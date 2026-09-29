"""Candidate-pool cost optimality from separately verified complete comparisons.

This is a comparison of the declared material estimates, including the baseline,
not a quote, global design optimum, or a measure of learned speedup.
"""

import math


COST_AUDIT_V1 = "rc-control-candidate-cost-optimality.v1"
COST_AUDIT_V2 = "rc-control-candidate-cost-optimality.v2"
COST_AUDIT_V3 = "rc-control-candidate-cost-optimality.v3"
FORCE_FLOOR_PLAN = "experimental-rc-control-force-floor-price-search-plan.v1"
FORCE_FLOOR_COMPARISON = "experimental-rc-control-design-comparison.v2"


def _force_floor_screen_matches(floor, screen):
    """Keep a reported signed response from being certified by a forged status."""
    if type(screen) is not dict or set(screen) != {
        "value", "limit", "status", "comparison"
    }:
        return False
    value = screen["value"]
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and type(screen["limit"]) in (int, float)
        and type(screen["limit"]) is type(floor["minimum_load_factor"])
        and math.isfinite(screen["limit"])
        and screen["limit"] == floor["minimum_load_factor"]
        and screen["comparison"] == "at_least"
        and screen["status"] == (
            "pass" if value >= floor["minimum_load_factor"] else "fail"
        )
    )


def verified_limit_outcome(plan, row):
    requested = set(plan["history_limits"]) | set(plan["material_limits"])
    requested.update("terminal_" + k for k in (plan["terminal_limits"] or {}))
    floor = None
    if plan.get("schema_version") == FORCE_FLOOR_PLAN:
        floor = plan.get("force_response_floor")
        if type(floor) is not dict or "minimum_load_factor" not in floor:
            return None
        requested.add("load_factor_at_target")
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
    if floor is not None and not _force_floor_screen_matches(
        floor, screens["load_factor_at_target"]
    ):
        return None
    return all(s["status"] == "pass" for s in screens.values())


def candidate_cost_optimality_audit(
    plan, comparisons, *, schema_version=None
):
    """Require every oracle result before identifying a finite-pool minimum.

    Unknown outcomes remain unknown even when their declared prices exceed the
    best known feasible price. Both online comparisons retain their own selected
    result; a contradictory later oracle does not silently replace it.
    V2 also intersects missed cheaper feasible alternatives with predicted
    limit failures for the learned arm; abstentions never count as failures.
    V3 carries the force floor identity and treats a missing or internally
    inconsistent signed response screen as unverifiable.
    """
    floor_plan = plan.get("schema_version") == FORCE_FLOOR_PLAN
    if schema_version is None:
        schema_version = COST_AUDIT_V3 if floor_plan else COST_AUDIT_V2
    if schema_version not in (COST_AUDIT_V1, COST_AUDIT_V2, COST_AUDIT_V3):
        raise ValueError("unsupported cost audit schema version")
    if floor_plan != (schema_version == COST_AUDIT_V3):
        raise ValueError("force floor plan requires cost audit v3")
    floor = None
    if floor_plan:
        floor = plan.get("force_response_floor")
        if (
            type(floor) is not dict
            or set(floor) != {
                "target_index", "target_control_displacement_m", "minimum_load_factor"
            }
            or type(floor["target_index"]) is not int
            or floor["target_index"] < 0
            or type(floor["target_control_displacement_m"]) not in (int, float)
            or not math.isfinite(floor["target_control_displacement_m"])
            or type(floor["minimum_load_factor"]) not in (int, float)
            or not math.isfinite(floor["minimum_load_factor"])
            or floor["minimum_load_factor"] <= 0
        ):
            raise ValueError("cost audit needs a finite force floor identity")
        if (
            type(plan.get("control_request")) is not dict
            or type(plan.get("baseline_checksum")) is not str
            or type(plan.get("source_revision")) is not str
        ):
            raise ValueError("cost audit needs frozen force floor source identity")
    pool = {row["candidate_id"]: row for row in plan["pool"]}
    if len(pool) != len(plan["pool"]) or "baseline" not in pool:
        raise ValueError("cost audit requires a unique pool including baseline")
    predicted_failures = set()
    if (
        schema_version in (COST_AUDIT_V2, COST_AUDIT_V3)
        and "learned_order" in plan["plans"]
    ):
        predictions = plan["predictions"]
        ids = [row["candidate_id"] for row in predictions]
        if len(ids) != len(pool) - 1 or set(ids) != set(pool) - {"baseline"}:
            raise ValueError("cost audit needs one prediction per alternative")
        requested_screens = set(plan["history_limits"]) | set(plan["material_limits"])
        requested_screens.update(
            "terminal_" + key for key in (plan["terminal_limits"] or {})
        )
        if floor_plan:
            requested_screens.add("load_factor_at_target")
        for row in predictions:
            prediction = row["prediction"]
            screens = row["predicted_screens"]
            if type(prediction.get("abstained")) is not bool:
                raise ValueError("cost audit needs explicit prediction abstention")
            if prediction["abstained"]:
                if screens is not None:
                    raise ValueError("abstained prediction cannot have screens")
            elif (
                type(screens) is not dict
                or set(screens) != requested_screens
                or any(
                    type(screen) is not dict
                    or screen.get("status") not in ("pass", "fail")
                    for screen in screens.values()
                )
            ):
                raise ValueError("cost audit needs complete prediction screens")
            elif any(screen["status"] == "fail" for screen in screens.values()):
                predicted_failures.add(row["candidate_id"])
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
        if floor_plan:
            if (
                report.get("schema_version") != FORCE_FLOOR_COMPARISON
                or report.get("control_request") != plan["control_request"]
                or report.get("baseline_checksum") != plan["baseline_checksum"]
                or report.get("source_revision") != plan["source_revision"]
            ):
                raise ValueError("cost audit comparison force floor source mismatch")
            report_floor = report.get("force_response_floor")
            if (
                type(report_floor) is not dict
                or set(report_floor) != set(floor)
                or any(
                    type(report_floor[key]) is not type(value)
                    or report_floor[key] != value
                    for key, value in floor.items()
                )
            ):
                raise ValueError("cost audit comparison force floor mismatch")
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
        arm = {
            "status": arm_status,
            "selected_candidate_id": selected_id,
            "selected_estimate": selected_estimate,
            "selected_minus_pool_minimum_estimate": gap,
            "matches_pool_minimum": None if gap is None else gap == 0,
            "missed_cheaper_feasible_count": None if missed is None else len(missed),
            "missed_cheaper_feasible_candidate_ids": missed,
        }
        if schema_version in (COST_AUDIT_V2, COST_AUDIT_V3):
            false_negative_missed = (
                [
                    candidate_id
                    for candidate_id in missed
                    if candidate_id in predicted_failures
                ]
                if missed is not None and name == "learned_order"
                else None
            )
            arm["missed_cheaper_false_negative_count"] = (
                None if false_negative_missed is None else len(false_negative_missed)
            )
            arm["missed_cheaper_false_negative_candidate_ids"] = false_negative_missed
        arms[name] = arm
    audit = {
        "schema_version": schema_version,
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
    if floor is not None:
        audit["force_response_floor"] = floor.copy()
    return audit
