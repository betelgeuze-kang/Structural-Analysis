from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_structure_viewer_contract_suite_before_frontend_smoke() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")

    assert "PR quality gate" in workflow
    assert "scripts/verify_quality_gate.py --mode pr" in workflow
    assert "verify:viewer-manifest" in gate
    assert "scripts/verify_structure_viewer_contracts.py" in gate
    assert "verify:frontend-browser-smoke" in gate
    assert gate.index("verify:viewer-manifest") < gate.index("scripts/verify_structure_viewer_contracts.py")
    assert gate.index("scripts/verify_structure_viewer_contracts.py") < gate.index("verify:frontend-browser-smoke")


def test_structure_viewer_contract_runner_covers_source_and_singlefile_surfaces() -> None:
    script = (ROOT / "scripts" / "verify_structure_viewer_contracts.py").read_text(encoding="utf-8")

    assert "tests/test_structure_viewer_real_drawing_browser_state_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_panel_events_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_panel_model_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_panel_renderer_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_quality_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_selection_contract.py" in script
    assert "tests/test_structure_viewer_real_drawing_tree_model_contract.py" in script
    assert "tests/test_structure_viewer_search_results_model_contract.py" in script
    assert "tests/test_structure_viewer_selection_summary_model_contract.py" in script
    assert "tests/test_structure_viewer_provenance_model_contract.py" in script
    assert "tests/test_structure_viewer_side_panel_model_contract.py" in script
    assert "tests/test_structure_viewer_shared_selection_state_contract.py" in script
    assert "tests/test_structure_viewer_stats_summary_contract.py" in script
    assert "tests/test_structure_viewer_project_manifest_verifier.py" in script
    assert "tests/test_structure_viewer_optimization_comparison_model_contract.py" in script
    assert "tests/test_structure_viewer_member_comparison_model_contract.py" in script
    assert "tests/test_structure_viewer_pdf_export_contract.py" in script
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
    assert "tests/test_structure_viewer_real_drawing_panel_events_contract.py" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_panel_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_panel_renderer_contract.py" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_quality_contract.py" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_selection_contract.py" in result.stdout
    assert "tests/test_structure_viewer_real_drawing_tree_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_search_results_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_selection_summary_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_provenance_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_side_panel_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_stats_summary_contract.py" in result.stdout
    assert "tests/test_structure_viewer_project_manifest_verifier.py" in result.stdout
    assert "tests/test_structure_viewer_optimization_comparison_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_member_comparison_model_contract.py" in result.stdout
    assert "tests/test_structure_viewer_pdf_export_contract.py" in result.stdout
