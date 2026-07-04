#!/usr/bin/env python3
"""Preflight the Vina/GNINA adapter rows template without promoting it."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM,
    ENGINE_RUN_CHECKSUM_FIELDS,
    ENGINE_RUN_PROVENANCE_FIELDS,
    ENGINE_RUN_RECEIPT_FIELDS,
    PLACEHOLDER_PROVENANCE_PREFIXES,
    PLACEHOLDER_SOURCE_TEXT_MARKERS,
    REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS,
    SCORE_DIRECTION_POLICY,
    SOURCE_CHECKSUM_PATTERN,
    SUPPORTED_ENGINES,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RUNTIME_READINESS = PRODUCTIZATION / "public_benchmark_vina_gnina_runtime_readiness.json"
DEFAULT_TEMPLATE = PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template.csv"
DEFAULT_EXPECTED_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_ROWS_FROM_TEMPLATE_REPORT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_from_template_report.json"
)
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template_preflight.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "public-benchmark-vina-gnina-rows-template-preflight.v1"
FLAT_REQUIRED_FIELDS = tuple(
    field for field in REQUIRED_CASE_FIELDS if field != "engine_runs"
) + tuple(REQUIRED_ENGINE_RUN_FIELDS)
LOCAL_REF_FIELDS = (
    "predicted_ligand_path_or_pose_ref",
    "engine_run_provenance_ref",
)
ROLE_PLANS = (
    {
        "role_id": "casf_pdbbind_case_source_receipt",
        "required_fields": (
            "case_id",
            "source_family",
            "benchmark_split",
            "complex_id",
            "reference_pose_id",
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
        ),
        "operator_action": "attach_casf_pdbbind_case_source_receipt",
        "closes_phase2_criteria": ("vina_gnina_comparison_ready",),
    },
    {
        "role_id": "engine_run_artifact_receipt",
        "required_fields": (
            "engine_id",
            "docking_run_id",
            "predicted_ligand_path_or_pose_ref",
            "predicted_ligand_checksum",
            "engine_run_provenance_ref",
        ),
        "operator_action": "attach_vina_gnina_engine_run_artifact_receipt",
        "closes_phase2_criteria": ("vina_gnina_comparison_ready",),
    },
    {
        "role_id": "engine_config_version_receipt",
        "required_fields": (
            "engine_id",
            "docking_run_id",
            "engine_version",
            "engine_config_checksum",
        ),
        "operator_action": "attach_vina_gnina_engine_config_version_receipt",
        "closes_phase2_criteria": ("vina_gnina_comparison_ready",),
    },
    {
        "role_id": "comparison_metric_receipt",
        "required_fields": (
            "symmetry_aware_rmsd_angstrom",
            "pose_success",
            "score",
            "score_direction",
        ),
        "operator_action": "attach_vina_gnina_comparison_metric_receipt",
        "closes_phase2_criteria": ("vina_gnina_comparison_ready",),
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(repo_root: Path, path: Path) -> tuple[list[str], list[dict[str, str]]]:
    resolved = _resolve(repo_root, path)
    if not resolved.is_file():
        return [], []
    with resolved.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [
            {
                str(key).strip(): str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in reader
        ]
    return [str(field) for field in reader.fieldnames or []], rows


def _expected_engine_run_slots(runtime_readiness: dict[str, Any]) -> list[dict[str, Any]]:
    slots = []
    raw_slots = runtime_readiness.get("engine_run_slots")
    if isinstance(raw_slots, list):
        for row in raw_slots:
            if not isinstance(row, dict):
                continue
            case_id = str(row.get("case_id") or "")
            engine_id = str(row.get("engine_id") or "")
            docking_run_id = str(row.get("docking_run_id") or "")
            if case_id and engine_id and docking_run_id:
                slots.append(
                    {
                        "slot_id": f"{case_id}_{engine_id}_{docking_run_id}",
                        "case_id": case_id,
                        "engine_id": engine_id,
                        "docking_run_id": docking_run_id,
                    }
                )
    return slots


def _slot_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("case_id") or ""),
        str(row.get("engine_id") or ""),
        str(row.get("docking_run_id") or ""),
    )


def _number(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _boolean(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _contains_placeholder_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_SOURCE_TEXT_MARKERS)


def _has_placeholder_provenance_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _is_repeated_placeholder_checksum(value: str) -> bool:
    if not SOURCE_CHECKSUM_PATTERN.fullmatch(value):
        return False
    digest = value.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def _checksum_status(value: str) -> dict[str, Any]:
    if not value:
        return {"present": False, "valid_sha256": False, "blocker": "checksum_missing"}
    if not SOURCE_CHECKSUM_PATTERN.fullmatch(value):
        return {"present": True, "valid_sha256": False, "blocker": "checksum_invalid"}
    if _is_repeated_placeholder_checksum(value):
        return {
            "present": True,
            "valid_sha256": False,
            "blocker": "checksum_placeholder_digest",
        }
    return {"present": True, "valid_sha256": True, "blocker": ""}


def _local_ref_status(repo_root: Path, value: str) -> dict[str, Any]:
    if not value:
        return {
            "ref": "",
            "present": False,
            "local_path_exists": False,
            "status": "missing",
            "blocker": "ref_missing",
        }
    if value.startswith(("http://", "https://")):
        return {
            "ref": value,
            "present": True,
            "local_path_exists": False,
            "status": "external_ref",
            "blocker": "",
        }
    if _has_placeholder_provenance_prefix(value) or _contains_placeholder_marker(value):
        return {
            "ref": value,
            "present": True,
            "local_path_exists": False,
            "status": "placeholder",
            "blocker": "ref_placeholder",
        }
    resolved = _resolve(repo_root, Path(value))
    local_path_exists = resolved.exists()
    return {
        "ref": value,
        "present": True,
        "local_path_exists": local_path_exists,
        "status": "ready" if local_path_exists else "local_ref_not_found",
        "blocker": "" if local_path_exists else "local_ref_not_found",
    }


def _score_direction_status(value: str) -> dict[str, Any]:
    accepted = {
        str(item)
        for item in SCORE_DIRECTION_POLICY.get("accepted_values", [])
        if str(item)
    }
    aliases = {
        alias
        for values in SCORE_DIRECTION_POLICY.get("accepted_aliases", {}).values()
        for alias in values
    }
    if not value:
        return {"present": False, "valid": False, "blocker": "score_direction_missing"}
    lowered = value.lower()
    valid = lowered in accepted or lowered in aliases
    return {
        "present": True,
        "valid": valid,
        "blocker": "" if valid else "score_direction_invalid",
    }


def _role_plan_rows(row_preflight: dict[str, Any]) -> list[dict[str, Any]]:
    missing_sets = [
        set(row_preflight["missing_required_fields"]),
        set(row_preflight["missing_engine_run_receipt_fields"]),
        set(row_preflight["missing_numeric_fields"]),
    ]
    invalid_sets = [
        set(row_preflight["invalid_checksum_fields"]),
        set(row_preflight["missing_local_ref_fields"]),
        set(row_preflight["invalid_numeric_fields"]),
    ]
    if (
        row_preflight["pose_success_status"]["present"]
        and not row_preflight["pose_success_status"]["valid"]
    ):
        invalid_sets.append({"pose_success"})
    if row_preflight["pose_success_consistency_blocker"]:
        invalid_sets.append({"pose_success"})
    if (
        row_preflight["score_direction_status"]["present"]
        and not row_preflight["score_direction_status"]["valid"]
    ):
        invalid_sets.append({"score_direction"})
    if row_preflight["engine_blocker"]:
        invalid_sets.append({"engine_id"})

    role_rows = []
    for role in ROLE_PLANS:
        required_fields = [str(field) for field in role["required_fields"]]
        missing_fields = sorted(
            {
                field
                for field in required_fields
                if any(field in missing_set for missing_set in missing_sets)
            }
        )
        invalid_fields = sorted(
            {
                field
                for field in required_fields
                if any(field in invalid_set for invalid_set in invalid_sets)
            }
        )
        blockers = []
        if missing_fields:
            blockers.append("required_role_fields_missing")
        if invalid_fields:
            blockers.append("required_role_fields_invalid")
        role_rows.append(
            {
                "slot_id": row_preflight["slot_id"],
                "case_id": row_preflight["case_id"],
                "engine_id": row_preflight["engine_id"],
                "docking_run_id": row_preflight["docking_run_id"],
                "role_id": str(role["role_id"]),
                "required_fields": required_fields,
                "missing_fields": missing_fields,
                "invalid_fields": invalid_fields,
                "closes_phase2_criteria": list(role["closes_phase2_criteria"]),
                "operator_action": str(role["operator_action"]),
                "status": "ready" if not blockers else "operator_completion_required",
                "blockers": blockers,
            }
        )
    return role_rows


def _row_preflight(repo_root: Path, row: dict[str, str]) -> dict[str, Any]:
    missing_required_fields = [
        field for field in FLAT_REQUIRED_FIELDS if not str(row.get(field) or "")
    ]
    missing_engine_run_receipt_fields = [
        field for field in ENGINE_RUN_RECEIPT_FIELDS if not str(row.get(field) or "")
    ]
    checksum_statuses = {
        field: _checksum_status(str(row.get(field) or ""))
        for field in (
            "source_checksum",
            *ENGINE_RUN_CHECKSUM_FIELDS,
        )
    }
    invalid_checksum_fields = [
        field
        for field, status in checksum_statuses.items()
        if status["present"] and str(status["blocker"] or "")
    ]
    local_ref_statuses = {
        field: _local_ref_status(repo_root, str(row.get(field) or ""))
        for field in LOCAL_REF_FIELDS
    }
    missing_local_ref_fields = [
        field
        for field, status in local_ref_statuses.items()
        if str(status.get("blocker") or "")
    ]
    missing_numeric_fields = [
        field
        for field in ("symmetry_aware_rmsd_angstrom", "score")
        if not str(row.get(field) or "")
    ]
    invalid_numeric_fields = [
        field
        for field in ("symmetry_aware_rmsd_angstrom", "score")
        if str(row.get(field) or "") and _number(str(row.get(field) or "")) is None
    ]
    pose_success_value = str(row.get("pose_success") or "")
    pose_success_status = {
        "present": bool(pose_success_value),
        "valid": bool(pose_success_value) and _boolean(pose_success_value) is not None,
        "blocker": (
            ""
            if pose_success_value and _boolean(pose_success_value) is not None
            else "pose_success_missing_or_invalid"
        ),
    }
    score_direction_status = _score_direction_status(
        str(row.get("score_direction") or "")
    )
    rmsd = _number(str(row.get("symmetry_aware_rmsd_angstrom") or ""))
    pose_success = _boolean(pose_success_value)
    pose_success_consistency_blocker = ""
    if rmsd is not None and pose_success is not None:
        expected = bool(rmsd <= DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM)
        if pose_success is not expected:
            pose_success_consistency_blocker = (
                "pose_success_inconsistent_with_rmsd_threshold"
            )
    engine_id = str(row.get("engine_id") or "").lower()
    engine_blocker = ""
    if engine_id and engine_id not in SUPPORTED_ENGINES:
        engine_blocker = "engine_id_unsupported"
    blockers = []
    if missing_required_fields:
        blockers.append("adapter_required_fields_missing")
    if missing_engine_run_receipt_fields:
        blockers.append("adapter_engine_run_receipts_missing")
    if invalid_checksum_fields:
        blockers.append("adapter_checksum_fields_invalid")
    if missing_local_ref_fields:
        blockers.append("adapter_local_refs_missing")
    if missing_numeric_fields:
        blockers.append("adapter_numeric_values_missing")
    if invalid_numeric_fields:
        blockers.append("adapter_numeric_values_invalid")
    if not pose_success_status["valid"]:
        blockers.append("adapter_pose_success_missing_or_invalid")
    if not score_direction_status["valid"]:
        blockers.append("adapter_score_direction_invalid")
    if pose_success_consistency_blocker:
        blockers.append("adapter_pose_success_inconsistent_with_rmsd")
    if engine_blocker:
        blockers.append(engine_blocker)
    row_preflight = {
        "slot_id": "_".join(_slot_key(row)),
        "case_id": str(row.get("case_id") or ""),
        "engine_id": engine_id,
        "docking_run_id": str(row.get("docking_run_id") or ""),
        "status": "operator_completion_required" if blockers else "ready",
        "missing_required_fields": missing_required_fields,
        "missing_engine_run_receipt_fields": missing_engine_run_receipt_fields,
        "invalid_checksum_fields": invalid_checksum_fields,
        "missing_local_ref_fields": missing_local_ref_fields,
        "missing_numeric_fields": missing_numeric_fields,
        "invalid_numeric_fields": invalid_numeric_fields,
        "pose_success_status": pose_success_status,
        "score_direction_status": score_direction_status,
        "pose_success_consistency_blocker": pose_success_consistency_blocker,
        "engine_blocker": engine_blocker,
        "checksum_statuses": checksum_statuses,
        "local_ref_statuses": local_ref_statuses,
        "blockers": blockers,
    }
    row_preflight["role_plan_rows"] = _role_plan_rows(row_preflight)
    return row_preflight


def build_public_benchmark_vina_gnina_rows_template_preflight(
    *,
    repo_root: Path = ROOT,
    runtime_readiness: Path = DEFAULT_RUNTIME_READINESS,
    template: Path = DEFAULT_TEMPLATE,
    expected_rows: Path = DEFAULT_EXPECTED_ROWS,
) -> dict[str, Any]:
    runtime_payload = _load_json(repo_root, runtime_readiness)
    expected_slots = _expected_engine_run_slots(runtime_payload)
    header_fields, rows = _read_csv_rows(repo_root, template)
    row_preflights = [_row_preflight(repo_root, row) for row in rows]
    role_receipt_plan = [
        role_row
        for row in row_preflights
        for role_row in row["role_plan_rows"]
    ]
    expected_slot_keys = [_slot_key(row) for row in expected_slots]
    template_slot_keys = [_slot_key(row) for row in rows]
    missing_expected_slots = [
        slot
        for slot in expected_slots
        if _slot_key(slot) not in template_slot_keys
    ]
    unexpected_template_slots = [
        {"case_id": case_id, "engine_id": engine_id, "docking_run_id": docking_run_id}
        for case_id, engine_id, docking_run_id in template_slot_keys
        if expected_slot_keys and (case_id, engine_id, docking_run_id) not in expected_slot_keys
    ]
    duplicate_slots = sorted(
        {
            "_".join((case_id, engine_id, docking_run_id))
            for case_id, engine_id, docking_run_id in template_slot_keys
            if case_id
            and engine_id
            and docking_run_id
            and template_slot_keys.count((case_id, engine_id, docking_run_id)) > 1
        }
    )
    missing_header_fields = [
        field for field in FLAT_REQUIRED_FIELDS if field not in header_fields
    ]
    missing_required_value_count = sum(
        len(row["missing_required_fields"]) for row in row_preflights
    )
    missing_engine_run_receipt_value_count = sum(
        len(row["missing_engine_run_receipt_fields"]) for row in row_preflights
    )
    invalid_checksum_count = sum(
        len(row["invalid_checksum_fields"]) for row in row_preflights
    )
    missing_local_ref_count = sum(
        len(row["missing_local_ref_fields"]) for row in row_preflights
    )
    missing_numeric_value_count = sum(
        len(row["missing_numeric_fields"]) for row in row_preflights
    )
    invalid_numeric_value_count = sum(
        len(row["invalid_numeric_fields"]) for row in row_preflights
    )
    invalid_pose_success_count = sum(
        1 for row in row_preflights if not row["pose_success_status"]["valid"]
    )
    invalid_score_direction_count = sum(
        1 for row in row_preflights if not row["score_direction_status"]["valid"]
    )
    template_slot_coverage_complete = bool(rows) and not (
        missing_expected_slots or unexpected_template_slots or duplicate_slots
    )
    adapter_template_ready = bool(rows) and template_slot_coverage_complete and not (
        missing_header_fields
        or missing_required_value_count
        or missing_engine_run_receipt_value_count
        or invalid_checksum_count
        or missing_local_ref_count
        or missing_numeric_value_count
        or invalid_numeric_value_count
        or invalid_pose_success_count
        or invalid_score_direction_count
    )
    if not rows:
        status = "template_missing_or_empty"
    elif not template_slot_coverage_complete or missing_header_fields:
        status = "template_slot_coverage_blocked"
    elif adapter_template_ready:
        status = "operator_template_complete"
    else:
        status = "operator_rows_completion_required"
    expected_rows_resolved = _resolve(repo_root, expected_rows)
    role_receipt_blocked_count = sum(
        1 for row in role_receipt_plan if row["status"] != "ready"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
                runtime_readiness,
                template,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_rows_template_preflight",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bool(rows) and template_slot_coverage_complete and not missing_header_fields,
        "adapter_template_ready": adapter_template_ready,
        "template_artifact": str(template),
        "expected_rows_artifact": str(expected_rows),
        "expected_rows_detected": expected_rows_resolved.exists(),
        "runtime_readiness_artifact": str(runtime_readiness),
        "required_flat_row_fields": list(FLAT_REQUIRED_FIELDS),
        "engine_run_receipt_fields": list(ENGINE_RUN_RECEIPT_FIELDS),
        "engine_run_checksum_fields": list(ENGINE_RUN_CHECKSUM_FIELDS),
        "engine_run_provenance_fields": list(ENGINE_RUN_PROVENANCE_FIELDS),
        "header_fields": header_fields,
        "missing_header_fields": missing_header_fields,
        "expected_engine_run_slots": expected_slots,
        "template_engine_run_slots": [
            {
                "case_id": case_id,
                "engine_id": engine_id,
                "docking_run_id": docking_run_id,
            }
            for case_id, engine_id, docking_run_id in template_slot_keys
        ],
        "missing_expected_slots": missing_expected_slots,
        "unexpected_template_slots": unexpected_template_slots,
        "duplicate_slots": duplicate_slots,
        "row_preflight_rows": row_preflights,
        "row_preflight_count": len(row_preflights),
        "role_receipt_plan": role_receipt_plan,
        "template_safety_policy": {
            "template_is_not_evidence": True,
            "operator_rows_must_be_real_engine_outputs": True,
            "placeholder_or_fixture_rows_do_not_promote": True,
            "preflight_does_not_run_engines": True,
            "adapter_rows_must_be_materialized_from_real_runs": True,
        },
        "operator_actions": [
            "do_not_commit_template_as_actual_vina_gnina_rows",
            "attach_real_predicted_ligand_outputs_for_each_engine_run",
            "fill_engine_version_config_checksum_rmsd_pose_success_and_score",
            "attach_engine_run_receipts",
            "attach_case_source_and_comparison_metric_receipts",
            "materialize_completed_rows_template_to_expected_rows_artifact",
            "materialize_public_benchmark_vina_gnina_comparison_adapter",
        ],
        "commands": {
            "write_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py "
                f"--out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}"
            ),
            "materialize_rows_from_template": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py "
                f"--template {template} --out-rows {expected_rows} "
                f"--out-report {DEFAULT_ROWS_FROM_TEMPLATE_REPORT}"
            ),
            "materialize_adapter": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                f"--intake {expected_rows} "
                f"--out-adapter {PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
                f"--out-report {PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
                "--fail-blocked"
            ),
            "rerun_phase2_row_audit": (
                "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
                f"--vina-gnina-rows {expected_rows} --fail-blocked"
            ),
        },
        "summary": {
            "expected_engine_run_slot_count": len(expected_slots),
            "template_row_count": len(rows),
            "template_slot_count": len(template_slot_keys),
            "template_slot_coverage_complete": template_slot_coverage_complete,
            "missing_expected_slot_count": len(missing_expected_slots),
            "unexpected_template_slot_count": len(unexpected_template_slots),
            "duplicate_slot_count": len(duplicate_slots),
            "missing_header_field_count": len(missing_header_fields),
            "missing_required_value_count": missing_required_value_count,
            "missing_engine_run_receipt_value_count": missing_engine_run_receipt_value_count,
            "invalid_checksum_count": invalid_checksum_count,
            "missing_local_ref_count": missing_local_ref_count,
            "missing_numeric_value_count": missing_numeric_value_count,
            "invalid_numeric_value_count": invalid_numeric_value_count,
            "invalid_pose_success_count": invalid_pose_success_count,
            "invalid_score_direction_count": invalid_score_direction_count,
            "role_receipt_plan_count": len(role_receipt_plan),
            "role_receipt_blocked_count": role_receipt_blocked_count,
            "adapter_template_ready": adapter_template_ready,
            "expected_rows_detected": expected_rows_resolved.exists(),
        },
        "claim_boundary": (
            "This preflight audits the Vina/GNINA adapter rows template only. It "
            "does not promote the template to actual engine output rows, run Vina "
            "or GNINA, compute symmetry-aware RMSD, synthesize pose-success labels, "
            "or close Public Benchmark Phase 2."
        ),
    }


def render_public_benchmark_vina_gnina_rows_template_preflight_markdown(
    payload: dict[str, Any],
) -> str:
    summary = payload["summary"]
    lines = [
        "# Public Benchmark Vina/GNINA Rows Template Preflight",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `adapter_template_ready`: `{payload['adapter_template_ready']}`",
        f"- `template_row_count`: `{summary['template_row_count']}`",
        f"- `expected_engine_run_slot_count`: `{summary['expected_engine_run_slot_count']}`",
        f"- `missing_required_value_count`: `{summary['missing_required_value_count']}`",
        "- `missing_engine_run_receipt_value_count`: "
        f"`{summary['missing_engine_run_receipt_value_count']}`",
        f"- `missing_local_ref_count`: `{summary['missing_local_ref_count']}`",
        f"- `missing_numeric_value_count`: `{summary['missing_numeric_value_count']}`",
        f"- `invalid_pose_success_count`: `{summary['invalid_pose_success_count']}`",
        f"- `role_receipt_plan_count`: `{summary['role_receipt_plan_count']}`",
        f"- `role_receipt_blocked_count`: `{summary['role_receipt_blocked_count']}`",
        f"- `expected_rows_detected`: `{summary['expected_rows_detected']}`",
        "",
        "## Engine Run Rows",
        "",
        "| Slot | Case | Engine | Status | Missing Receipts | Missing Values |",
        "|---|---|---|---|---|---|",
    ]
    for row in payload["row_preflight_rows"]:
        lines.append(
            f"| `{row['slot_id']}` | `{row['case_id']}` | "
            f"`{row['engine_id']}` | `{row['status']}` | "
            f"`{len(row['missing_engine_run_receipt_fields'])}` | "
            f"`{len(row['missing_required_fields'])}` |"
        )
    lines.extend(
        [
            "",
            "## Receipt Role Plan",
            "",
            "| Slot | Role | Status | Missing Fields | Invalid Fields |",
            "|---|---|---|---|---|",
        ]
    )
    for row in payload["role_receipt_plan"]:
        missing_fields = ", ".join(
            f"`{field}`" for field in row["missing_fields"] if str(field)
        )
        invalid_fields = ", ".join(
            f"`{field}`" for field in row["invalid_fields"] if str(field)
        )
        lines.append(
            f"| `{row['slot_id']}` | `{row['role_id']}` | "
            f"`{row['status']}` | {missing_fields or '`none`'} | "
            f"{invalid_fields or '`none`'} |"
        )
    lines.extend(["", "## Commands", ""])
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_public_benchmark_vina_gnina_rows_template_preflight(
    *,
    repo_root: Path = ROOT,
    runtime_readiness: Path = DEFAULT_RUNTIME_READINESS,
    template: Path = DEFAULT_TEMPLATE,
    expected_rows: Path = DEFAULT_EXPECTED_ROWS,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_public_benchmark_vina_gnina_rows_template_preflight(
        repo_root=repo_root,
        runtime_readiness=runtime_readiness,
        template=template,
        expected_rows=expected_rows,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = _resolve(repo_root, out_md)
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_public_benchmark_vina_gnina_rows_template_preflight_markdown(
            payload
        ),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--runtime-readiness", type=Path, default=DEFAULT_RUNTIME_READINESS)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--expected-rows", type=Path, default=DEFAULT_EXPECTED_ROWS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_public_benchmark_vina_gnina_rows_template_preflight(
        repo_root=args.repo_root,
        runtime_readiness=args.runtime_readiness,
        template=args.template,
        expected_rows=args.expected_rows,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-rows-template-preflight: "
            f"{payload['status']} | rows={payload['row_preflight_count']} | "
            f"adapter_template_ready={payload['adapter_template_ready']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
