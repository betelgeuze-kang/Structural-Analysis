from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_owner_evidence_request_packet.py"
SPEC = importlib.util.spec_from_file_location("build_pm_owner_evidence_request_packet", SCRIPT_PATH)
assert SPEC is not None
build_packet_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_packet_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _row(blocker_id: str, *, owner: str = "release_ci_owner", owner_action: str = "Collect evidence.") -> dict:
    return {
        "blocker_id": blocker_id,
        "owner": owner,
        "scope": "release_area",
        "title": "Basic CI",
        "owner_action": owner_action,
        "next_action": owner_action,
        "acceptance_criteria": ["`ci_streak_intake_packet.json.contract_pass == true`"],
        "reproduction_commands": ["python3 scripts/build_ci_streak_intake_packet.py"],
        "verification_commands": ["python3 scripts/build_ci_streak_intake_packet.py --fail-blocked"],
        "handoff_ready": bool(owner_action),
        "handoff_state": "external_owner_input_ready",
        "handoff": {"expected_intake_artifact": "ci_streak_intake_packet"},
        "evidence_status": {"state": "missing_tracked_ci_streak_evidence"},
        "evidence_artifacts": {
            "ci_streak_intake_packet": "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"
        },
        "external_input_required": True,
        "owner_input_required": True,
        "claim_boundary": "Tracked CI evidence is required.",
    }


def test_build_packet_groups_ci_blockers_by_owner_and_dedupes_commands(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "summary": {
                "open_blocker_count": 2,
                "release_area_gate_ready": False,
                "full_release_gate_ready": False,
                "limited_commercial_ready": True,
                "paid_pilot_candidate": True,
            },
            "rows": [
                _row("basic_ci::pr_ci_30_consecutive_pass_evidence_missing"),
                _row("basic_ci::nightly_ci_30_consecutive_pass_evidence_missing"),
            ],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)
    packet = payload["owner_packets"][0]

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["owner_packet_count"] == 1
    assert payload["summary"]["open_blocker_count"] == 2
    assert packet["owner"] == "release_ci_owner"
    assert packet["blocker_count"] == 2
    assert packet["blocker_ids"] == [
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
    ]
    assert packet["reproduction_commands"] == ["python3 scripts/build_ci_streak_intake_packet.py"]
    assert packet["expected_intake_paths"] == [
        "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"
    ]
    assert "does not create or replace tracked CI streaks" in payload["claim_boundary"]


def test_build_packet_emits_closed_release_owner_packet_when_no_blockers(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: READY",
            "summary": {"open_blocker_count": 0},
            "rows": [],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)

    assert payload["contract_pass"] is True
    assert payload["summary"]["open_blocker_count"] == 0
    assert payload["owner_packets"][0]["owner"] == "release_owner"
    assert payload["owner_packets"][0]["blocker_ids"] == []


def test_build_packet_blocks_when_owner_request_is_incomplete(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "summary": {"open_blocker_count": 1},
            "rows": [_row("security::license_status_not_configured", owner="product_legal_owner", owner_action="")],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_OWNER_EVIDENCE_REQUEST_INCOMPLETE"
    assert payload["incomplete_blockers"] == ["security::license_status_not_configured"]


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate",
            "summary": {"open_blocker_count": 0},
            "rows": [],
        },
    )
    out = tmp_path / "owner-packet.json"
    out_md = tmp_path / "owner-packet.md"

    exit_code = build_packet_module.main(
        [
            "--action-register",
            str(action_register),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Owner Evidence Request Packet" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["owner_packet_count"] == 1
    assert "No open owner evidence requests" in out_md.read_text(encoding="utf-8")
