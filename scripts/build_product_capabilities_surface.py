#!/usr/bin/env python3
"""Build the product capabilities evidence surface."""

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

DEFAULT_OUT = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_PUBLIC_BENCHMARK = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE = (
    PRODUCTIZATION / "public_benchmark_operator_intake_packet.json"
)
DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD = (
    PRODUCTIZATION / "public_benchmark_operator_intake_packet.md"
)
DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE = (
    PRODUCTIZATION / "public_benchmark_harness_bundle.json"
)
DEFAULT_POCKETMD_SURFACE = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_POCKETMD_CONTRACT = PRODUCTIZATION / "pocketmd_lite_contract.json"
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
DEFAULT_H_BOND_SURFACE = SURFACE_DIR / "h_bond_backmap_evidence_surface.json"
DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET = (
    PRODUCTIZATION / "h_bond_backmap_operator_intake_packet.json"
)
DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET_MD = (
    PRODUCTIZATION / "h_bond_backmap_operator_intake_packet.md"
)
DEFAULT_GPCR_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_GPCR_PRODUCT_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_product_report.json"
DEFAULT_GPCR_OPERATOR_INTAKE_PACKET = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.json"
DEFAULT_GPCR_OPERATOR_INTAKE_PACKET_MD = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.md"

STRUCTURAL_SURFACE_PATHS = (
    SURFACE_DIR / "element_material_breadth_gate_report.json",
    SURFACE_DIR / "general_fe_contact_benchmark_gate_report.json",
    SURFACE_DIR / "material_constitutive_gate_report.json",
    SURFACE_DIR / "solver_breadth_report.json",
    SURFACE_DIR / "solver_truthfulness_gate_report.json",
    SURFACE_DIR / "steel_composite_constitutive_gate_report.json",
    SURFACE_DIR / "structural_contact_gate_report.json",
    SURFACE_DIR / "surface_interaction_benchmark_gate_report.json",
)

SCHEMA_VERSION = "product-capabilities-surface.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _truthy_contract(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass")
        or payload.get("pass")
        or str(payload.get("status", "")).strip().lower() == "ready"
    )


def _payload_blocked(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("locked") is True
        or payload.get("claim_locked") is True
        or _as_list(payload.get("blockers"))
        or not _truthy_contract(payload)
    )


def _state(payload: dict[str, Any], *, ready_flag: bool | None = None) -> str:
    if ready_flag is not None:
        return "ready" if ready_flag else "blocked"
    return "blocked" if _payload_blocked(payload) else "ready"


def _next_actions(payload: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(payload.get("next_actions"))]


def _blockers(payload: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(payload.get("blockers"))]


def _first_str(values: list[Any]) -> str:
    for value in values:
        text = str(value or "")
        if text:
            return text
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _surface_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return summary if summary else _as_dict(payload.get("readiness_summary"))


def _first_dict(values: list[Any]) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _capability_handoff_slot(summary: dict[str, Any]) -> dict[str, Any]:
    slot = (
        _as_dict(summary.get("first_operator_evidence_gap"))
        or _as_dict(summary.get("first_operator_handoff"))
        or _first_dict(_as_list(summary.get("operator_handoff_queue")))
        or _first_dict(_as_list(summary.get("operator_evidence_gap_register")))
        or _first_dict(_as_list(summary.get("gate_unblock_plan")))
        or _first_dict(_as_list(summary.get("operator_intake_slots")))
        or _first_dict(_as_list(summary.get("operator_target_slots")))
    )
    if not slot:
        return {}
    slot_id = str(slot.get("slot_id") or "")
    queue_match = {}
    for row in _as_list(summary.get("operator_handoff_queue")):
        if not isinstance(row, dict):
            continue
        if slot_id and str(row.get("slot_id") or "") == slot_id:
            queue_match = row
            break
    blocked_criteria = (
        _as_list(slot.get("blocked_tier_beta_criteria"))
        or _as_list(queue_match.get("blocked_tier_beta_criteria"))
        or _as_list(slot.get("blocked_phase3_criteria"))
        or _as_list(queue_match.get("blocked_phase3_criteria"))
        or _as_list(slot.get("blocked_phase4_criteria"))
        or _as_list(queue_match.get("blocked_phase4_criteria"))
        or _as_list(slot.get("blocked_criteria"))
        or _as_list(queue_match.get("blocked_criteria"))
        or _as_list(slot.get("unblocks_tier_beta_criteria"))
        or _as_list(queue_match.get("unblocks_tier_beta_criteria"))
        or _as_list(slot.get("unblocks_phase3_criteria"))
        or _as_list(queue_match.get("unblocks_phase3_criteria"))
        or _as_list(slot.get("unblocks_phase4_criteria"))
        or _as_list(queue_match.get("unblocks_phase4_criteria"))
    )
    return {
        "slot_id": slot_id,
        "target_id": str(slot.get("target_id") or queue_match.get("target_id") or ""),
        "handoff_id": str(slot.get("handoff_id") or queue_match.get("handoff_id") or ""),
        "status": str(slot.get("status") or queue_match.get("status") or ""),
        "blocked_criteria": [str(row) for row in blocked_criteria],
        "first_next_action": str(
            slot.get("first_next_action") or queue_match.get("first_next_action") or ""
        ),
        "template_artifact": str(
            slot.get("template_artifact") or queue_match.get("template_artifact") or ""
        ),
        "minimum_evidence": _as_dict(
            slot.get("minimum_evidence") or queue_match.get("minimum_evidence")
        ),
        "materialization_steps": [
            str(row)
            for row in (
                _as_list(slot.get("materialization_steps"))
                or _as_list(queue_match.get("materialization_steps"))
            )
        ],
        "materialization_command": str(
            slot.get("materialization_command")
            or queue_match.get("materialization_command")
            or ""
        ),
        "validation_command": str(
            slot.get("validation_command") or queue_match.get("validation_command") or ""
        ),
    }


def _blocked_capability_register(
    capability_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked_rows = [
        row
        for row in capability_rows
        if str(row.get("state") or "") != "ready"
    ]
    register: list[dict[str, Any]] = []
    for index, row in enumerate(blocked_rows, start=1):
        summary = _as_dict(row.get("summary"))
        next_actions = [str(action) for action in _as_list(row.get("next_actions"))]
        handoff_slot = _capability_handoff_slot(summary)
        first_next_action = _first_str(
            [handoff_slot.get("first_next_action"), *next_actions]
        )
        register.append(
            {
                "queue_priority": index,
                "capability_id": str(row.get("capability_id") or ""),
                "title": str(row.get("title") or ""),
                "capability_kind": str(row.get("capability_kind") or ""),
                "state": str(row.get("state") or ""),
                "contract_pass": bool(row.get("contract_pass")),
                "blocker_count": int(row.get("blocker_count") or 0),
                "first_blocked_target": str(summary.get("first_blocked_target") or ""),
                "root_cause_tags": [
                    str(tag) for tag in _as_list(summary.get("root_cause_tags"))
                ],
                "first_next_action": first_next_action,
                "operator_intake_route": str(
                    summary.get("operator_intake_route") or ""
                ),
                "operator_intake_artifact": str(
                    summary.get("operator_intake_artifact") or ""
                ),
                "operator_intake_markdown_artifact": str(
                    summary.get("operator_intake_markdown_artifact") or ""
                ),
                "operator_intake_packet_status": str(
                    summary.get("operator_intake_packet_status") or ""
                ),
                "operator_intake_required_slot_count": int(
                    summary.get("operator_intake_required_slot_count") or 0
                ),
                "gate_unblock_plan_count": int(
                    summary.get("gate_unblock_plan_count") or 0
                ),
                "handoff_slot": handoff_slot,
                "evidence_artifact_count": len(_as_list(row.get("evidence_artifacts"))),
            }
        )
    return register


def _capability_row(
    *,
    capability_id: str,
    title: str,
    capability_kind: str,
    state: str,
    evidence_artifacts: list[Path],
    contract_pass: bool,
    blocker_count: int,
    next_actions: list[str],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "title": title,
        "capability_kind": capability_kind,
        "state": state,
        "contract_pass": contract_pass,
        "blocker_count": blocker_count,
        "evidence_artifacts": [str(path) for path in evidence_artifacts],
        "next_actions": next_actions,
        "summary": summary or {},
    }


def _structural_solver_capability(repo_root: Path) -> dict[str, Any]:
    payloads = [_load_json(repo_root, path) for path in STRUCTURAL_SURFACE_PATHS]
    present_payloads = [payload for payload in payloads if payload]
    ready_count = sum(1 for payload in present_payloads if not _payload_blocked(payload))
    return _capability_row(
        capability_id="structural_solver_restricted_alpha_surface",
        title="Restricted alpha structural solver evidence",
        capability_kind="engineering_core",
        state="ready" if present_payloads and ready_count == len(STRUCTURAL_SURFACE_PATHS) else "blocked",
        evidence_artifacts=list(STRUCTURAL_SURFACE_PATHS),
        contract_pass=bool(present_payloads and ready_count == len(STRUCTURAL_SURFACE_PATHS)),
        blocker_count=len(STRUCTURAL_SURFACE_PATHS) - ready_count,
        next_actions=[] if ready_count == len(STRUCTURAL_SURFACE_PATHS) else ["refresh_structural_solver_surface_receipts"],
        summary={
            "surface_count": len(STRUCTURAL_SURFACE_PATHS),
            "present_surface_count": len(present_payloads),
            "ready_surface_count": ready_count,
        },
    )


def _public_benchmark_capability(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_PUBLIC_BENCHMARK)
    operator_intake = _load_json(repo_root, DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE)
    harness_bundle = _load_json(repo_root, DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE)
    source_operator_summary = _as_dict(payload.get("operator_intake_packet"))
    tier_beta_gate = _as_dict(payload.get("tier_beta_gate"))
    operator_slots = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "required": bool(row.get("required")),
            "depends_on_count": len(_as_list(row.get("depends_on"))),
            "template_artifact": str(row.get("template_artifact") or ""),
        }
        for row in _as_list(operator_intake.get("input_slots"))
        if isinstance(row, dict)
    ]
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
            operator_intake.get("gate_unblock_plan")
            or source_operator_summary.get("gate_unblock_plan")
        )
        if isinstance(row, dict)
    ]
    operator_evidence_gap_register = [
        {
            "slot_priority": int(row.get("slot_priority") or 0),
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "tier_beta_blocked": bool(row.get("tier_beta_blocked")),
            "blocked_tier_beta_criteria": [
                str(item) for item in _as_list(row.get("blocked_tier_beta_criteria"))
            ],
            "first_next_action": str(row.get("first_next_action") or ""),
            "template_artifact": str(row.get("template_artifact") or ""),
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
        }
        for row in _as_list(payload.get("operator_evidence_gap_register"))
        if isinstance(row, dict)
    ]
    operator_handoff_queue = [
        {
            "queue_priority": int(row.get("queue_priority") or 0),
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
        for row in _as_list(payload.get("operator_handoff_queue"))
        if isinstance(row, dict)
    ]
    if not operator_handoff_queue:
        operator_handoff_queue = [
            {
                "queue_priority": int(row.get("slot_priority") or 0),
                "handoff_id": f"public_benchmark::{row.get('slot_id') or ''}",
                "route": "/product/public-benchmark/operator-intake",
                "operator_intake_artifact": str(DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE),
                "operator_intake_markdown_artifact": str(
                    DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD
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
                "materialization_command": "",
                "validation_command": "",
                "depends_on": [],
            }
            for row in operator_evidence_gap_register
            if bool(row.get("tier_beta_blocked"))
        ]
    tier_beta_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "pass": bool(row.get("pass")),
            "current": row.get("current"),
            "required": row.get("required"),
            "blocker_count": len(_as_list(row.get("blockers"))),
        }
        for row in _as_list(tier_beta_gate.get("criteria"))
        if isinstance(row, dict)
    ]
    ready = bool(payload.get("public_benchmark_ready"))
    return _capability_row(
        capability_id="public_benchmark_harness",
        title="Public benchmark harness",
        capability_kind="external_science_evidence",
        state=_state(payload, ready_flag=ready),
        evidence_artifacts=[
            DEFAULT_PUBLIC_BENCHMARK,
            DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE,
            DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD,
            DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE,
        ],
        contract_pass=bool(_truthy_contract(payload) and ready),
        blocker_count=len(_blockers(payload)),
        next_actions=_dedupe(_next_actions(payload) + _next_actions(operator_intake)),
        summary={
            "status": str(payload.get("status") or ""),
            "read_model_ready": bool(payload.get("read_model_ready")),
            "source_of_truth_route": str(
                payload.get("route")
                or _as_dict(payload.get("read_model")).get("route")
                or ""
            ),
            "tier_beta_ready": bool(payload.get("tier_beta_ready")),
            "public_benchmark_ready": ready,
            "first_blocked_target": str(
                payload.get("first_blocked_target")
                or operator_intake.get("first_blocked_target")
                or source_operator_summary.get("first_blocked_target")
                or ""
            ),
            "root_cause_tags": [
                str(row)
                for row in _as_list(
                    payload.get("root_cause_tags")
                    or operator_intake.get("root_cause_tags")
                    or source_operator_summary.get("root_cause_tags")
                )
            ],
            "operator_intake_route": str(
                operator_intake.get("route")
                or _as_dict(operator_intake.get("read_model")).get("route")
                or source_operator_summary.get("route")
                or _as_dict(source_operator_summary.get("read_model")).get("route")
                or ""
            ),
            "operator_intake_packet_status": str(
                operator_intake.get("status") or source_operator_summary.get("status") or ""
            ),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count")
                or source_operator_summary.get("required_slot_count")
                or 0
            ),
            "gate_unblock_plan_count": int(
                operator_intake.get("gate_unblock_plan_count")
                or source_operator_summary.get("gate_unblock_plan_count")
                or len(gate_unblock_plan)
            ),
            "operator_evidence_gap_count": int(
                payload.get("operator_evidence_gap_count")
                or len(operator_evidence_gap_register)
            ),
            "first_operator_evidence_gap": _as_dict(
                payload.get("first_operator_evidence_gap")
            ),
            "operator_handoff_queue_count": int(
                payload.get("operator_handoff_queue_count")
                or len(operator_handoff_queue)
            ),
            "first_operator_handoff": _as_dict(
                payload.get("first_operator_handoff")
                or (operator_handoff_queue[0] if operator_handoff_queue else {})
            ),
            "operator_handoff_queue": operator_handoff_queue,
            "minimum_subset_case_count": int(
                operator_intake.get("minimum_subset_case_count")
                or source_operator_summary.get("minimum_subset_case_count")
                or 0
            ),
            "operator_intake_artifact": str(DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE),
            "operator_intake_markdown_artifact": str(DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD),
            "harness_bundle_artifact": str(DEFAULT_PUBLIC_BENCHMARK_HARNESS_BUNDLE),
            "harness_bundle_status": str(harness_bundle.get("status") or ""),
            "harness_bundle_artifact_count": int(harness_bundle.get("artifact_count") or 0),
            "harness_bundle_missing_artifact_count": int(
                harness_bundle.get("missing_artifact_count") or 0
            ),
            "harness_bundle_index": _as_dict(payload.get("harness_bundle_index")),
            "operator_template_artifacts": _as_dict(
                operator_intake.get("operator_template_artifacts")
                or source_operator_summary.get("operator_template_artifacts")
            ),
            "tier_beta_gate_status": str(tier_beta_gate.get("status") or ""),
            "tier_beta_failed_criterion_count": int(
                tier_beta_gate.get("failed_criterion_count") or 0
            ),
            "tier_beta_failed_criteria": [
                str(row) for row in _as_list(tier_beta_gate.get("failed_criteria"))
            ],
            "tier_beta_gate_criteria": tier_beta_criteria,
            "operator_intake_slots": operator_slots,
            "gate_unblock_plan": gate_unblock_plan,
            "operator_evidence_gap_register": operator_evidence_gap_register,
            "subset_manifest_summary": _as_dict(payload.get("subset_manifest_summary")),
            "pose_validity_packet_summary": _as_dict(
                payload.get("pose_validity_packet_summary")
            ),
            "symmetry_rmsd_scorecard_summary": _as_dict(
                payload.get("symmetry_rmsd_scorecard_summary")
                or payload.get("symmetry_rmsd_summary")
            ),
            "enrichment_scorecard_summary": _as_dict(payload.get("enrichment_scorecard_summary")),
            "vina_gnina_comparison_adapter_summary": _as_dict(
                payload.get("vina_gnina_comparison_adapter_summary")
            ),
        },
    )


def _pocketmd_capability(repo_root: Path) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_POCKETMD_SURFACE)
    contract = _load_json(repo_root, DEFAULT_POCKETMD_CONTRACT)
    topk_report = _load_json(repo_root, DEFAULT_POCKETMD_TOPK_REPORT)
    readonly_api = _load_json(repo_root, DEFAULT_POCKETMD_READONLY_API)
    delivery_handoff = _load_json(repo_root, DEFAULT_POCKETMD_DELIVERY_HANDOFF)
    operator_intake = _load_json(repo_root, DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET)
    phase4_exit_gate = _as_dict(
        surface.get("phase4_exit_gate") or topk_report.get("phase4_exit_gate")
    )
    if not phase4_exit_gate:
        phase4_exit_gate = build_phase4_exit_gate(
            summary=_as_dict(topk_report.get("summary")),
            blockers=[str(row) for row in _as_list(topk_report.get("blockers"))],
            product_surface_ready=bool(
                topk_report.get("product_surface_ready") and topk_report.get("contract_pass")
            ),
            first_blocked_target=str(
                topk_report.get("first_blocked_target")
                or surface.get("first_blocked_target")
                or "top_k_refinement_operator_intake"
            ),
            blocked_claims=[str(row) for row in _as_list(contract.get("blocked_claims"))],
        )
    phase4_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "pass": bool(row.get("pass")),
            "current": row.get("current"),
            "required": row.get("required"),
            "blocker_count": len(_as_list(row.get("blockers"))),
        }
        for row in _as_list(phase4_exit_gate.get("criteria"))
        if isinstance(row, dict)
    ]
    operator_slots = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "required": bool(row.get("required")),
            "required_field_count": len(_as_list(row.get("required_case_fields"))),
            "template_artifact": str(row.get("template_artifact") or ""),
        }
        for row in _as_list(operator_intake.get("input_slots"))
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
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(row.get("validation_command") or ""),
        }
        for row in _as_list(operator_intake.get("gate_unblock_plan"))
        if isinstance(row, dict)
    ]
    ready = bool(surface.get("product_surface_ready") and surface.get("contract_pass"))
    return _capability_row(
        capability_id="pocketmd_lite_top_k_refinement",
        title="PocketMD Lite top-k refinement",
        capability_kind="science_product_surface",
        state=_state(surface, ready_flag=ready),
        evidence_artifacts=[
            DEFAULT_POCKETMD_CONTRACT,
            DEFAULT_POCKETMD_TOPK_REPORT,
            DEFAULT_POCKETMD_READONLY_API,
            DEFAULT_POCKETMD_DELIVERY_HANDOFF,
            DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET,
            DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD,
            DEFAULT_POCKETMD_OPERATOR_TEMPLATE,
            DEFAULT_POCKETMD_SURFACE,
        ],
        contract_pass=bool(_truthy_contract(contract) and ready),
        blocker_count=len(_blockers(surface)),
        next_actions=_dedupe(_next_actions(operator_intake) + _next_actions(surface)),
        summary={
            "surface_status": str(surface.get("status") or ""),
            "first_blocked_target": str(
                topk_report.get("first_blocked_target")
                or surface.get("first_blocked_target")
                or ""
            ),
            "root_cause_tags": [
                str(row)
                for row in _as_list(
                    topk_report.get("root_cause_tags")
                    or surface.get("root_cause_tags")
                )
            ],
            "product_surface_ready": ready,
            "real_refinement_case_count": _surface_summary(surface).get("real_refinement_case_count", 0),
            "top_k_candidate_count": _surface_summary(surface).get("top_k_candidate_count", 0),
            "topk_report_status": str(topk_report.get("status") or ""),
            "readonly_api_status": str(readonly_api.get("status") or ""),
            "readonly_api_route": str(
                readonly_api.get("route")
                or _as_dict(readonly_api.get("read_model")).get("route")
                or ""
            ),
            "readonly_api_endpoint_count": len(_as_list(readonly_api.get("endpoints"))),
            "handoff_status": str(delivery_handoff.get("status") or ""),
            "handoff_route": str(
                delivery_handoff.get("route")
                or _as_dict(delivery_handoff.get("read_model")).get("route")
                or ""
            ),
            "handoff_acceptance_criteria_count": len(
                _as_list(delivery_handoff.get("acceptance_criteria"))
            ),
            "handoff_phase4_exit_gate_required_status": str(
                _as_dict(delivery_handoff.get("phase4_exit_gate_reference")).get(
                    "required_status"
                )
                or ""
            ),
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_route": str(
                operator_intake.get("route")
                or _as_dict(operator_intake.get("read_model")).get("route")
                or ""
            ),
            "operator_intake_artifact": str(DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET),
            "operator_intake_markdown_artifact": str(
                DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD
            ),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
            "operator_template_artifact": str(
                _as_dict(operator_intake.get("linked_artifacts")).get("operator_template")
                or ""
            ),
            "gate_unblock_plan_count": int(
                operator_intake.get("gate_unblock_plan_count") or len(gate_unblock_plan)
            ),
            "minimum_refinement_case_count": int(
                operator_intake.get("minimum_refinement_case_count") or 0
            ),
            "minimum_top_k_candidate_count": int(
                operator_intake.get("minimum_top_k_candidate_count") or 0
            ),
            "phase4_exit_gate_status": str(phase4_exit_gate.get("status") or ""),
            "phase4_failed_criterion_count": int(
                phase4_exit_gate.get("failed_criterion_count") or 0
            ),
            "phase4_failed_criteria": [
                str(row) for row in _as_list(phase4_exit_gate.get("failed_criteria"))
            ],
            "phase4_exit_gate_criteria": phase4_criteria,
            "first_operator_evidence_gap": _as_dict(
                topk_report.get("first_operator_evidence_gap")
            ),
            "operator_intake_slots": operator_slots,
            "gate_unblock_plan": gate_unblock_plan,
        },
    )


def _single_surface_capability(
    *,
    repo_root: Path,
    path: Path,
    capability_id: str,
    title: str,
    capability_kind: str,
    next_action_fallback: str,
) -> dict[str, Any]:
    payload = _load_json(repo_root, path)
    state = _state(payload)
    return _capability_row(
        capability_id=capability_id,
        title=title,
        capability_kind=capability_kind,
        state=state,
        evidence_artifacts=[path],
        contract_pass=state == "ready",
        blocker_count=len(_blockers(payload)),
        next_actions=_next_actions(payload) or ([] if state == "ready" else [next_action_fallback]),
        summary={
            "status": str(payload.get("status") or ""),
            "reason_code": str(payload.get("reason_code") or ""),
            "first_blocked_target": str(payload.get("first_blocked_target") or ""),
            "root_cause_tags": [str(row) for row in _as_list(payload.get("root_cause_tags"))],
        },
    )


def _h_bond_capability(repo_root: Path) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_H_BOND_SURFACE)
    operator_intake = _load_json(repo_root, DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET)
    state = _state(surface)
    return _capability_row(
        capability_id="h_bond_backmap_evidence",
        title="H-bond backmap evidence",
        capability_kind="science_evidence_surface",
        state=state,
        evidence_artifacts=[
            DEFAULT_H_BOND_SURFACE,
            DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET,
            DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET_MD,
        ],
        contract_pass=state == "ready",
        blocker_count=len(_blockers(surface)),
        next_actions=_dedupe(
            _next_actions(operator_intake)
            + _next_actions(surface)
            + ([] if state == "ready" else ["fill_h_bond_backmap_operator_intake_packet"])
        ),
        summary={
            "status": str(surface.get("status") or ""),
            "reason_code": str(surface.get("reason_code") or ""),
            "first_blocked_target": str(surface.get("first_blocked_target") or ""),
            "root_cause_tags": [str(row) for row in _as_list(surface.get("root_cause_tags"))],
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_route": str(
                operator_intake.get("route")
                or _as_dict(operator_intake.get("read_model")).get("route")
                or "/product/capabilities"
            ),
            "operator_intake_artifact": str(DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET),
            "operator_intake_markdown_artifact": str(
                DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET_MD
            ),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
            "required_receipts": [str(row) for row in _as_list(surface.get("required_receipts"))],
            "claim_locked": bool(surface.get("claim_locked", True)),
        },
    )


def _gpcr_capability(repo_root: Path) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_GPCR_SURFACE)
    product_report = _load_json(repo_root, DEFAULT_GPCR_PRODUCT_REPORT)
    operator_intake = _load_json(repo_root, DEFAULT_GPCR_OPERATOR_INTAKE_PACKET)
    phase3_exit_gate = _as_dict(
        product_report.get("phase3_exit_gate") or surface.get("phase3_exit_gate")
    )
    phase3_gate_criteria = [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "pass": bool(row.get("pass")),
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
    operator_target_slots = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "target_id": str(row.get("target_id") or ""),
            "status": str(row.get("status") or ""),
            "required": bool(row.get("required")),
            "template_artifact": str(row.get("template_artifact") or ""),
            "required_field_count": len(_as_list(row.get("required_fields"))),
        }
        for row in _as_list(operator_intake.get("target_slots"))
        if isinstance(row, dict)
    ]
    gate_unblock_plan = [
        {
            "slot_id": str(row.get("slot_id") or ""),
            "target_id": str(row.get("target_id") or ""),
            "status": str(row.get("status") or ""),
            "unblocks_phase3_criteria": [
                str(item) for item in _as_list(row.get("unblocks_phase3_criteria"))
            ],
            "template_artifact": str(row.get("template_artifact") or ""),
            "minimum_evidence": _as_dict(row.get("minimum_evidence")),
            "materialization_steps": [
                str(item) for item in _as_list(row.get("materialization_steps"))
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(row.get("validation_command") or ""),
        }
        for row in _as_list(
            operator_intake.get("gate_unblock_plan")
            or _as_dict(product_report.get("operator_intake_packet")).get("gate_unblock_plan")
        )
        if isinstance(row, dict)
    ]
    state = _state(surface)
    return _capability_row(
        capability_id="gpcr_hard_decoy_evidence",
        title="GPCR hard-decoy evidence",
        capability_kind="science_evidence_surface",
        state=state,
        evidence_artifacts=[
            DEFAULT_GPCR_SURFACE,
            DEFAULT_GPCR_PRODUCT_REPORT,
            DEFAULT_GPCR_OPERATOR_INTAKE_PACKET,
            DEFAULT_GPCR_OPERATOR_INTAKE_PACKET_MD,
        ],
        contract_pass=state == "ready",
        blocker_count=len(_blockers(surface)),
        next_actions=_dedupe(
            _next_actions(product_report)
            + _next_actions(operator_intake)
            + _next_actions(surface)
            + ([] if state == "ready" else ["run_gpcr_hard_decoy_suite_materializer"])
        ),
        summary={
            "status": str(surface.get("status") or ""),
            "reason_code": str(surface.get("reason_code") or ""),
            "first_blocked_target": str(surface.get("first_blocked_target") or ""),
            "root_cause_tags": [str(row) for row in _as_list(surface.get("root_cause_tags"))],
            "product_report_route": str(product_report.get("route") or "/product/gpcr-hard-decoy-suite-report"),
            "product_report_ready": bool(product_report.get("read_model_ready")),
            "operator_intake_route": str(
                operator_intake.get("route")
                or _as_dict(operator_intake.get("read_model")).get("route")
                or _as_dict(product_report.get("operator_intake_packet")).get("route")
                or ""
            ),
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_artifact": str(DEFAULT_GPCR_OPERATOR_INTAKE_PACKET),
            "operator_intake_markdown_artifact": str(
                DEFAULT_GPCR_OPERATOR_INTAKE_PACKET_MD
            ),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
            "gate_unblock_plan_count": int(
                operator_intake.get("gate_unblock_plan_count")
                or _as_dict(product_report.get("operator_intake_packet")).get(
                    "gate_unblock_plan_count"
                )
                or len(gate_unblock_plan)
            ),
            "minimum_target_count": int(
                operator_intake.get("minimum_target_count")
                or _as_dict(product_report.get("operator_intake_packet")).get(
                    "minimum_target_count"
                )
                or 0
            ),
            "minimum_metric_field_count_per_target": int(
                operator_intake.get("minimum_metric_field_count_per_target")
                or _as_dict(product_report.get("operator_intake_packet")).get(
                    "minimum_metric_field_count_per_target"
                )
                or 0
            ),
            "broad_gpcr_family_claim_safe": bool(surface.get("broad_gpcr_family_claim_safe")),
            "phase3_exit_gate_status": str(phase3_exit_gate.get("status") or ""),
            "phase3_failed_criterion_count": int(
                phase3_exit_gate.get("failed_criterion_count") or 0
            ),
            "phase3_failed_criteria": [
                str(row) for row in _as_list(phase3_exit_gate.get("failed_criteria"))
            ],
            "phase3_exit_gate_criteria": phase3_gate_criteria,
            "operator_target_slots": operator_target_slots,
            "gate_unblock_plan": gate_unblock_plan,
        },
    )


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_product_capabilities_surface.py"),
        *STRUCTURAL_SURFACE_PATHS,
    ]


def build_product_capabilities_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    capability_rows = [
        _structural_solver_capability(repo_root),
    ]
    ready_count = sum(1 for row in capability_rows if row["state"] == "ready")
    blocked_rows = [row for row in capability_rows if row["state"] != "ready"]
    blocked_capability_register = _blocked_capability_register(capability_rows)
    first_blocked_capability = (
        blocked_capability_register[0] if blocked_capability_register else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=False,
            reuse_policy="product_capabilities_surface_aggregates_structural_solver_evidence",
            repo_root=repo_root,
        ),
        "surface_id": "product_capabilities_surface",
        "surface_kind": "product_capabilities_surface",
        "surface_scope": "product_capability_discovery",
        "status": "ready",
        "reason_code": "PASS",
        "contract_pass": True,
        "locked": False,
        "claim_locked": False,
        "product_capabilities_ready": False,
        "capability_count": len(capability_rows),
        "ready_capability_count": ready_count,
        "blocked_capability_count": len(blocked_rows),
        "capability_rows": capability_rows,
        "blocked_capability_register_count": len(blocked_capability_register),
        "first_blocked_capability_id": str(
            first_blocked_capability.get("capability_id") or ""
        ),
        "first_blocked_capability_next_action": str(
            first_blocked_capability.get("first_next_action") or ""
        ),
        "first_blocked_capability": first_blocked_capability,
        "blocked_capability_register": blocked_capability_register,
        "blockers": [],
        "first_blocked_target": "",
        "root_cause_tags": [],
        "read_model": {
            "route": "/product/capabilities",
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "next_actions": [
            "work_capability_rows_with_state_blocked",
            "regenerate_pm_release_gate_report",
            "regenerate_goal_bottleneck_action_board",
        ],
        "summary_line": (
            "Product capabilities surface: READY | "
            f"capabilities={len(capability_rows)} | ready={ready_count} | "
            f"blocked={len(blocked_rows)}"
        ),
        "claim_boundary": (
            "This surface is a read-only capability discovery map for the structural "
            "analysis solver product. Non-structural product domains are outside this "
            "repository's product scope."
        ),
    }


def write_product_capabilities_surface(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_product_capabilities_surface(repo_root=repo_root)
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
    payload = write_product_capabilities_surface(repo_root=args.repo_root, out=args.out)
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
