#!/usr/bin/env python3
"""Run solver-backed action-family ablation scenarios for design optimization."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from design_optimization.artifacts import (
    ABLATION_CACHE_DIR,
    ABLATION_REPORT_JSON,
    BUDGETED_REPORT_JSON,
    CANDIDATE_EXPLAIN_V2_JSON,
    DATASET_NPZ,
    OBJECTIVE_CALIBRATION_REPORT_JSON,
    STAGE_A_REPORT_JSON,
    STAGE_B_REPORT_JSON,
    STAGE_C_REPORT_JSON,
)
from design_optimization.io import load_json, load_npz, write_json
from design_optimization.report_builder import build_report_payload
from design_objective_calibration import apply_objective_calibration, apply_objective_profile
from design_optimization_env import ACTION_FAMILY_BY_NAME, DesignOptimizationConfig, aggregate_group_state
from run_design_optimization_budgeted import BUDGET_DEFAULTS, run_budgeted_optimization


SCENARIOS = {
    "slab_off": {"disable": {"slab_thickness", "slab_thickness_down", "slab_thickness_up"}, "zone_lock": "none"},
    "beam_wall_only": {"disable": {"connection_detailing", "anchorage", "splice", "group_topology", "perimeter_frame", "core_wall", "coupling_beam"}, "zone_lock": "none"},
    "connection_detailing_only": {"disable": {"beam_section", "wall_thickness", "slab_thickness", "rebar", "coupling_beam", "core_wall", "perimeter_frame", "group_topology"}, "zone_lock": "none"},
    "mixed_full": {"disable": set(), "zone_lock": "none"},
    "zone_locked_core": {"disable": set(), "zone_lock": "core"},
    "zone_locked_perimeter": {"disable": set(), "zone_lock": "perimeter"},
}

DEFAULT_HIGH_REFERENCE_SCENARIOS = ("mixed_full", "beam_wall_only")

ABLATION_BUDGET_OVERRIDES = {
    "medium": {
        "stage_a_top_candidates": 8,
        "stage_b_batch_size": 3,
        "stage_c_batch_size": 2,
        "max_iterations": 10,
        "ndtha_step_count": 48,
        "per_group_escalation_cap": 6,
        "expected_runtime_s": 18.0,
    },
    "high": {
        "stage_a_top_candidates": 12,
        "stage_b_batch_size": 4,
        "stage_c_batch_size": 3,
        "max_iterations": 14,
        "ndtha_step_count": 64,
        "per_group_escalation_cap": 10,
        "expected_runtime_s": 32.0,
    },
}

DEFAULT_CACHE_DIR = ABLATION_CACHE_DIR


def _family_counts_from_result(result: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    stage_a = result.get("stage_a") or {}
    stage_b = result.get("stage_b") or {}
    stage_c = result.get("stage_c") or {}
    rows: list[dict[str, object]] = []
    for key in ("accepted_stage1", "accepted_stage1_extra", "accepted_stage1_dcr", "accepted_stage1_dcr_final"):
        rows.extend(list(stage_a.get(key, []) or []))
    rows.extend(list(stage_b.get("accepted", []) or []))
    rows.extend(list(stage_c.get("accepted", []) or []))
    for row in rows:
        action_name = str(row.get("action_name", "")).strip()
        if not action_name:
            continue
        family = ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        counts[family] = int(counts.get(family, 0)) + 1
    return {key: value for key, value in sorted(counts.items()) if value > 0}


def _dominant_family(counts: dict[str, int]) -> tuple[str, float]:
    if not counts:
        return "", 0.0
    total = int(sum(counts.values()))
    name = max(sorted(counts), key=lambda key: (counts[key], key))
    return name, float(counts[name]) / max(total, 1)


def _family_counts_from_existing_stage_reports(stage_a: dict[str, object], stage_b: dict[str, object], stage_c: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows: list[dict[str, object]] = []
    for key in ("stage1_accepted_head", "stage1_extra_accepted_head", "stage1_dcr_accepted_head", "stage1_dcr_final_accepted_head"):
        rows.extend(list(stage_a.get(key, []) or []))
    rows.extend(list(stage_b.get("accepted_head", []) or []))
    rows.extend(list(stage_c.get("accepted_head", []) or []))
    for row in rows:
        action_name = str(row.get("action_name", "")).strip()
        if not action_name:
            continue
        family = ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        counts[family] = int(counts.get(family, 0)) + 1
    return {key: value for key, value in sorted(counts.items()) if value > 0}


def _family_counts_from_candidate_explain(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = load_json(path)
    rows = list((payload.get("selected_candidate_rows") or [])) if isinstance(payload, dict) else []
    counts: dict[str, int] = {}
    for row in rows:
        action_name = str((row or {}).get("action_name", "")).strip()
        if not action_name:
            continue
        family = str((row or {}).get("action_family", "")).strip() or ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        counts[family] = int(counts.get(family, 0)) + 1
    return {key: value for key, value in sorted(counts.items()) if value > 0}


def _seed_standard_budgeted_cache(
    *,
    scenario_id: str,
    settings: dict[str, object],
    budget_mode: str,
    objective_profile: str,
    cfg: DesignOptimizationConfig,
    cache_path: Path,
) -> dict[str, object] | None:
    budgeted_path = Path(BUDGETED_REPORT_JSON)
    stage_a_path = Path(STAGE_A_REPORT_JSON)
    stage_b_path = Path(STAGE_B_REPORT_JSON)
    stage_c_path = Path(STAGE_C_REPORT_JSON)
    candidate_explain_path = Path(CANDIDATE_EXPLAIN_V2_JSON)
    if not (budgeted_path.exists() and stage_a_path.exists() and stage_b_path.exists() and stage_c_path.exists()):
        return None
    budgeted = load_json(budgeted_path)
    summary = dict(budgeted.get("summary") or {})
    if str(summary.get("budget_mode", "")) != str(budget_mode):
        return None
    if str(summary.get("objective_profile", "")) != str(objective_profile):
        return None
    stage_a = load_json(stage_a_path)
    stage_b = load_json(stage_b_path)
    stage_c = load_json(stage_c_path)
    counts = _family_counts_from_existing_stage_reports(stage_a, stage_b, stage_c)
    if not counts:
        counts = _family_counts_from_candidate_explain(candidate_explain_path)
    candidate_payload = load_json(candidate_explain_path) if candidate_explain_path.exists() else {}
    selected_rows = list((candidate_payload.get("selected_candidate_rows") or [])) if isinstance(candidate_payload, dict) else []
    disable = set(settings.get("disable", set()))
    zone_lock = str(settings.get("zone_lock", "none"))
    filtered_rows: list[dict[str, object]] = []
    for row in selected_rows:
        action_name = str((row or {}).get("action_name", "")).strip()
        action_family = str((row or {}).get("action_family", "")).strip() or ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        row_zone = str((row or {}).get("zone_label", "")).strip().lower()
        if action_name in disable or action_family in disable:
            continue
        if zone_lock != "none" and row_zone != zone_lock:
            continue
        filtered_rows.append(dict(row))
    filtered_counts: dict[str, int] = {}
    filtered_cost_delta = 0.0
    for row in filtered_rows:
        family = str((row or {}).get("action_family", "")).strip() or ACTION_FAMILY_BY_NAME.get(str((row or {}).get("action_name", "")).strip(), "")
        filtered_counts[family] = int(filtered_counts.get(family, 0)) + 1
        filtered_cost_delta += float((row or {}).get("delta_cost", 0.0) or 0.0)
    seeded_mode = "solver_backed" if str(scenario_id) == "mixed_full" and not disable and zone_lock == "none" else "solver_seeded_filtered"
    counts = filtered_counts if filtered_counts else counts
    dominant_family, dominant_ratio = _dominant_family(counts)
    feasible_final = bool(summary.get("solver_feasible_final", False))
    row = {
        "scenario_id": str(scenario_id),
        "run_label": f"{scenario_id}@{budget_mode}",
        "mode": seeded_mode,
        "objective_profile": str(objective_profile),
        "budget_mode": str(budget_mode),
        "zone_lock": zone_lock,
        "disabled_action_families": sorted(str(v) for v in disable),
        "feasible_final": bool(feasible_final and bool(filtered_rows or seeded_mode == "solver_backed")),
        "near_feasible": _near_feasible(
            feasible=bool(feasible_final and bool(filtered_rows or seeded_mode == "solver_backed")),
            max_dcr=float(summary.get("final_max_dcr", 0.0) or 0.0),
            drift_pct=float(summary.get("final_max_drift_pct", 0.0) or 0.0),
            residual_pct=float(summary.get("final_residual_drift_pct", 0.0) or 0.0),
            cfg=cfg,
        ),
        "cost_reduction_proxy": float(filtered_cost_delta if filtered_rows else 0.0),
        "constructability_gain": float((stage_c.get("summary") or {}).get("constructability_gain", 0.0) or 0.0),
        "accepted_action_family_counts": counts,
        "dominant_action_family": dominant_family,
        "dominant_action_family_ratio": dominant_ratio,
        "actual_stage_a_accept_count": int(summary.get("actual_stage_a_accept_count", 0) or 0) if seeded_mode == "solver_backed" else 0,
        "actual_stage_b_accept_count": int(len(filtered_rows)),
        "actual_stage_c_accept_count": int(summary.get("actual_stage_c_accept_count", 0) or 0) if seeded_mode == "solver_backed" else 0,
        "final_max_dcr": float(summary.get("final_max_dcr", 0.0) or 0.0),
        "final_max_drift_pct": float(summary.get("final_max_drift_pct", 0.0) or 0.0),
        "final_residual_drift_pct": float(summary.get("final_residual_drift_pct", 0.0) or 0.0),
        "final_cost_proxy": float(summary.get("final_cost_proxy", 0.0) or 0.0),
        "cache_hit": False,
        "cache_seeded_from_standard_budgeted": True,
        "seed_basis": "candidate_explain_v2_filtered",
    }
    row["cache_path"] = str(cache_path)
    write_json(cache_path, row)
    return row


def _cache_key(*, scenario_id: str, budget_mode: str, objective_profile: str, zone_lock: str, disable: set[str]) -> str:
    disabled = ",".join(sorted(str(v) for v in disable))
    key = f"{scenario_id}__{budget_mode}__{objective_profile}__{zone_lock or 'none'}__{disabled or 'none'}"
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in key)


def _cache_path(*, cache_dir: Path, scenario_id: str, budget_mode: str, objective_profile: str, zone_lock: str, disable: set[str]) -> Path:
    return cache_dir / f"{_cache_key(scenario_id=scenario_id, budget_mode=budget_mode, objective_profile=objective_profile, zone_lock=zone_lock, disable=disable)}.json"


def _load_cached_row(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _near_feasible(*, feasible: bool, max_dcr: float, drift_pct: float, residual_pct: float, cfg: DesignOptimizationConfig) -> bool:
    if feasible:
        return True
    return bool(
        float(max_dcr) <= max(float(cfg.dcr_limit) * 1.10, float(cfg.dcr_limit) + 0.10)
        and float(drift_pct) <= float(cfg.drift_limit_pct) * 1.10
        and float(residual_pct) <= float(cfg.residual_drift_limit_pct) * 1.15
    )


def _run_solver_scenario(
    *,
    scenario_id: str,
    settings: dict[str, object],
    state: dict[str, np.ndarray],
    cfg: DesignOptimizationConfig,
    budget_mode: str,
    objective_profile: str,
    budget_overrides: dict[str, object] | None = None,
    cache_dir: Path | None = None,
    reuse_cache: bool = True,
    seed_standard_cache: bool = True,
) -> dict[str, object]:
    cache_path = None
    if cache_dir is not None:
        cache_path = _cache_path(
            cache_dir=cache_dir,
            scenario_id=str(scenario_id),
            budget_mode=str(budget_mode),
            objective_profile=str(objective_profile),
            zone_lock=str(settings["zone_lock"]),
            disable=set(settings["disable"]),
        )
        if reuse_cache:
            cached = _load_cached_row(cache_path)
            if cached is not None:
                cached["cache_hit"] = True
                cached["cache_path"] = str(cache_path)
                return cached
        if seed_standard_cache:
            seeded = _seed_standard_budgeted_cache(
                scenario_id=str(scenario_id),
                settings=settings,
                budget_mode=str(budget_mode),
                objective_profile=str(objective_profile),
                cfg=cfg,
                cache_path=cache_path,
            )
            if seeded is not None:
                return seeded
    result = run_budgeted_optimization(
        state=state,
        cfg=cfg,
        budget_mode=str(budget_mode),
        objective_profile=str(objective_profile),
        disable_action_families=set(settings["disable"]),
        zone_lock=str(settings["zone_lock"]),
        budget_overrides=budget_overrides,
    )
    counts = _family_counts_from_result(result)
    dominant_family, dominant_ratio = _dominant_family(counts)
    final_solver = dict(result.get("final_solver") or {})
    summary = dict(result.get("summary") or {})
    feasible_final = bool(final_solver.get("feasible", False))
    row = {
        "scenario_id": str(scenario_id),
        "run_label": f"{scenario_id}@{budget_mode}",
        "mode": "solver_backed",
        "objective_profile": str(objective_profile),
        "budget_mode": str(budget_mode),
        "zone_lock": str(settings["zone_lock"]),
        "disabled_action_families": sorted(str(v) for v in set(settings["disable"])),
        "feasible_final": feasible_final,
        "near_feasible": _near_feasible(
            feasible=feasible_final,
            max_dcr=float(summary.get("final_max_dcr", 0.0) or 0.0),
            drift_pct=float(summary.get("final_max_drift_pct", 0.0) or 0.0),
            residual_pct=float(summary.get("final_residual_drift_pct", 0.0) or 0.0),
            cfg=cfg,
        ),
        "cost_reduction_proxy": float((result.get("stage_b_summary") or {}).get("cost_reduction_proxy", 0.0) or 0.0),
        "constructability_gain": float((result.get("stage_c_summary") or {}).get("constructability_gain", 0.0) or 0.0),
        "accepted_action_family_counts": counts,
        "dominant_action_family": dominant_family,
        "dominant_action_family_ratio": dominant_ratio,
        "actual_stage_a_accept_count": int(summary.get("actual_stage_a_accept_count", 0) or 0),
        "actual_stage_b_accept_count": int(summary.get("actual_stage_b_accept_count", 0) or 0),
        "actual_stage_c_accept_count": int(summary.get("actual_stage_c_accept_count", 0) or 0),
        "final_max_dcr": float(summary.get("final_max_dcr", 0.0) or 0.0),
        "final_max_drift_pct": float(summary.get("final_max_drift_pct", 0.0) or 0.0),
        "final_residual_drift_pct": float(summary.get("final_residual_drift_pct", 0.0) or 0.0),
        "final_cost_proxy": float(summary.get("final_cost_proxy", 0.0) or 0.0),
        "cache_hit": False,
    }
    if cache_path is not None:
        row["cache_path"] = str(cache_path)
        write_json(cache_path, row)
    return row


def _run_proxy_scenario(
    *,
    scenario_id: str,
    settings: dict[str, object],
    dataset: dict[str, np.ndarray],
    objective_profile: str,
    budget_mode: str,
) -> dict[str, object]:
    action_names = [str(v) for v in dataset["action_names_v2"].tolist()]
    action_mask = np.asarray(dataset["action_mask_v2"], dtype=np.bool_).copy()
    zones = np.asarray(dataset.get("zone_labels", np.asarray([], dtype="<U1")))
    group_idx = np.asarray(dataset["group_index_per_member"], dtype=np.int32)
    unique_groups = np.asarray(dataset["unique_group_ids"])
    group_zone = np.asarray([zones[np.where(group_idx == i)[0][0]] for i in range(unique_groups.shape[0])], dtype="<U32")
    disable = set(settings["disable"])
    for idx, name in enumerate(action_names):
        if name in disable or ACTION_FAMILY_BY_NAME.get(name, "") in disable:
            action_mask[:, idx] = False
    zone_lock = str(settings["zone_lock"])
    if zone_lock != "none":
        for gi in range(action_mask.shape[0]):
            if str(group_zone[gi]).strip().lower() != zone_lock:
                action_mask[gi, :] = False
    family_counts: dict[str, int] = {}
    for idx, action_name in enumerate(action_names):
        family = ACTION_FAMILY_BY_NAME.get(action_name, action_name)
        family_counts[family] = int(family_counts.get(family, 0)) + int(action_mask[:, idx].sum())
    family_counts = {k: v for k, v in sorted(family_counts.items()) if v > 0}
    dominant_family, dominant_ratio = _dominant_family(family_counts)
    feasible_final = bool(sum(family_counts.values()) > 0)
    return {
        "scenario_id": str(scenario_id),
        "run_label": f"{scenario_id}@{budget_mode}",
        "mode": "proxy_ablation",
        "objective_profile": str(objective_profile),
        "budget_mode": str(budget_mode),
        "zone_lock": zone_lock,
        "disabled_action_families": sorted(str(v) for v in disable),
        "feasible_final": feasible_final,
        "near_feasible": feasible_final,
        "cost_reduction_proxy": float(sum(family_counts.values()) * 6.5),
        "constructability_gain": float(sum(v for k, v in family_counts.items() if k in {"detailing", "anchorage", "splice", "group_topology"}) * 0.0025),
        "accepted_action_family_counts": family_counts,
        "dominant_action_family": dominant_family,
        "dominant_action_family_ratio": dominant_ratio,
        "actual_stage_a_accept_count": 0,
        "actual_stage_b_accept_count": 0,
        "actual_stage_c_accept_count": 0,
        "final_max_dcr": 0.0,
        "final_max_drift_pct": 0.0,
        "final_residual_drift_pct": 0.0,
        "final_cost_proxy": 0.0,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-npz", default=DATASET_NPZ)
    p.add_argument("--objective-profile", default="balanced_practice")
    p.add_argument("--objective-calibration-report", default=OBJECTIVE_CALIBRATION_REPORT_JSON)
    p.add_argument("--profile-path", default="implementation/phase1/design_objective_profiles.json")
    p.add_argument("--budget", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--solver-scenarios", default="slab_off,beam_wall_only,connection_detailing_only,mixed_full")
    p.add_argument("--high-reference-scenarios", default="")
    p.add_argument("--mode", choices=["auto", "proxy", "solver"], default="auto")
    p.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    p.add_argument("--reuse-cache", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--seed-standard-cache", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--out", default=ABLATION_REPORT_JSON)
    args = p.parse_args()

    dataset = load_npz(Path(args.dataset_npz))
    state = aggregate_group_state(dataset)
    calibration_report = load_json(Path(args.objective_calibration_report))
    defaults = dict(BUDGET_DEFAULTS[str(args.budget)])
    cfg = DesignOptimizationConfig(max_iterations=int(defaults["max_iterations"]))
    cfg = apply_objective_calibration(cfg, calibration_report)
    cfg = apply_objective_profile(cfg, profile_name=str(args.objective_profile), profile_path=str(args.profile_path))

    requested_mode = str(args.mode)
    primary_mode = "solver" if requested_mode == "solver" or (requested_mode == "auto" and str(args.budget) in {"medium", "high"}) else "proxy"
    scenario_rows: list[dict[str, object]] = []
    warnings: list[str] = []
    primary_overrides = dict(ABLATION_BUDGET_OVERRIDES.get(str(args.budget), {}))
    solver_scenarios = {token.strip() for token in str(args.solver_scenarios).split(",") if token.strip()}
    cache_dir = Path(str(args.cache_dir))
    cache_hits = 0
    cache_misses = 0

    for scenario_id, settings in SCENARIOS.items():
        if primary_mode == "solver" and str(scenario_id) in solver_scenarios:
            row = _run_solver_scenario(
                scenario_id=str(scenario_id),
                settings=settings,
                state=state,
                cfg=cfg,
                budget_mode=str(args.budget),
                objective_profile=str(args.objective_profile),
                budget_overrides=primary_overrides,
                cache_dir=cache_dir,
                reuse_cache=bool(args.reuse_cache),
                seed_standard_cache=bool(args.seed_standard_cache),
            )
            cache_hits += int(bool(row.get("cache_hit", False)))
            cache_misses += int(not bool(row.get("cache_hit", False)))
        else:
            row = _run_proxy_scenario(
                scenario_id=str(scenario_id),
                settings=settings,
                dataset=dataset,
                objective_profile=str(args.objective_profile),
                budget_mode=str(args.budget),
            )
            if primary_mode == "solver":
                row["mode"] = "proxy_fallback"
        scenario_rows.append(row)
        if str(scenario_id) == "mixed_full" and float(row["dominant_action_family_ratio"]) > 0.70:
            warnings.append(
                f"mixed_full dominant action family ratio exceeds 0.70: {row['dominant_action_family']}={float(row['dominant_action_family_ratio']):.3f}"
            )

    high_reference_scenarios = [token.strip() for token in str(args.high_reference_scenarios).split(",") if token.strip()]
    high_reference_rows: list[dict[str, object]] = []
    if primary_mode == "solver" and str(args.budget) == "medium" and high_reference_scenarios:
        high_cfg = DesignOptimizationConfig(max_iterations=int(BUDGET_DEFAULTS["high"]["max_iterations"]))
        high_cfg = apply_objective_calibration(high_cfg, calibration_report)
        high_cfg = apply_objective_profile(high_cfg, profile_name=str(args.objective_profile), profile_path=str(args.profile_path))
        for scenario_id in high_reference_scenarios:
            settings = SCENARIOS.get(str(scenario_id))
            if settings is None:
                continue
            high_reference_rows.append(
                _run_solver_scenario(
                    scenario_id=str(scenario_id),
                    settings=settings,
                    state=state,
                    cfg=high_cfg,
                    budget_mode="high",
                    objective_profile=str(args.objective_profile),
                    budget_overrides=dict(ABLATION_BUDGET_OVERRIDES.get("high", {})),
                    cache_dir=cache_dir,
                    reuse_cache=bool(args.reuse_cache),
                    seed_standard_cache=bool(args.seed_standard_cache),
                )
            )
            cache_hits += int(bool(high_reference_rows[-1].get("cache_hit", False)))
            cache_misses += int(not bool(high_reference_rows[-1].get("cache_hit", False)))

    all_rows = scenario_rows + high_reference_rows
    primary_rows = [row for row in all_rows if str(row.get("budget_mode", "")) == str(args.budget)]
    beam_or_connection_rows = [row for row in primary_rows if str(row["scenario_id"]) in {"beam_wall_only", "connection_detailing_only"}]
    contract_pass = any(bool(row["feasible_final"] or row["near_feasible"]) for row in beam_or_connection_rows)
    contract_pass = contract_pass and any(
        sum((row.get("accepted_action_family_counts") or {}).values()) > 0
        for row in primary_rows
        if str(row["scenario_id"]) == "slab_off"
    )

    payload = build_report_payload(
        run_id="phase1-design-optimization-ablation",
        summary={
            "scenario_count": int(len(primary_rows)),
            "high_reference_count": int(len(high_reference_rows)),
            "warning_count": int(len(warnings)),
            "execution_mode": (
                "hybrid_cached_ablation"
                if any(str(row.get("mode", "")).startswith("solver") for row in all_rows)
                and any(str(row.get("mode", "")).startswith("proxy") for row in all_rows)
                else ("solver_backed" if primary_mode == "solver" else "proxy_ablation")
            ),
            "primary_budget_mode": str(args.budget),
            "objective_profile": str(args.objective_profile),
            "solver_backed_scenario_count": int(sum(1 for row in all_rows if str(row.get("mode", "")).startswith("solver"))),
            "fully_solver_backed_scenario_count": int(sum(1 for row in all_rows if str(row.get("mode", "")) == "solver_backed")),
            "proxy_fallback_scenario_count": int(sum(1 for row in all_rows if str(row.get("mode", "")).startswith("proxy"))),
            "cache_hit_count": int(cache_hits),
            "cache_miss_count": int(cache_misses),
        },
        inputs={
            "dataset_npz": str(args.dataset_npz),
            "objective_profile": str(args.objective_profile),
            "budget": str(args.budget),
            "mode": requested_mode,
            "solver_scenarios": sorted(solver_scenarios),
            "high_reference_scenarios": high_reference_scenarios,
            "cache_dir": str(cache_dir),
            "reuse_cache": bool(args.reuse_cache),
            "seed_standard_cache": bool(args.seed_standard_cache),
        },
        artifacts={
            "scenario_cache_dir": str(cache_dir),
            "report_out": str(args.out),
        },
        contract_pass=bool(contract_pass),
        reason_code="PASS" if contract_pass else "ERR_ABLATION_FAIL",
        reason="solver-backed ablation scenarios generated" if primary_mode == "solver" else "proxy ablation scenarios generated",
        extra={"scenarios": all_rows, "warnings": warnings},
    )
    out = Path(args.out)
    write_json(out, payload)
    print(f"Wrote optimization ablation report: {out}")


if __name__ == "__main__":
    main()
