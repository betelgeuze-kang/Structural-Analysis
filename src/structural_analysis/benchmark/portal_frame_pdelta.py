"""Bounded gravity-prestressed portal-frame P-Delta benchmark.

The kernel assembles two columns and one beam with the energy-consistent
corotational element used by the Lee-frame benchmark.  A closed-form symmetric
sway reduction independently verifies the assembled tangent, critical gravity
load, and lateral amplification.  This is an analytic three-member benchmark,
not a general production frame or member P-small-delta implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np
from scipy.optimize import brentq

from structural_analysis.benchmark.lee_frame import (
    corotational_frame_element_response,
)


PORTAL_FRAME_PDELTA_SCHEMA_VERSION = "phase2-portal-frame-pdelta-result.v1"
PORTAL_FRAME_PDELTA_FORMULATION = (
    "three_member_planar_corotational_gravity_prestressed_sway_tangent"
)
PORTAL_FRAME_PDELTA_CONTEXT_URL = (
    "https://opensees.github.io/OpenSeesDocumentation/user/manual/model/"
    "geomTransf/PDelta.html"
)
PORTAL_FRAME_PDELTA_CLAIM_BOUNDARY = (
    "This receipt verifies the gravity-prestressed symmetric sway tangent of "
    "one elastic, planar, three-member portal frame against an independent "
    "closed-form reduction. It does not validate finite-displacement load-path "
    "continuation, member P-small-delta stability functions, the legacy "
    "corotational proxy, a general 2D/3D production frame or shell, "
    "material-geometric coupling, sparse or ROCm/HIP execution, full-building "
    "equilibrium, or G1 closure."
)


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _nonnegative_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be nonnegative and finite")
    return result


def _finite_vector(values: np.ndarray, *, name: str, size: int) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},)")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _relative_inf_error(actual: np.ndarray, reference: np.ndarray) -> float:
    scale = max(
        1.0,
        float(np.linalg.norm(actual, ord=np.inf)),
        float(np.linalg.norm(reference, ord=np.inf)),
    )
    return float(np.linalg.norm(actual - reference, ord=np.inf)) / scale


@dataclass(frozen=True)
class PortalFramePDeltaProblem:
    """One-bay, one-story elastic portal with fixed column bases."""

    story_height_m: float = 3.0
    bay_width_m: float = 5.0
    youngs_modulus_kn_per_m2: float = 200_000_000.0
    column_area_m2: float = 0.2
    column_second_moment_m4: float = 8.0e-5
    beam_area_m2: float = 0.2
    beam_second_moment_m4: float = 1.6e-4
    maximum_column_axial_strain: float = 0.05
    node_coordinates_m: np.ndarray = field(init=False, repr=False, compare=False)
    elements: tuple[tuple[int, int, float, float], ...] = field(
        init=False,
        repr=False,
    )
    free_global_dofs: tuple[int, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        height = _positive_finite(self.story_height_m, "story_height_m")
        width = _positive_finite(self.bay_width_m, "bay_width_m")
        modulus = _positive_finite(
            self.youngs_modulus_kn_per_m2,
            "youngs_modulus_kn_per_m2",
        )
        column_area = _positive_finite(self.column_area_m2, "column_area_m2")
        column_inertia = _positive_finite(
            self.column_second_moment_m4,
            "column_second_moment_m4",
        )
        beam_area = _positive_finite(self.beam_area_m2, "beam_area_m2")
        beam_inertia = _positive_finite(
            self.beam_second_moment_m4,
            "beam_second_moment_m4",
        )
        strain_limit = _positive_finite(
            self.maximum_column_axial_strain,
            "maximum_column_axial_strain",
        )
        if strain_limit >= 0.1:
            raise ValueError("maximum_column_axial_strain must be less than 0.1")

        coordinates = np.asarray(
            [
                [0.0, 0.0],
                [0.0, height],
                [width, height],
                [width, 0.0],
            ],
            dtype=np.float64,
        )
        coordinates.setflags(write=False)
        elements = (
            (0, 1, column_area, column_inertia),
            (1, 2, beam_area, beam_inertia),
            (3, 2, column_area, column_inertia),
        )

        object.__setattr__(self, "story_height_m", height)
        object.__setattr__(self, "bay_width_m", width)
        object.__setattr__(self, "youngs_modulus_kn_per_m2", modulus)
        object.__setattr__(self, "column_area_m2", column_area)
        object.__setattr__(self, "column_second_moment_m4", column_inertia)
        object.__setattr__(self, "beam_area_m2", beam_area)
        object.__setattr__(self, "beam_second_moment_m4", beam_inertia)
        object.__setattr__(self, "maximum_column_axial_strain", strain_limit)
        object.__setattr__(self, "node_coordinates_m", coordinates)
        object.__setattr__(self, "elements", elements)
        object.__setattr__(self, "free_global_dofs", tuple(range(3, 9)))

    @property
    def free_dof_count(self) -> int:
        return len(self.free_global_dofs)

    @property
    def column_axial_rigidity_kn(self) -> float:
        return self.youngs_modulus_kn_per_m2 * self.column_area_m2

    def _validated_total_gravity_load_kn(self, value: float) -> float:
        load = _nonnegative_finite(value, "total_gravity_load_kn")
        column_strain = load / (2.0 * self.column_axial_rigidity_kn)
        if column_strain >= self.maximum_column_axial_strain:
            raise ValueError(
                "total_gravity_load_kn exceeds the benchmark axial-strain limit"
            )
        return load

    def gravity_state(self, total_gravity_load_kn: float) -> np.ndarray:
        """Return the exact straight equilibrium under symmetric top gravity."""

        load = self._validated_total_gravity_load_kn(total_gravity_load_kn)
        shortening = load * self.story_height_m / (2.0 * self.column_axial_rigidity_kn)
        return np.asarray(
            [0.0, -shortening, 0.0, 0.0, -shortening, 0.0],
            dtype=np.float64,
        )

    def gravity_load_vector_kn(self, total_gravity_load_kn: float) -> np.ndarray:
        load = self._validated_total_gravity_load_kn(total_gravity_load_kn)
        return np.asarray(
            [0.0, -0.5 * load, 0.0, 0.0, -0.5 * load, 0.0],
            dtype=np.float64,
        )

    def current_story_height_m(self, total_gravity_load_kn: float) -> float:
        load = self._validated_total_gravity_load_kn(total_gravity_load_kn)
        return self.story_height_m * (
            1.0 - load / (2.0 * self.column_axial_rigidity_kn)
        )

    def symmetric_sway_transformation(self) -> np.ndarray:
        """Map ``[story sway, antisymmetric vertical, joint rotation]``."""

        transformation = np.asarray(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
                [0.0, -1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        transformation.setflags(write=False)
        return transformation

    def assemble(
        self,
        free_displacements: np.ndarray,
    ) -> tuple[float, np.ndarray, np.ndarray]:
        """Assemble strain energy, internal force, and consistent tangent."""

        free = _finite_vector(
            free_displacements,
            name="free_displacements",
            size=self.free_dof_count,
        )
        global_displacements = np.zeros(12, dtype=np.float64)
        global_displacements[list(self.free_global_dofs)] = free
        global_force = np.zeros(12, dtype=np.float64)
        global_tangent = np.zeros((12, 12), dtype=np.float64)
        energy = 0.0
        for node_i, node_j, area, inertia in self.elements:
            element_dofs = (
                3 * node_i,
                3 * node_i + 1,
                3 * node_i + 2,
                3 * node_j,
                3 * node_j + 1,
                3 * node_j + 2,
            )
            response = corotational_frame_element_response(
                node_coordinates_m=self.node_coordinates_m[[node_i, node_j]],
                element_displacements=global_displacements[list(element_dofs)],
                youngs_modulus_kn_per_m2=self.youngs_modulus_kn_per_m2,
                area_m2=area,
                second_moment_m4=inertia,
            )
            energy += response.strain_energy_kn_m
            global_force[list(element_dofs)] += response.internal_force_global
            global_tangent[np.ix_(element_dofs, element_dofs)] += (
                response.consistent_tangent_global
            )

        free_indices = np.asarray(self.free_global_dofs, dtype=np.int64)
        force = global_force[free_indices]
        tangent = global_tangent[np.ix_(free_indices, free_indices)]
        return float(energy), force, tangent

    def analytic_symmetric_sway_tangent_kn(
        self,
        total_gravity_load_kn: float,
    ) -> np.ndarray:
        """Return the independently reduced ``[Delta, eta, theta]`` Hessian."""

        load = self._validated_total_gravity_load_kn(total_gravity_load_kn)
        height = self.story_height_m
        current_height = self.current_story_height_m(load)
        width = self.bay_width_m
        modulus = self.youngs_modulus_kn_per_m2
        column_flexural_rigidity = modulus * self.column_second_moment_m4
        beam_flexural_rigidity = modulus * self.beam_second_moment_m4

        sway_stiffness = (
            24.0 * column_flexural_rigidity / (height * current_height**2)
            - load / current_height
        )
        sway_rotation_coupling = (
            12.0 * column_flexural_rigidity / (height * current_height)
        )
        rotation_stiffness = (
            8.0 * column_flexural_rigidity / height
            + 12.0 * beam_flexural_rigidity / width
        )
        vertical_rotation_coupling = 24.0 * beam_flexural_rigidity / width**2
        antisymmetric_vertical_stiffness = (
            2.0 * self.column_axial_rigidity_kn / height
            + 48.0 * beam_flexural_rigidity / width**3
        )
        tangent = np.asarray(
            [
                [sway_stiffness, 0.0, sway_rotation_coupling],
                [
                    0.0,
                    antisymmetric_vertical_stiffness,
                    vertical_rotation_coupling,
                ],
                [
                    sway_rotation_coupling,
                    vertical_rotation_coupling,
                    rotation_stiffness,
                ],
            ],
            dtype=np.float64,
        )
        tangent.setflags(write=False)
        return tangent

    def assembled_symmetric_sway_tangent_kn(
        self,
        total_gravity_load_kn: float,
    ) -> np.ndarray:
        state = self.gravity_state(total_gravity_load_kn)
        _, _, tangent = self.assemble(state)
        transformation = self.symmetric_sway_transformation()
        reduced = transformation.T @ tangent @ transformation
        reduced.setflags(write=False)
        return reduced


def effective_sway_stiffness_kn_per_m(tangent: np.ndarray) -> float:
    """Statically condense the vertical and rotation coordinates."""

    matrix = np.asarray(tangent, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("tangent must be a finite 3x3 matrix")
    internal = matrix[1:, 1:]
    try:
        correction = float(matrix[0, 1:] @ np.linalg.solve(internal, matrix[1:, 0]))
    except np.linalg.LinAlgError as exc:
        raise ValueError("tangent internal block must be nonsingular") from exc
    return float(matrix[0, 0] - correction)


def portal_frame_sway_critical_load_kn(
    problem: PortalFramePDeltaProblem,
    *,
    use_assembled_tangent: bool = False,
) -> float:
    """Find the first gravity load where condensed sway stiffness is zero."""

    tangent_function = (
        problem.assembled_symmetric_sway_tangent_kn
        if use_assembled_tangent
        else problem.analytic_symmetric_sway_tangent_kn
    )

    def stiffness(load: float) -> float:
        return effective_sway_stiffness_kn_per_m(tangent_function(load))

    initial_stiffness = stiffness(0.0)
    if initial_stiffness <= 0.0:
        raise ValueError("portal frame must have positive unloaded sway stiffness")
    upper = initial_stiffness * problem.story_height_m
    maximum_load = (
        2.0
        * problem.column_axial_rigidity_kn
        * problem.maximum_column_axial_strain
        * (1.0 - 1.0e-9)
    )
    for _ in range(32):
        if upper >= maximum_load:
            upper = maximum_load
        if stiffness(upper) < 0.0:
            return float(brentq(stiffness, 0.0, upper, xtol=1.0e-10, rtol=1.0e-13))
        if upper >= maximum_load:
            break
        upper *= 1.5
    raise ValueError("no sway critical load exists inside the axial-strain limit")


def finite_difference_portal_frame_checks(
    problem: PortalFramePDeltaProblem,
    *,
    free_displacements: np.ndarray | None = None,
    perturbation: float = 2.0e-7,
) -> dict[str, Any]:
    """Check that the three-member force and tangent are energy derivatives."""

    delta = _positive_finite(perturbation, "perturbation")
    if free_displacements is None:
        critical_load = portal_frame_sway_critical_load_kn(problem)
        state = problem.gravity_state(0.5 * critical_load)
        state += np.asarray(
            [0.0020, 0.00012, -0.0007, 0.0017, -0.00009, -0.0005],
            dtype=np.float64,
        )
    else:
        state = _finite_vector(
            free_displacements,
            name="free_displacements",
            size=problem.free_dof_count,
        )
    _, force, tangent = problem.assemble(state)
    difference_gradient = np.zeros_like(force)
    difference_tangent = np.zeros_like(tangent)
    for column in range(problem.free_dof_count):
        offset = np.zeros(problem.free_dof_count, dtype=np.float64)
        offset[column] = delta
        positive_energy, positive_force, _ = problem.assemble(state + offset)
        negative_energy, negative_force, _ = problem.assemble(state - offset)
        difference_gradient[column] = (positive_energy - negative_energy) / (
            2.0 * delta
        )
        difference_tangent[:, column] = (positive_force - negative_force) / (
            2.0 * delta
        )

    gradient_error = _relative_inf_error(force, difference_gradient)
    tangent_error = _relative_inf_error(tangent, difference_tangent)
    symmetry_scale = max(1.0, float(np.linalg.norm(tangent, ord=np.inf)))
    symmetry_error = float(np.linalg.norm(tangent - tangent.T, ord=np.inf)) / (
        symmetry_scale
    )
    contract_pass = bool(
        gradient_error <= 1.0e-7
        and tangent_error <= 1.0e-7
        and symmetry_error <= 1.0e-12
    )
    return {
        "equation_count": problem.free_dof_count,
        "perturbation": delta,
        "energy_gradient_relative_error": gradient_error,
        "tangent_hessian_relative_error": tangent_error,
        "tangent_symmetry_relative_error": symmetry_error,
        "contract_pass": contract_pass,
    }


def portal_frame_pdelta_benchmark(
    *,
    load_ratios: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 0.9, 0.95),
) -> dict[str, Any]:
    """Build the bounded analytic-versus-assembled portal P-Delta receipt."""

    if len(load_ratios) < 4:
        raise ValueError("load_ratios must contain at least four values")
    ratios = tuple(float(value) for value in load_ratios)
    if any(not math.isfinite(value) or value < 0.0 or value >= 1.0 for value in ratios):
        raise ValueError("load_ratios must be finite values in [0, 1)")
    if any(right <= left for left, right in zip(ratios, ratios[1:])):
        raise ValueError("load_ratios must be strictly increasing")

    problem = PortalFramePDeltaProblem()
    analytic_critical_load = portal_frame_sway_critical_load_kn(problem)
    assembled_critical_load = portal_frame_sway_critical_load_kn(
        problem,
        use_assembled_tangent=True,
    )
    critical_load_relative_error = (
        abs(assembled_critical_load - analytic_critical_load) / analytic_critical_load
    )
    unloaded_stiffness = effective_sway_stiffness_kn_per_m(
        problem.analytic_symmetric_sway_tangent_kn(0.0)
    )
    transformation = problem.symmetric_sway_transformation()
    unit_story_load = np.asarray([1.0, 0.0, 0.0], dtype=np.float64)
    unit_full_load = np.asarray([0.5, 0.0, 0.0, 0.5, 0.0, 0.0])
    rows: list[dict[str, Any]] = []
    for ratio in ratios:
        gravity_load = ratio * analytic_critical_load
        gravity_state = problem.gravity_state(gravity_load)
        _, internal_force, full_tangent = problem.assemble(gravity_state)
        external_force = problem.gravity_load_vector_kn(gravity_load)
        analytic_tangent = problem.analytic_symmetric_sway_tangent_kn(gravity_load)
        assembled_tangent = transformation.T @ full_tangent @ transformation
        analytic_stiffness = effective_sway_stiffness_kn_per_m(analytic_tangent)
        assembled_stiffness = effective_sway_stiffness_kn_per_m(assembled_tangent)
        reduced_response = np.linalg.solve(assembled_tangent, unit_story_load)
        full_response = np.linalg.solve(full_tangent, unit_full_load)
        transformed_response = transformation @ reduced_response
        analytic_amplification = unloaded_stiffness / analytic_stiffness
        assembled_amplification = unloaded_stiffness / assembled_stiffness
        equilibrium_scale = max(1.0, gravity_load)
        rows.append(
            {
                "critical_load_ratio": ratio,
                "total_gravity_load_kn": gravity_load,
                "column_compressive_load_kn": 0.5 * gravity_load,
                "current_story_height_m": problem.current_story_height_m(gravity_load),
                "analytic_effective_sway_stiffness_kn_per_m": (analytic_stiffness),
                "assembled_effective_sway_stiffness_kn_per_m": (assembled_stiffness),
                "effective_stiffness_relative_error": abs(
                    assembled_stiffness - analytic_stiffness
                )
                / max(1.0, abs(analytic_stiffness)),
                "analytic_lateral_amplification": analytic_amplification,
                "assembled_lateral_amplification": assembled_amplification,
                "amplification_relative_error": abs(
                    assembled_amplification - analytic_amplification
                )
                / analytic_amplification,
                "analytic_vs_assembled_tangent_relative_inf_error": (
                    _relative_inf_error(assembled_tangent, analytic_tangent)
                ),
                "gravity_equilibrium_residual_inf_kn": float(
                    np.linalg.norm(internal_force - external_force, ord=np.inf)
                ),
                "gravity_equilibrium_residual_relative_inf": float(
                    np.linalg.norm(internal_force - external_force, ord=np.inf)
                )
                / equilibrium_scale,
                "condensed_unit_load_residual_inf": float(
                    np.linalg.norm(
                        assembled_tangent @ reduced_response - unit_story_load,
                        ord=np.inf,
                    )
                ),
                "full_vs_symmetric_response_abs_max": float(
                    np.linalg.norm(
                        full_response - transformed_response,
                        ord=np.inf,
                    )
                ),
                "minimum_symmetric_tangent_eigenvalue": float(
                    np.linalg.eigvalsh(assembled_tangent)[0]
                ),
                "full_tangent_symmetry_abs_max": float(
                    np.max(np.abs(full_tangent - full_tangent.T))
                ),
            }
        )

    tangent_checks = finite_difference_portal_frame_checks(problem)
    maximum_tangent_error = max(
        row["analytic_vs_assembled_tangent_relative_inf_error"] for row in rows
    )
    maximum_stiffness_error = max(
        row["effective_stiffness_relative_error"] for row in rows
    )
    maximum_amplification_error = max(
        row["amplification_relative_error"] for row in rows
    )
    maximum_gravity_residual = max(
        row["gravity_equilibrium_residual_inf_kn"] for row in rows
    )
    maximum_gravity_relative_residual = max(
        row["gravity_equilibrium_residual_relative_inf"] for row in rows
    )
    maximum_reduction_error = max(
        row["full_vs_symmetric_response_abs_max"] for row in rows
    )
    amplification_monotonic = all(
        right["assembled_lateral_amplification"]
        > left["assembled_lateral_amplification"]
        for left, right in zip(rows, rows[1:])
    )
    contract_pass = bool(
        critical_load_relative_error <= 1.0e-10
        and maximum_tangent_error <= 1.0e-11
        and maximum_stiffness_error <= 1.0e-10
        and maximum_amplification_error <= 1.0e-10
        and maximum_gravity_residual <= 1.0e-7
        and maximum_gravity_relative_residual <= 1.0e-12
        and maximum_reduction_error <= 1.0e-10
        and amplification_monotonic
        and rows[-1]["assembled_lateral_amplification"] >= 19.0
        and all(row["minimum_symmetric_tangent_eigenvalue"] > 0.0 for row in rows)
        and all(row["full_tangent_symmetry_abs_max"] <= 1.0e-12 for row in rows)
        and tangent_checks["contract_pass"]
    )
    return {
        "schema_version": PORTAL_FRAME_PDELTA_SCHEMA_VERSION,
        "benchmark_id": "three-member-portal-frame-pdelta-tangent-v1",
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "formulation": PORTAL_FRAME_PDELTA_FORMULATION,
        "reference": {
            "type": "independent_closed_form_symmetric_sway_reduction",
            "generalized_coordinates": [
                "story_sway_delta_m",
                "antisymmetric_joint_vertical_eta_m",
                "common_joint_rotation_theta_rad",
            ],
            "external_context_url": PORTAL_FRAME_PDELTA_CONTEXT_URL,
            "external_context_role": ("terminology_only_not_numerical_reference"),
        },
        "problem_definition": {
            "story_height_m": problem.story_height_m,
            "bay_width_m": problem.bay_width_m,
            "youngs_modulus_mpa": (problem.youngs_modulus_kn_per_m2 / 1000.0),
            "column_area_m2": problem.column_area_m2,
            "column_second_moment_m4": problem.column_second_moment_m4,
            "beam_area_m2": problem.beam_area_m2,
            "beam_second_moment_m4": problem.beam_second_moment_m4,
            "support_condition": "both_column_bases_fixed",
            "gravity_load_condition": (
                "equal_downward_top_joint_loads_before_unit_sway_probe"
            ),
            "member_count": len(problem.elements),
            "free_equation_count": problem.free_dof_count,
        },
        "critical_sway_load": {
            "analytic_total_gravity_load_kn": analytic_critical_load,
            "assembled_total_gravity_load_kn": assembled_critical_load,
            "relative_error": critical_load_relative_error,
            "contract_pass": critical_load_relative_error <= 1.0e-10,
        },
        "unloaded_effective_sway_stiffness_kn_per_m": unloaded_stiffness,
        "load_rows": rows,
        "error_summary": {
            "maximum_tangent_relative_inf_error": maximum_tangent_error,
            "maximum_effective_stiffness_relative_error": (maximum_stiffness_error),
            "maximum_amplification_relative_error": (maximum_amplification_error),
            "maximum_gravity_equilibrium_residual_inf_kn": (maximum_gravity_residual),
            "maximum_gravity_equilibrium_residual_relative_inf": (
                maximum_gravity_relative_residual
            ),
            "maximum_full_vs_symmetric_response_abs": maximum_reduction_error,
        },
        "path_shape": {
            "amplification_monotonic": amplification_monotonic,
            "maximum_load_ratio": rows[-1]["critical_load_ratio"],
            "maximum_assembled_lateral_amplification": rows[-1][
                "assembled_lateral_amplification"
            ],
        },
        "consistent_tangent_checks": tangent_checks,
        "solver": {
            "analysis_type": (
                "dense_direct_gravity_prestressed_tangent_and_static_condensation"
            ),
            "regularization_count": 0,
            "fallback_count": 0,
        },
        "claims": {
            "bounded_three_member_portal_pdelta_tangent": contract_pass,
            "analytic_sway_stiffness_validation": bool(
                maximum_stiffness_error <= 1.0e-10
            ),
            "gravity_prestress_equilibrium": bool(maximum_gravity_residual <= 1.0e-7),
            "assembled_critical_sway_load": bool(
                critical_load_relative_error <= 1.0e-10
            ),
            "energy_consistent_corotational_frame_connection": bool(
                tangent_checks["contract_pass"]
            ),
            "finite_displacement_load_path_continuation": False,
            "member_p_small_delta_stability_functions": False,
            "legacy_corotational_proxy_validated": False,
            "general_2d_3d_production_frame_or_shell": False,
            "material_geometric_coupling": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "finite_displacement_portal_load_path_not_verified",
            "member_p_small_delta_stability_functions_not_implemented",
            "legacy_corotational_proxy_not_promoted",
            "general_2d_3d_production_frame_shell_not_validated",
            "material_geometric_coupling_not_verified",
            "production_sparse_rocm_hip_path_not_connected",
            "full_building_equilibrium_not_closed",
            "g1_not_closed",
        ],
        "claim_boundary": PORTAL_FRAME_PDELTA_CLAIM_BOUNDARY,
    }


__all__ = [
    "PORTAL_FRAME_PDELTA_CLAIM_BOUNDARY",
    "PORTAL_FRAME_PDELTA_CONTEXT_URL",
    "PORTAL_FRAME_PDELTA_FORMULATION",
    "PORTAL_FRAME_PDELTA_SCHEMA_VERSION",
    "PortalFramePDeltaProblem",
    "effective_sway_stiffness_kn_per_m",
    "finite_difference_portal_frame_checks",
    "portal_frame_pdelta_benchmark",
    "portal_frame_sway_critical_load_kn",
]
