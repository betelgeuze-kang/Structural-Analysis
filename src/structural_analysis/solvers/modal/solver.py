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


MODAL_SOLUTION_SCHEMA_VERSION = "deterministic-modal-solution.v1"


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
    contract_pass: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def solve_modal_modes(
    stiffness: np.ndarray,
    mass: np.ndarray,
    *,
    mode_count: int,
    coordinate_recovery_scale: np.ndarray | None = None,
    symmetry_relative_tolerance: float = 1.0e-12,
    positive_semidefinite_relative_tolerance: float = 1.0e-12,
    rigid_mode_relative_tolerance: float = 1.0e-12,
    cluster_relative_tolerance: float = 1.0e-10,
    residual_relative_tolerance: float = 1.0e-10,
    orthogonality_tolerance: float = 1.0e-10,
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
        recovery_scale = _coordinate_recovery_scale(
            coordinate_recovery_scale,
            int(k_matrix.shape[0]),
        )
        solve_stiffness = (
            recovery_scale[:, None] * k_matrix * recovery_scale[None, :]
        )
        solve_mass = recovery_scale[:, None] * m_matrix * recovery_scale[None, :]
        if not (
            np.all(np.isfinite(solve_stiffness))
            and np.all(np.isfinite(solve_mass))
        ):
            raise GeneralizedEigenContractError(
                "coordinate-scaled modal matrices must be finite"
            )
        raw_values, raw_vectors = eigh(
            solve_stiffness,
            solve_mass,
            check_finite=False,
            driver="gvd",
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
        selected_vectors = np.asarray(raw_vectors[:, selected_indices], dtype=np.float64)
        canonical = np.empty_like(selected_vectors)
        for cluster in cluster_slices(
            selected_values,
            relative_tolerance=cluster_relative_tolerance,
        ):
            canonical[:, cluster] = canonicalize_eigenspace(
                selected_vectors[:, cluster],
                metric=solve_mass,
            )
        physical_modes = recovery_scale[:, None] * canonical
        values = np.asarray(
            [
                float(
                    physical_modes[:, index]
                    @ k_matrix
                    @ physical_modes[:, index]
                )
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
            vector = physical_modes[:, index]
            residual = k_matrix @ vector - eigenvalue * (m_matrix @ vector)
            denominator = max(
                float(np.linalg.norm(k_matrix @ vector, ord=np.inf))
                + abs(eigenvalue)
                * float(np.linalg.norm(m_matrix @ vector, ord=np.inf)),
                np.finfo(np.float64).tiny,
            )
            residual_relative = float(np.linalg.norm(residual, ord=np.inf)) / denominator
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
                )
            )
        mass_gram = physical_modes.T @ m_matrix @ physical_modes
        stiffness_gram = physical_modes.T @ k_matrix @ physical_modes
        mass_error = float(np.max(np.abs(mass_gram - np.eye(requested))))
        stiffness_scale = max(float(np.max(np.abs(values))), 1.0)
        stiffness_error = float(
            np.max(np.abs(stiffness_gram - np.diag(values))) / stiffness_scale
        )
        if mass_error > orthogonality_tolerance or stiffness_error > orthogonality_tolerance:
            raise GeneralizedEigenContractError(
                "modal orthogonality or stiffness diagonalization gate failed"
            )
    except (GeneralizedEigenContractError, np.linalg.LinAlgError) as exc:
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
        raw_result_hash=raw_modes_sha256(values.tolist(), physical_modes),
        semantic_result_hash=semantic_modes_sha256(
            values.tolist(),
            physical_modes,
        ),
        semantic_hash_profile=SEMANTIC_HASH_PROFILE,
        symmetry_projection_applied=bool(k_projected or m_projected),
        regularization_applied=False,
        fallback_used=False,
        deterministic_mode_basis=True,
        contract_pass=True,
    )


def _mode_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModalAnalysisError("mode_count must be a positive integer")
    return value


def _coordinate_recovery_scale(
    value: np.ndarray | None,
    size: int,
) -> np.ndarray:
    if value is None:
        return np.ones(size, dtype=np.float64)
    scale = np.asarray(value, dtype=np.float64)
    if (
        scale.shape != (size,)
        or not np.all(np.isfinite(scale))
        or np.any(scale <= 0.0)
    ):
        raise ModalAnalysisError(
            "coordinate_recovery_scale must be a finite positive DOF vector"
        )
    return scale
