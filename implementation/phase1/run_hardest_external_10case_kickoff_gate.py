#!/usr/bin/env python3
"""Aggregate readiness to start the hardest external 10-case validation program."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "hardest external 10-case kickoff boundary is ready to start now; any remaining review boundary is limited to final submission closure rather than kickoff execution",
    "ERR_INVALID_INPUT": "invalid hardest external 10-case kickoff gate input",
    "ERR_SOLVER_TRUTHFULNESS": "top-level solver truthfulness is not ready for hardest external kickoff",
    "ERR_SOLVER_HIP": "solver HIP production breadth is not ready for hardest external kickoff",
    "ERR_NONLINEAR_GENERALIZATION": "nonlinear generalization breadth is not ready for hardest external kickoff",
    "ERR_WORKFLOW_PRODUCTIZATION": "workflow productization boundary is not ready for hardest external kickoff",
    "ERR_COMMERCIAL_READINESS": "commercial readiness boundary is not ready for hardest external kickoff",
    "ERR_REAL_SOURCE_MULTI": "multi real-source coverage boundary is not ready for hardest external kickoff",
    "ERR_CASE_START_READINESS": "one or more hardest external cases are not ready to start",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "solver_truthfulness_report",
        "solver_hip_e2e_report",
        "nonlinear_generalization_report",
        "workflow_productization_report",
        "commercial_readiness_report",
        "real_source_multi_report",
        "material_constitutive_report",
        "surface_interaction_benchmark_report",
        "wind_benchmark_report",
        "ssi_boundary_report",
        "damper_validation_report",
        "construction_sequence_report",
        "pushover_stress_report",
        "ndtha_stress_report",
        "buckling_contract_report",
        "track_lf_solver_report",
        "moving_load_integrator_report",
        "vti_coupled_solver_report",
        "tunnel_dynamics_dataset_report",
        "foundation_soil_link_gate_report",
        "out",
    ],
    "properties": {
        "solver_truthfulness_report": {"type": "string", "minLength": 1},
        "solver_hip_e2e_report": {"type": "string", "minLength": 1},
        "nonlinear_generalization_report": {"type": "string", "minLength": 1},
        "workflow_productization_report": {"type": "string", "minLength": 1},
        "commercial_readiness_report": {"type": "string", "minLength": 1},
        "real_source_multi_report": {"type": "string", "minLength": 1},
        "material_constitutive_report": {"type": "string", "minLength": 1},
        "surface_interaction_benchmark_report": {"type": "string", "minLength": 1},
        "wind_benchmark_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "damper_validation_report": {"type": "string", "minLength": 1},
        "construction_sequence_report": {"type": "string", "minLength": 1},
        "pushover_stress_report": {"type": "string", "minLength": 1},
        "ndtha_stress_report": {"type": "string", "minLength": 1},
        "buckling_contract_report": {"type": "string", "minLength": 1},
        "track_lf_solver_report": {"type": "string", "minLength": 1},
        "moving_load_integrator_report": {"type": "string", "minLength": 1},
        "vti_coupled_solver_report": {"type": "string", "minLength": 1},
        "tunnel_dynamics_dataset_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_gate_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _truthy(report: dict[str, Any]) -> bool:
    if "contract_pass" in report:
        return bool(report.get("contract_pass", False))
    if "all_pass" in report:
        return bool(report.get("all_pass", False))
    if "pass" in report:
        return bool(report.get("pass", False))
    return False


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else {}


def _case_rows(availability: dict[str, bool]) -> list[dict[str, Any]]:
    catalog = [
        {
            "case_id": "peer_tbi_tall_building_ndtha",
            "label": "PEER TBI Tall Building NDTHA",
            "benchmark_family": "highrise_ndtha",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "nonlinear_generalization",
                "commercial_readiness",
                "ndtha_stress",
            ],
        },
        {
            "case_id": "nheri_designsafe_ssi",
            "label": "NHERI DesignSafe SSI",
            "benchmark_family": "soil_structure_interaction",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "nonlinear_generalization",
                "surface_interaction",
                "ssi_boundary",
                "foundation_soil_link",
            ],
        },
        {
            "case_id": "uic_erri_rail_bridge",
            "label": "UIC / ERRI Railway Bridge",
            "benchmark_family": "moving_load_track_bridge",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "track_lf",
                "moving_load",
                "vti_coupled",
            ],
        },
        {
            "case_id": "nist_fema_progressive_collapse",
            "label": "NIST / FEMA Progressive Collapse",
            "benchmark_family": "progressive_collapse",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "nonlinear_generalization",
                "material_constitutive",
                "pushover_stress",
                "ndtha_stress",
            ],
        },
        {
            "case_id": "caarc_wind_standard_tower",
            "label": "CAARC Wind Standard Tower",
            "benchmark_family": "wind_time_history",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "wind_benchmark",
                "workflow_productization",
            ],
        },
        {
            "case_id": "nceer_mceer_isolation_damper",
            "label": "NCEER / MCEER Isolation-Damper",
            "benchmark_family": "seismic_isolation_damping",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "nonlinear_generalization",
                "damper_validation",
            ],
        },
        {
            "case_id": "iass_dome_snapthrough",
            "label": "IASS Dome Snap-through",
            "benchmark_family": "buckling_snapthrough",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "nonlinear_generalization",
                "buckling_contract",
            ],
        },
        {
            "case_id": "aci_fib_construction_stage_csa",
            "label": "ACI / FIB Construction Stage CSA",
            "benchmark_family": "construction_stage_time_dependent",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "material_constitutive",
                "construction_sequence",
            ],
        },
        {
            "case_id": "oc3_oc4_offshore_monopile",
            "label": "OC3 / OC4 Offshore Monopile",
            "benchmark_family": "offshore_multiphysics_ssi",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "nonlinear_generalization",
                "surface_interaction",
                "ssi_boundary",
                "foundation_soil_link",
            ],
        },
        {
            "case_id": "tc204_excavation_tunnel",
            "label": "TC204 Excavation and Adjacent Tunnel",
            "benchmark_family": "excavation_tunnel_ground_interaction",
            "requirements": [
                "solver_truthfulness",
                "solver_hip",
                "surface_interaction",
                "ssi_boundary",
                "tunnel_dataset",
                "foundation_soil_link",
            ],
        },
    ]
    rows: list[dict[str, Any]] = []
    for row in catalog:
        missing = [key for key in row["requirements"] if not availability.get(key, False)]
        rows.append(
            {
                **row,
                "ready_to_start": not missing,
                "missing_requirements": missing,
                "missing_requirement_label": ", ".join(missing) if missing else "none",
            }
        )
    return rows


def run_hardest_external_10case_kickoff_gate(
    *,
    solver_truthfulness_report: dict[str, Any],
    solver_hip_e2e_report: dict[str, Any],
    nonlinear_generalization_report: dict[str, Any],
    workflow_productization_report: dict[str, Any],
    commercial_readiness_report: dict[str, Any],
    real_source_multi_report: dict[str, Any],
    material_constitutive_report: dict[str, Any],
    surface_interaction_benchmark_report: dict[str, Any],
    wind_benchmark_report: dict[str, Any],
    ssi_boundary_report: dict[str, Any],
    damper_validation_report: dict[str, Any],
    construction_sequence_report: dict[str, Any],
    pushover_stress_report: dict[str, Any],
    ndtha_stress_report: dict[str, Any],
    buckling_contract_report: dict[str, Any],
    track_lf_solver_report: dict[str, Any],
    moving_load_integrator_report: dict[str, Any],
    vti_coupled_solver_report: dict[str, Any],
    tunnel_dynamics_dataset_report: dict[str, Any],
    foundation_soil_link_gate_report: dict[str, Any],
) -> dict[str, Any]:
    truth_summary = _summary(solver_truthfulness_report)
    hip_summary = _summary(solver_hip_e2e_report)
    nonlinear_summary = _summary(nonlinear_generalization_report)
    workflow_summary = _summary(workflow_productization_report)
    workflow_checks = workflow_productization_report.get("checks") if isinstance(workflow_productization_report.get("checks"), dict) else {}
    commercial_summary = _summary(commercial_readiness_report)
    commercial_metrics = (
        commercial_readiness_report.get("global_metrics")
        if isinstance(commercial_readiness_report.get("global_metrics"), dict)
        else {}
    )
    commercial_checks = commercial_readiness_report.get("checks") if isinstance(commercial_readiness_report.get("checks"), dict) else {}

    solver_truthfulness_pass = bool(
        _truthy(solver_truthfulness_report)
        and int(truth_summary.get("top_level_production_seeded_runtime_count", 0) or 0) >= 4
        and int(truth_summary.get("top_level_runtime_policy_satisfied_count", 0) or 0) >= 4
        and int(truth_summary.get("surrogate_marker_count", 1) or 0) == 0
        and int(truth_summary.get("cpu_fallback_count", 1) or 0) == 0
    )
    solver_hip_pass = bool(
        _truthy(solver_hip_e2e_report)
        and int(hip_summary.get("production_kernel_solver_count", 0) or 0) >= 20
        and int(hip_summary.get("surrogate_runtime_free_solver_count", 0) or 0) >= 20
        and int(hip_summary.get("hazard_family_count", 0) or 0) >= 20
        and int(hip_summary.get("topology_family_count", 0) or 0) >= 15
        and int(hip_summary.get("load_path_family_count", 0) or 0) >= 15
    )
    nonlinear_generalization_pass = bool(
        _truthy(nonlinear_generalization_report)
        and int(nonlinear_summary.get("beam_family_count", 0) or 0) >= 6
        and int(nonlinear_summary.get("fiber_family_count", 0) or 0) >= 6
        and int(nonlinear_summary.get("layered_family_count", 0) or 0) >= 6
        and int(nonlinear_summary.get("joint_panel_family_count", 0) or 0) >= 4
        and int(nonlinear_summary.get("foundation_section_family_count", 0) or 0) >= 4
        and int(nonlinear_summary.get("device_section_family_count", 0) or 0) >= 4
        and int(nonlinear_summary.get("isolation_section_family_count", 0) or 0) >= 4
        and int(nonlinear_summary.get("soil_interface_section_family_count", 0) or 0) >= 4
    )
    workflow_productization_pass = bool(
        _truthy(workflow_productization_report)
        and bool(workflow_checks.get("signed_submission_bundle_pass", False))
        and bool(workflow_checks.get("auto_approved_subset_pass", False))
        and int(workflow_summary.get("generated_signed_submission_bundle_count", 0) or 0) >= 6
    )
    commercial_readiness_pass = bool(
        _truthy(commercial_readiness_report)
        and bool(commercial_checks.get("real_source_pass", False))
        and bool(commercial_checks.get("gpu_strict_pass", False))
    )
    real_source_multi_pass = bool(_truthy(real_source_multi_report))

    availability = {
        "solver_truthfulness": solver_truthfulness_pass,
        "solver_hip": solver_hip_pass,
        "nonlinear_generalization": nonlinear_generalization_pass,
        "workflow_productization": workflow_productization_pass,
        "commercial_readiness": commercial_readiness_pass,
        "material_constitutive": bool(_truthy(material_constitutive_report)),
        "surface_interaction": bool(_truthy(surface_interaction_benchmark_report)),
        "wind_benchmark": bool(_truthy(wind_benchmark_report)),
        "ssi_boundary": bool(_truthy(ssi_boundary_report)),
        "damper_validation": bool(_truthy(damper_validation_report)),
        "construction_sequence": bool(_truthy(construction_sequence_report)),
        "pushover_stress": bool(_truthy(pushover_stress_report)),
        "ndtha_stress": bool(_truthy(ndtha_stress_report)),
        "buckling_contract": bool(_truthy(buckling_contract_report)),
        "track_lf": bool(_truthy(track_lf_solver_report)),
        "moving_load": bool(_truthy(moving_load_integrator_report)),
        "vti_coupled": bool(_truthy(vti_coupled_solver_report)),
        "tunnel_dataset": bool(_truthy(tunnel_dynamics_dataset_report)),
        "foundation_soil_link": bool(_truthy(foundation_soil_link_gate_report)),
    }
    case_rows = _case_rows(availability)
    ready_case_count = sum(1 for row in case_rows if row["ready_to_start"])

    pending_review_count = int(workflow_summary.get("audit_queue_count", 0) or 0)
    approve_all_reason_code = str(workflow_summary.get("approve_all_preview_reason_code", "") or "").strip()
    if workflow_productization_pass and pending_review_count == 0 and approve_all_reason_code == "PASS_START_NOW_FULL":
        recommended_start_mode = "start_now_full_external_submission"
        ready_to_start_full_submission_now = True
    elif workflow_productization_pass:
        recommended_start_mode = "start_now_limited_external_benchmark"
        ready_to_start_full_submission_now = False
    else:
        recommended_start_mode = "wait_for_blockers"
        ready_to_start_full_submission_now = False

    base_boundary_pass = bool(
        solver_truthfulness_pass
        and solver_hip_pass
        and nonlinear_generalization_pass
        and workflow_productization_pass
        and commercial_readiness_pass
        and real_source_multi_pass
    )
    ready_to_start_now = bool(base_boundary_pass and ready_case_count == len(case_rows))

    if not solver_truthfulness_pass:
        reason_code = "ERR_SOLVER_TRUTHFULNESS"
    elif not solver_hip_pass:
        reason_code = "ERR_SOLVER_HIP"
    elif not nonlinear_generalization_pass:
        reason_code = "ERR_NONLINEAR_GENERALIZATION"
    elif not workflow_productization_pass:
        reason_code = "ERR_WORKFLOW_PRODUCTIZATION"
    elif not commercial_readiness_pass:
        reason_code = "ERR_COMMERCIAL_READINESS"
    elif not real_source_multi_pass:
        reason_code = "ERR_REAL_SOURCE_MULTI"
    elif ready_case_count != len(case_rows):
        reason_code = "ERR_CASE_START_READINESS"
    else:
        reason_code = "PASS"

    blocked_case_ids = [str(row["case_id"]) for row in case_rows if not row["ready_to_start"]]
    measured_source_family_count = int(
        commercial_summary.get("measured_source_family_count", commercial_metrics.get("measured_source_family_count", 0))
        or 0
    )
    measured_case_count = int(
        commercial_summary.get("measured_case_count", commercial_metrics.get("measured_case_count", 0)) or 0
    )
    summary_line = (
        f"Hardest external 10-case kickoff: {'PASS' if reason_code == 'PASS' else 'GAP'} | "
        f"ready={ready_case_count}/{len(case_rows)} | "
        f"start_now={'yes' if ready_to_start_now else 'no'} | "
        f"mode={recommended_start_mode} | "
        f"full_submission={'yes' if ready_to_start_full_submission_now else 'no'} | "
        f"review_pending={pending_review_count} | "
        f"measured_families={measured_source_family_count} | "
        f"measured_cases={measured_case_count}"
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "summary_line": summary_line,
        "checks": {
            "solver_truthfulness_pass": solver_truthfulness_pass,
            "solver_hip_pass": solver_hip_pass,
            "nonlinear_generalization_pass": nonlinear_generalization_pass,
            "workflow_productization_pass": workflow_productization_pass,
            "commercial_readiness_pass": commercial_readiness_pass,
            "real_source_multi_pass": real_source_multi_pass,
            "base_boundary_pass": base_boundary_pass,
            "ready_cases_pass": ready_case_count == len(case_rows),
        },
        "summary": {
            "case_count": len(case_rows),
            "ready_case_count": ready_case_count,
            "blocked_case_count": len(case_rows) - ready_case_count,
            "ready_case_ids": [str(row["case_id"]) for row in case_rows if row["ready_to_start"]],
            "blocked_case_ids": blocked_case_ids,
            "ready_to_start_now": ready_to_start_now,
            "ready_to_start_full_submission_now": ready_to_start_full_submission_now,
            "recommended_start_mode": recommended_start_mode,
            "audit_review_queue_pending_count": pending_review_count,
            "approve_all_preview_reason_code": approve_all_reason_code,
            "generated_signed_submission_bundle_count": int(
                workflow_summary.get("generated_signed_submission_bundle_count", 0) or 0
            ),
            "measured_source_family_count": measured_source_family_count,
            "measured_case_count": measured_case_count,
        },
        "cases": case_rows,
        "artifacts": {
            "solver_truthfulness_report": "implementation/phase1/solver_truthfulness_gate_report.json",
            "solver_hip_e2e_report": "implementation/phase1/solver_hip_e2e_contract_report.json",
            "nonlinear_generalization_report": "implementation/phase1/nonlinear_generalization_gate_report.json",
            "workflow_productization_report": "implementation/phase1/workflow_productization_gate_report.json",
            "commercial_readiness_report": "implementation/phase1/commercial_readiness_report.json",
            "real_source_multi_report": "implementation/phase1/real_source_multi_gate_report.json",
            "material_constitutive_report": "implementation/phase1/material_constitutive_gate_report.json",
            "surface_interaction_benchmark_report": "implementation/phase1/surface_interaction_benchmark_gate_report.json",
            "wind_benchmark_report": "implementation/phase1/wind_time_history_gate_report.json",
            "ssi_boundary_report": "implementation/phase1/ssi_boundary_gate_report.json",
            "damper_validation_report": "implementation/phase1/damper_validation_gate_report.json",
            "construction_sequence_report": "implementation/phase1/construction_sequence_gate_report.json",
            "pushover_stress_report": "implementation/phase1/nonlinear_pushover_stress_report.json",
            "ndtha_stress_report": "implementation/phase1/nonlinear_ndtha_stress_report.json",
            "buckling_contract_report": "implementation/phase1/buckling_contract_report.json",
            "track_lf_solver_report": "implementation/phase1/track_lf_solver_report.json",
            "moving_load_integrator_report": "implementation/phase1/moving_load_integrator_report.json",
            "vti_coupled_solver_report": "implementation/phase1/vti_coupled_solver_report.json",
            "tunnel_dynamics_dataset_report": "implementation/phase1/tunnel_dynamics_dataset_report.json",
            "foundation_soil_link_gate_report": "implementation/phase1/foundation_soil_link_gate_report.json",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-truthfulness-report", default="implementation/phase1/solver_truthfulness_gate_report.json")
    parser.add_argument("--solver-hip-e2e-report", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    parser.add_argument("--nonlinear-generalization-report", default="implementation/phase1/nonlinear_generalization_gate_report.json")
    parser.add_argument("--workflow-productization-report", default="implementation/phase1/workflow_productization_gate_report.json")
    parser.add_argument("--commercial-readiness-report", default="implementation/phase1/commercial_readiness_report.json")
    parser.add_argument("--real-source-multi-report", default="implementation/phase1/real_source_multi_gate_report.json")
    parser.add_argument("--material-constitutive-report", default="implementation/phase1/material_constitutive_gate_report.json")
    parser.add_argument("--surface-interaction-benchmark-report", default="implementation/phase1/surface_interaction_benchmark_gate_report.json")
    parser.add_argument("--wind-benchmark-report", default="implementation/phase1/wind_time_history_gate_report.json")
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--damper-validation-report", default="implementation/phase1/damper_validation_gate_report.json")
    parser.add_argument("--construction-sequence-report", default="implementation/phase1/construction_sequence_gate_report.json")
    parser.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    parser.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    parser.add_argument("--buckling-contract-report", default="implementation/phase1/buckling_contract_report.json")
    parser.add_argument("--track-lf-solver-report", default="implementation/phase1/track_lf_solver_report.json")
    parser.add_argument("--moving-load-integrator-report", default="implementation/phase1/moving_load_integrator_report.json")
    parser.add_argument("--vti-coupled-solver-report", default="implementation/phase1/vti_coupled_solver_report.json")
    parser.add_argument("--tunnel-dynamics-dataset-report", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    parser.add_argument("--foundation-soil-link-gate-report", default="implementation/phase1/foundation_soil_link_gate_report.json")
    parser.add_argument("--out", default="implementation/phase1/hardest_external_10case_kickoff_gate_report.json")
    args = parser.parse_args(argv)

    payload = {
        "solver_truthfulness_report": args.solver_truthfulness_report,
        "solver_hip_e2e_report": args.solver_hip_e2e_report,
        "nonlinear_generalization_report": args.nonlinear_generalization_report,
        "workflow_productization_report": args.workflow_productization_report,
        "commercial_readiness_report": args.commercial_readiness_report,
        "real_source_multi_report": args.real_source_multi_report,
        "material_constitutive_report": args.material_constitutive_report,
        "surface_interaction_benchmark_report": args.surface_interaction_benchmark_report,
        "wind_benchmark_report": args.wind_benchmark_report,
        "ssi_boundary_report": args.ssi_boundary_report,
        "damper_validation_report": args.damper_validation_report,
        "construction_sequence_report": args.construction_sequence_report,
        "pushover_stress_report": args.pushover_stress_report,
        "ndtha_stress_report": args.ndtha_stress_report,
        "buckling_contract_report": args.buckling_contract_report,
        "track_lf_solver_report": args.track_lf_solver_report,
        "moving_load_integrator_report": args.moving_load_integrator_report,
        "vti_coupled_solver_report": args.vti_coupled_solver_report,
        "tunnel_dynamics_dataset_report": args.tunnel_dynamics_dataset_report,
        "foundation_soil_link_gate_report": args.foundation_soil_link_gate_report,
        "out": args.out,
    }
    try:
        validate_input_contract(payload, INPUT_SCHEMA, label="hardest_external_10case_kickoff_gate")
    except InputContractError as exc:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_payload = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": REASONS["ERR_INVALID_INPUT"],
            "error": str(exc),
        }
        out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    report = run_hardest_external_10case_kickoff_gate(
        solver_truthfulness_report=_load_json(Path(args.solver_truthfulness_report)),
        solver_hip_e2e_report=_load_json(Path(args.solver_hip_e2e_report)),
        nonlinear_generalization_report=_load_json(Path(args.nonlinear_generalization_report)),
        workflow_productization_report=_load_json(Path(args.workflow_productization_report)),
        commercial_readiness_report=_load_json(Path(args.commercial_readiness_report)),
        real_source_multi_report=_load_json(Path(args.real_source_multi_report)),
        material_constitutive_report=_load_json(Path(args.material_constitutive_report)),
        surface_interaction_benchmark_report=_load_json(Path(args.surface_interaction_benchmark_report)),
        wind_benchmark_report=_load_json(Path(args.wind_benchmark_report)),
        ssi_boundary_report=_load_json(Path(args.ssi_boundary_report)),
        damper_validation_report=_load_json(Path(args.damper_validation_report)),
        construction_sequence_report=_load_json(Path(args.construction_sequence_report)),
        pushover_stress_report=_load_json(Path(args.pushover_stress_report)),
        ndtha_stress_report=_load_json(Path(args.ndtha_stress_report)),
        buckling_contract_report=_load_json(Path(args.buckling_contract_report)),
        track_lf_solver_report=_load_json(Path(args.track_lf_solver_report)),
        moving_load_integrator_report=_load_json(Path(args.moving_load_integrator_report)),
        vti_coupled_solver_report=_load_json(Path(args.vti_coupled_solver_report)),
        tunnel_dynamics_dataset_report=_load_json(Path(args.tunnel_dynamics_dataset_report)),
        foundation_soil_link_gate_report=_load_json(Path(args.foundation_soil_link_gate_report)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote hardest external 10-case kickoff gate report: {out_path}")
    return 0 if report.get("contract_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
