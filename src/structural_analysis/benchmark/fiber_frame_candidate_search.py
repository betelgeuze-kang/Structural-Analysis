"""Budgeted deterministic/learned selection with fresh physical confirmation.

Exhaustive oracle labels are computed only after both online shortlists are
frozen and executed. They never rank candidates or authorize an online winner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
import json
import math
from time import perf_counter_ns
from typing import Any

from structural_analysis.ai.fiber_frame_candidate_learning import (
    CANDIDATE_FEATURE_PROFILE,
    FiberFrameCandidateTrainingResult,
    _source_revision,
    _validated_training_report,
    candidate_model_identity,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    PHYSICAL_MODEL_IDENTITY_PROFILE,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel


@dataclass(frozen=True)
class FiberFrameCandidateSearchResult:
    status: str
    _report_json: str = field(repr=False)
    _comparison_snapshots: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._report_json)

    def design_comparison(
        self, arm_name: str
    ) -> design.FiberFrameDesignComparison | None:
        """Copy a producer result saved by this run; this is not a JSON input loader."""
        if arm_name not in ("deterministic", "learned"):
            raise ValueError("arm_name must be deterministic or learned")
        encoded = dict(self._comparison_snapshots).get(arm_name)
        if encoded is None:
            return None
        payload = json.loads(encoded)
        return design.FiberFrameDesignComparison(
            payload["status"],
            payload["report_hash"],
            payload["experiment_identity_hash"],
            payload,
        )


def _learned_shortlist(
    pool: list[dict[str, Any]],
    budget: int,
    exploration_slots: int,
) -> tuple[list[str], list[str]]:
    valid = [row for row in pool if row["screening_status"] == "ready"]
    ranked = sorted(
        valid,
        key=lambda row: (
            0
            if row["predicted_terminal_safe"] is True
            else 1
            if row["predicted_terminal_safe"] is None
            else 2,
            row["preanalysis_material_estimate"],
            row["candidate_id"],
        ),
    )
    exploit_count = max(0, budget - exploration_slots)
    selected = ranked[:exploit_count]
    selected_ids = {row["candidate_id"] for row in selected}
    uncertain = sorted(
        (row for row in valid if row["candidate_id"] not in selected_ids),
        key=lambda row: (
            0 if row["predicted_terminal_safe"] is None else 1,
            abs(row["predicted_limit_ratio"] - 1.0)
            if row["predicted_limit_ratio"] is not None
            else 0.0,
            row["preanalysis_material_estimate"],
            row["candidate_id"],
        ),
    )
    selected.extend(uncertain[: max(0, budget - len(selected))])
    return [row["candidate_id"] for row in ranked], [
        row["candidate_id"] for row in selected
    ]


def _unavailable(candidate_id: str, failure: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "status": "unavailable_model",
        "full_reference_verification_pass": False,
        "terminal_limit_status": "unavailable",
        "material_estimate": None,
        "performance": None,
        "result": None,
        "quantities": None,
        "solver_executed": False,
        "failure": failure,
        "analysis_requested": False,
        "reference_and_quantity_wall_ns": 0,
    }


def _fresh(
    candidate_id: str,
    model: CanonicalModel,
    config: public_api.PublicRCFiberFrameConfig,
    prices: design.FiberFrameMaterialPrices,
    limits: design.FiberFrameTerminalLimits,
) -> dict[str, Any]:
    row = design._evaluate_design(
        candidate_id, model.detached_analysis_snapshot(), config, prices, limits, 7850.0
    )
    row["analysis_requested"] = True
    return row


def _winner(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows[0]["full_reference_verification_pass"]:
        return None
    eligible = [
        row
        for row in rows
        if row["full_reference_verification_pass"]
        and row["terminal_limit_status"] == "pass"
        and row["material_estimate"] is not None
    ]
    return (
        min(
            eligible,
            key=lambda row: (row["material_estimate"]["total"], row["candidate_id"]),
        )
        if eligible
        else None
    )


def _audit_outcomes(
    pool: list[dict[str, Any]],
    shortlist: list[str],
    oracle: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if oracle is None:
        return {
            "missed_feasible_count": None,
            "false_safe_count": None,
            "predicted_safe_unverifiable_count": None,
            "oracle_verified_candidate_count": None,
            "reason": "exhaustive_oracle_not_run",
        }
    actual = {
        row["candidate_id"]: row for row in oracle if row["candidate_id"] != "baseline"
    }
    missed, false_safe, unverifiable, known = [], [], [], 0
    for candidate in pool:
        key = candidate["candidate_id"]
        row = actual[key]
        if row["full_reference_verification_pass"]:
            known += 1
            feasible = row["terminal_limit_status"] == "pass"
            if feasible and key not in shortlist:
                missed.append(key)
            if candidate["predicted_terminal_safe"] is True and not feasible:
                false_safe.append(key)
        elif candidate["predicted_terminal_safe"] is True:
            unverifiable.append(key)
    return {
        "missed_feasible_count": len(missed),
        "missed_feasible_candidate_ids": missed,
        "false_safe_count": len(false_safe),
        "false_safe_candidate_ids": false_safe,
        "predicted_safe_unverifiable_count": len(unverifiable),
        "predicted_safe_unverifiable_candidate_ids": unverifiable,
        "oracle_verified_candidate_count": known,
        "oracle_unverifiable_candidate_count": len(pool) - known,
        "false_safe_definition": "predicted_terminal_safe_but_verified_terminal_limit_failure",
        "missed_feasible_definition": "oracle_verified_terminal_feasible_candidate_not_in_shortlist",
        "reason": "separate_exhaustive_oracle_with_unverifiable_cases_retained",
    }


def compare_fiber_frame_candidate_search(
    baseline: CanonicalModel,
    candidates: Sequence[design.FiberFrameDesignCandidate],
    *,
    training: FiberFrameCandidateTrainingResult,
    prices: design.FiberFrameMaterialPrices,
    terminal_limits: design.FiberFrameTerminalLimits,
    source_revision: str,
    config: public_api.PublicRCFiberFrameConfig | None = None,
    full_analysis_budget: int = 3,
    exploration_slots: int = 1,
    oracle_audit: bool = False,
) -> FiberFrameCandidateSearchResult:
    """Each arm's fixed budget includes one fresh baseline analysis request."""
    if (
        type(baseline) is not CanonicalModel
        or type(training) is not FiberFrameCandidateTrainingResult
        or training.status != "ready"
        or training.policy is None
    ):
        raise ValueError("baseline and ready trained candidate policy required")
    if (
        type(prices) is not design.FiberFrameMaterialPrices
        or type(terminal_limits) is not design.FiberFrameTerminalLimits
    ):
        raise ValueError("explicit scoped prices and terminal limits required")
    source_revision = _source_revision(source_revision)
    if type(full_analysis_budget) is not int or not 2 <= full_analysis_budget <= 65:
        raise ValueError("full_analysis_budget must be in [2,65], including baseline")
    if (
        type(exploration_slots) is not int
        or not 0 <= exploration_slots < full_analysis_budget
    ):
        raise ValueError("exploration_slots must fit the candidate budget")
    if type(oracle_audit) is not bool:
        raise ValueError("oracle_audit must be boolean")
    cfg = config or public_api.PublicRCFiberFrameConfig()
    if type(cfg) is not public_api.PublicRCFiberFrameConfig:
        raise ValueError("typed solver config required")
    declared = tuple(candidates)
    if (
        not 1 <= len(declared) <= 64
        or any(type(item) is not design.FiberFrameDesignCandidate for item in declared)
        or len({item.candidate_id for item in declared}) != len(declared)
    ):
        raise ValueError("one to 64 uniquely identified candidates required")
    started = perf_counter_ns()
    policy_setup_started = perf_counter_ns()
    training_report, train_identities = _validated_training_report(training)
    policy = training.policy
    policy_hash = policy.artifact_hash
    policy_setup_wall = perf_counter_ns() - policy_setup_started
    preparation_started = perf_counter_ns()
    baseline = baseline.detached_analysis_snapshot()
    if candidate_model_identity(baseline) in train_identities:
        raise ValueError("online baseline overlaps a training-label physical model")
    pool, models = [], {}
    physical_ids = {candidate_model_identity(baseline)}
    for candidate in declared:
        row = {
            "candidate_id": candidate.candidate_id,
            "changes": [asdict(change) for change in candidate.changes],
            "screening_status": "blocked",
            "model_checksum": None,
            "preanalysis_material_estimate": None,
            "prediction": None,
            "predicted_terminal_safe": None,
            "predicted_limit_ratio": None,
            "failure": None,
        }
        try:
            model = design.apply_fiber_frame_section_changes(baseline, candidate)
            # Keep constructible but unsupported cases available to the separate
            # full-analysis oracle, with no physical identity or ranking credit.
            models[candidate.candidate_id] = model
            row["model_checksum"] = model.canonical_model_checksum
            identity = candidate_model_identity(model)
            if identity in train_identities:
                raise ValueError(
                    "online candidate overlaps a training-label physical model"
                )
            if identity in physical_ids:
                raise ValueError("candidate pool repeats a physical model")
            physical_ids.add(identity)
            quantities = design.calculate_fiber_frame_member_quantities(model)
            estimate = design._estimate(quantities, prices)
            row.update(
                screening_status="ready",
                preanalysis_material_estimate=estimate["total"],
            )
        except ValueError as exc:
            if "overlaps a training-label" in str(
                exc
            ) or "repeats a physical model" in str(exc):
                raise
            row["failure"] = {
                "kind": "preanalysis_candidate_invalid",
                "exception_type": type(exc).__name__,
            }
        except Exception as exc:
            row["failure"] = {
                "kind": "preanalysis_candidate_failed",
                "exception_type": type(exc).__name__,
            }
        pool.append(row)
    preparation_wall = perf_counter_ns() - preparation_started
    selection_started = perf_counter_ns()
    deterministic_order = [
        row["candidate_id"]
        for row in sorted(
            (row for row in pool if row["screening_status"] == "ready"),
            key=lambda row: (row["preanalysis_material_estimate"], row["candidate_id"]),
        )
    ]
    deterministic_shortlist = deterministic_order[: full_analysis_budget - 1]
    deterministic_selection_wall = perf_counter_ns() - selection_started
    inference_started = perf_counter_ns()
    inference_count = 0
    for row in pool:
        if row["screening_status"] != "ready":
            continue
        prediction = policy.predict(models[row["candidate_id"]], cfg)
        inference_count += 1
        row["prediction"] = prediction.to_dict()
        if not prediction.ood:
            ratio = max(
                prediction.maximum_translation_m
                / terminal_limits.maximum_translation_m,
                prediction.maximum_absolute_fiber_strain
                / terminal_limits.maximum_absolute_fiber_strain,
            )
            if math.isfinite(ratio):
                row["predicted_limit_ratio"] = ratio
                row["predicted_terminal_safe"] = ratio <= 1.0
    inference_wall = perf_counter_ns() - inference_started
    selection_started = perf_counter_ns()
    learned_order, learned_shortlist = _learned_shortlist(
        pool, full_analysis_budget - 1, exploration_slots
    )
    learned_selection_wall = perf_counter_ns() - selection_started
    if policy.artifact_hash != policy_hash:
        raise ValueError("policy mutated during online ranking")
    frozen_shortlists = {
        "deterministic": deterministic_shortlist,
        "learned": learned_shortlist,
    }
    shortlist_hash = canonical_hash(
        {"pool": pool, "shortlists": frozen_shortlists, "policy_hash": policy_hash}
    )
    arms = []
    comparison_snapshots: list[tuple[str, str]] = []
    declared_by_id = {candidate.candidate_id: candidate for candidate in declared}
    for name, ordering, shortlist, selection_wall, infer_wall in (
        (
            "deterministic",
            deterministic_order,
            deterministic_shortlist,
            deterministic_selection_wall,
            0,
        ),
        (
            "learned",
            learned_order,
            learned_shortlist,
            learned_selection_wall,
            inference_wall,
        ),
    ):
        analysis_started = perf_counter_ns()
        comparison_payload = None
        if shortlist:
            comparison = design.compare_public_rc_fiber_frame_designs(
                baseline,
                tuple(declared_by_id[key] for key in shortlist),
                cfg,
                prices=prices,
                terminal_limits=terminal_limits,
                source_revision=source_revision,
            )
            comparison_payload = comparison.to_dict()
            comparison_snapshots.append(
                (name, json.dumps(comparison_payload, sort_keys=True, allow_nan=False))
            )
            verified = comparison_payload["rows"]
            for row in verified:
                row["analysis_requested"] = True
        else:
            verified = [_fresh("baseline", baseline, cfg, prices, terminal_limits)]
        analysis_wall = perf_counter_ns() - analysis_started
        final_selection_started = perf_counter_ns()
        winner = _winner(verified)
        difference = design._difference(verified[0], winner) if winner else None
        final_selection_wall = perf_counter_ns() - final_selection_started
        outcomes = {row["candidate_id"]: row for row in verified}
        arms.append(
            {
                "strategy": name,
                "ranking": ordering,
                "shortlist": shortlist,
                "frozen_shortlist_hash": shortlist_hash,
                "baseline": verified[0],
                "design_comparison": json.loads(dict(comparison_snapshots)[name])
                if comparison_payload is not None
                else None,
                "design_comparison_unavailable_reason": None
                if comparison_payload is not None
                else "empty_shortlist_baseline_only",
                "candidate_outcomes": [
                    outcomes.get(
                        row["candidate_id"],
                        {
                            "candidate_id": row["candidate_id"],
                            "status": "not_shortlisted"
                            if row["screening_status"] == "ready"
                            else "preanalysis_blocked",
                            "analysis_requested": False,
                            "solver_executed": False,
                            "result": None,
                            "full_reference_verification_pass": False,
                            "failure": row["failure"],
                        },
                    )
                    for row in pool
                ],
                "final_selection": winner,
                "selection_difference_from_baseline": difference,
                "cost_accounting": {
                    "shared_pool_preparation_charged_wall_ns": preparation_wall,
                    "inference_wall_ns": infer_wall,
                    "inference_count": inference_count if name == "learned" else 0,
                    "shortlist_selection_wall_ns": selection_wall,
                    "final_selection_wall_ns": final_selection_wall,
                    "policy_setup_wall_ns": policy_setup_wall
                    if name == "learned"
                    else 0,
                    "full_reanalysis_wall_ns": analysis_wall,
                    "baseline_analysis_request_count": 1,
                    "candidate_analysis_request_count": len(shortlist),
                    "total_analysis_request_count": len(verified),
                    "known_solver_execution_count": sum(
                        row["solver_executed"] is True for row in verified
                    ),
                    "unknown_solver_execution_count": sum(
                        row["solver_executed"] is None for row in verified
                    ),
                    "charged_online_wall_ns": preparation_wall
                    + infer_wall
                    + selection_wall
                    + analysis_wall
                    + final_selection_wall
                    + (policy_setup_wall if name == "learned" else 0),
                },
            }
        )
    # The optional oracle begins only after both online choices are final.
    oracle_rows, oracle_wall = None, None
    if oracle_audit:
        oracle_started = perf_counter_ns()
        oracle_rows = [_fresh("baseline", baseline, cfg, prices, terminal_limits)]
        oracle_rows.extend(
            _fresh(
                row["candidate_id"],
                models[row["candidate_id"]],
                cfg,
                prices,
                terminal_limits,
            )
            if row["candidate_id"] in models
            else _unavailable(row["candidate_id"], row["failure"])
            for row in pool
        )
        oracle_wall = perf_counter_ns() - oracle_started
    for arm in arms:
        arm["oracle_audit"] = _audit_outcomes(pool, arm["shortlist"], oracle_rows)
        if arm["strategy"] == "deterministic":
            # Deterministic ranking makes no predicted-safety claim.
            arm["oracle_audit"].update(
                false_safe_count=None,
                false_safe_candidate_ids=None,
                predicted_safe_unverifiable_count=None,
                predicted_safe_unverifiable_candidate_ids=None,
                false_safe_applicability="strategy_makes_no_predicted_safety_claim",
            )
    det, learned = arms
    saving = (
        det["cost_accounting"]["charged_online_wall_ns"]
        - learned["cost_accounting"]["charged_online_wall_ns"]
    )
    labels_cost = training_report["cost_accounting"]["data_generation_wall_ns"]
    train_cost = training_report["cost_accounting"]["training_wall_ns"]
    quality = bool(
        det["final_selection"]
        and learned["final_selection"]
        and learned["final_selection"]["material_estimate"]["total"]
        <= det["final_selection"]["material_estimate"]["total"]
    )
    complete = all(arm["final_selection"] is not None for arm in arms)
    report = {
        "schema_version": "fiber-frame-candidate-search-comparison.v2",
        "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": CANDIDATE_FEATURE_PROFILE,
        "status": "ready" if complete else "blocked",
        "source_revision": source_revision,
        "policy_artifact_hash": policy_hash,
        "training_report_hash": training_report["report_hash"],
        "configuration": asdict(cfg),
        "terminal_limits": asdict(terminal_limits),
        "price_basis": {**asdict(prices), "price_table_hash": prices.price_table_hash},
        "fixed_full_analysis_budget_per_arm": full_analysis_budget,
        "baseline_included_in_budget": True,
        "exploration_slots": exploration_slots,
        "declared_candidate_count": len(pool),
        "candidate_pool": pool,
        "frozen_shortlist_hash": shortlist_hash,
        "arms": arms,
        "oracle": {
            "executed": oracle_audit,
            "rows": oracle_rows,
            "wall_ns": oracle_wall,
            "labels_available_to_online_selection": False,
            "baseline_analysis_request_count": 1 if oracle_rows is not None else None,
            "candidate_analysis_request_count": sum(
                row["analysis_requested"] for row in oracle_rows[1:]
            )
            if oracle_rows is not None
            else None,
            "full_analysis_request_count": sum(
                row["analysis_requested"] for row in oracle_rows
            )
            if oracle_rows is not None
            else None,
            "known_solver_execution_count": sum(
                row["solver_executed"] is True for row in oracle_rows
            )
            if oracle_rows is not None
            else None,
            "unknown_solver_execution_count": sum(
                row["solver_executed"] is None for row in oracle_rows
            )
            if oracle_rows is not None
            else None,
        },
        "cost_accounting": {
            "data_generation_wall_ns": labels_cost,
            "training_wall_ns": train_cost,
            "training_full_analysis_request_count": training_report["cost_accounting"][
                "full_analysis_request_count"
            ],
            "actual_shared_preparation_wall_ns": preparation_wall,
            "online_full_analysis_request_count": sum(
                arm["cost_accounting"]["total_analysis_request_count"] for arm in arms
            ),
            "total_analysis_request_count_including_training_and_oracle": (
                training_report["cost_accounting"]["full_analysis_request_count"]
                + sum(
                    arm["cost_accounting"]["total_analysis_request_count"]
                    for arm in arms
                )
                + (
                    sum(row["analysis_requested"] for row in oracle_rows)
                    if oracle_rows is not None
                    else 0
                )
            ),
            "actual_comparison_wall_ns_including_oracle": perf_counter_ns() - started,
            "io_wall_ns": None,
            "peak_memory_bytes": None,
        },
        "observed_comparison": {
            "deterministic_minus_learned_charged_online_wall_ns": saving,
            "learned_verified_scoped_material_cost_not_worse": quality,
            "projected_reuses_to_amortize_data_and_training": max(
                1, math.ceil((labels_cost + train_cost) / saving)
            )
            if saving > 0 and quality
            else None,
            "break_even_is_observed_execution": False,
            "break_even_scope": "single_local_online_difference_projection_if_verified_material_objective_not_worse",
        },
        "claims": {
            "same_declared_candidate_pool": True,
            "all_declared_candidates_retained": True,
            "final_selection_requires_fresh_full_public_analysis": True,
            "screen_limits_cover_full_history_extrema": False,
            "terminal_limit_scope": "terminal_translation_and_fiber_strain_only",
            "study_scope": "local_synthetic_section_family_research",
            "source_revision_is_attestation": False,
            "independent_project_generalization_verified": False,
            "confirmed_construction_savings": False,
            "design_code_compliance": False,
            "generalized_speedup_claimed": False,
            "production_promotion_eligible": False,
        },
    }
    report["report_hash"] = canonical_hash(report)
    return FiberFrameCandidateSearchResult(
        report["status"],
        json.dumps(report, sort_keys=True, allow_nan=False),
        tuple(comparison_snapshots),
    )
