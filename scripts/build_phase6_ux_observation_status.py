#!/usr/bin/env python3
"""Build a conservative Phase 6 new-user workflow observation status receipt."""

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
DEFAULT_OUT = PRODUCTIZATION / "phase6_ux_observation_status.json"
UX_OBSERVATION = PRODUCTIZATION / "ux_new_user_observation_report.json"
UX_OBSERVATION_INTAKE = PRODUCTIZATION / "ux_new_user_observation_intake_packet.json"
PHASE5_GUI_WORKFLOW = PRODUCTIZATION / "phase5_gui_workflow_readiness_receipt.json"
SCHEMA_VERSION = "phase6-ux-observation-status.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


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


def _blockers(payload: dict[str, Any]) -> list[str]:
    return [str(blocker) for blocker in _as_list(payload.get("blockers")) if str(blocker)]


def _workflow_step_ids(rows: Any) -> set[str]:
    return {str(row.get("id")) for row in _as_list(rows) if isinstance(row, dict) and str(row.get("id", ""))}


def build_phase6_ux_observation_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    observation = _load_json(repo_root, UX_OBSERVATION)
    intake = _load_json(repo_root, UX_OBSERVATION_INTAKE)
    phase5 = _load_json(repo_root, PHASE5_GUI_WORKFLOW)

    observation_summary = _as_dict(observation.get("summary"))
    intake_summary = _as_dict(intake.get("summary"))
    required_steps = _as_list(phase5.get("required_workflow_steps")) or _as_list(
        observation_summary.get("required_workflow_steps")
    )
    required_step_ids = _workflow_step_ids(required_steps)
    required_step_count = len(required_step_ids) or int(
        observation_summary.get("required_workflow_step_count", 5) or 5
    )

    human_observation_pass = bool(observation.get("contract_pass") is True)
    intake_pass = bool(intake.get("contract_pass") is True)
    phase5_contract_pass = bool(phase5.get("contract_pass") is True)
    phase5_shell_count = int(phase5.get("workflow_shell_step_pass_count", 0) or 0)
    phase5_execution_count = int(phase5.get("execution_workflow_step_pass_count", 0) or 0)
    observation_workflow_pass_count = int(observation_summary.get("workflow_step_pass_count", 0) or 0)
    intake_workflow_pass_count = int(intake_summary.get("workflow_step_pass_count", 0) or 0)
    task_based_ux_test = _as_dict(phase5.get("task_based_ux_test"))
    browser_execution_passed = bool(task_based_ux_test.get("browser_execution_passed") is True)

    missing_observation_steps = [
        str(step) for step in _as_list(observation_summary.get("missing_workflow_steps")) if str(step)
    ]
    not_passed_observation_steps = [
        str(step) for step in _as_list(observation_summary.get("not_passed_workflow_steps")) if str(step)
    ]
    missing_execution_steps = [
        str(step) for step in _as_list(phase5.get("missing_execution_workflow_steps")) if str(step)
    ]

    blockers: list[str] = []
    if not human_observation_pass:
        blockers.append("human_new_user_observation_not_passed")
    if not intake_pass:
        blockers.append("ux_observation_intake_packet_not_passed")
    if observation_workflow_pass_count < required_step_count:
        blockers.append(
            f"human_observation_workflow_step_pass_count_below_required:"
            f"{observation_workflow_pass_count}/{required_step_count}"
        )
    if missing_observation_steps:
        blockers.append(f"human_observation_required_workflow_steps_missing:{len(missing_observation_steps)}")
    if not_passed_observation_steps:
        blockers.append(f"human_observation_required_workflow_steps_not_passed:{len(not_passed_observation_steps)}")
    if phase5_execution_count < required_step_count:
        blockers.append(f"phase5_workflow_execution_not_proven:{phase5_execution_count}/{required_step_count}")
    if not phase5_contract_pass:
        blockers.append("phase5_gui_workflow_readiness_not_passed")
    if not browser_execution_passed:
        blockers.append("task_based_ux_browser_execution_not_passed")

    blockers.extend(f"observation_report:{blocker}" for blocker in _blockers(observation))
    blockers.extend(f"phase5_gui_workflow:{blocker}" for blocker in _blockers(phase5))
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = bool(
        human_observation_pass
        and intake_pass
        and phase5_contract_pass
        and browser_execution_passed
        and observation_workflow_pass_count >= required_step_count
        and phase5_execution_count >= required_step_count
        and not blockers
    )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                UX_OBSERVATION,
                UX_OBSERVATION_INTAKE,
                PHASE5_GUI_WORKFLOW,
                Path("scripts/build_phase6_ux_observation_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="phase6_ux_observation_status_aggregates_human_observation_and_phase5_gui_receipts",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "developer_preview_release_candidate_claim": contract_pass,
        "human_observation_gate": {
            "status": "ready" if human_observation_pass else "blocked",
            "contract_pass": human_observation_pass,
            "receipt": UX_OBSERVATION.as_posix(),
            "required_workflow_step_count": required_step_count,
            "workflow_step_pass_count": observation_workflow_pass_count,
            "missing_workflow_steps": missing_observation_steps,
            "not_passed_workflow_steps": not_passed_observation_steps,
            "blockers": _blockers(observation),
            "owner_action": str(observation_summary.get("owner_action", "")),
        },
        "intake_packet_gate": {
            "status": "ready" if intake_pass else "blocked",
            "contract_pass": intake_pass,
            "receipt": UX_OBSERVATION_INTAKE.as_posix(),
            "field_pass_count": int(intake_summary.get("field_pass_count", 0) or 0),
            "field_count": int(intake_summary.get("field_count", 0) or 0),
            "workflow_step_pass_count": intake_workflow_pass_count,
            "blockers": _as_list(intake.get("current_blockers")),
        },
        "phase5_workflow_gate": {
            "status": "ready" if phase5_contract_pass else "blocked",
            "contract_pass": phase5_contract_pass,
            "receipt": PHASE5_GUI_WORKFLOW.as_posix(),
            "required_workflow_step_count": required_step_count,
            "workflow_shell_step_pass_count": phase5_shell_count,
            "execution_workflow_step_pass_count": phase5_execution_count,
            "missing_execution_workflow_steps": missing_execution_steps,
            "task_based_ux_browser_execution_passed": browser_execution_passed,
            "task_based_ux_browser_execution_status": str(
                task_based_ux_test.get("browser_execution_status", "missing")
            ),
            "task_based_ux_browser_execution_blocker": str(
                task_based_ux_test.get("execution_blocker", "")
            ),
            "blockers": _blockers(phase5),
        },
        "readiness_inputs": {
            "ux_new_user_observation_report": UX_OBSERVATION.as_posix(),
            "ux_new_user_observation_intake_packet": UX_OBSERVATION_INTAKE.as_posix(),
            "phase5_gui_workflow_readiness_receipt": PHASE5_GUI_WORKFLOW.as_posix(),
        },
        "blockers": blockers,
        "owner_action": (
            "Attach a passing human new-user observation for all five workflow steps, "
            "keep the intake packet in sync, attach GUI execution/browser evidence, "
            "then rerun this Phase 6 UX status before promoting the RC UX gate."
        ),
        "summary_line": (
            "Phase 6 UX observation: "
            f"{'READY' if contract_pass else 'BLOCKED'} | human="
            f"{observation_workflow_pass_count}/{required_step_count} | execution="
            f"{phase5_execution_count}/{required_step_count} | browser={browser_execution_passed}"
        ),
        "claim_boundary": (
            "This receipt aggregates human new-user observation, owner intake, and "
            "Phase 5 GUI execution evidence for the RC UX gate. The intake packet is "
            "only a handoff checklist, automated browser/task tests do not replace a "
            "human observation, and visible workflow shell coverage does not prove a "
            "successful new-user workflow."
        ),
    }


def write_phase6_ux_observation_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_phase6_ux_observation_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase6_ux_observation_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_phase6_ux_observation_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase6_ux_observation_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase6_ux_observation_status_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase6_ux_observation_status_mismatch"
    return True, "phase6_ux_observation_status_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase6_ux_observation_status(out_path=args.out)
        print(f"Phase 6 UX observation status check: {message}")
        return 0 if ok else 1
    payload = write_phase6_ux_observation_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
