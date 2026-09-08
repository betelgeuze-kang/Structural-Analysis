"""One real frozen-policy batch; transport mutations do not rerun the solver."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
    collect_fiber_frame_warm_start_data,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    train_fiber_frame_warm_start_policy,
)
from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark import fiber_frame_strategy_process_suite as suite
from structural_analysis.benchmark.fiber_frame_runtime import (
    FIBER_FRAME_AI_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_REFERENCE_STRATEGY,
    FiberFrameRuntimeBenchmarkConfig,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40
STRATEGIES = (
    FIBER_FRAME_REFERENCE_STRATEGY,
    FIBER_FRAME_NON_AI_STRATEGY,
    FIBER_FRAME_AI_STRATEGY,
)


def _write(path, payload):
    path.write_bytes(process._bytes(payload))


def _rehash(payload, field="report_hash"):
    payload[field] = canonical_hash({k: v for k, v in payload.items() if k != field})


def _seal(worker):
    """Rebind every outer byte envelope so tests reach the inner contract."""
    report, resources, manifest = (
        worker["report"],
        worker["resources"],
        worker["manifest"],
    )
    _rehash(report)
    raw = process._bytes(report)
    resources.update(
        strategy_sha256=process._digest(raw),
        strategy_byte_length=len(raw),
        report_bytes_written=len(raw),
    )
    for name, payload in (("strategy.json", report), ("resources.json", resources)):
        raw = process._bytes(payload)
        manifest["artifacts"][name] = {
            "sha256": process._digest(raw),
            "byte_length": len(raw),
        }


def _expected_inputs(request_path):
    request = process._json(request_path.read_bytes())
    paths = [request_path, *(Path(row["model_file"]) for row in request["cases"])]
    if request["policy_file"] is not None:
        paths.append(Path(request["policy_file"]))
    return [suite._identity(path) for path in paths]


@pytest.fixture(scope="module")
def actual_suite():
    directory = Path(tempfile.mkdtemp(prefix="structural-strategy-process-"))
    config = PublicRCFiberFrameConfig(load_steps=2)
    cases = []
    model_paths = []
    example = json.loads(
        (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_bytes()
    )
    for index, split in enumerate(("train", "validation", "holdout")):
        payload = deepcopy(example)
        payload["sections"][0]["width_m"] = 0.4 + index * 0.001
        payload["loads"][0]["components"]["FY"] = -1.0
        path = directory / f"model-{split}.json"
        _write(path, payload)
        model_paths.append(path)
        cases.append(
            FiberFrameWarmStartDataCase(
                case_id=f"case-{split}",
                project_id=f"project-{index}",
                geometry_family_id=f"geometry-{index}",
                load_history_id=f"history-{index}",
                split=split,
                model=load_neutral_json_bytes(path.read_bytes(), source_path=str(path)),
                config=config,
            )
        )
    print(
        f"strategy fixture: three source-bound label analyses, artifacts={directory}",
        flush=True,
    )
    collection = collect_fiber_frame_warm_start_data(cases, source_revision=REVISION)
    _write(directory / "collection.json", collection.to_dict())
    assert collection.status == "ready", collection.to_dict()["blockers"]
    training = train_fiber_frame_warm_start_policy(collection.samples)
    _write(directory / "training.json", training.to_dict())
    _write(directory / "policy.json", training.policy.to_dict())
    request = directory / "request.json"
    _write(
        request,
        {
            "schema_version": "rc-fiber-runtime-process-request.v1",
            "cases": [
                {
                    "case_id": "case-validation",
                    "model_file": str(model_paths[1]),
                    "configuration": asdict(config),
                }
            ],
            "benchmark_configuration": asdict(
                FiberFrameRuntimeBenchmarkConfig(repetitions=1, warmup_repetitions=1)
            ),
            "policy_file": str(directory / "policy.json"),
        },
    )
    launch = process.run_fiber_frame_strategy_process

    def observed_launch(*args, **kwargs):
        manifest = launch(*args, **kwargs)
        print(
            f"strategy worker: {kwargs['output_directory'].name}, "
            f"status={manifest['status']}, pid={manifest['worker_pid']}, "
            f"artifacts={kwargs['output_directory']}",
            flush=True,
        )
        return manifest

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process, "run_fiber_frame_strategy_process", observed_launch)
        report = suite.run_fiber_frame_strategy_process_suite(
            request, source_revision=REVISION, output_directory=directory / "suite"
        )
    print(
        f"strategy suite status={report['status']}, "
        f"errors={[row['validation_errors'] for row in report['workers']]}",
        flush=True,
    )
    assert report["status"] == "ready", report["workers"]
    return {
        "directory": directory,
        "request": request,
        "report": report,
        "collection": collection.to_dict(),
        "training": training.to_dict(),
    }


def _worker(actual_suite, index=0):
    return deepcopy(actual_suite["report"]["workers"][index])


def _validate(actual_suite, worker, index=0):
    declaration = actual_suite["report"]["declaration"]
    strategy = STRATEGIES[index]
    expected = {
        "source_revision": REVISION,
        "strategy": strategy,
        "cases_in_execution_order": declaration["cases_in_execution_order"],
        "benchmark_configuration": declaration["benchmark_configuration"],
        "policy": declaration["policy"]
        if strategy == FIBER_FRAME_AI_STRATEGY
        else None,
    }
    request = (
        actual_suite["directory"] / "suite" / "inputs" / f"request-{index:03d}.json"
    )
    return suite._validate_worker_payload(
        worker["report"],
        worker["resources"],
        worker["manifest"],
        strategy=strategy,
        source_revision=REVISION,
        expected_declaration=expected,
        expected_inputs=_expected_inputs(request),
        expected_runtime_bindings=declaration["compiled_input_bindings"],
    )


def test_real_strategy_workers_bind_frozen_training_inputs_full_history_and_resources(
    actual_suite,
):
    report = actual_suite["report"]
    assert report["schema_version"] == "rc-fiber-strategy-process-suite.v1"
    assert report["measurement_contract_pass"] is True
    assert report["suite_identity_hash"] == canonical_hash(report["declaration"])
    assert report["report_hash"] == canonical_hash(
        {k: v for k, v in report.items() if k != "report_hash"}
    )
    assert (
        process._json((actual_suite["directory"] / "suite/report.json").read_bytes())
        == report
    )
    coverage = report["coverage"]
    assert coverage["declared_case_count"] == 1
    assert coverage["declared_strategy_count"] == 3
    assert (
        coverage["expected_measured_run_count"]
        == coverage["verified_measured_run_count"]
        == 3
    )
    assert coverage["expected_warmup_run_count"] == 3
    assert coverage["expected_reference_episode_count"] == 1
    assert coverage["ready_worker_count"] == 3
    assert coverage["frozen_inputs_unchanged"] is True
    assert len({row["manifest"]["worker_pid"] for row in report["workers"]}) == 3
    train_hashes = sorted(
        row["sample_hash"]
        for row in actual_suite["collection"]["samples"]
        if row["split"] == "train"
    )
    assert tuple(actual_suite["training"]["policy"]["training_sample_hashes"]) == tuple(
        train_hashes
    )
    assert actual_suite["collection"]["sample_count"] == 6
    for row in report["input_snapshots"]["frozen_inputs"]:
        assert Path(row["path"]).read_bytes() == Path(row["original_path"]).read_bytes()
    for index, worker in enumerate(report["workers"]):
        assert _validate(actual_suite, worker, index) == []
        assert worker["resources_validated"] is True
        manifest, resources, child = (
            worker["manifest"],
            worker["resources"],
            worker["report"],
        )
        assert resources["worker_pid"] == manifest["worker_pid"] != os.getpid()
        assert (
            resources["strategy"]
            == child["declaration"]["strategy"]
            == STRATEGIES[index]
        )
        assert (
            0
            < resources["workload_cpu_process_time_ns"]
            <= resources["cpu_process_time_ns"]
        )
        assert 0 < resources["workload_wall_ns"] <= manifest["launch_to_exit_wall_ns"]
        assert (
            resources["per_strategy_peak_memory_bytes"]
            == resources["peak_memory_bytes"]
        )
        assert (
            resources["per_strategy_peak_memory_reason"] == process.STRATEGY_PEAK_SCOPE
        )
        if sys.platform == "linux":
            assert resources["peak_memory_bytes"] > 0
        else:
            assert resources["peak_memory_bytes"] is None
        inputs = resources["inputs"]
        assert resources["input_bytes_read"] == sum(
            row["byte_length"] for row in inputs
        )
        assert resources["input_read_wall_ns"] == sum(
            row["read_wall_ns"] for row in inputs
        )
        for row in inputs:
            raw = Path(row["path"]).read_bytes()
            assert row["sha256"] == process._digest(raw)
            assert row["byte_length"] == len(raw)
        assert child["policy_execution_contract"]["training_executed"] is False
        assert child["policy_execution_contract"]["policy_reset_between_runs"] is False
        assert child["policy_execution_contract"][
            "same_instance_reused_across_cases_warmups_repetitions"
        ] is (index == 2)
        case = child["cases"][0]
        assert len(case["warmups"]) == len(case["runs"]) == 1
        assert case["warmups"][0]["warmup_index"] == case["runs"][0]["repetition"] == 0
        assert (
            case["warmups"][0]["authority_verification"]["reason_code"]
            == "warmup_execution_only"
        )
        run = case["runs"][0]
        assert run["authority_verification"]["contract_pass"] is True
        snapshot = run["comparison_snapshot"]
        assert len(snapshot["checkpoints"]) == 3
        assert len(snapshot["trial_assemblies"]) == 2
        assert [row["load_factor"] for row in snapshot["checkpoints"]] == [
            0.0,
            0.5,
            1.0,
        ]
        assert len(case["reference_solver_episode_verification"]["runs"]) == (
            1 if index == 0 else 0
        )
    assert all(
        row["reference_comparison"]["full_history_response_match"]
        for row in report["cases"][0]["runs"]
    )
    accounting = report["resource_accounting"]
    assert (
        accounting["training_execution_count"]
        == accounting["data_collection_execution_count"]
        == 0
    )
    assert accounting["observed_worker_resource_count"] == 3
    assert accounting["worker_cpu_process_time_ns"] == sum(
        row["resources"]["cpu_process_time_ns"] for row in report["workers"]
    )
    assert accounting["combined_peak_memory_bytes"] is None
    assert accounting["historical_training_cost_ns"] is None
    assert report["claims"]["independent_validation"] is False
    assert report["claims"]["equal_scope_peak_memory_advantage_claimed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "source",
        "strategy",
        "policy",
        "runtime-binding",
        "missing-run",
        "duplicate-run",
        "boolean-repetition",
        "missing-warmup",
        "duplicate-warmup",
        "missing-episode",
        "missing-snapshot",
        "early-checkpoint",
        "early-trial",
        "terminal-hash",
        "scope",
        "unknown-scope",
        "policy-reset",
        "training-claimed",
        "negative-cpu",
        "negative-wall",
        "missing-selected-solve-wall",
        "missing-assembly-wall",
        "missing-cpu",
        "cpu-subtotal",
        "input-hash",
        "input-order",
        "input-byte-count",
        "resource-scope",
        "unknown-resource",
        "shared-parent-pid",
        "coverage-count",
    ),
)
def test_rehashed_worker_contract_tampering_is_rejected(actual_suite, mutation):
    worker = _worker(actual_suite)
    report, resources = worker["report"], worker["resources"]
    case = report["cases"][0]
    run = case["runs"][0]
    if mutation == "source":
        report["declaration"]["source_revision"] = "b" * 40
        report["strategy_identity_hash"] = canonical_hash(report["declaration"])
    elif mutation == "strategy":
        resources["strategy"] = FIBER_FRAME_AI_STRATEGY
    elif mutation == "policy":
        report["declaration"]["policy"] = {"policy_artifact_hash": "sha256:" + "f" * 64}
    elif mutation == "runtime-binding":
        case["runtime_bindings"]["problem_contract_hash"] = "sha256:" + "f" * 64
    elif mutation in ("missing-run", "duplicate-run"):
        case["runs"] = [] if mutation == "missing-run" else [run, deepcopy(run)]
    elif mutation == "boolean-repetition":
        run["repetition"] = False
    elif mutation in ("missing-warmup", "duplicate-warmup"):
        case["warmups"] = [] if mutation == "missing-warmup" else case["warmups"] * 2
    elif mutation == "missing-episode":
        case["reference_solver_episode_verification"]["runs"] = []
    elif mutation == "missing-snapshot":
        run["comparison_snapshot"] = None
    elif mutation in ("early-checkpoint", "early-trial"):
        snapshot = run["comparison_snapshot"]
        snapshot[
            "checkpoints" if mutation == "early-checkpoint" else "trial_assemblies"
        ].pop(0)
        _rehash(snapshot, "snapshot_hash")
    elif mutation == "terminal-hash":
        run["terminal_checkpoint_state_hash"] = "sha256:" + "f" * 64
    elif mutation == "scope":
        report["measurement_scope"]["warmups"] = "not_executed"
    elif mutation == "unknown-scope":
        report["measurement_scope"]["unbound"] = True
    elif mutation == "policy-reset":
        report["policy_execution_contract"]["policy_reset_between_runs"] = True
    elif mutation == "training-claimed":
        report["policy_execution_contract"]["training_executed"] = True
    elif mutation == "negative-cpu":
        run["execution_cpu_process_time_ns"] = -1
    elif mutation == "negative-wall":
        run["wall_ns"] = -1
    elif mutation == "missing-selected-solve-wall":
        run.pop("selected_solve_wall_ns")
    elif mutation == "missing-assembly-wall":
        run["attempted_newton_runtime"].pop("assemble_wall_ns")
    elif mutation == "missing-cpu":
        run.pop("execution_cpu_process_time_ns")
    elif mutation == "cpu-subtotal":
        run["execution_cpu_process_time_ns"] = (
            run["execution_and_authority_verification_cpu_process_time_ns"] + 1
        )
    elif mutation == "input-hash":
        resources["inputs"][1]["sha256"] = "sha256:" + "f" * 64
    elif mutation == "input-order":
        resources["inputs"].reverse()
    elif mutation == "input-byte-count":
        resources["input_bytes_read"] += 1
    elif mutation == "resource-scope":
        resources["workload_scope"] = "selected_successful_runs_only"
    elif mutation == "unknown-resource":
        resources["extra"] = 0
    elif mutation == "shared-parent-pid":
        resources["worker_pid"] = worker["manifest"]["worker_pid"] = worker["manifest"][
            "parent_pid"
        ]
    elif mutation == "coverage-count":
        report["coverage"]["expected_measured_run_count"] += 1
    _seal(worker)
    assert _validate(actual_suite, worker), mutation


@pytest.mark.parametrize("value", (True, 1.0))
def test_strategy_peak_requires_exact_integer_type_even_when_numerically_equal(
    actual_suite, value
):
    worker = _worker(actual_suite)
    resources = worker["resources"]
    resources["peak_memory_bytes"] = 1
    resources["per_strategy_peak_memory_bytes"] = value
    _seal(worker)
    assert (
        process._resource_validation_failure(
            resources,
            worker["manifest"]["worker_pid"],
            REVISION,
            worker["manifest"]["artifacts"]["strategy.json"],
            process._STRATEGY,
        )
        == "worker_resources_contract_invalid"
    )


def test_frozen_learned_policy_hash_cannot_be_replaced_after_rehash(actual_suite):
    worker = _worker(actual_suite, 2)
    worker["report"]["declaration"]["policy"]["policy_artifact_hash"] = (
        "sha256:" + "f" * 64
    )
    worker["report"]["strategy_identity_hash"] = canonical_hash(
        worker["report"]["declaration"]
    )
    _seal(worker)
    assert "worker_report_identity_or_scope_mismatch" in _validate(
        actual_suite, worker, 2
    )


@pytest.mark.parametrize("phase", ("newton", "terminal", "guard"))
def test_material_subtotals_cannot_exceed_their_enclosing_interval(actual_suite, phase):
    index = 1 if phase == "guard" else 0
    worker = _worker(actual_suite, index)
    run = worker["report"]["cases"][0]["runs"][0]
    if phase == "newton":
        container = run["attempted_newton_runtime"]
        material = container["material_trial"]
        enclosing = container["assemble_wall_ns"]
    elif phase == "terminal":
        container = run["attempted_stateful_runtime"]
        material = container["terminal_material_trial"]
        enclosing = container["terminal_trial_assembly_wall_ns"]
    else:
        container = run["steps"][-1]
        material = container["guard_material_trial"]
        enclosing = container["guard_wall_ns"]
    assert material["coverage_complete"] is True
    delta = enclosing + 1
    material["wall_ns"] += delta
    material["materials"]["steel"]["wall_ns"] += delta
    assert material["wall_ns"] == sum(
        row["wall_ns"] for row in material["materials"].values()
    )
    _seal(worker)
    assert "worker_run_cost_contract_invalid" in _validate(actual_suite, worker, index)


def test_complete_material_exception_count_cannot_exceed_call_count(actual_suite):
    worker = _worker(actual_suite)
    material = worker["report"]["cases"][0]["runs"][0]["attempted_newton_runtime"][
        "material_trial"
    ]
    assert material["coverage_complete"] is True
    material["materials"]["steel"]["exception_count"] = material["call_count"] + 1
    material["exception_count"] = sum(
        row["exception_count"] for row in material["materials"].values()
    )
    _seal(worker)
    assert "worker_run_cost_contract_invalid" in _validate(actual_suite, worker)


@pytest.mark.parametrize("metadata", ("missing", "null", "incomplete"))
def test_unavailable_material_metadata_does_not_become_complete_measurement(
    actual_suite, metadata
):
    worker = _worker(actual_suite)
    run = worker["report"]["cases"][0]["runs"][0]
    container = run["attempted_newton_runtime"]
    if metadata == "missing":
        container.pop("material_trial")
    elif metadata == "null":
        container["material_trial"] = None
    else:
        container["material_trial"]["coverage_complete"] = False
        container["material_trial"]["unavailable_reasons"] = [
            "test_incomplete_metadata"
        ]
    _seal(worker)
    assert _validate(actual_suite, worker) == []
    material = suite._aggregate_material_trial([container.get("material_trial")])
    assert material["coverage_complete"] is False
    assert material["unavailable_reasons"]


def test_rehashed_typed_checkpoint_must_retain_its_actual_parent_connection(
    actual_suite,
):
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_checkpoint_io as codec,
    )
    from structural_analysis.benchmark.fiber_frame_runtime import (
        _validate_comparison_checkpoint,
    )

    worker = _worker(actual_suite)
    run = worker["report"]["cases"][0]["runs"][0]
    snapshot = run["comparison_snapshot"]
    last = snapshot["checkpoints"][-1]
    source = Path(worker["resources"]["inputs"][1]["path"])
    model = load_neutral_json_bytes(source.read_bytes(), source_path=str(source))
    compiled, _, _ = suite.public_api._compile(model)
    payload = {
        key: value for key, value in last.items() if key != "canonical_bytes_hex"
    }
    checkpoint = codec.load_stateful_fiber_frame2d_checkpoint_bytes(
        codec._artifact_json_bytes(payload), compiled.problem
    )
    changed = replace(checkpoint, parent_state_hash="sha256:" + "f" * 64, state_hash="")
    snapshot["checkpoints"][-1] = {
        **changed.to_dict(),
        "canonical_bytes_hex": changed.canonical_bytes().hex(),
    }
    _validate_comparison_checkpoint(snapshot["checkpoints"][-1])
    assert changed.parent_state_hash != snapshot["checkpoints"][-2]["state_hash"]
    run["terminal_checkpoint_state_hash"] = changed.state_hash
    _rehash(snapshot, "snapshot_hash")
    _seal(worker)
    assert "worker_snapshot_execution_binding_mismatch" in _validate(
        actual_suite, worker
    )


@pytest.mark.parametrize("scope", ("worker-launch", "warmup-execution"))
def test_rehashed_times_cannot_exceed_outer_scope(actual_suite, scope):
    worker = _worker(actual_suite)
    if scope == "worker-launch":
        worker["resources"]["worker_observed_wall_ns"] = (
            worker["manifest"]["launch_to_exit_wall_ns"] + 1
        )
    else:
        warmup = worker["report"]["cases"][0]["warmups"][0]
        warmup["wall_ns"] = warmup["execution_call_wall_ns"] + 1
    _seal(worker)
    expected_error = (
        "worker_resource_accounting_mismatch"
        if scope == "worker-launch"
        else "worker_warmup_contract_mismatch"
    )
    assert expected_error in _validate(actual_suite, worker)


@pytest.mark.parametrize("missing", ("report", "resources", "manifest"))
def test_missing_worker_metadata_never_receives_complete_scope_credit(
    actual_suite, missing
):
    worker = _worker(actual_suite)
    worker[missing] = None
    assert _validate(actual_suite, worker) == ["worker_payload_missing"]


@pytest.mark.parametrize("artifact", ("report", "resources"))
def test_worker_payload_bytes_are_checked_before_contract_credit(
    actual_suite, artifact
):
    worker = _worker(actual_suite)
    if artifact == "report":
        worker["report"]["extra_unbound_payload"] = True
    else:
        worker["resources"]["input_read_wall_ns"] += 1
    # Deliberately retain the previous raw artifact envelope.
    assert "worker_payload_byte_binding_mismatch" in _validate(actual_suite, worker)


def test_evaluation_only_worker_does_not_collect_or_train_again(
    actual_suite, tmp_path, monkeypatch
):
    from structural_analysis.ai import fiber_frame_warm_start_data as data
    from structural_analysis.ai import fiber_frame_warm_start_learning as learning
    from structural_analysis.benchmark import fiber_frame_learning_study as study
    from structural_analysis.benchmark import fiber_frame_runtime_strategy as strategy

    def unexpected(*args, **kwargs):
        pytest.fail("frozen-policy resource worker must not collect or train")

    for module, name in (
        (data, "collect_fiber_frame_warm_start_data"),
        (learning, "train_fiber_frame_warm_start_policy"),
        (study, "run_fiber_frame_learning_study"),
    ):
        monkeypatch.setattr(module, name, unexpected)
    calls = []
    expected = _worker(actual_suite, 2)["report"]

    def execute(cases, **kwargs):
        calls.append(kwargs)
        assert len(cases) == 1
        assert kwargs["strategy"] == FIBER_FRAME_AI_STRATEGY
        assert (
            kwargs["ai_policy"].artifact_hash
            == actual_suite["training"]["policy"]["artifact_hash"]
        )
        return deepcopy(expected)

    monkeypatch.setattr(
        strategy, "benchmark_public_rc_fiber_frame_runtime_strategy", execute
    )
    request = actual_suite["directory"] / "suite/inputs/request-002.json"
    # Direct worker with a contract stub: no fresh-process or timing claim here.
    assert process._worker(request, REVISION, tmp_path, process._STRATEGY) == 0
    assert len(calls) == 1


def _fake_launcher(actual_suite, mode="ready"):
    calls = []

    def launch(request_path, *, source_revision, output_directory, timeout_seconds):
        declaration = process._json(request_path.read_bytes())
        index = STRATEGIES.index(declaration["strategy"])
        calls.append(declaration["strategy"])
        output_directory.mkdir()
        worker = _worker(actual_suite, index)
        resources, manifest, report = (
            worker["resources"],
            worker["manifest"],
            worker["report"],
        )
        pid = 91_000 if mode == "duplicate-pid" else 91_000 + index
        resources["worker_pid"] = manifest["worker_pid"] = pid
        manifest["parent_pid"] = os.getpid()
        resources["inputs"] = [
            {**row, "read_wall_ns": 1} for row in _expected_inputs(request_path)
        ]
        resources["input_bytes_read"] = sum(
            row["byte_length"] for row in resources["inputs"]
        )
        resources["input_read_wall_ns"] = len(resources["inputs"])
        if mode == "blocked" and index == 1:
            report.update(status="blocked", measurement_contract_pass=False)
            report["cases"][0].update(status="blocked", measurement_contract_pass=False)
            report["cases"][0]["runs"][0].update(status="blocked", contract_pass=False)
            resources.update(status="blocked", measurement_contract_pass=False)
            manifest.update(status="blocked", worker_exit_code=2)
        _seal(worker)
        if mode == "timeout" and index == 1:
            manifest.update(
                status="timeout",
                worker_exit_code=-15,
                worker_measurements_available=False,
                worker_resource_validation_failure="worker_timeout",
            )
            for name, raw in (
                ("strategy.json", b'{"partial":'),
                ("resources.json", b'{"cpu":'),
            ):
                (output_directory / name).write_bytes(raw)
                manifest["artifacts"][name] = {
                    "sha256": process._digest(raw),
                    "byte_length": len(raw),
                }
        else:
            _write(output_directory / "strategy.json", report)
            _write(output_directory / "resources.json", resources)
        _write(output_directory / "manifest.json", manifest)
        if mode == "changed-frozen-input" and index == 0:
            Path(declaration["cases"][0]["model_file"]).write_bytes(
                b"changed after worker"
            )
        return manifest

    return launch, calls


@pytest.mark.parametrize(
    "mode", ("ready", "blocked", "timeout", "duplicate-pid", "changed-frozen-input")
)
def test_parent_retains_failed_slots_partial_costs_and_frozen_snapshot_identity(
    actual_suite, tmp_path, monkeypatch, mode
):
    launch, calls = _fake_launcher(actual_suite, mode)
    monkeypatch.setattr(process, "run_fiber_frame_strategy_process", launch)
    report = suite.run_fiber_frame_strategy_process_suite(
        actual_suite["request"],
        source_revision=REVISION,
        output_directory=tmp_path / "suite",
    )
    assert report["coverage"]["expected_measured_run_count"] == 3
    assert report["coverage"]["expected_warmup_run_count"] == 3
    assert len(report["workers"]) == 3
    accounting = report["resource_accounting"]
    if mode == "ready":
        assert report["status"] == "ready", report["workers"]
        assert (
            report["suite_identity_hash"]
            == actual_suite["report"]["suite_identity_hash"]
        )
        assert report["input_snapshots"] != actual_suite["report"]["input_snapshots"]
    else:
        assert report["status"] == "blocked"
    assert calls == list(
        STRATEGIES[:1] if mode == "changed-frozen-input" else STRATEGIES
    )
    if mode == "blocked":
        assert accounting["observed_worker_resource_count"] == 3
        assert report["workers"][1]["resources_validated"] is True
        assert report["workers"][1]["status"] == "blocked"
        assert accounting["observed_worker_cpu_process_time_ns"] == sum(
            row["resources"]["cpu_process_time_ns"] for row in report["workers"]
        )
    elif mode == "timeout":
        assert accounting["observed_worker_resource_count"] == 2
        assert accounting["worker_cpu_process_time_ns"] is None
        assert report["workers"][2]["status"] == "ready"
        directory = Path(report["workers"][1]["output_directory"])
        assert (directory / "resources.json").read_bytes() == b'{"cpu":'
    elif mode == "duplicate-pid":
        assert (
            "worker_pid_reused_across_strategies"
            in report["workers"][1]["validation_errors"]
        )
        assert accounting["observed_worker_resource_count"] == 1
    elif mode == "changed-frozen-input":
        assert report["coverage"]["frozen_inputs_unchanged"] is False
        assert accounting["observed_worker_resource_count"] == 0
        assert report["workers"][1]["manifest"]["status"] == "not_run"


def test_missing_workers_do_not_create_vacuously_verified_empty_summaries(actual_suite):
    workers = deepcopy(actual_suite["report"]["workers"])
    for worker in workers:
        worker["status"] = "blocked"
    declaration = actual_suite["report"]["declaration"]
    cases, _, _ = suite._compare_workers(
        workers,
        declaration["cases_in_execution_order"],
        declaration["benchmark_configuration"],
    )
    assert cases[0]["runs"] == []
    assert cases[0]["measurement_contract_pass"] is False
    for summary in cases[0]["summaries"].values():
        assert summary["summary_available"] is False
        assert summary["all_full_history_matches_reference"] is False
        assert summary["all_full_j1_j5_recovery_passed"] is False


def test_rehashed_early_reference_trial_tamper_fails_full_history_comparison(
    actual_suite,
):
    workers = deepcopy(actual_suite["report"]["workers"])
    snapshot = workers[0]["report"]["cases"][0]["runs"][0]["comparison_snapshot"]
    snapshot["trial_assemblies"][0]["residual_kn"][0] += 1.0
    _rehash(snapshot, "snapshot_hash")
    _seal(workers[0])
    declaration = actual_suite["report"]["declaration"]
    cases, _, _ = suite._compare_workers(
        workers,
        declaration["cases_in_execution_order"],
        declaration["benchmark_configuration"],
    )
    assert cases[0]["measurement_contract_pass"] is False
    assert all(
        row["reference_comparison"]["full_history_response_match"] is False
        for row in cases[0]["runs"]
        if row["strategy"] != FIBER_FRAME_REFERENCE_STRATEGY
    )


def test_strategy_timeout_reaps_worker_and_preserves_unparsed_partial_bytes(
    tmp_path, monkeypatch
):
    output = tmp_path / "output"
    events = []

    class Worker:
        pid = 92_001

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if len(events) == 1:
                raise subprocess.TimeoutExpired("worker", timeout)
            return -15

        def terminate(self):
            events.append(("terminate", None))

    def launch(*args, **kwargs):
        (output / "resources.json").write_bytes(b'{"cpu":')
        (output / "strategy.json").write_bytes(b'{"partial":')
        return Worker()

    monkeypatch.setattr(process.subprocess, "Popen", launch)
    manifest = process.run_fiber_frame_strategy_process(
        tmp_path / "request.json",
        source_revision=REVISION,
        output_directory=output,
        timeout_seconds=0.01,
    )
    assert manifest["status"] == "timeout"
    assert manifest["worker_measurements_available"] is False
    assert manifest["worker_resource_validation_failure"] == "worker_timeout"
    assert [event[0] for event in events] == ["wait", "terminate", "wait"]
    assert (output / "resources.json").read_bytes() == b'{"cpu":'
    assert manifest["artifacts"]["resources.json"]["sha256"] == process._digest(
        b'{"cpu":'
    )


def test_unknown_request_fields_fail_before_worker_launch(tmp_path, monkeypatch):
    request = tmp_path / "request.json"
    _write(
        request,
        {
            "schema_version": "rc-fiber-runtime-process-request.v1",
            "cases": [],
            "benchmark_configuration": {},
            "policy_file": None,
            "unbound": True,
        },
    )

    def unexpected(*args, **kwargs):
        pytest.fail("invalid frozen request must not launch a worker")

    monkeypatch.setattr(process, "run_fiber_frame_strategy_process", unexpected)
    with pytest.raises(ValueError):
        suite.run_fiber_frame_strategy_process_suite(
            request, source_revision=REVISION, output_directory=tmp_path / "suite"
        )
