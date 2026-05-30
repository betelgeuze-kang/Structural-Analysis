#!/usr/bin/env python3
"""Sync MGT export artifacts: parse optimized .mgt and refresh roundtrip JSON provenance."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "sync-mgt-roundtrip-provenance.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_roundtrip_source_from_mgt(
    *,
    roundtrip_json: Path,
    mgt_path: Path,
    write_back: bool = True,
) -> dict[str, Any]:
    """Update roundtrip JSON `source` block from the on-disk optimized MGT file."""
    mgt_path = mgt_path.resolve()
    if not mgt_path.is_file():
        return {"status": "missing_mgt", "mgt_path": str(mgt_path)}

    actual_sha = _sha256_file(mgt_path)
    size_bytes = int(mgt_path.stat().st_size)

    if roundtrip_json.is_file():
        payload = _load_json(roundtrip_json)
        previous_sha = str((payload.get("source") or {}).get("sha256") or "")
    else:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-midas-mgt-model",
        }
        previous_sha = ""

    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["source"] = {
        "path": (
            str(mgt_path.relative_to(REPO_ROOT))
            if str(mgt_path).startswith(str(REPO_ROOT))
            else str(mgt_path)
        ),
        "sha256": actual_sha,
        "size_bytes": size_bytes,
        "format": "midas_mgt",
        "source_family": "midas_mgt",
    }

    if write_back:
        _write_json(roundtrip_json, payload)

    return {
        "status": "synced",
        "mgt_path": str(mgt_path),
        "roundtrip_json": str(roundtrip_json),
        "previous_sha256": previous_sha,
        "sha256": actual_sha,
        "sha256_changed": bool(previous_sha) and previous_sha.lower() != actual_sha.lower(),
        "size_bytes": size_bytes,
    }


def run_parse_mgt_to_roundtrip(
    *,
    mgt_path: Path,
    roundtrip_json: Path,
    npz_out: Path | None = None,
    report_out: Path | None = None,
    edge_list_out: Path | None = None,
) -> dict[str, Any]:
    """Invoke parse_midas_mgt_to_json_npz to rebuild roundtrip JSON (+ optional NPZ)."""
    mgt_path = mgt_path.resolve()
    roundtrip_json = roundtrip_json.resolve()
    npz_out = npz_out or roundtrip_json.with_suffix(".npz")
    report_out = report_out or roundtrip_json.with_name(roundtrip_json.stem + ".parse_report.json")
    edge_list_out = edge_list_out or roundtrip_json.with_name(roundtrip_json.stem + ".edges.json")

    cmd = [
        sys.executable,
        str(REPO_ROOT / "implementation/phase1/parse_midas_mgt_to_json_npz.py"),
        "--mgt",
        str(mgt_path),
        "--json-out",
        str(roundtrip_json),
        "--npz-out",
        str(npz_out),
        "--edge-list-out",
        str(edge_list_out),
        "--report-out",
        str(report_out),
        "--forbid-synthetic-source",
        "--no-require-shell-beam-mix",
        "--min-elements",
        "1",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False, capture_output=True, text=True)
    report = _load_json(report_out) if report_out.is_file() else {}
    contract_pass = bool(report.get("contract_pass", report.get("pass", False)))
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    return {
        "status": "pass" if proc.returncode == 0 and contract_pass else "failed",
        "exit_code": proc.returncode,
        "contract_pass": contract_pass,
        "roundtrip_json": str(roundtrip_json),
        "npz_out": str(npz_out),
        "report_out": str(report_out),
        "element_count": int(metrics.get("element_count", 0) or 0),
        "node_count": int(metrics.get("node_count", 0) or 0),
        "log_tail": (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:],
    }


def refresh_optimized_roundtrip_from_mgt(
    *,
    mgt_path: Path,
    roundtrip_json: Path,
    npz_out: Path | None = None,
    parse_refresh: bool = True,
    sync_provenance_only: bool = False,
) -> dict[str, Any]:
    """Full refresh: optional re-parse, always sync source sha256 to match MGT."""
    steps: list[dict[str, Any]] = []
    parse_result: dict[str, Any] | None = None

    if parse_refresh and not sync_provenance_only:
        parse_result = run_parse_mgt_to_roundtrip(
            mgt_path=mgt_path,
            roundtrip_json=roundtrip_json,
            npz_out=npz_out,
        )
        steps.append({"step": "parse_mgt", **parse_result})
        if parse_result.get("status") != "pass":
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "parse_failed",
                "steps": steps,
                "parse": parse_result,
            }

    sync_result = sync_roundtrip_source_from_mgt(roundtrip_json=roundtrip_json, mgt_path=mgt_path)
    steps.append({"step": "sync_provenance", **sync_result})

    integrity = "verified" if sync_result.get("status") == "synced" else "missing_mgt"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if integrity == "verified" else "blocked",
        "mgt_path": str(mgt_path),
        "roundtrip_json": str(roundtrip_json),
        "npz_out": str(npz_out or roundtrip_json.with_suffix(".npz")),
        "integrity_status": integrity,
        "sha256": sync_result.get("sha256"),
        "parse": parse_result,
        "steps": steps,
    }
