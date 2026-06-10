#!/usr/bin/env python3
"""Focused G9 smoke for host ILU + ROCm torch matvec GMRES."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_mgt_coupled_frame_surface_sparse_equilibrium import (
    _combined_restraints,
    _select_frame_elements as _select_coupled_frame_elements,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    _assemble_sparse_frame,
    _beam_end_offset_lookup,
    _element_angle_array_from_props,
)
from run_mgt_rocm_sparse_solver_probe import (
    DEFAULT_ROUNDTRIP,
    PRODUCTIZATION,
    _assemble_surface_shell_6dof,
    _regularized_active_system,
    _torch_rocm_ready,
    _torch_sparse_host_ilu_device_gmres_sweep,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-host-ilu-device-gmres-focused-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_host_ilu_device_gmres_focused_probe.json"


def _load_model(roundtrip_json: Path) -> dict[str, Any]:
    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = (
        load_mgt_section_material_properties(mgt_path)
        if mgt_path.is_file()
        else {"sections": {}, "materials": {}}
    )
    with np.load(roundtrip_json.with_suffix(".npz"), allow_pickle=False) as archive:
        return {
            "provenance": provenance,
            "props": props,
            "node_xyz": np.asarray(archive["node_xyz"], dtype=np.float64),
            "edge_index": np.asarray(archive["edge_index"], dtype=np.int64),
            "elem_id": np.asarray(archive["elem_id"], dtype=np.int64),
            "elem_type_code": np.asarray(archive["elem_type_code"], dtype=np.int32),
            "elem_section_id": np.asarray(archive["elem_section_id"], dtype=np.int32),
            "elem_material_id": np.asarray(archive["elem_material_id"], dtype=np.int32),
            "elem_angle_deg": (
                np.asarray(archive["elem_angle_deg"], dtype=np.float64)
                if "elem_angle_deg" in archive.files
                else _element_angle_array_from_props(props, archive["elem_id"])
            ),
            "conn_ptr": np.asarray(archive["elem_conn_ptr"], dtype=np.int64),
            "conn_idx": np.asarray(archive["elem_conn_idx"], dtype=np.int64),
        }


def _shell_system(model: dict[str, Any]) -> tuple[Any, np.ndarray, dict[str, Any]]:
    props = model["props"]
    shell_stiffness, shell_f, shell_meta, surface_conns = _assemble_surface_shell_6dof(
        node_xyz=model["node_xyz"],
        elem_type_code=model["elem_type_code"],
        elem_section_id=model["elem_section_id"],
        elem_material_id=model["elem_material_id"],
        conn_ptr=model["conn_ptr"],
        conn_idx=model["conn_idx"],
        material_props=props.get("materials") or {},
        plate_thickness_props=props.get("plate_thicknesses") or {},
    )
    shell_restrained, shell_restraint_meta = _combined_restraints(
        n_nodes=int(model["node_xyz"].shape[0]),
        node_xyz=model["node_xyz"],
        frame_elements=[],
        surface_conns=surface_conns,
    )
    _active, _free, k_ff, rhs, _solution, meta = _regularized_active_system(
        stiffness=shell_stiffness,
        f_ext=shell_f,
        restrained=shell_restrained,
    )
    fingerprint = {**shell_meta, **shell_restraint_meta, **meta}
    return k_ff, rhs, fingerprint


def _coupled_system(model: dict[str, Any]) -> tuple[Any, np.ndarray, dict[str, Any]]:
    props = model["props"]
    section_props = props.get("sections") or {}
    material_props = props.get("materials") or {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
    shell_stiffness, shell_f, shell_meta, surface_conns = _assemble_surface_shell_6dof(
        node_xyz=model["node_xyz"],
        elem_type_code=model["elem_type_code"],
        elem_section_id=model["elem_section_id"],
        elem_material_id=model["elem_material_id"],
        conn_ptr=model["conn_ptr"],
        conn_idx=model["conn_idx"],
        material_props=material_props,
        plate_thickness_props=props.get("plate_thicknesses") or {},
    )
    coupled_frame_elements, coupled_frame_meta = _select_coupled_frame_elements(
        node_xyz=model["node_xyz"],
        edge_index=model["edge_index"],
        elem_id=model["elem_id"],
        elem_type_code=model["elem_type_code"],
        elem_section_id=model["elem_section_id"],
        elem_material_id=model["elem_material_id"],
        elem_angle_deg=model["elem_angle_deg"],
        beam_end_offsets=beam_end_offsets,
    )
    coupled_frame_stiffness, coupled_frame_f, _ = _assemble_sparse_frame(
        elements=coupled_frame_elements,
        node_xyz=model["node_xyz"],
        section_props=section_props,
        material_props=material_props,
    )
    coupled_stiffness = coupled_frame_stiffness + shell_stiffness
    coupled_restrained, coupled_restraint_meta = _combined_restraints(
        n_nodes=int(model["node_xyz"].shape[0]),
        node_xyz=model["node_xyz"],
        frame_elements=coupled_frame_elements,
        surface_conns=surface_conns,
    )
    coupled_f = coupled_frame_f * 0.01 + shell_f
    _active, _free, k_ff, rhs, _solution, meta = _regularized_active_system(
        stiffness=coupled_stiffness,
        f_ext=coupled_f,
        restrained=coupled_restrained,
    )
    fingerprint = {**coupled_frame_meta, **shell_meta, **coupled_restraint_meta, **meta}
    return k_ff, rhs, fingerprint


def run_probe(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    output_json: Path = DEFAULT_OUT,
    matrix_family: str = "both",
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    rocm_ready, torch_info = _torch_rocm_ready()
    if not rocm_ready:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "torch_rocm": torch_info,
            "blockers": ["torch_rocm_runtime_not_ready"],
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload

    model = _load_model(roundtrip_json)
    rows: list[dict[str, Any]] = []
    families = ("shell", "coupled") if matrix_family == "both" else (matrix_family,)
    gates = {"shell": 1.0e-3, "coupled": 5.0e-2}
    rel_tol = {"shell": 5.0e-8, "coupled": 2.0e-8}
    for family in families:
        if family == "shell":
            k_ff, rhs, fingerprint = _shell_system(model)
        else:
            k_ff, rhs, fingerprint = _coupled_system(model)
        result = _torch_sparse_host_ilu_device_gmres_sweep(
            k_ff=k_ff,
            rhs=rhs,
            tolerance_abs=gates[family],
            tolerance_rel=rel_tol[family],
            max_iterations=4000,
            restart=50,
        )
        public = {key: value for key, value in result.items() if key != "_solution_np"}
        public["matrix_family"] = family
        public["mesh_fingerprint"] = fingerprint
        rows.append(public)

    ready = all(bool(row.get("converged")) for row in rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial",
        "ready": ready,
        "torch_rocm": torch_info,
        "probe_rows": rows,
        "claim_boundary": (
            "Focused host ILU + ROCm torch matvec GMRES probe. Closure requires both shell "
            "and coupled rows to pass full CSR residual replay against official G9 gates."
        ),
        "blockers": [] if ready else ["host_ilu_device_gmres_gate_not_met"],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--matrix-family", choices=("shell", "coupled", "both"), default="both")
    args = parser.parse_args()
    payload = run_probe(
        roundtrip_json=args.roundtrip_json,
        output_json=args.output_json,
        matrix_family=args.matrix_family,
    )
    print(json.dumps({"status": payload.get("status"), "ready": payload.get("ready")}, indent=2))
    for row in payload.get("probe_rows", []):
        print(
            row.get("matrix_family"),
            "residual_inf_n=",
            row.get("residual_inf_n"),
            "converged=",
            row.get("converged"),
            "solve_seconds=",
            row.get("solve_seconds"),
        )
    return 0 if payload.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
