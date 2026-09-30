"""Conditioned study contracts; synthetic pipeline tests carry no solver credit."""

from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.ai import (
    fiber_frame_conditioned_warm_start_learning as conditioned,
)
from structural_analysis.ai import fiber_frame_warm_start_data as data
from structural_analysis.ai import fiber_frame_warm_start_features as features
from structural_analysis.ai import fiber_frame_warm_start_learning as legacy
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_learning_study as study
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameRuntimeBenchmarkConfig,
    FiberFrameWarmStartInput,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


BASE = Path(__file__).parent / "fixtures/fiber_frame_candidate_process/base.json"
REVISION = "a" * 40
CONDITIONED_SCHEMA = "fiber-frame-learned-runtime-study.v2"
REUSE_DIRECTORY = "STRUCTURAL_FIBER_CONDITIONED_STUDY_DIRECTORY"
CASE_VALUES = (
    ("train", 3.0, 0.4, -0.8),
    ("train", 3.0, 0.46, -1.2),
    ("train", 4.0, 0.4, -1.2),
    ("train", 4.0, 0.46, -0.8),
    ("validation", 3.25, 0.415, -1.0),
    ("holdout", 3.75, 0.44, -2.0),
)


def _model(length, width, load, *, stiffness=200000.0):
    value = json.loads(BASE.read_bytes())
    value["nodes"][1]["coordinates"][0] = length
    value["sections"][0]["width_m"] = width
    value["loads"][0]["components"]["FY"] = load
    value["materials"][0]["elastic_modulus_mpa"] = stiffness
    return load_neutral_json_bytes(json.dumps(value).encode())


def _cases():
    return tuple(
        data.FiberFrameWarmStartDataCase(
            f"case-{index}",
            f"synthetic-project-{index}",
            f"synthetic-geometry-{index}",
            f"synthetic-history-{index}",
            split,
            _model(length, width, load),
            public_api.PublicRCFiberFrameConfig(load_steps=2),
        )
        for index, (split, length, width, load) in enumerate(CASE_VALUES)
    )


@pytest.fixture
def cases():
    return _cases()


@pytest.fixture(autouse=True)
def no_real_pipeline_for_contract_tests(request, monkeypatch):
    if "real_conditioned" in request.node.name:
        return

    def forbidden(*args, **kwargs):
        pytest.fail(
            "contract test cannot execute analysis, fitting, or a child process"
        )

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    monkeypatch.setattr(legacy, "train_fiber_frame_warm_start_policy", forbidden)
    monkeypatch.setattr(study, "train_fiber_frame_warm_start_policy", forbidden)
    monkeypatch.setattr(
        conditioned, "train_fiber_frame_conditioned_warm_start_policy", forbidden
    )
    monkeypatch.setattr(process.subprocess, "Popen", forbidden)


@pytest.mark.parametrize("flag", [None, 0, 1, 0.0, "true", [], {}])
def test_conditioning_flag_is_strict_before_collection_or_analysis(flag):
    with pytest.raises(data.FiberFrameWarmStartDataError, match="model_conditioning"):
        data.collect_fiber_frame_warm_start_data(
            (), source_revision=REVISION, model_conditioning=flag
        )
    with pytest.raises(ValueError, match="model_conditioning"):
        study.run_fiber_frame_learning_study(
            (), source_revision=REVISION, model_conditioning=flag
        )


def test_changed_training_context_is_rejected_before_any_analysis(cases):
    changed = data.FiberFrameWarmStartDataCase(
        "different-material",
        "different-project",
        "different-geometry",
        "different-history",
        "train",
        _model(3.5, 0.43, -1.0, stiffness=210000.0),
        cases[0].config,
    )
    with pytest.raises(
        data.FiberFrameWarmStartDataError, match="training contexts must match"
    ):
        data.collect_fiber_frame_warm_start_data(
            (cases[0], changed), source_revision=REVISION, model_conditioning=True
        )


def test_all_geometry_load_features_are_prepared_before_synthetic_analysis_boundary(
    cases, monkeypatch
):
    prepared = []
    original = features.fiber_frame_warm_start_model_features

    def observe(problem):
        value = original(problem)
        prepared.append(value)
        return value

    calls = []

    def synthetic_stop(*args, **kwargs):
        assert len(prepared) == len(cases)
        calls.append(True)
        raise RuntimeError("synthetic collection stop; no solve was requested")

    monkeypatch.setattr(features, "fiber_frame_warm_start_model_features", observe)
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", synthetic_stop)
    result = data.collect_fiber_frame_warm_start_data(
        cases, source_revision=REVISION, model_conditioning=True
    )
    payload = result.to_dict()
    assert len(calls) == len(cases)
    assert len({value.context_hash for value in prepared[:4]}) == 1
    assert len({value.feature_hash for value in prepared}) == len(cases)
    assert payload["schema_version"] == "fiber-frame-warm-start-data-collection.v2"
    assert payload["model_conditioning"] is True
    assert payload["model_feature_profile"] == features.MODEL_FEATURE_PROFILE
    assert payload["status"] == "blocked"
    assert payload["samples"] == []
    assert (
        0
        <= payload["model_conditioning_preflight_wall_ns"]
        <= payload["data_generation_wall_ns"]
    )
    assert payload["model_conditioning_preflight_is_subset"] is True


def test_validation_context_can_differ_and_unsupported_compile_keeps_diagnostics_path(
    cases,
):
    changed = data.FiberFrameWarmStartDataCase(
        "ood-material",
        "ood-project",
        "ood-geometry",
        "ood-history",
        "validation",
        _model(3.5, 0.43, -1.0, stiffness=210000.0),
        cases[0].config,
    )
    unsupported_model = cases[-1].model
    unsupported_model.unsupported_features.append({"kind": "synthetic_unsupported"})
    unsupported = data.FiberFrameWarmStartDataCase(
        "unsupported",
        "other-project",
        "other-geometry",
        "other-history",
        "holdout",
        unsupported_model,
        cases[0].config,
    )
    cached = data._preflight_model_features((cases[0], changed, unsupported))
    assert cached[cases[0].case_id].context_hash != cached[changed.case_id].context_hash
    assert cached[unsupported.case_id] is None


def test_cached_features_bind_the_source_and_are_reused_in_every_synthetic_sample(
    cases, monkeypatch
):
    case = cases[0]
    compiled, _, _ = public_api._compile(case.model)
    problem = compiled.problem
    cached = features.fiber_frame_warm_start_model_features(problem)
    checkpoints = tuple(
        SimpleNamespace(
            epoch=epoch,
            load_factor=epoch / 2,
            state_hash=canonical_hash({"synthetic_epoch": epoch}),
            global_displacements=np.zeros_like(problem.physical_coordinate_scale),
        )
        for epoch in range(3)
    )
    chain = SimpleNamespace(
        checkpoints=checkpoints, chain_hash=canonical_hash({"synthetic_chain": True})
    )
    result = SimpleNamespace(
        _problem=problem,
        _checkpoint_chain=chain,
        contract_bindings={
            "checkpoint_chain_hash": chain.chain_hash,
            "problem_contract_hash": problem.contract_hash,
        },
        canonical_model_checksum=case.model.canonical_model_checksum,
        input_checksum=case.model.input_checksum,
        result_hash=canonical_hash({"synthetic_result": True}),
    )
    other = data._preflight_model_features((cases[1],))[cases[1].case_id]
    with pytest.raises(
        data.FiberFrameWarmStartDataError, match="cached model features"
    ):
        data._case_samples(
            case,
            result,
            data._physical_model_identity(case.model),
            REVISION,
            model_features=other,
        )

    def do_not_rebuild(*args):
        pytest.fail("sample construction must use the cached preflight features")

    monkeypatch.setattr(
        features, "fiber_frame_warm_start_model_features", do_not_rebuild
    )
    samples, bindings = data._case_samples(
        case,
        result,
        data._physical_model_identity(case.model),
        REVISION,
        model_features=cached,
    )
    assert len(samples) == 2
    for sample, binding in zip(samples, bindings, strict=True):
        assert sample.runtime_input.model_features.to_dict() == cached.to_dict()
        assert binding["model_feature_hash"] == cached.feature_hash
        assert binding["model_feature_profile"] == features.MODEL_FEATURE_PROFILE


def _stub_pipeline(
    monkeypatch, *, conditioned_mode, collection_status="ready", failure=None
):
    calls = []
    collection_payload = {
        "schema_version": "fiber-frame-warm-start-data-collection.v2"
        if conditioned_mode
        else "fiber-frame-warm-start-data-collection.v1",
        "status": collection_status,
        "data_generation_wall_ns": 10,
        "blockers": ["synthetic_block"] if collection_status != "ready" else [],
        **(
            {
                "model_conditioning": True,
                "model_feature_profile": features.MODEL_FEATURE_PROFILE,
            }
            if conditioned_mode
            else {}
        ),
    }
    collection = data.FiberFrameWarmStartDataResult(
        collection_status, ("synthetic-sample",), json.dumps(collection_payload)
    )
    policy = SimpleNamespace(artifact_hash=canonical_hash({"synthetic_policy": True}))
    training = SimpleNamespace(
        policy=policy,
        training_wall_ns=3,
        to_dict=lambda: {
            "policy": {"artifact_hash": policy.artifact_hash},
            "synthetic": True,
        },
    )

    def collect(selected, **options):
        calls.append(("collection", options))
        return collection

    def train(samples, **options):
        calls.append(("training", options))
        assert samples == collection.samples
        if failure == "training":
            raise RuntimeError("synthetic training exception")
        return training

    def evaluate(selected, **options):
        calls.append(("evaluation", options))
        assert options["ai_policy"] is policy
        assert [case.case_id for case in selected] == ["case-4", "case-5"]
        if failure == "evaluation":
            raise RuntimeError("synthetic evaluation exception")
        ready = failure != "evaluation_blocked"
        return SimpleNamespace(
            measurement_contract_pass=ready, to_dict=lambda: {"cases": []}
        )

    monkeypatch.setattr(study, "collect_fiber_frame_warm_start_data", collect)
    monkeypatch.setattr(
        conditioned if conditioned_mode else study,
        "train_fiber_frame_conditioned_warm_start_policy"
        if conditioned_mode
        else "train_fiber_frame_warm_start_policy",
        train,
    )
    monkeypatch.setattr(
        study, "benchmark_public_rc_fiber_frame_runtime_suite", evaluate
    )
    return calls


def test_conditioned_study_has_one_declared_pipeline_and_unchanged_phase_accounting(
    cases, monkeypatch
):
    calls = _stub_pipeline(monkeypatch, conditioned_mode=True)
    recorder = study.FiberFrameLearningStudyPhaseRecorder()
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, model_conditioning=True, phase_runtime=recorder
    ).to_dict()
    assert [name for name, _ in calls] == ["collection", "training", "evaluation"]
    assert calls[0][1] == {"source_revision": REVISION, "model_conditioning": True}
    assert payload["schema_version"] == CONDITIONED_SCHEMA
    assert payload["model_feature_profile"] == features.MODEL_FEATURE_PROFILE
    assert payload["hyperparameters_declared_before_collection"] == {
        "ridge": 1e-6,
        "ood_margin": 0.1,
        "model_conditioning": True,
    }
    assert payload["report_hash"] == canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )
    assert all(
        row["status"] == "completed" for row in recorder.to_dict()["phases"].values()
    )


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("collection", ["blocked", "skipped", "skipped"]),
        ("training", ["completed", "exception", "skipped"]),
        ("evaluation", ["completed", "completed", "exception"]),
        ("evaluation_blocked", ["completed", "completed", "blocked"]),
    ],
)
def test_conditioned_failures_keep_phase_prefix_and_skip_downstream(
    cases, monkeypatch, failure, expected
):
    calls = _stub_pipeline(
        monkeypatch,
        conditioned_mode=True,
        collection_status="blocked" if failure == "collection" else "ready",
        failure=failure,
    )
    recorder = study.FiberFrameLearningStudyPhaseRecorder()
    payload = study.run_fiber_frame_learning_study(
        cases, source_revision=REVISION, model_conditioning=True, phase_runtime=recorder
    ).to_dict()
    assert payload["status"] == "blocked"
    assert len(calls) == {"collection": 1, "training": 2}.get(failure, 3)
    assert [row["status"] for row in recorder.to_dict()["phases"].values()] == expected


def test_default_study_bytes_equal_explicit_false_with_fixed_report_clock(
    cases, monkeypatch
):
    _stub_pipeline(monkeypatch, conditioned_mode=False)
    outputs = []
    for options in ({}, {"model_conditioning": False}):
        monkeypatch.setattr(study, "perf_counter_ns", iter(range(0, 1000, 10)).__next__)
        outputs.append(
            process._bytes(
                study.run_fiber_frame_learning_study(
                    cases, source_revision=REVISION, **options
                ).to_dict()
            )
        )
    assert outputs[0] == outputs[1]
    payload = json.loads(outputs[0])
    assert payload["schema_version"] == "fiber-frame-learned-runtime-study.v1"
    assert "model_conditioning" not in payload
    assert "model_feature_profile" not in payload
    assert (
        "model_conditioning"
        not in payload["hyperparameters_declared_before_collection"]
    )


@pytest.mark.parametrize(
    "schema,configuration",
    [
        ("v1", {"ridge": 1e-6, "ood_margin": 0.1, "model_conditioning": True}),
        ("v2", {"ridge": 1e-6, "ood_margin": 0.1}),
        *(
            ("v2", {"ridge": 1e-6, "ood_margin": 0.1, "model_conditioning": value})
            for value in (False, 1, "true", None)
        ),
        ("v2", {"ridge": True, "ood_margin": 0.1, "model_conditioning": True}),
        ("v2", {"ridge": 1e-6, "ood_margin": float("inf"), "model_conditioning": True}),
        (
            "v2",
            {
                "ridge": 1e-6,
                "ood_margin": 0.1,
                "model_conditioning": True,
                "profile": "other",
            },
        ),
        ("v3", {"ridge": 1e-6, "ood_margin": 0.1, "model_conditioning": True}),
    ],
)
def test_learning_request_version_and_flag_are_exact_before_workload(
    schema, configuration
):
    with pytest.raises(ValueError):
        process._decode_learning_configuration(
            configuration, request_schema=f"rc-fiber-learning-process-request.{schema}"
        )


def test_default_collection_bytes_equal_explicit_false_without_feature_preparation(
    cases, monkeypatch
):
    def synthetic_stop(*args, **kwargs):
        raise RuntimeError("synthetic collection stop")

    def forbidden_features(*args):
        pytest.fail("legacy collection must not construct conditioned features")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", synthetic_stop)
    monkeypatch.setattr(
        features, "fiber_frame_warm_start_model_features", forbidden_features
    )
    outputs = []
    for options in ({}, {"model_conditioning": False}):
        monkeypatch.setattr(data, "perf_counter_ns", iter(range(0, 10000, 10)).__next__)
        outputs.append(
            process._bytes(
                data.collect_fiber_frame_warm_start_data(
                    cases, source_revision=REVISION, **options
                ).to_dict()
            )
        )
    assert outputs[0] == outputs[1]
    assert (
        json.loads(outputs[0])["schema_version"]
        == "fiber-frame-warm-start-data-collection.v1"
    )


@pytest.mark.parametrize("conditioned_mode", [False, True])
def test_process_policy_decoder_roundtrips_both_typed_profiles_without_fitting(
    cases, conditioned_mode
):
    compiled, _, _ = public_api._compile(cases[0].model)
    problem = compiled.problem
    model_features = features.fiber_frame_warm_start_model_features(problem)
    dofs = problem.free_global_dofs
    size = (
        3 * len(dofs)
        + 4
        + (len(model_features.feature_names) if conditioned_mode else 0)
    )
    options = {
        "free_global_dofs": dofs,
        "feature_mean": (0.0,) * size,
        "feature_scale": (1.0,) * size,
        "feature_min": (-1.0,) * size,
        "feature_max": (1.0,) * size,
        "target_scale": (1.0,) * len(dofs),
        "weights": tuple((0.0,) * len(dofs) for _ in range(size + 1)),
        "training_sample_hashes": tuple(
            sorted(canonical_hash({"synthetic_train": index}) for index in range(2))
        ),
        "ridge": 1e-6,
        "ood_margin": 0.1,
    }
    if conditioned_mode:
        policy = conditioned.FiberFrameConditionedWarmStartPolicy(
            **options,
            context_hash=model_features.context_hash,
            model_feature_names=model_features.feature_names,
        )
    else:
        policy = legacy.FiberFrameLearnedWarmStartPolicy(
            **options,
            physical_coordinate_scale=tuple(
                float(problem.physical_coordinate_scale[dof]) for dof in dofs
            ),
        )
    raw = process._bytes(policy.to_dict())
    decoded = process._decode_policy(raw)
    assert type(decoded) is type(policy)
    assert process._bytes(decoded.to_dict()) == raw
    if conditioned_mode:
        for field in ("policy_id", "policy_version", "model_feature_profile"):
            changed = policy.to_dict()
            changed[field] = "unknown-profile"
            with pytest.raises(ValueError):
                process._decode_policy(process._bytes(changed))


def _write_request(directory, cases, *, conditioned_mode):
    rows = []
    for case in cases:
        model_name = f"{case.case_id}.json"
        (directory / model_name).write_text(
            json.dumps(case.model.to_dict()), encoding="utf-8"
        )
        rows.append(
            {
                "case_id": case.case_id,
                "project_id": case.project_id,
                "geometry_family_id": case.geometry_family_id,
                "load_history_id": case.load_history_id,
                "split": case.split,
                "model_file": model_name,
                "configuration": asdict(case.config),
            }
        )
    payload = {
        "schema_version": "rc-fiber-learning-process-request.v2"
        if conditioned_mode
        else "rc-fiber-learning-process-request.v1",
        "cases": rows,
        "benchmark_configuration": asdict(
            FiberFrameRuntimeBenchmarkConfig(repetitions=1, warmup_repetitions=0)
        ),
        "learning_configuration": {
            "ridge": 1e-6,
            "ood_margin": 0.1,
            **({"model_conditioning": True} if conditioned_mode else {}),
        },
    }
    path = directory / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("conditioned_mode", [False, True])
def test_in_process_worker_stub_preserves_raw_resource_and_phase_contract(
    cases, tmp_path, monkeypatch, conditioned_mode
):
    request = _write_request(tmp_path, cases, conditioned_mode=conditioned_mode)
    calls = []

    def synthetic_study(selected, *, phase_runtime, **options):
        calls.append(options)
        assert options.get("model_conditioning", False) is conditioned_mode
        phase_runtime._begin_study()
        for name in ("data_collection", "training_attempt", "evaluation"):
            with phase_runtime._observe(name):
                pass
        hyperparameters = {
            "ridge": options["ridge"],
            "ood_margin": options["ood_margin"],
            **({"model_conditioning": True} if conditioned_mode else {}),
        }
        payload = {
            "schema_version": CONDITIONED_SCHEMA
            if conditioned_mode
            else "fiber-frame-learned-runtime-study.v1",
            "status": "ready",
            "hyperparameters_declared_before_collection": hyperparameters,
            **(
                {
                    "model_conditioning": True,
                    "model_feature_profile": features.MODEL_FEATURE_PROFILE,
                }
                if conditioned_mode
                else {}
            ),
        }
        return study.FiberFrameLearningStudyResult("ready", payload)

    monkeypatch.setattr(study, "run_fiber_frame_learning_study", synthetic_study)
    output = tmp_path / "output"
    output.mkdir()
    assert process._worker(request, REVISION, output, process._LEARNING) == 0
    assert len(calls) == 1
    if not conditioned_mode:
        assert "model_conditioning" not in calls[0]
    raw = (output / "study.json").read_bytes()
    resource = json.loads((output / "resources.json").read_bytes())
    artifact = {"sha256": process._digest(raw), "byte_length": len(raw)}
    assert (
        process._resource_validation_failure(
            resource, os.getpid(), REVISION, artifact, process._LEARNING
        )
        is None
    )
    assert (
        resource["study_phases"]["schema_version"]
        == "fiber-frame-learning-study-phase-runtime.v1"
    )
    assert resource["study_status"] == "ready"
    changed = deepcopy(resource)
    changed["study_phases"]["phases"]["training_attempt"]["cpu_process_time_ns"] = True
    assert (
        process._resource_validation_failure(
            changed, os.getpid(), REVISION, artifact, process._LEARNING
        )
        == "worker_resources_contract_invalid"
    )


@pytest.fixture(scope="module")
def real_conditioned_study(tmp_path_factory):
    """One actual worker, or read-only reuse of its saved files after a test fix."""
    reused = os.environ.get(REUSE_DIRECTORY)
    if reused:
        output = Path(reused)
        manifest = json.loads((output / "manifest.json").read_bytes())
    else:
        directory = tmp_path_factory.mktemp("conditioned-study-inputs")
        request = _write_request(directory, _cases(), conditioned_mode=True)
        output = directory / "worker"
        print(f"{REUSE_DIRECTORY}={output}", flush=True)
        manifest = process.run_fiber_frame_learning_process(
            request,
            source_revision=REVISION,
            output_directory=output,
        )
    assert (output / "study.json").is_file(), {
        "output": str(output),
        "manifest": manifest,
    }
    raw = (output / "study.json").read_bytes()
    return (
        output,
        manifest,
        json.loads(raw),
        json.loads((output / "resources.json").read_bytes()),
        raw,
    )


def test_real_conditioned_study_preserves_frozen_training_source_and_resource_bindings(
    real_conditioned_study,
):
    output, manifest, payload, resource, raw = real_conditioned_study
    assert manifest["status"] == "ready", {"output": str(output), "manifest": manifest}
    assert payload["status"] == "ready"
    assert payload["schema_version"] == CONDITIONED_SCHEMA
    assert payload["model_conditioning"] is True
    assert payload["model_feature_profile"] == features.MODEL_FEATURE_PROFILE
    assert resource["study_status"] == "ready"
    assert resource["worker_pid"] == manifest["worker_pid"] != os.getpid()
    assert (
        resource["source_revision"]
        == payload["source_revision"]
        == manifest["source_revision"]
    )
    artifact = {"sha256": process._digest(raw), "byte_length": len(raw)}
    assert manifest["artifacts"]["study.json"] == artifact
    assert (
        process._resource_validation_failure(
            resource,
            manifest["worker_pid"],
            manifest["source_revision"],
            artifact,
            process._LEARNING,
        )
        is None
    )
    collection = payload["data_collection"]
    assert collection["schema_version"] == "fiber-frame-warm-start-data-collection.v2"
    assert collection["dataset_complete"] is True
    assert collection["case_count"] == 6
    assert collection["sample_count"] == 12
    assert collection["failed_case_count"] == 0
    assert all(row["solver_executed"] is True for row in collection["cases"])
    assert (
        0
        <= collection["model_conditioning_preflight_wall_ns"]
        <= collection["data_generation_wall_ns"]
    )
    samples = collection["samples"]
    policy = payload["training"]["policy"]
    assert (
        payload["training"]["schema_version"]
        == "fiber-frame-conditioned-warm-start-training-result.v2"
    )
    assert policy["training_sample_hashes"] == sorted(
        row["sample_hash"] for row in samples if row["split"] == "train"
    )
    assert len(policy["training_sample_hashes"]) == 8
    by_sample = {row["sample_id"]: row for row in samples}
    for binding in collection["sample_source_bindings"]:
        sample = by_sample[binding["sample_id"]]
        assert sample["schema_version"] == "fiber-frame-warm-start-sample.v2"
        model_features = sample["runtime_input"]["model_features"]
        assert (
            model_features["problem_contract_hash"]
            == sample["runtime_input"]["problem_contract_hash"]
        )
        assert binding["model_feature_hash"] == model_features["feature_hash"]
        assert binding["sample_hash"] == sample["sample_hash"]
    assert [row["case_id"] for row in payload["evaluation"]["cases"]] == [
        "case-4",
        "case-5",
    ]
    assert all(
        row["measurement_contract_pass"] for row in payload["evaluation"]["cases"]
    )
    assert payload["evaluation"]["coverage"]["fully_verified_run_count"] == 6
    assert payload["evaluation"]["coverage"]["verified_reference_episode_count"] == 2
    for case in payload["evaluation"]["cases"]:
        assert case["coverage"]["fully_verified_run_count"] == 3
        assert case["coverage"]["verified_reference_episode_count"] == 1
        for run in case["benchmark_report"]["runs"]:
            assert run["committed_step_count"] == run["load_step_count"] == 2
            assert run["authority_verification"]["contract_pass"] is True
            assert (
                run["authority_verification"]["reason_code"]
                == "full_j1_j5_recovery_passed"
            )
            assert run["reference_comparison"]["full_history_response_match"] is True
    assert all(
        row["status"] == "completed"
        for row in resource["study_phases"]["phases"].values()
    )
    for claim in (
        "independent_project_generalization_verified",
        "blind_prediction_verified",
        "generalized_speedup_claimed",
        "production_promotion_eligible",
    ):
        assert payload["claims"][claim] is False


def test_real_conditioned_saved_policy_reuses_model_features_and_marks_holdout_load_ood(
    real_conditioned_study, monkeypatch
):
    _, _, payload, _, _ = real_conditioned_study

    def forbidden(*args, **kwargs):
        pytest.fail("saved-policy checks must not rerun analysis or fitting")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    monkeypatch.setattr(
        conditioned, "train_fiber_frame_conditioned_warm_start_policy", forbidden
    )
    policy_raw = process._bytes(payload["training"]["policy"])
    policy = process._decode_policy(policy_raw)
    assert process._bytes(policy.to_dict()) == policy_raw
    samples = payload["data_collection"]["samples"]
    assert (
        len({row["runtime_input"]["model_features"]["feature_hash"] for row in samples})
        == 6
    )
    training_scales = {
        tuple(row["runtime_input"]["physical_coordinate_scale"])
        for row in samples
        if row["split"] == "train"
    }
    assert training_scales == {(1.0, 1.0, 1 / 3), (1.0, 1.0, 1 / 4)}
    for split, expected_ood in (("train", False), ("holdout", True)):
        row = next(row for row in samples if row["split"] == split)
        snapshot = deepcopy(row["runtime_input"])
        snapshot["model_features"] = (
            features.decode_fiber_frame_warm_start_model_features(
                snapshot["model_features"]
            )
        )
        runtime_input = FiberFrameWarmStartInput(**snapshot)
        proposal = policy.propose(runtime_input)
        assert proposal.ood is expected_ood
        assert all(np.isfinite(proposal.free_coordinates_m))
        if expected_ood:
            assert proposal.free_coordinates_m == tuple(
                snapshot["parent_free_coordinates_m"]
            )
