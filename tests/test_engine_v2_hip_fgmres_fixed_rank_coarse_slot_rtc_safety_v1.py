from __future__ import annotations

import ctypes
from dataclasses import replace
import dis
from pathlib import Path
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_slot_rtc_v1 as rtc_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_plan_v1 import (  # noqa: E402
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_rtc_v1 import (  # noqa: E402
    HipRtcFgmresFixedRankCoarseSlotKernelV1,
    HipRtcFgmresFixedRankCoarseSlotV1Error,
    _KERNEL_MINT,
    validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1,
)
from structural_analysis.engine_v2.backends.hip.types import (  # noqa: E402
    HipRuntimeLibraryIdentity,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (  # noqa: E402
    HipRtcLibraryIdentity,
)


class _Runtime:
    def __init__(self) -> None:
        self.unload_status: int | BaseException = 0
        self.unloads = 0

    def unload(self, _module: object) -> int:
        self.unloads += 1
        if isinstance(self.unload_status, BaseException):
            raise self.unload_status
        return self.unload_status

    def error_string(self, status: int) -> str:
        return f"status={status}"


class _InterruptAfterStatusStore:
    def __init__(self, target: Any) -> None:
        stores = [
            instruction.offset
            for instruction in dis.get_instructions(target)
            if instruction.opname == "STORE_FAST" and instruction.argval == "status"
        ]
        assert len(stores) == 2
        self._target_code = target.__code__
        self._store_offset = stores[-1]
        self._store_seen = False
        self._previous_trace: Any = None
        self.fired = False

    def _trace(self, frame: Any, event: str, _argument: Any) -> Any:
        if frame.f_code is self._target_code:
            frame.f_trace_opcodes = True
            if event == "opcode":
                if self._store_seen:
                    self.fired = True
                    sys.settrace(self._previous_trace)
                    raise KeyboardInterrupt("after typed-slot unload status store")
                if frame.f_lasti == self._store_offset:
                    self._store_seen = True
        return self._trace

    def __enter__(self) -> _InterruptAfterStatusStore:
        self._previous_trace = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        sys.settrace(self._previous_trace)


def _kernel(
    monkeypatch: pytest.MonkeyPatch,
    runtime: _Runtime,
) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
    monkeypatch.setattr(
        rtc_module,
        "validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1",
        lambda identity: identity,
    )
    functions = {
        symbol: ctypes.c_void_p(index + 2)
        for index, symbol in enumerate(
            HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1
        )
    }
    return HipRtcFgmresFixedRankCoarseSlotKernelV1(
        runtime=runtime,  # type: ignore[arg-type]
        module=ctypes.c_void_p(1),
        functions=functions,
        identity=None,  # type: ignore[arg-type]
        _mint=_KERNEL_MINT,
    )


def test_close_finalization_interruption_never_repeats_native_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    original = rtc_module.HipRtcFgmresFixedRankCoarseSlotKernelV1._finish_close

    def interrupt_after_unload(
        _kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1,
    ) -> None:
        raise KeyboardInterrupt("after native unload")

    monkeypatch.setattr(
        rtc_module.HipRtcFgmresFixedRankCoarseSlotKernelV1,
        "_finish_close",
        interrupt_after_unload,
    )
    with pytest.raises(KeyboardInterrupt, match="after native unload"):
        kernel.close()
    assert runtime.unloads == 1
    assert kernel.unload_disposition == "external_unload_succeeded"
    assert not kernel.closed

    monkeypatch.setattr(
        rtc_module.HipRtcFgmresFixedRankCoarseSlotKernelV1,
        "_finish_close",
        original,
    )
    kernel.close()
    assert runtime.unloads == 1
    assert kernel.closed


def test_close_status_store_interruption_never_repeats_native_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    interrupt = _InterruptAfterStatusStore(type(kernel).close)

    with (
        interrupt,
        pytest.raises(
            KeyboardInterrupt,
            match="after typed-slot unload status store",
        ),
    ):
        kernel.close()

    assert interrupt.fired
    assert runtime.unloads == 1
    assert kernel.unload_disposition == "external_unload_succeeded"
    assert not kernel.closed

    kernel.close()
    assert runtime.unloads == 1
    assert kernel.closed


def test_unpublished_module_cleanup_reports_rejected_and_uncertain_outcomes() -> None:
    runtime = _Runtime()
    runtime.unload_status = 7
    primary = RuntimeError("binding failed")
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as rejected:
        rtc_module._cleanup_unpublished_module(
            runtime,  # type: ignore[arg-type]
            ctypes.c_void_p(1),
            primary,
        )
    assert rejected.value.code == "hip_rtc_fgmres_coarse_slot_compile_cleanup_failed"

    runtime.unload_status = RuntimeError("native unload boundary")
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as uncertain:
        rtc_module._cleanup_unpublished_module(
            runtime,  # type: ignore[arg-type]
            ctypes.c_void_p(1),
            primary,
        )
    assert (
        uncertain.value.code == "hip_rtc_fgmres_coarse_slot_compile_cleanup_uncertain"
    )


def test_identity_rejects_coherently_rehashed_component_drift() -> None:
    components = rtc_module.hip_fgmres_fixed_rank_coarse_slot_source_components_v1()
    identity = rtc_module._build_identity(
        architecture="gfx1030",
        source_hash=components["combined"]["sha256"],
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
        runtime_library=HipRuntimeLibraryIdentity(
            discovery_source="injected",
            requested_name="fake-libamdhip64.so",
            loaded_name="fake-libamdhip64.so",
            resolved_path="/fake/libamdhip64.so",
            sha256="sha256:" + "3" * 64,
        ),
        code_object=b"typed-slot-test-code-object",
    )
    validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(identity)
    drifted = replace(identity, slot_source_sha256="sha256:" + "4" * 64)
    drifted = replace(
        drifted,
        identity_hash=canonical_hash(
            rtc_module._identity_payload(drifted, include_hash=False)
        ),
    )
    with pytest.raises(HipRtcFgmresFixedRankCoarseSlotV1Error) as exc_info:
        validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(drifted)
    assert exc_info.value.code == "hip_rtc_fgmres_coarse_slot_identity_invalid"
