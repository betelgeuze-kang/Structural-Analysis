"""Case-withheld diagnostics on original train rows, without structural solves."""

from __future__ import annotations

from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import (
    RCControlSeedPolicy,
    _fit,
    NORMAL_RIDGE_FIT_PROFILE,
)
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
    HISTORY_FEATURE_NAMES,
)
from structural_analysis.benchmark.rc_control_material_features import (
    MATERIAL_FEATURE_PROFILE,
)


def audit_rc_control_training_folds(
    samples: list[dict[str, Any]], original_policy: RCControlSeedPolicy
) -> dict[str, Any]:
    """Refit fixed hyperparameters with each authored training case withheld.

    The original policy binds the sample identities and fixed hyperparameters.
    Its weights, scales and feature bounds never enter a withheld-case fit.
    This is development diagnosis within training data, not a new external split,
    a structural acceptance test, or a runtime performance measurement.
    """
    started = perf_counter_ns()
    if type(original_policy) is not RCControlSeedPolicy:
        raise ValueError("original typed RC control policy required")
    if type(samples) is not list or not 4 <= len(samples) <= 8160:
        raise ValueError("four to 8160 original training samples required")
    policy = original_policy.to_dict()
    history_profile = policy.get("feature_profile") == HISTORY_FEATURE_PROFILE
    material_profile = policy.get("feature_profile") == MATERIAL_FEATURE_PROFILE
    width = len(policy["feature_mean"])
    count = len(policy["target_scale"])
    hashes = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        if type(sample) is not dict or sample.get("split") != "train":
            raise ValueError("only original train rows may enter fold diagnostics")
        case = sample.get("case_id")
        if type(case) is not str or not case or len(case) > 128:
            raise ValueError("training case identity required")
        digest = sample.get("sample_hash")
        if digest != _sha(
            _bytes({k: v for k, v in sample.items() if k != "sample_hash"})
        ):
            raise ValueError("original training sample hash mismatch")
        for key, shape in (("features", (width,)), ("correction", (count,))):
            value = sample.get(key)
            if type(value) is not list or any(
                type(x) not in (int, float) for x in value
            ):
                raise ValueError("finite original training arrays required")
            array = np.asarray(value, dtype=float)
            if array.shape != shape or not np.all(np.isfinite(array)):
                raise ValueError("finite matching training arrays required")
        if (
            material_profile
            and sample.get("feature_profile") != MATERIAL_FEATURE_PROFILE
        ):
            raise ValueError("material-policy sample feature profile required")
        if history_profile:
            if sample.get("feature_profile") != HISTORY_FEATURE_PROFILE:
                raise ValueError("history-policy sample feature profile required")
            for key in ("source_correction", "correction_coordinate_scales"):
                value = sample.get(key)
                if type(value) is not list or any(
                    type(x) not in (int, float) for x in value
                ):
                    raise ValueError("source correction and coordinate scales required")
                array = np.asarray(value, dtype=float)
                if array.shape != (count,) or not np.all(np.isfinite(array)):
                    raise ValueError(
                        "matching finite source correction and scales required"
                    )
                if key == "correction_coordinate_scales" and np.any(array <= 0):
                    raise ValueError("positive correction-coordinate scales required")
            if not np.array_equal(
                np.asarray(sample["source_correction"])
                / sample["correction_coordinate_scales"],
                sample["correction"],
            ):
                raise ValueError(
                    "normalized correction differs from original coordinates"
                )
        hashes.append(digest)
        grouped.setdefault(case, []).append(sample)
    if len(set(hashes)) != len(hashes) or hashes != policy["training_sample_hashes"]:
        raise ValueError("exact ordered original policy sample identities required")
    if not 2 <= len(grouped) <= 32:
        raise ValueError("two to 32 original training cases required")
    if any(len(samples) - len(rows) < 2 for rows in grouped.values()):
        raise ValueError("each fold needs at least two remaining training rows")
    profile = {
        key: policy[key]
        for key in (
            "model_context_hash",
            "model_feature_names",
            "free_global_dofs",
            "control_free_index",
            "solver_config_hash",
        )
    }
    if "arithmetic_profile" in policy:
        profile["arithmetic_profile"] = policy["arithmetic_profile"]
    if history_profile:
        profile.update(
            feature_profile=HISTORY_FEATURE_PROFILE,
            load_factor_coordinate_scale_m=policy["load_factor_coordinate_scale_m"],
        )
    if material_profile:
        profile.update(
            feature_profile=MATERIAL_FEATURE_PROFILE,
            material_feature_names=policy["material_feature_names"],
        )
    feature_names = (
        list(policy["model_feature_names"])
        + [
            "target_m",
            "next_control_increment_m",
            "previous_control_increment_m",
            "accepted_step_count",
        ]
        + [f"accepted_augmented_coordinate_{i}" for i in range(count)]
        + [f"previous_augmented_increment_{i}" for i in range(count)]
    )
    if history_profile:
        feature_names = (
            ["normalized_" + name for name in policy["model_feature_names"]]
            + [
                "normalized_target",
                "normalized_next_increment",
                "normalized_previous_increment",
            ]
            + [f"normalized_accepted_coordinate_{i}" for i in range(count)]
            + [f"normalized_previous_increment_{i}" for i in range(count)]
            + list(HISTORY_FEATURE_NAMES)
        )
    if material_profile:
        feature_names += policy["material_feature_names"]
    folds = []
    for case in sorted(grouped):
        training = [row for row in samples if row["case_id"] != case]
        withheld = grouped[case]
        fit_started = perf_counter_ns()
        fitted = _fit(
            training,
            profile,
            policy["ridge"],
            policy["ood_margin"],
            fit_solver=policy.get("fit_solver_profile", NORMAL_RIDGE_FIT_PROFILE),
        )
        fit_wall_ns = perf_counter_ns() - fit_started
        fitted_payload = fitted.to_dict()
        prediction_started = perf_counter_ns()
        x = np.asarray([row["features"] for row in withheld])
        y = np.asarray([row["correction"] for row in withheld])
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            low = np.asarray(fitted_payload["feature_min"])
            high = np.asarray(fitted_payload["feature_max"])
            slack = np.maximum((high - low) * fitted_payload["ood_margin"], 1e-12)
            violations = (x < low - slack) | (x > high + slack)
            range_eligible = ~np.any(violations, axis=1)
            z = np.column_stack(
                [
                    (x - fitted_payload["feature_mean"])
                    / fitted_payload["feature_scale"],
                    np.ones(len(withheld)),
                ]
            )
            prediction = (z @ np.asarray(fitted_payload["weights"])) * fitted_payload[
                "target_scale"
            ]
            # Runtime always resets the prescribed coordinate to its target.
            prediction[:, policy["control_free_index"]] = 0.0
            if history_profile:
                prediction *= np.asarray(
                    [row["correction_coordinate_scales"] for row in withheld]
                )
                y = np.asarray([row["source_correction"] for row in withheld])
            error = prediction - y
            if not np.all(np.isfinite(error)):
                raise ValueError("nonfinite diagnostic predictions")

            def metrics(mask):
                size = int(np.count_nonzero(mask))
                if not size:
                    return {
                        "sample_count": 0,
                        "secant_rmse": None,
                        "learned_rmse": None,
                    }
                return {
                    "sample_count": size,
                    "secant_rmse": np.sqrt(np.mean(y[mask] ** 2, axis=0)).tolist(),
                    "learned_rmse": np.sqrt(np.mean(error[mask] ** 2, axis=0)).tolist(),
                }

            all_metrics = metrics(np.ones(len(y), dtype=bool))
            eligible_metrics = metrics(range_eligible)
        folds.append(
            {
                "withheld_training_case_id": case,
                "training_case_ids": sorted({row["case_id"] for row in training}),
                "withheld_sample_hashes": [row["sample_hash"] for row in withheld],
                "fitted_policy": fitted_payload,
                "fit_wall_ns": fit_wall_ns,
                "prediction_and_metrics_wall_ns": perf_counter_ns()
                - prediction_started,
                "range_eligible_count": int(np.count_nonzero(range_eligible)),
                "ood_sample_count": int(np.count_nonzero(~range_eligible)),
                "range_violations_by_feature": {
                    name: int(total)
                    for name, total in zip(
                        feature_names, violations.sum(axis=0), strict=True
                    )
                    if total
                },
                "ungated_diagnostic_only": all_metrics,
                "range_eligible_diagnostic_only": eligible_metrics,
            }
        )
    result = {
        "schema_version": "experimental-rc-control-train-fold-diagnostics.v1",
        "original_policy_hash": original_policy.policy_hash,
        **(
            {"fit_solver_profile": policy["fit_solver_profile"]}
            if "fit_solver_profile" in policy
            else {}
        ),
        **({"feature_profile": HISTORY_FEATURE_PROFILE} if history_profile else {}),
        **({"feature_profile": MATERIAL_FEATURE_PROFILE} if material_profile else {}),
        "original_training_sample_hashes": hashes,
        "coordinate_order": [
            *policy["free_global_dofs"],
            "scaled_load_factor_coordinate",
        ],
        "metric_units": "original_augmented_solver_coordinate_units; per-coordinate RMSE",
        "folds": folds,
        "fixed_ridge": policy["ridge"],
        "fixed_ood_margin": policy["ood_margin"],
        "diagnostic_wall_ns": perf_counter_ns() - started,
        "structural_solver_calls": 0,
        "fit_count": len(folds),
        "external_validation": False,
        "independent_project_split": False,
        "runtime_speedup_evidence": False,
        "policy_promoted": False,
    }
    # Refuse accidental nonfinite metrics instead of emitting nonstandard JSON.
    _bytes(result)
    return result
