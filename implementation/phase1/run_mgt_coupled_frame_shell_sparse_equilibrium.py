#!/usr/bin/env python3
"""Run a coupled frame + shell bending/drilling sparse equilibrium smoke solve for MGT."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_mgt_coupled_frame_surface_sparse_equilibrium import (
    _combined_restraints,
    _select_frame_elements,
    _solve_active_system,
    _translation_metrics,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    _assemble_sparse_frame,
    _beam_end_offset_lookup,
    _element_angle_array_from_props,
    _node_dofs,
)
from run_mgt_surface_membrane_tangent import (
    _local_basis,
    _source_or_fallback_thickness,
    _thickness_policy,
    _triangulate,
    _triangle_membrane_stiffness,
)
from run_mgt_surface_shell_bending_tangent import _triangle_shell_bending_stiffness
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-coupled-frame-shell-sparse-equilibrium.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _assemble_surface_shell_6dof(
    *,
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
    include_membrane: bool = False,
) -> tuple[Any, np.ndarray, dict[str, Any], list[list[int]]]:
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    f_ext = np.zeros(n_dof, dtype=np.float64)
    surface_indices = np.where(np.asarray(elem_type_code, dtype=np.int32) == 2)[0]
    surface_conns: list[list[int]] = []
    tri_count = 0
    membrane_tri_count = 0
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
        section_id = int(elem_section_id[elem_index])
        material_id = int(elem_material_id[elem_index])
        section_usage[section_id] += 1
        material_usage[material_id] += 1
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
            result = _triangle_shell_bending_stiffness(
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
            if include_membrane:
                membrane_result = _triangle_membrane_stiffness(
                    points=points,
                    e_n_per_m2=e_n_per_m2,
                    poisson=poisson,
                    thickness_m=thickness,
                )
                if membrane_result is not None:
                    ke_mem, _mem_area = membrane_result
                    trans_dofs = tuple(_node_dofs(node)[comp] for node in tri for comp in range(3))
                    for a, gi in enumerate(trans_dofs):
                        for b, gj in enumerate(trans_dofs):
                            rows.append(gi)
                            cols.append(gj)
                            vals.append(float(ke_mem[a, b]))
                    membrane_tri_count += 1
    stiffness = coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()
    material_coverage_pct = 100.0 * float(covered_material) / max(float(surface_indices.size), 1.0)
    source_thickness_coverage_pct = 100.0 * float(covered_source_thickness) / max(float(surface_indices.size), 1.0)
    meta = {
        "surface_element_count": int(surface_indices.size),
        "surface_quad_count": int(sum(1 for conn in surface_conns if len(conn) == 4)),
        "surface_tri_count": int(sum(1 for conn in surface_conns if len(conn) == 3)),
        "assembled_triangle_count": tri_count,
        "assembled_membrane_triangle_count": int(membrane_tri_count),
        "include_membrane": bool(include_membrane),
        "shell_tangent_model": (
            "mindlin_cst_bending_drilling_plus_cst_membrane"
            if include_membrane
            else "mindlin_cst_bending_drilling_only"
        ),
        "skipped_degenerate_triangle_count": skipped_degenerate,
        "surface_node_count": len({node for conn in surface_conns for node in conn}),
        "surface_material_coverage_pct": material_coverage_pct,
        "unique_surface_material_count": len(material_usage),
        "unique_surface_section_count": len(section_usage),
        "surface_total_area_m2": total_area,
        "surface_stiffness_nnz": int(stiffness.nnz),
        "thickness_policy": _thickness_policy(source_thickness_coverage_pct),
        "source_plate_thickness_coverage_count": covered_source_thickness,
        "source_plate_thickness_coverage_pct": source_thickness_coverage_pct,
        "source_thickness_table_count": len(plate_thickness_props),
        "thickness_min_m": float(min(thickness_values)) if thickness_values else 0.0,
        "thickness_max_m": float(max(thickness_values)) if thickness_values else 0.0,
    }
    return stiffness, f_ext, meta, surface_conns


def run_mgt_coupled_frame_shell_sparse_equilibrium(
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
    plate_thickness_props = props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
    roundtrip = _load_json(roundtrip_json)
    started = time.perf_counter()
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
        elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
        elem_angle_deg = (
            np.asarray(archive["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in archive.files
            else _element_angle_array_from_props(props, elem_id)
        )
        conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)
    frame_elements, frame_select_meta = _select_frame_elements(
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        elem_angle_deg=elem_angle_deg,
        beam_end_offsets=beam_end_offsets,
    )
    select_s = time.perf_counter() - started
    frame_start = time.perf_counter()
    frame_stiffness, frame_f, frame_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
    )
    frame_s = time.perf_counter() - frame_start
    surface_start = time.perf_counter()
    shell_stiffness, shell_f, shell_meta, surface_conns = _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    shell_s = time.perf_counter() - surface_start
    restrained, restraint_meta = _combined_restraints(
        n_nodes=int(node_xyz.shape[0]),
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        surface_conns=surface_conns,
    )
    stiffness = frame_stiffness + shell_stiffness
    frame_gravity_load_scale = 0.01
    f_ext = frame_f * frame_gravity_load_scale + shell_f
    solve_start = time.perf_counter()
    active, free, u_free, residual_inf, rhs_inf, regularization = _solve_active_system(
        stiffness=stiffness,
        f_ext=f_ext,
        restrained=restrained,
    )
    solve_s = time.perf_counter() - solve_start
    u = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
    u[free] = np.asarray(u_free, dtype=np.float64)
    metrics = _translation_metrics(u, node_xyz)
    ready = bool(
        frame_select_meta["line_elements_solved"] > 0
        and shell_meta["surface_element_count"] > 0
        and shell_meta["assembled_triangle_count"] > 0
        and free.size > 0
        and np.all(np.isfinite(u_free))
        and residual_inf <= 5.0e-2
        and residual_inf / max(rhs_inf, 1.0) <= 2.0e-8
        and metrics["max_translation_m"] <= 5.0
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial",
        "coupled_frame_shell_sparse_equilibrium_ready": ready,
        "coupled_frame_shell_nonlinear_equilibrium": False,
        "surface_shell_bending_drilling_coupled_ready": ready,
        "surface_shell_full_bending_tangent_ready": False,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "solve_scope": "full_mgt_line_frame_plus_source_thickness_surface_shell_bending_sparse_global_equilibrium",
        "claim_boundary": (
            "Assembles line/frame and PLATE shell bending/shear/drilling stiffness into one 6-DOF node space "
            "and runs a combined sparse equilibrium smoke solve with source MGT plate thickness. This is "
            "coupled frame-shell tangent evidence, not calibrated shell formulation, material nonlinear, "
            "or full-load Newton closure."
        ),
        "mesh_fingerprint": {
            **frame_select_meta,
            **shell_meta,
            **restraint_meta,
            "node_count": int(node_xyz.shape[0]),
            "dof_count": int(node_xyz.shape[0]) * DOF_PER_NODE,
            "active_dof_count": int(active.size),
            "free_dof_count": int(free.size),
            "frame_stiffness_nnz": int(frame_stiffness.nnz),
            "shell_stiffness_nnz": int(shell_stiffness.nnz),
            "coupled_stiffness_nnz": int(stiffness.nnz),
        },
        "frame_section_material_coverage": frame_meta,
        "beam_end_offset_support": {
            "typed_mgt_offset_parser_ready": bool(beam_end_offsets),
            "global_beam_end_offset_elements_available": int(len(beam_end_offsets)),
            "rigid_end_offset_transform_applied": bool(
                int(frame_select_meta.get("beam_end_offset_applied_element_count") or 0) > 0
            ),
            "applied_element_count": int(frame_select_meta.get("beam_end_offset_applied_element_count") or 0),
            "max_abs_offset_m": float(frame_select_meta.get("beam_end_offset_max_abs_m") or 0.0),
            "load_eccentricity_moments_applied": bool(
                int(frame_select_meta.get("beam_end_offset_applied_element_count") or 0) > 0
            ),
        },
        "surface_material_coverage": {
            key: value
            for key, value in shell_meta.items()
            if key
            in {
                "surface_material_coverage_pct",
                "unique_surface_material_count",
                "unique_surface_section_count",
                "thickness_policy",
                "source_plate_thickness_coverage_count",
                "source_plate_thickness_coverage_pct",
                "source_thickness_table_count",
                "thickness_min_m",
                "thickness_max_m",
            }
        },
        "equilibrium_metrics": {
            "residual_inf_n": residual_inf,
            "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
            "rhs_inf_n": rhs_inf,
            "regularization": regularization,
            "max_abs_displacement_m": metrics["max_abs_displacement_m"],
            "max_translation_m": metrics["max_translation_m"],
            "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
            "frame_total_gravity_kn": float(frame_meta["total_gravity_n"]) / 1000.0,
            "frame_gravity_load_scale": frame_gravity_load_scale,
            "surface_total_area_m2": float(shell_meta["surface_total_area_m2"]),
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_coupled_frame_shell",
            "selection_seconds": select_s,
            "frame_assembly_seconds": frame_s,
            "shell_assembly_seconds": shell_s,
            "solve_seconds": solve_s,
            "total_seconds": select_s + frame_s + shell_s + solve_s,
        },
        "limitations": [
            "Surface contribution is triangular Mindlin-type CST bending/shear with drilling regularization.",
            "Frame-shell coupling is same-node shell tangent coupling only; offsets, diaphragms, openings, local axis calibration, and full pressure/load-combo semantics remain open.",
            "Material nonlinearity and full-load Newton are not closed by this artifact.",
        ],
        "blockers": [] if ready else ["coupled_frame_shell_sparse_equilibrium_not_ready"],
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
        "--output-json",
        type=Path,
        default=PRODUCTIZATION / "mgt_coupled_frame_shell_sparse_equilibrium.json",
    )
    args = parser.parse_args()
    payload = run_mgt_coupled_frame_shell_sparse_equilibrium(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
    )
    mesh = payload.get("mesh_fingerprint") or {}
    print(
        "mgt-coupled-frame-shell: "
        f"status={payload['status']} line={mesh.get('line_elements_solved')} "
        f"surface={mesh.get('surface_element_count')} residual="
        f"{(payload.get('equilibrium_metrics') or {}).get('residual_inf_n')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
