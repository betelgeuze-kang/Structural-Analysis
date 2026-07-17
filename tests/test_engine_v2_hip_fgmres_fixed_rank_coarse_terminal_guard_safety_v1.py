from __future__ import annotations

# ruff: noqa: E402

import dis
from pathlib import Path
import sys
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_terminal_guard_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseTerminalGuardV1Error,
)

from tests.test_engine_v2_hip_fgmres_fixed_rank_coarse_terminal_guard_v1 import (
    GUARD,
    _Runtime,
    _kernel,
    _launch,
)


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
                    raise KeyboardInterrupt("after terminal-guard unload status store")
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


def test_only_the_exact_inactive_status_is_a_no_op() -> None:
    source = Path(GUARD).read_text(encoding="utf-8")

    assert "status == 0u || status == kCoarseGuardInactive" in source
    assert "(status & kCoarseGuardInactive) != 0u" not in source


@pytest.mark.parametrize(
    "outcome",
    (
        RuntimeError("ambiguous native boundary"),
        KeyboardInterrupt("interrupted native boundary"),
    ),
)
def test_uncertain_launch_requires_a_fence_before_relaunch(
    monkeypatch: pytest.MonkeyPatch,
    outcome: BaseException,
) -> None:
    runtime = _Runtime()
    runtime.launch_statuses = [outcome]
    kernel = _kernel(monkeypatch, runtime)

    expected_error = (
        HipRtcFgmresFixedRankCoarseTerminalGuardV1Error
        if isinstance(outcome, Exception)
        else type(outcome)
    )
    with pytest.raises(expected_error):
        _launch(kernel)
    assert kernel.pending
    assert len(runtime.launches) == 1

    with pytest.raises(
        HipRtcFgmresFixedRankCoarseTerminalGuardV1Error,
        match="fence_required",
    ) as blocked:
        _launch(kernel)
    assert blocked.value.launch_disposition == "not_attempted"
    assert len(runtime.launches) == 1

    assert kernel.acknowledge_stream_fence(11) == 0
    _launch(kernel)
    assert kernel.acknowledge_stream_fence(11) == 1
    kernel.close()


def test_known_unload_success_survives_status_store_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    kernel = _kernel(monkeypatch, runtime)
    interrupt = _InterruptAfterStatusStore(type(kernel).close)

    with (
        interrupt,
        pytest.raises(
            KeyboardInterrupt,
            match="after terminal-guard unload status store",
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
