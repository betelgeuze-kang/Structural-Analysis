"""Candidate-pool cost optimality from separately verified complete comparisons.

This is a comparison of the declared material estimates, including the baseline,
not a quote, global design optimum, or a measure of learned speedup.
"""

import math


def verified_limit_outcome(plan, row):
    requested = set(plan["history_limits"]) | set(plan["material_limits"])
    requested.update("terminal_" + k for k in (plan["terminal_limits"] or {}))
    screens = row.get("screens")
    if (
        row.get("full_reference_verification_pass") is not True
        or type(screens) is not dict
        or not screens
        or set(screens) != requested
        or any(
            type(s) is not dict or s.get("status") not in ("pass", "fail")
            for s in screens.values()
        )
    ):
        return None
    return all(s["status"] == "pass" for s in screens.values())


def candidate_cost_optimality_audit(plan, comparisons):
    """Require every oracle result before identifying a finite-pool minimum.

    Unknown outcomes remain unknown even when their declared prices exceed the
    best known feasible price. Both online comparisons retain their own selected
    result; a contradictory later oracle does not silently replace it.
    """
    pool = {row["candidate_id"]: row for row in plan["pool"]}
    if len(pool) != len(plan["pool"]) or "baseline" not in pool:
        raise ValueError("cost audit requires a unique pool including baseline")
    estimates = {}
    common = None
    for candidate_id, row in pool.items():
        estimate = row["material_estimate"]
        value = estimate["total"]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("finite nonnegative common-price estimates required")
        identity = (
            estimate["currency"],
            estimate["scope"],
            estimate["price_table_hash"],
        )
        if estimate["price_table_hash"] != plan["price_table_hash"]:
            raise ValueError("cost audit price table differs from frozen plan")
        if common is not None and identity != common:
            raise ValueError("cost audit requires one currency and quantity scope")
        common = identity
        estimates[candidate_id] = value
    assert common is not None  # The pool contains the baseline.

    oracle = comparisons.get("exhaustive_oracle")
    outcomes = {candidate_id: None for candidate_id in pool}
    for name, report in comparisons.items():
        expected = (
            set(pool)
            if name == "exhaustive_oracle"
            else {"baseline", *plan["plans"][name]["shortlist"]}
        )
        ids = [r["candidate_id"] for r in report["rows"]]
        if len(ids) != len(expected) or set(ids) != expected:
            raise ValueError("cost audit comparison must retain its complete pool")
        if report["price_table_hash"] != plan["price_table_hash"]:
            raise ValueError("cost audit comparison price table mismatch")
        for row in report["rows"]:
            if (
                row.get("material_estimate") is not None
                and row["material_estimate"]
                != pool[row["candidate_id"]]["material_estimate"]
            ):
                raise ValueError("cost audit comparison estimate mismatch")
        if name == "exhaustive_oracle":
            outcomes = {
                r["candidate_id"]: verified_limit_outcome(plan, r)
                for r in report["rows"]
            }
    unknown = [candidate_id for candidate_id in pool if outcomes[candidate_id] is None]
    feasible = [candidate_id for candidate_id in pool if outcomes[candidate_id] is True]
    status = (
        "oracle_not_run"
        if oracle is None
        else "oracle_incomplete"
        if unknown
        else "no_feasible_candidate"
        if not feasible
        else "complete"
    )
    minimum = min(estimates[c] for c in feasible) if status == "complete" else None
    winners = (
        sorted(c for c in feasible if estimates[c] == minimum)
        if minimum is not None
        else None
    )
    arms = {}
    for name in plan["plans"]:
        comparison = comparisons[name]
        selected_id = comparison["selected_candidate_id"]
        selected = next(
            (r for r in comparison["rows"] if r["candidate_id"] == selected_id), None
        )
        if selected_id is not None and (
            selected is None
            or verified_limit_outcome(plan, selected) is not True
            or selected.get("material_estimate") is None
        ):
            raise ValueError(
                "cost audit selection needs full reference and requested limits"
            )
        selected_estimate = estimates[selected_id] if selected_id is not None else None
        arm_status = status
        if status == "complete":
            arm_status = (
                "no_verified_selection"
                if selected_id is None
                else "selection_not_confirmed_by_oracle"
                if outcomes[selected_id] is not True
                else "compared"
            )
        gap = None
        if arm_status == "compared":
            assert selected_estimate is not None and minimum is not None
            gap = selected_estimate - minimum
        requested = {"baseline", *plan["plans"][name]["shortlist"]}
        missed = (
            [
                c
                for c in pool
                if c not in requested
                and outcomes[c] is True
                and estimates[c] < selected_estimate
            ]
            if arm_status == "compared"
            else None
        )
        arms[name] = {
            "status": arm_status,
            "selected_candidate_id": selected_id,
            "selected_estimate": selected_estimate,
            "selected_minus_pool_minimum_estimate": gap,
            "matches_pool_minimum": None if gap is None else gap == 0,
            "missed_cheaper_feasible_count": None if missed is None else len(missed),
            "missed_cheaper_feasible_candidate_ids": missed,
        }
    return {
        "schema_version": "rc-control-candidate-cost-optimality.v1",
        "status": status,
        "candidate_denominator": len(pool),
        "baseline_included": True,
        "price_table_hash": plan["price_table_hash"],
        "currency": common[0],
        "quantity_scope": common[1],
        "oracle_comparison_hash": None if oracle is None else oracle["report_hash"],
        "oracle_unverifiable_candidate_ids": None if oracle is None else unknown,
        "pool_minimum_feasible_estimate": minimum,
        "pool_minimum_feasible_candidate_ids": winners,
        "arms": arms,
        "global_design_optimality_proved": False,
        "confirmed_currency_savings": False,
        "independent_physical_validation": False,
    }
