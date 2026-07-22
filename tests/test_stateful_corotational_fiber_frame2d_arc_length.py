from __future__ import annotations

import json

import pytest

from structural_analysis.assembly import (
    StatefulCorotationalFiberFrame2DArcLengthError,
    StatefulCorotationalFiberFrame2DArcLengthStepProblem,
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    finite_difference_stateful_corotational_fiber_frame2d_arc_length_linearization_check,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes,
    read_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact,
    stateful_corotational_fiber_frame2d_arc_length_continuation,
    write_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials import (
    AsymmetricConcreteDamageMaterial,
    BilinearCombinedHardeningSteel,
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthConfig,
)


COORDINATES = ((-1.0, 0.0), (0.0, 0.1), (1.0, 0.0))


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


def _problem(
    *,
    case_id: str,
    all_fixed: bool = False,
) -> StatefulCorotationalFiberFrame2DProblem:
    steel, concrete = _elastic_materials()
    members = tuple(
        StatefulCorotationalFiberFrame2DMember(
            member_id=f"arch-member-{index}",
            node_i=node_i,
            node_j=node_j,
            element=StatefulCorotationalFiberBeam2D(
                node_coordinates_m=(
                    COORDINATES[node_i],
                    COORDINATES[node_j],
                ),
                section=make_rectangular_stateful_rc_fiber_section(
                    width_m=0.02,
                    depth_m=0.02,
                    cover_m=0.004,
                    concrete_layer_count=4,
                    top_bar_count=1,
                    bottom_bar_count=1,
                    bar_area_m2=1.0e-8,
                    section_id=f"arch-section-{index}",
                    steel=steel,
                    concrete=concrete,
                ),
                integration_order=3,
                element_id=f"arch-member-{index}",
            ),
        )
        for index, (node_i, node_j) in enumerate(((0, 1), (1, 2)), start=1)
    )
    fixed = tuple(range(9)) if all_fixed else tuple(dof for dof in range(9) if dof != 4)
    return StatefulCorotationalFiberFrame2DProblem(
        case_id=case_id,
        node_coordinates_m=COORDINATES,
        members=members,
        fixed_global_dofs=fixed,
        reference_external_loads=((4, -1.0),),
        rotation_coordinate_scale_m=1.0,
    )


def _path_config(
    *,
    target_displacement_m: float = -0.18,
    initial_arc_length_m: float = 0.006,
    minimum_arc_length_m: float = 0.00075,
    maximum_corrector_iterations: int = 12,
    maximum_attempt_count: int = 100,
) -> VectorArcLengthConfig:
    return VectorArcLengthConfig(
        target_monitor_dof_index=0,
        target_monitor_displacement_m=target_displacement_m,
        target_direction=-1,
        initial_arc_length_m=initial_arc_length_m,
        minimum_arc_length_m=minimum_arc_length_m,
        maximum_arc_length_m=initial_arc_length_m,
        failed_step_reduction=0.5,
        load_factor_metric_scale_m=0.001,
        residual_tolerance_kn=1.0e-9,
        constraint_tolerance_m2=1.0e-12,
        maximum_corrector_iterations=maximum_corrector_iterations,
        maximum_attempt_count=maximum_attempt_count,
    )


@pytest.fixture(scope="module")
def limit_path():
    problem = _problem(case_id="stateful-corotational-arch-limit-path")
    config = _path_config()
    result = stateful_corotational_fiber_frame2d_arc_length_continuation(
        problem,
        config=config,
    )
    return problem, config, result


def test_actual_frame_path_crosses_limit_point_and_rehardens(limit_path) -> None:
    problem, config, result = limit_path

    assert result.status == "ready"
    assert result.terminal_reason == "target_monitor_displacement_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["equation_count"] == 1
    assert result.metrics["accepted_step_count"] == 36
    assert result.metrics["rejected_step_count"] == 0
    assert result.metrics["dense_linear_solve_count"] > 0
    assert result.metrics["descending_load_branch_observed"] is True
    assert result.metrics["negative_load_factor_observed"] is True
    assert result.metrics["rehardening_load_branch_observed"] is True
    assert result.metrics["maximum_load_factor"] == pytest.approx(
        33.00941222046854,
        rel=1.0e-10,
    )
    assert result.metrics["minimum_load_factor"] == pytest.approx(
        -21.110341717052528,
        rel=1.0e-10,
    )
    assert result.metrics["maximum_accepted_residual_inf_norm_kn"] <= (
        config.residual_tolerance_kn
    )
    assert result.metrics["maximum_accepted_constraint_residual_m2"] <= (
        config.constraint_tolerance_m2
    )
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["rollback_exact"] is True
    assert result.final_state.global_displacements[4] < -0.18

    loads = [row.accepted_checkpoint.load_factor for row in result.checkpoints]
    first_local_maximum = next(
        index
        for index in range(1, len(loads) - 1)
        if loads[index - 1] < loads[index] > loads[index + 1]
    )
    assert result.checkpoints[
        first_local_maximum
    ].accepted_checkpoint.global_displacements[4] == pytest.approx(
        -0.04652497596624846, rel=1.0e-10
    )
    parent = result.initial_state
    for attempt in result.attempts:
        assert attempt.committed is True
        assert attempt.parent_checkpoint.state_hash == parent.state_hash
        assert attempt.accepted_checkpoint.parent_state_hash == parent.state_hash
        assert attempt.final_assembly is not None
        assert attempt.final_assembly.parent_checkpoint_hash == parent.state_hash
        parent = attempt.accepted_checkpoint

    payload = result.to_dict()
    assert (
        payload["claims"]["stateful_corotational_fiber_frame2d_arc_length_path"] is True
    )
    assert payload["claims"]["material_plus_geometric_consistent_tangent"] is True
    assert payload["claims"]["source_bound_persisted_checkpoint"] is True
    assert payload["claims"]["external_benchmark_acceptance"] is False
    assert payload["claims"]["lee_frame_acceptance"] is False
    assert payload["claims"]["production_sparse_solver"] is False
    assert payload["claims"]["rocm_hip_parity"] is False
    assert payload["claims"]["g1_full_building_closure"] is False
    assert payload["claims"]["commercial_readiness"] is False
    json.dumps(payload, allow_nan=False, sort_keys=True)

    repeated = stateful_corotational_fiber_frame2d_arc_length_continuation(
        problem,
        config=config,
    )
    assert repeated.to_dict() == result.to_dict()
    assert repeated.final_state.canonical_bytes() == (
        result.final_state.canonical_bytes()
    )


def test_persisted_direction_restart_matches_one_shot(limit_path, tmp_path) -> None:
    problem, config, one_shot = limit_path
    restart_boundary = one_shot.checkpoints[18]
    raw = restart_boundary.to_bytes()
    restored = load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes(
        raw,
        problem,
        config,
    )
    restarted = stateful_corotational_fiber_frame2d_arc_length_continuation(
        problem,
        config=config,
        checkpoint=restored,
    )

    assert restored.to_bytes() == raw
    assert restored.previous_tangent_displacements is not None
    assert restored.previous_tangent_load_factor is not None
    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.metrics["attempt_count"] == one_shot.metrics["attempt_count"]
    assert (
        restarted.metrics["accepted_step_count"]
        == (one_shot.metrics["accepted_step_count"])
    )
    assert restarted.metrics["descending_load_branch_observed"] is True
    assert restarted.metrics["negative_load_factor_observed"] is True
    assert restarted.metrics["rehardening_load_branch_observed"] is True
    assert restarted.final_checkpoint.checkpoint_hash == (
        one_shot.final_checkpoint.checkpoint_hash
    )
    assert restarted.final_state.canonical_bytes() == (
        one_shot.final_state.canonical_bytes()
    )

    artifact = tmp_path / "corotational-arc-length-checkpoint.json"
    write_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact(
        problem,
        config,
        restart_boundary,
        artifact,
    )
    reread = read_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact(
        problem,
        config,
        artifact,
    )
    assert reread.to_bytes() == raw
    with pytest.raises(
        StatefulCorotationalFiberFrame2DArcLengthError,
        match="already exists",
    ):
        write_stateful_corotational_fiber_frame2d_arc_length_checkpoint_artifact(
            problem,
            config,
            restart_boundary,
            artifact,
        )


def test_actual_corrector_failures_cut_back_with_exact_full_state_rollback() -> None:
    problem = _problem(case_id="stateful-corotational-arch-cutback")
    config = _path_config(
        target_displacement_m=-0.08,
        initial_arc_length_m=0.08,
        minimum_arc_length_m=0.005,
        maximum_corrector_iterations=4,
        maximum_attempt_count=40,
    )
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    initial_bytes = initial.canonical_bytes()
    result = stateful_corotational_fiber_frame2d_arc_length_continuation(
        problem,
        config=config,
        initial_state=initial,
    )

    assert result.status == "ready"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["accepted_step_count"] == 15
    assert result.metrics["rejected_step_count"] == 4
    assert result.metrics["failed_step_reduction_count"] == 4
    assert result.metrics["rollback_exact"] is True
    assert [row.outcome for row in result.attempts[:3]] == [
        "rolled_back",
        "rolled_back",
        "committed",
    ]
    assert [row.arc_length_m for row in result.attempts[:3]] == [0.08, 0.04, 0.02]
    assert result.attempts[0].parent_checkpoint is initial
    assert result.attempts[0].accepted_checkpoint is initial
    assert result.attempts[0].accepted_checkpoint.canonical_bytes() == initial_bytes
    assert result.attempts[1].accepted_checkpoint.canonical_bytes() == initial_bytes
    for row in result.attempts:
        if row.committed:
            continue
        assert row.rollback_exact is True
        assert row.final_assembly is None
        assert row.parent_checkpoint.canonical_bytes() == (
            row.accepted_checkpoint.canonical_bytes()
        )
        assert row.next_arc_length_m == pytest.approx(0.5 * row.arc_length_m)


def test_same_parent_material_geometric_linearization_is_finite_difference_exact() -> (
    None
):
    problem = _problem(case_id="stateful-corotational-arch-linearization")
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    step_problem = StatefulCorotationalFiberFrame2DArcLengthStepProblem(
        problem=problem,
        accepted_checkpoint=initial,
        attempt_arc_length_m=0.006,
    )
    check = finite_difference_stateful_corotational_fiber_frame2d_arc_length_linearization_check(
        step_problem,
        free_displacements_m=(-0.03,),
        load_factor=30.0,
        direction_m=(-1.0,),
    )

    assert check["contract_pass"] is True
    assert check["same_immutable_parent"] is True
    assert check["tangent_definition"] == "material_plus_geometric_consistent"
    assert check["displacement_relative_error"] <= check["relative_tolerance"]
    assert check["load_factor_relative_error"] <= check["relative_tolerance"]
    assert initial.epoch == 0
    assert initial.canonical_bytes() == (
        initial_stateful_corotational_fiber_frame2d_checkpoint(
            problem
        ).canonical_bytes()
    )


def test_checkpoint_tampering_wrong_source_and_fully_constrained_policy(
    limit_path,
) -> None:
    problem, config, result = limit_path
    raw = result.checkpoints[10].to_bytes()
    tampered = json.loads(raw)
    tampered["boundary"]["current_arc_length_m"] = 0.003
    tampered_raw = json.dumps(
        tampered,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(
        StatefulCorotationalFiberFrame2DArcLengthError,
        match="checkpoint_hash mismatch",
    ):
        load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes(
            tampered_raw,
            problem,
            config,
        )

    other_problem = _problem(case_id="stateful-corotational-arch-wrong-source")
    with pytest.raises((StatefulCorotationalFiberFrame2DArcLengthError, ValueError)):
        load_stateful_corotational_fiber_frame2d_arc_length_checkpoint_bytes(
            raw,
            other_problem,
            config,
        )

    all_fixed = _problem(
        case_id="stateful-corotational-arch-reaction-only",
        all_fixed=True,
    )
    with pytest.raises(
        StatefulCorotationalFiberFrame2DArcLengthError,
        match="reaction-only outcomes",
    ):
        stateful_corotational_fiber_frame2d_arc_length_continuation(
            all_fixed,
            config=config,
        )
