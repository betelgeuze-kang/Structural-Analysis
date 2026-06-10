#!/usr/bin/env python3
"""Build a load/stage runtime-flow receipt across solve, viewer, export, and audit surfaces."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "load-stage-runtime-flow-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
DEFAULT_MIDAS_INTEROP = REPO_ROOT / "implementation/phase1/release_evidence/midas/midas_interoperability_gate_report.json"
VIEWER_INDEX = REPO_ROOT / "src/structure-viewer/index.html"
VIEWER_PROVENANCE = REPO_ROOT / "src/structure-viewer/viewer-provenance-model.js"
VIEWER_LOCAL_OPS = REPO_ROOT / "src/structure-viewer/viewer-local-ops-state.js"
VIEWER_REPORT_EXPORT = REPO_ROOT / "src/structure-viewer/viewer-report-export.js"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _semantic_load_families(loads: dict[str, Any]) -> dict[str, Any]:
    static_cases = [row for row in (loads.get("static_load_cases") or []) if isinstance(row, dict)]
    case_types = sorted({str(row.get("type") or "").strip().upper() for row in static_cases if row.get("type")})
    summary = loads.get("semantic_load_summary") if isinstance(loads.get("semantic_load_summary"), dict) else {}
    return {
        "case_types": case_types,
        "case_names": [str(row.get("name") or "") for row in static_cases if row.get("name")],
        "has_dead": "D" in case_types,
        "has_live": "L" in case_types,
        "has_wind": "W" in case_types,
        "has_seismic": any(kind in case_types for kind in ("E", "EQ", "SEISMIC")),
        "nodal_load_row_count": len(loads.get("nodal_loads") or []),
        "pressure_load_row_count": len(loads.get("pressure_loads") or []),
        "selfweight_row_count": len(loads.get("selfweight") or []),
        "unbound_load_row_count": int(summary.get("unbound_nodal_load_row_count") or 0)
        + int(summary.get("unbound_selfweight_row_count") or 0)
        + int(summary.get("unbound_pressure_row_count") or 0),
        "body_load_pending_case_count": int(summary.get("body_load_pending_case_count") or 0),
        "surface_load_pending_case_count": int(summary.get("surface_load_pending_case_count") or 0),
    }


def _unsupported_hazard_queue(families: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    hazard_specs = [
        ("seismic_response_spectrum", families.get("has_seismic")),
        ("temperature_load", False),
        ("settlement_load", False),
        ("prestress_load", False),
    ]
    for hazard, present in hazard_specs:
        if present:
            continue
        queue.append(
            {
                "hazard_family": hazard,
                "status": "unsupported_or_no_source_rows",
                "reason": "No typed source rows are present in the current MGT lane; solver claim must stay blocked or engineer-reviewed.",
                "required_action_before_claim": "attach source rows, normalize typed entity, replay solve/export/audit evidence",
            }
        )
    return queue


def _viewer_contract() -> dict[str, Any]:
    index_text = _read(VIEWER_INDEX)
    provenance_text = _read(VIEWER_PROVENANCE)
    local_ops_text = _read(VIEWER_LOCAL_OPS)
    report_export_text = _read(VIEWER_REPORT_EXPORT)
    checks = {
        "shared_selection_load_case": "load_case" in index_text and "publishSharedSelection" in index_text,
        "stage_load_case_chip": "stage-load-case-chip" in index_text and "stageLoadCase" in provenance_text,
        "load_case_list": "load-case-list" in index_text and "buildLoadCaseListModel" in index_text,
        "audit_jsonl": "auditEventsJsonl" in local_ops_text and "appendViewerAuditEvent" in local_ops_text,
        "export_history": "appendViewerExportHistory" in local_ops_text and "report_exported" in index_text,
        "report_load_combo": "Load combo" in report_export_text and "solverReceipt?.load_combo" in report_export_text,
    }
    return {
        "status": "ready" if all(checks.values()) else "partial",
        "checks": checks,
        "source_files": [
            str(VIEWER_INDEX),
            str(VIEWER_PROVENANCE),
            str(VIEWER_LOCAL_OPS),
            str(VIEWER_REPORT_EXPORT),
        ],
    }


def _solver_evidence_contract(productization_dir: Path) -> dict[str, Any]:
    native_3d = _load(productization_dir / "mgt_global_fea_3d_native_solve.json")
    condensed = _load(productization_dir / "mgt_global_fea_condensed_solve.json")
    full_line = _load(productization_dir / "mgt_full_line_mesh_sparse_equilibrium.json")
    full_frame = _load(productization_dir / "mgt_full_frame_6dof_sparse_equilibrium.json")
    coupled_frame_shell = _load(productization_dir / "mgt_coupled_frame_shell_sparse_equilibrium.json")
    pdelta = _load(productization_dir / "mgt_pdelta_continuation_probe.json")

    native_3d_status = str(native_3d.get("native_solve_status") or native_3d.get("status") or "")
    condensed_status = str(condensed.get("native_solve_status") or condensed.get("status") or "")
    full_line_ready = bool(full_line.get("status") == "ready")
    full_frame_ready = bool(
        full_frame.get("status") == "ready"
        and full_frame.get("full_frame_6dof_sparse_elastic_equilibrium_ready")
        and full_frame.get("full_frame_6dof_linearized_geometric_equilibrium_ready")
    )
    frame_pdelta_ready = bool(
        (full_frame.get("deformed_state_pdelta_path") or {}).get("ready")
        or (pdelta.get("max_converged_load_scale") or 0.0) >= 0.5
    )
    coupled_frame_shell_ready = bool(
        coupled_frame_shell.get("status") == "ready"
        and coupled_frame_shell.get("coupled_frame_shell_sparse_equilibrium_ready")
    )
    current_sparse_global_solve_ready = bool(full_line_ready and full_frame_ready and coupled_frame_shell_ready)
    legacy_solve_ready = bool(
        native_3d_status
        in {"mesh_3d_beam_global_wired", "mesh_3d_beam_global_wired_with_licensed_fingerprint_bridge", "warn"}
        and condensed_status == "condensed_global_fea_wired"
    )
    ready = bool(legacy_solve_ready or (current_sparse_global_solve_ready and frame_pdelta_ready))
    return {
        "status": "ready" if ready else "partial",
        "ready": ready,
        "basis": (
            "legacy_native_and_condensed"
            if legacy_solve_ready
            else "current_full_sparse_line_frame_coupled_evidence"
            if ready
            else "insufficient_solver_evidence"
        ),
        "native_3d_status": native_3d_status,
        "condensed_status": condensed_status,
        "full_line_sparse_ready": full_line_ready,
        "full_frame_6dof_sparse_ready": full_frame_ready,
        "full_frame_6dof_pdelta_path_ready": frame_pdelta_ready,
        "coupled_frame_shell_sparse_ready": coupled_frame_shell_ready,
        "pdelta_continuation_status": pdelta.get("status"),
        "pdelta_max_converged_load_scale": pdelta.get("max_converged_load_scale"),
        "claim_boundary": (
            "Solve-flow readiness means typed load/load-combination/stage entities are wired to the current "
            "solver evidence lane with full sparse line, 6-DOF frame, and coupled frame-shell receipts. It "
            "does not claim full-load nonlinear convergence or hazard families with no source rows."
        ),
    }


def build_load_stage_runtime_flow_receipt(
    *,
    productization_dir: Path = PRODUCTIZATION,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    midas_interop_json: Path = DEFAULT_MIDAS_INTEROP,
    output_json: Path | None = None,
) -> dict[str, Any]:
    roundtrip = _load(roundtrip_json)
    model = roundtrip.get("model") if isinstance(roundtrip.get("model"), dict) else {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    load_stage = _load(productization_dir / "load_stage_semantics_contract.json")
    load_combo = _load(productization_dir / "load_combination_engine_gate.json")
    sync = _load(productization_dir / "mgt_roundtrip_sync.json")
    solver_evidence = _solver_evidence_contract(productization_dir)
    interop = _load(midas_interop_json)
    export_report_path = REPO_ROOT / str((interop.get("summary") or {}).get("export_report_path") or "")
    export_report = _load(export_report_path)

    families = _semantic_load_families(loads)
    unsupported_queue = _unsupported_hazard_queue(families)
    viewer = _viewer_contract()
    load_combo_summary = load_combo.get("summary") if isinstance(load_combo.get("summary"), dict) else {}
    interop_summary = interop.get("summary") if isinstance(interop.get("summary"), dict) else {}
    export_summary = export_report.get("summary") if isinstance(export_report.get("summary"), dict) else {}
    sync_status = str(sync.get("status") or "")

    typed_entities_ready = bool(
        load_stage.get("status") == "ready"
        and load_stage.get("typed_runtime_entities_ready")
        and load_stage.get("stage_semantics_ready")
        and load_combo.get("contract_pass")
        and families["has_dead"]
        and families["has_live"]
        and families["has_wind"]
        and families["unbound_load_row_count"] == 0
    )
    solve_flow_ready = bool(
        typed_entities_ready
        and sync_status in {"ready", "synced"}
        and solver_evidence.get("ready")
    )
    viewer_flow_ready = viewer.get("status") == "ready"
    export_flow_ready = bool(
        interop.get("contract_pass")
        and interop_summary.get("loadcomb_exact_roundtrip_pass")
        and float(interop_summary.get("roundtrip_exact_entry_row_coverage_min") or 0.0) >= 1.0
        and interop_summary.get("export_preview_roundtrip_verified")
    )
    audit_flow_ready = bool(
        (load_stage.get("audit_contract") or {}).get("roundtrip_exact_ready")
        and int(export_summary.get("audit_review_queue_item_count") or 0) >= 0
        and viewer_flow_ready
    )
    unsupported_queue_ready = all(
        row.get("reason") and row.get("required_action_before_claim") for row in unsupported_queue
    )
    ready = bool(
        typed_entities_ready
        and solve_flow_ready
        and viewer_flow_ready
        and export_flow_ready
        and audit_flow_ready
        and unsupported_queue_ready
    )
    blockers = [
        *(["typed_load_stage_entities_not_ready"] if not typed_entities_ready else []),
        *(["solve_flow_not_ready"] if not solve_flow_ready else []),
        *(["viewer_flow_not_ready"] if not viewer_flow_ready else []),
        *(["export_flow_not_ready"] if not export_flow_ready else []),
        *(["audit_flow_not_ready"] if not audit_flow_ready else []),
        *(["unsupported_hazard_queue_not_ready"] if not unsupported_queue_ready else []),
    ]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "partial",
        "typed_load_stage_flow_ready": typed_entities_ready,
        "solve_flow_ready": solve_flow_ready,
        "viewer_flow_ready": viewer_flow_ready,
        "export_flow_ready": export_flow_ready,
        "audit_flow_ready": audit_flow_ready,
        "unsupported_hazard_queue_ready": unsupported_queue_ready,
        "claim_boundary": (
            "Current lane proves typed D/L/W case inventory, D/L load-combination graph, staged-analysis "
            "semantics, viewer/export/audit propagation, and explicit unsupported queue for absent hazards; "
            "it is not a claim that every hazard family has source rows in the current MGT."
        ),
        "roundtrip_json": str(roundtrip_json),
        "summary": {
            "case_entity_count": (load_stage.get("summary") or {}).get("case_entity_count"),
            "combination_entity_count": (load_stage.get("summary") or {}).get("combination_entity_count"),
            "construction_stage_count": (load_stage.get("summary") or {}).get("construction_stage_count"),
            "runtime_combo_count_total": load_combo_summary.get("runtime_combo_count_total"),
            "runtime_max_nested_depth": load_combo_summary.get("runtime_max_nested_depth_global"),
            "loadcomb_exact_roundtrip_pass": interop_summary.get("loadcomb_exact_roundtrip_pass"),
            "roundtrip_exact_entry_row_coverage_min": interop_summary.get("roundtrip_exact_entry_row_coverage_min"),
            "native_3d_status": solver_evidence.get("native_3d_status"),
            "condensed_status": solver_evidence.get("condensed_status"),
            "solve_flow_basis": solver_evidence.get("basis"),
        },
        "load_family_inventory": families,
        "unsupported_hazard_queue": unsupported_queue,
        "flow_contract": {
            "solve": {
                "status": "ready" if solve_flow_ready else "partial",
                "mgt_roundtrip_sync_status": sync_status,
                "mgt_global_fea_3d_native_status": solver_evidence.get("native_3d_status"),
                "mgt_global_fea_condensed_status": solver_evidence.get("condensed_status"),
                "load_combination_contract_pass": bool(load_combo.get("contract_pass")),
                "solver_evidence": solver_evidence,
            },
            "viewer": viewer,
            "export": {
                "status": "ready" if export_flow_ready else "partial",
                "midas_interoperability_gate": str(midas_interop_json),
                "export_report": str(export_report_path),
                "summary_line": interop.get("summary_line"),
            },
            "audit": {
                "status": "ready" if audit_flow_ready else "partial",
                "load_stage_audit_contract": load_stage.get("audit_contract") or {},
                "export_audit_review_queue_item_count": export_summary.get("audit_review_queue_item_count"),
                "export_audit_review_resolution_closed_packet_count": export_summary.get(
                    "audit_review_resolution_closed_packet_count"
                ),
            },
        },
        "blockers": blockers,
    }
    out = output_json or productization_dir / "load_stage_runtime_flow_receipt.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--midas-interop-json", type=Path, default=DEFAULT_MIDAS_INTEROP)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "load_stage_runtime_flow_receipt.json")
    args = parser.parse_args()
    payload = build_load_stage_runtime_flow_receipt(
        productization_dir=args.productization_dir,
        roundtrip_json=args.roundtrip_json,
        midas_interop_json=args.midas_interop_json,
        output_json=args.output_json,
    )
    print(
        "load-stage-runtime-flow: "
        f"status={payload['status']} solve={payload['solve_flow_ready']} "
        f"viewer={payload['viewer_flow_ready']} export={payload['export_flow_ready']} "
        f"audit={payload['audit_flow_ready']} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
