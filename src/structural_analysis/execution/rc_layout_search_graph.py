"""Bounded layout-search graph admission; no solver replay or new qualification."""

import re

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.fiber_frame_design import (
    calculate_fiber_frame_member_quantities,
    FiberFrameMaterialPrices,
    FiberFrameHistoryLimits,
    FiberFrameMaterialHistoryLimits,
    FiberFrameTerminalLimits,
    _estimate,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark.rc_control_layout_features import (
    control_layout_candidate_features,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.benchmark.rc_control_candidate_cost import (
    candidate_cost_optimality_audit,
)
from structural_analysis.benchmark.rc_control_candidate_ranking import (
    CHEAPER_BOUNDARY_RANKING,
    candidate_ranking,
)
from structural_analysis.benchmark.rc_control_candidate_search import (
    _coverage_audit,
    _work,
)
from structural_analysis.benchmark.rc_control_layout_learning import (
    RCControlLayoutPolicy,
)
from structural_analysis.benchmark.rc_control_layout_search import _training_cost
from structural_analysis.execution.rc_search_http import _document, _META_MAX, _ROLES

_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}")


def _same(actual, expected, message):
    if study._bytes(actual) != study._bytes(expected):
        raise ValueError(message)


def read_layout_search_graph(read, result):
    """Read the exact original graph and recompute scheduling/accounting bindings.

    Result/checkpoint bytes remain original. Their engineering validation belongs
    to the subsequent review layer; this operation executes no numerical path.
    """
    try:
        _read_layout_search_graph(read, result)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("malformed layout artifact graph") from error


def _read_layout_search_graph(read, result):
    staged = (
        result.get("schema_version")
        == "experimental-rc-control-layout-staged-strategy.v1"
    )
    pruned = staged or result.get("schema_version") == (
        "experimental-rc-control-layout-cost-pruned-strategy.v1"
    )
    standalone = pruned or result.get("schema_version") == (
        "experimental-rc-control-layout-strategy.v1"
    )
    strategy = result.get("strategy") if standalone else None
    if standalone and strategy not in ("price_order", "learned_order"):
        raise ValueError("explicit standalone layout strategy required")
    uses_policy = strategy != "price_order"
    plan = _document(read("plan.json", _META_MAX), "plan_hash")
    if (
        plan.get("schema_version")
        != (
            "experimental-rc-control-layout-staged-plan.v1"
            if staged
            else "experimental-rc-control-layout-cost-pruned-strategy-plan.v1"
            if pruned
            else "experimental-rc-control-layout-strategy-plan.v1"
            if standalone
            else "experimental-rc-control-layout-search-plan.v1"
        )
        or result.get("plan_hash") != plan["plan_hash"]
    ):
        raise ValueError("layout plan binding mismatch")
    if (
        type(plan.get("source_revision")) is not str
        or not re.fullmatch(r"[a-f0-9]{40}", plan["source_revision"])
        or plan["source_revision"] != result.get("source_revision")
    ):
        raise ValueError("layout source revision binding mismatch")
    if standalone and (
        plan.get("strategy") != strategy
        or plan.get("oracle_after_online_arms") is not False
        or result.get("oracle") is not None
        or result.get("timing_scope")
        != (
            "single_strategy_preparation_cost_bounds_prefix_and_full_reference_verification_IO_excluding_final_report_write"
            if staged
            else "single_layout_strategy_preparation_ranking_cost_bounds_full_reference_and_IO_excluding_final_report_write"
            if pruned
            else "single_layout_strategy_preparation_ranking_full_reference_and_IO_excluding_final_report_write"
        )
    ):
        raise ValueError("standalone layout strategy or scope differs")
    if pruned:
        from structural_analysis.execution.rc_layout_cost_pruning_graph import (
            check_pruning_policy,
        )

        check_pruning_policy(plan, result)
    policy = None
    if uses_policy:
        policy_raw = read("policy.json", _META_MAX)
        policy = RCControlLayoutPolicy(policy_raw.decode("utf-8"))
        training = _document(read("historical-training.json", _META_MAX), "report_hash")
        _training_cost(policy, training)
        _same(
            result.get("historical_training_cost"),
            training,
            "historical training document differs",
        )
        if (
            plan.get("policy_hash") != policy.policy_hash
            or plan.get("training_report_hash") != training["report_hash"]
        ):
            raise ValueError("layout training/policy plan binding mismatch")
        if (
            result.get("historical_training_cost_counted_once_outside_online_arms")
            is not True
        ):
            raise ValueError("explicit once-only training accounting required")
    else:
        if (
            any(
                plan.get(k) is not None
                for k in ("policy_hash", "training_report_hash", "ranking")
            )
            or result.get("historical_training_cost") is not None
            or result.get("historical_training_cost_counted_once_outside_online_arms")
            is not False
            or result.get("ranking_wall_ns") != 0
        ):
            raise ValueError("price strategy cannot carry learned artifacts or costs")
    _same(
        result.get("claims"),
        {
            "physical_winner_requires_full_reference_and_screens": True,
            "independent_generalization": False,
            "functional_equivalence_verified": False,
            "net_savings_proved": False,
            "confirmed_currency_savings": False,
            "workbench_search_review_integrated": False,
        },
        "unsupported layout qualification claims",
    )
    if (
        plan.get("independent_project_geometry_history_split") is not False
        or plan.get("functional_equivalence_verified") is not False
    ):
        raise ValueError("layout scope flags differ")
    budget = plan.get("full_analysis_budget_per_arm")
    if type(budget) is not int or not 2 <= budget <= 17:
        raise ValueError("bounded layout request budget required")
    pool = plan.get("pool")
    if type(pool) is not list or not 2 <= len(pool) <= 17:
        raise ValueError("bounded layout pool required")
    ids = [r["candidate_id"] for r in pool]
    if (
        ids[0] != "baseline"
        or any(type(i) is not str or not _ID.fullmatch(i) for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("unique portable layout pool identities required")
    model_ids = [r["model_identity"] for r in pool]
    if len(set(model_ids)) != len(model_ids) or set(model_ids) & set(
        policy.to_dict()["training_model_identities"] if policy is not None else []
    ):
        raise ValueError("duplicate or training-overlapping layout identities")
    request = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(plan["control_request"])
    )
    if staged:
        from structural_analysis.execution.rc_layout_staged_graph import (
            check_staged_policy,
        )

        check_staged_policy(plan, result, request)
    models = {}
    history_limits = FiberFrameHistoryLimits(**plan["history_limits"])
    material_limits = FiberFrameMaterialHistoryLimits(**plan["material_limits"])
    terminal_limits = (
        None
        if plan["terminal_limits"] is None
        else FiberFrameTerminalLimits(**plan["terminal_limits"])
    )
    prices = FiberFrameMaterialPrices(
        **strict_json_object_bytes(
            read("price-table.json", _META_MAX), maximum_bytes=_META_MAX
        )
    )
    if prices.price_table_hash != plan["price_table_hash"]:
        raise ValueError("original price table hash differs")
    context = None
    for row in pool:
        reference = row["model_artifact"]
        if (
            set(reference) != {"path", "byte_length", "sha256"}
            or reference["path"] != f"pool/{row['candidate_id']}.json"
        ):
            raise ValueError("layout pool artifact path invalid")
        model = load_neutral_json_bytes(
            read(reference["path"], 16 * 1024**2, reference)
        )
        descriptor = control_layout_candidate_features(model, request)
        if context is None:
            context = descriptor["context_hash"]
        if (
            descriptor["physical_model_identity"] != row["model_identity"]
            or descriptor["context_hash"] != context
            or policy is not None
            and context != policy.to_dict()["context_hash"]
        ):
            raise ValueError("original layout model identity or context differs")
        _same(
            row["quantities"],
            calculate_fiber_frame_member_quantities(model),
            "original layout quantities differ",
        )
        _same(
            row["material_estimate"],
            _estimate(row["quantities"], prices),
            "original price/quantity estimate differs",
        )
        models[row["candidate_id"]] = model
    predicted = plan.get("predictions")
    if type(predicted) is not list or [r["candidate_id"] for r in predicted] != (
        ids[1:] if uses_policy else []
    ):
        raise ValueError("complete ordered layout predictions required")
    by_id = {r["candidate_id"]: r for r in pool}
    for row in predicted:
        assert policy is not None
        _same(
            row["estimate"],
            by_id[row["candidate_id"]]["material_estimate"]["total"],
            "prediction price differs from pool",
        )
        prediction = row["prediction"]
        _same(
            prediction,
            policy.predict(models[row["candidate_id"]], request),
            "layout prediction differs from frozen policy",
        )
        if (
            prediction.get("policy_hash") != policy.policy_hash
            or prediction.get("physical_result_authority") is not False
            or prediction.get("uncertainty_calibrated") is not False
            or prediction.get("joint_geometry_history_generalization") is not False
        ):
            raise ValueError("prediction identity or scope differs")
        if type(prediction.get("abstained")) is not bool:
            raise ValueError("explicit prediction abstention required")
        screens = row["predicted_screens"]
        if prediction["abstained"]:
            if screens is not None or prediction.get("performance") is not None:
                raise ValueError("abstention cannot carry predicted response")
            tier = 1
        else:
            limits = plan["history_limits"] | plan["material_limits"]
            limits.update(
                {"terminal_" + k: v for k, v in (plan["terminal_limits"] or {}).items()}
            )
            performance = prediction["performance"]
            expected = {
                k: {
                    "value": performance[k],
                    "limit": v,
                    "status": "pass" if performance[k] <= v else "fail",
                }
                for k, v in limits.items()
            }
            _same(screens, expected, "predicted screens differ from declared limits")
            tier = 0 if all(s["status"] == "pass" for s in screens.values()) else 2
        _same(row["ranking_tier"], tier, "prediction tier differs")
    learned, ranking = (
        candidate_ranking(predicted, CHEAPER_BOUNDARY_RANKING)
        if uses_policy
        else ([], None)
    )
    deterministic = [
        r["candidate_id"]
        for r in sorted(
            pool[1:], key=lambda r: (r["material_estimate"]["total"], r["candidate_id"])
        )
    ]
    _same(plan.get("ranking"), ranking, "layout ranking differs")
    plans = {
        name: {"ordering": order, "shortlist": order[: budget - 1]}
        for name, order in (("price_order", deterministic), ("learned_order", learned))
        if not standalone or name == strategy
    }
    _same(plan.get("plans"), plans, "layout shortlist differs from frozen ranking")
    arms = result.get("arms")
    if type(arms) is not dict or set(arms) != set(plans):
        raise ValueError("both layout arms required")
    if type(plan.get("oracle_after_online_arms")) is not bool or plan[
        "oracle_after_online_arms"
    ] != (result.get("oracle") is not None):
        raise ValueError("layout oracle declaration differs")
    outcomes = dict(arms)
    if result.get("oracle") is not None:
        outcomes["exhaustive_oracle"] = result["oracle"]
    comparisons = {}
    for name, outcome in outcomes.items():
        path = f"{name}/comparison.json"
        if (
            outcome.get("status") != "completed"
            or outcome.get("comparison_path") != path
            or outcome.get("unknown_work_until_outcome") is not False
        ):
            raise ValueError("completed layout arm required")
        comparison = _document(read(path, _META_MAX), "report_hash")
        comparison_schema = (
            "experimental-rc-control-layout-staged-comparison.v1"
            if staged
            else "experimental-rc-control-layout-cost-pruned-comparison.v1"
            if pruned
            else "experimental-rc-control-layout-comparison.v1"
        )
        if (
            comparison.get("schema_version") != comparison_schema
            or comparison["report_hash"] != outcome.get("comparison_hash")
            or comparison.get("price_table_hash") != plan["price_table_hash"]
        ):
            raise ValueError("layout comparison binding mismatch")
        rows = comparison.get("rows")
        expected_ids = [
            "baseline",
            *(
                deterministic
                if name == "exhaustive_oracle"
                else plans[name]["shortlist"]
            ),
        ]
        if (
            type(rows) is not list
            or not pruned
            and [r["candidate_id"] for r in rows] != expected_ids
            or pruned
            and (
                len(rows) > len(expected_ids)
                or len({r["candidate_id"] for r in rows}) != len(rows)
                or any(r["candidate_id"] not in expected_ids for r in rows)
            )
            or type(outcome.get("request_count")) is not int
            or outcome["request_count"] != len(rows)
        ):
            raise ValueError("layout comparison order or denominator differs")
        work = _work(comparison)
        if work["unknown_work"]:
            raise ValueError("layout comparison has unknown work")
        if not staged:
            _same(
                outcome.get("execution_work"),
                work,
                "layout execution accounting differs",
            )
        if outcome.get("selected_candidate_id") != comparison.get(
            "selected_candidate_id"
        ):
            raise ValueError("layout outcome selection differs")
        for row in rows:
            _same(
                row["quantities"],
                by_id[row["candidate_id"]]["quantities"],
                "comparison quantities differ from pool",
            )
            _same(
                row["material_estimate"],
                by_id[row["candidate_id"]]["material_estimate"],
                "comparison material estimate differs from pool",
            )
            if row.get("full_reference_verification_pass") is True:
                screens = study._screens(
                    row["performance"], history_limits, material_limits, terminal_limits
                )
                _same(
                    row["screens"],
                    screens,
                    "reference screens differ from recorded performance",
                )
                _same(
                    row["selection_eligible"],
                    all(s["status"] == "pass" for s in screens.values()),
                    "reference selection eligibility differs",
                )
            refs = row.get("artifacts")
            if type(refs) is not dict or not set(refs) <= _ROLES:
                raise ValueError("layout artifact roles invalid")
            if (
                row.get("full_reference_verification_pass") is True
                and set(refs) != _ROLES
            ):
                raise ValueError("verified layout row requires every original artifact")
            for role, ref in refs.items():
                relative = (
                    f"{row['candidate_id']}/baseline/{role.replace('_', '-')}.json"
                )
                if (
                    type(ref) is not dict
                    or set(ref) != {"path", "sha256", "byte_length"}
                    or ref.get("path") != relative
                ):
                    raise ValueError("layout original artifact path differs")
                read(
                    f"{name}/{relative}",
                    (64 if role == "result" else 128 if role == "checkpoint" else 16)
                    * 1024**2,
                    ref,
                )
            if "model" in refs:
                _same(
                    {k: v for k, v in refs["model"].items() if k != "path"},
                    {
                        k: v
                        for k, v in by_id[row["candidate_id"]]["model_artifact"].items()
                        if k != "path"
                    },
                    "reference model differs from pool",
                )
        if staged:
            from structural_analysis.execution.rc_layout_staged_graph import (
                check_staged_comparison,
            )

            staged_work = check_staged_comparison(
                read, plan, name, comparison, outcome, models, request
            )
            _same(
                outcome.get("execution_work"),
                staged_work,
                "staged total execution accounting differs",
            )
        elif pruned:
            from structural_analysis.execution.rc_layout_cost_pruning_graph import (
                check_pruned_comparison,
            )

            check_pruned_comparison(
                read, plan, name, comparison, outcome, models, request
            )
        eligible = [
            r
            for r in rows
            if r.get("full_reference_verification_pass") is True
            and r.get("selection_eligible") is True
        ]
        selected = (
            min(
                eligible,
                key=lambda r: (r["material_estimate"]["total"], r["candidate_id"]),
            )["candidate_id"]
            if eligible
            else None
        )
        _same(
            comparison.get("selected_candidate_id"),
            selected,
            "comparison winner differs from evaluated feasible minimum",
        )
        for key in ("wall_ns", "cpu_ns"):
            if type(outcome.get(key)) is not int or outcome[key] < 0:
                raise ValueError("known nonnegative layout arm costs required")
        comparisons[name] = comparison
    for key in (
        "ranking_wall_ns",
        "online_and_optional_oracle_wall_ns",
        "online_and_optional_oracle_cpu_ns",
    ):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError("known nonnegative layout search costs required")
    if result["online_and_optional_oracle_wall_ns"] < result["ranking_wall_ns"] + sum(
        o["wall_ns"] for o in outcomes.values()
    ):
        raise ValueError("layout total is smaller than disjoint components")
    _same(
        result.get("candidate_cost_optimality_audit"),
        None if pruned else candidate_cost_optimality_audit(plan, comparisons),
        "layout cost optimality differs",
    )
    _same(
        result.get("candidate_coverage_audit"),
        _coverage_audit(plan | {"plans": plans}, comparisons.get("exhaustive_oracle"))
        if uses_policy and not pruned
        else None,
        "layout coverage differs",
    )
