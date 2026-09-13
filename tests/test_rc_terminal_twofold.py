"""Terminal correction retains its low component through original native recovery."""

from dataclasses import replace
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest

from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    newton_raphson_vector,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_terminal_coordinate_precision,
    benchmark_rc_control_seed_paths,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint as initial,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    solve_stateful_fiber_frame2d_displacement_control_step as solve,
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes as dump,
    load_stateful_fiber_frame2d_checkpoint_bytes as load,
)
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "rational_fixture", ROOT / "tests/test_rc_control_rational_accumulation.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class SubUlpRoot:
    case_id = "sub-ulp-root"
    terminal_coordinate_precision = "twofold"

    def initial_free_displacements_m(self):
        return np.array([1.0])

    def reference_force_scale(self):
        return 1.0

    def assemble(self, high):
        return self.assemble_with_compensation(high, np.zeros(1))

    def assemble_with_compensation(self, high, low):
        return np.array(
            [float(F(float(high[0])) + F(float(low[0])) - F(1) - F(1, 2**54))]
        ), np.eye(1)


def test_sub_ulp_polish_survives_same_high_coordinate_and_final_reassembly():
    s = newton_raphson_vector(
        SubUlpRoot(), config=NewtonRaphsonConfig(terminal_polishing=True)
    )
    assert s.status == "ready" and s.metrics["contract_pass"]
    assert (
        s.free_displacements_m[0] == 1.0
        and s.free_displacement_compensation_m[0] == 2**-54
    )
    assert s.metrics["residual_kn"] == [0.0]
    assert s.metrics["terminal_polishing"]["accepted"]
    assert s.convergence_history[-1]["free_displacement_compensation_m"] == [2**-54]
    assert not s.free_displacement_compensation_m.flags.writeable
    p = SubUlpRoot()
    p.terminal_coordinate_precision = "binary64"
    old = newton_raphson_vector(p, config=NewtonRaphsonConfig(terminal_polishing=True))
    assert old.free_displacement_compensation_m is None
    assert (
        old.metrics["terminal_polishing"]["reason"]
        == "candidate_equals_converged_state"
    )


def test_rejected_polish_preserves_original_selected_coordinate():
    class Bad(SubUlpRoot):
        def assemble_with_compensation(self, high, low):
            if np.any(low):
                return np.array([1.0]), np.eye(1)
            return super().assemble_with_compensation(high, low)

    s = newton_raphson_vector(
        Bad(), config=NewtonRaphsonConfig(terminal_polishing=True)
    )
    assert s.status == "ready" and s.free_displacement_compensation_m is None
    assert not s.metrics["terminal_polishing"]["accepted"]
    assert (
        s.metrics["terminal_polishing"]["reason"]
        == "strict_residual_improvement_not_met"
    )
    assert s.metrics["residual_kn"] == [-(2**-54)]


def compiled(limit=1):
    return _with_terminal_coordinate_precision(fixture.compiled(), "twofold", limit)


@pytest.mark.parametrize("limit", [1, 2])
def test_native_two_steps_restart_recovery_and_failed_rollback(tmp_path, limit):
    c = compiled(limit)
    p = initial(c.problem)
    cfg = StatefulFiberFrame2DDisplacementControlConfig(
        newton=NewtonRaphsonConfig(terminal_polishing=True)
    )
    accepted_low = False
    for target in [-1e-5, -2e-5, -1e-5]:
        s = solve(
            c.problem,
            p,
            control_global_dof=7,
            target_control_displacement_m=target,
            config=cfg,
        )
        assert s.committed
        accepted_low |= s.trial_solution.free_displacement_compensation_m is not None
        raw = dump(c.problem, s.accepted_checkpoint)
        p = load(raw, c.problem)
        assert dump(c.problem, p) == raw
    assert accepted_low
    with pytest.raises(ValueError):
        load(raw, fixture.compiled().problem)
    f = solve(
        c.problem,
        p,
        control_global_dof=7,
        target_control_displacement_m=-0.01,
        config=replace(cfg, newton=replace(cfg.newton, max_iterations=1)),
    )
    assert not f.committed and f.metrics["rollback_exact"] and dump(c.problem, p) == raw
    (tmp_path / "parent.json").write_bytes(raw)
    # Explicitly test a fresh interpreter, including the selected native contract.
    import os
    import subprocess
    import sys

    code = """import importlib.util,sys,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('tests',Path(sys.argv[1])/'tests/test_rc_terminal_twofold.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.compiled(int(sys.argv[3]));r=Path(sys.argv[2]);p=m.load((r/'parent.json').read_bytes(),c.problem)
cfg=m.StatefulFiberFrame2DDisplacementControlConfig(newton=m.NewtonRaphsonConfig(terminal_polishing=True));s=m.solve(c.problem,p,control_global_dof=7,target_control_displacement_m=-2e-5,config=cfg);assert s.committed;(r/'next.json').write_text(json.dumps(s.to_dict()))
"""
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code, str(ROOT), str(tmp_path), str(limit)],
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    expected = solve(
        c.problem,
        p,
        control_global_dof=7,
        target_control_displacement_m=-2e-5,
        config=cfg,
    )
    assert json.loads((tmp_path / "next.json").read_text()) == expected.to_dict()


@pytest.mark.parametrize("limit", [1, 2])
def test_cyclic_original_full_transition_recovery(tmp_path, limit):
    report = benchmark_rc_control_seed_paths(
        load_neutral_json(fixture.MODEL),
        BoundedRCFiberDirectControlRequest(
            7,
            (-1e-5, -2e-5, -1e-5),
            allow_reversals=True,
            maximum_reversals=1,
            solver_config=StatefulFiberFrame2DDisplacementControlConfig(
                newton=NewtonRaphsonConfig(terminal_polishing=True)
            ),
        ),
        source_revision="0" * 40,
        output_directory=tmp_path / "study",
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
        material_arithmetic="retained-strain",
        fiber_strain_evaluation="retained-coordinate",
        force_accumulation="rational",
        terminal_coordinate_precision="twofold",
        terminal_refinement_limit=limit,
    )
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    for arm in ["reference", "secant", "fresh-reference"]:
        p = json.loads((tmp_path / "study" / arm / "path.json").read_text())
        assert p["status"] == "complete" and p["accepted_target_count"] == 3


@pytest.mark.parametrize("limit", [1, 2])
def test_tampered_compensation_is_rejected_by_commit_and_recovery(monkeypatch, limit):
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )
    from structural_analysis.benchmark.rc_control_seed_runtime import _recover

    c = compiled(limit)
    parent = initial(c.problem)
    cfg = StatefulFiberFrame2DDisplacementControlConfig(
        newton=NewtonRaphsonConfig(terminal_polishing=True)
    )
    step = None
    for target in [-1e-5, -2e-5, -1e-5]:
        step = solve(
            c.problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=target,
            config=cfg,
        )
        assert step.committed
        if step.trial_solution.free_displacement_compensation_m is not None:
            break
        parent = step.accepted_checkpoint
    assert step.trial_solution.free_displacement_compensation_m is not None
    bad = step.trial_solution.free_displacement_compensation_m.copy()
    bad[0] = np.nextafter(bad[0], np.inf)
    solution = replace(step.trial_solution, free_displacement_compensation_m=bad)
    with pytest.raises(ValueError, match="solver-coordinate binding"):
        _recover(
            c,
            replace(step, trial_solution=solution),
            BoundedRCFiberDirectControlRequest(7, (target,), solver_config=cfg),
        )

    def altered(adapter, **kwargs):
        return replace(solution, problem=adapter)

    monkeypatch.setattr(control, "newton_raphson_vector", altered)
    rejected = solve(
        c.problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=target,
        config=cfg,
    )
    assert not rejected.committed and rejected.metrics["rollback_exact"]
    assert not rejected.metrics["solver_assembly_coordinate_residual_binding_passed"]


def test_terminal_profile_requires_native_twofold_rational_problem():
    with pytest.raises(ValueError, match="requires rational assembly"):
        _with_terminal_coordinate_precision(fixture.compiled(False), "twofold")
    with pytest.raises(ValueError, match="unsupported terminal"):
        _with_terminal_coordinate_precision(fixture.compiled(), "extended")


def test_unselected_compensation_declaration_cannot_pass_commit_binding(monkeypatch):
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )

    c = fixture.compiled()
    parent = initial(c.problem)
    cfg = StatefulFiberFrame2DDisplacementControlConfig(
        newton=NewtonRaphsonConfig(terminal_polishing=True)
    )
    step = solve(
        c.problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=-1e-5,
        config=cfg,
    )
    assert (
        step.committed and step.trial_solution.free_displacement_compensation_m is None
    )
    metrics = dict(
        step.trial_solution.metrics,
        free_displacement_compensation_m=[0.0]
        * len(step.trial_solution.free_displacements_m),
    )

    def altered(adapter, **kwargs):
        return replace(step.trial_solution, problem=adapter, metrics=metrics)

    monkeypatch.setattr(control, "newton_raphson_vector", altered)
    result = solve(
        c.problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=-1e-5,
        config=cfg,
    )
    assert not result.committed and result.metrics["rollback_exact"]
    assert not result.metrics["solver_assembly_coordinate_residual_binding_passed"]


class RefiningRoot(SubUlpRoot):
    terminal_refinement_limit = 2

    def assemble_with_compensation(self, high, low):
        residual, _ = super().assemble_with_compensation(high, low)
        return residual, np.array([[2.0]])


def test_two_retained_corrections_keep_low_component_and_charge_each_solve():
    s = newton_raphson_vector(
        RefiningRoot(), config=NewtonRaphsonConfig(terminal_polishing=True)
    )
    p = s.metrics["terminal_polishing"]
    assert s.status == "ready" and p["accepted_correction_count"] == 2
    assert (
        p["attempt_count"] == p["assembly_call_count"] == p["linear_solve_count"] == 2
    )
    assert s.metrics["linear_solve_count"] == s.metrics["newton_iteration_count"] == 3
    assert s.free_displacements_m[0] == 1.0
    assert s.free_displacement_compensation_m[0] == 3 * 2**-56
    assert p["attempts"][1]["original_coordinate_compensation_m"] == [2**-55]
    assert s.metrics["residual_kn"] == [-(2**-56)]
    assert p["stop_reason"] == "refinement_limit_reached"


@pytest.mark.parametrize(
    "failure", ["worse_residual", "increment_gate", "assembly_error"]
)
def test_later_rejection_retains_earlier_accepted_pair_and_counts_attempt(failure):
    class LaterFailure(RefiningRoot):
        def assemble_with_compensation(self, high, low):
            if low[0] > 2**-55:
                if failure == "assembly_error":
                    raise np.linalg.LinAlgError("bounded later failure")
                if failure == "worse_residual":
                    return np.array([1.0]), np.eye(1)
                residual, _ = super().assemble_with_compensation(high, low)
                return residual, np.array([[1e-20]])
            return super().assemble_with_compensation(high, low)

    s = newton_raphson_vector(
        LaterFailure(), config=NewtonRaphsonConfig(terminal_polishing=True)
    )
    p = s.metrics["terminal_polishing"]
    assert s.status == "ready" and p["accepted"] and p["accepted_correction_count"] == 1
    assert p["attempt_count"] == p["assembly_call_count"] == 2
    assert s.free_displacement_compensation_m[0] == 2**-55
    assert s.metrics["residual_kn"] == [-(2**-55)]
    assert s.metrics["newton_iteration_count"] == 2
    assert s.metrics["linear_solve_count"] == (3 if failure == "increment_gate" else 2)
    assert p["assembly_exception_count"] == (1 if failure == "assembly_error" else 0)
    assert not p["attempts"][1]["accepted"]


def test_refinement_obeys_original_iteration_budget():
    s = newton_raphson_vector(
        RefiningRoot(),
        config=NewtonRaphsonConfig(terminal_polishing=True, max_iterations=1),
    )
    p = s.metrics["terminal_polishing"]
    assert p["accepted_correction_count"] == p["attempt_count"] == 1
    assert p["stop_reason"] == "max_iterations_exhausted"
    assert s.free_displacement_compensation_m[0] == 2**-55


@pytest.mark.parametrize("limit", [0, 5, True, 2.0, "2"])
def test_refinement_limit_is_strictly_bounded(limit):
    with pytest.raises(ValueError, match="refinement limit"):
        _with_terminal_coordinate_precision(fixture.compiled(), "twofold", limit)


def test_additional_refinement_requires_explicit_enabled_profile():
    with pytest.raises(ValueError, match="requires twofold"):
        _with_terminal_coordinate_precision(fixture.compiled(), "binary64", 2)
    with pytest.raises(ValueError, match="requires enabled twofold"):
        newton_raphson_vector(RefiningRoot())
    assert compiled(2).problem.contract_hash != compiled().problem.contract_hash
