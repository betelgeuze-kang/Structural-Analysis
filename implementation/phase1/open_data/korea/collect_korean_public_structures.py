#!/usr/bin/env python3
"""Collect a local-first Korean public-structure source catalog draft."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[4]
KOREA_OPEN_DATA_DIR = REPO_ROOT / "implementation/phase1/open_data/korea"
DEFAULT_CATALOG = KOREA_OPEN_DATA_DIR / "korean_source_catalog.json"
DEFAULT_OUT_DIR = KOREA_OPEN_DATA_DIR / "collected"
DEFAULT_REPORT_OUT = KOREA_OPEN_DATA_DIR / "korean_public_structure_collection_report.json"
SCHEMA_VERSION = "1.0"
COLLECTOR_VERSION = "0.1.0"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_reference(record: dict[str, Any], catalog_path: Path) -> tuple[str, str, Path | None, str]:
    raw_ref = (
        str(record.get("local_path") or "").strip()
        or str(record.get("curated_local_ifc_reference") or "").strip()
        or str(record.get("download_url") or "").strip()
        or str(record.get("provenance_url") or "").strip()
    )
    if not raw_ref:
        return "", "missing", None, "missing local_path/download_url/provenance_url"

    parsed = urlparse(raw_ref)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            return raw_ref, "file_url", None, "unsupported file url host"
        return raw_ref, "file_url", Path(unquote(parsed.path)), ""
    if parsed.scheme in {"http", "https"}:
        return raw_ref, "remote_reference", None, ""
    if parsed.scheme not in {"", None}:
        return raw_ref, parsed.scheme.lower(), None, "unsupported source scheme"

    candidate = Path(raw_ref)
    if not candidate.is_absolute():
        repo_candidate = (REPO_ROOT / candidate).resolve()
        catalog_candidate = (catalog_path.parent / candidate).resolve()
        candidate = catalog_candidate if catalog_candidate.exists() else repo_candidate
    return raw_ref, "local_path", candidate, ""


def _copied_name(source_id: str, source_format: str, resolved_path: Path) -> str:
    if resolved_path.suffix:
        return f"{source_id}{resolved_path.suffix.lower()}"
    suffix = f".{source_format}" if source_format and source_format != "unknown" else ".bin"
    return f"{source_id}{suffix}"


def collect_korean_public_structures(catalog_path: Path, out_dir: Path, report_out: Path) -> dict[str, Any]:
    catalog = _load_json(catalog_path)
    rows = catalog.get("source_records") if isinstance(catalog.get("source_records"), list) else []
    if not rows and isinstance(catalog.get("sources"), list):
        rows = catalog.get("sources")
    if not rows:
        raise ValueError("source_records or sources is required")

    artifact_root = out_dir / "artifacts"
    per_source_reports_dir = out_dir / "reports"
    now = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()

    local_path_count = 0
    file_url_count = 0
    remote_reference_count = 0
    metadata_only_count = 0
    collected_count = 0
    rejected_count = 0
    total_bytes_copied = 0
    format_counts: dict[str, int] = {}
    content_kind_counts: dict[str, int] = {}
    ingest_status_counts: dict[str, int] = {}
    seed_priority_counts: dict[str, int] = {}
    promotion_hint_counts: dict[str, int] = {}
    collection_policy_counts: dict[str, int] = {}
    exact_topology_candidate_count = 0
    native_writeback_candidate_count = 0
    seed_metadata_complete_count = 0
    p0_focus_candidate_count = 0
    curated_local_ifc_required_count = 0
    curated_local_ifc_attached_count = 0

    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        source_id = str(row.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source_id is required")
        if source_id in seen_source_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen_source_ids.add(source_id)
        source_format = str(row.get("format") or "unknown").strip()
        content_kind = str(row.get("content_kind") or "").strip()
        seed_priority = str(row.get("seed_priority") or "").strip()
        promotion_hint = str(row.get("promotion_hint") or "").strip()
        collection_policy = str(row.get("collection_policy") or "").strip()
        exact_topology_candidate = bool(row.get("exact_topology_candidate", False))
        native_writeback_candidate = bool(row.get("native_writeback_candidate", False))
        curated_local_ifc_required = bool(row.get("curated_local_ifc_required", False))
        curated_local_ifc_status = str(row.get("curated_local_ifc_status", "") or "").strip()
        curated_local_ifc_reference = str(row.get("curated_local_ifc_reference", "") or "").strip()
        resolved_ref, scheme, resolved_path, error = _resolve_reference(row, catalog_path)
        record: dict[str, Any] = {
            "source_id": source_id,
            "source_class": str(row.get("source_class") or "").strip(),
            "format": source_format,
            "content_kind": content_kind,
            "seed_basis": str(row.get("seed_basis") or "").strip(),
            "seed_priority": seed_priority,
            "promotion_hint": promotion_hint,
            "collection_policy": collection_policy,
            "curated_local_ifc_required": curated_local_ifc_required,
            "curated_local_ifc_status": curated_local_ifc_status,
            "curated_local_ifc_reference": curated_local_ifc_reference,
            "provenance_url": str(row.get("provenance_url") or "").strip(),
            "download_url": str(row.get("download_url") or "").strip(),
            "license_hint": str(row.get("license_hint") or "").strip(),
            "resolved_reference": resolved_ref,
            "reference_scheme": scheme,
            "retrieved_at_utc": now,
            "status": "",
            "ingest_status": "",
            "reason": "",
            "sha256": "",
            "local_path": "",
            "byte_count": 0,
            "artifacts": {},
        }

        if source_format:
            format_counts[source_format] = format_counts.get(source_format, 0) + 1
        if content_kind:
            content_kind_counts[content_kind] = content_kind_counts.get(content_kind, 0) + 1
        if seed_priority:
            seed_priority_counts[seed_priority] = seed_priority_counts.get(seed_priority, 0) + 1
        if promotion_hint:
            promotion_hint_counts[promotion_hint] = promotion_hint_counts.get(promotion_hint, 0) + 1
        if collection_policy:
            collection_policy_counts[collection_policy] = collection_policy_counts.get(collection_policy, 0) + 1
        if exact_topology_candidate:
            exact_topology_candidate_count += 1
        if native_writeback_candidate:
            native_writeback_candidate_count += 1
        if curated_local_ifc_required:
            curated_local_ifc_required_count += 1
        if curated_local_ifc_status == "attached":
            curated_local_ifc_attached_count += 1
        if record["seed_basis"] and seed_priority and promotion_hint and collection_policy:
            seed_metadata_complete_count += 1
        if seed_priority == "P0" and (
            exact_topology_candidate or native_writeback_candidate or promotion_hint == "preview_roundtrip_candidate"
        ):
            p0_focus_candidate_count += 1

        if scheme == "local_path":
            local_path_count += 1
        elif scheme == "file_url":
            file_url_count += 1
        elif scheme == "remote_reference":
            remote_reference_count += 1

        if error:
            record["status"] = "rejected"
            record["ingest_status"] = "rejected"
            record["reason"] = error
            rejected_count += 1
        elif scheme in {"local_path", "file_url"} and resolved_path is not None and resolved_path.exists():
            artifact_dir = artifact_root / source_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            copied_path = artifact_dir / _copied_name(source_id, source_format, resolved_path)
            shutil.copy2(resolved_path, copied_path)
            sha256 = _sha256(copied_path)
            byte_count = copied_path.stat().st_size
            source_metadata_path = per_source_reports_dir / f"{source_id}.json"
            source_metadata = {
                "schema_version": SCHEMA_VERSION,
                "source_id": source_id,
                "download_mode": "file_copy" if scheme == "file_url" else "local_copy",
                "reference_scheme": scheme,
                "resolved_reference": resolved_ref,
                "retrieved_at_utc": now,
                "sha256": sha256,
                "byte_count": byte_count,
                "format": source_format,
                "content_kind": content_kind,
                "provenance_url": record["provenance_url"],
                "license_hint": record["license_hint"],
                "seed_basis": record["seed_basis"],
                "seed_priority": seed_priority,
                "promotion_hint": promotion_hint,
                "collection_policy": collection_policy,
                "exact_topology_candidate": exact_topology_candidate,
                "native_writeback_candidate": native_writeback_candidate,
                "curated_local_ifc_required": curated_local_ifc_required,
                "curated_local_ifc_status": curated_local_ifc_status,
                "curated_local_ifc_reference": curated_local_ifc_reference,
            }
            _write_json(source_metadata_path, source_metadata)
            record["status"] = "collected"
            record["ingest_status"] = "fingerprinted"
            record["sha256"] = sha256
            record["local_path"] = str(copied_path)
            record["byte_count"] = byte_count
            record["artifacts"] = {
                "copied_source_path": str(copied_path),
                "source_metadata_path": str(source_metadata_path),
            }
            collected_count += 1
            total_bytes_copied += byte_count
        elif scheme == "remote_reference":
            record["status"] = "metadata_only_remote_candidate"
            record["ingest_status"] = "discovered"
            if curated_local_ifc_required and not record["curated_local_ifc_reference"]:
                record["reason"] = "curated local IFC reference required before collection"
            else:
                record["reason"] = "remote reference retained as metadata-only candidate"
            metadata_only_count += 1
        else:
            record["status"] = "rejected"
            record["ingest_status"] = "rejected"
            record["reason"] = "local source path not found"
            rejected_count += 1

        ingest_status = record["ingest_status"]
        ingest_status_counts[ingest_status] = ingest_status_counts.get(ingest_status, 0) + 1
        records.append(record)

    summary = {
        "source_count": len(records),
        "collected_count": collected_count,
        "metadata_only_remote_candidate_count": metadata_only_count,
        "rejected_count": rejected_count,
        "local_path_count": local_path_count,
        "file_url_count": file_url_count,
        "remote_reference_count": remote_reference_count,
        "total_bytes_copied": total_bytes_copied,
        "format_counts": dict(sorted(format_counts.items())),
        "content_kind_counts": dict(sorted(content_kind_counts.items())),
        "ingest_status_counts": dict(sorted(ingest_status_counts.items())),
        "seed_priority_counts": dict(sorted(seed_priority_counts.items())),
        "promotion_hint_counts": dict(sorted(promotion_hint_counts.items())),
        "collection_policy_counts": dict(sorted(collection_policy_counts.items())),
        "seed_metadata_complete_count": seed_metadata_complete_count,
        "exact_topology_candidate_count": exact_topology_candidate_count,
        "native_writeback_candidate_count": native_writeback_candidate_count,
        "curated_local_ifc_required_count": curated_local_ifc_required_count,
        "curated_local_ifc_attached_count": curated_local_ifc_attached_count,
        "p0_focus_candidate_count": p0_focus_candidate_count,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "generated_at_utc": now,
        "inputs": {
            "catalog_path": str(catalog_path),
            "out_dir": str(out_dir),
            "report_out": str(report_out),
        },
        "summary": summary,
        "records": records,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "korean public structure catalog processed",
        "summary_line": (
            "Korean source collect: PASS | "
            f"sources={summary['source_count']} | collected={summary['collected_count']} | "
            f"metadata_only={summary['metadata_only_remote_candidate_count']} | rejected={summary['rejected_count']} | "
            f"bytes={summary['total_bytes_copied']} | seed_complete={summary['seed_metadata_complete_count']} | "
            f"exact_topology={summary['exact_topology_candidate_count']} | "
            f"native_writeback={summary['native_writeback_candidate_count']} | "
            f"curated_local_ifc={summary['curated_local_ifc_attached_count']}/{summary['curated_local_ifc_required_count']} | "
            f"p0_focus={summary['p0_focus_candidate_count']}"
        ),
    }
    _write_json(report_out, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT_OUT))
    args = parser.parse_args()

    report = collect_korean_public_structures(
        catalog_path=Path(args.catalog),
        out_dir=Path(args.out_dir),
        report_out=Path(args.report_out),
    )
    print(f"Wrote Korean public structure collection report: {args.report_out}")
    raise SystemExit(0 if report.get("contract_pass") else 1)


if __name__ == "__main__":
    main()
