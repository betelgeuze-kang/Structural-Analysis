#!/usr/bin/env python3
"""Run a full line/beam MGT sparse global equilibrium solve."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, eye
from scipy.sparse.linalg import spsolve

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_story_model_reanalysis import build_mgt_reanalysis_provenance
from solve_mgt_beam_mesh_3d_global import (
    DOF_PER_NODE,
    BeamElement,
    _element_beam_props,
    _node_dof_indices,
    solve_beam_column_global_response,
)


SCHEMA_VERSION = "mgt-full-line-mesh-sparse-equilibrium.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _select_full_line_mesh(
    *,
    node_xyz: np.ndarray,
    edge_index: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
) -> tuple[list[BeamElement], np.ndarray, dict[str, Any]]:
    n_elem = int(elem_id.shape[0])
    edge = np.asarray(edge_index[:, :n_elem], dtype=np.int64)
    line_mask = np.asarray(elem_type_code, dtype=np.int32) == 1
    used_nodes = sorted(
        set(edge[0, line_mask].astype(int).tolist())
        | set(edge[1, line_mask].astype(int).tolist())
    )
    remap = {old: new for new, old in enumerate(used_nodes)}
    node_xyz_sub = np.asarray([node_xyz[old] for old in used_nodes], dtype=np.float64)
    elements: list[BeamElement] = []
    skipped_short = 0
    for idx in np.where(line_mask)[0]:
        old_i = int(edge[0, idx])
        old_j = int(edge[1, idx])
        if old_i not in remap or old_j not in remap:
            continue
        i = remap[old_i]
        j = remap[old_j]
        pi = node_xyz_sub[i]
        pj = node_xyz_sub[j]
        length_m = float(np.linalg.norm(pj - pi))
        if length_m < 0.25:
            skipped_short += 1
            continue
        plan_length_m = float(np.hypot(pj[0] - pi[0], pj[1] - pi[1]))
        elements.append(
            BeamElement(
                elem_id=int(elem_id[idx]),
                node_i=i,
                node_j=j,
                section_id=int(elem_section_id[idx]),
                material_id=int(elem_material_id[idx]),
                length_m=length_m,
                node_i_xz=(0.0, float(pi[2])),
                node_j_xz=(max(plan_length_m, 1.0e-6), float(pj[2])),
            )
        )
    return elements, node_xyz_sub, {
        "raw_line_element_count": int(np.count_nonzero(line_mask)),
        "skipped_short_or_degenerate_count": skipped_short,
        "line_node_count": len(used_nodes),
    }


def _component_restraints(elements: list[BeamElement], node_xyz: np.ndarray) -> tuple[set[int], int, int]:
    adjacency: dict[int, list[int]] = {idx: [] for idx in range(int(node_xyz.shape[0]))}
    for elem in elements:
        adjacency[elem.node_i].append(elem.node_j)
        adjacency[elem.node_j].append(elem.node_i)
    visited: set[int] = set()
    restrained: set[int] = set()
    component_count = 0
    base_node_count = 0
    for start in range(int(node_xyz.shape[0])):
        if start in visited or not adjacency.get(start):
            continue
        queue = [start]
        visited.add(start)
        component_nodes: list[int] = []
        while queue:
            current = queue.pop()
            component_nodes.append(current)
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        z_min = float(np.min(node_xyz[component_nodes, 2]))
        base_nodes = [
            node for node in component_nodes if abs(float(node_xyz[node, 2]) - z_min) <= 0.05
        ]
        if not base_nodes:
            base_nodes = [component_nodes[0]]
        for node in base_nodes:
            restrained.update(_node_dof_indices(node))
        component_count += 1
        base_node_count += len(base_nodes)
    return restrained, component_count, base_node_count


def _assemble_sparse_elastic(
    *,
    elements: list[BeamElement],
    n_nodes: int,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    element_axial_forces: dict[int, float] | None = None,
    include_geometric: bool = False,
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    n_dof = int(n_nodes) * DOF_PER_NODE
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(n_dof, dtype=np.float64)
    real_count = 0
    total_gravity_n = 0.0
    section_usage: Counter[int] = Counter()
    material_usage: Counter[int] = Counter()
    for elem in elements:
        props, used_real = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        real_count += int(bool(used_real))
        section_usage[int(elem.section_id)] += 1
        material_usage[int(elem.material_id)] += 1
        weight_n = float(props.area_m2) * float(elem.length_m) * 7850.0 * 9.80665
        total_gravity_n += weight_n
        for node in (elem.node_i, elem.node_j):
            _, uz, _ = _node_dof_indices(node)
            f_ext[uz] -= 0.5 * weight_n
        response = solve_beam_column_global_response(
            props=props,
            deformation_global=np.zeros(6, dtype=np.float64),
            node_i=elem.node_i_xz,
            node_j=elem.node_j_xz,
            axial_force_n=float((element_axial_forces or {}).get(elem.elem_id, 0.0)),
            include_geometric=include_geometric,
            formulation="force_based",
        )
        dofs = _node_dof_indices(elem.node_i) + _node_dof_indices(elem.node_j)
        for a, gi in enumerate(dofs):
            for b, gj in enumerate(dofs):
                rows.append(gi)
                cols.append(gj)
                vals.append(float(response.global_stiffness[a, b]))
    stiffness = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()
    meta = {
        "real_section_material_element_count": real_count,
        "real_section_material_coverage_pct": 100.0 * float(real_count) / max(float(len(elements)), 1.0),
        "total_gravity_n": total_gravity_n,
        "unique_section_count": len(section_usage),
        "unique_material_count": len(material_usage),
        "section_usage_head": dict(section_usage.most_common(10)),
        "material_usage_head": dict(material_usage.most_common(10)),
    }
    return stiffness, f_ext, meta


def _component_gravity_axial_forces(
    *,
    elements: list[BeamElement],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> dict[int, float]:
    by_node: dict[int, list[BeamElement]] = {idx: [] for idx in range(int(node_xyz.shape[0]))}
    weights: dict[int, float] = {}
    pcr_cap: dict[int, float] = {}
    for elem in elements:
        by_node[elem.node_i].append(elem)
        by_node[elem.node_j].append(elem)
        props, _used_real = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        weights[elem.elem_id] = float(props.area_m2) * float(elem.length_m) * 7850.0 * 9.80665
        ei = float(props.e_mpa) * 1.0e6 * float(props.iy_m4)
        pcr = float(np.pi**2 * ei / max(float(elem.length_m) ** 2, 1.0e-9))
        pcr_cap[elem.elem_id] = 0.25 * max(pcr, 0.0)

    visited_nodes: set[int] = set()
    axial: dict[int, float] = {}
    for start in range(int(node_xyz.shape[0])):
        if start in visited_nodes or not by_node.get(start):
            continue
        queue = [start]
        visited_nodes.add(start)
        component_elements: dict[int, BeamElement] = {}
        while queue:
            current = queue.pop()
            for elem in by_node.get(current, []):
                component_elements[elem.elem_id] = elem
                other = elem.node_j if elem.node_i == current else elem.node_i
                if other not in visited_nodes:
                    visited_nodes.add(other)
                    queue.append(other)
        ordered = sorted(
            component_elements.values(),
            key=lambda elem: 0.5 * (float(node_xyz[elem.node_i, 2]) + float(node_xyz[elem.node_j, 2])),
            reverse=True,
        )
        weight_above = 0.0
        for elem in ordered:
            dz = abs(float(node_xyz[elem.node_j, 2]) - float(node_xyz[elem.node_i, 2]))
            verticality = dz / max(float(elem.length_m), 1.0e-9)
            raw_axial = max(weight_above, 0.0) * min(max(verticality, 0.0), 1.0)
            axial[elem.elem_id] = min(raw_axial, pcr_cap.get(elem.elem_id, raw_axial))
            weight_above += weights.get(elem.elem_id, 0.0)
    return axial


def _solve_sparse_system(
    *,
    stiffness: Any,
    f_ext: np.ndarray,
    free: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    k_ff = stiffness[free, :][:, free].tocsc()
    diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
    regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
    k_ff = k_ff + eye(k_ff.shape[0], format="csc") * regularization
    u_free = spsolve(k_ff, f_ext[free])
    residual = k_ff @ u_free - f_ext[free]
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    return np.asarray(u_free, dtype=np.float64), residual_inf, regularization


def run_mgt_full_line_mesh_sparse_equilibrium(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
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
    roundtrip = _load_json(roundtrip_json)
    started = time.perf_counter()
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        elements, node_xyz_sub, select_meta = _select_full_line_mesh(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=np.asarray(archive["elem_id"], dtype=np.int64),
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
        )
    select_s = time.perf_counter() - started
    n_nodes = int(node_xyz_sub.shape[0])
    n_dof = n_nodes * DOF_PER_NODE
    restrained, component_count, base_node_count = _component_restraints(elements, node_xyz_sub)
    free = np.asarray([idx for idx in range(n_dof) if idx not in restrained], dtype=np.int64)
    assemble_start = time.perf_counter()
    stiffness, f_ext, asm_meta = _assemble_sparse_elastic(
        elements=elements,
        n_nodes=n_nodes,
        section_props=section_props,
        material_props=material_props,
    )
    assemble_s = time.perf_counter() - assemble_start
    solve_start = time.perf_counter()
    u_free, residual_inf, regularization = _solve_sparse_system(stiffness=stiffness, f_ext=f_ext, free=free)
    solve_s = time.perf_counter() - solve_start
    u = np.zeros(n_dof, dtype=np.float64)
    u[free] = np.asarray(u_free, dtype=np.float64)
    axial_forces = _component_gravity_axial_forces(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
    )
    geometric_assemble_start = time.perf_counter()
    geometric_stiffness, _geo_f_ext, geo_asm_meta = _assemble_sparse_elastic(
        elements=elements,
        n_nodes=n_nodes,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    geometric_assembly_s = time.perf_counter() - geometric_assemble_start
    geometric_solve_start = time.perf_counter()
    geo_u_free, geo_residual_inf, geo_regularization = _solve_sparse_system(
        stiffness=geometric_stiffness,
        f_ext=f_ext,
        free=free,
    )
    geometric_solve_s = time.perf_counter() - geometric_solve_start
    geo_u = np.zeros(n_dof, dtype=np.float64)
    geo_u[free] = np.asarray(geo_u_free, dtype=np.float64)
    z_vals = node_xyz_sub[:, 2] if node_xyz_sub.size else np.asarray([0.0])
    story_h = np.maximum(z_vals - float(np.min(z_vals)), 0.5)
    ux = u[0::DOF_PER_NODE]
    uz = u[1::DOF_PER_NODE]
    max_drift_ratio_pct = float(np.max(np.abs(ux) / story_h * 100.0)) if ux.size else 0.0
    top_displacement_m = float(np.max(np.hypot(ux, uz))) if ux.size else 0.0
    geo_ux = geo_u[0::DOF_PER_NODE]
    geo_uz = geo_u[1::DOF_PER_NODE]
    geo_max_drift_ratio_pct = float(np.max(np.abs(geo_ux) / story_h * 100.0)) if geo_ux.size else 0.0
    geo_top_displacement_m = float(np.max(np.hypot(geo_ux, geo_uz))) if geo_ux.size else 0.0
    solved_all_line = int(select_meta["raw_line_element_count"]) == len(elements) + int(select_meta["skipped_short_or_degenerate_count"])
    elastic_ready = bool(
        solved_all_line
        and len(elements) > 0
        and free.size > 0
        and np.all(np.isfinite(u_free))
        and residual_inf <= 1.0e-3
    )
    axial_positive = [force for force in axial_forces.values() if float(force) > 0.0]
    geometric_ready = bool(
        elastic_ready
        and np.all(np.isfinite(geo_u_free))
        and geo_residual_inf <= 1.0e-3
        and len(axial_positive) > 0
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if elastic_ready and geometric_ready else "partial",
        "full_line_mesh_sparse_elastic_equilibrium_ready": elastic_ready,
        "full_line_mesh_linearized_geometric_equilibrium_ready": geometric_ready,
        "full_line_mesh_nonlinear_equilibrium": False,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "solve_scope": "full_line_element_mesh_sparse_elastic_and_linearized_geometric_equilibrium",
        "claim_boundary": (
            "Solves the full line/beam element graph with sparse elastic and linearized geometric global "
            "tangents under gravity loads. Horizontal X/Y members are projected into a collapsed horizontal "
            "DOF; shell/plate and deformed-state nonlinear full-building equilibrium remain separate gaps."
        ),
        "mesh_fingerprint": {
            **select_meta,
            "line_elements_solved": len(elements),
            "line_nodes_solved": n_nodes,
            "component_count": component_count,
            "base_node_count": base_node_count,
            "dof_count": n_dof,
            "free_dof_count": int(free.size),
            "restrained_dof_count": len(restrained),
            "stiffness_nnz": int(stiffness.nnz),
            "geometric_stiffness_nnz": int(geometric_stiffness.nnz),
        },
        "section_material_coverage": asm_meta,
        "linearized_geometric_tangent": {
            "positive_axial_element_count": len(axial_positive),
            "max_axial_force_n": float(max(axial_positive)) if axial_positive else 0.0,
            "mean_positive_axial_force_n": float(np.mean(axial_positive)) if axial_positive else 0.0,
            "real_section_material_coverage_pct": geo_asm_meta.get("real_section_material_coverage_pct"),
        },
        "equilibrium_metrics": {
            "residual_inf_n": residual_inf,
            "max_abs_displacement_m": float(np.max(np.abs(u_free))) if u_free.size else 0.0,
            "top_displacement_m": top_displacement_m,
            "max_drift_ratio_pct": max_drift_ratio_pct,
            "total_gravity_kn": float(asm_meta["total_gravity_n"]) / 1000.0,
            "regularization": regularization,
        },
        "geometric_equilibrium_metrics": {
            "residual_inf_n": geo_residual_inf,
            "max_abs_displacement_m": float(np.max(np.abs(geo_u_free))) if geo_u_free.size else 0.0,
            "top_displacement_m": geo_top_displacement_m,
            "max_drift_ratio_pct": geo_max_drift_ratio_pct,
            "regularization": geo_regularization,
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu",
            "selection_seconds": select_s,
            "assembly_seconds": assemble_s,
            "solve_seconds": solve_s,
            "geometric_assembly_seconds": geometric_assembly_s,
            "geometric_solve_seconds": geometric_solve_s,
            "total_seconds": select_s + assemble_s + solve_s + geometric_assembly_s + geometric_solve_s,
        },
        "limitations": [
            "Sparse line mesh covers elastic and linearized geometric tangents, not full deformed-state nonlinear Newton closure.",
            "Collapsed horizontal DOF is a line-element productionization step, not a complete 6-DOF frame/shell model.",
            "Plate/shell surface elements remain unsupported by the current global tangent.",
        ],
        "blockers": [] if elastic_ready and geometric_ready else ["full_line_mesh_sparse_geometric_equilibrium_not_ready"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_full_line_mesh_sparse_equilibrium.json")
    args = parser.parse_args()
    payload = run_mgt_full_line_mesh_sparse_equilibrium(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
    )
    mesh = payload.get("mesh_fingerprint") or {}
    print(
        "mgt-full-line-sparse: "
        f"status={payload['status']} line={mesh.get('line_elements_solved')}/{mesh.get('raw_line_element_count')} "
        f"elastic_residual={(payload.get('equilibrium_metrics') or {}).get('residual_inf_n')} "
        f"geometric_residual={(payload.get('geometric_equilibrium_metrics') or {}).get('residual_inf_n')} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
