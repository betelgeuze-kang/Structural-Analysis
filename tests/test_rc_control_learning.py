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
            lengths=(6.0, 5.0),
            history=(-0.75e-5, -1.6e-5, -0.2e-5, 0.9e-5, 0.0, -0.3e-5),
        ),
    ]


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
def test_split_aliases_stop_before_output_or_solver(tmp_path, monkeypatch, kind):
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
            [a, b], source_revision="a" * 40, output_directory=tmp_path / "study"
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
    a = case(tmp_path, "a", "train", history=HISTORY[:3])
    b = case(
        tmp_path, "b", "holdout", lengths=(3.0, 2.5), history=(-1e-5, -3e-5, -2e-5)
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
    assert report["generation_work"]["known_work"]["core_calls"] == 9
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
