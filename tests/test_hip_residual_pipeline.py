"""Generated fixed-operator sequence contracts, with explicit optional native integration."""

import importlib.util
import ctypes as ct
import os
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "residual_pipeline",
    Path(__file__).resolve().parents[1] / "scripts/benchmark_hip_residual_pipeline.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_sequence_reference_is_explicit_state_evolution_and_final_residual():
    case = MODULE.BASE.generated_case(24, 2)
    initial = case["arrays"]["states"].copy()
    state, residual = MODULE.reference(case, 3, 0.05)
    expected = initial.copy()
    dense = case["operator"].toarray()
    for _ in range(3):
        expected -= 0.05 * (expected @ dense.T - case["arrays"]["external"])
    np.testing.assert_allclose(state, expected, rtol=1e-14, atol=1e-16)
    np.testing.assert_allclose(
        residual,
        expected @ dense.T - case["arrays"]["external"],
        rtol=1e-14,
        atol=1e-16,
    )
    assert np.array_equal(initial, case["arrays"]["states"])


@pytest.mark.parametrize(
    "dimensions,batches,steps,workers",
    [
        ([13], [1], [8], [1]),
        ([24], [0], [8], [1]),
        ([24], [1], [129], [1]),
        ([24], [1], [8], [2]),
        ([24, 24], [1], [8], [1]),
        ([24], [1], [8], [1, 13]),
    ],
)
def test_sequence_bounds(dimensions, batches, steps, workers):
    with pytest.raises(ValueError):
        MODULE.validate_scope(dimensions, batches, steps, workers)


def test_parity_checks_both_state_and_residual():
    expected = (np.zeros((2, 3)), np.zeros((2, 3)))
    assert MODULE.check_outputs(*expected, expected) == [0.0, 0.0]
    with pytest.raises(ValueError, match="parity"):
        MODULE.check_outputs(expected[0], np.ones((2, 3)), expected)


@pytest.mark.skipif(
    not os.environ.get("STRUCTURAL_HIP_PIPELINE_TEST_DIR"),
    reason="explicit compiled CPU/HIP integration library directory required",
)
def test_actual_cpu_and_two_gpu_sequences_match_the_same_reference():
    directory = Path(os.environ["STRUCTURAL_HIP_PIPELINE_TEST_DIR"])
    gpu = MODULE.HipSequence(directory / "libfixed_sequence_hip.so")
    result = MODULE.compare_case(
        directory / "libfixed_sequence_cpu.so", gpu, 24, 2, 3, 0.05, [1, 2], 0, 3, True
    )
    assert set(result["methods"]) == {
        "cpu_openmp_1",
        "cpu_openmp_2",
        "gpu_host_roundtrip",
        "gpu_resident_sequence",
    }
    assert all(value["parity"]["pass"] for value in result["methods"].values())
    assert result["methods"]["cpu_openmp_2"]["observed_workers"] == [2]
    assert result["transfer_contract"]["resident_h2d_calls"] == 1
    assert result["transfer_contract"]["host_roundtrip_h2d_calls"] == 4
    assert "best_cpu_time_over_resident_gpu_time" not in result


@pytest.mark.skipif(
    not os.environ.get("STRUCTURAL_HIP_PIPELINE_TEST_DIR"),
    reason="explicit compiled CPU/HIP integration library directory required",
)
def test_native_sequence_alias_rejection_preserves_inputs():
    directory = Path(os.environ["STRUCTURAL_HIP_PIPELINE_TEST_DIR"])
    gpu = MODULE.HipSequence(directory / "libfixed_sequence_hip.so")
    case = MODULE.BASE.generated_case(24, 2)
    initial = case["arrays"]["states"]
    before = initial.tobytes()
    residual = np.empty_like(initial)
    phases = np.full(6, -99.0)
    handle, _ = gpu.create(case)
    try:
        code = gpu.lib.structural_hip_fixed_residual_sequence_v1(
            handle,
            initial.ctypes.data,
            2,
            3,
            0.05,
            initial.ctypes.data,
            residual.ctypes.data,
            phases.ctypes.data,
        )
        assert code != 0 and initial.tobytes() == before
        assert np.array_equal(phases, np.full(6, -99.0))
    finally:
        gpu.checked(gpu.lib.mgt_hip_full_residual_destroy(handle))
    cpu = MODULE.CpuOperator(directory / "libfixed_sequence_cpu.so", case)
    try:
        observed = ct.c_int(-99)
        code = cpu.lib.structural_cpu_fixed_residual_sequence_v1(
            cpu.handle,
            initial.ctypes.data,
            2,
            3,
            2,
            0.05,
            initial.ctypes.data,
            residual.ctypes.data,
            ct.byref(observed),
        )
        assert code != 0 and initial.tobytes() == before and observed.value == -99
    finally:
        cpu.close()


@pytest.fixture(scope="module")
def cpu_create_library():
    path = os.environ.get("STRUCTURAL_CPU_PIPELINE_TEST_LIBRARY")
    if not path:
        directory = os.environ.get("STRUCTURAL_HIP_PIPELINE_TEST_DIR")
        if directory:
            path = str(Path(directory) / "libfixed_sequence_cpu.so")
    if not path:
        pytest.skip("explicit compiled CPU sequence library required")
    library = ct.CDLL(str(Path(path).resolve(strict=True)))
    pointer = ct.c_void_p
    library.structural_cpu_fixed_operator_create_v1.argtypes = [
        ct.c_size_t,
        ct.c_size_t,
        pointer,
        pointer,
        pointer,
        pointer,
        ct.POINTER(pointer),
    ]
    library.structural_cpu_fixed_operator_create_v1.restype = ct.c_int
    library.structural_cpu_fixed_operator_destroy_v1.argtypes = [pointer]
    library.structural_cpu_fixed_operator_destroy_v1.restype = ct.c_int
    return library


def cpu_create_inputs():
    case = MODULE.BASE.generated_case(24, 1)
    operator = case["operator"]
    arrays = {
        "row": operator.indptr.astype(np.int64),
        "column": operator.indices.astype(np.int64),
        "value": operator.data.copy(),
        "external": case["arrays"]["external"].copy(),
    }
    return case["dimension"], operator.nnz, arrays


@pytest.mark.parametrize("target", ["row", "column", "value", "external"])
@pytest.mark.parametrize("offset", [0, 8])
def test_cpu_create_rejects_handle_alias_before_any_caller_memory_write(
    cpu_create_library, target, offset
):
    dimension, nnz, arrays = cpu_create_inputs()
    before = {name: array.tobytes() for name, array in arrays.items()}
    result = ct.cast(arrays[target].ctypes.data + offset, ct.POINTER(ct.c_void_p))
    code = cpu_create_library.structural_cpu_fixed_operator_create_v1(
        dimension,
        nnz,
        *(arrays[name].ctypes.data for name in ("row", "column", "value", "external")),
        result,
    )
    assert code != 0
    assert before == {name: array.tobytes() for name, array in arrays.items()}


def test_cpu_create_nonaliased_handle_keeps_success_and_failure_lifecycle(
    cpu_create_library,
):
    dimension, nnz, arrays = cpu_create_inputs()
    before = {name: array.tobytes() for name, array in arrays.items()}
    handle = ct.c_void_p()
    code = cpu_create_library.structural_cpu_fixed_operator_create_v1(
        dimension,
        nnz,
        *(arrays[name].ctypes.data for name in ("row", "column", "value", "external")),
        ct.byref(handle),
    )
    assert code == 0 and handle.value is not None
    assert cpu_create_library.structural_cpu_fixed_operator_destroy_v1(handle) == 0
    assert before == {name: array.tobytes() for name, array in arrays.items()}
    arrays["row"][0] = 1
    handle = ct.c_void_p(123)
    code = cpu_create_library.structural_cpu_fixed_operator_create_v1(
        dimension,
        nnz,
        *(arrays[name].ctypes.data for name in ("row", "column", "value", "external")),
        ct.byref(handle),
    )
    assert code != 0 and handle.value is None
