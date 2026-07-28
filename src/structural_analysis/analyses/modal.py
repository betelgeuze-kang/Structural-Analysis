"""Authoritative small-dense whole-model modal analysis driver."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from math import isfinite
from numbers import Real
from typing import Any

import numpy as np

from structural_analysis.assembly.modal import (
    DOF_LABELS,
    DOF_PER_NODE,
    ModalAssembly,
    assemble_modal_matrices,
)
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.modal import ModalAnalysisError, solve_modal_modes
from structural_analysis.solvers.equation_scaling import (
    EQUATION_SCALING_6DOF_VERSION,
    EquationScaling6DOFError,
    characteristic_length_from_coordinates,
    frame3d_dof_labels,
    make_equation_scaling_6dof,
    reference_force_from_stiffness,
)


AUTHORITATIVE_CPU_MODAL_SOLVER_ID = "authoritative_cpu_modal_fea_3d_v1"
EIGEN_BACKEND = "scipy_linalg_eigh_dense"
MAX_DENSE_MODAL_FREE_DOF = 512
MODE_SHAPE_STORAGE_PROFILE = "inline_max_component_normalized_small_dense_v1"
MODAL_CLAIM_BOUNDARY = "dense_consistent_mass_frame_truss_modal_preview_v1"
TRANSLATION_DIRECTIONS = {"UX": 0, "UY": 1, "UZ": 2}


@dataclass(frozen=True)
class WholeModelModalSolution:
    status: str
    metrics: dict[str, Any]
    convergence_history: list[dict[str, Any]]
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_authoritative_modal(
    model: CanonicalModel,
    *,
    tolerance: float,
    mode_count: int,
    eigen_backend: str = EIGEN_BACKEND,
) -> WholeModelModalSolution:
    """Run the bounded whole-model modal path without fallback or regularization."""

    unsupported = _public_preflight(
        model,
        tolerance=tolerance,
        mode_count=mode_count,
        eigen_backend=eigen_backend,
    )
    if unsupported:
        return _blocked_solution(
            model,
            unsupported=unsupported,
            eigen_backend=eigen_backend,
        )

    assembly, assembly_unsupported = assemble_modal_matrices(model)
    if assembly is None:
        return _blocked_solution(
            model,
            unsupported=assembly_unsupported,
            eigen_backend=eigen_backend,
        )
    if len(assembly.free_dofs) > MAX_DENSE_MODAL_FREE_DOF:
        return _blocked_solution(
            model,
            unsupported=[
                {
                    "kind": "modal_dense_free_dof_limit_exceeded",
                    "free_dof_count": len(assembly.free_dofs),
                    "maximum_free_dof_count": MAX_DENSE_MODAL_FREE_DOF,
                    "detail": (
                        "Sparse modal extraction and binary mode-vector artifacts "
                        "are not connected to the public whole-model path."
                    ),
                }
            ],
            eigen_backend=eigen_backend,
            assembly=assembly,
        )

    free = np.asarray(assembly.free_dofs, dtype=np.int64)
    reduced_stiffness = assembly.stiffness[np.ix_(free, free)]
    reduced_mass = assembly.mass[np.ix_(free, free)]
    try:
        characteristic_length = characteristic_length_from_coordinates(
            assembly.node_coordinates
        )
        free_dof_labels = frame3d_dof_labels(
            tuple(int(index) for index in assembly.free_dofs)
        )
        reference_force = reference_force_from_stiffness(
            reduced_stiffness,
            characteristic_length=characteristic_length,
            dof_labels=free_dof_labels,
        )
        equation_scaling = make_equation_scaling_6dof(
            reference_force=reference_force,
            characteristic_length=characteristic_length,
            dof_labels=free_dof_labels,
        )
        modal = solve_modal_modes(
            reduced_stiffness,
            reduced_mass,
            mode_count=mode_count,
            positive_semidefinite_relative_tolerance=1.0e-10,
            rigid_mode_relative_tolerance=1.0e-10,
            cluster_relative_tolerance=1.0e-9,
            residual_relative_tolerance=tolerance,
            orthogonality_tolerance=tolerance,
            equation_scaling=equation_scaling,
        )
    except (EquationScaling6DOFError, ModalAnalysisError) as exc:
        return _blocked_solution(
            model,
            unsupported=[
                {
                    "kind": "modal_generalized_eigen_contract_failed",
                    "detail": str(exc),
                    "regularization_used": False,
                    "fallback_used": False,
                }
            ],
            eigen_backend=eigen_backend,
            assembly=assembly,
        )

    modes, total_directional_mass = _mode_rows(
        assembly,
        modal=modal,
        reduced_mass=reduced_mass,
    )
    convergence_history = [
        {
            "step": "modal_mode",
            "iteration": mode.mode_number,
            "residual_norm": mode.residual_relative_inf,
            "raw_residual_relative_norm": mode.raw_residual_relative_inf,
            "dimensionless_scaled_residual_norm": (
                mode.scaled_residual_relative_inf
            ),
            "raw_translational_residual_norm": (
                mode.raw_translational_residual_norm
            ),
            "raw_rotational_residual_norm": (
                mode.raw_rotational_residual_norm
            ),
            "relative_increment": None,
            "relative_increment_applicable": False,
            "status": "ready",
        }
        for mode in modal.modes
    ]
    metrics: dict[str, Any] = {
        "node_count": len(model.nodes),
        "element_count": len(model.elements),
        "load_count": len(model.loads),
        "support_count": len(model.supports),
        "solver_path_id": AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
        "analysis_fidelity": "cpu_reference_dense_whole_model_modal",
        "production_fail_closed": True,
        "implicit_property_fallback_used": False,
        "automatic_support_generation_used": False,
        "regularization_used": False,
        "fallback_used": False,
        "matrix_backend": eigen_backend,
        "sparse_backend_used": False,
        "stiffness_storage": "dense_numpy_binary64",
        "mass_storage": "dense_numpy_binary64",
        "equation_scaling": {
            "status": "available",
            "value": {
                "schema_version": EQUATION_SCALING_6DOF_VERSION,
                "solve_applied": modal.equation_scaling_applied,
                "reference_force": modal.reference_force,
                "reference_force_basis": (
                    "absolute_stiffness_action_for_unit_scaled_coordinates"
                ),
                "characteristic_length": modal.characteristic_length,
                "scaling_hash": modal.equation_scaling_hash,
                "scaled_stiffness_condition_number": _condition_evidence(
                    modal.scaled_stiffness_condition_number,
                    reason=(
                        "scaled_stiffness_is_singular_or_condition_is_nonfinite"
                    ),
                ),
                "scaled_mass_condition_number": _condition_evidence(
                    modal.scaled_mass_condition_number,
                    reason="scaled_mass_condition_is_nonfinite",
                ),
            },
        },
        "mass_matrix_unit": assembly.mass_matrix_unit,
        "material_density_unit": assembly.density_unit,
        "mass_formulation": assembly.mass_formulation,
        "total_physical_mass_kg": assembly.total_physical_mass_kg,
        "directional_free_mass_kg": total_directional_mass,
        "total_dof_count": int(assembly.stiffness.shape[0]),
        "active_dof_count": len(assembly.active_dofs),
        "free_dof_count": len(assembly.free_dofs),
        "constrained_dof_count": len(assembly.constrained_dofs),
        "inactive_dof_count": int(
            assembly.stiffness.shape[0] - len(assembly.active_dofs)
        ),
        "free_dof_map": _free_dof_rows(assembly),
        "free_dof_map_hash": _hash_json(_free_dof_rows(assembly)),
        "requested_mode_count": modal.requested_mode_count,
        "mode_count": modal.mode_count,
        "rigid_mode_count": modal.rigid_mode_count,
        "modes": modes,
        "mass_orthogonality_error_inf": modal.mass_orthogonality_error_inf,
        "stiffness_diagonalization_error_inf": (
            modal.stiffness_diagonalization_error_inf
        ),
        "stiffness_relative_symmetry_error": (
            modal.stiffness_relative_symmetry_error
        ),
        "mass_relative_symmetry_error": modal.mass_relative_symmetry_error,
        "stiffness_matrix_hash": modal.stiffness_matrix_hash,
        "mass_matrix_hash": modal.mass_matrix_hash,
        "raw_result_hash": modal.raw_result_hash,
        "semantic_result_hash": modal.semantic_result_hash,
        "semantic_hash_profile": modal.semantic_hash_profile,
        "deterministic_mode_basis": modal.deterministic_mode_basis,
        "symmetry_projection_applied": modal.symmetry_projection_applied,
        "mode_shape_storage_profile": MODE_SHAPE_STORAGE_PROFILE,
        "mass_normalized_mode_vectors_inlined": False,
        "binary_mode_vector_artifact_connected": False,
        "whole_model_frame_truss_modal_workflow": True,
        "general_frame_shell_modal_workflow": False,
        "nodal_lumped_mass_supported": False,
        "sparse_modal_backend_connected": False,
        "rocm_hip_modal_parity": False,
        "verification_level_2": False,
        "release_readiness": False,
        "claim_boundary": MODAL_CLAIM_BOUNDARY,
    }
    return WholeModelModalSolution(
        status="ready",
        metrics=metrics,
        convergence_history=convergence_history,
        warnings=list(assembly.warnings),
    )


def _mode_rows(
    assembly: ModalAssembly,
    *,
    modal: Any,
    reduced_mass: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    total_dofs = int(assembly.stiffness.shape[0])
    free = np.asarray(assembly.free_dofs, dtype=np.int64)
    influence_vectors: dict[str, np.ndarray] = {}
    total_mass_coefficients: dict[str, float] = {}
    for label, offset in TRANSLATION_DIRECTIONS.items():
        full = np.zeros(total_dofs, dtype=np.float64)
        full[offset::DOF_PER_NODE] = 1.0
        reduced = full[free]
        influence_vectors[label] = reduced
        total_mass_coefficients[label] = float(reduced @ reduced_mass @ reduced)

    cumulative = {label: 0.0 for label in TRANSLATION_DIRECTIONS}
    rows: list[dict[str, Any]] = []
    for mode in modal.modes:
        vector = np.asarray(mode.mass_normalized_shape, dtype=np.float64)
        max_vector = np.asarray(
            mode.max_component_normalized_shape,
            dtype=np.float64,
        )
        full_max = np.zeros(total_dofs, dtype=np.float64)
        full_max[free] = max_vector
        participation: dict[str, dict[str, Any]] = {}
        for label, influence in influence_vectors.items():
            generalized_mass = float(vector @ reduced_mass @ vector)
            numerator = float(vector @ reduced_mass @ influence)
            factor = numerator / generalized_mass
            effective_coefficient = numerator * numerator / generalized_mass
            total_coefficient = total_mass_coefficients[label]
            ratio = (
                effective_coefficient / total_coefficient
                if total_coefficient > np.finfo(np.float64).tiny
                else 0.0
            )
            cumulative[label] += ratio
            participation[label] = {
                "applicable": bool(
                    total_coefficient > np.finfo(np.float64).tiny
                ),
                "participation_factor": factor,
                "effective_modal_mass_kg": effective_coefficient * 1000.0,
                "effective_modal_mass_ratio": ratio,
                "cumulative_effective_modal_mass_ratio": cumulative[label],
            }
        rows.append(
            {
                "mode_number": mode.mode_number,
                "eigenvalue_rad2_per_s2": mode.eigenvalue_rad2_per_s2,
                "omega_rad_per_s": mode.omega_rad_per_s,
                "frequency_hz": mode.frequency_hz,
                "period_s": mode.period_s,
                "generalized_mass": mode.generalized_mass,
                "generalized_stiffness": mode.generalized_stiffness,
                "residual_relative_inf": mode.residual_relative_inf,
                "raw_residual_relative_inf": (
                    mode.raw_residual_relative_inf
                ),
                "raw_translational_residual_norm": (
                    mode.raw_translational_residual_norm
                ),
                "raw_rotational_residual_norm": (
                    mode.raw_rotational_residual_norm
                ),
                "scaled_residual_relative_inf": (
                    mode.scaled_residual_relative_inf
                ),
                "reduced_mass_normalized_shape_sha256": _vector_hash(vector),
                "max_component_normalized_node_shapes": _node_shape_rows(
                    assembly,
                    full_max,
                ),
                "directional_participation": participation,
            }
        )
    return (
        rows,
        {
            label: coefficient * 1000.0
            for label, coefficient in total_mass_coefficients.items()
        },
    )


def _condition_evidence(
    value: float | None,
    *,
    reason: str,
) -> dict[str, Any]:
    if value is None:
        return {"status": "unavailable", "reason": reason}
    return {"status": "available", "value": value}


def _node_shape_rows(
    assembly: ModalAssembly,
    vector: np.ndarray,
) -> list[dict[str, Any]]:
    return [
        {
            "node_id": node_id,
            "components": {
                label: float(vector[node_index * DOF_PER_NODE + offset])
                for offset, label in enumerate(DOF_LABELS)
            },
        }
        for node_index, node_id in enumerate(assembly.node_ids)
    ]


def _free_dof_rows(assembly: ModalAssembly) -> list[dict[str, Any]]:
    return [
        {
            "reduced_index": reduced_index,
            "global_index": global_index,
            "node_id": assembly.node_ids[global_index // DOF_PER_NODE],
            "dof": DOF_LABELS[global_index % DOF_PER_NODE],
        }
        for reduced_index, global_index in enumerate(assembly.free_dofs)
    ]


def _public_preflight(
    model: CanonicalModel,
    *,
    tolerance: float,
    mode_count: int,
    eigen_backend: str,
) -> list[dict[str, Any]]:
    unsupported: list[dict[str, Any]] = []
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, Real)
        or not isfinite(float(tolerance))
        or float(tolerance) <= 0.0
    ):
        unsupported.append(
            {
                "kind": "modal_tolerance_invalid",
                "tolerance": tolerance,
                "detail": "Modal tolerance must be finite and positive.",
            }
        )
    if isinstance(mode_count, bool) or not isinstance(mode_count, int) or mode_count <= 0:
        unsupported.append(
            {
                "kind": "modal_mode_count_invalid",
                "mode_count": mode_count,
                "detail": "mode_count must be a positive integer.",
            }
        )
    if eigen_backend != EIGEN_BACKEND:
        unsupported.append(
            {
                "kind": "modal_eigen_backend_not_supported",
                "eigen_backend": eigen_backend,
                "supported_backend": EIGEN_BACKEND,
            }
        )
    axis_order = tuple(
        str(axis).strip().upper() for axis in model.coordinate_system.axis_order
    )
    up_axis = str(model.coordinate_system.up_axis).strip().upper()
    if axis_order != ("X", "Y", "Z") or up_axis != "Z":
        unsupported.append(
            {
                "kind": "modal_coordinate_system_not_supported",
                "axis_order": list(axis_order),
                "up_axis": up_axis,
                "detail": "Modal v1 requires canonical global XYZ coordinates with Z-up.",
            }
        )
    return unsupported


def _blocked_solution(
    model: CanonicalModel,
    *,
    unsupported: list[dict[str, Any]],
    eigen_backend: str,
    assembly: ModalAssembly | None = None,
) -> WholeModelModalSolution:
    return WholeModelModalSolution(
        status="blocked",
        metrics={
            "node_count": len(model.nodes),
            "element_count": len(model.elements),
            "load_count": len(model.loads),
            "support_count": len(model.supports),
            "solver_path_id": AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
            "analysis_fidelity": "cpu_reference_dense_whole_model_modal",
            "production_fail_closed": True,
            "implicit_property_fallback_used": False,
            "automatic_support_generation_used": False,
            "regularization_used": False,
            "fallback_used": False,
            "matrix_backend": eigen_backend,
            "sparse_backend_used": False,
            "free_dof_count": len(assembly.free_dofs) if assembly else 0,
            "active_dof_count": len(assembly.active_dofs) if assembly else 0,
            "whole_model_frame_truss_modal_workflow": False,
            "general_frame_shell_modal_workflow": False,
            "nodal_lumped_mass_supported": False,
            "sparse_modal_backend_connected": False,
            "rocm_hip_modal_parity": False,
            "verification_level_2": False,
            "release_readiness": False,
            "claim_boundary": MODAL_CLAIM_BOUNDARY,
        },
        convergence_history=[],
        unsupported_features=unsupported,
        warnings=list(assembly.warnings) if assembly else [],
    )


def _vector_hash(vector: np.ndarray) -> str:
    canonical = np.ascontiguousarray(np.asarray(vector, dtype="<f8"))
    return "sha256:" + hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
