#!/usr/bin/env python3
"""Pre-flight gate before wiring MGT roundtrip → global FEA (honest; no native solve)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_mgt_roundtrip_assembly_fingerprint import build_mgt_roundtrip_assembly_fingerprint
from design_optimization.io import load_json


SCHEMA_VERSION = "mgt-global-fea-readiness-gate.v1"


def _section_count(roundtrip: dict[str, Any], key: str) -> int:
    parser = roundtrip.get("parser") if isinstance(roundtrip.get("parser"), dict) else {}
    counts = parser.get("section_counts") if isinstance(parser.get("section_counts"), dict) else {}
    try:
        return int(counts.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def build_mgt_global_fea_readiness_gate(
    *,
    roundtrip_json: Path,
    roundtrip_npz: Path | None = None,
    parse_report_json: Path | None = None,
    mgt_path: Path | None = None,
    min_elements: int = 1000,
    min_nodes: int = 1000,
) -> dict[str, Any]:
    blockers: list[str] = []
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    parse_report_json = parse_report_json or roundtrip_json.with_name(roundtrip_json.stem + ".parse_report.json")

    if not roundtrip_json.is_file():
        blockers.append("roundtrip_json_missing")
        roundtrip: dict[str, Any] = {}
    else:
        roundtrip = load_json(roundtrip_json)

    element_count = _section_count(roundtrip, "ELEMENT")
    node_count = _section_count(roundtrip, "NODE")
    if element_count < min_elements:
        blockers.append("element_count_below_min")
    if node_count < min_nodes:
        blockers.append("node_count_below_min")

    npz_ready = roundtrip_npz.is_file() and roundtrip_npz.stat().st_size > 0
    if not npz_ready:
        blockers.append("roundtrip_npz_missing")

    parse_pass = False
    parse_report: dict[str, Any] = {}
    if parse_report_json.is_file():
        parse_report = load_json(parse_report_json)
        parse_pass = bool(parse_report.get("contract_pass", parse_report.get("pass", False)))
    if not parse_pass:
        blockers.append("parse_report_not_pass")

    mgt_exists = bool(mgt_path and mgt_path.is_file())
    if mgt_path and not mgt_exists:
        blockers.append("mgt_file_missing")

    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    assembly_fingerprint = build_mgt_roundtrip_assembly_fingerprint(
        roundtrip_json=roundtrip_json,
        roundtrip_npz=roundtrip_npz,
    )
    if assembly_fingerprint.get("status") != "ready":
        blockers.extend(f"assembly_{item}" for item in assembly_fingerprint.get("blockers") or [])
    readiness = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if readiness else "blocked",
        "claim": "Roundtrip/NPZ/parse preflight only; does not run global FEA on full MGT mesh.",
        "native_solve_status": "not_wired",
        "readiness_for_global_fea_wiring": readiness,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "parse_report_json": str(parse_report_json),
        "mgt_path": str(mgt_path) if mgt_path else "",
        "metrics": {
            "element_count": element_count,
            "node_count": node_count,
            "npz_bytes": int(roundtrip_npz.stat().st_size) if npz_ready else 0,
            "parse_contract_pass": parse_pass,
            "source_sha256": source.get("sha256"),
        },
        "assembly_fingerprint": assembly_fingerprint,
        "blockers": blockers,
        "next_step": "Connect roundtrip NPZ assembly to licensed/global nonlinear solver export replay.",
    }


def write_gate(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
