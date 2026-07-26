"""Published Lee-frame snap-through and snap-back verification benchmark.

The bounded kernel in this module assembles a planar, elastic, corotational
Euler--Bernoulli frame and connects it to the existing dense vector spherical
arc-length solver. It verifies one published two-member frame path; it is not a
general production frame/shell or material-geometric solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, cast

import numpy as np

from structural_analysis.solvers.nonlinear.vector_arc_length import (
    VectorArcLengthCheckpoint,
    VectorArcLengthConfig,
    VectorArcLengthProblem,
    vector_arc_length_continuation,
)


LEE_FRAME_SCHEMA_VERSION = "phase2-lee-frame-snapthrough-result.v1"
LEE_FRAME_FORMULATION = "planar_corotational_euler_bernoulli_total_potential_hessian"
LEE_FRAME_REFERENCE_DOI = "10.12989/sem.2011.38.6.767"
LEE_FRAME_REFERENCE_TABLE = "Leahu-Aluas_and_Abed-Meraim_2011_Table_11"
LEE_FRAME_CLAIM_BOUNDARY = (
    "This receipt verifies one elastic, planar, two-member Lee frame against "
    "the published Table 11 path using a dense CPU arc-length solve. It does "
    "not validate the legacy corotational proxy, a general 2D/3D production "
    "frame or shell, material-geometric coupling, sparse or ROCm/HIP "
    "execution, full-building equilibrium, or G1 closure."
)

# Table 11: horizontal displacement, downward displacement, load
# proportionality factor. Displacements are converted from mm to m.
LEE_FRAME_PUBLISHED_PATH: tuple[tuple[float, float, float], ...] = (
    (0.00000, 0.00000, 0.00),
    (0.00096, 0.02045, 2.99),
    (0.01006, 0.07300, 8.02),
    (0.04376, 0.17849, 12.85),
    (0.12032, 0.32687, 16.57),
    (0.22602, 0.45160, 18.47),
    (0.28531, 0.49916, 18.59),
    (0.37873, 0.55282, 17.78),
    (0.47475, 0.58826, 16.01),
    (0.57242, 0.60741, 13.45),
    (0.67061, 0.60574, 9.84),
    (0.76393, 0.56363, 3.88),
    (0.78947, 0.53369, 0.59),
    (0.80896, 0.50916, -3.63),
    (0.83117, 0.51439, -6.63),
    (0.86972, 0.54360, -8.92),
    (0.90642, 0.58737, -9.51),
    (0.93210, 0.63913, -8.86),
    (0.94400, 0.69411, -7.52),
    (0.94223, 0.74880, -5.74),
    (0.92826, 0.80094, -3.50),
    (0.88987, 0.87205, 2.02),
    (0.86206, 0.91649, 12.91),
)


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _finite_vector(
    values: np.ndarray,
    *,
    name: str,
    size: int,
) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},)")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


@dataclass(frozen=True)
class CorotationalFrameElementResponse:
    """Energy, exact gradient, and exact Hessian for one planar frame element."""

    strain_energy_kn_m: float
    internal_force_global: np.ndarray
    consistent_tangent_global: np.ndarray
    basic_deformations: tuple[float, float, float]
    basic_forces: tuple[float, float, float]
    initial_length_m: float
    current_length_m: float
    chord_rotation_change_rad: float


def corotational_frame_element_response(
    *,
    node_coordinates_m: np.ndarray,
    element_displacements: np.ndarray,
    youngs_modulus_kn_per_m2: float,
    area_m2: float,
    second_moment_m4: float,
) -> CorotationalFrameElementResponse:
    """Evaluate a small-strain, large-rotation planar beam energy exactly.

    Physical element degrees of freedom are ``[ux_i, uy_i, theta_i, ux_j,
    uy_j, theta_j]``. Translational forces are in kN and rotational forces are
    moments in kN m.
    """

    coordinates = np.asarray(node_coordinates_m, dtype=np.float64)
    if coordinates.shape != (2, 2) or not np.all(np.isfinite(coordinates)):
        raise ValueError("node_coordinates_m must be a finite 2x2 array")
    displacements = _finite_vector(
        element_displacements,
        name="element_displacements",
        size=6,
    )
    modulus = _positive_finite(
        youngs_modulus_kn_per_m2,
        "youngs_modulus_kn_per_m2",
    )
    area = _positive_finite(area_m2, "area_m2")
    second_moment = _positive_finite(second_moment_m4, "second_moment_m4")

    initial_chord = coordinates[1] - coordinates[0]
    initial_length = float(np.linalg.norm(initial_chord))
    if initial_length <= np.finfo(np.float64).eps:
        raise ValueError("frame element nodes must not coincide")
    initial_angle = math.atan2(initial_chord[1], initial_chord[0])
    chord_difference = np.asarray(
        [
            [-1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0, 0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    current_chord = initial_chord + chord_difference @ displacements
    current_length = float(np.linalg.norm(current_chord))
    if current_length <= 1.0e-9 * initial_length:
        raise ValueError("frame element current chord is degenerate")
    cosine = float(current_chord[0] / current_length)
    sine = float(current_chord[1] / current_length)
    current_angle = math.atan2(current_chord[1], current_chord[0])
    raw_angle_change = current_angle - initial_angle
    angle_change = math.atan2(
        math.sin(raw_angle_change),
        math.cos(raw_angle_change),
    )

    basic_deformations = np.asarray(
        [
            current_length - initial_length,
            displacements[2] - angle_change,
            displacements[5] - angle_change,
        ],
        dtype=np.float64,
    )
    basic_stiffness = np.asarray(
        [
            [modulus * area / initial_length, 0.0, 0.0],
            [
                0.0,
                4.0 * modulus * second_moment / initial_length,
                2.0 * modulus * second_moment / initial_length,
            ],
            [
                0.0,
                2.0 * modulus * second_moment / initial_length,
                4.0 * modulus * second_moment / initial_length,
            ],
        ],
        dtype=np.float64,
    )
    basic_forces = basic_stiffness @ basic_deformations

    length_gradient_chord = np.asarray([cosine, sine], dtype=np.float64)
    angle_gradient_chord = np.asarray(
        [-sine / current_length, cosine / current_length],
        dtype=np.float64,
    )
    rotation_i_gradient = np.zeros(6, dtype=np.float64)
    rotation_i_gradient[2] = 1.0
    rotation_j_gradient = np.zeros(6, dtype=np.float64)
    rotation_j_gradient[5] = 1.0
    basic_gradient = np.vstack(
        (
            chord_difference.T @ length_gradient_chord,
            rotation_i_gradient - chord_difference.T @ angle_gradient_chord,
            rotation_j_gradient - chord_difference.T @ angle_gradient_chord,
        )
    )

    length_hessian_chord = (
        np.asarray(
            [
                [sine**2, -cosine * sine],
                [-cosine * sine, cosine**2],
            ],
            dtype=np.float64,
        )
        / current_length
    )
    angle_hessian_chord = (
        np.asarray(
            [
                [2.0 * cosine * sine, sine**2 - cosine**2],
                [sine**2 - cosine**2, -2.0 * cosine * sine],
            ],
            dtype=np.float64,
        )
        / current_length**2
    )
    length_hessian = chord_difference.T @ length_hessian_chord @ chord_difference
    angle_hessian = chord_difference.T @ angle_hessian_chord @ chord_difference

    internal_force = basic_gradient.T @ basic_forces
    tangent = (
        basic_gradient.T @ basic_stiffness @ basic_gradient
        + basic_forces[0] * length_hessian
        - (basic_forces[1] + basic_forces[2]) * angle_hessian
    )
    energy = 0.5 * float(basic_deformations @ basic_forces)
    internal_force.setflags(write=False)
    tangent.setflags(write=False)
    return CorotationalFrameElementResponse(
        strain_energy_kn_m=energy,
        internal_force_global=internal_force,
        consistent_tangent_global=tangent,
        basic_deformations=(
            float(basic_deformations[0]),
            float(basic_deformations[1]),
            float(basic_deformations[2]),
        ),
        basic_forces=(
            float(basic_forces[0]),
            float(basic_forces[1]),
            float(basic_forces[2]),
        ),
        initial_length_m=initial_length,
        current_length_m=current_length,
        chord_rotation_change_rad=angle_change,
    )


@dataclass(frozen=True)
class LeeFrameArcLengthProblem:
    """Two-member published Lee frame in energy-conjugate solver coordinates."""

    elements_per_member: int = 10
    member_length_m: float = 1.2
    load_offset_m: float = 0.24
    youngs_modulus_kn_per_m2: float = 72_000_000.0
    area_m2: float = 6.0e-4
    second_moment_m4: float = 2.0e-8
    reference_load_kn_value: float = 1.0
    case_id: str = "lee_frame_elastic_snapthrough_snapback"
    node_coordinates_m: np.ndarray = field(init=False, repr=False, compare=False)
    elements: tuple[tuple[int, int], ...] = field(init=False, repr=False)
    free_global_dofs: tuple[int, ...] = field(init=False, repr=False)
    load_point_node_index: int = field(init=False)
    load_point_x_free_dof_index: int = field(init=False)
    load_point_y_free_dof_index: int = field(init=False)
    rotation_coordinate_scale_m: float = field(init=False)
    _physical_coordinate_scale: np.ndarray = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        count = _positive_integer(
            self.elements_per_member,
            "elements_per_member",
        )
        if count < 5 or count % 5 != 0:
            raise ValueError("elements_per_member must be a positive multiple of five")
        length = _positive_finite(self.member_length_m, "member_length_m")
        offset = _positive_finite(self.load_offset_m, "load_offset_m")
        if not math.isclose(offset, length / 5.0, rel_tol=0.0, abs_tol=1.0e-14):
            raise ValueError("load_offset_m must equal one fifth of member_length_m")
        _positive_finite(
            self.youngs_modulus_kn_per_m2,
            "youngs_modulus_kn_per_m2",
        )
        _positive_finite(self.area_m2, "area_m2")
        _positive_finite(self.second_moment_m4, "second_moment_m4")
        _positive_finite(
            self.reference_load_kn_value,
            "reference_load_kn_value",
        )

        vertical_nodes = [(0.0, length * node / count) for node in range(count + 1)]
        horizontal_nodes = [
            (length * node / count, length) for node in range(1, count + 1)
        ]
        coordinates = np.asarray(
            [*vertical_nodes, *horizontal_nodes],
            dtype=np.float64,
        )
        coordinates.setflags(write=False)
        elements = tuple((node, node + 1) for node in range(2 * count))
        global_dof_count = 3 * coordinates.shape[0]
        right_support_node = 2 * count
        constrained = {
            0,
            1,
            3 * right_support_node,
            3 * right_support_node + 1,
        }
        free = tuple(dof for dof in range(global_dof_count) if dof not in constrained)
        load_node = count + count // 5
        load_x_global = 3 * load_node
        load_y_global = load_x_global + 1
        rotation_scale = length / count
        physical_scale = np.ones(global_dof_count, dtype=np.float64)
        physical_scale[2::3] = 1.0 / rotation_scale
        physical_scale.setflags(write=False)

        object.__setattr__(self, "elements_per_member", count)
        object.__setattr__(self, "member_length_m", length)
        object.__setattr__(self, "load_offset_m", offset)
        object.__setattr__(self, "node_coordinates_m", coordinates)
        object.__setattr__(self, "elements", elements)
        object.__setattr__(self, "free_global_dofs", free)
        object.__setattr__(self, "load_point_node_index", load_node)
        object.__setattr__(
            self,
            "load_point_x_free_dof_index",
            free.index(load_x_global),
        )
        object.__setattr__(
            self,
            "load_point_y_free_dof_index",
            free.index(load_y_global),
        )
        object.__setattr__(
            self,
            "rotation_coordinate_scale_m",
            rotation_scale,
        )
        object.__setattr__(self, "_physical_coordinate_scale", physical_scale)

    @property
    def global_dof_count(self) -> int:
        return 3 * self.node_coordinates_m.shape[0]

    @property
    def free_dof_count(self) -> int:
        return len(self.free_global_dofs)

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(self.free_dof_count, dtype=np.float64)

    def initial_load_factor(self) -> float:
        return 0.0

    def reference_load_kn(self) -> np.ndarray:
        reference = np.zeros(self.free_dof_count, dtype=np.float64)
        reference[self.load_point_y_free_dof_index] = -self.reference_load_kn_value
        return reference

    def _physical_global_displacements(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray:
        free = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            size=self.free_dof_count,
        )
        generalized = np.zeros(self.global_dof_count, dtype=np.float64)
        generalized[list(self.free_global_dofs)] = free
        return self._physical_coordinate_scale * generalized

    def _assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[float, np.ndarray, np.ndarray]:
        physical_displacements = self._physical_global_displacements(
            free_displacements_m
        )
        physical_force = np.zeros(self.global_dof_count, dtype=np.float64)
        physical_tangent = np.zeros(
            (self.global_dof_count, self.global_dof_count),
            dtype=np.float64,
        )
        energy = 0.0
        for node_i, node_j in self.elements:
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
                element_displacements=physical_displacements[list(element_dofs)],
                youngs_modulus_kn_per_m2=self.youngs_modulus_kn_per_m2,
                area_m2=self.area_m2,
                second_moment_m4=self.second_moment_m4,
            )
            energy += response.strain_energy_kn_m
            physical_force[list(element_dofs)] += response.internal_force_global
            physical_tangent[np.ix_(element_dofs, element_dofs)] += (
                response.consistent_tangent_global
            )

        free_indices = np.asarray(self.free_global_dofs, dtype=np.int64)
        free_scale = self._physical_coordinate_scale[free_indices]
        generalized_force = free_scale * physical_force[free_indices]
        generalized_tangent = (
            free_scale[:, None]
            * physical_tangent[np.ix_(free_indices, free_indices)]
            * free_scale[None, :]
        )
        return float(energy), generalized_force, generalized_tangent

    def strain_energy_kn_m(self, free_displacements_m: np.ndarray) -> float:
        energy, _, _ = self._assemble(free_displacements_m)
        return energy

    def internal_force_kn(self, free_displacements_m: np.ndarray) -> np.ndarray:
        _, force, _ = self._assemble(free_displacements_m)
        return force

    def consistent_tangent_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> np.ndarray:
        _, _, tangent = self._assemble(free_displacements_m)
        return tangent

    def load_point_displacements_m(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[float, float]:
        free = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            size=self.free_dof_count,
        )
        return (
            float(free[self.load_point_x_free_dof_index]),
            -float(free[self.load_point_y_free_dof_index]),
        )


def lee_frame_arc_length_config(
    problem: LeeFrameArcLengthProblem,
) -> VectorArcLengthConfig:
    """Return the fixed path-following contract for the published frame."""

    return VectorArcLengthConfig(
        target_monitor_dof_index=problem.load_point_y_free_dof_index,
        target_monitor_displacement_m=-0.94,
        target_direction=-1,
        initial_arc_length_m=0.02,
        minimum_arc_length_m=0.00015625,
        maximum_arc_length_m=0.02,
        failed_step_reduction=0.5,
        load_factor_metric_scale_m=0.0001,
        residual_tolerance_kn=1.0e-7,
        tangent_solve_residual_tolerance_kn=1.0e-7,
        constraint_tolerance_m2=1.0e-10,
        maximum_corrector_iterations=12,
        maximum_attempt_count=400,
    )


def finite_difference_lee_frame_checks(
    problem: LeeFrameArcLengthProblem,
    *,
    free_displacements_m: np.ndarray | None = None,
    perturbation_m: float = 2.0e-7,
) -> dict[str, Any]:
    """Verify at frame level that force and tangent are energy derivatives."""

    delta = _positive_finite(perturbation_m, "perturbation_m")
    if free_displacements_m is None:
        indices = np.arange(1, problem.free_dof_count + 1, dtype=np.float64)
        state = 0.006 * np.sin(0.37 * indices)
    else:
        state = _finite_vector(
            free_displacements_m,
            name="free_displacements_m",
            size=problem.free_dof_count,
        )
    _, force, tangent = problem._assemble(state)
    finite_difference_gradient = np.zeros_like(force)
    finite_difference_tangent = np.zeros_like(tangent)
    for column in range(problem.free_dof_count):
        offset = np.zeros(problem.free_dof_count, dtype=np.float64)
        offset[column] = delta
        positive_energy, positive_force, _ = problem._assemble(state + offset)
        negative_energy, negative_force, _ = problem._assemble(state - offset)
        finite_difference_gradient[column] = (positive_energy - negative_energy) / (
            2.0 * delta
        )
        finite_difference_tangent[:, column] = (positive_force - negative_force) / (
            2.0 * delta
        )

    gradient_scale = max(
        1.0,
        float(np.linalg.norm(force, ord=np.inf)),
        float(np.linalg.norm(finite_difference_gradient, ord=np.inf)),
    )
    tangent_scale = max(
        1.0,
        float(np.linalg.norm(tangent, ord=np.inf)),
        float(np.linalg.norm(finite_difference_tangent, ord=np.inf)),
    )
    gradient_relative_error = (
        float(np.linalg.norm(force - finite_difference_gradient, ord=np.inf))
        / gradient_scale
    )
    tangent_relative_error = (
        float(np.linalg.norm(tangent - finite_difference_tangent, ord=np.inf))
        / tangent_scale
    )
    symmetry_relative_error = (
        float(np.linalg.norm(tangent - tangent.T, ord=np.inf)) / tangent_scale
    )
    contract_pass = bool(
        gradient_relative_error <= 1.0e-7
        and tangent_relative_error <= 2.0e-7
        and symmetry_relative_error <= 1.0e-12
    )
    return {
        "equation_count": problem.free_dof_count,
        "perturbation_m": delta,
        "energy_gradient_relative_error": gradient_relative_error,
        "tangent_hessian_relative_error": tangent_relative_error,
        "tangent_symmetry_relative_error": symmetry_relative_error,
        "contract_pass": contract_pass,
    }


def _checkpoint_path_row(
    problem: LeeFrameArcLengthProblem,
    checkpoint: VectorArcLengthCheckpoint,
) -> dict[str, Any]:
    horizontal, downward = problem.load_point_displacements_m(
        np.asarray(checkpoint.free_displacements_m, dtype=np.float64)
    )
    return {
        "step_index": checkpoint.step_index,
        "horizontal_displacement_m": horizontal,
        "downward_displacement_m": downward,
        "load_proportionality_factor": checkpoint.load_factor,
        "state_hash": checkpoint.state_hash,
    }


def _published_path_comparisons(
    path_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    computed_points = np.asarray(
        [
            [
                row["horizontal_displacement_m"],
                row["downward_displacement_m"],
            ]
            for row in path_rows
        ],
        dtype=np.float64,
    )
    computed_loads = np.asarray(
        [row["load_proportionality_factor"] for row in path_rows],
        dtype=np.float64,
    )
    comparisons: list[dict[str, Any]] = []
    first_allowed_segment = 0
    for reference_index, (reference_x, reference_y, reference_load) in enumerate(
        LEE_FRAME_PUBLISHED_PATH
    ):
        reference_point = np.asarray([reference_x, reference_y], dtype=np.float64)
        best: tuple[float, int, float, np.ndarray, float] | None = None
        for segment_index in range(first_allowed_segment, len(path_rows) - 1):
            left = computed_points[segment_index]
            segment = computed_points[segment_index + 1] - left
            squared_length = float(segment @ segment)
            if squared_length <= np.finfo(np.float64).tiny:
                fraction = 0.0
            else:
                fraction = min(
                    1.0,
                    max(
                        0.0,
                        float((reference_point - left) @ segment) / squared_length,
                    ),
                )
            projected = left + fraction * segment
            distance = float(np.linalg.norm(projected - reference_point))
            projected_load = float(
                computed_loads[segment_index]
                + fraction
                * (computed_loads[segment_index + 1] - computed_loads[segment_index])
            )
            candidate = (
                distance,
                segment_index,
                fraction,
                projected,
                projected_load,
            )
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None:
            raise RuntimeError("computed Lee-frame path has no comparison segment")
        distance, segment_index, fraction, projected, projected_load = best
        first_allowed_segment = segment_index
        load_error = abs(projected_load - reference_load)
        comparisons.append(
            {
                "reference_index": reference_index,
                "reference_horizontal_displacement_m": reference_x,
                "reference_downward_displacement_m": reference_y,
                "reference_load_proportionality_factor": reference_load,
                "computed_segment_start_step_index": path_rows[segment_index][
                    "step_index"
                ],
                "computed_segment_fraction": fraction,
                "projected_horizontal_displacement_m": float(projected[0]),
                "projected_downward_displacement_m": float(projected[1]),
                "projected_load_proportionality_factor": projected_load,
                "displacement_path_distance_m": distance,
                "load_factor_absolute_error": load_error,
            }
        )
    return comparisons


def _first_local_maximum_index(values: list[float]) -> int | None:
    for index in range(1, len(values) - 1):
        if values[index] > values[index - 1] and values[index] > values[index + 1]:
            return index
    return None


def build_lee_frame_snapthrough_benchmark(
    *,
    elements_per_member: int = 10,
) -> dict[str, Any]:
    """Run the published elastic Lee-frame path and build a bounded receipt."""

    problem = LeeFrameArcLengthProblem(elements_per_member=elements_per_member)
    config = lee_frame_arc_length_config(problem)
    arc_length_problem = cast(VectorArcLengthProblem, problem)
    result = vector_arc_length_continuation(arc_length_problem, config=config)
    path_rows = [
        _checkpoint_path_row(problem, checkpoint) for checkpoint in result.checkpoints
    ]
    comparisons = _published_path_comparisons(path_rows)
    maximum_displacement_distance = max(
        row["displacement_path_distance_m"] for row in comparisons
    )
    maximum_load_error = max(row["load_factor_absolute_error"] for row in comparisons)
    root_mean_square_load_error = math.sqrt(
        sum(row["load_factor_absolute_error"] ** 2 for row in comparisons)
        / len(comparisons)
    )

    load_factors = [row["load_proportionality_factor"] for row in path_rows]
    downward_displacements = [row["downward_displacement_m"] for row in path_rows]
    horizontal_displacements = [row["horizontal_displacement_m"] for row in path_rows]
    first_maximum_index = _first_local_maximum_index(load_factors)
    if first_maximum_index is None:
        first_limit_point = None
        first_limit_load_error = math.inf
    else:
        first_limit_point = path_rows[first_maximum_index]
        first_limit_load_error = abs(
            first_limit_point["load_proportionality_factor"] - 18.59
        )
    snapback_observed = any(
        right < left
        for left, right in zip(
            downward_displacements,
            downward_displacements[1:],
        )
    ) and any(
        right < left
        for left, right in zip(
            horizontal_displacements,
            horizontal_displacements[1:],
        )
    )
    path_shape_contract_pass = bool(
        first_limit_point is not None
        and first_limit_load_error <= 0.25
        and result.metrics["descending_load_branch_observed"] is True
        and result.metrics["negative_load_factor_observed"] is True
        and result.metrics["rehardening_load_branch_observed"] is True
        and snapback_observed
    )
    published_path_contract_pass = bool(
        maximum_displacement_distance <= 0.004
        and maximum_load_error <= 0.35
        and root_mean_square_load_error <= 0.20
    )

    midpoint_checkpoint = result.checkpoints[len(result.checkpoints) // 2]
    restarted = vector_arc_length_continuation(
        arc_length_problem,
        config=config,
        resume_from=midpoint_checkpoint,
    )
    checkpoint_restart_exact = restarted.final_checkpoint == result.final_checkpoint
    tangent_checks = finite_difference_lee_frame_checks(
        problem,
        free_displacements_m=np.asarray(
            midpoint_checkpoint.free_displacements_m,
            dtype=np.float64,
        ),
    )
    solver_contract_pass = bool(
        result.status == "ready"
        and result.terminal_reason == "target_monitor_displacement_reached"
        and result.metrics["contract_pass"] is True
        and result.metrics["equation_count"] == problem.free_dof_count
        and result.metrics["fallback_count"] == 0
        and result.metrics["regularization_count"] == 0
        and checkpoint_restart_exact
    )
    contract_pass = bool(
        solver_contract_pass
        and tangent_checks["contract_pass"]
        and path_shape_contract_pass
        and published_path_contract_pass
    )
    return {
        "schema_version": LEE_FRAME_SCHEMA_VERSION,
        "benchmark_id": "lee-frame-elastic-snapthrough-snapback-v1",
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "formulation": LEE_FRAME_FORMULATION,
        "reference": {
            "doi": LEE_FRAME_REFERENCE_DOI,
            "table": LEE_FRAME_REFERENCE_TABLE,
            "published_path_point_count": len(LEE_FRAME_PUBLISHED_PATH),
            "original_problem_citation": (
                "Lee, Manuel, and Rossow (1968), Large deflections and "
                "stability of elastic frames"
            ),
        },
        "problem_definition": {
            "member_length_m": problem.member_length_m,
            "load_offset_m": problem.load_offset_m,
            "youngs_modulus_mpa": (problem.youngs_modulus_kn_per_m2 / 1000.0),
            "area_m2": problem.area_m2,
            "second_moment_m4": problem.second_moment_m4,
            "reference_load_kn": problem.reference_load_kn_value,
            "support_condition": "both_outer_ends_translation_pinned",
            "elements_per_member": problem.elements_per_member,
            "free_equation_count": problem.free_dof_count,
            "rotation_coordinate_scale_m": (problem.rotation_coordinate_scale_m),
        },
        "solver": {
            "analysis_type": "dense_vector_spherical_arc_length",
            "terminal_reason": result.terminal_reason,
            "path_contract_hash": result.path_contract_hash,
            "accepted_step_count": result.metrics["accepted_step_count"],
            "rejected_step_count": result.metrics["rejected_step_count"],
            "maximum_checkpoint_residual_inf_norm_kn": result.metrics[
                "maximum_checkpoint_residual_inf_norm_kn"
            ],
            "maximum_accepted_constraint_residual_m2": result.metrics[
                "maximum_accepted_constraint_residual_m2"
            ],
            "fallback_count": result.metrics["fallback_count"],
            "regularization_count": result.metrics["regularization_count"],
            "initial_checkpoint_state_hash": (result.initial_checkpoint.state_hash),
            "restart_checkpoint_state_hash": midpoint_checkpoint.state_hash,
            "final_checkpoint_state_hash": result.final_checkpoint.state_hash,
            "restarted_final_checkpoint_state_hash": (
                restarted.final_checkpoint.state_hash
            ),
            "checkpoint_restart_exact": checkpoint_restart_exact,
            "contract_pass": solver_contract_pass,
        },
        "consistent_tangent_checks": tangent_checks,
        "path_shape": {
            "first_limit_point": first_limit_point,
            "published_first_limit_load_factor": 18.59,
            "first_limit_load_factor_absolute_error": first_limit_load_error,
            "descending_load_branch_observed": result.metrics[
                "descending_load_branch_observed"
            ],
            "negative_load_factor_observed": result.metrics[
                "negative_load_factor_observed"
            ],
            "rehardening_load_branch_observed": result.metrics[
                "rehardening_load_branch_observed"
            ],
            "snapback_observed": snapback_observed,
            "contract_pass": path_shape_contract_pass,
        },
        "published_path_comparisons": comparisons,
        "published_path_error_summary": {
            "maximum_displacement_path_distance_m": (maximum_displacement_distance),
            "maximum_load_factor_absolute_error": maximum_load_error,
            "root_mean_square_load_factor_error": (root_mean_square_load_error),
            "contract_pass": published_path_contract_pass,
        },
        "path_rows": path_rows,
        "claims": {
            "bounded_elastic_lee_frame_snapthrough_snapback": contract_pass,
            "published_reference_path_validation": (published_path_contract_pass),
            "energy_consistent_corotational_frame_element": (
                tangent_checks["contract_pass"]
            ),
            "dense_multi_dof_arc_length_connection": solver_contract_pass,
            "legacy_corotational_proxy_validated": False,
            "general_2d_3d_production_frame_or_shell": False,
            "material_geometric_coupling": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "legacy_corotational_proxy_not_promoted",
            "general_2d_3d_production_frame_shell_not_validated",
            "material_geometric_coupling_not_verified_on_lee_frame",
            "production_sparse_rocm_hip_path_not_connected",
            "full_building_equilibrium_not_closed",
            "g1_not_closed",
        ],
        "claim_boundary": LEE_FRAME_CLAIM_BOUNDARY,
    }


__all__ = [
    "CorotationalFrameElementResponse",
    "LEE_FRAME_CLAIM_BOUNDARY",
    "LEE_FRAME_FORMULATION",
    "LEE_FRAME_PUBLISHED_PATH",
    "LEE_FRAME_REFERENCE_DOI",
    "LEE_FRAME_REFERENCE_TABLE",
    "LEE_FRAME_SCHEMA_VERSION",
    "LeeFrameArcLengthProblem",
    "build_lee_frame_snapthrough_benchmark",
    "corotational_frame_element_response",
    "finite_difference_lee_frame_checks",
    "lee_frame_arc_length_config",
]
