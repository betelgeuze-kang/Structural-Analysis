"""Selection/assessment isolation, baseline choice and original fit reservations."""

from copy import deepcopy
import json

import numpy as np
import pytest

from structural_analysis.benchmark import rc_control_model_selection as selection
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import _fit
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
)


PROFILE = {
    "model_context_hash": "sha256:" + "a" * 64,
    "model_feature_names": [],
    "free_global_dofs": [0],
    "control_free_index": 0,
    "solver_config_hash": "sha256:" + "b" * 64,
}
GRID = (1e-6, 1.0, 1e6)


def rehash(row):
    row["sample_hash"] = _sha(
        _bytes({k: v for k, v in row.items() if k != "sample_hash"})
    )


def samples(zero=False):
    rows = []
    for i in range(6):
        row = {
            "case_id": f"case-{i // 2}",
            "split": "train",
            "features": [float(i), *([0.0] * 7)],
            "correction": [0.0, 0.0 if zero else 2.0 * i + 1],
        }
        rehash(row)
        rows.append(row)
    return rows


def run(root, rows, **kwargs):
    source = _fit(rows, PROFILE, 1e-6, 0.1)
    return selection.run_rc_control_nested_selection(
        rows,
        source,
        source_revision="a" * 40,
        output_directory=root,
        ridge_grid=GRID,
        **kwargs,
    )


def test_outer_values_cannot_change_inner_choice_or_selected_policy(tmp_path):
    rows = samples()
    original = deepcopy(rows)
    report = run(tmp_path / "first", rows)
    assert rows == original
    assert report["fit_completed_count"] == report["fit_attempt_count"] == 31
    assert report["structural_solver_calls"] == report["material_integrations"] == 0
    assert not report["candidate_promoted"] and not report["independent_validation"]
    first = report["outer_folds"][0]
    assert first["selection"]["selected_strategy"] == "learned_svd"
    assert first["selection"]["selected_ridge"] == GRID[0]
    assert first["outer_metrics"]["relative_correction_loss"] < 1e-8
    by_case = {
        key: {r["sample_hash"] for r in rows if r["case_id"] == key}
        for key in ("case-0", "case-1", "case-2")
    }
    for record in report["fit_records"]:
        purpose = record["purpose"]
        outer = purpose["selection"].get("outer_withheld_case")
        training = set(record["training_sample_hashes"])
        if outer is not None:
            assert training.isdisjoint(by_case[outer])
        if "inner_withheld_case" in purpose:
            assert training.isdisjoint(by_case[purpose["inner_withheld_case"]])
        payload = json.loads((tmp_path / "first" / record["policy_file"]).read_bytes())
        assert payload["policy_hash"] == record["policy_hash"]
        assert payload["training_sample_hashes"] == record["training_sample_hashes"]
    changed = deepcopy(rows)
    for row in changed[:2]:
        row["features"][0] += 100
        row["correction"][1] += 1000
        rehash(row)
    other = run(tmp_path / "changed", changed)["outer_folds"][0]
    assert first["selection"]["policy"] == other["selection"]["policy"]
    assert first["selection"]["selected_ridge"] == other["selection"]["selected_ridge"]
    assert [c["score"] for c in first["selection"]["candidates"]] == [
        c["score"] for c in other["selection"]["candidates"]
    ]
    assert (
        first["outer_metrics"]["relative_correction_loss"]
        != other["outer_metrics"]["relative_correction_loss"]
    )


def test_perfect_secant_keeps_baseline_without_manufactured_final_fits(tmp_path):
    report = run(tmp_path / "zero", samples(zero=True))
    assert report["fit_attempt_count"] == 27
    for choice in [
        report["full_training_selection"],
        *(r["selection"] for r in report["outer_folds"]),
    ]:
        assert choice["selected_strategy"] == "secant"
        assert (
            choice["selected_ridge"]
            is choice["policy"]
            is choice["refit_index"]
            is None
        )
        assert all(c["score"] == 1.0 for c in choice["candidates"])
    assert all(
        r["outer_metrics"]["relative_correction_loss"] == 1.0
        for r in report["outer_folds"]
    )


@pytest.mark.parametrize(
    "mutation", ["heldout", "hash", "two-cases", "budget", "grid", "improvement"]
)
def test_rejects_before_directory_or_fit(tmp_path, monkeypatch, mutation):
    rows = samples()
    kwargs = {}
    if mutation == "heldout":
        rows[0]["split"] = "holdout"
        rehash(rows[0])
    elif mutation == "hash":
        rows[0]["correction"][1] += 1
    elif mutation == "two-cases":
        rows = rows[:4]
    elif mutation == "budget":
        kwargs["maximum_fits"] = 30
    elif mutation == "grid":
        kwargs["ridge_grid"] = (1, 0.1)
    elif mutation == "improvement":
        kwargs["minimum_relative_improvement"] = True
    source = _fit(rows, PROFILE, 1e-6, 0.1)
    monkeypatch.setattr(
        selection, "_fit", lambda *a, **k: pytest.fail("invalid input reached fit")
    )
    with pytest.raises(ValueError):
        selection.run_rc_control_nested_selection(
            rows,
            source,
            source_revision="a" * 40,
            output_directory=tmp_path / "invalid",
            **(dict(ridge_grid=GRID) | kwargs),
        )
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("failure", [KeyboardInterrupt, ValueError])
def test_interrupted_or_failed_fit_preserves_original_started_records(
    tmp_path, monkeypatch, failure
):
    rows = samples()
    source = _fit(rows, PROFILE, 1e-6, 0.1)
    calls = []
    original = selection._fit

    def interrupt(*args, **kwargs):
        calls.append(None)
        if len(calls) == 2:
            raise failure("injected")
        return original(*args, **kwargs)

    monkeypatch.setattr(selection, "_fit", interrupt)
    root = tmp_path / "interrupted"
    with pytest.raises(failure, match="injected"):
        selection.run_rc_control_nested_selection(
            rows,
            source,
            source_revision="a" * 40,
            output_directory=root,
            ridge_grid=GRID,
        )
    assert len(calls) == 2 and not (root / "result.json").exists()
    assert (
        json.loads((root / "fit-0000-outcome.json").read_bytes())["status"]
        == "completed"
    )
    assert json.loads((root / "fit-0001-started.json").read_bytes())[
        "unknown_fit_work_until_outcome"
    ]
    if failure is KeyboardInterrupt:
        assert not (root / "fit-0001-outcome.json").exists()
    else:
        record = json.loads((root / "fit-0001-outcome.json").read_bytes())
        assert record["status"] == "raised" and record["unknown_fit_work_until_outcome"]


def test_history_baseline_and_candidate_metrics_use_original_coordinates():
    rows = samples()
    for row in rows:
        row.update(
            source_correction=[0.0, row["correction"][1] * 10],
            correction_coordinate_scales=[2.0, 10.0],
            feature_profile=HISTORY_FEATURE_PROFILE,
        )
        # History layout replaces step count and adds eight history scalars.
        row["features"] += [0.0] * 7
        rehash(row)
    profile = dict(
        PROFILE,
        feature_profile=HISTORY_FEATURE_PROFILE,
        load_factor_coordinate_scale_m=10.0,
        arithmetic_profile=None,
    )
    fitted = _fit(rows, profile, 1e-6, 0.1)
    expected = np.sqrt(
        np.mean(np.array([r["source_correction"] for r in rows]) ** 2, axis=0)
    )
    baseline = selection._correction_score(
        rows, feature_profile=HISTORY_FEATURE_PROFILE
    )
    candidate = selection._correction_score(rows, fitted)
    assert (
        baseline["secant_rmse_original_coordinates"]
        == candidate["secant_rmse_original_coordinates"]
        == expected.tolist()
    )
    assert candidate["learned_rmse_original_coordinates"][1] < 1e-4
