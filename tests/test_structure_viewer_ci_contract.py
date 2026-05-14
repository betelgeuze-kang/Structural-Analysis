from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_structure_viewer_contract_suite_before_frontend_smoke() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Structure viewer contracts" in workflow
    assert "python scripts/verify_structure_viewer_contracts.py" in workflow
    assert workflow.index("Structure viewer contracts") < workflow.index("Frontend smoke")


def test_structure_viewer_contract_runner_covers_source_and_singlefile_surfaces() -> None:
    script = (ROOT / "scripts" / "verify_structure_viewer_contracts.py").read_text(encoding="utf-8")

    assert "tests/test_structure_viewer_real_drawing_browser_state_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_panel_renderer_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_quality_contract.py" in script
    assert "tests/test_structure_viewer_shared_selection_state_contract.py" in script
    assert "tests/test_structure_viewer_stats_summary_contract.py" in script
    assert "tests/test_generate_selfcontained_viewer.py" in script
    assert "tests/test_structure_viewer_singlefile_offline_contract.py" in script


def test_structure_viewer_contract_runner_has_dry_run_command_preview() -> None:
    result = subprocess.run(
        ["python3", "scripts/verify_structure_viewer_contracts.py", "--dry-run"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "pytest -q" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_panel_renderer_contract.py" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_quality_contract.py" in result.stdout
    assert "tests/test_structure_viewer_stats_summary_contract.py" in result.stdout
