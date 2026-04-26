from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


CASE_CATALOG: list[dict[str, Any]] = [
    {
        "case_id": "peer_tbi_tall_building_ndtha",
        "label": "PEER TBI Tall Building NDTHA",
        "benchmark_family": "highrise_ndtha",
        "hazard_family": "seismic",
        "topology_family": "tall_building_core_outrigger",
        "load_path_family": "ndtha_multi_record",
        "primary_report_path": "implementation/phase1/nonlinear_ndtha_stress_report.json",
        "supporting_reports": {
            "solver_truthfulness": "implementation/phase1/solver_truthfulness_gate_report.json",
            "solver_hip": "implementation/phase1/solver_hip_e2e_contract_report.json",
        },
        "kpi_specs": [
            {"label": "case_count", "source": "primary.summary.case_count"},
            {"label": "max_drift_ratio_pct_max", "source": "primary.summary.max_drift_ratio_pct_max"},
            {"label": "peak_plastic_story_count_mean", "source": "primary.summary.peak_plastic_story_count_mean"},
            {"label": "avg_step_iterations_mean", "source": "primary.summary.avg_step_iterations_mean"},
            {"label": "residual_drift_ratio_pct_max_abs", "source": "primary.summary.residual_drift_ratio_pct_max_abs"},
            {"label": "solver_hip_variants", "source": "supporting.solver_hip.summary.solver_count"},
        ],
    },
    {
        "case_id": "nheri_designsafe_ssi",
        "label": "NHERI DesignSafe SSI",
        "benchmark_family": "soil_structure_interaction",
        "hazard_family": "seismic_ssi",
        "topology_family": "foundation_soil_mat_pile",
        "load_path_family": "contact_boundary_dynamic",
        "primary_report_path": "implementation/phase1/ssi_boundary_gate_report.json",
        "supporting_reports": {
            "surface_interaction": "implementation/phase1/surface_interaction_benchmark_gate_report.json",
            "foundation_soil_link": "implementation/phase1/foundation_soil_link_gate_report.json",
        },
        "kpi_specs": [
            {"label": "selected_case_count", "source": "primary.summary.selected_case_count"},
            {"label": "dominant_frequency_hz", "source": "primary.summary.dominant_frequency_hz"},
            {"label": "nonlinear_ratio_max", "source": "primary.summary.nonlinear_ratio_max"},
            {"label": "shear_delta_ratio_max", "source": "primary.summary.shear_delta_ratio_max"},
            {"label": "ssi_residual_drift_pct_max_abs", "source": "primary.summary.ssi_residual_drift_pct_max_abs"},
            {"label": "surface_interaction_family_count", "source": "supporting.surface_interaction.summary.interaction_family_ready_count"},
        ],
    },
    {
        "case_id": "uic_erri_rail_bridge",
        "label": "UIC / ERRI Railway Bridge",
        "benchmark_family": "moving_load_track_bridge",
        "hazard_family": "moving_load_dynamic",
        "topology_family": "bridge_track_vehicle",
        "load_path_family": "moving_axle_sequence",
        "primary_report_path": "implementation/phase1/vti_coupled_solver_report.json",
        "supporting_reports": {
            "moving_load": "implementation/phase1/moving_load_integrator_report.json",
            "track_lf": "implementation/phase1/track_lf_solver_report.json",
        },
        "kpi_specs": [
            {"label": "step_count", "source": "primary.metrics.step_count"},
            {"label": "converged_ratio", "source": "primary.metrics.converged_ratio"},
            {"label": "max_track_disp_m", "source": "primary.metrics.max_track_disp_m"},
            {"label": "max_contact_force_n", "source": "primary.metrics.max_contact_force_n"},
            {"label": "max_acceleration_mps2", "source": "supporting.moving_load.metrics.max_acceleration_mps2"},
            {"label": "energy_balance_relative_error", "source": "supporting.moving_load.metrics.energy_balance_relative_error"},
        ],
    },
    {
        "case_id": "nist_fema_progressive_collapse",
        "label": "NIST / FEMA Progressive Collapse",
        "benchmark_family": "progressive_collapse",
        "hazard_family": "local_damage_sequence",
        "topology_family": "frame_column_removal",
        "load_path_family": "path_dependent_collapse",
        "primary_report_path": "implementation/phase1/nonlinear_pushover_stress_report.json",
        "supporting_reports": {
            "ndtha": "implementation/phase1/nonlinear_ndtha_stress_report.json",
            "material_constitutive": "implementation/phase1/material_constitutive_gate_report.json",
        },
        "kpi_specs": [
            {"label": "case_count", "source": "primary.summary.case_count"},
            {"label": "first_yield_load_factor_mean", "source": "primary.summary.first_yield_load_factor_mean"},
            {"label": "peak_plastic_story_count_mean", "source": "primary.summary.peak_plastic_story_count_mean"},
            {"label": "drift_amplification_mean", "source": "primary.summary.drift_amplification_mean"},
            {"label": "ndtha_residual_drift_ratio_pct_max_abs", "source": "supporting.ndtha.summary.residual_drift_ratio_pct_max_abs"},
            {"label": "material_family_count", "source": "supporting.material_constitutive.summary.calibration_matrix_family_counts"},
        ],
    },
    {
        "case_id": "caarc_wind_standard_tower",
        "label": "CAARC Wind Standard Tower",
        "benchmark_family": "wind_time_history",
        "hazard_family": "wind_dynamic",
        "topology_family": "aeroelastic_tall_tower",
        "load_path_family": "pressure_series_mapping",
        "primary_report_path": "implementation/phase1/wind_time_history_gate_report.json",
        "supporting_reports": {
            "solver_truthfulness": "implementation/phase1/solver_truthfulness_gate_report.json",
        },
        "kpi_specs": [
            {"label": "selected_case_count", "source": "primary.summary.selected_case_count"},
            {"label": "duration_hours", "source": "primary.summary.duration_hours"},
            {"label": "load_reversal_count", "source": "primary.summary.load_reversal_count"},
            {"label": "dominant_frequency_hz", "source": "primary.summary.dominant_frequency_hz"},
            {"label": "max_drift_ratio_pct_all_cases", "source": "primary.summary.max_drift_ratio_pct_all_cases"},
            {"label": "residual_drift_pct_max_abs", "source": "primary.summary.residual_drift_pct_max_abs"},
        ],
    },
    {
        "case_id": "nceer_mceer_isolation_damper",
        "label": "NCEER / MCEER Isolation-Damper",
        "benchmark_family": "seismic_isolation_damping",
        "hazard_family": "seismic_isolated",
        "topology_family": "base_isolation_damper_network",
        "load_path_family": "hysteretic_device_sequence",
        "primary_report_path": "implementation/phase1/damper_validation_gate_report.json",
        "supporting_reports": {
            "nonlinear_generalization": "implementation/phase1/nonlinear_generalization_gate_report.json",
        },
        "kpi_specs": [
            {"label": "case_count", "source": "primary.summary.case_count"},
            {"label": "waveform_corr_min", "source": "primary.summary.waveform_corr_min"},
            {"label": "phase_error_ms_max", "source": "primary.summary.phase_error_ms_max"},
            {"label": "residual_drift_mm_max", "source": "primary.summary.residual_drift_mm_max"},
            {"label": "damping_reduction_ratio_mean", "source": "primary.summary.damping_reduction_ratio_mean"},
            {"label": "device_section_family_count", "source": "supporting.nonlinear_generalization.summary.device_section_family_count"},
        ],
    },
    {
        "case_id": "iass_dome_snapthrough",
        "label": "IASS Dome Snap-through",
        "benchmark_family": "buckling_snapthrough",
        "hazard_family": "buckling_instability",
        "topology_family": "shell_dome_large_deformation",
        "load_path_family": "limit_point_snapthrough",
        "primary_report_path": "implementation/phase1/buckling_contract_report.json",
        "supporting_reports": {
            "nonlinear_generalization": "implementation/phase1/nonlinear_generalization_gate_report.json",
        },
        "kpi_specs": [
            {"label": "critical_load_factor", "source": "primary.critical_load_factor"},
            {"label": "mode_count", "source": "primary.mode_count"},
            {"label": "selected_mode", "source": "primary.selected_mode"},
            {"label": "layered_family_count", "source": "supporting.nonlinear_generalization.summary.layered_family_count"},
        ],
    },
    {
        "case_id": "aci_fib_construction_stage_csa",
        "label": "ACI / FIB Construction Stage CSA",
        "benchmark_family": "construction_stage_time_dependent",
        "hazard_family": "time_dependent_construction",
        "topology_family": "staged_highrise_megastructure",
        "load_path_family": "creep_shrinkage_stage_sequence",
        "primary_report_path": "implementation/phase1/construction_sequence_gate_report.json",
        "supporting_reports": {
            "material_constitutive": "implementation/phase1/material_constitutive_gate_report.json",
        },
        "kpi_specs": [
            {"label": "case_count", "source": "primary.summary.case_count"},
            {"label": "stage_count", "source": "primary.summary.stage_count"},
            {"label": "construction_years", "source": "primary.summary.construction_years"},
            {"label": "max_differential_shortening_mm", "source": "primary.summary.max_differential_shortening_mm"},
            {"label": "mean_creep_index", "source": "primary.summary.mean_creep_index"},
            {"label": "mean_shrinkage_index", "source": "primary.summary.mean_shrinkage_index"},
        ],
    },
    {
        "case_id": "oc3_oc4_offshore_monopile",
        "label": "OC3 / OC4 Offshore Monopile",
        "benchmark_family": "offshore_multiphysics_ssi",
        "hazard_family": "wave_wind_soil_sequence",
        "topology_family": "offshore_monopile_foundation",
        "load_path_family": "multiphysics_ssi_fatigue",
        "primary_report_path": "implementation/phase1/foundation_soil_link_gate_report.json",
        "supporting_reports": {
            "ssi_boundary": "implementation/phase1/ssi_boundary_gate_report.json",
            "surface_interaction": "implementation/phase1/surface_interaction_benchmark_gate_report.json",
        },
        "kpi_specs": [
            {"label": "foundation_member_type_count", "source": "primary.summary.foundation_member_type_count"},
            {"label": "optimized_foundation_group_count", "source": "primary.summary.optimized_foundation_group_count"},
            {"label": "foundation_link_model_types", "source": "primary.summary.foundation_link_model_types"},
            {"label": "soil_profile", "source": "supporting.ssi_boundary.summary.soil_profile"},
            {"label": "dominant_frequency_hz", "source": "supporting.ssi_boundary.summary.dominant_frequency_hz"},
            {"label": "footing_soil_interaction_count", "source": "supporting.surface_interaction.summary.interaction_family_group_ready_counts.footing_soil"},
        ],
    },
    {
        "case_id": "tc204_excavation_tunnel",
        "label": "TC204 Excavation and Adjacent Tunnel",
        "benchmark_family": "excavation_tunnel_ground_interaction",
        "hazard_family": "excavation_settlement",
        "topology_family": "deep_excavation_adjacent_tunnel",
        "load_path_family": "soil_tunnel_surface_sequence",
        "primary_report_path": "implementation/phase1/tunnel_dynamics_dataset_report.json",
        "supporting_reports": {
            "ssi_boundary": "implementation/phase1/ssi_boundary_gate_report.json",
            "foundation_soil_link": "implementation/phase1/foundation_soil_link_gate_report.json",
            "surface_interaction": "implementation/phase1/surface_interaction_benchmark_gate_report.json",
        },
        "kpi_specs": [
            {"label": "production_seed_success_count", "source": "primary.production_seed_success_count"},
            {"label": "dataset_case_count", "source": "primary.outputs.case_count"},
            {"label": "max_equilibrium_residual", "source": "primary.metrics.max_equilibrium_residual"},
            {"label": "mean_displacement_m", "source": "primary.metrics.mean_displacement_m"},
            {"label": "soil_tunnel_interaction_count", "source": "supporting.surface_interaction.summary.interaction_family_group_ready_counts.soil_tunnel"},
            {"label": "foundation_member_type_count", "source": "supporting.foundation_soil_link.summary.foundation_member_type_count"},
        ],
    },
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _get_nested(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def catalog_rows() -> list[dict[str, Any]]:
    return [dict(row) for row in CASE_CATALOG]


def catalog_map() -> dict[str, dict[str, Any]]:
    return {str(row["case_id"]): dict(row) for row in CASE_CATALOG}


def _resolve_repo_path(raw: str) -> Path:
    return (REPO_ROOT / raw).resolve()


def load_case_payloads(case_row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    primary_payload = _load_json(_resolve_repo_path(str(case_row.get("primary_report_path", "") or "")))
    supporting_payloads = {
        role: _load_json(_resolve_repo_path(str(path) or ""))
        for role, path in (case_row.get("supporting_reports") or {}).items()
    }
    return primary_payload, supporting_payloads


def extract_case_kpis(
    case_row: dict[str, Any],
    primary_payload: dict[str, Any],
    supporting_payloads: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    context = {
        "primary": primary_payload,
        "supporting": supporting_payloads,
    }
    for spec in case_row.get("kpi_specs", []):
        if not isinstance(spec, dict):
            continue
        label = str(spec.get("label", "") or "").strip()
        source = str(spec.get("source", "") or "").strip()
        if not label or not source:
            continue
        root_name, _, dotted_path = source.partition(".")
        root_payload = context.get(root_name)
        value = None
        if isinstance(root_payload, dict) and dotted_path:
            value = _get_nested(root_payload, dotted_path)
        rows.append(
            {
                "label": label,
                "source": source,
                "value": value,
            }
        )
    return rows


def primary_summary_head(primary_payload: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    summary = primary_payload.get("summary")
    if not isinstance(summary, dict):
        return {}
    return {key: summary[key] for key in list(summary.keys())[:limit]}

