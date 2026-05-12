from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any

from implementation.phase1.real_drawing_structure_viewer_preset import (
    STRUCTURE_VIEWER_HREF,
    STRUCTURE_VIEWER_PRESET_KEY,
    write_structure_viewer_sidecar,
)


DEFAULT_INTAKE_QUEUE = Path("tmp/real_drawing_private_corpus/model_optimization_intake_queue.json")
DEFAULT_OUT_HTML = Path("tmp/real_drawing_private_corpus/webviewer/real_drawing_3d_registry.html")
DEFAULT_OUT_SUMMARY = Path("tmp/real_drawing_private_corpus/webviewer/real_drawing_3d_registry_summary.json")
DEFAULT_OUT_VIEWER_SIDECAR = Path("src/structure-viewer/index.real_drawing_private.data.js")
DEFAULT_SOLVER_EXACT_PROMOTION_QUEUE = Path(
    "implementation/phase1/commercialization_status/real_drawing_solver_exact_promotion_queue.json"
)
DEFAULT_FULL_DETAIL_LOD_MANIFEST = Path(
    "implementation/phase1/commercialization_status/real_drawing_full_detail_lod_manifest.json"
)
DEFAULT_MAX_SEGMENTS_PER_ASSET = 1800
DEFAULT_MAX_PROXY_NODES = 900
DEFAULT_MAX_PROXY_EDGES = 1800
IFC_LOAD_RECEIPT_ID = "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    if text.endswith("\n"):
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _color_for(text: str) -> str:
    palette = (
        "#0f766e",
        "#2563eb",
        "#b45309",
        "#be123c",
        "#4d7c0f",
        "#7c3aed",
        "#0369a1",
        "#a16207",
        "#c2410c",
    )
    return palette[_stable_hash(text or "default") % len(palette)]


def _candidate_path(reference: Any, *, base_dir: Path) -> Path | None:
    text = str(reference or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate if candidate.exists() and candidate.is_file() else None
    if candidate.exists() and candidate.is_file():
        return candidate
    joined = base_dir / candidate
    return joined if joined.exists() and joined.is_file() else None


def _graph_reference(row: dict[str, Any]) -> str:
    for key in (
        "solver_graph_model_json",
        "archive_solver_graph_model_json",
        "archive_preview_model_json",
        "ifc_proxy_graph_json",
    ):
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    artifacts = row.get("hard_evidence_artifacts") if isinstance(row.get("hard_evidence_artifacts"), dict) else {}
    return str(artifacts.get("model_json", "") or "").strip()


def _full_detail_lod_by_asset(manifest_path: Path | None) -> dict[str, dict[str, Any]]:
    if manifest_path is None:
        return {}
    manifest = _load_json(manifest_path)
    items = manifest.get("lod_items") if isinstance(manifest.get("lod_items"), list) else []
    return {
        str(item.get("asset_ref") or ""): item
        for item in items
        if isinstance(item, dict) and str(item.get("asset_ref") or "")
    }


def _compact_lod_evidence(item: dict[str, Any], *, expected_full_detail_segment_count: int) -> dict[str, Any]:
    full_detail_segment_count = _safe_int(item.get("full_detail_segment_count"), 0)
    viewer_sample_segment_count = _safe_int(item.get("viewer_sample_segment_count"), 0)
    contract_pass = (
        bool(item.get("contract_pass", False))
        and bool(item.get("full_detail_lod_ready", False))
        and full_detail_segment_count >= expected_full_detail_segment_count
        and viewer_sample_segment_count > 0
    )
    return {
        "contract_pass": contract_pass,
        "reason_code": str(
            item.get("reason_code")
            or ("PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED" if contract_pass else "ERR_FULL_DETAIL_LOD_EVIDENCE_INCOMPLETE")
        ),
        "lod_policy": str(item.get("lod_policy") or ""),
        "full_detail_segment_count": full_detail_segment_count,
        "viewer_sample_segment_count": viewer_sample_segment_count,
        "sample_ratio": _safe_float(item.get("sample_ratio"), 0.0),
        "closure_evidence": [
            str(value)
            for value in (item.get("closure_evidence") or [])
            if str(value)
        ][:8],
    }


def _point_from_node(row: dict[str, Any]) -> list[float] | None:
    x = _safe_float(row.get("x"), math.nan)
    y = _safe_float(row.get("y"), math.nan)
    z = _safe_float(row.get("z"), math.nan)
    if not all(math.isfinite(value) for value in (x, y, z)):
        return None
    return [round(x, 4), round(y, 4), round(z, 4)]


def _sample_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or len(rows) <= limit:
        return rows
    step = len(rows) / float(limit)
    return [rows[min(len(rows) - 1, int(index * step))] for index in range(limit)]


def _model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model")
    return model if isinstance(model, dict) else payload


def _is_ifc_solver_graph_draft(payload: dict[str, Any]) -> bool:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    return (
        str(payload.get("schema_version") or "") == "real-drawing-ifc-solver-graph-draft.v1"
        or str(model.get("geometry_scope") or "").startswith("ifc_axis_or_body_member_extents")
        or str(model.get("geometry_scope") or "") == "placement_origin_axis_marker_not_member_extents"
    )


def _ifc_solver_graph_missing_member_extents(payload: dict[str, Any]) -> bool:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    geometry_scope = str(model.get("geometry_scope") or "")
    if geometry_scope == "placement_origin_axis_marker_not_member_extents":
        return True
    fallback_count = _safe_int(metrics.get("placement_marker_fallback_count"), 0)
    member_extent_count = _safe_int(metrics.get("member_extent_element_count"), 0)
    if member_extent_count <= 0:
        return True
    if fallback_count <= 0:
        return False
    source_shape_missing_count = _safe_int(metrics.get("placement_marker_fallback_source_shape_missing_count"), 0)
    unresolved_count = _safe_int(
        metrics.get(
            "placement_marker_fallback_unresolved_count",
            max(0, fallback_count - source_shape_missing_count),
        ),
        max(0, fallback_count - source_shape_missing_count),
    )
    coverage_ratio = _safe_float(metrics.get("member_extent_coverage_ratio"), 0.0)
    return not (
        unresolved_count <= 0
        and source_shape_missing_count == fallback_count
        and coverage_ratio >= 0.99
    )


def _ifc_source_quality_flags(payload: dict[str, Any]) -> list[str]:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    if _safe_int(metrics.get("placement_marker_fallback_source_shape_missing_count"), 0) > 0:
        return ["ifc_source_shape_missing_partial"]
    return []


def _solver_graph_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    receipts = payload.get("evidence_receipts") if isinstance(payload.get("evidence_receipts"), dict) else {}
    receipt = receipts.get("solver_graph_json_npz_receipt")
    return receipt if isinstance(receipt, dict) else {}


def _ifc_geometry_exact_ready(
    payload: dict[str, Any],
    *,
    metrics: dict[str, Any],
    geometry_available: bool,
) -> bool:
    if not geometry_available or not _is_ifc_solver_graph_draft(payload):
        return False
    if _ifc_solver_graph_missing_member_extents(payload):
        return False
    member_extent_count = _safe_int(metrics.get("member_extent_element_count"), 0)
    coverage_ratio = _safe_float(metrics.get("member_extent_coverage_ratio"), 0.0)
    unresolved_count = _safe_int(metrics.get("placement_marker_fallback_unresolved_count"), 0)
    return member_extent_count > 0 and coverage_ratio >= 0.99 and unresolved_count <= 0


def _ifc_load_model_status(payload: dict[str, Any]) -> str:
    if not _is_ifc_solver_graph_draft(payload):
        return "not_applicable"
    receipt = _solver_graph_receipt(payload)
    open_dependencies = [str(value) for value in (receipt.get("open_dependencies") or []) if str(value)]
    if IFC_LOAD_RECEIPT_ID in set(open_dependencies):
        return "source_ifc_load_model_missing"
    if receipt:
        return "ifc_load_model_ready"
    return "ifc_load_model_unknown"


def _geometry_claim_status(
    *,
    solver_exact: bool,
    is_ifc_solver_graph_draft: bool,
    ifc_geometry_exact_ready: bool,
    is_proxy_graph: bool,
) -> str:
    if solver_exact:
        return "solver_exact"
    if ifc_geometry_exact_ready:
        return "ifc_geometry_exact_ready"
    if is_ifc_solver_graph_draft:
        return "ifc_geometry_draft_incomplete"
    if is_proxy_graph:
        return "proxy_preview"
    return "preview"


def _extract_xyz_segments(payload: dict[str, Any], *, max_segments: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    model = _model_payload(payload)
    nodes = [row for row in (model.get("nodes") or []) if isinstance(row, dict)]
    elements = [row for row in (model.get("elements") or []) if isinstance(row, dict)]
    node_points: dict[str, list[float]] = {}
    for node in nodes:
        node_id = str(node.get("id", "") or "").strip()
        point = _point_from_node(node)
        if node_id and point is not None:
            node_points[node_id] = point
    segments: list[dict[str, Any]] = []
    for element in elements:
        raw_ids = element.get("node_ids") if isinstance(element.get("node_ids"), list) else []
        node_ids = [str(node_id).strip() for node_id in raw_ids if str(node_id).strip()]
        if len(node_ids) < 2:
            continue
        pairs = list(zip(node_ids, node_ids[1:]))
        if len(node_ids) > 2:
            pairs.append((node_ids[-1], node_ids[0]))
        family = str(element.get("family") or element.get("type") or "element")
        for source, target in pairs:
            p0 = node_points.get(source)
            p1 = node_points.get(target)
            if p0 is None or p1 is None:
                continue
            segments.append(
                {
                    "p0": p0,
                    "p1": p1,
                    "family": family,
                    "color": _color_for(family),
                }
            )
    return _sample_rows(segments, max_segments), {
        "node_count": len(nodes),
        "element_count": len(elements),
        "renderable_segment_count": len(segments),
    }


def _proxy_node_point(node_id: str, index: int, kind: str) -> list[float]:
    layer = (_stable_hash(kind or "node") % 9) - 4
    angle = (index * 2.399963229728653) + ((_stable_hash(node_id) % 180) / 180.0)
    radius = 12.0 + math.sqrt(index + 1) * 1.35 + abs(layer) * 1.8
    return [
        round(math.cos(angle) * radius, 4),
        round(math.sin(angle) * radius, 4),
        round(layer * 5.0 + ((index % 7) - 3) * 0.45, 4),
    ]


def _proxy_node_model_point(node: dict[str, Any]) -> list[float] | None:
    point = _point_from_node(node)
    if point is None:
        return None
    return point


def _extract_proxy_segments(
    payload: dict[str, Any],
    *,
    max_nodes: int,
    max_edges: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    nodes = [row for row in (payload.get("nodes") or []) if isinstance(row, dict)]
    edges = [row for row in (payload.get("edges") or []) if isinstance(row, dict)]
    selected_ids: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        for key in ("source", "target"):
            node_id = str(edge.get(key, "") or "").strip()
            if node_id and node_id not in seen:
                seen.add(node_id)
                selected_ids.append(node_id)
            if len(selected_ids) >= max_nodes:
                break
        if len(selected_ids) >= max_nodes:
            break
    if len(selected_ids) < max_nodes:
        for node in nodes:
            node_id = str(node.get("id", "") or "").strip()
            if node_id and node_id not in seen:
                seen.add(node_id)
                selected_ids.append(node_id)
            if len(selected_ids) >= max_nodes:
                break
    node_by_id = {str(row.get("id", "") or ""): row for row in nodes}
    coords: dict[str, list[float]] = {}
    for index, node_id in enumerate(selected_ids):
        node = node_by_id.get(node_id, {})
        kind = str(node.get("proxy_node_kind") or node.get("ifc_entity_type") or "node")
        coords[node_id] = _proxy_node_model_point(node) or _proxy_node_point(node_id, index, kind)
    segments: list[dict[str, Any]] = []
    for edge in edges:
        source = str(edge.get("source", "") or "").strip()
        target = str(edge.get("target", "") or "").strip()
        p0 = coords.get(source)
        p1 = coords.get(target)
        if p0 is None or p1 is None:
            continue
        family = str(edge.get("relationship") or "proxy-edge")
        segments.append(
            {
                "p0": p0,
                "p1": p1,
                "family": family,
                "color": _color_for(family),
            }
        )
        if len(segments) >= max_edges:
            break
    if not segments:
        for node_id in selected_ids:
            p0 = coords.get(node_id)
            if p0 is None:
                continue
            node = node_by_id.get(node_id, {})
            family = str(node.get("proxy_node_kind") or node.get("ifc_entity_type") or "proxy-node")
            p1 = [round(p0[0] + 0.7, 4), round(p0[1] + 0.7, 4), round(p0[2] + 0.7, 4)]
            segments.append(
                {
                    "p0": p0,
                    "p1": p1,
                    "family": family,
                    "color": _color_for(family),
                }
            )
            if len(segments) >= max_edges:
                break
    return segments, {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "renderable_segment_count": len(segments),
    }


def _build_asset_payload(
    row: dict[str, Any],
    *,
    index: int,
    base_dir: Path,
    full_detail_lod_by_asset: dict[str, dict[str, Any]],
    max_segments_per_asset: int,
    max_proxy_nodes: int,
    max_proxy_edges: int,
) -> dict[str, Any]:
    asset_ref = f"RD-{index:03d}"
    graph_path = _candidate_path(_graph_reference(row), base_dir=base_dir)
    payload = _load_json(graph_path) if graph_path else {}
    is_proxy_graph = bool(isinstance(payload.get("nodes"), list) and isinstance(payload.get("edges"), list) and not payload.get("model"))
    is_ifc_solver_graph_draft = _is_ifc_solver_graph_draft(payload)
    if is_proxy_graph:
        segments, metrics = _extract_proxy_segments(payload, max_nodes=max_proxy_nodes, max_edges=max_proxy_edges)
        geometry_mode = "ifc_proxy_topology_3d_layout"
        graph_source_kind = "ifc_proxy_graph"
    else:
        segments, metrics = _extract_xyz_segments(payload, max_segments=max_segments_per_asset)
        geometry_mode = "solver_topology_xyz"
        graph_source_kind = "ifc_solver_graph_draft" if is_ifc_solver_graph_draft else "solver_graph"
        if not segments and payload.get("edges"):
            segments, metrics = _extract_proxy_segments(payload, max_nodes=max_proxy_nodes, max_edges=max_proxy_edges)
            geometry_mode = "proxy_topology_3d_layout"
            graph_source_kind = "proxy_graph_fallback"
    source_metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    metrics = {**source_metrics, **metrics}
    route = str(row.get("optimization_route", "") or "")
    status = str(row.get("optimization_status", "") or "")
    solver_exact = bool(row.get("solver_exact", False))
    raw_renderable_count = _safe_int(metrics.get("renderable_segment_count", len(segments)))
    ifc_geometry_exact_ready = _ifc_geometry_exact_ready(
        payload,
        metrics=metrics,
        geometry_available=bool(segments),
    )
    geometry_claim_status = _geometry_claim_status(
        solver_exact=solver_exact,
        is_ifc_solver_graph_draft=is_ifc_solver_graph_draft,
        ifc_geometry_exact_ready=ifc_geometry_exact_ready,
        is_proxy_graph=is_proxy_graph,
    )
    load_model_status = (
        _ifc_load_model_status(payload)
        if is_ifc_solver_graph_draft
        else "solver_exact_source_model"
        if solver_exact
        else "not_applicable"
    )
    load_model_ready = load_model_status in {"ifc_load_model_ready", "solver_exact_source_model"}
    analysis_claim_ready = bool(solver_exact or (ifc_geometry_exact_ready and load_model_ready))
    claim_quality_flags = (
        ["ifc_load_model_missing"]
        if ifc_geometry_exact_ready and load_model_status == "source_ifc_load_model_missing"
        else []
    )
    source_quality_flags = _ifc_source_quality_flags(payload) if is_ifc_solver_graph_draft else []
    lod_evidence = (
        _compact_lod_evidence(
            full_detail_lod_by_asset.get(asset_ref, {}),
            expected_full_detail_segment_count=raw_renderable_count,
        )
        if raw_renderable_count > len(segments)
        else {}
    )
    lod_evidence_ready = bool(lod_evidence.get("contract_pass", False))
    quality_flags: list[str] = []
    if is_proxy_graph:
        quality_flags.append("proxy_layout_not_true_geometry")
        if _safe_int(metrics.get("edge_count", 0)) <= 0 and segments:
            quality_flags.append("proxy_node_glyph_fallback")
    if is_ifc_solver_graph_draft and _ifc_solver_graph_missing_member_extents(payload):
        quality_flags.append("ifc_solver_graph_draft_not_member_extents")
    if raw_renderable_count > len(segments) and not lod_evidence_ready:
        quality_flags.append("sampled_dense_model")
    if len(segments) < 10 and not solver_exact:
        quality_flags.append("sparse_preview")
    if not solver_exact:
        quality_flags.append("not_solver_exact")
    warning_label = ""
    if "proxy_layout_not_true_geometry" in quality_flags:
        warning_label = "proxy layout"
    elif "ifc_solver_graph_draft_not_member_extents" in quality_flags:
        warning_label = "IFC draft"
    elif "ifc_load_model_missing" in claim_quality_flags:
        warning_label = "load missing"
    elif source_quality_flags:
        warning_label = "IFC source"
    elif "sampled_dense_model" in quality_flags:
        warning_label = "sampled"
    elif "sparse_preview" in quality_flags:
        warning_label = "sparse"
    return {
        "asset_ref": asset_ref,
        "file_type": str(row.get("file_type", "") or ""),
        "route": route,
        "status": status,
        "solver_exact": solver_exact,
        "model_asset_count": _safe_int(row.get("model_asset_count", 0)),
        "geometry_mode": geometry_mode,
        "graph_source_kind": graph_source_kind,
        "geometry_available": bool(segments),
        "geometry_exact_ready": bool(solver_exact or ifc_geometry_exact_ready),
        "ifc_geometry_exact_ready": ifc_geometry_exact_ready,
        "geometry_claim_status": geometry_claim_status,
        "load_model_status": load_model_status,
        "load_model_ready": load_model_ready,
        "analysis_claim_ready": analysis_claim_ready,
        "segment_count": len(segments),
        "metrics": metrics,
        "quality_flags": quality_flags,
        "source_quality_flags": source_quality_flags,
        "claim_quality_flags": claim_quality_flags,
        "warning_label": warning_label,
        "segments": segments,
        **({"lod_evidence": lod_evidence} if lod_evidence_ready else {}),
    }


def _attach_viewer_sidecar_rebuild_receipts(
    registry: dict[str, Any],
    *,
    out_viewer_sidecar: Path | None,
) -> None:
    sidecar_ready = bool(out_viewer_sidecar and out_viewer_sidecar.exists() and out_viewer_sidecar.stat().st_size > 0)
    sidecar_path = str(out_viewer_sidecar) if out_viewer_sidecar is not None else ""
    for asset in registry.get("assets") or []:
        if not isinstance(asset, dict) or str(asset.get("file_type") or "").lower() != ".ifc":
            continue
        contract_pass = (
            sidecar_ready
            and bool(asset.get("geometry_available", False))
            and str(asset.get("graph_source_kind") or "") == "ifc_solver_graph_draft"
            and _safe_int(asset.get("segment_count", 0)) > 0
        )
        receipts = asset.setdefault("evidence_receipts", {})
        if not isinstance(receipts, dict):
            receipts = {}
            asset["evidence_receipts"] = receipts
        receipts["viewer_sidecar_rebuild_receipt"] = {
            "contract_pass": contract_pass,
            "reason_code": (
                "PASS_VIEWER_SIDECAR_REBUILT_WITH_IFC_SOLVER_GRAPH_DRAFT"
                if contract_pass
                else "ERR_VIEWER_SIDECAR_REBUILD_MISSING_IFC_SOLVER_GRAPH_DRAFT"
            ),
            "viewer_sidecar": sidecar_path,
            "structure_viewer_preset": STRUCTURE_VIEWER_PRESET_KEY,
            "asset_ref": str(asset.get("asset_ref") or ""),
            "geometry_mode": str(asset.get("geometry_mode") or ""),
            "graph_source_kind": str(asset.get("graph_source_kind") or ""),
            "segment_count": _safe_int(asset.get("segment_count", 0)),
            "solver_exact": bool(asset.get("solver_exact", False)),
            "geometry_claim_status": str(asset.get("geometry_claim_status") or ""),
            "load_model_status": str(asset.get("load_model_status") or ""),
            "analysis_claim_ready": bool(asset.get("analysis_claim_ready", False)),
            "commercial_claim_blocked": not bool(asset.get("analysis_claim_ready", asset.get("solver_exact", False))),
        }


def build_registry_payload(
    *,
    intake_queue_path: Path = DEFAULT_INTAKE_QUEUE,
    full_detail_lod_manifest_path: Path | None = None,
    max_segments_per_asset: int = DEFAULT_MAX_SEGMENTS_PER_ASSET,
    max_proxy_nodes: int = DEFAULT_MAX_PROXY_NODES,
    max_proxy_edges: int = DEFAULT_MAX_PROXY_EDGES,
) -> dict[str, Any]:
    queue_payload = _load_json(intake_queue_path)
    rows = [
        row
        for row in (queue_payload.get("queue") or [])
        if isinstance(row, dict) and bool(row.get("ready_for_optimized_drawing_generation", False))
    ]
    lod_by_asset = _full_detail_lod_by_asset(full_detail_lod_manifest_path)
    assets = [
        _build_asset_payload(
            row,
            index=index,
            base_dir=intake_queue_path.parent.parent.parent if intake_queue_path.parent.name == "real_drawing_private_corpus" else Path("."),
            full_detail_lod_by_asset=lod_by_asset,
            max_segments_per_asset=max_segments_per_asset,
            max_proxy_nodes=max_proxy_nodes,
            max_proxy_edges=max_proxy_edges,
        )
        for index, row in enumerate(rows, start=1)
    ]
    renderable_assets = [asset for asset in assets if asset["geometry_available"]]
    route_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for asset in assets:
        route_counts[str(asset["route"])] = route_counts.get(str(asset["route"]), 0) + 1
        status_counts[str(asset["status"])] = status_counts.get(str(asset["status"]), 0) + 1
    return {
        "schema_version": "real-drawing-private-3d-webviewer.v1",
        "surface": "private_local_derived_geometry",
        "asset_count": len(assets),
        "renderable_asset_count": len(renderable_assets),
        "solver_exact_asset_count": sum(1 for asset in assets if asset["solver_exact"]),
        "proxy_or_preview_asset_count": sum(1 for asset in assets if not asset["solver_exact"]),
        "route_counts": route_counts,
        "status_counts": status_counts,
        "assets": assets,
    }


def _summary_payload(
    registry: dict[str, Any],
    *,
    out_html: Path | None,
    out_viewer_sidecar: Path | None,
    promotion_queue_path: Path | None = None,
    promotion_queue: dict[str, Any] | None = None,
    full_detail_lod_manifest_path: Path | None = None,
) -> dict[str, Any]:
    promotion_summary = (
        promotion_queue.get("summary")
        if isinstance(promotion_queue, dict) and isinstance(promotion_queue.get("summary"), dict)
        else {}
    )
    return {
        "schema_version": registry["schema_version"],
        "surface": registry["surface"],
        "output_html": str(out_html) if out_html is not None else "",
        "output_viewer_sidecar": str(out_viewer_sidecar) if out_viewer_sidecar is not None else "",
        "solver_exact_promotion_queue": str(promotion_queue_path) if promotion_queue_path is not None else "",
        "full_detail_lod_manifest": str(full_detail_lod_manifest_path) if full_detail_lod_manifest_path is not None else "",
        "structure_viewer_preset": STRUCTURE_VIEWER_PRESET_KEY,
        "structure_viewer_href": STRUCTURE_VIEWER_HREF,
        "asset_count": _safe_int(registry.get("asset_count", 0)),
        "renderable_asset_count": _safe_int(registry.get("renderable_asset_count", 0)),
        "solver_exact_asset_count": _safe_int(registry.get("solver_exact_asset_count", 0)),
        "proxy_or_preview_asset_count": _safe_int(registry.get("proxy_or_preview_asset_count", 0)),
        "solver_exact_target_asset_count": _safe_int(promotion_summary.get("target_solver_exact_asset_count", 0)),
        "solver_exact_planned_unlock_batch_count": _safe_int(
            promotion_summary.get("planned_unlock_batch_count", 0)
        ),
        "solver_exact_planned_asset_count_after_unlock_batch": _safe_int(
            promotion_summary.get("planned_solver_exact_asset_count_after_unlock_batch", 0)
        ),
        "solver_exact_open_promotion_item_count": _safe_int(
            promotion_summary.get("promotion_candidate_count", 0)
        ),
        "route_counts": registry.get("route_counts") if isinstance(registry.get("route_counts"), dict) else {},
        "status_counts": registry.get("status_counts") if isinstance(registry.get("status_counts"), dict) else {},
        "assets": [
            {
                key: value
                for key, value in asset.items()
                if key != "segments"
            }
            for asset in (registry.get("assets") or [])
            if isinstance(asset, dict)
        ],
    }


def _render_html(registry: dict[str, Any]) -> str:
    payload_json = json.dumps(registry, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    title = "Real Drawing 3D Registry"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>
:root {{
  color-scheme: light;
  --ink:#17202a;
  --muted:#5f6f7a;
  --line:#d8e0e6;
  --panel:#f7f9fb;
  --accent:#0f766e;
  --accent-2:#2563eb;
  --paper:#ffffff;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background:#eef3f6;
  color:var(--ink);
}}
.app {{
  min-height:100vh;
  display:grid;
  grid-template-columns:minmax(260px, 360px) minmax(0, 1fr);
}}
.sidebar {{
  border-right:1px solid var(--line);
  background:var(--paper);
  padding:18px;
  overflow:auto;
  max-height:100vh;
}}
.brand {{
  display:flex;
  flex-direction:column;
  gap:6px;
  margin-bottom:16px;
}}
.kicker {{
  font-size:12px;
  font-weight:800;
  text-transform:uppercase;
  color:var(--accent);
}}
h1 {{
  font-size:24px;
  line-height:1.1;
  margin:0;
  letter-spacing:0;
}}
.meta-grid {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:8px;
  margin:14px 0;
}}
.metric {{
  border:1px solid var(--line);
  background:var(--panel);
  padding:10px;
  border-radius:8px;
}}
.metric strong {{
  display:block;
  font-size:20px;
  line-height:1;
}}
.metric span {{
  display:block;
  margin-top:5px;
  font-size:12px;
  color:var(--muted);
}}
.asset-list {{
  display:flex;
  flex-direction:column;
  gap:8px;
}}
.asset-button {{
  width:100%;
  border:1px solid var(--line);
  background:#fff;
  color:var(--ink);
  text-align:left;
  padding:10px;
  border-radius:8px;
  cursor:pointer;
}}
.asset-button:hover,
.asset-button.is-active {{
  border-color:var(--accent);
  box-shadow:0 0 0 2px rgba(15, 118, 110, .14);
}}
.asset-title {{
  display:flex;
  justify-content:space-between;
  gap:10px;
  font-weight:800;
}}
.asset-title span:last-child {{
  white-space:nowrap;
}}
.asset-detail {{
  margin-top:6px;
  color:var(--muted);
  font-size:12px;
  line-height:1.45;
}}
.stage {{
  min-width:0;
  display:grid;
  grid-template-rows:auto minmax(0, 1fr);
  max-height:100vh;
}}
.toolbar {{
  min-height:76px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:14px 18px;
  background:#fff;
  border-bottom:1px solid var(--line);
}}
.active-title {{
  font-weight:900;
  font-size:18px;
}}
.active-subtitle {{
  color:var(--muted);
  font-size:13px;
  margin-top:4px;
}}
.controls {{
  display:flex;
  gap:8px;
  flex-wrap:wrap;
  justify-content:flex-end;
}}
button.control {{
  border:1px solid var(--line);
  background:var(--panel);
  color:var(--ink);
  border-radius:8px;
  min-height:34px;
  padding:0 11px;
  font-weight:700;
  cursor:pointer;
}}
button.control:hover {{ border-color:var(--accent-2); }}
.canvas-wrap {{
  position:relative;
  min-height:0;
  background:linear-gradient(180deg, #f7fbfc, #e8eef2);
}}
canvas {{
  width:100%;
  height:100%;
  display:block;
}}
.hud {{
  position:absolute;
  left:16px;
  bottom:16px;
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  pointer-events:none;
}}
.chip {{
  background:rgba(255, 255, 255, .88);
  border:1px solid rgba(23, 32, 42, .12);
  border-radius:999px;
  padding:7px 10px;
  font-size:12px;
  color:var(--muted);
}}
.notice {{
  margin-top:10px;
  border:1px solid #f1c27d;
  background:#fff8eb;
  color:#7a4b10;
  border-radius:8px;
  padding:9px 10px;
  font-size:12px;
  line-height:1.45;
}}
@media (max-width: 860px) {{
  .app {{ grid-template-columns:1fr; }}
  .sidebar {{ max-height:none; border-right:0; border-bottom:1px solid var(--line); }}
  .stage {{ min-height:70vh; max-height:none; }}
  .toolbar {{ align-items:flex-start; flex-direction:column; }}
}}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="kicker">Private local registry</div>
      <h1>{html.escape(title)}</h1>
      <div class="asset-detail">Derived topology only. Raw drawings, source URLs, and private source paths are not embedded.</div>
    </div>
    <div class="meta-grid">
      <div class="metric"><strong id="asset-count">0</strong><span>registered assets</span></div>
      <div class="metric"><strong id="renderable-count">0</strong><span>renderable assets</span></div>
      <div class="metric"><strong id="solver-count">0</strong><span>solver exact</span></div>
      <div class="metric"><strong id="proxy-count">0</strong><span>proxy / preview</span></div>
    </div>
    <div class="asset-list" id="asset-list"></div>
  </aside>
  <main class="stage">
    <div class="toolbar">
      <div>
        <div class="active-title" id="active-title">No asset selected</div>
        <div class="active-subtitle" id="active-subtitle">Use the registry list to open a derived 3D topology view.</div>
      </div>
      <div class="controls">
        <button class="control" type="button" data-view="iso">Iso</button>
        <button class="control" type="button" data-view="top">Top</button>
        <button class="control" type="button" data-view="front">Front</button>
        <button class="control" type="button" id="reset-view">Reset</button>
      </div>
    </div>
    <div class="canvas-wrap">
      <canvas id="viewer"></canvas>
      <div class="hud" id="hud"></div>
    </div>
  </main>
</div>
<script>
const registryPayload = {payload_json};
const initialAssetIndex = Math.max(0, (registryPayload.assets || []).findIndex(asset => asset.solver_exact && asset.geometry_available));
const state = {{
  activeIndex: initialAssetIndex,
  rotX: -0.62,
  rotY: 0.78,
  zoom: 1,
  panX: 0,
  panY: 0,
  dragging: false,
  lastX: 0,
  lastY: 0,
}};
const canvas = document.getElementById('viewer');
const ctx = canvas.getContext('2d');
const assetList = document.getElementById('asset-list');
const activeTitle = document.getElementById('active-title');
const activeSubtitle = document.getElementById('active-subtitle');
const hud = document.getElementById('hud');
document.getElementById('asset-count').textContent = String(registryPayload.asset_count || 0);
document.getElementById('renderable-count').textContent = String(registryPayload.renderable_asset_count || 0);
document.getElementById('solver-count').textContent = String(registryPayload.solver_exact_asset_count || 0);
document.getElementById('proxy-count').textContent = String(registryPayload.proxy_or_preview_asset_count || 0);

function activeAsset() {{
  return (registryPayload.assets || [])[state.activeIndex] || null;
}}

function setView(view) {{
  if (view === 'top') {{
    state.rotX = -Math.PI / 2;
    state.rotY = 0;
  }} else if (view === 'front') {{
    state.rotX = 0;
    state.rotY = 0;
  }} else {{
    state.rotX = -0.62;
    state.rotY = 0.78;
  }}
  state.panX = 0;
  state.panY = 0;
  state.zoom = 1;
  draw();
}}

function buildList() {{
  assetList.innerHTML = '';
  (registryPayload.assets || []).forEach((asset, index) => {{
    const button = document.createElement('button');
    button.className = 'asset-button' + (index === state.activeIndex ? ' is-active' : '');
    button.type = 'button';
    const flags = asset.quality_flags || [];
    const claimFlags = (asset.claim_quality_flags || []).map(flag => `claim:${{flag}}`);
    const tierLabel = asset.solver_exact ? 'exact' : asset.geometry_claim_status === 'ifc_geometry_exact_ready' ? 'geometry' : 'proxy';
    const warning = asset.warning_label ? ` · ${{asset.warning_label}}` : '';
    button.innerHTML = `
      <div class="asset-title"><span>${{asset.asset_ref}}</span><span>${{tierLabel}}${{warning}}</span></div>
      <div class="asset-detail">${{asset.file_type || 'model'}} | ${{asset.status || 'ready'}}<br />segments=${{asset.segment_count || 0}} | mode=${{asset.geometry_mode || 'n/a'}}${{flags.length || claimFlags.length ? `<br />flags=${{[...flags, ...claimFlags].join(', ')}}` : ''}}</div>
    `;
    button.addEventListener('click', () => {{
      state.activeIndex = index;
      state.panX = 0;
      state.panY = 0;
      state.zoom = 1;
      buildList();
      draw();
    }});
    assetList.appendChild(button);
  }});
}}

function resizeCanvas() {{
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(320, Math.floor(rect.width * dpr));
  canvas.height = Math.max(320, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}}

function bounds(asset) {{
  const points = [];
  (asset.segments || []).forEach(segment => {{
    points.push(segment.p0, segment.p1);
  }});
  if (!points.length) return {{ center:[0,0,0], scale:1 }};
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  points.forEach(point => {{
    for (let i = 0; i < 3; i += 1) {{
      min[i] = Math.min(min[i], Number(point[i]) || 0);
      max[i] = Math.max(max[i], Number(point[i]) || 0);
    }}
  }});
  const center = [(min[0]+max[0])/2, (min[1]+max[1])/2, (min[2]+max[2])/2];
  const span = Math.max(max[0]-min[0], max[1]-min[1], max[2]-min[2], 1);
  return {{ center, scale:span }};
}}

function project(point, frame) {{
  let x = ((Number(point[0]) || 0) - frame.center[0]) / frame.scale;
  let y = ((Number(point[1]) || 0) - frame.center[1]) / frame.scale;
  let z = ((Number(point[2]) || 0) - frame.center[2]) / frame.scale;
  const cosY = Math.cos(state.rotY);
  const sinY = Math.sin(state.rotY);
  const x1 = x * cosY + z * sinY;
  const z1 = -x * sinY + z * cosY;
  const cosX = Math.cos(state.rotX);
  const sinX = Math.sin(state.rotX);
  const y2 = y * cosX - z1 * sinX;
  const z2 = y * sinX + z1 * cosX;
  const rect = canvas.getBoundingClientRect();
  const size = Math.min(rect.width, rect.height) * 0.78 * state.zoom;
  return {{
    x: rect.width / 2 + state.panX + x1 * size,
    y: rect.height / 2 + state.panY - y2 * size,
    z: z2,
  }};
}}

function drawAxes(frame) {{
  const axes = [
    {{ label:'X', color:'#be123c', p0:[0,0,0], p1:[frame.scale * .35,0,0] }},
    {{ label:'Y', color:'#0f766e', p0:[0,0,0], p1:[0,frame.scale * .35,0] }},
    {{ label:'Z', color:'#2563eb', p0:[0,0,0], p1:[0,0,frame.scale * .35] }},
  ];
  axes.forEach(axis => {{
    const p0 = project([frame.center[0], frame.center[1], frame.center[2]], frame);
    const p1 = project([frame.center[0] + axis.p1[0], frame.center[1] + axis.p1[1], frame.center[2] + axis.p1[2]], frame);
    ctx.strokeStyle = axis.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.stroke();
    ctx.fillStyle = axis.color;
    ctx.font = '700 12px Inter, sans-serif';
    ctx.fillText(axis.label, p1.x + 4, p1.y + 4);
  }});
}}

function draw() {{
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  const asset = activeAsset();
  if (!asset) return;
  const activeTierLabel = asset.solver_exact ? 'solver-exact' : asset.geometry_claim_status === 'ifc_geometry_exact_ready' ? 'geometry ready' : 'proxy/preview';
  activeTitle.textContent = `${{asset.asset_ref}} | ${{activeTierLabel}}`;
  activeSubtitle.textContent = `${{asset.file_type || 'model'}} | ${{asset.route || 'route'}} | ${{asset.geometry_mode || 'geometry'}}`;
  const flags = asset.quality_flags || [];
  const claimFlags = (asset.claim_quality_flags || []).map(flag => `claim:${{flag}}`);
  hud.innerHTML = `
    <span class="chip">segments ${{asset.segment_count || 0}}</span>
    <span class="chip">status ${{asset.status || 'ready'}}</span>
    ${{flags.length || claimFlags.length ? `<span class="chip">flags ${{[...flags, ...claimFlags].join(', ')}}</span>` : ''}}
    <span class="chip">drag rotate | wheel zoom</span>
  `;
  if (flags.includes('proxy_layout_not_true_geometry') || flags.includes('sampled_dense_model') || flags.includes('sparse_preview') || claimFlags.includes('claim:ifc_load_model_missing')) {{
    const notice = document.createElement('div');
    notice.className = 'notice';
    if (flags.includes('proxy_layout_not_true_geometry')) {{
      notice.textContent = 'This asset is an IFC proxy topology layout, not recovered architectural/structural coordinates.';
    }} else if (claimFlags.includes('claim:ifc_load_model_missing')) {{
      notice.textContent = 'IFC geometry is ready, but source load-model evidence is missing; analysis claims stay blocked.';
    }} else if (flags.includes('sampled_dense_model')) {{
      notice.textContent = 'This dense solver model is sampled for browser performance; use it for shape inspection, not element-by-element completeness.';
    }} else {{
      notice.textContent = 'This archive preview is sparse and may look like a small skeleton rather than a full drawing.';
    }}
    hud.appendChild(notice);
  }}
  const frame = bounds(asset);
  drawAxes(frame);
  const rows = (asset.segments || []).map(segment => {{
    const p0 = project(segment.p0, frame);
    const p1 = project(segment.p1, frame);
    return {{ segment, p0, p1, z:(p0.z + p1.z) / 2 }};
  }}).sort((a, b) => a.z - b.z);
  ctx.lineCap = 'round';
  rows.forEach(row => {{
    ctx.strokeStyle = row.segment.color || '#0f766e';
    ctx.globalAlpha = 0.72;
    ctx.lineWidth = asset.solver_exact ? 1.25 : 1;
    ctx.beginPath();
    ctx.moveTo(row.p0.x, row.p0.y);
    ctx.lineTo(row.p1.x, row.p1.y);
    ctx.stroke();
  }});
  ctx.globalAlpha = 1;
}}

canvas.addEventListener('pointerdown', event => {{
  state.dragging = true;
  state.lastX = event.clientX;
  state.lastY = event.clientY;
  canvas.setPointerCapture(event.pointerId);
}});
canvas.addEventListener('pointermove', event => {{
  if (!state.dragging) return;
  const dx = event.clientX - state.lastX;
  const dy = event.clientY - state.lastY;
  state.lastX = event.clientX;
  state.lastY = event.clientY;
  if (event.shiftKey) {{
    state.panX += dx;
    state.panY += dy;
  }} else {{
    state.rotY += dx * 0.008;
    state.rotX += dy * 0.008;
  }}
  draw();
}});
canvas.addEventListener('pointerup', event => {{
  state.dragging = false;
  canvas.releasePointerCapture(event.pointerId);
}});
canvas.addEventListener('wheel', event => {{
  event.preventDefault();
  const factor = event.deltaY < 0 ? 1.12 : 0.89;
  state.zoom = Math.min(8, Math.max(0.25, state.zoom * factor));
  draw();
}}, {{ passive:false }});
document.querySelectorAll('[data-view]').forEach(button => {{
  button.addEventListener('click', () => setView(button.getAttribute('data-view')));
}});
document.getElementById('reset-view').addEventListener('click', () => setView('iso'));
window.addEventListener('resize', resizeCanvas);
buildList();
resizeCanvas();
</script>
</body>
</html>
"""


def build_webviewer(
    *,
    intake_queue_path: Path = DEFAULT_INTAKE_QUEUE,
    out_html: Path | None = None,
    out_summary: Path = DEFAULT_OUT_SUMMARY,
    out_viewer_sidecar: Path | None = DEFAULT_OUT_VIEWER_SIDECAR,
    promotion_queue_path: Path | None = None,
    full_detail_lod_manifest_path: Path | None = None,
    max_segments_per_asset: int = DEFAULT_MAX_SEGMENTS_PER_ASSET,
    max_proxy_nodes: int = DEFAULT_MAX_PROXY_NODES,
    max_proxy_edges: int = DEFAULT_MAX_PROXY_EDGES,
) -> dict[str, Any]:
    registry = build_registry_payload(
        intake_queue_path=intake_queue_path,
        full_detail_lod_manifest_path=full_detail_lod_manifest_path,
        max_segments_per_asset=max_segments_per_asset,
        max_proxy_nodes=max_proxy_nodes,
        max_proxy_edges=max_proxy_edges,
    )
    promotion_queue = _load_json(promotion_queue_path) if promotion_queue_path is not None else {}
    if out_html is not None:
        _write_text(out_html, _render_html(registry))
    if out_viewer_sidecar is not None:
        write_structure_viewer_sidecar(out_viewer_sidecar, registry, promotion_queue=promotion_queue)
        _attach_viewer_sidecar_rebuild_receipts(registry, out_viewer_sidecar=out_viewer_sidecar)
        write_structure_viewer_sidecar(out_viewer_sidecar, registry, promotion_queue=promotion_queue)
    summary = _summary_payload(
        registry,
        out_html=out_html,
        out_viewer_sidecar=out_viewer_sidecar,
        promotion_queue_path=promotion_queue_path,
        promotion_queue=promotion_queue,
        full_detail_lod_manifest_path=full_detail_lod_manifest_path,
    )
    _write_text(out_summary, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the integrated structure-viewer preset for real drawing derived topology."
    )
    parser.add_argument("--intake-queue", default=str(DEFAULT_INTAKE_QUEUE))
    parser.add_argument(
        "--out-html",
        default="",
        help="Optional legacy standalone HTML output. Omit to keep the existing structure-viewer as the canonical UI.",
    )
    parser.add_argument("--out-summary", default=str(DEFAULT_OUT_SUMMARY))
    parser.add_argument("--out-viewer-sidecar", default=str(DEFAULT_OUT_VIEWER_SIDECAR))
    parser.add_argument(
        "--promotion-queue",
        default="",
        help="Optional solver-exact promotion queue JSON to embed as sanitized viewer metadata.",
    )
    parser.add_argument(
        "--full-detail-lod-manifest",
        default="",
        help=(
            "Optional full-detail LOD evidence manifest for sampled solver-exact assets. "
            f"Canonical path: {DEFAULT_FULL_DETAIL_LOD_MANIFEST}"
        ),
    )
    parser.add_argument("--max-segments-per-asset", type=int, default=DEFAULT_MAX_SEGMENTS_PER_ASSET)
    parser.add_argument("--max-proxy-nodes", type=int, default=DEFAULT_MAX_PROXY_NODES)
    parser.add_argument("--max-proxy-edges", type=int, default=DEFAULT_MAX_PROXY_EDGES)
    args = parser.parse_args()
    build_webviewer(
        intake_queue_path=Path(args.intake_queue),
        out_html=Path(args.out_html) if str(args.out_html).strip() else None,
        out_summary=Path(args.out_summary),
        out_viewer_sidecar=Path(args.out_viewer_sidecar) if str(args.out_viewer_sidecar).strip() else None,
        promotion_queue_path=Path(args.promotion_queue) if str(args.promotion_queue).strip() else None,
        full_detail_lod_manifest_path=(
            Path(args.full_detail_lod_manifest) if str(args.full_detail_lod_manifest).strip() else None
        ),
        max_segments_per_asset=args.max_segments_per_asset,
        max_proxy_nodes=args.max_proxy_nodes,
        max_proxy_edges=args.max_proxy_edges,
    )


if __name__ == "__main__":
    main()
