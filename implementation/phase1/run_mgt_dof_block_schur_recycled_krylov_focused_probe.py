#!/usr/bin/env python3
"""Focused ROCm DOF-block Schur FGMRES probe with recycled Krylov correction."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from itertools import product
import json
from pathlib import Path
from typing import Any

import numpy as np

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_mgt_coupled_frame_surface_sparse_equilibrium import (
    _combined_restraints,
    _select_frame_elements as _select_coupled_frame_elements,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DOF_PER_NODE as FRAME_DOF_PER_NODE,
    _assemble_sparse_frame,
    _beam_end_offset_lookup,
    _element_angle_array_from_props,
)
from run_mgt_rocm_sparse_solver_probe import (
    DEFAULT_ROUNDTRIP,
    PRODUCTIZATION,
    SCHEMA_VERSION as ROCM_PROBE_SCHEMA_VERSION,
    _assemble_surface_shell_6dof,
    _regularized_active_system,
    _torch_rocm_ready,
    _torch_sparse_dof_block_schur_fgmres,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-dof-block-schur-recycled-krylov-focused-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_dof_block_schur_recycled_krylov_focused_probe.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _parse_ints(raw: str) -> tuple[int, ...]:
    return tuple(int(value.strip()) for value in str(raw).split(",") if value.strip())


def _parse_floats(raw: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(raw).split(",") if value.strip())


def _parse_strings(raw: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in str(raw).split(",") if value.strip())


def _load_roundtrip_model(roundtrip_json: Path) -> dict[str, Any]:
    roundtrip_npz = roundtrip_json.with_suffix(".npz")
    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = (
        load_mgt_section_material_properties(mgt_path)
        if mgt_path.is_file()
        else {"sections": {}, "materials": {}}
    )
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
    return {
        "provenance": provenance,
        "props": props,
        "node_xyz": node_xyz,
        "edge_index": edge_index,
        "elem_id": elem_id,
        "elem_type_code": elem_type_code,
        "elem_section_id": elem_section_id,
        "elem_material_id": elem_material_id,
        "elem_angle_deg": elem_angle_deg,
        "conn_ptr": conn_ptr,
        "conn_idx": conn_idx,
    }


def _assemble_shell_system(roundtrip_json: Path) -> dict[str, Any]:
    model = _load_roundtrip_model(roundtrip_json)
    props = model["props"]
    node_xyz = np.asarray(model["node_xyz"], dtype=np.float64)
    elem_type_code = np.asarray(model["elem_type_code"], dtype=np.int32)
    elem_section_id = np.asarray(model["elem_section_id"], dtype=np.int32)
    elem_material_id = np.asarray(model["elem_material_id"], dtype=np.int32)
    conn_ptr = np.asarray(model["conn_ptr"], dtype=np.int64)
    conn_idx = np.asarray(model["conn_idx"], dtype=np.int64)
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    plate_thickness_props = (
        props.get("plate_thicknesses")
        if isinstance(props.get("plate_thicknesses"), dict)
        else {}
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
    shell_restrained, shell_restraint_meta = _combined_restraints(
        n_nodes=int(node_xyz.shape[0]),
        node_xyz=node_xyz,
        frame_elements=[],
        surface_conns=surface_conns,
    )
    active, free, k_ff, rhs, _cpu_solution, system_meta = _regularized_active_system(
        stiffness=shell_stiffness,
        f_ext=shell_f,
        restrained=shell_restrained,
    )
    return {
        "matrix_family": "surface_shell_bending_6dof",
        "provenance": model["provenance"],
        "active": active,
        "free": free,
        "k_ff": k_ff,
        "rhs": rhs,
        "node_xyz": node_xyz,
        "mesh_fingerprint": {
            **shell_meta,
            **shell_restraint_meta,
            "active_dof_count": int(system_meta["active_dof_count"]),
            "free_dof_count": int(system_meta["free_dof_count"]),
            "matrix_shape": [int(k_ff.shape[0]), int(k_ff.shape[1])],
            "matrix_nnz": int(k_ff.nnz),
            "cpu_reference": system_meta["cpu_reference"],
        },
    }


def _assemble_coupled_frame_shell_system(roundtrip_json: Path) -> dict[str, Any]:
    model = _load_roundtrip_model(roundtrip_json)
    props = model["props"]
    node_xyz = np.asarray(model["node_xyz"], dtype=np.float64)
    elem_type_code = np.asarray(model["elem_type_code"], dtype=np.int32)
    elem_section_id = np.asarray(model["elem_section_id"], dtype=np.int32)
    elem_material_id = np.asarray(model["elem_material_id"], dtype=np.int32)
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    plate_thickness_props = (
        props.get("plate_thicknesses")
        if isinstance(props.get("plate_thicknesses"), dict)
        else {}
    )
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
    shell_stiffness, shell_f, shell_meta, surface_conns = _assemble_surface_shell_6dof(
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=np.asarray(model["conn_ptr"], dtype=np.int64),
        conn_idx=np.asarray(model["conn_idx"], dtype=np.int64),
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    frame_elements, frame_meta = _select_coupled_frame_elements(
        node_xyz=node_xyz,
        edge_index=np.asarray(model["edge_index"], dtype=np.int64),
        elem_id=np.asarray(model["elem_id"], dtype=np.int64),
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        elem_angle_deg=np.asarray(model["elem_angle_deg"], dtype=np.float64),
        beam_end_offsets=beam_end_offsets,
    )
    frame_stiffness, frame_f, frame_asm = _assemble_sparse_frame(
        elements=frame_elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
    )
    restrained, restraint_meta = _combined_restraints(
        n_nodes=int(node_xyz.shape[0]),
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        surface_conns=surface_conns,
    )
    frame_gravity_load_scale = 0.01
    stiffness = frame_stiffness + shell_stiffness
    f_ext = frame_f * frame_gravity_load_scale + shell_f
    active, free, k_ff, rhs, _cpu_solution, system_meta = _regularized_active_system(
        stiffness=stiffness,
        f_ext=f_ext,
        restrained=restrained,
    )
    return {
        "matrix_family": "coupled_frame_shell_6dof",
        "provenance": model["provenance"],
        "active": active,
        "free": free,
        "k_ff": k_ff,
        "rhs": rhs,
        "node_xyz": node_xyz,
        "mesh_fingerprint": {
            **frame_meta,
            **shell_meta,
            **restraint_meta,
            "active_dof_count": int(system_meta["active_dof_count"]),
            "free_dof_count": int(system_meta["free_dof_count"]),
            "matrix_shape": [int(k_ff.shape[0]), int(k_ff.shape[1])],
            "matrix_nnz": int(k_ff.nnz),
            "frame_stiffness_nnz": int(frame_stiffness.nnz),
            "shell_stiffness_nnz": int(shell_stiffness.nnz),
            "coupled_stiffness_nnz": int(stiffness.nnz),
            "frame_gravity_load_scale": frame_gravity_load_scale,
            "cpu_reference": system_meta["cpu_reference"],
            "frame_section_material_coverage": frame_asm,
        },
    }


def _assemble_matrix_family(roundtrip_json: Path, matrix_family: str) -> dict[str, Any]:
    if matrix_family == "surface_shell_bending_6dof":
        return _assemble_shell_system(roundtrip_json)
    if matrix_family == "coupled_frame_shell_6dof":
        return _assemble_coupled_frame_shell_system(roundtrip_json)
    raise ValueError(f"unsupported matrix_family: {matrix_family}")


def _default_tolerances(matrix_family: str) -> tuple[float, float]:
    if matrix_family == "coupled_frame_shell_6dof":
        return 5.0e-2, 2.0e-8
    return 1.0e-3, 5.0e-8


def run_mgt_dof_block_schur_recycled_krylov_focused_probe(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    output_json: Path | None = DEFAULT_OUT,
    matrix_family: str = "surface_shell_bending_6dof",
    basis_sizes: tuple[int, ...] = (8,),
    sources: tuple[str, ...] = ("residual_and_preconditioned",),
    ridge_factors: tuple[float, ...] = (1.0e-10,),
    alpha_values: tuple[float, ...] = (1.0,),
    correction_passes: int = 1,
    min_relative_improvement: float = 1.0e-8,
    restart_dimension: int = 32,
    restart_cycles: int = 3,
    inner_jacobi_steps: int = 12,
    inner_jacobi_weight: float = 0.35,
    schur_basis_aggregate_count: int = 0,
    schur_basis_aggregate_counts: tuple[int, ...] | None = None,
    schur_basis_selection: str = "algebraic",
    schur_basis_selections: tuple[str, ...] | None = None,
    schur_basis_ridge_factor: float = 1.0e-10,
    schur_basis_weight: float = 1.0,
    schur_basis_weights: tuple[float, ...] | None = None,
    coupling_hotspot_correction_size: int = 0,
    coupling_hotspot_correction_sizes: tuple[int, ...] | None = None,
    coupling_hotspot_selection: str = "coupling_strength",
    coupling_hotspot_selections: tuple[str, ...] | None = None,
    coupling_hotspot_ridge_factor: float = 1.0e-10,
    coupling_hotspot_post_passes: int = 0,
    coupling_hotspot_post_passes_values: tuple[int, ...] | None = None,
    coupling_hotspot_post_correction_size: int = 0,
    coupling_hotspot_post_correction_sizes: tuple[int, ...] | None = None,
    coupling_hotspot_post_selection: str = "",
    coupling_hotspot_post_selections: tuple[str, ...] | None = None,
    coupling_pair_smoother_count: int = 0,
    coupling_pair_smoother_counts: tuple[int, ...] | None = None,
    coupling_pair_smoother_sweeps: int = 0,
    coupling_pair_smoother_weight: float = 1.0,
    coupling_pair_smoother_weights: tuple[float, ...] | None = None,
    coupling_pair_smoother_ridge_factor: float = 1.0e-10,
    coupling_pair_smoother_selection: str = "coupling_strength",
    coupling_pair_smoother_selections: tuple[str, ...] | None = None,
    coupling_pair_basis_count: int = 0,
    coupling_pair_basis_counts: tuple[int, ...] | None = None,
    coupling_pair_basis_selection: str = "coupling_strength",
    coupling_pair_basis_selections: tuple[str, ...] | None = None,
    coupling_pair_basis_weight: float = 1.0,
    coupling_pair_basis_weights: tuple[float, ...] | None = None,
    coupling_pair_basis_ridge_factor: float = 1.0e-10,
    node_block_smoother_sweeps: int = 0,
    node_block_smoother_weight: float = 1.0,
    node_block_subdomain_smoother_sweeps: int = 0,
    node_block_subdomain_smoother_weight: float = 1.0,
    node_block_subdomain_smoother_weights: tuple[float, ...] | None = None,
    node_block_subdomain_smoother_max_dof_count: int = 96,
    node_block_subdomain_smoother_max_dof_counts: tuple[int, ...] | None = None,
    node_block_subdomain_smoother_ridge_factor: float = 1.0e-10,
    node_block_subdomain_smoother_update_mode: str = "additive",
    node_block_subdomain_smoother_update_modes: tuple[str, ...] | None = None,
    node_block_interface_pair_smoother_sweeps: int = 0,
    node_block_interface_pair_smoother_weight: float = 1.0,
    node_block_interface_pair_smoother_weights: tuple[float, ...] | None = None,
    node_block_interface_pair_smoother_max_dof_count: int = 128,
    node_block_interface_pair_smoother_max_dof_counts: tuple[int, ...] | None = None,
    node_block_interface_pair_smoother_ridge_factor: float = 1.0e-10,
    node_block_interface_pair_smoother_halo_depth: int = 0,
    node_block_interface_pair_smoother_halo_depth_values: tuple[int, ...] | None = None,
    node_block_interface_pair_smoother_update_mode: str = "additive",
    node_block_interface_pair_smoother_update_modes: tuple[str, ...] | None = None,
    node_block_interface_pair_coarse_rebalance_passes: int = 0,
    node_block_interface_pair_coarse_rebalance_pass_values: tuple[int, ...] | None = None,
    node_block_interface_pair_coarse_rebalance_weight: float = 1.0,
    node_block_interface_pair_coarse_rebalance_weights: tuple[float, ...] | None = None,
    node_block_coarse_aggregate_count: int = 0,
    node_block_coarse_aggregate_counts: tuple[int, ...] | None = None,
    node_block_coarse_ridge_factor: float = 1.0e-10,
    node_block_coarse_order: str = "coarse_then_smooth",
    node_block_coarse_correction_passes: int = 1,
    node_block_coarse_correction_pass_values: tuple[int, ...] | None = None,
    node_block_coarse_load_restriction_target: str = "load",
    node_block_coarse_load_restriction_targets: tuple[str, ...] | None = None,
    node_block_coarse_smoothing_steps: int = 0,
    node_block_coarse_smoothing_weight: float = 0.0,
    node_block_coarse_smoothing_weights: tuple[float, ...] | None = None,
    node_block_coarse_partition: str = "sorted_node_id",
    node_block_coarse_overlap_depth: int = 0,
    node_block_coarse_mode: str = "constant",
    node_block_coarse_local_dof_filter: str = "all",
    node_block_coarse_local_dof_filters: tuple[str, ...] | None = None,
    node_block_coarse_energy_modes_per_dof: int = 2,
    node_block_coarse_energy_modes_per_dof_values: tuple[int, ...] | None = None,
    node_block_coarse_energy_mode_selection: str = "low_eigen",
    node_block_coarse_energy_mode_selections: tuple[str, ...] | None = None,
    node_block_coarse_weight: float = 1.0,
    node_block_coarse_weights: tuple[float, ...] | None = None,
    node_block_coarse_basis_orthogonalization: str = "none",
    node_block_coarse_basis_orthogonalizations: tuple[str, ...] | None = None,
    node_block_coarse_harmonic_extension_weight: float = 1.0,
    node_block_coarse_harmonic_extension_weights: tuple[float, ...] | None = None,
    node_block_coarse_harmonic_extension_steps: int = 1,
    node_block_coarse_harmonic_extension_step_values: tuple[int, ...] | None = None,
    node_block_coarse_schur_cycle_passes: int = 0,
    node_block_coarse_schur_cycle_pass_values: tuple[int, ...] | None = None,
    node_block_coarse_schur_cycle_weight: float = 1.0,
    node_block_coarse_schur_cycle_weights: tuple[float, ...] | None = None,
    node_block_coarse_secondary_mode: str = "",
    node_block_coarse_secondary_weight: float = 0.0,
    node_block_coarse_secondary_correction_passes: int = 1,
    tolerance_abs: float | None = None,
    tolerance_rel: float | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    tolerance_abs, tolerance_rel = (
        _default_tolerances(matrix_family)
        if tolerance_abs is None or tolerance_rel is None
        else (float(tolerance_abs), float(tolerance_rel))
    )
    rocm_ready, torch_info = _torch_rocm_ready()
    if not rocm_ready:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "torch_rocm": torch_info,
            "blockers": ["torch_rocm_runtime_not_ready"],
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    system = _assemble_matrix_family(roundtrip_json, matrix_family)
    k_ff = system["k_ff"]
    rhs = system["rhs"]
    free = system["free"]
    rows: list[dict[str, Any]] = []
    coarse_weights = (
        tuple(float(value) for value in node_block_coarse_weights)
        if node_block_coarse_weights is not None
        else (float(node_block_coarse_weight),)
    )
    coarse_weights = tuple(
        value for value in coarse_weights if np.isfinite(float(value))
    ) or (float(node_block_coarse_weight),)
    coarse_harmonic_extension_weight_candidates = (
        tuple(float(value) for value in node_block_coarse_harmonic_extension_weights)
        if node_block_coarse_harmonic_extension_weights is not None
        else (float(node_block_coarse_harmonic_extension_weight),)
    )
    coarse_harmonic_extension_weight_candidates = tuple(
        value
        for value in coarse_harmonic_extension_weight_candidates
        if np.isfinite(float(value))
    ) or (float(node_block_coarse_harmonic_extension_weight),)
    allowed_coarse_basis_orthogonalizations = {"none", "qr", "energy"}
    coarse_basis_orthogonalization_candidates = (
        tuple(
            str(value).strip().lower()
            for value in node_block_coarse_basis_orthogonalizations
            if str(value).strip()
        )
        if node_block_coarse_basis_orthogonalizations is not None
        else (str(node_block_coarse_basis_orthogonalization).strip().lower() or "none",)
    )
    coarse_basis_orthogonalization_candidates = tuple(
        value
        for value in coarse_basis_orthogonalization_candidates
        if value in allowed_coarse_basis_orthogonalizations
    ) or (str(node_block_coarse_basis_orthogonalization).strip().lower() or "none",)
    coarse_harmonic_extension_step_candidates = (
        tuple(int(value) for value in node_block_coarse_harmonic_extension_step_values)
        if node_block_coarse_harmonic_extension_step_values is not None
        else (int(node_block_coarse_harmonic_extension_steps),)
    )
    coarse_harmonic_extension_step_candidates = tuple(
        value for value in coarse_harmonic_extension_step_candidates if int(value) >= 0
    ) or (int(node_block_coarse_harmonic_extension_steps),)
    coarse_smoothing_weights = (
        tuple(float(value) for value in node_block_coarse_smoothing_weights)
        if node_block_coarse_smoothing_weights is not None
        else (float(node_block_coarse_smoothing_weight),)
    )
    coarse_smoothing_weights = tuple(
        value for value in coarse_smoothing_weights if np.isfinite(float(value))
    ) or (float(node_block_coarse_smoothing_weight),)
    coarse_aggregate_counts = (
        tuple(int(value) for value in node_block_coarse_aggregate_counts)
        if node_block_coarse_aggregate_counts is not None
        else (int(node_block_coarse_aggregate_count),)
    )
    coarse_aggregate_counts = tuple(
        value for value in coarse_aggregate_counts if int(value) >= 0
    ) or (int(node_block_coarse_aggregate_count),)
    coarse_correction_pass_candidates = (
        tuple(int(value) for value in node_block_coarse_correction_pass_values)
        if node_block_coarse_correction_pass_values is not None
        else (int(node_block_coarse_correction_passes),)
    )
    coarse_correction_pass_candidates = tuple(
        max(1, int(value)) for value in coarse_correction_pass_candidates
    ) or (max(1, int(node_block_coarse_correction_passes)),)
    allowed_load_restriction_targets = {"load", "residual"}
    coarse_load_restriction_target_candidates = (
        tuple(
            str(value).strip().lower()
            for value in node_block_coarse_load_restriction_targets
            if str(value).strip()
        )
        if node_block_coarse_load_restriction_targets is not None
        else (str(node_block_coarse_load_restriction_target).strip().lower() or "load",)
    )
    coarse_load_restriction_target_candidates = tuple(
        value
        for value in coarse_load_restriction_target_candidates
        if value in allowed_load_restriction_targets
    ) or (str(node_block_coarse_load_restriction_target).strip().lower() or "load",)
    coarse_energy_modes_per_dof_candidates = (
        tuple(int(value) for value in node_block_coarse_energy_modes_per_dof_values)
        if node_block_coarse_energy_modes_per_dof_values is not None
        else (int(node_block_coarse_energy_modes_per_dof),)
    )
    coarse_energy_modes_per_dof_candidates = tuple(
        max(1, int(value)) for value in coarse_energy_modes_per_dof_candidates
    ) or (max(1, int(node_block_coarse_energy_modes_per_dof)),)
    coarse_local_dof_filter_candidates = (
        tuple(
            str(value).strip().lower()
            for value in node_block_coarse_local_dof_filters
            if str(value).strip()
        )
        if node_block_coarse_local_dof_filters is not None
        else (str(node_block_coarse_local_dof_filter).strip().lower() or "all",)
    )
    coarse_local_dof_filter_candidates = tuple(
        "translations"
        if value in {"translation", "translations", "translational"}
        else (
            "rotations"
            if value in {"rotation", "rotations", "rotational"}
            else "all"
        )
        for value in coarse_local_dof_filter_candidates
    ) or ("all",)
    allowed_energy_mode_selections = {
        "low_eigen",
        "rhs_projection",
        "rhs_energy_score",
    }
    coarse_energy_mode_selection_candidates = (
        tuple(str(value).strip().lower() for value in node_block_coarse_energy_mode_selections)
        if node_block_coarse_energy_mode_selections is not None
        else (str(node_block_coarse_energy_mode_selection).strip().lower() or "low_eigen",)
    )
    coarse_energy_mode_selection_candidates = tuple(
        value
        for value in coarse_energy_mode_selection_candidates
        if value in allowed_energy_mode_selections
    ) or (str(node_block_coarse_energy_mode_selection).strip().lower() or "low_eigen",)
    coarse_schur_cycle_pass_candidates = (
        tuple(int(value) for value in node_block_coarse_schur_cycle_pass_values)
        if node_block_coarse_schur_cycle_pass_values is not None
        else (int(node_block_coarse_schur_cycle_passes),)
    )
    coarse_schur_cycle_pass_candidates = tuple(
        max(0, int(value)) for value in coarse_schur_cycle_pass_candidates
    ) or (max(0, int(node_block_coarse_schur_cycle_passes)),)
    coarse_schur_cycle_weight_candidates = (
        tuple(float(value) for value in node_block_coarse_schur_cycle_weights)
        if node_block_coarse_schur_cycle_weights is not None
        else (float(node_block_coarse_schur_cycle_weight),)
    )
    coarse_schur_cycle_weight_candidates = tuple(
        value for value in coarse_schur_cycle_weight_candidates if np.isfinite(float(value))
    ) or (float(node_block_coarse_schur_cycle_weight),)
    schur_aggregate_counts = (
        tuple(int(value) for value in schur_basis_aggregate_counts)
        if schur_basis_aggregate_counts is not None
        else (int(schur_basis_aggregate_count),)
    )
    schur_aggregate_counts = tuple(
        value for value in schur_aggregate_counts if int(value) >= 0
    ) or (int(schur_basis_aggregate_count),)
    allowed_schur_selections = {
        "algebraic",
        "rhs_weighted",
        "rhs_signed_weighted",
        "mixed_rhs",
        "mixed_rhs_signed",
    }
    schur_selection_candidates = (
        tuple(str(value) for value in schur_basis_selections)
        if schur_basis_selections is not None
        else (str(schur_basis_selection),)
    )
    schur_selection_candidates = tuple(
        value for value in schur_selection_candidates if value in allowed_schur_selections
    ) or (str(schur_basis_selection),)
    schur_weight_candidates = (
        tuple(float(value) for value in schur_basis_weights)
        if schur_basis_weights is not None
        else (float(schur_basis_weight),)
    )
    schur_weight_candidates = tuple(
        value for value in schur_weight_candidates if np.isfinite(float(value))
    ) or (float(schur_basis_weight),)
    coupling_hotspot_size_candidates = (
        tuple(int(value) for value in coupling_hotspot_correction_sizes)
        if coupling_hotspot_correction_sizes is not None
        else (int(coupling_hotspot_correction_size),)
    )
    coupling_hotspot_size_candidates = tuple(
        value for value in coupling_hotspot_size_candidates if int(value) >= 0
    ) or (int(coupling_hotspot_correction_size),)
    allowed_coupling_hotspot_selections = {
        "coupling_strength",
        "rhs_residual",
        "mixed",
    }
    coupling_hotspot_selection_candidates = (
        tuple(str(value) for value in coupling_hotspot_selections)
        if coupling_hotspot_selections is not None
        else (str(coupling_hotspot_selection),)
    )
    coupling_hotspot_selection_candidates = tuple(
        value
        for value in coupling_hotspot_selection_candidates
        if value in allowed_coupling_hotspot_selections
    ) or (str(coupling_hotspot_selection),)
    coupling_hotspot_post_pass_candidates = (
        tuple(int(value) for value in coupling_hotspot_post_passes_values)
        if coupling_hotspot_post_passes_values is not None
        else (int(coupling_hotspot_post_passes),)
    )
    coupling_hotspot_post_pass_candidates = tuple(
        value for value in coupling_hotspot_post_pass_candidates if int(value) >= 0
    ) or (int(coupling_hotspot_post_passes),)
    coupling_hotspot_post_size_candidates = (
        tuple(int(value) for value in coupling_hotspot_post_correction_sizes)
        if coupling_hotspot_post_correction_sizes is not None
        else (int(coupling_hotspot_post_correction_size),)
    )
    coupling_hotspot_post_size_candidates = tuple(
        value for value in coupling_hotspot_post_size_candidates if int(value) >= 0
    ) or (int(coupling_hotspot_post_correction_size),)
    coupling_hotspot_post_selection_candidates = (
        tuple(str(value) for value in coupling_hotspot_post_selections)
        if coupling_hotspot_post_selections is not None
        else ((str(coupling_hotspot_post_selection),) if str(coupling_hotspot_post_selection) else ("",))
    )
    coupling_hotspot_post_selection_candidates = tuple(
        value
        for value in coupling_hotspot_post_selection_candidates
        if value == "" or value in allowed_coupling_hotspot_selections
    ) or ((str(coupling_hotspot_post_selection),) if str(coupling_hotspot_post_selection) else ("",))
    coupling_pair_smoother_count_candidates = (
        tuple(int(value) for value in coupling_pair_smoother_counts)
        if coupling_pair_smoother_counts is not None
        else (int(coupling_pair_smoother_count),)
    )
    coupling_pair_smoother_count_candidates = tuple(
        value for value in coupling_pair_smoother_count_candidates if int(value) >= 0
    ) or (int(coupling_pair_smoother_count),)
    coupling_pair_smoother_weight_candidates = (
        tuple(float(value) for value in coupling_pair_smoother_weights)
        if coupling_pair_smoother_weights is not None
        else (float(coupling_pair_smoother_weight),)
    )
    coupling_pair_smoother_weight_candidates = tuple(
        value for value in coupling_pair_smoother_weight_candidates if np.isfinite(float(value))
    ) or (float(coupling_pair_smoother_weight),)
    allowed_pair_selections = {"coupling_strength", "rhs_weighted", "mixed"}
    coupling_pair_smoother_selection_candidates = (
        tuple(str(value) for value in coupling_pair_smoother_selections)
        if coupling_pair_smoother_selections is not None
        else (str(coupling_pair_smoother_selection),)
    )
    coupling_pair_smoother_selection_candidates = tuple(
        value for value in coupling_pair_smoother_selection_candidates if value in allowed_pair_selections
    ) or (str(coupling_pair_smoother_selection),)
    coupling_pair_basis_count_candidates = (
        tuple(int(value) for value in coupling_pair_basis_counts)
        if coupling_pair_basis_counts is not None
        else (int(coupling_pair_basis_count),)
    )
    coupling_pair_basis_count_candidates = tuple(
        value for value in coupling_pair_basis_count_candidates if int(value) >= 0
    ) or (int(coupling_pair_basis_count),)
    coupling_pair_basis_selection_candidates = (
        tuple(str(value) for value in coupling_pair_basis_selections)
        if coupling_pair_basis_selections is not None
        else (str(coupling_pair_basis_selection),)
    )
    coupling_pair_basis_selection_candidates = tuple(
        value for value in coupling_pair_basis_selection_candidates if value in allowed_pair_selections
    ) or (str(coupling_pair_basis_selection),)
    coupling_pair_basis_weight_candidates = (
        tuple(float(value) for value in coupling_pair_basis_weights)
        if coupling_pair_basis_weights is not None
        else (float(coupling_pair_basis_weight),)
    )
    coupling_pair_basis_weight_candidates = tuple(
        value for value in coupling_pair_basis_weight_candidates if np.isfinite(float(value))
    ) or (float(coupling_pair_basis_weight),)
    subdomain_smoother_weight_candidates = (
        tuple(float(value) for value in node_block_subdomain_smoother_weights)
        if node_block_subdomain_smoother_weights is not None
        else (float(node_block_subdomain_smoother_weight),)
    )
    subdomain_smoother_weight_candidates = tuple(
        value for value in subdomain_smoother_weight_candidates if np.isfinite(float(value))
    ) or (float(node_block_subdomain_smoother_weight),)
    subdomain_smoother_max_width_candidates = (
        tuple(int(value) for value in node_block_subdomain_smoother_max_dof_counts)
        if node_block_subdomain_smoother_max_dof_counts is not None
        else (int(node_block_subdomain_smoother_max_dof_count),)
    )
    subdomain_smoother_max_width_candidates = tuple(
        value for value in subdomain_smoother_max_width_candidates if int(value) > 0
    ) or (int(node_block_subdomain_smoother_max_dof_count),)
    subdomain_smoother_update_mode_candidates = (
        tuple(
            str(value).strip().lower()
            for value in node_block_subdomain_smoother_update_modes
            if str(value).strip()
        )
        if node_block_subdomain_smoother_update_modes is not None
        else (str(node_block_subdomain_smoother_update_mode).strip().lower() or "additive",)
    )
    subdomain_smoother_update_mode_candidates = tuple(
        "multiplicative"
        if value in {"multiplicative", "swept", "gauss_seidel"}
        else "additive"
        for value in subdomain_smoother_update_mode_candidates
    ) or ("additive",)
    interface_pair_smoother_weight_candidates = (
        tuple(float(value) for value in node_block_interface_pair_smoother_weights)
        if node_block_interface_pair_smoother_weights is not None
        else (float(node_block_interface_pair_smoother_weight),)
    )
    interface_pair_smoother_weight_candidates = tuple(
        value for value in interface_pair_smoother_weight_candidates if np.isfinite(float(value))
    ) or (float(node_block_interface_pair_smoother_weight),)
    interface_pair_smoother_max_width_candidates = (
        tuple(int(value) for value in node_block_interface_pair_smoother_max_dof_counts)
        if node_block_interface_pair_smoother_max_dof_counts is not None
        else (int(node_block_interface_pair_smoother_max_dof_count),)
    )
    interface_pair_smoother_max_width_candidates = tuple(
        value for value in interface_pair_smoother_max_width_candidates if int(value) > 0
    ) or (int(node_block_interface_pair_smoother_max_dof_count),)
    interface_pair_smoother_halo_depth_candidates = (
        tuple(int(value) for value in node_block_interface_pair_smoother_halo_depth_values)
        if node_block_interface_pair_smoother_halo_depth_values is not None
        else (int(node_block_interface_pair_smoother_halo_depth),)
    )
    interface_pair_smoother_halo_depth_candidates = tuple(
        max(0, int(value)) for value in interface_pair_smoother_halo_depth_candidates
    ) or (max(0, int(node_block_interface_pair_smoother_halo_depth)),)
    interface_pair_smoother_update_mode_candidates = (
        tuple(
            str(value).strip().lower()
            for value in node_block_interface_pair_smoother_update_modes
            if str(value).strip()
        )
        if node_block_interface_pair_smoother_update_modes is not None
        else (
            str(node_block_interface_pair_smoother_update_mode).strip().lower()
            or "additive",
        )
    )
    interface_pair_smoother_update_mode_candidates = tuple(
        "multiplicative"
        if value in {"multiplicative", "swept", "gauss_seidel"}
        else "additive"
        for value in interface_pair_smoother_update_mode_candidates
    ) or ("additive",)
    interface_pair_rebalance_pass_candidates = (
        tuple(int(value) for value in node_block_interface_pair_coarse_rebalance_pass_values)
        if node_block_interface_pair_coarse_rebalance_pass_values is not None
        else (int(node_block_interface_pair_coarse_rebalance_passes),)
    )
    interface_pair_rebalance_pass_candidates = tuple(
        max(0, int(value)) for value in interface_pair_rebalance_pass_candidates
    ) or (max(0, int(node_block_interface_pair_coarse_rebalance_passes)),)
    interface_pair_rebalance_weight_candidates = (
        tuple(float(value) for value in node_block_interface_pair_coarse_rebalance_weights)
        if node_block_interface_pair_coarse_rebalance_weights is not None
        else (float(node_block_interface_pair_coarse_rebalance_weight),)
    )
    interface_pair_rebalance_weight_candidates = tuple(
        value
        for value in interface_pair_rebalance_weight_candidates
        if np.isfinite(float(value))
    ) or (float(node_block_interface_pair_coarse_rebalance_weight),)
    base_candidate_axes = product(
        basis_sizes,
        sources,
        ridge_factors,
        schur_aggregate_counts,
        schur_selection_candidates,
        schur_weight_candidates,
        coupling_hotspot_size_candidates,
        coupling_hotspot_selection_candidates,
        coupling_hotspot_post_pass_candidates,
        coupling_hotspot_post_size_candidates,
        coupling_hotspot_post_selection_candidates,
        coupling_pair_smoother_count_candidates,
        coupling_pair_smoother_selection_candidates,
        coupling_pair_smoother_weight_candidates,
        coupling_pair_basis_count_candidates,
        coupling_pair_basis_selection_candidates,
        coarse_aggregate_counts,
        coarse_weights,
        coarse_correction_pass_candidates,
        coarse_load_restriction_target_candidates,
        coarse_smoothing_weights,
        coarse_local_dof_filter_candidates,
        coarse_energy_modes_per_dof_candidates,
        coarse_energy_mode_selection_candidates,
        coarse_basis_orthogonalization_candidates,
        coarse_harmonic_extension_weight_candidates,
        coarse_harmonic_extension_step_candidates,
        coarse_schur_cycle_pass_candidates,
        coarse_schur_cycle_weight_candidates,
    )
    for (
        basis_size,
        source,
        ridge_factor,
        schur_aggregate_count,
        schur_selection,
        schur_weight,
        hotspot_size,
        hotspot_selection,
        hotspot_post_passes,
        hotspot_post_size,
        hotspot_post_selection,
        pair_count,
        pair_selection,
        pair_weight,
        pair_basis_count,
        pair_basis_selection,
        coarse_aggregate_count,
        coarse_weight,
        coarse_correction_passes,
        coarse_load_restriction_target,
        coarse_smoothing_weight,
        coarse_local_dof_filter,
        coarse_energy_modes_per_dof,
        coarse_energy_mode_selection,
        coarse_basis_orthogonalization,
        coarse_harmonic_extension_weight,
        coarse_harmonic_extension_steps,
        coarse_schur_cycle_passes,
        coarse_schur_cycle_weight,
    ) in base_candidate_axes:
        pair_basis_weight_loop = (
            (0.0,)
            if int(pair_basis_count) <= 0
            else coupling_pair_basis_weight_candidates
        )
        subdomain_weight_loop = (
            (0.0,)
            if int(node_block_subdomain_smoother_sweeps) <= 0
            else subdomain_smoother_weight_candidates
        )
        subdomain_width_loop = (
            (int(node_block_subdomain_smoother_max_dof_count),)
            if int(node_block_subdomain_smoother_sweeps) <= 0
            else subdomain_smoother_max_width_candidates
        )
        subdomain_update_mode_loop = (
            ("additive",)
            if int(node_block_subdomain_smoother_sweeps) <= 0
            else subdomain_smoother_update_mode_candidates
        )
        interface_pair_weight_loop = (
            (0.0,)
            if int(node_block_interface_pair_smoother_sweeps) <= 0
            else interface_pair_smoother_weight_candidates
        )
        interface_pair_width_loop = (
            (int(node_block_interface_pair_smoother_max_dof_count),)
            if int(node_block_interface_pair_smoother_sweeps) <= 0
            else interface_pair_smoother_max_width_candidates
        )
        interface_pair_halo_loop = (
            (int(node_block_interface_pair_smoother_halo_depth),)
            if int(node_block_interface_pair_smoother_sweeps) <= 0
            else interface_pair_smoother_halo_depth_candidates
        )
        interface_pair_update_mode_loop = (
            ("additive",)
            if int(node_block_interface_pair_smoother_sweeps) <= 0
            else interface_pair_smoother_update_mode_candidates
        )
        interface_pair_rebalance_pass_loop = (
            (0,)
            if int(node_block_interface_pair_smoother_sweeps) <= 0
            else interface_pair_rebalance_pass_candidates
        )
        interface_pair_rebalance_weight_loop = (
            (0.0,)
            if int(node_block_interface_pair_smoother_sweeps) <= 0
            else interface_pair_rebalance_weight_candidates
        )
        for (
            pair_basis_weight,
            subdomain_max_width,
            subdomain_weight,
            subdomain_update_mode,
            interface_pair_weight,
            interface_pair_max_width,
            interface_pair_halo_depth,
            interface_pair_update_mode,
            interface_pair_rebalance_passes,
            interface_pair_rebalance_weight,
        ) in product(
            pair_basis_weight_loop,
            subdomain_width_loop,
            subdomain_weight_loop,
            subdomain_update_mode_loop,
            interface_pair_weight_loop,
            interface_pair_width_loop,
            interface_pair_halo_loop,
            interface_pair_update_mode_loop,
            interface_pair_rebalance_pass_loop,
            interface_pair_rebalance_weight_loop,
        ):
            row = _torch_sparse_dof_block_schur_fgmres(
                k_ff=k_ff,
                rhs=rhs,
                free_global_dof=free,
                node_xyz=system.get("node_xyz"),
                dof_per_node=FRAME_DOF_PER_NODE,
                max_iterations=int(restart_dimension) * int(restart_cycles),
                tolerance_abs=tolerance_abs,
                tolerance_rel=tolerance_rel,
                restart_dimension=restart_dimension,
                restart_cycles=restart_cycles,
                inner_jacobi_steps=inner_jacobi_steps,
                inner_jacobi_weight=inner_jacobi_weight,
                coupling_hotspot_correction_size=int(hotspot_size),
                coupling_hotspot_selection=str(hotspot_selection),
                coupling_hotspot_ridge_factor=float(coupling_hotspot_ridge_factor),
                coupling_hotspot_post_passes=int(hotspot_post_passes),
                coupling_hotspot_post_correction_size=int(hotspot_post_size),
                coupling_hotspot_post_selection=str(hotspot_post_selection),
                coupling_pair_smoother_count=int(pair_count),
                coupling_pair_smoother_sweeps=int(coupling_pair_smoother_sweeps),
                coupling_pair_smoother_weight=float(pair_weight),
                coupling_pair_smoother_ridge_factor=float(coupling_pair_smoother_ridge_factor),
                coupling_pair_smoother_selection=str(pair_selection),
                coupling_pair_basis_count=int(pair_basis_count),
                coupling_pair_basis_selection=str(pair_basis_selection),
                coupling_pair_basis_weight=float(pair_basis_weight),
                coupling_pair_basis_ridge_factor=float(coupling_pair_basis_ridge_factor),
                schur_basis_aggregate_count=int(schur_aggregate_count),
                schur_basis_selection=str(schur_selection),
                schur_basis_ridge_factor=schur_basis_ridge_factor,
                schur_basis_weight=float(schur_weight),
                node_block_smoother_sweeps=node_block_smoother_sweeps,
                node_block_smoother_weight=node_block_smoother_weight,
                node_block_subdomain_smoother_sweeps=node_block_subdomain_smoother_sweeps,
                node_block_subdomain_smoother_weight=float(subdomain_weight),
                node_block_subdomain_smoother_max_dof_count=int(subdomain_max_width),
                node_block_subdomain_smoother_ridge_factor=float(
                    node_block_subdomain_smoother_ridge_factor
                ),
                node_block_subdomain_smoother_update_mode=str(subdomain_update_mode),
                node_block_interface_pair_smoother_sweeps=(
                    node_block_interface_pair_smoother_sweeps
                ),
                node_block_interface_pair_smoother_weight=float(interface_pair_weight),
                node_block_interface_pair_smoother_max_dof_count=int(
                    interface_pair_max_width
                ),
                node_block_interface_pair_smoother_ridge_factor=float(
                    node_block_interface_pair_smoother_ridge_factor
                ),
                node_block_interface_pair_smoother_halo_depth=int(
                    interface_pair_halo_depth
                ),
                node_block_interface_pair_smoother_update_mode=str(
                    interface_pair_update_mode
                ),
                node_block_interface_pair_coarse_rebalance_passes=int(
                    interface_pair_rebalance_passes
                ),
                node_block_interface_pair_coarse_rebalance_weight=float(
                    interface_pair_rebalance_weight
                ),
                node_block_coarse_aggregate_count=int(coarse_aggregate_count),
                node_block_coarse_ridge_factor=node_block_coarse_ridge_factor,
                node_block_coarse_order=node_block_coarse_order,
                node_block_coarse_correction_passes=int(coarse_correction_passes),
                node_block_coarse_load_restriction_target=str(
                    coarse_load_restriction_target
                ),
                node_block_coarse_smoothing_steps=node_block_coarse_smoothing_steps,
                node_block_coarse_smoothing_weight=float(coarse_smoothing_weight),
                node_block_coarse_partition=node_block_coarse_partition,
                node_block_coarse_overlap_depth=int(node_block_coarse_overlap_depth),
                node_block_coarse_mode=node_block_coarse_mode,
                node_block_coarse_local_dof_filter=str(coarse_local_dof_filter),
                node_block_coarse_energy_modes_per_dof=int(coarse_energy_modes_per_dof),
                node_block_coarse_energy_mode_selection=str(coarse_energy_mode_selection),
                node_block_coarse_weight=float(coarse_weight),
                node_block_coarse_basis_orthogonalization=str(
                    coarse_basis_orthogonalization
                ),
                node_block_coarse_harmonic_extension_weight=float(
                    coarse_harmonic_extension_weight
                ),
                node_block_coarse_harmonic_extension_steps=int(
                    coarse_harmonic_extension_steps
                ),
                node_block_coarse_schur_cycle_passes=int(coarse_schur_cycle_passes),
                node_block_coarse_schur_cycle_weight=float(coarse_schur_cycle_weight),
                node_block_coarse_secondary_mode=str(node_block_coarse_secondary_mode),
                node_block_coarse_secondary_weight=float(node_block_coarse_secondary_weight),
                node_block_coarse_secondary_correction_passes=int(
                    node_block_coarse_secondary_correction_passes
                ),
                schur_order="rotations_first",
                recycled_krylov_basis_size=int(basis_size),
                recycled_krylov_source=str(source),
                recycled_krylov_ridge_factor=float(ridge_factor),
                recycled_krylov_min_relative_improvement=min_relative_improvement,
                recycled_krylov_alpha_values=alpha_values,
                recycled_krylov_correction_passes=correction_passes,
            )
            row.pop("_solution_np", None)
            rows.append(row)

    valid_rows = [
        row
        for row in rows
        if isinstance(row.get("best_residual_inf_n"), (int, float))
    ]
    best_row = (
        min(valid_rows, key=lambda row: float(row["best_residual_inf_n"]))
        if valid_rows
        else None
    )
    gate = max(tolerance_abs, tolerance_rel * max(float(np.max(np.abs(rhs))) if rhs.size else 0.0, 1.0))
    converged = bool(best_row and float(best_row["best_residual_inf_n"]) <= gate)
    previous_best: Any = None
    if matrix_family == "surface_shell_bending_6dof":
        previous_frontier = _load_json(
            PRODUCTIZATION / "mgt_dof_block_schur_fgmres_focused_probe.json"
        )
        previous_best = (
            previous_frontier.get("best_row", {}).get("best_residual_inf_n")
            if isinstance(previous_frontier.get("best_row"), dict)
            else None
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if converged else "partial",
        "rocm_parent_schema_version": ROCM_PROBE_SCHEMA_VERSION,
        "torch_rocm": torch_info,
        "roundtrip_json": str(roundtrip_json),
        "mesh_fingerprint": system["mesh_fingerprint"],
        "probe_contract": {
            "matrix_family": matrix_family,
            "official_backend_family": "amd_rocm_hip",
            "cpu_fallback_promoted": False,
            "host_dense_solve_fallback_allowed": False,
            "residual_replay_gate_n": float(gate),
            "previous_block_schur_frontier_residual_inf_n": previous_best,
            "node_block_coarse_aggregate_count_candidates": [
                int(value) for value in coarse_aggregate_counts
            ],
            "schur_basis_aggregate_count_candidates": [
                int(value) for value in schur_aggregate_counts
            ],
            "schur_basis_selection_candidates": [
                str(value) for value in schur_selection_candidates
            ],
            "schur_basis_weight_candidates": [
                float(value) for value in schur_weight_candidates
            ],
            "coupling_hotspot_correction_size_candidates": [
                int(value) for value in coupling_hotspot_size_candidates
            ],
            "coupling_hotspot_selection_candidates": [
                str(value) for value in coupling_hotspot_selection_candidates
            ],
            "coupling_hotspot_ridge_factor": float(coupling_hotspot_ridge_factor),
            "coupling_hotspot_post_pass_candidates": [
                int(value) for value in coupling_hotspot_post_pass_candidates
            ],
            "coupling_hotspot_post_correction_size_candidates": [
                int(value) for value in coupling_hotspot_post_size_candidates
            ],
            "coupling_hotspot_post_selection_candidates": [
                str(value) for value in coupling_hotspot_post_selection_candidates
            ],
            "coupling_pair_smoother_count_candidates": [
                int(value) for value in coupling_pair_smoother_count_candidates
            ],
            "coupling_pair_smoother_selection_candidates": [
                str(value) for value in coupling_pair_smoother_selection_candidates
            ],
            "coupling_pair_smoother_weight_candidates": [
                float(value) for value in coupling_pair_smoother_weight_candidates
            ],
            "coupling_pair_smoother_sweeps": int(coupling_pair_smoother_sweeps),
            "coupling_pair_smoother_ridge_factor": float(coupling_pair_smoother_ridge_factor),
            "coupling_pair_basis_count_candidates": [
                int(value) for value in coupling_pair_basis_count_candidates
            ],
            "coupling_pair_basis_selection_candidates": [
                str(value) for value in coupling_pair_basis_selection_candidates
            ],
            "coupling_pair_basis_weight_candidates": [
                float(value) for value in coupling_pair_basis_weight_candidates
            ],
            "coupling_pair_basis_ridge_factor": float(coupling_pair_basis_ridge_factor),
            "node_block_subdomain_smoother_sweeps": int(node_block_subdomain_smoother_sweeps),
            "node_block_subdomain_smoother_weight_candidates": [
                float(value) for value in subdomain_smoother_weight_candidates
            ],
            "node_block_subdomain_smoother_max_dof_count_candidates": [
                int(value) for value in subdomain_smoother_max_width_candidates
            ],
            "node_block_subdomain_smoother_ridge_factor": float(
                node_block_subdomain_smoother_ridge_factor
            ),
            "node_block_subdomain_smoother_update_mode_candidates": [
                str(value) for value in subdomain_smoother_update_mode_candidates
            ],
            "node_block_interface_pair_smoother_sweeps": int(
                node_block_interface_pair_smoother_sweeps
            ),
            "node_block_interface_pair_smoother_weight_candidates": [
                float(value) for value in interface_pair_smoother_weight_candidates
            ],
            "node_block_interface_pair_smoother_max_dof_count_candidates": [
                int(value) for value in interface_pair_smoother_max_width_candidates
            ],
            "node_block_interface_pair_smoother_ridge_factor": float(
                node_block_interface_pair_smoother_ridge_factor
            ),
            "node_block_interface_pair_smoother_halo_depth_candidates": [
                int(value) for value in interface_pair_smoother_halo_depth_candidates
            ],
            "node_block_interface_pair_smoother_update_mode_candidates": [
                str(value) for value in interface_pair_smoother_update_mode_candidates
            ],
            "node_block_interface_pair_coarse_rebalance_pass_candidates": [
                int(value) for value in interface_pair_rebalance_pass_candidates
            ],
            "node_block_interface_pair_coarse_rebalance_weight_candidates": [
                float(value) for value in interface_pair_rebalance_weight_candidates
            ],
            "node_block_coarse_weight_candidates": [
                float(value) for value in coarse_weights
            ],
            "node_block_coarse_load_restriction_target_candidates": [
                str(value) for value in coarse_load_restriction_target_candidates
            ],
            "node_block_coarse_local_dof_filter_candidates": [
                str(value) for value in coarse_local_dof_filter_candidates
            ],
            "node_block_coarse_basis_orthogonalization_candidates": [
                str(value) for value in coarse_basis_orthogonalization_candidates
            ],
            "node_block_coarse_harmonic_extension_weight_candidates": [
                float(value) for value in coarse_harmonic_extension_weight_candidates
            ],
            "node_block_coarse_harmonic_extension_step_candidates": [
                int(value) for value in coarse_harmonic_extension_step_candidates
            ],
            "node_block_coarse_correction_pass_candidates": [
                int(value) for value in coarse_correction_pass_candidates
            ],
            "node_block_coarse_smoothing_weight_candidates": [
                float(value) for value in coarse_smoothing_weights
            ],
            "node_block_coarse_mode": str(node_block_coarse_mode),
            "node_block_coarse_energy_modes_per_dof_candidates": [
                int(value) for value in coarse_energy_modes_per_dof_candidates
            ],
            "node_block_coarse_energy_mode_selection_candidates": [
                str(value) for value in coarse_energy_mode_selection_candidates
            ],
            "node_block_coarse_schur_cycle_pass_candidates": [
                int(value) for value in coarse_schur_cycle_pass_candidates
            ],
            "node_block_coarse_schur_cycle_weight_candidates": [
                float(value) for value in coarse_schur_cycle_weight_candidates
            ],
            "node_block_coarse_overlap_depth": int(node_block_coarse_overlap_depth),
            "node_block_coarse_secondary_mode": str(node_block_coarse_secondary_mode),
            "node_block_coarse_secondary_weight": float(node_block_coarse_secondary_weight),
            "node_block_coarse_secondary_correction_passes": int(
                node_block_coarse_secondary_correction_passes
            ),
        },
        "rows": rows,
        "best_row": best_row,
        "recycled_krylov_frontier_improved": bool(
            best_row
            and isinstance(previous_best, (int, float))
            and float(best_row["best_residual_inf_n"]) < float(previous_best)
        ),
        "blockers": [] if converged else [f"g9_{matrix_family}_residual_gate_not_closed"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--matrix-family",
        choices=("surface_shell_bending_6dof", "coupled_frame_shell_6dof"),
        default="surface_shell_bending_6dof",
    )
    parser.add_argument("--basis-sizes", default="8")
    parser.add_argument("--sources", default="residual_and_preconditioned")
    parser.add_argument("--ridge-factors", default="1e-10")
    parser.add_argument("--alpha-values", default="1")
    parser.add_argument("--correction-passes", type=int, default=1)
    parser.add_argument("--min-relative-improvement", type=float, default=1.0e-8)
    parser.add_argument("--restart-dimension", type=int, default=32)
    parser.add_argument("--restart-cycles", type=int, default=3)
    parser.add_argument("--inner-jacobi-steps", type=int, default=12)
    parser.add_argument("--inner-jacobi-weight", type=float, default=0.35)
    parser.add_argument("--schur-basis-aggregate-count", type=int, default=0)
    parser.add_argument(
        "--schur-basis-aggregate-counts",
        default="",
        help="Comma-separated Schur projected-basis aggregate counts to sweep; overrides --schur-basis-aggregate-count when set.",
    )
    parser.add_argument(
        "--schur-basis-selection",
        choices=(
            "algebraic",
            "rhs_weighted",
            "rhs_signed_weighted",
            "mixed_rhs",
            "mixed_rhs_signed",
        ),
        default="algebraic",
    )
    parser.add_argument(
        "--schur-basis-selections",
        default="",
        help="Comma-separated Schur projected-basis selection modes to sweep; overrides --schur-basis-selection when set.",
    )
    parser.add_argument("--schur-basis-ridge-factor", type=float, default=1.0e-10)
    parser.add_argument("--schur-basis-weight", type=float, default=1.0)
    parser.add_argument(
        "--schur-basis-weights",
        default="",
        help="Comma-separated Schur projected-basis correction weights to sweep; overrides --schur-basis-weight when set.",
    )
    parser.add_argument("--coupling-hotspot-correction-size", type=int, default=0)
    parser.add_argument(
        "--coupling-hotspot-correction-sizes",
        default="",
        help="Comma-separated coupling-hotspot dense correction sizes to sweep.",
    )
    parser.add_argument(
        "--coupling-hotspot-selection",
        choices=("coupling_strength", "rhs_residual", "mixed"),
        default="coupling_strength",
    )
    parser.add_argument(
        "--coupling-hotspot-selections",
        default="",
        help="Comma-separated coupling-hotspot selection modes to sweep.",
    )
    parser.add_argument("--coupling-hotspot-ridge-factor", type=float, default=1.0e-10)
    parser.add_argument("--coupling-hotspot-post-passes", type=int, default=0)
    parser.add_argument(
        "--coupling-hotspot-post-pass-values",
        default="",
        help="Comma-separated post-coarse coupling-hotspot polish pass counts to sweep.",
    )
    parser.add_argument("--coupling-hotspot-post-correction-size", type=int, default=0)
    parser.add_argument(
        "--coupling-hotspot-post-correction-sizes",
        default="",
        help="Comma-separated post-interface coupling-hotspot correction sizes to sweep.",
    )
    parser.add_argument(
        "--coupling-hotspot-post-selection",
        choices=("", "coupling_strength", "rhs_residual", "mixed"),
        default="",
    )
    parser.add_argument(
        "--coupling-hotspot-post-selections",
        default="",
        help="Comma-separated post-interface coupling-hotspot selection modes to sweep.",
    )
    parser.add_argument("--coupling-pair-smoother-count", type=int, default=0)
    parser.add_argument(
        "--coupling-pair-smoother-counts",
        default="",
        help="Comma-separated translation-rotation coupling-pair smoother counts to sweep.",
    )
    parser.add_argument("--coupling-pair-smoother-sweeps", type=int, default=0)
    parser.add_argument("--coupling-pair-smoother-weight", type=float, default=1.0)
    parser.add_argument(
        "--coupling-pair-smoother-weights",
        default="",
        help="Comma-separated coupling-pair smoother weights to sweep.",
    )
    parser.add_argument("--coupling-pair-smoother-ridge-factor", type=float, default=1.0e-10)
    parser.add_argument(
        "--coupling-pair-smoother-selection",
        choices=("coupling_strength", "rhs_weighted", "mixed"),
        default="coupling_strength",
    )
    parser.add_argument(
        "--coupling-pair-smoother-selections",
        default="",
        help="Comma-separated coupling-pair smoother selection modes to sweep.",
    )
    parser.add_argument("--coupling-pair-basis-count", type=int, default=0)
    parser.add_argument(
        "--coupling-pair-basis-counts",
        default="",
        help="Comma-separated translation-rotation coupling-pair projected-basis counts to sweep.",
    )
    parser.add_argument(
        "--coupling-pair-basis-selection",
        choices=("coupling_strength", "rhs_weighted", "mixed"),
        default="coupling_strength",
    )
    parser.add_argument(
        "--coupling-pair-basis-selections",
        default="",
        help="Comma-separated coupling-pair projected-basis selection modes to sweep.",
    )
    parser.add_argument("--coupling-pair-basis-weight", type=float, default=1.0)
    parser.add_argument(
        "--coupling-pair-basis-weights",
        default="",
        help="Comma-separated coupling-pair projected-basis correction weights to sweep.",
    )
    parser.add_argument("--coupling-pair-basis-ridge-factor", type=float, default=1.0e-10)
    parser.add_argument("--node-block-smoother-sweeps", type=int, default=0)
    parser.add_argument("--node-block-smoother-weight", type=float, default=1.0)
    parser.add_argument("--node-block-subdomain-smoother-sweeps", type=int, default=0)
    parser.add_argument("--node-block-subdomain-smoother-weight", type=float, default=1.0)
    parser.add_argument(
        "--node-block-subdomain-smoother-weights",
        default="",
        help="Comma-separated bounded subdomain Schwarz smoother weights to sweep.",
    )
    parser.add_argument("--node-block-subdomain-smoother-max-dof-count", type=int, default=96)
    parser.add_argument(
        "--node-block-subdomain-smoother-max-dof-counts",
        default="",
        help="Comma-separated max dense local DOF widths for bounded subdomain Schwarz smoothing.",
    )
    parser.add_argument("--node-block-subdomain-smoother-ridge-factor", type=float, default=1.0e-10)
    parser.add_argument(
        "--node-block-subdomain-smoother-update-mode",
        default="additive",
        choices=("additive", "multiplicative", "swept", "gauss_seidel"),
    )
    parser.add_argument(
        "--node-block-subdomain-smoother-update-modes",
        default="",
        help="Comma-separated subdomain Schwarz update modes: additive or multiplicative.",
    )
    parser.add_argument("--node-block-interface-pair-smoother-sweeps", type=int, default=0)
    parser.add_argument("--node-block-interface-pair-smoother-weight", type=float, default=1.0)
    parser.add_argument(
        "--node-block-interface-pair-smoother-weights",
        default="",
        help="Comma-separated interface-pair DD smoother weights to sweep.",
    )
    parser.add_argument("--node-block-interface-pair-smoother-max-dof-count", type=int, default=128)
    parser.add_argument(
        "--node-block-interface-pair-smoother-max-dof-counts",
        default="",
        help="Comma-separated max dense DOF widths for interface-pair DD smoothing.",
    )
    parser.add_argument(
        "--node-block-interface-pair-smoother-ridge-factor",
        type=float,
        default=1.0e-10,
    )
    parser.add_argument("--node-block-interface-pair-smoother-halo-depth", type=int, default=0)
    parser.add_argument(
        "--node-block-interface-pair-smoother-halo-depth-values",
        default="",
        help="Comma-separated interface-pair graph halo depths to sweep.",
    )
    parser.add_argument(
        "--node-block-interface-pair-smoother-update-mode",
        choices=("additive", "multiplicative"),
        default="additive",
    )
    parser.add_argument(
        "--node-block-interface-pair-smoother-update-modes",
        default="",
        help="Comma-separated interface-pair smoother update modes to sweep.",
    )
    parser.add_argument(
        "--node-block-interface-pair-coarse-rebalance-passes",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--node-block-interface-pair-coarse-rebalance-pass-values",
        default="",
        help="Comma-separated coarse rebalance pass counts after interface-pair smoothing.",
    )
    parser.add_argument(
        "--node-block-interface-pair-coarse-rebalance-weight",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--node-block-interface-pair-coarse-rebalance-weights",
        default="",
        help="Comma-separated coarse rebalance weights after interface-pair smoothing.",
    )
    parser.add_argument("--node-block-coarse-aggregate-count", type=int, default=0)
    parser.add_argument(
        "--node-block-coarse-aggregate-counts",
        default="",
        help="Comma-separated aggregate counts to sweep; overrides --node-block-coarse-aggregate-count when set.",
    )
    parser.add_argument("--node-block-coarse-ridge-factor", type=float, default=1.0e-10)
    parser.add_argument(
        "--node-block-coarse-order",
        choices=("coarse_then_smooth", "smooth_then_coarse", "smooth_coarse_smooth"),
        default="coarse_then_smooth",
    )
    parser.add_argument("--node-block-coarse-correction-passes", type=int, default=1)
    parser.add_argument(
        "--node-block-coarse-correction-pass-values",
        default="",
        help="Comma-separated coarse correction pass counts to sweep.",
    )
    parser.add_argument(
        "--node-block-coarse-load-restriction-target",
        choices=("load", "residual"),
        default="load",
    )
    parser.add_argument(
        "--node-block-coarse-load-restriction-targets",
        default="",
        help="Comma-separated load-restriction targets to sweep.",
    )
    parser.add_argument("--node-block-coarse-smoothing-steps", type=int, default=0)
    parser.add_argument("--node-block-coarse-smoothing-weight", type=float, default=0.0)
    parser.add_argument(
        "--node-block-coarse-smoothing-weights",
        default="",
        help="Comma-separated prolongation smoothing weights to sweep; overrides --node-block-coarse-smoothing-weight when set.",
    )
    parser.add_argument("--node-block-coarse-weight", type=float, default=1.0)
    parser.add_argument(
        "--node-block-coarse-weights",
        default="",
        help="Comma-separated coarse correction weights to sweep; overrides --node-block-coarse-weight when set.",
    )
    parser.add_argument(
        "--node-block-coarse-basis-orthogonalization",
        choices=("none", "qr", "energy"),
        default="none",
    )
    parser.add_argument(
        "--node-block-coarse-basis-orthogonalizations",
        default="",
        help="Comma-separated coarse basis orthogonalization modes to sweep.",
    )
    parser.add_argument(
        "--node-block-coarse-harmonic-extension-weight",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--node-block-coarse-harmonic-extension-weights",
        default="",
        help="Comma-separated harmonic GENEO extension weights to sweep.",
    )
    parser.add_argument(
        "--node-block-coarse-harmonic-extension-steps",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--node-block-coarse-harmonic-extension-step-values",
        default="",
        help="Comma-separated harmonic GENEO extension depths to sweep.",
    )
    parser.add_argument("--node-block-coarse-schur-cycle-passes", type=int, default=0)
    parser.add_argument(
        "--node-block-coarse-schur-cycle-pass-values",
        default="",
        help="Comma-separated residual Schur-after-coarse cycle pass counts to sweep.",
    )
    parser.add_argument("--node-block-coarse-schur-cycle-weight", type=float, default=1.0)
    parser.add_argument(
        "--node-block-coarse-schur-cycle-weights",
        default="",
        help="Comma-separated residual Schur-after-coarse cycle weights to sweep.",
    )
    parser.add_argument(
        "--node-block-coarse-partition",
        choices=("sorted_node_id", "matrix_rcm", "graph_bfs", "rhs_graph_bfs"),
        default="sorted_node_id",
    )
    parser.add_argument("--node-block-coarse-overlap-depth", type=int, default=0)
    parser.add_argument(
        "--node-block-coarse-mode",
        choices=(
            "constant",
            "interface_split",
            "interface_boundary",
            "interface_edge",
            "interface_edge_energy_restricted",
            "interface_edge_geneo_restricted",
            "interface_edge_geneo_harmonic_restricted",
            "interface_edge_rhs_enriched",
            "interface_edge_rhs_enriched_restricted",
            "interface_edge_rhs_enriched_orthogonalized",
            "interface_edge_rhs_weighted",
            "interface_edge_rhs_signed",
            "rigid_body",
            "rigid_body_plus_constant",
            "affine_dof",
        ),
        default="constant",
    )
    parser.add_argument("--node-block-coarse-energy-modes-per-dof", type=int, default=2)
    parser.add_argument(
        "--node-block-coarse-local-dof-filter",
        choices=("all", "translations", "rotations"),
        default="all",
    )
    parser.add_argument(
        "--node-block-coarse-local-dof-filters",
        default="",
        help="Comma-separated local DOF filters for interface/GENEO coarse modes.",
    )
    parser.add_argument(
        "--node-block-coarse-energy-modes-per-dof-values",
        default="",
        help="Comma-separated energy/GENEO local mode counts per interface DOF to sweep.",
    )
    parser.add_argument(
        "--node-block-coarse-energy-mode-selection",
        choices=("low_eigen", "rhs_projection", "rhs_energy_score"),
        default="low_eigen",
    )
    parser.add_argument(
        "--node-block-coarse-energy-mode-selections",
        default="",
        help="Comma-separated local energy/GENEO mode ordering policies to sweep.",
    )
    parser.add_argument(
        "--node-block-coarse-secondary-mode",
        choices=("", "interface_edge_rhs_enriched_restricted"),
        default="",
    )
    parser.add_argument("--node-block-coarse-secondary-weight", type=float, default=0.0)
    parser.add_argument(
        "--node-block-coarse-secondary-correction-passes",
        type=int,
        default=1,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run_mgt_dof_block_schur_recycled_krylov_focused_probe(
        roundtrip_json=args.roundtrip_json,
        output_json=args.output_json,
        matrix_family=args.matrix_family,
        basis_sizes=_parse_ints(args.basis_sizes) or (8,),
        sources=tuple(
            value.strip() for value in str(args.sources).split(",") if value.strip()
        )
        or ("residual_and_preconditioned",),
        ridge_factors=_parse_floats(args.ridge_factors) or (1.0e-10,),
        alpha_values=_parse_floats(args.alpha_values) or (1.0,),
        correction_passes=args.correction_passes,
        min_relative_improvement=args.min_relative_improvement,
        restart_dimension=args.restart_dimension,
        restart_cycles=args.restart_cycles,
        inner_jacobi_steps=args.inner_jacobi_steps,
        inner_jacobi_weight=args.inner_jacobi_weight,
        schur_basis_aggregate_count=args.schur_basis_aggregate_count,
        schur_basis_aggregate_counts=_parse_ints(args.schur_basis_aggregate_counts) or None,
        schur_basis_selection=args.schur_basis_selection,
        schur_basis_selections=tuple(
            value.strip() for value in str(args.schur_basis_selections).split(",") if value.strip()
        )
        or None,
        schur_basis_ridge_factor=args.schur_basis_ridge_factor,
        schur_basis_weight=args.schur_basis_weight,
        schur_basis_weights=_parse_floats(args.schur_basis_weights) or None,
        coupling_hotspot_correction_size=args.coupling_hotspot_correction_size,
        coupling_hotspot_correction_sizes=_parse_ints(args.coupling_hotspot_correction_sizes) or None,
        coupling_hotspot_selection=args.coupling_hotspot_selection,
        coupling_hotspot_selections=tuple(
            value.strip()
            for value in str(args.coupling_hotspot_selections).split(",")
            if value.strip()
        )
        or None,
        coupling_hotspot_ridge_factor=args.coupling_hotspot_ridge_factor,
        coupling_hotspot_post_passes=args.coupling_hotspot_post_passes,
        coupling_hotspot_post_passes_values=_parse_ints(args.coupling_hotspot_post_pass_values) or None,
        coupling_hotspot_post_correction_size=args.coupling_hotspot_post_correction_size,
        coupling_hotspot_post_correction_sizes=_parse_ints(args.coupling_hotspot_post_correction_sizes) or None,
        coupling_hotspot_post_selection=args.coupling_hotspot_post_selection,
        coupling_hotspot_post_selections=tuple(
            value.strip()
            for value in str(args.coupling_hotspot_post_selections).split(",")
            if value.strip()
        )
        or None,
        coupling_pair_smoother_count=args.coupling_pair_smoother_count,
        coupling_pair_smoother_counts=_parse_ints(args.coupling_pair_smoother_counts) or None,
        coupling_pair_smoother_sweeps=args.coupling_pair_smoother_sweeps,
        coupling_pair_smoother_weight=args.coupling_pair_smoother_weight,
        coupling_pair_smoother_weights=_parse_floats(args.coupling_pair_smoother_weights) or None,
        coupling_pair_smoother_ridge_factor=args.coupling_pair_smoother_ridge_factor,
        coupling_pair_smoother_selection=args.coupling_pair_smoother_selection,
        coupling_pair_smoother_selections=tuple(
            value.strip()
            for value in str(args.coupling_pair_smoother_selections).split(",")
            if value.strip()
        )
        or None,
        coupling_pair_basis_count=args.coupling_pair_basis_count,
        coupling_pair_basis_counts=_parse_ints(args.coupling_pair_basis_counts) or None,
        coupling_pair_basis_selection=args.coupling_pair_basis_selection,
        coupling_pair_basis_selections=tuple(
            value.strip()
            for value in str(args.coupling_pair_basis_selections).split(",")
            if value.strip()
        )
        or None,
        coupling_pair_basis_weight=args.coupling_pair_basis_weight,
        coupling_pair_basis_weights=_parse_floats(args.coupling_pair_basis_weights) or None,
        coupling_pair_basis_ridge_factor=args.coupling_pair_basis_ridge_factor,
        node_block_smoother_sweeps=args.node_block_smoother_sweeps,
        node_block_smoother_weight=args.node_block_smoother_weight,
        node_block_subdomain_smoother_sweeps=args.node_block_subdomain_smoother_sweeps,
        node_block_subdomain_smoother_weight=args.node_block_subdomain_smoother_weight,
        node_block_subdomain_smoother_weights=_parse_floats(
            args.node_block_subdomain_smoother_weights
        )
        or None,
        node_block_subdomain_smoother_max_dof_count=args.node_block_subdomain_smoother_max_dof_count,
        node_block_subdomain_smoother_max_dof_counts=_parse_ints(
            args.node_block_subdomain_smoother_max_dof_counts
        )
        or None,
        node_block_subdomain_smoother_ridge_factor=args.node_block_subdomain_smoother_ridge_factor,
        node_block_subdomain_smoother_update_mode=args.node_block_subdomain_smoother_update_mode,
        node_block_subdomain_smoother_update_modes=_parse_strings(
            args.node_block_subdomain_smoother_update_modes
        )
        or None,
        node_block_interface_pair_smoother_sweeps=args.node_block_interface_pair_smoother_sweeps,
        node_block_interface_pair_smoother_weight=args.node_block_interface_pair_smoother_weight,
        node_block_interface_pair_smoother_weights=_parse_floats(
            args.node_block_interface_pair_smoother_weights
        )
        or None,
        node_block_interface_pair_smoother_max_dof_count=(
            args.node_block_interface_pair_smoother_max_dof_count
        ),
        node_block_interface_pair_smoother_max_dof_counts=_parse_ints(
            args.node_block_interface_pair_smoother_max_dof_counts
        )
        or None,
        node_block_interface_pair_smoother_ridge_factor=(
            args.node_block_interface_pair_smoother_ridge_factor
        ),
        node_block_interface_pair_smoother_halo_depth=(
            args.node_block_interface_pair_smoother_halo_depth
        ),
        node_block_interface_pair_smoother_halo_depth_values=_parse_ints(
            args.node_block_interface_pair_smoother_halo_depth_values
        )
        or None,
        node_block_interface_pair_smoother_update_mode=(
            args.node_block_interface_pair_smoother_update_mode
        ),
        node_block_interface_pair_smoother_update_modes=_parse_strings(
            args.node_block_interface_pair_smoother_update_modes
        )
        or None,
        node_block_interface_pair_coarse_rebalance_passes=(
            args.node_block_interface_pair_coarse_rebalance_passes
        ),
        node_block_interface_pair_coarse_rebalance_pass_values=_parse_ints(
            args.node_block_interface_pair_coarse_rebalance_pass_values
        )
        or None,
        node_block_interface_pair_coarse_rebalance_weight=(
            args.node_block_interface_pair_coarse_rebalance_weight
        ),
        node_block_interface_pair_coarse_rebalance_weights=_parse_floats(
            args.node_block_interface_pair_coarse_rebalance_weights
        )
        or None,
        node_block_coarse_aggregate_count=args.node_block_coarse_aggregate_count,
        node_block_coarse_aggregate_counts=_parse_ints(args.node_block_coarse_aggregate_counts) or None,
        node_block_coarse_ridge_factor=args.node_block_coarse_ridge_factor,
        node_block_coarse_order=args.node_block_coarse_order,
        node_block_coarse_correction_passes=args.node_block_coarse_correction_passes,
        node_block_coarse_correction_pass_values=_parse_ints(
            args.node_block_coarse_correction_pass_values
        )
        or None,
        node_block_coarse_load_restriction_target=(
            args.node_block_coarse_load_restriction_target
        ),
        node_block_coarse_load_restriction_targets=_parse_strings(
            args.node_block_coarse_load_restriction_targets
        )
        or None,
        node_block_coarse_smoothing_steps=args.node_block_coarse_smoothing_steps,
        node_block_coarse_smoothing_weight=args.node_block_coarse_smoothing_weight,
        node_block_coarse_smoothing_weights=_parse_floats(args.node_block_coarse_smoothing_weights) or None,
        node_block_coarse_partition=args.node_block_coarse_partition,
        node_block_coarse_overlap_depth=args.node_block_coarse_overlap_depth,
        node_block_coarse_mode=args.node_block_coarse_mode,
        node_block_coarse_local_dof_filter=args.node_block_coarse_local_dof_filter,
        node_block_coarse_local_dof_filters=_parse_strings(
            args.node_block_coarse_local_dof_filters
        )
        or None,
        node_block_coarse_energy_modes_per_dof=args.node_block_coarse_energy_modes_per_dof,
        node_block_coarse_energy_modes_per_dof_values=_parse_ints(
            args.node_block_coarse_energy_modes_per_dof_values
        )
        or None,
        node_block_coarse_energy_mode_selection=args.node_block_coarse_energy_mode_selection,
        node_block_coarse_energy_mode_selections=_parse_strings(
            args.node_block_coarse_energy_mode_selections
        )
        or None,
        node_block_coarse_weight=args.node_block_coarse_weight,
        node_block_coarse_weights=_parse_floats(args.node_block_coarse_weights) or None,
        node_block_coarse_basis_orthogonalization=(
            args.node_block_coarse_basis_orthogonalization
        ),
        node_block_coarse_basis_orthogonalizations=_parse_strings(
            args.node_block_coarse_basis_orthogonalizations
        )
        or None,
        node_block_coarse_harmonic_extension_weight=(
            args.node_block_coarse_harmonic_extension_weight
        ),
        node_block_coarse_harmonic_extension_weights=_parse_floats(
            args.node_block_coarse_harmonic_extension_weights
        )
        or None,
        node_block_coarse_harmonic_extension_steps=(
            args.node_block_coarse_harmonic_extension_steps
        ),
        node_block_coarse_harmonic_extension_step_values=_parse_ints(
            args.node_block_coarse_harmonic_extension_step_values
        )
        or None,
        node_block_coarse_schur_cycle_passes=args.node_block_coarse_schur_cycle_passes,
        node_block_coarse_schur_cycle_pass_values=_parse_ints(
            args.node_block_coarse_schur_cycle_pass_values
        )
        or None,
        node_block_coarse_schur_cycle_weight=args.node_block_coarse_schur_cycle_weight,
        node_block_coarse_schur_cycle_weights=_parse_floats(
            args.node_block_coarse_schur_cycle_weights
        )
        or None,
        node_block_coarse_secondary_mode=args.node_block_coarse_secondary_mode,
        node_block_coarse_secondary_weight=args.node_block_coarse_secondary_weight,
        node_block_coarse_secondary_correction_passes=(
            args.node_block_coarse_secondary_correction_passes
        ),
    )
    best = payload.get("best_row") if isinstance(payload.get("best_row"), dict) else {}
    print(
        "mgt-dof-block-schur-recycled-krylov: "
        f"{payload['status']} best={best.get('best_residual_inf_n')} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
