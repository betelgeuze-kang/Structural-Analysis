#!/usr/bin/env python3
"""Build an owner intake packet for UX new-user observation release evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ux-new-user-observation-intake-packet.v1"
DEFAULT_OBSERVATION = Path("implementation/phase1/release_evidence/productization/ux_new_user_observation.json")
DEFAULT_TEMPLATE = Path("docs/templates/ux_new_user_observation.template.json")
DEFAULT_OBSERVATION_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

FIELD_SPECS = (
    {
        "field": "contract_pass",
        "required_value": "true",
        "check": "contract_signal_pass",
        "owner_note": "Observation source must explicitly opt into release evidence, not remain draft or template-only.",
    },
    {
        "field": "participant_ref",
        "required_value": "stable anonymized participant reference",
        "check": "required_fields_present",
        "owner_note": "Use an anonymized participant/session reference so reviewers can trace the observation without storing raw personal data.",
    },
    {
        "field": "participant_role",
        "required_value": "new_user | first_time_user | pilot_user",
        "check": "participant_role_new_user_pass",
        "owner_note": "Participant must be new to the product workflow being released.",
    },
    {
        "field": "new_to_product",
        "required_value": "true",
        "check": "new_to_product_pass",
        "owner_note": "Do not use expert/operator rehearsals as PM UX release-area evidence.",
    },
    {
        "field": "sample_project_id",
        "required_value": "sample project identifier used in the observed workflow",
        "check": "required_fields_present",
        "owner_note": "Must identify the exact sample project completed by the participant.",
    },
    {
        "field": "workflow_scope",
        "required_value": "observed workflow scope covering the full five-step workflow",
        "check": "required_fields_present",
        "owner_note": "Scope should match the paid-pilot workflow promised to customers.",
    },
    {
        "field": "workflow_steps",
        "required_value": (
            "all five steps observed and passed: Import, Model Health, Analysis Setup, "
            "Run & Monitor, Compare & Report"
        ),
        "check": "all_required_workflow_steps_passed",
        "owner_note": "Each required workflow step must have a human-observed pass/outcome signal.",
    },
    {
        "field": "observer",
        "required_value": "human observer or UX research owner",
        "check": "required_fields_present",
        "owner_note": "Automated browser smoke tests do not satisfy this field.",
    },
    {
        "field": "started_at_utc",
        "required_value": "timezone-aware ISO-8601 observation start timestamp",
        "check": "started_at_utc_valid",
        "owner_note": "Use a timezone-aware ISO-8601 timestamp with Z or an explicit UTC offset.",
    },
    {
        "field": "completed_at_utc",
        "required_value": "timezone-aware ISO-8601 observation completion timestamp",
        "check": "completed_at_utc_valid",
        "owner_note": "Use a timezone-aware ISO-8601 timestamp with Z or an explicit UTC offset.",
    },
    {
        "field": "completion_minutes",
        "required_value": "<= 30.0 and matches timestamp elapsed minutes",
        "check": "completion_30min_pass",
        "owner_note": "Completion time must prove the PM 30-minute UX gate and match wall-clock timestamps.",
    },
    {
        "field": "blocker_count",
        "required_value": "0",
        "check": "blocker_count_zero_pass",
        "owner_note": "Blocking usability issues keep the UX release area blocked.",
    },
    {
        "field": "evidence_ref",
        "required_value": "non-placeholder evidence reference",
        "check": "required_fields_present",
        "owner_note": "Reference the observation note, ticket, recording, or signed evidence bundle.",
    },
    {
        "field": "approval_decision",
        "required_value": "accepted | approved | pass | signed | approved_for_release",
        "check": "approval_decision_pass",
        "owner_note": "Decision must explicitly accept the observation for release evidence.",
    },
)
DERIVED_CHECK_SPECS = (
    {
        "field": "timestamp_order",
        "required_value": "completed_at_utc >= started_at_utc",
        "check": "timestamp_order_pass",
        "owner_note": "Completion timestamp must not precede the observed start timestamp.",
    },
    {
        "field": "elapsed_minutes",
        "required_value": "<= 30.0 from completed_at_utc - started_at_utc",
        "check": "elapsed_30min_pass",
        "owner_note": "The PM 30-minute gate is enforced from parsed wall-clock timestamps.",
    },
    {
        "field": "completion_minutes_elapsed_match",
        "required_value": "completion_minutes equals elapsed_minutes within tolerance",
        "check": "completion_minutes_elapsed_match_pass",
        "owner_note": "Declared completion_minutes must match computed elapsed minutes within the report tolerance.",
    },
    {
        "field": "workflow_step_coverage",
        "required_value": "required workflow observed count == 5/5",
        "check": "all_required_workflow_steps_observed",
        "owner_note": "The observed task must cover Import through Compare & Report without skipped steps.",
    },
    {
        "field": "workflow_step_placeholders",
        "required_value": "no placeholder workflow step labels or outcomes",
        "check": "workflow_step_placeholders_absent",
        "owner_note": "Template workflow step placeholders must be replaced with real observed outcomes.",
    },
    {
        "field": "evidence_ref_resolvable",
        "required_value": "https URL, ticket/jira/ux/user-study reference, or existing local evidence path",
        "check": "evidence_ref_resolvable_pass",
        "owner_note": "The 30-minute sample must point to a retrievable note, ticket, recording, or signed bundle.",
    },
    {
        "field": "evidence_ref_not_self_reference",
        "required_value": "evidence_ref must not point back to the observation JSON itself",
        "check": "evidence_ref_not_self_reference_pass",
        "owner_note": "Self-references do not prove that separate human-observation evidence exists.",
    },
    {
        "field": "evidence_ref_not_template_reference",
        "required_value": "evidence_ref must not point to the UX observation template",
        "check": "evidence_ref_not_template_reference_pass",
        "owner_note": "Templates are owner input aids, not human observation evidence.",
    },
    {
        "field": "evidence_ref_not_template_artifact",
        "required_value": "evidence_ref must not point to docs/templates or a .template.* artifact",
        "check": "evidence_ref_not_template_artifact_pass",
        "owner_note": "Any template-like file is rejected as human observation evidence.",
    },
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value if value is not None else "")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _field_status(*, field: str, check_name: str, observation_report: dict[str, Any]) -> dict[str, Any]:
    checks = _as_dict(observation_report.get("checks"))
    summary = _as_dict(observation_report.get("summary"))
    missing_fields = {str(item) for item in _as_list(summary.get("missing_fields"))}
    placeholder_fields = {str(item) for item in _as_list(summary.get("placeholder_fields"))}
    missing = field in missing_fields
    placeholder = field in placeholder_fields
    workflow_source_missing = field.startswith("workflow_step_") and "workflow_steps" in missing_fields
    if check_name == "required_fields_present":
        check_pass = (not missing) and (not placeholder)
    else:
        check_pass = bool(checks.get(check_name, False)) and not missing and not placeholder and not workflow_source_missing
    return {
        "missing": missing,
        "placeholder": placeholder,
        "check_pass": check_pass,
    }


def _current_value(field: str, observation: dict[str, Any], summary: dict[str, Any]) -> Any:
    if field == "timestamp_order":
        started = summary.get("started_at_utc")
        completed = summary.get("completed_at_utc")
        return f"{started} <= {completed}" if started or completed else ""
    if field == "elapsed_minutes":
        return summary.get("elapsed_minutes")
    if field == "completion_minutes_elapsed_match":
        declared = summary.get("declared_completion_minutes", summary.get("completion_minutes"))
        elapsed = summary.get("elapsed_minutes")
        tolerance = summary.get("timestamp_tolerance_minutes")
        return f"declared={declared}; elapsed={elapsed}; tolerance={tolerance}"
    if field == "workflow_step_coverage":
        return (
            f"pass={summary.get('workflow_step_pass_count')}/"
            f"{summary.get('required_workflow_step_count')}; "
            f"missing={summary.get('missing_workflow_steps')}"
        )
    if field == "workflow_step_placeholders":
        return summary.get("placeholder_workflow_steps")
    if field == "evidence_ref_resolvable":
        return (
            f"ref={summary.get('evidence_ref', '')}; "
            f"kind={summary.get('evidence_ref_kind', '')}; "
            f"resolved={summary.get('evidence_ref_resolved_path', '')}"
        )
    if field == "evidence_ref_not_self_reference":
        return summary.get("evidence_ref_resolved_path", "")
    if field == "evidence_ref_not_template_reference":
        return summary.get("evidence_ref_resolved_path", "")
    if field == "evidence_ref_not_template_artifact":
        return summary.get("evidence_ref_resolved_path", "")
    return observation.get(field)


def _gate_unblock_plan(
    *,
    observation_path: Path,
    template_path: Path,
    observation_report_path: Path,
    report: dict[str, Any],
    field_rows: list[dict[str, Any]],
    validation_commands: list[str],
    contract_pass: bool,
) -> list[dict[str, Any]]:
    if contract_pass:
        return []
    report_plan = report.get("gate_unblock_plan")
    if isinstance(report_plan, list) and report_plan:
        return [
            row
            for row in report_plan
            if isinstance(row, dict)
        ]
    failing_fields = [
        str(row["field"])
        for row in field_rows
        if row.get("report_check_pass") is not True
    ]
    return [
        {
            "slot_id": "attach_observation_record",
            "required_artifact": str(observation_path),
            "template_artifact": str(template_path),
            "observation_report": str(observation_report_path),
            "failing_fields": failing_fields,
            "minimum_evidence": [
                "real human new-user observation record",
                "all required fields populated without OWNER_INPUT_REQUIRED placeholders",
                "contract_pass=true only after the observation is complete",
            ],
        },
        {
            "slot_id": "rerun_validation_chain",
            "validation_commands": validation_commands,
            "minimum_evidence": [
                "ux_new_user_observation_report.json contract_pass=true",
                "ux_new_user_observation_intake_packet.json contract_pass=true",
                "PM release and Developer Preview RC gates refreshed",
            ],
        },
    ]


def _next_actions(contract_pass: bool) -> list[str]:
    if contract_pass:
        return []
    return [
        "fill_ux_new_user_observation_record_from_template",
        "run_30_minute_human_new_user_core_workflow_observation",
        "rerun_ux_observation_validation_chain",
    ]


def build_packet(
    *,
    observation_path: Path = DEFAULT_OBSERVATION,
    template_path: Path = DEFAULT_TEMPLATE,
    observation_report_path: Path = DEFAULT_OBSERVATION_REPORT,
) -> dict[str, Any]:
    observation = _load_json(observation_path)
    template = _load_json(template_path)
    report = _load_json(observation_report_path)
    blockers = [str(blocker) for blocker in _as_list(report.get("blockers"))]
    summary = _as_dict(report.get("summary"))

    field_rows: list[dict[str, Any]] = []
    for spec in (*FIELD_SPECS, *DERIVED_CHECK_SPECS):
        field = str(spec["field"])
        status = _field_status(
            field=field,
            check_name=str(spec["check"]),
            observation_report=report,
        )
        field_rows.append(
            {
                "field": field,
                "required_value": str(spec["required_value"]),
                "current_value": _display_value(_current_value(field, observation, summary)),
                "template_value": _display_value(template.get(field, "derived from observation timestamps")),
                "report_check": str(spec["check"]),
                "report_check_pass": bool(status["check_pass"]),
                "missing": bool(status["missing"]),
                "placeholder": bool(status["placeholder"]),
                "owner_note": str(spec["owner_note"]),
            }
        )

    contract_pass = bool(report.get("contract_pass", False))
    validation_commands = [
        f"python3 scripts/build_ux_new_user_observation_report.py --out {DEFAULT_OBSERVATION_REPORT}",
        f"python3 scripts/build_ux_new_user_observation_intake_packet.py --out {DEFAULT_OUT}",
        "python3 scripts/report_pm_release_gate.py "
        "--out implementation/phase1/release_evidence/productization/pm_release_gate_report.json "
        "--out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        "python3 scripts/build_pm_release_blocker_action_register.py "
        "--out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json "
        "--out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
    ]
    gate_unblock_plan = _gate_unblock_plan(
        observation_path=observation_path,
        template_path=template_path,
        observation_report_path=observation_report_path,
        report=report,
        field_rows=field_rows,
        validation_commands=validation_commands,
        contract_pass=contract_pass,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_UX_NEW_USER_OBSERVATION_OWNER_INPUT_REQUIRED",
        "observation_path": str(observation_path),
        "template_path": str(template_path),
        "observation_report_path": str(observation_report_path),
        "summary_line": (
            f"UX new-user observation intake: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"fields={sum(1 for row in field_rows if row['report_check_pass'])}/{len(field_rows)} | "
            f"blockers={len(blockers)}"
        ),
        "summary": {
            "owner_action": str(
                summary.get(
                    "owner_action",
                    "Attach a human new-user observation record for the sample project workflow.",
                )
            ),
            "observation_contract_pass": contract_pass,
            "observation_blocker_count": len(blockers),
            "field_count": len(field_rows),
            "field_pass_count": sum(1 for row in field_rows if row["report_check_pass"]),
            "completion_minutes": summary.get("completion_minutes"),
            "declared_completion_minutes": summary.get("declared_completion_minutes", summary.get("completion_minutes")),
            "elapsed_minutes": summary.get("elapsed_minutes"),
            "max_completion_minutes": summary.get("max_completion_minutes", 30.0),
            "timestamp_tolerance_minutes": summary.get("timestamp_tolerance_minutes"),
            "required_workflow_steps": summary.get("required_workflow_steps", []),
            "workflow_step_count": summary.get("workflow_step_count", 0),
            "required_workflow_step_count": summary.get("required_workflow_step_count", 0),
            "workflow_step_pass_count": summary.get("workflow_step_pass_count", 0),
            "missing_workflow_steps": summary.get("missing_workflow_steps", []),
            "not_passed_workflow_steps": summary.get("not_passed_workflow_steps", []),
            "placeholder_workflow_steps": summary.get("placeholder_workflow_steps", []),
            "evidence_ref": summary.get("evidence_ref", ""),
            "evidence_ref_kind": summary.get("evidence_ref_kind", ""),
            "evidence_ref_resolved_path": summary.get("evidence_ref_resolved_path", ""),
        },
        "field_rows": field_rows,
        "current_blockers": blockers,
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "next_actions": _next_actions(contract_pass),
        "validation_commands": validation_commands,
        "claim_boundary": (
            "This intake packet is an owner handoff checklist. It does not create human observation evidence "
            "and does not make the PM UX release area pass until the observation report passes."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# UX New-User Observation Intake Packet",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `gate_unblock_plan_count`: `{payload['gate_unblock_plan_count']}`",
        f"- `observation_path`: `{payload['observation_path']}`",
        f"- `template_path`: `{payload['template_path']}`",
        f"- `owner_action`: {payload['summary']['owner_action']}",
        "",
        "| Field | Current | Template | Required | Report Check |",
        "|---|---|---|---|---|",
    ]
    for row in payload["field_rows"]:
        lines.append(
            f"| `{cell(row['field'])}` | `{cell(row['current_value'])}` | `{cell(row['template_value'])}` | "
            f"{cell(row['required_value'])} | `{cell(row['report_check'])}` = `{row['report_check_pass']}` |"
        )
    lines.extend(["", "## Gate Unblock Plan", ""])
    if payload["gate_unblock_plan"]:
        for row in payload["gate_unblock_plan"]:
            lines.append(f"- `{cell(row['slot_id'])}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, default=DEFAULT_OBSERVATION)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--observation-report", type=Path, default=DEFAULT_OBSERVATION_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(
        observation_path=args.observation,
        template_path=args.template,
        observation_report_path=args.observation_report,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
