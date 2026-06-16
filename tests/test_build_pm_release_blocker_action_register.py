from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_blocker_action_register.py"
SPEC = importlib.util.spec_from_file_location("build_pm_release_blocker_action_register", SCRIPT_PATH)
assert SPEC is not None
build_register_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_register_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pm_report(path: Path, *, blockers: list[str] | None = None) -> Path:
    if blockers is None:
        blockers = [
            "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
            "security::license_status_not_configured",
        ]
    return _write_json(
        path,
        {
            "schema_version": "pm-release-gate.v1",
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "paid_pilot_candidate": True,
            "limited_commercial_ready": True,
            "release_area_gate_ready": False,
            "full_release_gate_ready": False,
            "blockers": [],
            "release_area_blockers": blockers,
            "full_release_blockers": blockers,
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "basic_ci",
                    "title": "Basic CI",
                    "status": "blocked",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                    "claim_boundary": "CI claim boundary",
                    "summary": {
                        "required_consecutive_pass_count": 30,
                        "pr_pass_streak_count": 2,
                        "pr_missing_consecutive_pass_count": 28,
                        "pr_owner_action": "Collect 28 additional consecutive successful PR CI run(s).",
                        "pr_claim_boundary": "Tracked PR CI evidence is required.",
                    },
                    "artifacts": {
                        "ci_streak_intake_packet": "ci_streak_intake_packet.json",
                        "ci_streak_manifest": "ci_consecutive_pass_manifest.json",
                    },
                },
                {
                    "area": "security",
                    "title": "Security",
                    "status": "blocked",
                    "blockers": ["license_status_not_configured"],
                    "summary": {
                        "license_status": "not_configured",
                        "license_status_owner_action": "Populate license status from approved legal evidence.",
                        "license_status_template_path": "docs/templates/license_status.template.json",
                    },
                    "artifacts": {
                        "license_status_closure": "license_status_closure_report.json",
                    },
                },
            ],
        },
    )


def test_build_register_surfaces_owner_actions_and_acceptance(tmp_path: Path) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json")

    payload = build_register_module.build_register(pm_report=report)
    rows = {row["blocker_id"]: row for row in payload["rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_RELEASE_BLOCKERS_OPEN"
    assert payload["summary"]["open_blocker_count"] == 2
    assert payload["summary"]["owner_input_required_count"] == 2
    assert payload["summary"]["external_input_required_count"] == 2

    ci_row = rows["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"]
    assert ci_row["owner"] == "release_ci_owner"
    assert ci_row["next_action"] == ci_row["owner_action"]
    assert ci_row["external_input_required"] is True
    assert ci_row["resolution_type"] == "external_tracked_ci_evidence_required"
    assert ci_row["owner_action"] == "Collect 28 additional consecutive successful PR CI run(s)."
    assert ci_row["claim_boundary"] == "Tracked PR CI evidence is required."
    assert any("build_ci_consecutive_pass_manifest.py" in command for command in ci_row["reproduction_commands"])
    assert any("build_ci_streak_intake_packet.py" in command for command in ci_row["reproduction_commands"])
    assert any("build_ci_streak_intake_packet.py" in command for command in ci_row["verification_commands"])
    assert any("pr_pass_streak_count >= 30" in item for item in ci_row["acceptance_criteria"])
    assert any("ci_streak_intake_packet.json.contract_pass" in item for item in ci_row["acceptance_criteria"])
    assert "ci_streak_intake_packet" in ci_row["evidence_artifacts"]
    assert ci_row["evidence_status"]["state"] == "missing_tracked_ci_streak_evidence"
    assert ci_row["evidence_status"]["lane"] == "pr"
    assert ci_row["evidence_status"]["missing_consecutive_pass_count"] == 28
    assert ci_row["evidence_snapshot"]["pr_missing_consecutive_pass_count"] == 28

    security_row = rows["security::license_status_not_configured"]
    assert security_row["owner"] == "product_legal_owner"
    assert security_row["external_input_required"] is True
    assert security_row["resolution_type"] == "product_legal_decision_required"
    assert security_row["owner_action"] == "Populate license status from approved legal evidence."
    assert any("build_license_status_intake_packet.py" in command for command in security_row["reproduction_commands"])
    assert any("build_license_status_closure_report.py" in command for command in security_row["reproduction_commands"])
    assert any("build_license_status_closure_report.py" in command for command in security_row["verification_commands"])
    assert any("license_status_closure_report.json.contract_pass" in item for item in security_row["acceptance_criteria"])
    assert "license_status_intake_packet" in security_row["evidence_artifacts"]
    assert security_row["evidence_status"]["state"] == "not_configured"


def test_build_register_passes_when_pm_report_has_no_blockers(tmp_path: Path) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json", blockers=[])
    payload = build_register_module.build_register(pm_report=report)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["rows"] == []
    assert payload["next_actions"] == []


def test_build_register_guides_frontend_dependency_audit_blocker(tmp_path: Path) -> None:
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": ["security::frontend_dependency_audit_missing_or_failed"],
            "release_area_blockers": ["security::frontend_dependency_audit_missing_or_failed"],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "security",
                    "title": "Security",
                    "status": "blocked",
                    "blockers": ["frontend_dependency_audit_missing_or_failed"],
                    "summary": {
                        "frontend_dependency_vulnerability_total": 1,
                        "frontend_dependency_high_or_critical_vulnerability_count": 1,
                    },
                    "artifacts": {
                        "frontend_dependency_audit": "frontend_dependency_audit_report.json",
                    },
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    row = payload["rows"][0]

    assert row["blocker_id"] == "security::frontend_dependency_audit_missing_or_failed"
    assert row["owner"] == "frontend_security_owner"
    assert row["external_input_required"] is False
    assert row["resolution_type"] == "local_dependency_remediation_required"
    assert "npm audit --audit-level high" in row["reproduction_commands"]
    assert any("build_frontend_dependency_audit_report.py" in command for command in row["reproduction_commands"])
    assert any("build_frontend_dependency_audit_report.py" in command for command in row["verification_commands"])
    assert any("high_or_critical_vulnerability_count == 0" in item for item in row["acceptance_criteria"])
    assert "frontend_dependency_audit_report" in row["evidence_artifacts"]


def test_build_register_guides_human_new_user_ux_blocker(tmp_path: Path) -> None:
    report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_blockers": ["ux::human_new_user_observation_missing_or_failed"],
            "release_area_blockers": ["ux::human_new_user_observation_missing_or_failed"],
            "blockers": [],
            "milestones": [],
            "release_area_matrix": [
                {
                    "area": "ux",
                    "title": "UX",
                    "status": "blocked",
                    "blockers": ["human_new_user_observation_missing_or_failed"],
                    "claim_boundary": "Human new-user observation is required for PM UX pass.",
                    "checks": {
                        "human_new_user_observation_pass": False,
                        "human_new_user_sample_30min_pass": False,
                    },
                    "summary": {
                        "automated_sample_completion_minutes": 0.27,
                        "human_sample_completion_minutes": None,
                        "human_observation_reason_code": "ERR_UX_NEW_USER_OBSERVATION_REQUIRED",
                        "human_observation_owner_action": "Schedule and attach one observed new-user sample run.",
                    },
                    "artifacts": {
                        "ux_new_user_observation": "ux_new_user_observation_report.json",
                    },
                }
            ],
        },
    )

    payload = build_register_module.build_register(pm_report=report)
    row = payload["rows"][0]

    assert row["blocker_id"] == "ux::human_new_user_observation_missing_or_failed"
    assert row["owner"] == "ux_research_owner"
    assert row["owner_input_required"] is True
    assert row["external_input_required"] is True
    assert row["resolution_type"] == "external_human_new_user_observation_required"
    assert row["owner_action"] == "Schedule and attach one observed new-user sample run."
    assert any("build_ux_new_user_observation_report.py" in command for command in row["reproduction_commands"])
    assert any("build_ux_new_user_observation_intake_packet.py" in command for command in row["reproduction_commands"])
    assert any("build_ux_new_user_observation_report.py" in command for command in row["verification_commands"])
    assert any("build_ux_new_user_observation_intake_packet.py" in command for command in row["verification_commands"])
    assert any("ux_new_user_observation_report.json.contract_pass" in item for item in row["acceptance_criteria"])
    assert "ux_new_user_observation_report" in row["evidence_artifacts"]
    assert "ux_new_user_observation_intake_packet" in row["evidence_artifacts"]
    assert row["evidence_status"]["state"] == "missing_human_new_user_observation"
    assert row["evidence_status"]["source_policy"] == "human_new_user_observation_required"
    assert row["evidence_status"]["human_observation_reason_code"] == "ERR_UX_NEW_USER_OBSERVATION_REQUIRED"


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    report = _pm_report(tmp_path / "pm_release_gate_report.json")
    out = tmp_path / "register.json"
    out_md = tmp_path / "register.md"

    exit_code = build_register_module.main(
        [
            "--pm-report",
            str(report),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Release Blocker Action Register" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_blocker_count"] == 2
    assert "basic_ci::pr_ci_30_consecutive_pass_evidence_missing" in out_md.read_text(encoding="utf-8")
    assert "release_ci_owner" in out_md.read_text(encoding="utf-8")
