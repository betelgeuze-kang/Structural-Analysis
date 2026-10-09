"""Real RC worker plus operator backup; no independent specimen/physics claim."""

import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sqlite3
import sys

import pytest
import time


from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
    verify_job_store_backup,
)

_SPEC = importlib.util.spec_from_file_location(
    "rc_backup_lifecycle_helpers",
    Path(__file__).with_name("test_rc_real_process_lifecycle.py"),
)
lifecycle = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lifecycle)

LIMIT = 10 * 1024 * 1024


@pytest.mark.parametrize("isolated", [False, pytest.param(True, marks=pytest.mark.skipif(sys.platform != "linux", reason="Linux phase isolation"))])
@pytest.mark.parametrize("payload_cap", [None, LIMIT])
def test_rc_checkpoint_backup_stop_restore_resume_and_report(tmp_path, monkeypatch, payload_cap, isolated):
    source = tmp_path / "source"
    service = lifecycle.DurableJobService(
        source, tenant_tokens=lifecycle.TENANTS, worker_tokens=lifecycle.WORKERS,
        worker_tenants={name: {"a"} for name in lifecycle.WORKERS},
        max_blob_payload_bytes=payload_cap,
    )
    request = lifecycle.request()
    if isolated:
        from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy
        request["execution_config"]["phase_execution_policy"] = RCFiberPhasePolicy(30000, 30000, 100).to_dict()
    job = service.submit_job(
        **lifecycle.tenant(), idempotency_key="backup-rc", request=request
    )
    first = lifecycle.spawn(source, "first")
    try:
        checkpoint = lifecycle.read_ready(first)
        assert checkpoint["abandoned_ordinal"] == 3
        before = lifecycle.numerical_rows(source)
        sealed = tmp_path / "sealed"
        receipt = backup_job_store(source, sealed, maximum_bytes=LIMIT)
        verified = verify_job_store_backup(
            sealed, manifest_sha256=receipt["manifest_sha256"], maximum_bytes=LIMIT
        )
        assert verified["recovery_snapshot"]["job_status_counts"]["running"] == 1
        assert verified["recovery_snapshot"]["original_writers_fenced"] is False
        assert lifecycle.numerical_rows(source) == before
        # The supported operator procedure stops the original before resuming a
        # restored copy. Snapshot creation does not provide distributed fencing.
        first.kill()
        first.wait(timeout=10)
        assert first.returncode == -signal.SIGKILL
        if Path("/proc").is_dir():
            assert not Path(f"/proc/{first.pid}").exists()
        restored_root = tmp_path / "restored"
        restore_job_store(
            sealed,
            restored_root,
            manifest_sha256=receipt["manifest_sha256"],
            maximum_bytes=LIMIT,
        )
        assert lifecycle.numerical_rows(restored_root) == before
        time.sleep(5.1)
        fresh = lifecycle.spawn(restored_root, "fresh")
        try:
            ready = lifecycle.read_ready(fresh)
            assert ready["progress"] == 1
            restored = lifecycle.service(restored_root)
            assert (
                restored.claim_next(**lifecycle.worker("first"), lease_seconds=5)
                is None
            )
            stale = lifecycle.assert_error(
                lambda: restored.heartbeat(
                    job.job_id,
                    **lifecycle.worker("first"),
                    lease_token=checkpoint["lease_token"],
                )
            )
            assert stale
            fresh.stdin.write("continue\n")
            fresh.stdin.flush()
            lifecycle.read_ready(fresh)
            fresh.wait(timeout=90)
            assert fresh.returncode == 0, fresh.stderr.read()
        finally:
            if fresh.poll() is None:
                fresh.kill()
                fresh.wait()
    finally:
        if first.poll() is None:
            first.kill()
            first.wait()
    restored = lifecycle.service(restored_root)
    completed = restored.get_job(job.job_id, **lifecycle.tenant())
    assert completed.status == "succeeded"
    result_bytes = restored.read_result(job.job_id, **lifecycle.tenant())
    result = json.loads(result_bytes)
    assert result["completed_target_count"] == 2
    assert result["execution_budget"]["reserved_attempts"] == 5
    evidence = restored.read_rc_invocation_evidence(job.job_id, **lifecycle.tenant())
    assert evidence["pending_ordinals"] == [3]
    assert evidence["pending_execution_work"] == "unknown"
    report = restored.create_rc_quantity_report(
        job.job_id,
        **lifecycle.tenant(),
        expected_request_hash=completed.request.content_hash,
        expected_result_artifact_hash=completed.result.content_hash,
        declared_prices={
            "concrete_per_m3": 120.0,
            "rebar_per_kg": 2.0,
            "currency": "USD",
            "as_of": "2026-10-08",
            "source": "synthetic integration-test prices",
        },
    )
    terminal_backup = tmp_path / "terminal-backup"
    terminal = backup_job_store(restored_root, terminal_backup, maximum_bytes=LIMIT)
    reopened_root = tmp_path / "reopened"
    restore_job_store(
        terminal_backup,
        reopened_root,
        manifest_sha256=terminal["manifest_sha256"],
        maximum_bytes=LIMIT,
    )
    # Reading a retained result/report must not invoke the solver again.
    from structural_analysis.solvers.nonlinear import newton
    from structural_analysis.api import rc_fiber_frame_direct_control as api
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_control_path as paths,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("backup reopen unexpectedly entered numerical solve")

    monkeypatch.setattr(newton, "newton_raphson_vector", forbidden)
    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(paths, "_execute_raw", forbidden)
    reopened = lifecycle.service(reopened_root)
    assert reopened.read_result(job.job_id, **lifecycle.tenant()) == result_bytes
    assert (
        reopened.read_rc_invocation_evidence(job.job_id, **lifecycle.tenant())
        == evidence
    )
    assert reopened.validate_integrity(job.job_id, **lifecycle.tenant())[
        "contract_pass"
    ]
    report_bytes = reopened.read_rc_quantity_report(
        job.job_id, report["report_id"], **lifecycle.tenant()
    )
    assert (
        "sha256:" + hashlib.sha256(report_bytes).hexdigest() == report["content_hash"]
    )
    assert lifecycle.numerical_rows(reopened_root) == lifecycle.numerical_rows(
        restored_root
    )

    for root in (source, restored_root, reopened_root):
        with sqlite3.connect(root / "jobs.sqlite3") as connection:
            policy = connection.execute("SELECT maximum_bytes FROM job_blob_payload_policy").fetchall()
        assert policy == ([] if payload_cap is None else [(payload_cap,)])
        if payload_cap is not None:
            assert sum(p.stat().st_size for p in (root / "blobs").rglob("*") if p.is_file()) <= payload_cap
