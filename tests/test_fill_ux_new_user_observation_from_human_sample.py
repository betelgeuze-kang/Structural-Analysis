from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "fill_ux_new_user_observation_from_human_sample.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fill_ux_new_user_observation_from_human_sample",
    SCRIPT_PATH,
)
assert SPEC is not None
fill_ux_observation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fill_ux_observation)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fill_ux_observation_from_explicit_human_sample_passes_report(
    tmp_path: Path,
) -> None:
    observation = tmp_path / "ux_new_user_observation.json"
    template_path = tmp_path / "ux_new_user_observation.template.json"

    payload = fill_ux_observation.fill_ux_new_user_observation(
        repo_root=tmp_path,
        out=observation,
        template_path=template_path,
        participant_ref="ux-participant-001",
        participant_role="new_user",
        new_to_product=True,
        sample_project_id="sample_tower",
        observer="ux-research-owner",
        started_at_utc="2026-06-16T09:00:00+00:00",
        completed_at_utc="2026-06-16T09:24:00+00:00",
        completion_minutes=24.0,
        blocker_count=0,
        evidence_ref="ux:UX-OBS-001",
        approval_decision="accepted",
        all_required_steps_passed=True,
    )

    written = _read_json(observation)
    assert payload["contract_pass"] is True
    assert payload["status"] == "filled"
    assert payload["validation_blockers"] == []
    assert written["template_only"] is False
    assert len(written["workflow_steps"]) == 5
    assert written["workflow_steps"][0] == {
        "id": "import",
        "label": "Import",
        "outcome": "passed",
    }
    assert any(
        "build_ux_new_user_observation_report.py" in command
        for command in payload["validation_commands"]
    )


def test_fill_ux_observation_blocks_placeholder_or_missing_workflow_steps(
    tmp_path: Path,
) -> None:
    observation = tmp_path / "ux_new_user_observation.json"
    template_path = tmp_path / "ux_new_user_observation.template.json"

    payload = fill_ux_observation.fill_ux_new_user_observation(
        repo_root=tmp_path,
        out=observation,
        template_path=template_path,
        participant_ref="OWNER_INPUT_REQUIRED",
        participant_role="new_user",
        new_to_product=True,
        sample_project_id="sample_tower",
        observer="ux-research-owner",
        started_at_utc="2026-06-16T09:00:00+00:00",
        completed_at_utc="2026-06-16T09:24:00+00:00",
        completion_minutes=24.0,
        blocker_count=0,
        evidence_ref="ux:UX-OBS-001",
        approval_decision="accepted",
    )

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert "placeholder_values_present" in payload["validation_blockers"]
    assert "workflow_steps_missing" in payload["validation_blockers"]
    assert _read_json(observation)["workflow_steps"] == []
