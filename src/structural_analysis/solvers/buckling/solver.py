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
from structural_analysis.solvers.equation_scaling import (
    EquationScaling6DOFError,
    EquationScaling6DOFTransform,
    TRANSLATION_DOF_LABELS,
)


BUCKLING_SOLUTION_SCHEMA_VERSION = "deterministic-linear-buckling-solution.v2"


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
    raw_residual_relative_inf: float
    raw_translational_residual_norm: float | None
    raw_rotational_residual_norm: float | None
    scaled_residual_relative_inf: float | None


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
    equation_scaling_applied: bool
    equation_scaling_hash: str | None
    characteristic_length: float | None
    reference_force: float | None
    scaled_stiffness_condition_number: float | None
    scaled_geometric_stiffness_condition_number: float | None
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
    equation_scaling: EquationScaling6DOFTransform | None = None,
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
        solve_stiffness = k_matrix
        solve_geometric = kg_matrix
        scaled_projection_applied = False
        scaled_stiffness_condition: float | None = None
        scaled_geometric_condition: float | None = None
        if equation_scaling is not None:
            if not isinstance(equation_scaling, EquationScaling6DOFTransform):
                raise GeneralizedEigenContractError(
                    "equation_scaling must be an EquationScaling6DOFTransform"
                )
            if len(equation_scaling.dof_labels) != k_matrix.shape[0]:
                raise GeneralizedEigenContractError(
                    "equation_scaling order must match the buckling matrices"
                )
            scaled_stiffness = np.asarray(
                equation_scaling.scale_tangent(k_matrix),
                dtype=np.float64,
            )
            scaled_geometric = np.asarray(
                equation_scaling.scale_tangent(kg_matrix),
                dtype=np.float64,
            )
            solve_stiffness, _, scaled_k_projected = validate_symmetric(
                scaled_stiffness,
                name="scaled stiffness",
                relative_tolerance=symmetry_relative_tolerance,
            )
            solve_geometric, _, scaled_kg_projected = validate_symmetric(
                scaled_geometric,
                name="scaled geometric stiffness",
                relative_tolerance=symmetry_relative_tolerance,
            )
            require_positive_definite(
                solve_stiffness,
                name="scaled stiffness",
            )
            require_positive_semidefinite(
                solve_geometric,
                name="scaled geometric stiffness",
                relative_tolerance=positive_semidefinite_relative_tolerance,
            )
            scaled_projection_applied = bool(
                scaled_k_projected or scaled_kg_projected
            )
            scaled_stiffness_condition = _finite_condition_number(
                solve_stiffness
            )
            scaled_geometric_condition = _finite_condition_number(
                solve_geometric
            )
        raw_reciprocals, raw_vectors = eigh(
            solve_geometric,
            solve_stiffness,
            check_finite=False,
            driver="gvd",
        )
        physical_raw_vectors = (
            np.asarray(
                equation_scaling.increment_scales,
                dtype=np.float64,
            )[:, np.newaxis]
            * raw_vectors
            if equation_scaling is not None
            else raw_vectors
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
            vector = np.asarray(
                physical_raw_vectors[:, index],
                dtype=np.float64,
            )
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
            elastic_action = k_matrix @ vector
            geometric_action = kg_matrix @ vector
            residual = elastic_action - load_factor * geometric_action
            denominator = max(
                float(np.linalg.norm(elastic_action, ord=np.inf))
                + abs(load_factor)
                * float(np.linalg.norm(geometric_action, ord=np.inf)),
                np.finfo(np.float64).tiny,
            )
            raw_residual_relative = (
                float(np.linalg.norm(residual, ord=np.inf)) / denominator
            )
            (
                raw_translation_residual,
                raw_rotation_residual,
                scaled_residual_relative,
            ) = _scaled_residual_evidence(
                equation_scaling,
                residual=residual,
                first_action=elastic_action,
                second_action=load_factor * geometric_action,
            )
            residual_relative = (
                scaled_residual_relative
                if scaled_residual_relative is not None
                else raw_residual_relative
            )
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
                    raw_residual_relative_inf=raw_residual_relative,
                    raw_translational_residual_norm=raw_translation_residual,
                    raw_rotational_residual_norm=raw_rotation_residual,
                    scaled_residual_relative_inf=scaled_residual_relative,
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
    except (
        EquationScaling6DOFError,
        GeneralizedEigenContractError,
        np.linalg.LinAlgError,
    ) as exc:
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
        symmetry_projection_applied=bool(
            k_projected or kg_projected or scaled_projection_applied
        ),
        regularization_applied=False,
        fallback_used=False,
        deterministic_mode_basis=True,
        equation_scaling_applied=equation_scaling is not None,
        equation_scaling_hash=(
            equation_scaling.scaling_hash
            if equation_scaling is not None
            else None
        ),
        characteristic_length=(
            equation_scaling.characteristic_length
            if equation_scaling is not None
            else None
        ),
        reference_force=(
            equation_scaling.reference_force
            if equation_scaling is not None
            else None
        ),
        scaled_stiffness_condition_number=scaled_stiffness_condition,
        scaled_geometric_stiffness_condition_number=(
            scaled_geometric_condition
        ),
        contract_pass=True,
    )


def _scaled_residual_evidence(
    scaling: EquationScaling6DOFTransform | None,
    *,
    residual: np.ndarray,
    first_action: np.ndarray,
    second_action: np.ndarray,
) -> tuple[float | None, float | None, float | None]:
    if scaling is None:
        return None, None, None
    translation_mask = np.asarray(
        [
            label in TRANSLATION_DOF_LABELS
            for label in scaling.dof_labels
        ],
        dtype=bool,
    )
    rotation_mask = ~translation_mask
    translation_norm = _masked_inf_norm(residual, translation_mask)
    rotation_norm = _masked_inf_norm(residual, rotation_mask)
    scaled_residual = scaling.scale_residual(residual)
    scaled_first = scaling.scale_residual(first_action)
    scaled_second = scaling.scale_residual(second_action)
    denominator = max(
        _inf_norm(scaled_first) + _inf_norm(scaled_second),
        np.finfo(np.float64).tiny,
    )
    return (
        translation_norm,
        rotation_norm,
        _inf_norm(scaled_residual) / denominator,
    )


def _masked_inf_norm(values: np.ndarray, mask: np.ndarray) -> float:
    return _inf_norm(np.asarray(values, dtype=np.float64)[mask])


def _inf_norm(values: np.ndarray) -> float:
    vector = np.asarray(values, dtype=np.float64)
    return float(np.linalg.norm(vector, ord=np.inf)) if vector.size else 0.0


def _finite_condition_number(matrix: np.ndarray) -> float | None:
    condition = float(np.linalg.cond(matrix))
    return condition if math.isfinite(condition) and condition > 0.0 else None


def _mode_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BucklingAnalysisError("mode_count must be a positive integer")
    return value
