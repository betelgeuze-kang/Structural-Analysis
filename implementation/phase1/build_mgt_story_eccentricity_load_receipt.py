#!/usr/bin/env python3
"""Build a receipt for consuming MIDAS *STORY-ECCEN into equivalent load generation."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_story_eccentricity,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-story-eccentricity-load-receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
DEFAULT_OUT = PRODUCTIZATION / "mgt_story_eccentricity_load_receipt.json"
DOF_PER_NODE = 6


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _material_density(material: dict[str, Any] | None) -> float:
    if not material:
        return 2500.0
    material_type = str(material.get("type") or "").upper()
    if material_type == "STEEL":
        return 7850.0
    if material_type == "SRC":
        return 3600.0
    if material_type == "USER":
        return 2500.0
    return 2500.0


def _cluster_story_levels(node_xyz: np.ndarray, *, tolerance_m: float = 0.05) -> list[dict[str, Any]]:
    rounded: dict[float, list[int]] = defaultdict(list)
    for idx, z_value in enumerate(np.asarray(node_xyz[:, 2], dtype=np.float64)):
        rounded[round(float(z_value) / tolerance_m) * tolerance_m].append(int(idx))
    stories: list[dict[str, Any]] = []
    for story_index, (z_key, node_indices) in enumerate(sorted(rounded.items(), key=lambda item: item[0]), start=1):
        if len(node_indices) < 4:
            continue
        coords = node_xyz[node_indices, :]
        x_span = float(np.max(coords[:, 0]) - np.min(coords[:, 0])) if coords.size else 0.0
        y_span = float(np.max(coords[:, 1]) - np.min(coords[:, 1])) if coords.size else 0.0
        if x_span <= 0.0 or y_span <= 0.0:
            continue
        stories.append(
            {
                "story_index": int(story_index),
                "z_m": float(z_key),
                "node_indices": node_indices,
                "node_count": int(len(node_indices)),
                "x_span_m": x_span,
                "y_span_m": y_span,
                "x_center_m": float(np.mean(coords[:, 0])),
                "y_center_m": float(np.mean(coords[:, 1])),
                "gravity_weight_n": 0.0,
            }
        )
    return stories


def _polygon_area(points: np.ndarray) -> float:
    if points.shape[0] < 3:
        return 0.0
    centroid = np.mean(points, axis=0)
    area = 0.0
    for idx in range(1, points.shape[0] - 1):
        area += 0.5 * float(np.linalg.norm(np.cross(points[idx] - centroid, points[idx + 1] - centroid)))
    return abs(area)


def _nearest_story_index(stories: list[dict[str, Any]], z_value: float) -> int | None:
    if not stories:
        return None
    distances = [abs(float(story["z_m"]) - float(z_value)) for story in stories]
    return int(np.argmin(np.asarray(distances, dtype=np.float64)))


def _assign_story_weights(
    *,
    stories: list[dict[str, Any]],
    node_xyz: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    plate_thickness_props: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    line_weight = 0.0
    surface_weight = 0.0
    skipped = 0
    for elem_idx, elem_type in enumerate(np.asarray(elem_type_code, dtype=np.int32)):
        start = int(conn_ptr[elem_idx])
        end = int(conn_ptr[elem_idx + 1])
        nodes = [int(v) for v in conn_idx[start:end]]
        if len(nodes) < 2:
            skipped += 1
            continue
        coords = np.asarray(node_xyz[nodes, :], dtype=np.float64)
        story_idx = _nearest_story_index(stories, float(np.mean(coords[:, 2])))
        if story_idx is None:
            skipped += 1
            continue
        material = material_props.get(int(elem_material_id[elem_idx]))
        density = _material_density(material)
        weight = 0.0
        if int(elem_type) == 1:
            section = section_props.get(int(elem_section_id[elem_idx]))
            area = float((section or {}).get("A_m2") or 0.02)
            length = float(np.linalg.norm(coords[-1] - coords[0]))
            weight = max(area, 1.0e-6) * max(length, 0.0) * density * 9.80665
            line_weight += weight
        elif int(elem_type) == 2:
            thickness = plate_thickness_props.get(int(elem_section_id[elem_idx]))
            thickness_m = float((thickness or {}).get("effective_thickness_m") or 0.2)
            area = _polygon_area(coords)
            weight = max(area, 0.0) * max(thickness_m, 1.0e-4) * density * 9.80665
            surface_weight += weight
        else:
            skipped += 1
            continue
        stories[story_idx]["gravity_weight_n"] = float(stories[story_idx]["gravity_weight_n"]) + float(weight)
    total = sum(float(story["gravity_weight_n"]) for story in stories)
    if total <= 0.0 and stories:
        fallback = 1000.0
        for story in stories:
            story["gravity_weight_n"] = float(story["node_count"]) * fallback
        total = sum(float(story["gravity_weight_n"]) for story in stories)
    return {
        "line_weight_n": float(line_weight),
        "surface_weight_n": float(surface_weight),
        "total_story_weight_n": float(total),
        "skipped_element_count": int(skipped),
    }


def _case_specs(story_eccentricity: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if bool(story_eccentricity.get("include_seismic_eccentricity")):
        percent = float(story_eccentricity.get("seismic_eccentricity_percent") or 0.0)
        for axis, span_axis in (("X", "y_span_m"), ("Y", "x_span_m")):
            for sign in (-1.0, 1.0):
                specs.append(
                    {
                        "family": "seismic_accidental_eccentricity",
                        "axis": axis,
                        "sign": sign,
                        "eccentricity_percent": percent,
                        "perpendicular_span_key": span_axis,
                    }
                )
    if bool(story_eccentricity.get("include_wind_eccentricity")):
        percent = float(story_eccentricity.get("wind_eccentricity_percent") or 0.0)
        for axis, span_axis in (("X", "y_span_m"), ("Y", "x_span_m")):
            for sign in (-1.0, 1.0):
                specs.append(
                    {
                        "family": "wind_accidental_eccentricity",
                        "axis": axis,
                        "sign": sign,
                        "eccentricity_percent": percent,
                        "perpendicular_span_key": span_axis,
                    }
                )
    return specs


def _generate_load_cases(
    *,
    stories: list[dict[str, Any]],
    story_eccentricity: dict[str, Any],
    notional_lateral_coefficient: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    case_rows: list[dict[str, Any]] = []
    nodal_entries_head: list[dict[str, Any]] = []
    for case_index, spec in enumerate(_case_specs(story_eccentricity), start=1):
        total_lateral = 0.0
        total_abs_torsion = 0.0
        max_eccentricity = 0.0
        nodal_entry_count = 0
        story_rows: list[dict[str, Any]] = []
        for story in stories:
            node_count = max(int(story["node_count"]), 1)
            story_weight = float(story["gravity_weight_n"])
            lateral = story_weight * float(notional_lateral_coefficient)
            eccentricity = float(story[spec["perpendicular_span_key"]]) * float(spec["eccentricity_percent"]) / 100.0
            torsion = float(spec["sign"]) * lateral * eccentricity
            total_lateral += lateral
            total_abs_torsion += abs(torsion)
            max_eccentricity = max(max_eccentricity, abs(eccentricity))
            nodal_entry_count += node_count * 2
            story_rows.append(
                {
                    "story_index": int(story["story_index"]),
                    "z_m": float(story["z_m"]),
                    "node_count": node_count,
                    "story_weight_n": story_weight,
                    "lateral_force_n": lateral,
                    "eccentricity_m": eccentricity,
                    "torsional_moment_nm": torsion,
                    "nodal_lateral_force_n": lateral / node_count,
                    "nodal_torsion_moment_nm": torsion / node_count,
                }
            )
            for node in story["node_indices"][:2]:
                if len(nodal_entries_head) >= 16:
                    break
                nodal_entries_head.append(
                    {
                        "case_index": int(case_index),
                        "family": str(spec["family"]),
                        "axis": str(spec["axis"]),
                        "node_index": int(node),
                        "force_dof": "Fx" if spec["axis"] == "X" else "Fy",
                        "force_value_n": lateral / node_count,
                        "moment_dof": "Mz",
                        "moment_value_nm": torsion / node_count,
                    }
                )
        case_rows.append(
            {
                "case_index": int(case_index),
                "family": str(spec["family"]),
                "axis": str(spec["axis"]),
                "eccentricity_sign": float(spec["sign"]),
                "eccentricity_percent": float(spec["eccentricity_percent"]),
                "story_count": int(len(story_rows)),
                "total_lateral_force_n": float(total_lateral),
                "total_abs_torsional_moment_nm": float(total_abs_torsion),
                "max_eccentricity_m": float(max_eccentricity),
                "nodal_equivalent_entry_count": int(nodal_entry_count),
                "story_rows_head": story_rows[:8],
            }
        )
    return case_rows, nodal_entries_head


def build_mgt_story_eccentricity_load_receipt(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
    notional_lateral_coefficient: float = 0.01,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    if not mgt_path.is_file() or not roundtrip_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["mgt_or_roundtrip_npz_missing"],
        }
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    props = load_mgt_section_material_properties(mgt_path)
    story_eccentricity = parse_mgt_story_eccentricity(text)
    roundtrip = _load_json(roundtrip_json)
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int64)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int64)
        conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)
    stories = _cluster_story_levels(node_xyz)
    weight_meta = _assign_story_weights(
        stories=stories,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props=props.get("sections") if isinstance(props.get("sections"), dict) else {},
        material_props=props.get("materials") if isinstance(props.get("materials"), dict) else {},
        plate_thickness_props=props.get("plate_thicknesses") if isinstance(props.get("plate_thicknesses"), dict) else {},
    )
    load_cases, nodal_entries_head = _generate_load_cases(
        stories=stories,
        story_eccentricity=story_eccentricity,
        notional_lateral_coefficient=notional_lateral_coefficient,
    )
    active = bool(load_cases)
    ready = bool(active and stories and weight_meta["total_story_weight_n"] > 0.0)
    max_abs_torsion = max((float(row["total_abs_torsional_moment_nm"]) for row in load_cases), default=0.0)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if ready else "partial",
        "source": {
            "mgt_path": str(mgt_path),
            "mgt_sha256": _sha256(mgt_path),
            "roundtrip_json": str(roundtrip_json),
            "roundtrip_npz": str(roundtrip_npz),
            "roundtrip_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
            "block": "*STORY-ECCEN",
            "provenance": "repo_benchmark_bridge",
        },
        "story_eccentricity": story_eccentricity,
        "generation_policy": {
            "mode": "notional_accidental_torsion_equivalent_nodal_loads",
            "notional_lateral_coefficient": float(notional_lateral_coefficient),
            "lateral_force_basis": "story gravity proxy from MGT line/surface elements",
            "seismic_enabled_by_source": bool(story_eccentricity.get("include_seismic_eccentricity")),
            "wind_enabled_by_source": bool(story_eccentricity.get("include_wind_eccentricity")),
        },
        "summary": {
            "story_count": int(len(stories)),
            "generated_case_count": int(len(load_cases)),
            "generated_seismic_case_count": sum(1 for row in load_cases if str(row["family"]).startswith("seismic")),
            "generated_wind_case_count": sum(1 for row in load_cases if str(row["family"]).startswith("wind")),
            "max_abs_torsional_moment_nm": float(max_abs_torsion),
            "total_story_weight_n": float(weight_meta["total_story_weight_n"]),
            "line_weight_n": float(weight_meta["line_weight_n"]),
            "surface_weight_n": float(weight_meta["surface_weight_n"]),
            "max_story_node_count": max((int(story["node_count"]) for story in stories), default=0),
            "max_story_x_span_m": max((float(story["x_span_m"]) for story in stories), default=0.0),
            "max_story_y_span_m": max((float(story["y_span_m"]) for story in stories), default=0.0),
            "nodal_equivalent_entry_count": sum(int(row["nodal_equivalent_entry_count"]) for row in load_cases),
        },
        "support": {
            "typed_mgt_story_eccentricity_parser_ready": bool(story_eccentricity),
            "story_eccentricity_load_generation_ready": ready,
            "seismic_story_eccentricity_load_generation_ready": bool(
                story_eccentricity.get("include_seismic_eccentricity") and load_cases
            ),
            "wind_story_eccentricity_disabled_by_source": not bool(
                story_eccentricity.get("include_wind_eccentricity")
            ),
            "global_solver_consumes_story_eccentricity_loads": False,
            "design_code_response_spectrum_ready": False,
        },
        "story_rows_head": [
            {
                key: story[key]
                for key in (
                    "story_index",
                    "z_m",
                    "node_count",
                    "x_span_m",
                    "y_span_m",
                    "gravity_weight_n",
                )
            }
            for story in stories[:12]
        ],
        "generated_load_cases": load_cases,
        "nodal_equivalent_entries_head": nodal_entries_head,
        "claim_boundary": {
            "closed": [
                "real MGT *STORY-ECCEN is consumed into equivalent accidental torsion load cases",
                "story plan spans and gravity proxy are computed from the roundtrip model",
                "equivalent nodal lateral force and Mz torsion entries are generated for enabled source families",
            ],
            "not_closed": [
                "generated story eccentricity loads are not yet injected into the full global frame-shell solve",
                "this is not a KDS/IBC response spectrum or wind-code implementation",
                "wind eccentricity is parsed but disabled because the source row sets bIncludeEccWind=NO",
            ],
        },
        "blockers": [] if ready else ["story_eccentricity_load_generation_not_ready"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--notional-lateral-coefficient", type=float, default=0.01)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_mgt_story_eccentricity_load_receipt(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
        notional_lateral_coefficient=args.notional_lateral_coefficient,
    )
    print(
        "mgt-story-eccentricity-load: "
        f"status={payload['status']} "
        f"stories={(payload.get('summary') or {}).get('story_count')} "
        f"cases={(payload.get('summary') or {}).get('generated_case_count')} "
        f"max_torsion={(payload.get('summary') or {}).get('max_abs_torsional_moment_nm')}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
