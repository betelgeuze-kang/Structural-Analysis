"""Independent dense-matrix oracle for the bounded nonlinear story-frame slice.

This module intentionally does not load either native library.  It assembles the
story equilibrium and tangent with NumPy dense matrices, while the product kernel
uses a C++ tridiagonal implementation.  Python owns this test-only oracle until the
bounded C1 matrix is frozen as language-neutral golden data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


EPSILON = 1.0e-12


@dataclass(frozen=True)
class NonlinearStaticOracleConfig:
    tolerance: float
    max_iter: int
    hardening_ratio: float
    line_search_decay: float
    line_search_min: float
    pdelta_factor: float


@dataclass(frozen=True)
class NonlinearStaticOracleResult:
    converged: bool
    iterations: int
    residual_inf: float
    residual_l2: float
    max_abs_displacement_m: float
    top_displacement_m: float
    base_shear_kn: float
    plastic_story_count: int
    line_search_backtracks: int
    displacement_m: tuple[float, ...]


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
    config: NonlinearStaticOracleConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
    return internal_force, tangent, spring_force


def solve_nonlinear_static_oracle(
    *,
    config: NonlinearStaticOracleConfig,
    story_stiffness_n_per_m: Sequence[float],
    story_height_m: Sequence[float],
    story_axial_n: Sequence[float],
    story_yield_drift_m: Sequence[float],
    floor_load_n: Sequence[float],
) -> NonlinearStaticOracleResult:
    """Solve one deterministic case without calling Rust, C++, or the C ABI."""

    stiffness = _as_vector(story_stiffness_n_per_m, name="story stiffness")
    height = _as_vector(story_height_m, name="story height")
    axial = _as_vector(story_axial_n, name="story axial load")
    yield_drift = _as_vector(story_yield_drift_m, name="story yield drift")
    load = _as_vector(floor_load_n, name="floor load")
    count = int(stiffness.size)
    if any(vector.size != count for vector in (height, axial, yield_drift, load)):
        raise ValueError("all story vectors must have the same length")
    if not bool(np.all(stiffness > 0.0)) or not bool(np.all(height > 0.0)):
        raise ValueError("story stiffness and height must be positive")

    displacement = np.zeros(count, dtype=np.float64)
    converged = False
    iterations = 0
    backtracks = 0
    for iteration in range(1, config.max_iter + 1):
        internal_force, tangent, _ = _assemble(
            displacement,
            stiffness=stiffness,
            height=height,
            axial=axial,
            yield_drift=yield_drift,
            config=config,
        )
        residual = load - internal_force
        residual_inf = float(np.linalg.norm(residual, ord=np.inf))
        if np.isfinite(residual_inf) and residual_inf <= config.tolerance:
            converged = True
            iterations = iteration
            break
        try:
            increment = np.linalg.solve(tangent, residual)
        except np.linalg.LinAlgError:
            iterations = iteration
            break

        baseline = max(residual_inf, EPSILON)
        scale = 1.0
        accepted = False
        local_backtracks = 0
        while scale >= config.line_search_min:
            trial = displacement + scale * increment
            trial_internal, _, _ = _assemble(
                trial,
                stiffness=stiffness,
                height=height,
                axial=axial,
                yield_drift=yield_drift,
                config=config,
            )
            trial_inf = float(np.linalg.norm(load - trial_internal, ord=np.inf))
            if np.isfinite(trial_inf) and trial_inf < baseline:
                displacement = trial
                accepted = True
                break
            scale *= config.line_search_decay
            local_backtracks += 1
        backtracks += local_backtracks
        iterations = iteration
        if not accepted:
            break

    internal_force, _, spring_force = _assemble(
        displacement,
        stiffness=stiffness,
        height=height,
        axial=axial,
        yield_drift=yield_drift,
        config=config,
    )
    residual = load - internal_force
    residual_inf = float(np.linalg.norm(residual, ord=np.inf))
    residual_l2 = float(np.linalg.norm(residual, ord=2))
    finite = bool(
        np.all(np.isfinite(displacement))
        and np.isfinite(residual_inf)
        and np.isfinite(residual_l2)
    )
    converged = finite and residual_inf <= config.tolerance
    drift = np.diff(np.concatenate((np.zeros(1, dtype=np.float64), displacement)))
    effective_yield = np.maximum(np.abs(yield_drift), 1.0e-9)
    return NonlinearStaticOracleResult(
        converged=converged,
        iterations=iterations,
        residual_inf=residual_inf,
        residual_l2=residual_l2,
        max_abs_displacement_m=float(np.max(np.abs(displacement))),
        top_displacement_m=float(displacement[-1]),
        base_shear_kn=float(abs(spring_force[0]) / 1000.0),
        plastic_story_count=int(np.count_nonzero(np.abs(drift) > effective_yield)),
        line_search_backtracks=backtracks,
        displacement_m=tuple(float(value) for value in displacement),
    )


def solve_case(case: Mapping[str, object]) -> NonlinearStaticOracleResult:
    """Decode the language-neutral fixture shape and execute the Python oracle."""

    raw_config = case["config"]
    raw_inputs = case["inputs"]
    if not isinstance(raw_config, Mapping) or not isinstance(raw_inputs, Mapping):
        raise TypeError("fixture config and inputs must be mappings")
    return solve_nonlinear_static_oracle(
        config=NonlinearStaticOracleConfig(
            tolerance=float(raw_config["tolerance"]),
            max_iter=int(raw_config["max_iter"]),
            hardening_ratio=float(raw_config["hardening_ratio"]),
            line_search_decay=float(raw_config["line_search_decay"]),
            line_search_min=float(raw_config["line_search_min"]),
            pdelta_factor=float(raw_config["pdelta_factor"]),
        ),
        story_stiffness_n_per_m=raw_inputs["story_k_n_per_m"],
        story_height_m=raw_inputs["story_h_m"],
        story_axial_n=raw_inputs["story_axial_n"],
        story_yield_drift_m=raw_inputs["story_yield_drift_m"],
        floor_load_n=raw_inputs["floor_load_n"],
    )
