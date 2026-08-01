from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_canonical_ci_owns_structural_core_lane() -> None:
    workflow = _read("ci.yml")

    assert "name: CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "timeout-minutes: 180" in workflow
    assert "scripts/check_product_ci_boundaries.py" in workflow
    assert "scripts/run_product_ci_lane.py --lane core" in workflow
    assert "scripts/verify_quality_gate.py --mode pr" in workflow


def test_pr_quality_gate_pins_reproducible_numerical_toolchain() -> None:
    workflow = _read("ci.yml")

    install = workflow.split("- name: Install Python package", 1)[1].split(
        "- name: Install Node dependencies",
        1,
    )[0]
    assert "python -m pip install numpy==1.26.4 scipy==1.12.0" in install

    quality_gate = workflow.split("- name: PR quality gate", 1)[1].split(
        "- name: Upload quality-gate log",
        1,
    )[0]
    assert "OPENBLAS_CORETYPE: Haswell" in quality_gate
    assert 'OPENBLAS_NUM_THREADS: "1"' in quality_gate
    assert 'OMP_NUM_THREADS: "1"' in quality_gate


def test_python_and_frontend_source_triggers_are_disjoint() -> None:
    canonical = _read("ci.yml")
    frontend = _read("frontend-web-ci.yml")

    assert canonical.count('- "src/structural_analysis/**"') == 2
    assert '- "src/**"' not in canonical

    frontend_lines = frontend.splitlines()
    broad_indices = [
        index
        for index, line in enumerate(frontend_lines)
        if line.strip() == '- "src/**"'
    ]
    excluded_indices = [
        index
        for index, line in enumerate(frontend_lines)
        if line.strip() == '- "!src/structural_analysis/**"'
    ]
    assert len(broad_indices) == 2
    assert len(excluded_indices) == 2
    assert all(
        broad_index < excluded_index
        for broad_index, excluded_index in zip(
            broad_indices,
            excluded_indices,
            strict=True,
        )
    )


def test_frontend_lane_keeps_non_python_source_and_self_triggers() -> None:
    workflow = _read("frontend-web-ci.yml")

    for path in (
        "index.html",
        "prototype/**",
        "src/**",
        "tests/frontend/**",
        "scripts/*.mjs",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "vite.config.ts",
        ".github/workflows/frontend-web-ci.yml",
    ):
        assert f'- "{path}"' in workflow


def test_legacy_evidence_has_independent_hosted_lane() -> None:
    workflow = _read("legacy-evidence-ci.yml")

    assert "name: Legacy Evidence CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "timeout-minutes: 180" in workflow
    assert "python -m pip install numpy==1.26.4 scipy==1.12.0" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    assert "scripts/run_product_ci_lane.py" in workflow
    assert "--lane legacy_evidence" in workflow
    assert "tests/test_build_product_readiness_snapshot.py" in workflow
    assert "tests/test_validate_external_vv_operator_attestation.py" in workflow
    assert "tests/test_promote_external_vv_level2.py" in workflow
    assert "run_clean_runner.py" in workflow
    assert "--refresh-product-replay-summary" in workflow
    assert (
        "scripts/build_bounded_planar_external_linear_case_package.py" in workflow
    )
    assert (
        "scripts/build_bounded_planar_external_negative_case_package.py" in workflow
    )
    assert (
        "tests/test_build_bounded_planar_external_linear_case_package.py" in workflow
    )
    assert (
        "tests/test_build_bounded_planar_external_negative_case_package.py" in workflow
    )
    assert "tests/test_ingest_bounded_planar_external_linear_results.py" in workflow
    assert "tests/test_ingest_bounded_planar_external_negative_results.py" in workflow
    assert "tests/test_build_bounded_planar_external_vv_matrix.py" in workflow


def test_molecular_code_is_checked_only_as_quarantine() -> None:
    workflow = _read("science-quarantine-ci.yml")

    assert "name: Molecular Quarantine CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "--lane molecular_quarantine" in workflow
    assert "--collect-only" in workflow
    assert "without product promotion" in workflow


def test_quarantine_control_plane_path_does_not_match_product_tokens() -> None:
    assert not (WORKFLOWS / "molecular-quarantine-ci.yml").exists()
    assert (WORKFLOWS / "science-quarantine-ci.yml").exists()


def test_pr_quality_gate_no_longer_lints_all_product_domains_together() -> None:
    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")

    assert '"scripts/check_product_ci_boundaries.py"' in gate
    assert '_lane_command("core")' in gate
    assert '[_python(), "-m", "ruff", "check", "."]' not in gate
    assert '_lane_command("legacy_evidence")' in gate
    assert '_lane_command("molecular_quarantine")' in gate


def test_runner_policy_allowlists_all_deterministic_product_lanes() -> None:
    policy = (ROOT / "scripts" / "check_github_actions_runner_policy.py").read_text(
        encoding="utf-8"
    )

    assert '".github/workflows/ci.yml"' in policy
    assert '".github/workflows/engine-v2-contract-ci.yml"' in policy
    assert '".github/workflows/legacy-evidence-ci.yml"' in policy
    assert '".github/workflows/science-quarantine-ci.yml"' in policy
    assert '".github/workflows/molecular-quarantine-ci.yml"' not in policy


def test_engine_v2_contract_lane_runs_the_complete_hosted_suite() -> None:
    workflow = _read("engine-v2-contract-ci.yml")

    assert "name: Engine v2 Contract CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "python -m pip install numpy==1.26.4 scipy==1.12.0" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    assert 'MKL_NUM_THREADS: "1"' in workflow
    assert 'PYTHONHASHSEED: "0"' in workflow
    assert "python -m pytest -q" in workflow
    assert "tests/test_engine_v2*.py" in workflow
    assert "tests/test_model_ir_v2_contract.py" in workflow
    assert '- "src/structural_analysis/engine_v2/**"' in workflow
    assert '- "src/structural_analysis/engine_v2_backends/**"' in workflow
    assert (
        '- "src/structural_analysis/schemas/cpu_fgmres_checkpoint_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/numerical_result_ir_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/diagnostic_ir_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/engineering_result_ir_v1.schema.json"'
        in workflow
    )
    assert (
        '- "src/structural_analysis/schemas/linear_static_recovery_operator_v1.schema.json"'
        in workflow
    )
    assert "scripts/run_engine_v2_hip_primitive_parity.py --check" in workflow
    assert "scripts/run_engine_v2_hip_current_tangent_operator.py" in workflow
    assert "scripts/run_engine_v2_hip_sparse_lu_apply.py" in workflow
    assert "scripts/run_engine_v2_hip_fgmres_recurrence.py --check" in workflow
    assert "--compile-only --check" in workflow
    assert "hip_fgmres_multiblock_compile_receipt_v1.schema.json" in workflow
    assert "hip_fgmres_device_receipt_v1.schema.json" in workflow
    assert "run_engine_v2_hip_fgmres_device_receipt.py" in workflow
    assert "engine_v2_hip_fgmres_gfx1030_device_receipt.json" in workflow
    assert "Check committed gfx1030 device receipt offline" in workflow
    assert "engine_v2_hip_fgmres_multiblock_compile_receipt.json" in workflow
    assert "hip_fgmres_stage4_status_v1.schema.json" in workflow
    assert "build_engine_v2_hip_fgmres_stage4_status.py --check" in workflow
    assert "engine_v2_hip_fgmres_stage4_status.json" in workflow
    assert "hip_current_tangent_operator_compile_receipt_v1.schema.json" in (
        workflow
    )
    assert "hip_current_tangent_operator_parity_v1.schema.json" in workflow
    assert "engine_v2_current_tangent_operator.hip.cpp" in workflow
    assert (
        "engine_v2_hip_current_tangent_operator_compile_receipt.json"
        in workflow
    )
    assert "Check committed HIP current-tangent compile receipt offline" in (
        workflow
    )
    assert (
        "build_g1_mgt_hip_current_tangent_host_parser_receipt.py"
        in workflow
    )
    assert "--check-source-only" in workflow
    assert (
        "g1_mgt_hip_current_tangent_host_parser_receipt_v1.schema.json"
        in workflow
    )
    assert (
        "g1_mgt_hip_current_tangent_host_parser_receipt.json" in workflow
    )
    assert (
        "Check actual-MGT HIP current-tangent parser receipt sources offline"
        in workflow
    )
    assert (
        "run_g1_mgt_hip_current_tangent_hardware_parity.py" in workflow
    )
    assert (
        "g1_mgt_hip_current_tangent_hardware_parity_receipt_v1.schema.json"
        in workflow
    )
    assert (
        "g1_mgt_hip_current_tangent_hardware_parity_receipt.json" in workflow
    )
    assert "g1_mgt_hip_current_tangent_action.f64le" in workflow
    assert (
        "Check actual-MGT HIP current-tangent hardware receipt sources offline"
        in workflow
    )
    assert "hip_sparse_lu_apply_compile_receipt_v1.schema.json" in workflow
    assert "hip_sparse_lu_apply_parity_v1.schema.json" in workflow
    assert "engine_v2_sparse_lu_apply.hip.cpp" in workflow
    assert "engine_v2_hip_sparse_lu_apply_compile_receipt.json" in workflow
    assert "Check committed HIP sparse-LU compile receipt offline" in workflow
    assert '- "tests/test_engine_v2*.py"' in workflow
    assert '- "tests/test_model_ir_v2_contract.py"' in workflow
    assert "self-hosted" not in workflow
    assert "does not exercise" in workflow
    assert "hipcc" not in workflow
