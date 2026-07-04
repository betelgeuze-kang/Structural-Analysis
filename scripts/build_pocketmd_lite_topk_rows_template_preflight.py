#!/usr/bin/env python3
"""Preflight the PocketMD Lite top-k rows template without promoting it."""

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

from materialize_pocketmd_lite_operator_intake_from_rows import (  # noqa: E402
    DEFAULT_MAX_TOP_K,
    SOURCE_RECEIPT_REQUIREMENTS,
    row_value_contract,
)
from materialize_pocketmd_lite_topk_survival_report import (  # noqa: E402
    PLACEHOLDER_PROVENANCE_PREFIXES,
    PLACEHOLDER_SOURCE_TEXT_MARKERS,
    REQUIRED_CASE_FIELDS,
    SOURCE_CHECKSUM_PATTERN,
    TOPK_ROW_QUALITY_CRITERIA,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_REFINEMENT_PLAN = PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
DEFAULT_TEMPLATE = PRODUCTIZATION / "pocketmd_lite_topk_rows_template.csv"
DEFAULT_EXPECTED_ROWS = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_OUT = PRODUCTIZATION / "pocketmd_lite_topk_rows_template_preflight.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "pocketmd-lite-topk-rows-template-preflight.v1"
REQUIRED_METRIC_FIELDS = (
    "local_min_survived",
    "contact_persistence_rate",
    "h_bond_persistence_rate",
    "clash_count_before",
    "clash_count_after",
    "uncertainty_low",
    "uncertainty_high",
    "uncertainty_unit",
)
ENERGY_PROXY_FIELDS = ("pre_refinement_energy_proxy", "post_refinement_energy_proxy")
ROW_RECEIPT_FIELDS = (
    "upstream_top_k_provenance_ref",
    "upstream_top_k_source_checksum",
    "provenance_ref",
    "source_checksum",
)
CHECKSUM_FIELDS = ("upstream_top_k_source_checksum", "source_checksum")
PROVENANCE_REF_FIELDS = ("upstream_top_k_provenance_ref", "provenance_ref")
ROLE_PLANS = (
    {
        "role_id": "upstream_top_k_candidate_scope_receipt",
        "required_fields": (
            "case_id",
            "candidate_id",
            "top_k_rank",
            "upstream_top_k_provenance_ref",
            "upstream_top_k_source_checksum",
        ),
        "operator_action": "attach_upstream_top_k_scope_receipt",
        "closes_phase4_criteria": (
            "top_k_refinement_rows_present",
            "top_k_refinement_case_coverage",
        ),
    },
    {
        "role_id": "lite_refinement_run_receipt",
        "required_fields": (
            "pre_refinement_energy_proxy",
            "post_refinement_energy_proxy",
            "local_min_survived",
            "provenance_ref",
            "source_checksum",
        ),
        "operator_action": "attach_lite_refinement_run_receipt",
        "closes_phase4_criteria": (
            "local_min_survival_materialized",
            "report_blockers_resolved",
        ),
    },
    {
        "role_id": "interaction_persistence_receipt",
        "required_fields": (
            "contact_persistence_rate",
            "h_bond_persistence_rate",
            "clash_count_before",
            "clash_count_after",
            "provenance_ref",
            "source_checksum",
        ),
        "operator_action": "attach_contact_hbond_clash_metric_receipt",
        "closes_phase4_criteria": (
            "contact_persistence_materialized",
            "h_bond_persistence_materialized",
            "clash_relief_materialized",
            "report_blockers_resolved",
        ),
    },
    {
        "role_id": "uncertainty_interval_receipt",
        "required_fields": (
            "uncertainty_low",
            "uncertainty_high",
            "uncertainty_unit",
            "provenance_ref",
            "source_checksum",
        ),
        "operator_action": "attach_uncertainty_interval_receipt",
        "closes_phase4_criteria": (
            "uncertainty_summary_materialized",
            "report_blockers_resolved",
        ),
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


def _required_flat_row_fields() -> list[str]:
    fields: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        if field == "uncertainty_interval":
            fields.extend(["uncertainty_low", "uncertainty_high", "uncertainty_unit"])
        else:
            fields.append(field)
    return fields


REQUIRED_FLAT_ROW_FIELDS = tuple(_required_flat_row_fields())


def _expected_slots(refinement_plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = refinement_plan.get("candidate_slots")
    if isinstance(candidates, list) and candidates:
        rows = candidates
    else:
        rows = refinement_plan.get("candidate_slot_statuses")
    slots = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            case_id = str(row.get("case_id") or "")
            try:
                top_k_rank = int(row.get("top_k_rank"))
            except (TypeError, ValueError):
                continue
            if case_id and top_k_rank > 0:
                slots.append(
                    {
                        "slot_id": f"{case_id}_rank_{top_k_rank:02d}",
                        "case_id": case_id,
                        "top_k_rank": top_k_rank,
                    }
                )
    if slots:
        return slots

    min_case_count = int(TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"])
    min_rank_coverage = int(TOPK_ROW_QUALITY_CRITERIA["min_top_k_rank_coverage_per_case"])
    return [
        {
            "slot_id": f"pocketmd_lite_case_{case_index:03d}_rank_{rank:02d}",
            "case_id": f"pocketmd_lite_case_{case_index:03d}",
            "top_k_rank": rank,
        }
        for case_index in range(1, min_case_count + 1)
        for rank in range(1, min_rank_coverage + 1)
    ]


def _slot_key(row: dict[str, Any]) -> tuple[str, int]:
    try:
        top_k_rank = int(row.get("top_k_rank"))
    except (TypeError, ValueError):
        top_k_rank = 0
    return str(row.get("case_id") or ""), top_k_rank


def _number(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _integer(value: str) -> int | None:
    parsed = _number(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _boolean(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y"}:
        return True
    if lowered in {"0", "false", "f", "no", "n"}:
        return False
    return None


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


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


def _provenance_ref_status(value: str) -> dict[str, Any]:
    if not value:
        return {"present": False, "status": "missing", "blocker": "ref_missing"}
    if _has_placeholder_provenance_prefix(value) or _contains_marker(
        value,
        PLACEHOLDER_SOURCE_TEXT_MARKERS,
    ):
        return {
            "present": True,
            "status": "placeholder",
            "blocker": "ref_placeholder",
        }
    return {"present": True, "status": "present", "blocker": ""}


def _metric_status(field: str, value: str) -> dict[str, Any]:
    if not value:
        return {"present": False, "valid": False, "blocker": "metric_missing"}
    if field == "local_min_survived":
        valid = _boolean(value) is not None
        return {"present": True, "valid": valid, "blocker": "" if valid else "boolean_invalid"}
    if field in {"contact_persistence_rate", "h_bond_persistence_rate"}:
        parsed = _number(value)
        valid = parsed is not None and 0.0 <= parsed <= 1.0
        return {"present": True, "valid": valid, "blocker": "" if valid else "rate_invalid"}
    if field in {"clash_count_before", "clash_count_after"}:
        parsed = _integer(value)
        valid = parsed is not None and parsed >= 0
        return {"present": True, "valid": valid, "blocker": "" if valid else "integer_invalid"}
    if field in {"uncertainty_low", "uncertainty_high"}:
        valid = _number(value) is not None
        return {"present": True, "valid": valid, "blocker": "" if valid else "number_invalid"}
    if field == "uncertainty_unit":
        return {"present": True, "valid": True, "blocker": ""}
    return {"present": True, "valid": True, "blocker": ""}


def _energy_proxy_status(value: str) -> dict[str, Any]:
    if not value:
        return {"present": False, "valid": False, "blocker": "energy_proxy_missing"}
    parsed = _number(value)
    return {
        "present": True,
        "valid": parsed is not None,
        "blocker": "" if parsed is not None else "energy_proxy_invalid",
    }


def _role_plan_rows(row_preflight: dict[str, Any]) -> list[dict[str, Any]]:
    role_rows = []
    missing_sets = [
        set(row_preflight["missing_required_fields"]),
        set(row_preflight["missing_metric_fields"]),
        set(row_preflight["missing_energy_proxy_fields"]),
        set(row_preflight["missing_receipt_fields"]),
    ]
    invalid_sets = [
        set(row_preflight["invalid_checksum_fields"]),
        set(row_preflight["invalid_provenance_ref_fields"]),
        set(row_preflight["invalid_metric_fields"]),
        set(row_preflight["invalid_energy_proxy_fields"]),
    ]
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
        if (
            role["role_id"] == "upstream_top_k_candidate_scope_receipt"
            and row_preflight["top_k_rank_blocker"]
        ):
            blockers.append(str(row_preflight["top_k_rank_blocker"]))
        if (
            role["role_id"] == "uncertainty_interval_receipt"
            and row_preflight["uncertainty_interval_blocker"]
        ):
            blockers.append(str(row_preflight["uncertainty_interval_blocker"]))
        role_rows.append(
            {
                "case_id": row_preflight["case_id"],
                "top_k_rank": row_preflight["top_k_rank"],
                "candidate_id": row_preflight["candidate_id"],
                "role_id": role["role_id"],
                "required_fields": required_fields,
                "missing_fields": missing_fields,
                "invalid_fields": invalid_fields,
                "closes_phase4_criteria": list(role["closes_phase4_criteria"]),
                "operator_action": role["operator_action"],
                "status": "ready" if not blockers else "operator_completion_required",
                "blockers": blockers,
            }
        )
    return role_rows


def _row_preflight(row: dict[str, str]) -> dict[str, Any]:
    missing_required_fields = [
        field for field in REQUIRED_FLAT_ROW_FIELDS if not str(row.get(field) or "")
    ]
    missing_metric_fields = [
        field for field in REQUIRED_METRIC_FIELDS if not str(row.get(field) or "")
    ]
    missing_energy_proxy_fields = [
        field for field in ENERGY_PROXY_FIELDS if not str(row.get(field) or "")
    ]
    missing_receipt_fields = [
        field for field in ROW_RECEIPT_FIELDS if not str(row.get(field) or "")
    ]
    checksum_statuses = {
        field: _checksum_status(str(row.get(field) or "")) for field in CHECKSUM_FIELDS
    }
    invalid_checksum_fields = [
        field
        for field, status in checksum_statuses.items()
        if status["present"] and str(status["blocker"] or "")
    ]
    provenance_ref_statuses = {
        field: _provenance_ref_status(str(row.get(field) or ""))
        for field in PROVENANCE_REF_FIELDS
    }
    invalid_provenance_ref_fields = [
        field
        for field, status in provenance_ref_statuses.items()
        if status["present"] and str(status["blocker"] or "")
    ]
    metric_statuses = {
        field: _metric_status(field, str(row.get(field) or ""))
        for field in REQUIRED_METRIC_FIELDS
    }
    invalid_metric_fields = [
        field
        for field, status in metric_statuses.items()
        if status["present"] and not bool(status["valid"])
    ]
    energy_proxy_statuses = {
        field: _energy_proxy_status(str(row.get(field) or ""))
        for field in ENERGY_PROXY_FIELDS
    }
    invalid_energy_proxy_fields = [
        field
        for field, status in energy_proxy_statuses.items()
        if status["present"] and not bool(status["valid"])
    ]
    interval_blocker = ""
    low = _number(str(row.get("uncertainty_low") or ""))
    high = _number(str(row.get("uncertainty_high") or ""))
    if low is not None and high is not None and high < low:
        interval_blocker = "uncertainty_interval_high_below_low"
    rank = _integer(str(row.get("top_k_rank") or ""))
    rank_blocker = ""
    if str(row.get("top_k_rank") or "") and (rank is None or rank < 1):
        rank_blocker = "top_k_rank_invalid"
    elif rank is not None and rank > DEFAULT_MAX_TOP_K:
        rank_blocker = f"top_k_rank_exceeds_max:{DEFAULT_MAX_TOP_K}"

    blockers = []
    if missing_required_fields:
        blockers.append("topk_required_fields_missing")
    if missing_metric_fields:
        blockers.append("topk_metric_fields_missing")
    if missing_energy_proxy_fields:
        blockers.append("topk_energy_proxy_fields_missing")
    if missing_receipt_fields:
        blockers.append("topk_receipt_fields_missing")
    if invalid_checksum_fields:
        blockers.append("topk_checksum_fields_invalid")
    if invalid_provenance_ref_fields:
        blockers.append("topk_provenance_refs_invalid")
    if invalid_metric_fields or interval_blocker:
        blockers.append("topk_metric_values_invalid")
    if invalid_energy_proxy_fields:
        blockers.append("topk_energy_proxy_values_invalid")
    if rank_blocker:
        blockers.append("top_k_rank_invalid")
    row_preflight = {
        "case_id": str(row.get("case_id") or ""),
        "top_k_rank": rank or 0,
        "candidate_id": str(row.get("candidate_id") or ""),
        "slot_id": (
            f"{row.get('case_id')}_rank_{rank:02d}"
            if str(row.get("case_id") or "") and rank
            else ""
        ),
        "status": "operator_completion_required" if blockers else "ready",
        "missing_required_fields": missing_required_fields,
        "missing_metric_fields": missing_metric_fields,
        "missing_energy_proxy_fields": missing_energy_proxy_fields,
        "missing_receipt_fields": missing_receipt_fields,
        "invalid_checksum_fields": invalid_checksum_fields,
        "invalid_provenance_ref_fields": invalid_provenance_ref_fields,
        "invalid_metric_fields": invalid_metric_fields,
        "invalid_energy_proxy_fields": invalid_energy_proxy_fields,
        "uncertainty_interval_blocker": interval_blocker,
        "top_k_rank_blocker": rank_blocker,
        "checksum_statuses": checksum_statuses,
        "provenance_ref_statuses": provenance_ref_statuses,
        "metric_statuses": metric_statuses,
        "energy_proxy_statuses": energy_proxy_statuses,
        "blockers": blockers,
    }
    row_preflight["role_plan_rows"] = _role_plan_rows(row_preflight)
    return row_preflight


def _operator_input_source_receipt_plan(
    *,
    expected_rows: Path,
    expected_rows_detected: bool,
) -> list[dict[str, Any]]:
    plan = []
    for field in SOURCE_RECEIPT_REQUIREMENTS["required_fields"]:
        field = str(field)
        if field == "source_artifact":
            plan.append(
                {
                    "field": field,
                    "expected_value": str(expected_rows),
                    "status": "ready"
                    if expected_rows_detected
                    else "operator_completion_required",
                    "blocker": "" if expected_rows_detected else "source_artifact_missing",
                    "operator_action": "write_pocketmd_lite_topk_rows_at_expected_artifact",
                }
            )
            continue
        if field == "source_artifact_sha256":
            plan.append(
                {
                    "field": field,
                    "expected_value": "",
                    "status": "operator_completion_required",
                    "blocker": "source_artifact_sha256_required",
                    "operator_action": "compute_source_artifact_sha256_after_rows_written",
                }
            )
            continue
        plan.append(
            {
                "field": field,
                "expected_value": "",
                "status": "operator_completion_required",
                "blocker": f"{field}_required",
                "operator_action": f"attach_operator_input_source_{field}",
            }
        )
    return plan


def build_pocketmd_lite_topk_rows_template_preflight(
    *,
    repo_root: Path = ROOT,
    refinement_plan: Path = DEFAULT_REFINEMENT_PLAN,
    template: Path = DEFAULT_TEMPLATE,
    expected_rows: Path = DEFAULT_EXPECTED_ROWS,
) -> dict[str, Any]:
    refinement_plan_payload = _load_json(repo_root, refinement_plan)
    header_fields, rows = _read_csv_rows(repo_root, template)
    row_preflights = [_row_preflight(row) for row in rows]
    role_receipt_plan = [
        role_row
        for row in row_preflights
        for role_row in row["role_plan_rows"]
    ]
    expected_slots = _expected_slots(refinement_plan_payload)
    expected_slot_keys = [(_slot_key(row)) for row in expected_slots]
    template_slot_keys = [_slot_key(row) for row in rows]
    missing_expected_slots = [
        slot
        for slot in expected_slots
        if (str(slot["case_id"]), int(slot["top_k_rank"])) not in template_slot_keys
    ]
    unexpected_template_slots = [
        {"case_id": case_id, "top_k_rank": rank}
        for case_id, rank in template_slot_keys
        if expected_slot_keys and (case_id, rank) not in expected_slot_keys
    ]
    duplicate_slots = sorted(
        {
            f"{case_id}_rank_{rank:02d}"
            for case_id, rank in template_slot_keys
            if case_id and rank and template_slot_keys.count((case_id, rank)) > 1
        }
    )
    missing_header_fields = [
        field for field in REQUIRED_FLAT_ROW_FIELDS if field not in header_fields
    ]
    missing_required_value_count = sum(
        len(row["missing_required_fields"]) for row in row_preflights
    )
    missing_metric_value_count = sum(
        len(row["missing_metric_fields"]) for row in row_preflights
    )
    missing_energy_proxy_value_count = sum(
        len(row["missing_energy_proxy_fields"]) for row in row_preflights
    )
    missing_receipt_value_count = sum(
        len(row["missing_receipt_fields"]) for row in row_preflights
    )
    invalid_checksum_count = sum(
        len(row["invalid_checksum_fields"]) for row in row_preflights
    )
    invalid_provenance_ref_count = sum(
        len(row["invalid_provenance_ref_fields"]) for row in row_preflights
    )
    invalid_metric_value_count = sum(
        len(row["invalid_metric_fields"])
        + (1 if row["uncertainty_interval_blocker"] else 0)
        + (1 if row["top_k_rank_blocker"] else 0)
        for row in row_preflights
    )
    invalid_energy_proxy_value_count = sum(
        len(row["invalid_energy_proxy_fields"]) for row in row_preflights
    )
    template_slot_coverage_complete = bool(rows) and not (
        missing_expected_slots or unexpected_template_slots or duplicate_slots
    )
    top_k_template_ready = bool(rows) and template_slot_coverage_complete and not (
        missing_header_fields
        or missing_required_value_count
        or missing_metric_value_count
        or missing_energy_proxy_value_count
        or missing_receipt_value_count
        or invalid_checksum_count
        or invalid_provenance_ref_count
        or invalid_metric_value_count
        or invalid_energy_proxy_value_count
    )
    if not rows:
        status = "template_missing_or_empty"
    elif not template_slot_coverage_complete or missing_header_fields:
        status = "template_slot_coverage_blocked"
    elif top_k_template_ready:
        status = "operator_template_complete"
    else:
        status = "operator_rows_completion_required"
    expected_rows_resolved = _resolve(repo_root, expected_rows)
    expected_rows_detected = expected_rows_resolved.exists()
    operator_input_source_receipt_plan = _operator_input_source_receipt_plan(
        expected_rows=expected_rows,
        expected_rows_detected=expected_rows_detected,
    )
    role_receipt_blocked_count = sum(
        1 for row in role_receipt_plan if row["status"] != "ready"
    )
    operator_input_source_receipt_blocked_count = sum(
        1
        for row in operator_input_source_receipt_plan
        if row["status"] != "ready"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_pocketmd_lite_topk_rows_template_preflight.py"),
                Path("scripts/build_pocketmd_lite_refinement_execution_plan.py"),
                refinement_plan,
                template,
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_topk_rows_template_preflight",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bool(rows) and template_slot_coverage_complete and not missing_header_fields,
        "top_k_template_ready": top_k_template_ready,
        "template_artifact": str(template),
        "expected_rows_artifact": str(expected_rows),
        "expected_rows_detected": expected_rows_detected,
        "required_fields": list(REQUIRED_FLAT_ROW_FIELDS),
        "required_metric_fields": list(REQUIRED_METRIC_FIELDS),
        "required_energy_proxy_fields": list(ENERGY_PROXY_FIELDS),
        "required_row_receipt_fields": list(ROW_RECEIPT_FIELDS),
        "operator_source_receipt_required_fields": list(
            SOURCE_RECEIPT_REQUIREMENTS["required_fields"]
        ),
        "header_fields": header_fields,
        "missing_header_fields": missing_header_fields,
        "expected_slots": expected_slots,
        "template_slots": [
            {"case_id": case_id, "top_k_rank": rank}
            for case_id, rank in template_slot_keys
        ],
        "missing_expected_slots": missing_expected_slots,
        "unexpected_template_slots": unexpected_template_slots,
        "duplicate_slots": duplicate_slots,
        "row_preflight_rows": row_preflights,
        "row_preflight_count": len(row_preflights),
        "role_receipt_plan": role_receipt_plan,
        "operator_input_source_receipt_plan": operator_input_source_receipt_plan,
        "row_value_contract": row_value_contract(max_top_k=DEFAULT_MAX_TOP_K),
        "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
        "template_safety_policy": {
            "template_is_not_evidence": True,
            "operator_rows_must_be_real_top_k_refinement_outputs": True,
            "placeholder_or_fixture_rows_do_not_promote": True,
            "preflight_does_not_run_refinement": True,
            "broad_all_atom_or_fep_claims_remain_locked": True,
        },
        "operator_actions": [
            "do_not_commit_template_as_actual_topk_row_evidence",
            "fill_blank_top_k_refinement_metric_values",
            "attach_upstream_top_k_candidate_scope_receipts",
            "attach_lite_refinement_metric_receipts",
            "materialize_completed_template_to_expected_rows_artifact",
            "rerun_pocketmd_lite_operator_intake_and_survival_materializer",
        ],
        "commands": {
            "write_preflight": (
                "python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py "
                f"--out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}"
            ),
            "materialize_rows_from_template": (
                "python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py "
                f"--template {template} --out-rows {expected_rows} "
                f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_rows_from_template_report.json'} "
                "--fail-blocked"
            ),
            "import_rows": (
                "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
                f"--rows {expected_rows} "
                f"--out {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
            "materialize_survival_report": (
                "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
                f"--intake {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
                f"--contract {PRODUCTIZATION / 'pocketmd_lite_contract.json'} "
                f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_survival_report.json'} "
                "--out-surface implementation/phase1/release_evidence/surface/"
                "pocketmd_lite_science_product_surface.json --fail-blocked"
            ),
            "rerun_refinement_execution_plan": (
                "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py "
                f"--out {DEFAULT_REFINEMENT_PLAN}"
            ),
            "rerun_science_actual_closure": (
                "python3 scripts/materialize_science_actual_closure_from_rows.py "
                f"--pocketmd-rows {expected_rows} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license> --fail-blocked"
            ),
        },
        "summary": {
            "expected_slot_count": len(expected_slots),
            "template_row_count": len(rows),
            "template_slot_count": len(template_slot_keys),
            "template_slot_coverage_complete": template_slot_coverage_complete,
            "missing_expected_slot_count": len(missing_expected_slots),
            "unexpected_template_slot_count": len(unexpected_template_slots),
            "duplicate_slot_count": len(duplicate_slots),
            "missing_header_field_count": len(missing_header_fields),
            "missing_required_value_count": missing_required_value_count,
            "missing_metric_value_count": missing_metric_value_count,
            "missing_energy_proxy_value_count": missing_energy_proxy_value_count,
            "missing_receipt_value_count": missing_receipt_value_count,
            "invalid_checksum_count": invalid_checksum_count,
            "invalid_provenance_ref_count": invalid_provenance_ref_count,
            "invalid_metric_value_count": invalid_metric_value_count,
            "invalid_energy_proxy_value_count": invalid_energy_proxy_value_count,
            "role_receipt_plan_count": len(role_receipt_plan),
            "role_receipt_blocked_count": role_receipt_blocked_count,
            "operator_input_source_receipt_requirement_count": len(
                operator_input_source_receipt_plan
            ),
            "operator_input_source_receipt_blocked_count": (
                operator_input_source_receipt_blocked_count
            ),
            "top_k_template_ready": top_k_template_ready,
            "expected_rows_detected": expected_rows_detected,
        },
        "claim_boundary": (
            "This preflight audits the PocketMD Lite top-k rows template only. It "
            "does not promote the template to actual row evidence, run bounded "
            "refinement, synthesize local-min, contact, H-bond, clash, or "
            "uncertainty metrics, or close PocketMD Lite Phase 4."
        ),
    }


def render_pocketmd_lite_topk_rows_template_preflight_markdown(
    payload: dict[str, Any],
) -> str:
    summary = payload["summary"]
    lines = [
        "# PocketMD Lite Top-k Rows Template Preflight",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `top_k_template_ready`: `{payload['top_k_template_ready']}`",
        f"- `template_row_count`: `{summary['template_row_count']}`",
        f"- `expected_slot_count`: `{summary['expected_slot_count']}`",
        f"- `missing_required_value_count`: `{summary['missing_required_value_count']}`",
        f"- `missing_metric_value_count`: `{summary['missing_metric_value_count']}`",
        f"- `missing_energy_proxy_value_count`: `{summary['missing_energy_proxy_value_count']}`",
        f"- `missing_receipt_value_count`: `{summary['missing_receipt_value_count']}`",
        f"- `invalid_metric_value_count`: `{summary['invalid_metric_value_count']}`",
        f"- `invalid_energy_proxy_value_count`: `{summary['invalid_energy_proxy_value_count']}`",
        f"- `role_receipt_blocked_count`: `{summary['role_receipt_blocked_count']}`",
        "- `operator_input_source_receipt_blocked_count`: "
        f"`{summary['operator_input_source_receipt_blocked_count']}`",
        f"- `expected_rows_detected`: `{summary['expected_rows_detected']}`",
        "",
        "## Row Slots",
        "",
        "| Slot | Case | Rank | Status | Missing Energy | Missing Metrics | Missing Receipts |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in payload["row_preflight_rows"]:
        lines.append(
            f"| `{row['slot_id']}` | `{row['case_id']}` | "
            f"`{row['top_k_rank']}` | `{row['status']}` | "
            f"`{len(row['missing_energy_proxy_fields'])}` | "
            f"`{len(row['missing_metric_fields'])}` | "
            f"`{len(row['missing_receipt_fields'])}` |"
        )
    role_plan = [
        row for row in payload.get("role_receipt_plan", []) if isinstance(row, dict)
    ]
    if role_plan:
        lines.extend(
            [
                "",
                "## Role Receipt Plan",
                "",
                "| Candidate | Role | Status | Missing | Invalid | Action |",
                "|---|---|---|---:|---:|---|",
            ]
        )
        for row in role_plan:
            lines.append(
                f"| `{row.get('candidate_id', '')}` | `{row.get('role_id', '')}` | "
                f"`{row.get('status', '')}` | "
                f"`{len(row.get('missing_fields', []))}` | "
                f"`{len(row.get('invalid_fields', []))}` | "
                f"`{row.get('operator_action', '')}` |"
            )
    source_receipt_plan = [
        row
        for row in payload.get("operator_input_source_receipt_plan", [])
        if isinstance(row, dict)
    ]
    if source_receipt_plan:
        lines.extend(
            [
                "",
                "## Operator Input Source Receipt Plan",
                "",
                "| Field | Status | Blocker | Action |",
                "|---|---|---|---|",
            ]
        )
        for row in source_receipt_plan:
            lines.append(
                f"| `{row.get('field', '')}` | `{row.get('status', '')}` | "
                f"`{row.get('blocker', '')}` | "
                f"`{row.get('operator_action', '')}` |"
            )
    lines.extend(["", "## Commands", ""])
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_pocketmd_lite_topk_rows_template_preflight(
    *,
    repo_root: Path = ROOT,
    refinement_plan: Path = DEFAULT_REFINEMENT_PLAN,
    template: Path = DEFAULT_TEMPLATE,
    expected_rows: Path = DEFAULT_EXPECTED_ROWS,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_pocketmd_lite_topk_rows_template_preflight(
        repo_root=repo_root,
        refinement_plan=refinement_plan,
        template=template,
        expected_rows=expected_rows,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = _resolve(repo_root, out_md)
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_pocketmd_lite_topk_rows_template_preflight_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--refinement-plan", type=Path, default=DEFAULT_REFINEMENT_PLAN)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--expected-rows", type=Path, default=DEFAULT_EXPECTED_ROWS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_pocketmd_lite_topk_rows_template_preflight(
        repo_root=args.repo_root,
        refinement_plan=args.refinement_plan,
        template=args.template,
        expected_rows=args.expected_rows,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "pocketmd-lite-topk-rows-template-preflight: "
            f"{payload['status']} | rows={payload['row_preflight_count']} | "
            f"template_ready={payload['top_k_template_ready']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
