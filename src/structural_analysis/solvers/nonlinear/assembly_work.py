"""Opt-in observations of actual vector-Newton assembly dispatches."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class VectorAssemblyWorkRecorder:
    """Caller-owned, serial sidecar; not part of any numerical result identity.

    Counts dispatches, including rejected trials and raised calls. One dispatch
    can perform multiple element/material evaluations: these are not counted.
    No timing, solver completion or physical-validity claim is inferred.
    """

    _calls: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _active: bool = field(default=False, init=False, repr=False)
    _reuse_hit_count: int = field(default=0, init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        calls = [dict(row) for row in self._calls]
        return {
            "schema_version": "vector-newton-assembly-dispatch-work.v1",
            "scope": "vector_newton_problem_assembly_dispatches_only",
            "call_count": len(calls),
            "returned_count": sum(row["status"] == "returned" for row in calls),
            "exception_count": sum(row["status"] == "raised" for row in calls),
            "in_flight_count": sum(row["status"] == "started" for row in calls),
            "calls": calls,
            "element_material_evaluations": None,
            "outside_newton_assembly_calls": None,
            "wall_ns": None,
            "solver_completion_inferred": False,
            "physical_validation": False,
            **(
                {"line_search_reuse_hit_count": self._reuse_hit_count}
                if self._reuse_hit_count
                else {}
            ),
        }

    def _assemble(self, problem, coordinates, *, compensation, phase):
        if self._active:
            raise RuntimeError("assembly work recorder is already active")
        row = {
            "ordinal": len(self._calls) + 1,
            "phase": phase,
            "compensated": compensation is not None,
            "status": "started",
        }
        self._calls.append(row)
        self._active = True
        try:
            result = _dispatch(problem, coordinates, compensation)
            row["status"] = "returned"
            return result
        except BaseException as exc:
            row.update(status="raised", exception_kind=type(exc).__name__)
            raise
        finally:
            self._active = False


def _dispatch(problem, coordinates, compensation):
    if compensation is None:
        return problem.assemble(coordinates)
    return problem.assemble_with_compensation(coordinates, compensation)


class VectorLineSearchAssemblyReuse:
    """One-solve cache for a caller-certified deterministic, immutable problem.

    The RC control adapter creates a fresh instance per solve. Generic problems
    are not opted in automatically. Mandatory observations always dispatch.
    """

    def __init__(self, problem):
        self.problem = problem
        self.pending = None

    def clear(self):
        self.pending = None

    def assemble(self, problem, coordinates, *, compensation, phase, recorder):
        pending, self.pending = self.pending, None
        if problem is not self.problem:
            raise ValueError("assembly reuse belongs to a different problem")
        key = None
        if compensation is None:
            values = np.asarray(coordinates)
            key = (values.dtype.str, values.shape, values.tobytes())
        if (
            phase == "primary_iteration"
            and key is not None
            and pending is not None
            and pending[0] == key
        ):
            if recorder is not None:
                if recorder._active:
                    raise RuntimeError("assembly work recorder is already active")
                recorder._reuse_hit_count += 1
            return pending[1]
        result = assemble_vector(
            problem,
            coordinates,
            compensation=compensation,
            phase=phase,
            recorder=recorder,
        )
        if phase == "line_search" and key is not None:
            self.pending = (key, tuple(value.copy() for value in result))
        return result


def assemble_vector(
    problem, coordinates, *, compensation=None, phase, recorder=None, reuse=None
):
    """Dispatch exactly once with the original coordinate objects and return values."""
    if reuse is not None:
        return reuse.assemble(
            problem,
            coordinates,
            compensation=compensation,
            phase=phase,
            recorder=recorder,
        )
    if recorder is None:
        return _dispatch(problem, coordinates, compensation)
    return recorder._assemble(
        problem, coordinates, compensation=compensation, phase=phase
    )
