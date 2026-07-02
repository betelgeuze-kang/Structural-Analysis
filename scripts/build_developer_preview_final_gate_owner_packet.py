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
        "closure_decision_required": "accepted_human_new_user_observation",
    },
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def _gate_item(gate: dict[str, Any]) -> str:
    return str(gate.get("item", "") or "")


def _blocked_gates(final_gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        gate
        for gate in final_gates
        if str(gate.get("status", "")).lower() != "ready"
        or gate.get("contract_pass") is not True
    ]


def _owner_packet_for_gate(gate: dict[str, Any]) -> dict[str, Any]:
    item = _gate_item(gate)
    handoff = GATE_HANDOFFS.get(item, {})
    release_surface_impacts = [
        str(item) for item in _as_list(handoff.get("release_surface_impacts"))
    ]
    blocker_ids = _deduped(
        [
            f"developer_preview_rc::{item}" if item else "",
            *release_surface_impacts,
        ]
    )
    required_owner_evidence = [
        str(item) for item in _as_list(handoff.get("required_owner_evidence"))
    ]
    verification_commands = [
        str(item) for item in _as_list(handoff.get("verification_commands"))
    ]
    evidence_intake_artifacts = [
        str(item) for item in _as_list(handoff.get("evidence_intake_artifacts"))
    ]
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
        "evidence_intake_artifacts": evidence_intake_artifacts,
        "evidence_intake_artifact_count": len(evidence_intake_artifacts),
        "prohibited_substitutes": [
            str(item) for item in _as_list(handoff.get("prohibited_substitutes"))
        ],
        "release_surface_impacts": release_surface_impacts,
        "release_surface_impact_count": len(release_surface_impacts),
        "current_blockers": current_blockers,
        "current_blocker_count": len(current_blockers),
        "blocker_grouping_metadata": gate.get("blocker_grouping_metadata", {}),
        "current_evidence_refs": _split_evidence_refs(gate.get("evidence")),
        "notes": [str(item) for item in _as_list(gate.get("notes"))],
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
    owner_packets = [_owner_packet_for_gate(gate) for gate in blocked_gates]
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
        "owner_packet_count": len(owner_packets),
        "owner_packet_gate_ids": [packet["gate_id"] for packet in owner_packets],
        "owner_packet_blocker_ids": owner_packet_blocker_ids,
        "owner_packet_blocker_id_count": len(owner_packet_blocker_ids),
        "evidence_intake_artifact_count": sum(
            len(packet["evidence_intake_artifacts"]) for packet in owner_packets
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
        "## Owner Packets",
        "",
        "| Gate | Owner | Blockers | Closure Decision |",
        "|---|---|---:|---|",
    ]
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
    lines.extend(["## Evidence Intake Artifacts", ""])
    for packet in payload["owner_packets"]:
        lines.append(f"### `{packet['gate_id']}`")
        for artifact in packet["evidence_intake_artifacts"]:
            lines.append(f"- `{artifact}`")
        if not packet["evidence_intake_artifacts"]:
            lines.append("- none")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--rc-status", type=Path, default=DEFAULT_RC_STATUS)
    parser.add_argument("--action-register", type=Path, default=DEFAULT_ACTION_REGISTER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
