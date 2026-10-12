"""Tiny actual v7 numerical work plus durable cutoff custody; no specimen claim."""

import json
import os
from pathlib import Path
import signal
import sqlite3
import sys

import pytest

from structural_analysis.api import rc_corotational_control as api
from structural_analysis.execution import rc_corotational_phase_supervisor as supervisor
from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.execution.rc_fiber_phase_supervisor import RCFiberPhaseError
from tests.test_rc_corotational_managed_restore import helpers, service


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux isolated phase profile"
)


def request(**policy_updates):
    payload = helpers.request()
    payload["schema_version"] = "structural-analysis-job-request.v7"
    payload["execution_config"].update(
        attempt_limit_per_call=2,
        maximum_api_invocations=6,
        phase_execution_policy={
            "schema_version": "bounded-rc-corotational-phase-execution-policy.v1",
            "analysis_timeout_ms": 60_000,
            "verification_timeout_ms": 60_000,
            "termination_grace_ms": 500,
            **policy_updates,
        },
    )
    return payload


def outcomes(current, job_id):
    evidence = current.read_rc_invocation_evidence(job_id, **helpers.TENANT)
    return [
        json.loads(
            current.read_rc_invocation_artifact(
                job_id, **helpers.TENANT, ordinal=row["ordinal"]
            )
        )
        for row in evidence["invocations"]
    ]


def assert_reaped(pid):
    assert pid != os.getpid()
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)
    # A reaped direct child no longer owns a /proc entry in this test observer.
    assert not Path(f"/proc/{pid}").exists()


def test_actual_isolated_managed_backup_restore_reopen_retains_unknown_spend(
    tmp_path, monkeypatch
):
    source, backup, restored = (
        tmp_path / name for name in ("source", "backup", "restored")
    )
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", source)
    current = service(source, execution_authority=authority, execution_binding=binding)
    payload = request()
    job = current.submit_job(
        **helpers.TENANT, idempotency_key="managed-v7", request=payload
    )
    assert (
        current.submit_job(
            **helpers.TENANT, idempotency_key="managed-v7", request=payload
        ).job_id
        == job.job_id
    )
    first = current.claim_next(**helpers.WORKER, lease_seconds=300)
    assert current.claim_next(**helpers.SECOND, lease_seconds=300) is None

    def forbid_parent_api(*args, **kwargs):
        pytest.fail("v7 parent called the numerical API")

    with monkeypatch.context() as patch:
        patch.setattr(api, "analyze_rc_corotational_control", forbid_parent_api)
        patch.setattr(
            api, "validate_rc_corotational_control_artifacts", forbid_parent_api
        )
        saved = execute_job_claim(current, first, **helpers.WORKER)
    assert saved.status == "checkpointed" and saved.progress_completed == 2
    retained = current.read_checkpoint(job.job_id, **helpers.TENANT)
    receipt = backup_job_store(source, backup, maximum_bytes=10_000_000)
    options = {
        "manifest_sha256": receipt["manifest_sha256"],
        "maximum_bytes": 10_000_000,
    }
    live = current.claim_next(**helpers.SECOND, lease_seconds=300)
    credentials = dict(helpers.SECOND, lease_token=live.lease_token)
    assert current.reserve_execution_attempt(job.job_id, **credentials) == 3
    restore_job_store(backup, restored, **options)
    with current.execution_guard():
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(backup, restored, **options)
    assert activate_managed_restore(backup, restored, **options)["generation"] == 2
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.heartbeat(job.job_id, **credentials)
    fresh = service(restored)
    assert fresh.read_checkpoint(job.job_id, **helpers.TENANT) == retained
    claim = fresh.claim_next(**helpers.SECOND, lease_seconds=300)
    before = fresh.read_rc_invocation_evidence(job.job_id, **helpers.TENANT)
    assert before["pending_ordinals"] == [3]
    next_root = tmp_path / "next-root"
    restore_job_store(backup, next_root, **options)
    original = supervisor.run_rc_corotational_phase
    guarded = []

    def guarded_phase(**kwargs):
        assert type(kwargs["authority_fd"]) is int
        os.fstat(kwargs["authority_fd"])
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(
                backup,
                next_root,
                **options,
                expected_generation=2,
                expected_root=str(restored),
            )
        reply = original(**kwargs)
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(
                backup,
                next_root,
                **options,
                expected_generation=2,
                expected_root=str(restored),
            )
        guarded.append(kwargs["phase"])
        return reply

    with monkeypatch.context() as patch:
        patch.setattr(supervisor, "run_rc_corotational_phase", guarded_phase)
        patch.setattr(api, "analyze_rc_corotational_control", forbid_parent_api)
        patch.setattr(
            api, "validate_rc_corotational_control_artifacts", forbid_parent_api
        )
        completed = execute_job_claim(fresh, claim, **helpers.SECOND)
    assert guarded == ["analysis", "verification"]
    assert completed.status == "succeeded"
    assert (completed.progress_completed, completed.progress_total) == (3, 255)
    evidence = fresh.read_rc_invocation_evidence(job.job_id, **helpers.TENANT)
    assert evidence["execution_budget"] == {
        "maximum_attempts": 6,
        "reserved_attempts": 5,
        "remaining_attempts": 1,
    }
    assert evidence["pending_ordinals"] == [3]
    observations = outcomes(fresh, job.job_id)
    assert [row["phase"] for row in observations] == [
        "analysis",
        "verification",
        "analysis",
        "verification",
    ]
    pids = []
    for row in observations:
        assert row["schema_version"] == "bounded-rc-corotational-job-invocation.v2"
        assert row["status"] == row["phase_supervision"]["status"] == "returned"
        assert row["phase_supervision"]["cleanup"] == {}
        summary = row["phase_supervision"]["supervisor"]
        assert (
            summary["direct_child_reaped"] is True and summary["child_returncode"] == 0
        )
        assert 0 <= row["timing"]["wall_ns"] <= summary["wall_ns"] <= 60_000_000_000
        assert type(row["timing"]["process_cpu_ns"]) is int
        assert_reaped(summary["child_pid"])
        pids.append(summary["child_pid"])
    assert len(set(pids)) == 4
    result = json.loads(fresh.read_result(job.job_id, **helpers.TENANT))
    assert [row["analysis_ordinal"] for row in result["receipts"]] == [1, 4]
    assert [row["verification_ordinal"] for row in result["receipts"]] == [2, 5]
    assert result["api_result"]["contract_pass"]
    assert fresh.validate_integrity(job.job_id, **helpers.TENANT)["contract_pass"]
    assert (
        service(restored).get_job(job.job_id, **helpers.TENANT).to_dict()
        == completed.to_dict()
    )
    with pytest.raises(JobServiceError, match="rc_quantity_job_unsupported"):
        fresh.create_rc_quantity_report(
            job.job_id,
            **helpers.TENANT,
            expected_request_hash=completed.request.content_hash,
            expected_result_artifact_hash=completed.result.content_hash,
            declared_prices=None,
        )


@pytest.mark.parametrize("phase,reserved", [("analysis", 1), ("verification", 2)])
def test_actual_phase_cutoff_keeps_spend_cleanup_and_unavailable_cpu(
    tmp_path, phase, reserved
):
    current = service(tmp_path / "store")
    payload = request(**{f"{phase}_timeout_ms": 200})
    job = current.submit_job(
        **helpers.TENANT, idempotency_key="cutoff", request=payload
    )
    claim = current.claim_next(**helpers.WORKER, lease_seconds=300)
    with pytest.raises(
        RCFiberPhaseError, match=f"rc_corotational_worker_{phase}_timeout"
    ):
        execute_job_claim(current, claim, **helpers.WORKER)
    view = current.get_job(job.job_id, **helpers.TENANT)
    assert view.status == "failed" and view.result is None and view.checkpoint is None
    evidence = current.read_rc_invocation_evidence(job.job_id, **helpers.TENANT)
    assert evidence["execution_budget"]["reserved_attempts"] == reserved
    recorded = outcomes(current, job.job_id)
    assert len(recorded) == reserved
    last = recorded[-1]
    assert last["phase"] == phase and last["status"] == "raised"
    assert last["unavailable_execution_work"] is True
    assert last["timing"]["process_cpu_ns"] is None
    assert last["phase_supervision"]["status"] == "unaccounted"
    assert (
        last["timing"]["wall_ns"] == last["phase_supervision"]["supervisor"]["wall_ns"]
    )
    cleanup = last["phase_supervision"]["cleanup"]
    if cleanup:
        assert cleanup["direct_child_reaped"] is True
        assert cleanup["signal_errors"] == [] and cleanup["ownership_lost"] is False
        assert_reaped(cleanup["pid"])
    # A deadline also covers request reconstruction before launch. No PID or
    # child-reaping claim is fabricated for a legitimate prelaunch timeout.
    (tmp_path / "cutoff-proof.json").write_text(
        json.dumps(
            {
                "phase": phase,
                "reserved_attempts": reserved,
                "process_cpu_ns": last["timing"]["process_cpu_ns"],
                "cleanup": cleanup,
                "independent_physical_validation": False,
            },
            indent=2,
        )
        + "\n"
    )
    assert current.validate_integrity(job.job_id, **helpers.TENANT)["contract_pass"]


def test_unsupported_host_rejects_before_reservation(tmp_path, monkeypatch):
    current = service(tmp_path / "store")
    job = current.submit_job(
        **helpers.TENANT, idempotency_key="unsupported", request=request()
    )
    claim = current.claim_next(**helpers.WORKER, lease_seconds=300)
    original = signal.getsignal
    monkeypatch.setattr(
        signal,
        "getsignal",
        lambda signum: signal.SIG_IGN if signum == signal.SIGCHLD else original(signum),
    )
    with pytest.raises(
        RCFiberPhaseError, match="rc_corotational_worker_analysis_unsupported"
    ):
        execute_job_claim(current, claim, **helpers.WORKER)
    evidence = current.read_rc_invocation_evidence(job.job_id, **helpers.TENANT)
    assert evidence["execution_budget"]["reserved_attempts"] == 0
    assert evidence["invocations"] == []
    assert current.get_job(job.job_id, **helpers.TENANT).status == "failed"


def test_v7_storage_budget_rejects_before_any_job_blob_or_reservation(tmp_path):
    current = service(tmp_path / "store", max_blob_payload_bytes=1)
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        current.submit_job(
            **helpers.TENANT, idempotency_key="too-large", request=request()
        )
    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as db:
        for table in ("jobs", "job_execution_budgets", "job_events"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert list((tmp_path / "store" / "blobs").glob("*/*")) == []
