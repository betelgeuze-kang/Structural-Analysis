#!/usr/bin/env python3
"""Aggregate bounded-subset/export/interoperability evidence into one contract report."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "MIDAS interoperability/export readiness is satisfied for the current bounded subset",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_EVIDENCE_MISSING": "one or more required MIDAS interoperability artifacts are missing",
    "ERR_EXPORT_FIDELITY_FAIL": "export preview or LOADCOMB round-trip fidelity failed",
    "ERR_INTEROPERABILITY_FAIL": "one or more interoperability readiness checks failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["model_jsons", "export_report", "loadcomb_roundtrip_reports", "loadcomb_preview_files", "out"],
    "properties": {
        "model_jsons": {"type": "string", "minLength": 1},
        "export_report": {"type": "string", "minLength": 1},
        "loadcomb_roundtrip_reports": {"type": "string", "minLength": 1},
        "loadcomb_preview_files": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}

DEFAULT_MODEL_JSONS = (
    "implementation/phase1/open_data/midas/midas_generator_33.json,"
    "implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json,"
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
)

DEFAULT_EXPORT_REPORT = "implementation/phase1/open_data/midas/midas_generator_33.optimized.export_report.json"

DEFAULT_LOADCOMB_ROUNDTRIP_REPORTS = (
    "implementation/phase1/release/midas_generator_33_loadcomb_roundtrip_report.json,"
    "implementation/phase1/release/midas_generator_33_pr_recheck_loadcomb_roundtrip_report.json,"
    "implementation/phase1/release/midas_generator_33_optimized_roundtrip_loadcomb_roundtrip_report.json"
)

DEFAULT_LOADCOMB_PREVIEW_FILES = (
    "implementation/phase1/release/midas_generator_33_loadcomb_preview.mgt,"
    "implementation/phase1/release/midas_generator_33_pr_recheck_loadcomb_preview.mgt,"
    "implementation/phase1/release/midas_generator_33_optimized_roundtrip_loadcomb_preview.mgt"
)


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_row(path: Path) -> dict[str, Any]:
    row = {
        "path": str(path),
        "exists": bool(path.exists()),
        "sha256": "",
        "size_bytes": 0,
    }
    if path.exists():
        row["size_bytes"] = int(path.stat().st_size)
        row["sha256"] = _sha256(path)
    return row


def _has_minimal_structured_loads_contract(model: dict[str, Any]) -> bool:
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    if not loads:
        return False

    structured_list_keys = (
        "static_load_cases",
        "load_cases",
        "load_combinations",
        "nodal_loads",
        "pressure_loads",
        "selfweight",
        "active_static_case_sequence",
    )
    for key in structured_list_keys:
        rows = loads.get(key)
        if isinstance(rows, list) and any(
            isinstance(item, dict) and bool(item) for item in rows
        ):
            return True

    graph = loads.get("load_combination_graph")
    if isinstance(graph, dict) and bool(graph):
        return True

    semantic_summary = loads.get("semantic_load_summary")
    if isinstance(semantic_summary, dict) and bool(semantic_summary):
        return True

    return False


def _load_model_evidence(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    recovery = metadata.get("load_contract_recovery") if isinstance(metadata.get("load_contract_recovery"), dict) else {}
    seed = metadata.get("load_combination_editor_seed") if isinstance(metadata.get("load_combination_editor_seed"), dict) else {}
    pattern = metadata.get("load_pattern_library") if isinstance(metadata.get("load_pattern_library"), dict) else {}
    bridge = metadata.get("kds_geometry_bridge") if isinstance(metadata.get("kds_geometry_bridge"), dict) else {}

    seed_summary = seed.get("summary") if isinstance(seed.get("summary"), dict) else {}
    pattern_summary = pattern.get("summary") if isinstance(pattern.get("summary"), dict) else {}
    bridge_summary = bridge.get("summary") if isinstance(bridge.get("summary"), dict) else {}
    seed_limitations = seed.get("limitations") if isinstance(seed.get("limitations"), list) else []
    pattern_limitations = pattern.get("limitations") if isinstance(pattern.get("limitations"), list) else []
    seed_kind = str(seed.get("seed_kind", "") or "")
    provenance = str(seed.get("provenance", "") or "")
    pattern_provenance = str(pattern.get("provenance", "") or "")

    return {
        "path": str(path),
        "exists": bool(path.exists()),
        "sha256": _sha256(path) if path.exists() else "",
        "recovery_mode": str(recovery.get("mode", "") or ""),
        "recovery_case_count": int(recovery.get("case_count", 0) or 0),
        "recovery_combination_count": int(recovery.get("combination_count", 0) or 0),
        "structured_loads_contract_present": _has_minimal_structured_loads_contract(model),
        "seed_present": bool(seed),
        "seed_kind": seed_kind,
        "seed_provenance": provenance,
        "seed_case_count": int(seed_summary.get("case_count", 0) or 0),
        "seed_combo_count": int(seed_summary.get("combination_count", 0) or 0),
        "seed_graph_edge_count": int(seed_summary.get("graph_edge_count", 0) or 0),
        "seed_limitations": [str(item) for item in seed_limitations if str(item).strip()],
        "pattern_present": bool(pattern),
        "pattern_provenance": pattern_provenance,
        "pattern_count": int(pattern_summary.get("pattern_count", 0) or 0),
        "pattern_primitive_count": int(pattern_summary.get("primitive_count", 0) or 0),
        "pattern_limitations": [str(item) for item in pattern_limitations if str(item).strip()],
        "bridge_present": bool(bridge),
        "bridge_provenance": str(bridge.get("provenance", "") or ""),
        "bridge_registry_source_label": str(bridge.get("registry_source_label", "") or ""),
        "bridge_exact_review_id_count": int(bridge_summary.get("exact_mapped_review_id_count", 0) or 0),
        "bridge_heuristic_review_id_count": int(bridge_summary.get("heuristic_mapped_review_id_count", 0) or 0),
        "bridge_exact_row_provenance_count": int(bridge_summary.get("exact_mapped_row_provenance_count", 0) or 0),
        "bridge_heuristic_row_provenance_count": int(bridge_summary.get("heuristic_mapped_row_provenance_count", 0) or 0),
    }


def _extract_limit_labels(
    model_rows: list[dict[str, Any]],
    *,
    exact_name_coverage_pass: bool,
    exact_entry_row_coverage_pass: bool,
    exact_header_coverage_pass: bool,
    exact_factor_map_coverage_pass: bool,
    exact_expression_coverage_pass: bool,
    export_preview_roundtrip_verified: bool,
) -> list[str]:
    labels: list[str] = []

    def _add(label: str) -> None:
        label = str(label).strip()
        if label and label not in labels:
            labels.append(label)

    exact_roundtrip_contract_proven = bool(
        export_preview_roundtrip_verified
        and exact_name_coverage_pass
        and exact_entry_row_coverage_pass
        and exact_header_coverage_pass
        and exact_factor_map_coverage_pass
    )

    for row in model_rows:
        recovery_mode = str(row.get("recovery_mode", "") or "")
        if recovery_mode == "combination_only_raw_recovery" and bool(row.get("raw_recovery_pending", False)):
            _add("primitive_load_cards_pending")

        for text in row.get("seed_limitations", []) + row.get("pattern_limitations", []):
            s = str(text).strip().lower()
            if not s:
                continue
            if (
                ("normalized references" in s or "normalized reference" in s)
                and not exact_factor_map_coverage_pass
            ):
                _add("normalized_factor_maps_pending")
            if (
                ("not final solver-ready" in s or "not final solver side" in s or "not final solver-side" in s)
                and not exact_roundtrip_contract_proven
            ):
                _add("solver_ready_reconstruction_pending")
            if ("summary-grade" in s or "summary grade" in s) and not exact_expression_coverage_pass:
                _add("summary_grade_preview_only")
            if "load primitives are unavailable" in s and bool(row.get("raw_recovery_pending", False)):
                _add("primitive_load_cards_pending")

    return labels


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="midas_interoperability_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def build_interoperability_report(
    *,
    model_jsons: list[Path],
    export_report_path: Path,
    roundtrip_report_paths: list[Path],
    preview_files: list[Path],
    source_args: dict[str, Any],
) -> dict[str, Any]:
    model_rows = [_load_model_evidence(path) for path in model_jsons]
    export_report = _load_json(export_report_path)
    roundtrip_reports = [_load_json(path) for path in roundtrip_report_paths]

    model_exists_pass = all(row["exists"] for row in model_rows)
    seed_present_pass = all(row["seed_present"] for row in model_rows)
    pattern_present_pass = all(row["pattern_present"] for row in model_rows)

    export_summary = export_report.get("summary") if isinstance(export_report.get("summary"), dict) else {}
    export_contract_pass = bool(export_report.get("contract_pass", False))
    loadcomb_preview_exists = bool(export_summary.get("loadcomb_preview_exists", False))
    loadcomb_roundtrip_pass = bool(export_summary.get("loadcomb_roundtrip_pass", False))
    export_report_pass = bool(export_contract_pass and loadcomb_preview_exists and loadcomb_roundtrip_pass)

    preview_rows = [_artifact_row(path) for path in preview_files]
    preview_present_count = sum(1 for row in preview_rows if row["exists"] and int(row["size_bytes"]) > 0)
    preview_files_pass = bool(preview_rows) and preview_present_count == len(preview_rows)

    roundtrip_rows: list[dict[str, Any]] = []
    for path, payload in zip(roundtrip_report_paths, roundtrip_reports):
        roundtrip_rows.append(
            {
                "path": str(path),
                "exists": bool(path.exists()),
                "pass": bool(payload.get("pass", False)),
                "exact_name_coverage": float(payload.get("exact_name_coverage", 0.0) or 0.0),
                "exact_entry_row_coverage": float(payload.get("exact_entry_row_coverage", 0.0) or 0.0),
                "exact_header_coverage": float(payload.get("exact_header_coverage", 0.0) or 0.0),
                "exact_factor_map_coverage": float(payload.get("exact_factor_map_coverage", 0.0) or 0.0),
                "exact_expression_coverage": float(payload.get("exact_expression_coverage", 0.0) or 0.0),
                "raw_combo_count": int(payload.get("raw_combo_count", 0) or 0),
                "export_combo_count": int(payload.get("export_combo_count", 0) or 0),
                "recovery_mode": str(payload.get("recovery_mode", "") or ""),
                "source_model_json": str(payload.get("source_model_json", "") or ""),
            }
        )

    roundtrip_reports_pass = bool(roundtrip_rows) and all(
        row["pass"]
        and row["exact_entry_row_coverage"] >= 1.0
        and row["exact_header_coverage"] >= 1.0
        and row["exact_factor_map_coverage"] >= 1.0
        for row in roundtrip_rows
    )
    roundtrip_pass_count = sum(
        1
        for row in roundtrip_rows
        if row["pass"]
        and row["exact_entry_row_coverage"] >= 1.0
        and row["exact_header_coverage"] >= 1.0
        and row["exact_factor_map_coverage"] >= 1.0
    )

    exact_name_coverage_pass = bool(roundtrip_rows) and all(row["exact_name_coverage"] >= 1.0 for row in roundtrip_rows)
    exact_entry_row_coverage_pass = bool(roundtrip_rows) and all(
        row["exact_entry_row_coverage"] >= 1.0 for row in roundtrip_rows
    )
    exact_header_coverage_pass = bool(roundtrip_rows) and all(
        row["exact_header_coverage"] >= 1.0 for row in roundtrip_rows
    )
    exact_factor_map_coverage_pass = bool(roundtrip_rows) and all(
        row["exact_factor_map_coverage"] >= 1.0 for row in roundtrip_rows
    )
    exact_expression_coverage_pass = bool(roundtrip_rows) and all(
        row["exact_expression_coverage"] >= 1.0 for row in roundtrip_rows
    )
    roundtrip_exact_contract_by_source_model = {
        str(row.get("source_model_json", "") or ""): bool(
            row["pass"]
            and row["exact_name_coverage"] >= 1.0
            and row["exact_entry_row_coverage"] >= 1.0
            and row["exact_header_coverage"] >= 1.0
            and row["exact_factor_map_coverage"] >= 1.0
        )
        for row in roundtrip_rows
        if str(row.get("source_model_json", "") or "").strip()
    }
    for row in model_rows:
        row["raw_recovery_pending"] = bool(
            row.get("recovery_mode") == "combination_only_raw_recovery"
            and not (
                bool(row.get("structured_loads_contract_present", False))
                and bool(roundtrip_exact_contract_by_source_model.get(str(row.get("path", "") or ""), False))
            )
        )

    checks = {
        "model_artifacts_present_pass": bool(model_exists_pass),
        "editor_seed_present_pass": bool(seed_present_pass),
        "load_pattern_library_present_pass": bool(pattern_present_pass),
        "export_report_pass": bool(export_report_pass),
        "loadcomb_preview_files_pass": bool(preview_files_pass),
        "loadcomb_roundtrip_reports_pass": bool(roundtrip_reports_pass),
    }

    remaining_limits = _extract_limit_labels(
        model_rows,
        exact_name_coverage_pass=exact_name_coverage_pass,
        exact_entry_row_coverage_pass=exact_entry_row_coverage_pass,
        exact_header_coverage_pass=exact_header_coverage_pass,
        exact_factor_map_coverage_pass=exact_factor_map_coverage_pass,
        exact_expression_coverage_pass=exact_expression_coverage_pass,
        export_preview_roundtrip_verified=bool(export_report_pass and preview_files_pass),
    )
    heuristic_recovery_model_count = sum(1 for row in model_rows if bool(row.get("raw_recovery_pending", False)))
    heuristic_geometry_bridge_model_count = sum(
        1
        for row in model_rows
        if int(row.get("bridge_heuristic_review_id_count", 0) or 0) > 0
        or int(row.get("bridge_heuristic_row_provenance_count", 0) or 0) > 0
    )
    heuristic_labels: list[str] = []
    if heuristic_recovery_model_count:
        heuristic_labels.append("heuristic_raw_loadcomb_recovery")
    if heuristic_geometry_bridge_model_count:
        heuristic_labels.append("heuristic_kds_geometry_bridge")
    exact_roundtrip_closure_blockers = [*heuristic_labels, *remaining_limits]
    exact_roundtrip_closure_pass = bool(
        model_exists_pass
        and seed_present_pass
        and pattern_present_pass
        and export_report_pass
        and preview_files_pass
        and roundtrip_reports_pass
        and exact_name_coverage_pass
        and not exact_roundtrip_closure_blockers
    )
    if exact_roundtrip_closure_pass:
        bounded_subset_mode = "full_exact_roundtrip"
    else:
        bounded_subset_parts = ["editor_seed"]
        if heuristic_recovery_model_count:
            bounded_subset_parts.append("raw_recovery")
        if heuristic_geometry_bridge_model_count:
            bounded_subset_parts.append("heuristic_geometry_bridge")
        bounded_subset_parts.append("preview_roundtrip")
        bounded_subset_mode = "+".join(bounded_subset_parts)
    if exact_roundtrip_closure_pass:
        exact_roundtrip_closure_status = "closed"
    elif not model_exists_pass or not seed_present_pass or not pattern_present_pass or not preview_files_pass:
        exact_roundtrip_closure_status = "evidence_missing"
    elif not export_report_pass or not roundtrip_reports_pass or not exact_name_coverage_pass:
        exact_roundtrip_closure_status = "fidelity_gap"
    else:
        exact_roundtrip_closure_status = "bounded_subset_pending"

    summary = {
        "model_count": len(model_rows),
        "model_artifact_count": len(model_rows),
        "model_paths": [row["path"] for row in model_rows],
        "model_sha256": {Path(row["path"]).name: row["sha256"] for row in model_rows},
        "recovery_mode_counts": dict(sorted(Counter(row["recovery_mode"] or "embedded_metadata" for row in model_rows).items())),
        "heuristic_raw_recovery_model_count": heuristic_recovery_model_count,
        "structured_loads_contract_present_count": sum(
            1 for row in model_rows if bool(row.get("structured_loads_contract_present", False))
        ),
        "seed_kind_counts": dict(sorted(Counter(row["seed_kind"] or "unknown" for row in model_rows).items())),
        "pattern_provenance_counts": dict(sorted(Counter(row["pattern_provenance"] or "unknown" for row in model_rows).items())),
        "seed_present_count": sum(1 for row in model_rows if row["seed_present"]),
        "pattern_present_count": sum(1 for row in model_rows if row["pattern_present"]),
        "kds_geometry_bridge_present_count": sum(1 for row in model_rows if row["bridge_present"]),
        "kds_geometry_bridge_provenance_counts": dict(
            sorted(Counter(row["bridge_provenance"] or "unknown" for row in model_rows).items())
        ),
        "kds_geometry_bridge_registry_source_counts": dict(
            sorted(Counter(row["bridge_registry_source_label"] or "unknown" for row in model_rows).items())
        ),
        "kds_geometry_bridge_exact_review_id_total": sum(
            int(row["bridge_exact_review_id_count"] or 0) for row in model_rows
        ),
        "kds_geometry_bridge_heuristic_review_id_total": sum(
            int(row["bridge_heuristic_review_id_count"] or 0) for row in model_rows
        ),
        "kds_geometry_bridge_exact_row_provenance_total": sum(
            int(row["bridge_exact_row_provenance_count"] or 0) for row in model_rows
        ),
        "kds_geometry_bridge_heuristic_row_provenance_total": sum(
            int(row["bridge_heuristic_row_provenance_count"] or 0) for row in model_rows
        ),
        "heuristic_kds_geometry_bridge_model_count": heuristic_geometry_bridge_model_count,
        "seed_case_count_by_model": {Path(row["path"]).name: row["seed_case_count"] for row in model_rows},
        "seed_combo_count_by_model": {Path(row["path"]).name: row["seed_combo_count"] for row in model_rows},
        "pattern_count_by_model": {Path(row["path"]).name: row["pattern_count"] for row in model_rows},
        "pattern_primitive_count_by_model": {Path(row["path"]).name: row["pattern_primitive_count"] for row in model_rows},
        "export_report_path": str(export_report_path),
        "export_report_summary_line": str(export_summary.get("loadcomb_roundtrip_summary_line", "") or ""),
        "export_delivery_boundary": str(export_summary.get("mgt_export_delivery_boundary", "") or ""),
        "export_preview_roundtrip_verified": bool(export_summary.get("loadcomb_preview_exists", False))
        and bool(export_summary.get("loadcomb_roundtrip_pass", False)),
        "group_local_connection_detailing_payload_available_count": int(export_summary.get("group_local_connection_detailing_payload_available_count", 0) or 0),
        "group_local_detailing_payload_available_count": int(export_summary.get("group_local_detailing_payload_available_count", 0) or 0),
        "group_local_rebar_payload_available_count": int(export_summary.get("group_local_rebar_payload_available_count", 0) or 0),
        "loadcomb_combo_count": int(export_summary.get("loadcomb_combo_count", 0) or 0),
        "loadcomb_preview_exists": bool(loadcomb_preview_exists),
        "loadcomb_roundtrip_pass": bool(loadcomb_roundtrip_pass),
        "loadcomb_roundtrip_report_exists": bool(export_summary.get("loadcomb_roundtrip_report_exists", False)),
        "preview_file_count": len(preview_rows),
        "preview_file_present_count": preview_present_count,
        "preview_file_rows": preview_rows,
        "roundtrip_report_count": len(roundtrip_rows),
        "roundtrip_report_pass_count": roundtrip_pass_count,
        "roundtrip_reports": roundtrip_rows,
        "roundtrip_exact_name_coverage_min": min((row["exact_name_coverage"] for row in roundtrip_rows), default=0.0),
        "roundtrip_exact_entry_row_coverage_min": min((row["exact_entry_row_coverage"] for row in roundtrip_rows), default=0.0),
        "roundtrip_exact_header_coverage_min": min((row["exact_header_coverage"] for row in roundtrip_rows), default=0.0),
        "roundtrip_exact_factor_map_coverage_min": min((row["exact_factor_map_coverage"] for row in roundtrip_rows), default=0.0),
        "roundtrip_exact_expression_coverage_min": min((row["exact_expression_coverage"] for row in roundtrip_rows), default=0.0),
        "loadcomb_exact_roundtrip_pass": bool(roundtrip_reports_pass and exact_name_coverage_pass),
        "roundtrip_recovery_modes": dict(sorted(Counter(row["recovery_mode"] or "embedded_metadata" for row in roundtrip_rows).items())),
        "roundtrip_source_model_jsons": [row["source_model_json"] for row in roundtrip_rows],
        "bounded_subset_mode": bounded_subset_mode,
        "remaining_limits": remaining_limits,
        "exact_roundtrip_closure_pass": exact_roundtrip_closure_pass,
        "exact_roundtrip_closure_status": exact_roundtrip_closure_status,
        "exact_roundtrip_closure_blockers": exact_roundtrip_closure_blockers,
        "evidence_notes": [
            "LOADCOMB preview files are bounded authoring exports, not a full commercial editor round-trip.",
            "Exact entry-row coverage is the primary fidelity signal for the current interoperability subset.",
        ],
    }

    summary_line = (
        "MIDAS interoperability/export readiness: "
        f"{'PASS' if all(checks.values()) else 'CHECK'} | "
        f"seeds={summary['seed_present_count']}/{summary['model_count']} | "
        f"patterns={summary['pattern_present_count']}/{summary['model_count']} | "
        f"preview={summary['preview_file_present_count']}/{summary['preview_file_count']} | "
        f"roundtrip={summary['roundtrip_report_pass_count']}/{summary['roundtrip_report_count']} "
        f"exact_entry_row_min={summary['roundtrip_exact_entry_row_coverage_min']:.2f} "
        f"| bounded_subset={summary['bounded_subset_mode']} | "
        f"limits={', '.join(summary['remaining_limits']) if summary['remaining_limits'] else 'none'} | "
        f"exact_closure={summary['exact_roundtrip_closure_status']}"
    )

    contract_pass = bool(all(checks.values()))
    if not model_exists_pass:
        reason_code = "ERR_EVIDENCE_MISSING"
    elif not export_report_pass or not roundtrip_reports_pass:
        reason_code = "ERR_EXPORT_FIDELITY_FAIL"
    elif not seed_present_pass or not pattern_present_pass or not preview_files_pass:
        reason_code = "ERR_INTEROPERABILITY_FAIL"
    else:
        reason_code = "PASS"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-midas-interoperability-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": source_args,
        "checks": checks,
        "summary": summary,
        "summary_line": summary_line,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "artifacts": {
            "model_jsons": [str(path) for path in model_jsons],
            "export_report": str(export_report_path),
            "loadcomb_roundtrip_reports": [str(path) for path in roundtrip_report_paths],
            "loadcomb_preview_files": [str(path) for path in preview_files],
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-jsons", default=DEFAULT_MODEL_JSONS)
    parser.add_argument("--export-report", default=DEFAULT_EXPORT_REPORT)
    parser.add_argument("--loadcomb-roundtrip-reports", default=DEFAULT_LOADCOMB_ROUNDTRIP_REPORTS)
    parser.add_argument("--loadcomb-preview-files", default=DEFAULT_LOADCOMB_PREVIEW_FILES)
    parser.add_argument("--out", default="implementation/phase1/midas_interoperability_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "model_jsons": str(args.model_jsons),
        "export_report": str(args.export_report),
        "loadcomb_roundtrip_reports": str(args.loadcomb_roundtrip_reports),
        "loadcomb_preview_files": str(args.loadcomb_preview_files),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_midas_interoperability_gate")
        model_jsons = [Path(item) for item in _parse_csv(args.model_jsons)]
        roundtrip_reports = [Path(item) for item in _parse_csv(args.loadcomb_roundtrip_reports)]
        preview_files = [Path(item) for item in _parse_csv(args.loadcomb_preview_files)]
        export_report_path = Path(args.export_report)
        if not model_jsons or not roundtrip_reports or not preview_files:
            raise ValueError("one or more evidence lists are empty")

        payload = build_interoperability_report(
            model_jsons=model_jsons,
            export_report_path=export_report_path,
            roundtrip_report_paths=roundtrip_reports,
            preview_files=preview_files,
            source_args=input_payload,
        )
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        archive_manifest = _archive(
            [
                str(out),
                *[str(path) for path in model_jsons],
                str(export_report_path),
                *[str(path) for path in roundtrip_reports],
                *[str(path) for path in preview_files],
            ]
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote MIDAS interoperability gate report: {out}")
        print(payload["summary_line"])
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-midas-interoperability-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote MIDAS interoperability gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
