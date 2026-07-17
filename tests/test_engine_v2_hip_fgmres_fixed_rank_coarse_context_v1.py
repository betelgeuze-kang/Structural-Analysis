from __future__ import annotations

import ctypes
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixed_rank_coarse_context_v1 as context_module,
    fgmres_fixed_rank_coarse_rtc_v1 as rtc_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_context_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION,
    HipFgmresFixedRankCoarseContextV1Error,
    open_hip_fgmres_fixed_rank_coarse_context_v1,
    validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1,
    validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1,
    compile_hip_fgmres_fixed_rank_coarse_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseKernelV1,
    _KERNEL_MINT,
)
from structural_analysis.engine_v2.assembly_backend.hip_allocation_lineage import (
    HipAllocationOwnerV1,
    snapshot_hip_allocation_owner_cleanup_v1,
    validate_hip_allocation_borrow_v1,
)
from structural_analysis.engine_v2.backends.hip.context import (
    HipFreeKnownNotFreedError,
)
from structural_analysis.engine_v2.rtc_backend.rtc import HipRtcLibraryIdentity
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
)

from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    HipFgmresLiveCheckpointContextV1Error,
    _cleanup as _cleanup_live,
    _open_live,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/hip_fgmres_fixed_rank_coarse_context_v1.schema.json"
)
APPLICATION_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/hip_fgmres_fixed_rank_coarse_application_v1.schema.json"
)
PARENT_ROLES = ("jacobi_inverse", "basis_v", "preconditioned_basis_z")
OWNED_ROLES = (
    "coarse_physical_basis_z",
    "coarse_operator_basis_az",
    "coarse_cholesky_l",
    "coarse_rhs",
    "coarse_coefficients",
    "coarse_status",
)


class _CoarseModuleApi:
    def __init__(self, loaded_runtime: Any) -> None:
        self._runtime = loaded_runtime
        self.launches: list[dict[str, Any]] = []
        self.launch_outcomes: list[int | BaseException] = []
        self.launch_callback: Any | None = None
        self.unload_outcome: int | BaseException = 0
        self.unload_count = 0

    def launch(self, function: object, **keywords: Any) -> int:
        self.launches.append({"function": function, **keywords})
        if self.launch_callback is not None:
            self.launch_callback(len(self.launches))
        outcome = self.launch_outcomes.pop(0) if self.launch_outcomes else 0
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def unload(self, _module: object) -> int:
        self.unload_count += 1
        if isinstance(self.unload_outcome, BaseException):
            raise self.unload_outcome
        return self.unload_outcome

    def error_string(self, status: int) -> str:
        return f"status={status}"


def _compile_coarse_plan(live_context: Any) -> Any:
    source_plan = live_context._source_plan
    execution = source_plan._source_execution_plan
    basis = np.eye(
        source_plan.free_dof_count,
        min(2, source_plan.free_dof_count),
        dtype="<f8",
    )
    coarse = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        execution,
        basis,
        rank_cap=2,
    )
    return compile_hip_fgmres_fixed_rank_coarse_plan_v1(source_plan, coarse)


def _coarse_kernel(runtime: Any, plan: Any) -> tuple[Any, _CoarseModuleApi]:
    loaded = runtime._loaded
    api = _CoarseModuleApi(loaded)
    identity = rtc_module._build_identity(
        architecture="gfx1030",
        source_hash=plan.kernel_source_hash,
        options=(
            "--offload-arch=gfx1030",
            "-O3",
            "-std=c++17",
            "-ffp-contract=off",
        ),
        rtc_version=(9, 1),
        rtc_library=HipRtcLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libhiprtc.so",
            loaded_name="fake-libhiprtc.so",
            resolved_path="/fake/libhiprtc.so",
            sha256="sha256:" + "2" * 64,
        ),
        runtime_library=loaded.library_identity,
        code_object=b"fixed-rank-coarse-context-test-code-object",
    )
    functions = {
        symbol: ctypes.c_void_p(index + 2)
        for index, symbol in enumerate(HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1)
    }
    kernel = HipRtcFgmresFixedRankCoarseKernelV1(
        runtime=api,  # type: ignore[arg-type]
        module=ctypes.c_void_p(1),
        functions=functions,
        identity=identity,
        _mint=_KERNEL_MINT,
    )
    return kernel, api


def _prepare(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    live_items = _open_live(monkeypatch)
    runtime = live_items[0]
    live = live_items[-1]
    assert live.context is not None
    plan = _compile_coarse_plan(live.context)
    kernel, api = _coarse_kernel(runtime, plan)
    return (*live_items, plan, kernel, api)


def _cleanup_all(coarse: Any, live_items: tuple[Any, ...]) -> None:
    if coarse is not None and coarse.context is not None and not coarse.context.closed:
        coarse.context.close()
    (
        _,
        parent_open,
        resident_open,
        free_open,
        _,
        opened,
        _,
        _,
        live,
    ) = live_items
    _cleanup_live(live, opened, free_open, resident_open, parent_open)


def test_live_coarse_context_binds_exact_parent3_owned6_and_closes_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, _, _, _, _, _, _, _, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    h2d_before = runtime.h2d_attempt_count
    sync_before = len(runtime.sync_streams)
    allocation_baseline = set(runtime.allocations)
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert coarse.ready and context is not None and coarse.receipt is not None
    try:
        receipt = validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(
            coarse.receipt,
            expected_context=context,
        )
        assert receipt.status == "context_ready"
        assert receipt.schema_version == (
            HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION
        )
        assert receipt.actual_backend == "test_double"
        assert tuple(row.name for row in receipt.owned_buffers) == OWNED_ROLES
        assert receipt.dimensions.parent_capability_count == 3
        assert receipt.dimensions.owned_capability_count == 6
        assert receipt.telemetry.allocation_success_count == 6
        assert receipt.telemetry.h2d_operation_success_count == 3
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.fence_acknowledged_launch_count == 0
        assert runtime.h2d_attempt_count - h2d_before == 3
        assert len(runtime.sync_streams) - sync_before == 1
        assert runtime.h2d_streams[-3:] == [parent._stream] * 3
        np.testing.assert_array_equal(
            runtime.h2d_arrays[-3],
            plan._source_coarse_space.physical_basis_z,
        )
        np.testing.assert_array_equal(
            runtime.h2d_arrays[-2],
            plan._source_coarse_space.operator_basis_az,
        )
        np.testing.assert_array_equal(
            runtime.h2d_arrays[-1],
            plan._source_coarse_space.coarse_cholesky_l,
        )

        authority = context._parent_authority
        assert authority is not None
        assert tuple(row.role for row in authority.source_capabilities) == PARENT_ROLES
        assert authority.source_capabilities[0] is parent._group_capabilities[2]
        assert authority.source_capabilities[1] is parent._owned_capabilities["basis_v"]
        assert (
            authority.source_capabilities[2]
            is parent._owned_capabilities["preconditioned_basis_z"]
        )
        assert authority.parent_group_lease is parent._group_lease
        validate_hip_allocation_borrow_v1(authority.parent_group_lease)
        owner = context._allocation_owner
        assert owner is not None
        capabilities, free_leases, orphan_leases = (
            snapshot_hip_allocation_owner_cleanup_v1(owner)
        )
        assert tuple(row.role for row in capabilities) == OWNED_ROLES
        assert free_leases == () and orphan_leases == ()
        owned_pointers = {row.pointer_snapshot for row in capabilities}
        assert owned_pointers.isdisjoint(allocation_baseline)

        with pytest.raises(
            HipFgmresLiveCheckpointContextV1Error,
            match="coarse_child_active",
        ):
            parent.close()

        events: list[str] = []
        original_free = runtime.free

        def observed_free(pointer: int) -> None:
            events.append("owned_free")
            original_free(pointer)

        monkeypatch.setattr(runtime, "free", observed_free)
        original_owner_close = HipAllocationOwnerV1.close

        def observed_owner_close(
            owner: HipAllocationOwnerV1, *args: Any, **kwargs: Any
        ) -> None:
            if owner is context._allocation_owner:
                events.append("owner_close")
            original_owner_close(owner, *args, **kwargs)

        monkeypatch.setattr(HipAllocationOwnerV1, "close", observed_owner_close)
        original_parent_release = type(parent)._release_fixed_rank_coarse_child

        def observed_parent_release(
            live_context: Any,
            token: object,
            child_context: object,
        ) -> None:
            if live_context is parent:
                events.append("parent_release")
            original_parent_release(live_context, token, child_context)

        monkeypatch.setattr(
            type(parent),
            "_release_fixed_rank_coarse_child",
            observed_parent_release,
        )
        context.close()
        assert context.closed and kernel.closed and api.unload_count == 1
        assert owned_pointers.isdisjoint(runtime.allocations)
        assert events.count("owned_free") == 6
        assert events[-2:] == ["owner_close", "parent_release"]
        assert parent._fixed_rank_coarse_child_token is None
        terminal = context.receipt()
        assert terminal.status == "context_closed"
        assert terminal.telemetry.deallocation_success_count == 6
        assert terminal.telemetry.parent_delegation_release_success_count == 1
    finally:
        _cleanup_all(coarse, live_items)


def test_application_window_is_exact_four_launches_and_zero_host_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    assert live.context is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        live.context,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    try:
        before = (
            runtime.h2d_attempt_count,
            len(runtime.d2h_streams),
            runtime.malloc_calls,
            len(runtime.sync_streams),
            len(runtime.allocations),
            len(api.launches),
        )
        application = context.enqueue_application(1)
        validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(
            application,
            expected_context=context,
        )
        after = (
            runtime.h2d_attempt_count,
            len(runtime.d2h_streams),
            runtime.malloc_calls,
            len(runtime.sync_streams),
            len(runtime.allocations),
            len(api.launches),
        )
        assert tuple(
            right - left for left, right in zip(before, after, strict=True)
        ) == (
            0,
            0,
            0,
            0,
            0,
            4,
        )
        assert application.accepted_launch_count == 4
        assert kernel.pending
        assert context.fence() == 4
        assert not kernel.pending
        assert len(runtime.sync_streams) == before[3] + 1
        receipt = context.receipt()
        assert receipt.telemetry.application_success_count == 1
        assert receipt.telemetry.kernel_launch_success_count == 4
        assert receipt.telemetry.fence_success_count == 2
        assert receipt.telemetry.fence_acknowledged_launch_count == 4
    finally:
        _cleanup_all(coarse, live_items)


def test_partial_launch_rejection_poison_is_fenced_before_terminal_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    _, *_, live = live_items
    plan, kernel, api = prepared[9:]
    assert live.context is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        live.context,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    api.launch_outcomes[:] = [0, 7]
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error) as failed:
            context.enqueue_application(0)
        assert failed.value.cleanup_owner is context
        assert context.poisoned and kernel.pending
        assert kernel.pending_accepted_launch_count == 1
        assert context.receipt().status == "poisoned"
        context.close()
        assert context.closed and kernel.closed
        assert api.unload_count == 1
    finally:
        _cleanup_all(coarse, live_items)


def test_fence_failure_retains_all_cleanup_authority_for_exact_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    context.enqueue_application(0)
    original_synchronize = runtime.synchronize
    fail_once = True

    def interrupted_synchronize(stream: object) -> None:
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise RuntimeError("injected fence failure")
        original_synchronize(stream)

    monkeypatch.setattr(runtime, "synchronize", interrupted_synchronize)
    free_before = runtime.free_calls
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error) as failed:
            context.close()
        assert failed.value.cleanup_owner is context
        assert not context.closed and not kernel.closed
        assert runtime.free_calls == free_before
        assert api.unload_count == 0
        assert parent._fixed_rank_coarse_child_token is context._token
        context.close()
        assert context.closed and kernel.closed
        assert parent._fixed_rank_coarse_child_token is None
    finally:
        _cleanup_all(coarse, live_items)


def test_uncertain_module_unload_is_terminally_quarantined_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    _, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    api.unload_outcome = RuntimeError("uncertain unload")
    try:
        context.close()
        assert context.closed and not kernel.closed
        assert kernel.unload_disposition == "unload_outcome_uncertain"
        assert api.unload_count == 1
        assert context.receipt().status == "cleanup_quarantined"
        assert parent._fixed_rank_coarse_child_token is None
        context.close()
        assert api.unload_count == 1
    finally:
        _cleanup_all(coarse, live_items)


def test_parent_exclusivity_and_memory_budget_fail_before_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, _ = prepared[9:]
    parent = live.context
    assert parent is not None
    baseline = (
        runtime.malloc_calls,
        runtime.h2d_attempt_count,
        len(runtime.sync_streams),
    )
    unavailable = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        memory_budget_bytes=1,
        rtc_kernel=kernel,
    )
    assert not unavailable.ready
    assert unavailable.context is None and unavailable.receipt is None
    assert unavailable.reason is not None
    assert unavailable.reason.code == "hip_fgmres_coarse_context_memory_budget_exceeded"
    assert parent._fixed_rank_coarse_child_token is None
    assert not kernel.closed
    assert baseline == (
        runtime.malloc_calls,
        runtime.h2d_attempt_count,
        len(runtime.sync_streams),
    )
    kernel.close()
    _cleanup_all(None, live_items)


def test_second_child_rejection_does_not_consume_caller_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, _ = prepared[9:]
    parent = live.context
    assert parent is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    second_kernel, second_api = _coarse_kernel(runtime, plan)
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
            open_hip_fgmres_fixed_rank_coarse_context_v1(
                parent,
                plan,
                rtc_kernel=second_kernel,
            )
        assert not second_kernel.closed
        assert second_api.unload_count == 0
    finally:
        if not second_kernel.closed:
            second_kernel.close()
        _cleanup_all(coarse, live_items)


def test_internal_compile_return_boundary_interruption_unloads_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    original_compiler = (
        context_module.compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1
    )
    baseline = set(runtime.allocations)

    def fake_compile_impl(
        _loaded_runtime: object,
        _architecture: str,
        _hiprtc_library: object,
        *,
        _handoff: object,
    ) -> HipRtcFgmresFixedRankCoarseKernelV1:
        _handoff.publish(kernel)  # type: ignore[attr-defined]
        return kernel

    def interrupt_after_return(*args: object) -> object:
        compiled = original_compiler(*args)
        assert compiled is kernel
        raise KeyboardInterrupt("after compiler return")

    monkeypatch.setattr(rtc_module, "_compile_impl", fake_compile_impl)
    monkeypatch.setattr(
        context_module,
        "compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1",
        interrupt_after_return,
    )
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error) as failed:
            open_hip_fgmres_fixed_rank_coarse_context_v1(parent, plan)
        assert failed.value.code == "hip_fgmres_coarse_context_open_interrupted"
        assert kernel.closed and api.unload_count == 1
        assert set(runtime.allocations) == baseline
        assert parent._fixed_rank_coarse_child_token is None
    finally:
        if not kernel.closed:
            kernel.close()
    _cleanup_all(None, live_items)


def test_second_coarse_child_is_rejected_without_stealing_kernel_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, first_kernel, _ = prepared[9:]
    parent = live.context
    assert parent is not None
    first = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=first_kernel,
    )
    second_kernel, second_api = _coarse_kernel(runtime, plan)
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
            open_hip_fgmres_fixed_rank_coarse_context_v1(
                parent,
                plan,
                rtc_kernel=second_kernel,
            )
        assert not second_kernel.closed and second_api.unload_count == 0
        assert first.context is not None
        assert parent._fixed_rank_coarse_child_token is first.context._token
    finally:
        if not second_kernel.closed:
            second_kernel.close()
        _cleanup_all(first, live_items)


@pytest.mark.parametrize("failure_stage", ("static_h2d", "setup_fence"))
def test_static_initialization_failure_fences_and_reclaims_all_authority(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    baseline = set(runtime.allocations)
    if failure_stage == "static_h2d":
        runtime.h2d_failure_at = runtime.h2d_attempt_count + 2
    else:
        runtime.sync_failure_at = runtime.sync_calls + 1
    with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
        open_hip_fgmres_fixed_rank_coarse_context_v1(
            parent,
            plan,
            rtc_kernel=kernel,
        )
    assert set(runtime.allocations) == baseline
    assert parent._fixed_rank_coarse_child_token is None
    assert kernel.closed and api.unload_count == 1
    _cleanup_all(None, live_items)


@pytest.mark.parametrize("failure_offset", (1, 3, 6))
def test_allocation_failure_reclaims_peer_owner_and_parent_lease(
    monkeypatch: pytest.MonkeyPatch,
    failure_offset: int,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    baseline_pointers = set(runtime.allocations)
    runtime.malloc_failure_at = runtime.malloc_calls + failure_offset
    with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
        open_hip_fgmres_fixed_rank_coarse_context_v1(
            parent,
            plan,
            rtc_kernel=kernel,
        )
    assert set(runtime.allocations) == baseline_pointers
    assert parent._fixed_rank_coarse_child_token is None
    assert kernel.closed and api.unload_count == 1
    _cleanup_all(None, live_items)


def test_parent_reservation_return_boundary_interruption_is_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    _, *_, live = live_items
    plan, kernel, _ = prepared[9:]
    parent = live.context
    assert parent is not None
    original = type(parent)._reserve_fixed_rank_coarse_child

    def interrupted_reservation(
        live_context: Any,
        token: object,
        child_context: object,
    ) -> object:
        result = original(live_context, token, child_context)
        assert result is token
        raise KeyboardInterrupt("after parent reservation")

    monkeypatch.setattr(
        type(parent),
        "_reserve_fixed_rank_coarse_child",
        interrupted_reservation,
    )
    with pytest.raises(HipFgmresFixedRankCoarseContextV1Error) as exc_info:
        open_hip_fgmres_fixed_rank_coarse_context_v1(
            parent,
            plan,
            rtc_kernel=kernel,
        )
    assert exc_info.value.code == "hip_fgmres_coarse_context_open_interrupted"
    assert parent._fixed_rank_coarse_child_token is None
    assert not kernel.closed
    kernel.close()
    _cleanup_all(None, live_items)


def test_allocation_publication_return_boundary_interruption_is_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    baseline = set(runtime.allocations)
    original = HipAllocationOwnerV1.allocate
    interrupted = False

    def interrupted_allocation(
        owner: HipAllocationOwnerV1,
        role: str,
        nbytes: int,
        element_type: str,
        **kwargs: Any,
    ) -> Any:
        nonlocal interrupted
        capability = original(owner, role, nbytes, element_type, **kwargs)
        if (
            owner.owner_role == "fgmres_fixed_rank_coarse_owned_buffers"
            and not interrupted
        ):
            interrupted = True
            raise KeyboardInterrupt("after allocation publication")
        return capability

    monkeypatch.setattr(HipAllocationOwnerV1, "allocate", interrupted_allocation)
    with pytest.raises(HipFgmresFixedRankCoarseContextV1Error) as exc_info:
        open_hip_fgmres_fixed_rank_coarse_context_v1(
            parent,
            plan,
            rtc_kernel=kernel,
        )
    assert exc_info.value.code == "hip_fgmres_coarse_context_open_interrupted"
    assert set(runtime.allocations) == baseline
    assert parent._fixed_rank_coarse_child_token is None
    assert kernel.closed and api.unload_count == 1
    _cleanup_all(None, live_items)


def test_known_not_freed_cleanup_failure_is_retryable_and_parent_stays_reserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, _ = prepared[9:]
    parent = live.context
    assert parent is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    target = context._owned_capabilities["coarse_status"].pointer_snapshot
    original_free = runtime.free
    failed = False

    def fail_once(pointer: int) -> None:
        nonlocal failed
        if pointer == target and not failed:
            failed = True
            raise HipFreeKnownNotFreedError("injected", "known not freed")
        original_free(pointer)

    monkeypatch.setattr(runtime, "free", fail_once)
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error) as exc_info:
            context.close()
        assert exc_info.value.code == "hip_fgmres_coarse_context_cleanup_failed"
        assert not context.closed
        assert parent._fixed_rank_coarse_child_token is context._token
        assert target in runtime.allocations
        context.close()
        assert context.closed
        assert target not in runtime.allocations
        assert parent._fixed_rank_coarse_child_token is None
    finally:
        _cleanup_all(coarse, live_items)


@pytest.mark.parametrize("boundary", ("begin_free", "resolve_free_success"))
def test_lineage_return_boundary_interruption_converges_without_double_free(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, _ = prepared[9:]
    parent = live.context
    assert parent is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None and context._allocation_owner is not None
    target = context._owned_capabilities["coarse_status"].pointer_snapshot
    free_count = 0
    original_free = runtime.free

    def observed_free(pointer: int) -> None:
        nonlocal free_count
        if pointer == target:
            free_count += 1
        original_free(pointer)

    monkeypatch.setattr(runtime, "free", observed_free)
    original_boundary = getattr(HipAllocationOwnerV1, boundary)
    interrupted = False

    def interrupted_boundary(owner_self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal interrupted
        result = original_boundary(owner_self, *args, **kwargs)
        lease = args[0]
        capability = lease if boundary == "begin_free" else lease.capability
        if capability.pointer_snapshot == target and not interrupted:
            interrupted = True
            raise RuntimeError(f"after {boundary} publication")
        return result

    monkeypatch.setattr(HipAllocationOwnerV1, boundary, interrupted_boundary)
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
            context.close()
        assert not context.closed
        assert parent._fixed_rank_coarse_child_token is context._token
        context.close()
        assert context.closed
        assert parent._fixed_rank_coarse_child_token is None
        assert free_count == 1
    finally:
        _cleanup_all(coarse, live_items)


def test_ambiguous_launch_poison_is_receipted_fenced_and_cleanup_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    _, *_, live = live_items
    plan, kernel, api = prepared[9:]
    assert live.context is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        live.context,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    api.launch_outcomes = [0, RuntimeError("ambiguous native launch")]
    try:
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
            context.enqueue_application(0)
        assert context.poisoned and kernel.pending
        poisoned = context.receipt()
        assert poisoned.status == "poisoned"
        assert poisoned.reason is not None
        assert not poisoned.claims.same_stream_application_ready
        assert context.fence() == 1
        assert not kernel.pending
        context.close()
        assert context.closed
    finally:
        _cleanup_all(coarse, live_items)


def test_uncertain_module_unload_is_terminal_quarantine_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    runtime, *_, live = live_items
    plan, kernel, api = prepared[9:]
    parent = live.context
    assert parent is not None
    baseline = set(runtime.allocations)
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        parent,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    api.unload_outcome = RuntimeError("ambiguous unload")
    context.close()
    assert context.closed
    assert api.unload_count == 1
    assert kernel.unload_disposition == "unload_outcome_uncertain"
    assert set(runtime.allocations) == baseline
    assert parent._fixed_rank_coarse_child_token is None
    terminal = context.receipt()
    assert terminal.status == "cleanup_quarantined"
    assert terminal.reason is not None
    context.close()
    assert api.unload_count == 1
    _cleanup_all(coarse, live_items)


def test_native_launch_callback_reentry_fails_without_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    _, *_, live = live_items
    plan, kernel, api = prepared[9:]
    assert live.context is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        live.context,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None
    observed: list[str] = []

    def reenter(_launch_count: int) -> None:
        if observed:
            return
        try:
            context.close()
        except HipFgmresFixedRankCoarseContextV1Error as exc:
            observed.append(exc.code)

    api.launch_callback = reenter
    try:
        application = context.enqueue_application(0)
        assert application.accepted_launch_count == 4
        assert observed == ["hip_fgmres_coarse_context_reentrant_operation"]
        assert context.fence() == 4
    finally:
        _cleanup_all(coarse, live_items)


def test_receipts_are_pointer_free_and_forgery_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare(monkeypatch)
    live_items = prepared[:9]
    _, *_, live = live_items
    plan, kernel, _ = prepared[9:]
    assert live.context is not None
    coarse = open_hip_fgmres_fixed_rank_coarse_context_v1(
        live.context,
        plan,
        rtc_kernel=kernel,
    )
    context = coarse.context
    assert context is not None and coarse.receipt is not None
    try:
        payload = coarse.receipt.to_dict()
        serialized = json.dumps(payload, sort_keys=True)
        for forbidden in (
            "pointer_snapshot",
            "owner_identity",
            "lease_id",
            "stream_pointer",
            "module_pointer",
            "function_pointer",
        ):
            assert forbidden not in serialized
        forged = replace(
            coarse.receipt,
            claims=replace(
                coarse.receipt.claims,
                recurrence_state_machine_integrated=True,  # type: ignore[arg-type]
            ),
        )
        with pytest.raises(HipFgmresFixedRankCoarseContextV1Error):
            validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(forged)
    finally:
        _cleanup_all(coarse, live_items)


def test_context_schema_is_strict_when_packaged() -> None:
    schemas = tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (SCHEMA, APPLICATION_SCHEMA)
    )
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
    assert schemas[0]["$id"].endswith(
        "hip_fgmres_fixed_rank_coarse_context_v1.schema.json"
    )
    assert schemas[1]["$id"].endswith(
        "hip_fgmres_fixed_rank_coarse_application_v1.schema.json"
    )
    assert (
        context_module.HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_V1_SCHEMA_VERSION
        in json.dumps(
            schemas,
            sort_keys=True,
        )
    )
