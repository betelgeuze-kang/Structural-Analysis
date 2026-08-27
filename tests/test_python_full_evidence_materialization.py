from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _extract_job(workflow: str, job_name: str) -> str:
    """Return one top-level GitHub Actions job without relying on job order."""

    lines = workflow.splitlines()
    marker = f"  {job_name}:"
    try:
        start = lines.index(marker)
    except ValueError as exc:  # pragma: no cover
        message = f"workflow job not found: {job_name}"
        raise AssertionError(message) from exc

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break

    return "\n".join(lines[start:end])


def test_full_pytest_refreshes_clean_runner_after_embedded_host_receipts() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")
    shard_job = _extract_job(workflow, "full_shards")
    aggregate_job = _extract_job(workflow, "full")

    code_receipt = shard_job.index(
        "python scripts/run_external_code_to_code_technical_receipt.py"
    )
    modal_receipt = shard_job.index(
        "python scripts/run_external_modal_buckling_technical_receipt.py"
    )
    clean_runner = shard_job.index(
        "python benchmarks/clean-runners/opensees-calculix/run_clean_runner.py"
    )
    first_case_package = shard_job.index(
        "python scripts/build_bounded_planar_external_linear_case_package.py"
    )

    assert code_receipt < modal_receipt < clean_runner < first_case_package
    assert "--repo-root ." in shard_job[clean_runner:first_case_package]
    assert (
        "--output-dir artifacts/vv/opensees_calculix_clean_runner"
        in shard_job[clean_runner:first_case_package]
    )
    assert (
        "--refresh-product-replay-summary"
        in shard_job[clean_runner:first_case_package]
    )

    assert "needs: full_shards" in aggregate_job
    assert "FULL_SHARDS_RESULT: ${{ needs.full_shards.result }}" in aggregate_job
    assert "run_external_code_to_code_technical_receipt.py" not in aggregate_job


def test_nightly_full_quality_materializes_current_source_evidence_before_gate() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "nightly-full-quality.yml"
    ).read_text(encoding="utf-8")
    job = _extract_job(workflow, "deterministic_quality")
    shard_job = _extract_job(workflow, "python_full_shards")
    aggregate_job = _extract_job(workflow, "full_quality")

    code_receipt = job.index(
        "python scripts/run_external_code_to_code_technical_receipt.py"
    )
    modal_receipt = job.index(
        "python scripts/run_external_modal_buckling_technical_receipt.py"
    )
    clean_runner = job.index(
        "python benchmarks/clean-runners/opensees-calculix/run_clean_runner.py"
    )
    matrix = job.index("python scripts/build_bounded_planar_external_vv_matrix.py")
    pristine_ledger = job.index("- name: Validate pristine commercial gap ledger")
    quality_step = job.index("- name: Deterministic repository quality gate")
    quality_gate = job.index("python scripts/verify_quality_gate.py")

    assert pristine_ledger < code_receipt < modal_receipt < clean_runner < matrix
    assert matrix < quality_step < quality_gate
    assert "--refresh-product-replay" in job[code_receipt:clean_runner]
    assert "--refresh-product-replay-summary" in job[clean_runner:matrix]
    assert "external execution bytes reused without freshness credit" in job
    ledger_nodeid = (
        "tests/test_commercial_gap_ledger_status.py::"
        "test_commercial_gap_ledger_status_is_honest_about_current_blockers"
    )
    assert "--mode full" in job[quality_gate:]
    assert "--python-suite-delegated-to-workflow-shards" in job[quality_gate:]
    host_parser_nodeid = (
        "tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py::"
        "test_committed_receipt_is_reproducible"
    )
    assert job.count(ledger_nodeid) == 1
    assert shard_job.count(ledger_nodeid) == 2
    assert host_parser_nodeid in shard_job
    assert shard_job.count("--deselect") == 2
    assert "python scripts/run_pytest_shard.py" in shard_job
    assert "- name: Deterministic Python regression suite" not in job
    for command in (
        "python scripts/build_stateful_nonlinear_no_solve_reaction_only_artifact.py",
        "python scripts/build_fracture_energy_concrete_benchmark.py",
        "python scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py",
        "python scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.py",
        "python scripts/build_phase2_linear_reference_artifacts.py",
        "python scripts/build_phase2_newton_globalization_artifacts.py",
        "python scripts/build_phase2_nonlinear_load_step_artifacts.py",
        "python scripts/build_phase2_material_newton_breadth_artifacts.py",
        "python scripts/build_phase2_material_mesh_newton_artifacts.py",
        "python scripts/build_phase2_patch_rigidbody_artifacts.py",
        "python scripts/build_phase2_mesh_load_step_convergence_artifacts.py",
        "python scripts/build_phase2_frame_shell_material_coupling_artifacts.py",
    ):
        assert matrix < job.index(command) < quality_gate

    shard_gate = shard_job.index("python scripts/run_pytest_shard.py")
    for command in (
        "python scripts/build_phase2_linear_reference_artifacts.py",
        "python scripts/build_phase2_newton_globalization_artifacts.py",
        "python scripts/build_phase2_nonlinear_load_step_artifacts.py",
        "python scripts/build_phase2_material_newton_breadth_artifacts.py",
        "python scripts/build_phase2_material_mesh_newton_artifacts.py",
        "python scripts/build_phase2_patch_rigidbody_artifacts.py",
        "python scripts/build_phase2_mesh_load_step_convergence_artifacts.py",
        "python scripts/build_phase2_frame_shell_material_coupling_artifacts.py",
    ):
        assert shard_job.index(command) < shard_gate

    assert "needs: [python_full_shards, deterministic_quality]" in aggregate_job
    assert "PYTHON_FULL_SHARDS_RESULT" in aggregate_job
    assert "DETERMINISTIC_QUALITY_RESULT" in aggregate_job
