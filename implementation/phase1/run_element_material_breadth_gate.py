#!/usr/bin/env python3
"""Summarize direct element/material breadth evidence from existing contract reports."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from runtime_contracts import InputContractError, validate_input_contract
try:
    from layered_shell_wall import (
        evaluate_layered_panel_response,
        make_layered_slab_section,
        make_layered_wall_section,
    )
except Exception:  # pragma: no cover - additive fallback when the helper is unavailable.
    evaluate_layered_panel_response = None
    make_layered_slab_section = None
    make_layered_wall_section = None

try:
    from beam_column_nonlinear import (
        BeamColumnProperties,
        solve_beam_column_response,
        solve_beam_column_supported_response,
    )
except Exception:  # pragma: no cover - additive fallback when the helper is unavailable.
    BeamColumnProperties = None
    solve_beam_column_response = None
    solve_beam_column_supported_response = None

try:
    from section_family_library import evaluate_story_section_profile
except Exception:  # pragma: no cover - additive fallback when the helper is unavailable.
    evaluate_story_section_profile = None

try:
    from foundation_link_library import describe_foundation_link_library
except Exception:  # pragma: no cover - additive fallback when the library is unavailable.
    def describe_foundation_link_library() -> dict[str, object]:
        return {}

try:
    from device_library import describe_device_library
except Exception:  # pragma: no cover - additive fallback when the library is unavailable.
    def describe_device_library() -> dict[str, object]:
        return {}


REASONS = {
    "PASS": "direct solver contract coverage is present for shell, wall, structural-contact links, interface/compression-surrogate, and material/link breadth",
    "ERR_INVALID_INPUT": "invalid element/material breadth gate input",
    "ERR_SHELL_DIRECT_COVERAGE": "shell direct solver coverage evidence is missing",
    "ERR_WALL_DIRECT_COVERAGE": "wall direct solver coverage evidence is missing",
    "ERR_CONTACT_INTERFACE_SURROGATE": "contact-related interface/compression surrogate evidence is missing",
    "ERR_FOUNDATION_SOIL_LINK_DIRECT_COVERAGE": "foundation/soil nonlinear link evidence is missing",
    "ERR_MATERIAL_MODEL_BREADTH": "material-model breadth evidence is missing",
    "ERR_STRUCTURAL_CONTACT_DIRECT_COVERAGE": "broader structural-contact link evidence is missing",
    "ERR_LINK_MODEL_BREADTH": "structural-contact link-model breadth evidence is missing",
    "ERR_MATERIAL_CAPABILITY_BREADTH": "material-capability breadth evidence is missing",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "topology_report",
        "flexible_diaphragm_report",
        "pushover_stress_report",
        "ndtha_stress_report",
        "ssi_boundary_report",
        "substructuring_interface_report",
        "wind_time_history_report",
        "special_link_library",
        "structural_contact_validation_report",
        "structural_contact_gate_report",
        "rc_benchmark_lock_report",
        "construction_sequence_report",
        "damper_validation_report",
        "foundation_soil_link_gate_report",
        "benchmark_cases",
        "required_material_models",
        "required_link_models",
        "required_material_capabilities",
        "min_shell_elements",
        "min_shell_beam_mix_cases",
        "min_wall_rows",
        "min_wall_frame_cases",
        "min_compression_surrogate_rows",
        "out",
    ],
    "properties": {
        "topology_report": {"type": "string", "minLength": 1},
        "flexible_diaphragm_report": {"type": "string", "minLength": 1},
        "pushover_stress_report": {"type": "string", "minLength": 1},
        "ndtha_stress_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "substructuring_interface_report": {"type": "string", "minLength": 1},
        "wind_time_history_report": {"type": "string", "minLength": 1},
        "special_link_library": {"type": "string", "minLength": 1},
        "structural_contact_validation_report": {"type": "string", "minLength": 1},
        "structural_contact_gate_report": {"type": "string", "minLength": 1},
        "rc_benchmark_lock_report": {"type": "string", "minLength": 1},
        "construction_sequence_report": {"type": "string", "minLength": 1},
        "damper_validation_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_gate_report": {"type": "string", "minLength": 1},
        "benchmark_cases": {"type": "string", "minLength": 1},
        "required_material_models": {"type": "string", "minLength": 1},
        "required_link_models": {"type": "string", "minLength": 1},
        "required_material_capabilities": {"type": "string", "minLength": 1},
        "min_shell_elements": {"type": "integer", "minimum": 1},
        "min_shell_beam_mix_cases": {"type": "integer", "minimum": 1},
        "min_wall_rows": {"type": "integer", "minimum": 1},
        "min_wall_frame_cases": {"type": "integer", "minimum": 1},
        "min_compression_surrogate_rows": {"type": "integer", "minimum": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_csv(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def _sorted_string_union(*sources: object) -> list[str]:
    merged: set[str] = set()
    for source in sources:
        if isinstance(source, (list, tuple, set)):
            candidates = source
        else:
            continue
        for item in candidates:
            text = str(item).strip()
            if text:
                merged.add(text)
    return sorted(merged)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _iter_wall_family_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    block = payload.get("rows")
    if not isinstance(block, list):
        return rows
    for row in block:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else row
        family_counts = summary.get("section_family_counts")
        if not isinstance(family_counts, dict):
            continue
        wall_counts = {
            str(name): int(count)
            for name, count in family_counts.items()
            if str(name).startswith("wall_")
        }
        if not wall_counts:
            continue
        rows.append(
            {
                "case_id": str(row.get("case_id", summary.get("case_id", ""))),
                "topology_type": str(row.get("topology_type", "")),
                "section_family_counts": wall_counts,
            }
        )
    return rows


def _compression_damage_evidence(payload: dict) -> dict:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    qualifying_rows: list[dict] = []
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        material_indices = summary.get("material_indices") if isinstance(summary.get("material_indices"), dict) else {}
        try:
            compression_damage = float(material_indices.get("compression_damage_mean", 0.0) or 0.0)
        except Exception:
            compression_damage = 0.0
        values.append(compression_damage)
        if compression_damage > 0.0:
            qualifying_rows.append(
                {
                    "case_id": str(row.get("case_id", "")),
                    "topology_type": str(row.get("topology_type", "")),
                    "hazard_type": str(row.get("hazard_type", "")),
                    "compression_damage_mean": compression_damage,
                }
            )
    return {
        "row_count": len(rows),
        "qualifying_row_count": len(qualifying_rows),
        "qualifying_rows": qualifying_rows,
        "compression_damage_mean_min": min(values) if values else 0.0,
        "compression_damage_mean_max": max(values) if values else 0.0,
    }


def _collect_material_models(payload: dict) -> set[str]:
    models: set[str] = set()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    direct_model = summary.get("material_model")
    if isinstance(direct_model, str) and direct_model.strip():
        models.add(direct_model.strip())
    model_types = summary.get("material_model_types")
    if isinstance(model_types, list):
        for item in model_types:
            text = str(item).strip()
            if text:
                models.add(text)
    rows = payload.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_model = row.get("material_model")
            if isinstance(row_model, str) and row_model.strip():
                models.add(row_model.strip())
            row_summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
            row_summary_model = row_summary.get("material_model")
            if isinstance(row_summary_model, str) and row_summary_model.strip():
                models.add(row_summary_model.strip())
    return models


def _add_material_source(models_by_source: dict[str, set[str]], source_name: str, payload: dict) -> None:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    if not bool(payload.get("contract_pass", False)):
        return
    material_model_pass = checks.get("material_model_pass")
    if material_model_pass is not None and not bool(material_model_pass):
        return
    for model in _collect_material_models(payload):
        models_by_source.setdefault(model, set()).add(source_name)


def _aggregate_benchmark_cases(case_paths: list[Path]) -> dict:
    topology_counts: Counter[str] = Counter()
    element_mix_counts: Counter[str] = Counter()
    case_count = 0
    rows_by_file: list[dict] = []

    for path in case_paths:
        payload = _load_json(path)
        rows = payload.get("cases")
        if not isinstance(rows, list):
            rows = []
        file_topology_counts: Counter[str] = Counter()
        file_mix_counts: Counter[str] = Counter()
        for row in rows:
            if not isinstance(row, dict):
                continue
            case_count += 1
            topology = str(row.get("topology_type", "")).strip()
            mix = str(row.get("element_mix", "")).strip()
            if topology:
                topology_counts[topology] += 1
                file_topology_counts[topology] += 1
            if mix:
                element_mix_counts[mix] += 1
                file_mix_counts[mix] += 1
        rows_by_file.append(
            {
                "cases_path": str(path),
                "cases_sha256": _sha256(path) if path.exists() else "",
                "case_count": len(rows),
                "topology_counts": dict(sorted(file_topology_counts.items())),
                "element_mix_counts": dict(sorted(file_mix_counts.items())),
            }
        )

    return {
        "case_count": int(case_count),
        "topology_counts": dict(sorted(topology_counts.items())),
        "element_mix_counts": dict(sorted(element_mix_counts.items())),
        "rows_by_file": rows_by_file,
    }


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _panel_rc_cyclic_surface_summary() -> dict[str, object]:
    if (
        evaluate_layered_panel_response is None
        or make_layered_wall_section is None
        or make_layered_slab_section is None
    ):
        return {
            "present": False,
            "section_count": 0,
            "section_families": [],
            "section_names": [],
            "reversal_count_min": 0,
            "reversal_count_max": 0,
            "min_pinching_ratio": 1.0,
            "max_crushing_ratio": 0.0,
            "max_stiffness_degradation": 0.0,
            "max_strength_degradation": 0.0,
            "evidence_tags": [],
            "total_energy_like": 0.0,
        }

    responses = [
        evaluate_layered_panel_response(
            section=make_layered_wall_section(),
            panel_width_m=3.0,
            panel_height_m=3.5,
            membrane_strain_x=2.5e-4,
            membrane_strain_y=2.0e-4,
            shear_strain_xy=5.0e-5,
            curvature_x_per_m=0.004,
            curvature_y_per_m=0.003,
            diaphragm_strain=0.0,
        ),
        evaluate_layered_panel_response(
            section=make_layered_slab_section(),
            panel_width_m=6.0,
            panel_height_m=4.0,
            membrane_strain_x=2.0e-4,
            membrane_strain_y=1.2e-4,
            shear_strain_xy=8.0e-5,
            curvature_x_per_m=0.003,
            curvature_y_per_m=0.002,
            diaphragm_strain=1.0e-4,
        ),
    ]
    evidence = [response.cyclic_evidence for response in responses if response.cyclic_evidence is not None]
    if not evidence:
        return {
            "present": False,
            "section_count": 0,
            "section_families": [],
            "section_names": [],
            "reversal_count_min": 0,
            "reversal_count_max": 0,
            "min_pinching_ratio": 1.0,
            "max_crushing_ratio": 0.0,
            "max_stiffness_degradation": 0.0,
            "max_strength_degradation": 0.0,
            "evidence_tags": [],
            "total_energy_like": 0.0,
        }

    present = all(
        item.reversal_count >= 1
        and item.pinching_observed
        and item.crushing_observed
        and item.degradation_observed
        for item in evidence
    )
    return {
        "present": bool(present),
        "section_count": len(evidence),
        "section_families": sorted({item.section_family for item in evidence}),
        "section_names": sorted({item.section_name for item in evidence}),
        "reversal_count_min": min(item.reversal_count for item in evidence),
        "reversal_count_max": max(item.reversal_count for item in evidence),
        "min_pinching_ratio": min(item.min_pinching_ratio for item in evidence),
        "max_crushing_ratio": max(item.max_crushing_ratio for item in evidence),
        "max_stiffness_degradation": max(item.max_stiffness_degradation for item in evidence),
        "max_strength_degradation": max(item.max_strength_degradation for item in evidence),
        "evidence_tags": sorted({tag for item in evidence for tag in item.evidence_tags}),
        "total_energy_like": float(sum(item.cyclic_energy_like for item in evidence)),
    }


def _assembled_global_depth_surface_summary() -> dict[str, object]:
    default = {
        "present": False,
        "beam_case_count": 0,
        "beam_iteration_count": 0,
        "beam_yielded_end_count": 0,
        "beam_tangent_scale_min": 0.0,
        "beam_free_dof_residual_max": 0.0,
        "beam_displacement_max_m": 0.0,
        "beam_equilibrium_pass": False,
        "panel_case_count": 0,
        "panel_section_families": [],
        "panel_force_balance_error_max_n": 0.0,
        "panel_corner_force_max_n": 0.0,
        "panel_torsional_case_count": 0,
        "panel_diaphragm_coupling_case_count": 0,
        "panel_force_balance_pass": False,
        "depth_signal_count": 0,
    }
    if (
        BeamColumnProperties is None
        or solve_beam_column_response is None
        or solve_beam_column_supported_response is None
        or evaluate_layered_panel_response is None
        or make_layered_wall_section is None
        or make_layered_slab_section is None
    ):
        return default

    beam_supported_response = solve_beam_column_supported_response(
        props=BeamColumnProperties(
            length_m=4.0,
            area_m2=0.018,
            e_mpa=200000.0,
            iy_m4=6.5e-5,
            yield_moment_kNm=400.0,
            hardening_ratio=0.05,
        ),
        node_i=(0.0, 0.0),
        node_j=(0.0, 4.0),
        external_force_global=[0.0, 0.0, 0.0, 20000.0, 0.0, 40000.0],
        restrained_dofs=(0, 1, 2),
        formulation="force_based",
    )
    beam_probe_response = solve_beam_column_response(
        props=BeamColumnProperties(
            length_m=4.0,
            area_m2=0.018,
            e_mpa=200000.0,
            iy_m4=6.5e-5,
            yield_moment_kNm=120.0,
            hardening_ratio=0.05,
        ),
        deformation_local=np.array([0.0, 0.0, 0.14, 0.0, 0.16, -0.02], dtype=np.float64),
        axial_force_n=1.6e6,
        include_geometric=True,
        formulation="force_based",
    )
    beam_free_dof_residual_max = max(abs(float(value)) for value in beam_supported_response.free_dof_residual)
    beam_displacement_max_m = max(abs(float(value)) for value in beam_supported_response.displacement_global)
    beam_equilibrium_pass = bool(beam_free_dof_residual_max <= 1.0e-6 and beam_supported_response.iteration_count >= 1)

    wall_section = make_layered_wall_section()
    slab_section = make_layered_slab_section()
    panel_cases = [
        (
            wall_section.family,
            evaluate_layered_panel_response(
                section=wall_section,
                panel_width_m=3.0,
                panel_height_m=3.5,
                membrane_strain_x=2.5e-4,
                membrane_strain_y=2.0e-4,
                shear_strain_xy=5.0e-5,
                curvature_x_per_m=0.004,
                curvature_y_per_m=0.003,
                diaphragm_strain=0.0,
            ),
        ),
        (
            slab_section.family,
            evaluate_layered_panel_response(
                section=slab_section,
                panel_width_m=6.0,
                panel_height_m=4.0,
                membrane_strain_x=2.0e-4,
                membrane_strain_y=1.2e-4,
                shear_strain_xy=8.0e-5,
                curvature_x_per_m=0.003,
                curvature_y_per_m=0.002,
                diaphragm_strain=1.0e-4,
            ),
        ),
    ]
    assembled = [response.assembled_response for _, response in panel_cases if response.assembled_response is not None]
    panel_force_balance_error_max_n = max(
        (abs(float(item.force_balance_error_n)) for item in assembled),
        default=0.0,
    )
    panel_corner_force_max_n = max(
        (
            max(abs(float(value)) for value in item.corner_nodal_force_vector_n)
            for item in assembled
        ),
        default=0.0,
    )
    panel_torsional_case_count = sum(abs(float(item.torsional_coupling_moment_n_m)) > 1.0e-9 for item in assembled)
    panel_diaphragm_coupling_case_count = sum(
        max(abs(float(value)) for value in item.diaphragm_coupling_vector_n_per_m) > 1.0e-9
        for item in assembled
    )
    panel_force_balance_pass = bool(panel_force_balance_error_max_n <= 1.0e-6 and len(assembled) == len(panel_cases))
    present = bool(beam_equilibrium_pass and panel_force_balance_pass)
    return {
        "present": present,
        "beam_case_count": 1,
        "beam_iteration_count": int(beam_supported_response.iteration_count),
        "beam_yielded_end_count": int(beam_probe_response.yielded_end_count),
        "beam_tangent_scale_min": float(beam_probe_response.tangent_scale),
        "beam_max_trial_end_moment_ratio": float(np.max(beam_probe_response.trial_end_moment_ratios)),
        "beam_max_plastic_rotation_proxy_rad": float(np.max(beam_probe_response.plastic_rotation_proxy_rad)),
        "beam_stability_index": float(beam_probe_response.stability_index),
        "beam_strain_energy_n_m": float(beam_probe_response.strain_energy_n_m),
        "beam_free_dof_residual_max": float(beam_free_dof_residual_max),
        "beam_displacement_max_m": float(beam_displacement_max_m),
        "beam_equilibrium_pass": beam_equilibrium_pass,
        "panel_case_count": len(assembled),
        "panel_section_families": sorted({family for family, _ in panel_cases}),
        "panel_force_balance_error_max_n": float(panel_force_balance_error_max_n),
        "panel_corner_force_max_n": float(panel_corner_force_max_n),
        "panel_torsional_case_count": int(panel_torsional_case_count),
        "panel_diaphragm_coupling_case_count": int(panel_diaphragm_coupling_case_count),
        "panel_force_balance_pass": panel_force_balance_pass,
        "depth_signal_count": int(1 + len(assembled) + panel_torsional_case_count + panel_diaphragm_coupling_case_count),
    }


def _section_family_demand_surface_summary() -> dict[str, object]:
    default = {
        "present": False,
        "story_count": 0,
        "family_counts": {},
        "beam_tangent_scale_mean": 0.0,
        "beam_tangent_scale_min": 0.0,
        "beam_yielded_story_count": 0,
        "beam_max_trial_end_moment_ratio": 0.0,
        "beam_max_plastic_rotation_proxy_rad": 0.0,
        "beam_stability_index_max": 0.0,
        "beam_strain_energy_total_n_m": 0.0,
    }
    if evaluate_story_section_profile is None:
        return default

    profile = evaluate_story_section_profile(
        topology="wall-frame",
        material_type="rc_composite",
        story_h_m=np.array([3.8, 3.6, 3.5, 3.4, 3.3], dtype=np.float64),
        drift_ratio_profile=np.array([0.012, 0.0105, 0.009, 0.0075, 0.006], dtype=np.float64),
        load_scale=1.15,
    )
    summary = profile.get("summary") if isinstance(profile.get("summary"), dict) else {}
    family_counts = profile.get("family_counts") if isinstance(profile.get("family_counts"), dict) else {}
    present = bool(
        int(summary.get("story_count", 0) or 0) >= 5
        and float(summary.get("beam_tangent_scale_min", 0.0) or 0.0) > 0.0
        and float(summary.get("beam_max_trial_end_moment_ratio", 0.0) or 0.0) > 1.0
        and float(summary.get("beam_strain_energy_total_n_m", 0.0) or 0.0) > 0.0
    )
    return {
        "present": present,
        "story_count": int(summary.get("story_count", 0) or 0),
        "family_counts": {str(name): int(count) for name, count in family_counts.items()},
        "beam_tangent_scale_mean": float(summary.get("beam_tangent_scale_mean", 0.0) or 0.0),
        "beam_tangent_scale_min": float(summary.get("beam_tangent_scale_min", 0.0) or 0.0),
        "beam_yielded_story_count": int(summary.get("beam_yielded_story_count", 0) or 0),
        "beam_max_trial_end_moment_ratio": float(summary.get("beam_max_trial_end_moment_ratio", 0.0) or 0.0),
        "beam_max_plastic_rotation_proxy_rad": float(
            summary.get("beam_max_plastic_rotation_proxy_rad", 0.0) or 0.0
        ),
        "beam_stability_index_max": float(summary.get("beam_stability_index_max", 0.0) or 0.0),
        "beam_strain_energy_total_n_m": float(summary.get("beam_strain_energy_total_n_m", 0.0) or 0.0),
    }


def _beam_shell_contact_coupling_surface_summary(
    assembled_global_depth_summary: dict[str, object],
    structural_contact_summary: dict,
    structural_contact_validation_checks: dict,
    foundation_soil_link_summary: dict,
    foundation_soil_link_checks: dict,
) -> dict[str, object]:
    support_search_model_types = _sorted_string_union(
        structural_contact_summary.get("support_search_model_types"),
        foundation_soil_link_summary.get("support_search_model_types"),
    )
    node_to_surface_proxy_model_types = _sorted_string_union(
        structural_contact_summary.get("node_to_surface_proxy_model_types"),
        foundation_soil_link_summary.get("node_to_surface_proxy_model_types"),
    )
    support_search_family_types = _sorted_string_union(
        structural_contact_summary.get("support_search_family_types"),
        foundation_soil_link_summary.get("support_search_family_types"),
    )
    node_to_surface_proxy_family_types = _sorted_string_union(
        structural_contact_summary.get("node_to_surface_proxy_family_types"),
        foundation_soil_link_summary.get("node_to_surface_proxy_family_types"),
    )
    support_depth_values: list[int] = []
    for source in (structural_contact_summary, foundation_soil_link_summary):
        try:
            support_depth_values.append(int(source.get("support_depth_score", 0) or 0))
        except Exception:
            support_depth_values.append(0)
    support_depth_score = max(support_depth_values, default=0)
    beam_signal_present = bool(
        assembled_global_depth_summary.get("beam_case_count", 0)
        and assembled_global_depth_summary.get("beam_equilibrium_pass", False)
    )
    panel_signal_present = bool(
        assembled_global_depth_summary.get("panel_case_count", 0)
        and assembled_global_depth_summary.get("panel_force_balance_pass", False)
    )
    support_signal_present = bool(
        support_depth_score > 0
        and support_search_model_types
        and node_to_surface_proxy_model_types
        and support_search_family_types
        and node_to_surface_proxy_family_types
        and structural_contact_validation_checks.get("support_search_family_surface_pass", False)
        and structural_contact_validation_checks.get("node_to_surface_proxy_family_surface_pass", False)
        and foundation_soil_link_checks.get("support_search_family_surface_ready", False)
        and foundation_soil_link_checks.get("node_to_surface_proxy_family_surface_ready", False)
    )
    coupling_signal_count = (
        int(bool(beam_signal_present))
        + int(assembled_global_depth_summary.get("panel_case_count", 0) or 0)
        + len(support_search_model_types)
        + len(node_to_surface_proxy_model_types)
        + len(support_search_family_types)
        + len(node_to_surface_proxy_family_types)
    )
    present = bool(beam_signal_present and panel_signal_present and support_signal_present)
    return {
        "present": present,
        "beam_signal_present": bool(beam_signal_present),
        "panel_signal_present": bool(panel_signal_present),
        "support_signal_present": bool(support_signal_present),
        "beam_case_count": int(assembled_global_depth_summary.get("beam_case_count", 0) or 0),
        "panel_case_count": int(assembled_global_depth_summary.get("panel_case_count", 0) or 0),
        "support_depth_score": int(support_depth_score),
        "support_search_model_count": len(support_search_model_types),
        "node_to_surface_proxy_model_count": len(node_to_surface_proxy_model_types),
        "support_search_family_count": len(support_search_family_types),
        "node_to_surface_proxy_family_count": len(node_to_surface_proxy_family_types),
        "coupling_signal_count": int(coupling_signal_count),
        "support_search_model_types": list(support_search_model_types),
        "node_to_surface_proxy_model_types": list(node_to_surface_proxy_model_types),
        "support_search_family_types": list(support_search_family_types),
        "node_to_surface_proxy_family_types": list(node_to_surface_proxy_family_types),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology-report", default="implementation/phase1/opensees_topology_report.json")
    parser.add_argument("--flexible-diaphragm-report", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    parser.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    parser.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--substructuring-interface-report", default="implementation/phase1/substructuring_interface_report.json")
    parser.add_argument("--wind-time-history-report", default="implementation/phase1/wind_time_history_gate_report.json")
    parser.add_argument("--special-link-library", default="implementation/phase1/special_link_library.py")
    parser.add_argument(
        "--structural-contact-validation-report",
        default="implementation/phase1/structural_contact_validation_report.json",
    )
    parser.add_argument(
        "--structural-contact-gate-report",
        default="implementation/phase1/structural_contact_gate_report.json",
    )
    parser.add_argument("--rc-benchmark-lock-report", default="implementation/phase1/rc_benchmark_lock_report.json")
    parser.add_argument("--construction-sequence-report", default="implementation/phase1/construction_sequence_gate_report.json")
    parser.add_argument("--damper-validation-report", default="implementation/phase1/damper_validation_gate_report.json")
    parser.add_argument(
        "--foundation-soil-link-gate-report",
        default="implementation/phase1/foundation_soil_link_gate_report.json",
    )
    parser.add_argument(
        "--benchmark-cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.json"
        ),
    )
    parser.add_argument("--required-material-models", default="rc_composite,steel_elastic_plastic")
    parser.add_argument(
        "--required-link-models",
        default="normal_gap_unilateral,uplift_seat_unilateral,compression_only_penalty,bearing_bilinear,coulomb_friction,kelvin_voigt_pounding",
    )
    parser.add_argument(
        "--required-material-capabilities",
        default=(
            "rc_cracking,rc_bond_slip,rc_creep_shrinkage,slab_wall_interaction,wall_compression_damage,"
            "shell_surface_transfer,interface_transfer_finite,soil_boundary_nonlinear,"
            "dissipative_device_response,foundation_soil_link_nonlinear,"
            "contact_gap_uplift_unilateral,contact_bearing_friction_impact"
        ),
    )
    parser.add_argument("--min-shell-elements", type=int, default=1)
    parser.add_argument("--min-shell-beam-mix-cases", type=int, default=1)
    parser.add_argument("--min-wall-rows", type=int, default=1)
    parser.add_argument("--min-wall-frame-cases", type=int, default=1)
    parser.add_argument("--min-compression-surrogate-rows", type=int, default=1)
    parser.add_argument("--out", default="implementation/phase1/element_material_breadth_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "topology_report": str(args.topology_report),
        "flexible_diaphragm_report": str(args.flexible_diaphragm_report),
        "pushover_stress_report": str(args.pushover_stress_report),
        "ndtha_stress_report": str(args.ndtha_stress_report),
        "ssi_boundary_report": str(args.ssi_boundary_report),
        "substructuring_interface_report": str(args.substructuring_interface_report),
        "wind_time_history_report": str(args.wind_time_history_report),
        "special_link_library": str(args.special_link_library),
        "structural_contact_validation_report": str(args.structural_contact_validation_report),
        "structural_contact_gate_report": str(args.structural_contact_gate_report),
        "rc_benchmark_lock_report": str(args.rc_benchmark_lock_report),
        "construction_sequence_report": str(args.construction_sequence_report),
        "damper_validation_report": str(args.damper_validation_report),
        "foundation_soil_link_gate_report": str(args.foundation_soil_link_gate_report),
        "benchmark_cases": str(args.benchmark_cases),
        "required_material_models": str(args.required_material_models),
        "required_link_models": str(args.required_link_models),
        "required_material_capabilities": str(args.required_material_capabilities),
        "min_shell_elements": int(args.min_shell_elements),
        "min_shell_beam_mix_cases": int(args.min_shell_beam_mix_cases),
        "min_wall_rows": int(args.min_wall_rows),
        "min_wall_frame_cases": int(args.min_wall_frame_cases),
        "min_compression_surrogate_rows": int(args.min_compression_surrogate_rows),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_element_material_breadth_gate")

        case_paths = [Path(item) for item in _parse_csv(args.benchmark_cases)]
        required_material_models = sorted(set(_parse_csv(args.required_material_models)))
        required_link_models = sorted(set(_parse_csv(args.required_link_models)))
        required_material_capabilities = sorted(set(_parse_csv(args.required_material_capabilities)))
        if not case_paths:
            raise ValueError("no benchmark case files provided")
        if not required_material_models:
            raise ValueError("no required material models provided")
        if not required_link_models:
            raise ValueError("no required link models provided")
        if not required_material_capabilities:
            raise ValueError("no required material capabilities provided")

        topology = _load_json(Path(args.topology_report))
        diaphragm = _load_json(Path(args.flexible_diaphragm_report))
        pushover = _load_json(Path(args.pushover_stress_report))
        ndtha = _load_json(Path(args.ndtha_stress_report))
        ssi = _load_json(Path(args.ssi_boundary_report))
        substructuring = _load_json(Path(args.substructuring_interface_report))
        wind = _load_json(Path(args.wind_time_history_report))
        special_link_text = _load_text(Path(args.special_link_library))
        structural_contact_validation = _load_json(Path(args.structural_contact_validation_report))
        structural_contact_gate = _load_json(Path(args.structural_contact_gate_report))
        rc_benchmark_lock = _load_json(Path(args.rc_benchmark_lock_report))
        construction_sequence = _load_json(Path(args.construction_sequence_report))
        damper_validation = _load_json(Path(args.damper_validation_report))
        foundation_soil_link_gate = _load_json(Path(args.foundation_soil_link_gate_report))
        benchmarks = _aggregate_benchmark_cases(case_paths)

        topology_checks = topology.get("checks") if isinstance(topology.get("checks"), dict) else {}
        topology_metrics = topology.get("metrics") if isinstance(topology.get("metrics"), dict) else {}
        diaphragm_checks = diaphragm.get("checks") if isinstance(diaphragm.get("checks"), dict) else {}
        pushover_checks = pushover.get("checks") if isinstance(pushover.get("checks"), dict) else {}
        ndtha_checks = ndtha.get("checks") if isinstance(ndtha.get("checks"), dict) else {}
        ssi_checks = ssi.get("checks") if isinstance(ssi.get("checks"), dict) else {}
        substructuring_checks = (
            substructuring.get("checks") if isinstance(substructuring.get("checks"), dict) else {}
        )
        shell_element_count = int(topology_metrics.get("shell_element_count", 0) or 0)
        shell_beam_mix_case_count = int((benchmarks.get("element_mix_counts") or {}).get("shell_beam_mix", 0) or 0)
        wall_frame_case_count = int((benchmarks.get("topology_counts") or {}).get("wall-frame", 0) or 0)

        shell_topology_evidence_pass = bool(
            topology.get("contract_pass", False)
            and topology_checks.get("shell_beam_mix_pass", False)
            and shell_element_count >= int(args.min_shell_elements)
        )
        shell_diaphragm_evidence_pass = bool(
            diaphragm.get("contract_pass", False)
            and diaphragm_checks.get("flexible_diaphragm_modeled", False)
            and diaphragm_checks.get("shell_beam_mix_topology_pass", False)
            and diaphragm_checks.get("slab_shear_stress_pass", False)
        )
        shell_direct_contract_pass = bool(
            shell_topology_evidence_pass
            and shell_diaphragm_evidence_pass
            and shell_beam_mix_case_count >= int(args.min_shell_beam_mix_cases)
        )

        pushover_wall_rows = _iter_wall_family_rows(pushover)
        ndtha_wall_rows = _iter_wall_family_rows(ndtha)
        pushover_wall_evidence_pass = bool(
            pushover.get("contract_pass", False)
            and pushover_checks.get("material_model_pass", False)
            and pushover_checks.get("section_family_pass", False)
            and len(pushover_wall_rows) >= int(args.min_wall_rows)
        )
        ndtha_wall_evidence_pass = bool(
            ndtha.get("contract_pass", False)
            and ndtha_checks.get("material_model_pass", False)
            and ndtha_checks.get("section_family_pass", False)
            and len(ndtha_wall_rows) >= int(args.min_wall_rows)
        )
        wall_direct_contract_pass = bool(
            pushover_wall_evidence_pass
            and ndtha_wall_evidence_pass
            and wall_frame_case_count >= int(args.min_wall_frame_cases)
        )

        pushover_compression = _compression_damage_evidence(pushover)
        ndtha_compression = _compression_damage_evidence(ndtha)
        ssi_boundary_evidence_pass = bool(
            ssi.get("contract_pass", False)
            and ssi_checks.get("ssi_nonlinear_boundary_active", False)
            and ssi_checks.get("ssi_transfer_finite", False)
            and ssi_checks.get("section_family_pass", False)
            and ssi_checks.get("material_model_pass", False)
        )
        substructuring_interface_evidence_pass = bool(
            substructuring.get("contract_pass", False)
            and substructuring_checks.get("finite_transfer", False)
            and substructuring_checks.get("coupling_stability", False)
        )
        contact_interface_compression_surrogate_pass = bool(
            ssi_boundary_evidence_pass
            and substructuring_interface_evidence_pass
            and pushover.get("contract_pass", False)
            and ndtha.get("contract_pass", False)
            and pushover_checks.get("material_model_pass", False)
            and ndtha_checks.get("material_model_pass", False)
            and int(pushover_compression.get("qualifying_row_count", 0)) >= int(args.min_compression_surrogate_rows)
            and int(ndtha_compression.get("qualifying_row_count", 0)) >= int(args.min_compression_surrogate_rows)
        )

        material_sources: dict[str, set[str]] = {}
        _add_material_source(material_sources, "pushover_stress_report", pushover)
        _add_material_source(material_sources, "ndtha_stress_report", ndtha)
        _add_material_source(material_sources, "ssi_boundary_report", ssi)
        _add_material_source(material_sources, "wind_time_history_report", wind)
        material_models = sorted(material_sources)
        missing_material_models = [model for model in required_material_models if model not in material_sources]
        material_model_breadth_pass = bool(not missing_material_models)

        structural_contact_checks = (
            structural_contact_gate.get("checks")
            if isinstance(structural_contact_gate.get("checks"), dict)
            else {}
        )
        structural_contact_validation_checks = (
            structural_contact_validation.get("checks")
            if isinstance(structural_contact_validation.get("checks"), dict)
            else {}
        )
        rc_benchmark_checks = (
            rc_benchmark_lock.get("checks")
            if isinstance(rc_benchmark_lock.get("checks"), dict)
            else {}
        )
        construction_checks = (
            construction_sequence.get("checks")
            if isinstance(construction_sequence.get("checks"), dict)
            else {}
        )
        damper_checks = (
            damper_validation.get("checks")
            if isinstance(damper_validation.get("checks"), dict)
            else {}
        )
        foundation_soil_link_checks = (
            foundation_soil_link_gate.get("checks")
            if isinstance(foundation_soil_link_gate.get("checks"), dict)
            else {}
        )
        foundation_soil_link_summary = (
            foundation_soil_link_gate.get("summary")
            if isinstance(foundation_soil_link_gate.get("summary"), dict)
            else {}
        )
        structural_contact_summary = (
            structural_contact_validation.get("summary")
            if isinstance(structural_contact_validation.get("summary"), dict)
            else {}
        )
        link_model_types = sorted(
            str(item).strip()
            for item in (structural_contact_summary.get("link_model_types") or [])
            if str(item).strip()
        )
        foundation_support_model_types = _sorted_string_union(
            foundation_soil_link_summary.get("foundation_support_model_types"),
            structural_contact_summary.get("foundation_support_model_types"),
            list(describe_foundation_link_library().keys()),
        )
        device_model_types = _sorted_string_union(
            foundation_soil_link_summary.get("device_model_types"),
            structural_contact_summary.get("device_model_types"),
            list(describe_device_library().keys()),
        )
        missing_link_models = [model for model in required_link_models if model not in link_model_types]
        special_link_keywords_present = all(
            token in special_link_text.lower()
            for token in ("gap", "uplift", "compression-only", "bearing", "friction", "pounding")
        )
        link_model_breadth_pass = bool(not missing_link_models)
        structural_contact_direct_contract_pass = bool(
            structural_contact_gate.get("contract_pass", False)
            and structural_contact_validation.get("contract_pass", False)
            and structural_contact_checks.get("all_structural_contact_categories_ready", False)
            and structural_contact_checks.get("structural_contact_event_sequence_zero_pass", False)
            and special_link_keywords_present
            and link_model_breadth_pass
        )
        material_capabilities = sorted(
            capability
            for capability, present in {
                "rc_cracking": bool(
                    rc_benchmark_lock.get("contract_pass", False)
                    and rc_benchmark_checks.get("cracking_case_pass", False)
                ),
                "rc_bond_slip": bool(
                    rc_benchmark_lock.get("contract_pass", False)
                    and rc_benchmark_checks.get("bond_slip_case_pass", False)
                ),
                "rc_creep_shrinkage": bool(
                    rc_benchmark_lock.get("contract_pass", False)
                    and rc_benchmark_checks.get("creep_case_pass", False)
                    and construction_sequence.get("contract_pass", False)
                    and construction_checks.get("creep_shrinkage_applied", False)
                ),
                "slab_wall_interaction": bool(
                    rc_benchmark_lock.get("contract_pass", False)
                    and rc_benchmark_checks.get("slab_wall_case_pass", False)
                ),
                "wall_compression_damage": bool(
                    int(pushover_compression.get("qualifying_row_count", 0)) >= int(args.min_compression_surrogate_rows)
                    and int(ndtha_compression.get("qualifying_row_count", 0)) >= int(args.min_compression_surrogate_rows)
                ),
                "shell_surface_transfer": bool(shell_diaphragm_evidence_pass),
                "interface_transfer_finite": bool(substructuring_interface_evidence_pass),
                "soil_boundary_nonlinear": bool(
                    ssi.get("contract_pass", False)
                    and ssi_checks.get("ssi_nonlinear_boundary_active", False)
                    and ssi_checks.get("ssi_transfer_finite", False)
                ),
                "dissipative_device_response": bool(
                    damper_validation.get("contract_pass", False)
                    and damper_checks.get("damper_type_diversity_pass", False)
                    and damper_checks.get("waveform_corr_pass", False)
                    and damper_checks.get("phase_error_pass", False)
                    and damper_checks.get("residual_drift_pass", False)
                ),
                "foundation_soil_link_nonlinear": bool(
                    foundation_soil_link_gate.get("contract_pass", False)
                    and foundation_soil_link_checks.get("foundation_scope_ready", False)
                    and foundation_soil_link_checks.get("foundation_artifact_ready", False)
                    and foundation_soil_link_checks.get("ssi_boundary_ready", False)
                    and foundation_soil_link_checks.get("soil_tunnel_ready", False)
                    and foundation_soil_link_checks.get("impedance_schema_ready", False)
                    and foundation_soil_link_checks.get("foundation_link_models_ready", False)
                ),
                "contact_gap_uplift_unilateral": bool(
                    {"normal_gap_unilateral", "uplift_seat_unilateral"}.issubset(set(link_model_types))
                    and structural_contact_direct_contract_pass
                ),
                "contact_bearing_friction_impact": bool(
                    {"bearing_bilinear", "coulomb_friction", "kelvin_voigt_pounding"}.issubset(set(link_model_types))
                    and structural_contact_direct_contract_pass
                ),
            }.items()
            if present
        )
        missing_material_capabilities = [
            capability
            for capability in required_material_capabilities
            if capability not in material_capabilities
        ]
        material_capability_breadth_pass = bool(not missing_material_capabilities)

        wall_family_counter: Counter[str] = Counter()
        for row in pushover_wall_rows + ndtha_wall_rows:
            wall_family_counter.update({name: int(count) for name, count in row["section_family_counts"].items()})

        panel_rc_cyclic_summary = _panel_rc_cyclic_surface_summary()
        assembled_global_depth_summary = _assembled_global_depth_surface_summary()
        section_family_demand_summary = _section_family_demand_surface_summary()
        beam_shell_contact_coupling_summary = _beam_shell_contact_coupling_surface_summary(
            assembled_global_depth_summary=assembled_global_depth_summary,
            structural_contact_summary=structural_contact_summary,
            structural_contact_validation_checks=structural_contact_validation_checks,
            foundation_soil_link_summary=foundation_soil_link_summary,
            foundation_soil_link_checks=foundation_soil_link_checks,
        )
        contact_surface_status = (
            "full_structural_contact"
            if structural_contact_direct_contract_pass
            else "interface_compression_surrogate"
            if contact_interface_compression_surrogate_pass
            else "tracked_gap"
        )
        checks = {
            "shell_topology_evidence_pass": bool(shell_topology_evidence_pass),
            "shell_diaphragm_evidence_pass": bool(shell_diaphragm_evidence_pass),
            "shell_direct_contract_pass": bool(shell_direct_contract_pass),
            "pushover_wall_evidence_pass": bool(pushover_wall_evidence_pass),
            "ndtha_wall_evidence_pass": bool(ndtha_wall_evidence_pass),
            "wall_direct_contract_pass": bool(wall_direct_contract_pass),
            "ssi_boundary_evidence_pass": bool(ssi_boundary_evidence_pass),
            "substructuring_interface_evidence_pass": bool(substructuring_interface_evidence_pass),
            "contact_interface_compression_surrogate_pass": bool(contact_interface_compression_surrogate_pass),
            "special_link_keywords_present": bool(special_link_keywords_present),
            "structural_contact_direct_contract_pass": bool(structural_contact_direct_contract_pass),
            "foundation_soil_link_direct_contract_pass": bool(
                foundation_soil_link_gate.get("contract_pass", False)
                and foundation_soil_link_checks.get("foundation_scope_ready", False)
                and foundation_soil_link_checks.get("foundation_artifact_ready", False)
                and foundation_soil_link_checks.get("ssi_boundary_ready", False)
                and foundation_soil_link_checks.get("soil_tunnel_ready", False)
                and foundation_soil_link_checks.get("impedance_schema_ready", False)
                and foundation_soil_link_checks.get("foundation_link_models_ready", False)
            ),
            "support_link_surface_present": bool(
                link_model_types and foundation_support_model_types and device_model_types
            ),
            "material_model_breadth_pass": bool(material_model_breadth_pass),
            "link_model_breadth_pass": bool(link_model_breadth_pass),
            "material_capability_breadth_pass": bool(material_capability_breadth_pass),
            "panel_rc_cyclic_surface_present": bool(panel_rc_cyclic_summary["present"]),
            "beam_column_global_surface_present": bool(assembled_global_depth_summary["beam_case_count"]),
            "beam_column_global_equilibrium_pass": bool(assembled_global_depth_summary["beam_equilibrium_pass"]),
            "layered_panel_assembled_surface_present": bool(assembled_global_depth_summary["panel_case_count"]),
            "layered_panel_force_balance_pass": bool(assembled_global_depth_summary["panel_force_balance_pass"]),
            "assembled_global_depth_surface_present": bool(assembled_global_depth_summary["present"]),
            "section_family_demand_surface_present": bool(section_family_demand_summary["present"]),
            "beam_shell_contact_coupling_surface_present": bool(beam_shell_contact_coupling_summary["present"]),
        }
        contract_pass = bool(
            checks["shell_direct_contract_pass"]
            and checks["wall_direct_contract_pass"]
            and checks["contact_interface_compression_surrogate_pass"]
            and checks["structural_contact_direct_contract_pass"]
            and checks["foundation_soil_link_direct_contract_pass"]
            and checks["material_model_breadth_pass"]
            and checks["link_model_breadth_pass"]
            and checks["material_capability_breadth_pass"]
        )

        if not checks["shell_direct_contract_pass"]:
            reason_code = "ERR_SHELL_DIRECT_COVERAGE"
        elif not checks["wall_direct_contract_pass"]:
            reason_code = "ERR_WALL_DIRECT_COVERAGE"
        elif not checks["contact_interface_compression_surrogate_pass"]:
            reason_code = "ERR_CONTACT_INTERFACE_SURROGATE"
        elif not checks["structural_contact_direct_contract_pass"]:
            reason_code = "ERR_STRUCTURAL_CONTACT_DIRECT_COVERAGE"
        elif not checks["foundation_soil_link_direct_contract_pass"]:
            reason_code = "ERR_FOUNDATION_SOIL_LINK_DIRECT_COVERAGE"
        elif not checks["material_model_breadth_pass"]:
            reason_code = "ERR_MATERIAL_MODEL_BREADTH"
        elif not checks["link_model_breadth_pass"]:
            reason_code = "ERR_LINK_MODEL_BREADTH"
        elif not checks["material_capability_breadth_pass"]:
            reason_code = "ERR_MATERIAL_CAPABILITY_BREADTH"
        else:
            reason_code = "PASS"

        summary = {
            "shell_element_count": shell_element_count,
            "shell_beam_mix_case_count": shell_beam_mix_case_count,
            "wall_frame_case_count": wall_frame_case_count,
            "benchmark_case_count": int(benchmarks.get("case_count", 0) or 0),
            "pushover_wall_row_count": len(pushover_wall_rows),
            "ndtha_wall_row_count": len(ndtha_wall_rows),
            "wall_family_counts": dict(sorted(wall_family_counter.items())),
            "contact_surface_status": contact_surface_status,
            "panel_rc_cyclic_surface_status": (
                "pass" if checks["panel_rc_cyclic_surface_present"] else "missing"
            ),
            "panel_rc_cyclic_section_count": int(panel_rc_cyclic_summary["section_count"]),
            "panel_rc_cyclic_section_families": list(panel_rc_cyclic_summary["section_families"]),
            "panel_rc_cyclic_section_names": list(panel_rc_cyclic_summary["section_names"]),
            "panel_rc_cyclic_reversal_count_min": int(panel_rc_cyclic_summary["reversal_count_min"]),
            "panel_rc_cyclic_reversal_count_max": int(panel_rc_cyclic_summary["reversal_count_max"]),
            "panel_rc_cyclic_min_pinching_ratio": float(panel_rc_cyclic_summary["min_pinching_ratio"]),
            "panel_rc_cyclic_max_crushing_ratio": float(panel_rc_cyclic_summary["max_crushing_ratio"]),
            "panel_rc_cyclic_max_stiffness_degradation": float(panel_rc_cyclic_summary["max_stiffness_degradation"]),
            "panel_rc_cyclic_max_strength_degradation": float(panel_rc_cyclic_summary["max_strength_degradation"]),
            "panel_rc_cyclic_evidence_tags": list(panel_rc_cyclic_summary["evidence_tags"]),
            "panel_rc_cyclic_total_energy_like": float(panel_rc_cyclic_summary["total_energy_like"]),
            "assembled_global_depth_surface_status": (
                "pass" if checks["assembled_global_depth_surface_present"] else "missing"
            ),
            "assembled_global_depth_signal_count": int(assembled_global_depth_summary["depth_signal_count"]),
            "beam_column_global_case_count": int(assembled_global_depth_summary["beam_case_count"]),
            "beam_column_global_iteration_count": int(assembled_global_depth_summary["beam_iteration_count"]),
            "beam_column_global_yielded_end_count": int(assembled_global_depth_summary["beam_yielded_end_count"]),
            "beam_column_global_tangent_scale_min": float(assembled_global_depth_summary["beam_tangent_scale_min"]),
            "beam_column_global_max_trial_end_moment_ratio": float(
                assembled_global_depth_summary["beam_max_trial_end_moment_ratio"]
            ),
            "beam_column_global_max_plastic_rotation_proxy_rad": float(
                assembled_global_depth_summary["beam_max_plastic_rotation_proxy_rad"]
            ),
            "beam_column_global_stability_index": float(assembled_global_depth_summary["beam_stability_index"]),
            "beam_column_global_strain_energy_n_m": float(assembled_global_depth_summary["beam_strain_energy_n_m"]),
            "beam_column_global_free_dof_residual_max": float(
                assembled_global_depth_summary["beam_free_dof_residual_max"]
            ),
            "beam_column_global_displacement_max_m": float(
                assembled_global_depth_summary["beam_displacement_max_m"]
            ),
            "section_family_demand_surface_status": (
                "pass" if checks["section_family_demand_surface_present"] else "missing"
            ),
            "section_family_story_count": int(section_family_demand_summary["story_count"]),
            "section_family_distribution": dict(sorted(section_family_demand_summary["family_counts"].items())),
            "section_family_beam_tangent_scale_mean": float(
                section_family_demand_summary["beam_tangent_scale_mean"]
            ),
            "section_family_beam_tangent_scale_min": float(
                section_family_demand_summary["beam_tangent_scale_min"]
            ),
            "section_family_beam_yielded_story_count": int(
                section_family_demand_summary["beam_yielded_story_count"]
            ),
            "section_family_beam_max_trial_end_moment_ratio": float(
                section_family_demand_summary["beam_max_trial_end_moment_ratio"]
            ),
            "section_family_beam_max_plastic_rotation_proxy_rad": float(
                section_family_demand_summary["beam_max_plastic_rotation_proxy_rad"]
            ),
            "section_family_beam_stability_index_max": float(
                section_family_demand_summary["beam_stability_index_max"]
            ),
            "section_family_beam_strain_energy_total_n_m": float(
                section_family_demand_summary["beam_strain_energy_total_n_m"]
            ),
            "layered_panel_assembled_case_count": int(assembled_global_depth_summary["panel_case_count"]),
            "layered_panel_assembled_section_families": list(
                assembled_global_depth_summary["panel_section_families"]
            ),
            "layered_panel_assembled_force_balance_error_max_n": float(
                assembled_global_depth_summary["panel_force_balance_error_max_n"]
            ),
            "layered_panel_assembled_corner_force_max_n": float(
                assembled_global_depth_summary["panel_corner_force_max_n"]
            ),
            "layered_panel_assembled_torsional_case_count": int(
                assembled_global_depth_summary["panel_torsional_case_count"]
            ),
            "layered_panel_assembled_diaphragm_coupling_case_count": int(
                assembled_global_depth_summary["panel_diaphragm_coupling_case_count"]
            ),
            "beam_shell_contact_coupling_surface_status": (
                "pass" if checks["beam_shell_contact_coupling_surface_present"] else "missing"
            ),
            "beam_shell_contact_coupling_signal_count": int(beam_shell_contact_coupling_summary["coupling_signal_count"]),
            "beam_shell_contact_support_depth_score": int(beam_shell_contact_coupling_summary["support_depth_score"]),
            "beam_shell_contact_support_search_count": int(
                beam_shell_contact_coupling_summary["support_search_model_count"]
            ),
            "beam_shell_contact_node_surface_proxy_count": int(
                beam_shell_contact_coupling_summary["node_to_surface_proxy_model_count"]
            ),
            "beam_shell_contact_support_family_count": int(
                beam_shell_contact_coupling_summary["support_search_family_count"]
            ),
            "beam_shell_contact_proxy_family_count": int(
                beam_shell_contact_coupling_summary["node_to_surface_proxy_family_count"]
            ),
            "substructuring_transfer_ratio": float(
                (substructuring.get("metrics") or {}).get("mean_transfer_ratio_building_to_track", 0.0)
            )
            if isinstance(substructuring.get("metrics"), dict)
            else 0.0,
            "pushover_compression_surrogate_row_count": int(pushover_compression.get("qualifying_row_count", 0)),
            "ndtha_compression_surrogate_row_count": int(ndtha_compression.get("qualifying_row_count", 0)),
            "material_model_types": material_models,
            "material_model_source_map": {
                model: sorted(sources) for model, sources in sorted(material_sources.items())
            },
            "required_material_models": required_material_models,
            "missing_material_models": missing_material_models,
            "link_model_types": link_model_types,
            "required_link_models": required_link_models,
            "missing_link_models": missing_link_models,
            "foundation_soil_link_status": "pass" if checks["foundation_soil_link_direct_contract_pass"] else "missing",
            "foundation_support_model_types": foundation_support_model_types,
            "device_model_types": device_model_types,
            "support_link_group_counts": {
                "contact": len(link_model_types),
                "foundation": len(foundation_support_model_types),
                "device": len(device_model_types),
            },
            "support_link_family_count": len(
                set(link_model_types) | set(foundation_support_model_types) | set(device_model_types)
            ),
            "material_capability_types": material_capabilities,
            "material_capability_group_counts": {
                "rc": sum(1 for capability in material_capabilities if capability.startswith("rc_") or capability in {"slab_wall_interaction", "wall_compression_damage"}),
                "shell_interface": sum(1 for capability in material_capabilities if capability in {"shell_surface_transfer", "interface_transfer_finite"}),
                "foundation_soil": sum(1 for capability in material_capabilities if capability in {"soil_boundary_nonlinear", "foundation_soil_link_nonlinear"}),
                "device_contact": sum(1 for capability in material_capabilities if capability in {"dissipative_device_response", "contact_gap_uplift_unilateral", "contact_bearing_friction_impact"}),
            },
            "required_material_capabilities": required_material_capabilities,
            "missing_material_capabilities": missing_material_capabilities,
        }

        reasons = [
            (
                f"shell={'pass' if checks['shell_direct_contract_pass'] else 'missing'} via "
                f"topology={_format_yes_no(shell_topology_evidence_pass)}, "
                f"diaphragm={_format_yes_no(shell_diaphragm_evidence_pass)}, "
                f"shell_beam_mix_cases={shell_beam_mix_case_count}."
            ),
            (
                f"wall={'pass' if checks['wall_direct_contract_pass'] else 'missing'} via "
                f"pushover_rows={len(pushover_wall_rows)}, "
                f"ndtha_rows={len(ndtha_wall_rows)}, "
                f"wall_frame_cases={wall_frame_case_count}."
            ),
            (
                f"contact_interface_surrogate={'pass' if checks['contact_interface_compression_surrogate_pass'] else 'missing'} via "
                f"ssi_boundary={_format_yes_no(ssi_boundary_evidence_pass)}, "
                f"substructuring={_format_yes_no(substructuring_interface_evidence_pass)}, "
                f"compression_rows={summary['pushover_compression_surrogate_row_count']}/"
                f"{summary['ndtha_compression_surrogate_row_count']}."
            ),
            (
                f"panel_rc_cyclic={'pass' if checks['panel_rc_cyclic_surface_present'] else 'missing'} via "
                f"sections={summary['panel_rc_cyclic_section_families'] or ['none']}, "
                f"reversal={summary['panel_rc_cyclic_reversal_count_min']}-"
                f"{summary['panel_rc_cyclic_reversal_count_max']}, "
                f"pinch={summary['panel_rc_cyclic_min_pinching_ratio']:.2f}, "
                f"crush={summary['panel_rc_cyclic_max_crushing_ratio']:.2f}."
            ),
            (
                f"assembled_global_depth={'pass' if checks['assembled_global_depth_surface_present'] else 'missing'} via "
                f"beam_iter={summary['beam_column_global_iteration_count']}, "
                f"beam_tangent={summary['beam_column_global_tangent_scale_min']:.2f}, "
                f"beam_ratio={summary['beam_column_global_max_trial_end_moment_ratio']:.2f}, "
                f"beam_stability={summary['beam_column_global_stability_index']:.2f}, "
                f"beam_residual={summary['beam_column_global_free_dof_residual_max']:.2e}, "
                f"panel_cases={summary['layered_panel_assembled_case_count']}, "
                f"torsion_cases={summary['layered_panel_assembled_torsional_case_count']}, "
                f"diaphragm_cases={summary['layered_panel_assembled_diaphragm_coupling_case_count']}."
            ),
            (
                f"section_family_demand={'pass' if checks['section_family_demand_surface_present'] else 'missing'} via "
                f"stories={summary['section_family_story_count']}, "
                f"families={sorted(summary['section_family_distribution']) or ['none']}, "
                f"yielded={summary['section_family_beam_yielded_story_count']}, "
                f"tangent={summary['section_family_beam_tangent_scale_min']:.2f}, "
                f"demand={summary['section_family_beam_max_trial_end_moment_ratio']:.2f}, "
                f"stability={summary['section_family_beam_stability_index_max']:.2f}."
            ),
            (
                f"beam_shell_contact_coupling={'pass' if checks['beam_shell_contact_coupling_surface_present'] else 'missing'} via "
                f"beam={summary['beam_column_global_case_count']}, "
                f"panel={summary['layered_panel_assembled_case_count']}, "
                f"support_depth={summary['beam_shell_contact_support_depth_score']}, "
                f"support_search={summary['beam_shell_contact_support_search_count']}, "
                f"node_surface_proxy={summary['beam_shell_contact_node_surface_proxy_count']}."
            ),
            (
                f"structural_contact={'pass' if checks['structural_contact_direct_contract_pass'] else 'missing'} via "
                f"special_link_keywords={_format_yes_no(special_link_keywords_present)}, "
                f"gate={_format_yes_no(bool(structural_contact_gate.get('contract_pass', False)))}, "
                f"validation={_format_yes_no(bool(structural_contact_validation.get('contract_pass', False)))}, "
                f"link_models={link_model_types or ['none']}."
            ),
            (
                f"foundation_soil_link={'pass' if checks['foundation_soil_link_direct_contract_pass'] else 'missing'} via "
                f"gate={_format_yes_no(bool(foundation_soil_link_gate.get('contract_pass', False)))}, "
                f"foundation_scope={_format_yes_no(bool(foundation_soil_link_checks.get('foundation_scope_ready', False)))}, "
                f"ssi={_format_yes_no(bool(foundation_soil_link_checks.get('ssi_boundary_ready', False)))}, "
                f"soil_tunnel={_format_yes_no(bool(foundation_soil_link_checks.get('soil_tunnel_ready', False)))}."
            ),
            (
                f"support_link_surface={'pass' if checks['support_link_surface_present'] else 'missing'} via "
                f"contact={link_model_types or ['none']}, "
                f"foundation={foundation_support_model_types or ['none']}, "
                f"device={device_model_types or ['none']}."
            ),
            (
                f"material_models={'pass' if checks['material_model_breadth_pass'] else 'partial'} via "
                f"found={material_models or ['none']}, "
                f"required={required_material_models}, "
                f"missing={missing_material_models or ['none']}."
            ),
            (
                f"link_models={'pass' if checks['link_model_breadth_pass'] else 'partial'} via "
                f"found={link_model_types or ['none']}, "
                f"required={required_link_models}, "
                f"missing={missing_link_models or ['none']}."
            ),
            (
                f"material_capabilities={'pass' if checks['material_capability_breadth_pass'] else 'partial'} via "
                f"found={material_capabilities or ['none']}, "
                f"required={required_material_capabilities}, "
                f"missing={missing_material_capabilities or ['none']}."
            ),
        ]
        limitations = [
            "This gate summarizes checked-in contract evidence and does not rerun the underlying solvers.",
            "Structural-contact breadth is measured from the validated special-link library plus the broader structural-contact gate, not a full finite-element general-contact benchmark matrix.",
            "Foundation/soil-link breadth is measured from checked-in foundation optimization, SSI, soil-tunnel, and impedance/support-link contracts, not a full geotechnical FE interaction matrix.",
            "Support-link surface counts roll up contact, foundation, and device libraries to make the implementation catalog explicit, but they do not replace solver validation by themselves.",
            "Material-model breadth is inferred from reported material_model labels across contract reports, not exhaustive constitutive feature parity.",
            "Material/link breadth can be assembled from different contract reports rather than one single cross-element benchmark.",
            "Panel RC cyclic surface is a bounded library-backed wall/slab helper summary and does not replace a full shell/smeared-crack cyclic benchmark matrix.",
            "Assembled/global depth is a bounded helper-backed surface built from one beam-column solve and two layered-panel assemblies; it exposes integration depth signals without replacing full multi-member solver validation.",
            "Section-family demand surface is a bounded story-wise reduced-order profile and highlights beam demand/stability aggregation without replacing a full assembled frame benchmark set.",
            "Beam/shell-contact coupling is a bounded rollup of assembled beam depth, panel assembly depth, and support-search depth from validated contact/foundation summaries; it does not replace the separate general FE contact benchmark matrix.",
        ]
        if shell_beam_mix_case_count < int(args.min_shell_beam_mix_cases) or wall_frame_case_count < int(args.min_wall_frame_cases):
            limitations.append("Benchmark case counts are used as breadth context only and do not replace direct solver evidence.")

        summary_line = (
            f"Element/material breadth: {'PASS' if contract_pass else 'CHECK'} | "
            f"shell={_format_yes_no(checks['shell_direct_contract_pass'])}"
            f"(elems={shell_element_count},cases={shell_beam_mix_case_count}) | "
            f"wall={_format_yes_no(checks['wall_direct_contract_pass'])}"
            f"(rows={len(pushover_wall_rows) + len(ndtha_wall_rows)},cases={wall_frame_case_count}) | "
            f"panel_cyclic={_format_yes_no(checks['panel_rc_cyclic_surface_present'])}"
            f"(sections={summary['panel_rc_cyclic_section_count']},"
            f"pinch={summary['panel_rc_cyclic_min_pinching_ratio']:.2f},"
            f"crush={summary['panel_rc_cyclic_max_crushing_ratio']:.2f}) | "
            f"assembled_depth={_format_yes_no(checks['assembled_global_depth_surface_present'])}"
            f"(beam_iter={summary['beam_column_global_iteration_count']},"
            f"tangent={summary['beam_column_global_tangent_scale_min']:.2f},"
            f"ratio={summary['beam_column_global_max_trial_end_moment_ratio']:.2f},"
            f"panel={summary['layered_panel_assembled_case_count']},"
            f"torsion={summary['layered_panel_assembled_torsional_case_count']}) | "
            f"family_demand={_format_yes_no(checks['section_family_demand_surface_present'])}"
            f"(stories={summary['section_family_story_count']},"
            f"yielded={summary['section_family_beam_yielded_story_count']},"
            f"demand={summary['section_family_beam_max_trial_end_moment_ratio']:.2f},"
            f"stability={summary['section_family_beam_stability_index_max']:.2f}) | "
            f"coupling={_format_yes_no(checks['beam_shell_contact_coupling_surface_present'])}"
            f"(beam={summary['beam_column_global_case_count']},"
            f"panel={summary['layered_panel_assembled_case_count']},"
            f"support={summary['beam_shell_contact_support_depth_score']},"
            f"search={summary['beam_shell_contact_support_search_count']},"
            f"proxy={summary['beam_shell_contact_node_surface_proxy_count']}) | "
            f"contact={contact_surface_status} | "
            f"support={summary['support_link_family_count']}"
            f"(contact={summary['support_link_group_counts']['contact']},"
            f"foundation={summary['support_link_group_counts']['foundation']},"
            f"device={summary['support_link_group_counts']['device']}) | "
            f"materials={len(material_models)}({','.join(material_models) if material_models else 'none'}) | "
            f"links={len(link_model_types)}({','.join(link_model_types) if link_model_types else 'none'}) | "
            f"capabilities={len(material_capabilities)}({','.join(material_capabilities) if material_capabilities else 'none'}) | "
            f"groups=4(rc={summary['material_capability_group_counts']['rc']},"
            f"shell_interface={summary['material_capability_group_counts']['shell_interface']},"
            f"foundation_soil={summary['material_capability_group_counts']['foundation_soil']},"
            f"device_contact={summary['material_capability_group_counts']['device_contact']})"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-element-material-breadth-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": summary,
            "benchmark_cases": benchmarks,
            "summary_line": summary_line,
            "reasons": reasons,
            "limitations": limitations,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line)
        print(f"Wrote element/material breadth gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-element-material-breadth-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(payload["reason"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
