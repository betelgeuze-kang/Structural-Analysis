from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


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
    assert "scripts/check_p0_closure_status.py --json --fail-core-open" in output
    assert "scripts/check_p1_readiness_status.py --json --fail-core-open" in output
    assert "scripts/check_p1_benchmark_breadth_status.py --json --fail-core-open" in output
    assert "npm audit --audit-level high" in output
    assert output.index("npm ci") < output.index("npm audit --audit-level high")
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
    assert "scripts/check_p0_closure_status.py --json --fail-open" in output
    assert "scripts/check_p1_readiness_status.py --json --fail-blocked" in output
    assert "scripts/check_p1_benchmark_breadth_status.py --json --fail-blocked" in output
    assert "-m pytest -q" in output
    assert "verify:viewer-report-pdf" in output
    assert "verify:viewer-performance-probe" in output
    assert "verify:viewer-visual-regression" in output
    assert output.index("verify:frontend-browser-smoke") < output.index("verify:viewer-report-pdf")
    assert output.index("verify:viewer-report-pdf") < output.index("verify:viewer-performance-probe")
    assert output.index("verify:viewer-performance-probe") < output.index("verify:viewer-visual-regression")
    assert "scripts/report_commercialization_level.py --closure-mode conditional --fail-below 9.0" in output
    assert output.index("verify:viewer-visual-regression") < output.index("scripts/report_commercialization_level.py")
    assert "scripts/build_developer_preview_readiness.py --check" in output
    assert output.index("scripts/report_commercialization_level.py") < output.index(
        "scripts/build_developer_preview_readiness.py"
    )
    assert "scripts/build_phase1_core_api_contract_artifacts.py --check" in output
    assert output.index("scripts/build_developer_preview_readiness.py") < output.index(
        "scripts/build_phase1_core_api_contract_artifacts.py"
    )
    assert "scripts/build_phase2_frame_shell_material_coupling_artifacts.py --check" in output
    assert output.index("scripts/build_phase2_material_mesh_newton_artifacts.py") < output.index(
        "scripts/build_phase2_patch_rigidbody_artifacts.py"
    )
    assert output.index("scripts/build_phase2_patch_rigidbody_artifacts.py") < output.index(
        "scripts/build_phase2_mesh_load_step_convergence_artifacts.py"
    )
    assert output.index("scripts/build_phase2_mesh_load_step_convergence_artifacts.py") < output.index(
        "scripts/build_phase2_frame_shell_material_coupling_artifacts.py"
    )
    assert output.index("scripts/build_phase2_frame_shell_material_coupling_artifacts.py") < output.index(
        "scripts/build_phase3_benchmark_factory_artifacts.py"
    )
    assert "scripts/check_workstation_delivery_readiness.py --json" in output
    assert output.index("scripts/build_phase1_core_api_contract_artifacts.py") < output.index(
        "scripts/check_workstation_delivery_readiness.py"
    )
    assert "scripts/check_independent_product_readiness.py --json" in output
    assert output.index("scripts/check_workstation_delivery_readiness.py") < output.index(
        "scripts/check_independent_product_readiness.py"
    )
    assert "git diff --check" in output


def test_quality_gate_release_dry_run_lists_canonical_snapshot_gate(capsys) -> None:
    exit_code = verify_quality_gate.main(["--mode", "release", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "-m pytest -q" in output
    assert "verify:viewer-visual-regression" in output
    assert "scripts/check_generated_worktree_clean.py --show-ok" in output
    assert "scripts/check_github_actions_runner_policy.py --fail-blocked" in output
    assert "scripts/check_github_actions_self_hosted_runner_status.py" in output
    assert "github_actions_self_hosted_runner_status.json" in output
    runner_status_line = next(
        line for line in output.splitlines()
        if "scripts/check_github_actions_self_hosted_runner_status.py" in line
    )
    assert " --check" in runner_status_line
    assert " --fail-blocked" in runner_status_line
    assert "--write-query-error-evidence" not in runner_status_line
    assert "scripts/build_product_readiness_snapshot.py" in output
    assert "scripts/build_developer_preview_readiness.py --check" in output
    assert "scripts/build_phase1_core_api_contract_artifacts.py --check" in output
    assert "scripts/build_phase2_patch_rigidbody_artifacts.py --check" in output
    assert "scripts/build_phase2_mesh_load_step_convergence_artifacts.py --check" in output
    assert "scripts/build_phase2_frame_shell_material_coupling_artifacts.py --check" in output
    assert "product_readiness_snapshot.json" in output
    assert "tests/test_product_readiness_snapshot_doc_sync.py" in output
    assert "--fail-blocked" in output
    # The canonical snapshot gate must run as a non-mutating --check.
    snapshot_gate_line = next(
        line for line in output.splitlines()
        if "scripts/build_product_readiness_snapshot.py" in line
    )
    assert " --check" in snapshot_gate_line
    assert " --fail-blocked" in snapshot_gate_line
    assert output.index("verify:viewer-visual-regression") < output.index(
        "scripts/check_github_actions_runner_policy.py"
    )
    assert output.index("scripts/check_github_actions_runner_policy.py") < output.index(
        "scripts/check_github_actions_self_hosted_runner_status.py"
    )
    assert output.index("scripts/check_github_actions_self_hosted_runner_status.py") < output.index(
        "scripts/build_product_readiness_snapshot.py"
    )
    assert output.index("scripts/build_product_readiness_snapshot.py") < output.index(
        "tests/test_product_readiness_snapshot_doc_sync.py"
    )
    assert output.index("tests/test_product_readiness_snapshot_doc_sync.py") < output.rindex("git diff --check")


def test_quality_gate_release_mode_returns_nonzero_but_runs_followup_checks(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, cwd, check):
        calls.append(command)
        returncode = 1 if "scripts/build_product_readiness_snapshot.py" in command else 0
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(verify_quality_gate.subprocess, "run", fake_run)

    exit_code = verify_quality_gate.main(["--mode", "release"])

    rendered = [" ".join(command) for command in calls]
    assert exit_code == 1
    assert any("scripts/build_product_readiness_snapshot.py" in item for item in rendered)
    runner_status_line = next(
        item for item in rendered
        if "scripts/check_github_actions_self_hosted_runner_status.py" in item
    )
    assert " --check" in runner_status_line
    assert " --fail-blocked" in runner_status_line
    assert "--write-query-error-evidence" not in runner_status_line
    # The snapshot gate must run as a non-mutating --check that can also
    # still report a non-zero exit when the stored snapshot is stale.
    snapshot_gate_line = next(
        item for item in rendered if "scripts/build_product_readiness_snapshot.py" in item
    )
    assert " --check" in snapshot_gate_line
    assert " --fail-blocked" in snapshot_gate_line
    assert any("tests/test_product_readiness_snapshot_doc_sync.py" in item for item in rendered)
    assert rendered[-1] == "git diff --check"
    assert rendered.index(
        next(item for item in rendered if "scripts/build_product_readiness_snapshot.py" in item)
    ) < rendered.index(
        next(item for item in rendered if "tests/test_product_readiness_snapshot_doc_sync.py" in item)
    )


def test_quality_gate_release_mode_continues_after_runner_status_failure(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, cwd, check):
        calls.append(command)
        rendered = " ".join(command)
        if "scripts/check_github_actions_self_hosted_runner_status.py" in rendered:
            return SimpleNamespace(returncode=2)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verify_quality_gate.subprocess, "run", fake_run)

    exit_code = verify_quality_gate.main(["--mode", "release"])

    rendered = [" ".join(command) for command in calls]
    assert exit_code == 2
    assert any(
        "scripts/check_github_actions_self_hosted_runner_status.py" in item
        for item in rendered
    )
    assert any("scripts/build_product_readiness_snapshot.py" in item for item in rendered)
    assert any("tests/test_product_readiness_snapshot_doc_sync.py" in item for item in rendered)
    assert rendered[-1] == "git diff --check"
    assert rendered.index(
        next(
            item
            for item in rendered
            if "scripts/check_github_actions_self_hosted_runner_status.py" in item
        )
    ) < rendered.index(
        next(item for item in rendered if "scripts/build_product_readiness_snapshot.py" in item)
    )


def test_quality_gate_release_mode_fails_when_final_diff_check_fails(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, cwd, check):
        calls.append(command)
        rendered = " ".join(command)
        if rendered == "git diff --check":
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verify_quality_gate.subprocess, "run", fake_run)

    exit_code = verify_quality_gate.main(["--mode", "release"])

    rendered = [" ".join(command) for command in calls]
    assert exit_code == 1
    assert rendered[-1] == "git diff --check"
    assert any(
        "scripts/check_github_actions_self_hosted_runner_status.py" in item
        for item in rendered
    )
    assert any("scripts/build_product_readiness_snapshot.py" in item for item in rendered)
