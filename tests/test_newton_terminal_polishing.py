"""Tiny algebraic systems cover the opt-in terminal Newton correction contract.

These fixtures distinguish acceptance gates and accounting; they are not RC-frame
analyses or independent physical validation.
"""

from __future__ import annotations

from itertools import count

import numpy as np
import pytest
from scipy.sparse import csr_matrix

import structural_analysis.solvers.nonlinear.newton as newton
from structural_analysis.materials.trial_runtime import MaterialTrialTimingError
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
    ScalarNonlinearAxialReference,
    VectorIncrementRuntimeRecorder,
    newton_raphson_scalar,
    newton_raphson_vector,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    validate_sparse_factorization_diagnostic_manifest,
)


_EPS = 2.0**-42
_POLISH_KEYS = {
    "schema_version",
    "enabled",
    "status",
    "attempted",
    "accepted",
    "reason",
    "source_iteration",
    "candidate_iteration",
    "original_residual_linf",
    "candidate_residual_linf",
    "original_relative_residual",
    "candidate_relative_residual",
    "candidate_increment_abs_m",
    "original_free_displacements_m",
    "candidate_free_displacements_m",
    "original_residual_kn",
    "candidate_residual_kn",
    "proposed_correction_m",
    "candidate_newton_increment_m",
    "assembly_call_count",
    "assembly_exception_count",
    "linear_solve_count",
    "linear_solve_exception_count",
    "sparse_factorization_diagnostic",
    "error_type",
    "error_message",
}


class _TerminalProbe:
    """Two-point algebraic probe whose initial state already meets both gates."""

    case_id = "toy_terminal_polishing"

    def __init__(
        self,
        *,
        candidate_residual=None,
        candidate_jacobian=None,
        candidate_error=None,
        initial=None,
        residual=None,
        sparse=False,
    ):
        self.initial = np.array(
            [1.0, -0.0] if initial is None else initial, dtype=float
        )
        self.residual = np.array(
            [_EPS, _EPS / 2] if residual is None else residual, dtype=float
        )
        self.candidate_residual = np.array(
            [_EPS / 4, _EPS / 8] if candidate_residual is None else candidate_residual,
            dtype=float,
        )
        self.candidate_jacobian = np.array(
            np.eye(2) if candidate_jacobian is None else candidate_jacobian,
            dtype=float,
        )
        self.candidate_error = candidate_error
        self.sparse = sparse
        self.assembly_states = []

    def reference_force_scale(self):
        return 1.0

    def initial_free_displacements_m(self):
        return self.initial.copy()

    def assemble(self, displacement):
        self.assembly_states.append(displacement.copy())
        if displacement.tobytes() == self.initial.tobytes():
            residual, jacobian = self.residual.copy(), np.eye(2)
        else:
            if self.candidate_error is not None:
                raise self.candidate_error
            residual = self.candidate_residual.copy()
            jacobian = self.candidate_jacobian.copy()
        return residual, csr_matrix(jacobian) if self.sparse else jacobian


def _config(enabled=True, **overrides):
    values = {
        "terminal_polishing": enabled,
        "residual_tolerance": 4 * _EPS,
        "increment_tolerance": 2 * _EPS,
        "max_iterations": 4,
    }
    values.update(overrides)
    return NewtonRaphsonConfig(**values)


def _metadata(solution, status, reason):
    metadata = solution.metrics["terminal_polishing"]
    assert set(metadata) == _POLISH_KEYS
    assert metadata["schema_version"] == "newton-vector-terminal-polishing.v1"
    assert metadata["enabled"] is True
    assert metadata["status"] == status
    assert metadata["reason"] == reason
    assert metadata["accepted"] is (status == "accepted")
    return metadata


def _same_terminal_state(solution, baseline):
    assert solution.status == baseline.status == "ready"
    assert (
        solution.free_displacements_m.tobytes()
        == baseline.free_displacements_m.tobytes()
    )
    assert solution.convergence_history == baseline.convergence_history
    assert solution.line_search_history == baseline.line_search_history
    assert solution.metrics["residual_kn"] == baseline.metrics["residual_kn"]
    assert (
        solution.metrics["free_displacements_m"]
        == baseline.metrics["free_displacements_m"]
    )
    assert solution.metrics["contract_pass"] is True
    assert solution.metrics["residual_gate_passed"] is True
    assert solution.metrics["increment_gate_passed"] is True


def _recorder():
    return VectorIncrementRuntimeRecorder(
        clock_ns=lambda ticks=count(0, 11): next(ticks)
    )


@pytest.mark.parametrize(
    "backend", [VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND]
)
def test_default_and_explicit_false_preserve_exact_path_metrics_and_history(backend):
    implicit_problem = _TerminalProbe(sparse=backend == VECTOR_SPARSE_MATRIX_BACKEND)
    explicit_problem = _TerminalProbe(sparse=backend == VECTOR_SPARSE_MATRIX_BACKEND)
    implicit = newton_raphson_vector(
        implicit_problem, config=NewtonRaphsonConfig(matrix_backend=backend)
    )
    explicit = newton_raphson_vector(
        explicit_problem,
        config=NewtonRaphsonConfig(matrix_backend=backend, terminal_polishing=False),
    )
    assert NewtonRaphsonConfig().terminal_polishing is False
    assert implicit.status == explicit.status == "ready"
    assert (
        implicit.free_displacements_m.tobytes()
        == explicit.free_displacements_m.tobytes()
    )
    assert implicit.metrics == explicit.metrics
    assert implicit.convergence_history == explicit.convergence_history
    assert implicit.line_search_history == explicit.line_search_history == []
    assert "terminal_polishing" not in implicit.metrics
    assert implicit.metrics["linear_solve_count"] == 1
    assert (
        len(implicit_problem.assembly_states)
        == len(explicit_problem.assembly_states)
        == 2
    )
    assert all(
        state.tobytes() == implicit_problem.initial.tobytes()
        for state in implicit_problem.assembly_states
    )


@pytest.mark.parametrize(
    "bad", [0, 1, None, "false", [], np.bool_(False), np.bool_(True)]
)
def test_terminal_polishing_requires_exact_boolean(bad):
    with pytest.raises(ValueError, match="terminal_polishing"):
        NewtonRaphsonConfig(terminal_polishing=bad)


def test_scalar_solver_rejects_enabled_polishing_instead_of_ignoring_it():
    with pytest.raises(ValueError, match="terminal_polishing"):
        newton_raphson_scalar(ScalarNonlinearAxialReference(), config=_config())


def test_scalar_default_false_remains_identical_and_has_no_polishing_metadata():
    problem = ScalarNonlinearAxialReference()
    default = newton_raphson_scalar(problem)
    explicit = newton_raphson_scalar(
        problem, config=NewtonRaphsonConfig(terminal_polishing=False)
    )
    assert default == explicit
    assert "terminal_polishing" not in default.metrics


@pytest.mark.parametrize(
    "backend", [VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND]
)
def test_improving_candidate_is_the_final_state_with_recomputed_increment(backend):
    problem = _TerminalProbe(sparse=backend == VECTOR_SPARSE_MATRIX_BACKEND)
    baseline = newton_raphson_vector(
        _TerminalProbe(sparse=problem.sparse),
        config=_config(False, matrix_backend=backend),
    )
    recorder = _recorder()
    solution = newton_raphson_vector(
        problem, config=_config(matrix_backend=backend), increment_runtime=recorder
    )
    metadata = _metadata(
        solution, "accepted", "strict_residual_improvement_and_original_gates_passed"
    )
    expected = problem.initial - problem.residual
    assert solution.problem is problem
    assert solution.status == "ready"
    assert solution.metrics["contract_pass"] is True
    assert solution.free_displacements_m.tobytes() == expected.tobytes()
    assert problem.initial.tobytes() == np.array([1.0, -0.0]).tobytes()
    assert solution.convergence_history[:-1] == baseline.convergence_history
    terminal = solution.convergence_history[-1]
    assert set(terminal) == set(baseline.convergence_history[-1])
    assert terminal["iteration"] == baseline.convergence_history[-1]["iteration"] + 1
    assert terminal["free_displacements_m"] == expected.tolist()
    assert terminal["residual_kn"] == problem.candidate_residual.tolist()
    assert terminal["newton_increment_m"] == (-problem.candidate_residual).tolist()
    assert terminal["increment_abs_m"] == _EPS / 4
    assert terminal["residual_gate_passed"] is terminal["increment_gate_passed"] is True
    assert solution.metrics["final_increment_abs_m"] == terminal["increment_abs_m"]
    assert solution.metrics["residual_kn"] == terminal["residual_kn"]
    assert solution.line_search_history == baseline.line_search_history == []
    assert metadata["attempted"] is True
    assert metadata["source_iteration"] == 0
    assert metadata["candidate_iteration"] == 1
    assert metadata["original_residual_linf"] == _EPS
    assert metadata["candidate_residual_linf"] == _EPS / 4
    assert metadata["proposed_correction_m"] == (-problem.residual).tolist()
    assert (
        metadata["candidate_newton_increment_m"]
        == (-problem.candidate_residual).tolist()
    )
    assert metadata["assembly_call_count"] == metadata["linear_solve_count"] == 1
    assert (
        metadata["assembly_exception_count"]
        == metadata["linear_solve_exception_count"]
        == 0
    )
    assert metadata["error_type"] is metadata["error_message"] is None
    assert solution.metrics["linear_solve_count"] == recorder.call_count == 2
    assert recorder.wall_ns == 22
    assert recorder.exception_count == 0
    assert len(problem.assembly_states) == 3
    assert problem.assembly_states[0].tobytes() == problem.initial.tobytes()
    assert all(
        state.tobytes() == expected.tobytes() for state in problem.assembly_states[1:]
    )
    if problem.sparse:
        assert solution.metrics["sparse_factorization_count"] == 2
        assert solution.metrics["sparse_factorization_diagnostics_passed"] is True


def test_strict_improvement_uses_infinity_norm_not_euclidean_norm():
    residual = np.array([0.75 * _EPS, 0.9 * _EPS])
    problem = _TerminalProbe(candidate_residual=residual)
    assert np.linalg.norm(residual) > np.linalg.norm(problem.residual)
    solution = newton_raphson_vector(problem, config=_config())
    metadata = _metadata(
        solution, "accepted", "strict_residual_improvement_and_original_gates_passed"
    )
    assert metadata["candidate_residual_linf"] == 0.9 * _EPS
    assert solution.metrics["relative_residual"] == 0.9 * _EPS


def test_larger_candidate_increment_is_accepted_when_original_gate_still_passes():
    solution = newton_raphson_vector(
        _TerminalProbe(candidate_jacobian=np.eye(2) / 6), config=_config()
    )
    metadata = _metadata(
        solution, "accepted", "strict_residual_improvement_and_original_gates_passed"
    )
    original_increment = solution.convergence_history[0]["increment_abs_m"]
    assert original_increment < metadata["candidate_increment_abs_m"]
    assert metadata["candidate_increment_abs_m"] <= solution.config.increment_tolerance
    assert metadata["candidate_residual_linf"] < metadata["original_residual_linf"]
    assert solution.status == "ready"
    assert solution.convergence_history[-1]["increment_gate_passed"] is True


@pytest.mark.parametrize("candidate", [[_EPS, 0.0], [1.25 * _EPS, 0.0]])
def test_equal_or_worse_infinity_residual_preserves_original_signed_zero_and_history(
    candidate,
):
    baseline = newton_raphson_vector(_TerminalProbe(), config=_config(False))
    recorder = _recorder()
    problem = _TerminalProbe(candidate_residual=candidate)
    solution = newton_raphson_vector(
        problem, config=_config(), increment_runtime=recorder
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "strict_residual_improvement_not_met")
    assert np.signbit(solution.free_displacements_m[1])
    assert metadata["attempted"] is True
    assert metadata["assembly_call_count"] == 1
    assert metadata["linear_solve_count"] == 0
    assert solution.metrics["linear_solve_count"] == recorder.call_count == 1
    assert metadata["candidate_residual_linf"] >= metadata["original_residual_linf"]
    assert problem.assembly_states[-1].tobytes() == problem.initial.tobytes()


def test_improved_residual_cannot_bypass_candidate_increment_gate():
    baseline = newton_raphson_vector(_TerminalProbe(), config=_config(False))
    problem = _TerminalProbe(candidate_jacobian=np.eye(2) / 64)
    recorder = _recorder()
    solution = newton_raphson_vector(
        problem, config=_config(), increment_runtime=recorder
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "candidate_increment_gate_failed")
    assert metadata["candidate_residual_linf"] < metadata["original_residual_linf"]
    assert metadata["candidate_increment_abs_m"] == 16 * _EPS
    assert metadata["candidate_increment_abs_m"] > solution.config.increment_tolerance
    assert metadata["linear_solve_count"] == 1
    assert solution.metrics["linear_solve_count"] == recorder.call_count == 2


def test_correction_rounded_to_same_state_never_reassembles_candidate():
    problem = _TerminalProbe(initial=[2.0**54, 0.0], residual=[_EPS, 0.0])
    baseline = newton_raphson_vector(
        _TerminalProbe(initial=problem.initial, residual=problem.residual),
        config=_config(False),
    )
    solution = newton_raphson_vector(problem, config=_config())
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "candidate_equals_converged_state")
    assert metadata["attempted"] is True
    assert metadata["assembly_call_count"] == metadata["linear_solve_count"] == 0
    assert len(problem.assembly_states) == 2


@pytest.mark.parametrize("stage", ["assemble", "increment"])
@pytest.mark.parametrize(
    "error_type", [ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError]
)
def test_expected_numerical_candidate_errors_reject_without_losing_valid_terminal(
    monkeypatch, stage, error_type
):
    baseline = newton_raphson_vector(_TerminalProbe(), config=_config(False))
    error = error_type("candidate numerical probe")
    problem = _TerminalProbe(candidate_error=error if stage == "assemble" else None)
    original_solve = newton._solve_vector_increment
    calls = []

    def solve(matrix, residual, *, matrix_backend):
        calls.append(residual.copy())
        if stage == "increment" and len(calls) == 2:
            raise error
        return original_solve(matrix, residual, matrix_backend=matrix_backend)

    monkeypatch.setattr(newton, "_solve_vector_increment", solve)
    recorder = _recorder()
    solution = newton_raphson_vector(
        problem, config=_config(), increment_runtime=recorder
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "numerical_error")
    assert metadata["error_type"] == error_type.__name__
    assert metadata["error_message"] == "candidate numerical probe"
    assert metadata["assembly_call_count"] == 1
    assert metadata["assembly_exception_count"] == int(stage == "assemble")
    assert metadata["linear_solve_count"] == int(stage == "increment")
    assert metadata["linear_solve_exception_count"] == int(stage == "increment")
    assert solution.metrics["linear_solve_count"] == recorder.call_count == len(calls)
    assert recorder.exception_count == int(stage == "increment")
    assert problem.assembly_states[-1].tobytes() == problem.initial.tobytes()


@pytest.mark.parametrize("stage", ["assemble", "increment"])
@pytest.mark.parametrize("error_type", [RuntimeError, TypeError])
def test_unexpected_candidate_errors_propagate(monkeypatch, stage, error_type):
    error = error_type("unexpected candidate defect")
    problem = _TerminalProbe(candidate_error=error if stage == "assemble" else None)
    original = newton._solve_vector_increment
    calls = 0

    def solve(matrix, residual, *, matrix_backend):
        nonlocal calls
        calls += 1
        if stage == "increment" and calls == 2:
            raise error
        return original(matrix, residual, matrix_backend=matrix_backend)

    monkeypatch.setattr(newton, "_solve_vector_increment", solve)
    with pytest.raises(error_type) as raised:
        newton_raphson_vector(problem, config=_config())
    assert raised.value is error


def test_material_runtime_timing_error_propagates_from_original_assembly():
    error = MaterialTrialTimingError("caller timing observation failed")
    problem = _TerminalProbe(candidate_error=error)
    with pytest.raises(MaterialTrialTimingError) as raised:
        newton_raphson_vector(problem, config=_config())
    assert raised.value is error
    assert len(problem.assembly_states) == 2
    assert problem.assembly_states[0].tobytes() == problem.initial.tobytes()
    assert problem.assembly_states[1].tobytes() != problem.initial.tobytes()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["residual", "jacobian"])
def test_nonfinite_candidate_cannot_replace_verified_state(bad, field):
    baseline = newton_raphson_vector(_TerminalProbe(), config=_config(False))
    options = (
        {"candidate_residual": [bad, 0.0]}
        if field == "residual"
        else {"candidate_jacobian": [[bad, 0.0], [0.0, 1.0]]}
    )
    recorder = _recorder()
    solution = newton_raphson_vector(
        _TerminalProbe(**options), config=_config(), increment_runtime=recorder
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "numerical_error")
    assert metadata["assembly_call_count"] == 1
    assert solution.metrics["linear_solve_count"] == recorder.call_count
    assert np.all(np.isfinite(solution.free_displacements_m))


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nonfinite_candidate_backend_increment_is_rejected_and_counted(
    monkeypatch, bad
):
    baseline = newton_raphson_vector(_TerminalProbe(), config=_config(False))
    original = newton._solve_vector_increment
    calls = 0

    def solve(matrix, residual, *, matrix_backend):
        nonlocal calls
        calls += 1
        if calls == 2:
            return np.array([bad, 0.0]), None
        return original(matrix, residual, matrix_backend=matrix_backend)

    monkeypatch.setattr(newton, "_solve_vector_increment", solve)
    recorder = _recorder()
    solution = newton_raphson_vector(
        _TerminalProbe(), config=_config(), increment_runtime=recorder
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "numerical_error")
    assert metadata["linear_solve_count"] == 1
    assert solution.metrics["linear_solve_count"] == recorder.call_count == calls == 2


def test_exhausted_budget_skips_even_when_the_usual_gates_pass():
    problem = _TerminalProbe()
    baseline = newton_raphson_vector(
        _TerminalProbe(), config=_config(False, max_iterations=0)
    )
    recorder = _recorder()
    solution = newton_raphson_vector(
        problem, config=_config(max_iterations=0), increment_runtime=recorder
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "skipped", "max_iterations_exhausted")
    assert metadata["attempted"] is False
    assert metadata["assembly_call_count"] == metadata["linear_solve_count"] == 0
    assert solution.metrics["linear_solve_count"] == recorder.call_count == 1
    assert len(problem.assembly_states) == 2


def test_no_free_equations_adds_no_newton_increment_or_extra_assembly(monkeypatch):
    class Empty:
        case_id = "empty_terminal_polishing_probe"

        def __init__(self):
            self.assembly_count = 0

        def initial_free_displacements_m(self):
            return np.empty(0)

        def reference_force_scale(self):
            pytest.fail("empty systems have no residual gate")

        def assemble(self, displacement):
            self.assembly_count += 1
            assert displacement.shape == (0,)
            return np.empty(0), np.empty((0, 0))

    def forbidden(*_args, **_kwargs):
        pytest.fail("empty equation space must not invoke a linear backend")

    monkeypatch.setattr(newton, "_solve_vector_increment", forbidden)
    problem = Empty()
    recorder = _recorder()
    solution = newton_raphson_vector(
        problem, config=_config(), increment_runtime=recorder
    )
    metadata = _metadata(solution, "skipped", "no_free_equations")
    assert solution.status == "ready"
    assert metadata["attempted"] is False
    assert metadata["assembly_call_count"] == metadata["linear_solve_count"] == 0
    assert solution.metrics["linear_solve_count"] == recorder.call_count == 0
    assert recorder.wall_ns == 0
    assert problem.assembly_count == 1
    assert solution.convergence_history == solution.line_search_history == []
    assert solution.metrics["solver_executed"] is False


def test_failed_usual_convergence_never_reaches_polishing():
    class Flat(_TerminalProbe):
        def assemble(self, displacement):
            self.assembly_states.append(displacement.copy())
            return np.ones(2), np.eye(2)

    baseline = newton_raphson_vector(Flat(), config=_config(False))
    solution = newton_raphson_vector(Flat(), config=_config())
    metadata = _metadata(solution, "not_reached", "usual_convergence_not_reached")
    assert solution.status == baseline.status == "blocked"
    assert solution.metrics["detail"] == "line_search_failed_to_reduce_residual"
    assert metadata["attempted"] is False
    assert metadata["assembly_call_count"] == metadata["linear_solve_count"] == 0
    assert solution.convergence_history == baseline.convergence_history
    assert solution.line_search_history == baseline.line_search_history
    assert (
        solution.free_displacements_m.tobytes()
        == baseline.free_displacements_m.tobytes()
    )


def test_sparse_candidate_failure_stays_nested_and_preserves_valid_selected_diagnostics():
    baseline = newton_raphson_vector(
        _TerminalProbe(sparse=True),
        config=_config(False, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND),
    )
    problem = _TerminalProbe(sparse=True, candidate_jacobian=np.diag([1.0, 1.0e-13]))
    recorder = _recorder()
    solution = newton_raphson_vector(
        problem,
        config=_config(matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND),
        increment_runtime=recorder,
    )
    _same_terminal_state(solution, baseline)
    metadata = _metadata(solution, "rejected", "numerical_error")
    diagnostic = metadata["sparse_factorization_diagnostic"]
    assert validate_sparse_factorization_diagnostic_manifest(diagnostic) == diagnostic
    assert diagnostic["contract_pass"] is False
    assert diagnostic["condition_number_1"] == 1.0e13
    assert metadata["error_type"] == "SparseFactorizationError"
    assert (
        metadata["linear_solve_count"] == metadata["linear_solve_exception_count"] == 1
    )
    assert solution.metrics["linear_solve_count"] == recorder.call_count == 2
    assert recorder.exception_count == 1
    assert solution.metrics["sparse_factorization_count"] == 1
    assert solution.metrics["sparse_factorization_diagnostics_passed"] is True
    assert (
        solution.metrics["sparse_factorization_diagnostics"]
        == baseline.metrics["sparse_factorization_diagnostics"]
    )
    assert (
        solution.metrics["fallback_used"]
        is solution.metrics["regularization_used"]
        is False
    )
