#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = REPO_ROOT / "implementation/phase1/_vendor"

REASONS = {
    "PASS": "rhino 3dm baseline bridge passed",
    "ERR_RHINO_IMPORT": "failed to import rhino3dm",
    "ERR_FILE_MISSING": "input rhino 3dm file missing",
    "ERR_READ_FAIL": "failed to read rhino 3dm model",
    "ERR_NO_CURVES": "no supported curve geometry found",
}


def _load_rhino3dm():
    if VENDOR_DIR.exists():
        vendor_path = str(VENDOR_DIR)
        if vendor_path not in sys.path:
            sys.path.insert(0, vendor_path)
    try:
        import rhino3dm  # type: ignore
    except Exception as exc:  # pragma: no cover - import error path
        raise RuntimeError("failed to import rhino3dm") from exc
    return rhino3dm


def _point_key(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return (round(point[0], 6), round(point[1], 6), round(point[2], 6))


def _clean_points(points: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    cleaned: list[tuple[float, float, float]] = []
    for point in points:
        rounded = _point_key(point)
        if cleaned and rounded == cleaned[-1]:
            continue
        cleaned.append(rounded)
    return cleaned


def _sample_nurbs_curve(curve: Any, sample_count: int) -> list[tuple[float, float, float]]:
    domain = getattr(curve, "Domain", None)
    point_at = getattr(curve, "PointAt", None)
    if domain is None or point_at is None:
        return []
    t0 = float(getattr(domain, "T0", 0.0))
    t1 = float(getattr(domain, "T1", t0))
    if abs(t1 - t0) <= 1.0e-12:
        point = point_at(t0)
        return _clean_points([(float(point.X), float(point.Y), float(point.Z))])
    params = np.linspace(t0, t1, num=max(2, int(sample_count)))
    points = []
    for value in params.tolist():
        point = point_at(float(value))
        points.append((float(point.X), float(point.Y), float(point.Z)))
    return _clean_points(points)


def _extract_curve_points(geometry: Any, sample_count: int) -> tuple[list[tuple[float, float, float]], str]:
    geometry_type = type(geometry).__name__
    if hasattr(geometry, "PointCount") and hasattr(geometry, "Point"):
        point_count = int(getattr(geometry, "PointCount", 0) or 0)
        points = []
        for index in range(point_count):
            point = geometry.Point(index)
            points.append((float(point.X), float(point.Y), float(point.Z)))
        return _clean_points(points), geometry_type
    if geometry_type == "NurbsCurve":
        return _sample_nurbs_curve(geometry, sample_count), geometry_type
    return [], geometry_type


def _make_npz_payload(
    npz_out: Path,
    nodes: dict[int, tuple[float, float, float]],
    elements: list[dict[str, Any]],
    edges: list[tuple[int, int]],
) -> dict[str, int]:
    node_ids = sorted(nodes.keys())
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    node_xyz = np.asarray([nodes[node_id] for node_id in node_ids], dtype=np.float64)

    edge_index = np.zeros((2, len(edges) * 2), dtype=np.int64)
    for index, (node_a, node_b) in enumerate(edges):
        ia = node_index[int(node_a)]
        ib = node_index[int(node_b)]
        edge_index[:, 2 * index] = np.asarray([ia, ib], dtype=np.int64)
        edge_index[:, 2 * index + 1] = np.asarray([ib, ia], dtype=np.int64)

    elem_ids = np.asarray([int(row["id"]) for row in elements], dtype=np.int64)
    elem_conn_ptr = [0]
    elem_conn_idx: list[int] = []
    for row in elements:
        for node_id in row.get("node_ids", []):
            elem_conn_idx.append(int(node_index[int(node_id)]))
        elem_conn_ptr.append(len(elem_conn_idx))

    member_ids = np.asarray([str(row["id"]) for row in elements], dtype=str)
    story_band_index = np.zeros((len(elements),), dtype=np.int64)

    npz_out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        npz_out,
        node_id=np.asarray(node_ids, dtype=np.int64),
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_ids,
        elem_type_code=np.ones((len(elements),), dtype=np.int32),
        elem_section_id=np.full((len(elements),), -1, dtype=np.int64),
        elem_material_id=np.full((len(elements),), -1, dtype=np.int64),
        elem_conn_ptr=np.asarray(elem_conn_ptr, dtype=np.int64),
        elem_conn_idx=np.asarray(elem_conn_idx, dtype=np.int64),
        member_ids=member_ids,
        story_band_index=story_band_index,
    )
    return {
        "node_count": int(len(node_ids)),
        "edge_count_directed": int(edge_index.shape[1]),
        "element_count": int(len(elements)),
        "member_id_count": int(member_ids.size),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Rhino 3dm curves into viewer baseline geometry.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--rhino-3dm", required=True)
    parser.add_argument("--model-json-out", required=True)
    parser.add_argument("--npz-out", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--nurbs-sample-count", type=int, default=25)
    args = parser.parse_args()

    source_id = str(args.source_id).strip() or "unknown_source"
    rhino_path = Path(args.rhino_3dm)
    model_json_out = Path(args.model_json_out)
    npz_out = Path(args.npz_out)
    report_out = Path(args.report_out)

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "report_type": "rhino_3dm_baseline_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "inputs": {
            "rhino_3dm": str(rhino_path),
            "model_json_out": str(model_json_out),
            "npz_out": str(npz_out),
            "report_out": str(report_out),
            "nurbs_sample_count": int(args.nurbs_sample_count),
        },
    }

    if not rhino_path.exists():
        report.update({"contract_pass": False, "reason_code": "ERR_FILE_MISSING"})
        _write_json(report_out, report)
        return 1

    try:
        rhino3dm = _load_rhino3dm()
    except Exception:
        report.update({"contract_pass": False, "reason_code": "ERR_RHINO_IMPORT"})
        _write_json(report_out, report)
        return 1

    model = rhino3dm.File3dm.Read(str(rhino_path))
    if not model:
        report.update({"contract_pass": False, "reason_code": "ERR_READ_FAIL"})
        _write_json(report_out, report)
        return 1

    nodes: dict[int, tuple[float, float, float]] = {}
    node_lookup: dict[tuple[float, float, float], int] = {}
    elements: list[dict[str, Any]] = []
    edges: list[tuple[int, int]] = []
    object_type_counts: Counter[str] = Counter()
    accepted_type_counts: Counter[str] = Counter()
    bbox_min = [float("inf"), float("inf"), float("inf")]
    bbox_max = [float("-inf"), float("-inf"), float("-inf")]
    accepted_object_count = 0
    skipped_object_count = 0
    element_id = 1
    node_id = 1

    for object_index in range(len(model.Objects)):
        obj = model.Objects[object_index]
        geometry = obj.Geometry
        points, geometry_type = _extract_curve_points(geometry, int(args.nurbs_sample_count))
        object_type_counts[geometry_type] += 1
        if len(points) < 2:
            skipped_object_count += 1
            continue
        accepted_object_count += 1
        accepted_type_counts[geometry_type] += 1
        node_ids: list[int] = []
        for point in points:
            key = _point_key(point)
            for axis in range(3):
                bbox_min[axis] = min(bbox_min[axis], key[axis])
                bbox_max[axis] = max(bbox_max[axis], key[axis])
            if key not in node_lookup:
                node_lookup[key] = node_id
                nodes[node_id] = key
                node_id += 1
            node_ids.append(node_lookup[key])
        for local_index in range(len(node_ids) - 1):
            start_id = int(node_ids[local_index])
            end_id = int(node_ids[local_index + 1])
            if start_id == end_id:
                continue
            edges.append((min(start_id, end_id), max(start_id, end_id)))
            elements.append(
                {
                    "id": int(element_id),
                    "type": "BEAM",
                    "family": "beam",
                    "node_ids": [start_id, end_id],
                    "section_id": -1,
                    "material_id": -1,
                    "source_curve_index": int(object_index),
                    "source_geometry_type": geometry_type,
                }
            )
            element_id += 1

    if not elements or not nodes:
        report.update(
            {
                "contract_pass": False,
                "reason_code": "ERR_NO_CURVES",
                "summary": {
                    "object_type_label": ", ".join(f"{key}={value}" for key, value in sorted(object_type_counts.items())) or "n/a",
                    "accepted_object_count": int(accepted_object_count),
                    "skipped_object_count": int(skipped_object_count),
                },
            }
        )
        _write_json(report_out, report)
        return 1

    edge_rows = sorted(set(edges))
    model_payload = {
        "schema_version": "1.0",
        "source_provenance": {
            "source_family": "rhino_3dm_curve_bridge",
            "source_id": source_id,
            "path": str(rhino_path),
        },
        "model": {
            "nodes": [
                {"id": int(current_id), "x": float(coord[0]), "y": float(coord[1]), "z": float(coord[2])}
                for current_id, coord in sorted(nodes.items())
            ],
            "elements": elements,
            "materials": [],
            "sections": [],
            "loads": {},
            "metadata": {
                "bridge_family": "rhino_curve_baseline",
                "object_type_label": ", ".join(
                    f"{key}={value}" for key, value in sorted(object_type_counts.items(), key=lambda item: item[0])
                )
                or "n/a",
                "accepted_type_label": ", ".join(
                    f"{key}={value}" for key, value in sorted(accepted_type_counts.items(), key=lambda item: item[0])
                )
                or "n/a",
            },
        },
        "topology_metrics": {
            "node_count": int(len(nodes)),
            "element_count": int(len(elements)),
            "edge_count_undirected": int(len(edge_rows)),
            "beam_element_count": int(len(elements)),
            "shell_element_count": 0,
        },
    }
    _write_json(model_json_out, model_payload)
    npz_summary = _make_npz_payload(npz_out, nodes, elements, edge_rows)

    report.update(
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "object_count": int(len(model.Objects)),
                "accepted_object_count": int(accepted_object_count),
                "skipped_object_count": int(skipped_object_count),
                "object_type_label": ", ".join(
                    f"{key}={value}" for key, value in sorted(object_type_counts.items(), key=lambda item: item[0])
                )
                or "n/a",
                "accepted_type_label": ", ".join(
                    f"{key}={value}" for key, value in sorted(accepted_type_counts.items(), key=lambda item: item[0])
                )
                or "n/a",
                "family_assumption": "beam",
                "bbox_min": [round(value, 4) for value in bbox_min],
                "bbox_max": [round(value, 4) for value in bbox_max],
                "viewer_ready": True,
                **npz_summary,
            },
            "artifacts": {
                "model_json": str(model_json_out),
                "dataset_npz": str(npz_out),
                "source_rhino_3dm": str(rhino_path),
            },
        }
    )
    _write_json(report_out, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
