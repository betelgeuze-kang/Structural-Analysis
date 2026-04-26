#!/usr/bin/env python3
"""Generate a release-consumable commercialization breadth report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.construction_stage_engine import generate_construction_stage_report
    from implementation.phase1.design_report_book import (
        build_design_report_book,
        write_design_report_book_artifacts,
    )
    from implementation.phase1.rail_tunnel_postprocess import build_postprocess_report
    from implementation.phase1.section_optimizer import (
        generate_section_suggestions,
        write_section_optimizer_artifacts,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from construction_stage_engine import generate_construction_stage_report
    from design_report_book import build_design_report_book, write_design_report_book_artifacts
    from rail_tunnel_postprocess import build_postprocess_report
    from section_optimizer import generate_section_suggestions, write_section_optimizer_artifacts


DEFAULT_OUT = Path("implementation/phase1/release/commercial_workflow_breadth_report.json")
DEFAULT_COMPONENT_DIR = Path("implementation/phase1/release/commercialization")
DEFAULT_CONSTRUCTION_SEQUENCE_GATE = Path("implementation/phase1/construction_sequence_gate_report.json")


def _sample_construction_stage_payload() -> dict[str, Any]:
    return {
        "elements": [
            {"id": "FOUND", "kind": "foundation", "stiffness": 120.0, "capacity": 2.0, "self_weight": 12.0},
            {"id": "COL1", "kind": "column", "stiffness": 100.0, "capacity": 1.5, "self_weight": 10.0},
            {"id": "BEAM1", "kind": "beam", "stiffness": 80.0, "capacity": 1.0, "self_weight": 8.0},
        ],
        "loads": [
            {"id": "DL_COL", "target": "COL1", "magnitude": 30.0},
            {"id": "DL_BEAM", "target": "BEAM1", "magnitude": 20.0},
        ],
        "stages": [
            {
                "name": "foundation_and_core",
                "duration_days": 10.0,
                "load_scale": 0.5,
                "activate_elements": ["FOUND", "COL1"],
                "activate_loads": ["DL_COL"],
            },
            {
                "name": "framing",
                "duration_days": 20.0,
                "load_scale": 1.0,
                "activate_elements": ["BEAM1"],
                "activate_loads": ["DL_BEAM"],
            },
            {
                "name": "strip_beam",
                "duration_days": 5.0,
                "load_scale": 1.0,
                "deactivate_elements": ["BEAM1"],
            },
        ],
        "max_utilization_ratio": 1.0,
    }


def _sample_rail_tunnel_payload() -> dict[str, Any]:
    return {
        "case_id": "release_fixture_case",
        "metadata": {
            "source_mode": "release_fixture",
            "nominal_clearance_mm": 105.0,
        },
        "track_samples": [
            {"location_id": "CH000", "chainage_m": 0.0, "rail_settlement_mm": -1.0, "tunnel_crown_settlement_mm": -0.5},
            {"location_id": "CH010", "chainage_m": 10.0, "rail_settlement_mm": -3.0, "tunnel_crown_settlement_mm": -1.0},
            {"location_id": "CH020", "chainage_m": 20.0, "rail_settlement_mm": -2.0, "tunnel_crown_settlement_mm": -0.7, "clearance_mm": 98.0},
        ],
        "lining_samples": [
            {
                "ring_id": "R-A",
                "position_deg": 0.0,
                "moment_kNm": 220.0,
                "moment_capacity_kNm": 400.0,
                "axial_force_kN": 820.0,
                "axial_capacity_kN": 1600.0,
                "shear_kN": 42.0,
                "shear_capacity_kN": 100.0,
                "longitudinal_strain": 0.0010,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-A",
                "position_deg": 180.0,
                "moment_kNm": 260.0,
                "moment_capacity_kNm": 400.0,
                "axial_force_kN": 910.0,
                "axial_capacity_kN": 1600.0,
                "shear_kN": 48.0,
                "shear_capacity_kN": 100.0,
                "longitudinal_strain": 0.0012,
                "strain_capacity": 0.0025,
            },
            {
                "ring_id": "R-B",
                "position_deg": 90.0,
                "moment_kNm": 180.0,
                "moment_capacity_kNm": 450.0,
                "utilization": 0.88,
            },
        ],
        "vibration_samples": [
            {"location_id": "V1", "chainage_m": 10.0, "freq_hz": 16.0, "velocity_mm_s": 0.19},
            {"location_id": "V2", "chainage_m": 20.0, "freq_hz": 31.5, "velocity_mm_s": 0.22},
        ],
    }


def _sample_rail_tunnel_thresholds() -> dict[str, Any]:
    return {
        "max_abs_settlement_mm": 8.0,
        "max_diff_settlement_mm": 3.0,
        "min_clearance_mm": 95.0,
        "max_lining_utilization": 1.0,
        "max_vibration_velocity_mm_s": 0.25,
        "nominal_clearance_mm": 105.0,
        "lining_moment_capacity_kNm": 650.0,
        "lining_strain_capacity": 0.0025,
    }


def _code_check_report_fixture() -> dict[str, Any]:
    return {
        "contract_pass": False,
        "summary": {
            "member_count": 5,
            "member_check_row_count": 10,
            "max_dcr": 1.24,
        },
        "rows": [
            {
                "member_id": "B1",
                "case_id": "CASE-B1",
                "member_type": "beam",
                "hazard_type": "seismic",
                "topology_type": "rahmen",
                "governing_component": "flexure",
                "governing_combination": "KDS_ULS_1",
                "max_dcr": 1.24,
            },
            {
                "member_id": "W1",
                "case_id": "CASE-W1",
                "member_type": "wall",
                "hazard_type": "seismic",
                "topology_type": "wall-frame",
                "governing_component": "boundary_element",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 1.12,
            },
            {
                "member_id": "S1",
                "case_id": "CASE-S1",
                "member_type": "slab",
                "hazard_type": "gravity",
                "topology_type": "wall-frame",
                "governing_component": "punching",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 1.18,
            },
            {
                "member_id": "C1",
                "case_id": "CASE-C1",
                "member_type": "column",
                "hazard_type": "wind",
                "topology_type": "outrigger",
                "governing_component": "axial_flexure",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 0.52,
            },
            {
                "member_id": "N1",
                "case_id": "CASE-N1",
                "member_type": "connection",
                "hazard_type": "seismic",
                "topology_type": "jointed-frame",
                "governing_component": "slip",
                "governing_combination": "RC_DETAIL",
                "max_dcr": 1.08,
            },
        ],
        "member_check_rows": [
            {
                "member_id": "B1",
                "case_id": "CASE-B1",
                "member_type": "beam",
                "hazard_type": "seismic",
                "topology_type": "rahmen",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "flexure",
                "clause": "KDS-RC-BEAM-FLEX-001",
                "dcr": 1.24,
            },
            {
                "member_id": "B1",
                "case_id": "CASE-B1",
                "member_type": "beam",
                "hazard_type": "seismic",
                "topology_type": "rahmen",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "shear",
                "clause": "KDS-RC-BEAM-SHEAR-001",
                "dcr": 1.05,
            },
            {
                "member_id": "W1",
                "case_id": "CASE-W1",
                "member_type": "wall",
                "hazard_type": "seismic",
                "topology_type": "wall-frame",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "boundary_element",
                "clause": "KDS-RC-WALL-BE-001",
                "dcr": 1.12,
            },
            {
                "member_id": "S1",
                "case_id": "CASE-S1",
                "member_type": "slab",
                "hazard_type": "gravity",
                "topology_type": "wall-frame",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "punching",
                "clause": "KDS-RC-SLAB-PUNCH-001",
                "dcr": 1.18,
            },
            {
                "member_id": "C1",
                "case_id": "CASE-C1",
                "member_type": "column",
                "hazard_type": "wind",
                "topology_type": "outrigger",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "axial_flexure",
                "clause": "KDS-RC-COL-INT-001",
                "dcr": 0.52,
            },
            {
                "member_id": "N1",
                "case_id": "CASE-N1",
                "member_type": "connection",
                "hazard_type": "seismic",
                "topology_type": "jointed-frame",
                "rule_family": "rc_detail",
                "combination": "RC_DETAIL",
                "component": "slip",
                "clause": "KDS-RC-CONN-SLIP-001",
                "dcr": 1.08,
            },
        ],
    }


def _design_optimization_fixture() -> dict[str, Any]:
    return {
        "summary": {
            "accepted_count": 2,
            "cost_reduction_proxy": 184.25,
            "final_max_dcr": 0.98,
        },
        "accepted_head": [
            {
                "member_id": "C1",
                "member_type": "column",
                "action_name": "perimeter_frame_down",
                "action_family": "perimeter_frame",
                "governing_clause_label": "KDS-RC-COL-INT-001",
                "projected_cost_delta": -42.0,
                "max_dcr": 0.52,
                "viewer_row_url": "../viewer?member=C1",
            },
            {
                "member_id": "N1",
                "member_type": "connection",
                "action_name": "connection_detailing_up",
                "action_family": "connection_detailing",
                "governing_clause_label": "KDS-RC-CONN-SLIP-001",
                "projected_cost_delta": 15.0,
                "max_dcr": 1.08,
                "viewer_row_url": "../viewer?member=N1",
            },
        ],
    }


def _construction_stage_breadth(
    *,
    construction_sequence_gate_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = generate_construction_stage_report(_sample_construction_stage_payload())
    sequence_summary = (
        construction_sequence_gate_report.get("summary")
        if isinstance((construction_sequence_gate_report or {}).get("summary"), dict)
        else {}
    )
    history_snapshot_count = int(report.get("summary", {}).get("history_snapshot_count", 0) or 0)
    shortening_mm = float(sequence_summary.get("max_differential_shortening_mm", 0.0) or 0.0)
    stage_count = int(sequence_summary.get("stage_count", report.get("summary", {}).get("stage_count", 0) or 0) or 0)
    ready = bool(
        report.get("contract_pass", False)
        and history_snapshot_count > 0
        and stage_count > 0
        and shortening_mm >= 0.0
    )
    return {
        "contract_pass": ready,
        "summary_line": (
            "Construction-stage breadth: "
            f"{'PASS' if ready else 'CHECK'} | "
            f"history_snapshots={history_snapshot_count} | "
            f"stage_count={stage_count} | "
            f"max_shortening_mm={shortening_mm:.3f}"
        ),
        "summary": {
            "construction_stage_ready": ready,
            "history_snapshot_count": history_snapshot_count,
            "max_differential_shortening_mm": shortening_mm,
            "stage_count": stage_count,
            "auto_deactivated_load_count_total": int(
                report.get("summary", {}).get("auto_deactivated_load_count_total", 0) or 0
            ),
            "validation_warning_count": int(report.get("summary", {}).get("validation_warning_count", 0) or 0),
        },
        "source_report": report,
    }


def _rail_tunnel_breadth() -> dict[str, Any]:
    report = build_postprocess_report(
        _sample_rail_tunnel_payload(),
        thresholds=_sample_rail_tunnel_thresholds(),
    )
    maintenance = report.get("summaries", {}).get("maintenance", {})
    ready = bool(report.get("contract_pass", False) and report.get("checks", {}).get("benchmark_pass", False))
    serviceability_status = "PASS" if ready else "CHECK"
    return {
        "contract_pass": ready,
        "summary_line": (
            "Rail/tunnel breadth: "
            f"{'PASS' if ready else 'CHECK'} | "
            f"serviceability={serviceability_status} | "
            f"maintenance={str(maintenance.get('priority', '') or 'n/a')} | "
            f"actions={len(maintenance.get('recommended_actions', []) or [])}"
        ),
        "summary": {
            "rail_tunnel_ready": ready,
            "serviceability_status": serviceability_status,
            "maintenance_priority": str(maintenance.get("priority", "") or "n/a"),
            "recommended_action_count": int(len(maintenance.get("recommended_actions", []) or [])),
        },
        "source_report": report,
    }


def _design_redesign_loop_breadth() -> dict[str, Any]:
    code_check_report = _code_check_report_fixture()
    design_optimization_report = _design_optimization_fixture()
    optimizer_payload = generate_section_suggestions(
        code_check_report=code_check_report,
        design_optimization_report=design_optimization_report,
    )
    design_report_payload = build_design_report_book(
        code_check_report=code_check_report,
        design_optimization_report=design_optimization_report,
        design_change_rows=[
            {
                "group_id": "C1-group",
                "member_type": "column",
                "action_name": "perimeter_frame_down",
                "action_family": "perimeter_frame",
                "governing_clause": "KDS-RC-COL-INT-001",
                "cost_proxy_delta": -42.0,
                "max_dcr_after": 0.52,
            }
        ],
        section_optimizer_report=optimizer_payload,
        external_design_sheet_diff_report={
            "summary": {
                "changed_row_count": 2,
                "added_row_count": 1,
                "removed_row_count": 0,
                "key_field": "member_id",
                "max_numeric_delta": 0.18,
                "shared_column_count": 4,
            },
            "changed_rows": [
                {
                    "row_key": "B1",
                    "changed_columns": ["dcr", "remark"],
                    "max_numeric_delta": 0.18,
                }
            ],
        },
    )
    design_summary = design_report_payload.get("summary", {})
    optimizer_summary = optimizer_payload.get("summary", {})
    ready = bool(
        design_report_payload.get("contract_pass", False)
        and optimizer_payload.get("contract_pass", False)
        and design_report_payload.get("checks", {}).get("governing_clause_traceability_pass", False)
        and optimizer_payload.get("checks", {}).get("governing_clause_traceability_pass", False)
    )
    return {
        "contract_pass": ready,
        "summary_line": (
            "Design redesign loop breadth: "
            f"{'PASS' if ready else 'CHECK'} | "
            f"trace={float(design_summary.get('governing_clause_traceability_ratio', 0.0) or 0.0) * 100.0:.1f}% | "
            f"ng={int(design_summary.get('ng_member_count', 0) or 0)} | "
            f"suggestions={int(optimizer_summary.get('suggestion_count', 0) or 0)} | "
            f"strengthen={int(optimizer_summary.get('strengthen_count', 0) or 0)} | "
            f"reduce={int(optimizer_summary.get('reduce_count', 0) or 0)}"
        ),
        "summary": {
            "design_redesign_loop_ready": ready,
            "design_report_traceability_ratio": float(
                design_summary.get("governing_clause_traceability_ratio", 0.0) or 0.0
            ),
            "design_report_ng_member_count": int(design_summary.get("ng_member_count", 0) or 0),
            "section_optimizer_suggestion_count": int(optimizer_summary.get("suggestion_count", 0) or 0),
            "section_optimizer_strengthen_count": int(optimizer_summary.get("strengthen_count", 0) or 0),
            "section_optimizer_reduce_count": int(optimizer_summary.get("reduce_count", 0) or 0),
            "governing_clause_count": int(optimizer_summary.get("governing_clause_count", 0) or 0),
        },
        "section_optimizer_report": optimizer_payload,
        "design_report_book": design_report_payload,
    }


def build_commercial_workflow_breadth_report(
    *,
    construction_sequence_gate_report: dict[str, Any] | None = None,
    component_dir: Path | None = None,
) -> dict[str, Any]:
    component_dir = component_dir or DEFAULT_COMPONENT_DIR
    construction = _construction_stage_breadth(
        construction_sequence_gate_report=construction_sequence_gate_report,
    )
    rail_tunnel = _rail_tunnel_breadth()
    design_redesign = _design_redesign_loop_breadth()

    component_dir.mkdir(parents=True, exist_ok=True)
    construction_artifact = component_dir / "construction_stage_breadth_report.json"
    rail_artifact = component_dir / "rail_tunnel_breadth_report.json"
    design_report_json = component_dir / "design_report_book.json"
    design_report_md = component_dir / "design_report_book.md"
    optimizer_json = component_dir / "section_optimizer_report.json"
    optimizer_csv = component_dir / "section_optimizer_report.csv"

    construction_artifact.write_text(
        json.dumps(construction["source_report"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rail_artifact.write_text(
        json.dumps(rail_tunnel["source_report"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_design_report_book_artifacts(
        design_redesign["design_report_book"],
        out_json=design_report_json,
        out_md=design_report_md,
    )
    write_section_optimizer_artifacts(
        design_redesign["section_optimizer_report"],
        out_json=optimizer_json,
        out_csv=optimizer_csv,
    )

    rows = [
        {
            "id": "construction_stage",
            "label": "Construction stage breadth",
            "status": "PASS" if construction["contract_pass"] else "CHECK",
            "summary_line": construction["summary_line"],
            "ready": bool(construction["contract_pass"]),
        },
        {
            "id": "rail_tunnel",
            "label": "Rail/tunnel breadth",
            "status": "PASS" if rail_tunnel["contract_pass"] else "CHECK",
            "summary_line": rail_tunnel["summary_line"],
            "ready": bool(rail_tunnel["contract_pass"]),
        },
        {
            "id": "design_redesign_loop",
            "label": "Design redesign loop breadth",
            "status": "PASS" if design_redesign["contract_pass"] else "CHECK",
            "summary_line": design_redesign["summary_line"],
            "ready": bool(design_redesign["contract_pass"]),
        },
    ]

    all_pass = all(bool(row["ready"]) for row in rows)
    summary = {
        "construction_stage_ready": bool(construction["contract_pass"]),
        "construction_stage_history_snapshot_count": int(
            construction["summary"]["history_snapshot_count"]
        ),
        "construction_stage_max_differential_shortening_mm": float(
            construction["summary"]["max_differential_shortening_mm"]
        ),
        "rail_tunnel_ready": bool(rail_tunnel["contract_pass"]),
        "rail_tunnel_serviceability_status": rail_tunnel["summary"]["serviceability_status"],
        "rail_tunnel_maintenance_priority": rail_tunnel["summary"]["maintenance_priority"],
        "rail_tunnel_recommended_action_count": int(
            rail_tunnel["summary"]["recommended_action_count"]
        ),
        "design_redesign_loop_ready": bool(design_redesign["contract_pass"]),
        "design_report_traceability_ratio": float(
            design_redesign["summary"]["design_report_traceability_ratio"]
        ),
        "design_report_ng_member_count": int(
            design_redesign["summary"]["design_report_ng_member_count"]
        ),
        "section_optimizer_suggestion_count": int(
            design_redesign["summary"]["section_optimizer_suggestion_count"]
        ),
        "section_optimizer_strengthen_count": int(
            design_redesign["summary"]["section_optimizer_strengthen_count"]
        ),
        "section_optimizer_reduce_count": int(
            design_redesign["summary"]["section_optimizer_reduce_count"]
        ),
        "governing_clause_count": int(design_redesign["summary"]["governing_clause_count"]),
    }
    summary_line = (
        "Commercial workflow breadth: "
        f"{'PASS' if all_pass else 'CHECK'} | "
        f"construction=yes(snapshots={summary['construction_stage_history_snapshot_count']},"
        f"shortening={summary['construction_stage_max_differential_shortening_mm']:.3f}mm) | "
        f"rail=yes(serviceability={summary['rail_tunnel_serviceability_status']},"
        f"maintenance={summary['rail_tunnel_maintenance_priority']},"
        f"actions={summary['rail_tunnel_recommended_action_count']}) | "
        f"redesign=yes(trace={summary['design_report_traceability_ratio'] * 100.0:.1f}%,"
        f"ng={summary['design_report_ng_member_count']},"
        f"suggestions={summary['section_optimizer_suggestion_count']},"
        f"strengthen={summary['section_optimizer_strengthen_count']},"
        f"reduce={summary['section_optimizer_reduce_count']},"
        f"clauses={summary['governing_clause_count']})"
    )
    return {
        "contract_pass": all_pass,
        "reason_code": "PASS" if all_pass else "CHECK",
        "summary_line": summary_line,
        "checks": {
            "pass": all_pass,
            "construction_stage_ready": bool(construction["contract_pass"]),
            "rail_tunnel_ready": bool(rail_tunnel["contract_pass"]),
            "design_redesign_loop_ready": bool(design_redesign["contract_pass"]),
        },
        "summary": summary,
        "rows": rows,
        "construction_stage": {
            "summary_line": construction["summary_line"],
            "summary": construction["summary"],
        },
        "rail_tunnel": {
            "summary_line": rail_tunnel["summary_line"],
            "summary": rail_tunnel["summary"],
        },
        "design_redesign_loop": {
            "summary_line": design_redesign["summary_line"],
            "summary": design_redesign["summary"],
        },
        "artifacts": {
            "construction_stage_breadth_report_json": str(construction_artifact),
            "rail_tunnel_breadth_report_json": str(rail_artifact),
            "design_report_book_json": str(design_report_json),
            "design_report_book_md": str(design_report_md),
            "section_optimizer_report_json": str(optimizer_json),
            "section_optimizer_report_csv": str(optimizer_csv),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--construction-sequence-gate-report",
        default=str(DEFAULT_CONSTRUCTION_SEQUENCE_GATE),
    )
    parser.add_argument("--component-dir", default=str(DEFAULT_COMPONENT_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    construction_sequence_gate_report = (
        json.loads(Path(args.construction_sequence_gate_report).read_text(encoding="utf-8"))
        if Path(args.construction_sequence_gate_report).exists()
        else {}
    )
    payload = build_commercial_workflow_breadth_report(
        construction_sequence_gate_report=construction_sequence_gate_report,
        component_dir=Path(args.component_dir),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(payload["summary_line"])
    print(f"Wrote commercial workflow breadth report: {out_path}")


if __name__ == "__main__":
    main()
