"""Repeated, order-balanced comparisons of declared candidate pools.

Every comparison makes fresh online requests and, when enabled, its own later
oracle requests. Historical training costs are charged once per artifact, never
once per repetition. Hash bindings check local consistency, not provenance.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import math
import re
from statistics import median, pstdev
from time import perf_counter_ns
from typing import Any

from structural_analysis.ai.fiber_frame_candidate_learning import (
    CANDIDATE_FEATURE_PROFILE,
    FiberFrameCandidateTrainingResult,
    _source_revision,
    _validated_training_report,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    PHYSICAL_MODEL_IDENTITY_PROFILE,
)
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark.fiber_frame_candidate_search import (
    FiberFrameCandidateSearchResult,
    _audit_outcomes,
    _deterministic_plan,
    _learned_shortlist,
    _target_profile_binding,
    _validate_prediction_pool,
    _without_prediction_claims,
    _winner,
    compare_fiber_frame_candidate_search,
)
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameDesignComparison,
    FiberFrameHistoryLimits,
    FiberFrameMaterialHistoryLimits,
    FiberFrameMaterialPrices,
    FiberFrameTerminalLimits,
    apply_fiber_frame_section_changes,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel


STRATEGIES = ("deterministic", "learned")
SCHEMA_VERSION = "fiber-frame-candidate-search-suite.v1"
MATERIAL_SCHEMA_VERSION = "fiber-frame-candidate-search-suite.v2"


@dataclass(frozen=True)
class FiberFrameCandidateSearchCase:
    case_id: str
    baseline: CanonicalModel
    candidates: tuple[FiberFrameDesignCandidate, ...]
    training: FiberFrameCandidateTrainingResult
    prices: FiberFrameMaterialPrices
    terminal_limits: FiberFrameTerminalLimits
    config: PublicRCFiberFrameConfig = field(default_factory=PublicRCFiberFrameConfig)
    full_analysis_budget: int = 3
    exploration_slots: int = 1
    history_limits: FiberFrameHistoryLimits | None = None
    material_history_limits: FiberFrameMaterialHistoryLimits | None = None

    def __post_init__(self) -> None:
        if type(self.case_id) is not str or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", self.case_id
        ):
            raise ValueError("case_id must be a stable identifier")
        for value, expected in (
            (self.baseline, CanonicalModel),
            (self.training, FiberFrameCandidateTrainingResult),
            (self.prices, FiberFrameMaterialPrices),
            (self.terminal_limits, FiberFrameTerminalLimits),
            (self.config, PublicRCFiberFrameConfig),
        ):
            if type(value) is not expected:
                raise ValueError("exact typed case inputs required")
        candidates = tuple(self.candidates)
        if (
            not 1 <= len(candidates) <= 64
            or any(type(c) is not FiberFrameDesignCandidate for c in candidates)
            or len({c.candidate_id for c in candidates}) != len(candidates)
        ):
            raise ValueError("one to 64 uniquely identified candidates required")
        object.__setattr__(self, "candidates", candidates)
        if (
            type(self.full_analysis_budget) is not int
            or not 2 <= self.full_analysis_budget <= 65
        ):
            raise ValueError("full_analysis_budget must be in [2,65]")
        if (
            type(self.exploration_slots) is not int
            or not 0 <= self.exploration_slots < self.full_analysis_budget
        ):
            raise ValueError("exploration_slots must fit the candidate budget")
        if (
            self.history_limits is not None
            and type(self.history_limits) is not FiberFrameHistoryLimits
        ):
            raise ValueError("typed history limits required")
        if self.material_history_limits is not None and (
            type(self.material_history_limits) is not FiberFrameMaterialHistoryLimits
            or self.history_limits is None
        ):
            raise ValueError("typed material history limits require history limits")


@dataclass(frozen=True)
class FiberFrameCandidateSearchSuiteResult:
    status: str
    report_hash: str
    _report_json: str = field(repr=False)
    _comparison_snapshots: tuple[tuple[str, int, str, str], ...] = field(
        default=(), repr=False
    )

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._report_json)

    def design_comparison(
        self, case_id: str, arm_name: str, *, repetition: int = 0
    ) -> FiberFrameDesignComparison | None:
        """Copy one measured producer bundle without another analysis request."""
        if arm_name not in STRATEGIES or type(repetition) is not int or repetition < 0:
            raise ValueError(
                "valid strategy and nonnegative measured repetition required"
            )
        report = self.to_dict()
        if not any(
            row["case_id"] == case_id
            and row["repetition"] == repetition
            and row["phase"] == "measured"
            for row in report["runs"]
        ):
            raise ValueError("case/repetition not declared in this suite")
        for key, index, strategy, encoded in self._comparison_snapshots:
            if (key, index, strategy) == (case_id, repetition, arm_name):
                payload = json.loads(encoded)
                return FiberFrameDesignComparison(
                    payload["status"],
                    payload["report_hash"],
                    payload["experiment_identity_hash"],
                    payload,
                )
        return None


def _natural(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer cost or count required")
    return value


def _distribution(values: list[int]) -> dict[str, Any]:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "median": median(values) if values else None,
        "maximum": max(values) if values else None,
        "population_standard_deviation": pstdev(values) if values else None,
    }


def _validate_unrequested(row: dict[str, Any]) -> None:
    if (
        row["solver_executed"] is not False
        or row["full_reference_verification_pass"] is not False
        or row["result"] is not None
    ):
        raise ValueError(
            "unrequested candidate cannot carry execution or result credit"
        )


def _validate_history_row(row: dict[str, Any], binding: dict[str, Any]) -> None:
    """Check report consistency; source recovery belongs to the public producer."""
    if type(row.get("full_history_verification_pass")) is not bool:
        raise ValueError("history verification state required")
    if not row["full_history_verification_pass"]:
        if (
            row["history_limit_status"] != "unavailable"
            or row["response_history"] is not None
            or not row["history_failure"]
            or row["violated_history_limits"]
        ):
            raise ValueError("unavailable history cannot receive limit credit")
        return
    if row["full_reference_verification_pass"] is not True:
        raise ValueError("history requires full public reference verification")
    sidecar = row["response_history"]
    history = sidecar["history"]
    for report, key in ((sidecar, "report_hash"), (history, "history_hash")):
        if report[key] != canonical_hash({k: v for k, v in report.items() if k != key}):
            raise ValueError("history report hash mismatch")
    if (
        sidecar["schema_version"] != "public-rc-fiber-frame-response-history.v1"
        or sidecar["source_result_hash"] != row["result"]["result_hash"]
        or sidecar["canonical_model_checksum"] != row["model_checksum"]
        or sidecar["history_hash"] != history["history_hash"]
        or sidecar["status"] != "ready"
        or sidecar["contract_pass"] is not True
        or history["status"] != "ready"
        or history["contract_pass"] is not True
        or history["epoch_count"] != binding["configuration"]["load_steps"]
        or history["bindings"]["model_ir_content_hash"] != row["model_checksum"]
        or history["bindings"]["checkpoint_chain_hash"]
        != row["result"]["checkpoint"]["chain_hash"]
    ):
        raise ValueError("history source or coverage mismatch")
    if [step["epoch"] for step in history["steps"]] != list(
        range(1, history["epoch_count"] + 1)
    ):
        raise ValueError("history must retain every committed step")
    translation = max(
        math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
        for step in history["steps"]
        for node in step["node_displacements"]
    )
    strain = max(
        abs(fiber["strain"])
        for step in history["steps"]
        for fiber in step["fiber_results"]
    )
    violated = []
    for key, observed in (
        ("maximum_translation_m", translation),
        ("maximum_absolute_fiber_strain", strain),
    ):
        if (
            not math.isfinite(observed)
            or history["envelope"][key] != observed
            or row["performance"]["history_" + key] != observed
        ):
            raise ValueError("history envelope mismatch")
        if observed > binding["history_limits"][key]:
            violated.append("history_" + key)
    if (
        row["history_limit_status"] != ("fail" if violated else "pass")
        or row["violated_history_limits"] != violated
        or row["history_failure"] is not None
    ):
        raise ValueError("history limit status mismatch")


def _validate_material_history_row(
    row: dict[str, Any], binding: dict[str, Any]
) -> None:
    """Check stored material assertions and limits, without claiming source replay."""
    from structural_analysis.benchmark import (
        fiber_frame_constitutive_history as material,
    )
    from structural_analysis.benchmark.fiber_frame_design import (
        MATERIAL_HISTORY_METRICS,
    )

    def require(ok: bool, message: str) -> None:
        if not ok:
            raise ValueError("material history " + message)

    def same(a: Any, b: Any) -> bool:
        return canonical_hash(a) == canonical_hash(b)

    require("history_limits" in binding, "requires response history")
    limits = binding["material_history_limits"]
    require(
        type(limits) is dict
        and set(limits) == set(asdict(FiberFrameMaterialHistoryLimits(**limits))),
        "limit fields invalid",
    )
    require(
        type(row.get("full_material_history_verification_pass")) is bool,
        "verification state required",
    )
    if not row["full_material_history_verification_pass"]:
        require(
            row["constitutive_history"] is None
            and row["material_history_limit_status"] == "unavailable"
            and row["violated_material_history_limits"] == []
            and bool(row["material_history_failure"]),
            "unavailable scope cannot receive credit",
        )
        require(
            row["performance"] is None
            or not any(key in row["performance"] for key in MATERIAL_HISTORY_METRICS),
            "unavailable maxima cannot receive credit",
        )
        return
    require(
        row["full_reference_verification_pass"] is True
        and row["full_history_verification_pass"] is True,
        "requires verified public response history",
    )
    report = row["constitutive_history"]
    require(
        set(report)
        == {
            "schema_version",
            "status",
            "contract_pass",
            "bindings",
            "accepted_epoch_count",
            "states",
            "scope",
            "claim_boundary",
            "report_hash",
        },
        "report fields mismatch",
    )
    material.FiberFrameConstitutiveHistory(
        report["status"],
        report["contract_pass"],
        report["report_hash"],
        json.dumps(report, allow_nan=False),
    )
    require(
        same(
            report["scope"],
            {
                "validation": "existing_full_public_response_history_accessor_then_retained_material_memory_aggregation",
                "material_point": "member_integration_point_modeled_fiber_not_individual_bar",
                "state_value_counts": "strictly_positive_native_values_not_current_step_yield_events",
                "transition_counts": "exact_comparison_with_immediately_preceding_accepted_state",
                "total_energy": "original_per_epoch_engineering_recovery_MJ_not_density_or_epoch_sum",
            },
        ),
        "stored scope mismatch",
    )
    response, result = row["response_history"], row["result"]
    history = response["history"]
    expected_bindings = {
        "source_result_hash": result["result_hash"],
        "canonical_model_checksum": row["model_checksum"],
        "input_checksum": result["input_checksum"],
        "problem_contract_hash": result["contract_bindings"]["problem_contract_hash"],
        "checkpoint_chain_hash": result["checkpoint"]["chain_hash"],
        "checkpoint_artifact_hash": result["checkpoint"]["artifact_hash"],
        "checkpoint_artifact_byte_length": result["checkpoint"]["artifact_byte_length"],
        "response_history_report_hash": response["report_hash"],
        "engineering_history_hash": history["history_hash"],
    }
    require(same(report["bindings"], expected_bindings), "source bindings mismatch")
    epochs = binding["configuration"]["load_steps"]
    states = report["states"]
    require(
        type(report["accepted_epoch_count"]) is int
        and report["accepted_epoch_count"] == epochs
        and type(states) is list
        and len(states) == epochs + 1,
        "full accepted coverage required",
    )
    prior_hash = None
    for index, state in enumerate(states):
        engineering = history["steps"][index - 1] if index else None
        require(
            type(state["epoch"]) is int
            and type(state["step_index"]) is int
            and state["epoch"] == state["step_index"] == index,
            "epoch order mismatch",
        )
        require(
            same(state["load_factor"], index / epochs)
            and state["parent_checkpoint_state_hash"] == prior_hash,
            "load or parent chain mismatch",
        )
        expected_hash = (
            result["checkpoint"]["root_state_hash"]
            if index == 0
            else engineering["bindings"]["checkpoint_state_hash"]
        )
        require(
            state["checkpoint_state_hash"] == expected_hash,
            "checkpoint identity mismatch",
        )
        require(
            same(
                state["engineering_recovery_hash"],
                engineering["recovery_hash"] if index else None,
            )
            and same(
                state["total_dissipated_energy_mj"],
                engineering["metrics"]["total_dissipated_energy_mj"] if index else None,
            ),
            "engineering recovery binding mismatch",
        )
        require(
            state["engineering_recovery_reason"]
            == (None if index else "genesis_has_no_engineering_recovery"),
            "recovery availability mismatch",
        )
        if index:
            require(
                engineering["bindings"]["parent_checkpoint_state_hash"] == prior_hash,
                "response history parent mismatch",
            )
        prior_hash = state["checkpoint_state_hash"]
        fibers = (engineering or history["steps"][0])["fiber_results"]
        require(
            type(state["material_point_count"]) is int
            and state["material_point_count"] == len(fibers) > 0
            and set(state["materials"]) == set(material._FIELDS),
            "point coverage mismatch",
        )
        for kind, fields in material._FIELDS.items():
            group = state["materials"][kind]
            count = _natural(group["point_count"])
            require(
                count == sum(f["material_kind"] == kind for f in fibers) > 0
                and set(group["fields"]) == set(fields),
                "native field coverage mismatch",
            )
            for field_name, (unit, meaning) in fields.items():
                stats = group["fields"][field_name]
                require(
                    set(stats)
                    == {
                        "unit",
                        "interpretation",
                        "minimum",
                        "maximum",
                        "maximum_absolute",
                        "positive_value_point_count",
                        "changed_from_parent_point_count",
                        "increased_from_parent_point_count",
                        "decreased_from_parent_point_count",
                        "parent_comparison_reason",
                    },
                    "native statistics fields mismatch",
                )
                require(
                    stats["unit"] == unit and stats["interpretation"] == meaning,
                    "native field meaning mismatch",
                )
                values = [stats[k] for k in ("minimum", "maximum", "maximum_absolute")]
                require(
                    all(type(v) is float and math.isfinite(v) for v in values)
                    and values[0] <= values[1]
                    and values[2] == max(abs(values[0]), abs(values[1])),
                    "native extrema invalid",
                )
                require(
                    _natural(stats["positive_value_point_count"]) <= count,
                    "positive point count invalid",
                )
                positive = stats["positive_value_point_count"]
                require(
                    (values[1] > 0.0) is (positive > 0)
                    and (values[0] > 0.0) is (positive == count),
                    "positive counts contradict extrema",
                )
                if field_name not in ("plastic_strain", "backstress_mpa"):
                    require(values[0] >= 0.0, "cumulative native value negative")
                    if index:
                        previous = states[index - 1]["materials"][kind]["fields"][
                            field_name
                        ]
                        require(
                            values[0] >= previous["minimum"]
                            and values[1] >= previous["maximum"]
                            and stats["positive_value_point_count"]
                            >= previous["positive_value_point_count"]
                            and stats["decreased_from_parent_point_count"] == 0,
                            "cumulative native memory decreased",
                        )
                if field_name in ("tensile_damage", "compressive_damage"):
                    require(values[1] <= 1.0, "damage outside unit interval")
                changes = [
                    stats[k + "_from_parent_point_count"]
                    for k in ("changed", "increased", "decreased")
                ]
                require(
                    stats["parent_comparison_reason"]
                    == (None if index else "genesis_has_no_parent"),
                    "parent count availability mismatch",
                )
                require(
                    all(value is None for value in changes)
                    if not index
                    else all(_natural(value) <= count for value in changes)
                    and changes[0] == changes[1] + changes[2],
                    "parent change counts invalid",
                )
    require(
        prior_hash == result["checkpoint"]["terminal_state_hash"],
        "terminal checkpoint mismatch",
    )
    violated = []
    for metric, (limit, kind, field_name) in MATERIAL_HISTORY_METRICS.items():
        maximum = max(
            state["materials"][kind]["fields"][field_name]["maximum"]
            for state in states[1:]
        )
        require(same(row["performance"][metric], maximum), "accepted maximum mismatch")
        if maximum > limits[limit]:
            violated.append(metric)
    require(
        row["material_history_limit_status"] == ("fail" if violated else "pass")
        and row["violated_material_history_limits"] == violated
        and row["material_history_failure"] is None,
        "limit decision mismatch",
    )


def _validate_report(
    report: dict[str, Any],
    binding: dict[str, Any],
    order: tuple[str, str],
    oracle: bool,
) -> None:
    if report.get("report_hash") != canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    ):
        raise ValueError("comparison report hash mismatch")
    expected = {
        "schema_version": "fiber-frame-candidate-search-comparison.v4"
        if "material_history_limits" in binding
        else "fiber-frame-candidate-search-comparison.v3"
        if "history_limits" in binding
        else "fiber-frame-candidate-search-comparison.v2",
        "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": CANDIDATE_FEATURE_PROFILE,
        "source_revision": binding["source_revision"],
        "configuration": binding["configuration"],
        "terminal_limits": binding["terminal_limits"],
        "price_basis": binding["price_basis"],
        "policy_artifact_hash": binding["policy_artifact_hash"],
        "training_report_hash": binding["training_report_hash"],
        "fixed_full_analysis_budget_per_arm": binding["full_analysis_budget"],
        "exploration_slots": binding["exploration_slots"],
        "execution_order": list(order),
        "baseline_included_in_budget": True,
        "declared_candidate_count": len(binding["candidates"]),
    }
    profile_key = "candidate_target_profile"
    if (profile_key in report) != (profile_key in binding):
        raise ValueError("candidate target profile presence mismatch")
    if profile_key in binding:
        expected[profile_key] = binding[profile_key]
    if "history_limits" in binding:
        expected["history_limits"] = binding["history_limits"]
    if "material_history_limits" in binding:
        expected["material_history_limits"] = binding["material_history_limits"]
        if (
            report["claims"]["material_history_limit_scope"]
            != "positive_committed_static_epoch_material_memory"
            or report["claims"]["predictor_material_history_safety_authority"]
            is not False
        ):
            raise ValueError("material history predictor authority mismatch")
    for key, value in expected.items():
        if canonical_hash(report.get(key)) != canonical_hash(value):
            raise ValueError(f"comparison declaration mismatch: {key}")
    pool = report["candidate_pool"]
    _validate_prediction_pool(pool, binding, predictions_required=True)
    if [
        {k: row[k] for k in ("candidate_id", "changes", "model_checksum")}
        for row in pool
    ] != binding["candidates"]:
        raise ValueError("candidate pool identity mismatch")
    arms = report["arms"]
    if [arm["strategy"] for arm in arms] != list(STRATEGIES):
        raise ValueError("comparison must retain both canonical strategy rows")
    if profile_key in binding:
        deterministic_ranking, deterministic_shortlist, _ = _deterministic_plan(
            pool, binding["full_analysis_budget"]
        )
        expected_plans = {
            "deterministic": (deterministic_ranking, deterministic_shortlist),
            "learned": _learned_shortlist(
                pool,
                binding["full_analysis_budget"] - 1,
                binding["exploration_slots"],
            ),
        }
        for arm in arms:
            ranking, shortlist = expected_plans[arm["strategy"]]
            if canonical_hash(
                (arm.get("ranking"), arm.get("shortlist"))
            ) != canonical_hash((ranking, shortlist)):
                raise ValueError(
                    f"{arm['strategy']} requested-scope ranking or shortlist mismatch"
                )
    shortlists = {arm["strategy"]: arm["shortlist"] for arm in arms}
    frozen_hash = canonical_hash(
        {
            "pool": pool,
            "shortlists": shortlists,
            "policy_hash": binding["policy_artifact_hash"],
        }
    )
    if report["frozen_shortlist_hash"] != frozen_hash:
        raise ValueError("frozen shortlist mismatch")
    pool_ids = [row["candidate_id"] for row in pool]
    online_requests = 0
    for arm in arms:
        shortlist = arm["shortlist"]
        if (
            len(shortlist) != len(set(shortlist))
            or not set(shortlist) <= set(pool_ids)
            or len(shortlist) >= binding["full_analysis_budget"]
            or arm["frozen_shortlist_hash"] != frozen_hash
            or arm["baseline"]["candidate_id"] != "baseline"
            or arm["baseline"]["model_checksum"] != binding["baseline_model_checksum"]
            or [row["candidate_id"] for row in arm["candidate_outcomes"]] != pool_ids
        ):
            raise ValueError("arm pool, baseline or budget mismatch")
        requested = [arm["baseline"]]
        for row, candidate in zip(
            arm["candidate_outcomes"], binding["candidates"], strict=True
        ):
            if row["analysis_requested"] is not (row["candidate_id"] in shortlist):
                raise ValueError("shortlist request coverage mismatch")
            if row["analysis_requested"]:
                if row["model_checksum"] != candidate["model_checksum"]:
                    raise ValueError("analyzed candidate identity mismatch")
                requested.append(row)
            else:
                _validate_unrequested(row)
        cost = arm["cost_accounting"]
        if "history_limits" in binding:
            for row in requested:
                _validate_history_row(row, binding)
        if "material_history_limits" in binding:
            from structural_analysis.benchmark.fiber_frame_candidate_search_arm import (
                _validate_bundle,
                _validate_requested_row,
            )

            for row in requested:
                _validate_requested_row(
                    row, row["candidate_id"], row["model_checksum"], binding
                )
            _validate_bundle(arm, requested, binding)
        for value in cost.values():
            _natural(value)
        if (
            arm["baseline"]["analysis_requested"] is not True
            or cost["baseline_analysis_request_count"] != 1
            or cost["candidate_analysis_request_count"] != len(shortlist)
            or cost["total_analysis_request_count"] != len(requested)
            or cost["known_solver_execution_count"]
            != sum(row["solver_executed"] is True for row in requested)
            or cost["unknown_solver_execution_count"]
            != sum(row["solver_executed"] is None for row in requested)
        ):
            raise ValueError("arm request accounting mismatch")
        if cost["charged_online_wall_ns"] != sum(
            cost[key]
            for key in (
                "shared_pool_preparation_charged_wall_ns",
                "inference_wall_ns",
                "shortlist_selection_wall_ns",
                "final_selection_wall_ns",
                "policy_setup_wall_ns",
                "full_reanalysis_wall_ns",
            )
        ):
            raise ValueError("arm charged time mismatch")
        winner = arm["final_selection"]
        if any(
            row["solver_executed"] is not None
            and type(row["solver_executed"]) is not bool
            for row in requested
        ):
            raise ValueError("solver execution state must be boolean or unknown")
        if winner != _winner(requested):
            raise ValueError("winner differs from verified material objective")
        if winner is not None and (
            not arm["baseline"]["full_reference_verification_pass"]
            or winner not in requested
            or winner["full_reference_verification_pass"] is not True
            or winner["terminal_limit_status"] != "pass"
        ):
            raise ValueError("winner lacks fresh verified terminal feasibility")
        if winner is not None:
            amount = winner["material_estimate"]["total"]
            if (
                type(amount) not in (int, float)
                or not math.isfinite(amount)
                or amount < 0
            ):
                raise ValueError(
                    "finite nonnegative verified material estimate required"
                )
        online_requests += len(requested)
    audit = report["oracle"]
    if (
        audit["executed"] is not oracle
        or audit["labels_available_to_online_selection"] is not False
    ):
        raise ValueError("oracle execution declaration mismatch")
    oracle_requests = 0
    if oracle:
        rows = audit["rows"]
        if [row["candidate_id"] for row in rows] != ["baseline", *pool_ids]:
            raise ValueError("oracle denominator mismatch")
        for row, checksum in zip(
            rows,
            [
                binding["baseline_model_checksum"],
                *(c["model_checksum"] for c in binding["candidates"]),
            ],
            strict=True,
        ):
            if row["analysis_requested"] is not (checksum is not None) or (
                checksum is not None and row["model_checksum"] != checksum
            ):
                raise ValueError("oracle model or request mismatch")
            if not row["analysis_requested"]:
                _validate_unrequested(row)
            elif "history_limits" in binding:
                _validate_history_row(row, binding)
                if "material_history_limits" in binding:
                    from structural_analysis.benchmark.fiber_frame_candidate_search_arm import (
                        _validate_requested_row,
                    )

                    _validate_requested_row(row, row["candidate_id"], checksum, binding)
        oracle_requests = sum(row["analysis_requested"] for row in rows)
        if any(
            row["solver_executed"] is not None
            and type(row["solver_executed"]) is not bool
            for row in rows
        ):
            raise ValueError("oracle solver state must be boolean or unknown")
        if (
            _natural(audit["full_analysis_request_count"]) != oracle_requests
            or _natural(audit["baseline_analysis_request_count"]) != 1
            or _natural(audit["candidate_analysis_request_count"])
            != oracle_requests - 1
            or _natural(audit["known_solver_execution_count"])
            != sum(row["solver_executed"] is True for row in rows)
            or _natural(audit["unknown_solver_execution_count"])
            != sum(row["solver_executed"] is None for row in rows)
        ):
            raise ValueError("oracle request accounting mismatch")
        _natural(audit["wall_ns"])
    elif any(
        audit[key] is not None
        for key in (
            "rows",
            "wall_ns",
            "full_analysis_request_count",
            "baseline_analysis_request_count",
            "candidate_analysis_request_count",
            "known_solver_execution_count",
            "unknown_solver_execution_count",
        )
    ):
        raise ValueError("unexecuted oracle must remain unavailable")
    cost = report["cost_accounting"]
    historical = binding["training_cost_accounting"]
    for key in ("data_generation_wall_ns", "training_wall_ns"):
        if _natural(cost[key]) != historical[key]:
            raise ValueError("training cost binding mismatch")
    if (
        _natural(cost["training_full_analysis_request_count"])
        != historical["full_analysis_request_count"]
        or _natural(cost["online_full_analysis_request_count"]) != online_requests
        or _natural(cost["total_analysis_request_count_including_training_and_oracle"])
        != online_requests + oracle_requests + historical["full_analysis_request_count"]
    ):
        raise ValueError("comparison request totals mismatch")
    actual_preparation = _natural(cost["actual_shared_preparation_wall_ns"])
    if any(
        arm["cost_accounting"]["shared_pool_preparation_charged_wall_ns"]
        != actual_preparation
        for arm in arms
    ):
        raise ValueError("shared preparation charge mismatch")
    unique_timed_work = (
        sum(arm["cost_accounting"]["charged_online_wall_ns"] for arm in arms)
        - actual_preparation
        + (audit["wall_ns"] or 0)
    )
    if _natural(cost["actual_comparison_wall_ns_including_oracle"]) < unique_timed_work:
        raise ValueError("comparison wall time cannot omit timed work")
    for arm in arms:
        expected_audit = _audit_outcomes(
            pool,
            arm["shortlist"],
            audit["rows"],
            "history_limits" in binding,
            "material_history_limits" in binding,
        )
        if arm["strategy"] == "deterministic":
            expected_audit = _without_prediction_claims(expected_audit)
        if arm["oracle_audit"] != expected_audit:
            raise ValueError("oracle audit classification mismatch")
    winners = [arm["final_selection"] for arm in arms]
    quality = bool(
        all(winners)
        and winners[1]["material_estimate"]["total"]
        <= winners[0]["material_estimate"]["total"]
    )
    saving = (
        arms[0]["cost_accounting"]["charged_online_wall_ns"]
        - arms[1]["cost_accounting"]["charged_online_wall_ns"]
    )
    observed_saving = report["observed_comparison"][
        "deterministic_minus_learned_charged_online_wall_ns"
    ]
    if type(observed_saving) is not int or observed_saving != saving:
        raise ValueError("paired time difference mismatch")
    if (
        report["observed_comparison"]["learned_verified_scoped_material_cost_not_worse"]
        is not quality
    ):
        raise ValueError("verified material objective comparison mismatch")
    if report["status"] != (
        "ready"
        if all(arm["final_selection"] is not None for arm in arms)
        else "blocked"
    ):
        raise ValueError("comparison status mismatch")


def benchmark_fiber_frame_candidate_search_suite(
    cases: Sequence[FiberFrameCandidateSearchCase],
    *,
    source_revision: str,
    repetitions: int = 2,
    warmups: int = 0,
    oracle_audit: bool = True,
    runner: Callable[..., FiberFrameCandidateSearchResult] | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> FiberFrameCandidateSearchSuiteResult:
    """Predeclare all pools, then alternate arm order within each case.

    An even repetition count balances first/second position. Warmups are separate
    attempts and costs; they cannot change a measured shortlist. Injected runners
    or clocks are contract-test facilities and never local timing evidence.
    """
    source_revision = _source_revision(source_revision)
    if (
        not isinstance(cases, Sequence)
        or not 1 <= len(cases) <= 64
        or any(type(case) is not FiberFrameCandidateSearchCase for case in cases)
    ):
        raise ValueError("one to 64 typed cases required")
    cases = tuple(cases)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("case IDs must be unique")
    if type(repetitions) is not int or not 2 <= repetitions <= 32 or repetitions % 2:
        raise ValueError("repetitions must be even and in [2,32]")
    if type(warmups) is not int or not 0 <= warmups <= 5:
        raise ValueError("warmups must be in [0,5]")
    if (
        type(oracle_audit) is not bool
        or not callable(clock_ns)
        or (runner is not None and not callable(runner))
    ):
        raise ValueError("boolean oracle and callable runner/clock required")
    started = _natural(clock_ns())
    snapshots, bindings, artifacts = [], [], {}
    for case in cases:
        baseline = case.baseline.detached_analysis_snapshot()
        training = deepcopy(case.training)
        report, _ = _validated_training_report(training)
        training_cost = {
            key: report["cost_accounting"][key]
            for key in (
                "data_generation_wall_ns",
                "training_wall_ns",
                "full_analysis_request_count",
            )
        }
        artifacts[report["report_hash"]] = training_cost
        candidates = []
        for candidate in case.candidates:
            try:
                checksum = apply_fiber_frame_section_changes(
                    baseline, candidate
                ).canonical_model_checksum
            except Exception:
                checksum = None
            candidates.append({**asdict(candidate), "model_checksum": checksum})
        bindings.append(
            {
                "case_id": case.case_id,
                "source_revision": source_revision,
                "baseline_model_checksum": baseline.canonical_model_checksum,
                "candidates": candidates,
                "configuration": asdict(case.config),
                "terminal_limits": asdict(case.terminal_limits),
                "price_basis": {
                    **asdict(case.prices),
                    "price_table_hash": case.prices.price_table_hash,
                },
                "full_analysis_budget": case.full_analysis_budget,
                "exploration_slots": case.exploration_slots,
                "policy_artifact_hash": training.policy.artifact_hash,
                "training_report_hash": report["report_hash"],
                "training_cost_accounting": training_cost,
                **_target_profile_binding(training.policy),
            }
        )
        if case.history_limits is not None:
            bindings[-1]["history_limits"] = asdict(case.history_limits)
        if case.material_history_limits is not None:
            bindings[-1]["material_history_limits"] = asdict(
                case.material_history_limits
            )
        snapshots.append((baseline, training))
    # JSON-normalize dataclass tuples before comparing with producer JSON rows.
    bindings = json.loads(json.dumps(bindings, allow_nan=False))
    preflight_wall = _natural(_natural(clock_ns()) - started)
    injected = runner is not None or clock_ns is not perf_counter_ns
    declaration = {
        "source_revision": source_revision,
        "cases": bindings,
        "repetitions": repetitions,
        "warmups": warmups,
        "oracle_audit": oracle_audit,
        "execution_schedule": "round_major_case_order_alternating_arms_by_round_plus_case_index",
        "runner_profile": "injected_contract_test"
        if runner is not None
        else "public_candidate_search",
        "clock_profile": "injected_contract_test"
        if clock_ns is not perf_counter_ns
        else "perf_counter_ns",
    }
    execute = compare_fiber_frame_candidate_search if runner is None else runner
    runs = []
    comparison_snapshots = []
    frozen_hashes: dict[str, str] = {}
    for phase, count in (("warmup", warmups), ("measured", repetitions)):
        for repetition in range(count):
            for index, (case, binding, (baseline, training)) in enumerate(
                zip(cases, bindings, snapshots, strict=True)
            ):
                order = (
                    STRATEGIES if (repetition + index) % 2 == 0 else STRATEGIES[::-1]
                )
                row = {
                    "case_id": case.case_id,
                    "phase": phase,
                    "repetition": repetition,
                    "execution_order": list(order),
                    "status": "error",
                    "report_contract_pass": False,
                    "failure": None,
                    "comparison_report": None,
                    "observed_attempt_wall_ns": None,
                }
                begin = _natural(clock_ns())
                try:
                    result = execute(
                        baseline.detached_analysis_snapshot(),
                        case.candidates,
                        training=deepcopy(training),
                        prices=case.prices,
                        terminal_limits=case.terminal_limits,
                        config=case.config,
                        source_revision=source_revision,
                        full_analysis_budget=case.full_analysis_budget,
                        exploration_slots=case.exploration_slots,
                        oracle_audit=oracle_audit,
                        arm_order=order,
                        **(
                            {"history_limits": case.history_limits}
                            if case.history_limits is not None
                            else {}
                        ),
                        **(
                            {"material_history_limits": case.material_history_limits}
                            if case.material_history_limits is not None
                            else {}
                        ),
                    )
                    if type(result) is not FiberFrameCandidateSearchResult:
                        raise ValueError("typed search result required")
                    payload = result.to_dict()
                    # A malformed non-finite report must not poison the suite's
                    # serializable failure record or drop later attempts.
                    canonical_hash(payload)
                    row["comparison_report"] = payload
                    _validate_report(payload, binding, order, oracle_audit)
                    previous = frozen_hashes.setdefault(
                        case.case_id, payload["frozen_shortlist_hash"]
                    )
                    if previous != payload["frozen_shortlist_hash"]:
                        raise ValueError(
                            "frozen ranking changed across attempts of one case"
                        )
                    if result.status != payload["status"]:
                        raise ValueError("result and report status mismatch")
                    if phase == "measured":
                        copied = []
                        for name in STRATEGIES:
                            comparison = result.design_comparison(name)
                            if comparison is not None:
                                copied.append(
                                    (
                                        case.case_id,
                                        repetition,
                                        name,
                                        json.dumps(
                                            comparison.to_dict(),
                                            sort_keys=True,
                                            allow_nan=False,
                                        ),
                                    )
                                )
                        comparison_snapshots.extend(copied)
                    row.update(status=payload["status"], report_contract_pass=True)
                except Exception as exc:
                    row["failure"] = {
                        "kind": "comparison_failed",
                        "exception_type": type(exc).__name__,
                        "detail": str(exc),
                    }
                row["observed_attempt_wall_ns"] = _natural(_natural(clock_ns()) - begin)
                runs.append(row)
    summaries = [
        _case_summary(binding, runs, repetitions, injected) for binding in bindings
    ]
    valid = [row for row in runs if row["report_contract_pass"]]
    complete = len(valid) == len(runs)
    historical_requests = sum(
        cost["full_analysis_request_count"] for cost in artifacts.values()
    )
    accounting = {}
    for phase in ("warmup", "measured"):
        phase_rows = [row for row in runs if row["phase"] == phase]
        valid_phase = [row for row in valid if row["phase"] == phase]
        observed_online = sum(
            row["comparison_report"]["cost_accounting"][
                "online_full_analysis_request_count"
            ]
            for row in valid_phase
        )
        observed_oracle = sum(
            row["comparison_report"]["oracle"]["full_analysis_request_count"] or 0
            for row in valid_phase
        )
        accounting[phase] = {
            "declared_comparisons": len(phase_rows),
            "valid_report_count": len(valid_phase),
            "unknown_request_comparisons": len(phase_rows) - len(valid_phase),
            "validated_online_request_subtotal": observed_online,
            "validated_oracle_request_subtotal": observed_oracle,
            "total_analysis_request_count": observed_online + observed_oracle
            if len(valid_phase) == len(phase_rows)
            else None,
            "observed_attempt_wall_ns": sum(
                row["observed_attempt_wall_ns"] for row in phase_rows
            ),
            "validated_comparison_wall_ns_including_oracle": sum(
                row["comparison_report"]["cost_accounting"][
                    "actual_comparison_wall_ns_including_oracle"
                ]
                for row in valid_phase
            ),
        }
    ready = complete and all(row["status"] == "ready" for row in runs)
    suite_wall = _natural(_natural(clock_ns()) - started)
    historical_generation = sum(
        cost["data_generation_wall_ns"] for cost in artifacts.values()
    )
    historical_fit = sum(cost["training_wall_ns"] for cost in artifacts.values())
    payload = {
        "schema_version": MATERIAL_SCHEMA_VERSION
        if any(case.material_history_limits is not None for case in cases)
        else SCHEMA_VERSION,
        "status": "ready" if ready else "incomplete",
        "declaration": declaration,
        "suite_identity_hash": canonical_hash(declaration),
        "runs": runs,
        "case_summaries": summaries,
        "cost_accounting": {
            "training_artifacts_charged_once": artifacts,
            "historical_training_cost_scope": "one_generation_and_fit_per_distinct_artifact_hash_reused_across_all_attempts",
            "historical_data_generation_wall_ns": historical_generation,
            "historical_training_wall_ns": historical_fit,
            "historical_training_analysis_request_count": historical_requests,
            "phases": accounting,
            "total_analysis_request_count_including_training_warmups_and_oracles": historical_requests
            + sum(
                phase["total_analysis_request_count"] for phase in accounting.values()
            )
            if complete
            else None,
            "preflight_wall_ns": preflight_wall,
            "suite_wall_ns_through_aggregation": suite_wall,
            "accounted_wall_ns_including_historical_generation_and_fit": historical_generation
            + historical_fit
            + suite_wall,
            "accounted_wall_scope": "historical_generation_fit_plus_current_suite_through_aggregation_excludes_final_encoding_io_and_resource_measurement",
            "io_wall_ns": None,
            "peak_memory_bytes": None,
        },
        "claims": {
            "all_declared_comparisons_retained": True,
            "declared_measured_execution_order_balanced_by_case": True,
            "report_contract_pass": complete,
            "local_timing_evidence_eligible": ready and not injected,
            "hashes_attest_provenance": False,
            "per_arm_times_include_shared_preparation_charge": True,
            "oracle_labels_available_to_online_selection": False,
            "independent_case_families_verified": False,
            "generalized_speedup_claimed": False,
            "full_history_limit_extrema_verified": False,
            "confirmed_construction_savings": False,
            "production_promotion_eligible": False,
        },
    }
    payload["report_hash"] = canonical_hash(payload)
    return FiberFrameCandidateSearchSuiteResult(
        payload["status"],
        payload["report_hash"],
        json.dumps(payload, sort_keys=True, allow_nan=False),
        tuple(comparison_snapshots),
    )


def _case_summary(
    binding: dict[str, Any],
    runs: list[dict[str, Any]],
    repetitions: int,
    injected: bool,
) -> dict[str, Any]:
    rows = [
        row
        for row in runs
        if row["case_id"] == binding["case_id"] and row["phase"] == "measured"
    ]
    valid = [row["comparison_report"] for row in rows if row["report_contract_pass"]]
    complete = len(valid) == repetitions and all(
        report["status"] == "ready" for report in valid
    )
    all_attempts_ready = all(
        row["report_contract_pass"] and row["status"] == "ready"
        for row in runs
        if row["case_id"] == binding["case_id"]
    )
    quality = complete and all(
        report["observed_comparison"]["learned_verified_scoped_material_cost_not_worse"]
        is True
        for report in valid
    )
    differences = [
        report["arms"][0]["cost_accounting"]["charged_online_wall_ns"]
        - report["arms"][1]["cost_accounting"]["charged_online_wall_ns"]
        for report in valid
    ]
    saving = median(differences) if differences else None
    historical = binding["training_cost_accounting"]
    audit_keys = (
        (
            "missed_feasible_count",
            "false_safe_count",
            "predicted_safe_unverifiable_count",
            "oracle_verified_candidate_count",
        )
        + (
            (
                "oracle_combined_verified_candidate_count",
                "oracle_combined_unverifiable_candidate_count",
            )
            if "history_limits" in binding
            else ()
        )
        + (
            ("combined_false_safe_count", "combined_predicted_safe_unverifiable_count")
            if "candidate_target_profile" in binding
            else ()
        )
    )
    return {
        "case_id": binding["case_id"],
        "declared_measured_comparisons": repetitions,
        "valid_report_count": len(valid),
        "ready_comparison_count": sum(report["status"] == "ready" for report in valid),
        "all_measured_comparisons_ready": complete,
        "all_warmup_and_measured_attempts_ready": all_attempts_ready,
        "distribution_scope": "all_valid_measured_reports_including_blocked_choices_failures_counted_separately",
        "charged_online_wall_ns_by_strategy": {
            name: _distribution(
                [
                    report["arms"][index]["cost_accounting"]["charged_online_wall_ns"]
                    for report in valid
                ]
            )
            for index, name in enumerate(STRATEGIES)
        },
        "paired_deterministic_minus_learned_wall_ns": _distribution(differences),
        "verified_selection_counts_by_strategy": {
            name: {
                candidate_id: sum(
                    report["arms"][index]["final_selection"] is not None
                    and report["arms"][index]["final_selection"]["candidate_id"]
                    == candidate_id
                    for report in valid
                )
                for candidate_id in (
                    "baseline",
                    *(row["candidate_id"] for row in binding["candidates"]),
                )
            }
            for index, name in enumerate(STRATEGIES)
        },
        "measured_oracle_audit": {
            "scope": "candidate_observations_across_repetitions_not_unique_physical_candidates",
            "declared_candidate_observations": repetitions * len(binding["candidates"]),
            "validated_candidate_observations": sum(
                len(report["candidate_pool"])
                for report in valid
                if report["oracle"]["executed"]
            ),
            "by_strategy": {
                name: {
                    key: sum(
                        report["arms"][index]["oracle_audit"][key] for report in valid
                    )
                    if len(valid) == repetitions
                    and all(
                        report["arms"][index]["oracle_audit"][key] is not None
                        for report in valid
                    )
                    else None
                    for key in audit_keys
                }
                for index, name in enumerate(STRATEGIES)
            },
        },
        "learned_verified_material_objective_not_worse_in_every_pair": quality,
        "projected_reuses_to_amortize_this_artifact": max(
            1,
            math.ceil(
                (historical["data_generation_wall_ns"] + historical["training_wall_ns"])
                / saving
            ),
        )
        if quality
        and all_attempts_ready
        and not injected
        and saving is not None
        and saving > 0
        else None,
        "projection_scope": "positive_median_paired_difference_all_pairs_ready_material_objective_not_worse_same_artifact_reused_no_pooled_case_projection",
        "break_even_is_observed_execution": False,
    }
