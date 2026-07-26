"""Bounded nonlinear Newmark transient reference with exact checkpoint replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any, Iterable

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


NONLINEAR_TRANSIENT_PROFILE = "newmark_average_acceleration_bilinear_sdof.v1"
NONLINEAR_TRANSIENT_SCHEMA_VERSION = "nonlinear-transient-solution.v1"
NONLINEAR_TRANSIENT_CHECKPOINT_SCHEMA_VERSION = (
    "nonlinear-transient-checkpoint.v1"
)
NONLINEAR_TRANSIENT_CLAIM_BOUNDARY = (
    "Deterministic force-driven SDOF bilinear kinematic-hardening reference; "
    "not a whole-frame, ground-motion, damping-calibration, or release path."
)
_ZERO_HASH = "sha256:" + "0" * 64


class NonlinearTransientError(RuntimeError):
    """Fail-closed input, convergence, or checkpoint-contract error."""


@dataclass(frozen=True)
class BilinearOscillator:
    mass_kn_s2_per_m: float
    elastic_stiffness_kn_per_m: float
    yield_force_kn: float
    post_yield_stiffness_ratio: float
    damping_kn_s_per_m: float = 0.0
    model_id: str = "bilinear_sdof"

    def __post_init__(self) -> None:
        for name in (
            "mass_kn_s2_per_m",
            "elastic_stiffness_kn_per_m",
            "yield_force_kn",
        ):
            object.__setattr__(self, name, _positive_float(getattr(self, name), name))
        object.__setattr__(
            self,
            "damping_kn_s_per_m",
            _nonnegative_float(self.damping_kn_s_per_m, "damping_kn_s_per_m"),
        )
        ratio = _finite_float(
            self.post_yield_stiffness_ratio,
            "post_yield_stiffness_ratio",
        )
        if ratio < 0.0 or ratio >= 1.0:
            raise ValueError("post_yield_stiffness_ratio must be in [0, 1)")
        object.__setattr__(self, "post_yield_stiffness_ratio", ratio)
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")

    @property
    def hardening_stiffness_kn_per_m(self) -> float:
        ratio = self.post_yield_stiffness_ratio
        if ratio == 0.0:
            return 0.0
        return self.elastic_stiffness_kn_per_m * ratio / (1.0 - ratio)

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "mass_kn_s2_per_m": self.mass_kn_s2_per_m,
            "elastic_stiffness_kn_per_m": self.elastic_stiffness_kn_per_m,
            "yield_force_kn": self.yield_force_kn,
            "post_yield_stiffness_ratio": self.post_yield_stiffness_ratio,
            "hardening_stiffness_kn_per_m": (
                self.hardening_stiffness_kn_per_m
            ),
            "damping_kn_s_per_m": self.damping_kn_s_per_m,
        }


@dataclass(frozen=True)
class BilinearMaterialState:
    plastic_displacement_m: float = 0.0
    backstress_kn: float = 0.0
    cumulative_plastic_displacement_m: float = 0.0
    plastic_dissipation_kn_m: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class BilinearRestoringResponse:
    force_kn: float
    tangent_kn_per_m: float
    state: BilinearMaterialState
    yielded: bool
    yield_function_kn: float
    stored_energy_kn_m: float


@dataclass(frozen=True)
class NonlinearTransientConfig:
    time_step_s: float
    residual_relative_tolerance: float = 1.0e-10
    residual_absolute_tolerance_kn: float = 1.0e-12
    maximum_iterations: int = 20
    newmark_beta: float = 0.25
    newmark_gamma: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "time_step_s",
            _positive_float(self.time_step_s, "time_step_s"),
        )
        for name in (
            "residual_relative_tolerance",
            "residual_absolute_tolerance_kn",
        ):
            object.__setattr__(self, name, _positive_float(getattr(self, name), name))
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be a positive integer")
        beta = _finite_float(self.newmark_beta, "newmark_beta")
        gamma = _finite_float(self.newmark_gamma, "newmark_gamma")
        if beta != 0.25 or gamma != 0.5:
            raise ValueError(
                "v1 supports Newmark average acceleration beta=0.25, gamma=0.5 only"
            )
        object.__setattr__(self, "newmark_beta", beta)
        object.__setattr__(self, "newmark_gamma", gamma)

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": NONLINEAR_TRANSIENT_PROFILE,
            "time_step_s": self.time_step_s,
            "residual_relative_tolerance": self.residual_relative_tolerance,
            "residual_absolute_tolerance_kn": self.residual_absolute_tolerance_kn,
            "maximum_iterations": self.maximum_iterations,
            "newmark_beta": self.newmark_beta,
            "newmark_gamma": self.newmark_gamma,
            "adaptive_time_step": False,
            "fallback_allowed": False,
            "regularization_allowed": False,
        }


@dataclass(frozen=True)
class NonlinearTransientCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    integration_contract_hash: str
    step_index: int
    time_s: float
    time_step_s: float
    applied_force_kn: float
    displacement_m: float
    velocity_m_per_s: float
    acceleration_m_per_s2: float
    material_state: BilinearMaterialState
    external_work_kn_m: float
    damping_dissipation_kn_m: float
    initial_mechanical_energy_kn_m: float
    parent_checkpoint_hash: str | None
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NonlinearTransientStep:
    step_index: int
    time_s: float
    applied_force_kn: float
    displacement_m: float
    velocity_m_per_s: float
    acceleration_m_per_s2: float
    restoring_force_kn: float
    tangent_kn_per_m: float
    yielded: bool
    newton_iterations: int
    equilibrium_residual_kn: float
    relative_residual: float
    kinetic_energy_kn_m: float
    stored_energy_kn_m: float
    external_work_kn_m: float
    damping_dissipation_kn_m: float
    plastic_dissipation_kn_m: float
    energy_balance_error_kn_m: float
    checkpoint_hash: str
    parent_checkpoint_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NonlinearTransientSolution:
    schema_version: str
    profile: str
    model_hash: str
    integration_contract_hash: str
    start_step_index: int
    end_step_index: int
    steps: tuple[NonlinearTransientStep, ...]
    checkpoints: tuple[NonlinearTransientCheckpoint, ...]
    maximum_relative_residual: float
    maximum_absolute_energy_balance_error_kn_m: float
    yielded_step_count: int
    result_hash: str
    deterministic: bool
    exact_checkpoint_resume_supported: bool
    adaptive_time_step_used: bool
    regularization_used: bool
    fallback_used: bool
    contract_pass: bool
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_bilinear_restoring_force(
    model: BilinearOscillator,
    displacement_m: float,
    committed_state: BilinearMaterialState,
) -> BilinearRestoringResponse:
    """Return one path-consistent trial response from an immutable committed state."""

    displacement = _finite_float(displacement_m, "displacement_m")
    _validate_material_state(model, committed_state)
    stiffness = model.elastic_stiffness_kn_per_m
    hardening = model.hardening_stiffness_kn_per_m
    trial_force = stiffness * (
        displacement - committed_state.plastic_displacement_m
    )
    shifted_trial = trial_force - committed_state.backstress_kn
    yield_function = abs(shifted_trial) - model.yield_force_kn
    yield_tolerance = 1.0e-12 * max(
        abs(trial_force),
        abs(committed_state.backstress_kn),
        model.yield_force_kn,
        1.0,
    )
    if yield_function <= yield_tolerance:
        force = trial_force
        tangent = stiffness
        state = committed_state
        yielded = False
    else:
        direction = 1.0 if shifted_trial > 0.0 else -1.0
        plastic_increment = yield_function / (stiffness + hardening)
        plastic_displacement = (
            committed_state.plastic_displacement_m
            + direction * plastic_increment
        )
        backstress = committed_state.backstress_kn + (
            direction * hardening * plastic_increment
        )
        state = BilinearMaterialState(
            plastic_displacement_m=plastic_displacement,
            backstress_kn=backstress,
            cumulative_plastic_displacement_m=(
                committed_state.cumulative_plastic_displacement_m
                + plastic_increment
            ),
            plastic_dissipation_kn_m=(
                committed_state.plastic_dissipation_kn_m
                + model.yield_force_kn * plastic_increment
            ),
        )
        force = stiffness * (displacement - plastic_displacement)
        tangent = stiffness * hardening / (stiffness + hardening)
        yielded = True
    stored_energy = 0.5 * stiffness * (
        displacement - state.plastic_displacement_m
    ) ** 2 + 0.5 * hardening * state.plastic_displacement_m**2
    values = (force, tangent, yield_function, stored_energy)
    if not all(math.isfinite(value) for value in values):
        raise NonlinearTransientError("bilinear restoring response is non-finite")
    return BilinearRestoringResponse(
        force_kn=force,
        tangent_kn_per_m=tangent,
        state=state,
        yielded=yielded,
        yield_function_kn=yield_function,
        stored_energy_kn_m=stored_energy,
    )


def solve_bilinear_transient(
    model: BilinearOscillator,
    applied_force_history_kn: Iterable[float],
    *,
    config: NonlinearTransientConfig,
    initial_displacement_m: float = 0.0,
    initial_velocity_m_per_s: float = 0.0,
) -> NonlinearTransientSolution:
    """Integrate a complete force history from a path-unambiguous elastic state."""

    forces = _force_history(applied_force_history_kn, allow_empty=False)
    displacement = _finite_float(initial_displacement_m, "initial_displacement_m")
    velocity = _finite_float(initial_velocity_m_per_s, "initial_velocity_m_per_s")
    initial_state = BilinearMaterialState()
    initial_response = evaluate_bilinear_restoring_force(
        model,
        displacement,
        initial_state,
    )
    if initial_response.yielded:
        raise NonlinearTransientError(
            "initial displacement must remain elastic; prehistory is otherwise ambiguous"
        )
    acceleration = (
        forces[0]
        - model.damping_kn_s_per_m * velocity
        - initial_response.force_kn
    ) / model.mass_kn_s2_per_m
    initial_energy = (
        0.5 * model.mass_kn_s2_per_m * velocity**2
        + initial_response.stored_energy_kn_m
    )
    checkpoint = _create_checkpoint(
        model=model,
        config=config,
        step_index=0,
        applied_force_kn=forces[0],
        displacement_m=displacement,
        velocity_m_per_s=velocity,
        acceleration_m_per_s2=acceleration,
        material_state=initial_state,
        external_work_kn_m=0.0,
        damping_dissipation_kn_m=0.0,
        initial_mechanical_energy_kn_m=initial_energy,
        parent_checkpoint_hash=None,
    )
    return _integrate(
        model,
        config,
        checkpoint,
        future_forces=forces[1:],
    )


def resume_bilinear_transient(
    model: BilinearOscillator,
    checkpoint: NonlinearTransientCheckpoint,
    future_applied_forces_kn: Iterable[float],
    *,
    config: NonlinearTransientConfig,
) -> NonlinearTransientSolution:
    """Resume from an exact checkpoint; future forces exclude the checkpoint force."""

    validate_nonlinear_transient_checkpoint(
        checkpoint,
        model=model,
        config=config,
    )
    future = _force_history(future_applied_forces_kn, allow_empty=True)
    return _integrate(model, config, checkpoint, future_forces=future)


def validate_nonlinear_transient_checkpoint(
    checkpoint: NonlinearTransientCheckpoint,
    *,
    model: BilinearOscillator,
    config: NonlinearTransientConfig,
) -> None:
    if not isinstance(checkpoint, NonlinearTransientCheckpoint):
        raise NonlinearTransientError("checkpoint has the wrong type")
    if checkpoint.schema_version != NONLINEAR_TRANSIENT_CHECKPOINT_SCHEMA_VERSION:
        raise NonlinearTransientError("checkpoint schema_version mismatch")
    if checkpoint.profile != NONLINEAR_TRANSIENT_PROFILE:
        raise NonlinearTransientError("checkpoint profile mismatch")
    if checkpoint.model_hash != model.model_hash:
        raise NonlinearTransientError("checkpoint model hash mismatch")
    if checkpoint.integration_contract_hash != config.contract_hash:
        raise NonlinearTransientError("checkpoint integration contract hash mismatch")
    if checkpoint.time_step_s != config.time_step_s:
        raise NonlinearTransientError("checkpoint time step mismatch")
    if type(checkpoint.step_index) is not int or checkpoint.step_index < 0:
        raise NonlinearTransientError("checkpoint step index is invalid")
    expected_time = checkpoint.step_index * config.time_step_s
    if abs(checkpoint.time_s - expected_time) > 1.0e-12 * max(expected_time, 1.0):
        raise NonlinearTransientError("checkpoint time/index relation mismatch")
    for name in (
        "time_s",
        "applied_force_kn",
        "displacement_m",
        "velocity_m_per_s",
        "acceleration_m_per_s2",
        "external_work_kn_m",
        "damping_dissipation_kn_m",
        "initial_mechanical_energy_kn_m",
    ):
        if not math.isfinite(float(getattr(checkpoint, name))):
            raise NonlinearTransientError(f"checkpoint {name} is non-finite")
    if checkpoint.damping_dissipation_kn_m < 0.0:
        raise NonlinearTransientError("checkpoint damping dissipation is negative")
    _validate_material_state(model, checkpoint.material_state)
    if checkpoint.step_index == 0 and checkpoint.parent_checkpoint_hash is not None:
        raise NonlinearTransientError("initial checkpoint cannot have a parent")
    if checkpoint.step_index > 0 and not _is_hash(checkpoint.parent_checkpoint_hash):
        raise NonlinearTransientError("positive-step checkpoint requires a parent hash")
    expected_hash = canonical_hash(_checkpoint_payload(checkpoint, include_hash=False))
    if checkpoint.checkpoint_hash != expected_hash:
        raise NonlinearTransientError("checkpoint hash mismatch")


def _integrate(
    model: BilinearOscillator,
    config: NonlinearTransientConfig,
    start: NonlinearTransientCheckpoint,
    *,
    future_forces: tuple[float, ...],
) -> NonlinearTransientSolution:
    validate_nonlinear_transient_checkpoint(start, model=model, config=config)
    checkpoints = [start]
    initial_response = evaluate_bilinear_restoring_force(
        model,
        start.displacement_m,
        start.material_state,
    )
    steps = [_step_from_checkpoint(model, start, initial_response)]
    current = start
    for force in future_forces:
        step, current = _advance_one_step(model, config, current, force)
        steps.append(step)
        checkpoints.append(current)
    maximum_residual = max(step.relative_residual for step in steps)
    maximum_energy_error = max(abs(step.energy_balance_error_kn_m) for step in steps)
    provisional = NonlinearTransientSolution(
        schema_version=NONLINEAR_TRANSIENT_SCHEMA_VERSION,
        profile=NONLINEAR_TRANSIENT_PROFILE,
        model_hash=model.model_hash,
        integration_contract_hash=config.contract_hash,
        start_step_index=start.step_index,
        end_step_index=current.step_index,
        steps=tuple(steps),
        checkpoints=tuple(checkpoints),
        maximum_relative_residual=maximum_residual,
        maximum_absolute_energy_balance_error_kn_m=maximum_energy_error,
        yielded_step_count=sum(step.yielded for step in steps),
        result_hash=_ZERO_HASH,
        deterministic=True,
        exact_checkpoint_resume_supported=True,
        adaptive_time_step_used=False,
        regularization_used=False,
        fallback_used=False,
        contract_pass=True,
        claim_boundary=NONLINEAR_TRANSIENT_CLAIM_BOUNDARY,
    )
    return replace(
        provisional,
        result_hash=canonical_hash(_solution_payload(provisional, include_hash=False)),
    )


def _advance_one_step(
    model: BilinearOscillator,
    config: NonlinearTransientConfig,
    previous: NonlinearTransientCheckpoint,
    applied_force_kn: float,
) -> tuple[NonlinearTransientStep, NonlinearTransientCheckpoint]:
    dt = config.time_step_s
    beta = config.newmark_beta
    gamma = config.newmark_gamma
    displacement_predictor = (
        previous.displacement_m
        + dt * previous.velocity_m_per_s
        + dt**2 * (0.5 - beta) * previous.acceleration_m_per_s2
    )
    velocity_predictor = previous.velocity_m_per_s + dt * (
        1.0 - gamma
    ) * previous.acceleration_m_per_s2
    displacement = displacement_predictor
    response: BilinearRestoringResponse | None = None
    acceleration = 0.0
    velocity = 0.0
    residual = math.inf
    relative_residual = math.inf
    effective_tangent = math.nan
    converged_iteration = 0
    for iteration in range(1, config.maximum_iterations + 1):
        acceleration = (displacement - displacement_predictor) / (beta * dt**2)
        velocity = velocity_predictor + gamma * dt * acceleration
        response = evaluate_bilinear_restoring_force(
            model,
            displacement,
            previous.material_state,
        )
        inertia = model.mass_kn_s2_per_m * acceleration
        damping = model.damping_kn_s_per_m * velocity
        residual = inertia + damping + response.force_kn - applied_force_kn
        scale = max(
            abs(applied_force_kn),
            abs(inertia) + abs(damping) + abs(response.force_kn),
            1.0,
        )
        relative_residual = abs(residual) / scale
        if abs(residual) <= (
            config.residual_absolute_tolerance_kn
            + config.residual_relative_tolerance * scale
        ):
            converged_iteration = iteration
            break
        effective_tangent = (
            model.mass_kn_s2_per_m / (beta * dt**2)
            + model.damping_kn_s_per_m * gamma / (beta * dt)
            + response.tangent_kn_per_m
        )
        if not math.isfinite(effective_tangent) or effective_tangent <= 0.0:
            raise NonlinearTransientError(
                f"step {previous.step_index + 1} has an invalid effective tangent"
            )
        displacement -= residual / effective_tangent
        if not math.isfinite(displacement):
            raise NonlinearTransientError(
                f"step {previous.step_index + 1} produced non-finite displacement"
            )
    if response is None or converged_iteration == 0:
        raise NonlinearTransientError(
            f"step {previous.step_index + 1} failed Newton convergence without fallback"
        )
    effective_tangent = (
        model.mass_kn_s2_per_m / (beta * dt**2)
        + model.damping_kn_s_per_m * gamma / (beta * dt)
        + response.tangent_kn_per_m
    )
    external_work = previous.external_work_kn_m + 0.5 * (
        previous.applied_force_kn + applied_force_kn
    ) * (displacement - previous.displacement_m)
    damping_dissipation = previous.damping_dissipation_kn_m + (
        0.5
        * model.damping_kn_s_per_m
        * (previous.velocity_m_per_s**2 + velocity**2)
        * dt
    )
    checkpoint = _create_checkpoint(
        model=model,
        config=config,
        step_index=previous.step_index + 1,
        applied_force_kn=applied_force_kn,
        displacement_m=displacement,
        velocity_m_per_s=velocity,
        acceleration_m_per_s2=acceleration,
        material_state=response.state,
        external_work_kn_m=external_work,
        damping_dissipation_kn_m=damping_dissipation,
        initial_mechanical_energy_kn_m=previous.initial_mechanical_energy_kn_m,
        parent_checkpoint_hash=previous.checkpoint_hash,
    )
    kinetic = 0.5 * model.mass_kn_s2_per_m * velocity**2
    energy_error = (
        previous.initial_mechanical_energy_kn_m
        + external_work
        - kinetic
        - response.stored_energy_kn_m
        - damping_dissipation
        - response.state.plastic_dissipation_kn_m
    )
    step = NonlinearTransientStep(
        step_index=checkpoint.step_index,
        time_s=checkpoint.time_s,
        applied_force_kn=applied_force_kn,
        displacement_m=displacement,
        velocity_m_per_s=velocity,
        acceleration_m_per_s2=acceleration,
        restoring_force_kn=response.force_kn,
        tangent_kn_per_m=response.tangent_kn_per_m,
        yielded=response.yielded,
        newton_iterations=converged_iteration,
        equilibrium_residual_kn=residual,
        relative_residual=relative_residual,
        kinetic_energy_kn_m=kinetic,
        stored_energy_kn_m=response.stored_energy_kn_m,
        external_work_kn_m=external_work,
        damping_dissipation_kn_m=damping_dissipation,
        plastic_dissipation_kn_m=response.state.plastic_dissipation_kn_m,
        energy_balance_error_kn_m=energy_error,
        checkpoint_hash=checkpoint.checkpoint_hash,
        parent_checkpoint_hash=checkpoint.parent_checkpoint_hash,
    )
    return step, checkpoint


def _step_from_checkpoint(
    model: BilinearOscillator,
    checkpoint: NonlinearTransientCheckpoint,
    response: BilinearRestoringResponse,
) -> NonlinearTransientStep:
    inertia = model.mass_kn_s2_per_m * checkpoint.acceleration_m_per_s2
    damping = model.damping_kn_s_per_m * checkpoint.velocity_m_per_s
    residual = inertia + damping + response.force_kn - checkpoint.applied_force_kn
    scale = max(
        abs(checkpoint.applied_force_kn),
        abs(inertia) + abs(damping) + abs(response.force_kn),
        1.0,
    )
    kinetic = 0.5 * model.mass_kn_s2_per_m * checkpoint.velocity_m_per_s**2
    energy_error = (
        checkpoint.initial_mechanical_energy_kn_m
        + checkpoint.external_work_kn_m
        - kinetic
        - response.stored_energy_kn_m
        - checkpoint.damping_dissipation_kn_m
        - checkpoint.material_state.plastic_dissipation_kn_m
    )
    return NonlinearTransientStep(
        step_index=checkpoint.step_index,
        time_s=checkpoint.time_s,
        applied_force_kn=checkpoint.applied_force_kn,
        displacement_m=checkpoint.displacement_m,
        velocity_m_per_s=checkpoint.velocity_m_per_s,
        acceleration_m_per_s2=checkpoint.acceleration_m_per_s2,
        restoring_force_kn=response.force_kn,
        tangent_kn_per_m=response.tangent_kn_per_m,
        yielded=False,
        newton_iterations=0,
        equilibrium_residual_kn=residual,
        relative_residual=abs(residual) / scale,
        kinetic_energy_kn_m=kinetic,
        stored_energy_kn_m=response.stored_energy_kn_m,
        external_work_kn_m=checkpoint.external_work_kn_m,
        damping_dissipation_kn_m=checkpoint.damping_dissipation_kn_m,
        plastic_dissipation_kn_m=(
            checkpoint.material_state.plastic_dissipation_kn_m
        ),
        energy_balance_error_kn_m=energy_error,
        checkpoint_hash=checkpoint.checkpoint_hash,
        parent_checkpoint_hash=checkpoint.parent_checkpoint_hash,
    )


def _create_checkpoint(
    *,
    model: BilinearOscillator,
    config: NonlinearTransientConfig,
    step_index: int,
    applied_force_kn: float,
    displacement_m: float,
    velocity_m_per_s: float,
    acceleration_m_per_s2: float,
    material_state: BilinearMaterialState,
    external_work_kn_m: float,
    damping_dissipation_kn_m: float,
    initial_mechanical_energy_kn_m: float,
    parent_checkpoint_hash: str | None,
) -> NonlinearTransientCheckpoint:
    provisional = NonlinearTransientCheckpoint(
        schema_version=NONLINEAR_TRANSIENT_CHECKPOINT_SCHEMA_VERSION,
        profile=NONLINEAR_TRANSIENT_PROFILE,
        model_hash=model.model_hash,
        integration_contract_hash=config.contract_hash,
        step_index=step_index,
        time_s=step_index * config.time_step_s,
        time_step_s=config.time_step_s,
        applied_force_kn=applied_force_kn,
        displacement_m=displacement_m,
        velocity_m_per_s=velocity_m_per_s,
        acceleration_m_per_s2=acceleration_m_per_s2,
        material_state=material_state,
        external_work_kn_m=external_work_kn_m,
        damping_dissipation_kn_m=damping_dissipation_kn_m,
        initial_mechanical_energy_kn_m=initial_mechanical_energy_kn_m,
        parent_checkpoint_hash=parent_checkpoint_hash,
        checkpoint_hash=_ZERO_HASH,
    )
    checkpoint = replace(
        provisional,
        checkpoint_hash=canonical_hash(
            _checkpoint_payload(provisional, include_hash=False)
        ),
    )
    validate_nonlinear_transient_checkpoint(
        checkpoint,
        model=model,
        config=config,
    )
    return checkpoint


def _checkpoint_payload(
    checkpoint: NonlinearTransientCheckpoint,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = checkpoint.to_dict()
    if not include_hash:
        payload.pop("checkpoint_hash")
    return payload


def _solution_payload(
    solution: NonlinearTransientSolution,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = solution.to_dict()
    if not include_hash:
        payload.pop("result_hash")
    return payload


def _validate_material_state(
    model: BilinearOscillator,
    state: BilinearMaterialState,
) -> None:
    if not isinstance(state, BilinearMaterialState):
        raise NonlinearTransientError("material state has the wrong type")
    for name, value in state.to_dict().items():
        if not math.isfinite(float(value)):
            raise NonlinearTransientError(f"material state {name} is non-finite")
    if state.cumulative_plastic_displacement_m < 0.0:
        raise NonlinearTransientError("cumulative plastic displacement is negative")
    if state.plastic_dissipation_kn_m < 0.0:
        raise NonlinearTransientError("plastic dissipation is negative")
    expected_backstress = (
        model.hardening_stiffness_kn_per_m * state.plastic_displacement_m
    )
    if abs(state.backstress_kn - expected_backstress) > 1.0e-10 * max(
        abs(state.backstress_kn),
        abs(expected_backstress),
        1.0,
    ):
        raise NonlinearTransientError("material state backstress is inconsistent")


def _force_history(values: Iterable[float], *, allow_empty: bool) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("applied force history must be numeric")
    try:
        normalized = tuple(
            _finite_float(value, "applied_force_history_kn") for value in values
        )
    except TypeError as exc:
        raise ValueError("applied force history must be iterable") from exc
    if not normalized and not allow_empty:
        raise ValueError("applied force history must contain an initial value")
    return normalized


def _is_hash(value: str | None) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value.removeprefix("sha256:")
    return len(suffix) == 64 and all(character in "0123456789abcdef" for character in suffix)


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite number")
    return normalized


def _positive_float(value: Any, name: str) -> float:
    normalized = _finite_float(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _nonnegative_float(value: Any, name: str) -> float:
    normalized = _finite_float(value, name)
    if normalized < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return normalized


__all__ = [
    "NONLINEAR_TRANSIENT_CHECKPOINT_SCHEMA_VERSION",
    "NONLINEAR_TRANSIENT_CLAIM_BOUNDARY",
    "NONLINEAR_TRANSIENT_PROFILE",
    "NONLINEAR_TRANSIENT_SCHEMA_VERSION",
    "BilinearMaterialState",
    "BilinearOscillator",
    "BilinearRestoringResponse",
    "NonlinearTransientCheckpoint",
    "NonlinearTransientConfig",
    "NonlinearTransientError",
    "NonlinearTransientSolution",
    "NonlinearTransientStep",
    "evaluate_bilinear_restoring_force",
    "resume_bilinear_transient",
    "solve_bilinear_transient",
    "validate_nonlinear_transient_checkpoint",
]
