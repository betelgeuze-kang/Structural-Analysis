"""Model-aware input routing at the pre-step boundary; no numerical solves."""

from dataclasses import replace
from pathlib import Path

import pytest

from structural_analysis.ai import fiber_frame_warm_start_features as features
from structural_analysis.ai import fiber_frame_warm_start_learning as learning
from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.benchmark import fiber_frame_runtime as runtime
from structural_analysis.io.neutral.loader import load_neutral_json


BASE = Path(__file__).parent / "fixtures/fiber_frame_candidate_process/base.json"


@pytest.fixture
def problem(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("input-routing test must not solve or assemble a material trial")

    monkeypatch.setattr(public, "analyze_public_rc_fiber_frame", forbidden)
    monkeypatch.setattr(runtime, "solve_stateful_fiber_frame2d_load_step", forbidden)
    monkeypatch.setattr(runtime, "assemble_stateful_fiber_frame2d", forbidden)
    compiled, blockers, _ = public._compile(load_neutral_json(BASE))
    assert compiled is not None and not blockers
    return compiled.problem


class CapturePolicy:
    model_feature_profile = features.MODEL_FEATURE_PROFILE

    def __init__(self):
        self.inputs = []

    def propose(self, value):
        self.inputs.append(value)
        return runtime.FiberFrameWarmStartProposal(
            value.parent_free_coordinates_m, 0.0, False
        )


def _route(problem, policy):
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    original = parent.canonical_bytes()
    result = runtime._ai_proposal(
        policy,
        problem,
        [parent],
        0.5,
        runtime.FiberFrameRuntimeBenchmarkConfig(),
    )
    assert parent.canonical_bytes() == original
    return result


def test_conditioned_policy_receives_only_current_problem_model_features(problem):
    policy = CapturePolicy()
    result = _route(problem, policy)
    assert result[3] == "policy_prediction_available"
    assert len(policy.inputs) == 1
    supplied = policy.inputs[0]
    assert supplied.model_features.to_dict() == (
        features.fiber_frame_warm_start_model_features(problem).to_dict()
    )
    assert supplied.model_features.problem_contract_hash == problem.contract_hash
    assert supplied.parent_free_coordinates_m == (0.0,) * len(problem.free_global_dofs)
    assert supplied.previous_free_coordinates_m is None
    assert learning._input_snapshot(supplied) == supplied


@pytest.mark.parametrize("profile", [None, "legacy-does-not-request-features"])
def test_feature_opt_in_and_unknown_profile_cannot_silently_infer(
    problem, monkeypatch, profile
):
    policy = CapturePolicy()
    policy.model_feature_profile = profile

    def forbidden(*args, **kwargs):
        pytest.fail("legacy or unsupported profile must not prepare model features")

    monkeypatch.setattr(features, "fiber_frame_warm_start_model_features", forbidden)
    result = _route(problem, policy)
    if profile is None:
        assert result[3] == "policy_prediction_available"
        assert policy.inputs[0].model_features is None
        assert "model_features" not in learning._input_payload(policy.inputs[0])
    else:
        assert result == (None, None, None, "policy_model_feature_profile_unsupported")
        assert not policy.inputs


def test_failed_feature_preparation_preserves_parent_and_skips_policy(
    problem, monkeypatch
):
    policy = CapturePolicy()

    def failed(*args, **kwargs):
        raise ValueError("unsupported pre-analysis model feature")

    monkeypatch.setattr(features, "fiber_frame_warm_start_model_features", failed)
    assert _route(problem, policy) == (
        None,
        None,
        None,
        "policy_model_feature_preparation_failed",
    )
    assert not policy.inputs


@pytest.mark.parametrize("mutation", ["wrong-problem", "plain-dictionary"])
def test_sample_snapshot_rejects_detached_feature_bindings(problem, mutation):
    policy = CapturePolicy()
    _route(problem, policy)
    supplied = policy.inputs[0]
    if mutation == "wrong-problem":
        changed = replace(
            supplied.model_features,
            problem_contract_hash="sha256:" + "1" * 64,
        )
    else:
        changed = supplied.model_features.to_dict()
    with pytest.raises(
        learning.FiberFrameWarmStartLearningError, match="model_features"
    ):
        learning._input_snapshot(replace(supplied, model_features=changed))


def test_sample_versions_retain_legacy_payload_and_bind_new_features(problem):
    policy = CapturePolicy()
    _route(problem, policy)
    supplied = policy.inputs[0]

    def sample(value):
        return learning.FiberFrameWarmStartSample(
            "sample",
            "project",
            "geometry",
            "history",
            "sha256:" + "2" * 64,
            value.problem_contract_hash,
            "train",
            value,
            (0.0,) * len(value.free_global_dofs),
        )

    conditioned = sample(supplied).to_dict()
    legacy = sample(replace(supplied, model_features=None)).to_dict()
    assert conditioned["schema_version"] == "fiber-frame-warm-start-sample.v2"
    assert legacy["schema_version"] == "fiber-frame-warm-start-sample.v1"
    assert "model_features" not in legacy["runtime_input"]
    assert (
        conditioned["runtime_input"]["model_features"]
        == supplied.model_features.to_dict()
    )
    assert legacy["sample_hash"] != conditioned["sample_hash"]


@pytest.mark.parametrize(
    "mutation", ["translation", "rotation", "zero_length", "missing_length"]
)
def test_compiled_model_and_runtime_coordinate_scales_must_agree(problem, mutation):
    policy = CapturePolicy()
    _route(problem, policy)
    supplied = policy.inputs[0]
    if mutation in ("translation", "rotation"):
        scale = list(supplied.physical_coordinate_scale)
        scale[0 if mutation == "translation" else 2] *= 2.0
        changed = replace(supplied, physical_coordinate_scale=tuple(scale))
    else:
        model = supplied.model_features
        index = model.feature_names.index("rotation_coordinate_scale_m")
        if mutation == "zero_length":
            values = list(model.values)
            values[index] = 0.0
            model = replace(model, values=tuple(values))
        else:
            names = list(model.feature_names)
            names[index] = "missing_rotation_length"
            model = replace(model, feature_names=tuple(names))
        changed = replace(supplied, model_features=model)
    with pytest.raises(
        learning.FiberFrameWarmStartLearningError, match="model_features"
    ):
        learning._input_snapshot(changed)
    # Legacy history-only inputs still retain their existing coordinate profile
    # semantics and payload: the new metadata relation is opt-in only.
    legacy = replace(changed, model_features=None)
    assert learning._input_snapshot(legacy).model_features is None
