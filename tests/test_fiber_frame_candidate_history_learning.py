"""Algebraic and stub-source contracts only; no public numerical analysis.

Typed sidecars below test transport and aggregation, not physical provenance.
The source-accessor stubs are explicit; the actual analyzer is always forbidden.
"""

from copy import deepcopy
from dataclasses import fields, replace
import json
from pathlib import Path

import pytest

from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import (
    fiber_frame_constitutive_history as constitutive,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


PROFILE = learning.CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE
LEGACY = learning.CANDIDATE_TERMINAL_TARGET_PROFILE


def _seal(value, key):
    value[key] = canonical_hash({k: v for k, v in value.items() if k != key})
    return value


def _model(width=0.4, load=-1.0):
    path = (
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    payload = json.loads(path.read_text())
    payload["sections"][0]["width_m"] = width
    payload["loads"][0]["components"]["FY"] = load
    return load_neutral_json_bytes(json.dumps(payload).encode())


def _cases():
    return tuple(
        FiberFrameWarmStartDataCase(
            f"stub-{i}",
            f"project-{i}",
            f"geometry-{i}",
            f"loads-{i}",
            split,
            _model(width),
            public_api.PublicRCFiberFrameConfig(load_steps=2),
        )
        for i, (width, split) in enumerate(
            ((0.34, "train"), (0.46, "train"), (0.37, "validation"), (0.43, "holdout"))
        )
    )


def _source_parts(model, config):
    """Construct labelled test doubles without replaying a physical source."""
    width = model.sections[0]["width_m"]

    def tag(value):
        return canonical_hash((model.canonical_model_checksum, value))

    steps, states = [], [{"epoch": 0}]
    for epoch in (1, 2):
        # An interior response peak demonstrates why terminal labels are distinct.
        translation, strain = (
            (0.002 if epoch == 1 else 0.001) / width,
            (0.0002 if epoch == 1 else 0.0001) / width,
        )
        step = {
            "epoch": epoch,
            "step_index": epoch,
            "target_load_factor": epoch / 2,
            "bindings": {
                "checkpoint_state_hash": tag(epoch),
                "parent_checkpoint_state_hash": tag(epoch - 1),
            },
            "recovery_hash": tag(f"recovery-{epoch}"),
            "metrics": {"total_dissipated_energy_mj": float(epoch)},
            "node_displacements": [{"UX_m": translation, "UY_m": 0.0, "UZ_m": 0.0}],
            "fiber_results": [{"strain": -strain}],
            "envelope": {
                "maximum_translation_m": translation,
                "maximum_absolute_fiber_strain": strain,
            },
        }
        steps.append(step)
        states.append(
            {
                "epoch": epoch,
                "step_index": epoch,
                "load_factor": epoch / 2,
                "checkpoint_state_hash": tag(epoch),
                "parent_checkpoint_state_hash": tag(epoch - 1),
                "engineering_recovery_hash": step["recovery_hash"],
                "total_dissipated_energy_mj": float(epoch),
                "materials": {
                    "steel": {
                        "fields": {
                            "accumulated_plastic_strain": {
                                "maximum": 0.0001 * epoch / width
                            }
                        }
                    },
                    "concrete": {
                        "fields": {
                            "tensile_damage": {"maximum": 0.05 * epoch / width},
                            "compressive_damage": {"maximum": 0.02 * epoch / width},
                        }
                    },
                },
            }
        )
    result = public_api.PublicRCFiberFrameResult(
        status="ready",
        contract_pass=True,
        result_hash=tag("public"),
        canonical_model_checksum=model.canonical_model_checksum,
        input_checksum=model.input_checksum,
        solver_id=public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
        compiler_profile=public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        configuration={},
        contract_bindings={
            "problem_contract_hash": tag("problem"),
            "checkpoint_chain_hash": tag("chain"),
        },
        checkpoint={
            "chain_hash": tag("chain"),
            "artifact_hash": tag("checkpoint"),
            "terminal_state_hash": tag(2),
        },
        authority={},
        node_displacements=tuple(steps[-1]["node_displacements"]),
        fiber_results=tuple(steps[-1]["fiber_results"]),
        support_reactions=(),
        member_end_forces=(),
        section_results=(),
        convergence_history=(),
        metrics={"solver_executed": True},
        unsupported_features=(),
        warnings=(),
    )
    engineering = _seal(
        {
            "schema_version": "stateful-fiber-frame2d-nonlinear-engineering-history.v1",
            "steps": steps,
            "envelope": steps[0]["envelope"],
        },
        "history_hash",
    )
    response = _seal(
        {
            "schema_version": "public-rc-fiber-frame-response-history.v1",
            "status": "ready",
            "contract_pass": True,
            "source_result_hash": result.result_hash,
            "canonical_model_checksum": model.canonical_model_checksum,
            "history_hash": engineering["history_hash"],
            "history": engineering,
        },
        "report_hash",
    )
    material = _seal(
        {
            "schema_version": constitutive.SCHEMA_VERSION,
            "status": "ready",
            "contract_pass": True,
            "bindings": {
                "source_result_hash": result.result_hash,
                "canonical_model_checksum": model.canonical_model_checksum,
                "input_checksum": model.input_checksum,
                "problem_contract_hash": tag("problem"),
                "checkpoint_chain_hash": tag("chain"),
                "checkpoint_artifact_hash": tag("checkpoint"),
                "checkpoint_artifact_byte_length": len(b"stub checkpoint"),
                "response_history_report_hash": response["report_hash"],
                "engineering_history_hash": engineering["history_hash"],
            },
            "accepted_epoch_count": config.load_steps,
            "states": states,
            "claim_boundary": constitutive._CLAIMS,
        },
        "report_hash",
    )
    return result, response, material


@pytest.fixture(autouse=True)
def no_physical_analysis(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("actual public analysis is forbidden in this contract module")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)


@pytest.fixture
def stub_sources(monkeypatch):
    sources, calls = (
        {},
        {
            "analysis_stub": 0,
            "validation_stub": 0,
            "response_stub": 0,
            "material_stub": 0,
        },
    )
    cases = _cases()
    for case in cases:
        parts = _source_parts(case.model, case.config)
        sources[case.model.canonical_model_checksum] = parts

    def analyze(model, config):
        calls["analysis_stub"] += 1
        return sources[model.canonical_model_checksum][0]

    def validate(result):
        calls["validation_stub"] += 1
        return public_api.PublicRCFiberFrameValidationReport(
            "ready",
            True,
            result.result_hash,
            True,
            True,
            2,
            1.0,
            0,
            0,
            0,
            0,
        )

    def response(result):
        calls["response_stub"] += 1
        payload = sources[result.canonical_model_checksum][1]
        return public_api.PublicRCFiberFrameResponseHistory(
            "ready", True, payload["report_hash"], json.dumps(payload)
        )

    def material(result):
        calls["material_stub"] += 1
        payload = sources[result.canonical_model_checksum][2]
        return constitutive.FiberFrameConstitutiveHistory(
            "ready", True, payload["report_hash"], json.dumps(payload)
        )

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", analyze)
    monkeypatch.setattr(public_api, "validate_public_rc_fiber_frame_result", validate)
    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", response
    )
    monkeypatch.setattr(
        public_api.PublicRCFiberFrameResult,
        "checkpoint_artifact",
        lambda self: b"stub checkpoint",
    )
    monkeypatch.setattr(
        constitutive, "inspect_public_rc_fiber_frame_constitutive_history", material
    )
    return cases, sources, calls


def _train(stub_sources, **options):
    return learning.train_fiber_frame_candidate_policy(
        stub_sources[0],
        source_revision="a" * 40,
        target_profile=PROFILE,
        **options,
    )


@pytest.fixture
def history_training(stub_sources):
    return _train(stub_sources)


def test_source_bound_seven_target_collection_preserves_raw_inputs_and_interior_peak(
    stub_sources,
):
    cases, sources, calls = stub_sources
    before = json.dumps(
        {key: [p[0].to_dict(), p[1], p[2]] for key, p in sources.items()},
        sort_keys=True,
    )
    training = _train(stub_sources)
    assert training.status == "ready", training.to_dict()["cases"]
    report, identities = learning._validated_training_report(training)
    assert len(identities) == 2
    assert calls == {
        "analysis_stub": 4,
        "validation_stub": 4,
        "response_stub": 4,
        "material_stub": 4,
    }
    assert before == json.dumps(
        {key: [p[0].to_dict(), p[1], p[2]] for key, p in sources.items()},
        sort_keys=True,
    )
    assert report["schema_version"] == learning.CANDIDATE_HISTORY_LEARNING_SCHEMA
    assert report["targets"] == list(
        learning.CANDIDATE_TERMINAL_TARGETS + learning.CANDIDATE_HISTORY_TARGETS
    )
    for sample, case in zip(report["samples"], cases, strict=True):
        width = case.model.sections[0]["width_m"]
        assert sample["targets"] == [
            0.001 / width,
            0.0001 / width,
            0.002 / width,
            0.0002 / width,
            0.0002 / width,
            0.1 / width,
            0.04 / width,
        ]
        assert len(sample["history_label_source"]["epochs"]) == 2
    assert report["cost_accounting"]["full_analysis_request_count"] == 4
    assert (
        report["claims"]["frozen_label_validation_is_independent_source_replay"]
        is False
    )


def test_holdout_labels_and_feature_ranges_do_not_enter_fit(history_training):
    samples = history_training.to_dict()["samples"]
    first = learning._fit(samples, 1e-6, 0.1, PROFILE)
    changed = deepcopy(samples)
    for sample in changed:
        if sample["split"] != "train":
            sample["features"] = [1e20] * len(learning.FEATURE_NAMES)
            sample["targets"] = [1e3, 1e3, 1e4, 1e4, 1.0, 1.0, 1.0]
            _seal(sample, "sample_hash")
    second = learning._fit(changed, 1e-6, 0.1, PROFILE)
    assert first.to_dict() == second.to_dict()


def test_opt_in_policy_round_trip_prediction_and_ood(history_training):
    policy = history_training.policy
    payload = policy.to_dict()
    decoded = learning.FiberFrameCandidatePolicy(
        **{f.name: payload[f.name] for f in fields(policy) if f.init}
    )
    assert decoded.to_dict() == payload
    assert len(policy.target_scale) == 7
    assert all(len(row) == 7 for row in policy.weights)
    prediction = policy.predict(
        _model(), public_api.PublicRCFiberFrameConfig(load_steps=2)
    )
    assert prediction.ood is False
    assert set(prediction.history_prediction) == set(learning.CANDIDATE_HISTORY_TARGETS)
    assert prediction.to_dict()["physical_result_authority"] is False
    prediction.to_dict()["history_prediction"][
        learning.CANDIDATE_HISTORY_TARGETS[0]
    ] = 999.0
    assert prediction.history_prediction[learning.CANDIDATE_HISTORY_TARGETS[0]] != 999.0
    with pytest.raises(TypeError):
        prediction.history_prediction[learning.CANDIDATE_HISTORY_TARGETS[0]] = 1.0
    for model, reason in (
        (_model(0.9), "feature_range_out_of_distribution"),
        (_model(load=-150), "analysis_context_out_of_distribution"),
    ):
        unavailable = policy.predict(
            model, public_api.PublicRCFiberFrameConfig(load_steps=2)
        )
        assert unavailable.ood is True and unavailable.reason == reason
        assert unavailable.to_dict()["history_prediction"] is None
        assert unavailable.maximum_translation_m is None


@pytest.mark.parametrize(
    "values",
    [
        [0.1, 0.1, 0.2, 0.2, 0.0, 1.1, 0.0],
        [0.1, 0.1, 0.05, 0.2, 0.0, 0.5, 0.0],
        [0.1, 0.1, 0.2, 0.05, 0.0, 0.5, 0.0],
        [0.1, 0.1, 0.2, 0.2, -0.1, 0.5, 0.0],
    ],
)
def test_inconsistent_prediction_abstains_without_clipping(history_training, values):
    policy = history_training.policy
    weights = tuple((0.0,) * 7 for _ in learning.FEATURE_NAMES) + (tuple(values),)
    invalid = replace(policy, weights=weights, target_scale=(1.0,) * 7)
    result = invalid.predict(
        _model(), public_api.PublicRCFiberFrameConfig(load_steps=2)
    )
    assert result.ood is True
    assert result.history_prediction is None
    assert result.maximum_translation_m is None


@pytest.mark.parametrize(
    "changes",
    [
        {"ood": 1},
        {"ood": "true"},
        {"reason": ""},
        {"reason": 1},
        {"maximum_translation_m": 0.0},
        {"maximum_absolute_fiber_strain": 0.0},
    ],
)
def test_new_prediction_status_and_ood_values_are_strict(changes):
    args = {
        "maximum_translation_m": None,
        "maximum_absolute_fiber_strain": None,
        "ood": True,
        "reason": "test OOD",
        "target_profile": PROFILE,
    }
    args.update(changes)
    with pytest.raises(learning.FiberFrameCandidateLearningError):
        learning.FiberFrameCandidatePrediction(**args)


@pytest.mark.parametrize(
    "profile", [None, True, "", "terminal_and_committed_material_history.v2"]
)
def test_invalid_profile_rejected_before_public_call(profile):
    with pytest.raises(
        learning.FiberFrameCandidateLearningError, match="target_profile"
    ):
        learning.train_fiber_frame_candidate_policy(
            _cases(), source_revision="a" * 40, target_profile=profile
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_scale", (1.0,) * 2),
        ("target_scale", (1.0,) * 6 + (float("inf"),)),
        ("target_scale", (1.0,) * 6 + (False,)),
        ("target_profile", LEGACY),
    ],
)
def test_policy_dimensions_and_values_are_bound_to_profile(
    history_training, field, value
):
    with pytest.raises(learning.FiberFrameCandidateLearningError):
        replace(history_training.policy, **{field: value})


def _changed_training(training, mutate):
    report = training.to_dict()
    mutate(report)
    # Rehash all local containers and policy membership to exercise semantic checks.
    for sample in report["samples"]:
        if "history_label_source" in sample:
            _seal(sample["history_label_source"], "source_hash")
        _seal(sample, "sample_hash")
    policy = replace(
        training.policy,
        training_sample_hashes=tuple(
            sorted(
                row["sample_hash"]
                for row in report["samples"]
                if row["split"] == "train"
            )
        ),
    )
    report["policy"] = policy.to_dict()
    _seal(report, "report_hash")
    return learning.FiberFrameCandidateTrainingResult(
        "ready", policy, json.dumps(report)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.pop("target_profile"),
        lambda r: r.update(target_profile=LEGACY),
        lambda r: r.update(schema_version=learning.CANDIDATE_LEARNING_SCHEMA),
        lambda r: r["targets"].reverse(),
        lambda r: r["samples"][0].pop("target_profile"),
        lambda r: r["samples"][0]["targets"].__setitem__(2, 1.0),
        lambda r: r["samples"][0]["history_label_source"]["epochs"][0][
            "targets"
        ].__setitem__(0, 1.0),
        lambda r: r["samples"][0]["history_label_source"]["epochs"][1].update(
            parent_checkpoint_state_hash=canonical_hash("wrong parent")
        ),
        lambda r: r["samples"][0]["history_label_source"]["epochs"][0].update(
            epoch=True
        ),
        lambda r: r["samples"][0]["history_label_source"]["epochs"][0].update(
            load_factor=0.25
        ),
        lambda r: r["samples"][0]["history_label_source"]["bindings"].update(
            source_result_hash=canonical_hash("detached")
        ),
        lambda r: r["samples"][0]["history_label_source"]["bindings"].update(
            checkpoint_artifact_byte_length=True
        ),
        lambda r: r["samples"][0]["history_label_source"]["epochs"].pop(),
        lambda r: r["cases"][0]["validation"].update(
            result_hash=canonical_hash("wrong public")
        ),
        lambda r: r["cases"][0].update(
            history_label_source_hash=canonical_hash("wrong source")
        ),
        lambda r: r["cases"][0].update(
            history_label_collection_wall_ns=r["cases"][0]["data_generation_wall_ns"]
            + 1
        ),
    ],
)
def test_rehashed_stored_profile_source_and_aggregate_contradictions_rejected(
    history_training, mutation
):
    changed = _changed_training(history_training, mutation)
    with pytest.raises(learning.FiberFrameCandidateLearningError):
        learning._validated_training_report(changed)


@pytest.mark.parametrize(
    "field", ["project_id", "geometry_family_id", "load_history_id"]
)
@pytest.mark.parametrize("change", ["missing", "invalid", "cross_split"])
def test_stored_declared_group_boundaries_remain_required(
    history_training, field, change
):
    def mutate(report):
        sample = report["samples"][2]
        if change == "missing":
            sample.pop(field)
        elif change == "invalid":
            sample[field] = "not a stable id"
        else:
            sample[field] = report["samples"][0][field]

    with pytest.raises(
        learning.FiberFrameCandidateLearningError, match="identity|split_leakage"
    ):
        learning._validated_training_report(_changed_training(history_training, mutate))


@pytest.mark.parametrize("key", list(learning._HISTORY_LABEL_CLAIMS))
def test_history_claim_cannot_be_removed_or_promoted(history_training, key):
    with pytest.raises(learning.FiberFrameCandidateLearningError, match="claims"):
        learning._validated_training_report(
            _changed_training(
                history_training, lambda report: report["claims"].pop(key)
            )
        )


def test_terminal_success_with_history_failure_never_becomes_partial_training(
    stub_sources, monkeypatch
):
    cases, sources, calls = stub_sources
    original = constitutive.inspect_public_rc_fiber_frame_constitutive_history
    blocked_hash = cases[1].model.canonical_model_checksum

    def fail_one(result):
        if result.canonical_model_checksum == blocked_hash:
            raise ValueError("one missing history label")
        return original(result)

    monkeypatch.setattr(
        constitutive, "inspect_public_rc_fiber_frame_constitutive_history", fail_one
    )
    training = _train(stub_sources)
    report = training.to_dict()
    assert training.status == "blocked" and training.policy is None
    assert len(report["cases"]) == 4 and len(report["samples"]) == 3
    assert calls["analysis_stub"] == 4
    assert report["cases"][1]["validation"]["contract_pass"] is True
    assert (
        report["cases"][1]["history_label_failure"]["detail"]
        == "one missing history label"
    )
    assert report["cost_accounting"]["full_analysis_request_count"] == 4
    assert report["cost_accounting"]["training_wall_ns"] is None


def test_blocked_public_verification_does_not_call_history_accessors(
    stub_sources, monkeypatch
):
    def blocked(result):
        return public_api.PublicRCFiberFrameValidationReport(
            "blocked",
            False,
            result.result_hash,
            False,
            False,
            None,
            None,
            1,
            0,
            0,
            0,
        )

    monkeypatch.setattr(public_api, "validate_public_rc_fiber_frame_result", blocked)
    training = _train(stub_sources)
    report = training.to_dict()
    assert report["cost_accounting"]["full_analysis_request_count"] == 4
    assert stub_sources[2]["response_stub"] == stub_sources[2]["material_stub"] == 0
    assert report["samples"] == []
    assert all(
        row["history_label_collection_wall_ns"] is None for row in report["cases"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("targets", [0.1, 0.1, 0.2, 0.2, 0.0, float("nan"), 0.0]),
        ("targets", [0.1, 0.1, 0.2, 0.2, True, 0.5, 0.0]),
        ("targets", [0.1, 0.1]),
        ("features", [0.0]),
        ("features", [float("inf")] * len(learning.FEATURE_NAMES)),
    ],
)
def test_fit_rejects_invalid_label_vectors_before_linalg(
    history_training, monkeypatch, field, value
):
    samples = history_training.to_dict()["samples"]
    samples[0][field] = value
    monkeypatch.setattr(
        learning.np.linalg,
        "lstsq",
        lambda *a, **k: pytest.fail("invalid labels must not reach fitting"),
    )
    with pytest.raises(learning.FiberFrameCandidateLearningError):
        learning._fit(samples, 1e-6, 0.1, PROFILE)


@pytest.mark.parametrize("stage", ["response", "material"])
def test_recovery_failure_keeps_all_requests_and_inclusive_costs(
    stub_sources, monkeypatch, stage
):
    def failed(*args):
        raise RuntimeError("synthetic source recovery failure")

    if stage == "response":
        monkeypatch.setattr(
            public_api, "recover_public_rc_fiber_frame_response_history", failed
        )
    else:
        monkeypatch.setattr(
            constitutive, "inspect_public_rc_fiber_frame_constitutive_history", failed
        )
    training = _train(stub_sources)
    report = training.to_dict()
    assert training.status == "blocked" and training.policy is None
    assert report["samples"] == []
    assert report["cost_accounting"]["full_analysis_request_count"] == 4
    assert report["cost_accounting"]["known_solver_execution_count"] == 4
    assert report["cost_accounting"]["training_wall_ns"] is None
    for row in report["cases"]:
        assert row["status"] == "blocked"
        assert row["exception_type"] == "RuntimeError"
        assert (
            0
            <= row["history_label_collection_wall_ns"]
            <= row["data_generation_wall_ns"]
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r, c: c["bindings"].update(
            source_result_hash=canonical_hash("detached")
        ),
        lambda r, c: c["states"][1].update(
            engineering_recovery_hash=canonical_hash("wrong recovery")
        ),
        lambda r, c: c["states"][1]["materials"]["concrete"]["fields"][
            "tensile_damage"
        ].update(maximum=1.1),
        lambda r, c: r["history"]["steps"][0]["node_displacements"].clear(),
    ],
)
def test_source_accessor_contradictions_block_all_labels(stub_sources, mutation):
    for _, response, material in stub_sources[1].values():
        mutation(response, material)
        _seal(response["history"], "history_hash")
        response["history_hash"] = response["history"]["history_hash"]
        _seal(response, "report_hash")
        material["bindings"].update(
            response_history_report_hash=response["report_hash"],
            engineering_history_hash=response["history_hash"],
        )
        _seal(material, "report_hash")
    training = _train(stub_sources)
    assert training.status == "blocked"
    assert training.to_dict()["samples"] == []


def test_default_and_explicit_terminal_profile_preserve_legacy_payload(
    stub_sources, monkeypatch
):
    monkeypatch.setattr(learning, "perf_counter_ns", lambda: 100)
    implicit = learning.train_fiber_frame_candidate_policy(
        stub_sources[0], source_revision="a" * 40
    )
    explicit = learning.train_fiber_frame_candidate_policy(
        stub_sources[0], source_revision="a" * 40, target_profile=LEGACY
    )
    assert implicit.to_dict() == explicit.to_dict()
    report = implicit.to_dict()
    assert report["schema_version"] == learning.CANDIDATE_LEARNING_SCHEMA
    assert "target_profile" not in report and "targets" not in report
    assert "target_profile" not in report["policy"]
    assert all("history_label_source" not in row for row in report["samples"])
    prediction = implicit.policy.predict(
        _model(), public_api.PublicRCFiberFrameConfig(load_steps=2)
    ).to_dict()
    assert "target_profile" not in prediction and "history_prediction" not in prediction
    assert stub_sources[2]["response_stub"] == stub_sources[2]["material_stub"] == 0


def test_original_frozen_terminal_policy_bytes_remain_identical():
    path = Path("/tmp/structural-candidate-process-observation.5TRGr2/training.json")
    if not path.exists():
        pytest.skip("historical local artifact not present; no replacement solver run")
    report = json.loads(path.read_bytes())
    payload = report["policy"]
    kwargs = {
        f.name: payload[f.name]
        for f in fields(learning.FiberFrameCandidatePolicy)
        if f.init and f.name in payload
    }
    policy = learning.FiberFrameCandidatePolicy(**kwargs)
    assert json.dumps(policy.to_dict(), sort_keys=True) == json.dumps(
        payload, sort_keys=True
    )
    assert policy.artifact_hash == payload["artifact_hash"]
    training = learning.FiberFrameCandidateTrainingResult(
        "ready", policy, json.dumps(report)
    )
    assert learning._validated_training_report(training)[0] == report
