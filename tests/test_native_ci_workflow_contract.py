from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_ci_contract.py"
SPEC = importlib.util.spec_from_file_location("check_native_ci_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_native_ci_contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_native_ci_contract
SPEC.loader.exec_module(check_native_ci_contract)


def test_native_workflows_satisfy_gate_bootstrap_contract() -> None:
    payload = check_native_ci_contract.check_native_ci_contract(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["native_pr_fast_jobs"] == sorted(
        {
            *check_native_ci_contract.PR_FAST_CHILDREN,
            *check_native_ci_contract.WINDOWS_HOSTED_CHILDREN,
            *check_native_ci_contract.MERGE_PRODUCT_CHILDREN,
            "native-pr-fast",
            "native-merge-product",
        }
    )
    assert payload["native_merge_product_jobs"] == sorted(
        {
            *check_native_ci_contract.MERGE_PRODUCT_CHILDREN,
            "native-merge-product",
        }
    )
    assert payload["native_nightly_quality_jobs"] == sorted(
        {
            *check_native_ci_contract.NIGHTLY_QUALITY_CHILDREN,
            "native-nightly-quality",
        }
    )


def test_merge_product_is_a_direct_required_context_sequenced_after_pr_fast() -> None:
    pr_fast = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    aggregate = pr_fast.split("  native-merge-product:\n", 1)[1]
    assert "- native-pr-fast" in aggregate
    assert "uses: ./.github/workflows/" not in aggregate
    assert "merge-ref base parent mismatch" in pr_fast
    assert "merge-ref head parent mismatch" in pr_fast


def test_hosted_native_gates_cannot_execute_hip_or_mutate_runner_services() -> None:
    combined = "\n".join(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8").lower()
        for name in (
            "native-pr-fast.yml",
            "native-nightly-quality.yml",
        )
    )

    assert "structural_enable_hip=off" in combined
    for forbidden in check_native_ci_contract.FORBIDDEN_HOSTED_COMMANDS:
        assert forbidden not in combined


def test_windows_hosted_gate_runs_bounded_native_frame3d_installed_layout() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )
    block = workflow.split("  windows-hosted-smoke:\n", 1)[1].split(
        "  native-pr-fast:\n", 1
    )[0]

    assert "runs-on: windows-latest" in block
    assert "needs:" not in block
    assert 'GIT_CONFIG_COUNT: "2"' in block
    assert "GIT_CONFIG_KEY_0: core.longpaths" in block
    assert 'GIT_CONFIG_VALUE_0: "true"' in block
    assert "GIT_CONFIG_KEY_1: core.autocrlf" in block
    assert 'GIT_CONFIG_VALUE_1: "false"' in block
    assert "cmake -S native/cpp -B $cmakeBuild -A x64" in block
    assert "--config Release" in block
    assert "STRUCTURAL_ENABLE_HIP=OFF" in block
    assert "structural_c_abi_v1.dll" in block
    assert "structural-workbench.exe" in block
    assert "workflow-model-linear" in block
    assert "element-recovery-view" in block
    assert (
        "structural-native-workbench-model-ir-linear-element-recovery-view.v1"
        in block
    )
    recovery_contract = block.split("$recoveryOutput =", 1)[1].split(
        "$htmlInvocation =", 1
    )[0]
    assert "ConvertFrom-Json" not in recovery_contract
    assert '"element-recovery-view.txt"' in recovery_contract
    assert "^View hash: sha256:[0-9a-f]{64}$" in recovery_contract
    assert "report-export-html" in block
    assert "structural-native-windows-process-receipt.v1" in block
    assert ".stderr.txt" in block
    assert "Not a structural-distribution bundle" in block


def test_native_language_neutral_oracles_pin_lf_checkout_bytes() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "native/tests/fixtures/model_ir_linear/*.txt text eol=lf" in attributes


def test_native_nightly_requires_sanitizer_fuzz_and_license_policy() -> None:
    nightly = (ROOT / ".github/workflows/native-nightly-quality.yml").read_text(
        encoding="utf-8"
    )

    assert "STRUCTURAL_ENABLE_SANITIZERS=ON" in nightly
    assert "STRUCTURAL_BUILD_FUZZERS=ON" in nightly
    assert "structural_native_fuzzers" in nightly
    assert "check_native_dependency_licenses.py" in nightly

    fuzz_contract = (ROOT / "native/cpp/tests/fuzz/CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    assert "structural_model_ir_linear_assembly_abi_fuzz" in fuzz_contract
    assert "structural_model_ir_linear_assembly_abi_fuzz_smoke" in fuzz_contract
    assert "structural_model_ir_linear_reactions_abi_fuzz" in fuzz_contract
    assert "structural_model_ir_linear_reactions_abi_fuzz_smoke" in fuzz_contract


def test_native_rust_gate_checks_the_declared_minimum_toolchain() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    assert "rustup toolchain install 1.77.0 --profile minimal" in workflow
    assert "cargo +1.77.0 check" in workflow
    assert "--workspace --all-targets --locked" in workflow


def test_native_dependency_boundary_requires_deployment_cutover_contract() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    dependency = workflow.split("  dependency-boundary:\n", 1)[1].split(
        "  native-pr-fast:\n", 1
    )[0]
    assert "check_native_deployment_cutover.py --json --fail-blocked" in dependency
    assert "check_native_automation_cutover.py --json --fail-blocked" in dependency
    assert "check_native_workbench_ui_transition.py --json --fail-blocked" in dependency


def test_native_rust_gate_separates_r4_product_and_legacy_runtime_exports() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    assert "implementation/phase1/structural_runtime_ffi/Cargo.toml" in workflow
    assert "check_structural_runtime_ffi_r4.py" in workflow
    assert "build/native-legacy-runtime-r4/release/libstructural_runtime_ffi.so" in workflow
    assert "structural_track_point_load_abi_tests" in workflow
    assert "structural_nonlinear_static_abi_tests" in workflow
    assert "structural_backend_selector_abi_tests" in workflow
    assert "structural_nonlinear_ndtha_abi_tests" in workflow
    assert "structural_reference_elements_abi_tests" in workflow
    assert "structural_model_ir_linear_assembly_abi_tests" in workflow
    assert "structural_generalized_eigen_abi_tests" in workflow
    assert 'payload["abi_version"] == "0x0001000f"' in workflow
    assert "check_native_backend_selector.py" in workflow
    assert "libmgt_hip_full_residual_rust_ffi.so" in workflow


def test_modelir_gate_requires_component_and_aggregate_slice_d_promotion() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    assert "--is-enabled modelir_v2_rust_wire" in workflow
    assert "--is-enabled modelir_v2_cpp_core; then" in workflow
    assert "--is-enabled modelir_v2" in workflow
    assert "-p structural-ffi -p structural-runtime -p structural-cli" in workflow
    assert "--no-tests=error -L modelir" in workflow


def test_merge_oracle_gate_runs_all_native_solver_python_c1_matrices() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )
    assert "tests/test_native_nonlinear_ndtha_python_parity.py" in workflow
    assert "tests/test_native_nonlinear_static_python_parity.py" in workflow

    assert "tests/test_native_track_point_load_python_parity.py" in workflow
    assert "tests/test_native_reference_elements_python_parity.py" in workflow
    assert "tests/test_native_sparse_linear_python_parity.py" in workflow
    assert "tests/test_native_generalized_eigen_python_parity.py" in workflow
    assert "check_native_generalized_eigen.py" in workflow
    assert "check_native_generalized_eigen_product.py" in workflow
    assert "check_native_sparse_linear_product.py" in workflow
    assert "check_native_model_ir_linear_product.py" in workflow
    assert "check_native_model_ir_linear_jobs.py" in workflow
    assert "check_native_model_ir_linear_workbench.py" in workflow
    assert "check_native_nonlinear_static_product.py" in workflow
    assert "structural_sparse_linear_abi_tests" in workflow


def test_reference_hip_c2_is_manual_protected_and_self_hosted_only() -> None:
    workflow = (ROOT / ".github/workflows/native-hip-dedicated.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "environment: native-hip-approved" in workflow
    assert "runs-on: [self-hosted, linux, x64, rocm, structural-approved]" in workflow
    assert "STRUCTURAL_ENABLE_HIP=ON" in workflow
    assert "--require-approved-runner" in workflow
    assert "structural_sparse_linear_hip_parity_tests" in workflow
    assert "check_native_sparse_linear_hip.py" in workflow
    assert "native-sparse-linear-hip-receipt.json" in workflow
    assert "structural_generalized_eigen_hip_parity_tests" in workflow
    assert "check_native_generalized_eigen_hip.py" in workflow
    assert "native-generalized-eigen-hip-receipt.json" in workflow
    assert "structural_nonlinear_static_hip_parity_tests" in workflow
    assert "check_native_nonlinear_static_hip.py" in workflow
    assert "native-nonlinear-static-hip-receipt.json" in workflow
    assert "structural_nonlinear_ndtha_hip_parity_tests" in workflow
    assert "check_native_nonlinear_ndtha_hip.py" in workflow
    assert "native-nonlinear-ndtha-hip-receipt.json" in workflow
    assert "structural_reference_elements_hip_parity_tests" in workflow
