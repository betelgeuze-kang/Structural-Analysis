"""Select a development ridge candidate using complete withheld-training-case paths.

Runtime fold scores are tuning evidence, not independent evaluation or net savings.
Original solver-produced labels and their generation costs remain required inputs.
"""

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


def _runtime_score(report, decisions):
    """Keep failed or unaccounted paths ineligible, including the fresh reference."""
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
    return {
        "full_comparison_pass": bool(physical),
        "proposal_over_secant_path_wall_ratio": proposed / baseline
        if physical
        else None,
        "secant_path_wall_ns": baseline,
        "proposal_path_wall_ns": proposed,
        "proposed_count": sum(d["decision"] == "proposed" for d in decisions),
        "abstained_count": sum(
            d["decision"] == "abstained_to_reference" for d in decisions
        ),
        "execution_work": learning._execution_work([{"report": report}]),
        "whole_benchmark_wall_ns": report["whole_study_wall_ns"],
        "score_scope": "whole path including input capture, inference, numerical retries, recovery and step IO; final path file write excluded",
    }


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
):
    """Fit each ridge without one training case, then execute that case's full path.

    All original cases enter the existing leakage preflight. Only cases already
    declared train may be fitted or executed here; validation/holdout outputs are
    untouched. Whole-case exclusion is internal tuning, not an independent split.
    No structural labels are regenerated. Bounds cover every path and possible
    proposal retry before the first fit or output is created.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
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
    source, grouped, profile = _validated_training_data(samples, original_policy)
    measured: dict[str, Any] = {}
    prepared = learning._preflight(
        cases, arithmetic_profile, measurement_screen=measured
    )
    training_cases = _validate_case_rows(
        cases, prepared, grouped, source, arithmetic_profile
    )
    case_ids = sorted(training_cases)
    fit_bound = len(case_ids) * len(ridge_grid) + 1
    # Each case has three experimental arms and a fresh reference. Only the
    # proposer may retry a target once; constant preload runs once per path.
    core_bound = len(ridge_grid) * sum(
        5 * len(c.request.targets_m) + 4 * bool(c.request.constant_nodal_loads)
        for c in training_cases.values()
    )
    if fit_bound > maximum_fits or core_bound > maximum_core_calls:
        raise ValueError(
            f"runtime selection requires budgets for {fit_bound} fits and up to {core_bound} core calls"
        )
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    capture = source.get("feature_profile") == MATERIAL_FEATURE_PROFILE
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
        "fit_solver_profile": learning.SVD_RIDGE_FIT_PROFILE,
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
        "abstention": "existing_reference_fallback",
        "selection_score": "equal-case mean of proposal/secant measured path wall ratios; all fixed comparisons and known-work records required",
        "tie_break": "secant unless strict improvement; greatest ridge among exact learned score ties",
        "independent_evaluation": False,
        "source_label_authentication": False,
        "validation_or_holdout_execution": False,
        "new_training_labels": 0,
        "original_label_generation_cost_required_separately": True,
        "automatic_promotion": False,
    }
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
                fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
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
            rows = [r for r in samples if r["case_id"] != held]
            policy, fit_index = fit(rows, ridge, {"withheld_training_case": held})
            frozen = _bytes(policy.to_dict())
            _, compiled, features, _, _ = prepared[held]
            decisions = []

            def propose(context):
                value = policy.propose(
                    context,
                    features,
                    compiled.problem.free_global_dofs,
                    case.request.solver_config.contract_hash,
                    arithmetic_profile=arithmetic_profile,
                    load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
                )
                decisions.append(
                    {
                        "accepted_prefix_count": len(context.accepted_targets_m),
                        "target_m": context.target_m,
                        "decision": "abstained_to_reference"
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
            folds.append(record)
            _save(root, stem + "-started.json", _bytes(record))
            fw, fc = perf_counter_ns(), process_time_ns()
            try:
                report = learning.benchmark_rc_control_seed_paths(
                    case.model,
                    case.request,
                    source_revision=source_revision,
                    output_directory=root / stem,
                    proposal=propose,
                    proposal_identity=policy.policy_hash,
                    arm_order=tuple(plan["arm_order"]),
                    absolute_tolerance=1e-10,
                    relative_tolerance=1e-8,
                    capture_material_state=capture,
                    material_capture_scope=plan["material_capture_scope"],
                    **learning._arithmetic_kwargs(arithmetic_profile),
                )
                if _bytes(policy.to_dict()) != frozen:
                    raise ValueError("frozen fold policy changed during execution")
                score = _runtime_score(report, decisions)
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
            if record["unknown_work_until_outcome"] or known_calls > maximum_core_calls:
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
    if winner is not None:
        selected, _ = fit(
            samples, winner["ridge"], {"selected_full_training_refit": True}
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
        "selected_strategy": "secant" if winner is None else "learned_svd",
        "selected_ridge": None if winner is None else winner["ridge"],
        "selected_score": 1.0 if winner is None else winner["score"],
        "selected_policy": None if selected is None else selected.to_dict(),
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "timing_scope": "validation_fits_all_four_path_fold_runs_comparisons_and_intermediate_IO_excluding_final_result_write",
        "new_training_labels": 0,
        "validation_or_holdout_execution": False,
        "independent_evaluation": False,
        "net_savings_proved": False,
        "candidate_promoted": False,
    }
    result["result_hash"] = _sha(_bytes(result))
    _save(root, "result.json", _bytes(result))
    return result
