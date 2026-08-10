"""Fail-closed sparse modal and linear-buckling generalized-eigen kernels."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import struct
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix, issparse
from scipy.sparse.linalg import (
    ArpackNoConvergence,
    LinearOperator,
    eigsh,
    splu,
)

from structural_analysis.solvers._generalized_eigen import (
    SEMANTIC_HASH_PROFILE,
    GeneralizedEigenContractError,
    cluster_slices,
    max_component_normalized,
    raw_modes_sha256,
    require_complete_cluster_selection,
    require_nonnegative_tolerance,
    semantic_modes_sha256,
)
from structural_analysis.solvers.buckling.solver import BucklingMode
from structural_analysis.solvers.modal.solver import ModalMode


SPARSE_MODAL_PROFILE = "scipy_arpack_symmetric_generalized_modal.v1"
SPARSE_BUCKLING_PROFILE = "scipy_arpack_splu_reciprocal_linear_buckling.v1"
SPARSE_EIGEN_CLAIM_BOUNDARY = (
    "Sparse symmetric extraction with CSR inputs and no dense or regularized "
    "fallback. Assembly may still be dense upstream; only the requested low-mode "
    "subspace is proven, and external Level 2 validation remains separate."
)


class SparseGeneralizedEigenError(GeneralizedEigenContractError):
    """Stable failure for sparse eigen input, convergence, or contract gates."""


@dataclass(frozen=True)
class SparseModalSolution:
    schema_version: str
    backend_profile: str
    dof_count: int
    requested_mode_count: int
    mode_count: int
    rigid_mode_count: int
    candidate_eigenpair_count: int
    modes: tuple[ModalMode, ...]
    mass_orthogonality_error_inf: float
    stiffness_diagonalization_error_inf: float
    stiffness_relative_symmetry_error: float
    mass_relative_symmetry_error: float
    stiffness_minimum_eigenvalue_estimate: float
    mass_minimum_eigenvalue_estimate: float
    stiffness_matrix_hash: str
    mass_matrix_hash: str
    raw_result_hash: str
    semantic_result_hash: str
    semantic_hash_profile: str
    symmetry_projection_applied: bool
    native_sparse_input: bool
    regularization_applied: bool
    fallback_used: bool
    deterministic_mode_basis: bool
    contract_pass: bool
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SparseBucklingSolution:
    schema_version: str
    backend_profile: str
    dof_count: int
    requested_mode_count: int
    mode_count: int
    candidate_eigenpair_count: int
    finite_positive_eigenvalue_count_lower_bound: int
    geometric_stiffness_positive_rank_lower_bound: int
    modes: tuple[BucklingMode, ...]
    critical_load_factor: float
    stiffness_orthogonality_error_inf: float
    geometric_diagonalization_error_inf: float
    stiffness_relative_symmetry_error: float
    geometric_stiffness_relative_symmetry_error: float
    stiffness_minimum_eigenvalue_estimate: float
    geometric_stiffness_minimum_eigenvalue_estimate: float
    stiffness_matrix_hash: str
    geometric_stiffness_matrix_hash: str
    raw_result_hash: str
    semantic_result_hash: str
    semantic_hash_profile: str
    symmetry_projection_applied: bool
    native_sparse_input: bool
    regularization_applied: bool
    fallback_used: bool
    deterministic_mode_basis: bool
    contract_pass: bool
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def solve_sparse_modal_modes(
    stiffness: Any,
    mass: Any,
    *,
    mode_count: int,
    symmetry_relative_tolerance: float = 1.0e-12,
    positive_semidefinite_relative_tolerance: float = 1.0e-10,
    rigid_mode_relative_tolerance: float = 1.0e-10,
    cluster_relative_tolerance: float = 1.0e-9,
    residual_relative_tolerance: float = 1.0e-9,
    orthogonality_tolerance: float = 1.0e-8,
    arpack_tolerance: float = 1.0e-12,
    maximum_iterations: int | None = None,
) -> SparseModalSolution:
    requested = _mode_count(mode_count)
    tolerances = _tolerances(
        symmetry_relative_tolerance=symmetry_relative_tolerance,
        positive_semidefinite_relative_tolerance=(
            positive_semidefinite_relative_tolerance
        ),
        cluster_relative_tolerance=cluster_relative_tolerance,
        residual_relative_tolerance=residual_relative_tolerance,
        orthogonality_tolerance=orthogonality_tolerance,
        arpack_tolerance=arpack_tolerance,
    )
    rigid_tolerance = require_nonnegative_tolerance(
        rigid_mode_relative_tolerance,
        name="rigid_mode_relative_tolerance",
    )
    native_sparse = bool(issparse(stiffness) and issparse(mass))
    try:
        k_matrix = _as_csr(stiffness, "stiffness")
        m_matrix = _as_csr(mass, "mass")
        _same_shape(k_matrix, m_matrix)
        n = k_matrix.shape[0]
        candidate_count = _candidate_count(n, requested)
        k_matrix, k_symmetry, k_projected = _validate_symmetric_sparse(
            k_matrix,
            name="stiffness",
            tolerance=tolerances["symmetry_relative_tolerance"],
        )
        m_matrix, m_symmetry, m_projected = _validate_symmetric_sparse(
            m_matrix,
            name="mass",
            tolerance=tolerances["symmetry_relative_tolerance"],
        )
        try:
            mass_factor = splu(m_matrix.tocsc())
        except RuntimeError as exc:
            raise SparseGeneralizedEigenError(
                "mass must be numerically positive definite"
            ) from exc
        mass_inverse = LinearOperator(
            shape=m_matrix.shape,
            matvec=mass_factor.solve,
            dtype=np.float64,
        )
        try:
            mass_minimum, mass_scale = _extreme_eigenvalues(
                m_matrix,
                maximum_iterations=maximum_iterations,
                arpack_tolerance=tolerances["arpack_tolerance"],
            )
        except (
            ArpackNoConvergence,
            RuntimeError,
            ValueError,
            np.linalg.LinAlgError,
        ) as exc:
            raise SparseGeneralizedEigenError(
                "mass must be numerically positive definite"
            ) from exc
        _require_numerically_positive_definite(
            mass_minimum,
            mass_scale,
            size=n,
            name="mass",
        )
        stiffness_minimum, stiffness_scale = _extreme_eigenvalues(
            k_matrix,
            maximum_iterations=maximum_iterations,
            arpack_tolerance=tolerances["arpack_tolerance"],
        )
        if (
            stiffness_minimum
            < -tolerances["positive_semidefinite_relative_tolerance"] * stiffness_scale
        ):
            raise SparseGeneralizedEigenError(
                "stiffness violates the positive-semidefinite contract"
            )
        raw_values, raw_vectors = eigsh(
            k_matrix,
            k=candidate_count,
            M=m_matrix,
            Minv=mass_inverse,
            which="SM",
            tol=tolerances["arpack_tolerance"],
            maxiter=maximum_iterations,
            v0=_deterministic_start(n),
        )
        order = np.argsort(raw_values, kind="stable")
        raw_values = np.asarray(raw_values[order], dtype=np.float64)
        raw_vectors = np.asarray(raw_vectors[:, order], dtype=np.float64)
        largest_generalized = float(
            eigsh(
                k_matrix,
                k=1,
                M=m_matrix,
                Minv=mass_inverse,
                which="LA",
                return_eigenvectors=False,
                tol=tolerances["arpack_tolerance"],
                maxiter=maximum_iterations,
                v0=_deterministic_start(n),
            )[0]
        )
        spectral_scale = max(abs(largest_generalized), 1.0)
        rigid_threshold = rigid_tolerance * spectral_scale
        positive_indices = np.flatnonzero(raw_values > rigid_threshold)
        rigid_count = int(np.count_nonzero(raw_values <= rigid_threshold))
        if positive_indices.size < requested:
            raise SparseGeneralizedEigenError(
                f"requested {requested} positive modes but only "
                f"{positive_indices.size} were extracted"
            )
        positive_values = raw_values[positive_indices]
        require_complete_cluster_selection(
            positive_values,
            selected_count=requested,
            relative_tolerance=tolerances["cluster_relative_tolerance"],
        )
        selected_values = np.asarray(positive_values[:requested], dtype=np.float64)
        selected_vectors = raw_vectors[:, positive_indices[:requested]]
        canonical = _canonicalize_sparse_clusters(
            selected_vectors,
            selected_values,
            metric=m_matrix,
            cluster_relative_tolerance=tolerances["cluster_relative_tolerance"],
        )
        values = np.asarray(
            [float(vector @ (k_matrix @ vector)) for vector in canonical.T],
            dtype=np.float64,
        )
        modes: list[ModalMode] = []
        for index, (eigenvalue, vector) in enumerate(
            zip(values.tolist(), canonical.T, strict=True)
        ):
            if not math.isfinite(eigenvalue) or eigenvalue <= 0.0:
                raise SparseGeneralizedEigenError(
                    f"mode {index + 1} has a non-positive Rayleigh eigenvalue"
                )
            residual = k_matrix @ vector - eigenvalue * (m_matrix @ vector)
            denominator = max(
                float(np.linalg.norm(k_matrix @ vector, ord=np.inf))
                + abs(eigenvalue)
                * float(np.linalg.norm(m_matrix @ vector, ord=np.inf)),
                float(np.finfo(np.float64).tiny),
            )
            residual_relative = (
                float(np.linalg.norm(residual, ord=np.inf)) / denominator
            )
            if residual_relative > tolerances["residual_relative_tolerance"]:
                raise SparseGeneralizedEigenError(
                    f"mode {index + 1} residual gate failed"
                )
            omega = math.sqrt(eigenvalue)
            modes.append(
                ModalMode(
                    mode_number=index + 1,
                    eigenvalue_rad2_per_s2=eigenvalue,
                    omega_rad_per_s=omega,
                    frequency_hz=omega / (2.0 * math.pi),
                    period_s=2.0 * math.pi / omega,
                    mass_normalized_shape=tuple(float(value) for value in vector),
                    max_component_normalized_shape=max_component_normalized(vector),
                    generalized_mass=float(vector @ (m_matrix @ vector)),
                    generalized_stiffness=float(vector @ (k_matrix @ vector)),
                    residual_relative_inf=residual_relative,
                )
            )
        mass_gram = canonical.T @ (m_matrix @ canonical)
        stiffness_gram = canonical.T @ (k_matrix @ canonical)
        mass_error = float(np.max(np.abs(mass_gram - np.eye(requested))))
        stiffness_error = float(
            np.max(np.abs(stiffness_gram - np.diag(values)))
            / max(float(np.max(np.abs(values))), 1.0)
        )
        if (
            mass_error > tolerances["orthogonality_tolerance"]
            or stiffness_error > tolerances["orthogonality_tolerance"]
        ):
            raise SparseGeneralizedEigenError(
                "modal orthogonality or diagonalization gate failed"
            )
    except (
        SparseGeneralizedEigenError,
        GeneralizedEigenContractError,
        ArpackNoConvergence,
        RuntimeError,
        ValueError,
        np.linalg.LinAlgError,
    ) as exc:
        if isinstance(exc, SparseGeneralizedEigenError):
            raise
        raise SparseGeneralizedEigenError(str(exc)) from exc

    return SparseModalSolution(
        schema_version="structural-analysis-sparse-modal-solution.v1",
        backend_profile=SPARSE_MODAL_PROFILE,
        dof_count=n,
        requested_mode_count=requested,
        mode_count=len(modes),
        rigid_mode_count=rigid_count,
        candidate_eigenpair_count=candidate_count,
        modes=tuple(modes),
        mass_orthogonality_error_inf=mass_error,
        stiffness_diagonalization_error_inf=stiffness_error,
        stiffness_relative_symmetry_error=k_symmetry,
        mass_relative_symmetry_error=m_symmetry,
        stiffness_minimum_eigenvalue_estimate=stiffness_minimum,
        mass_minimum_eigenvalue_estimate=mass_minimum,
        stiffness_matrix_hash=_sparse_matrix_hash(k_matrix),
        mass_matrix_hash=_sparse_matrix_hash(m_matrix),
        raw_result_hash=raw_modes_sha256(values.tolist(), canonical),
        semantic_result_hash=semantic_modes_sha256(values.tolist(), canonical),
        semantic_hash_profile=SEMANTIC_HASH_PROFILE,
        symmetry_projection_applied=bool(k_projected or m_projected),
        native_sparse_input=native_sparse,
        regularization_applied=False,
        fallback_used=False,
        deterministic_mode_basis=True,
        contract_pass=True,
        claim_boundary=SPARSE_EIGEN_CLAIM_BOUNDARY,
    )


def solve_sparse_linear_buckling(
    stiffness: Any,
    geometric_stiffness_per_unit_load: Any,
    *,
    mode_count: int,
    symmetry_relative_tolerance: float = 1.0e-12,
    positive_semidefinite_relative_tolerance: float = 1.0e-10,
    finite_mode_relative_tolerance: float = 1.0e-12,
    cluster_relative_tolerance: float = 1.0e-9,
    residual_relative_tolerance: float = 1.0e-8,
    orthogonality_tolerance: float = 1.0e-7,
    arpack_tolerance: float = 1.0e-12,
    maximum_iterations: int | None = None,
) -> SparseBucklingSolution:
    requested = _mode_count(mode_count)
    tolerances = _tolerances(
        symmetry_relative_tolerance=symmetry_relative_tolerance,
        positive_semidefinite_relative_tolerance=(
            positive_semidefinite_relative_tolerance
        ),
        cluster_relative_tolerance=cluster_relative_tolerance,
        residual_relative_tolerance=residual_relative_tolerance,
        orthogonality_tolerance=orthogonality_tolerance,
        arpack_tolerance=arpack_tolerance,
    )
    finite_tolerance = require_nonnegative_tolerance(
        finite_mode_relative_tolerance,
        name="finite_mode_relative_tolerance",
    )
    native_sparse = bool(
        issparse(stiffness) and issparse(geometric_stiffness_per_unit_load)
    )
    try:
        k_matrix = _as_csr(stiffness, "stiffness")
        kg_matrix = _as_csr(
            geometric_stiffness_per_unit_load,
            "geometric_stiffness_per_unit_load",
        )
        _same_shape(k_matrix, kg_matrix)
        n = k_matrix.shape[0]
        candidate_count = _operator_candidate_count(n, requested)
        k_matrix, k_symmetry, k_projected = _validate_symmetric_sparse(
            k_matrix,
            name="stiffness",
            tolerance=tolerances["symmetry_relative_tolerance"],
        )
        kg_matrix, kg_symmetry, kg_projected = _validate_symmetric_sparse(
            kg_matrix,
            name="geometric_stiffness_per_unit_load",
            tolerance=tolerances["symmetry_relative_tolerance"],
        )
        stiffness_minimum, stiffness_scale = _extreme_eigenvalues(
            k_matrix,
            maximum_iterations=maximum_iterations,
            arpack_tolerance=tolerances["arpack_tolerance"],
        )
        _require_numerically_positive_definite(
            stiffness_minimum,
            stiffness_scale,
            size=n,
            name="stiffness",
        )
        geometric_minimum, geometric_scale = _extreme_eigenvalues(
            kg_matrix,
            maximum_iterations=maximum_iterations,
            arpack_tolerance=tolerances["arpack_tolerance"],
        )
        if (
            geometric_minimum
            < -tolerances["positive_semidefinite_relative_tolerance"] * geometric_scale
        ):
            raise SparseGeneralizedEigenError(
                "geometric stiffness violates the positive-semidefinite contract"
            )
        stiffness_factor = splu(k_matrix.tocsc())
        stiffness_inverse = LinearOperator(
            shape=k_matrix.shape,
            matvec=stiffness_factor.solve,
            dtype=np.float64,
        )
        raw_reciprocals, raw_vectors = eigsh(
            kg_matrix,
            k=candidate_count,
            # Keep the Arnoldi workspace immediately above the requested
            # candidate subspace. ARPACK can fail to factorize when its wider
            # default workspace is forced into the nullspace of singular Kg.
            ncv=min(n, candidate_count + 1),
            M=k_matrix,
            Minv=stiffness_inverse,
            which="LA",
            tol=tolerances["arpack_tolerance"],
            maxiter=maximum_iterations,
            v0=_deterministic_start(n),
        )
        reciprocals = np.asarray(raw_reciprocals, dtype=np.float64)
        vectors = np.asarray(raw_vectors, dtype=np.float64)
        if not np.all(np.isfinite(reciprocals)) or not np.all(np.isfinite(vectors)):
            raise SparseGeneralizedEigenError(
                "buckling reciprocal operator returned non-finite modes"
            )
        reciprocal_scale = max(float(np.max(np.abs(reciprocals))), 1.0)
        positive_threshold = finite_tolerance * reciprocal_scale
        positive_candidate_indices = [
            index
            for index, reciprocal in enumerate(reciprocals)
            if math.isfinite(float(reciprocal))
            and float(reciprocal) > positive_threshold
        ]
        candidate_relative_residuals = [
            _generalized_relative_residual(
                kg_matrix,
                k_matrix,
                float(reciprocals[index]),
                np.asarray(vectors[:, index], dtype=np.float64),
            )
            for index in positive_candidate_indices
        ]
        if (
            not candidate_relative_residuals
            or not all(math.isfinite(value) for value in candidate_relative_residuals)
            or max(candidate_relative_residuals)
            > tolerances["residual_relative_tolerance"]
        ):
            raise SparseGeneralizedEigenError(
                "buckling ARPACK candidate relative-residual gate failed"
            )
        candidates = [
            (
                1.0 / float(reciprocals[index]),
                np.asarray(vectors[:, index], dtype=np.float64),
            )
            for index in positive_candidate_indices
        ]
        candidates.sort(key=lambda item: item[0])
        if len(candidates) < requested:
            raise SparseGeneralizedEigenError(
                f"requested {requested} finite positive modes but only "
                f"{len(candidates)} were extracted"
            )
        candidate_values = np.asarray(
            [item[0] for item in candidates],
            dtype=np.float64,
        )
        require_complete_cluster_selection(
            candidate_values,
            selected_count=requested,
            relative_tolerance=tolerances["cluster_relative_tolerance"],
        )
        selected_values = candidate_values[:requested]
        selected_vectors = np.column_stack([item[1] for item in candidates[:requested]])
        canonical = _canonicalize_sparse_clusters(
            selected_vectors,
            selected_values,
            metric=k_matrix,
            cluster_relative_tolerance=tolerances["cluster_relative_tolerance"],
        )
        values: list[float] = []
        modes: list[BucklingMode] = []
        for index, vector in enumerate(canonical.T):
            elastic = float(vector @ (k_matrix @ vector))
            geometric = float(vector @ (kg_matrix @ vector))
            if geometric <= 0.0 or not math.isfinite(geometric):
                raise SparseGeneralizedEigenError(
                    f"buckling mode {index + 1} has non-positive geometric energy"
                )
            factor = elastic / geometric
            residual = k_matrix @ vector - factor * (kg_matrix @ vector)
            denominator = max(
                float(np.linalg.norm(k_matrix @ vector, ord=np.inf))
                + factor * float(np.linalg.norm(kg_matrix @ vector, ord=np.inf)),
                float(np.finfo(np.float64).tiny),
            )
            residual_relative = (
                float(np.linalg.norm(residual, ord=np.inf)) / denominator
            )
            if residual_relative > tolerances["residual_relative_tolerance"]:
                raise SparseGeneralizedEigenError(
                    f"buckling mode {index + 1} residual gate failed"
                )
            values.append(factor)
            modes.append(
                BucklingMode(
                    mode_number=index + 1,
                    load_factor=factor,
                    stiffness_normalized_shape=tuple(float(value) for value in vector),
                    max_component_normalized_shape=max_component_normalized(vector),
                    generalized_elastic_stiffness=elastic,
                    generalized_geometric_stiffness=geometric,
                    residual_relative_inf=residual_relative,
                )
            )
        value_array = np.asarray(values, dtype=np.float64)
        stiffness_gram = canonical.T @ (k_matrix @ canonical)
        geometric_gram = canonical.T @ (kg_matrix @ canonical)
        stiffness_error = float(np.max(np.abs(stiffness_gram - np.eye(requested))))
        expected_geometric = np.diag(1.0 / value_array)
        geometric_error = float(
            np.max(np.abs(geometric_gram - expected_geometric))
            / max(float(np.max(np.abs(expected_geometric))), 1.0)
        )
        if (
            stiffness_error > tolerances["orthogonality_tolerance"]
            or geometric_error > tolerances["orthogonality_tolerance"]
        ):
            raise SparseGeneralizedEigenError(
                "buckling orthogonality or diagonalization gate failed"
            )
    except (
        SparseGeneralizedEigenError,
        GeneralizedEigenContractError,
        ArpackNoConvergence,
        RuntimeError,
        ValueError,
        np.linalg.LinAlgError,
    ) as exc:
        if isinstance(exc, SparseGeneralizedEigenError):
            raise
        raise SparseGeneralizedEigenError(str(exc)) from exc

    return SparseBucklingSolution(
        schema_version="structural-analysis-sparse-linear-buckling-solution.v1",
        backend_profile=SPARSE_BUCKLING_PROFILE,
        dof_count=n,
        requested_mode_count=requested,
        mode_count=len(modes),
        candidate_eigenpair_count=candidate_count,
        finite_positive_eigenvalue_count_lower_bound=len(candidates),
        geometric_stiffness_positive_rank_lower_bound=len(candidates),
        modes=tuple(modes),
        critical_load_factor=float(value_array[0]),
        stiffness_orthogonality_error_inf=stiffness_error,
        geometric_diagonalization_error_inf=geometric_error,
        stiffness_relative_symmetry_error=k_symmetry,
        geometric_stiffness_relative_symmetry_error=kg_symmetry,
        stiffness_minimum_eigenvalue_estimate=stiffness_minimum,
        geometric_stiffness_minimum_eigenvalue_estimate=geometric_minimum,
        stiffness_matrix_hash=_sparse_matrix_hash(k_matrix),
        geometric_stiffness_matrix_hash=_sparse_matrix_hash(kg_matrix),
        raw_result_hash=raw_modes_sha256(value_array.tolist(), canonical),
        semantic_result_hash=semantic_modes_sha256(value_array.tolist(), canonical),
        semantic_hash_profile=SEMANTIC_HASH_PROFILE,
        symmetry_projection_applied=bool(k_projected or kg_projected),
        native_sparse_input=native_sparse,
        regularization_applied=False,
        fallback_used=False,
        deterministic_mode_basis=True,
        contract_pass=True,
        claim_boundary=SPARSE_EIGEN_CLAIM_BOUNDARY,
    )


def _mode_count(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise SparseGeneralizedEigenError("mode_count must be a positive integer")
    return value


def _candidate_count(dof_count: int, requested: int) -> int:
    if dof_count < 3 or requested >= dof_count - 1:
        raise SparseGeneralizedEigenError(
            "sparse extraction requires mode_count <= dof_count - 2"
        )
    return min(dof_count - 1, max(requested + 8, 2 * requested + 2))


def _operator_candidate_count(dof_count: int, requested: int) -> int:
    if dof_count < 3 or requested >= dof_count - 1:
        raise SparseGeneralizedEigenError(
            "sparse extraction requires mode_count <= dof_count - 2"
        )
    # scipy.sparse.linalg.eigsh requires k < N. Keep one further vector
    # outside the requested subspace so cluster-cut detection stays sparse.
    return min(dof_count - 2, max(requested + 8, 2 * requested + 2))


def _tolerances(**values: float) -> dict[str, float]:
    return {
        name: require_nonnegative_tolerance(value, name=name)
        for name, value in values.items()
    }


def _as_csr(value: Any, name: str) -> csr_matrix:
    try:
        matrix = csr_matrix(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise SparseGeneralizedEigenError(f"{name} must be a numeric matrix") from exc
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        raise SparseGeneralizedEigenError(f"{name} must be a non-empty square matrix")
    matrix.sum_duplicates()
    matrix.sort_indices()
    if not np.all(np.isfinite(matrix.data)):
        raise SparseGeneralizedEigenError(f"{name} must contain finite values")
    return matrix


def _same_shape(left: csr_matrix, right: csr_matrix) -> None:
    if left.shape != right.shape:
        raise SparseGeneralizedEigenError(
            "generalized-eigen matrices must have equal shape"
        )


def _validate_symmetric_sparse(
    matrix: csr_matrix,
    *,
    name: str,
    tolerance: float,
) -> tuple[csr_matrix, float, bool]:
    difference = matrix - matrix.T
    error = float(np.max(np.abs(difference.data))) if difference.nnz else 0.0
    scale = max(float(np.max(np.abs(matrix.data))) if matrix.nnz else 0.0, 1.0)
    relative = error / scale
    if relative > tolerance:
        raise SparseGeneralizedEigenError(
            f"{name} symmetry error {relative:.17g} exceeds {tolerance:.17g}"
        )
    projected = bool(error > 0.0)
    result = csr_matrix(0.5 * (matrix + matrix.T), dtype=np.float64)
    result.eliminate_zeros()
    result.sort_indices()
    return result, relative, projected


def _extreme_eigenvalues(
    matrix: csr_matrix,
    *,
    maximum_iterations: int | None,
    arpack_tolerance: float,
) -> tuple[float, float]:
    start = _deterministic_start(matrix.shape[0])
    minimum = float(
        eigsh(
            matrix,
            k=1,
            which="SA",
            return_eigenvectors=False,
            tol=arpack_tolerance,
            maxiter=maximum_iterations,
            v0=start,
        )[0]
    )
    largest = float(
        eigsh(
            matrix,
            k=1,
            which="LA",
            return_eigenvectors=False,
            tol=arpack_tolerance,
            maxiter=maximum_iterations,
            v0=start,
        )[0]
    )
    return minimum, max(
        abs(minimum),
        abs(largest),
        float(np.finfo(np.float64).tiny),
    )


def _require_numerically_positive_definite(
    minimum_eigenvalue: float,
    spectral_scale: float,
    *,
    size: int,
    name: str,
) -> None:
    threshold = (
        float(np.finfo(np.float64).eps)
        * max(size, 1)
        * max(spectral_scale, float(np.finfo(np.float64).tiny))
    )
    if not math.isfinite(minimum_eigenvalue) or minimum_eigenvalue <= threshold:
        raise SparseGeneralizedEigenError(
            f"{name} must be numerically positive definite"
        )


def _generalized_relative_residual(
    left: csr_matrix,
    right: csr_matrix,
    eigenvalue: float,
    vector: np.ndarray,
) -> float:
    left_vector = left @ vector
    right_vector = right @ vector
    residual = left_vector - eigenvalue * right_vector
    denominator = max(
        float(np.linalg.norm(left_vector, ord=np.inf))
        + abs(eigenvalue) * float(np.linalg.norm(right_vector, ord=np.inf)),
        float(np.finfo(np.float64).tiny),
    )
    return float(np.linalg.norm(residual, ord=np.inf)) / denominator


def _deterministic_start(size: int) -> np.ndarray:
    vector = np.linspace(1.0, 2.0, num=size, dtype=np.float64)
    return vector / float(np.linalg.norm(vector))


def _canonicalize_sparse_clusters(
    vectors: np.ndarray,
    values: np.ndarray,
    *,
    metric: csr_matrix,
    cluster_relative_tolerance: float,
) -> np.ndarray:
    canonical = np.empty_like(vectors)
    for cluster in cluster_slices(
        values,
        relative_tolerance=cluster_relative_tolerance,
    ):
        canonical[:, cluster] = _canonicalize_sparse_eigenspace(
            vectors[:, cluster],
            metric,
        )
    return canonical


def _canonicalize_sparse_eigenspace(
    basis: np.ndarray,
    metric: csr_matrix,
) -> np.ndarray:
    orthonormal = _metric_orthonormalize(
        [basis[:, index] for index in range(basis.shape[1])],
        metric,
        required_count=basis.shape[1],
    )
    coefficients = np.asarray(orthonormal.T @ metric, dtype=np.float64)
    candidates = [
        orthonormal @ coefficients[:, coordinate]
        for coordinate in range(metric.shape[0])
    ]
    return _metric_orthonormalize(
        candidates,
        metric,
        required_count=basis.shape[1],
    )


def _metric_orthonormalize(
    candidates: list[np.ndarray],
    metric: csr_matrix,
    *,
    required_count: int,
) -> np.ndarray:
    accepted: list[np.ndarray] = []
    for candidate in candidates:
        vector = np.asarray(candidate, dtype=np.float64).copy()
        if vector.shape != (metric.shape[0],) or not np.all(np.isfinite(vector)):
            continue
        for _ in range(2):
            for prior in accepted:
                vector -= prior * float(prior @ (metric @ vector))
        norm_squared = float(vector @ (metric @ vector))
        if not math.isfinite(norm_squared) or norm_squared <= 1.0e-24:
            continue
        vector /= math.sqrt(norm_squared)
        pivot = int(np.argmax(np.abs(vector)))
        if vector[pivot] < 0.0:
            vector *= -1.0
        accepted.append(vector)
        if len(accepted) == required_count:
            break
    if len(accepted) != required_count:
        raise SparseGeneralizedEigenError(
            "coordinate-axis sparse eigenspace canonicalization lost rank"
        )
    return np.column_stack(accepted)


def _sparse_matrix_hash(matrix: csr_matrix) -> str:
    value = matrix.copy()
    value.sum_duplicates()
    value.sort_indices()
    digest = hashlib.sha256()
    digest.update(b"structural-analysis/canonical-csr-f64/v1\0")
    digest.update(struct.pack("<2q", *value.shape))
    digest.update(np.asarray(value.indptr, dtype="<i8").tobytes())
    digest.update(np.asarray(value.indices, dtype="<i8").tobytes())
    digest.update(np.asarray(value.data, dtype="<f8").tobytes())
    return "sha256:" + digest.hexdigest()


__all__ = [
    "SPARSE_BUCKLING_PROFILE",
    "SPARSE_EIGEN_CLAIM_BOUNDARY",
    "SPARSE_MODAL_PROFILE",
    "SparseBucklingSolution",
    "SparseGeneralizedEigenError",
    "SparseModalSolution",
    "solve_sparse_linear_buckling",
    "solve_sparse_modal_modes",
]
