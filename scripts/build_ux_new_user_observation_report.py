#!/usr/bin/env python3
"""Validate human new-user sample workflow observation evidence for the PM UX gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import input_checksums  # noqa: E402


SCHEMA_VERSION = "ux-new-user-observation-report.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_OBSERVATION = Path("implementation/phase1/release_evidence/productization/ux_new_user_observation.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_TEMPLATE = Path("docs/templates/ux_new_user_observation.template.json")
DEFAULT_TIMESTAMP_TOLERANCE_MINUTES = 1.0
ACCEPTED_DECISIONS = {"accepted", "approved", "pass", "signed", "approved_for_release"}
EXTERNAL_REFERENCE_PREFIXES = ("ticket:", "jira:", "ux:", "user-study:")
PLACEHOLDER_MARKERS = ("TODO", "TBD", "PLACEHOLDER", "TEMPLATE", "REPLACE_ME", "OWNER_INPUT_REQUIRED")
PLACEHOLDER_TOKENS = {
    "SAMPLE-PROJECT-ID",
    "UX-OBSERVATION-EVIDENCE-REF",
}
REQUIRED_FIELDS = (
    "contract_pass",
    "participant_role",
    "new_to_product",
    "sample_project_id",
    "workflow_scope",
    "workflow_steps",
    "observer",
    "started_at_utc",
    "completed_at_utc",
    "completion_minutes",
    "blocker_count",
    "evidence_ref",
    "approval_decision",
)
REQUIRED_WORKFLOW_STEPS = (
    {"id": "import", "label": "Import"},
    {"id": "model_health", "label": "Model Health"},
    {"id": "analysis_setup", "label": "Analysis Setup"},
    {"id": "run_monitor", "label": "Run & Monitor"},
    {"id": "compare_report", "label": "Compare & Report"},
)
PASS_STEP_STATUSES = {"pass", "passed", "complete", "completed", "accepted", "ok", "success", "successful"}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _field_present(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _looks_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    upper = value.strip().upper()
    return bool(not upper or upper in PLACEHOLDER_TOKENS or any(marker in upper for marker in PLACEHOLDER_MARKERS))


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_step_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().lower().replace("&", "and")
    for char in (" ", "-", "/"):
        normalized = normalized.replace(char, "_")
    aliases = {
        "run_and_monitor": "run_monitor",
        "compare_and_report": "compare_report",
    }
    return aliases.get(normalized, normalized)


def _workflow_step_rows(observation: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = observation.get("workflow_steps")
    rows: list[dict[str, Any]] = []
    if isinstance(raw_steps, dict):
        iterable = [
            {"id": key, **(value if isinstance(value, dict) else {"outcome": value})}
            for key, value in raw_steps.items()
        ]
    elif isinstance(raw_steps, list):
        iterable = raw_steps
    else:
        iterable = []

    for raw in iterable:
        if isinstance(raw, str):
            step_id = _normalize_step_id(raw)
            label = raw.strip()
            outcome = ""
            explicit_pass = None
        elif isinstance(raw, dict):
            step_id = _normalize_step_id(
                raw.get("id") or raw.get("step_id") or raw.get("step") or raw.get("name") or raw.get("label")
            )
            label = str(raw.get("label") or raw.get("name") or raw.get("step") or step_id)
            outcome = str(raw.get("outcome") or raw.get("status") or raw.get("result") or "").strip().lower()
            explicit_pass = raw.get("pass") if "pass" in raw else raw.get("passed")
        else:
            continue
        passed = bool(explicit_pass is True or outcome in PASS_STEP_STATUSES)
        placeholder = _looks_placeholder(label) or _looks_placeholder(outcome)
        rows.append(
            {
                "id": step_id,
                "label": label,
                "outcome": outcome,
                "pass": passed,
                "placeholder": placeholder,
            }
        )
    return rows


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _evidence_ref_resolution(
    reference: Any,
    *,
    observation_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    if not isinstance(reference, str):
        return {"kind": "missing", "resolvable": False, "resolved_path": ""}
    text = reference.strip()
    if not text:
        return {"kind": "missing", "resolvable": False, "resolved_path": ""}
    if text.lower().startswith(EXTERNAL_REFERENCE_PREFIXES):
        suffix = text.split(":", 1)[1].strip()
        return {"kind": "external_reference", "resolvable": bool(suffix), "resolved_path": ""}
    parsed = urlparse(text)
    if parsed.scheme:
        if parsed.scheme == "https" and bool(parsed.netloc):
            return {"kind": "https_url", "resolvable": True, "resolved_path": ""}
        return {"kind": "unsupported_url", "resolvable": False, "resolved_path": ""}
    path = Path(text).expanduser()
    candidates = [path] if path.is_absolute() else [repo_root / path, observation_path.parent / path]
    for candidate in candidates:
        if candidate.exists():
            return {"kind": "local_path", "resolvable": True, "resolved_path": str(candidate)}
    return {"kind": "local_path_missing", "resolvable": False, "resolved_path": ""}


def _same_resolved_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except Exception:
        return False


def build_report(
    *,
    observation_path: Path = DEFAULT_OBSERVATION,
    max_completion_minutes: float = 30.0,
    timestamp_tolerance_minutes: float = DEFAULT_TIMESTAMP_TOLERANCE_MINUTES,
    template_path: Path = DEFAULT_TEMPLATE,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    observation = _load_json(observation_path)
    missing_fields = [field for field in REQUIRED_FIELDS if not _field_present(observation, field)]
    placeholder_fields = [field for field in REQUIRED_FIELDS if _looks_placeholder(observation.get(field))]
    completion_minutes = _as_float(observation.get("completion_minutes"))
    started_at_raw = observation.get("started_at_utc")
    completed_at_raw = observation.get("completed_at_utc")
    started_at_present = _field_present(observation, "started_at_utc")
    completed_at_present = _field_present(observation, "completed_at_utc")
    started_at = _parse_datetime(started_at_raw)
    completed_at = _parse_datetime(completed_at_raw)
    timestamp_order_pass = bool(started_at is not None and completed_at is not None and completed_at >= started_at)
    elapsed_minutes = (
        round((completed_at - started_at).total_seconds() / 60.0, 6) if timestamp_order_pass else None
    )
    decision = str(observation.get("approval_decision", "")).strip().lower()
    participant_role = str(observation.get("participant_role", "")).strip().lower()
    new_to_product = observation.get("new_to_product") is True
    blocker_count = _as_int(observation.get("blocker_count"), 1)
    evidence_ref = observation.get("evidence_ref")
    evidence_ref_resolution = _evidence_ref_resolution(
        evidence_ref,
        observation_path=observation_path,
        repo_root=repo_root,
    )
    resolved_evidence_path = str(evidence_ref_resolution.get("resolved_path", "") or "")
    evidence_ref_self_reference = bool(
        resolved_evidence_path and _same_resolved_path(Path(resolved_evidence_path), observation_path)
    )
    evidence_ref_template_reference = bool(
        resolved_evidence_path and _same_resolved_path(Path(resolved_evidence_path), repo_root / template_path)
    )
    template_only = observation.get("template_only") is True
    template_note_present = _looks_placeholder(observation.get("note"))
    workflow_rows = _workflow_step_rows(observation)
    workflow_by_id = {row["id"]: row for row in workflow_rows if row["id"]}
    required_step_ids = [str(step["id"]) for step in REQUIRED_WORKFLOW_STEPS]
    missing_workflow_steps = [step_id for step_id in required_step_ids if step_id not in workflow_by_id]
    not_passed_workflow_steps = [
        step_id for step_id in required_step_ids if step_id in workflow_by_id and workflow_by_id[step_id]["pass"] is not True
    ]
    placeholder_workflow_steps = [
        row["id"] or row["label"] for row in workflow_rows if row["placeholder"] is True
    ]
    workflow_step_pass_count = sum(
        1 for step_id in required_step_ids if step_id in workflow_by_id and workflow_by_id[step_id]["pass"] is True
    )

    checks = {
        "observation_file_present": observation_path.exists(),
        "contract_signal_pass": _reason_pass(observation),
        "required_fields_present": not missing_fields,
        "placeholder_values_absent": not placeholder_fields,
        "template_only_absent": not template_only,
        "template_note_absent": not template_note_present,
        "participant_role_new_user_pass": participant_role in {"new_user", "first_time_user", "pilot_user"},
        "new_to_product_pass": new_to_product,
        "completion_minutes_present": completion_minutes is not None,
        "completion_30min_pass": bool(completion_minutes is not None and completion_minutes <= max_completion_minutes),
        "started_at_utc_valid": bool(started_at_present and started_at is not None),
        "completed_at_utc_valid": bool(completed_at_present and completed_at is not None),
        "timestamp_order_pass": timestamp_order_pass,
        "elapsed_minutes_present": elapsed_minutes is not None,
        "elapsed_30min_pass": bool(elapsed_minutes is not None and elapsed_minutes <= max_completion_minutes),
        "completion_minutes_elapsed_match_pass": bool(
            completion_minutes is not None
            and elapsed_minutes is not None
            and abs(completion_minutes - elapsed_minutes) <= timestamp_tolerance_minutes
        ),
        "workflow_steps_present": bool(workflow_rows),
        "workflow_step_placeholders_absent": not placeholder_workflow_steps,
        "all_required_workflow_steps_observed": not missing_workflow_steps,
        "all_required_workflow_steps_passed": bool(
            not missing_workflow_steps and not not_passed_workflow_steps and workflow_step_pass_count == len(required_step_ids)
        ),
        "blocker_count_zero_pass": blocker_count == 0,
        "evidence_ref_present_pass": _field_present(observation, "evidence_ref"),
        "evidence_ref_resolvable_pass": bool(evidence_ref_resolution["resolvable"]),
        "evidence_ref_not_self_reference_pass": bool(
            _field_present(observation, "evidence_ref")
            and evidence_ref_resolution["resolvable"]
            and not evidence_ref_self_reference
        ),
        "evidence_ref_not_template_reference_pass": bool(
            _field_present(observation, "evidence_ref")
            and evidence_ref_resolution["resolvable"]
            and not evidence_ref_template_reference
        ),
        "approval_decision_pass": decision in ACCEPTED_DECISIONS,
    }
    blockers = [
        *(["observation_file_missing"] if not checks["observation_file_present"] else []),
        *(["contract_signal_not_pass"] if not checks["contract_signal_pass"] else []),
        *(["required_fields_missing"] if not checks["required_fields_present"] else []),
        *(["placeholder_values_present"] if not checks["placeholder_values_absent"] else []),
        *(["template_only_observation_source"] if not checks["template_only_absent"] else []),
        *(["template_note_observation_source"] if not checks["template_note_absent"] else []),
        *(["participant_not_new_user"] if not checks["participant_role_new_user_pass"] else []),
        *(["new_to_product_not_confirmed"] if not checks["new_to_product_pass"] else []),
        *(["completion_minutes_missing"] if not checks["completion_minutes_present"] else []),
        *(["completion_gt_30min"] if completion_minutes is not None and not checks["completion_30min_pass"] else []),
        *(["started_at_utc_invalid"] if started_at_present and not checks["started_at_utc_valid"] else []),
        *(["completed_at_utc_invalid"] if completed_at_present and not checks["completed_at_utc_valid"] else []),
        *(
            ["completion_timestamp_order_invalid"]
            if started_at is not None and completed_at is not None and not checks["timestamp_order_pass"]
            else []
        ),
        *(["elapsed_minutes_missing"] if (started_at_present or completed_at_present) and elapsed_minutes is None else []),
        *(["elapsed_gt_30min"] if elapsed_minutes is not None and not checks["elapsed_30min_pass"] else []),
        *(
            ["completion_minutes_elapsed_mismatch"]
            if completion_minutes is not None
            and elapsed_minutes is not None
            and not checks["completion_minutes_elapsed_match_pass"]
            else []
        ),
        *(["workflow_steps_missing"] if not checks["workflow_steps_present"] else []),
        *(["workflow_step_placeholders_present"] if not checks["workflow_step_placeholders_absent"] else []),
        *(["required_workflow_steps_missing"] if not checks["all_required_workflow_steps_observed"] else []),
        *(["required_workflow_step_not_passed"] if not checks["all_required_workflow_steps_passed"] else []),
        *(["blocking_usability_issue_present"] if not checks["blocker_count_zero_pass"] else []),
        *(["evidence_ref_missing"] if not checks["evidence_ref_present_pass"] else []),
        *(["evidence_ref_unresolvable"] if checks["evidence_ref_present_pass"] and not checks["evidence_ref_resolvable_pass"] else []),
        *(["evidence_ref_self_reference"] if evidence_ref_self_reference else []),
        *(["evidence_ref_template_reference"] if evidence_ref_template_reference else []),
        *(["approval_decision_not_accepted"] if not checks["approval_decision_pass"] else []),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": input_checksums(
            [observation_path, *( [Path(resolved_evidence_path)] if resolved_evidence_path else [] )],
            repo_root=repo_root,
        ),
        "reused_evidence": False,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_UX_NEW_USER_OBSERVATION_REQUIRED",
        "observation_path": str(observation_path),
        "checks": checks,
        "blockers": blockers,
        "summary_line": (
            f"UX new-user observation: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"completion={completion_minutes if completion_minutes is not None else 'missing'}/{max_completion_minutes} min | "
            f"elapsed={elapsed_minutes if elapsed_minutes is not None else 'missing'}/{max_completion_minutes} min | "
            f"workflow={workflow_step_pass_count}/{len(required_step_ids)} | "
            f"blockers={len(blockers)}"
        ),
        "summary": {
            "completion_minutes": completion_minutes,
            "declared_completion_minutes": completion_minutes,
            "elapsed_minutes": elapsed_minutes,
            "max_completion_minutes": max_completion_minutes,
            "timestamp_tolerance_minutes": timestamp_tolerance_minutes,
            "started_at_utc": started_at.isoformat() if started_at is not None else None,
            "completed_at_utc": completed_at.isoformat() if completed_at is not None else None,
            "participant_role": participant_role,
            "new_to_product": new_to_product,
            "blocker_count": blocker_count,
            "reported_blocker_count": blocker_count,
            "release_blocker_count": len(blockers),
            "approval_decision": decision,
            "evidence_ref": evidence_ref if isinstance(evidence_ref, str) else "",
            "evidence_ref_kind": str(evidence_ref_resolution["kind"]),
            "evidence_ref_resolved_path": resolved_evidence_path,
            "missing_fields": missing_fields,
            "placeholder_fields": placeholder_fields,
            "template_only": template_only,
            "template_note_present": template_note_present,
            "required_workflow_steps": list(REQUIRED_WORKFLOW_STEPS),
            "workflow_steps": workflow_rows,
            "workflow_step_count": len(workflow_rows),
            "required_workflow_step_count": len(required_step_ids),
            "workflow_step_pass_count": workflow_step_pass_count,
            "missing_workflow_steps": missing_workflow_steps,
            "not_passed_workflow_steps": not_passed_workflow_steps,
            "placeholder_workflow_steps": placeholder_workflow_steps,
            "owner_action": (
                "Attach a human new-user observation record for the sample project workflow, including "
                "participant status, observer, all five workflow steps (Import, Model Health, Analysis Setup, "
                "Run & Monitor, Compare & Report), timezone-aware start/end timestamps, wall-clock completion "
                "minutes, blocker count, evidence reference, and accepted release decision."
            ),
        },
        "required_fields": list(REQUIRED_FIELDS),
        "required_workflow_steps": list(REQUIRED_WORKFLOW_STEPS),
        "validation_commands": [
            f"python3 scripts/build_ux_new_user_observation_report.py --out {DEFAULT_OUT}",
            "python3 scripts/build_ux_new_user_observation_intake_packet.py "
            "--out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json",
            "python3 scripts/report_pm_release_gate.py "
            "--out implementation/phase1/release_evidence/productization/pm_release_gate_report.json "
            "--out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        ],
        "claim_boundary": (
            "This report validates a human new-user observation record. Automated browser rehearsal evidence "
            "does not satisfy the PM UX release-area gate by itself."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# UX New-User Observation Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `observation_path`: `{payload['observation_path']}`",
        "",
        "## Timing Checks",
        "",
        f"- `declared_completion_minutes`: `{payload['summary']['declared_completion_minutes']}`",
        f"- `elapsed_minutes`: `{payload['summary']['elapsed_minutes']}`",
        f"- `max_completion_minutes`: `{payload['summary']['max_completion_minutes']}`",
        f"- `timestamp_tolerance_minutes`: `{payload['summary']['timestamp_tolerance_minutes']}`",
        f"- `completion_minutes_elapsed_match_pass`: "
        f"`{payload['checks']['completion_minutes_elapsed_match_pass']}`",
        "",
        "## Workflow Checks",
        "",
        f"- `workflow_step_pass_count`: `{payload['summary']['workflow_step_pass_count']}`",
        f"- `required_workflow_step_count`: `{payload['summary']['required_workflow_step_count']}`",
        f"- `all_required_workflow_steps_observed`: "
        f"`{payload['checks']['all_required_workflow_steps_observed']}`",
        f"- `all_required_workflow_steps_passed`: "
        f"`{payload['checks']['all_required_workflow_steps_passed']}`",
        f"- `missing_workflow_steps`: `{payload['summary']['missing_workflow_steps']}`",
        f"- `not_passed_workflow_steps`: `{payload['summary']['not_passed_workflow_steps']}`",
        "",
        "## Required Fields",
        "",
    ]
    for field in payload["required_fields"]:
        lines.append(f"- `{field}`")
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, default=DEFAULT_OBSERVATION)
    parser.add_argument("--max-completion-minutes", type=float, default=30.0)
    parser.add_argument("--timestamp-tolerance-minutes", type=float, default=DEFAULT_TIMESTAMP_TOLERANCE_MINUTES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        observation_path=args.observation,
        max_completion_minutes=float(args.max_completion_minutes),
        timestamp_tolerance_minutes=float(args.timestamp_tolerance_minutes),
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
