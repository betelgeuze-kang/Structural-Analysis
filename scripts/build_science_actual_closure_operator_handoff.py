#!/usr/bin/env python3
"""Build a one-page operator handoff for science actual-closure row inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_AUDIT = PRODUCTIZATION / "science_actual_closure_row_audit.json"
DEFAULT_OUT = PRODUCTIZATION / "science_actual_closure_operator_handoff.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_POCKETMD_REFINEMENT_PLAN = (
    PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
)
DEFAULT_VINA_GNINA_RUNTIME_READINESS = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_runtime_readiness.json"
)
DEFAULT_GPCR_SUITE_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"
SCHEMA_VERSION = "science-actual-closure-operator-handoff.v1"
EXPECTED_ROW_INPUTS = (
    "subset_rows",
    "pose_rows",
    "enrichment_rows",
    "vina_gnina_rows",
    "gpcr_rows",
    "pocketmd_rows",
)
DEFAULT_ROW_TEMPLATE_ARTIFACTS = {
    "subset_rows": PRODUCTIZATION / "public_benchmark_subset_rows_template.csv",
    "pose_rows": PRODUCTIZATION / "public_benchmark_pose_rows_template.csv",
    "enrichment_rows": PRODUCTIZATION / "public_benchmark_enrichment_rows_template.csv",
    "vina_gnina_rows": PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template.csv",
    "gpcr_rows": PRODUCTIZATION / "gpcr_hard_decoy_rows_template.csv",
    "pocketmd_rows": PRODUCTIZATION / "pocketmd_lite_topk_rows_template.csv",
}
FIELD_GROUP_KEYS = (
    "required_case_fields",
    "required_context_fields",
    "required_pose_fields",
    "required_flat_row_fields",
    "required_target_fields",
    "required_molecule_fields",
    "required_engine_run_fields",
    "required_component_metrics",
    "required_summary_metrics",
    "uncertainty_field_modes",
    "source_receipt_required_fields",
)
POLICY_KEYS = (
    "row_integrity_policy",
    "source_actuality_policy",
    "source_checksum_policy",
    "numeric_value_policy",
    "boolean_label_policy",
    "boolean_value_policy",
    "score_direction_policy",
    "per_row_source_actuality_policy",
    "top_k_row_quality_minimums",
    "raw_row_quality_minimums",
)
ROW_INPUT_UPSTREAM_SOURCE_IDS = {
    "subset_rows": "public_benchmark_phase2",
    "pose_rows": "public_benchmark_phase2",
    "enrichment_rows": "public_benchmark_phase2",
    "vina_gnina_rows": "public_benchmark_phase2",
    "pocketmd_rows": "pocketmd_lite",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _comma(values: list[Any]) -> str:
    rendered = [str(item) for item in values if str(item)]
    return ", ".join(rendered) if rendered else ""


def _code_join(values: list[Any]) -> str:
    rendered = [f"`{str(item)}`" for item in values if str(item)]
    return ", ".join(rendered) if rendered else "`none`"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _contract_field_groups(contract: dict[str, Any]) -> dict[str, Any]:
    return {key: contract[key] for key in FIELD_GROUP_KEYS if key in contract}


def _contract_policies(contract: dict[str, Any]) -> dict[str, Any]:
    return {key: contract[key] for key in POLICY_KEYS if key in contract}


def _first_default_path(row: dict[str, Any]) -> str:
    candidates = [str(item) for item in _as_list(row.get("default_row_path_candidates"))]
    return candidates[0] if candidates else ""


def _operator_action(row: dict[str, Any]) -> str:
    row_input_id = str(row.get("row_input_id") or "")
    if bool(row.get("missing")):
        default_path = _first_default_path(row)
        if default_path:
            return f"attach_{row_input_id}_at_{default_path}"
        return f"attach_{row_input_id}"
    return f"review_{row_input_id}_materialization"


def _row_template_artifact(row_input_id: str) -> str:
    raw_path = DEFAULT_ROW_TEMPLATE_ARTIFACTS.get(row_input_id)
    return str(raw_path) if raw_path else ""


def _slot_source_context(
    row_input_id: str,
    upstream_source_acquisition: dict[str, Any],
) -> dict[str, Any]:
    source_id = ROW_INPUT_UPSTREAM_SOURCE_IDS.get(row_input_id, "")
    if not source_id:
        return {
            "source_id": "",
            "present": False,
            "status": "",
            "artifact": "",
            "contract_pass": None,
            "blocker_count": 0,
            "blockers": [],
            "missing_row_input_action_count": 0,
            "missing_row_input_actions": [],
            "summary": {},
            "operator_action": "",
        }
    source = _as_dict(upstream_source_acquisition.get(source_id))
    blockers = [str(item) for item in _as_list(source.get("blockers"))]
    missing_row_input_actions = [
        row
        for row in _as_list(source.get("missing_row_input_actions"))
        if isinstance(row, dict)
    ]
    phase2_row_closure_matrix = [
        row
        for row in _as_list(source.get("phase2_row_closure_matrix"))
        if isinstance(row, dict)
    ]
    phase2_exit_criteria = [
        row
        for row in _as_list(source.get("phase2_exit_criteria"))
        if isinstance(row, dict)
    ]
    phase4_candidate_slot_matrix = [
        row
        for row in _as_list(source.get("phase4_candidate_slot_matrix"))
        if isinstance(row, dict)
    ]
    phase4_metric_closure_matrix = [
        row
        for row in _as_list(source.get("phase4_metric_closure_matrix"))
        if isinstance(row, dict)
    ]
    vina_gnina_case_input_slot_matrix = [
        row
        for row in _as_list(source.get("vina_gnina_case_input_slot_matrix"))
        if isinstance(row, dict)
    ]
    vina_gnina_engine_run_slot_matrix = [
        row
        for row in _as_list(source.get("vina_gnina_engine_run_slot_matrix"))
        if isinstance(row, dict)
    ]
    source_access_preflight_rows = [
        row
        for row in _as_list(source.get("source_access_preflight_rows"))
        if isinstance(row, dict)
    ]
    return {
        "source_id": source_id,
        "present": bool(source.get("present")),
        "status": str(source.get("status") or ""),
        "artifact": str(source.get("artifact") or ""),
        "contract_pass": source.get("contract_pass"),
        "blocker_count": int(source.get("blocker_count") or len(blockers)),
        "blockers": blockers,
        "missing_row_input_action_count": int(
            source.get("missing_row_input_action_count")
            or len(missing_row_input_actions)
        ),
        "missing_row_input_actions": missing_row_input_actions,
        "phase2_row_closure_matrix_count": int(
            source.get("phase2_row_closure_matrix_count")
            or len(phase2_row_closure_matrix)
        ),
        "phase2_exit_criterion_count": int(
            source.get("phase2_exit_criterion_count")
            or len(phase2_exit_criteria)
        ),
        "source_access_preflight_count": int(
            source.get("source_access_preflight_count")
            or len(source_access_preflight_rows)
        ),
        "source_access_preflight_rows": source_access_preflight_rows,
        "source_access_preflight_receipt_artifact": str(
            source.get("source_access_preflight_receipt_artifact") or ""
        ),
        "source_access_preflight_receipt_markdown_artifact": str(
            source.get("source_access_preflight_receipt_markdown_artifact") or ""
        ),
        "source_access_preflight_receipt_command": str(
            source.get("source_access_preflight_receipt_command") or ""
        ),
        "source_access_network_probe_command": str(
            source.get("source_access_network_probe_command") or ""
        ),
        "source_access_preflight_receipt_summary": _as_dict(
            source.get("source_access_preflight_receipt_summary")
        ),
        "external_receipts_validation_summary": _as_dict(
            source.get("external_receipts_validation_summary")
        ),
        "phase4_candidate_slot_matrix_count": int(
            source.get("phase4_candidate_slot_matrix_count")
            or len(phase4_candidate_slot_matrix)
        ),
        "phase4_missing_candidate_slot_count": int(
            source.get("phase4_missing_candidate_slot_count")
            or sum(1 for row in phase4_candidate_slot_matrix if row.get("missing"))
        ),
        "phase4_metric_closure_matrix_count": int(
            source.get("phase4_metric_closure_matrix_count")
            or len(phase4_metric_closure_matrix)
        ),
        "vina_gnina_case_input_slot_matrix_count": int(
            source.get("vina_gnina_case_input_slot_matrix_count")
            or len(vina_gnina_case_input_slot_matrix)
        ),
        "vina_gnina_blocked_case_input_slot_count": int(
            source.get("vina_gnina_blocked_case_input_slot_count")
            or sum(
                1
                for row in vina_gnina_case_input_slot_matrix
                if row.get("status") != "ready"
            )
        ),
        "vina_gnina_engine_run_slot_matrix_count": int(
            source.get("vina_gnina_engine_run_slot_matrix_count")
            or len(vina_gnina_engine_run_slot_matrix)
        ),
        "vina_gnina_blocked_engine_run_slot_count": int(
            source.get("vina_gnina_blocked_engine_run_slot_count")
            or sum(
                1
                for row in vina_gnina_engine_run_slot_matrix
                if row.get("status") != "ready_for_engine_execution"
            )
        ),
        "vina_gnina_runtime_readiness": _as_dict(
            source.get("vina_gnina_runtime_readiness")
        ),
        "summary": _as_dict(source.get("summary")),
        "operator_action": (
            f"resolve_{source_id}_source_acquisition_blockers"
            if blockers
            else ""
        ),
    }


def _source_acquisition_row_action(
    row_input_id: str,
    source_context: dict[str, Any],
) -> dict[str, Any]:
    for action in _as_list(source_context.get("missing_row_input_actions")):
        if not isinstance(action, dict):
            continue
        if str(action.get("row_input_id") or "") == row_input_id:
            return action
    return {}


def _compact_candidate_slot_status(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": str(row.get("slot_id") or ""),
        "case_id": str(row.get("case_id") or ""),
        "top_k_rank": _as_int(row.get("top_k_rank")),
        "status": str(row.get("status") or ""),
        "missing": bool(row.get("missing")),
        "provided": bool(row.get("provided")),
        "operator_action": str(row.get("operator_action") or ""),
        "expected_rows_artifact": str(row.get("expected_rows_artifact") or ""),
        "required_metric_fields": [
            str(item) for item in _as_list(row.get("required_metric_fields"))
        ],
        "required_receipt_fields": [
            str(item) for item in _as_list(row.get("required_receipt_fields"))
        ],
    }


def _pocketmd_top_k_slot_detail(
    refinement_plan: dict[str, Any],
    *,
    artifact: Path,
) -> dict[str, Any]:
    if not refinement_plan:
        return {}
    candidate_slot_statuses = [
        _compact_candidate_slot_status(row)
        for row in _as_list(refinement_plan.get("candidate_slot_statuses"))
        if isinstance(row, dict)
    ]
    summary = _as_dict(refinement_plan.get("top_k_slot_status_summary"))
    return {
        "artifact": str(artifact),
        "status": str(refinement_plan.get("status") or ""),
        "operator_rows_ready": bool(refinement_plan.get("operator_rows_ready")),
        "expected_rows_artifact": str(
            refinement_plan.get("expected_rows_artifact") or ""
        ),
        "required_candidate_slot_count": _as_int(
            refinement_plan.get("required_candidate_slot_count")
        ),
        "missing_candidate_slot_count": _as_int(
            summary.get("missing_candidate_slot_count")
        ),
        "provided_candidate_slot_count": _as_int(
            summary.get("provided_candidate_slot_count")
        ),
        "top_k_slot_status_summary": summary,
        "candidate_slot_statuses": candidate_slot_statuses,
        "operator_unblock_packet": _as_dict(
            refinement_plan.get("operator_unblock_packet")
        ),
        "first_missing_candidate_slot": _as_dict(
            summary.get("first_missing_candidate_slot")
        ),
        "claim_boundary": str(refinement_plan.get("claim_boundary") or ""),
    }


def _compact_vina_gnina_engine_run_slot(row: dict[str, Any]) -> dict[str, Any]:
    slot_id = (
        f"{row.get('case_id')}_{row.get('engine_id')}_"
        f"{row.get('docking_run_id')}"
    )
    return {
        "slot_id": slot_id,
        "case_id": str(row.get("case_id") or ""),
        "complex_id": str(row.get("complex_id") or ""),
        "engine_id": str(row.get("engine_id") or ""),
        "docking_run_id": str(row.get("docking_run_id") or ""),
        "status": str(row.get("status") or ""),
        "engine_available": bool(row.get("engine_available")),
        "case_inputs_ready": bool(row.get("case_inputs_ready")),
        "docking_box_ready": bool(row.get("docking_box_ready")),
        "blockers": [str(item) for item in _as_list(row.get("blockers"))],
        "operator_actions": [
            action
            for action in (
                f"resolve_vina_gnina_case_inputs_for_{row.get('case_id')}"
                if not bool(row.get("case_inputs_ready"))
                else "",
                f"configure_{row.get('engine_id')}_runtime"
                if not bool(row.get("engine_available"))
                else "",
                f"attach_vina_gnina_adapter_row_for_{row.get('case_id')}_{row.get('engine_id')}",
            )
            if action
        ],
        "expected_predicted_ligand_path_or_pose_ref": str(
            row.get("expected_predicted_ligand_path_or_pose_ref") or ""
        ),
        "expected_engine_config_ref": str(
            row.get("expected_engine_config_ref") or ""
        ),
        "expected_engine_run_provenance_ref": str(
            row.get("expected_engine_run_provenance_ref") or ""
        ),
        "required_adapter_engine_run_fields": [
            str(item)
            for item in _as_list(row.get("required_adapter_engine_run_fields"))
        ],
    }


def _vina_gnina_engine_run_slot_detail(
    runtime_readiness: dict[str, Any],
    *,
    artifact: Path,
) -> dict[str, Any]:
    if not runtime_readiness:
        return {}
    engine_run_slots = [
        _compact_vina_gnina_engine_run_slot(row)
        for row in _as_list(runtime_readiness.get("engine_run_slots"))
        if isinstance(row, dict)
    ]
    blocked_slots = [
        row for row in engine_run_slots if str(row.get("status") or "") != "ready_for_engine_execution"
    ]
    ready_slots = [
        row for row in engine_run_slots if str(row.get("status") or "") == "ready_for_engine_execution"
    ]
    summary = _as_dict(runtime_readiness.get("summary"))
    return {
        "artifact": str(artifact),
        "status": str(runtime_readiness.get("status") or ""),
        "runtime_ready_for_engine_execution": bool(
            runtime_readiness.get("runtime_ready_for_engine_execution")
        ),
        "operator_execution_ready": bool(
            runtime_readiness.get("operator_execution_ready")
        ),
        "adapter_rows_ready": bool(runtime_readiness.get("adapter_rows_ready")),
        "required_engine_run_count": _as_int(
            runtime_readiness.get("required_engine_run_count")
            or summary.get("required_engine_run_count")
        ),
        "ready_engine_run_slot_count": len(ready_slots),
        "blocked_engine_run_slot_count": len(blocked_slots),
        "missing_engine_ids": [
            str(item)
            for item in _as_list(runtime_readiness.get("missing_engine_ids"))
        ],
        "row_candidate_status": _as_dict(
            runtime_readiness.get("row_candidate_status")
        ),
        "operator_unblock_packet": _as_dict(
            runtime_readiness.get("operator_unblock_packet")
        ),
        "engine_run_status_summary": {
            "required_engine_run_count": len(engine_run_slots),
            "ready_engine_run_slot_count": len(ready_slots),
            "blocked_engine_run_slot_count": len(blocked_slots),
            "first_blocked_engine_run_slot": blocked_slots[0] if blocked_slots else {},
            "first_ready_engine_run_slot": ready_slots[0] if ready_slots else {},
        },
        "engine_run_slots": engine_run_slots,
        "claim_boundary": str(runtime_readiness.get("claim_boundary") or ""),
    }


def _compact_gpcr_target_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": str(row.get("target_id") or ""),
        "status": str(row.get("status") or ""),
        "contract_pass": bool(row.get("contract_pass")),
        "ranking_pr_auc_ci_low": row.get("ranking_pr_auc_ci_low"),
        "top20_hit_rate": row.get("top20_hit_rate"),
        "decoys_above_positive_count": row.get("decoys_above_positive_count"),
        "positive_out_anchored_by_top_decoys": bool(
            row.get("positive_out_anchored_by_top_decoys")
        ),
        "criteria": _as_dict(row.get("criteria")),
        "blockers": [str(item) for item in _as_list(row.get("blockers"))],
    }


def _compact_gpcr_phase3_criterion(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "criterion_id": str(row.get("criterion_id") or ""),
        "required": row.get("required"),
        "pass": bool(row.get("pass")),
        "current_by_target": _as_dict(row.get("current_by_target")),
        "failed_targets": [
            str(item) for item in _as_list(row.get("failed_targets"))
        ],
        "blockers": [str(item) for item in _as_list(row.get("blockers"))],
    }


def _gpcr_phase3_slot_detail(
    suite_report: dict[str, Any],
    *,
    artifact: Path,
) -> dict[str, Any]:
    if not suite_report:
        return {}
    summary = _as_dict(suite_report.get("summary"))
    phase3_exit_gate = _as_dict(suite_report.get("phase3_exit_gate"))
    target_rows = [
        _compact_gpcr_target_row(row)
        for row in _as_list(suite_report.get("target_rows"))
        if isinstance(row, dict)
    ]
    criteria = [
        _compact_gpcr_phase3_criterion(row)
        for row in _as_list(phase3_exit_gate.get("criteria"))
        if isinstance(row, dict)
    ]
    return {
        "artifact": str(artifact),
        "status": str(suite_report.get("status") or ""),
        "contract_pass": bool(suite_report.get("contract_pass")),
        "actual_closure_ready": bool(summary.get("actual_closure_ready")),
        "phase3_exit_gate_status": str(
            summary.get("phase3_exit_gate_status")
            or phase3_exit_gate.get("status")
            or ""
        ),
        "phase3_failed_criteria": [
            str(item)
            for item in _as_list(
                summary.get("phase3_failed_criteria")
                or phase3_exit_gate.get("failed_criteria")
            )
        ],
        "target_count": _as_int(
            summary.get("target_count") or phase3_exit_gate.get("target_count")
        ),
        "target_pass_count": _as_int(
            summary.get("target_pass_count")
            or phase3_exit_gate.get("target_pass_count")
        ),
        "exit_criteria": _as_dict(suite_report.get("exit_criteria")),
        "criteria_pass": _as_dict(summary.get("criteria_pass")),
        "observed_threshold_metrics": {
            "ranking_pr_auc_ci_low_min_observed": summary.get(
                "ranking_pr_auc_ci_low_min_observed"
            ),
            "top20_hit_rate_min_observed": summary.get(
                "top20_hit_rate_min_observed"
            ),
            "decoys_above_positive_count_max_observed": summary.get(
                "decoys_above_positive_count_max_observed"
            ),
            "positive_out_anchored_target_count": summary.get(
                "positive_out_anchored_target_count"
            ),
        },
        "phase3_exit_gate_criteria": criteria,
        "target_rows": target_rows,
        "claim_boundary": str(suite_report.get("claim_boundary") or ""),
    }


def _slot(
    row: dict[str, Any],
    contract: dict[str, Any],
    *,
    repo_root: Path,
    upstream_source_acquisition: dict[str, Any],
    row_input_slot_details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    row_input_id = str(row.get("row_input_id") or "")
    missing = bool(row.get("missing"))
    source_context = _slot_source_context(row_input_id, upstream_source_acquisition)
    source_acquisition_row_action = _source_acquisition_row_action(
        row_input_id,
        source_context,
    )
    row_input_slot_detail = _as_dict(row_input_slot_details.get(row_input_id))
    row_template_artifact = _row_template_artifact(row_input_id)
    row_template_path = (
        repo_root / row_template_artifact if row_template_artifact else Path()
    )
    materialization_chain = [
        str(item) for item in _as_list(row.get("materialization_chain"))
    ]
    materialization_command = str(contract.get("materialization_command") or "")
    if not materialization_command:
        materialization_command = (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--fail-blocked"
        )
    return {
        "handoff_id": f"science_actual_closure::{row_input_id}",
        "row_input_id": row_input_id,
        "description": str(row.get("description") or ""),
        "status": "operator_input_required" if missing else "provided",
        "missing": missing,
        "operator_action": _operator_action(row),
        "row_template_artifact": row_template_artifact,
        "row_template_present": bool(
            row_template_artifact and row_template_path.exists()
        ),
        "preferred_default_row_path": _first_default_path(row),
        "default_row_path_candidates": [
            str(item) for item in _as_list(row.get("default_row_path_candidates"))
        ],
        "accepted_formats": [str(item) for item in _as_list(row.get("accepted_formats"))],
        "provided_path": str(row.get("provided_path") or ""),
        "resolved_path": str(row.get("resolved_path") or ""),
        "actual_closure_component_id": str(
            row.get("actual_closure_component_id") or ""
        ),
        "expected_rows_mode": str(row.get("expected_rows_mode") or ""),
        "closes_actual_closure_criteria": [
            str(item) for item in _as_list(row.get("closes_actual_closure_criteria"))
        ],
        "closes_phase2_criteria": [
            str(item) for item in _as_list(row.get("closes_phase2_criteria"))
        ],
        "operator_blockers_if_missing": [
            str(item) for item in _as_list(row.get("operator_blockers_if_missing"))
        ],
        "phase2_operator_blockers_if_missing": [
            str(item)
            for item in _as_list(row.get("phase2_operator_blockers_if_missing"))
        ],
        "upstream_source_id": source_context["source_id"],
        "upstream_source_acquisition": source_context,
        "upstream_source_blockers": source_context["blockers"],
        "source_acquisition_operator_action": source_context["operator_action"],
        "source_acquisition_row_action": source_acquisition_row_action,
        "row_input_slot_detail": row_input_slot_detail,
        "row_contract_ref": str(row.get("row_contract_ref") or ""),
        "contract_field_groups": _contract_field_groups(contract),
        "contract_policies": _contract_policies(contract),
        "materialization_chain": materialization_chain,
        "materialization_command": materialization_command,
        "claim_boundary": (
            "This slot records what operator-attached row evidence is needed. "
            "It does not close the science gate until the materializer accepts "
            "the real rows and the source receipt."
        ),
    }


def _slot_order(slot: dict[str, Any]) -> int:
    row_input_id = str(slot.get("row_input_id") or "")
    try:
        return EXPECTED_ROW_INPUTS.index(row_input_id)
    except ValueError:
        return len(EXPECTED_ROW_INPUTS)


def _component_slot_summary(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    component_ids = sorted(
        {
            str(slot.get("actual_closure_component_id") or "")
            for slot in slots
            if str(slot.get("actual_closure_component_id") or "")
        }
    )
    summaries: list[dict[str, Any]] = []
    for component_id in component_ids:
        component_slots = [
            slot
            for slot in slots
            if str(slot.get("actual_closure_component_id") or "") == component_id
        ]
        missing_slots = [slot for slot in component_slots if bool(slot.get("missing"))]
        criteria = []
        for slot in component_slots:
            criteria.extend(
                str(item)
                for item in _as_list(slot.get("closes_actual_closure_criteria"))
            )
        summaries.append(
            {
                "component_id": component_id,
                "slot_count": len(component_slots),
                "missing_slot_count": len(missing_slots),
                "row_input_ids": [
                    str(slot.get("row_input_id") or "") for slot in component_slots
                ],
                "missing_row_input_ids": [
                    str(slot.get("row_input_id") or "") for slot in missing_slots
                ],
                "closes_actual_closure_criteria": sorted(set(criteria)),
            }
        )
    return summaries


def _row_input_materialization_contracts(
    missing_slots: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for slot in missing_slots:
        row_input_id = str(slot.get("row_input_id") or "")
        if not row_input_id:
            continue
        contracts[row_input_id] = {
            "row_input_id": row_input_id,
            "status": str(slot.get("status") or ""),
            "operator_action": str(slot.get("operator_action") or ""),
            "preferred_default_row_path": str(
                slot.get("preferred_default_row_path") or ""
            ),
            "default_row_path_candidates": [
                str(item) for item in _as_list(slot.get("default_row_path_candidates"))
            ],
            "row_template_artifact": str(slot.get("row_template_artifact") or ""),
            "row_template_present": bool(slot.get("row_template_present")),
            "accepted_formats": [
                str(item) for item in _as_list(slot.get("accepted_formats"))
            ],
            "actual_closure_component_id": str(
                slot.get("actual_closure_component_id") or ""
            ),
            "expected_rows_mode": str(slot.get("expected_rows_mode") or ""),
            "materialization_chain": [
                str(item) for item in _as_list(slot.get("materialization_chain"))
            ],
            "materialization_command": str(
                slot.get("materialization_command") or ""
            ),
            "contract_field_groups": _as_dict(slot.get("contract_field_groups")),
            "contract_policies": _as_dict(slot.get("contract_policies")),
            "upstream_source_id": str(slot.get("upstream_source_id") or ""),
            "upstream_source_blockers": [
                str(item) for item in _as_list(slot.get("upstream_source_blockers"))
            ],
            "source_acquisition_operator_action": str(
                slot.get("source_acquisition_operator_action") or ""
            ),
            "row_input_slot_detail": _as_dict(
                slot.get("row_input_slot_detail")
            ),
            "operator_blockers_if_missing": [
                str(item)
                for item in _as_list(slot.get("operator_blockers_if_missing"))
            ],
            "claim_boundary": str(slot.get("claim_boundary") or ""),
        }
    return contracts


def _operator_rows_packet(missing_slots: list[dict[str, Any]]) -> dict[str, Any]:
    contracts = _row_input_materialization_contracts(missing_slots)
    missing_row_inputs = [str(slot.get("row_input_id") or "") for slot in missing_slots]
    return {
        "status": "operator_rows_required" if missing_slots else "ready",
        "missing_row_input_count": len(missing_slots),
        "missing_row_inputs": missing_row_inputs,
        "first_missing_row_input": missing_row_inputs[0] if missing_row_inputs else "",
        "row_input_materialization_contracts": contracts,
        "row_input_contract_count": len(contracts),
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--fail-blocked"
        ),
        "claim_boundary": (
            "This packet summarizes missing operator row inputs only. It does not "
            "promote any science closure until the referenced materializers accept "
            "real rows and source receipts."
        ),
    }


def _blocked_component_operator_actions(
    slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for summary in _component_slot_summary(slots):
        missing_ids = [
            str(item) for item in _as_list(summary.get("missing_row_input_ids"))
        ]
        if not missing_ids:
            continue
        component_slots = [
            slot
            for slot in slots
            if str(slot.get("actual_closure_component_id") or "")
            == str(summary.get("component_id") or "")
            and bool(slot.get("missing"))
        ]
        missing_row_input_actions = [
            {
                "row_input_id": str(slot.get("row_input_id") or ""),
                "operator_action": str(slot.get("operator_action") or ""),
                "preferred_default_row_path": str(
                    slot.get("preferred_default_row_path") or ""
                ),
                "row_template_artifact": str(slot.get("row_template_artifact") or ""),
                "materialization_command": str(
                    slot.get("materialization_command") or ""
                ),
                "source_acquisition_operator_action": str(
                    slot.get("source_acquisition_operator_action") or ""
                ),
                "source_acquisition_row_action": _as_dict(
                    slot.get("source_acquisition_row_action")
                ),
                "upstream_source_blockers": [
                    str(item) for item in _as_list(slot.get("upstream_source_blockers"))
                ],
                "operator_blockers_if_missing": [
                    str(item)
                    for item in _as_list(slot.get("operator_blockers_if_missing"))
                ],
            }
            for slot in component_slots
        ]
        rows.append(
            {
                "component_id": str(summary.get("component_id") or ""),
                "missing_row_input_ids": missing_ids,
                "operator_actions": [
                    str(slot.get("operator_action") or "") for slot in component_slots
                ],
                "missing_row_input_actions": missing_row_input_actions,
                "missing_row_input_action_count": len(missing_row_input_actions),
                "source_acquisition_operator_actions": sorted(
                    {
                        str(slot.get("source_acquisition_operator_action") or "")
                        for slot in component_slots
                        if str(slot.get("source_acquisition_operator_action") or "")
                    }
                ),
                "closes_actual_closure_criteria": [
                    str(item)
                    for item in _as_list(
                        summary.get("closes_actual_closure_criteria")
                    )
                ],
            }
        )
    return rows


def build_science_actual_closure_operator_handoff(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    audit = _load_json(repo_root, audit_path)
    row_matrix = [
        row
        for row in _as_list(audit.get("row_closure_matrix"))
        if isinstance(row, dict)
    ]
    contracts = _as_dict(audit.get("row_intake_contracts"))
    upstream_source_acquisition = _as_dict(audit.get("upstream_source_acquisition"))
    science_actual_closure_blockers = [
        str(item) for item in _as_list(audit.get("blockers"))
    ]
    upstream_source_blockers = [
        str(item) for item in _as_list(audit.get("upstream_source_blockers"))
    ]
    blockers = list(
        dict.fromkeys(
            [
                *(f"science_actual_closure::{item}" for item in science_actual_closure_blockers),
                *upstream_source_blockers,
            ]
        )
    )
    pocketmd_refinement_plan = _load_json(
        repo_root,
        DEFAULT_POCKETMD_REFINEMENT_PLAN,
    )
    vina_gnina_runtime_readiness = _load_json(
        repo_root,
        DEFAULT_VINA_GNINA_RUNTIME_READINESS,
    )
    gpcr_suite_report = _load_json(repo_root, DEFAULT_GPCR_SUITE_REPORT)
    row_input_slot_details = {
        "gpcr_rows": _gpcr_phase3_slot_detail(
            gpcr_suite_report,
            artifact=DEFAULT_GPCR_SUITE_REPORT,
        ),
        "pocketmd_rows": _pocketmd_top_k_slot_detail(
            pocketmd_refinement_plan,
            artifact=DEFAULT_POCKETMD_REFINEMENT_PLAN,
        ),
        "vina_gnina_rows": _vina_gnina_engine_run_slot_detail(
            vina_gnina_runtime_readiness,
            artifact=DEFAULT_VINA_GNINA_RUNTIME_READINESS,
        ),
    }
    slots = sorted(
        [
            _slot(
                row,
                _as_dict(contracts.get(str(row.get("row_input_id") or ""))),
                repo_root=repo_root,
                upstream_source_acquisition=upstream_source_acquisition,
                row_input_slot_details=row_input_slot_details,
            )
            for row in row_matrix
        ],
        key=_slot_order,
    )
    missing_slots = [slot for slot in slots if bool(slot.get("missing"))]
    science_contract_pass = bool(audit.get("contract_pass"))
    if science_contract_pass:
        status = "ready_for_review"
    elif missing_slots:
        status = "operator_rows_required"
    else:
        status = "row_blockers_require_resolution"

    criteria = []
    for slot in slots:
        criteria.extend(
            str(item)
            for item in _as_list(slot.get("closes_actual_closure_criteria"))
        )
    handoff_contract_pass = bool(slots) and not set(EXPECTED_ROW_INPUTS).difference(
        str(slot.get("row_input_id") or "") for slot in slots
    )
    row_template_artifacts = {
        str(slot.get("row_input_id") or ""): str(slot.get("row_template_artifact") or "")
        for slot in slots
        if str(slot.get("row_template_artifact") or "")
    }
    missing_row_template_artifacts = [
        str(slot.get("row_input_id") or "")
        for slot in slots
        if not bool(slot.get("row_template_present"))
    ]
    row_input_materialization_contracts = _row_input_materialization_contracts(
        missing_slots
    )
    operator_rows_packet = _operator_rows_packet(missing_slots)
    blocked_component_operator_actions = _blocked_component_operator_actions(slots)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_science_actual_closure_operator_handoff.py"),
                audit_path,
                DEFAULT_POCKETMD_REFINEMENT_PLAN,
                DEFAULT_VINA_GNINA_RUNTIME_READINESS,
                DEFAULT_GPCR_SUITE_REPORT,
            ],
            reused_evidence=True,
            reuse_policy=(
                "science_actual_closure_operator_handoff_from_row_audit"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": handoff_contract_pass,
        "science_actual_closure_contract_pass": science_contract_pass,
        "science_actual_closure_status": str(audit.get("status") or ""),
        "audit_artifact": str(audit_path),
        "summary": {
            "slot_count": len(slots),
            "expected_slot_count": len(EXPECTED_ROW_INPUTS),
            "missing_slot_count": len(missing_slots),
            "provided_slot_count": len(slots) - len(missing_slots),
            "component_count": len(_component_slot_summary(slots)),
            "closes_actual_closure_criteria_count": len(set(criteria)),
            "science_actual_closure_blocker_count": len(
                science_actual_closure_blockers
            ),
            "row_template_artifact_count": len(row_template_artifacts),
            "missing_row_template_artifact_count": len(
                missing_row_template_artifacts
            ),
            "upstream_source_context_count": sum(
                1
                for source in upstream_source_acquisition.values()
                if _as_dict(source).get("present")
            ),
            "upstream_source_blocker_count": len(upstream_source_blockers),
            "operator_rows_packet_missing_input_count": operator_rows_packet[
                "missing_row_input_count"
            ],
            "blocked_component_operator_action_count": len(
                blocked_component_operator_actions
            ),
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "blocker_count": len(blockers),
        "science_actual_closure_blockers": science_actual_closure_blockers,
        "upstream_source_acquisition": upstream_source_acquisition,
        "upstream_source_blockers": upstream_source_blockers,
        "row_template_artifacts": row_template_artifacts,
        "missing_row_template_artifacts": missing_row_template_artifacts,
        "missing_row_inputs": [
            str(slot.get("row_input_id") or "") for slot in missing_slots
        ],
        "row_input_materialization_contracts": row_input_materialization_contracts,
        "operator_rows_packet": operator_rows_packet,
        "blocked_component_operator_actions": blocked_component_operator_actions,
        "first_missing_slot": missing_slots[0] if missing_slots else {},
        "operator_next_actions": [
            str(item) for item in _as_list(audit.get("operator_next_actions"))
        ],
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--fail-blocked"
        ),
        "required_actual_closures": [
            str(item) for item in _as_list(audit.get("required_actual_closures"))
        ],
        "component_slot_summary": _component_slot_summary(slots),
        "row_slot_handoffs": slots,
        "row_slot_handoff_count": len(slots),
        "claim_boundary": (
            "This handoff is an operator checklist derived from the science row "
            "audit. It is not actual science evidence and does not close Phase 2, "
            "GPCR hard-decoy, or PocketMD Lite gates without accepted real rows."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = _as_dict(payload.get("summary"))
    lines = [
        "# Science Actual Closure Operator Handoff",
        "",
        f"- `status`: `{payload.get('status')}`",
        f"- `contract_pass`: `{payload.get('contract_pass')}`",
        "- `science_actual_closure_contract_pass`: "
        f"`{payload.get('science_actual_closure_contract_pass')}`",
        f"- `missing_slot_count`: `{summary.get('missing_slot_count')}`",
        f"- `slot_count`: `{summary.get('slot_count')}`",
        f"- `blocker_count`: `{payload.get('blocker_count')}`",
        "",
        "| Row Input | Status | Preferred Path | CSV Starter | Closes Criteria | Action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for slot in _as_list(payload.get("row_slot_handoffs")):
        if not isinstance(slot, dict):
            continue
        criteria = ", ".join(
            str(item) for item in _as_list(slot.get("closes_actual_closure_criteria"))
        )
        lines.append(
            "| "
            f"`{slot.get('row_input_id')}` | "
            f"`{slot.get('status')}` | "
            f"`{slot.get('preferred_default_row_path')}` | "
            f"`{slot.get('row_template_artifact')}` | "
            f"`{criteria}` | "
            f"`{slot.get('operator_action')}` |"
        )
    operator_rows_packet = _as_dict(payload.get("operator_rows_packet"))
    packet_contracts = _as_dict(
        operator_rows_packet.get("row_input_materialization_contracts")
    )
    if packet_contracts:
        lines.extend(["", "## Missing Row Packet", ""])
        lines.extend(
            [
                "| Row Input | Action | Template | Materialization |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row_input_id, contract in packet_contracts.items():
            if not isinstance(contract, dict):
                continue
            lines.append(
                "| "
                f"`{row_input_id}` | "
                f"`{contract.get('operator_action')}` | "
                f"`{contract.get('row_template_artifact')}` | "
                f"`{contract.get('materialization_command')}` |"
            )
            row_input_detail = _as_dict(contract.get("row_input_slot_detail"))
            top_k_summary = _as_dict(
                row_input_detail.get("top_k_slot_status_summary")
            )
            missing_candidate_slots = [
                item
                for item in _as_list(top_k_summary.get("missing_candidate_slots"))
                if isinstance(item, dict)
            ]
            if missing_candidate_slots:
                operator_unblock = _as_dict(
                    row_input_detail.get("operator_unblock_packet")
                )
                lines.extend(["", "### PocketMD Top-k Candidate Slots", ""])
                if operator_unblock:
                    lines.extend(
                        [
                            f"- `operator_unblock_status`: `{operator_unblock.get('status')}`",
                            f"- `row_template_artifact`: `{operator_unblock.get('row_template_artifact')}`",
                        ]
                    )
                lines.extend(
                    [
                        "| Slot | Case | Rank | Status | Action |",
                        "| --- | --- | --- | --- | --- |",
                    ]
                )
                for candidate_slot in missing_candidate_slots:
                    lines.append(
                        "| "
                        f"`{candidate_slot.get('slot_id')}` | "
                        f"`{candidate_slot.get('case_id')}` | "
                        f"`{candidate_slot.get('top_k_rank')}` | "
                        "`missing` | "
                        f"`{candidate_slot.get('operator_action')}` |"
                    )
            engine_run_detail = _as_dict(contract.get("row_input_slot_detail"))
            engine_run_summary = _as_dict(
                engine_run_detail.get("engine_run_status_summary")
            )
            blocked_engine_run_slots = [
                item
                for item in _as_list(engine_run_detail.get("engine_run_slots"))
                if isinstance(item, dict)
                and str(item.get("status") or "") != "ready_for_engine_execution"
            ]
            if blocked_engine_run_slots:
                operator_unblock = _as_dict(
                    engine_run_detail.get("operator_unblock_packet")
                )
                lines.extend(["", "### Vina/GNINA Engine Run Slots", ""])
                lines.append(
                    f"- `blocked_engine_run_slot_count`: "
                    f"`{engine_run_summary.get('blocked_engine_run_slot_count')}`"
                )
                if operator_unblock:
                    lines.extend(
                        [
                            f"- `operator_unblock_status`: `{operator_unblock.get('status')}`",
                            f"- `input_manifest_template_artifact`: `{operator_unblock.get('input_manifest_template_artifact')}`",
                            "- `input_manifest_template_preflight_artifact`: "
                            f"`{operator_unblock.get('input_manifest_template_preflight_artifact')}`",
                            "- `input_manifest_template_preflight_command`: "
                            f"`{_as_dict(operator_unblock.get('commands')).get('build_input_manifest_template_preflight', '')}`",
                        ]
                    )
                lines.extend(
                    [
                        "",
                        "| Slot | Case | Engine | Status | Actions |",
                        "| --- | --- | --- | --- | --- |",
                    ]
                )
                for engine_slot in blocked_engine_run_slots:
                    actions = ", ".join(
                        str(item)
                        for item in _as_list(engine_slot.get("operator_actions"))
                    )
                    lines.append(
                        "| "
                        f"`{engine_slot.get('slot_id')}` | "
                        f"`{engine_slot.get('case_id')}` | "
                        f"`{engine_slot.get('engine_id')}` | "
                        f"`{engine_slot.get('status')}` | "
                        f"`{actions}` |"
                    )
    blocked_component_actions = [
        row
        for row in _as_list(payload.get("blocked_component_operator_actions"))
        if isinstance(row, dict)
    ]
    if blocked_component_actions:
        lines.extend(["", "## Blocked Component Actions", ""])
        lines.extend(
            [
                "| Component | Row Input | Action | Default Artifact | Source Action | Source Row Action | Source Command | Required Receipts | Source Phase 2 Criteria | Source Phase 4 Criteria |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for component in blocked_component_actions:
            for action in _as_list(component.get("missing_row_input_actions")):
                if not isinstance(action, dict):
                    continue
                source_action = _as_dict(action.get("source_acquisition_row_action"))
                source_commands = _as_dict(source_action.get("commands"))
                source_command = (
                    str(source_action.get("runtime_readiness_command") or "")
                    or str(source_commands.get("import_rows") or "")
                    or str(source_action.get("materialization_command") or "")
                    or str(source_commands.get("materialize_survival") or "")
                    or str(source_commands.get("science_actual_closure") or "")
                )
                required_receipts = _comma(
                    [
                        *_as_list(source_action.get("receipt_fields")),
                        *_as_list(source_action.get("required_receipt_roles")),
                    ]
                )
                source_phase2_criteria = _comma(
                    _as_list(source_action.get("closes_phase2_criteria"))
                )
                source_phase4_criteria = _comma(
                    _as_list(source_action.get("closes_phase4_criteria"))
                )
                lines.append(
                    "| "
                    f"`{component.get('component_id')}` | "
                    f"`{action.get('row_input_id')}` | "
                    f"`{action.get('operator_action')}` | "
                    f"`{action.get('preferred_default_row_path')}` | "
                    f"`{action.get('source_acquisition_operator_action')}` | "
                    f"`{source_action.get('operator_action') or ''}` | "
                    f"`{source_command}` | "
                    f"`{required_receipts}` | "
                    f"`{source_phase2_criteria}` | "
                    f"`{source_phase4_criteria}` |"
                )
        detailed_actions: list[dict[str, Any]] = []
        for component in blocked_component_actions:
            for action in _as_list(component.get("missing_row_input_actions")):
                if not isinstance(action, dict):
                    continue
                source_action = _as_dict(action.get("source_acquisition_row_action"))
                manifest_action = _as_dict(
                    source_action.get("engine_input_manifest_action_packet")
                )
                if manifest_action:
                    detailed_actions.append(
                        {
                            "kind": "vina_gnina_manifest",
                            "component_id": str(component.get("component_id") or ""),
                            "row_input_id": str(action.get("row_input_id") or ""),
                            "action": manifest_action,
                        }
                    )
                adapter_preflight_action = _as_dict(
                    source_action.get("adapter_row_preflight_action_packet")
                )
                if adapter_preflight_action:
                    detailed_actions.append(
                        {
                            "kind": "vina_gnina_adapter_preflight",
                            "component_id": str(component.get("component_id") or ""),
                            "row_input_id": str(action.get("row_input_id") or ""),
                            "action": adapter_preflight_action,
                        }
                    )
                top_k_action = _as_dict(
                    source_action.get("top_k_rows_action_packet")
                )
                pocketmd_row_preflight_action = _as_dict(
                    source_action.get("row_preflight_action_packet")
                )
                if pocketmd_row_preflight_action:
                    detailed_actions.append(
                        {
                            "kind": "pocketmd_row_preflight",
                            "component_id": str(component.get("component_id") or ""),
                            "row_input_id": str(action.get("row_input_id") or ""),
                            "action": pocketmd_row_preflight_action,
                        }
                    )
                if top_k_action:
                    detailed_actions.append(
                        {
                            "kind": "pocketmd_top_k_rows",
                            "component_id": str(component.get("component_id") or ""),
                            "row_input_id": str(action.get("row_input_id") or ""),
                            "action": top_k_action,
                        }
                    )
        for detail in detailed_actions:
            action = _as_dict(detail.get("action"))
            safety_policy = _as_dict(action.get("template_safety_policy"))
            if detail.get("kind") == "vina_gnina_manifest":
                lines.extend(["", "### Vina/GNINA Input Manifest Action", ""])
                manifest_load_errors = [
                    f"{row.get('path')}: {row.get('load_error')}"
                    for row in _as_list(action.get("input_manifest_load_errors"))
                    if isinstance(row, dict) and str(row.get("load_error") or "")
                ]
                lines.extend(
                    [
                        f"- `component_id`: `{detail.get('component_id')}`",
                        f"- `row_input_id`: `{detail.get('row_input_id')}`",
                        f"- `status`: `{action.get('status')}`",
                        f"- `template_artifact`: `{action.get('template_artifact')}`",
                        f"- `expected_manifest_artifact`: `{action.get('expected_manifest_artifact')}`",
                        f"- `default_execution_plan_manifest_path`: `{action.get('default_execution_plan_manifest_path')}`",
                        f"- `recommended_template_dropzone`: `{action.get('recommended_template_dropzone')}`",
                        f"- `recommended_template_dropzone_is_supported_candidate_path`: `{action.get('recommended_template_dropzone_is_supported_candidate_path')}`",
                        f"- `accepted_manifest_formats`: {_code_join(_as_list(action.get('accepted_manifest_formats')))}",
                        f"- `supported_manifest_candidate_paths`: {_code_join(_as_list(action.get('supported_manifest_candidate_paths')))}",
                        f"- `detected_manifest_artifact_count`: `{action.get('detected_manifest_artifact_count')}`",
                        f"- `selected_manifest_path`: `{action.get('selected_manifest_path')}`",
                        f"- `selected_manifest_format`: `{action.get('selected_manifest_format')}`",
                        f"- `input_manifest_row_count`: `{action.get('input_manifest_row_count')}`",
                        f"- `input_manifest_load_errors`: {_code_join(manifest_load_errors)}",
                        f"- `template_to_manifest_command`: `{action.get('template_to_manifest_command')}`",
                        f"- `verify_execution_plan_command`: `{action.get('verify_execution_plan_command')}`",
                        f"- `verify_runtime_readiness_command`: `{action.get('verify_runtime_readiness_command')}`",
                        f"- `operator_must_fill_or_verify`: {_code_join(_as_list(action.get('operator_must_fill_or_verify')))}",
                        f"- `template_is_not_evidence`: `{safety_policy.get('template_is_not_evidence')}`",
                        f"- `do_not_treat_blank_prepared_checksums_as_ready`: `{safety_policy.get('do_not_treat_blank_prepared_checksums_as_ready')}`",
                    ]
                )
            elif detail.get("kind") == "vina_gnina_adapter_preflight":
                lines.extend(["", "### Vina/GNINA Adapter Row Preflight Action", ""])
                lines.extend(
                    [
                        f"- `component_id`: `{detail.get('component_id')}`",
                        f"- `row_input_id`: `{detail.get('row_input_id')}`",
                        f"- `status`: `{action.get('status')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `supported_candidate_paths`: {_code_join(_as_list(action.get('supported_candidate_paths')))}",
                        f"- `detected_row_artifact_count`: `{action.get('detected_row_artifact_count')}`",
                        f"- `selected_path`: `{action.get('selected_path')}`",
                        f"- `adapter_preflight_status`: `{action.get('adapter_preflight_status')}`",
                        f"- `adapter_preflight_blockers`: {_code_join(_as_list(action.get('adapter_preflight_blockers')))}",
                        f"- `direct_adapter_materialization_command`: `{action.get('direct_adapter_materialization_command')}`",
                        f"- `operator_rows_must_be_real_engine_outputs`: `{safety_policy.get('operator_rows_must_be_real_engine_outputs')}`",
                        f"- `preflight_does_not_run_engines`: `{safety_policy.get('preflight_does_not_run_engines')}`",
                    ]
                )
            elif detail.get("kind") == "pocketmd_row_preflight":
                lines.extend(["", "### PocketMD Row Preflight Action", ""])
                lines.extend(
                    [
                        f"- `component_id`: `{detail.get('component_id')}`",
                        f"- `row_input_id`: `{detail.get('row_input_id')}`",
                        f"- `status`: `{action.get('status')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `supported_candidate_paths`: {_code_join(_as_list(action.get('supported_candidate_paths')))}",
                        f"- `detected_row_artifact_count`: `{action.get('detected_row_artifact_count')}`",
                        f"- `selected_path`: `{action.get('selected_path')}`",
                        f"- `validated_row_count`: `{action.get('validated_row_count')}`",
                        f"- `covered_required_slot_count`: `{action.get('covered_required_slot_count')}/{action.get('required_candidate_slot_count')}`",
                        f"- `missing_required_slot_count`: `{len(_as_list(action.get('missing_required_slots')))}`",
                        f"- `validation_error`: `{action.get('validation_error')}`",
                        f"- `blocker`: `{action.get('blocker')}`",
                        f"- `import_rows_command`: `{action.get('import_rows_command')}`",
                        f"- `verify_science_actual_closure_command`: `{action.get('verify_science_actual_closure_command')}`",
                        f"- `operator_rows_must_be_real_top_k_refinement_outputs`: `{safety_policy.get('operator_rows_must_be_real_top_k_refinement_outputs')}`",
                        f"- `preflight_does_not_run_refinement`: `{safety_policy.get('preflight_does_not_run_refinement')}`",
                    ]
                )
            elif detail.get("kind") == "pocketmd_top_k_rows":
                lines.extend(["", "### PocketMD Top-k Rows Action", ""])
                phase4_metric_receipt_actions = [
                    row
                    for row in _as_list(action.get("phase4_metric_receipt_actions"))
                    if isinstance(row, dict)
                ]
                lines.extend(
                    [
                        f"- `component_id`: `{detail.get('component_id')}`",
                        f"- `row_input_id`: `{detail.get('row_input_id')}`",
                        f"- `status`: `{action.get('status')}`",
                        f"- `template_artifact`: `{action.get('template_artifact')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `import_rows_command`: `{action.get('import_rows_command')}`",
                        f"- `materialize_survival_command`: `{action.get('materialize_survival_command')}`",
                        f"- `verify_science_actual_closure_command`: `{action.get('verify_science_actual_closure_command')}`",
                        f"- `operator_must_fill_or_verify`: {_code_join(_as_list(action.get('operator_must_fill_or_verify')))}",
                        f"- `required_receipt_roles`: {_code_join(_as_list(action.get('required_receipt_roles')))}",
                        f"- `phase4_metric_receipt_action_count`: `{action.get('phase4_metric_receipt_action_count')}`",
                        f"- `template_is_not_evidence`: `{safety_policy.get('template_is_not_evidence')}`",
                        f"- `placeholder_or_fixture_rows_do_not_promote`: `{safety_policy.get('placeholder_or_fixture_rows_do_not_promote')}`",
                        f"- `summary_only_metrics_do_not_promote`: `{safety_policy.get('summary_only_metrics_do_not_promote')}`",
                    ]
                )
                if phase4_metric_receipt_actions:
                    lines.extend(
                        [
                            "",
                            "#### PocketMD Phase 4 Receipt Closure Actions",
                            "",
                            "| Criterion | Metric | Receipt Roles | Required Row Fields | Blockers |",
                            "|---|---|---|---|---|",
                        ]
                    )
                    for metric_action in phase4_metric_receipt_actions:
                        lines.append(
                            "| "
                            f"`{metric_action.get('criterion_id', '')}` | "
                            f"`{metric_action.get('metric_id', '')}` | "
                            f"{_code_join(_as_list(metric_action.get('receipt_roles')))} | "
                            f"{_code_join(_as_list(metric_action.get('required_row_fields')))} | "
                            f"{_code_join(_as_list(metric_action.get('blockers')))} |"
                        )
        public_source_context = _as_dict(
            _as_dict(payload.get("upstream_source_acquisition")).get(
                "public_benchmark_phase2"
            )
        )
        source_access_preflight_rows = [
            row
            for row in _as_list(
                public_source_context.get("source_access_preflight_rows")
            )
            if isinstance(row, dict)
        ]
        if source_access_preflight_rows:
            lines.extend(["", "### Public Benchmark Source Access Preflight", ""])
            receipt_artifact = str(
                public_source_context.get(
                    "source_access_preflight_receipt_artifact"
                )
                or ""
            )
            receipt_command = str(
                public_source_context.get(
                    "source_access_preflight_receipt_command"
                )
                or ""
            )
            network_probe_command = str(
                public_source_context.get("source_access_network_probe_command")
                or ""
            )
            receipt_summary = _as_dict(
                public_source_context.get(
                    "source_access_preflight_receipt_summary"
                )
            )
            external_receipts_summary = _as_dict(
                public_source_context.get("external_receipts_validation_summary")
            )
            if receipt_artifact or receipt_command or network_probe_command:
                lines.extend(
                    [
                        f"- `receipt_artifact`: `{receipt_artifact}`",
                        f"- `receipt_command`: `{receipt_command}`",
                        f"- `network_probe_command`: `{network_probe_command}`",
                        "- `receipt_status`: "
                        f"`{receipt_summary.get('status', '')}`",
                        "- `receipt_reachable_count`: "
                        f"`{receipt_summary.get('reachable_count', 0)}`",
                        "- `external_receipts_status`: "
                        f"`{external_receipts_summary.get('status', '')}`",
                        "- `external_receipts_complete_roles`: "
                        f"`{external_receipts_summary.get('receipt_complete_artifact_role_count', 0)}/"
                        f"{external_receipts_summary.get('expected_artifact_role_count', 0)}`",
                        "",
                    ]
                )
            lines.extend(
                [
                    "| Source | Access Mode | Primary Probe |",
                    "| --- | --- | --- |",
                ]
            )
            for row in source_access_preflight_rows:
                lines.append(
                    "| "
                    f"`{row.get('source_id')}` | "
                    f"`{row.get('access_mode')}` | "
                    f"`{row.get('primary_head_command')}` |"
                )
    upstream_source_blockers = [
        str(item) for item in _as_list(payload.get("upstream_source_blockers"))
    ]
    gpcr_slots = [
        slot
        for slot in _as_list(payload.get("row_slot_handoffs"))
        if isinstance(slot, dict) and slot.get("row_input_id") == "gpcr_rows"
    ]
    gpcr_detail = (
        _as_dict(gpcr_slots[0].get("row_input_slot_detail"))
        if gpcr_slots
        else {}
    )
    if gpcr_detail:
        lines.extend(["", "## Provided Closure Evidence", ""])
        lines.extend(
            [
                "### GPCR Phase 3 Gate",
                "",
                f"- `status`: `{gpcr_detail.get('phase3_exit_gate_status')}`",
                f"- `actual_closure_ready`: `{gpcr_detail.get('actual_closure_ready')}`",
                f"- `target_pass_count`: `{gpcr_detail.get('target_pass_count')}/{gpcr_detail.get('target_count')}`",
                "",
                "| Target | PR-AUC CI Low | Top20 Hit Rate | Decoys Above Positive | Out-Anchored | Status |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for target in _as_list(gpcr_detail.get("target_rows")):
            if not isinstance(target, dict):
                continue
            lines.append(
                "| "
                f"`{target.get('target_id')}` | "
                f"`{target.get('ranking_pr_auc_ci_low')}` | "
                f"`{target.get('top20_hit_rate')}` | "
                f"`{target.get('decoys_above_positive_count')}` | "
                f"`{target.get('positive_out_anchored_by_top_decoys')}` | "
                f"`{target.get('status')}` |"
            )
    if upstream_source_blockers:
        lines.extend(["", "## Upstream Source Blockers", ""])
        for blocker in upstream_source_blockers:
            lines.append(f"- `{blocker}`")
    lines.extend(
        [
            "",
            "## Materialization",
            "",
            f"```bash\n{payload.get('materialization_command')}\n```",
            "",
            "## Claim Boundary",
            "",
            str(payload.get("claim_boundary") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-md", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_science_actual_closure_operator_handoff(
        repo_root=args.repo_root,
        audit_path=args.audit,
    )
    out = args.out if args.out.is_absolute() else args.repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    if not args.no_md:
        out_md = (
            args.out_md
            if args.out_md.is_absolute()
            else args.repo_root / args.out_md
        )
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(payload), encoding="utf-8")
    print(
        _json_text(payload).rstrip()
        if args.json
        else (
            "science-actual-closure-operator-handoff: "
            f"{payload['status']} | "
            f"missing={payload['summary']['missing_slot_count']}/"
            f"{payload['summary']['slot_count']}"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
