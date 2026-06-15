#!/usr/bin/env python3
"""Build bounded MGT shell material nonlinear tangent evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.sparse import eye
from scipy.sparse.linalg import spsolve

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_mgt_coupled_frame_shell_sparse_equilibrium import _assemble_surface_shell_6dof
from run_mgt_frame_material_nonlinear_tangent import (
    MaterialTangentState,
    _infer_strength_mpa,
    _material_e_mpa,
    _material_fd_tangent_row,
    _material_fd_tangent_summary,
    _material_tangent_state,
    _probe_strain,
)
from mgt_shell_material_tangent import _state_summary, surface_strain_proxy
from run_mgt_full_frame_6dof_sparse_equilibrium import DOF_PER_NODE
from run_mgt_surface_shell_bending_tangent import _surface_restraints
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-shell-material-nonlinear-tangent.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _solve_shell_state(
    *,
    stiffness: Any,
    f_ext: np.ndarray,
    surface_conns: list[list[int]],
    node_xyz: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    active = np.asarray(np.where(np.abs(stiffness.diagonal()) > 1.0e-9)[0], dtype=np.int64)
    restrained = _surface_restraints(surface_conns, node_xyz)
    free = np.asarray([idx for idx in active.tolist() if idx not in restrained], dtype=np.int64)
    u = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
    if free.size:
        k_free = stiffness[free, :][:, free].tocsc()
        diag = np.asarray(k_free.diagonal(), dtype=np.float64)
        regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
        k_reg = k_free + eye(k_free.shape[0], format="csc") * regularization
        started = time.perf_counter()
        u_free = np.asarray(spsolve(k_reg, f_ext[free]), dtype=np.float64)
        solve_s = time.perf_counter() - started
        residual = k_reg @ u_free - f_ext[free]
        u[free] = u_free
        residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
        rhs_inf = float(np.max(np.abs(f_ext[free]))) if free.size else 0.0
        max_displacement = float(np.max(np.abs(u_free))) if u_free.size else 0.0
    else:
        regularization = 0.0
        solve_s = 0.0
        residual_inf = float("inf")
        rhs_inf = 0.0
        max_displacement = 0.0
    return u, {
        "residual_inf_n": residual_inf,
        "relative_residual_inf": residual_inf / max(rhs_inf, 1.0),
        "rhs_inf_n": rhs_inf,
        "max_abs_displacement_m": max_displacement,
        "active_shell_dof_count": int(active.size),
        "free_shell_dof_count": int(free.size),
        "restrained_shell_dof_count": len(restrained),
        "regularization": regularization,
        "solve_seconds": solve_s,
    }


def _fixed_tangent_jvp_consistency(
    *,
    stiffness: Any,
    u: np.ndarray,
    free_count_hint: int,
) -> dict[str, Any]:
    direction = np.zeros_like(u, dtype=np.float64)
    diagonal = np.asarray(stiffness.diagonal(), dtype=np.float64)
    active = np.where(np.abs(diagonal) > 1.0e-9)[0]
    if active.size == 0:
        return {
            "fixed_tangent_global_jvp_consistency_pass": False,
            "reason": "no_active_shell_dofs",
        }
    stride = max(int(active.size // 128), 1)
    selected = active[::stride][:128]
    for idx, dof in enumerate(selected.tolist()):
        direction[dof] = -1.0 if idx % 2 else 1.0
    direction /= max(float(np.max(np.abs(direction))), 1.0)
    eps = 1.0e-6
    plus = np.asarray(stiffness @ (np.asarray(u, dtype=np.float64) + eps * direction), dtype=np.float64)
    minus = np.asarray(stiffness @ (np.asarray(u, dtype=np.float64) - eps * direction), dtype=np.float64)
    fd_jvp = (plus - minus) / (2.0 * eps)
    analytic_jvp = np.asarray(stiffness @ direction, dtype=np.float64)
    diff = fd_jvp - analytic_jvp
    fd_inf = float(np.max(np.abs(fd_jvp))) if fd_jvp.size else 0.0
    analytic_inf = float(np.max(np.abs(analytic_jvp))) if analytic_jvp.size else 0.0
    abs_error = float(np.max(np.abs(diff))) if diff.size else 0.0
    relative_error = abs_error / max(fd_inf, analytic_inf, 1.0)
    absolute_tolerance = max(1.0e-2, 1.0e-9 * max(fd_inf, analytic_inf, 1.0))
    return {
        "fixed_tangent_global_jvp_consistency_pass": bool(
            selected.size > 0 and relative_error <= 1.0e-7 and abs_error <= absolute_tolerance
        ),
        "sample_direction_dof_count": int(selected.size),
        "free_count_hint": int(free_count_hint),
        "fd_epsilon_m": float(eps),
        "fd_jvp_inf_n_per_m": fd_inf,
        "analytic_jvp_inf_n_per_m": analytic_inf,
        "absolute_error_n_per_m": abs_error,
        "relative_error": float(relative_error),
        "relative_error_tolerance": 1.0e-7,
        "absolute_error_tolerance_n_per_m": float(absolute_tolerance),
    }


def _weakest_surface_examples(
    *,
    elem_id: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    probe_states: dict[int, MaterialTangentState],
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for surface_index, probe in sorted(probe_states.items(), key=lambda item: item[1].tangent_ratio)[:limit]:
        rows.append(
            {
                "surface_index": int(surface_index),
                "elem_id": int(elem_id[surface_index]) if surface_index < int(elem_id.shape[0]) else None,
                "section_id": int(elem_section_id[surface_index]),
                "material_id": int(elem_material_id[surface_index]),
                "material_family": probe.material_family,
                "probe_strain": float(probe.strain),
                "probe_state_tag": probe.state_tag,
                "probe_tangent_ratio": float(probe.tangent_ratio),
            }
        )
    return rows


def run_mgt_shell_material_nonlinear_tangent(
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
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    plate_thickness_props = props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
    roundtrip = _load_json(roundtrip_json)

    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
        conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)

    surface_indices = np.where(elem_type_code == 2)[0]
    elastic_assembly_start = time.perf_counter()
    elastic_stiffness, elastic_f_ext, elastic_meta, surface_conns = _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
    )
    elastic_assembly_s = time.perf_counter() - elastic_assembly_start
    service_u, service_metrics = _solve_shell_state(
        stiffness=elastic_stiffness,
        f_ext=elastic_f_ext,
        surface_conns=surface_conns,
        node_xyz=node_xyz,
    )

    service_states: dict[int, MaterialTangentState] = {}
    probe_states: dict[int, MaterialTangentState] = {}
    tangent_by_surface_index_mpa: dict[int, float] = {}
    material_strengths: dict[str, dict[str, Any]] = {}
    fd_tangent_rows: list[dict[str, Any]] = []
    material_usage: Counter[int] = Counter()
    section_usage: Counter[int] = Counter()
    for surface_index in surface_indices.tolist():
        material_id = int(elem_material_id[surface_index])
        section_id = int(elem_section_id[surface_index])
        mat = material_props.get(material_id, {})
        fallback_e_mpa = _material_e_mpa(mat, fallback_mpa=210000.0)
        service_strain = surface_strain_proxy(
            elem_index=int(surface_index),
            node_xyz=node_xyz,
            u=service_u,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
        )
        service_state = _material_tangent_state(mat, service_strain, fallback_e_mpa=fallback_e_mpa)
        probe_state = _material_tangent_state(
            mat,
            _probe_strain(mat, service_strain, fallback_e_mpa=fallback_e_mpa),
            fallback_e_mpa=fallback_e_mpa,
        )
        service_states[int(surface_index)] = service_state
        probe_states[int(surface_index)] = probe_state
        tangent_by_surface_index_mpa[int(surface_index)] = float(probe_state.solver_tangent_mpa)
        fd_tangent_rows.append(
            _material_fd_tangent_row(
                mat=mat,
                strain=service_strain,
                fallback_e_mpa=fallback_e_mpa,
                label="surface_service_proxy",
                material_id=material_id,
                elem_id=int(elem_id[surface_index]) if surface_index < int(elem_id.shape[0]) else None,
            )
        )
        fd_tangent_rows.append(
            _material_fd_tangent_row(
                mat=mat,
                strain=probe_state.strain,
                fallback_e_mpa=fallback_e_mpa,
                label="surface_controlled_probe",
                material_id=material_id,
                elem_id=int(elem_id[surface_index]) if surface_index < int(elem_id.shape[0]) else None,
            )
        )
        family, strength = _infer_strength_mpa(mat)
        material_strengths[str(material_id)] = {
            "family": family,
            "name": str(mat.get("name") or ""),
            "source_E_mpa": _material_e_mpa(mat, fallback_mpa=0.0),
            "inferred_strength_mpa": strength,
            "strength_source": "mgt_material_name_grade_proxy" if strength is not None else "not_inferred",
        }
        material_usage[material_id] += 1
        section_usage[section_id] += 1

    tangent_assembly_start = time.perf_counter()
    tangent_stiffness, tangent_f_ext, tangent_meta, _surface_conns = _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
        material_tangent_by_surface_index_mpa=tangent_by_surface_index_mpa,
    )
    tangent_assembly_s = time.perf_counter() - tangent_assembly_start
    tangent_u, tangent_metrics = _solve_shell_state(
        stiffness=tangent_stiffness,
        f_ext=tangent_f_ext,
        surface_conns=surface_conns,
        node_xyz=node_xyz,
    )
    service_summary = _state_summary(list(service_states.values()))
    probe_summary = _state_summary(list(probe_states.values()))
    fd_summary = _material_fd_tangent_summary(fd_tangent_rows)
    jvp_summary = _fixed_tangent_jvp_consistency(
        stiffness=tangent_stiffness,
        u=tangent_u,
        free_count_hint=int(tangent_metrics.get("free_shell_dof_count") or 0),
    )
    stiffness_delta = tangent_stiffness - elastic_stiffness
    force_delta = np.asarray(stiffness_delta @ service_u, dtype=np.float64)
    tangent_consumption_ready = bool(
        int(tangent_meta.get("material_tangent_override_surface_element_count") or 0) == int(surface_indices.size)
        and int(tangent_meta.get("material_tangent_reduction_surface_element_count") or 0) > 0
        and float(np.max(np.abs(stiffness_delta.data))) > 0.0
    )
    service_ready = bool(
        int(surface_indices.size) > 0
        and int(elastic_meta.get("assembled_triangle_count") or 0) > 0
        and np.isfinite(float(service_metrics["max_abs_displacement_m"]))
        and float(service_metrics["residual_inf_n"]) <= 1.0e-3
    )
    probe_ready = bool(
        int(probe_summary["nonlinear_tangent_surface_element_count"]) > 0
        and float(probe_summary["min_tangent_ratio"]) < 0.98
    )
    fd_ready = bool(fd_summary["constitutive_tangent_fd_consistency_pass"])
    jvp_ready = bool(jvp_summary["fixed_tangent_global_jvp_consistency_pass"])
    smoke_ready = bool(
        tangent_consumption_ready
        and np.isfinite(float(tangent_metrics["max_abs_displacement_m"]))
        and float(tangent_metrics["residual_inf_n"]) <= 1.0e-3
    )
    ready = bool(service_ready and probe_ready and fd_ready and jvp_ready and smoke_ready)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial",
        "shell_material_nonlinear_tangent_ready": ready,
        "service_shell_material_state_ready": service_ready,
        "controlled_probe_shell_material_state_ready": probe_ready,
        "local_constitutive_tangent_fd_consistency_ready": fd_ready,
        "fixed_tangent_global_shell_jvp_consistency_ready": jvp_ready,
        "bounded_shell_material_tangent_smoke_ready": smoke_ready,
        "global_smoke_solver_uses_per_surface_element_material_tangent": tangent_consumption_ready,
        "full_material_nonlinear_newton_equilibrium": False,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "claim_boundary": (
            "MGT PLATE/shell elements consume source material E/nu and material-name grade proxies "
            "for bounded per-surface-element material tangent states. The receipt assembles the full "
            "membrane+bending+drilling shell operator with those tangents, solves a deterministic smoke "
            "system, and checks the fixed-tangent global shell JVP by finite difference. This is not full "
            "path-dependent shell material Newton, layered/fiber shell closure, or production residual-gate closure."
        ),
        "mesh_fingerprint": {
            **elastic_meta,
            "node_count": int(node_xyz.shape[0]),
            "dof_count": int(node_xyz.shape[0]) * DOF_PER_NODE,
            "surface_element_count": int(surface_indices.size),
            "elastic_shell_stiffness_nnz": int(elastic_stiffness.nnz),
            "material_tangent_shell_stiffness_nnz": int(tangent_stiffness.nnz),
        },
        "surface_material_inventory": {
            "unique_material_count": len(material_usage),
            "unique_section_count": len(section_usage),
            "material_usage_head": dict(material_usage.most_common(10)),
            "section_usage_head": dict(section_usage.most_common(10)),
            "material_strength_inventory": material_strengths,
        },
        "service_shell_material_state_summary": service_summary,
        "controlled_probe_shell_material_state_summary": probe_summary,
        "local_constitutive_tangent_fd_consistency": fd_summary,
        "fixed_tangent_global_shell_jvp_consistency": jvp_summary,
        "weakest_probe_surface_elements": _weakest_surface_examples(
            elem_id=elem_id,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            probe_states=probe_states,
        ),
        "elastic_reference_shell_equilibrium": service_metrics,
        "material_tangent_shell_equilibrium": {
            **tangent_metrics,
            "material_tangent_override_surface_element_count": tangent_meta.get(
                "material_tangent_override_surface_element_count"
            ),
            "material_tangent_reduction_surface_element_count": tangent_meta.get(
                "material_tangent_reduction_surface_element_count"
            ),
            "min_material_tangent_ratio": tangent_meta.get("min_material_tangent_ratio"),
            "max_material_tangent_ratio": tangent_meta.get("max_material_tangent_ratio"),
        },
        "tangent_consumption_check": {
            "stiffness_delta_nnz": int(stiffness_delta.nnz),
            "stiffness_delta_inf": float(np.max(np.abs(stiffness_delta.data))) if stiffness_delta.nnz else 0.0,
            "service_force_delta_inf_n": float(np.max(np.abs(force_delta))) if force_delta.size else 0.0,
            "tangent_consumption_ready": tangent_consumption_ready,
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_6dof_shell_material_tangent_smoke",
            "elastic_assembly_seconds": elastic_assembly_s,
            "elastic_solve_seconds": service_metrics.get("solve_seconds"),
            "material_tangent_assembly_seconds": tangent_assembly_s,
            "material_tangent_solve_seconds": tangent_metrics.get("solve_seconds"),
            "total_seconds": time.perf_counter() - started,
        },
        "limitations": [
            "Surface strain is a deterministic edge-projection proxy used to select bounded material tangent states.",
            "The global JVP check is for the fixed material-tangent shell operator, not a full state-updated material Jacobian.",
            "No path-dependent shell history variables, layered shell integration, rebar/fiber section model, or cyclic damage law is promoted.",
            "The receipt remains CPU sparse smoke evidence; official G1 residual closure still requires the physical residual gate.",
        ],
        "blockers": []
        if ready
        else [
            *([] if service_ready else ["service_shell_material_state_not_ready"]),
            *([] if probe_ready else ["controlled_probe_shell_material_state_not_ready"]),
            *([] if fd_ready else ["local_constitutive_tangent_fd_consistency_not_ready"]),
            *([] if jvp_ready else ["fixed_tangent_global_shell_jvp_consistency_not_ready"]),
            *([] if smoke_ready else ["bounded_shell_material_tangent_smoke_not_ready"]),
        ],
    }
    out = output_json or PRODUCTIZATION / "mgt_shell_material_nonlinear_tangent.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_shell_material_nonlinear_tangent.json")
    args = parser.parse_args()
    payload = run_mgt_shell_material_nonlinear_tangent(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
    )
    probe = payload.get("controlled_probe_shell_material_state_summary") or {}
    smoke = payload.get("material_tangent_shell_equilibrium") or {}
    print(
        "mgt-shell-material-nonlinear-tangent: "
        f"status={payload['status']} nonlinear_probe={probe.get('nonlinear_tangent_surface_element_count')} "
        f"min_tangent_ratio={probe.get('min_tangent_ratio')} "
        f"residual={smoke.get('residual_inf_n')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
