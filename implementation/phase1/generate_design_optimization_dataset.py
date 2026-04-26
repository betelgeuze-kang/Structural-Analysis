#!/usr/bin/env python3
"""Generate a deterministic NPZ/JSON dataset for constrained design optimization."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import numpy as np

from cost_model import MemberCostInput, estimate_project_cost
from design_optimization_env import ACTION_SPECS_V2, LEGACY_ACTION_NAMES


ACTION_NAMES = list(LEGACY_ACTION_NAMES)
ACTION_INDEX = {name: idx for idx, name in enumerate(ACTION_NAMES)}
ACTION_NAMES_V2 = [name for name, _, _ in ACTION_SPECS_V2]
ACTION_FAMILY_PER_INDEX = [family for _, family, _ in ACTION_SPECS_V2]
ACTION_STAGE_PER_INDEX = [stage for _, _, stage in ACTION_SPECS_V2]
ACTION_INDEX_V2 = {name: idx for idx, name in enumerate(ACTION_NAMES_V2)}
LEGALITY_REASON_CODES = [
    "legal",
    "member_type_disallowed",
    "zone_disallowed",
    "story_band_disallowed",
    "robustness_margin_low",
    "multi_hazard_margin_low",
    "governing_clause_locked",
    "group_variance_low",
    "merge_similarity_low",
]
LEGALITY_REASON_INDEX = {name: idx for idx, name in enumerate(LEGALITY_REASON_CODES)}


CLAUSE_WEIGHT_PREFIXES = [
    ("KDS-RC-CONN-", 1.00),
    ("KDS-RC-FOUND-", 0.95),
    ("KDS-RC-WALL-", 0.92),
    ("KDS-RC-SLAB-", 0.88),
    ("KDS-RC-COL-", 0.90),
    ("KDS-RC-BEAM-", 0.85),
    ("KDS-STAB-", 0.82),
    ("KDS-INT-", 0.80),
    ("KDS-SHEAR-", 0.76),
    ("KDS-MOMENT-", 0.72),
    ("KDS-AXIAL-", 0.68),
    ("KDS-SVC-", 0.64),
]

RULE_FAMILY_THRESHOLD = {
    "rc_detail": 0.55,
    "strength_interaction": 0.65,
    "strength": 0.72,
    "serviceability": 0.60,
    "stability": 0.62,
}

FOUNDATION_TOKEN_RE = re.compile(
    r"\b(?:foundation|footing|pile\s*cap|mat|raft|pile|caisson)\b",
    re.IGNORECASE,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _element_node_ids(elem: dict) -> list[int]:
    conn = elem.get("node_ids") if isinstance(elem.get("node_ids"), list) else (
        elem.get("nodes") if isinstance(elem.get("nodes"), list) else []
    )
    out: list[int] = []
    for value in conn:
        try:
            out.append(int(value))
        except Exception:
            continue
    return out


def _plate_orientation(
    *,
    elem: dict,
    nodes_by_id: dict[int, dict],
) -> str:
    node_ids = _element_node_ids(elem)
    if len(node_ids) < 3:
        return "unknown"
    pts: list[np.ndarray] = []
    for node_id in node_ids[:3]:
        node = nodes_by_id.get(int(node_id))
        if not isinstance(node, dict):
            return "unknown"
        pts.append(
            np.asarray(
                [
                    float(node.get("x", 0.0)),
                    float(node.get("y", 0.0)),
                    float(node.get("z", 0.0)),
                ],
                dtype=np.float64,
            )
        )
    normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    norm = float(np.linalg.norm(normal))
    if norm <= 1.0e-9:
        return "unknown"
    nz = abs(float(normal[2])) / norm
    if nz < 0.25:
        return "vertical"
    if nz > 0.85:
        return "horizontal"
    return "tilted"


def _member_type_from_element(
    elem: dict,
    sections_by_id: dict[int, dict],
    nodes_by_id: dict[int, dict],
    *,
    semantic_group: str = "",
    group_plane_type: str = "",
) -> str:
    et = str(elem.get("type", "")).strip().upper()
    sec_id = int(elem.get("section_id", elem.get("section", -1)) or -1)
    sec = sections_by_id.get(sec_id, {})
    sec_name = str(sec.get("name", "")).strip().lower()
    sec_signature = _section_signature(sec).strip().lower()
    semantic_text = str(semantic_group).strip().lower()
    plane_type_text = str(group_plane_type).strip().lower()
    combined_text = " ".join(
        token
        for token in (
            sec_name,
            sec_signature,
            semantic_text,
            plane_type_text,
            str(elem.get("name", "")).strip().lower(),
        )
        if token
    )
    normalized_text = re.sub(r"[-_/]+", " ", combined_text)
    if FOUNDATION_TOKEN_RE.search(normalized_text):
        return "foundation"
    if et in {"BEAM", "TRUSS"}:
        node_ids = _element_node_ids(elem)
        if len(node_ids) >= 2:
            pts = []
            for node_id in node_ids[:2]:
                node = nodes_by_id.get(int(node_id))
                if not isinstance(node, dict):
                    pts = []
                    break
                pts.append(
                    (
                        float(node.get("x", 0.0)),
                        float(node.get("y", 0.0)),
                        float(node.get("z", 0.0)),
                    )
                )
            if len(pts) == 2:
                dx = float(pts[1][0] - pts[0][0])
                dy = float(pts[1][1] - pts[0][1])
                dz = float(pts[1][2] - pts[0][2])
                span = float((dx * dx + dy * dy + dz * dz) ** 0.5)
                vertical_ratio = abs(dz) / span if span > 1.0e-9 else 0.0
                zmin = min(float(pts[0][2]), float(pts[1][2]))
                zmax = max(float(pts[0][2]), float(pts[1][2]))
                if vertical_ratio >= 0.98 and zmin < -0.5 and zmax <= 0.1:
                    return "foundation"
    if et in {"BEAM", "TRUSS"}:
        return "beam"
    if et in {"ELASTICLINK", "LINK"}:
        return "connection"
    if et == "COMPTR":
        if any(token in combined_text for token in ("wall", "shear", "corewall", "core-wall")):
            return "wall"
        return "column"
    if et in {"PLATE", "WALL", "SHELL"}:
        if any(token in combined_text for token in ("wall", "shear", "corewall", "core-wall")):
            return "wall"
        if any(token in combined_text for token in ("slab", "deck", "floor", "roof")):
            return "slab"
        orientation = _plate_orientation(elem=elem, nodes_by_id=nodes_by_id)
        if orientation == "vertical":
            return "wall"
        if orientation == "horizontal":
            return "slab"
        if et == "WALL":
            return "wall"
        return "slab"
    return "column"


def _section_signature(section: dict) -> str:
    raw_tokens = section.get("raw_tokens") if isinstance(section.get("raw_tokens"), list) else []
    if raw_tokens:
        text = str(raw_tokens[0]).strip()
        if text:
            return text
    return str(section.get("name", "")).strip() or "default"


def _extract_section_depth(signature: str) -> float:
    nums = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", str(signature))]
    if not nums:
        return 0.0
    return float(max(nums))


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    arr = np.asarray(sorted(values), dtype=np.float64)
    return float(np.quantile(arr, q))


def _clause_weight(clause: str) -> float:
    text = str(clause).strip().upper()
    for prefix, weight in CLAUSE_WEIGHT_PREFIXES:
        if text.startswith(prefix):
            return float(weight)
    return 0.60


def _detail_penalty_ratio_from_check_rows(rows: list[dict]) -> tuple[float, str, int]:
    if not rows:
        return 0.0, "", 0
    scored: list[tuple[float, str]] = []
    for row in rows:
        dcr = float(row.get("dcr", 0.0) or 0.0)
        clause = str(row.get("clause", "") or "")
        rule_family = str(row.get("rule_family", "") or "").strip().lower()
        threshold = float(RULE_FAMILY_THRESHOLD.get(rule_family, 0.70))
        if dcr <= threshold:
            severity = 0.0
        else:
            severity = _clause_weight(clause) * (dcr - threshold) / max(1.0 - threshold, 1.0e-9)
        scored.append((float(severity), clause))
    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[: min(5, len(scored))]
    if not top:
        return 0.0, "", 0
    ratio = float(min(1.0, sum(v for v, _ in top) / max(len(top), 1)))
    governing_clause = str(top[0][1]) if top[0][0] > 0.0 else ""
    active_count = int(sum(1 for v, _ in scored if v > 0.0))
    return ratio, governing_clause, active_count


def _max_dcr_from_check_rows(rows: list[dict]) -> tuple[float, str]:
    if not rows:
        return 0.0, ""
    best = max(rows, key=lambda row: float(row.get("dcr", 0.0) or 0.0))
    return float(best.get("dcr", 0.0) or 0.0), str(best.get("component", "") or "")


def _governing_check_row(rows: list[dict]) -> dict:
    if not rows:
        return {}
    return max(rows, key=lambda row: float(row.get("dcr", 0.0) or 0.0))


def _family_clause_scale(
    *,
    member_type: str,
    zone_label: str,
    story_band: int,
    story_band_count: int,
    section_depth: float,
    clause: str,
) -> float:
    scale = 1.0
    zone = str(zone_label).strip().lower()
    if zone == "transfer":
        scale *= 1.25
    elif zone == "core":
        scale *= 1.12
    elif zone == "perimeter":
        scale *= 0.94
    mt = str(member_type).strip().lower()
    if mt in {"column", "wall", "foundation"}:
        scale *= 1.08
    elif mt == "slab":
        scale *= 0.92
    if story_band <= 1:
        scale *= 1.10
    elif story_band >= max(story_band_count - 2, 0):
        scale *= 0.94
    if float(section_depth) >= 1200.0:
        scale *= 1.05
    clause_text = str(clause).strip().upper()
    if clause_text.startswith("KDS-RC-CONN-") and mt == "connection":
        scale *= 1.10
    if clause_text.startswith("KDS-RC-WALL-") and mt == "wall":
        scale *= 1.08
    if clause_text.startswith("KDS-STAB-"):
        scale *= 1.06
    return float(scale)


def _member_local_proxy_fields(
    *,
    member_type: str,
    volume_m3: float,
    steel_mass: float,
    span_len: float,
    max_dcr: float,
    story_index: int,
    story_band: int,
    story_band_count: int,
    zone_label: str,
) -> dict[str, object]:
    mt = str(member_type).strip().lower()
    zone = str(zone_label).strip().lower()
    axial_scale = {
        "column": 420.0,
        "wall": 360.0,
        "beam": 160.0,
        "slab": 80.0,
        "foundation": 520.0,
        "connection": 60.0,
    }.get(mt, 120.0)
    shear_scale = {
        "column": 180.0,
        "wall": 220.0,
        "beam": 210.0,
        "slab": 70.0,
        "foundation": 150.0,
        "connection": 120.0,
    }.get(mt, 100.0)
    moment_scale = {
        "column": 95.0,
        "wall": 110.0,
        "beam": 130.0,
        "slab": 45.0,
        "foundation": 80.0,
        "connection": 35.0,
    }.get(mt, 60.0)
    zone_factor = {
        "transfer": 1.22,
        "core": 1.10,
        "perimeter": 0.92,
        "intermediate": 1.0,
    }.get(zone, 1.0)
    story_factor = 1.0 + 0.10 * max(float(story_band_count - max(story_band, 0)) / max(story_band_count, 1), 0.0)
    member_axial_kN = float(volume_m3 * axial_scale * zone_factor * story_factor)
    member_shear_y_kN = float(span_len * shear_scale * (0.70 + 0.25 * zone_factor))
    member_shear_z_kN = float(member_shear_y_kN * (0.88 if mt == "beam" else 0.72))
    member_moment_y_kNm = float(span_len * moment_scale * zone_factor * (1.0 + 0.15 * max_dcr))
    member_moment_z_kNm = float(member_moment_y_kNm * (0.82 if mt in {"beam", "column"} else 0.64))
    if max_dcr >= 1.10:
        hinge_state = "plastic_proxy"
    elif max_dcr >= 0.90:
        hinge_state = "yielding_proxy"
    else:
        hinge_state = "elastic_proxy"
    member_plastic_rotation_rad = float(max(max_dcr - 1.0, 0.0) * 0.012)
    story_drift_contribution_pct = float(
        np.clip(
            (0.05 + 0.08 * max_dcr)
            * zone_factor
            * (1.15 if mt in {"column", "wall"} else 0.85 if mt == "slab" else 1.0),
            0.01,
            0.85,
        )
    )
    sensitivity_base = 0.30 + 0.45 * max_dcr + 0.18 * zone_factor
    return {
        "member_axial_kN": member_axial_kN,
        "member_shear_y_kN": member_shear_y_kN,
        "member_shear_z_kN": member_shear_z_kN,
        "member_moment_y_kNm": member_moment_y_kNm,
        "member_moment_z_kNm": member_moment_z_kNm,
        "member_hinge_state": hinge_state,
        "member_hinge_state_source": "proxy",
        "member_plastic_rotation_rad": member_plastic_rotation_rad,
        "member_story_drift_contribution_pct": story_drift_contribution_pct,
        "member_local_sensitivity_dcr": float(np.clip(sensitivity_base, 0.05, 1.80)),
        "member_local_sensitivity_drift": float(np.clip(story_drift_contribution_pct * 1.6, 0.02, 1.50)),
        "member_local_sensitivity_cost": float(np.clip(steel_mass / max(volume_m3 * 1000.0, 1.0), 0.02, 1.50)),
        "member_local_sensitivity_constructability": float(np.clip((0.18 + 0.40 * zone_factor + 0.15 * max_dcr), 0.05, 1.80)),
    }


def _group_topology_fields(
    *,
    group_id: str,
    member_type: str,
    zone_label: str,
    story_band: int,
    exact_family_key: str,
    max_dcr: float,
    detailing_violation_ratio: float,
    member_local_sensitivity_dcr: float,
    member_local_sensitivity_drift: float,
) -> dict[str, object]:
    group_family_key = f"{member_type}:{zone_label}:SB{story_band:02d}:{exact_family_key}"
    group_variance_score = float(
        np.clip(
            0.12
            + 0.35 * abs(float(member_local_sensitivity_dcr) - float(member_local_sensitivity_drift))
            + 0.25 * max(float(max_dcr) - 0.85, 0.0)
            + 0.18 * float(detailing_violation_ratio),
            0.0,
            1.25,
        )
    )
    group_merge_similarity_score = float(
        np.clip(
            1.05
            - 0.22 * max(float(max_dcr) - 1.0, 0.0)
            - 0.18 * float(detailing_violation_ratio),
            0.0,
            1.0,
        )
    )
    split_candidate_id = f"{group_id}:split" if group_variance_score > 0.18 else ""
    merge_candidate_id = f"{group_id}:merge" if group_merge_similarity_score >= 0.90 else ""
    return {
        "group_parent_id": str(group_id),
        "group_split_candidate_id": split_candidate_id,
        "group_merge_candidate_id": merge_candidate_id,
        "group_family_key": group_family_key,
        "group_variance_score": group_variance_score,
        "group_merge_similarity_score": group_merge_similarity_score,
    }


def _action_v2_legality(
    *,
    row: dict[str, object],
) -> tuple[np.ndarray, np.ndarray]:
    member_type = str(row.get("member_type", "")).strip().lower()
    zone = str(row.get("zone", "")).strip().lower()
    story_band = int(row.get("story_band", 0) or 0)
    robustness = float(row.get("robustness_margin", 0.0) or 0.0)
    multi_hazard = float(row.get("multi_hazard_margin", 0.0) or 0.0)
    clause = str(row.get("member_governing_clause", row.get("detailing_governing_clause", "")) or "").upper()
    variance = float(row.get("group_variance_score", 0.0) or 0.0)
    merge_similarity = float(row.get("group_merge_similarity_score", 0.0) or 0.0)
    legal = np.ones(len(ACTION_NAMES_V2), dtype=np.bool_)
    reasons = np.zeros(len(ACTION_NAMES_V2), dtype=np.int32)

    for idx, action_name in enumerate(ACTION_NAMES_V2):
        reason = "legal"
        allow = True
        if action_name.startswith("beam_section") and member_type not in {"beam", "column"}:
            allow = False
            reason = "member_type_disallowed"
        elif action_name.startswith("wall_thickness") and not (member_type == "wall" or (member_type == "column" and zone in {"core", "transfer"})):
            allow = False
            reason = "member_type_disallowed"
        elif action_name.startswith("slab_thickness") and member_type != "slab":
            allow = False
            reason = "member_type_disallowed"
        elif action_name.startswith("coupling_beam") and not (member_type == "beam" and zone in {"core", "transfer"}):
            allow = False
            reason = "zone_disallowed"
        elif action_name.startswith("core_wall") and not (member_type == "wall" and zone == "core"):
            allow = False
            reason = "zone_disallowed"
        elif action_name.startswith("perimeter_frame") and not (member_type in {"beam", "column"} and zone == "perimeter"):
            allow = False
            reason = "zone_disallowed"
        elif action_name.startswith("connection_detailing") and member_type not in {"connection", "beam", "column"}:
            allow = False
            reason = "member_type_disallowed"
        elif action_name.startswith("anchorage") and member_type not in {"beam", "column", "wall", "foundation", "connection"}:
            allow = False
            reason = "member_type_disallowed"
        elif action_name.startswith("splice") and member_type not in {"beam", "column", "wall", "slab"}:
            allow = False
            reason = "member_type_disallowed"
        elif action_name == "group_split" and variance <= 0.18:
            allow = False
            reason = "group_variance_low"
        elif action_name == "group_merge" and merge_similarity < 0.90:
            allow = False
            reason = "merge_similarity_low"

        if allow and story_band <= 0 and action_name.endswith("_down") and member_type in {"column", "wall"} and action_name not in {"beam_section_down", "wall_thickness_down", "connection_detailing_down"}:
            allow = False
            reason = "story_band_disallowed"
        if allow and robustness < 0.04 and action_name.endswith("_down") and action_name not in {"beam_section_down", "wall_thickness_down"}:
            allow = False
            reason = "robustness_margin_low"
        if allow and multi_hazard < 0.06 and action_name.endswith("_down") and action_name not in {"beam_section_down", "wall_thickness_down"}:
            allow = False
            reason = "multi_hazard_margin_low"
        if allow and clause.startswith("KDS-RC-CONN-") and action_name in {"detailing_down", "connection_detailing_down"}:
            allow = False
            reason = "governing_clause_locked"

        legal[idx] = bool(allow)
        reasons[idx] = int(LEGALITY_REASON_INDEX[reason])
    return legal, reasons


def _story_index_for_element(node_ids: list[int], nodes_by_id: dict[int, dict], z_levels: list[float]) -> tuple[int, float]:
    z_values = [float(nodes_by_id[nid]["z"]) for nid in node_ids if nid in nodes_by_id]
    if not z_values:
        return 0, 0.0
    centroid_z = float(sum(z_values) / len(z_values))
    if not z_levels:
        return 0, centroid_z
    nearest = min(range(len(z_levels)), key=lambda i: abs(z_levels[i] - centroid_z))
    return int(nearest), centroid_z


def _normalize_group_name(name: str) -> str:
    text = re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_")
    return text or "UNGROUPED"


def _semantic_group_profile_scale(name: str, story_index: int, zone_label: str, member_type: str) -> float:
    text = _normalize_group_name(name).upper()
    scale = 1.0
    match = re.search(r"(\d+)", text)
    if match:
        try:
            token_story = int(match.group(1))
            if abs(token_story - int(story_index)) <= 1:
                scale *= 1.08
            elif token_story <= max(int(story_index), 1):
                scale *= 1.04
        except Exception:
            pass
    if "CORE" in text:
        scale *= 1.08
    if "OUT" in text or "PERI" in text:
        scale *= 0.97
    if "TR" in text or "TRANSFER" in text:
        scale *= 1.12
    if str(zone_label).strip().lower() == "transfer":
        scale *= 1.04
    if str(member_type).strip().lower() in {"column", "wall", "foundation"}:
        scale *= 1.02
    return float(scale)


def _build_combination_provenance_maps(code_check: dict) -> tuple[dict[str, dict[str, object]], dict[str, float]]:
    provenance_rows = code_check.get("combination_provenance_rows") if isinstance(code_check.get("combination_provenance_rows"), list) else []
    combination_rows = code_check.get("combination_rows") if isinstance(code_check.get("combination_rows"), list) else []
    by_kds_name: dict[str, dict[str, object]] = {}
    risk_by_runtime_name: dict[str, float] = {}
    combo_metrics_by_kds: dict[str, dict[str, float]] = {}
    combo_buckets: dict[str, list[float]] = defaultdict(list)
    for row in combination_rows:
        if not isinstance(row, dict):
            continue
        combo_buckets[str(row.get("combination", "")).strip()].append(float(row.get("dcr", 0.0) or 0.0))
    for combo_name, values in combo_buckets.items():
        if not values:
            continue
        combo_metrics_by_kds[combo_name] = {
            "peak_dcr": float(max(values)),
            "avg_dcr": float(sum(values) / max(len(values), 1)),
        }
    for row in provenance_rows:
        if not isinstance(row, dict):
            continue
        kds_name = str(row.get("kds_name", "")).strip()
        runtime_name = str(row.get("matched_runtime_name", "")).strip()
        match_score = float(row.get("match_score", 0.0) or 0.0)
        kds_map = row.get("kds_factor_map") if isinstance(row.get("kds_factor_map"), dict) else {}
        runtime_map = row.get("matched_runtime_factor_map") if isinstance(row.get("matched_runtime_factor_map"), dict) else {}
        kds_mag = float(sum(abs(float(v)) for v in kds_map.values()))
        runtime_mag = float(sum(abs(float(v)) for v in runtime_map.values()))
        mag_gap = abs(runtime_mag - kds_mag) / max(kds_mag, 1.0e-9)
        combo_metrics = combo_metrics_by_kds.get(kds_name, {})
        peak_dcr = float(combo_metrics.get("peak_dcr", 0.0))
        avg_dcr = float(combo_metrics.get("avg_dcr", 0.0))
        risk = 1.0 + (1.0 - min(max(match_score, 0.0), 1.0)) * 0.75 + min(mag_gap, 2.0) * 0.40
        risk *= 1.0 + max(peak_dcr - 1.0, 0.0) * 0.70 + avg_dcr * 0.12
        if "ENV" in runtime_name.upper():
            risk *= 1.05
        payload = {
            "kds_name": kds_name,
            "runtime_name": runtime_name,
            "match_score": float(match_score),
            "risk_scale": float(risk),
            "peak_dcr": float(peak_dcr),
            "avg_dcr": float(avg_dcr),
            "runtime_factor_map": {str(k): float(v) for k, v in runtime_map.items()},
            "kds_factor_map": {str(k): float(v) for k, v in kds_map.items()},
        }
        if kds_name:
            by_kds_name[kds_name] = payload
        if runtime_name:
            risk_by_runtime_name[runtime_name] = max(float(risk_by_runtime_name.get(runtime_name, 0.0)), float(risk))
    return by_kds_name, risk_by_runtime_name


def _zone_for_centroid(x: float, y: float, center_x: float, center_y: float, max_radius: float) -> str:
    dx = float(x - center_x)
    dy = float(y - center_y)
    radius = (dx * dx + dy * dy) ** 0.5
    normalized = radius / max(max_radius, 1.0e-6)
    if normalized <= 0.33:
        return "core"
    if normalized >= 0.72:
        return "perimeter"
    return "intermediate"


def _build_action_mask_row(row: dict[str, object]) -> np.ndarray:
    mask = np.ones(len(ACTION_NAMES), dtype=np.bool_)
    member_type = str(row.get("member_type", "")).strip().lower()
    zone_label = str(row.get("zone", "")).strip().lower()
    max_dcr = float(row.get("max_dcr", 0.0) or 0.0)
    detail_ratio = float(row.get("detailing_violation_ratio", 0.0) or 0.0)
    robustness_margin = float(row.get("robustness_margin", 0.0) or 0.0)
    multi_hazard_margin = float(row.get("multi_hazard_margin", 0.0) or 0.0)
    combo_risk = float(row.get("combination_risk_scale", 1.0) or 1.0)

    if member_type == "connection":
        mask[ACTION_INDEX["rebar_down"]] = False
        mask[ACTION_INDEX["rebar_up"]] = False
        mask[ACTION_INDEX["thickness_down"]] = False
        mask[ACTION_INDEX["thickness_up"]] = False
        mask[ACTION_INDEX["detailing_down"]] = bool(max_dcr < 0.25 and detail_ratio < 0.08)
        mask[ACTION_INDEX["detailing_up"]] = True
        return mask

    if member_type == "foundation":
        mask[ACTION_INDEX["rebar_down"]] = bool(max_dcr < 0.40 and robustness_margin > 0.65 and combo_risk < 1.10)
        mask[ACTION_INDEX["thickness_down"]] = False
        mask[ACTION_INDEX["detailing_down"]] = bool(detail_ratio < 0.06 and max_dcr < 0.35)
        mask[ACTION_INDEX["rebar_up"]] = True
        mask[ACTION_INDEX["thickness_up"]] = True
        mask[ACTION_INDEX["detailing_up"]] = True
        return mask

    if member_type == "column":
        mask[ACTION_INDEX["rebar_down"]] = bool(
            zone_label in {"perimeter", "intermediate"}
            and max_dcr < 0.52
            and robustness_margin > 0.42
            and combo_risk < 1.18
        )
        mask[ACTION_INDEX["thickness_down"]] = bool(
            zone_label == "perimeter"
            and max_dcr < 0.44
            and robustness_margin > 0.48
            and combo_risk < 1.12
        )
        mask[ACTION_INDEX["detailing_down"]] = bool(
            zone_label in {"perimeter", "intermediate"} and detail_ratio < 0.10 and max_dcr < 0.58
        )
        return mask

    if member_type == "wall":
        mask[ACTION_INDEX["rebar_down"]] = bool(
            zone_label not in {"core", "transfer"}
            and max_dcr < 0.70
            and robustness_margin > 0.32
            and combo_risk < 1.26
        )
        mask[ACTION_INDEX["thickness_down"]] = bool(
            zone_label in {"perimeter", "intermediate"}
            and max_dcr < 0.60
            and robustness_margin > 0.18
            and combo_risk < 1.24
        )
        mask[ACTION_INDEX["detailing_down"]] = bool(detail_ratio < 0.12 and max_dcr < 0.68)
        return mask

    if member_type == "slab":
        mask[ACTION_INDEX["rebar_down"]] = bool(
            zone_label in {"perimeter", "intermediate"}
            and max_dcr < 0.74
            and robustness_margin > 0.24
            and combo_risk < 1.30
        )
        mask[ACTION_INDEX["thickness_down"]] = bool(
            zone_label in {"perimeter", "intermediate"}
            and max_dcr < 0.66
            and robustness_margin > 0.18
            and combo_risk < 1.30
        )
        mask[ACTION_INDEX["detailing_down"]] = bool(detail_ratio < 0.14 and max_dcr < 0.66)
        return mask

    if member_type == "beam":
        mask[ACTION_INDEX["rebar_down"]] = bool(
            zone_label != "transfer"
            and max_dcr < 0.94
            and robustness_margin > 0.18
            and combo_risk < 1.34
        )
        mask[ACTION_INDEX["thickness_down"]] = bool(
            zone_label not in {"transfer", "core"}
            and max_dcr < 0.88
            and robustness_margin > 0.14
            and combo_risk < 1.32
        )
        mask[ACTION_INDEX["detailing_down"]] = bool(detail_ratio < 0.24 and max_dcr < 0.90)
        return mask

    return mask


def _aggregate_group_action_mask(group_rows: list[dict]) -> np.ndarray:
    if not group_rows:
        return np.ones(len(ACTION_NAMES), dtype=np.bool_)
    row_masks = np.stack([_build_action_mask_row(row) for row in group_rows], axis=0)
    weights = []
    for row in group_rows:
        w = 1.0
        w += 0.25 * max(float(row.get("max_dcr", 0.0) or 0.0), 0.0)
        w += 0.10 * max(float(row.get("combination_risk_scale", 1.0) or 1.0) - 1.0, 0.0)
        zone = str(row.get("zone", "")).strip().lower()
        if zone in {"transfer", "core"}:
            w += 0.20
        weights.append(w)
    weight_arr = np.asarray(weights, dtype=np.float64).reshape(-1, 1)
    frac = np.sum(row_masks.astype(np.float64) * weight_arr, axis=0) / np.maximum(np.sum(weight_arr), 1.0e-9)
    group_max_dcr = max(float(row.get("max_dcr", 0.0) or 0.0) for row in group_rows)
    group_min_robust = min(float(row.get("robustness_margin", 0.0) or 0.0) for row in group_rows)
    group_min_multi = min(float(row.get("multi_hazard_margin", 0.0) or 0.0) for row in group_rows)
    group_member_type = str(group_rows[0].get("member_type", "")).strip().lower()
    group_zone = str(group_rows[0].get("zone", "")).strip().lower()
    group_story_band = int(group_rows[0].get("story_band", 0) or 0)
    legal = np.ones(len(ACTION_NAMES), dtype=np.bool_)
    legal[ACTION_INDEX["rebar_up"]] = bool(frac[ACTION_INDEX["rebar_up"]] >= 0.05)
    legal[ACTION_INDEX["thickness_up"]] = bool(frac[ACTION_INDEX["thickness_up"]] >= 0.05)
    legal[ACTION_INDEX["detailing_up"]] = bool(frac[ACTION_INDEX["detailing_up"]] >= 0.05)
    legal[ACTION_INDEX["rebar_down"]] = bool(
        frac[ACTION_INDEX["rebar_down"]] >= 0.28
        and group_max_dcr < 1.04
        and group_min_robust > 0.06
    )
    legal[ACTION_INDEX["thickness_down"]] = bool(
        frac[ACTION_INDEX["thickness_down"]] >= 0.24
        and group_max_dcr < 1.00
    )
    legal[ACTION_INDEX["detailing_down"]] = bool(
        frac[ACTION_INDEX["detailing_down"]] >= 0.22
        and group_max_dcr < 1.02
    )
    # Lower-story intermediate beam groups can be overly constrained by weighted aggregation
    # even when every local demand metric is comfortably below limit.
    if (
        group_member_type == "beam"
        and group_zone == "intermediate"
        and group_story_band <= 1
        and group_max_dcr < 0.10
        and group_min_robust > 0.08
        and group_min_multi > 0.08
    ):
        legal[ACTION_INDEX["rebar_down"]] = True
        legal[ACTION_INDEX["thickness_down"]] = True
        legal[ACTION_INDEX["detailing_down"]] = True
    return legal


def _build_rows(model: dict, code_check: dict, pbd: dict, ndtha_residual: dict) -> tuple[list[MemberCostInput], dict[str, float], list[dict]]:
    mdl = model.get("model") if isinstance(model.get("model"), dict) else {}
    elements = mdl.get("elements") if isinstance(mdl.get("elements"), list) else []
    sections = mdl.get("sections") if isinstance(mdl.get("sections"), list) else []
    nodes = mdl.get("nodes") if isinstance(mdl.get("nodes"), list) else []
    metadata = mdl.get("metadata") if isinstance(mdl.get("metadata"), dict) else {}
    sections_by_id = {int(sec.get("id", -1)): sec for sec in sections if isinstance(sec, dict)}
    nodes_by_id = {int(node.get("id", -1)): node for node in nodes if isinstance(node, dict)}
    member_cluster_by_element_id: dict[int, int] = {}
    for member_row in metadata.get("members", []) if isinstance(metadata.get("members"), list) else []:
        if not isinstance(member_row, dict):
            continue
        member_cluster_id = int(member_row.get("id", -1) or -1)
        element_seed = int(member_row.get("element_seed", -1) or -1)
        if element_seed > 0:
            member_cluster_by_element_id[element_seed] = member_cluster_id
        for elem_id in member_row.get("element_ids", []) if isinstance(member_row.get("element_ids"), list) else []:
            try:
                member_cluster_by_element_id[int(elem_id)] = member_cluster_id
            except Exception:
                continue
    group_labels_by_element_id: dict[int, str] = {}
    group_plane_type_by_element_id: dict[int, str] = {}
    for group_row in metadata.get("groups", []) if isinstance(metadata.get("groups"), list) else []:
        if not isinstance(group_row, dict):
            continue
        group_name = _normalize_group_name(str(group_row.get("name", "")))
        group_plane_type = str(group_row.get("plane_type", "")).strip()
        for elem_id in group_row.get("element_ids", []) if isinstance(group_row.get("element_ids"), list) else []:
            try:
                elem_id_int = int(elem_id)
            except Exception:
                continue
            group_labels_by_element_id[elem_id_int] = group_name
            if group_plane_type:
                group_plane_type_by_element_id[elem_id_int] = group_plane_type
    z_levels = sorted({float(node.get("z", 0.0)) for node in nodes if isinstance(node, dict)})
    x_values = [float(node.get("x", 0.0)) for node in nodes if isinstance(node, dict)]
    y_values = [float(node.get("y", 0.0)) for node in nodes if isinstance(node, dict)]
    center_x = float((min(x_values) + max(x_values)) * 0.5) if x_values else 0.0
    center_y = float((min(y_values) + max(y_values)) * 0.5) if y_values else 0.0
    max_radius = max(
        (
            ((float(node.get("x", 0.0)) - center_x) ** 2 + (float(node.get("y", 0.0)) - center_y) ** 2) ** 0.5
            for node in nodes
            if isinstance(node, dict)
        ),
        default=1.0,
    )

    member_rows = code_check.get("rows") if isinstance(code_check.get("rows"), list) else []
    per_member: dict[str, dict] = {str(r.get("member_id", "")): r for r in member_rows if isinstance(r, dict)}
    member_check_rows = code_check.get("member_check_rows") if isinstance(code_check.get("member_check_rows"), list) else []
    member_clause_rows: dict[str, list[dict]] = defaultdict(list)
    member_type_clause_rows: dict[str, list[dict]] = defaultdict(list)
    combo_provenance_by_kds, combo_risk_by_runtime = _build_combination_provenance_maps(code_check)
    for row in member_check_rows:
        if not isinstance(row, dict):
            continue
        member_clause_rows[str(row.get("member_id", ""))].append(row)
        member_type_clause_rows[str(row.get("member_type", "")).strip().lower()].append(row)

    pbd_metrics = pbd.get("metrics") if isinstance(pbd.get("metrics"), dict) else {}
    ndtha_summary = ndtha_residual.get("summary") if isinstance(ndtha_residual.get("summary"), dict) else {}
    drift_envelope_max_pct = float(pbd_metrics.get("drift_envelope_max_pct", 0.0))
    residual_drift_pct_max_abs = float(ndtha_summary.get("residual_drift_ratio_pct_max_abs", 0.0))
    wind_residual_drift_pct_max_abs = float(pbd_metrics.get("wind_residual_drift_pct_max_abs", 0.0))
    ssi_residual_drift_pct_max_abs = float(pbd_metrics.get("ssi_residual_drift_pct_max_abs", 0.0))

    member_metadata: list[dict] = []
    depth_by_type: dict[str, list[float]] = {}
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        member_type = _member_type_from_element(
            elem,
            sections_by_id,
            nodes_by_id,
            semantic_group=str(group_labels_by_element_id.get(int(elem.get("id", -1) or -1), "")).strip(),
            group_plane_type=str(group_plane_type_by_element_id.get(int(elem.get("id", -1) or -1), "")).strip(),
        )
        sec_id = int(elem.get("section_id", elem.get("section", -1)) or -1)
        sec = sections_by_id.get(sec_id, {})
        signature = _section_signature(sec)
        depth = _extract_section_depth(signature)
        conn = elem.get("node_ids") if isinstance(elem.get("node_ids"), list) else (elem.get("nodes") if isinstance(elem.get("nodes"), list) else [])
        story_index, centroid_z = _story_index_for_element([int(v) for v in conn], nodes_by_id, z_levels)
        xy_nodes = [nodes_by_id[int(v)] for v in conn if int(v) in nodes_by_id]
        centroid_x = float(sum(float(n["x"]) for n in xy_nodes) / len(xy_nodes)) if xy_nodes else center_x
        centroid_y = float(sum(float(n["y"]) for n in xy_nodes) / len(xy_nodes)) if xy_nodes else center_y
        member_metadata.append(
            {
                "element": elem,
                "member_type": member_type,
                "section_signature": signature,
                "section_depth": depth,
                "story_index": story_index,
                "centroid_z": centroid_z,
                "centroid_x": centroid_x,
                "centroid_y": centroid_y,
            }
        )
        depth_by_type.setdefault(member_type, []).append(depth)
    transfer_threshold = {k: _quantile(v, 0.85) for k, v in depth_by_type.items()}
    story_band_divisor = max(1, int(round(max(len(z_levels), 1) / 10.0)))
    story_band_count = max(1, int((max(len(z_levels) - 1, 0) // story_band_divisor) + 1))
    profile_cache: dict[str, dict[str, object]] = {}
    inferred_cluster_profile: dict[tuple[str, str, str, int], int] = {}
    cluster_votes: dict[tuple[str, str, str, int], list[int]] = defaultdict(list)
    for item in member_metadata:
        elem = item["element"]
        elem_id = int(elem.get("id", -1) or -1)
        member_cluster_id = int(member_cluster_by_element_id.get(elem_id, -1))
        if member_cluster_id <= 0:
            continue
        story_index = int(item["story_index"])
        story_band = int(story_index // story_band_divisor)
        member_type = str(item["member_type"])
        zone = _zone_for_centroid(
            x=float(item["centroid_x"]),
            y=float(item["centroid_y"]),
            center_x=center_x,
            center_y=center_y,
            max_radius=max_radius,
        )
        is_transfer = bool(
            member_type in {"beam", "column"}
            and float(item["section_depth"]) > 0.0
            and float(item["section_depth"]) >= float(transfer_threshold.get(member_type, 0.0))
            and story_index <= max(len(z_levels) // 2, 1)
        )
        zone_label = "transfer" if is_transfer else zone
        semantic_group = str(group_labels_by_element_id.get(elem_id, "")).strip()
        cluster_votes[(semantic_group, member_type, zone_label, story_band)].append(member_cluster_id)
    for key, values in cluster_votes.items():
        if not values:
            continue
        counts = defaultdict(int)
        for value in values:
            counts[int(value)] += 1
        inferred_cluster_profile[key] = max(sorted(counts.keys()), key=lambda v: (counts[v], -v))

    costs: list[MemberCostInput] = []
    rows: list[dict] = []
    for item in member_metadata:
        elem = item["element"]
        member_id = str(elem.get("id", ""))
        member_type = str(item["member_type"])
        conn = elem.get("node_ids") if isinstance(elem.get("node_ids"), list) else (elem.get("nodes") if isinstance(elem.get("nodes"), list) else [])
        node_count = max(len(conn), 2)
        span_len = float(max(node_count - 1, 1)) * 3.2
        sec_id = int(elem.get("section_id", elem.get("section", -1)) or -1)
        section_name = str(sections_by_id.get(sec_id, {}).get("name", ""))
        section_signature = str(item["section_signature"])
        volume_m3 = 0.12 * span_len if member_type in {"beam", "column"} else 0.25 * span_len
        steel_mass = 18.0 * span_len if member_type in {"beam", "column", "connection"} else 6.0 * span_len
        base_rebar = {
            "beam": 0.018,
            "column": 0.024,
            "wall": 0.014,
            "slab": 0.010,
            "foundation": 0.022,
            "connection": 0.006,
        }.get(member_type, 0.015)
        congestion = {
            "beam": 0.25,
            "column": 0.35,
            "wall": 0.20,
            "slab": 0.15,
            "foundation": 0.40,
            "connection": 0.10,
        }.get(member_type, 0.2)
        story_index = int(item["story_index"])
        story_band = int(story_index // story_band_divisor)
        zone = _zone_for_centroid(
            x=float(item["centroid_x"]),
            y=float(item["centroid_y"]),
            center_x=center_x,
            center_y=center_y,
            max_radius=max_radius,
        )
        is_transfer = bool(
            member_type in {"beam", "column"}
            and float(item["section_depth"]) > 0.0
            and float(item["section_depth"]) >= float(transfer_threshold.get(member_type, 0.0))
            and story_index <= max(len(z_levels) // 2, 1)
        )
        zone_label = "transfer" if is_transfer else zone
        member_cluster_id = int(member_cluster_by_element_id.get(int(elem.get("id", -1) or -1), -1))
        semantic_group = str(group_labels_by_element_id.get(int(elem.get("id", -1) or -1), "")).strip()
        inferred_member_cluster_id = -1
        if member_cluster_id <= 0:
            inferred_member_cluster_id = int(
                inferred_cluster_profile.get((semantic_group, member_type, zone_label, story_band), -1)
            )
            if inferred_member_cluster_id > 0:
                member_cluster_id = int(inferred_member_cluster_id)
        exact_family_key = f"{member_type}:{zone_label}:SB{story_band:02d}:{section_signature or section_name or 'default'}"
        if semantic_group:
            exact_family_key = f"G{semantic_group}:{exact_family_key}"
        if member_cluster_id > 0:
            exact_family_key = f"M{member_cluster_id}:{exact_family_key}"
        lap_splice_ratio = {
            "beam": 0.08,
            "column": 0.18,
            "wall": 0.14,
            "slab": 0.05,
            "foundation": 0.10,
            "connection": 0.02,
        }.get(member_type, 0.06)
        if story_index <= max(len(z_levels) // 4, 1):
            lap_splice_ratio += 0.04
        anchorage_complexity = {
            "core": 0.30,
            "intermediate": 0.18,
            "perimeter": 0.22,
            "transfer": 0.40,
        }.get(zone_label, 0.18)
        thickness_scale = {
            "beam": 1.00,
            "column": 1.02,
            "wall": 1.08,
            "slab": 0.96,
            "foundation": 1.10,
            "connection": 0.92,
        }.get(member_type, 1.0)
        cost_in = MemberCostInput(
            member_id=member_id,
            member_type=member_type,
            length_m=float(span_len),
            volume_m3=float(volume_m3),
            steel_mass_kg=float(steel_mass),
            rebar_ratio=float(base_rebar),
            congestion_index=float(congestion),
            lap_splice_ratio=float(lap_splice_ratio),
            anchorage_complexity=float(anchorage_complexity),
        )
        code_row = per_member.get(member_id, {})
        max_dcr = float(code_row.get("max_dcr", 0.0))
        governing_component = str(code_row.get("governing_component", ""))
        if member_clause_rows.get(member_id):
            clause_rows = member_clause_rows.get(member_id, [])
            detailing_violation_ratio, detailing_governing_clause, detailing_active_clause_count = _detail_penalty_ratio_from_check_rows(clause_rows)
            max_dcr, governing_component = _max_dcr_from_check_rows(clause_rows)
            governing_row = _governing_check_row(clause_rows)
            detailing_mapping_mode = "member_id_exact"
        else:
            semantic_scale = _semantic_group_profile_scale(
                semantic_group,
                story_index=int(story_index),
                zone_label=zone_label,
                member_type=member_type,
            )
            if inferred_member_cluster_id > 0:
                profile_mode = "member_cluster_story_exact_profile"
                profile_key = f"inferred_cluster:{member_cluster_id}:{semantic_group}:{zone_label}:SB{story_band:02d}:{section_signature or section_name or 'default'}"
            elif member_cluster_id > 0:
                profile_mode = "member_cluster_exact_profile"
                profile_key = f"cluster:{member_cluster_id}:{exact_family_key}"
            elif semantic_group:
                profile_mode = "semantic_group_exact_profile"
                profile_key = f"semantic:{semantic_group}:{member_type}:{zone_label}:SB{story_band:02d}:{section_signature or section_name or 'default'}"
            else:
                profile_mode = "exact_family_profile"
                profile_key = exact_family_key
            if profile_key not in profile_cache:
                source_rows = member_type_clause_rows.get(member_type, [])
                adjusted_rows: list[dict] = []
                for row in source_rows:
                    scaled = dict(row)
                    scaled["dcr"] = float(row.get("dcr", 0.0)) * _family_clause_scale(
                        member_type=member_type,
                        zone_label=zone_label,
                        story_band=story_band,
                        story_band_count=story_band_count,
                        section_depth=float(item["section_depth"]),
                        clause=str(row.get("clause", "")),
                    ) * float(semantic_scale)
                    adjusted_rows.append(scaled)
                profile_cache[profile_key] = {
                    "detail": _detail_penalty_ratio_from_check_rows(adjusted_rows),
                    "max_dcr": _max_dcr_from_check_rows(adjusted_rows),
                    "governing_row": _governing_check_row(adjusted_rows),
                }
            cached = profile_cache[profile_key]
            detailing_violation_ratio, detailing_governing_clause, detailing_active_clause_count = cached["detail"]
            max_dcr, governing_component = cached["max_dcr"]
            governing_row = cached["governing_row"]
            detailing_mapping_mode = profile_mode
        governing_combination = str(governing_row.get("combination", "") or "")
        provenance = combo_provenance_by_kds.get(governing_combination, {})
        combination_match_score = float(provenance.get("match_score", 0.55 if governing_combination else 0.50))
        combination_runtime_name = str(provenance.get("runtime_name", "") or "")
        combination_risk_scale = float(
            provenance.get(
                "risk_scale",
                max(float(combo_risk_by_runtime.get(combination_runtime_name, 1.0)), 1.0),
            )
        )
        detailing_quality = float(np.clip(1.10 - 0.55 * float(detailing_violation_ratio), 0.55, 1.20))
        member_governing_clause = str(governing_row.get("clause", "") or detailing_governing_clause or "")
        member_governing_combo = str(governing_row.get("combination", "") or governing_combination or "")
        robustness_margin = float(
            np.clip(
                1.15
                - max(float(max_dcr) - 1.0, 0.0)
                - 0.18 * max(combination_risk_scale - 1.0, 0.0)
                - 0.08 * float(detailing_violation_ratio),
                0.0,
                1.25,
            )
        )
        multi_hazard_margin = float(
            np.clip(
                1.20
                - 0.18 * max(drift_envelope_max_pct - 2.0, 0.0)
                - 0.22 * max(residual_drift_pct_max_abs - 0.5, 0.0)
                - 0.15 * max(wind_residual_drift_pct_max_abs - 0.05, 0.0)
                - 0.12 * max(ssi_residual_drift_pct_max_abs - 0.05, 0.0)
                - 0.10 * max(combination_risk_scale - 1.0, 0.0),
                0.0,
                1.25,
            )
        )
        member_local = _member_local_proxy_fields(
            member_type=member_type,
            volume_m3=float(volume_m3),
            steel_mass=float(steel_mass),
            span_len=float(span_len),
            max_dcr=float(max_dcr),
            story_index=int(story_index),
            story_band=int(story_band),
            story_band_count=int(story_band_count),
            zone_label=zone_label,
        )
        constructability_score = float(
            np.clip(
                0.35 * float(congestion)
                + 0.28 * float(detailing_violation_ratio)
                + 0.22 * float(anchorage_complexity)
                + 0.15 * float(lap_splice_ratio),
                0.0,
                1.5,
            )
        )
        detailing_complexity_score = float(
            np.clip(0.62 * float(detailing_violation_ratio) + 0.18 * float(anchorage_complexity), 0.0, 1.5)
        )
        anchorage_complexity_score = float(np.clip(float(anchorage_complexity), 0.0, 1.5))
        splice_burden_score = float(np.clip(float(lap_splice_ratio) * 2.0, 0.0, 1.5))
        overdesign_margin_score = float(max(1.0 - float(max_dcr), 0.0) * (1.0 + 0.25 * float(volume_m3)))
        material_reduction_potential_score = float(
            np.clip(overdesign_margin_score + 0.30 * float(robustness_margin) + 0.20 * float(member_local["member_local_sensitivity_cost"]), 0.0, 2.5)
        )
        row_group_id = f"S{story_band:02d}:{zone_label}:{semantic_group or 'nogroup'}:{member_type}:{section_signature or section_name or 'default'}"
        group_topology = _group_topology_fields(
            group_id=row_group_id,
            member_type=member_type,
            zone_label=zone_label,
            story_band=int(story_band),
            exact_family_key=exact_family_key,
            max_dcr=float(max_dcr),
            detailing_violation_ratio=float(detailing_violation_ratio),
            member_local_sensitivity_dcr=float(member_local["member_local_sensitivity_dcr"]),
            member_local_sensitivity_drift=float(member_local["member_local_sensitivity_drift"]),
        )
        cost_in = MemberCostInput(
            member_id=cost_in.member_id,
            member_type=cost_in.member_type,
            length_m=cost_in.length_m,
            volume_m3=cost_in.volume_m3,
            steel_mass_kg=cost_in.steel_mass_kg,
            rebar_ratio=cost_in.rebar_ratio,
            congestion_index=cost_in.congestion_index,
            lap_splice_ratio=cost_in.lap_splice_ratio,
            anchorage_complexity=cost_in.anchorage_complexity,
            detailing_violation_ratio=float(detailing_violation_ratio),
        )
        costs.append(cost_in)
        rows.append(
            {
                "member_id": member_id,
                "member_type": member_type,
                "section_name": section_name,
                "section_signature": section_signature,
                "story_index": int(story_index),
                "story_band": int(story_band),
                "zone": zone_label,
                "member_cluster_id": int(member_cluster_id),
                "member_cluster_inferred": bool(inferred_member_cluster_id > 0),
                "semantic_group": semantic_group,
                "exact_family_key": exact_family_key,
                "group_id": row_group_id,
                "rebar_ratio": float(base_rebar),
                "volume_m3": float(volume_m3),
                "steel_mass_kg": float(steel_mass),
                "congestion_index": float(congestion),
                "lap_splice_ratio": float(lap_splice_ratio),
                "anchorage_complexity": float(anchorage_complexity),
                "detailing_violation_ratio": float(detailing_violation_ratio),
                "detailing_quality": float(detailing_quality),
                "detailing_governing_clause": detailing_governing_clause,
                "detailing_active_clause_count": int(detailing_active_clause_count),
                "detailing_mapping_mode": detailing_mapping_mode,
                "thickness_scale": float(thickness_scale),
                "robustness_margin": float(robustness_margin),
                "multi_hazard_margin": float(multi_hazard_margin),
                "max_dcr": max_dcr,
                "governing_component": governing_component,
                "governing_combination": governing_combination,
                "combination_runtime_name": combination_runtime_name,
                "combination_match_score": float(combination_match_score),
                "combination_risk_scale": float(combination_risk_scale),
                "case_state_ref": "project_global_0",
                "member_governing_dcr": float(max_dcr),
                "member_governing_clause": member_governing_clause,
                "member_governing_combo": member_governing_combo,
                "constructability_score": constructability_score,
                "detailing_complexity_score": detailing_complexity_score,
                "anchorage_complexity_score": anchorage_complexity_score,
                "splice_burden_score": splice_burden_score,
                "overdesign_margin_score": overdesign_margin_score,
                "material_reduction_potential_score": material_reduction_potential_score,
                **member_local,
                **group_topology,
            }
        )
    totals = estimate_project_cost(costs)
    totals["drift_envelope_max_pct"] = drift_envelope_max_pct
    totals["residual_drift_pct_max_abs"] = residual_drift_pct_max_abs
    totals["wind_residual_drift_pct_max_abs"] = wind_residual_drift_pct_max_abs
    totals["ssi_residual_drift_pct_max_abs"] = ssi_residual_drift_pct_max_abs
    mapping_counts: dict[str, int] = defaultdict(int)
    cluster_mapped_count = 0
    cluster_inferred_count = 0
    semantic_group_mapped_count = 0
    for row in rows:
        mapping_counts[str(row.get("detailing_mapping_mode", ""))] += 1
        if int(row.get("member_cluster_id", -1)) > 0:
            cluster_mapped_count += 1
        if bool(row.get("member_cluster_inferred", False)):
            cluster_inferred_count += 1
        if str(row.get("semantic_group", "")).strip():
            semantic_group_mapped_count += 1
    totals["detail_mapping_mode_counts"] = {str(k): int(v) for k, v in sorted(mapping_counts.items())}
    totals["member_cluster_mapped_count"] = int(cluster_mapped_count)
    totals["member_cluster_inferred_count"] = int(cluster_inferred_count)
    totals["semantic_group_mapped_count"] = int(semantic_group_mapped_count)
    return costs, totals, rows


def _write_npz(path: Path, rows: list[dict], totals: dict[str, float]) -> dict[str, object]:
    group_ids = [str(r["group_id"]) for r in rows]
    unique_groups = sorted(set(group_ids))
    group_index = {name: i for i, name in enumerate(unique_groups)}
    unique_zones = sorted(set(str(r["zone"]) for r in rows))
    zone_index = {name: i for i, name in enumerate(unique_zones)}
    rows_by_group: dict[str, list[dict]] = defaultdict(list)
    member_type_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        rows_by_group[str(row["group_id"])].append(row)
        member_type_counts[str(row["member_type"])] += 1
    member_type_per_group = np.asarray([str(rows_by_group[g][0].get("member_type", "")) for g in unique_groups], dtype="<U32")
    zone_label_per_group = np.asarray([str(rows_by_group[g][0].get("zone", "")) for g in unique_groups], dtype="<U32")
    semantic_group_per_group = np.asarray([str(rows_by_group[g][0].get("semantic_group", "")) for g in unique_groups], dtype="<U96")
    section_name_per_group = np.asarray([str(rows_by_group[g][0].get("section_name", "")) for g in unique_groups], dtype="<U128")
    section_signature_per_group = np.asarray([str(rows_by_group[g][0].get("section_signature", "")) for g in unique_groups], dtype="<U128")
    story_band_per_group = np.asarray([int(rows_by_group[g][0].get("story_band", 0) or 0) for g in unique_groups], dtype=np.int32)
    member_governing_clause_per_group = np.asarray(
        [str(rows_by_group[g][0].get("member_governing_clause", "")) for g in unique_groups],
        dtype="<U128",
    )
    action_names = np.asarray(ACTION_NAMES, dtype="<U32")
    action_names_v2 = np.asarray(ACTION_NAMES_V2, dtype="<U48")
    action_mask_extended = np.ones((len(unique_groups), int(action_names.shape[0])), dtype=np.bool_)
    action_mask_v2 = np.ones((len(unique_groups), int(action_names_v2.shape[0])), dtype=np.bool_)
    action_legality_reason_matrix = np.zeros((len(unique_groups), int(action_names_v2.shape[0])), dtype=np.int32)
    action_mask_summary_counts = {name: 0 for name in ACTION_NAMES}
    action_mask_summary_counts_v2 = {name: 0 for name in ACTION_NAMES_V2}
    for name, idx in group_index.items():
        group_rows = rows_by_group.get(str(name), [])
        if not group_rows:
            continue
        legal_mask = _aggregate_group_action_mask(group_rows)
        action_mask_extended[idx, :] = legal_mask
        for action_name, action_idx in ACTION_INDEX.items():
            if bool(legal_mask[action_idx]):
                action_mask_summary_counts[action_name] += 1
        seed_row = dict(group_rows[0])
        group_legal_mask, group_reason_codes = _action_v2_legality(row=seed_row)
        action_mask_v2[idx, :] = group_legal_mask
        action_legality_reason_matrix[idx, :] = group_reason_codes
        for action_name, action_idx in ACTION_INDEX_V2.items():
            if bool(group_legal_mask[action_idx]):
                action_mask_summary_counts_v2[action_name] += 1
    action_mask = np.zeros((len(unique_groups), 2), dtype=np.bool_)
    action_mask[:, 0] = action_mask_extended[:, ACTION_INDEX["rebar_down"]]
    action_mask[:, 1] = action_mask_extended[:, ACTION_INDEX["rebar_up"]]
    case_state_ids = np.asarray(["project_global_0"], dtype="<U64")
    case_state_index_per_member = np.zeros(len(rows), dtype=np.int32)
    group_parent_id = np.asarray([str(rows_by_group[g][0].get("group_parent_id", g)) for g in unique_groups], dtype="<U160")
    group_split_candidate_id = np.asarray([str(rows_by_group[g][0].get("group_split_candidate_id", "")) for g in unique_groups], dtype="<U160")
    group_merge_candidate_id = np.asarray([str(rows_by_group[g][0].get("group_merge_candidate_id", "")) for g in unique_groups], dtype="<U160")
    group_family_key = np.asarray([str(rows_by_group[g][0].get("group_family_key", g)) for g in unique_groups], dtype="<U160")
    group_variance_score = np.asarray([float(rows_by_group[g][0].get("group_variance_score", 0.0) or 0.0) for g in unique_groups], dtype=np.float64)
    group_merge_similarity_score = np.asarray([float(rows_by_group[g][0].get("group_merge_similarity_score", 0.0) or 0.0) for g in unique_groups], dtype=np.float64)
    payload = {
        "member_ids": np.asarray([str(r["member_id"]) for r in rows], dtype="<U128"),
        "member_types": np.asarray([str(r["member_type"]) for r in rows], dtype="<U32"),
        "section_names": np.asarray([str(r["section_name"]) for r in rows], dtype="<U128"),
        "section_signatures": np.asarray([str(r["section_signature"]) for r in rows], dtype="<U128"),
        "exact_family_keys": np.asarray([str(r["exact_family_key"]) for r in rows], dtype="<U160"),
        "semantic_groups": np.asarray([str(r["semantic_group"]) for r in rows], dtype="<U96"),
        "group_ids": np.asarray(group_ids, dtype="<U128"),
        "group_index_per_member": np.asarray([int(group_index[g]) for g in group_ids], dtype=np.int32),
        "member_type_per_group": member_type_per_group,
        "zone_label_per_group": zone_label_per_group,
        "semantic_group_per_group": semantic_group_per_group,
        "section_name_per_group": section_name_per_group,
        "section_signature_per_group": section_signature_per_group,
        "story_band_per_group": story_band_per_group,
        "member_governing_clause_per_group": member_governing_clause_per_group,
        "story_index": np.asarray([int(r["story_index"]) for r in rows], dtype=np.int32),
        "story_band_index": np.asarray([int(r["story_band"]) for r in rows], dtype=np.int32),
        "zone_labels": np.asarray([str(r["zone"]) for r in rows], dtype="<U32"),
        "zone_index_per_member": np.asarray([int(zone_index[str(r["zone"])]) for r in rows], dtype=np.int32),
        "member_cluster_id": np.asarray([int(r["member_cluster_id"]) for r in rows], dtype=np.int32),
        "member_cluster_inferred": np.asarray([bool(r["member_cluster_inferred"]) for r in rows], dtype=np.bool_),
        "rebar_ratio": np.asarray([float(r["rebar_ratio"]) for r in rows], dtype=np.float64),
        "volume_m3": np.asarray([float(r["volume_m3"]) for r in rows], dtype=np.float64),
        "steel_mass_kg": np.asarray([float(r["steel_mass_kg"]) for r in rows], dtype=np.float64),
        "congestion_index": np.asarray([float(r["congestion_index"]) for r in rows], dtype=np.float64),
        "lap_splice_ratio": np.asarray([float(r["lap_splice_ratio"]) for r in rows], dtype=np.float64),
        "anchorage_complexity": np.asarray([float(r["anchorage_complexity"]) for r in rows], dtype=np.float64),
        "detailing_violation_ratio": np.asarray([float(r["detailing_violation_ratio"]) for r in rows], dtype=np.float64),
        "detailing_quality": np.asarray([float(r["detailing_quality"]) for r in rows], dtype=np.float64),
        "thickness_scale": np.asarray([float(r["thickness_scale"]) for r in rows], dtype=np.float64),
        "robustness_margin": np.asarray([float(r["robustness_margin"]) for r in rows], dtype=np.float64),
        "multi_hazard_margin": np.asarray([float(r["multi_hazard_margin"]) for r in rows], dtype=np.float64),
        "combination_match_score": np.asarray([float(r["combination_match_score"]) for r in rows], dtype=np.float64),
        "combination_risk_scale": np.asarray([float(r["combination_risk_scale"]) for r in rows], dtype=np.float64),
        "max_dcr": np.asarray([float(r["max_dcr"]) for r in rows], dtype=np.float64),
        "member_axial_kN": np.asarray([float(r["member_axial_kN"]) for r in rows], dtype=np.float64),
        "member_shear_y_kN": np.asarray([float(r["member_shear_y_kN"]) for r in rows], dtype=np.float64),
        "member_shear_z_kN": np.asarray([float(r["member_shear_z_kN"]) for r in rows], dtype=np.float64),
        "member_moment_y_kNm": np.asarray([float(r["member_moment_y_kNm"]) for r in rows], dtype=np.float64),
        "member_moment_z_kNm": np.asarray([float(r["member_moment_z_kNm"]) for r in rows], dtype=np.float64),
        "member_governing_dcr": np.asarray([float(r["member_governing_dcr"]) for r in rows], dtype=np.float64),
        "member_governing_clause": np.asarray([str(r["member_governing_clause"]) for r in rows], dtype="<U128"),
        "member_governing_combo": np.asarray([str(r["member_governing_combo"]) for r in rows], dtype="<U128"),
        "member_hinge_state": np.asarray([str(r["member_hinge_state"]) for r in rows], dtype="<U64"),
        "member_hinge_state_source": np.asarray([str(r["member_hinge_state_source"]) for r in rows], dtype="<U32"),
        "member_plastic_rotation_rad": np.asarray([float(r["member_plastic_rotation_rad"]) for r in rows], dtype=np.float64),
        "member_story_drift_contribution_pct": np.asarray([float(r["member_story_drift_contribution_pct"]) for r in rows], dtype=np.float64),
        "member_local_sensitivity_dcr": np.asarray([float(r["member_local_sensitivity_dcr"]) for r in rows], dtype=np.float64),
        "member_local_sensitivity_drift": np.asarray([float(r["member_local_sensitivity_drift"]) for r in rows], dtype=np.float64),
        "member_local_sensitivity_cost": np.asarray([float(r["member_local_sensitivity_cost"]) for r in rows], dtype=np.float64),
        "member_local_sensitivity_constructability": np.asarray([float(r["member_local_sensitivity_constructability"]) for r in rows], dtype=np.float64),
        "constructability_score": np.asarray([float(r["constructability_score"]) for r in rows], dtype=np.float64),
        "detailing_complexity_score": np.asarray([float(r["detailing_complexity_score"]) for r in rows], dtype=np.float64),
        "anchorage_complexity_score": np.asarray([float(r["anchorage_complexity_score"]) for r in rows], dtype=np.float64),
        "splice_burden_score": np.asarray([float(r["splice_burden_score"]) for r in rows], dtype=np.float64),
        "overdesign_margin_score": np.asarray([float(r["overdesign_margin_score"]) for r in rows], dtype=np.float64),
        "material_reduction_potential_score": np.asarray([float(r["material_reduction_potential_score"]) for r in rows], dtype=np.float64),
        "case_state_ids": case_state_ids,
        "case_state_index_per_member": case_state_index_per_member,
        "case_state_drift_envelope_max_pct": np.asarray([float(totals["drift_envelope_max_pct"])], dtype=np.float64),
        "case_state_residual_drift_pct_max_abs": np.asarray([float(totals["residual_drift_pct_max_abs"])], dtype=np.float64),
        "case_state_wind_residual_drift_pct_max_abs": np.asarray([float(totals.get("wind_residual_drift_pct_max_abs", 0.0))], dtype=np.float64),
        "case_state_ssi_residual_drift_pct_max_abs": np.asarray([float(totals.get("ssi_residual_drift_pct_max_abs", 0.0))], dtype=np.float64),
        "unique_group_ids": np.asarray(unique_groups, dtype="<U128"),
        "unique_zone_labels": np.asarray(unique_zones, dtype="<U32"),
        "group_parent_id": group_parent_id,
        "group_split_candidate_id": group_split_candidate_id,
        "group_merge_candidate_id": group_merge_candidate_id,
        "group_family_key": group_family_key,
        "group_variance_score": group_variance_score,
        "group_merge_similarity_score": group_merge_similarity_score,
        "action_mask": action_mask,
        "action_names": action_names,
        "action_mask_extended": action_mask_extended,
        "action_names_v2": action_names_v2,
        "action_family_per_index": np.asarray(ACTION_FAMILY_PER_INDEX, dtype="<U48"),
        "action_stage_per_index": np.asarray(ACTION_STAGE_PER_INDEX, dtype="<U32"),
        "action_mask_v2": action_mask_v2,
        "action_legality_reason_codes": np.asarray(LEGALITY_REASON_CODES, dtype="<U64"),
        "action_legality_reason_matrix": action_legality_reason_matrix,
        "project_total_cost": np.asarray([float(totals["total_cost"])], dtype=np.float64),
        "detailing_active_clause_count": np.asarray([int(r["detailing_active_clause_count"]) for r in rows], dtype=np.int32),
        "schema_version": np.asarray(["2.0"], dtype="<U8"),
        "explain_schema_version": np.asarray(["2.0"], dtype="<U8"),
        "global_state_split": np.asarray([True], dtype=np.bool_),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    return {
        "path": str(path),
        "member_count": int(len(rows)),
        "group_count": int(len(unique_groups)),
        "zone_count": int(len(unique_zones)),
        "story_band_count": int(len(set(int(r["story_band"]) for r in rows))),
        "member_type_counts": {str(k): int(v) for k, v in sorted(member_type_counts.items())},
        "action_mask_legal_counts": {str(k): int(v) for k, v in sorted(action_mask_summary_counts.items())},
        "action_mask_legal_counts_v2": {str(k): int(v) for k, v in sorted(action_mask_summary_counts_v2.items())},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--midas-model", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument("--code-check", default="implementation/phase1/release/kds_compliance/code_check_report.json")
    p.add_argument("--pbd-review", default="implementation/phase1/release/pbd_review/pbd_review_package_report.json")
    p.add_argument("--ndtha-residual", default="implementation/phase1/ndtha_residual_gate_report.json")
    p.add_argument("--dataset-npz-out", default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz")
    p.add_argument("--summary-out", default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json")
    args = p.parse_args()

    model = _load_json(Path(args.midas_model))
    code_check = _load_json(Path(args.code_check))
    pbd = _load_json(Path(args.pbd_review))
    ndtha_residual = _load_json(Path(args.ndtha_residual))
    costs, totals, rows = _build_rows(model, code_check, pbd, ndtha_residual)
    npz_summary = _write_npz(Path(args.dataset_npz_out), rows, totals)
    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "2.0",
        "run_id": "phase1-design-optimization-dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "midas_model": str(args.midas_model),
            "code_check": str(args.code_check),
            "pbd_review": str(args.pbd_review),
            "ndtha_residual": str(args.ndtha_residual),
            "dataset_npz_out": str(args.dataset_npz_out),
        },
        "summary": {
            "member_count": int(npz_summary["member_count"]),
            "group_count": int(npz_summary["group_count"]),
            "zone_count": int(npz_summary["zone_count"]),
            "story_band_count": int(npz_summary["story_band_count"]),
            "project_total_cost": float(totals["total_cost"]),
            "drift_envelope_max_pct": float(totals["drift_envelope_max_pct"]),
            "residual_drift_pct_max_abs": float(totals["residual_drift_pct_max_abs"]),
            "wind_residual_drift_pct_max_abs": float(totals.get("wind_residual_drift_pct_max_abs", 0.0)),
            "ssi_residual_drift_pct_max_abs": float(totals.get("ssi_residual_drift_pct_max_abs", 0.0)),
            "global_state_split": True,
            "action_space_count": int(len(ACTION_NAMES_V2)),
            "detail_mapping_mode_counts": dict(totals.get("detail_mapping_mode_counts", {})),
            "member_cluster_mapped_count": int(totals.get("member_cluster_mapped_count", 0)),
            "member_cluster_inferred_count": int(totals.get("member_cluster_inferred_count", 0)),
            "semantic_group_mapped_count": int(totals.get("semantic_group_mapped_count", 0)),
            "member_type_counts": dict(npz_summary.get("member_type_counts", {})),
            "action_mask_legal_counts_legacy": dict(npz_summary.get("action_mask_legal_counts", {})),
            "action_mask_legal_counts": dict(npz_summary.get("action_mask_legal_counts_v2", {})),
            "schema_version": "2.0",
            "explain_schema_version": "2.0",
        },
        "artifacts": {
            "dataset_npz_out": str(args.dataset_npz_out),
            "summary_json": str(out),
        },
        "rows_head": rows[:32],
        "contract_pass": bool(len(rows) > 0 and npz_summary["group_count"] > 0),
        "reason_code": "PASS" if len(rows) > 0 else "ERR_INPUT",
        "reason": "design optimization dataset generated" if len(rows) > 0 else "design optimization dataset generation failed",
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote design optimization dataset report: {out}")


if __name__ == "__main__":
    main()
