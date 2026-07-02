#!/usr/bin/env python3
"""Fill ux_new_user_observation.json from explicit human observation metadata."""

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

import build_ux_new_user_observation_report as observation_report  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "ux-new-user-observation-human-sample-fill.v1"
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation.json"
)
DEFAULT_REPORT_OUT = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation.fill_report.json"
)
DEFAULT_WORKFLOW_SCOPE = (
    "Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report"
)
ALLOWED_PARTICIPANT_ROLES = ("first_time_user", "new_user", "pilot_user")


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _bool_text(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _parse_workflow_step(value: str) -> dict[str, Any]:
    separator = "=" if "=" in value else ":"
    if separator not in value:
        raise argparse.ArgumentTypeError("workflow step must look like step_id=outcome")
    step_id, outcome = [part.strip() for part in value.split(separator, 1)]
    if not step_id or not outcome:
        raise argparse.ArgumentTypeError("workflow step id and outcome are required")
    return {"id": step_id, "label": step_id.replace("_", " ").title(), "outcome": outcome}


def _required_workflow_steps_passed() -> list[dict[str, str]]:
    return [
        {
            "id": str(step["id"]),
            "label": str(step["label"]),
            "outcome": "passed",
        }
        for step in observation_report.REQUIRED_WORKFLOW_STEPS
    ]


def _observation_payload(
    *,
    participant_ref: str,
    participant_role: str,
    new_to_product: bool,
    sample_project_id: str,
    workflow_scope: str,
    workflow_steps: list[dict[str, Any]],
    observer: str,
    started_at_utc: str,
    completed_at_utc: str,
    completion_minutes: float,
    blocker_count: int,
    evidence_ref: str,
    approval_decision: str,
    note: str,
) -> dict[str, Any]:
    return {
        "contract_pass": True,
        "participant_ref": participant_ref,
        "participant_role": participant_role,
        "new_to_product": new_to_product,
        "sample_project_id": sample_project_id,
        "workflow_scope": workflow_scope,
        "workflow_steps": workflow_steps,
        "observer": observer,
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "completion_minutes": completion_minutes,
        "blocker_count": blocker_count,
        "evidence_ref": evidence_ref,
        "approval_decision": approval_decision,
        "template_only": False,
        "note": note,
    }


def fill_ux_new_user_observation(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    template_path: Path = observation_report.DEFAULT_TEMPLATE,
    participant_ref: str,
    participant_role: str,
    new_to_product: bool,
    sample_project_id: str,
    observer: str,
    started_at_utc: str,
    completed_at_utc: str,
    completion_minutes: float,
    blocker_count: int,
    evidence_ref: str,
    approval_decision: str,
    workflow_scope: str = DEFAULT_WORKFLOW_SCOPE,
    workflow_steps: list[dict[str, Any]] | None = None,
    all_required_steps_passed: bool = False,
    note: str = "Populated from explicit human new-user observation metadata.",
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    steps = list(workflow_steps or [])
    if all_required_steps_passed and not steps:
        steps = _required_workflow_steps_passed()
    observation = _observation_payload(
        participant_ref=participant_ref,
        participant_role=participant_role,
        new_to_product=new_to_product,
        sample_project_id=sample_project_id,
        workflow_scope=workflow_scope,
        workflow_steps=steps,
        observer=observer,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        completion_minutes=float(completion_minutes),
        blocker_count=int(blocker_count),
        evidence_ref=evidence_ref,
        approval_decision=approval_decision,
        note=note,
    )
    resolved_out.write_text(_json_text(observation), encoding="utf-8")
    validation = observation_report.build_report(
        observation_path=out,
        template_path=template_path,
        repo_root=repo_root,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/fill_ux_new_user_observation_from_human_sample.py"),
                Path("scripts/build_ux_new_user_observation_report.py"),
                template_path,
                out,
            ],
            reused_evidence=False,
            reuse_policy="ux_new_user_observation_filled_from_explicit_human_sample_metadata",
            repo_root=repo_root,
        ),
        "status": "filled" if validation.get("contract_pass") is True else "blocked",
        "contract_pass": validation.get("contract_pass") is True,
        "observation_path": out.as_posix(),
        "template_path": template_path.as_posix(),
        "observation": observation,
        "validation_status": validation.get("status", ""),
        "validation_reason_code": validation.get("reason_code", ""),
        "validation_blockers": validation.get("blockers", []),
        "validation_summary_line": validation.get("summary_line", ""),
        "validation_commands": validation.get("validation_commands", []),
        "claim_boundary": (
            "This helper materializes a UX observation record from explicit human "
            "new-user sample metadata and immediately validates it. It does not "
            "create the underlying human observation, recording, note, ticket, or "
            "release approval evidence."
        ),
    }


def write_report(*, payload: dict[str, Any], repo_root: Path, out: Path | None) -> None:
    if out is None:
        return
    resolved = _resolve(repo_root, out)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--template", type=Path, default=observation_report.DEFAULT_TEMPLATE)
    parser.add_argument("--participant-ref", required=True)
    parser.add_argument("--participant-role", choices=ALLOWED_PARTICIPANT_ROLES, required=True)
    parser.add_argument("--new-to-product", type=_bool_text, required=True)
    parser.add_argument("--sample-project-id", required=True)
    parser.add_argument("--workflow-scope", default=DEFAULT_WORKFLOW_SCOPE)
    parser.add_argument(
        "--workflow-step",
        action="append",
        type=_parse_workflow_step,
        default=[],
        help="Observed workflow step in step_id=outcome form. Repeatable.",
    )
    parser.add_argument(
        "--all-required-steps-passed",
        action="store_true",
        help="Materialize all five required workflow steps with outcome=passed.",
    )
    parser.add_argument("--observer", required=True)
    parser.add_argument("--started-at-utc", required=True)
    parser.add_argument("--completed-at-utc", required=True)
    parser.add_argument("--completion-minutes", type=float, required=True)
    parser.add_argument("--blocker-count", type=int, required=True)
    parser.add_argument("--evidence-ref", required=True)
    parser.add_argument(
        "--approval-decision",
        choices=sorted(observation_report.ACCEPTED_DECISIONS),
        required=True,
    )
    parser.add_argument(
        "--note",
        default="Populated from explicit human new-user observation metadata.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = fill_ux_new_user_observation(
        repo_root=args.repo_root,
        out=args.out,
        template_path=args.template,
        participant_ref=args.participant_ref,
        participant_role=args.participant_role,
        new_to_product=args.new_to_product,
        sample_project_id=args.sample_project_id,
        workflow_scope=args.workflow_scope,
        workflow_steps=args.workflow_step,
        all_required_steps_passed=args.all_required_steps_passed,
        observer=args.observer,
        started_at_utc=args.started_at_utc,
        completed_at_utc=args.completed_at_utc,
        completion_minutes=args.completion_minutes,
        blocker_count=args.blocker_count,
        evidence_ref=args.evidence_ref,
        approval_decision=args.approval_decision,
        note=args.note,
    )
    write_report(payload=payload, repo_root=args.repo_root, out=args.report_out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "ux new-user observation fill: "
            f"{payload['status'].upper()} | "
            f"contract_pass={payload['contract_pass']} | "
            f"blockers={len(payload['validation_blockers'])}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
