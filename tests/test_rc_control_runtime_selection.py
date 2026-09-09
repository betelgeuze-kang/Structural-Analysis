"""Full-path execution, train-case exclusion, cost selection and interrupted work."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_runtime_selection as selection
from structural_analysis.benchmark.rc_control_training_diagnostics import (
    _validated_training_data,
)
from structural_analysis.io.neutral.loader import load_neutral_json


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    root = tmp_path_factory.mktemp("runtime-selection-original")
    cases = []
    for name, split, lengths, targets in (
        ("train-a", "train", (2.0, 1.5), (-1e-6, -2e-6, 1e-6, 0.0)),
        ("train-b", "train", (3.0, 2.5), (-1e-6, -2e-6, 1e-6, 0.0)),
        ("validation", "validation", (2.5, 2.0), (-0.7e-6, -1.3e-6, 1.1e-6, 0.1e-6)),
    ):
        payload = json.loads(
            Path(
                "examples/public_rc_fiber_frame_l_frame_material_history.json"
            ).read_bytes()
        )
        for node in payload["nodes"]:
            if node["id"] == "N2":
                node["coordinates"] = [lengths[0], 0.0, 0.0]
            elif node["id"] == "N3":
                node["coordinates"] = [lengths[0], lengths[1], 0.0]
        path = root / (name + ".json")
        path.write_text(json.dumps(payload))
        request = BoundedRCFiberDirectControlRequest(
            7,
            targets,
            allow_reversals=True,
            maximum_reversals=3,
            constant_nodal_loads=(("N3", 0.0, -0.1, 0.0),),
        )
        request = replace(
            request,
            solver_config=replace(
                request.solver_config,
                newton=replace(request.solver_config.newton, terminal_polishing=True),
            ),
        )
        cases.append(
            learning.RCControlLearningCase(
                name, name, name, name, split, load_neutral_json(path), request
            )
        )
    report = learning.run_rc_control_learning_study(
        cases,
        source_revision="a" * 40,
        output_directory=root / "study",
        feature_profile=learning.MATERIAL_FEATURE_PROFILE,
        arithmetic_profile="retained-twofold-refinement.v1",
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
    )
    policy = learning.RCControlSeedPolicy(json.dumps(report["policy"]))
    samples = json.loads((root / "study/training-samples.json").read_bytes())
    assert len(samples) == 6
    return cases, samples, policy, report


def run(root, original, **kwargs):
    cases, samples, policy, _ = original
    options = {
        "ridge_grid": (1e4, 1e6),
        "arithmetic_profile": "retained-twofold-refinement.v1",
        "maximum_fits": 5,
        "maximum_core_calls": 96,
    } | kwargs
    return selection.run_rc_control_runtime_selection(
        cases,
        samples,
        policy,
        source_revision="a" * 40,
        output_directory=root,
        **options,
    )


def test_actual_full_paths_charge_preload_and_material_only_to_proposer(
    tmp_path, original, monkeypatch
):
    executed = []
    benchmark = learning.benchmark_rc_control_seed_paths

    def observe(model, request, **kwargs):
        executed.append(model.canonical_model_checksum)
        return benchmark(model, request, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    root = tmp_path / "study"
    result = run(root, original)
    assert len(executed) == 4
    assert set(executed) == {
        c.model.canonical_model_checksum for c in original[0] if c.split == "train"
    }
    assert result["fit_attempt_count"] == result["fit_completed_count"] == 4
    assert result["selected_strategy"] == "secant" and result["selected_policy"] is None
    assert (
        not result["validation_or_holdout_execution"]
        and not result["net_savings_proved"]
    )
    assert all(f["score"]["full_comparison_pass"] for f in result["folds"])
    assert (
        sum(
            f["score"]["execution_work"]["known_work"]["core_calls"]
            for f in result["folds"]
        )
        == 80
    )
    for fold in result["folds"]:
        policy = json.loads(
            (root / f"fit-{fold['fit_index']:04d}-policy.json").read_bytes()
        )
        excluded = {
            s["sample_hash"]
            for s in original[1]
            if s["case_id"] == fold["withheld_training_case"]
        }
        assert excluded.isdisjoint(policy["training_sample_hashes"])
        for arm in ("reference", "secant", "proposal", "fresh-reference"):
            path = json.loads(
                (root / f"fold-{fold['index']:04d}" / arm / "path.json").read_bytes()
            )
            assert len(path["entries"]) == 4 and len(path["preload_invocations"]) == 1
            for e in path["entries"]:
                assert ("committed_material_capture" in e) == (arm == "proposal")


def injected_benchmark(
    original, monkeypatch, ratios, *, physical=True, known=True, propose=True
):
    cases, samples, _, source_report = original
    template = deepcopy(source_report["evaluation"][0]["report"])
    by_hash = {c.model.canonical_model_checksum: c.case_id for c in cases}
    calls = []
    if propose:
        monkeypatch.setattr(
            learning.RCControlSeedPolicy,
            "propose",
            lambda self, context, *a, **kw: learning.secant_seed(context),
        )
    else:
        monkeypatch.setattr(
            learning.RCControlSeedPolicy, "propose", lambda *a, **kw: None
        )

    def benchmark(model, request, **kwargs):
        held = by_hash[model.canonical_model_checksum]
        assert held.startswith("train-")
        calls.append(held)
        for row in samples:
            if row["case_id"] == held:
                kwargs["proposal"](learning.RCControlSeedContext(**row["context"]))
        result = deepcopy(template)
        result["arms"]["secant"]["wall_ns"] = 1000000
        result["arms"]["proposal"]["wall_ns"] = int(
            ratios[(len(calls) - 1) // 2] * 1000000
        )
        result["comparisons"]["proposal"]["full_history_pass"] = physical
        result["all_execution_work_reported"] = known
        if not known:
            result["arms"]["proposal"]["entries"][0]["invocations"][0][
                "unknown_work"
            ] = True
        return result

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", benchmark)
    return calls


def test_selection_uses_measured_cost_and_final_refit_restores_all_train_rows(
    tmp_path, original, monkeypatch
):
    calls = injected_benchmark(original, monkeypatch, (1.2, 0.8))
    result = run(tmp_path / "study", original)
    assert calls == ["train-a", "train-b", "train-a", "train-b"]
    assert result["selected_ridge"] == 1e6 and result["selected_score"] == 0.8
    assert result["fit_completed_count"] == 5
    assert result["selected_policy"]["training_sample_hashes"] == [
        s["sample_hash"] for s in original[1]
    ]
    assert not result["candidate_promoted"] and not result["independent_evaluation"]


@pytest.mark.parametrize(
    "ratios,physical,propose",
    [
        ((1.1, 1.2), True, True),
        ((0.2, 0.3), False, True),
        ((0.2, 0.3), True, False),
        ((0.99, 0.99), True, True),
    ],
)
def test_baseline_remains_for_slow_failed_abstaining_or_threshold_tied_candidates(
    tmp_path, original, monkeypatch, ratios, physical, propose
):
    injected_benchmark(
        original, monkeypatch, ratios, physical=physical, propose=propose
    )
    result = run(tmp_path / "study", original)
    assert result["selected_strategy"] == "secant" and result["selected_policy"] is None
    assert result["fit_completed_count"] == 4


def test_exact_learned_cost_tie_prefers_stronger_ridge(tmp_path, original, monkeypatch):
    injected_benchmark(original, monkeypatch, (0.8, 0.8))
    assert run(tmp_path / "study", original)["selected_ridge"] == 1e6


def test_withheld_labels_cannot_change_that_folds_fit(tmp_path, original, monkeypatch):
    injected_benchmark(original, monkeypatch, (1.2, 1.3))
    first = run(tmp_path / "first", original)
    cases, rows, source, report = original
    changed = deepcopy(rows)
    for row in changed:
        if row["case_id"] == "train-a":
            row["accepted_coordinates"][0] += 100
            row["correction"] = (
                np.asarray(row["accepted_coordinates"])
                - learning.secant_seed(learning.RCControlSeedContext(**row["context"]))
            ).tolist()
            row["sample_hash"] = learning._sha(
                learning._bytes({k: v for k, v in row.items() if k != "sample_hash"})
            )
    _, _, profile = _validated_training_data(rows, source)
    updated = learning._fit(
        changed,
        profile,
        source.to_dict()["ridge"],
        source.to_dict()["ood_margin"],
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
    )
    injected_benchmark(original, monkeypatch, (1.2, 1.3))
    other = run(tmp_path / "other", (cases, changed, updated, report))
    assert [
        f["policy_hash"]
        for f in first["folds"]
        if f["withheld_training_case"] == "train-a"
    ] == [
        f["policy_hash"]
        for f in other["folds"]
        if f["withheld_training_case"] == "train-a"
    ]


@pytest.mark.parametrize(
    "options",
    [
        {"maximum_fits": 4},
        {"maximum_core_calls": 95},
        {"ridge_grid": ()},
        {"ridge_grid": (1e4, 1e4)},
        {"ridge_grid": (True,)},
        {"minimum_relative_improvement": float("nan")},
        {"maximum_fits": True},
        {"arithmetic_profile": "binary64"},
    ],
)
def test_invalid_inputs_and_budgets_reject_before_fits_or_output(
    tmp_path, original, monkeypatch, options
):
    def forbidden(*args, **kwargs):
        pytest.fail("must reject before fit or runtime")

    monkeypatch.setattr(learning, "_fit", forbidden)
    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", forbidden)
    root = tmp_path / "rejected"
    with pytest.raises(ValueError):
        run(root, original, **options)
    assert not root.exists()


def test_changed_request_cannot_reuse_original_training_contexts(tmp_path, original):
    cases, rows, policy, report = original
    changed = list(cases)
    c = cases[0]
    request = replace(c.request, targets_m=(-1.1e-6, -2.1e-6, 1e-6, 0.0))
    changed[0] = learning.RCControlLearningCase(
        c.case_id,
        c.project_id,
        c.geometry_family_id,
        c.load_history_id,
        c.split,
        c.model,
        request,
    )
    with pytest.raises(ValueError, match="context differs"):
        run(tmp_path / "rejected", (changed, rows, policy, report))
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize(
    "field", ["parent_hash", "accepted_coordinates", "target_index"]
)
def test_rehashed_source_row_still_requires_consistent_parent_label_and_target(
    tmp_path, original, monkeypatch, field
):
    cases, rows, source, report = original
    changed = deepcopy(rows)
    if field == "parent_hash":
        changed[0][field] = "sha256:" + "0" * 64
    elif field == "accepted_coordinates":
        changed[0][field][0] += 1
    else:
        changed[0][field] = True
    row = changed[0]
    row["sample_hash"] = learning._sha(
        learning._bytes({k: v for k, v in row.items() if k != "sample_hash"})
    )
    _, _, profile = _validated_training_data(rows, source)
    updated = learning._fit(
        changed,
        profile,
        source.to_dict()["ridge"],
        source.to_dict()["ood_margin"],
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("inconsistent source rows must reject before fitting or execution")

    monkeypatch.setattr(learning, "_fit", forbidden)
    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", forbidden)
    root = tmp_path / "rejected"
    with pytest.raises(ValueError):
        run(root, (cases, changed, updated, report))
    assert not root.exists()


@pytest.mark.parametrize("phase", ["fit", "runtime"])
@pytest.mark.parametrize("error", [ValueError, KeyboardInterrupt])
def test_interrupted_work_retains_reservation_without_invented_completion(
    tmp_path, original, monkeypatch, phase, error
):
    def fail(*args, **kwargs):
        raise error("injected")

    monkeypatch.setattr(
        learning, "_fit" if phase == "fit" else "benchmark_rc_control_seed_paths", fail
    )
    root = tmp_path / "study"
    with pytest.raises(error, match="injected"):
        run(root, original)
    stem = "fit-0000" if phase == "fit" else "fold-0000"
    assert (root / (stem + "-started.json")).exists()
    assert not (root / "result.json").exists()
    outcome = root / (stem + "-outcome.json")
    if error is KeyboardInterrupt:
        assert not outcome.exists()
    else:
        record = json.loads(outcome.read_bytes())
        assert record["status"] == "raised"
        assert record[
            "unknown_fit_work_until_outcome"
            if phase == "fit"
            else "unknown_work_until_outcome"
        ]


def test_unknown_runtime_work_stops_before_another_candidate(
    tmp_path, original, monkeypatch
):
    calls = injected_benchmark(original, monkeypatch, (0.8, 0.8), known=False)
    root = tmp_path / "study"
    with pytest.raises(ValueError, match="unaccounted work"):
        run(root, original)
    assert len(calls) == 1 and not (root / "fit-0001-started.json").exists()
    assert json.loads((root / "fold-0000-outcome.json").read_bytes())[
        "unknown_work_until_outcome"
    ]
