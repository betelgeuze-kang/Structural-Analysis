"""Generation-only predecessor exports from bounded authored solver inputs."""

import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.io.neutral.loader import load_neutral_json


@pytest.mark.parametrize(
    "options",
    [
        {"export_generation_prior_work": 1},
        {"export_generation_prior_work": None},
        {"record_generation_assembly_work": "yes"},
        {"record_generation_assembly_work": 0},
        {"record_generation_assembly_work": True},
    ],
)
def test_export_options_reject_before_input_consumption_or_output(tmp_path, options):
    def never_consume():
        raise AssertionError("invalid options consumed cases")
        yield

    with pytest.raises(ValueError, match="generation"):
        learning.run_rc_control_learning_study(
            never_consume(),
            source_revision="a" * 40,
            output_directory=tmp_path / "invalid",
            **options,
        )
    assert not (tmp_path / "invalid").exists()


def _authored_cases(tmp_path):
    path = Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    train = learning.RCControlLearningCase(
        "authored-train",
        "train-project",
        "train-geometry",
        "train-history",
        "train",
        load_neutral_json(path),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-7, 1e-7, -0.8e-7), allow_reversals=True, maximum_reversals=2
        ),
    )
    changed = json.loads(path.read_bytes())
    for node in changed["nodes"]:
        if node["id"] == "N2":
            node["coordinates"] = [2.5, 0.0, 0.0]
        elif node["id"] == "N3":
            node["coordinates"] = [2.5, 2.0, 0.0]
    different = tmp_path / "authored-validation-model.json"
    different.write_text(json.dumps(changed))
    validation = learning.RCControlLearningCase(
        "authored-validation",
        "validation-project",
        "validation-geometry",
        "validation-history",
        "validation",
        load_neutral_json(different),
        BoundedRCFiberDirectControlRequest(
            7, (-0.8e-7, 1.2e-7, -0.7e-7), allow_reversals=True, maximum_reversals=2
        ),
    )
    return [train, validation]


@pytest.mark.parametrize("assembly", [False, True])
def test_actual_export_preserves_numeric_samples_and_deferred_evaluation(
    tmp_path, monkeypatch, assembly
):
    # Small checked-in authored input; no measured or retained campaign is read.
    cases = _authored_cases(tmp_path)
    calls = []
    original = learning.benchmark_rc_control_seed_paths

    def observe(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    base, exported = tmp_path / "legacy", tmp_path / "exported"
    common = {
        "source_revision": "e11007a08a4de755090fe615384d068879bac8ba",
        "defer_evaluation": True,
        "fit_solver": learning.CONSTANT_SAFE_SVD_FIT_PROFILE,
    }
    legacy = learning.run_rc_control_learning_study(
        cases, output_directory=base, **common
    )
    report = learning.run_rc_control_learning_study(
        cases,
        output_directory=exported,
        export_generation_prior_work=True,
        record_generation_assembly_work=assembly,
        **common,
    )
    assert len(calls) == 2
    assert "record_prior_accepted_transition_work" not in calls[0]
    assert "record_assembly_work" not in calls[0]
    assert calls[1]["record_prior_accepted_transition_work"] is True
    assert calls[1].get("record_assembly_work", False) is assembly
    assert legacy["fit"]["status"] == report["fit"]["status"] == "completed"
    assert legacy["policy"] == report["policy"]
    raw_samples = (base / "training-samples.json").read_bytes()
    assert raw_samples == (exported / "training-samples.json").read_bytes()
    samples = json.loads(raw_samples)
    assert len(samples) == 2
    assert all("prior_work_binding" not in s["context"] for s in samples)
    assert "generation_prior_work_export" not in legacy
    assert not list(base.glob("generation-prior-work-export*"))
    assert not list(exported.glob("*-evaluation-started.json"))
    assert all(r["status"] == "not_attempted" for r in report["evaluation"])
    receipt = report["generation_prior_work_export"]
    raw_export = (exported / receipt["file"]).read_bytes()
    assert receipt["sha256"] == learning._sha(raw_export)
    assert receipt["byte_length"] == len(raw_export)
    assert receipt["wall_ns"] >= 0 and receipt["cpu_ns"] >= 0
    assert receipt["policy_specific_label_lineage_checked"] is False
    assert report["whole_study_wall_ns"] >= receipt["wall_ns"]
    assert report["whole_study_cpu_ns"] >= receipt["cpu_ns"]
    export = json.loads(raw_export)
    rows = export["rows"]
    assert [r["target_index"] for r in rows] == [0, 1, 2]
    assert {r["case_id"] for r in rows} == {"authored-train"}
    assert rows[0]["status"] == "unavailable"
    assert rows[0]["source_sample_hash"] is None
    assert not rows[0]["six_counter_profile_usable"]
    for row, sample in zip(rows[1:], samples, strict=True):
        assert row["status"] == "available"
        assert row["source_sample_hash"] == sample["sample_hash"]
        assert row["counters"]["core_calls"] == 1
        assert row["six_counter_profile_usable"] is assembly
        assert row["producer_role"] == "generation-reference"
        assert "prior_work_context" not in row
        descriptor = row["prior_work_context_artifact"]
        raw_context = (exported / descriptor["path"]).read_bytes()
        assert descriptor["sha256"] == learning._sha(raw_context)
        assert descriptor["byte_length"] == len(raw_context)
        assert json.loads(raw_context)["prior_accepted_transition_work"]
        if not assembly:
            assert row["counters"]["assembly_dispatches"] is None
            assert row["counters"]["line_search_dispatches"] is None
            assert row["counters"]["terminal_refinement_dispatches"] is None


def test_failed_generation_keeps_complete_unavailable_target_roster(
    tmp_path, monkeypatch
):
    calls = []

    def fail_generation(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("authored bounded failure")

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", fail_generation)
    report = learning.run_rc_control_learning_study(
        _authored_cases(tmp_path),
        source_revision="a" * 40,
        output_directory=tmp_path / "failed-generation",
        export_generation_prior_work=True,
    )
    assert len(calls) == 1
    assert report["fit"] is None
    assert report["evaluation"][0]["reason"] == "training_not_completed"
    export = json.loads(
        (tmp_path / "failed-generation/generation-prior-work-export.json").read_bytes()
    )
    assert len(export["rows"]) == 3
    assert all(r["status"] == "unavailable" for r in export["rows"])
    assert all(not r["six_counter_profile_usable"] for r in export["rows"])


def test_actual_ordinary_evaluation_does_not_receive_generation_recording(
    tmp_path, monkeypatch
):
    calls = []
    original = learning.benchmark_rc_control_seed_paths

    def observe(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", observe)
    report = learning.run_rc_control_learning_study(
        _authored_cases(tmp_path),
        source_revision="a" * 40,
        output_directory=tmp_path / "ordinary-evaluation",
        export_generation_prior_work=True,
        record_generation_assembly_work=True,
        fit_solver=learning.CONSTANT_SAFE_SVD_FIT_PROFILE,
    )
    assert report["fit"]["status"] == "completed"
    assert len(calls) == 2
    assert calls[0]["record_prior_accepted_transition_work"] is True
    assert calls[0]["record_assembly_work"] is True
    assert "record_prior_accepted_transition_work" not in calls[1]
    assert "record_assembly_work" not in calls[1]
    assert "proposal" in calls[1]
    assert report["evaluation"][0]["status"] == "returned"
