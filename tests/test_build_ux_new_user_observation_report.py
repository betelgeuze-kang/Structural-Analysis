from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ux_new_user_observation_report.py"
SPEC = importlib.util.spec_from_file_location("build_ux_new_user_observation_report", SCRIPT_PATH)
assert SPEC is not None
build_ux_new_user_observation_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ux_new_user_observation_report)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _passing_observation() -> dict[str, object]:
    return {
        "contract_pass": True,
        "participant_ref": "ux-participant-001",
        "participant_role": "new_user",
        "new_to_product": True,
        "sample_project_id": "sample_tower",
        "workflow_scope": "Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report",
        "workflow_steps": [
            {"id": "import", "label": "Import", "outcome": "passed"},
            {"id": "model_health", "label": "Model Health", "outcome": "passed"},
            {"id": "analysis_setup", "label": "Analysis Setup", "outcome": "passed"},
            {"id": "run_monitor", "label": "Run & Monitor", "outcome": "passed"},
            {"id": "compare_report", "label": "Compare & Report", "outcome": "passed"},
        ],
        "observer": "ux-research-owner",
        "started_at_utc": "2026-06-16T09:00:00+00:00",
        "completed_at_utc": "2026-06-16T09:24:00+00:00",
        "completion_minutes": 24.0,
        "blocker_count": 0,
        "evidence_ref": "ticket:UX-OBS-001",
        "approval_decision": "accepted",
    }


def _legacy_template_observation() -> dict[str, object]:
    record = _passing_observation()
    record.update(
        {
            "sample_project_id": "SAMPLE-PROJECT-ID",
            "observer": "UX-RESEARCH-OWNER",
            "evidence_ref": "UX-OBSERVATION-EVIDENCE-REF",
            "template_only": True,
            "note": "Template only. Do not use as release evidence until populated.",
        }
    )
    return record


def test_ux_new_user_observation_blocks_when_missing(tmp_path: Path) -> None:
    payload = build_ux_new_user_observation_report.build_report(
        observation_path=tmp_path / "missing.json",
    )

    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_UX_NEW_USER_OBSERVATION_REQUIRED"
    assert payload["template_path"] == "docs/templates/ux_new_user_observation.template.json"
    assert payload["gate_unblock_plan_count"] == 5
    assert payload["next_actions"] == [
        "fill_ux_new_user_observation_record_from_template",
        "run_30_minute_human_new_user_core_workflow_observation",
        "attach_non_template_observation_evidence_reference",
        "rerun_ux_observation_report_and_release_gates",
    ]
    assert payload["gate_unblock_plan"][0]["slot_id"] == "attach_observation_record"
    assert payload["gate_unblock_plan"][1]["slot_id"] == "observe_required_workflow_steps"
    assert "observation_file_missing" in payload["blockers"]
    assert "completion_minutes" in payload["summary"]["missing_fields"]
    assert "workflow_steps" in payload["summary"]["missing_fields"]
    assert "workflow_steps_missing" in payload["blockers"]
    assert "required_workflow_steps_missing" in payload["blockers"]
    assert "required_workflow_step_not_passed" in payload["blockers"]
    assert "completion_gt_30min" not in payload["blockers"]


def test_ux_new_user_observation_passes_with_human_record(tmp_path: Path) -> None:
    observation = _write_json(tmp_path / "ux_observation.json", _passing_observation())

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is True
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "ready"
    assert payload["reason_code"] == "PASS"
    assert payload["gate_unblock_plan"] == []
    assert payload["gate_unblock_plan_count"] == 0
    assert payload["next_actions"] == []
    assert payload["checks"]["completion_30min_pass"] is True
    assert payload["checks"]["elapsed_30min_pass"] is True
    assert payload["checks"]["completion_minutes_elapsed_match_pass"] is True
    assert payload["summary"]["completion_minutes"] == 24.0
    assert payload["summary"]["elapsed_minutes"] == 24.0
    assert payload["summary"]["participant_ref"] == "ux-participant-001"
    assert payload["summary"]["timestamp_tolerance_minutes"] == 1.0
    assert payload["checks"]["all_required_workflow_steps_observed"] is True
    assert payload["checks"]["all_required_workflow_steps_passed"] is True
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_generated_gate_artifact_pass"] is True
    assert payload["summary"]["evidence_ref_kind"] == "external_reference"
    assert payload["summary"]["workflow_step_pass_count"] == 5
    assert payload["summary"]["missing_workflow_steps"] == []


def test_ux_new_user_observation_accepts_z_suffix_timestamps(tmp_path: Path) -> None:
    record = _passing_observation()
    record["started_at_utc"] = "2026-06-16T09:00:00Z"
    record["completed_at_utc"] = "2026-06-16T09:24:00Z"
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is True
    assert payload["summary"]["elapsed_minutes"] == 24.0
    assert payload["summary"]["started_at_utc"] == "2026-06-16T09:00:00+00:00"


def test_ux_new_user_observation_accepts_offset_timestamps(tmp_path: Path) -> None:
    record = _passing_observation()
    record["started_at_utc"] = "2026-06-16T18:00:00+09:00"
    record["completed_at_utc"] = "2026-06-16T18:24:00+09:00"
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is True
    assert payload["summary"]["elapsed_minutes"] == 24.0
    assert payload["summary"]["started_at_utc"] == "2026-06-16T09:00:00+00:00"


def test_ux_new_user_observation_rejects_naive_timestamps(tmp_path: Path) -> None:
    record = _passing_observation()
    record["started_at_utc"] = "2026-06-16T09:00:00"
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "started_at_utc_invalid" in payload["blockers"]
    assert "elapsed_minutes_missing" in payload["blockers"]
    assert payload["checks"]["started_at_utc_valid"] is False


def test_ux_new_user_observation_requires_participant_ref(tmp_path: Path) -> None:
    record = _passing_observation()
    record.pop("participant_ref")
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "required_fields_missing" in payload["blockers"]
    assert "participant_ref" in payload["summary"]["missing_fields"]


def test_ux_new_user_observation_rejects_reversed_timestamps(tmp_path: Path) -> None:
    record = _passing_observation()
    record["completed_at_utc"] = "2026-06-16T08:59:00+00:00"
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "completion_timestamp_order_invalid" in payload["blockers"]
    assert "elapsed_minutes_missing" in payload["blockers"]
    assert payload["checks"]["timestamp_order_pass"] is False


def test_ux_new_user_observation_rejects_elapsed_over_30_with_declared_pass(tmp_path: Path) -> None:
    record = _passing_observation()
    record["completed_at_utc"] = "2026-06-16T09:31:00+00:00"
    record["completion_minutes"] = 29.0
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "completion_gt_30min" not in payload["blockers"]
    assert "elapsed_gt_30min" in payload["blockers"]
    assert "completion_minutes_elapsed_mismatch" in payload["blockers"]


def test_ux_new_user_observation_rejects_declared_elapsed_mismatch(tmp_path: Path) -> None:
    record = _passing_observation()
    record["completion_minutes"] = 20.0
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "completion_minutes_elapsed_mismatch" in payload["blockers"]
    assert payload["checks"]["completion_minutes_elapsed_match_pass"] is False


def test_ux_new_user_observation_rejects_declared_over_30_with_elapsed_pass(tmp_path: Path) -> None:
    record = _passing_observation()
    record["completion_minutes"] = 31.0
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "completion_gt_30min" in payload["blockers"]
    assert "elapsed_gt_30min" not in payload["blockers"]
    assert "completion_minutes_elapsed_mismatch" in payload["blockers"]


def test_ux_new_user_observation_rejects_template_copy(tmp_path: Path) -> None:
    template = Path("docs/templates/ux_new_user_observation.template.json")
    observation = _write_json(tmp_path / "ux_observation.json", json.loads(template.read_text(encoding="utf-8")))

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "contract_signal_not_pass" in payload["blockers"]
    assert "placeholder_values_present" in payload["blockers"]
    assert "template_only_observation_source" in payload["blockers"]
    assert "template_note_observation_source" in payload["blockers"]
    assert payload["checks"]["template_only_absent"] is False
    assert payload["checks"]["template_note_absent"] is False
    assert "sample_project_id" in payload["summary"]["placeholder_fields"]
    assert "workflow_step_placeholders_present" in payload["blockers"]


def test_ux_new_user_observation_rejects_missing_workflow_step(tmp_path: Path) -> None:
    record = _passing_observation()
    record["workflow_steps"] = [
        {"id": "import", "outcome": "passed"},
        {"id": "model_health", "outcome": "passed"},
        {"id": "analysis_setup", "outcome": "passed"},
        {"id": "run_monitor", "outcome": "passed"},
    ]
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "required_workflow_steps_missing" in payload["blockers"]
    assert "required_workflow_step_not_passed" in payload["blockers"]
    assert payload["summary"]["missing_workflow_steps"] == ["compare_report"]
    assert payload["summary"]["workflow_step_pass_count"] == 4


def test_ux_new_user_observation_rejects_failed_workflow_step(tmp_path: Path) -> None:
    record = _passing_observation()
    record["workflow_steps"][3]["outcome"] = "blocked"
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "required_workflow_step_not_passed" in payload["blockers"]
    assert payload["summary"]["missing_workflow_steps"] == []
    assert payload["summary"]["not_passed_workflow_steps"] == ["run_monitor"]


def test_ux_new_user_observation_rejects_legacy_template_tokens(tmp_path: Path) -> None:
    observation = _write_json(tmp_path / "ux_observation.json", _legacy_template_observation())

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "placeholder_values_present" in payload["blockers"]
    assert "template_only_observation_source" in payload["blockers"]
    assert "sample_project_id" in payload["summary"]["placeholder_fields"]
    assert "evidence_ref" in payload["summary"]["placeholder_fields"]


def test_ux_new_user_observation_rejects_unresolvable_evidence_ref(tmp_path: Path) -> None:
    record = _passing_observation()
    record["evidence_ref"] = "ux-observation-001"
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "evidence_ref_unresolvable" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is False
    assert payload["summary"]["evidence_ref_kind"] == "local_path_missing"


def test_ux_new_user_observation_rejects_self_referenced_evidence_ref(tmp_path: Path) -> None:
    observation = tmp_path / "ux_observation.json"
    record = _passing_observation()
    record["evidence_ref"] = str(observation)
    _write_json(observation, record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "evidence_ref_self_reference" in payload["blockers"]
    assert payload["checks"]["evidence_ref_not_self_reference_pass"] is False


def test_ux_new_user_observation_rejects_template_evidence_ref(tmp_path: Path) -> None:
    template = Path("docs/templates/ux_new_user_observation.template.json").resolve()
    record = _passing_observation()
    record["evidence_ref"] = str(template)
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "evidence_ref_template_reference" in payload["blockers"]
    assert payload["checks"]["evidence_ref_not_template_reference_pass"] is False


def test_ux_new_user_observation_rejects_template_like_evidence_artifact(tmp_path: Path) -> None:
    observation_template = _write_json(tmp_path / "docs" / "templates" / "ux-observation-note.json", {"template": True})
    record = _passing_observation()
    record["evidence_ref"] = str(observation_template)
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(
        observation_path=observation,
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert "evidence_ref_template_artifact" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_template_reference_pass"] is True
    assert payload["checks"]["evidence_ref_not_template_artifact_pass"] is False


def test_ux_new_user_observation_rejects_generated_gate_artifact_evidence_ref(tmp_path: Path) -> None:
    generated_report = _write_json(
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "ux_new_user_observation_report.json",
        {"contract_pass": False},
    )
    record = _passing_observation()
    record["evidence_ref"] = str(generated_report)
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(
        observation_path=observation,
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert "evidence_ref_generated_gate_artifact" in payload["blockers"]
    assert payload["checks"]["evidence_ref_resolvable_pass"] is True
    assert payload["checks"]["evidence_ref_not_generated_gate_artifact_pass"] is False


def test_ux_new_user_observation_rejects_placeholder_and_slow_completion(tmp_path: Path) -> None:
    record = _passing_observation()
    record["observer"] = "TODO"
    record["completion_minutes"] = 35.0
    observation = _write_json(tmp_path / "ux_observation.json", record)

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "placeholder_values_present" in payload["blockers"]
    assert "completion_gt_30min" in payload["blockers"]


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    out = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    exit_code = build_ux_new_user_observation_report.main(
        [
            "--observation",
            str(tmp_path / "missing.json"),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "UX New-User Observation Report" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is False
    markdown = out_md.read_text(encoding="utf-8")
    assert "Required Fields" in markdown
    assert "Gate Unblock Plan" in markdown
