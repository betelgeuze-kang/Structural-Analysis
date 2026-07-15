from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MethodType
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_iteration_host_transfer_audit_v1 as audit_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (
    open_hip_fgmres_canonical_predecessor_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_iteration_host_transfer_audit_v1 import (
    HipFgmresIterationHostTransferAuditV1Error,
    open_hip_fgmres_iteration_host_transfer_audit_v1,
    validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1,
    validate_hip_fgmres_iteration_host_transfer_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (
    open_hip_fgmres_live_checkpoint_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.backends.hip import context as hip_context_module
from structural_analysis.engine_v2.backends.hip.context import _BoundHipContextRuntime
from structural_analysis.engine_v2.backends.hip.transfer_audit_v1 import (
    _BOUND_COPY_AUDIT_SNAPSHOT_MINT_V1,
    _BoundHipCopyAuditStateV1,
    _capture_bound_copy_audit_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.solvers.cpu_fgmres import compile_fgmres_policy_v1

from tests.test_engine_v2_hip_fgmres_context_v2 import BoundFakeLoadedRuntime
from tests.test_engine_v2_hip_fgmres_live_checkpoint_context_v1 import (
    _cleanup,
    _prepare_live_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_iteration_host_transfer_audit_v1.schema.json"
)


class _AuditedBlockingCopy:
    __slots__ = ("_copy", "_copy_audit_v1", "_loaded", "_memcpy")

    def __init__(self, runtime: Any, state: _BoundHipCopyAuditStateV1) -> None:
        self._copy = runtime._blocking_d2h_copy
        self._copy_audit_v1 = state
        self._loaded = runtime
        self._memcpy = runtime.allocations

    def __call__(self, array: np.ndarray, pointer: int) -> None:
        ticket = self._copy_audit_v1.begin("d2h_blocking", int(array.nbytes))
        try:
            self._copy(array, pointer)
        except BaseException:
            self._copy_audit_v1.finish(ticket, succeeded=False)
            raise
        self._copy_audit_v1.finish(ticket, succeeded=True)


def _instrument_test_double_runtime(runtime: Any) -> _BoundHipCopyAuditStateV1:
    state = _BoundHipCopyAuditStateV1()
    original_h2d = runtime.copy_h2d_async
    original_d2h = runtime.copy_d2h_async

    def copy_h2d_async(
        _runtime: Any,
        pointer: int,
        array: np.ndarray,
        stream: object,
    ) -> None:
        ticket = state.begin("h2d_async", int(array.nbytes))
        try:
            original_h2d(pointer, array, stream)
        except BaseException:
            state.finish(ticket, succeeded=False)
            raise
        state.finish(ticket, succeeded=True)

    def copy_d2h_async(
        _runtime: Any,
        array: np.ndarray,
        pointer: int,
        stream: object,
    ) -> None:
        ticket = state.begin("d2h_async", int(array.nbytes))
        try:
            original_d2h(array, pointer, stream)
        except BaseException:
            state.finish(ticket, succeeded=False)
            raise
        state.finish(ticket, succeeded=True)

    def snapshot(_runtime: Any, mint: object) -> tuple[Any, Any]:
        if mint is not _BOUND_COPY_AUDIT_SNAPSHOT_MINT_V1:
            raise PermissionError("invalid test audit mint")
        return state, state.snapshot()

    runtime.copy_h2d_async = MethodType(copy_h2d_async, runtime)
    runtime.copy_d2h_async = MethodType(copy_d2h_async, runtime)
    runtime._blocking_d2h_copy = _AuditedBlockingCopy(runtime, state)
    runtime._bound_copy_audit_snapshot_v1 = MethodType(snapshot, runtime)
    return state


def _open_audited_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], Any]:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        primitive_open,
        _,
        kernel,
        loaded,
    ) = _prepare_live_inputs(monkeypatch)
    primitive = primitive_open.context
    assert primitive is not None
    policy = compile_fgmres_policy_v1(restart_dimension=1, max_iterations=2)
    source_plan = compile_hip_fgmres_plan_v1(
        primitive._parent._plan,
        primitive._parent._overlay,
        policy,
    )
    recurrence = compile_hip_fgmres_recurrence_plan_v2(source_plan)
    live = open_hip_fgmres_live_checkpoint_context_v1(
        primitive,
        source_apply,
        recurrence,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    canonical = sealed = global_open = audit = None
    try:
        assert live.context is not None
        canonical = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
        state = _instrument_test_double_runtime(runtime)
        audit = open_hip_fgmres_iteration_host_transfer_audit_v1(canonical.context)
        canonical_pending = canonical.context.enqueue_canonical_predecessor()
        canonical_capability = canonical.context.synchronize_canonical_predecessor(
            canonical_pending
        )
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            canonical.context,
            canonical_capability,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        stack = {
            "runtime": runtime,
            "parent_open": parent_open,
            "resident_open": resident_open,
            "free_open": free_open,
            "primitive_open": primitive_open,
            "kernel": kernel,
            "loaded": loaded,
            "live": live,
            "canonical": canonical,
            "sealed": sealed,
            "continuation": continuation,
            "global": global_open,
            "audit": audit,
        }
        return stack, state
    except BaseException:
        if audit is not None:
            audit.context.close()
        if global_open is not None and not global_open.context.closed:
            global_open.context.close()
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        if canonical is not None and not canonical.context.closed:
            canonical.context.close()
        _cleanup(live, primitive_open, free_open, resident_open, parent_open)
        raise


def _close_audited_chain(stack: dict[str, Any]) -> None:
    audit = stack["audit"].context
    if audit._state != "closed":
        audit.close()
    global_context = stack["global"].context
    if not global_context.closed:
        global_context.close()
    if not stack["sealed"].context.closed:
        stack["sealed"].context.close()
    if not stack["canonical"].context.closed:
        stack["canonical"].context.close()
    _cleanup(
        stack["live"],
        stack["primitive_open"],
        stack["free_open"],
        stack["resident_open"],
        stack["parent_open"],
    )


def _fence_global(stack: dict[str, Any]) -> Any:
    context = stack["global"].context
    pending = context.enqueue_remaining_global_recurrence()
    return context.synchronize(pending)


def _seed_completion_sources(stack: dict[str, Any]) -> None:
    direct = stack["global"].context._require_binding().direct_capabilities
    by_role = {row.role: row for row in direct}
    for role_index, role in enumerate(("solution_x", "true_residual", "solve_record")):
        source = by_role[role]
        payload = bytes(
            (31 + 41 * role_index + 17 * index) & 0xFF for index in range(source.nbytes)
        )
        stack["runtime"].allocations[int(source.pointer_snapshot)][:] = payload


def _rehash(receipt: Any, **changes: Any) -> Any:
    forged = replace(receipt, **changes)
    return replace(
        forged,
        receipt_hash=canonical_hash(
            audit_module._receipt_payload(forged, include_hash=False)
        ),
    )


def _contains_copy_binding_or_invocation(source: str) -> bool:
    def literal_text(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and type(node.value) is str:
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = literal_text(node.left)
            right = literal_text(node.right)
            if left is not None and right is not None:
                return left + right
        return None

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "bind"
            and node.args
            and literal_text(node.args[0]) in {"hipMemcpy", "hipMemcpyAsync"}
        ):
            return True
        if isinstance(function, ast.Attribute) and function.attr in {
            "_memcpy",
            "_memcpy_async",
        }:
            return True
    return False


def test_bound_runtime_copy_counter_records_success_failure_and_blocking_export() -> (
    None
):
    class CopyLoaded(BoundFakeLoadedRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.fail_async_kind: int | None = None
            self.raise_async_kind: int | None = None
            self.fail_blocking = False
            self.raise_blocking = False

        def bind(self, symbol: str, argtypes: Any, restype: Any) -> Any:
            if symbol == "hipMemcpyAsync":

                def copy_async(*arguments: Any) -> int:
                    kind = int(arguments[3])
                    if self.raise_async_kind == kind:
                        raise RuntimeError("injected async copy exception")
                    return 7 if self.fail_async_kind == kind else 0

                return copy_async
            if symbol == "hipMemcpy":

                def copy_blocking(*_arguments: Any) -> int:
                    if self.raise_blocking:
                        raise RuntimeError("injected blocking copy exception")
                    return 7 if self.fail_blocking else 0

                return copy_blocking
            return super().bind(symbol, argtypes, restype)

    loaded = CopyLoaded()
    runtime = _BoundHipContextRuntime(
        loaded,
        _injected_runtime_mint=hip_context_module._INJECTED_HIP_CONTEXT_RUNTIME_MINT,
    )
    host = np.arange(4, dtype="<f8")
    stream = object()
    runtime.copy_h2d_async(1, host, stream)
    runtime.copy_d2h_async(host.copy(), 1, stream)
    runtime.copy_d2h(host.copy(), 1)

    for kind, operation in (
        (1, lambda: runtime.copy_h2d_async(1, host, stream)),
        (2, lambda: runtime.copy_d2h_async(host.copy(), 1, stream)),
    ):
        loaded.fail_async_kind = kind
        with pytest.raises(Exception):
            operation()
        loaded.fail_async_kind = None
        loaded.raise_async_kind = kind
        with pytest.raises(RuntimeError):
            operation()
        loaded.raise_async_kind = None

    loaded.fail_blocking = True
    with pytest.raises(Exception):
        runtime.copy_d2h(host.copy(), 1)
    loaded.fail_blocking = False
    loaded.raise_blocking = True
    with pytest.raises(RuntimeError):
        runtime.copy_d2h(host.copy(), 1)

    capture = _capture_bound_copy_audit_v1(runtime)
    snapshot = capture.snapshot
    assert snapshot.h2d_async.attempt_count == 3
    assert snapshot.h2d_async.success_count == 1
    assert snapshot.h2d_async.failure_count == 2
    assert snapshot.d2h_async.attempt_count == 3
    assert snapshot.d2h_async.success_count == 1
    assert snapshot.d2h_async.failure_count == 2
    assert snapshot.d2h_blocking.attempt_count == 3
    assert snapshot.d2h_blocking.success_count == 1
    assert snapshot.d2h_blocking.failure_count == 2
    assert snapshot.total_in_flight_count == 0
    assert snapshot.sequence == 18
    assert not capture.native_loader_bound


def test_open_rejects_reentrant_predecessor_enqueue_during_start_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        runtime,
        parent_open,
        resident_open,
        free_open,
        source_apply,
        primitive_open,
        _,
        kernel,
        _loaded,
    ) = _prepare_live_inputs(monkeypatch)
    primitive = primitive_open.context
    assert primitive is not None
    policy = compile_fgmres_policy_v1(restart_dimension=1, max_iterations=2)
    source_plan = compile_hip_fgmres_plan_v1(
        primitive._parent._plan,
        primitive._parent._overlay,
        policy,
    )
    recurrence = compile_hip_fgmres_recurrence_plan_v2(source_plan)
    live = open_hip_fgmres_live_checkpoint_context_v1(
        primitive,
        source_apply,
        recurrence,
        architecture="gfx1030",
        rtc_kernel=kernel,
    )
    canonical = None
    pending: list[Any] = []
    try:
        assert live.context is not None
        canonical = open_hip_fgmres_canonical_predecessor_context_v1(live.context)
        state = _instrument_test_double_runtime(runtime)
        in_flight = state.begin("h2d_async", 8)
        try:
            with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as active:
                open_hip_fgmres_iteration_host_transfer_audit_v1(canonical.context)
            assert active.value.code == (
                "hip_fgmres_iteration_host_transfer_audit_copy_inflight"
            )
        finally:
            state.finish(in_flight, succeeded=False)
        original_capture = audit_module._capture_bound_copy_audit_v1

        def mutate_boundary(bound_runtime: Any) -> Any:
            capture = original_capture(bound_runtime)
            pending.append(canonical.context.enqueue_canonical_predecessor())
            return capture

        monkeypatch.setattr(
            audit_module,
            "_capture_bound_copy_audit_v1",
            mutate_boundary,
        )
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as failed:
            open_hip_fgmres_iteration_host_transfer_audit_v1(canonical.context)
        assert failed.value.code == (
            "hip_fgmres_iteration_host_transfer_audit_start_boundary_changed"
        )
        assert len(pending) == 1
        canonical.context.synchronize_canonical_predecessor(pending[0])
    finally:
        if canonical is not None and not canonical.context.closed:
            canonical.context.close()
        _cleanup(live, primitive_open, free_open, resident_open, parent_open)


def test_audited_recurrence_program_is_copy_zero_and_export_is_exact_three_d2h(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack, state = _open_audited_chain(monkeypatch)
    try:
        completion = _fence_global(stack)
        _seed_completion_sources(stack)
        result = stack["audit"].context.export_completion_buffers(
            stack["global"].context,
            completion,
        )
        assert (
            validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
                result,
                expected_context=stack["audit"].context,
            )
            is result
        )
        receipt = result.receipt
        assert receipt.actual_backend == "test_double"
        assert receipt.window.recurrence_program.sequence_delta == 0
        assert receipt.window.completion_export.sequence_delta == 6
        blocking = receipt.window.completion_export.d2h_blocking
        assert (
            blocking.attempt_count,
            blocking.success_count,
            blocking.failure_count,
        ) == (
            3,
            3,
            0,
        )
        assert blocking.bytes_succeeded == receipt.dimensions.total_export_byte_count
        assert receipt.claims.recurrence_program_bound_runtime_copy_attempt_zero
        assert receipt.claims.post_fence_exact_three_blocking_d2h
        assert not receipt.claims.iteration_host_copy_zero_proven
        pre_window_dma_zero = getattr(
            receipt.claims,
            "pre_window_async_copy_completion_or_device_dma_activity_zero_proven",
        )
        assert not pre_window_dma_zero
        assert not receipt.claims.standalone_receipt_provenance_authenticity
        assert not receipt.claims.process_wide_host_transfer_zero_proven
        assert not receipt.claims.synchronization_zero_proven
        assert not receipt.claims.commercial_ready

        forged_claims = replace(
            receipt.claims,
            iteration_host_copy_zero_proven=True,
        )
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error):
            validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(
                _rehash(receipt, claims=forged_claims)
            )

        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        payload = receipt.to_dict()
        validator.validate(payload)
        for path in ("top", "window", "claims"):
            forged_payload = deepcopy(payload)
            target = forged_payload if path == "top" else forged_payload[path]
            target["unexpected"] = True
            with pytest.raises(ValidationError):
                validator.validate(forged_payload)

        float_dimensions = replace(
            receipt.dimensions,
            full_program_launch_count=float(
                receipt.dimensions.full_program_launch_count
            ),
        )
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as numeric:
            validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(
                _rehash(receipt, dimensions=float_dimensions)
            )
        assert numeric.value.code == (
            "hip_fgmres_iteration_host_transfer_audit_type_invalid"
        )

        class TextAlias(str):
            pass

        aliased_bindings = replace(
            receipt.bindings,
            architecture=TextAlias(receipt.bindings.architecture),
        )
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as string:
            validate_hip_fgmres_iteration_host_transfer_audit_receipt_v1(
                replace(receipt, bindings=aliased_bindings)
            )
        assert string.value.code == (
            "hip_fgmres_iteration_host_transfer_audit_type_invalid"
        )

        forged_backend_bindings = replace(
            receipt.bindings,
            native_loader_bound_runtime=True,
        )
        forged_backend_receipt = _rehash(
            receipt,
            actual_backend="hip",
            bindings=forged_backend_bindings,
        )
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as backend:
            validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
                replace(result, receipt=forged_backend_receipt)
            )
        assert backend.value.code == (
            "hip_fgmres_iteration_host_transfer_audit_export_binding_invalid"
        )

        forged_architecture_receipt = _rehash(
            receipt,
            bindings=replace(receipt.bindings, architecture="gfx1100"),
        )
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error):
            validate_hip_fgmres_iteration_host_transfer_audit_result_v1(
                replace(result, receipt=forged_architecture_receipt)
            )

        sequence = state.snapshot().sequence
        assert (
            stack["audit"].context.export_completion_buffers(
                stack["global"].context,
                completion,
            )
            is result
        )
        assert state.snapshot().sequence == sequence
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as changed:
            stack["audit"].context.export_completion_buffers(object(), object())
        assert changed.value.code == (
            "hip_fgmres_iteration_host_transfer_audit_cached_input_changed"
        )
        audit_context = stack["audit"].context
        audit_context.close()
        audit_context.close()
        with audit_module._RUNTIME_AUDIT_OWNERS_LOCK:
            owner = audit_module._RUNTIME_AUDIT_OWNERS.get(stack["runtime"])
            assert owner is None or owner() is not audit_context
    finally:
        _close_audited_chain(stack)


def test_copy_attempt_inside_recurrence_window_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack, state = _open_audited_chain(monkeypatch)
    try:
        ticket = state.begin("d2h_async", 8)
        state.finish(ticket, succeeded=False)
        completion = _fence_global(stack)
        with pytest.raises(HipFgmresIterationHostTransferAuditV1Error) as failed:
            stack["audit"].context.export_completion_buffers(
                stack["global"].context,
                completion,
            )
        assert failed.value.code == (
            "hip_fgmres_iteration_host_transfer_audit_copy_observed"
        )
        assert stack["audit"].context.result is None
    finally:
        _close_audited_chain(stack)


def test_schema_is_strict_and_package_copy_bindings_have_one_allowlisted_owner() -> (
    None
):
    import structural_analysis.engine_v2 as engine_v2_public
    import structural_analysis.engine_v2.assembly_backend as assembly_public

    assert (
        engine_v2_public.open_hip_fgmres_iteration_host_transfer_audit_v1
        is open_hip_fgmres_iteration_host_transfer_audit_v1
    )
    assert (
        assembly_public.validate_hip_fgmres_iteration_host_transfer_audit_result_v1
        is validate_hip_fgmres_iteration_host_transfer_audit_result_v1
    )
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

    engine_root = ROOT / "src/structural_analysis/engine_v2"
    owners: list[str] = []
    for path in engine_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if _contains_copy_binding_or_invocation(text):
            owners.append(str(path.relative_to(ROOT)))
    assert owners == [
        "src/structural_analysis/engine_v2/backends/hip/context.py",
    ]
    assert _contains_copy_binding_or_invocation("runtime.bind('hipMemcpy', [], int)")
    assert _contains_copy_binding_or_invocation(
        'runtime.bind("hip" + "MemcpyAsync", [], int)'
    )
    assert _contains_copy_binding_or_invocation("runtime._memcpy(dst, src, n, 2)")
