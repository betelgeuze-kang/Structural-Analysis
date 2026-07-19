"""Deterministic linear-buckling kernel for ``K phi = lambda Kg phi``."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np
from scipy.linalg import eigh

from structural_analysis.solvers._generalized_eigen import (
    SEMANTIC_HASH_PROFILE,
    GeneralizedEigenContractError,
    as_binary64_square,
    canonicalize_eigenspace,
    cluster_slices,
    matrix_sha256,
    max_component_normalized,
    raw_modes_sha256,
    require_complete_cluster_selection,
    require_nonnegative_tolerance,
    require_positive_definite,
    require_positive_semidefinite,
    semantic_modes_sha256,
    validate_symmetric,
)


BUCKLING_SOLUTION_SCHEMA_VERSION = "deterministic-linear-buckling-solution.v1"


class BucklingAnalysisError(GeneralizedEigenContractError):
    """Raised when a linear-buckling eigenproblem fails its strict contract."""


@dataclass(frozen=True)
class BucklingMode:
    mode_number: int
    load_factor: float
    stiffness_normalized_shape: tuple[float, ...]
    max_component_normalized_shape: tuple[float, ...]
    generalized_elastic_stiffness: float
    generalized_geometric_stiffness: float
    residual_relative_inf: float


@dataclass(frozen=True)
class BucklingSolution:
    schema_version: str
    dof_count: int
    requested_mode_count: int
    mode_count: int
    finite_positive_eigenvalue_count: int
    modes: tuple[BucklingMode, ...]
    critical_load_factor: float
    stiffness_orthogonality_error_inf: float
    geometric_diagonalization_error_inf: float
    stiffness_relative_symmetry_error: float
    geometric_stiffness_relative_symmetry_error: float
    stiffness_minimum_eigenvalue: float
    geometric_stiffness_minimum_eigenvalue: float
    geometric_stiffness_positive_rank: int
    stiffness_matrix_hash: str
    geometric_stiffness_matrix_hash: str
    raw_result_hash: str
    semantic_result_hash: str
    semantic_hash_profile: str
    symmetry_projection_applied: bool
    regularization_applied: bool
    fallback_used: bool
    deterministic_mode_basis: bool
    contract_pass: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def solve_linear_buckling(
    stiffness: np.ndarray,
    geometric_stiffness_per_unit_load: np.ndarray,
    *,
    mode_count: int,
    symmetry_relative_tolerance: float = 1.0e-12,
    positive_semidefinite_relative_tolerance: float = 1.0e-12,
    finite_mode_relative_tolerance: float = 1.0e-12,
    cluster_relative_tolerance: float = 1.0e-10,
    residual_relative_tolerance: float = 1.0e-9,
    orthogonality_tolerance: float = 1.0e-8,
) -> BucklingSolution:
    """Solve a strict symmetric linear-buckling problem without fallback."""

    requested = _mode_count(mode_count)
    try:
        symmetry_relative_tolerance = require_nonnegative_tolerance(
            symmetry_relative_tolerance,
            name="symmetry_relative_tolerance",
        )
        positive_semidefinite_relative_tolerance = require_nonnegative_tolerance(
            positive_semidefinite_relative_tolerance,
            name="positive_semidefinite_relative_tolerance",
        )
        finite_mode_relative_tolerance = require_nonnegative_tolerance(
            finite_mode_relative_tolerance,
            name="finite_mode_relative_tolerance",
        )
        cluster_relative_tolerance = require_nonnegative_tolerance(
            cluster_relative_tolerance,
            name="cluster_relative_tolerance",
        )
        residual_relative_tolerance = require_nonnegative_tolerance(
            residual_relative_tolerance,
            name="residual_relative_tolerance",
        )
        orthogonality_tolerance = require_nonnegative_tolerance(
            orthogonality_tolerance,
            name="orthogonality_tolerance",
        )
        k_input = as_binary64_square(stiffness, name="stiffness")
        kg_input = as_binary64_square(
            geometric_stiffness_per_unit_load,
            name="geometric_stiffness_per_unit_load",
        )
        if k_input.shape != kg_input.shape:
            raise GeneralizedEigenContractError(
                "stiffness and geometric stiffness matrices must have the same shape"
            )
        k_matrix, k_symmetry, k_projected = validate_symmetric(
            k_input,
            name="stiffness",
            relative_tolerance=symmetry_relative_tolerance,
        )
        kg_matrix, kg_symmetry, kg_projected = validate_symmetric(
            kg_input,
            name="geometric_stiffness_per_unit_load",
            relative_tolerance=symmetry_relative_tolerance,
        )
        stiffness_minimum = require_positive_definite(k_matrix, name="stiffness")
        geometric_minimum, geometric_rank = require_positive_semidefinite(
            kg_matrix,
            name="geometric_stiffness_per_unit_load",
            relative_tolerance=positive_semidefinite_relative_tolerance,
        )
        raw_reciprocals, raw_vectors = eigh(
            kg_matrix,
            k_matrix,
            check_finite=False,
            driver="gvd",
        )
        candidates: list[tuple[float, np.ndarray]] = []
        reciprocal_scale = max(
            float(np.max(np.abs(raw_reciprocals))),
            np.finfo(np.float64).tiny,
        )
        positive_threshold = finite_mode_relative_tolerance * reciprocal_scale
        for index, reciprocal in enumerate(raw_reciprocals.tolist()):
            reciprocal_value = float(reciprocal)
            if (
                not math.isfinite(reciprocal_value)
                or reciprocal_value <= positive_threshold
            ):
                continue
            vector = np.asarray(raw_vectors[:, index], dtype=np.float64)
            norm_squared = float(vector @ k_matrix @ vector)
            if not math.isfinite(norm_squared) or norm_squared <= 0.0:
                continue
            candidates.append(
                (1.0 / reciprocal_value, vector / math.sqrt(norm_squared))
            )
        candidates.sort(key=lambda item: item[0])
        if len(candidates) < requested:
            raise GeneralizedEigenContractError(
                f"requested {requested} finite positive buckling modes but only "
                f"{len(candidates)} are available"
            )
        require_complete_cluster_selection(
            np.asarray([item[0] for item in candidates], dtype=np.float64),
            selected_count=requested,
            relative_tolerance=cluster_relative_tolerance,
        )
        selected = candidates[:requested]
        selected_values = np.asarray([item[0] for item in selected], dtype=np.float64)
        selected_vectors = np.column_stack([item[1] for item in selected])
        canonical = np.empty_like(selected_vectors)
        for cluster in cluster_slices(
            selected_values,
            relative_tolerance=cluster_relative_tolerance,
        ):
            canonical[:, cluster] = canonicalize_eigenspace(
                selected_vectors[:, cluster],
                metric=k_matrix,
            )
        values: list[float] = []
        modes: list[BucklingMode] = []
        for index in range(requested):
            vector = canonical[:, index]
            elastic = float(vector @ k_matrix @ vector)
            geometric = float(vector @ kg_matrix @ vector)
            if not math.isfinite(geometric) or geometric <= 0.0:
                raise GeneralizedEigenContractError(
                    f"buckling mode {index + 1} has non-positive geometric energy"
                )
            load_factor = elastic / geometric
            residual = k_matrix @ vector - load_factor * (kg_matrix @ vector)
            denominator = max(
                float(np.linalg.norm(k_matrix @ vector, ord=np.inf))
                + abs(load_factor)
                * float(np.linalg.norm(kg_matrix @ vector, ord=np.inf)),
                np.finfo(np.float64).tiny,
            )
            residual_relative = float(np.linalg.norm(residual, ord=np.inf)) / denominator
            if residual_relative > residual_relative_tolerance:
                raise GeneralizedEigenContractError(
                    f"buckling mode {index + 1} residual {residual_relative:.17g} "
                    f"exceeds {residual_relative_tolerance:.17g}"
                )
            values.append(load_factor)
            modes.append(
                BucklingMode(
                    mode_number=index + 1,
                    load_factor=load_factor,
                    stiffness_normalized_shape=tuple(
                        float(value) for value in vector.tolist()
                    ),
                    max_component_normalized_shape=max_component_normalized(vector),
                    generalized_elastic_stiffness=elastic,
                    generalized_geometric_stiffness=geometric,
                    residual_relative_inf=residual_relative,
                )
            )
        value_array = np.asarray(values, dtype=np.float64)
        stiffness_gram = canonical.T @ k_matrix @ canonical
        geometric_gram = canonical.T @ kg_matrix @ canonical
        stiffness_error = float(
            np.max(np.abs(stiffness_gram - np.eye(requested)))
        )
        expected_geometric = np.diag(1.0 / value_array)
        geometric_scale = max(float(np.max(np.abs(expected_geometric))), 1.0)
        geometric_error = float(
            np.max(np.abs(geometric_gram - expected_geometric)) / geometric_scale
        )
        if (
            stiffness_error > orthogonality_tolerance
            or geometric_error > orthogonality_tolerance
        ):
            raise GeneralizedEigenContractError(
                "buckling orthogonality or geometric diagonalization gate failed"
            )
    except (GeneralizedEigenContractError, np.linalg.LinAlgError) as exc:
        raise BucklingAnalysisError(str(exc)) from exc

    return BucklingSolution(
        schema_version=BUCKLING_SOLUTION_SCHEMA_VERSION,
        dof_count=int(k_matrix.shape[0]),
        requested_mode_count=requested,
        mode_count=len(modes),
        finite_positive_eigenvalue_count=len(candidates),
        modes=tuple(modes),
        critical_load_factor=float(value_array[0]),
        stiffness_orthogonality_error_inf=stiffness_error,
        geometric_diagonalization_error_inf=geometric_error,
        stiffness_relative_symmetry_error=k_symmetry,
        geometric_stiffness_relative_symmetry_error=kg_symmetry,
        stiffness_minimum_eigenvalue=stiffness_minimum,
        geometric_stiffness_minimum_eigenvalue=geometric_minimum,
        geometric_stiffness_positive_rank=geometric_rank,
        stiffness_matrix_hash=matrix_sha256(k_matrix),
        geometric_stiffness_matrix_hash=matrix_sha256(kg_matrix),
        raw_result_hash=raw_modes_sha256(value_array.tolist(), canonical),
        semantic_result_hash=semantic_modes_sha256(value_array.tolist(), canonical),
        semantic_hash_profile=SEMANTIC_HASH_PROFILE,
        symmetry_projection_applied=bool(k_projected or kg_projected),
        regularization_applied=False,
        fallback_used=False,
        deterministic_mode_basis=True,
        contract_pass=True,
    )


def _mode_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BucklingAnalysisError("mode_count must be a positive integer")
    return value
