"""Deterministic modal generalized-eigen kernel for ``K phi = omega^2 M phi``."""

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


MODAL_SOLUTION_SCHEMA_VERSION = "deterministic-modal-solution.v2"


class ModalAnalysisError(GeneralizedEigenContractError):
    """Raised when a modal eigenproblem fails its strict contract."""


@dataclass(frozen=True)
class ModalMode:
    mode_number: int
    eigenvalue_rad2_per_s2: float
    omega_rad_per_s: float
    frequency_hz: float
    period_s: float
    mass_normalized_shape: tuple[float, ...]
    max_component_normalized_shape: tuple[float, ...]
    generalized_mass: float
    generalized_stiffness: float
    residual_relative_inf: float
    raw_residual_relative_inf: float
    raw_translational_residual_norm: float | None
    raw_rotational_residual_norm: float | None
    scaled_residual_relative_inf: float | None


@dataclass(frozen=True)
class ModalSolution:
    schema_version: str
    dof_count: int
    requested_mode_count: int
    mode_count: int
    rigid_mode_count: int
    modes: tuple[ModalMode, ...]
    mass_orthogonality_error_inf: float
    stiffness_diagonalization_error_inf: float
    stiffness_relative_symmetry_error: float
    mass_relative_symmetry_error: float
    stiffness_minimum_eigenvalue: float
    mass_minimum_eigenvalue: float
    stiffness_matrix_hash: str
    mass_matrix_hash: str
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
    scaled_mass_condition_number: float | None
    contract_pass: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def solve_modal_modes(
    stiffness: np.ndarray,
    mass: np.ndarray,
    *,
    mode_count: int,
    symmetry_relative_tolerance: float = 1.0e-12,
    positive_semidefinite_relative_tolerance: float = 1.0e-12,
    rigid_mode_relative_tolerance: float = 1.0e-12,
    cluster_relative_tolerance: float = 1.0e-10,
    residual_relative_tolerance: float = 1.0e-10,
    orthogonality_tolerance: float = 1.0e-10,
    equation_scaling: EquationScaling6DOFTransform | None = None,
) -> ModalSolution:
    """Solve a strict symmetric modal problem without regularization or fallback."""

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
        rigid_mode_relative_tolerance = require_nonnegative_tolerance(
            rigid_mode_relative_tolerance,
            name="rigid_mode_relative_tolerance",
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
        m_input = as_binary64_square(mass, name="mass")
        if k_input.shape != m_input.shape:
            raise GeneralizedEigenContractError(
                "stiffness and mass matrices must have the same shape"
            )
        k_matrix, k_symmetry, k_projected = validate_symmetric(
            k_input,
            name="stiffness",
            relative_tolerance=symmetry_relative_tolerance,
        )
        m_matrix, m_symmetry, m_projected = validate_symmetric(
            m_input,
            name="mass",
            relative_tolerance=symmetry_relative_tolerance,
        )
        mass_minimum = require_positive_definite(m_matrix, name="mass")
        stiffness_minimum, _ = require_positive_semidefinite(
            k_matrix,
            name="stiffness",
            relative_tolerance=positive_semidefinite_relative_tolerance,
        )
        solve_stiffness = k_matrix
        solve_mass = m_matrix
        scaled_projection_applied = False
        scaled_stiffness_condition: float | None = None
        scaled_mass_condition: float | None = None
        if equation_scaling is not None:
            if not isinstance(equation_scaling, EquationScaling6DOFTransform):
                raise GeneralizedEigenContractError(
                    "equation_scaling must be an EquationScaling6DOFTransform"
                )
            if len(equation_scaling.dof_labels) != k_matrix.shape[0]:
                raise GeneralizedEigenContractError(
                    "equation_scaling order must match the modal matrices"
                )
            scaled_stiffness = np.asarray(
                equation_scaling.scale_tangent(k_matrix),
                dtype=np.float64,
            )
            scaled_mass = np.asarray(
                equation_scaling.scale_tangent(m_matrix),
                dtype=np.float64,
            )
            solve_stiffness, _, scaled_k_projected = validate_symmetric(
                scaled_stiffness,
                name="scaled stiffness",
                relative_tolerance=symmetry_relative_tolerance,
            )
            solve_mass, _, scaled_m_projected = validate_symmetric(
                scaled_mass,
                name="scaled mass",
                relative_tolerance=symmetry_relative_tolerance,
            )
            require_positive_definite(solve_mass, name="scaled mass")
            require_positive_semidefinite(
                solve_stiffness,
                name="scaled stiffness",
                relative_tolerance=positive_semidefinite_relative_tolerance,
            )
            scaled_projection_applied = bool(
                scaled_k_projected or scaled_m_projected
            )
            scaled_stiffness_condition = _finite_condition_number(
                solve_stiffness
            )
            scaled_mass_condition = _finite_condition_number(solve_mass)
        raw_values, raw_vectors = eigh(
            solve_stiffness,
            solve_mass,
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
        spectral_scale = max(float(np.max(np.abs(raw_values))), 1.0)
        rigid_threshold = rigid_mode_relative_tolerance * spectral_scale
        rigid_count = int(np.count_nonzero(raw_values <= rigid_threshold))
        indices = np.flatnonzero(raw_values > rigid_threshold)
        if indices.size < requested:
            raise GeneralizedEigenContractError(
                f"requested {requested} positive modes but only {indices.size} are available"
            )
        positive_values = np.asarray(raw_values[indices], dtype=np.float64)
        require_complete_cluster_selection(
            positive_values,
            selected_count=requested,
            relative_tolerance=cluster_relative_tolerance,
        )
        selected_indices = indices[:requested]
        selected_values = np.asarray(raw_values[selected_indices], dtype=np.float64)
        selected_vectors = np.asarray(
            physical_raw_vectors[:, selected_indices],
            dtype=np.float64,
        )
        canonical = np.empty_like(selected_vectors)
        for cluster in cluster_slices(
            selected_values,
            relative_tolerance=cluster_relative_tolerance,
        ):
            canonical[:, cluster] = canonicalize_eigenspace(
                selected_vectors[:, cluster],
                metric=m_matrix,
            )
        values = np.asarray(
            [
                float(canonical[:, index] @ k_matrix @ canonical[:, index])
                for index in range(requested)
            ],
            dtype=np.float64,
        )
        modes: list[ModalMode] = []
        for index, eigenvalue in enumerate(values.tolist()):
            if not math.isfinite(eigenvalue) or eigenvalue <= 0.0:
                raise GeneralizedEigenContractError(
                    f"mode {index + 1} has a non-positive Rayleigh eigenvalue"
                )
            vector = canonical[:, index]
            stiffness_action = k_matrix @ vector
            mass_action = m_matrix @ vector
            residual = stiffness_action - eigenvalue * mass_action
            denominator = max(
                float(np.linalg.norm(stiffness_action, ord=np.inf))
                + abs(eigenvalue) * float(np.linalg.norm(mass_action, ord=np.inf)),
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
                first_action=stiffness_action,
                second_action=eigenvalue * mass_action,
            )
            residual_relative = (
                scaled_residual_relative
                if scaled_residual_relative is not None
                else raw_residual_relative
            )
            if residual_relative > residual_relative_tolerance:
                raise GeneralizedEigenContractError(
                    f"mode {index + 1} residual {residual_relative:.17g} exceeds "
                    f"{residual_relative_tolerance:.17g}"
                )
            omega = math.sqrt(eigenvalue)
            modes.append(
                ModalMode(
                    mode_number=index + 1,
                    eigenvalue_rad2_per_s2=eigenvalue,
                    omega_rad_per_s=omega,
                    frequency_hz=omega / (2.0 * math.pi),
                    period_s=(2.0 * math.pi) / omega,
                    mass_normalized_shape=tuple(float(value) for value in vector.tolist()),
                    max_component_normalized_shape=max_component_normalized(vector),
                    generalized_mass=float(vector @ m_matrix @ vector),
                    generalized_stiffness=float(vector @ k_matrix @ vector),
                    residual_relative_inf=residual_relative,
                    raw_residual_relative_inf=raw_residual_relative,
                    raw_translational_residual_norm=raw_translation_residual,
                    raw_rotational_residual_norm=raw_rotation_residual,
                    scaled_residual_relative_inf=scaled_residual_relative,
                )
            )
        mass_gram = canonical.T @ m_matrix @ canonical
        stiffness_gram = canonical.T @ k_matrix @ canonical
        mass_error = float(np.max(np.abs(mass_gram - np.eye(requested))))
        stiffness_scale = max(float(np.max(np.abs(values))), 1.0)
        stiffness_error = float(
            np.max(np.abs(stiffness_gram - np.diag(values))) / stiffness_scale
        )
        if mass_error > orthogonality_tolerance or stiffness_error > orthogonality_tolerance:
            raise GeneralizedEigenContractError(
                "modal orthogonality or stiffness diagonalization gate failed"
            )
    except (
        EquationScaling6DOFError,
        GeneralizedEigenContractError,
        np.linalg.LinAlgError,
    ) as exc:
        raise ModalAnalysisError(str(exc)) from exc

    return ModalSolution(
        schema_version=MODAL_SOLUTION_SCHEMA_VERSION,
        dof_count=int(k_matrix.shape[0]),
        requested_mode_count=requested,
        mode_count=len(modes),
        rigid_mode_count=rigid_count,
        modes=tuple(modes),
        mass_orthogonality_error_inf=mass_error,
        stiffness_diagonalization_error_inf=stiffness_error,
        stiffness_relative_symmetry_error=k_symmetry,
        mass_relative_symmetry_error=m_symmetry,
        stiffness_minimum_eigenvalue=stiffness_minimum,
        mass_minimum_eigenvalue=mass_minimum,
        stiffness_matrix_hash=matrix_sha256(k_matrix),
        mass_matrix_hash=matrix_sha256(m_matrix),
        raw_result_hash=raw_modes_sha256(values.tolist(), canonical),
        semantic_result_hash=semantic_modes_sha256(values.tolist(), canonical),
        semantic_hash_profile=SEMANTIC_HASH_PROFILE,
        symmetry_projection_applied=bool(
            k_projected or m_projected or scaled_projection_applied
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
        scaled_mass_condition_number=scaled_mass_condition,
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
        raise ModalAnalysisError("mode_count must be a positive integer")
    return value
