"""Bounded dense linear-static solver for three-node shell meshes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any, Sequence

import numpy as np

from structural_analysis.elements.shell_triangle import recover_shell_triangle, shell_triangle_matrices
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


SHELL_STATIC_PROFILE = "linear_cst_membrane_mindlin_triangle_shell.v1"
SHELL_STATIC_SCHEMA_VERSION = "shell-static-solution.v1"
SHELL_CHECKPOINT_SCHEMA_VERSION = "shell-static-checkpoint.v1"
_ZERO_HASH = "sha256:" + "0" * 64


class ShellStaticError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShellStaticModel:
    model_id: str
    node_ids: tuple[str, ...]
    node_coordinates_m: tuple[tuple[float, float, float], ...]
    element_ids: tuple[str, ...]
    element_connectivity: tuple[tuple[int, int, int], ...]
    elastic_modulus_pa: float
    poisson_ratio: float
    thickness_m: float
    restrained_dofs: tuple[int, ...]
    load_global_n_nm: tuple[float, ...]

    def __init__(
        self, *, model_id: str, node_ids: Sequence[str],
        node_coordinates_m: Sequence[Sequence[float]], element_ids: Sequence[str],
        element_connectivity: Sequence[Sequence[int]], elastic_modulus_pa: float,
        poisson_ratio: float, thickness_m: float, restrained_dofs: Sequence[int],
        load_global_n_nm: Sequence[float],
    ) -> None:
        ids = tuple(map(str, node_ids)); coordinates = np.asarray(node_coordinates_m, dtype=np.float64)
        elements = tuple(tuple(map(int, row)) for row in element_connectivity)
        element_names = tuple(map(str, element_ids)); dof_count = 6 * len(ids)
        load = np.asarray(load_global_n_nm, dtype=np.float64)
        restraints = tuple(sorted(set(map(int, restrained_dofs))))
        if len(ids) < 3 or len(set(ids)) != len(ids) or coordinates.shape != (len(ids), 3):
            raise ValueError("shell node identity/coordinates are invalid")
        if len(elements) < 1 or len(element_names) != len(elements) or len(set(element_names)) != len(element_names):
            raise ValueError("shell element identity is invalid")
        if any(len(row) != 3 or len(set(row)) != 3 or min(row) < 0 or max(row) >= len(ids) for row in elements):
            raise ValueError("shell connectivity is invalid")
        if load.shape != (dof_count,) or not np.all(np.isfinite(load)):
            raise ValueError("shell load vector is invalid")
        if not restraints or min(restraints) < 0 or max(restraints) >= dof_count:
            raise ValueError("shell restraints are invalid")
        object.__setattr__(self, "model_id", str(model_id)); object.__setattr__(self, "node_ids", ids)
        object.__setattr__(self, "node_coordinates_m", tuple(map(tuple, coordinates.tolist())))
        object.__setattr__(self, "element_ids", element_names); object.__setattr__(self, "element_connectivity", elements)
        object.__setattr__(self, "elastic_modulus_pa", float(elastic_modulus_pa)); object.__setattr__(self, "poisson_ratio", float(poisson_ratio)); object.__setattr__(self, "thickness_m", float(thickness_m))
        object.__setattr__(self, "restrained_dofs", restraints); object.__setattr__(self, "load_global_n_nm", tuple(map(float, load)))

    @property
    def dof_count(self) -> int:
        return 6 * len(self.node_ids)

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return asdict(self) | {"profile": SHELL_STATIC_PROFILE}


@dataclass(frozen=True)
class ShellElementResult:
    element_id: str
    membrane_strain: tuple[float, float, float]
    membrane_resultant_n_per_m: tuple[float, float, float]
    curvature_per_m: tuple[float, float, float]
    bending_resultant_nm_per_m: tuple[float, float, float]
    transverse_shear_strain: tuple[float, float]
    transverse_shear_resultant_n_per_m: tuple[float, float]
    strain_energy_j: float


@dataclass(frozen=True)
class ShellStaticCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    stiffness_hash: str
    load_hash: str
    displacement_global: tuple[float, ...]
    reaction_global_n_nm: tuple[float, ...]
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShellStaticSolution:
    schema_version: str
    profile: str
    model_hash: str
    stiffness_hash: str
    load_hash: str
    displacement_global: tuple[float, ...]
    reaction_global_n_nm: tuple[float, ...]
    equilibrium_residual_global_n_nm: tuple[float, ...]
    element_results: tuple[ShellElementResult, ...]
    free_dof_count: int
    maximum_free_residual: float
    strain_energy_j: float
    external_work_j: float
    checkpoint: ShellStaticCheckpoint
    result_hash: str
    fallback_used: bool
    regularization_used: bool
    contract_pass: bool


def _assemble(model: ShellStaticModel) -> tuple[np.ndarray, tuple[Any, ...]]:
    stiffness = np.zeros((model.dof_count, model.dof_count), dtype=np.float64)
    element_matrices = []
    coordinates = np.asarray(model.node_coordinates_m)
    for connectivity in model.element_connectivity:
        matrices = shell_triangle_matrices(
            coordinates[list(connectivity)], elastic_modulus_pa=model.elastic_modulus_pa,
            poisson_ratio=model.poisson_ratio, thickness_m=model.thickness_m,
        )
        dofs = [6 * node + component for node in connectivity for component in range(6)]
        stiffness[np.ix_(dofs, dofs)] += matrices.stiffness_n_per_m
        element_matrices.append((matrices, tuple(dofs)))
    return 0.5 * (stiffness + stiffness.T), tuple(element_matrices)


def solve_shell_static(model: ShellStaticModel) -> ShellStaticSolution:
    stiffness, element_matrices = _assemble(model); load = np.asarray(model.load_global_n_nm)
    restrained = set(model.restrained_dofs); free = np.asarray([index for index in range(model.dof_count) if index not in restrained], dtype=np.int64)
    if free.size == 0:
        raise ShellStaticError("shell model has no free equations")
    reduced = stiffness[np.ix_(free, free)]
    if np.linalg.matrix_rank(reduced) != reduced.shape[0]:
        raise ShellStaticError("shell reduced stiffness is singular; no regularization is allowed")
    displacement = np.zeros(model.dof_count); displacement[free] = np.linalg.solve(reduced, load[free])
    residual = stiffness @ displacement - load
    scale = max(float(np.max(np.abs(load[free]))), 1.0)
    maximum_free_residual = float(np.max(np.abs(residual[free])))
    if maximum_free_residual / scale > 1.0e-10:
        raise ShellStaticError("shell physical residual gate failed")
    reactions = np.zeros(model.dof_count); reactions[list(restrained)] = residual[list(restrained)]
    results = []
    for element_id, (matrices, dofs) in zip(model.element_ids, element_matrices, strict=True):
        recovered = recover_shell_triangle(matrices, displacement[list(dofs)])
        results.append(ShellElementResult(element_id=element_id, **asdict(recovered)))
    stiffness_hash = canonical_hash(stiffness.tolist()); load_hash = canonical_hash(load.tolist())
    checkpoint0 = ShellStaticCheckpoint(
        SHELL_CHECKPOINT_SCHEMA_VERSION, SHELL_STATIC_PROFILE, model.model_hash,
        stiffness_hash, load_hash, tuple(map(float, displacement)), tuple(map(float, reactions)), _ZERO_HASH,
    )
    checkpoint_payload = checkpoint0.to_dict(); checkpoint_payload.pop("checkpoint_hash")
    checkpoint = replace(checkpoint0, checkpoint_hash=canonical_hash(checkpoint_payload))
    strain_energy = 0.5 * float(displacement @ stiffness @ displacement)
    external_work = 0.5 * float(displacement @ load)
    provisional = ShellStaticSolution(
        SHELL_STATIC_SCHEMA_VERSION, SHELL_STATIC_PROFILE, model.model_hash,
        stiffness_hash, load_hash, tuple(map(float, displacement)), tuple(map(float, reactions)),
        tuple(map(float, residual)), tuple(results), int(free.size), maximum_free_residual,
        strain_energy, external_work, checkpoint, _ZERO_HASH, False, False, True,
    )
    payload = asdict(provisional); payload.pop("result_hash")
    return replace(provisional, result_hash=canonical_hash(payload))


def resume_shell_static(model: ShellStaticModel, checkpoint: ShellStaticCheckpoint) -> ShellStaticSolution:
    if checkpoint.schema_version != SHELL_CHECKPOINT_SCHEMA_VERSION or checkpoint.profile != SHELL_STATIC_PROFILE or checkpoint.model_hash != model.model_hash:
        raise ShellStaticError("shell checkpoint binding mismatch")
    payload = checkpoint.to_dict(); claimed = payload.pop("checkpoint_hash")
    if canonical_hash(payload) != claimed:
        raise ShellStaticError("shell checkpoint hash mismatch")
    replay = solve_shell_static(model)
    if replay.checkpoint != checkpoint:
        raise ShellStaticError("shell checkpoint exact replay mismatch")
    return replay


__all__ = [
    "SHELL_CHECKPOINT_SCHEMA_VERSION", "SHELL_STATIC_PROFILE", "SHELL_STATIC_SCHEMA_VERSION",
    "ShellElementResult", "ShellStaticCheckpoint", "ShellStaticError", "ShellStaticModel",
    "ShellStaticSolution", "resume_shell_static", "solve_shell_static",
]
