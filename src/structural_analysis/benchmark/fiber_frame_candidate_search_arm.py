"""Single candidate-search arms for separately measured fresh processes.

The ordinary comparison API keeps its schemas and scheduling. These reports
retain one actual arm and its original design bundle; a later parent joins the
arms and oracle. Hashes establish artifact consistency, never authentication.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import asdict
import json
import math
from time import perf_counter_ns
from typing import Any

from structural_analysis.ai.fiber_frame_candidate_learning import (
    CANDIDATE_FEATURE_PROFILE,
    FiberFrameCandidateTrainingResult,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    PHYSICAL_MODEL_IDENTITY_PROFILE,
)
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_candidate_search as core
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import (
    CanonicalModel,
    CoordinateSystem,
    UnitSystem,
)

ARM_SCHEMA_VERSION = "fiber-frame-candidate-search-arm.v1"
ORACLE_SCHEMA_VERSION = "fiber-frame-candidate-search-oracle.v1"
STRATEGIES = ("deterministic", "learned", "oracle")
CLAIMS = {
    "all_declared_candidates_retained": True,
    "fresh_baseline_in_each_execution": True,
    "training_reexecuted": False,
    "oracle_labels_available_to_online_selection": False,
    "predictor_history_safety_authority": False,
    "source_revision_is_attestation": False,
    "independent_validation": False,
    "generalized_speedup_claimed": False,
    "confirmed_construction_savings": False,
    "design_code_compliance": False,
    "production_promotion_eligible": False,
}
WORKLOAD_SCOPE = (
    "input_contract_frozen_training_validation_pool_preparation_ranking_and_"
    "full_analysis_through_final_selection_before_report_assembly"
)


def _normal(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _prepare(baseline, candidates, **kwargs):
    declared, cfg, revision, history_options = core._validate_search_inputs(
        baseline, candidates, **kwargs
    )
    values = core._prepare_search_pool(
        baseline, declared, kwargs["training"], kwargs["prices"]
    )
    (
        baseline,
        training_report,
        policy,
        policy_hash,
        pool,
        models,
        setup_wall,
        preparation_wall,
    ) = values
    binding = {
        "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": CANDIDATE_FEATURE_PROFILE,
        "source_revision": revision,
        "baseline_model_checksum": baseline.canonical_model_checksum,
        "candidates": [
            {
                "candidate_id": row["candidate_id"],
                "changes": row["changes"],
                "model_checksum": row["model_checksum"],
            }
            for row in pool
        ],
        "configuration": asdict(cfg),
        "terminal_limits": asdict(kwargs["terminal_limits"]),
        "price_basis": {
            **asdict(kwargs["prices"]),
            "price_table_hash": kwargs["prices"].price_table_hash,
        },
        "full_analysis_budget": kwargs["full_analysis_budget"],
        "exploration_slots": kwargs["exploration_slots"],
        "policy_artifact_hash": policy_hash,
        "training_report_hash": training_report["report_hash"],
        "training_cost_accounting": {
            key: training_report["cost_accounting"][key]
            for key in (
                "data_generation_wall_ns",
                "training_wall_ns",
                "full_analysis_request_count",
            )
        },
    }
    if kwargs["history_limits"] is not None:
        binding["history_limits"] = asdict(kwargs["history_limits"])
    return {
        **kwargs,
        "baseline": baseline,
        "declared": declared,
        "cfg": cfg,
        "source_revision": revision,
        "history_options": history_options,
        "policy": policy,
        "policy_hash": policy_hash,
        "pool": pool,
        "models": models,
        "setup_wall": setup_wall,
        "preparation_wall": preparation_wall,
        "input_binding": _normal(binding),
    }


def _plan(prepared, strategy):
    pool = deepcopy(prepared["pool"])
    inference_count = inference_wall = 0
    if strategy == "learned":
        inference_count, inference_wall = core._predict_pool(
            pool,
            prepared["models"],
            prepared["policy"],
            prepared["cfg"],
            prepared["terminal_limits"],
        )
        started = perf_counter_ns()
        ranking, shortlist = core._learned_shortlist(
            pool, prepared["full_analysis_budget"] - 1, prepared["exploration_slots"]
        )
        selection_wall = perf_counter_ns() - started
    elif strategy == "deterministic":
        ranking, shortlist, selection_wall = core._deterministic_plan(
            pool, prepared["full_analysis_budget"]
        )
    elif strategy == "oracle":
        started = perf_counter_ns()
        ranking = [row["candidate_id"] for row in pool]
        shortlist = [key for key in ranking if key in prepared["models"]]
        selection_wall = perf_counter_ns() - started
    else:
        raise ValueError("strategy must be deterministic, learned or oracle")
    if (
        prepared["policy"].artifact_hash != prepared["policy_hash"]
        or canonical_hash(prepared["policy"]._payload()) != prepared["policy_hash"]
    ):
        raise ValueError("frozen candidate policy changed during planning")
    plan = {
        "strategy": strategy,
        "input_binding_hash": canonical_hash(prepared["input_binding"]),
        "ranking": ranking,
        "shortlist": shortlist,
        "policy_artifact_hash": prepared["policy_hash"],
        "pool_hash": canonical_hash(pool),
    }
    return (
        {
            "candidate_pool": pool,
            "frozen_plan": plan,
            "frozen_plan_hash": canonical_hash(plan),
        },
        inference_count,
        inference_wall,
        selection_wall,
    )


def prepare_fiber_frame_candidate_search_expectations(
    baseline: CanonicalModel,
    candidates: Sequence[design.FiberFrameDesignCandidate],
    *,
    training: FiberFrameCandidateTrainingResult,
    prices: design.FiberFrameMaterialPrices,
    terminal_limits: design.FiberFrameTerminalLimits,
    source_revision: str,
    config: PublicRCFiberFrameConfig | None = None,
    full_analysis_budget: int = 3,
    exploration_slots: int = 1,
    history_limits: design.FiberFrameHistoryLimits | None = None,
) -> dict[str, Any]:
    """Freeze declarations and predictions without any full analysis request.

    Parent validation work includes these extra predictions and geometry checks;
    it is separate from worker observations and historical training costs.
    """
    prepared = _prepare(
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
    )
    return _normal(
        {
            "input_binding": prepared["input_binding"],
            **{strategy: _plan(prepared, strategy)[0] for strategy in STRATEGIES},
        }
    )


def _cost(prepared, actual_workload_wall, inference_count):
    return {
        "actual_workload_wall_ns": actual_workload_wall,
        "workload_scope": WORKLOAD_SCOPE,
        "training_artifact_validation_wall_ns": prepared["setup_wall"],
        "pool_preparation_wall_ns": prepared["preparation_wall"],
        "inference_count": inference_count,
        "training_execution_count": 0,
        "data_collection_execution_count": 0,
        "historical_costs_charged_here": False,
        "historical_training_cost_accounting": prepared["input_binding"][
            "training_cost_accounting"
        ],
        "historical_cost_scope": "identity_bound_prior_generation_and_fit_charged_once_by_parent_per_training_report_hash",
    }


def _check_expected_plan(expected_plan_hash, actual):
    if expected_plan_hash is not None and expected_plan_hash != actual:
        raise ValueError("candidate search plan differs from predeclared parent plan")


def run_fiber_frame_candidate_search_arm(
    baseline: CanonicalModel,
    candidates: Sequence[design.FiberFrameDesignCandidate],
    *,
    strategy: str,
    training: FiberFrameCandidateTrainingResult,
    prices: design.FiberFrameMaterialPrices,
    terminal_limits: design.FiberFrameTerminalLimits,
    source_revision: str,
    config: PublicRCFiberFrameConfig | None = None,
    full_analysis_budget: int = 3,
    exploration_slots: int = 1,
    history_limits: design.FiberFrameHistoryLimits | None = None,
    expected_plan_hash: str | None = None,
) -> dict[str, Any]:
    """Run exactly one online arm; baseline consumes one of its request slots."""
    if strategy not in ("deterministic", "learned"):
        raise ValueError("online strategy must be deterministic or learned")
    started = perf_counter_ns()
    prepared = _prepare(
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
    )
    planned, inference_count, inference_wall, selection_wall = _plan(prepared, strategy)
    _check_expected_plan(expected_plan_hash, planned["frozen_plan_hash"])
    plan = planned["frozen_plan"]
    arm, _encoded = core._execute_search_arm(
        name=strategy,
        ordering=plan["ranking"],
        shortlist=plan["shortlist"],
        selection_wall=selection_wall,
        infer_wall=inference_wall,
        inference_count=inference_count,
        baseline=prepared["baseline"],
        declared_by_id={item.candidate_id: item for item in prepared["declared"]},
        cfg=prepared["cfg"],
        prices=prices,
        terminal_limits=terminal_limits,
        source_revision=prepared["source_revision"],
        history_options=prepared["history_options"],
        pool=planned["candidate_pool"],
        shortlist_hash=planned["frozen_plan_hash"],
        preparation_wall=prepared["preparation_wall"],
        policy_setup_charge_wall=prepared["setup_wall"],
    )
    report = {
        "schema_version": ARM_SCHEMA_VERSION,
        "status": "ready" if arm["final_selection"] is not None else "blocked",
        "report_contract_pass": True,
        "strategy": strategy,
        "input_binding": prepared["input_binding"],
        **planned,
        "arm": arm,
        "cost_accounting": _cost(
            prepared, perf_counter_ns() - started, inference_count
        ),
        "claims": dict(CLAIMS),
    }
    report["report_hash"] = canonical_hash(report)
    return _normal(report)


def run_fiber_frame_candidate_search_oracle(
    baseline: CanonicalModel,
    candidates: Sequence[design.FiberFrameDesignCandidate],
    *,
    training: FiberFrameCandidateTrainingResult,
    prices: design.FiberFrameMaterialPrices,
    terminal_limits: design.FiberFrameTerminalLimits,
    source_revision: str,
    config: PublicRCFiberFrameConfig | None = None,
    full_analysis_budget: int = 3,
    exploration_slots: int = 1,
    history_limits: design.FiberFrameHistoryLimits | None = None,
    expected_plan_hash: str | None = None,
) -> dict[str, Any]:
    """Run a fresh exhaustive audit without predicting or choosing an online arm."""
    started = perf_counter_ns()
    prepared = _prepare(
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
    )
    planned, _, _, selection_wall = _plan(prepared, "oracle")
    _check_expected_plan(expected_plan_hash, planned["frozen_plan_hash"])
    rows, analysis_wall = core._execute_search_oracle(
        prepared["baseline"],
        prepared["cfg"],
        prices,
        terminal_limits,
        prepared["history_options"],
        planned["candidate_pool"],
        prepared["models"],
    )
    cost = _cost(prepared, perf_counter_ns() - started, 0)
    cost.update(
        full_reanalysis_wall_ns=analysis_wall,
        plan_selection_wall_ns=selection_wall,
        baseline_analysis_request_count=1,
        candidate_analysis_request_count=sum(
            row["analysis_requested"] is True for row in rows[1:]
        ),
        total_analysis_request_count=sum(
            row["analysis_requested"] is True for row in rows
        ),
        known_solver_execution_count=sum(
            row["solver_executed"] is True for row in rows
        ),
        unknown_solver_execution_count=sum(
            row["solver_executed"] is None for row in rows
        ),
    )
    report = {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "status": "ready"
        if all(design._verified_for_requested_scopes(row) for row in rows)
        else "blocked",
        "report_contract_pass": True,
        "strategy": "oracle",
        "input_binding": prepared["input_binding"],
        **planned,
        "rows": rows,
        "cost_accounting": cost,
        "claims": dict(CLAIMS),
    }
    report["report_hash"] = canonical_hash(report)
    return _normal(report)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _equal(actual, expected, reason):
    _require(canonical_hash(actual) == canonical_hash(expected), reason)


def _fields(value, names, reason):
    _require(type(value) is dict and set(value) == set(names), reason)


def _natural(value):
    _require(
        type(value) is int and value >= 0, "nonnegative integer cost or count required"
    )
    return value


def _hashed(value, key):
    _require(type(value) is dict, "hashed object required")
    _equal(
        value.get(key),
        canonical_hash({k: v for k, v in value.items() if k != key}),
        f"{key} mismatch",
    )


def _validate_common(report, expectations, strategy):
    oracle = strategy == "oracle"
    _fields(
        report,
        {
            "schema_version",
            "status",
            "report_contract_pass",
            "strategy",
            "input_binding",
            "candidate_pool",
            "frozen_plan",
            "frozen_plan_hash",
            "rows" if oracle else "arm",
            "cost_accounting",
            "claims",
            "report_hash",
        },
        "single-arm report fields mismatch",
    )
    _hashed(report, "report_hash")
    _equal(
        report["schema_version"],
        ORACLE_SCHEMA_VERSION if oracle else ARM_SCHEMA_VERSION,
        "single-arm schema mismatch",
    )
    _equal(report["strategy"], strategy, "single-arm strategy mismatch")
    _equal(report["report_contract_pass"], True, "single-arm contract failed")
    _equal(
        report["input_binding"],
        expectations["input_binding"],
        "input declaration mismatch",
    )
    _equal(report["claims"], CLAIMS, "single-arm authority scope mismatch")
    for key in ("candidate_pool", "frozen_plan", "frozen_plan_hash"):
        _equal(report[key], expectations[strategy][key], f"predeclared {key} mismatch")
    _hashed(
        report["frozen_plan"] | {"plan_hash": report["frozen_plan_hash"]}, "plan_hash"
    )
    _equal(
        report["frozen_plan"]["pool_hash"],
        canonical_hash(report["candidate_pool"]),
        "plan pool binding mismatch",
    )
    _equal(
        report["frozen_plan"]["input_binding_hash"],
        canonical_hash(report["input_binding"]),
        "plan input binding mismatch",
    )
    cost = report["cost_accounting"]
    _fields(
        cost,
        {
            "actual_workload_wall_ns",
            "workload_scope",
            "training_artifact_validation_wall_ns",
            "pool_preparation_wall_ns",
            "inference_count",
            "training_execution_count",
            "data_collection_execution_count",
            "historical_costs_charged_here",
            "historical_training_cost_accounting",
            "historical_cost_scope",
        }
        | (
            {
                "full_reanalysis_wall_ns",
                "plan_selection_wall_ns",
                "baseline_analysis_request_count",
                "candidate_analysis_request_count",
                "total_analysis_request_count",
                "known_solver_execution_count",
                "unknown_solver_execution_count",
            }
            if oracle
            else set()
        ),
        "single-arm cost fields mismatch",
    )
    for key, value in cost.items():
        if key.endswith("_ns") or key.endswith("_count"):
            _natural(value)
    _equal(cost["workload_scope"], WORKLOAD_SCOPE, "workload scope mismatch")
    _equal(cost["training_execution_count"], 0, "training reexecution forbidden")
    _equal(cost["data_collection_execution_count"], 0, "label recollection forbidden")
    _equal(
        cost["historical_costs_charged_here"],
        False,
        "worker historical costs must not be charged",
    )
    _equal(
        cost["historical_training_cost_accounting"],
        expectations["input_binding"]["training_cost_accounting"],
        "historical training cost binding mismatch",
    )
    _equal(
        cost["historical_cost_scope"],
        "identity_bound_prior_generation_and_fit_charged_once_by_parent_per_training_report_hash",
        "historical cost scope mismatch",
    )
    expected_inference = (
        sum(row["screening_status"] == "ready" for row in report["candidate_pool"])
        if strategy == "learned"
        else 0
    )
    _equal(
        cost["inference_count"],
        expected_inference,
        "inference execution count mismatch",
    )
    return report["input_binding"]


def _canonical_model(payload, checksum):
    _equal(canonical_hash(payload), checksum, "row canonical model checksum mismatch")
    # Recreate only the detached typed geometry to verify quantity arithmetic.
    # This compiles geometry but makes no Newton or physical analysis request.
    return CanonicalModel(
        schema_version=payload["schema_version"],
        source_path="candidate-search-report",
        source_format="candidate-search-report",
        input_checksum=checksum,
        units=UnitSystem(**payload["units"]),
        coordinate_system=CoordinateSystem(
            axis_order=tuple(payload["coordinate_system"]["axis_order"]),
            up_axis=payload["coordinate_system"]["up_axis"],
        ),
        **{
            key: deepcopy(payload[key])
            for key in (
                "nodes",
                "elements",
                "materials",
                "sections",
                "loads",
                "supports",
                "unsupported_features",
                "warnings",
                "metadata",
            )
        },
    )


def _validate_requested_row(row, candidate_id, checksum, binding):
    _equal(row["candidate_id"], candidate_id, "requested candidate ID mismatch")
    _equal(row["model_checksum"], checksum, "requested model checksum mismatch")
    _equal(row["analysis_requested"], True, "requested row lost request credit")
    _require(
        type(row["full_reference_verification_pass"]) is bool,
        "verification state must be boolean",
    )
    _require(
        row["solver_executed"] is None or type(row["solver_executed"]) is bool,
        "solver execution state must be boolean or unknown",
    )
    _natural(row["reference_and_quantity_wall_ns"])
    model = _canonical_model(row["canonical_model"], checksum)
    result = row["result"]
    if result is not None:
        _hashed(result, "result_hash")
        _require(
            type(result["metrics"]) is dict
            and type(result["metrics"].get("solver_executed")) is bool
            and type(result["contract_bindings"]) is dict
            and type(result["unsupported_features"]) is list
            and all(type(item) is dict for item in result["unsupported_features"]),
            "public execution receipt shape invalid",
        )
        # The public API's missing execution receipt on an exceptional path is
        # not evidence that Newton never ran. Mirror _evaluate_design exactly
        # for failed as well as verified rows before accepting request counts.
        execution_failed = bool(
            result["contract_bindings"].get("problem_contract_hash")
            and any(
                item.get("kind") == "rc_fiber_frame_execution_failed"
                for item in result["unsupported_features"]
            )
        )
        _equal(
            row["solver_executed"],
            None if execution_failed else result["metrics"]["solver_executed"],
            "solver execution receipt mismatch",
        )
        for key, expected in {
            "schema_version": core.public_api.PUBLIC_RC_FIBER_FRAME_SCHEMA_VERSION,
            "solver_id": core.public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
            "compiler_profile": core.public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
            "claim_boundary": core.public_api.PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY,
        }.items():
            _equal(result[key], expected, f"public result {key} mismatch")
        _require(
            result["status"] in ("ready", "blocked"), "public result status invalid"
        )
        _equal(
            result["contract_pass"],
            result["status"] == "ready",
            "public result contract status mismatch",
        )
        _equal(
            result["authority"],
            {
                key: value if result["status"] == "ready" else "not_authoritative"
                for key, value in core.public_api.FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES.items()
            },
            "public result authority mismatch",
        )
        _equal(
            result["canonical_model_checksum"],
            checksum,
            "public result model binding mismatch",
        )
        cfg = PublicRCFiberFrameConfig(**binding["configuration"])
        _equal(
            result["configuration"],
            {
                "load_steps": cfg.load_steps,
                "target_load_factors": list(cfg.target_load_factors),
                "scaled_residual_tolerance": cfg.residual_tolerance,
                "solver_coordinate_increment_tolerance_m": cfg.increment_tolerance_m,
                "maximum_iterations": cfg.maximum_iterations,
                "matrix_backend": "numpy_dense_ndarray",
                "restart_supplied": False,
                "restart_checkpoint_artifact_hash": None,
            },
            "public result fresh configuration mismatch",
        )
        _equal(
            row["validation"]["result_hash"],
            result["result_hash"],
            "public validation result binding mismatch",
        )
    if row["full_reference_verification_pass"]:
        _require(
            result is not None
            and result["status"] == "ready"
            and result["contract_pass"] is True
            and row["status"] == "ready"
            and row["solver_executed"] is True,
            "verified row lacks ready executed public result",
        )
        validation = row["validation"]
        for key, expected in {
            "schema_version": core.public_api.PUBLIC_RC_FIBER_FRAME_REPORT_SCHEMA_VERSION,
            "claim_boundary": core.public_api.PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY,
            "contract_pass": True,
            "exact_engineering_recovery": True,
            "terminal_epoch": binding["configuration"]["load_steps"],
            "terminal_load_factor": 1.0,
            "fallback_count": 0,
            "regularization_count": 0,
        }.items():
            _equal(validation[key], expected, f"public verification {key} mismatch")
        for key, expected in {
            "solver_executed": True,
            "exact_engineering_recovery": True,
            "committed_step_count": binding["configuration"]["load_steps"],
            "newly_solved_step_count": binding["configuration"]["load_steps"],
            "replayed_prefix_step_count": 0,
            "fallback_count": 0,
            "regularization_count": 0,
        }.items():
            _equal(
                result["metrics"][key], expected, f"fresh public metrics {key} mismatch"
            )
        expected_quantities = design.calculate_fiber_frame_member_quantities(model)
        _equal(row["quantities"], expected_quantities, "geometry quantity mismatch")
        prices = design.FiberFrameMaterialPrices(
            **{
                key: value
                for key, value in binding["price_basis"].items()
                if key != "price_table_hash"
            }
        )
        _equal(
            row["material_estimate"],
            design._estimate(expected_quantities, prices),
            "verified scoped material estimate mismatch",
        )
        performance = row["performance"]
        observed = {
            "terminal_maximum_translation_m": max(
                math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
                for node in result["node_displacements"]
            ),
            "terminal_maximum_absolute_fiber_strain": max(
                abs(fiber["strain"]) for fiber in result["fiber_results"]
            ),
        }
        violated = []
        for key, limit in (
            ("terminal_maximum_translation_m", "maximum_translation_m"),
            ("terminal_maximum_absolute_fiber_strain", "maximum_absolute_fiber_strain"),
        ):
            _require(math.isfinite(observed[key]), "finite terminal recovery required")
            _equal(performance[key], observed[key], "terminal envelope mismatch")
            if observed[key] > binding["terminal_limits"][limit]:
                violated.append(key)
        _equal(
            row["terminal_limit_status"],
            "fail" if violated else "pass",
            "terminal limit decision mismatch",
        )
        _equal(
            row["violated_terminal_limits"], violated, "terminal violations mismatch"
        )
        _equal(row["failure"], None, "verified row cannot carry failure")
    else:
        for key in ("quantities", "material_estimate", "performance"):
            _equal(row[key], None, "unverified row cannot receive objective credit")
        _equal(
            row["terminal_limit_status"],
            "unavailable",
            "unverified terminal limits unavailable",
        )
        _equal(
            row["violated_terminal_limits"],
            [],
            "unverified terminal violations unavailable",
        )
    if "history_limits" in binding:
        from structural_analysis.benchmark.fiber_frame_candidate_search_suite import (
            _validate_history_row,
        )

        _validate_history_row(row, binding)
    else:
        _require(
            not any(
                key in row
                for key in (
                    "response_history",
                    "full_history_verification_pass",
                    "history_limit_status",
                    "violated_history_limits",
                    "history_failure",
                )
            ),
            "unrequested history scope cannot be added",
        )


def _validate_counts(cost, requested):
    _equal(
        cost["baseline_analysis_request_count"],
        1,
        "each arm requires its fresh baseline",
    )
    _equal(
        cost["candidate_analysis_request_count"],
        len(requested) - 1,
        "candidate request count mismatch",
    )
    _equal(
        cost["total_analysis_request_count"],
        len(requested),
        "full request total mismatch",
    )
    _equal(
        cost["known_solver_execution_count"],
        sum(row["solver_executed"] is True for row in requested),
        "known solver count mismatch",
    )
    _equal(
        cost["unknown_solver_execution_count"],
        sum(row["solver_executed"] is None for row in requested),
        "unknown solver count mismatch",
    )
    _require(
        sum(row["reference_and_quantity_wall_ns"] for row in requested)
        <= cost["full_reanalysis_wall_ns"],
        "full reanalysis interval omits row work",
    )


def _validate_bundle(arm, requested, binding):
    bundle = arm["design_comparison"]
    if not arm["shortlist"]:
        _equal(bundle, None, "baseline-only arm has no producer comparison bundle")
        _equal(
            arm["design_comparison_unavailable_reason"],
            "empty_shortlist_baseline_only",
            "baseline-only bundle reason mismatch",
        )
        return
    _equal(
        arm["design_comparison_unavailable_reason"],
        None,
        "producer bundle unavailable reason mismatch",
    )
    _hashed(bundle, "report_hash")
    _equal(
        bundle["experiment_identity_hash"],
        canonical_hash(bundle["identity"]),
        "design experiment identity hash mismatch",
    )
    expected_identity = {
        "schema_version": design.DESIGN_HISTORY_COMPARISON_SCHEMA
        if "history_limits" in binding
        else design.DESIGN_COMPARISON_SCHEMA,
        "source_revision": binding["source_revision"],
        "compiler_profile": core.public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        "configuration": binding["configuration"],
        "baseline_model_checksum": binding["baseline_model_checksum"],
        "candidates": [
            next(row for row in binding["candidates"] if row["candidate_id"] == key)
            for key in arm["shortlist"]
        ],
        "price_table_hash": binding["price_basis"]["price_table_hash"],
        "terminal_limits": binding["terminal_limits"],
        "quantity_scope": design.QUANTITY_SCOPE,
        "rebar_density_kg_per_m3": 7850.0,
    }
    if "history_limits" in binding:
        expected_identity["history_limits"] = binding["history_limits"]
    _equal(bundle["identity"], expected_identity, "design bundle declaration mismatch")
    _equal(
        bundle["schema_version"],
        expected_identity["schema_version"],
        "design bundle schema mismatch",
    )
    _equal(
        bundle["price_basis"], binding["price_basis"], "design bundle price mismatch"
    )
    _equal(bundle["baseline_id"], "baseline", "design baseline ID mismatch")
    _equal(
        bundle["rows"],
        [
            {key: value for key, value in row.items() if key != "analysis_requested"}
            for row in requested
        ],
        "untouched producer bundle row mismatch",
    )
    _equal(
        bundle["status"],
        "ready"
        if all(design._verified_for_requested_scopes(row) for row in requested)
        else "partial",
        "design bundle status mismatch",
    )
    eligible = [
        row
        for row in requested
        if design._verified_for_requested_scopes(row)
        and design._requested_limits_pass(row)
        and row["material_estimate"] is not None
    ]
    winner = core._winner(requested)
    _equal(
        bundle["selection"],
        {
            "criterion": "minimum_scoped_material_estimate_with_verified_terminal_and_history_limits"
            if "history_limits" in binding
            else "minimum_scoped_material_estimate_with_verified_terminal_limits",
            "candidate_id": winner["candidate_id"] if winner else None,
            "evaluated_pool_size": len(requested),
            "eligible_count": len(eligible),
            "reason": "selected_within_declared_scope"
            if winner
            else "reference_or_limits_or_prices_unavailable_or_no_candidate_passes",
        },
        "design bundle selection mismatch",
    )
    for row in requested:
        comparable = (
            requested[0]["full_reference_verification_pass"]
            and row["full_reference_verification_pass"]
        )
        _equal(
            row["comparable_to_baseline"],
            comparable,
            "baseline comparison scope mismatch",
        )
        _equal(
            row["difference_from_baseline"],
            design._difference(requested[0], row) if comparable else None,
            "baseline difference mismatch",
        )
    runtime = bundle["runtime"]
    for key, expected in {
        "clock": "time.perf_counter_ns",
        "reference_analysis_request_count": len(requested),
        "known_solver_execution_count": sum(
            row["solver_executed"] is True for row in requested
        ),
        "unknown_solver_execution_count": sum(
            row["solver_executed"] is None for row in requested
        ),
        "training_wall_ns": None,
        "ai_inference_wall_ns": None,
        "peak_memory_bytes": None,
    }.items():
        _equal(runtime[key], expected, "design runtime scope or count mismatch")
    _require(
        sum(row["reference_and_quantity_wall_ns"] for row in requested)
        <= _natural(runtime["total_wall_ns"])
        <= arm["cost_accounting"]["full_reanalysis_wall_ns"],
        "design bundle runtime is not nested in arm",
    )
    expected_claims = {
        "actual_physical_design_changes": True,
        "quantities_are_geometry_derived": True,
        "all_analysis_requests_start_at_epoch_zero": True,
        "all_requested_models_verified": all(
            row["full_reference_verification_pass"] for row in requested
        ),
        "limits_scope": "terminal_and_committed_history_translation_and_fiber_strain"
        if "history_limits" in binding
        else "terminal_translation_and_fiber_strain_only",
        "detailed_takeoff": False,
        "confirmed_currency_savings": False,
        "design_code_compliance": False,
        "engineering_approval": False,
        "ai_acceleration_measured": False,
        "commercial_readiness": False,
    }
    if "history_limits" in binding:
        expected_claims["all_requested_history_verified"] = all(
            row["full_history_verification_pass"] for row in requested
        )
    _equal(bundle["claims"], expected_claims, "design bundle authority mismatch")


def validate_fiber_frame_candidate_search_arm_report(report, expectations, *, strategy):
    """Validate a detached report against the parent's earlier frozen plan.

    This performs no inference or solver execution. Source recovery validation
    stays with the actual public producer; this is an internal consistency gate.
    """
    _require(strategy in ("deterministic", "learned"), "online strategy required")
    binding = _validate_common(report, expectations, strategy)
    arm = report["arm"]
    _fields(
        arm,
        {
            "strategy",
            "ranking",
            "shortlist",
            "frozen_shortlist_hash",
            "baseline",
            "design_comparison",
            "design_comparison_unavailable_reason",
            "candidate_outcomes",
            "final_selection",
            "selection_difference_from_baseline",
            "cost_accounting",
        },
        "online arm fields mismatch",
    )
    for key in ("strategy", "ranking", "shortlist"):
        _equal(arm[key], report["frozen_plan"][key], "online arm plan mismatch")
    _equal(
        arm["frozen_shortlist_hash"],
        report["frozen_plan_hash"],
        "online arm frozen plan hash mismatch",
    )
    _validate_requested_row(
        arm["baseline"], "baseline", binding["baseline_model_checksum"], binding
    )
    _equal(
        [row["candidate_id"] for row in arm["candidate_outcomes"]],
        [row["candidate_id"] for row in binding["candidates"]],
        "complete candidate outcome denominator required",
    )
    requested_by_id = {"baseline": arm["baseline"]}
    for row, candidate, pool_row in zip(
        arm["candidate_outcomes"],
        binding["candidates"],
        report["candidate_pool"],
        strict=True,
    ):
        key = candidate["candidate_id"]
        if key in arm["shortlist"]:
            _validate_requested_row(row, key, candidate["model_checksum"], binding)
            requested_by_id[key] = row
        else:
            _equal(
                row,
                {
                    "candidate_id": key,
                    "status": "not_shortlisted"
                    if pool_row["screening_status"] == "ready"
                    else "preanalysis_blocked",
                    "analysis_requested": False,
                    "solver_executed": False,
                    "result": None,
                    "full_reference_verification_pass": False,
                    "failure": pool_row["failure"],
                },
                "unrequested row cannot carry result or execution credit",
            )
    requested = [arm["baseline"], *(requested_by_id[key] for key in arm["shortlist"])]
    cost = arm["cost_accounting"]
    _fields(
        cost,
        {
            "shared_pool_preparation_charged_wall_ns",
            "inference_wall_ns",
            "inference_count",
            "shortlist_selection_wall_ns",
            "final_selection_wall_ns",
            "policy_setup_wall_ns",
            "full_reanalysis_wall_ns",
            "baseline_analysis_request_count",
            "candidate_analysis_request_count",
            "total_analysis_request_count",
            "known_solver_execution_count",
            "unknown_solver_execution_count",
            "charged_online_wall_ns",
        },
        "online cost fields mismatch",
    )
    for value in cost.values():
        _natural(value)
    _validate_counts(cost, requested)
    _equal(
        cost["inference_count"],
        report["cost_accounting"]["inference_count"],
        "arm inference count mismatch",
    )
    if strategy == "deterministic":
        _equal(cost["inference_wall_ns"], 0, "deterministic inference forbidden")
    _equal(
        cost["policy_setup_wall_ns"],
        report["cost_accounting"]["training_artifact_validation_wall_ns"],
        "training validation cost mismatch",
    )
    _equal(
        cost["shared_pool_preparation_charged_wall_ns"],
        report["cost_accounting"]["pool_preparation_wall_ns"],
        "pool preparation cost mismatch",
    )
    _equal(
        cost["charged_online_wall_ns"],
        sum(
            cost[key]
            for key in (
                "shared_pool_preparation_charged_wall_ns",
                "inference_wall_ns",
                "shortlist_selection_wall_ns",
                "final_selection_wall_ns",
                "policy_setup_wall_ns",
                "full_reanalysis_wall_ns",
            )
        ),
        "online cost balance mismatch",
    )
    _require(
        cost["charged_online_wall_ns"]
        <= report["cost_accounting"]["actual_workload_wall_ns"],
        "actual workload interval omits online work",
    )
    winner = core._winner(requested)
    _equal(
        arm["final_selection"],
        winner,
        "fresh verified minimum-material selection mismatch",
    )
    _equal(
        arm["selection_difference_from_baseline"],
        design._difference(requested[0], winner) if winner else None,
        "selected difference mismatch",
    )
    _equal(
        report["status"],
        "ready" if winner else "blocked",
        "online report status mismatch",
    )
    _validate_bundle(arm, requested, binding)


def validate_fiber_frame_candidate_search_oracle_report(report, expectations):
    """Validate exhaustive rows, with unsupported candidates kept unavailable."""
    binding = _validate_common(report, expectations, "oracle")
    rows = report["rows"]
    _equal(
        [row["candidate_id"] for row in rows],
        ["baseline", *(row["candidate_id"] for row in binding["candidates"])],
        "oracle denominator mismatch",
    )
    _validate_requested_row(
        rows[0], "baseline", binding["baseline_model_checksum"], binding
    )
    requested = [rows[0]]
    for row, candidate, pool in zip(
        rows[1:], binding["candidates"], report["candidate_pool"], strict=True
    ):
        if candidate["model_checksum"] is not None:
            _validate_requested_row(
                row, candidate["candidate_id"], candidate["model_checksum"], binding
            )
            requested.append(row)
        else:
            _equal(
                row,
                core._unavailable(candidate["candidate_id"], pool["failure"]),
                "unavailable oracle row mismatch",
            )
    cost = report["cost_accounting"]
    _validate_counts(cost, requested)
    _require(
        sum(
            cost[key]
            for key in (
                "training_artifact_validation_wall_ns",
                "pool_preparation_wall_ns",
                "plan_selection_wall_ns",
                "full_reanalysis_wall_ns",
            )
        )
        <= cost["actual_workload_wall_ns"],
        "oracle workload interval omits work",
    )
    _equal(
        report["status"],
        "ready"
        if all(design._verified_for_requested_scopes(row) for row in rows)
        else "blocked",
        "oracle status mismatch",
    )
