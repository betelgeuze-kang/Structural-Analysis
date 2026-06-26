from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def test_benchmark_package_cli_writes_seed_manifest_scorecard_and_summary(
    tmp_path: Path,
) -> None:
    manifest_out = tmp_path / "manifest.json"
    scorecard_out = tmp_path / "scorecard.json"
    summary_out = tmp_path / "summary.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.benchmark.cli",
            "--manifest-out",
            str(manifest_out),
            "--scorecard-out",
            str(scorecard_out),
            "--summary-out",
            str(summary_out),
            "--json",
            "--fail-blocked",
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(manifest_out.read_text(encoding="utf-8"))
    scorecard = json.loads(scorecard_out.read_text(encoding="utf-8"))
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    stdout_summary = json.loads(completed.stdout)

    assert manifest["schema_version"] == "phase3-benchmark-factory-manifest.v1"
    assert manifest["case_count"] == 30
    assert manifest["lanes"] == [
        "analytic-small",
        "element-patch",
        "nonlinear-material-mesh",
    ]
    assert scorecard["schema_version"] == "phase3-benchmark-factory-scorecard.v1"
    assert scorecard["contract_pass"] is True
    assert scorecard["case_count"] == 30
    assert scorecard["pass_count"] == 30
    expected_comparison_count = sum(
        len(row["expected_outputs"]) for row in manifest["rows"]
    )
    assert scorecard["expected_output_comparison_count"] == expected_comparison_count
    assert (
        scorecard["expected_output_comparison_pass_count"]
        == expected_comparison_count
    )
    assert scorecard["expected_output_contract_pass"] is True
    assert all(row["expected_output_contract_pass"] is True for row in scorecard["rows"])
    assert summary == stdout_summary
    assert summary["schema_version"] == "phase3-benchmark-runner-cli-summary.v1"
    assert summary["runner"] == "structural-analysis-benchmark"
    assert summary["module_command"] == "python -m structural_analysis.benchmark.cli"
    assert summary["contract_pass"] is True
    assert summary["expected_output_comparison_count"] == expected_comparison_count
    assert (
        summary["expected_output_comparison_pass_count"]
        == expected_comparison_count
    )
    assert summary["expected_output_contract_pass"] is True
    assert summary["phase3_closure_claim"] is False
    assert summary["developer_preview_release_candidate_claim"] is False
    assert "does not close full Phase 3" in summary["claim_boundary"]
    assert "G1 solver-core" in summary["claim_boundary"]


def test_benchmark_entrypoint_is_declared_for_packaging() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    setup_cfg = (REPO_ROOT / "setup.cfg").read_text(encoding="utf-8")

    assert (
        'structural-analysis-benchmark = "structural_analysis.benchmark.cli:main"'
        in pyproject
    )
    assert "structural-analysis-benchmark = structural_analysis.benchmark.cli:main" in setup_cfg
