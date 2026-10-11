from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH,
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check,
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
    solve_stateful_corotational_fiber_frame2d_displacement_control,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials import (
    AsymmetricConcreteDamageMaterial,
    BilinearCombinedHardeningSteel,
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_SPARSE_MATRIX_BACKEND,
)


ARCH_COORDINATES = ((-1.0, 0.0), (0.0, 0.1), (1.0, 0.0))
ARCH_TARGETS = tuple(-0.01 * index for index in range(1, 19))


def _elastic_materials() -> tuple[
    BilinearCombinedHardeningSteel,
    AsymmetricConcreteDamageMaterial,
]:
    modulus_mpa = 200_000.0
    return (
        BilinearCombinedHardeningSteel(
            elastic_modulus_mpa=modulus_mpa,
            yield_stress_mpa=1.0e12,
            isotropic_hardening_modulus_mpa=0.0,
            kinematic_hardening_modulus_mpa=0.0,
        ),
        AsymmetricConcreteDamageMaterial(
            elastic_modulus_mpa=modulus_mpa,
            tensile_strength_mpa=1.0e12,
            compressive_strength_mpa=1.0e12,
            tensile_softening_rate=1.0,
            compressive_softening_rate=1.0,
        ),
    )


def _section(section_id: str):
    steel, concrete = _elastic_materials()
    return make_rectangular_stateful_rc_fiber_section(
        width_m=0.02,
        depth_m=0.02,
        cover_m=0.004,
        concrete_layer_count=4,
        top_bar_count=1,
        bottom_bar_count=1,
        bar_area_m2=1.0e-8,
        section_id=section_id,
        steel=steel,
        concrete=concrete,
    )


def _member(
    coordinates: tuple[tuple[float, float], ...],
    member_id: str,
    node_i: int,
    node_j: int,
) -> StatefulCorotationalFiberFrame2DMember:
    return StatefulCorotationalFiberFrame2DMember(
        member_id=member_id,
        node_i=node_i,
        node_j=node_j,
        element=StatefulCorotationalFiberBeam2D(
            node_coordinates_m=(coordinates[node_i], coordinates[node_j]),
            section=_section(f"section-{member_id}"),
            integration_order=3,
            element_id=member_id,
        ),
    )


def _arch_problem(case_id: str) -> StatefulCorotationalFiberFrame2DProblem:
    return StatefulCorotationalFiberFrame2DProblem(
        case_id=case_id,
        node_coordinates_m=ARCH_COORDINATES,
        members=(
            _member(ARCH_COORDINATES, "arch-left", 0, 1),
            _member(ARCH_COORDINATES, "arch-right", 1, 2),
        ),
        fixed_global_dofs=tuple(dof for dof in range(9) if dof != 4),
        reference_external_loads=((4, -1.0),),
        rotation_coordinate_scale_m=1.0,
    )


@pytest.fixture(scope="module")
def direct_arch_path():
    problem = _arch_problem("direct-control-shallow-arch")
    config = StatefulCorotationalFiberFrame2DDisplacementControlConfig(
        maximum_iterations=80,
    )
    result = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        ARCH_TARGETS,
        control_global_dof=4,
        config=config,
    )
    return problem, config, result


def test_direct_control_crosses_limit_point_and_hits_every_target(
    direct_arch_path,
) -> None:
    _problem, config, result = direct_arch_path

    assert result.status == "ready"
    assert result.contract_pass is True
    assert result.final_checkpoint.global_displacements[4] == ARCH_TARGETS[-1]
    assert len(result.steps) == len(ARCH_TARGETS)
    assert all(
        step.committed
        and step.metrics["solver_contract_pass"] is True
        and step.metrics["parent_checkpoint_immutable"] is True
        and step.metrics["section_and_element_parent_binding_passed"] is True
        and step.metrics["solver_assembly_coordinate_residual_binding_passed"] is True
        and step.metrics["control_coordinate_gate_passed"] is True
        and step.trial_solution.metrics["regularization_used"] is False
        and step.trial_solution.metrics["fallback_used"] is False
        and abs(step.trial_solution.metrics["control_error_m"])
        <= config.control_tolerance_m
        for step in result.steps
    )
    assert [
        step.accepted_checkpoint.global_displacements[4] for step in result.steps
    ] == list(ARCH_TARGETS)

    load_factors = [step.accepted_checkpoint.load_factor for step in result.steps]
    peak_index = max(range(len(load_factors)), key=load_factors.__getitem__)
    minimum_index = min(range(len(load_factors)), key=load_factors.__getitem__)
    assert 0 < peak_index < minimum_index < len(load_factors) - 1
    assert load_factors[minimum_index] < 0.0
    assert load_factors[-1] > load_factors[minimum_index]


def test_direct_control_checkpoint_restart_replays_exact_terminal_state(
    direct_arch_path,
) -> None:
    problem, config, baseline = direct_arch_path
    prefix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        ARCH_TARGETS[:9],
        control_global_dof=4,
        config=config,
    )
    persisted = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem,
        prefix.final_checkpoint,
    )
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        persisted,
        problem,
    )
    suffix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        ARCH_TARGETS[9:],
        control_global_dof=4,
        initial_checkpoint=restored,
        config=config,
    )

    assert prefix.contract_pass is True
    assert suffix.contract_pass is True
    assert restored.canonical_bytes() == prefix.final_checkpoint.canonical_bytes()
    assert suffix.final_checkpoint.canonical_bytes() == (
        baseline.final_checkpoint.canonical_bytes()
    )
    assert [step.accepted_checkpoint.load_factor for step in suffix.steps] == [
        step.accepted_checkpoint.load_factor for step in baseline.steps[9:]
    ]


def test_augmented_linearization_includes_proportional_support_coupling() -> None:
    coordinates = ((0.0, 0.0), (1.0, 0.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-control-prescribed-column",
        node_coordinates_m=coordinates,
        members=(_member(coordinates, "bar", 0, 1),),
        fixed_global_dofs=(0, 1, 2, 4, 5),
        reference_external_loads=((3, 2.0),),
        prescribed_displacements=((0, 1.0e-4),),
        rotation_coordinate_scale_m=1.0,
    )
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem=problem,
        accepted_checkpoint=parent,
        control_global_dof=3,
        target_control_displacement_m=1.0e-3,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(),
    )
    check = finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check(
        step_problem,
        displacement_step_m=1.0e-4,
        load_factor_step=1.0e-4,
    )
    center = step_problem.assemble(step_problem.initial_augmented_coordinates_m())
    external_only_column = -problem.reference_external_load_vector()[3]

    assert check["parent_binding_passed"] is True
    assert check["displacement_column_max_abs_error_kn_per_m"] < 1.0e-7
    assert check["load_factor_column_max_abs_error_kn"] < 1.0e-7
    assert center.load_factor_residual_derivative_kn[0] != external_only_column
    assert check["augmented_formula_hash"] == (
        STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH
    )


def test_direct_control_solves_coupled_multi_equation_frame() -> None:
    coordinates = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-control-two-member-frame",
        node_coordinates_m=coordinates,
        members=(
            _member(coordinates, "beam", 0, 1),
            _member(coordinates, "column", 1, 2),
        ),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((6, 0.25), (7, -1.0)),
        rotation_coordinate_scale_m=2.0,
    )
    targets = (-1.0e-4, -2.0e-4, -3.0e-4)
    result = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets,
        control_global_dof=7,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            residual_tolerance=1.0e-9,
        ),
    )

    assert result.contract_pass is True
    assert len(problem.free_global_dofs) == 6
    assert result.final_checkpoint.global_displacements[7] == targets[-1]
    assert all(
        step.trial_solution.metrics["residual_gate_passed"] is True
        and len(step.trial_assembly.residual_kn) == 6
        for step in result.steps
    )


def test_invalid_full_step_trial_is_rejected_and_backtracking_continues(
    monkeypatch,
) -> None:
    coordinates = ((0.0, 0.0), (1.0, 0.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-control-invalid-full-alpha",
        node_coordinates_m=coordinates,
        members=(_member(coordinates, "bar", 0, 1),),
        fixed_global_dofs=(0, 1, 2, 4, 5),
        reference_external_loads=((3, 2.0),),
        rotation_coordinate_scale_m=1.0,
    )
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem=problem,
        accepted_checkpoint=parent,
        control_global_dof=3,
        target_control_displacement_m=1.0e-3,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=30,
        ),
    )
    step_type = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem
    original_assemble = step_type.assemble
    call_count = 0

    def assemble_with_invalid_full_trial(self, coordinates_m):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError("synthetic collapsed trial chord")
        return original_assemble(self, coordinates_m)

    monkeypatch.setattr(step_type, "assemble", assemble_with_invalid_full_trial)
    solution = solve_stateful_corotational_fiber_frame2d_displacement_control(
        step_problem
    )

    assert solution.status == "ready"
    assert solution.metrics["contract_pass"] is True
    first_attempts = solution.line_search_history[0]["attempts"]
    assert first_attempts[0]["alpha"] == 1.0
    assert first_attempts[0]["accepted"] is False
    assert first_attempts[0]["failure"] == "invalid_trial_assembly"
    assert len(first_attempts) >= 2
    assert any(row["accepted"] is True for row in first_attempts[1:])


def test_direct_control_rejects_disconnected_member_graph() -> None:
    coordinates = ((0.0, 0.0), (1.0, 0.0), (3.0, 0.0), (4.0, 0.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="direct-control-disconnected",
        node_coordinates_m=coordinates,
        members=(
            _member(coordinates, "controlled", 0, 1),
            _member(coordinates, "isolated-fixed", 2, 3),
        ),
        fixed_global_dofs=(0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11),
        reference_external_loads=((3, 1.0),),
        rotation_coordinate_scale_m=1.0,
    )

    with pytest.raises(ValueError, match="member graph must be connected"):
        run_stateful_corotational_fiber_frame2d_displacement_control_path(
            problem,
            (1.0e-4,),
            control_global_dof=3,
        )


def test_failed_direct_control_step_rolls_back_exact_parent() -> None:
    problem = _arch_problem("direct-control-rollback")
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    parent_bytes = parent.canonical_bytes()
    result = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_global_dof=4,
        target_control_displacement_m=-0.18,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=0,
        ),
    )

    assert result.status == "blocked"
    assert result.committed is False
    assert result.accepted_checkpoint is parent
    assert result.accepted_checkpoint.canonical_bytes() == parent_bytes
    assert result.metrics["rollback_exact"] is True
    assert result.trial_solution.metrics["contract_pass"] is False
    assert result.trial_solution.metrics["fallback_used"] is False
    assert result.trial_solution.metrics["regularization_used"] is False


def test_direct_control_rejects_ambiguous_or_unsupported_configuration() -> None:
    problem = _arch_problem("direct-control-invalid")
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)

    with pytest.raises(ValueError, match="free global DOF"):
        solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            problem,
            parent,
            control_global_dof=0,
            target_control_displacement_m=-0.01,
        )
    rotational_free = replace(problem, fixed_global_dofs=(0, 1, 2, 3, 4, 6, 7, 8))
    rotational_parent = initial_stateful_corotational_fiber_frame2d_checkpoint(
        rotational_free
    )
    with pytest.raises(ValueError, match="translational"):
        solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            rotational_free,
            rotational_parent,
            control_global_dof=5,
            target_control_displacement_m=-0.01,
        )
    with pytest.raises(ValueError, match="strictly in one direction"):
        run_stateful_corotational_fiber_frame2d_displacement_control_path(
            problem,
            (-0.01, -0.02, -0.015),
            control_global_dof=4,
        )
    with pytest.raises(ValueError, match="dense backend"):
        StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
        )


def test_direct_control_manifest_keeps_non_promoting_claim_boundary(
    direct_arch_path,
) -> None:
    _problem, _config, result = direct_arch_path
    payload = result.to_dict()

    assert payload["contract_pass"] is True
    assert payload["claim_boundary"] == (
        STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY
    )
    assert "does not promote the unified public API" in payload["claim_boundary"]
    assert "external Level 2 validation" in payload["claim_boundary"]
    assert np.isfinite(payload["final_checkpoint"]["load_factor"])


def test_constant_axial_load_reversal_and_serialized_restart():
    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
        solve_stateful_corotational_fiber_frame2d_load_step,
    )

    coordinates = ((0.0, 0.0), (0.0, 1.0))
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="fixed-axial-reversal",
        node_coordinates_m=coordinates,
        members=(_member(coordinates, "column", 0, 1),),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((3, 1.0),),
        fixed_external_loads=((4, -0.01),),
        rotation_coordinate_scale_m=1.0,
    )
    seed = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    preload = solve_stateful_corotational_fiber_frame2d_load_step(
        problem,
        seed,
        target_load_factor=0.0,
    )
    assert preload.committed
    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem=problem,
        accepted_checkpoint=preload.accepted_checkpoint,
        control_global_dof=3,
        target_control_displacement_m=0.001,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(),
    )
    check = finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check(
        step_problem,
        displacement_step_m=1e-6,
        load_factor_step=1e-6,
    )
    assert check["parent_binding_passed"]
    np.testing.assert_allclose(
        check["finite_difference_displacement_column_kn_per_m"],
        check["analytic_displacement_column_kn_per_m"],
        rtol=1e-6,
        atol=1e-5,
    )
    assert check["load_factor_column_max_abs_error_kn"] < 1e-8
    targets = (0.001, -0.001, 0.002)
    kwargs = dict(control_global_dof=3, allow_reversal=True)
    full = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets,
        initial_checkpoint=preload.accepted_checkpoint,
        **kwargs,
    )
    assert full.contract_pass
    prefix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets[:1],
        initial_checkpoint=preload.accepted_checkpoint,
        **kwargs,
    )
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem,
        prefix.final_checkpoint,
    )
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, problem)
    suffix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets[1:],
        initial_checkpoint=restored,
        **kwargs,
    )
    assert suffix.contract_pass
    assert (
        suffix.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )
    failed = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        problem,
        restored,
        control_global_dof=3,
        target_control_displacement_m=-0.002,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=0,
        ),
    )
    assert not failed.committed
    assert failed.accepted_checkpoint.canonical_bytes() == restored.canonical_bytes()
    assert failed.metrics["rollback_exact"] is True

    assert full.steps[0].accepted_checkpoint.load_factor > 0.0
    assert full.steps[1].accepted_checkpoint.load_factor < 0.0
    from structural_analysis.assembly import (
        assemble_stateful_corotational_fiber_frame2d,
    )

    for step in full.steps:
        state = step.accepted_checkpoint
        assembly = assemble_stateful_corotational_fiber_frame2d(
            problem,
            state,
            target_load_factor=state.load_factor,
            trial_free_coordinates_m=np.asarray(state.global_displacements)[
                list(problem.free_global_dofs)
            ],
        )
        assert assembly.external_loads_global[4] == -0.01
        np.testing.assert_allclose(
            (assembly.internal_loads_global - assembly.external_loads_global)[
                list(problem.free_global_dofs)
            ],
            0.0,
            atol=1e-6,
        )
    with pytest.raises(ValueError, match="does not match the supplied frame problem"):
        load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
            raw,
            replace(problem, fixed_external_loads=((4, -0.02),)),
        )


@pytest.mark.parametrize("flag", [1, "true", None])
def test_reversal_opt_in_requires_boolean(flag):
    with pytest.raises(ValueError, match="allow_reversal must be a boolean"):
        run_stateful_corotational_fiber_frame2d_displacement_control_path(
            _arch_problem("invalid-flag"),
            (-0.01, 0.01),
            control_global_dof=4,
            allow_reversal=flag,
        )


def test_reversal_opt_in_still_rejects_duplicate_target():
    with pytest.raises(ValueError, match="distinct consecutive targets"):
        run_stateful_corotational_fiber_frame2d_displacement_control_path(
            _arch_problem("duplicate-target"),
            (-0.01, -0.01),
            control_global_dof=4,
            allow_reversal=True,
        )


def test_nonlinear_fixed_axial_reversal_restart_and_coarse_failure():
    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
        solve_stateful_corotational_fiber_frame2d_load_step,
    )

    coords = ((0.0, 0.0), (0.0, 1.0))
    steel = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200000,
        yield_stress_mpa=400,
        isotropic_hardening_modulus_mpa=1000,
        kinematic_hardening_modulus_mpa=1000,
    )
    concrete = AsymmetricConcreteDamageMaterial(
        elastic_modulus_mpa=30000,
        tensile_strength_mpa=3,
        compressive_strength_mpa=30,
        tensile_softening_rate=20,
        compressive_softening_rate=20,
    )
    section = make_rectangular_stateful_rc_fiber_section(
        width_m=0.2,
        depth_m=0.2,
        cover_m=0.03,
        concrete_layer_count=8,
        top_bar_count=2,
        bottom_bar_count=2,
        bar_area_m2=0.0002,
        section_id="diagnostic",
        steel=steel,
        concrete=concrete,
    )
    member = StatefulCorotationalFiberFrame2DMember(
        member_id="column",
        node_i=0,
        node_j=1,
        element=StatefulCorotationalFiberBeam2D(
            node_coordinates_m=coords,
            section=section,
            integration_order=3,
            element_id="column",
        ),
    )
    p = StatefulCorotationalFiberFrame2DProblem(
        case_id="nonlinear-diagnostic",
        node_coordinates_m=coords,
        members=(member,),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((3, 1.0),),
        fixed_external_loads=((4, -10.0),),
        rotation_coordinate_scale_m=1.0,
    )

    pre = solve_stateful_corotational_fiber_frame2d_load_step(
        p,
        initial_stateful_corotational_fiber_frame2d_checkpoint(p),
        target_load_factor=0.0,
    )
    assert pre.committed
    turns = (0.0, 0.005, 0.01, -0.005, -0.01, 0.005)
    coarse = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        p,
        turns[1:],
        initial_checkpoint=pre.accepted_checkpoint,
        control_global_dof=3,
        allow_reversal=True,
    )
    # If convergence improves, success is acceptable; failure must not advance state.
    if not coarse.contract_pass:
        assert coarse.steps[-1].metrics["rollback_exact"]
        assert (
            coarse.final_checkpoint.canonical_bytes()
            == coarse.steps[-1].parent_checkpoint.canonical_bytes()
        )
    targets = tuple(
        v for a, b in zip(turns[:-1], turns[1:]) for v in np.linspace(a, b, 11)[1:]
    )
    kwargs = dict(control_global_dof=3, allow_reversal=True)
    full = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        p,
        targets,
        initial_checkpoint=pre.accepted_checkpoint,
        **kwargs,
    )
    assert full.contract_pass
    observed = {"plastic_strain": 0.0, "tensile_damage": 0.0, "compressive_damage": 0.0}

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in observed:
                    observed[key] = max(observed[key], abs(item))
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for step in full.steps:
        visit(step.accepted_checkpoint.to_dict())
    assert all(value > 0.0 for value in observed.values())
    prefix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        p,
        targets[:25],
        initial_checkpoint=pre.accepted_checkpoint,
        **kwargs,
    )
    assert prefix.contract_pass
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        p, prefix.final_checkpoint
    )
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, p)
    suffix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        p,
        targets[25:],
        initial_checkpoint=restored,
        **kwargs,
    )
    assert suffix.contract_pass
    assert (
        suffix.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )
