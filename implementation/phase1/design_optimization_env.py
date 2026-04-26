#!/usr/bin/env python3
"""Deterministic constrained optimization environment for grouped reinforcement tuning."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


LEGACY_ACTION_NAMES = [
    "rebar_down",
    "rebar_up",
    "thickness_down",
    "thickness_up",
    "detailing_down",
    "detailing_up",
]

ACTION_SPECS_V2 = [
    ("beam_section_up", "beam_section", "stage_a"),
    ("wall_thickness_up", "wall_thickness", "stage_a"),
    ("slab_thickness_up", "slab_thickness", "stage_a"),
    ("rebar_up", "rebar", "stage_a"),
    ("coupling_beam_up", "coupling_beam", "stage_a"),
    ("core_wall_up", "core_wall", "stage_a"),
    ("perimeter_frame_up", "perimeter_frame", "stage_a"),
    ("connection_detailing_up", "connection_detailing", "stage_a"),
    ("anchorage_reinforce", "anchorage", "stage_a"),
    ("splice_reinforce", "splice", "stage_a"),
    ("foundation_mat_thickness_up", "foundation_thickness", "stage_a"),
    ("pile_cap_depth_up", "pile_cap", "stage_a"),
    ("pile_count_increase", "pile_count", "stage_a"),
    ("beam_section_down", "beam_section", "stage_b"),
    ("wall_thickness_down", "wall_thickness", "stage_b"),
    ("slab_thickness_down", "slab_thickness", "stage_b"),
    ("rebar_down", "rebar", "stage_b"),
    ("coupling_beam_down", "coupling_beam", "stage_b"),
    ("core_wall_down", "core_wall", "stage_b"),
    ("perimeter_frame_down", "perimeter_frame", "stage_b"),
    ("connection_detailing_down", "connection_detailing", "stage_b"),
    ("detailing_down", "detailing", "stage_c"),
    ("anchorage_simplify", "anchorage", "stage_c"),
    ("splice_simplify", "splice", "stage_c"),
    ("group_split", "group_topology", "stage_c"),
    ("group_merge", "group_topology", "stage_c"),
    ("foundation_mat_thickness_down", "foundation_thickness", "stage_b"),
    ("pile_cap_depth_down", "pile_cap", "stage_b"),
    ("pile_count_decrease", "pile_count", "stage_b"),
]

ACTION_INDEX_V2 = {name: idx for idx, (name, _, _) in enumerate(ACTION_SPECS_V2)}
ACTION_FAMILY_BY_NAME = {name: family for name, family, _ in ACTION_SPECS_V2}
ACTION_STAGE_BY_NAME = {name: stage for name, _, stage in ACTION_SPECS_V2}


@dataclass(frozen=True)
class DesignOptimizationConfig:
    rebar_step: float = 0.01
    thickness_step: float = 0.02
    detailing_step: float = 0.04
    min_rebar_ratio: float = 0.004
    max_rebar_ratio: float = 0.08
    dcr_penalty_scale: float = 2500.0
    drift_penalty_scale: float = 1200.0
    residual_penalty_scale: float = 900.0
    congestion_penalty_scale: float = 180.0
    detailing_complexity_penalty_scale: float = 220.0
    robustness_penalty_scale: float = 420.0
    multi_hazard_penalty_scale: float = 360.0
    constructability_penalty_scale: float = 240.0
    dcr_limit: float = 1.0
    drift_limit_pct: float = 2.0
    residual_drift_limit_pct: float = 0.5
    max_iterations: int = 64
    min_improvement: float = 1.0e-6
    base_sensitivity: float = 0.75
    cost_weight: float = 1.0
    constructability_weight: float = 1.0
    congestion_weight: float = 1.0
    detailing_complexity_weight: float = 1.0
    robustness_weight: float = 1.0
    multi_hazard_weight: float = 1.0
    drift_weight_multiplier: float = 1.0
    residual_weight_multiplier: float = 1.0
    connection_weight_multiplier: float = 1.0
    ssi_weight_multiplier: float = 1.0


@dataclass(frozen=True)
class CandidateEvaluation:
    group_index: int
    direction: int
    action_name: str
    reward: float
    estimated_cost: float
    estimated_max_dcr: float
    estimated_drift_pct: float
    estimated_residual_drift_pct: float


@dataclass(frozen=True)
class StageEvaluation:
    violation_score: float
    feasible: bool


def _mean_by_group(values: np.ndarray, group_index_per_member: np.ndarray, group_count: int) -> np.ndarray:
    totals = np.zeros(group_count, dtype=np.float64)
    counts = np.zeros(group_count, dtype=np.float64)
    for idx, val in zip(group_index_per_member, values):
        gi = int(idx)
        totals[gi] += float(val)
        counts[gi] += 1.0
    counts = np.maximum(counts, 1.0)
    return totals / counts


def _max_by_group(values: np.ndarray, group_index_per_member: np.ndarray, group_count: int) -> np.ndarray:
    out = np.zeros(group_count, dtype=np.float64)
    for idx, val in zip(group_index_per_member, values):
        gi = int(idx)
        out[gi] = max(float(out[gi]), float(val))
    return out


def _first_by_group(values: np.ndarray, group_index_per_member: np.ndarray, group_count: int, *, dtype: str) -> np.ndarray:
    out = np.empty(group_count, dtype=dtype)
    for gi in range(group_count):
        indices = np.where(group_index_per_member == gi)[0]
        out[gi] = values[indices[0]]
    return out


def aggregate_group_state(dataset: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    group_index_per_member = np.asarray(dataset["group_index_per_member"], dtype=np.int32)
    group_ids = np.asarray(dataset["unique_group_ids"])
    group_count = int(group_ids.shape[0])
    rebar_ratio = _mean_by_group(np.asarray(dataset["rebar_ratio"], dtype=np.float64), group_index_per_member, group_count)
    max_dcr = _max_by_group(np.asarray(dataset["max_dcr"], dtype=np.float64), group_index_per_member, group_count)
    congestion = _mean_by_group(np.asarray(dataset["congestion_index"], dtype=np.float64), group_index_per_member, group_count)
    lap_splice = _mean_by_group(np.asarray(dataset["lap_splice_ratio"], dtype=np.float64), group_index_per_member, group_count)
    anchorage = _mean_by_group(np.asarray(dataset["anchorage_complexity"], dtype=np.float64), group_index_per_member, group_count)
    detailing = _mean_by_group(np.asarray(dataset["detailing_violation_ratio"], dtype=np.float64), group_index_per_member, group_count)
    detailing_quality = _mean_by_group(
        np.asarray(dataset.get("detailing_quality", np.ones(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    volume = _mean_by_group(np.asarray(dataset["volume_m3"], dtype=np.float64), group_index_per_member, group_count)
    steel_mass = _mean_by_group(np.asarray(dataset["steel_mass_kg"], dtype=np.float64), group_index_per_member, group_count)
    thickness_scale = _mean_by_group(
        np.asarray(dataset.get("thickness_scale", np.ones(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    robustness_margin = _mean_by_group(
        np.asarray(dataset.get("robustness_margin", np.full(group_index_per_member.size, 0.25, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    multi_hazard_margin = _mean_by_group(
        np.asarray(dataset.get("multi_hazard_margin", np.full(group_index_per_member.size, 0.25, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_types = np.asarray(dataset["member_types"])
    group_member_type = np.asarray(
        dataset.get(
            "member_type_per_group",
            _first_by_group(member_types, group_index_per_member, group_count, dtype="<U32"),
        ),
        dtype="<U32",
    )
    zone_labels = np.asarray(dataset.get("zone_labels", np.asarray(["intermediate"] * group_index_per_member.size)))
    group_zone = np.asarray(
        dataset.get(
            "zone_label_per_group",
            _first_by_group(zone_labels, group_index_per_member, group_count, dtype="<U32"),
        ),
        dtype="<U32",
    )
    semantic_groups = np.asarray(dataset.get("semantic_groups", np.asarray([""] * group_index_per_member.size)))
    group_semantic = np.asarray(
        dataset.get(
            "semantic_group_per_group",
            _first_by_group(semantic_groups, group_index_per_member, group_count, dtype="<U96"),
        ),
        dtype="<U96",
    )
    section_names = np.asarray(dataset.get("section_names", np.asarray([""] * group_index_per_member.size)))
    group_section_name = np.asarray(
        dataset.get(
            "section_name_per_group",
            _first_by_group(section_names, group_index_per_member, group_count, dtype="<U128"),
        ),
        dtype="<U128",
    )
    section_signatures = np.asarray(dataset.get("section_signatures", np.asarray([""] * group_index_per_member.size)))
    group_section_signature = np.asarray(
        dataset.get(
            "section_signature_per_group",
            _first_by_group(section_signatures, group_index_per_member, group_count, dtype="<U128"),
        ),
        dtype="<U128",
    )
    governing_clauses = np.asarray(dataset.get("member_governing_clause", np.asarray([""] * group_index_per_member.size)))
    group_governing_clause = np.asarray(
        dataset.get(
            "member_governing_clause_per_group",
            _first_by_group(governing_clauses, group_index_per_member, group_count, dtype="<U128"),
        ),
        dtype="<U128",
    )
    story_band_index = np.asarray(dataset.get("story_band_index", np.zeros(group_index_per_member.size, dtype=np.int32)), dtype=np.int32)
    group_story_band = np.asarray(
        dataset.get(
            "story_band_per_group",
            _first_by_group(story_band_index, group_index_per_member, group_count, dtype=np.int32),
        ),
        dtype=np.int32,
    )
    group_parent_id = np.asarray(dataset.get("group_parent_id", group_ids), dtype="<U160")
    group_family_key = np.asarray(dataset.get("group_family_key", group_ids), dtype="<U160")
    group_variance_score = np.asarray(dataset.get("group_variance_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
    group_merge_similarity_score = np.asarray(dataset.get("group_merge_similarity_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
    combo_match = _mean_by_group(
        np.asarray(dataset.get("combination_match_score", np.ones(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    combo_risk = _mean_by_group(
        np.asarray(dataset.get("combination_risk_scale", np.ones(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    constructability_score = _mean_by_group(
        np.asarray(dataset.get("constructability_score", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    detailing_complexity_score = _mean_by_group(
        np.asarray(dataset.get("detailing_complexity_score", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    anchorage_complexity_score = _mean_by_group(
        np.asarray(dataset.get("anchorage_complexity_score", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    splice_burden_score = _mean_by_group(
        np.asarray(dataset.get("splice_burden_score", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    overdesign_margin_score = _mean_by_group(
        np.asarray(dataset.get("overdesign_margin_score", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    material_reduction_potential_score = _mean_by_group(
        np.asarray(dataset.get("material_reduction_potential_score", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_governing_dcr = _max_by_group(
        np.asarray(dataset.get("member_governing_dcr", dataset.get("max_dcr", np.zeros(group_index_per_member.size, dtype=np.float64))), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_story_drift_contribution_pct = _mean_by_group(
        np.asarray(dataset.get("member_story_drift_contribution_pct", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_local_sensitivity_dcr = _mean_by_group(
        np.asarray(dataset.get("member_local_sensitivity_dcr", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_local_sensitivity_drift = _mean_by_group(
        np.asarray(dataset.get("member_local_sensitivity_drift", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_local_sensitivity_cost = _mean_by_group(
        np.asarray(dataset.get("member_local_sensitivity_cost", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    member_local_sensitivity_constructability = _mean_by_group(
        np.asarray(dataset.get("member_local_sensitivity_constructability", np.zeros(group_index_per_member.size, dtype=np.float64)), dtype=np.float64),
        group_index_per_member,
        group_count,
    )
    group_cost_proxy = volume * 110.0 + steel_mass * 1.8 + volume * rebar_ratio * 7850.0 * 1.3
    if "case_state_drift_envelope_max_pct" in dataset:
        case_state_index = np.asarray(dataset.get("case_state_index_per_member", np.zeros(group_index_per_member.size, dtype=np.int32)), dtype=np.int32)
        case_state_drift = np.asarray(dataset["case_state_drift_envelope_max_pct"], dtype=np.float64)
        case_state_residual = np.asarray(dataset["case_state_residual_drift_pct_max_abs"], dtype=np.float64)
        case_state_wind = np.asarray(dataset.get("case_state_wind_residual_drift_pct_max_abs", np.zeros(case_state_drift.shape[0], dtype=np.float64)), dtype=np.float64)
        case_state_ssi = np.asarray(dataset.get("case_state_ssi_residual_drift_pct_max_abs", np.zeros(case_state_drift.shape[0], dtype=np.float64)), dtype=np.float64)
        drift_pct = float(np.max(case_state_drift))
        residual_drift_pct = float(np.max(case_state_residual))
        wind_residual_drift_pct = float(np.max(case_state_wind))
        ssi_residual_drift_pct = float(np.max(case_state_ssi))
    else:
        case_state_index = np.zeros(group_index_per_member.size, dtype=np.int32)
        drift_pct = float(np.max(np.asarray(dataset["drift_envelope_max_pct"], dtype=np.float64)))
        residual_drift_pct = float(np.max(np.asarray(dataset["residual_drift_pct_max_abs"], dtype=np.float64)))
        wind_residual_drift_pct = 0.0
        ssi_residual_drift_pct = 0.0
    repair_influence = np.ones(group_count, dtype=np.float64)
    for gi in range(group_count):
        mt = str(group_member_type[gi]).strip().lower()
        zone = str(group_zone[gi]).strip().lower()
        story_band = int(group_story_band[gi])
        influence = {
            "wall": 1.45,
            "column": 1.25,
            "beam": 1.00,
            "slab": 0.65,
            "foundation": 1.30,
            "connection": 0.90,
        }.get(mt, 0.85)
        if zone == "transfer":
            influence *= 1.35
        elif zone == "core":
            influence *= 1.18
        elif zone == "perimeter":
            influence *= 0.92
        if story_band <= 1:
            influence *= 1.12
        influence *= 1.0 + 0.40 * max(float(combo_risk[gi]) - 1.0, 0.0)
        if str(group_semantic[gi]).strip():
            influence *= 1.04
        repair_influence[gi] = float(influence)
    action_mask_ext = np.asarray(
        dataset.get("action_mask_extended", np.ones((group_count, len(LEGACY_ACTION_NAMES)), dtype=np.bool_)),
        dtype=np.bool_,
    )
    action_mask_v2 = np.asarray(
        dataset.get("action_mask_v2", np.ones((group_count, len(ACTION_SPECS_V2)), dtype=np.bool_)),
        dtype=np.bool_,
    )
    action_names = np.asarray(
        dataset.get(
            "action_names",
            np.asarray(LEGACY_ACTION_NAMES, dtype="<U32"),
        )
    )
    action_names_v2 = np.asarray(
        dataset.get("action_names_v2", np.asarray([name for name, _, _ in ACTION_SPECS_V2], dtype="<U48")),
        dtype="<U48",
    )
    action_family_per_index = np.asarray(
        dataset.get("action_family_per_index", np.asarray([family for _, family, _ in ACTION_SPECS_V2], dtype="<U48")),
        dtype="<U48",
    )
    action_stage_per_index = np.asarray(
        dataset.get("action_stage_per_index", np.asarray([stage for _, _, stage in ACTION_SPECS_V2], dtype="<U32")),
        dtype="<U32",
    )
    return {
        "group_ids": np.asarray(group_ids),
        "rebar_ratio": rebar_ratio,
        "max_dcr": max_dcr,
        "congestion": congestion,
        "lap_splice": lap_splice,
        "anchorage": anchorage,
        "detailing": detailing,
        "detailing_quality": detailing_quality,
        "thickness_scale": thickness_scale,
        "robustness_margin": robustness_margin,
        "multi_hazard_margin": multi_hazard_margin,
        "group_cost_proxy": group_cost_proxy,
        "member_type": group_member_type,
        "zone_label": group_zone,
        "semantic_group": group_semantic,
        "section_name": group_section_name,
        "section_signature": group_section_signature,
        "story_band": group_story_band,
        "repair_influence": repair_influence,
        "combination_match_score": combo_match,
        "combination_risk": combo_risk,
        "constructability_score": constructability_score,
        "detailing_complexity_score": detailing_complexity_score,
        "anchorage_complexity_score": anchorage_complexity_score,
        "splice_burden_score": splice_burden_score,
        "overdesign_margin_score": overdesign_margin_score,
        "material_reduction_potential_score": material_reduction_potential_score,
        "member_governing_dcr": member_governing_dcr,
        "member_governing_clause": group_governing_clause,
        "member_story_drift_contribution_pct": member_story_drift_contribution_pct,
        "member_local_sensitivity_dcr": member_local_sensitivity_dcr,
        "member_local_sensitivity_drift": member_local_sensitivity_drift,
        "member_local_sensitivity_cost": member_local_sensitivity_cost,
        "member_local_sensitivity_constructability": member_local_sensitivity_constructability,
        "group_parent_id": group_parent_id,
        "group_family_key": group_family_key,
        "group_variance_score": group_variance_score,
        "group_merge_similarity_score": group_merge_similarity_score,
        "wind_residual_drift_pct": np.asarray([wind_residual_drift_pct], dtype=np.float64),
        "ssi_residual_drift_pct": np.asarray([ssi_residual_drift_pct], dtype=np.float64),
        "case_state_index_per_member": case_state_index,
        "global_drift_pct": np.asarray([drift_pct], dtype=np.float64),
        "global_residual_drift_pct": np.asarray([residual_drift_pct], dtype=np.float64),
        "action_mask": np.asarray(dataset["action_mask"], dtype=np.bool_),
        "action_mask_extended": action_mask_ext,
        "action_names": action_names,
        "action_mask_v2": action_mask_v2,
        "action_names_v2": action_names_v2,
        "action_family_per_index": action_family_per_index,
        "action_stage_per_index": action_stage_per_index,
    }


def _member_type_sensitivity(member_type: str) -> float:
    return {
        "column": 1.05,
        "beam": 0.82,
        "wall": 0.95,
        "slab": 0.55,
        "foundation": 0.90,
        "connection": 1.10,
    }.get(str(member_type).strip().lower(), 0.80)


def _member_type_cost_shares(member_type: str) -> tuple[float, float, float]:
    mt = str(member_type).strip().lower()
    if mt == "slab":
        return 0.28, 0.58, 0.12
    if mt == "wall":
        return 0.42, 0.34, 0.12
    if mt == "column":
        return 0.48, 0.18, 0.14
    if mt == "beam":
        return 0.38, 0.24, 0.16
    if mt == "foundation":
        return 0.26, 0.30, 0.12
    if mt == "connection":
        return 0.32, 0.00, 0.34
    return 0.34, 0.22, 0.12


def project_group_cost_proxy(
    *,
    state: dict[str, np.ndarray],
    rebar_ratio: np.ndarray,
    thickness_scale: np.ndarray | None = None,
    detailing_quality: np.ndarray | None = None,
    group_index: int | None = None,
) -> np.ndarray:
    current_cost = np.asarray(state["group_cost_proxy"], dtype=np.float64)
    current_rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
    current_thickness = np.asarray(
        state.get("thickness_scale", np.ones_like(current_rebar)),
        dtype=np.float64,
    )
    current_detail = np.asarray(
        state.get("detailing_quality", np.ones_like(current_rebar)),
        dtype=np.float64,
    )
    next_rebar = np.asarray(rebar_ratio, dtype=np.float64)
    next_thickness = np.asarray(
        current_thickness if thickness_scale is None else thickness_scale,
        dtype=np.float64,
    )
    next_detail = np.asarray(
        current_detail if detailing_quality is None else detailing_quality,
        dtype=np.float64,
    )
    out = current_cost.copy()
    if group_index is None:
        indices = range(int(current_cost.shape[0]))
    else:
        indices = (int(group_index),)
    member_types = np.asarray(
        state.get("member_type", np.asarray([""] * current_cost.shape[0])),
        dtype="<U32",
    )
    for gi in indices:
        steel_share, thickness_share, detailing_share = _member_type_cost_shares(
            str(member_types[gi])
        )
        rebar_ratio_scale = float(next_rebar[gi] / max(current_rebar[gi], 1.0e-9))
        thickness_ratio_scale = float(
            next_thickness[gi] / max(current_thickness[gi], 1.0e-9)
        )
        detail_delta = float(next_detail[gi] - current_detail[gi])
        scale = 1.0
        scale *= 1.0 + steel_share * (rebar_ratio_scale - 1.0)
        scale *= 1.0 + thickness_share * (thickness_ratio_scale - 1.0)
        scale *= 1.0 + detailing_share * detail_delta
        out[gi] = float(current_cost[gi] * np.clip(scale, 0.15, 2.25))
    return np.asarray(out, dtype=np.float64)


def _transition_state(
    *,
    state: dict[str, np.ndarray],
    group_index: int,
    direction: int,
    cfg: DesignOptimizationConfig,
    action_name: str | None = None,
) -> dict[str, np.ndarray]:
    updated_state = {k: np.asarray(v).copy() for k, v in state.items()}
    rebar = np.asarray(state["rebar_ratio"], dtype=np.float64)
    if "thickness_scale" not in updated_state:
        updated_state["thickness_scale"] = np.ones_like(rebar, dtype=np.float64)
    if "detailing_quality" not in updated_state:
        updated_state["detailing_quality"] = np.ones_like(rebar, dtype=np.float64)
    if "robustness_margin" not in updated_state:
        updated_state["robustness_margin"] = np.full(rebar.size, 0.25, dtype=np.float64)
    if "multi_hazard_margin" not in updated_state:
        updated_state["multi_hazard_margin"] = np.full(rebar.size, 0.25, dtype=np.float64)
    if "constructability_score" not in updated_state:
        updated_state["constructability_score"] = np.zeros(rebar.size, dtype=np.float64)
    if "detailing_complexity_score" not in updated_state:
        updated_state["detailing_complexity_score"] = np.asarray(updated_state.get("detailing", np.zeros(rebar.size, dtype=np.float64)), dtype=np.float64).copy()
    resolved_action = str(action_name or ("rebar_down" if int(direction) < 0 else "rebar_up"))
    resolved_action = {
        "beam_section_up": "thickness_up",
        "beam_section_down": "thickness_down",
        "wall_thickness_up": "thickness_up",
        "wall_thickness_down": "thickness_down",
        "slab_thickness_up": "thickness_up",
        "slab_thickness_down": "thickness_down",
        "coupling_beam_up": "rebar_up",
        "coupling_beam_down": "rebar_down",
        "core_wall_up": "thickness_up",
        "core_wall_down": "thickness_down",
        "perimeter_frame_up": "rebar_up",
        "perimeter_frame_down": "rebar_down",
        "connection_detailing_up": "detailing_up",
        "connection_detailing_down": "detailing_down",
        "anchorage_reinforce": "detailing_up",
        "anchorage_simplify": "detailing_down",
        "splice_reinforce": "detailing_up",
        "splice_simplify": "detailing_down",
        "foundation_mat_thickness_up": "thickness_up",
        "foundation_mat_thickness_down": "thickness_down",
        "pile_cap_depth_up": "thickness_up",
        "pile_cap_depth_down": "thickness_down",
        "pile_count_increase": "detailing_up",
        "pile_count_decrease": "detailing_down",
    }.get(resolved_action, resolved_action)
    updated_rebar = apply_group_action(
        rebar_ratio=rebar,
        action_mask=np.asarray(state["action_mask"], dtype=np.bool_),
        group_index=group_index,
        direction=direction,
        cfg=cfg,
        action_name=resolved_action,
        action_mask_extended=np.asarray(state.get("action_mask_extended", np.ones((rebar.size, 6), dtype=np.bool_)), dtype=np.bool_),
        thickness_scale=np.asarray(state.get("thickness_scale", np.ones_like(rebar)), dtype=np.float64),
        detailing_quality=np.asarray(state.get("detailing_quality", np.ones_like(rebar)), dtype=np.float64),
    )
    updated_state["rebar_ratio"] = updated_rebar["rebar_ratio"]
    updated_state["thickness_scale"] = updated_rebar["thickness_scale"]
    updated_state["detailing_quality"] = updated_rebar["detailing_quality"]
    delta = float(updated_state["rebar_ratio"][group_index] - rebar[group_index])
    delta_thickness = float(updated_state["thickness_scale"][group_index] - np.asarray(state.get("thickness_scale", np.ones_like(rebar)), dtype=np.float64)[group_index])
    delta_detail = float(updated_state["detailing_quality"][group_index] - np.asarray(state.get("detailing_quality", np.ones_like(rebar)), dtype=np.float64)[group_index])
    dcr = np.asarray(state["max_dcr"], dtype=np.float64).copy()
    member_type = str(np.asarray(state["member_type"])[group_index])
    sensitivity = float(cfg.base_sensitivity) * _member_type_sensitivity(member_type)
    congestion = float(np.asarray(state["congestion"], dtype=np.float64)[group_index])
    detailing = float(np.asarray(state["detailing"], dtype=np.float64)[group_index])
    repair_influence = float(np.asarray(state["repair_influence"], dtype=np.float64)[group_index])
    combination_risk = float(np.asarray(state.get("combination_risk", np.ones_like(rebar)), dtype=np.float64)[group_index])
    combination_match = float(np.asarray(state.get("combination_match_score", np.ones_like(rebar)), dtype=np.float64)[group_index])
    action_dcr_gain = {
        "rebar_up": 1.0,
        "rebar_down": -0.40,
        "thickness_up": 1.35,
        "thickness_down": -0.55,
        "detailing_up": 0.72,
        "detailing_down": -0.38,
    }.get(resolved_action, 1.0)
    total_delta_effect = (
        delta * sensitivity * (3.0 + repair_influence + congestion + detailing)
        + delta_thickness * (20.0 + 4.0 * repair_influence + 3.0 * congestion)
        + delta_detail * (8.0 + 3.0 * detailing + 2.0 * repair_influence)
    )
    dcr[group_index] = max(0.0, float(dcr[group_index]) - total_delta_effect * action_dcr_gain)
    updated_state["max_dcr"] = dcr
    drift_pct = float(np.asarray(state["global_drift_pct"], dtype=np.float64)[0])
    residual_drift_pct = float(np.asarray(state["global_residual_drift_pct"], dtype=np.float64)[0])
    structural_gain = abs(delta) + 2.4 * abs(delta_thickness) + 1.2 * abs(delta_detail)
    if resolved_action.endswith("_down"):
        drift_pct += structural_gain * (22.0 + 8.0 * repair_influence + 4.0 * congestion) * (1.0 + 0.45 * max(combination_risk - 1.0, 0.0))
        residual_drift_pct += structural_gain * (6.0 + 4.0 * repair_influence + 2.0 * detailing) * (1.0 + 0.60 * max(combination_risk - 1.0, 0.0))
    else:
        gain = 1.0 + 0.65 * max(combination_risk - 1.0, 0.0) + 0.20 * max(1.0 - combination_match, 0.0)
        drift_pct = max(0.0, drift_pct - structural_gain * (90.0 + 28.0 * repair_influence) * gain)
        residual_drift_pct = max(0.0, residual_drift_pct - structural_gain * (22.0 + 9.0 * repair_influence) * gain)
    updated_state["group_cost_proxy"] = project_group_cost_proxy(
        state=state,
        rebar_ratio=np.asarray(updated_state["rebar_ratio"], dtype=np.float64),
        thickness_scale=np.asarray(updated_state["thickness_scale"], dtype=np.float64),
        detailing_quality=np.asarray(updated_state["detailing_quality"], dtype=np.float64),
        group_index=int(group_index),
    )
    updated_state["congestion"][group_index] = float(
        np.clip(
            float(np.asarray(state["congestion"], dtype=np.float64)[group_index])
            + max(delta_thickness, 0.0) * 0.35
            + max(delta_detail, 0.0) * 0.10
            - max(-delta_thickness, 0.0) * 0.12,
            0.0,
            1.5,
        )
    )
    updated_state["detailing"][group_index] = float(
        np.clip(
            float(np.asarray(state["detailing"], dtype=np.float64)[group_index])
            - max(delta_detail, 0.0) * 0.45
            + max(-delta_detail, 0.0) * 0.20,
            0.0,
            1.5,
        )
    )
    updated_state["detailing_complexity_score"][group_index] = float(
        np.clip(
            float(np.asarray(state.get("detailing_complexity_score", state["detailing"]), dtype=np.float64)[group_index])
            - max(delta_detail, 0.0) * 0.55
            + max(-delta_detail, 0.0) * 0.18
            - max(-delta_thickness, 0.0) * 0.05,
            0.0,
            1.5,
        )
    )
    updated_state["constructability_score"][group_index] = float(
        np.clip(
            float(np.asarray(state.get("constructability_score", np.zeros(rebar.size, dtype=np.float64)), dtype=np.float64)[group_index])
            + max(delta_thickness, 0.0) * 0.28
            + max(delta_detail, 0.0) * 0.22
            + max(delta, 0.0) * 0.10
            - max(-delta_thickness, 0.0) * 0.14
            - max(-delta_detail, 0.0) * 0.30
            - max(-delta, 0.0) * 0.12,
            0.0,
            1.5,
        )
    )
    updated_state["robustness_margin"][group_index] = float(
        np.clip(
            float(np.asarray(state.get("robustness_margin", np.full(rebar.size, 0.25)), dtype=np.float64)[group_index])
            + max(delta, 0.0) * 3.0
            + max(delta_thickness, 0.0) * 2.0
            + max(delta_detail, 0.0) * 1.5
            - max(-delta, 0.0) * 1.8,
            0.0,
            1.5,
        )
    )
    updated_state["multi_hazard_margin"][group_index] = float(
        np.clip(
            float(np.asarray(state.get("multi_hazard_margin", np.full(rebar.size, 0.25)), dtype=np.float64)[group_index])
            + max(delta_thickness, 0.0) * 1.6
            + max(delta_detail, 0.0) * 1.2
            + max(delta, 0.0) * 0.8
            - max(-delta, 0.0) * 1.1
            - max(-delta_thickness, 0.0) * 1.4,
            0.0,
            1.5,
        )
    )
    updated_state["global_drift_pct"] = np.asarray([drift_pct], dtype=np.float64)
    updated_state["global_residual_drift_pct"] = np.asarray([residual_drift_pct], dtype=np.float64)
    return updated_state


def hydrate_state_constructability_fields(
    *,
    state: dict[str, np.ndarray],
    reference_state: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    hydrated = {k: np.asarray(v).copy() for k, v in state.items()}
    if "rebar_ratio" not in hydrated:
        return hydrated
    rebar = np.asarray(hydrated["rebar_ratio"], dtype=np.float64)
    group_count = rebar.size
    current_thickness = np.asarray(hydrated.get("thickness_scale", np.ones(group_count, dtype=np.float64)), dtype=np.float64)
    current_detailing_quality = np.asarray(hydrated.get("detailing_quality", np.ones(group_count, dtype=np.float64)), dtype=np.float64)
    ref_rebar = np.asarray(reference_state.get("rebar_ratio", np.full(group_count, 0.0, dtype=np.float64)), dtype=np.float64)
    ref_thickness = np.asarray(reference_state.get("thickness_scale", np.ones(group_count, dtype=np.float64)), dtype=np.float64)
    ref_detailing_quality = np.asarray(reference_state.get("detailing_quality", np.ones(group_count, dtype=np.float64)), dtype=np.float64)
    ref_constructability = np.asarray(reference_state.get("constructability_score", np.zeros(group_count, dtype=np.float64)), dtype=np.float64)
    ref_detailing_complexity = np.asarray(
        reference_state.get("detailing_complexity_score", reference_state.get("detailing", np.zeros(group_count, dtype=np.float64))),
        dtype=np.float64,
    )
    delta = current_thickness * 0.0 + (rebar - ref_rebar)
    delta_thickness = current_thickness - ref_thickness
    delta_detail = current_detailing_quality - ref_detailing_quality
    hydrated["detailing_complexity_score"] = np.clip(
        ref_detailing_complexity
        - np.maximum(delta_detail, 0.0) * 0.55
        + np.maximum(-delta_detail, 0.0) * 0.18
        - np.maximum(-delta_thickness, 0.0) * 0.05,
        0.0,
        1.5,
    ).astype(np.float64)
    hydrated["constructability_score"] = np.clip(
        ref_constructability
        + np.maximum(delta_thickness, 0.0) * 0.28
        + np.maximum(delta_detail, 0.0) * 0.22
        + np.maximum(delta, 0.0) * 0.10
        - np.maximum(-delta_thickness, 0.0) * 0.14
        - np.maximum(-delta_detail, 0.0) * 0.30
        - np.maximum(-delta, 0.0) * 0.12,
        0.0,
        1.5,
    ).astype(np.float64)
    for key in (
        "anchorage_complexity_score",
        "splice_burden_score",
        "overdesign_margin_score",
        "material_reduction_potential_score",
    ):
        if key not in hydrated and key in reference_state:
            hydrated[key] = np.asarray(reference_state[key]).copy()
    return hydrated


def evaluate_candidate(
    *,
    state: dict[str, np.ndarray],
    group_index: int,
    direction: int,
    cfg: DesignOptimizationConfig,
    action_name: str | None = None,
) -> CandidateEvaluation:
    current_max_dcr = float(np.max(np.asarray(state["max_dcr"], dtype=np.float64)))
    current_drift_pct = float(np.asarray(state["global_drift_pct"], dtype=np.float64)[0])
    current_residual_drift_pct = float(np.asarray(state["global_residual_drift_pct"], dtype=np.float64)[0])
    updated_state = _transition_state(state=state, group_index=group_index, direction=direction, cfg=cfg, action_name=action_name)
    cost = float(np.sum(np.asarray(updated_state["group_cost_proxy"], dtype=np.float64)))
    max_dcr = float(np.max(np.asarray(updated_state["max_dcr"], dtype=np.float64)))
    drift_pct = float(np.asarray(updated_state["global_drift_pct"], dtype=np.float64)[0])
    residual_drift_pct = float(np.asarray(updated_state["global_residual_drift_pct"], dtype=np.float64)[0])
    hard_invalid = False
    if current_max_dcr > float(cfg.dcr_limit) and max_dcr > current_max_dcr + 1.0e-9:
        hard_invalid = True
    if current_max_dcr <= float(cfg.dcr_limit) and max_dcr > float(cfg.dcr_limit) + 1.0e-9:
        hard_invalid = True
    if current_drift_pct > float(cfg.drift_limit_pct) and drift_pct > current_drift_pct + 1.0e-9:
        hard_invalid = True
    if current_drift_pct <= float(cfg.drift_limit_pct) and drift_pct > float(cfg.drift_limit_pct) + 1.0e-9:
        hard_invalid = True
    if current_residual_drift_pct > float(cfg.residual_drift_limit_pct) and residual_drift_pct > current_residual_drift_pct + 1.0e-9:
        hard_invalid = True
    if current_residual_drift_pct <= float(cfg.residual_drift_limit_pct) and residual_drift_pct > float(cfg.residual_drift_limit_pct) + 1.0e-9:
        hard_invalid = True
    reward = evaluate_reward(
        total_cost=cost,
        max_dcr=max_dcr,
        drift_pct=drift_pct,
        drift_limit_pct=float(cfg.drift_limit_pct),
        residual_drift_pct=residual_drift_pct,
        residual_drift_limit_pct=float(cfg.residual_drift_limit_pct),
        dcr_limit=float(cfg.dcr_limit),
        cfg=cfg,
        avg_congestion=float(np.mean(np.asarray(updated_state["congestion"], dtype=np.float64))),
        avg_detailing_complexity=float(np.mean(np.asarray(updated_state["detailing"], dtype=np.float64))),
        robustness_margin_min=float(np.min(np.asarray(updated_state.get("robustness_margin", np.full(1, 0.25)), dtype=np.float64))),
        multi_hazard_margin_min=float(np.min(np.asarray(updated_state.get("multi_hazard_margin", np.full(1, 0.25)), dtype=np.float64))),
        avg_constructability=float(np.mean(np.asarray(updated_state.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64))),
    )
    if hard_invalid:
        reward = float(-1.0e18)
    return CandidateEvaluation(
        group_index=int(group_index),
        direction=int(direction),
        action_name=str(action_name or ("rebar_down" if int(direction) < 0 else "rebar_up")),
        reward=float(reward),
        estimated_cost=float(cost),
        estimated_max_dcr=float(max_dcr),
        estimated_drift_pct=float(drift_pct),
        estimated_residual_drift_pct=float(residual_drift_pct),
    )


def evaluate_stage_state(*, state: dict[str, np.ndarray], cfg: DesignOptimizationConfig) -> StageEvaluation:
    max_dcr = float(np.max(np.asarray(state["max_dcr"], dtype=np.float64)))
    drift_pct = float(np.asarray(state["global_drift_pct"], dtype=np.float64)[0])
    residual_drift_pct = float(np.asarray(state["global_residual_drift_pct"], dtype=np.float64)[0])
    violation = 0.0
    violation += max(max_dcr - float(cfg.dcr_limit), 0.0) * float(cfg.dcr_penalty_scale)
    violation += max(drift_pct - float(cfg.drift_limit_pct), 0.0) * float(cfg.drift_penalty_scale)
    violation += max(residual_drift_pct - float(cfg.residual_drift_limit_pct), 0.0) * float(cfg.residual_penalty_scale)
    violation += max(0.08 - float(np.min(np.asarray(state.get("robustness_margin", np.full(1, 0.25)), dtype=np.float64))), 0.0) * float(cfg.robustness_penalty_scale)
    violation += max(0.10 - float(np.min(np.asarray(state.get("multi_hazard_margin", np.full(1, 0.25)), dtype=np.float64))), 0.0) * float(cfg.multi_hazard_penalty_scale)
    return StageEvaluation(violation_score=float(violation), feasible=bool(violation <= 1.0e-9))


def greedy_feasible_repair(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> dict[str, object]:
    current = {k: np.asarray(v).copy() for k, v in state.items()}
    history: list[dict[str, object]] = []
    current_eval = evaluate_stage_state(state=current, cfg=cfg)
    for _ in range(int(cfg.max_iterations)):
        if current_eval.feasible:
            break
        best: CandidateEvaluation | None = None
        best_score = current_eval.violation_score
        for gi in range(int(np.asarray(current["group_ids"]).shape[0])):
            for action_name in ("rebar_up", "thickness_up", "detailing_up"):
                cand = evaluate_candidate(state=current, group_index=gi, direction=1, cfg=cfg, action_name=action_name)
                next_state = _transition_state(state=current, group_index=gi, direction=1, cfg=cfg, action_name=action_name)
                next_eval = evaluate_stage_state(state=next_state, cfg=cfg)
                if next_eval.violation_score + 1.0e-9 < best_score:
                    best_score = float(next_eval.violation_score)
                    best = cand
        if best is None:
            break
        current = _transition_state(
            state=current,
            group_index=int(best.group_index),
            direction=1,
            cfg=cfg,
            action_name=str(best.action_name),
        )
        current_eval = evaluate_stage_state(state=current, cfg=cfg)
        history.append(
            {
                "group_id": str(np.asarray(current["group_ids"])[int(best.group_index)]),
                "group_index": int(best.group_index),
                "direction": 1,
                "action_name": str(best.action_name),
                "violation_score": float(current_eval.violation_score),
                "estimated_cost": float(np.sum(np.asarray(current["group_cost_proxy"], dtype=np.float64))),
                "estimated_max_dcr": float(np.max(np.asarray(current["max_dcr"], dtype=np.float64))),
                "estimated_drift_pct": float(np.asarray(current["global_drift_pct"], dtype=np.float64)[0]),
                "estimated_residual_drift_pct": float(np.asarray(current["global_residual_drift_pct"], dtype=np.float64)[0]),
            }
        )
    return {
        "state": current,
        "history": history,
        "feasible": bool(current_eval.feasible),
        "violation_score": float(current_eval.violation_score),
    }


def greedy_cost_reduction(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> dict[str, object]:
    current = {k: np.asarray(v).copy() for k, v in state.items()}
    history: list[dict[str, object]] = []
    current_reward = evaluate_reward(
        total_cost=float(np.sum(np.asarray(current["group_cost_proxy"], dtype=np.float64))),
        max_dcr=float(np.max(np.asarray(current["max_dcr"], dtype=np.float64))),
        drift_pct=float(np.asarray(current["global_drift_pct"], dtype=np.float64)[0]),
        drift_limit_pct=float(cfg.drift_limit_pct),
        residual_drift_pct=float(np.asarray(current["global_residual_drift_pct"], dtype=np.float64)[0]),
        residual_drift_limit_pct=float(cfg.residual_drift_limit_pct),
        dcr_limit=float(cfg.dcr_limit),
        cfg=cfg,
        avg_congestion=float(np.mean(np.asarray(current["congestion"], dtype=np.float64))),
        avg_detailing_complexity=float(np.mean(np.asarray(current["detailing"], dtype=np.float64))),
        robustness_margin_min=float(np.min(np.asarray(current.get("robustness_margin", np.full(1, 0.25)), dtype=np.float64))),
        multi_hazard_margin_min=float(np.min(np.asarray(current.get("multi_hazard_margin", np.full(1, 0.25)), dtype=np.float64))),
        avg_constructability=float(np.mean(np.asarray(current.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64))),
    )
    for _ in range(int(cfg.max_iterations)):
        best: CandidateEvaluation | None = None
        for gi in range(int(np.asarray(current["group_ids"]).shape[0])):
            for action_name in ("rebar_down", "thickness_down", "detailing_down"):
                cand = evaluate_candidate(state=current, group_index=gi, direction=-1, cfg=cfg, action_name=action_name)
                if cand.reward <= -1.0e17:
                    continue
                if best is None or cand.reward > best.reward:
                    best = cand
        if best is None or float(best.reward - current_reward) <= float(cfg.min_improvement):
            break
        current = _transition_state(
            state=current,
            group_index=int(best.group_index),
            direction=-1,
            cfg=cfg,
            action_name=str(best.action_name),
        )
        current_reward = float(best.reward)
        history.append(
            {
                "group_id": str(np.asarray(current["group_ids"])[int(best.group_index)]),
                "group_index": int(best.group_index),
                "direction": -1,
                "action_name": str(best.action_name),
                "reward": float(best.reward),
                "estimated_cost": float(best.estimated_cost),
                "estimated_max_dcr": float(best.estimated_max_dcr),
                "estimated_drift_pct": float(best.estimated_drift_pct),
                "estimated_residual_drift_pct": float(best.estimated_residual_drift_pct),
            }
        )
    return {
        "state": current,
        "history": history,
        "final_reward": float(current_reward),
    }


def run_two_stage_search(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> dict[str, object]:
    baseline_cost = float(np.sum(np.asarray(state["group_cost_proxy"], dtype=np.float64)))
    baseline_eval = evaluate_stage_state(state=state, cfg=cfg)
    repair = greedy_feasible_repair(state=state, cfg=cfg)
    repaired_state = repair["state"]
    reduction = {"state": repaired_state, "history": [], "final_reward": 0.0}
    if bool(repair["feasible"]):
        reduction = greedy_cost_reduction(state=repaired_state, cfg=cfg)
    final_state = reduction["state"]
    final_cost = float(np.sum(np.asarray(final_state["group_cost_proxy"], dtype=np.float64)))
    final_eval = evaluate_stage_state(state=final_state, cfg=cfg)
    return {
        "baseline_cost": float(baseline_cost),
        "final_cost": float(final_cost),
        "cost_reduction": float(baseline_cost - final_cost),
        "baseline_violation_score": float(baseline_eval.violation_score),
        "final_violation_score": float(final_eval.violation_score),
        "feasible_after_repair": bool(repair["feasible"]),
        "repair_history": list(repair["history"]),
        "cost_reduction_history": list(reduction["history"]),
        "iteration_count_stage1": int(len(repair["history"])),
        "iteration_count_stage2": int(len(reduction["history"])),
        "final_state": final_state,
        "final_max_dcr": float(np.max(np.asarray(final_state["max_dcr"], dtype=np.float64))),
        "final_drift_pct": float(np.asarray(final_state["global_drift_pct"], dtype=np.float64)[0]),
        "final_residual_drift_pct": float(np.asarray(final_state["global_residual_drift_pct"], dtype=np.float64)[0]),
    }


def greedy_constrained_search(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
) -> dict[str, object]:
    staged = run_two_stage_search(state=state, cfg=cfg)
    final_state = staged["final_state"]
    history = list(staged["repair_history"]) + list(staged["cost_reduction_history"])
    baseline_reward = evaluate_reward(
        total_cost=float(staged["baseline_cost"]),
        max_dcr=float(np.max(np.asarray(state["max_dcr"], dtype=np.float64))),
        drift_pct=float(np.asarray(state["global_drift_pct"], dtype=np.float64)[0]),
        drift_limit_pct=float(cfg.drift_limit_pct),
        residual_drift_pct=float(np.asarray(state["global_residual_drift_pct"], dtype=np.float64)[0]),
        residual_drift_limit_pct=float(cfg.residual_drift_limit_pct),
        dcr_limit=float(cfg.dcr_limit),
        cfg=cfg,
        avg_congestion=float(np.mean(np.asarray(state["congestion"], dtype=np.float64))),
        avg_detailing_complexity=float(np.mean(np.asarray(state["detailing"], dtype=np.float64))),
        robustness_margin_min=float(np.min(np.asarray(state.get("robustness_margin", np.full(1, 0.25)), dtype=np.float64))),
        multi_hazard_margin_min=float(np.min(np.asarray(state.get("multi_hazard_margin", np.full(1, 0.25)), dtype=np.float64))),
        avg_constructability=float(np.mean(np.asarray(state.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64))),
    )
    current_reward = evaluate_reward(
        total_cost=float(staged["final_cost"]),
        max_dcr=float(staged["final_max_dcr"]),
        drift_pct=float(staged["final_drift_pct"]),
        drift_limit_pct=float(cfg.drift_limit_pct),
        residual_drift_pct=float(staged["final_residual_drift_pct"]),
        residual_drift_limit_pct=float(cfg.residual_drift_limit_pct),
        dcr_limit=float(cfg.dcr_limit),
        cfg=cfg,
        avg_congestion=float(np.mean(np.asarray(final_state["congestion"], dtype=np.float64))),
        avg_detailing_complexity=float(np.mean(np.asarray(final_state["detailing"], dtype=np.float64))),
        robustness_margin_min=float(np.min(np.asarray(final_state.get("robustness_margin", np.full(1, 0.25)), dtype=np.float64))),
        multi_hazard_margin_min=float(np.min(np.asarray(final_state.get("multi_hazard_margin", np.full(1, 0.25)), dtype=np.float64))),
        avg_constructability=float(np.mean(np.asarray(final_state.get("constructability_score", np.zeros(1, dtype=np.float64)), dtype=np.float64))),
    )
    return {
        "baseline_reward": float(baseline_reward),
        "final_reward": float(current_reward),
        "iteration_count": int(len(history)),
        "history": history,
        "final_rebar_ratio": np.asarray(final_state["rebar_ratio"], dtype=np.float64),
        "final_drift_pct": float(staged["final_drift_pct"]),
        "final_residual_drift_pct": float(staged["final_residual_drift_pct"]),
        "final_max_dcr": float(staged["final_max_dcr"]),
    }


def apply_group_action(
    *,
    rebar_ratio: np.ndarray,
    action_mask: np.ndarray,
    group_index: int,
    direction: int,
    cfg: DesignOptimizationConfig,
    action_name: str | None = None,
    action_mask_extended: np.ndarray | None = None,
    thickness_scale: np.ndarray | None = None,
    detailing_quality: np.ndarray | None = None,
) -> np.ndarray | dict[str, np.ndarray]:
    legacy_mode = (
        action_name is None
        and action_mask_extended is None
        and thickness_scale is None
        and detailing_quality is None
    )
    updated = np.asarray(rebar_ratio, dtype=np.float64).copy()
    updated_thickness = np.asarray(
        np.ones_like(updated) if thickness_scale is None else thickness_scale,
        dtype=np.float64,
    ).copy()
    updated_detailing = np.asarray(
        np.ones_like(updated) if detailing_quality is None else detailing_quality,
        dtype=np.float64,
    ).copy()
    if group_index < 0 or group_index >= updated.size:
        result = {
            "rebar_ratio": updated,
            "thickness_scale": updated_thickness,
            "detailing_quality": updated_detailing,
        }
        return updated if legacy_mode else result
    resolved_action = str(action_name or ("rebar_down" if int(direction) < 0 else "rebar_up"))
    action_alias = {
        "beam_section_up": "thickness_up",
        "beam_section_down": "thickness_down",
        "wall_thickness_up": "thickness_up",
        "wall_thickness_down": "thickness_down",
        "slab_thickness_up": "thickness_up",
        "slab_thickness_down": "thickness_down",
        "coupling_beam_up": "rebar_up",
        "coupling_beam_down": "rebar_down",
        "core_wall_up": "thickness_up",
        "core_wall_down": "thickness_down",
        "perimeter_frame_up": "rebar_up",
        "perimeter_frame_down": "rebar_down",
        "connection_detailing_up": "detailing_up",
        "connection_detailing_down": "detailing_down",
        "anchorage_reinforce": "detailing_up",
        "anchorage_simplify": "detailing_down",
        "splice_reinforce": "detailing_up",
        "splice_simplify": "detailing_down",
    }
    resolved_action = action_alias.get(resolved_action, resolved_action)
    if action_mask_extended is not None:
        action_lookup = {
            "rebar_down": 0,
            "rebar_up": 1,
            "thickness_down": 2,
            "thickness_up": 3,
            "detailing_down": 4,
            "detailing_up": 5,
        }
        idx = action_lookup.get(resolved_action, 1 if int(direction) >= 0 else 0)
        if not bool(action_mask_extended[group_index, idx]):
            result = {
                "rebar_ratio": updated,
                "thickness_scale": updated_thickness,
                "detailing_quality": updated_detailing,
            }
            return updated if legacy_mode else result
    elif not bool(action_mask[group_index, 0 if direction < 0 else 1]):
        result = {
            "rebar_ratio": updated,
            "thickness_scale": updated_thickness,
            "detailing_quality": updated_detailing,
        }
        return updated if legacy_mode else result
    if resolved_action.startswith("rebar_"):
        delta = float(cfg.rebar_step) * (-1.0 if resolved_action.endswith("_down") else 1.0)
        updated[group_index] = np.clip(updated[group_index] + delta, float(cfg.min_rebar_ratio), float(cfg.max_rebar_ratio))
    elif resolved_action.startswith("thickness_"):
        delta = float(cfg.thickness_step) * (-1.0 if resolved_action.endswith("_down") else 1.0)
        updated_thickness[group_index] = np.clip(updated_thickness[group_index] + delta, 0.80, 1.40)
    elif resolved_action.startswith("detailing_"):
        delta = float(cfg.detailing_step) * (-1.0 if resolved_action.endswith("_down") else 1.0)
        updated_detailing[group_index] = np.clip(updated_detailing[group_index] + delta, 0.60, 1.40)
    result = {
        "rebar_ratio": updated,
        "thickness_scale": updated_thickness,
        "detailing_quality": updated_detailing,
    }
    return updated if legacy_mode else result


def evaluate_reward(
    *,
    total_cost: float,
    max_dcr: float,
    drift_pct: float,
    drift_limit_pct: float,
    residual_drift_pct: float,
    residual_drift_limit_pct: float,
    dcr_limit: float,
    cfg: DesignOptimizationConfig,
    avg_congestion: float = 0.0,
    avg_detailing_complexity: float = 0.0,
    robustness_margin_min: float = 0.25,
    multi_hazard_margin_min: float = 0.25,
    avg_constructability: float = 0.0,
) -> float:
    dcr_penalty = max(float(max_dcr) - float(dcr_limit), 0.0) * float(cfg.dcr_penalty_scale)
    drift_penalty = max(float(drift_pct) - float(drift_limit_pct), 0.0) * float(cfg.drift_penalty_scale) * float(cfg.drift_weight_multiplier)
    residual_penalty = max(float(residual_drift_pct) - float(residual_drift_limit_pct), 0.0) * float(cfg.residual_penalty_scale) * float(cfg.residual_weight_multiplier)
    congestion_penalty = max(float(avg_congestion) - 0.55, 0.0) * float(cfg.congestion_penalty_scale) * float(cfg.congestion_weight)
    detailing_penalty = max(float(avg_detailing_complexity) - 0.35, 0.0) * float(cfg.detailing_complexity_penalty_scale) * float(cfg.detailing_complexity_weight)
    constructability_penalty = max(float(avg_constructability) - 0.45, 0.0) * float(cfg.constructability_penalty_scale) * float(cfg.constructability_weight)
    robustness_penalty = max(0.12 - float(robustness_margin_min), 0.0) * float(cfg.robustness_penalty_scale) * float(cfg.robustness_weight)
    multi_hazard_penalty = max(0.14 - float(multi_hazard_margin_min), 0.0) * float(cfg.multi_hazard_penalty_scale) * float(cfg.multi_hazard_weight)
    return float(
        -float(total_cost) * float(cfg.cost_weight)
        - dcr_penalty
        - drift_penalty
        - residual_penalty
        - congestion_penalty
        - detailing_penalty
        - constructability_penalty
        - robustness_penalty
        - multi_hazard_penalty
    )


__all__ = [
    "ACTION_FAMILY_BY_NAME",
    "ACTION_INDEX_V2",
    "ACTION_SPECS_V2",
    "CandidateEvaluation",
    "DesignOptimizationConfig",
    "LEGACY_ACTION_NAMES",
    "StageEvaluation",
    "aggregate_group_state",
    "apply_group_action",
    "evaluate_reward",
    "evaluate_candidate",
    "evaluate_stage_state",
    "greedy_cost_reduction",
    "project_group_cost_proxy",
    "hydrate_state_constructability_fields",
    "greedy_constrained_search",
    "greedy_feasible_repair",
    "run_two_stage_search",
]
