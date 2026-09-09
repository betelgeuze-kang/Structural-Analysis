"""Length-normalized RC inputs and already accepted control-history features."""

from __future__ import annotations

from copy import deepcopy
import numpy as np

from structural_analysis.ai.fiber_frame_warm_start_features import (
    FiberFrameWarmStartModelFeatures,
)
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext


HISTORY_FEATURE_PROFILE = "length-normalized-accepted-control-history.v1"
HISTORY_FEATURE_NAMES = (
    "accepted_control_min",
    "accepted_control_max",
    "accepted_control_travel",
    "accepted_reversal_count",
    "accepted_branch_direction",
    "last_reversal_control",
    "branch_control_travel",
    "next_control_direction",
)


def control_history_features(context, model_features, load_factor_coordinate_scale_m):
    """Return features and correction scales using no future response or trial.

    Spatial solver coordinates have length units (including scaled rotations).
    Their divisor is the declared rotation-coordinate length; the augmented load
    coordinate uses its separately declared scale. Reference forces/moments are
    expressed per length squared/cubed, not asserted to be dimensionless.
    """
    if (
        type(context) is not RCControlSeedContext
        or type(model_features) is not FiberFrameWarmStartModelFeatures
    ):
        raise ValueError("typed original context and model features required")
    if context.problem_contract_hash != model_features.problem_contract_hash:
        raise ValueError("context and compiled model must match")
    if (
        type(load_factor_coordinate_scale_m) not in (int, float)
        or not np.isfinite(load_factor_coordinate_scale_m)
        or load_factor_coordinate_scale_m <= 0
    ):
        raise ValueError("positive finite load-coordinate scale required")
    mapping = dict(
        zip(model_features.feature_names, model_features.values, strict=True)
    )
    length = mapping.get("rotation_coordinate_scale_m", 0.0)
    if not np.isfinite(length) or length <= 0:
        raise ValueError("positive declared rotation-coordinate length required")
    q = np.asarray(context.accepted_augmented_coordinates_m, dtype=float)
    targets = np.asarray(context.accepted_targets_m, dtype=float)
    if (
        q.ndim != 2
        or not 2 <= q.shape[1] <= 49
        or targets.ndim != 1
        or len(q) != len(targets)
        or not 1 <= len(targets) <= 255
        or type(context.control_free_index) is not int
        or not 0 <= context.control_free_index < q.shape[1] - 1
        or not np.all(np.isfinite(q))
        or not np.all(np.isfinite(targets))
        or type(context.target_m) not in (int, float)
        or not np.isfinite(context.target_m)
    ):
        raise ValueError("bounded finite accepted prefix required")
    scales = np.asarray([length] * (q.shape[1] - 1) + [load_factor_coordinate_scale_m])
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        model = []
        for name, value in zip(
            model_features.feature_names, model_features.values, strict=True
        ):
            if name.endswith("_area_m2"):
                divisor = length**2
            elif name.endswith(("_fx_kn", "_fy_kn")):
                divisor = length**2
            elif name.endswith("_mz_kn_m"):
                divisor = length**3
            elif name.endswith("_m"):
                divisor = length
            else:
                raise ValueError("unsupported declared model feature unit")
            model.append(value / divisor)
        t = targets / length
        next_delta = context.target_m / length - t[-1]
        differences = np.diff(t)
        direction = 0.0
        reversals = 0
        reversal_target = t[0]
        branch_travel = 0.0
        for index, delta in enumerate(differences):
            if delta == 0:
                continue
            new_direction = float(np.sign(delta))
            if direction and direction != new_direction:
                reversals += 1
                reversal_target = t[index]
                branch_travel = 0.0
            direction = new_direction
            branch_travel += abs(delta)
        previous_delta = differences[-1] if len(differences) else 0.0
        previous_q_delta = q[-1] - q[-2] if len(q) > 1 else np.zeros(q.shape[1])
        features = np.concatenate(
            [
                model,
                [context.target_m / length, next_delta, previous_delta],
                q[-1] / scales,
                previous_q_delta / scales,
                [
                    t.min(),
                    t.max(),
                    np.abs(differences).sum(),
                    reversals,
                    direction,
                    reversal_target,
                    branch_travel,
                    float(np.sign(next_delta)),
                ],
            ]
        )
    if not np.all(np.isfinite(features)) or not np.all(np.isfinite(scales)):
        raise ValueError("nonfinite normalized control features")
    return features, scales


def history_sample_fields(
    context, model_features, load_factor_coordinate_scale_m, correction
):
    features, scales = control_history_features(
        context, model_features, load_factor_coordinate_scale_m
    )
    original = np.asarray(correction, dtype=float)
    if original.shape != scales.shape or not np.all(np.isfinite(original)):
        raise ValueError("original correction must match augmented coordinate order")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        normalized = original / scales
    if not np.all(np.isfinite(normalized)):
        raise ValueError("nonfinite normalized correction")
    return {
        "feature_profile": HISTORY_FEATURE_PROFILE,
        "features": features.tolist(),
        "correction": normalized.tolist(),
        "source_correction": original.tolist(),
        "correction_coordinate_scales": scales.tolist(),
    }


def derive_control_history_samples(
    samples, original_policy, model_features_by_case, load_factor_coordinate_scale_m
):
    """Derive new rows while keeping each original row's identity and coordinates."""
    from structural_analysis.benchmark.rc_control_learning import (
        RCControlSeedPolicy,
        _features,
    )
    from structural_analysis.benchmark.rc_control_seed_runtime import secant_seed
    from structural_analysis.benchmark.rc_control_design import _bytes, _sha

    if type(original_policy) is not RCControlSeedPolicy or type(samples) is not list:
        raise ValueError("original policy and training sample list required")
    policy = original_policy.to_dict()
    if "feature_profile" in policy:
        raise ValueError("derive from original legacy-feature samples only")
    if any(type(row) is not dict for row in samples):
        raise ValueError("original hashed train rows required")
    if [row.get("sample_hash") for row in samples] != policy["training_sample_hashes"]:
        raise ValueError("original policy sample order and identities required")
    derived = []
    for sample in samples:
        if sample.get("split") != "train" or sample["sample_hash"] != _sha(
            _bytes({k: v for k, v in sample.items() if k != "sample_hash"})
        ):
            raise ValueError("original hashed train rows required")
        features = model_features_by_case[sample["case_id"]]
        if (
            type(features) is not FiberFrameWarmStartModelFeatures
            or features.context_hash != policy["model_context_hash"]
            or list(features.feature_names) != policy["model_feature_names"]
        ):
            raise ValueError("original source-bound case features required")
        value = sample["context"]
        context = RCControlSeedContext(
            value["problem_contract_hash"],
            value["control_global_dof"],
            value["control_free_index"],
            value["target_m"],
            tuple(value["accepted_targets_m"]),
            tuple(tuple(q) for q in value["accepted_augmented_coordinates_m"]),
        )
        if not np.array_equal(_features(context, features), sample["features"]):
            raise ValueError("original case features do not reproduce sample")
        seed = secant_seed(context)
        if seed is None or not np.array_equal(
            np.asarray(sample["accepted_coordinates"]) - seed, sample["correction"]
        ):
            raise ValueError("original secant correction does not reproduce sample")
        row = deepcopy(sample)
        row["source_sample_hash"] = row.pop("sample_hash")
        row.update(
            history_sample_fields(
                context, features, load_factor_coordinate_scale_m, sample["correction"]
            )
        )
        row["sample_hash"] = _sha(_bytes(row))
        derived.append(row)
    return derived
