"""Actual tiny v6 work through external generation fencing; no specimen claim."""

import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from structural_analysis.api import rc_corotational_control as api
from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from structural_analysis.execution.job_worker import execute_job_claim

_spec = importlib.util.spec_from_file_location(
    "managed_corotational_helpers",
    Path(__file__).with_name("test_rc_corotational_durable_worker.py"),
)
helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helpers)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux managed authority"
)


def service(path, **options):
    return DurableJobService(
        path,
        max_blob_payload_bytes=options.pop("max_blob_payload_bytes", 10_000_000),
        tenant_tokens={"tenant": helpers.TENANT["authorization_token"]},
        worker_tokens={
            "worker": helpers.WORKER["authorization_token"],
            "second": helpers.SECOND["authorization_token"],
        },
        worker_tenants={"worker": {"tenant"}, "second": {"tenant"}},
        **options,
    )


def test_managed_old_backup_keeps_unknown_spend_and_fences_old_source(
    tmp_path, monkeypatch
):
    source, backup, restored = (
        tmp_path / name for name in ("source", "backup", "restored")
    )
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", source)
    current = service(source, execution_authority=authority, execution_binding=binding)
    payload = helpers.request()
    payload["execution_config"].update(
        attempt_limit_per_call=2, maximum_api_invocations=6
    )
    job = current.submit_job(
        **helpers.TENANT, idempotency_key="managed-v6", request=payload
    )
    first = current.claim_next(**helpers.WORKER, lease_seconds=300)
    saved = execute_job_claim(current, first, **helpers.WORKER)
    assert saved.status == "checkpointed" and saved.progress_completed == 2
    retained_checkpoint = current.read_checkpoint(job.job_id, **helpers.TENANT)
    receipt = backup_job_store(source, backup, maximum_bytes=10_000_000)
    options = dict(manifest_sha256=receipt["manifest_sha256"], maximum_bytes=10_000_000)
    # Reservation 3 is spent after the backup, with execution explicitly unknown.
    live = current.claim_next(**helpers.SECOND, lease_seconds=300)
    credentials = dict(helpers.SECOND, lease_token=live.lease_token)
    assert current.reserve_execution_attempt(job.job_id, **credentials) == 3
    restore_job_store(backup, restored, **options)
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(restored)
    with current.execution_guard():
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(backup, restored, **options)
    assert activate_managed_restore(backup, restored, **options)["generation"] == 2
    for operation in (current.heartbeat, current.reserve_execution_attempt):
        with pytest.raises(JobServiceError, match="execution_authority_rejected"):
            operation(job.job_id, **credentials)
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(source)
    fresh = service(restored)
    assert fresh.read_checkpoint(job.job_id, **helpers.TENANT) == retained_checkpoint
    claim = fresh.claim_next(**helpers.SECOND, lease_seconds=300)
    assert claim.job.progress_completed == 2
    evidence = fresh.read_rc_invocation_evidence(job.job_id, **helpers.TENANT)
    assert evidence["pending_ordinals"] == [3]
    assert evidence["execution_budget"]["reserved_attempts"] == 3
    assert fresh.claim_next(**helpers.WORKER, lease_seconds=300) is None
    next_root = tmp_path / "next-restored"
    restore_job_store(backup, next_root, **options)
    # A cutover attempted from inside each real analysis/replay must be blocked
    # by the v6 worker's guard for its entire invocation/publication lifetime.
    original_analysis = api.analyze_rc_corotational_control
    guarded_calls = []

    def guarded_analysis(*args, **kwargs):
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(
                backup,
                next_root,
                **options,
                expected_generation=2,
                expected_root=str(restored),
            )
        guarded_calls.append(True)
        return original_analysis(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(api, "analyze_rc_corotational_control", guarded_analysis)
        completed = execute_job_claim(fresh, claim, **helpers.SECOND)
    assert len(guarded_calls) == 2  # analysis and mandatory fresh verification
    assert completed.status == "succeeded"
    assert (completed.progress_completed, completed.progress_total) == (3, 255)
    evidence = fresh.read_rc_invocation_evidence(job.job_id, **helpers.TENANT)
    assert evidence["execution_budget"] == {
        "maximum_attempts": 6,
        "reserved_attempts": 5,
        "remaining_attempts": 1,
    }
    assert evidence["pending_ordinals"] == [3]
    result = json.loads(fresh.read_result(job.job_id, **helpers.TENANT))
    assert [row["analysis_ordinal"] for row in result["receipts"]] == [1, 4]
    assert [row["verification_ordinal"] for row in result["receipts"]] == [2, 5]
    assert result["api_result"]["contract_pass"]
    assert (
        service(restored).get_job(job.job_id, **helpers.TENANT).to_dict()
        == completed.to_dict()
    )
    assert fresh.validate_integrity(job.job_id, **helpers.TENANT)["contract_pass"]


def test_managed_v6_rejects_storage_budget_before_job_or_reservation(tmp_path):
    source = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", source)
    current = service(
        source,
        execution_authority=authority,
        execution_binding=binding,
        max_blob_payload_bytes=1,
    )
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        current.submit_job(
            **helpers.TENANT,
            idempotency_key="insufficient-store",
            request=helpers.request(),
        )
    with sqlite3.connect(source / "jobs.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert (
            connection.execute("SELECT count(*) FROM job_execution_budgets").fetchone()[
                0
            ]
            == 0
        )
        assert connection.execute("SELECT count(*) FROM job_events").fetchone()[0] == 0
    assert list((source / "blobs").glob("*/*")) == []
