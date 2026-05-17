from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verify_quality_gate.py"
SPEC = importlib.util.spec_from_file_location("verify_quality_gate", SCRIPT_PATH)
assert SPEC is not None
verify_quality_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verify_quality_gate)


def test_quality_gate_pr_dry_run_lists_fast_gates(capsys) -> None:
    exit_code = verify_quality_gate.main(["--mode", "pr", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "scripts/check_p0_closure_status.py --json --fail-open" in output
    assert "scripts/check_p1_readiness_status.py --json --fail-blocked" in output
    assert "verify:viewer-manifest" in output
    assert "scripts/verify_structure_viewer_contracts.py" in output
    assert output.index("verify:viewer-manifest") < output.index("scripts/verify_structure_viewer_contracts.py")
    assert "verify:frontend-browser-smoke -- --mode minimal" in output
    assert "scripts/report_source_boundary_footprint.py --check" in output
    assert "tests/test_project_ops_api_service.py" in output
    assert "-m pytest -q\n" not in output


def test_quality_gate_full_dry_run_lists_full_regression(capsys) -> None:
    exit_code = verify_quality_gate.main(["--mode", "full", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "-m pytest -q" in output
    assert "verify:viewer-report-pdf" in output
    assert output.index("verify:frontend-browser-smoke") < output.index("verify:viewer-report-pdf")
    assert "scripts/report_commercialization_level.py --closure-mode conditional --fail-below 9.0" in output
    assert output.index("verify:viewer-report-pdf") < output.index("scripts/report_commercialization_level.py")
    assert "git diff --check" in output
