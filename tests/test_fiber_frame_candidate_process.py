"""One actual 21-request batch; saved worker bytes serve the negative probes.

The frozen training artifact has four historical label requests. This fixture
does not repeat them or claim a new training/performance observation. Set
STRUCTURAL_CANDIDATE_PROCESS_TEST_FIXTURE to a preserved fixture directory only
for an explicitly requested artifact-revalidation run without new analysis.
"""

from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from structural_analysis.api import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_candidate_process as candidate
from structural_analysis.benchmark import fiber_frame_runtime_process as process
from structural_analysis.benchmark.fiber_frame_design import (
    FiberFrameDesignCandidate,
    FiberFrameMaterialPrices,
    FiberFrameSectionChange,
    FiberFrameTerminalLimits,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/fiber_frame_candidate_process"
REVISION = "a" * 40


def request_payload():
    training = json.loads((FIXTURES / "training.json").read_bytes())
    labels = [row["targets"] for row in training["samples"] if row["split"] == "train"]
    limits = FiberFrameTerminalLimits(
        *(sum(row[index] for row in labels) / len(labels) for index in (0, 1))
    )
    payload = {
        "schema_version": "rc-fiber-candidate-process-suite-request.v1",
        "cases": [
            {
                "case_id": "pool-a",
                "model_file": str(FIXTURES / "base.json"),
                "training_file": str(FIXTURES / "training.json"),
                "candidates": [
                    asdict(
                        FiberFrameDesignCandidate(
                            name, (FiberFrameSectionChange("RC1", width_m=width),)
                        )
                    )
                    for name, width in (("narrow", 0.36), ("near-limit", 0.395))
                ],
                "configuration": asdict(PublicRCFiberFrameConfig(load_steps=2)),
                "prices": asdict(
                    FiberFrameMaterialPrices(
                        100.0,
                        1.0,
                        "KRW",
                        "2026-09-08",
                        "Synthetic integration prices; not a quote",
                    )
                ),
                "terminal_limits": asdict(limits),
                "history_limits": None,
                "full_analysis_budget": 2,
                "exploration_slots": 1,
            }
        ],
        "repetitions": 2,
        "warmups": 1,
        "oracle_audit": True,
    }
    return process._json(process._bytes(payload))


def _write(path, payload):
    path.write_bytes(process._bytes(payload))


def _rehash(payload, field="report_hash"):
    payload[field] = canonical_hash({k: v for k, v in payload.items() if k != field})


def _seal(worker):
    """Bind changed inner values through every raw resource/manifest envelope."""
    report, resources, manifest = (
        worker["report"],
        worker["resources"],
        worker["manifest"],
    )
    _rehash(report)
    raw = process._bytes(report)
    resources.update(
        search_sha256=process._digest(raw),
        search_byte_length=len(raw),
        report_bytes_written=len(raw),
    )
    for name, payload in (("search.json", report), ("resources.json", resources)):
        raw = process._bytes(payload)
        manifest["artifacts"][name] = {
            "sha256": process._digest(raw),
            "byte_length": len(raw),
        }


def _load_fixture(directory):
    report = process._json((directory / "suite/suite.json").read_bytes())
    workers = []
    for manifest_path in sorted((directory / "suite/workers").glob("*/manifest.json")):
        worker_dir = manifest_path.parent
        workers.append(
            {
                "directory": worker_dir,
                "report": process._json((worker_dir / "search.json").read_bytes()),
                "resources": process._json(
                    (worker_dir / "resources.json").read_bytes()
                ),
                "manifest": process._json(manifest_path.read_bytes()),
            }
        )
    return {
        "directory": directory,
        "request": directory / "request.json",
        "report": report,
        "workers": workers,
        "frozen": process._json(
            (directory / "suite/inputs/declaration.json").read_bytes()
        ),
    }


def _validate_saved_worker(actual_suite, tmp_path, worker):
    """Replay parent validation over a detached copy; never launch a process."""
    output = tmp_path / "worker"
    output.mkdir()
    for name, key in (
        ("search.json", "report"),
        ("resources.json", "resources"),
        ("manifest.json", "manifest"),
    ):
        _write(output / name, worker[key])
    request_path = Path(worker["resources"]["inputs"][0]["path"])
    return candidate._validate_worker(
        output,
        request_path,
        actual_suite["frozen"]["cases"][0]["expectations"],
        source_revision=REVISION,
    )


@pytest.fixture(scope="module")
def actual_suite():
    preserved = os.environ.get("STRUCTURAL_CANDIDATE_PROCESS_TEST_FIXTURE")
    if preserved:
        directory = Path(preserved)
        assert (
            process._json((directory / "request.json").read_bytes())
            == request_payload()
        )
        print(
            f"revalidating preserved candidate fixture; new requests=0; {directory}",
            flush=True,
        )
        return _load_fixture(directory)
    directory = Path(tempfile.mkdtemp(prefix="structural-candidate-process-"))
    request = directory / "request.json"
    _write(request, request_payload())
    print(
        f"candidate process fixture: 21 new full-reference requests, "
        f"4 historical labels reused, no training; artifacts={directory}",
        flush=True,
    )
    launch = process._run_fiber_frame_process

    def observed_launch(*args, **kwargs):
        manifest = launch(*args, **kwargs)
        print(
            f"candidate worker: {kwargs['output_directory'].name}, "
            f"status={manifest['status']}, pid={manifest['worker_pid']}",
            flush=True,
        )
        return manifest

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process, "_run_fiber_frame_process", observed_launch)
        report = candidate.run_fiber_frame_candidate_process_suite(
            request, source_revision=REVISION, output_directory=directory / "suite"
        )
    print(
        f"candidate suite status={report['status']}; artifacts={directory}", flush=True
    )
    assert report["status"] == "ready", report
    return _load_fixture(directory)


def test_portable_actual_training_keeps_original_bytes_and_historical_scope():
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    for name, artifact in provenance["artifacts"].items():
        raw = (FIXTURES / name).read_bytes()
        assert process._digest(raw) == artifact["sha256"]
        assert len(raw) == artifact["byte_length"]
        assert artifact["preserved_exact_bytes"] is True
    training = json.loads((FIXTURES / "training.json").read_bytes())
    assert training["report_hash"] == provenance["training_report_hash"]
    assert training["policy"]["artifact_hash"] == provenance["policy_artifact_hash"]
    assert training["source_revision"] == provenance["source_revision"] != REVISION
    assert [row["split"] for row in training["samples"]] == [
        "train",
        "train",
        "validation",
        "holdout",
    ]
    assert provenance["historical_training_analysis_request_count"] == 4
    assert provenance["historical_known_solver_execution_count"] == 4
    assert provenance["historical_unknown_solver_execution_count"] == 0
    for flag in (
        "training_reexecuted_during_fixture_copy",
        "independent_physical_validation_claimed",
        "independent_project_generalization_verified",
        "generalized_speedup_claimed",
        "production_promotion_eligible",
    ):
        assert provenance[flag] is False


def test_actual_workers_have_distinct_resource_scopes_and_bound_raw_artifacts(
    actual_suite,
):
    workers = actual_suite["workers"]
    assert len(workers) == 9
    assert len({row["manifest"]["worker_pid"] for row in workers}) == 9
    strategies = [row["resources"]["strategy"] for row in workers]
    assert strategies == [
        "deterministic",
        "learned",
        "oracle",
        "deterministic",
        "learned",
        "oracle",
        "learned",
        "deterministic",
        "oracle",
    ]
    for worker in workers:
        manifest, resources = worker["manifest"], worker["resources"]
        assert manifest["status"] == "ready"
        assert manifest["worker_exit_code"] == 0
        assert manifest["fresh_python_process"] is True
        assert (
            resources["worker_pid"] == manifest["worker_pid"] != manifest["parent_pid"]
        )
        assert (
            process._resource_validation_failure(
                resources,
                manifest["worker_pid"],
                REVISION,
                manifest["artifacts"]["search.json"],
                process._CANDIDATE,
            )
            is None
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
            resources["per_strategy_peak_memory_reason"] == process.CANDIDATE_PEAK_SCOPE
        )
        if sys.platform == "linux":
            assert resources["peak_memory_bytes"] > 0
        else:
            assert resources["peak_memory_bytes"] is None
        assert resources["input_bytes_read"] == sum(
            row["byte_length"] for row in resources["inputs"]
        )
        for row in resources["inputs"]:
            raw = Path(row["path"]).read_bytes()
            assert row["sha256"] == process._digest(raw)
            assert row["byte_length"] == len(raw)
        for name, artifact in manifest["artifacts"].items():
            raw = (worker["directory"] / name).read_bytes()
            assert artifact == {"sha256": process._digest(raw), "byte_length": len(raw)}
        assert resources["resource_sidecar_io_included"] is False
        assert resources["source_revision_is_attestation"] is False
        assert resources["independent_hardware_validation"] is False
        assert resources["generalized_speedup_claimed"] is False


def test_actual_schedule_preserves_training_once_and_every_baseline_oracle_request(
    actual_suite,
):
    report = actual_suite["report"]
    assert report["schema_version"] == "rc-fiber-candidate-process-suite.v1"
    assert report["suite_identity_hash"] == canonical_hash(report["declaration"])
    assert report["report_hash"] == canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )
    assert report["declaration"]["configuration"] == {
        "repetitions": 2,
        "warmups": 1,
        "oracle_audit": True,
    }
    assert report["declaration"]["parent_plans_frozen_before_first_worker"] is True
    runs = report["runs"]
    assert len(runs) == 9
    assert all(
        row["attempted"]
        and row["report_contract_pass"]
        and row["resource_contract_pass"]
        for row in runs
    )
    assert [(row["phase"], row["repetition"], row["strategy"]) for row in runs] == [
        (phase, repetition, strategy)
        for phase, repetition, order in (
            ("warmup", 0, ("deterministic", "learned", "oracle")),
            ("measured", 0, ("deterministic", "learned", "oracle")),
            ("measured", 1, ("learned", "deterministic", "oracle")),
        )
        for strategy in order
    ]
    original_training = json.loads((FIXTURES / "training.json").read_bytes())
    cost = report["cost_accounting"]
    assert list(cost["training_artifacts_charged_once"]) == [
        original_training["report_hash"]
    ]
    assert cost["historical_training_analysis_request_count"] == 4
    assert (
        cost["historical_data_generation_wall_ns"]
        == original_training["cost_accounting"]["data_generation_wall_ns"]
    )
    assert (
        cost["historical_training_wall_ns"]
        == original_training["cost_accounting"]["training_wall_ns"]
    )
    assert cost["current_analysis_request_count"] == 21
    assert (
        cost["total_analysis_request_count_including_training_warmups_and_oracles"]
        == 25
    )
    for phase, slots, online, oracle in (("warmup", 3, 4, 3), ("measured", 6, 8, 6)):
        actual = cost["phases"][phase]
        assert (
            actual["declared_worker_slots"]
            == actual["attempted_worker_slots"]
            == actual["validated_report_count"]
            == slots
        )
        assert actual["validated_online_request_subtotal"] == online
        assert actual["validated_oracle_request_subtotal"] == oracle
        assert actual["total_analysis_request_count"] == online + oracle
        assert actual["known_solver_execution_subtotal"] == online + oracle
        assert (
            actual["unknown_request_slots"]
            == actual["not_launched_slots"]
            == actual["unknown_solver_execution_subtotal"]
            == 0
        )
    for row in runs:
        child = row["report"]
        assert child["cost_accounting"]["training_execution_count"] == 0
        assert child["cost_accounting"]["data_collection_execution_count"] == 0
        assert child["cost_accounting"]["historical_costs_charged_here"] is False
        request = process._json(Path(row["request_file"]).read_bytes())
        if row["strategy"] == "oracle":
            assert len(child["rows"]) == 3
            assert set(request["online_completion_hashes"]) == {
                "deterministic",
                "learned",
            }
        else:
            arm = child["arm"]
            assert request["online_completion_hashes"] == {}
            assert arm["cost_accounting"]["baseline_analysis_request_count"] == 1
            assert arm["cost_accounting"]["candidate_analysis_request_count"] == 1
            assert arm["cost_accounting"]["total_analysis_request_count"] == 2
            assert arm["final_selection"]["full_reference_verification_pass"] is True
            assert arm["final_selection"]["terminal_limit_status"] == "pass"
    accounting = report["resource_accounting"]
    assert accounting["validated_resource_worker_count"] == 9
    assert (
        accounting["worker_cpu_process_time_ns"]
        == accounting["worker_cpu_process_time_ns_subtotal"]
        == sum(row["resources"]["cpu_process_time_ns"] for row in runs)
    )
    assert (
        accounting["current_parent_plus_workers_cpu_time_ns"]
        == accounting["parent_cpu_time_ns"] + accounting["worker_cpu_process_time_ns"]
    )
    for strategy in ("deterministic", "learned", "oracle"):
        for phase, count in (("warmup", 1), ("measured", 2)):
            values = accounting["workers_by_strategy"][strategy][phase]
            assert values["observed_workers"] == values["declared_slots"] == count
            assert values["worker_cpu_process_time_ns"]["count"] == count
            if sys.platform == "linux":
                assert values["peak_memory_bytes"]["count"] == count
            assert values["peak_values_are_separate_process_high_water_marks"] is True
    pairs = report["case_summaries"][0]["measured_pairs"]
    assert len(pairs) == 2
    for pair in pairs:
        assert pair["online_reports_valid"] is True
        assert pair["online_resources_valid"] is True
        assert pair["selected_candidate_ids"] == {
            "deterministic": "baseline",
            "learned": "near-limit",
        }
        assert pair["oracle_audit"]["deterministic"]["false_safe_count"] is None
    assert report["case_summaries"][0]["break_even_is_observed_execution"] is False
    for claim in (
        "historical_training_reexecuted",
        "oracle_labels_available_to_online_selection",
        "independent_case_families_verified",
        "hashes_attest_provenance",
        "generalized_speedup_claimed",
        "confirmed_construction_savings",
        "production_promotion_eligible",
    ):
        assert report["claims"][claim] is False


@pytest.mark.parametrize("value", (True, 1.0))
def test_candidate_peak_requires_exact_integer_type_after_outer_rehash(
    actual_suite, value
):
    worker = deepcopy(actual_suite["workers"][0])
    worker["resources"].update(
        peak_memory_bytes=1, per_strategy_peak_memory_bytes=value
    )
    _seal(worker)
    assert (
        process._resource_validation_failure(
            worker["resources"],
            worker["manifest"]["worker_pid"],
            REVISION,
            worker["manifest"]["artifacts"]["search.json"],
            process._CANDIDATE,
        )
        == "worker_resources_contract_invalid"
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-cpu",
        "negative-cpu",
        "boolean-wall",
        "unknown-field",
        "partial-workload-scope",
        "unbound-source",
        "unbound-pid",
        "unbound-report-bytes",
        "promoted-claim",
        "wrong-arm",
    ),
)
def test_resource_sidecar_cannot_promote_partial_or_detached_measurements(
    actual_suite, mutation
):
    worker = deepcopy(actual_suite["workers"][0])
    resources = worker["resources"]
    if mutation == "missing-cpu":
        resources.pop("cpu_process_time_ns")
    elif mutation == "negative-cpu":
        resources["workload_cpu_process_time_ns"] = -1
    elif mutation == "boolean-wall":
        resources["workload_wall_ns"] = True
    elif mutation == "unknown-field":
        resources["extra"] = 0
    elif mutation == "partial-workload-scope":
        resources["workload_scope"] = "successful_selected_solve_only"
    elif mutation == "unbound-source":
        resources["source_revision"] = "b" * 40
    elif mutation == "unbound-pid":
        resources["worker_pid"] += 1
    elif mutation == "promoted-claim":
        resources["generalized_speedup_claimed"] = True
    elif mutation == "wrong-arm":
        resources["strategy"] = "all-arms-in-one-process"
    _seal(worker)
    if mutation == "unbound-report-bytes":
        resources["search_sha256"] = "sha256:" + "b" * 64
    assert (
        process._resource_validation_failure(
            resources,
            worker["manifest"]["worker_pid"],
            REVISION,
            worker["manifest"]["artifacts"]["search.json"],
            process._CANDIDATE,
        )
        is not None
    )


def test_cpu_process_time_is_not_artificially_capped_by_wall_time(actual_suite):
    worker = deepcopy(actual_suite["workers"][0])
    resources = worker["resources"]
    # The CPU metric sums process threads. This contract probe changes no real
    # measurement and deliberately exercises a valid CPU-greater-than-wall shape.
    resources["workload_cpu_process_time_ns"] = resources["workload_wall_ns"] * 2
    resources["cpu_process_time_ns"] = resources["workload_cpu_process_time_ns"] + 1
    _seal(worker)
    assert (
        process._resource_validation_failure(
            resources,
            worker["manifest"]["worker_pid"],
            REVISION,
            worker["manifest"]["artifacts"]["search.json"],
            process._CANDIDATE,
        )
        is None
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "source",
        "configuration",
        "price",
        "limits",
        "training",
        "missing-candidate",
        "duplicate-candidate",
        "frozen-shortlist",
        "candidate-outcome-coverage",
        "baseline-request-not-charged",
        "known-solver-count",
        "total-request-count",
        "training-executed",
        "historical-double-charge",
        "negative-workload-wall",
        "boolean-workload-wall",
        "promoted-oracle-label-access",
    ),
)
def test_rehashed_search_report_cannot_change_frozen_inputs_or_costs(
    actual_suite, tmp_path, mutation
):
    worker = deepcopy(actual_suite["workers"][0])
    report = worker["report"]
    binding = report["input_binding"]
    arm = report["arm"]
    if mutation == "source":
        binding["source_revision"] = "b" * 40
    elif mutation == "configuration":
        binding["configuration"]["load_steps"] += 1
    elif mutation == "price":
        binding["price_basis"]["currency"] = "USD"
    elif mutation == "limits":
        binding["terminal_limits"]["maximum_translation_m"] *= 2
    elif mutation == "training":
        binding["training_report_hash"] = "sha256:" + "f" * 64
    elif mutation == "missing-candidate":
        report["candidate_pool"].pop()
    elif mutation == "duplicate-candidate":
        report["candidate_pool"].append(deepcopy(report["candidate_pool"][0]))
    elif mutation == "frozen-shortlist":
        report["frozen_plan"]["shortlist"] = ["near-limit"]
        report["frozen_plan_hash"] = canonical_hash(report["frozen_plan"])
    elif mutation == "candidate-outcome-coverage":
        arm["candidate_outcomes"].pop()
    elif mutation == "baseline-request-not-charged":
        arm["cost_accounting"]["baseline_analysis_request_count"] = 0
    elif mutation == "known-solver-count":
        arm["cost_accounting"]["known_solver_execution_count"] -= 1
    elif mutation == "total-request-count":
        arm["cost_accounting"]["total_analysis_request_count"] -= 1
    elif mutation == "training-executed":
        report["cost_accounting"]["training_execution_count"] = 1
    elif mutation == "historical-double-charge":
        report["cost_accounting"]["historical_costs_charged_here"] = True
    elif mutation == "negative-workload-wall":
        report["cost_accounting"]["actual_workload_wall_ns"] = -1
    elif mutation == "boolean-workload-wall":
        report["cost_accounting"]["actual_workload_wall_ns"] = True
    elif mutation == "promoted-oracle-label-access":
        report["claims"]["oracle_labels_available_to_online_selection"] = True
    _seal(worker)
    validation = _validate_saved_worker(actual_suite, tmp_path, worker)
    assert validation["report_contract_pass"] is False, mutation
    assert validation["failure"]["report"] is not None


@pytest.mark.parametrize("index", (0, 1, 2))
def test_saved_positive_arm_and_oracle_remain_valid_under_parent_revalidation(
    actual_suite, tmp_path, index
):
    worker = deepcopy(actual_suite["workers"][index])
    _seal(worker)
    validation = _validate_saved_worker(actual_suite, tmp_path, worker)
    assert validation["report_contract_pass"] is True, validation["failure"]
    assert validation["resource_contract_pass"] is True, validation["failure"]


def test_rehashed_oracle_cannot_omit_a_declared_candidate(actual_suite, tmp_path):
    worker = deepcopy(actual_suite["workers"][2])
    assert worker["report"]["strategy"] == "oracle"
    worker["report"]["rows"].pop()
    _seal(worker)
    validation = _validate_saved_worker(actual_suite, tmp_path, worker)
    assert validation["report_contract_pass"] is False


def test_outer_byte_binding_is_checked_before_report_credit(actual_suite, tmp_path):
    worker = deepcopy(actual_suite["workers"][0])
    worker["report"]["extra"] = "detached bytes without a new manifest identity"
    validation = _validate_saved_worker(actual_suite, tmp_path, worker)
    assert validation["report_contract_pass"] is False


def _fake_launcher(actual_suite, mode):
    """Orchestration-only replay: retained physical rows, synthetic launch data."""
    calls = []

    def launch(request_path, *, source_revision, output_directory, timeout_seconds):
        declaration = process._json(request_path.read_bytes())
        strategy = declaration["strategy"]
        calls.append(strategy)
        first = len(calls) == 1
        worker = deepcopy(
            next(
                row
                for row in actual_suite["workers"]
                if row["resources"]["strategy"] == strategy
            )
        )
        report, resources, manifest = (
            worker["report"],
            worker["resources"],
            worker["manifest"],
        )
        pid = 93_100 if mode == "duplicate-pid" else 93_100 + len(calls)
        resources["worker_pid"] = manifest["worker_pid"] = pid
        manifest["parent_pid"] = os.getpid()
        resources["inputs"] = [
            {**candidate._identity(request_path), "read_wall_ns": 1},
            *({**item, "read_wall_ns": 1} for item in declaration["expected_inputs"]),
        ]
        resources["input_bytes_read"] = sum(
            row["byte_length"] for row in resources["inputs"]
        )
        resources["input_read_wall_ns"] = len(resources["inputs"])
        if first and mode == "malformed-report":
            report["arm"]["cost_accounting"]["baseline_analysis_request_count"] = 0
        _seal(worker)
        output_directory.mkdir()
        _write(output_directory / "search.json", report)
        if not (first and mode == "missing-resources"):
            _write(output_directory / "resources.json", resources)
        if first and mode == "timeout":
            manifest.update(
                status="timeout",
                worker_exit_code=-15,
                worker_measurements_available=False,
                worker_resource_validation_failure="worker_timeout",
            )
            for filename, raw in (
                ("search.json", b'{"partial":'),
                ("resources.json", b'{"cpu":'),
            ):
                (output_directory / filename).write_bytes(raw)
                manifest["artifacts"][filename] = {
                    "sha256": process._digest(raw),
                    "byte_length": len(raw),
                }
        _write(output_directory / "manifest.json", manifest)
        if first and mode == "changed-frozen-input":
            Path(declaration["case"]["model_file"]).write_bytes(b"changed copied input")
        return manifest

    return launch, calls


def test_parent_slot_includes_request_persistence_launch_and_validation(
    actual_suite, tmp_path, monkeypatch
):
    """Controlled-clock replay checks scope arithmetic, not measured performance."""
    clock = {"wall": 0, "cpu": 0}
    request_costs = {"deterministic": (11, 2), "learned": (29, 3), "oracle": (17, 4)}
    validation_costs = {"deterministic": (31, 5), "learned": (71, 7), "oracle": (43, 6)}
    events = []
    saved_write = process._write
    saved_validate = candidate._validate_worker
    replay, _calls = _fake_launcher(actual_suite, "ready")

    def advance(phase, strategy, wall, cpu):
        events.append((phase, strategy))
        clock["wall"] += wall
        clock["cpu"] += cpu

    def persist_request(path, raw):
        if path.parent.name == "requests":
            strategy = process._json(raw)["strategy"]
            advance("request", strategy, *request_costs[strategy])
        return saved_write(path, raw)

    def launch(request_path, **kwargs):
        strategy = process._json(request_path.read_bytes())["strategy"]
        advance("launch", strategy, 100, 1)
        return replay(request_path, **kwargs)

    def validate(output, request_path, expectations, **kwargs):
        strategy = process._json(request_path.read_bytes())["strategy"]
        advance("validation", strategy, *validation_costs[strategy])
        return saved_validate(output, request_path, expectations, **kwargs)

    monkeypatch.setattr(candidate, "perf_counter_ns", lambda: clock["wall"])
    monkeypatch.setattr(candidate, "process_time_ns", lambda: clock["cpu"])
    monkeypatch.setattr(process, "_write", persist_request)
    monkeypatch.setattr(candidate, "_launch_worker", launch)
    monkeypatch.setattr(candidate, "_validate_worker", validate)
    report = candidate.run_fiber_frame_candidate_process_suite(
        actual_suite["request"],
        source_revision=REVISION,
        output_directory=tmp_path / "suite",
    )
    assert report["status"] == "ready", report["runs"]
    expected_walls = {"deterministic": 142, "learned": 200, "oracle": 160}
    expected_cpus = {"deterministic": 8, "learned": 11, "oracle": 11}
    assert events == [
        (phase, row["strategy"])
        for row in report["runs"]
        for phase in ("request", "launch", "validation")
    ]
    for row in report["runs"]:
        assert row["parent_slot_observed_wall_ns"] == expected_walls[row["strategy"]]
        assert row["parent_slot_cpu_time_ns"] == expected_cpus[row["strategy"]]
        assert row["slot_wall_includes_worker_launch_and_parent_validation"] is True
    summary = report["case_summaries"][0]
    # Both synthetic launches consume 100 ns. Only the full parent slots expose
    # the 58 ns difference caused by request persistence and parent validation.
    assert [
        row["deterministic_minus_learned_slot_wall_ns"]
        for row in summary["measured_pairs"]
    ] == [-58, -58]
    assert summary["paired_deterministic_minus_learned_slot_wall_ns"]["count"] == 2
    assert summary["paired_deterministic_minus_learned_slot_wall_ns"]["median"] == -58
    assert summary["projected_reuses_to_amortize_this_training_artifact"] is None
    assert report["resource_accounting"]["parent_wall_ns"] == sum(
        row["parent_slot_observed_wall_ns"] for row in report["runs"]
    )
    assert report["resource_accounting"]["parent_cpu_time_ns"] == sum(
        row["parent_slot_cpu_time_ns"] for row in report["runs"]
    )


@pytest.mark.parametrize(
    "mode",
    (
        "malformed-report",
        "timeout",
        "missing-resources",
        "duplicate-pid",
        "changed-frozen-input",
    ),
)
def test_parent_retains_failed_slots_and_separates_unknown_work_from_known_cpu(
    actual_suite, tmp_path, monkeypatch, mode
):
    launch, calls = _fake_launcher(actual_suite, mode)
    monkeypatch.setattr(candidate, "_launch_worker", launch)
    report = candidate.run_fiber_frame_candidate_process_suite(
        actual_suite["request"],
        source_revision=REVISION,
        output_directory=tmp_path / "suite",
    )
    assert report["status"] == "incomplete"
    assert len(report["runs"]) == 9
    assert report["claims"]["report_contract_pass"] is False
    assert report["claims"]["local_timing_evidence_eligible"] is False
    cost = report["cost_accounting"]
    accounting = report["resource_accounting"]
    assert cost["historical_training_analysis_request_count"] == 4
    assert len(cost["training_artifacts_charged_once"]) == 1
    assert (
        report["case_summaries"][0][
            "projected_reuses_to_amortize_this_training_artifact"
        ]
        is None
    )
    observed = [row for row in report["runs"] if row["resource_contract_pass"]]
    assert accounting["validated_resource_worker_count"] == len(observed)
    assert accounting["worker_cpu_process_time_ns_subtotal"] == sum(
        row["resources"]["cpu_process_time_ns"] for row in observed
    )
    if mode == "malformed-report":
        assert len(calls) == 8
        assert report["runs"][0]["report_contract_pass"] is False
        assert report["runs"][0]["resource_contract_pass"] is True
        assert cost["phases"]["warmup"]["unknown_request_slots"] == 1
        assert cost["current_analysis_request_count"] is None
        assert (
            cost["total_analysis_request_count_including_training_warmups_and_oracles"]
            is None
        )
        assert accounting["validated_resource_worker_count"] == 8
        assert (
            accounting["worker_cpu_process_time_ns"]
            == accounting["worker_cpu_process_time_ns_subtotal"]
        )
    elif mode == "timeout":
        assert len(calls) == 8
        assert accounting["validated_resource_worker_count"] == 7
        assert accounting["worker_cpu_process_time_ns"] is None
        assert cost["current_analysis_request_count"] is None
        failed = Path(report["runs"][0]["worker_directory"])
        assert (failed / "search.json").read_bytes() == b'{"partial":'
        assert (failed / "resources.json").read_bytes() == b'{"cpu":'
    elif mode == "missing-resources":
        assert len(calls) == 9
        assert report["runs"][0]["report_contract_pass"] is True
        assert report["runs"][0]["resource_contract_pass"] is False
        assert accounting["validated_resource_worker_count"] == 8
        assert accounting["worker_cpu_process_time_ns"] is None
        assert cost["current_analysis_request_count"] == 21
    elif mode == "duplicate-pid":
        assert accounting["validated_resource_worker_count"] < 9
    elif mode == "changed-frozen-input":
        assert calls == ["deterministic"]
        assert all(not row["attempted"] for row in report["runs"][1:])
        assert accounting["validated_resource_worker_count"] == 0
        assert cost["current_analysis_request_count"] is None


def test_candidate_timeout_reaps_only_its_worker_and_retains_partial_bytes(
    tmp_path, monkeypatch
):
    output = tmp_path / "worker"
    events = []

    class Worker:
        pid = 92_311

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if len(events) == 1:
                raise subprocess.TimeoutExpired("candidate worker", timeout)
            return -15

        def terminate(self):
            events.append(("terminate", None))

    def launch(*_args, **_kwargs):
        (output / "resources.json").write_bytes(b'{"cpu":')
        (output / "search.json").write_bytes(b'{"partial":')
        return Worker()

    monkeypatch.setattr(process.subprocess, "Popen", launch)
    manifest = process._run_fiber_frame_process(
        tmp_path / "request.json",
        source_revision=REVISION,
        output_directory=output,
        timeout_seconds=0.01,
        profile=process._CANDIDATE,
    )
    assert manifest["status"] == "timeout"
    assert manifest["worker_measurements_available"] is False
    assert manifest["worker_resource_validation_failure"] == "worker_timeout"
    assert [row[0] for row in events] == ["wait", "terminate", "wait"]
    assert (output / "search.json").read_bytes() == b'{"partial":'
    assert (output / "resources.json").read_bytes() == b'{"cpu":'
    assert manifest["artifacts"]["search.json"] == {
        "sha256": process._digest(b'{"partial":'),
        "byte_length": len(b'{"partial":'),
    }
