from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import (  # noqa: E402
    HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE,
    HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
    HIP_SPARSE_LU_APPLY_OUTPUT_VERSION,
    HIP_SPARSE_LU_FIXTURE_VALIDATION_OUTPUT_VERSION,
    build_hip_sparse_lu_apply_reference,
    validate_hip_sparse_lu_fixture_parser_output,
)


def _load_runner():
    path = ROOT / "scripts/run_engine_v2_hip_sparse_lu_apply.py"
    spec = importlib.util.spec_from_file_location("hip_sparse_lu_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runner import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_output() -> dict[str, object]:
    reference = build_hip_sparse_lu_apply_reference()
    fixture = reference.fixture
    return {
        "schema_version": HIP_SPARSE_LU_APPLY_OUTPUT_VERSION,
        "status": "ok",
        "cpu_backend": False,
        "device_name": "AMD Radeon test fixture",
        "gcn_arch_name": "gfx1030",
        "execution_profile": HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
        "accumulation_profile": HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE,
        "dimension": fixture.dimension,
        "lower_level_count": fixture.lower_level_count,
        "upper_level_count": fixture.upper_level_count,
        "kernel_invocation_count": fixture.expected_kernel_invocation_count,
        "mid_apply_d2h_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
        "solution_m": reference.device_order_solution_m.tolist(),
    }


def _host_fixture_validation() -> dict[str, object]:
    fixture = build_hip_sparse_lu_apply_reference().fixture
    output = {
        "schema_version": HIP_SPARSE_LU_FIXTURE_VALIDATION_OUTPUT_VERSION,
        "status": "ok",
        "mode": "host_fixture_validation_only",
        "actual_hardware": False,
        "hip_runtime_api_call_count": 0,
        "dimension": fixture.dimension,
        "lower_nnz": int(fixture.factor.lower_numeric_values.size),
        "upper_nnz": int(fixture.factor.upper_numeric_values.size),
        "lower_level_count": fixture.lower_level_count,
        "upper_level_count": fixture.upper_level_count,
        "expected_kernel_invocation_count": (
            fixture.expected_kernel_invocation_count
        ),
        "fixture_byte_length": len(fixture.to_bytes()),
    }
    return validate_hip_sparse_lu_fixture_parser_output(fixture, output)


def test_runner_builds_source_bound_partial_receipt() -> None:
    runner = _load_runner()

    receipt = runner.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        binary_sha256="sha256:" + "a" * 64,
    )

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["hardware_execution"]["actual_hardware"] is True
    assert receipt["comparison"]["contract_pass"] is True
    assert receipt["claims"]["gfx1030_local_sparse_lu_apply"] is True
    assert receipt["claims"]["gfx1100_independent_sparse_lu_apply"] is False
    assert receipt["claims"]["actual_mgt_factor_apply"] is False
    assert receipt["claims"]["production_scale_factor_apply"] is False
    assert receipt["claims"]["production_current_tangent_fgmres"] is False
    assert receipt["claims"]["performance"] is False
    assert runner.validate_receipt(receipt, repo_root=ROOT) == receipt


def test_runner_rejects_stale_receipt_hash() -> None:
    runner = _load_runner()
    receipt = runner.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        binary_sha256="sha256:" + "b" * 64,
    )
    receipt["receipt_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        runner.validate_receipt(receipt, repo_root=ROOT)


def test_runner_builds_dual_target_compile_only_receipt() -> None:
    runner = _load_runner()

    receipt = runner.build_compile_receipt(
        repo_root=ROOT,
        compiler_path="/opt/rocm-6.0.2/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        targets=[
            {
                "architecture": "gfx1100",
                "target_compile": True,
                "binary_sha256": "sha256:" + "d" * 64,
                "binary_byte_length": 57_112,
                "host_fixture_parser_execution": True,
                "host_fixture_validation": _host_fixture_validation(),
            },
            {
                "architecture": "gfx1030",
                "target_compile": True,
                "binary_sha256": "sha256:" + "c" * 64,
                "binary_byte_length": 56_824,
                "host_fixture_parser_execution": True,
                "host_fixture_validation": _host_fixture_validation(),
            },
        ],
    )

    assert receipt["contract_scope"] == (
        "target_compile_and_host_fixture_parser_only"
    )
    assert [row["architecture"] for row in receipt["targets"]] == [
        "gfx1030",
        "gfx1100",
    ]
    assert receipt["claims"]["gfx1030_target_compile"] is True
    assert receipt["claims"]["gfx1100_target_compile"] is True
    assert receipt["claims"][
        "dual_target_host_fixture_parser_execution"
    ] is True
    assert all(
        row["host_fixture_parser_execution"] is True
        and row["host_fixture_validation"]["contract_pass"] is True
        and row["host_fixture_validation"]["actual_hardware_execution"]
        is False
        for row in receipt["targets"]
    )
    assert receipt["claims"]["actual_hardware_execution"] is False
    assert receipt["claims"]["numerical_parity"] is False
    assert receipt["claims"]["actual_mgt_factor_apply"] is False
    assert receipt["claims"]["production_scale_factor_apply"] is False
    assert receipt["claims"]["production_current_tangent_fgmres"] is False
    assert receipt["claims"]["performance"] is False
    assert runner.validate_compile_receipt(receipt, repo_root=ROOT) == receipt


def test_runner_compile_receipt_rejects_duplicate_target() -> None:
    runner = _load_runner()
    target = {
        "architecture": "gfx1030",
        "target_compile": True,
        "binary_sha256": "sha256:" + "e" * 64,
        "binary_byte_length": 56_824,
        "host_fixture_parser_execution": True,
        "host_fixture_validation": _host_fixture_validation(),
    }

    with pytest.raises(ValueError, match="compile_targets_invalid"):
        runner.build_compile_receipt(
            repo_root=ROOT,
            compiler_path="/opt/rocm-6.0.2/bin/hipcc",
            compiler_version_output="HIP version: synthetic-test\n",
            targets=[target, dict(target)],
        )


def test_runner_schema_and_kernel_source_contract_are_present() -> None:
    runner = _load_runner()
    schema = json.loads((ROOT / runner.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    compile_schema = json.loads(
        (ROOT / runner.COMPILE_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(compile_schema)
    source = (ROOT / runner.SOURCE_PATH).read_text(encoding="utf-8")

    for token in (
        "permute_rhs_kernel",
        "lower_level_kernel",
        "upper_level_kernel",
        "column_permutation_kernel",
        "hipMemcpyAsync_d2h",
        "hipStreamSynchronize",
        "--validate-fixture-only",
        "hip_runtime_api_call_count",
        "-ffp-contract=off",
    ):
        if token == "-ffp-contract=off":
            assert token in (ROOT / runner.__file__).read_text(encoding="utf-8")
        else:
            assert token in source


def test_runner_check_fails_closed_when_receipt_is_missing(tmp_path: Path) -> None:
    runner = _load_runner()
    missing = tmp_path / "missing-receipt.json"

    passed, reason = runner.check_committed_receipt(
        repo_root=ROOT,
        out=missing,
    )

    assert passed is False
    assert reason.startswith("engine_v2_hip_sparse_lu_receipt_missing:")
