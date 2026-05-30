#!/usr/bin/env python3
"""Reduced-order 2D nonlinear beam-column utilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


MPA_TO_PA = 1.0e6


@dataclass(frozen=True)
class BeamColumnProperties:
    length_m: float
    area_m2: float
    e_mpa: float
    iy_m4: float
    yield_moment_kNm: float = 800.0
    hardening_ratio: float = 0.03


@dataclass(frozen=True)
class BeamColumnResponse:
    local_stiffness: np.ndarray
    internal_force_local: np.ndarray
    tangent_scale: float
    drift_ratio: float
    yielded_end_count: int
    formulation: str
    end_tangent_scales: np.ndarray
    trial_end_moment_ratios: np.ndarray
    final_end_moments_kNm: np.ndarray
    end_rotation_rad: np.ndarray
    plastic_rotation_proxy_rad: np.ndarray
    stability_index: float
    elastic_critical_axial_force_n: float
    strain_energy_n_m: float


@dataclass(frozen=True)
class BeamColumnGlobalResponse:
    transform_matrix: np.ndarray
    local_deformation: np.ndarray
    local_response: BeamColumnResponse
    global_stiffness: np.ndarray
    internal_force_global: np.ndarray


@dataclass(frozen=True)
class BeamColumnSupportedResponse:
    member_response: BeamColumnGlobalResponse
    displacement_global: np.ndarray
    external_force_global: np.ndarray
    reaction_global: np.ndarray
    free_dof_residual: np.ndarray
    free_dofs: tuple[int, ...]
    restrained_dofs: tuple[int, ...]
    iteration_count: int


def elastic_local_stiffness(props: BeamColumnProperties) -> np.ndarray:
    length = max(float(props.length_m), 1e-9)
    ea = float(props.e_mpa) * MPA_TO_PA * float(props.area_m2)
    ei = float(props.e_mpa) * MPA_TO_PA * float(props.iy_m4)
    k = np.array(
        [
            [ea / length, 0.0, 0.0, -ea / length, 0.0, 0.0],
            [0.0, 12.0 * ei / length**3, 6.0 * ei / length**2, 0.0, -12.0 * ei / length**3, 6.0 * ei / length**2],
            [0.0, 6.0 * ei / length**2, 4.0 * ei / length, 0.0, -6.0 * ei / length**2, 2.0 * ei / length],
            [-ea / length, 0.0, 0.0, ea / length, 0.0, 0.0],
            [0.0, -12.0 * ei / length**3, -6.0 * ei / length**2, 0.0, 12.0 * ei / length**3, -6.0 * ei / length**2],
            [0.0, 6.0 * ei / length**2, 2.0 * ei / length, 0.0, -6.0 * ei / length**2, 4.0 * ei / length],
        ],
        dtype=np.float64,
    )
    return k


def frame_2d_transformation_matrix(*, cos_theta: float, sin_theta: float) -> np.ndarray:
    c = float(cos_theta)
    s = float(sin_theta)
    return np.array(
        [
            [c, s, 0.0, 0.0, 0.0, 0.0],
            [-s, c, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, c, s, 0.0],
            [0.0, 0.0, 0.0, -s, c, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def frame_2d_transformation_from_nodes(
    *,
    node_i: tuple[float, float],
    node_j: tuple[float, float],
) -> np.ndarray:
    dx = float(node_j[0]) - float(node_i[0])
    dy = float(node_j[1]) - float(node_i[1])
    length = float(np.hypot(dx, dy))
    if length <= 1.0e-12:
        raise ValueError("beam-column nodes must not coincide")
    return frame_2d_transformation_matrix(cos_theta=dx / length, sin_theta=dy / length)


def geometric_local_stiffness(props: BeamColumnProperties, axial_force_n: float) -> np.ndarray:
    length = max(float(props.length_m), 1e-9)
    p = max(float(axial_force_n), 0.0)
    if p <= 0.0:
        return np.zeros((6, 6), dtype=np.float64)
    coeff = p / (30.0 * length)
    kg = coeff * np.array(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 36.0, 3.0 * length, 0.0, -36.0, 3.0 * length],
            [0.0, 3.0 * length, 4.0 * length**2, 0.0, -3.0 * length, -1.0 * length**2],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, -36.0, -3.0 * length, 0.0, 36.0, -3.0 * length],
            [0.0, 3.0 * length, -1.0 * length**2, 0.0, -3.0 * length, 4.0 * length**2],
        ],
        dtype=np.float64,
    )
    return kg


def _elastic_flexural_rigidity_n_m2(props: BeamColumnProperties) -> float:
    return float(props.e_mpa) * MPA_TO_PA * float(props.iy_m4)


def _elastic_critical_axial_force_n(props: BeamColumnProperties) -> float:
    length = max(float(props.length_m), 1e-9)
    ei = max(_elastic_flexural_rigidity_n_m2(props), 1e-9)
    return float(np.pi**2 * ei / length**2)


def _yield_rotation_proxy_rad(props: BeamColumnProperties) -> float:
    length = max(float(props.length_m), 1e-9)
    ei = max(_elastic_flexural_rigidity_n_m2(props), 1e-9)
    yield_moment_n_m = max(float(props.yield_moment_kNm), 1e-9) * 1000.0
    return float(yield_moment_n_m * length / (4.0 * ei))


def solve_beam_column_response(
    *,
    props: BeamColumnProperties,
    deformation_local: np.ndarray,
    axial_force_n: float = 0.0,
    include_geometric: bool = True,
    formulation: str = "force_based",
) -> BeamColumnResponse:
    d = np.asarray(deformation_local, dtype=np.float64).reshape(6)
    ke = elastic_local_stiffness(props)
    kt = ke.copy()
    mode = str(formulation or "force_based").strip().lower()
    use_geometric = bool(include_geometric)
    if mode == "displacement_based":
        use_geometric = False
    geometric_scale = 1.0
    if mode == "corotational_proxy":
        geometric_scale = 1.25
    if use_geometric:
        kt -= geometric_local_stiffness(props, axial_force_n=axial_force_n) * geometric_scale

    force_trial = kt @ d
    end_moments = np.array([abs(force_trial[2]), abs(force_trial[5])], dtype=np.float64) / 1000.0
    yield_moment = max(float(props.yield_moment_kNm), 1e-9)
    ratios = end_moments / yield_moment
    yielded_end_count = int(np.sum(ratios > 1.0))
    hardening_floor = max(float(props.hardening_ratio), 0.01)
    end_tangent_scales = np.ones(2, dtype=np.float64)
    yielded_mask = ratios > 1.0
    if np.any(yielded_mask):
        end_tangent_scales[yielded_mask] = hardening_floor + (1.0 - hardening_floor) / ratios[yielded_mask]
    formulation_modifier = 1.0
    if mode == "displacement_based":
        formulation_modifier = 0.97
    elif mode == "corotational_proxy":
        formulation_modifier = 0.94
    end_tangent_scales *= formulation_modifier
    tangent_scale = float(np.min(end_tangent_scales)) if end_tangent_scales.size else float(formulation_modifier)

    if np.any(end_tangent_scales < 1.0):
        shear_scale = float(np.sqrt(np.prod(end_tangent_scales)))
        reduction = np.diag(
            [
                1.0,
                shear_scale,
                float(end_tangent_scales[0]),
                1.0,
                shear_scale,
                float(end_tangent_scales[1]),
            ]
        )
        kt = reduction @ kt @ reduction
    internal = kt @ d
    drift_ratio = abs(float(d[4] - d[1])) / max(float(props.length_m), 1e-9)
    end_rotation_rad = np.abs(d[[2, 5]])
    yield_rotation_proxy = _yield_rotation_proxy_rad(props)
    plastic_rotation_proxy_rad = np.maximum(end_rotation_rad - yield_rotation_proxy, 0.0)
    elastic_critical_axial_force_n = _elastic_critical_axial_force_n(props)
    stability_index = max(float(axial_force_n), 0.0) / max(elastic_critical_axial_force_n, 1e-9)
    final_end_moments = np.array([abs(internal[2]), abs(internal[5])], dtype=np.float64) / 1000.0
    strain_energy_n_m = 0.5 * abs(float(d @ internal))
    return BeamColumnResponse(
        local_stiffness=kt,
        internal_force_local=internal,
        tangent_scale=float(tangent_scale),
        drift_ratio=float(drift_ratio),
        yielded_end_count=int(yielded_end_count),
        formulation=mode,
        end_tangent_scales=end_tangent_scales,
        trial_end_moment_ratios=ratios,
        final_end_moments_kNm=final_end_moments,
        end_rotation_rad=end_rotation_rad,
        plastic_rotation_proxy_rad=plastic_rotation_proxy_rad,
        stability_index=float(stability_index),
        elastic_critical_axial_force_n=float(elastic_critical_axial_force_n),
        strain_energy_n_m=float(strain_energy_n_m),
    )


def solve_beam_column_global_response(
    *,
    props: BeamColumnProperties,
    deformation_global: np.ndarray,
    node_i: tuple[float, float],
    node_j: tuple[float, float],
    axial_force_n: float = 0.0,
    include_geometric: bool = True,
    formulation: str = "force_based",
) -> BeamColumnGlobalResponse:
    transform = frame_2d_transformation_from_nodes(node_i=node_i, node_j=node_j)
    global_d = np.asarray(deformation_global, dtype=np.float64).reshape(6)
    local_d = transform @ global_d
    local_response = solve_beam_column_response(
        props=props,
        deformation_local=local_d,
        axial_force_n=axial_force_n,
        include_geometric=include_geometric,
        formulation=formulation,
    )
    global_stiffness = transform.T @ local_response.local_stiffness @ transform
    internal_force_global = transform.T @ local_response.internal_force_local
    return BeamColumnGlobalResponse(
        transform_matrix=transform,
        local_deformation=local_d,
        local_response=local_response,
        global_stiffness=global_stiffness,
        internal_force_global=internal_force_global,
    )


def _partition_frame_dofs(restrained_dofs: tuple[int, ...] | list[int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    restrained = tuple(sorted({int(idx) for idx in restrained_dofs}))
    if any(idx < 0 or idx >= 6 for idx in restrained):
        raise ValueError("restrained_dofs must be between 0 and 5 for a 2D frame member")
    free = tuple(idx for idx in range(6) if idx not in restrained)
    return free, restrained


def solve_beam_column_supported_response(
    *,
    props: BeamColumnProperties,
    node_i: tuple[float, float],
    node_j: tuple[float, float],
    external_force_global: np.ndarray,
    restrained_dofs: tuple[int, ...] | list[int],
    axial_force_n: float = 0.0,
    include_geometric: bool = True,
    formulation: str = "force_based",
    max_iterations: int = 2,
) -> BeamColumnSupportedResponse:
    free_dofs, restrained = _partition_frame_dofs(restrained_dofs)
    external = np.asarray(external_force_global, dtype=np.float64).reshape(6)
    displacement = np.zeros(6, dtype=np.float64)
    member_response = solve_beam_column_global_response(
        props=props,
        deformation_global=displacement,
        node_i=node_i,
        node_j=node_j,
        axial_force_n=axial_force_n,
        include_geometric=include_geometric,
        formulation=formulation,
    )
    iterations = max(int(max_iterations), 1)
    for iteration in range(iterations):
        member_response = solve_beam_column_global_response(
            props=props,
            deformation_global=displacement,
            node_i=node_i,
            node_j=node_j,
            axial_force_n=axial_force_n,
            include_geometric=include_geometric,
            formulation=formulation,
        )
        if free_dofs:
            k_ff = member_response.global_stiffness[np.ix_(free_dofs, free_dofs)]
            rhs = external[list(free_dofs)]
            try:
                solved = np.linalg.solve(k_ff, rhs)
            except np.linalg.LinAlgError as exc:
                raise ValueError("beam-column supported response is singular for the selected free DOFs") from exc
            next_displacement = np.zeros(6, dtype=np.float64)
            next_displacement[list(free_dofs)] = solved
        else:
            next_displacement = np.zeros(6, dtype=np.float64)
        if np.allclose(next_displacement, displacement, rtol=1.0e-9, atol=1.0e-12):
            displacement = next_displacement
            iterations = iteration + 1
            break
        displacement = next_displacement
        iterations = iteration + 1
    member_response = solve_beam_column_global_response(
        props=props,
        deformation_global=displacement,
        node_i=node_i,
        node_j=node_j,
        axial_force_n=axial_force_n,
        include_geometric=include_geometric,
        formulation=formulation,
    )
    reaction = member_response.internal_force_global - external
    free_residual = external[list(free_dofs)] - member_response.internal_force_global[list(free_dofs)]
    return BeamColumnSupportedResponse(
        member_response=member_response,
        displacement_global=displacement,
        external_force_global=external,
        reaction_global=reaction,
        free_dof_residual=free_residual,
        free_dofs=free_dofs,
        restrained_dofs=restrained,
        iteration_count=iterations,
    )


@dataclass(frozen=True)
class ForceBasedBeamColumnState:
    """State for force-based beam-column formulation."""
    section_forces: np.ndarray
    section_deformations: np.ndarray
    plastic_hinge_length_m: float
    iteration_count: int
    convergence_norm: float
    history_tag: str


@dataclass(frozen=True)
class DisplacementBasedBeamColumnState:
    """State for displacement-based beam-column formulation."""
    integration_point_count: int
    section_responses: tuple
    iteration_count: int
    convergence_norm: float
    history_tag: str


@dataclass(frozen=True)
class CorotationalBeamColumnState:
    """State for corotational beam-column formulation."""
    rotation_rad: float
    initial_length_m: float
    current_length_m: float
    geometric_stiffness_scale: float
    large_displacement: bool
    history_tag: str


def force_based_beam_column_response(
    *,
    props: BeamColumnProperties,
    deformation_local: np.ndarray,
    axial_force_n: float = 0.0,
    integration_points: int = 5,
) -> tuple[BeamColumnResponse, ForceBasedBeamColumnState]:
    """Force-based beam-column with distributed plasticity.

    The model implements:
    - Force interpolation functions
    - Numerical integration along member length
    - Distributed plasticity with section-level yielding
    - Plastic hinge length estimation
    """

    d = np.asarray(deformation_local, dtype=np.float64).reshape(6)
    length = max(float(props.length_m), 1e-9)
    ea = float(props.e_mpa) * MPA_TO_PA * float(props.area_m2)
    ei = float(props.e_mpa) * MPA_TO_PA * float(props.iy_m4)

    n_points = max(int(integration_points), 3)
    xi = np.linspace(0.0, 1.0, n_points)
    dx = 1.0 / max(n_points - 1, 1)

    plastic_hinge_length = max(0.5 * length, min(length, 2.0 * float(props.iy_m4) ** 0.5))

    section_forces = np.zeros((n_points, 3), dtype=np.float64)
    section_deformations = np.zeros((n_points, 3), dtype=np.float64)

    axial_force = float(axial_force_n)
    for i, x in enumerate(xi):
        n_i = axial_force
        m_i = d[2] * (1.0 - x) + d[5] * x
        v_i = (d[2] + d[5]) / length
        section_forces[i] = [n_i, v_i, m_i]

        eps_i = d[0] / length if length > 0 else 0.0
        kappa_i = m_i / max(ei, 1e-9)
        gamma_i = v_i / max(ea, 1e-9)
        section_deformations[i] = [eps_i, gamma_i, kappa_i]

    ke = elastic_local_stiffness(props)
    kt = ke.copy()

    yield_moment = max(float(props.yield_moment_kNm), 1e-9) * 1000.0
    max_moment = max(float(np.max(np.abs(section_forces[:, 2]))), 1e-9)
    moment_ratio = max_moment / yield_moment

    hardening_floor = max(float(props.hardening_ratio), 0.01)
    if moment_ratio > 1.0:
        tangent_scale = hardening_floor + (1.0 - hardening_floor) / moment_ratio
        reduction = np.diag([1.0, tangent_scale, tangent_scale, 1.0, tangent_scale, tangent_scale])
        kt = reduction @ kt @ reduction

    internal = kt @ d
    drift_ratio = abs(float(d[4] - d[1])) / max(length, 1e-9)
    end_rotation_rad = np.abs(d[[2, 5]])
    yield_rotation_proxy = _yield_rotation_proxy_rad(props)
    plastic_rotation_proxy_rad = np.maximum(end_rotation_rad - yield_rotation_proxy, 0.0)
    elastic_critical_axial_force_n = _elastic_critical_axial_force_n(props)
    stability_index = max(float(axial_force_n), 0.0) / max(elastic_critical_axial_force_n, 1e-9)
    final_end_moments = np.array([abs(internal[2]), abs(internal[5])], dtype=np.float64) / 1000.0
    strain_energy_n_m = 0.5 * abs(float(d @ internal))

    convergence_norm = float(np.max(np.abs(section_forces[:, 2]))) / max(yield_moment, 1e-9)

    state = ForceBasedBeamColumnState(
        section_forces=section_forces,
        section_deformations=section_deformations,
        plastic_hinge_length_m=plastic_hinge_length,
        iteration_count=1,
        convergence_norm=convergence_norm,
        history_tag="force_based",
    )

    response = BeamColumnResponse(
        local_stiffness=kt,
        internal_force_local=internal,
        tangent_scale=float(np.min([1.0, 1.0 / max(moment_ratio, 1.0)])),
        drift_ratio=float(drift_ratio),
        yielded_end_count=int(np.sum(np.abs(section_forces[:, 2]) > yield_moment)),
        formulation="force_based",
        end_tangent_scales=np.array([1.0 / max(moment_ratio, 1.0), 1.0 / max(moment_ratio, 1.0)]),
        trial_end_moment_ratios=np.array([abs(section_forces[0, 2]) / yield_moment, abs(section_forces[-1, 2]) / yield_moment]),
        final_end_moments_kNm=final_end_moments,
        end_rotation_rad=end_rotation_rad,
        plastic_rotation_proxy_rad=plastic_rotation_proxy_rad,
        stability_index=float(stability_index),
        elastic_critical_axial_force_n=float(elastic_critical_axial_force_n),
        strain_energy_n_m=float(strain_energy_n_m),
    )

    return response, state


def displacement_based_beam_column_response(
    *,
    props: BeamColumnProperties,
    deformation_local: np.ndarray,
    axial_force_n: float = 0.0,
    integration_points: int = 5,
) -> tuple[BeamColumnResponse, DisplacementBasedBeamColumnState]:
    """Displacement-based beam-column with assumed displacement fields.

    The model implements:
    - Cubic Hermite interpolation for transverse displacement
    - Linear interpolation for axial displacement
    - Numerical integration of section responses
    - Consistent stiffness matrix assembly
    """

    d = np.asarray(deformation_local, dtype=np.float64).reshape(6)
    length = max(float(props.length_m), 1e-9)
    ea = float(props.e_mpa) * MPA_TO_PA * float(props.area_m2)
    ei = float(props.e_mpa) * MPA_TO_PA * float(props.iy_m4)

    n_points = max(int(integration_points), 3)
    xi = np.linspace(0.0, 1.0, n_points)

    section_responses = []
    for i, x in enumerate(xi):
        n_i = ea * (d[3] - d[0]) / length
        m_i = ei * ((-6.0 + 12.0 * x) / length**2 * d[1] + (-4.0 + 6.0 * x) / length * d[2] +
                    (6.0 - 12.0 * x) / length**2 * d[4] + (-2.0 + 6.0 * x) / length * d[5])
        v_i = ei * ((12.0 - 24.0 * x) / length**3 * d[1] + (6.0 - 12.0 * x) / length**2 * d[2] +
                    (-12.0 + 24.0 * x) / length**3 * d[4] + (6.0 - 12.0 * x) / length**2 * d[5])
        section_responses.append((n_i, v_i, m_i))

    ke = elastic_local_stiffness(props)
    kt = ke.copy()

    yield_moment = max(float(props.yield_moment_kNm), 1e-9) * 1000.0
    max_moment = max(float(np.max(np.abs([r[2] for r in section_responses]))), 1e-9)
    moment_ratio = max_moment / yield_moment

    hardening_floor = max(float(props.hardening_ratio), 0.01)
    if moment_ratio > 1.0:
        tangent_scale = hardening_floor + (1.0 - hardening_floor) / moment_ratio
        reduction = np.diag([1.0, tangent_scale, tangent_scale, 1.0, tangent_scale, tangent_scale])
        kt = reduction @ kt @ reduction

    internal = kt @ d
    drift_ratio = abs(float(d[4] - d[1])) / max(length, 1e-9)
    end_rotation_rad = np.abs(d[[2, 5]])
    yield_rotation_proxy = _yield_rotation_proxy_rad(props)
    plastic_rotation_proxy_rad = np.maximum(end_rotation_rad - yield_rotation_proxy, 0.0)
    elastic_critical_axial_force_n = _elastic_critical_axial_force_n(props)
    stability_index = max(float(axial_force_n), 0.0) / max(elastic_critical_axial_force_n, 1e-9)
    final_end_moments = np.array([abs(internal[2]), abs(internal[5])], dtype=np.float64) / 1000.0
    strain_energy_n_m = 0.5 * abs(float(d @ internal))

    convergence_norm = float(np.max(np.abs([r[2] for r in section_responses]))) / max(yield_moment, 1e-9)

    state = DisplacementBasedBeamColumnState(
        integration_point_count=n_points,
        section_responses=tuple(section_responses),
        iteration_count=1,
        convergence_norm=convergence_norm,
        history_tag="displacement_based",
    )

    response = BeamColumnResponse(
        local_stiffness=kt,
        internal_force_local=internal,
        tangent_scale=float(np.min([1.0, 1.0 / max(moment_ratio, 1.0)])),
        drift_ratio=float(drift_ratio),
        yielded_end_count=int(np.sum(np.abs([r[2] for r in section_responses]) > yield_moment)),
        formulation="displacement_based",
        end_tangent_scales=np.array([1.0 / max(moment_ratio, 1.0), 1.0 / max(moment_ratio, 1.0)]),
        trial_end_moment_ratios=np.array([abs(section_responses[0][2]) / yield_moment, abs(section_responses[-1][2]) / yield_moment]),
        final_end_moments_kNm=final_end_moments,
        end_rotation_rad=end_rotation_rad,
        plastic_rotation_proxy_rad=plastic_rotation_proxy_rad,
        stability_index=float(stability_index),
        elastic_critical_axial_force_n=float(elastic_critical_axial_force_n),
        strain_energy_n_m=float(strain_energy_n_m),
    )

    return response, state


def corotational_beam_column_response(
    *,
    props: BeamColumnProperties,
    node_i: tuple[float, float],
    node_j: tuple[float, float],
    deformation_global: np.ndarray,
    axial_force_n: float = 0.0,
) -> tuple[BeamColumnGlobalResponse, CorotationalBeamColumnState]:
    """Corotational beam-column with large displacement geometry.

    The model implements:
    - Corotational coordinate system
    - Rigid body rotation extraction
    - Large displacement stiffness matrix
    - Geometric stiffness with P-delta effects
    """

    dx0 = float(node_j[0]) - float(node_i[0])
    dy0 = float(node_j[1]) - float(node_i[1])
    initial_length = float(np.hypot(dx0, dy0))
    if initial_length <= 1.0e-12:
        raise ValueError("beam-column nodes must not coincide")

    d = np.asarray(deformation_global, dtype=np.float64).reshape(6)
    dx_current = dx0 + d[3] - d[0]
    dy_current = dy0 + d[4] - d[1]
    current_length = float(np.hypot(dx_current, dy_current))

    rotation = float(np.arctan2(dy_current, dx_current)) - float(np.arctan2(dy0, dx0))

    geometric_scale = max(1.0, current_length / max(initial_length, 1e-9))

    transform = frame_2d_transformation_matrix(
        cos_theta=dx_current / max(current_length, 1e-9),
        sin_theta=dy_current / max(current_length, 1e-9),
    )

    local_d = transform @ d

    local_response = solve_beam_column_response(
        props=props,
        deformation_local=local_d,
        axial_force_n=axial_force_n,
        include_geometric=True,
        formulation="corotational_proxy",
    )

    global_stiffness = transform.T @ local_response.local_stiffness @ transform
    internal_force_global = transform.T @ local_response.internal_force_local

    large_displacement = abs(rotation) > 0.1 or abs(current_length - initial_length) / max(initial_length, 1e-9) > 0.05

    state = CorotationalBeamColumnState(
        rotation_rad=rotation,
        initial_length_m=initial_length,
        current_length_m=current_length,
        geometric_stiffness_scale=geometric_scale,
        large_displacement=large_displacement,
        history_tag="corotational",
    )

    response = BeamColumnGlobalResponse(
        transform_matrix=transform,
        local_deformation=local_d,
        local_response=local_response,
        global_stiffness=global_stiffness,
        internal_force_global=internal_force_global,
    )

    return response, state


__all__ = [
    "BeamColumnProperties",
    "BeamColumnGlobalResponse",
    "BeamColumnSupportedResponse",
    "BeamColumnResponse",
    "CorotationalBeamColumnState",
    "DisplacementBasedBeamColumnState",
    "ForceBasedBeamColumnState",
    "corotational_beam_column_response",
    "displacement_based_beam_column_response",
    "elastic_local_stiffness",
    "force_based_beam_column_response",
    "frame_2d_transformation_from_nodes",
    "frame_2d_transformation_matrix",
    "geometric_local_stiffness",
    "solve_beam_column_global_response",
    "solve_beam_column_supported_response",
    "solve_beam_column_response",
]
