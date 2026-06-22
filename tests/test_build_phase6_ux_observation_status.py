from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase6_ux_observation_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase6_ux_observation_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase6_ux_observation_status_blocks_without_human_and_execution_evidence() -> None:
    payload = module.build_phase6_ux_observation_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase6-ux-observation-status.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["human_observation_gate"]["status"] == "blocked"
    assert payload["human_observation_gate"]["workflow_step_pass_count"] == 0
    assert payload["human_observation_gate"]["missing_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert payload["intake_packet_gate"]["status"] == "blocked"
    assert payload["intake_packet_gate"]["field_pass_count"] == 0
    assert payload["phase5_workflow_gate"]["status"] == "blocked"
    assert payload["phase5_workflow_gate"]["workflow_shell_step_pass_count"] == 5
    assert payload["phase5_workflow_gate"]["execution_workflow_step_pass_count"] == 0
    assert payload["phase5_workflow_gate"]["task_based_ux_browser_execution_passed"] is False
    assert "human_new_user_observation_not_passed" in payload["blockers"]
    assert "human_observation_workflow_step_pass_count_below_required:0/5" in payload["blockers"]
    assert "phase5_workflow_execution_not_proven:0/5" in payload["blockers"]
    assert "task_based_ux_browser_execution_not_passed" in payload["blockers"]
    assert "observation_report:observation_file_missing" in payload["blockers"]
    assert "intake packet is only a handoff checklist" in payload["claim_boundary"]
    assert "automated browser/task tests do not replace" in payload["claim_boundary"]


def test_phase6_ux_observation_status_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase6_ux_observation_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase6_ux_observation_status_missing:")


def test_phase6_ux_observation_status_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "ux.json"
    module.write_phase6_ux_observation_status(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase6_ux_observation_status(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "phase6_ux_observation_status_mismatch"
