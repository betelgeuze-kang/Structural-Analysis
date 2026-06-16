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
        "participant_role": "new_user",
        "new_to_product": True,
        "sample_project_id": "sample_tower",
        "workflow_scope": "open sample project, review evidence package, export report",
        "observer": "ux-research-owner",
        "started_at_utc": "2026-06-16T09:00:00+00:00",
        "completed_at_utc": "2026-06-16T09:24:00+00:00",
        "completion_minutes": 24.0,
        "blocker_count": 0,
        "evidence_ref": "ux-observation-001",
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
    assert payload["reason_code"] == "ERR_UX_NEW_USER_OBSERVATION_REQUIRED"
    assert "observation_file_missing" in payload["blockers"]
    assert "completion_minutes" in payload["summary"]["missing_fields"]
    assert "completion_gt_30min" not in payload["blockers"]


def test_ux_new_user_observation_passes_with_human_record(tmp_path: Path) -> None:
    observation = _write_json(tmp_path / "ux_observation.json", _passing_observation())

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["completion_30min_pass"] is True
    assert payload["summary"]["completion_minutes"] == 24.0


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


def test_ux_new_user_observation_rejects_legacy_template_tokens(tmp_path: Path) -> None:
    observation = _write_json(tmp_path / "ux_observation.json", _legacy_template_observation())

    payload = build_ux_new_user_observation_report.build_report(observation_path=observation)

    assert payload["contract_pass"] is False
    assert "placeholder_values_present" in payload["blockers"]
    assert "template_only_observation_source" in payload["blockers"]
    assert "sample_project_id" in payload["summary"]["placeholder_fields"]
    assert "evidence_ref" in payload["summary"]["placeholder_fields"]


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
    assert "Required Fields" in out_md.read_text(encoding="utf-8")
