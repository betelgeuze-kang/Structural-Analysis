#!/usr/bin/env python3
"""Build material/section/element tangent support matrix for the MGT solver lane."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "material-element-tangent-support-matrix.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _element_type_counts(roundtrip: dict[str, Any]) -> Counter[str]:
    elements = roundtrip.get("model", {}).get("elements") if isinstance(roundtrip.get("model"), dict) else []
    counts: Counter[str] = Counter()
    for row in elements or []:
        if not isinstance(row, dict):
            continue
        counts[str(row.get("type") or row.get("family") or "UNKNOWN").upper()] += 1
    return counts


def _coverage_for_code(
    *,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    code: int,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    idx = np.where(np.asarray(elem_type_code, dtype=np.int32) == int(code))[0]
    total = int(idx.size)
    if total == 0:
        return {
            "element_count": 0,
            "section_material_coverage_count": 0,
            "section_material_coverage_pct": 0.0,
            "missing_section_id_count": 0,
            "missing_material_id_count": 0,
        }
    missing_sections = {
        int(elem_section_id[i])
        for i in idx
        if int(elem_section_id[i]) not in section_props
    }
    missing_materials = {
        int(elem_material_id[i])
        for i in idx
        if int(elem_material_id[i]) not in material_props
    }
    covered = sum(
        1
        for i in idx
        if int(elem_section_id[i]) in section_props and int(elem_material_id[i]) in material_props
    )
    return {
        "element_count": total,
        "section_material_coverage_count": int(covered),
        "section_material_coverage_pct": 100.0 * float(covered) / float(total),
        "missing_section_id_count": len(missing_sections),
        "missing_material_id_count": len(missing_materials),
        "missing_section_id_head": sorted(missing_sections)[:10],
        "missing_material_id_head": sorted(missing_materials)[:10],
    }


def build_material_element_tangent_support_matrix(
    *,
    productization_dir: Path = PRODUCTIZATION,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    roundtrip_npz = roundtrip_json.with_suffix(".npz")
    roundtrip = _load(roundtrip_json)
    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = load_mgt_section_material_properties(mgt_path) if mgt_path.is_file() else {"sections": {}, "materials": {}}
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    native_3d = _load(productization_dir / "mgt_global_fea_3d_native_solve.json")
    mesh = native_3d.get("mesh_3d_global_solve") if isinstance(native_3d.get("mesh_3d_global_solve"), dict) else {}
    surface_membrane = _load(productization_dir / "mgt_surface_membrane_tangent.json")
    surface_shell_bending = _load(productization_dir / "mgt_surface_shell_bending_tangent.json")
    shell_calibration = _load(productization_dir / "mgt_shell_calibration_benchmarks.json")
    coupled_frame_shell = _load(productization_dir / "mgt_coupled_frame_shell_sparse_equilibrium.json")
    frame_material_nonlinear = _load(productization_dir / "mgt_frame_material_nonlinear_tangent.json")
    shell_material_nonlinear = _load(productization_dir / "mgt_shell_material_nonlinear_tangent.json")
    local_axis_opening = _load(productization_dir / "mgt_element_local_axis_opening_semantics_receipt.json")
    surface_membrane_ready = bool(
        surface_membrane.get("status") == "ready"
        and surface_membrane.get("surface_membrane_tangent_ready")
        and surface_membrane.get("surface_membrane_smoke_solve_ready")
    )
    surface_shell_bending_ready = bool(
        surface_shell_bending.get("status") == "ready"
        and surface_shell_bending.get("surface_shell_bending_drilling_smoke_ready")
        and surface_shell_bending.get("surface_shell_transverse_pressure_smoke_ready")
    )
    shell_calibration_ready = bool(
        shell_calibration.get("status") == "ready"
        and shell_calibration.get("shell_calibration_benchmarks_ready")
    )
    coupled_frame_shell_ready = bool(
        coupled_frame_shell.get("status") == "ready"
        and coupled_frame_shell.get("coupled_frame_shell_sparse_equilibrium_ready")
        and coupled_frame_shell.get("surface_shell_bending_drilling_coupled_ready")
    )
    frame_material_nonlinear_ready = bool(
        frame_material_nonlinear.get("status") == "ready"
        and frame_material_nonlinear.get("frame_material_nonlinear_tangent_ready")
        and frame_material_nonlinear.get("bounded_material_tangent_global_smoke_ready")
        and frame_material_nonlinear.get("local_constitutive_tangent_fd_consistency_ready")
        and frame_material_nonlinear.get("global_axial_stress_correction_fd_consistency_ready")
    )
    shell_material_nonlinear_ready = bool(
        shell_material_nonlinear.get("status") == "ready"
        and shell_material_nonlinear.get("shell_material_nonlinear_tangent_ready")
        and shell_material_nonlinear.get("bounded_shell_material_tangent_smoke_ready")
        and shell_material_nonlinear.get("local_constitutive_tangent_fd_consistency_ready")
        and shell_material_nonlinear.get("fixed_tangent_global_shell_jvp_consistency_ready")
    )
    frame_local_axis_ready = bool(
        local_axis_opening.get("status") in {"ready", "partial"}
        and ((local_axis_opening.get("support") or {}).get("frame_angle_solver_consumption_ready"))
    )
    surface_lcaxis_parser_ready = bool(
        (local_axis_opening.get("support") or {}).get("surface_lcaxis_parser_ready")
    )
    surface_membrane_material = (
        surface_membrane.get("surface_material_coverage")
        if isinstance(surface_membrane.get("surface_material_coverage"), dict)
        else {}
    )
    surface_shell_material = (
        surface_shell_bending.get("surface_material_coverage")
        if isinstance(surface_shell_bending.get("surface_material_coverage"), dict)
        else {}
    )
    source_thickness_coverage_pct = max(
        float(surface_membrane_material.get("source_plate_thickness_coverage_pct") or 0.0),
        float(surface_shell_material.get("source_plate_thickness_coverage_pct") or 0.0),
    )
    source_thickness_ready = bool(surface_membrane_ready and source_thickness_coverage_pct >= 99.0)
    source_thickness_policy = str(
        surface_shell_material.get("thickness_policy")
        or surface_membrane_material.get("thickness_policy")
        or ""
    )

    element_type_counts = _element_type_counts(roundtrip)
    if not roundtrip_npz.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["roundtrip_npz_missing"],
        }
    else:
        with np.load(roundtrip_npz, allow_pickle=False) as archive:
            elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
            elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
            elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
        line_coverage = _coverage_for_code(
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            code=1,
            section_props=section_props,
            material_props=material_props,
        )
        surface_coverage = _coverage_for_code(
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            code=2,
            section_props=section_props,
            material_props=material_props,
        )
        line_tangent_ready = bool(
            mesh.get("used_real_section_properties")
            and float(mesh.get("real_section_property_coverage_pct") or 0.0) >= 99.0
            and not bool(mesh.get("fell_back_to_linear_tangent"))
            and float(line_coverage["section_material_coverage_pct"]) >= 95.0
        )
        unsupported_queue = [
            {
                "family": "plate_shell_surface_code2",
                "element_count": surface_coverage["element_count"],
                "status": (
                    "membrane_bending_drilling_calibrated_benchmark_ready_opening_local_axis_unsupported"
                    if surface_shell_bending_ready and source_thickness_ready and shell_calibration_ready
                    else
                    "membrane_bending_drilling_smoke_solved_source_thickness_promoted_full_benchmark_unsupported"
                    if surface_shell_bending_ready and source_thickness_ready
                    else "membrane_bending_drilling_smoke_solved_source_thickness_unsupported"
                    if surface_shell_bending_ready
                    else "membrane_tangent_smoke_solved_bending_drilling_unsupported"
                    if surface_membrane_ready
                    else "unsupported_for_global_tangent"
                ),
                "reason": (
                    "Surface membrane plus bending/drilling smoke solves are attached with source MGT plate "
                    "thickness coverage and shell calibration benchmarks. Opening/local-axis handling, higher-order "
                    "shell breadth, full-load frame-shell nonlinear coupling, and material nonlinear shell behavior "
                    "are not promoted."
                    if surface_shell_bending_ready and source_thickness_ready and shell_calibration_ready
                    else
                    "Surface membrane plus bending/drilling smoke solves are attached with source MGT plate "
                    "thickness coverage and same-node frame-shell sparse coupling, but calibrated shell benchmarks, "
                    "full-load frame-shell nonlinear coupling, and material nonlinear shell behavior are not promoted."
                    if surface_shell_bending_ready and source_thickness_ready and coupled_frame_shell_ready
                    else "Surface membrane plus bending/drilling smoke solves are attached with source MGT plate "
                    "thickness coverage, but same-node frame-shell bending coupling, calibrated shell benchmarks, "
                    "full-load frame-shell nonlinear coupling, and material nonlinear shell behavior are not promoted."
                    if surface_shell_bending_ready and source_thickness_ready
                    else "Surface membrane plus bending/drilling smoke solves are attached, but source thickness "
                    "promotion, calibrated shell benchmarks, full frame-shell coupling, and material nonlinear "
                    "shell behavior are not promoted."
                    if surface_shell_bending_ready
                    else (
                    "Surface membrane tangent smoke solve is attached, but shell bending, drilling DOF, "
                    "transverse pressure, and frame-shell coupling are not promoted."
                    if surface_membrane_ready
                    else "Parsed and exported as surface elements, but not assembled into the current in-repo global tangent."
                    )
                ),
                "required_action_before_claim": (
                    "promote parsed local axes/openings, higher-order shell breadth, and coupled full-load frame-shell Newton"
                    if surface_shell_bending_ready and source_thickness_ready and shell_calibration_ready
                    else
                    "promote calibrated shell benchmarks, local axes/openings, coupled full-load frame-shell Newton"
                    if surface_shell_bending_ready and source_thickness_ready
                    else "promote source thickness/local axes, mesh-quality shell benchmarks, coupled full-load frame-shell Newton"
                    if surface_shell_bending_ready
                    else (
                    "attach bending/drilling/transverse shell stiffness, source thickness promotion, coupled frame-shell benchmarks"
                    if surface_membrane_ready
                    else "attach shell/plate stiffness, drilling DOF policy, local axes, thickness coupling, and benchmark replay"
                    )
                ),
            },
            {
                "family": "nonlinear_rc_steel_composite_material_laws",
                "element_count": int(elem_type_code.size),
                "status": (
                    "bounded_frame_shell_material_nonlinear_tangent_smoke_ready_full_newton_unsupported"
                    if frame_material_nonlinear_ready and shell_material_nonlinear_ready
                    else
                    "bounded_frame_material_nonlinear_tangent_smoke_ready_full_newton_unsupported"
                    if frame_material_nonlinear_ready
                    else "unsupported_for_material_nonlinearity"
                ),
                "reason": (
                    "Frame and shell elements now have bounded material tangent receipts using MGT E/nu and "
                    "material-name grade proxies. Frame evidence includes local constitutive finite-difference "
                    "consistency and global axial stress-correction force/JVP consistency; shell evidence includes "
                    "per-surface-element material tangent consumption, fixed-tangent global shell JVP consistency, "
                    "and a bounded shell tangent smoke solve. Full path-dependent internal-force history, "
                    "fiber/layered shell sections, and production Newton consistent global residual/Jacobian "
                    "benchmarks are not promoted."
                    if frame_material_nonlinear_ready and shell_material_nonlinear_ready
                    else
                    "Frame elements now have a bounded material tangent receipt using MGT E/nu and material-name "
                    "grade proxies with service/probe states, local constitutive finite-difference tangent "
                    "consistency, global axial stress-correction force/JVP consistency, and a global "
                    "bounded tangent smoke solve. Full path-dependent "
                    "internal-force history, fiber sections, shell material nonlinearity, and Newton consistent "
                    "global residual/Jacobian benchmarks are not promoted."
                    if frame_material_nonlinear_ready
                    else "Current tangent uses elastic isotropic E/nu from MGT materials; plasticity/damage/fiber laws are not promoted."
                ),
                "required_action_before_claim": (
                    "promote path-dependent constitutive update, internal-force history variables, fiber/layered-section material tangents, consistent global Newton residual/Jacobian, and regression benchmarks"
                    if frame_material_nonlinear_ready
                    else "attach constitutive update, internal-force history variables, consistent Jacobian, and regression benchmarks"
                ),
            },
            {
                "family": "contact_interface_foundation",
                "element_count": 0,
                "status": "unsupported_or_no_source_rows",
                "reason": "No source rows are normalized into a contact/interface/foundation tangent in this MGT lane.",
                "required_action_before_claim": "normalize source entities and attach contact/interface tangent benchmarks",
            },
        ]
        unsupported_queue_ready = all(row["reason"] and row["required_action_before_claim"] for row in unsupported_queue)
        ready = bool(line_tangent_ready and unsupported_queue_ready)
        material_clause = (
            "bounded frame and shell material tangent smokes are attached; full path-dependent material Newton remains queued"
            if frame_material_nonlinear_ready and shell_material_nonlinear_ready
            else "bounded frame material tangent smoke is attached; shell/full path-dependent material Newton remains queued"
            if frame_material_nonlinear_ready
            else "nonlinear material laws remain explicit unsupported queues"
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "ready" if ready else "partial",
            "line_beam_tangent_ready": line_tangent_ready,
            "unsupported_queue_ready": unsupported_queue_ready,
            "roundtrip_json": str(roundtrip_json),
            "roundtrip_npz": str(roundtrip_npz),
            "mgt_path": str(mgt_path),
            "claim_boundary": (
                "Line/beam-family elastic real-section tangent is productized for the current representative "
                f"MGT solver lane; surface elements are queued and {material_clause}."
                if not surface_membrane_ready
                else "MGT solver lane; surface membrane tangent smoke solve is attached, while bending/drilling "
                f"shell behavior is queued and {material_clause}."
                if not surface_shell_bending_ready
                else (
                    "MGT solver lane; surface membrane, bending/drilling, and same-node frame-shell smoke solves are "
                    "attached with source plate thickness coverage, while calibrated full shell benchmarks, local "
                    f"axes/openings, full-load coupled solves are queued and {material_clause}."
                    if source_thickness_ready and coupled_frame_shell_ready
                    else "MGT solver lane; surface membrane and bending/drilling smoke solves are attached with source "
                    "plate thickness coverage, while same-node frame-shell bending coupling, calibrated full shell "
                    f"benchmarks, local axes/openings, full-load coupled solves are queued and {material_clause}."
                    if source_thickness_ready
                    else "MGT solver lane; surface membrane and bending/drilling smoke solves are attached, while "
                    f"source-thickness promotion and calibrated full shell benchmarks are queued; {material_clause}."
                )
            ),
            "element_inventory": {
                "model_element_type_counts": dict(element_type_counts),
                "npz_element_type_code_counts": {
                    str(int(code)): int(count)
                    for code, count in zip(*np.unique(elem_type_code, return_counts=True))
                },
            },
            "section_material_inventory": {
                "parsed_section_count": len(section_props),
                "parsed_material_count": len(material_props),
                "supported_section_shapes": sorted(
                    {
                        str(row.get("shape") or "UNKNOWN")
                        for row in section_props.values()
                        if isinstance(row, dict)
                    }
                ),
                "supported_material_types": sorted(
                    {
                        str(row.get("type") or "UNKNOWN")
                        for row in material_props.values()
                        if isinstance(row, dict)
                    }
                ),
            },
            "support_matrix": [
                {
                    "family": "line_beam_column_code1",
                    "status": "tangent_coupled",
                    "formulation": "2D beam-column global tangent embedded in 3D MGT component selection",
                    "material_law": "elastic_isotropic_mgt_E_nu",
                    "section_law": "parsed_SB_and_pipe_real_section_properties",
                    "geometric_nonlinearity": "P-delta axial geometric stiffness available for representative component",
                    "frame_local_axis_roll_transform_ready": frame_local_axis_ready,
                    "frame_local_axis_nonzero_angle_count": (
                        (local_axis_opening.get("summary") or {}).get("line_nonzero_angle_row_count")
                    ),
                    "frame_local_axis_max_abs_angle_deg": (
                        (local_axis_opening.get("summary") or {}).get("line_max_abs_angle_deg")
                    ),
                    **line_coverage,
                },
                {
                    "family": "plate_shell_surface_code2",
                    "status": (
                        "membrane_bending_drilling_calibrated_benchmark_ready_opening_local_axis_unsupported"
                        if surface_shell_bending_ready and source_thickness_ready and shell_calibration_ready
                        else "membrane_bending_drilling_smoke_solved_source_thickness_promoted_full_benchmark_unsupported"
                        if surface_shell_bending_ready and source_thickness_ready
                        else "membrane_bending_drilling_smoke_solved_source_thickness_unsupported"
                        if surface_shell_bending_ready
                        else "membrane_tangent_smoke_solved_bending_drilling_unsupported"
                        if surface_membrane_ready
                        else "parsed_exported_not_tangent_coupled"
                    ),
                    "formulation": (
                        "constant_strain_membrane_plus_mindlin_cst_bending_drilling_smoke"
                        if surface_shell_bending_ready
                        else "constant_strain_membrane_triangles_from_plate_quads"
                        if surface_membrane_ready
                        else "unsupported_for_current_global_tangent"
                    ),
                    "material_law": "elastic_isotropic_mgt_E_nu" if surface_membrane_ready else "not_promoted",
                    "section_law": (
                        "source_mgt_thickness_rows_by_plate_section_id"
                        if source_thickness_ready
                        else "deterministic_thickness_fallback_pending_source_thickness_promotion"
                        if surface_membrane_ready
                        else "thickness_rows_parsed_for_authoring_export_only"
                    ),
                    "source_plate_thickness_coverage_pct": source_thickness_coverage_pct,
                    "source_plate_thickness_policy": source_thickness_policy,
                    "surface_membrane_tangent_ready": surface_membrane_ready,
                    "surface_shell_bending_drilling_smoke_ready": surface_shell_bending_ready,
                    "surface_shell_transverse_pressure_smoke_ready": surface_shell_bending.get(
                        "surface_shell_transverse_pressure_smoke_ready"
                    ),
                    "surface_shell_coupled_sparse_equilibrium_ready": coupled_frame_shell_ready,
                    "surface_shell_calibration_benchmarks_ready": shell_calibration_ready,
                    "surface_lcaxis_parser_ready": surface_lcaxis_parser_ready,
                    "surface_lcaxis_source_all_default": (
                        (local_axis_opening.get("support") or {}).get("surface_lcaxis_source_all_default")
                    ),
                    "opening_runtime_semantics_ready": (
                        (local_axis_opening.get("support") or {}).get("opening_runtime_semantics_ready")
                    ),
                    "current_source_opening_noop_runtime_ready": (
                        (local_axis_opening.get("support") or {}).get("current_source_opening_noop_runtime_ready")
                    ),
                    "generic_opening_cutout_runtime_semantics_ready": (
                        (local_axis_opening.get("support") or {}).get(
                            "generic_opening_cutout_runtime_semantics_ready"
                        )
                    ),
                    "shell_calibration_case_count": shell_calibration.get("case_count"),
                    "shell_calibration_ready_case_count": shell_calibration.get("ready_case_count"),
                    "shell_calibration_cases": shell_calibration.get("cases"),
                    "surface_shell_full_bending_tangent_ready": surface_membrane.get(
                        "surface_shell_full_bending_tangent_ready"
                    )
                    or surface_shell_bending.get("surface_shell_full_bending_tangent_ready"),
                    "surface_shell_material_nonlinear_tangent_ready": shell_material_nonlinear_ready,
                    "bounded_shell_material_tangent_smoke_ready": shell_material_nonlinear.get(
                        "bounded_shell_material_tangent_smoke_ready"
                    ),
                    "fixed_tangent_global_shell_jvp_consistency_ready": shell_material_nonlinear.get(
                        "fixed_tangent_global_shell_jvp_consistency_ready"
                    ),
                    "shell_material_state_summary": shell_material_nonlinear.get(
                        "controlled_probe_shell_material_state_summary"
                    ),
                    **surface_coverage,
                },
                {
                    "family": "nonlinear_rc_steel_composite_material_laws",
                    "status": (
                        "bounded_frame_shell_material_nonlinear_tangent_smoke_ready_full_newton_unsupported"
                        if frame_material_nonlinear_ready and shell_material_nonlinear_ready
                        else
                        "bounded_frame_material_nonlinear_tangent_smoke_ready_full_newton_unsupported"
                        if frame_material_nonlinear_ready
                        else "not_promoted"
                    ),
                    "formulation": (
                        "source_material_name_grade_proxy_frame_shell_tangent_smoke"
                        if frame_material_nonlinear_ready and shell_material_nonlinear_ready
                        else
                        "source_material_name_grade_proxy_frame_tangent_smoke"
                        if frame_material_nonlinear_ready
                        else "unsupported_for_current_global_tangent"
                    ),
                    "material_law": (
                        "steel_bilinear_concrete_damage_src_bounded_composite_proxy"
                        if frame_material_nonlinear_ready
                        else "not_promoted"
                    ),
                    "frame_material_nonlinear_tangent_ready": frame_material_nonlinear_ready,
                    "shell_material_nonlinear_tangent_ready": shell_material_nonlinear_ready,
                    "service_load_material_state_ready": frame_material_nonlinear.get(
                        "service_load_material_state_ready"
                    ),
                    "service_shell_material_state_ready": shell_material_nonlinear.get(
                        "service_shell_material_state_ready"
                    ),
                    "controlled_probe_material_state_ready": frame_material_nonlinear.get(
                        "controlled_probe_material_state_ready"
                    ),
                    "controlled_probe_shell_material_state_ready": shell_material_nonlinear.get(
                        "controlled_probe_shell_material_state_ready"
                    ),
                    "bounded_material_tangent_global_smoke_ready": frame_material_nonlinear.get(
                        "bounded_material_tangent_global_smoke_ready"
                    ),
                    "bounded_shell_material_tangent_smoke_ready": shell_material_nonlinear.get(
                        "bounded_shell_material_tangent_smoke_ready"
                    ),
                    "fixed_tangent_global_shell_jvp_consistency_ready": shell_material_nonlinear.get(
                        "fixed_tangent_global_shell_jvp_consistency_ready"
                    ),
                    "full_material_nonlinear_newton_equilibrium": frame_material_nonlinear.get(
                        "full_material_nonlinear_newton_equilibrium"
                    )
                    and shell_material_nonlinear.get("full_material_nonlinear_newton_equilibrium"),
                    "service_material_state_summary": frame_material_nonlinear.get(
                        "service_material_state_summary"
                    ),
                    "service_shell_material_state_summary": shell_material_nonlinear.get(
                        "service_shell_material_state_summary"
                    ),
                    "controlled_probe_material_state_summary": frame_material_nonlinear.get(
                        "controlled_probe_material_state_summary"
                    ),
                    "controlled_probe_shell_material_state_summary": shell_material_nonlinear.get(
                        "controlled_probe_shell_material_state_summary"
                    ),
                    "material_tangent_smoke_equilibrium": frame_material_nonlinear.get(
                        "material_tangent_smoke_equilibrium"
                    ),
                    "shell_material_tangent_smoke_equilibrium": shell_material_nonlinear.get(
                        "material_tangent_shell_equilibrium"
                    ),
                },
            ],
            "native_3d_evidence": {
                "native_solve_status": native_3d.get("native_solve_status"),
                "solve_mode": native_3d.get("solve_mode"),
                "used_real_section_properties": mesh.get("used_real_section_properties"),
                "real_section_property_coverage_pct": mesh.get("real_section_property_coverage_pct"),
                "fell_back_to_linear_tangent": mesh.get("fell_back_to_linear_tangent"),
                "partial_connected_component_mesh": mesh.get("partial_connected_component_mesh"),
            },
            "unsupported_element_material_queue": unsupported_queue,
            "blockers": [] if ready else ["line_beam_tangent_or_unsupported_queue_not_ready"],
        }
    out = output_json or productization_dir / "material_element_tangent_support_matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "material_element_tangent_support_matrix.json")
    args = parser.parse_args()
    payload = build_material_element_tangent_support_matrix(
        productization_dir=args.productization_dir,
        roundtrip_json=args.roundtrip_json,
        output_json=args.output_json,
    )
    print(
        "material-element-tangent-support: "
        f"status={payload['status']} line={payload.get('line_beam_tangent_ready')} "
        f"unsupported_queue={payload.get('unsupported_queue_ready')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
