"""Optional preassembled-CSR HIP contracts for a fixed linear sequence only.

The explicit integration directory supplies an already built library. These
tests neither build native code nor admit an RC/material/physical solver claim.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import ctypes as ct
import importlib.util
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location(
    "csr_residual_pipeline_contracts",
    Path(__file__).resolve().parents[1] / "scripts/benchmark_hip_residual_pipeline.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CSR_NAMES = ("row", "column", "value", "external")
EVAL_NAMES = ("initial", "state", "residual", "phase")
ALIAS_PAIRS = (
    ("initial", "state"),
    ("initial", "residual"),
    ("initial", "phase"),
    ("state", "residual"),
    ("state", "phase"),
    ("residual", "phase"),
)


@pytest.fixture(scope="module")
def gpu():
    directory = os.environ.get("STRUCTURAL_HIP_PIPELINE_TEST_DIR")
    if not directory:
        pytest.skip("explicit compiled HIP pipeline library directory required")
    result = MODULE.HipCsrSequence(Path(directory) / "libfixed_sequence_hip.so")
    pointer = ct.c_void_p
    result.lib.structural_hip_csr_residual_last_error_v1.argtypes = []
    result.lib.structural_hip_csr_residual_last_error_v1.restype = ct.c_char_p
    result.lib.structural_hip_csr_residual_create_v1.argtypes = [
        ct.c_longlong,
        ct.c_longlong,
        pointer,
        pointer,
        pointer,
        pointer,
        ct.POINTER(pointer),
    ]
    result.lib.structural_hip_csr_residual_create_v1.restype = ct.c_int
    result.lib.structural_hip_csr_residual_evaluate_v1.argtypes = [
        pointer,
        pointer,
        ct.c_longlong,
        ct.c_int,
        ct.c_double,
        pointer,
        pointer,
        pointer,
    ]
    result.lib.structural_hip_csr_residual_evaluate_v1.restype = ct.c_int
    result.lib.structural_hip_csr_residual_destroy_v1.argtypes = [pointer]
    result.lib.structural_hip_csr_residual_destroy_v1.restype = ct.c_int
    return result


def case(batch=2):
    return MODULE.BASE.generated_case(24, batch)


def snapshots(arrays):
    return {name: value.tobytes() for name, value in arrays.items()}


def raw_create(gpu, model, arrays, *, n=None, nnz=None, addresses=None, output=None):
    if addresses is None:
        addresses = {name: arrays[name].ctypes.data for name in CSR_NAMES}
    if output is None:
        output = ct.c_void_p()
    code = gpu.lib.structural_hip_csr_residual_create_v1(
        model["dimension"] if n is None else n,
        arrays["value"].size if nnz is None else nnz,
        *(addresses[name] for name in CSR_NAMES),
        ct.byref(output),
    )
    return code, output


@contextmanager
def live_handle(gpu, model):
    handle, setup_ms = gpu.create(model)
    assert handle.value is not None
    assert np.isfinite(setup_ms) and setup_ms >= 0.0
    try:
        yield handle
    finally:
        gpu.close(handle)


def evaluation_arrays(model):
    initial = model["arrays"]["states"].copy()
    return {
        "initial": initial,
        "state": np.full_like(initial, -71.0),
        "residual": np.full_like(initial, -83.0),
        "phase": np.full(6, -97.0, dtype=np.float64),
    }


def raw_evaluate(
    gpu, handle, model, arrays, *, batch=None, steps=2, omega=0.05, addresses=None
):
    if addresses is None:
        addresses = {name: arrays[name].ctypes.data for name in EVAL_NAMES}
    return gpu.lib.structural_hip_csr_residual_evaluate_v1(
        handle,
        addresses["initial"],
        model["batch"] if batch is None else batch,
        steps,
        omega,
        addresses["state"],
        addresses["residual"],
        addresses["phase"],
    )


def assert_rejected_without_writes(gpu, handle, model, arrays, **arguments):
    before = snapshots(arrays)
    assert raw_evaluate(gpu, handle, model, arrays, **arguments) != 0
    assert snapshots(arrays) == before
    assert gpu.lib.structural_hip_csr_residual_last_error_v1()


def test_csr_array_adapter_preserves_order_values_and_current_source():
    model = case()
    before = {
        "row": model["operator"].indptr.tobytes(),
        "column": model["operator"].indices.tobytes(),
        "value": model["operator"].data.tobytes(),
        "external": model["arrays"]["external"].tobytes(),
    }
    arrays = MODULE.csr_arrays(model)
    assert set(arrays) == set(CSR_NAMES)
    for name, array in arrays.items():
        assert type(array) is np.ndarray
        assert array.flags.c_contiguous and array.flags.aligned
        expected_dtype = np.int64 if name in CSR_NAMES[:2] else np.float64
        assert array.dtype == np.dtype(expected_dtype)
    np.testing.assert_array_equal(arrays["row"], model["operator"].indptr)
    np.testing.assert_array_equal(arrays["column"], model["operator"].indices)
    np.testing.assert_array_equal(arrays["value"], model["operator"].data)
    np.testing.assert_array_equal(arrays["external"], model["arrays"]["external"])
    assert before == {
        "row": model["operator"].indptr.tobytes(),
        "column": model["operator"].indices.tobytes(),
        "value": model["operator"].data.tobytes(),
        "external": model["arrays"]["external"].tobytes(),
    }


@pytest.mark.parametrize("omega", [1.0e-12, 1.0])
def test_minimum_dimension_and_nnz_maximum_batch_and_valid_omega_endpoints(gpu, omega):
    model = MODULE.BASE.generated_case(12, 64)
    model["operator"] = MODULE.BASE.sparse.csr_matrix(
        (
            np.array([0.25], dtype=np.float64),
            np.array([0], dtype=np.int64),
            np.array([0, *([1] * 12)], dtype=np.int64),
        ),
        shape=(12, 12),
    )
    expected = MODULE.reference(model, 1, omega)
    with live_handle(gpu, model) as handle:
        state, residual = [np.empty_like(expected[0]) for _ in range(2)]
        gpu.resident(handle, model, 1, omega, state, residual)
        MODULE.check_outputs(state, residual, expected)


@pytest.mark.parametrize(
    "n,nnz", [(-1, 24), (0, 24), (11, 24), (196609, 24), (24, -1), (24, 0), (24, 769)]
)
def test_create_dimension_and_nnz_bounds_precede_input_reads(gpu, n, nnz):
    model = case()
    arrays = MODULE.csr_arrays(model)
    before = snapshots(arrays)
    code, handle = raw_create(gpu, model, arrays, n=n, nnz=nnz)
    assert code != 0 and handle.value is None
    assert snapshots(arrays) == before


@pytest.mark.parametrize(
    "damage",
    [
        "row_first",
        "row_last",
        "row_negative",
        "row_decreasing",
        "column_negative",
        "column_high",
        "value_nan",
        "value_inf",
        "value_negative_inf",
        "external_nan",
        "external_inf",
        "external_negative_inf",
    ],
)
def test_create_invalid_csr_or_nonfinite_operator_preserves_inputs(gpu, damage):
    model = case()
    arrays = {name: value.copy() for name, value in MODULE.csr_arrays(model).items()}
    if damage == "row_first":
        arrays["row"][0] = 1
    elif damage == "row_last":
        arrays["row"][-1] -= 1
    elif damage == "row_negative":
        arrays["row"][1] = -1
    elif damage == "row_decreasing":
        arrays["row"][1] = arrays["row"][2] + 1
    elif damage == "column_negative":
        arrays["column"][0] = -1
    elif damage == "column_high":
        arrays["column"][0] = model["dimension"]
    else:
        name, kind = damage.split("_", 1)
        arrays[name][0] = {"nan": np.nan, "inf": np.inf, "negative_inf": -np.inf}[kind]
    before = snapshots(arrays)
    code, handle = raw_create(gpu, model, arrays, output=ct.c_void_p(123))
    assert code != 0 and handle.value is None
    assert snapshots(arrays) == before
    assert gpu.lib.structural_hip_csr_residual_last_error_v1()


@pytest.mark.parametrize("target", CSR_NAMES)
@pytest.mark.parametrize("damage", ["null", "misaligned", "overflow"])
def test_create_pointer_admission_preserves_all_caller_arrays(gpu, target, damage):
    model = case()
    arrays = MODULE.csr_arrays(model)
    addresses = {name: arrays[name].ctypes.data for name in CSR_NAMES}
    addresses[target] = {
        "null": None,
        "misaligned": arrays[target].ctypes.data + 1,
        "overflow": ct.c_void_p(-8).value,
    }[damage]
    before = snapshots(arrays)
    code, handle = raw_create(gpu, model, arrays, addresses=addresses)
    assert code != 0 and handle.value is None
    assert snapshots(arrays) == before


@pytest.mark.parametrize("target", CSR_NAMES)
@pytest.mark.parametrize("offset", [0, 8])
def test_create_handle_slot_alias_is_rejected_before_failure_sentinel_write(
    gpu, target, offset
):
    model = case()
    arrays = MODULE.csr_arrays(model)
    before = snapshots(arrays)
    output = ct.cast(arrays[target].ctypes.data + offset, ct.POINTER(ct.c_void_p))
    code = gpu.lib.structural_hip_csr_residual_create_v1(
        model["dimension"],
        arrays["value"].size,
        *(arrays[name].ctypes.data for name in CSR_NAMES),
        output,
    )
    assert code != 0 and snapshots(arrays) == before


@pytest.mark.parametrize(
    "first,second",
    [
        ("row", "column"),
        ("row", "value"),
        ("row", "external"),
        ("column", "value"),
        ("column", "external"),
        ("value", "external"),
    ],
)
@pytest.mark.parametrize("offset", [0, 8])
def test_all_six_create_input_alias_pairs_precede_reads_and_handle_slot_write(
    gpu, first, second, offset
):
    model = case()
    arrays = MODULE.csr_arrays(model)
    addresses = {name: arrays[name].ctypes.data for name in CSR_NAMES}
    addresses[second] = addresses[first] + offset
    before = snapshots(arrays)
    code, handle = raw_create(
        gpu, model, arrays, addresses=addresses, output=ct.c_void_p(123)
    )
    assert code != 0 and handle.value == 123
    assert snapshots(arrays) == before


@pytest.mark.parametrize("damage", ["null", "misaligned", "overflow"])
def test_create_handle_slot_itself_is_admitted_before_writing(gpu, damage):
    model = case()
    arrays = MODULE.csr_arrays(model)
    storage = np.full(24, 0xA5, dtype=np.uint8)
    address = {
        "null": None,
        "misaligned": storage.ctypes.data + 1,
        "overflow": ct.c_void_p(-8).value,
    }[damage]
    before = snapshots(arrays), storage.tobytes()
    output = None if address is None else ct.cast(address, ct.POINTER(ct.c_void_p))
    code = gpu.lib.structural_hip_csr_residual_create_v1(
        model["dimension"],
        arrays["value"].size,
        *(arrays[name].ctypes.data for name in CSR_NAMES),
        output,
    )
    assert code != 0
    assert (snapshots(arrays), storage.tobytes()) == before


@pytest.mark.parametrize(
    "arguments",
    [
        {"batch": -1},
        {"batch": 0},
        {"batch": 65},
        {"steps": 0},
        {"steps": 129},
        {"omega": 0.0},
        {"omega": -0.1},
        {"omega": 1.01},
        {"omega": np.nan},
        {"omega": np.inf},
        {"omega": -np.inf},
    ],
)
def test_evaluate_bounds_reject_without_output_writes(gpu, arguments):
    model = case()
    with live_handle(gpu, model) as handle:
        assert_rejected_without_writes(
            gpu, handle, model, evaluation_arrays(model), **arguments
        )


@pytest.mark.parametrize("target", EVAL_NAMES)
@pytest.mark.parametrize("damage", ["null", "misaligned", "overflow"])
def test_evaluate_pointer_admission_precedes_reads_and_writes(gpu, target, damage):
    model = case()
    arrays = evaluation_arrays(model)
    addresses = {name: arrays[name].ctypes.data for name in EVAL_NAMES}
    addresses[target] = {
        "null": None,
        "misaligned": arrays[target].ctypes.data + 1,
        "overflow": ct.c_void_p(-8).value,
    }[damage]
    with live_handle(gpu, model) as handle:
        assert_rejected_without_writes(gpu, handle, model, arrays, addresses=addresses)


@pytest.mark.parametrize("first,second", ALIAS_PAIRS)
@pytest.mark.parametrize("offset", [0, 8])
def test_all_six_evaluate_alias_pairs_preserve_every_caller_buffer(
    gpu, first, second, offset
):
    model = case()
    arrays = evaluation_arrays(model)
    addresses = {name: arrays[name].ctypes.data for name in EVAL_NAMES}
    addresses[second] = addresses[first] + offset
    with live_handle(gpu, model) as handle:
        assert_rejected_without_writes(gpu, handle, model, arrays, addresses=addresses)


@pytest.mark.parametrize("raw_handle", [None, 1, 4096])
def test_unregistered_handles_never_get_dereferenced(gpu, raw_handle):
    model = case()
    assert_rejected_without_writes(
        gpu, ct.c_void_p(raw_handle), model, evaluation_arrays(model)
    )
    assert gpu.lib.structural_hip_csr_residual_destroy_v1(ct.c_void_p(raw_handle)) != 0


def test_destroyed_handles_stay_invalid_after_new_handle_creation(gpu):
    model = case()
    handle, _ = gpu.create(model)
    stale = ct.c_void_p(handle.value)
    gpu.close(handle)
    assert gpu.lib.structural_hip_csr_residual_destroy_v1(stale) != 0
    with live_handle(gpu, model) as replacement:
        assert_rejected_without_writes(gpu, stale, model, evaluation_arrays(model))
        arrays = evaluation_arrays(model)
        assert raw_evaluate(gpu, replacement, model, arrays) == 0


@pytest.mark.parametrize("steps", [1, 2, 127, 128])
def test_odd_even_final_state_residual_repeat_and_batch_capacity_changes(gpu, steps):
    original = case(2)
    with live_handle(gpu, original) as handle:
        for batch in (2, 8, 1):
            model = case(batch)
            before = model["arrays"]["states"].tobytes()
            expected = MODULE.reference(model, steps, 0.05)
            retained = None
            for _ in range(2):
                state, residual = [np.empty_like(expected[0]) for _ in range(2)]
                timing = gpu.resident(handle, model, steps, 0.05, state, residual)
                MODULE.check_outputs(state, residual, expected)
                assert model["arrays"]["states"].tobytes() == before
                assert np.isfinite(timing["wall_ms"]) and timing["wall_ms"] >= 0.0
                phases = tuple(timing["phases_ms"].values())
                assert len(phases) == 6
                assert np.all(np.isfinite(phases)) and np.all(np.asarray(phases) >= 0.0)
                if retained is not None:
                    np.testing.assert_array_equal(state, retained[0])
                    np.testing.assert_array_equal(residual, retained[1])
                retained = state.copy(), residual.copy()


def test_resident_operator_copies_inputs_and_later_calls_cannot_change_held_outputs(
    gpu,
):
    model = case()
    expected = MODULE.reference(model, 2, 0.05)
    arrays = {name: value.copy() for name, value in MODULE.csr_arrays(model).items()}
    before = snapshots(arrays)
    code, handle = raw_create(gpu, model, arrays)
    gpu.checked(code)
    assert snapshots(arrays) == before
    try:
        for array in arrays.values():
            array.fill(0)
        first = evaluation_arrays(model)
        gpu.checked(raw_evaluate(gpu, handle, model, first))
        MODULE.check_outputs(first["state"], first["residual"], expected)
        saved = snapshots(first)
        changed = case(1)
        changed["arrays"]["states"] *= -2.0
        following = evaluation_arrays(changed)
        gpu.checked(raw_evaluate(gpu, handle, changed, following, steps=1))
        MODULE.check_outputs(
            following["state"],
            following["residual"],
            MODULE.reference(changed, 1, 0.05),
        )
        assert snapshots(first) == saved
    finally:
        gpu.close(handle)


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_nonfinite_initial_is_rejected_without_publishing_outputs_and_handle_recovers(
    gpu, invalid
):
    model = case()
    with live_handle(gpu, model) as handle:
        arrays = evaluation_arrays(model)
        arrays["initial"][0, 0] = invalid
        assert_rejected_without_writes(gpu, handle, model, arrays)
        recovered = evaluation_arrays(model)
        gpu.checked(raw_evaluate(gpu, handle, model, recovered))
        MODULE.check_outputs(
            recovered["state"], recovered["residual"], MODULE.reference(model, 2, 0.05)
        )


@pytest.mark.parametrize("overflow_at", ["residual", "update"])
def test_nonfinite_device_results_are_refused_before_any_output_publication(
    gpu, overflow_at
):
    model = MODULE.BASE.generated_case(12, 1)
    largest = np.finfo(np.float64).max
    diagonal = largest if overflow_at == "residual" else -1.0
    model["operator"] = MODULE.BASE.sparse.diags(np.full(12, diagonal), format="csr")
    model["arrays"]["external"] = np.zeros(12, dtype=np.float64)
    model["arrays"]["states"] = np.full(
        (1, 12), 2.0 if overflow_at == "residual" else largest
    )
    with live_handle(gpu, model) as handle:
        assert_rejected_without_writes(
            gpu, handle, model, evaluation_arrays(model), steps=1, omega=1.0
        )


def test_failed_create_does_not_poison_later_creation_or_checked_error_reporting(gpu):
    model = case()
    arrays = {name: value.copy() for name, value in MODULE.csr_arrays(model).items()}
    arrays["row"][0] = 1
    code, handle = raw_create(gpu, model, arrays)
    assert code != 0 and handle.value is None
    with pytest.raises(RuntimeError):
        gpu.checked(code)
    for _ in range(3):
        with live_handle(gpu, model) as valid:
            gpu.checked(
                raw_evaluate(gpu, valid, model, evaluation_arrays(model), steps=1)
            )


def test_concurrent_evaluation_rejects_busy_handle_without_touching_rejected_outputs(
    gpu,
):
    model = case(8)
    expected = MODULE.reference(model, 128, 0.05)
    with live_handle(gpu, model) as handle:
        observed_busy = False
        with ThreadPoolExecutor(max_workers=4) as pool:
            for _ in range(8):
                barrier = Barrier(4)

                def evaluate_together():
                    arrays = evaluation_arrays(model)
                    before = snapshots(arrays)
                    barrier.wait(timeout=10)
                    code = raw_evaluate(gpu, handle, model, arrays, steps=128)
                    return code, arrays, before

                results = list(pool.map(lambda _: evaluate_together(), range(4)))
                assert any(code == 0 for code, _, _ in results)
                for code, arrays, before in results:
                    assert code in (0, -3)
                    if code == -3:
                        observed_busy = True
                        assert snapshots(arrays) == before
                    else:
                        MODULE.check_outputs(
                            arrays["state"], arrays["residual"], expected
                        )
                if observed_busy:
                    break
        # A successful ordinary call proves contention released the busy guard.
        gpu.checked(raw_evaluate(gpu, handle, model, evaluation_arrays(model), steps=1))
        if not observed_busy:
            pytest.skip("scheduler did not overlap the bounded native evaluations")


def test_destroy_rejects_inflight_handle_and_allows_cleanup_after_evaluation(gpu):
    import time
    from threading import Event

    model = MODULE.BASE.generated_case(1536, 8)
    expected = MODULE.reference(model, 128, 0.05)
    observed_busy = False
    for _ in range(4):
        handle, _ = gpu.create(model)
        destroyed = False
        try:
            entered = Event()

            def evaluate_after_signal():
                arrays = evaluation_arrays(model)
                before = snapshots(arrays)
                entered.set()
                code = raw_evaluate(gpu, handle, model, arrays, steps=128)
                return code, arrays, before

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(evaluate_after_signal)
                assert entered.wait(timeout=10)
                time.sleep(0.001)
                # Invalid arguments make this an admission-only, nonnumeric probe.
                probe_code = gpu.lib.structural_hip_csr_residual_evaluate_v1(
                    handle, None, 0, 0, 0.05, None, None, None
                )
                assert probe_code in (-3, -1)
                if probe_code == -3:
                    destroy_code = gpu.lib.structural_hip_csr_residual_destroy_v1(
                        handle
                    )
                    assert destroy_code in (0, -3)
                    destroyed = destroy_code == 0
                    # Completion between probe and destroy is a valid cleanup race.
                    observed_busy = destroy_code == -3
                code, arrays, before = future.result(timeout=30)
            assert code in (0, -3)
            if code == 0:
                MODULE.check_outputs(arrays["state"], arrays["residual"], expected)
            else:
                # The admission probe may briefly win the guard before the worker.
                assert snapshots(arrays) == before
                observed_busy = False
        finally:
            if not destroyed:
                gpu.close(handle)
        if observed_busy:
            break
    if not observed_busy:
        pytest.skip("scheduler did not overlap destroy with a native evaluation")


def test_unsorted_csr_retains_stored_accumulation_order(gpu):
    model = MODULE.BASE.generated_case(12, 1)
    model["operator"] = MODULE.BASE.sparse.csr_matrix(
        (
            np.array([1.0e16, -1.0e16, 1.0], dtype=np.float64),
            np.array([0, 2, 1], dtype=np.int64),
            np.array([0, *([3] * 12)], dtype=np.int64),
        ),
        shape=(12, 12),
    )
    model["arrays"]["external"] = np.zeros(12, dtype=np.float64)
    model["arrays"]["states"] = np.ones((1, 12), dtype=np.float64)
    expected = MODULE.reference(model, 1, 0.05)
    with live_handle(gpu, model) as handle:
        state, residual = [np.empty_like(expected[0]) for _ in range(2)]
        gpu.resident(handle, model, 1, 0.05, state, residual)
        # Stored order sums to one; sorting/reassociation changes it to zero.
        assert state[0, 0] == np.float64(0.95)
        MODULE.check_outputs(state, residual, expected)


def test_tiny_finite_states_and_residuals_remain_exactly_nonzero(gpu):
    model = MODULE.BASE.generated_case(12, 1)
    model["operator"] = MODULE.BASE.sparse.eye(12, format="csr", dtype=np.float64)
    model["arrays"]["external"] = np.zeros(12, dtype=np.float64)
    model["arrays"]["states"] = np.full((1, 12), 1.0e-290, dtype=np.float64)
    expected = model["arrays"]["states"] * 0.5
    assert np.all(expected != 0.0)
    with live_handle(gpu, model) as handle:
        state, residual = [np.empty_like(expected) for _ in range(2)]
        gpu.resident(handle, model, 1, 0.5, state, residual)
        np.testing.assert_array_equal(state, expected)
        np.testing.assert_array_equal(residual, expected)
        assert np.all(state != 0.0) and np.all(residual != 0.0)


@pytest.fixture
def wrapper_without_native():
    calls = []

    def forbidden(*arguments):
        calls.append(arguments)
        pytest.fail("wrapper admission must reject before a native call")

    wrapper = object.__new__(MODULE.HipCsrSequence)
    wrapper.lib = SimpleNamespace(
        structural_hip_csr_residual_create_v1=forbidden,
        structural_hip_csr_residual_evaluate_v1=forbidden,
        structural_hip_csr_residual_destroy_v1=forbidden,
        structural_hip_csr_residual_last_error_v1=forbidden,
    )
    wrapper._dimensions = {123: 24}
    return wrapper, ct.c_void_p(123), calls


def strided_copy(array):
    storage = np.empty(array.size * 2, dtype=array.dtype)
    result = storage[::2].reshape(array.shape)
    result[...] = array
    assert not result.flags.c_contiguous
    return result


def unaligned_copy(array):
    storage = np.empty(array.nbytes + 1, dtype=np.uint8)
    result = np.ndarray(array.shape, dtype=array.dtype, buffer=storage, offset=1)
    result[...] = array
    assert not result.flags.aligned
    return result


@pytest.mark.parametrize(
    "damage",
    [
        "short_output",
        "float32_initial",
        "float32_state",
        "float32_residual",
        "strided_state",
        "strided_residual",
        "readonly_state",
        "readonly_residual",
        "unaligned_residual",
        "dimension",
        "dimension_float",
        "batch",
        "stale_handle",
        "arrays_mapping",
        "output_subclass",
    ],
)
def test_resident_wrapper_rejects_unsafe_buffers_or_handle_binding_before_ffi(
    wrapper_without_native, damage
):
    wrapper, handle, calls = wrapper_without_native
    model = case()
    inputs = model["arrays"]
    outputs = {
        "state": np.full_like(inputs["states"], -71.0),
        "residual": np.full_like(inputs["states"], -83.0),
    }
    if damage == "short_output":
        outputs["state"] = np.full((1, 12), -71.0, dtype=np.float64)
    elif damage == "float32_initial":
        inputs["states"] = inputs["states"].astype(np.float32)
    elif damage.startswith("float32_"):
        target = damage.removeprefix("float32_")
        outputs[target] = outputs[target].astype(np.float32)
    elif damage.startswith("strided_"):
        target = damage.removeprefix("strided_")
        outputs[target] = strided_copy(outputs[target])
    elif damage.startswith("readonly_"):
        outputs[damage.removeprefix("readonly_")].setflags(write=False)
    elif damage == "unaligned_residual":
        outputs["residual"] = unaligned_copy(outputs["residual"])
    elif damage == "dimension":
        model["dimension"] = 12
    elif damage == "dimension_float":
        model["dimension"] = 24.0
    elif damage == "batch":
        model["batch"] = 1
    elif damage == "stale_handle":
        wrapper._dimensions.pop(handle.value)
    elif damage == "arrays_mapping":
        model["arrays"] = tuple(inputs.items())
    else:

        class ArraySubclass(np.ndarray):
            pass

        outputs["state"] = outputs["state"].view(ArraySubclass)
    tracked = {**inputs, **outputs}
    before = snapshots(tracked)
    with pytest.raises(ValueError):
        wrapper.resident(handle, model, 2, 0.05, outputs["state"], outputs["residual"])
    assert snapshots(tracked) == before
    assert calls == []


@pytest.mark.parametrize(
    "damage",
    [
        "dimension",
        "operator_shape",
        "operator_format",
        "external_dtype",
        "external_shape",
        "row_dtype",
        "column_dtype",
        "column_shape",
        "row_strided",
        "column_unaligned",
    ],
)
def test_csr_adapter_and_create_reject_unsafe_array_representation_before_ffi(
    wrapper_without_native, damage
):
    wrapper, _, calls = wrapper_without_native
    model = case()
    operator = model["operator"]
    if damage == "dimension":
        model["dimension"] = 12
    elif damage == "operator_shape":
        model["operator"] = operator[:12, :].copy()
    elif damage == "operator_format":
        model["operator"] = operator.tocsc()
    elif damage == "external_dtype":
        model["arrays"]["external"] = model["arrays"]["external"].astype(np.float32)
    elif damage == "external_shape":
        model["arrays"]["external"] = model["arrays"]["external"].reshape(1, -1)
    elif damage == "row_dtype":
        operator.indptr = operator.indptr.astype(np.float64)
    elif damage == "column_dtype":
        operator.indices = operator.indices.astype(np.float64)
    elif damage == "column_shape":
        operator.indices = operator.indices[:-1].copy()
    elif damage == "row_strided":
        operator.indptr = strided_copy(operator.indptr)
    else:
        operator.indices = unaligned_copy(operator.indices)
    current = model["operator"]
    tracked = {
        "row": current.indptr,
        "column": current.indices,
        "value": current.data,
        "external": model["arrays"]["external"],
    }
    before = snapshots(tracked)
    with pytest.raises(ValueError):
        MODULE.csr_arrays(model)
    with pytest.raises(ValueError):
        wrapper.create(model)
    assert snapshots(tracked) == before
    assert wrapper._dimensions == {123: 24}
    assert calls == []


@pytest.mark.parametrize("damage", ["float64", "shape", "order", "strided"])
def test_comparison_rejects_nonidentity_free_layout_before_native_construction(
    monkeypatch, damage
):
    model = case()
    free = model["arrays"]["free"]
    if damage == "float64":
        model["arrays"]["free"] = free.astype(np.float64)
    elif damage == "shape":
        model["arrays"]["free"] = free.reshape(1, -1)
    elif damage == "order":
        model["arrays"]["free"] = free[::-1].copy()
    else:
        model["arrays"]["free"] = strided_copy(free)
    before = snapshots(model["arrays"])
    calls = []

    def forbidden(*arguments, **keywords):
        calls.append((arguments, keywords))
        pytest.fail("free-equation admission must precede reference/native work")

    monkeypatch.setattr(MODULE.BASE, "generated_case", lambda *_: model)
    monkeypatch.setattr(MODULE, "reference", forbidden)
    monkeypatch.setattr(MODULE, "CpuOperator", forbidden)
    native = SimpleNamespace(create=forbidden, csr=SimpleNamespace(create=forbidden))
    with pytest.raises(ValueError, match="identity order"):
        MODULE.compare_case(
            "unused-native-library", native, 24, 2, 2, 0.05, [1], 0, 1, True
        )
    assert snapshots(model["arrays"]) == before
    assert calls == []
