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
DEFAULT_POCKETMD_TOPK_ROWS_TEMPLATE_PREFLIGHT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_template_preflight.json"
)
DEFAULT_POCKETMD_TOPK_SURVIVAL_REPORT = (
    PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


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
            "operator_next_actions": [],
            "missing_row_input_action_count": 0,
            "missing_row_input_actions": [],
            "summary": {},
            "phase4_completion_audit": {},
            "phase4_actual_evidence_audit": {},
            "vina_gnina_actual_evidence_audit": {},
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
    phase4_completion_audit = _as_dict(source.get("phase4_completion_audit"))
    source_commands = _source_command_lookup(source, missing_row_input_actions)
    phase4_actual_evidence_audit = _compact_actual_evidence_audit(
        _as_dict(source.get("phase4_actual_evidence_audit")),
        commands=source_commands,
    )
    vina_gnina_actual_evidence_audit = _compact_actual_evidence_audit(
        _as_dict(source.get("vina_gnina_actual_evidence_audit")),
        commands=source_commands,
    )
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
        "operator_next_actions": [
            str(item) for item in _as_list(source.get("operator_next_actions"))
        ],
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
        "phase4_completion_audit": phase4_completion_audit,
        "phase4_actual_evidence_audit": phase4_actual_evidence_audit,
        "phase4_actual_evidence_audit_status": str(
            phase4_actual_evidence_audit.get("status") or ""
        ),
        "phase4_actual_evidence_blocked_component_count": _as_int(
            phase4_actual_evidence_audit.get("blocked_component_count")
        ),
        "vina_gnina_actual_evidence_audit": vina_gnina_actual_evidence_audit,
        "vina_gnina_actual_evidence_audit_status": str(
            vina_gnina_actual_evidence_audit.get("status") or ""
        ),
        "vina_gnina_actual_evidence_blocked_component_count": _as_int(
            vina_gnina_actual_evidence_audit.get("blocked_component_count")
        ),
        "phase4_completion_audit_status": str(
            phase4_completion_audit.get("status") or ""
        ),
        "phase4_completion_blocked_requirement_count": _as_int(
            phase4_completion_audit.get("blocked_requirement_count")
        ),
        "phase4_completion_remaining_blockers": [
            str(item)
            for item in _as_list(phase4_completion_audit.get("remaining_blockers"))
            if str(item)
        ],
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


def _compact_input_manifest_completion_action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(row.get("case_id") or ""),
        "complex_id": str(row.get("complex_id") or ""),
        "status": str(row.get("status") or ""),
        "operator_completion_action": str(
            row.get("operator_completion_action") or ""
        ),
        "missing_required_field_count": _as_int(
            row.get("missing_required_field_count")
        ),
        "missing_local_file_count": _as_int(row.get("missing_local_file_count")),
        "missing_receipt_ref_count": _as_int(
            row.get("missing_receipt_ref_count")
        ),
    }


def _omit_repeated_input_manifest_completion_plans(value: Any) -> Any:
    if isinstance(value, list):
        return [
            _omit_repeated_input_manifest_completion_plans(item)
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key == "input_manifest_completion_action_plan":
            action_plan = [row for row in _as_list(item) if isinstance(row, dict)]
            sanitized["input_manifest_completion_action_plan_count"] = len(
                action_plan
            )
            sanitized["input_manifest_completion_action_plan_omitted"] = bool(
                action_plan
            )
            sanitized["first_input_manifest_completion_action"] = (
                _compact_input_manifest_completion_action(action_plan[0])
                if action_plan
                else {}
            )
            continue
        sanitized[key] = _omit_repeated_input_manifest_completion_plans(item)
    return sanitized


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
    template_preflight: dict[str, Any],
    template_preflight_artifact: Path,
    survival_report: dict[str, Any],
    survival_report_artifact: Path,
) -> dict[str, Any]:
    if not refinement_plan:
        return {}
    candidate_slot_statuses = [
        _compact_candidate_slot_status(row)
        for row in _as_list(refinement_plan.get("candidate_slot_statuses"))
        if isinstance(row, dict)
    ]
    summary = _as_dict(refinement_plan.get("top_k_slot_status_summary"))
    template_preflight_summary = _as_dict(template_preflight.get("summary"))
    survival_summary = _as_dict(survival_report.get("summary"))
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
        "row_template_preflight": {
            "artifact": str(template_preflight_artifact),
            "status": str(template_preflight.get("status") or ""),
            "contract_pass": bool(template_preflight.get("contract_pass")),
            "top_k_template_ready": bool(
                template_preflight.get("top_k_template_ready")
            ),
            "template_row_count": _as_int(
                template_preflight_summary.get("template_row_count")
            ),
            "expected_slot_count": _as_int(
                template_preflight_summary.get("expected_slot_count")
            ),
            "missing_required_value_count": _as_int(
                template_preflight_summary.get("missing_required_value_count")
            ),
            "missing_metric_value_count": _as_int(
                template_preflight_summary.get("missing_metric_value_count")
            ),
            "missing_receipt_value_count": _as_int(
                template_preflight_summary.get("missing_receipt_value_count")
            ),
            "expected_rows_detected": bool(
                template_preflight_summary.get("expected_rows_detected")
            ),
            "commands": _as_dict(template_preflight.get("commands")),
            "claim_boundary": str(template_preflight.get("claim_boundary") or ""),
        },
        "survival_report": {
            "artifact": str(survival_report_artifact),
            "status": str(survival_report.get("status") or ""),
            "contract_pass": bool(survival_report.get("contract_pass")),
            "product_surface_ready": bool(
                survival_report.get("product_surface_ready")
            ),
            "first_blocked_target": str(
                survival_report.get("first_blocked_target") or ""
            ),
            "blocker_count": len(_as_list(survival_report.get("blockers"))),
            "blockers": [
                str(item) for item in _as_list(survival_report.get("blockers"))
            ],
            "real_refinement_case_count": _as_int(
                survival_summary.get("real_refinement_case_count")
            ),
            "top_k_candidate_count": _as_int(
                survival_summary.get("top_k_candidate_count")
            ),
            "local_min_survival_rate": survival_summary.get(
                "local_min_survival_rate"
            ),
            "contact_persistence_rate_median": survival_summary.get(
                "contact_persistence_rate_median"
            ),
            "h_bond_persistence_rate_median": survival_summary.get(
                "h_bond_persistence_rate_median"
            ),
            "clash_relief_rate": survival_summary.get("clash_relief_rate"),
            "uncertainty_width_median": survival_summary.get(
                "uncertainty_width_median"
            ),
            "claim_boundary": str(survival_report.get("claim_boundary") or ""),
        },
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
        "runtime_readiness_blocker_count": _as_int(summary.get("blocker_count")),
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
        "operator_unblock_packet": _compact_vina_gnina_operator_unblock_packet(
            _as_dict(runtime_readiness.get("operator_unblock_packet"))
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
        "source_acquisition_operator_next_actions": source_context[
            "operator_next_actions"
        ],
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


def _unblock_plan_artifacts(unblock: dict[str, Any]) -> dict[str, str]:
    artifact_keys = (
        "expected_rows_artifact",
        "expected_operator_intake_artifact",
        "input_manifest_template_artifact",
        "input_manifest_template_preflight_artifact",
        "input_manifest_template_preflight_markdown_artifact",
        "rows_template_artifact",
        "rows_template_preflight_artifact",
        "rows_template_preflight_markdown_artifact",
        "row_template_artifact",
        "row_template_preflight_artifact",
        "row_template_preflight_markdown_artifact",
    )
    return {
        key: str(unblock.get(key) or "")
        for key in artifact_keys
        if str(unblock.get(key) or "")
    }


def _unblock_plan_counts(unblock: dict[str, Any]) -> dict[str, int]:
    count_keys = (
        "case_input_slot_count",
        "blocked_case_input_slot_count",
        "required_engine_run_count",
        "ready_engine_run_slot_count",
        "blocked_engine_run_slot_count",
        "required_candidate_slot_count",
        "provided_candidate_slot_count",
        "missing_candidate_slot_count",
    )
    return {
        key: _as_int(unblock.get(key))
        for key in count_keys
        if key in unblock
    }


def _compact_operator_blocker_family(
    row: dict[str, Any],
    *,
    commands: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not row:
        return {}
    command_key = str(row.get("command_key") or "")
    return {
        "family_id": str(row.get("family_id") or ""),
        "description": str(row.get("description") or ""),
        "status": str(row.get("status") or ""),
        "missing_item_count": _as_int(row.get("missing_item_count")),
        "blocked_case_count": _as_int(row.get("blocked_case_count")),
        "first_missing_item": _as_dict(row.get("first_missing_item")),
        "operator_action": str(row.get("operator_action") or ""),
        "next_action": str(
            row.get("next_action") or row.get("operator_action") or ""
        ),
        "command_key": command_key,
        "materialization_command": str(
            row.get("materialization_command")
            or _as_dict(commands or {}).get(command_key)
            or ""
        ),
    }


def _compact_operator_blocker_family_plan(
    rows: list[Any],
    *,
    commands: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        _compact_operator_blocker_family(row, commands=commands)
        for row in rows
        if isinstance(row, dict)
    ]


def _source_command_lookup(
    source: dict[str, Any],
    missing_row_input_actions: list[dict[str, Any]],
) -> dict[str, str]:
    commands = {
        str(key): str(value)
        for key, value in _as_dict(source.get("commands")).items()
        if str(key) and str(value)
    }
    for action in missing_row_input_actions:
        packets = [
            action,
            _as_dict(action.get("top_k_rows_action_packet")),
            _as_dict(action.get("row_preflight_action_packet")),
            _as_dict(action.get("adapter_row_preflight_action_packet")),
            _as_dict(action.get("engine_input_manifest_action_packet")),
        ]
        for packet in packets:
            for key, value in packet.items():
                key_text = str(key)
                value_text = str(value)
                if not key_text.endswith("_command") or not value_text:
                    continue
                commands.setdefault(
                    key_text.removesuffix("_command"),
                    value_text,
                )
    if (
        "build_row_template_preflight" not in commands
        and "build_template_preflight" in commands
    ):
        commands["build_row_template_preflight"] = commands[
            "build_template_preflight"
        ]
    return commands


def _compact_actual_evidence_audit(
    packet: dict[str, Any],
    *,
    commands: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not packet:
        return {}
    compact = dict(packet)
    compact["first_operator_blocker_family"] = _compact_operator_blocker_family(
        _as_dict(packet.get("first_operator_blocker_family")),
        commands=commands,
    )
    compact["operator_blocker_family_plan"] = _compact_operator_blocker_family_plan(
        _as_list(packet.get("operator_blocker_family_plan")),
        commands=commands,
    )
    return compact


def _compact_vina_gnina_operator_unblock_packet(
    packet: dict[str, Any],
) -> dict[str, Any]:
    if not packet:
        return {}
    compact = dict(packet)
    commands = _as_dict(packet.get("commands"))
    compact["first_operator_blocker_family"] = _compact_operator_blocker_family(
        _as_dict(packet.get("first_operator_blocker_family")),
        commands=commands,
    )
    compact["operator_blocker_family_plan"] = _compact_operator_blocker_family_plan(
        _as_list(packet.get("operator_blocker_family_plan")),
        commands=commands,
    )
    return compact


def _unblock_plan_runtime_action_packet(
    slot: dict[str, Any],
    unblock: dict[str, Any],
) -> dict[str, Any]:
    source_action = _as_dict(slot.get("source_acquisition_row_action"))
    source_runtime_action_packet = _as_dict(source_action.get("runtime_action_packet"))
    detail = _as_dict(slot.get("row_input_slot_detail"))

    runtime_keys = (
        "case_input_slot_count",
        "blocked_case_input_slot_count",
        "required_engine_run_count",
        "ready_engine_run_slot_count",
        "blocked_engine_run_slot_count",
    )
    first_blocked_case_input_slot = _as_dict(
        unblock.get("first_blocked_case_input_slot")
    )
    first_blocked_engine_run_slot = _as_dict(
        unblock.get("first_blocked_engine_run_slot")
    )
    preflight_summary = _as_dict(
        source_runtime_action_packet.get("input_manifest_template_preflight_summary")
        or unblock.get("input_manifest_template_preflight_summary")
    )
    compact_preflight_summary = _omit_repeated_input_manifest_completion_plans(
        preflight_summary
    )
    input_manifest_completion_action_plan = [
        row
        for row in _as_list(
            source_runtime_action_packet.get("input_manifest_completion_action_plan")
            or unblock.get("input_manifest_completion_action_plan")
            or preflight_summary.get("input_manifest_completion_action_plan")
        )
        if isinstance(row, dict)
    ]
    operator_blocker_family_plan = [
        row
        for row in _as_list(
            source_runtime_action_packet.get("operator_blocker_family_plan")
            or unblock.get("operator_blocker_family_plan")
        )
        if isinstance(row, dict)
    ]
    if (
        not first_blocked_case_input_slot
        and not first_blocked_engine_run_slot
        and not any(key in unblock for key in runtime_keys)
        and not source_runtime_action_packet
    ):
        return {}

    return {
        **source_runtime_action_packet,
        "artifact": str(
            source_runtime_action_packet.get("artifact")
            or detail.get("artifact")
            or unblock.get("artifact")
            or ""
        ),
        "status": str(
            source_runtime_action_packet.get("status")
            or unblock.get("status")
            or detail.get("status")
            or ""
        ),
        "runtime_readiness_blocker_count": _as_int(
            detail.get("runtime_readiness_blocker_count")
        ),
        "case_input_slot_count": _as_int(
            source_runtime_action_packet.get("case_input_slot_count")
            or unblock.get("case_input_slot_count")
        ),
        "blocked_case_input_slot_count": _as_int(
            source_runtime_action_packet.get("blocked_case_input_slot_count")
            or unblock.get("blocked_case_input_slot_count")
        ),
        "required_engine_run_count": _as_int(
            source_runtime_action_packet.get("required_engine_run_count")
            or unblock.get("required_engine_run_count")
        ),
        "ready_engine_run_slot_count": _as_int(
            source_runtime_action_packet.get("ready_engine_run_slot_count")
            or unblock.get("ready_engine_run_slot_count")
        ),
        "blocked_engine_run_slot_count": _as_int(
            source_runtime_action_packet.get("blocked_engine_run_slot_count")
            or unblock.get("blocked_engine_run_slot_count")
        ),
        "missing_engine_ids": [
            str(item)
            for item in _as_list(
                source_runtime_action_packet.get("missing_engine_ids")
                or detail.get("missing_engine_ids")
                or unblock.get("missing_engine_ids")
            )
        ],
        "engine_runtime_actions": [
            row
            for row in _as_list(
                source_runtime_action_packet.get("engine_runtime_actions")
                or unblock.get("engine_runtime_actions")
            )
            if isinstance(row, dict)
        ],
        "first_blocked_case_input_slot": _as_dict(
            source_runtime_action_packet.get("first_blocked_case_input_slot")
            or first_blocked_case_input_slot
        ),
        "first_blocked_engine_run_slot": _as_dict(
            source_runtime_action_packet.get("first_blocked_engine_run_slot")
            or first_blocked_engine_run_slot
        ),
        "input_manifest_template_preflight_summary": compact_preflight_summary,
        "input_manifest_completion_action_case_count": _as_int(
            source_runtime_action_packet.get(
                "input_manifest_completion_action_case_count"
            )
            or unblock.get("input_manifest_completion_action_case_count")
            or preflight_summary.get("input_manifest_completion_action_case_count")
            or len(input_manifest_completion_action_plan)
        ),
        "input_manifest_completion_blocked_case_count": _as_int(
            source_runtime_action_packet.get(
                "input_manifest_completion_blocked_case_count"
            )
            or unblock.get("input_manifest_completion_blocked_case_count")
            or preflight_summary.get("input_manifest_completion_blocked_case_count")
            or len(input_manifest_completion_action_plan)
        ),
        "input_manifest_completion_action_plan": (
            input_manifest_completion_action_plan
        ),
        "detected_row_artifact_count": _as_int(
            unblock.get("detected_row_artifact_count")
        ),
        "selected_row_path": str(unblock.get("selected_row_path") or ""),
        "adapter_row_preflight_status": str(
            unblock.get("adapter_row_preflight_status") or ""
        ),
        "operator_blocker_family_count": _as_int(
            source_runtime_action_packet.get("operator_blocker_family_count")
            or unblock.get("operator_blocker_family_count")
            or len(operator_blocker_family_plan)
        ),
        "operator_blocker_family_blocked_count": _as_int(
            source_runtime_action_packet.get("operator_blocker_family_blocked_count")
            or unblock.get("operator_blocker_family_blocked_count")
        ),
        "operator_blocker_family_missing_item_count": _as_int(
            source_runtime_action_packet.get(
                "operator_blocker_family_missing_item_count"
            )
            or unblock.get("operator_blocker_family_missing_item_count")
        ),
        "first_operator_blocker_family": _compact_operator_blocker_family(
            _as_dict(
                source_runtime_action_packet.get("first_operator_blocker_family")
                or unblock.get("first_operator_blocker_family")
            )
        ),
        "operator_blocker_family_plan": _compact_operator_blocker_family_plan(
            operator_blocker_family_plan
        ),
        "commands": {
            **_as_dict(source_runtime_action_packet.get("commands")),
            **_as_dict(unblock.get("commands")),
        },
        "claim_boundary": str(
            source_runtime_action_packet.get("claim_boundary")
            or unblock.get("claim_boundary")
            or ""
        ),
    }


def _unblock_plan_refinement_action_packet(
    slot: dict[str, Any],
    unblock: dict[str, Any],
) -> dict[str, Any]:
    source_action = _as_dict(slot.get("source_acquisition_row_action"))
    top_k_action = _as_dict(source_action.get("top_k_rows_action_packet"))
    row_preflight_action = _as_dict(source_action.get("row_preflight_action_packet"))
    rows_from_receipt_bundle_report = _as_dict(
        top_k_action.get("rows_from_receipt_bundle_report")
    )
    first_incomplete_receipt = _as_dict(
        rows_from_receipt_bundle_report.get("first_incomplete_receipt")
    )
    detail = _as_dict(slot.get("row_input_slot_detail"))
    top_k_summary = _as_dict(detail.get("top_k_slot_status_summary"))
    first_missing_candidate_slot = _as_dict(
        unblock.get("first_missing_candidate_slot")
        or detail.get("first_missing_candidate_slot")
        or top_k_summary.get("first_missing_candidate_slot")
    )
    role_receipt_summary = _as_dict(top_k_action.get("role_receipt_plan_summary"))
    input_source_receipt_summary = _as_dict(
        top_k_action.get("operator_input_source_receipt_plan_summary")
    )
    first_blocked_role_receipt = _as_dict(
        role_receipt_summary.get("first_blocked_role_receipt")
    )
    first_blocked_source_receipt = _as_dict(
        input_source_receipt_summary.get("first_blocked_receipt")
    )
    survival_report = _as_dict(detail.get("survival_report"))
    if (
        not first_missing_candidate_slot
        and not first_blocked_role_receipt
        and not first_blocked_source_receipt
        and not top_k_action
        and not row_preflight_action
        and not survival_report
    ):
        return {}

    return {
        "status": str(
            top_k_action.get("status")
            or unblock.get("status")
            or detail.get("status")
            or ""
        ),
        "expected_rows_artifact": str(
            top_k_action.get("expected_rows_artifact")
            or unblock.get("expected_rows_artifact")
            or slot.get("preferred_default_row_path")
            or ""
        ),
        "required_candidate_slot_count": _as_int(
            unblock.get("required_candidate_slot_count")
            or row_preflight_action.get("required_candidate_slot_count")
        ),
        "provided_candidate_slot_count": _as_int(
            unblock.get("provided_candidate_slot_count")
        ),
        "missing_candidate_slot_count": _as_int(
            unblock.get("missing_candidate_slot_count")
        ),
        "first_missing_candidate_slot": first_missing_candidate_slot,
        "role_receipt_blocked_count": _as_int(
            role_receipt_summary.get("role_receipt_blocked_count")
        ),
        "first_blocked_role_receipt": first_blocked_role_receipt,
        "operator_input_source_receipt_blocked_count": _as_int(
            input_source_receipt_summary.get("blocked_count")
        ),
        "first_blocked_operator_input_source_receipt": (
            first_blocked_source_receipt
        ),
        "rows_from_receipt_bundle_report": rows_from_receipt_bundle_report,
        "rows_from_receipt_bundle_status": str(
            rows_from_receipt_bundle_report.get("status") or ""
        ),
        "rows_from_receipt_bundle_receipt_count": _as_int(
            rows_from_receipt_bundle_report.get("receipt_count")
        ),
        "rows_from_receipt_bundle_ready_receipt_count": _as_int(
            rows_from_receipt_bundle_report.get("ready_receipt_count")
        ),
        "rows_from_receipt_bundle_incomplete_receipt_count": _as_int(
            rows_from_receipt_bundle_report.get("incomplete_receipt_count")
        ),
        "rows_from_receipt_bundle_missing_required_field_count": _as_int(
            first_incomplete_receipt.get("completion_missing_required_field_count")
        ),
        "rows_from_receipt_bundle_unique_missing_required_field_count": _as_int(
            rows_from_receipt_bundle_report.get(
                "unique_missing_required_field_count"
            )
        ),
        "rows_from_receipt_bundle_total_missing_required_field_count": _as_int(
            rows_from_receipt_bundle_report.get("total_missing_required_field_count")
        ),
        "first_incomplete_receipt": first_incomplete_receipt,
        "survival_report": survival_report,
        "commands": _as_dict(unblock.get("commands")),
        "claim_boundary": str(
            top_k_action.get("claim_boundary") or unblock.get("claim_boundary") or ""
        ),
    }


def _blocking_input_unblock_plan(
    missing_slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in missing_slots:
        detail = _as_dict(slot.get("row_input_slot_detail"))
        unblock = _as_dict(detail.get("operator_unblock_packet"))
        if not unblock:
            continue
        operator_sequence = [
            str(item) for item in _as_list(unblock.get("operator_sequence"))
        ]
        artifacts = _unblock_plan_artifacts(unblock)
        runtime_action_packet = _unblock_plan_runtime_action_packet(slot, unblock)
        refinement_action_packet = _unblock_plan_refinement_action_packet(
            slot,
            unblock,
        )
        row_payload = {
            "row_input_id": str(slot.get("row_input_id") or ""),
            "component_id": str(slot.get("actual_closure_component_id") or ""),
            "status": str(
                unblock.get("status")
                or detail.get("status")
                or slot.get("status")
                or ""
            ),
            "operator_action": str(slot.get("operator_action") or ""),
            "source_acquisition_operator_action": str(
                slot.get("source_acquisition_operator_action") or ""
            ),
            "expected_rows_artifact": str(
                unblock.get("expected_rows_artifact")
                or slot.get("preferred_default_row_path")
                or ""
            ),
            "artifact_refs": artifacts,
            "operator_sequence": operator_sequence,
            "first_operator_sequence_step": (
                operator_sequence[0] if operator_sequence else ""
            ),
            "commands": _as_dict(unblock.get("commands")),
            "counts": _unblock_plan_counts(unblock),
            "claim_boundary": str(unblock.get("claim_boundary") or ""),
        }
        if runtime_action_packet:
            row_payload["runtime_action_packet"] = runtime_action_packet
            first_case_slot = _as_dict(
                runtime_action_packet.get("first_blocked_case_input_slot")
            )
            first_engine_slot = _as_dict(
                runtime_action_packet.get("first_blocked_engine_run_slot")
            )
            if first_case_slot:
                row_payload["first_blocked_case_input_slot"] = first_case_slot
            if first_engine_slot:
                row_payload["first_blocked_engine_run_slot"] = first_engine_slot
        if refinement_action_packet:
            row_payload["refinement_action_packet"] = refinement_action_packet
            first_candidate_slot = _as_dict(
                refinement_action_packet.get("first_missing_candidate_slot")
            )
            first_role_receipt = _as_dict(
                refinement_action_packet.get("first_blocked_role_receipt")
            )
            first_source_receipt = _as_dict(
                refinement_action_packet.get(
                    "first_blocked_operator_input_source_receipt"
                )
            )
            rows_from_receipt_bundle_report = _as_dict(
                refinement_action_packet.get("rows_from_receipt_bundle_report")
            )
            first_incomplete_receipt = _as_dict(
                refinement_action_packet.get("first_incomplete_receipt")
            )
            if first_candidate_slot:
                row_payload["first_missing_candidate_slot"] = first_candidate_slot
            if first_role_receipt:
                row_payload["first_blocked_role_receipt"] = first_role_receipt
            if first_source_receipt:
                row_payload["first_blocked_operator_input_source_receipt"] = (
                    first_source_receipt
                )
            if rows_from_receipt_bundle_report:
                row_payload["rows_from_receipt_bundle_report"] = (
                    rows_from_receipt_bundle_report
                )
            if first_incomplete_receipt:
                row_payload["first_incomplete_receipt"] = first_incomplete_receipt
            survival_report = _as_dict(
                refinement_action_packet.get("survival_report")
            )
            if survival_report:
                row_payload["survival_report"] = survival_report
        rows.append(row_payload)
    return rows


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
                "source_acquisition_operator_next_actions": [
                    str(item)
                    for item in _as_list(
                        slot.get("source_acquisition_operator_next_actions")
                    )
                ],
                "source_acquisition_row_action": _as_dict(
                    slot.get("source_acquisition_row_action")
                ),
                "source_acquisition_completion_audit": _as_dict(
                    _as_dict(slot.get("upstream_source_acquisition")).get(
                        "phase4_completion_audit"
                    )
                ),
                "source_acquisition_phase4_actual_evidence_audit": _as_dict(
                    _as_dict(slot.get("upstream_source_acquisition")).get(
                        "phase4_actual_evidence_audit"
                    )
                ),
                "source_acquisition_vina_gnina_actual_evidence_audit": _as_dict(
                    _as_dict(slot.get("upstream_source_acquisition")).get(
                        "vina_gnina_actual_evidence_audit"
                    )
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
        operator_actions = _dedupe(
            [str(slot.get("operator_action") or "") for slot in component_slots]
        )
        source_acquisition_operator_actions = sorted(
            {
                str(slot.get("source_acquisition_operator_action") or "")
                for slot in component_slots
                if str(slot.get("source_acquisition_operator_action") or "")
            }
        )
        upstream_source_blockers = _dedupe(
            [
                str(blocker)
                for slot in component_slots
                for blocker in _as_list(slot.get("upstream_source_blockers"))
            ]
        )
        operator_blockers_if_missing = _dedupe(
            [
                str(blocker)
                for slot in component_slots
                for blocker in _as_list(slot.get("operator_blockers_if_missing"))
            ]
        )
        first_action = missing_row_input_actions[0] if missing_row_input_actions else {}
        rows.append(
            {
                "component_id": str(summary.get("component_id") or ""),
                "missing_row_input_ids": missing_ids,
                "operator_action": str(first_action.get("operator_action") or ""),
                "operator_actions": operator_actions,
                "missing_row_input_actions": missing_row_input_actions,
                "missing_row_input_action_count": len(missing_row_input_actions),
                "first_missing_row_input_action": first_action,
                "source_acquisition_operator_action": str(
                    first_action.get("source_acquisition_operator_action") or ""
                ),
                "source_acquisition_operator_actions": (
                    source_acquisition_operator_actions
                ),
                "upstream_source_blockers": upstream_source_blockers,
                "operator_blockers_if_missing": operator_blockers_if_missing,
                "closes_actual_closure_criteria": [
                    str(item)
                    for item in _as_list(
                        summary.get("closes_actual_closure_criteria")
                    )
                ],
            }
        )
    return rows


def _science_completion_progress(audit: dict[str, Any]) -> dict[str, Any]:
    completion = _as_dict(audit.get("completion_audit"))
    summary = _as_dict(audit.get("summary"))
    component_progress = [
        {
            "component_id": str(row.get("component_id") or ""),
            "status": str(row.get("status") or ""),
            "actual_closure_ready": bool(row.get("actual_closure_ready")),
            "requirement_count": _as_int(row.get("requirement_count")),
            "requirement_pass_count": _as_int(row.get("requirement_pass_count")),
            "failed_criteria": [
                str(item) for item in _as_list(row.get("failed_criteria"))
            ],
            "missing_row_inputs": [
                str(item) for item in _as_list(row.get("missing_row_inputs"))
            ],
        }
        for row in _as_list(completion.get("component_audits"))
        if isinstance(row, dict)
    ]
    requirement_count = _as_int(
        completion.get("requirement_count") or summary.get("requirement_count")
    )
    requirement_pass_count = _as_int(
        completion.get("requirement_pass_count")
        or summary.get("passing_requirement_count")
    )
    blocked_requirement_count = _as_int(summary.get("blocked_requirement_count"))
    if not blocked_requirement_count and requirement_count >= requirement_pass_count:
        blocked_requirement_count = requirement_count - requirement_pass_count
    complete_component_ids = [
        str(item) for item in _as_list(completion.get("complete_component_ids"))
    ]
    blocked_component_ids = [
        str(item) for item in _as_list(completion.get("blocked_component_ids"))
    ]
    missing_row_inputs = [
        str(item) for item in _as_list(completion.get("missing_row_inputs"))
    ]
    return {
        "status": str(completion.get("status") or audit.get("status") or ""),
        "actual_closure_ready": bool(completion.get("actual_closure_ready")),
        "requirement_count": requirement_count,
        "requirement_pass_count": requirement_pass_count,
        "blocked_requirement_count": blocked_requirement_count,
        "required_component_count": _as_int(
            completion.get("required_component_count")
            or summary.get("required_component_count")
        ),
        "complete_component_count": len(complete_component_ids),
        "blocked_component_count": len(blocked_component_ids),
        "complete_component_ids": complete_component_ids,
        "blocked_component_ids": blocked_component_ids,
        "missing_row_input_count": len(missing_row_inputs),
        "missing_row_inputs": missing_row_inputs,
        "first_blocked_component_id": (
            blocked_component_ids[0] if blocked_component_ids else ""
        ),
        "component_progress": component_progress,
        "claim_boundary": str(completion.get("claim_boundary") or ""),
    }


def _actual_evidence_audit_lines(title: str, audit: dict[str, Any]) -> list[str]:
    if not audit:
        return []
    components = [
        row for row in _as_list(audit.get("components")) if isinstance(row, dict)
    ]
    operator_blocker_families = [
        row
        for row in _as_list(audit.get("operator_blocker_family_plan"))
        if isinstance(row, dict)
    ]
    lines = [
        "",
        f"### {title}",
        "",
        f"- `status`: `{audit.get('status')}`",
        f"- `actual_closure_ready`: `{audit.get('actual_closure_ready')}`",
        "- `ready_component_count`: "
        f"`{audit.get('ready_component_count')}`",
        "- `blocked_component_count`: "
        f"`{audit.get('blocked_component_count')}`",
        "- `remaining_evidence`: "
        f"{_code_join(_as_list(audit.get('remaining_evidence')))}",
        "- `operator_blocker_family_count`: "
        f"`{audit.get('operator_blocker_family_count', 0)}`",
        "- `operator_blocker_family_missing_item_count`: "
        f"`{audit.get('operator_blocker_family_missing_item_count', 0)}`",
        "",
        "| Component | Status | Pass | Current | Required | Blockers |",
        "|---|---|---|---|---|---|",
    ]
    for row in components:
        current = json.dumps(
            _as_dict(row.get("current")),
            ensure_ascii=False,
            sort_keys=True,
        )
        required = json.dumps(
            _as_dict(row.get("required")),
            ensure_ascii=False,
            sort_keys=True,
        )
        lines.append(
            "| "
            f"`{row.get('component_id', '')}` | "
            f"`{row.get('status', '')}` | "
            f"`{row.get('pass')}` | "
            f"`{current}` | "
            f"`{required}` | "
            f"{_code_join(_as_list(row.get('blockers')))} |"
        )
    if operator_blocker_families:
        lines.extend(
            [
                "",
                "#### Operator Blocker Families",
                "",
                "| Family | Status | Missing Items | Blocked Cases | Operator Action | Command Key |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for row in operator_blocker_families:
            lines.append(
                "| "
                f"`{row.get('family_id', '')}` | "
                f"`{row.get('status', '')}` | "
                f"{_as_int(row.get('missing_item_count'))} | "
                f"{_as_int(row.get('blocked_case_count'))} | "
                f"`{row.get('operator_action', '')}` | "
                f"`{row.get('command_key', '')}` |"
            )
    return lines


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
    pocketmd_template_preflight = _load_json(
        repo_root,
        DEFAULT_POCKETMD_TOPK_ROWS_TEMPLATE_PREFLIGHT,
    )
    pocketmd_survival_report = _load_json(
        repo_root,
        DEFAULT_POCKETMD_TOPK_SURVIVAL_REPORT,
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
            template_preflight=pocketmd_template_preflight,
            template_preflight_artifact=DEFAULT_POCKETMD_TOPK_ROWS_TEMPLATE_PREFLIGHT,
            survival_report=pocketmd_survival_report,
            survival_report_artifact=DEFAULT_POCKETMD_TOPK_SURVIVAL_REPORT,
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
    blocking_input_unblock_plan = _blocking_input_unblock_plan(missing_slots)
    blocked_component_operator_actions = _blocked_component_operator_actions(slots)
    completion_progress = _science_completion_progress(audit)
    handoff_upstream_source_acquisition = (
        _omit_repeated_input_manifest_completion_plans(upstream_source_acquisition)
    )
    handoff_row_input_materialization_contracts = (
        _omit_repeated_input_manifest_completion_plans(
            row_input_materialization_contracts
        )
    )
    handoff_operator_rows_packet = _omit_repeated_input_manifest_completion_plans(
        operator_rows_packet
    )
    handoff_blocked_component_operator_actions = (
        _omit_repeated_input_manifest_completion_plans(
            blocked_component_operator_actions
        )
    )
    handoff_slots = _omit_repeated_input_manifest_completion_plans(slots)
    handoff_first_missing_slot = _omit_repeated_input_manifest_completion_plans(
        missing_slots[0] if missing_slots else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_science_actual_closure_operator_handoff.py"),
                audit_path,
                DEFAULT_POCKETMD_REFINEMENT_PLAN,
                DEFAULT_POCKETMD_TOPK_ROWS_TEMPLATE_PREFLIGHT,
                DEFAULT_POCKETMD_TOPK_SURVIVAL_REPORT,
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
            "actual_closure_requirement_count": completion_progress[
                "requirement_count"
            ],
            "actual_closure_requirement_pass_count": completion_progress[
                "requirement_pass_count"
            ],
            "actual_closure_blocked_requirement_count": completion_progress[
                "blocked_requirement_count"
            ],
            "actual_closure_complete_component_count": completion_progress[
                "complete_component_count"
            ],
            "actual_closure_blocked_component_count": completion_progress[
                "blocked_component_count"
            ],
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "blocker_count": len(blockers),
        "science_actual_closure_blockers": science_actual_closure_blockers,
        "upstream_source_acquisition": handoff_upstream_source_acquisition,
        "upstream_source_blockers": upstream_source_blockers,
        "row_template_artifacts": row_template_artifacts,
        "missing_row_template_artifacts": missing_row_template_artifacts,
        "missing_row_inputs": [
            str(slot.get("row_input_id") or "") for slot in missing_slots
        ],
        "row_input_materialization_contracts": (
            handoff_row_input_materialization_contracts
        ),
        "operator_rows_packet": handoff_operator_rows_packet,
        "science_actual_closure_completion_progress": completion_progress,
        "blocking_input_unblock_plan": blocking_input_unblock_plan,
        "blocking_input_unblock_plan_count": len(blocking_input_unblock_plan),
        "blocked_component_operator_actions": (
            handoff_blocked_component_operator_actions
        ),
        "first_missing_slot": handoff_first_missing_slot,
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
        "row_slot_handoffs": handoff_slots,
        "row_slot_handoff_count": len(slots),
        "claim_boundary": (
            "This handoff is an operator checklist derived from the science row "
            "audit. It is not actual science evidence and does not close Phase 2, "
            "GPCR hard-decoy, or PocketMD Lite gates without accepted real rows."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = _as_dict(payload.get("summary"))
    completion_progress = _as_dict(
        payload.get("science_actual_closure_completion_progress")
    )
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
        "## Actual Closure Progress",
        "",
        f"- `status`: `{completion_progress.get('status')}`",
        f"- `actual_closure_ready`: `{completion_progress.get('actual_closure_ready')}`",
        "- `requirements`: "
        f"`{completion_progress.get('requirement_pass_count')}/"
        f"{completion_progress.get('requirement_count')}`",
        "- `blocked_requirement_count`: "
        f"`{completion_progress.get('blocked_requirement_count')}`",
        "- `complete_components`: "
        f"`{completion_progress.get('complete_component_count')}/"
        f"{completion_progress.get('required_component_count')}`",
        "- `blocked_components`: "
        f"{_code_join(_as_list(completion_progress.get('blocked_component_ids')))}",
        "- `missing_row_inputs`: "
        f"{_code_join(_as_list(completion_progress.get('missing_row_inputs')))}",
        "",
        "| Row Input | Status | Preferred Path | CSV Starter | Closes Criteria | Action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    component_progress = [
        row
        for row in _as_list(completion_progress.get("component_progress"))
        if isinstance(row, dict)
    ]
    if component_progress:
        lines.extend(
            [
                "",
                "| Component | Status | Requirements | Missing Rows | Failed Criteria |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for component in component_progress:
            lines.append(
                "| "
                f"`{component.get('component_id')}` | "
                f"`{component.get('status')}` | "
                f"`{component.get('requirement_pass_count')}/"
                f"{component.get('requirement_count')}` | "
                f"{_code_join(_as_list(component.get('missing_row_inputs')))} | "
                f"{_code_join(_as_list(component.get('failed_criteria')))} |"
            )
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
    unblock_plan = [
        row
        for row in _as_list(payload.get("blocking_input_unblock_plan"))
        if isinstance(row, dict)
    ]
    if unblock_plan:
        lines.extend(["", "## Blocking Input Unblock Plan", ""])
        lines.extend(
            [
                "| Row Input | Status | Expected Rows | First Step | First Blocked Slot | Preflight Artifacts | Primary Command |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        command_preference = (
            "build_input_manifest_template_preflight",
            "build_row_template_preflight",
            "build_rows_template_preflight",
            "rerun_execution_plan",
            "import_rows",
            "materialize_survival_report",
            "materialize_adapter",
        )
        preflight_keys = (
            "input_manifest_template_preflight_artifact",
            "rows_template_preflight_artifact",
            "row_template_preflight_artifact",
        )
        for row in unblock_plan:
            artifacts = _as_dict(row.get("artifact_refs"))
            commands = _as_dict(row.get("commands"))
            runtime_action = _as_dict(row.get("runtime_action_packet"))
            first_case_slot = _as_dict(
                runtime_action.get("first_blocked_case_input_slot")
            )
            first_engine_slot = _as_dict(
                runtime_action.get("first_blocked_engine_run_slot")
            )
            manifest_completion_plan = [
                item
                for item in _as_list(
                    runtime_action.get("input_manifest_completion_action_plan")
                )
                if isinstance(item, dict)
            ]
            first_manifest_completion_action = (
                manifest_completion_plan[0] if manifest_completion_plan else {}
            )
            refinement_action = _as_dict(row.get("refinement_action_packet"))
            first_candidate_slot = _as_dict(
                refinement_action.get("first_missing_candidate_slot")
            )
            first_role_receipt = _as_dict(
                refinement_action.get("first_blocked_role_receipt")
            )
            first_source_receipt = _as_dict(
                refinement_action.get(
                    "first_blocked_operator_input_source_receipt"
                )
            )
            first_incomplete_receipt = _as_dict(
                refinement_action.get("first_incomplete_receipt")
            )
            survival_report = _as_dict(refinement_action.get("survival_report"))
            first_blocked_slot_refs = []
            if first_case_slot:
                first_blocked_slot_refs.append(
                    "case:"
                    f"{first_case_slot.get('case_id', '')}/"
                    f"{first_case_slot.get('operator_action', '')}"
                )
            if first_engine_slot:
                first_blocked_slot_refs.append(
                    "engine:"
                    f"{first_engine_slot.get('case_id', '')}/"
                    f"{first_engine_slot.get('engine_id', '')}/"
                    f"{first_engine_slot.get('docking_run_id', '')}"
                )
            engine_run_bundle_status = str(
                runtime_action.get("engine_run_bundle_status") or ""
            )
            if engine_run_bundle_status:
                first_blocked_slot_refs.append(
                    f"bundle:{engine_run_bundle_status}"
                )
            rows_from_engine_run_bundle_status = str(
                runtime_action.get("rows_from_engine_run_bundle_status") or ""
            )
            if rows_from_engine_run_bundle_status:
                first_blocked_slot_refs.append(
                    f"rows_bundle:{rows_from_engine_run_bundle_status}"
                )
            if first_candidate_slot:
                first_blocked_slot_refs.append(
                    "candidate:"
                    f"{first_candidate_slot.get('slot_id', '')}/"
                    f"{first_candidate_slot.get('operator_action', '')}"
                )
            if first_role_receipt:
                first_blocked_slot_refs.append(
                    "role:"
                    f"{first_role_receipt.get('role_id', '')}/"
                    f"{first_role_receipt.get('candidate_id', '')}"
                )
            if first_source_receipt:
                first_blocked_slot_refs.append(
                    "source:"
                    f"{first_source_receipt.get('field', '')}/"
                    f"{first_source_receipt.get('operator_action', '')}"
                )
            if first_incomplete_receipt:
                first_blocked_slot_refs.append(
                    "receipt:"
                    f"{first_incomplete_receipt.get('receipt_ref', '')}/"
                    "missing_fields="
                    f"{first_incomplete_receipt.get('completion_missing_required_field_count', '')}"
                )
            if survival_report and str(
                survival_report.get("first_blocked_target") or ""
            ):
                first_blocked_slot_refs.append(
                    "report:"
                    f"{survival_report.get('first_blocked_target', '')}"
                )
            if first_manifest_completion_action:
                first_blocked_slot_refs.append(
                    "manifest:"
                    f"{first_manifest_completion_action.get('case_id', '')}/"
                    f"{first_manifest_completion_action.get('operator_completion_action', '')}/"
                    "missing_files="
                    f"{first_manifest_completion_action.get('missing_local_file_count', '')}"
                )
            preflight_refs = [
                artifacts[key] for key in preflight_keys if str(artifacts.get(key) or "")
            ]
            primary_command = ""
            for key in command_preference:
                command = str(commands.get(key) or "")
                if command:
                    primary_command = command
                    break
            lines.append(
                "| "
                f"`{row.get('row_input_id')}` | "
                f"`{row.get('status')}` | "
                f"`{row.get('expected_rows_artifact')}` | "
                f"`{row.get('first_operator_sequence_step')}` | "
                f"{_code_join(first_blocked_slot_refs)} | "
                f"{_code_join(preflight_refs)} | "
                f"`{primary_command}` |"
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
                template_preflight = _as_dict(
                    row_input_detail.get("row_template_preflight")
                )
                template_preflight_commands = _as_dict(
                    template_preflight.get("commands")
                )
                survival_report = _as_dict(
                    row_input_detail.get("survival_report")
                )
                lines.extend(["", "### PocketMD Top-k Candidate Slots", ""])
                if operator_unblock:
                    lines.extend(
                        [
                            f"- `operator_unblock_status`: `{operator_unblock.get('status')}`",
                            f"- `row_template_artifact`: `{operator_unblock.get('row_template_artifact')}`",
                            "- `row_template_preflight_artifact`: "
                            f"`{operator_unblock.get('row_template_preflight_artifact')}`",
                            "- `row_template_preflight_command`: "
                            f"`{_as_dict(operator_unblock.get('commands')).get('build_row_template_preflight', '')}`",
                        ]
                    )
                if template_preflight:
                    lines.extend(
                        [
                            f"- `row_template_preflight_status`: `{template_preflight.get('status')}`",
                            f"- `row_template_preflight_ready`: `{template_preflight.get('top_k_template_ready')}`",
                            "- `row_template_preflight_missing_metric_value_count`: "
                            f"`{template_preflight.get('missing_metric_value_count')}`",
                            "- `row_template_preflight_missing_receipt_value_count`: "
                            f"`{template_preflight.get('missing_receipt_value_count')}`",
                            "- `row_template_preflight_write_command`: "
                            f"`{template_preflight_commands.get('write_preflight', '')}`",
                        ]
                    )
                if survival_report:
                    lines.extend(
                        [
                            f"- `survival_report_status`: `{survival_report.get('status')}`",
                            "- `survival_report_contract_pass`: "
                            f"`{survival_report.get('contract_pass')}`",
                            "- `survival_report_first_blocked_target`: "
                            f"`{survival_report.get('first_blocked_target')}`",
                            "- `survival_report_blocker_count`: "
                            f"`{survival_report.get('blocker_count')}`",
                            "- `survival_report_blockers`: "
                            f"{_code_join(_as_list(survival_report.get('blockers')))}",
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
                    engine_runtime_actions = [
                        row
                        for row in _as_list(operator_unblock.get("engine_runtime_actions"))
                        if isinstance(row, dict)
                    ]
                    lines.extend(
                        [
                            f"- `operator_unblock_status`: `{operator_unblock.get('status')}`",
                            "- `missing_engine_ids`: "
                            f"{_code_join(_as_list(operator_unblock.get('missing_engine_ids')))}",
                            "- `runtime_readiness_blocker_count`: "
                            f"`{engine_run_detail.get('runtime_readiness_blocker_count')}`",
                            "- `adapter_row_preflight_status`: "
                            f"`{operator_unblock.get('adapter_row_preflight_status')}`",
                            f"- `input_manifest_template_artifact`: `{operator_unblock.get('input_manifest_template_artifact')}`",
                            "- `input_manifest_template_preflight_artifact`: "
                            f"`{operator_unblock.get('input_manifest_template_preflight_artifact')}`",
                            "- `input_manifest_template_preflight_command`: "
                            f"`{_as_dict(operator_unblock.get('commands')).get('build_input_manifest_template_preflight', '')}`",
                        ]
                    )
                    if engine_runtime_actions:
                        lines.extend(
                            [
                                "",
                                "| Engine | Runtime Action | Binary Env | Container Env |",
                                "| --- | --- | --- | --- |",
                            ]
                        )
                        for action in engine_runtime_actions:
                            lines.append(
                                "| "
                                f"`{action.get('engine_id')}` | "
                                f"`{action.get('operator_action')}` | "
                                f"`{action.get('binary_env_var')}` | "
                                f"`{action.get('container_image_env_var')}` |"
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
        source_next_action_rows: list[dict[str, Any]] = []
        for component in blocked_component_actions:
            for action in _as_list(component.get("missing_row_input_actions")):
                if not isinstance(action, dict):
                    continue
                next_actions = [
                    str(item)
                    for item in _as_list(
                        action.get("source_acquisition_operator_next_actions")
                    )
                    if str(item)
                ]
                if not next_actions:
                    continue
                source_next_action_rows.append(
                    {
                        "component_id": str(component.get("component_id") or ""),
                        "row_input_id": str(action.get("row_input_id") or ""),
                        "source_action": str(
                            action.get("source_acquisition_operator_action") or ""
                        ),
                        "first_step": next_actions[0],
                        "last_step": next_actions[-1],
                        "action_count": len(next_actions),
                    }
                )
        if source_next_action_rows:
            lines.extend(["", "### Source Acquisition Next Actions", ""])
            lines.extend(
                [
                    "| Component | Row Input | Source Action | First Step | Last Step | Count |",
                    "| --- | --- | --- | --- | --- | ---: |",
                ]
            )
            for row in source_next_action_rows:
                lines.append(
                    "| "
                    f"`{row['component_id']}` | "
                    f"`{row['row_input_id']}` | "
                    f"`{row['source_action']}` | "
                    f"`{row['first_step']}` | "
                    f"`{row['last_step']}` | "
                    f"{row['action_count']} |"
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
                        f"- `source_archive_operator_artifact`: `{action.get('source_archive_operator_artifact')}`",
                        f"- `source_archive_extraction_command`: `{action.get('source_archive_extraction_command')}`",
                        f"- `source_archive_extraction_report_artifact`: `{action.get('source_archive_extraction_report_artifact')}`",
                        f"- `verify_execution_plan_command`: `{action.get('verify_execution_plan_command')}`",
                        f"- `verify_runtime_readiness_command`: `{action.get('verify_runtime_readiness_command')}`",
                        f"- `operator_must_fill_or_verify`: {_code_join(_as_list(action.get('operator_must_fill_or_verify')))}",
                        f"- `template_is_not_evidence`: `{safety_policy.get('template_is_not_evidence')}`",
                        f"- `do_not_treat_blank_prepared_checksums_as_ready`: `{safety_policy.get('do_not_treat_blank_prepared_checksums_as_ready')}`",
                    ]
                )
            elif detail.get("kind") == "vina_gnina_adapter_preflight":
                lines.extend(["", "### Vina/GNINA Adapter Row Preflight Action", ""])
                role_receipt_summary = _as_dict(
                    action.get("role_receipt_plan_summary")
                )
                first_blocked_role = _as_dict(
                    role_receipt_summary.get("first_blocked_role_receipt")
                )
                lines.extend(
                    [
                        f"- `component_id`: `{detail.get('component_id')}`",
                        f"- `row_input_id`: `{detail.get('row_input_id')}`",
                        f"- `status`: `{action.get('status')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `row_template_artifact`: `{action.get('row_template_artifact')}`",
                        f"- `row_template_preflight_artifact`: `{action.get('row_template_preflight_artifact')}`",
                        f"- `build_row_template_preflight_command`: `{action.get('build_row_template_preflight_command')}`",
                        f"- `role_receipt_blocked_count`: `{role_receipt_summary.get('role_receipt_blocked_count')}`",
                        f"- `first_blocked_role_receipt`: `{first_blocked_role.get('role_id', '')}` / `{first_blocked_role.get('slot_id', '')}`",
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
                template_preflight_summary = _as_dict(
                    action.get("template_preflight_summary")
                )
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
                        "- `template_preflight_role_receipt_blocked_count`: "
                        f"`{template_preflight_summary.get('role_receipt_blocked_count')}`",
                        "- `template_preflight_operator_input_source_receipt_blocked_count`: "
                        f"`{template_preflight_summary.get('operator_input_source_receipt_blocked_count')}`",
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
                rows_from_receipt_bundle_report = _as_dict(
                    action.get("rows_from_receipt_bundle_report")
                )
                metric_family_completion_plan = [
                    row
                    for row in _as_list(
                        rows_from_receipt_bundle_report.get(
                            "receipt_metric_family_completion_plan"
                        )
                    )
                    if isinstance(row, dict)
                ]
                first_metric_family_blocker = (
                    metric_family_completion_plan[0]
                    if metric_family_completion_plan
                    else {}
                )
                role_receipt_summary = _as_dict(
                    action.get("role_receipt_plan_summary")
                )
                input_source_receipt_summary = _as_dict(
                    action.get("operator_input_source_receipt_plan_summary")
                )
                first_blocked_role = _as_dict(
                    role_receipt_summary.get("first_blocked_role_receipt")
                )
                first_blocked_source_receipt = _as_dict(
                    input_source_receipt_summary.get("first_blocked_receipt")
                )
                lines.extend(
                    [
                        f"- `component_id`: `{detail.get('component_id')}`",
                        f"- `row_input_id`: `{detail.get('row_input_id')}`",
                        f"- `status`: `{action.get('status')}`",
                        f"- `template_artifact`: `{action.get('template_artifact')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `import_rows_command`: `{action.get('import_rows_command')}`",
                        f"- `materialize_rows_from_template_command`: `{action.get('materialize_rows_from_template_command')}`",
                        f"- `materialize_rows_from_receipt_bundle_command`: `{action.get('materialize_rows_from_receipt_bundle_command')}`",
                        f"- `materialize_survival_command`: `{action.get('materialize_survival_command')}`",
                        f"- `verify_science_actual_closure_command`: `{action.get('verify_science_actual_closure_command')}`",
                        f"- `operator_must_fill_or_verify`: {_code_join(_as_list(action.get('operator_must_fill_or_verify')))}",
                        f"- `required_receipt_roles`: {_code_join(_as_list(action.get('required_receipt_roles')))}",
                        f"- `role_receipt_blocked_count`: `{role_receipt_summary.get('role_receipt_blocked_count')}`",
                        f"- `first_blocked_role_receipt`: `{first_blocked_role.get('role_id', '')}` / `{first_blocked_role.get('candidate_id', '')}`",
                        f"- `operator_input_source_receipt_blocked_count`: `{input_source_receipt_summary.get('blocked_count')}`",
                        f"- `first_blocked_operator_input_source_receipt`: `{first_blocked_source_receipt.get('field', '')}`",
                        f"- `phase4_metric_receipt_action_count`: `{action.get('phase4_metric_receipt_action_count')}`",
                        f"- `receipt_metric_family_blocked_count`: `{rows_from_receipt_bundle_report.get('receipt_metric_family_blocked_count')}`",
                        f"- `first_receipt_metric_family_blocker`: `{first_metric_family_blocker.get('metric_family_id', '')}` / `{first_metric_family_blocker.get('blocked_receipt_count', '')}`",
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
        pocketmd_source_context = _as_dict(
            _as_dict(payload.get("upstream_source_acquisition")).get(
                "pocketmd_lite"
            )
        )
        phase4_completion_audit = _as_dict(
            pocketmd_source_context.get("phase4_completion_audit")
        )
        if phase4_completion_audit:
            remaining_blockers = [
                str(item)
                for item in _as_list(phase4_completion_audit.get("remaining_blockers"))
                if str(item)
            ]
            requirement_rows = [
                row
                for row in _as_list(phase4_completion_audit.get("requirements"))
                if isinstance(row, dict)
            ]
            lines.extend(
                [
                    "",
                    "### PocketMD Phase 4 Completion Audit",
                    "",
                    f"- `status`: `{phase4_completion_audit.get('status')}`",
                    "- `requirements_ready`: "
                    f"`{phase4_completion_audit.get('ready_requirement_count')}/"
                    f"{phase4_completion_audit.get('requirement_count')}`",
                    "- `blocked_requirement_count`: "
                    f"`{phase4_completion_audit.get('blocked_requirement_count')}`",
                    "- `remaining_row_inputs`: "
                    f"{_code_join(_as_list(phase4_completion_audit.get('remaining_row_inputs')))}",
                    "- `remaining_operator_action`: "
                    f"`{phase4_completion_audit.get('remaining_operator_action')}`",
                    f"- `remaining_blockers`: {_code_join(remaining_blockers)}",
                    "",
                    "| Requirement | Status | Product Requirement | Blockers |",
                    "|---|---|---|---|",
                ]
            )
            for row in requirement_rows:
                lines.append(
                    "| "
                    f"`{row.get('requirement_id', '')}` | "
                    f"`{row.get('status', '')}` | "
                    f"{row.get('product_requirement', '')} | "
                    f"{_code_join(_as_list(row.get('blockers')))} |"
                )
        lines.extend(
            _actual_evidence_audit_lines(
                "PocketMD Actual Evidence Audit",
                _as_dict(pocketmd_source_context.get("phase4_actual_evidence_audit")),
            )
        )
        public_source_context = _as_dict(
            _as_dict(payload.get("upstream_source_acquisition")).get(
                "public_benchmark_phase2"
            )
        )
        lines.extend(
            _actual_evidence_audit_lines(
                "Public Benchmark Vina/GNINA Actual Evidence Audit",
                _as_dict(
                    public_source_context.get("vina_gnina_actual_evidence_audit")
                ),
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
