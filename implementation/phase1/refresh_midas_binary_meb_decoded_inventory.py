#!/usr/bin/env python3
"""Refresh decoded inventory artifacts for extracted MIDAS .meb/.mmbx/.mcb archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from implementation.phase1.parse_midas_binary_meb_to_json_npz import decode_meb_inventory, _write_npz


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTED_DIR = REPO_ROOT / "implementation/phase1/open_data/midas/quality_corpus/extracted"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_table_local_preview_mode(preview_mode: str) -> bool:
    mode = str(preview_mode or "").strip().lower()
    return (
        "table_local" in mode
        or "table-local" in mode
        or "sparse_local" in mode
        or "payload_local" in mode
    )


def _classify_preview_quality(report_payload: dict[str, Any]) -> dict[str, Any]:
    summary = report_payload.get("summary", {}) if isinstance(report_payload.get("summary"), dict) else {}
    preview_mode = str(summary.get("geometry_preview_mode", "") or "")
    preview_point_count = int(summary.get("geometry_preview_point_count", 0) or 0)
    preview_segment_count = int(summary.get("geometry_preview_segment_count", 0) or 0)
    preview_feature_count = max(preview_point_count, preview_segment_count)
    geometry_preview_ready = bool(summary.get("geometry_preview_ready", False))
    topology_preview_ready = bool(summary.get("topology_preview_ready", False))
    table_local_probe = summary.get("table_local_preview_probe", {}) if isinstance(summary.get("table_local_preview_probe"), dict) else {}
    payload_exact_topology_ready = bool(
        summary.get("payload_exact_topology_ready", False)
        or table_local_probe.get("payload_exact_topology_ready", False)
    )

    if geometry_preview_ready:
        return {
            "rank": 5,
            "label": "verified preview",
            "mode": preview_mode,
            "feature_count": preview_feature_count,
            "point_count": preview_point_count,
            "segment_count": preview_segment_count,
        }
    if payload_exact_topology_ready and topology_preview_ready and _is_table_local_preview_mode(preview_mode) and preview_feature_count > 0:
        return {
            "rank": 4,
            "label": "payload-exact member-add preview",
            "mode": preview_mode,
            "feature_count": preview_feature_count,
            "point_count": preview_point_count,
            "segment_count": preview_segment_count,
        }
    if topology_preview_ready and _is_table_local_preview_mode(preview_mode) and preview_feature_count > 0:
        return {
            "rank": 4,
            "label": "topology-grounded preview",
            "mode": preview_mode,
            "feature_count": preview_feature_count,
            "point_count": preview_point_count,
            "segment_count": preview_segment_count,
        }
    if _is_table_local_preview_mode(preview_mode) and preview_feature_count > 0:
        return {
            "rank": 3,
            "label": "table-local preview",
            "mode": preview_mode,
            "feature_count": preview_feature_count,
            "point_count": preview_point_count,
            "segment_count": preview_segment_count,
        }
    if preview_mode == "mcvl_node_hint_preview" and preview_feature_count > 0:
        return {
            "rank": 2,
            "label": "hint preview",
            "mode": preview_mode,
            "feature_count": preview_feature_count,
            "point_count": preview_point_count,
            "segment_count": preview_segment_count,
        }
    if preview_feature_count > 0:
        return {
            "rank": 1,
            "label": "raw preview",
            "mode": preview_mode,
            "feature_count": preview_feature_count,
            "point_count": preview_point_count,
            "segment_count": preview_segment_count,
        }
    return {
        "rank": 0,
        "label": "inventory only",
        "mode": preview_mode,
        "feature_count": 0,
        "point_count": preview_point_count,
        "segment_count": preview_segment_count,
    }


def _selection_basis(report_payload: dict[str, Any]) -> str:
    summary = report_payload.get("summary", {}) if isinstance(report_payload.get("summary"), dict) else {}
    quality = _classify_preview_quality(report_payload)
    return (
        f"{quality['label']} | "
        f"mode={quality['mode'] or 'none'} | "
        f"points={quality['point_count']} | "
        f"segments={quality['segment_count']} | "
        f"tables={int(summary.get('table_entry_count', 0) or 0)} | "
        f"payload_tables={int(summary.get('in_file_payload_table_count', 0) or 0)} | "
        f"contract_pass={bool(report_payload.get('contract_pass', False))}"
    )


def _score_report(report_payload: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    summary = report_payload.get("summary", {}) if isinstance(report_payload.get("summary"), dict) else {}
    quality = _classify_preview_quality(report_payload)
    return (
        1 if bool(report_payload.get("contract_pass", False)) else 0,
        int(quality["rank"]),
        int(quality["segment_count"]),
        int(quality["point_count"]),
        int(summary.get("in_file_payload_table_count", 0) or 0),
        int(summary.get("table_entry_count", 0) or 0),
    )


def _candidate_rows(source_dir: Path, adapter_manifest: dict[str, Any]) -> list[Path]:
    binary_files = sorted(
        [
            path
            for pattern in ("*.meb", "*.mmbx", "*.mcb")
            for path in source_dir.glob(pattern)
        ]
    )
    summary = adapter_manifest.get("summary", {}) if isinstance(adapter_manifest.get("summary"), dict) else {}
    preferred_name = str(summary.get("recommended_primary_member", "") or "")
    preferred_path = source_dir / preferred_name if preferred_name else None
    if preferred_path is not None and preferred_path.exists():
        ordered = [preferred_path]
        ordered.extend(path for path in binary_files if path != preferred_path)
        return ordered
    return binary_files


def refresh_source(source_dir: Path) -> dict[str, Any]:
    adapter_manifest = _load_json(source_dir / "adapter_manifest.json")
    source_id = str(adapter_manifest.get("source_id", "") or source_dir.name)
    candidates = _candidate_rows(source_dir, adapter_manifest)
    if not candidates:
        raise FileNotFoundError(f"no .meb/.mmbx/.mcb files found in {source_dir}")

    evaluations: list[dict[str, Any]] = []
    best_payload: dict[str, Any] | None = None
    best_report: dict[str, Any] | None = None
    best_path: Path | None = None
    best_score: tuple[int, int, int, int, int, int] | None = None

    for member_path in candidates:
        inventory_payload, report_payload = decode_meb_inventory(member_path)
        report_score = _score_report(report_payload)
        summary = report_payload.get("summary", {}) if isinstance(report_payload.get("summary"), dict) else {}
        quality = _classify_preview_quality(report_payload)
        evaluations.append(
            {
                "member_name": member_path.name,
                "member_path": str(member_path),
                "score": list(report_score),
                "selection_basis": _selection_basis(report_payload),
                "reason_code": str(report_payload.get("reason_code", "") or ""),
                "contract_pass": bool(report_payload.get("contract_pass", False)),
                "preview_quality_rank": int(quality["rank"]),
                "preview_quality_label": str(quality["label"]),
                "geometry_preview_ready": bool(summary.get("geometry_preview_ready", False)),
                "topology_preview_ready": bool(summary.get("topology_preview_ready", False)),
                "geometry_preview_point_count": int(summary.get("geometry_preview_point_count", 0) or 0),
                "geometry_preview_segment_count": int(summary.get("geometry_preview_segment_count", 0) or 0),
                "geometry_preview_mode": str(summary.get("geometry_preview_mode", "") or ""),
                "mcvl_node_layout_state_label": str(
                    (summary.get("mcvl_node_uint_layout_probe", {}) if isinstance(summary.get("mcvl_node_uint_layout_probe"), dict) else {}).get("layout_state_label", "")
                    or ""
                ),
                "mcvl_node_likely_identifier_slots": [
                    int(value)
                    for value in (
                        (summary.get("mcvl_node_uint_layout_probe", {}) if isinstance(summary.get("mcvl_node_uint_layout_probe"), dict) else {}).get("likely_identifier_slots", [])
                        or []
                    )
                ],
                "mcvl_node_likely_counter_slots": [
                    int(value)
                    for value in (
                        (summary.get("mcvl_node_uint_layout_probe", {}) if isinstance(summary.get("mcvl_node_uint_layout_probe"), dict) else {}).get("likely_counter_slots", [])
                        or []
                    )
                ],
                "mcvl_node_likely_packed_identifier_pairs": [
                    [int(item) for item in pair]
                    for pair in (
                        (summary.get("mcvl_node_uint_layout_probe", {}) if isinstance(summary.get("mcvl_node_uint_layout_probe"), dict) else {}).get("likely_packed_identifier_pairs", [])
                        or []
                    )
                    if isinstance(pair, (list, tuple))
                ],
                "table_local_topology_grounding_label": str(
                    (summary.get("table_local_preview_probe", {}) if isinstance(summary.get("table_local_preview_probe"), dict) else {}).get("topology_grounding_label", "")
                    or ""
                ),
                "table_local_topology_edge_count": int(
                    (summary.get("table_local_preview_probe", {}) if isinstance(summary.get("table_local_preview_probe"), dict) else {}).get("topology_edge_count", 0)
                    or 0
                ),
                "table_local_topology_component_count": int(
                    (summary.get("table_local_preview_probe", {}) if isinstance(summary.get("table_local_preview_probe"), dict) else {}).get("topology_component_count", 0)
                    or 0
                ),
                "table_local_topology_preview_ready": bool(
                    (summary.get("table_local_preview_probe", {}) if isinstance(summary.get("table_local_preview_probe"), dict) else {}).get("topology_preview_ready", False)
                ),
                "table_local_topology_readiness_label": str(
                    (summary.get("table_local_preview_probe", {}) if isinstance(summary.get("table_local_preview_probe"), dict) else {}).get("topology_readiness_label", "")
                    or ""
                ),
                "table_entry_count": int(summary.get("table_entry_count", 0) or 0),
                "in_file_payload_table_count": int(summary.get("in_file_payload_table_count", 0) or 0),
            }
        )
        if best_score is None or report_score > best_score:
            best_score = report_score
            best_payload = inventory_payload
            best_report = report_payload
            best_path = member_path

    assert best_report is not None and best_path is not None
    json_out = source_dir / "meb_decoded_inventory.json"
    npz_out = source_dir / "meb_decoded_inventory.npz"
    report_out = source_dir / "meb_decoded_inventory_report.json"
    refresh_report_out = source_dir / "meb_inventory_refresh_report.json"

    if best_payload:
        json_out.write_text(json.dumps(best_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_npz(npz_out, best_payload.get("table_inventory_rows", []), best_payload.get("geometry_preview", {}))
    report_out.write_text(json.dumps(best_report, ensure_ascii=False, indent=2), encoding="utf-8")

    refresh_payload = {
        "schema_version": "1.0",
        "run_id": "phase1-refresh-midas-binary-meb-decoded-inventory",
        "source_id": source_id,
        "selection_priority_policy": [
            "verified preview",
            "payload-exact member-add preview",
            "topology-grounded preview",
            "table-local preview",
            "hint preview",
            "raw preview",
            "inventory only",
        ],
        "selected_member_name": best_path.name,
        "selected_member_path": str(best_path),
        "selected_reason_code": str(best_report.get("reason_code", "") or ""),
        "selected_contract_pass": bool(best_report.get("contract_pass", False)),
        "selected_score": list(best_score) if best_score is not None else [],
        "selected_selection_basis": _selection_basis(best_report),
        "selected_preview_quality": _classify_preview_quality(best_report),
        "selected_summary": best_report.get("summary", {}) if isinstance(best_report.get("summary"), dict) else {},
        "evaluations": evaluations,
    }
    refresh_report_out.write_text(json.dumps(refresh_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return refresh_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--all", action="store_true", dest="refresh_all")
    parser.add_argument("--extracted-dir", default=str(DEFAULT_EXTRACTED_DIR))
    args = parser.parse_args()

    extracted_dir = Path(args.extracted_dir)
    source_ids = [str(row).strip() for row in args.source_id if str(row).strip()]
    if args.refresh_all and not source_ids:
        source_ids = [path.name for path in sorted(extracted_dir.iterdir()) if path.is_dir()]
    if not source_ids:
        raise SystemExit("provide --source-id or --all")

    refreshed = 0
    for source_id in source_ids:
        source_dir = extracted_dir / source_id
        if not source_dir.exists():
            continue
        if not any(path for pattern in ("*.meb", "*.mmbx", "*.mcb") for path in source_dir.glob(pattern)):
            continue
        payload = refresh_source(source_dir)
        refreshed += 1
        print(
            f"Refreshed decoded inventory: {source_id} | "
            f"member={payload['selected_member_name']} | "
            f"reason={payload['selected_reason_code']}"
        )
    if refreshed <= 0:
        raise SystemExit("no .meb/.mmbx/.mcb sources refreshed")


if __name__ == "__main__":
    main()
