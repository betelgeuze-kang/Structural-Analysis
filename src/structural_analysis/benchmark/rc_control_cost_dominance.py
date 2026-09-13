"""Cost-only scheduling bounds from an already verified layout incumbent.

This helper does not execute, accept, or reject a physical model. Its caller must
retain and validate the original reference artifacts behind the supplied rows.
An expensive unevaluated candidate remains physically unverified.
"""

import math
import re

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_cost import (
    verified_limit_outcome,
)
from structural_analysis.benchmark.rc_control_candidate_search import _work


def layout_cost_dominance(plan, rows):
    """Identify strictly more expensive, unevaluated candidates in a frozen pool.

    Equal-cost candidates are retained, including possible tie-break winners.
    No predictions, oracle outcomes or unverified feasibility flags can establish
    the incumbent. A returned bound is for this declared material-cost objective,
    not for functional equivalence, other objectives or global design optimality.
    """
    data = strict_json_object_bytes(
        study._bytes({"plan": plan, "rows": rows}), maximum_bytes=8 * 1024 * 1024
    )
    plan, rows = data["plan"], data["rows"]
    if (
        type(plan) is not dict
        or plan.get("schema_version")
        not in (
            "experimental-rc-control-layout-search-plan.v1",
            "experimental-rc-control-layout-strategy-plan.v1",
            "experimental-rc-control-layout-cost-pruned-strategy-plan.v1",
            "experimental-rc-control-layout-staged-plan.v1",
        )
        or plan.get("plan_hash")
        != study._sha(study._bytes({k: v for k, v in plan.items() if k != "plan_hash"}))
        or type(plan.get("pool")) is not list
        or not 2 <= len(plan["pool"]) <= 17
        or type(rows) is not list
        or len(rows) > len(plan["pool"])
        or type(plan.get("history_limits")) is not dict
        or type(plan.get("material_limits")) is not dict
        or plan.get("terminal_limits") is not None
        and type(plan.get("terminal_limits")) is not dict
    ):
        raise ValueError("bounded frozen layout plan and reference rows required")
    pool = {}
    identity = None
    for item in plan["pool"]:
        if type(item) is not dict or type(item.get("candidate_id")) is not str:
            raise ValueError("typed unique layout pool required")
        key = item["candidate_id"]
        if key in pool or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", key):
            raise ValueError("unique portable layout pool candidate required")
        model_ref = item.get("model_artifact")
        if (
            type(model_ref) is not dict
            or type(model_ref.get("sha256")) is not str
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", model_ref["sha256"])
            or type(model_ref.get("byte_length")) is not int
            or model_ref["byte_length"] <= 0
            or type(item.get("quantities")) is not dict
        ):
            raise ValueError("typed model and quantity bindings required")
        estimate = item.get("material_estimate")
        if type(estimate) is not dict:
            raise ValueError("common material estimate required")
        total = estimate.get("total")
        if not isinstance(total, (int, float)) or isinstance(total, bool):
            raise ValueError("finite nonnegative material estimate required")
        try:
            finite = math.isfinite(total)
        except OverflowError:
            finite = False
        current = tuple(
            estimate.get(k) for k in ("currency", "scope", "price_table_hash")
        )
        if (
            not finite
            or total < 0
            or any(type(v) is not str or not v for v in current)
            or current[2] != plan.get("price_table_hash")
            or identity is not None
            and current != identity
        ):
            raise ValueError(
                "finite estimates with one currency, scope and price table required"
            )
        identity = current
        pool[key] = item
    if "baseline" not in pool:
        raise ValueError("layout pool must retain baseline")
    eligible, evaluated = [], set()
    for row in rows:
        if type(row) is not dict:
            raise ValueError("typed original reference row required")
        key = row.get("candidate_id")
        if type(key) is not str or key not in pool or key in evaluated:
            raise ValueError("unique evaluated rows from the frozen pool required")
        evaluated.add(key)
        if (
            row.get("material_estimate") != pool[key]["material_estimate"]
            or row.get("quantities") != pool[key].get("quantities")
            or type(row.get("quantities")) is not dict
        ):
            raise ValueError(
                "reference row quantities or estimate differ from frozen pool"
            )
        artifacts = row.get("artifacts")
        model_ref = artifacts.get("model") if type(artifacts) is dict else None
        pool_ref = pool[key].get("model_artifact")
        if (
            type(model_ref) is not dict
            or type(pool_ref) is not dict
            or any(
                model_ref.get(k) != pool_ref.get(k) for k in ("sha256", "byte_length")
            )
        ):
            raise ValueError("reference model artifact differs from frozen pool")
        invocations = row.get("invocations")
        complete_invocations = (
            type(invocations) is list
            and len(invocations) == 2
            and all(type(i) is dict for i in invocations)
            and [i.get("phase") for i in invocations] == ["analysis", "verification"]
            and all(
                i.get("status") == "returned"
                and i.get("unknown_execution_work") is False
                and type(i.get("work")) is dict
                and type(i["work"].get("attempted_step_count")) is int
                and i["work"]["attempted_step_count"] > 0
                for i in invocations
            )
        )
        if (
            row.get("selection_eligible") is True
            and verified_limit_outcome(plan, row) is True
            and complete_invocations
            and not _work({"rows": [row]})["unknown_work"]
        ):
            eligible.append(row)
    winner = min(
        eligible,
        key=lambda r: (r["material_estimate"]["total"], r["candidate_id"]),
        default=None,
    )
    dominated = []
    if winner is not None:
        dominated = [
            key
            for key, item in pool.items()
            if key not in evaluated
            and item["material_estimate"]["total"]
            > winner["material_estimate"]["total"]
        ]
    result = {
        "schema_version": "experimental-rc-layout-cost-dominance.v1",
        "plan_hash": plan["plan_hash"],
        "price_table_hash": plan["price_table_hash"],
        "evaluated_rows_hash": study._sha(study._bytes(rows)),
        "incumbent_candidate_id": None if winner is None else winner["candidate_id"],
        "incumbent_estimate": None
        if winner is None
        else winner["material_estimate"]["total"],
        "cost_dominated_unevaluated_candidate_ids": dominated,
        "retained_unevaluated_candidate_ids": [
            key for key in pool if key not in evaluated and key not in dominated
        ],
        "unevaluated_physical_feasibility": "unknown",
        "original_reference_artifact_verification_required": True,
        "global_cost_optimality_proved": False,
        "net_savings_proved": False,
        "execution_skips_performed": 0,
    }
    result["bound_hash"] = study._sha(study._bytes(result))
    return result
