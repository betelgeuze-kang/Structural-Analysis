"""Read-only finite-pool cost audit for a validated fiber-frame search report.

The later oracle uses the same reference solver. This audit compares declared
material estimates within that pool; it does not establish a global optimum,
an independent physical validation, or construction savings.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from structural_analysis.benchmark.fiber_frame_design import (
    QUANTITY_SCOPE,
    FiberFrameMaterialPrices,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _ids(rows: Any, label: str) -> list[str]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} must be a list")
    ids = []
    for row in rows:
        key = _object(row, label).get("candidate_id")
        if type(key) is not str or not key:
            raise ValueError(f"{label} has an invalid candidate ID")
        ids.append(key)
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} has duplicate candidate IDs")
    return ids


def _amount(value: Any, label: str) -> int | float:
    if type(value) not in (int, float) or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{label} must be finite and nonnegative")
    return value


def _outcome(row: Mapping[str, Any], *, history: bool, material: bool) -> bool | None:
    if row.get("analysis_requested") is not True:
        return None
    checks = [("full_reference_verification_pass", "terminal_limit_status")]
    if history:
        checks.append(("full_history_verification_pass", "history_limit_status"))
    if material:
        checks.append(
            ("full_material_history_verification_pass", "material_history_limit_status")
        )
    for verification, status in checks:
        if row.get(verification) is not True or row.get(status) not in ("pass", "fail"):
            return None
    return all(row[status] == "pass" for _, status in checks)


def audit_fiber_frame_candidate_pool_cost(report: Mapping[str, Any]) -> dict[str, Any]:
    """Derive a cost audit without changing or re-running a validated v2-v5 report.

    The caller must first validate the search report and its original physical
    artifacts. This function also rejects cost-basis and selection contradictions.
    Any unknown oracle outcome, even for an expensive candidate, leaves the
    finite-pool minimum and dependent arm metrics unavailable.
    """
    report = _object(report, "comparison report")
    source_hash = report.get("report_hash")
    if source_hash != canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    ):
        raise ValueError("cost audit source report hash mismatch")
    version = report.get("schema_version")
    if version not in {
        f"fiber-frame-candidate-search-comparison.v{n}" for n in range(2, 6)
    }:
        raise ValueError("unsupported fiber-frame comparison schema")
    history = "history_limits" in report
    material = "material_history_limits" in report
    stopping = "stop_mode" in report
    if (
        (
            version == "fiber-frame-candidate-search-comparison.v2"
            and (history or material or stopping)
        )
        or (
            version == "fiber-frame-candidate-search-comparison.v3"
            and (not history or material or stopping)
        )
        or (
            version == "fiber-frame-candidate-search-comparison.v4"
            and (not history or not material or stopping)
        )
        or (version == "fiber-frame-candidate-search-comparison.v5" and not stopping)
        or (material and not history)
        or (stopping and report["stop_mode"] != "first_verified_feasible")
    ):
        raise ValueError("fiber-frame comparison scope does not match its schema")
    basis = _object(report.get("price_basis"), "price basis")
    currency, price_hash = basis.get("currency"), basis.get("price_table_hash")
    price_keys = {
        "concrete_per_m3",
        "rebar_per_kg",
        "currency",
        "as_of",
        "source",
    }
    if set(basis) != price_keys | {"price_table_hash"}:
        raise ValueError("cost audit price basis fields mismatch")
    prices = FiberFrameMaterialPrices(**{key: basis[key] for key in price_keys})
    if type(price_hash) is not str or price_hash != prices.price_table_hash:
        raise ValueError("cost audit price table hash differs from declared prices")

    pool = report.get("candidate_pool")
    pool_ids = _ids(pool, "candidate pool")
    if not pool_ids or "baseline" in pool_ids:
        raise ValueError("cost audit requires alternatives distinct from baseline")
    totals: dict[str, int | float] = {}

    def remember(candidate_id: str, value: Any, label: str) -> int | float:
        total = _amount(value, label)
        if candidate_id in totals and totals[candidate_id] != total:
            raise ValueError("cost audit candidate estimates disagree")
        totals[candidate_id] = total
        return total

    def estimate(row: Mapping[str, Any], label: str) -> int | float | None:
        value = row.get("material_estimate")
        if value is None:
            return None
        value = _object(value, label)
        if (
            value.get("price_table_hash") != price_hash
            or value.get("currency") != currency
            or value.get("scope") != QUANTITY_SCOPE
        ):
            raise ValueError("cost audit estimate price basis mismatch")
        return remember(row["candidate_id"], value.get("total"), label)

    for row in pool:
        key = row["candidate_id"]
        amount = row.get("preanalysis_material_estimate")
        if amount is not None:
            remember(key, amount, "preanalysis material estimate")
        elif row.get("screening_status") == "ready":
            raise ValueError("ready candidate lacks a preanalysis material estimate")

    arms = report.get("arms")
    if (
        not isinstance(arms, list)
        or len(arms) != 2
        or [_object(arm, "online arm").get("strategy") for arm in arms]
        != ["deterministic", "learned"]
    ):
        raise ValueError("cost audit requires both canonical online arms")
    arm_state = {}
    for arm in arms:
        name = arm["strategy"]
        shortlist = arm.get("shortlist")
        if (
            not isinstance(shortlist, list)
            or len(shortlist) != len(set(shortlist))
            or any(type(key) is not str or key not in pool_ids for key in shortlist)
        ):
            raise ValueError("cost audit shortlist differs from the candidate pool")
        attempted = shortlist
        if stopping:
            execution = _object(arm.get("execution"), "stop execution")
            attempted = execution.get("attempted_candidate_ids")
            if (
                not isinstance(attempted, list)
                or attempted != shortlist[: len(attempted)]
            ):
                raise ValueError(
                    "cost audit attempted candidates must be a shortlist prefix"
                )
        baseline = _object(arm.get("baseline"), "online baseline")
        if (
            baseline.get("candidate_id") != "baseline"
            or baseline.get("analysis_requested") is not True
        ):
            raise ValueError("cost audit requires a requested online baseline")
        estimate(baseline, "online baseline estimate")
        outcomes = arm.get("candidate_outcomes")
        if _ids(outcomes, "online candidate outcomes") != pool_ids:
            raise ValueError("cost audit online candidate denominator mismatch")
        by_id = {row["candidate_id"]: row for row in outcomes}
        for key, row in by_id.items():
            if row.get("analysis_requested") is not (key in attempted):
                raise ValueError("cost audit attempted candidate coverage mismatch")
            estimate(row, "online candidate estimate")
        requested = [baseline, *(by_id[key] for key in attempted)]
        eligible = [
            row
            for row in requested
            if _outcome(row, history=history, material=material) is True
            and row.get("material_estimate") is not None
        ]
        expected = None
        if _outcome(baseline, history=history, material=material) is not None:
            if eligible:
                expected = (
                    eligible[0]
                    if stopping
                    else min(
                        eligible,
                        key=lambda row: (
                            totals[row["candidate_id"]],
                            row["candidate_id"],
                        ),
                    )
                )
        selected = arm.get("final_selection")
        if selected != expected:
            raise ValueError("cost audit online selection contradicts requested rows")
        selected_id = None if selected is None else selected["candidate_id"]
        arm_state[name] = (shortlist, attempted, selected_id)

    oracle = _object(report.get("oracle"), "separate oracle")
    executed = oracle.get("executed")
    rows = oracle.get("rows")
    if (
        type(executed) is not bool
        or oracle.get("labels_available_to_online_selection") is not False
        or (executed is False and rows is not None)
    ):
        raise ValueError("cost audit oracle execution declaration mismatch")
    if executed:
        if _ids(rows, "oracle rows") != ["baseline", *pool_ids]:
            raise ValueError("cost audit oracle must cover the full declared pool")
        for row in rows:
            estimate(row, "oracle material estimate")
        oracle_by_id = {row["candidate_id"]: row for row in rows}
        outcomes = {
            key: _outcome(row, history=history, material=material)
            for key, row in oracle_by_id.items()
        }
        unknown = [
            key
            for key in ("baseline", *pool_ids)
            if outcomes[key] is None
            or (
                outcomes[key] is True
                and oracle_by_id[key].get("material_estimate") is None
            )
        ]
        feasible = [key for key in ("baseline", *pool_ids) if outcomes[key] is True]
        status = (
            "oracle_incomplete"
            if unknown
            else "no_feasible_candidate"
            if not feasible
            else "complete"
        )
    else:
        oracle_by_id = {}
        outcomes = {}
        unknown = None
        feasible = []
        status = "oracle_not_run"
    minimum = min(totals[key] for key in feasible) if status == "complete" else None
    winners = (
        sorted(key for key in feasible if totals[key] == minimum)
        if minimum is not None
        else None
    )
    results = {}
    for name, (shortlist, attempted, selected_id) in arm_state.items():
        selected_estimate = totals[selected_id] if selected_id is not None else None
        arm_status = status
        if status == "complete":
            arm_status = (
                "no_verified_selection"
                if selected_id is None
                else "selection_not_confirmed_by_oracle"
                if outcomes[selected_id] is not True
                else "compared"
            )
        gap = selected_estimate - minimum if arm_status == "compared" else None
        if gap is not None and gap < 0:
            raise ValueError("cost audit selected estimate below the oracle minimum")
        missed = (
            [
                key
                for key in pool_ids
                if key not in shortlist
                and outcomes[key] is True
                and totals[key] < selected_estimate
            ]
            if arm_status == "compared"
            else None
        )
        unrequested = (
            [
                key
                for key in pool_ids
                if key not in attempted
                and outcomes[key] is True
                and totals[key] < selected_estimate
            ]
            if arm_status == "compared"
            else None
        )
        results[name] = {
            "status": arm_status,
            "selected_candidate_id": selected_id,
            "selected_estimate": selected_estimate,
            "selected_minus_pool_minimum_estimate": gap,
            "matches_pool_minimum": None if gap is None else gap == 0,
            "missed_cheaper_feasible_candidate_ids": missed,
            "missed_cheaper_feasible_count": None if missed is None else len(missed),
            "unrequested_cheaper_feasible_candidate_ids": unrequested,
            "unrequested_cheaper_feasible_count": None
            if unrequested is None
            else len(unrequested),
        }
    return {
        "schema_version": "fiber-frame-candidate-pool-cost-audit.v1",
        "source_report_hash": source_hash,
        "status": status,
        "candidate_denominator": len(pool_ids) + 1,
        "baseline_included": True,
        "price_table_hash": price_hash,
        "currency": currency,
        "quantity_scope": QUANTITY_SCOPE,
        "oracle_unverifiable_candidate_ids": unknown,
        "pool_minimum_feasible_estimate": minimum,
        "pool_minimum_feasible_candidate_ids": winners,
        "arms": results,
        "missed_cheaper_definition": "oracle_verified_feasible_cheaper_than_selected_outside_planned_shortlist",
        "unrequested_cheaper_definition": "oracle_verified_feasible_cheaper_than_selected_outside_attempted_candidate_prefix",
        "global_design_optimality_proved": False,
        "confirmed_currency_savings": False,
        "independent_physical_validation": False,
    }
