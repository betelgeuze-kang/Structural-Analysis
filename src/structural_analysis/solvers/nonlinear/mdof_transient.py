"""Coupled nonlinear MDOF Newmark solver with immutable material commits."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any, Sequence

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.transient import (
    BilinearMaterialState,
    BilinearOscillator,
    evaluate_bilinear_restoring_force,
)


NONLINEAR_MDOF_TRANSIENT_PROFILE = "newmark_consistent_newton_bilinear_shear_mdof.v1"
NONLINEAR_MDOF_TRANSIENT_SCHEMA_VERSION = "nonlinear-mdof-transient-solution.v1"
NONLINEAR_MDOF_CHECKPOINT_SCHEMA_VERSION = "nonlinear-mdof-transient-checkpoint.v1"
NONLINEAR_MDOF_AUTHORITY_SCHEMA_VERSION = "nonlinear-mdof-checkpoint-authority.v1"
_ZERO_HASH = "sha256:" + "0" * 64


class NonlinearMDOFTransientError(RuntimeError):
    pass


@dataclass(frozen=True)
class BilinearStory:
    story_id: str
    elastic_stiffness_kn_per_m: float
    yield_force_kn: float
    post_yield_stiffness_ratio: float

    def __post_init__(self) -> None:
        model = self.material_model
        if not self.story_id:
            raise ValueError("story_id must be nonempty")
        _ = model.model_hash

    @property
    def material_model(self) -> BilinearOscillator:
        return BilinearOscillator(
            mass_kn_s2_per_m=1.0,
            elastic_stiffness_kn_per_m=self.elastic_stiffness_kn_per_m,
            yield_force_kn=self.yield_force_kn,
            post_yield_stiffness_ratio=self.post_yield_stiffness_ratio,
            model_id=f"story:{self.story_id}",
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "elastic_stiffness_kn_per_m": self.elastic_stiffness_kn_per_m,
            "yield_force_kn": self.yield_force_kn,
            "post_yield_stiffness_ratio": self.post_yield_stiffness_ratio,
        }


@dataclass(frozen=True)
class NonlinearShearBuilding:
    mass_matrix_kn_s2_per_m: tuple[tuple[float, ...], ...]
    damping_matrix_kn_s_per_m: tuple[tuple[float, ...], ...]
    stories: tuple[BilinearStory, ...]
    dof_ids: tuple[str, ...]
    model_id: str

    def __init__(
        self,
        mass_matrix_kn_s2_per_m: Sequence[Sequence[float]] | np.ndarray,
        damping_matrix_kn_s_per_m: Sequence[Sequence[float]] | np.ndarray,
        stories: Sequence[BilinearStory],
        dof_ids: Sequence[str],
        model_id: str = "nonlinear_shear_building",
    ) -> None:
        mass = np.asarray(mass_matrix_kn_s2_per_m, dtype=np.float64)
        damping = np.asarray(damping_matrix_kn_s_per_m, dtype=np.float64)
        story_rows = tuple(stories)
        ids = tuple(str(value) for value in dof_ids)
        n = len(ids)
        if (
            n < 2
            or mass.shape != (n, n)
            or damping.shape != (n, n)
            or len(story_rows) != n
        ):
            raise ValueError("nonlinear MDOF dimensions are inconsistent")
        if not np.array_equal(mass, mass.T) or not np.array_equal(damping, damping.T):
            raise ValueError("mass and damping matrices must be exactly symmetric")
        if not np.all(np.isfinite(mass)) or not np.all(np.isfinite(damping)):
            raise ValueError("mass and damping matrices must be finite")
        if (
            np.min(np.linalg.eigvalsh(mass)) <= 0.0
            or np.min(np.linalg.eigvalsh(damping)) < -1.0e-12
        ):
            raise ValueError("mass must be positive definite and damping semidefinite")
        if len(set(ids)) != n or len({row.story_id for row in story_rows}) != n:
            raise ValueError("DOF and story IDs must be unique")
        object.__setattr__(
            self, "mass_matrix_kn_s2_per_m", tuple(map(tuple, mass.tolist()))
        )
        object.__setattr__(
            self, "damping_matrix_kn_s_per_m", tuple(map(tuple, damping.tolist()))
        )
        object.__setattr__(self, "stories", story_rows)
        object.__setattr__(self, "dof_ids", ids)
        object.__setattr__(self, "model_id", model_id)

    @property
    def dimension(self) -> int:
        return len(self.dof_ids)

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    @property
    def drift_matrix(self) -> np.ndarray:
        matrix = np.eye(self.dimension, dtype=np.float64)
        for index in range(1, self.dimension):
            matrix[index, index - 1] = -1.0
        return matrix

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        return np.asarray(self.mass_matrix_kn_s2_per_m), np.asarray(
            self.damping_matrix_kn_s_per_m
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "dof_ids": list(self.dof_ids),
            "mass_matrix_kn_s2_per_m": [
                list(row) for row in self.mass_matrix_kn_s2_per_m
            ],
            "damping_matrix_kn_s_per_m": [
                list(row) for row in self.damping_matrix_kn_s_per_m
            ],
            "stories": [row.to_manifest() for row in self.stories],
            "drift_matrix": self.drift_matrix.tolist(),
        }


@dataclass(frozen=True)
class NonlinearMDOFTransientConfig:
    time_step_s: float
    residual_relative_tolerance: float = 1.0e-10
    residual_absolute_tolerance_kn: float = 1.0e-11
    maximum_iterations: int = 20
    newmark_beta: float = 0.25
    newmark_gamma: float = 0.5

    def __post_init__(self) -> None:
        for name in (
            "time_step_s",
            "residual_relative_tolerance",
            "residual_absolute_tolerance_kn",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be positive")
        if self.newmark_beta != 0.25 or self.newmark_gamma != 0.5:
            raise ValueError("v1 requires Newmark average acceleration")

    @property
    def contract_hash(self) -> str:
        return canonical_hash(
            asdict(self) | {"profile": NONLINEAR_MDOF_TRANSIENT_PROFILE}
        )


@dataclass(frozen=True)
class NonlinearMDOFCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    integration_contract_hash: str
    step_index: int
    time_s: float
    applied_force_kn: tuple[float, ...]
    displacement_m: tuple[float, ...]
    velocity_m_per_s: tuple[float, ...]
    acceleration_m_per_s2: tuple[float, ...]
    material_states: tuple[BilinearMaterialState, ...]
    external_work_kn_m: float
    damping_dissipation_kn_m: float
    initial_mechanical_energy_kn_m: float
    parent_checkpoint_hash: str | None
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NonlinearMDOFStep:
    step_index: int
    time_s: float
    applied_force_kn: tuple[float, ...]
    displacement_m: tuple[float, ...]
    velocity_m_per_s: tuple[float, ...]
    acceleration_m_per_s2: tuple[float, ...]
    story_drift_m: tuple[float, ...]
    story_force_kn: tuple[float, ...]
    equilibrium_residual_kn: tuple[float, ...]
    relative_residual: float
    newton_iterations: int
    yielded_story_count: int
    kinetic_energy_kn_m: float
    stored_energy_kn_m: float
    external_work_kn_m: float
    damping_dissipation_kn_m: float
    plastic_dissipation_kn_m: float
    energy_balance_error_kn_m: float
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NonlinearMDOFSolution:
    schema_version: str
    profile: str
    model_hash: str
    integration_contract_hash: str
    start_step_index: int
    end_step_index: int
    steps: tuple[NonlinearMDOFStep, ...]
    checkpoints: tuple[NonlinearMDOFCheckpoint, ...]
    maximum_relative_residual: float
    maximum_absolute_energy_balance_error_kn_m: float
    total_newton_iterations: int
    yielded_step_count: int
    result_hash: str
    exact_checkpoint_resume_supported: bool
    material_trial_commit_rollback: bool
    regularization_used: bool
    fallback_used: bool
    contract_pass: bool


@dataclass(frozen=True)
class NonlinearMDOFCheckpointAuthority:
    schema_version: str
    checkpoint_hash: str
    source_authenticated_checkpoint: bool
    parent_chain_complete: bool
    force_history_hash: str
    force_history_sample_count: int
    dynamic_equilibrium_replay_pass: bool
    material_state_replay_pass: bool
    deterministic_checkpoint_replay_pass: bool
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        claimed = payload.pop("receipt_hash")
        if canonical_hash(payload) != claimed:
            raise NonlinearMDOFTransientError("authority receipt hash mismatch")
        payload["receipt_hash"] = claimed
        return payload


def _response(
    system: NonlinearShearBuilding,
    displacement: np.ndarray,
    committed_states: Sequence[BilinearMaterialState],
) -> tuple[
    np.ndarray, np.ndarray, tuple[BilinearMaterialState, ...], tuple[bool, ...], float
]:
    drift = system.drift_matrix @ displacement
    rows = tuple(
        evaluate_bilinear_restoring_force(
            story.material_model, float(drift[index]), committed_states[index]
        )
        for index, story in enumerate(system.stories)
    )
    story_force = np.asarray([row.force_kn for row in rows])
    tangent = (
        system.drift_matrix.T
        @ np.diag([row.tangent_kn_per_m for row in rows])
        @ system.drift_matrix
    )
    global_force = system.drift_matrix.T @ story_force
    return (
        global_force,
        tangent,
        tuple(row.state for row in rows),
        tuple(row.yielded for row in rows),
        float(sum(row.stored_energy_kn_m for row in rows)),
    )


def _checkpoint(
    *,
    system: NonlinearShearBuilding,
    config: NonlinearMDOFTransientConfig,
    step_index: int,
    force: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    a: np.ndarray,
    states: tuple[BilinearMaterialState, ...],
    external_work: float,
    damping_dissipation: float,
    initial_energy: float,
    parent: str | None,
) -> NonlinearMDOFCheckpoint:
    provisional = NonlinearMDOFCheckpoint(
        schema_version=NONLINEAR_MDOF_CHECKPOINT_SCHEMA_VERSION,
        profile=NONLINEAR_MDOF_TRANSIENT_PROFILE,
        model_hash=system.model_hash,
        integration_contract_hash=config.contract_hash,
        step_index=step_index,
        time_s=step_index * config.time_step_s,
        applied_force_kn=tuple(map(float, force)),
        displacement_m=tuple(map(float, u)),
        velocity_m_per_s=tuple(map(float, v)),
        acceleration_m_per_s2=tuple(map(float, a)),
        material_states=states,
        external_work_kn_m=float(external_work),
        damping_dissipation_kn_m=float(damping_dissipation),
        initial_mechanical_energy_kn_m=float(initial_energy),
        parent_checkpoint_hash=parent,
        checkpoint_hash=_ZERO_HASH,
    )
    payload = provisional.to_dict()
    payload.pop("checkpoint_hash")
    return replace(provisional, checkpoint_hash=canonical_hash(payload))


def solve_nonlinear_mdof_transient(
    system: NonlinearShearBuilding,
    applied_force_history_kn: Sequence[Sequence[float]] | np.ndarray,
    *,
    config: NonlinearMDOFTransientConfig,
    initial_displacement_m: Sequence[float] | None = None,
    initial_velocity_m_per_s: Sequence[float] | None = None,
) -> NonlinearMDOFSolution:
    forces = np.asarray(applied_force_history_kn, dtype=np.float64)
    if (
        forces.ndim != 2
        or forces.shape[0] < 1
        or forces.shape[1] != system.dimension
        or not np.all(np.isfinite(forces))
    ):
        raise ValueError("force history must be a finite [sample, dof] matrix")
    u = np.asarray(
        initial_displacement_m
        if initial_displacement_m is not None
        else np.zeros(system.dimension),
        dtype=np.float64,
    )
    v = np.asarray(
        initial_velocity_m_per_s
        if initial_velocity_m_per_s is not None
        else np.zeros(system.dimension),
        dtype=np.float64,
    )
    states = tuple(BilinearMaterialState() for _ in system.stories)
    internal, _, initial_states, yielded, stored = _response(system, u, states)
    if any(yielded) or initial_states != states:
        raise NonlinearMDOFTransientError("initial displacement must remain elastic")
    mass, damping = system.arrays()
    a = np.linalg.solve(mass, forces[0] - damping @ v - internal)
    initial_energy = float(0.5 * v @ mass @ v + stored)
    start = _checkpoint(
        system=system,
        config=config,
        step_index=0,
        force=forces[0],
        u=u,
        v=v,
        a=a,
        states=states,
        external_work=0.0,
        damping_dissipation=0.0,
        initial_energy=initial_energy,
        parent=None,
    )
    return _advance(system, config, start, forces[1:])


def resume_nonlinear_mdof_transient(
    system: NonlinearShearBuilding,
    checkpoint: NonlinearMDOFCheckpoint,
    future_applied_forces_kn: Sequence[Sequence[float]] | np.ndarray,
    *,
    config: NonlinearMDOFTransientConfig,
    checkpoint_chain: Sequence[NonlinearMDOFCheckpoint],
    force_history_prefix_kn: Sequence[Sequence[float]] | np.ndarray,
) -> NonlinearMDOFSolution:
    authority = validate_nonlinear_mdof_checkpoint_authority(
        checkpoint,
        system=system,
        config=config,
        checkpoint_chain=checkpoint_chain,
        force_history_prefix_kn=force_history_prefix_kn,
    )
    if not authority.source_authenticated_checkpoint:
        raise NonlinearMDOFTransientError("checkpoint is not source authenticated")
    future = np.asarray(future_applied_forces_kn, dtype=np.float64)
    return _advance(system, config, checkpoint, future)


def _advance(
    system: NonlinearShearBuilding,
    config: NonlinearMDOFTransientConfig,
    start: NonlinearMDOFCheckpoint,
    future_forces: np.ndarray,
) -> NonlinearMDOFSolution:
    mass, damping = system.arrays()
    drift_matrix = system.drift_matrix
    dt, beta, gamma = config.time_step_s, config.newmark_beta, config.newmark_gamma
    c0, c1 = 1.0 / (beta * dt * dt), gamma / (beta * dt)
    u = np.asarray(start.displacement_m)
    v = np.asarray(start.velocity_m_per_s)
    a = np.asarray(start.acceleration_m_per_s2)
    previous_force = np.asarray(start.applied_force_kn)
    states = start.material_states
    external_work, damping_dissipation = (
        start.external_work_kn_m,
        start.damping_dissipation_kn_m,
    )
    checkpoints = [start]
    steps: list[NonlinearMDOFStep] = []
    initial_internal, _, _, _, initial_stored = _response(system, u, states)
    _ = initial_internal
    initial_kinetic = float(0.5 * v @ mass @ v)
    steps.append(
        NonlinearMDOFStep(
            step_index=start.step_index,
            time_s=start.time_s,
            applied_force_kn=start.applied_force_kn,
            displacement_m=start.displacement_m,
            velocity_m_per_s=start.velocity_m_per_s,
            acceleration_m_per_s2=start.acceleration_m_per_s2,
            story_drift_m=tuple(map(float, drift_matrix @ u)),
            story_force_kn=tuple(
                map(float, np.linalg.solve(drift_matrix.T, initial_internal))
            ),
            equilibrium_residual_kn=tuple(0.0 for _ in range(system.dimension)),
            relative_residual=0.0,
            newton_iterations=0,
            yielded_story_count=0,
            kinetic_energy_kn_m=initial_kinetic,
            stored_energy_kn_m=initial_stored,
            external_work_kn_m=external_work,
            damping_dissipation_kn_m=damping_dissipation,
            plastic_dissipation_kn_m=float(
                sum(row.plastic_dissipation_kn_m for row in states)
            ),
            energy_balance_error_kn_m=float(
                external_work
                + start.initial_mechanical_energy_kn_m
                - initial_kinetic
                - initial_stored
                - damping_dissipation
            ),
            checkpoint_hash=start.checkpoint_hash,
        )
    )
    total_iterations = 0
    for offset, force in enumerate(
        np.asarray(future_forces, dtype=np.float64), start=1
    ):
        step_index = start.step_index + offset
        parent_states = states
        candidate = u + dt * v + 0.5 * dt * dt * a
        converged = False
        final = None
        for iteration in range(1, config.maximum_iterations + 1):
            candidate_a = (
                c0 * (candidate - u)
                - (1.0 / (beta * dt)) * v
                - (1.0 / (2.0 * beta) - 1.0) * a
            )
            candidate_v = v + dt * ((1.0 - gamma) * a + gamma * candidate_a)
            internal, tangent, trial_states, yielded, stored = _response(
                system, candidate, parent_states
            )
            residual = mass @ candidate_a + damping @ candidate_v + internal - force
            scale = max(
                float(np.linalg.norm(force)),
                float(
                    np.linalg.norm(mass @ candidate_a)
                    + np.linalg.norm(damping @ candidate_v)
                    + np.linalg.norm(internal)
                ),
                1.0,
            )
            relative = float(np.linalg.norm(residual) / scale)
            if (
                float(np.linalg.norm(residual)) <= config.residual_absolute_tolerance_kn
                or relative <= config.residual_relative_tolerance
            ):
                converged = True
                final = (
                    candidate_a,
                    candidate_v,
                    internal,
                    trial_states,
                    yielded,
                    stored,
                    residual,
                    relative,
                    iteration,
                )
                break
            effective = c0 * mass + c1 * damping + tangent
            candidate = candidate - np.linalg.solve(effective, residual)
        if not converged or final is None:
            if states != parent_states:
                raise NonlinearMDOFTransientError("material rollback failed")
            raise NonlinearMDOFTransientError(
                f"Newton failed at step {step_index}; accepted state rolled back exactly"
            )
        (
            new_a,
            new_v,
            internal,
            trial_states,
            yielded,
            stored,
            residual,
            relative,
            iterations,
        ) = final
        external_work += float(0.5 * (previous_force + force) @ (candidate - u))
        damping_dissipation += float(
            0.5 * dt * (v @ damping @ v + new_v @ damping @ new_v)
        )
        kinetic = float(0.5 * new_v @ mass @ new_v)
        plastic = float(sum(row.plastic_dissipation_kn_m for row in trial_states))
        energy_error = (
            external_work
            + start.initial_mechanical_energy_kn_m
            - kinetic
            - stored
            - damping_dissipation
            - plastic
        )
        checkpoint = _checkpoint(
            system=system,
            config=config,
            step_index=step_index,
            force=force,
            u=candidate,
            v=new_v,
            a=new_a,
            states=trial_states,
            external_work=external_work,
            damping_dissipation=damping_dissipation,
            initial_energy=start.initial_mechanical_energy_kn_m,
            parent=checkpoints[-1].checkpoint_hash,
        )
        story_force = np.linalg.solve(drift_matrix.T, internal)
        steps.append(
            NonlinearMDOFStep(
                step_index=step_index,
                time_s=step_index * dt,
                applied_force_kn=tuple(map(float, force)),
                displacement_m=tuple(map(float, candidate)),
                velocity_m_per_s=tuple(map(float, new_v)),
                acceleration_m_per_s2=tuple(map(float, new_a)),
                story_drift_m=tuple(map(float, drift_matrix @ candidate)),
                story_force_kn=tuple(map(float, story_force)),
                equilibrium_residual_kn=tuple(map(float, residual)),
                relative_residual=relative,
                newton_iterations=iterations,
                yielded_story_count=sum(yielded),
                kinetic_energy_kn_m=kinetic,
                stored_energy_kn_m=stored,
                external_work_kn_m=external_work,
                damping_dissipation_kn_m=damping_dissipation,
                plastic_dissipation_kn_m=plastic,
                energy_balance_error_kn_m=energy_error,
                checkpoint_hash=checkpoint.checkpoint_hash,
            )
        )
        checkpoints.append(checkpoint)
        total_iterations += iterations
        u, v, a, states, previous_force = candidate, new_v, new_a, trial_states, force
    provisional = NonlinearMDOFSolution(
        schema_version=NONLINEAR_MDOF_TRANSIENT_SCHEMA_VERSION,
        profile=NONLINEAR_MDOF_TRANSIENT_PROFILE,
        model_hash=system.model_hash,
        integration_contract_hash=config.contract_hash,
        start_step_index=start.step_index,
        end_step_index=checkpoints[-1].step_index,
        steps=tuple(steps),
        checkpoints=tuple(checkpoints),
        maximum_relative_residual=max(row.relative_residual for row in steps),
        maximum_absolute_energy_balance_error_kn_m=max(
            abs(row.energy_balance_error_kn_m) for row in steps
        ),
        total_newton_iterations=total_iterations,
        yielded_step_count=sum(row.yielded_story_count > 0 for row in steps),
        result_hash=_ZERO_HASH,
        exact_checkpoint_resume_supported=True,
        material_trial_commit_rollback=True,
        regularization_used=False,
        fallback_used=False,
        contract_pass=True,
    )
    payload = asdict(provisional)
    payload.pop("result_hash")
    return replace(provisional, result_hash=canonical_hash(payload))


def validate_nonlinear_mdof_checkpoint_authority(
    terminal: NonlinearMDOFCheckpoint,
    *,
    system: NonlinearShearBuilding,
    config: NonlinearMDOFTransientConfig,
    checkpoint_chain: Sequence[NonlinearMDOFCheckpoint],
    force_history_prefix_kn: Sequence[Sequence[float]] | np.ndarray,
) -> NonlinearMDOFCheckpointAuthority:
    chain = tuple(checkpoint_chain)
    forces = np.asarray(force_history_prefix_kn, dtype=np.float64)
    parent_complete = bool(
        chain
        and chain[-1] == terminal
        and len(chain) == terminal.step_index + 1
        and chain[0].parent_checkpoint_hash is None
        and all(row.step_index == index for index, row in enumerate(chain))
        and all(
            chain[index].parent_checkpoint_hash == chain[index - 1].checkpoint_hash
            for index in range(1, len(chain))
        )
    )
    force_exact = bool(
        forces.shape == (len(chain), system.dimension)
        and all(
            np.array_equal(np.asarray(row.applied_force_kn), forces[index])
            for index, row in enumerate(chain)
        )
    )
    replay = (
        solve_nonlinear_mdof_transient(
            system,
            forces,
            config=config,
            initial_displacement_m=chain[0].displacement_m,
            initial_velocity_m_per_s=chain[0].velocity_m_per_s,
        )
        if parent_complete and force_exact
        else None
    )
    deterministic = bool(replay is not None and replay.checkpoints == chain)
    dynamic = bool(
        replay is not None
        and replay.maximum_relative_residual <= config.residual_relative_tolerance
    )
    material = bool(
        replay is not None
        and replay.checkpoints[-1].material_states == terminal.material_states
    )
    payload = {
        "schema_version": NONLINEAR_MDOF_AUTHORITY_SCHEMA_VERSION,
        "checkpoint_hash": terminal.checkpoint_hash,
        "source_authenticated_checkpoint": bool(
            parent_complete and force_exact and deterministic and dynamic and material
        ),
        "parent_chain_complete": parent_complete,
        "force_history_hash": canonical_hash(forces.tolist()),
        "force_history_sample_count": int(forces.shape[0]) if forces.ndim == 2 else 0,
        "dynamic_equilibrium_replay_pass": dynamic,
        "material_state_replay_pass": material,
        "deterministic_checkpoint_replay_pass": deterministic,
    }
    return NonlinearMDOFCheckpointAuthority(
        **payload, receipt_hash=canonical_hash(payload)
    )


__all__ = [
    "BilinearStory",
    "NONLINEAR_MDOF_AUTHORITY_SCHEMA_VERSION",
    "NONLINEAR_MDOF_CHECKPOINT_SCHEMA_VERSION",
    "NONLINEAR_MDOF_TRANSIENT_PROFILE",
    "NONLINEAR_MDOF_TRANSIENT_SCHEMA_VERSION",
    "NonlinearMDOFCheckpoint",
    "NonlinearMDOFCheckpointAuthority",
    "NonlinearMDOFSolution",
    "NonlinearMDOFStep",
    "NonlinearMDOFTransientConfig",
    "NonlinearMDOFTransientError",
    "NonlinearShearBuilding",
    "resume_nonlinear_mdof_transient",
    "solve_nonlinear_mdof_transient",
    "validate_nonlinear_mdof_checkpoint_authority",
]
