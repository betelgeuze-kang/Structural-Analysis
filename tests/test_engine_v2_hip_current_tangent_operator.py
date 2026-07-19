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

from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
    HIP_CURRENT_TANGENT_BINARY_MAGIC,
    HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
    HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_OUTPUT_VERSION,
    HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_PROFILE,
    HIP_CURRENT_TANGENT_FIXTURE_VERSION,
    HIP_CURRENT_TANGENT_OUTPUT_VERSION,
    HIPCurrentTangentOperatorError,
    build_hip_current_tangent_operator_reference,
    compare_hip_current_tangent_operator_output,
    create_hip_current_tangent_operator_reference,
    validate_hip_current_tangent_fixture_parser_output,
    validate_hip_current_tangent_operator_fixture,
)


def _runtime_output() -> dict[str, object]:
    reference = build_hip_current_tangent_operator_reference()
    fixture = reference.fixture
    return {
        "schema_version": HIP_CURRENT_TANGENT_OUTPUT_VERSION,
        "status": "ok",
        "cpu_backend": False,
        "device_name": "synthetic-test-device",
        "gcn_arch_name": "gfx-test",
        "execution_profile": HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
        "accumulation_profile": HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
        "equation_count": fixture.equation_count,
        "kernel_invocation_count": fixture.expected_kernel_invocation_count,
        "mid_action_d2h_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
        "action_n_per_m": reference.device_order_action_n_per_m.tolist(),
    }


def _parser_output() -> dict[str, object]:
    fixture = build_hip_current_tangent_operator_reference().fixture
    return {
        "schema_version": (
            HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_OUTPUT_VERSION
        ),
        "status": "ok",
        "mode": "host_fixture_validation_only",
        "actual_hardware": False,
        "hip_runtime_api_call_count": 0,
        "equation_count": fixture.equation_count,
        "global_dof_count": fixture.global_dof_count,
        "reference_nnz": fixture.operator.reference_nnz,
        "frame_element_count": fixture.operator.frame_element_count,
        "geometry_element_count": fixture.operator.geometry_element_count,
        "frame_incidence_count": fixture.frame_incidence_count,
        "geometry_incidence_count": fixture.geometry_incidence_count,
        "expected_kernel_invocation_count": (
            fixture.expected_kernel_invocation_count
        ),
        "fixture_byte_length": len(fixture.to_bytes()),
    }


def test_fixture_binds_operator_schedules_inputs_and_binary_bytes() -> None:
    reference = build_hip_current_tangent_operator_reference()
    fixture = validate_hip_current_tangent_operator_fixture(reference.fixture)
    manifest = fixture.to_manifest()

    assert fixture.schema_version == HIP_CURRENT_TANGENT_FIXTURE_VERSION
    assert fixture.equation_count == 5
    assert fixture.global_dof_count == 12
    assert fixture.operator.reference_nnz == 15
    assert fixture.operator.frame_element_count == 1
    assert fixture.operator.geometry_element_count == 1
    assert fixture.frame_incidence_pointer.tolist() == [0, 1, 2, 3, 4, 5]
    assert fixture.geometry_incidence_pointer.tolist() == [0, 1, 2, 3, 4, 5]
    assert fixture.frame_incidence_element.tolist() == [0] * 5
    assert fixture.geometry_incidence_element.tolist() == [0] * 5
    assert fixture.frame_incidence_local_dof.tolist() == [0, 1, 2, 6, 7]
    assert fixture.geometry_incidence_local_dof.tolist() == [0, 1, 2, 6, 7]
    assert fixture.expected_kernel_invocation_count == 1
    assert fixture.to_bytes().startswith(HIP_CURRENT_TANGENT_BINARY_MAGIC)
    assert manifest["operator_contract_hash"] == fixture.operator.contract_hash
    assert manifest["schedule_contract_hash"] == fixture.schedule_contract_hash
    assert manifest["fixture_hash"] == fixture.fixture_hash
    assert manifest["execution_contract_hash"] == (
        fixture.execution_contract_hash
    )
    assert manifest["arrays"]["free_displacements_m"]["shape"] == [5]
    np.testing.assert_allclose(
        reference.device_order_action_n_per_m,
        reference.canonical_action_n_per_m,
        rtol=1.0e-12,
        atol=1.0e-6,
    )


def test_runtime_output_matches_both_cpu_references() -> None:
    reference = build_hip_current_tangent_operator_reference()

    comparison = compare_hip_current_tangent_operator_output(
        reference,
        _runtime_output(),
    )

    assert comparison["contract_pass"] is True
    assert comparison["canonical_cpu_max_abs_error_n_per_m"] <= comparison[
        "comparison_tolerance_n_per_m"
    ]
    assert comparison["device_order_cpu_max_abs_error_n_per_m"] == 0.0
    assert comparison["actual_hardware_execution_required_for_claim"] is True
    assert comparison["actual_mgt_scale_claim"] is False
    assert comparison["production_performance_claim"] is False


def test_arbitrary_fixture_reference_matches_synthetic_builder() -> None:
    expected = build_hip_current_tangent_operator_reference()

    actual = create_hip_current_tangent_operator_reference(expected.fixture)

    assert actual.fixture is expected.fixture
    np.testing.assert_array_equal(
        actual.canonical_action_n_per_m,
        expected.canonical_action_n_per_m,
    )
    np.testing.assert_array_equal(
        actual.device_order_action_n_per_m,
        expected.device_order_action_n_per_m,
    )


def test_runtime_output_rejects_metadata_forgery() -> None:
    reference = build_hip_current_tangent_operator_reference()
    runtime = _runtime_output()
    runtime["kernel_invocation_count"] = 2

    with pytest.raises(
        HIPCurrentTangentOperatorError,
        match="hip_current_tangent_output_semantics_invalid",
    ):
        compare_hip_current_tangent_operator_output(reference, runtime)


def test_runtime_output_exposes_numerical_failure() -> None:
    reference = build_hip_current_tangent_operator_reference()
    runtime = _runtime_output()
    action = list(runtime["action_n_per_m"])
    action[2] += 1.0e3
    runtime["action_n_per_m"] = action

    comparison = compare_hip_current_tangent_operator_output(
        reference,
        runtime,
    )

    assert comparison["contract_pass"] is False
    assert comparison["canonical_cpu_max_abs_error_n_per_m"] > 100.0


def test_host_fixture_parser_output_is_strictly_bounded() -> None:
    fixture = build_hip_current_tangent_operator_reference().fixture

    comparison = validate_hip_current_tangent_fixture_parser_output(
        fixture,
        _parser_output(),
    )

    assert comparison["profile"] == (
        HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_PROFILE
    )
    assert comparison["contract_pass"] is True
    assert comparison["fixture_hash"] == fixture.fixture_hash
    assert comparison["equation_count"] == 5
    assert comparison["fixture_byte_length"] == len(fixture.to_bytes())
    assert comparison["actual_hardware_execution"] is False
    assert comparison["hip_runtime_api_call_count"] == 0


def test_host_fixture_parser_rejects_hardware_forgery() -> None:
    fixture = build_hip_current_tangent_operator_reference().fixture
    output = _parser_output()
    output["actual_hardware"] = True

    with pytest.raises(
        HIPCurrentTangentOperatorError,
        match="hip_current_tangent_parser_output_semantics_invalid",
    ):
        validate_hip_current_tangent_fixture_parser_output(fixture, output)


def test_fixture_rejects_stale_schedule_hash() -> None:
    fixture = build_hip_current_tangent_operator_reference().fixture
    stale = replace(fixture, schedule_contract_hash="sha256:" + "0" * 64)

    with pytest.raises(
        HIPCurrentTangentOperatorError,
        match="hip_current_tangent_schedule_hash_mismatch",
    ):
        validate_hip_current_tangent_operator_fixture(stale)
