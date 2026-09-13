"""Frozen candidate scheduling from predictions, never from oracle results."""

LEGACY_RANKING = "feasibility_then_price.v1"
CHEAPER_BOUNDARY_RANKING = "feasibility_then_cheaper_boundary.v1"
RANKING_STRATEGIES = (LEGACY_RANKING, CHEAPER_BOUNDARY_RANKING)


def candidate_ranking(predicted, strategy):
    """Keep one predicted feasible seed, then challenge its declared price.

    The bounded relative exceedance is a heuristic distance, not uncertainty.
    An abstention has no distance: cheaper unknowns get explicit exploratory
    priority. No seed means the original tier/price order remains in force.
    """
    if type(strategy) is not str or strategy not in RANKING_STRATEGIES:
        raise ValueError("supported candidate ranking strategy required")

    def price(row):
        return row["estimate"], row["candidate_id"]

    legacy = sorted(predicted, key=lambda row: (row["ranking_tier"], *price(row)))
    if strategy == LEGACY_RANKING:
        return [r["candidate_id"] for r in legacy], None
    scores = {
        r["candidate_id"]: None
        if r["predicted_screens"] is None
        else max(
            (s["value"] - s["limit"]) / s["value"] if s["value"] > s["limit"] else 0.0
            for s in r["predicted_screens"].values()
        )
        for r in predicted
    }
    seed = next((r for r in legacy if r["ranking_tier"] == 0), None)
    challengers = (
        []
        if seed is None
        else sorted(
            [r for r in legacy if r["estimate"] < seed["estimate"]],
            key=lambda r: (
                0 if scores[r["candidate_id"]] is None else 1,
                scores[r["candidate_id"]] or 0.0,
                *price(r),
            ),
        )
    )
    front = ([] if seed is None else [seed]) + challengers
    front_ids = {r["candidate_id"] for r in front}
    ordering = front + [r for r in legacy if r["candidate_id"] not in front_ids]
    challenger_ids = {r["candidate_id"] for r in challengers}
    return [r["candidate_id"] for r in ordering], {
        "strategy": strategy,
        "predicted_feasible_seed_id": None if seed is None else seed["candidate_id"],
        "fallback_reason": "no_predicted_feasible_seed" if seed is None else None,
        "uncertainty_calibrated": False,
        "physical_result_authority": False,
        "rows": [
            {
                "candidate_id": r["candidate_id"],
                "relative_exceedance": scores[r["candidate_id"]],
                "role": "predicted_feasible_seed"
                if seed is not None and r["candidate_id"] == seed["candidate_id"]
                else "cheaper_unpredicted"
                if r["candidate_id"] in challenger_ids
                and scores[r["candidate_id"]] is None
                else "cheaper_predicted_boundary"
                if r["candidate_id"] in challenger_ids
                else "remaining_legacy_order",
            }
            for r in predicted
        ],
    }
