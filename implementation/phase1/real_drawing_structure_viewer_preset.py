from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


STRUCTURE_VIEWER_PRESET_KEY = "real_drawing_private_3d"
STRUCTURE_VIEWER_HREF = f"src/structure-viewer/index.html?preset={STRUCTURE_VIEWER_PRESET_KEY}"
STRUCTURE_VIEWER_SIDECAR_GLOBAL = "__STRUCTURE_VIEWER_PRESET_PAYLOADS__"


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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    if text.endswith("\n"):
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")


def quality_notice(asset: dict[str, Any]) -> str:
    flags = {str(flag) for flag in (asset.get("quality_flags") or [])}
    if "proxy_layout_not_true_geometry" in flags:
        return "IFC proxy topology layout; not recovered architectural/structural coordinates."
    if "sampled_dense_model" in flags:
        return "Dense solver model sampled for browser performance."
    if "sparse_preview" in flags:
        return "Sparse archive preview; shape may look like a small skeleton."
    return "Solver-derived topology segment."


def viewer_element_type(family: Any, geometry_mode: Any) -> str:
    label = f"{family or ''} {geometry_mode or ''}".lower()
    if "column" in label:
        return "column"
    if "brace" in label:
        return "brace"
    if "beam" in label or "bar" in label or "line" in label:
        return "beam"
    if "wall" in label:
        return "wall"
    if "slab" in label or "plate" in label or "shell" in label:
        return "slab"
    return "other"


def asset_bounds(asset: dict[str, Any]) -> tuple[list[float], list[float]]:
    points: list[list[float]] = []
    for segment in asset.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        for key in ("p0", "p1"):
            point = segment.get(key)
            if isinstance(point, list) and len(point) >= 3:
                points.append([_safe_float(point[0]), _safe_float(point[1]), _safe_float(point[2])])
    if not points:
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]
    mins = [min(point[index] for point in points) for index in range(3)]
    maxs = [max(point[index] for point in points) for index in range(3)]
    return mins, maxs


def asset_registry_row(asset: dict[str, Any]) -> dict[str, Any]:
    metrics = asset.get("metrics") if isinstance(asset.get("metrics"), dict) else {}
    quality_flags = [str(flag) for flag in (asset.get("quality_flags") or [])]
    return {
        "asset_ref": str(asset.get("asset_ref") or ""),
        "file_type": str(asset.get("file_type") or ""),
        "route": str(asset.get("route") or ""),
        "status": str(asset.get("status") or ""),
        "solver_exact": bool(asset.get("solver_exact", False)),
        "geometry_mode": str(asset.get("geometry_mode") or ""),
        "geometry_available": bool(asset.get("geometry_available", False)),
        "segment_count": _safe_int(asset.get("segment_count", 0)),
        "model_asset_count": _safe_int(asset.get("model_asset_count", 0)),
        "warning_label": str(asset.get("warning_label") or ""),
        "quality_flags": quality_flags,
        "quality_notice": quality_notice(asset),
        "node_count": _safe_int(metrics.get("node_count", metrics.get("proxy_node_count", 0))),
        "element_count": _safe_int(metrics.get("element_count", metrics.get("edge_count", 0))),
        "renderable_segment_count": _safe_int(metrics.get("renderable_segment_count", asset.get("segment_count", 0))),
    }


def registry_summary(registry: dict[str, Any], asset_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "asset_count": _safe_int(registry.get("asset_count", len(asset_rows))),
        "renderable_asset_count": _safe_int(registry.get("renderable_asset_count", 0)),
        "solver_exact_asset_count": _safe_int(registry.get("solver_exact_asset_count", 0)),
        "proxy_or_preview_asset_count": _safe_int(registry.get("proxy_or_preview_asset_count", 0)),
        "route_counts": registry.get("route_counts") if isinstance(registry.get("route_counts"), dict) else {},
        "status_counts": registry.get("status_counts") if isinstance(registry.get("status_counts"), dict) else {},
        "quality_flag_counts": {
            flag: sum(1 for row in asset_rows if flag in set(row.get("quality_flags") or []))
            for flag in sorted({flag for row in asset_rows for flag in (row.get("quality_flags") or [])})
        },
    }


def transform_point(point: Any, *, center: list[float], scale: float, offset_x: float, offset_y: float) -> list[float]:
    normalized = point if isinstance(point, list) and len(point) >= 3 else [0.0, 0.0, 0.0]
    return [
        round((_safe_float(normalized[0]) - center[0]) * scale + offset_x, 4),
        round((_safe_float(normalized[1]) - center[1]) * scale + offset_y, 4),
        round((_safe_float(normalized[2]) - center[2]) * scale, 4),
    ]


def register_viewer_node(
    point: list[float],
    *,
    node_index_by_key: dict[str, int],
    nodes: list[dict[str, Any]],
) -> int:
    key = "|".join(f"{value:.4f}" for value in point)
    existing = node_index_by_key.get(key)
    if existing is not None:
        return existing
    node_id = len(nodes)
    nodes.append(
        {
            "id": node_id,
            "x": point[0],
            "y": point[1],
            "z": point[2],
            "dx": 0,
            "dy": 0,
            "dz": 0,
            "disp_mag": 0,
            "stress_vm": 0,
            "dcr": 0,
            "axial": 0,
            "moment": 0,
            "shear": 0,
        }
    )
    node_index_by_key[key] = node_id
    return node_id


def build_structure_viewer_preset_payload(registry: dict[str, Any]) -> dict[str, Any]:
    assets = [asset for asset in (registry.get("assets") or []) if isinstance(asset, dict)]
    asset_rows = [asset_registry_row(asset) for asset in assets]
    columns = max(1, math.ceil(math.sqrt(max(len(assets), 1))))
    tile_spacing = 48.0
    nodes: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    node_index_by_key: dict[str, int] = {}

    for asset_index, asset in enumerate(assets):
        asset_ref = str(asset.get("asset_ref") or f"RD-{asset_index + 1:03d}")
        segments = [segment for segment in (asset.get("segments") or []) if isinstance(segment, dict)]
        if not segments:
            continue
        mins, maxs = asset_bounds(asset)
        spans = [maxs[index] - mins[index] for index in range(3)]
        max_span = max(max(spans), 1.0)
        scale = 32.0 / max_span
        center = [(mins[index] + maxs[index]) / 2.0 for index in range(3)]
        column = asset_index % columns
        row = asset_index // columns
        offset_x = column * tile_spacing
        offset_y = row * tile_spacing
        warning_label = str(asset.get("warning_label") or "").strip()
        group_name = f"{asset_ref} · {warning_label or str(asset.get('geometry_mode') or 'derived topology')}"
        element_ids: list[str] = []
        group_node_ids: set[int] = set()
        notice = quality_notice(asset)
        for segment_index, segment in enumerate(segments, start=1):
            p0 = transform_point(segment.get("p0"), center=center, scale=scale, offset_x=offset_x, offset_y=offset_y)
            p1 = transform_point(segment.get("p1"), center=center, scale=scale, offset_x=offset_x, offset_y=offset_y)
            n0 = register_viewer_node(p0, node_index_by_key=node_index_by_key, nodes=nodes)
            n1 = register_viewer_node(p1, node_index_by_key=node_index_by_key, nodes=nodes)
            group_node_ids.update((n0, n1))
            family = str(segment.get("family") or asset.get("geometry_mode") or "derived")
            element_id = f"{asset_ref}:S{segment_index:04d}"
            element_ids.append(element_id)
            elements.append(
                {
                    "id": element_id,
                    "type": viewer_element_type(family, asset.get("geometry_mode")),
                    "family": family,
                    "node_ids": [n0, n1],
                    "member_id": asset_ref,
                    "section": str(asset.get("geometry_mode") or "--"),
                    "color": str(segment.get("color") or _color_for(family)),
                    "dcr": 0,
                    "axial": 0,
                    "moment": 0,
                    "shear": 0,
                    "overlay_scope": "real_drawing_private_corpus",
                    "story_band_label": asset_ref,
                    "zone_label": str(asset.get("file_type") or "--"),
                    "action_name": str(asset.get("route") or "--"),
                    "optimization_meaning_label": (
                        f"{asset_ref} | solver_exact={bool(asset.get('solver_exact'))} | "
                        f"segments={len(segments)}"
                    ),
                    "before_after_snapshot_note": notice,
                    "review_case_id": asset_ref,
                    "review_row_label": warning_label or str(asset.get("status") or "--"),
                    "review_summary_label": (
                        f"mode={asset.get('geometry_mode') or '--'} | "
                        f"status={asset.get('status') or '--'} | "
                        f"flags={', '.join(str(flag) for flag in (asset.get('quality_flags') or [])) or 'none'}"
                    ),
                    "group_names": [group_name],
                    "group_label": group_name,
                }
            )
        groups.append(
            {
                "name": group_name,
                "element_ids": element_ids,
                "element_ids_head": element_ids[:8],
                "element_count": len(element_ids),
                "node_count": len(group_node_ids),
                "physical_line_span": round(max_span, 4),
            }
        )
        members.append(
            {
                "id": asset_ref,
                "element_ids": element_ids,
                "element_count": len(element_ids),
                "note": notice,
            }
        )

    root_payload = {
        "schema_version": "real-drawing-private-3d-viewer-preset.v1",
        "run_id": "real_drawing_private_3d_gallery",
        "source": {
            "path": "private local derived topology sidecar",
            "source_family": "real_drawing_private_corpus",
            "format": "derived_segment_gallery",
        },
        "meta": {
            "name": "Real Drawing Private 3D Gallery",
            "source_label": "private real drawing derived topology",
            "source_mode": "private_derived_topology",
            "real_drawing_asset_count": _safe_int(registry.get("asset_count", 0)),
            "real_drawing_renderable_asset_count": _safe_int(registry.get("renderable_asset_count", 0)),
            "real_drawing_solver_exact_asset_count": _safe_int(registry.get("solver_exact_asset_count", 0)),
            "real_drawing_proxy_or_preview_asset_count": _safe_int(registry.get("proxy_or_preview_asset_count", 0)),
            "real_drawing_registry_summary": registry_summary(registry, asset_rows),
            "real_drawing_asset_registry": asset_rows,
        },
        "model": {
            "nodes": nodes,
            "elements": elements,
            "metadata": {
                "groups": groups,
                "members": members,
                "structure_type": [{"raw": "real drawing derived topology gallery"}],
                "length_units": [{"raw": "normalized per asset tile"}],
            },
        },
    }
    return {
        STRUCTURE_VIEWER_PRESET_KEY: {
            "label": "private real drawing derived topology",
            "report_name": "real_drawing_private_3d_gallery",
            "path": "private local derived topology sidecar",
            "payload": root_payload,
        }
    }


def serialize_structure_viewer_sidecar(registry: dict[str, Any]) -> str:
    payload = build_structure_viewer_preset_payload(registry)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f"window.{STRUCTURE_VIEWER_SIDECAR_GLOBAL}={serialized};\n"


def write_structure_viewer_sidecar(path: Path, registry: dict[str, Any]) -> None:
    _write_text(path, serialize_structure_viewer_sidecar(registry))
