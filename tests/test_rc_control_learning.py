"""Actual cyclic labels, train-only fitting and conservative split rejection."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.io.neutral.loader import load_neutral_json


HISTORY = (-1e-5, -2e-5, -1e-5, 1e-5, 0.0, -0.5e-5)


def case(
    tmp_path,
    name,
    split,
    *,
    lengths=(2.0, 1.5),
    history=HISTORY,
    project=None,
    family=None,
    load=None,
):
    model = json.loads(
        Path(
            "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ).read_bytes()
    )
    for node in model["nodes"]:
        if node["id"] == "N2":
            node["coordinates"] = [lengths[0], 0.0, 0.0]
        if node["id"] == "N3":
            node["coordinates"] = [lengths[0], lengths[1], 0.0]
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(model))
    return learning.RCControlLearningCase(
        name,
        project or name,
        family or name,
        load or name,
        split,
        load_neutral_json(path),
        BoundedRCFiberDirectControlRequest(
            7, tuple(history), allow_reversals=True, maximum_reversals=2
        ),
    )


@pytest.fixture
def cases(tmp_path):
    return [
        case(tmp_path, "train-a", "train"),
        case(tmp_path, "train-b", "train", lengths=(3.0, 2.5)),
        case(
            tmp_path,
            "validation",
            "validation",
            lengths=(2.5, 2.0),
            history=(-0.5e-5, -1.5e-5, -0.25e-5, 1.1e-5, 0.0, -0.4e-5),
        ),
        case(
            tmp_path,
            "holdout",
            "holdout",
            lengths=(6.0, 4.7),
            history=(-0.75e-5, -1.6e-5, -0.2e-5, 0.9e-5, 0.0, -0.3e-5),
        ),
    ]


def test_fit_interrupt_preserves_unknown_started_record_and_original_exception(
    tmp_path, cases, monkeypatch
):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt("injected fit interruption")

    monkeypatch.setattr(learning, "_fit", interrupt)
    root = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt, match="injected fit interruption"):
        learning.run_rc_control_learning_study(
            cases, source_revision="a" * 40, output_directory=root
        )
    started = json.loads((root / "fit-started.json").read_bytes())
    assert started["unknown_fit_work_until_outcome"]
    assert not (root / "fit-outcome.json").exists()
    assert not (root / "learning-study.json").exists()
    assert not list(root.glob("*-evaluation-started.json"))


def test_actual_history_feature_study_preserves_original_labels_and_executes_proposals(
    tmp_path, cases
):
    from structural_analysis.benchmark.rc_control_history_features import (
        HISTORY_FEATURE_PROFILE,
    )

    root = tmp_path / "history-study"
    report = learning.run_rc_control_learning_study(
        cases,
        source_revision="a" * 40,
        output_directory=root,
        feature_profile=HISTORY_FEATURE_PROFILE,
        ood_margin=1.0,
    )
    assert report["fit"]["status"] == "completed"
    assert report["feature_profile"] == HISTORY_FEATURE_PROFILE
    assert report["policy"]["schema_version"].endswith(".v3")
    assert report["generation_work"]["known_work"]["core_calls"] == 36
    assert report["generation_work"]["unknown_work"] is False
    assert report["evaluation_work"]["unknown_work"] is False
    rows = json.loads((root / "training-samples.json").read_bytes())
    assert len(rows) == 10 and {row["split"] for row in rows} == {"train"}
    import numpy as np

    for row in rows:
        assert row["feature_profile"] == HISTORY_FEATURE_PROFILE
        assert np.array_equal(
            np.asarray(row["source_correction"]) / row["correction_coordinate_scales"],
            row["correction"],
        )
        assert row["sample_hash"] == learning._sha(
            learning._bytes({k: v for k, v in row.items() if k != "sample_hash"})
        )
    for case_result in report["evaluation"]:
        assert case_result["status"] == "returned"
        assert case_result["report"]["reference_repeat_exact"]
    assert any(
        row["decision"] == "proposed"
        for case_result in report["evaluation"]
        for row in case_result["proposal_decisions"]
    )
    assert report["claims"]["performance_improvement"] is False


def test_actual_train_only_fit_then_frozen_evaluation(tmp_path, cases, monkeypatch):
    events = []
    original = learning.benchmark_rc_control_seed_paths
    fit = learning._fit

    def observe(*a, **kw):
        events.append(
            (
                "evaluation" if kw.get("proposal") else "generation",
                str(kw["output_directory"]),
            )
        )
        return original(*a, **kw)

    def train(samples, *a, **kw):
        events.append(("fit", None))
        assert {s["case_id"] for s in samples} == {"train-a", "train-b"}
        assert all(s["split"] == "train" for s in samples)
        return fit(samples, *a, **kw)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    monkeypatch.setattr(learning, "_fit", train)
    report = learning.run_rc_control_learning_study(
        cases,
        source_revision="a" * 40,
        output_directory=tmp_path / "study",
        ood_margin=1.0,
    )
    assert report["fit"]["status"] == "completed"
    assert [e[0] for e in events] == [
        "generation",
        "generation",
        "fit",
        "evaluation",
        "evaluation",
    ]
    assert report["claims"]["policy_training_performed"] is True
    assert report["claims"]["independent_validation"] is False
    screen = report["measured_source_split_screen"]
    assert screen["cases_without_measured_source"] == [c.case_id for c in cases]
    assert not screen["independent_provenance_verified"]
    plan = json.loads((tmp_path / "study/plan.json").read_bytes())
    assert plan["measured_source_split_screen"] == {
        key: value for key, value in screen.items() if key != "screen_wall_ns"
    }
    samples = json.loads((tmp_path / "study/training-samples.json").read_bytes())
    assert len(samples) == 10
    assert report["generation_work"]["known_work"]["core_calls"] == 36
    assert report["evaluation_work"]["known_work"]["core_calls"] >= 48
    assert report["generation_work"]["unknown_work"] is False
    assert report["evaluation_work"]["unknown_work"] is False
    assert len(report["policy"]["training_sample_hashes"]) == 10
    assert report["policy"]["training_sample_hashes"] == [
        s["sample_hash"] for s in samples
    ]
    policy = learning.RCControlSeedPolicy(learning._bytes(report["policy"]).decode())
    assert policy.policy_hash == report["policy"]["policy_hash"]
    for row in report["evaluation"]:
        assert row["status"] == "returned"
        assert row["report"]["reference_repeat_exact"]
        assert row["report"]["all_execution_work_reported"]
        assert row["report"]["proposal_identity"] == policy.policy_hash
        assert row["proposal_decisions"][0]["decision"] == "abstained_to_reference"
        assert len(row["proposal_decisions"]) == 6
    validation = report["evaluation"][0]
    assert any(d["decision"] == "proposed" for d in validation["proposal_decisions"])
    assert all(
        d["decision"] == "abstained_to_reference"
        for d in report["evaluation"][1]["proposal_decisions"]
    )
    # Every preprocessing statistic is computed from the recorded training rows.
    import numpy as np

    assert np.array_equal(
        np.asarray(report["policy"]["feature_mean"]),
        np.asarray([s["features"] for s in samples]).mean(axis=0),
    )
    for field, value in [
        ("ridge", True),
        ("free_global_dofs", [True] * 6),
        ("weights", [[True] * 7] * (len(report["policy"]["weights"]))),
    ]:
        altered = deepcopy(report["policy"])
        altered[field] = value
        altered.pop("policy_hash")
        altered["policy_hash"] = learning._sha(learning._bytes(altered))
        with pytest.raises(ValueError):
            learning.RCControlSeedPolicy(learning._bytes(altered).decode())
    raw = learning._bytes(report["policy"]).decode()
    duplicate = raw[:-1] + ',"ridge":1e-6}'
    with pytest.raises(ValueError):
        learning.RCControlSeedPolicy(duplicate)
    detached = policy.to_dict()
    detached["weights"][0][0] += 1
    assert policy.to_dict() == report["policy"]


@pytest.mark.parametrize(
    "kind",
    [
        "project",
        "family",
        "load",
        "geometry",
        "history",
        "scaled_history",
        "sign_history",
        "prefix_history",
    ],
)
@pytest.mark.parametrize(
    "arithmetic_profile", ["binary64", learning.RETAINED_LEARNING_ARITHMETIC_PROFILE]
)
def test_split_aliases_stop_before_output_or_solver(
    tmp_path, monkeypatch, kind, arithmetic_profile
):
    a = case(tmp_path, "a", "train")
    kw = {"lengths": (2.5, 2.0), "history": (-1e-5, -3e-5, -1e-5, 2e-5, 0.0, -0.2e-5)}
    if kind in ("project", "family", "load"):
        kw[kind] = "a"
    if kind == "geometry":
        kw["lengths"] = (2.0, 1.5)
    if kind == "history":
        kw["history"] = HISTORY
    if kind == "scaled_history":
        kw["history"] = tuple(x * 2 for x in HISTORY)
    if kind == "sign_history":
        kw["history"] = tuple(-x for x in HISTORY)
    if kind == "prefix_history":
        kw["history"] = HISTORY[:3]
    b = case(tmp_path, "b", "holdout", **kw)
    monkeypatch.setattr(
        learning,
        "benchmark_rc_control_seed_paths",
        lambda *a, **k: pytest.fail("leaked case reached numerical collection"),
    )
    with pytest.raises(ValueError, match="split_leakage"):
        learning.run_rc_control_learning_study(
            polished_cases([a, b]) if arithmetic_profile != "binary64" else [a, b],
            source_revision="a" * 40,
            output_directory=tmp_path / "study",
            arithmetic_profile=arithmetic_profile,
        )
    assert not (tmp_path / "study").exists()


def test_case_model_is_detached(tmp_path):
    c = case(tmp_path, "a", "train")
    checksum = c.model.canonical_model_checksum
    m = c.model
    m.nodes[0]["coordinates"][0] = 99
    assert c.model.canonical_model_checksum == checksum


def test_failed_generation_keeps_roster_and_skips_fitting_evaluation(
    tmp_path, cases, monkeypatch
):
    calls = []

    def raises(*args, **kwargs):
        calls.append(kwargs["output_directory"])
        raise RuntimeError("injected unknown generation work")

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", raises)
    report = learning.run_rc_control_learning_study(
        cases, source_revision="a" * 40, output_directory=tmp_path / "study"
    )
    assert (
        len(calls) == 2
        and len(report["generation"]) == 2
        and len(report["evaluation"]) == 2
    )
    assert all(row["unknown_work"] for row in report["generation"])
    assert all(row["status"] == "not_attempted" for row in report["evaluation"])
    assert report["policy"] is None and report["fit"] is None
    assert not report["claims"]["policy_training_performed"]


def test_fit_failure_retains_training_cost_and_skips_all_evaluation(
    tmp_path, monkeypatch
):
    a = case(tmp_path, "a", "train", history=HISTORY)
    b = case(
        tmp_path,
        "b",
        "holdout",
        lengths=(3.0, 2.5),
        history=(-1e-5, -3e-5, 2e-5, -1e-5),
    )
    monkeypatch.setattr(
        learning,
        "_fit",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("injected fit failure")),
    )
    report = learning.run_rc_control_learning_study(
        [a, b], source_revision="a" * 40, output_directory=tmp_path / "study"
    )
    assert report["fit"]["status"] == "failed" and report["fit"]["unknown_fit_work"]
    assert report["generation_work"]["known_work"]["core_calls"] == 18
    assert report["evaluation_work"]["known_work"]["core_calls"] == 0
    assert report["evaluation"][0]["status"] == "not_attempted"
    assert not report["claims"]["policy_training_performed"]


def test_invalid_arm_roster_stops_before_collection(tmp_path, cases, monkeypatch):
    monkeypatch.setattr(
        learning,
        "benchmark_rc_control_seed_paths",
        lambda *a, **k: pytest.fail("bad arm order reached solver"),
    )
    with pytest.raises(ValueError, match="arm order"):
        learning.run_rc_control_learning_study(
            cases,
            source_revision="a" * 40,
            output_directory=tmp_path / "study",
            evaluation_arm_order=("proposal", "proposal", "reference"),
        )
    assert not (tmp_path / "study").exists()


def polished_cases(cases):
    from dataclasses import replace

    return [
        learning.RCControlLearningCase(
            c.case_id,
            c.project_id,
            c.geometry_family_id,
            c.load_history_id,
            c.split,
            c.model,
            replace(
                c.request,
                solver_config=replace(
                    c.request.solver_config,
                    newton=replace(
                        c.request.solver_config.newton, terminal_polishing=True
                    ),
                ),
            ),
        )
        for c in cases
    ]


@pytest.mark.parametrize("profile", ["unknown", None, True, 2])
def test_learning_arithmetic_profile_rejects_unknown_before_output(
    tmp_path, cases, monkeypatch, profile
):
    monkeypatch.setattr(
        learning,
        "benchmark_rc_control_seed_paths",
        lambda *a, **k: pytest.fail("invalid profile reached solver"),
    )
    with pytest.raises(ValueError, match="arithmetic profile"):
        learning.run_rc_control_learning_study(
            cases,
            source_revision="a" * 40,
            output_directory=tmp_path / "study",
            arithmetic_profile=profile,
        )
    assert not (tmp_path / "study").exists()


def test_retained_learning_requires_polishing_before_any_label(
    tmp_path, cases, monkeypatch
):
    monkeypatch.setattr(
        learning,
        "benchmark_rc_control_seed_paths",
        lambda *a, **k: pytest.fail("disabled polishing reached label generation"),
    )
    with pytest.raises(ValueError, match="requires enabled terminal polishing"):
        learning.run_rc_control_learning_study(
            cases,
            source_revision="a" * 40,
            output_directory=tmp_path / "study",
            arithmetic_profile=learning.RETAINED_LEARNING_ARITHMETIC_PROFILE,
        )
    assert not (tmp_path / "study").exists()


def test_retained_context_preserves_physical_features_and_public_type_boundary(cases):
    from structural_analysis.ai.fiber_frame_warm_start_features import (
        fiber_frame_warm_start_model_features,
    )

    rows = polished_cases(cases)
    old = learning._preflight(rows)
    new = learning._preflight(rows, learning.RETAINED_LEARNING_ARITHMETIC_PROFILE)
    for c in rows:
        _, compiled, features, _, _ = new[c.case_id]
        baseline = old[c.case_id][2]
        assert (
            features.values == baseline.values
            and features.feature_names == baseline.feature_names
        )
        assert features.problem_contract_hash == compiled.problem.contract_hash
        assert features.problem_contract_hash != baseline.problem_contract_hash
        assert features.context_hash != baseline.context_hash
        with pytest.raises(ValueError, match="exact immutable RC member sections"):
            fiber_frame_warm_start_model_features(compiled.problem)


def test_retained_training_and_evaluation_bind_same_profile_and_preserve_original_labels(
    tmp_path, cases, monkeypatch
):
    import numpy as np
    from dataclasses import replace

    profile = learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
    rows = polished_cases(cases)
    original = learning.benchmark_rc_control_seed_paths
    calls = []

    def observe(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    report = learning.run_rc_control_learning_study(
        rows,
        source_revision="a" * 40,
        output_directory=tmp_path / "study",
        arithmetic_profile=profile,
        ood_margin=1.0,
    )
    assert report["fit"]["status"] == "completed"
    expected = learning._arithmetic_manifest(profile)
    assert report["arithmetic_profile"] == expected
    assert len(calls) == 4
    for kwargs in calls:
        assert all(
            kwargs[k] == v for k, v in learning._arithmetic_kwargs(profile).items()
        )
    assert (
        not report["generation_work"]["unknown_work"]
        and not report["evaluation_work"]["unknown_work"]
    )
    assert report["generation_work"]["known_work"]["core_calls"] == 36
    assert all(
        r["report"]["reference_repeat_exact"]
        for r in report["generation"] + report["evaluation"]
    )
    assert all(r["status"] == "returned" for r in report["evaluation"])
    assert any(
        d["decision"] == "proposed"
        for d in report["evaluation"][0]["proposal_decisions"]
    )
    assert all(
        d["decision"] == "abstained_to_reference"
        for d in report["evaluation"][1]["proposal_decisions"]
    )
    samples = json.loads((tmp_path / "study/training-samples.json").read_text())
    assert len(samples) == 10 and {s["case_id"] for s in samples} == {
        "train-a",
        "train-b",
    }
    for sample in samples:
        raw = (
            tmp_path
            / "study"
            / sample["case_id"]
            / "generation/reference"
            / f"{sample['target_index']:03d}-1-step.json"
        ).read_bytes()
        step = json.loads(raw)
        assert sample["original_step_bytes_hash"] == learning._sha(raw)
        assert (
            sample["accepted_coordinates"]
            == step["trial_solution"]["augmented_coordinates_m"]
        )
        assert (
            sample["accepted_coordinate_compensation_m"]
            == step["trial_solution"]["augmented_coordinate_compensation_m"]
        )
        assert sample["arithmetic_profile"] == expected
    assert np.array_equal(
        np.asarray(report["policy"]["feature_mean"]),
        np.asarray([s["features"] for s in samples]).mean(axis=0),
    )
    policy = learning.RCControlSeedPolicy(learning._bytes(report["policy"]).decode())
    assert (
        policy.to_dict()["schema_version"].endswith(".v2")
        and policy.to_dict()["arithmetic_profile"] == expected
    )
    prepared = learning._preflight(rows, profile)
    _, compiled, features, _, _ = prepared["train-a"]
    sample = next(s for s in samples if s["case_id"] == "train-a")
    context = learning.RCControlSeedContext(**sample["context"])
    context = replace(
        context,
        accepted_targets_m=tuple(context.accepted_targets_m),
        accepted_augmented_coordinates_m=tuple(
            tuple(q) for q in context.accepted_augmented_coordinates_m
        ),
    )
    args = (
        context,
        features,
        compiled.problem.free_global_dofs,
        rows[0].request.solver_config.contract_hash,
    )
    assert policy.propose(*args) is None
    assert policy.propose(*args, arithmetic_profile=profile) is not None
    # Even an otherwise matching v1 document cannot be used under v2 arithmetic.
    legacy = policy.to_dict()
    legacy["schema_version"] = "experimental-rc-control-secant-correction-policy.v1"
    legacy.pop("arithmetic_profile")
    legacy.pop("policy_hash")
    legacy["policy_hash"] = learning._sha(learning._bytes(legacy))
    old_policy = learning.RCControlSeedPolicy(learning._bytes(legacy).decode())
    assert old_policy.propose(*args, arithmetic_profile=profile) is None
    for value in [1, 2.0, True, 3, "2"]:
        tampered = policy.to_dict()
        tampered["arithmetic_profile"]["terminal_refinement_limit"] = value
        tampered.pop("policy_hash")
        tampered["policy_hash"] = learning._sha(learning._bytes(tampered))
        with pytest.raises(ValueError, match="arithmetic profile"):
            learning.RCControlSeedPolicy(learning._bytes(tampered).decode())
    import os
    import subprocess
    import sys

    raw = tmp_path / "policy.json"
    raw.write_text(learning._bytes(report["policy"]).decode())
    code = "from pathlib import Path;import sys;from structural_analysis.benchmark.rc_control_learning import RCControlSeedPolicy;print(RCControlSeedPolicy(Path(sys.argv[1]).read_text()).policy_hash)"
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code, str(raw)],
        env=dict(os.environ, PYTHONPATH=str(Path.cwd() / "src")),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == policy.policy_hash
