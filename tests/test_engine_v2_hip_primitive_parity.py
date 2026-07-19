from __future__ import annotations

from copy import deepcopy
import math

import pytest

from structural_analysis.engine_v2.cpu_fgmres import (
    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
)
from structural_analysis.engine_v2_backends.hip_primitive_parity import (
    HIP_PRIMITIVE_OPERATION_ORDER,
    HIP_PRIMITIVE_OUTPUT_VERSION,
    HIPPrimitiveParityError,
    build_engine_v2_cpu_hip_parity_reference,
    compare_hip_primitive_output,
    cpu_hip_primitive_reference,
)


def _hip_output() -> tuple[object, dict]:
    reference = build_engine_v2_cpu_hip_parity_reference()
    operations = cpu_hip_primitive_reference(reference.fixture)
    payload = {
        "schema_version": HIP_PRIMITIVE_OUTPUT_VERSION,
        "runtime_status": "success",
        "runtime_status_code": 0,
        "backend": "amd_rocm_hip",
        "cpu_backend": False,
        "same_stream_ordering": True,
        "blocking_d2h_synchronization_count": 1,
        "kernel_invocation_count": 6,
        "production_full_recurrence_claim": False,
        "preconditioner_profile": (
            "operator_derived_left_scaled_jacobi_right.v1"
        ),
        "reduction_profile": "single_thread_ascending_index_fp64_probe.v1",
        "device_index": 0,
        "device_name": "AMD Radeon RX 6900 XT",
        "gcn_arch_name": "gfx1030",
        "fixture_dimension": reference.fixture.dimension,
        "fixture_nnz": reference.fixture.nnz,
        "operations": operations,
    }
    return reference, payload


def test_fixture_binds_cpu_fgmres_reduced_csr_and_binary_bytes() -> None:
    first = build_engine_v2_cpu_hip_parity_reference()
    second = build_engine_v2_cpu_hip_parity_reference()
    fixture = first.fixture
    manifest = fixture.to_manifest()

    assert first.cpu_run.converged is True
    assert (
        first.cpu_run.preconditioner_profile
        == CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
    )
    assert first.cpu_run.run_hash == second.cpu_run.run_hash
    assert fixture.fixture_hash == second.fixture.fixture_hash
    assert fixture.execution_plan_hash == first.cpu_run.execution_plan_hash
    assert fixture.scaling_hash == first.cpu_run.scaling_hash
    assert fixture.reduced_csr_identity_hash == first.cpu_run.reduced_csr_identity_hash
    assert fixture.operator_numeric_values_hash == (
        first.cpu_run.operator_numeric_values_hash
    )
    assert fixture.to_bytes().startswith(b"EV2HIP01")
    assert manifest["dimension"] == first.cpu_run.free_count == 6
    assert manifest["nnz"] == 36
    assert manifest["preconditioner_profile"] == (
        CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
    )
    assert manifest["preconditioner_contract_hash"] == (
        fixture.preconditioner_contract_hash
    )
    assert all(not array.flags.writeable for array in (
        fixture.row_ptr,
        fixture.column_indices,
        fixture.values,
        fixture.x,
        fixture.y,
        fixture.scale_divisors,
        fixture.inverse_diagonal,
        fixture.solution,
        fixture.direction,
    ))


def test_cpu_primitive_reference_has_expected_semantics() -> None:
    reference = build_engine_v2_cpu_hip_parity_reference()
    operations = cpu_hip_primitive_reference(reference.fixture)

    assert tuple(operations) == HIP_PRIMITIVE_OPERATION_ORDER
    assert operations["spmv"] == pytest.approx([3.0, -6.5, 8.75, -0.25, -4.75, 6.75])
    assert operations["dot"] == pytest.approx(-2.125)
    assert operations["l2_norm"] == pytest.approx(math.sqrt(8.125))
    assert operations["linf_norm"] == pytest.approx(2.0)
    assert operations["preconditioner_apply"] == pytest.approx(
        [
            float(value * inverse)
            for value, inverse in zip(
                reference.fixture.x,
                reference.fixture.inverse_diagonal,
                strict=True,
            )
        ]
    )
    assert operations["axpy"] == pytest.approx(
        [-1.375, -0.75, 3.75, -0.1875, 1.0625, 0.875]
    )
    assert operations["solution_update"] == pytest.approx(
        [-0.3, 0.4, -0.2, -0.4, 0.1, -0.05]
    )


def test_hip_primitive_output_passes_without_promoting_full_recurrence() -> None:
    reference, payload = _hip_output()

    comparison = compare_hip_primitive_output(reference.fixture, payload)

    assert comparison["contract_pass"] is True
    assert comparison["runtime_status_propagation_pass"] is True
    assert comparison["same_stream_ordering_pass"] is True
    assert comparison["cpu_fallback_absent"] is True
    assert comparison["maximum_absolute_error"] == 0.0
    assert comparison[
        "operator_derived_scaled_jacobi_apply_probe_claim"
    ] is True
    assert comparison["full_recurrence_parity_claim"] is False
    assert comparison["performance_claim"] is False


def test_hip_primitive_output_allows_only_bounded_fp64_difference() -> None:
    reference, payload = _hip_output()
    payload["operations"]["dot"] += 5.0e-13

    comparison = compare_hip_primitive_output(reference.fixture, payload)

    assert comparison["contract_pass"] is True
    assert comparison["maximum_absolute_error"] == pytest.approx(5.0e-13)


def test_hip_primitive_output_rejects_numerical_drift() -> None:
    reference, payload = _hip_output()
    payload["operations"]["spmv"][2] += 1.0e-6

    comparison = compare_hip_primitive_output(reference.fixture, payload)

    assert comparison["contract_pass"] is False
    row = next(
        item for item in comparison["operation_rows"] if item["operation"] == "spmv"
    )
    assert row["contract_pass"] is False


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("runtime_status",), "error", "hip_output_runtime_contract_invalid"),
        (("cpu_backend",), True, "hip_output_runtime_contract_invalid"),
        (("same_stream_ordering",), False, "hip_output_runtime_contract_invalid"),
        (("gcn_arch_name",), "cpu", "hip_output_arch_invalid"),
        (("kernel_invocation_count",), 5, "hip_output_kernel_count_invalid"),
        (("blocking_d2h_synchronization_count",), 2, "hip_output_sync_contract_invalid"),
    ],
)
def test_hip_primitive_output_fails_closed_on_runtime_contract_drift(
    path: tuple[str, ...],
    value: object,
    code: str,
) -> None:
    reference, original = _hip_output()
    payload = deepcopy(original)
    payload[path[0]] = value

    with pytest.raises(HIPPrimitiveParityError) as caught:
        compare_hip_primitive_output(reference.fixture, payload)

    assert caught.value.code == code


def test_hip_primitive_output_rejects_operation_set_drift() -> None:
    reference, payload = _hip_output()
    del payload["operations"]["dot"]
    payload["operations"]["unknown"] = 0.0

    with pytest.raises(HIPPrimitiveParityError) as caught:
        compare_hip_primitive_output(reference.fixture, payload)

    assert caught.value.code == "hip_output_operation_set_invalid"
