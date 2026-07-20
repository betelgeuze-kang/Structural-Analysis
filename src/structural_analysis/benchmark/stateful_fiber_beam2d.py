"""Bounded state-updated RC fiber beam and cantilever Newton benchmark."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any

import numpy as np

from structural_analysis.elements.stateful_fiber_beam2d import (
    STATEFUL_FIBER_BEAM2D_TANGENT,
    StatefulFiberBeam2D,
    StatefulFiberBeam2DResponse,
    StatefulFiberBeam2DState,
    finite_difference_stateful_fiber_beam2d_tangent_check,
    integrate_stateful_fiber_beam2d_history,
)
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)


STATEFUL_FIBER_BEAM2D_BENCHMARK_SCHEMA_VERSION = "phase2-stateful-rc-fiber-beam2d.v1"
STATEFUL_FIBER_BEAM2D_NEWTON_SCHEMA_VERSION = (
    "stateful-rc-fiber-beam2d-cantilever-newton.v1"
)
STATEFUL_FIBER_BEAM2D_CLAIM_BOUNDARY = (
    "This receipt verifies one local-coordinate, small-displacement, two-node "
    "Euler-Bernoulli beam element with axial-curvature RC fiber-section "
    "states at three Gauss points, a consistent 6x6 material tangent, and a "
    "fixed-base single-element cantilever Newton solve with deterministic "
    "replay and exact rollback. It does not validate coordinate "
    "transformation, multi-element assembly, shear deformation, torsion, "
    "geometric nonlinearity, general plastic-hinge or distributed-plasticity "
    "formulations, mesh objectivity, external benchmarks, production sparse "
    "or ROCm/HIP execution, full-building equilibrium, or G1 closure. The "
    "element state has no higher-level parent hash and is not an authoritative "
    "restart chain; diagnostic history acceptance is not a product commit path."
)

_FREE_TIP_DOFS = (3, 4, 5)


def _finite_three_vector(values: Any, *, name: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite three-vector") from exc
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite three-vector")
    return np.ascontiguousarray(vector, dtype=np.float64)


def _positive(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be positive")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be positive") from exc
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


@dataclass(frozen=True)
class FiberBeamCantileverNewtonConfig:
    axial_force_scale_kn: float = 1_000.0
    shear_force_scale_kn: float = 100.0
    moment_scale_kn_m: float = 100.0
    axial_displacement_scale_m: float = 1.0e-3
    transverse_displacement_scale_m: float = 1.0e-2
    rotation_scale_rad: float = 1.0e-2
    residual_tolerance: float = 1.0e-10
    increment_tolerance: float = 1.0e-10
    maximum_iterations: int = 24
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    )

    def __post_init__(self) -> None:
        for name in (
            "axial_force_scale_kn",
            "shear_force_scale_kn",
            "moment_scale_kn_m",
            "axial_displacement_scale_m",
            "transverse_displacement_scale_m",
            "rotation_scale_rad",
            "residual_tolerance",
            "increment_tolerance",
        ):
            object.__setattr__(
                self,
                name,
                _positive(getattr(self, name), name=name),
            )
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 0:
            raise ValueError("maximum_iterations must be a non-negative integer")
        if not self.line_search_alphas:
            raise ValueError("line_search_alphas must be non-empty")
        previous = math.inf
        normalized: list[float] = []
        for value in self.line_search_alphas:
            alpha = _positive(value, name="line_search_alpha")
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized.append(alpha)
            previous = alpha
        object.__setattr__(self, "line_search_alphas", tuple(normalized))

    @property
    def residual_scales(self) -> np.ndarray:
        return np.asarray(
            [
                self.axial_force_scale_kn,
                self.shear_force_scale_kn,
                self.moment_scale_kn_m,
            ],
            dtype=np.float64,
        )

    @property
    def increment_scales(self) -> np.ndarray:
        return np.asarray(
            [
                self.axial_displacement_scale_m,
                self.transverse_displacement_scale_m,
                self.rotation_scale_rad,
            ],
            dtype=np.float64,
        )


@dataclass(frozen=True)
class FiberBeamCantileverNewtonResult:
    status: str
    terminal_reason: str
    target_tip_load: tuple[float, float, float]
    parent_state: StatefulFiberBeam2DState
    accepted_state: StatefulFiberBeam2DState
    solution_tip_displacements: tuple[float, float, float]
    trial_response: StatefulFiberBeam2DResponse
    convergence_history: tuple[dict[str, Any], ...]
    line_search_history: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]

    @property
    def committed(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_FIBER_BEAM2D_NEWTON_SCHEMA_VERSION,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "target_tip_load": {
                "axial_force_kn": self.target_tip_load[0],
                "shear_force_kn": self.target_tip_load[1],
                "moment_z_kn_m": self.target_tip_load[2],
            },
            "parent_state_hash": self.parent_state.state_hash,
            "accepted_state": self.accepted_state.to_dict(),
            "solution_tip_displacements": {
                "axial_m": self.solution_tip_displacements[0],
                "transverse_m": self.solution_tip_displacements[1],
                "rotation_rad": self.solution_tip_displacements[2],
            },
            "committed": self.committed,
            "trial_response": self.trial_response.to_summary_dict(),
            "convergence_history": list(self.convergence_history),
            "line_search_history": list(self.line_search_history),
            "metrics": dict(self.metrics),
        }


def _fixed_base_local_displacements(tip: np.ndarray) -> np.ndarray:
    local = np.zeros(6, dtype=np.float64)
    local[list(_FREE_TIP_DOFS)] = tip
    return local


def _scaled_residual_norm(
    residual: np.ndarray,
    config: FiberBeamCantileverNewtonConfig,
) -> float:
    return float(np.linalg.norm(residual / config.residual_scales, ord=np.inf))


def _scaled_increment_norm(
    increment: np.ndarray,
    config: FiberBeamCantileverNewtonConfig,
) -> float:
    return float(np.linalg.norm(increment / config.increment_scales, ord=np.inf))


def solve_stateful_fiber_beam2d_cantilever(
    element: StatefulFiberBeam2D,
    committed_state: StatefulFiberBeam2DState,
    *,
    target_tip_load: Any,
    initial_tip_displacements: Any | None = None,
    config: FiberBeamCantileverNewtonConfig | None = None,
) -> FiberBeamCantileverNewtonResult:
    """Solve one fixed-base local cantilever step and commit atomically."""

    element.validate_state(committed_state)
    if any(abs(value) > 1.0e-14 for value in committed_state.local_displacements[:3]):
        raise ValueError("cantilever parent state must have a fixed zero base")
    cfg = config or FiberBeamCantileverNewtonConfig()
    target = _finite_three_vector(target_tip_load, name="target_tip_load")
    tip = _finite_three_vector(
        (
            committed_state.local_displacements[3:]
            if initial_tip_displacements is None
            else initial_tip_displacements
        ),
        name="initial_tip_displacements",
    )
    parent_bytes = committed_state.canonical_bytes()
    history: list[dict[str, Any]] = []
    line_search_history: list[dict[str, Any]] = []
    accepted_response: StatefulFiberBeam2DResponse | None = None
    terminal_reason = "maximum_iterations_exhausted"

    for iteration in range(cfg.maximum_iterations + 1):
        local = _fixed_base_local_displacements(tip)
        response = element.integrate(local, committed_state)
        residual = response.internal_force_local[list(_FREE_TIP_DOFS)] - target
        residual_norm = _scaled_residual_norm(residual, cfg)
        reduced_tangent = response.consistent_tangent_local[
            np.ix_(_FREE_TIP_DOFS, _FREE_TIP_DOFS)
        ]
        try:
            newton_increment = np.linalg.solve(reduced_tangent, -residual)
        except np.linalg.LinAlgError:
            terminal_reason = "singular_consistent_cantilever_tangent"
            break
        increment_norm = _scaled_increment_norm(newton_increment, cfg)
        residual_gate = residual_norm <= cfg.residual_tolerance
        increment_gate = increment_norm <= cfg.increment_tolerance
        row: dict[str, Any] = {
            "iteration": iteration,
            "tip_displacements": tip.tolist(),
            "tip_internal_force": response.internal_force_local[
                list(_FREE_TIP_DOFS)
            ].tolist(),
            "residual": residual.tolist(),
            "scaled_residual_inf_norm": residual_norm,
            "newton_increment": newton_increment.tolist(),
            "scaled_increment_inf_norm": increment_norm,
            "residual_gate_passed": residual_gate,
            "increment_gate_passed": increment_gate,
        }
        if residual_gate and increment_gate:
            row.update(
                {
                    "selected_line_search_alpha": 1.0,
                    "line_search_attempt_count": 0,
                    "accepted": True,
                }
            )
            history.append(row)
            accepted_response = response
            terminal_reason = "residual_and_increment_converged"
            break

        attempts: list[dict[str, Any]] = []
        selected_alpha = 0.0
        selected_tip = tip
        for alpha in cfg.line_search_alphas:
            trial_tip = tip + alpha * newton_increment
            trial_response = element.integrate(
                _fixed_base_local_displacements(trial_tip),
                committed_state,
            )
            trial_residual = (
                trial_response.internal_force_local[list(_FREE_TIP_DOFS)] - target
            )
            trial_norm = _scaled_residual_norm(trial_residual, cfg)
            accepted = trial_norm < residual_norm
            attempts.append(
                {
                    "alpha": alpha,
                    "trial_tip_displacements": trial_tip.tolist(),
                    "trial_residual": trial_residual.tolist(),
                    "trial_scaled_residual_inf_norm": trial_norm,
                    "accepted": accepted,
                }
            )
            if accepted:
                selected_alpha = alpha
                selected_tip = trial_tip
                break
        line_search_history.append(
            {
                "iteration": iteration,
                "selected_alpha": selected_alpha,
                "attempts": attempts,
            }
        )
        row.update(
            {
                "selected_line_search_alpha": selected_alpha,
                "line_search_attempt_count": len(attempts),
                "accepted": selected_alpha > 0.0,
            }
        )
        history.append(row)
        if selected_alpha == 0.0:
            terminal_reason = "line_search_failed_to_reduce_residual"
            break
        tip = np.ascontiguousarray(selected_tip, dtype=np.float64)
        if iteration == cfg.maximum_iterations:
            terminal_reason = "maximum_iterations_exhausted"
            break

    parent_unchanged = bool(
        committed_state.canonical_bytes() == parent_bytes
        and element.validate_state(committed_state) is None
    )
    if accepted_response is None:
        status = "blocked"
        accepted_state = committed_state
        final_response = element.integrate(
            _fixed_base_local_displacements(tip),
            committed_state,
        )
        rollback_exact = bool(
            accepted_state is committed_state
            and accepted_state.canonical_bytes() == parent_bytes
            and parent_unchanged
        )
    else:
        status = "ready"
        accepted_state = accepted_response.state
        final_response = accepted_response
        rollback_exact = True
    final_residual = final_response.internal_force_local[list(_FREE_TIP_DOFS)] - target
    final_scaled_residual = _scaled_residual_norm(final_residual, cfg)
    solver_contract_pass = bool(
        status == "ready"
        and final_scaled_residual <= cfg.residual_tolerance
        and parent_unchanged
        and rollback_exact
    )
    metrics = {
        "contract_pass": solver_contract_pass,
        "residual_formula": "tip_internal_force-target_tip_load",
        "tangent_definition": STATEFUL_FIBER_BEAM2D_TANGENT,
        "final_scaled_residual_inf_norm": final_scaled_residual,
        "final_residual": final_residual.tolist(),
        "base_reaction": final_response.internal_force_local[:3].tolist(),
        "iteration_count": len(history),
        "linear_solve_count": len(history),
        "line_search_step_count": len(line_search_history),
        "line_search_used": any(
            row["selected_alpha"] < 1.0
            for row in line_search_history
            if row["selected_alpha"] > 0.0
        ),
        "parent_state_immutable": parent_unchanged,
        "rollback_exact": rollback_exact,
        "fallback_count": 0,
        "regularization_count": 0,
        "element_contract_hash": element.contract_hash,
    }
    return FiberBeamCantileverNewtonResult(
        status=status,
        terminal_reason=terminal_reason,
        target_tip_load=(float(target[0]), float(target[1]), float(target[2])),
        parent_state=committed_state,
        accepted_state=accepted_state,
        solution_tip_displacements=(
            float(tip[0]),
            float(tip[1]),
            float(tip[2]),
        ),
        trial_response=final_response,
        convergence_history=tuple(history),
        line_search_history=tuple(line_search_history),
        metrics=metrics,
    )


def _elastic_reference_check(element: StatefulFiberBeam2D) -> dict[str, Any]:
    zero = element.integrate(np.zeros(6, dtype=np.float64), element.initial_state())
    section_tangent = zero.section_responses[0].consistent_tangent
    axial_rigidity = float(section_tangent[0, 0])
    flexural_rigidity = float(section_tangent[1, 1])
    length = element.length_m
    expected = np.zeros((6, 6), dtype=np.float64)
    axial = axial_rigidity / length
    expected[np.ix_((0, 3), (0, 3))] = np.asarray(
        [[axial, -axial], [-axial, axial]],
        dtype=np.float64,
    )
    bending = flexural_rigidity * np.asarray(
        [
            [12.0 / length**3, 6.0 / length**2, -12.0 / length**3, 6.0 / length**2],
            [6.0 / length**2, 4.0 / length, -6.0 / length**2, 2.0 / length],
            [-12.0 / length**3, -6.0 / length**2, 12.0 / length**3, -6.0 / length**2],
            [6.0 / length**2, 2.0 / length, -6.0 / length**2, 4.0 / length],
        ],
        dtype=np.float64,
    )
    expected[np.ix_((1, 2, 4, 5), (1, 2, 4, 5))] = bending
    error = zero.consistent_tangent_local - expected
    absolute_error = float(np.linalg.norm(error, ord=np.inf))
    scale = max(float(np.linalg.norm(expected, ord=np.inf)), 1.0)
    relative_error = absolute_error / scale
    return {
        "axial_rigidity_kn": axial_rigidity,
        "flexural_rigidity_kn_m2": flexural_rigidity,
        "analytic_local_tangent": expected.tolist(),
        "integrated_local_tangent": zero.consistent_tangent_local.tolist(),
        "absolute_inf_error": absolute_error,
        "relative_inf_error": relative_error,
        "pass": bool(relative_error <= 1.0e-12),
    }


def _rigid_body_patch_check(element: StatefulFiberBeam2D) -> dict[str, Any]:
    translation_x = 2.0e-3
    translation_y = -3.0e-3
    rotation = 1.2e-2
    local = np.asarray(
        [
            translation_x,
            translation_y,
            rotation,
            translation_x,
            translation_y + rotation * element.length_m,
            rotation,
        ],
        dtype=np.float64,
    )
    response = element.integrate(local, element.initial_state())
    maximum_strain = float(np.max(np.abs(response.generalized_strains)))
    force_norm = float(np.linalg.norm(response.internal_force_local, ord=np.inf))
    return {
        "local_displacements": local.tolist(),
        "maximum_generalized_strain_abs": maximum_strain,
        "internal_force_inf_norm": force_norm,
        "pass": bool(maximum_strain <= 1.0e-15 and force_norm <= 1.0e-9),
    }


def _elastic_cantilever_tip_load_check(
    element: StatefulFiberBeam2D,
) -> dict[str, Any]:
    tip_shear_kn = -10.0
    result = solve_stateful_fiber_beam2d_cantilever(
        element,
        element.initial_state(),
        target_tip_load=(0.0, tip_shear_kn, 0.0),
    )
    zero = element.integrate(
        np.zeros(6, dtype=np.float64),
        element.initial_state(),
    )
    flexural_rigidity = float(zero.section_responses[0].consistent_tangent[1, 1])
    length = element.length_m
    expected_transverse = tip_shear_kn * length**3 / (3.0 * flexural_rigidity)
    expected_rotation = tip_shear_kn * length**2 / (2.0 * flexural_rigidity)
    displacement_error = max(
        abs(result.solution_tip_displacements[1] - expected_transverse),
        abs(result.solution_tip_displacements[2] - expected_rotation),
    )
    expected_reaction = np.asarray(
        [0.0, -tip_shear_kn, -tip_shear_kn * length],
        dtype=np.float64,
    )
    reaction_error = float(
        np.linalg.norm(
            result.trial_response.internal_force_local[:3] - expected_reaction,
            ord=np.inf,
        )
    )
    return {
        "tip_shear_kn": tip_shear_kn,
        "flexural_rigidity_kn_m2": flexural_rigidity,
        "expected_tip_transverse_displacement_m": expected_transverse,
        "expected_tip_rotation_rad": expected_rotation,
        "solution_tip_displacements": list(result.solution_tip_displacements),
        "maximum_displacement_abs_error": displacement_error,
        "expected_base_reaction": expected_reaction.tolist(),
        "base_reaction": result.trial_response.internal_force_local[:3].tolist(),
        "base_reaction_inf_error": reaction_error,
        "newton_result": result.to_dict(),
        "pass": bool(
            result.committed
            and displacement_error <= 1.0e-12
            and reaction_error <= 1.0e-9
            and result.metrics["fallback_count"] == 0
            and result.metrics["regularization_count"] == 0
        ),
    }


def _manufactured_cantilever_path(
    element: StatefulFiberBeam2D,
    target_generalized_strains: tuple[tuple[float, float], ...],
) -> dict[str, Any]:
    state = element.initial_state()
    rows: list[dict[str, Any]] = []
    maximum_error = 0.0
    for step_index, (axial_strain, curvature) in enumerate(
        target_generalized_strains,
        start=1,
    ):
        truth_displacement = element.uniform_generalized_strain_displacements(
            axial_strain,
            curvature,
        )
        truth = element.integrate(truth_displacement, state)
        target = truth.internal_force_local[list(_FREE_TIP_DOFS)]
        result = solve_stateful_fiber_beam2d_cantilever(
            element,
            state,
            target_tip_load=target,
        )
        solution = _fixed_base_local_displacements(
            np.asarray(result.solution_tip_displacements, dtype=np.float64)
        )
        error = float(np.linalg.norm(solution - truth_displacement, ord=np.inf))
        maximum_error = max(maximum_error, error)
        rows.append(
            {
                "step_index": step_index,
                "manufactured_generalized_strain": [
                    axial_strain,
                    curvature,
                ],
                "manufactured_local_displacements": truth_displacement.tolist(),
                "manufactured_tip_load": target.tolist(),
                "solution_error_inf_norm": error,
                "newton_result": result.to_dict(),
            }
        )
        if not result.committed:
            break
        state = result.accepted_state
    return {
        "status": (
            "ready"
            if len(rows) == len(target_generalized_strains)
            and all(row["newton_result"]["committed"] for row in rows)
            else "blocked"
        ),
        "step_count": len(rows),
        "maximum_solution_error_inf_norm": maximum_error,
        "final_state": state.to_dict(),
        "steps": rows,
    }


def _quadratic_convergence_evidence(
    newton_step: dict[str, Any],
    *,
    local_residual_ceiling: float = 1.0e-1,
    minimum_observed_order: float = 1.8,
) -> dict[str, Any]:
    residuals = [
        float(row["scaled_residual_inf_norm"])
        for row in newton_step["newton_result"]["convergence_history"]
        if 0.0 < float(row["scaled_residual_inf_norm"]) <= local_residual_ceiling
    ]
    orders: list[float] = []
    for previous, current, following in zip(
        residuals,
        residuals[1:],
        residuals[2:],
        strict=False,
    ):
        denominator = math.log(current / previous)
        if previous > current > following > 0.0 and denominator != 0.0:
            orders.append(math.log(following / current) / denominator)
    return {
        "source_step_index": newton_step["step_index"],
        "local_residual_ceiling": local_residual_ceiling,
        "local_scaled_residual_inf_norms": residuals,
        "observed_orders": orders,
        "minimum_observed_order_required": minimum_observed_order,
        "pass": bool(len(orders) >= 2 and min(orders[-2:]) >= minimum_observed_order),
    }


@lru_cache(maxsize=1)
def _build_stateful_fiber_beam2d_benchmark_cached() -> dict[str, Any]:
    section = make_rectangular_stateful_rc_fiber_section()
    element = StatefulFiberBeam2D(section=section)
    initial = element.initial_state()
    elastic = _elastic_reference_check(element)
    rigid_body = _rigid_body_patch_check(element)
    elastic_cantilever = _elastic_cantilever_tip_load_check(element)
    tangent = finite_difference_stateful_fiber_beam2d_tangent_check(
        element,
        initial,
    )
    cyclic_generalized = (
        (-2.0e-4, 0.0),
        (-2.0e-4, 4.0e-3),
        (-2.0e-4, 9.0e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, -5.0e-3),
        (-2.0e-4, -9.0e-3),
        (-2.0e-4, 0.0),
    )
    cyclic = integrate_stateful_fiber_beam2d_history(
        element,
        tuple(
            element.uniform_generalized_strain_displacements(axial, curvature)
            for axial, curvature in cyclic_generalized
        ),
    )
    manufactured_targets = (
        (-5.0e-5, 0.0),
        (-1.0e-4, 1.5e-3),
        (-1.5e-4, 3.0e-3),
        (-2.0e-4, 4.5e-3),
        (-2.0e-4, 3.0e-3),
        (-2.0e-4, 0.0),
    )
    first = _manufactured_cantilever_path(element, manufactured_targets)
    repeated = _manufactured_cantilever_path(element, manufactured_targets)
    quadratic = _quadratic_convergence_evidence(
        max(
            first["steps"],
            key=lambda row: len(row["newton_result"]["convergence_history"]),
        )
    )
    damped_parent = element.initial_state()
    damped_target_generalized = (-1.0e-4, 1.5e-3)
    damped_truth_displacement = element.uniform_generalized_strain_displacements(
        *damped_target_generalized
    )
    damped_truth = element.integrate(
        damped_truth_displacement,
        damped_parent,
    )
    damped_initial_generalized = (1.0e-3, -2.0e-2)
    damped_initial_tip = element.uniform_generalized_strain_displacements(
        *damped_initial_generalized
    )[list(_FREE_TIP_DOFS)]
    damped_result = solve_stateful_fiber_beam2d_cantilever(
        element,
        damped_parent,
        target_tip_load=damped_truth.internal_force_local[list(_FREE_TIP_DOFS)],
        initial_tip_displacements=damped_initial_tip,
    )
    damped_solution = _fixed_base_local_displacements(
        np.asarray(damped_result.solution_tip_displacements, dtype=np.float64)
    )
    damped_solution_error = float(
        np.linalg.norm(
            damped_solution - damped_truth_displacement,
            ord=np.inf,
        )
    )
    selected_alphas = [
        float(row["selected_alpha"])
        for row in damped_result.line_search_history
        if float(row["selected_alpha"]) > 0.0
    ]
    damped_line_search_gate = bool(
        damped_result.committed
        and damped_solution_error <= 1.0e-10
        and damped_result.metrics["line_search_used"] is True
        and selected_alphas
        and min(selected_alphas) < 1.0
        and damped_result.metrics["parent_state_immutable"] is True
        and damped_result.metrics["fallback_count"] == 0
        and damped_result.metrics["regularization_count"] == 0
    )
    rollback_parent = element.initial_state()
    rollback_truth = element.integrate(
        element.uniform_generalized_strain_displacements(-2.0e-4, 6.0e-3),
        rollback_parent,
    )
    forced_failure = solve_stateful_fiber_beam2d_cantilever(
        element,
        rollback_parent,
        target_tip_load=rollback_truth.internal_force_local[list(_FREE_TIP_DOFS)],
        config=FiberBeamCantileverNewtonConfig(maximum_iterations=0),
    )
    nonlinear_parent = element.initial_state()
    nonlinear = element.integrate(
        element.uniform_generalized_strain_displacements(-3.0e-4, 6.0e-3),
        nonlinear_parent,
    )
    deterministic_replay_exact = first == repeated
    newton_gate = bool(
        first["status"] == "ready"
        and first["step_count"] == len(manufactured_targets)
        and first["maximum_solution_error_inf_norm"] <= 1.0e-10
        and all(
            row["newton_result"]["metrics"]["contract_pass"] is True
            and row["newton_result"]["metrics"]["parent_state_immutable"] is True
            and row["newton_result"]["metrics"]["fallback_count"] == 0
            and row["newton_result"]["metrics"]["regularization_count"] == 0
            for row in first["steps"]
        )
    )
    rollback_gate = bool(
        forced_failure.status == "blocked"
        and forced_failure.accepted_state is rollback_parent
        and forced_failure.accepted_state.canonical_bytes()
        == rollback_parent.canonical_bytes()
        and forced_failure.metrics["rollback_exact"] is True
    )
    cyclic_gate = bool(
        cyclic["curvature_reversal_count"] >= 2
        and cyclic["yielded_step_count"] > 0
        and cyclic["concrete_damage_step_count"] > 0
        and cyclic["dissipated_energy_nonnegative_monotonic"] is True
        and cyclic["final_dissipated_energy_mj"] > 0.0
    )
    gauss_state_gate = bool(
        nonlinear.yielded_integration_point_count == element.integration_order
        and nonlinear.damaged_integration_point_count == element.integration_order
        and all(
            state.step_index == 1 for state in nonlinear.state.integration_point_states
        )
    )
    section_parent_binding_gate = all(
        response.parent_state_hash == parent.state_hash
        for response, parent in zip(
            nonlinear.section_responses,
            nonlinear_parent.integration_point_states,
            strict=True,
        )
    )
    contract_pass = bool(
        elastic["pass"] is True
        and rigid_body["pass"] is True
        and elastic_cantilever["pass"] is True
        and tangent["pass"] is True
        and tangent["tangent_symmetry_error"] <= 1.0e-10
        and cyclic_gate
        and newton_gate
        and quadratic["pass"] is True
        and damped_line_search_gate
        and rollback_gate
        and deterministic_replay_exact
        and gauss_state_gate
        and section_parent_binding_gate
    )
    return {
        "schema_version": STATEFUL_FIBER_BEAM2D_BENCHMARK_SCHEMA_VERSION,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": element.element_id,
        "analysis_type": "stateful_rc_fiber_beam2d_cantilever_newton",
        "element_contract_hash": element.contract_hash,
        "section_contract_hash": section.contract_hash,
        "length_m": element.length_m,
        "integration_order": element.integration_order,
        "elastic_reference": elastic,
        "rigid_body_patch": rigid_body,
        "elastic_cantilever_tip_load": elastic_cantilever,
        "tangent_finite_difference": tangent,
        "cyclic_history": cyclic,
        "manufactured_cantilever_path": first,
        "quadratic_convergence": quadratic,
        "damped_line_search": {
            "manufactured_target_generalized_strain": list(damped_target_generalized),
            "initial_generalized_strain": list(damped_initial_generalized),
            "solution_error_inf_norm": damped_solution_error,
            "minimum_selected_alpha": min(selected_alphas, default=0.0),
            "newton_result": damped_result.to_dict(),
            "gate_passed": damped_line_search_gate,
        },
        "forced_failure_rollback": forced_failure.to_dict(),
        "verification": {
            "elastic_euler_bernoulli_reference_passed": elastic["pass"],
            "elastic_tangent_relative_inf_error": elastic["relative_inf_error"],
            "rigid_body_patch_passed": rigid_body["pass"],
            "rigid_body_internal_force_inf_norm": rigid_body["internal_force_inf_norm"],
            "elastic_cantilever_tip_load_passed": elastic_cantilever["pass"],
            "elastic_cantilever_displacement_abs_error": (
                elastic_cantilever["maximum_displacement_abs_error"]
            ),
            "elastic_cantilever_reaction_inf_error": elastic_cantilever[
                "base_reaction_inf_error"
            ],
            "consistent_6x6_tangent_finite_difference_passed": tangent["pass"],
            "consistent_6x6_tangent_relative_inf_error": tangent["relative_inf_error"],
            "tangent_symmetry_error": tangent["tangent_symmetry_error"],
            "cyclic_gauss_state_and_energy_gate_passed": cyclic_gate,
            "manufactured_cantilever_newton_gate_passed": newton_gate,
            "manufactured_cantilever_step_count": first["step_count"],
            "maximum_manufactured_solution_error_inf_norm": first[
                "maximum_solution_error_inf_norm"
            ],
            "quadratic_convergence_gate_passed": quadratic["pass"],
            "minimum_tail_observed_convergence_order": min(
                quadratic["observed_orders"][-2:],
                default=0.0,
            ),
            "damped_line_search_gate_passed": damped_line_search_gate,
            "damped_line_search_minimum_alpha": min(
                selected_alphas,
                default=0.0,
            ),
            "damped_line_search_solution_error_inf_norm": (damped_solution_error),
            "gauss_point_state_coupling_passed": gauss_state_gate,
            "section_response_parent_binding_passed": (section_parent_binding_gate),
            "deterministic_replay_exact": deterministic_replay_exact,
            "forced_failure_rollback_exact": rollback_gate,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "verification_hierarchy": {
            "level_1_analytic_and_manufactured": contract_pass,
            "level_2_external_code_to_code": False,
            "level_3_published_benchmark": False,
            "level_4_experimental": False,
            "level_5_customer_shadow": False,
        },
        "claims": {
            "bounded_stateful_rc_fiber_beam2d_element": contract_pass,
            "small_displacement_euler_bernoulli_kinematics": elastic["pass"],
            "gauss_point_path_dependent_section_states": (
                cyclic_gate and gauss_state_gate
            ),
            "consistent_6x6_material_tangent": tangent["pass"],
            "single_element_fixed_base_cantilever_equilibrium": (
                elastic_cantilever["pass"]
                and newton_gate
                and damped_line_search_gate
                and rollback_gate
            ),
            "authoritative_restart_chain": False,
            "product_commit_path": False,
            "generalized_axial_curvature_section_protocol": False,
            "coordinate_transformed_general_frame": False,
            "multi_element_global_assembly": False,
            "shear_deformation_or_torsion": False,
            "geometric_nonlinearity": False,
            "general_plastic_hinge_or_distributed_plasticity": False,
            "fracture_energy_regularization_or_mesh_objectivity": False,
            "external_validation": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "element_state_parent_hash_and_checkpoint_epoch_not_connected",
            "diagnostic_history_is_not_an_authoritative_product_commit_path",
            "generalized_axial_curvature_section_protocol_not_extracted",
            "element_state_response_and_diagnostics_module_split_pending",
            "local_to_global_coordinate_transformation_not_connected",
            "multi_element_global_assembly_not_connected",
            "shear_deformation_and_torsion_not_implemented",
            "geometric_nonlinearity_not_coupled",
            "general_plastic_hinge_and_distributed_plasticity_not_validated",
            "fracture_energy_regularization_and_mesh_objectivity_not_verified",
            "external_code_to_code_published_and_experimental_receipts_missing",
            "production_sparse_and_rocm_hip_paths_not_connected",
            "full_building_equilibrium_not_demonstrated",
            "g1_closure_not_claimed",
        ],
        "claim_boundary": STATEFUL_FIBER_BEAM2D_CLAIM_BOUNDARY,
    }


def build_stateful_fiber_beam2d_benchmark() -> dict[str, Any]:
    """Return a deterministic Level-1 element/cantilever receipt."""

    return deepcopy(_build_stateful_fiber_beam2d_benchmark_cached())


__all__ = [
    "STATEFUL_FIBER_BEAM2D_BENCHMARK_SCHEMA_VERSION",
    "STATEFUL_FIBER_BEAM2D_CLAIM_BOUNDARY",
    "STATEFUL_FIBER_BEAM2D_NEWTON_SCHEMA_VERSION",
    "FiberBeamCantileverNewtonConfig",
    "FiberBeamCantileverNewtonResult",
    "build_stateful_fiber_beam2d_benchmark",
    "solve_stateful_fiber_beam2d_cantilever",
]
