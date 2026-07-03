#!/usr/bin/env python3
"""Build owner-evidence handoff for blocked Developer Preview final gates."""

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


SCHEMA_VERSION = "developer-preview-final-gate-owner-packet.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RC_STATUS = PRODUCTIZATION / "developer_preview_rc_status.json"
DEFAULT_ACTION_REGISTER = Path("docs/developer_preview_final_gate_action_register.md")
DEFAULT_OUT = PRODUCTIZATION / "developer_preview_final_gate_owner_packet.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_UX_OBSERVATION_INTAKE = PRODUCTIZATION / "ux_new_user_observation_intake_packet.json"
UX_OBSERVATION_GATE = "new_user_core_workflow_observation_passed"
NEAREST_ABF_SLICE: tuple[dict[str, str], ...] = (
    {
        "slice_id": "A",
        "gate": "benchmark_results_clean_checkout_regenerated",
        "slice_goal": "keep_clean_checkout_and_git_clean_clone_receipts_fresh",
        "owner_action_if_blocked": (
            "Regenerate clean-checkout and git-clean-clone benchmark receipts "
            "from the tracked source state."
        ),
    },
    {
        "slice_id": "B",
        "gate": "silent_import_loss_zero",
        "slice_goal": "keep_ifc_import_loss_technical_gate_green",
        "owner_action_if_blocked": (
            "Regenerate IFC import-health and silent-data-loss receipts without "
            "counting product/license credit blockers as DP technical closure."
        ),
    },
    {
        "slice_id": "F",
        "gate": UX_OBSERVATION_GATE,
        "slice_goal": "attach_human_new_user_30_minute_observation",
        "owner_action_if_blocked": (
            "Attach a real human new-user observation record for the five-step "
            "sample workflow, completed within 30 minutes with blocker_count=0 "
            "and an accepted release decision."
        ),
    },
)

GATE_HANDOFFS: dict[str, dict[str, Any]] = {
    "selected_medium_models_pass_or_approved_review": {
        "owner": "benchmark_validation_owner",
        "owner_action": (
            "Attach product/legal source approval, five selected medium structural "
            "model cases, reference outputs or approved REVIEW baselines, "
            "normalization receipts, and per-case scorecard receipts."
        ),
        "required_owner_evidence": [
            "product_legal_source_license_approval",
            "five_selected_medium_structural_model_case_receipts",
            "reference_outputs_or_approved_review_baselines",
            "per_case_normalization_receipts",
            "per_case_scorecard_receipts_with_PASS_or_APPROVED_REVIEW",
        ],
        "verification_commands": [
            "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
            "python3 scripts/build_phase6_benchmark_scale_status.py --check",
            "python3 scripts/build_developer_preview_rc_status.py --check",
        ],
        "evidence_refresh_commands": [
            (
                "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py "
                "--out implementation/phase1/release_evidence/productization/"
                "phase3_medium_model_scorecard_readiness_receipt.json"
            ),
            (
                "python3 scripts/build_phase6_benchmark_scale_status.py "
                "--out implementation/phase1/release_evidence/productization/"
                "phase6_benchmark_scale_status.json"
            ),
            (
                "python3 scripts/build_developer_preview_rc_status.py "
                "--out implementation/phase1/release_evidence/productization/"
                "developer_preview_rc_status.json"
            ),
            (
                "python3 scripts/build_product_readiness_snapshot.py "
                "--out implementation/phase1/release_evidence/productization/"
                "product_readiness_snapshot.json"
            ),
        ],
        "prohibited_substitutes": [
            "parser_only_medium_topology_evidence",
            "candidate_case_count_without_scorecard_receipts",
            "license_pending_rows_used_as_pass_evidence",
        ],
        "release_surface_impacts": [
            "developer_preview_rc::selected_medium_models_pass_or_approved_review",
            "product_readiness_snapshot::final_gate_blocked:selected_medium_models_pass_or_approved_review",
        ],
        "evidence_intake_artifacts": [
            "implementation/phase1/release_evidence/productization/phase3_medium_model_scorecard_readiness_receipt.json",
            "implementation/phase1/release_evidence/productization/phase6_benchmark_scale_status.json",
        ],
        "upstream_handoff_artifacts": [
            "implementation/phase1/release_evidence/productization/phase3_medium_model_scorecard_readiness_receipt.json",
        ],
        "closure_decision_required": "five_PASS_or_explicit_APPROVED_REVIEW_rows",
    },
    "linux_windows_reproducibility_confirmed": {
        "owner": "release_reproducibility_owner",
        "owner_action": (
            "Attach a Windows platform replay receipt from the same tracked source "
            "state, with platform metadata, commands, return codes, and stable "
            "output checksums matching the Linux replay contract."
        ),
        "required_owner_evidence": [
            "phase6_windows_platform_replay_receipt_json",
            "same_source_commit_as_linux_replay",
            "clean_worktree_platform_metadata",
            "required_replay_commands_return_0",
            "stable_output_checksum_comparison",
        ],
        "verification_commands": [
            "python3 scripts/build_phase6_linux_windows_parity_status.py --check",
            "python3 scripts/build_developer_preview_rc_status.py --check",
        ],
        "evidence_refresh_commands": [
            (
                "python3 scripts/build_phase6_linux_windows_parity_status.py "
                "--out implementation/phase1/release_evidence/productization/"
                "phase6_linux_windows_parity_status.json"
            ),
            (
                "python3 scripts/build_developer_preview_rc_status.py "
                "--out implementation/phase1/release_evidence/productization/"
                "developer_preview_rc_status.json"
            ),
            (
                "python3 scripts/build_product_readiness_snapshot.py "
                "--out implementation/phase1/release_evidence/productization/"
                "product_readiness_snapshot.json"
            ),
        ],
        "prohibited_substitutes": [
            "linux_only_replay_copied_as_windows_parity",
            "git_clean_clone_receipt_counted_twice",
            "manual_platform_claim_without_replay_receipt",
        ],
        "release_surface_impacts": [
            "developer_preview_rc::linux_windows_reproducibility_confirmed",
            "product_readiness_snapshot::final_gate_blocked:linux_windows_reproducibility_confirmed",
        ],
        "evidence_intake_artifacts": [
            "implementation/phase1/release_evidence/productization/phase6_windows_platform_replay_receipt.json",
            "implementation/phase1/release_evidence/productization/phase6_linux_windows_parity_status.json",
        ],
        "upstream_handoff_artifacts": [
            "implementation/phase1/release_evidence/productization/phase6_linux_windows_parity_status.json",
        ],
        "closure_decision_required": "direct_windows_replay_receipt_passes",
    },
    "new_user_core_workflow_observation_passed": {
        "owner": "ux_research_owner",
        "owner_action": (
            "Attach a real human new-user observation record for the five-step "
            "sample workflow with timezone-aware timestamps, completion minutes "
            "<= 30, blocker_count=0, evidence reference, and accepted decision."
        ),
        "required_owner_evidence": [
            "non_template_human_new_user_observation_record",
            "participant_confirmed_new_to_product",
            "all_five_workflow_steps_passed",
            "timezone_aware_start_and_end_timestamps",
            "completion_minutes_lte_30",
            "blocker_count_zero",
            "non_placeholder_evidence_ref",
            "accepted_release_decision",
        ],
        "verification_commands": [
            (
                "python3 scripts/build_ux_new_user_observation_report.py "
                "--out implementation/phase1/release_evidence/productization/"
                "ux_new_user_observation_report.json"
            ),
            (
                "python3 scripts/build_ux_new_user_observation_intake_packet.py "
                "--out implementation/phase1/release_evidence/productization/"
                "ux_new_user_observation_intake_packet.json"
            ),
            "python3 scripts/build_phase6_ux_observation_status.py --check",
            "python3 scripts/build_developer_preview_rc_status.py --check",
        ],
        "evidence_refresh_commands": [
            (
                "python3 scripts/build_ux_new_user_observation_report.py "
                "--out implementation/phase1/release_evidence/productization/"
                "ux_new_user_observation_report.json"
            ),
            (
                "python3 scripts/build_ux_new_user_observation_intake_packet.py "
                "--out implementation/phase1/release_evidence/productization/"
                "ux_new_user_observation_intake_packet.json"
            ),
            (
                "python3 scripts/build_phase6_ux_observation_status.py "
                "--out implementation/phase1/release_evidence/productization/"
                "phase6_ux_observation_status.json"
            ),
            (
                "python3 scripts/build_developer_preview_rc_status.py "
                "--out implementation/phase1/release_evidence/productization/"
                "developer_preview_rc_status.json"
            ),
            (
                "python3 scripts/build_product_readiness_snapshot.py "
                "--out implementation/phase1/release_evidence/productization/"
                "product_readiness_snapshot.json"
            ),
        ],
        "prohibited_substitutes": [
            "automated_browser_smoke_without_human_observation",
            "template_ux_observation_json",
            "self_referential_or_placeholder_evidence_refs",
            "gui_shell_coverage_without_user_observation",
        ],
        "release_surface_impacts": [
            "developer_preview_rc::new_user_core_workflow_observation_passed",
            "pm_release::ux::human_new_user_observation_missing_or_failed",
            "pm_release::ux::human_new_user_30min_sample_evidence_missing",
            "product_readiness_snapshot::human_ux::*",
        ],
        "evidence_intake_artifacts": [
            "docs/templates/ux_new_user_observation.template.json",
            "implementation/phase1/release_evidence/productization/ux_new_user_observation.json",
            "implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json",
            "implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json",
            "implementation/phase1/release_evidence/productization/phase6_ux_observation_status.json",
        ],
        "upstream_handoff_artifacts": [
            "implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json",
        ],
        "closure_decision_required": "accepted_human_new_user_observation",
    },
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _semantic_normalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _semantic_normalize(child, path + (str(key),))
            for key, child in value.items()
            if str(key) != "generated_at"
            and not (path == () and str(key) == "source_commit_sha")
        }
    if isinstance(value, list):
        return [_semantic_normalize(item, path) for item in value]
    return value


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _split_evidence_refs(value: Any) -> list[str]:
    refs = [item.strip() for item in str(value or "").split(";")]
    return [item for item in refs if item]


def _deduped(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _compact_upstream_handoff_source(repo_root: Path, artifact: str) -> dict[str, Any]:
    path = Path(artifact)
    payload = _load_json(repo_root, path)
    if not payload:
        return {
            "artifact": artifact,
            "present": False,
            "status": "missing",
            "contract_pass": False,
            "summary_line": "",
            "blockers": [f"upstream_handoff_artifact_missing:{artifact}"],
            "blocker_count": 1,
            "gate_unblock_plan": [],
            "gate_unblock_plan_count": 0,
            "operator_next_actions": [],
            "operator_next_action_count": 0,
            "recommended_next_actions": [],
            "recommended_next_action_count": 0,
            "validation_commands": [],
            "validation_command_count": 0,
            "missing_evidence_breakdown": [],
            "missing_evidence_count": 0,
        }
    blockers = [str(item) for item in _as_list(payload.get("blockers"))]
    gate_unblock_plan = _as_list(payload.get("gate_unblock_plan"))
    operator_next_actions = _as_list(payload.get("operator_next_actions"))
    recommended_next_actions = _as_list(payload.get("recommended_next_actions"))
    validation_commands = [
        str(item) for item in _as_list(payload.get("validation_commands"))
    ]
    missing_evidence_breakdown = _as_list(payload.get("missing_evidence_breakdown"))
    source = {
        "artifact": artifact,
        "present": True,
        "status": str(payload.get("status", "")),
        "contract_pass": bool(payload.get("contract_pass") is True),
        "summary_line": str(payload.get("summary_line", "")),
        "blockers": blockers,
        "blocker_count": len(blockers),
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "operator_next_actions": operator_next_actions,
        "operator_next_action_count": len(operator_next_actions),
        "recommended_next_actions": recommended_next_actions,
        "recommended_next_action_count": len(recommended_next_actions),
        "validation_commands": validation_commands,
        "validation_command_count": len(validation_commands),
        "missing_evidence_breakdown": missing_evidence_breakdown,
        "missing_evidence_count": len(missing_evidence_breakdown),
    }
    runner_command_template = payload.get("runner_command_template")
    if isinstance(runner_command_template, str) and runner_command_template:
        source["runner_command_template"] = runner_command_template
    case_input_requirements = payload.get("case_input_requirements")
    if isinstance(case_input_requirements, dict):
        source["case_input_requirements"] = case_input_requirements
    return source


def _upstream_handoff_sources(
    *, repo_root: Path, artifacts: list[str]
) -> list[dict[str, Any]]:
    return [
        _compact_upstream_handoff_source(repo_root, artifact)
        for artifact in artifacts
    ]


def _source_plan_rows(source: dict[str, Any]) -> list[Any]:
    plan = _as_list(source.get("gate_unblock_plan"))
    if plan:
        return plan
    plan = _as_list(source.get("operator_next_actions"))
    if plan:
        return plan
    return _as_list(source.get("recommended_next_actions"))


def _owner_unblock_plan(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for source in sources:
        artifact = str(source.get("artifact", ""))
        for index, row in enumerate(_source_plan_rows(source), start=1):
            if isinstance(row, dict):
                item = dict(row)
            else:
                item = {"action": str(row)}
            slot_id = str(item.get("slot_id") or item.get("id") or f"step_{index}")
            item["slot_id"] = slot_id
            item["source_artifact"] = artifact
            plan.append(item)
    return plan


def _upstream_validation_commands(sources: list[dict[str, Any]]) -> list[str]:
    return _deduped(
        [
            str(command)
            for source in sources
            for command in _as_list(source.get("validation_commands"))
        ]
    )


def _gate_item(gate: dict[str, Any]) -> str:
    return str(gate.get("item", "") or "")


def _blocked_gates(final_gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        gate
        for gate in final_gates
        if str(gate.get("status", "")).lower() != "ready"
        or gate.get("contract_pass") is not True
    ]


def _owner_packet_for_gate(*, gate: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    item = _gate_item(gate)
    handoff = GATE_HANDOFFS.get(item, {})
    ux_intake = (
        _load_json(repo_root, DEFAULT_UX_OBSERVATION_INTAKE)
        if item == UX_OBSERVATION_GATE
        else {}
    )
    ux_intake_blocker_ids = [str(item) for item in _as_list(ux_intake.get("blocker_ids"))]
    ux_release_area_blocker_ids = [
        str(item) for item in _as_list(ux_intake.get("release_area_blocker_ids"))
    ]
    ux_developer_preview_blocker_ids = [
        str(item) for item in _as_list(ux_intake.get("developer_preview_blocker_ids"))
    ]
    ux_product_readiness_blocker_ids = [
        str(item) for item in _as_list(ux_intake.get("product_readiness_blocker_ids"))
    ]
    release_surface_impacts = [
        str(item) for item in _as_list(handoff.get("release_surface_impacts"))
    ]
    blocker_ids = _deduped(
        [
            f"developer_preview_rc::{item}" if item else "",
            *release_surface_impacts,
            *ux_release_area_blocker_ids,
            *ux_developer_preview_blocker_ids,
            *ux_product_readiness_blocker_ids,
            *ux_intake_blocker_ids,
        ]
    )
    required_owner_evidence = [
        str(item) for item in _as_list(handoff.get("required_owner_evidence"))
    ]
    verification_commands = [
        str(item) for item in _as_list(handoff.get("verification_commands"))
    ]
    evidence_refresh_commands = [
        str(item) for item in _as_list(handoff.get("evidence_refresh_commands"))
    ]
    evidence_intake_artifacts = [
        str(item) for item in _as_list(handoff.get("evidence_intake_artifacts"))
    ]
    evidence_intake_artifacts = _deduped(
        evidence_intake_artifacts
        + [str(item) for item in _as_list(ux_intake.get("evidence_intake_artifacts"))]
    )
    human_observation_evidence_policy = _as_dict(
        ux_intake.get("human_observation_evidence_policy")
    )
    upstream_handoff_artifacts = [
        str(item) for item in _as_list(handoff.get("upstream_handoff_artifacts"))
    ]
    upstream_handoff_sources = _upstream_handoff_sources(
        repo_root=repo_root,
        artifacts=upstream_handoff_artifacts,
    )
    upstream_validation_commands = _upstream_validation_commands(upstream_handoff_sources)
    verification_commands = _deduped(verification_commands + upstream_validation_commands)
    owner_unblock_plan = _owner_unblock_plan(upstream_handoff_sources)
    prohibited_substitutes = _deduped(
        [str(item) for item in _as_list(handoff.get("prohibited_substitutes"))]
        + [
            str(item)
            for item in _as_list(human_observation_evidence_policy.get("rejected_substitutes"))
        ]
    )
    current_blockers = [str(item) for item in _as_list(gate.get("blockers"))]
    return {
        "gate_id": item,
        "gate": item,
        "status": str(gate.get("status", "")),
        "contract_pass": bool(gate.get("contract_pass")),
        "current_evidence_gap_state": (
            "owner_evidence_required"
            if current_blockers or gate.get("contract_pass") is not True
            else "ready"
        ),
        "owner": str(handoff.get("owner", "owner_assignment_required")),
        "owner_action": str(handoff.get("owner_action", "Owner action mapping required.")),
        "closure_decision_required": str(
            handoff.get("closure_decision_required", "owner_decision_required")
        ),
        "blocker_ids": blocker_ids,
        "required_owner_evidence": required_owner_evidence,
        "required_owner_evidence_count": len(required_owner_evidence),
        "verification_commands": verification_commands,
        "verification_command_count": len(verification_commands),
        "evidence_refresh_commands": evidence_refresh_commands,
        "evidence_refresh_command_count": len(evidence_refresh_commands),
        "evidence_intake_artifacts": evidence_intake_artifacts,
        "evidence_intake_artifact_count": len(evidence_intake_artifacts),
        "upstream_handoff_artifacts": upstream_handoff_artifacts,
        "upstream_handoff_artifact_count": len(upstream_handoff_artifacts),
        "upstream_handoff_sources": upstream_handoff_sources,
        "upstream_handoff_source_count": len(upstream_handoff_sources),
        "upstream_validation_commands": upstream_validation_commands,
        "upstream_validation_command_count": len(upstream_validation_commands),
        "owner_unblock_plan": owner_unblock_plan,
        "owner_unblock_plan_count": len(owner_unblock_plan),
        "owner_unblock_slot_ids": [
            str(row.get("slot_id", "")) for row in owner_unblock_plan
        ],
        "prohibited_substitutes": prohibited_substitutes,
        "release_surface_impacts": release_surface_impacts,
        "release_surface_impact_count": len(release_surface_impacts),
        "upstream_intake_artifact": (
            DEFAULT_UX_OBSERVATION_INTAKE.as_posix()
            if item == UX_OBSERVATION_GATE
            else ""
        ),
        "upstream_intake_status": str(ux_intake.get("status", "")),
        "upstream_intake_contract_pass": bool(ux_intake.get("contract_pass") is True),
        "upstream_intake_blocker_ids": ux_intake_blocker_ids,
        "upstream_intake_blocker_id_count": len(ux_intake_blocker_ids),
        "human_observation_evidence_policy": human_observation_evidence_policy,
        "current_blockers": current_blockers,
        "current_blocker_count": len(current_blockers),
        "blocker_grouping_metadata": gate.get("blocker_grouping_metadata", {}),
        "current_evidence_refs": _split_evidence_refs(gate.get("evidence")),
        "notes": [str(item) for item in _as_list(gate.get("notes"))],
    }


def _nearest_abf_slice_rows(
    *,
    final_gates: list[dict[str, Any]],
    owner_packets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gates_by_item = {_gate_item(gate): gate for gate in final_gates}
    packets_by_gate = {str(packet.get("gate", "")): packet for packet in owner_packets}
    rows: list[dict[str, Any]] = []
    for spec in NEAREST_ABF_SLICE:
        gate_id = spec["gate"]
        gate = gates_by_item.get(gate_id, {})
        packet = packets_by_gate.get(gate_id, {})
        present = bool(gate)
        contract_pass = bool(gate.get("contract_pass") is True)
        status = str(gate.get("status", "missing") or "missing")
        blockers = [str(item) for item in _as_list(gate.get("blockers"))]
        rows.append(
            {
                "slice_id": spec["slice_id"],
                "gate": gate_id,
                "slice_goal": spec["slice_goal"],
                "present": present,
                "status": status,
                "contract_pass": contract_pass,
                "ready_for_dp_final_gate": bool(
                    present and status.lower() == "ready" and contract_pass
                ),
                "owner_review_required": bool(not contract_pass),
                "owner": str(packet.get("owner", "")),
                "owner_action_if_blocked": str(
                    packet.get("owner_action") or spec["owner_action_if_blocked"]
                ),
                "closure_decision_required": str(
                    packet.get("closure_decision_required", "")
                ),
                "current_evidence_gap_state": str(
                    packet.get(
                        "current_evidence_gap_state",
                        "ready" if contract_pass else "owner_evidence_required",
                    )
                ),
                "current_evidence_refs": _split_evidence_refs(gate.get("evidence")),
                "current_blockers": blockers,
                "current_blocker_count": len(blockers),
                "owner_unblock_slot_ids": [
                    str(item)
                    for item in _as_list(packet.get("owner_unblock_slot_ids"))
                ],
                "verification_commands": [
                    str(item)
                    for item in _as_list(packet.get("verification_commands"))
                ],
                "evidence_refresh_commands": [
                    str(item)
                    for item in _as_list(packet.get("evidence_refresh_commands"))
                ],
            }
        )
    return rows


def _nearest_abf_slice_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ready_rows = [
        row
        for row in rows
        if row["ready_for_dp_final_gate"] is True
    ]
    blocked_rows = [
        row
        for row in rows
        if row["ready_for_dp_final_gate"] is not True
    ]
    return {
        "slice_count": len(rows),
        "ready_count": len(ready_rows),
        "blocked_count": len(blocked_rows),
        "ready_slice_ids": [str(row["slice_id"]) for row in ready_rows],
        "blocked_slice_ids": [str(row["slice_id"]) for row in blocked_rows],
        "blocked_gates": [str(row["gate"]) for row in blocked_rows],
        "completion_ratio": (
            round(len(ready_rows) / len(rows), 4)
            if rows
            else 1.0
        ),
        "claim_boundary": (
            "A/B/F slice tracking only reports current DP final-gate state. "
            "It does not create missing human observation, benchmark, or "
            "platform replay evidence and does not promote Developer Preview."
        ),
    }


def build_owner_packet(
    *,
    repo_root: Path = ROOT,
    rc_status_path: Path = DEFAULT_RC_STATUS,
    action_register_path: Path = DEFAULT_ACTION_REGISTER,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    rc_status = _load_json(repo_root, rc_status_path)
    action_register_resolved = _resolve(repo_root, action_register_path)
    action_register_present = action_register_resolved.exists()
    final_gates = [
        gate
        for gate in _as_list(rc_status.get("final_gates"))
        if isinstance(gate, dict)
    ]
    blocked_gates = _blocked_gates(final_gates)
    owner_packets = [
        _owner_packet_for_gate(gate=gate, repo_root=repo_root)
        for gate in blocked_gates
    ]
    nearest_abf_slice_rows = _nearest_abf_slice_rows(
        final_gates=final_gates,
        owner_packets=owner_packets,
    )
    nearest_abf_slice_summary = _nearest_abf_slice_summary(
        nearest_abf_slice_rows
    )
    owner_packet_blocker_ids = _deduped(
        [
            str(item)
            for packet in owner_packets
            for item in _as_list(packet.get("blocker_ids"))
        ]
    )
    unmapped = [
        packet["gate"]
        for packet in owner_packets
        if packet["gate"] not in GATE_HANDOFFS
    ]
    incomplete_packets = [
        packet["gate"]
        for packet in owner_packets
        if not packet["required_owner_evidence"]
        or not packet["verification_commands"]
        or packet["owner"] == "owner_assignment_required"
    ]
    blockers: list[str] = []
    if not rc_status:
        blockers.append("developer_preview_rc_status_missing")
    if not action_register_present:
        blockers.append("developer_preview_final_gate_action_register_missing")
    if not final_gates:
        blockers.append("developer_preview_final_gates_missing")
    blockers.extend(f"owner_handoff_mapping_missing:{item}" for item in unmapped)
    blockers.extend(f"owner_handoff_packet_incomplete:{item}" for item in incomplete_packets)
    contract_pass = bool(rc_status and action_register_present and final_gates and not blockers)
    final_gate_count = int(rc_status.get("final_gate_count") or len(final_gates))
    final_gate_pass_count = int(
        rc_status.get("final_gate_pass_count")
        or sum(1 for gate in final_gates if str(gate.get("status", "")) == "ready")
    )
    evidence_closure_pass = bool(contract_pass and not blocked_gates)
    status = (
        "complete"
        if evidence_closure_pass
        else "ready_for_owner_review"
        if contract_pass
        else "blocked_handoff"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_developer_preview_final_gate_owner_packet.py"),
                rc_status_path,
                action_register_path,
                DEFAULT_UX_OBSERVATION_INTAKE,
            ],
            reused_evidence=False,
            reuse_policy=(
                "developer_preview_final_gate_owner_packet_from_rc_status"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": contract_pass,
        "evidence_closure_pass": evidence_closure_pass,
        "summary_line": (
            "Developer Preview final gate owner packet: "
            f"{status.upper()} | blocked_gates={len(blocked_gates)}/{final_gate_count} | "
            f"handoff_rows={len(owner_packets)}"
        ),
        "owner_review_required": bool(blocked_gates),
        "final_gate_count": final_gate_count,
        "final_gate_pass_count": final_gate_pass_count,
        "blocked_final_gate_count": len(blocked_gates),
        "blocked_gate_items": [_gate_item(gate) for gate in blocked_gates],
        "ready_gate_items": [
            _gate_item(gate)
            for gate in final_gates
            if gate not in blocked_gates
        ],
        "nearest_abf_slice_summary": nearest_abf_slice_summary,
        "nearest_abf_slice": nearest_abf_slice_rows,
        "owner_packet_count": len(owner_packets),
        "owner_packet_gate_ids": [packet["gate_id"] for packet in owner_packets],
        "owner_packet_blocker_ids": owner_packet_blocker_ids,
        "owner_packet_blocker_id_count": len(owner_packet_blocker_ids),
        "evidence_intake_artifact_count": sum(
            len(packet["evidence_intake_artifacts"]) for packet in owner_packets
        ),
        "evidence_refresh_command_count": sum(
            len(packet["evidence_refresh_commands"]) for packet in owner_packets
        ),
        "owner_unblock_plan_count": sum(
            len(packet["owner_unblock_plan"]) for packet in owner_packets
        ),
        "release_surface_impact_count": sum(
            len(packet["release_surface_impacts"]) for packet in owner_packets
        ),
        "owner_packets": owner_packets,
        "required_closure_evidence_policy": (
            "Each blocked final gate must attach the named owner evidence and "
            "pass its verification commands before Developer Preview RC closure. "
            "Handoff packets, templates, Linux-only replays, parser-only rows, "
            "and automated smoke tests do not substitute for the missing receipts."
        ),
        "blockers": blockers,
        "artifacts": {
            "developer_preview_rc_status": rc_status_path.as_posix(),
            "developer_preview_final_gate_action_register": action_register_path.as_posix(),
        },
        "claim_boundary": (
            "This packet is a Developer Preview owner-evidence handoff for blocked "
            "RC final gates. It does not create benchmark, Windows, or human UX "
            "evidence; does not promote Developer Preview readiness; and does not "
            "close Commercial Release, G1, customer shadow, external benchmark, "
            "license, SLA, or GitHub CI streak gates."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Developer Preview Final Gate Owner Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `blocked_final_gate_count`: `{payload['blocked_final_gate_count']}`",
        "",
        "## Nearest A/B/F Slice",
        "",
        "| Slice | Gate | Status | Owner Review Required | Blockers |",
        "|---|---|---|---:|---:|",
    ]
    for row in payload["nearest_abf_slice"]:
        lines.append(
            "| "
            f"`{row['slice_id']}` | "
            f"`{row['gate']}` | "
            f"`{row['status']}` | "
            f"`{row['owner_review_required']}` | "
            f"{row['current_blocker_count']} |"
        )
    summary = payload["nearest_abf_slice_summary"]
    lines.extend(
        [
            "",
            "- `nearest_abf_ready_count`: "
            f"`{summary['ready_count']}/{summary['slice_count']}`",
            "- `nearest_abf_blocked_slice_ids`: "
            f"`{summary['blocked_slice_ids']}`",
            "",
        ]
    )
    lines.extend(
        [
        "## Owner Packets",
        "",
        "| Gate | Owner | Blockers | Closure Decision |",
        "|---|---|---:|---|",
        ]
    )
    for packet in payload["owner_packets"]:
        lines.append(
            "| "
            f"`{packet['gate']}` | "
            f"`{packet['owner']}` | "
            f"{len(packet['current_blockers'])} | "
            f"`{packet['closure_decision_required']}` |"
        )
    lines.extend(["", "## Verification Commands", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate']}`")
        for command in packet["verification_commands"]:
            lines.append(f"- `{command}`")
        lines.append("")
    lines.extend(["## Evidence Refresh Commands", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate']}`")
        for command in packet["evidence_refresh_commands"]:
            lines.append(f"- `{command}`")
        if not packet["evidence_refresh_commands"]:
            lines.append("- none")
        lines.append("")
    lines.extend(["## Gate Unblock Plan", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate']}`")
        if packet["owner_unblock_plan"]:
            for row in packet["owner_unblock_plan"]:
                source = str(row.get("source_artifact", ""))
                lines.append(f"- `{row.get('slot_id', '')}` from `{source}`")
        else:
            lines.append("- none")
        lines.append("")
    lines.extend(["## Upstream Handoff Sources", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate']}`")
        lines.append("| Artifact | Status | Pass | Plan Rows | Blockers |")
        lines.append("|---|---|---:|---:|---:|")
        for source in packet["upstream_handoff_sources"]:
            lines.append(
                "| "
                f"`{source['artifact']}` | "
                f"`{source['status']}` | "
                f"`{source['contract_pass']}` | "
                f"{source['gate_unblock_plan_count']} | "
                f"{source['blocker_count']} |"
            )
        if not packet["upstream_handoff_sources"]:
            lines.append("| none |  |  |  |  |")
        lines.append("")
    lines.extend(["## Evidence Intake Artifacts", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate_id']}`")
        for artifact in packet["evidence_intake_artifacts"]:
            lines.append(f"- `{artifact}`")
        if not packet["evidence_intake_artifacts"]:
            lines.append("- none")
        lines.append("")
    ux_policy_packets = [
        packet
        for packet in payload["owner_packets"]
        if packet.get("human_observation_evidence_policy")
    ]
    if ux_policy_packets:
        lines.extend(["## Human Observation Evidence Policy", ""])
        for packet in ux_policy_packets:
            policy = packet["human_observation_evidence_policy"]
            lines.append(f"### `{packet['gate_id']}`")
            lines.append(f"- `closure_rule`: {policy.get('closure_rule', '')}")
            accepted = "; ".join(str(item) for item in _as_list(policy.get("accepted_evidence")))
            rejected = "; ".join(str(item) for item in _as_list(policy.get("rejected_substitutes")))
            lines.append(f"- `accepted_evidence`: {accepted}")
            lines.append(f"- `rejected_substitutes`: {rejected}")
            lines.append("")
    lines.extend(["## Blocker IDs", ""])
    if payload["owner_packet_blocker_ids"]:
        lines.extend(f"- `{item}`" for item in payload["owner_packet_blocker_ids"])
    else:
        lines.append("- none")
    lines.append("")
    lines.extend(["## Release Surface Impacts", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate']}`")
        for item in packet["release_surface_impacts"]:
            lines.append(f"- `{item}`")
        if not packet["release_surface_impacts"]:
            lines.append("- none")
        lines.append("")
    if payload["blockers"]:
        lines.extend(["## Packet Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
        lines.append("")
    lines.extend(["## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_owner_packet(
    *,
    repo_root: Path = ROOT,
    rc_status_path: Path = DEFAULT_RC_STATUS,
    action_register_path: Path = DEFAULT_ACTION_REGISTER,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_owner_packet(
        repo_root=repo_root,
        rc_status_path=rc_status_path,
        action_register_path=action_register_path,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def check_owner_packet(
    *,
    repo_root: Path = ROOT,
    rc_status_path: Path = DEFAULT_RC_STATUS,
    action_register_path: Path = DEFAULT_ACTION_REGISTER,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> tuple[bool, str, dict[str, Any]]:
    expected = build_owner_packet(
        repo_root=repo_root,
        rc_status_path=rc_status_path,
        action_register_path=action_register_path,
    )
    resolved_out = _resolve(repo_root, out)
    if not resolved_out.exists():
        return False, "developer_preview_final_gate_owner_packet_missing", expected
    try:
        actual = json.loads(resolved_out.read_text(encoding="utf-8"))
    except Exception:
        return False, "developer_preview_final_gate_owner_packet_unreadable", expected
    if not isinstance(actual, dict):
        return False, "developer_preview_final_gate_owner_packet_not_object", expected
    if _semantic_normalize(actual) != _semantic_normalize(expected):
        return False, "developer_preview_final_gate_owner_packet_mismatch", expected

    resolved_out_md = _resolve(repo_root, out_md)
    if not resolved_out_md.exists():
        return False, "developer_preview_final_gate_owner_packet_markdown_missing", expected
    if resolved_out_md.read_text(encoding="utf-8") != _markdown(expected):
        return False, "developer_preview_final_gate_owner_packet_markdown_mismatch", expected
    return True, "developer_preview_final_gate_owner_packet_consistent", expected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--rc-status", type=Path, default=DEFAULT_RC_STATUS)
    parser.add_argument("--action-register", type=Path, default=DEFAULT_ACTION_REGISTER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message, payload = check_owner_packet(
            repo_root=args.repo_root,
            rc_status_path=args.rc_status,
            action_register_path=args.action_register,
            out=args.out,
            out_md=args.out_md,
        )
        if args.json:
            print(_json_text(payload), end="")
        if not ok:
            print(f"Developer Preview final gate owner packet check FAILED: {message}", file=sys.stderr)
            return 1
        if args.fail_blocked and not payload["contract_pass"]:
            print("Developer Preview final gate owner packet check FAILED: blocked_handoff", file=sys.stderr)
            return 1
        print(f"Developer Preview final gate owner packet check: {message}")
        return 0

    payload = write_owner_packet(
        repo_root=args.repo_root,
        rc_status_path=args.rc_status,
        action_register_path=args.action_register,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
