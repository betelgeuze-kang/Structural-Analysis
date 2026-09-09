"""Normalization, accepted history and explicit v3 proposal bindings."""

from copy import deepcopy
from dataclasses import asdict, replace

import numpy as np
import pytest

from structural_analysis.ai.fiber_frame_warm_start_features import (
    FiberFrameWarmStartModelFeatures,
)
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
    control_history_features,
    derive_control_history_samples,
    history_sample_fields,
)
from structural_analysis.benchmark.rc_control_learning import (
    RCControlSeedPolicy,
    _features,
    _fit,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext,
    secant_seed,
)


def model_features(factor=1.0):
    return FiberFrameWarmStartModelFeatures(
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        (
            "rotation_coordinate_scale_m",
            "node_0_x_m",
            "node_0_y_m",
            "node_0_reference_fx_kn",
            "node_0_reference_mz_kn_m",
            "member_0_length_m",
            "member_0_fiber_0_area_m2",
        ),
        (
            2 * factor,
            0.0,
            0.0,
            8 * factor**2,
            16 * factor**3,
            4 * factor,
            12 * factor**2,
        ),
    )


def context(targets=(0.0, 2.0, 2.0, 1.0, -1.0, 0.0), target=2.0, factor=1.0):
    return RCControlSeedContext(
        "sha256:" + "a" * 64,
        0,
        0,
        target * factor,
        tuple(t * factor for t in targets),
        tuple((t * factor, t * 0.5 * factor, i * 10.0) for i, t in enumerate(targets)),
    )


def test_declared_length_and_load_coordinate_scaling():
    features, scales = control_history_features(context(), model_features(), 10.0)
    assert np.array_equal(features[:7], [1, 0, 0, 2, 2, 2, 3])
    assert np.array_equal(scales, [2, 2, 10])
    assert np.array_equal(features[-8:], [-0.5, 1, 3, 2, 1, -0.5, 0.5, 1])
    scaled, _ = control_history_features(context(factor=4), model_features(4), 10.0)
    assert np.array_equal(features, scaled)
    original = history_sample_fields(context(), model_features(), 10.0, [1, 2, 3])
    transformed = history_sample_fields(
        context(factor=4), model_features(4), 10.0, [4, 8, 3]
    )
    assert original["correction"] == transformed["correction"]
    assert original["source_correction"] == [1, 2, 3]


def test_earlier_accepted_history_is_not_collapsed_to_the_last_two_states():
    left = context((0.0, 4.0, 1.0, 0.0))
    right = context((0.0, -4.0, 1.0, 0.0))
    assert np.array_equal(
        _features(left, model_features()), _features(right, model_features())
    )
    a, _ = control_history_features(left, model_features(), 10.0)
    b, _ = control_history_features(right, model_features(), 10.0)
    assert np.array_equal(a[:-8], b[:-8])
    assert not np.array_equal(a[-8:], b[-8:])


@pytest.mark.parametrize("scale", [None, True, 0, -1, float("nan"), float("inf")])
def test_invalid_load_coordinate_scales_reject(scale):
    with pytest.raises(ValueError):
        control_history_features(context(), model_features(), scale)


def test_foreign_model_and_unsupported_units_reject():
    with pytest.raises(ValueError, match="must match"):
        control_history_features(
            context(),
            replace(model_features(), problem_contract_hash="sha256:" + "c" * 64),
            10.0,
        )
    with pytest.raises(ValueError, match="unsupported"):
        control_history_features(
            context(),
            replace(
                model_features(),
                feature_names=(*model_features().feature_names[:-1], "unknown_unit"),
            ),
            10.0,
        )


def test_v3_policy_unscales_corrections_and_requires_explicit_coordinate_binding():
    features = model_features()
    profile = {
        "model_context_hash": features.context_hash,
        "model_feature_names": list(features.feature_names),
        "free_global_dofs": [0, 2],
        "control_free_index": 0,
        "solver_config_hash": "sha256:" + "d" * 64,
        "feature_profile": HISTORY_FEATURE_PROFILE,
        "load_factor_coordinate_scale_m": 10.0,
        "arithmetic_profile": None,
    }
    rows = []
    for target in (2.0, 3.0):
        row = {
            "split": "train",
            "case_id": str(target),
            **history_sample_fields(
                context(target=target), features, 10.0, [0, 0.02, 0.3]
            ),
        }
        row["sample_hash"] = _sha(_bytes(row))
        rows.append(row)
    policy = _fit(rows, profile, 1e-6, 0.1)
    assert policy.to_dict()["schema_version"].endswith(".v3")
    assert RCControlSeedPolicy(policy._json).to_dict() == policy.to_dict()
    args = (context(), features, [0, 2], profile["solver_config_hash"])
    assert policy.propose(*args) is None
    assert policy.propose(*args, load_factor_coordinate_scale_m=20.0) is None
    proposal = policy.propose(*args, load_factor_coordinate_scale_m=10.0)
    assert proposal is not None
    seed = np.asarray(secant_seed(context()))
    assert proposal[0] == context().target_m
    assert np.allclose(
        np.asarray(proposal)[1:] - seed[1:], [0.02, 0.3], atol=1e-6, rtol=0
    )
    for key in (
        "feature_profile",
        "load_factor_coordinate_scale_m",
        "arithmetic_profile",
    ):
        altered = deepcopy(policy.to_dict())
        altered.pop(key)
        altered.pop("policy_hash")
        altered["policy_hash"] = _sha(_bytes(altered))
        with pytest.raises(ValueError):
            RCControlSeedPolicy(_bytes(altered).decode())


def test_derived_samples_preserve_labels_and_fold_isolation_in_original_units():
    from structural_analysis.benchmark.rc_control_training_diagnostics import (
        audit_rc_control_training_folds,
    )

    features = model_features()
    profile = {
        "model_context_hash": features.context_hash,
        "model_feature_names": list(features.feature_names),
        "free_global_dofs": [0, 2],
        "control_free_index": 0,
        "solver_config_hash": "sha256:" + "d" * 64,
    }
    originals = []
    for index in range(6):
        ctx = context(target=2.0 + index)
        seed = np.asarray(secant_seed(ctx))
        accepted = seed + [0, 0.25 * index, 2 * index + 1]
        row = {
            "case_id": f"case-{index // 2}",
            "split": "train",
            "context": asdict(ctx),
            "features": _features(ctx, features).tolist(),
            "accepted_coordinates": accepted.tolist(),
            "correction": (accepted - seed).tolist(),
        }
        row["sample_hash"] = _sha(_bytes(row))
        originals.append(row)
    before = deepcopy(originals)
    original_policy = _fit(originals, profile, 1e-6, 0.1)
    model_map = {row["case_id"]: features for row in originals}
    rows = derive_control_history_samples(originals, original_policy, model_map, 10.0)
    assert originals == before
    for old, new in zip(originals, rows, strict=True):
        assert new["source_sample_hash"] == old["sample_hash"]
        assert new["source_correction"] == old["correction"]
        assert new["accepted_coordinates"] == old["accepted_coordinates"]
    new_profile = {
        **profile,
        "feature_profile": HISTORY_FEATURE_PROFILE,
        "load_factor_coordinate_scale_m": 10.0,
        "arithmetic_profile": None,
    }
    policy = _fit(rows, new_profile, 1e-6, 0.1)
    result = audit_rc_control_training_folds(rows, policy)
    first = result["folds"][0]
    expected = np.sqrt(np.mean(np.square([[0, 0, 1], [0, 0.25, 3]]), axis=0))
    assert np.array_equal(first["ungated_diagnostic_only"]["secant_rmse"], expected)
    changed = deepcopy(rows)
    for row in changed[:2]:
        row["features"][0] += 100
        row["source_correction"][2] += 1000
        row["correction"][2] = row["source_correction"][2] / 10
        row.pop("sample_hash")
        row["sample_hash"] = _sha(_bytes(row))
    changed_policy = _fit(changed, new_profile, 1e-6, 0.1)
    other = audit_rc_control_training_folds(changed, changed_policy)
    assert first["fitted_policy"] == other["folds"][0]["fitted_policy"]
    damaged = deepcopy(originals)
    damaged[0]["accepted_coordinates"][1] += 1
    damaged[0].pop("sample_hash")
    damaged[0]["sample_hash"] = _sha(_bytes(damaged[0]))
    damaged_policy = _fit(damaged, profile, 1e-6, 0.1)
    with pytest.raises(ValueError, match="original secant correction"):
        derive_control_history_samples(damaged, damaged_policy, model_map, 10.0)
    with pytest.raises(ValueError, match="hashed train rows"):
        derive_control_history_samples([None], original_policy, model_map, 10.0)
