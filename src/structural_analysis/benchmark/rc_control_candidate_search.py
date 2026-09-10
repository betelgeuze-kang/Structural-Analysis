"""Freeze cheap candidate rankings before bounded full RC control comparisons."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns

from structural_analysis.ai.fiber_frame_candidate_learning import (
    candidate_model_identity,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_learning import (
    RCControlCandidatePolicy,
    control_candidate_features,
)


def _work(report):
    invocations = [i for row in report["rows"] for i in row["invocations"]]
    unknown = any(i["unknown_execution_work"] for i in invocations)
    counts: dict[str, int] = {}
    for invocation in invocations:
        work = invocation["work"]
        if work is None:
            unknown = True
            continue
        for key in (
            "attempted_step_count",
            "known_linear_solve_count",
            "known_newton_iteration_count",
            "unknown_solver_work_attempt_count",
        ):
            value = work.get(key)
            if type(value) is not int or value < 0:
                unknown = True
            else:
                counts[key] = counts.get(key, 0) + value
        unknown = unknown or work.get("unknown_solver_work_attempt_count", 1) != 0
    return {
        "known_counters": counts,
        "unknown_work": unknown,
        "api_invocation_count": len(invocations),
    }


def _coverage_audit(plan, oracle_report):
    """Count alternative-level mistakes against the later full reference paths.

    A failed or incomplete oracle path is unknown, never a verified failure of
    the caller's limits. Baselines are excluded from prediction/coverage counts.
    No oracle means that whole-pool counts are unavailable, not zero.
    """
    ids = [r["candidate_id"] for r in plan["pool"] if r["candidate_id"] != "baseline"]
    prediction_rows = {r["candidate_id"]: r for r in plan["predictions"]}
    requested_screens = set(plan["history_limits"]) | set(plan["material_limits"])
    requested_screens.update("terminal_" + k for k in (plan["terminal_limits"] or {}))
    outcomes = None
    if oracle_report is not None:
        oracle_ids = [r["candidate_id"] for r in oracle_report["rows"]]
        if len(oracle_ids) != len(ids) + 1 or set(oracle_ids) != {"baseline", *ids}:
            raise ValueError("coverage oracle must retain the complete candidate pool")
        outcomes = {}
        for row in oracle_report["rows"]:
            if row["candidate_id"] == "baseline":
                continue
            screens = row.get("screens")
            known = (
                row["full_reference_verification_pass"] is True
                and type(screens) is dict
                and bool(screens)
                and set(screens) == requested_screens
                and all(s.get("status") in ("pass", "fail") for s in screens.values())
            )
            outcomes[row["candidate_id"]] = (
                None
                if not known
                else all(s["status"] == "pass" for s in screens.values())
            )
    details = []
    for candidate_id in ids:
        prediction = prediction_rows[candidate_id]
        screens = prediction["predicted_screens"]
        predicted_pass = (
            None
            if prediction["prediction"]["abstained"] or screens is None
            else all(s["status"] == "pass" for s in screens.values())
        )
        details.append(
            {
                "candidate_id": candidate_id,
                "predicted_all_requested_limits_pass": predicted_pass,
                "oracle_all_requested_limits_pass": None
                if outcomes is None
                else outcomes[candidate_id],
                "shortlisted_by": [
                    name
                    for name, arm in plan["plans"].items()
                    if candidate_id in arm["shortlist"]
                ],
            }
        )
    audits = {}
    for name in plan["plans"]:

        def matching(predicate):
            return (
                None
                if outcomes is None
                else [r["candidate_id"] for r in details if predicate(r)]
            )

        missed = matching(
            lambda r: r["oracle_all_requested_limits_pass"] is True
            and name not in r["shortlisted_by"]
        )
        unknown = matching(lambda r: r["oracle_all_requested_limits_pass"] is None)
        false_safe = (
            matching(
                lambda r: r["predicted_all_requested_limits_pass"] is True
                and r["oracle_all_requested_limits_pass"] is False
            )
            if name == "learned_order"
            else None
        )
        unverified = (
            matching(
                lambda r: r["predicted_all_requested_limits_pass"] is True
                and r["oracle_all_requested_limits_pass"] is None
            )
            if name == "learned_order"
            else None
        )
        false_negative = (
            matching(
                lambda r: r["predicted_all_requested_limits_pass"] is False
                and r["oracle_all_requested_limits_pass"] is True
            )
            if name == "learned_order"
            else None
        )
        groups = {
            "missed_feasible": missed,
            "oracle_unverifiable": unknown,
            "false_safe": false_safe,
            "predicted_safe_unverifiable": unverified,
            "false_negative": false_negative,
        }
        audits[name] = {
            key + suffix: (
                None if value is None else len(value) if suffix == "_count" else value
            )
            for key, value in groups.items()
            for suffix in ("_count", "_candidate_ids")
        }
    return {
        "schema_version": "rc-control-candidate-coverage-audit.v1",
        "status": "oracle_not_run"
        if outcomes is None
        else "compared_with_separate_full_reference_oracle",
        "alternative_denominator": len(ids),
        "baseline_excluded": True,
        "oracle_comparison_hash": None
        if oracle_report is None
        else oracle_report["report_hash"],
        "definitions": {
            "missed_feasible": "oracle_verified_all_requested_limits_pass_but_not_shortlisted",
            "false_safe": "predicted_all_requested_limits_pass_but_oracle_verified_limit_failure",
            "predicted_safe_unverifiable": "predicted_all_requested_limits_pass_but_oracle_unverifiable",
            "false_negative": "predicted_limit_failure_but_oracle_verified_all_requested_limits_pass",
            "deterministic_prediction_counts": "not_applicable_strategy_makes_no_predictions",
            "unavailable_counts": "null_does_not_mean_zero",
        },
        "candidates": details,
        "arms": audits,
        "independent_physical_validation": False,
    }


def compare_rc_control_candidate_search(
    baseline,
    candidates,
    request,
    *,
    policy: RCControlCandidatePolicy,
    training_report: dict,
    prices: design.FiberFrameMaterialPrices,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    source_revision: str,
    output_directory: Path,
    full_analysis_budget: int = 3,
    terminal_limits: design.FiberFrameTerminalLimits | None = None,
    evaluate_exhaustive_oracle: bool = False,
):
    """Compare frozen price-order and learned-order shortlists at the same budget.

    Each request budget includes the fresh baseline. Every selected alternative
    executes its entire requested path and fresh source replay. A separately
    charged exhaustive oracle may run only after both online arms finish.
    Training costs are retained once, outside online arm totals. This known
    family study is not a held-out project/campaign generalization experiment.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
    if type(policy) is not RCControlCandidatePolicy:
        raise ValueError("direct-control candidate policy required")
    if type(candidates) is not tuple or not 1 <= len(candidates) <= 16:
        raise ValueError("one to sixteen canonical alternatives required")
    if any(type(c) is not design.FiberFrameDesignCandidate for c in candidates):
        raise ValueError("exact canonical alternative type required")
    if len({c.candidate_id for c in candidates}) != len(candidates):
        raise ValueError("unique candidate IDs required")
    if type(full_analysis_budget) is not int or not 2 <= full_analysis_budget <= 17:
        raise ValueError(
            "two to seventeen requests per arm including baseline required"
        )
    if type(evaluate_exhaustive_oracle) is not bool:
        raise ValueError("explicit boolean oracle option required")
    if type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("one common explicit price table required")
    if (
        type(history_limits) is not design.FiberFrameHistoryLimits
        or type(material_limits) is not design.FiberFrameMaterialHistoryLimits
    ):
        raise ValueError("complete history and material screens required")
    if (
        terminal_limits is not None
        and type(terminal_limits) is not design.FiberFrameTerminalLimits
    ):
        raise ValueError("exact optional terminal screens required")
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ):
        raise ValueError("full source revision required")
    if (
        type(training_report) is not dict
        or training_report.get("schema_version")
        != "experimental-rc-control-candidate-training.v1"
    ):
        raise ValueError("original candidate training report required")
    # Detach caller-owned inputs before using their training cost declarations.
    training = json.loads(study._bytes(training_report))
    if training.get("report_hash") != study._sha(
        study._bytes({k: v for k, v in training.items() if k != "report_hash"})
    ):
        raise ValueError("training report hash mismatch")
    p = policy.to_dict()
    if (
        training.get("policy_hash") != policy.policy_hash
        or training.get("label_comparison_hash") != p["label_comparison_hash"]
    ):
        raise ValueError("training report/policy identity mismatch")
    if (
        training.get("sample_count") != len(p["training_sample_hashes"])
        or training.get("fit", {}).get("status") != "completed"
        or training["fit"].get("unknown_fit_work_until_outcome") is not False
    ):
        raise ValueError("completed training fit required")
    if len(training["label_invocations"]) != 2 * training["sample_count"]:
        raise ValueError(
            "original analysis and fresh replay required for every training model"
        )
    if any(
        i.get("unknown_execution_work") is not False or i.get("work") is None
        for i in training["label_invocations"]
    ):
        raise ValueError("known historical label generation work required")
    for value in (
        training["wall_ns"],
        training["cpu_ns"],
        training["fit"]["wall_ns"],
        training["label_generation_wall_ns"],
    ):
        if type(value) is not int or value < 0:
            raise ValueError("known nonnegative historical training costs required")
    frozen = policy._json
    original = baseline.detached_analysis_snapshot()
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            c.candidate_id,
            tuple(design.FiberFrameSectionChange(**asdict(s)) for s in c.changes),
        )
        for c in candidates
    )
    models = {"baseline": original}
    for c in candidates:
        models[c.candidate_id] = design.apply_fiber_frame_section_changes(original, c)
    identities = {key: candidate_model_identity(model) for key, model in models.items()}
    if len(set(identities.values())) != len(identities):
        raise ValueError(
            "duplicate physical alternatives are not new search candidates"
        )
    if set(identities.values()) & set(p["training_model_identities"]):
        raise ValueError("training/evaluation physical model overlap")
    pool = []
    for key, model in models.items():
        _, context = control_candidate_features(model, request)
        if context != p["context_hash"]:
            raise ValueError(
                "training/search direct-control or fixed model context mismatch"
            )
        quantities = design.calculate_fiber_frame_member_quantities(model)
        estimate = design._estimate(quantities, prices)
        assert estimate is not None
        model_bytes = study._bytes(model.canonical_payload())
        pool.append(
            {
                "candidate_id": key,
                "model_identity": identities[key],
                "model_checksum": model.canonical_model_checksum,
                "model_artifact": {
                    "path": "pool/" + key + ".json",
                    "byte_length": len(model_bytes),
                    "sha256": study._sha(model_bytes),
                },
                "quantities": quantities,
                "material_estimate": estimate,
            }
        )
    alternatives = [row for row in pool if row["candidate_id"] != "baseline"]

    def price_key(row):
        return row["material_estimate"]["total"], row["candidate_id"]

    deterministic = [r["candidate_id"] for r in sorted(alternatives, key=price_key)]
    rank_start = perf_counter_ns()
    predicted = []
    for row in alternatives:
        prediction = policy.predict(models[row["candidate_id"]], request)
        screens = (
            None
            if prediction["abstained"]
            else study._screens(
                prediction["performance"],
                history_limits,
                material_limits,
                terminal_limits,
            )
        )
        tier = (
            1
            if screens is None
            else 0
            if all(s["status"] == "pass" for s in screens.values())
            else 2
        )
        predicted.append(
            {
                "candidate_id": row["candidate_id"],
                "prediction": prediction,
                "predicted_screens": screens,
                "ranking_tier": tier,
                "estimate": row["material_estimate"]["total"],
            }
        )
    learned = [
        r["candidate_id"]
        for r in sorted(
            predicted,
            key=lambda r: (r["ranking_tier"], r["estimate"], r["candidate_id"]),
        )
    ]
    rank_wall = perf_counter_ns() - rank_start
    if policy._json != frozen:
        raise ValueError("policy changed while ranking")
    plans = {
        name: {"ordering": order, "shortlist": order[: full_analysis_budget - 1]}
        for name, order in (("price_order", deterministic), ("learned_order", learned))
    }
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    for row in pool:
        study._save(
            root,
            row["model_artifact"]["path"],
            study._bytes(models[row["candidate_id"]].canonical_payload()),
        )
    plan = {
        "schema_version": "experimental-rc-control-candidate-search-plan.v2",
        "source_revision": source_revision,
        "control_request": request.to_dict(),
        "policy_hash": policy.policy_hash,
        "training_report_hash": training["report_hash"],
        "price_table_hash": prices.price_table_hash,
        "pool": pool,
        "plans": plans,
        "history_limits": asdict(history_limits),
        "material_limits": asdict(material_limits),
        "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
        "predictions": predicted,
        "full_analysis_budget_per_arm": full_analysis_budget,
        "oracle_after_online_arms": evaluate_exhaustive_oracle,
        "original_training_and_pool_models_disjoint": True,
        "independent_project_geometry_history_split": False,
    }
    plan["plan_hash"] = study._sha(study._bytes(plan))
    study._save(root, "plan.json", study._bytes(plan))
    study._save(root, "policy.json", study._bytes(p))
    study._save(root, "historical-training.json", study._bytes(training))
    arm_results = {}
    comparisons = {}
    by_id = {c.candidate_id: c for c in candidates}

    def execute(name, chosen):
        started = {
            "status": "started",
            "candidate_ids": ["baseline", *chosen],
            "unknown_work_until_outcome": True,
        }
        study._save(root, name + "-started.json", study._bytes(started))
        aw, ac = perf_counter_ns(), process_time_ns()
        try:
            report = study.compare_rc_control_designs(
                original,
                tuple(by_id[k] for k in chosen),
                request,
                history_limits=history_limits,
                material_limits=material_limits,
                terminal_limits=terminal_limits,
                prices=prices,
                source_revision=source_revision,
                output_directory=root / name,
            )
        except BaseException as exc:
            study._save(
                root,
                name + "-outcome.json",
                study._bytes(
                    {
                        "status": "interrupted"
                        if isinstance(exc, KeyboardInterrupt)
                        else "raised",
                        "exception_kind": type(exc).__name__,
                        "wall_ns": perf_counter_ns() - aw,
                        "cpu_ns": process_time_ns() - ac,
                        "unknown_work_until_outcome": True,
                    }
                ),
            )
            raise
        work = _work(report)
        selected = next(
            (
                r
                for r in report["rows"]
                if r["candidate_id"] == report["selected_candidate_id"]
            ),
            None,
        )
        outcome = {
            "status": "completed",
            "comparison_hash": report["report_hash"],
            "comparison_path": name + "/comparison.json",
            "request_count": len(report["rows"]),
            "selected_candidate_id": report["selected_candidate_id"],
            "selected_estimate": None
            if selected is None
            else selected["material_estimate"]["total"],
            "selected_full_reference_verified": selected is not None
            and selected["full_reference_verification_pass"],
            "wall_ns": perf_counter_ns() - aw,
            "cpu_ns": process_time_ns() - ac,
            "execution_work": work,
            "unknown_work_until_outcome": work["unknown_work"],
        }
        study._save(root, name + "-outcome.json", study._bytes(outcome))
        if work["unknown_work"]:
            raise ValueError("unknown numerical work; stop before another search arm")
        comparisons[name] = report
        return outcome

    for name, choices in plans.items():
        arm_results[name] = execute(name, choices["shortlist"])
    oracle = (
        execute("exhaustive_oracle", deterministic)
        if evaluate_exhaustive_oracle
        else None
    )
    if policy._json != frozen:
        raise ValueError("policy changed during full path verification")
    report = {
        "schema_version": "experimental-rc-control-candidate-search.v2",
        "source_revision": source_revision,
        "plan_hash": plan["plan_hash"],
        "candidate_denominator": len(pool),
        "arms": arm_results,
        "oracle": oracle,
        "candidate_coverage_audit": _coverage_audit(
            plan, comparisons.get("exhaustive_oracle")
        ),
        "ranking_wall_ns": rank_wall,
        "historical_training_cost": training,
        "historical_training_cost_counted_once_outside_online_arms": True,
        "online_and_optional_oracle_wall_ns": perf_counter_ns() - wall,
        "online_and_optional_oracle_cpu_ns": process_time_ns() - cpu,
        "timing_scope": "preflight_ranking_both_full_analysis_arms_optional_oracle_and_IO_excluding_final_report_write",
        "claims": {
            "physical_winner_requires_full_reference_and_screens": True,
            "independent_generalization": False,
            "net_savings_proved": False,
            "confirmed_currency_savings": False,
            "workbench_search_review_integrated": False,
        },
    }
    study._save(
        root,
        "result.json",
        study._bytes(report | {"report_hash": study._sha(study._bytes(report))}),
    )
    return report | {"report_hash": study._sha(study._bytes(report))}
