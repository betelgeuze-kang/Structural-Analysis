#!/usr/bin/env python3
"""Materialize MIDAS binary archive adapter artifacts for the private corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_PRIVATE_MANIFEST = Path("private_corpus/real_drawings/private_real_drawing_corpus_manifest.json")
DEFAULT_OUT_ROOT = Path("tmp/real_drawing_private_corpus/midas_archive_adapter")
DEFAULT_OUT_REPORT = DEFAULT_OUT_ROOT / "midas_archive_adapter_report.json"
SCRIPT_ROOT = Path(__file__).resolve().parent
PREPARE_ARCHIVE_ADAPTER = SCRIPT_ROOT / "prepare_midas_binary_archive_adapter.py"
PARSE_BINARY_MEB = SCRIPT_ROOT / "parse_midas_binary_meb_to_json_npz.py"
PREPARE_PREVIEW_BRIDGE = SCRIPT_ROOT / "prepare_midas_binary_decoded_preview_bridge.py"
REPORT_SCHEMA_VERSION = "real-drawing-midas-archive-adapter-report.v1"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _source_rows(private_manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for project in private_manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        for file_row in project.get("files", []):
            if not isinstance(file_row, dict):
                continue
            if str(file_row.get("file_type", "") or "").lower() != ".zip":
                continue
            if file_row.get("model_optimization_candidate") is not True:
                continue
            rows.append((project, file_row))
    return rows


def _primary_member_path(adapter_manifest: dict[str, Any]) -> Path | None:
    summary = adapter_manifest.get("summary") if isinstance(adapter_manifest.get("summary"), dict) else {}
    preferred_name = str(summary.get("recommended_primary_member", "") or "")
    out_dir = Path(str(adapter_manifest.get("out_dir", "") or ""))
    if preferred_name:
        preferred_path = out_dir / preferred_name
        if preferred_path.exists():
            return preferred_path
    for row in adapter_manifest.get("members", []):
        if not isinstance(row, dict):
            continue
        path = Path(str(row.get("extracted_path", "") or ""))
        if path.exists():
            return path
    return None


def _status(
    *,
    adapter_pass: bool,
    decode_pass: bool,
    bridge_pass: bool,
) -> str:
    if bridge_pass:
        return "decoded_preview_bridge_ready"
    if decode_pass:
        return "decoded_inventory_ready"
    if adapter_pass:
        return "archive_adapter_ready"
    return "archive_adapter_failed"


def _archive_hard_tier_decision(row: dict[str, Any]) -> dict[str, Any]:
    exactness_tier = str(row.get("preview_exactness_tier", "") or "")
    exact_promoted = bool(row.get("exact_topology_promoted", False)) or exactness_tier == "exact-topology-promoted"
    exact_candidate = bool(row.get("exact_topology_candidate", False)) or exactness_tier == "exact-topology-candidate"
    node_count = int(row.get("node_count", 0) or 0)
    element_count = int(row.get("element_count", 0) or 0)
    topology_node_count = int(row.get("topology_node_count", 0) or 0)
    topology_edge_count = int(row.get("topology_edge_count", 0) or 0)
    missing_member_path_count = int(row.get("missing_member_path_count", 0) or 0)
    missing_member_reference_count = int(row.get("missing_member_reference_count", 0) or 0)
    has_graph = node_count > 0 and element_count > 0
    has_topology_counts = topology_node_count > 0 and topology_edge_count > 0
    no_missing_refs = missing_member_path_count == 0 and missing_member_reference_count == 0
    graph_matches_topology_counts = node_count == topology_node_count and element_count == topology_edge_count

    if exact_promoted and has_graph and has_topology_counts and no_missing_refs and graph_matches_topology_counts:
        return {
            "archive_hard_tier_ready": True,
            "archive_hard_tier_reason_code": "PASS_ARCHIVE_EXACT_TOPOLOGY_PROMOTED",
        }
    if exact_promoted and not has_topology_counts:
        reason_code = "ERR_ARCHIVE_PROMOTED_TOPOLOGY_COUNTS_MISSING"
    elif exact_promoted and not no_missing_refs:
        reason_code = "ERR_ARCHIVE_PROMOTED_TOPOLOGY_REFERENCES_UNRESOLVED"
    elif exact_promoted and not graph_matches_topology_counts:
        reason_code = "ERR_ARCHIVE_PROMOTED_TOPOLOGY_GRAPH_PARITY_MISMATCH"
    elif exact_promoted:
        reason_code = "ERR_ARCHIVE_PROMOTED_GRAPH_EMPTY"
    elif exact_candidate and has_graph and has_topology_counts and no_missing_refs and not graph_matches_topology_counts:
        reason_code = "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_GRAPH_PARITY_MISMATCH"
    elif exact_candidate:
        reason_code = "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_NOT_PROMOTED"
    elif exactness_tier == "verified-geometry":
        reason_code = "ERR_ARCHIVE_VERIFIED_GEOMETRY_NOT_SOLVER_TOPOLOGY"
    else:
        reason_code = "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT"
    return {
        "archive_hard_tier_ready": False,
        "archive_hard_tier_reason_code": reason_code,
    }


def _materialize_source(
    *,
    project: dict[str, Any],
    file_row: dict[str, Any],
    out_root: Path,
    python_executable: str,
) -> dict[str, Any]:
    file_id = str(file_row.get("file_id", "") or "archive")
    archive_path = Path(str(file_row.get("private_path", "") or ""))
    source_out = out_root / file_id
    extracted_dir = source_out / "extracted"
    adapter_report_path = source_out / "adapter_manifest.json"
    inventory_json = source_out / "meb_decoded_inventory.json"
    inventory_npz = source_out / "meb_decoded_inventory.npz"
    inventory_report = source_out / "meb_decoded_inventory_report.json"
    bridge_model_json = source_out / "model.json"
    bridge_npz = source_out / "model.npz"
    bridge_report = source_out / "decoded_preview_bridge_report.json"
    source_out.mkdir(parents=True, exist_ok=True)

    row: dict[str, Any] = {
        "project_id": str(project.get("project_id", "") or ""),
        "project_title": str(project.get("project_title", "") or ""),
        "source_family": str(project.get("source_family", "") or ""),
        "file_id": file_id,
        "file_name": str(file_row.get("file_name", "") or ""),
        "file_type": str(file_row.get("file_type", "") or ""),
        "bytes": int(file_row.get("bytes", 0) or 0),
        "sha256": str(file_row.get("sha256", "") or ""),
        "source_url": str(file_row.get("source_url", "") or ""),
        "zip_model_member_count": int(file_row.get("zip_model_member_count", 0) or 0),
        "adapter_report": str(adapter_report_path),
        "inventory_report": str(inventory_report),
        "bridge_report": str(bridge_report),
        "model_json": str(bridge_model_json),
        "dataset_npz": str(bridge_npz),
        "raw_redistribution_allowed": False,
        "release_surface_allowed": False,
    }

    if not archive_path.exists():
        row.update({"status": "archive_adapter_failed", "reason_code": "ERR_PRIVATE_ARCHIVE_MISSING"})
        return row

    adapter_proc = _run(
        [
            python_executable,
            str(PREPARE_ARCHIVE_ADAPTER),
            "--source-id",
            file_id,
            "--archive",
            str(archive_path),
            "--out-dir",
            str(extracted_dir),
            "--report-out",
            str(adapter_report_path),
        ]
    )
    adapter_manifest = _load_json(adapter_report_path) if adapter_report_path.exists() else {}
    adapter_pass = adapter_proc.returncode == 0 and adapter_manifest.get("contract_pass") is True
    row["adapter_reason_code"] = str(adapter_manifest.get("reason_code", "") or "")
    row["recognized_member_count"] = int(
        (adapter_manifest.get("summary", {}) if isinstance(adapter_manifest.get("summary"), dict) else {}).get(
            "recognized_member_count", 0
        )
        or 0
    )
    if not adapter_pass:
        row.update({"status": _status(adapter_pass=False, decode_pass=False, bridge_pass=False), "reason_code": row["adapter_reason_code"]})
        return row

    primary_member_path = _primary_member_path(adapter_manifest)
    if primary_member_path is None:
        row.update({"status": "archive_adapter_ready", "reason_code": "ERR_PRIMARY_MEMBER_MISSING"})
        return row
    row["selected_member_extension"] = primary_member_path.suffix.lower()
    row["selected_member_size_bytes"] = int(primary_member_path.stat().st_size)

    decode_proc = _run(
        [
            python_executable,
            str(PARSE_BINARY_MEB),
            "--meb",
            str(primary_member_path),
            "--json-out",
            str(inventory_json),
            "--npz-out",
            str(inventory_npz),
            "--report-out",
            str(inventory_report),
        ]
    )
    inventory_payload = _load_json(inventory_report) if inventory_report.exists() else {}
    decode_pass = decode_proc.returncode == 0 and inventory_payload.get("contract_pass") is True
    row["decode_reason_code"] = str(inventory_payload.get("reason_code", "") or "")
    inventory_summary = inventory_payload.get("summary") if isinstance(inventory_payload.get("summary"), dict) else {}
    row["decoded_geometry_preview_ready"] = bool(inventory_summary.get("geometry_preview_ready", False))
    row["decoded_geometry_preview_point_count"] = int(inventory_summary.get("geometry_preview_point_count", 0) or 0)
    row["decoded_geometry_preview_segment_count"] = int(inventory_summary.get("geometry_preview_segment_count", 0) or 0)
    row["decoded_geometry_preview_mode"] = str(inventory_summary.get("geometry_preview_mode", "") or "")
    if not decode_pass:
        row.update({"status": _status(adapter_pass=True, decode_pass=False, bridge_pass=False), "reason_code": row["decode_reason_code"]})
        return row

    bridge_proc = _run(
        [
            python_executable,
            str(PREPARE_PREVIEW_BRIDGE),
            "--source-id",
            file_id,
            "--decoded-inventory-json",
            str(inventory_json),
            "--decoded-inventory-report",
            str(inventory_report),
            "--refresh-report",
            str(source_out / "missing_refresh_report.json"),
            "--model-json-out",
            str(bridge_model_json),
            "--npz-out",
            str(bridge_npz),
            "--report-out",
            str(bridge_report),
        ]
    )
    bridge_payload = _load_json(bridge_report) if bridge_report.exists() else {}
    bridge_pass = bridge_proc.returncode == 0 and bridge_payload.get("contract_pass") is True
    bridge_summary = bridge_payload.get("summary") if isinstance(bridge_payload.get("summary"), dict) else {}
    row.update(
        {
            "bridge_reason_code": str(bridge_payload.get("reason_code", "") or ""),
            "viewer_ready": bool(bridge_summary.get("viewer_ready", False)),
            "node_count": int(bridge_summary.get("node_count", 0) or 0),
            "element_count": int(bridge_summary.get("element_count", 0) or 0),
            "preview_surface_bucket": str(bridge_summary.get("preview_surface_bucket", "") or ""),
            "preview_state_label": str(bridge_summary.get("preview_state_label", "") or ""),
            "preview_exactness_tier": str(bridge_summary.get("preview_exactness_tier", "") or ""),
            "preview_exactness_label": str(bridge_summary.get("preview_exactness_label", "") or ""),
            "preview_exactness_signal_source": str(bridge_summary.get("preview_exactness_signal_source", "") or ""),
            "topology_preview_ready": bool(bridge_summary.get("topology_preview_ready", False)),
            "payload_exact_topology_ready": bool(bridge_summary.get("payload_exact_topology_ready", False)),
            "exact_topology_candidate": bool(bridge_summary.get("exact_topology_candidate", False)),
            "exact_topology_promoted": bool(bridge_summary.get("exact_topology_promoted", False)),
            "topology_readiness_label": str(bridge_summary.get("topology_readiness_label", "") or ""),
            "topology_grounding_label": str(bridge_summary.get("topology_grounding_label", "") or ""),
            "topology_node_count": int(bridge_summary.get("topology_node_count", 0) or 0),
            "topology_edge_count": int(bridge_summary.get("topology_edge_count", 0) or 0),
            "missing_member_path_count": int(bridge_summary.get("missing_member_path_count", 0) or 0),
            "missing_member_reference_count": int(bridge_summary.get("missing_member_reference_count", 0) or 0),
            "status": _status(adapter_pass=True, decode_pass=True, bridge_pass=bridge_pass),
            "reason_code": str(bridge_payload.get("reason_code", row["decode_reason_code"]) or row["decode_reason_code"]),
        }
    )
    row.update(_archive_hard_tier_decision(row))
    return row


def materialize_adapters(
    *,
    private_manifest_path: Path,
    out_root: Path,
    python_executable: str,
) -> dict[str, Any]:
    private_manifest = _load_json(private_manifest_path)
    rows = [
        _materialize_source(project=project, file_row=file_row, out_root=out_root, python_executable=python_executable)
        for project, file_row in _source_rows(private_manifest)
    ]
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    bridge_ready_rows = [row for row in rows if row.get("status") == "decoded_preview_bridge_ready"]
    hard_ready_rows = [row for row in bridge_ready_rows if row.get("archive_hard_tier_ready") is True]
    exact_candidate_rows = [row for row in bridge_ready_rows if row.get("exact_topology_candidate") is True]
    verified_geometry_rows = [
        row for row in bridge_ready_rows if str(row.get("preview_exactness_tier", "") or "") == "verified-geometry"
    ]
    summary = {
        "archive_candidate_count": len(rows),
        "recognized_member_count": sum(int(row.get("recognized_member_count", 0) or 0) for row in rows),
        "decoded_inventory_ready_count": sum(
            1 for row in rows if row.get("status") in {"decoded_inventory_ready", "decoded_preview_bridge_ready"}
        ),
        "decoded_preview_bridge_ready_count": len(bridge_ready_rows),
        "archive_hard_tier_ready_count": len(hard_ready_rows),
        "archive_exact_topology_candidate_count": len(exact_candidate_rows),
        "archive_verified_geometry_preview_count": len(verified_geometry_rows),
        "archive_hard_tier_blocked_count": len(bridge_ready_rows) - len(hard_ready_rows),
        "archive_hard_tier_blocked_reason_counts": dict(
            sorted(
                {
                    reason: sum(
                        1
                        for row in bridge_ready_rows
                        if row.get("archive_hard_tier_ready") is False
                        and row.get("archive_hard_tier_reason_code") == reason
                    )
                    for reason in {
                        str(row.get("archive_hard_tier_reason_code", "") or "")
                        for row in bridge_ready_rows
                        if row.get("archive_hard_tier_ready") is False
                    }
                    if reason
                }.items()
            )
        ),
        "archive_hard_tier_guard_note": (
            "Archive preview bridges require exact_topology_promoted=true plus preview graph/recovered topology count parity "
            "before solver-graph hard tier promotion; exact-topology-candidate and verified-geometry remain preview/triage inputs."
        ),
        "viewer_ready_count": sum(1 for row in bridge_ready_rows if row.get("viewer_ready") is True),
        "ready_node_count_total": sum(int(row.get("node_count", 0) or 0) for row in bridge_ready_rows),
        "ready_element_count_total": sum(int(row.get("element_count", 0) or 0) for row in bridge_ready_rows),
        "status_counts": dict(sorted(status_counts.items())),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "out_root": str(out_root),
        "contract_pass": bool(rows) and len(bridge_ready_rows) == len(rows),
        "reason_code": "PASS" if bool(rows) and len(bridge_ready_rows) == len(rows) else "ERR_ARCHIVE_ADAPTER_INCOMPLETE",
        "summary": summary,
        "archives": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-manifest", type=Path, default=DEFAULT_PRIVATE_MANIFEST)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = materialize_adapters(
        private_manifest_path=args.private_manifest,
        out_root=args.out_root,
        python_executable=str(args.python_executable),
    )
    _write_json(args.out_report, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = report["summary"]
        print(
            "MIDAS archive private corpus adapters: "
            f"{report['reason_code']} | archives={summary['archive_candidate_count']} | "
            f"bridge_ready={summary['decoded_preview_bridge_ready_count']} | "
            f"viewer_ready={summary['viewer_ready_count']}"
        )
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
