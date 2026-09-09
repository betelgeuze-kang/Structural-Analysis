"""Separate constant compression, retained preload and cyclic native restart."""

from dataclasses import replace
import numpy as np
import pytest
from structural_analysis.ai.fiber_frame_warm_start_features import (
    fiber_frame_warm_start_model_features,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    solve_stateful_fiber_frame2d_constant_load_preload,
    StatefulFiberFrame2DLoadStepRuntimeRecorder,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig as Config,
    StatefulFiberFrame2DDisplacementControlStepAdapter as Adapter,
    solve_stateful_fiber_frame2d_displacement_control_step as control,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes as dump,
    load_stateful_fiber_frame2d_checkpoint_bytes as load,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.materials.retained_fiber_strain import retained_fiber_section
from structural_analysis.materials.rational_force_section import rational_force_section
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


def fixed_problem(retained=False):
    problem = replace(
        make_two_element_stateful_fiber_cantilever(),
        constant_external_loads=((6, -600.0),),
    )
    if not retained:
        return problem
    return replace(
        problem,
        coordinate_precision="twofold-increment",
        terminal_coordinate_precision="twofold",
        terminal_refinement_limit=2,
        members=tuple(
            replace(
                m,
                element=replace(
                    m.element,
                    section=rational_force_section(
                        retained_fiber_section(m.element.section)
                    ),
                    strain_evaluation="exact-rational",
                    coordinate_precision="twofold-increment",
                ),
            )
            for m in problem.members
        ),
    )


@pytest.mark.parametrize("retained", [False, True])
def test_preload_analytic_axial_shortening_and_lateral_reversal(retained):
    problem = fixed_problem(retained)
    recorder = StatefulFiberFrame2DLoadStepRuntimeRecorder()
    preload = solve_stateful_fiber_frame2d_constant_load_preload(
        problem,
        config=NewtonRaphsonConfig(terminal_polishing=True),
        runtime_recorder=recorder,
    )
    assert preload.committed, preload.metrics
    assert recorder.completed_run_count == 1
    assert preload.accepted_checkpoint.load_factor == 0.0
    assert (
        preload.parent_checkpoint.epoch == 0 and preload.accepted_checkpoint.epoch == 1
    )
    # Independent elastic EA from declared section, before damage/yield.
    expected = -600 * 3 / (0.4 * 0.6 * 30000 * 1000 + 8 * 3.87e-4 * 200000 * 1000)
    assert preload.accepted_checkpoint.global_displacements[6] == pytest.approx(
        expected, abs=1e-12
    )
    assert preload.accepted_checkpoint.global_displacements[7] == pytest.approx(
        0, abs=1e-14
    )
    parent = preload.accepted_checkpoint
    for target in (-0.0001, 0.0001, -0.00005):
        before = parent.canonical_bytes()
        step = control(
            problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=target,
            config=Config(newton=NewtonRaphsonConfig(terminal_polishing=True)),
        )
        assert step.committed, step.metrics
        assert parent.canonical_bytes() == before
        assert step.trial_assembly.external_loads_global[6] == -600.0
        assert step.trial_assembly.reactions_global[0] == pytest.approx(600.0, abs=1e-7)
        assert step.trial_assembly.external_loads_global[7] == pytest.approx(
            -10 * step.accepted_checkpoint.load_factor
        )
        assert step.accepted_checkpoint.parent_state_hash == parent.state_hash
        assert step.accepted_checkpoint.global_displacements[7] == pytest.approx(
            target, abs=1e-12
        )
        assert (
            step.metrics["external_loading_profile"] == "constant-plus-proportional.v1"
        )
        assert "constant loads plus" in step.to_dict()["claim_boundary"]
        assert (
            step.accepted_checkpoint.free_coordinate_compensation_m is not None
        ) == retained
        parent = step.accepted_checkpoint


@pytest.mark.parametrize("retained", [False, True])
def test_nonlinear_preloaded_restart_and_failed_step_rollback(retained):
    problem = fixed_problem(retained)
    preload = solve_stateful_fiber_frame2d_constant_load_preload(
        problem, config=NewtonRaphsonConfig(terminal_polishing=True)
    )
    assert preload.committed
    parent = preload.accepted_checkpoint
    original = parent.canonical_bytes()
    failed = control(
        problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=0.02,
        config=Config(
            newton=NewtonRaphsonConfig(max_iterations=1, terminal_polishing=True)
        ),
    )
    assert not failed.committed
    assert failed.accepted_checkpoint is parent
    assert failed.metrics["rollback_exact"] is True
    assert parent.canonical_bytes() == original
    step = control(
        problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=0.01,
        config=Config(newton=NewtonRaphsonConfig(terminal_polishing=True)),
    )
    assert step.committed, step.metrics
    assert any(
        row.response.damaged_integration_point_count > 0
        for row in step.trial_assembly.member_assemblies
    )
    blob = dump(problem, step.accepted_checkpoint)
    reopened = load(blob, problem)
    assert dump(problem, reopened) == blob
    direct = control(
        problem,
        step.accepted_checkpoint,
        control_global_dof=7,
        target_control_displacement_m=-0.005,
        config=Config(newton=NewtonRaphsonConfig(terminal_polishing=True)),
    )
    resumed = control(
        problem,
        reopened,
        control_global_dof=7,
        target_control_displacement_m=-0.005,
        config=Config(newton=NewtonRaphsonConfig(terminal_polishing=True)),
    )
    assert direct.committed and resumed.committed
    assert (
        direct.accepted_checkpoint.canonical_bytes()
        == resumed.accepted_checkpoint.canonical_bytes()
    )
    assert direct.trial_assembly.to_dict() == resumed.trial_assembly.to_dict()
    with pytest.raises(ValueError):
        load(blob, replace(problem, constant_external_loads=((6, -601.0),)))


def test_fixed_loads_change_residual_not_load_factor_derivative_and_include_support_loads():
    problem = replace(fixed_problem(), constant_external_loads=((0, -7.0), (6, -600.0)))
    preload = solve_stateful_fiber_frame2d_constant_load_preload(
        problem, config=NewtonRaphsonConfig(terminal_polishing=True)
    )
    assert preload.committed
    assert preload.trial_assembly.reactions_global[0] == pytest.approx(607.0)
    adapter = Adapter(problem, preload.accepted_checkpoint, 7, -0.0001, Config())
    x = adapter.initial_free_displacements_m()
    _, jacobian = adapter.assemble(x)
    h = 1e-7
    plus, minus = x.copy(), x.copy()
    plus[-1] += h
    minus[-1] -= h
    finite_difference = (adapter.assemble(plus)[0] - adapter.assemble(minus)[0]) / (
        2 * h
    )
    np.testing.assert_allclose(finite_difference, jacobian[:, -1], atol=1e-5, rtol=1e-9)
    assert jacobian[problem.free_global_dofs.index(6), -1] == 0.0


def test_preload_required_and_constant_identity_is_not_hidden_from_features_or_topology():
    problem = fixed_problem()
    root = initial_stateful_fiber_frame2d_checkpoint(problem)
    with pytest.raises(ValueError, match="preload"):
        Adapter(problem, root, 7, -0.0001, Config())
    legacy = replace(problem, constant_external_loads=())
    with pytest.raises(ValueError, match="constant pattern"):
        solve_stateful_fiber_frame2d_constant_load_preload(legacy)
    with pytest.raises(ValueError):
        validate_stateful_fiber_frame2d_checkpoint(legacy, root)
    a = fiber_frame_warm_start_model_features(legacy)
    b = fiber_frame_warm_start_model_features(problem)
    c = fiber_frame_warm_start_model_features(
        replace(problem, constant_external_loads=((6, -700.0),))
    )
    assert a.context_hash != b.context_hash == c.context_hash
    assert b.feature_hash != c.feature_hash
    assert b.values[b.feature_names.index("node_2_constant_fx_kn")] == -600
    with pytest.raises(ValueError):
        compile_stateful_fiber_frame2d_execution_topology(
            problem, model_ir_content_hash="sha256:" + "a" * 64
        )


@pytest.mark.parametrize(
    "loads",
    [
        [(6, -1)],
        ((6, -1), (6, -2)),
        ((99, -1),),
        ((True, -1),),
        ((6, float("nan")),),
        ((6, 0),),
    ],
)
def test_invalid_constant_load_declarations_reject(loads):
    with pytest.raises(ValueError):
        replace(
            make_two_element_stateful_fiber_cantilever(), constant_external_loads=loads
        )


def test_failed_preload_never_supplies_a_lateral_parent():
    problem = replace(fixed_problem(), constant_external_loads=((6, -30000.0),))
    step = solve_stateful_fiber_frame2d_constant_load_preload(
        problem, config=NewtonRaphsonConfig(max_iterations=1)
    )
    assert not step.committed
    assert step.accepted_checkpoint is step.parent_checkpoint
    assert step.accepted_checkpoint.epoch == 0
    assert step.metrics["rollback_exact"] is True
    with pytest.raises(ValueError, match="preload"):
        Adapter(problem, step.accepted_checkpoint, 7, -0.001, Config())


def test_preload_rejects_a_terminal_assembly_that_disagrees_with_newton(monkeypatch):
    from structural_analysis.assembly import stateful_fiber_frame2d_solver as solver

    original = solver._assemble_terminal_trial

    def changed(*args, **kwargs):
        assembled = original(*args, **kwargs)
        return replace(assembled, residual_kn=assembled.residual_kn + 1.0)

    monkeypatch.setattr(solver, "_assemble_terminal_trial", changed)
    result = solve_stateful_fiber_frame2d_constant_load_preload(fixed_problem())
    assert result.trial_solution.status == "ready"
    assert result.committed is False
    assert result.metrics["terminal_assembly_equilibrium_binding_passed"] is False
    assert result.accepted_checkpoint is result.parent_checkpoint
    assert result.metrics["rollback_exact"] is True


def test_rational_load_sum_retains_cancellation_before_rounding():
    from fractions import Fraction
    from structural_analysis.assembly.stateful_fiber_frame2d import (
        assemble_stateful_fiber_frame2d,
    )

    problem = replace(fixed_problem(True), constant_external_loads=((7, 1.0),))
    root = initial_stateful_fiber_frame2d_checkpoint(problem)
    result = assemble_stateful_fiber_frame2d(
        problem,
        root,
        target_load_factor=0.1,
        trial_free_coordinates_m=root.free_coordinates_m,
        trial_free_coordinate_compensation_m=root.free_coordinate_compensation_m,
    )
    expected = float(Fraction(0.1) * Fraction(-10.0) + Fraction(1.0))
    assert expected != 0 and 0.1 * -10 + 1 == 0
    assert result.external_loads_global[7] == expected
    assert result.residual_kn[problem.free_global_dofs.index(7)] == -expected
