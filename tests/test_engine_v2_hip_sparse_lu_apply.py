from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import (  # noqa: E402
    HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE,
    HIP_SPARSE_LU_APPLY_BINARY_MAGIC,
    HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
    HIP_SPARSE_LU_APPLY_FIXTURE_VERSION,
    HIP_SPARSE_LU_APPLY_OUTPUT_VERSION,
    HIP_SPARSE_LU_FIXTURE_VALIDATION_OUTPUT_VERSION,
    HIP_SPARSE_LU_FIXTURE_VALIDATION_PROFILE,
    HIPSparseLUApplyParityError,
    build_hip_sparse_lu_apply_reference,
    compare_hip_sparse_lu_apply_output,
    validate_hip_sparse_lu_apply_fixture,
    validate_hip_sparse_lu_fixture_parser_output,
)


def _runtime_output() -> dict[str, object]:
    reference = build_hip_sparse_lu_apply_reference()
    fixture = reference.fixture
    return {
        "schema_version": HIP_SPARSE_LU_APPLY_OUTPUT_VERSION,
        "status": "ok",
        "cpu_backend": False,
        "device_name": "synthetic-test-device",
        "gcn_arch_name": "gfx-test",
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


def _parser_output() -> dict[str, object]:
    fixture = build_hip_sparse_lu_apply_reference().fixture
    return {
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


def test_sparse_lu_fixture_binds_factor_levels_and_binary_bytes() -> None:
    reference = build_hip_sparse_lu_apply_reference()
    fixture = validate_hip_sparse_lu_apply_fixture(reference.fixture)
    manifest = fixture.to_manifest()

    assert fixture.schema_version == HIP_SPARSE_LU_APPLY_FIXTURE_VERSION
    assert fixture.dimension == 8
    assert fixture.factor.lower_numeric_values.size == 19
    assert fixture.factor.upper_numeric_values.size == 19
    assert fixture.lower_level_pointer.tolist() == [0, 1, 3, 5, 6, 7, 8]
    assert fixture.lower_level_rows.tolist() == list(range(8))
    assert fixture.upper_level_pointer.tolist() == [0, 1, 2, 3, 5, 7, 8]
    assert fixture.upper_level_rows.tolist() == [7, 6, 5, 3, 4, 1, 2, 0]
    assert fixture.lower_level_count == 6
    assert fixture.upper_level_count == 6
    assert fixture.expected_kernel_invocation_count == 14
    assert fixture.to_bytes().startswith(HIP_SPARSE_LU_APPLY_BINARY_MAGIC)
    assert manifest["factor_contract_hash"] == fixture.factor.contract_hash
    assert manifest["schedule_contract_hash"] == fixture.schedule_contract_hash
    assert manifest["fixture_hash"] == fixture.fixture_hash
    assert manifest["preconditioner_contract_hash"] == (
        fixture.preconditioner_contract_hash
    )
    assert manifest["arrays"]["right_hand_side_kn"]["shape"] == [8]
    np.testing.assert_allclose(
        reference.device_order_solution_m,
        reference.canonical_solution_m,
        rtol=1.0e-15,
        atol=1.0e-12,
    )


def test_sparse_lu_runtime_output_matches_both_cpu_references() -> None:
    reference = build_hip_sparse_lu_apply_reference()

    comparison = compare_hip_sparse_lu_apply_output(
        reference,
        _runtime_output(),
    )

    assert comparison["contract_pass"] is True
    assert comparison["canonical_cpu_max_abs_error_m"] <= 1.0e-11
    assert comparison["device_order_cpu_max_abs_error_m"] == 0.0
    assert comparison["actual_hardware_execution_required_for_claim"] is True
    assert comparison["production_performance_claim"] is False


def test_sparse_lu_runtime_output_rejects_metadata_forgery() -> None:
    reference = build_hip_sparse_lu_apply_reference()
    runtime = _runtime_output()
    runtime["kernel_invocation_count"] = 13

    with pytest.raises(
        HIPSparseLUApplyParityError,
        match="hip_sparse_lu_output_semantics_invalid",
    ):
        compare_hip_sparse_lu_apply_output(reference, runtime)


def test_sparse_lu_runtime_output_exposes_numerical_failure() -> None:
    reference = build_hip_sparse_lu_apply_reference()
    runtime = _runtime_output()
    solution = list(runtime["solution_m"])
    solution[4] += 1.0e-4
    runtime["solution_m"] = solution

    comparison = compare_hip_sparse_lu_apply_output(reference, runtime)

    assert comparison["contract_pass"] is False
    assert comparison["canonical_cpu_max_abs_error_m"] > 1.0e-5


def test_sparse_lu_host_fixture_parser_output_is_strictly_bounded() -> None:
    fixture = build_hip_sparse_lu_apply_reference().fixture

    comparison = validate_hip_sparse_lu_fixture_parser_output(
        fixture,
        _parser_output(),
    )

    assert comparison["profile"] == HIP_SPARSE_LU_FIXTURE_VALIDATION_PROFILE
    assert comparison["contract_pass"] is True
    assert comparison["fixture_hash"] == fixture.fixture_hash
    assert comparison["dimension"] == 8
    assert comparison["fixture_byte_length"] == len(fixture.to_bytes())
    assert comparison["actual_hardware_execution"] is False
    assert comparison["hip_runtime_api_call_count"] == 0


def test_sparse_lu_host_fixture_parser_rejects_hardware_forgery() -> None:
    fixture = build_hip_sparse_lu_apply_reference().fixture
    output = _parser_output()
    output["actual_hardware"] = True

    with pytest.raises(
        HIPSparseLUApplyParityError,
        match="hip_sparse_lu_parser_output_semantics_invalid",
    ):
        validate_hip_sparse_lu_fixture_parser_output(fixture, output)


def test_sparse_lu_fixture_rejects_stale_schedule_hash() -> None:
    fixture = build_hip_sparse_lu_apply_reference().fixture
    stale = replace(fixture, schedule_contract_hash="sha256:" + "0" * 64)

    with pytest.raises(
        HIPSparseLUApplyParityError,
        match="hip_sparse_lu_schedule_hash_mismatch",
    ):
        validate_hip_sparse_lu_apply_fixture(stale)
