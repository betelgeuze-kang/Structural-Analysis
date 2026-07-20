"""Bounded coordinate-transformed two-member stateful fiber-frame receipt."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DMember,
    StatefulFiberFrame2DProblem,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE,
    dump_stateful_fiber_frame2d_checkpoint_bytes,
    load_stateful_fiber_frame2d_checkpoint_bytes,
    stateful_fiber_frame2d_checkpoint_artifact_hash,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_STORAGE_PROFILE,
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
    stateful_fiber_frame2d_checkpoint_chain_artifact_hash,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
    run_stateful_fiber_frame2d_load_path,
    solve_stateful_fiber_frame2d_load_step,
)
from structural_analysis.benchmark.stateful_fiber_frame2d_diagnostics import (
    finite_difference_stateful_fiber_frame2d_tangent_check,
)
from structural_analysis.elements.axial_curvature_section import (
    AxialCurvatureSection,
)
from structural_analysis.elements.stateful_fiber_beam2d import (
    StatefulFiberBeam2D,
)
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


STATEFUL_FIBER_FRAME2D_BENCHMARK_SCHEMA_VERSION = (
    "phase2-stateful-fiber-frame2d-global-assembly.v3"
)
STATEFUL_FIBER_FRAME2D_CLAIM_BOUNDARY = (
    "This receipt verifies fixed initial-chord coordinate transformation, "
    "dense global assembly of two small-displacement Euler-Bernoulli members, "
    "stateful RC axial-curvature sections, a consistent free-equation tangent, "
    "an in-memory committed checkpoint chain with parent hashes and epochs, and "
    "exact schema-validated single-checkpoint and complete epoch-zero-rooted "
    "ancestor-chain persisted round-trips plus restart for the built-in RC fiber "
    "state family. It does not validate geometric nonlinearity, shear deformation, "
    "torsion, a general frame model importer, a generalized section-state codec "
    "registry, constitutive transition replay from chain contents alone, "
    "mesh-objective distributed plasticity, external benchmarks, production "
    "sparse or ROCm/HIP execution, full-building equilibrium, or G1 closure."
)


def make_two_element_stateful_fiber_cantilever(
    *,
    angle_rad: float = 0.0,
    tip_shear_kn: float = -10.0,
) -> StatefulFiberFrame2DProblem:
    """Create a straight 3 m cantilever split into two transformed members."""

    angle = float(angle_rad)
    load = float(tip_shear_kn)
    if not math.isfinite(angle) or not math.isfinite(load) or load == 0.0:
        raise ValueError("angle_rad and nonzero tip_shear_kn must be finite")
    member_length = 1.5
    cosine = math.cos(angle)
    sine = math.sin(angle)
    coordinates = tuple(
        (
            member_length * node * cosine,
            member_length * node * sine,
        )
        for node in range(3)
    )
    section = make_rectangular_stateful_rc_fiber_section()
    members = tuple(
        StatefulFiberFrame2DMember(
            member_id=f"cantilever-member-{index + 1}",
            node_i=index,
            node_j=index + 1,
            element=StatefulFiberBeam2D(
                section=section,
                length_m=member_length,
                integration_order=3,
                element_id=f"cantilever-member-{index + 1}",
            ),
        )
        for index in range(2)
    )
    magnitude = abs(load)
    sign = 1.0 if load > 0.0 else -1.0
    global_x = -sign * magnitude * sine
    global_y = sign * magnitude * cosine
    return StatefulFiberFrame2DProblem(
        case_id=f"two_element_stateful_fiber_cantilever_angle_{angle:.12g}",
        node_coordinates_m=coordinates,
        members=members,
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((6, global_x), (7, global_y)),
        rotation_coordinate_scale_m=member_length,
    )


def make_two_member_stateful_fiber_l_frame() -> StatefulFiberFrame2DProblem:
    """Create the bounded non-collinear material-state load-path problem."""

    section = make_rectangular_stateful_rc_fiber_section()
    lengths = (2.0, 1.5)
    members = tuple(
        StatefulFiberFrame2DMember(
            member_id=f"l-frame-member-{index + 1}",
            node_i=index,
            node_j=index + 1,
            element=StatefulFiberBeam2D(
                section=section,
                length_m=lengths[index],
                integration_order=3,
                element_id=f"l-frame-member-{index + 1}",
            ),
        )
        for index in range(2)
    )
    return StatefulFiberFrame2DProblem(
        case_id="two_member_stateful_fiber_l_frame",
        node_coordinates_m=((0.0, 0.0), (2.0, 0.0), (2.0, 1.5)),
        members=members,
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((7, -150.0),),
        rotation_coordinate_scale_m=1.5,
    )


def _local_nodal_displacements(
    problem: StatefulFiberFrame2DProblem,
    global_displacements: tuple[float, ...],
) -> np.ndarray:
    physical = np.asarray(global_displacements, dtype=np.float64).reshape((-1, 3))
    angle = math.atan2(
        problem.node_coordinates_m[1][1] - problem.node_coordinates_m[0][1],
        problem.node_coordinates_m[1][0] - problem.node_coordinates_m[0][0],
    )
    rotation = np.asarray(
        [
            [math.cos(angle), math.sin(angle)],
            [-math.sin(angle), math.cos(angle)],
        ],
        dtype=np.float64,
    )
    local = np.zeros_like(physical)
    local[:, :2] = (rotation @ physical[:, :2].T).T
    local[:, 2] = physical[:, 2]
    return local


def _elastic_cantilever_check() -> dict[str, Any]:
    problem = make_two_element_stateful_fiber_cantilever()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    result = solve_stateful_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=1.0,
    )
    section = problem.members[0].element.section
    section_response = section.integrate((0.0, 0.0), section.initial_state())
    flexural_rigidity = float(section_response.consistent_tangent[1, 1])
    length = 3.0
    load = 10.0
    expected_tip = np.asarray(
        [
            0.0,
            -load * length**3 / (3.0 * flexural_rigidity),
            -load * length**2 / (2.0 * flexural_rigidity),
        ],
        dtype=np.float64,
    )
    local = _local_nodal_displacements(
        problem,
        result.accepted_checkpoint.global_displacements,
    )
    reaction = result.trial_assembly.reactions_global[:3]
    expected_reaction = np.asarray((0.0, load, load * length), dtype=np.float64)
    displacement_error = float(np.linalg.norm(local[-1] - expected_tip, ord=np.inf))
    reaction_error = float(np.linalg.norm(reaction - expected_reaction, ord=np.inf))
    gate = bool(
        result.committed
        and displacement_error <= 1.0e-14
        and reaction_error <= 1.0e-10
        and result.accepted_checkpoint.parent_state_hash == initial.state_hash
        and result.accepted_checkpoint.epoch == 1
    )
    return {
        "pass": gate,
        "flexural_rigidity_kn_m2": flexural_rigidity,
        "expected_tip_local": expected_tip.tolist(),
        "actual_tip_local": local[-1].tolist(),
        "maximum_tip_abs_error": displacement_error,
        "expected_base_reaction_local": expected_reaction.tolist(),
        "actual_base_reaction_local": reaction.tolist(),
        "maximum_reaction_abs_error": reaction_error,
        "checkpoint_hash": result.accepted_checkpoint.state_hash,
    }


def _rotation_invariance_check() -> dict[str, Any]:
    baseline_problem = make_two_element_stateful_fiber_cantilever()
    rotated_problem = make_two_element_stateful_fiber_cantilever(angle_rad=0.617)
    baseline = solve_stateful_fiber_frame2d_load_step(
        baseline_problem,
        initial_stateful_fiber_frame2d_checkpoint(baseline_problem),
        target_load_factor=1.0,
    )
    rotated = solve_stateful_fiber_frame2d_load_step(
        rotated_problem,
        initial_stateful_fiber_frame2d_checkpoint(rotated_problem),
        target_load_factor=1.0,
    )
    baseline_local = _local_nodal_displacements(
        baseline_problem,
        baseline.accepted_checkpoint.global_displacements,
    )
    rotated_local = _local_nodal_displacements(
        rotated_problem,
        rotated.accepted_checkpoint.global_displacements,
    )
    displacement_error = float(
        np.linalg.norm(rotated_local - baseline_local, ord=np.inf)
    )
    baseline_reaction = baseline.trial_assembly.reactions_global[:3]
    rotated_reaction = rotated.trial_assembly.reactions_global[:3]
    angle = 0.617
    rotation = np.asarray(
        [
            [math.cos(angle), math.sin(angle)],
            [-math.sin(angle), math.cos(angle)],
        ],
        dtype=np.float64,
    )
    rotated_reaction_local = np.asarray(
        [
            *(rotation @ rotated_reaction[:2]),
            rotated_reaction[2],
        ],
        dtype=np.float64,
    )
    reaction_error = float(
        np.linalg.norm(rotated_reaction_local - baseline_reaction, ord=np.inf)
    )
    return {
        "pass": bool(
            baseline.committed
            and rotated.committed
            and displacement_error <= 1.0e-13
            and reaction_error <= 1.0e-10
        ),
        "angle_rad": angle,
        "local_displacement_inf_error": displacement_error,
        "local_reaction_inf_error": reaction_error,
    }


def _nonlinear_tangent_check() -> dict[str, Any]:
    problem = make_two_element_stateful_fiber_cantilever()
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)
    physical = np.zeros(problem.global_dof_count, dtype=np.float64)
    axial_strain = -3.0e-4
    curvature = 6.0e-3
    for node, coordinate in enumerate((0.0, 1.5, 3.0)):
        physical[3 * node] = axial_strain * coordinate
        physical[3 * node + 1] = 0.5 * curvature * coordinate**2
        physical[3 * node + 2] = curvature * coordinate
    generalized = physical / problem.physical_coordinate_scale
    return finite_difference_stateful_fiber_frame2d_tangent_check(
        problem,
        checkpoint,
        target_load_factor=0.0,
        trial_free_coordinates_m=generalized[list(problem.free_global_dofs)],
    )


def _path_summary(path: StatefulFiberFrame2DLoadPathResult) -> dict[str, Any]:
    return {
        "status": path.status,
        "contract_pass": path.contract_pass,
        "initial_checkpoint_hash": path.initial_checkpoint.state_hash,
        "initial_epoch": path.initial_checkpoint.epoch,
        "final_checkpoint_hash": path.final_checkpoint.state_hash,
        "final_epoch": path.final_checkpoint.epoch,
        "steps": [
            {
                "target_load_factor": step.metrics["target_load_factor"],
                "status": step.status,
                "committed": step.committed,
                "parent_checkpoint_hash": step.parent_checkpoint.state_hash,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "parent_epoch": step.parent_checkpoint.epoch,
                "accepted_epoch": step.accepted_checkpoint.epoch,
                "accepted_parent_state_hash": (
                    step.accepted_checkpoint.parent_state_hash
                ),
                "iteration_count": step.trial_solution.metrics.get(
                    "iteration_count",
                    0,
                ),
                "relative_residual": step.trial_solution.metrics.get(
                    "relative_residual"
                ),
                "parent_binding_passed": step.metrics[
                    "section_and_element_parent_binding_passed"
                ],
                "yielded_member_count": step.metrics["yielded_member_count"],
                "damaged_member_count": step.metrics["damaged_member_count"],
                "fallback_used": step.metrics["fallback_used"],
                "regularization_used": step.metrics["regularization_used"],
            }
            for step in path.steps
        ],
    }


@lru_cache(maxsize=1)
def _build_stateful_fiber_frame2d_benchmark_cached() -> dict[str, Any]:
    elastic = _elastic_cantilever_check()
    rotation = _rotation_invariance_check()
    tangent = _nonlinear_tangent_check()
    factors = (0.25, 0.5, 0.75, 1.0)
    config = NewtonRaphsonConfig(max_iterations=40)

    path_problem = make_two_member_stateful_fiber_l_frame()
    first = run_stateful_fiber_frame2d_load_path(
        path_problem,
        factors,
        config=config,
    )
    repeated_problem = make_two_member_stateful_fiber_l_frame()
    repeated = run_stateful_fiber_frame2d_load_path(
        repeated_problem,
        factors,
        config=config,
    )
    restart_problem = make_two_member_stateful_fiber_l_frame()
    prefix = run_stateful_fiber_frame2d_load_path(
        restart_problem,
        factors[:2],
        config=config,
    )
    resumed = run_stateful_fiber_frame2d_load_path(
        restart_problem,
        factors[2:],
        initial_checkpoint=deepcopy(prefix.final_checkpoint),
        config=config,
    )
    checkpoint_artifact = dump_stateful_fiber_frame2d_checkpoint_bytes(
        restart_problem,
        prefix.final_checkpoint,
    )
    persisted_restart_problem = make_two_member_stateful_fiber_l_frame()
    persisted_checkpoint = load_stateful_fiber_frame2d_checkpoint_bytes(
        checkpoint_artifact,
        persisted_restart_problem,
    )
    persisted_resumed = run_stateful_fiber_frame2d_load_path(
        persisted_restart_problem,
        factors[2:],
        initial_checkpoint=persisted_checkpoint,
        config=config,
    )
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        restart_problem,
        (
            prefix.initial_checkpoint,
            *(step.accepted_checkpoint for step in prefix.steps),
        ),
    )
    checkpoint_chain_artifact = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
        restart_problem,
        checkpoint_chain,
    )
    persisted_chain_problem = make_two_member_stateful_fiber_l_frame()
    persisted_checkpoint_chain = load_stateful_fiber_frame2d_checkpoint_chain_bytes(
        checkpoint_chain_artifact,
        persisted_chain_problem,
    )
    persisted_chain_resumed = run_stateful_fiber_frame2d_load_path(
        persisted_chain_problem,
        factors[2:],
        initial_checkpoint=persisted_checkpoint_chain.terminal_checkpoint,
        config=config,
    )
    rollback_problem = make_two_member_stateful_fiber_l_frame()
    rollback_parent = initial_stateful_fiber_frame2d_checkpoint(rollback_problem)
    rollback_parent_bytes = rollback_parent.canonical_bytes()
    forced_failure = solve_stateful_fiber_frame2d_load_step(
        rollback_problem,
        rollback_parent,
        target_load_factor=1.0,
        config=NewtonRaphsonConfig(max_iterations=0),
    )

    first_summary = _path_summary(first)
    repeated_summary = _path_summary(repeated)
    resumed_summary = _path_summary(resumed)
    persisted_resumed_summary = _path_summary(persisted_resumed)
    ancestry_gate = bool(
        first.contract_pass
        and first.final_checkpoint.epoch == len(factors)
        and all(
            step.accepted_checkpoint.parent_state_hash
            == step.parent_checkpoint.state_hash
            and step.accepted_checkpoint.epoch == step.parent_checkpoint.epoch + 1
            and all(
                element_state.step_index == step.accepted_checkpoint.epoch
                for element_state in step.accepted_checkpoint.element_states
            )
            for step in first.steps
        )
    )
    nonlinear_state_gate = bool(
        any(step.metrics["damaged_member_count"] > 0 for step in first.steps)
        and first.final_checkpoint.state_hash != first.initial_checkpoint.state_hash
    )
    deterministic_gate = first_summary == repeated_summary
    restart_gate = bool(
        prefix.contract_pass
        and resumed.contract_pass
        and resumed.initial_checkpoint.state_hash == prefix.final_checkpoint.state_hash
        and resumed.initial_checkpoint.epoch == 2
        and resumed.final_checkpoint.state_hash == first.final_checkpoint.state_hash
        and resumed.final_checkpoint.canonical_bytes()
        == first.final_checkpoint.canonical_bytes()
    )
    persistent_roundtrip_gate = bool(
        persisted_checkpoint.state_hash == prefix.final_checkpoint.state_hash
        and persisted_checkpoint.canonical_bytes()
        == prefix.final_checkpoint.canonical_bytes()
        and dump_stateful_fiber_frame2d_checkpoint_bytes(
            persisted_restart_problem,
            persisted_checkpoint,
        )
        == checkpoint_artifact
        and persisted_resumed.contract_pass
        and persisted_resumed.initial_checkpoint.state_hash
        == prefix.final_checkpoint.state_hash
        and persisted_resumed.final_checkpoint.state_hash
        == first.final_checkpoint.state_hash
        and persisted_resumed.final_checkpoint.canonical_bytes()
        == first.final_checkpoint.canonical_bytes()
    )
    persistent_chain_gate = bool(
        len(persisted_checkpoint_chain.checkpoints) == 3
        and persisted_checkpoint_chain.root_checkpoint.state_hash
        == prefix.initial_checkpoint.state_hash
        and persisted_checkpoint_chain.terminal_checkpoint.state_hash
        == prefix.final_checkpoint.state_hash
        and persisted_checkpoint_chain.chain_hash == checkpoint_chain.chain_hash
        and persisted_checkpoint_chain.canonical_bytes()
        == checkpoint_chain.canonical_bytes()
        and dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
            persisted_chain_problem,
            persisted_checkpoint_chain,
        )
        == checkpoint_chain_artifact
        and persisted_chain_resumed.contract_pass
        and persisted_chain_resumed.initial_checkpoint.state_hash
        == prefix.final_checkpoint.state_hash
        and persisted_chain_resumed.final_checkpoint.state_hash
        == first.final_checkpoint.state_hash
        and persisted_chain_resumed.final_checkpoint.canonical_bytes()
        == first.final_checkpoint.canonical_bytes()
    )
    rollback_gate = bool(
        forced_failure.committed is False
        and forced_failure.accepted_checkpoint is rollback_parent
        and forced_failure.accepted_checkpoint.canonical_bytes()
        == rollback_parent_bytes
        and forced_failure.metrics["rollback_exact"] is True
    )
    section_protocol_gate = all(
        isinstance(member.element.section, AxialCurvatureSection)
        for member in path_problem.members
    )
    contract_pass = bool(
        elastic["pass"]
        and rotation["pass"]
        and tangent["pass"]
        and ancestry_gate
        and nonlinear_state_gate
        and deterministic_gate
        and restart_gate
        and persistent_roundtrip_gate
        and persistent_chain_gate
        and rollback_gate
        and section_protocol_gate
        and all(
            step.metrics["fallback_used"] is False
            and step.metrics["regularization_used"] is False
            for step in first.steps
        )
    )
    return {
        "schema_version": STATEFUL_FIBER_FRAME2D_BENCHMARK_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": path_problem.case_id,
        "problem_contract_hash": path_problem.contract_hash,
        "member_count": len(path_problem.members),
        "node_count": len(path_problem.node_coordinates_m),
        "free_equation_count": len(path_problem.free_global_dofs),
        "elastic_two_element_cantilever": elastic,
        "rotation_invariance": rotation,
        "global_tangent_finite_difference": tangent,
        "nonlinear_l_frame_path": first_summary,
        "resumed_path": resumed_summary,
        "persisted_resumed_path": persisted_resumed_summary,
        "persisted_checkpoint_artifact": {
            "storage_profile": STATEFUL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE,
            "byte_length": len(checkpoint_artifact),
            "artifact_hash": stateful_fiber_frame2d_checkpoint_artifact_hash(
                checkpoint_artifact
            ),
            "accepted_checkpoint_hash": prefix.final_checkpoint.state_hash,
            "restored_checkpoint_hash": persisted_checkpoint.state_hash,
            "exact_roundtrip_and_restart": persistent_roundtrip_gate,
        },
        "persisted_checkpoint_ancestor_chain_artifact": {
            "storage_profile": (
                STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_STORAGE_PROFILE
            ),
            "checkpoint_count": len(checkpoint_chain.checkpoints),
            "byte_length": len(checkpoint_chain_artifact),
            "artifact_hash": (
                stateful_fiber_frame2d_checkpoint_chain_artifact_hash(
                    checkpoint_chain_artifact
                )
            ),
            "chain_hash": checkpoint_chain.chain_hash,
            "root_checkpoint_hash": checkpoint_chain.root_checkpoint.state_hash,
            "terminal_checkpoint_hash": (
                checkpoint_chain.terminal_checkpoint.state_hash
            ),
            "exact_roundtrip_and_restart": persistent_chain_gate,
        },
        "forced_failure": {
            "status": forced_failure.status,
            "terminal_reason": forced_failure.metrics["terminal_reason"],
            "parent_checkpoint_hash": rollback_parent.state_hash,
            "accepted_checkpoint_hash": (forced_failure.accepted_checkpoint.state_hash),
            "rollback_exact": forced_failure.metrics["rollback_exact"],
        },
        "verification": {
            "axial_curvature_section_protocol_passed": section_protocol_gate,
            "two_element_elastic_closed_form_passed": elastic["pass"],
            "fixed_transform_rotation_invariance_passed": rotation["pass"],
            "consistent_global_tangent_finite_difference_passed": tangent["pass"],
            "checkpoint_parent_hash_and_epoch_chain_passed": ancestry_gate,
            "nonlinear_member_state_update_passed": nonlinear_state_gate,
            "deterministic_replay_exact": deterministic_gate,
            "in_memory_checkpoint_restart_exact": restart_gate,
            "persistent_checkpoint_roundtrip_and_restart_exact": (
                persistent_roundtrip_gate
            ),
            "persistent_checkpoint_ancestor_chain_roundtrip_and_restart_exact": (
                persistent_chain_gate
            ),
            "forced_failure_rollback_exact": rollback_gate,
            "fallback_count": sum(
                int(step.metrics["fallback_used"]) for step in first.steps
            ),
            "regularization_count": sum(
                int(step.metrics["regularization_used"]) for step in first.steps
            ),
        },
        "verification_hierarchy": {
            "level_1_analytic_and_manufactured": contract_pass,
            "level_2_external_code_to_code": False,
            "level_3_published_benchmark": False,
            "level_4_experimental": False,
            "level_5_customer_shadow": False,
        },
        "claims": {
            "bounded_two_member_stateful_fiber_frame2d": contract_pass,
            "fixed_initial_chord_coordinate_transformation": rotation["pass"],
            "two_member_dense_global_assembly": contract_pass,
            "consistent_global_material_tangent": tangent["pass"],
            "committed_checkpoint_parent_hash_and_epoch": ancestry_gate,
            "in_memory_checkpoint_restart": restart_gate,
            "persistent_checkpoint_roundtrip": persistent_roundtrip_gate,
            "persistent_checkpoint_ancestor_chain_bundle": persistent_chain_gate,
            "generalized_section_state_codec_registry": False,
            "general_frame_model_import": False,
            "geometric_nonlinearity": False,
            "shear_deformation_or_torsion": False,
            "mesh_objective_distributed_plasticity": False,
            "external_validation": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "generalized_section_state_codec_registry_not_connected",
            "general_frame_model_import_and_boundary_conditions_not_connected",
            "geometric_nonlinearity_not_coupled",
            "shear_deformation_and_torsion_not_implemented",
            "mesh_objective_distributed_plasticity_not_validated",
            "external_code_to_code_published_and_experimental_receipts_missing",
            "production_sparse_and_rocm_hip_paths_not_connected",
            "full_building_equilibrium_not_demonstrated",
            "g1_closure_not_claimed",
        ],
        "claim_boundary": STATEFUL_FIBER_FRAME2D_CLAIM_BOUNDARY,
    }


def build_stateful_fiber_frame2d_benchmark() -> dict[str, Any]:
    """Return the deterministic bounded two-member global-assembly receipt."""

    return deepcopy(_build_stateful_fiber_frame2d_benchmark_cached())


__all__ = [
    "STATEFUL_FIBER_FRAME2D_BENCHMARK_SCHEMA_VERSION",
    "STATEFUL_FIBER_FRAME2D_CLAIM_BOUNDARY",
    "build_stateful_fiber_frame2d_benchmark",
    "make_two_element_stateful_fiber_cantilever",
    "make_two_member_stateful_fiber_l_frame",
]
