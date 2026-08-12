"""Independent dense-matrix oracle for the bounded nonlinear NDTHA slice.

This module intentionally does not load the legacy Rust probe, the C++ product
library, or the C ABI.  It assembles dense NumPy story-frame operators and uses
``numpy.linalg.solve`` while the product kernel owns a C++ tridiagonal solver.
Python remains a test-only C1 oracle until these cases become neutral goldens.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

import numpy as np


EPSILON = 1.0e-12
GRAVITY_M_PER_S2 = 9.80665


@dataclass(frozen=True)
class NonlinearNdthaOracleConfig:
    story_count: int
    step_count: int
    dt_s: float
    newmark_beta: float
    newmark_gamma: float
    tolerance: float
    max_step_iterations: int
    adaptive_load_decay: float
    damping_force_cap_ratio: float
    newton_max_iter: int
    line_search_decay: float
    line_search_min: float
    hardening_ratio: float
    pdelta_factor: float
    collapse_drift_threshold_pct: float


@dataclass(frozen=True)
class NonlinearNdthaOracleResponse:
    top_displacement_m: tuple[float, ...]
    drift_ratio_pct: tuple[float, ...]
    base_shear_kn: tuple[float, ...]
    core_drift_pct: tuple[float, ...]
    core_shear_kn: tuple[float, ...]
    step_converged: tuple[bool, ...]
    step_iterations: tuple[int, ...]
    step_plastic_story_count: tuple[int, ...]
    step_residual_inf: tuple[float, ...]
    story_drift_envelope_pct: tuple[float, ...]
    final_story_drift_pct: tuple[float, ...]


@dataclass(frozen=True)
class NonlinearNdthaOracleResult:
    converged_all_steps: bool
    collapsed: bool
    collapse_step: int
    collapse_time_s: float
    collapse_drift_ratio_pct: float
    collapse_top_displacement_m: float
    step_count_completed: int
    max_plastic_story_count: int
    max_drift_ratio_pct: float
    avg_step_iterations: float
    residual_top_displacement_m: float
    residual_drift_ratio_pct: float
    total_line_search_backtracks: int
    response: NonlinearNdthaOracleResponse


@dataclass(frozen=True)
class _StepResult:
    converged: bool
    adaptive_iterations: int
    plastic_story_count: int
    base_shear_kn: float
    residual_inf: float
    line_search_backtracks: int
    displacement_m: np.ndarray
    velocity_m_per_s: np.ndarray
    acceleration_m_per_s2: np.ndarray


def _as_vector(values: Sequence[float], *, name: str) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional vector")
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError(f"{name} must contain only finite values")
    return vector


def _assemble(
    displacement: np.ndarray,
    *,
    stiffness: np.ndarray,
    height: np.ndarray,
    axial: np.ndarray,
    yield_drift: np.ndarray,
    config: NonlinearNdthaOracleConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    count = int(displacement.size)
    compatibility = np.eye(count, dtype=np.float64)
    if count > 1:
        compatibility[np.arange(1, count), np.arange(count - 1)] = -1.0
    drift = compatibility @ displacement

    absolute_drift = np.abs(drift)
    effective_yield = np.maximum(np.abs(yield_drift), 1.0e-9)
    initial_stiffness = np.maximum(stiffness, EPSILON)
    hardened_stiffness = config.hardening_ratio * initial_stiffness
    elastic = absolute_drift <= effective_yield
    spring_force = np.where(
        elastic,
        initial_stiffness * drift,
        np.sign(drift)
        * (
            initial_stiffness * effective_yield
            + hardened_stiffness * (absolute_drift - effective_yield)
        ),
    )
    material_tangent = np.where(elastic, initial_stiffness, hardened_stiffness)
    geometric_stiffness = (
        config.pdelta_factor * np.abs(axial) / np.maximum(height, EPSILON)
    )
    story_tangent = material_tangent - geometric_stiffness
    internal_force = compatibility.T @ spring_force
    tangent = compatibility.T @ np.diag(story_tangent) @ compatibility
    if float(np.min(np.abs(np.diag(tangent)))) <= 1.0e-9:
        tangent += np.diag(1.0e-6 * np.maximum(stiffness, 1.0))
    return (
        internal_force,
        tangent,
        spring_force,
        int(np.count_nonzero(~elastic)),
    )


def _solve_step(
    *,
    config: NonlinearNdthaOracleConfig,
    stiffness: np.ndarray,
    height: np.ndarray,
    axial: np.ndarray,
    yield_drift: np.ndarray,
    mass: np.ndarray,
    damping: np.ndarray,
    external_force: np.ndarray,
    previous_displacement: np.ndarray,
    previous_velocity: np.ndarray,
    previous_acceleration: np.ndarray,
) -> _StepResult:
    dt = max(config.dt_s, EPSILON)
    beta = max(config.newmark_beta, EPSILON)
    gamma = max(config.newmark_gamma, EPSILON)
    acceleration_coefficient = 1.0 / (beta * dt * dt)
    damping_coefficient = gamma / (beta * dt)
    predicted_displacement = (
        previous_displacement
        + dt * previous_velocity
        + dt * dt * (0.5 - beta) * previous_acceleration
    )
    predicted_velocity = (
        previous_velocity + dt * (1.0 - gamma) * previous_acceleration
    )
    trial_displacement = previous_displacement.copy()

    load_scale = 1.0
    adaptive_iterations = 0
    last_residual_inf = math.inf
    last_base_shear_kn = 0.0
    last_plastic_story_count = 0
    total_backtracks = 0
    for attempt in range(1, config.max_step_iterations + 1):
        adaptive_iterations = attempt
        trial_force = external_force * load_scale
        success = False
        for _ in range(config.newton_max_iter):
            internal_force, tangent, spring_force, plastic_count = _assemble(
                trial_displacement,
                stiffness=stiffness,
                height=height,
                axial=axial,
                yield_drift=yield_drift,
                config=config,
            )
            last_base_shear_kn = float(abs(spring_force[0]) / 1000.0)
            last_plastic_story_count = plastic_count
            acceleration = acceleration_coefficient * (
                trial_displacement - predicted_displacement
            )
            velocity = predicted_velocity + gamma * dt * acceleration
            residual = (
                trial_force - internal_force - damping * velocity - mass * acceleration
            )
            residual_inf = float(np.linalg.norm(residual, ord=np.inf))
            last_residual_inf = residual_inf
            if residual_inf <= config.tolerance:
                success = True
                return _StepResult(
                    converged=True,
                    adaptive_iterations=adaptive_iterations,
                    plastic_story_count=last_plastic_story_count,
                    base_shear_kn=last_base_shear_kn,
                    residual_inf=last_residual_inf,
                    line_search_backtracks=total_backtracks,
                    displacement_m=trial_displacement.copy(),
                    velocity_m_per_s=velocity,
                    acceleration_m_per_s2=acceleration,
                )

            effective_tangent = tangent + np.diag(
                mass * acceleration_coefficient + damping * damping_coefficient
            )
            try:
                increment = np.linalg.solve(effective_tangent, residual)
            except np.linalg.LinAlgError:
                break

            baseline = max(residual_inf, EPSILON)
            scale = 1.0
            while scale >= config.line_search_min:
                candidate = trial_displacement + scale * increment
                candidate_internal, _, _, _ = _assemble(
                    candidate,
                    stiffness=stiffness,
                    height=height,
                    axial=axial,
                    yield_drift=yield_drift,
                    config=config,
                )
                candidate_acceleration = acceleration_coefficient * (
                    candidate - predicted_displacement
                )
                candidate_velocity = (
                    predicted_velocity + gamma * dt * candidate_acceleration
                )
                candidate_residual = (
                    trial_force
                    - candidate_internal
                    - damping * candidate_velocity
                    - mass * candidate_acceleration
                )
                candidate_norm = float(
                    np.linalg.norm(candidate_residual, ord=np.inf)
                )
                if candidate_norm < baseline:
                    trial_displacement = candidate
                    success = True
                    break
                scale *= config.line_search_decay
                total_backtracks += 1
            if not success:
                break
            success = False

        load_scale *= config.adaptive_load_decay

    return _StepResult(
        converged=False,
        adaptive_iterations=max(adaptive_iterations, 1),
        plastic_story_count=last_plastic_story_count,
        base_shear_kn=last_base_shear_kn,
        residual_inf=last_residual_inf,
        line_search_backtracks=total_backtracks,
        displacement_m=previous_displacement.copy(),
        velocity_m_per_s=previous_velocity.copy(),
        acceleration_m_per_s2=previous_acceleration.copy(),
    )


def solve_nonlinear_ndtha_oracle(
    *,
    config: NonlinearNdthaOracleConfig,
    story_stiffness_n_per_m: Sequence[float],
    story_height_m: Sequence[float],
    story_axial_n: Sequence[float],
    story_yield_drift_m: Sequence[float],
    story_mass_kg: Sequence[float],
    story_damping_n_s_per_m: Sequence[float],
    floor_load_base_n: Sequence[float],
    acceleration_g: Sequence[float],
) -> NonlinearNdthaOracleResult:
    """Solve one deterministic case without calling Rust, C++, or the C ABI."""

    stiffness = _as_vector(story_stiffness_n_per_m, name="story stiffness")
    height = _as_vector(story_height_m, name="story height")
    axial = _as_vector(story_axial_n, name="story axial load")
    yield_drift = _as_vector(story_yield_drift_m, name="story yield drift")
    mass = _as_vector(story_mass_kg, name="story mass")
    damping = _as_vector(story_damping_n_s_per_m, name="story damping")
    floor_load = _as_vector(floor_load_base_n, name="floor load")
    ground_acceleration = _as_vector(acceleration_g, name="ground acceleration")
    story_count = int(stiffness.size)
    if config.story_count != story_count:
        raise ValueError("story_count does not match the input vectors")
    if any(
        vector.size != story_count
        for vector in (height, axial, yield_drift, mass, damping, floor_load)
    ):
        raise ValueError("all story vectors must have the same length")
    if config.step_count != int(ground_acceleration.size):
        raise ValueError("step_count does not match the acceleration vector")
    if not bool(np.all(stiffness > 0.0)) or not bool(np.all(height > 0.0)):
        raise ValueError("story stiffness and height must be positive")
    if not bool(np.all(mass > 0.0)) or not bool(np.all(damping >= 0.0)):
        raise ValueError("story mass must be positive and damping non-negative")

    step_count = config.step_count
    top_displacement = np.zeros(step_count, dtype=np.float64)
    drift_ratio = np.zeros(step_count, dtype=np.float64)
    base_shear = np.zeros(step_count, dtype=np.float64)
    core_drift = np.zeros(step_count, dtype=np.float64)
    core_shear = np.zeros(step_count, dtype=np.float64)
    step_converged = np.zeros(step_count, dtype=np.bool_)
    step_iterations = np.zeros(step_count, dtype=np.int64)
    step_plastic_count = np.zeros(step_count, dtype=np.int64)
    step_residual = np.zeros(step_count, dtype=np.float64)
    drift_envelope = np.zeros(story_count, dtype=np.float64)
    final_story_drift = np.zeros(story_count, dtype=np.float64)

    displacement = np.zeros(story_count, dtype=np.float64)
    velocity = np.zeros(story_count, dtype=np.float64)
    acceleration = np.zeros(story_count, dtype=np.float64)
    if story_count == 1:
        height_shape = np.ones(1, dtype=np.float64)
    else:
        height_shape = np.asarray(
            [
                0.85 + 0.30 * math.sin(index * 2.0 * math.pi / story_count)
                for index in range(story_count)
            ],
            dtype=np.float64,
        )

    converged_all_steps = True
    collapsed = False
    collapse_step = -1
    collapse_time_s = 0.0
    collapse_drift_ratio_pct = 0.0
    collapse_top_displacement_m = 0.0
    max_plastic_story_count = 0
    max_drift_ratio_pct = 0.0
    adaptive_iteration_sum = 0
    step_count_completed = 0
    total_line_search_backtracks = 0

    for step, acceleration_g_value in enumerate(ground_acceleration):
        sign = (
            1.0
            if abs(acceleration_g_value) <= 1.0e-12 or acceleration_g_value >= 0.0
            else -1.0
        )
        denominator = max(step_count - 1, 1)
        envelope = 1.0 + 0.50 * (step / denominator)
        raw_force = (
            floor_load
            * height_shape
            * envelope
            * (0.25 * acceleration_g_value + 0.02 * sign)
            - (mass * height_shape)
            * (acceleration_g_value * GRAVITY_M_PER_S2 * 0.05)
        )
        damping_force = damping * velocity
        damping_cap = np.maximum(
            np.abs(raw_force) * config.damping_force_cap_ratio, 1.0
        )
        external_force = raw_force - np.clip(
            damping_force, -damping_cap, damping_cap
        )

        step_result = _solve_step(
            config=config,
            stiffness=stiffness,
            height=height,
            axial=axial,
            yield_drift=yield_drift,
            mass=mass,
            damping=damping,
            external_force=external_force,
            previous_displacement=displacement,
            previous_velocity=velocity,
            previous_acceleration=acceleration,
        )
        step_converged[step] = step_result.converged
        step_iterations[step] = step_result.adaptive_iterations
        step_plastic_count[step] = step_result.plastic_story_count
        step_residual[step] = step_result.residual_inf
        adaptive_iteration_sum += step_result.adaptive_iterations
        total_line_search_backtracks += step_result.line_search_backtracks
        step_count_completed += 1
        if not step_result.converged:
            converged_all_steps = False
            break

        displacement = step_result.displacement_m
        velocity = step_result.velocity_m_per_s
        acceleration = step_result.acceleration_m_per_s2
        previous = np.concatenate((np.zeros(1, dtype=np.float64), displacement[:-1]))
        story_drift = displacement - previous
        final_story_drift = 100.0 * story_drift / np.maximum(height, EPSILON)
        story_shear = stiffness * story_drift / 1000.0
        drift_envelope = np.maximum(drift_envelope, np.abs(final_story_drift))
        current_drift_ratio = float(np.linalg.norm(final_story_drift, ord=np.inf))
        current_top_displacement = float(displacement[-1])
        top_displacement[step] = current_top_displacement
        drift_ratio[step] = current_drift_ratio
        base_shear[step] = step_result.base_shear_kn
        core_drift[step] = float(final_story_drift[0])
        core_shear[step] = float(story_shear[0])
        max_plastic_story_count = max(
            max_plastic_story_count, step_result.plastic_story_count
        )
        max_drift_ratio_pct = max(max_drift_ratio_pct, current_drift_ratio)

        if current_drift_ratio > config.collapse_drift_threshold_pct:
            collapsed = True
            converged_all_steps = False
            collapse_step = step
            collapse_time_s = step * config.dt_s
            collapse_drift_ratio_pct = current_drift_ratio
            collapse_top_displacement_m = current_top_displacement
            break

    return NonlinearNdthaOracleResult(
        converged_all_steps=converged_all_steps and not collapsed,
        collapsed=collapsed,
        collapse_step=collapse_step,
        collapse_time_s=collapse_time_s,
        collapse_drift_ratio_pct=collapse_drift_ratio_pct,
        collapse_top_displacement_m=collapse_top_displacement_m,
        step_count_completed=step_count_completed,
        max_plastic_story_count=max_plastic_story_count,
        max_drift_ratio_pct=max_drift_ratio_pct,
        avg_step_iterations=(
            adaptive_iteration_sum / step_count_completed
            if step_count_completed > 0
            else 0.0
        ),
        residual_top_displacement_m=float(displacement[-1]),
        residual_drift_ratio_pct=float(
            np.linalg.norm(final_story_drift, ord=np.inf)
        ),
        total_line_search_backtracks=total_line_search_backtracks,
        response=NonlinearNdthaOracleResponse(
            top_displacement_m=tuple(float(value) for value in top_displacement),
            drift_ratio_pct=tuple(float(value) for value in drift_ratio),
            base_shear_kn=tuple(float(value) for value in base_shear),
            core_drift_pct=tuple(float(value) for value in core_drift),
            core_shear_kn=tuple(float(value) for value in core_shear),
            step_converged=tuple(bool(value) for value in step_converged),
            step_iterations=tuple(int(value) for value in step_iterations),
            step_plastic_story_count=tuple(
                int(value) for value in step_plastic_count
            ),
            step_residual_inf=tuple(float(value) for value in step_residual),
            story_drift_envelope_pct=tuple(float(value) for value in drift_envelope),
            final_story_drift_pct=tuple(float(value) for value in final_story_drift),
        ),
    )


def solve_case(case: Mapping[str, object]) -> NonlinearNdthaOracleResult:
    """Decode the language-neutral fixture shape and execute the Python oracle."""

    raw_config = case["config"]
    raw_inputs = case["inputs"]
    if not isinstance(raw_config, Mapping) or not isinstance(raw_inputs, Mapping):
        raise TypeError("fixture config and inputs must be mappings")
    return solve_nonlinear_ndtha_oracle(
        config=NonlinearNdthaOracleConfig(
            story_count=int(raw_config["story_count"]),
            step_count=int(raw_config["step_count"]),
            dt_s=float(raw_config["dt_s"]),
            newmark_beta=float(raw_config["newmark_beta"]),
            newmark_gamma=float(raw_config["newmark_gamma"]),
            tolerance=float(raw_config["tolerance"]),
            max_step_iterations=int(raw_config["max_step_iterations"]),
            adaptive_load_decay=float(raw_config["adaptive_load_decay"]),
            damping_force_cap_ratio=float(raw_config["damping_force_cap_ratio"]),
            newton_max_iter=int(raw_config["newton_max_iter"]),
            line_search_decay=float(raw_config["line_search_decay"]),
            line_search_min=float(raw_config["line_search_min"]),
            hardening_ratio=float(raw_config["hardening_ratio"]),
            pdelta_factor=float(raw_config["pdelta_factor"]),
            collapse_drift_threshold_pct=float(
                raw_config["collapse_drift_threshold_pct"]
            ),
        ),
        story_stiffness_n_per_m=raw_inputs["story_k_n_per_m"],
        story_height_m=raw_inputs["story_h_m"],
        story_axial_n=raw_inputs["story_axial_n"],
        story_yield_drift_m=raw_inputs["story_yield_drift_m"],
        story_mass_kg=raw_inputs["story_mass_kg"],
        story_damping_n_s_per_m=raw_inputs["story_damping_n_s_per_m"],
        floor_load_base_n=raw_inputs["floor_load_base_n"],
        acceleration_g=raw_inputs["ag_g"],
    )
