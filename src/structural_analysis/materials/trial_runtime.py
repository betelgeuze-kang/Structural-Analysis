"""Caller-owned constitutive trial timing, separate from numerical identities."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from time import perf_counter_ns
from typing import Any, Literal, TypeVar


MATERIAL_TRIAL_TIMING_SCOPE = "steel_and_concrete_integrate_api_calls_excluding_fiber_accumulation_and_section_assembly"
_Result = TypeVar("_Result")


class MaterialTrialTimingError(RuntimeError):
    """Instrumentation failure that must not become physical nonconvergence."""


@dataclass
class MaterialTrialRuntimeRecorder:
    """Accumulate only explicitly observed steel/concrete integration calls.

    The observed subset remains available when a custom section cannot expose
    its material calls. Coverage and timing errors must be checked before using
    the total as the complete constitutive cost of an assembly attempt.
    """

    clock_ns: Callable[[], int] = field(default=perf_counter_ns, repr=False)
    wall_ns: int = field(default=0, init=False)
    call_count: int = field(default=0, init=False)
    exception_count: int = field(default=0, init=False)
    timing_error_count: int = field(default=0, init=False)
    instrumented_section_call_count: int = field(default=0, init=False)
    unmeasured_section_call_count: int = field(default=0, init=False)
    _active: bool = field(default=False, init=False, repr=False)
    _materials: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            name: {"wall_ns": 0, "call_count": 0, "exception_count": 0}
            for name in ("steel", "concrete")
        },
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not callable(self.clock_ns):
            raise ValueError("clock_ns must be callable")

    @property
    def coverage_complete(self) -> bool:
        return self.unmeasured_section_call_count == 0 and self.timing_error_count == 0

    def mark_instrumented_section_call(self) -> None:
        self.instrumented_section_call_count += 1

    def mark_unmeasured_section_call(self) -> None:
        self.unmeasured_section_call_count += 1

    def _read_clock(self) -> int:
        try:
            value = self.clock_ns()
        except Exception as exc:
            self.timing_error_count += 1
            raise MaterialTrialTimingError("material clock_ns failed") from exc
        if type(value) is not int or value < 0:
            self.timing_error_count += 1
            raise MaterialTrialTimingError(
                "material clock_ns must return nonnegative integer nanoseconds"
            )
        return value

    def observe(
        self,
        material_kind: Literal["steel", "concrete"],
        operation: Callable[..., _Result],
        *args: Any,
        **kwargs: Any,
    ) -> _Result:
        if material_kind not in ("steel", "concrete") or not callable(operation):
            raise ValueError(
                "a supported material kind and callable operation are required"
            )
        if self._active:
            self.timing_error_count += 1
            raise MaterialTrialTimingError(
                "material runtime recorder is already active"
            )
        row = self._materials[material_kind]
        self._active = True
        try:
            failed = False
            started = self._read_clock()
            try:
                return operation(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                try:
                    elapsed = self._read_clock() - started
                    if elapsed < 0:
                        self.timing_error_count += 1
                        raise MaterialTrialTimingError(
                            "material clock_ns must be monotonic"
                        )
                    self.wall_ns += elapsed
                    row["wall_ns"] += elapsed
                finally:
                    self.call_count += 1
                    row["call_count"] += 1
                    if failed:
                        self.exception_count += 1
                        row["exception_count"] += 1
        finally:
            self._active = False

    def to_dict(self) -> dict[str, Any]:
        unavailable = []
        if self.unmeasured_section_call_count:
            unavailable.append("section_material_trial_instrumentation_unavailable")
        if self.timing_error_count:
            unavailable.append("material_trial_clock_invalid")
        return {
            "schema_version": "material-trial-runtime.v1",
            "scope": MATERIAL_TRIAL_TIMING_SCOPE,
            "wall_ns": self.wall_ns,
            "call_count": self.call_count,
            "exception_count": self.exception_count,
            "timing_error_count": self.timing_error_count,
            "instrumented_section_call_count": self.instrumented_section_call_count,
            "unmeasured_section_call_count": self.unmeasured_section_call_count,
            "materials": deepcopy(self._materials),
            "coverage_complete": self.coverage_complete,
            "unavailable_reasons": unavailable,
        }
