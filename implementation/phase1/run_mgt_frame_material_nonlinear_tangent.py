#!/usr/bin/env python3
"""Build bounded MGT frame material nonlinear tangent evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DEFAULT_ROUNDTRIP,
    DOF_PER_NODE,
    PRODUCTIZATION,
    FrameElement,
    FrameProps,
    _assemble_sparse_frame,
    _beam_end_offset_lookup,
    _component_restraints,
    _element_angle_array_from_props,
    _element_end_points,
    _frame_props,
    _local_frame_stiffness,
    _node_dofs,
    _rigid_end_offset_transform,
    _rotation_matrix,
    _select_full_line_mesh,
    _solve_sparse_system,
    _transform_stiffness,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance
from steel_constitutive_library import SteelMaterial as MonotonicSteelMaterial
from steel_constitutive_library import steel_response


SCHEMA_VERSION = "mgt-frame-material-nonlinear-tangent.v1"
_STEEL_GRADE_RE = re.compile(r"\bQ\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_CONCRETE_GRADE_RE = re.compile(r"\bC\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class MaterialTangentState:
    strain: float
    stress_mpa: float
    tangent_mpa: float
    solver_tangent_mpa: float
    tangent_ratio: float
    state_tag: str
    material_family: str
    inferred_strength_mpa: float | None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _material_e_mpa(mat: dict[str, Any], fallback_mpa: float = 1.0e-9) -> float:
    source = float(mat.get("E_kN_per_m2") or 0.0) * 1.0e-3
    return max(source if source > 0.0 else float(fallback_mpa), 1.0e-9)


def _match_grade(regex: re.Pattern[str], text: str) -> float | None:
    match = regex.search(text)
    if not match:
        return None
    value = float(match.group(1))
    return value if value > 0.0 else None


def _infer_strength_mpa(mat: dict[str, Any]) -> tuple[str, float | None]:
    family = str(mat.get("type") or "").upper()
    name = str(mat.get("name") or "")
    text = f"{family} {name}"
    if family in {"STEEL", "SRC"}:
        fy = _match_grade(_STEEL_GRADE_RE, text)
        if fy is not None:
            return family, fy
    if family in {"CONC", "SRC"}:
        fc = _match_grade(_CONCRETE_GRADE_RE, text)
        if fc is not None:
            return family, fc
    return family or "UNKNOWN", None


def _concrete_tangent_state(*, strain: float, e_mpa: float, fc_mpa: float) -> tuple[float, float, str]:
    fc = max(float(fc_mpa), 1.0)
    e0 = max(float(e_mpa), 1.0)
    ft = max(0.33 * math.sqrt(fc), 0.05 * fc)
    eps_t_crack = ft / e0
    eps_c0 = max(2.0 * fc / e0, 1.5e-3)
    eps_cu = max(3.5e-3, eps_c0 * 1.35)
    eps = float(strain)
    if eps >= 0.0:
        if eps <= eps_t_crack:
            return e0 * eps, e0, "concrete_tension_elastic"
        decay = math.exp(-(eps - eps_t_crack) / max(5.0 * eps_t_crack, 1.0e-9))
        stress = ft * max(0.05, decay)
        tangent = max(0.02 * e0, 0.05 * e0 * decay)
        return stress, tangent, "concrete_tension_cracked"

    comp = abs(eps)
    if comp <= eps_c0:
        x = comp / eps_c0
        stress = -fc * (2.0 * x - x * x)
        tangent = max(0.02 * e0, e0 * (1.0 - x))
        return stress, tangent, "concrete_compression_hardening"
    if comp <= eps_cu:
        residual = -0.20 * fc
        ratio = (comp - eps_c0) / max(eps_cu - eps_c0, 1.0e-9)
        stress = -fc + ratio * (residual + fc)
        tangent = max(0.02 * e0, 0.05 * e0 * (1.0 - ratio))
        return stress, tangent, "concrete_compression_softening"
    return -0.20 * fc, 0.02 * e0, "concrete_compression_crushed"


def _material_tangent_state(
    mat: dict[str, Any],
    strain: float,
    *,
    fallback_e_mpa: float = 1.0e-9,
) -> MaterialTangentState:
    family, strength = _infer_strength_mpa(mat)
    name = str(mat.get("name") or "")
    e_mpa = _material_e_mpa(mat, fallback_mpa=fallback_e_mpa)
    family_upper = family.upper()
    if family_upper == "USER" or "RIGID" in name.upper():
        tangent = e_mpa
        return MaterialTangentState(
            strain=float(strain),
            stress_mpa=e_mpa * float(strain),
            tangent_mpa=tangent,
            solver_tangent_mpa=tangent,
            tangent_ratio=1.0,
            state_tag="rigid_user_elastic_proxy",
            material_family=family_upper or "USER",
            inferred_strength_mpa=None,
        )

    if family_upper == "STEEL":
        fy = float(strength or 235.0)
        snap = steel_response(
            float(strain),
            MonotonicSteelMaterial(
                fy_mpa=fy,
                es_mpa=e_mpa,
                hardening_ratio=0.015,
                fu_mpa=max(1.45 * fy, fy + 100.0),
            ),
        )
        tangent = max(abs(float(snap.tangent_mpa)), 0.015 * e_mpa)
        return MaterialTangentState(
            strain=float(strain),
            stress_mpa=float(snap.stress_mpa),
            tangent_mpa=float(snap.tangent_mpa),
            solver_tangent_mpa=tangent,
            tangent_ratio=tangent / e_mpa,
            state_tag=f"steel_{snap.state_tag}",
            material_family=family_upper,
            inferred_strength_mpa=fy,
        )

    if family_upper == "SRC":
        fy = _match_grade(_STEEL_GRADE_RE, name) or 235.0
        fc = _match_grade(_CONCRETE_GRADE_RE, name) or 40.0
        steel_snap = steel_response(
            float(strain),
            MonotonicSteelMaterial(
                fy_mpa=float(fy),
                es_mpa=e_mpa,
                hardening_ratio=0.015,
                fu_mpa=max(1.45 * float(fy), float(fy) + 100.0),
            ),
        )
        concrete_e = max(float(mat.get("E_secondary_kN_per_m2") or 0.0) * 1.0e-3, 0.15 * e_mpa)
        concrete_stress, concrete_tangent, concrete_tag = _concrete_tangent_state(
            strain=float(strain),
            e_mpa=concrete_e,
            fc_mpa=float(fc),
        )
        steel_tangent = max(abs(float(steel_snap.tangent_mpa)), 0.015 * e_mpa)
        tangent = 0.75 * steel_tangent + 0.25 * concrete_tangent
        stress = 0.75 * float(steel_snap.stress_mpa) + 0.25 * concrete_stress
        return MaterialTangentState(
            strain=float(strain),
            stress_mpa=stress,
            tangent_mpa=tangent,
            solver_tangent_mpa=max(tangent, 0.02 * e_mpa),
            tangent_ratio=max(tangent, 0.02 * e_mpa) / e_mpa,
            state_tag=f"src_steel_{steel_snap.state_tag}+{concrete_tag}",
            material_family=family_upper,
            inferred_strength_mpa=float(fy),
        )

    if family_upper == "CONC":
        fc = float(strength or 40.0)
        stress, tangent, tag = _concrete_tangent_state(strain=float(strain), e_mpa=e_mpa, fc_mpa=fc)
        tangent = max(float(tangent), 0.02 * e_mpa)
        return MaterialTangentState(
            strain=float(strain),
            stress_mpa=stress,
            tangent_mpa=tangent,
            solver_tangent_mpa=tangent,
            tangent_ratio=tangent / e_mpa,
            state_tag=tag,
            material_family=family_upper,
            inferred_strength_mpa=fc,
        )

    tangent = e_mpa
    return MaterialTangentState(
        strain=float(strain),
        stress_mpa=e_mpa * float(strain),
        tangent_mpa=tangent,
        solver_tangent_mpa=tangent,
        tangent_ratio=1.0,
        state_tag="unknown_elastic_proxy",
        material_family=family_upper or "UNKNOWN",
        inferred_strength_mpa=strength,
    )


def _probe_strain(mat: dict[str, Any], service_strain: float, *, fallback_e_mpa: float = 1.0e-9) -> float:
    family, strength = _infer_strength_mpa(mat)
    family_upper = family.upper()
    name = str(mat.get("name") or "")
    if family_upper == "USER" or "RIGID" in name.upper():
        return float(service_strain)
    e_mpa = _material_e_mpa(mat, fallback_mpa=fallback_e_mpa)
    if family_upper in {"STEEL", "SRC"}:
        fy = _match_grade(_STEEL_GRADE_RE, name) or strength or 235.0
        threshold = float(fy) / e_mpa
        sign = 1.0 if service_strain >= 0.0 else -1.0
        return sign * max(abs(float(service_strain)) * 25.0, 1.25 * threshold)
    if family_upper == "CONC":
        fc = strength or 40.0
        eps_c0 = max(2.0 * float(fc) / e_mpa, 1.5e-3)
        return -max(abs(float(service_strain)) * 25.0, 1.10 * eps_c0)
    return float(service_strain)


def _axial_strain(elem: FrameElement, node_xyz: np.ndarray, u: np.ndarray) -> float:
    if u.size == 0:
        return 0.0
    disp = u.reshape((-1, DOF_PER_NODE))[:, :3]
    pi, pj = _element_end_points(elem, node_xyz)
    axis = np.asarray(pj - pi, dtype=np.float64)
    length = max(float(np.linalg.norm(axis)), 1.0e-9)
    axis /= length
    delta = disp[elem.node_j] - disp[elem.node_i]
    return float(np.dot(delta, axis) / length)


def _frame_props_with_tangent(
    elem: FrameElement,
    *,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    tangent_by_element_mpa: dict[int, float],
) -> tuple[FrameProps, bool]:
    props, used_real = _frame_props(elem, section_props=section_props, material_props=material_props)
    tangent_mpa = tangent_by_element_mpa.get(int(elem.elem_id))
    if tangent_mpa is None:
        return props, used_real
    mat = material_props.get(int(elem.material_id), {})
    nu = float(mat.get("poisson", 0.3) or 0.3)
    e_n_per_m2 = max(float(tangent_mpa) * 1.0e6, 1.0e6)
    return (
        FrameProps(
            area_m2=props.area_m2,
            e_n_per_m2=e_n_per_m2,
            g_n_per_m2=e_n_per_m2 / (2.0 * (1.0 + nu)) if nu > -0.95 else props.g_n_per_m2,
            iy_m4=props.iy_m4,
            iz_m4=props.iz_m4,
            j_m4=props.j_m4,
        ),
        used_real,
    )


def _assemble_material_tangent_frame(
    *,
    elements: list[FrameElement],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    tangent_by_element_mpa: dict[int, float],
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(n_dof, dtype=np.float64)
    real_count = 0
    total_gravity_n = 0.0
    min_tangent_ratio = 1.0
    reduction_count = 0
    for elem in elements:
        elastic_props, used_real = _frame_props(elem, section_props=section_props, material_props=material_props)
        props, _ = _frame_props_with_tangent(
            elem,
            section_props=section_props,
            material_props=material_props,
            tangent_by_element_mpa=tangent_by_element_mpa,
        )
        real_count += int(bool(used_real))
        ratio = props.e_n_per_m2 / max(elastic_props.e_n_per_m2, 1.0e-9)
        min_tangent_ratio = min(min_tangent_ratio, float(ratio))
        reduction_count += int(ratio < 0.98)
        weight_n = elastic_props.area_m2 * float(elem.length_m) * 7850.0 * 9.80665
        total_gravity_n += weight_n
        offset_i = np.asarray(elem.offset_i_global_m, dtype=np.float64)
        offset_j = np.asarray(elem.offset_j_global_m, dtype=np.float64)
        rigid_transform = _rigid_end_offset_transform(offset_i, offset_j)
        f_end = np.zeros(12, dtype=np.float64)
        f_end[2] -= 0.5 * weight_n
        f_end[8] -= 0.5 * weight_n
        f_node = rigid_transform.T @ f_end
        pi, pj = _element_end_points(elem, node_xyz)
        rotation = _rotation_matrix(pi, pj, roll_deg=elem.local_axis_angle_deg)
        local = _local_frame_stiffness(props, elem.length_m)
        ke_end = _transform_stiffness(local, rotation)
        ke = rigid_transform.T @ ke_end @ rigid_transform
        dofs = _node_dofs(elem.node_i) + _node_dofs(elem.node_j)
        for a, gi in enumerate(dofs):
            f_ext[gi] += float(f_node[a])
        for a, gi in enumerate(dofs):
            for b, gj in enumerate(dofs):
                rows.append(gi)
                cols.append(gj)
                vals.append(float(ke[a, b]))
    stiffness = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()
    return stiffness, f_ext, {
        "real_section_material_element_count": real_count,
        "real_section_material_coverage_pct": 100.0 * float(real_count) / max(float(len(elements)), 1.0),
        "total_gravity_n": total_gravity_n,
        "min_solver_tangent_ratio": min_tangent_ratio,
        "tangent_reduction_element_count": int(reduction_count),
    }


def _state_summary(states: list[MaterialTangentState]) -> dict[str, Any]:
    ratios = [float(state.tangent_ratio) for state in states]
    strains = [abs(float(state.strain)) for state in states]
    nonlinear = [
        state
        for state in states
        if state.material_family != "USER" and float(state.tangent_ratio) < 0.98
    ]
    return {
        "element_count": len(states),
        "material_family_counts": dict(Counter(state.material_family for state in states)),
        "state_tag_counts": dict(Counter(state.state_tag for state in states)),
        "nonlinear_tangent_element_count": len(nonlinear),
        "min_tangent_ratio": float(min(ratios)) if ratios else 1.0,
        "mean_tangent_ratio": float(np.mean(ratios)) if ratios else 1.0,
        "max_abs_strain": float(max(strains)) if strains else 0.0,
    }


def _weakest_examples(
    *,
    elements: list[FrameElement],
    service_states: dict[int, MaterialTangentState],
    probe_states: dict[int, MaterialTangentState],
    limit: int = 10,
) -> list[dict[str, Any]]:
    by_elem = {int(elem.elem_id): elem for elem in elements}
    rows: list[dict[str, Any]] = []
    for elem_id, probe in sorted(probe_states.items(), key=lambda item: item[1].tangent_ratio)[:limit]:
        elem = by_elem[int(elem_id)]
        service = service_states[int(elem_id)]
        rows.append(
            {
                "elem_id": int(elem_id),
                "section_id": int(elem.section_id),
                "material_id": int(elem.material_id),
                "material_family": probe.material_family,
                "service_strain": service.strain,
                "probe_strain": probe.strain,
                "probe_state_tag": probe.state_tag,
                "probe_tangent_ratio": probe.tangent_ratio,
            }
        )
    return rows


def run_mgt_frame_material_nonlinear_tangent(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    if not roundtrip_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["roundtrip_npz_missing"],
        }

    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = load_mgt_section_material_properties(mgt_path) if mgt_path.is_file() else {"sections": {}, "materials": {}}
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
    roundtrip = _load_json(roundtrip_json)

    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        elem_id_array = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_angle_deg = (
            np.asarray(archive["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in archive.files
            else _element_angle_array_from_props(props, elem_id_array)
        )
        elements, node_xyz_sub, select_meta = _select_full_line_mesh(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=elem_id_array,
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )

    restrained, component_count, base_node_count = _component_restraints(elements, node_xyz_sub)
    n_dof = int(node_xyz_sub.shape[0]) * DOF_PER_NODE
    free = np.asarray([idx for idx in range(n_dof) if idx not in restrained], dtype=np.int64)

    elastic_assembly_start = time.perf_counter()
    elastic_stiffness, f_ext, elastic_meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
    )
    elastic_assembly_s = time.perf_counter() - elastic_assembly_start
    elastic_solve_start = time.perf_counter()
    u_free, service_residual_inf, service_regularization = _solve_sparse_system(
        stiffness=elastic_stiffness,
        f_ext=f_ext,
        free=free,
    )
    elastic_solve_s = time.perf_counter() - elastic_solve_start
    u = np.zeros(n_dof, dtype=np.float64)
    u[free] = np.asarray(u_free, dtype=np.float64)

    service_states: dict[int, MaterialTangentState] = {}
    probe_states: dict[int, MaterialTangentState] = {}
    tangent_by_element_mpa: dict[int, float] = {}
    material_strengths: dict[str, dict[str, Any]] = {}
    for elem in elements:
        mat = material_props.get(int(elem.material_id), {})
        elastic_props, _used_real = _frame_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        fallback_e_mpa = float(elastic_props.e_n_per_m2) / 1.0e6
        service_strain = _axial_strain(elem, node_xyz_sub, u)
        service_state = _material_tangent_state(mat, service_strain, fallback_e_mpa=fallback_e_mpa)
        probe_state = _material_tangent_state(
            mat,
            _probe_strain(mat, service_strain, fallback_e_mpa=fallback_e_mpa),
            fallback_e_mpa=fallback_e_mpa,
        )
        service_states[int(elem.elem_id)] = service_state
        probe_states[int(elem.elem_id)] = probe_state
        tangent_by_element_mpa[int(elem.elem_id)] = float(probe_state.solver_tangent_mpa)
        family, strength = _infer_strength_mpa(mat)
        material_strengths[str(elem.material_id)] = {
            "family": family,
            "name": str(mat.get("name") or ""),
            "source_E_mpa": _material_e_mpa(mat, fallback_mpa=0.0),
            "solver_fallback_E_mpa": fallback_e_mpa if not mat else None,
            "inferred_strength_mpa": strength,
            "strength_source": "mgt_material_name_grade_proxy" if strength is not None else "not_inferred",
        }

    tangent_assembly_start = time.perf_counter()
    tangent_stiffness, tangent_f_ext, tangent_meta = _assemble_material_tangent_frame(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
        tangent_by_element_mpa=tangent_by_element_mpa,
    )
    tangent_assembly_s = time.perf_counter() - tangent_assembly_start
    tangent_solve_start = time.perf_counter()
    tangent_u_free, tangent_residual_inf, tangent_regularization = _solve_sparse_system(
        stiffness=tangent_stiffness,
        f_ext=tangent_f_ext,
        free=free,
    )
    tangent_solve_s = time.perf_counter() - tangent_solve_start

    solved_all_line = int(select_meta["raw_line_element_count"]) == len(elements) + int(
        select_meta["skipped_short_or_degenerate_count"]
    )
    service_ready = bool(
        solved_all_line
        and len(elements) > 0
        and free.size > 0
        and np.all(np.isfinite(u_free))
        and service_residual_inf <= 1.0e-3
    )
    probe_summary = _state_summary(list(probe_states.values()))
    service_summary = _state_summary(list(service_states.values()))
    probe_ready = bool(
        int(probe_summary["nonlinear_tangent_element_count"]) > 0
        and float(probe_summary["min_tangent_ratio"]) < 0.98
    )
    smoke_ready = bool(
        np.all(np.isfinite(tangent_u_free))
        and tangent_residual_inf <= 1.0e-3
        and int(tangent_meta["tangent_reduction_element_count"]) > 0
    )
    ready = bool(service_ready and probe_ready and smoke_ready)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial",
        "frame_material_nonlinear_tangent_ready": ready,
        "service_load_material_state_ready": service_ready,
        "controlled_probe_material_state_ready": probe_ready,
        "bounded_material_tangent_global_smoke_ready": smoke_ready,
        "global_smoke_solver_uses_per_element_material_tangent": smoke_ready,
        "full_material_nonlinear_newton_equilibrium": False,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "claim_boundary": (
            "MGT line/frame elements consume source material E/nu and material-name grade proxies "
            "for bounded nonlinear tangent states. Service load material states and a controlled "
            "yield/damage probe are assembled into a per-element tangent smoke solve. This is not "
            "full path-dependent material nonlinear Newton closure, fiber-section closure, or shell material closure."
        ),
        "strength_proxy_policy": {
            "steel": "Q235-style material names infer fy in MPa",
            "concrete": "C40-style material names infer fc in MPa",
            "src": "Cxx+Qyyy names infer concrete fc and steel fy; tangent is bounded composite proxy",
            "rigid_user": "RigidBar/USER rows remain elastic and are excluded from nonlinear damage claims",
        },
        "mesh_fingerprint": {
            **select_meta,
            "line_elements_solved": len(elements),
            "line_nodes_solved": int(node_xyz_sub.shape[0]),
            "component_count": component_count,
            "base_node_count": base_node_count,
            "dof_count": n_dof,
            "free_dof_count": int(free.size),
            "restrained_dof_count": len(restrained),
            "elastic_stiffness_nnz": int(elastic_stiffness.nnz),
            "material_tangent_stiffness_nnz": int(tangent_stiffness.nnz),
        },
        "material_strength_inventory": material_strengths,
        "service_material_state_summary": service_summary,
        "controlled_probe_material_state_summary": probe_summary,
        "weakest_probe_elements": _weakest_examples(
            elements=elements,
            service_states=service_states,
            probe_states=probe_states,
        ),
        "elastic_reference_equilibrium": {
            "residual_inf_n": service_residual_inf,
            "regularization": service_regularization,
            "real_section_material_coverage_pct": elastic_meta.get("real_section_material_coverage_pct"),
            "total_gravity_kn": float(elastic_meta.get("total_gravity_n") or 0.0) / 1000.0,
        },
        "material_tangent_smoke_equilibrium": {
            "residual_inf_n": tangent_residual_inf,
            "regularization": tangent_regularization,
            "real_section_material_coverage_pct": tangent_meta.get("real_section_material_coverage_pct"),
            "min_solver_tangent_ratio": tangent_meta.get("min_solver_tangent_ratio"),
            "tangent_reduction_element_count": tangent_meta.get("tangent_reduction_element_count"),
            "total_gravity_kn": float(tangent_meta.get("total_gravity_n") or 0.0) / 1000.0,
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_6dof_frame_material_tangent_smoke",
            "elastic_assembly_seconds": elastic_assembly_s,
            "elastic_solve_seconds": elastic_solve_s,
            "material_tangent_assembly_seconds": tangent_assembly_s,
            "material_tangent_solve_seconds": tangent_solve_s,
            "total_seconds": time.perf_counter() - started,
        },
        "limitations": [
            "Controlled probe strain is not a production load combination.",
            "Tangent is per-element axial material tangent mapped onto frame EA/EI/GJ stiffness, not a full fiber-section Jacobian.",
            "No path-dependent internal-force history update or Newton residual iteration is promoted by this artifact.",
            "Shell/plate material nonlinearity remains outside this frame receipt.",
        ],
        "blockers": []
        if ready
        else [
            *([] if service_ready else ["service_load_material_state_not_ready"]),
            *([] if probe_ready else ["controlled_probe_material_state_not_ready"]),
            *([] if smoke_ready else ["material_tangent_global_smoke_not_ready"]),
        ],
    }
    out = output_json or PRODUCTIZATION / "mgt_frame_material_nonlinear_tangent.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_frame_material_nonlinear_tangent.json")
    args = parser.parse_args()
    payload = run_mgt_frame_material_nonlinear_tangent(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
    )
    probe = payload.get("controlled_probe_material_state_summary") or {}
    smoke = payload.get("material_tangent_smoke_equilibrium") or {}
    print(
        "mgt-frame-material-nonlinear-tangent: "
        f"status={payload['status']} nonlinear_probe={probe.get('nonlinear_tangent_element_count')} "
        f"min_tangent_ratio={probe.get('min_tangent_ratio')} "
        f"residual={smoke.get('residual_inf_n')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
