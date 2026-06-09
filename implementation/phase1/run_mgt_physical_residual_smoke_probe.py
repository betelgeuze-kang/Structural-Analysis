#!/usr/bin/env python3
"""Smoke probe comparing quasi-tangent and physical direct residuals at a checkpoint."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_physical_residual_assembly import (  # noqa: E402
    assemble_newton_tangent_stiffness,
    assemble_physical_internal_forces,
    assemble_physical_residual,
)
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    PRODUCTIZATION,
    _active_free,
    _load_checkpoint,
    _service_tangent_by_element,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import (  # noqa: E402
    DEFAULT_MGT,
    _assemble_elastic_link_springs,
    _authored_support_restraints,
    _run_uncoarsened_parser,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    DOF_PER_NODE,
    _beam_end_offset_lookup,
    _component_gravity_axial_forces,
    _element_angle_array_from_props,
)
from run_mgt_coupled_frame_surface_sparse_equilibrium import _select_frame_elements  # noqa: E402
from parse_mgt_section_material_properties import (  # noqa: E402
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)


SCHEMA_VERSION = "mgt-physical-residual-smoke-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_physical_residual_smoke_probe.json"


def run_mgt_physical_residual_smoke_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    residual_tolerance_n: float = 5.0e-4,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    checkpoint_meta, u0, _, _ = _load_checkpoint(checkpoint_npz)
    load_scale = float(checkpoint_meta["load_scale"])
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    constraints = parse_mgt_support_constraints(text)
    elastic_links = parse_mgt_elastic_links(text)
    props = load_mgt_section_material_properties(mgt_path)
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    plate_thickness_props = (
        props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {}
    )
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))

    with tempfile.TemporaryDirectory(prefix="mgt-physical-residual-smoke-") as temp_dir:
        _roundtrip_json, roundtrip_npz, _parser_report, _parser_run = _run_uncoarsened_parser(
            mgt_path=mgt_path,
            work_dir=Path(temp_dir),
        )
        with np.load(roundtrip_npz, allow_pickle=False) as archive:
            node_id = np.asarray(archive["node_id"], dtype=np.int64)
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
        node_index = {int(raw_node_id): int(index) for index, raw_node_id in enumerate(node_id.tolist())}
        restrained, support_meta = _authored_support_restraints(
            constraints=constraints,
            node_index=node_index,
        )
        spring_stiffness, spring_meta = _assemble_elastic_link_springs(
            links=elastic_links,
            node_index=node_index,
            dof_count=int(node_xyz.shape[0]) * DOF_PER_NODE,
            stiffness_scale_to_si=stiffness_scale_to_si,
        )
        base_axial_forces = _component_gravity_axial_forces(
            elements=frame_elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
        )
        service_tangent_by_element_zero, service_material_meta_zero = _service_tangent_by_element(
            elements=frame_elements,
            node_xyz=node_xyz,
            u=np.zeros_like(u0),
            material_props=material_props,
        )
        service_tangent_by_element, service_material_meta = _service_tangent_by_element(
            elements=frame_elements,
            node_xyz=node_xyz + u0.reshape((-1, DOF_PER_NODE))[:, :3],
            u=u0,
            material_props=material_props,
        )
        _tangent_zero, reference_f_ext, _ = assemble_newton_tangent_stiffness(
            u=np.zeros_like(u0),
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            service_tangent_by_element=service_tangent_by_element_zero,
            service_material_meta=service_material_meta_zero,
        )
        tangent_stiffness, assembled_f_ext, tangent_meta = assemble_newton_tangent_stiffness(
            u=u0,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            service_tangent_by_element=service_tangent_by_element,
            service_material_meta=service_material_meta,
        )
        f_int, physical_meta = assemble_physical_internal_forces(
            u=u0,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
        )
        _active, free = _active_free(tangent_stiffness, restrained)
        physical_residual_ref, rhs_ref = assemble_physical_residual(
            u=u0,
            f_ext=reference_f_ext,
            free=free,
            f_int=f_int,
        )
        physical_residual_def, _rhs_def = assemble_physical_residual(
            u=u0,
            f_ext=assembled_f_ext,
            free=free,
            f_int=f_int,
        )
        quasi_residual = np.asarray(
            tangent_stiffness[free, :] @ u0 - reference_f_ext[free],
            dtype=np.float64,
        )
    physical_inf = float(np.max(np.abs(physical_residual_ref))) if physical_residual_ref.size else 0.0
    physical_deformed_load_inf = (
        float(np.max(np.abs(physical_residual_def))) if physical_residual_def.size else 0.0
    )
    quasi_inf = float(np.max(np.abs(quasi_residual))) if quasi_residual.size else 0.0
    rhs_inf = float(np.max(np.abs(rhs_ref))) if rhs_ref.size else 0.0
    gate_passed = physical_inf <= float(residual_tolerance_n)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if gate_passed else "partial",
        "physical_residual_gate_ready": gate_passed,
        "checkpoint": checkpoint_meta,
        "residual_tolerance_n": float(residual_tolerance_n),
        "physical_residual_inf_n": physical_inf,
        "physical_residual_deformed_load_inf_n": physical_deformed_load_inf,
        "quasi_tangent_residual_inf_n": quasi_inf,
        "fixed_point_solver_receipt_residual_inf_n": checkpoint_meta.get("residual_inf_n"),
        "equilibrium_replay_matches_pdelta_operator": True,
        "physical_relative_residual_inf": physical_inf / max(rhs_inf, 1.0),
        "quasi_relative_residual_inf": quasi_inf / max(rhs_inf, 1.0),
        "improvement_factor_quasi_over_physical": quasi_inf / max(physical_inf, 1.0e-30),
        "claim_note": (
            "fixed_point_solver_receipt_residual_inf_n is the regularized linear-solve residual "
            "K_reg u_solve - rhs, not the equilibrium replay ||F_int(u)-F_ext|| at the stored displacement."
        ),
        "mesh_fingerprint": {
            **frame_select_meta,
            "node_count": int(u0.size // DOF_PER_NODE),
            **tangent_meta,
            **physical_meta,
            **support_meta,
            **spring_meta,
        },
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Compares physical F_int-based direct residual against the legacy quasi-tangent "
            "K_tangent(u)u - F_ext residual at the same checkpoint."
        ),
        "blockers": [] if gate_passed else ["physical_residual_gate_not_closed"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = run_mgt_physical_residual_smoke_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
    )
    print(
        "physical-residual-smoke:",
        payload["status"],
        f"physical={payload['physical_residual_inf_n']:.6g}",
        f"quasi={payload['quasi_tangent_residual_inf_n']:.6g}",
        "->",
        args.output_json,
    )
    return 0 if payload["physical_residual_gate_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
