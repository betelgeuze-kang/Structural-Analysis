#!/usr/bin/env python3
"""Build deterministic P1 real-project row provenance seed report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "real_project_row_provenance_report.v1"
RUN_ID = "phase1-real-project-row-provenance-report"
KONEPS_SOURCE_ID = "koneps_turnkey_design_docs"
PEER_TBI_SOURCE_ID = "peer_tbi_tall_buildings"
REQUIRED_SOURCE_IDS = {KONEPS_SOURCE_ID, PEER_TBI_SOURCE_ID}
REQUIRED_ROW_FIELDS = {
    "row_id",
    "source_id",
    "source_label",
    "source_kind",
    "jurisdiction",
    "official_url",
    "p0_upstream_hard_gate",
    "access_policy",
    "artifact_status",
    "checksum_status_or_withheld_reason",
    "file_inventory_status",
    "parser_contract",
    "row_pointer",
    "release_surface_allowed",
    "blocked_reason",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_sources(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [source for source in manifest.get("source_families", []) if isinstance(source, dict)]


def _access_policy(source: dict[str, Any]) -> dict[str, Any]:
    access_policy = source.get("access_policy")
    if isinstance(access_policy, dict):
        return {
            "classification": str(access_policy.get("classification", "") or ""),
            "redistribution_allowed": bool(access_policy.get("redistribution_allowed", False)),
            "requires_manual_review": bool(access_policy.get("requires_manual_review", True)),
            "license_basis": str(access_policy.get("license_basis", "") or ""),
        }
    return {
        "classification": "",
        "redistribution_allowed": False,
        "requires_manual_review": True,
        "license_basis": "",
    }


def _coverage_source_row(coverage_matrix: dict[str, Any], source_id: str) -> dict[str, Any] | None:
    for row in coverage_matrix.get("source_rows", []):
        if isinstance(row, dict) and row.get("source_id") == source_id:
            return row
    return None


def _coverage_gate_row(coverage_matrix: dict[str, Any], gate_id: str) -> dict[str, Any] | None:
    for row in coverage_matrix.get("p1_gate_rows", []):
        if isinstance(row, dict) and row.get("gate_id") == gate_id:
            return row
    return None


def _peer_metric_groups(peer_metric_records: dict[str, Any]) -> list[str]:
    groups = {
        str(record.get("metric_group"))
        for record in peer_metric_records.get("metric_records", [])
        if isinstance(record, dict) and isinstance(record.get("metric_group"), str)
    }
    return sorted(groups)


def _parser_contract(
    source_id: str,
    coverage_matrix: dict[str, Any],
    peer_metric_records: dict[str, Any],
) -> dict[str, Any]:
    if source_id == KONEPS_SOURCE_ID:
        gate = _coverage_gate_row(coverage_matrix, "P1_KONEPS_PARSER_COVERAGE") or {}
        required_targets = [str(target) for target in gate.get("required_targets", []) if isinstance(target, str)]
        return {
            "source_file": "real_project_parser_coverage_matrix.json",
            "gate_id": "P1_KONEPS_PARSER_COVERAGE",
            "coverage_status": str(gate.get("coverage_status", "") or ""),
            "required_targets": required_targets,
            "required_target_count": len(required_targets),
        }

    if source_id == PEER_TBI_SOURCE_ID:
        metric_groups = _peer_metric_groups(peer_metric_records)
        return {
            "source_file": "peer_tbi_benchmark_metric_records.json",
            "gate_id": "P1_PEER_TBI_BENCHMARK_METRICS",
            "coverage_status": "seeded",
            "metric_groups": metric_groups,
            "metric_group_count": len(metric_groups),
        }

    coverage_row = _coverage_source_row(coverage_matrix, source_id) or {}
    return {
        "source_file": "real_project_parser_coverage_matrix.json",
        "gate_id": "",
        "coverage_status": "planned" if coverage_row else "",
        "required_targets": [],
        "required_target_count": 0,
    }


def _row_pointer(source_id: str, manifest_index: int) -> dict[str, str]:
    if source_id == PEER_TBI_SOURCE_ID:
        return {
            "source_file": "peer_tbi_benchmark_metric_records.json",
            "json_path": "$.metric_records[*]",
        }
    return {
        "source_file": "real_project_corpus_seed_manifest.json",
        "json_path": f"$.source_families[{manifest_index}]",
    }


def _artifact_fields(source_id: str) -> dict[str, str]:
    if source_id == PEER_TBI_SOURCE_ID:
        return {
            "artifact_status": "citation_metric_records_seeded_no_raw_models",
            "checksum_status_or_withheld_reason": "raw_model_files_not_redistributed",
            "file_inventory_status": "peer_tbi_benchmark_metric_records.json",
            "blocked_reason": "PEER TBI seed exposes citation/metric provenance only; raw model redistribution remains blocked pending explicit review.",
        }
    if source_id == KONEPS_SOURCE_ID:
        return {
            "artifact_status": "metadata_only_candidate_pending_artifact_review",
            "checksum_status_or_withheld_reason": "withheld_until_artifact_level_review",
            "file_inventory_status": "not_collected_metadata_seed_only",
            "blocked_reason": "KONEPS attachments require artifact-level access, security, copyright, checksum, and redistribution review before release.",
        }
    return {
        "artifact_status": "metadata_only_candidate_pending_artifact_review",
        "checksum_status_or_withheld_reason": "withheld_until_artifact_level_review",
        "file_inventory_status": "not_collected_metadata_seed_only",
        "blocked_reason": "Raw redistribution remains blocked pending explicit review.",
    }


def _source_row(
    source: dict[str, Any],
    manifest_index: int,
    coverage_matrix: dict[str, Any],
    peer_metric_records: dict[str, Any],
) -> dict[str, Any]:
    source_id = str(source.get("source_id", "") or "")
    access_policy = _access_policy(source)
    artifact_fields = _artifact_fields(source_id)
    return {
        "row_id": f"real-project-row-provenance:{source_id}",
        "source_id": source_id,
        "source_label": str(source.get("source_label", "") or ""),
        "source_kind": str(source.get("source_kind", "") or ""),
        "jurisdiction": str(source.get("jurisdiction", "") or ""),
        "official_url": str(source.get("official_entrypoint_url", "") or ""),
        "p0_upstream_hard_gate": True,
        "access_policy": access_policy,
        "artifact_status": artifact_fields["artifact_status"],
        "checksum_status_or_withheld_reason": artifact_fields["checksum_status_or_withheld_reason"],
        "file_inventory_status": artifact_fields["file_inventory_status"],
        "parser_contract": _parser_contract(source_id, coverage_matrix, peer_metric_records),
        "row_pointer": _row_pointer(source_id, manifest_index),
        "release_surface_allowed": False,
        "blocked_reason": artifact_fields["blocked_reason"],
    }


def _all_rows_have_required_fields(rows: list[dict[str, Any]]) -> bool:
    return all(REQUIRED_ROW_FIELDS <= set(row) for row in rows)


def _raw_redistribution_blocked(rows: list[dict[str, Any]]) -> bool:
    return all(row.get("release_surface_allowed") is False for row in rows)


def _reason_code(contract_pass: bool, required_source_families_present: bool, raw_blocked: bool) -> str:
    if contract_pass:
        return "PASS"
    if not required_source_families_present:
        return "ERR_REQUIRED_SOURCE_FAMILY_MISSING"
    if not raw_blocked:
        return "ERR_RAW_REDISTRIBUTION_NOT_BLOCKED"
    return "ERR_ROW_PROVENANCE_CONTRACT_INCOMPLETE"


def build_report(
    manifest: dict[str, Any],
    coverage_matrix: dict[str, Any],
    peer_metric_records: dict[str, Any],
) -> dict[str, Any]:
    sources = _manifest_sources(manifest)
    indexed_sources = [(idx, source) for idx, source in enumerate(sources)]
    rows = [
        _source_row(source, idx, coverage_matrix, peer_metric_records)
        for idx, source in indexed_sources
        if source.get("source_id") in REQUIRED_SOURCE_IDS
    ]
    source_ids = {row["source_id"] for row in rows}
    required_source_families_present = REQUIRED_SOURCE_IDS <= source_ids
    p0_hard_gate_represented = all(row["p0_upstream_hard_gate"] is True for row in rows)
    all_rows_have_required_fields = _all_rows_have_required_fields(rows)
    row_provenance_coverage = 1.0 if rows and all_rows_have_required_fields else 0.0
    raw_redistribution_default_blocked = _raw_redistribution_blocked(rows)
    peer_metric_group_count = len(_peer_metric_groups(peer_metric_records))
    peer_row_references_metric_records = any(
        row["source_id"] == PEER_TBI_SOURCE_ID
        and row["row_pointer"]["source_file"] == "peer_tbi_benchmark_metric_records.json"
        and row["parser_contract"].get("metric_group_count") == 5
        for row in rows
    )
    contract_pass = (
        required_source_families_present
        and p0_hard_gate_represented
        and all_rows_have_required_fields
        and raw_redistribution_default_blocked
        and peer_row_references_metric_records
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "source_manifest_schema_version": manifest.get("schema_version"),
        "coverage_matrix_schema_version": coverage_matrix.get("schema_version"),
        "peer_metric_records_schema_version": peer_metric_records.get("schema_version"),
        "generated_at": manifest.get("generated_at"),
        "contract_pass": contract_pass,
        "reason_code": _reason_code(
            contract_pass,
            required_source_families_present,
            raw_redistribution_default_blocked,
        ),
        "p0_upstream_hard_gate": p0_hard_gate_represented,
        "row_provenance_coverage": row_provenance_coverage,
        "raw_redistribution_default_blocked": raw_redistribution_default_blocked,
        "summary": {
            "required_source_families": sorted(REQUIRED_SOURCE_IDS),
            "required_source_families_present": required_source_families_present,
            "p0_hard_gate_represented": p0_hard_gate_represented,
            "row_count": len(rows),
            "release_surface_allowed_count": sum(1 for row in rows if row["release_surface_allowed"]),
            "all_rows_have_required_fields": all_rows_have_required_fields,
            "row_provenance_coverage": row_provenance_coverage,
            "peer_tbi_metric_group_count": peer_metric_group_count,
            "raw_redistribution_default_blocked": raw_redistribution_default_blocked,
        },
        "source_provenance_rows": rows,
        "promoted_row_provenance_rows": [],
    }


def write_report(
    manifest_path: Path,
    coverage_matrix_path: Path,
    peer_metric_records_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    payload = build_report(
        _load_json(manifest_path),
        _load_json(coverage_matrix_path),
        _load_json(peer_metric_records_path),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage-matrix", type=Path, required=True)
    parser.add_argument("--peer-metric-records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = write_report(args.manifest, args.coverage_matrix, args.peer_metric_records, args.out)
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
