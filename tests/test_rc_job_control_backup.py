"""Control custody after byte backup/restore; no solver or external execution."""

import json
import sqlite3

import pytest

from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
    _event_hash,
)
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from tests.test_rc_fiber_job_service import (
    Clock,
    OTHER,
    TENANT,
    WORKER,
    WORKER_B,
    canonical,
    claim,
    lease,
    no_solver as no_solver,
    service,
    sha,
    submit,
    tenant,
)
from tests.test_rc_job_control_http import command, read_control, send_control


def roundtrip(current, tmp_path):
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    receipt = backup_job_store(current.root, backup, maximum_bytes=10_000_000)
    options = {
        "manifest_sha256": receipt["manifest_sha256"],
        "maximum_bytes": 10_000_000,
    }
    result = restore_job_store(backup, restored, **options)
    # Copying verified bytes is separate from application admission on reopen.
    assert result["application_integrity_checked"] is False
    return backup, restored, options


def managed_service(root, clock, **kwargs):
    return DurableJobService(
        root,
        tenant_tokens={"a": TENANT, "b": OTHER},
        worker_tokens={"worker-a": WORKER, "worker-b": WORKER_B},
        worker_tenants={"worker-a": {"a"}, "worker-b": {"a", "b"}},
        clock=clock,
        **kwargs,
    )


def test_paused_queue_roundtrip_preserves_identity_and_hold(tmp_path):
    current = service(tmp_path / "source")
    job = submit(current)
    paused = send_control(current, job, command(read_control(current, job)))
    before = current.get_job(job.job_id, **tenant()).to_dict()
    integrity = current.validate_integrity(job.job_id, **tenant())
    _, restored, _ = roundtrip(current, tmp_path)
    fresh = service(restored)
    assert fresh.get_job(job.job_id, **tenant()).to_dict() == before
    assert fresh.validate_integrity(job.job_id, **tenant()) == integrity
    assert read_control(fresh, job) == paused["view"]
    assert (
        fresh.claim_next(
            worker_id="worker-a", authorization_token=WORKER, lease_seconds=5
        )
        is None
    )
    resumed = send_control(fresh, job, command(paused["view"], "resume"))
    assert resumed["view"]["state"] == "available"
    acquired = claim(fresh)
    assert acquired.job.job_id == job.job_id
    assert acquired.request_bytes == canonical(json.loads(acquired.request_bytes))
    assert acquired.job.request == job.request
    assert acquired.job.attempt == 1


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_managed_pending_restore_preserves_post_snapshot_unknown_spend(
    tmp_path, action
):
    clock = Clock()
    source = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", source)
    current = managed_service(
        source, clock, execution_authority=authority, execution_binding=binding
    )
    job = submit(current)
    acquired = claim(current)
    assert current.reserve_execution_attempt(job.job_id, **lease(acquired)) == 1
    pending = send_control(current, job, command(read_control(current, job), action))
    assert pending["view"]["state"] == f"{action}_pending"
    backup, restored, options = roundtrip(current, tmp_path)
    # Emulate a reservation committed to the authority before a worker crash,
    # without a local outcome or a fabricated numerical result.
    authority.reserve(binding, job.job_id, job.request.content_hash)
    activated = activate_managed_restore(backup, restored, **options)
    assert activated["status"] == "activated"
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.claim_next(
            worker_id="worker-a", authorization_token=WORKER, lease_seconds=5
        )
    fresh = managed_service(restored, clock)
    assert read_control(fresh, job)["state"] == f"{action}_pending"
    clock.advance()
    assert (
        fresh.claim_next(
            worker_id="worker-a", authorization_token=WORKER, lease_seconds=5
        )
        is None
    )
    recovered = read_control(fresh, job)
    assert recovered["state"] == ("paused" if action == "pause" else "terminal")
    assert recovered["last_command"]["boundary"] == "lease_expired"
    assert recovered["last_command"]["control_id"] == pending["control_id"]
    # This existing explicit operation imports authority-only reservations;
    # neither metadata GET nor a held claim invents an outcome for them.
    fresh.reconcile_execution_reservations(job.job_id, **tenant())
    evidence = fresh.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["execution_budget"]["reserved_attempts"] == 2
    assert evidence["pending_ordinals"] == [1, 2]
    assert evidence["invocations"] == []
    assert fresh.get_job(job.job_id, **tenant()).request == job.request
    assert fresh.validate_integrity(job.job_id, **tenant())["contract_pass"]
    if action == "pause":
        send_control(fresh, job, command(recovered, "resume"))
        second = claim(fresh)
        assert second.job.attempt == 2
        assert second.job.job_id == job.job_id
        assert (
            fresh.read_execution_budget(job.job_id, **lease(second))[
                "reserved_attempts"
            ]
            == 2
        )


def test_coherently_rehashed_impossible_control_is_rejected_after_byte_restore(
    tmp_path,
):
    current = service(tmp_path / "source")
    job = submit(current)
    send_control(current, job, command(read_control(current, job)))
    with sqlite3.connect(current.root / "jobs.sqlite3") as db:
        db.row_factory = sqlite3.Row
        events = db.execute(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY revision", (job.job_id,)
        ).fetchall()
        previous = None
        for event in events:
            payload = json.loads(event["payload_json"])
            if event["event_type"] == "rc_control_requested":
                # Queue attempt was zero. Update the command digest and the
                # whole outer chain too: byte consistency cannot make this
                # historically impossible CAS admissible.
                payload["command"]["expected_attempt"] = 1
                payload["command_hash"] = sha(canonical(payload["command"]))
            digest, serialized = _event_hash(
                job_id=job.job_id,
                revision=event["revision"],
                event_type=event["event_type"],
                status=event["status"],
                occurred_at=event["occurred_at"],
                payload=payload,
                previous_event_hash=previous,
            )
            db.execute(
                "UPDATE job_events SET payload_json=?, previous_event_hash=?, event_hash=? WHERE job_id=? AND revision=?",
                (serialized, previous, digest, job.job_id, event["revision"]),
            )
            previous = digest
        db.execute(
            "UPDATE jobs SET terminal_event_hash=? WHERE job_id=?",
            (previous, job.job_id),
        )
    _, restored, _ = roundtrip(current, tmp_path)
    fresh = service(restored)
    for operation in (
        lambda: fresh.get_rc_control(job.job_id, **tenant()),
        lambda: fresh.validate_integrity(job.job_id, **tenant()),
        lambda: fresh.claim_next(
            worker_id="worker-a", authorization_token=WORKER, lease_seconds=5
        ),
    ):
        with pytest.raises(JobServiceError, match="rc_control_integrity_failed"):
            operation()
    with sqlite3.connect(restored / "jobs.sqlite3") as db:
        assert db.execute(
            "SELECT status, attempt FROM jobs WHERE job_id=?", (job.job_id,)
        ).fetchone() == ("queued", 0)
