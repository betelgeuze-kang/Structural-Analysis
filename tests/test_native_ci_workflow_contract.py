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


def test_abi_lane_builds_every_executable_selected_by_its_ctest_label() -> None:
    pr_fast = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    abi_contract = pr_fast.split("  abi-contract:\n", 1)[1].split(
        "\n  modelir-golden:", 1
    )[0]
    for target in (
        "structural_abi_header_c11_smoke",
        "structural_abi_header_cpp20_smoke",
        "structural_abi_contract_tests",
        "structural_abi_link_smoke_c",
        "structural_model_ir_contract_tests",
    ):
        assert target in abi_contract
    assert "ctest --test-dir build/native-abi --output-on-failure -L abi" in (
        abi_contract
    )


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


def test_native_nightly_requires_sanitizer_fuzz_and_license_policy() -> None:
    nightly = (ROOT / ".github/workflows/native-nightly-quality.yml").read_text(
        encoding="utf-8"
    )

    assert "STRUCTURAL_ENABLE_SANITIZERS=ON" in nightly
    assert "STRUCTURAL_BUILD_FUZZERS=ON" in nightly
    assert "structural_native_fuzzers" in nightly
    assert "check_native_dependency_licenses.py" in nightly


def test_native_rust_gate_checks_the_declared_minimum_toolchain() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    assert "rustup toolchain install 1.77.0 --profile minimal" in workflow
    assert "cargo +1.77.0 check" in workflow
    assert "--workspace --all-targets --locked" in workflow


def test_modelir_gate_separates_component_promotion_from_aggregate_slice() -> None:
    workflow = (ROOT / ".github/workflows/native-pr-fast.yml").read_text(
        encoding="utf-8"
    )

    assert "--is-enabled modelir_v2_rust_wire" in workflow
    assert "--is-enabled modelir_v2_cpp_core; then" in workflow
    assert "--no-tests=error -L modelir" in workflow
