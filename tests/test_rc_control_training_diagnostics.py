"""Train-case withholding, original identities and diagnostic-only predictions."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark import rc_control_training_diagnostics as audit
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import _fit


PROFILE = {
    "model_context_hash": "sha256:" + "a" * 64,
    "model_feature_names": [],
    "free_global_dofs": [0],
    "control_free_index": 0,
    "solver_config_hash": "sha256:" + "b" * 64,
}


def _rehash(row):
    row["sample_hash"] = _sha(
        _bytes({k: v for k, v in row.items() if k != "sample_hash"})
    )


def _samples():
    rows = []
    for index in range(6):
        row = {
            "case_id": f"case-{index // 2}",
            "split": "train",
            "features": [float(index), *([0.0] * 7)],
            "correction": [0.0, 2.0 * index + 1.0],
        }
        _rehash(row)
        rows.append(row)
    return rows


def test_folds_exclude_case_targets_from_weights_scales_and_bounds():
    samples = _samples()
    original = deepcopy(samples)
    policy = _fit(samples, PROFILE, 1e-6, 0.1)
    result = audit.audit_rc_control_training_folds(samples, policy)
    assert samples == original
    assert result["fit_count"] == 3
    assert result["structural_solver_calls"] == 0
    assert result["policy_promoted"] is False
    assert result["independent_project_split"] is False
    assert result["runtime_speedup_evidence"] is False
    for fold in result["folds"]:
        training = set(fold["fitted_policy"]["training_sample_hashes"])
        assert training.isdisjoint(fold["withheld_sample_hashes"])
        assert len(training) == 4
        assert fold["fit_wall_ns"] > 0
        metrics = fold["ungated_diagnostic_only"]
        assert metrics["learned_rmse"][1] < 1e-4
        assert metrics["secant_rmse"][1] > 1
    first = result["folds"][0]
    assert first["range_eligible_count"] == 0
    assert first["ood_sample_count"] == 2
    assert first["range_violations_by_feature"] == {"target_m": 2}
    assert first["range_eligible_diagnostic_only"] == {
        "sample_count": 0,
        "secant_rmse": None,
        "learned_rmse": None,
    }
    changed = deepcopy(samples)
    for row in changed:
        if row["case_id"] == "case-0":
            row["features"][0] -= 100.0
            row["correction"][1] += 1000.0
            _rehash(row)
    changed_policy = _fit(changed, PROFILE, 1e-6, 0.1)
    changed_result = audit.audit_rc_control_training_folds(changed, changed_policy)
    # Withheld features/labels may change errors, never this fold's preprocessing.
    assert first["fitted_policy"] == changed_result["folds"][0]["fitted_policy"]
    assert (
        first["ungated_diagnostic_only"]
        != changed_result["folds"][0]["ungated_diagnostic_only"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["validation", "holdout", "hash", "order", "duplicate", "one-case", "nonfinite"],
)
def test_ineligible_inputs_reject_before_any_diagnostic_fit(monkeypatch, mutation):
    samples = _samples()
    policy = _fit(samples, PROFILE, 1e-6, 0.1)
    if mutation in ("validation", "holdout"):
        samples[0]["split"] = mutation
        _rehash(samples[0])
    elif mutation == "hash":
        samples[0]["correction"][1] += 1
    elif mutation == "order":
        samples.reverse()
    elif mutation == "duplicate":
        samples[-1] = deepcopy(samples[0])
    elif mutation == "one-case":
        for row in samples:
            row["case_id"] = "same-case"
            _rehash(row)
        policy = _fit(samples, PROFILE, 1e-6, 0.1)
    elif mutation == "nonfinite":
        samples[0]["features"][0] = float("nan")

    def forbidden(*args):
        raise AssertionError("ineligible rows reached fitting")

    monkeypatch.setattr(audit, "_fit", forbidden)
    with pytest.raises(ValueError):
        audit.audit_rc_control_training_folds(samples, policy)
