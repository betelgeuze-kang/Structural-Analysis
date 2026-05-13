#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


REASONS = {
    "PASS": "synthetic 606m outrigger bridge passed",
    "PASS_SUITE": "synthetic 606m outrigger bridge suite passed",
    "ERR_SOURCE_MISSING": "ndtha source report missing",
    "ERR_CASE_MISSING": "requested outrigger case missing",
    "ERR_INVALID_CASE": "case does not provide enough summary data for synthetic bridge",
    "ERR_NO_OUTRIGGER_CASES": "no outrigger cases found for requested candidate",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _family_member_type(family_name: str) -> str:
    token = str(family_name or "").lower()
    if "beam" in token:
        return "beam"
    if "wall" in token:
        return "wall"
    if "column" in token:
        return "column"
    if "slab" in token:
        return "slab"
    return "other"


def _family_zone_label(family_name: str) -> str:
    token = str(family_name or "").lower()
    if "outrigger" in token:
        return "transfer"
    if "core" in token:
        return "core"
    if "slab" in token:
        return "intermediate"
    return "perimeter"


def _family_action_family(family_name: str) -> str:
    token = str(family_name or "").lower()
    if "outrigger" in token:
        return "beam_section"
    if "mega" in token:
        return "perimeter_frame"
    if "core" in token:
        return "connection_detailing"
    if "wall" in token:
        return "wall_thickness"
    if "slab" in token:
        return "slab_thickness"
    return "detailing"


def _family_action_name(family_name: str) -> str:
    action_family = _family_action_family(family_name)
    return f"{action_family}_down"


def _governing_clause(family_name: str) -> str:
    token = str(family_name or "").lower()
    if "outrigger" in token:
        return "OPSTOOL-OUTRIGGER-DRIFT-001"
    if "mega" in token:
        return "OPSTOOL-MEGA-COLUMN-001"
    if "core" in token:
        return "OPSTOOL-CORE-STABILITY-001"
    return "OPSTOOL-SYNTHETIC-001"


def _base_cost_for_family(family_name: str) -> float:
    token = str(family_name or "").lower()
    if "mega" in token:
        return 1880.0
    if "outrigger" in token:
        return 1325.0
    if "core" in token:
        return 1460.0
    if "wall" in token:
        return 980.0
    if "slab" in token:
        return 760.0
    return 900.0


def _story_family_profile(summary: dict[str, Any], story_count: int) -> list[str]:
    counts = summary.get("section_family_counts") if isinstance(summary.get("section_family_counts"), dict) else {}
    ordered: list[str] = []
    for family_name, count in counts.items():
        ordered.extend([str(family_name)] * max(0, _safe_int(count, 0)))
    if not ordered:
        ordered = ["mega_column"] * story_count
    if len(ordered) < story_count:
        ordered.extend([ordered[-1]] * (story_count - len(ordered)))
    return ordered[:story_count]


def _probe_by_story(
    probe_rows: list[dict[str, Any]],
    *,
    story_count: int,
    default_family_profile: list[str],
    summary: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    section_profile = summary.get("section_profile") if isinstance(summary.get("section_profile"), dict) else {}
    material_indices = summary.get("material_indices") if isinstance(summary.get("material_indices"), dict) else {}
    default_stiffness = _safe_float(section_profile.get("stiffness_scale_mean"), 1.0)
    default_yield = _safe_float(section_profile.get("yield_scale_mean"), 1.0)
    default_beam_tangent = _safe_float(material_indices.get("stiffness_scale_mean"), 0.92)
    probe_by_story: dict[int, dict[str, Any]] = {}
    for row in probe_rows:
        if not isinstance(row, dict):
            continue
        story = _safe_int(row.get("story"), 0)
        if story <= 0:
            continue
        probe_by_story[story] = {
            "family_name": str(row.get("family_name", "") or default_family_profile[min(story - 1, len(default_family_profile) - 1)]),
            "stiffness_scale": _safe_float(row.get("stiffness_scale"), default_stiffness),
            "yield_scale": _safe_float(row.get("yield_scale"), default_yield),
            "beam_tangent_scale": _safe_float(row.get("beam_tangent_scale"), default_beam_tangent),
            "beam_yielded_end_count": _safe_int(row.get("beam_yielded_end_count"), 0),
            "section_moment_kNm": _safe_float(row.get("section_moment_kNm"), 0.0),
        }
    for story in range(1, story_count + 1):
        if story in probe_by_story:
            continue
        family_name = default_family_profile[min(story - 1, len(default_family_profile) - 1)]
        drift_weight = story / max(1, story_count)
        probe_by_story[story] = {
            "family_name": family_name,
            "stiffness_scale": max(default_stiffness * (1.0 - 0.015 * drift_weight), 0.82),
            "yield_scale": max(default_yield * (1.0 - 0.01 * drift_weight), 0.9),
            "beam_tangent_scale": max(default_beam_tangent * (1.0 - 0.02 * drift_weight), 0.72),
            "beam_yielded_end_count": 1 if "outrigger" in family_name.lower() and 0.35 < drift_weight < 0.75 else 0,
            "section_moment_kNm": 65.0 if "beam" in family_name.lower() else 138.0,
        }
    return probe_by_story


def _aggregate_change_summary(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, str, str], dict[str, Any]] = {}
    for row in changes:
        key = (
            _safe_int(row.get("story_band"), 0),
            str(row.get("zone_label", "") or "unknown"),
            str(row.get("member_type", "") or "unknown"),
        )
        bucket = buckets.setdefault(
            key,
            {
                "story_band": key[0],
                "zone_label": key[1],
                "member_type": key[2],
                "changed_group_count": 0,
                "semantic_group_count": 0,
                "rebar_ratio_delta_sum": 0.0,
                "cost_proxy_delta_sum": 0.0,
                "constructability_delta_sum": 0.0,
                "overdesign_margin_delta_sum": 0.0,
                "max_dcr_before_max": 0.0,
                "max_dcr_after_max": 0.0,
                "selection_gate": str(row.get("selection_gate", "") or "n/a"),
                "constructability_before_avg": 0.0,
                "constructability_after_avg": 0.0,
                "detailing_complexity_before_avg": 0.0,
                "detailing_complexity_after_avg": 0.0,
            },
        )
        bucket["changed_group_count"] += 1
        bucket["cost_proxy_delta_sum"] += _safe_float(row.get("cost_proxy_delta"), 0.0)
        bucket["constructability_delta_sum"] += _safe_float(row.get("constructability_delta"), 0.0)
        bucket["overdesign_margin_delta_sum"] += _safe_float(row.get("overdesign_margin_delta"), 0.0)
        bucket["max_dcr_before_max"] = max(bucket["max_dcr_before_max"], _safe_float(row.get("max_dcr_before"), 0.0))
        bucket["max_dcr_after_max"] = max(bucket["max_dcr_after_max"], _safe_float(row.get("max_dcr_after"), 0.0))
        bucket["constructability_before_avg"] += _safe_float(row.get("before_constructability"), 0.0)
        bucket["constructability_after_avg"] += _safe_float(row.get("after_constructability"), 0.0)
        bucket["detailing_complexity_before_avg"] += _safe_float(row.get("before_detailing_complexity"), 0.0)
        bucket["detailing_complexity_after_avg"] += _safe_float(row.get("after_detailing_complexity"), 0.0)
    rows = list(buckets.values())
    for row in rows:
        count = max(1, int(row["changed_group_count"]))
        for key in (
            "cost_proxy_delta_sum",
            "constructability_delta_sum",
            "overdesign_margin_delta_sum",
            "max_dcr_before_max",
            "max_dcr_after_max",
        ):
            row[key] = round(_safe_float(row[key], 0.0), 4)
        for key in (
            "constructability_before_avg",
            "constructability_after_avg",
            "detailing_complexity_before_avg",
            "detailing_complexity_after_avg",
        ):
            row[key] = round(_safe_float(row[key], 0.0) / count, 4)
    rows.sort(key=lambda item: (int(item["story_band"]), str(item["zone_label"]), str(item["member_type"])))
    return rows


def _default_release_gap_summary(case_id: str, story_count: int, total_height_m: float) -> dict[str, Any]:
    return {
        "commercial_grade": "Synthetic Benchmark",
        "deployment_model": "benchmark-derived response-conditioned 3d viewer",
        "measured_chain_total_minutes": 0.0,
        "measured_chain_selected_step_count": int(story_count),
        "mgt_export_delivery_boundary": "synthetic benchmark overlay / no release patch delivery",
        "pbd_dynamic_hinge_refresh_ready": False,
        "panel_zone_3d_clash_ready": False,
        "foundation_optimization_ready": False,
        "wind_tunnel_raw_mapping_ready": False,
        "panel_zone_constructability_mode": "synthetic benchmark only",
        "panel_zone_validation_boundary": "synthetic_geometry_only",
        "panel_zone_internal_engine_complete": False,
        "panel_zone_external_validation_pending": False,
        "synthetic_source_case_id": case_id,
        "synthetic_total_height_m": round(total_height_m, 3),
        "synthetic_story_count": int(story_count),
    }


def _build_case_payloads(case_row: dict[str, Any]) -> dict[str, Any]:
    summary = case_row.get("summary") if isinstance(case_row.get("summary"), dict) else {}
    response = case_row.get("response") if isinstance(case_row.get("response"), dict) else {}
    story_count = max(1, _safe_int(summary.get("story_count"), 24))
    total_height_m = 606.0
    story_height_m = total_height_m / story_count

    family_profile = _story_family_profile(summary, story_count)
    outrigger_story_set = {
        index + 1
        for index, family_name in enumerate(family_profile)
        if str(family_name or "").lower() == "outrigger_beam"
    }
    probe_rows = [row for row in (case_row.get("section_probe_head") or []) if isinstance(row, dict)]
    probe_by_story = _probe_by_story(
        probe_rows,
        story_count=story_count,
        default_family_profile=family_profile,
        summary=summary,
    )
    drift_envelope = list(response.get("story_drift_envelope_pct") or [])
    final_story_drift = list(response.get("final_story_drift_pct") or [])
    max_drift = max([_safe_float(value, 0.0) for value in drift_envelope] + [1.0])
    residual_drift = _safe_float(summary.get("residual_drift_ratio_pct"), 0.0)
    max_story_drift_envelope_pct = max([_safe_float(value, 0.0) for value in drift_envelope] + [0.0])
    max_final_story_drift_pct = max([_safe_float(value, 0.0) for value in final_story_drift] + [0.0])
    roof_final_story_drift_pct = _safe_float(final_story_drift[-1], 0.0) if final_story_drift else 0.0
    hotspot_story = 1
    if drift_envelope:
        hotspot_story = max(range(1, len(drift_envelope) + 1), key=lambda idx: _safe_float(drift_envelope[idx - 1], 0.0))
    hotspot_family_name = family_profile[min(max(hotspot_story - 1, 0), len(family_profile) - 1)] if family_profile else "n/a"

    perimeter_half = 42.0
    core_half = 11.5
    z_levels = [round(story * story_height_m, 4) for story in range(story_count + 1)]
    outer_xy = {
        "NW": (-perimeter_half, perimeter_half),
        "NE": (perimeter_half, perimeter_half),
        "SE": (perimeter_half, -perimeter_half),
        "SW": (-perimeter_half, -perimeter_half),
    }
    core_xy = {
        "CNW": (-core_half, core_half),
        "CNE": (core_half, core_half),
        "CSE": (core_half, -core_half),
        "CSW": (-core_half, -core_half),
    }

    nodes: list[dict[str, Any]] = []
    node_ids: dict[tuple[str, int], int] = {}
    next_node_id = 1
    for level_index, z in enumerate(z_levels):
        for label, (x, y) in {**outer_xy, **core_xy}.items():
            node_ids[(label, level_index)] = next_node_id
            nodes.append({"id": next_node_id, "x": round(x, 4), "y": round(y, 4), "z": z})
            next_node_id += 1

    elements: list[dict[str, Any]] = []
    member_ids: list[str] = []
    group_ids: list[str] = []
    group_index_per_member: list[int] = []
    story_band_index: list[int] = []
    zone_labels: list[str] = []
    member_types: list[str] = []
    unique_group_ids: list[str] = []
    member_type_per_group: list[str] = []
    zone_label_per_group: list[str] = []
    story_band_per_group: list[int] = []
    group_index_lookup: dict[str, int] = {}
    next_element_id = 1

    def ensure_group(group_id: str, *, member_type: str, zone_label: str, story_band: int) -> int:
        if group_id in group_index_lookup:
            return group_index_lookup[group_id]
        group_index = len(unique_group_ids)
        group_index_lookup[group_id] = group_index
        unique_group_ids.append(group_id)
        member_type_per_group.append(member_type)
        zone_label_per_group.append(zone_label)
        story_band_per_group.append(int(story_band))
        return group_index

    def add_element(
        member_id: str,
        *,
        type_label: str,
        family: str,
        node_id_list: list[int],
        group_id: str,
        story_band: int,
        zone_label: str,
    ) -> None:
        nonlocal next_element_id
        group_index = ensure_group(
            group_id,
            member_type=_family_member_type(family),
            zone_label=zone_label,
            story_band=story_band,
        )
        elements.append(
            {
                "id": member_id,
                "type": type_label,
                "family": family,
                "node_ids": node_id_list,
                "element_id": next_element_id,
                "story_band": story_band,
                "zone_label": zone_label,
                "group_id": group_id,
                "group_index": group_index,
            }
        )
        member_ids.append(member_id)
        group_ids.append(group_id)
        group_index_per_member.append(group_index)
        story_band_index.append(int(story_band))
        zone_labels.append(zone_label)
        member_types.append(_family_member_type(family))
        next_element_id += 1

    perimeter_edges = [("NW", "NE"), ("NE", "SE"), ("SE", "SW"), ("SW", "NW")]
    core_edges = [("CNW", "CNE"), ("CNE", "CSE"), ("CSE", "CSW"), ("CSW", "CNW")]
    outrigger_pairs = [("CNW", "NW"), ("CNE", "NE"), ("CSE", "SE"), ("CSW", "SW")]

    for story in range(1, story_count + 1):
        lower = story - 1
        upper = story
        for corner in ("NW", "NE", "SE", "SW"):
            add_element(
                f"MCOL_{corner}_S{story:02d}",
                type_label="COLUMN",
                family="mega_column",
                node_id_list=[node_ids[(corner, lower)], node_ids[(corner, upper)]],
                group_id=f"S{story:02d}:perimeter:mega_column",
                story_band=story,
                zone_label="perimeter",
            )
        for corner in ("CNW", "CNE", "CSE", "CSW"):
            add_element(
                f"CCOL_{corner}_S{story:02d}",
                type_label="COLUMN",
                family="core_column",
                node_id_list=[node_ids[(corner, lower)], node_ids[(corner, upper)]],
                group_id=f"S{story:02d}:core:core_column",
                story_band=story,
                zone_label="core",
            )
        for edge_index, (start_label, end_label) in enumerate(core_edges, start=1):
            add_element(
                f"CWALL_{edge_index}_S{story:02d}",
                type_label="WALL",
                family="core_wall",
                node_id_list=[
                    node_ids[(start_label, lower)],
                    node_ids[(end_label, lower)],
                    node_ids[(end_label, upper)],
                    node_ids[(start_label, upper)],
                ],
                group_id=f"S{story:02d}:core:core_wall",
                story_band=story,
                zone_label="core",
            )
        for edge_index, (start_label, end_label) in enumerate(perimeter_edges, start=1):
            add_element(
                f"PBEAM_{edge_index}_S{story:02d}",
                type_label="BEAM",
                family="perimeter_beam",
                node_id_list=[node_ids[(start_label, upper)], node_ids[(end_label, upper)]],
                group_id=f"S{story:02d}:perimeter:perimeter_beam",
                story_band=story,
                zone_label="perimeter",
            )
        add_element(
            f"SLAB_S{story:02d}",
            type_label="PLATE",
            family="slab",
            node_id_list=[
                node_ids[("NW", upper)],
                node_ids[("NE", upper)],
                node_ids[("SE", upper)],
                node_ids[("SW", upper)],
            ],
            group_id=f"S{story:02d}:intermediate:slab",
            story_band=story,
            zone_label="intermediate",
        )
        if story in outrigger_story_set:
            for arm_index, (start_label, end_label) in enumerate(outrigger_pairs, start=1):
                add_element(
                    f"OUTRIGGER_{arm_index}_S{story:02d}",
                    type_label="BEAM",
                    family="outrigger_beam",
                    node_id_list=[node_ids[(start_label, upper)], node_ids[(end_label, upper)]],
                    group_id=f"S{story:02d}:transfer:outrigger_beam",
                    story_band=story,
                    zone_label="transfer",
                )

    changes: list[dict[str, Any]] = []
    for story in range(1, story_count + 1):
        family_name = family_profile[story - 1]
        member_type = _family_member_type(family_name)
        zone_label = _family_zone_label(family_name)
        group_id = f"S{story:02d}:{zone_label}:{family_name}"
        group_index = group_index_lookup.get(group_id)
        if group_index is None:
            continue
        probe = probe_by_story.get(story, {})
        stiffness_scale = _safe_float(probe.get("stiffness_scale"), 1.0)
        beam_tangent_scale = _safe_float(probe.get("beam_tangent_scale"), 1.0)
        section_moment = _safe_float(probe.get("section_moment_kNm"), 0.0)
        drift_before = _safe_float(drift_envelope[story - 1] if story - 1 < len(drift_envelope) else max_drift * (1.0 - 0.03 * (story - 1)))
        drift_after = _safe_float(final_story_drift[story - 1] if story - 1 < len(final_story_drift) else drift_before * 0.28)
        base_cost = _base_cost_for_family(family_name)
        story_weight = 1.0 + (story / max(1, story_count)) * 0.22
        cost_before = base_cost * story_weight
        efficiency_factor = 0.93 if "mega" in family_name else 0.905 if "outrigger" in family_name else 0.918
        stiffness_bonus = max(0.0, min(0.08, (1.0 - min(stiffness_scale, 1.08)) * 0.45))
        after_factor = max(0.72, efficiency_factor - stiffness_bonus)
        cost_after = cost_before * after_factor
        before_constructability = 0.38 + (story / max(1, story_count)) * 0.18 + (0.08 if "outrigger" in family_name else 0.03)
        constructability_delta = -0.042 if "outrigger" in family_name else -0.028 if "mega" in family_name else -0.019
        after_constructability = max(0.08, before_constructability + constructability_delta)
        before_detailing = 0.56 + (0.09 if "core" in family_name else 0.04 if "outrigger" in family_name else 0.02)
        after_detailing = max(0.12, before_detailing - (0.05 if "core" in family_name else 0.035))
        max_dcr_before = min(1.18, (drift_before / max_drift) * 1.08 + 0.04)
        max_dcr_after = min(1.08, max(0.12, max_dcr_before * (0.88 - max(0.0, (beam_tangent_scale - 0.7) * 0.06))))
        changes.append(
            {
                "group_id": group_id,
                "group_index": int(group_index),
                "story_band": int(story),
                "zone_label": zone_label,
                "member_type": member_type,
                "semantic_group": family_name,
                "action_name": _family_action_name(family_name),
                "action_family": _family_action_family(family_name),
                "before_section": family_name.upper(),
                "after_section": f"{family_name.upper()}_AI",
                "before_rebar_ratio": 0.012 if member_type in {"column", "wall"} else 0.0,
                "after_rebar_ratio": 0.009 if member_type in {"column", "wall"} else 0.0,
                "rebar_ratio_delta": -0.003 if member_type in {"column", "wall"} else 0.0,
                "before_thickness_scale": 1.0 if member_type != "wall" else 0.98,
                "after_thickness_scale": 1.0 if member_type != "wall" else 0.95,
                "before_detailing_quality": before_detailing,
                "after_detailing_quality": after_detailing,
                "cost_proxy_before": round(cost_before, 4),
                "cost_proxy_after": round(cost_after, 4),
                "cost_proxy_delta": round(cost_after - cost_before, 4),
                "max_dcr_before": round(max_dcr_before, 4),
                "max_dcr_after": round(max_dcr_after, 4),
                "max_dcr_delta": round(max_dcr_after - max_dcr_before, 4),
                "governing_member_governing_dcr_before": round(max_dcr_before * 1.06, 4),
                "governing_member_governing_dcr_after": round(max_dcr_after * 1.04, 4),
                "governing_clause": _governing_clause(family_name),
                "drift_before_pct": round(drift_before, 4),
                "drift_after_pct": round(drift_after, 4),
                "residual_before_pct": round(max(residual_drift, drift_before * 0.08), 4),
                "residual_after_pct": round(max(residual_drift * 0.78, drift_after * 0.06), 4),
                "before_constructability": round(before_constructability, 4),
                "after_constructability": round(after_constructability, 4),
                "before_detailing_complexity": round(before_detailing, 4),
                "after_detailing_complexity": round(after_detailing, 4),
                "constructability_delta": round(after_constructability - before_constructability, 4),
                "overdesign_margin_delta": round((cost_before - cost_after) * 0.72 + section_moment * 0.18, 4),
                "selection_gate": "synthetic_benchmark_story_family_pass",
                "reason_selected": "derived_from_ndtha_story_family_profile",
            }
        )

    change_summary_rows = _aggregate_change_summary(changes)
    action_family_counts = Counter(str(row.get("action_family", "") or "unknown") for row in changes)
    dominant_action_family = "n/a"
    dominant_action_family_count = 0
    if action_family_counts:
        dominant_action_family, dominant_action_family_count = action_family_counts.most_common(1)[0]
    action_family_label = ", ".join(
        f"{family}={count}" for family, count in sorted(action_family_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ) or "none"

    dataset_payload = {
        "member_ids": np.asarray(member_ids, dtype=str),
        "member_types": np.asarray(member_types, dtype=str),
        "group_ids": np.asarray(group_ids, dtype=str),
        "group_index_per_member": np.asarray(group_index_per_member, dtype=np.int32),
        "member_type_per_group": np.asarray(member_type_per_group, dtype=str),
        "zone_label_per_group": np.asarray(zone_label_per_group, dtype=str),
        "story_band_per_group": np.asarray(story_band_per_group, dtype=np.int32),
        "story_band_index": np.asarray(story_band_index, dtype=np.int32),
        "zone_labels": np.asarray(zone_labels, dtype=str),
        "unique_group_ids": np.asarray(unique_group_ids, dtype=str),
    }
    model_payload = {
        "schema_version": "1.0",
        "model_kind": "synthetic_606m_outrigger_megatall",
        "synthetic_geometry_notice": (
            "This geometry is a benchmark-derived structural representation synthesized from NDTHA summary data. "
            "It is not a direct CAD/OpenSees source export."
        ),
        "topology_metrics": {
            "story_count": int(story_count),
            "total_height_m": round(total_height_m, 4),
            "node_count": len(nodes),
            "element_count": len(elements),
        },
        "model": {
            "nodes": nodes,
            "elements": elements,
        },
    }
    return {
        "story_count": story_count,
        "total_height_m": total_height_m,
        "model_payload": model_payload,
        "dataset_payload": dataset_payload,
        "changes_payload": {"schema_version": "1.0", "changes": changes},
        "change_summary_payload": {"schema_version": "1.0", "change_summary_rows": change_summary_rows},
        "release_gap_payload": {
            "schema_version": "1.0",
            "summary": _default_release_gap_summary(str(case_row.get("case_id", "") or "unknown_case"), story_count, total_height_m),
        },
        "export_report_payload": {
            "schema_version": "1.0",
            "summary": {
                "direct_patch_change_count": int(len(changes)),
                "instruction_sidecar_change_count": 0,
                "instruction_sidecar_audit_only_change_count": 0,
                "audit_review_packet_count": 0,
                "audit_review_queue_pending_count": 0,
                "evidence_model": "synthetic_ndtha_story_family_overlay",
                "mgt_export_delivery_boundary": "synthetic benchmark overlay / no release patch delivery",
                "support_mode": "synthetic benchmark overlay",
                "direct_patch_action_family_counts": dict(action_family_counts),
                "instruction_sidecar_audit_only_action_family_counts": {},
            },
        },
        "bridge_summary": {
            "story_count": int(story_count),
            "total_height_m": round(total_height_m, 4),
            "node_count": len(nodes),
            "element_count": len(elements),
            "changed_group_count": len(changes),
            "max_story_drift_envelope_pct": round(max_story_drift_envelope_pct, 4),
            "max_final_story_drift_pct": round(max_final_story_drift_pct, 4),
            "roof_final_story_drift_pct": round(roof_final_story_drift_pct, 4),
            "residual_drift_ratio_pct": round(residual_drift, 4),
            "drift_hotspot_story": int(hotspot_story),
            "drift_hotspot_story_label": f"S{hotspot_story:02d}",
            "drift_hotspot_family": str(hotspot_family_name),
            "dominant_action_family": str(dominant_action_family),
            "dominant_action_family_count": int(dominant_action_family_count),
            "action_family_counts": dict(action_family_counts),
            "action_family_label": action_family_label,
            "viewer_ready": True,
            "ai_overlay_ready": True,
            "story_family_profile": family_profile,
            "synthetic_geometry_notice": (
                "Benchmark-derived synthetic 3D bridge. Original CAD/OpenSees geometry is not bundled in this repo."
            ),
        },
    }


def _collect_outrigger_rows(ndtha_payload: dict[str, Any], candidate_id: str) -> list[dict[str, Any]]:
    rows = []
    for row in ndtha_payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id", "") or "")
        if not case_id.startswith(f"{candidate_id}-"):
            continue
        if str(row.get("topology_type", "") or "") != "outrigger":
            continue
        rows.append(row)
    rows.sort(key=lambda item: str(item.get("case_id", "")))
    return rows


def _write_case_bundle(case_row: dict[str, Any], out_dir: Path, *, candidate_id: str) -> dict[str, Any]:
    report_path = out_dir / "bridge_report.json"
    model_json_path = out_dir / "model.json"
    dataset_npz_path = out_dir / "dataset.npz"
    changes_json_path = out_dir / "synthetic_changes.json"
    change_summary_json_path = out_dir / "synthetic_change_summary.json"
    release_gap_json_path = out_dir / "synthetic_release_gap_report.json"
    export_report_json_path = out_dir / "synthetic_export_report.json"
    case_id = str(case_row.get("case_id", "") or "unknown_case")
    payloads = _build_case_payloads(case_row)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(model_json_path, payloads["model_payload"])
    np.savez_compressed(dataset_npz_path, **payloads["dataset_payload"])
    _write_json(changes_json_path, payloads["changes_payload"])
    _write_json(change_summary_json_path, payloads["change_summary_payload"])
    _write_json(release_gap_json_path, payloads["release_gap_payload"])
    _write_json(export_report_json_path, payloads["export_report_payload"])
    report_payload = {
        "schema_version": "1.0",
        "report_type": "synthetic_606m_outrigger_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "candidate_id": candidate_id,
            "case_id": case_id,
            "out_dir": str(out_dir),
        },
        "contract_pass": True,
        "reason_code": "PASS",
        "summary": payloads["bridge_summary"],
        "artifacts": {
            "model_json": str(model_json_path),
            "dataset_npz": str(dataset_npz_path),
            "changes_json": str(changes_json_path),
            "change_summary_json": str(change_summary_json_path),
            "release_gap_json": str(release_gap_json_path),
            "export_report_json": str(export_report_json_path),
        },
    }
    _write_json(report_path, report_payload)
    return report_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a synthetic 606m outrigger megatall 3D bridge from NDTHA summary data.")
    parser.add_argument("--ndtha-report", default="implementation/phase1/nonlinear_ndtha_stress_report.pbd7.json")
    parser.add_argument("--candidate-id", default="opstool_606m_megatall_model")
    parser.add_argument("--case-id", default="opstool_606m_megatall_model-00001")
    parser.add_argument("--out-dir", default="implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model")
    parser.add_argument("--all-outrigger-cases", action="store_true")
    args = parser.parse_args()

    ndtha_report_path = Path(args.ndtha_report)
    out_dir = Path(args.out_dir)
    report_path = out_dir / "bridge_report.json"

    report_payload: dict[str, Any] = {
        "schema_version": "1.0",
        "report_type": "synthetic_606m_outrigger_bridge",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "ndtha_report": str(ndtha_report_path),
            "candidate_id": str(args.candidate_id),
            "case_id": str(args.case_id),
            "out_dir": str(out_dir),
        },
    }

    if not ndtha_report_path.exists():
        report_payload.update({"contract_pass": False, "reason_code": "ERR_SOURCE_MISSING"})
        _write_json(report_path, report_payload)
        return 1

    ndtha_payload = json.loads(ndtha_report_path.read_text(encoding="utf-8"))
    if bool(args.all_outrigger_cases):
        outrigger_rows = _collect_outrigger_rows(ndtha_payload, str(args.candidate_id))
        if not outrigger_rows:
            report_payload.update({"contract_pass": False, "reason_code": "ERR_NO_OUTRIGGER_CASES"})
            _write_json(report_path, report_payload)
            return 1
        case_reports = []
        for row in outrigger_rows:
            case_id = str(row.get("case_id", "") or "unknown_case")
            case_dir = out_dir / case_id
            case_report = _write_case_bundle(row, case_dir, candidate_id=str(args.candidate_id))
            case_reports.append(
                {
                    "case_id": case_id,
                    "out_dir": str(case_dir),
                    "summary": case_report.get("summary", {}),
                    "artifacts": case_report.get("artifacts", {}),
                }
            )
        suite_report = {
            "schema_version": "1.0",
            "report_type": "synthetic_606m_outrigger_bridge_suite",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "ndtha_report": str(ndtha_report_path),
                "candidate_id": str(args.candidate_id),
                "out_dir": str(out_dir),
                "all_outrigger_cases": True,
            },
            "contract_pass": True,
            "reason_code": "PASS_SUITE",
            "summary": {
                "case_count": len(case_reports),
                "case_ids": [row["case_id"] for row in case_reports],
                "viewer_ready_count": sum(1 for row in case_reports if bool((row.get("summary") or {}).get("viewer_ready"))),
                "ai_overlay_ready_count": sum(1 for row in case_reports if bool((row.get("summary") or {}).get("ai_overlay_ready"))),
            },
            "cases": case_reports,
        }
        _write_json(report_path, suite_report)
        print(f"Wrote synthetic 606m outrigger bridge suite: {report_path}")
        return 0

    case_row = None
    for row in ndtha_payload.get("rows", []):
        if isinstance(row, dict) and str(row.get("case_id", "")) == str(args.case_id):
            case_row = row
            break
    if not isinstance(case_row, dict):
        report_payload.update({"contract_pass": False, "reason_code": "ERR_CASE_MISSING"})
        _write_json(report_path, report_payload)
        return 1

    summary = case_row.get("summary") if isinstance(case_row.get("summary"), dict) else {}
    if _safe_int(summary.get("story_count"), 0) <= 0:
        report_payload.update({"contract_pass": False, "reason_code": "ERR_INVALID_CASE"})
        _write_json(report_path, report_payload)
        return 1

    case_report = _write_case_bundle(case_row, out_dir, candidate_id=str(args.candidate_id))
    report_payload.update(case_report)
    _write_json(report_path, report_payload)
    print(f"Wrote synthetic 606m outrigger bridge: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
