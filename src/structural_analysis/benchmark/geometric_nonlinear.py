"""Narrow analytic geometric-nonlinear benchmark seeds.

The functions here are verification kernels, not a general frame solver.  They
cover a pinned Euler column, modal P-Delta amplification, and the exact
displacement-controlled equilibrium path of a two-bar shallow arch.  The
separation is intentional: none of these kernels may be used to claim Lee-frame,
arc-length, continuum-cantilever, or general 2D/3D frame capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
from scipy.linalg import eigh


GEOMETRIC_BENCHMARK_SCHEMA_VERSION = (
    "phase2-geometric-nonlinear-benchmark-result.v1"
)
EULER_ELEMENT_FORMULATION = "euler_bernoulli_beam_column_consistent_geometric"
PDELTA_FORMULATION = "modal_second_order_K_minus_PKg"
SHALLOW_ARCH_FORMULATION = "exact_two_bar_corotational_truss_displacement_control"


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _positive_element_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("element_count must be a positive integer")
    return value


@dataclass(frozen=True)
class EulerColumnSystem:
    """Reduced pinned-pinned Euler-Bernoulli beam-column matrices."""

    element_count: int
    length_m: float
    flexural_rigidity_kn_m2: float
    node_positions_m: tuple[float, ...]
    free_dofs: tuple[int, ...]
    elastic_stiffness: np.ndarray
    unit_compression_geometric_stiffness: np.ndarray

    @property
    def full_dof_count(self) -> int:
        return 2 * (self.element_count + 1)


def assemble_euler_column_system(
    *,
    element_count: int,
    length_m: float = 3.0,
    flexural_rigidity_kn_m2: float = 10_000.0,
) -> EulerColumnSystem:
    """Assemble reduced ``K`` and unit-compression ``Kg`` for a pinned column."""

    count = _positive_element_count(element_count)
    length = _positive_finite(length_m, "length_m")
    rigidity = _positive_finite(
        flexural_rigidity_kn_m2,
        "flexural_rigidity_kn_m2",
    )
    element_length = length / count
    dof_count = 2 * (count + 1)
    elastic = np.zeros((dof_count, dof_count), dtype=np.float64)
    geometric = np.zeros_like(elastic)
    le = element_length
    elastic_element = (rigidity / le**3) * np.asarray(
        [
            [12.0, 6.0 * le, -12.0, 6.0 * le],
            [6.0 * le, 4.0 * le**2, -6.0 * le, 2.0 * le**2],
            [-12.0, -6.0 * le, 12.0, -6.0 * le],
            [6.0 * le, 2.0 * le**2, -6.0 * le, 4.0 * le**2],
        ],
        dtype=np.float64,
    )
    geometric_element = (1.0 / (30.0 * le)) * np.asarray(
        [
            [36.0, 3.0 * le, -36.0, 3.0 * le],
            [3.0 * le, 4.0 * le**2, -3.0 * le, -(le**2)],
            [-36.0, -3.0 * le, 36.0, -3.0 * le],
            [3.0 * le, -(le**2), -3.0 * le, 4.0 * le**2],
        ],
        dtype=np.float64,
    )
    for element_index in range(count):
        dofs = (
            2 * element_index,
            2 * element_index + 1,
            2 * element_index + 2,
            2 * element_index + 3,
        )
        elastic[np.ix_(dofs, dofs)] += elastic_element
        geometric[np.ix_(dofs, dofs)] += geometric_element

    constrained_translations = {0, 2 * count}
    free_dofs = tuple(
        dof for dof in range(dof_count) if dof not in constrained_translations
    )
    reduced_elastic = elastic[np.ix_(free_dofs, free_dofs)]
    reduced_geometric = geometric[np.ix_(free_dofs, free_dofs)]
    reduced_elastic.setflags(write=False)
    reduced_geometric.setflags(write=False)
    return EulerColumnSystem(
        element_count=count,
        length_m=length,
        flexural_rigidity_kn_m2=rigidity,
        node_positions_m=tuple(np.linspace(0.0, length, count + 1)),
        free_dofs=free_dofs,
        elastic_stiffness=reduced_elastic,
        unit_compression_geometric_stiffness=reduced_geometric,
    )


def _first_buckling_mode(system: EulerColumnSystem) -> tuple[float, np.ndarray]:
    eigenvalues, eigenvectors = eigh(
        system.elastic_stiffness,
        system.unit_compression_geometric_stiffness,
        check_finite=True,
    )
    positive = np.flatnonzero(eigenvalues > 0.0)
    if positive.size == 0:
        raise ValueError("column system has no positive buckling eigenvalue")
    index = int(positive[0])
    eigenvalue = float(eigenvalues[index])
    mode = np.asarray(eigenvectors[:, index], dtype=np.float64)
    mode /= float(np.linalg.norm(mode))

    full_mode = np.zeros(system.full_dof_count, dtype=np.float64)
    full_mode[np.asarray(system.free_dofs)] = mode
    translations = full_mode[::2]
    pivot = int(np.argmax(np.abs(translations)))
    if translations[pivot] < 0.0:
        mode = -mode
    return eigenvalue, mode


def _full_mode(system: EulerColumnSystem, reduced_mode: np.ndarray) -> np.ndarray:
    full = np.zeros(system.full_dof_count, dtype=np.float64)
    full[np.asarray(system.free_dofs)] = reduced_mode
    return full


def _matrix_symmetry_error(matrix: np.ndarray) -> float:
    return float(np.max(np.abs(matrix - matrix.T), initial=0.0))


def _normalized_generalized_eigen_residual(
    elastic: np.ndarray,
    geometric: np.ndarray,
    eigenvalue: float,
    mode: np.ndarray,
) -> float:
    left = elastic @ mode
    right = eigenvalue * (geometric @ mode)
    scale = max(
        float(np.linalg.norm(left, ord=np.inf)),
        float(np.linalg.norm(right, ord=np.inf)),
        np.finfo(np.float64).tiny,
    )
    return float(np.linalg.norm(left - right, ord=np.inf)) / scale


def _modal_assurance(reference: np.ndarray, actual: np.ndarray) -> float:
    numerator = float(np.dot(reference, actual)) ** 2
    denominator = float(np.dot(reference, reference) * np.dot(actual, actual))
    if denominator <= 0.0:
        return 0.0
    return min(1.0, max(0.0, numerator / denominator))


def euler_column_buckling_benchmark(
    *,
    element_counts: tuple[int, ...] = (2, 4, 8, 16),
    length_m: float = 3.0,
    flexural_rigidity_kn_m2: float = 10_000.0,
) -> dict[str, Any]:
    """Compare FE buckling loads and modes with the pinned Euler solution."""

    if len(element_counts) < 3:
        raise ValueError("element_counts must contain at least three meshes")
    counts = tuple(_positive_element_count(value) for value in element_counts)
    if any(right <= left for left, right in zip(counts, counts[1:])):
        raise ValueError("element_counts must be strictly increasing")
    length = _positive_finite(length_m, "length_m")
    rigidity = _positive_finite(
        flexural_rigidity_kn_m2,
        "flexural_rigidity_kn_m2",
    )
    exact_critical_load = math.pi**2 * rigidity / length**2
    rows: list[dict[str, Any]] = []
    errors: list[float] = []
    for count in counts:
        system = assemble_euler_column_system(
            element_count=count,
            length_m=length,
            flexural_rigidity_kn_m2=rigidity,
        )
        critical_load, reduced_mode = _first_buckling_mode(system)
        full_mode = _full_mode(system, reduced_mode)
        translations = full_mode[::2]
        translation_scale = float(np.max(np.abs(translations)))
        normalized_translations = translations / translation_scale
        exact_mode = np.sin(
            math.pi * np.asarray(system.node_positions_m, dtype=float) / length
        )
        relative_error = abs(critical_load - exact_critical_load) / exact_critical_load
        eigen_residual = _normalized_generalized_eigen_residual(
            system.elastic_stiffness,
            system.unit_compression_geometric_stiffness,
            critical_load,
            reduced_mode,
        )
        mode_mac = _modal_assurance(exact_mode, normalized_translations)
        symmetry_error = max(
            _matrix_symmetry_error(system.elastic_stiffness),
            _matrix_symmetry_error(
                system.unit_compression_geometric_stiffness
            ),
        )
        errors.append(relative_error)
        rows.append(
            {
                "element_count": count,
                "element_length_m": length / count,
                "computed_critical_load_kn": critical_load,
                "exact_critical_load_kn": exact_critical_load,
                "relative_error": relative_error,
                "generalized_eigen_residual_relative_inf": eigen_residual,
                "matrix_symmetry_abs_max": symmetry_error,
                "mode_mac": mode_mac,
                "normalized_nodal_translations": normalized_translations.tolist(),
                "contract_pass": bool(
                    critical_load >= exact_critical_load
                    and relative_error <= 1.0e-2
                    and eigen_residual <= 1.0e-10
                    and symmetry_error <= 1.0e-12
                    and mode_mac >= 1.0 - 1.0e-12
                ),
            }
        )

    observed_orders = [
        math.log(errors[index] / errors[index + 1])
        / math.log(counts[index + 1] / counts[index])
        for index in range(len(errors) - 1)
    ]
    monotonic_upper_bound = all(
        later < earlier
        for earlier, later in zip(errors, errors[1:])
    )
    contract_pass = bool(
        all(row["contract_pass"] for row in rows)
        and monotonic_upper_bound
        and min(observed_orders) >= 3.7
        and errors[-1] <= 3.0e-6
    )
    return {
        "case_id": "pinned_pinned_euler_column_fe_convergence",
        "formulation": EULER_ELEMENT_FORMULATION,
        "truth_basis": "closed_form_euler_critical_load_and_sine_mode",
        "parameters": {
            "length_m": length,
            "flexural_rigidity_kn_m2": rigidity,
        },
        "exact_critical_load_kn": exact_critical_load,
        "mesh_rows": rows,
        "observed_convergence_orders": observed_orders,
        "monotonic_upper_bound_convergence": monotonic_upper_bound,
        "finest_relative_error": errors[-1],
        "contract_pass": contract_pass,
    }


def modal_pdelta_amplification_benchmark(
    *,
    element_count: int = 16,
    load_ratios: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 0.9),
    length_m: float = 3.0,
    flexural_rigidity_kn_m2: float = 10_000.0,
) -> dict[str, Any]:
    """Verify modal second-order amplification below the FE critical load."""

    if not load_ratios:
        raise ValueError("load_ratios must not be empty")
    ratios = tuple(float(value) for value in load_ratios)
    if any(not math.isfinite(value) or value < 0.0 or value >= 1.0 for value in ratios):
        raise ValueError("load_ratios must be finite and in [0, 1)")
    if any(right <= left for left, right in zip(ratios, ratios[1:])):
        raise ValueError("load_ratios must be strictly increasing")

    system = assemble_euler_column_system(
        element_count=element_count,
        length_m=length_m,
        flexural_rigidity_kn_m2=flexural_rigidity_kn_m2,
    )
    critical_load, mode = _first_buckling_mode(system)
    elastic = system.elastic_stiffness
    geometric = system.unit_compression_geometric_stiffness
    modal_force = elastic @ mode
    baseline = np.linalg.solve(elastic, modal_force)
    denominator = float(np.dot(mode, baseline))
    rows: list[dict[str, Any]] = []
    for ratio in ratios:
        axial_compression = ratio * critical_load
        effective = elastic - axial_compression * geometric
        displacement = np.linalg.solve(effective, modal_force)
        amplification = float(np.dot(mode, displacement)) / denominator
        exact_amplification = 1.0 / (1.0 - ratio)
        relative_error = abs(amplification - exact_amplification) / exact_amplification
        residual = effective @ displacement - modal_force
        residual_relative = float(np.linalg.norm(residual, ord=np.inf)) / max(
            float(np.linalg.norm(modal_force, ord=np.inf)),
            np.finfo(np.float64).tiny,
        )
        rows.append(
            {
                "compression_to_critical_ratio": ratio,
                "compression_load_kn": axial_compression,
                "computed_modal_amplification": amplification,
                "exact_modal_amplification": exact_amplification,
                "relative_error": relative_error,
                "equilibrium_residual_relative_inf": residual_relative,
                "contract_pass": bool(
                    relative_error <= 1.0e-10 and residual_relative <= 1.0e-10
                ),
            }
        )
    monotonic = all(
        right["computed_modal_amplification"]
        > left["computed_modal_amplification"]
        for left, right in zip(rows, rows[1:])
    )
    contract_pass = bool(all(row["contract_pass"] for row in rows) and monotonic)
    return {
        "case_id": "pinned_column_first_mode_pdelta_amplification",
        "formulation": PDELTA_FORMULATION,
        "truth_basis": "generalized_eigenmode_amplification_identity",
        "element_count": system.element_count,
        "fe_critical_load_kn": critical_load,
        "load_rows": rows,
        "amplification_monotonic": monotonic,
        "contract_pass": contract_pass,
        "general_frame_pdelta_claim": False,
    }


@dataclass(frozen=True)
class TwoBarShallowArch:
    """Symmetric two-bar truss with exact finite-rotation kinematics."""

    half_span_m: float = 1.0
    rise_m: float = 0.2
    axial_rigidity_kn: float = 10_000.0

    def __post_init__(self) -> None:
        _positive_finite(self.half_span_m, "half_span_m")
        _positive_finite(self.rise_m, "rise_m")
        _positive_finite(self.axial_rigidity_kn, "axial_rigidity_kn")

    @property
    def initial_bar_length_m(self) -> float:
        return math.hypot(self.half_span_m, self.rise_m)

    def current_bar_length_m(self, downward_displacement_m: float) -> float:
        vertical_coordinate = self.rise_m - float(downward_displacement_m)
        return math.hypot(self.half_span_m, vertical_coordinate)

    def internal_force_kn(self, downward_displacement_m: float) -> float:
        displacement = float(downward_displacement_m)
        if not math.isfinite(displacement):
            raise ValueError("downward_displacement_m must be finite")
        vertical_coordinate = self.rise_m - displacement
        current_length = self.current_bar_length_m(displacement)
        initial_length = self.initial_bar_length_m
        return (
            2.0
            * self.axial_rigidity_kn
            / initial_length
            * (initial_length / current_length - 1.0)
            * vertical_coordinate
        )

    def consistent_tangent_kn_per_m(self, downward_displacement_m: float) -> float:
        displacement = float(downward_displacement_m)
        if not math.isfinite(displacement):
            raise ValueError("downward_displacement_m must be finite")
        current_length = self.current_bar_length_m(displacement)
        initial_length = self.initial_bar_length_m
        return (
            2.0
            * self.axial_rigidity_kn
            / initial_length
            * (
                1.0
                - initial_length * self.half_span_m**2 / current_length**3
            )
        )

    def strain_energy_kn_m(self, downward_displacement_m: float) -> float:
        current_length = self.current_bar_length_m(downward_displacement_m)
        extension = current_length - self.initial_bar_length_m
        return (
            self.axial_rigidity_kn
            / self.initial_bar_length_m
            * extension**2
        )

    def first_limit_point(self) -> tuple[float, float]:
        initial_length = self.initial_bar_length_m
        limit_length = (initial_length * self.half_span_m**2) ** (1.0 / 3.0)
        limit_vertical = math.sqrt(limit_length**2 - self.half_span_m**2)
        displacement = self.rise_m - limit_vertical
        return displacement, self.internal_force_kn(displacement)


def finite_difference_shallow_arch_checks(
    arch: TwoBarShallowArch,
    *,
    downward_displacement_m: float,
    step_m: float | None = None,
) -> dict[str, Any]:
    """Check tangent and energy derivative using central finite differences."""

    displacement = float(downward_displacement_m)
    if not math.isfinite(displacement):
        raise ValueError("downward_displacement_m must be finite")
    step = (
        max(arch.rise_m * 1.0e-5, 1.0e-9)
        if step_m is None
        else _positive_finite(step_m, "step_m")
    )
    force_plus = arch.internal_force_kn(displacement + step)
    force_minus = arch.internal_force_kn(displacement - step)
    tangent_fd = (force_plus - force_minus) / (2.0 * step)
    tangent_exact = arch.consistent_tangent_kn_per_m(displacement)
    energy_plus = arch.strain_energy_kn_m(displacement + step)
    energy_minus = arch.strain_energy_kn_m(displacement - step)
    energy_derivative_fd = (energy_plus - energy_minus) / (2.0 * step)
    force_exact = arch.internal_force_kn(displacement)
    tangent_relative_error = abs(tangent_fd - tangent_exact) / max(
        abs(tangent_exact),
        1.0,
    )
    energy_derivative_relative_error = abs(
        energy_derivative_fd - force_exact
    ) / max(abs(force_exact), 1.0)
    return {
        "downward_displacement_m": displacement,
        "finite_difference_step_m": step,
        "exact_internal_force_kn": force_exact,
        "finite_difference_energy_derivative_kn": energy_derivative_fd,
        "exact_tangent_kn_per_m": tangent_exact,
        "finite_difference_tangent_kn_per_m": tangent_fd,
        "tangent_relative_error": tangent_relative_error,
        "energy_derivative_relative_error": energy_derivative_relative_error,
        "contract_pass": bool(
            tangent_relative_error <= 1.0e-8
            and energy_derivative_relative_error <= 1.0e-8
        ),
    }


def shallow_arch_snapthrough_benchmark(
    *,
    arch: TwoBarShallowArch | None = None,
    sample_count: int = 91,
) -> dict[str, Any]:
    """Trace the exact two-bar equilibrium path through its first limit point."""

    if isinstance(sample_count, bool) or not isinstance(sample_count, int):
        raise ValueError("sample_count must be an integer")
    if sample_count < 9:
        raise ValueError("sample_count must be at least 9")
    model = arch or TwoBarShallowArch()
    limit_displacement, limit_force = model.first_limit_point()
    displacements = np.linspace(0.0, 2.25 * model.rise_m, sample_count)
    curve_rows = [
        {
            "downward_displacement_m": float(displacement),
            "equilibrium_load_kn": model.internal_force_kn(float(displacement)),
            "consistent_tangent_kn_per_m": (
                model.consistent_tangent_kn_per_m(float(displacement))
            ),
            "strain_energy_kn_m": model.strain_energy_kn_m(float(displacement)),
            "equilibrium_residual_kn": 0.0,
        }
        for displacement in displacements
    ]
    check_displacements = (
        0.25 * limit_displacement,
        0.75 * limit_displacement,
        limit_displacement + 0.25 * (model.rise_m - limit_displacement),
    )
    difference_checks = [
        finite_difference_shallow_arch_checks(
            model,
            downward_displacement_m=displacement,
        )
        for displacement in check_displacements
    ]
    probe = max(model.rise_m * 1.0e-5, 1.0e-8)
    tangent_before = model.consistent_tangent_kn_per_m(limit_displacement - probe)
    tangent_at = model.consistent_tangent_kn_per_m(limit_displacement)
    tangent_after = model.consistent_tangent_kn_per_m(limit_displacement + probe)
    negative_branch_force = model.internal_force_kn(1.5 * model.rise_m)
    rehardening_force = model.internal_force_kn(2.25 * model.rise_m)
    zero_force_abs_max = max(
        abs(model.internal_force_kn(0.0)),
        abs(model.internal_force_kn(model.rise_m)),
        abs(model.internal_force_kn(2.0 * model.rise_m)),
    )
    limit_point_gate = bool(
        limit_displacement > 0.0
        and limit_displacement < model.rise_m
        and limit_force > 0.0
        and tangent_before > 0.0
        and abs(tangent_at) <= 1.0e-10
        and tangent_after < 0.0
    )
    path_shape_gate = bool(
        negative_branch_force < 0.0
        and rehardening_force > 0.0
        and zero_force_abs_max <= 1.0e-10
    )
    contract_pass = bool(
        limit_point_gate
        and path_shape_gate
        and all(row["contract_pass"] for row in difference_checks)
    )
    return {
        "case_id": "two_bar_shallow_arch_exact_snapthrough_path",
        "formulation": SHALLOW_ARCH_FORMULATION,
        "truth_basis": "closed_form_finite_rotation_two_bar_equilibrium",
        "parameters": {
            "half_span_m": model.half_span_m,
            "rise_m": model.rise_m,
            "axial_rigidity_kn": model.axial_rigidity_kn,
            "initial_bar_length_m": model.initial_bar_length_m,
        },
        "first_limit_point": {
            "downward_displacement_m": limit_displacement,
            "equilibrium_load_kn": limit_force,
            "consistent_tangent_kn_per_m": tangent_at,
            "tangent_before_kn_per_m": tangent_before,
            "tangent_after_kn_per_m": tangent_after,
            "contract_pass": limit_point_gate,
        },
        "finite_difference_checks": difference_checks,
        "path_shape": {
            "negative_force_after_apex_inversion_kn": negative_branch_force,
            "positive_force_after_rehardening_kn": rehardening_force,
            "zero_force_checkpoints_abs_max_kn": zero_force_abs_max,
            "contract_pass": path_shape_gate,
        },
        "curve_rows": curve_rows,
        "contract_pass": contract_pass,
        "arc_length_solver_claim": False,
        "lee_frame_claim": False,
    }


def build_geometric_nonlinear_benchmark_seed() -> dict[str, Any]:
    """Build deterministic evidence for the three deliberately narrow kernels."""

    euler = euler_column_buckling_benchmark()
    pdelta = modal_pdelta_amplification_benchmark()
    shallow_arch = shallow_arch_snapthrough_benchmark()
    implemented_pass = bool(
        euler["contract_pass"]
        and pdelta["contract_pass"]
        and shallow_arch["contract_pass"]
    )
    return {
        "schema_version": GEOMETRIC_BENCHMARK_SCHEMA_VERSION,
        "status": "partial" if implemented_pass else "blocked",
        "contract_pass": implemented_pass,
        "truth_class": "analytic_and_semianalytic_geometric_seed_truth",
        "analysis_type": "geometric_nonlinear_benchmark_seed",
        "benchmarks": {
            "euler_column": euler,
            "modal_pdelta_column": pdelta,
            "two_bar_shallow_arch": shallow_arch,
        },
        "implemented_benchmarks_contract_pass": implemented_pass,
        "geometric_nonlinear_benchmark_breadth_claim": False,
        "general_frame_pdelta_claim": False,
        "lee_frame_snapthrough_claim": False,
        "arc_length_path_following_claim": False,
        "continuum_cantilever_large_rotation_claim": False,
        "general_2d_3d_geometric_stiffness_claim": False,
    }
