#!/usr/bin/env python3
"""Build an evidence plan for promoting IFC proxy graphs to solver-exact drawings."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_VIEWER_MANIFEST = Path(
    "implementation/phase1/commercialization_status/real_drawing_private_3d_viewer_manifest.json"
)
DEFAULT_INTAKE_QUEUE = Path("tmp/real_drawing_private_corpus/model_optimization_intake_queue.json")
DEFAULT_OUT = Path(
    "implementation/phase1/commercialization_status/real_drawing_ifc_solver_exact_reconstruction_plan.json"
)
DEFAULT_OUT_MD = Path(
    "implementation/phase1/commercialization_status/real_drawing_ifc_solver_exact_reconstruction_plan.md"
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object at {path}")
    return payload


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    return _load_json(path) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")


def _flags(row: dict[str, Any]) -> list[str]:
    return sorted(str(flag) for flag in (row.get("quality_flags") or []) if str(flag))


def _ready_intake_rows(intake_queue: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in (intake_queue.get("queue") or [])
        if isinstance(row, dict) and bool(row.get("ready_for_optimized_drawing_generation", False))
    ]


def _report_metrics(row: dict[str, Any], report: dict[str, Any], graph: dict[str, Any]) -> dict[str, int]:
    report_metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    graph_metrics = graph.get("metrics") if isinstance(graph.get("metrics"), dict) else {}
    return {
        "proxy_node_count": _safe_int(
            report_metrics.get("proxy_node_count", graph_metrics.get("proxy_node_count", row.get("proxy_node_count", 0)))
        ),
        "proxy_edge_count": _safe_int(
            report_metrics.get("proxy_edge_count", graph_metrics.get("proxy_edge_count", row.get("proxy_edge_count", 0)))
        ),
        "structural_entity_count": _safe_int(
            report_metrics.get(
                "structural_entity_count",
                graph_metrics.get("structural_entity_count", row.get("structural_entity_count", 0)),
            )
        ),
        "storey_count": _safe_int(
            report_metrics.get("storey_count", graph_metrics.get("storey_count", row.get("storey_count", 0)))
        ),
    }


def _relationship_types(graph: dict[str, Any]) -> list[str]:
    relationship_types = {
        str(edge.get("relationship") or edge.get("family") or edge.get("type") or "")
        for edge in (graph.get("edges") or [])
        if isinstance(edge, dict)
    }
    return sorted(value for value in relationship_types if value)


def _blocker(metrics: dict[str, int], flags: list[str]) -> tuple[str, str]:
    proxy_edge_count = _safe_int(metrics.get("proxy_edge_count", 0))
    structural_entity_count = _safe_int(metrics.get("structural_entity_count", 0))
    if proxy_edge_count <= 0 or "proxy_node_glyph_fallback" in set(flags):
        return "ifc_relationship_edge_extraction_required", "ERR_IFC_PROXY_NODE_GLYPH_FALLBACK"
    if structural_entity_count > 0 and proxy_edge_count < structural_entity_count:
        return "ifc_relationship_coverage_gap", "ERR_IFC_PROXY_RELATIONSHIP_COVERAGE_GAP"
    return "ifc_geometry_material_load_solver_exact_adapter_required", "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY"


def _required_evidence(blocker_family: str) -> list[str]:
    evidence = [
        "ifc_local_placement_coordinate_extraction_receipt",
        "ifc_representation_shape_axis_receipt",
        "ifc_material_section_binding_receipt",
        "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt",
        "solver_graph_json_npz_receipt",
        "viewer_sidecar_rebuild_receipt",
    ]
    if blocker_family in {"ifc_relationship_edge_extraction_required", "ifc_relationship_coverage_gap"}:
        return ["ifc_relationship_edge_extraction_receipt", *evidence]
    return evidence


def _reconstruction_steps(blocker_family: str) -> list[str]:
    steps = [
        "extract_ifc_local_placement_coordinate_graph",
        "bind_shape_representation_to_member_axis_or_surface",
        "map_material_profile_and_section_assignments",
        "extract_load_cases_or_attach_engineer_signed_zero_load_receipt",
        "emit_solver_exact_graph_and_viewer_sidecar",
    ]
    if blocker_family in {"ifc_relationship_edge_extraction_required", "ifc_relationship_coverage_gap"}:
        return ["recover_structural_relationship_edges", *steps]
    return steps


def _build_asset_ref_rows(
    viewer_manifest: dict[str, Any],
    intake_queue: dict[str, Any],
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    viewer_assets = {
        str(asset.get("asset_ref") or ""): asset
        for asset in (viewer_manifest.get("assets") or [])
        if isinstance(asset, dict) and str(asset.get("asset_ref") or "")
    }
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for index, intake_row in enumerate(_ready_intake_rows(intake_queue), start=1):
        asset_ref = f"RD-{index:03d}"
        viewer_asset = viewer_assets.get(asset_ref, {})
        if str(intake_row.get("file_type") or "").lower() == ".ifc":
            rows.append((asset_ref, intake_row, viewer_asset))
    if rows:
        return rows
    return [
        (
            str(asset.get("asset_ref") or ""),
            {},
            asset,
        )
        for asset in viewer_assets.values()
        if str(asset.get("file_type") or "").lower() == ".ifc"
    ]


def _plan_row(asset_ref: str, intake_row: dict[str, Any], viewer_asset: dict[str, Any]) -> dict[str, Any]:
    report_path_text = str(intake_row.get("ifc_adapter_report") or "")
    graph_path_text = str(intake_row.get("ifc_proxy_graph_json") or "")
    report_path = Path(report_path_text) if report_path_text else None
    graph_path = Path(graph_path_text) if graph_path_text else None
    report = _load_json_if_exists(report_path) if report_path is not None else {}
    graph_path_text = str(report.get("graph_json") or graph_path_text)
    graph_path = Path(graph_path_text) if graph_path_text else None
    graph = _load_json_if_exists(graph_path) if graph_path is not None else {}
    flags = _flags(viewer_asset) or ["proxy_layout_not_true_geometry", "not_solver_exact"]
    metrics = _report_metrics(intake_row, report, graph)
    blocker_family, blocker_reason_code = _blocker(metrics, flags)
    structural_entity_count = _safe_int(metrics.get("structural_entity_count", 0))
    proxy_edge_count = _safe_int(metrics.get("proxy_edge_count", 0))
    edge_coverage_ratio = (
        round(min(1.0, proxy_edge_count / structural_entity_count), 4)
        if structural_entity_count > 0
        else 0.0
    )
    return {
        "asset_ref": asset_ref,
        "file_id": str(intake_row.get("file_id") or ""),
        "file_type": ".ifc",
        "route": str(viewer_asset.get("route") or intake_row.get("optimization_route") or "ifc_to_structural_graph_adapter"),
        "status": str(viewer_asset.get("status") or intake_row.get("optimization_status") or "ifc_proxy_graph_ready"),
        "current_solver_exact": bool(viewer_asset.get("solver_exact", intake_row.get("solver_exact", False))),
        "reconstruction_ready": False,
        "commercial_claim_blocked": True,
        "blocker_family": blocker_family,
        "blocker_reason_code": blocker_reason_code,
        "quality_flags": flags,
        "adapter_report": str(report_path) if report_path is not None else "",
        "proxy_graph_json": str(graph_path) if graph_path is not None else "",
        "metrics": {
            **metrics,
            "edge_coverage_ratio": edge_coverage_ratio,
            "proxy_relationship_types": _relationship_types(graph),
        },
        "required_evidence": _required_evidence(blocker_family),
        "reconstruction_steps": _reconstruction_steps(blocker_family),
        "commercialization_recommendation": (
            "Keep this asset in proxy_preview_review until placement, shape, section/material, load, "
            "and solver graph receipts are attached."
        ),
    }


def build_reconstruction_plan(
    viewer_manifest_path: Path = DEFAULT_VIEWER_MANIFEST,
    intake_queue_path: Path = DEFAULT_INTAKE_QUEUE,
) -> dict[str, Any]:
    if not viewer_manifest_path.exists():
        return {
            "schema_version": "real-drawing-ifc-solver-exact-reconstruction-plan.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_viewer_manifest": str(viewer_manifest_path),
            "source_intake_queue": str(intake_queue_path),
            "contract_pass": False,
            "reason_code": "ERR_REAL_DRAWING_VIEWER_MANIFEST_MISSING",
            "summary": {"ifc_asset_count": 0, "blocked_count": 0},
            "ifc_reconstruction_items": [],
        }
    viewer_manifest = _load_json(viewer_manifest_path)
    intake_queue = _load_json_if_exists(intake_queue_path)
    items = [
        _plan_row(asset_ref, intake_row, viewer_asset)
        for asset_ref, intake_row, viewer_asset in _build_asset_ref_rows(viewer_manifest, intake_queue)
    ]
    blocker_counts = Counter(str(item.get("blocker_family") or "") for item in items)
    reason_counts = Counter(str(item.get("blocker_reason_code") or "") for item in items)
    proxy_node_total = sum(_safe_int(item.get("metrics", {}).get("proxy_node_count", 0)) for item in items)
    proxy_edge_total = sum(_safe_int(item.get("metrics", {}).get("proxy_edge_count", 0)) for item in items)
    structural_total = sum(_safe_int(item.get("metrics", {}).get("structural_entity_count", 0)) for item in items)
    return {
        "schema_version": "real-drawing-ifc-solver-exact-reconstruction-plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_viewer_manifest": str(viewer_manifest_path),
        "source_intake_queue": str(intake_queue_path),
        "contract_pass": True,
        "reason_code": "PASS_IFC_RECONSTRUCTION_PLAN_OPEN",
        "summary": {
            "ifc_asset_count": len(items),
            "solver_exact_ready_count": sum(1 for item in items if bool(item.get("reconstruction_ready", False))),
            "blocked_count": sum(1 for item in items if bool(item.get("commercial_claim_blocked", False))),
            "node_glyph_fallback_count": reason_counts.get("ERR_IFC_PROXY_NODE_GLYPH_FALLBACK", 0),
            "relationship_coverage_gap_count": reason_counts.get("ERR_IFC_PROXY_RELATIONSHIP_COVERAGE_GAP", 0),
            "geometry_material_load_adapter_required_count": blocker_counts.get(
                "ifc_geometry_material_load_solver_exact_adapter_required", 0
            ),
            "proxy_node_count_total": proxy_node_total,
            "proxy_edge_count_total": proxy_edge_total,
            "structural_entity_count_total": structural_total,
            "blocker_family_counts": dict(sorted(blocker_counts.items())),
            "blocker_reason_counts": dict(sorted(reason_counts.items())),
        },
        "ifc_reconstruction_items": items,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    items = report.get("ifc_reconstruction_items") if isinstance(report.get("ifc_reconstruction_items"), list) else []
    lines = [
        "# Real Drawing IFC Solver-Exact Reconstruction Plan",
        "",
        f"- Contract: {report.get('reason_code')}",
        f"- IFC assets: {summary.get('ifc_asset_count', 0)}",
        f"- Blocked assets: {summary.get('blocked_count', 0)}",
        f"- Node-glyph fallback: {summary.get('node_glyph_fallback_count', 0)}",
        f"- Relationship coverage gaps: {summary.get('relationship_coverage_gap_count', 0)}",
        "",
        "## Reconstruction Queue",
        "",
    ]
    if not items:
        lines.append("No IFC reconstruction items are open.")
        return "\n".join(lines)
    lines.extend(
        [
            "| Asset | Blocker | Edges / Structural | Edge Coverage | Required Evidence |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for item in items:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        evidence = ", ".join(str(value) for value in (item.get("required_evidence") or [])[:3])
        lines.append(
            "| {asset} | {reason} | {edges}/{structural} | {ratio} | {evidence} |".format(
                asset=item.get("asset_ref", ""),
                reason=item.get("blocker_reason_code", ""),
                edges=metrics.get("proxy_edge_count", 0),
                structural=metrics.get("structural_entity_count", 0),
                ratio=metrics.get("edge_coverage_ratio", 0),
                evidence=evidence.replace("|", "/"),
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer-manifest", type=Path, default=DEFAULT_VIEWER_MANIFEST)
    parser.add_argument("--intake-queue", type=Path, default=DEFAULT_INTAKE_QUEUE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true", help="Print the reconstruction plan JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_reconstruction_plan(args.viewer_manifest, args.intake_queue)
    _write_json(args.out, report)
    _write_text(args.out_md, render_markdown(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if bool(report.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
