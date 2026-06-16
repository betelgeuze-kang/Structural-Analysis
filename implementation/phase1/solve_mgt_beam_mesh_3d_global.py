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
    material_id: int = 0
    length_m: float = 0.0
    node_i_xz: tuple[float, float] = (0.0, 0.0)
    node_j_xz: tuple[float, float] = (0.0, 0.0)


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


def _real_beam_props(
    *,
    length_m: float,
    section_id: int,
    material_id: int,
    section_props: dict[int, dict[str, Any]] | None,
    material_props: dict[int, dict[str, Any]] | None,
) -> tuple[BeamColumnProperties, bool]:
    representative = _beam_props(length_m=length_m, section_id=section_id)
    if not section_props or not material_props:
        return representative, False
    sec = section_props.get(int(section_id))
    mat = material_props.get(int(material_id))
    if sec is None or mat is None:
        return representative, False
    return (
        BeamColumnProperties(
            length_m=representative.length_m,
            area_m2=float(sec["A_m2"]),
            e_mpa=float(mat["E_kN_per_m2"]) / 1000.0,
            iy_m4=float(min(sec["Iy_m4"], sec["Iz_m4"])),
            yield_moment_kNm=representative.yield_moment_kNm,
            hardening_ratio=representative.hardening_ratio,
        ),
        True,
    )


def _element_beam_props(
    elem: BeamElement,
    *,
    section_props: dict[int, dict[str, Any]] | None,
    material_props: dict[int, dict[str, Any]] | None,
) -> tuple[BeamColumnProperties, bool]:
    if section_props is not None and material_props is not None:
        return _real_beam_props(
            length_m=elem.length_m,
            section_id=elem.section_id,
            material_id=elem.material_id,
            section_props=section_props,
            material_props=material_props,
        )
    return _beam_props(length_m=elem.length_m, section_id=elem.section_id), False


def _real_section_property_coverage_pct(
    elements: list[BeamElement],
    *,
    section_props: dict[int, dict[str, Any]] | None,
    material_props: dict[int, dict[str, Any]] | None,
) -> float:
    if not elements or section_props is None or material_props is None:
        return 0.0
    real_count = 0
    for elem in elements:
        _, used_real = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        if used_real:
            real_count += 1
    return 100.0 * float(real_count) / float(len(elements))


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

    visited: set[int] = set()
    components: list[list[BeamElement]] = []
    for start in sorted(adjacency):
        if start in visited:
            continue
        queue = [start]
        visited.add(start)
        component_nodes: set[int] = set()
        component_edges: dict[int, BeamElement] = {}
        while queue:
            current = queue.pop(0)
            component_nodes.add(current)
            for neighbor, elem in adjacency.get(current, []):
                component_edges[elem.elem_id] = elem
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if component_edges:
            components.append(list(component_edges.values()))

    candidate_elements = elements
    if components:
        def component_score(component: list[BeamElement]) -> tuple[float, int]:
            nodes = {elem.node_i for elem in component} | {elem.node_j for elem in component}
            z_vals = [float(node_xyz[node, 2]) for node in nodes if 0 <= node < node_xyz.shape[0]]
            z_span = max(z_vals) - min(z_vals) if z_vals else 0.0
            return z_span, len(component)

        candidate_elements = max(components, key=component_score)
        if len(candidate_elements) <= 80:
            return candidate_elements

    z_by_node = {elem.node_i: float(node_xyz[elem.node_i, 2]) for elem in candidate_elements}
    z_by_node.update({elem.node_j: float(node_xyz[elem.node_j, 2]) for elem in candidate_elements})
    start = min(z_by_node, key=z_by_node.get)
    target = max(z_by_node, key=z_by_node.get)
    candidate_ids = {elem.elem_id for elem in candidate_elements}

    parent: dict[int, tuple[int, BeamElement | None]] = {start: (-1, None)}
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current == target:
            break
        for neighbor, elem in adjacency.get(current, []):
            if elem.elem_id not in candidate_ids:
                continue
            if neighbor in parent:
                continue
            parent[neighbor] = (current, elem)
            queue.append(neighbor)

    if target not in parent:
        return candidate_elements[: min(80, len(candidate_elements))]

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
    elem_material_id: np.ndarray | None = None,
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
        mat_id = 0
        if elem_material_id is not None and idx < elem_material_id.shape[0]:
            mat_id = int(elem_material_id[idx])
        elements.append(
            BeamElement(
                elem_id=int(elem_id[idx]),
                node_i=i,
                node_j=j,
                section_id=int(elem_section_id[idx]),
                material_id=mat_id,
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


def _condition_number_threshold(diag: np.ndarray, *, ratio_limit: float = 1.0e8) -> bool:
    d = np.abs(np.asarray(diag, dtype=np.float64))
    d = d[d > EPS]
    if d.size == 0:
        return False
    return float(np.max(d) / max(float(np.min(d)), EPS)) > float(ratio_limit)


def _solve_newton_increment(
    k_ff: np.ndarray,
    residual_free: np.ndarray,
    *,
    use_jacobi_scaling: bool,
) -> np.ndarray:
    if not use_jacobi_scaling or not _condition_number_threshold(np.diag(k_ff)):
        return np.linalg.solve(k_ff, residual_free)
    d = np.sqrt(np.maximum(np.abs(np.diag(k_ff)), EPS))
    k_scaled = (k_ff / d[:, None]) / d[None, :]
    r_scaled = residual_free / d
    du_scaled = np.linalg.solve(k_scaled, r_scaled)
    return du_scaled / d


def _elastic_predictor_displacement(
    *,
    elements: list[BeamElement],
    n_nodes: int,
    free: list[int],
    f_step: np.ndarray,
    u_prev: np.ndarray,
    asm_kw: dict[str, Any],
) -> np.ndarray:
    u_pred = u_prev.copy()
    k_prev, f_int_prev = _assemble_global(
        elements=elements,
        displacement=u_prev,
        n_nodes=n_nodes,
        include_geometric=False,
        **asm_kw,
    )
    k_ff = k_prev[np.ix_(free, free)].copy()
    reg = 1.0e-8 * max(float(np.mean(np.abs(np.diag(k_ff)))), 1.0)
    k_ff[np.arange(len(free)), np.arange(len(free))] += reg
    rhs = f_step[free] - f_int_prev[free]
    try:
        u_pred[free] = u_prev[free] + np.linalg.solve(k_ff, rhs)
    except np.linalg.LinAlgError:
        pass
    return u_pred


def _backtracking_line_search(
    *,
    u: np.ndarray,
    free: list[int],
    du: np.ndarray,
    f_step: np.ndarray,
    elements: list[BeamElement],
    n_nodes: int,
    baseline: float,
    asm_kw: dict[str, Any],
    max_trials: int = 8,
    armijo_c: float = 1.0e-4,
) -> tuple[np.ndarray, bool]:
    lam = 1.0
    best_u = u.copy()
    best_r = baseline
    for _ in range(int(max_trials)):
        u_trial = u.copy()
        u_trial[free] = u[free] + lam * du
        _, f_int_trial = _assemble_global(
            elements=elements,
            displacement=u_trial,
            n_nodes=n_nodes,
            include_geometric=True,
            **asm_kw,
        )
        trial_r = float(np.max(np.abs((f_step - f_int_trial)[free])))
        if trial_r < best_r:
            best_r = trial_r
            best_u = u_trial
        armijo_ok = trial_r <= baseline * (1.0 - armijo_c * lam)
        if trial_r < baseline or armijo_ok:
            return u_trial, True
        lam *= 0.5
    if best_r < baseline:
        return best_u, True
    u_fallback = u.copy()
    u_fallback[free] = u[free] + 0.05 * du
    _, f_int_fb = _assemble_global(
        elements=elements,
        displacement=u_fallback,
        n_nodes=n_nodes,
        include_geometric=True,
        **asm_kw,
    )
    fb_r = float(np.max(np.abs((f_step - f_int_fb)[free])))
    if fb_r < baseline:
        return u_fallback, False
    if best_r < fb_r:
        return best_u, False
    return u_fallback, False


def _estimate_gravity_axial_forces(
    elements: list[BeamElement],
    *,
    section_props: dict[int, dict[str, Any]] | None,
    material_props: dict[int, dict[str, Any]] | None,
    load_scale: float,
) -> dict[int, float]:
    """Estimate member compression from tributary self-weight (for P-Delta geometric stiffness)."""
    if not elements:
        return {}
    node_z: dict[int, float] = {}
    for elem in elements:
        node_z[elem.node_i] = elem.node_i_xz[1]
        node_z[elem.node_j] = elem.node_j_xz[1]
    elem_weight: dict[int, float] = {}
    for elem in elements:
        props, _ = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        elem_weight[elem.elem_id] = (
            props.area_m2 * props.length_m * 7850.0 * 9.80665 * float(load_scale)
        )
    sorted_elems = sorted(
        elements,
        key=lambda e: 0.5 * (node_z.get(e.node_i, 0.0) + node_z.get(e.node_j, 0.0)),
        reverse=True,
    )
    axial: dict[int, float] = {}
    weight_above = 0.0
    for elem in sorted_elems:
        axial[elem.elem_id] = max(weight_above, 0.0)
        weight_above += elem_weight.get(elem.elem_id, 0.0)
    return axial


def _assemble_global(
    *,
    elements: list[BeamElement],
    displacement: np.ndarray,
    n_nodes: int,
    include_geometric: bool = True,
    section_props: dict[int, dict[str, Any]] | None = None,
    material_props: dict[int, dict[str, Any]] | None = None,
    element_axial_forces: dict[int, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    n_dof = n_nodes * DOF_PER_NODE
    stiffness = np.zeros((n_dof, n_dof), dtype=np.float64)
    f_int = np.zeros(n_dof, dtype=np.float64)
    for elem in elements:
        props, _ = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        dof_map = _element_dof_map(elem)
        u_elem = displacement[list(dof_map)]
        axial_n = 0.0
        if include_geometric and element_axial_forces is not None:
            axial_n = float(element_axial_forces.get(elem.elem_id, 0.0))
        response = solve_beam_column_global_response(
            props=props,
            deformation_global=u_elem,
            node_i=elem.node_i_xz,
            node_j=elem.node_j_xz,
            axial_force_n=axial_n,
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
    elem_material_id: np.ndarray | None = None,
    section_props: dict[int, dict[str, Any]] | None = None,
    material_props: dict[int, dict[str, Any]] | None = None,
    max_elements: int = 420,
    max_newton_iterations: int = 48,
    tolerance: float = 1.0e-3,
    load_scale: float = 1.0,
    lateral_load_scale: float = 0.0,
    use_improved_newton: bool = True,
) -> dict[str, Any]:
    elements = _select_beam_submesh(
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        max_elements=max_elements,
    )
    raw_beam_element_count = len(elements)
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
                material_id=elem.material_id,
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
                material_id=elem.material_id,
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
                material_id=elem.material_id,
                length_m=elem.length_m,
                node_i_xz=(float(pi[0]), float(pi[2])),
                node_j_xz=(float(pj[0]), float(pj[2])),
            )
        )
    n_nodes = len(used_nodes)
    partial_connected_component_mesh = raw_beam_element_count >= 8 and len(elements) < 8
    real_coverage_pct = _real_section_property_coverage_pct(
        elements,
        section_props=section_props,
        material_props=material_props,
    )
    used_real_section_properties = real_coverage_pct > 0.0
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
    total_gravity_n = 0.0
    for elem in elements:
        props, _ = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        weight_n = props.area_m2 * props.length_m * 7850.0 * 9.80665 * float(load_scale)
        total_gravity_n += weight_n
        for node, share in ((elem.node_i, 0.5), (elem.node_j, 0.5)):
            _, uz, _ = _node_dof_indices(node)
            f_ext[uz] -= weight_n * share

    lateral_scale = max(float(lateral_load_scale), 0.0)
    if lateral_scale > 0.0 and top_nodes:
        lateral_total_n = lateral_scale * total_gravity_n
        share = lateral_total_n / float(len(top_nodes))
        for node in top_nodes:
            ux, _, _ = _node_dof_indices(node)
            f_ext[ux] += share

    free = [i for i in range(n_dof) if i not in restrained]
    u = np.zeros(n_dof, dtype=np.float64)
    iteration_log: list[dict[str, Any]] = []
    converged = False
    solve_mode = "mgt_npz_beam_mesh_3d_global_newton"
    newton_converged_at_load_step: float | None = None
    newton_iterations_total = 0
    fell_back_to_linear_tangent = False

    asm_kw: dict[str, Any] = {
        "section_props": section_props,
        "material_props": material_props,
    }
    if use_improved_newton and lateral_scale > 0.0:
        asm_kw["element_axial_forces"] = _estimate_gravity_axial_forces(
            elements,
            section_props=section_props,
            material_props=material_props,
            load_scale=float(load_scale),
        )
    u_zero = np.zeros(n_dof, dtype=np.float64)
    k_lin0, _ = _assemble_global(
        elements=elements, displacement=u_zero, n_nodes=n_nodes, include_geometric=False, **asm_kw
    )
    k_ff_lin0 = k_lin0[np.ix_(free, free)].copy()
    reg0 = 1.0e-8 * max(float(np.mean(np.abs(np.diag(k_ff_lin0)))), 1.0)

    if not use_improved_newton:
        k0, _ = _assemble_global(
            elements=elements, displacement=u, n_nodes=n_nodes, include_geometric=True, **asm_kw
        )
        k_ff0 = k0[np.ix_(free, free)].copy()
        k_ff0[np.arange(len(free)), np.arange(len(free))] += reg0
        try:
            u_seed = np.linalg.solve(k_ff0, f_ext[free])
            u[free] = 0.35 * u_seed
            iteration_log.append({"iteration": 0, "load_step": 0.0, "residual_inf": 0.0, "solver_mode": "linear_seed"})
        except np.linalg.LinAlgError:
            pass

    load_steps = (
        (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.65, 0.8, 1.0)
        if use_improved_newton
        else (0.2, 0.4, 0.6, 0.8, 1.0)
    )
    for load_step in load_steps:
        f_step = f_ext * float(load_step)
        if use_improved_newton:
            u = _elastic_predictor_displacement(
                elements=elements,
                n_nodes=n_nodes,
                free=free,
                f_step=f_step,
                u_prev=u,
                asm_kw=asm_kw,
            )
            iteration_log.append(
                {
                    "iteration": 0,
                    "load_step": float(load_step),
                    "residual_inf": 0.0,
                    "solver_mode": "elastic_predictor",
                }
            )
        step_converged = False
        prev_r_inf: float | None = None
        stall_count = 0
        for it in range(1, int(max_newton_iterations) + 1):
            stiffness, f_int = _assemble_global(
                elements=elements, displacement=u, n_nodes=n_nodes, include_geometric=True, **asm_kw
            )
            residual = f_step - f_int
            r_inf = float(np.max(np.abs(residual[free]))) if free else 0.0
            newton_iterations_total += 1
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
                newton_converged_at_load_step = float(load_step)
                break
            if (
                prev_r_inf is not None
                and abs(r_inf - prev_r_inf) <= max(1.0e-12, 1.0e-9 * max(prev_r_inf, 1.0))
            ):
                stall_count += 1
            else:
                stall_count = 0
            prev_r_inf = r_inf
            if use_improved_newton and stall_count >= 2:
                stiffness, _ = _assemble_global(
                    elements=elements,
                    displacement=u,
                    n_nodes=n_nodes,
                    include_geometric=False,
                    **asm_kw,
                )
            k_ff = stiffness[np.ix_(free, free)].copy()
            reg = 1.0e-8 * max(float(np.mean(np.abs(np.diag(k_ff)))), 1.0)
            k_ff[np.arange(len(free)), np.arange(len(free))] += reg
            try:
                du = _solve_newton_increment(
                    k_ff,
                    residual[free],
                    use_jacobi_scaling=use_improved_newton,
                )
            except np.linalg.LinAlgError:
                step_converged = False
                break
            if use_improved_newton:
                u, accepted = _backtracking_line_search(
                    u=u,
                    free=free,
                    du=du,
                    f_step=f_step,
                    elements=elements,
                    n_nodes=n_nodes,
                    baseline=r_inf,
                    asm_kw=asm_kw,
                    max_trials=8,
                )
                if accepted:
                    stall_count = 0
            else:
                baseline = r_inf
                accepted = False
                for lam in (1.0, 0.5, 0.25, 0.125, 0.0625):
                    u_trial = u.copy()
                    u_trial[free] = u[free] + float(lam) * du
                    _, f_int_trial = _assemble_global(
                        elements=elements, displacement=u_trial, n_nodes=n_nodes, include_geometric=True, **asm_kw
                    )
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
        fell_back_to_linear_tangent = True
        u = np.zeros(n_dof, dtype=np.float64)
        try:
            k_lin, _ = _assemble_global(
                elements=elements, displacement=u, n_nodes=n_nodes, include_geometric=False, **asm_kw
            )
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
                solve_mode = (
                    "mgt_npz_beam_mesh_3d_real_section_linear_tangent"
                    if used_real_section_properties
                    else "mgt_npz_beam_mesh_3d_linear_tangent"
                )
        except np.linalg.LinAlgError:
            pass

    if converged and solve_mode == "mgt_npz_beam_mesh_3d_global_newton":
        if used_real_section_properties and partial_connected_component_mesh:
            solve_mode = "mgt_npz_beam_mesh_3d_real_section_connected_component"
        elif used_real_section_properties:
            solve_mode = "mgt_npz_beam_mesh_3d_real_section"
        elif partial_connected_component_mesh:
            solve_mode = "mgt_npz_beam_mesh_3d_global_connected_component"

    ux = u[0::DOF_PER_NODE]
    uz = u[1::DOF_PER_NODE]
    story_h = np.maximum(z_vals - z_min, 0.5)
    drift_from_ux = np.abs(ux) / story_h * 100.0
    drift_from_uz = np.abs(uz) / story_h * 100.0
    max_drift_pct = float(np.max(np.maximum(drift_from_ux, drift_from_uz)))
    base_shear_kn = float(np.sum(np.abs(f_ext[1::DOF_PER_NODE])) / 1000.0) if converged else 0.0
    top_disp_m = float(np.max(np.hypot(ux, uz)))
    representative_component_nonlinear_equilibrium = bool(
        converged
        and solve_mode
        in {
            "mgt_npz_beam_mesh_3d_global_newton",
            "mgt_npz_beam_mesh_3d_real_section",
            "mgt_npz_beam_mesh_3d_global_connected_component",
            "mgt_npz_beam_mesh_3d_real_section_connected_component",
        }
    )
    nonlinear_equilibrium = bool(
        representative_component_nonlinear_equilibrium and not partial_connected_component_mesh
    )

    return {
        "status": "warn" if converged and partial_connected_component_mesh else ("ready" if converged else "warn"),
        "converged": converged,
        "solve_mode": solve_mode,
        "nonlinear_equilibrium": nonlinear_equilibrium,
        "representative_component_nonlinear_equilibrium": representative_component_nonlinear_equilibrium,
        "used_real_section_properties": used_real_section_properties,
        "real_section_property_coverage_pct": real_coverage_pct,
        "partial_connected_component_mesh": partial_connected_component_mesh,
        "use_improved_newton": bool(use_improved_newton),
        "lateral_load_scale": lateral_scale,
        "newton_converged_at_load_step": newton_converged_at_load_step,
        "newton_iterations_total": int(newton_iterations_total),
        "fell_back_to_linear_tangent": bool(fell_back_to_linear_tangent),
        "mesh_fingerprint": {
            "raw_beam_elements_available": raw_beam_element_count,
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
        "limitations": ["partial_connected_component_mesh"] if partial_connected_component_mesh else [],
        "blockers": [] if converged else ["global_beam_newton_not_converged"],
    }
