#!/usr/bin/env python3
"""Build an optimization intake queue from the private real-drawing corpus metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_REDACTED_MANIFEST = Path("tmp/real_drawing_private_corpus/redacted_manifest.json")
DEFAULT_MGT_PARSE_REPORT_DIR = Path("tmp/real_drawing_private_corpus/mgt_parse")
DEFAULT_IFC_ADAPTER_REPORT_DIR = Path("tmp/real_drawing_private_corpus/ifc_adapter")
DEFAULT_MIDAS_ARCHIVE_ADAPTER_REPORT = Path(
    "tmp/real_drawing_private_corpus/midas_archive_adapter/midas_archive_adapter_report.json"
)
DEFAULT_MIDAS_NATIVE_WRITEBACK_DIFF_RECEIPTS_REPORT = Path(
    "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json"
)
DEFAULT_OUT = Path("tmp/real_drawing_private_corpus/model_optimization_intake_queue.json")
QUEUE_SCHEMA_VERSION = "real-drawing-model-optimization-intake-queue.v1"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mgt_parse_report_candidates(parse_report_dir: Path, *, file_id: str, file_name: str) -> list[Path]:
    stem = Path(file_name).stem
    candidates = [
        parse_report_dir / f"{stem}.report.json",
        parse_report_dir / f"{file_id}.report.json",
    ]
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _load_mgt_parse_report(parse_report_dir: Path, *, file_id: str, file_name: str) -> tuple[Path | None, dict[str, Any]]:
    for candidate in _mgt_parse_report_candidates(parse_report_dir, file_id=file_id, file_name=file_name):
        if candidate.exists():
            return candidate, _load_json(candidate)
    return None, {}


def _ifc_adapter_report_candidates(adapter_report_dir: Path, *, file_id: str, file_name: str) -> list[Path]:
    stem = Path(file_name).stem
    candidates = [
        adapter_report_dir / f"{file_id}.report.json",
        adapter_report_dir / f"{stem}.report.json",
    ]
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _load_ifc_adapter_report(
    adapter_report_dir: Path,
    *,
    file_id: str,
    file_name: str,
) -> tuple[Path | None, dict[str, Any]]:
    for candidate in _ifc_adapter_report_candidates(adapter_report_dir, file_id=file_id, file_name=file_name):
        if candidate.exists():
            return candidate, _load_json(candidate)
    return None, {}


def _archive_adapter_report_rows(report_path: Path) -> dict[str, dict[str, Any]]:
    if not report_path.exists():
        return {}
    payload = _load_json(report_path)
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("archives", []):
        if not isinstance(row, dict):
            continue
        file_id = str(row.get("file_id", "") or "")
        if file_id:
            rows[file_id] = row
    return rows


def _native_writeback_receipt_rows(report_path: Path) -> dict[str, dict[str, Any]]:
    if not report_path.exists():
        return {}
    payload = _load_json(report_path)
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("receipt_rows", []):
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id", "") or "")
        suffix = "__decoded_preview_native__identity_writeback"
        if not case_id.endswith(suffix):
            continue
        file_id = case_id[: -len(suffix)]
        if file_id:
            rows[file_id] = row
    return rows


def _path_exists(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and Path(text).exists()


def _mgt_hard_tier_decision(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    node_count = int(metrics.get("node_count", 0) or 0)
    element_count = int(metrics.get("element_count", 0) or 0)
    json_out = str(artifacts.get("json_out", "") or "")
    npz_out = str(artifacts.get("npz_out", "") or "")
    unbound_load_rows = (
        int(metrics.get("unbound_nodal_load_row_count", 0) or 0)
        + int(metrics.get("unbound_selfweight_row_count", 0) or 0)
        + int(metrics.get("unbound_pressure_row_count", 0) or 0)
    )
    if node_count <= 0 or element_count <= 0:
        return {
            "solver_exact": False,
            "mgt_hard_tier_ready": False,
            "mgt_hard_tier_reason_code": "ERR_MGT_SOLVER_GRAPH_EMPTY",
            "mgt_hard_tier_note": "Direct MGT parser passed, but node/element counts are empty.",
        }
    if not _path_exists(json_out) or not _path_exists(npz_out):
        return {
            "solver_exact": False,
            "mgt_hard_tier_ready": False,
            "mgt_hard_tier_reason_code": "ERR_MGT_SOLVER_ARTIFACTS_MISSING",
            "mgt_hard_tier_note": "Direct MGT parser passed, but JSON/NPZ solver artifacts are missing.",
        }
    if unbound_load_rows != 0:
        return {
            "solver_exact": False,
            "mgt_hard_tier_ready": False,
            "mgt_hard_tier_reason_code": "ERR_MGT_LOAD_BINDINGS_UNRESOLVED",
            "mgt_hard_tier_note": "Direct MGT parser passed, but one or more load rows are not bound to graph entities.",
        }
    return {
        "solver_exact": True,
        "mgt_hard_tier_ready": True,
        "mgt_hard_tier_reason_code": "PASS_MGT_DIRECT_SOLVER_GRAPH_EXACT",
        "mgt_hard_tier_note": "Direct MGT parser produced solver graph JSON/NPZ artifacts with nonempty topology and bound load rows.",
    }


def _mgt_hard_evidence(report_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    source_provenance = (
        report.get("source_provenance") if isinstance(report.get("source_provenance"), dict) else {}
    )
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    return {
        "hard_evidence_tier": "direct_native_mgt_parser",
        "hard_evidence_basis": "native MIDAS MGT parser contract_pass with direct node/element/load extraction.",
        "hard_evidence_report": str(report_path),
        "hard_evidence_provenance": {
            "source_family": str(source_provenance.get("source_family", "midas_mgt") or "midas_mgt"),
            "source_sha256": str(source_provenance.get("sha256", "") or ""),
            "source_size_bytes": int(source_provenance.get("size_bytes", 0) or 0),
            "parser_schema_version": str(report.get("schema_version", "") or ""),
            "parser_reason_code": str(report.get("reason_code", "") or ""),
        },
        "hard_evidence_artifacts": {
            "model_json": str(artifacts.get("json_out", "") or ""),
            "dataset_npz": str(artifacts.get("npz_out", "") or ""),
            "edge_list_json": str(artifacts.get("edge_list_out", "") or ""),
        },
        "hard_evidence_checks": {
            "contract_pass": bool(report.get("contract_pass", False)),
            "node_count": int(metrics.get("node_count", 0) or 0),
            "element_count": int(metrics.get("element_count", 0) or 0),
            "element_rows_skipped": int(metrics.get("element_rows_skipped", 0) or 0),
            "unbound_load_row_count": (
                int(metrics.get("unbound_nodal_load_row_count", 0) or 0)
                + int(metrics.get("unbound_selfweight_row_count", 0) or 0)
                + int(metrics.get("unbound_pressure_row_count", 0) or 0)
            ),
        },
    }


def _archive_hard_tier_decision(archive_report: dict[str, Any]) -> dict[str, Any]:
    exactness_tier = str(archive_report.get("preview_exactness_tier", "") or "")
    exact_promoted = bool(archive_report.get("exact_topology_promoted", False)) or exactness_tier == "exact-topology-promoted"
    exact_candidate = bool(archive_report.get("exact_topology_candidate", False)) or exactness_tier == "exact-topology-candidate"
    node_count = int(archive_report.get("node_count", 0) or 0)
    element_count = int(archive_report.get("element_count", 0) or 0)
    topology_node_count = int(archive_report.get("topology_node_count", 0) or 0)
    topology_edge_count = int(archive_report.get("topology_edge_count", 0) or 0)
    missing_member_path_count = int(archive_report.get("missing_member_path_count", 0) or 0)
    missing_member_reference_count = int(archive_report.get("missing_member_reference_count", 0) or 0)
    has_graph = node_count > 0 and element_count > 0
    has_topology_counts = topology_node_count > 0 and topology_edge_count > 0
    no_missing_refs = missing_member_path_count == 0 and missing_member_reference_count == 0
    graph_matches_topology_counts = node_count == topology_node_count and element_count == topology_edge_count

    if exact_promoted and has_graph and has_topology_counts and no_missing_refs and graph_matches_topology_counts:
        return {
            "archive_hard_tier_ready": True,
            "archive_hard_tier_reason_code": "PASS_ARCHIVE_EXACT_TOPOLOGY_PROMOTED",
            "archive_hard_tier_note": "Archive preview bridge carries promoted exact topology and satisfies solver graph count guards.",
        }
    if exact_promoted and not has_topology_counts:
        reason_code = "ERR_ARCHIVE_PROMOTED_TOPOLOGY_COUNTS_MISSING"
        note = "exact_topology_promoted is present, but topology node/edge counts are missing."
    elif exact_promoted and not no_missing_refs:
        reason_code = "ERR_ARCHIVE_PROMOTED_TOPOLOGY_REFERENCES_UNRESOLVED"
        note = "exact_topology_promoted is present, but member path/reference gaps remain."
    elif exact_promoted and not graph_matches_topology_counts:
        reason_code = "ERR_ARCHIVE_PROMOTED_TOPOLOGY_GRAPH_PARITY_MISMATCH"
        note = "exact_topology_promoted is present, but preview graph counts do not match recovered topology counts."
    elif exact_promoted:
        reason_code = "ERR_ARCHIVE_PROMOTED_GRAPH_EMPTY"
        note = "exact_topology_promoted is present, but the bridge graph has no nodes/elements."
    elif exact_candidate and has_graph and has_topology_counts and no_missing_refs and not graph_matches_topology_counts:
        reason_code = "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_GRAPH_PARITY_MISMATCH"
        note = (
            "Exact topology is candidate-only and preview graph counts do not match recovered topology counts; "
            "full structural preview materialization is required before hard solver graph promotion."
        )
    elif exact_candidate:
        reason_code = "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_NOT_PROMOTED"
        note = "Exact topology is candidate-only; it needs structural preview materialization before hard solver graph promotion."
    elif exactness_tier == "verified-geometry":
        reason_code = "ERR_ARCHIVE_VERIFIED_GEOMETRY_NOT_SOLVER_TOPOLOGY"
        note = "Verified geometry preview is viewer-ready, but it is not native solver topology."
    else:
        reason_code = "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT"
        note = "Decoded archive preview is intake-ready for triage, not solver-exact hard tier."
    return {
        "archive_hard_tier_ready": False,
        "archive_hard_tier_reason_code": reason_code,
        "archive_hard_tier_note": note,
    }


def _archive_native_writeback_hard_tier_decision(native_receipt: dict[str, Any]) -> dict[str, Any]:
    if not native_receipt:
        return {
            "archive_native_writeback_ready": False,
            "archive_native_writeback_reason_code": "ERR_ARCHIVE_NATIVE_WRITEBACK_RECEIPT_MISSING",
            "archive_native_writeback_note": "No decoded-preview native write-back receipt is available.",
        }
    taxonomy = native_receipt.get("taxonomy") if isinstance(native_receipt.get("taxonomy"), dict) else {}
    labels = {str(label) for label in (taxonomy.get("labels") or [])}
    checks = {
        "contract_pass": bool(native_receipt.get("contract_pass", False)),
        "topology_stability_pass": bool(native_receipt.get("topology_stability_pass", False)),
        "load_contract_stability_pass": bool(native_receipt.get("load_contract_stability_pass", False)),
        "loadcomb_exact_roundtrip_pass": bool(native_receipt.get("loadcomb_exact_roundtrip_pass", False)),
        "unknown_rows_zero_pass": bool(native_receipt.get("unknown_rows_zero_pass", False)),
        "review_pending_zero_pass": int(native_receipt.get("review_pending_count", 0) or 0) == 0,
        "preserved_exact_label_pass": "preserved_exact" in labels,
    }
    if all(checks.values()):
        return {
            "archive_native_writeback_ready": True,
            "archive_native_writeback_reason_code": "PASS_ARCHIVE_NATIVE_WRITEBACK_STABLE_DECODED_PREVIEW",
            "archive_native_writeback_note": (
                "Decoded archive preview has a native write-back receipt with stable topology/load contracts, "
                "exact load-combination round-trip, zero unknown rows, and no pending review."
            ),
            "archive_native_writeback_checks": checks,
        }
    failing = ",".join(key for key, passed in checks.items() if not passed)
    return {
        "archive_native_writeback_ready": False,
        "archive_native_writeback_reason_code": "ERR_ARCHIVE_NATIVE_WRITEBACK_RECEIPT_NOT_EXACT",
        "archive_native_writeback_note": f"Decoded-preview native write-back receipt is not sufficient: {failing}.",
        "archive_native_writeback_checks": checks,
    }


def _queue_row(
    *,
    project: dict[str, Any],
    file_row: dict[str, Any],
    parse_report_dir: Path,
    ifc_adapter_report_dir: Path,
    archive_adapter_rows: dict[str, dict[str, Any]],
    native_writeback_receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    project_id = str(project.get("project_id", "") or "")
    file_id = str(file_row.get("file_id", "") or "")
    file_name = str(file_row.get("file_name", "") or "")
    file_type = str(file_row.get("file_type", "") or "").lower()
    row: dict[str, Any] = {
        "project_id": project_id,
        "project_title": str(project.get("project_title", "") or ""),
        "source_family": str(project.get("source_family", "") or ""),
        "file_id": file_id,
        "file_name": file_name,
        "file_type": file_type,
        "role": str(file_row.get("role", "") or ""),
        "bytes": int(file_row.get("bytes", 0) or 0),
        "sha256": str(file_row.get("sha256", "") or ""),
        "source_url": str(file_row.get("source_url", "") or ""),
        "raw_redistribution_allowed": bool(file_row.get("raw_redistribution_allowed", False)),
        "release_surface_allowed": bool(file_row.get("release_surface_allowed", False)),
        "optimization_status": "adapter_required",
        "optimization_route": "manual_review",
        "ready_for_optimized_drawing_generation": False,
        "model_asset_count": 1,
    }

    if file_type == ".mgt":
        report_path, report = _load_mgt_parse_report(parse_report_dir, file_id=file_id, file_name=file_name)
        if report_path is not None:
            row["mgt_parse_report"] = str(report_path)
        if report.get("contract_pass") is True:
            metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
            artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
            hard_tier = _mgt_hard_tier_decision(report)
            row.update(
                {
                    "optimization_status": "solver_graph_ready",
                    "optimization_route": "midas_mgt_direct_parser",
                    "ready_for_optimized_drawing_generation": True,
                    "adapter_mode": "direct_mgt_parser",
                    "readiness_note": "Direct MIDAS MGT parser output is solver graph ready when exactness guards pass.",
                    "node_count": int(metrics.get("node_count", 0) or 0),
                    "element_count": int(metrics.get("element_count", 0) or 0),
                    "beam_element_count": int(metrics.get("beam_element_count", 0) or 0),
                    "shell_element_count": int(metrics.get("shell_element_count", 0) or 0),
                    "static_load_case_count": int(metrics.get("static_load_case_count", 0) or 0),
                    "load_combination_row_count": int(metrics.get("load_combination_row_count", 0) or 0),
                    "unbound_load_row_count": (
                        int(metrics.get("unbound_nodal_load_row_count", 0) or 0)
                        + int(metrics.get("unbound_selfweight_row_count", 0) or 0)
                        + int(metrics.get("unbound_pressure_row_count", 0) or 0)
                    ),
                    "solver_graph_model_json": str(artifacts.get("json_out", "") or ""),
                    "solver_graph_dataset_npz": str(artifacts.get("npz_out", "") or ""),
                    **_mgt_hard_evidence(report_path, report),
                    **hard_tier,
                }
            )
        elif report_path is not None:
            row["optimization_status"] = "parser_failed"
            row["optimization_route"] = "midas_mgt_parser_repair"
            row["parser_reason_code"] = str(report.get("reason_code", "") or "")
        else:
            row["optimization_status"] = "parser_pending"
            row["optimization_route"] = "midas_mgt_direct_parser"
    elif file_type == ".ifc":
        row["optimization_status"] = "ifc_adapter_required"
        row["optimization_route"] = "ifc_to_structural_graph_adapter"
        report_path, report = _load_ifc_adapter_report(
            ifc_adapter_report_dir,
            file_id=file_id,
            file_name=file_name,
        )
        if report_path is not None:
            row["ifc_adapter_report"] = str(report_path)
        if report.get("contract_pass") is True and report.get("adapter_mode") == "entity_proxy_graph":
            metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
            row.update(
                {
                    "optimization_status": "ifc_proxy_graph_ready",
                    "optimization_route": "ifc_to_structural_graph_adapter",
                    "ready_for_optimized_drawing_generation": True,
                    "adapter_mode": "entity_proxy_graph",
                    "solver_exact": False,
                    "readiness_note": (
                        "IFC entity proxy graph is intake-ready for optimization triage, not solver-exact native topology; "
                        "exact member geometry, material/section binding, load extraction, and solver connectivity remain adapter gaps."
                    ),
                    "proxy_node_count": int(metrics.get("proxy_node_count", 0) or 0),
                    "proxy_edge_count": int(metrics.get("proxy_edge_count", 0) or 0),
                    "structural_entity_count": int(metrics.get("structural_entity_count", 0) or 0),
                    "storey_count": int(metrics.get("storey_count", 0) or 0),
                }
            )
            graph_json = str(report.get("graph_json", "") or "")
            if graph_json:
                row["ifc_proxy_graph_json"] = graph_json
        elif report_path is not None:
            row["optimization_status"] = "ifc_adapter_failed"
            row["ifc_adapter_reason_code"] = str(report.get("reason_code", "") or "")
    elif file_type == ".zip":
        zip_model_member_count = int(file_row.get("zip_model_member_count", 0) or 0)
        row["zip_member_count"] = int(file_row.get("zip_member_count", 0) or 0)
        row["zip_model_member_count"] = zip_model_member_count
        row["model_asset_count"] = zip_model_member_count
        row["optimization_status"] = (
            "archive_adapter_required" if zip_model_member_count > 0 else "archive_no_model_members"
        )
        row["optimization_route"] = "midas_binary_archive_adapter"
        archive_report = archive_adapter_rows.get(file_id, {})
        native_receipt = native_writeback_receipts.get(file_id, {})
        if archive_report:
            row["archive_adapter_report"] = str(archive_report.get("bridge_report", "") or archive_report.get("adapter_report", "") or "")
        if archive_report.get("status") == "decoded_preview_bridge_ready":
            hard_tier = _archive_hard_tier_decision(archive_report)
            native_writeback_tier = _archive_native_writeback_hard_tier_decision(native_receipt)
            archive_ready = bool(hard_tier.get("archive_hard_tier_ready", False)) or bool(
                native_writeback_tier.get("archive_native_writeback_ready", False)
            )
            archive_hard_reason_code = (
                str(hard_tier.get("archive_hard_tier_reason_code") or "")
                if bool(hard_tier.get("archive_hard_tier_ready", False))
                else str(native_writeback_tier.get("archive_native_writeback_reason_code") or "")
                if archive_ready
                else str(hard_tier.get("archive_hard_tier_reason_code") or "")
            )
            archive_hard_note = (
                str(hard_tier.get("archive_hard_tier_note") or "")
                if bool(hard_tier.get("archive_hard_tier_ready", False))
                else str(native_writeback_tier.get("archive_native_writeback_note") or "")
                if archive_ready
                else str(hard_tier.get("archive_hard_tier_note") or "")
            )
            row.update(
                {
                    "optimization_status": (
                        "archive_solver_graph_ready" if archive_ready else "archive_decoded_preview_bridge_ready"
                    ),
                    "optimization_route": (
                        "midas_binary_archive_exact_topology_promoted"
                        if archive_ready
                        else "midas_binary_decoded_preview_bridge"
                    ),
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": archive_ready,
                    "adapter_mode": "decoded_preview_bridge",
                    "readiness_note": (
                        "MIDAS binary archive exact topology bridge is solver-graph ready."
                        if archive_ready
                        else (
                            "MIDAS binary archive decoded preview bridge is intake-ready for visualization/optimization triage, "
                            "not solver-exact native topology."
                        )
                    ),
                    "viewer_ready": bool(archive_report.get("viewer_ready", False)),
                    "node_count": int(archive_report.get("node_count", 0) or 0),
                    "element_count": int(archive_report.get("element_count", 0) or 0),
                    "preview_exactness_tier": str(archive_report.get("preview_exactness_tier", "") or ""),
                    "preview_exactness_label": str(archive_report.get("preview_exactness_label", "") or ""),
                    "preview_exactness_signal_source": str(
                        archive_report.get("preview_exactness_signal_source", "") or ""
                    ),
                    "preview_surface_bucket": str(archive_report.get("preview_surface_bucket", "") or ""),
                    "topology_preview_ready": bool(archive_report.get("topology_preview_ready", False)),
                    "payload_exact_topology_ready": bool(archive_report.get("payload_exact_topology_ready", False)),
                    "exact_topology_candidate": bool(archive_report.get("exact_topology_candidate", False)),
                    "exact_topology_promoted": bool(archive_report.get("exact_topology_promoted", False)),
                    "topology_node_count": int(archive_report.get("topology_node_count", 0) or 0),
                    "topology_edge_count": int(archive_report.get("topology_edge_count", 0) or 0),
                    "missing_member_path_count": int(archive_report.get("missing_member_path_count", 0) or 0),
                    "missing_member_reference_count": int(
                        archive_report.get("missing_member_reference_count", 0) or 0
                    ),
                    **hard_tier,
                    **native_writeback_tier,
                    "archive_hard_tier_ready": archive_ready,
                    "archive_hard_tier_reason_code": archive_hard_reason_code,
                    "archive_hard_tier_note": archive_hard_note,
                }
            )
            if native_receipt:
                row["archive_native_writeback_receipt_json"] = str(native_receipt.get("receipt_json", "") or "")
                row["archive_native_writeback_receipt_md"] = str(native_receipt.get("receipt_md", "") or "")
                row["archive_native_writeback_summary_line"] = str(native_receipt.get("summary_line", "") or "")
            model_json = str(archive_report.get("model_json", "") or "")
            if model_json:
                row["archive_preview_model_json"] = model_json
                if archive_ready:
                    row["archive_solver_graph_model_json"] = model_json
            dataset_npz = str(archive_report.get("dataset_npz", "") or "")
            if dataset_npz:
                row["archive_preview_dataset_npz"] = dataset_npz
                if archive_ready:
                    row["archive_solver_graph_dataset_npz"] = dataset_npz
        elif archive_report:
            row["optimization_status"] = "archive_adapter_failed"
            row["archive_adapter_reason_code"] = str(archive_report.get("reason_code", "") or "")

    return row


def build_queue(
    *,
    redacted_manifest: Path,
    mgt_parse_report_dir: Path,
    ifc_adapter_report_dir: Path,
    midas_archive_adapter_report: Path,
    midas_native_writeback_diff_receipts_report: Path,
) -> dict[str, Any]:
    manifest = _load_json(redacted_manifest)
    archive_adapter_rows = _archive_adapter_report_rows(midas_archive_adapter_report)
    native_writeback_receipts = _native_writeback_receipt_rows(midas_native_writeback_diff_receipts_report)
    rows: list[dict[str, Any]] = []
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        for file_row in project.get("files", []):
            if not isinstance(file_row, dict) or file_row.get("model_optimization_candidate") is not True:
                continue
            rows.append(
                _queue_row(
                    project=project,
                    file_row=file_row,
                    parse_report_dir=mgt_parse_report_dir,
                    ifc_adapter_report_dir=ifc_adapter_report_dir,
                    archive_adapter_rows=archive_adapter_rows,
                    native_writeback_receipts=native_writeback_receipts,
                )
            )

    status_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("optimization_status", "") or "unknown")
        route = str(row.get("optimization_route", "") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        route_counts[route] = route_counts.get(route, 0) + 1

    ready_rows = [row for row in rows if row.get("ready_for_optimized_drawing_generation") is True]
    parser_failed_count = status_counts.get("parser_failed", 0)
    ifc_adapter_failed_count = status_counts.get("ifc_adapter_failed", 0)
    archive_adapter_failed_count = status_counts.get("archive_adapter_failed", 0)
    mgt_ready_rows = [row for row in rows if row.get("optimization_status") == "solver_graph_ready"]
    mgt_hard_ready_count = sum(1 for row in mgt_ready_rows if row.get("mgt_hard_tier_ready") is True)
    archive_hard_ready_count = status_counts.get("archive_solver_graph_ready", 0)
    archive_preview_ready_count = status_counts.get("archive_decoded_preview_bridge_ready", 0)
    archive_ready_rows = [
        row
        for row in rows
        if row.get("file_type") == ".zip"
        and row.get("optimization_status") in {"archive_solver_graph_ready", "archive_decoded_preview_bridge_ready"}
    ]
    archive_native_writeback_ready_count = sum(
        1 for row in archive_ready_rows if row.get("archive_native_writeback_ready") is True
    )
    archive_native_writeback_promoted_count = sum(
        1
        for row in archive_ready_rows
        if row.get("archive_hard_tier_reason_code") == "PASS_ARCHIVE_NATIVE_WRITEBACK_STABLE_DECODED_PREVIEW"
    )
    solver_exact_rows = [row for row in rows if row.get("solver_exact") is True]
    direct_mgt_solver_exact_count = sum(
        1 for row in solver_exact_rows if row.get("optimization_route") == "midas_mgt_direct_parser"
    )
    archive_solver_exact_count = sum(
        1 for row in solver_exact_rows if row.get("optimization_status") == "archive_solver_graph_ready"
    )
    summary = {
        "candidate_file_count": len(rows),
        "candidate_model_asset_count": sum(int(row.get("model_asset_count", 0) or 0) for row in rows),
        "optimized_drawing_generation_ready_count": len(ready_rows),
        "optimized_drawing_generation_ready_model_asset_count": sum(
            int(row.get("model_asset_count", 0) or 0) for row in ready_rows
        ),
        "ifc_adapter_required_count": status_counts.get("ifc_adapter_required", 0),
        "ifc_proxy_graph_ready_count": status_counts.get("ifc_proxy_graph_ready", 0),
        "ifc_adapter_failed_count": ifc_adapter_failed_count,
        "ifc_proxy_ready_note": "IFC proxy-ready rows are entity-count graph adapters, not solver-exact geometry extraction.",
        "archive_adapter_required_count": status_counts.get("archive_adapter_required", 0),
        "archive_decoded_preview_bridge_ready_count": archive_preview_ready_count,
        "archive_solver_graph_ready_count": archive_hard_ready_count,
        "archive_hard_tier_ready_count": archive_hard_ready_count,
        "archive_native_writeback_ready_count": archive_native_writeback_ready_count,
        "archive_native_writeback_promoted_count": archive_native_writeback_promoted_count,
        "archive_exact_topology_candidate_count": sum(
            1 for row in archive_ready_rows if row.get("exact_topology_candidate") is True
        ),
        "archive_verified_geometry_preview_count": sum(
            1 for row in archive_ready_rows if str(row.get("preview_exactness_tier", "") or "") == "verified-geometry"
        ),
        "archive_hard_tier_blocked_count": sum(
            1
            for row in archive_ready_rows
            if row.get("optimization_status") == "archive_decoded_preview_bridge_ready"
            and row.get("archive_hard_tier_ready") is False
        ),
        "archive_hard_tier_blocked_reason_counts": dict(
            sorted(
                {
                    reason: sum(
                        1
                        for row in archive_ready_rows
                        if row.get("archive_hard_tier_reason_code") == reason
                        and row.get("archive_hard_tier_ready") is False
                    )
                    for reason in {
                        str(row.get("archive_hard_tier_reason_code", "") or "")
                        for row in archive_ready_rows
                        if row.get("archive_hard_tier_ready") is False
                    }
                    if reason
                }.items()
            )
        ),
        "archive_adapter_failed_count": archive_adapter_failed_count,
        "archive_preview_ready_note": (
            "Archive preview-ready rows require exact_topology_promoted=true and preview graph/recovered topology count parity before hard solver graph promotion."
        ),
        "mgt_parser_pending_count": status_counts.get("parser_pending", 0),
        "mgt_parser_failed_count": parser_failed_count,
        "direct_solver_graph_ready_count": status_counts.get("solver_graph_ready", 0),
        "direct_mgt_solver_exact_count": direct_mgt_solver_exact_count,
        "archive_solver_exact_count": archive_solver_exact_count,
        "solver_exact_ready_count": len(solver_exact_rows),
        "mgt_hard_tier_ready_count": mgt_hard_ready_count,
        "mgt_hard_tier_blocked_count": len(mgt_ready_rows) - mgt_hard_ready_count,
        "mgt_hard_tier_blocked_reason_counts": dict(
            sorted(
                {
                    reason: sum(
                        1
                        for row in mgt_ready_rows
                        if row.get("mgt_hard_tier_reason_code") == reason
                        and row.get("mgt_hard_tier_ready") is False
                    )
                    for reason in {
                        str(row.get("mgt_hard_tier_reason_code", "") or "")
                        for row in mgt_ready_rows
                        if row.get("mgt_hard_tier_ready") is False
                    }
                    if reason
                }.items()
            )
        ),
        "solver_graph_ready_count": len(solver_exact_rows),
        "proxy_or_preview_ready_count": status_counts.get("ifc_proxy_graph_ready", 0)
        + archive_preview_ready_count,
        "ready_node_count_total": sum(int(row.get("node_count", 0) or 0) for row in ready_rows),
        "ready_element_count_total": sum(int(row.get("element_count", 0) or 0) for row in ready_rows),
        "ready_ifc_proxy_node_count_total": sum(int(row.get("proxy_node_count", 0) or 0) for row in ready_rows),
        "ready_ifc_proxy_edge_count_total": sum(int(row.get("proxy_edge_count", 0) or 0) for row in ready_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
    }
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_redacted_manifest": str(redacted_manifest),
        "mgt_parse_report_dir": str(mgt_parse_report_dir),
        "ifc_adapter_report_dir": str(ifc_adapter_report_dir),
        "midas_archive_adapter_report": str(midas_archive_adapter_report),
        "midas_native_writeback_diff_receipts_report": str(midas_native_writeback_diff_receipts_report),
        "contract_pass": parser_failed_count == 0 and ifc_adapter_failed_count == 0 and archive_adapter_failed_count == 0,
        "reason_code": (
            "PASS"
            if parser_failed_count == 0 and ifc_adapter_failed_count == 0 and archive_adapter_failed_count == 0
            else "ERR_MODEL_INTAKE_ADAPTER_FAILURE"
        ),
        "summary": summary,
        "queue": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redacted-manifest", type=Path, default=DEFAULT_REDACTED_MANIFEST)
    parser.add_argument("--mgt-parse-report-dir", type=Path, default=DEFAULT_MGT_PARSE_REPORT_DIR)
    parser.add_argument("--ifc-adapter-report-dir", type=Path, default=DEFAULT_IFC_ADAPTER_REPORT_DIR)
    parser.add_argument("--midas-archive-adapter-report", type=Path, default=DEFAULT_MIDAS_ARCHIVE_ADAPTER_REPORT)
    parser.add_argument(
        "--midas-native-writeback-diff-receipts-report",
        type=Path,
        default=DEFAULT_MIDAS_NATIVE_WRITEBACK_DIFF_RECEIPTS_REPORT,
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    queue = build_queue(
        redacted_manifest=args.redacted_manifest,
        mgt_parse_report_dir=args.mgt_parse_report_dir,
        ifc_adapter_report_dir=args.ifc_adapter_report_dir,
        midas_archive_adapter_report=args.midas_archive_adapter_report,
        midas_native_writeback_diff_receipts_report=args.midas_native_writeback_diff_receipts_report,
    )
    _write_json(args.out, queue)
    if args.json:
        print(json.dumps(queue, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = queue["summary"]
        print(
            "Real drawing optimization intake queue: "
            f"{queue['reason_code']} | candidates={summary['candidate_file_count']} | "
            f"ready={summary['optimized_drawing_generation_ready_count']} | "
            f"ifc_adapter={summary['ifc_adapter_required_count']} | "
            f"archive_adapter={summary['archive_adapter_required_count']}"
        )
    return 0 if queue["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
