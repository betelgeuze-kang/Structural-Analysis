from __future__ import annotations

import ctypes
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import inspect
from itertools import combinations
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.fgmres_context_v2 import (  # noqa: E402
    HipFgmresCheckpointBuffersV2,
    HipFgmresCheckpointPredecessorReceiptV2,
    HipFgmresCheckpointTransactionReceiptV2,
    HipFgmresDeviceAllocationV2,
    HipFgmresRecurrenceExecutionContextV2,
)
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_context_v2 as context_v2_module,
)
from structural_analysis.engine_v2.backends.hip.context import (  # noqa: E402
    _BoundHipContextRuntime,
)
from structural_analysis.engine_v2.backends.hip import (  # noqa: E402
    context as hip_context_module,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    LoadedHipRuntime,
    load_hip_native_runtime,
)
from structural_analysis.engine_v2.backends.hip import (  # noqa: E402
    native as hip_native_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (  # noqa: E402
    HipRtcFgmresV2Kernel,
    first_column_checkpoint_transaction_launches_v2,
    reduction_stage_output_counts_v2,
    solve_record_byte_length_v2,
)
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_rtc_v2 as rtc_v2_module,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash  # noqa: E402

from tests.test_engine_v2_hip_fgmres_rtc_v2 import (  # noqa: E402
    FakeLoadedRuntime,
    _compile_fake,
    _compile_sealed_native_runtime_library,
    _launch_control,
    _launch_reduction,
    _launch_spmv,
    _launch_vector,
)


F = 513
M = 4
MAX_ITERATIONS = 8
R = 2
STREAM = ctypes.c_void_p(0xBEEF)
DEVICE_ORDINAL = 0
STAGE_COUNT = len(reduction_stage_output_counts_v2(F))
START_SCHEDULE_EPOCH = 26 + 14 * STAGE_COUNT
REDUCTION_EPOCH = 14 * STAGE_COUNT
# The source preflight row is non-advancing, so four launches claim three epochs.
END_SCHEDULE_EPOCH = START_SCHEDULE_EPOCH + 3
CHECKPOINT_TRANSACTION_LAUNCH_COUNT = 4
SCHEDULE_HASH = canonical_hash(
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
)
COMBINED_ABI_HASH = canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2())
CALLER_ATTESTED_SCOPE = "caller_attested_valid_predecessor_non_promoting"

ROLE_EXTENTS = {
    "reduced_state": ("f64", 8 * F),
    "reduced_load": ("f64", 8 * F),
    "inverse_diagonal": ("f64", 8 * F),
    "solution_x": ("f64", 8 * F),
    "true_residual": ("f64", 8 * F),
    "work_w": ("f64", 8 * F),
    "basis_v": ("f64", 8 * (M + 1) * F),
    "basis_z": ("f64", 8 * M * F),
    "dense": ("f64", 8 * (M * M + 5 * M + 1)),
    "control_state": ("u8", 256),
    "solve_record": ("u8", solve_record_byte_length_v2(R)),
}
ROLES = tuple(ROLE_EXTENTS)


class FakeSyncRuntime:
    def __init__(
        self,
        *,
        loaded_runtime: FakeLoadedRuntime | None = None,
        device_ordinal: int = DEVICE_ORDINAL,
        fail_count: int = 0,
        synchronize_callback: Any | None = None,
    ) -> None:
        self.loaded_runtime = loaded_runtime
        self.runtime_library_identity = (
            None if loaded_runtime is None else loaded_runtime.library_identity
        )
        self.device_ordinal = device_ordinal
        self.fail_count = fail_count
        self.synchronize_callback = synchronize_callback
        self.sync_streams: list[int] = []

    def bind_loaded_runtime(
        self,
        loaded_runtime: FakeLoadedRuntime,
        device_ordinal: int = DEVICE_ORDINAL,
    ) -> None:
        if self.loaded_runtime is not None:
            return
        self.loaded_runtime = loaded_runtime
        self.runtime_library_identity = loaded_runtime.library_identity
        self.device_ordinal = device_ordinal

    def synchronize(self, stream: Any) -> None:
        value = stream.value if isinstance(stream, ctypes.c_void_p) else stream
        self.sync_streams.append(int(value))
        if self.synchronize_callback is not None:
            self.synchronize_callback()
        if self.fail_count:
            self.fail_count -= 1
            raise RuntimeError("injected synchronization failure")


class BoundFakeLoadedRuntime(FakeLoadedRuntime):
    def __init__(
        self,
        *,
        sync_fail_count: int = 0,
        sync_callback: Any | None = None,
        current_device: int = DEVICE_ORDINAL,
        get_device_status: int = 0,
        get_device_exception: bool = False,
        get_device_callback: Any | None = None,
        launch_callback: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.sync_fail_count = sync_fail_count
        self.sync_callback = sync_callback
        self.sync_streams: list[int] = []
        self.selected_device: int | None = None
        self.current_device = current_device
        self.get_device_status = get_device_status
        self.get_device_exception = get_device_exception
        self.get_device_callback = get_device_callback
        self.get_device_calls = 0
        self.launch_callback = launch_callback

    def bind(self, symbol: str, argtypes: Any, restype: Any) -> Any:
        if symbol in {
            "hipModuleLoadData",
            "hipModuleGetFunction",
            "hipModuleLaunchKernel",
            "hipModuleUnload",
        }:
            return super().bind(symbol, argtypes, restype)
        del argtypes, restype
        if symbol == "hipSetDevice":
            return self._set_device
        if symbol == "hipGetDevice":
            return self._get_device
        if symbol == "hipStreamSynchronize":
            return self._synchronize
        if symbol == "hipStreamQuery":
            return self._query
        if symbol == "hipMemsetAsync":
            return self._memset_async
        return lambda *args: 0

    def _set_device(self, ordinal: int) -> int:
        self.selected_device = int(ordinal)
        self.current_device = int(ordinal)
        return 0

    def _get_device(self, output: Any) -> int:
        self.get_device_calls += 1
        if self.get_device_callback is not None:
            self.get_device_callback()
        if self.get_device_exception:
            raise RuntimeError("injected hipGetDevice exception")
        if self.get_device_status:
            return self.get_device_status
        ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = ctypes.c_int(
            self.current_device
        )
        return 0

    def _launch(self, *arguments: Any) -> int:
        status = super()._launch(*arguments)
        if self.launch_callback is not None:
            self.launch_callback(len(self.launch_records))
        return status

    def _synchronize(self, stream: Any) -> int:
        value = stream.value if isinstance(stream, ctypes.c_void_p) else stream
        self.sync_streams.append(int(value))
        if self.sync_callback is not None:
            self.sync_callback()
        if self.sync_fail_count:
            self.sync_fail_count -= 1
            return 7
        self._stream_completion[int(value)] = True
        return 0


def _exact_sync_runtime(
    loaded_runtime: Any,
    *,
    device_ordinal: int = DEVICE_ORDINAL,
) -> _BoundHipContextRuntime:
    runtime = _BoundHipContextRuntime(
        loaded_runtime,
        **(
            {}
            if type(loaded_runtime) is LoadedHipRuntime
            else {
                "_injected_runtime_mint": (
                    hip_context_module._INJECTED_HIP_CONTEXT_RUNTIME_MINT
                )
            }
        ),
    )
    runtime.set_device(device_ordinal)
    runtime.sync_streams = getattr(loaded_runtime, "sync_streams", [])
    return runtime


class SequencedLoadedRuntime(BoundFakeLoadedRuntime):
    def __init__(self, *, raise_at: int | None = None) -> None:
        super().__init__()
        self.raise_at = raise_at

    def _launch(self, *arguments: Any) -> int:
        status = super()._launch(*arguments)
        if len(self.launch_records) == self.raise_at:
            raise RuntimeError(
                f"ambiguous fake launch {len(self.launch_records)} exception"
            )
        return status


class SequencedStatusLoadedRuntime(BoundFakeLoadedRuntime):
    def __init__(
        self,
        *,
        reject_at: int,
        status: int = 7,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.reject_at = reject_at
        self.rejection_status = status

    def _launch(self, *arguments: Any) -> int:
        status = super()._launch(*arguments)
        if len(self.launch_records) == self.reject_at:
            return self.rejection_status
        return status


class ReentrantUnloadLoadedRuntime(BoundFakeLoadedRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.unload_callback: Any | None = None

    def _unload(self, module: Any) -> int:
        callback = self.unload_callback
        self.unload_callback = None
        if callback is not None:
            callback()
        return super()._unload(module)


class _FakeNativeFunction:
    def __init__(self, target: Any) -> None:
        self._target = target
        self.argtypes: Any = None
        self.restype: Any = None

    def __call__(self, *arguments: Any) -> Any:
        return self._target(*arguments)


class _FakeNativeCdll:
    def __init__(self, backend: BoundFakeLoadedRuntime, handle: int) -> None:
        self._backend = backend
        self._handle = handle
        self._functions: dict[str, _FakeNativeFunction] = {}

    def __getattr__(self, symbol: str) -> _FakeNativeFunction:
        function = self._functions.get(symbol)
        if function is None:
            target = self._backend.bind(symbol, (), None)
            function = _FakeNativeFunction(target)
            self._functions[symbol] = function
        return function


def _native_loaded_runtime(
    backend: BoundFakeLoadedRuntime,
    *,
    handle: int,
) -> LoadedHipRuntime:
    return LoadedHipRuntime(
        _FakeNativeCdll(backend, handle),
        backend.library_identity,
        _loader_mint=hip_native_module._LOADED_HIP_RUNTIME_MINT,
    )


def _allocations(
    *,
    runtime: object,
    owner_token: object | None = None,
    generation_base: int = 100,
) -> tuple[object, tuple[HipFgmresDeviceAllocationV2, ...]]:
    owner = object() if owner_token is None else owner_token
    rows = tuple(
        HipFgmresDeviceAllocationV2(
            base=0x100000 + index * 0x100000,
            pointer_snapshot=0x100000 + index * 0x100000,
            nbytes=nbytes,
            element_type=element_type,
            owner_token=owner,
            generation=generation_base + index,
            runtime=runtime,
            device_ordinal=DEVICE_ORDINAL,
        )
        for index, (_, (element_type, nbytes)) in enumerate(ROLE_EXTENTS.items())
    )
    return owner, rows


def _buffers(
    allocations: tuple[HipFgmresDeviceAllocationV2, ...],
) -> HipFgmresCheckpointBuffersV2:
    return HipFgmresCheckpointBuffersV2(**dict(zip(ROLES, allocations, strict=True)))


def _generation_witness(
    buffers: HipFgmresCheckpointBuffersV2,
) -> tuple[tuple[str, int], ...]:
    return tuple((role, getattr(buffers, role).generation) for role in ROLES)


def _active_generation_witness(
    buffers: HipFgmresCheckpointBuffersV2,
) -> tuple[tuple[str, int], ...]:
    return (
        ("work_w", buffers.work_w.generation),
        ("basis_v", buffers.basis_v.generation),
    )


def _assert_error(exc: BaseException, fragment: str) -> None:
    text = " ".join(
        str(value)
        for value in (
            getattr(exc, "code", ""),
            getattr(exc, "path", ""),
            str(exc),
        )
    ).lower()
    assert fragment.lower() in text


def _assert_caller_attested_nonpromoting(receipt: Any) -> None:
    assert receipt.evidence_scope == CALLER_ATTESTED_SCOPE
    assert receipt.authoritative_predecessor_proven is False
    assert receipt.live_krylov_parent_integrated is False
    assert receipt.promotion_eligible is False
    assert receipt.completion_fence_authoritative is True


def _open_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    loaded_runtime: BoundFakeLoadedRuntime | None = None,
    sync_runtime: Any | None = None,
    allocation_transform: Any | None = None,
) -> tuple[
    HipFgmresRecurrenceExecutionContextV2,
    Any,
    BoundFakeLoadedRuntime,
    Any,
    HipFgmresCheckpointBuffersV2,
]:
    loaded = loaded_runtime or BoundFakeLoadedRuntime()
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    runtime = sync_runtime or _exact_sync_runtime(loaded)
    _, rows = _allocations(runtime=runtime)
    if allocation_transform is not None:
        rows = allocation_transform(rows)
    buffers = _buffers(rows)
    context = _construct_context(kernel, runtime, buffers)
    return context, kernel, loaded, runtime, buffers


def _construct_context(
    kernel: Any,
    runtime: Any,
    buffers: HipFgmresCheckpointBuffersV2,
    *,
    stream: Any = STREAM,
    device_ordinal: int = DEVICE_ORDINAL,
    free_dof_count: int = F,
    restart_dimension: int = M,
    max_iterations: int = MAX_ITERATIONS,
    maximum_restart_count: int = R,
) -> HipFgmresRecurrenceExecutionContextV2:
    return HipFgmresRecurrenceExecutionContextV2(
        kernel=kernel,
        runtime=runtime,
        stream=stream,
        device_ordinal=device_ordinal,
        free_dof_count=free_dof_count,
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
        maximum_restart_count=maximum_restart_count,
        stagnation_checkpoint_limit=2,
        absolute_tolerance=0.0,
        relative_tolerance=1.0e-8,
        authoritative_tolerance=1.0e-9,
        stagnation_relative_tolerance=1.0e-8,
        divergence_factor=1.0e8,
        buffers=buffers,
    )


def _issue(
    context: HipFgmresRecurrenceExecutionContextV2,
    buffers: HipFgmresCheckpointBuffersV2,
) -> HipFgmresCheckpointPredecessorReceiptV2:
    return context.issue_predecessor_receipt(
        schedule_epoch=START_SCHEDULE_EPOCH,
        reduction_epoch=REDUCTION_EPOCH,
        source_generations=_active_generation_witness(buffers),
    )


def _close_ready(context: HipFgmresRecurrenceExecutionContextV2) -> None:
    if context.state in {
        "READY",
        "FENCED",
        "POISONED_FENCED",
        "POISONED_NO_WORK",
    }:
        context.close()
    if context.state == "CLOSED":
        for _, allocation in context.buffers.items():
            if allocation.pointer_snapshot in context._registered:
                context.release_allocation(allocation)


def _replace_role(
    rows: tuple[HipFgmresDeviceAllocationV2, ...],
    role: str,
    **changes: Any,
) -> tuple[HipFgmresDeviceAllocationV2, ...]:
    index = ROLES.index(role)
    mutable = list(rows)
    mutable[index] = replace(mutable[index], **changes)
    return tuple(mutable)


def _mutable_pointer_rows(
    rows: tuple[HipFgmresDeviceAllocationV2, ...],
) -> tuple[HipFgmresDeviceAllocationV2, ...]:
    return tuple(
        replace(row, base=ctypes.c_void_p(row.pointer_snapshot)) for row in rows
    )


def _mutated_allocation_value(
    field: str,
    allocation: HipFgmresDeviceAllocationV2,
    *,
    loaded_runtime: BoundFakeLoadedRuntime,
) -> Any:
    if field == "base":
        return allocation.pointer_snapshot + 8
    if field == "pointer_snapshot":
        return allocation.pointer_snapshot + 8
    if field == "nbytes":
        return allocation.nbytes + 8
    if field == "element_type":
        return "u8" if allocation.element_type == "f64" else "f64"
    if field == "owner_token":
        return object()
    if field == "generation":
        return allocation.generation + 1
    if field == "runtime":
        return _exact_sync_runtime(loaded_runtime)
    if field == "device_ordinal":
        return allocation.device_ordinal + 1
    raise AssertionError(field)


def test_public_descriptors_are_frozen_and_receipts_are_context_issued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, _, _, buffers = _open_context(monkeypatch)
    try:
        with pytest.raises(FrozenInstanceError):
            buffers.work_w.generation = 999  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            buffers.work_w = buffers.solution_x  # type: ignore[misc]
        with pytest.raises(TypeError):
            HipFgmresCheckpointPredecessorReceiptV2()  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            HipFgmresCheckpointTransactionReceiptV2()  # type: ignore[call-arg]
        predecessor = _issue(context, buffers)
        assert type(predecessor) is HipFgmresCheckpointPredecessorReceiptV2
    finally:
        _close_ready(context)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    ("change", "fragment"),
    (("under", "extent"), ("over", "extent"), ("type", "type")),
)
def test_every_role_requires_exact_typed_extent(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    change: str,
    fragment: str,
) -> None:
    def transform(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        row = rows[ROLES.index(role)]
        if change == "under":
            return _replace_role(rows, role, nbytes=row.nbytes - 1)
        if change == "over":
            return _replace_role(rows, role, nbytes=row.nbytes + 1)
        wrong_type = "u8" if row.element_type == "f64" else "f64"
        return _replace_role(rows, role, element_type=wrong_type)

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=transform)
    _assert_error(caught.value, fragment)


@pytest.mark.parametrize("role", ROLES)
def test_every_role_requires_exact_allocation_base_not_shifted_pointer(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    def transform(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        row = rows[ROLES.index(role)]
        return _replace_role(rows, role, pointer_snapshot=row.base + 1)

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=transform)
    _assert_error(caught.value, "base")


@pytest.mark.parametrize("stage", ("receipt", "enqueue"))
@pytest.mark.parametrize("mutation", ("shift", "overlap"))
def test_mutable_pointer_base_drift_is_rejected_before_any_raw_launch(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    mutation: str,
) -> None:
    context, _, loaded, _, buffers = _open_context(
        monkeypatch,
        allocation_transform=_mutable_pointer_rows,
    )
    predecessor = None if stage == "receipt" else _issue(context, buffers)
    original = buffers.work_w.pointer_snapshot
    assert isinstance(buffers.work_w.base, ctypes.c_void_p)
    buffers.work_w.base.value = (
        original + 8 if mutation == "shift" else buffers.solution_x.pointer_snapshot
    )
    try:
        with pytest.raises(Exception) as caught:
            if stage == "receipt":
                _issue(context, buffers)
            else:
                assert predecessor is not None
                context.enqueue_checkpoint_transaction(predecessor)
        _assert_error(caught.value, "allocation")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        buffers.work_w.base.value = original
        _close_ready(context)


def test_mutable_pointer_launch_arguments_are_exact_registered_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, loaded, _, buffers = _open_context(
        monkeypatch,
        allocation_transform=_mutable_pointer_rows,
    )
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    assert loaded.launch_records[0]["arguments"][-3:] == (
        buffers.dense.pointer_snapshot,
        buffers.control_state.pointer_snapshot,
        buffers.solve_record.pointer_snapshot,
    )
    expected_pointers = tuple(getattr(buffers, role).pointer_snapshot for role in ROLES)
    assert loaded.launch_records[1]["arguments"][-11:] == expected_pointers
    assert loaded.launch_records[2]["arguments"][-11:] == expected_pointers
    assert loaded.launch_records[1]["stream"] == STREAM.value
    assert loaded.launch_records[2]["stream"] == STREAM.value
    context.synchronize_checkpoint_transaction(pending)
    _close_ready(context)


@pytest.mark.parametrize(
    "field",
    (
        "base",
        "pointer_snapshot",
        "nbytes",
        "element_type",
        "owner_token",
        "generation",
        "runtime",
        "device_ordinal",
    ),
)
def test_every_public_allocation_field_mutation_is_rejected_prelaunch(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    allocation = buffers.work_w
    original = getattr(allocation, field)
    object.__setattr__(
        allocation,
        field,
        _mutated_allocation_value(
            field,
            allocation,
            loaded_runtime=loaded,
        ),
    )
    try:
        with pytest.raises(Exception) as caught:
            _issue(context, buffers)
        _assert_error(caught.value, "allocation")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        object.__setattr__(allocation, field, original)
        _close_ready(context)


def test_buffer_role_object_swap_is_rejected_prelaunch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    original = buffers.work_w
    object.__setattr__(buffers, "work_w", buffers.solution_x)
    try:
        with pytest.raises(Exception) as caught:
            _issue(context, buffers)
        _assert_error(caught.value, "allocation")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        object.__setattr__(buffers, "work_w", original)
        _close_ready(context)


@pytest.mark.parametrize("field", ("base", "pointer_snapshot"))
def test_launch_boundary_mutation_never_reaches_raw_pointer_arguments(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    original_launch = HipRtcFgmresV2Kernel.launch_control
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    allocation = buffers.work_w
    original_value = getattr(allocation, field)
    mutated_pointer = allocation.pointer_snapshot + 8
    callback_count = 0

    def mutate_at_launch(
        self: Any,
        *arguments: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            object.__setattr__(allocation, field, mutated_pointer)
        return original_launch(self, *arguments, **kwargs)

    monkeypatch.setattr(HipRtcFgmresV2Kernel, "launch_control", mutate_at_launch)
    try:
        pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
        assert callback_count == 2
        expected_pointers = tuple(context._pointer_snapshots[role] for role in ROLES)
        assert loaded.launch_records[1]["arguments"][-11:] == expected_pointers
        assert loaded.launch_records[2]["arguments"][-11:] == expected_pointers
        assert mutated_pointer not in loaded.launch_records[1]["arguments"][-11:]
        assert mutated_pointer not in loaded.launch_records[2]["arguments"][-11:]
        object.__setattr__(allocation, field, original_value)
        context.synchronize_checkpoint_transaction(pending)
    finally:
        object.__setattr__(allocation, field, original_value)
        if context.state != "CLOSED":
            _close_ready(context)


def test_pointer_snapshot_mapping_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, loaded, _, _ = _open_context(monkeypatch)
    original = context._pointer_snapshots["work_w"]
    with pytest.raises(TypeError):
        context._pointer_snapshots["work_w"] = original + 8
    assert context._pointer_snapshots["work_w"] == original
    assert loaded.launch_records == []
    _close_ready(context)


def test_private_pointer_snapshot_mapping_replacement_is_rejected_prelaunch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    original = context._pointer_snapshots
    tampered_rows = dict(original)
    tampered_rows["work_w"] += 8
    tampered = MappingProxyType(tampered_rows)
    try:
        object.__setattr__(context, "_pointer_snapshots", tampered)
        with pytest.raises(Exception) as caught:
            _issue(context, buffers)
        _assert_error(caught.value, "pointer")
        assert context.state == "READY"
        assert loaded.launch_records == []

        object.__setattr__(context, "_pointer_snapshots", original)
        predecessor = _issue(context, buffers)
        object.__setattr__(context, "_pointer_snapshots", tampered)
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(predecessor)
        _assert_error(caught.value, "pointer")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        object.__setattr__(context, "_pointer_snapshots", original)
        _close_ready(context)


@pytest.mark.parametrize(
    "mutation",
    ("same_kind_row", "row_field", "vector_reorder", "tuple_identity"),
)
def test_canonical_checkpoint_row_drift_is_rejected_with_zero_launches(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    predecessor = _issue(context, buffers)
    original_launches = context._launches
    mutated_row: Any | None = None
    original_mode: int | None = None
    if mutation == "same_kind_row":
        rows = list(original_launches)
        rows[-1] = rows[0]
        object.__setattr__(context, "_launches", tuple(rows))
    elif mutation == "row_field":
        mutated_row = original_launches[1]
        original_mode = mutated_row.mode
        object.__setattr__(mutated_row, "mode", original_launches[2].mode)
    elif mutation == "vector_reorder":
        object.__setattr__(
            context,
            "_launches",
            (
                original_launches[0],
                original_launches[2],
                original_launches[1],
                original_launches[3],
            ),
        )
    else:
        object.__setattr__(context, "_launches", tuple(list(original_launches)))
    try:
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(predecessor)
        _assert_error(caught.value, "schedule")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        if mutated_row is not None:
            object.__setattr__(mutated_row, "mode", original_mode)
        object.__setattr__(context, "_launches", original_launches)
        pending = context.enqueue_checkpoint_transaction(predecessor)
        context.synchronize_checkpoint_transaction(pending)
        _close_ready(context)


@pytest.mark.parametrize(
    "field",
    ("pointer_snapshot", "runtime", "device_ordinal", "generation"),
)
def test_registration_mutation_and_lease_failure_rollback_use_original_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    _, rows = _allocations(runtime=runtime, generation_base=9000)
    buffers = _buffers(rows)
    allocation = buffers.work_w
    original_value = getattr(allocation, field)
    original_register = context_v2_module._register_buffer_set
    mutation_count = 0

    def mutate_between_validation_and_commit(
        context_token: object,
        candidates: Any,
    ) -> Any:
        nonlocal mutation_count
        mutation_count += 1
        object.__setattr__(
            allocation,
            field,
            _mutated_allocation_value(
                field,
                allocation,
                loaded_runtime=loaded,
            ),
        )
        return original_register(context_token, candidates)

    monkeypatch.setattr(
        context_v2_module,
        "_register_buffer_set",
        mutate_between_validation_and_commit,
    )
    blocked_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    external_token = object()
    blocked_kernel._acquire_checkpoint_transaction_owner(
        _checkpoint_owner_token=external_token
    )
    try:
        with pytest.raises(Exception) as caught:
            _construct_context(blocked_kernel, runtime, buffers)
        _assert_error(caught.value, "lease")
        assert mutation_count == 1
    finally:
        object.__setattr__(allocation, field, original_value)
        blocked_kernel.close(_checkpoint_owner_token=external_token)

    monkeypatch.setattr(
        context_v2_module,
        "_register_buffer_set",
        original_register,
    )
    retry_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    retry = _construct_context(retry_kernel, runtime, buffers)
    _close_ready(retry)


def test_context_releases_preissued_token_after_acquisition_return_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    _, rows = _allocations(runtime=runtime, generation_base=12000)
    buffers = _buffers(rows)
    original_acquire = (
        HipRtcFgmresV2Kernel._acquire_checkpoint_transaction_owner_and_binding_snapshot
    )
    interruption = KeyboardInterrupt(
        "injected after checkpoint lease acquisition return"
    )
    observed_tokens: list[object] = []

    def acquire_then_interrupt(
        self: Any,
        expected_device_ordinal: int | None = None,
        *,
        _checkpoint_owner_token: object,
    ) -> Any:
        result = original_acquire(
            self,
            expected_device_ordinal,
            _checkpoint_owner_token=_checkpoint_owner_token,
        )
        observed_tokens.append(_checkpoint_owner_token)
        assert result[0] is _checkpoint_owner_token
        assert self._checkpoint_owner_token is _checkpoint_owner_token
        raise interruption

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_acquire_checkpoint_transaction_owner_and_binding_snapshot",
        acquire_then_interrupt,
    )
    with pytest.raises(KeyboardInterrupt) as caught:
        _construct_context(kernel, runtime, buffers)
    assert caught.value is interruption
    assert len(observed_tokens) == 1
    assert kernel._checkpoint_owner_token is None
    assert kernel.pending_stream_count == 0
    assert loaded.unload_calls == 0

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_acquire_checkpoint_transaction_owner_and_binding_snapshot",
        original_acquire,
    )
    retry = _construct_context(kernel, runtime, buffers)
    assert retry._checkpoint_owner_token is not None
    _close_ready(retry)


@pytest.mark.parametrize("mismatch", ("loaded_runtime", "identity", "device"))
def test_sync_runtime_must_bind_exact_kernel_runtime_and_device_before_open(
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    foreign = BoundFakeLoadedRuntime()
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    runtime = _exact_sync_runtime(
        foreign if mismatch == "loaded_runtime" else loaded,
        device_ordinal=(DEVICE_ORDINAL + 1 if mismatch == "device" else DEVICE_ORDINAL),
    )
    if mismatch == "identity":
        loaded.library_identity = replace(
            loaded.library_identity,
            sha256="sha256:" + "9" * 64,
        )
    _, rows = _allocations(runtime=runtime)
    buffers = _buffers(rows)
    with pytest.raises(Exception) as caught:
        _construct_context(kernel, runtime, buffers)
    _assert_error(caught.value, "runtime" if mismatch != "device" else "device")
    assert kernel.pending_stream_count == 0
    if mismatch == "device":
        loaded.current_device = DEVICE_ORDINAL
    kernel.close()


@pytest.mark.parametrize("failure", ("mismatch", "status", "exception"))
def test_hip_get_device_lease_open_failure_has_no_token_and_rolls_back_registry(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    _, rows = _allocations(runtime=runtime, generation_base=9700)
    buffers = _buffers(rows)
    assert runtime.device_ordinal == DEVICE_ORDINAL
    if failure == "mismatch":
        loaded.current_device = DEVICE_ORDINAL + 1
    elif failure == "status":
        loaded.get_device_status = 7
    else:
        loaded.get_device_exception = True

    with pytest.raises(Exception) as caught:
        _construct_context(kernel, runtime, buffers)
    _assert_error(caught.value, "device")
    assert kernel._checkpoint_owner_token is None
    assert kernel.pending_stream_count == 0
    assert loaded.launch_records == []

    loaded.current_device = DEVICE_ORDINAL
    loaded.get_device_status = 0
    loaded.get_device_exception = False
    retry = _construct_context(kernel, runtime, buffers)
    _close_ready(retry)


def test_current_device_drift_rejects_issue_and_enqueue_before_any_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, loaded, _, buffers = _open_context(monkeypatch)
    assert context._runtime.device_ordinal == DEVICE_ORDINAL
    loaded.current_device = DEVICE_ORDINAL + 1
    try:
        with pytest.raises(Exception) as caught:
            _issue(context, buffers)
        _assert_error(caught.value, "device")
        assert context.state == "READY"
        assert kernel.pending_stream_count == 0
        assert loaded.launch_records == []

        loaded.current_device = DEVICE_ORDINAL
        predecessor = _issue(context, buffers)
        loaded.current_device = DEVICE_ORDINAL + 1
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(predecessor)
        _assert_error(caught.value, "device")
        assert context.state == "READY"
        assert kernel.pending_stream_count == 0
        assert loaded.launch_records == []
    finally:
        loaded.current_device = DEVICE_ORDINAL
        _close_ready(context)


def test_device_drift_between_launches_blocks_suffix_and_requires_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()

    def drift_after_first_launch(launch_count: int) -> None:
        if launch_count == 1:
            loaded.current_device = DEVICE_ORDINAL + 1
            loaded.launch_callback = None

    loaded.launch_callback = drift_after_first_launch
    runtime = _exact_sync_runtime(loaded)
    context, kernel, _, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded,
        sync_runtime=runtime,
    )
    predecessor = _issue(context, buffers)
    with pytest.raises(Exception) as caught:
        context.enqueue_checkpoint_transaction(predecessor)
    pending = getattr(caught.value, "transaction_receipt", None)
    assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
    assert pending.state == "POISONED_PENDING_FENCE"
    assert pending.attempted_launch_count == 1
    assert pending.accepted_launch_count_lower_bound == 1
    assert pending.accepted_launch_count_upper_bound == 1
    assert len(loaded.launch_records) == 1
    assert kernel.pending_stream_count == 1

    loaded.current_device = DEVICE_ORDINAL
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "POISONED_FENCED"
    assert kernel.pending_stream_count == 0
    _close_ready(context)


@pytest.mark.parametrize(
    "mutation",
    ("pointers", "stream", "kernel", "rows", "scalar", "owner_token"),
)
def test_mid_enqueue_binding_drift_after_preflight_blocks_commit_suffix(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    context, kernel, _, runtime, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded,
    )
    predecessor = _issue(context, buffers)
    restored: list[tuple[str, Any]] = []

    def replace_context_field(name: str, value: Any) -> None:
        restored.append((name, getattr(context, name)))
        object.__setattr__(context, name, value)

    def mutate_after_preflight(launch_count: int) -> None:
        if launch_count != 2:
            return
        loaded.launch_callback = None
        if mutation == "pointers":
            values = dict(context._pointer_snapshots)
            values["work_w"] += 8
            replace_context_field("_pointer_snapshots", MappingProxyType(values))
        elif mutation == "stream":
            replace_context_field("_stream_pointer", context._stream_pointer + 8)
        elif mutation == "kernel":
            replace_context_field("_kernel", object())
        elif mutation == "rows":
            rows = context._launches
            replace_context_field(
                "_launches",
                (rows[0], rows[2], rows[1], rows[3]),
            )
        elif mutation == "scalar":
            replace_context_field(
                "_absolute_tolerance",
                context._absolute_tolerance + 1.0,
            )
        else:
            replace_context_field("_checkpoint_owner_token", object())

    loaded.launch_callback = mutate_after_preflight
    try:
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(predecessor)
        pending = getattr(caught.value, "transaction_receipt", None)
        assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
        assert pending.state == "POISONED_PENDING_FENCE"
        assert pending.attempted_launch_count == 2
        assert pending.accepted_launch_count_lower_bound == 2
        assert pending.accepted_launch_count_upper_bound == 2
        assert len(loaded.launch_records) == 2
        expected_pointers = tuple(getattr(buffers, role).base for role in ROLES)
        assert loaded.launch_records[1]["arguments"][-11:] == expected_pointers
        assert {row["stream"] for row in loaded.launch_records} == {STREAM.value}
        assert kernel.pending_stream_count == 1
    finally:
        for name, value in reversed(restored):
            object.__setattr__(context, name, value)
        loaded.launch_callback = None
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "POISONED_FENCED"
    assert runtime.sync_streams == [STREAM.value]
    assert kernel.pending_stream_count == 0
    _close_ready(context)


def test_public_context_rejects_arbitrary_noop_sync_facade_preopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    noop = FakeSyncRuntime(loaded_runtime=loaded)
    _, rows = _allocations(runtime=noop)
    with pytest.raises(Exception) as caught:
        _construct_context(kernel, noop, _buffers(rows))
    _assert_error(caught.value, "runtime")
    assert loaded.launch_records == []
    assert loaded.sync_streams == []
    assert kernel.pending_stream_count == 0
    assert loaded.unload_calls == 0
    kernel.close()


def test_context_rejects_duck_typed_kernel_wrapper_even_with_exact_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    kernel, _, _ = _compile_fake(monkeypatch, loaded)

    class Delegate:
        def __init__(self, target: Any) -> None:
            self._target = target

        def __getattr__(self, name: str) -> Any:
            return getattr(self._target, name)

    _, rows = _allocations(runtime=runtime)
    with pytest.raises(Exception) as caught:
        _construct_context(Delegate(kernel), runtime, _buffers(rows))
    _assert_error(caught.value, "kernel")
    assert kernel.pending_stream_count == 0
    kernel.close()


def test_public_bound_runtime_rejects_unminted_bind_capable_fake() -> None:
    loaded = BoundFakeLoadedRuntime()
    with pytest.raises(TypeError, match="loader-issued"):
        _BoundHipContextRuntime(loaded)
    assert loaded.selected_device is None
    assert loaded.get_device_calls == 0
    assert loaded.launch_records == []


def test_loader_issued_native_runtime_can_mint_authoritative_fence_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    library = _compile_sealed_native_runtime_library(
        tmp_path,
        stem="context_loader_native_runtime",
    )
    loaded = load_hip_native_runtime(library)
    runtime = _exact_sync_runtime(loaded)
    context, _, _, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded,
        sync_runtime=runtime,
    )
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.completion_fence_observed
    assert fenced.completion_fence_authoritative
    assert fenced.evidence_scope == CALLER_ATTESTED_SCOPE
    _close_ready(context)


@pytest.mark.parametrize(
    "mutation",
    ("function_mapping", "function_handle_value", "module_handle_value"),
)
def test_raw_module_or_function_handle_drift_is_rejected_prelaunch(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    context, kernel, loaded, _, buffers = _open_context(monkeypatch)
    predecessor = _issue(context, buffers)
    original_functions = kernel._function_pointers
    original_module = kernel._module_pointer
    if mutation == "function_mapping":
        object.__setattr__(
            kernel, "_function_pointers", tuple(reversed(original_functions))
        )
    elif mutation == "function_handle_value":
        function_name, function_pointer = original_functions[0]
        object.__setattr__(
            kernel,
            "_function_pointers",
            ((function_name, function_pointer + 1), *original_functions[1:]),
        )
    else:
        object.__setattr__(kernel, "_module_pointer", original_module + 1)
    try:
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(predecessor)
        _assert_error(caught.value, "kernel")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        object.__setattr__(kernel, "_function_pointers", original_functions)
        object.__setattr__(kernel, "_module_pointer", original_module)
        _close_ready(context)


def test_direct_kernel_constructor_cannot_forge_compile_mint_with_copied_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    compiled, _, _ = _compile_fake(monkeypatch, loaded)
    try:
        with pytest.raises(TypeError) as caught:
            HipRtcFgmresV2Kernel(
                runtime=compiled._runtime,
                module=ctypes.c_void_p(compiled._module_pointer),
                functions={
                    name: ctypes.c_void_p(pointer)
                    for name, pointer in compiled._function_pointers
                },
                identity=compiled.identity,
                _owner_mint=object(),
            )
        _assert_error(caught.value, "fixed-source compiler")
        assert loaded.launch_records == []
    finally:
        compiled.close()


def test_uintptr_end_overflow_and_f64_alignment_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def overflow(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        base = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 8
        return _replace_role(
            rows,
            "control_state",
            base=base,
            pointer_snapshot=base,
        )

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=overflow)
    _assert_error(caught.value, "overflow")

    def misaligned(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        row = rows[0]
        return _replace_role(
            rows,
            "reduced_state",
            base=row.base + 1,
            pointer_snapshot=row.base + 1,
        )

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=misaligned)
    _assert_error(caught.value, "align")


@pytest.mark.parametrize("role", ("control_state", "solve_record"))
def test_atomic_u8_control_and_record_require_eight_byte_alignment(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    def misaligned(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        row = rows[ROLES.index(role)]
        return _replace_role(
            rows,
            role,
            base=row.base + 1,
            pointer_snapshot=row.pointer_snapshot + 1,
        )

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=misaligned)
    _assert_error(caught.value, "align")


@pytest.mark.parametrize(("left", "right"), tuple(combinations(ROLES, 2)))
def test_all_eleven_role_ranges_are_pairwise_disjoint(
    monkeypatch: pytest.MonkeyPatch,
    left: str,
    right: str,
) -> None:
    def overlap(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        left_row = rows[ROLES.index(left)]
        right_row = rows[ROLES.index(right)]
        alignment = (
            8
            if right_row.element_type == "f64"
            or right in {"control_state", "solve_record"}
            else 1
        )
        shifted = ((left_row.base + left_row.nbytes - 1) // alignment) * alignment
        assert shifted < left_row.base + left_row.nbytes
        return _replace_role(
            rows,
            right,
            base=shifted,
            pointer_snapshot=shifted,
        )

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=overlap)
    _assert_error(caught.value, "overlap")


def test_adjacent_allocation_ranges_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def adjacent(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        left = rows[0]
        base = left.base + left.nbytes
        return _replace_role(
            rows,
            "reduced_load",
            base=base,
            pointer_snapshot=base,
        )

    context, _, _, _, _ = _open_context(monkeypatch, allocation_transform=adjacent)
    _close_ready(context)


@pytest.mark.parametrize(
    ("change", "fragment"),
    (("owner", "owner"), ("runtime", "runtime"), ("device", "device")),
)
def test_foreign_allocation_lineage_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    fragment: str,
) -> None:
    def transform(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        changes: dict[str, Any]
        if change == "owner":
            changes = {"owner_token": object()}
        elif change == "runtime":
            changes = {"runtime": FakeSyncRuntime()}
        else:
            changes = {"device_ordinal": DEVICE_ORDINAL + 1}
        return _replace_role(rows, "work_w", **changes)

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=transform)
    _assert_error(caught.value, fragment)


def test_allocation_generation_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stale(
        rows: tuple[HipFgmresDeviceAllocationV2, ...],
    ) -> tuple[HipFgmresDeviceAllocationV2, ...]:
        return _replace_role(rows, "work_w", generation=0)

    with pytest.raises(Exception) as caught:
        _open_context(monkeypatch, allocation_transform=stale)
    _assert_error(caught.value, "generation")


def test_active_duplicate_and_released_generation_reuse_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    _, rows = _allocations(runtime=runtime)
    buffers = _buffers(rows)
    first_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    first = _construct_context(first_kernel, runtime, buffers)
    duplicate_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    try:
        with pytest.raises(Exception) as caught:
            _construct_context(duplicate_kernel, runtime, buffers)
        _assert_error(caught.value, "registered")
        duplicate_kernel.close()

        _close_ready(first)
        reused_kernel, _, _ = _compile_fake(monkeypatch, loaded)
        with pytest.raises(Exception) as caught:
            _construct_context(reused_kernel, runtime, buffers)
        _assert_error(caught.value, "generation")
        reused_kernel.close()

        advanced = tuple(replace(row, generation=row.generation + 1) for row in rows)
        advanced_kernel, _, _ = _compile_fake(monkeypatch, loaded)
        next_context = _construct_context(
            advanced_kernel,
            runtime,
            _buffers(advanced),
        )
        _close_ready(next_context)
    finally:
        _close_ready(first)


@pytest.mark.parametrize("overlap_kind", ("same", "shifted", "contained"))
def test_fresh_owner_cannot_bypass_active_global_allocation_ranges(
    monkeypatch: pytest.MonkeyPatch,
    overlap_kind: str,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    _, first_rows = _allocations(runtime=runtime, generation_base=1000)
    first_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    first = _construct_context(first_kernel, runtime, _buffers(first_rows))
    try:
        _, second_rows = _allocations(
            runtime=runtime,
            owner_token=object(),
            generation_base=2000,
        )
        if overlap_kind == "shifted":
            second_rows = tuple(
                replace(
                    row,
                    base=row.pointer_snapshot + 8,
                    pointer_snapshot=row.pointer_snapshot + 8,
                )
                for row in second_rows
            )
        elif overlap_kind == "contained":
            second_rows = tuple(
                replace(
                    row,
                    base=0x4000000 + index * 0x100000,
                    pointer_snapshot=0x4000000 + index * 0x100000,
                )
                for index, row in enumerate(second_rows)
            )
            contained = first_rows[ROLES.index("basis_v")].pointer_snapshot + 8
            second_rows = _replace_role(
                second_rows,
                "reduced_state",
                base=contained,
                pointer_snapshot=contained,
            )
        second_kernel, _, _ = _compile_fake(monkeypatch, loaded)
        second: HipFgmresRecurrenceExecutionContextV2 | None = None
        try:
            second = _construct_context(
                second_kernel,
                runtime,
                _buffers(second_rows),
            )
        except Exception as exc:
            _assert_error(exc, "registered" if overlap_kind == "same" else "overlap")
        else:
            pytest.fail("fresh owner bypassed an active global allocation range")
        finally:
            if second is not None:
                _close_ready(second)
            elif not second_kernel.closed:
                second_kernel.close()
    finally:
        _close_ready(first)


def test_fresh_owner_cannot_reset_released_base_generation_high_water(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    _, rows = _allocations(runtime=runtime, generation_base=3000)
    first_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    first = _construct_context(first_kernel, runtime, _buffers(rows))
    _close_ready(first)

    _, reused = _allocations(
        runtime=runtime,
        owner_token=object(),
        generation_base=3000,
    )
    reused_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    rejected: HipFgmresRecurrenceExecutionContextV2 | None = None
    try:
        rejected = _construct_context(reused_kernel, runtime, _buffers(reused))
    except Exception as exc:
        _assert_error(exc, "generation")
    else:
        pytest.fail("fresh owner reset released allocation generation high-water")
    finally:
        if rejected is not None:
            _close_ready(rejected)
        elif not reused_kernel.closed:
            reused_kernel.close()

    advanced = tuple(replace(row, generation=row.generation + 1) for row in reused)
    advanced_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    next_context = _construct_context(advanced_kernel, runtime, _buffers(advanced))
    _close_ready(next_context)


@pytest.mark.parametrize("offset", (0, 8))
def test_distinct_sync_facades_cannot_bypass_global_active_ranges(
    monkeypatch: pytest.MonkeyPatch,
    offset: int,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    first_runtime = _exact_sync_runtime(loaded)
    second_runtime = _exact_sync_runtime(loaded)
    _, first_rows = _allocations(runtime=first_runtime, generation_base=5000)
    first_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    first = _construct_context(first_kernel, first_runtime, _buffers(first_rows))
    try:
        _, second_rows = _allocations(
            runtime=second_runtime,
            owner_token=object(),
            generation_base=6000,
        )
        second_rows = tuple(
            replace(
                row,
                base=row.pointer_snapshot + offset,
                pointer_snapshot=row.pointer_snapshot + offset,
            )
            for row in second_rows
        )
        second_kernel, _, _ = _compile_fake(monkeypatch, loaded)
        second: HipFgmresRecurrenceExecutionContextV2 | None = None
        try:
            second = _construct_context(
                second_kernel,
                second_runtime,
                _buffers(second_rows),
            )
        except Exception as exc:
            _assert_error(exc, "registered" if offset == 0 else "overlap")
        else:
            pytest.fail("a second sync facade bypassed the global range registry")
        finally:
            if second is not None:
                _close_ready(second)
            elif not second_kernel.closed:
                second_kernel.close()
    finally:
        _close_ready(first)


def test_distinct_sync_facade_cannot_reset_released_generation_high_water(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    first_runtime = _exact_sync_runtime(loaded)
    second_runtime = _exact_sync_runtime(loaded)
    _, first_rows = _allocations(runtime=first_runtime, generation_base=7000)
    first_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    first = _construct_context(first_kernel, first_runtime, _buffers(first_rows))
    _close_ready(first)

    _, reused = _allocations(
        runtime=second_runtime,
        owner_token=object(),
        generation_base=7000,
    )
    reused_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    rejected: HipFgmresRecurrenceExecutionContextV2 | None = None
    try:
        rejected = _construct_context(reused_kernel, second_runtime, _buffers(reused))
    except Exception as exc:
        _assert_error(exc, "generation")
    else:
        pytest.fail("a second sync facade reset allocation generation high-water")
    finally:
        if rejected is not None:
            _close_ready(rejected)
        elif not reused_kernel.closed:
            reused_kernel.close()


def test_distinct_native_runtime_wrappers_share_process_global_registry_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = BoundFakeLoadedRuntime()
    first_loaded = _native_loaded_runtime(backend, handle=0xA001)
    second_loaded = _native_loaded_runtime(backend, handle=0xB002)
    assert first_loaded is not second_loaded
    assert first_loaded.cdll._handle != second_loaded.cdll._handle
    first_runtime = _exact_sync_runtime(first_loaded)
    second_runtime = _exact_sync_runtime(second_loaded)
    first_owner = context_v2_module._registered_runtime_owner(first_runtime)
    second_owner = context_v2_module._registered_runtime_owner(second_runtime)
    assert first_owner is second_owner
    representative = first_owner.representative_runtime
    assert type(representative) is LoadedHipRuntime
    assert representative._loader_provenance_witness() is not None

    _, first_rows = _allocations(runtime=first_runtime, generation_base=9800)
    first_kernel, _, _ = _compile_fake(monkeypatch, first_loaded)
    first = _construct_context(first_kernel, first_runtime, _buffers(first_rows))
    _, second_rows = _allocations(
        runtime=second_runtime,
        owner_token=object(),
        generation_base=9800,
    )
    active_kernel, _, _ = _compile_fake(monkeypatch, second_loaded)
    try:
        with pytest.raises(Exception) as caught:
            _construct_context(
                active_kernel,
                second_runtime,
                _buffers(second_rows),
            )
        _assert_error(caught.value, "registered")
        assert active_kernel._checkpoint_owner_token is None
    finally:
        if not active_kernel.closed:
            active_kernel.close()
        _close_ready(first)

    stale_kernel, _, _ = _compile_fake(monkeypatch, second_loaded)
    with pytest.raises(Exception) as caught:
        _construct_context(stale_kernel, second_runtime, _buffers(second_rows))
    _assert_error(caught.value, "generation")
    assert stale_kernel._checkpoint_owner_token is None

    advanced = tuple(
        replace(allocation, generation=allocation.generation + 1)
        for allocation in second_rows
    )
    advanced_context = _construct_context(
        stale_kernel,
        second_runtime,
        _buffers(advanced),
    )
    _close_ready(advanced_context)


def test_distinct_injected_runtime_objects_keep_separate_registry_domains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_loaded = BoundFakeLoadedRuntime()
    second_loaded = BoundFakeLoadedRuntime()
    first_runtime = _exact_sync_runtime(first_loaded)
    second_runtime = _exact_sync_runtime(second_loaded)
    assert context_v2_module._registered_runtime_owner(
        first_runtime
    ) is not context_v2_module._registered_runtime_owner(second_runtime)
    _, first_rows = _allocations(runtime=first_runtime, generation_base=9900)
    _, second_rows = _allocations(runtime=second_runtime, generation_base=9900)
    first_kernel, _, _ = _compile_fake(monkeypatch, first_loaded)
    second_kernel, _, _ = _compile_fake(monkeypatch, second_loaded)
    first = _construct_context(first_kernel, first_runtime, _buffers(first_rows))
    second = _construct_context(second_kernel, second_runtime, _buffers(second_rows))
    try:
        assert len(first._registered) == len(ROLES)
        assert len(second._registered) == len(ROLES)
    finally:
        _close_ready(second)
        _close_ready(first)


def test_kernel_lease_open_failure_rolls_back_registry_and_generation_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    _, rows = _allocations(runtime=runtime, generation_base=4000)
    buffers = _buffers(rows)
    blocked_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    external_token = object()
    blocked_kernel._acquire_checkpoint_transaction_owner(
        _checkpoint_owner_token=external_token
    )
    with pytest.raises(Exception) as caught:
        _construct_context(blocked_kernel, runtime, buffers)
    _assert_error(caught.value, "lease")
    assert blocked_kernel.pending_stream_count == 0
    blocked_kernel.close(_checkpoint_owner_token=external_token)

    retry_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    retry = _construct_context(retry_kernel, runtime, buffers)
    _close_ready(retry)


def test_atomic_binding_snapshot_failure_leaves_no_lease_or_registry_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_snapshot = rtc_v2_module._checkpoint_binding_snapshot_values
    snapshot_calls = 0

    def fail_first_snapshot(witness: Any) -> tuple[Any, ...]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 1:
            raise RuntimeError("injected atomic binding snapshot failure")
        return original_snapshot(witness)

    monkeypatch.setattr(
        rtc_v2_module,
        "_checkpoint_binding_snapshot_values",
        fail_first_snapshot,
    )
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    _, rows = _allocations(runtime=runtime, generation_base=9600)
    buffers = _buffers(rows)
    failed_kernel, _, _ = _compile_fake(monkeypatch, loaded)

    with pytest.raises(Exception) as caught:
        _construct_context(failed_kernel, runtime, buffers)
    _assert_error(caught.value, "lease")
    assert snapshot_calls == 1
    assert failed_kernel._checkpoint_owner_token is None
    assert failed_kernel.pending_stream_count == 0
    failed_kernel.close()

    retry_kernel, _, _ = _compile_fake(monkeypatch, loaded)
    retry = _construct_context(retry_kernel, runtime, buffers)
    assert snapshot_calls > 1
    _close_ready(retry)


def test_checkpoint_transaction_is_exact_four_launch_program_and_single_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, loaded, runtime, buffers = _open_context(monkeypatch)
    predecessor = _issue(context, buffers)
    rows = first_column_checkpoint_transaction_launches_v2(F, M)
    assert len(rows) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    assert [row.submission_kind for row in rows] == [
        "control",
        "vector",
        "vector",
        "control",
    ]
    assert rows[1].name == "PREFLIGHT_COMMIT_SOURCE_COLUMN0"
    assert rows[2].name == "COMMIT_CHECKPOINT_COLUMN0"
    assert predecessor.schedule_epoch == START_SCHEDULE_EPOCH
    assert predecessor.reduction_epoch == REDUCTION_EPOCH
    assert rows[-1].expected_schedule_epoch + 1 == END_SCHEDULE_EPOCH
    assert {
        row.expected_reduction_epoch
        for row in rows
        if row.expected_reduction_epoch is not None
    } == {REDUCTION_EPOCH}
    assert context.state == "READY"
    assert kernel.pending_stream_count == 0

    pending = context.enqueue_checkpoint_transaction(predecessor)
    _assert_caller_attested_nonpromoting(predecessor)
    _assert_caller_attested_nonpromoting(pending)
    assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
    assert pending.state == "PENDING_FENCE"
    assert pending.checkpoint_schedule_hash == SCHEDULE_HASH
    assert pending.combined_abi_hash == COMBINED_ABI_HASH
    assert pending.kernel_identity_hash == kernel.identity.identity_hash
    assert pending.attempted_launch_count == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    assert (
        pending.accepted_launch_count_lower_bound == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    )
    assert (
        pending.accepted_launch_count_upper_bound == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    )
    assert not pending.completion_fence_observed
    assert not pending.poisoned
    assert context.last_transaction_receipt is pending
    assert context.state == "PENDING_FENCE"
    assert kernel.pending_stream_count == 1
    assert runtime.sync_streams == []

    assert [record["symbol"] for record in loaded.launch_records] == [
        row.kernel_symbol for row in rows
    ]
    assert [
        loaded.launch_records[0]["arguments"][1],
        loaded.launch_records[1]["arguments"][2],
        loaded.launch_records[2]["arguments"][2],
        loaded.launch_records[3]["arguments"][1],
    ] == [
        START_SCHEDULE_EPOCH,
        START_SCHEDULE_EPOCH + 1,
        START_SCHEDULE_EPOCH + 1,
        START_SCHEDULE_EPOCH + 2,
    ]
    control = hip_fgmres_control_state_abi_payload_v2()
    assert loaded.launch_records[0]["arguments"][:6] == (
        control["control_mode_codes"]["CHECKPOINT_DECIDE"],
        START_SCHEDULE_EPOCH,
        1,
        0,
        -1,
        -1,
    )
    assert loaded.launch_records[1]["arguments"][:7] == (
        control["vector_mode_codes"]["PREFLIGHT_COMMIT_SOURCE"],
        control["vector_gate_codes"]["COMMIT_REQUIRED"],
        START_SCHEDULE_EPOCH + 1,
        1,
        0,
        F,
        M,
    )
    assert loaded.launch_records[2]["arguments"][:7] == (
        control["vector_mode_codes"]["COMMIT_CHECKPOINT"],
        control["vector_gate_codes"]["COMMIT_REQUIRED"],
        START_SCHEDULE_EPOCH + 1,
        1,
        0,
        F,
        M,
    )
    assert loaded.launch_records[3]["arguments"][:6] == (
        control["control_mode_codes"]["CHECKPOINT_FINALIZE"],
        START_SCHEDULE_EPOCH + 2,
        1,
        0,
        -1,
        -1,
    )
    assert loaded.launch_records[0]["arguments"][-3:] == (
        buffers.dense.base,
        buffers.control_state.base,
        buffers.solve_record.base,
    )
    expected_vector_pointers = tuple(getattr(buffers, role).base for role in ROLES)
    assert loaded.launch_records[1]["arguments"][-11:] == expected_vector_pointers
    assert loaded.launch_records[2]["arguments"][-11:] == expected_vector_pointers
    assert loaded.launch_records[1]["stream"] == STREAM.value
    assert loaded.launch_records[2]["stream"] == STREAM.value

    fenced = context.synchronize_checkpoint_transaction(pending)
    _assert_caller_attested_nonpromoting(fenced)
    assert fenced is context.last_transaction_receipt
    assert fenced is not pending
    assert fenced.state == "FENCED"
    assert fenced.completion_fence_observed
    assert not fenced.poisoned
    assert (
        fenced.accepted_launch_count_lower_bound == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    )
    assert (
        fenced.accepted_launch_count_upper_bound == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    )
    assert runtime.sync_streams == [STREAM.value]
    assert kernel.pending_stream_count == 0
    assert context.state == "FENCED"

    context.close()
    assert context.state == "CLOSED"
    assert kernel.closed
    assert context._registered == {}


def test_predecessor_binds_mask_domain_without_host_observing_actual_device_mask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, _, _, buffers = _open_context(monkeypatch)
    try:
        parameters = inspect.signature(context.issue_predecessor_receipt).parameters
        assert "reduction_valid_mask" not in parameters
        predecessor = context.issue_predecessor_receipt(
            schedule_epoch=START_SCHEDULE_EPOCH,
            reduction_epoch=REDUCTION_EPOCH,
            source_generations=_active_generation_witness(buffers),
        )
        assert predecessor.reduction_valid_mask_domain == (0, 1792, 7936)
        assert predecessor.source_generations == _active_generation_witness(buffers)
        _assert_caller_attested_nonpromoting(predecessor)
    finally:
        _close_ready(context)


@pytest.mark.parametrize(
    ("domain", "sources", "fragment"),
    (
        ((0, 1792), None, "mask"),
        ((0, 1792, 7936, 7936), None, "mask"),
        ((0, 1792, 7936), (), "generation"),
        ((0, 1792, 7936), (("work_w", -1), ("basis_v", -1)), "generation"),
    ),
)
def test_mask_domain_and_conditional_source_generations_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    domain: tuple[int, ...],
    sources: tuple[tuple[str, int], ...] | None,
    fragment: str,
) -> None:
    context, _, _, _, buffers = _open_context(monkeypatch)
    try:
        with pytest.raises(Exception) as caught:
            context.issue_predecessor_receipt(
                schedule_epoch=START_SCHEDULE_EPOCH,
                reduction_epoch=REDUCTION_EPOCH,
                reduction_valid_mask_domain=domain,
                source_generations=(
                    _active_generation_witness(buffers) if sources is None else sources
                ),
            )
        _assert_error(caught.value, fragment)
    finally:
        _close_ready(context)


@pytest.mark.parametrize(
    ("schedule_epoch", "reduction_epoch", "fragment"),
    (
        (START_SCHEDULE_EPOCH - 1, REDUCTION_EPOCH, "schedule"),
        (START_SCHEDULE_EPOCH, REDUCTION_EPOCH - 1, "reduction"),
    ),
)
def test_predecessor_coordinates_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    schedule_epoch: int,
    reduction_epoch: int,
    fragment: str,
) -> None:
    context, _, _, _, _ = _open_context(monkeypatch)
    try:
        with pytest.raises(Exception) as caught:
            context.issue_predecessor_receipt(
                schedule_epoch=schedule_epoch,
                reduction_epoch=reduction_epoch,
                source_generations=_active_generation_witness(context.buffers),
            )
        _assert_error(caught.value, fragment)
    finally:
        _close_ready(context)


def test_exclusive_kernel_lease_rejects_every_raw_entrypoint_pre_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, loaded, _, _ = _open_context(monkeypatch)
    control = hip_fgmres_control_state_abi_payload_v2()
    calls = (
        lambda: _launch_control(
            kernel,
            STREAM,
            control["control_mode_codes"]["INIT"],
            0,
        ),
        lambda: _launch_vector(
            kernel,
            STREAM,
            control["vector_mode_codes"]["COPY_INITIAL_X"],
            1,
        ),
        lambda: _launch_spmv(kernel, STREAM, 7),
        lambda: _launch_reduction(
            kernel,
            STREAM,
            mode=control["reduction_mode_codes"]["LASSQ_LOAD"],
            target=control["reduction_target_codes"]["NONE"],
            schedule_epoch=2,
            reduction_epoch=0,
            value_count=F,
        ),
        lambda: kernel.acknowledge_stream_completion(STREAM),
        kernel.close,
    )
    try:
        for call in calls:
            with pytest.raises(Exception) as caught:
                call()
            _assert_error(caught.value, "lease")
            assert loaded.launch_records == []
            assert kernel.pending_stream_count == 0
            assert not kernel.closed

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(calls[index]) for index in (0, 1)]
        for future in futures:
            with pytest.raises(Exception) as caught:
                future.result()
            _assert_error(caught.value, "lease")
        assert loaded.launch_records == []
        assert kernel.pending_stream_count == 0
    finally:
        _close_ready(context)


def _forge_predecessor(
    receipt: HipFgmresCheckpointPredecessorReceiptV2,
    field: str,
    value: Any,
) -> HipFgmresCheckpointPredecessorReceiptV2:
    forged = object.__new__(HipFgmresCheckpointPredecessorReceiptV2)
    for name in receipt.__slots__:
        object.__setattr__(
            forged,
            name,
            value if name == field else getattr(receipt, name),
        )
    return forged


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("runtime", object()),
        ("device_ordinal", DEVICE_ORDINAL + 1),
        ("stream", ctypes.c_void_p(STREAM.value + 1)),
        ("stream_pointer", STREAM.value + 1),
        ("kernel", object()),
        ("kernel_identity", object()),
        ("kernel_identity_hash", "sha256:" + "0" * 64),
        ("combined_abi_hash", "sha256:" + "1" * 64),
        ("checkpoint_schedule_hash", "sha256:" + "2" * 64),
        ("free_dof_count", F + 1),
        ("restart_dimension", M + 1),
        ("maximum_restart_count", R + 1),
        ("schedule_epoch", START_SCHEDULE_EPOCH + 1),
        ("reduction_epoch", REDUCTION_EPOCH + 1),
        ("reduction_valid_mask_domain", (0, 1792)),
        ("source_generations", (("work_w", -1), ("basis_v", -1))),
        ("allocation_generations", ()),
    ),
)
def test_every_predecessor_binding_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    receipt = _issue(context, buffers)
    forged = _forge_predecessor(receipt, field, value)
    try:
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(forged)
        _assert_error(caught.value, "receipt")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        _close_ready(context)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evidence_scope", "authoritative_live_parent"),
        ("authoritative_predecessor_proven", True),
        ("live_krylov_parent_integrated", True),
        ("promotion_eligible", True),
        ("completion_fence_authoritative", False),
        ("combined_abi_hash", "sha256:" + "4" * 64),
        ("checkpoint_schedule_hash", "sha256:" + "5" * 64),
        ("free_dof_count", F + 1),
        ("allocation_generations", ()),
    ),
)
def test_same_issued_predecessor_object_tamper_is_rejected_prelaunch(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    receipt = _issue(context, buffers)
    original = getattr(receipt, field)
    object.__setattr__(receipt, field, value)
    try:
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(receipt)
        _assert_error(caught.value, "receipt")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        object.__setattr__(receipt, field, original)
        pending = context.enqueue_checkpoint_transaction(receipt)
        context.synchronize_checkpoint_transaction(pending)
        _close_ready(context)


def test_predecessor_is_immutable_foreign_single_issue_and_single_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, _, first_loaded, _, first_buffers = _open_context(monkeypatch)
    second, _, second_loaded, _, second_buffers = _open_context(monkeypatch)
    first_receipt = _issue(first, first_buffers)
    second_receipt = _issue(second, second_buffers)
    try:
        with pytest.raises(AttributeError):
            first_receipt.free_dof_count = F + 1  # type: ignore[misc]
        with pytest.raises(TypeError):
            replace(first_receipt, free_dof_count=F + 1)  # type: ignore[call-overload]
        with pytest.raises(Exception) as caught:
            first.issue_predecessor_receipt(
                schedule_epoch=START_SCHEDULE_EPOCH,
                reduction_epoch=REDUCTION_EPOCH,
                source_generations=_active_generation_witness(first_buffers),
            )
        _assert_error(caught.value, "issued")
        with pytest.raises(Exception) as caught:
            first.enqueue_checkpoint_transaction(second_receipt)
        _assert_error(caught.value, "receipt")
        assert first_loaded.launch_records == []
        assert second_loaded.launch_records == []

        pending = first.enqueue_checkpoint_transaction(first_receipt)
        with pytest.raises(Exception) as caught:
            first.enqueue_checkpoint_transaction(first_receipt)
        _assert_error(caught.value, "state")
        fenced = first.synchronize_checkpoint_transaction(pending)
        first.close()
        assert fenced.state == "FENCED"
    finally:
        _close_ready(first)
        _close_ready(second)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("transaction_id", "forged-transaction"),
        ("predecessor_id", "forged-predecessor"),
        ("evidence_scope", "authoritative_live_parent"),
        ("authoritative_predecessor_proven", True),
        ("live_krylov_parent_integrated", True),
        ("promotion_eligible", True),
        ("completion_fence_authoritative", False),
        ("state", "FENCED"),
        ("checkpoint_schedule_hash", "sha256:" + "1" * 64),
        ("combined_abi_hash", "sha256:" + "2" * 64),
        ("kernel_identity_hash", "sha256:" + "3" * 64),
        ("attempted_launch_count", 2),
        ("accepted_launch_count_lower_bound", 2),
        ("accepted_launch_count_upper_bound", 2),
        ("completion_fence_observed", True),
        ("poisoned", True),
    ),
)
def test_same_issued_transaction_receipt_tamper_is_rejected_before_fence(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    context, kernel, _, runtime, buffers = _open_context(monkeypatch)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    original = getattr(pending, field)
    object.__setattr__(pending, field, value)
    try:
        with pytest.raises(Exception) as caught:
            context.synchronize_checkpoint_transaction(pending)
        _assert_error(caught.value, "receipt")
        assert runtime.sync_streams == []
        assert kernel.pending_stream_count == 1
        assert context.state == "PENDING_FENCE"
    finally:
        object.__setattr__(pending, field, original)
        fenced = context.synchronize_checkpoint_transaction(pending)
        assert fenced.state == "FENCED"
        _close_ready(context)


def test_transaction_receipts_are_context_only_and_copy_forgery_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, _, runtime, buffers = _open_context(monkeypatch)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    values = {
        name: getattr(pending, name)
        for name in (
            "transaction_id",
            "predecessor_id",
            "state",
            "checkpoint_schedule_hash",
            "combined_abi_hash",
            "kernel_identity_hash",
            "attempted_launch_count",
            "accepted_launch_count_lower_bound",
            "accepted_launch_count_upper_bound",
            "completion_fence_observed",
            "poisoned",
        )
    }
    with pytest.raises(TypeError):
        HipFgmresCheckpointTransactionReceiptV2(**values)
    try:
        forged = replace(pending, poisoned=True)
    except TypeError:
        forged = None
    if forged is not None:
        with pytest.raises(Exception) as caught:
            context.synchronize_checkpoint_transaction(forged)
        _assert_error(caught.value, "receipt")
    assert runtime.sync_streams == []
    assert kernel.pending_stream_count == 1
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "FENCED"
    _close_ready(context)


@pytest.mark.parametrize(
    "field",
    ("source_sha256", "architecture", "runtime_library", "_code_object_witness"),
)
def test_nested_fixed_kernel_identity_drift_invalidates_issued_predecessor(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    predecessor = _issue(context, buffers)
    identity = predecessor.kernel_identity
    original = getattr(identity, field)
    replacement: Any
    if field == "source_sha256":
        replacement = "sha256:" + "0" * 64
    elif field == "architecture":
        replacement = "gfx000"
    elif field == "runtime_library":
        replacement = replace(original, sha256="sha256:" + "9" * 64)
    else:
        replacement = b"forged-code-object"
    object.__setattr__(identity, field, replacement)
    try:
        with pytest.raises(Exception) as caught:
            context.enqueue_checkpoint_transaction(predecessor)
        _assert_error(caught.value, "identity")
        assert context.state == "READY"
        assert loaded.launch_records == []
    finally:
        object.__setattr__(identity, field, original)
        pending = context.enqueue_checkpoint_transaction(predecessor)
        context.synchronize_checkpoint_transaction(pending)
        _close_ready(context)


def test_pending_transaction_forbids_ack_close_release_reuse_and_suffix_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, loaded, _, buffers = _open_context(monkeypatch)
    predecessor = _issue(context, buffers)
    pending = context.enqueue_checkpoint_transaction(predecessor)
    assert len(loaded.launch_records) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    assert context.state == "PENDING_FENCE"
    for call, fragment in (
        (lambda: kernel.acknowledge_stream_completion(STREAM), "lease"),
        (context.close, "pending"),
        (lambda: context.release_allocation(buffers.work_w), "pending"),
        (
            lambda: context.enqueue_checkpoint_transaction(predecessor),
            "state",
        ),
    ):
        with pytest.raises(Exception) as caught:
            call()
        _assert_error(caught.value, fragment)
    assert len(loaded.launch_records) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    assert context.state == "PENDING_FENCE"
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "FENCED"
    _close_ready(context)


def test_two_thread_enqueue_race_has_one_transaction_and_no_duplicate_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, loaded, _, buffers = _open_context(monkeypatch)
    predecessor = _issue(context, buffers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(context.enqueue_checkpoint_transaction, predecessor)
            for _ in range(2)
        ]
    successes: list[HipFgmresCheckpointTransactionReceiptV2] = []
    failures: list[BaseException] = []
    for future in futures:
        try:
            successes.append(future.result())
        except BaseException as exc:
            failures.append(exc)
    assert len(successes) == len(failures) == 1
    _assert_error(failures[0], "state")
    assert len(loaded.launch_records) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    assert context.last_transaction_receipt is successes[0]
    fenced = context.synchronize_checkpoint_transaction(successes[0])
    assert fenced.state == "FENCED"
    _close_ready(context)


@pytest.mark.parametrize("raise_at", (1, 2, 3, 4))
def test_each_launch_exception_poison_retains_exact_ambiguous_prefix_and_no_suffix(
    monkeypatch: pytest.MonkeyPatch,
    raise_at: int,
) -> None:
    loaded = SequencedLoadedRuntime(raise_at=raise_at)
    context, kernel, _, runtime, buffers = _open_context(
        monkeypatch, loaded_runtime=loaded
    )
    predecessor = _issue(context, buffers)
    with pytest.raises(Exception) as caught:
        context.enqueue_checkpoint_transaction(predecessor)
    _assert_error(caught.value, "launch")
    pending = getattr(caught.value, "transaction_receipt", None)
    assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
    assert pending is context.last_transaction_receipt
    assert pending.state == "POISONED_PENDING_FENCE"
    assert pending.poisoned
    assert pending.attempted_launch_count == raise_at
    assert pending.accepted_launch_count_lower_bound == raise_at - 1
    assert pending.accepted_launch_count_upper_bound == raise_at
    assert len(loaded.launch_records) == raise_at
    assert kernel.pending_stream_count == 1
    assert context.state == "POISONED_PENDING_FENCE"

    with pytest.raises(Exception):
        context.enqueue_checkpoint_transaction(predecessor)
    assert len(loaded.launch_records) == raise_at
    with pytest.raises(Exception):
        context.close()

    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "POISONED_FENCED"
    assert fenced.poisoned
    assert fenced.completion_fence_observed
    assert runtime.sync_streams == [STREAM.value]
    assert kernel.pending_stream_count == 0
    _close_ready(context)


def test_non_none_launch_return_is_ambiguous_poison_and_never_enqueues_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HipRtcFgmresV2Kernel.launch_vector
    calls: list[tuple[Any, ...]] = []

    def non_none(self: Any, *arguments: Any, **kwargs: Any) -> object:
        calls.append(arguments)
        original(self, *arguments, **kwargs)
        return object()

    monkeypatch.setattr(HipRtcFgmresV2Kernel, "launch_vector", non_none)
    context, kernel, loaded, _, buffers = _open_context(monkeypatch)
    assert type(kernel) is HipRtcFgmresV2Kernel
    predecessor = _issue(context, buffers)
    with pytest.raises(Exception) as caught:
        context.enqueue_checkpoint_transaction(predecessor)
    _assert_error(caught.value, "return")
    pending = getattr(caught.value, "transaction_receipt", None)
    assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
    assert pending is context.last_transaction_receipt
    assert pending.state == "POISONED_PENDING_FENCE"
    assert pending.attempted_launch_count == 2
    assert pending.accepted_launch_count_lower_bound == 1
    assert pending.accepted_launch_count_upper_bound == 2
    assert len(loaded.launch_records) == 2
    assert len(calls) == 1
    assert kernel.pending_stream_count == 1
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "POISONED_FENCED"
    _close_ready(context)


def test_pre_runtime_launch_contract_failure_is_exact_not_attempted_no_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PreRuntimeFailure(RuntimeError):
        launch_disposition = "not_attempted"

    def fail_before_runtime(self: Any, *arguments: Any, **kwargs: Any) -> None:
        del self, arguments, kwargs
        raise PreRuntimeFailure("injected pre-runtime contract failure")

    monkeypatch.setattr(HipRtcFgmresV2Kernel, "launch_control", fail_before_runtime)
    context, kernel, loaded, runtime, buffers = _open_context(monkeypatch)
    with pytest.raises(Exception) as caught:
        context.enqueue_checkpoint_transaction(_issue(context, buffers))
    pending = getattr(caught.value, "transaction_receipt", None)
    assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
    assert pending.attempted_launch_count == 0
    assert pending.accepted_launch_count_lower_bound == 0
    assert pending.accepted_launch_count_upper_bound == 0
    assert pending.state == "POISONED_NO_WORK"
    assert pending.poisoned
    assert not pending.completion_fence_observed
    assert context.state == "POISONED_NO_WORK"
    assert loaded.launch_records == []
    assert kernel.pending_stream_count == 0
    assert runtime.sync_streams == []
    _close_ready(context)


@pytest.mark.parametrize("reject_at", (1, 2, 3, 4))
def test_definitive_launch_status_rejection_has_exact_accepted_prefix(
    monkeypatch: pytest.MonkeyPatch,
    reject_at: int,
) -> None:
    loaded = SequencedStatusLoadedRuntime(
        reject_at=reject_at,
        sync_fail_count=(1 if reject_at == 1 else 0),
    )
    runtime = _exact_sync_runtime(loaded)
    context, kernel, _, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded,
        sync_runtime=runtime,
    )
    predecessor = _issue(context, buffers)
    with pytest.raises(Exception) as caught:
        context.enqueue_checkpoint_transaction(predecessor)
    pending = getattr(caught.value, "transaction_receipt", None)
    assert type(pending) is HipFgmresCheckpointTransactionReceiptV2
    assert pending.attempted_launch_count == reject_at
    assert pending.accepted_launch_count_lower_bound == reject_at - 1
    assert pending.accepted_launch_count_upper_bound == reject_at - 1
    assert len(loaded.launch_records) == reject_at
    if reject_at == 1:
        assert pending.state == "POISONED_NO_WORK"
        assert context.state == "POISONED_NO_WORK"
        assert not pending.completion_fence_observed
        assert kernel.pending_stream_count == 0
        assert runtime.sync_streams == []
        _close_ready(context)
        assert loaded.sync_fail_count == 1
    else:
        assert pending.state == "POISONED_PENDING_FENCE"
        assert context.state == "POISONED_PENDING_FENCE"
        assert kernel.pending_stream_count == 1
        fenced = context.synchronize_checkpoint_transaction(pending)
        assert fenced.state == "POISONED_FENCED"
        _close_ready(context)


def test_sync_failure_retains_cleanup_authority_and_retry_does_the_only_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_runtime = BoundFakeLoadedRuntime(sync_fail_count=1)
    runtime = _exact_sync_runtime(loaded_runtime)
    context, kernel, loaded, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded_runtime,
        sync_runtime=runtime,
    )
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    with pytest.raises(Exception) as caught:
        context.synchronize_checkpoint_transaction(pending)
    _assert_error(caught.value, "synchron")
    retry_receipt = context.last_transaction_receipt
    assert retry_receipt is not None
    assert context.state == "POISONED_PENDING_FENCE"
    assert retry_receipt.state == "POISONED_PENDING_FENCE"
    assert not retry_receipt.completion_fence_observed
    assert kernel.pending_stream_count == 1
    assert runtime.sync_streams == [STREAM.value]
    with pytest.raises(Exception):
        context.release_allocation(buffers.work_w)
    with pytest.raises(Exception):
        context.close()
    with pytest.raises(Exception):
        context.enqueue_checkpoint_transaction(_issue(context, buffers))
    assert len(loaded.launch_records) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT

    fenced = context.synchronize_checkpoint_transaction(retry_receipt)
    assert fenced.state == "POISONED_FENCED"
    assert fenced.completion_fence_observed
    assert kernel.pending_stream_count == 0
    assert runtime.sync_streams == [STREAM.value, STREAM.value]
    _close_ready(context)


def test_device_drift_before_sync_retains_pending_until_device_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, loaded, runtime, buffers = _open_context(monkeypatch)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    loaded.current_device = DEVICE_ORDINAL + 1
    with pytest.raises(Exception) as caught:
        context.synchronize_checkpoint_transaction(pending)
    _assert_error(caught.value, "device")
    assert context.state == "PENDING_FENCE"
    assert kernel.pending_stream_count == 1
    assert runtime.sync_streams == []

    loaded.current_device = DEVICE_ORDINAL
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "FENCED"
    assert kernel.pending_stream_count == 0
    assert runtime.sync_streams == [STREAM.value]
    _close_ready(context)


def test_device_drift_during_sync_defers_consume_without_second_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    context, kernel, _, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded,
        sync_runtime=runtime,
    )
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))

    def drift_after_fence() -> None:
        loaded.current_device = DEVICE_ORDINAL + 1
        loaded.sync_callback = None

    loaded.sync_callback = drift_after_fence
    with pytest.raises(Exception) as caught:
        context.synchronize_checkpoint_transaction(pending)
    retry = getattr(caught.value, "transaction_receipt", None)
    assert type(retry) is HipFgmresCheckpointTransactionReceiptV2
    assert retry.state == "FENCE_OBSERVED_ACK_PENDING"
    assert context.state == "FENCE_OBSERVED_ACK_PENDING"
    assert kernel.pending_stream_count == 1
    assert runtime.sync_streams == [STREAM.value]

    loaded.current_device = DEVICE_ORDINAL
    fenced = context.synchronize_checkpoint_transaction(retry)
    assert fenced.state == "POISONED_FENCED"
    assert fenced.completion_fence_observed
    assert kernel.pending_stream_count == 0
    assert runtime.sync_streams == [STREAM.value]
    _close_ready(context)


def test_device_drift_before_close_retains_lease_and_registry_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, kernel, loaded, _, _ = _open_context(monkeypatch)
    owner_token = context._checkpoint_owner_token
    loaded.current_device = DEVICE_ORDINAL + 1
    with pytest.raises(Exception) as caught:
        context.close()
    _assert_error(caught.value, "device")
    assert context.state == "READY"
    assert not kernel.closed
    assert kernel._checkpoint_owner_token is owner_token
    assert loaded.unload_calls == 0
    assert len(context._registered) == len(ROLES)

    loaded.current_device = DEVICE_ORDINAL
    context.close()
    assert context.state == "CLOSED"
    assert kernel.closed
    assert kernel._checkpoint_owner_token is None
    assert loaded.unload_calls == 1
    assert context._registered == {}


def test_pending_count_exception_during_context_open_is_pre_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HipRtcFgmresV2Kernel.pending_stream_count

    def fail_pending_count(self: Any) -> int:
        del self
        raise RuntimeError("injected pending getter failure")

    loaded = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded)
    kernel, _, _ = _compile_fake(monkeypatch, loaded)
    _, rows = _allocations(runtime=runtime, generation_base=8000)
    buffers = _buffers(rows)
    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "pending_stream_count",
        property(fail_pending_count),
    )
    with pytest.raises(Exception) as caught:
        _construct_context(kernel, runtime, buffers)
    _assert_error(caught.value, "pending")

    monkeypatch.setattr(HipRtcFgmresV2Kernel, "pending_stream_count", original)
    retry = _construct_context(kernel, runtime, buffers)
    _close_ready(retry)


@pytest.mark.parametrize("reported_count", (0, 3, 5))
def test_atomic_consume_wrong_count_poison_clears_map_and_is_closable(
    monkeypatch: pytest.MonkeyPatch,
    reported_count: int,
) -> None:
    original = HipRtcFgmresV2Kernel._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def wrong_count(self: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        assert original(self, token, stream) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
        return reported_count

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_consume_checkpoint_pending_after_fence",
        wrong_count,
    )
    context, kernel, _, runtime, buffers = _open_context(monkeypatch)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    with pytest.raises(Exception) as caught:
        context.synchronize_checkpoint_transaction(pending)
    terminal = getattr(caught.value, "transaction_receipt", None)
    assert terminal is context.last_transaction_receipt
    assert type(terminal) is HipFgmresCheckpointTransactionReceiptV2
    assert terminal.state == "POISONED_FENCED"
    assert terminal.completion_fence_observed
    assert terminal.poisoned
    assert runtime.sync_streams == [STREAM.value]
    assert consume_calls == 1
    assert kernel.pending_stream_count == 0
    _close_ready(context)


def test_atomic_consume_exception_before_pop_retries_without_second_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HipRtcFgmresV2Kernel._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def fail_before_pop(self: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        if consume_calls == 1:
            raise RuntimeError("injected pre-consume exception")
        return int(original(self, token, stream))

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_consume_checkpoint_pending_after_fence",
        fail_before_pop,
    )
    context, kernel, _, runtime, buffers = _open_context(monkeypatch)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    with pytest.raises(Exception) as caught:
        context.synchronize_checkpoint_transaction(pending)
    retry = getattr(caught.value, "transaction_receipt", None)
    assert retry is context.last_transaction_receipt
    assert type(retry) is HipFgmresCheckpointTransactionReceiptV2
    assert retry.state == "FENCE_OBSERVED_ACK_PENDING"
    assert retry.poisoned
    assert consume_calls == 1
    assert kernel.pending_stream_count == 1
    assert runtime.sync_streams == [STREAM.value]

    fenced = context.synchronize_checkpoint_transaction(retry)
    assert fenced.state == "POISONED_FENCED"
    assert fenced.poisoned
    assert consume_calls == 2
    assert runtime.sync_streams == [STREAM.value]
    assert kernel.pending_stream_count == 0
    _close_ready(context)


def test_atomic_consume_exception_after_pop_retries_as_already_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HipRtcFgmresV2Kernel._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def pop_then_fail(self: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        consumed = int(original(self, token, stream))
        if consume_calls == 1:
            assert consumed == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
            raise RuntimeError("injected post-consume exception")
        assert consumed == 0
        return consumed

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_consume_checkpoint_pending_after_fence",
        pop_then_fail,
    )
    context, kernel, _, runtime, buffers = _open_context(monkeypatch)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    with pytest.raises(Exception) as caught:
        context.synchronize_checkpoint_transaction(pending)
    retry_receipt = getattr(caught.value, "transaction_receipt", None)
    assert retry_receipt is context.last_transaction_receipt
    assert type(retry_receipt) is HipFgmresCheckpointTransactionReceiptV2
    assert retry_receipt.state == "FENCE_OBSERVED_ACK_PENDING"
    assert runtime.sync_streams == [STREAM.value]
    assert kernel.pending_stream_count == 0
    assert retry_receipt.poisoned
    assert consume_calls == 1
    with pytest.raises(Exception):
        context.close()

    fenced = context.synchronize_checkpoint_transaction(retry_receipt)
    assert fenced.state == "POISONED_FENCED"
    assert fenced.poisoned
    assert runtime.sync_streams == [STREAM.value]
    assert kernel.pending_stream_count == 0
    assert consume_calls == 2
    _close_ready(context)


def test_module_close_failure_retains_registry_and_is_retryable_before_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = BoundFakeLoadedRuntime(unload_statuses=(7, 0))
    context, kernel, _, _, buffers = _open_context(monkeypatch, loaded_runtime=loaded)
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    context.synchronize_checkpoint_transaction(pending)
    with pytest.raises(Exception) as caught:
        context.close()
    _assert_error(caught.value, "close")
    assert context.state == "FENCED"
    assert not kernel.closed
    assert len(context._registered) == len(ROLES)
    with pytest.raises(Exception):
        context.release_allocation(buffers.work_w)

    context.close()
    assert context.state == "CLOSED"
    assert kernel.closed
    assert loaded.unload_calls == 2
    assert context._registered == {}
    context.close()


@pytest.mark.parametrize(
    "field",
    (
        "base",
        "pointer_snapshot",
        "nbytes",
        "element_type",
        "owner_token",
        "generation",
        "runtime",
        "device_ordinal",
    ),
)
def test_close_bulk_cleanup_uses_allocation_snapshots_after_descriptor_mutation(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    context, kernel, loaded, _, buffers = _open_context(monkeypatch)
    allocation = buffers.work_w
    original = getattr(allocation, field)
    mutated = _mutated_allocation_value(
        field,
        allocation,
        loaded_runtime=loaded,
    )
    object.__setattr__(allocation, field, mutated)
    try:
        context.close()
        assert context.state == "CLOSED"
        assert kernel.closed
        assert loaded.unload_calls == 1
        assert context._registered == {}
    finally:
        object.__setattr__(allocation, field, original)
        if context.state != "CLOSED":
            context.close()


def test_registry_cleanup_failure_retries_without_second_kernel_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = context_v2_module._bulk_release_registered_allocations
    cleanup_calls = 0

    def fail_once(context_token: object, candidates: Any) -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            raise RuntimeError("injected bulk registry cleanup failure")
        original(context_token, candidates)

    monkeypatch.setattr(
        context_v2_module,
        "_bulk_release_registered_allocations",
        fail_once,
    )
    context, kernel, loaded, _, _ = _open_context(monkeypatch)
    with pytest.raises(Exception) as caught:
        context.close()
    _assert_error(caught.value, "cleanup")
    assert context.state == "CLEANUP_FAILED"
    assert kernel.closed
    assert loaded.unload_calls == 1
    assert len(context._registered) == len(ROLES)

    context.close()
    assert context.state == "CLOSED"
    assert cleanup_calls == 2
    assert loaded.unload_calls == 1
    assert context._registered == {}


def test_sync_callback_reentry_is_pre_mutation_and_outer_fences_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_consume = HipRtcFgmresV2Kernel._consume_checkpoint_pending_after_fence
    consume_calls = 0

    def counted_consume(self: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        return int(original_consume(self, token, stream))

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_consume_checkpoint_pending_after_fence",
        counted_consume,
    )
    loaded_runtime = BoundFakeLoadedRuntime()
    runtime = _exact_sync_runtime(loaded_runtime)
    context, _, loaded, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded_runtime,
        sync_runtime=runtime,
    )
    predecessor = _issue(context, buffers)
    pending = context.enqueue_checkpoint_transaction(predecessor)
    reentrant_errors: list[BaseException] = []

    def reenter() -> None:
        loaded_runtime.sync_callback = None
        calls = (
            lambda: context.synchronize_checkpoint_transaction(pending),
            lambda: context.enqueue_checkpoint_transaction(predecessor),
            context.close,
            lambda: context.release_allocation(buffers.work_w),
        )
        for call in calls:
            try:
                call()
            except BaseException as exc:
                reentrant_errors.append(exc)

    loaded_runtime.sync_callback = reenter
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "FENCED"
    assert len(reentrant_errors) == 4
    assert all(
        "state" in str(exc).lower() or "operation" in str(exc).lower()
        for exc in reentrant_errors
    )
    assert runtime.sync_streams == [STREAM.value]
    assert consume_calls == 1
    assert len(loaded.launch_records) == CHECKPOINT_TRANSACTION_LAUNCH_COUNT
    _close_ready(context)


def test_consume_callback_reentry_is_pre_mutation_and_outer_consumes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_consume = HipRtcFgmresV2Kernel._consume_checkpoint_pending_after_fence
    callback_errors: list[BaseException] = []
    consume_calls = 0
    context_holder: dict[str, Any] = {}

    def reentrant_consume(self: Any, token: object, stream: Any) -> int:
        nonlocal consume_calls
        consume_calls += 1
        context = context_holder["context"]
        receipt = context.last_transaction_receipt
        for call in (
            lambda: context.synchronize_checkpoint_transaction(receipt),
            context.close,
        ):
            try:
                call()
            except BaseException as exc:
                callback_errors.append(exc)
        return int(original_consume(self, token, stream))

    monkeypatch.setattr(
        HipRtcFgmresV2Kernel,
        "_consume_checkpoint_pending_after_fence",
        reentrant_consume,
    )
    context, kernel, _, runtime, buffers = _open_context(monkeypatch)
    context_holder["context"] = context
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    fenced = context.synchronize_checkpoint_transaction(pending)
    assert fenced.state == "FENCED"
    assert len(callback_errors) == 2
    assert all(
        "state" in str(exc).lower() or "operation" in str(exc).lower()
        for exc in callback_errors
    )
    assert runtime.sync_streams == [STREAM.value]
    assert consume_calls == 1
    assert kernel.pending_stream_count == 0
    _close_ready(context)


def test_unload_callback_close_reentry_is_pre_mutation_and_unloads_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = ReentrantUnloadLoadedRuntime()
    context, kernel, _, _, buffers = _open_context(
        monkeypatch,
        loaded_runtime=loaded,
    )
    pending = context.enqueue_checkpoint_transaction(_issue(context, buffers))
    context.synchronize_checkpoint_transaction(pending)
    callback_errors: list[BaseException] = []

    def reenter_close() -> None:
        try:
            context.close()
        except BaseException as exc:
            callback_errors.append(exc)

    loaded.unload_callback = reenter_close
    context.close()
    assert context.state == "CLOSED"
    assert kernel.closed
    assert loaded.unload_calls == 1
    assert len(callback_errors) == 1
    assert (
        "state" in str(callback_errors[0]).lower()
        or "operation" in str(callback_errors[0]).lower()
    )
    _close_ready(context)
