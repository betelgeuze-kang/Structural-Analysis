#!/usr/bin/env python3
"""Run coupled frame-shell smoke solves with generated MGT story eccentricity loads."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from build_mgt_story_eccentricity_load_receipt import (
    _assign_story_weights,
    _case_specs,
    _cluster_story_levels,
)
from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_story_eccentricity,
)
from run_mgt_coupled_frame_shell_sparse_equilibrium import _assemble_surface_shell_6dof
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
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-coupled-frame-shell-story-eccentricity-equilibrium.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _story_load_vector(
    *,
    n_nodes: int,
    stories: list[dict[str, Any]],
    spec: dict[str, Any],
    notional_lateral_coefficient: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    vector = np.zeros(int(n_nodes) * DOF_PER_NODE, dtype=np.float64)
    total_lateral = 0.0
    total_abs_torsion = 0.0
    max_eccentricity = 0.0
    max_nodal_force = 0.0
    max_nodal_torsion = 0.0
    entry_count = 0
    for story in stories:
        nodes = [int(node) for node in story.get("node_indices") or []]
        node_count = max(len(nodes), 1)
        lateral = float(story.get("gravity_weight_n") or 0.0) * float(notional_lateral_coefficient)
        eccentricity = (
            float(story.get(str(spec["perpendicular_span_key"])) or 0.0)
            * float(spec["eccentricity_percent"])
            / 100.0
        )
        torsion = float(spec["sign"]) * lateral * eccentricity
        nodal_lateral = lateral / node_count
        nodal_torsion = torsion / node_count
        total_lateral += lateral
        total_abs_torsion += abs(torsion)
        max_eccentricity = max(max_eccentricity, abs(eccentricity))
        max_nodal_force = max(max_nodal_force, abs(nodal_lateral))
        max_nodal_torsion = max(max_nodal_torsion, abs(nodal_torsion))
        for node in nodes:
            dofs = _node_dofs(node)
            if str(spec["axis"]) == "X":
                vector[dofs[0]] += nodal_lateral
            else:
                vector[dofs[1]] += nodal_lateral
            vector[dofs[5]] += nodal_torsion
            entry_count += 2
    return vector, {
        "family": str(spec["family"]),
        "axis": str(spec["axis"]),
        "eccentricity_sign": float(spec["sign"]),
        "eccentricity_percent": float(spec["eccentricity_percent"]),
        "story_count": int(len(stories)),
        "equivalent_entry_count": int(entry_count),
        "total_lateral_force_n": float(total_lateral),
        "total_abs_torsional_moment_nm": float(total_abs_torsion),
        "max_eccentricity_m": float(max_eccentricity),
        "max_abs_nodal_lateral_force_n": float(max_nodal_force),
        "max_abs_nodal_torsion_nm": float(max_nodal_torsion),
        "load_vector_inf": float(np.max(np.abs(vector))) if vector.size else 0.0,
    }


def run_mgt_coupled_frame_shell_story_eccentricity_equilibrium(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
    notional_lateral_coefficient: float = 0.01,
    frame_gravity_load_scale: float = 0.01,
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
    if not mgt_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_missing"],
        }
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    props = load_mgt_section_material_properties(mgt_path)
    story_eccentricity = parse_mgt_story_eccentricity(text)
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
    frame_stiffness, frame_f, frame_meta = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
    )
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
    restrained, restraint_meta = _combined_restraints(
        n_nodes=int(node_xyz.shape[0]),
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        surface_conns=surface_conns,
    )
    stiffness = frame_stiffness + shell_stiffness
    stories = _cluster_story_levels(node_xyz)
    story_weight_meta = _assign_story_weights(
        stories=stories,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    base_load = frame_f * float(frame_gravity_load_scale) + shell_f
    case_rows: list[dict[str, Any]] = []
    all_ready = True
    max_relative_residual = 0.0
    max_abs_residual = 0.0
    max_translation = 0.0
    for case_index, spec in enumerate(_case_specs(story_eccentricity), start=1):
        story_load, load_meta = _story_load_vector(
            n_nodes=int(node_xyz.shape[0]),
            stories=stories,
            spec=spec,
            notional_lateral_coefficient=notional_lateral_coefficient,
        )
        solve_start = time.perf_counter()
        active, free, u_free, residual_inf, rhs_inf, regularization = _solve_active_system(
            stiffness=stiffness,
            f_ext=base_load + story_load,
            restrained=restrained,
        )
        solve_seconds = time.perf_counter() - solve_start
        u = np.zeros(int(node_xyz.shape[0]) * DOF_PER_NODE, dtype=np.float64)
        u[free] = np.asarray(u_free, dtype=np.float64)
        metrics = _translation_metrics(u, node_xyz)
        relative = residual_inf / max(rhs_inf, 1.0)
        ready = bool(
            free.size > 0
            and np.all(np.isfinite(u_free))
            and residual_inf <= 5.0e-2
            and relative <= 1.0e-6
            and metrics["max_translation_m"] <= 5.0
        )
        all_ready = bool(all_ready and ready)
        max_relative_residual = max(max_relative_residual, relative)
        max_abs_residual = max(max_abs_residual, residual_inf)
        max_translation = max(max_translation, float(metrics["max_translation_m"]))
        case_rows.append(
            {
                "case_index": int(case_index),
                "ready": ready,
                **load_meta,
                "active_dof_count": int(active.size),
                "free_dof_count": int(free.size),
                "residual_inf_n": float(residual_inf),
                "relative_residual_inf": float(relative),
                "rhs_inf_n": float(rhs_inf),
                "regularization": float(regularization),
                "max_abs_displacement_m": float(metrics["max_abs_displacement_m"]),
                "max_translation_m": float(metrics["max_translation_m"]),
                "max_drift_ratio_pct": float(metrics["max_drift_ratio_pct"]),
                "solve_seconds": solve_seconds,
            }
        )
    status = "ready" if all_ready and case_rows else "partial"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": status,
        "coupled_frame_shell_story_eccentricity_equilibrium_ready": bool(status == "ready"),
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "solve_scope": "full_mgt_line_frame_plus_source_thickness_shell_with_story_eccentricity_loads",
        "story_eccentricity": story_eccentricity,
        "generation_policy": {
            "mode": "notional_accidental_torsion_equivalent_nodal_loads_injected_into_coupled_frame_shell_solve",
            "notional_lateral_coefficient": float(notional_lateral_coefficient),
            "frame_gravity_load_scale": float(frame_gravity_load_scale),
            "enabled_case_count": int(len(case_rows)),
        },
        "mesh_fingerprint": {
            **frame_select_meta,
            **shell_meta,
            **restraint_meta,
            "node_count": int(node_xyz.shape[0]),
            "dof_count": int(node_xyz.shape[0]) * DOF_PER_NODE,
            "frame_stiffness_nnz": int(frame_stiffness.nnz),
            "shell_stiffness_nnz": int(shell_stiffness.nnz),
            "coupled_stiffness_nnz": int(stiffness.nnz),
            "story_count": int(len(stories)),
        },
        "story_weight_summary": story_weight_meta,
        "frame_section_material_coverage": frame_meta,
        "equilibrium_summary": {
            "case_count": int(len(case_rows)),
            "ready_case_count": sum(1 for row in case_rows if bool(row["ready"])),
            "max_residual_inf_n": float(max_abs_residual),
            "max_relative_residual_inf": float(max_relative_residual),
            "max_translation_m": float(max_translation),
        },
        "case_rows": case_rows,
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_coupled_frame_shell_story_eccentricity",
            "total_seconds": time.perf_counter() - started,
        },
        "support": {
            "story_eccentricity_load_generation_ready": bool(case_rows),
            "global_solver_consumes_story_eccentricity_loads": bool(status == "ready"),
            "coupled_frame_shell_story_eccentricity_solve_ready": bool(status == "ready"),
            "design_code_response_spectrum_ready": False,
            "full_load_nonlinear_newton_ready": False,
        },
        "claim_boundary": {
            "closed": [
                "generated MGT story eccentricity equivalent nodal loads are injected into a full coupled frame-shell sparse equilibrium solve",
                "all enabled seismic accidental torsion cases solve against the assembled frame plus source-thickness shell tangent",
            ],
            "not_closed": [
                "this remains a smoke-scale linear sparse equilibrium, not full-load nonlinear Newton",
                "response spectrum, wind-code eccentricity, diaphragm, opening, and calibrated shell formulation claims remain open",
            ],
        },
        "blockers": [] if status == "ready" else ["coupled_frame_shell_story_eccentricity_equilibrium_not_ready"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PRODUCTIZATION / "mgt_coupled_frame_shell_story_eccentricity_equilibrium.json",
    )
    parser.add_argument("--notional-lateral-coefficient", type=float, default=0.01)
    parser.add_argument("--frame-gravity-load-scale", type=float, default=0.01)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_coupled_frame_shell_story_eccentricity_equilibrium(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
        notional_lateral_coefficient=args.notional_lateral_coefficient,
        frame_gravity_load_scale=args.frame_gravity_load_scale,
    )
    summary = payload.get("equilibrium_summary") if isinstance(payload.get("equilibrium_summary"), dict) else {}
    print(
        "mgt-coupled-frame-shell-story-eccentricity: "
        f"status={payload['status']} cases={summary.get('ready_case_count')}/{summary.get('case_count')} "
        f"max_rel={summary.get('max_relative_residual_inf')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
