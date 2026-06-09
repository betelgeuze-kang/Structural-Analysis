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
from run_mgt_direct_residual_newton_probe import (
    _active_free,
    _load_checkpoint,
    _service_tangent_by_element,
)
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
from mgt_physical_residual_assembly import (
    assemble_newton_tangent_stiffness,
    assemble_physical_internal_forces,
    assemble_physical_residual,
)


def build_direct_residual_assembler(
    *,
    mgt_path: Path,
    checkpoint_npz: Path,
    frame_gravity_load_scale: float = 0.01,
    stiffness_scale_to_si: float = 1000.0,
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
    reference_holder: dict[str, np.ndarray] = {}

    def assemble_residual(
        u: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        translations = np.asarray(u, dtype=np.float64).reshape((-1, DOF_PER_NODE))[:, :3]
        deformed_xyz = node_xyz + translations
        axial_forces = {
            int(elem): float(force) * float(frame_gravity_load_scale) * load_scale
            for elem, force in base_axial_forces.items()
        }
        service_tangent_by_element, service_material_meta = _service_tangent_by_element(
            elements=frame_elements,
            node_xyz=deformed_xyz,
            u=u,
            material_props=material_props,
        )
        stiffness, assembled_f_ext, tangent_meta = assemble_newton_tangent_stiffness(
            u=u,
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
            u=u,
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
        if external_load_override is not None:
            f_ext = np.asarray(external_load_override, dtype=np.float64)
        elif "reference_f_ext" in reference_holder:
            f_ext = reference_holder["reference_f_ext"]
        else:
            f_ext = assembled_f_ext
        active, free = _active_free(stiffness, restrained)
        residual, rhs = assemble_physical_residual(
            u=u,
            f_ext=f_ext,
            free=free,
            f_int=f_int,
        )
        return stiffness, f_ext, free, residual, rhs, {
            **tangent_meta,
            **physical_meta,
            "active_dof_count": int(active.size),
            "free_dof_count": int(free.size),
        }

    _reference_stiffness, reference_f_ext, _reference_free, _reference_residual, _reference_rhs, _ = (
        assemble_residual(np.zeros_like(u0))
    )
    reference_holder["reference_f_ext"] = reference_f_ext

    setup_meta = {
        "checkpoint": checkpoint_meta,
        "u0": u0,
        "load_scale": load_scale,
        "reference_f_ext_inf_n": float(np.max(np.abs(reference_f_ext))) if reference_f_ext.size else 0.0,
        "frame_select_meta": frame_select_meta,
        "support_meta": support_meta,
        "spring_meta": spring_meta,
        "parser_report_contract_pass": bool(parser_report.get("contract_pass")),
        "parser_run": parser_run,
        "_temp_dir": temp_dir,
    }

    def assemble_with_reference(
        u: np.ndarray,
        *,
        external_load_override: np.ndarray | None = None,
    ) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        override = reference_f_ext if external_load_override is None else external_load_override
        return assemble_residual(u, external_load_override=override)

    return assemble_with_reference, setup_meta
