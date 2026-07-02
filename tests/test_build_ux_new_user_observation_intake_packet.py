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
        "participant_ref": "OWNER_INPUT_REQUIRED: anonymized participant or session reference",
        "participant_role": "OWNER_INPUT_REQUIRED: new_user | first_time_user | pilot_user",
        "new_to_product": "OWNER_INPUT_REQUIRED: true",
        "sample_project_id": "OWNER_INPUT_REQUIRED: sample project identifier",
        "workflow_scope": "OWNER_INPUT_REQUIRED: Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report",
        "workflow_steps": [
            {"id": "import", "outcome": "OWNER_INPUT_REQUIRED: pass"},
            {"id": "model_health", "outcome": "OWNER_INPUT_REQUIRED: pass"},
            {"id": "analysis_setup", "outcome": "OWNER_INPUT_REQUIRED: pass"},
            {"id": "run_monitor", "outcome": "OWNER_INPUT_REQUIRED: pass"},
            {"id": "compare_report", "outcome": "OWNER_INPUT_REQUIRED: pass"},
        ],
        "observer": "OWNER_INPUT_REQUIRED: UX research owner",
        "started_at_utc": "OWNER_INPUT_REQUIRED: timezone-aware ISO timestamp, e.g. 2026-06-16T09:00:00Z",
        "completed_at_utc": "OWNER_INPUT_REQUIRED: timezone-aware ISO timestamp, e.g. 2026-06-16T09:24:00Z",
        "completion_minutes": (
            "OWNER_INPUT_REQUIRED: wall-clock minutes matching completed_at_utc - started_at_utc, numeric <= 30.0"
        ),
        "blocker_count": "OWNER_INPUT_REQUIRED: 0",
        "evidence_ref": "OWNER_INPUT_REQUIRED: evidence reference",
        "approval_decision": "OWNER_INPUT_REQUIRED: accepted | approved | pass | signed | approved_for_release",
        "template_only": True,
    }


def _observation() -> dict[str, object]:
    return {
        "contract_pass": True,
        "participant_ref": "ux-participant-001",
        "participant_role": "new_user",
        "new_to_product": True,
        "sample_project_id": "sample_tower",
        "workflow_scope": "Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report",
        "workflow_steps": [
            {"id": "import", "outcome": "passed"},
            {"id": "model_health", "outcome": "passed"},
            {"id": "analysis_setup", "outcome": "passed"},
            {"id": "run_monitor", "outcome": "passed"},
            {"id": "compare_report", "outcome": "passed"},
        ],
        "observer": "ux-research-owner",
        "started_at_utc": "2026-06-16T09:00:00+00:00",
        "completed_at_utc": "2026-06-16T09:24:00+00:00",
        "completion_minutes": 24.0,
        "blocker_count": 0,
        "evidence_ref": "ticket:UX-OBS-001",
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
                "started_at_utc_valid": False,
                "completed_at_utc_valid": False,
                "timestamp_order_pass": False,
                "elapsed_30min_pass": False,
                "completion_minutes_elapsed_match_pass": False,
                "all_required_workflow_steps_observed": False,
                "all_required_workflow_steps_passed": False,
                "workflow_step_placeholders_absent": False,
                "evidence_ref_resolvable_pass": False,
                "evidence_ref_not_self_reference_pass": False,
                "evidence_ref_not_template_reference_pass": False,
                "evidence_ref_not_template_artifact_pass": False,
                "evidence_ref_not_generated_gate_artifact_pass": False,
                "blocker_count_zero_pass": False,
                "approval_decision_pass": False,
            },
            "summary": {
                "missing_fields": [
                    "contract_pass",
                    "participant_ref",
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
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_UX_NEW_USER_OBSERVATION_OWNER_INPUT_REQUIRED"
    assert payload["release_area"] == "ux"
    assert payload["release_area_blocker_ids"] == [
        "pm_release::ux::human_new_user_observation_missing_or_failed",
        "pm_release::ux::human_new_user_30min_sample_evidence_missing",
    ]
    assert payload["developer_preview_final_gate_id"] == "new_user_core_workflow_observation_passed"
    assert payload["developer_preview_blocker_ids"] == [
        "developer_preview_rc::new_user_core_workflow_observation_passed"
    ]
    assert "human_ux::observation_file_missing" in payload["product_readiness_blocker_ids"]
    assert "ux_new_user_observation::observation_file_missing" in payload["blocker_ids"]
    assert (
        "implementation/phase1/release_evidence/productization/phase6_ux_observation_status.json"
        in payload["evidence_intake_artifacts"]
    )
    assert "automated browser smoke" in payload["human_observation_evidence_policy"]["rejected_substitutes"][0]
    assert payload["summary"]["field_pass_count"] == 0
    assert payload["summary"]["observation_blocker_count"] == 2
    assert payload["gate_unblock_plan_count"] == 2
    assert payload["gate_unblock_plan"][0]["slot_id"] == "attach_observation_record"
    assert "participant_role" in payload["gate_unblock_plan"][0]["failing_fields"]
    assert payload["next_actions"] == [
        "fill_ux_new_user_observation_record_from_template",
        "run_30_minute_human_new_user_core_workflow_observation",
        "rerun_ux_observation_validation_chain",
    ]
    assert rows["participant_ref"]["template_value"].startswith("OWNER_INPUT_REQUIRED")
    assert rows["participant_role"]["template_value"].startswith("OWNER_INPUT_REQUIRED")
    assert rows["completion_minutes"]["missing"] is True
    assert rows["completion_minutes"]["report_check_pass"] is False
    assert rows["elapsed_minutes"]["report_check"] == "elapsed_30min_pass"
    assert rows["completion_minutes_elapsed_match"]["report_check_pass"] is False
    assert rows["workflow_steps"]["report_check"] == "all_required_workflow_steps_passed"
    assert rows["workflow_step_coverage"]["report_check"] == "all_required_workflow_steps_observed"
    assert rows["workflow_step_placeholders"]["report_check_pass"] is False
    assert rows["evidence_ref_resolvable"]["report_check"] == "evidence_ref_resolvable_pass"
    assert rows["evidence_ref_resolvable"]["report_check_pass"] is False
    assert rows["evidence_ref_not_template_artifact"]["report_check"] == "evidence_ref_not_template_artifact_pass"
    assert rows["evidence_ref_not_generated_gate_artifact"]["report_check"] == (
        "evidence_ref_not_generated_gate_artifact_pass"
    )
    assert rows["evidence_ref_not_generated_gate_artifact"]["report_check_pass"] is False
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
                "started_at_utc_valid": True,
                "completed_at_utc_valid": True,
                "timestamp_order_pass": True,
                "elapsed_30min_pass": True,
                "completion_minutes_elapsed_match_pass": True,
                "all_required_workflow_steps_observed": True,
                "all_required_workflow_steps_passed": True,
                "workflow_step_placeholders_absent": True,
                "evidence_ref_resolvable_pass": True,
                "evidence_ref_not_self_reference_pass": True,
                "evidence_ref_not_template_reference_pass": True,
                "evidence_ref_not_template_artifact_pass": True,
                "evidence_ref_not_generated_gate_artifact_pass": True,
                "blocker_count_zero_pass": True,
                "approval_decision_pass": True,
            },
            "summary": {
                "missing_fields": [],
                "placeholder_fields": [],
                "completion_minutes": 24.0,
                "declared_completion_minutes": 24.0,
                "elapsed_minutes": 24.0,
                "started_at_utc": "2026-06-16T09:00:00+00:00",
                "completed_at_utc": "2026-06-16T09:24:00+00:00",
                "timestamp_tolerance_minutes": 1.0,
                "required_workflow_steps": [
                    {"id": "import", "label": "Import"},
                    {"id": "model_health", "label": "Model Health"},
                    {"id": "analysis_setup", "label": "Analysis Setup"},
                    {"id": "run_monitor", "label": "Run & Monitor"},
                    {"id": "compare_report", "label": "Compare & Report"},
                ],
                "workflow_step_count": 5,
                "required_workflow_step_count": 5,
                "workflow_step_pass_count": 5,
                "missing_workflow_steps": [],
                "not_passed_workflow_steps": [],
                "placeholder_workflow_steps": [],
                "evidence_ref": "ticket:UX-OBS-001",
                "evidence_ref_kind": "external_reference",
                "evidence_ref_resolved_path": "",
            },
        },
    )

    payload = build_ux_new_user_observation_intake_packet.build_packet(
        observation_path=observation,
        template_path=template,
        observation_report_path=report,
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "ready"
    assert payload["reason_code"] == "PASS"
    assert payload["release_area_blocker_ids"] == []
    assert payload["developer_preview_blocker_ids"] == []
    assert payload["product_readiness_blocker_ids"] == []
    assert payload["blocker_ids"] == []
    assert payload["summary"]["field_pass_count"] == 24
    assert payload["summary"]["field_count"] == 24
    assert payload["gate_unblock_plan"] == []
    assert payload["gate_unblock_plan_count"] == 0
    assert payload["next_actions"] == []
    assert payload["summary"]["elapsed_minutes"] == 24.0
    assert payload["summary"]["evidence_ref_kind"] == "external_reference"
    assert payload["summary"]["workflow_step_pass_count"] == 5
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
    assert "Gate Unblock Plan" in markdown
    assert "Validation Commands" in markdown
    assert "Blocker IDs" in markdown
    assert "Human Observation Evidence Policy" in markdown
    assert "phase6_ux_observation_status.json" in markdown


def test_ux_observation_intake_reuses_report_gate_unblock_plan(tmp_path: Path) -> None:
    template = _write_json(tmp_path / "ux-template.json", _template())
    report = _write_json(
        tmp_path / "ux-report.json",
        {
            "contract_pass": False,
            "blockers": ["observation_file_missing"],
            "checks": {},
            "summary": {},
            "gate_unblock_plan": [
                {
                    "slot_id": "report_defined_slot",
                    "minimum_evidence": ["report-owned unblock details"],
                }
            ],
        },
    )

    payload = build_ux_new_user_observation_intake_packet.build_packet(
        observation_path=tmp_path / "missing-observation.json",
        template_path=template,
        observation_report_path=report,
    )

    assert payload["gate_unblock_plan"] == [
        {
            "slot_id": "report_defined_slot",
            "minimum_evidence": ["report-owned unblock details"],
        }
    ]
    assert payload["gate_unblock_plan_count"] == 1
