"""Candidate selection helpers for bounded design-optimization refactor."""

from __future__ import annotations

from typing import Callable

import numpy as np

from implementation.phase1.design_optimization_env import ACTION_FAMILY_BY_NAME, ACTION_INDEX_V2, DesignOptimizationConfig

SolverStageStateFn = Callable[..., dict[str, object]]
RefineMasksFn = Callable[..., dict[str, np.ndarray]]
EvaluateCandidateFn = Callable[..., dict[str, object] | None]
PreviewCandidateFn = Callable[..., dict[str, object] | None]
CostDownActionsFn = Callable[..., list[str]]


def _prefilter_group_indices(
    *,
    state: dict[str, np.ndarray],
    ranked: np.ndarray,
    max_groups: int,
) -> list[int]:
    member_types = np.asarray(state.get("member_type", np.asarray([], dtype="<U1")))
    zone_labels = np.asarray(state.get("zone_label", np.asarray([], dtype="<U1")))
    selected: list[int] = []
    seen: set[int] = set()
    member_counts: dict[str, int] = {}
    zone_counts: dict[str, int] = {}
    member_cap = max(2, int(np.ceil(float(max_groups) / 3.0)))
    zone_cap = max(2, int(np.ceil(float(max_groups) / 2.5)))

    for gi in ranked.tolist():
        gi = int(gi)
        member_type = str(member_types[gi]).strip().lower() if gi < member_types.size else ""
        zone_label = str(zone_labels[gi]).strip().lower() if gi < zone_labels.size else ""
        if member_counts.get(member_type, 0) >= member_cap and zone_counts.get(zone_label, 0) >= zone_cap:
            continue
        if gi not in seen:
            selected.append(gi)
            seen.add(gi)
            member_counts[member_type] = int(member_counts.get(member_type, 0)) + 1
            zone_counts[zone_label] = int(zone_counts.get(zone_label, 0)) + 1
        if len(selected) >= max_groups:
            break

    if len(selected) < max_groups:
        for gi in ranked.tolist():
            gi = int(gi)
            if gi not in seen:
                selected.append(gi)
                seen.add(gi)
            if len(selected) >= max_groups:
                break
    return selected


def _augment_prefilter_with_action_families(
    *,
    state: dict[str, np.ndarray],
    ranked: np.ndarray,
    selected: list[int],
    preferred_actions: dict[str, str],
    minimums: dict[str, int],
    max_groups: int,
) -> list[int]:
    action_mask_v2 = np.asarray(
        state.get("action_mask_v2", np.zeros((np.asarray(state.get("group_ids", np.asarray([], dtype="<U1"))).size, len(ACTION_INDEX_V2)), dtype=np.bool_)),
        dtype=np.bool_,
    )
    if action_mask_v2.size == 0:
        return selected
    selected_out = list(selected)
    seen = set(int(gi) for gi in selected_out)
    ranked_list = [int(gi) for gi in ranked.tolist()]
    ranked_position = {int(gi): idx for idx, gi in enumerate(ranked_list)}
    local_dcr = np.asarray(
        state.get("max_dcr", np.zeros(action_mask_v2.shape[0], dtype=np.float64)),
        dtype=np.float64,
    )
    detailing_quality = np.asarray(
        state.get("detailing_quality", np.ones(action_mask_v2.shape[0], dtype=np.float64)),
        dtype=np.float64,
    )
    detail_ratio = np.asarray(
        state.get("detailing", np.zeros(action_mask_v2.shape[0], dtype=np.float64)),
        dtype=np.float64,
    )
    detailing_complexity = np.asarray(
        state.get("detailing_complexity_score", detail_ratio),
        dtype=np.float64,
    )
    constructability = np.asarray(
        state.get("constructability_score", np.zeros(action_mask_v2.shape[0], dtype=np.float64)),
        dtype=np.float64,
    )
    zone_labels = np.asarray(
        state.get("zone_label", np.asarray([""] * action_mask_v2.shape[0])),
        dtype="<U32",
    )
    for family, minimum_count in minimums.items():
        if int(minimum_count) <= 0:
            continue
        action_name = str(preferred_actions.get(family, ""))
        action_idx = ACTION_INDEX_V2.get(action_name)
        if action_idx is None or action_idx >= action_mask_v2.shape[1]:
            continue
        existing = 0
        for gi in selected_out:
            if gi < action_mask_v2.shape[0] and bool(action_mask_v2[int(gi), action_idx]):
                existing += 1
        if existing >= int(minimum_count) and str(family).lower() != "connection_detailing":
            continue
        candidate_ranked_list = ranked_list
        if str(family).lower() == "connection_detailing":
            buckets: dict[str, list[int]] = {}
            for gi in ranked_list:
                if gi >= action_mask_v2.shape[0] or not bool(action_mask_v2[gi, action_idx]):
                    continue
                zone_key = str(zone_labels[gi]).strip().lower() if gi < zone_labels.shape[0] else ""
                buckets.setdefault(zone_key, []).append(int(gi))
            for zone_key, items in buckets.items():
                items.sort(
                    key=lambda gi: (
                        float(detailing_quality[gi]) if gi < detailing_quality.shape[0] else 1.0,
                        -float(detail_ratio[gi]) if gi < detail_ratio.shape[0] else 0.0,
                        -float(detailing_complexity[gi]) if gi < detailing_complexity.shape[0] else 0.0,
                        -float(constructability[gi]) if gi < constructability.shape[0] else 0.0,
                        float(local_dcr[gi]) if gi < local_dcr.shape[0] else 0.0,
                        int(ranked_position.get(int(gi), 0)),
                        zone_key,
                    ),
                )
            bucket_order = sorted(
                buckets,
                key=lambda zone_key: (
                    min(
                        (
                            float(detailing_quality[gi]) if gi < detailing_quality.shape[0] else 1.0,
                            -float(detail_ratio[gi]) if gi < detail_ratio.shape[0] else 0.0,
                            -float(detailing_complexity[gi]) if gi < detailing_complexity.shape[0] else 0.0,
                            -float(constructability[gi]) if gi < constructability.shape[0] else 0.0,
                            float(local_dcr[gi]) if gi < local_dcr.shape[0] else 0.0,
                        )
                        for gi in buckets[zone_key]
                    ),
                    zone_key,
                ),
            )
            candidate_ranked_list = []
            progress = True
            while progress:
                progress = False
                for zone_key in bucket_order:
                    items = buckets.get(zone_key, [])
                    if not items:
                        continue
                    candidate_ranked_list.append(int(items.pop(0)))
                    progress = True
            def _connection_pressure_key(gi: int) -> tuple[float, ...]:
                return (
                    float(detailing_quality[gi]) if gi < detailing_quality.shape[0] else 1.0,
                    -float(detail_ratio[gi]) if gi < detail_ratio.shape[0] else 0.0,
                    -float(detailing_complexity[gi]) if gi < detailing_complexity.shape[0] else 0.0,
                    -float(constructability[gi]) if gi < constructability.shape[0] else 0.0,
                    float(local_dcr[gi]) if gi < local_dcr.shape[0] else 0.0,
                    float(ranked_position.get(int(gi), 0)),
                )

            target_candidates = [
                int(gi)
                for gi in candidate_ranked_list
                if gi < action_mask_v2.shape[0] and bool(action_mask_v2[gi, action_idx])
            ]
            selected_family_gis = [
                int(gi)
                for gi in selected_out
                if int(gi) < action_mask_v2.shape[0] and bool(action_mask_v2[int(gi), action_idx])
            ]
            if len(selected_family_gis) >= int(minimum_count):
                desired = target_candidates[: int(minimum_count)]
                replaceable_family = sorted(
                    [gi for gi in selected_family_gis if gi not in desired],
                    key=_connection_pressure_key,
                    reverse=True,
                )
                for target_gi in desired:
                    if target_gi in seen:
                        continue
                    if not replaceable_family:
                        break
                    victim_gi = int(replaceable_family.pop(0))
                    victim_idx = selected_out.index(victim_gi)
                    seen.discard(victim_gi)
                    selected_out[victim_idx] = int(target_gi)
                    seen.add(int(target_gi))
        for gi in candidate_ranked_list:
            if gi >= action_mask_v2.shape[0] or not bool(action_mask_v2[gi, action_idx]) or gi in seen:
                continue
            if len(selected_out) >= int(max_groups):
                victim_idx = None
                victim_rank = -1
                for idx_selected, selected_gi in enumerate(selected_out):
                    if selected_gi >= action_mask_v2.shape[0] or bool(action_mask_v2[int(selected_gi), action_idx]):
                        continue
                    rank = int(ranked_position.get(int(selected_gi), -1))
                    if rank > victim_rank:
                        victim_rank = rank
                        victim_idx = idx_selected
                if victim_idx is None:
                    break
                seen.discard(int(selected_out[victim_idx]))
                selected_out[victim_idx] = gi
            else:
                selected_out.append(gi)
            seen.add(gi)
            existing += 1
            if existing >= int(minimum_count):
                break
    return selected_out[: int(max_groups)]


def _family_batched_preview_rows(
    *,
    preview_rows: list[dict[str, object]],
    total_budget: int,
    family_cap: int,
    constructability_families: set[str],
    min_constructability_gain: float,
    constructability_quota: int,
    preferred_family_minimums: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    buckets: dict[str, list[dict[str, object]]] = {}
    for row in preview_rows:
        family = str(row.get("action_family", "")).lower()
        buckets.setdefault(family, []).append(row)
    for family, rows in buckets.items():
        rows.sort(
            key=lambda item: (
                -float(item.get("selection_score", item.get("projected_cost_delta", 0.0) or 0.0)),
                float(item.get("local_max_dcr", 0.0) or 0.0)
                if str(family).lower() in {"connection_detailing", "perimeter_frame"}
                else 0.0,
                int(item.get("story_band", 0) or 0),
                str(item.get("zone_label", "")),
                str(item.get("group_id", "")),
                str(item.get("action_name", "")),
            )
        )

    ordered: list[dict[str, object]] = []
    family_counts: dict[str, int] = {}
    seen_pairs: set[tuple[str, str]] = set()

    preferred_families = sorted(
        constructability_families,
        key=lambda family: -float(buckets.get(family, [{}])[0].get("selection_score", 0.0) if buckets.get(family) else 0.0),
    )
    preferred_family_minimums = {
        str(family).lower(): int(count)
        for family, count in (preferred_family_minimums or {}).items()
        if int(count) > 0
    }
    constructability_selected = 0
    for family in preferred_families:
        if constructability_selected >= constructability_quota:
            break
        rows = buckets.get(family, [])
        while rows:
            row = rows.pop(0)
            pair = (str(row.get("group_id", "")), str(row.get("action_name", "")))
            if pair in seen_pairs:
                continue
            if float(row.get("constructability_gain", 0.0) or 0.0) < min_constructability_gain:
                continue
            ordered.append(row)
            seen_pairs.add(pair)
            family_counts[family] = int(family_counts.get(family, 0)) + 1
            constructability_selected += 1
            break

    for family, minimum_count in preferred_family_minimums.items():
        rows = buckets.get(family, [])
        while rows and int(family_counts.get(family, 0)) < minimum_count and len(ordered) < total_budget:
            row = rows.pop(0)
            pair = (str(row.get("group_id", "")), str(row.get("action_name", "")))
            if pair in seen_pairs:
                continue
            ordered.append(row)
            seen_pairs.add(pair)
            family_counts[family] = int(family_counts.get(family, 0)) + 1

    family_order = sorted(
        buckets,
        key=lambda family: (
            0 if family in constructability_families else 1,
            -float(buckets[family][0].get("selection_score", 0.0) if buckets[family] else 0.0),
            family,
        ),
    )
    while len(ordered) < total_budget:
        progress = False
        for family in family_order:
            rows = buckets.get(family, [])
            if not rows:
                continue
            if int(family_counts.get(family, 0)) >= family_cap:
                continue
            row = rows.pop(0)
            pair = (str(row.get("group_id", "")), str(row.get("action_name", "")))
            if pair in seen_pairs:
                continue
            ordered.append(row)
            seen_pairs.add(pair)
            family_counts[family] = int(family_counts.get(family, 0)) + 1
            progress = True
            if len(ordered) >= total_budget:
                break
        if not progress:
            break
    return ordered


def _reserved_family_order_key(row: dict[str, object]) -> tuple[object, ...]:
    family = str(row.get("action_family", "")).lower()
    local_dcr = float(row.get("local_max_dcr", 0.0) or 0.0)
    constructability_gain = float(row.get("constructability_gain", 0.0) or 0.0)
    selection_score = float(row.get("selection_score", row.get("projected_cost_delta", 0.0) or 0.0))
    if family == "connection_detailing":
        return (
            local_dcr,
            -constructability_gain,
            -selection_score,
            float(row.get("story_band", 0) or 0),
            str(row.get("zone_label", "")),
            str(row.get("group_id", "")),
            str(row.get("action_name", "")),
        )
    return (
        -selection_score,
        local_dcr,
        float(row.get("story_band", 0) or 0),
        str(row.get("zone_label", "")),
        str(row.get("group_id", "")),
        str(row.get("action_name", "")),
    )


def _ordered_reserved_family_previews(
    family_name: str,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if str(family_name).lower() != "connection_detailing":
        return sorted(rows, key=_reserved_family_order_key)
    buckets: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        key = str(row.get("zone_label", "")).lower()
        buckets.setdefault(key, []).append(row)
    for bucket_rows in buckets.values():
        bucket_rows.sort(key=_reserved_family_order_key)
    bucket_order = sorted(
        buckets,
        key=lambda key: (
            min(float(row.get("local_max_dcr", 0.0) or 0.0) for row in buckets[key]),
            str(key),
        ),
    )
    ordered: list[dict[str, object]] = []
    progress = True
    while progress:
        progress = False
        for key in bucket_order:
            bucket_rows = buckets.get(key, [])
            if not bucket_rows:
                continue
            ordered.append(bucket_rows.pop(0))
            progress = True
    return ordered


def run_cost_reduction_selection(
    *,
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    ndtha_step_count: int,
    max_iterations: int,
    batch_limit: int,
    solver_stage_state_fn: SolverStageStateFn,
    refine_masks_fn: RefineMasksFn,
    evaluate_candidate_fn: EvaluateCandidateFn,
    preview_candidate_fn: PreviewCandidateFn | None,
    cost_down_actions_for_group_fn: CostDownActionsFn,
) -> dict[str, object]:
    refined_input = refine_masks_fn(state=state, cfg=cfg)
    current_state = {k: np.asarray(v).copy() for k, v in refined_input.items()}
    baseline_state = {k: np.asarray(v).copy() for k, v in refined_input.items()}
    baseline_solver = solver_stage_state_fn(state=current_state, cfg=cfg, step_count=ndtha_step_count)
    current_solver = dict(baseline_solver)
    accepted: list[dict[str, object]] = []
    preview_supply_family_counts_total: dict[str, int] = {}
    preview_evaluated_family_counts_total: dict[str, int] = {}
    diversity_bias = float(
        max(
            (
                float(cfg.constructability_weight)
                + 0.70 * float(cfg.detailing_complexity_weight)
                + 0.50 * float(cfg.congestion_weight)
            )
            / max(float(cfg.cost_weight), 1.0e-9),
            1.0,
        )
    )

    if not bool(baseline_solver["feasible"]):
        return {
            "baseline_state": baseline_state,
            "baseline_solver": baseline_solver,
            "final_solver": current_solver,
            "final_state": current_state,
            "accepted": accepted,
            "blocked": True,
            "block_reason": "ERR_NOT_FEASIBLE",
        }

    for _ in range(max(int(max_iterations), 0)):
        historical_family_counts: dict[str, int] = {}
        for row in accepted:
            family = str(row.get("action_family", ACTION_FAMILY_BY_NAME.get(str(row.get("action_name", "")), str(row.get("action_name", ""))))).lower()
            historical_family_counts[family] = int(historical_family_counts.get(family, 0)) + 1
        current_state = refine_masks_fn(state=current_state, cfg=cfg)
        current_rebar = np.asarray(current_state["rebar_ratio"], dtype=np.float64)
        combo_risk = np.asarray(current_state.get("combination_risk", np.ones_like(current_rebar)), dtype=np.float64)
        combo_match = np.asarray(current_state.get("combination_match_score", np.ones_like(current_rebar)), dtype=np.float64)
        repair = np.asarray(current_state["repair_influence"], dtype=np.float64)
        detail = np.asarray(current_state["detailing"], dtype=np.float64)
        cost = np.asarray(current_state["group_cost_proxy"], dtype=np.float64)
        priority = cost * (1.0 + 0.30 * np.maximum(combo_risk - 1.0, 0.0)) / (
            1.0 + repair + 0.40 * detail + 0.20 * np.maximum(1.0 - combo_match, 0.0)
        )
        ranked = np.argsort(-priority)
        prefilter_limit = max(8, min(int(current_rebar.size), int(max(batch_limit * 5, 12))))
        candidate_group_indices = _prefilter_group_indices(
            state=current_state,
            ranked=ranked,
            max_groups=prefilter_limit,
        )
        preferred_action_names = {
            "beam_section": "beam_section_down",
            "wall_thickness": "wall_thickness_down",
            "connection_detailing": "connection_detailing_down",
            "detailing": "detailing_down",
            "perimeter_frame": "perimeter_frame_down",
        }
        candidate_group_indices = _augment_prefilter_with_action_families(
            state=current_state,
            ranked=ranked,
            selected=candidate_group_indices,
            preferred_actions=preferred_action_names,
            minimums={
                "beam_section": 2 if int(batch_limit) >= 4 else 1,
                "wall_thickness": 1,
                "connection_detailing": 3 if int(batch_limit) >= 8 else 2 if int(batch_limit) >= 6 else 1,
                "detailing": 2 if int(batch_limit) >= 8 else 1,
                "perimeter_frame": 1 if int(batch_limit) >= 8 else 0,
            },
            max_groups=prefilter_limit,
        )
        preview_rows: list[dict[str, object]] = []
        constructability_families = {"beam_section", "wall_thickness", "connection_detailing", "detailing", "perimeter_frame"}
        preferred_representation_families = ("beam_section", "perimeter_frame", "connection_detailing", "wall_thickness", "detailing")
        min_constructability_gain = 0.012 if diversity_bias > 1.0 else 0.0
        constructability_quota = 1 if int(batch_limit) <= 3 else (4 if int(batch_limit) >= 8 else min(2, int(batch_limit)))
        for gi in candidate_group_indices:
            gi = int(gi)
            for action_name in cost_down_actions_for_group_fn(state=current_state, group_index=gi):
                preview = (
                    preview_candidate_fn(
                        state=current_state,
                        current_solver=current_solver,
                        cfg=cfg,
                        group_index=gi,
                        action_name=action_name,
                    )
                    if preview_candidate_fn is not None
                    else evaluate_candidate_fn(
                        state=current_state,
                        current_solver=current_solver,
                        cfg=cfg,
                        ndtha_step_count=ndtha_step_count,
                        group_index=gi,
                        action_name=action_name,
                    )
                )
                if preview is None:
                    continue
                family = str(preview.get("action_family", ACTION_FAMILY_BY_NAME.get(str(preview["action_name"]), str(preview["action_name"]))))
                member_type = str(preview["member_type"]).lower()
                family_bonus = {
                    "beam_section": 1.24,
                    "wall_thickness": 0.98,
                    "connection_detailing": 1.36,
                    "detailing": 1.14,
                    "core_wall": 1.08,
                    "perimeter_frame": 1.18,
                    "coupling_beam": 1.05,
                    "slab_thickness": 0.98,
                    "rebar": 0.94,
                }.get(family, 1.0)
                member_bonus = {
                    "beam": 1.14,
                    "wall": 1.12,
                    "connection": 1.10,
                    "column": 1.04,
                    "slab": 0.95,
                }.get(member_type, 1.0)
                local_dcr = float(
                    np.asarray(
                        current_state.get("max_dcr", np.zeros_like(current_rebar, dtype=np.float64)),
                        dtype=np.float64,
                    )[gi]
                )
                constructability_signal = float(preview.get("constructability_gain", 0.0) or 0.0)
                congestion_signal = float(preview.get("congestion_gain", 0.0) or 0.0)
                detailing_signal = float(preview.get("detailing_gain", 0.0) or 0.0)
                diversity_penalty = 1.0
                if family == "connection_detailing":
                    if local_dcr >= 0.80:
                        diversity_penalty *= 0.12
                    elif local_dcr >= 0.65:
                        diversity_penalty *= 0.45
                    elif local_dcr <= 0.35:
                        diversity_penalty *= 1.12
                if family in {"rebar", "slab_thickness"} and constructability_signal <= 0.02:
                    diversity_penalty *= 0.82
                if family in {"beam_section", "wall_thickness", "connection_detailing", "detailing", "perimeter_frame"} and constructability_signal > 0.0:
                    diversity_penalty *= 1.08
                historical_count = int(historical_family_counts.get(family, 0))
                if family == "rebar" and historical_count > 0:
                    diversity_penalty *= max(0.48, 1.0 - 0.14 * float(historical_count))
                elif family == "slab_thickness" and historical_count > 0:
                    diversity_penalty *= max(0.60, 1.0 - 0.12 * float(historical_count))
                elif family == "detailing" and historical_count > 0:
                    diversity_penalty *= max(0.62, 1.0 - 0.10 * float(historical_count))
                elif family == "wall_thickness" and historical_count > 0:
                    diversity_penalty *= max(0.28, 1.0 - 0.22 * float(historical_count))
                score = (
                    float(preview["projected_cost_delta"]) * float(cfg.cost_weight)
                    + 120.0 * constructability_signal * float(cfg.constructability_weight)
                    + 90.0 * congestion_signal * float(cfg.congestion_weight)
                    + 100.0 * detailing_signal * float(cfg.detailing_complexity_weight)
                )
                preview["local_max_dcr"] = float(local_dcr)
                preview["selection_score"] = float(score) * family_bonus * member_bonus * diversity_penalty
                preview_rows.append(preview)
        if not preview_rows:
            break
        preferred_family_minimums = {
            family: count
            for family, count in {
                "beam_section": 2 if int(batch_limit) >= 4 else 1,
                "wall_thickness": 1,
                "connection_detailing": 3 if int(batch_limit) >= 8 else 2 if int(batch_limit) >= 6 else 1,
                "detailing": 2 if int(batch_limit) >= 8 else 1,
                "perimeter_frame": 1 if int(batch_limit) >= 8 else 0,
            }.items()
            if any(str(row.get("action_family", "")).lower() == family for row in preview_rows)
        }
        for row in preview_rows:
            family = str(row.get("action_family", "")).lower()
            preview_supply_family_counts_total[family] = int(preview_supply_family_counts_total.get(family, 0)) + 1
        candidate_rows: list[dict[str, object]] = []
        seen_preview_pairs: set[tuple[str, str]] = set()
        counted_preview_pairs: set[tuple[str, str]] = set()
        preview_family_counts: dict[str, int] = {}
        preview_eval_budget = max(int(batch_limit) * 3, 9)
        preview_family_cap = max(2, int(np.ceil(float(batch_limit) / 1.5)))
        preview_eval_rows = _family_batched_preview_rows(
            preview_rows=preview_rows,
            total_budget=preview_eval_budget,
            family_cap=preview_family_cap,
            constructability_families=constructability_families,
            min_constructability_gain=min_constructability_gain,
            constructability_quota=constructability_quota,
            preferred_family_minimums=preferred_family_minimums,
        )
        for preview in preview_eval_rows:
            pair = (str(preview["group_id"]), str(preview["action_name"]))
            family = str(preview.get("action_family", "")).lower()
            if pair in seen_preview_pairs:
                continue
            if int(preview_family_counts.get(family, 0)) >= preview_family_cap:
                continue
            candidate = evaluate_candidate_fn(
                state=current_state,
                current_solver=current_solver,
                cfg=cfg,
                ndtha_step_count=ndtha_step_count,
                group_index=int(preview["group_index"]),
                action_name=str(preview["action_name"]),
            )
            if candidate is None:
                continue
            candidate["selection_score"] = float(preview.get("selection_score", candidate["projected_cost_delta"]))
            candidate_rows.append(candidate)
            seen_preview_pairs.add(pair)
            counted_preview_pairs.add(pair)
            preview_family_counts[family] = int(preview_family_counts.get(family, 0)) + 1
            preview_evaluated_family_counts_total[family] = int(preview_evaluated_family_counts_total.get(family, 0)) + 1
            if len(candidate_rows) >= preview_eval_budget:
                break
        if not candidate_rows:
            break
        candidate_rows.sort(
            key=lambda item: (
                0
                if (
                    str(item.get("action_family", "")).lower() in constructability_families
                    and float(item.get("constructability_gain", 0.0) or 0.0) >= min_constructability_gain
                )
                else 1,
                -float(item.get("selection_score", item.get("projected_cost_delta", 0.0) or 0.0)),
                int(item.get("story_band", 0) or 0),
                str(item.get("zone_label", "")),
                str(item.get("group_id", "")),
                str(item.get("action_name", "")),
            )
        )
        batch_selected = 0
        batch_state = {k: np.asarray(v).copy() for k, v in current_state.items()}
        batch_solver = dict(current_solver)
        used_groups: set[str] = set()
        used_member_types: set[str] = set()
        used_action_families: set[str] = set()
        family_counts: dict[str, int] = {}
        progress = False
        same_family_cap = 1 if int(batch_limit) <= 3 else max(1, int(np.ceil(float(batch_limit) / (5.0 if diversity_bias > 1.05 else 4.0))))
        family_cap_overrides = {
            "connection_detailing": min(3, same_family_cap + 1) if int(batch_limit) >= 6 else same_family_cap,
        }
        constructability_selected = 0
        global_family_caps = {
            "rebar": max(2, int(np.ceil(float(len(accepted) + batch_limit) / 9.0))),
            "slab_thickness": max(2, int(np.ceil(float(len(accepted) + batch_limit) / 10.0))),
            "wall_thickness": max(7, int(np.ceil(float(len(accepted) + batch_limit) / 6.5))),
        }
        soft_family_targets = {
            "detailing": max(4, int(np.ceil(float(len(accepted) + batch_limit) / 8.5))),
            "wall_thickness": max(2, int(np.ceil(float(len(accepted) + batch_limit) / 11.0))),
        }
        minimum_family_targets = {
            "beam_section": 1,
            "connection_detailing": 4 if sum(1 for row in preview_eval_rows if str(row.get("action_family", "")).lower() == "connection_detailing") >= 4 and int(batch_limit) >= 8 else 3 if sum(1 for row in preview_eval_rows if str(row.get("action_family", "")).lower() == "connection_detailing") >= 3 and int(batch_limit) >= 6 else 2 if sum(1 for row in preview_eval_rows if str(row.get("action_family", "")).lower() == "connection_detailing") >= 2 else 1,
            "detailing": 2 if int(batch_limit) >= 8 else 1,
            "perimeter_frame": 1 if any(str(row.get("action_family", "")).lower() == "perimeter_frame" for row in preview_eval_rows) and int(batch_limit) >= 6 else 0,
        }
        reserved_family_targets = {
            "perimeter_frame": 1 if any(str(row.get("action_family", "")).lower() == "perimeter_frame" for row in preview_rows) and int(batch_limit) >= 6 else 0,
            "connection_detailing": 1 if any(str(row.get("action_family", "")).lower() == "connection_detailing" for row in preview_rows) and int(batch_limit) >= 6 else 0,
        }
        reserved_attempted_pairs: set[tuple[str, str]] = set()

        def _accept_candidate(candidate: dict[str, object], *, bypass_family_cap: bool = False) -> bool:
            nonlocal batch_selected, batch_state, batch_solver, progress, constructability_selected
            group_id = str(candidate["group_id"])
            member_type = str(candidate["member_type"]).lower()
            action_family = str(candidate.get("action_family", ACTION_FAMILY_BY_NAME.get(str(candidate["action_name"]), str(candidate["action_name"])))).lower()
            pair = (group_id, str(candidate["action_name"]))
            if group_id in used_groups:
                return False
            historical_count = int(historical_family_counts.get(action_family, 0))
            if action_family in global_family_caps and historical_count >= int(global_family_caps[action_family]):
                return False
            family_cap = int(family_cap_overrides.get(action_family, same_family_cap))
            if not bypass_family_cap and int(family_counts.get(action_family, 0)) >= family_cap:
                return False
            fresh_candidate = evaluate_candidate_fn(
                state=batch_state,
                current_solver=batch_solver,
                cfg=cfg,
                ndtha_step_count=ndtha_step_count,
                group_index=int(candidate["group_index"]),
                action_name=str(candidate["action_name"]),
            )
            if fresh_candidate is None:
                return False
            if pair not in counted_preview_pairs:
                counted_preview_pairs.add(pair)
                preview_evaluated_family_counts_total[action_family] = int(preview_evaluated_family_counts_total.get(action_family, 0)) + 1
            batch_state = {k: np.asarray(v).copy() for k, v in fresh_candidate["trial_state"].items()}
            batch_solver = dict(fresh_candidate["trial_solver"])
            used_groups.add(group_id)
            used_member_types.add(member_type)
            used_action_families.add(action_family)
            family_counts[action_family] = int(family_counts.get(action_family, 0)) + 1
            historical_family_counts[action_family] = int(historical_family_counts.get(action_family, 0)) + 1
            batch_selected += 1
            progress = True
            if (
                action_family in constructability_families
                and float(candidate.get("constructability_gain", 0.0) or 0.0) >= min_constructability_gain
            ):
                constructability_selected += 1
            accepted.append(
                {
                    "group_id": group_id,
                    "group_index": int(candidate["group_index"]),
                    "story_band": int(candidate["story_band"]),
                    "zone_label": str(candidate["zone_label"]),
                    "member_type": str(candidate["member_type"]),
                    "semantic_group": str(np.asarray(batch_state.get("semantic_group", np.asarray([""] * np.asarray(batch_state["group_ids"]).size)))[int(candidate["group_index"])]),
                    "action_name": str(candidate["action_name"]),
                    "action_family": str(candidate.get("action_family", ACTION_FAMILY_BY_NAME.get(str(candidate["action_name"]), str(candidate["action_name"])))),
                    "cost_proxy": float(batch_solver["cost_proxy"]),
                    "max_dcr": float(batch_solver["max_dcr"]),
                    "max_drift_pct": float(batch_solver["max_drift_pct"]),
                    "residual_drift_pct": float(batch_solver["residual_drift_pct"]),
                    "projected_cost_delta": float(candidate["projected_cost_delta"]),
                    "priority": float(candidate["priority"]),
                    "current_congestion": float(candidate.get("current_congestion", 0.0) or 0.0),
                    "trial_congestion": float(candidate.get("trial_congestion", 0.0) or 0.0),
                    "current_detailing_complexity": float(candidate.get("current_detailing_complexity", 0.0) or 0.0),
                    "trial_detailing_complexity": float(candidate.get("trial_detailing_complexity", 0.0) or 0.0),
                    "current_constructability": float(candidate.get("current_constructability", 0.0) or 0.0),
                    "trial_constructability": float(candidate.get("trial_constructability", 0.0) or 0.0),
                    "constructability_gain": float(candidate.get("constructability_gain", 0.0) or 0.0),
                    "congestion_gain": float(candidate.get("congestion_gain", 0.0) or 0.0),
                    "detailing_gain": float(candidate.get("detailing_gain", 0.0) or 0.0),
                }
            )
            return True

        def _reserve_family_slot(family_name: str, target_count: int) -> None:
            if int(target_count) <= 0:
                return
            attempt_cap = max(8, int(batch_limit) * 3)
            attempts = 0
            while (
                batch_selected < batch_limit
                and int(family_counts.get(family_name, 0)) < int(target_count)
            ):
                progress_reserved = False
                family_previews = [
                    row
                    for row in preview_rows
                    if str(row.get("action_family", "")).lower() == family_name
                    and str(row.get("group_id", "")) not in used_groups
                    and (str(row.get("group_id", "")), str(row.get("action_name", ""))) not in reserved_attempted_pairs
                ]
                family_previews = _ordered_reserved_family_previews(family_name, family_previews)
                for candidate in family_previews:
                    pair = (str(candidate.get("group_id", "")), str(candidate.get("action_name", "")))
                    reserved_attempted_pairs.add(pair)
                    attempts += 1
                    if _accept_candidate(candidate, bypass_family_cap=True):
                        progress_reserved = True
                        break
                    if attempts >= attempt_cap:
                        break
                if not progress_reserved or attempts >= attempt_cap:
                    break

        for family_name, target_count in reserved_family_targets.items():
            _reserve_family_slot(family_name, int(target_count))

        prioritized_constructability_candidates = [
            candidate
            for candidate in candidate_rows
            if str(candidate.get("action_family", "")).lower() in constructability_families
            and float(candidate.get("constructability_gain", 0.0) or 0.0) >= min_constructability_gain
        ]
        for family_name in preferred_representation_families:
            if batch_selected >= batch_limit:
                break
            if int(family_counts.get(family_name, 0)) >= int(minimum_family_targets.get(family_name, 0)):
                continue
            family_candidates = [
                candidate
                for candidate in prioritized_constructability_candidates
                if str(candidate.get("action_family", "")).lower() == family_name
                and str(candidate.get("action_family", "")).lower() not in used_action_families
            ]
            for candidate in family_candidates:
                if _accept_candidate(candidate, bypass_family_cap=True):
                    break
        for candidate in prioritized_constructability_candidates:
            if batch_selected >= batch_limit or constructability_selected >= constructability_quota:
                break
            action_family = str(candidate.get("action_family", "")).lower()
            if action_family in used_action_families:
                continue
            _accept_candidate(candidate, bypass_family_cap=True)

        for round_index in range(3):
            for candidate in candidate_rows:
                if batch_selected >= batch_limit:
                    break
                group_id = str(candidate["group_id"])
                member_type = str(candidate["member_type"]).lower()
                action_family = str(candidate.get("action_family", ACTION_FAMILY_BY_NAME.get(str(candidate["action_name"]), str(candidate["action_name"])))).lower()
                constructability_gain = float(candidate.get("constructability_gain", 0.0) or 0.0)
                if group_id in used_groups:
                    continue
                if int(family_counts.get(action_family, 0)) >= same_family_cap:
                    continue
                if action_family in global_family_caps and int(historical_family_counts.get(action_family, 0)) >= int(global_family_caps[action_family]):
                    continue
                if (
                    action_family in soft_family_targets
                    and int(historical_family_counts.get(action_family, 0)) >= int(soft_family_targets[action_family])
                    and any(
                        str(other.get("group_id", "")) not in used_groups
                        and str(other.get("action_family", "")).lower() != action_family
                        for other in candidate_rows
                    )
                ):
                    continue
                if (
                    constructability_selected < constructability_quota
                    and (
                        action_family in {"rebar", "slab_thickness"}
                        or constructability_gain < min_constructability_gain
                    )
                    and any(
                        str(other.get("action_family", "")).lower() in constructability_families
                        and float(other.get("constructability_gain", 0.0) or 0.0) >= min_constructability_gain
                        and str(other.get("group_id", "")) not in used_groups
                        for other in candidate_rows
                    )
                ):
                    continue
                if (
                    round_index == 0
                    and action_family in {"rebar", "slab_thickness"}
                    and constructability_gain < min_constructability_gain
                    and any(
                        str(other.get("action_family", "")).lower() not in {"rebar", "slab_thickness"}
                        and float(other.get("constructability_gain", 0.0) or 0.0) >= min_constructability_gain
                        for other in candidate_rows
                    )
                ):
                    continue
                if round_index == 0 and used_action_families and action_family in used_action_families:
                    continue
                if round_index == 1 and used_member_types and member_type in used_member_types:
                    continue
                if round_index == 1 and used_action_families and action_family in used_action_families and used_member_types:
                    continue
                _accept_candidate(candidate)
            if batch_selected >= batch_limit:
                break
        if not progress:
            break
        current_state = refine_masks_fn(state=batch_state, cfg=cfg)
        current_solver = dict(batch_solver)

    return {
        "baseline_state": baseline_state,
        "baseline_solver": baseline_solver,
        "final_solver": current_solver,
        "final_state": current_state,
        "accepted": accepted,
        "preview_supply_family_counts": {str(k): int(v) for k, v in sorted(preview_supply_family_counts_total.items())},
        "preview_evaluated_family_counts": {str(k): int(v) for k, v in sorted(preview_evaluated_family_counts_total.items())},
        "blocked": False,
        "block_reason": "",
    }


__all__ = ["run_cost_reduction_selection"]
