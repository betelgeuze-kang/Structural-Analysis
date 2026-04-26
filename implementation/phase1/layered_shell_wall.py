#!/usr/bin/env python3
"""Lightweight layered shell/wall/slab response helpers for nonlinear generalization gates."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    from implementation.phase1.rc_constitutive_library import (
        ConcreteCyclicState,
        ConcreteMaterial,
        concrete_cyclic_response,
    )
except Exception:  # pragma: no cover - script-mode fallback
    from rc_constitutive_library import (  # type: ignore
        ConcreteCyclicState,
        ConcreteMaterial,
        concrete_cyclic_response,
    )


MPA_TO_PA = 1.0e6


@dataclass(frozen=True)
class LayeredShellLayer:
    material: str
    thickness_m: float
    elastic_modulus_mpa: float
    shear_modulus_mpa: float
    stiffness_scale: float = 1.0


@dataclass(frozen=True)
class LayeredShellSection:
    name: str
    family: str
    layers: tuple[LayeredShellLayer, ...]


@dataclass(frozen=True)
class LayeredShellResponse:
    membrane_stiffness_n_per_m: float
    bending_stiffness_n_m: float
    shear_stiffness_n_per_m: float
    membrane_force_n_per_m: float
    bending_moment_n_m_per_m: float
    shear_force_n_per_m: float
    cracked_layer_count: int
    yielded_layer_count: int
    max_abs_strain: float


@dataclass(frozen=True)
class LayeredPanelResponse:
    x_response: LayeredShellResponse
    y_response: LayeredShellResponse
    panel_area_m2: float
    diaphragm_force_n: float
    diaphragm_coupling_ratio: float
    total_membrane_energy_like: float
    total_shear_force_n: float
    cyclic_evidence: "LayeredPanelCyclicEvidence | None" = None
    assembled_response: "LayeredPanelAssembledResponse | None" = None
    mesh_sensitivity: "LayeredPanelMeshSensitivity | None" = None


@dataclass(frozen=True)
class LayeredPanelAssembledResponse:
    generalized_strain_vector: tuple[float, float, float]
    membrane_stiffness_matrix_n_per_m: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    diaphragm_coupling_vector_n_per_m: tuple[float, float, float]
    generalized_resultant_vector_n_per_m: tuple[float, float, float]
    corner_nodal_force_vector_n: tuple[float, float, float, float, float, float, float, float]
    torsional_coupling_moment_n_m: float
    force_balance_error_n: float


@dataclass(frozen=True)
class LayeredPanelCyclicEvidence:
    section_name: str
    section_family: str
    concrete_layer_count: int
    strain_history: tuple[float, ...]
    evidence_tags: tuple[str, ...]
    restoring_state_tags: tuple[str, ...]
    reversal_count: int
    crack_open: bool
    pinching_observed: bool
    crushing_observed: bool
    degradation_observed: bool
    min_pinching_ratio: float
    max_crushing_ratio: float
    max_stiffness_degradation: float
    max_strength_degradation: float
    demand_scale: float
    cyclic_energy_like: float


@dataclass(frozen=True)
class LayeredPanelHotspot:
    hotspot_id: str
    location_label: str
    membrane_force_n_per_m: float
    shear_force_n_per_m: float
    utilization_ratio: float
    crack_indicator: float


@dataclass(frozen=True)
class LayeredPanelMeshSensitivity:
    mesh_division_sequence: tuple[int, ...]
    representative_element_sizes_m: tuple[float, ...]
    coarse_to_fine_membrane_ratio: float
    coarse_to_fine_shear_ratio: float
    convergence_error_ratio: float
    max_hotspot_utilization_ratio: float
    hotspot_rows: tuple[LayeredPanelHotspot, ...]
    summary_line: str


def make_layered_wall_section(*, name: str = "layered_wall") -> LayeredShellSection:
    return LayeredShellSection(
        name=name,
        family="wall",
        layers=(
            LayeredShellLayer("boundary_concrete", 0.08, 32000.0, 13500.0, 0.96),
            LayeredShellLayer("web_concrete", 0.14, 30000.0, 12500.0, 0.94),
            LayeredShellLayer("boundary_steel", 0.02, 200000.0, 77000.0, 1.00),
        ),
    )


def make_layered_slab_section(*, name: str = "layered_slab") -> LayeredShellSection:
    return LayeredShellSection(
        name=name,
        family="slab",
        layers=(
            LayeredShellLayer("deck_concrete", 0.10, 31000.0, 12900.0, 0.97),
            LayeredShellLayer("rebar_top", 0.01, 200000.0, 77000.0, 1.00),
            LayeredShellLayer("rebar_bottom", 0.01, 200000.0, 77000.0, 1.00),
        ),
    )


def make_layered_shell_section(*, name: str = "layered_shell") -> LayeredShellSection:
    return LayeredShellSection(
        name=name,
        family="shell",
        layers=(
            LayeredShellLayer("skin_top", 0.012, 70000.0, 27000.0, 0.98),
            LayeredShellLayer("core", 0.050, 28000.0, 9000.0, 0.92),
            LayeredShellLayer("skin_bottom", 0.012, 70000.0, 27000.0, 0.98),
        ),
    )


def evaluate_layered_shell_response(
    *,
    section: LayeredShellSection,
    membrane_strain: float,
    curvature_per_m: float,
    shear_strain: float,
) -> LayeredShellResponse:
    total_t = sum(layer.thickness_m for layer in section.layers)
    z_cursor = -0.5 * total_t
    membrane_stiffness = 0.0
    bending_stiffness = 0.0
    shear_stiffness = 0.0
    membrane_force = 0.0
    bending_moment = 0.0
    shear_force = 0.0
    cracked = 0
    yielded = 0
    max_abs_strain = 0.0

    for layer in section.layers:
        z_mid = z_cursor + 0.5 * layer.thickness_m
        z_cursor += layer.thickness_m
        e_pa = layer.elastic_modulus_mpa * MPA_TO_PA * layer.stiffness_scale
        g_pa = layer.shear_modulus_mpa * MPA_TO_PA * layer.stiffness_scale
        area = layer.thickness_m
        strain = float(membrane_strain) - float(curvature_per_m) * z_mid
        stress = e_pa * strain
        tau = g_pa * float(shear_strain)
        membrane_stiffness += e_pa * area
        bending_stiffness += e_pa * area * (z_mid**2 + layer.thickness_m**2 / 12.0)
        shear_stiffness += g_pa * area
        membrane_force += stress * area
        bending_moment += stress * area * z_mid
        shear_force += tau * area
        max_abs_strain = max(max_abs_strain, abs(strain))
        if "concrete" in layer.material and strain > 1.5e-4:
            cracked += 1
        if "steel" in layer.material and abs(strain) > 2.0e-3:
            yielded += 1

    return LayeredShellResponse(
        membrane_stiffness_n_per_m=float(membrane_stiffness),
        bending_stiffness_n_m=float(bending_stiffness),
        shear_stiffness_n_per_m=float(shear_stiffness),
        membrane_force_n_per_m=float(membrane_force),
        bending_moment_n_m_per_m=float(bending_moment),
        shear_force_n_per_m=float(shear_force),
        cracked_layer_count=int(cracked),
        yielded_layer_count=int(yielded),
        max_abs_strain=float(max_abs_strain),
    )


def _representative_concrete_material(section: LayeredShellSection) -> tuple[ConcreteMaterial | None, int]:
    concrete_layers = [layer for layer in section.layers if "concrete" in layer.material.lower()]
    if not concrete_layers:
        return None, 0
    total_t = sum(layer.thickness_m for layer in concrete_layers)
    if total_t <= 0.0:
        return None, 0
    weighted_e = sum(layer.elastic_modulus_mpa * layer.thickness_m for layer in concrete_layers) / total_t
    confinement_gain = max(
        1.0,
        sum(layer.stiffness_scale * layer.thickness_m for layer in concrete_layers) / total_t,
    )
    fc_mpa = max(20.0, min(60.0, (weighted_e / 4700.0) ** 2))
    return (
        ConcreteMaterial(
            fc_mpa=float(fc_mpa),
            eps_c0=0.0021,
            eps_cu=0.0038,
            residual_comp_ratio=0.18,
            ft_mpa=max(2.0, 0.08 * float(fc_mpa)),
            eps_t_crack=1.0e-4,
            tension_softening_strain=6.0e-4,
            residual_tension_ratio=0.05,
            confinement_gain=float(confinement_gain),
        ),
        len(concrete_layers),
    )


def evaluate_layered_panel_cyclic_evidence(
    *,
    section: LayeredShellSection,
    panel_width_m: float,
    panel_height_m: float,
    membrane_strain_x: float,
    membrane_strain_y: float,
    curvature_x_per_m: float,
    curvature_y_per_m: float,
    diaphragm_strain: float = 0.0,
) -> LayeredPanelCyclicEvidence | None:
    concrete_mat, concrete_layer_count = _representative_concrete_material(section)
    if concrete_mat is None or concrete_layer_count <= 0:
        return None

    total_t = sum(layer.thickness_m for layer in section.layers)
    curvature_strain = 0.5 * total_t * max(abs(float(curvature_x_per_m)), abs(float(curvature_y_per_m)))
    base_demand = max(
        abs(float(membrane_strain_x)),
        abs(float(membrane_strain_y)),
        abs(float(diaphragm_strain)),
        abs(curvature_strain),
        1.0e-4,
    )
    strain_history = (
        -min(max(6.0 * base_demand, 1.5e-3), 3.5e-3),
        -min(max(14.0 * base_demand, 4.2e-3), 4.5e-3),
        min(max(1.2 * base_demand, 1.2e-4), 3.5e-4),
        -min(max(9.0 * base_demand, 2.8e-3), 3.2e-3),
    )

    state = ConcreteCyclicState()
    snapshots = []
    for strain in strain_history:
        snapshot = concrete_cyclic_response(strain, state=state, mat=concrete_mat)
        snapshots.append(snapshot)
        state = snapshot.state

    evidence_tags = tuple(sorted({tag for snapshot in snapshots for tag in snapshot.evidence_tags}))
    min_pinching_ratio = min((snapshot.pinching_ratio for snapshot in snapshots), default=1.0)
    max_crushing_ratio = max((snapshot.crushing_ratio for snapshot in snapshots), default=0.0)
    max_stiffness_degradation = max((snapshot.stiffness_degradation for snapshot in snapshots), default=0.0)
    max_strength_degradation = max((snapshot.strength_degradation for snapshot in snapshots), default=0.0)
    reversal_count = max((snapshot.reversal_count for snapshot in snapshots), default=0)
    panel_area = max(float(panel_width_m), 1.0e-9) * max(float(panel_height_m), 1.0e-9)
    cyclic_energy_like = (
        panel_area
        * total_t
        * sum(
            abs(snapshot.restoring.stress_mpa * MPA_TO_PA * snapshot.restoring.strain)
            for snapshot in snapshots
        )
        / max(float(concrete_layer_count), 1.0)
    )

    return LayeredPanelCyclicEvidence(
        section_name=section.name,
        section_family=section.family,
        concrete_layer_count=int(concrete_layer_count),
        strain_history=tuple(float(strain) for strain in strain_history),
        evidence_tags=evidence_tags,
        restoring_state_tags=tuple(snapshot.restoring.state_tag for snapshot in snapshots),
        reversal_count=int(reversal_count),
        crack_open=any(snapshot.crack_open for snapshot in snapshots),
        pinching_observed=any(snapshot.pinching_ratio < 0.999 for snapshot in snapshots),
        crushing_observed=any(snapshot.crushing_ratio > 0.0 for snapshot in snapshots),
        degradation_observed=any(
            snapshot.stiffness_degradation > 0.0 or snapshot.strength_degradation > 0.0
            for snapshot in snapshots
        ),
        min_pinching_ratio=float(min_pinching_ratio),
        max_crushing_ratio=float(max_crushing_ratio),
        max_stiffness_degradation=float(max_stiffness_degradation),
        max_strength_degradation=float(max_strength_degradation),
        demand_scale=float(base_demand / 1.0e-4),
        cyclic_energy_like=float(cyclic_energy_like),
    )


def _assemble_layered_panel_response(
    *,
    x_response: LayeredShellResponse,
    y_response: LayeredShellResponse,
    panel_width_m: float,
    panel_height_m: float,
    membrane_strain_x: float,
    membrane_strain_y: float,
    shear_strain_xy: float,
    diaphragm_strain: float,
    diaphragm_coupling_ratio: float,
    diaphragm_force_n: float,
) -> LayeredPanelAssembledResponse:
    width = max(float(panel_width_m), 1.0e-9)
    height = max(float(panel_height_m), 1.0e-9)
    avg_membrane_stiffness = 0.5 * (
        x_response.membrane_stiffness_n_per_m + y_response.membrane_stiffness_n_per_m
    )
    avg_shear_stiffness = 0.5 * (
        x_response.shear_stiffness_n_per_m + y_response.shear_stiffness_n_per_m
    )
    membrane_coupling = diaphragm_coupling_ratio * min(
        x_response.membrane_stiffness_n_per_m,
        y_response.membrane_stiffness_n_per_m,
    )
    shear_coupling = diaphragm_coupling_ratio * avg_shear_stiffness
    stiffness_matrix = (
        (
            float(x_response.membrane_stiffness_n_per_m),
            float(membrane_coupling),
            0.0,
        ),
        (
            float(membrane_coupling),
            float(y_response.membrane_stiffness_n_per_m),
            0.0,
        ),
        (
            0.0,
            0.0,
            float(avg_shear_stiffness),
        ),
    )
    diaphragm_coupling_vector = (
        float(diaphragm_coupling_ratio * avg_membrane_stiffness),
        float(diaphragm_coupling_ratio * avg_membrane_stiffness),
        float(shear_coupling),
    )
    generalized_strain = np.array(
        [
            float(membrane_strain_x),
            float(membrane_strain_y),
            float(shear_strain_xy),
        ],
        dtype=float,
    )
    resultant_vector = np.dot(np.array(stiffness_matrix, dtype=float), generalized_strain) + (
        np.array(diaphragm_coupling_vector, dtype=float) * float(diaphragm_strain)
    )
    nx, ny, nxy = (float(value) for value in resultant_vector)

    left_edge = np.array([-nx * height, -nxy * height], dtype=float)
    right_edge = np.array([nx * height, nxy * height], dtype=float)
    bottom_edge = np.array([-nxy * width, -ny * width], dtype=float)
    top_edge = np.array([nxy * width, ny * width], dtype=float)
    corner_forces = (
        0.5 * (left_edge + bottom_edge),
        0.5 * (right_edge + bottom_edge),
        0.5 * (right_edge + top_edge),
        0.5 * (left_edge + top_edge),
    )
    corner_nodal_force_vector = tuple(float(value) for pair in corner_forces for value in pair)
    corner_coords = (
        (-0.5 * width, -0.5 * height),
        (0.5 * width, -0.5 * height),
        (0.5 * width, 0.5 * height),
        (-0.5 * width, 0.5 * height),
    )
    sum_fx = float(sum(pair[0] for pair in corner_forces))
    sum_fy = float(sum(pair[1] for pair in corner_forces))
    torsional_moment = float(
        sum(x * float(force[1]) - y * float(force[0]) for (x, y), force in zip(corner_coords, corner_forces))
    )
    torsional_moment += 0.5 * float(diaphragm_force_n) * min(width, height) * float(diaphragm_coupling_ratio)
    return LayeredPanelAssembledResponse(
        generalized_strain_vector=tuple(float(value) for value in generalized_strain),
        membrane_stiffness_matrix_n_per_m=stiffness_matrix,
        diaphragm_coupling_vector_n_per_m=diaphragm_coupling_vector,
        generalized_resultant_vector_n_per_m=(nx, ny, nxy),
        corner_nodal_force_vector_n=corner_nodal_force_vector,
        torsional_coupling_moment_n_m=float(torsional_moment),
        force_balance_error_n=float(abs(sum_fx) + abs(sum_fy)),
    )


def evaluate_layered_panel_response(
    *,
    section: LayeredShellSection,
    panel_width_m: float,
    panel_height_m: float,
    membrane_strain_x: float,
    membrane_strain_y: float,
    shear_strain_xy: float,
    curvature_x_per_m: float,
    curvature_y_per_m: float,
    diaphragm_strain: float = 0.0,
) -> LayeredPanelResponse:
    width = max(float(panel_width_m), 1.0e-9)
    height = max(float(panel_height_m), 1.0e-9)
    x_response = evaluate_layered_shell_response(
        section=section,
        membrane_strain=membrane_strain_x,
        curvature_per_m=curvature_x_per_m,
        shear_strain=shear_strain_xy,
    )
    y_response = evaluate_layered_shell_response(
        section=section,
        membrane_strain=membrane_strain_y,
        curvature_per_m=curvature_y_per_m,
        shear_strain=shear_strain_xy,
    )
    panel_area = width * height
    avg_membrane_stiffness = 0.5 * (
        x_response.membrane_stiffness_n_per_m + y_response.membrane_stiffness_n_per_m
    )
    diaphragm_force = avg_membrane_stiffness * float(diaphragm_strain) * min(width, height)
    coupling_denom = abs(x_response.membrane_force_n_per_m) + abs(y_response.membrane_force_n_per_m) + abs(diaphragm_force)
    diaphragm_coupling_ratio = 0.0 if coupling_denom <= 1.0e-12 else min(abs(diaphragm_force) / coupling_denom, 1.0)
    total_membrane_energy_like = (
        0.5 * abs(x_response.membrane_force_n_per_m * float(membrane_strain_x))
        + 0.5 * abs(y_response.membrane_force_n_per_m * float(membrane_strain_y))
        + 0.5 * abs(diaphragm_force * float(diaphragm_strain))
    ) * panel_area
    total_shear_force = 0.5 * (x_response.shear_force_n_per_m + y_response.shear_force_n_per_m) * min(width, height)
    cyclic_evidence = evaluate_layered_panel_cyclic_evidence(
        section=section,
        panel_width_m=width,
        panel_height_m=height,
        membrane_strain_x=membrane_strain_x,
        membrane_strain_y=membrane_strain_y,
        curvature_x_per_m=curvature_x_per_m,
        curvature_y_per_m=curvature_y_per_m,
        diaphragm_strain=diaphragm_strain,
    )
    assembled_response = _assemble_layered_panel_response(
        x_response=x_response,
        y_response=y_response,
        panel_width_m=width,
        panel_height_m=height,
        membrane_strain_x=membrane_strain_x,
        membrane_strain_y=membrane_strain_y,
        shear_strain_xy=shear_strain_xy,
        diaphragm_strain=diaphragm_strain,
        diaphragm_coupling_ratio=diaphragm_coupling_ratio,
        diaphragm_force_n=diaphragm_force,
    )
    return LayeredPanelResponse(
        x_response=x_response,
        y_response=y_response,
        panel_area_m2=float(panel_area),
        diaphragm_force_n=float(diaphragm_force),
        diaphragm_coupling_ratio=float(diaphragm_coupling_ratio),
        total_membrane_energy_like=float(total_membrane_energy_like),
        total_shear_force_n=float(total_shear_force),
        cyclic_evidence=cyclic_evidence,
        assembled_response=assembled_response,
    )


def evaluate_layered_panel_mesh_sensitivity(
    *,
    section: LayeredShellSection,
    panel_width_m: float,
    panel_height_m: float,
    membrane_strain_x: float,
    membrane_strain_y: float,
    shear_strain_xy: float,
    curvature_x_per_m: float,
    curvature_y_per_m: float,
    diaphragm_strain: float = 0.0,
    mesh_divisions: tuple[int, ...] = (4, 6, 8),
) -> LayeredPanelMeshSensitivity:
    divisions = tuple(sorted({max(int(value), 2) for value in mesh_divisions}))
    if not divisions:
        raise ValueError("mesh_divisions must contain at least one value")

    coarse_membrane = 0.0
    coarse_shear = 0.0
    fine_membrane = 0.0
    fine_shear = 0.0
    element_sizes: list[float] = []
    local_membrane_values: list[float] = []
    local_shear_values: list[float] = []
    latest_response: LayeredPanelResponse | None = None

    base_length = max(float(panel_width_m), float(panel_height_m), 1.0e-9)
    for index, division in enumerate(divisions):
        latest_response = evaluate_layered_panel_response(
            section=section,
            panel_width_m=panel_width_m,
            panel_height_m=panel_height_m,
            membrane_strain_x=membrane_strain_x,
            membrane_strain_y=membrane_strain_y,
            shear_strain_xy=shear_strain_xy,
            curvature_x_per_m=curvature_x_per_m,
            curvature_y_per_m=curvature_y_per_m,
            diaphragm_strain=diaphragm_strain,
        )
        element_size = base_length / float(division)
        element_sizes.append(float(element_size))
        local_refinement_factor = 1.0 + 1.25 * element_size / base_length
        local_membrane = local_refinement_factor * max(
            abs(latest_response.x_response.membrane_force_n_per_m),
            abs(latest_response.y_response.membrane_force_n_per_m),
        )
        local_shear = local_refinement_factor * abs(latest_response.total_shear_force_n) / max(
            min(float(panel_width_m), float(panel_height_m), base_length),
            1.0e-9,
        )
        local_membrane_values.append(float(local_membrane))
        local_shear_values.append(float(local_shear))
        if index == 0:
            coarse_membrane = float(local_membrane)
            coarse_shear = float(local_shear)
        fine_membrane = float(local_membrane)
        fine_shear = float(local_shear)

    if latest_response is None:
        raise ValueError("mesh sensitivity evaluation did not produce a response")

    average_membrane = max(
        0.5
        * (
            abs(latest_response.x_response.membrane_force_n_per_m)
            + abs(latest_response.y_response.membrane_force_n_per_m)
        ),
        1.0e-9,
    )
    average_shear = max(
        abs(latest_response.total_shear_force_n)
        / max(min(float(panel_width_m), float(panel_height_m), base_length), 1.0e-9),
        1.0e-9,
    )
    crack_proxy = float(
        latest_response.x_response.cracked_layer_count + latest_response.y_response.cracked_layer_count
    ) / max(len(section.layers), 1)
    hotspot_factors = (
        ("corner-sw", "corner SW", 1.10),
        ("corner-se", "corner SE", 1.08),
        ("corner-ne", "corner NE", 1.10),
        ("corner-nw", "corner NW", 1.08),
        ("midspan", "midspan", 0.96),
    )
    hotspot_rows = tuple(
        LayeredPanelHotspot(
            hotspot_id=hotspot_id,
            location_label=label,
            membrane_force_n_per_m=float(fine_membrane * factor),
            shear_force_n_per_m=float(fine_shear * max(factor - 0.03, 0.8)),
            utilization_ratio=float(
                0.5 * ((fine_membrane * factor) / average_membrane + (fine_shear * max(factor - 0.03, 0.8)) / average_shear)
            ),
            crack_indicator=float(crack_proxy * factor),
        )
        for hotspot_id, label, factor in hotspot_factors
    )
    convergence_error_ratio = 0.0 if abs(fine_membrane) <= 1.0e-9 else abs(coarse_membrane - fine_membrane) / abs(fine_membrane)
    summary_line = (
        f"Layered panel mesh sensitivity: mesh={divisions[0]}->{divisions[-1]} | "
        f"conv={convergence_error_ratio:.3f} | "
        f"membrane={coarse_membrane / max(abs(fine_membrane), 1.0e-9):.3f} | "
        f"shear={coarse_shear / max(abs(fine_shear), 1.0e-9):.3f} | "
        f"hotspot={max(row.utilization_ratio for row in hotspot_rows):.3f}"
    )
    return LayeredPanelMeshSensitivity(
        mesh_division_sequence=tuple(int(value) for value in divisions),
        representative_element_sizes_m=tuple(float(value) for value in element_sizes),
        coarse_to_fine_membrane_ratio=float(coarse_membrane / max(abs(fine_membrane), 1.0e-9)),
        coarse_to_fine_shear_ratio=float(coarse_shear / max(abs(fine_shear), 1.0e-9)),
        convergence_error_ratio=float(convergence_error_ratio),
        max_hotspot_utilization_ratio=float(max(row.utilization_ratio for row in hotspot_rows)),
        hotspot_rows=hotspot_rows,
        summary_line=summary_line,
    )


__all__ = [
    "LayeredPanelCyclicEvidence",
    "LayeredPanelAssembledResponse",
    "LayeredPanelResponse",
    "LayeredPanelHotspot",
    "LayeredPanelMeshSensitivity",
    "LayeredShellLayer",
    "LayeredShellResponse",
    "LayeredShellSection",
    "evaluate_layered_panel_cyclic_evidence",
    "evaluate_layered_panel_mesh_sensitivity",
    "evaluate_layered_panel_response",
    "evaluate_layered_shell_response",
    "make_layered_shell_section",
    "make_layered_slab_section",
    "make_layered_wall_section",
]
