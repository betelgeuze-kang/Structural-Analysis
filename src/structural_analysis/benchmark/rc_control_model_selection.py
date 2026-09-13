"""Nested training-case selection of fixed-grid SVD ridge corrections.

This selects a development candidate, not an accepted structural result. Scores
are correction losses before runtime abstention, not simulated runtime savings.
"""

from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

import numpy as np

from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_learning import (
    RCControlSeedPolicy,
    SVD_RIDGE_FIT_PROFILE,
    _fit,
)
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
)
from structural_analysis.benchmark.rc_control_training_diagnostics import (
    _validated_training_data,
)


DEFAULT_RIDGE_GRID = (1e-6, 1e-4, 1e-2, 1.0, 1e2, 1e4, 1e6)


def _correction_score(rows, policy=None, *, feature_profile=None):
    """Use fitted train scales for loss; also retain original-coordinate RMSE."""
    started, cpu = perf_counter_ns(), process_time_ns()
    y = np.asarray([row["correction"] for row in rows], dtype=float)
    p = None if policy is None else policy.to_dict()
    history = (
        feature_profile if p is None else p.get("feature_profile")
    ) == HISTORY_FEATURE_PROFILE
    original = np.asarray(
        [row["source_correction"] if history else row["correction"] for row in rows],
        dtype=float,
    )
    result = {
        "sample_hashes": [row["sample_hash"] for row in rows],
        "sample_count": len(rows),
        "secant_rmse_original_coordinates": np.sqrt(
            np.mean(original**2, axis=0)
        ).tolist(),
    }
    if p is None:
        result.update(
            relative_correction_loss=1.0,
            learned_loss_in_training_target_scales=None,
            secant_loss_in_training_target_scales=None,
            learned_rmse_original_coordinates=result[
                "secant_rmse_original_coordinates"
            ],
            range_eligible_count=None,
        )
    else:
        x = np.asarray([row["features"] for row in rows], dtype=float)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            z = np.column_stack(
                [(x - p["feature_mean"]) / p["feature_scale"], np.ones(len(rows))]
            )
            prediction = (z @ np.asarray(p["weights"])) * p["target_scale"]
            prediction[:, p["control_free_index"]] = 0.0
            keep = np.arange(y.shape[1]) != p["control_free_index"]
            error = (prediction - y)[:, keep] / np.asarray(p["target_scale"])[keep]
            baseline = y[:, keep] / np.asarray(p["target_scale"])[keep]
            loss, baseline_loss = float(np.mean(error**2)), float(np.mean(baseline**2))
            relative = (
                loss / baseline_loss if baseline_loss else 1.0 if loss == 0 else None
            )
            if relative is not None and not np.isfinite(relative):
                raise ValueError("nonfinite relative correction loss")
            if p.get("feature_profile") == HISTORY_FEATURE_PROFILE:
                prediction *= np.asarray(
                    [row["correction_coordinate_scales"] for row in rows]
                )
            low, high = np.asarray(p["feature_min"]), np.asarray(p["feature_max"])
            slack = np.maximum((high - low) * p["ood_margin"], 1e-12)
            eligible = ~np.any((x < low - slack) | (x > high + slack), axis=1)
            result.update(
                relative_correction_loss=relative,
                relative_loss_unavailable_reason="nonzero_error_against_exact_zero_secant_loss"
                if relative is None
                else None,
                learned_loss_in_training_target_scales=loss,
                secant_loss_in_training_target_scales=baseline_loss,
                learned_rmse_original_coordinates=np.sqrt(
                    np.mean((prediction - original) ** 2, axis=0)
                ).tolist(),
                range_eligible_count=int(eligible.sum()),
            )
    result.update(wall_ns=perf_counter_ns() - started, cpu_ns=process_time_ns() - cpu)
    _bytes(result)
    return result


def run_rc_control_nested_selection(
    samples,
    original_policy: RCControlSeedPolicy,
    *,
    source_revision,
    output_directory,
    ridge_grid=DEFAULT_RIDGE_GRID,
    minimum_relative_improvement=0.01,
    maximum_fits=256,
):
    """Choose ridge on inner cases, evaluate on an untouched outer training case.

    The source policy supplies static layout metadata and original row identities;
    its fitted weights and preprocessing never enter selection. All rows must be
    from the declared training split. Persist each fit reservation/outcome before
    proceeding; interruption leaves explicit unfinished reservations.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ):
        raise ValueError("exact source revision required")
    if (
        type(ridge_grid) is not tuple
        or not 2 <= len(ridge_grid) <= 16
        or any(
            type(v) not in (int, float) or not np.isfinite(v) or v <= 0
            for v in ridge_grid
        )
        or any(a >= b for a, b in zip(ridge_grid, ridge_grid[1:]))
    ):
        raise ValueError(
            "two to sixteen increasing positive finite ridge values required"
        )
    if (
        type(minimum_relative_improvement) not in (int, float)
        or not np.isfinite(minimum_relative_improvement)
        or not 0 <= minimum_relative_improvement < 1
        or type(maximum_fits) is not int
        or not 1 <= maximum_fits <= 32768
    ):
        raise ValueError("bounded improvement and explicit fit budget required")
    source, grouped, profile = _validated_training_data(samples, original_policy)
    case_ids = sorted(grouped)
    if (
        len(case_ids) < 3
        or len(samples) - sum(sorted(map(len, grouped.values()))[-2:]) < 2
    ):
        raise ValueError(
            "nested selection needs three cases and two rows in every innermost fit"
        )
    required = len(case_ids) ** 2 * len(ridge_grid) + len(case_ids) + 1
    if required > maximum_fits:
        raise ValueError(f"nested selection requires budget for up to {required} fits")
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    plan = {
        "schema_version": "rc-control-nested-selection-plan.v1",
        "source_revision": source_revision,
        "source_policy_hash": original_policy.policy_hash,
        "source_policy_weights_and_preprocessing_used_for_selection": False,
        "training_sample_hashes": source["training_sample_hashes"],
        "case_sample_hashes": {
            k: [r["sample_hash"] for r in grouped[k]] for k in case_ids
        },
        "fit_solver_profile": SVD_RIDGE_FIT_PROFILE,
        "ridge_grid": list(ridge_grid),
        "ood_margin": source["ood_margin"],
        "minimum_relative_improvement": minimum_relative_improvement,
        "maximum_fits": maximum_fits,
        "maximum_required_fit_count": required,
        "score": "equal-case mean of learned/secant MSE ratios in each fit's training-target scales; controlled coordinate excluded",
        "baseline": "zero-correction secant",
        "tie_break": "secant unless strict minimum improvement; greatest ridge among exactly tied learned scores",
        "runtime_abstention_simulated": False,
        "range_coverage_is_diagnostic_only": True,
        "independent_campaign_split": False,
        "automatic_policy_promotion": False,
    }
    plan["plan_hash"] = _sha(_bytes(plan))
    _save(root, "plan.json", _bytes(plan))
    records: list[dict[str, Any]] = []

    def fit(rows, ridge, purpose):
        if len(records) >= maximum_fits:
            raise ValueError("declared fit budget exhausted")
        index = len(records)
        stem = f"fit-{index:04d}"
        record = {
            "index": index,
            "purpose": purpose,
            "ridge": ridge,
            "training_sample_hashes": [r["sample_hash"] for r in rows],
            "status": "started",
            "unknown_fit_work_until_outcome": True,
        }
        records.append(record)
        _save(root, stem + "-started.json", _bytes(record))
        fw, fc = perf_counter_ns(), process_time_ns()
        try:
            fitted = _fit(
                rows,
                profile,
                ridge,
                source["ood_margin"],
                fit_solver=SVD_RIDGE_FIT_PROFILE,
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
            policy_hash=fitted.policy_hash,
            policy_file=stem + "-policy.json",
        )
        _save(root, record["policy_file"], _bytes(fitted.to_dict()))
        _save(root, stem + "-outcome.json", _bytes(record))
        return fitted, index

    def select(rows, purpose):
        ids = sorted({r["case_id"] for r in rows})
        candidates = []
        for ridge in ridge_grid:
            folds = []
            for held in ids:
                training = [r for r in rows if r["case_id"] != held]
                withheld = [r for r in rows if r["case_id"] == held]
                fitted, index = fit(
                    training, ridge, {"selection": purpose, "inner_withheld_case": held}
                )
                metrics = _correction_score(withheld, fitted)
                fold = {
                    "withheld_case_id": held,
                    "fit_index": index,
                    "metrics": metrics,
                }
                _save(root, f"fit-{index:04d}-score.json", _bytes(fold))
                folds.append(fold)
            losses = [f["metrics"]["relative_correction_loss"] for f in folds]
            score = None if any(v is None for v in losses) else float(np.mean(losses))
            candidates.append({"ridge": ridge, "score": score, "folds": folds})
        eligible = [
            c
            for c in candidates
            if c["score"] is not None and c["score"] < 1 - minimum_relative_improvement
        ]
        winner = (
            min(eligible, key=lambda c: (c["score"], -c["ridge"])) if eligible else None
        )
        selection = {
            "purpose": purpose,
            "case_ids": ids,
            "candidates": candidates,
            "selected_strategy": "secant" if winner is None else "learned_svd",
            "selected_ridge": None if winner is None else winner["ridge"],
            "selected_inner_score": 1.0 if winner is None else winner["score"],
            "policy": None,
            "refit_index": None,
        }
        if winner is not None:
            fitted, index = fit(
                rows, winner["ridge"], {"selection": purpose, "phase": "selected_refit"}
            )
            selection.update(policy=fitted.to_dict(), refit_index=index)
        return selection

    outer = []
    for held in case_ids:
        training = [row for row in samples if row["case_id"] != held]
        selection = select(training, {"outer_withheld_case": held})
        chosen = (
            None
            if selection["policy"] is None
            else RCControlSeedPolicy(_bytes(selection["policy"]).decode())
        )
        metrics = _correction_score(
            grouped[held], chosen, feature_profile=source.get("feature_profile")
        )
        row = {
            "withheld_training_case_id": held,
            "selection": selection,
            "outer_metrics": metrics,
        }
        outer.append(row)
        _save(root, f"outer-{len(outer) - 1:02d}.json", _bytes(row))
    final = select(samples, {"full_training_selection": True})
    _save(root, "full-training-selection.json", _bytes(final))
    result = {
        "schema_version": "rc-control-nested-selection-result.v1",
        "plan_hash": plan["plan_hash"],
        "source_revision": source_revision,
        "outer_folds": outer,
        "full_training_selection": final,
        "fit_records": records,
        "fit_attempt_count": len(records),
        "fit_completed_count": sum(r["status"] == "completed" for r in records),
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "timing_scope": "validation_all_fits_scores_and_intermediate_io_excluding_final_result_write",
        "structural_solver_calls": 0,
        "material_integrations": 0,
        "runtime_speedup_evidence": False,
        "independent_validation": False,
        "candidate_promoted": False,
    }
    result["result_hash"] = _sha(_bytes(result))
    _save(root, "result.json", _bytes(result))
    return result
