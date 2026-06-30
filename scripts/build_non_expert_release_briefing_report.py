#!/usr/bin/env python3
"""Build a plain-language release briefing from the /goal bottleneck surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_GOAL_SURFACE = PRODUCTIZATION / "goal_bottleneck_roadmap_surface.json"
DEFAULT_OUT = PRODUCTIZATION / "non_expert_release_briefing_report.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "non-expert-release-briefing-report.v1"
ROUTE = "/goal/non-expert-release-briefing"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str_list(rows: Any) -> list[str]:
    return [str(row) for row in _as_list(rows) if str(row)]


def _first_handoff(briefing: dict[str, Any]) -> dict[str, Any]:
    slot = _as_dict(briefing.get("first_operator_handoff_slot"))
    if slot:
        return slot
    return _as_dict(briefing.get("first_operator_handoff"))


def _human_ux_summary(briefing: dict[str, Any]) -> dict[str, Any]:
    gate = _as_dict(briefing.get("human_ux_release_gate"))
    return {
        "status": str(gate.get("status") or "unknown"),
        "plain_status": str(gate.get("plain_status") or ""),
        "owner_action": str(
            briefing.get("human_ux_owner_action") or gate.get("owner_action") or ""
        ),
        "release_area_blocker_count": len(_as_list(briefing.get("human_ux_blockers"))),
        "human_observation_contract_pass": bool(
            gate.get("human_observation_contract_pass") is True
        ),
        "owner_intake_contract_pass": bool(gate.get("owner_intake_contract_pass") is True),
        "missing_field_count": int(gate.get("missing_field_count") or 0),
        "required_workflow_step_count": int(gate.get("required_workflow_step_count") or 0),
        "workflow_step_pass_count": int(gate.get("workflow_step_pass_count") or 0),
        "max_completion_minutes": gate.get("max_completion_minutes"),
        "evidence_artifacts": _as_dict(gate.get("evidence_artifacts")),
        "validation_commands": _str_list(gate.get("validation_commands")),
    }


def _next_owner_actions(briefing: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for row in _as_list(briefing.get("release_area_owner_handoffs")):
        if not isinstance(row, dict):
            continue
        owner_action = str(row.get("owner_action") or "")
        if not owner_action:
            continue
        actions.append(
            {
                "source": "release_area",
                "blocker_id": str(row.get("blocker_id") or ""),
                "owner": str(row.get("owner") or ""),
                "external_input_required": bool(row.get("external_input_required") is True),
                "owner_action": owner_action,
            }
        )
    first_handoff = _first_handoff(briefing)
    if first_handoff:
        actions.insert(
            0,
            {
                "source": "goal_operator_handoff",
                "blocker_id": str(first_handoff.get("first_blocker") or ""),
                "owner": "operator",
                "external_input_required": True,
                "owner_action": str(first_handoff.get("first_next_action") or ""),
            },
        )
    return actions


def build_report(
    *,
    repo_root: Path = ROOT,
    goal_surface: Path = DEFAULT_GOAL_SURFACE,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    surface = _load_json(repo_root, goal_surface)
    briefing = _as_dict(surface.get("non_expert_release_briefing"))
    kpis = _as_dict(surface.get("release_decision_kpis"))
    ready = bool(surface.get("non_expert_release_briefing_ready") is True and briefing)
    blockers: list[str] = []
    if not ready:
        blockers.append("non_expert_release_briefing_missing_or_not_ready")
    required_keys = [
        "plain_status",
        "primary_release_blocker",
        "release_area_owner_handoffs",
        "human_ux_release_gate",
        "blocked_science_or_beta_phases",
        "claim_boundaries",
    ]
    missing_required_keys = [key for key in required_keys if key not in briefing]
    blockers.extend(f"briefing_required_key_missing:{key}" for key in missing_required_keys)

    release_allowed = bool(kpis.get("release_allowed") is True or briefing.get("release_allowed") is True)
    status = "ready_release_allowed" if release_allowed else "ready_release_blocked"
    if blockers:
        status = "blocked_report_incomplete"
    first_handoff = _first_handoff(briefing)

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_non_expert_release_briefing_report.py"),
                goal_surface,
            ],
            reused_evidence=True,
            reuse_policy="non_expert_release_briefing_report_from_goal_bottleneck_surface",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_NON_EXPERT_BRIEFING_INCOMPLETE",
        "read_model_ready": not blockers,
        "route": ROUTE,
        "read_model": {
            "route": ROUTE,
            "alternate_routes": ["/goal/bottleneck", "/goal/roadmap", "/product/capabilities"],
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "release_allowed": release_allowed,
        "plain_status": str(briefing.get("plain_status") or ""),
        "primary_release_blocker": str(briefing.get("primary_release_blocker") or ""),
        "primary_roadmap_phase_id": str(briefing.get("primary_roadmap_phase_id") or ""),
        "primary_roadmap_bottleneck": str(briefing.get("primary_roadmap_bottleneck") or ""),
        "release_area_blocker_count": int(briefing.get("release_area_blocker_count") or 0),
        "release_area_owner_handoff_count": int(
            briefing.get("release_area_owner_handoff_count") or 0
        ),
        "blocked_science_or_beta_phase_count": int(
            briefing.get("blocked_science_or_beta_phase_count") or 0
        ),
        "blocked_science_or_beta_phases": [
            {
                "phase_id": str(row.get("phase_id") or ""),
                "roadmap_item": str(row.get("roadmap_item") or ""),
                "bottleneck": str(row.get("bottleneck") or ""),
                "first_blocker": str(row.get("first_blocker") or ""),
                "first_blocked_target": str(row.get("first_blocked_target") or ""),
            }
            for row in _as_list(briefing.get("blocked_science_or_beta_phases"))
            if isinstance(row, dict)
        ],
        "human_ux_summary": _human_ux_summary(briefing),
        "first_operator_handoff": first_handoff,
        "next_owner_action_count": len(_next_owner_actions(briefing)),
        "next_owner_actions": _next_owner_actions(briefing),
        "claim_boundaries": _str_list(briefing.get("claim_boundaries")),
        "blockers": blockers,
        "source_artifacts": {
            "goal_bottleneck_roadmap_surface": str(goal_surface),
        },
        "claim_boundary": (
            "This report is a plain-language read model over /goal bottleneck evidence. "
            "It does not create new release evidence, close human UX observation, attach "
            "public benchmark data, or unlock GPCR/PocketMD science claims."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Non-Expert Release Briefing",
        "",
        f"Status: `{payload.get('status', '')}`",
        f"Release allowed: `{payload.get('release_allowed', False)}`",
        f"Primary blocker: `{payload.get('primary_release_blocker', '') or 'none'}`",
        "",
        "## Plain Status",
        "",
        str(payload.get("plain_status") or "No plain-language status available."),
        "",
        "## Human UX Gate",
        "",
    ]
    human_ux = _as_dict(payload.get("human_ux_summary"))
    lines.extend(
        [
            f"- Status: `{human_ux.get('status', '')}`",
            f"- Owner action: {human_ux.get('owner_action', '') or 'none'}",
            f"- Workflow steps passed: `{human_ux.get('workflow_step_pass_count', 0)}/{human_ux.get('required_workflow_step_count', 0)}`",
            "",
            "## Science And Beta Blockers",
            "",
        ]
    )
    phases = _as_list(payload.get("blocked_science_or_beta_phases"))
    if phases:
        for row in phases:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- "
                f"`{row.get('phase_id', '')}`: {row.get('roadmap_item', '')} "
                f"blocked by `{row.get('first_blocker', '') or row.get('bottleneck', '')}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## First Owner Handoff", ""])
    handoff = _as_dict(payload.get("first_operator_handoff"))
    if handoff:
        lines.extend(
            [
                f"- Slot: `{handoff.get('slot_id', '') or handoff.get('handoff_id', '')}`",
                f"- Action: {handoff.get('first_next_action', '') or 'none'}",
                f"- Template: `{handoff.get('template_artifact', '') or 'none'}`",
            ]
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Claim Boundaries", ""])
    boundaries = _str_list(payload.get("claim_boundaries"))
    lines.extend(f"- `{item}`" for item in boundaries)
    lines.extend(["", "## Report Boundary", "", str(payload.get("claim_boundary") or "")])
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--goal-surface", type=Path, default=DEFAULT_GOAL_SURFACE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(repo_root=args.repo_root, goal_surface=args.goal_surface)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(_markdown(payload), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_blocked and not payload["contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
