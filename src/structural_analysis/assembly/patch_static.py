"""Narrow deterministic patch and rigid-body checks for Phase 2 evidence."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix


@dataclass(frozen=True)
class AxialPatchRigidBodyProblem:
    case_id: str
    node_coordinates_m: tuple[float, ...]
    elastic_modulus_kn_per_m2: float
    area_m2: float
    prescribed_strain: float
    rigid_translation_m: float


@dataclass(frozen=True)
class AxialPatchState:
    displacement_m: np.ndarray
    internal_forces_kn: np.ndarray
    external_forces_kn: np.ndarray
    residual_kn: np.ndarray
    element_strains: np.ndarray
    element_forces_kn: np.ndarray
    stiffness_kn_per_m: np.ndarray
    residual_formula: str = "F_internal_minus_F_external"


def default_axial_patch_rigidbody_problem() -> AxialPatchRigidBodyProblem:
    return AxialPatchRigidBodyProblem(
        case_id="phase2_axial_constant_strain_patch_and_rigidbody_seed",
        node_coordinates_m=(0.0, 1.0, 2.0),
        elastic_modulus_kn_per_m2=210_000_000.0,
        area_m2=0.012,
        prescribed_strain=1.25e-4,
        rigid_translation_m=0.375,
    )


def assemble_axial_patch_state(problem: AxialPatchRigidBodyProblem) -> AxialPatchState:
    coordinates = np.asarray(problem.node_coordinates_m, dtype=float)
    displacement = problem.prescribed_strain * coordinates
    stiffness = axial_patch_stiffness(problem)
    internal_forces = stiffness @ displacement
    element_strains, element_forces = axial_element_strains_and_forces(
        problem,
        displacement,
    )
    external_forces = np.zeros_like(internal_forces)
    external_forces[0] = internal_forces[0]
    external_forces[-1] = internal_forces[-1]
    residual = internal_forces - external_forces
    return AxialPatchState(
        displacement_m=displacement,
        internal_forces_kn=internal_forces,
        external_forces_kn=external_forces,
        residual_kn=residual,
        element_strains=element_strains,
        element_forces_kn=element_forces,
        stiffness_kn_per_m=stiffness,
    )


def axial_patch_stiffness(problem: AxialPatchRigidBodyProblem) -> np.ndarray:
    coordinates = np.asarray(problem.node_coordinates_m, dtype=float)
    if coordinates.ndim != 1 or coordinates.size < 2:
        raise ValueError("Axial patch problem requires at least two nodes.")
    if problem.elastic_modulus_kn_per_m2 <= 0.0:
        raise ValueError("Elastic modulus must be positive.")
    if problem.area_m2 <= 0.0:
        raise ValueError("Area must be positive.")
    if not np.all(np.diff(coordinates) > 0.0):
        raise ValueError("Axial patch coordinates must be strictly increasing.")

    stiffness = np.zeros((coordinates.size, coordinates.size), dtype=float)
    axial_rigidity = problem.elastic_modulus_kn_per_m2 * problem.area_m2
    for index, length in enumerate(np.diff(coordinates)):
        value = axial_rigidity / float(length)
        local = value * np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=float)
        stiffness[index : index + 2, index : index + 2] += local
    return stiffness


def axial_element_strains_and_forces(
    problem: AxialPatchRigidBodyProblem,
    displacement_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    coordinates = np.asarray(problem.node_coordinates_m, dtype=float)
    displacement = np.asarray(displacement_m, dtype=float)
    if displacement.shape != coordinates.shape:
        raise ValueError("Displacement vector must match patch node count.")
    lengths = np.diff(coordinates)
    strains = np.diff(displacement) / lengths
    element_forces = problem.elastic_modulus_kn_per_m2 * problem.area_m2 * strains
    return strains, element_forces


def rigid_body_nullspace_check(problem: AxialPatchRigidBodyProblem) -> dict[str, object]:
    stiffness = axial_patch_stiffness(problem)
    translation = np.full(
        len(problem.node_coordinates_m),
        problem.rigid_translation_m,
        dtype=float,
    )
    internal_forces = stiffness @ translation
    strains, element_forces = axial_element_strains_and_forces(problem, translation)
    dense_nullspace_norm = float(np.linalg.norm(internal_forces, ord=np.inf))
    sparse_internal = csr_matrix(stiffness) @ translation
    sparse_nullspace_norm = float(np.linalg.norm(sparse_internal, ord=np.inf))
    return {
        "rigid_translation_m": problem.rigid_translation_m,
        "element_strain_inf_norm": float(np.linalg.norm(strains, ord=np.inf)),
        "element_force_inf_norm_kn": float(np.linalg.norm(element_forces, ord=np.inf)),
        "dense_stiffness_times_translation_inf_norm_kn": dense_nullspace_norm,
        "sparse_stiffness_times_translation_inf_norm_kn": sparse_nullspace_norm,
        "stiffness_storage": "dense_numpy_and_scipy_sparse_csr",
        "pass": dense_nullspace_norm <= 1.0e-12
        and sparse_nullspace_norm <= 1.0e-12
        and float(np.linalg.norm(strains, ord=np.inf)) <= 1.0e-12,
    }

