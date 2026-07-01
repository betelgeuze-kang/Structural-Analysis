from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_gate_reviewer_handoff.py"
SPEC = importlib.util.spec_from_file_location("build_pm_release_gate_reviewer_handoff", SCRIPT_PATH)
assert SPEC is not None
build_handoff_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_handoff_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_handoff_packages_open_blocker_review_actions(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED",
            "paid_pilot_candidate": True,
            "limited_commercial_milestone_ready": True,
            "limited_commercial_release_ready": False,
            "limited_commercial_ready": False,
            "release_area_gate_ready": False,
            "full_release_gate_ready": False,
        },
    )
    closure_board = _write_json(
        tmp_path / "pm_release_blocker_closure_board.json",
        {
            "rows": [
                {
                    "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                    "owner": "release_ci_owner",
                    "closure_state": "external_owner_input_ready",
                    "handoff_state": "external_owner_input_ready",
                    "evidence_state": "missing_tracked_ci_streak_evidence",
                    "next_action": "Collect additional tracked PR CI streak evidence.",
                    "claim_boundary": "Tracked PR CI evidence is required.",
                    "acceptance_criteria": ["`pr_pass_streak_count >= 30`"],
                    "primary_evidence_artifacts": {"ci_streak_manifest": "ci_streak_manifest.json"},
                    "reproduction_commands": ["python3 scripts/build_ci_streak_intake_packet.py"],
                    "verification_commands": ["python3 scripts/build_ci_streak_intake_packet.py --fail-blocked"],
                    "external_input_required": True,
                    "owner_input_required": True,
                }
            ]
        },
    )
    completion_audit = _write_json(
        tmp_path / "pm_release_gate_completion_audit.json",
        {
            "rows": [
                {
                    "requirement_id": "release_area.basic_ci",
                    "status": "blocked_external_owner_input_ready",
                    "checks": {
                        "pr_ci_30_run_streak_pass": False,
                        "nightly_ci_30_run_streak_pass": True,
                    },
                    "claim_boundary": "Basic CI claim boundary.",
                },
                {
                    "requirement_id": "release_tier.paid_pilot_scope_guard_pass",
                    "group": "release_tier",
                    "title": "Paid Pilot Scope Guard",
                    "status": "pass",
                    "pass": True,
                    "blockers": [],
                    "next_action": "",
                    "claim_boundary": "Paid pilot is constrained customer PoC only.",
                    "evidence_artifacts": {
                        "paid_pilot_scope_guard_report": "paid_pilot_scope_guard_report.json"
                    },
                },
                {
                    "requirement_id": "release_tier.ga_enterprise_evidence_gate_pass",
                    "group": "release_tier",
                    "title": "GA / Enterprise Evidence Gate",
                    "status": "blocked",
                    "pass": False,
                    "blockers": ["independent_vv_missing"],
                    "next_action": "Attach independent V&V evidence.",
                    "claim_boundary": "GA requires independent V&V.",
                    "evidence_artifacts": {
                        "ga_enterprise_readiness_report": "ga_enterprise_readiness_report.json"
                    },
                }
            ]
        },
    )

    payload = build_handoff_module.build_handoff(
        pm_report=pm_report,
        closure_board=closure_board,
        completion_audit=completion_audit,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["open_blocker_count"] == 1
    assert payload["summary"]["handoff_incomplete_count"] == 0
    assert payload["summary"]["release_tier_count"] == 2
    assert payload["summary"]["release_tier_pass_count"] == 1
    assert payload["summary"]["release_tier_blocked_count"] == 1
    assert payload["summary"]["release_tier_handoff_incomplete_count"] == 0
    assert payload["summary"]["limited_commercial_milestone_ready"] is True
    assert payload["summary"]["limited_commercial_release_ready"] is False
    assert payload["summary"]["limited_commercial_ready"] is False
    assert payload["incomplete_release_tiers"] == []
    assert payload["release_tier_rows"][0]["requirement_id"] == "release_tier.paid_pilot_scope_guard_pass"
    assert payload["release_tier_rows"][1]["status"] == "blocked"
    assert payload["release_tier_rows"][1]["next_action"] == "Attach independent V&V evidence."
    assert (
        payload["release_tier_rows"][1]["evidence_artifact_paths"]["ga_enterprise_readiness_report"]
        == "ga_enterprise_readiness_report.json"
    )
    assert row["blocker_id"] == "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    assert row["release_area_requirement_id"] == "release_area.basic_ci"
    assert row["owner"] == "release_ci_owner"
    assert row["evidence_artifact_paths"]["ci_streak_manifest"] == "ci_streak_manifest.json"
    assert any("pr_ci_30_run_streak_pass" in item for item in row["verdict_change_conditions"])
    assert any("release_area.basic_ci" in item for item in row["verdict_change_conditions"])
    assert any("Current false audit check" in item for item in row["verdict_change_conditions"])
    assert "does not convert missing tracked CI streak" in payload["claim_boundary"]

    markdown = build_handoff_module._markdown(payload)
    assert "## Release Tier Boundaries" in markdown
    assert "`release_tier.ga_enterprise_evidence_gate_pass` GA / Enterprise Evidence Gate" in markdown
    assert "`independent_vv_missing`" in markdown
    assert "Attach independent V&V evidence." in markdown
    assert "GA requires independent V&V." in markdown
    assert "## Blocker Details" in markdown
    assert "### `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`" in markdown
    assert "`ci_streak_manifest`: `ci_streak_manifest.json`" in markdown
    assert "`python3 scripts/build_ci_streak_intake_packet.py`" in markdown
    assert "`python3 scripts/build_ci_streak_intake_packet.py --fail-blocked`" in markdown
    assert "Verdict change conditions:" in markdown


def test_build_handoff_blocks_when_required_review_fields_are_missing(tmp_path: Path) -> None:
    pm_report = _write_json(tmp_path / "pm_release_gate_report.json", {"summary_line": "PM release gate"})
    closure_board = _write_json(
        tmp_path / "pm_release_blocker_closure_board.json",
        {
            "rows": [
                {
                    "blocker_id": "security::license_status_not_configured",
                    "owner": "product_legal_owner",
                    "closure_state": "external_owner_input_ready",
                }
            ]
        },
    )
    completion_audit = _write_json(tmp_path / "pm_release_gate_completion_audit.json", {"rows": []})

    payload = build_handoff_module.build_handoff(
        pm_report=pm_report,
        closure_board=closure_board,
        completion_audit=completion_audit,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_REVIEWER_HANDOFF_INCOMPLETE"
    assert payload["incomplete_blockers"] == ["security::license_status_not_configured"]


def test_build_handoff_routes_release_tier_blocker_verdict_conditions(tmp_path: Path) -> None:
    pm_report = _write_json(tmp_path / "pm_release_gate_report.json", {"summary_line": "PM release gate"})
    closure_board = _write_json(
        tmp_path / "pm_release_blocker_closure_board.json",
        {
            "rows": [
                {
                    "blocker_id": "independent_vv_missing",
                    "owner": "independent_vv_owner",
                    "closure_state": "external_owner_input_ready",
                    "handoff_state": "external_owner_input_ready",
                    "evidence_state": "missing_external_ga_enterprise_signoff_evidence",
                    "next_action": "Attach an approved independent V&V attestation.",
                    "claim_boundary": "GA requires independent V&V evidence.",
                    "acceptance_criteria": ["approved independent V&V attestation attached"],
                    "primary_evidence_artifacts": {
                        "ga_enterprise_signoff_intake_packet": "ga_packet.json"
                    },
                    "reproduction_commands": ["python3 scripts/build_ga_enterprise_signoff_intake_packet.py"],
                    "verification_commands": [
                        "python3 scripts/build_pm_release_gate_reviewer_handoff.py"
                    ],
                    "external_input_required": True,
                    "owner_input_required": True,
                }
            ]
        },
    )
    completion_audit = _write_json(
        tmp_path / "pm_release_gate_completion_audit.json",
        {
            "rows": [
                {
                    "requirement_id": "release_tier.ga_enterprise_evidence_gate_pass",
                    "group": "release_tier",
                    "title": "GA / Enterprise Evidence Gate",
                    "status": "blocked",
                    "pass": False,
                    "blockers": ["independent_vv_missing"],
                    "next_action": "Attach independent V&V evidence.",
                    "claim_boundary": "GA requires independent V&V.",
                }
            ]
        },
    )

    payload = build_handoff_module.build_handoff(
        pm_report=pm_report,
        closure_board=closure_board,
        completion_audit=completion_audit,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is True
    assert row["release_area_requirement_id"] == ""
    assert row["verdict_requirement_id"] == "release_tier.ga_enterprise_evidence_gate_pass"
    assert row["verdict_requirement_group"] == "release_tier"
    assert any("pass is `true`" in item for item in row["verdict_change_conditions"])
    assert any("independent_vv_missing" in item for item in row["verdict_change_conditions"])
    assert not any("release_area." in item for item in row["verdict_change_conditions"])

    markdown = build_handoff_module._markdown(payload)
    assert "Verdict requirement: `release_tier.ga_enterprise_evidence_gate_pass`" in markdown
    assert "Verdict requirement group: `release_tier`" in markdown


def test_build_handoff_blocks_when_blocked_release_tier_missing_handoff_fields(tmp_path: Path) -> None:
    pm_report = _write_json(tmp_path / "pm_release_gate_report.json", {"summary_line": "PM release gate"})
    closure_board = _write_json(tmp_path / "pm_release_blocker_closure_board.json", {"rows": []})
    completion_audit = _write_json(
        tmp_path / "pm_release_gate_completion_audit.json",
        {
            "rows": [
                {
                    "requirement_id": "release_tier.limited_commercial_full_gate_ready",
                    "group": "release_tier",
                    "title": "Limited Commercial Full Gate",
                    "status": "blocked",
                    "pass": False,
                    "blockers": ["strict_ndtha_long_profile_failed"],
                    "next_action": "",
                    "claim_boundary": "Limited commercial requires strict NDTHA closure.",
                }
            ]
        },
    )

    payload = build_handoff_module.build_handoff(
        pm_report=pm_report,
        closure_board=closure_board,
        completion_audit=completion_audit,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_REVIEWER_HANDOFF_INCOMPLETE"
    assert payload["summary"]["release_tier_handoff_incomplete_count"] == 1
    assert payload["incomplete_release_tiers"] == ["release_tier.limited_commercial_full_gate_ready"]


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    pm_report = _write_json(tmp_path / "pm_release_gate_report.json", {"summary_line": "PM release gate"})
    closure_board = _write_json(tmp_path / "pm_release_blocker_closure_board.json", {"rows": []})
    completion_audit = _write_json(tmp_path / "pm_release_gate_completion_audit.json", {"rows": []})
    out = tmp_path / "handoff.json"
    out_md = tmp_path / "handoff.md"

    exit_code = build_handoff_module.main(
        [
            "--pm-report",
            str(pm_report),
            "--closure-board",
            str(closure_board),
            "--completion-audit",
            str(completion_audit),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Release Gate Reviewer Handoff" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_blocker_count"] == 0
    markdown = out_md.read_text(encoding="utf-8")
    assert "No open PM release blockers" in markdown
    assert "## Blocker Details" not in markdown
