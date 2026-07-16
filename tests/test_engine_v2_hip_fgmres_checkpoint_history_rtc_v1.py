from __future__ import annotations

import ctypes
from pathlib import Path

import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_checkpoint_history_rtc_v1 import (
    HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1,
    HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1,
    HipRtcFgmresCheckpointHistoryKernelV1,
    HipRtcFgmresCheckpointHistoryV1Error,
    _fixed_source,
)


class _Runtime:
    def __init__(self) -> None:
        self.launch_status = 0
        self.unload_status = 0
        self.launches: list[dict[str, object]] = []
        self.unloads = 0

    def launch(self, function: object, **keywords: object) -> int:
        self.launches.append({"function": function, **keywords})
        return self.launch_status

    def unload(self, _module: object) -> int:
        self.unloads += 1
        return self.unload_status

    def error_string(self, status: int) -> str:
        return f"status={status}"


def _kernel(runtime: _Runtime | None = None) -> HipRtcFgmresCheckpointHistoryKernelV1:
    return HipRtcFgmresCheckpointHistoryKernelV1(
        runtime=runtime or _Runtime(),  # type: ignore[arg-type]
        module=ctypes.c_void_p(1),
        initialize_function=ctypes.c_void_p(2),
        capture_function=ctypes.c_void_p(3),
        identity=None,  # type: ignore[arg-type]
    )


def test_checkpoint_history_source_contains_only_two_fixed_entrypoints() -> None:
    source = _fixed_source()
    assert (
        source.count(HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1.encode())
        == 1
    )
    assert (
        source.count(HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1.encode()) == 1
    )
    assert b"CHECKPOINT_FINALIZE" not in source
    assert b"hipMemcpy" not in source
    assert (
        Path(
            "src/structural_analysis/engine_v2/assembly_backend/kernels/"
            "engine_v2_fgmres_checkpoint_history_v1.hip.cpp"
        ).read_bytes()
        == source
    )


def test_checkpoint_history_kernel_tracks_same_stream_until_fence() -> None:
    runtime = _Runtime()
    kernel = _kernel(runtime)
    kernel.launch_initialize(11, 3, 2, 101, 201)
    kernel.launch_capture(11, 1, 0, 1, 3, 2, 301, 401, 501, 101, 201)
    assert len(runtime.launches) == 2
    assert kernel.accepted_launch_count == 2
    assert kernel.pending
    assert runtime.launches[0]["grid_x"] == 1
    assert runtime.launches[0]["block_x"] == 256
    with pytest.raises(
        HipRtcFgmresCheckpointHistoryV1Error,
        match="pending_work",
    ):
        kernel.close()
    assert kernel.acknowledge_stream_fence(11) == 2
    assert not kernel.pending
    kernel.close()
    assert runtime.unloads == 1
    assert kernel.closed


def test_checkpoint_history_kernel_rejects_alias_before_native_launch() -> None:
    runtime = _Runtime()
    kernel = _kernel(runtime)
    with pytest.raises(
        HipRtcFgmresCheckpointHistoryV1Error,
        match="alias_invalid",
    ) as initialize:
        kernel.launch_initialize(11, 3, 2, 101, 101)
    assert initialize.value.launch_disposition == "not_attempted"
    with pytest.raises(
        HipRtcFgmresCheckpointHistoryV1Error,
        match="alias_invalid",
    ) as capture:
        kernel.launch_capture(11, 1, 0, 1, 3, 2, 301, 301, 501, 101, 201)
    assert capture.value.launch_disposition == "not_attempted"
    assert runtime.launches == []
    kernel.close()


def test_checkpoint_history_kernel_rejected_launch_is_not_pending() -> None:
    runtime = _Runtime()
    runtime.launch_status = 7
    kernel = _kernel(runtime)
    with pytest.raises(
        HipRtcFgmresCheckpointHistoryV1Error,
        match="kernel_launch_failed",
    ) as caught:
        kernel.launch_initialize(11, 3, 2, 101, 201)
    assert caught.value.launch_disposition == "rejected"
    assert not kernel.pending
    kernel.close()


def test_checkpoint_history_kernel_rejects_stream_change_with_pending_work() -> None:
    kernel = _kernel()
    kernel.launch_initialize(11, 3, 2, 101, 201)
    with pytest.raises(
        HipRtcFgmresCheckpointHistoryV1Error,
        match="stream_changed",
    ):
        kernel.launch_capture(12, 1, 0, 1, 3, 2, 301, 401, 501, 101, 201)
    with pytest.raises(
        HipRtcFgmresCheckpointHistoryV1Error,
        match="fence_stream_invalid",
    ):
        kernel.acknowledge_stream_fence(12)
    kernel.acknowledge_stream_fence(11)
    kernel.close()
