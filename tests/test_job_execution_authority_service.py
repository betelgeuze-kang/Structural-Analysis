"""Managed binding, conservative shared reservations and real RC execution."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from tests.test_rc_real_process_lifecycle import (
    TENANTS,
    WORKERS,
    request,
    tenant,
    worker,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux authority")


def service(root, **kwargs):
    return DurableJobService(
        root, tenant_tokens=TENANTS, worker_tokens=WORKERS, **kwargs
    )


def test_worker_reservation_crash_preserves_external_spend_and_next_ordinal(
    tmp_path, monkeypatch
):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(**tenant(), idempotency_key="first", request=request())
    claim = current.claim_next(**worker("first"), lease_seconds=60)
    transition = current._transition

    def interrupted(*args, **kwargs):
        if kwargs["event_type"] == "execution_attempt_reserved":
            raise RuntimeError("local reservation commit interrupted")
        return transition(*args, **kwargs)

    monkeypatch.setattr(current, "_transition", interrupted)
    with pytest.raises(RuntimeError, match="local reservation commit interrupted"):
        current.reserve_execution_attempt(
            job.job_id, **worker("first"), lease_token=claim.lease_token
        )
    reopened = service(root)
    budget = reopened.read_execution_budget(
        job.job_id, **worker("first"), lease_token=claim.lease_token
    )
    assert budget["reserved_attempts"] == 1
    assert (
        reopened.reserve_execution_attempt(
            job.job_id, **worker("first"), lease_token=claim.lease_token
        )
        == 2
    )
    evidence = reopened.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["pending_ordinals"] == [1, 2]
    assert evidence["invocations"] == []
    with reopened._transaction() as db:
        row = reopened._job_row(db, job.job_id)
        # Ordinal 1 has no fabricated lease; real lease reservation retains 2.
        assert list(reopened._rc_reservations(db, row)) == [2]


@pytest.mark.parametrize("orphaned", [0, 1])
@pytest.mark.parametrize("isolated", [False, True])
def test_managed_real_worker_completes_two_chunks_with_shared_budget(
    tmp_path, orphaned, isolated
):
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        execute_rc_fiber_direct_control_claim,
    )

    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    authored = request()
    if isolated:
        authored["execution_config"]["phase_execution_policy"] = {
            "schema_version": "bounded-rc-fiber-phase-execution-policy.v1",
            "analysis_timeout_ms": 30_000,
            "verification_timeout_ms": 30_000,
            "termination_grace_ms": 50,
        }
    job = current.submit_job(**tenant(), idempotency_key="first", request=authored)
    if orphaned:
        current.reconcile_execution_reservations(job.job_id, **tenant())
        with sqlite3.connect(root / "jobs.sqlite3") as db:
            request_hash = db.execute("SELECT request_hash FROM jobs").fetchone()[0]
        authority.reserve(binding, job.job_id, request_hash)
    for expected in ("checkpointed", "succeeded"):
        current = service(root)
        claim = current.claim_next(**worker("first"), lease_seconds=60)
        result = execute_rc_fiber_direct_control_claim(
            current, claim, **worker("first"), lease_seconds=60
        )
        assert result.status == expected
    evidence = current.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["execution_budget"]["reserved_attempts"] == 4 + orphaned
    assert len(evidence["invocations"]) == 4
    assert evidence["pending_ordinals"] == ([1] if orphaned else [])
    shared = authority.read_budget(binding, job.job_id, evidence["job_request_hash"])
    assert shared["reserved_attempts"] == 4 + orphaned
    assert shared["remaining_attempts"] == 4 - orphaned
    if isolated:
        for invocation in evidence["invocations"]:
            outcome = json.loads(
                current.read_rc_invocation_artifact(
                    job.job_id, **tenant(), ordinal=invocation["ordinal"]
                )
            )
            assert outcome["status"] == "returned"
            assert outcome["timing"]["process_cpu_ns"] > 0


def test_orphan_authority_spend_is_imported_as_unknown_without_lease_history(tmp_path):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(**tenant(), idempotency_key="first", request=request())
    initial = current.reconcile_execution_reservations(job.job_id, **tenant())
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        request_hash = db.execute("SELECT request_hash FROM jobs").fetchone()[0]
    assert authority.reserve(binding, job.job_id, request_hash) == 1
    assert authority.reserve(binding, job.job_id, request_hash) == 2
    reopened = service(root)
    reconciled = reopened.reconcile_execution_reservations(job.job_id, **tenant())
    assert reconciled == {
        "maximum_attempts": initial["maximum_attempts"],
        "reserved_attempts": 2,
        "remaining_attempts": initial["maximum_attempts"] - 2,
    }
    evidence = reopened.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["pending_ordinals"] == [1, 2]
    assert evidence["pending_execution_work"] == "unknown"
    assert evidence["invocations"] == []
    assert reopened.get_job(job.job_id, **tenant()).attempt == 0
    assert (
        reopened.reconcile_execution_reservations(job.job_id, **tenant()) == reconciled
    )
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        assert (
            db.execute(
                "SELECT count(*) FROM job_events WHERE event_type='execution_authority_reservation_imported'"
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM job_events WHERE event_type='execution_attempt_reserved'"
            ).fetchone()[0]
            == 0
        )


def test_reconciliation_interruption_rolls_back_local_history_without_refund(
    tmp_path, monkeypatch
):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(**tenant(), idempotency_key="first", request=request())
    current.reconcile_execution_reservations(job.job_id, **tenant())
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        request_hash = db.execute("SELECT request_hash FROM jobs").fetchone()[0]
    authority.reserve(binding, job.job_id, request_hash)
    transition = current._transition

    def interrupted(*args, **kwargs):
        transition(*args, **kwargs)
        raise RuntimeError("interrupted import")

    monkeypatch.setattr(current, "_transition", interrupted)
    with pytest.raises(RuntimeError, match="interrupted import"):
        current.reconcile_execution_reservations(job.job_id, **tenant())
    assert (
        authority.read_budget(binding, job.job_id, request_hash)["reserved_attempts"]
        == 1
    )
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        assert (
            db.execute(
                "SELECT reserved_attempts FROM job_execution_budgets"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM job_events WHERE event_type='execution_authority_reservation_imported'"
            ).fetchone()[0]
            == 0
        )
    assert (
        service(root).reconcile_execution_reservations(job.job_id, **tenant())[
            "reserved_attempts"
        ]
        == 1
    )


@pytest.mark.parametrize(
    "replacement",
    [
        "json_set(payload_json, '$.execution_work', 'completed')",
        "json_set(payload_json, '$.authority_generation', json('true'))",
        "json_set(payload_json, '$.worker_id', 'invented-worker')",
    ],
)
def test_imported_spend_is_checked_against_external_journal(tmp_path, replacement):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(**tenant(), idempotency_key="first", request=request())
    current.reconcile_execution_reservations(job.job_id, **tenant())
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        request_hash = db.execute("SELECT request_hash FROM jobs").fetchone()[0]
    authority.reserve(binding, job.job_id, request_hash)
    current.reconcile_execution_reservations(job.job_id, **tenant())
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        db.execute(
            f"UPDATE job_events SET payload_json={replacement} WHERE event_type='execution_authority_reservation_imported'"
        )
    with pytest.raises(JobServiceError, match="execution_budget_integrity_failed"):
        current.read_rc_invocation_evidence(job.job_id, **tenant())


def test_binding_reopens_automatically_and_stale_instance_cannot_write(tmp_path):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    first = service(root, execution_authority=authority, execution_binding=binding)
    job = first.submit_job(**tenant(), idempotency_key="first", request=request())
    second = service(root)  # Omitting constructor options cannot disable protection.
    assert second.get_job(job.job_id, **tenant()).job_id == job.job_id
    assert (
        second.claim_next(**worker("first"), lease_seconds=60).job.job_id == job.job_id
    )
    authority.activate(binding, tmp_path / "restored")
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        first.submit_job(**tenant(), idempotency_key="stale", request=request())
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(root)


def test_backup_carries_binding_and_restored_copy_cannot_open_as_unmanaged(tmp_path):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    current.submit_job(**tenant(), idempotency_key="first", request=request())
    sealed, restored = tmp_path / "sealed", tmp_path / "restored"
    receipt = backup_job_store(root, sealed, maximum_bytes=10 * 1024 * 1024)
    restore_job_store(
        sealed,
        restored,
        manifest_sha256=receipt["manifest_sha256"],
        maximum_bytes=10 * 1024 * 1024,
    )
    before = hashlib.sha256((restored / "jobs.sqlite3").read_bytes()).hexdigest()
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(restored)
    assert (
        hashlib.sha256((restored / "jobs.sqlite3").read_bytes()).hexdigest() == before
    )


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE job_execution_authority_binding",
        "DELETE FROM job_execution_authority_binding",
        "PRAGMA application_id=0",
    ],
)
def test_incomplete_binding_does_not_fall_back_to_unmanaged(tmp_path, sql):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    service(root, execution_authority=authority, execution_binding=binding)
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        db.execute(sql)
    with pytest.raises(JobServiceError, match="execution_authority_invalid"):
        service(root)


def test_existing_store_cannot_be_silently_adopted(tmp_path):
    root = tmp_path / "source"
    service(root)
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    with pytest.raises(JobServiceError, match="execution_authority_adoption_required"):
        service(root, execution_authority=authority, execution_binding=binding)


def test_failed_enrollment_is_quarantined_not_reopened_unmanaged(tmp_path, monkeypatch):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    initialize = DurableJobService._initialize_database

    def fail_after_schema(self):
        initialize(self)
        raise RuntimeError("injected enrollment interruption")

    monkeypatch.setattr(DurableJobService, "_initialize_database", fail_after_schema)
    with pytest.raises(RuntimeError, match="injected"):
        service(root, execution_authority=authority, execution_binding=binding)
    assert not root.exists()
    staged = list(tmp_path.glob(".job-store-enroll-*"))
    assert len(staged) == 1
    assert (staged[0] / ".job-store-authority.pending").is_file()
    monkeypatch.setattr(DurableJobService, "_initialize_database", initialize)
    with pytest.raises(JobServiceError, match="job_store_not_activated"):
        service(staged[0])
    with pytest.raises(ValueError, match="not an active-store"):
        backup_job_store(staged[0], tmp_path / "backup", maximum_bytes=10 * 1024 * 1024)


@pytest.mark.parametrize("competing_store", [False, True])
def test_enrollment_never_overwrites_competing_destination(
    tmp_path, monkeypatch, competing_store
):
    from structural_analysis.execution import job_service

    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    install = job_service.install_new_store
    saved = {}

    def compete(staging, destination):
        assert not destination.exists()
        if competing_store:
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; from tests.test_job_execution_authority_service import service; service(sys.argv[1])",
                    str(destination),
                ],
                check=True,
                timeout=10,
            )
            saved["database"] = (destination / "jobs.sqlite3").read_bytes()
        else:
            destination.mkdir()
        return install(staging, destination)

    monkeypatch.setattr(job_service, "install_new_store", compete)
    with pytest.raises(JobServiceError, match="execution_authority_install_failed"):
        service(root, execution_authority=authority, execution_binding=binding)
    if competing_store:
        assert (root / "jobs.sqlite3").read_bytes() == saved["database"]
    else:
        assert list(root.iterdir()) == []
    staged = list(tmp_path.glob(".job-store-enroll-*"))
    assert len(staged) == 1
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(staged[0])


def test_phase_child_receives_authority_descriptor(tmp_path, monkeypatch):
    from structural_analysis.execution import rc_fiber_phase_supervisor as supervisor
    from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy
    from tests.test_rc_fiber_phase_supervisor import (
        _script,
        _write_reply_code,
        _request_bytes,
    )

    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    policy = RCFiberPhasePolicy(5000, 5000, 100)
    with authority.execution(binding) as fd:
        identity = os.fstat(fd)
        body = f"s=os.fstat({fd}); assert (s.st_dev,s.st_ino)=={(identity.st_dev, identity.st_ino)!r}"
        _script(tmp_path, monkeypatch, _write_reply_code(body=body))
        reply = supervisor.run_rc_fiber_phase(
            phase="analysis",
            request_bytes=_request_bytes(policy),
            completed_before=0,
            completed_after=1,
            restart=None,
            policy=policy,
            lease_check=lambda: None,
            authority_fd=fd,
        )
        assert reply.status == "returned"
        assert reply.supervisor_timing["direct_child_reaped"]


@pytest.mark.parametrize("fd", [True, -1, 0, 2**40])
def test_invalid_authority_descriptor_never_launches_child(monkeypatch, fd):
    from structural_analysis.execution import rc_fiber_phase_supervisor as supervisor
    from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy

    def forbidden(*args, **kwargs):
        pytest.fail("invalid descriptor must fail before child launch")

    monkeypatch.setattr(supervisor.subprocess, "Popen", forbidden)
    with pytest.raises(supervisor.RCFiberPhaseError, match="authority"):
        supervisor.run_rc_fiber_phase(
            phase="analysis",
            request_bytes=b"{}",
            completed_before=0,
            completed_after=1,
            restart=None,
            policy=RCFiberPhasePolicy(5000, 5000, 100),
            lease_check=lambda: None,
            authority_fd=fd,
        )
