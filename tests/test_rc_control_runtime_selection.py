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
        "maximum_core_calls": 112,
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


@pytest.mark.parametrize("repetitions", [1, 3])
def test_unknown_runtime_work_stops_before_another_candidate(
    tmp_path, original, monkeypatch, repetitions
):
    calls = injected_benchmark(original, monkeypatch, (0.8, 0.8), known=False)
    root = tmp_path / "study"
    with pytest.raises(ValueError, match="unaccounted work"):
        run(
            root,
            original,
            repetitions=repetitions,
            maximum_core_calls=112 * repetitions,
        )
    assert len(calls) == 1 and not (root / "fit-0001-started.json").exists()
    assert json.loads((root / "fold-0000-outcome.json").read_bytes())[
        "unknown_work_until_outcome"
    ]


def test_secant_abstention_runs_actual_full_paths_and_keeps_baseline_states(
    tmp_path, original, monkeypatch
):
    # Force abstention to isolate the fallback mechanics, not learned performance.
    monkeypatch.setattr(learning.RCControlSeedPolicy, "propose", lambda *a, **k: None)
    root = tmp_path / "secant-abstention"
    result = run(
        root, original, ridge_grid=(1e4,), proposal_abstention_strategy="secant"
    )
    assert result["proposal_abstention_strategy"] == "secant"
    plan = json.loads((root / "plan.json").read_bytes())
    assert plan["maximum_possible_core_calls"] == 56
    assert plan["abstention"] == "secant_when_available_otherwise_reference"
    for fold in result["folds"]:
        folder = root / f"fold-{fold['index']:04d}"
        baseline = json.loads((folder / "secant/path.json").read_bytes())
        proposal = json.loads((folder / "proposal/path.json").read_bytes())
        assert baseline["terminal_checkpoint"] == proposal["terminal_checkpoint"]
        assert baseline["response_history"] == proposal["response_history"]
        decisions = [e["proposal_decision"] for e in proposal["entries"]]
        assert decisions == ["abstained_to_reference"] + ["abstained_to_secant"] * 3
        assert [e["proposal"] for e in baseline["entries"]] == [
            e["proposal"] for e in proposal["entries"]
        ]
        assert fold["score"]["abstained_count"] == 4
        assert fold["score"]["proposed_count"] == 0
        assert fold["score"]["full_comparison_pass"]
        assert all(e["proposal_wall_ns"] > 0 for e in proposal["entries"])
        assert all("committed_material_capture" in e for e in proposal["entries"])
        assert all("committed_material_capture" not in e for e in baseline["entries"])


@pytest.mark.parametrize("option", [None, True, "automatic"])
def test_unknown_abstention_option_rejected_before_output(tmp_path, original, option):
    with pytest.raises(ValueError, match="abstention"):
        run(tmp_path / "invalid", original, proposal_abstention_strategy=option)
    assert not (tmp_path / "invalid").exists()


def test_budget_counts_possible_secant_retries_too(tmp_path, original):
    # 48 covered the old five-per-target estimate but not both seeded arms' retry.
    with pytest.raises(ValueError, match="56 core calls"):
        run(
            tmp_path / "underbudget", original, ridge_grid=(1e4,), maximum_core_calls=48
        )
    assert not (tmp_path / "underbudget").exists()


@pytest.mark.parametrize("abstention", ["reference", "secant"])
def test_static_rejection_omits_capture_and_inference_with_exact_actual_paths(
    tmp_path, original, monkeypatch, abstention
):
    from structural_analysis.benchmark import rc_control_material_features as material

    def unexpected(*args, **kwargs):
        pytest.fail("proved static rejection must not capture material or infer")

    monkeypatch.setattr(material, "committed_material_snapshot", unexpected)
    monkeypatch.setattr(learning.RCControlSeedPolicy, "propose", unexpected)
    root = tmp_path / abstention
    result = run(
        root,
        original,
        ridge_grid=(1e4,),
        proposal_abstention_strategy=abstention,
        static_model_abstention=True,
    )
    assert result["static_model_abstention"] is True
    assert result["selected_strategy"] == "secant"
    assert result["fit_completed_count"] == 2  # no final learned refit
    plan = json.loads((root / "plan.json").read_bytes())
    assert plan["static_model_abstention"] is True
    assert plan["maximum_possible_core_calls"] == 56
    for fold in result["folds"]:
        stem = f"fold-{fold['index']:04d}"
        gate = json.loads((root / (stem + "-model-gate.json")).read_bytes())
        assert gate["status"] == "rejected" and gate["violations"]
        assert gate["policy_hash"] == fold["policy_hash"]
        assert gate["gate_hash"] == fold["static_model_gate_hash"]
        assert gate["gate_hash"] == learning._sha(
            learning._bytes({k: v for k, v in gate.items() if k != "gate_hash"})
        )
        assert not gate["proposal_acceptance_authorized"]
        baseline = json.loads((root / stem / abstention / "path.json").read_bytes())
        proposal = json.loads((root / stem / "proposal/path.json").read_bytes())
        assert baseline["terminal_checkpoint"] == proposal["terminal_checkpoint"]
        assert baseline["response_history"] == proposal["response_history"]
        steps = sorted((root / stem / "proposal").glob("*step.json"))
        assert len(steps) == 5  # four targets and the original constant preload
        assert all(
            step.read_bytes() == (root / stem / abstention / step.name).read_bytes()
            for step in steps
        )
        assert [e["proposal"] for e in baseline["entries"]] == [
            e["proposal"] for e in proposal["entries"]
        ]
        assert all("committed_material_capture" not in e for e in proposal["entries"])
        assert fold["score"]["full_comparison_pass"]
        assert fold["score"]["proposed_count"] == 0
        assert (
            fold["score"]["proposal_setup_wall_ns"]
            == fold["static_model_gate_wall_ns"]
            > 0
        )
        assert (
            fold["score"]["proposal_scored_wall_ns"]
            == proposal["wall_ns"] + fold["static_model_gate_wall_ns"]
        )
        assert (
            fold["score"]["proposal_over_secant_path_wall_ratio"]
            == fold["score"]["proposal_scored_wall_ns"]
            / fold["score"]["secant_path_wall_ns"]
        )


def test_static_pass_does_not_authorize_dynamic_or_missing_material_inputs(original):
    cases, samples, policy, _ = original
    features = learning._preflight(cases, "retained-twofold-refinement.v1")["train-a"][
        2
    ]
    gate = selection._static_material_model_gate(policy, features)
    assert gate["status"] == "not_rejected"
    assert not gate["material_capture_omitted"]
    assert not gate["proposal_acceptance_authorized"]
    context = learning.RCControlSeedContext(
        **next(s for s in samples if s["case_id"] == "train-a")["context"]
    )
    for changed in (
        replace(context, target_m=1e6),
        replace(context, committed_material_state_json=None),
    ):
        assert (
            policy.propose(
                changed,
                features,
                policy.to_dict()["free_global_dofs"],
                cases[0].request.solver_config.contract_hash,
                arithmetic_profile="retained-twofold-refinement.v1",
            )
            is None
        )
    with pytest.raises(ValueError, match="matching material"):
        selection._static_material_model_gate(
            policy, replace(features, context_hash="sha256:" + "f" * 64)
        )


def test_static_overflow_does_not_manufacture_rejection(original):
    features = learning._preflight(original[0], "retained-twofold-refinement.v1")[
        "train-a"
    ][2]
    body = original[2].to_dict()
    body["feature_min"][0], body["feature_max"][0] = -1e308, 1e308
    body["policy_hash"] = learning._sha(
        learning._bytes({k: v for k, v in body.items() if k != "policy_hash"})
    )
    policy = learning.RCControlSeedPolicy(learning._bytes(body).decode())
    gate = selection._static_material_model_gate(policy, features)
    assert gate["status"] == "not_proved" and not gate["violations"]
    assert not gate["material_capture_omitted"]


def test_unproved_static_gate_preserves_capture_and_policy_callback(
    tmp_path, original, monkeypatch
):
    calls = injected_benchmark(original, monkeypatch, (1.2, 1.3))
    benchmark = learning.benchmark_rc_control_seed_paths

    def observe(*args, **kwargs):
        assert kwargs["capture_material_state"] is True
        assert kwargs["material_capture_scope"] == "proposal-only"
        return benchmark(*args, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    # Inject an unresolved gate, never a grant of permission to propose.
    monkeypatch.setattr(
        selection,
        "_static_material_model_gate",
        lambda *a: {"status": "not_proved", "gate_hash": "sha256:" + "b" * 64},
    )
    result = run(tmp_path / "unproved", original, static_model_abstention=True)
    assert len(calls) == 4
    assert all(f["score"]["proposed_count"] == 3 for f in result["folds"])


@pytest.mark.parametrize("value", [1, "true", None])
def test_static_option_requires_explicit_bool_before_output(tmp_path, original, value):
    with pytest.raises(ValueError, match="boolean static"):
        run(tmp_path / "rejected", original, static_model_abstention=value)
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("physical", [True, False])
def test_model_gate_cost_is_charged_without_qualifying_failed_paths(original, physical):
    report = deepcopy(original[3]["evaluation"][0]["report"])
    report["arms"]["secant"]["wall_ns"] = 100
    report["arms"]["proposal"]["wall_ns"] = 50
    report["comparisons"]["proposal"]["full_history_pass"] = physical
    score = selection._runtime_score(report, [], proposal_setup_wall_ns=75)
    assert score["proposal_scored_wall_ns"] == 125
    assert score["proposal_over_secant_path_wall_ratio"] == (1.25 if physical else None)
    assert "proposal_setup_wall_ns" not in selection._runtime_score(report, [])
    for invalid in (True, -1, 0.0, float("nan")):
        with pytest.raises(ValueError, match="setup time"):
            selection._runtime_score(report, [], proposal_setup_wall_ns=invalid)


def test_actual_counterbalanced_repeats_reuse_fit_and_preserve_complete_paths(
    tmp_path, original, monkeypatch
):
    observed = []
    real = learning.benchmark_rc_control_seed_paths

    def record(model, request, **kwargs):
        observed.append(
            (
                model.canonical_model_checksum,
                kwargs["arm_order"],
                kwargs["proposal_identity"],
            )
        )
        return real(model, request, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", record)
    root = tmp_path / "repeated"
    result = run(
        root,
        original,
        ridge_grid=(1e4,),
        repetitions=3,
        maximum_core_calls=168,
        maximum_fits=3,
        proposal_abstention_strategy="secant",
        static_model_abstention=True,
        record_assembly_work=True,
    )
    plan = json.loads((root / "plan.json").read_bytes())
    assert (
        plan["assembly_work_recording"]
        == result["assembly_work_recording"]
        == "vector-newton-assembly-dispatch-work.v1"
    )
    assert "recording costs included" in plan["selection_score"]
    schedule = [
        ["reference", "secant", "proposal"],
        ["secant", "proposal", "reference"],
        ["proposal", "reference", "secant"],
    ]
    assert plan["arm_order_schedule"] == schedule
    assert (
        plan["maximum_possible_core_calls"] == 168
        and plan["maximum_required_fits"] == 3
    )
    assert plan["schema_version"] == "rc-control-runtime-selection-plan.v2"
    assert result["schema_version"] == "rc-control-runtime-selection-result.v2"
    assert (
        result["fit_completed_count"] == 2
        and len(result["folds"]) == len(observed) == 6
    )
    assert [f["fit_index"] for f in result["folds"]] == [0, 0, 0, 1, 1, 1]
    assert [f["repetition_index"] for f in result["folds"]] == [0, 1, 2, 0, 1, 2]
    assert [list(item[1]) for item in observed] == schedule * 2
    assert len(set(item[0] for item in observed)) == 2
    assert observed[0][2] == observed[1][2] == observed[2][2]
    assert observed[3][2] == observed[4][2] == observed[5][2]
    assert not result["repeats_are_independent_cases"]
    assert (
        not result["validation_or_holdout_execution"]
        and not result["net_savings_proved"]
    )
    assert result["selected_strategy"] == "secant" and result["selected_policy"] is None
    assert (
        sum(
            f["score"]["execution_work"]["known_work"]["core_calls"]
            for f in result["folds"]
        )
        == 120
    )
    for fold in result["folds"]:
        folder = root / f"fold-{fold['index']:04d}"
        score = fold["score"]
        assert score["full_comparison_pass"] and score["proposed_count"] == 0
        assert score["proposal_setup_wall_ns"] == fold["static_model_gate_wall_ns"] > 0
        assert (
            score["proposal_scored_wall_ns"]
            == score["proposal_path_wall_ns"] + score["proposal_setup_wall_ns"]
        )
        baseline = json.loads((folder / "secant/path.json").read_bytes())
        proposal = json.loads((folder / "proposal/path.json").read_bytes())
        for arm in ("reference", "secant", "proposal", "fresh-reference"):
            path = json.loads((folder / arm / "path.json").read_bytes())
            invocations = path["preload_invocations"] + [
                inv for entry in path["entries"] for inv in entry["invocations"]
            ]
            assert len(invocations) == 5
            for inv in invocations:
                work = inv["newton_assembly_work"]
                assert (
                    work["call_count"]
                    == work["returned_count"]
                    == len(work["calls"])
                    > 0
                )
                assert work["exception_count"] == work["in_flight_count"] == 0
                assert work["outside_newton_assembly_calls"] is None
        assert baseline["response_history"] == proposal["response_history"]
        assert baseline["terminal_checkpoint"] == proposal["terminal_checkpoint"]
    for case in result["candidates"][0]["case_repeat_scores"]:
        assert case["requested_repetitions"] == case["valid_repetitions"] == 3
        assert case["mean_ratio"] == pytest.approx(np.mean(case["ratios"]))
        assert case["sample_standard_deviation"] == pytest.approx(
            np.std(case["ratios"], ddof=1)
        )


@pytest.mark.parametrize("repetitions", [None, True, 0, 2, 4, "3", 3.0])
def test_repetition_count_rejects_before_preflight_or_output(
    tmp_path, original, monkeypatch, repetitions
):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid repeats must reject before data validation")

    monkeypatch.setattr(selection, "_validated_training_data", forbidden)
    with pytest.raises(ValueError, match="counterbalanced repetitions"):
        run(tmp_path / "bad", original, repetitions=repetitions)
    assert not (tmp_path / "bad").exists()


def test_repeated_core_reservation_rejects_before_fit(tmp_path, original, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("insufficient repeated budget must reject before fit")

    monkeypatch.setattr(learning, "_fit", forbidden)
    with pytest.raises(ValueError, match="up to 168 core calls"):
        run(
            tmp_path / "short",
            original,
            repetitions=3,
            ridge_grid=(1e4,),
            maximum_core_calls=167,
        )
    assert not (tmp_path / "short").exists()


def test_failed_repeat_remains_in_denominator_and_disqualifies_candidate(
    tmp_path, original, monkeypatch
):
    # Synthetic timing/physical-status controls, not evidence of a speed benefit.
    calls = injected_benchmark(original, monkeypatch, (0.5, 0.5, 0.5))
    template = learning.benchmark_rc_control_seed_paths

    def one_failed(*args, **kwargs):
        report = template(*args, **kwargs)
        if len(calls) == 3:
            report["comparisons"]["proposal"]["full_history_pass"] = False
        return report

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", one_failed)
    result = run(
        tmp_path / "failed-repeat",
        original,
        repetitions=3,
        ridge_grid=(1e4,),
        maximum_core_calls=168,
    )
    candidate = result["candidates"][0]
    assert len(calls) == 6 and result["fit_completed_count"] == 2
    assert candidate["score"] is None and result["selected_strategy"] == "secant"
    first = candidate["case_repeat_scores"][0]
    assert (
        first["ratios"] == [0.5, 0.5, None]
        and first["requested_repetitions"] == 3
        and first["valid_repetitions"] == 2
    )
    assert (
        first["mean_ratio"]
        is first["minimum_ratio"]
        is first["maximum_ratio"]
        is first["sample_standard_deviation"]
        is None
    )
    assert candidate["case_repeat_scores"][1]["mean_ratio"] == 0.5


def test_repeated_score_preserves_each_case_and_counts_one_fit_per_case(
    tmp_path, original, monkeypatch
):
    # Invented ratios isolate aggregation and final-refit accounting.
    injected_benchmark(original, monkeypatch, (0.8, 0.9, 1.0))
    result = run(
        tmp_path / "synthetic-repeat",
        original,
        repetitions=3,
        ridge_grid=(1e4,),
        maximum_core_calls=168,
    )
    scores = result["candidates"][0]["case_repeat_scores"]
    assert scores[0]["ratios"] == [0.8, 0.8, 0.9] and scores[1]["ratios"] == [
        0.9,
        1.0,
        1.0,
    ]
    assert result["candidates"][0]["score"] == pytest.approx(0.9)
    assert result["fit_completed_count"] == 3
    assert not result["candidate_promoted"] and not result["independent_evaluation"]


def test_six_repeat_schedule_has_two_observations_in_every_arm_position(
    tmp_path, original, monkeypatch
):
    # Synthetic runtime reports only verify scheduling and accounting.
    injected_benchmark(original, monkeypatch, (1.2,) * 6)
    real_control = learning.benchmark_rc_control_seed_paths
    observed = []

    def observe(*args, **kwargs):
        observed.append(kwargs["arm_order"])
        return real_control(*args, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    result = run(
        tmp_path / "six",
        original,
        repetitions=6,
        ridge_grid=(1e4,),
        maximum_core_calls=336,
    )
    assert (
        len(result["folds"]) == len(observed) == 12
        and result["fit_completed_count"] == 2
    )
    for offset in (0, 6):
        orders = observed[offset : offset + 6]
        for arm in ["reference", "secant", "proposal"]:
            for position in range(3):
                assert sum(order[position] == arm for order in orders) == 2
    assert all(
        c["requested_repetitions"] == c["valid_repetitions"] == 6
        for c in result["candidates"][0]["case_repeat_scores"]
    )


@pytest.mark.parametrize("value", [True, False])
def test_assembly_recording_boolean_is_declared_and_forwarded(
    tmp_path, original, monkeypatch, value
):
    observed = []
    real = learning.benchmark_rc_control_seed_paths

    def observe(*args, **kwargs):
        observed.append(kwargs.get("record_assembly_work", False))
        return real(*args, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    result = run(
        tmp_path / "recording", original, ridge_grid=(1e4,), record_assembly_work=value
    )
    assert observed == [value, value]
    assert ("assembly_work_recording" in result) is value


@pytest.mark.parametrize("value", [1, None, "true"])
def test_invalid_assembly_recording_rejects_before_training_or_output(tmp_path, value):
    with pytest.raises(ValueError, match="explicit boolean assembly"):
        selection.run_rc_control_runtime_selection(
            None,
            None,
            None,
            source_revision="a" * 40,
            output_directory=tmp_path / "absent",
            ridge_grid=(1e4,),
            record_assembly_work=value,
        )
    assert not (tmp_path / "absent").exists()
