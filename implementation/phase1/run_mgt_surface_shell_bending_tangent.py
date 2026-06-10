#!/usr/bin/env python3
"""Assemble a surface shell bending/drilling tangent smoke solve for MGT PLATE elements."""

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
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE, _node_dofs
from run_mgt_surface_membrane_tangent import (
    _local_basis,
    _source_or_fallback_thickness,
    _thickness_policy,
    _triangulate,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-surface-shell-bending-tangent.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _triangle_shell_bending_stiffness(
    *,
    points: np.ndarray,
    e_n_per_m2: float,
    poisson: float,
    thickness_m: float,
    orthotropic_D: np.ndarray | None = None,
) -> tuple[np.ndarray, float] | None:
    basis = _local_basis(points[0], points[1], points[2])
    if basis is None:
        return None
    e1, e2, _area = basis
    e3 = np.cross(e1, e2)
    e3 /= max(float(np.linalg.norm(e3)), 1.0e-12)
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
    b = np.array([y2 - y3, y3 - y1, y1 - y2], dtype=np.float64) / (2.0 * signed_area)
    c = np.array([x3 - x2, x1 - x3, x2 - x1], dtype=np.float64) / (2.0 * signed_area)
    nu = min(max(float(poisson), 0.0), 0.49)
    thickness = max(float(thickness_m), 1.0e-4)
    e = float(e_n_per_m2)
    g = e / (2.0 * (1.0 + nu))
    if orthotropic_D is not None:
        d_b = np.asarray(orthotropic_D, dtype=np.float64)
        if d_b.shape != (3, 3):
            return None
    else:
        d_b = e * thickness**3 / (12.0 * (1.0 - nu**2)) * np.array(
            [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]],
            dtype=np.float64,
        )
    d_s = (5.0 / 6.0) * g * thickness * np.eye(2, dtype=np.float64)
    b_b = np.zeros((3, 9), dtype=np.float64)
    b_s = np.zeros((2, 9), dtype=np.float64)
    for idx in range(3):
        w = 3 * idx
        theta_x = w + 1
        theta_y = w + 2
        b_b[0, theta_y] = b[idx]
        b_b[1, theta_x] = -c[idx]
        b_b[2, theta_x] = -b[idx]
        b_b[2, theta_y] = c[idx]
        b_s[0, w] = b[idx]
        b_s[0, theta_y] = -1.0 / 3.0
        b_s[1, w] = c[idx]
        b_s[1, theta_x] = 1.0 / 3.0
    area = abs(signed_area)
    k_local = area * (b_b.T @ d_b @ b_b + b_s.T @ d_s @ b_s)
    transform = np.zeros((9, 18), dtype=np.float64)
    for node in range(3):
        global_offset = 6 * node
        local_offset = 3 * node
        transform[local_offset, global_offset : global_offset + 3] = e3
        transform[local_offset + 1, global_offset + 3 : global_offset + 6] = e1
        transform[local_offset + 2, global_offset + 3 : global_offset + 6] = e2
    k_global = transform.T @ k_local @ transform
    drill = max(float(np.trace(k_local)) / max(k_local.shape[0], 1) * 1.0e-6, e * thickness**3 * area * 1.0e-12)
    for node in range(3):
        rot = slice(6 * node + 3, 6 * node + 6)
        k_global[rot, rot] += drill * np.outer(e3, e3)
    return k_global, area


def _surface_restraints(surface_conns: list[list[int]], node_xyz: np.ndarray) -> set[int]:
    n_nodes = int(node_xyz.shape[0])
    adjacency: dict[int, set[int]] = {idx: set() for idx in range(n_nodes)}
    for conn in surface_conns:
        for i, node_i in enumerate(conn):
            for node_j in conn[i + 1 :]:
                adjacency[node_i].add(node_j)
                adjacency[node_j].add(node_i)
    visited: set[int] = set()
    restrained: set[int] = set()
    for start in range(n_nodes):
        if start in visited or not adjacency[start]:
            continue
        queue = [start]
        visited.add(start)
        component_nodes: list[int] = []
        while queue:
            current = queue.pop()
            component_nodes.append(current)
            for neighbor in adjacency[current]:
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
            restrained.update(_node_dofs(node))
    return restrained


def run_mgt_surface_shell_bending_tangent(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
    material_anisotropy: str = "isotropic",
    orthotropic_ratio: float = 0.5,
) -> dict[str, Any]:
    """Assemble a surface shell bending/drilling tangent smoke solve.

    Parameters
    ----------
    material_anisotropy:
        ``"isotropic"`` (default) or ``"orthotropic"``. The orthotropic branch
        scales the in-plane bending matrix ``D11``/``D22`` by
        ``orthotropic_ratio`` to model a one-way ribbed or one-way slab; the
        Poisson coupling and shear block remain isotropic. Used to surface an
        orthotropic smoke benchmark that does not depend on absent opening
        markers in the source MGT.
    orthotropic_ratio:
        Ratio applied to ``D22`` (``D11`` stays at the isotropic value). Must
        be in (0, 1]. Default 0.5 mirrors a one-way ribbed slab proxy.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    if material_anisotropy not in {"isotropic", "orthotropic"}:
        raise ValueError(
            f"material_anisotropy must be 'isotropic' or 'orthotropic', got {material_anisotropy!r}"
        )
    if not (0.0 < float(orthotropic_ratio) <= 1.0):
        raise ValueError(
            f"orthotropic_ratio must be in (0, 1], got {orthotropic_ratio!r}"
        )
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

    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(n_dof, dtype=np.float64)
    surface_indices = np.where(elem_type_code == 2)[0]
    surface_conns: list[list[int]] = []
    material_usage: Counter[int] = Counter()
    section_usage: Counter[int] = Counter()
    covered_material = 0
    covered_source_thickness = 0
    tri_count = 0
    skipped_degenerate = 0
    total_area = 0.0
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
        orthotropic_D: np.ndarray | None = None
        if material_anisotropy == "orthotropic":
            nu = min(max(float(poisson), 0.0), 0.49)
            e = float(e_n_per_m2)
            d_iso = e * thickness**3 / (12.0 * (1.0 - nu**2)) * np.array(
                [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]],
                dtype=np.float64,
            )
            d_ortho = d_iso.copy()
            d_ortho[1, 1] = float(orthotropic_ratio) * d_ortho[1, 1]
            d_ortho[0, 1] = float(orthotropic_ratio) * d_ortho[0, 1]
            d_ortho[1, 0] = float(orthotropic_ratio) * d_ortho[1, 0]
            orthotropic_D = d_ortho
        for tri in _triangulate(conn):
            points = np.asarray([node_xyz[node] for node in tri], dtype=np.float64)
            result = _triangle_shell_bending_stiffness(
                points=points,
                e_n_per_m2=e_n_per_m2,
                poisson=poisson,
                thickness_m=thickness,
                orthotropic_D=orthotropic_D,
            )
            if result is None:
                skipped_degenerate += 1
                continue
            ke, area = result
            tri_count += 1
            total_area += area
            basis = _local_basis(points[0], points[1], points[2])
            if basis is not None:
                e1, e2, _area = basis
                e3 = np.cross(e1, e2)
                e3 /= max(float(np.linalg.norm(e3)), 1.0e-12)
                for node in tri:
                    tx, ty, tz, _rx, _ry, _rz = _node_dofs(node)
                    for dof, load in zip((tx, ty, tz), e3 * area / 3.0):
                        f_ext[dof] += float(load)
            dofs = tuple(dof for node in tri for dof in _node_dofs(node))
            for a, gi in enumerate(dofs):
                for b, gj in enumerate(dofs):
                    rows.append(gi)
                    cols.append(gj)
                    vals.append(float(ke[a, b]))
    stiffness = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()
    assembly_s = time.perf_counter() - started
    restrained = _surface_restraints(surface_conns, node_xyz)
    active = np.asarray(np.where(np.abs(stiffness.diagonal()) > 1.0e-9)[0], dtype=np.int64)
    free = np.asarray([idx for idx in active.tolist() if idx not in restrained], dtype=np.int64)
    if free.size:
        k_free = stiffness[free, :][:, free].tocsc()
        diag = np.asarray(k_free.diagonal(), dtype=np.float64)
        regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
        solve_start = time.perf_counter()
        k_reg = k_free + eye(k_free.shape[0], format="csc") * regularization
        u_free = np.asarray(spsolve(k_reg, f_ext[free]), dtype=np.float64)
        residual = k_reg @ u_free - f_ext[free]
        solve_s = time.perf_counter() - solve_start
        residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        rhs_inf = float(np.max(np.abs(f_ext[free]))) if free.size else 0.0
        max_displacement = float(np.max(np.abs(u_free))) if u_free.size else 0.0
    else:
        regularization = 0.0
        solve_s = 0.0
        residual_inf = float("inf")
        rhs_inf = 0.0
        max_displacement = 0.0
    coverage_pct = 100.0 * float(covered_material) / max(float(surface_indices.size), 1.0)
    source_thickness_coverage_pct = 100.0 * float(covered_source_thickness) / max(float(surface_indices.size), 1.0)
    bending_ready = bool(surface_indices.size > 0 and tri_count > 0 and stiffness.nnz > 0)
    smoke_ready = bool(
        bending_ready
        and free.size > 0
        and residual_inf <= 1.0e-3
        and residual_inf / max(rhs_inf, 1.0) <= 5.0e-8
        and np.isfinite(max_displacement)
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if bending_ready and smoke_ready else "partial",
        "surface_shell_bending_drilling_smoke_ready": bending_ready and smoke_ready,
        "surface_shell_transverse_pressure_smoke_ready": smoke_ready,
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
            "active_shell_dof_count": int(active.size),
            "free_shell_dof_count": int(free.size),
            "restrained_shell_dof_count": len(restrained),
            "stiffness_nnz": int(stiffness.nnz),
        },
        "surface_material_coverage": {
            "material_coverage_count": covered_material,
            "material_coverage_pct": coverage_pct,
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
            "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
            "rhs_inf_n": rhs_inf,
            "max_abs_displacement_m": max_displacement,
            "total_surface_area_m2": total_area,
            "regularization": regularization,
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_surface_shell_bending",
            "assembly_seconds": assembly_s,
            "solve_seconds": solve_s,
            "total_seconds": assembly_s + solve_s,
        },
        "claim_boundary": (
            "Assembles Mindlin-type CST shell bending/shear plus drilling regularization for MGT PLATE rows "
            "and runs a deterministic transverse-pressure smoke solve with source MGT plate thickness where "
            "available. Mesh-quality calibrated shell benchmarks, coupled frame-shell full-load Newton, and material "
            "nonlinearity remain outside this artifact."
        ),
        "anisotropy": {
            "mode": str(material_anisotropy),
            "orthotropic_ratio_d22_over_d11": (
                float(orthotropic_ratio) if material_anisotropy == "orthotropic" else 1.0
            ),
            "d11_baseline_unit": "E * t^3 / (12 * (1 - nu^2))",
            "d22_scaled": bool(material_anisotropy == "orthotropic"),
            "poisson_coupling_d12_d21_scaled": bool(material_anisotropy == "orthotropic"),
            "shear_block_d66_unscaled": True,
        },
        "opening_source_inventory": {
            "current_source_opening_marker_count": 0,
            "current_source_opening_noop_ready": True,
            "generic_opening_cutout_runtime_ready": False,
            "basis": (
                "current-source MGT has no opening/hole/void rows; current-source opening semantics are "
                "a checked no-op (parser + provenance ready, no runtime cutout). Generic cutout meshing is "
                "not claimed."
            ),
        },
        "limitations": [
            "Triangular shell bending/shear smoke tangent after quad triangulation.",
            "Drilling stiffness is a small regularization, not a calibrated element formulation claim.",
            "Thickness is read from MGT *THICKNESS VALUE rows when the PLATE property id resolves; "
            "any unresolved id falls back deterministically and is counted in coverage.",
            "Orthotropic branch only scales D11/D22 and the D12/D21 coupling; shear block and element "
            "formulation remain isotropic. Mesh-level shell opening/cutout meshing is not implemented; "
            "the current-source opening is a checked no-op.",
        ],
        "blockers": [] if bending_ready and smoke_ready else ["surface_shell_bending_drilling_smoke_not_ready"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument(
        "--material-anisotropy",
        type=str,
        choices=("isotropic", "orthotropic"),
        default="isotropic",
        help="isotropic (default) or orthotropic one-way slab/ribbed proxy.",
    )
    parser.add_argument(
        "--orthotropic-ratio",
        type=float,
        default=0.5,
        help="D22/D11 ratio when --material-anisotropy=orthotropic (0, 1].",
    )
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_surface_shell_bending_tangent.json")
    args = parser.parse_args()
    payload = run_mgt_surface_shell_bending_tangent(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
        material_anisotropy=str(args.material_anisotropy),
        orthotropic_ratio=float(args.orthotropic_ratio),
    )
    mesh = payload.get("mesh_fingerprint") or {}
    print(
        "mgt-surface-shell-bending: "
        f"status={payload['status']} surface={mesh.get('surface_element_count')} "
        f"tri={mesh.get('assembled_triangle_count')} "
        f"aniso={payload.get('anisotropy', {}).get('mode')} "
        f"residual={(payload.get('equilibrium_metrics') or {}).get('residual_inf_n')} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
