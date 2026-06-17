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
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "paid_pilot_candidate": True,
            "limited_commercial_ready": True,
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
    assert row["blocker_id"] == "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    assert row["release_area_requirement_id"] == "release_area.basic_ci"
    assert row["owner"] == "release_ci_owner"
    assert row["evidence_artifact_paths"]["ci_streak_manifest"] == "ci_streak_manifest.json"
    assert any("pr_ci_30_run_streak_pass" in item for item in row["verdict_change_conditions"])
    assert any("release_area.basic_ci" in item for item in row["verdict_change_conditions"])
    assert any("Current false audit check" in item for item in row["verdict_change_conditions"])
    assert "does not convert missing tracked CI streak" in payload["claim_boundary"]

    markdown = build_handoff_module._markdown(payload)
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
