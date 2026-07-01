#!/usr/bin/env python3
"""Materialize a Vina/GNINA comparison adapter from operator intake rows."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_ADAPTER_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_comparison_adapter.json"

SCHEMA_VERSION = "public-benchmark-vina-gnina-comparison-materialization.v1"
ADAPTER_SCHEMA_VERSION = "public-benchmark-vina-gnina-comparison-adapter.v1"
DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM = 2.0
SUPPORTED_ENGINES = ("vina", "gnina")
SUPPORTED_BENCHMARK_SPLITS = (
    "CASF-core",
    "PDBBind-core",
    "PDBBind-refined",
    "PDBBind-general",
)
REQUIRED_CASE_FIELDS = (
    "case_id",
    "source_family",
    "benchmark_split",
    "complex_id",
    "reference_pose_id",
    "engine_runs",
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
)
REQUIRED_ENGINE_RUN_FIELDS = (
    "engine_id",
    "docking_run_id",
    "predicted_ligand_path_or_pose_ref",
    "symmetry_aware_rmsd_angstrom",
    "pose_success",
    "score",
    "score_direction",
)
SOURCE_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
PLACEHOLDER_SOURCE_TEXT_MARKERS = (
    "<operator",
    "dry-run",
    "dummy",
    "example.invalid",
    "example://",
    "fake",
    "fixture",
    "mock",
    "operator_supplied",
    "placeholder",
    "synthetic",
    "test-accession",
    "todo",
    "unit-test",
)
PLACEHOLDER_PROVENANCE_PREFIXES = (
    "operator://",
    "local-evidence://",
    "local://",
    "fixture://",
    "mock://",
    "synthetic://",
    "placeholder://",
    "test://",
    "unit-test://",
    "file://",
)
ROW_INTEGRITY_POLICY = {
    "required_unique_row_keys": {
        "cases": ["case_id"],
        "case_engine_runs": ["engine_id", "docking_run_id"],
    },
    "purpose": (
        "Duplicate comparison cases or engine runs cannot be used to inflate Vina/GNINA "
        "case coverage, engine coverage, or pose-success summaries."
    ),
}
SCORE_DIRECTION_POLICY = {
    "required": True,
    "accepted_values": ["higher_is_better", "lower_is_better"],
    "accepted_aliases": {
        "higher_is_better": ["higher", "higher_is_better", "descending"],
        "lower_is_better": ["lower", "lower_is_better", "ascending"],
    },
    "blank_values": "rejected; no implicit default is applied",
}
BOOLEAN_VALUE_POLICY = {
    "pose_success": "must be a JSON boolean true/false; strings and numbers are rejected",
}
NUMERIC_VALUE_POLICY = {
    "symmetry_aware_rmsd_angstrom": (
        "must parse to a finite non-negative float; NaN, Infinity, and negative "
        "RMSD values are rejected"
    ),
    "score": "must parse to a finite float; NaN and Infinity are rejected",
    "pose_success_rmsd_threshold_angstrom": (
        "must parse to a finite positive float; NaN, Infinity, zero, and negative "
        "thresholds are rejected"
    ),
}
POSE_SUCCESS_POLICY = {
    "threshold_default_angstrom": DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM,
    "consistency_rule": (
        "pose_success must equal symmetry_aware_rmsd_angstrom <= "
        "pose_success_rmsd_threshold_angstrom"
    ),
}
ENGINE_PAIR_POLICY = {
    "per_case_required_engines": list(SUPPORTED_ENGINES),
    "duplicate_engine_ids_rejected": True,
    "duplicate_docking_run_ids_rejected": True,
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _is_sha256_ref(value: str) -> bool:
    return bool(SOURCE_CHECKSUM_PATTERN.fullmatch(value))


def _contains_placeholder_marker(value: Any) -> bool:
    lowered = _string(value).lower()
    return any(marker in lowered for marker in PLACEHOLDER_SOURCE_TEXT_MARKERS)


def _has_placeholder_provenance_prefix(value: Any) -> bool:
    lowered = _string(value).lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _is_repeated_placeholder_checksum(value: str) -> bool:
    if not _is_sha256_ref(value):
        return False
    digest = value.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def _engine_id(value: Any) -> str:
    return _string(value).lower().replace("_", "-")


def _direction(value: Any) -> str:
    token = _string(value).lower()
    if token in {"higher", "higher_is_better", "descending"}:
        return "higher_is_better"
    if token in {"lower", "lower_is_better", "ascending"}:
        return "lower_is_better"
    return token


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _string(row.get(key))
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _case_key(row: dict[str, Any], index: int) -> str:
    return _string(row.get("case_id")) or f"case_{index + 1}"


def _normalize_engine_run(
    row: dict[str, Any],
    *,
    case_key: str,
    index: int,
) -> tuple[dict[str, Any], list[str], list[str]]:
    blockers: list[str] = []
    root_cause_tags: list[str] = []
    run_key = f"{case_key}:engine_run_{index}"
    for field in REQUIRED_ENGINE_RUN_FIELDS:
        if field not in row:
            blockers.append(f"{run_key}:{field}_missing")
            root_cause_tags.append("operator_values_required")

    engine_id = _engine_id(row.get("engine_id"))
    docking_run_id = _string(row.get("docking_run_id"))
    pose_ref = _string(row.get("predicted_ligand_path_or_pose_ref"))
    rmsd = _number(row.get("symmetry_aware_rmsd_angstrom"))
    pose_success = _boolean(row.get("pose_success"))
    score = _number(row.get("score"))
    score_direction = _direction(row.get("score_direction"))
    threshold = _number(
        row.get(
            "pose_success_rmsd_threshold_angstrom",
            DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM,
        )
    )

    if "engine_id" in row and engine_id not in SUPPORTED_ENGINES:
        blockers.append(f"{run_key}:engine_id_unsupported")
        root_cause_tags.append("unsupported_engine")
    if "docking_run_id" in row and not docking_run_id:
        blockers.append(f"{run_key}:docking_run_id_blank")
        root_cause_tags.append("operator_values_required")
    if "predicted_ligand_path_or_pose_ref" in row and not pose_ref:
        blockers.append(f"{run_key}:predicted_ligand_path_or_pose_ref_blank")
        root_cause_tags.append("operator_values_required")
    elif (
        "predicted_ligand_path_or_pose_ref" in row
        and pose_ref
        and (
            _has_placeholder_provenance_prefix(pose_ref)
            or _contains_placeholder_marker(pose_ref)
        )
    ):
        blockers.append(f"{run_key}:predicted_ligand_path_or_pose_ref_placeholder")
        root_cause_tags.append("operator_receipts_required")
    if "symmetry_aware_rmsd_angstrom" in row and (rmsd is None or rmsd < 0.0):
        blockers.append(f"{run_key}:symmetry_aware_rmsd_angstrom_invalid")
        root_cause_tags.append("operator_values_required")
    if "pose_success" in row and pose_success is None:
        blockers.append(f"{run_key}:pose_success_invalid")
        root_cause_tags.append("operator_values_required")
    if "score" in row and score is None:
        blockers.append(f"{run_key}:score_invalid")
        root_cause_tags.append("operator_values_required")
    if "score_direction" in row and score_direction not in {
        "higher_is_better",
        "lower_is_better",
    }:
        blockers.append(f"{run_key}:score_direction_invalid")
        root_cause_tags.append("operator_values_required")
    if threshold is None or threshold <= 0.0:
        blockers.append(f"{run_key}:pose_success_rmsd_threshold_angstrom_invalid")
        root_cause_tags.append("operator_values_required")
    elif rmsd is not None and pose_success is not None:
        expected_pose_success = bool(rmsd <= threshold)
        if pose_success is not expected_pose_success:
            blockers.append(
                f"{run_key}:pose_success_inconsistent_with_rmsd_threshold"
            )
            root_cause_tags.append("pose_success_rmsd_inconsistent")

    return (
        {
            "engine_id": engine_id,
            "docking_run_id": docking_run_id,
            "predicted_ligand_path_or_pose_ref": pose_ref,
            "symmetry_aware_rmsd_angstrom": rmsd,
            "pose_success": pose_success,
            "score": score,
            "score_direction": score_direction,
            "pose_success_rmsd_threshold_angstrom": threshold,
            "status": "pass" if not blockers else "blocked",
            "contract_pass": not blockers,
            "blockers": blockers,
        },
        blockers,
        root_cause_tags,
    )


def _normalize_case(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    case_key = _case_key(row, index)
    blockers: list[str] = []
    root_cause_tags: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        if field not in row:
            blockers.append(f"{case_key}:{field}_missing")
            root_cause_tags.append("operator_values_required")

    case_id = _string(row.get("case_id"))
    source_family = _string(row.get("source_family"))
    benchmark_split = _string(row.get("benchmark_split"))
    complex_id = _string(row.get("complex_id"))
    reference_pose_id = _string(row.get("reference_pose_id"))
    source_license = _string(row.get("source_license_or_accession"))
    source_checksum = _string(row.get("source_checksum"))
    provenance_ref = _string(row.get("provenance_ref"))

    for field, value in {
        "case_id": case_id,
        "source_family": source_family,
        "benchmark_split": benchmark_split,
        "complex_id": complex_id,
        "reference_pose_id": reference_pose_id,
        "source_license_or_accession": source_license,
        "source_checksum": source_checksum,
        "provenance_ref": provenance_ref,
    }.items():
        if field in row and not value:
            blockers.append(f"{case_key}:{field}_blank")
            root_cause_tags.append("operator_values_required")
    if "source_checksum" in row and source_checksum and not _is_sha256_ref(source_checksum):
        blockers.append(f"{case_key}:source_checksum_invalid")
        root_cause_tags.append("operator_receipts_required")
    elif (
        "source_checksum" in row
        and source_checksum
        and _is_repeated_placeholder_checksum(source_checksum)
    ):
        blockers.append(f"{case_key}:source_checksum_placeholder_digest")
        root_cause_tags.append("operator_receipts_required")
    if (
        "source_license_or_accession" in row
        and source_license
        and _contains_placeholder_marker(source_license)
    ):
        blockers.append(f"{case_key}:source_license_or_accession_placeholder")
        root_cause_tags.append("operator_receipts_required")
    if (
        "provenance_ref" in row
        and provenance_ref
        and (
            _has_placeholder_provenance_prefix(provenance_ref)
            or _contains_placeholder_marker(provenance_ref)
        )
    ):
        blockers.append(f"{case_key}:provenance_ref_placeholder")
        root_cause_tags.append("operator_receipts_required")
    if (
        "benchmark_split" in row
        and benchmark_split
        and benchmark_split not in SUPPORTED_BENCHMARK_SPLITS
    ):
        blockers.append(f"{case_key}:unsupported_benchmark_split")
        root_cause_tags.append("operator_values_required")

    raw_runs = _as_list(row.get("engine_runs"))
    if not raw_runs:
        blockers.append(f"{case_key}:engine_runs_missing")
        root_cause_tags.append("operator_values_required")

    engine_runs: list[dict[str, Any]] = []
    seen_engine_ids: set[str] = set()
    seen_docking_run_ids: set[str] = set()
    for run_index, raw_run in enumerate(raw_runs):
        if not isinstance(raw_run, dict):
            blockers.append(f"{case_key}:engine_run_{run_index}:invalid_object")
            root_cause_tags.append("operator_values_required")
            continue
        engine_run, run_blockers, run_root_cause_tags = _normalize_engine_run(
            raw_run,
            case_key=case_key,
            index=run_index,
        )
        engine_runs.append(engine_run)
        blockers.extend(run_blockers)
        root_cause_tags.extend(run_root_cause_tags)
        engine_id = _string(engine_run.get("engine_id"))
        if engine_id:
            if engine_id in seen_engine_ids:
                blockers.append(
                    f"{case_key}:engine_run_{run_index}:"
                    f"engine_id_duplicate:{engine_id}"
                )
                root_cause_tags.append("row_integrity_required")
            else:
                seen_engine_ids.add(engine_id)
        docking_run_id = _string(engine_run.get("docking_run_id"))
        if docking_run_id:
            if docking_run_id in seen_docking_run_ids:
                blockers.append(
                    f"{case_key}:engine_run_{run_index}:"
                    f"docking_run_id_duplicate:{docking_run_id}"
                )
                root_cause_tags.append("row_integrity_required")
            else:
                seen_docking_run_ids.add(docking_run_id)

    present_engines = sorted(
        {
            str(run.get("engine_id") or "")
            for run in engine_runs
            if run.get("engine_id") in SUPPORTED_ENGINES
        }
    )
    missing_engines = [
        engine for engine in SUPPORTED_ENGINES if engine not in present_engines
    ]
    for engine in missing_engines:
        blockers.append(f"{case_key}:{engine}_engine_run_missing")
        root_cause_tags.append("vina_gnina_pair_required")

    return {
        "case_id": case_id,
        "source_family": source_family,
        "benchmark_split": benchmark_split,
        "complex_id": complex_id,
        "reference_pose_id": reference_pose_id,
        "engine_runs": engine_runs,
        "present_engines": present_engines,
        "source_license_or_accession": source_license,
        "source_checksum": source_checksum,
        "provenance_ref": provenance_ref,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "root_cause_tags": list(dict.fromkeys(root_cause_tags)),
        "blockers": blockers,
    }


def _engine_summaries(case_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for engine in SUPPORTED_ENGINES:
        runs = [
            run
            for row in case_rows
            for run in _as_list(row.get("engine_runs"))
            if run.get("engine_id") == engine
        ]
        success_values = [
            bool(run["pose_success"])
            for run in runs
            if run.get("pose_success") is not None
        ]
        rmsd_values = [
            float(run["symmetry_aware_rmsd_angstrom"])
            for run in runs
            if run.get("symmetry_aware_rmsd_angstrom") is not None
        ]
        summaries.append(
            {
                "engine_id": engine,
                "run_count": len(runs),
                "pose_success_count": sum(1 for value in success_values if value),
                "pose_success_rate": (
                    sum(1 for value in success_values if value) / len(success_values)
                    if success_values
                    else None
                ),
                "symmetry_aware_rmsd_median_angstrom": _median(rmsd_values),
            }
        )
    return summaries


def materialize_vina_gnina_comparison_adapter(
    intake_payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
) -> dict[str, Any]:
    raw_cases = [
        row for row in _as_list(intake_payload.get("cases")) if isinstance(row, dict)
    ]
    case_rows: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, row in enumerate(raw_cases):
        normalized = _normalize_case(row, index=index)
        case_id = _string(normalized.get("case_id"))
        if case_id:
            if case_id in seen_case_ids:
                normalized["blockers"].append(f"{case_id}:case_id_duplicate")
                normalized["root_cause_tags"] = list(
                    dict.fromkeys(
                        [*normalized["root_cause_tags"], "row_integrity_required"]
                    )
                )
                normalized["status"] = "blocked"
                normalized["contract_pass"] = False
            else:
                seen_case_ids.add(case_id)
        case_rows.append(normalized)
    blockers = [blocker for row in case_rows for blocker in row["blockers"]]
    root_cause_tags = list(
        dict.fromkeys(tag for row in case_rows for tag in row["root_cause_tags"])
    )
    if not case_rows:
        blockers = [
            "vina_gnina_comparison_cases_missing",
            "vina_gnina_engine_runs_missing",
            "vina_gnina_external_receipts_missing",
        ]
        root_cause_tags = ["operator_vina_gnina_rows_required"]

    ready = bool(case_rows and not blockers)
    first_blocked_target = next(
        (
            row["case_id"] or f"case_{index + 1}"
            for index, row in enumerate(case_rows)
            if row["blockers"]
        ),
        "vina_gnina_operator_intake" if blockers else "",
    )
    engine_summaries = _engine_summaries(case_rows)
    benchmark_split_counts = _counts_by_key(case_rows, "benchmark_split")
    input_paths = [
        Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py")
    ]
    if intake_path is not None:
        input_paths.append(intake_path)

    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_comparison_adapter_materialized_from_operator_intake",
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "operator_evidence_required",
        "contract_pass": ready,
        "public_benchmark_engine_comparison_ready": ready,
        "real_comparison_case_count": len(case_rows),
        "case_rows": case_rows,
        "engine_summaries": engine_summaries,
        "benchmark_split_counts": benchmark_split_counts,
        "summary": {
            "case_count": len(case_rows),
            "ready_case_count": sum(1 for row in case_rows if row["contract_pass"]),
            "engine_count": len(SUPPORTED_ENGINES),
            "supported_engines": list(SUPPORTED_ENGINES),
            "supported_benchmark_splits": list(SUPPORTED_BENCHMARK_SPLITS),
            "benchmark_split_counts": benchmark_split_counts,
            "blocker_count": len(blockers),
        },
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "required_engine_run_fields": list(REQUIRED_ENGINE_RUN_FIELDS),
        "row_integrity_policy": ROW_INTEGRITY_POLICY,
        "score_direction_policy": SCORE_DIRECTION_POLICY,
        "boolean_value_policy": BOOLEAN_VALUE_POLICY,
        "numeric_value_policy": NUMERIC_VALUE_POLICY,
        "pose_success_policy": POSE_SUCCESS_POLICY,
        "engine_pair_policy": ENGINE_PAIR_POLICY,
        "supported_engines": list(SUPPORTED_ENGINES),
        "supported_benchmark_splits": list(SUPPORTED_BENCHMARK_SPLITS),
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": root_cause_tags,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "operator_case_count": len(raw_cases),
            "materialized_case_count": len(case_rows),
            "ready_case_count": sum(1 for row in case_rows if row["contract_pass"]),
            "benchmark_split_counts": benchmark_split_counts,
            "blocker_count": len(blockers),
            "public_benchmark_engine_comparison_ready": ready,
        },
        "summary_line": (
            "Public benchmark Vina/GNINA comparison adapter: PASS | "
            f"cases={len(case_rows)}"
            if ready
            else (
                "Public benchmark Vina/GNINA comparison adapter: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'} | "
                f"blockers={len(blockers)}"
            )
        ),
        "claim_boundary": (
            "This adapter consumes operator-attached Vina/GNINA comparison rows for "
            "already-selected public benchmark cases. It does not run Vina or GNINA, "
            "download benchmark data, validate ligand chemistry, or close Tier beta by itself."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--out-adapter", type=Path, default=DEFAULT_ADAPTER_OUT)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    intake_payload = json.loads(args.intake.read_text(encoding="utf-8"))
    adapter = materialize_vina_gnina_comparison_adapter(
        intake_payload,
        repo_root=args.repo_root,
        intake_path=args.intake,
    )
    args.out_adapter.parent.mkdir(parents=True, exist_ok=True)
    args.out_adapter.write_text(_json_text(adapter), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(adapter["materialization_report"]),
            encoding="utf-8",
        )
    print(
        "public-benchmark-vina-gnina-comparison-materialization: "
        f"{adapter['status']} | cases={adapter['real_comparison_case_count']} | "
        f"blockers={len(adapter['blockers'])}"
    )
    return 1 if args.fail_blocked and not adapter["public_benchmark_engine_comparison_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
