"""Select a development ridge candidate using complete withheld-training-case paths.

Runtime fold scores are tuning evidence, not independent evaluation or net savings.
Original solver-produced labels and their generation costs remain required inputs.
"""

from copy import deepcopy
import json
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

import numpy as np

from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
    control_history_features,
)
from structural_analysis.benchmark.rc_control_material_features import (
    MATERIAL_FEATURE_PROFILE,
    decode_material_snapshot,
    material_control_features,
)
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext
from structural_analysis.benchmark.rc_control_training_diagnostics import (
    _validated_training_data,
)
from structural_analysis.ai.fiber_frame_warm_start_features import (
    FiberFrameWarmStartModelFeatures,
)


def _static_material_model_gate(policy, features):
    """Prove rejection from the unchanged material profile's immutable prefix.

    Passing this necessary range check never authorizes a proposal. The normal
    context, material and dynamic-feature checks still run for that case.
    """
    if (
        type(policy) is not learning.RCControlSeedPolicy
        or type(features) is not FiberFrameWarmStartModelFeatures
    ):
        raise ValueError("typed policy and immutable model features required")
    d = policy.to_dict()
    if (
        d.get("feature_profile") != MATERIAL_FEATURE_PROFILE
        or d["model_context_hash"] != features.context_hash
        or d["model_feature_names"] != list(features.feature_names)
    ):
        raise ValueError("matching material policy model prefix required")
    count = len(features.values)
    low = np.asarray(d["feature_min"][:count])
    high = np.asarray(d["feature_max"][:count])
    x = np.asarray(features.values)
    violations = []
    status = "not_proved"
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            slack = np.maximum((high - low) * d["ood_margin"], 1e-12)
            for index in np.flatnonzero((x < low - slack) | (x > high + slack)):
                i = int(index)
                violations.append(
                    {
                        "index": i,
                        "feature": features.feature_names[i],
                        "value": float(x[i]),
                        "low": float(low[i]),
                        "high": float(high[i]),
                        "slack": float(slack[i]),
                    }
                )
        status = "rejected" if violations else "not_rejected"
    except FloatingPointError:
        # Preserve the original callback/fallback behavior when finite inputs
        # cannot produce finite range arithmetic; do not infer a rejection.
        violations = []
    gate = {
        "schema_version": "rc-material-static-model-gate.v1",
        "policy_hash": policy.policy_hash,
        "model_feature_hash": features.feature_hash,
        "problem_contract_hash": features.problem_contract_hash,
        "model_context_hash": features.context_hash,
        "feature_profile": d["feature_profile"],
        "arithmetic_profile": d.get("arithmetic_profile"),
        "static_feature_count": count,
        "status": status,
        "violations": violations,
        "material_capture_omitted": status == "rejected",
        "proposal_acceptance_authorized": False,
    }
    gate["gate_hash"] = _sha(_bytes(gate))
    return gate


def _validate_case_rows(cases, prepared, grouped, source, arithmetic_profile):
    """Bind declared original rows to the supplied model, request and feature layout."""
    training = {c.case_id: c for c in cases if c.split == "train"}
    if set(training) != set(grouped):
        raise ValueError("exact original training-case roster required")
    arithmetic = learning._arithmetic_manifest(arithmetic_profile)
    if source.get("arithmetic_profile") != arithmetic:
        raise ValueError("original policy arithmetic profile differs")
    for case_id, rows in grouped.items():
        case = training[case_id]
        _, compiled, features, _, _ = prepared[case_id]
        if (
            source["model_context_hash"] != features.context_hash
            or source["model_feature_names"] != list(features.feature_names)
            or source["free_global_dofs"] != list(compiled.problem.free_global_dofs)
            or source["solver_config_hash"] != case.request.solver_config.contract_hash
            or source["control_free_index"]
            != compiled.problem.free_global_dofs.index(case.request.control_global_dof)
        ):
            raise ValueError("training model or solver context differs")
        indices = []
        for row in rows:
            index = row.get("target_index")
            if type(index) is not int or not 1 <= index < len(case.request.targets_m):
                raise ValueError("original noninitial target index required")
            indices.append(index)
            try:
                context = RCControlSeedContext(**row["context"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("original typed training context required") from exc
            if (
                context.problem_contract_hash != compiled.problem.contract_hash
                or context.control_global_dof != case.request.control_global_dof
                or context.control_free_index != source["control_free_index"]
                or context.target_m != case.request.targets_m[index]
                or len(context.accepted_targets_m) != index + 1
                or tuple(context.accepted_targets_m[1:])
                != case.request.targets_m[:index]
                or row.get("arithmetic_profile") != arithmetic
            ):
                raise ValueError("training context differs from the original request")
            if source.get("feature_profile") == MATERIAL_FEATURE_PROFILE:
                if type(row.get("parent_hash")) is not str:
                    raise ValueError("original material parent identity required")
                decode_material_snapshot(
                    context.committed_material_state_json,
                    compiled.problem.contract_hash,
                    row["parent_hash"],
                )
                actual, names = material_control_features(context, features)
                if names != source["material_feature_names"]:
                    raise ValueError("material input layout differs")
            elif source.get("feature_profile") == HISTORY_FEATURE_PROFILE:
                actual, _ = control_history_features(
                    context,
                    features,
                    case.request.solver_config.load_factor_coordinate_scale_m,
                )
            else:
                actual = learning._features(context, features)
            if not np.array_equal(actual, row["features"]):
                raise ValueError("training features differ from their original context")
            accepted = np.asarray(row.get("accepted_coordinates"), dtype=float)
            baseline = learning.secant_seed(context)
            correction = row[
                "source_correction"
                if source.get("feature_profile") == HISTORY_FEATURE_PROFILE
                else "correction"
            ]
            if (
                baseline is None
                or accepted.shape != (len(source["free_global_dofs"]) + 1,)
                or not np.all(np.isfinite(accepted))
                or not np.array_equal(accepted - baseline, correction)
            ):
                raise ValueError(
                    "training correction differs from accepted source coordinates"
                )
        if indices != sorted(set(indices)):
            raise ValueError("unique ordered original target indices required")
    return training


def _runtime_score(
    report,
    decisions,
    *,
    proposal_setup_wall_ns=None,
    include_prior_work_source_setup=False,
):
    """Keep failed or unaccounted paths ineligible, including the fresh reference."""
    if (
        report.get("schema_version")
        == "experimental-rc-control-parent-step-comparison.v1"
    ):
        raise ValueError(
            "a parent-step comparison is not complete-path runtime evidence"
        )
    if proposal_setup_wall_ns is not None and (
        type(proposal_setup_wall_ns) is not int or proposal_setup_wall_ns < 0
    ):
        raise ValueError("nonnegative measured proposal setup time required")
    setup = proposal_setup_wall_ns or 0
    if type(include_prior_work_source_setup) is not bool:
        raise ValueError("explicit prior source setup accounting required")
    source_setup = None
    if include_prior_work_source_setup:
        source_setup = report.get("prior_work_source_setup_cost")
        if (
            type(source_setup) is not dict
            or set(source_setup) != {"wall_ns", "cpu_ns", "scope"}
            or any(
                type(source_setup.get(key)) is not int or source_setup[key] < 0
                for key in ("wall_ns", "cpu_ns")
            )
            or type(source_setup.get("scope")) is not str
            or source_setup["scope"]
            != "once_per_benchmark_prior_source_binding_setup_inside_whole_study"
        ):
            raise ValueError("measured prior source setup cost required")
        source_setup = dict(source_setup)
    source_wall = 0 if source_setup is None else source_setup["wall_ns"]
    paths = (*report["arms"].values(), report["fresh_reference"])
    physical = (
        report["reference_repeat_exact"]
        and report["all_execution_work_reported"]
        and all(p["status"] == "complete" for p in paths)
        and all(c["full_history_pass"] for c in report["comparisons"].values())
    )
    baseline = report["arms"]["secant"]["wall_ns"]
    proposed = report["arms"]["proposal"]["wall_ns"]
    if (
        type(baseline) is not int
        or baseline <= 0
        or type(proposed) is not int
        or proposed <= 0
    ):
        raise ValueError("positive measured path timings required")
    score = {
        "full_comparison_pass": bool(physical),
        "proposal_over_secant_path_wall_ratio": (proposed + setup + source_wall)
        / baseline
        if physical
        else None,
        "secant_path_wall_ns": baseline,
        "proposal_path_wall_ns": proposed,
        "proposed_count": sum(d["decision"] == "proposed" for d in decisions),
        "abstained_count": sum(
            d["decision"] in ("abstained_to_reference", "abstained_to_secant")
            for d in decisions
        ),
        "execution_work": learning._execution_work([{"report": report}]),
        "whole_benchmark_wall_ns": report["whole_study_wall_ns"],
        "score_scope": "whole path including input capture, inference, numerical retries, recovery and step IO; final path file write excluded",
    }
    if proposal_setup_wall_ns is not None:
        score.update(
            proposal_setup_wall_ns=setup,
            proposal_scored_wall_ns=proposed + setup + source_wall,
            whole_scored_benchmark_wall_ns=report["whole_study_wall_ns"] + setup,
        )
        score["score_scope"] += (
            "; static model gate computation and record write added to proposal time"
        )
    if source_setup is not None:
        score.update(
            prior_work_source_setup_cost=source_setup,
            proposal_scored_wall_ns=proposed + setup + source_wall,
            # Source setup is already nested in whole_study_wall_ns.
            whole_scored_benchmark_wall_ns=report["whole_study_wall_ns"] + setup,
        )
        score["score_scope"] += (
            "; prior source binding setup added once to proposal time and already included in whole study"
        )
    return score


def _validated_proposal_guard_binding(binding, policy_hash, excluded_case_ids):
    """Bind a caller's guard to this frozen fit and its actual exclusions.

    The supplied identities do not authenticate external training data or code.
    A guarded fold cannot qualify a subsequently refitted bare seed policy.
    """
    if (
        type(binding) is not dict
        or set(binding)
        != {"guard", "guard_identity", "seed_policy_hash", "excluded_case_ids"}
        or not callable(binding.get("guard"))
        or type(binding.get("guard_identity")) is not str
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", binding["guard_identity"])
        or type(binding.get("seed_policy_hash")) is not str
        or binding["seed_policy_hash"] != policy_hash
        or type(binding.get("excluded_case_ids")) is not tuple
        or any(type(case_id) is not str for case_id in binding["excluded_case_ids"])
        or binding["excluded_case_ids"] != excluded_case_ids
    ):
        raise ValueError("guard binding must match the frozen seed and exclusions")
    return binding["guard"], {
        "guard_identity": binding["guard_identity"],
        "seed_policy_hash": policy_hash,
        "excluded_case_ids": list(excluded_case_ids),
        "caller_identity_is_external_attestation": False,
    }


def _validated_full_training_pair(binding, policy, sample_hashes):
    """Check a detached full-training pair, without authenticating its caller."""
    required = {
        "training_scope",
        "seed_policy_hash",
        "gate_policy_hash",
        "gate_policy",
        "training_sample_hashes",
        "fit_receipt",
    }
    if (
        type(binding) is not dict
        or set(binding) != required
        or binding["training_scope"] != "declared_training_only"
        or binding["seed_policy_hash"] != policy.policy_hash
        or type(binding["training_sample_hashes"]) is not list
        or binding["training_sample_hashes"] != sample_hashes
        or policy.to_dict()["training_sample_hashes"] != sample_hashes
    ):
        raise ValueError("full-training pair must bind the actual seed and samples")
    # JSON detaches caller-owned dictionaries and rejects nonfinite JSON numbers.
    detached = json.loads(_bytes(binding))
    gate, receipt = detached["gate_policy"], detached["fit_receipt"]
    gate_fields = {
        "schema_version",
        "feature_profile",
        "feature_names",
        "mean",
        "scale",
        "minimum",
        "maximum",
        "weights",
        "ridge",
        "threshold",
        "excluded_case_ids",
        "training_sample_hashes",
        "positive_count",
        "negative_count",
        "training_rows_hash",
        "policy_hash",
        "seed_policy_hash",
        "training_scope",
        "teacher_roster_hash",
        "declared_training_sample_hashes",
        "unverified_sample_hashes",
        "unverified_count",
        "cost_target_profile",
    }
    if (
        type(gate) is not dict
        or set(gate) != gate_fields
        or gate["schema_version"] != "rc-full-training-prior-work-cost-margin-gate.v1"
        or gate["training_scope"] != "declared_training_only"
        or gate["excluded_case_ids"] != []
        or gate["feature_profile"] != "rc-switch-accepted-prefix-prior-work-features.v1"
        or gate["cost_target_profile"] != "minimum-three-repeat-relative-time-margin.v1"
        or type(gate["ridge"]) is not float
        or gate["ridge"] != 1.0
        or type(gate["threshold"]) is not float
        or gate["threshold"] != 0.01
        or gate["seed_policy_hash"] != policy.policy_hash
        or gate["declared_training_sample_hashes"] != sample_hashes
        or gate["policy_hash"] != detached["gate_policy_hash"]
        or gate["policy_hash"]
        != _sha(_bytes({k: v for k, v in gate.items() if k != "policy_hash"}))
    ):
        raise ValueError("canonical full-training gate policy and scope required")
    for key in ("training_rows_hash", "teacher_roster_hash", "policy_hash"):
        if type(gate[key]) is not str or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", gate[key]
        ):
            raise ValueError("full-training gate provenance hashes required")
    known, unknown = gate["training_sample_hashes"], gate["unverified_sample_hashes"]
    if (
        type(known) is not list
        or not known
        or type(unknown) is not list
        or any(type(v) is not str for v in known + unknown)
        or len(known) + len(unknown) != len(sample_hashes)
        or bool(set(known) & set(unknown))
        or len(set(known + unknown)) != len(sample_hashes)
        or set(known + unknown) != set(sample_hashes)
        or known != [v for v in sample_hashes if v in set(known)]
        or unknown != [v for v in sample_hashes if v in set(unknown)]
        or type(gate["unverified_count"]) is not int
        or gate["unverified_count"] != len(unknown)
        or any(
            type(gate[k]) is not int or gate[k] < 0
            for k in ("positive_count", "negative_count")
        )
        or gate["positive_count"] + gate["negative_count"] != len(known)
    ):
        raise ValueError(
            "complete full-training known and unknown denominators required"
        )
    names = gate["feature_names"]
    seed = policy.to_dict()
    coordinates = len(seed["free_global_dofs"]) + 1
    expected_names = [
        *("model." + name for name in seed["model_feature_names"]),
        "target_m",
        "target_increment_m",
        "previous_target_increment_m",
        *(f"last_coordinate_{i}" for i in range(coordinates)),
        *(f"coordinate_increment_{i}" for i in range(coordinates)),
        *(
            "prior_work." + name
            for name in (
                "core_calls",
                "newton_iterations",
                "linear_solves",
                "assembly_dispatches",
                "line_search_dispatches",
                "terminal_refinement_dispatches",
            )
        ),
    ]
    if (
        type(names) is not list
        or names != expected_names
        or len(set(names)) != len(names)
    ):
        raise ValueError("aligned full-training gate features required")
    width = len(names)
    for key in ("mean", "scale", "minimum", "maximum", "weights"):
        values = gate[key]
        if (
            type(values) is not list
            or len(values) != width + (key == "weights")
            or any(type(v) not in (int, float) or not np.isfinite(v) for v in values)
        ):
            raise ValueError("finite aligned full-training gate arrays required")
    if any(s <= 0 for s in gate["scale"]) or any(
        not low <= center <= high
        for low, center, high in zip(gate["minimum"], gate["mean"], gate["maximum"])
    ):
        raise ValueError("valid full-training gate normalization required")
    if (
        type(receipt) is not dict
        or receipt.get("fit_completed") is not True
        or receipt.get("unknown_work") is not False
        or type(receipt.get("fit_wall_ns")) is not int
        or receipt["fit_wall_ns"] < 0
        or any(
            receipt.get(k) is not False
            for k in (
                "independent_evaluation",
                "historical_training_admitted",
                "predecessor_counter_authenticity_established",
                "online_extraction_cost_in_target",
            )
        )
        or any(
            type(receipt.get(k)) is not int or receipt[k] != expected
            for k, expected in (
                ("verified_rows", len(known)),
                ("unverified_rows_excluded", len(unknown)),
                ("declared_rows", len(sample_hashes)),
                ("seed_fit_count", 0),
                ("gate_fit_count", 1),
            )
        )
        or any(
            receipt.get(k) != expected
            for k, expected in (
                ("training_scope", "declared_training_only"),
                ("seed_policy_hash", policy.policy_hash),
                ("policy_hash", gate["policy_hash"]),
                ("teacher_roster_hash", gate["teacher_roster_hash"]),
                ("declared_training_sample_hashes", sample_hashes),
                ("unverified_sample_hashes", unknown),
                ("target_profile", gate["cost_target_profile"]),
                ("feature_profile", gate["feature_profile"]),
            )
        )
    ):
        raise ValueError("known completed full-training fit receipt required")
    return detached


def run_rc_control_runtime_selection(
    cases,
    samples,
    original_policy,
    *,
    source_revision,
    output_directory,
    ridge_grid,
    arithmetic_profile="binary64",
    minimum_relative_improvement=0.01,
    maximum_fits=257,
    maximum_core_calls=32768,
    proposal_abstention_strategy="reference",
    static_model_abstention=False,
    repetitions=1,
    record_assembly_work=False,
    reuse_line_search_assembly=False,
    record_assembly_timing=False,
    withholding_strategy="case",
    observe_initial_residuals=False,
    proposal_guard_factory=None,
    proposal_guard_factory_identity=None,
    record_prior_accepted_transition_work=False,
    full_training_pair_factory=None,
    full_training_pair_factory_identity=None,
):
    """Fit each ridge with declared exclusions, then execute each case's full path.

    All original cases enter the existing leakage preflight. Only cases already
    declared train may be fitted or executed here; validation/holdout outputs are
    untouched. Default exclusion is one case. Connected-group mode excludes all
    transitively related training cases and requires at least two groups. Both
    modes remain internal tuning, not authenticated independent evaluation.
    No structural labels are regenerated. Bounds cover every path and possible
    proposal retry before the first fit or output is created.

    An optional guard factory receives only this fit, the held model's static
    features and its exact exclusions. Its identified binding runs before
    material capture, and setup/persistence costs enter the proposal score.
    Guarded fold winners remain tuning records and cannot promote a bare seed.
    An identified full-training pair factory may fit one gate to the actual final
    seed and detached original TRAIN rows after repeated connected folds. Its
    exact binding is checked and persisted before selection. Original data and
    causal producer authenticity remain separate requirements. All optional
    fields are absent from legacy output.
    """
    if withholding_strategy not in ("case", "connected_training_groups"):
        raise ValueError("supported runtime withholding strategy required")
    if type(observe_initial_residuals) is not bool:
        raise ValueError("explicit boolean initial residual observation required")
    if type(record_prior_accepted_transition_work) is not bool:
        raise ValueError(
            "explicit boolean prior accepted-transition recording required"
        )
    if record_prior_accepted_transition_work and proposal_guard_factory is None:
        raise ValueError(
            "prior accepted-transition recording requires an identified guard factory"
        )
    if (proposal_guard_factory is None) != (
        proposal_guard_factory_identity is None
    ) or (
        proposal_guard_factory is not None
        and (
            not callable(proposal_guard_factory)
            or type(proposal_guard_factory_identity) is not str
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", proposal_guard_factory_identity)
            or proposal_abstention_strategy != "secant"
        )
    ):
        raise ValueError("identified proposal guard factory requires secant abstention")
    if (full_training_pair_factory is None) != (
        full_training_pair_factory_identity is None
    ) or (
        full_training_pair_factory is not None
        and (
            not callable(full_training_pair_factory)
            or type(full_training_pair_factory_identity) is not str
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", full_training_pair_factory_identity
            )
            or proposal_guard_factory is None
            or proposal_abstention_strategy != "secant"
            or withholding_strategy != "connected_training_groups"
            or type(repetitions) is not int
            or repetitions not in (3, 6)
            or record_prior_accepted_transition_work is not True
        )
    ):
        raise ValueError(
            "identified full-training pair requires repeated connected guarded prior-work folds"
        )
    wall, cpu = perf_counter_ns(), process_time_ns()
    if type(record_assembly_timing) is not bool or (
        record_assembly_timing and not record_assembly_work
    ):
        raise ValueError("assembly timing requires explicit work recording")
    if type(record_assembly_work) is not bool:
        raise ValueError("explicit boolean assembly recording required")
    if type(reuse_line_search_assembly) is not bool:
        raise ValueError("explicit boolean line-search assembly reuse required")
    if type(repetitions) is not int or repetitions not in (1, 3, 6):
        raise ValueError("one run or three/six counterbalanced repetitions required")
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ):
        raise ValueError("exact source revision required")
    if (
        type(ridge_grid) is not tuple
        or not 1 <= len(ridge_grid) <= 8
        or any(
            type(v) not in (int, float) or not np.isfinite(v) or v <= 0
            for v in ridge_grid
        )
        or any(a >= b for a, b in zip(ridge_grid, ridge_grid[1:]))
    ):
        raise ValueError(
            "one to eight increasing positive finite ridge values required"
        )
    if (
        type(minimum_relative_improvement) not in (int, float)
        or not np.isfinite(minimum_relative_improvement)
        or not 0 <= minimum_relative_improvement < 1
        or type(maximum_fits) is not int
        or not 1 <= maximum_fits <= 257
        or type(maximum_core_calls) is not int
        or not 1 <= maximum_core_calls <= 1048576
    ):
        raise ValueError("bounded improvement, fit and core-call budgets required")
    if type(
        proposal_abstention_strategy
    ) is not str or proposal_abstention_strategy not in (
        "reference",
        "secant",
    ):
        raise ValueError("supported proposal abstention strategy required")
    if type(static_model_abstention) is not bool:
        raise ValueError("explicit boolean static model abstention required")
    source, grouped, profile = _validated_training_data(samples, original_policy)
    if (
        static_model_abstention
        and source.get("feature_profile") != MATERIAL_FEATURE_PROFILE
    ):
        raise ValueError(
            "static model abstention requires the material feature profile"
        )
    measured: dict[str, Any] = {}
    prepared = learning._preflight(
        cases, arithmetic_profile, measurement_screen=measured
    )
    training_cases = _validate_case_rows(
        cases, prepared, grouped, source, arithmetic_profile
    )
    case_ids = sorted(training_cases)
    exclusion_groups = None
    withheld = {case_id: [case_id] for case_id in case_ids}
    if withholding_strategy == "connected_training_groups":
        from structural_analysis.benchmark.rc_control_learning_split import (
            control_training_exclusion_groups,
        )

        exclusion_groups = control_training_exclusion_groups(cases)
        if len(exclusion_groups["groups"]) < 2:
            raise ValueError(
                "connected training groups leave no independent fitting group"
            )
        withheld = {
            case_id: group for group in exclusion_groups["groups"] for case_id in group
        }
    fit_bound = len(case_ids) * len(ridge_grid) + (
        2
        if full_training_pair_factory is not None
        else 1
        if proposal_guard_factory is None
        else 0
    )
    # Reference and fresh reference use one call per target. Both secant and
    # proposer can retry once; constant preload runs once per path.
    core_bound = (
        repetitions
        * len(ridge_grid)
        * sum(
            6 * len(c.request.targets_m) + 4 * bool(c.request.constant_nodal_loads)
            for c in training_cases.values()
        )
    )
    if fit_bound > maximum_fits or core_bound > maximum_core_calls:
        raise ValueError(
            f"runtime selection requires budgets for {fit_bound} fits and up to {core_bound} core calls"
        )
    frozen_training_samples = (
        _bytes(samples) if full_training_pair_factory is not None else None
    )
    frozen_source_policy = (
        _bytes(original_policy.to_dict())
        if full_training_pair_factory is not None
        else None
    )
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    capture = source.get("feature_profile") == MATERIAL_FEATURE_PROFILE
    fit_solver = (
        learning.CONSTANT_SAFE_SVD_FIT_PROFILE
        if source.get("fit_solver_profile") == learning.CONSTANT_SAFE_SVD_FIT_PROFILE
        else learning.SVD_RIDGE_FIT_PROFILE
    )
    plan = {
        "schema_version": "rc-control-runtime-selection-plan.v1",
        "source_revision": source_revision,
        "source_policy_hash": original_policy.policy_hash,
        "source_policy_weights_and_preprocessing_used": False,
        "source_sample_hashes": source["training_sample_hashes"],
        "case_sample_hashes": {
            k: [r["sample_hash"] for r in grouped[k]] for k in case_ids
        },
        "cases": [
            {
                "case_id": c.case_id,
                "split": c.split,
                "request": c.request.to_dict(),
                "model_hash": c.model.canonical_model_checksum,
                "split_keys": prepared[c.case_id][3],
            }
            for c in cases
        ],
        "measured_source_screen": measured,
        "ridge_grid": list(ridge_grid),
        "fit_solver_profile": fit_solver,
        "arithmetic_profile": arithmetic_profile,
        "ood_margin": source["ood_margin"],
        "minimum_relative_improvement": minimum_relative_improvement,
        "maximum_fits": maximum_fits,
        "maximum_core_calls": maximum_core_calls,
        "maximum_required_fits": fit_bound,
        "maximum_possible_core_calls": core_bound,
        "training_case_order": case_ids,
        "arm_order": ["reference", "secant", "proposal"],
        "fresh_reference_each_fold": True,
        "material_capture_scope": "proposal-only" if capture else "all-arms",
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "abstention": "existing_reference_fallback"
        if proposal_abstention_strategy == "reference"
        else "secant_when_available_otherwise_reference",
        "proposal_abstention_strategy": proposal_abstention_strategy,
        "selection_score": "equal-case mean of proposal/secant measured path wall ratios; all fixed comparisons and known-work records required",
        "tie_break": "secant unless strict improvement; greatest ridge among exact learned score ties",
        "independent_evaluation": False,
        "source_label_authentication": False,
        "validation_or_holdout_execution": False,
        "new_training_labels": 0,
        "original_label_generation_cost_required_separately": True,
        "automatic_promotion": False,
    }
    if exclusion_groups is not None:
        plan["withholding_strategy"] = withholding_strategy
        plan["training_exclusion_groups"] = exclusion_groups
        plan["selection_score"] += (
            "; equal-case weighting retained across connected groups"
        )
    if static_model_abstention:
        plan["static_model_abstention"] = True
        plan["static_model_gate_profile"] = "rc-material-static-model-gate.v1"
        plan["selection_score"] += (
            "; static model gate computation and record write charged to proposal"
        )
    if repetitions > 1:
        plan["schema_version"] = "rc-control-runtime-selection-plan.v2"
        base_order = plan["arm_order"]
        plan["repetitions"] = repetitions
        plan["arm_order_schedule"] = [
            base_order[i % 3 :] + base_order[: i % 3] for i in range(repetitions)
        ]
        plan["fold_order"] = "ridge_then_withheld_case_then_repetition"
        plan["fit_reuse"] = "one_withheld_case_fit_frozen_across_repetitions"
        plan["warmup_repetitions_excluded"] = 0
        plan["repeats_are_independent_cases"] = False
        plan["selection_score"] = (
            "equal-case mean of within-case equal-repeat proposal/secant path ratios; "
            "every repeat must pass full comparisons and known-work checks; "
            "static gate computation and record writing charged when enabled"
        )
    if observe_initial_residuals:
        plan["observe_initial_residuals"] = True
        plan["selection_score"] += "; full residual/tangent observation costs included"
    if record_prior_accepted_transition_work:
        plan["record_prior_accepted_transition_work"] = True
        plan["selection_score"] += "; prior transition recording costs included"
    if proposal_guard_factory is not None:
        plan["proposal_guard_factory"] = {
            "identity": proposal_guard_factory_identity,
            "binding": "frozen_fold_seed_policy_and_exact_withheld_case_ids",
            "input_scope": "this_arm_accepted_parent_before_material_capture",
            "caller_identity_is_external_attestation": False,
            "bare_seed_refit_from_guarded_scores": False,
        }
        plan["selection_score"] += (
            "; caller guard setup and binding persistence charged to proposal time"
        )
    if full_training_pair_factory is not None:
        plan["full_training_pair_factory"] = {
            "identity": full_training_pair_factory_identity,
            "training_scope": "declared_training_only",
            "input_scope": "actual final seed and detached original TRAIN samples only",
            "maximum_final_seed_fits": 1,
            "maximum_final_gate_fits": 1,
            "caller_identity_is_external_attestation": False,
            "separate_locked_evaluation_required": True,
            "original_read_join_preparation_cost_required_separately": True,
        }
    if record_assembly_work:
        plan["assembly_work_recording"] = "vector-newton-assembly-dispatch-work.v1"
        plan["selection_score"] += "; opted-in assembly recording costs included"
    if record_assembly_timing:
        plan["assembly_timing_recording"] = True
        plan["selection_score"] += "; opted-in assembly timing costs included"
    if reuse_line_search_assembly:
        plan["line_search_assembly_reuse"] = "rc-control-immediate-line-search-reuse.v1"
        plan["selection_score"] += "; native reuse costs included for every control arm"
    plan["plan_hash"] = _sha(_bytes(plan))
    _save(root, "plan.json", _bytes(plan))
    fits: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    def fit(rows, ridge, purpose):
        if len(fits) >= maximum_fits:
            raise ValueError("declared fit budget exhausted")
        index = len(fits)
        stem = f"fit-{index:04d}"
        record = {
            "index": index,
            "ridge": ridge,
            "purpose": purpose,
            "training_sample_hashes": [r["sample_hash"] for r in rows],
            "status": "started",
            "unknown_fit_work_until_outcome": True,
        }
        fits.append(record)
        _save(root, stem + "-started.json", _bytes(record))
        fw, fc = perf_counter_ns(), process_time_ns()
        try:
            policy = learning._fit(
                rows,
                profile,
                ridge,
                source["ood_margin"],
                fit_solver=fit_solver,
            )
        except Exception as exc:
            record.update(
                status="raised",
                exception_kind=type(exc).__name__,
                wall_ns=perf_counter_ns() - fw,
                cpu_ns=process_time_ns() - fc,
            )
            _save(root, stem + "-outcome.json", _bytes(record))
            raise
        record.update(
            status="completed",
            unknown_fit_work_until_outcome=False,
            wall_ns=perf_counter_ns() - fw,
            cpu_ns=process_time_ns() - fc,
            policy_hash=policy.policy_hash,
            policy_file=stem + "-policy.json",
        )
        _save(root, record["policy_file"], _bytes(policy.to_dict()))
        _save(root, stem + "-outcome.json", _bytes(record))
        return policy, index

    for ridge in ridge_grid:
        candidate_folds = []
        for held in case_ids:
            case = training_cases[held]
            rows = [r for r in samples if r["case_id"] not in withheld[held]]
            purpose = {"withheld_training_case": held}
            if exclusion_groups is not None:
                purpose["withheld_training_group"] = withheld[held]
            policy, fit_index = fit(rows, ridge, purpose)
            frozen = _bytes(policy.to_dict())
            _, compiled, features, _, _ = prepared[held]
            frozen_guard_record = None
            for repetition in range(repetitions):
                decisions = []
                arm_order = tuple(
                    plan["arm_order"]
                    if repetitions == 1
                    else plan["arm_order_schedule"][repetition]
                )
                static_abstain = False

                def propose(context):
                    value = (
                        None
                        if static_abstain
                        else policy.propose(
                            context,
                            features,
                            compiled.problem.free_global_dofs,
                            case.request.solver_config.contract_hash,
                            arithmetic_profile=arithmetic_profile,
                            load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
                        )
                    )
                    decisions.append(
                        {
                            "accepted_prefix_count": len(context.accepted_targets_m),
                            "target_m": context.target_m,
                            "decision": (
                                "abstained_to_secant"
                                if proposal_abstention_strategy == "secant"
                                and learning.secant_seed(context) is not None
                                else "abstained_to_reference"
                            )
                            if value is None
                            else "proposed",
                        }
                    )
                    return value

                index = len(folds)
                stem = f"fold-{index:04d}"
                record = {
                    "index": index,
                    "withheld_training_case": held,
                    "ridge": ridge,
                    "fit_index": fit_index,
                    "policy_hash": policy.policy_hash,
                    "status": "started",
                    "unknown_work_until_outcome": True,
                }
                if repetitions > 1:
                    record.update(
                        repetition_index=repetition, arm_order=list(arm_order)
                    )
                folds.append(record)
                _save(root, stem + "-started.json", _bytes(record))
                fw, fc = perf_counter_ns(), process_time_ns()
                try:
                    setup_wall = None
                    if static_model_abstention:
                        gw, gc = perf_counter_ns(), process_time_ns()
                        gate = _static_material_model_gate(policy, features)
                        _save(root, stem + "-model-gate.json", _bytes(gate))
                        setup_wall = perf_counter_ns() - gw
                        record.update(
                            static_model_gate_hash=gate["gate_hash"],
                            static_model_gate_wall_ns=setup_wall,
                            static_model_gate_cpu_ns=process_time_ns() - gc,
                        )
                        static_abstain = gate["status"] == "rejected"
                    effective_capture = capture and not static_abstain
                    guard_kwargs = {}
                    if proposal_guard_factory is not None:
                        gw, gc = perf_counter_ns(), process_time_ns()
                        frozen_features = _bytes(features.to_dict())
                        excluded = tuple(withheld[held])
                        binding = proposal_guard_factory(
                            policy=policy,
                            model_features=features,
                            excluded_case_ids=excluded,
                        )
                        guard, guard_record = _validated_proposal_guard_binding(
                            binding, policy.policy_hash, excluded
                        )
                        if (
                            _bytes(policy.to_dict()) != frozen
                            or _bytes(features.to_dict()) != frozen_features
                        ):
                            raise ValueError(
                                "frozen fold inputs changed during guard setup"
                            )
                        guard_record["model_features_hash"] = _sha(frozen_features)
                        guard_bytes = _bytes(guard_record)
                        if frozen_guard_record is None:
                            frozen_guard_record = guard_bytes
                        elif guard_bytes != frozen_guard_record:
                            raise ValueError(
                                "frozen fold guard changed across repetitions"
                            )
                        _save(
                            root,
                            stem + "-proposal-guard-binding.json",
                            _bytes(guard_record),
                        )
                        guard_setup_wall = perf_counter_ns() - gw
                        record.update(
                            proposal_guard_binding=guard_record,
                            proposal_guard_setup_wall_ns=guard_setup_wall,
                            proposal_guard_setup_cpu_ns=process_time_ns() - gc,
                        )
                        setup_wall = (setup_wall or 0) + guard_setup_wall

                        guard_kwargs = {
                            "proposal_guard": guard,
                            "proposal_guard_identity": guard_record["guard_identity"],
                        }
                    if record_prior_accepted_transition_work:
                        guard_kwargs["record_prior_accepted_transition_work"] = True
                    report = learning.benchmark_rc_control_seed_paths(
                        case.model,
                        case.request,
                        source_revision=source_revision,
                        output_directory=root / stem,
                        proposal=propose,
                        proposal_identity=policy.policy_hash,
                        proposal_abstention_strategy=proposal_abstention_strategy,
                        arm_order=arm_order,
                        absolute_tolerance=1e-10,
                        relative_tolerance=1e-8,
                        capture_material_state=effective_capture,
                        material_capture_scope="proposal-only"
                        if effective_capture
                        else "all-arms",
                        record_assembly_work=record_assembly_work,
                        record_assembly_timing=record_assembly_timing,
                        reuse_line_search_assembly=reuse_line_search_assembly,
                        **guard_kwargs,
                        **(
                            {"observe_initial_residuals": True}
                            if observe_initial_residuals
                            else {}
                        ),
                        **learning._arithmetic_kwargs(arithmetic_profile),
                    )
                    if _bytes(policy.to_dict()) != frozen:
                        raise ValueError("frozen fold policy changed during execution")
                    if (
                        proposal_guard_factory is not None
                        and _bytes(features.to_dict()) != frozen_features
                    ):
                        raise ValueError(
                            "frozen fold model features changed during execution"
                        )
                    if proposal_guard_factory is not None:
                        # Runtime may decline an unavailable prior record before
                        # calling the guard. Count the actual arm ledger, including
                        # that decline, rather than only callback invocations.
                        decisions[:] = [
                            {
                                "accepted_prefix_count": entry["target_index"] + 1,
                                "target_m": entry["target_m"],
                                "decision": entry.get(
                                    "proposal_decision", "unresolved"
                                ),
                            }
                            for entry in report["arms"]["proposal"]["entries"]
                        ]
                        record["proposal_decision_source"] = (
                            "original_proposal_arm_entries"
                        )
                    score = _runtime_score(
                        report,
                        decisions,
                        proposal_setup_wall_ns=setup_wall,
                        **(
                            {"include_prior_work_source_setup": True}
                            if record_prior_accepted_transition_work
                            else {}
                        ),
                    )
                    if proposal_guard_factory is not None:
                        score["score_scope"] = score["score_scope"].replace(
                            "static model gate computation and record write added to proposal time",
                            "guard setup and binding write, plus enabled static gate setup, added to proposal time",
                        )
                except Exception as exc:
                    record.update(
                        status="raised",
                        exception_kind=type(exc).__name__,
                        wall_ns=perf_counter_ns() - fw,
                        cpu_ns=process_time_ns() - fc,
                    )
                    _save(root, stem + "-outcome.json", _bytes(record))
                    raise
                finally:
                    _save(root, stem + "-decisions.json", _bytes(decisions))
                record.update(
                    status="completed",
                    unknown_work_until_outcome=score["execution_work"]["unknown_work"],
                    wall_ns=perf_counter_ns() - fw,
                    cpu_ns=process_time_ns() - fc,
                    report_hash=report["report_hash"],
                    score=score,
                )
                _save(root, stem + "-outcome.json", _bytes(record))
                candidate_folds.append(record)
                known_calls = sum(
                    f.get("score", {})
                    .get("execution_work", {})
                    .get("known_work", {})
                    .get("core_calls", 0)
                    for f in folds
                )
                if (
                    record["unknown_work_until_outcome"]
                    or known_calls > maximum_core_calls
                ):
                    raise ValueError(
                        "unaccounted work or declared core-call budget exhausted"
                    )
        ratios = [
            f["score"]["proposal_over_secant_path_wall_ratio"] for f in candidate_folds
        ]
        score = None if any(r is None for r in ratios) else float(np.mean(ratios))
        candidates.append(
            {
                "ridge": ridge,
                "score": score,
                "proposed_count": sum(
                    f["score"]["proposed_count"] for f in candidate_folds
                ),
                "fold_indices": [f["index"] for f in candidate_folds],
            }
        )
        if repetitions > 1:
            repeated_cases = []
            for held in case_ids:
                records = [
                    f for f in candidate_folds if f["withheld_training_case"] == held
                ]
                values = [
                    f["score"]["proposal_over_secant_path_wall_ratio"] for f in records
                ]
                valid = all(v is not None for v in values)
                repeated_cases.append(
                    {
                        "case_id": held,
                        "fold_indices": [f["index"] for f in records],
                        "ratios": values,
                        "requested_repetitions": repetitions,
                        "valid_repetitions": sum(v is not None for v in values),
                        "mean_ratio": float(np.mean(values)) if valid else None,
                        "minimum_ratio": min(values) if valid else None,
                        "maximum_ratio": max(values) if valid else None,
                        "sample_standard_deviation": float(np.std(values, ddof=1))
                        if valid
                        else None,
                    }
                )
            candidates[-1]["case_repeat_scores"] = repeated_cases
            candidates[-1]["score"] = (
                float(np.mean([c["mean_ratio"] for c in repeated_cases]))
                if all(c["mean_ratio"] is not None for c in repeated_cases)
                else None
            )
    eligible = [
        c
        for c in candidates
        if c["score"] is not None
        and c["score"] < 1 - minimum_relative_improvement
        and c["proposed_count"] > 0
    ]
    winner = (
        min(eligible, key=lambda c: (c["score"], -c["ridge"])) if eligible else None
    )
    selected = None
    selected_pair = None
    final_pair_refit = None
    if winner is not None and proposal_guard_factory is None:
        selected, _ = fit(
            samples, winner["ridge"], {"selected_full_training_refit": True}
        )
    if full_training_pair_factory is not None:
        final_pair_refit = {"status": "not_attempted", "reason": "no_guarded_winner"}
        if winner is not None:
            pw, pc = perf_counter_ns(), process_time_ns()
            phase = "final_seed_fit"
            try:
                frozen_samples = frozen_training_samples
                if (
                    _bytes(samples) != frozen_samples
                    or _bytes(original_policy.to_dict()) != frozen_source_policy
                ):
                    raise ValueError(
                        "frozen original full-training inputs changed during folds"
                    )
                final_seed, seed_index = fit(
                    samples,
                    winner["ridge"],
                    {"selected_full_training_pair_seed_refit": True},
                )
                frozen_seed = _bytes(final_seed.to_dict())
                if _bytes(samples) != frozen_samples:
                    raise ValueError(
                        "frozen full-training samples changed during seed fit"
                    )
                phase = "final_gate_fit"
                index = len(fits)
                if index >= maximum_fits:
                    raise ValueError("declared fit budget exhausted")
                stem = f"fit-{index:04d}"
                record = {
                    "index": index,
                    "purpose": {"selected_full_training_pair_gate_refit": True},
                    "seed_fit_index": seed_index,
                    "seed_policy_hash": final_seed.policy_hash,
                    "training_sample_hashes": [r["sample_hash"] for r in samples],
                    "status": "started",
                    "unknown_fit_work_until_outcome": True,
                }
                fits.append(record)
                _save(root, stem + "-started.json", _bytes(record))
                fw, fc = perf_counter_ns(), process_time_ns()
                try:
                    detached_samples = deepcopy(samples)
                    binding = full_training_pair_factory(
                        policy=final_seed, training_samples=detached_samples
                    )
                    if (
                        _bytes(final_seed.to_dict()) != frozen_seed
                        or _bytes(samples) != frozen_samples
                        or _bytes(detached_samples) != frozen_samples
                        or _bytes(original_policy.to_dict()) != frozen_source_policy
                    ):
                        raise ValueError(
                            "frozen full-training inputs changed during pair factory"
                        )
                    binding = _validated_full_training_pair(
                        binding, final_seed, record["training_sample_hashes"]
                    )
                except Exception as exc:
                    record.update(
                        status="raised",
                        exception_kind=type(exc).__name__,
                        wall_ns=perf_counter_ns() - fw,
                        cpu_ns=process_time_ns() - fc,
                    )
                    _save(root, stem + "-outcome.json", _bytes(record))
                    raise
                record.update(
                    status="completed",
                    unknown_fit_work_until_outcome=False,
                    wall_ns=perf_counter_ns() - fw,
                    cpu_ns=process_time_ns() - fc,
                    policy_hash=binding["gate_policy_hash"],
                    policy_file=stem + "-gate-policy.json",
                    fit_receipt=binding["fit_receipt"],
                )
                _save(root, record["policy_file"], _bytes(binding["gate_policy"]))
                _save(root, stem + "-outcome.json", _bytes(record))
                phase = "pair_persistence"
                pair = {
                    "schema_version": "rc-control-full-training-seed-prior-work-pair.v1",
                    **binding,
                    "seed_policy": json.loads(frozen_seed),
                    "source_revision": source_revision,
                    "source_policy_hash": original_policy.policy_hash,
                    "factory_identity": full_training_pair_factory_identity,
                    "seed_fit_index": seed_index,
                    "gate_fit_index": index,
                    "independent_evaluation": False,
                    "source_authenticity": False,
                    "historical_training_admitted": False,
                    "full_path_gain_proved": False,
                }
                pair["pair_hash"] = _sha(_bytes(pair))
                _save(root, "selected-pair.json", _bytes(pair))
                selected_pair = pair
                final_pair_refit = {
                    "status": "completed",
                    "pair_hash": pair["pair_hash"],
                    "pair_file": "selected-pair.json",
                    "unknown_work": False,
                }
            except Exception as exc:
                final_pair_refit = {
                    "status": "raised",
                    "failed_phase": phase,
                    "exception_kind": type(exc).__name__,
                    "unknown_work": True,
                }
            final_pair_refit.update(
                wall_ns=perf_counter_ns() - pw,
                cpu_ns=process_time_ns() - pc,
                timing_scope="final seed fit and gate callback validation and pair persistence; fit record clocks are nested",
            )
    result = {
        "schema_version": "rc-control-runtime-selection-result.v1",
        "source_revision": source_revision,
        "plan_hash": plan["plan_hash"],
        "candidates": candidates,
        "folds": folds,
        "fit_records": fits,
        "fit_attempt_count": len(fits),
        "fit_completed_count": sum(f["status"] == "completed" for f in fits),
        "selected_strategy": "guarded_seed_prior_work_pair"
        if selected_pair is not None
        else "secant"
        if selected is None
        else "learned_svd",
        "selected_ridge": None
        if selected is None and selected_pair is None
        else winner["ridge"],
        "selected_score": 1.0
        if selected is None and selected_pair is None
        else winner["score"],
        "selected_policy": None if selected is None else selected.to_dict(),
        "proposal_abstention_strategy": proposal_abstention_strategy,
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "timing_scope": "validation_fits_all_four_path_fold_runs_comparisons_and_intermediate_IO_excluding_final_result_write",
        "new_training_labels": 0,
        "validation_or_holdout_execution": False,
        "independent_evaluation": False,
        "net_savings_proved": False,
        "candidate_promoted": False,
    }
    if observe_initial_residuals:
        result["observe_initial_residuals"] = True
    if record_prior_accepted_transition_work:
        result["record_prior_accepted_transition_work"] = True
    if proposal_guard_factory is not None:
        result["proposal_guard_factory"] = plan["proposal_guard_factory"]
        result["guarded_fold_winner"] = winner
        result["guarded_policy_refit_performed"] = False
        result["guarded_deployment_artifact_required"] = (
            "a separately bound full-training seed-plus-guard policy; fold scores do not qualify the bare seed"
        )
    if full_training_pair_factory is not None:
        result["full_training_pair_factory"] = plan["full_training_pair_factory"]
        result["selected_pair"] = selected_pair
        result["final_pair_refit"] = final_pair_refit
        result["guarded_policy_refit_performed"] = selected_pair is not None
        result["selected_score_scope"] = (
            "guarded development fold score; final pair has not been evaluated"
        )
        result["timing_scope"] += (
            "; enabled final seed and gate fits, validation and pair persistence included; original read/join preparation cost required separately"
        )
    if reuse_line_search_assembly:
        result["line_search_assembly_reuse"] = plan["line_search_assembly_reuse"]
    if record_assembly_timing:
        result["assembly_timing_recording"] = True
    if record_assembly_work:
        result["assembly_work_recording"] = plan["assembly_work_recording"]
    if static_model_abstention:
        result["static_model_abstention"] = True
    if repetitions > 1:
        result["schema_version"] = "rc-control-runtime-selection-result.v2"
        result["repetitions"] = repetitions
        result["arm_order_schedule"] = plan["arm_order_schedule"]
        result["repeats_are_independent_cases"] = False
    result["result_hash"] = _sha(_bytes(result))
    _save(root, "result.json", _bytes(result))
    return result
