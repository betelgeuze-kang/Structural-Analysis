"""Complete short vector arc-length path using Engine v2 CPU FGMRES tangents."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from structural_analysis.benchmark.arc_length_fgmres_bridge import (
    ARC_LENGTH_CPU_FGMRES_VECTOR_TANGENT_SOLVER_PROFILE,
    create_arc_length_cpu_fgmres_tangent_solver,
)
from structural_analysis.benchmark.coupled_shallow_arch_arc_length import (
    CoupledShallowArchArcLengthProblem,
)
from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE,
    VectorArcLengthConfig,
    vector_arc_length_continuation,
)


ARC_LENGTH_FGMRES_CONTINUATION_SCHEMA_VERSION = (
    "phase2-arc-length-cpu-fgmres-continuation.v1"
)
ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY = (
    "This receipt runs the complete accepted/trial/rollback vector arc-length "
    "loop to a negative-load branch on one analytic coupled two-DOF problem, "
    "using bound Engine v2 CPU FGMRES for every predictor and Schur-corrector "
    "tangent solve. It does not connect a frame/shell residual, cover a production "
    "model scale or sparse preconditioner, establish ROCm/HIP nonlinear parity, "
    "close full-load/full-mesh G1, or provide release-readiness evidence."
)
ARC_LENGTH_FGMRES_CONTINUATION_CONFIG = VectorArcLengthConfig(
    target_monitor_displacement_m=0.20,
    initial_arc_length_m=0.08,
    minimum_arc_length_m=0.02,
    maximum_arc_length_m=0.08,
    failed_step_reduction=0.5,
    maximum_corrector_iterations=5,
)


def _tangent_solve_metadata_rows(attempts: tuple[dict[str, Any], ...]):
    rows: list[dict[str, Any]] = []
    for attempt in attempts:
        predictor = attempt.get("predictor_tangent_solve")
        if predictor is not None:
            rows.append(predictor)
        for history_row in attempt.get("corrector_history", []):
            metadata = history_row.get("tangent_solve_metadata") or {}
            for key in (
                "residual_solve",
                "reference_load_solve",
                "load_linearization_solve",
            ):
                if metadata.get(key) is not None:
                    rows.append(metadata[key])
    return rows


@lru_cache(maxsize=1)
def _build_arc_length_cpu_fgmres_continuation_seed_cached() -> dict[str, Any]:
    """Build full short-path integration, rollback, restart, and replay evidence."""

    problem = CoupledShallowArchArcLengthProblem()
    config = ARC_LENGTH_FGMRES_CONTINUATION_CONFIG
    tangent_solver = create_arc_length_cpu_fgmres_tangent_solver()
    first = vector_arc_length_continuation(
        problem,
        config=config,
        tangent_solver=tangent_solver,
    )
    second = vector_arc_length_continuation(
        problem,
        config=config,
        tangent_solver=tangent_solver,
    )
    deterministic_replay_exact = first.to_dict() == second.to_dict()
    restart_checkpoint = first.checkpoints[len(first.checkpoints) // 2]
    restarted = vector_arc_length_continuation(
        problem,
        config=config,
        resume_from=restart_checkpoint,
        tangent_solver=tangent_solver,
    )
    checkpoint_restart_exact = restarted.final_checkpoint == first.final_checkpoint
    dense_reference = vector_arc_length_continuation(problem, config=config)

    same_checkpoint_count = len(first.checkpoints) == len(dense_reference.checkpoints)
    dense_displacement_max_error = max(
        abs(external_value - dense_value)
        for external_checkpoint, dense_checkpoint in zip(
            first.checkpoints,
            dense_reference.checkpoints,
        )
        for external_value, dense_value in zip(
            external_checkpoint.free_displacements_m,
            dense_checkpoint.free_displacements_m,
        )
    )
    dense_load_factor_max_error = max(
        abs(external.load_factor - dense.load_factor)
        for external, dense in zip(first.checkpoints, dense_reference.checkpoints)
    )
    dense_reference_gate_pass = bool(
        dense_reference.status == "ready"
        and same_checkpoint_count
        and dense_displacement_max_error <= 1.0e-12
        and dense_load_factor_max_error <= 1.0e-12
    )

    tangent_solve_rows = _tangent_solve_metadata_rows(first.attempts)
    tangent_solve_receipts = [row["receipt"] for row in tangent_solve_rows]
    all_tangent_solves_ready = bool(
        tangent_solve_rows
        and all(receipt["contract_pass"] is True for receipt in tangent_solve_receipts)
    )
    rejected_attempts = [
        row for row in first.attempts if row["accepted"] is False
    ]
    rollback_gate_pass = bool(
        rejected_attempts
        and all(
            row["rollback_exact"] is True
            and row["accepted_state_hash_before"]
            == row["accepted_state_hash_after"]
            for row in rejected_attempts
        )
    )
    coupling_errors = [
        abs(
            row.free_displacements_m[1]
            - problem.coupling_ratio * row.free_displacements_m[0]
        )
        for row in first.checkpoints
    ]
    reduced_equilibrium_errors = [
        abs(
            row.load_factor
            - problem.arch.internal_force_kn(row.free_displacements_m[0])
        )
        for row in first.checkpoints
    ]
    exact_reduction_gate_pass = bool(
        max(coupling_errors) <= 1.0e-12
        and max(reduced_equilibrium_errors) <= config.residual_tolerance_kn
    )
    first_limit_displacement, _first_limit_load = problem.arch.first_limit_point()
    limit_point_crossed = bool(
        first.checkpoints[0].free_displacements_m[0] < first_limit_displacement
        and first.final_checkpoint.free_displacements_m[0]
        > first_limit_displacement
        and first.metrics["descending_load_branch_observed"] is True
    )
    path_gate_pass = bool(
        first.status == "ready"
        and first.metrics["contract_pass"] is True
        and first.metrics["target_monitor_displacement_reached"] is True
        and first.metrics["negative_load_factor_observed"] is True
        and limit_point_crossed
        and first.metrics["fallback_count"] == 0
        and first.metrics["regularization_count"] == 0
    )
    external_integration_gate_pass = bool(
        first.metrics["tangent_linear_solver_profile"]
        == tangent_solver.profile
        and first.metrics["tangent_linear_solver_mode"]
        == VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE
        and first.metrics["external_tangent_solver_contract_hash"]
        == tangent_solver.contract_hash
        and first.metrics["external_tangent_solve_count"]
        == len(tangent_solve_rows)
        and all_tangent_solves_ready
    )
    contract_pass = bool(
        path_gate_pass
        and external_integration_gate_pass
        and rollback_gate_pass
        and checkpoint_restart_exact
        and deterministic_replay_exact
        and dense_reference_gate_pass
        and exact_reduction_gate_pass
    )
    return {
        "schema_version": ARC_LENGTH_FGMRES_CONTINUATION_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": "coupled_shallow_arch_full_cpu_fgmres_arc_length_loop",
        "analysis_type": "complete_short_path_arc_length_cpu_fgmres_integration",
        "tangent_solver_profile": (
            ARC_LENGTH_CPU_FGMRES_VECTOR_TANGENT_SOLVER_PROFILE
        ),
        "tangent_solver_mode": VECTOR_ARC_LENGTH_MATRIX_TANGENT_SOLVER_MODE,
        "tangent_solver_contract_hash": tangent_solver.contract_hash,
        "solver_result": first.to_dict(),
        "verification": {
            "path_gate_passed": path_gate_pass,
            "limit_point_crossed": limit_point_crossed,
            "negative_load_branch_reached": first.metrics[
                "negative_load_factor_observed"
            ],
            "external_tangent_integration_gate_passed": (
                external_integration_gate_pass
            ),
            "all_tangent_solves_ready": all_tangent_solves_ready,
            "rollback_evidence_passed": rollback_gate_pass,
            "checkpoint_restart_exact": checkpoint_restart_exact,
            "deterministic_replay_exact": deterministic_replay_exact,
            "dense_augmented_reference_gate_passed": dense_reference_gate_pass,
            "exact_scalar_reduction_gate_passed": exact_reduction_gate_pass,
            "same_dense_reference_checkpoint_count": same_checkpoint_count,
            "maximum_dense_reference_displacement_absolute_error_m": (
                dense_displacement_max_error
            ),
            "maximum_dense_reference_load_factor_absolute_error": (
                dense_load_factor_max_error
            ),
            "maximum_coupling_relation_absolute_error_m": max(coupling_errors),
            "maximum_reduced_equilibrium_absolute_error_kn": max(
                reduced_equilibrium_errors
            ),
            "tangent_solve_count": len(tangent_solve_rows),
            "maximum_tangent_solve_explicit_residual_inf_norm_kn": max(
                float(row["explicit_residual_inf_norm_kn"])
                for row in tangent_solve_rows
            ),
            "maximum_tangent_solve_iteration_count": max(
                receipt["solver"]["iteration_count"]
                for receipt in tangent_solve_receipts
            ),
            "tangent_solve_hashes": [
                receipt["solve_hash"] for receipt in tangent_solve_receipts
            ],
            "restart_checkpoint_state_hash": restart_checkpoint.state_hash,
            "final_checkpoint_state_hash": first.final_checkpoint.state_hash,
            "restarted_final_checkpoint_state_hash": (
                restarted.final_checkpoint.state_hash
            ),
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "claims": {
            "complete_short_path_cpu_fgmres_arc_length_integration": contract_pass,
            "engine_v2_cpu_fgmres_every_tangent_solve": (
                external_integration_gate_pass
            ),
            "failed_step_rollback": rollback_gate_pass,
            "checkpoint_restart": checkpoint_restart_exact,
            "dense_augmented_path_equivalence": dense_reference_gate_pass,
            "general_frame_shell_arc_length": False,
            "lee_frame_snapthrough": False,
            "production_scale_sparse_preconditioner": False,
            "production_rocm_hip_nonlinear_parity": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "frame_shell_consistent_residual_not_connected",
            "lee_frame_snapthrough_not_implemented",
            "production_scale_sparse_preconditioner_not_verified",
            "production_rocm_hip_nonlinear_parity_not_verified",
            "g1_full_load_full_mesh_not_closed",
        ],
        "claim_boundary": ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY,
    }


def build_arc_length_cpu_fgmres_continuation_seed() -> dict[str, Any]:
    """Return an isolated copy of the deterministic cached evidence payload."""

    return deepcopy(_build_arc_length_cpu_fgmres_continuation_seed_cached())


__all__ = [
    "ARC_LENGTH_FGMRES_CONTINUATION_CLAIM_BOUNDARY",
    "ARC_LENGTH_FGMRES_CONTINUATION_CONFIG",
    "ARC_LENGTH_FGMRES_CONTINUATION_SCHEMA_VERSION",
    "build_arc_length_cpu_fgmres_continuation_seed",
]
