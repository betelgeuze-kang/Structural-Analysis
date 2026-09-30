"""Original isolated RC numerical phases compared with contemporaneous baselines.

Each authored case runs an absent-policy in-process full path, an isolated full
path and isolated fixed chunks on newly constructed services. Every numerical
analysis receives an actual fresh verification. These synthetic tiny models are
software regressions, not independent physical validation, performance evidence,
RSS/disk quotas or release approval. Original bytes remain in pytest temporary
stores; no retained-environment artifact shortcut is used.
"""

from __future__ import annotations

from copy import deepcopy
import gc
import json
import os
import sys
import time
from types import SimpleNamespace
import weakref

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution import rc_fiber_direct_control_worker as worker
from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.execution.rc_fiber_phase_policy import (
    decode_rc_fiber_phase_policy,
)
from tests.test_rc_fiber_durable_worker import (
    ROOT,
    TENANT_AUTH,
    WORKER_AUTH,
    _bytes,
    _claim,
    _evidence,
    _native,
    _request,
    _run,
    _sha,
)
from tests.test_rc_fiber_pin_roller_beam_public import _payload as pin_roller_payload

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Authored isolated RC phase policy requires Linux"
)


def _policy():
    return {
        "schema_version": "bounded-rc-fiber-phase-execution-policy.v1",
        "analysis_timeout_ms": 30_000,
        "verification_timeout_ms": 30_000,
        "termination_grace_ms": 100,
    }


def _new_service(directory):
    # Real UTC lease clock; connections are scoped/closed by service operations.
    return DurableJobService(
        directory,
        tenant_tokens={"tenant": TENANT_AUTH["authorization_token"]},
        worker_tokens={"worker": WORKER_AUTH["authorization_token"]},
        worker_tenants={"worker": {"tenant"}},
    )


def _authored(case, *, chunk_size):
    request = _request(chunk_size=chunk_size, maximum_invocations=16)
    request["case_id"] = "isolated-native-" + case
    targets = (-1e-6, -2e-6)
    if case == "proportional-v1":
        typed = BoundedRCFiberDirectControlRequest(7, targets)
    elif case == "constant-v2":
        request["model"] = json.loads(
            (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_bytes()
        )
        request["model"]["sections"][0]["concrete_layer_count"] = 2
        typed = BoundedRCFiberDirectControlRequest(
            4, (-1e-5, -2e-5), constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),)
        )
    else:
        request["model"] = pin_roller_payload()
        loaded = case == "loaded-zero-first-v4"
        if loaded:
            nodes = request["model"]["nodes"]
            nodes[1], nodes[5] = nodes[5], nodes[1]
            targets = (0.0, -1e-6, -2e-6)
        typed = BoundedRCFiberDirectControlRequest(
            10,
            targets,
            allow_reversals=loaded,
            maximum_reversals=2 if loaded else 0,
            experimental_pin_roller_beam=True,
            constant_nodal_loads=(("N4", 0.0, -0.1, 0.0),) if loaded else (),
        )
    request["config"] = typed.to_dict()
    request["result_contract"] = (
        "bounded-rc-fiber-job-result.v2"
        if typed.constant_nodal_loads
        else "bounded-rc-fiber-job-result.v1"
    )
    return request


def _retire_service(service):
    # The service has no close() API and retains no connection field. Its
    # transactions close their connections; require no instance to be reused.
    return weakref.ref(service)


def _assert_store_fds_released(directory):
    # Releasing a Python object alone does not prove SQLite/blob descriptors
    # closed. Inspect this actual store's descriptors before its next reopen.
    prefix = str(directory.resolve()) + "/"
    for name in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink("/proc/self/fd/" + name)
        except FileNotFoundError:
            continue
        assert not target.startswith(prefix), (
            "Released service retained a store descriptor"
        )


def _retain(directory, service, job):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_bytes(_bytes(job.to_dict()))
    for role in ("request", "checkpoint", "result", "evidence"):
        if getattr(job, role) is not None:
            (directory / (role + ".json")).write_bytes(
                getattr(service, "read_" + role)(job.job_id, **TENANT_AUTH)
            )
    evidence = _evidence(service, job.job_id, **TENANT_AUTH)
    (directory / "invocations.json").write_bytes(_bytes(evidence))
    for reference in evidence["invocations"]:
        (directory / f"invocation-{reference['ordinal']}.json").write_bytes(
            service.read_rc_invocation_artifact(
                job.job_id, **TENANT_AUTH, ordinal=reference["ordinal"]
            )
        )
    return evidence


def _actual_observer(directory, rows):
    from structural_analysis.execution import rc_fiber_phase_supervisor as supervisor

    original = supervisor.run_rc_fiber_phase

    def observed(**kwargs):
        # This is an observer of the real supervisor, never a substitute reply.
        reply = original(**kwargs)
        metadata = reply.supervisor_timing
        assert metadata["child_pid"] != os.getpid()
        assert metadata["direct_child_reaped"] is True
        assert metadata["child_returncode"] == 0
        with pytest.raises(ChildProcessError):
            os.waitpid(metadata["child_pid"], os.WNOHANG)
        timing = reply.timing
        assert all(type(value) is int and value > 0 for value in timing.values())
        assert metadata["wall_ns"] >= timing["wall_ns"]
        index = len(rows) + 1
        export = directory / f"child-{index}-{kwargs['phase']}"
        export.mkdir(parents=True)
        for name, raw in (
            ("result.json", reply.raw_result),
            ("native-checkpoint.json", reply.native_checkpoint),
        ):
            if raw is not None:
                (export / name).write_bytes(raw)
        if reply.verification_report is not None:
            (export / "verification.json").write_bytes(
                _bytes(reply.verification_report)
            )
        row = {
            "phase": kwargs["phase"],
            "completed_before": kwargs["completed_before"],
            "completed_after": kwargs["completed_after"],
            "request_hash": _sha(kwargs["request_bytes"]),
            "restart_hash": None
            if kwargs["restart"] is None
            else _sha(kwargs["restart"]),
            "policy": kwargs["policy"].to_dict(),
            "status": reply.status,
            "timing": timing,
            "supervisor_timing": metadata,
        }
        rows.append(row)
        (export / "measurement.json").write_bytes(_bytes(row))
        return reply

    return supervisor, observed


def _forbid_parent_numerics_and_cpu(patch):
    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "Opted-in phase used parent numerical execution or parent CPU clock"
        )

    patch.setattr(api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    patch.setattr(api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden)
    # Replace only the worker module's time reference, never global time or the
    # fresh child interpreter. Child CPU must come from the real child reply.
    patch.setattr(
        worker,
        "time",
        SimpleNamespace(
            perf_counter_ns=time.perf_counter_ns, process_time_ns=forbidden
        ),
    )


def _run_arm(directory, request, *, isolated):
    request = deepcopy(request)
    if isolated:
        request["execution_config"]["phase_execution_policy"] = _policy()
    authored_bytes = _bytes(request)
    directory.mkdir()
    (directory / "authored-request.json").write_bytes(authored_bytes)
    service = _new_service(directory / "store")
    job = service.submit_job(
        **TENANT_AUTH, idempotency_key="phase-native", request=request
    )
    assert service.read_request(job.job_id, **TENANT_AUTH) == authored_bytes
    old = _retire_service(service)
    del service
    gc.collect()
    assert old() is None
    _assert_store_fds_released(directory / "store")
    saved, rows = [], []
    with pytest.MonkeyPatch.context() as patch:
        if isolated:
            supervisor, observer = _actual_observer(directory, rows)
            patch.setattr(supervisor, "run_rc_fiber_phase", observer)
            _forbid_parent_numerics_and_cpu(patch)
        total = len(request["config"]["targets_m"])
        size = request["execution_config"]["chunk_target_count"]
        for start in range(0, total, size):
            service = _new_service(directory / "store")
            claim = _claim(service)
            assert claim.request_bytes == authored_bytes
            if start:
                assert claim.checkpoint_bytes == saved[-1]
                assert service.read_checkpoint(job.job_id, **TENANT_AUTH) == saved[-1]
            else:
                assert claim.checkpoint_bytes is None
            job = _run(service, claim)
            after = min(start + size, total)
            assert job.progress_completed == after
            assert job.progress_total == total
            assert job.status == ("succeeded" if after == total else "checkpointed")
            assert service.validate_integrity(job.job_id, **TENANT_AUTH)[
                "contract_pass"
            ]
            checkpoint = (
                service.read_checkpoint(job.job_id, **TENANT_AUTH)
                if job.checkpoint is not None
                else None
            )
            if after < total:
                assert checkpoint is not None
                saved.append(checkpoint)
                (directory / f"checkpoint-after-{after}.json").write_bytes(checkpoint)
            old = _retire_service(service)
            del service
            gc.collect()
            assert old() is None
            _assert_store_fds_released(directory / "store")
    service = _new_service(directory / "store")
    final = service.get_job(job.job_id, **TENANT_AUTH)
    raw = service.read_result(job.job_id, **TENANT_AUTH)
    evidence = _retain(directory / "originals", service, final)
    result = json.loads(raw)
    arm = {
        "request": request,
        "authored_bytes": authored_bytes,
        "raw": raw,
        "result": result,
        "checkpoints": saved,
        "evidence": evidence,
        "observed_child_replies": rows,
    }
    (directory / "summary.json").write_bytes(
        _bytes(
            {
                "request_hash": _sha(authored_bytes),
                "result_hash": _sha(raw),
                "reserved_attempts": result["execution_budget"]["reserved_attempts"],
                "observed_child_replies": rows,
                "scope": "original software regression; child API and parent launch/IPC clocks are nested separate scopes, not a performance comparison",
            }
        )
    )
    old = _retire_service(service)
    del service
    gc.collect()
    assert old() is None
    _assert_store_fds_released(directory / "store")
    return arm


@pytest.fixture(
    scope="module",
    params=[
        "proportional-v1",
        "constant-v2",
        "pin-roller-v4",
        "loaded-zero-first-v4",
    ],
)
def actual_phase_runs(request, tmp_path_factory):
    case = request.param
    directory = tmp_path_factory.mktemp("rc-isolated-" + case)
    split_request = _authored(case, chunk_size=1)
    full_request = deepcopy(split_request)
    full_request["execution_config"]["chunk_target_count"] = len(
        full_request["config"]["targets_m"]
    )
    assert decode_rc_fiber_phase_policy(_policy()).to_dict() == _policy()
    arms = {
        "in-process-full": _run_arm(
            directory / "in-process-full", full_request, isolated=False
        ),
        "isolated-full": _run_arm(
            directory / "isolated-full", full_request, isolated=True
        ),
        "isolated-split": _run_arm(
            directory / "isolated-split", split_request, isolated=True
        ),
    }
    print("Original isolated/native RC regression artifacts:", directory, flush=True)
    return directory, arms


def test_actual_isolated_full_and_reopened_chunks_preserve_original_native_state(
    actual_phase_runs,
):
    _, arms = actual_phase_runs
    baseline = arms["in-process-full"]["result"]
    original_api = baseline["api_result"]
    for name in ("isolated-full", "isolated-split"):
        arm = arms[name]
        result = arm["result"]
        assert _native(result) == _native(baseline)
        assert result["authority"] == baseline["authority"]
        assert result["source_revision_is_attestation"] is False
        assert result["control_targets"] == baseline["control_targets"]
        for key in (
            "response_history",
            "terminal_response",
            "checkpoint",
            "model",
            "control",
            "claims",
        ):
            assert _bytes(result["api_result"][key]) == _bytes(original_api[key])
        assert result["api_result"].get("preload_response") == original_api.get(
            "preload_response"
        )
        for row in result["api_result"]["response_history"]:
            assert (
                row["member_end_forces"]
                and row["section_results"]
                and row["fiber_results"]
            )
        assert arm["request"]["execution_config"]["phase_execution_policy"] == _policy()
        assert (
            "phase_execution_policy"
            not in arms["in-process-full"]["request"]["execution_config"]
        )
        # Full wrappers contain different request identities and measured timing.
        assert arm["raw"] != arms["in-process-full"]["raw"]
    split = arms["isolated-split"]
    for index, raw in enumerate(split["checkpoints"], 1):
        prefix = json.loads(raw)
        assert prefix["completed_target_count"] == index
        assert prefix["receipts"] == split["result"]["receipts"][:index]
        assert prefix["resume_contract_hash"] == split["result"]["resume_contract_hash"]
    if split["request"]["case_id"].endswith("loaded-zero-first-v4"):
        current = split["result"]["api_result"]
        assert current["preload_response"]["epoch"] == 1
        assert current["response_history"][0]["epoch"] == 2
        preload_node = next(
            n
            for n in current["preload_response"]["node_displacements"]
            if n["node_id"] == "N4"
        )
        controlled = next(
            n
            for n in current["response_history"][0]["node_displacements"]
            if n["node_id"] == "N4"
        )
        assert preload_node["UY_m"] < 0
        assert abs(controlled["UY_m"]) <= 1e-12
        assert current["path"]["requested_directions"] == [1, -1, -1]


def test_actual_phase_child_timings_fresh_verification_and_reservations_are_exact(
    actual_phase_runs,
):
    _, arms = actual_phase_runs
    for name, arm in arms.items():
        result, envelope = arm["result"], arm["evidence"]
        receipts = result["receipts"]
        expected = 2 * len(receipts)
        assert result["execution_budget"]["reserved_attempts"] == expected
        assert envelope["execution_budget"]["reserved_attempts"] == expected
        assert envelope["pending_ordinals"] == []
        assert [record["ordinal"] for record in envelope["records"]] == list(
            range(1, expected + 1)
        )
        assert [record["outcome"]["phase"] for record in envelope["records"]] == [
            "analysis",
            "verification",
        ] * len(receipts)
        replies = arm["observed_child_replies"]
        if name != "in-process-full":
            assert len(replies) == expected
            assert (
                len({row["supervisor_timing"]["child_pid"] for row in replies})
                == expected
            )
        else:
            assert replies == []
        offset = int(bool(arm["request"]["config"].get("constant_nodal_loads")))
        for index, record in enumerate(envelope["records"]):
            outcome = record["outcome"]
            assert outcome["status"] == "returned"
            assert outcome["unavailable_execution_work"] is False
            assert all(
                type(value) is int and value > 0 for value in outcome["timing"].values()
            )
            receipt = receipts[index // 2]
            role = "analysis" if index % 2 == 0 else "verification"
            assert outcome["timing"] == receipt[role + "_timing"]
            assert record["ordinal"] == receipt[role + "_ordinal"]
            if replies:
                assert outcome["timing"] == replies[index]["timing"]
                assert replies[index]["phase"] == role
                assert replies[index]["policy"] == _policy()
                assert replies[index]["request_hash"] == _sha(arm["authored_bytes"])
            metrics = (
                outcome["api_result"]["metrics"]["control_work"]
                if role == "analysis"
                else outcome["verification_report"]["replay_control_work"]
            )
            assert (
                metrics["attempted_step_count"] == receipt["completed_after"] + offset
            )
            assert metrics["unknown_solver_work_attempt_count"] == 0
            assert metrics["known_newton_iteration_count"] > 0
            assert metrics["known_linear_solve_count"] > 0
            if role == "verification":
                report = outcome["verification_report"]
                assert report["fresh_source_execution_invoked"] is True
                assert report["solver_replay_performed"] is True
                assert report["contract_pass"] is True
                assert report["physical_path_complete"] is True


def test_actual_isolated_loaded_suffix_nonconvergence_retains_verified_prefix(tmp_path):
    directory = tmp_path / "isolated-loaded-suffix"
    directory.mkdir()
    request = _authored("pin-roller-v4", chunk_size=1)
    request["case_id"] = "isolated-loaded-suffix-nonconvergence"
    request["result_contract"] = "bounded-rc-fiber-job-result.v2"
    request["config"] = BoundedRCFiberDirectControlRequest(
        10,
        (-1e-6, -0.02),
        experimental_pin_roller_beam=True,
        constant_nodal_loads=(("N4", 0.0, -0.1, 0.0),),
    ).to_dict()
    request["config"]["solver_config"]["newton"]["max_iterations"] = 2
    request["execution_config"]["phase_execution_policy"] = _policy()
    service = _new_service(directory / "store")
    job = service.submit_job(
        **TENANT_AUTH, idempotency_key="phase-native-failed", request=request
    )
    request_raw = service.read_request(job.job_id, **TENANT_AUTH)
    replies = []
    with pytest.MonkeyPatch.context() as patch:
        supervisor, observer = _actual_observer(directory, replies)
        patch.setattr(supervisor, "run_rc_fiber_phase", observer)
        _forbid_parent_numerics_and_cpu(patch)
        first = _run(service, _claim(service))
        assert first.status == "checkpointed" and first.progress_completed == 1
        old_raw = service.read_checkpoint(job.job_id, **TENANT_AUTH)
        old_outcomes = {
            ordinal: service.read_rc_invocation_artifact(
                job.job_id, **TENANT_AUTH, ordinal=ordinal
            )
            for ordinal in (1, 2)
        }
        (directory / "verified-prefix.json").write_bytes(old_raw)
        old = _retire_service(service)
        del service
        gc.collect()
        assert old() is None
        _assert_store_fds_released(directory / "store")
        service = _new_service(directory / "store")
        claim = _claim(service)
        assert claim.checkpoint_bytes == old_raw
        with pytest.raises(
            worker.RCFiberDirectControlWorkerError,
            match="rc_fiber_worker_chunk_blocked",
        ):
            _run(service, claim)
    failed = service.get_job(job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.progress_completed == 1
    assert failed.checkpoint == first.checkpoint
    assert failed.result is failed.evidence is None
    assert service.read_checkpoint(job.job_id, **TENANT_AUTH) == old_raw
    assert service.read_request(job.job_id, **TENANT_AUTH) == request_raw
    for ordinal, raw in old_outcomes.items():
        assert (
            service.read_rc_invocation_artifact(
                job.job_id, **TENANT_AUTH, ordinal=ordinal
            )
            == raw
        )
    envelope = _retain(directory / "originals", service, failed)
    assert envelope["pending_ordinals"] == []
    assert envelope["execution_budget"]["reserved_attempts"] == 4
    assert len(replies) == 4
    outcomes = [record["outcome"] for record in envelope["records"]]
    assert [row["phase"] for row in outcomes] == ["analysis", "verification"] * 2
    for outcome, reply in zip(outcomes, replies):
        assert outcome["status"] == "returned"
        assert outcome["unavailable_execution_work"] is False
        assert outcome["timing"] == reply["timing"]
    suffix, verified = outcomes[2]["api_result"], outcomes[3]["verification_report"]
    assert suffix["status"] == "blocked" and suffix["contract_pass"] is False
    assert suffix["path"]["accepted_target_prefix_m"] == [-1e-6]
    assert _native(json.loads(old_raw)) == _native(
        {
            "terminal_checkpoint_artifact_base64": outcomes[2][
                "checkpoint_artifact_base64"
            ]
        }
    )
    assert suffix["path"]["attempts"][0]["committed"] is False
    assert suffix["path"]["attempts"][0]["rollback_exact"] is True
    assert verified["artifact_contract_pass"] is True
    assert verified["contract_pass"] is False
    assert verified["physical_path_complete"] is False
    assert verified["fresh_source_execution_invoked"] is True
    assert verified["solver_replay_performed"] is True
    assert verified["verified_result_hash"] == suffix["result_hash"]
    assert verified["errors"] == []
    work = [
        row["api_result"]["metrics"]["control_work"]
        if row["phase"] == "analysis"
        else row["verification_report"]["replay_control_work"]
        for row in outcomes
    ]
    assert [row["attempted_step_count"] for row in work] == [2, 2, 3, 3]
    assert all(row["unknown_solver_work_attempt_count"] == 0 for row in work)
    old = _retire_service(service)
    del service
    gc.collect()
    assert old() is None
    _assert_store_fds_released(directory / "store")
