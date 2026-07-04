#!/usr/bin/env python3
"""Build the read-only /goal bottleneck and roadmap surface."""

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
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_PM_REPORT = PRODUCTIZATION / "pm_release_gate_report.json"
DEFAULT_ACTION_REGISTER = PRODUCTIZATION / "pm_release_blocker_action_register.json"
DEFAULT_FRESHNESS_REPORT = PRODUCTIZATION / "release_evidence_freshness_report.json"
DEFAULT_SOURCE_OF_TRUTH_GAP_CLASSIFICATION = (
    PRODUCTIZATION / "source_of_truth_gap_classification.json"
)
DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT = (
    PRODUCTIZATION / "science_actual_closure_row_audit.json"
)
DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF = (
    PRODUCTIZATION / "science_actual_closure_operator_handoff.json"
)
DEFAULT_PRODUCT_CAPABILITIES = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_UX_OBSERVATION_REPORT = PRODUCTIZATION / "ux_new_user_observation_report.json"
DEFAULT_UX_OBSERVATION_INTAKE_PACKET = (
    PRODUCTIZATION / "ux_new_user_observation_intake_packet.json"
)
DEFAULT_OUT = PRODUCTIZATION / "goal_bottleneck_roadmap_surface.json"

SCHEMA_VERSION = "goal-bottleneck-roadmap-surface.v1"
STRUCTURAL_PHASE_CAPABILITY_IDS: dict[str, str] = {}
STRUCTURAL_PHASE_ACTUAL_CLOSURE_COMPONENT_IDS: dict[str, str] = {}
SCIENCE_ACTUAL_CLOSURE_COMPONENT_PHASES: dict[str, dict[str, Any]] = {
    "public_benchmark_phase2_actual_closure": {
        "phase_id": "phase_2_public_benchmark_actual_closure",
        "phase_label": "Phase 2",
        "roadmap_item": "Public benchmark Phase 2 actual closure",
        "bottleneck": "public_benchmark_vina_gnina_actual_rows_required",
        "root_cause_tags": [
            "science_actual_closure",
            "public_benchmark_phase2",
            "vina_gnina_actual_rows",
        ],
        "evidence_artifacts": [
            DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT,
            DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF,
            PRODUCTIZATION / "public_benchmark_phase2_source_acquisition_plan.json",
        ],
    },
    "gpcr_hard_decoy_actual_closure": {
        "phase_id": "phase_3_gpcr_hard_decoy_actual_closure",
        "phase_label": "Phase 3",
        "roadmap_item": "GPCR hard-decoy actual closure",
        "bottleneck": "gpcr_hard_decoy_actual_rows_required",
        "root_cause_tags": [
            "science_actual_closure",
            "gpcr_hard_decoy",
            "actual_gate_metrics",
        ],
        "evidence_artifacts": [
            DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT,
            DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF,
            PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json",
        ],
    },
    "pocketmd_lite_topk_actual_closure": {
        "phase_id": "phase_4_pocketmd_lite_topk_actual_closure",
        "phase_label": "Phase 4",
        "roadmap_item": "PocketMD Lite top-k actual closure",
        "bottleneck": "pocketmd_lite_topk_actual_rows_required",
        "root_cause_tags": [
            "science_actual_closure",
            "pocketmd_lite",
            "top_k_refinement_rows",
        ],
        "evidence_artifacts": [
            DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT,
            DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF,
            PRODUCTIZATION / "pocketmd_lite_source_acquisition_plan.json",
        ],
    },
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_goal_bottleneck_roadmap_surface.py"),
        DEFAULT_PM_REPORT,
        DEFAULT_ACTION_REGISTER,
        DEFAULT_FRESHNESS_REPORT,
        DEFAULT_SOURCE_OF_TRUTH_GAP_CLASSIFICATION,
        DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT,
        DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF,
        DEFAULT_PRODUCT_CAPABILITIES,
        DEFAULT_UX_OBSERVATION_REPORT,
        DEFAULT_UX_OBSERVATION_INTAKE_PACKET,
    ]


def _first_str(rows: list[Any]) -> str:
    return str(rows[0]) if rows else ""


def _dedupe(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for row in rows:
        if row and row not in seen:
            seen.add(row)
            deduped.append(row)
    return deduped


def _operator_handoff_id(
    *, namespace: str, phase_id: str = "", slot_id: str = "", fallback: Any = ""
) -> str:
    existing = str(fallback or "")
    if existing:
        return existing
    slot = str(slot_id or "")
    if slot:
        return f"{namespace or phase_id}::{slot}"
    phase = str(phase_id or "")
    return f"{namespace}::{phase}" if namespace and phase else phase


def _phase_capability_id(phase_id: str) -> str:
    return STRUCTURAL_PHASE_CAPABILITY_IDS.get(str(phase_id or ""), "")


def _phase_actual_closure_component_id(phase_id: str) -> str:
    return STRUCTURAL_PHASE_ACTUAL_CLOSURE_COMPONENT_IDS.get(str(phase_id or ""), "")


def _roadmap_row(
    *,
    phase_id: str,
    phase_label: str,
    roadmap_item: str,
    state: str,
    bottleneck: str = "",
    first_blocker: str = "",
    first_blocked_target: str = "",
    root_cause_tags: list[str] | None = None,
    evidence_artifacts: list[Path] | None = None,
    linked_routes: list[str] | None = None,
    next_actions: list[str] | None = None,
    blocked_criteria: list[str] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    criteria = blocked_criteria or []
    return {
        "phase_id": phase_id,
        "phase_label": phase_label,
        "roadmap_item": roadmap_item,
        "state": state,
        "bottleneck": bottleneck,
        "first_blocker": first_blocker,
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": root_cause_tags or [],
        "evidence_artifacts": [str(path) for path in evidence_artifacts or []],
        "linked_routes": linked_routes or [],
        "next_actions": next_actions or [],
        "blocked_criteria_count": len(criteria),
        "blocked_criteria": criteria,
        "summary": summary or {},
    }


def _source_of_truth_row(freshness: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(freshness.get("summary"))
    classification_rows = [
        row
        for row in _as_list(freshness.get("source_of_truth_gap_classification"))
        if isinstance(row, dict)
    ]
    candidate_count = _as_int(summary.get("source_of_truth_gap_candidate_count"))
    fix_count = _as_int(
        summary.get(
            "source_of_truth_gap_fix_count",
            summary.get("source_of_truth_gap_fixed_count"),
        )
    )
    no_op_count = _as_int(summary.get("source_of_truth_gap_no_op_count"))
    aggregator_count = _as_int(summary.get("source_of_truth_gap_aggregator_review_count"))
    blocker_count = _as_int(summary.get("blocker_count"))
    ready = bool(
        candidate_count
        and fix_count + no_op_count + aggregator_count == candidate_count
        and blocker_count == 0
    )
    return _roadmap_row(
        phase_id="phase_0_source_of_truth_hardening",
        phase_label="Phase 0",
        roadmap_item="/goal source-of-truth gap hardening",
        state="ready" if ready else "blocked",
        bottleneck="" if ready else "source_of_truth_gap_classification_open",
        first_blocker="" if ready else "source_of_truth_gap_candidate_unclassified",
        evidence_artifacts=[
            DEFAULT_FRESHNESS_REPORT,
            Path("docs/source-of-truth-gap-classification.md"),
        ],
        next_actions=(
            ["keep_aggregator_freshness_policy_visible"]
            if ready
            else ["classify_remaining_source_of_truth_gap_candidates"]
        ),
        summary={
            "candidate_count": candidate_count,
            "fix_count": fix_count,
            "fixed_count": fix_count,
            "no_op_count": no_op_count,
            "aggregator_review_count": aggregator_count,
            "freshness_blocker_count": blocker_count,
            "classification_rows": [
                {
                    "candidate": str(row.get("candidate") or ""),
                    "classification": str(row.get("classification") or ""),
                    "freshness_policy": str(row.get("freshness_policy") or ""),
                    "freshness_label": str(row.get("freshness_label") or ""),
                    "validation_basis": [
                        str(item)
                        for item in _as_list(row.get("validation_basis"))
                    ],
                }
                for row in classification_rows
            ],
        },
    )


def _release_cockpit_row(
    *,
    decision: dict[str, Any],
    action_register: dict[str, Any],
    product_capabilities: dict[str, Any],
) -> dict[str, Any]:
    release_allowed = _as_bool(decision.get("release_allowed"))
    required_kpis_present = all(
        key in decision
        for key in (
            "release_allowed",
            "blocked_release_count",
            "first_blocker",
            "operator_action_count",
            "approval_token_count",
            "stale_artifact_count",
            "evidence_surface_count",
            "missing_evidence_surface_count",
            "locked_evidence_surface_count",
            "public_benchmark_ready",
        )
    )
    return _roadmap_row(
        phase_id="phase_1_goal_release_cockpit",
        phase_label="Phase 1",
        roadmap_item="/goal release cockpit",
        state="ready" if required_kpis_present and release_allowed else "blocked",
        bottleneck=str(decision.get("first_blocker") or ""),
        first_blocker=str(decision.get("first_blocker") or ""),
        evidence_artifacts=[
            DEFAULT_PM_REPORT,
            DEFAULT_ACTION_REGISTER,
            DEFAULT_PRODUCT_CAPABILITIES,
        ],
        linked_routes=["/goal", "/goal/bottleneck", "/goal/roadmap", "/product/capabilities"],
        next_actions=(
            ["work_release_decision_operator_actions"]
            if not release_allowed
            else ["monitor_release_decision_kpis"]
        ),
        summary={
            "release_allowed": release_allowed,
            "blocked_release_count": _as_int(decision.get("blocked_release_count")),
            "operator_action_count": _as_int(decision.get("operator_action_count")),
            "approval_token_count": _as_int(decision.get("approval_token_count")),
            "action_register_contract_pass": _as_bool(action_register.get("contract_pass")),
            "product_capability_count": _as_int(product_capabilities.get("capability_count")),
            "blocked_capability_count": _as_int(product_capabilities.get("blocked_capability_count")),
        },
    )


def _science_actual_audit_for_component(
    science_handoff: dict[str, Any],
    component_id: str,
) -> dict[str, Any]:
    upstream = _as_dict(science_handoff.get("upstream_source_acquisition"))
    if component_id == "public_benchmark_phase2_actual_closure":
        return _as_dict(
            _as_dict(upstream.get("public_benchmark_phase2")).get(
                "vina_gnina_actual_evidence_audit"
            )
        )
    if component_id == "pocketmd_lite_topk_actual_closure":
        return _as_dict(
            _as_dict(upstream.get("pocketmd_lite")).get(
                "phase4_actual_evidence_audit"
            )
        )
    return {}


def _science_source_blockers_for_component(
    science_handoff: dict[str, Any],
    component_id: str,
) -> list[str]:
    upstream = _as_dict(science_handoff.get("upstream_source_acquisition"))
    if component_id == "public_benchmark_phase2_actual_closure":
        source = _as_dict(upstream.get("public_benchmark_phase2"))
    elif component_id == "pocketmd_lite_topk_actual_closure":
        source = _as_dict(upstream.get("pocketmd_lite"))
    else:
        source = {}
    return [str(row) for row in _as_list(source.get("blockers"))]


def _science_row_contracts_by_component(
    science_handoff: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    contracts_by_component: dict[str, list[dict[str, Any]]] = {}
    contracts = _as_dict(science_handoff.get("row_input_materialization_contracts"))
    for row_input_id, contract_value in contracts.items():
        contract = _as_dict(contract_value)
        if not contract:
            continue
        contract = {**contract, "row_input_id": str(row_input_id)}
        component_id = str(contract.get("actual_closure_component_id") or "")
        if not component_id:
            continue
        contracts_by_component.setdefault(component_id, []).append(contract)
    return contracts_by_component


def _science_actions_by_component(
    science_handoff: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("component_id") or ""): row
        for row in _as_list(science_handoff.get("blocked_component_operator_actions"))
        if isinstance(row, dict) and str(row.get("component_id") or "")
    }


def _pocketmd_operator_blocker_family_counts(
    pocketmd_summary: dict[str, Any],
    pocketmd_actual_audit: dict[str, Any],
) -> dict[str, int]:
    metric_family_count = _as_int(
        pocketmd_summary.get("rows_from_receipt_bundle_metric_family_count")
    )
    family_count = (
        _as_int(pocketmd_actual_audit.get("operator_blocker_family_count"))
        or _as_int(
            pocketmd_summary.get("phase4_actual_operator_blocker_family_count")
        )
    )
    if not family_count and metric_family_count:
        family_count = 3 + metric_family_count
    blocked_count = (
        _as_int(
            pocketmd_actual_audit.get("operator_blocker_family_blocked_count")
        )
        or _as_int(
            pocketmd_summary.get(
                "phase4_actual_operator_blocker_family_blocked_count"
            )
        )
    )
    if not blocked_count and family_count:
        blocked_count = family_count
    missing_item_count = (
        _as_int(
            pocketmd_actual_audit.get("operator_blocker_family_missing_item_count")
        )
        or _as_int(
            pocketmd_summary.get(
                "phase4_actual_operator_blocker_family_missing_item_count"
            )
        )
    )
    if not missing_item_count:
        missing_item_count = sum(
            [
                _as_int(pocketmd_summary.get("phase4_missing_candidate_slot_count")),
                _as_int(
                    pocketmd_summary.get(
                        "template_preflight_role_receipt_blocked_count"
                    )
                ),
                _as_int(
                    pocketmd_summary.get(
                        "template_preflight_operator_input_source_receipt_blocked_count"
                    )
                ),
                _as_int(
                    pocketmd_summary.get(
                        "rows_from_receipt_bundle_metric_family_missing_field_occurrence_count"
                    )
                ),
            ]
        )
    return {
        "operator_blocker_family_count": family_count,
        "operator_blocker_family_blocked_count": blocked_count,
        "operator_blocker_family_missing_item_count": missing_item_count,
    }


def _science_row_audit_component(
    science_row_audit: dict[str, Any],
    component_id: str,
) -> dict[str, Any]:
    for row in _as_list(science_row_audit.get("components")):
        if not isinstance(row, dict):
            continue
        if str(row.get("component_id") or "") == component_id:
            return row
    return {}


def _phase2_requirement_summary_row(
    row: dict[str, Any],
    phase2_row_input_status: dict[str, str],
) -> dict[str, Any]:
    row_inputs = [
        str(item)
        for item in (
            _as_list(row.get("row_inputs"))
            or _as_list(row.get("required_row_inputs"))
        )
    ]
    row_input_status = _as_dict(row.get("row_input_status"))
    if not row_input_status:
        row_input_status = {
            row_input_id: phase2_row_input_status.get(row_input_id, "")
            for row_input_id in row_inputs
        }
    ready = _as_bool(row.get("ready"))
    if "pass" in row:
        pass_value = _as_bool(row.get("pass"))
    elif "contract_pass" in row:
        pass_value = ready and _as_bool(row.get("contract_pass"))
    else:
        pass_value = ready
    return {
        "requirement": str(row.get("requirement") or ""),
        "requirement_id": str(row.get("requirement_id") or ""),
        "component_id": str(row.get("component_id") or ""),
        "criterion_id": str(row.get("criterion_id") or ""),
        "status": str(row.get("status") or ""),
        "ready": ready,
        "pass": pass_value,
        "operator_evidence_required": _as_bool(
            row.get("operator_evidence_required")
        ),
        "current_count": _as_int(row.get("current_count")),
        "required_minimum_count": _as_int(row.get("required_minimum_count")),
        "row_inputs": row_inputs,
        "row_input_status": row_input_status,
        "blockers": [str(item) for item in _as_list(row.get("blockers"))],
    }


def _phase4_requirement_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": str(row.get("requirement_id") or ""),
        "criterion_id": str(
            row.get("phase4_criterion_id") or row.get("criterion_id") or ""
        ),
        "product_requirement": str(row.get("product_requirement") or ""),
        "evidence_kind": str(row.get("evidence_kind") or ""),
        "status": str(row.get("status") or ""),
        "pass": _as_bool(row.get("pass")),
        "current": row.get("current"),
        "required": row.get("required"),
        "summary_field": str(row.get("summary_field") or ""),
        "blocker_id": str(row.get("blocker_id") or ""),
        "blockers": [str(item) for item in _as_list(row.get("blockers"))],
    }


def _phase4_metric_criterion_row(
    row: dict[str, Any],
    requirement_by_criterion: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    criterion_id = str(row.get("criterion_id") or "")
    requirement = _as_dict(requirement_by_criterion.get(criterion_id))
    return {
        "criterion_id": criterion_id,
        "requirement_id": str(requirement.get("requirement_id") or ""),
        "product_requirement": str(requirement.get("product_requirement") or ""),
        "status": str(requirement.get("status") or row.get("status") or ""),
        "pass": _as_bool(requirement.get("pass")),
        "current": requirement.get("current", row.get("current")),
        "required": requirement.get(
            "required",
            str(row.get("required_value_policy") or ""),
        ),
        "summary_field": str(requirement.get("summary_field") or ""),
        "materialized_report_field": str(row.get("materialized_report_field") or ""),
        "metric_id": str(row.get("metric_id") or ""),
        "receipt_roles": [str(item) for item in _as_list(row.get("receipt_roles"))],
        "required_row_fields": [
            str(item) for item in _as_list(row.get("required_row_fields"))
        ],
        "required_value_policy": str(row.get("required_value_policy") or ""),
        "blockers": [
            str(item)
            for item in (
                _as_list(requirement.get("blockers")) or _as_list(row.get("blockers"))
            )
        ],
    }


def _phase4_candidate_slot_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": str(row.get("slot_id") or ""),
        "case_id": str(row.get("case_id") or ""),
        "top_k_rank": _as_int(row.get("top_k_rank")),
        "candidate_scope": str(row.get("candidate_scope") or ""),
        "status": str(row.get("status") or ""),
        "missing": _as_bool(row.get("missing")),
        "closes_phase4_criteria": [
            str(item) for item in _as_list(row.get("closes_phase4_criteria"))
        ],
        "required_metric_fields": [
            str(item) for item in _as_list(row.get("required_metric_fields"))
        ],
        "required_receipt_roles": [
            str(item) for item in _as_list(row.get("required_receipt_roles"))
        ],
        "operator_action": str(row.get("operator_action") or ""),
    }


def _science_phase4_gate_summary(
    component_audit: dict[str, Any],
    source_acquisition: dict[str, Any],
) -> dict[str, Any]:
    completion_audit = _as_dict(source_acquisition.get("phase4_completion_audit"))
    metric_rows = [
        row
        for row in _as_list(source_acquisition.get("phase4_metric_closure_matrix"))
        if isinstance(row, dict)
    ]
    candidate_rows = [
        row
        for row in _as_list(source_acquisition.get("phase4_candidate_slot_matrix"))
        if isinstance(row, dict)
    ]
    if not completion_audit and not metric_rows and not candidate_rows:
        return {}

    requirements = [
        _phase4_requirement_summary_row(row)
        for row in _as_list(completion_audit.get("requirements"))
        if isinstance(row, dict)
    ]
    requirement_by_criterion = {
        row["criterion_id"]: row
        for row in requirements
        if row.get("criterion_id")
        and row.get("criterion_id") != "broad_all_atom_fep_claims_locked"
    }
    phase4_criteria = [
        _phase4_metric_criterion_row(row, requirement_by_criterion)
        for row in metric_rows
    ]
    candidate_slot_matrix = [_phase4_candidate_slot_row(row) for row in candidate_rows]
    missing_candidate_slots = [
        row
        for row in candidate_slot_matrix
        if row["missing"] or row["status"] not in {"ready", "provided"}
    ]
    source_summary = _as_dict(source_acquisition.get("summary"))
    failed_criteria = [
        str(item) for item in _as_list(component_audit.get("failed_criteria"))
    ]
    remaining_blockers = _dedupe(
        [str(item) for item in _as_list(completion_audit.get("remaining_blockers"))]
        + [str(item) for item in _as_list(component_audit.get("blockers"))]
    )
    ready = _as_bool(completion_audit.get("pass")) and _as_bool(
        component_audit.get("actual_closure_ready")
    )
    return {
        "phase4_exit_gate_status": "ready" if ready else "blocked",
        "phase4_operator_status": str(completion_audit.get("status") or ""),
        "phase4_ready": ready,
        "phase4_failed_criteria": failed_criteria,
        "phase4_requirement_summary": {
            "actual_closure_ready": _as_bool(
                completion_audit.get("actual_closure_ready")
            ),
            "requirement_count": _as_int(completion_audit.get("requirement_count")),
            "ready_requirement_count": _as_int(
                completion_audit.get("ready_requirement_count")
            ),
            "blocked_requirement_count": _as_int(
                completion_audit.get("blocked_requirement_count")
            ),
            "blocked_requirement_ids": [
                str(item)
                for item in _as_list(completion_audit.get("blocked_requirement_ids"))
            ],
            "remaining_row_inputs": [
                str(item)
                for item in _as_list(completion_audit.get("remaining_row_inputs"))
            ],
            "remaining_operator_action": str(
                completion_audit.get("remaining_operator_action") or ""
            ),
            "remaining_blockers": remaining_blockers,
            "phase4_actual_evidence_audit_status": str(
                source_summary.get("phase4_actual_evidence_audit_status") or ""
            ),
            "phase4_actual_evidence_blocked_component_count": _as_int(
                source_summary.get("phase4_actual_evidence_blocked_component_count")
            ),
            "phase4_missing_candidate_slot_count": _as_int(
                source_summary.get("phase4_missing_candidate_slot_count")
            ),
            "phase4_actual_evidence_missing_metric_count": _as_int(
                source_summary.get("phase4_actual_evidence_missing_metric_count")
            ),
        },
        "phase4_exit_gate_criteria": phase4_criteria,
        "phase4_requirements": requirements,
        "phase4_candidate_slot_summary": {
            "candidate_slot_count": len(candidate_slot_matrix),
            "missing_candidate_slot_count": len(missing_candidate_slots),
            "missing_candidate_slot_ids": [
                str(row.get("slot_id") or "") for row in missing_candidate_slots
            ],
        },
        "phase4_candidate_slot_matrix": candidate_slot_matrix,
    }


def _science_component_gate_summary(
    component_audit: dict[str, Any],
    *,
    source_acquisition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not component_audit:
        return {}
    raw_phase2_row_closure_matrix = [
        row
        for row in _as_list(component_audit.get("phase2_row_closure_matrix"))
        if isinstance(row, dict)
    ]
    phase2_row_input_status = {
        str(row.get("row_input_id") or ""): str(row.get("status") or "")
        for row in raw_phase2_row_closure_matrix
        if str(row.get("row_input_id") or "")
    }
    phase2_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "component_id": str(row.get("component_id") or ""),
            "artifact_role": str(row.get("artifact_role") or ""),
            "pass": _as_bool(row.get("pass")),
            "current": _as_dict(row.get("current")),
            "required": _as_dict(row.get("required")),
            "blockers": [str(item) for item in _as_list(row.get("blockers"))],
        }
        for row in _as_list(component_audit.get("phase2_exit_gate_criteria"))
        if isinstance(row, dict)
    ]
    phase2_requirements = [
        _phase2_requirement_summary_row(row, phase2_row_input_status)
        for row in _as_list(component_audit.get("phase2_requirements"))
        if isinstance(row, dict)
    ]
    phase2_row_closure_matrix = [
        {
            "row_input_id": str(row.get("row_input_id") or ""),
            "status": str(row.get("status") or ""),
            "missing": _as_bool(row.get("missing")),
            "resolved_path": str(row.get("resolved_path") or ""),
            "provided_path": str(row.get("provided_path") or ""),
            "closes_phase2_criteria": [
                str(item) for item in _as_list(row.get("closes_phase2_criteria"))
            ],
            "feeds_components": [
                str(item) for item in _as_list(row.get("feeds_components"))
            ],
            "materialization_chain": [
                str(item) for item in _as_list(row.get("materialization_chain"))
            ],
            "operator_blockers_if_missing": [
                str(item)
                for item in _as_list(row.get("operator_blockers_if_missing"))
            ],
        }
        for row in raw_phase2_row_closure_matrix
    ]
    phase3_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "pass": _as_bool(row.get("pass")),
            "required": row.get("required"),
            "current_by_target": _as_dict(row.get("current_by_target")),
            "failed_targets": [
                str(item) for item in _as_list(row.get("failed_targets"))
            ],
            "blockers": [str(item) for item in _as_list(row.get("blockers"))],
        }
        for row in _as_list(component_audit.get("phase3_exit_gate_criteria"))
        if isinstance(row, dict)
    ]
    summary = {
        "component_status": str(component_audit.get("status") or ""),
        "component_contract_pass": _as_bool(component_audit.get("contract_pass")),
        "expected_rows_mode": str(component_audit.get("expected_rows_mode") or ""),
        "materialized": _as_bool(component_audit.get("materialized")),
        "rows_path": str(component_audit.get("rows_path") or ""),
        "target_count": _as_int(component_audit.get("target_count")),
        "target_pass_count": _as_int(component_audit.get("target_pass_count")),
        "outputs": _as_dict(component_audit.get("outputs")),
    }
    if phase3_criteria:
        summary.update(
            {
                "phase3_exit_gate_status": str(
                    component_audit.get("phase3_exit_gate_status") or ""
                ),
                "phase3_exit_gate_criteria": phase3_criteria,
                "phase3_failed_criteria": [
                    str(item)
                    for item in _as_list(component_audit.get("phase3_failed_criteria"))
                ],
            }
        )
    if phase2_criteria or phase2_requirements:
        phase2_requirement_summary = _as_dict(
            component_audit.get("phase2_requirement_summary")
        )
        summary.update(
            {
                "phase2_exit_gate_status": str(
                    component_audit.get("phase2_exit_gate_status") or ""
                ),
                "phase2_ready": _as_bool(component_audit.get("phase2_ready")),
                "phase2_failed_criteria": [
                    str(item)
                    for item in _as_list(component_audit.get("phase2_failed_criteria"))
                ],
                "phase2_requirement_summary": phase2_requirement_summary,
                "phase2_exit_gate_criteria": phase2_criteria,
                "phase2_requirements": phase2_requirements,
                "phase2_row_closure_matrix": phase2_row_closure_matrix,
            }
        )
    summary.update(
        _science_phase4_gate_summary(
            component_audit,
            _as_dict(source_acquisition),
        )
    )
    return summary


def _science_source_acquisition_for_component(
    science_handoff: dict[str, Any],
    component_id: str,
) -> dict[str, Any]:
    upstream = _as_dict(science_handoff.get("upstream_source_acquisition"))
    if component_id == "public_benchmark_phase2_actual_closure":
        return _as_dict(upstream.get("public_benchmark_phase2"))
    if component_id == "pocketmd_lite_topk_actual_closure":
        return _as_dict(upstream.get("pocketmd_lite"))
    return {}


def _science_first_blocker(
    *,
    science_handoff: dict[str, Any],
    component_id: str,
    operator_gaps: list[dict[str, Any]],
    actual_audit: dict[str, Any],
) -> str:
    for gap in operator_gaps:
        blockers = _as_list(_as_dict(gap.get("minimum_evidence")).get("blockers"))
        if blockers:
            return str(blockers[0])
    for blocker in _as_list(science_handoff.get("science_actual_closure_blockers")):
        blocker_text = str(blocker)
        if blocker_text.startswith(f"{component_id}::"):
            return blocker_text
    for row in _as_list(actual_audit.get("components")):
        if not isinstance(row, dict):
            continue
        blockers = _as_list(row.get("blockers"))
        if blockers:
            return str(blockers[0])
    return ""


def _science_operator_gap_register(
    *,
    component: dict[str, Any],
    contracts: list[dict[str, Any]],
    action: dict[str, Any],
    actual_audit: dict[str, Any],
    unblock_plans_by_row_input: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    component_id = str(component.get("component_id") or "")
    failed_criteria = [str(row) for row in _as_list(component.get("failed_criteria"))]
    source_blockers = [
        str(row) for row in _as_list(action.get("upstream_source_blockers"))
    ]
    gaps: list[dict[str, Any]] = []
    for contract in contracts:
        row_input_id = str(contract.get("row_input_id") or "")
        operator_blockers = [
            str(row) for row in _as_list(contract.get("operator_blockers_if_missing"))
        ]
        materialization_chain = [
            str(row) for row in _as_list(contract.get("materialization_chain"))
        ]
        unblock_plan = _as_dict(unblock_plans_by_row_input.get(row_input_id))
        first_unblock_action = _as_dict(
            unblock_plan.get("first_refinement_receipt_action")
            or unblock_plan.get("first_runtime_action")
        )
        materialization_command = str(
            unblock_plan.get("materialization_command")
            or contract.get("materialization_command")
            or ""
        )
        first_next_action = str(
            unblock_plan.get("next_action") or contract.get("operator_action") or ""
        )
        gaps.append(
            {
                "handoff_id": f"science_actual_closure::{row_input_id}",
                "slot_id": row_input_id,
                "target_id": component_id,
                "status": "operator_rows_required",
                "blocked_criteria": failed_criteria,
                "first_next_action": first_next_action,
                "command_key": str(unblock_plan.get("command_key") or ""),
                "first_unblock_action": first_unblock_action,
                "template_artifact": str(contract.get("row_template_artifact") or ""),
                "minimum_evidence": {
                    "accepted_formats": [
                        str(row) for row in _as_list(contract.get("accepted_formats"))
                    ],
                    "preferred_default_row_path": str(
                        contract.get("preferred_default_row_path") or ""
                    ),
                    "contract_field_groups": _as_dict(
                        contract.get("contract_field_groups")
                    ),
                    "contract_policies": _as_dict(contract.get("contract_policies")),
                    "actual_evidence_audit_status": str(
                        actual_audit.get("status") or ""
                    ),
                    "actual_evidence_blocked_component_count": _as_int(
                        actual_audit.get("blocked_component_count")
                    ),
                    "actual_evidence_remaining_evidence": [
                        str(row)
                        for row in _as_list(actual_audit.get("remaining_evidence"))
                    ],
                    "blockers": operator_blockers or source_blockers,
                },
                "materialization_steps": materialization_chain,
                "materialization_command": materialization_command,
                "validation_command": materialization_command,
                "actual_evidence_audit_status": str(actual_audit.get("status") or ""),
                "actual_evidence_blocked_component_count": _as_int(
                    actual_audit.get("blocked_component_count")
                ),
                "actual_evidence_remaining_evidence": [
                    str(row) for row in _as_list(actual_audit.get("remaining_evidence"))
                ],
                "source_acquisition_blockers": source_blockers,
            }
        )
    return gaps


def _science_actual_closure_rows(
    *,
    science_handoff: dict[str, Any],
    science_row_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    progress = _as_dict(
        science_handoff.get("science_actual_closure_completion_progress")
    )
    component_rows = [
        row for row in _as_list(progress.get("component_progress")) if isinstance(row, dict)
    ]
    if not component_rows:
        return []

    contracts_by_component = _science_row_contracts_by_component(science_handoff)
    actions_by_component = _science_actions_by_component(science_handoff)
    audit_summary = _as_dict(science_row_audit.get("summary"))
    unblock_plans_by_row_input = {
        str(row.get("row_input_id") or ""): row
        for row in _as_list(science_handoff.get("blocking_input_unblock_plan"))
        if isinstance(row, dict) and str(row.get("row_input_id") or "")
    }
    rows: list[dict[str, Any]] = []
    for component in component_rows:
        component_id = str(component.get("component_id") or "")
        phase = _as_dict(SCIENCE_ACTUAL_CLOSURE_COMPONENT_PHASES.get(component_id))
        if not phase:
            continue
        actual_ready = _as_bool(component.get("actual_closure_ready"))
        component_audit = _science_row_audit_component(
            science_row_audit,
            component_id,
        )
        source_acquisition = _science_source_acquisition_for_component(
            science_handoff,
            component_id,
        )
        component_gate_summary = _science_component_gate_summary(
            component_audit,
            source_acquisition=source_acquisition,
        )
        actual_audit = _science_actual_audit_for_component(science_handoff, component_id)
        action = _as_dict(actions_by_component.get(component_id))
        operator_gaps = _science_operator_gap_register(
            component=component,
            contracts=contracts_by_component.get(component_id, []),
            action=action,
            actual_audit=actual_audit,
            unblock_plans_by_row_input=unblock_plans_by_row_input,
        )
        source_blockers = _science_source_blockers_for_component(
            science_handoff,
            component_id,
        )
        first_gap = operator_gaps[0] if operator_gaps else {}
        first_blocker = _science_first_blocker(
            science_handoff=science_handoff,
            component_id=component_id,
            operator_gaps=operator_gaps,
            actual_audit=actual_audit,
        )
        next_actions = _dedupe(
            [str(first_gap.get("first_next_action") or "")]
            + [str(row) for row in _as_list(science_handoff.get("operator_next_actions"))]
        )
        rows.append(
            _roadmap_row(
                phase_id=str(phase.get("phase_id") or ""),
                phase_label=str(phase.get("phase_label") or ""),
                roadmap_item=str(phase.get("roadmap_item") or ""),
                state="ready" if actual_ready else "blocked",
                bottleneck="" if actual_ready else str(phase.get("bottleneck") or ""),
                first_blocker="" if actual_ready else first_blocker,
                first_blocked_target="" if actual_ready else component_id,
                root_cause_tags=[
                    str(row) for row in _as_list(phase.get("root_cause_tags"))
                ],
                evidence_artifacts=[
                    Path(str(row)) for row in _as_list(phase.get("evidence_artifacts"))
                ],
                linked_routes=["/goal/bottleneck", "/goal/roadmap"],
                next_actions=[] if actual_ready else next_actions,
                blocked_criteria=[
                    str(row) for row in _as_list(component.get("failed_criteria"))
                ],
                summary={
                    "component_id": component_id,
                    "status": str(component.get("status") or ""),
                    "actual_closure_ready": actual_ready,
                    "requirement_count": _as_int(component.get("requirement_count")),
                    "requirement_pass_count": _as_int(
                        component.get("requirement_pass_count")
                    ),
                    "failed_criteria": [
                        str(row) for row in _as_list(component.get("failed_criteria"))
                    ],
                    "missing_row_inputs": [
                        str(row) for row in _as_list(component.get("missing_row_inputs"))
                    ],
                    "first_operator_evidence_gap": first_gap,
                    "operator_evidence_gap_register": operator_gaps,
                    "operator_evidence_gap_count": len(operator_gaps),
                    "actual_evidence_audit": actual_audit,
                    "actual_evidence_audit_status": str(
                        actual_audit.get("status") or ""
                    ),
                    "actual_evidence_blocked_component_count": _as_int(
                        actual_audit.get("blocked_component_count")
                    ),
                    "component_gate_summary": component_gate_summary,
                    "phase3_exit_gate": _as_dict(
                        {
                            key: component_gate_summary[key]
                            for key in (
                                "phase3_exit_gate_status",
                                "phase3_exit_gate_criteria",
                                "phase3_failed_criteria",
                            )
                            if key in component_gate_summary
                        }
                    ),
                    "phase4_exit_gate": _as_dict(
                        {
                            key: component_gate_summary[key]
                            for key in (
                                "phase4_exit_gate_status",
                                "phase4_operator_status",
                                "phase4_ready",
                                "phase4_failed_criteria",
                                "phase4_requirement_summary",
                                "phase4_exit_gate_criteria",
                                "phase4_requirements",
                                "phase4_candidate_slot_summary",
                                "phase4_candidate_slot_matrix",
                            )
                            if key in component_gate_summary
                        }
                    ),
                    "source_acquisition_blockers": source_blockers,
                    "source_acquisition_blocker_count": len(source_blockers),
                    "science_actual_closure_status": str(
                        science_handoff.get("science_actual_closure_status") or ""
                    ),
                    "science_actual_closure_contract_pass": _as_bool(
                        science_handoff.get("science_actual_closure_contract_pass")
                    ),
                    "science_actual_closure_missing_row_inputs": [
                        str(row)
                        for row in _as_list(science_handoff.get("missing_row_inputs"))
                    ],
                    "science_actual_closure_audit_summary": audit_summary,
                },
            )
        )
    return rows


def _capability_summary_rows(product_capabilities: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _as_list(product_capabilities.get("capability_rows")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "capability_id": str(row.get("capability_id") or ""),
                "title": str(row.get("title") or ""),
                "state": str(row.get("state") or ""),
                "blocker_count": _as_int(row.get("blocker_count")),
                "contract_pass": _as_bool(row.get("contract_pass")),
            }
        )
    return rows


def _roadmap_rows_by_phase(
    roadmap_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("phase_id") or ""): row
        for row in roadmap_rows
        if str(row.get("phase_id") or "")
    }


def _audit_component(
    audit: dict[str, Any],
    component_id: str,
) -> dict[str, Any]:
    for row in _as_list(audit.get("components")):
        if not isinstance(row, dict):
            continue
        if str(row.get("component_id") or "") == component_id:
            return row
    return {}


def _goal_priority_row(
    *,
    priority: int,
    priority_id: str,
    name: str,
    phase_id: str,
    roadmap_row: dict[str, Any],
    state: str,
    pass_value: bool,
    requirements: list[str],
    current: dict[str, Any],
    blockers: list[str],
    operator_next_action: str,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "priority_id": priority_id,
        "name": name,
        "phase_id": phase_id,
        "state": state,
        "pass": pass_value,
        "requirements": requirements,
        "current": current,
        "blockers": blockers,
        "operator_next_action": operator_next_action,
        "evidence_artifacts": [
            str(item) for item in _as_list(roadmap_row.get("evidence_artifacts"))
        ],
    }


def _active_thread_goal_objective_audit(
    *,
    roadmap_rows: list[dict[str, Any]],
    source_of_truth_gap_summary: dict[str, Any],
    source_of_truth_gap_evidence_matrix: list[dict[str, Any]],
    science_handoff: dict[str, Any],
) -> dict[str, Any]:
    rows_by_phase = _roadmap_rows_by_phase(roadmap_rows)
    source_row = _as_dict(rows_by_phase.get("phase_0_source_of_truth_hardening"))
    phase2_row = _as_dict(
        rows_by_phase.get("phase_2_public_benchmark_actual_closure")
    )
    phase3_row = _as_dict(rows_by_phase.get("phase_3_gpcr_hard_decoy_actual_closure"))
    phase4_row = _as_dict(
        rows_by_phase.get("phase_4_pocketmd_lite_topk_actual_closure")
    )

    source_matrix = {
        str(row.get("candidate") or ""): row
        for row in source_of_truth_gap_evidence_matrix
        if str(row.get("candidate") or "")
    }
    accuracy_row = _as_dict(source_matrix.get("accuracy_parity_scorecard"))

    upstream = _as_dict(science_handoff.get("upstream_source_acquisition"))
    public_source = _as_dict(upstream.get("public_benchmark_phase2"))
    public_summary = _as_dict(public_source.get("summary"))
    public_actual_audit = _as_dict(
        public_source.get("vina_gnina_actual_evidence_audit")
    ) or _as_dict(_as_dict(phase2_row.get("summary")).get("actual_evidence_audit"))
    manifest_component = _audit_component(
        public_actual_audit,
        "engine_input_manifest",
    )
    runtime_component = _audit_component(public_actual_audit, "engine_runtime")
    adapter_component = _audit_component(public_actual_audit, "adapter_rows")
    manifest_current = _as_dict(manifest_component.get("current"))
    runtime_current = _as_dict(runtime_component.get("current"))
    adapter_current = _as_dict(adapter_component.get("current"))
    phase2_summary = _as_dict(phase2_row.get("summary"))
    phase2_gate = _as_dict(phase2_summary.get("component_gate_summary"))
    phase2_requirement_summary = _as_dict(
        phase2_gate.get("phase2_requirement_summary")
    )

    gpcr_summary = _as_dict(phase3_row.get("summary"))
    gpcr_gate = _as_dict(gpcr_summary.get("phase3_exit_gate"))
    gpcr_criteria = {
        str(row.get("criterion_id") or ""): {
            "pass": _as_bool(row.get("pass")),
            "required": row.get("required"),
            "current_by_target": _as_dict(row.get("current_by_target")),
            "failed_targets": [
                str(item) for item in _as_list(row.get("failed_targets"))
            ],
        }
        for row in _as_list(gpcr_gate.get("phase3_exit_gate_criteria"))
        if isinstance(row, dict) and str(row.get("criterion_id") or "")
    }

    pocketmd_source = _as_dict(upstream.get("pocketmd_lite"))
    pocketmd_summary = _as_dict(pocketmd_source.get("summary"))
    pocketmd_actual_audit = _as_dict(pocketmd_source.get("phase4_actual_evidence_audit"))
    survival_component = _audit_component(
        pocketmd_actual_audit,
        "survival_metric_summary",
    )
    survival_current = _as_dict(survival_component.get("current"))
    pocketmd_operator_family_counts = _pocketmd_operator_blocker_family_counts(
        pocketmd_summary,
        pocketmd_actual_audit,
    )
    phase4_summary = _as_dict(phase4_row.get("summary"))
    phase4_gate = _as_dict(phase4_summary.get("phase4_exit_gate"))
    phase4_requirement_summary = _as_dict(
        phase4_gate.get("phase4_requirement_summary")
    )

    priority_rows = [
        _goal_priority_row(
            priority=1,
            priority_id="priority_1_source_of_truth_gap_classification",
            name="Source-of-truth gap classification",
            phase_id="phase_0_source_of_truth_hardening",
            roadmap_row=source_row,
            state="complete" if source_row.get("state") == "ready" else "blocked",
            pass_value=source_row.get("state") == "ready",
            requirements=[
                "classify five remaining source-of-truth candidates",
                "keep accuracy_parity_scorecard as a science scorecard review item",
            ],
            current={
                **source_of_truth_gap_summary,
                "accuracy_parity_scorecard_classification": str(
                    accuracy_row.get("classification") or ""
                ),
                "accuracy_parity_scorecard_freshness_policy": str(
                    accuracy_row.get("freshness_policy") or ""
                ),
                "accuracy_parity_scorecard_science_scorecard_priority_review": (
                    _as_bool(accuracy_row.get("science_scorecard_priority_review"))
                ),
            },
            blockers=[] if source_row.get("state") == "ready" else [
                str(source_row.get("first_blocker") or "")
            ],
            operator_next_action=_first_str(
                [str(item) for item in _as_list(source_row.get("next_actions"))]
            ),
        ),
        _goal_priority_row(
            priority=2,
            priority_id="priority_2_public_benchmark_phase2_actual_closure",
            name="Public benchmark Phase 2 actual closure",
            phase_id="phase_2_public_benchmark_actual_closure",
            roadmap_row=phase2_row,
            state="complete" if phase2_row.get("state") == "ready" else "blocked",
            pass_value=phase2_row.get("state") == "ready",
            requirements=[
                "CASF/PDBBind pose-success harness",
                "symmetry-aware ligand RMSD",
                "PoseBusters-style pose validity checks",
                "Vina/GNINA comparison adapter",
                "DUD-E or LIT-PCBA enrichment",
            ],
            current={
                "requirement_count": _as_int(
                    public_summary.get(
                        "phase2_harness_requirement_count",
                        phase2_requirement_summary.get("required_component_count"),
                    )
                ),
                "requirement_pass_count": _as_int(
                    public_summary.get(
                        "phase2_harness_ready_requirement_count",
                        phase2_requirement_summary.get("ready_component_count"),
                    )
                ),
                "failed_criteria": [
                    str(item) for item in _as_list(phase2_summary.get("failed_criteria"))
                ],
                "missing_row_inputs": [
                    str(item) for item in _as_list(phase2_summary.get("missing_row_inputs"))
                ],
                "input_manifest_detected": _as_bool(
                    manifest_current.get("input_manifest_detected")
                ),
                "input_manifest_syntax_ready": _as_bool(
                    manifest_current.get("input_manifest_syntax_ready")
                ),
                "input_manifest_verification_status": str(
                    manifest_current.get("input_manifest_verification_status") or ""
                ),
                "verified_case_input_count": _as_int(
                    manifest_current.get("verified_case_input_count")
                ),
                "template_completion_blocked_case_count": _as_int(
                    manifest_current.get("template_completion_blocked_case_count")
                ),
                "runtime_ready_for_engine_execution": _as_bool(
                    runtime_current.get(
                        "runtime_ready_for_engine_execution",
                        public_summary.get(
                            "vina_gnina_runtime_ready_for_engine_execution"
                        ),
                    )
                ),
                "missing_engine_ids": [
                    str(item)
                    for item in (
                        _as_list(runtime_current.get("missing_engine_ids"))
                        or _as_list(
                            public_summary.get("vina_gnina_runtime_missing_engine_ids")
                        )
                    )
                ],
                "detected_row_artifact_count": _as_int(
                    adapter_current.get(
                        "detected_row_artifact_count",
                        public_summary.get(
                            "vina_gnina_runtime_detected_row_artifact_count"
                        ),
                    )
                ),
            },
            blockers=_dedupe(
                [str(item) for item in _as_list(phase2_summary.get("failed_criteria"))]
                + [str(item) for item in _as_list(manifest_component.get("blockers"))]
                + [str(item) for item in _as_list(runtime_component.get("blockers"))]
                + [str(item) for item in _as_list(adapter_component.get("blockers"))]
            ),
            operator_next_action=_first_str(
                [str(item) for item in _as_list(phase2_row.get("next_actions"))]
            ),
        ),
        _goal_priority_row(
            priority=3,
            priority_id="priority_3_gpcr_hard_decoy_actual_closure",
            name="GPCR hard-decoy actual closure",
            phase_id="phase_3_gpcr_hard_decoy_actual_closure",
            roadmap_row=phase3_row,
            state="complete" if phase3_row.get("state") == "ready" else "blocked",
            pass_value=phase3_row.get("state") == "ready",
            requirements=[
                "ranking_pr_auc_ci_low >= 0.45",
                "top20_hit_rate >= 0.20",
                "decoys_above_positive_count == 0",
                "positive not out-anchored by top decoys",
            ],
            current={
                "requirement_count": _as_int(gpcr_summary.get("requirement_count")),
                "requirement_pass_count": _as_int(
                    gpcr_summary.get("requirement_pass_count")
                ),
                "target_pass_count": _as_int(
                    _as_dict(gpcr_summary.get("component_gate_summary")).get(
                        "target_pass_count"
                    )
                ),
                "criteria": gpcr_criteria,
            },
            blockers=[
                str(item) for item in _as_list(gpcr_summary.get("failed_criteria"))
            ],
            operator_next_action=_first_str(
                [str(item) for item in _as_list(phase3_row.get("next_actions"))]
            ),
        ),
        _goal_priority_row(
            priority=4,
            priority_id="priority_4_pocketmd_lite_topk_refinement",
            name="PocketMD Lite top-k refinement",
            phase_id="phase_4_pocketmd_lite_topk_actual_closure",
            roadmap_row=phase4_row,
            state="complete" if phase4_row.get("state") == "ready" else "blocked",
            pass_value=phase4_row.get("state") == "ready",
            requirements=[
                "PocketMD Lite is limited to upstream top-k candidates",
                "local-min survival is reported",
                "contact persistence is reported",
                "H-bond persistence is reported",
                "clash relief is reported",
                "uncertainty is reported",
            ],
            current={
                "requirement_count": _as_int(phase4_summary.get("requirement_count")),
                "requirement_pass_count": _as_int(
                    phase4_summary.get("requirement_pass_count")
                ),
                "ready_requirement_count": _as_int(
                    phase4_requirement_summary.get("ready_requirement_count")
                ),
                "blocked_requirement_count": _as_int(
                    phase4_requirement_summary.get("blocked_requirement_count")
                ),
                "missing_row_inputs": [
                    str(item) for item in _as_list(phase4_summary.get("missing_row_inputs"))
                ],
                "missing_candidate_slot_count": _as_int(
                    pocketmd_summary.get("phase4_missing_candidate_slot_count")
                ),
                "receipt_metric_family_blocked_count": _as_int(
                    pocketmd_summary.get(
                        "rows_from_receipt_bundle_metric_family_blocked_count"
                    )
                ),
                "receipt_metric_family_missing_field_occurrence_count": _as_int(
                    pocketmd_summary.get(
                        "rows_from_receipt_bundle_metric_family_missing_field_occurrence_count"
                    )
                ),
                "operator_blocker_family_count": _as_int(
                    pocketmd_operator_family_counts.get(
                        "operator_blocker_family_count"
                    )
                ),
                "operator_blocker_family_blocked_count": _as_int(
                    pocketmd_operator_family_counts.get(
                        "operator_blocker_family_blocked_count"
                    )
                ),
                "operator_blocker_family_missing_item_count": _as_int(
                    pocketmd_operator_family_counts.get(
                        "operator_blocker_family_missing_item_count"
                    )
                ),
                "ready_receipt_count": _as_int(
                    pocketmd_summary.get("rows_from_receipt_bundle_ready_receipt_count")
                ),
                "incomplete_receipt_count": _as_int(
                    pocketmd_summary.get(
                        "rows_from_receipt_bundle_incomplete_receipt_count"
                    )
                ),
                "reported_metric_count": _as_int(
                    survival_current.get("reported_metric_count")
                ),
                "required_metric_count": _as_int(
                    survival_current.get("required_metric_count")
                ),
            },
            blockers=_dedupe(
                [str(item) for item in _as_list(phase4_summary.get("failed_criteria"))]
                + [str(item) for item in _as_list(survival_component.get("blockers"))]
                + [
                    str(item)
                    for item in _as_list(phase4_summary.get("source_acquisition_blockers"))
                ]
            ),
            operator_next_action=_first_str(
                [str(item) for item in _as_list(phase4_row.get("next_actions"))]
            ),
        ),
    ]

    complete_priority_ids = [
        str(row["priority_id"]) for row in priority_rows if row["state"] == "complete"
    ]
    blocked_priority_ids = [
        str(row["priority_id"]) for row in priority_rows if row["state"] != "complete"
    ]
    operator_row_inputs_required = _dedupe(
        [
            str(item)
            for row in priority_rows
            for item in _as_list(row.get("current", {}).get("missing_row_inputs"))
        ]
    )
    return {
        "objective_id": "current_thread_goal_objective",
        "scope_policy": "current_thread_goal_objective_only",
        "status": "ready" if not blocked_priority_ids else "operator_evidence_required",
        "actual_closure_ready": not blocked_priority_ids,
        "priority_count": len(priority_rows),
        "complete_priority_count": len(complete_priority_ids),
        "blocked_priority_count": len(blocked_priority_ids),
        "complete_priority_ids": complete_priority_ids,
        "blocked_priority_ids": blocked_priority_ids,
        "operator_row_inputs_required": operator_row_inputs_required,
        "priority_rows": priority_rows,
        "claim_boundary": (
            "This audit reflects only the active thread goal priorities. It does "
            "not promote missing Vina/GNINA or PocketMD operator evidence into "
            "actual closure."
        ),
    }


def _operator_evidence_handoff_queue(roadmap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked_rows = [row for row in roadmap_rows if row["state"] != "ready"]
    queue: list[dict[str, Any]] = []
    for index, row in enumerate(blocked_rows, start=1):
        summary = _as_dict(row.get("summary"))
        first_gap = _as_dict(summary.get("first_operator_evidence_gap"))
        if not first_gap:
            continue
        phase_id = str(row.get("phase_id") or "")
        blocked_criteria = (
            _as_list(first_gap.get("blocked_tier_beta_criteria"))
            or _as_list(first_gap.get("blocked_phase3_criteria"))
            or _as_list(first_gap.get("blocked_phase4_criteria"))
        )
        queue.append(
            {
                "queue_priority": len(queue) + 1,
                "handoff_id": _operator_handoff_id(
                    namespace=str(row.get("bottleneck") or ""),
                    phase_id=phase_id,
                    slot_id=str(first_gap.get("slot_id") or ""),
                    fallback=first_gap.get("handoff_id"),
                ),
                "phase_id": phase_id,
                "capability_id": _phase_capability_id(phase_id),
                "actual_closure_component_id": _phase_actual_closure_component_id(
                    phase_id
                ),
                "phase_label": str(row.get("phase_label") or ""),
                "roadmap_item": str(row.get("roadmap_item") or ""),
                "bottleneck": str(row.get("bottleneck") or ""),
                "first_blocker": str(row.get("first_blocker") or ""),
                "first_blocked_target": str(row.get("first_blocked_target") or ""),
                "root_cause_tags": [
                    str(tag) for tag in _as_list(row.get("root_cause_tags"))
                ],
                "slot_id": str(first_gap.get("slot_id") or ""),
                "target_id": str(first_gap.get("target_id") or ""),
                "status": str(first_gap.get("status") or ""),
                "blocked_criteria": [str(item) for item in blocked_criteria],
                "first_next_action": str(
                    first_gap.get("first_next_action")
                    or _first_str([str(action) for action in _as_list(row.get("next_actions"))])
                ),
                "command_key": str(first_gap.get("command_key") or ""),
                "first_unblock_action": _as_dict(
                    first_gap.get("first_unblock_action")
                ),
                "template_artifact": str(first_gap.get("template_artifact") or ""),
                "minimum_evidence": _as_dict(first_gap.get("minimum_evidence")),
                "materialization_steps": [
                    str(step) for step in _as_list(first_gap.get("materialization_steps"))
                ],
                "materialization_command": str(first_gap.get("materialization_command") or ""),
                "validation_command": str(first_gap.get("validation_command") or ""),
                "actual_evidence_audit_status": str(
                    first_gap.get("actual_evidence_audit_status") or ""
                ),
                "actual_evidence_blocked_component_count": _as_int(
                    first_gap.get("actual_evidence_blocked_component_count")
                ),
                "actual_evidence_remaining_evidence": [
                    str(item)
                    for item in _as_list(
                        first_gap.get("actual_evidence_remaining_evidence")
                    )
                ],
                "source_acquisition_blockers": [
                    str(item)
                    for item in _as_list(first_gap.get("source_acquisition_blockers"))
                ],
                "evidence_artifacts": [
                    str(path) for path in _as_list(row.get("evidence_artifacts"))
                ],
                "linked_routes": [
                    str(route) for route in _as_list(row.get("linked_routes"))
                ],
            }
        )
    return queue


def _operator_evidence_handoff_slot_queue(
    roadmap_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked_rows = [row for row in roadmap_rows if row["state"] != "ready"]
    queue: list[dict[str, Any]] = []
    for phase_index, row in enumerate(blocked_rows, start=1):
        summary = _as_dict(row.get("summary"))
        phase_id = str(row.get("phase_id") or "")
        slot_rows = [
            _as_dict(slot)
            for slot in _as_list(
                summary.get("operator_handoff_queue")
                or summary.get("operator_evidence_gap_register")
            )
            if isinstance(slot, dict)
        ]
        if not slot_rows:
            first_gap = _as_dict(summary.get("first_operator_evidence_gap"))
            if first_gap:
                slot_rows = [first_gap]
        for slot_index, slot in enumerate(slot_rows, start=1):
            blocked_criteria = (
                _as_list(slot.get("blocked_tier_beta_criteria"))
                or _as_list(slot.get("blocked_phase3_criteria"))
                or _as_list(slot.get("blocked_phase4_criteria"))
                or _as_list(slot.get("blocked_criteria"))
            )
            queue.append(
                {
                    "queue_priority": len(queue) + 1,
                    "phase_queue_priority": phase_index,
                    "slot_queue_priority": slot_index,
                    "phase_id": phase_id,
                    "capability_id": _phase_capability_id(phase_id),
                    "actual_closure_component_id": _phase_actual_closure_component_id(
                        phase_id
                    ),
                    "phase_label": str(row.get("phase_label") or ""),
                    "roadmap_item": str(row.get("roadmap_item") or ""),
                    "bottleneck": str(row.get("bottleneck") or ""),
                    "first_blocker": str(row.get("first_blocker") or ""),
                    "first_blocked_target": str(row.get("first_blocked_target") or ""),
                    "root_cause_tags": [
                        str(tag) for tag in _as_list(row.get("root_cause_tags"))
                    ],
                    "handoff_id": _operator_handoff_id(
                        namespace=str(row.get("bottleneck") or ""),
                        phase_id=phase_id,
                        slot_id=str(slot.get("slot_id") or ""),
                        fallback=slot.get("handoff_id"),
                    ),
                    "slot_id": str(slot.get("slot_id") or ""),
                    "target_id": str(slot.get("target_id") or ""),
                    "status": str(slot.get("status") or ""),
                    "blocked_criteria": [str(item) for item in blocked_criteria],
                    "first_next_action": str(slot.get("first_next_action") or ""),
                    "command_key": str(slot.get("command_key") or ""),
                    "first_unblock_action": _as_dict(
                        slot.get("first_unblock_action")
                    ),
                    "template_artifact": str(slot.get("template_artifact") or ""),
                    "minimum_evidence": _as_dict(slot.get("minimum_evidence")),
                    "materialization_steps": [
                        str(step) for step in _as_list(slot.get("materialization_steps"))
                    ],
                    "materialization_command": str(
                        slot.get("materialization_command") or ""
                    ),
                    "validation_command": str(slot.get("validation_command") or ""),
                    "actual_evidence_audit_status": str(
                        slot.get("actual_evidence_audit_status") or ""
                    ),
                    "actual_evidence_blocked_component_count": _as_int(
                        slot.get("actual_evidence_blocked_component_count")
                    ),
                    "actual_evidence_remaining_evidence": [
                        str(item)
                        for item in _as_list(
                            slot.get("actual_evidence_remaining_evidence")
                        )
                    ],
                    "source_acquisition_blockers": [
                        str(item)
                        for item in _as_list(slot.get("source_acquisition_blockers"))
                    ],
                    "evidence_artifacts": [
                        str(path) for path in _as_list(row.get("evidence_artifacts"))
                    ],
                    "linked_routes": [
                        str(route) for route in _as_list(row.get("linked_routes"))
                    ],
                }
            )
    return queue


def _human_ux_release_gate_briefing(
    *,
    human_ux_blockers: list[str],
    ux_observation_report: dict[str, Any],
    ux_observation_intake_packet: dict[str, Any],
) -> dict[str, Any]:
    report_summary = _as_dict(ux_observation_report.get("summary"))
    intake_summary = _as_dict(ux_observation_intake_packet.get("summary"))
    report_blockers = [
        str(row) for row in _as_list(ux_observation_report.get("blockers"))
    ]
    current_intake_blockers = [
        str(row)
        for row in _as_list(ux_observation_intake_packet.get("current_blockers"))
    ]
    validation_commands = _dedupe(
        [str(row) for row in _as_list(ux_observation_report.get("validation_commands"))]
        + [
            str(row)
            for row in _as_list(
                ux_observation_intake_packet.get("validation_commands")
            )
        ]
    )
    owner_action = str(
        intake_summary.get("owner_action")
        or report_summary.get("owner_action")
        or ""
    )
    return {
        "status": "blocked" if human_ux_blockers else "ready",
        "release_area_blockers": human_ux_blockers,
        "release_area_blocker_count": len(human_ux_blockers),
        "human_observation_contract_pass": _as_bool(
            ux_observation_report.get("contract_pass")
        ),
        "human_observation_reason_code": str(
            ux_observation_report.get("reason_code") or ""
        ),
        "human_observation_blocker_count": len(report_blockers),
        "human_observation_blockers": report_blockers,
        "owner_intake_contract_pass": _as_bool(
            ux_observation_intake_packet.get("contract_pass")
        ),
        "owner_intake_reason_code": str(
            ux_observation_intake_packet.get("reason_code") or ""
        ),
        "owner_intake_current_blocker_count": len(current_intake_blockers),
        "owner_intake_current_blockers": current_intake_blockers,
        "missing_field_count": len(_as_list(report_summary.get("missing_fields"))),
        "missing_fields": [
            str(row) for row in _as_list(report_summary.get("missing_fields"))
        ],
        "workflow_step_pass_count": _as_int(
            report_summary.get("workflow_step_pass_count")
        ),
        "required_workflow_step_count": _as_int(
            report_summary.get("required_workflow_step_count")
        ),
        "missing_workflow_steps": [
            str(row) for row in _as_list(report_summary.get("missing_workflow_steps"))
        ],
        "max_completion_minutes": _as_int(report_summary.get("max_completion_minutes")),
        "owner_action": owner_action,
        "plain_status": (
            "Human new-user observation evidence is still required for the UX "
            "release-area gate. Automated rehearsal or templates do not close it."
            if human_ux_blockers
            else "Human UX release-area blockers are not present."
        ),
        "evidence_artifacts": {
            "observation_report": str(DEFAULT_UX_OBSERVATION_REPORT),
            "owner_intake_packet": str(DEFAULT_UX_OBSERVATION_INTAKE_PACKET),
            "observation_source": str(
                ux_observation_report.get("observation_path")
                or ux_observation_intake_packet.get("observation_path")
                or ""
            ),
            "template": str(ux_observation_intake_packet.get("template_path") or ""),
        },
        "validation_commands": validation_commands,
        "claim_boundary": str(
            ux_observation_report.get("claim_boundary")
            or ux_observation_intake_packet.get("claim_boundary")
            or ""
        ),
    }


def _release_area_owner_handoffs(
    *,
    release_area_blockers: list[str],
    action_register: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_by_blocker = {
        str(row.get("blocker_id") or ""): row
        for row in _as_list(action_register.get("rows"))
        if isinstance(row, dict)
    }
    handoffs: list[dict[str, Any]] = []
    for blocker_id in release_area_blockers:
        row = _as_dict(rows_by_blocker.get(blocker_id))
        if not row:
            handoffs.append(
                {
                    "blocker_id": blocker_id,
                    "namespace": blocker_id.split("::", 1)[0],
                    "title": "",
                    "owner": "",
                    "handoff_state": "action_register_row_missing",
                    "external_input_required": False,
                    "owner_action": "",
                    "evidence_state": "",
                    "acceptance_criteria_count": 0,
                    "acceptance_criteria": [],
                    "evidence_artifact_keys": [],
                }
            )
            continue
        evidence_status = _as_dict(row.get("evidence_status"))
        evidence_artifacts = _as_dict(row.get("evidence_artifacts"))
        acceptance_criteria = [
            str(item) for item in _as_list(row.get("acceptance_criteria"))
        ]
        handoffs.append(
            {
                "blocker_id": blocker_id,
                "namespace": str(row.get("namespace") or blocker_id.split("::", 1)[0]),
                "title": str(row.get("title") or ""),
                "owner": str(row.get("owner") or ""),
                "handoff_state": str(row.get("handoff_state") or ""),
                "external_input_required": _as_bool(row.get("external_input_required")),
                "owner_action": str(
                    row.get("owner_action") or row.get("next_action") or ""
                ),
                "evidence_state": str(evidence_status.get("state") or ""),
                "acceptance_criteria_count": len(acceptance_criteria),
                "acceptance_criteria": acceptance_criteria,
                "evidence_artifact_keys": sorted(
                    str(key) for key in evidence_artifacts.keys()
                ),
            }
        )
    return handoffs


def _release_decision_operator_actions(
    *,
    decision: dict[str, Any],
    action_register: dict[str, Any],
    release_decision_kpis: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_rows in (
        _as_list(decision.get("operator_actions")),
        _as_list(action_register.get("release_decision_operator_actions")),
    ):
        for row in source_rows:
            if not isinstance(row, dict):
                continue
            action_id = str(row.get("action_id") or "")
            if action_id and action_id in seen:
                continue
            if action_id:
                seen.add(action_id)
            actions.append(row)

    if (
        release_decision_kpis["stale_artifact_count"] > 0
        and "refresh_release_evidence_freshness" not in seen
    ):
        actions.insert(
            0,
            {
                "action_id": "refresh_release_evidence_freshness",
                "status": "refresh_required",
                "reason": (
                    "release_evidence_freshness_report has stale or incomplete "
                    "source-of-truth blockers"
                ),
                "artifact": "release_evidence_freshness_report",
                "next_actions": ["refresh_stale_goal_artifacts"],
            },
        )

    return actions


def _non_expert_release_briefing(
    *,
    release_decision_kpis: dict[str, Any],
    release_decision_operator_actions: list[dict[str, Any]],
    pm_report: dict[str, Any],
    action_register: dict[str, Any],
    roadmap_rows: list[dict[str, Any]],
    operator_evidence_handoff_queue: list[dict[str, Any]],
    operator_evidence_handoff_slot_queue: list[dict[str, Any]],
    primary_bottleneck_row: dict[str, Any],
    ux_observation_report: dict[str, Any],
    ux_observation_intake_packet: dict[str, Any],
) -> dict[str, Any]:
    release_area_blockers = [
        str(row) for row in _as_list(pm_report.get("release_area_blockers")) if str(row)
    ]
    human_ux_blockers = [
        blocker for blocker in release_area_blockers if blocker.startswith("ux::")
    ]
    release_area_owner_handoffs = _release_area_owner_handoffs(
        release_area_blockers=release_area_blockers,
        action_register=action_register,
    )
    human_ux_release_gate = _human_ux_release_gate_briefing(
        human_ux_blockers=human_ux_blockers,
        ux_observation_report=ux_observation_report,
        ux_observation_intake_packet=ux_observation_intake_packet,
    )
    blocked_science_or_beta_rows = [
        row
        for row in roadmap_rows
        if row.get("state") != "ready"
        and "science_actual_closure" in _as_list(row.get("root_cause_tags"))
    ]
    refresh_required_actions = [
        row
        for row in release_decision_operator_actions
        if str(row.get("status") or "") == "refresh_required"
        or str(row.get("action_id") or "").startswith("refresh_")
    ]
    return {
        "audience": "non_expert_pm_operator",
        "release_allowed": _as_bool(release_decision_kpis.get("release_allowed")),
        "plain_status": (
            "Release is blocked. The product can remain in restricted alpha/beta "
            "preparation, but it must not be presented as fully release-ready."
        ),
        "primary_release_blocker": str(
            release_decision_kpis.get("first_blocker") or ""
        ),
        "refresh_required_operator_action_count": len(refresh_required_actions),
        "refresh_required_operator_actions": refresh_required_actions,
        "release_area_blocker_count": len(release_area_blockers),
        "release_area_owner_handoff_count": len(release_area_owner_handoffs),
        "release_area_owner_handoffs": release_area_owner_handoffs,
        "human_ux_blockers": human_ux_blockers,
        "human_ux_owner_action": (
            "attach a passing human new-user observation record before claiming "
            "the UX release-area gate"
            if human_ux_blockers
            else ""
        ),
        "human_ux_release_gate": human_ux_release_gate,
        "primary_roadmap_bottleneck": str(primary_bottleneck_row.get("bottleneck") or ""),
        "primary_roadmap_phase_id": str(primary_bottleneck_row.get("phase_id") or ""),
        "blocked_science_or_beta_phase_count": len(blocked_science_or_beta_rows),
        "blocked_science_or_beta_phases": [
            {
                "phase_id": str(row.get("phase_id") or ""),
                "roadmap_item": str(row.get("roadmap_item") or ""),
                "bottleneck": str(row.get("bottleneck") or ""),
                "first_blocker": str(row.get("first_blocker") or ""),
                "first_blocked_target": str(row.get("first_blocked_target") or ""),
            }
            for row in blocked_science_or_beta_rows
        ],
        "next_owner_handoff_count": len(operator_evidence_handoff_queue),
        "first_operator_handoff": (
            operator_evidence_handoff_queue[0]
            if operator_evidence_handoff_queue
            else {}
        ),
        "next_owner_handoff_slot_count": len(operator_evidence_handoff_slot_queue),
        "first_operator_handoff_slot": (
            operator_evidence_handoff_slot_queue[0]
            if operator_evidence_handoff_slot_queue
            else {}
        ),
        "claim_boundaries": [
            "do_not_claim_limited_commercial_release_until_release_allowed_true",
            "do_not_replace_human_ux_observation_with_templates_or_automation",
            "do_not_claim_science_actual_closure_until_operator_rows_pass",
        ],
    }


def build_goal_bottleneck_roadmap_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    pm_report = _load_json(repo_root, DEFAULT_PM_REPORT)
    action_register = _load_json(repo_root, DEFAULT_ACTION_REGISTER)
    freshness = _load_json(repo_root, DEFAULT_FRESHNESS_REPORT)
    source_of_truth_gap = _load_json(
        repo_root,
        DEFAULT_SOURCE_OF_TRUTH_GAP_CLASSIFICATION,
    )
    science_row_audit = _load_json(repo_root, DEFAULT_SCIENCE_ACTUAL_CLOSURE_ROW_AUDIT)
    science_handoff = _load_json(
        repo_root,
        DEFAULT_SCIENCE_ACTUAL_CLOSURE_OPERATOR_HANDOFF,
    )
    product_capabilities = _load_json(repo_root, DEFAULT_PRODUCT_CAPABILITIES)
    ux_observation_report = _load_json(repo_root, DEFAULT_UX_OBSERVATION_REPORT)
    ux_observation_intake_packet = _load_json(
        repo_root, DEFAULT_UX_OBSERVATION_INTAKE_PACKET
    )

    decision = _as_dict(pm_report.get("release_decision"))
    release_decision_kpis = {
        "release_allowed": _as_bool(decision.get("release_allowed")),
        "blocked_release_count": _as_int(decision.get("blocked_release_count")),
        "first_blocker": str(decision.get("first_blocker") or ""),
        "operator_action_count": _as_int(decision.get("operator_action_count")),
        "approval_token_count": _as_int(decision.get("approval_token_count")),
        "stale_artifact_count": _as_int(decision.get("stale_artifact_count")),
        "evidence_surface_count": _as_int(decision.get("evidence_surface_count")),
        "missing_evidence_surface_count": _as_int(
            decision.get("missing_evidence_surface_count")
        ),
        "locked_evidence_surface_count": _as_int(decision.get("locked_evidence_surface_count")),
        "public_benchmark_ready": _as_bool(decision.get("public_benchmark_ready")),
    }

    roadmap_rows = [
        _source_of_truth_row(freshness),
        _release_cockpit_row(
            decision=decision,
            action_register=action_register,
            product_capabilities=product_capabilities,
        ),
        *_science_actual_closure_rows(
            science_handoff=science_handoff,
            science_row_audit=science_row_audit,
        ),
    ]
    blocked_roadmap_rows = [row for row in roadmap_rows if row["state"] != "ready"]
    primary_bottleneck_row = next(
        (row for row in roadmap_rows if row["state"] != "ready"),
        blocked_roadmap_rows[0] if blocked_roadmap_rows else {},
    )
    primary_bottleneck = str(primary_bottleneck_row.get("bottleneck") or "")
    science_bottlenecks = [
        str(row.get("bottleneck") or "")
        for row in roadmap_rows
        if row.get("state") != "ready"
        and "science_actual_closure" in _as_list(row.get("root_cause_tags"))
        and str(row.get("bottleneck") or "")
    ]
    source_of_truth_gap_classification = [
        {
            "candidate": str(row.get("candidate") or ""),
            "classification": str(row.get("classification") or ""),
            "freshness_policy": str(row.get("freshness_policy") or ""),
            "freshness_label": str(row.get("freshness_label") or ""),
            "current_repo_match": str(row.get("current_repo_match") or ""),
            "decision": str(row.get("decision") or ""),
            "validation_basis": [
                str(item) for item in _as_list(row.get("validation_basis"))
            ],
        }
        for row in _as_list(freshness.get("source_of_truth_gap_classification"))
        if isinstance(row, dict)
    ]
    source_of_truth_gap_evidence_matrix = [
        {
            "candidate": str(row.get("candidate") or ""),
            "classification": str(row.get("classification") or ""),
            "status": str(row.get("status") or ""),
            "contract_pass": bool(row.get("contract_pass")),
            "freshness_policy": str(row.get("freshness_policy") or ""),
            "freshness_label": str(row.get("freshness_label") or ""),
            "source_tracking_mode": str(row.get("source_tracking_mode") or ""),
            "source_tracking_verified": bool(
                row.get("source_tracking_verified")
            ),
            "operator_action": str(row.get("operator_action") or ""),
            "current_repo_paths": [
                str(item) for item in _as_list(row.get("current_repo_paths"))
            ],
            "failed_live_checks": [
                str(item) for item in _as_list(row.get("failed_live_checks"))
            ],
            "science_scorecard_priority_review": bool(
                row.get("science_scorecard_priority_review")
            ),
        }
        for row in _as_list(source_of_truth_gap.get("classification_evidence_matrix"))
        if isinstance(row, dict)
    ]
    freshness_summary = _as_dict(freshness.get("summary"))
    source_of_truth_gap_summary = {
        "candidate_count": _as_int(
            freshness_summary.get("source_of_truth_gap_candidate_count")
        ),
        "fix_count": _as_int(
            freshness_summary.get(
                "source_of_truth_gap_fix_count",
                freshness_summary.get("source_of_truth_gap_fixed_count"),
            )
        ),
        "no_op_count": _as_int(
            freshness_summary.get("source_of_truth_gap_no_op_count")
        ),
        "fixed_count": _as_int(
            freshness_summary.get(
                "source_of_truth_gap_fix_count",
                freshness_summary.get("source_of_truth_gap_fixed_count"),
            )
        ),
        "aggregator_review_count": _as_int(
            freshness_summary.get("source_of_truth_gap_aggregator_review_count")
        ),
    }
    active_thread_goal_objective_audit = _active_thread_goal_objective_audit(
        roadmap_rows=roadmap_rows,
        source_of_truth_gap_summary=source_of_truth_gap_summary,
        source_of_truth_gap_evidence_matrix=source_of_truth_gap_evidence_matrix,
        science_handoff=science_handoff,
    )
    handoff_source_rows = roadmap_rows
    operator_evidence_handoff_queue = _operator_evidence_handoff_queue(handoff_source_rows)
    operator_evidence_handoff_slot_queue = _operator_evidence_handoff_slot_queue(
        handoff_source_rows
    )
    release_decision_operator_actions = _release_decision_operator_actions(
        decision=decision,
        action_register=action_register,
        release_decision_kpis=release_decision_kpis,
    )
    non_expert_release_briefing = _non_expert_release_briefing(
        release_decision_kpis=release_decision_kpis,
        release_decision_operator_actions=release_decision_operator_actions,
        pm_report=pm_report,
        action_register=action_register,
        roadmap_rows=roadmap_rows,
        operator_evidence_handoff_queue=operator_evidence_handoff_queue,
        operator_evidence_handoff_slot_queue=operator_evidence_handoff_slot_queue,
        primary_bottleneck_row=primary_bottleneck_row,
        ux_observation_report=ux_observation_report,
        ux_observation_intake_packet=ux_observation_intake_packet,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=True,
            reuse_policy="goal_bottleneck_roadmap_surface_aggregates_structural_release_inputs",
            repo_root=repo_root,
        ),
        "surface_id": "goal_bottleneck_roadmap_surface",
        "surface_kind": "goal_bottleneck_roadmap_surface",
        "surface_scope": "goal_release_bottleneck_and_product_roadmap",
        "status": "ready_release_blocked"
        if not release_decision_kpis["release_allowed"]
        else "ready",
        "reason_code": "PASS_READ_MODEL_RELEASE_BLOCKED"
        if not release_decision_kpis["release_allowed"]
        else "PASS",
        "contract_pass": True,
        "read_model_ready": True,
        "mutation_allowed": False,
        "route": "/goal/bottleneck",
        "read_model": {
            "route": "/goal/bottleneck",
            "alternate_routes": ["/goal/roadmap"],
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "release_decision_kpis": release_decision_kpis,
        "source_of_truth_gap_summary": source_of_truth_gap_summary,
        "source_of_truth_gap_classification": source_of_truth_gap_classification,
        "source_of_truth_gap_evidence_matrix": source_of_truth_gap_evidence_matrix,
        "source_of_truth_gap_evidence_matrix_count": len(
            source_of_truth_gap_evidence_matrix
        ),
        "active_thread_goal_objective_audit": active_thread_goal_objective_audit,
        "science_evidence_surface_bottlenecks": science_bottlenecks,
        "science_evidence_surface_status": {
            "status": str(science_handoff.get("science_actual_closure_status") or ""),
            "contract_pass": _as_bool(
                science_handoff.get("science_actual_closure_contract_pass")
            ),
            "missing_row_inputs": [
                str(row) for row in _as_list(science_handoff.get("missing_row_inputs"))
            ],
            "completion_progress": _as_dict(
                science_handoff.get("science_actual_closure_completion_progress")
            ),
        },
        "capability_summary_rows": _capability_summary_rows(product_capabilities),
        "roadmap_rows": roadmap_rows,
        "blocked_roadmap_row_count": len(blocked_roadmap_rows),
        "primary_roadmap_bottleneck": primary_bottleneck,
        "primary_roadmap_phase_id": str(primary_bottleneck_row.get("phase_id") or ""),
        "primary_next_actions": [str(row) for row in _as_list(primary_bottleneck_row.get("next_actions"))],
        "operator_evidence_handoff_scope": "first_blocked_operator_gap_per_blocked_phase",
        "operator_evidence_handoff_count": len(operator_evidence_handoff_queue),
        "first_operator_evidence_handoff": (
            operator_evidence_handoff_queue[0]
            if operator_evidence_handoff_queue
            else {}
        ),
        "operator_evidence_handoff_queue": operator_evidence_handoff_queue,
        "operator_evidence_handoff_slot_scope": "all_blocked_operator_slots_per_blocked_phase",
        "operator_evidence_handoff_slot_count": len(
            operator_evidence_handoff_slot_queue
        ),
        "first_operator_evidence_handoff_slot": (
            operator_evidence_handoff_slot_queue[0]
            if operator_evidence_handoff_slot_queue
            else {}
        ),
        "operator_evidence_handoff_slot_queue": operator_evidence_handoff_slot_queue,
        "non_expert_release_briefing_ready": True,
        "non_expert_release_briefing": non_expert_release_briefing,
        "release_decision_operator_actions": release_decision_operator_actions,
        "next_actions": _dedupe(
            [str(row) for row in _as_list(primary_bottleneck_row.get("next_actions"))]
            + (
                ["refresh_stale_goal_artifacts"]
                if release_decision_kpis["stale_artifact_count"] > 0
                else []
            )
        ),
        "summary_line": (
            "Goal bottleneck roadmap surface: READY | "
            f"release_allowed={release_decision_kpis['release_allowed']} | "
            f"primary_bottleneck={primary_bottleneck or 'none'} | "
            f"blocked_roadmap_rows={len(blocked_roadmap_rows)}"
        ),
        "claim_boundary": (
            "This read-only /goal surface aggregates existing PM release, freshness, "
            "and structural solver product capability evidence. It does not close "
            "release, limited-commercial, GA, or engineer-of-record replacement claims."
        ),
    }


def write_goal_bottleneck_roadmap_surface(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_goal_bottleneck_roadmap_surface(repo_root=repo_root)
    resolved = out if out.is_absolute() else repo_root / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_goal_bottleneck_roadmap_surface(repo_root=args.repo_root, out=args.out)
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
