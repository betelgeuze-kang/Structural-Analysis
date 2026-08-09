"""Deterministic matrix Newmark solver for bounded linear MDOF transients."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any, Sequence

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


LINEAR_MDOF_TRANSIENT_PROFILE = "newmark_average_acceleration_linear_mdof.v1"
LINEAR_MDOF_TRANSIENT_SCHEMA_VERSION = "linear-mdof-transient-solution.v1"
LINEAR_MDOF_CHECKPOINT_SCHEMA_VERSION = "linear-mdof-transient-checkpoint.v1"
LINEAR_MDOF_AUTHORITY_SCHEMA_VERSION = "linear-mdof-checkpoint-authority.v1"
_ZERO_HASH = "sha256:" + "0" * 64


class LinearMDOFTransientError(RuntimeError):
    """Fail-closed MDOF input, solve, or checkpoint error."""


def _vector(values: Sequence[float] | np.ndarray, *, size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite vector of length {size}")
    return array


def _matrix(values: Sequence[Sequence[float]] | np.ndarray, *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] != array.shape[1] or array.shape[0] < 2:
        raise ValueError(f"{name} must be a square matrix with dimension >= 2")
    if not np.all(np.isfinite(array)) or not np.array_equal(array, array.T):
        raise ValueError(f"{name} must be finite and exactly symmetric")
    return array


def _tuples(array: np.ndarray) -> tuple[float, ...]:
    return tuple(float(value) for value in array)


@dataclass(frozen=True)
class LinearMDOFSystem:
    mass_matrix_kg: tuple[tuple[float, ...], ...]
    damping_matrix_n_s_per_m: tuple[tuple[float, ...], ...]
    stiffness_matrix_n_per_m: tuple[tuple[float, ...], ...]
    dof_ids: tuple[str, ...]
    model_id: str = "linear_mdof"

    def __init__(
        self,
        mass_matrix_kg: Sequence[Sequence[float]] | np.ndarray,
        damping_matrix_n_s_per_m: Sequence[Sequence[float]] | np.ndarray,
        stiffness_matrix_n_per_m: Sequence[Sequence[float]] | np.ndarray,
        dof_ids: Sequence[str],
        model_id: str = "linear_mdof",
    ) -> None:
        mass = _matrix(mass_matrix_kg, name="mass_matrix_kg")
        damping = _matrix(damping_matrix_n_s_per_m, name="damping_matrix_n_s_per_m")
        stiffness = _matrix(stiffness_matrix_n_per_m, name="stiffness_matrix_n_per_m")
        if damping.shape != mass.shape or stiffness.shape != mass.shape:
            raise ValueError("MDOF matrices must have identical dimensions")
        if np.min(np.linalg.eigvalsh(mass)) <= 0.0:
            raise ValueError("mass_matrix_kg must be positive definite")
        if np.min(np.linalg.eigvalsh(stiffness)) <= 0.0:
            raise ValueError("stiffness_matrix_n_per_m must be positive definite")
        if np.min(np.linalg.eigvalsh(damping)) < -1.0e-12:
            raise ValueError("damping_matrix_n_s_per_m must be positive semidefinite")
        ids = tuple(str(value) for value in dof_ids)
        if len(ids) != mass.shape[0] or len(set(ids)) != len(ids) or any(not value for value in ids):
            raise ValueError("dof_ids must be unique and match the matrix dimension")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("model_id must be nonempty")
        object.__setattr__(self, "mass_matrix_kg", tuple(map(tuple, mass.tolist())))
        object.__setattr__(self, "damping_matrix_n_s_per_m", tuple(map(tuple, damping.tolist())))
        object.__setattr__(self, "stiffness_matrix_n_per_m", tuple(map(tuple, stiffness.tolist())))
        object.__setattr__(self, "dof_ids", ids)
        object.__setattr__(self, "model_id", model_id)

    @property
    def dimension(self) -> int:
        return len(self.dof_ids)

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.asarray(self.mass_matrix_kg, dtype=np.float64),
            np.asarray(self.damping_matrix_n_s_per_m, dtype=np.float64),
            np.asarray(self.stiffness_matrix_n_per_m, dtype=np.float64),
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "dof_ids": list(self.dof_ids),
            "mass_matrix_kg": [list(row) for row in self.mass_matrix_kg],
            "damping_matrix_n_s_per_m": [list(row) for row in self.damping_matrix_n_s_per_m],
            "stiffness_matrix_n_per_m": [list(row) for row in self.stiffness_matrix_n_per_m],
        }


@dataclass(frozen=True)
class LinearMDOFTransientConfig:
    time_step_s: float
    residual_relative_tolerance: float = 1.0e-10
    residual_absolute_tolerance_n: float = 1.0e-9
    newmark_beta: float = 0.25
    newmark_gamma: float = 0.5

    def __post_init__(self) -> None:
        for name in ("time_step_s", "residual_relative_tolerance", "residual_absolute_tolerance_n"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
            object.__setattr__(self, name, value)
        if float(self.newmark_beta) != 0.25 or float(self.newmark_gamma) != 0.5:
            raise ValueError("v1 requires Newmark average acceleration beta=0.25, gamma=0.5")

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": LINEAR_MDOF_TRANSIENT_PROFILE,
            "time_step_s": self.time_step_s,
            "residual_relative_tolerance": self.residual_relative_tolerance,
            "residual_absolute_tolerance_n": self.residual_absolute_tolerance_n,
            "newmark_beta": self.newmark_beta,
            "newmark_gamma": self.newmark_gamma,
            "fallback_allowed": False,
            "regularization_allowed": False,
        }


@dataclass(frozen=True)
class LinearMDOFCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    integration_contract_hash: str
    step_index: int
    time_s: float
    applied_force_n: tuple[float, ...]
    displacement_m: tuple[float, ...]
    velocity_m_per_s: tuple[float, ...]
    acceleration_m_per_s2: tuple[float, ...]
    external_work_j: float
    damping_dissipation_j: float
    initial_mechanical_energy_j: float
    parent_checkpoint_hash: str | None
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LinearMDOFStep:
    step_index: int
    time_s: float
    applied_force_n: tuple[float, ...]
    displacement_m: tuple[float, ...]
    velocity_m_per_s: tuple[float, ...]
    acceleration_m_per_s2: tuple[float, ...]
    restoring_force_n: tuple[float, ...]
    damping_force_n: tuple[float, ...]
    inertia_force_n: tuple[float, ...]
    equilibrium_residual_n: tuple[float, ...]
    relative_residual: float
    kinetic_energy_j: float
    strain_energy_j: float
    external_work_j: float
    damping_dissipation_j: float
    energy_balance_error_j: float
    linear_solve_count: int
    checkpoint_hash: str
    parent_checkpoint_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LinearMDOFSolution:
    schema_version: str
    profile: str
    model_hash: str
    integration_contract_hash: str
    start_step_index: int
    end_step_index: int
    steps: tuple[LinearMDOFStep, ...]
    checkpoints: tuple[LinearMDOFCheckpoint, ...]
    maximum_relative_residual: float
    maximum_absolute_energy_balance_error_j: float
    linear_solve_count: int
    result_hash: str
    deterministic: bool
    exact_checkpoint_resume_supported: bool
    regularization_used: bool
    fallback_used: bool
    contract_pass: bool


@dataclass(frozen=True)
class LinearMDOFCheckpointAuthority:
    schema_version: str
    checkpoint_hash: str
    source_authenticated_checkpoint: bool
    parent_chain_complete: bool
    force_history_hash: str
    force_history_sample_count: int
    dynamic_equilibrium_replay_pass: bool
    newmark_kinematic_replay_pass: bool
    energy_replay_pass: bool
    deterministic_checkpoint_replay_pass: bool
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        claimed = payload.pop("receipt_hash")
        if canonical_hash(payload) != claimed:
            raise LinearMDOFTransientError("checkpoint authority receipt hash mismatch")
        payload["receipt_hash"] = claimed
        return payload


def _checkpoint(
    *, system: LinearMDOFSystem, config: LinearMDOFTransientConfig, step_index: int,
    force: np.ndarray, displacement: np.ndarray, velocity: np.ndarray,
    acceleration: np.ndarray, external_work: float, damping_dissipation: float,
    initial_mechanical_energy: float, parent_hash: str | None,
) -> LinearMDOFCheckpoint:
    provisional = LinearMDOFCheckpoint(
        schema_version=LINEAR_MDOF_CHECKPOINT_SCHEMA_VERSION,
        profile=LINEAR_MDOF_TRANSIENT_PROFILE,
        model_hash=system.model_hash,
        integration_contract_hash=config.contract_hash,
        step_index=step_index,
        time_s=step_index * config.time_step_s,
        applied_force_n=_tuples(force), displacement_m=_tuples(displacement),
        velocity_m_per_s=_tuples(velocity), acceleration_m_per_s2=_tuples(acceleration),
        external_work_j=float(external_work), damping_dissipation_j=float(damping_dissipation),
        initial_mechanical_energy_j=float(initial_mechanical_energy),
        parent_checkpoint_hash=parent_hash, checkpoint_hash=_ZERO_HASH,
    )
    return replace(provisional, checkpoint_hash=canonical_hash({k: v for k, v in provisional.to_dict().items() if k != "checkpoint_hash"}))


def _step_from_checkpoint(
    checkpoint: LinearMDOFCheckpoint, *, system: LinearMDOFSystem,
    relative_residual: float, energy_error: float, linear_solve_count: int,
) -> LinearMDOFStep:
    mass, damping, stiffness = system.arrays()
    u = np.asarray(checkpoint.displacement_m)
    v = np.asarray(checkpoint.velocity_m_per_s)
    a = np.asarray(checkpoint.acceleration_m_per_s2)
    force = np.asarray(checkpoint.applied_force_n)
    restoring = stiffness @ u
    damping_force = damping @ v
    inertia = mass @ a
    return LinearMDOFStep(
        step_index=checkpoint.step_index, time_s=checkpoint.time_s,
        applied_force_n=checkpoint.applied_force_n,
        displacement_m=checkpoint.displacement_m,
        velocity_m_per_s=checkpoint.velocity_m_per_s,
        acceleration_m_per_s2=checkpoint.acceleration_m_per_s2,
        restoring_force_n=_tuples(restoring), damping_force_n=_tuples(damping_force),
        inertia_force_n=_tuples(inertia),
        equilibrium_residual_n=_tuples(force - inertia - damping_force - restoring),
        relative_residual=float(relative_residual),
        kinetic_energy_j=float(0.5 * v @ mass @ v),
        strain_energy_j=float(0.5 * u @ stiffness @ u),
        external_work_j=checkpoint.external_work_j,
        damping_dissipation_j=checkpoint.damping_dissipation_j,
        energy_balance_error_j=float(energy_error), linear_solve_count=linear_solve_count,
        checkpoint_hash=checkpoint.checkpoint_hash,
        parent_checkpoint_hash=checkpoint.parent_checkpoint_hash,
    )


def solve_linear_mdof_transient(
    system: LinearMDOFSystem,
    force_history_n: Sequence[Sequence[float]] | np.ndarray,
    *, config: LinearMDOFTransientConfig,
    initial_displacement_m: Sequence[float] | np.ndarray | None = None,
    initial_velocity_m_per_s: Sequence[float] | np.ndarray | None = None,
) -> LinearMDOFSolution:
    forces = np.asarray(force_history_n, dtype=np.float64)
    if forces.ndim != 2 or forces.shape[0] < 1 or forces.shape[1] != system.dimension or not np.all(np.isfinite(forces)):
        raise ValueError("force_history_n must be a finite [sample, dof] matrix")
    zero = np.zeros(system.dimension, dtype=np.float64)
    u = _vector(initial_displacement_m if initial_displacement_m is not None else zero, size=system.dimension, name="initial_displacement_m")
    v = _vector(initial_velocity_m_per_s if initial_velocity_m_per_s is not None else zero, size=system.dimension, name="initial_velocity_m_per_s")
    mass, damping, stiffness = system.arrays()
    a = np.linalg.solve(mass, forces[0] - damping @ v - stiffness @ u)
    initial_energy = float(0.5 * v @ mass @ v + 0.5 * u @ stiffness @ u)
    checkpoint0 = _checkpoint(system=system, config=config, step_index=0, force=forces[0], displacement=u, velocity=v, acceleration=a, external_work=0.0, damping_dissipation=0.0, initial_mechanical_energy=initial_energy, parent_hash=None)
    return _advance(system, config, checkpoint0, forces[1:], include_start=True)


def resume_linear_mdof_transient(
    system: LinearMDOFSystem,
    checkpoint: LinearMDOFCheckpoint,
    future_force_history_n: Sequence[Sequence[float]] | np.ndarray,
    *, config: LinearMDOFTransientConfig,
    checkpoint_chain: Sequence[LinearMDOFCheckpoint],
    force_history_prefix_n: Sequence[Sequence[float]] | np.ndarray,
) -> LinearMDOFSolution:
    validate_linear_mdof_checkpoint_authority(
        checkpoint, system=system, config=config, checkpoint_chain=checkpoint_chain,
        force_history_prefix_n=force_history_prefix_n,
    )
    future = np.asarray(future_force_history_n, dtype=np.float64)
    if future.ndim != 2 or future.shape[1] != system.dimension:
        raise ValueError("future_force_history_n dimension mismatch")
    return _advance(system, config, checkpoint, future, include_start=True)


def _advance(
    system: LinearMDOFSystem, config: LinearMDOFTransientConfig,
    start: LinearMDOFCheckpoint, future_forces: np.ndarray, *, include_start: bool,
) -> LinearMDOFSolution:
    mass, damping, stiffness = system.arrays()
    dt = config.time_step_s
    beta, gamma = config.newmark_beta, config.newmark_gamma
    c0 = 1.0 / (beta * dt * dt)
    c1 = gamma / (beta * dt)
    effective = stiffness + c1 * damping + c0 * mass
    u = np.asarray(start.displacement_m, dtype=np.float64)
    v = np.asarray(start.velocity_m_per_s, dtype=np.float64)
    a = np.asarray(start.acceleration_m_per_s2, dtype=np.float64)
    previous_force = np.asarray(start.applied_force_n, dtype=np.float64)
    external_work = start.external_work_j
    damping_dissipation = start.damping_dissipation_j
    initial_energy = start.initial_mechanical_energy_j
    checkpoints = [start] if include_start else []
    start_energy = 0.5 * v @ mass @ v + 0.5 * u @ stiffness @ u
    start_error = external_work + initial_energy - start_energy - damping_dissipation
    steps = [_step_from_checkpoint(start, system=system, relative_residual=0.0, energy_error=float(start_error), linear_solve_count=0)] if include_start else []
    parent_hash = start.checkpoint_hash
    solve_count = 0
    for offset, force in enumerate(np.asarray(future_forces, dtype=np.float64), start=1):
        step_index = start.step_index + offset
        rhs = (
            force
            + mass @ (c0 * u + (1.0 / (beta * dt)) * v + (1.0 / (2.0 * beta) - 1.0) * a)
            + damping @ (c1 * u + (gamma / beta - 1.0) * v + dt * (gamma / (2.0 * beta) - 1.0) * a)
        )
        new_u = np.linalg.solve(effective, rhs)
        solve_count += 1
        new_a = c0 * (new_u - u) - (1.0 / (beta * dt)) * v - (1.0 / (2.0 * beta) - 1.0) * a
        new_v = v + dt * ((1.0 - gamma) * a + gamma * new_a)
        residual = force - mass @ new_a - damping @ new_v - stiffness @ new_u
        denominator = max(float(np.linalg.norm(force)), float(np.linalg.norm(mass @ new_a) + np.linalg.norm(damping @ new_v) + np.linalg.norm(stiffness @ new_u)), 1.0)
        relative = float(np.linalg.norm(residual) / denominator)
        if float(np.linalg.norm(residual)) > config.residual_absolute_tolerance_n and relative > config.residual_relative_tolerance:
            raise LinearMDOFTransientError(f"dynamic residual gate failed at step {step_index}")
        delta_u = new_u - u
        external_work += float(0.5 * (previous_force + force) @ delta_u)
        damping_dissipation += float(0.5 * dt * (v @ damping @ v + new_v @ damping @ new_v))
        mechanical = float(0.5 * new_v @ mass @ new_v + 0.5 * new_u @ stiffness @ new_u)
        energy_error = external_work + initial_energy - mechanical - damping_dissipation
        checkpoint = _checkpoint(
            system=system, config=config, step_index=step_index, force=force,
            displacement=new_u, velocity=new_v, acceleration=new_a,
            external_work=external_work, damping_dissipation=damping_dissipation,
            initial_mechanical_energy=initial_energy, parent_hash=parent_hash,
        )
        checkpoints.append(checkpoint)
        steps.append(_step_from_checkpoint(checkpoint, system=system, relative_residual=relative, energy_error=energy_error, linear_solve_count=1))
        u, v, a, previous_force = new_u, new_v, new_a, force
        parent_hash = checkpoint.checkpoint_hash
    provisional = LinearMDOFSolution(
        schema_version=LINEAR_MDOF_TRANSIENT_SCHEMA_VERSION,
        profile=LINEAR_MDOF_TRANSIENT_PROFILE,
        model_hash=system.model_hash, integration_contract_hash=config.contract_hash,
        start_step_index=start.step_index, end_step_index=checkpoints[-1].step_index,
        steps=tuple(steps), checkpoints=tuple(checkpoints),
        maximum_relative_residual=max((step.relative_residual for step in steps), default=0.0),
        maximum_absolute_energy_balance_error_j=max((abs(step.energy_balance_error_j) for step in steps), default=0.0),
        linear_solve_count=solve_count, result_hash=_ZERO_HASH, deterministic=True,
        exact_checkpoint_resume_supported=True, regularization_used=False,
        fallback_used=False, contract_pass=True,
    )
    payload = asdict(provisional)
    payload.pop("result_hash")
    return replace(provisional, result_hash=canonical_hash(payload))


def validate_linear_mdof_checkpoint_authority(
    terminal: LinearMDOFCheckpoint, *, system: LinearMDOFSystem,
    config: LinearMDOFTransientConfig,
    checkpoint_chain: Sequence[LinearMDOFCheckpoint],
    force_history_prefix_n: Sequence[Sequence[float]] | np.ndarray,
) -> LinearMDOFCheckpointAuthority:
    chain = tuple(checkpoint_chain)
    forces = np.asarray(force_history_prefix_n, dtype=np.float64)
    parent_complete = bool(
        chain and chain[-1] == terminal and len(chain) == terminal.step_index + 1
        and chain[0].parent_checkpoint_hash is None
        and all(row.step_index == index for index, row in enumerate(chain))
        and all(chain[index].parent_checkpoint_hash == chain[index - 1].checkpoint_hash for index in range(1, len(chain)))
    )
    force_exact = bool(forces.shape == (len(chain), system.dimension) and all(np.array_equal(np.asarray(row.applied_force_n), forces[index]) for index, row in enumerate(chain)))
    replay = solve_linear_mdof_transient(
        system, forces, config=config,
        initial_displacement_m=chain[0].displacement_m,
        initial_velocity_m_per_s=chain[0].velocity_m_per_s,
    ) if parent_complete and force_exact else None
    deterministic = bool(replay is not None and replay.checkpoints == chain)
    dynamic = bool(replay is not None and replay.maximum_relative_residual <= config.residual_relative_tolerance)
    kinematic = bool(replay is not None and all(np.all(np.isfinite(row.acceleration_m_per_s2)) for row in replay.checkpoints))
    energy = bool(replay is not None and math.isfinite(replay.maximum_absolute_energy_balance_error_j))
    payload = {
        "schema_version": LINEAR_MDOF_AUTHORITY_SCHEMA_VERSION,
        "checkpoint_hash": terminal.checkpoint_hash,
        "source_authenticated_checkpoint": bool(parent_complete and force_exact and deterministic and dynamic and kinematic and energy),
        "parent_chain_complete": parent_complete,
        "force_history_hash": canonical_hash(forces.tolist()),
        "force_history_sample_count": int(forces.shape[0]) if forces.ndim == 2 else 0,
        "dynamic_equilibrium_replay_pass": dynamic,
        "newmark_kinematic_replay_pass": kinematic,
        "energy_replay_pass": energy,
        "deterministic_checkpoint_replay_pass": deterministic,
    }
    return LinearMDOFCheckpointAuthority(**payload, receipt_hash=canonical_hash(payload))


__all__ = [
    "LINEAR_MDOF_AUTHORITY_SCHEMA_VERSION", "LINEAR_MDOF_CHECKPOINT_SCHEMA_VERSION",
    "LINEAR_MDOF_TRANSIENT_PROFILE", "LINEAR_MDOF_TRANSIENT_SCHEMA_VERSION",
    "LinearMDOFCheckpoint", "LinearMDOFCheckpointAuthority", "LinearMDOFSolution",
    "LinearMDOFStep", "LinearMDOFSystem", "LinearMDOFTransientConfig",
    "LinearMDOFTransientError", "resume_linear_mdof_transient",
    "solve_linear_mdof_transient", "validate_linear_mdof_checkpoint_authority",
]
