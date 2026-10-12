"""New storage-only RC recovery checks; no worker or numerical API execution."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution import rc_fiber_job_contract as contract
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)

TENANT = "recovery-limit-tenant-0123456789"
WORKER = "recovery-limit-worker-0123456789"
LIMIT = 1024 * 1024


@pytest.fixture(autouse=True)
def prohibit_numerics(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("storage recovery must not call numerical analysis")

    for name in [
        "analyze_bounded_rc_fiber_direct_control",
        "validate_bounded_rc_fiber_direct_control_artifacts",
        "run_stateful_fiber_frame2d_control_path",
    ]:
        monkeypatch.setattr(api, name, forbidden)


def open_store(root, clock, cap=None):
    return DurableJobService(
        root,
        tenant_tokens={"tenant": TENANT},
        worker_tokens={"worker": WORKER},
        clock=lambda: clock[0],
        max_blob_payload_bytes=cap,
    )


def request():
    return {
        "schema_version": contract.RC_FIBER_JOB_REQUEST_SCHEMA_VERSION,
        "operation": contract.RC_FIBER_JOB_OPERATION,
        "case_id": "new-storage-recovery-reservation",
        "model": json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "examples/public_rc_fiber_frame_l_frame_material_history.json"
            ).read_bytes()
        ),
        "config": BoundedRCFiberDirectControlRequest(7, (-0.0001,)).to_dict(),
        "source_revision": "b" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 2},
    }


def copy_store(original, tmp_path):
    receipt = backup_job_store(
        original.root, tmp_path / "backup", maximum_bytes=10 * LIMIT
    )
    restored = tmp_path / "restored"
    restore_job_store(
        tmp_path / "backup",
        restored,
        manifest_sha256=receipt["manifest_sha256"],
        maximum_bytes=10 * LIMIT,
    )
    return restored


def test_recovery_does_not_refill_rc_invocation_budget(tmp_path):
    clock = [datetime(2026, 10, 8, tzinfo=timezone.utc)]
    original = open_store(tmp_path / "source", clock)
    tenant = dict(tenant_id="tenant", authorization_token=TENANT)
    worker = dict(worker_id="worker", authorization_token=WORKER)
    job = original.submit_job(
        **tenant, idempotency_key="recovery-budget", request=request()
    )
    first = original.claim_next(**worker, lease_seconds=5)
    assert first is not None
    assert (
        original.reserve_execution_attempt(
            job.job_id, **worker, lease_token=first.lease_token
        )
        == 1
    )
    assert (
        original.reserve_execution_attempt(
            job.job_id, **worker, lease_token=first.lease_token
        )
        == 2
    )
    before = original.read_execution_budget(
        job.job_id, **worker, lease_token=first.lease_token
    )
    restored = open_store(copy_store(original, tmp_path), clock)
    restored.validate_integrity(job.job_id, **tenant)
    clock[0] += timedelta(seconds=6)
    claimed = restored.claim_next(**worker)
    assert claimed is not None
    assert (
        restored.read_execution_budget(
            job.job_id, **worker, lease_token=claimed.lease_token
        )
        == before
    )
    assert before["remaining_attempts"] == 0
    with pytest.raises(JobServiceError) as exc:
        restored.reserve_execution_attempt(
            job.job_id, **worker, lease_token=claimed.lease_token
        )
    assert exc.value.code == "execution_attempt_budget_exhausted"
    restored.validate_integrity(job.job_id, **tenant)
    with sqlite3.connect(original.root / "jobs.sqlite3") as db:
        assert db.execute(
            "SELECT reserved_attempts FROM job_execution_budgets"
        ).fetchall() == [(2,)]


def test_recovery_preserves_immutable_payload_policy_and_rejects_replacement(tmp_path):
    clock = [datetime(2026, 10, 8, tzinfo=timezone.utc)]
    original = open_store(tmp_path / "source", clock, LIMIT)
    restored_root = copy_store(original, tmp_path)
    restored = open_store(restored_root, clock)
    with sqlite3.connect(restored.root / "jobs.sqlite3") as db:
        assert db.execute(
            "SELECT maximum_bytes FROM job_blob_payload_policy"
        ).fetchall() == [(LIMIT,)]
    with pytest.raises(JobServiceError) as exc:
        open_store(restored_root, clock, 2 * LIMIT)
    assert exc.value.code == "blob_payload_budget_conflict"
    with sqlite3.connect(restored.root / "jobs.sqlite3") as db:
        assert db.execute(
            "SELECT maximum_bytes FROM job_blob_payload_policy"
        ).fetchall() == [(LIMIT,)]
