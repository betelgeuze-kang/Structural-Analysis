from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_structure_viewer_contract_suite_before_frontend_smoke() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Structure viewer contracts" in workflow
    assert "tests/test_structure_viewer_real_drawing_browser_state_contract.py" in workflow
    assert "tests/test_structure_viewer_real_drawing_quality_contract.py" in workflow
    assert "tests/test_structure_viewer_shared_selection_state_contract.py" in workflow
    assert "tests/test_generate_selfcontained_viewer.py" in workflow
    assert workflow.index("Structure viewer contracts") < workflow.index("Frontend smoke")
