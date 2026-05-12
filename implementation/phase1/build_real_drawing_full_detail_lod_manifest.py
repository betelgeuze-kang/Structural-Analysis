#!/usr/bin/env python3
"""Build full-detail LOD evidence for sampled real drawing assets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from implementation.phase1.build_real_drawing_private_3d_webviewer import (
    DEFAULT_INTAKE_QUEUE,
    DEFAULT_MAX_SEGMENTS_PER_ASSET,
    _candidate_path,
    _extract_xyz_segments,
    _graph_reference,
    _load_json,
)


DEFAULT_OUT = Path("implementation/phase1/commercialization_status/real_drawing_full_detail_lod_manifest.json")
DEFAULT_OUT_MD = Path("implementation/phase1/commercialization_status/real_drawing_full_detail_lod_manifest.md")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")


def _ready_rows(intake_queue: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in (intake_queue.get("queue") or [])
        if isinstance(row, dict) and bool(row.get("ready_for_optimized_drawing_generation", False))
    ]


def _base_dir_for_intake(intake_queue_path: Path) -> Path:
    if intake_queue_path.parent.name == "real_drawing_private_corpus":
        return intake_queue_path.parent.parent.parent
    return Path(".")


def _lod_item(
    row: dict[str, Any],
    *,
    asset_ref: str,
    base_dir: Path,
    max_segments_per_asset: int,
) -> dict[str, Any] | None:
    graph_path = _candidate_path(_graph_reference(row), base_dir=base_dir)
    if graph_path is None:
        return None
    payload = _load_json(graph_path)
    sampled_segments, metrics = _extract_xyz_segments(payload, max_segments=max_segments_per_asset)
    full_segment_count = _safe_int(metrics.get("renderable_segment_count"), len(sampled_segments))
    sample_segment_count = len(sampled_segments)
    if full_segment_count <= sample_segment_count or sample_segment_count <= 0:
        return None
    sample_ratio = round(sample_segment_count / full_segment_count, 6) if full_segment_count > 0 else 0.0
    return {
        "asset_ref": asset_ref,
        "file_type": str(row.get("file_type") or ""),
        "route": str(row.get("optimization_route") or ""),
        "status": str(row.get("optimization_status") or ""),
        "solver_exact": bool(row.get("solver_exact", False)),
        "contract_pass": True,
        "reason_code": "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED",
        "full_detail_lod_ready": True,
        "lod_policy": "sampled_viewport_with_full_detail_source_receipt",
        "full_detail_segment_count": full_segment_count,
        "viewer_sample_segment_count": sample_segment_count,
        "sample_ratio": sample_ratio,
        "node_count": _safe_int(metrics.get("node_count"), 0),
        "element_count": _safe_int(metrics.get("element_count"), 0),
        "closure_evidence": [
            "source_solver_graph_json_receipt",
            "full_detail_segment_count_receipt",
            "viewer_sample_lod_policy_receipt",
        ],
    }


def build_full_detail_lod_manifest(
    intake_queue_path: Path = DEFAULT_INTAKE_QUEUE,
    *,
    max_segments_per_asset: int = DEFAULT_MAX_SEGMENTS_PER_ASSET,
) -> dict[str, Any]:
    if not intake_queue_path.exists():
        return {
            "schema_version": "real-drawing-full-detail-lod-manifest.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_intake_queue": str(intake_queue_path),
            "contract_pass": False,
            "reason_code": "ERR_REAL_DRAWING_INTAKE_QUEUE_MISSING",
            "summary": {
                "sampled_solver_exact_asset_count": 0,
                "full_detail_segment_count_total": 0,
                "viewer_sample_segment_count_total": 0,
            },
            "lod_items": [],
        }
    intake_queue = _load_json(intake_queue_path)
    base_dir = _base_dir_for_intake(intake_queue_path)
    items = [
        item
        for index, row in enumerate(_ready_rows(intake_queue), start=1)
        for item in [
            _lod_item(
                row,
                asset_ref=f"RD-{index:03d}",
                base_dir=base_dir,
                max_segments_per_asset=max_segments_per_asset,
            )
        ]
        if item is not None
    ]
    sampled_solver_exact_count = sum(1 for item in items if bool(item.get("solver_exact", False)))
    sampled_preview_count = len(items) - sampled_solver_exact_count
    return {
        "schema_version": "real-drawing-full-detail-lod-manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_intake_queue": str(intake_queue_path),
        "contract_pass": True,
        "reason_code": "PASS_FULL_DETAIL_LOD_MANIFEST_READY",
        "summary": {
            "sampled_asset_count": len(items),
            "sampled_solver_exact_asset_count": sampled_solver_exact_count,
            "sampled_preview_asset_count": sampled_preview_count,
            "full_detail_segment_count_total": sum(
                _safe_int(item.get("full_detail_segment_count"), 0) for item in items
            ),
            "viewer_sample_segment_count_total": sum(
                _safe_int(item.get("viewer_sample_segment_count"), 0) for item in items
            ),
            "max_segments_per_asset": int(max_segments_per_asset),
        },
        "lod_items": items,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    items = report.get("lod_items") if isinstance(report.get("lod_items"), list) else []
    lines = [
        "# Real Drawing Full-Detail LOD Manifest",
        "",
        f"- Contract: {report.get('reason_code')}",
        f"- Sampled assets: {summary.get('sampled_asset_count', 0)}",
        f"- Sampled solver-exact assets: {summary.get('sampled_solver_exact_asset_count', 0)}",
        f"- Sampled preview/draft assets: {summary.get('sampled_preview_asset_count', 0)}",
        f"- Full-detail segments: {summary.get('full_detail_segment_count_total', 0)}",
        f"- Viewer sample segments: {summary.get('viewer_sample_segment_count_total', 0)}",
        "",
        "## LOD Evidence",
        "",
    ]
    if not items:
        lines.append("No sampled solver-exact LOD evidence items are open.")
        return "\n".join(lines)
    lines.extend(
        [
            "| Asset | Policy | Viewer Sample | Full Detail | Sample Ratio |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for item in items:
        lines.append(
            "| {asset} | {policy} | {sample} | {full} | {ratio} |".format(
                asset=item.get("asset_ref", ""),
                policy=item.get("lod_policy", ""),
                sample=item.get("viewer_sample_segment_count", 0),
                full=item.get("full_detail_segment_count", 0),
                ratio=item.get("sample_ratio", 0),
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-queue", type=Path, default=DEFAULT_INTAKE_QUEUE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--max-segments-per-asset", type=int, default=DEFAULT_MAX_SEGMENTS_PER_ASSET)
    parser.add_argument("--json", action="store_true", help="Print the LOD manifest JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_full_detail_lod_manifest(
        args.intake_queue,
        max_segments_per_asset=args.max_segments_per_asset,
    )
    _write_json(args.out, report)
    _write_text(args.out_md, render_markdown(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if bool(report.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
