from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_blocker_closure_board.py"
SPEC = importlib.util.spec_from_file_location("build_pm_release_blocker_closure_board", SCRIPT_PATH)
assert SPEC is not None
build_board_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_board_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_board_groups_open_blockers_by_closure_state(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "paid_pilot_candidate": True,
            "limited_commercial_ready": True,
            "release_area_gate_ready": False,
            "full_release_gate_ready": False,
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "pm_summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "summary": {
                "open_blocker_count": 2,
                "handoff_ready_count": 2,
                "handoff_not_ready_count": 0,
                "all_open_blockers_have_handoff": True,
                "full_release_gate_ready": False,
            },
            "rows": [
                {
                    "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                    "scope": "release_area",
                    "owner": "release_ci_owner",
                    "owner_input_required": True,
                    "external_input_required": True,
                    "resolution_type": "external_tracked_ci_evidence_required",
                    "next_action": "Collect additional PR CI streak evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                    "evidence_status": {"state": "missing_tracked_ci_streak_evidence"},
                    "evidence_artifacts": {"ci_streak_intake_packet": "ci_streak_intake_packet.json"},
                    "acceptance_criteria": ["`pr_pass_streak_count >= 30`"],
                    "reproduction_commands": ["python3 scripts/build_ci_streak_intake_packet.py"],
                    "verification_commands": ["python3 scripts/build_ci_streak_intake_packet.py --fail-blocked"],
                    "claim_boundary": "Tracked PR CI evidence is required.",
                },
                {
                    "blocker_id": "security::frontend_dependency_audit_missing_or_failed",
                    "scope": "release_area",
                    "owner": "frontend_security_owner",
                    "owner_input_required": False,
                    "external_input_required": False,
                    "resolution_type": "local_dependency_remediation_required",
                    "next_action": "Patch vulnerable frontend dependencies.",
                    "handoff_ready": True,
                    "handoff_state": "local_remediation_ready",
                    "evidence_status": {"state": "dependency_vulnerabilities_present"},
                    "evidence_artifacts": {"frontend_dependency_audit_report": "frontend_dependency_audit.json"},
                    "acceptance_criteria": ["`high_or_critical_vulnerability_count == 0`"],
                    "reproduction_commands": ["npm audit --audit-level high"],
                    "verification_commands": ["npm audit --audit-level high"],
                },
            ],
        },
    )

    payload = build_board_module.build_board(action_register=action_register, pm_report=pm_report)
    rows = {row["blocker_id"]: row for row in payload["rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_RELEASE_BLOCKERS_OPEN"
    assert payload["summary"]["open_blocker_count"] == 2
    assert payload["summary"]["register_open_blocker_count"] == 2
    assert payload["summary"]["external_owner_input_ready_count"] == 1
    assert payload["summary"]["local_remediation_ready_count"] == 1
    assert payload["summary"]["handoff_not_ready_count"] == 0
    assert payload["summary"]["all_open_blockers_have_handoff"] is True
    assert payload["summary"]["paid_pilot_candidate"] is True

    ci_row = rows["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"]
    assert ci_row["closure_state"] == "external_owner_input_ready"
    assert ci_row["evidence_state"] == "missing_tracked_ci_streak_evidence"
    assert ci_row["primary_evidence_artifacts"]["ci_streak_intake_packet"] == "ci_streak_intake_packet.json"
    assert ci_row["claim_boundary"] == "Tracked PR CI evidence is required."

    dependency_row = rows["security::frontend_dependency_audit_missing_or_failed"]
    assert dependency_row["closure_state"] == "local_remediation_ready"
    assert dependency_row["external_input_required"] is False


def test_build_board_passes_when_gate_and_register_are_closed(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {"summary_line": "PM release gate: LIMITED_READY", "full_release_gate_ready": True},
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": True,
            "summary": {"open_blocker_count": 0, "all_open_blockers_have_handoff": True},
            "rows": [],
        },
    )

    payload = build_board_module.build_board(action_register=action_register, pm_report=pm_report)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["open_blocker_count"] == 0
    assert payload["rows"] == []


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {"summary_line": "PM release gate: LIMITED_READY", "full_release_gate_ready": False},
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "summary": {"open_blocker_count": 1, "all_open_blockers_have_handoff": True},
            "rows": [
                {
                    "blocker_id": "ux::human_new_user_observation_missing_or_failed",
                    "owner": "ux_research_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Attach observed UX sample workflow evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                }
            ],
        },
    )
    out = tmp_path / "board.json"
    out_md = tmp_path / "board.md"

    exit_code = build_board_module.main(
        [
            "--action-register",
            str(action_register),
            "--pm-report",
            str(pm_report),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Release Blocker Closure Board" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_blocker_count"] == 1
    assert "ux::human_new_user_observation_missing_or_failed" in out_md.read_text(encoding="utf-8")
