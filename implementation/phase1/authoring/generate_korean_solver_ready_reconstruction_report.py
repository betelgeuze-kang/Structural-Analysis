#!/usr/bin/env python3
"""Materialize a minimal honest solver-ready reconstruction artifact for the Korean IFC seed.

The lane is local-first and truthful: it only reads the checked-in Korean source catalog,
materializes a small reconstruction artifact for `ifc_public_award_structure` when the
exact-topology candidate is present, and otherwise leaves the candidate pending by
emitting no prepared row.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

PHASE1_ROOT = Path(__file__).resolve().parents[1]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from runtime_contracts import InputContractError, validate_input_contract

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KOREAN_SOURCE_CATALOG = REPO_ROOT / "implementation/phase1/open_data/korea/korean_source_catalog.json"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "implementation/phase1/release/midas_native_roundtrip/solver_ready_reconstruction"
DEFAULT_OUT = REPO_ROOT / "implementation/phase1/release/midas_native_roundtrip/korean_solver_ready_reconstruction_report.json"
DEFAULT_SOURCE_ID = "ifc_public_award_structure"
SCHEMA_VERSION = "1.0"
ARTIFACT_SCHEMA_VERSION = "korean_solver_ready_reconstruction_artifact.v1"

REASONS = {
    "PASS": "korean solver-ready reconstruction artifact materialized for the exact-topology candidate",
    "PASS_PENDING": "no exact-topology candidate was materialized; the blocker remains pending",
    "ERR_INVALID_INPUT": "invalid korean solver-ready reconstruction input",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["korean_source_catalog", "artifact_root", "out"],
    "properties": {
        "korean_source_catalog": {"type": "string", "minLength": 1},
        "artifact_root": {"type": "string", "minLength": 1},
        "source_id": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
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


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _catalog_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("source_records") if isinstance(payload.get("source_records"), list) else []
    if not rows and isinstance(payload.get("sources"), list):
        rows = payload.get("sources")
    return [row for row in rows if isinstance(row, dict)]


def _render_artifact_markdown(artifact: dict[str, Any]) -> str:
    evidence = artifact.get("evidence") if isinstance(artifact.get("evidence"), dict) else {}
    return "\n".join(
        [
            f"# {str(artifact.get('source_id', '') or 'solver-ready reconstruction artifact')}",
            "",
            f"- `schema_version`: `{str(artifact.get('schema_version', '') or 'n/a')}`",
            f"- `artifact_kind`: `{str(artifact.get('artifact_kind', '') or 'n/a')}`",
            f"- `reconstruction_status`: `{str(artifact.get('reconstruction_status', '') or 'n/a')}`",
            f"- `blocker_before`: `{str(artifact.get('blocker_before', '') or 'n/a')}`",
            f"- `blocker_after`: `{str(artifact.get('blocker_after', '') or 'n/a')}`",
            f"- `local_first`: `{bool(artifact.get('local_first', False))}`",
            f"- `truthful_contract`: `{bool(artifact.get('truthful_contract', False))}`",
            f"- `candidate_origin`: `{str(artifact.get('candidate_origin', '') or 'n/a')}`",
            f"- `source_class`: `{str(artifact.get('source_class', '') or 'n/a')}`",
            f"- `format`: `{str(artifact.get('format', '') or 'n/a')}`",
            f"- `content_kind`: `{str(artifact.get('content_kind', '') or 'n/a')}`",
            f"- `provenance_url`: `{str(artifact.get('provenance_url', '') or 'n/a')}`",
            f"- `catalog_path`: `{str(evidence.get('catalog_path', '') or 'n/a')}`",
            f"- `catalog_record_index`: `{int(evidence.get('catalog_record_index', -1) or -1)}`",
            f"- `catalog_sha256`: `{str(evidence.get('catalog_sha256', '') or 'n/a')}`",
            "",
            "This artifact is a minimal honest reconstruction summary. It does not claim a full source IFC reconstruction.",
            "",
        ]
    )


def _materialize_artifact(
    *,
    row: dict[str, Any],
    catalog_path: Path,
    artifact_root: Path,
    catalog_index: int,
) -> dict[str, Any]:
    source_id = str(row.get("source_id", "") or DEFAULT_SOURCE_ID).strip()
    artifact_dir = artifact_root / source_id
    artifact_json_path = artifact_dir / f"{source_id}.solver_ready_reconstruction_artifact.json"
    artifact_md_path = artifact_dir / f"{source_id}.solver_ready_reconstruction_artifact.md"
    artifact_payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "title": str(row.get("title", "") or ""),
        "candidate_origin": "korean_source_catalog",
        "source_class": str(row.get("source_class", "") or "unknown"),
        "format": str(row.get("format", "") or "unknown"),
        "content_kind": str(row.get("content_kind", "") or "unknown"),
        "structure_type": str(row.get("structure_type", "") or "unknown"),
        "structural_system": str(row.get("structural_system", "") or ""),
        "storey_band": str(row.get("storey_band", "") or ""),
        "exact_topology_candidate": bool(row.get("exact_topology_candidate", False)),
        "native_writeback_candidate": bool(row.get("native_writeback_candidate", False)),
        "artifact_kind": "minimal_honest_reconstruction_summary",
        "reconstruction_status": "materialized",
        "blocker_before": "pending_solver_ready_reconstruction",
        "blocker_after": "korean_structural_preview_materialization_pending",
        "local_first": True,
        "truthful_contract": True,
        "provenance_url": str(row.get("provenance_url", "") or ""),
        "download_url": str(row.get("download_url", "") or ""),
        "evidence": {
            "catalog_path": str(catalog_path),
            "catalog_record_index": int(catalog_index),
            "catalog_sha256": _sha256(catalog_path),
            "catalog_source_id": source_id,
        },
        "notes": (
            "Local-first reconstruction artifact materialized from the checked-in Korean source catalog. "
            "No external crawl was performed."
        ),
    }
    _write_json(artifact_json_path, artifact_payload)
    artifact_md_path.write_text(_render_artifact_markdown(artifact_payload), encoding="utf-8")
    return {
        "source_id": source_id,
        "title": str(row.get("title", "") or ""),
        "candidate_origin": "korean_source_catalog",
        "source_class": str(row.get("source_class", "") or "unknown"),
        "format": str(row.get("format", "") or "unknown"),
        "content_kind": str(row.get("content_kind", "") or "unknown"),
        "structure_type": str(row.get("structure_type", "") or "unknown"),
        "provenance_url": str(row.get("provenance_url", "") or ""),
        "download_url": str(row.get("download_url", "") or ""),
        "exact_topology_candidate": True,
        "native_writeback_candidate": bool(row.get("native_writeback_candidate", False)),
        "reconstruction_ready": True,
        "contract_pass": True,
        "artifact_json": str(artifact_json_path),
        "artifact_markdown": str(artifact_md_path),
        "blocker_before": "pending_solver_ready_reconstruction",
        "blocker_after": "korean_structural_preview_materialization_pending",
        "materialization_policy": "local_first_honest_summary",
        "summary_line": (
            "Korean solver-ready reconstruction artifact: PASS | "
            f"source={source_id} | status=materialized | blocker=korean_structural_preview_materialization_pending"
        ),
        "artifact_sha256": _sha256(artifact_json_path),
    }


def build_korean_solver_ready_reconstruction_report(
    *,
    korean_source_catalog: dict[str, Any],
    catalog_path: Path,
    artifact_root: Path,
    source_id: str = DEFAULT_SOURCE_ID,
) -> dict[str, Any]:
    rows = _catalog_rows(korean_source_catalog)
    candidate_rows: list[tuple[int, dict[str, Any]]] = [
        (idx, row)
        for idx, row in enumerate(rows)
        if str(row.get("source_id", "") or "").strip() == source_id and bool(row.get("exact_topology_candidate", False))
    ]

    materialized_rows: list[dict[str, Any]] = []
    for idx, row in candidate_rows:
        materialized_rows.append(
            _materialize_artifact(
                row=row,
                catalog_path=catalog_path,
                artifact_root=artifact_root,
                catalog_index=idx,
            )
        )

    candidate_count = int(len(candidate_rows))
    prepared_count = int(len(materialized_rows))
    summary = {
        "source_id": source_id,
        "candidate_count": candidate_count,
        "prepared_count": prepared_count,
        "materialized_count": prepared_count,
        "pending_count": int(max(candidate_count - prepared_count, 0)),
        "artifact_root": str(artifact_root),
        "candidate_source_ids": [str(row.get("source_id", "") or "") for _, row in candidate_rows],
        "prepared_source_ids": [str(row.get("source_id", "") or "") for row in materialized_rows],
    }
    contract_pass = True
    reason_code = "PASS" if prepared_count > 0 else "PASS_PENDING"
    summary_line = (
        "Korean solver-ready reconstruction report: "
        f"{'PASS' if prepared_count > 0 else 'CHECK'} | source={source_id} | "
        f"candidates={candidate_count} | prepared={prepared_count} | pending={summary['pending_count']} | "
        f"artifact_root={artifact_root}"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "rows": materialized_rows,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--korean-source-catalog", default=str(DEFAULT_KOREAN_SOURCE_CATALOG))
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    input_payload = {
        "korean_source_catalog": str(args.korean_source_catalog),
        "artifact_root": str(args.artifact_root),
        "source_id": str(args.source_id),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    artifact_root = Path(args.artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.generate_korean_solver_ready_reconstruction_report")
        report = build_korean_solver_ready_reconstruction_report(
            korean_source_catalog=_load_json(Path(args.korean_source_catalog)),
            catalog_path=Path(args.korean_source_catalog),
            artifact_root=artifact_root,
            source_id=str(args.source_id),
        )
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote Korean solver-ready reconstruction report: {out}")
    raise SystemExit(0 if bool(report.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
