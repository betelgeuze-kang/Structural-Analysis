#!/usr/bin/env python3
"""Build the physical direct-residual assembler used by equilibrium Newton."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from typing import Any, Callable

import numpy as np

_PHASE1 = Path(__file__).resolve().parent
if str(_PHASE1) not in sys.path:
    sys.path.insert(0, str(_PHASE1))

from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_elastic_links,
    parse_mgt_support_constraints,
)
from run_mgt_coupled_frame_surface_sparse_equilibrium import _select_frame_elements
from run_mgt_direct_residual_newton_probe import _load_checkpoint
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE,
    _beam_end_offset_lookup,
    _component_gravity_axial_forces,
    _element_angle_array_from_props,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import (
    _assemble_elastic_link_springs,
    _authored_support_restraints,
    _run_uncoarsened_parser,
)
from mgt_equilibrium_step_assembly import build_equilibrium_step_assembler


def build_direct_residual_assembler(
    *,
    mgt_path: Path,
    checkpoint_npz: Path,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
    shell_pressure_load_path_policy: str = "all_components",
) -> tuple[
    Callable[..., tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]],
    dict[str, Any],
]:
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

    temp_dir = tempfile.TemporaryDirectory(prefix="mgt-equilibrium-newton-setup-")
    _roundtrip_json, roundtrip_npz, parser_report, parser_run = _run_uncoarsened_parser(
        mgt_path=mgt_path,
        work_dir=Path(temp_dir.name),
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
    assemble_with_frozen_external_load, step_meta = build_equilibrium_step_assembler(
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
        restrained=restrained,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )

    setup_meta = {
        "checkpoint": checkpoint_meta,
        "u0": u0,
        "load_scale": load_scale,
        "reference_f_ext_inf_n": step_meta.get("reference_f_ext_inf_n"),
        "frame_select_meta": frame_select_meta,
        "support_meta": support_meta,
        "spring_meta": spring_meta,
        "shell_pressure_load_path_policy": str(shell_pressure_load_path_policy),
        "parser_report_contract_pass": bool(parser_report.get("contract_pass")),
        "parser_run": parser_run,
        "equilibrium_step_meta": step_meta,
        "frame_gravity_load_scale": float(frame_gravity_load_scale),
        "_node_xyz": node_xyz,
        "_node_id": node_id,
        "_elem_id": elem_id,
        "_elem_type_code": elem_type_code,
        "_elem_section_id": elem_section_id,
        "_elem_material_id": elem_material_id,
        "_conn_ptr": conn_ptr,
        "_conn_idx": conn_idx,
        "_frame_elements": frame_elements,
        "_restrained_dofs": np.asarray(sorted(int(dof) for dof in restrained), dtype=np.int64),
        "_section_props": section_props,
        "_material_props": material_props,
        "_plate_thickness_props": plate_thickness_props,
        "_base_axial_forces": base_axial_forces,
        "_spring_stiffness": spring_stiffness,
        "_temp_dir": temp_dir,
    }
    return assemble_with_frozen_external_load, setup_meta
