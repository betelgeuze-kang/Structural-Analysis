"""Count actual dispatches without changing retained numerical outcomes."""

from collections import Counter
from fractions import Fraction

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    VectorAssemblyWorkRecorder,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    newton_raphson_vector,
)


class Cubic:
    case_id = "assembly-work-cubic"

    def __init__(self, *, sparse=False):
        self.calls = []
        self.sparse = sparse

    def initial_free_displacements_m(self):
        return np.array([0.1])

    def reference_force_scale(self):
        return 1.0

    def assemble(self, x):
        self.calls.append(x.copy())
        tangent = np.array([[3 * x[0] ** 2]])
        return np.array([x[0] ** 3 - 1]), (
            csr_matrix(tangent) if self.sparse else tangent
        )


def same(left, right):
    assert left.status == right.status
    assert left.metrics == right.metrics
    assert left.convergence_history == right.convergence_history
    assert left.line_search_history == right.line_search_history
    assert left.unsupported_features == right.unsupported_features
    assert left.free_displacements_m.tobytes() == right.free_displacements_m.tobytes()
    if left.free_displacement_compensation_m is None:
        assert right.free_displacement_compensation_m is None
    else:
        assert (
            left.free_displacement_compensation_m.tobytes()
            == right.free_displacement_compensation_m.tobytes()
        )


@pytest.mark.parametrize(
    "backend", [VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND]
)
@pytest.mark.parametrize("polishing", [False, True])
def test_real_backtracking_and_final_dispatches_preserve_exact_solution(
    backend, polishing
):
    a, b = (
        Cubic(sparse=backend == VECTOR_SPARSE_MATRIX_BACKEND),
        Cubic(sparse=backend == VECTOR_SPARSE_MATRIX_BACKEND),
    )
    config = NewtonRaphsonConfig(matrix_backend=backend, terminal_polishing=polishing)
    recorder = VectorAssemblyWorkRecorder()
    same(
        newton_raphson_vector(a, config=config),
        newton_raphson_vector(b, config=config, assembly_work=recorder),
    )
    assert [x.tobytes() for x in a.calls] == [x.tobytes() for x in b.calls]
    report = recorder.to_dict()
    phases = Counter(r["phase"] for r in report["calls"])
    assert phases["line_search"] > phases["primary_iteration"]
    assert phases["final_observation"] == 1
    assert report["call_count"] == report["returned_count"] == len(b.calls)
    assert report["exception_count"] == report["in_flight_count"] == 0
    assert report["outside_newton_assembly_calls"] is None
    report["calls"][0]["status"] = "forged"
    assert recorder.to_dict()["calls"][0]["status"] == "returned"


class Compensated(Cubic):
    terminal_coordinate_precision = "twofold"
    terminal_refinement_limit = 2

    def __init__(self, mode="accepted"):
        super().__init__()
        self.mode = mode

    def initial_free_displacements_m(self):
        return np.array([1.0])

    def assemble(self, high):
        return self.assemble_with_compensation(high, np.zeros(1))

    def assemble_with_compensation(self, high, low):
        self.calls.append((high.copy(), low.copy()))
        if np.any(low):
            if self.mode == "raised":
                raise np.linalg.LinAlgError("retained trial failed")
            if self.mode == "rejected":
                return np.array([1.0]), np.eye(1)
        return np.array(
            [
                float(
                    Fraction(float(high[0]))
                    + Fraction(float(low[0]))
                    - 1
                    - Fraction(1, 2**54)
                )
            ]
        ), np.eye(1)


@pytest.mark.parametrize("mode", ["accepted", "rejected", "raised"])
def test_compensated_terminal_rejection_and_exception_still_spend_assembly(mode):
    a, b = Compensated(mode), Compensated(mode)
    recorder = VectorAssemblyWorkRecorder()
    config = NewtonRaphsonConfig(terminal_polishing=True)
    baseline = newton_raphson_vector(a, config=config)
    measured = newton_raphson_vector(b, config=config, assembly_work=recorder)
    same(baseline, measured)
    report = recorder.to_dict()
    assert report["call_count"] == len(b.calls) == len(a.calls) == 3
    assert [r["phase"] for r in report["calls"]] == [
        "primary_iteration",
        "terminal_refinement",
        "final_observation",
    ]
    assert report["calls"][1]["compensated"] is True
    assert report["calls"][-1]["compensated"] is (mode == "accepted")
    assert report["exception_count"] == int(mode == "raised")
    assert report["in_flight_count"] == 0


@pytest.mark.parametrize(
    "kind", ["singular", "line_search", "max_iterations", "unsupported_backend"]
)
def test_blocked_paths_count_terminal_observation_without_convergence_credit(
    kind, monkeypatch
):
    import structural_analysis.solvers.nonlinear.newton as solver

    dispatched = []
    original = solver._solve_vector_increment

    def counted(*args, **kwargs):
        dispatched.append(kwargs["matrix_backend"])
        return original(*args, **kwargs)

    monkeypatch.setattr(solver, "_solve_vector_increment", counted)

    class Problem(Cubic):
        def assemble(self, x):
            if kind in ("singular", "line_search"):
                self.calls.append(x.copy())
                return np.array([1.0]), np.array([[0.0 if kind == "singular" else 1.0]])
            return super().assemble(x)

    cfg = (
        NewtonRaphsonConfig(max_iterations=0)
        if kind == "max_iterations"
        else NewtonRaphsonConfig()
    )
    if kind == "unsupported_backend":
        # The scalar backend is a valid config but unsupported for vector solves.
        cfg = NewtonRaphsonConfig(matrix_backend="numpy_linalg_solve_scalar")
    a, b = Problem(), Problem()
    recorder = VectorAssemblyWorkRecorder()
    before = newton_raphson_vector(a, config=cfg)
    after = newton_raphson_vector(b, config=cfg, assembly_work=recorder)
    same(before, after)
    assert after.status == "blocked"
    report = recorder.to_dict()
    assert report["call_count"] == len(b.calls) == len(a.calls)
    assert report["calls"][-1]["phase"] == "blocked_observation"
    assert not report["solver_completion_inferred"]
    # A failed linear solve is still an attempted solve; history rows may be zero.
    expected_solves = 0 if kind == "unsupported_backend" else 1
    expected_history = 0 if kind in ("singular", "unsupported_backend") else 1
    assert after.metrics["linear_solve_count"] == expected_solves
    assert len(dispatched) == 2 * expected_solves
    assert after.metrics["iteration_count"] == expected_history
    assert after.metrics["newton_iteration_count"] == len(after.convergence_history)
    assert after.metrics["contract_pass"] is False
    assert after.metrics["convergence_claim"] is False


@pytest.mark.parametrize("raised", [False, True])
def test_no_free_equations_observation_is_not_zero_work(raised):
    class Empty(Cubic):
        def initial_free_displacements_m(self):
            return np.array([])

        def assemble(self, x):
            self.calls.append(x.copy())
            if raised:
                raise ValueError("observation failure")
            return np.array([]), np.empty((0, 0))

    recorder = VectorAssemblyWorkRecorder()
    same(
        newton_raphson_vector(Empty()),
        newton_raphson_vector(Empty(), assembly_work=recorder),
    )
    report = recorder.to_dict()
    assert report["call_count"] == 1 and report["exception_count"] == int(raised)
    assert report["calls"][0]["phase"] == "no_free_equations"


def test_escaped_assembly_error_keeps_partial_work_and_original_exception():
    error = RuntimeError("assembly interrupted")

    class Bad(Cubic):
        def assemble(self, x):
            if len(self.calls) == 1:
                raise error
            return super().assemble(x)

    recorder = VectorAssemblyWorkRecorder()
    with pytest.raises(RuntimeError) as info:
        newton_raphson_vector(Bad(), assembly_work=recorder)
    assert info.value is error
    report = recorder.to_dict()
    assert report["call_count"] == 2 and report["exception_count"] == 1
    assert report["calls"][-1]["phase"] == "line_search"
    assert report["in_flight_count"] == 0


@pytest.mark.parametrize("bad", [True, {}, 0])
def test_invalid_recorder_rejects_before_assembly(bad):
    problem = Cubic()
    with pytest.raises(ValueError, match="assembly_work"):
        newton_raphson_vector(problem, assembly_work=bad)
    assert not problem.calls


@pytest.mark.parametrize("retained", [False, True])
def test_actual_rc_path_recording_preserves_step_hashes_and_parent_state(
    monkeypatch, retained
):
    from dataclasses import replace
    from pathlib import Path
    from structural_analysis.api import nonlinear_fiber_frame as public
    from structural_analysis.assembly.stateful_fiber_frame2d import (
        initial_stateful_fiber_frame2d_checkpoint,
    )
    from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
        StatefulFiberFrame2DDisplacementControlConfig,
        StatefulFiberFrame2DDisplacementControlStepAdapter as Adapter,
        solve_stateful_fiber_frame2d_displacement_control_step as solve,
    )
    from structural_analysis.benchmark import rc_control_seed_runtime as runtime
    from structural_analysis.io.neutral.loader import load_neutral_json

    compiled, blockers, _ = public._compile(
        load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        )
    )
    assert not blockers
    if retained:
        compiled = runtime._with_strain_evaluation(compiled, "exact-rational")
        compiled = runtime._with_coordinate_precision(compiled, "twofold-increment")
        compiled = runtime._with_material_arithmetic(compiled, "retained-strain")
        compiled = runtime._with_fiber_strain_evaluation(
            compiled, "retained-coordinate"
        )
        compiled = runtime._with_force_accumulation(compiled, "rational")
        compiled = runtime._with_terminal_coordinate_precision(compiled, "twofold", 2)
    cfg = StatefulFiberFrame2DDisplacementControlConfig()
    cfg = replace(cfg, newton=replace(cfg.newton, terminal_polishing=True))
    parent = initial_stateful_fiber_frame2d_checkpoint(compiled.problem)
    raw_calls = []
    normal, compensated = Adapter.assemble, Adapter.assemble_with_compensation

    def track(self, x):
        raw_calls.append(False)
        return normal(self, x)

    def track_low(self, high, low):
        raw_calls.append(True)
        return compensated(self, high, low)

    monkeypatch.setattr(Adapter, "assemble", track)
    monkeypatch.setattr(Adapter, "assemble_with_compensation", track_low)
    for target in [-1e-6, -2e-6, -1e-6]:
        before = parent.canonical_bytes()
        kwargs = dict(
            control_global_dof=7, target_control_displacement_m=target, config=cfg
        )
        baseline = solve(compiled.problem, parent, **kwargs)
        raw_calls.clear()
        recorder = VectorAssemblyWorkRecorder()
        measured = solve(compiled.problem, parent, **kwargs, assembly_work=recorder)
        assert measured.committed and baseline.committed
        assert measured.to_dict() == baseline.to_dict()
        assert measured.step_hash == baseline.step_hash
        assert parent.canonical_bytes() == before
        report = recorder.to_dict()
        assert report["call_count"] == len(raw_calls)
        assert [r["compensated"] for r in report["calls"]] == raw_calls
        assert report["calls"][-1]["phase"] == "final_observation"
        parent = measured.accepted_checkpoint
