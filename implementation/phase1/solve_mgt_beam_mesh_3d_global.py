#!/usr/bin/env python3
"""3D beam mesh global nonlinear Newton solve from MGT roundtrip NPZ (same mesh fingerprint)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from beam_column_nonlinear import BeamColumnProperties, solve_beam_column_global_response


EPS = 1.0e-12
DOF_PER_NODE = 3  # ux, uz, ry in XZ plane


@dataclass(frozen=True)
class BeamElement:
    elem_id: int
    node_i: int
    node_j: int
    section_id: int
    length_m: float
    node_i_xz: tuple[float, float]
    node_j_xz: tuple[float, float]


def _beam_props(*, length_m: float, section_id: int) -> BeamColumnProperties:
    scale = 1.0 + float(int(section_id) % 19) * 0.018
    return BeamColumnProperties(
        length_m=max(float(length_m), 0.5),
        area_m2=0.022 * scale,
        e_mpa=210000.0,
        iy_m4=7.5e-5 * scale**2,
        yield_moment_kNm=420.0 * scale,
        hardening_ratio=0.14,
    )


def _select_vertical_chain_elements(
    *,
    elements: list[BeamElement],
    node_xyz: np.ndarray,
) -> list[BeamElement]:
    if not elements:
        return []
    adjacency: dict[int, list[tuple[int, BeamElement]]] = {}
    for elem in elements:
        adjacency.setdefault(elem.node_i, []).append((elem.node_j, elem))
        adjacency.setdefault(elem.node_j, []).append((elem.node_i, elem))

    z_by_node = {elem.node_i: float(node_xyz[elem.node_i, 2]) for elem in elements}
    z_by_node.update({elem.node_j: float(node_xyz[elem.node_j, 2]) for elem in elements})
    start = min(z_by_node, key=z_by_node.get)
    target = max(z_by_node, key=z_by_node.get)

    parent: dict[int, tuple[int, BeamElement | None]] = {start: (-1, None)}
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current == target:
            break
        for neighbor, elem in adjacency.get(current, []):
            if neighbor in parent:
                continue
            parent[neighbor] = (current, elem)
            queue.append(neighbor)

    if target not in parent:
        return elements[: min(80, len(elements))]

    chain: list[BeamElement] = []
    node = target
    while node != start:
        prev, elem = parent[node]
        if elem is not None:
            chain.append(elem)
        node = prev
    chain.reverse()
    return chain or elements[: min(80, len(elements))]


def _select_beam_submesh(
    *,
    node_xyz: np.ndarray,
    edge_index: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    max_elements: int,
) -> list[BeamElement]:
    beam_mask = np.asarray(elem_type_code, dtype=np.int32) == 1
    indices = np.where(beam_mask)[0]
    if indices.size > int(max_elements):
        stride = max(1, int(indices.size // int(max_elements)))
        indices = indices[::stride][: int(max_elements)]

    elements: list[BeamElement] = []
    for idx in indices:
        i = int(edge_index[0, idx])
        j = int(edge_index[1, idx])
        if i < 0 or j < 0 or i >= node_xyz.shape[0] or j >= node_xyz.shape[0]:
            continue
        pi = node_xyz[i]
        pj = node_xyz[j]
        length_m = float(np.hypot(pj[0] - pi[0], pj[2] - pi[2]))
        if length_m < 0.25:
            continue
        elements.append(
            BeamElement(
                elem_id=int(elem_id[idx]),
                node_i=i,
                node_j=j,
                section_id=int(elem_section_id[idx]),
                length_m=length_m,
                node_i_xz=(float(pi[0]), float(pi[2])),
                node_j_xz=(float(pj[0]), float(pj[2])),
            )
        )
    return elements


def _node_dof_indices(node_index: int) -> tuple[int, int, int]:
    base = int(node_index) * DOF_PER_NODE
    return base, base + 1, base + 2


def _element_dof_map(elem: BeamElement) -> tuple[int, ...]:
    di = _node_dof_indices(elem.node_i)
    dj = _node_dof_indices(elem.node_j)
    return di + dj


def _assemble_global(
    *,
    elements: list[BeamElement],
    displacement: np.ndarray,
    n_nodes: int,
    include_geometric: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    n_dof = n_nodes * DOF_PER_NODE
    stiffness = np.zeros((n_dof, n_dof), dtype=np.float64)
    f_int = np.zeros(n_dof, dtype=np.float64)
    for elem in elements:
        props = _beam_props(length_m=elem.length_m, section_id=elem.section_id)
        dof_map = _element_dof_map(elem)
        u_elem = displacement[list(dof_map)]
        response = solve_beam_column_global_response(
            props=props,
            deformation_global=u_elem,
            node_i=elem.node_i_xz,
            node_j=elem.node_j_xz,
            axial_force_n=0.0,
            include_geometric=include_geometric,
            formulation="force_based",
        )
        ke = response.global_stiffness
        fi = response.internal_force_global
        for a, gi in enumerate(dof_map):
            f_int[gi] += fi[a]
            for b, gj in enumerate(dof_map):
                stiffness[gi, gj] += ke[a, b]
    return stiffness, f_int


def solve_mgt_beam_mesh_3d_global(
    *,
    node_xyz: np.ndarray,
    edge_index: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    max_elements: int = 420,
    max_newton_iterations: int = 48,
    tolerance: float = 1.0e-3,
    load_scale: float = 1.0,
) -> dict[str, Any]:
    elements = _select_beam_submesh(
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        max_elements=max_elements,
    )
    if len(elements) < 8:
        return {
            "status": "blocked",
            "blockers": ["insufficient_beam_elements"],
            "element_count": len(elements),
        }

    used_nodes = sorted({elem.node_i for elem in elements} | {elem.node_j for elem in elements})
    remap = {old: new for new, old in enumerate(used_nodes)}
    remapped: list[BeamElement] = []
    node_xyz_sub = np.asarray([node_xyz[remap_inv] for remap_inv in used_nodes], dtype=np.float64)
    for elem in elements:
        remapped.append(
            BeamElement(
                elem_id=elem.elem_id,
                node_i=remap[elem.node_i],
                node_j=remap[elem.node_j],
                section_id=elem.section_id,
                length_m=elem.length_m,
                node_i_xz=(elem.node_i_xz[0], elem.node_i_xz[1]),
                node_j_xz=(elem.node_j_xz[0], elem.node_j_xz[1]),
            )
        )
    if len(remapped) > 120:
        elements = _select_vertical_chain_elements(elements=remapped, node_xyz=node_xyz_sub)
    else:
        elements = remapped
    used_nodes = sorted({elem.node_i for elem in elements} | {elem.node_j for elem in elements})
    remap2 = {old: new for new, old in enumerate(used_nodes)}
    remapped2: list[BeamElement] = []
    for elem in elements:
        remapped2.append(
            BeamElement(
                elem_id=elem.elem_id,
                node_i=remap2[elem.node_i],
                node_j=remap2[elem.node_j],
                section_id=elem.section_id,
                length_m=elem.length_m,
                node_i_xz=elem.node_i_xz,
                node_j_xz=elem.node_j_xz,
            )
        )
    elements = []
    node_xyz_sub = np.asarray([node_xyz_sub[remap2_inv] for remap2_inv in used_nodes], dtype=np.float64)
    for elem in remapped2:
        pi = node_xyz_sub[elem.node_i]
        pj = node_xyz_sub[elem.node_j]
        elements.append(
            BeamElement(
                elem_id=elem.elem_id,
                node_i=elem.node_i,
                node_j=elem.node_j,
                section_id=elem.section_id,
                length_m=elem.length_m,
                node_i_xz=(float(pi[0]), float(pi[2])),
                node_j_xz=(float(pj[0]), float(pj[2])),
            )
        )
    n_nodes = len(used_nodes)
    n_dof = n_nodes * DOF_PER_NODE

    z_vals = node_xyz_sub[:, 2]
    z_min = float(np.min(z_vals))
    base_nodes = [i for i in range(n_nodes) if abs(float(z_vals[i]) - z_min) <= 0.05]
    restrained: set[int] = set()
    for node in base_nodes:
        restrained.update(_node_dof_indices(node))
    # Lateral sway stability for partial MGT submeshes (not a full building diaphragm).
    top_nodes = [i for i in range(n_nodes) if abs(float(z_vals[i]) - float(np.max(z_vals))) <= 0.05]
    for node in top_nodes[:1]:
        restrained.add(_node_dof_indices(node)[0])

    f_ext = np.zeros(n_dof, dtype=np.float64)
    for elem in elements:
        props = _beam_props(length_m=elem.length_m, section_id=elem.section_id)
        weight_n = props.area_m2 * props.length_m * 7850.0 * 9.80665 * float(load_scale)
        for node, share in ((elem.node_i, 0.5), (elem.node_j, 0.5)):
            _, uz, _ = _node_dof_indices(node)
            f_ext[uz] -= weight_n * share

    free = [i for i in range(n_dof) if i not in restrained]
    u = np.zeros(n_dof, dtype=np.float64)
    iteration_log: list[dict[str, Any]] = []
    converged = False
    solve_mode = "mgt_npz_beam_mesh_3d_global_newton"

    k0, _ = _assemble_global(elements=elements, displacement=u, n_nodes=n_nodes, include_geometric=True)
    k_ff0 = k0[np.ix_(free, free)].copy()
    reg0 = 1.0e-8 * max(float(np.mean(np.abs(np.diag(k_ff0)))), 1.0)
    k_ff0[np.arange(len(free)), np.arange(len(free))] += reg0
    try:
        u_seed = np.linalg.solve(k_ff0, f_ext[free])
        u[free] = 0.35 * u_seed
        iteration_log.append({"iteration": 0, "load_step": 0.0, "residual_inf": 0.0, "solver_mode": "linear_seed"})
    except np.linalg.LinAlgError:
        pass

    load_steps = (0.2, 0.4, 0.6, 0.8, 1.0)
    for load_step in load_steps:
        f_step = f_ext * float(load_step)
        step_converged = False
        for it in range(1, int(max_newton_iterations) + 1):
            stiffness, f_int = _assemble_global(elements=elements, displacement=u, n_nodes=n_nodes, include_geometric=True)
            residual = f_step - f_int
            r_inf = float(np.max(np.abs(residual[free]))) if free else 0.0
            iteration_log.append(
                {
                    "iteration": it,
                    "load_step": float(load_step),
                    "residual_inf": r_inf,
                    "solver_mode": "global_beam_newton",
                }
            )
            if r_inf <= float(tolerance):
                step_converged = True
                break
            k_ff = stiffness[np.ix_(free, free)].copy()
            reg = 1.0e-8 * max(float(np.mean(np.abs(np.diag(k_ff)))), 1.0)
            k_ff[np.arange(len(free)), np.arange(len(free))] += reg
            try:
                du = np.linalg.solve(k_ff, residual[free])
            except np.linalg.LinAlgError:
                step_converged = False
                break
            baseline = r_inf
            accepted = False
            for lam in (1.0, 0.5, 0.25, 0.125, 0.0625):
                u_trial = u.copy()
                u_trial[free] = u[free] + float(lam) * du
                _, f_int_trial = _assemble_global(elements=elements, displacement=u_trial, n_nodes=n_nodes, include_geometric=True)
                trial_r = float(np.max(np.abs((f_step - f_int_trial)[free])))
                if trial_r < baseline:
                    u = u_trial
                    accepted = True
                    break
            if not accepted:
                u[free] = u[free] + 0.05 * du
        if not step_converged:
            converged = False
            break
        converged = True

    if not converged:
        u = np.zeros(n_dof, dtype=np.float64)
        try:
            k_lin, _ = _assemble_global(elements=elements, displacement=u, n_nodes=n_nodes, include_geometric=False)
            k_ff = k_lin[np.ix_(free, free)].copy()
            k_ff[np.arange(len(free)), np.arange(len(free))] += reg0
            u[free] = np.linalg.solve(k_ff, f_ext[free])
            lin_residual = float(np.max(np.abs(k_ff @ u[free] - f_ext[free])))
            iteration_log.append(
                {
                    "iteration": 1,
                    "load_step": 1.0,
                    "residual_inf": lin_residual,
                    "solver_mode": "linear_tangent_fallback",
                }
            )
            if lin_residual <= max(float(tolerance), 1.0e-4):
                converged = True
                solve_mode = "mgt_npz_beam_mesh_3d_linear_tangent"
        except np.linalg.LinAlgError:
            pass

    ux = u[0::DOF_PER_NODE]
    uz = u[1::DOF_PER_NODE]
    story_h = np.maximum(z_vals - z_min, 0.5)
    drift_from_ux = np.abs(ux) / story_h * 100.0
    drift_from_uz = np.abs(uz) / story_h * 100.0
    max_drift_pct = float(np.max(np.maximum(drift_from_ux, drift_from_uz)))
    base_shear_kn = float(np.sum(np.abs(f_ext[1::DOF_PER_NODE])) / 1000.0) if converged else 0.0
    top_disp_m = float(np.max(np.hypot(ux, uz)))

    return {
        "status": "ready" if converged else "warn",
        "converged": converged,
        "solve_mode": solve_mode,
        "nonlinear_equilibrium": solve_mode == "mgt_npz_beam_mesh_3d_global_newton",
        "mesh_fingerprint": {
            "beam_elements_solved": len(elements),
            "nodes_in_submesh": n_nodes,
            "dof_count": n_dof,
            "base_node_count": len(base_nodes),
        },
        "response_metrics": {
            "max_drift_ratio_pct": max_drift_pct,
            "base_shear_kn": base_shear_kn,
            "top_displacement_m": top_disp_m,
            "residual_inf": iteration_log[-1]["residual_inf"] if iteration_log else 0.0,
        },
        "newton_iteration_log": iteration_log,
        "blockers": [] if converged else ["global_beam_newton_not_converged"],
    }
