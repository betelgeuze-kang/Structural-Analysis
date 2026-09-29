"""Prospective RC search with an indexed force-response floor.

The floor and shortlist are frozen before numerical work. A later, separately
charged exhaustive comparison can establish only the declared pool optimum.
The v1 path uses price order; the v2 path compares price and learned rankings.
Neither establishes independent physical validation.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import math
import re
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from structural_analysis.ai.fiber_frame_candidate_learning import (
    candidate_model_identity,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_cost import (
    FORCE_FLOOR_PLAN,
    FORCE_FLOOR_LEARNED_PLAN,
    candidate_cost_optimality_audit,
)
from structural_analysis.benchmark.rc_control_candidate_search import (
    _coverage_audit,
    _work,
)
from structural_analysis.benchmark.rc_control_candidate_learning import TARGETS
from structural_analysis.benchmark.rc_control_candidate_ranking import (
    LEGACY_RANKING,
    candidate_ranking,
)
from structural_analysis.model.schema import CanonicalModel


SEARCH_SCHEMA = "experimental-rc-control-force-floor-price-search.v1"
LEARNED_SEARCH_SCHEMA = "experimental-rc-control-force-floor-learned-search.v2"


def compare_rc_control_force_floor_price_search(
    baseline: CanonicalModel,
    candidates: tuple[design.FiberFrameDesignCandidate, ...],
    request: BoundedRCFiberDirectControlRequest,
    *,
    force_response_floor: dict,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    prices: design.FiberFrameMaterialPrices,
    source_revision: str,
    output_directory: Path,
    full_analysis_budget: int,
    terminal_limits: design.FiberFrameTerminalLimits | None = None,
    reuse_line_search_assembly: bool = False,
    protocol_binding: dict | None = None,
) -> dict:
    """Run a frozen price shortlist, then a separate full-pool oracle.

    The budget includes the baseline. Failed candidates retain their place in
    the denominator; missing execution work prevents the next comparison.
    """
    started_wall, started_cpu = perf_counter_ns(), process_time_ns()
    if type(baseline) is not CanonicalModel:
        raise ValueError("exact canonical baseline required")
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact direct-control request required")
    request = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(request.to_dict())
    )
    floor = study._validated_force_response_floor(
        force_response_floor, baseline, request
    )
    if floor is None:
        raise ValueError("prospective force-response floor required")
    if type(candidates) is not tuple or not 1 <= len(candidates) <= 16:
        raise ValueError("one to sixteen canonical alternatives required")
    if any(
        type(candidate) is not design.FiberFrameDesignCandidate
        for candidate in candidates
    ):
        raise ValueError("exact canonical section-change alternatives required")
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("unique candidate identities required")
    if (
        type(full_analysis_budget) is not int
        or not 2 <= full_analysis_budget <= len(candidates) + 1
    ):
        raise ValueError(
            "analysis budget must include baseline and one to all alternatives"
        )
    if type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("one common explicit price table required")
    if (
        type(history_limits) is not design.FiberFrameHistoryLimits
        or type(material_limits) is not design.FiberFrameMaterialHistoryLimits
    ):
        raise ValueError("explicit full history and material screens required")
    if (
        terminal_limits is not None
        and type(terminal_limits) is not design.FiberFrameTerminalLimits
    ):
        raise ValueError("exact optional terminal screens required")
    if type(reuse_line_search_assembly) is not bool:
        raise ValueError("explicit boolean line-search assembly reuse required")
    if (
        type(source_revision) is not str
        or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None
    ):
        raise ValueError("full source revision required")
    if protocol_binding is not None:
        if type(protocol_binding) is not dict or set(protocol_binding) != {
            "protocol_commit",
            "protocol_path",
            "protocol_sha256",
            "input_sha256",
        }:
            raise ValueError("exact precommitted protocol binding required")
        if (
            type(protocol_binding["protocol_commit"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", protocol_binding["protocol_commit"])
            is None
            or type(protocol_binding["protocol_path"]) is not str
            or not protocol_binding["protocol_path"].startswith("examples/research/")
            or ".." in Path(protocol_binding["protocol_path"]).parts
            or type(protocol_binding["protocol_sha256"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", protocol_binding["protocol_sha256"])
            is None
            or type(protocol_binding["input_sha256"]) is not dict
            or set(protocol_binding["input_sha256"])
            != {"model", "request", "experiment", "floor_plan"}
            or any(
                type(value) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                for value in protocol_binding["input_sha256"].values()
            )
        ):
            raise ValueError("invalid precommitted protocol binding")
        protocol_binding = {
            **protocol_binding,
            "input_sha256": dict(protocol_binding["input_sha256"]),
        }

    original = baseline.detached_analysis_snapshot()
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            candidate.candidate_id,
            tuple(
                design.FiberFrameSectionChange(**asdict(change))
                for change in candidate.changes
            ),
        )
        for candidate in candidates
    )
    models = {"baseline": original}
    for candidate in candidates:
        models[candidate.candidate_id] = design.apply_fiber_frame_section_changes(
            original, candidate
        )
    identities = {
        candidate_id: candidate_model_identity(model, experimental_pin_roller_beam=True)
        for candidate_id, model in models.items()
    }
    if len(set(identities.values())) != len(identities):
        raise ValueError("duplicate physical alternatives are not new candidates")
    pool = []
    for candidate_id, model in models.items():
        quantities = design.calculate_fiber_frame_member_quantities(
            model, experimental_pin_roller_beam=True
        )
        estimate = design._estimate(quantities, prices)
        model_bytes = study._bytes(model.canonical_payload())
        pool.append(
            {
                "candidate_id": candidate_id,
                "model_identity": identities[candidate_id],
                "model_checksum": model.canonical_model_checksum,
                "model_artifact": {
                    "path": f"pool/{candidate_id}.json",
                    "byte_length": len(model_bytes),
                    "sha256": study._sha(model_bytes),
                },
                "quantities": quantities,
                "material_estimate": estimate,
            }
        )
    alternatives = sorted(
        (row for row in pool if row["candidate_id"] != "baseline"),
        key=lambda row: (row["material_estimate"]["total"], row["candidate_id"]),
    )
    ordering = [row["candidate_id"] for row in alternatives]
    shortlist = ordering[: full_analysis_budget - 1]
    plan = {
        "schema_version": FORCE_FLOOR_PLAN,
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "baseline_checksum": original.canonical_model_checksum,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "control_request": request.to_dict(),
        "force_response_floor": floor,
        "history_limits": asdict(history_limits),
        "material_limits": asdict(material_limits),
        "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
        "prices": asdict(prices),
        "price_table_hash": prices.price_table_hash,
        "pool": pool,
        "plans": {"price_order": {"ordering": ordering, "shortlist": shortlist}},
        "full_analysis_budget_including_baseline": full_analysis_budget,
        "oracle_after_online_arm": True,
        "learned_policy_used": False,
        "independent_project_geometry_history_split": False,
        "line_search_assembly_reuse": reuse_line_search_assembly,
        "protocol_binding": protocol_binding,
    }
    plan["plan_hash"] = study._sha(study._bytes(plan))
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    study._save(root, "plan.json", study._bytes(plan))
    for row in pool:
        model = models[row["candidate_id"]]
        study._save(
            root, row["model_artifact"]["path"], study._bytes(model.canonical_payload())
        )
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    comparisons = {}
    arms = {}

    def execute(name: str, selected_ids: list[str]) -> dict:
        study._save(
            root,
            f"{name}-started.json",
            study._bytes(
                {
                    "status": "started",
                    "plan_hash": plan["plan_hash"],
                    "candidate_ids": ["baseline", *selected_ids],
                    "unknown_work_until_outcome": True,
                }
            ),
        )
        wall, cpu = perf_counter_ns(), process_time_ns()
        try:
            comparison = study.compare_rc_control_designs(
                original,
                tuple(by_id[candidate_id] for candidate_id in selected_ids),
                request,
                history_limits=history_limits,
                material_limits=material_limits,
                terminal_limits=terminal_limits,
                prices=prices,
                source_revision=source_revision,
                output_directory=root / name,
                force_response_floor=floor,
                reuse_line_search_assembly=reuse_line_search_assembly,
            )
        except BaseException as error:
            study._save(
                root,
                f"{name}-outcome.json",
                study._bytes(
                    {
                        "status": "interrupted"
                        if isinstance(error, KeyboardInterrupt)
                        else "raised",
                        "exception_kind": type(error).__name__,
                        "unknown_work_until_outcome": True,
                        "wall_ns": perf_counter_ns() - wall,
                        "cpu_ns": process_time_ns() - cpu,
                    }
                ),
            )
            raise
        work = _work(comparison)
        outcome = {
            "status": "completed",
            "comparison_hash": comparison["report_hash"],
            "comparison_path": f"{name}/comparison.json",
            "request_count": len(comparison["rows"]),
            "selected_candidate_id": comparison["selected_candidate_id"],
            "wall_ns": perf_counter_ns() - wall,
            "cpu_ns": process_time_ns() - cpu,
            "execution_work": work,
            "unknown_work_until_outcome": work["unknown_work"],
        }
        study._save(root, f"{name}-outcome.json", study._bytes(outcome))
        if work["unknown_work"]:
            raise ValueError("unknown numerical work; stop before another comparison")
        comparisons[name] = comparison
        return outcome

    arms["price_order"] = execute("price_order", shortlist)
    oracle = execute("exhaustive_oracle", ordering)
    cost_audit = candidate_cost_optimality_audit(plan, comparisons)
    report = {
        "schema_version": SEARCH_SCHEMA,
        "source_revision": source_revision,
        "plan_hash": plan["plan_hash"],
        "force_response_floor": floor,
        "candidate_denominator": len(pool),
        "arms": arms,
        "oracle": oracle,
        "candidate_cost_optimality_audit": cost_audit,
        "online_and_oracle_wall_ns": perf_counter_ns() - started_wall,
        "online_and_oracle_cpu_ns": process_time_ns() - started_cpu,
        "timing_scope": "preflight_price_order_online_full_reference_then_separate_full_pool_oracle_and_IO_excluding_final_report_write",
        "claims": {
            "known_pool_cost_optimality_only": True,
            "learned_policy_used": False,
            "net_ai_savings_proved": False,
            "independent_physical_validation": False,
            "confirmed_currency_savings": False,
            "workbench_search_review_integrated": False,
            "precommitted_protocol_independently_verified": False,
        },
    }
    design._finite_tree(report)
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "result.json", study._bytes(report))
    return report


def compare_rc_control_force_floor_learned_search(
    baseline: CanonicalModel,
    candidates: tuple[design.FiberFrameDesignCandidate, ...],
    request: BoundedRCFiberDirectControlRequest,
    *,
    force_response_floor: dict,
    policy,
    training_report: dict,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    prices: design.FiberFrameMaterialPrices,
    source_revision: str,
    output_directory: Path,
    full_analysis_budget: int,
    terminal_limits: design.FiberFrameTerminalLimits | None = None,
    reuse_line_search_assembly: bool = False,
    protocol_binding: dict | None = None,
) -> dict:
    """Freeze equal-budget price and signed-factor rankings before any solve.

    The learned prediction affects only order. Both online arms and the later
    complete-pool oracle use the same solver, screens, and fresh replay.
    """
    from structural_analysis.benchmark.rc_control_force_factor_learning import (
        FORCE_FACTOR_TRAINING_SCHEMA,
        FORCE_FACTOR_TARGETS,
        RCControlForceFactorPolicy,
        control_force_factor_features,
    )

    started_wall, started_cpu = perf_counter_ns(), process_time_ns()
    if type(baseline) is not CanonicalModel:
        raise ValueError("exact canonical baseline required")
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact direct-control request required")
    request = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(request.to_dict())
    )
    floor = study._validated_force_response_floor(
        force_response_floor, baseline, request
    )
    if floor is None:
        raise ValueError("prospective force-response floor required")
    if (
        type(candidates) is not tuple
        or not 1 <= len(candidates) <= 16
        or any(
            type(candidate) is not design.FiberFrameDesignCandidate
            for candidate in candidates
        )
    ):
        raise ValueError("one to sixteen exact canonical alternatives required")
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("unique candidate identities required")
    if (
        type(full_analysis_budget) is not int
        or not 2 <= full_analysis_budget <= len(candidates) + 1
    ):
        raise ValueError(
            "analysis budget must include baseline and one to all alternatives"
        )
    if type(policy) is not RCControlForceFactorPolicy:
        raise ValueError("exact signed force-factor policy required")
    if type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("one common explicit price table required")
    if (
        type(history_limits) is not design.FiberFrameHistoryLimits
        or type(material_limits) is not design.FiberFrameMaterialHistoryLimits
        or (
            terminal_limits is not None
            and type(terminal_limits) is not design.FiberFrameTerminalLimits
        )
    ):
        raise ValueError(
            "explicit full history, material, and optional terminal screens required"
        )
    if type(reuse_line_search_assembly) is not bool:
        raise ValueError("explicit boolean line-search assembly reuse required")
    if (
        type(source_revision) is not str
        or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None
    ):
        raise ValueError("full source revision required")
    if protocol_binding is not None:
        if type(protocol_binding) is not dict or set(protocol_binding) != {
            "protocol_commit",
            "protocol_path",
            "protocol_sha256",
            "input_sha256",
        }:
            raise ValueError("exact precommitted protocol binding required")
        if (
            type(protocol_binding["protocol_commit"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", protocol_binding["protocol_commit"])
            is None
            or type(protocol_binding["protocol_path"]) is not str
            or not protocol_binding["protocol_path"].startswith("examples/research/")
            or ".." in Path(protocol_binding["protocol_path"]).parts
            or type(protocol_binding["protocol_sha256"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", protocol_binding["protocol_sha256"])
            is None
            or type(protocol_binding["input_sha256"]) is not dict
            or set(protocol_binding["input_sha256"])
            != {
                "model",
                "request",
                "training_experiment",
                "experiment",
                "floor_plan",
                "learning_plan",
            }
            or any(
                type(value) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                for value in protocol_binding["input_sha256"].values()
            )
        ):
            raise ValueError("invalid precommitted protocol binding")
        protocol_binding = {
            **protocol_binding,
            "input_sha256": dict(protocol_binding["input_sha256"]),
        }

    p = policy.to_dict()
    if (
        type(training_report) is not dict
        or training_report.get("schema_version") != FORCE_FACTOR_TRAINING_SCHEMA
    ):
        raise ValueError("original signed force-factor training report required")
    training = json.loads(study._bytes(training_report))
    if training.get("report_hash") != study._sha(
        study._bytes(
            {key: value for key, value in training.items() if key != "report_hash"}
        )
    ):
        raise ValueError("training report hash mismatch")
    if (
        training.get("policy_hash") != policy.policy_hash
        or training.get("label_comparison_hash") != p["label_comparison_hash"]
        or training.get("force_response_floor") != floor
        or p["force_target"]
        != {
            "target_index": floor["target_index"],
            "target_control_displacement_m": floor["target_control_displacement_m"],
        }
        or training.get("sample_count") != len(p["training_sample_hashes"])
    ):
        raise ValueError("training report, policy, or indexed floor identity mismatch")
    fit = training.get("fit")
    invocations = training.get("label_invocations")
    if (
        type(fit) is not dict
        or fit.get("status") != "completed"
        or fit.get("unknown_fit_work_until_outcome") is not False
        or type(invocations) is not list
        or len(invocations) != 2 * training["sample_count"]
    ):
        raise ValueError("completed original and replay training work required")
    for value in (
        training.get("wall_ns"),
        training.get("cpu_ns"),
        training.get("label_generation_wall_ns"),
        fit.get("wall_ns"),
        fit.get("cpu_ns"),
    ):
        if type(value) is not int or value < 0:
            raise ValueError("known nonnegative historical training costs required")
    if (
        training["wall_ns"] < training["label_generation_wall_ns"]
        or training["wall_ns"] < fit["wall_ns"]
        or training["cpu_ns"] < fit["cpu_ns"]
    ):
        raise ValueError("training component timing exceeds enclosing total")
    if any(
        type(invocation) is not dict
        or invocation.get("unknown_execution_work") is not False
        or type(invocation.get("work")) is not dict
        for invocation in invocations
    ):
        raise ValueError("known historical training invocation work required")
    training_work = _work({"rows": [{"invocations": invocations}]})
    if training_work["unknown_work"]:
        raise ValueError("unknown historical training numerical work")
    frozen_policy = policy._json

    original = baseline.detached_analysis_snapshot()
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            candidate.candidate_id,
            tuple(
                design.FiberFrameSectionChange(**asdict(change))
                for change in candidate.changes
            ),
        )
        for candidate in candidates
    )
    models = {"baseline": original}
    for candidate in candidates:
        models[candidate.candidate_id] = design.apply_fiber_frame_section_changes(
            original, candidate
        )
    identities = {
        candidate_id: candidate_model_identity(model, experimental_pin_roller_beam=True)
        for candidate_id, model in models.items()
    }
    if len(set(identities.values())) != len(identities):
        raise ValueError("duplicate physical alternatives are not new candidates")
    if set(identities.values()) & set(p["training_model_identities"]):
        raise ValueError("training/evaluation physical model overlap")
    for model in models.values():
        _, context = control_force_factor_features(model, request, floor)
        if context != p["context_hash"]:
            raise ValueError("training/search indexed force-response context mismatch")

    pool = []
    for candidate_id, model in models.items():
        quantities = design.calculate_fiber_frame_member_quantities(
            model, experimental_pin_roller_beam=True
        )
        estimate = design._estimate(quantities, prices)
        model_bytes = study._bytes(model.canonical_payload())
        pool.append(
            {
                "candidate_id": candidate_id,
                "model_identity": identities[candidate_id],
                "model_checksum": model.canonical_model_checksum,
                "model_artifact": {
                    "path": f"pool/{candidate_id}.json",
                    "byte_length": len(model_bytes),
                    "sha256": study._sha(model_bytes),
                },
                "quantities": quantities,
                "material_estimate": estimate,
            }
        )
    alternatives = [row for row in pool if row["candidate_id"] != "baseline"]
    price_order = [
        row["candidate_id"]
        for row in sorted(
            alternatives,
            key=lambda row: (row["material_estimate"]["total"], row["candidate_id"]),
        )
    ]
    ranking_started = perf_counter_ns()
    predictions = []
    for row in alternatives:
        prediction = policy.predict(models[row["candidate_id"]], request, floor)
        if (
            type(prediction) is not dict
            or prediction.get("policy_hash") != policy.policy_hash
            or type(prediction.get("abstained")) is not bool
            or prediction.get("physical_result_authority") is not False
        ):
            raise ValueError(
                "signed force-factor prediction identity or authority invalid"
            )
        performance = prediction.get("performance")
        if prediction["abstained"]:
            if performance is not None:
                raise ValueError("abstained prediction has physical values")
            screens = None
            floor_status = "unavailable"
            tier = 1
        else:
            if (
                type(performance) is not dict
                or set(performance) != set(FORCE_FACTOR_TARGETS)
                or any(
                    type(value) not in (int, float) or not math.isfinite(value)
                    for value in performance.values()
                )
                or any(performance[key] < 0 for key in TARGETS)
            ):
                raise ValueError(
                    "complete finite signed force-factor prediction required"
                )
            screens = study._screens(
                performance, history_limits, material_limits, terminal_limits
            )
            factor = performance["load_factor_at_target"]
            minimum = floor["minimum_load_factor"]
            screens["load_factor_at_target"] = {
                "value": factor,
                "limit": minimum,
                "status": "pass" if factor >= minimum else "fail",
                "comparison": "at_least",
            }
            floor_status = "available"
            tier = (
                0
                if all(screen["status"] == "pass" for screen in screens.values())
                else 2
            )
        predictions.append(
            {
                "candidate_id": row["candidate_id"],
                "prediction": prediction,
                "predicted_screens": screens,
                "predicted_force_floor_status": floor_status,
                "ranking_tier": tier,
                "estimate": row["material_estimate"]["total"],
            }
        )
    learned_order, _ = candidate_ranking(predictions, LEGACY_RANKING)
    ranking_wall = perf_counter_ns() - ranking_started
    if policy._json != frozen_policy:
        raise ValueError("policy changed while ranking")
    plans = {
        name: {"ordering": order, "shortlist": order[: full_analysis_budget - 1]}
        for name, order in (
            ("price_order", price_order),
            ("learned_order", learned_order),
        )
    }
    policy_bytes = study._bytes(p)
    training_bytes = study._bytes(training)
    plan = {
        "schema_version": FORCE_FLOOR_LEARNED_PLAN,
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "baseline_checksum": original.canonical_model_checksum,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "control_request": request.to_dict(),
        "force_response_floor": floor,
        "history_limits": asdict(history_limits),
        "material_limits": asdict(material_limits),
        "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
        "prices": asdict(prices),
        "price_table_hash": prices.price_table_hash,
        "pool": pool,
        "plans": plans,
        "predictions": predictions,
        "ranking_strategy": LEGACY_RANKING,
        "policy_hash": policy.policy_hash,
        "training_report_hash": training["report_hash"],
        "policy_artifact": {
            "path": "policy.json",
            "byte_length": len(policy_bytes),
            "sha256": study._sha(policy_bytes),
        },
        "historical_training_artifact": {
            "path": "historical-training.json",
            "byte_length": len(training_bytes),
            "sha256": study._sha(training_bytes),
        },
        "full_analysis_budget_including_baseline_per_arm": full_analysis_budget,
        "oracle_after_online_arms": True,
        "learned_policy_used": True,
        "original_training_and_pool_models_disjoint": True,
        "independent_project_geometry_history_split": False,
        "line_search_assembly_reuse": reuse_line_search_assembly,
        "protocol_binding": protocol_binding,
    }
    plan["plan_hash"] = study._sha(study._bytes(plan))
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    study._save(root, "plan.json", study._bytes(plan))
    for row in pool:
        study._save(
            root,
            row["model_artifact"]["path"],
            study._bytes(models[row["candidate_id"]].canonical_payload()),
        )
    study._save(root, "policy.json", policy_bytes)
    study._save(root, "historical-training.json", training_bytes)

    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    comparisons = {}
    arms = {}

    def execute(name: str, selected_ids: list[str]) -> dict:
        study._save(
            root,
            f"{name}-started.json",
            study._bytes(
                {
                    "status": "started",
                    "plan_hash": plan["plan_hash"],
                    "candidate_ids": ["baseline", *selected_ids],
                    "unknown_work_until_outcome": True,
                }
            ),
        )
        wall, cpu = perf_counter_ns(), process_time_ns()
        try:
            comparison = study.compare_rc_control_designs(
                original,
                tuple(by_id[candidate_id] for candidate_id in selected_ids),
                request,
                history_limits=history_limits,
                material_limits=material_limits,
                terminal_limits=terminal_limits,
                prices=prices,
                source_revision=source_revision,
                output_directory=root / name,
                force_response_floor=floor,
                reuse_line_search_assembly=reuse_line_search_assembly,
            )
        except BaseException as error:
            study._save(
                root,
                f"{name}-outcome.json",
                study._bytes(
                    {
                        "status": "interrupted"
                        if isinstance(error, KeyboardInterrupt)
                        else "raised",
                        "exception_kind": type(error).__name__,
                        "unknown_work_until_outcome": True,
                        "wall_ns": perf_counter_ns() - wall,
                        "cpu_ns": process_time_ns() - cpu,
                    }
                ),
            )
            raise
        work = _work(comparison)
        selected = next(
            (
                row
                for row in comparison["rows"]
                if row["candidate_id"] == comparison["selected_candidate_id"]
            ),
            None,
        )
        outcome = {
            "status": "completed",
            "comparison_hash": comparison["report_hash"],
            "comparison_path": f"{name}/comparison.json",
            "request_count": len(comparison["rows"]),
            "selected_candidate_id": comparison["selected_candidate_id"],
            "selected_estimate": None
            if selected is None
            else selected["material_estimate"]["total"],
            "selected_full_reference_verified": selected is not None
            and selected["full_reference_verification_pass"],
            "wall_ns": perf_counter_ns() - wall,
            "cpu_ns": process_time_ns() - cpu,
            "execution_work": work,
            "unknown_work_until_outcome": work["unknown_work"],
        }
        study._save(root, f"{name}-outcome.json", study._bytes(outcome))
        if work["unknown_work"]:
            raise ValueError("unknown numerical work; stop before another comparison")
        comparisons[name] = comparison
        return outcome

    for name in ("price_order", "learned_order"):
        arms[name] = execute(name, plans[name]["shortlist"])
    oracle = execute("exhaustive_oracle", price_order)
    if policy._json != frozen_policy:
        raise ValueError("policy changed during full path verification")
    coverage = _coverage_audit(plan, comparisons["exhaustive_oracle"])
    coverage["schema_version"] = "rc-control-force-floor-candidate-coverage-audit.v2"
    coverage["force_response_floor"] = floor
    cost_audit = candidate_cost_optimality_audit(plan, comparisons)
    report = {
        "schema_version": LEARNED_SEARCH_SCHEMA,
        "source_revision": source_revision,
        "plan_hash": plan["plan_hash"],
        "force_response_floor": floor,
        "candidate_denominator": len(pool),
        "arms": arms,
        "oracle": oracle,
        "candidate_coverage_audit": coverage,
        "candidate_cost_optimality_audit": cost_audit,
        "ranking_wall_ns": ranking_wall,
        "historical_training_cost": training,
        "historical_training_execution_work": training_work,
        "historical_training_cost_counted_once_outside_online_arms": True,
        "online_and_oracle_wall_ns": perf_counter_ns() - started_wall,
        "online_and_oracle_cpu_ns": process_time_ns() - started_cpu,
        "timing_scope": "preflight_signed_factor_ranking_two_online_full_reference_arms_then_separate_oracle_and_IO_excluding_final_report_write",
        "claims": {
            "known_pool_cost_optimality_only": True,
            "learned_policy_used": True,
            "net_ai_savings_proved": False,
            "independent_physical_validation": False,
            "independent_generalization": False,
            "confirmed_currency_savings": False,
            "workbench_search_review_integrated": False,
            "precommitted_protocol_independently_verified": False,
        },
    }
    design._finite_tree(report)
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "result.json", study._bytes(report))
    return report
