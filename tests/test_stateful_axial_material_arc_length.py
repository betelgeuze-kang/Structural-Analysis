from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest

from structural_analysis.assembly.stateful_axial import (
    StatefulAxialChainProblem,
    StatefulAxialElement,
    initial_stateful_axial_state,
    two_element_bilinear_link_chain_problem,
    two_element_composite_section_chain_problem,
    two_element_concrete_damage_chain_problem,
    two_element_stateful_steel_chain_problem,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA_HASH
from structural_analysis.solvers.nonlinear.stateful_axial_material_arc_length import (
    STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION,
    STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION,
    STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION,
    StatefulAxialMaterialArcLengthError,
    StatefulAxialMaterialArcLengthStepProblem,
    finite_difference_stateful_axial_material_arc_length_linearization_check,
    stateful_axial_material_arc_length_continuation,
    validate_stateful_axial_material_arc_length_checkpoint,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthConfig,
    VectorArcLengthTangentSolve,
)


def _force_controlled_concrete_problem() -> StatefulAxialChainProblem:
    material = AsymmetricConcreteDamageMaterial(
        tensile_softening_rate=1_200.0,
    )
    return StatefulAxialChainProblem(
        case_id="stateful_two_dof_force_controlled_concrete_damage",
        node_count=3,
        elements=(
            StatefulAxialElement("bar-1", 0, 1, 1.0, 0.01, material),
            StatefulAxialElement("bar-2", 1, 2, 1.0, 0.01, material),
        ),
        fixed_nodes=(0,),
        reference_external_forces_kn=((2, 30.0),),
    )


def _concrete_path_config() -> VectorArcLengthConfig:
    return VectorArcLengthConfig(
        target_monitor_dof_index=1,
        target_monitor_displacement_m=0.0012,
        target_direction=1,
        initial_arc_length_m=0.00015,
        minimum_arc_length_m=0.0000375,
        maximum_arc_length_m=0.00015,
        failed_step_reduction=0.5,
        load_factor_metric_scale_m=0.00005,
        displacement_metric_weights=(1.0, 1.0),
        residual_tolerance_kn=1.0e-8,
        tangent_solve_residual_tolerance_kn=1.0e-8,
        constraint_tolerance_m2=1.0e-12,
        maximum_corrector_iterations=12,
        maximum_attempt_count=30,
    )


def _steel_reduction_config() -> VectorArcLengthConfig:
    return VectorArcLengthConfig(
        target_monitor_dof_index=1,
        target_monitor_displacement_m=0.004,
        target_direction=1,
        initial_arc_length_m=0.01,
        minimum_arc_length_m=0.0025,
        maximum_arc_length_m=0.01,
        failed_step_reduction=0.5,
        load_factor_metric_scale_m=0.002,
        displacement_metric_weights=(1.0, 1.0),
        residual_tolerance_kn=1.0e-8,
        tangent_solve_residual_tolerance_kn=1.0e-8,
        constraint_tolerance_m2=1.0e-12,
        maximum_corrector_iterations=10,
        maximum_attempt_count=5,
    )


def test_two_dof_damage_path_commits_material_state_past_the_limit_point() -> None:
    problem = _force_controlled_concrete_problem()
    initial = initial_stateful_axial_state(problem)
    result = stateful_axial_material_arc_length_continuation(
        problem,
        config=_concrete_path_config(),
        initial_state=initial,
    )
    payload = result.to_dict()
    committed_loads = [initial.load_factor] + [
        row.accepted_state.load_factor for row in result.attempts if row.committed
    ]
    maximum_load_index = max(
        range(len(committed_loads)),
        key=committed_loads.__getitem__,
    )

    assert result.status == "ready"
    assert result.terminal_reason == "target_monitor_displacement_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["equation_count"] == 2
    assert result.metrics["accepted_step_count"] == 9
    assert result.metrics["rejected_step_count"] == 0
    assert result.metrics["accepted_material_parent_rebind_count"] == 9
    assert result.metrics["material_state_changed_step_count"] == 9
    assert result.metrics["descending_load_branch_observed"] is True
    assert 0 < maximum_load_index < len(committed_loads) - 1
    assert result.final_state.load_factor < max(committed_loads)
    assert result.final_state.displacements_m[2] >= 0.0012
    assert result.metrics["tangent_solve_count"] > 0
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["maximum_accepted_residual_inf_norm_kn"] <= 1.0e-8
    assert result.metrics["maximum_accepted_constraint_residual_m2"] <= 1.0e-12
    assert all(row.rollback_exact for row in result.attempts)
    assert all(
        row.final_assembly is not None
        and row.final_assembly.parent_state_hash == row.parent_state.state_hash
        for row in result.attempts
    )
    assert all(
        current.accepted_state.state_hash == following.parent_state.state_hash
        for current, following in zip(result.attempts, result.attempts[1:])
    )
    assert all(
        after.tensile_damage >= before.tensile_damage
        for before, after in zip(
            initial.material_states,
            result.final_state.material_states,
            strict=True,
        )
    )
    assert payload["claims"]["stateful_material_vector_arc_length_path"] is True
    assert payload["claims"]["descending_load_branch_observed"] is True
    assert payload["claims"]["material_state_embedded_checkpoint"] is True
    assert payload["claims"]["durable_serialized_checkpoint"] is False
    assert payload["claims"]["geometric_frame_shell_arc_length"] is False
    assert payload["claims"]["production_matrix_free_krylov"] is False
    assert payload["claims"]["rocm_hip_parity"] is False
    assert payload["claims"]["lee_frame_benchmark"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


_FAULT_FACTORY_CONTRACT_HASH = canonical_hash(
    {"fault": "reject_state_tangent_solves_above_arc_length_0.005_m"}
)


@dataclass(frozen=True)
class _RejectLargeArcSolver:
    delegate: object
    reject: bool
    profile: str
    contract_hash: str

    def solve_at_state(
        self,
        problem,
        free_displacements_m,
        right_hand_side_kn,
        *,
        load_factor,
        solve_id,
    ) -> VectorArcLengthTangentSolve:
        if self.reject:
            return VectorArcLengthTangentSolve(
                profile=self.profile,
                contract_hash=self.contract_hash,
                contract_pass=False,
                terminal_reason="injected_large_arc_rejection",
                solution_free=tuple(np.zeros_like(right_hand_side_kn)),
                receipt={"fallback_count": 0, "regularization_count": 0},
            )
        result = getattr(self.delegate, "solve_at_state")(
            problem,
            free_displacements_m,
            right_hand_side_kn,
            load_factor=load_factor,
            solve_id=solve_id,
        )
        return replace(
            result,
            profile=self.profile,
            contract_hash=self.contract_hash,
            receipt={**result.receipt, "fault_wrapper": "pass_through"},
        )


def _reject_large_arc_factory(step_problem):
    delegate = create_matrix_free_cpu_fgmres_state_tangent_solver(step_problem)
    reject = step_problem.attempt_arc_length_m > 0.005
    return _RejectLargeArcSolver(
        delegate=delegate,
        reject=reject,
        profile="test_reject_large_material_arc_solver.v1",
        contract_hash=canonical_hash(
            {
                "factory_contract_hash": _FAULT_FACTORY_CONTRACT_HASH,
                "delegate_contract_hash": delegate.contract_hash,
                "reject": reject,
            }
        ),
    )


def test_failed_attempt_rolls_back_exact_material_bytes_before_reduction() -> None:
    problem = two_element_stateful_steel_chain_problem()
    initial = initial_stateful_axial_state(problem)
    initial_bytes = initial.canonical_bytes()
    initial_material_bytes = tuple(
        state.canonical_bytes() for state in initial.material_states
    )
    result = stateful_axial_material_arc_length_continuation(
        problem,
        config=_steel_reduction_config(),
        initial_state=initial,
        solver_factory=_reject_large_arc_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    failed, committed = result.attempts
    failed_checkpoint = result.checkpoints[1]

    assert result.status == "ready"
    assert result.metrics["attempt_count"] == 2
    assert result.metrics["accepted_step_count"] == 1
    assert result.metrics["rejected_step_count"] == 1
    assert result.metrics["failed_step_reduction_count"] == 1
    assert result.metrics["rollback_exact"] is True
    assert failed.outcome == "rolled_back"
    assert failed.stop_reason.endswith("injected_large_arc_rejection")
    assert failed.arc_length_m == 0.01
    assert failed.next_arc_length_m == 0.005
    assert failed.accepted_state is initial
    assert failed.accepted_state.canonical_bytes() == initial_bytes
    assert (
        tuple(
            state.canonical_bytes() for state in failed.accepted_state.material_states
        )
        == initial_material_bytes
    )
    assert failed_checkpoint.accepted_state is initial
    assert failed_checkpoint.current_arc_length_m == 0.005
    assert failed_checkpoint.last_attempt_outcome == "rolled_back"
    assert committed.outcome == "committed"
    assert committed.parent_state is initial
    assert committed.material_state_changed is True
    assert result.final_state.state_hash != initial.state_hash

    restarted = stateful_axial_material_arc_length_continuation(
        problem,
        config=_steel_reduction_config(),
        checkpoint=failed_checkpoint,
        solver_factory=_reject_large_arc_factory,
        solver_factory_contract_hash=_FAULT_FACTORY_CONTRACT_HASH,
    )
    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.metrics["attempt_count"] == result.metrics["attempt_count"]
    assert restarted.metrics["run_attempt_count"] == 1
    assert (
        restarted.final_state.canonical_bytes() == result.final_state.canonical_bytes()
    )
    assert restarted.final_checkpoint.checkpoint_hash == (
        result.final_checkpoint.checkpoint_hash
    )


def test_material_checkpoint_restart_is_bit_identical_on_descending_branch() -> None:
    problem = _force_controlled_concrete_problem()
    config = _concrete_path_config()
    one_shot = stateful_axial_material_arc_length_continuation(
        problem,
        config=config,
    )
    midpoint = one_shot.checkpoints[4]
    restarted = stateful_axial_material_arc_length_continuation(
        problem,
        config=config,
        checkpoint=midpoint,
    )

    assert midpoint.schema_version == (
        STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION
    )
    assert restarted.status == "ready"
    assert restarted.metrics["restart_checkpoint_consumed"] is True
    assert restarted.metrics["attempt_count"] == one_shot.metrics["attempt_count"]
    assert restarted.metrics["run_attempt_count"] == 5
    assert restarted.final_state.state_hash == one_shot.final_state.state_hash
    assert (
        restarted.final_state.canonical_bytes()
        == one_shot.final_state.canonical_bytes()
    )
    assert tuple(
        state.canonical_bytes() for state in restarted.final_state.material_states
    ) == tuple(
        state.canonical_bytes() for state in one_shot.final_state.material_states
    )
    assert restarted.final_checkpoint.checkpoint_hash == (
        one_shot.final_checkpoint.checkpoint_hash
    )


def test_load_coupled_linearization_matches_finite_difference_with_prescribed_load() -> (
    None
):
    problem = two_element_concrete_damage_chain_problem()
    accepted = initial_stateful_axial_state(problem)
    step_problem = StatefulAxialMaterialArcLengthStepProblem(
        problem,
        accepted,
        0.0002,
    )
    check = finite_difference_stateful_axial_material_arc_length_linearization_check(
        step_problem,
        displacement_increments_m=np.asarray([-0.0007]),
        increment_load_factor=0.5,
        direction_m=np.asarray([0.7]),
        displacement_epsilon_m=1.0e-9,
        load_factor_epsilon=1.0e-7,
        relative_tolerance=1.0e-7,
    )

    assert check["contract_pass"] is True
    assert check["same_accepted_material_parent_state"] is True
    assert check["displacement_relative_error"] <= check["relative_tolerance"]
    assert check["load_factor_relative_error"] <= check["relative_tolerance"]
    assert check["residual_formula_hash"] == RESIDUAL_FORMULA_HASH
    assert check["tangent_action"] == (
        STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_TANGENT_ACTION
    )
    assert check["load_linearization"] == (
        STATEFUL_AXIAL_MATERIAL_ARC_LENGTH_LOAD_LINEARIZATION
    )
    assert accepted == initial_stateful_axial_state(problem)


@pytest.mark.parametrize(
    (
        "problem_factory",
        "monitor_index",
        "target_displacement_m",
        "target_direction",
        "arc_length_m",
        "load_metric_scale_m",
    ),
    (
        (
            two_element_stateful_steel_chain_problem,
            1,
            0.004,
            1,
            0.005,
            0.002,
        ),
        (
            two_element_concrete_damage_chain_problem,
            0,
            -0.0005,
            -1,
            0.0004,
            0.0002,
        ),
        (
            two_element_composite_section_chain_problem,
            0,
            0.0005,
            1,
            0.0004,
            0.0002,
        ),
        (
            two_element_bilinear_link_chain_problem,
            0,
            0.012,
            1,
            0.004,
            0.002,
        ),
    ),
    ids=("steel", "concrete_damage", "composite", "bilinear_link"),
)
def test_arc_length_commits_every_bounded_material_family(
    problem_factory,
    monitor_index,
    target_displacement_m,
    target_direction,
    arc_length_m,
    load_metric_scale_m,
) -> None:
    problem = problem_factory()
    config = VectorArcLengthConfig(
        target_monitor_dof_index=monitor_index,
        target_monitor_displacement_m=target_displacement_m,
        target_direction=target_direction,
        initial_arc_length_m=arc_length_m,
        minimum_arc_length_m=arc_length_m / 8.0,
        maximum_arc_length_m=arc_length_m,
        failed_step_reduction=0.5,
        load_factor_metric_scale_m=load_metric_scale_m,
        displacement_metric_weights=tuple(1.0 for _ in problem.free_node_indices),
        residual_tolerance_kn=1.0e-8,
        tangent_solve_residual_tolerance_kn=1.0e-8,
        constraint_tolerance_m2=1.0e-12,
        maximum_corrector_iterations=12,
        maximum_attempt_count=20,
    )
    result = stateful_axial_material_arc_length_continuation(
        problem,
        config=config,
    )

    assert result.status == "ready"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["accepted_step_count"] > 0
    assert result.metrics["material_state_changed_step_count"] > 0
    assert (
        result.metrics["accepted_material_parent_rebind_count"]
        == (result.metrics["accepted_step_count"])
    )
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0


def test_checkpoint_rejects_tamper_source_drift_and_path_drift() -> None:
    problem = _force_controlled_concrete_problem()
    config = _concrete_path_config()
    checkpoint = stateful_axial_material_arc_length_continuation(
        problem,
        config=config,
    ).checkpoints[3]

    with pytest.raises(
        StatefulAxialMaterialArcLengthError,
        match="checkpoint_hash mismatch",
    ):
        replace(
            checkpoint,
            current_arc_length_m=checkpoint.current_arc_length_m / 2.0,
        )

    modified_material = replace(
        problem.elements[0].material,
        elastic_modulus_mpa=29_000.0,
    )
    modified_problem = replace(
        problem,
        elements=tuple(
            replace(element, material=modified_material) for element in problem.elements
        ),
    )
    with pytest.raises(
        StatefulAxialMaterialArcLengthError,
        match="source problem contract mismatch",
    ):
        validate_stateful_axial_material_arc_length_checkpoint(
            checkpoint,
            modified_problem,
            config,
        )

    with pytest.raises(
        StatefulAxialMaterialArcLengthError,
        match="path contract mismatch",
    ):
        validate_stateful_axial_material_arc_length_checkpoint(
            checkpoint,
            problem,
            replace(config, maximum_attempt_count=31),
        )


def test_custom_solver_factory_requires_explicit_path_contract_hash() -> None:
    with pytest.raises(
        StatefulAxialMaterialArcLengthError,
        match="requires solver_factory_contract_hash",
    ):
        stateful_axial_material_arc_length_continuation(
            two_element_stateful_steel_chain_problem(),
            config=_steel_reduction_config(),
            solver_factory=_reject_large_arc_factory,
        )
