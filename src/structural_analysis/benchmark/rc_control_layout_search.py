"""Frozen full-layout search plans with common-price reference evaluation."""

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns

from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
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
from structural_analysis.benchmark.rc_control_layout_features import (
    control_layout_candidate_features,
)
from structural_analysis.benchmark.rc_control_layout_learning import (
    RCControlLayoutPolicy,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.model.schema import CanonicalModel


@dataclass(frozen=True)
class RCControlLayoutCandidate:
    candidate_id: str
    model: CanonicalModel

    def __post_init__(self):
        if (
            type(self.candidate_id) is not str
            or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", self.candidate_id)
            or self.candidate_id == "baseline"
        ):
            raise ValueError(
                "unique portable non-baseline layout candidate ID required"
            )
        if type(self.model) is not CanonicalModel:
            raise ValueError("canonical layout candidate required")
        object.__setattr__(self, "model", self.model.detached_analysis_snapshot())


def _training_cost(policy, report):
    if type(report) is not dict:
        raise ValueError("original layout training report required")
    report = strict_json_object_bytes(
        study._bytes(report), maximum_bytes=2 * 1024 * 1024
    )
    p = policy.to_dict()
    if type(report.get("policy")) is not dict or type(report.get("fit")) is not dict:
        raise ValueError("typed training policy reference and fit required")
    if (
        report.get("schema_version") != "experimental-rc-control-layout-training.v1"
        or report.get("report_hash")
        != study._sha(
            study._bytes({k: v for k, v in report.items() if k != "report_hash"})
        )
        or report.get("labels_report_hash") != p["label_comparison_hash"]
        or report.get("policy", {}).get("sha256") != study._sha(study._bytes(p))
        or report.get("policy", {}).get("byte_length") != len(study._bytes(p))
        or type(report.get("sample_count")) is not int
        or report["sample_count"] != len(p["training_sample_hashes"])
        or report.get("fit", {}).get("status") != "completed"
        or report["fit"].get("unknown_fit_work_until_outcome") is not False
    ):
        raise ValueError("layout training report/policy identity or fit mismatch")
    invocations = report.get("label_invocations")
    if (
        type(invocations) is not list
        or len(invocations) != 2 * report["sample_count"]
        or any(type(i) is not dict for i in invocations)
        or [i.get("phase") for i in invocations]
        != ["analysis", "verification"] * report["sample_count"]
        or any(
            i.get("status") != "returned"
            or i.get("unknown_execution_work") is not False
            or i.get("work") is None
            for i in invocations
        )
        or _work({"rows": [{"invocations": invocations}]})["unknown_work"]
    ):
        raise ValueError(
            "known original training analysis and verification work required"
        )
    for value in (
        report.get("wall_ns"),
        report.get("cpu_ns"),
        report["fit"].get("wall_ns"),
        report.get("label_generation_wall_ns"),
    ):
        if type(value) is not int or value < 0:
            raise ValueError("known nonnegative training costs required")
    if (
        report["wall_ns"]
        < report["fit"]["wall_ns"] + report["label_generation_wall_ns"]
    ):
        raise ValueError(
            "enclosing training interval cannot be smaller than components"
        )
    return report


def _run_layout_search(
    baseline,
    candidates,
    request,
    *,
    policy=None,
    training_report=None,
    prices,
    history_limits,
    material_limits,
    source_revision,
    output_directory,
    full_analysis_budget=3,
    evaluate_exhaustive_oracle=False,
    terminal_limits=None,
    only_strategy=None,
):
    """Execute frozen schedules; final results require actual reference paths."""
    wall, cpu = perf_counter_ns(), process_time_ns()
    if only_strategy not in (None, "price_order", "learned_order"):
        raise ValueError("supported standalone layout strategy required")
    if only_strategy is not None and evaluate_exhaustive_oracle:
        raise ValueError("standalone layout execution cannot receive an oracle")
    uses_policy = only_strategy != "price_order"
    if not uses_policy and (policy is not None or training_report is not None):
        raise ValueError("price-only layout execution cannot receive learned artifacts")
    if uses_policy and type(policy) is not RCControlLayoutPolicy:
        raise ValueError("exact layout policy required")
    if type(baseline) is not CanonicalModel:
        raise ValueError("canonical layout baseline required")
    if (
        type(candidates) is not tuple
        or not 1 <= len(candidates) <= 16
        or any(type(c) is not RCControlLayoutCandidate for c in candidates)
    ):
        raise ValueError("one to sixteen typed layout alternatives required")
    if len({c.candidate_id for c in candidates}) != len(candidates):
        raise ValueError("unique layout candidate IDs required")
    if type(full_analysis_budget) is not int or not 2 <= full_analysis_budget <= 17:
        raise ValueError(
            "two to seventeen requests per arm including baseline required"
        )
    if type(evaluate_exhaustive_oracle) is not bool:
        raise ValueError("explicit boolean oracle option required")
    if (
        type(prices) is not design.FiberFrameMaterialPrices
        or type(history_limits) is not design.FiberFrameHistoryLimits
        or type(material_limits) is not design.FiberFrameMaterialHistoryLimits
    ):
        raise ValueError("common typed prices and complete performance limits required")
    if (
        terminal_limits is not None
        and type(terminal_limits) is not design.FiberFrameTerminalLimits
    ):
        raise ValueError("typed optional terminal limits required")
    if type(source_revision) is not str or not re.fullmatch(
        r"[a-f0-9]{40}", source_revision
    ):
        raise ValueError("full source revision required")
    training = _training_cost(policy, training_report) if uses_policy else None
    frozen = policy._json if uses_policy else None
    policy_data = policy.to_dict() if uses_policy else None
    models = {"baseline": baseline.detached_analysis_snapshot()}
    models.update(
        {c.candidate_id: c.model.detached_analysis_snapshot() for c in candidates}
    )
    pool, identities = [], set()
    context = None
    for key, model in models.items():
        descriptor = control_layout_candidate_features(model, request)
        identity = descriptor["physical_model_identity"]
        if (
            identity in identities
            or policy_data is not None
            and identity in policy_data["training_model_identities"]
        ):
            raise ValueError("duplicate or training/evaluation physical model overlap")
        if context is None:
            context = descriptor["context_hash"]
        if (
            descriptor["context_hash"] != context
            or policy_data is not None
            and context != policy_data["context_hash"]
        ):
            raise ValueError("layout search fixed context mismatch")
        identities.add(identity)
        quantities = design.calculate_fiber_frame_member_quantities(model)
        raw = study._bytes(model.canonical_payload())
        pool.append(
            {
                "candidate_id": key,
                "model_identity": identity,
                "quantities": quantities,
                "material_estimate": design._estimate(quantities, prices),
                "model_artifact": {
                    "path": f"pool/{key}.json",
                    "byte_length": len(raw),
                    "sha256": study._sha(raw),
                },
            }
        )
    alternatives = pool[1:]
    deterministic = [
        r["candidate_id"]
        for r in sorted(
            alternatives,
            key=lambda r: (r["material_estimate"]["total"], r["candidate_id"]),
        )
    ]
    predictions = []
    learned, ranking, rank_wall = [], None, 0
    if uses_policy:
        rank_start = perf_counter_ns()
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
            predictions.append(
                {
                    "candidate_id": row["candidate_id"],
                    "prediction": prediction,
                    "predicted_screens": screens,
                    "ranking_tier": tier,
                    "estimate": row["material_estimate"]["total"],
                }
            )
        learned, ranking = candidate_ranking(predictions, CHEAPER_BOUNDARY_RANKING)
        rank_wall = perf_counter_ns() - rank_start
        if policy._json != frozen:
            raise ValueError("policy changed during ranking")
    plans = {
        name: {"ordering": order, "shortlist": order[: full_analysis_budget - 1]}
        for name, order in (("price_order", deterministic), ("learned_order", learned))
        if only_strategy is None or name == only_strategy
    }
    plan = {
        "schema_version": "experimental-rc-control-layout-search-plan.v1",
        "source_revision": source_revision,
        "control_request": request.to_dict(),
        "policy_hash": policy.policy_hash if uses_policy else None,
        "training_report_hash": training["report_hash"]
        if training is not None
        else None,
        "pool": pool,
        "plans": plans,
        "price_table_hash": prices.price_table_hash,
        "history_limits": asdict(history_limits),
        "material_limits": asdict(material_limits),
        "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
        "predictions": predictions,
        "ranking": ranking,
        "full_analysis_budget_per_arm": full_analysis_budget,
        "oracle_after_online_arms": evaluate_exhaustive_oracle,
        "independent_project_geometry_history_split": False,
        "functional_equivalence_verified": False,
    }
    if only_strategy is not None:
        plan["schema_version"] = "experimental-rc-control-layout-strategy-plan.v1"
        plan["strategy"] = only_strategy
    plan["plan_hash"] = study._sha(study._bytes(plan))
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    study._save(root, "plan.json", study._bytes(plan))
    study._save(root, "price-table.json", study._bytes(asdict(prices)))
    if uses_policy:
        study._save(root, "policy.json", study._bytes(policy_data))
        study._save(root, "historical-training.json", study._bytes(training))
    for row in pool:
        study._save(
            root,
            row["model_artifact"]["path"],
            study._bytes(models[row["candidate_id"]].canonical_payload()),
        )
    comparisons, outcomes = {}, {}

    def execute(name, chosen):
        arm_root = root / name
        arm_root.mkdir()
        rows = []
        study._save(
            arm_root,
            "started.json",
            study._bytes(
                {
                    "status": "started",
                    "candidate_ids": ["baseline", *chosen],
                    "unknown_work_until_outcome": True,
                }
            ),
        )
        aw, ac = perf_counter_ns(), process_time_ns()
        try:
            for key in ("baseline", *chosen):
                case_root = arm_root / key
                case_root.mkdir()
                row = study._reference_design_row(
                    models[key],
                    None,
                    request,
                    case_root,
                    request.api_kwargs() | {"restart": None},
                    prices,
                    history_limits,
                    material_limits,
                    terminal_limits,
                )
                row["candidate_id"] = key
                row["artifacts"] = {
                    k: ref | {"path": f"{key}/{ref['path']}"}
                    for k, ref in row["artifacts"].items()
                }
                rows.append(row)
                study._save(case_root, "row.json", study._bytes(row))
                if _work({"rows": [row]})["unknown_work"]:
                    raise ValueError("unknown numerical work; stop layout search")
            eligible = [r for r in rows if r["selection_eligible"]]
            winner = (
                min(
                    eligible,
                    key=lambda r: (r["material_estimate"]["total"], r["candidate_id"]),
                )
                if eligible
                else None
            )
            comparison = {
                "schema_version": "experimental-rc-control-layout-comparison.v1",
                "rows": rows,
                "price_table_hash": prices.price_table_hash,
                "selected_candidate_id": None
                if winner is None
                else winner["candidate_id"],
            }
            comparison["report_hash"] = study._sha(study._bytes(comparison))
            study._save(arm_root, "comparison.json", study._bytes(comparison))
        except BaseException as error:
            study._save(
                arm_root,
                "outcome.json",
                study._bytes(
                    {
                        "status": "interrupted"
                        if isinstance(error, KeyboardInterrupt)
                        else "raised",
                        "exception_kind": type(error).__name__,
                        "rows": rows,
                        "wall_ns": perf_counter_ns() - aw,
                        "unknown_work_until_outcome": True,
                    }
                ),
            )
            raise
        outcome = {
            "status": "completed",
            "comparison_hash": comparison["report_hash"],
            "comparison_path": f"{name}/comparison.json",
            "request_count": len(rows),
            "selected_candidate_id": comparison["selected_candidate_id"],
            "execution_work": _work(comparison),
            "wall_ns": perf_counter_ns() - aw,
            "cpu_ns": process_time_ns() - ac,
            "unknown_work_until_outcome": False,
        }
        study._save(arm_root, "outcome.json", study._bytes(outcome))
        comparisons[name] = comparison
        return outcome

    for name, choices in plans.items():
        outcomes[name] = execute(name, choices["shortlist"])
    oracle = (
        execute("exhaustive_oracle", deterministic)
        if evaluate_exhaustive_oracle
        else None
    )
    if uses_policy and policy._json != frozen:
        raise ValueError("policy changed during evaluation")
    report = {
        "schema_version": "experimental-rc-control-layout-search.v1",
        "source_revision": source_revision,
        "plan_hash": plan["plan_hash"],
        "arms": outcomes,
        "oracle": oracle,
        "candidate_coverage_audit": _coverage_audit(
            plan, comparisons.get("exhaustive_oracle")
        )
        if uses_policy
        else None,
        "candidate_cost_optimality_audit": candidate_cost_optimality_audit(
            plan, comparisons
        ),
        "ranking_wall_ns": rank_wall,
        "historical_training_cost": training,
        "historical_training_cost_counted_once_outside_online_arms": uses_policy,
        "online_and_optional_oracle_wall_ns": perf_counter_ns() - wall,
        "online_and_optional_oracle_cpu_ns": process_time_ns() - cpu,
        "timing_scope": "preflight_ranking_both_reference_arms_optional_oracle_and_IO_excluding_final_report_write",
        "claims": {
            "physical_winner_requires_full_reference_and_screens": True,
            "independent_generalization": False,
            "functional_equivalence_verified": False,
            "net_savings_proved": False,
            "confirmed_currency_savings": False,
            "workbench_search_review_integrated": False,
        },
    }
    if only_strategy is not None:
        report["schema_version"] = "experimental-rc-control-layout-strategy.v1"
        report["strategy"] = only_strategy
        report["timing_scope"] = (
            "single_layout_strategy_preparation_ranking_full_reference_and_IO_excluding_final_report_write"
        )
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "result.json", study._bytes(report))
    return report


def compare_control_layout_search(*args, **kwargs):
    """Run both frozen schedules followed by an optional separate oracle."""
    if "only_strategy" in kwargs:
        raise ValueError("use run_control_layout_strategy for standalone execution")
    return _run_layout_search(*args, **kwargs)


def run_control_layout_strategy(*args, strategy, **kwargs):
    """Run one complete strategy; price order receives no learned artifacts."""
    if strategy not in ("price_order", "learned_order") or "only_strategy" in kwargs:
        raise ValueError("one supported explicit layout strategy required")
    return _run_layout_search(*args, only_strategy=strategy, **kwargs)
