from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    VectorNewtonRuntimeRecorder,
    newton_raphson_vector,
)


class _StepClock:
    def __init__(self, step_ns: int = 10) -> None:
        self._next_ns = 0
        self._step_ns = step_ns

    def __call__(self) -> int:
        value = self._next_ns
        self._next_ns += self._step_ns
        return value


@dataclass(frozen=True)
class _LinearVectorProblem:
    case_id: str = "vector-newton-runtime-linear"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([0.0], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        return (
            np.asarray([free_displacements_m[0] - 1.0], dtype=float),
            np.asarray([[1.0]], dtype=float),
        )


@dataclass(frozen=True)
class _FlatResidualVectorProblem:
    case_id: str = "vector-newton-runtime-flat-residual"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([0.0], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert free_displacements_m.shape == (1,)
        return np.asarray([1.0], dtype=float), np.asarray([[1.0]], dtype=float)


class _ZeroEquationProblem:
    case_id = "vector-newton-runtime-zero-equation"

    def __init__(self, *, raise_during_assembly: bool = False) -> None:
        self.raise_during_assembly = raise_during_assembly

    def reference_force_scale(self) -> float:
        raise AssertionError("zero-equation solve must not request a force scale")

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert free_displacements_m.shape == (0,)
        if self.raise_during_assembly:
            raise IndexError("synthetic zero-equation assembly failure")
        return np.asarray([], dtype=float), np.empty((0, 0), dtype=float)


class _RaisingAssemblyProblem:
    case_id = "vector-newton-runtime-raising-assembly"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([0.0], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert free_displacements_m.shape == (1,)
        raise RuntimeError("synthetic propagated assembly failure")


@dataclass(frozen=True)
class _SingularVectorProblem:
    case_id: str = "vector-newton-runtime-singular"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.asarray([0.0], dtype=float)

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert free_displacements_m.shape == (1,)
        return np.asarray([1.0], dtype=float), np.asarray([[0.0]], dtype=float)


def test_ready_runtime_recording_does_not_change_solver_output() -> None:
    problem = _LinearVectorProblem()
    config = NewtonRaphsonConfig(max_iterations=4)
    baseline = newton_raphson_vector(problem, config=config)
    recorder = VectorNewtonRuntimeRecorder(clock_ns=_StepClock())

    recorded = newton_raphson_vector(
        problem,
        config=config,
        runtime_recorder=recorder,
    )

    assert recorded.status == baseline.status == "ready"
    assert recorded.problem is baseline.problem
    assert recorded.config == baseline.config
    np.testing.assert_array_equal(
        recorded.free_displacements_m,
        baseline.free_displacements_m,
    )
    assert recorded.metrics == baseline.metrics
    assert recorded.convergence_history == baseline.convergence_history
    assert recorded.line_search_history == baseline.line_search_history
    assert recorded.unsupported_features == baseline.unsupported_features
    assert recorded.warnings == baseline.warnings
    assert not any("wall_ns" in key for key in recorded.metrics)
    assert recorder.to_dict() == {
        "total_wall_ns": 130,
        "assemble_wall_ns": 40,
        "linear_solve_wall_ns": 20,
        "unattributed_wall_ns": 70,
        "run_count": 1,
        "completed_run_count": 1,
        "exception_run_count": 0,
        "assemble_call_count": 4,
        "assemble_exception_count": 0,
        "linear_solve_call_count": 2,
        "linear_solve_exception_count": 0,
        "active": False,
    }


def test_blocked_line_search_records_every_assembly_attempt() -> None:
    recorder = VectorNewtonRuntimeRecorder(clock_ns=_StepClock())

    solution = newton_raphson_vector(
        _FlatResidualVectorProblem(),
        config=NewtonRaphsonConfig(max_iterations=4),
        runtime_recorder=recorder,
    )

    assert solution.status == "blocked"
    assert solution.metrics["detail"] == "line_search_failed_to_reduce_residual"
    assert recorder.assemble_call_count == 8
    assert recorder.assemble_wall_ns == 80
    assert recorder.linear_solve_call_count == 1
    assert recorder.linear_solve_wall_ns == 10
    assert recorder.total_wall_ns == 190
    assert recorder.unattributed_wall_ns == 100
    assert recorder.completed_run_count == 1
    assert recorder.exception_run_count == 0


@pytest.mark.parametrize(
    ("raise_during_assembly", "expected_status", "expected_assembly_errors"),
    ((False, "ready", 0), (True, "blocked", 1)),
)
def test_zero_equation_return_records_its_only_assembly(
    raise_during_assembly: bool,
    expected_status: str,
    expected_assembly_errors: int,
) -> None:
    recorder = VectorNewtonRuntimeRecorder(clock_ns=_StepClock())

    solution = newton_raphson_vector(
        _ZeroEquationProblem(raise_during_assembly=raise_during_assembly),
        runtime_recorder=recorder,
    )

    assert solution.status == expected_status
    assert recorder.total_wall_ns == 30
    assert recorder.assemble_call_count == 1
    assert recorder.assemble_wall_ns == 10
    assert recorder.assemble_exception_count == expected_assembly_errors
    assert recorder.linear_solve_call_count == 0
    assert recorder.linear_solve_wall_ns == 0
    assert recorder.completed_run_count == 1
    assert recorder.exception_run_count == 0


def test_propagated_assembly_exception_still_finishes_runtime_accounting() -> None:
    recorder = VectorNewtonRuntimeRecorder(clock_ns=_StepClock())

    with pytest.raises(RuntimeError, match="synthetic propagated assembly failure"):
        newton_raphson_vector(
            _RaisingAssemblyProblem(),
            runtime_recorder=recorder,
        )

    assert recorder.total_wall_ns == 30
    assert recorder.assemble_call_count == 1
    assert recorder.assemble_wall_ns == 10
    assert recorder.assemble_exception_count == 1
    assert recorder.linear_solve_call_count == 0
    assert recorder.completed_run_count == 0
    assert recorder.exception_run_count == 1
    assert recorder.active is False


def test_handled_linear_solve_failure_counts_the_failed_solve_span() -> None:
    recorder = VectorNewtonRuntimeRecorder(clock_ns=_StepClock())

    solution = newton_raphson_vector(
        _SingularVectorProblem(),
        runtime_recorder=recorder,
    )

    assert solution.status == "blocked"
    assert solution.metrics["detail"] == "singular_tangent_stiffness"
    assert recorder.total_wall_ns == 70
    assert recorder.assemble_call_count == 2
    assert recorder.assemble_exception_count == 0
    assert recorder.linear_solve_call_count == 1
    assert recorder.linear_solve_exception_count == 1
    assert recorder.completed_run_count == 1
    assert recorder.exception_run_count == 0
