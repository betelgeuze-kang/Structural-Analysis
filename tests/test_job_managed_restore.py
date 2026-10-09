"""Managed restore activation: real execution, old snapshots and interrupted cutover."""

import json
import gc
import hashlib
import selectors
import sqlite3
import subprocess
import sys

import pytest

from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)
from tests.test_job_execution_authority_service import service
from tests.test_rc_real_process_lifecycle import request, tenant, worker

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux managed restore")


def setup_store(tmp_path, *, checkpoint=False):
    source, backup, restored = (
        tmp_path / name for name in ("source", "backup", "restored")
    )
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", source)
    current = service(source, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(**tenant(), idempotency_key="first", request=request())
    if checkpoint:
        claim = current.claim_next(**worker("first"), lease_seconds=60)
        assert (
            execute_rc_fiber_direct_control_claim(
                current, claim, **worker("first"), lease_seconds=60
            ).status
            == "checkpointed"
        )
    receipt = backup_job_store(source, backup, maximum_bytes=10_000_000)
    options = {
        "manifest_sha256": receipt["manifest_sha256"],
        "maximum_bytes": 10_000_000,
    }
    restore_job_store(backup, restored, **options)
    return current, authority, binding, job, backup, restored, options


@pytest.mark.parametrize("checkpoint", [False, True])
def test_old_snapshot_preserves_spend_and_fences_source(tmp_path, checkpoint):
    current, authority, binding, job, backup, restored, options = setup_store(
        tmp_path, checkpoint=checkpoint
    )
    claim = current.claim_next(**worker("first"), lease_seconds=60)
    assert execute_rc_fiber_direct_control_claim(
        current, claim, **worker("first"), lease_seconds=60
    ).status == ("succeeded" if checkpoint else "checkpointed")
    assert (
        activate_managed_restore(backup, restored, **options)["status"] == "activated"
    )
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.claim_next(**worker("first"), lease_seconds=60)
    for expected in ("succeeded",) if checkpoint else ("checkpointed", "succeeded"):
        fresh = service(restored)
        claim = fresh.claim_next(**worker("first"), lease_seconds=60)
        if checkpoint:
            assert claim.job.progress_completed == 1
            assert claim.checkpoint_bytes is not None
        assert (
            execute_rc_fiber_direct_control_claim(
                fresh, claim, **worker("first"), lease_seconds=60
            ).status
            == expected
        )
    evidence = fresh.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["pending_ordinals"] == ([3, 4] if checkpoint else [1, 2])
    assert evidence["execution_budget"]["reserved_attempts"] == 6
    assert len(evidence["invocations"]) == 4
    final = fresh.get_job(job.job_id, **tenant()).to_dict()
    report = fresh.create_rc_quantity_report(
        job.job_id,
        **tenant(),
        declared_prices=None,
        expected_request_hash=evidence["job_request_hash"],
        expected_result_artifact_hash=final["result"]["content_hash"],
    )
    assert service(restored).read_rc_quantity_report(
        job.job_id, report["report_id"], **tenant()
    ) == fresh.read_rc_quantity_report(job.job_id, report["report_id"], **tenant())
    assert (
        activate_managed_restore(backup, restored, **options)["status"]
        == "already_activated"
    )


def test_older_generation_backup_requires_explicit_current_binding(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    activate_managed_restore(backup, restored, **options)
    third = tmp_path / "third"
    restore_job_store(backup, third, **options)
    with pytest.raises(ValueError, match="stale or invalid"):
        activate_managed_restore(backup, third, **options)
    result = activate_managed_restore(
        backup, third, **options, expected_generation=2, expected_root=str(restored)
    )
    assert result["generation"] == 3
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(restored)
    assert service(third).claim_next(**worker("first"), lease_seconds=60)


def test_active_execution_prevents_cutover(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    with current.execution_guard():
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(backup, restored, **options)
    assert current.claim_next(**worker("first"), lease_seconds=60) is not None


def test_fenced_read_does_not_reconfigure_original_database(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    activate_managed_restore(backup, restored, **options)
    gc.collect()
    # Deliberately choose DELETE in this disposable stale store. A query must not
    # restore WAL after the authority has switched to a different active root.
    database = current.root / "jobs.sqlite3"
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",)
    db.close()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.get_job(job.job_id, **tenant())
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    db.close()


def test_connection_configuration_holds_execution_authority(tmp_path, monkeypatch):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    original = current._open_configured_connection
    observed = []

    def configured():
        with pytest.raises(ValueError, match="authority busy"):
            authority.activate(binding, restored)
        observed.append(True)
        return original()

    monkeypatch.setattr(current, "_open_configured_connection", configured)
    assert current.get_job(job.job_id, **tenant()).job_id == job.job_id
    assert observed == [True]


def test_changed_destination_is_rejected_before_source_is_fenced(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    with sqlite3.connect(restored / "jobs.sqlite3") as db:
        db.execute("UPDATE jobs SET attempt=100")
    with pytest.raises(ValueError, match="restored member differs"):
        activate_managed_restore(backup, restored, **options)
    assert current.claim_next(**worker("first"), lease_seconds=60) is not None


@pytest.mark.parametrize("after_update", [False, True])
def test_process_death_after_external_commit_is_recoverable_without_two_active_roots(
    tmp_path,
    after_update,
):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    program = """
import os, sqlite3, sys, json
from structural_analysis.execution.job_managed_restore import activate_managed_restore
original = sqlite3.connect
class Interrupted(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        if sql.startswith("UPDATE job_execution_authority_binding SET"):
            if sys.argv[4] == "after":
                super().execute(sql, *args, **kwargs)
            os._exit(23)
        return super().execute(sql, *args, **kwargs)
def connect(path, *args, **kwargs):
    if str(path).startswith(sys.argv[2]):
        kwargs["factory"] = Interrupted
    return original(path, *args, **kwargs)
sqlite3.connect = connect
activate_managed_restore(sys.argv[1], sys.argv[2], **json.loads(sys.argv[3]))
"""
    # SQLite target connection uses a URI; match that exact observed root URI.
    program = program.replace(
        "str(path).startswith(sys.argv[2])",
        'str(path).startswith(__import__("pathlib").Path(sys.argv[2]).as_uri())',
    )
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(backup),
            str(restored),
            json.dumps(options),
            "after" if after_update else "before",
        ],
        timeout=30,
        capture_output=True,
        text=True,
    )
    assert child.returncode == 23, child.stderr
    for root in (current.root, restored):
        with pytest.raises(JobServiceError, match="execution_authority_rejected"):
            service(root)
    assert (
        activate_managed_restore(backup, restored, **options)["status"] == "activated"
    )
    assert service(restored).claim_next(**worker("first"), lease_seconds=60) is not None


def test_activation_cli_runs_and_retries_without_starting_worker(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    command = [
        sys.executable,
        "-m",
        "structural_analysis.execution.job_managed_restore_cli",
        str(backup),
        str(restored),
        "--manifest-sha256",
        options["manifest_sha256"],
        "--maximum-bytes",
        str(options["maximum_bytes"]),
    ]
    for status in ("activated", "already_activated"):
        result = subprocess.run(command, timeout=30, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout)
        assert receipt["status"] == status
        assert receipt["service_started"] is False
    fresh = service(restored)
    assert fresh.get_job(job.job_id, **tenant()).attempt == 0


def test_repeated_old_backup_activation_cannot_reset_total_budget(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    claim = current.claim_next(**worker("first"), lease_seconds=60)
    for ordinal in range(1, 5):
        assert (
            current.reserve_execution_attempt(
                job.job_id, **worker("first"), lease_token=claim.lease_token
            )
            == ordinal
        )
    activate_managed_restore(backup, restored, **options)
    fresh = service(restored)
    claim = fresh.claim_next(**worker("first"), lease_seconds=60)
    for ordinal in range(5, 9):
        assert (
            fresh.reserve_execution_attempt(
                job.job_id, **worker("first"), lease_token=claim.lease_token
            )
            == ordinal
        )
    third = tmp_path / "third"
    restore_job_store(backup, third, **options)
    activate_managed_restore(
        backup, third, **options, expected_generation=2, expected_root=str(restored)
    )
    final = service(third)
    claim = final.claim_next(**worker("first"), lease_seconds=60)
    assert (
        final.read_execution_budget(
            job.job_id, **worker("first"), lease_token=claim.lease_token
        )["remaining_attempts"]
        == 0
    )
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        final.reserve_execution_attempt(
            job.job_id, **worker("first"), lease_token=claim.lease_token
        )
    evidence = final.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["pending_ordinals"] == list(range(1, 9))
    assert evidence["invocations"] == []
    for old in (current, fresh):
        with pytest.raises(JobServiceError, match="execution_authority_rejected"):
            old.claim_next(**worker("first"), lease_seconds=60)


def test_two_processes_cannot_activate_two_restored_copies(tmp_path):
    current, authority, binding, job, backup, restored, options = setup_store(tmp_path)
    alternative = tmp_path / "alternative"
    restore_job_store(backup, alternative, **options)
    program = """
import json, sys
from structural_analysis.execution.job_managed_restore import activate_managed_restore
print("ready", flush=True)
assert sys.stdin.readline() == "activate\\n"
try:
    result = activate_managed_restore(sys.argv[1], sys.argv[2], **json.loads(sys.argv[3]))
except ValueError:
    print("rejected", flush=True)
else:
    print(result["status"], flush=True)
"""
    children = []
    try:
        for target in (restored, alternative):
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        program,
                        str(backup),
                        str(target),
                        json.dumps(options),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        for child in children:
            with selectors.DefaultSelector() as ready:
                ready.register(child.stdout, selectors.EVENT_READ)
                assert ready.select(timeout=10), "activation child did not become ready"
                assert child.stdout.readline() == "ready\n"
        for child in children:
            child.stdin.write("activate\n")
            child.stdin.flush()
        results = [child.communicate(timeout=30) for child in children]
        assert sorted(output.strip() for output, _ in results) == [
            "activated",
            "rejected",
        ]
        assert all(child.returncode == 0 for child in children), results
        winner = (restored, alternative)[
            next(i for i, (out, _) in enumerate(results) if out.strip() == "activated")
        ]
        loser = alternative if winner == restored else restored
        assert service(winner).claim_next(**worker("first"), lease_seconds=60)
        for path in (current.root, loser):
            with pytest.raises(JobServiceError, match="execution_authority_rejected"):
                service(path)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()
