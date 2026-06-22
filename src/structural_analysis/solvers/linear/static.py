"""Narrow deterministic linear-static solver for axial canonical models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import warnings as warnings_module

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from structural_analysis.assembly.linear_static import (
    DOF_LABELS,
    SPARSE_STIFFNESS_STORAGE,
    STIFFNESS_STORAGE,
    LinearStaticAssembly,
    assemble_linear_static,
    assemble_linear_static_sparse,
)
from structural_analysis.model.schema import CanonicalModel

MATRIX_BACKEND = "numpy_linalg_solve_dense"
SPARSE_MATRIX_BACKEND = "scipy_sparse_spsolve_cpu"
SPARSE_BACKEND_USED = False
RESIDUAL_FORMULA = "F_internal_minus_F_external"


def linear_static_residual(
    assembly: LinearStaticAssembly,
    displacements: np.ndarray,
) -> np.ndarray:
    """Residual R(u)=F_internal(u)-F_external for the narrow linear-static slice."""
    return assembly.stiffness @ displacements - assembly.loads


def linear_static_tangent_jacobian(assembly: LinearStaticAssembly) -> np.ndarray | csr_matrix:
    """Consistent tangent dR/du equals assembled global stiffness for linear elasticity."""
    return assembly.stiffness


@dataclass(frozen=True)
class LinearStaticSolution:
    status: str
    metrics: dict[str, Any]
    convergence_history: list[dict[str, Any]]
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def solve_linear_static(model: CanonicalModel, *, tolerance: float) -> LinearStaticSolution:
    assembly, unsupported = assemble_linear_static(model)
    if assembly is None:
        return _blocked(unsupported, model)
    return _solve_linear_static(
        assembly,
        model,
        tolerance=tolerance,
        matrix_backend=MATRIX_BACKEND,
        sparse_backend_used=SPARSE_BACKEND_USED,
    )


def solve_linear_static_sparse(model: CanonicalModel, *, tolerance: float) -> LinearStaticSolution:
    assembly, unsupported = assemble_linear_static_sparse(model)
    if assembly is None:
        return _blocked_sparse(unsupported, model)
    return _solve_linear_static(
        assembly,
        model,
        tolerance=tolerance,
        matrix_backend=SPARSE_MATRIX_BACKEND,
        sparse_backend_used=True,
    )


def _stiffness_symmetry_error(stiffness: np.ndarray | csr_matrix) -> float:
    diff = stiffness - stiffness.T
    if hasattr(diff, "toarray"):
        return float(np.linalg.norm(diff.toarray(), ord=np.inf))
    return float(np.linalg.norm(diff, ord=np.inf))


def _small_sparse_rank_deficiency_detail(free_stiffness: csr_matrix) -> str | None:
    """Small-preview guard to block singular sparse systems before SuperLU emits output."""
    if free_stiffness.shape[0] > 64:
        return None
    dense = free_stiffness.toarray()
    rank = int(np.linalg.matrix_rank(dense))
    order = int(free_stiffness.shape[0])
    if rank < order:
        return f"small_sparse_rank_precheck_failed:rank={rank}:order={order}"
    return None


def _solve_linear_static(
    assembly: LinearStaticAssembly,
    model: CanonicalModel,
    *,
    tolerance: float,
    matrix_backend: str,
    sparse_backend_used: bool,
) -> LinearStaticSolution:
    constrained = set(assembly.constrained_dofs)
    all_dofs = set(range(assembly.loads.shape[0]))
    free = sorted(all_dofs - constrained)
    if not free:
        return _blocked_response(
            [{"kind": "linear_static_no_free_dofs"}],
            model,
            assembly=assembly,
            matrix_backend=matrix_backend,
            sparse_backend_used=sparse_backend_used,
        )

    free_stiffness = assembly.stiffness[np.ix_(free, free)]
    free_loads = assembly.loads[free]
    try:
        if sparse_backend_used:
            rank_deficiency_detail = _small_sparse_rank_deficiency_detail(
                free_stiffness.tocsr()
            )
            if rank_deficiency_detail is not None:
                raise ValueError(rank_deficiency_detail)
            with warnings_module.catch_warnings():
                warnings_module.simplefilter("error", MatrixRankWarning)
                free_displacements = np.asarray(
                    spsolve(free_stiffness.tocsc(), free_loads),
                    dtype=float,
                )
            if not np.all(np.isfinite(free_displacements)):
                raise ValueError("sparse solve returned non-finite displacements")
        else:
            free_displacements = np.linalg.solve(free_stiffness, free_loads)
    except (np.linalg.LinAlgError, ValueError, MatrixRankWarning) as exc:
        return _blocked_response(
            [
                {
                    "kind": "linear_static_singular_stiffness",
                    "detail": str(exc),
                    "free_dof_count": len(free),
                    "constrained_dof_count": len(constrained),
                    "guard_outcome": "blocked",
                    "mechanism_guard": "singular_or_rigid_body",
                    "regularization_used": False,
                    "fallback_used": False,
                }
            ],
            model,
            assembly=assembly,
            free_dof_count=len(free),
            matrix_backend=matrix_backend,
            sparse_backend_used=sparse_backend_used,
        )

    displacements = np.zeros(assembly.loads.shape[0], dtype=float)
    displacements[free] = free_displacements
    internal_forces = assembly.stiffness @ displacements
    external_forces = assembly.loads
    residual = linear_static_residual(assembly, displacements)
    reactions = residual.copy()
    residual_free = residual[free]
    residual_constrained = residual[sorted(constrained)] if constrained else np.array([])
    residual_norm = float(np.linalg.norm(residual_free, ord=np.inf)) if residual_free.size else 0.0
    constrained_reaction_norm = (
        float(np.linalg.norm(residual_constrained, ord=np.inf))
        if residual_constrained.size
        else 0.0
    )
    load_norm = float(np.linalg.norm(assembly.loads, ord=np.inf)) if assembly.loads.size else 0.0
    displacement_norm = float(np.linalg.norm(displacements, ord=np.inf)) if displacements.size else 0.0
    relative_residual = residual_norm / max(load_norm, 1.0)
    strain_energy = float(0.5 * displacements @ internal_forces)
    linear_ramp_external_work = float(0.5 * displacements @ external_forces)
    energy_balance_error = abs(strain_energy - linear_ramp_external_work)
    stiffness_symmetry_error = _stiffness_symmetry_error(assembly.stiffness)
    status = "ready" if residual_norm <= tolerance * max(load_norm, 1.0) else "degraded"
    warnings = list(assembly.warnings)
    if status == "degraded":
        warnings.append("Linear static residual exceeded configured tolerance.")

    return LinearStaticSolution(
        status=status,
        metrics={
            "node_count": len(model.nodes),
            "element_count": len(model.elements),
            "load_count": len(model.loads),
            "support_count": len(model.supports),
            "free_dof_count": len(free),
            "constrained_dof_count": len(constrained),
            "residual_formula": RESIDUAL_FORMULA,
            "tangent_jacobian_equals_assembled_stiffness": True,
            "tangent_jacobian_storage": assembly.stiffness_storage,
            "residual_norm": residual_norm,
            "free_residual_norm": residual_norm,
            "constrained_reaction_norm": constrained_reaction_norm,
            "relative_residual": relative_residual,
            "max_displacement": displacement_norm,
            "regularization_used": False,
            "fallback_used": False,
            "stiffness_storage": assembly.stiffness_storage,
            "stiffness_order": int(assembly.stiffness.shape[0]),
            "free_stiffness_order": len(free),
            "matrix_backend": matrix_backend,
            "sparse_backend_used": sparse_backend_used,
            "strain_energy": strain_energy,
            "linear_ramp_external_work": linear_ramp_external_work,
            "energy_balance_error": energy_balance_error,
            "stiffness_symmetry_error": stiffness_symmetry_error,
            "external_forces": _node_vector_rows(assembly.node_ids, external_forces),
            "internal_forces": _node_vector_rows(assembly.node_ids, internal_forces),
            "displacements": _node_vector_rows(assembly.node_ids, displacements),
            "reactions": _node_vector_rows(assembly.node_ids, reactions),
            "claim_boundary": "linear_static_axial_truss_preview_only",
        },
        convergence_history=[
            {
                "step": "linear_static",
                "iteration": 1,
                "residual_norm": residual_norm,
                "relative_residual": relative_residual,
                "relative_increment": displacement_norm,
                "status": status,
            }
        ],
        warnings=warnings,
    )


def _blocked(
    unsupported: list[dict[str, Any]],
    model: CanonicalModel,
    *,
    assembly: Any | None = None,
    free_dof_count: int | None = None,
) -> LinearStaticSolution:
    return _blocked_response(
        unsupported,
        model,
        assembly=assembly,
        free_dof_count=free_dof_count,
        matrix_backend=MATRIX_BACKEND,
        sparse_backend_used=SPARSE_BACKEND_USED,
    )


def _blocked_sparse(
    unsupported: list[dict[str, Any]],
    model: CanonicalModel,
    *,
    assembly: Any | None = None,
    free_dof_count: int | None = None,
) -> LinearStaticSolution:
    return _blocked_response(
        unsupported,
        model,
        assembly=assembly,
        free_dof_count=free_dof_count,
        matrix_backend=SPARSE_MATRIX_BACKEND,
        sparse_backend_used=True,
    )


def _blocked_response(
    unsupported: list[dict[str, Any]],
    model: CanonicalModel,
    *,
    assembly: Any | None = None,
    free_dof_count: int | None = None,
    matrix_backend: str,
    sparse_backend_used: bool,
) -> LinearStaticSolution:
    stiffness_storage = (
        SPARSE_STIFFNESS_STORAGE if sparse_backend_used else STIFFNESS_STORAGE
    )
    metrics: dict[str, Any] = {
        "node_count": len(model.nodes),
        "element_count": len(model.elements),
        "load_count": len(model.loads),
        "support_count": len(model.supports),
        "claim_boundary": "linear_static_axial_truss_preview_only",
        "regularization_used": False,
        "fallback_used": False,
        "stiffness_storage": stiffness_storage,
        "matrix_backend": matrix_backend,
        "sparse_backend_used": sparse_backend_used,
    }
    if assembly is not None:
        metrics["stiffness_order"] = int(assembly.stiffness.shape[0])
        if free_dof_count is not None:
            metrics["free_stiffness_order"] = free_dof_count
    return LinearStaticSolution(
        status="blocked",
        metrics=metrics,
        convergence_history=[],
        unsupported_features=unsupported,
    )


def _node_vector_rows(node_ids: tuple[str, ...], vector: np.ndarray) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    for node_index, node_id in enumerate(node_ids):
        base = 3 * node_index
        rows[node_id] = {
            label: float(vector[base + offset])
            for offset, label in enumerate(DOF_LABELS)
        }
    return rows
