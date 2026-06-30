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
from materialize_pocketmd_lite_topk_survival_report import build_phase4_exit_gate  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_PM_REPORT = PRODUCTIZATION / "pm_release_gate_report.json"
DEFAULT_ACTION_REGISTER = PRODUCTIZATION / "pm_release_blocker_action_register.json"
DEFAULT_FRESHNESS_REPORT = PRODUCTIZATION / "release_evidence_freshness_report.json"
DEFAULT_PUBLIC_BENCHMARK = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE = (
    PRODUCTIZATION / "public_benchmark_operator_intake_packet.json"
)
DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE = (
    PRODUCTIZATION / "public_benchmark_harness_bundle.json"
)
DEFAULT_GPCR_PRODUCT_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_product_report.json"
DEFAULT_GPCR_OPERATOR_INTAKE_PACKET = (
    PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.json"
)
DEFAULT_GPCR_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_POCKETMD_SURFACE = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_POCKETMD_TOPK_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_POCKETMD_READONLY_API = PRODUCTIZATION / "pocketmd_lite_readonly_api.json"
DEFAULT_POCKETMD_DELIVERY_HANDOFF = PRODUCTIZATION / "pocketmd_lite_delivery_handoff.json"
DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET = (
    PRODUCTIZATION / "pocketmd_lite_operator_intake_packet.json"
)
DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD = (
    PRODUCTIZATION / "pocketmd_lite_operator_intake_packet.md"
)
DEFAULT_POCKETMD_OPERATOR_TEMPLATE = PRODUCTIZATION / "pocketmd_lite_operator_template.json"
DEFAULT_PRODUCT_CAPABILITIES = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_UX_OBSERVATION_REPORT = PRODUCTIZATION / "ux_new_user_observation_report.json"
DEFAULT_UX_OBSERVATION_INTAKE_PACKET = (
    PRODUCTIZATION / "ux_new_user_observation_intake_packet.json"
)
DEFAULT_OUT = PRODUCTIZATION / "goal_bottleneck_roadmap_surface.json"

SCHEMA_VERSION = "goal-bottleneck-roadmap-surface.v1"


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
        DEFAULT_PUBLIC_BENCHMARK,
        DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE,
        DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE,
        DEFAULT_GPCR_PRODUCT_REPORT,
        DEFAULT_GPCR_OPERATOR_INTAKE_PACKET,
        DEFAULT_GPCR_SURFACE,
        Path("scripts/materialize_pocketmd_lite_topk_survival_report.py"),
        DEFAULT_POCKETMD_SURFACE,
        DEFAULT_POCKETMD_TOPK_REPORT,
        DEFAULT_POCKETMD_READONLY_API,
        DEFAULT_POCKETMD_DELIVERY_HANDOFF,
        DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET,
        DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD,
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


def _first_gate_blocker(gate: dict[str, Any]) -> str:
    for criterion in _as_list(gate.get("criteria")):
        if not isinstance(criterion, dict) or _as_bool(criterion.get("pass")):
            continue
        blocker = _first_str([str(row) for row in _as_list(criterion.get("blockers"))])
        if blocker:
            return blocker
    return ""


def _action_by_bottleneck(action_register: dict[str, Any], bottleneck: str) -> dict[str, Any]:
    for row in _as_list(action_register.get("release_decision_operator_actions")):
        if isinstance(row, dict) and row.get("bottleneck") == bottleneck:
            return row
    return {}


def _capability_by_id(product_capabilities: dict[str, Any], capability_id: str) -> dict[str, Any]:
    for row in _as_list(product_capabilities.get("capability_rows")):
        if isinstance(row, dict) and row.get("capability_id") == capability_id:
            return row
    return {}


def _science_evidence_surface_rows(
    *,
    decision: dict[str, Any],
    product_capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    status_by_family = _as_dict(decision.get("science_evidence_surface_status"))
    capability_by_family = (
        ("h_bond", "h_bond_backmap_evidence"),
        ("gpcr", "gpcr_hard_decoy_evidence"),
        ("pocketmd_lite", "pocketmd_lite_top_k_refinement"),
    )
    rows: list[dict[str, Any]] = []
    for family, capability_id in capability_by_family:
        status = _as_dict(status_by_family.get(family))
        capability = _capability_by_id(product_capabilities, capability_id)
        capability_summary = _as_dict(capability.get("summary"))
        next_actions = [str(row) for row in _as_list(capability.get("next_actions"))]
        rows.append(
            {
                "surface_family": family,
                "surface_ids": [str(row) for row in _as_list(status.get("surface_ids"))],
                "present": _as_bool(status.get("present")),
                "status": str(status.get("status") or capability_summary.get("status") or ""),
                "bottleneck": str(status.get("bottleneck") or ""),
                "locked": (
                    _as_int(status.get("locked_count")) > 0
                    or str(status.get("status") or "") == "locked"
                    or str(capability.get("state") or "") == "blocked"
                ),
                "locked_count": _as_int(status.get("locked_count")),
                "surface_count": _as_int(status.get("surface_count")),
                "first_blocked_target": str(
                    status.get("first_blocked_target")
                    or capability_summary.get("first_blocked_target")
                    or ""
                ),
                "root_cause_tags": [
                    str(row)
                    for row in _as_list(
                        status.get("root_cause_tags")
                        or capability_summary.get("root_cause_tags")
                    )
                ],
                "capability_id": capability_id,
                "capability_state": str(capability.get("state") or ""),
                "capability_blocker_count": _as_int(capability.get("blocker_count")),
                "operator_intake_packet_status": str(
                    capability_summary.get("operator_intake_packet_status") or ""
                ),
                "operator_intake_required_slot_count": _as_int(
                    capability_summary.get("operator_intake_required_slot_count")
                ),
                "first_next_action": _first_str(next_actions),
                "evidence_artifact_count": len(_as_list(capability.get("evidence_artifacts"))),
            }
        )
    return rows


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
    science_bottlenecks = [str(row) for row in _as_list(decision.get("science_evidence_surface_bottlenecks"))]
    science_surface_rows = _science_evidence_surface_rows(
        decision=decision,
        product_capabilities=product_capabilities,
    )
    first_locked_science_surface = next(
        (row for row in science_surface_rows if row["locked"]),
        {},
    )
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
            "broad_gpcr_family_claim_safe",
        )
    )
    return _roadmap_row(
        phase_id="phase_1_goal_release_cockpit",
        phase_label="Phase 1",
        roadmap_item="/goal release cockpit",
        state="ready" if required_kpis_present else "blocked",
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
            "science_evidence_surface_bottlenecks": science_bottlenecks,
            "science_evidence_surface_status_rows": science_surface_rows,
            "first_locked_science_evidence_surface": first_locked_science_surface,
            "action_register_contract_pass": _as_bool(action_register.get("contract_pass")),
            "product_capability_count": _as_int(product_capabilities.get("capability_count")),
            "blocked_capability_count": _as_int(product_capabilities.get("blocked_capability_count")),
        },
    )


def _public_benchmark_row(
    *,
    decision: dict[str, Any],
    public_benchmark: dict[str, Any],
    public_benchmark_operator_intake: dict[str, Any],
    action_register: dict[str, Any],
    product_capabilities: dict[str, Any],
) -> dict[str, Any]:
    action = _action_by_bottleneck(action_register, "public_benchmark_source_of_truth_not_ready")
    capability = _capability_by_id(product_capabilities, "public_benchmark_harness")
    capability_summary = _as_dict(capability.get("summary"))
    blockers = [str(row) for row in _as_list(public_benchmark.get("blockers"))]
    tier_beta_gate = _as_dict(public_benchmark.get("tier_beta_gate"))
    operator_slots = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "required": _as_bool(row.get("required")),
            "depends_on_count": len(_as_list(row.get("depends_on"))),
            "template_artifact": str(row.get("template_artifact") or ""),
        }
        for row in _as_list(public_benchmark_operator_intake.get("input_slots"))
        if isinstance(row, dict)
    ]
    source_operator_summary = _as_dict(public_benchmark.get("operator_intake_packet"))
    gate_unblock_plan = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "unblocks_tier_beta_criteria": [
                str(item) for item in _as_list(row.get("unblocks_tier_beta_criteria"))
            ],
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "template_artifact": str(row.get("template_artifact") or ""),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
        }
        for row in _as_list(
            public_benchmark_operator_intake.get("gate_unblock_plan")
            or source_operator_summary.get("gate_unblock_plan")
        )
        if isinstance(row, dict)
    ]
    operator_evidence_gap_register = [
        {
            "slot_priority": _as_int(row.get("slot_priority")),
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "tier_beta_blocked": _as_bool(row.get("tier_beta_blocked")),
            "blocked_tier_beta_criteria": [
                str(item) for item in _as_list(row.get("blocked_tier_beta_criteria"))
            ],
            "first_next_action": str(row.get("first_next_action") or ""),
            "template_artifact": str(row.get("template_artifact") or ""),
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(row.get("validation_command") or ""),
            "depends_on": [str(item) for item in _as_list(row.get("depends_on"))],
        }
        for row in _as_list(public_benchmark.get("operator_evidence_gap_register"))
        if isinstance(row, dict)
    ]
    operator_handoff_queue = [
        {
            "queue_priority": _as_int(row.get("queue_priority")),
            "handoff_id": str(row.get("handoff_id") or ""),
            "route": str(row.get("route") or ""),
            "operator_intake_artifact": str(row.get("operator_intake_artifact") or ""),
            "operator_intake_markdown_artifact": str(
                row.get("operator_intake_markdown_artifact") or ""
            ),
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "first_next_action": str(row.get("first_next_action") or ""),
            "template_artifact": str(row.get("template_artifact") or ""),
            "blocked_tier_beta_criteria": [
                str(item) for item in _as_list(row.get("blocked_tier_beta_criteria"))
            ],
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(row.get("validation_command") or ""),
            "depends_on": [str(item) for item in _as_list(row.get("depends_on"))],
        }
        for row in _as_list(public_benchmark.get("operator_handoff_queue"))
        if isinstance(row, dict)
    ]
    if not operator_handoff_queue:
        operator_handoff_queue = [
            {
                "queue_priority": _as_int(row.get("slot_priority")),
                "handoff_id": f"public_benchmark::{row.get('slot_id') or ''}",
                "route": "/product/public-benchmark/operator-intake",
                "operator_intake_artifact": str(DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE),
                "operator_intake_markdown_artifact": (
                    "implementation/phase1/release_evidence/productization/"
                    "public_benchmark_operator_intake_packet.md"
                ),
                "slot_id": str(row.get("slot_id") or ""),
                "status": str(row.get("status") or ""),
                "first_next_action": str(row.get("first_next_action") or ""),
                "template_artifact": str(row.get("template_artifact") or ""),
                "blocked_tier_beta_criteria": [
                    str(item)
                    for item in _as_list(row.get("blocked_tier_beta_criteria"))
                ],
                "minimum_evidence": _as_dict(row.get("minimum_evidence")),
                "materialization_steps": [
                    str(item) for item in _as_list(row.get("materialization_steps"))
                ],
                "materialization_command": str(row.get("materialization_command") or ""),
                "validation_command": str(row.get("validation_command") or ""),
                "depends_on": [str(item) for item in _as_list(row.get("depends_on"))],
            }
            for row in operator_evidence_gap_register
            if _as_bool(row.get("tier_beta_blocked"))
        ]
    tier_beta_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "pass": _as_bool(row.get("pass")),
            "current": row.get("current"),
            "required": row.get("required"),
            "blocker_count": len(_as_list(row.get("blockers"))),
        }
        for row in _as_list(tier_beta_gate.get("criteria"))
        if isinstance(row, dict)
    ]
    tier_beta_failed_criteria = [
        str(row) for row in _as_list(tier_beta_gate.get("failed_criteria"))
    ]
    first_operator_evidence_gap = _as_dict(
        public_benchmark.get("first_operator_evidence_gap")
    )
    if not first_operator_evidence_gap:
        first_operator_evidence_gap = next(
            (
                row
                for row in operator_evidence_gap_register
                if row["tier_beta_blocked"]
            ),
            {},
        )
    source_operator_handoff_queue = [
        _as_dict(row)
        for row in _as_list(
            public_benchmark.get("operator_handoff_queue")
            or capability_summary.get("operator_handoff_queue")
        )
        if isinstance(row, dict)
    ]
    if source_operator_handoff_queue:
        operator_handoff_queue = source_operator_handoff_queue
    first_operator_handoff = _as_dict(
        public_benchmark.get("first_operator_handoff")
        or capability_summary.get("first_operator_handoff")
        or (operator_handoff_queue[0] if operator_handoff_queue else {})
    )
    first_blocked_target = str(
        action.get("first_blocked_target")
        or public_benchmark.get("first_blocked_target")
        or public_benchmark_operator_intake.get("first_blocked_target")
        or capability_summary.get("first_blocked_target")
        or first_operator_evidence_gap.get("slot_id")
        or ""
    )
    root_cause_tags = [
        str(row)
        for row in _as_list(
            action.get("root_cause_tags")
            or public_benchmark.get("root_cause_tags")
            or public_benchmark_operator_intake.get("root_cause_tags")
            or capability_summary.get("root_cause_tags")
        )
    ]
    ready = _as_bool(decision.get("public_benchmark_ready") or public_benchmark.get("public_benchmark_ready"))
    source_route = str(
        public_benchmark.get("route")
        or _as_dict(public_benchmark.get("read_model")).get("route")
        or "/product/public-benchmark"
    )
    operator_route = str(
        public_benchmark_operator_intake.get("route")
        or _as_dict(public_benchmark_operator_intake.get("read_model")).get("route")
        or _as_dict(public_benchmark.get("operator_intake_packet")).get("route")
        or "/product/public-benchmark/operator-intake"
    )
    return _roadmap_row(
        phase_id="phase_2_public_benchmark_harness",
        phase_label="Phase 2",
        roadmap_item="Public benchmark harness",
        state="ready" if ready else "blocked",
        bottleneck="" if ready else "public_benchmark_source_of_truth_not_ready",
        first_blocker=str(action.get("first_blocker") or _first_str(blockers)),
        first_blocked_target=first_blocked_target,
        root_cause_tags=root_cause_tags,
        evidence_artifacts=[
            DEFAULT_PUBLIC_BENCHMARK,
            DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE,
            DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE,
        ],
        linked_routes=[source_route, operator_route, "/product/capabilities"],
        next_actions=_dedupe(
            [str(row) for row in _as_list(action.get("next_actions"))]
            + [str(row) for row in _as_list(capability.get("next_actions"))]
            + [str(row) for row in _as_list(public_benchmark.get("next_actions"))]
            + [str(row) for row in _as_list(public_benchmark_operator_intake.get("next_actions"))]
        ),
        blocked_criteria=tier_beta_failed_criteria,
        summary={
            "status": str(public_benchmark.get("status") or ""),
            "read_model_ready": _as_bool(public_benchmark.get("read_model_ready")),
            "source_of_truth_route": source_route,
            "tier_beta_ready": _as_bool(public_benchmark.get("tier_beta_ready")),
            "public_benchmark_ready": ready,
            "blockers": blockers,
            "operator_intake_route": operator_route,
            "operator_intake_packet_status": str(
                public_benchmark_operator_intake.get("status") or ""
            ),
            "harness_bundle_index": _as_dict(
                public_benchmark.get("harness_bundle_index")
            ),
            "harness_bundle_artifact": str(DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE),
            "operator_template_artifacts": _as_dict(
                public_benchmark_operator_intake.get("operator_template_artifacts")
                or source_operator_summary.get("operator_template_artifacts")
            ),
            "operator_intake_required_slot_count": _as_int(
                public_benchmark_operator_intake.get("required_slot_count")
            ),
            "gate_unblock_plan_count": _as_int(
                public_benchmark_operator_intake.get("gate_unblock_plan_count")
                or source_operator_summary.get("gate_unblock_plan_count")
                or len(gate_unblock_plan)
            ),
            "operator_evidence_gap_count": _as_int(
                public_benchmark.get("operator_evidence_gap_count")
                or len(operator_evidence_gap_register)
            ),
            "operator_handoff_queue_count": _as_int(
                public_benchmark.get("operator_handoff_queue_count")
                or capability_summary.get("operator_handoff_queue_count")
                or len(operator_handoff_queue)
            ),
            "first_operator_handoff": first_operator_handoff,
            "operator_handoff_queue": operator_handoff_queue,
            "first_operator_evidence_gap": _as_dict(first_operator_evidence_gap),
            "minimum_subset_case_count": _as_int(
                public_benchmark_operator_intake.get("minimum_subset_case_count")
                or source_operator_summary.get("minimum_subset_case_count")
            ),
            "tier_beta_gate_status": str(tier_beta_gate.get("status") or ""),
            "tier_beta_failed_criterion_count": _as_int(
                tier_beta_gate.get("failed_criterion_count")
            ),
            "tier_beta_failed_criteria": tier_beta_failed_criteria,
            "tier_beta_gate_criteria": tier_beta_criteria,
            "operator_intake_slots": operator_slots,
            "gate_unblock_plan": gate_unblock_plan,
            "operator_evidence_gap_register": operator_evidence_gap_register,
            "subset_manifest_summary": _as_dict(public_benchmark.get("subset_manifest_summary")),
            "pose_validity_packet_summary": _as_dict(
                public_benchmark.get("pose_validity_packet_summary")
            ),
            "symmetry_rmsd_scorecard_summary": _as_dict(
                public_benchmark.get("symmetry_rmsd_scorecard_summary")
                or public_benchmark.get("symmetry_rmsd_summary")
            ),
            "enrichment_scorecard_summary": _as_dict(public_benchmark.get("enrichment_scorecard_summary")),
            "vina_gnina_comparison_adapter_summary": _as_dict(
                public_benchmark.get("vina_gnina_comparison_adapter_summary")
            ),
        },
    )


def _gpcr_row(
    *,
    decision: dict[str, Any],
    gpcr_product_report: dict[str, Any],
    gpcr_operator_intake: dict[str, Any],
    gpcr_surface: dict[str, Any],
    action_register: dict[str, Any],
    product_capabilities: dict[str, Any],
) -> dict[str, Any]:
    action = _action_by_bottleneck(action_register, "broad_gpcr_family_claim_locked")
    capability = _capability_by_id(product_capabilities, "gpcr_hard_decoy_evidence")
    broad_safe = _as_bool(
        decision.get("broad_gpcr_family_claim_safe")
        or gpcr_product_report.get("broad_gpcr_family_claim_safe")
        or gpcr_surface.get("broad_gpcr_family_claim_safe")
    )
    first_target = str(
        action.get("first_blocked_target")
        or gpcr_product_report.get("first_blocked_target")
        or gpcr_surface.get("first_blocked_target")
        or ""
    )
    root_cause_tags = [
        str(row)
        for row in _as_list(
            gpcr_product_report.get("root_cause_tags")
            or gpcr_surface.get("root_cause_tags")
            or action.get("root_cause_tags")
        )
    ]
    phase3_exit_gate = _as_dict(
        gpcr_product_report.get("phase3_exit_gate")
        or gpcr_surface.get("phase3_exit_gate")
    )
    first_blocker = str(
        gpcr_product_report.get("first_blocker")
        or _first_str([str(row) for row in _as_list(gpcr_surface.get("blockers"))])
        or _first_gate_blocker(phase3_exit_gate)
        or action.get("first_blocker")
    )
    phase3_gate_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "pass": _as_bool(row.get("pass")),
            "required": row.get("required"),
            "current_by_target": _as_dict(row.get("current_by_target")),
            "failed_targets": [
                str(target) for target in _as_list(row.get("failed_targets"))
            ],
            "blocker_count": len(_as_list(row.get("blockers"))),
        }
        for row in _as_list(phase3_exit_gate.get("criteria"))
        if isinstance(row, dict)
    ]
    phase3_failed_criteria = [
        str(row) for row in _as_list(phase3_exit_gate.get("failed_criteria"))
    ]
    operator_target_slots = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "target_id": str(row.get("target_id") or ""),
            "status": str(row.get("status") or ""),
            "required": _as_bool(row.get("required")),
            "template_artifact": str(row.get("template_artifact") or ""),
            "required_field_count": len(_as_list(row.get("required_fields"))),
        }
        for row in _as_list(gpcr_operator_intake.get("target_slots"))
        if isinstance(row, dict)
    ]
    source_operator_summary = _as_dict(gpcr_product_report.get("operator_intake_packet"))
    gate_unblock_plan = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "target_id": str(row.get("target_id") or ""),
            "status": str(row.get("status") or ""),
            "unblocks_phase3_criteria": [
                str(item) for item in _as_list(row.get("unblocks_phase3_criteria"))
            ],
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "template_artifact": str(row.get("template_artifact") or ""),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(
                row.get("validation_command") or row.get("materialization_command") or ""
            ),
        }
        for row in _as_list(
            gpcr_operator_intake.get("gate_unblock_plan")
            or source_operator_summary.get("gate_unblock_plan")
        )
        if isinstance(row, dict)
    ]
    operator_status_by_slot = {
        str(row.get("slot_id") or ""): str(row.get("status") or "")
        for row in operator_target_slots
    }
    operator_evidence_gap_register = [
        {
            "slot_priority": index,
            "handoff_id": _operator_handoff_id(
                namespace="gpcr_hard_decoy",
                phase_id="phase_3_gpcr_hard_decoy_closure",
                slot_id=str(row.get("slot_id") or ""),
                fallback=row.get("handoff_id"),
            ),
            "slot_id": str(row.get("slot_id") or ""),
            "target_id": str(row.get("target_id") or ""),
            "status": str(row.get("status") or "")
            or operator_status_by_slot.get(str(row.get("slot_id") or ""), ""),
            "phase3_blocked": not broad_safe
            and bool(_as_list(row.get("unblocks_phase3_criteria"))),
            "blocked_phase3_criteria": [
                str(item) for item in _as_list(row.get("unblocks_phase3_criteria"))
            ]
            if not broad_safe
            else [],
            "first_next_action": (
                f"fill {row.get('target_id')} hard-decoy metrics in the GPCR operator intake packet"
                if row.get("target_id")
                else "fill GPCR hard-decoy metrics in the operator intake packet"
            ),
            "template_artifact": str(row.get("template_artifact") or ""),
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(
                row.get("validation_command") or row.get("materialization_command") or ""
            ),
        }
        for index, row in enumerate(gate_unblock_plan, start=1)
    ]
    product_report_route = str(
        gpcr_product_report.get("route") or "/product/gpcr-hard-decoy-suite-report"
    )
    operator_intake_route = str(
        gpcr_operator_intake.get("route")
        or _as_dict(gpcr_operator_intake.get("read_model")).get("route")
        or _as_dict(gpcr_product_report.get("operator_intake_packet")).get("route")
        or "/product/gpcr-hard-decoy-suite-report/operator-intake"
    )
    return _roadmap_row(
        phase_id="phase_3_gpcr_hard_decoy_closure",
        phase_label="Phase 3",
        roadmap_item="GPCR hard-decoy closure",
        state="ready" if broad_safe else "blocked",
        bottleneck="" if broad_safe else "broad_gpcr_family_claim_locked",
        first_blocker="" if broad_safe else first_blocker,
        first_blocked_target=first_target,
        root_cause_tags=root_cause_tags,
        evidence_artifacts=[
            DEFAULT_GPCR_PRODUCT_REPORT,
            DEFAULT_GPCR_OPERATOR_INTAKE_PACKET,
            DEFAULT_GPCR_SURFACE,
        ],
        linked_routes=[product_report_route, operator_intake_route, "/product/capabilities"],
        next_actions=_dedupe(
            [str(row) for row in _as_list(gpcr_product_report.get("next_actions"))]
            + [str(row) for row in _as_list(gpcr_operator_intake.get("next_actions"))]
            + [str(row) for row in _as_list(capability.get("next_actions"))]
            + (["run_gpcr_hard_decoy_suite_materializer"] if not broad_safe else [])
        ),
        blocked_criteria=phase3_failed_criteria if not broad_safe else [],
        summary={
            "broad_gpcr_family_claim_safe": broad_safe,
            "target_count": _as_int(gpcr_product_report.get("target_count")),
            "target_pass_count": _as_int(gpcr_product_report.get("target_pass_count")),
            "science_claim_status": str(gpcr_product_report.get("science_claim_status") or ""),
            "product_report_ready": _as_bool(gpcr_product_report.get("read_model_ready")),
            "product_report_route": product_report_route,
            "operator_intake_route": operator_intake_route,
            "operator_intake_packet_status": str(gpcr_operator_intake.get("status") or ""),
            "operator_intake_required_slot_count": _as_int(
                gpcr_operator_intake.get("required_slot_count")
            ),
            "gate_unblock_plan_count": _as_int(
                gpcr_operator_intake.get("gate_unblock_plan_count")
                or source_operator_summary.get("gate_unblock_plan_count")
                or len(gate_unblock_plan)
            ),
            "minimum_target_count": _as_int(
                gpcr_operator_intake.get("minimum_target_count")
                or source_operator_summary.get("minimum_target_count")
            ),
            "minimum_metric_field_count_per_target": _as_int(
                gpcr_operator_intake.get("minimum_metric_field_count_per_target")
                or source_operator_summary.get("minimum_metric_field_count_per_target")
            ),
            "phase3_exit_gate_status": str(phase3_exit_gate.get("status") or ""),
            "phase3_failed_criterion_count": _as_int(
                phase3_exit_gate.get("failed_criterion_count")
            ),
            "phase3_failed_criteria": phase3_failed_criteria,
            "phase3_exit_gate_criteria": phase3_gate_criteria,
            "operator_target_slots": operator_target_slots,
            "gate_unblock_plan": gate_unblock_plan,
            "operator_evidence_gap_count": len(operator_evidence_gap_register),
            "first_operator_evidence_gap": (
                operator_evidence_gap_register[0]
                if operator_evidence_gap_register
                else {}
            ),
            "operator_evidence_gap_register": operator_evidence_gap_register,
        },
    )


def _pocketmd_row(
    *,
    decision: dict[str, Any],
    pocketmd_surface: dict[str, Any],
    pocketmd_topk_report: dict[str, Any],
    pocketmd_readonly_api: dict[str, Any],
    pocketmd_delivery_handoff: dict[str, Any],
    pocketmd_operator_intake: dict[str, Any],
    product_capabilities: dict[str, Any],
) -> dict[str, Any]:
    linkage = _as_dict(pocketmd_surface.get("goal_roadmap_linkage"))
    capability = _capability_by_id(product_capabilities, "pocketmd_lite_top_k_refinement")
    phase4_exit_gate = _as_dict(
        pocketmd_surface.get("phase4_exit_gate")
        or pocketmd_topk_report.get("phase4_exit_gate")
    )
    if not phase4_exit_gate:
        phase4_exit_gate = build_phase4_exit_gate(
            summary=_as_dict(pocketmd_topk_report.get("summary")),
            blockers=[str(row) for row in _as_list(pocketmd_topk_report.get("blockers"))],
            product_surface_ready=bool(
                pocketmd_topk_report.get("product_surface_ready")
                and pocketmd_topk_report.get("contract_pass")
            ),
            first_blocked_target=str(
                pocketmd_topk_report.get("first_blocked_target")
                or pocketmd_surface.get("first_blocked_target")
                or "top_k_refinement_operator_intake"
            ),
        )
    first_blocker = str(
        _first_gate_blocker(phase4_exit_gate)
        or _first_str([str(row) for row in _as_list(pocketmd_surface.get("blockers"))])
        or _first_str([str(row) for row in _as_list(pocketmd_topk_report.get("blockers"))])
    )
    ready = _as_bool(
        decision.get("pocketmd_lite_product_surface_ready")
        or pocketmd_surface.get("product_surface_ready")
    )
    operator_intake_route = str(
        pocketmd_operator_intake.get("route")
        or _as_dict(pocketmd_operator_intake.get("read_model")).get("route")
        or "/product/pocketmd-lite/operator-intake"
    )
    operator_intake_slots = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "required": _as_bool(row.get("required")),
            "required_case_field_count": len(_as_list(row.get("required_case_fields"))),
            "template_artifact": str(row.get("template_artifact") or ""),
        }
        for row in _as_list(pocketmd_operator_intake.get("input_slots"))
        if isinstance(row, dict)
    ]
    gate_unblock_plan = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "unblocks_phase4_criteria": [
                str(item) for item in _as_list(row.get("unblocks_phase4_criteria"))
            ],
            "preserves_phase4_criteria": [
                str(item) for item in _as_list(row.get("preserves_phase4_criteria"))
            ],
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "template_artifact": str(row.get("template_artifact") or ""),
            "raw_row_importer": _as_dict(row.get("raw_row_importer")),
            "raw_row_import_command": str(row.get("raw_row_import_command") or ""),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(
                row.get("validation_command") or row.get("materialization_command") or ""
            ),
        }
        for row in _as_list(pocketmd_operator_intake.get("gate_unblock_plan"))
        if isinstance(row, dict)
    ]
    operator_status_by_slot = {
        str(row.get("slot_id") or ""): str(row.get("status") or "")
        for row in operator_intake_slots
    }
    operator_evidence_gap_register = [
        {
            "slot_priority": index,
            "handoff_id": _operator_handoff_id(
                namespace="pocketmd_lite",
                phase_id="phase_4_pocketmd_lite",
                slot_id=str(row.get("slot_id") or ""),
                fallback=row.get("handoff_id"),
            ),
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or "")
            or operator_status_by_slot.get(str(row.get("slot_id") or ""), ""),
            "phase4_blocked": not ready
            and bool(_as_list(row.get("unblocks_phase4_criteria"))),
            "blocked_phase4_criteria": [
                str(item) for item in _as_list(row.get("unblocks_phase4_criteria"))
            ]
            if not ready
            else [],
            "first_next_action": "attach top-k candidate refinement rows",
            "template_artifact": str(row.get("template_artifact") or ""),
            "raw_row_importer": _as_dict(row.get("raw_row_importer")),
            "raw_row_import_command": str(row.get("raw_row_import_command") or ""),
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(
                row.get("validation_command") or row.get("materialization_command") or ""
            ),
            "preserves_phase4_criteria": [
                str(item) for item in _as_list(row.get("preserves_phase4_criteria"))
            ],
        }
        for index, row in enumerate(gate_unblock_plan, start=1)
    ]
    phase4_failed_criteria = [
        str(row) for row in _as_list(phase4_exit_gate.get("failed_criteria"))
    ]
    return _roadmap_row(
        phase_id="phase_4_pocketmd_lite",
        phase_label="Phase 4",
        roadmap_item=str(linkage.get("roadmap_item") or "PocketMD Lite science product surface"),
        state="ready" if ready else "blocked",
        bottleneck=("" if ready else str(linkage.get("bottleneck") or "pocketmd_lite_science_product_surface_locked")),
        first_blocker="" if ready else first_blocker,
        first_blocked_target=str(pocketmd_surface.get("first_blocked_target") or ""),
        root_cause_tags=[str(row) for row in _as_list(pocketmd_surface.get("root_cause_tags"))],
        evidence_artifacts=[
            PRODUCTIZATION / "pocketmd_lite_contract.json",
            PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json",
            DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET,
            DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD,
            DEFAULT_POCKETMD_OPERATOR_TEMPLATE,
            DEFAULT_POCKETMD_READONLY_API,
            DEFAULT_POCKETMD_DELIVERY_HANDOFF,
            DEFAULT_POCKETMD_SURFACE,
        ],
        linked_routes=[
            "/product/pocketmd-lite",
            operator_intake_route,
            "/product/pocketmd-lite/handoff",
            "/product/capabilities",
        ],
        next_actions=_dedupe(
            [str(row) for row in _as_list(linkage.get("next_goal_actions"))]
            + [str(row) for row in _as_list(pocketmd_operator_intake.get("next_actions"))]
            + [str(row) for row in _as_list(pocketmd_surface.get("next_actions"))]
            + [str(row) for row in _as_list(capability.get("next_actions"))]
        ),
        blocked_criteria=phase4_failed_criteria if not ready else [],
        summary={
            "product_surface_ready": ready,
            "surface_status": str(pocketmd_surface.get("status") or ""),
            "readonly_api_status": str(pocketmd_readonly_api.get("status") or ""),
            "readonly_api_route": str(
                pocketmd_readonly_api.get("route")
                or _as_dict(pocketmd_readonly_api.get("read_model")).get("route")
                or ""
            ),
            "readonly_api_endpoint_count": len(
                _as_list(pocketmd_readonly_api.get("endpoints"))
            ),
            "handoff_status": str(pocketmd_delivery_handoff.get("status") or ""),
            "handoff_route": str(
                pocketmd_delivery_handoff.get("route")
                or _as_dict(pocketmd_delivery_handoff.get("read_model")).get("route")
                or ""
            ),
            "handoff_acceptance_criteria_count": len(
                _as_list(pocketmd_delivery_handoff.get("acceptance_criteria"))
            ),
            "handoff_phase4_exit_gate_required_status": str(
                _as_dict(
                    pocketmd_delivery_handoff.get("phase4_exit_gate_reference")
                ).get("required_status")
                or ""
            ),
            "operator_intake_packet_status": str(pocketmd_operator_intake.get("status") or ""),
            "operator_intake_route": operator_intake_route,
            "operator_template_artifact": str(
                _as_dict(pocketmd_operator_intake.get("linked_artifacts")).get(
                    "operator_template"
                )
                or ""
            ),
            "operator_intake_required_slot_count": _as_int(
                pocketmd_operator_intake.get("required_slot_count")
            ),
            "operator_intake_slots": operator_intake_slots,
            "gate_unblock_plan_count": _as_int(
                pocketmd_operator_intake.get("gate_unblock_plan_count")
                or len(gate_unblock_plan)
            ),
            "minimum_refinement_case_count": _as_int(
                pocketmd_operator_intake.get("minimum_refinement_case_count")
            ),
            "minimum_top_k_candidate_count": _as_int(
                pocketmd_operator_intake.get("minimum_top_k_candidate_count")
            ),
            "gate_unblock_plan": gate_unblock_plan,
            "operator_evidence_gap_count": len(operator_evidence_gap_register),
            "first_operator_evidence_gap": (
                operator_evidence_gap_register[0]
                if operator_evidence_gap_register
                else {}
            ),
            "operator_evidence_gap_register": operator_evidence_gap_register,
            "readiness_summary": _as_dict(pocketmd_surface.get("readiness_summary")),
            "phase4_exit_gate_status": str(phase4_exit_gate.get("status") or ""),
            "phase4_failed_criterion_count": _as_int(
                phase4_exit_gate.get("failed_criterion_count")
            ),
            "phase4_failed_criteria": phase4_failed_criteria,
            "broad_all_atom_fep_claim_locked": True,
        },
    )


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


def _operator_evidence_handoff_queue(roadmap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked_rows = [row for row in roadmap_rows if row["state"] != "ready"]
    queue: list[dict[str, Any]] = []
    for index, row in enumerate(blocked_rows, start=1):
        summary = _as_dict(row.get("summary"))
        first_gap = _as_dict(summary.get("first_operator_evidence_gap"))
        if not first_gap:
            continue
        blocked_criteria = (
            _as_list(first_gap.get("blocked_tier_beta_criteria"))
            or _as_list(first_gap.get("blocked_phase3_criteria"))
            or _as_list(first_gap.get("blocked_phase4_criteria"))
        )
        queue.append(
            {
                "queue_priority": index,
                "handoff_id": _operator_handoff_id(
                    namespace=str(row.get("bottleneck") or ""),
                    phase_id=str(row.get("phase_id") or ""),
                    slot_id=str(first_gap.get("slot_id") or ""),
                    fallback=first_gap.get("handoff_id"),
                ),
                "phase_id": str(row.get("phase_id") or ""),
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
                "template_artifact": str(first_gap.get("template_artifact") or ""),
                "minimum_evidence": _as_dict(first_gap.get("minimum_evidence")),
                "materialization_steps": [
                    str(step) for step in _as_list(first_gap.get("materialization_steps"))
                ],
                "materialization_command": str(first_gap.get("materialization_command") or ""),
                "validation_command": str(first_gap.get("validation_command") or ""),
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
                    "phase_id": str(row.get("phase_id") or ""),
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
                        phase_id=str(row.get("phase_id") or ""),
                        slot_id=str(slot.get("slot_id") or ""),
                        fallback=slot.get("handoff_id"),
                    ),
                    "slot_id": str(slot.get("slot_id") or ""),
                    "target_id": str(slot.get("target_id") or ""),
                    "status": str(slot.get("status") or ""),
                    "blocked_criteria": [str(item) for item in blocked_criteria],
                    "first_next_action": str(slot.get("first_next_action") or ""),
                    "template_artifact": str(slot.get("template_artifact") or ""),
                    "minimum_evidence": _as_dict(slot.get("minimum_evidence")),
                    "materialization_steps": [
                        str(step) for step in _as_list(slot.get("materialization_steps"))
                    ],
                    "materialization_command": str(
                        slot.get("materialization_command") or ""
                    ),
                    "validation_command": str(slot.get("validation_command") or ""),
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
        if row.get("phase_id")
        in {
            "phase_2_public_benchmark_harness",
            "phase_3_gpcr_hard_decoy_closure",
            "phase_4_pocketmd_lite",
        }
        and row.get("state") != "ready"
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
            "do_not_claim_tier_beta_until_public_benchmark_ready_true",
            "do_not_claim_broad_gpcr_until_broad_gpcr_family_claim_safe_true",
            "do_not_claim_pocketmd_lite_ready_until_product_surface_ready_true",
            "do_not_replace_human_ux_observation_with_templates_or_automation",
        ],
    }


def build_goal_bottleneck_roadmap_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    pm_report = _load_json(repo_root, DEFAULT_PM_REPORT)
    action_register = _load_json(repo_root, DEFAULT_ACTION_REGISTER)
    freshness = _load_json(repo_root, DEFAULT_FRESHNESS_REPORT)
    public_benchmark = _load_json(repo_root, DEFAULT_PUBLIC_BENCHMARK)
    public_benchmark_operator_intake = _load_json(
        repo_root, DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE
    )
    gpcr_product_report = _load_json(repo_root, DEFAULT_GPCR_PRODUCT_REPORT)
    gpcr_operator_intake = _load_json(repo_root, DEFAULT_GPCR_OPERATOR_INTAKE_PACKET)
    gpcr_surface = _load_json(repo_root, DEFAULT_GPCR_SURFACE)
    pocketmd_surface = _load_json(repo_root, DEFAULT_POCKETMD_SURFACE)
    pocketmd_topk_report = _load_json(repo_root, DEFAULT_POCKETMD_TOPK_REPORT)
    pocketmd_readonly_api = _load_json(repo_root, DEFAULT_POCKETMD_READONLY_API)
    pocketmd_delivery_handoff = _load_json(repo_root, DEFAULT_POCKETMD_DELIVERY_HANDOFF)
    pocketmd_operator_intake = _load_json(repo_root, DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET)
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
        "public_benchmark_ready": _as_bool(
            decision.get("public_benchmark_ready") or public_benchmark.get("public_benchmark_ready")
        ),
        "broad_gpcr_family_claim_safe": _as_bool(
            decision.get("broad_gpcr_family_claim_safe")
            or gpcr_product_report.get("broad_gpcr_family_claim_safe")
        ),
        "pocketmd_lite_product_surface_ready": _as_bool(
            decision.get("pocketmd_lite_product_surface_ready")
            or pocketmd_surface.get("product_surface_ready")
        ),
    }

    roadmap_rows = [
        _source_of_truth_row(freshness),
        _release_cockpit_row(
            decision=decision,
            action_register=action_register,
            product_capabilities=product_capabilities,
        ),
        _public_benchmark_row(
            decision=decision,
            public_benchmark=public_benchmark,
            public_benchmark_operator_intake=public_benchmark_operator_intake,
            action_register=action_register,
            product_capabilities=product_capabilities,
        ),
        _gpcr_row(
            decision=decision,
            gpcr_product_report=gpcr_product_report,
            gpcr_operator_intake=gpcr_operator_intake,
            gpcr_surface=gpcr_surface,
            action_register=action_register,
            product_capabilities=product_capabilities,
        ),
        _pocketmd_row(
            decision=decision,
            pocketmd_surface=pocketmd_surface,
            pocketmd_topk_report=pocketmd_topk_report,
            pocketmd_readonly_api=pocketmd_readonly_api,
            pocketmd_delivery_handoff=pocketmd_delivery_handoff,
            pocketmd_operator_intake=pocketmd_operator_intake,
            product_capabilities=product_capabilities,
        ),
    ]
    blocked_roadmap_rows = [row for row in roadmap_rows if row["state"] != "ready"]
    primary_bottleneck_row = next(
        (
            row
            for row in roadmap_rows
            if row["state"] != "ready"
            and row["phase_id"]
            in {
                "phase_2_public_benchmark_harness",
                "phase_3_gpcr_hard_decoy_closure",
                "phase_4_pocketmd_lite",
            }
        ),
        blocked_roadmap_rows[0] if blocked_roadmap_rows else {},
    )
    primary_bottleneck = str(primary_bottleneck_row.get("bottleneck") or "")
    science_bottlenecks = [
        str(row) for row in _as_list(decision.get("science_evidence_surface_bottlenecks"))
    ]
    source_of_truth_gap_classification = [
        {
            "candidate": str(row.get("candidate") or ""),
            "classification": str(row.get("classification") or ""),
            "freshness_policy": str(row.get("freshness_policy") or ""),
            "freshness_label": str(row.get("freshness_label") or ""),
            "current_repo_match": str(row.get("current_repo_match") or ""),
            "decision": str(row.get("decision") or ""),
        }
        for row in _as_list(freshness.get("source_of_truth_gap_classification"))
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
    operator_evidence_handoff_queue = _operator_evidence_handoff_queue(roadmap_rows)
    operator_evidence_handoff_slot_queue = _operator_evidence_handoff_slot_queue(
        roadmap_rows
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
            reuse_policy="goal_bottleneck_roadmap_surface_aggregates_pm_release_and_science_surfaces",
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
        "science_evidence_surface_bottlenecks": science_bottlenecks,
        "science_evidence_surface_status": _as_dict(decision.get("science_evidence_surface_status")),
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
            "public benchmark, GPCR, PocketMD, and product capability evidence. It does "
            "not close release, benchmark, GPCR, PocketMD, or broad MD/FEP claims."
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
