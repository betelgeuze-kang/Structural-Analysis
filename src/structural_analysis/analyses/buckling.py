"""Bounded public whole-model linear-buckling analysis for 3D frames."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from math import isfinite
from numbers import Real
from typing import Any
import json

import numpy as np
from scipy.sparse import csr_matrix

from structural_analysis.analyses.linear_static import (
    AUTHORITATIVE_CPU_SOLVER_ID,
    run_authoritative_linear_static,
)
from structural_analysis.assembly.buckling import (
    BucklingAssembly,
    SUPPORTED_BUCKLING_ELEMENT_TYPES,
    assemble_linear_buckling_matrices,
    reference_load_vector_hash_payload,
)
from structural_analysis.assembly.linear_static import DOF_LABELS, DOF_PER_NODE
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.buckling import (
    BucklingAnalysisError,
    solve_linear_buckling,
)
from structural_analysis.solvers.sparse_generalized_eigen import (
    SPARSE_BUCKLING_PROFILE,
    SPARSE_EIGEN_CLAIM_BOUNDARY,
    SparseGeneralizedEigenError,
    solve_sparse_linear_buckling,
)


AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID = (
    "authoritative_cpu_linear_buckling_fea_3d_v1"
)
BUCKLING_EIGEN_BACKEND = "scipy_linalg_eigh_dense"
SPARSE_BUCKLING_EIGEN_BACKEND = SPARSE_BUCKLING_PROFILE
MAX_DENSE_BUCKLING_FREE_DOF = 512
MAX_SPARSE_BUCKLING_FREE_DOF = 4096
BUCKLING_MODE_SHAPE_STORAGE_PROFILE = (
    "inline_max_component_normalized_small_dense_v1"
)
BUCKLING_CLAIM_BOUNDARY = "dense_reference_state_frame_linear_buckling_preview_v1"
SPARSE_BUCKLING_CLAIM_BOUNDARY = (
    "dense_assembly_sparse_low_mode_frame_linear_buckling_experimental_v1"
)
SUPPORTED_REFERENCE_LOAD_KINDS = {
    "nodal",
    "node",
    "nodal_load",
    "point",
    "point_load",
}


@dataclass(frozen=True)
class WholeModelBucklingSolution:
    status: str
    metrics: dict[str, Any]
    convergence_history: list[dict[str, Any]]
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_authoritative_linear_buckling(
    model: CanonicalModel,
    *,
    tolerance: float,
    mode_count: int,
    eigen_backend: str = BUCKLING_EIGEN_BACKEND,
    load_case: str | None = None,
) -> WholeModelBucklingSolution:
    """Run reference-static plus initial-stress buckling without fallback."""

    normalized_load_case = (
        load_case.strip() if isinstance(load_case, str) else load_case
    )
    normalized_load_case = normalized_load_case or None
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

    reference = run_authoritative_linear_static(
        model,
        tolerance=float(tolerance),
        matrix_backend="numpy_linalg_solve_dense",
        load_case=normalized_load_case,
    )
    if reference.status != "ready" or reference.unsupported_features:
        return _blocked_solution(
            model,
            unsupported=[
                {
                    "kind": "buckling_reference_static_state_failed",
                    "reference_status": reference.status,
                    "reference_diagnostics": reference.unsupported_features,
                    "detail": (
                        "Linear buckling requires a ready authoritative dense "
                        "linear-static reference state at load factor 1.0."
                    ),
                }
            ],
            eigen_backend=eigen_backend,
            reference_status=reference.status,
        )
    member_forces = reference.metrics.get("member_forces")
    if not isinstance(member_forces, list):
        return _blocked_solution(
            model,
            unsupported=[{"kind": "buckling_reference_member_forces_missing"}],
            eigen_backend=eigen_backend,
            reference_status=reference.status,
        )

    assembly, assembly_unsupported = assemble_linear_buckling_matrices(
        model,
        reference_member_forces=member_forces,
        load_case=normalized_load_case,
    )
    if assembly is None:
        return _blocked_solution(
            model,
            unsupported=assembly_unsupported,
            eigen_backend=eigen_backend,
            reference_status=reference.status,
        )
    sparse_selected = eigen_backend == SPARSE_BUCKLING_EIGEN_BACKEND
    maximum_free_dof_count = (
        MAX_SPARSE_BUCKLING_FREE_DOF
        if sparse_selected
        else MAX_DENSE_BUCKLING_FREE_DOF
    )
    if len(assembly.free_dofs) > maximum_free_dof_count:
        return _blocked_solution(
            model,
            unsupported=[
                {
                    "kind": (
                        "buckling_sparse_extraction_free_dof_limit_exceeded"
                        if sparse_selected
                        else "buckling_dense_free_dof_limit_exceeded"
                    ),
                    "free_dof_count": len(assembly.free_dofs),
                    "maximum_free_dof_count": maximum_free_dof_count,
                    "detail": (
                        "Sparse extraction still receives matrices from bounded "
                        "dense whole-model assembly; binary mode artifacts and "
                        "native sparse assembly remain unconnected."
                        if sparse_selected
                        else "Select the explicit experimental sparse extraction "
                        "backend for larger bounded systems; native sparse assembly "
                        "and binary mode artifacts remain unconnected."
                    ),
                }
            ],
            eigen_backend=eigen_backend,
            reference_status=reference.status,
            assembly=assembly,
        )

    free = np.asarray(assembly.free_dofs, dtype=np.int64)
    reduced_stiffness = assembly.stiffness[np.ix_(free, free)]
    reduced_geometric = assembly.geometric_stiffness[np.ix_(free, free)]
    buckling: Any
    try:
        if sparse_selected:
            buckling = solve_sparse_linear_buckling(
                csr_matrix(reduced_stiffness),
                csr_matrix(reduced_geometric),
                mode_count=mode_count,
                positive_semidefinite_relative_tolerance=1.0e-10,
                finite_mode_relative_tolerance=1.0e-12,
                cluster_relative_tolerance=1.0e-9,
                residual_relative_tolerance=tolerance,
                orthogonality_tolerance=tolerance,
            )
        else:
            buckling = solve_linear_buckling(
                reduced_stiffness,
                reduced_geometric,
                mode_count=mode_count,
                positive_semidefinite_relative_tolerance=1.0e-10,
                finite_mode_relative_tolerance=1.0e-12,
                cluster_relative_tolerance=1.0e-9,
                residual_relative_tolerance=tolerance,
                orthogonality_tolerance=tolerance,
            )
    except (BucklingAnalysisError, SparseGeneralizedEigenError) as exc:
        return _blocked_solution(
            model,
            unsupported=[
                {
                    "kind": "buckling_generalized_eigen_contract_failed",
                    "detail": str(exc),
                    "regularization_used": False,
                    "fallback_used": False,
                }
            ],
            eigen_backend=eigen_backend,
            reference_status=reference.status,
            assembly=assembly,
        )

    modes = _mode_rows(assembly, buckling=buckling)
    free_dof_rows = _free_dof_rows(assembly)
    load_hash_payload = reference_load_vector_hash_payload(reference.metrics)
    compression_rows = [
        {
            "element_id": row.element_id,
            "node_ids": list(row.node_ids),
            "reference_compression_force_kn": row.reference_compression_force_kn,
            "reference_axial_equilibrium_error_kn": (
                row.reference_axial_equilibrium_error_kn
            ),
        }
        for row in assembly.element_records
    ]
    convergence_history = [
        {
            "step": "linear_buckling_mode",
            "iteration": mode.mode_number,
            "residual_norm": mode.residual_relative_inf,
            "relative_increment": 0.0,
            "status": "ready",
        }
        for mode in buckling.modes
    ]
    metrics: dict[str, Any] = {
        "node_count": len(model.nodes),
        "element_count": len(model.elements),
        "load_count": len(model.loads),
        "support_count": len(model.supports),
        "solver_path_id": AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
        "analysis_fidelity": (
            "cpu_experimental_sparse_extraction_whole_model_linear_buckling"
            if sparse_selected
            else "cpu_reference_dense_whole_model_linear_buckling"
        ),
        "production_fail_closed": True,
        "implicit_property_fallback_used": False,
        "automatic_support_generation_used": False,
        "regularization_used": False,
        "fallback_used": False,
        "matrix_backend": eigen_backend,
        "sparse_backend_used": sparse_selected,
        "stiffness_storage": (
            "scipy_csr_binary64_reduced_from_dense_assembly"
            if sparse_selected
            else "dense_numpy_binary64"
        ),
        "geometric_stiffness_storage": (
            "scipy_csr_binary64_reduced_from_dense_assembly"
            if sparse_selected
            else "dense_numpy_binary64"
        ),
        "whole_model_assembly_storage": "dense_numpy_binary64",
        "native_sparse_assembly_used": False,
        "sparse_eigen_extraction_used": sparse_selected,
        "geometric_stiffness_formulation": (
            assembly.geometric_stiffness_formulation
        ),
        "geometric_stiffness_sign_convention": (
            assembly.geometric_stiffness_sign_convention
        ),
        "stability_equation": "K_phi_equals_lambda_Kg_phi",
        "reference_static_solver_id": AUTHORITATIVE_CPU_SOLVER_ID,
        "reference_static_status": reference.status,
        "reference_load_case": normalized_load_case,
        "reference_load_factor": 1.0,
        "reference_load_pattern_hash": _hash_json(load_hash_payload),
        "reference_static_residual_norm": reference.metrics["residual_norm"],
        "reference_static_relative_residual": reference.metrics["relative_residual"],
        "reference_static_max_displacement": reference.metrics["max_displacement"],
        "reference_member_compression_forces": compression_rows,
        "reference_compression_scale_kn": assembly.reference_compression_scale_kn,
        "total_dof_count": int(assembly.stiffness.shape[0]),
        "active_dof_count": len(assembly.active_dofs),
        "free_dof_count": len(assembly.free_dofs),
        "constrained_dof_count": len(assembly.constrained_dofs),
        "inactive_dof_count": int(
            assembly.stiffness.shape[0] - len(assembly.active_dofs)
        ),
        "free_dof_map": free_dof_rows,
        "free_dof_map_hash": _hash_json(free_dof_rows),
        "requested_mode_count": buckling.requested_mode_count,
        "mode_count": buckling.mode_count,
        "candidate_eigenpair_count": getattr(
            buckling,
            "candidate_eigenpair_count",
            buckling.mode_count,
        ),
        "eigen_backend_profile": getattr(
            buckling,
            "backend_profile",
            BUCKLING_EIGEN_BACKEND,
        ),
        "finite_positive_eigenvalue_count": getattr(
            buckling,
            "finite_positive_eigenvalue_count",
            None,
        ),
        "finite_positive_eigenvalue_count_lower_bound": getattr(
            buckling,
            "finite_positive_eigenvalue_count_lower_bound",
            getattr(buckling, "finite_positive_eigenvalue_count", 0),
        ),
        "finite_positive_eigenvalue_count_exact": not sparse_selected,
        "critical_load_factor": buckling.critical_load_factor,
        "modes": modes,
        "stiffness_orthogonality_error_inf": (
            buckling.stiffness_orthogonality_error_inf
        ),
        "geometric_diagonalization_error_inf": (
            buckling.geometric_diagonalization_error_inf
        ),
        "stiffness_relative_symmetry_error": (
            buckling.stiffness_relative_symmetry_error
        ),
        "geometric_stiffness_relative_symmetry_error": (
            buckling.geometric_stiffness_relative_symmetry_error
        ),
        "geometric_stiffness_positive_rank": getattr(
            buckling,
            "geometric_stiffness_positive_rank",
            None,
        ),
        "geometric_stiffness_positive_rank_lower_bound": getattr(
            buckling,
            "geometric_stiffness_positive_rank_lower_bound",
            getattr(buckling, "geometric_stiffness_positive_rank", 0),
        ),
        "geometric_stiffness_positive_rank_exact": not sparse_selected,
        "stiffness_matrix_hash": buckling.stiffness_matrix_hash,
        "geometric_stiffness_matrix_hash": (
            buckling.geometric_stiffness_matrix_hash
        ),
        "raw_result_hash": buckling.raw_result_hash,
        "semantic_result_hash": buckling.semantic_result_hash,
        "semantic_hash_profile": buckling.semantic_hash_profile,
        "deterministic_mode_basis": buckling.deterministic_mode_basis,
        "symmetry_projection_applied": buckling.symmetry_projection_applied,
        "mode_shape_storage_profile": BUCKLING_MODE_SHAPE_STORAGE_PROFILE,
        "stiffness_normalized_mode_vectors_inlined": False,
        "binary_mode_vector_artifact_connected": False,
        "whole_model_frame_linear_buckling_workflow": True,
        "general_frame_shell_linear_buckling_workflow": False,
        "mixed_tension_compression_reference_supported": False,
        "nonlinear_buckling_supported": False,
        "imperfection_sensitivity_supported": False,
        "sparse_buckling_backend_connected": sparse_selected,
        "rocm_hip_buckling_parity": False,
        "verification_level_2": False,
        "release_readiness": False,
        "eigen_solver_claim_boundary": (
            SPARSE_EIGEN_CLAIM_BOUNDARY
            if sparse_selected
            else BUCKLING_CLAIM_BOUNDARY
        ),
        "claim_boundary": (
            SPARSE_BUCKLING_CLAIM_BOUNDARY
            if sparse_selected
            else BUCKLING_CLAIM_BOUNDARY
        ),
    }
    return WholeModelBucklingSolution(
        status="ready",
        metrics=metrics,
        convergence_history=convergence_history,
        warnings=[*reference.warnings, *assembly.warnings],
    )


def _mode_rows(assembly: BucklingAssembly, *, buckling: Any) -> list[dict[str, Any]]:
    total_dofs = int(assembly.stiffness.shape[0])
    free = np.asarray(assembly.free_dofs, dtype=np.int64)
    rows: list[dict[str, Any]] = []
    for mode in buckling.modes:
        reduced_stiffness_normalized = np.asarray(
            mode.stiffness_normalized_shape,
            dtype=np.float64,
        )
        reduced_max = np.asarray(
            mode.max_component_normalized_shape,
            dtype=np.float64,
        )
        full_max = np.zeros(total_dofs, dtype=np.float64)
        full_max[free] = reduced_max
        rows.append(
            {
                "mode_number": mode.mode_number,
                "load_factor": mode.load_factor,
                "generalized_elastic_stiffness": (
                    mode.generalized_elastic_stiffness
                ),
                "generalized_geometric_stiffness": (
                    mode.generalized_geometric_stiffness
                ),
                "residual_relative_inf": mode.residual_relative_inf,
                "reduced_stiffness_normalized_shape_sha256": _vector_hash(
                    reduced_stiffness_normalized
                ),
                "max_component_normalized_node_shapes": _node_shape_rows(
                    assembly,
                    full_max,
                ),
            }
        )
    return rows


def _node_shape_rows(
    assembly: BucklingAssembly,
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


def _free_dof_rows(assembly: BucklingAssembly) -> list[dict[str, Any]]:
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
                "kind": "buckling_tolerance_invalid",
                "tolerance": tolerance,
                "detail": "Buckling tolerance must be finite and positive.",
            }
        )
    if isinstance(mode_count, bool) or not isinstance(mode_count, int) or mode_count <= 0:
        unsupported.append(
            {
                "kind": "buckling_mode_count_invalid",
                "mode_count": mode_count,
                "detail": "mode_count must be a positive integer.",
            }
        )
    supported_backends = (
        BUCKLING_EIGEN_BACKEND,
        SPARSE_BUCKLING_EIGEN_BACKEND,
    )
    if eigen_backend not in supported_backends:
        unsupported.append(
            {
                "kind": "buckling_eigen_backend_not_supported",
                "eigen_backend": eigen_backend,
                "supported_backends": list(supported_backends),
            }
        )
    for element in model.elements:
        element_type = str(element.get("type", "")).strip().lower()
        if element_type not in SUPPORTED_BUCKLING_ELEMENT_TYPES:
            unsupported.append(
                {
                    "kind": "buckling_element_not_supported",
                    "element": str(element.get("id", "")),
                    "element_type": element.get("type", ""),
                    "detail": (
                        "Whole-model linear buckling v1 supports frame/beam/"
                        "column initial-stress assembly only."
                    ),
                }
            )
    for index, load in enumerate(model.loads):
        raw_kind = load.get("kind", load.get("type"))
        if raw_kind is None:
            continue
        kind = str(raw_kind).strip().lower()
        if kind not in SUPPORTED_REFERENCE_LOAD_KINDS:
            unsupported.append(
                {
                    "kind": "buckling_reference_load_type_not_supported",
                    "load_index": index,
                    "load_type": raw_kind,
                    "detail": (
                        "Linear buckling v1 accepts explicit nodal reference loads "
                        "only; distributed, thermal, settlement, and follower loads "
                        "are not silently converted."
                    ),
                }
            )
    return unsupported


def _blocked_solution(
    model: CanonicalModel,
    *,
    unsupported: list[dict[str, Any]],
    eigen_backend: str,
    reference_status: str = "not_run",
    assembly: BucklingAssembly | None = None,
) -> WholeModelBucklingSolution:
    sparse_selected = eigen_backend == SPARSE_BUCKLING_EIGEN_BACKEND
    return WholeModelBucklingSolution(
        status="blocked",
        metrics={
            "node_count": len(model.nodes),
            "element_count": len(model.elements),
            "load_count": len(model.loads),
            "support_count": len(model.supports),
            "solver_path_id": AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
            "analysis_fidelity": (
                "cpu_experimental_sparse_extraction_whole_model_linear_buckling"
                if sparse_selected
                else "cpu_reference_dense_whole_model_linear_buckling"
            ),
            "production_fail_closed": True,
            "implicit_property_fallback_used": False,
            "automatic_support_generation_used": False,
            "regularization_used": False,
            "fallback_used": False,
            "matrix_backend": eigen_backend,
            "sparse_backend_used": sparse_selected,
            "whole_model_assembly_storage": "dense_numpy_binary64",
            "native_sparse_assembly_used": False,
            "sparse_eigen_extraction_used": sparse_selected,
            "reference_static_status": reference_status,
            "reference_load_factor": 1.0,
            "free_dof_count": len(assembly.free_dofs) if assembly else 0,
            "active_dof_count": len(assembly.active_dofs) if assembly else 0,
            "whole_model_frame_linear_buckling_workflow": False,
            "general_frame_shell_linear_buckling_workflow": False,
            "mixed_tension_compression_reference_supported": False,
            "nonlinear_buckling_supported": False,
            "imperfection_sensitivity_supported": False,
            "sparse_buckling_backend_connected": sparse_selected,
            "rocm_hip_buckling_parity": False,
            "verification_level_2": False,
            "release_readiness": False,
            "claim_boundary": (
                SPARSE_BUCKLING_CLAIM_BOUNDARY
                if sparse_selected
                else BUCKLING_CLAIM_BOUNDARY
            ),
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
