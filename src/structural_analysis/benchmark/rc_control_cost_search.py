"""Local single-strategy search with a finite-pool cost certificate.

A verified incumbent and verified failure of *every strictly cheaper* model are
sufficient for a pool price minimum, not complete response coverage or global
optimality. Numerical failure/unknown work is never a verified limit failure.
The old exhaustive strategy-comparison contract is deliberately unchanged.
"""

from __future__ import annotations

from dataclasses import asdict
from collections.abc import Callable
import math
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_cost import (
    verified_limit_outcome,
)
from structural_analysis.benchmark.rc_control_reuse import (
    NewAnalysisRequired,
    RCControlResultSession,
    _inputs,
)


def finite_pool_cost_bound(pool: list[dict], outcomes: dict[str, bool | None]) -> dict:
    """Pure arithmetic certificate; caller must obtain outcomes from verified physics.

    This helper does not authenticate arbitrary receipts or authorize designs.
    Unknown expensive candidates do not hide response gaps, but cannot beat an
    incumbent under the same already-computed material-price objective.
    """
    if type(pool) is not list or not 1 <= len(pool) <= 17:
        raise ValueError("one to seventeen finite-pool rows required")
    costs: dict[str, float] = {}
    common = None
    for row in pool:
        if type(row) is not dict or set(row) != {"candidate_id", "material_estimate"}:
            raise ValueError("typed candidate price row required")
        name = row["candidate_id"]
        design._identifier(name, "candidate_id")
        if name in costs:
            raise ValueError("duplicate pool candidate")
        estimate = row["material_estimate"]
        if type(estimate) is not dict:
            raise ValueError("explicit material estimate required")
        value = estimate.get("total")
        if (
            type(value) not in (int, float)
            or (type(value) is int and abs(value) > 2**53 - 1)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("finite nonnegative price required")
        identity = tuple(
            estimate.get(key) for key in ("currency", "scope", "price_table_hash")
        )
        if any(type(v) is not str or not v for v in identity):
            raise ValueError("explicit common currency/scope/price identity required")
        if common is not None and identity != common:
            raise ValueError("incompatible cost bases")
        common = identity
        costs[name] = value
    if (
        "baseline" not in costs
        or type(outcomes) is not dict
        or set(outcomes) != set(costs)
        or any(v is not None and type(v) is not bool for v in outcomes.values())
    ):
        raise ValueError(
            "complete unique pool and strict three-state outcomes required"
        )
    feasible = [name for name, value in outcomes.items() if value is True]
    unknown = sorted(name for name, value in outcomes.items() if value is None)
    selected = min(feasible, key=lambda name: (costs[name], name)) if feasible else None
    cheaper_unknown = (
        None
        if selected is None
        else [name for name in unknown if costs[name] < costs[selected]]
    )
    confirmed = selected is not None and not cheaper_unknown
    status = (
        "pool_minimum_confirmed"
        if confirmed
        else "cheaper_outcomes_unknown"
        if selected is not None
        else "no_verified_selection"
        if unknown
        else "no_feasible_candidate"
    )
    assert common is not None
    return {
        "schema_version": "local-rc-finite-pool-cost-bound.v1",
        "status": status,
        "baseline_included": True,
        "candidate_denominator": len(costs),
        "currency": common[0],
        "quantity_scope": common[1],
        "price_table_hash": common[2],
        "selected_candidate_id": selected,
        "selected_estimate": None if selected is None else costs[selected],
        "pool_minimum_feasible_estimate": costs[selected] if confirmed else None,
        "selected_minus_pool_minimum_estimate": 0 if confirmed else None,
        "strictly_cheaper_unverified_candidate_ids": cheaper_unknown,
        "unverified_response_candidate_ids": unknown,
        "response_coverage_complete": not unknown,
        "all_minimum_cost_ties_verified": None
        if not confirmed
        else not any(costs[name] == costs[selected] for name in unknown),
        "global_design_optimality_proved": False,
        "independent_physical_validation": False,
        "confirmed_currency_savings": False,
        "basis": "verified_incumbent_and_no_strictly_cheaper_unknown_or_feasible_outcome",
    }


def run_rc_control_cost_search(
    baseline,
    candidates,
    request,
    *,
    session: RCControlResultSession,
    scope_id: str,
    prices: design.FiberFrameMaterialPrices,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    output_directory: Path,
    max_new_model_analyses: int = 17,
    candidate_order: tuple[str, ...] | None = None,
    terminal_limits: design.FiberFrameTerminalLimits | None = None,
    maximum_wall_seconds: float | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run one predeclared order, with bounded new verified-model evaluations.

    The baseline is scheduled first. Prices and physical quantities for the
    entire pool are fixed before numerical work. Optional ordering may come
    from a separately frozen predictor; no prediction excludes a cheap model.
    Each cache miss reserves one original analysis AND its full fresh replay.
    A cache hit consumes no new-model budget and is not independent evidence.
    No exhaustive oracle or second strategy is run by this local-use function.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
    if maximum_wall_seconds is not None and (
        type(maximum_wall_seconds) not in (int, float)
        or not math.isfinite(maximum_wall_seconds)
        or not 0 < maximum_wall_seconds <= 86400
    ):
        raise ValueError("wall budget must be finite in (0, 86400]")
    if stop_requested is not None and not callable(stop_requested):
        raise ValueError("stop request must be a callable")
    stopped = None
    if type(session) is not RCControlResultSession:
        raise ValueError("exact process-local result session required")
    if type(max_new_model_analyses) is not int or not 0 <= max_new_model_analyses <= 17:
        raise ValueError("new-model budget must be an integer in [0, 17]")
    if type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("common explicit prices required")
    baseline, request, history_limits, material_limits, terminal_limits, prices = (
        _inputs(
            baseline, request, history_limits, material_limits, terminal_limits, prices
        )
    )
    if type(candidates) is not tuple or not 1 <= len(candidates) <= 16:
        raise ValueError("one to sixteen typed alternatives required")
    if any(type(c) is not design.FiberFrameDesignCandidate for c in candidates):
        raise ValueError("exact design candidates required")
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            c.candidate_id,
            tuple(
                design.FiberFrameSectionChange(**asdict(change)) for change in c.changes
            ),
        )
        for c in candidates
    )
    ids = [c.candidate_id for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("unique alternative IDs required")
    if candidate_order is not None and (
        type(candidate_order) is not tuple
        or len(candidate_order) != len(ids)
        or any(type(n) is not str for n in candidate_order)
        or set(candidate_order) != set(ids)
    ):
        raise ValueError("candidate_order must be a complete unique permutation")
    # Preflight every candidate; no invalid quantities are assigned a zero cost.
    models = {"baseline": baseline}
    models.update(
        {
            c.candidate_id: design.apply_fiber_frame_section_changes(baseline, c)
            for c in candidates
        }
    )
    quantities = {
        name: design.calculate_fiber_frame_member_quantities(model)
        for name, model in models.items()
    }
    pool = [
        {
            "candidate_id": name,
            "material_estimate": design._estimate(quantities[name], prices),
        }
        for name in models
    ]
    outcomes: dict[str, bool | None] = {name: None for name in models}
    finite_pool_cost_bound(
        pool, outcomes
    )  # Validates finite comparable prices before output.
    costs = {row["candidate_id"]: row["material_estimate"]["total"] for row in pool}
    order = [
        "baseline",
        *(
            candidate_order
            if candidate_order is not None
            else sorted(ids, key=lambda name: (costs[name], name))
        ),
    ]
    session._check_context(scope_id)
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    plan = {
        "schema_version": "local-rc-cost-search-plan.v1",
        "source_revision": session.source_revision,
        "source_revision_is_attestation": False,
        "scope_id": scope_id,
        "baseline_checksum": baseline.canonical_model_checksum,
        "candidates": [asdict(c) for c in candidates],
        "request": request.to_dict(),
        "history_limits": asdict(history_limits),
        "material_limits": asdict(material_limits),
        "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
        "prices": asdict(prices),
        "price_table_hash": prices.price_table_hash,
        "pool": pool,
        "evaluation_order": order,
        "max_new_model_analyses": max_new_model_analyses,
        "maximum_wall_seconds": maximum_wall_seconds,
        "cancellation_enabled": stop_requested is not None,
        "wall_budget_scope": "cooperative_between_models_not_a_solver_timeout",
        "budget_scope": "new_model_evaluations_including_baseline_each_with_original_analysis_and_fresh_replay",
        "model_checksums": {
            name: model.canonical_model_checksum for name, model in models.items()
        },
    }
    plan["plan_hash"] = study._sha(study._bytes(plan))
    study._save(root, "plan.json", study._bytes(plan))
    used, hits, unknown_work_stop = 0, 0, False
    records = []
    aggregate = {
        key: 0
        for key in (
            "attempted_step_count",
            "known_linear_solve_count",
            "known_newton_iteration_count",
            "unknown_solver_work_attempt_count",
        )
    }
    invocations = 0
    for name in order:
        record: dict[str, Any] = {
            "candidate_id": name,
            "status": "not_evaluated",
            "verified_limit_outcome": None,
            "evaluation": None,
        }
        records.append(record)
        if stopped is None and stop_requested is not None:
            requested = stop_requested()
            if type(requested) is not bool:
                raise ValueError("stop request must return an actual boolean")
            if requested:
                stopped = "cancelled_between_models"
        if stopped is None and maximum_wall_seconds is not None:
            if perf_counter_ns() - wall >= maximum_wall_seconds * 1e9:
                stopped = "wall_budget_exhausted_between_models"
        if stopped is not None:
            record["status"] = "not_run_after_cooperative_stop"
            continue
        bound = finite_pool_cost_bound(pool, outcomes)
        selected_cost = bound["selected_estimate"]
        if (
            name != "baseline"
            and selected_cost is not None
            and costs[name] >= selected_cost
        ):
            record["status"] = "not_needed_for_strict_price_improvement"
            continue
        if unknown_work_stop:
            record["status"] = "not_run_after_unknown_numerical_work"
            continue
        try:
            evaluation = session.evaluate(
                models[name],
                request,
                scope_id=scope_id,
                output_directory=root / name,
                prices=prices,
                history_limits=history_limits,
                material_limits=material_limits,
                terminal_limits=terminal_limits,
                allow_new_analysis=used < max_new_model_analyses,
            )
        except NewAnalysisRequired:
            record["status"] = "new_analysis_budget_exhausted"
            continue  # A later cheaper candidate may already exist in the session.
        fresh = evaluation["mode"] == "fresh_reference_and_replay"
        used += int(fresh)
        hits += int(not fresh)
        row = evaluation["row"]
        if (
            row["material_estimate"]
            != next(r["material_estimate"] for r in pool if r["candidate_id"] == name)
            or row["quantities"] != quantities[name]
            or evaluation["model_checksum"] != models[name].canonical_model_checksum
            or evaluation["request"] != request.to_dict()
        ):
            raise ValueError(
                "evaluated model/quantity/price/request differs from the frozen pool"
            )
        work = evaluation["new_work"]
        # An uncounted execution cannot become a price-bound incumbent even
        # when its response/verification fields otherwise look successful.
        outcomes[name] = (
            None if work["unknown_work"] else verified_limit_outcome(plan, row)
        )
        record.update(
            status="evaluated",
            verified_limit_outcome=outcomes[name],
            evaluation={
                "path": f"{name}/evaluation.json",
                "report_hash": evaluation["report_hash"],
                "mode": evaluation["mode"],
                "physics_key": evaluation["physics_key"],
            },
        )
        invocations += work["api_invocation_count"]
        unknown_work_stop = work["unknown_work"]
        for key, value in work["known_counters"].items():
            aggregate[key] += value
    bound = finite_pool_cost_bound(pool, outcomes)
    report = {
        "schema_version": "local-rc-cost-search-result.v1",
        "plan_hash": plan["plan_hash"],
        "status": "unknown_work_stop" if unknown_work_stop else (stopped or bound["status"]),
        "evaluation_order": order,
        "records": records,
        "outcomes": outcomes,
        "cost_bound": bound,
        "new_model_evaluations": used,
        "reused_model_evaluations": hits,
        "new_work": {
            "known_counters": aggregate,
            "unknown_work": unknown_work_stop,
            "api_invocation_count": invocations,
        },
        "total_wall_ns": perf_counter_ns() - wall,
        "total_process_cpu_ns": process_time_ns() - cpu,
        "timing_scope": "one_local_search_including_preflight_original_exports_and_reuse_excluding_final_report_write",
        "claims": {
            "global_design_optimality_proved": False,
            "confirmed_currency_savings": False,
            "independent_physical_validation": False,
            "design_authority": False,
            "performance_improvement": False,
            "exhaustive_oracle_executed": False,
            "strategy_comparison_executed": False,
            "release_approved": False,
        },
    }
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "search.json", study._bytes(report))
    return report
