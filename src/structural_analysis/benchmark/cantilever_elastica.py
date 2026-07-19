"""Bounded large-rotation cantilever elastica verification benchmark.

This module compares a first-integral reference solution for an inextensible
planar Euler elastica with an independently discretized rotation-field energy.
It is a verification kernel for one conservative dead-tip-load problem, not a
production corotational beam, general frame/shell, or material-geometric solver.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from scipy.integrate import quad
from scipy.optimize import brentq


CANTILEVER_ELASTICA_SCHEMA_VERSION = (
    "phase2-cantilever-elastica-large-rotation-result.v1"
)
CONTINUUM_ELASTICA_FORMULATION = (
    "inextensible_planar_euler_elastica_conservative_dead_tip_force"
)
DISCRETE_ELASTICA_FORMULATION = (
    "piecewise_linear_rotation_energy_with_two_point_gauss_quadrature"
)

_GAUSS_POINTS = (-1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0))
_REFERENCE_QUADRATURE_TOLERANCE = 1.0e-10


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _free_rotation_vector(values: np.ndarray) -> np.ndarray:
    rotations = np.asarray(values, dtype=np.float64)
    if rotations.ndim != 1 or rotations.size == 0:
        raise ValueError("free_rotations_rad must be a non-empty 1D array")
    if not np.all(np.isfinite(rotations)):
        raise ValueError("free_rotations_rad must contain only finite values")
    return rotations


def _transformed_elastica_integral(
    *,
    tip_rotation_rad: float,
    dimensionless_load: float,
    observable: Callable[[float], float],
) -> tuple[float, float]:
    """Integrate over rotation after removing the free-tip square-root singularity."""

    if tip_rotation_rad == 0.0:
        return 0.0, 0.0
    upper = math.sqrt(tip_rotation_rad)

    def integrand(root_rotation_gap: float) -> float:
        if root_rotation_gap == 0.0:
            endpoint_scale = math.sqrt(
                2.0 * dimensionless_load * math.cos(tip_rotation_rad)
            )
            return 2.0 * observable(tip_rotation_rad) / endpoint_scale
        gap_squared = root_rotation_gap**2
        rotation = tip_rotation_rad - gap_squared
        sine_difference = (
            2.0
            * math.cos(tip_rotation_rad - 0.5 * gap_squared)
            * math.sin(0.5 * gap_squared)
        )
        denominator = math.sqrt(2.0 * dimensionless_load * sine_difference)
        return 2.0 * root_rotation_gap * observable(rotation) / denominator

    value, error = quad(
        integrand,
        0.0,
        upper,
        epsabs=_REFERENCE_QUADRATURE_TOLERANCE,
        epsrel=_REFERENCE_QUADRATURE_TOLERANCE,
        limit=200,
    )
    return float(value), float(error)


def cantilever_elastica_reference(
    *,
    dimensionless_load: float = 4.0,
) -> dict[str, Any]:
    """Return the continuum first-integral solution for a vertical dead tip load.

    The nondimensional load is ``alpha = P L^2 / EI``. Rotation and transverse
    coordinates are positive in the load (downward) direction.
    """

    load = _positive_finite(dimensionless_load, "dimensionless_load")
    # Staying slightly inside pi/2 avoids asking adaptive quadrature to resolve
    # the logarithmic limiting configuration at float64 endpoint precision.
    upper_rotation = 0.5 * math.pi - 1.0e-8

    def length_constraint(tip_rotation: float) -> float:
        value, _ = _transformed_elastica_integral(
            tip_rotation_rad=tip_rotation,
            dimensionless_load=load,
            observable=lambda _rotation: 1.0,
        )
        return value - 1.0

    upper_constraint = length_constraint(upper_rotation)
    if upper_constraint <= 0.0:
        raise ValueError(
            "dimensionless_load is too large for the principal branch "
            "at float64 resolution"
        )
    tip_rotation, root_result = brentq(
        length_constraint,
        0.0,
        upper_rotation,
        xtol=1.0e-13,
        rtol=1.0e-13,
        full_output=True,
        disp=True,
    )
    normalized_length, length_error = _transformed_elastica_integral(
        tip_rotation_rad=tip_rotation,
        dimensionless_load=load,
        observable=lambda _rotation: 1.0,
    )
    tip_x, x_error = _transformed_elastica_integral(
        tip_rotation_rad=tip_rotation,
        dimensionless_load=load,
        observable=math.cos,
    )
    tip_downward_y, y_error = _transformed_elastica_integral(
        tip_rotation_rad=tip_rotation,
        dimensionless_load=load,
        observable=math.sin,
    )
    return {
        "method": "first_integral_endpoint_root_and_regularized_quadrature",
        "dimensionless_load": load,
        "tip_rotation_rad": float(tip_rotation),
        "tip_x_over_length": tip_x,
        "tip_downward_y_over_length": tip_downward_y,
        "normalized_arc_length": normalized_length,
        "length_constraint_abs_error": abs(normalized_length - 1.0),
        "quadrature_abs_error_estimates": {
            "arc_length": length_error,
            "tip_x": x_error,
            "tip_downward_y": y_error,
        },
        "root_iterations": int(root_result.iterations),
        "root_converged": bool(root_result.converged),
        "principal_branch": True,
        "tip_rotation_interval_rad": [0.0, 0.5 * math.pi],
    }


def assemble_discrete_cantilever_elastica(
    free_rotations_rad: np.ndarray,
    *,
    dimensionless_load: float,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Assemble nondimensional energy, exact gradient, and exact Hessian.

    The fixed root rotation is excluded from ``free_rotations_rad``. Each entry
    therefore corresponds to one element and one free nodal rotation.
    """

    rotations = _free_rotation_vector(free_rotations_rad)
    load = _positive_finite(dimensionless_load, "dimensionless_load")
    element_count = int(rotations.size)
    element_length = 1.0 / element_count
    all_rotations = np.concatenate((np.zeros(1, dtype=np.float64), rotations))
    energy = 0.0
    full_residual = np.zeros(element_count + 1, dtype=np.float64)
    full_tangent = np.zeros(
        (element_count + 1, element_count + 1),
        dtype=np.float64,
    )
    bending_tangent = (
        np.asarray(
            [[1.0, -1.0], [-1.0, 1.0]],
            dtype=np.float64,
        )
        / element_length
    )

    for element_index in range(element_count):
        indices = (element_index, element_index + 1)
        element_rotations = all_rotations[list(indices)]
        rotation_increment = float(element_rotations[1] - element_rotations[0])
        energy += 0.5 * rotation_increment**2 / element_length
        full_residual[element_index] -= rotation_increment / element_length
        full_residual[element_index + 1] += rotation_increment / element_length
        full_tangent[np.ix_(indices, indices)] += bending_tangent

        for gauss_coordinate in _GAUSS_POINTS:
            shape = np.asarray(
                [
                    0.5 * (1.0 - gauss_coordinate),
                    0.5 * (1.0 + gauss_coordinate),
                ],
                dtype=np.float64,
            )
            rotation = float(shape @ element_rotations)
            integration_weight = 0.5 * element_length
            energy -= load * integration_weight * math.sin(rotation)
            full_residual[list(indices)] -= (
                load * integration_weight * math.cos(rotation) * shape
            )
            full_tangent[np.ix_(indices, indices)] += (
                load * integration_weight * math.sin(rotation) * np.outer(shape, shape)
            )

    return (
        float(energy),
        full_residual[1:],
        full_tangent[1:, 1:],
    )


def discrete_cantilever_tip_coordinates(
    free_rotations_rad: np.ndarray,
) -> tuple[float, float]:
    """Integrate normalized tip coordinates from the discrete rotation field."""

    rotations = _free_rotation_vector(free_rotations_rad)
    element_count = int(rotations.size)
    element_length = 1.0 / element_count
    all_rotations = np.concatenate((np.zeros(1, dtype=np.float64), rotations))
    tip_x = 0.0
    tip_downward_y = 0.0
    for element_index in range(element_count):
        element_rotations = all_rotations[element_index : element_index + 2]
        for gauss_coordinate in _GAUSS_POINTS:
            shape = np.asarray(
                [
                    0.5 * (1.0 - gauss_coordinate),
                    0.5 * (1.0 + gauss_coordinate),
                ],
                dtype=np.float64,
            )
            rotation = float(shape @ element_rotations)
            integration_weight = 0.5 * element_length
            tip_x += integration_weight * math.cos(rotation)
            tip_downward_y += integration_weight * math.sin(rotation)
    return float(tip_x), float(tip_downward_y)


def solve_discrete_cantilever_elastica(
    *,
    element_count: int,
    dimensionless_load: float = 4.0,
    load_step_count: int = 16,
    residual_tolerance: float = 1.0e-11,
    maximum_newton_iterations: int = 30,
    maximum_line_search_reductions: int = 20,
) -> dict[str, Any]:
    """Solve the discrete energy stationarity equations by load continuation."""

    count = _positive_integer(element_count, "element_count")
    load = _positive_finite(dimensionless_load, "dimensionless_load")
    step_count = _positive_integer(load_step_count, "load_step_count")
    tolerance = _positive_finite(residual_tolerance, "residual_tolerance")
    iteration_limit = _positive_integer(
        maximum_newton_iterations,
        "maximum_newton_iterations",
    )
    reduction_limit = _positive_integer(
        maximum_line_search_reductions,
        "maximum_line_search_reductions",
    )
    rotations = np.zeros(count, dtype=np.float64)
    step_receipts: list[dict[str, Any]] = []
    total_newton_corrections = 0
    total_line_search_reductions = 0

    for load_step_index in range(1, step_count + 1):
        step_load = load * load_step_index / step_count
        step_corrections = 0
        step_reductions = 0
        accepted = False
        for _iteration in range(iteration_limit + 1):
            energy, residual, tangent = assemble_discrete_cantilever_elastica(
                rotations,
                dimensionless_load=step_load,
            )
            residual_norm = float(np.linalg.norm(residual, ord=np.inf))
            if residual_norm <= tolerance:
                accepted = True
                break
            if step_corrections >= iteration_limit:
                break
            try:
                correction = np.linalg.solve(tangent, -residual)
            except np.linalg.LinAlgError as exc:
                raise RuntimeError(
                    "discrete elastica tangent solve failed without fallback"
                ) from exc
            directional_derivative = float(residual @ correction)
            if not math.isfinite(directional_derivative) or (
                directional_derivative >= 0.0
            ):
                raise RuntimeError(
                    "discrete elastica Newton direction is not an energy "
                    "descent direction"
                )
            floating_energy_floor = (
                32.0 * np.finfo(np.float64).eps * max(1.0, abs(energy))
            )
            step_scale = 1.0
            trial_accepted = False
            for reduction in range(reduction_limit + 1):
                trial_rotations = rotations + step_scale * correction
                trial_energy, _, _ = assemble_discrete_cantilever_elastica(
                    trial_rotations,
                    dimensionless_load=step_load,
                )
                armijo_bound = (
                    energy
                    + 1.0e-4 * step_scale * directional_derivative
                    + floating_energy_floor
                )
                if trial_energy <= armijo_bound:
                    trial_accepted = True
                    step_reductions += reduction
                    break
                step_scale *= 0.5
            if not trial_accepted:
                raise RuntimeError(
                    "discrete elastica line search failed without fallback"
                )
            rotations = trial_rotations
            step_corrections += 1

        if not accepted:
            raise RuntimeError(
                "discrete elastica Newton solve exceeded its iteration limit"
            )
        total_newton_corrections += step_corrections
        total_line_search_reductions += step_reductions
        step_receipts.append(
            {
                "load_step_index": load_step_index,
                "dimensionless_load": step_load,
                "newton_correction_count": step_corrections,
                "line_search_reduction_count": step_reductions,
                "residual_inf": residual_norm,
                "accepted": True,
            }
        )

    energy, residual, tangent = assemble_discrete_cantilever_elastica(
        rotations,
        dimensionless_load=load,
    )
    tip_x, tip_downward_y = discrete_cantilever_tip_coordinates(rotations)
    symmetry_error = float(np.max(np.abs(tangent - tangent.T), initial=0.0))
    minimum_tangent_eigenvalue = float(np.linalg.eigvalsh(tangent)[0])
    return {
        "element_count": count,
        "free_rotation_dof_count": count,
        "dimensionless_load": load,
        "load_step_count": step_count,
        "initialization": "zero_rotation_then_previous_accepted_load_state",
        "nodal_rotations_rad": [0.0, *rotations.tolist()],
        "tip_rotation_rad": float(rotations[-1]),
        "tip_x_over_length": tip_x,
        "tip_downward_y_over_length": tip_downward_y,
        "dimensionless_total_potential_energy": energy,
        "final_residual_inf": float(np.linalg.norm(residual, ord=np.inf)),
        "tangent_symmetry_abs_max": symmetry_error,
        "minimum_tangent_eigenvalue": minimum_tangent_eigenvalue,
        "newton_correction_count": total_newton_corrections,
        "line_search_reduction_count": total_line_search_reductions,
        "load_step_receipts": step_receipts,
        "all_load_steps_accepted": all(
            receipt["accepted"] for receipt in step_receipts
        ),
        "regularization_count": 0,
        "fallback_count": 0,
    }


def finite_difference_cantilever_elastica_checks(
    *,
    element_count: int = 7,
    dimensionless_load: float = 2.3,
    perturbation: float = 1.0e-5,
) -> dict[str, Any]:
    """Check that residual and tangent are the energy gradient and Hessian."""

    count = _positive_integer(element_count, "element_count")
    load = _positive_finite(dimensionless_load, "dimensionless_load")
    delta = _positive_finite(perturbation, "perturbation")
    normalized_nodes = np.linspace(0.0, 1.0, count + 1)[1:]
    rotations = 0.45 * (2.0 * normalized_nodes - normalized_nodes**2)
    _, residual, tangent = assemble_discrete_cantilever_elastica(
        rotations,
        dimensionless_load=load,
    )
    finite_difference_gradient = np.zeros(count, dtype=np.float64)
    finite_difference_hessian = np.zeros((count, count), dtype=np.float64)
    for column in range(count):
        offset = np.zeros(count, dtype=np.float64)
        offset[column] = delta
        positive_energy, positive_residual, _ = assemble_discrete_cantilever_elastica(
            rotations + offset,
            dimensionless_load=load,
        )
        negative_energy, negative_residual, _ = assemble_discrete_cantilever_elastica(
            rotations - offset,
            dimensionless_load=load,
        )
        finite_difference_gradient[column] = (positive_energy - negative_energy) / (
            2.0 * delta
        )
        finite_difference_hessian[:, column] = (
            positive_residual - negative_residual
        ) / (2.0 * delta)

    gradient_scale = max(
        1.0,
        float(np.linalg.norm(residual, ord=np.inf)),
        float(np.linalg.norm(finite_difference_gradient, ord=np.inf)),
    )
    hessian_scale = max(
        1.0,
        float(np.linalg.norm(tangent, ord=np.inf)),
        float(np.linalg.norm(finite_difference_hessian, ord=np.inf)),
    )
    gradient_relative_error = (
        float(
            np.linalg.norm(
                residual - finite_difference_gradient,
                ord=np.inf,
            )
        )
        / gradient_scale
    )
    hessian_relative_error = (
        float(
            np.linalg.norm(
                tangent - finite_difference_hessian,
                ord=np.inf,
            )
        )
        / hessian_scale
    )
    symmetry_error = float(np.max(np.abs(tangent - tangent.T), initial=0.0))
    contract_pass = bool(
        gradient_relative_error <= 1.0e-8
        and hessian_relative_error <= 1.0e-8
        and symmetry_error <= 1.0e-12
    )
    return {
        "element_count": count,
        "dimensionless_load": load,
        "perturbation": delta,
        "energy_gradient_relative_error": gradient_relative_error,
        "tangent_hessian_relative_error": hessian_relative_error,
        "tangent_symmetry_abs_max": symmetry_error,
        "contract_pass": contract_pass,
    }


def _observed_orders(errors: list[float], counts: tuple[int, ...]) -> list[float]:
    return [
        math.log(errors[index] / errors[index + 1])
        / math.log(counts[index + 1] / counts[index])
        for index in range(len(errors) - 1)
    ]


def cantilever_elastica_large_rotation_benchmark(
    *,
    element_counts: tuple[int, ...] = (8, 16, 32, 64),
    dimensionless_load: float = 4.0,
    load_step_count: int = 16,
) -> dict[str, Any]:
    """Build the continuum-reference and discrete mesh-convergence receipt."""

    if len(element_counts) < 3:
        raise ValueError("element_counts must contain at least three meshes")
    counts = tuple(
        _positive_integer(value, "element_count") for value in element_counts
    )
    if any(right <= left for left, right in zip(counts, counts[1:])):
        raise ValueError("element_counts must be strictly increasing")
    load = _positive_finite(dimensionless_load, "dimensionless_load")
    step_count = _positive_integer(load_step_count, "load_step_count")
    reference = cantilever_elastica_reference(dimensionless_load=load)
    finite_difference = finite_difference_cantilever_elastica_checks(
        dimensionless_load=load
    )
    error_keys = (
        "tip_rotation_abs_error_rad",
        "tip_x_over_length_abs_error",
        "tip_downward_y_over_length_abs_error",
    )
    errors = {key: [] for key in error_keys}
    mesh_rows: list[dict[str, Any]] = []

    for count in counts:
        solution = solve_discrete_cantilever_elastica(
            element_count=count,
            dimensionless_load=load,
            load_step_count=step_count,
        )
        row_errors = {
            "tip_rotation_abs_error_rad": abs(
                solution["tip_rotation_rad"] - reference["tip_rotation_rad"]
            ),
            "tip_x_over_length_abs_error": abs(
                solution["tip_x_over_length"] - reference["tip_x_over_length"]
            ),
            "tip_downward_y_over_length_abs_error": abs(
                solution["tip_downward_y_over_length"]
                - reference["tip_downward_y_over_length"]
            ),
        }
        for key, value in row_errors.items():
            errors[key].append(float(value))
        row_contract_pass = bool(
            solution["all_load_steps_accepted"]
            and solution["final_residual_inf"] <= 1.0e-9
            and solution["tangent_symmetry_abs_max"] <= 1.0e-12
            and solution["minimum_tangent_eigenvalue"] > 0.0
            and solution["regularization_count"] == 0
            and solution["fallback_count"] == 0
            and max(row_errors.values()) <= 3.0e-3
        )
        mesh_rows.append(
            {
                **solution,
                **row_errors,
                "contract_pass": row_contract_pass,
            }
        )

    order_labels = {
        "tip_rotation_abs_error_rad": "tip_rotation_rad",
        "tip_x_over_length_abs_error": "tip_x_over_length",
        "tip_downward_y_over_length_abs_error": ("tip_downward_y_over_length"),
    }
    observed_orders = {
        order_labels[key]: _observed_orders(values, counts)
        for key, values in errors.items()
    }
    monotonic_convergence = {
        key: all(later < earlier for earlier, later in zip(values, values[1:]))
        for key, values in errors.items()
    }
    minimum_observed_order = min(
        order for orders in observed_orders.values() for order in orders
    )
    finest_errors = {key: values[-1] for key, values in errors.items()}
    linear_tip_downward_y = load / 3.0
    nonlinear_to_linear_displacement_ratio = (
        reference["tip_downward_y_over_length"] / linear_tip_downward_y
    )
    large_rotation_contract_pass = bool(
        reference["tip_rotation_rad"] >= 1.0
        and reference["tip_downward_y_over_length"] >= 0.6
        and nonlinear_to_linear_displacement_ratio <= 0.6
    )
    mesh_contract_pass = bool(
        all(row["contract_pass"] for row in mesh_rows)
        and all(monotonic_convergence.values())
        and minimum_observed_order >= 1.9
        and max(finest_errors.values()) <= 5.0e-5
    )
    contract_pass = bool(
        reference["root_converged"]
        and reference["length_constraint_abs_error"] <= 1.0e-10
        and finite_difference["contract_pass"]
        and mesh_contract_pass
        and large_rotation_contract_pass
    )
    return {
        "schema_version": CANTILEVER_ELASTICA_SCHEMA_VERSION,
        "benchmark_id": "cantilever-elastica-large-rotation-v1",
        "status": "partial",
        "continuum_formulation": CONTINUUM_ELASTICA_FORMULATION,
        "discrete_formulation": DISCRETE_ELASTICA_FORMULATION,
        "reference": reference,
        "finite_difference_checks": finite_difference,
        "mesh_rows": mesh_rows,
        "observed_convergence_orders": observed_orders,
        "monotonic_convergence": monotonic_convergence,
        "minimum_observed_convergence_order": minimum_observed_order,
        "finest_mesh_abs_errors": finest_errors,
        "large_rotation_checks": {
            "small_rotation_linear_tip_downward_y_over_length": (linear_tip_downward_y),
            "nonlinear_to_linear_displacement_ratio": (
                nonlinear_to_linear_displacement_ratio
            ),
            "contract_pass": large_rotation_contract_pass,
        },
        "mesh_convergence_contract_pass": mesh_contract_pass,
        "implemented_benchmark_contract_pass": contract_pass,
        "contract_pass": contract_pass,
        "continuum_cantilever_large_rotation_benchmark_claim": contract_pass,
        "production_corotational_beam_validation_claim": False,
        "lee_frame_snapthrough_claim": False,
        "general_geometric_nonlinear_frame_or_shell_claim": False,
        "material_geometric_coupling_claim": False,
        "production_sparse_or_hip_solver_claim": False,
        "geometric_nonlinear_benchmark_breadth_claim": False,
        "g1_closure_claim": False,
    }
