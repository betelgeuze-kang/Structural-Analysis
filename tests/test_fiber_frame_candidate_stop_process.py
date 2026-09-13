"""No-worker stop-mode request, parent accounting and portable review checks."""

from copy import deepcopy
import json

import pytest

from structural_analysis.benchmark import fiber_frame_candidate_process as process
from structural_analysis.benchmark import fiber_frame_candidate_review as review
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arm
from tests.test_fiber_frame_candidate_material_contract import (
    SOURCE,
    material_request as _material_request,
    no_execution as _no_execution,
    retained as _retained,
)
from tests.test_fiber_frame_candidate_stop_suite import (
    arguments as _stop_arguments,
    evaluate_rows as _evaluate_rows,
    produce,
)


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    return _no_execution.__wrapped__(monkeypatch)


@pytest.fixture(scope="module")
def retained():
    return _retained.__wrapped__()


@pytest.fixture
def stop_arguments(tmp_path, retained):
    return _stop_arguments.__wrapped__(tmp_path, retained)


@pytest.fixture
def evaluate_rows(retained, monkeypatch):
    return _evaluate_rows.__wrapped__(retained, monkeypatch)


@pytest.fixture
def stop_request(tmp_path, retained):
    path, value = _material_request.__wrapped__(tmp_path, retained)
    value["schema_version"] = process.REQUEST_STOP_SCHEMA
    value["cases"][0]["stop_mode"] = search.FIRST_VERIFIED_FEASIBLE
    path.write_bytes(process.process._bytes(value))
    return path, value


def freeze(path, tmp_path):
    output = tmp_path / "frozen"
    output.mkdir()
    return process._freeze_inputs(path, output, source_revision=SOURCE)


@pytest.mark.parametrize("mode", [None, False, True, 0, "", "all", "first"])
def test_explicit_invalid_json_mode_rejected_before_plan(stop_request, tmp_path, mode):
    path, payload = stop_request
    payload["cases"][0]["stop_mode"] = mode
    path.write_bytes(process.process._bytes(payload))
    with pytest.raises(ValueError, match="stop mode"):
        freeze(path, tmp_path)


@pytest.mark.parametrize(
    "schema", [process.REQUEST_SCHEMA, process.REQUEST_MATERIAL_SCHEMA]
)
def test_mode_cannot_downgrade_request_version(stop_request, tmp_path, schema):
    path, payload = stop_request
    payload["schema_version"] = schema
    path.write_bytes(process.process._bytes(payload))
    with pytest.raises(ValueError, match="unsupported"):
        freeze(path, tmp_path)


def test_v3_requires_at_least_one_explicit_mode(stop_request, tmp_path):
    path, payload = stop_request
    payload["cases"][0].pop("stop_mode")
    path.write_bytes(process.process._bytes(payload))
    with pytest.raises(ValueError, match="unsupported"):
        freeze(path, tmp_path)


def test_mixed_modes_bind_every_plan_and_worker_schema(stop_request, tmp_path):
    path, payload = stop_request
    material = deepcopy(payload["cases"][0])
    material.pop("stop_mode")
    material["case_id"] = "material"
    legacy = deepcopy(material)
    legacy.pop("material_history_limits")
    legacy["case_id"] = "legacy"
    payload["cases"].extend([material, legacy])
    path.write_bytes(process.process._bytes(payload))
    frozen = freeze(path, tmp_path)
    assert [process._worker_schema(c["request"]) for c in frozen["cases"]] == [
        process.WORKER_STOP_SCHEMA,
        process.WORKER_MATERIAL_SCHEMA,
        process.WORKER_SCHEMA,
    ]
    for case in frozen["cases"]:
        enabled = case["case_id"] == "pool-a"
        binding = case["expectations"]["input_binding"]
        assert ("stop_mode" in binding) is enabled
        for strategy in arm.STRATEGIES:
            plan = case["expectations"][strategy]["frozen_plan"]
            assert ("stop_mode" in plan) is enabled
            if enabled:
                assert plan["stop_mode"] == search.FIRST_VERIFIED_FEASIBLE


@pytest.mark.parametrize("mutation", ["schema", "delete_mode", "different_mode"])
def test_worker_mode_mismatch_fails_before_artifact_read(
    stop_request, tmp_path, mutation
):
    path, _ = stop_request
    case = freeze(path, tmp_path)["cases"][0]
    request = dict(
        schema_version=process.WORKER_STOP_SCHEMA,
        case=deepcopy(case["request"]),
        strategy="learned",
        expected_plan_hash=case["expectations"]["learned"]["frozen_plan_hash"],
        expected_inputs=[],
        online_completion_hashes={},
    )
    if mutation == "schema":
        request["schema_version"] = process.WORKER_MATERIAL_SCHEMA
    elif mutation == "delete_mode":
        request["case"].pop("stop_mode")
        request["schema_version"] = process.WORKER_MATERIAL_SCHEMA
    else:
        request["case"]["stop_mode"] = None
    target = tmp_path / "worker-request.json"
    reads = []

    def read(file, _limit):
        reads.append(file)
        assert file == target, "invalid mode reached worker artifact reads"
        return process.process._bytes(request)

    checked = process._validate_worker(
        tmp_path / "worker",
        target,
        case["expectations"],
        source_revision=SOURCE,
        read=read,
    )
    assert reads == [target]
    assert checked["report_contract_pass"] is False
    assert checked["failure"]["report"] is not None


def test_unlaunched_v3_keeps_all_slots_zero_requests_and_portable_review(
    stop_request, tmp_path, monkeypatch
):
    path, _ = stop_request
    monkeypatch.setattr(process, "_unchanged", lambda *_: False)
    report = process.run_fiber_frame_candidate_process_suite(
        path, source_revision=SOURCE, output_directory=tmp_path / "suite"
    )
    assert report["schema_version"] == process.STOP_SCHEMA_VERSION
    assert report["status"] == "incomplete"
    assert len(report["runs"]) == 6
    assert all(not row["attempted"] for row in report["runs"])
    assert report["cost_accounting"]["current_analysis_request_count"] == 0
    assert (
        report["cost_accounting"][
            "total_analysis_request_count_including_training_warmups_and_oracles"
        ]
        == 4
    )
    target = review.write_fiber_frame_candidate_process_review_bundle(
        tmp_path / "suite/suite.json", tmp_path / "review"
    )
    manifest = json.loads(target.read_bytes())
    assert manifest["schema_version"] == review.STOP_SCHEMA_VERSION
    bundle = review.validate_fiber_frame_candidate_process_review_bundle(
        tmp_path / "review"
    )
    assert bundle["suite"]["status"] == "incomplete"
    assert len(bundle["suite"]["runs"]) == 6
    assert (
        bundle["suite"]["case_summaries"][0][
            "projected_reuses_to_amortize_this_training_artifact"
        ]
        is None
    )
    manifest["schema_version"] = review.MATERIAL_SCHEMA_VERSION
    target.write_bytes(process.process._bytes(manifest))
    with pytest.raises(ValueError, match="review schema"):
        review.validate_fiber_frame_candidate_process_review_bundle(tmp_path / "review")


def test_default_request_has_no_additional_mode_keys(stop_request, tmp_path):
    path, value = stop_request
    value["schema_version"] = process.REQUEST_MATERIAL_SCHEMA
    value["cases"][0].pop("stop_mode")
    path.write_bytes(process.process._bytes(value))
    case = freeze(path, tmp_path)["cases"][0]
    assert "stop_mode" not in process._case_arguments(case["request"], path.parent)
    assert "stop_mode" not in case["expectations"]["input_binding"]
    assert all(
        "stop_mode" not in case["expectations"][s]["frozen_plan"]
        for s in arm.STRATEGIES
    )


def test_actual_count_does_not_charge_planned_suffix():
    report = {
        "strategy": "learned",
        "arm": {
            "baseline": {"analysis_requested": True, "solver_executed": True},
            "shortlist": ["attempted-failed", "unattempted"],
            "candidate_outcomes": [
                {"analysis_requested": True, "solver_executed": None},
                {"analysis_requested": False, "solver_executed": False},
            ],
        },
    }
    assert process._counts(report) == {
        "full_analysis_request_count": 2,
        "known_solver_execution_count": 1,
        "unknown_solver_execution_count": 1,
    }


@pytest.mark.parametrize("worse_quality", [False, True])
def test_parent_summary_keeps_planned_vs_unrequested_and_quality_cost_gate(
    stop_arguments, evaluate_rows, worse_quality
):
    report, binding = produce(stop_arguments)
    expectations = arm.prepare_fiber_frame_candidate_search_expectations(
        **stop_arguments
    )
    frozen = {
        "configuration": {"repetitions": 2},
        "cases": [
            {
                "case_id": "synthetic",
                "request": {
                    "stop_mode": search.FIRST_VERIFIED_FEASIBLE,
                    "history_limits": binding["history_limits"],
                    "material_history_limits": binding["material_history_limits"],
                },
                "expectations": expectations,
            }
        ],
    }
    slots = []
    for repetition in range(2):
        for index, strategy in enumerate(arm.STRATEGIES):
            payload = {"status": "ready", "strategy": strategy}
            if strategy == "oracle":
                payload["rows"] = report["oracle"]["rows"]
            else:
                payload["arm"] = deepcopy(report["arms"][index])
                # Synthetic parent-only quality boundary, not a changed valid artifact.
                if strategy == "learned" and worse_quality:
                    payload["arm"]["final_selection"]["material_estimate"]["total"] += (
                        1.0
                    )
            slots.append(
                {
                    "case_id": "synthetic",
                    "phase": "measured",
                    "repetition": repetition,
                    "strategy": strategy,
                    "report_contract_pass": True,
                    "resource_contract_pass": True,
                    "report": payload,
                    "parent_slot_observed_wall_ns": 20
                    if strategy == "deterministic"
                    else 10,
                    "resources": {
                        "cpu_process_time_ns": 10 if strategy == "deterministic" else 5
                    },
                }
            )
    result = process._summarize_cases(frozen, slots)[0]
    assert result["paired_deterministic_minus_learned_slot_wall_ns"]["median"] == 10
    assert (
        result["projected_reuses_to_amortize_this_training_artifact"] is None
    ) is worse_quality
    for pair in result["measured_pairs"]:
        assert (
            pair["learned_verified_scoped_material_cost_not_worse"] is not worse_quality
        )
        for audit in pair["oracle_audit"].values():
            assert audit["missed_feasible_count"] == 0
            assert audit["unrequested_feasible_count"] == 1
            assert audit["unrequested_feasible_candidate_ids"] == ["near-limit"]
        assert pair["oracle_audit"]["deterministic"]["false_safe_count"] is None
