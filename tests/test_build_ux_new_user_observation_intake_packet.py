from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ux_new_user_observation_intake_packet.py"
SPEC = importlib.util.spec_from_file_location("build_ux_new_user_observation_intake_packet", SCRIPT_PATH)
assert SPEC is not None
build_ux_new_user_observation_intake_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ux_new_user_observation_intake_packet)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _template() -> dict[str, object]:
    return {
        "contract_pass": False,
        "participant_role": "OWNER_INPUT_REQUIRED: new_user | first_time_user | pilot_user",
        "new_to_product": "OWNER_INPUT_REQUIRED: true",
        "sample_project_id": "OWNER_INPUT_REQUIRED: sample project identifier",
        "workflow_scope": "OWNER_INPUT_REQUIRED: open sample project and export reviewer report",
        "observer": "OWNER_INPUT_REQUIRED: UX research owner",
        "started_at_utc": "OWNER_INPUT_REQUIRED: 2026-06-16T09:00:00+00:00",
        "completed_at_utc": "OWNER_INPUT_REQUIRED: 2026-06-16T09:24:00+00:00",
        "completion_minutes": "OWNER_INPUT_REQUIRED: numeric minutes <= 30.0",
        "blocker_count": "OWNER_INPUT_REQUIRED: 0",
        "evidence_ref": "OWNER_INPUT_REQUIRED: evidence reference",
        "approval_decision": "OWNER_INPUT_REQUIRED: accepted | approved | pass | signed | approved_for_release",
        "template_only": True,
    }


def _observation() -> dict[str, object]:
    return {
        "contract_pass": True,
        "participant_role": "new_user",
        "new_to_product": True,
        "sample_project_id": "sample_tower",
        "workflow_scope": "open sample project and export reviewer report",
        "observer": "ux-research-owner",
        "started_at_utc": "2026-06-16T09:00:00+00:00",
        "completed_at_utc": "2026-06-16T09:24:00+00:00",
        "completion_minutes": 24.0,
        "blocker_count": 0,
        "evidence_ref": "ux-observation-001",
        "approval_decision": "accepted",
    }


def test_ux_observation_intake_packet_surfaces_missing_owner_fields(tmp_path: Path) -> None:
    template = _write_json(tmp_path / "ux-template.json", _template())
    report = _write_json(
        tmp_path / "ux-report.json",
        {
            "contract_pass": False,
            "blockers": ["observation_file_missing", "completion_minutes_missing"],
            "checks": {
                "contract_signal_pass": False,
                "participant_role_new_user_pass": False,
                "new_to_product_pass": False,
                "completion_30min_pass": False,
                "blocker_count_zero_pass": False,
                "approval_decision_pass": False,
            },
            "summary": {
                "missing_fields": [
                    "contract_pass",
                    "participant_role",
                    "new_to_product",
                    "sample_project_id",
                    "workflow_scope",
                    "observer",
                    "started_at_utc",
                    "completed_at_utc",
                    "completion_minutes",
                    "blocker_count",
                    "evidence_ref",
                    "approval_decision",
                ],
                "placeholder_fields": [],
                "owner_action": "Attach observed new-user evidence.",
            },
        },
    )

    payload = build_ux_new_user_observation_intake_packet.build_packet(
        observation_path=tmp_path / "missing-observation.json",
        template_path=template,
        observation_report_path=report,
    )
    rows = {row["field"]: row for row in payload["field_rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_UX_NEW_USER_OBSERVATION_OWNER_INPUT_REQUIRED"
    assert payload["summary"]["field_pass_count"] == 0
    assert payload["summary"]["observation_blocker_count"] == 2
    assert rows["participant_role"]["template_value"].startswith("OWNER_INPUT_REQUIRED")
    assert rows["completion_minutes"]["missing"] is True
    assert rows["completion_minutes"]["report_check_pass"] is False
    assert "observation_file_missing" in payload["current_blockers"]
    assert any("build_ux_new_user_observation_report.py" in command for command in payload["validation_commands"])


def test_ux_observation_intake_packet_passes_closed_report(tmp_path: Path) -> None:
    observation = _write_json(tmp_path / "ux-observation.json", _observation())
    template = _write_json(tmp_path / "ux-template.json", _template())
    report = _write_json(
        tmp_path / "ux-report.json",
        {
            "contract_pass": True,
            "blockers": [],
            "checks": {
                "contract_signal_pass": True,
                "participant_role_new_user_pass": True,
                "new_to_product_pass": True,
                "required_fields_present": True,
                "completion_30min_pass": True,
                "blocker_count_zero_pass": True,
                "approval_decision_pass": True,
            },
            "summary": {
                "missing_fields": [],
                "placeholder_fields": [],
                "completion_minutes": 24.0,
            },
        },
    )

    payload = build_ux_new_user_observation_intake_packet.build_packet(
        observation_path=observation,
        template_path=template,
        observation_report_path=report,
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["field_pass_count"] == 12
    assert payload["current_blockers"] == []


def test_ux_observation_intake_packet_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    template = _write_json(tmp_path / "ux-template.json", _template())
    report = _write_json(
        tmp_path / "ux-report.json",
        {"contract_pass": False, "blockers": ["observation_file_missing"], "checks": {}, "summary": {}},
    )
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = build_ux_new_user_observation_intake_packet.main(
        [
            "--observation",
            str(tmp_path / "missing-observation.json"),
            "--template",
            str(template),
            "--observation-report",
            str(report),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "UX New-User Observation Intake Packet" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["observation_blocker_count"] == 1
    markdown = out_md.read_text(encoding="utf-8")
    assert "new_user \\| first_time_user \\| pilot_user" in markdown
    assert "Validation Commands" in markdown
