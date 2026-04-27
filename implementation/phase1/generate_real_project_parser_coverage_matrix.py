#!/usr/bin/env python3
"""Generate the P1 parser and benchmark coverage matrix for real-project sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KONEPS_SOURCE_ID = "koneps_turnkey_design_docs"
PEER_TBI_SOURCE_ID = "peer_tbi_tall_buildings"
KONEPS_TARGET_FILE_TYPES = [".mgt", ".ifc", ".dwg", ".dxf", ".pdf", ".xlsx", ".zip"]
PEER_TBI_BENCHMARK_METRICS = ["period", "base_shear", "story_drift", "nonlinear_response", "citation"]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _access_policy(source: dict[str, Any]) -> dict[str, Any]:
    access_policy = source.get("access_policy")
    return access_policy if isinstance(access_policy, dict) else {}


def _planned_parser_targets(file_types: list[str]) -> list[dict[str, str]]:
    return [{"file_type": file_type, "coverage_status": "planned"} for file_type in file_types]


def _planned_metric_targets(metrics: list[str]) -> list[dict[str, str]]:
    return [{"metric": metric, "coverage_status": "planned"} for metric in metrics]


def _source_row(source: dict[str, Any]) -> dict[str, Any]:
    source_id = str(source.get("source_id", "") or "")
    access_policy = _access_policy(source)
    row: dict[str, Any] = {
        "source_id": source_id,
        "source_label": str(source.get("source_label", "") or ""),
        "source_kind": str(source.get("source_kind", "") or ""),
        "jurisdiction": str(source.get("jurisdiction", "") or ""),
        "priority_phase": str(source.get("priority_phase", "") or ""),
        "p0_provenance_required": True,
        "redistribution_allowed": bool(access_policy.get("redistribution_allowed", False)),
        "manual_review_required": bool(access_policy.get("requires_manual_review", True)),
    }

    if source_id == KONEPS_SOURCE_ID:
        row["parser_coverage_targets"] = _planned_parser_targets(KONEPS_TARGET_FILE_TYPES)
        row["benchmark_metric_targets"] = []
    elif source_id == PEER_TBI_SOURCE_ID:
        row["parser_coverage_targets"] = []
        row["benchmark_metric_targets"] = _planned_metric_targets(PEER_TBI_BENCHMARK_METRICS)
    else:
        target_file_types = [str(item) for item in source.get("target_file_types", []) if isinstance(item, str)]
        row["parser_coverage_targets"] = _planned_parser_targets(target_file_types)
        row["benchmark_metric_targets"] = []

    return row


def build_coverage_matrix(manifest: dict[str, Any]) -> dict[str, Any]:
    sources = [source for source in manifest.get("source_families", []) if isinstance(source, dict)]
    source_rows = [_source_row(source) for source in sources]
    source_ids = {row["source_id"] for row in source_rows}
    required_sources_present = {KONEPS_SOURCE_ID, PEER_TBI_SOURCE_ID} <= source_ids
    p0_provenance_required_count = sum(1 for row in source_rows if row["p0_provenance_required"])
    manual_review_required_count = sum(1 for row in source_rows if row["manual_review_required"])
    raw_redistribution_auto_allowed_after_p0 = False

    p1_gate_rows = [
        {
            "gate_id": "P1_KONEPS_PARSER_COVERAGE",
            "source_id": KONEPS_SOURCE_ID,
            "coverage_status": "planned",
            "required_targets": KONEPS_TARGET_FILE_TYPES,
        },
        {
            "gate_id": "P1_PEER_TBI_BENCHMARK_METRICS",
            "source_id": PEER_TBI_SOURCE_ID,
            "coverage_status": "planned",
            "required_targets": PEER_TBI_BENCHMARK_METRICS,
        },
        {
            "gate_id": "P1_RAW_REDISTRIBUTION_SAFETY",
            "coverage_status": "planned",
            "raw_redistribution_auto_allowed_after_p0": raw_redistribution_auto_allowed_after_p0,
            "safety_flag": "P0_CLOSEOUT_DOES_NOT_GRANT_RAW_REDISTRIBUTION",
        },
    ]

    contract_pass = required_sources_present
    return {
        "schema_version": "real_project_parser_coverage_matrix.v1",
        "run_id": "phase1-real-project-parser-coverage-matrix",
        "source_manifest_schema_version": manifest.get("schema_version"),
        "generated_at": manifest.get("generated_at"),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_REQUIRED_SOURCE_FAMILY_MISSING",
        "summary": {
            "source_family_count": len(source_rows),
            "p0_provenance_required_count": p0_provenance_required_count,
            "manual_review_required_count": manual_review_required_count,
            "koneps_parser_target_count": len(KONEPS_TARGET_FILE_TYPES) if KONEPS_SOURCE_ID in source_ids else 0,
            "peer_tbi_benchmark_metric_target_count": (
                len(PEER_TBI_BENCHMARK_METRICS) if PEER_TBI_SOURCE_ID in source_ids else 0
            ),
            "raw_redistribution_auto_allowed_after_p0": raw_redistribution_auto_allowed_after_p0,
        },
        "source_rows": source_rows,
        "p1_gate_rows": p1_gate_rows,
    }


def write_matrix(manifest_path: Path, out_path: Path) -> dict[str, Any]:
    matrix = build_coverage_matrix(_load_json(manifest_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    matrix = write_matrix(args.manifest, args.out)
    return 0 if matrix["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
