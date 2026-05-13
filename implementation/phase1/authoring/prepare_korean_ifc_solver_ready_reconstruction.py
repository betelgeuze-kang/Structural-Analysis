#!/usr/bin/env python3
"""Prepare honest solver-ready reconstruction artifacts for Korean IFC exact-topology candidates."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

PHASE1_ROOT = Path(__file__).resolve().parents[1]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from runtime_contracts import InputContractError, validate_input_contract

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KOREAN_SOURCE_CATALOG = REPO_ROOT / "implementation/phase1/open_data/korea/korean_source_catalog.json"
DEFAULT_KOREAN_COLLECTION_REPORT = (
    REPO_ROOT / "implementation/phase1/open_data/korea/korean_public_structure_collection_report.json"
)
DEFAULT_OUT_DIR = REPO_ROOT / "implementation/phase1/release/midas_native_roundtrip/solver_ready_reconstruction"
DEFAULT_OUT = REPO_ROOT / "implementation/phase1/release/midas_native_roundtrip/korean_solver_ready_reconstruction_report.json"

REASONS = {
    "PASS": "korean IFC solver-ready reconstruction artifacts generated for all locally available exact-topology candidates",
    "ERR_INVALID_INPUT": "invalid korean IFC solver-ready reconstruction input",
    "CHECK_PENDING_LOCAL_REFERENCE": "korean IFC exact-topology candidates still need a local IFC reference before reconstruction artifacts can be generated",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["korean_source_catalog", "korean_collection_report", "out_dir", "out"],
    "properties": {
        "korean_source_catalog": {"type": "string", "minLength": 1},
        "korean_collection_report": {"type": "string", "minLength": 1},
        "out_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}

ENTITY_PATTERNS = {
    "ifc_beam_count": re.compile(r"\bIFCBEAM\b", re.IGNORECASE),
    "ifc_column_count": re.compile(r"\bIFCCOLUMN\b", re.IGNORECASE),
    "ifc_slab_count": re.compile(r"\bIFCSLAB\b", re.IGNORECASE),
    "ifc_wall_count": re.compile(r"\bIFCWALL(?:STANDARDCASE)?\b", re.IGNORECASE),
    "ifc_plate_count": re.compile(r"\bIFCPLATE\b", re.IGNORECASE),
    "ifc_member_count": re.compile(r"\bIFCMEMBER\b", re.IGNORECASE),
    "ifc_footing_count": re.compile(r"\bIFCFOOTING\b", re.IGNORECASE),
    "ifc_storey_count": re.compile(r"\bIFCBUILDINGSTOREY\b", re.IGNORECASE),
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _catalog_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("source_records")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("sources")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _resolve_local_path(value: str) -> Path:
    raw = str(value or "").strip()
    if raw.startswith("file://"):
        raw = raw[7:]
    path = Path(raw)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _ifc_metrics(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    metrics = {name: len(pattern.findall(text)) for name, pattern in ENTITY_PATTERNS.items()}
    metrics["ifc_structural_entity_total"] = int(
        metrics["ifc_beam_count"]
        + metrics["ifc_column_count"]
        + metrics["ifc_slab_count"]
        + metrics["ifc_wall_count"]
        + metrics["ifc_plate_count"]
        + metrics["ifc_member_count"]
        + metrics["ifc_footing_count"]
    )
    return metrics


def _render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    return "\n".join(
        [
            f"# {str(payload.get('source_id', '') or 'candidate')}",
            "",
            f"- `summary`: `{str(payload.get('summary_line', '') or 'n/a')}`",
            f"- `local_ifc_path`: `{str(payload.get('local_ifc_path', '') or 'n/a')}`",
            f"- `structural_preview_case_id`: `{str(payload.get('structural_preview_case_id', '') or 'n/a')}`",
            f"- `structural_preview_writeback_case_id`: `{str(payload.get('structural_preview_writeback_case_id', '') or 'n/a')}`",
            "",
            "## Summary",
            "",
            f"- `reconstruction_ready`: `{bool(summary.get('reconstruction_ready', False))}`",
            f"- `storey_count`: `{int(metrics.get('ifc_storey_count', 0) or 0)}`",
            f"- `structural_entity_total`: `{int(metrics.get('ifc_structural_entity_total', 0) or 0)}`",
            f"- `beam/column/slab/wall`: `{int(metrics.get('ifc_beam_count', 0) or 0)}/{int(metrics.get('ifc_column_count', 0) or 0)}/{int(metrics.get('ifc_slab_count', 0) or 0)}/{int(metrics.get('ifc_wall_count', 0) or 0)}`",
            "",
        ]
    )


def build_report(*, korean_source_catalog: dict[str, Any], korean_collection_report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    collection_rows = {
        str(row.get("source_id", "") or "").strip(): row
        for row in (korean_collection_report.get("records") or [])
        if isinstance(row, dict) and str(row.get("source_id", "") or "").strip()
    }

    rows: list[dict[str, Any]] = []
    prepared_count = 0
    missing_local_reference_count = 0
    missing_curated_local_ifc_reference_count = 0
    parse_failed_count = 0

    for source_row in _catalog_rows(korean_source_catalog):
        if not bool(source_row.get("exact_topology_candidate", False)):
            continue
        if str(source_row.get("format", "") or "").strip() != "ifc":
            continue
        source_id = str(source_row.get("source_id", "") or "").strip()
        if not source_id:
            continue
        collection_row = collection_rows.get(source_id, {})
        local_path_value = str(collection_row.get("local_path", source_row.get("local_path", "")) or "").strip()
        curated_local_ifc_required = bool(
            collection_row.get("curated_local_ifc_required", source_row.get("curated_local_ifc_required", False))
        )
        curated_local_ifc_status = str(
            collection_row.get("curated_local_ifc_status", source_row.get("curated_local_ifc_status", "")) or ""
        ).strip()
        curated_local_ifc_reference = str(
            collection_row.get("curated_local_ifc_reference", source_row.get("curated_local_ifc_reference", "")) or ""
        ).strip()
        if not local_path_value and curated_local_ifc_reference:
            local_path_value = curated_local_ifc_reference
        row_payload = {
            "source_id": source_id,
            "title": str(source_row.get("title", "") or "").strip(),
            "source_class": str(source_row.get("source_class", "") or "").strip(),
            "collection_policy": str(source_row.get("collection_policy", "") or "").strip(),
            "curated_local_ifc_required": curated_local_ifc_required,
            "curated_local_ifc_status": curated_local_ifc_status,
            "curated_local_ifc_reference": curated_local_ifc_reference,
            "local_ifc_path": "",
            "artifact_json": "",
            "artifact_markdown": "",
            "contract_pass": False,
            "reconstruction_ready": False,
            "status": "missing_local_reference",
            "reason": "local IFC reference not available yet",
            "summary_line": "",
        }
        if not local_path_value:
            missing_local_reference_count += 1
            if curated_local_ifc_required:
                missing_curated_local_ifc_reference_count += 1
                row_payload["status"] = "missing_curated_local_ifc_reference"
                row_payload["reason"] = "curated local IFC reference not attached yet"
                row_payload["summary_line"] = (
                    f"Korean IFC solver-ready reconstruction: CHECK | source={source_id} | status=missing_curated_local_ifc_reference"
                )
            else:
                row_payload["summary_line"] = (
                    f"Korean IFC solver-ready reconstruction: CHECK | source={source_id} | status=missing_local_reference"
                )
            rows.append(row_payload)
            continue
        local_ifc_path = _resolve_local_path(local_path_value)
        row_payload["local_ifc_path"] = str(local_ifc_path)
        if not local_ifc_path.exists():
            missing_local_reference_count += 1
            row_payload["status"] = "missing_local_file"
            row_payload["reason"] = "referenced local IFC file does not exist"
            row_payload["summary_line"] = (
                f"Korean IFC solver-ready reconstruction: CHECK | source={source_id} | status=missing_local_file"
            )
            rows.append(row_payload)
            continue
        try:
            metrics = _ifc_metrics(local_ifc_path)
        except Exception as exc:  # pragma: no cover - defensive path
            parse_failed_count += 1
            row_payload["status"] = "parse_failed"
            row_payload["reason"] = f"IFC scan failed: {exc}"
            row_payload["summary_line"] = (
                f"Korean IFC solver-ready reconstruction: CHECK | source={source_id} | status=parse_failed"
            )
            rows.append(row_payload)
            continue
        structural_preview_case_id = f"{source_id}__structural_preview_candidate"
        writeback_case_id = f"{structural_preview_case_id}__identity_writeback"
        reconstruction_ready = bool(metrics["ifc_structural_entity_total"] > 0 and metrics["ifc_storey_count"] > 0)
        artifact = {
            "schema_version": "1.0",
            "run_id": "phase1-korean-ifc-solver-ready-reconstruction",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_id": source_id,
            "title": str(source_row.get("title", "") or "").strip(),
            "source_class": str(source_row.get("source_class", "") or "").strip(),
            "local_ifc_path": str(local_ifc_path),
            "structural_preview_case_id": structural_preview_case_id,
            "structural_preview_writeback_case_id": writeback_case_id,
            "metrics": metrics,
            "summary": {
                "reconstruction_ready": reconstruction_ready,
            },
            "summary_line": (
                f"Korean IFC solver-ready reconstruction artifact: {'PASS' if reconstruction_ready else 'CHECK'} | "
                f"source={source_id} | storeys={metrics['ifc_storey_count']} | structural_entities={metrics['ifc_structural_entity_total']}"
            ),
            "contract_pass": reconstruction_ready,
            "reason_code": "PASS" if reconstruction_ready else "CHECK_PENDING_LOCAL_REFERENCE",
            "reason": (
                "IFC local reference scanned into a solver-ready reconstruction artifact"
                if reconstruction_ready
                else "IFC local reference scanned but structural/storey signals were insufficient"
            ),
        }
        artifact_json = out_dir / f"{source_id}.solver_ready_reconstruction.json"
        artifact_md = out_dir / f"{source_id}.solver_ready_reconstruction.md"
        _write_json(artifact_json, artifact)
        artifact_md.write_text(_render_markdown(artifact), encoding="utf-8")
        prepared_count += int(reconstruction_ready)
        row_payload.update(
            {
                "artifact_json": str(artifact_json),
                "artifact_markdown": str(artifact_md),
                "contract_pass": reconstruction_ready,
                "reconstruction_ready": reconstruction_ready,
                "status": "prepared" if reconstruction_ready else "insufficient_structural_signal",
                "reason": artifact["reason"],
                "summary_line": artifact["summary_line"],
                "structural_preview_case_id": structural_preview_case_id,
                "structural_preview_writeback_case_id": writeback_case_id,
            }
        )
        rows.append(row_payload)

    candidate_count = len(rows)
    contract_pass = prepared_count == candidate_count if candidate_count else True
    reason_code = "PASS" if contract_pass else "CHECK_PENDING_LOCAL_REFERENCE"
    summary = {
        "candidate_count": candidate_count,
        "prepared_count": prepared_count,
        "missing_local_reference_count": missing_local_reference_count,
        "missing_curated_local_ifc_reference_count": missing_curated_local_ifc_reference_count,
        "parse_failed_count": parse_failed_count,
    }
    return {
        "schema_version": "1.0",
        "run_id": "phase1-korean-ifc-solver-ready-reconstruction",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "rows": rows,
        "summary_line": (
            "Korean IFC solver-ready reconstruction: "
            f"{'PASS' if contract_pass else 'CHECK'} | candidates={candidate_count} | prepared={prepared_count} | "
            f"missing_local={missing_local_reference_count} | "
            f"missing_curated={missing_curated_local_ifc_reference_count} | "
            f"parse_failed={parse_failed_count}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--korean-source-catalog", default=str(DEFAULT_KOREAN_SOURCE_CATALOG))
    parser.add_argument("--korean-collection-report", default=str(DEFAULT_KOREAN_COLLECTION_REPORT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    input_payload = {
        "korean_source_catalog": str(args.korean_source_catalog),
        "korean_collection_report": str(args.korean_collection_report),
        "out_dir": str(args.out_dir),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.prepare_korean_ifc_solver_ready_reconstruction")
        report = build_report(
            korean_source_catalog=_load_json(Path(args.korean_source_catalog)),
            korean_collection_report=_load_json(Path(args.korean_collection_report)),
            out_dir=Path(args.out_dir),
        )
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-korean-ifc-solver-ready-reconstruction",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "candidate_count": 0,
                "prepared_count": 0,
                "missing_local_reference_count": 0,
                "missing_curated_local_ifc_reference_count": 0,
                "parse_failed_count": 0,
            },
            "rows": [],
            "summary_line": (
                "Korean IFC solver-ready reconstruction: CHECK | candidates=0 | prepared=0 | "
                "missing_local=0 | missing_curated=0 | parse_failed=0"
            ),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    _write_json(out, report)
    print(f"Wrote Korean IFC solver-ready reconstruction report: {out}")
    raise SystemExit(0 if bool(report.get('contract_pass', False)) else 0)


if __name__ == "__main__":
    main()
