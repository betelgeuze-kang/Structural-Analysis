"""Budgeted deterministic/learned selection with fresh physical confirmation.

Exhaustive oracle labels are computed only after both online shortlists are
frozen and executed. They never rank candidates or authorize an online winner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
import json
import math
import sys
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


SEARCH_MATERIAL_HISTORY_SCHEMA = "fiber-frame-candidate-search-comparison.v4"
TERMINAL_TARGET_PROFILE = "terminal_response.v1"
HISTORY_TARGET_PROFILE = "terminal_and_committed_material_history.v1"
_COMBINED_FIELDS = (
    "predicted_history_safe",
    "predicted_material_history_safe",
    "predicted_requested_limits_safe",
    "predicted_requested_limit_ratio",
)
_HISTORY_TARGETS = (
    "history_maximum_translation_m",
    "history_maximum_absolute_fiber_strain",
    "history_maximum_steel_accumulated_plastic_strain",
    "history_maximum_concrete_tensile_damage",
    "history_maximum_concrete_compressive_damage",
)


def _target_profile_binding(policy) -> dict[str, str]:
    profile = getattr(policy, "target_profile", TERMINAL_TARGET_PROFILE)
    if profile not in (TERMINAL_TARGET_PROFILE, HISTORY_TARGET_PROFILE):
        raise ValueError("unsupported candidate target profile")
    return (
        {"candidate_target_profile": profile}
        if profile == HISTORY_TARGET_PROFILE
        else {}
    )


def _finite_limit_ratio(value: float, limit: float) -> float:
    # This finite saturation is a ranking representation, never the safety gate.
    if limit == 0.0:
        return 0.0 if value == 0.0 else sys.float_info.max
    return min(value / limit, sys.float_info.max)


def _requested_prediction_fields(prediction, terminal, history, material):
    values = {key: None for key in _COMBINED_FIELDS}
    values.update(predicted_terminal_safe=None, predicted_limit_ratio=None)
    if prediction is None:
        return values
    if (
        type(prediction) is not dict
        or prediction.get("target_profile") != HISTORY_TARGET_PROFILE
        or set(prediction)
        != {
            "maximum_translation_m",
            "maximum_absolute_fiber_strain",
            "ood",
            "reason",
            "uncertainty_kind",
            "physical_result_authority",
            "target_profile",
            "history_prediction",
        }
        or type(prediction["ood"]) is not bool
        or prediction["physical_result_authority"] is not False
        or prediction["uncertainty_kind"]
        != "uncalibrated_feature_range_indicator_not_probability"
        or type(prediction["reason"]) is not str
    ):
        raise ValueError("candidate prediction target profile/fields mismatch")
    if prediction["ood"]:
        if any(
            prediction[key] is not None
            for key in (
                "maximum_translation_m",
                "maximum_absolute_fiber_strain",
                "history_prediction",
            )
        ):
            raise ValueError("OOD prediction must preserve unavailable targets")
        return values
    hp = prediction["history_prediction"]
    if type(hp) is not dict or set(hp) != set(_HISTORY_TARGETS):
        raise ValueError("candidate history prediction fields mismatch")
    all_values = [
        prediction["maximum_translation_m"],
        prediction["maximum_absolute_fiber_strain"],
        *hp.values(),
    ]
    if any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
        for value in all_values
    ):
        raise ValueError("candidate prediction targets must be finite and nonnegative")
    if (
        hp["history_maximum_translation_m"] < prediction["maximum_translation_m"]
        or hp["history_maximum_absolute_fiber_strain"]
        < prediction["maximum_absolute_fiber_strain"]
        or hp["history_maximum_concrete_tensile_damage"] > 1.0
        or hp["history_maximum_concrete_compressive_damage"] > 1.0
    ):
        raise ValueError("candidate history prediction range inconsistent")
    groups = [
        (
            "predicted_terminal_safe",
            [
                (
                    prediction["maximum_translation_m"],
                    terminal["maximum_translation_m"],
                ),
                (
                    prediction["maximum_absolute_fiber_strain"],
                    terminal["maximum_absolute_fiber_strain"],
                ),
            ],
        )
    ]
    if history is not None:
        groups.append(
            (
                "predicted_history_safe",
                [
                    (hp[key], history[key.removeprefix("history_")])
                    for key in _HISTORY_TARGETS[:2]
                ],
            )
        )
    if material is not None:
        groups.append(
            (
                "predicted_material_history_safe",
                [
                    (hp[key], material[key.removeprefix("history_")])
                    for key in _HISTORY_TARGETS[2:]
                ],
            )
        )
    ratios = []
    for name, pairs in groups:
        values[name] = all(value <= limit for value, limit in pairs)
        ratio = max(_finite_limit_ratio(value, limit) for value, limit in pairs)
        ratios.append(ratio)
        if name == "predicted_terminal_safe":
            values["predicted_limit_ratio"] = ratio
    values["predicted_requested_limits_safe"] = all(values[name] for name, _ in groups)
    values["predicted_requested_limit_ratio"] = max(ratios)
    return values


def _validate_prediction_pool(pool, binding, *, predictions_required=False):
    profile = binding.get("candidate_target_profile")
    if "candidate_target_profile" in binding and profile != HISTORY_TARGET_PROFILE:
        raise ValueError("candidate target profile binding mismatch")
    for row in pool:
        prediction = row.get("prediction")
        if profile is None:
            if any(key in row for key in _COMBINED_FIELDS) or (
                isinstance(prediction, dict) and "target_profile" in prediction
            ):
                raise ValueError("unexpected candidate target profile")
            continue
        if (
            predictions_required
            and row["screening_status"] == "ready"
            and prediction is None
        ):
            raise ValueError("missing candidate history prediction")
        expected = _requested_prediction_fields(
            prediction,
            binding["terminal_limits"],
            binding.get("history_limits"),
            binding.get("material_history_limits"),
        )
        for key, value in expected.items():
            if key not in row or canonical_hash(row[key]) != canonical_hash(value):
                raise ValueError("candidate requested prediction mismatch: " + key)


def _without_prediction_claims(audit):
    result = dict(audit)
    result.update(
        false_safe_count=None,
        false_safe_candidate_ids=None,
        predicted_safe_unverifiable_count=None,
        predicted_safe_unverifiable_candidate_ids=None,
        false_safe_applicability="strategy_makes_no_predicted_safety_claim",
    )
    if "combined_false_safe_count" in result:
        result.update(
            combined_false_safe_count=None,
            combined_false_safe_candidate_ids=None,
            combined_predicted_safe_unverifiable_count=None,
            combined_predicted_safe_unverifiable_candidate_ids=None,
            combined_false_safe_applicability="strategy_makes_no_predicted_safety_claim",
        )
        for key in (
            "predicted_history_safety_available",
            "predicted_material_history_safety_available",
        ):
            if key in result:
                result[key] = False
        for key in (
            "predicted_history_safety_candidate_count",
            "predicted_material_history_safety_candidate_count",
            "predicted_requested_limits_safety_candidate_count",
        ):
            if key in result:
                result[key] = 0
    return result


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

    def safety(row):
        return (
            row["predicted_requested_limits_safe"]
            if "predicted_requested_limits_safe" in row
            else row["predicted_terminal_safe"]
        )

    def ratio(row):
        return (
            row["predicted_requested_limit_ratio"]
            if "predicted_requested_limit_ratio" in row
            else row["predicted_limit_ratio"]
        )

    ranked = sorted(
        valid,
        key=lambda row: (
            0 if safety(row) is True else 1 if safety(row) is None else 2,
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
            0 if safety(row) is None else 1,
            abs(ratio(row) - 1.0) if ratio(row) is not None else 0.0,
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
    history_limits: design.FiberFrameHistoryLimits | None = None,
    material_history_limits: design.FiberFrameMaterialHistoryLimits | None = None,
) -> dict[str, Any]:
    row = design._evaluate_design(
        candidate_id,
        model.detached_analysis_snapshot(),
        config,
        prices,
        limits,
        7850.0,
        **({"history_limits": history_limits} if history_limits is not None else {}),
        **(
            {"material_history_limits": material_history_limits}
            if material_history_limits is not None
            else {}
        ),
    )
    row["analysis_requested"] = True
    return row


def _winner(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not design._verified_for_requested_scopes(rows[0]):
        return None
    eligible = [
        row
        for row in rows
        if design._verified_for_requested_scopes(row)
        and design._requested_limits_pass(row)
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
    history_required: bool = False,
    material_history_required: bool = False,
) -> dict[str, Any]:
    if material_history_required and not history_required:
        raise ValueError("material history audit requires history scope")
    combined_profile = any("predicted_requested_limits_safe" in row for row in pool)
    extra = {}
    if combined_profile:
        extra = {
            "combined_false_safe_count": None,
            "combined_false_safe_candidate_ids": None,
            "combined_predicted_safe_unverifiable_count": None,
            "combined_predicted_safe_unverifiable_candidate_ids": None,
            "combined_false_safe_definition": "predicted_requested_limits_safe_but_verified_requested_limit_failure",
            "combined_predicted_safe_unverifiable_definition": "predicted_requested_limits_safe_without_all_requested_verification",
            "predicted_requested_limits_safety_candidate_count": sum(
                type(row.get("predicted_requested_limits_safe")) is bool for row in pool
            ),
        }
        for required, scope in (
            (history_required, "history"),
            (material_history_required, "material_history"),
        ):
            if required:
                count = sum(
                    type(row.get(f"predicted_{scope}_safe")) is bool for row in pool
                )
                extra[f"predicted_{scope}_safety_available"] = count > 0
                extra[f"predicted_{scope}_safety_candidate_count"] = count
    if oracle is None:
        missing = {
            "missed_feasible_count": None,
            "false_safe_count": None,
            "predicted_safe_unverifiable_count": None,
            "oracle_verified_candidate_count": None,
            "reason": "exhaustive_oracle_not_run",
        }
        if history_required:
            missing.update(
                oracle_combined_verified_candidate_count=None,
                oracle_combined_unverifiable_candidate_count=None,
                predicted_history_safety_available=False,
            )
        if material_history_required:
            missing["predicted_material_history_safety_available"] = False
        missing.update(extra)
        return missing
    actual = {
        row["candidate_id"]: row for row in oracle if row["candidate_id"] != "baseline"
    }
    missed, false_safe, unverifiable, known, combined_known = [], [], [], 0, 0
    combined_false_safe, combined_unverifiable = [], []
    for candidate in pool:
        key = candidate["candidate_id"]
        row = actual[key]
        combined_verified = (
            row["full_reference_verification_pass"] is True
            and (
                not history_required
                or row.get("full_history_verification_pass") is True
            )
            and (
                not material_history_required
                or row.get("full_material_history_verification_pass") is True
            )
        )
        if (
            combined_profile
            and candidate.get("predicted_requested_limits_safe") is True
        ):
            if not combined_verified:
                combined_unverifiable.append(key)
            elif (
                row["terminal_limit_status"] != "pass"
                or (history_required and row.get("history_limit_status") != "pass")
                or (
                    material_history_required
                    and row.get("material_history_limit_status") != "pass"
                )
            ):
                combined_false_safe.append(key)
        if row["full_reference_verification_pass"]:
            known += 1
            feasible = row["terminal_limit_status"] == "pass"
            history_verified = (
                not history_required
                or row.get("full_history_verification_pass") is True
            )
            if material_history_required:
                history_verified = (
                    history_verified
                    and row.get("full_material_history_verification_pass") is True
                )
            combined_known += int(history_verified)
            combined_feasible = (
                feasible
                and history_verified
                and (not history_required or row.get("history_limit_status") == "pass")
                and (
                    not material_history_required
                    or row.get("material_history_limit_status") == "pass"
                )
            )
            if combined_feasible and key not in shortlist:
                missed.append(key)
            if candidate["predicted_terminal_safe"] is True and not feasible:
                false_safe.append(key)
        elif candidate["predicted_terminal_safe"] is True:
            unverifiable.append(key)
    audit = {
        "missed_feasible_count": len(missed),
        "missed_feasible_candidate_ids": missed,
        "false_safe_count": len(false_safe),
        "false_safe_candidate_ids": false_safe,
        "predicted_safe_unverifiable_count": len(unverifiable),
        "predicted_safe_unverifiable_candidate_ids": unverifiable,
        "oracle_verified_candidate_count": known,
        "oracle_unverifiable_candidate_count": len(pool) - known,
        "false_safe_definition": "predicted_terminal_safe_but_verified_terminal_limit_failure",
        "missed_feasible_definition": "oracle_verified_terminal_history_and_material_history_feasible_candidate_not_in_shortlist"
        if material_history_required
        else "oracle_verified_terminal_and_committed_history_feasible_candidate_not_in_shortlist"
        if history_required
        else "oracle_verified_terminal_feasible_candidate_not_in_shortlist",
        "reason": "separate_exhaustive_oracle_with_unverifiable_cases_retained",
    }
    if history_required:
        audit.update(
            oracle_combined_verified_candidate_count=combined_known,
            oracle_combined_unverifiable_candidate_count=len(pool) - combined_known,
            predicted_history_safety_available=False,
        )
    if material_history_required:
        audit["predicted_material_history_safety_available"] = False
    if combined_profile:
        extra.update(
            combined_false_safe_count=len(combined_false_safe),
            combined_false_safe_candidate_ids=combined_false_safe,
            combined_predicted_safe_unverifiable_count=len(combined_unverifiable),
            combined_predicted_safe_unverifiable_candidate_ids=combined_unverifiable,
        )
        audit.update(extra)
    return audit


FIRST_VERIFIED_FEASIBLE = "first_verified_feasible"
SEARCH_STOP_SCHEMA = "fiber-frame-candidate-search-comparison.v5"


def _stop_binding(stop_mode):
    if stop_mode is not None and (
        type(stop_mode) is not str or stop_mode != FIRST_VERIFIED_FEASIBLE
    ):
        raise ValueError("unsupported candidate stop mode")
    return {"stop_mode": stop_mode} if stop_mode is not None else {}


def _with_unrequested_feasible(
    audit, pool, attempted_ids, oracle_rows, history_required, material_history_required
):
    """Retain planned-shortlist coverage and separately audit actual requests."""
    actual = _audit_outcomes(
        pool, attempted_ids, oracle_rows, history_required, material_history_required
    )
    return {
        **audit,
        "unrequested_feasible_count": actual["missed_feasible_count"],
        "unrequested_feasible_candidate_ids": actual.get(
            "missed_feasible_candidate_ids"
        ),
        "unrequested_feasible_definition": "oracle_verified_requested_limits_feasible_candidate_not_requested",
    }


def _validate_stop_execution(arm, binding):
    """Check the first feasible stop against retained, ordered original rows.

    Callers still validate every requested source/result and all unrequested
    no-result fields. This helper makes no prediction, solve or recovery call.
    """
    if binding.get("stop_mode") != FIRST_VERIFIED_FEASIBLE:
        raise ValueError("explicit first-verified-feasible binding required")
    execution = arm["execution"]
    attempted = execution["attempted_candidate_ids"]
    shortlist = arm["shortlist"]
    if (
        type(attempted) is not list
        or any(type(key) is not str for key in attempted)
        or len(attempted) > len(shortlist)
        or attempted != shortlist[: len(attempted)]
    ):
        raise ValueError("actual candidate requests must be a frozen shortlist prefix")
    outcomes = {row["candidate_id"]: row for row in arm["candidate_outcomes"]}
    if len(outcomes) != len(arm["candidate_outcomes"]):
        raise ValueError("candidate outcome identities must be unique")
    requested = [arm["baseline"], *(outcomes[key] for key in attempted)]
    baseline = requested[0]
    stop_id = None
    if not design._verified_for_requested_scopes(baseline):
        if attempted:
            raise ValueError(
                "unverified baseline cannot authorize candidate evaluation"
            )
        reason = "baseline_verification_unavailable"
    else:
        feasible_indices = [
            index
            for index, row in enumerate(requested)
            if _winner([baseline, row]) is not None
        ]
        if feasible_indices:
            first = feasible_indices[0]
            if first != len(requested) - 1:
                raise ValueError(
                    "evaluation continued after the first verified feasible row"
                )
            reason = "first_verified_feasible"
            stop_id = requested[first]["candidate_id"]
        else:
            if attempted != shortlist:
                raise ValueError(
                    "candidate evaluation stopped before feasibility or exhaustion"
                )
            reason = "planned_shortlist_exhausted"
    expected = {
        "stop_mode": FIRST_VERIFIED_FEASIBLE,
        "attempted_candidate_ids": attempted,
        "termination_reason": reason,
        "stop_candidate_id": stop_id,
        "unattempted_candidate_ids": shortlist[len(attempted) :],
        "unused_analysis_request_budget": binding["full_analysis_budget"]
        - len(requested),
        "selection_scope": "first_verified_feasible_in_frozen_evaluation_order",
        "global_material_optimality_verified": False,
    }
    if expected["unused_analysis_request_budget"] < 0 or canonical_hash(
        execution
    ) != canonical_hash(expected):
        raise ValueError("candidate stop receipt or unused budget mismatch")
    return requested


def _validate_search_inputs(
    baseline: CanonicalModel,
    candidates: Sequence[design.FiberFrameDesignCandidate],
    *,
    training: FiberFrameCandidateTrainingResult,
    prices: design.FiberFrameMaterialPrices,
    terminal_limits: design.FiberFrameTerminalLimits,
    source_revision: str,
    config: public_api.PublicRCFiberFrameConfig | None,
    full_analysis_budget: int,
    exploration_slots: int,
    history_limits: design.FiberFrameHistoryLimits | None,
    material_history_limits: design.FiberFrameMaterialHistoryLimits | None = None,
    stop_mode: str | None = None,
) -> tuple[
    tuple[design.FiberFrameDesignCandidate, ...],
    public_api.PublicRCFiberFrameConfig,
    str,
    dict[str, Any],
]:
    _stop_binding(stop_mode)
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
    if (
        history_limits is not None
        and type(history_limits) is not design.FiberFrameHistoryLimits
    ):
        raise ValueError("typed committed-history limits required")
    history_options = (
        {"history_limits": history_limits} if history_limits is not None else {}
    )
    design._validate_material_history_limits(history_limits, material_history_limits)
    if material_history_limits is not None:
        history_options["material_history_limits"] = material_history_limits
    source_revision = _source_revision(source_revision)
    if type(full_analysis_budget) is not int or not 2 <= full_analysis_budget <= 65:
        raise ValueError("full_analysis_budget must be in [2,65], including baseline")
    if (
        type(exploration_slots) is not int
        or not 0 <= exploration_slots < full_analysis_budget
    ):
        raise ValueError("exploration_slots must fit the candidate budget")
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
    return declared, cfg, source_revision, history_options


def _prepare_search_pool(baseline, declared, training, prices):
    """Validate frozen training membership and construct the unpredicted pool."""
    policy_setup_started = perf_counter_ns()
    training_report, train_identities = _validated_training_report(training)
    policy = training.policy
    target_binding = _target_profile_binding(policy)
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
            **({key: None for key in _COMBINED_FIELDS} if target_binding else {}),
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
    return (
        baseline,
        training_report,
        policy,
        policy_hash,
        pool,
        models,
        policy_setup_wall,
        preparation_wall,
    )


def _deterministic_plan(pool, full_analysis_budget):
    selection_started = perf_counter_ns()
    ordering = [
        row["candidate_id"]
        for row in sorted(
            (row for row in pool if row["screening_status"] == "ready"),
            key=lambda row: (row["preanalysis_material_estimate"], row["candidate_id"]),
        )
    ]
    shortlist = ordering[: full_analysis_budget - 1]
    selection_wall = perf_counter_ns() - selection_started
    return ordering, shortlist, selection_wall


def _predict_pool(
    pool,
    models,
    policy,
    cfg,
    terminal_limits,
    history_limits=None,
    material_history_limits=None,
):
    inference_started = perf_counter_ns()
    inference_count = 0
    target_binding = _target_profile_binding(policy)
    for row in pool:
        if row["screening_status"] != "ready":
            continue
        prediction = policy.predict(models[row["candidate_id"]], cfg)
        inference_count += 1
        row["prediction"] = prediction.to_dict()
        if target_binding:
            row.update(
                _requested_prediction_fields(
                    row["prediction"],
                    asdict(terminal_limits),
                    asdict(history_limits) if history_limits is not None else None,
                    asdict(material_history_limits)
                    if material_history_limits is not None
                    else None,
                )
            )
        elif not prediction.ood:
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
    return inference_count, inference_wall


def _execute_search_arm(
    *,
    name,
    ordering,
    shortlist,
    selection_wall,
    infer_wall,
    inference_count,
    baseline,
    declared_by_id,
    cfg,
    prices,
    terminal_limits,
    source_revision,
    history_options,
    pool,
    shortlist_hash,
    preparation_wall,
    policy_setup_charge_wall,
    stop_mode=None,
    full_analysis_budget=None,
):
    """Execute one fresh baseline and shortlist, preserving its producer bundle."""
    _stop_binding(stop_mode)
    if stop_mode is not None and (
        type(full_analysis_budget) is not int
        or not 2 <= full_analysis_budget <= 65
        or len(shortlist) >= full_analysis_budget
    ):
        raise ValueError("stop execution requires the full declared request budget")
    analysis_started = perf_counter_ns()
    comparison_payload = None
    comparison_encoded = None
    execution = None
    if stop_mode is not None:
        verified = [
            _fresh(
                "baseline", baseline, cfg, prices, terminal_limits, **history_options
            )
        ]
        attempted = []
        stop_id = None
        if not design._verified_for_requested_scopes(verified[0]):
            reason = "baseline_verification_unavailable"
        elif _winner(verified) is not None:
            reason, stop_id = "first_verified_feasible", "baseline"
        else:
            reason = "planned_shortlist_exhausted"
            for key in shortlist:
                model = design.apply_fiber_frame_section_changes(
                    baseline, declared_by_id[key]
                )
                verified.append(
                    _fresh(key, model, cfg, prices, terminal_limits, **history_options)
                )
                attempted.append(key)
                if _winner(verified) is not None:
                    reason, stop_id = "first_verified_feasible", key
                    break
        if attempted:
            identity = design._build_design_comparison_identity(
                baseline.canonical_model_checksum,
                tuple(declared_by_id[key] for key in attempted),
                [row["model_checksum"] for row in verified[1:]],
                cfg,
                prices=prices,
                terminal_limits=terminal_limits,
                history_limits=history_options.get("history_limits"),
                material_history_limits=history_options.get("material_history_limits"),
                source_revision=source_revision,
                rebar_density_kg_per_m3=7850.0,
            )
            comparison = design._assemble_design_comparison(
                identity,
                [
                    {
                        key: value
                        for key, value in row.items()
                        if key != "analysis_requested"
                    }
                    for row in verified
                ],
                prices=prices,
                started_ns=analysis_started,
            )
            comparison_payload = comparison.to_dict()
            comparison_encoded = json.dumps(
                comparison_payload, sort_keys=True, allow_nan=False
            )
            verified = comparison_payload["rows"]
            for row in verified:
                row["analysis_requested"] = True
        execution = {
            "stop_mode": stop_mode,
            "attempted_candidate_ids": attempted,
            "termination_reason": reason,
            "stop_candidate_id": stop_id,
            "unattempted_candidate_ids": shortlist[len(attempted) :],
            "unused_analysis_request_budget": full_analysis_budget - len(verified),
            "selection_scope": "first_verified_feasible_in_frozen_evaluation_order",
            "global_material_optimality_verified": False,
        }
    elif shortlist:
        comparison = design.compare_public_rc_fiber_frame_designs(
            baseline,
            tuple(declared_by_id[key] for key in shortlist),
            cfg,
            prices=prices,
            terminal_limits=terminal_limits,
            source_revision=source_revision,
            **history_options,
        )
        comparison_payload = comparison.to_dict()
        comparison_encoded = json.dumps(
            comparison_payload, sort_keys=True, allow_nan=False
        )
        verified = comparison_payload["rows"]
        for row in verified:
            row["analysis_requested"] = True
    else:
        verified = [
            _fresh(
                "baseline",
                baseline,
                cfg,
                prices,
                terminal_limits,
                **history_options,
            )
        ]
    analysis_wall = perf_counter_ns() - analysis_started
    final_selection_started = perf_counter_ns()
    winner = _winner(verified)
    difference = design._difference(verified[0], winner) if winner else None
    final_selection_wall = perf_counter_ns() - final_selection_started
    outcomes = {row["candidate_id"]: row for row in verified}
    arm = {
        "strategy": name,
        "ranking": ordering,
        "shortlist": shortlist,
        "frozen_shortlist_hash": shortlist_hash,
        "baseline": verified[0],
        "design_comparison": json.loads(comparison_encoded)
        if comparison_payload is not None
        else None,
        "design_comparison_unavailable_reason": None
        if comparison_payload is not None
        else "stopped_before_candidate_evaluation"
        if stop_mode is not None
        else "empty_shortlist_baseline_only",
        "candidate_outcomes": [
            outcomes.get(
                row["candidate_id"],
                {
                    "candidate_id": row["candidate_id"],
                    "status": "not_attempted_after_stop"
                    if stop_mode is not None and row["candidate_id"] in shortlist
                    else "not_shortlisted"
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
            "policy_setup_wall_ns": policy_setup_charge_wall,
            "full_reanalysis_wall_ns": analysis_wall,
            "baseline_analysis_request_count": 1,
            "candidate_analysis_request_count": len(verified) - 1,
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
            + policy_setup_charge_wall,
        },
    }
    if execution is not None:
        arm["execution"] = execution
    return arm, comparison_encoded


def _execute_search_oracle(
    baseline, cfg, prices, terminal_limits, history_options, pool, models
):
    oracle_started = perf_counter_ns()
    oracle_rows = [
        _fresh("baseline", baseline, cfg, prices, terminal_limits, **history_options)
    ]
    oracle_rows.extend(
        _fresh(
            row["candidate_id"],
            models[row["candidate_id"]],
            cfg,
            prices,
            terminal_limits,
            **history_options,
        )
        if row["candidate_id"] in models
        else _unavailable(row["candidate_id"], row["failure"])
        for row in pool
    )
    oracle_wall = perf_counter_ns() - oracle_started
    return oracle_rows, oracle_wall


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
    arm_order: Sequence[str] = ("deterministic", "learned"),
    history_limits: design.FiberFrameHistoryLimits | None = None,
    material_history_limits: design.FiberFrameMaterialHistoryLimits | None = None,
    stop_mode: str | None = None,
) -> FiberFrameCandidateSearchResult:
    """Each arm's fixed budget includes one fresh baseline analysis request."""
    declared, cfg, source_revision, history_options = _validate_search_inputs(
        baseline,
        candidates,
        training=training,
        prices=prices,
        terminal_limits=terminal_limits,
        source_revision=source_revision,
        config=config,
        full_analysis_budget=full_analysis_budget,
        exploration_slots=exploration_slots,
        history_limits=history_limits,
        material_history_limits=material_history_limits,
        stop_mode=stop_mode,
    )
    if type(oracle_audit) is not bool:
        raise ValueError("oracle_audit must be boolean")
    canonical_arm_order = ("deterministic", "learned")
    if (
        type(arm_order) not in (tuple, list)
        or len(arm_order) != 2
        or any(type(name) is not str for name in arm_order)
        or set(arm_order) != set(canonical_arm_order)
    ):
        raise ValueError(
            "arm_order must contain deterministic and learned exactly once"
        )
    execution_order = tuple(arm_order)
    started = perf_counter_ns()
    (
        baseline,
        training_report,
        policy,
        policy_hash,
        pool,
        models,
        policy_setup_wall,
        preparation_wall,
    ) = _prepare_search_pool(baseline, declared, training, prices)
    deterministic_order, deterministic_shortlist, deterministic_selection_wall = (
        _deterministic_plan(pool, full_analysis_budget)
    )
    inference_count, inference_wall = _predict_pool(
        pool,
        models,
        policy,
        cfg,
        terminal_limits,
        history_limits,
        material_history_limits,
    )
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
        {
            "pool": pool,
            "shortlists": frozen_shortlists,
            "policy_hash": policy_hash,
            **_stop_binding(stop_mode),
        }
    )
    arms = []
    comparison_snapshots: list[tuple[str, str]] = []
    declared_by_id = {candidate.candidate_id: candidate for candidate in declared}
    arm_specifications = {
        "deterministic": (
            deterministic_order,
            deterministic_shortlist,
            deterministic_selection_wall,
            0,
        ),
        "learned": (
            learned_order,
            learned_shortlist,
            learned_selection_wall,
            inference_wall,
        ),
    }
    for name in execution_order:
        ordering, shortlist, selection_wall, infer_wall = arm_specifications[name]
        arm, encoded_comparison = _execute_search_arm(
            name=name,
            ordering=ordering,
            shortlist=shortlist,
            selection_wall=selection_wall,
            infer_wall=infer_wall,
            inference_count=inference_count,
            baseline=baseline,
            declared_by_id=declared_by_id,
            cfg=cfg,
            prices=prices,
            terminal_limits=terminal_limits,
            source_revision=source_revision,
            history_options=history_options,
            pool=pool,
            shortlist_hash=shortlist_hash,
            preparation_wall=preparation_wall,
            policy_setup_charge_wall=policy_setup_wall if name == "learned" else 0,
            **(
                {"stop_mode": stop_mode, "full_analysis_budget": full_analysis_budget}
                if stop_mode is not None
                else {}
            ),
        )
        arms.append(arm)
        if encoded_comparison is not None:
            comparison_snapshots.append((name, encoded_comparison))
    arms.sort(key=lambda arm: canonical_arm_order.index(arm["strategy"]))
    comparison_snapshots.sort(key=lambda row: canonical_arm_order.index(row[0]))
    # The optional oracle begins only after both online choices are final.
    oracle_rows, oracle_wall = None, None
    if oracle_audit:
        oracle_rows, oracle_wall = _execute_search_oracle(
            baseline, cfg, prices, terminal_limits, history_options, pool, models
        )
    for arm in arms:
        arm["oracle_audit"] = _audit_outcomes(
            pool,
            arm["shortlist"],
            oracle_rows,
            history_limits is not None,
            material_history_limits is not None,
        )
        if arm["strategy"] == "deterministic":
            # Deterministic ranking makes no predicted-safety claim.
            arm["oracle_audit"] = _without_prediction_claims(arm["oracle_audit"])
        if stop_mode is not None:
            arm["oracle_audit"] = _with_unrequested_feasible(
                arm["oracle_audit"],
                pool,
                arm["execution"]["attempted_candidate_ids"],
                oracle_rows,
                history_limits is not None,
                material_history_limits is not None,
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
        "schema_version": SEARCH_STOP_SCHEMA
        if stop_mode is not None
        else SEARCH_MATERIAL_HISTORY_SCHEMA
        if material_history_limits is not None
        else "fiber-frame-candidate-search-comparison.v3"
        if history_limits is not None
        else "fiber-frame-candidate-search-comparison.v2",
        "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": CANDIDATE_FEATURE_PROFILE,
        **_target_profile_binding(policy),
        **_stop_binding(stop_mode),
        "status": "ready" if complete else "blocked",
        "source_revision": source_revision,
        "policy_artifact_hash": policy_hash,
        "training_report_hash": training_report["report_hash"],
        "configuration": asdict(cfg),
        "terminal_limits": asdict(terminal_limits),
        "price_basis": {**asdict(prices), "price_table_hash": prices.price_table_hash},
        "fixed_full_analysis_budget_per_arm": full_analysis_budget,
        "execution_order": list(execution_order),
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
    if history_limits is not None:
        report["history_limits"] = asdict(history_limits)
        report["claims"].update(
            screen_limits_cover_all_committed_steps=True,
            history_limit_scope="positive_committed_static_epochs_only",
            predictor_history_safety_authority=False,
        )
    if material_history_limits is not None:
        report["material_history_limits"] = asdict(material_history_limits)
        report["claims"].update(
            material_history_limit_scope="positive_committed_static_epoch_material_memory",
            predictor_material_history_safety_authority=False,
        )
    report["report_hash"] = canonical_hash(report)
    return FiberFrameCandidateSearchResult(
        report["status"],
        json.dumps(report, sort_keys=True, allow_nan=False),
        tuple(comparison_snapshots),
    )
