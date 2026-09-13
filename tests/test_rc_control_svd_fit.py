"""Numerical solver agreement, strict v5 contracts and fold isolation."""

from copy import deepcopy

import numpy as np
import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import (
    RCControlSeedPolicy,
    SVD_RIDGE_FIT_PROFILE,
    _fit,
)
from structural_analysis.benchmark.rc_control_training_diagnostics import (
    audit_rc_control_training_folds,
)


PROFILE = {
    "model_context_hash": "sha256:" + "a" * 64,
    "model_feature_names": [],
    "free_global_dofs": [0],
    "control_free_index": 0,
    "solver_config_hash": "sha256:" + "b" * 64,
}


def rehash(row):
    row["sample_hash"] = _sha(
        _bytes({k: v for k, v in row.items() if k != "sample_hash"})
    )


def samples():
    rows = []
    for i in range(6):
        row = {
            "case_id": f"case-{i // 2}",
            "split": "train",
            "features": [float(i), i + (1e-8 if i % 2 else 0), *([0.0] * 6)],
            "correction": [0.0, 2.0 * i + 1.0],
        }
        rehash(row)
        rows.append(row)
    return rows


def test_svd_matches_augmented_least_squares_and_folds_keep_method(monkeypatch):
    rows = samples()

    # More columns than rows, exact null columns and nearly duplicate columns.
    def forbidden(*args, **kwargs):
        pytest.fail("SVD profile must not use the normal-equation solve")

    monkeypatch.setattr(np.linalg, "solve", forbidden)
    policy = _fit(rows, PROFILE, 1e-6, 0.1, fit_solver=SVD_RIDGE_FIT_PROFILE)
    p = policy.to_dict()
    assert p["schema_version"].endswith(".v5")
    x = np.array([s["features"] for s in rows])
    y = np.array([s["correction"] for s in rows])
    z = np.column_stack([(x - p["feature_mean"]) / p["feature_scale"], np.ones(len(x))])
    a = np.vstack([z, np.sqrt(p["ridge"]) * np.eye(z.shape[1])])
    b = np.vstack([y / p["target_scale"], np.zeros((z.shape[1], y.shape[1]))])
    expected = np.linalg.lstsq(a, b, rcond=None)[0]
    assert np.allclose(p["weights"], expected, rtol=1e-8, atol=1e-10)
    result = audit_rc_control_training_folds(rows, policy)
    assert result["fit_solver_profile"] == SVD_RIDGE_FIT_PROFILE
    assert all(
        f["fitted_policy"]["fit_solver_profile"] == SVD_RIDGE_FIT_PROFILE
        for f in result["folds"]
    )
    changed = deepcopy(rows)
    for row in changed[:2]:
        row["features"][0] += 100
        row["correction"][1] += 1000
        rehash(row)
    other = audit_rc_control_training_folds(
        changed, _fit(changed, PROFILE, 1e-6, 0.1, fit_solver=SVD_RIDGE_FIT_PROFILE)
    )
    assert result["folds"][0]["fitted_policy"] == other["folds"][0]["fitted_policy"]


@pytest.mark.parametrize(
    "mutation", ["method", "unknown", "hash", "weights", "dimensions"]
)
def test_svd_policy_preserves_strict_underlying_contract(mutation):
    p = _fit(samples(), PROFILE, 1e-6, 0.1, fit_solver=SVD_RIDGE_FIT_PROFILE).to_dict()
    if mutation == "method":
        p["fit_solver_profile"] = "unspecified"
    elif mutation == "unknown":
        p["unexpected"] = True
    elif mutation == "weights":
        p["weights"][0][0] = True
    elif mutation == "dimensions":
        p["weights"].pop()
    if mutation != "hash":
        p.pop("policy_hash")
        p["policy_hash"] = _sha(_bytes(p))
    else:
        p["policy_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        RCControlSeedPolicy(_bytes(p).decode())
