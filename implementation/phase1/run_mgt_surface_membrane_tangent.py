#!/usr/bin/env python3
"""Assemble a surface membrane tangent smoke solve for MGT PLATE elements."""

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


SCHEMA_VERSION = "mgt-surface-membrane-tangent.v1"
DOF_PER_NODE = 3  # translational membrane projection only
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _node_dofs(node: int) -> tuple[int, int, int]:
    base = int(node) * DOF_PER_NODE
    return base, base + 1, base + 2


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _triangulate(conn: list[int]) -> list[tuple[int, int, int]]:
    if len(conn) == 3:
        return [(conn[0], conn[1], conn[2])]
    if len(conn) == 4:
        return [(conn[0], conn[1], conn[2]), (conn[0], conn[2], conn[3])]
    return []


def _surface_components(surface_conns: list[list[int]], n_nodes: int) -> tuple[list[int], int]:
    adjacency: dict[int, set[int]] = {idx: set() for idx in range(n_nodes)}
    for conn in surface_conns:
        for i, node_i in enumerate(conn):
            for node_j in conn[i + 1 :]:
                adjacency[node_i].add(node_j)
                adjacency[node_j].add(node_i)
    visited: set[int] = set()
    base_nodes: list[int] = []
    component_count = 0
    return_nodes: list[list[int]] = []
    for start in range(n_nodes):
        if start in visited or not adjacency[start]:
            continue
        queue = [start]
        visited.add(start)
        component: list[int] = []
        while queue:
            current = queue.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return_nodes.append(component)
        component_count += 1
    return base_nodes, component_count


def _local_basis(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> tuple[np.ndarray, np.ndarray, float] | None:
    v1 = np.asarray(p1 - p0, dtype=np.float64)
    v2 = np.asarray(p2 - p0, dtype=np.float64)
    normal = np.cross(v1, v2)
    area2 = float(np.linalg.norm(normal))
    if area2 <= 1.0e-10:
        return None
    e1 = v1 / max(float(np.linalg.norm(v1)), 1.0e-12)
    e3 = normal / area2
    e2 = np.cross(e3, e1)
    e2 /= max(float(np.linalg.norm(e2)), 1.0e-12)
    return e1, e2, 0.5 * area2


def _triangle_membrane_stiffness(
    *,
    points: np.ndarray,
    e_n_per_m2: float,
    poisson: float,
    thickness_m: float,
) -> tuple[np.ndarray, float] | None:
    basis = _local_basis(points[0], points[1], points[2])
    if basis is None:
        return None
    e1, e2, area = basis
    xy = np.array(
        [
            [0.0, 0.0],
            [float(np.dot(points[1] - points[0], e1)), float(np.dot(points[1] - points[0], e2))],
            [float(np.dot(points[2] - points[0], e1)), float(np.dot(points[2] - points[0], e2))],
        ],
        dtype=np.float64,
    )
    x1, y1 = xy[0]
    x2, y2 = xy[1]
    x3, y3 = xy[2]
    signed_area = 0.5 * ((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
    if abs(signed_area) <= 1.0e-12:
        return None
    b = np.array([y2 - y3, y3 - y1, y1 - y2], dtype=np.float64)
    c = np.array([x3 - x2, x1 - x3, x2 - x1], dtype=np.float64)
    bmat = np.zeros((3, 6), dtype=np.float64)
    for idx in range(3):
        bmat[0, 2 * idx] = b[idx]
        bmat[1, 2 * idx + 1] = c[idx]
        bmat[2, 2 * idx] = c[idx]
        bmat[2, 2 * idx + 1] = b[idx]
    bmat /= 2.0 * signed_area
    nu = min(max(float(poisson), 0.0), 0.49)
    dmat = float(e_n_per_m2) * float(thickness_m) / (1.0 - nu**2) * np.array(
        [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]],
        dtype=np.float64,
    )
    k_local = abs(signed_area) * (bmat.T @ dmat @ bmat)
    transform = np.zeros((6, 9), dtype=np.float64)
    for node in range(3):
        transform[2 * node, 3 * node : 3 * node + 3] = e1
        transform[2 * node + 1, 3 * node : 3 * node + 3] = e2
    return transform.T @ k_local @ transform, area


def _fallback_thickness(section_id: int) -> float:
    return 0.12 + 0.01 * float(int(section_id) % 9)


def _source_or_fallback_thickness(
    section_id: int,
    plate_thickness_props: dict[int, dict[str, Any]],
) -> tuple[float, bool]:
    props = plate_thickness_props.get(int(section_id))
    if isinstance(props, dict):
        thickness = float(props.get("effective_thickness_m") or 0.0)
        if thickness > 0.0:
            return thickness, True
    return _fallback_thickness(section_id), False


def _thickness_policy(source_coverage_pct: float) -> str:
    if source_coverage_pct >= 99.999:
        return "source_mgt_thickness_rows_by_plate_section_id"
    if source_coverage_pct > 0.0:
        return "mixed_source_mgt_thickness_rows_with_section_id_fallback"
    return "deterministic_section_id_fallback_no_source_thickness_rows"


def run_mgt_surface_membrane_tangent(
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
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    plate_thickness_props = props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
    roundtrip = _load_json(roundtrip_json)
    started = time.perf_counter()
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
        conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)

    surface_indices = np.where(elem_type_code == 2)[0]
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(n_dof, dtype=np.float64)
    surface_conns: list[list[int]] = []
    tri_count = 0
    skipped_degenerate = 0
    total_area = 0.0
    covered_material = 0
    covered_source_thickness = 0
    material_usage: Counter[int] = Counter()
    section_usage: Counter[int] = Counter()
    thickness_values: list[float] = []
    for elem_index in surface_indices.tolist():
        conn = [int(node) for node in conn_idx[conn_ptr[elem_index] : conn_ptr[elem_index + 1]].tolist()]
        if len(conn) not in {3, 4}:
            continue
        surface_conns.append(conn)
        material_id = int(elem_material_id[elem_index])
        section_id = int(elem_section_id[elem_index])
        material_usage[material_id] += 1
        section_usage[section_id] += 1
        mat = material_props.get(material_id)
        if isinstance(mat, dict):
            covered_material += 1
        e_n_per_m2 = float((mat or {}).get("E_kN_per_m2") or 2.1e8) * 1000.0
        poisson = float((mat or {}).get("poisson") or 0.2)
        thickness, has_source_thickness = _source_or_fallback_thickness(section_id, plate_thickness_props)
        if has_source_thickness:
            covered_source_thickness += 1
        thickness_values.append(thickness)
        for tri in _triangulate(conn):
            points = np.asarray([node_xyz[node] for node in tri], dtype=np.float64)
            result = _triangle_membrane_stiffness(
                points=points,
                e_n_per_m2=e_n_per_m2,
                poisson=poisson,
                thickness_m=thickness,
            )
            if result is None:
                skipped_degenerate += 1
                continue
            ke, area = result
            tri_count += 1
            total_area += area
            # Deterministic in-plane smoke load: unit local-x traction distributed to nodes.
            basis = _local_basis(points[0], points[1], points[2])
            if basis is not None:
                e1, _e2, _area = basis
                for node in tri:
                    for local_dof, load in zip(_node_dofs(node), e1 * area / 3.0):
                        f_ext[local_dof] += float(load)
            dofs = tuple(dof for node in tri for dof in _node_dofs(node))
            for a, gi in enumerate(dofs):
                for b, gj in enumerate(dofs):
                    rows.append(gi)
                    cols.append(gj)
                    vals.append(float(ke[a, b]))
    stiffness = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()
    assembly_s = time.perf_counter() - started
    active = np.asarray(np.where(np.abs(stiffness.diagonal()) > 1.0e-9)[0], dtype=np.int64)
    if active.size:
        k_active = stiffness[active, :][:, active].tocsc()
        diag = np.asarray(k_active.diagonal(), dtype=np.float64)
        regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
        solve_start = time.perf_counter()
        u_active = spsolve(k_active + eye(k_active.shape[0], format="csc") * regularization, f_ext[active])
        residual = (k_active + eye(k_active.shape[0], format="csc") * regularization) @ u_active - f_ext[active]
        solve_s = time.perf_counter() - solve_start
        residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        max_displacement = float(np.max(np.abs(u_active))) if u_active.size else 0.0
    else:
        regularization = 0.0
        solve_s = 0.0
        residual_inf = float("inf")
        max_displacement = 0.0
    material_coverage_pct = 100.0 * float(covered_material) / max(float(surface_indices.size), 1.0)
    source_thickness_coverage_pct = 100.0 * float(covered_source_thickness) / max(float(surface_indices.size), 1.0)
    membrane_ready = bool(surface_indices.size > 0 and tri_count > 0 and stiffness.nnz > 0)
    smoke_ready = bool(membrane_ready and active.size > 0 and residual_inf <= 1.0e-3 and np.isfinite(max_displacement))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if membrane_ready and smoke_ready else "partial",
        "surface_membrane_tangent_ready": membrane_ready,
        "surface_membrane_smoke_solve_ready": smoke_ready,
        "surface_shell_full_bending_tangent_ready": False,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "mesh_fingerprint": {
            "surface_element_count": int(surface_indices.size),
            "surface_quad_count": int(sum(1 for conn in surface_conns if len(conn) == 4)),
            "surface_tri_count": int(sum(1 for conn in surface_conns if len(conn) == 3)),
            "assembled_triangle_count": tri_count,
            "skipped_degenerate_triangle_count": skipped_degenerate,
            "surface_node_count": len({node for conn in surface_conns for node in conn}),
            "dof_count": n_dof,
            "active_membrane_dof_count": int(active.size),
            "stiffness_nnz": int(stiffness.nnz),
        },
        "surface_material_coverage": {
            "material_coverage_count": covered_material,
            "material_coverage_pct": material_coverage_pct,
            "unique_material_count": len(material_usage),
            "unique_section_count": len(section_usage),
            "material_usage_head": dict(material_usage.most_common(10)),
            "section_usage_head": dict(section_usage.most_common(10)),
            "thickness_policy": _thickness_policy(source_thickness_coverage_pct),
            "source_plate_thickness_coverage_count": covered_source_thickness,
            "source_plate_thickness_coverage_pct": source_thickness_coverage_pct,
            "source_thickness_table_count": len(plate_thickness_props),
            "thickness_min_m": float(min(thickness_values)) if thickness_values else 0.0,
            "thickness_max_m": float(max(thickness_values)) if thickness_values else 0.0,
        },
        "equilibrium_metrics": {
            "residual_inf_n": residual_inf,
            "max_abs_displacement_m": max_displacement,
            "total_surface_area_m2": total_area,
            "regularization": regularization,
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_surface_membrane",
            "assembly_seconds": assembly_s,
            "solve_seconds": solve_s,
            "total_seconds": assembly_s + solve_s,
        },
        "claim_boundary": (
            "Assembles MGT PLATE rows into a translational membrane tangent and runs a deterministic "
            "in-plane smoke solve. Bending, drilling rotation, transverse shell behavior, plate thickness "
            "calibration, and full frame-shell coupling remain outside this artifact."
        ),
        "limitations": [
            "Membrane-only constant-strain triangles after quad triangulation.",
            "No shell bending, drilling DOF, transverse pressure solve, or frame-shell coupled global tangent yet.",
            "Plate thickness is read from MGT *THICKNESS VALUE rows when the PLATE property id resolves; "
            "any unresolved id falls back deterministically and is counted in coverage.",
        ],
        "blockers": []
        if membrane_ready and smoke_ready
        else ["surface_membrane_tangent_or_smoke_solve_not_ready"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_surface_membrane_tangent.json")
    args = parser.parse_args()
    payload = run_mgt_surface_membrane_tangent(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
    )
    mesh = payload.get("mesh_fingerprint") or {}
    print(
        "mgt-surface-membrane: "
        f"status={payload['status']} surface={mesh.get('surface_element_count')} "
        f"tri={mesh.get('assembled_triangle_count')} "
        f"residual={(payload.get('equilibrium_metrics') or {}).get('residual_inf_n')} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
