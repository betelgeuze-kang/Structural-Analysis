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
    l = max(float(props.length_m), 1e-9)
    ea = float(props.e_mpa) * MPA_TO_PA * float(props.area_m2)
    ei = float(props.e_mpa) * MPA_TO_PA * float(props.iy_m4)
    k = np.array(
        [
            [ea / l, 0.0, 0.0, -ea / l, 0.0, 0.0],
            [0.0, 12.0 * ei / l**3, 6.0 * ei / l**2, 0.0, -12.0 * ei / l**3, 6.0 * ei / l**2],
            [0.0, 6.0 * ei / l**2, 4.0 * ei / l, 0.0, -6.0 * ei / l**2, 2.0 * ei / l],
            [-ea / l, 0.0, 0.0, ea / l, 0.0, 0.0],
            [0.0, -12.0 * ei / l**3, -6.0 * ei / l**2, 0.0, 12.0 * ei / l**3, -6.0 * ei / l**2],
            [0.0, 6.0 * ei / l**2, 2.0 * ei / l, 0.0, -6.0 * ei / l**2, 4.0 * ei / l],
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
    l = max(float(props.length_m), 1e-9)
    p = max(float(axial_force_n), 0.0)
    if p <= 0.0:
        return np.zeros((6, 6), dtype=np.float64)
    coeff = p / (30.0 * l)
    kg = coeff * np.array(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 36.0, 3.0 * l, 0.0, -36.0, 3.0 * l],
            [0.0, 3.0 * l, 4.0 * l**2, 0.0, -3.0 * l, -1.0 * l**2],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, -36.0, -3.0 * l, 0.0, 36.0, -3.0 * l],
            [0.0, 3.0 * l, -1.0 * l**2, 0.0, -3.0 * l, 4.0 * l**2],
        ],
        dtype=np.float64,
    )
    return kg


def _elastic_flexural_rigidity_n_m2(props: BeamColumnProperties) -> float:
    return float(props.e_mpa) * MPA_TO_PA * float(props.iy_m4)


def _elastic_critical_axial_force_n(props: BeamColumnProperties) -> float:
    l = max(float(props.length_m), 1e-9)
    ei = max(_elastic_flexural_rigidity_n_m2(props), 1e-9)
    return float(np.pi**2 * ei / l**2)


def _yield_rotation_proxy_rad(props: BeamColumnProperties) -> float:
    l = max(float(props.length_m), 1e-9)
    ei = max(_elastic_flexural_rigidity_n_m2(props), 1e-9)
    yield_moment_n_m = max(float(props.yield_moment_kNm), 1e-9) * 1000.0
    return float(yield_moment_n_m * l / (4.0 * ei))


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


__all__ = [
    "BeamColumnProperties",
    "BeamColumnGlobalResponse",
    "BeamColumnSupportedResponse",
    "BeamColumnResponse",
    "elastic_local_stiffness",
    "frame_2d_transformation_from_nodes",
    "frame_2d_transformation_matrix",
    "geometric_local_stiffness",
    "solve_beam_column_global_response",
    "solve_beam_column_supported_response",
    "solve_beam_column_response",
]
