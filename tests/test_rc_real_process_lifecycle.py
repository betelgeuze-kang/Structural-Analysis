"""Real tiny RC solves, process death, durable restart, and report-only revisions.

Uses generated local test credentials and an empty store. No completed result,
checkpoint or solver response is injected. This is software lifecycle evidence,
not independent physical validation or design authority.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import shutil
import sqlite3
import subprocess
import sys
import time

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)


ROOT = Path(__file__).resolve().parents[1]
TENANTS = {name: f"local-test-only-{name}-token-0123456789" for name in ("a", "b")}
WORKERS = {
    name: f"local-test-only-{name}-token-0123456789" for name in ("first", "fresh")
}
SOURCE_REVISION = "a" * 40  # Caller declaration, not source authentication.


def service(root):
    return DurableJobService(
        root,
        tenant_tokens=TENANTS,
        worker_tokens=WORKERS,
        worker_tenants={name: {"a"} for name in WORKERS},
    )


def tenant(name="a"):
    return {"tenant_id": name, "authorization_token": TENANTS[name]}


def worker(name):
    return {"worker_id": name, "authorization_token": WORKERS[name]}


def request():
    return {
        "schema_version": "structural-analysis-job-request.v3",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "real-process-cantilever",
        "model": json.loads(
            (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_text()
        ),
        "config": BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6)).to_dict(),
        "source_revision": SOURCE_REVISION,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 8},
    }


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def child(root, name):
    current = service(root)
    claim = current.claim_next(**worker(name), lease_seconds=5)
    assert claim is not None
    if name == "fresh":
        assert claim.job.progress_completed == 1
        assert claim.checkpoint_bytes is not None
        emit({"resumed_pid": os.getpid(), "progress": claim.job.progress_completed})
        assert sys.stdin.readline() == "continue\n"
    result = execute_rc_fiber_direct_control_claim(
        current, claim, **worker(name), lease_seconds=5
    )
    if name == "first":
        assert result.status == "checkpointed" and result.progress_completed == 1
        # Crash with a newly claimed lease and an unfulfilled reservation. This
        # proves abandoned work remains unknown rather than being erased.
        abandoned = current.claim_next(**worker(name), lease_seconds=5)
        ordinal = current.reserve_execution_attempt(
            result.job_id, **worker(name), lease_token=abandoned.lease_token
        )
        emit(
            {
                "pid": os.getpid(),
                "job_id": result.job_id,
                "checkpoint_hash": result.checkpoint.content_hash,
                "abandoned_ordinal": ordinal,
                "lease_token": abandoned.lease_token,
            }
        )
        while True:
            time.sleep(60)
    assert result.status == "succeeded" and result.progress_completed == 2
    emit({"pid": os.getpid(), "job": result.to_dict()})


def spawn(root, name):
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(root), name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def read_ready(process, timeout=90):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout):
            raise AssertionError("worker failed to checkpoint within deadline")
    line = process.stdout.readline()
    if not line:
        raise AssertionError(process.stderr.read())
    return json.loads(line)


def numerical_rows(root):
    with sqlite3.connect(root / "jobs.sqlite3") as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in (
                "jobs",
                "job_events",
                "job_rc_invocation_outcomes",
                "job_execution_budgets",
            )
        }


def assert_error(call):
    try:
        call()
    except JobServiceError as error:
        return error.code
    raise AssertionError("unauthorized or conflicting action unexpectedly succeeded")


def run_lifecycle(root):
    assert not root.exists(), "lifecycle requires an empty isolated store"
    current = service(root)
    original = request()
    job = current.submit_job(**tenant(), idempotency_key="new-input", request=original)
    # Re-delivery after a lost HTTP response must bind to the same immutable job.
    retried = service(root).submit_job(
        **tenant(), idempotency_key="new-input", request=original
    )
    assert retried.job_id == job.job_id
    isolation = assert_error(lambda: current.get_job(job.job_id, **tenant("b")))
    auth = assert_error(
        lambda: current.get_job(job.job_id, tenant_id="a", authorization_token="wrong")
    )
    first = spawn(root, "first")
    try:
        checkpoint = read_ready(first)
        assert checkpoint["abandoned_ordinal"] == 3
        first.kill()
        first.wait(timeout=10)
        assert first.returncode == -signal.SIGKILL
        assert current.claim_next(**worker("fresh"), lease_seconds=5) is None
        time.sleep(5.1)
        fresh = spawn(root, "fresh")
        try:
            restored = read_ready(fresh)
            assert restored["progress"] == 1
            stale = assert_error(
                lambda: current.heartbeat(
                    job.job_id, **worker("first"), lease_token=checkpoint["lease_token"]
                )
            )
            fresh.stdin.write("continue\n")
            fresh.stdin.flush()
            completed = read_ready(fresh)
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
    assert completed["pid"] != checkpoint["pid"]
    job = service(root).get_job(job.job_id, **tenant())
    evidence = current.read_rc_invocation_evidence(job.job_id, **tenant())
    result = json.loads(current.read_result(job.job_id, **tenant()))
    assert result["completed_target_count"] == 2
    assert len(result["receipts"]) == 2
    assert result["receipts"][1]["restart_input_sha256"] is not None
    assert result["execution_budget"]["reserved_attempts"] == 5
    assert evidence["pending_ordinals"] == [3]
    assert evidence["pending_execution_work"] == "unknown"
    assert [row["ordinal"] for row in evidence["invocations"]] == [1, 2, 4, 5]
    before = numerical_rows(root)
    # Fail loudly if any report path attempts analysis, verification or solving.
    from structural_analysis.api import rc_fiber_frame_direct_control as api
    from structural_analysis.assembly import stateful_fiber_frame2d_control_path as path
    from structural_analysis.solvers.nonlinear import newton
    from unittest.mock import patch

    def forbidden(*args, **kwargs):
        raise AssertionError("price-only path entered a numerical solver")

    prices = {
        "concrete_per_m3": 120.0,
        "rebar_per_kg": 2.0,
        "currency": "USD",
        "as_of": "2026-10-07",
        "source": "local lifecycle test declaration",
    }
    binding = {
        "expected_request_hash": job.request.content_hash,
        "expected_result_artifact_hash": job.result.content_hash,
    }
    with (
        patch.object(api, "analyze_bounded_rc_fiber_direct_control", forbidden),
        patch.object(
            api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
        ),
        patch.object(path, "_execute_raw", forbidden),
        patch.object(newton, "newton_raphson_vector", forbidden),
    ):
        first_report = current.create_rc_quantity_report(
            job.job_id, **tenant(), **binding, declared_prices=prices
        )
        second_report = service(root).create_rc_quantity_report(
            job.job_id,
            **tenant(),
            **binding,
            declared_prices=prices | {"concrete_per_m3": 150.0},
        )
        assert [first_report["revision"], second_report["revision"]] == [1, 2]
        assert (
            current.create_rc_quantity_report(
                job.job_id, **tenant(), **binding, declared_prices=prices
            )
            == first_report
        )
        assert numerical_rows(root) == before
    api_http = DurableJobHttpApi(service(root))
    report_path = (
        f"/v1/jobs/{job.job_id}/rc-quantity-reports/{second_report['report_id']}"
    )
    download = api_http.handle(
        "GET",
        report_path,
        headers={"X-Structural-Tenant": "a", "Authorization": f"Bearer {TENANTS['a']}"},
    )
    assert download.status == 200
    assert "attachment" in download.headers["content-disposition"]
    assert (
        "sha256:" + hashlib.sha256(download.body).hexdigest()
        == second_report["content_hash"]
    )
    denied_download = api_http.handle(
        "GET",
        report_path,
        headers={"X-Structural-Tenant": "b", "Authorization": f"Bearer {TENANTS['b']}"},
    )
    assert denied_download.status in (403, 404)
    changed = deepcopy(original)
    changed["model"]["sections"][0]["depth_m"] = 0.65
    conflict = assert_error(
        lambda: current.submit_job(
            **tenant(), idempotency_key="new-input", request=changed
        )
    )
    changed_job = current.submit_job(
        **tenant(), idempotency_key="changed-structure", request=changed
    )
    assert changed_job.job_id != job.job_id and changed_job.status == "queued"
    # Corrupt a copied store only. Genuine retained result bytes must fail closed.
    damaged_root = root.parent / "corrupt-copy"
    shutil.copytree(root, damaged_root)
    damaged = service(damaged_root)
    blob = damaged._blob_path(job.result.content_hash)
    raw = blob.read_bytes()
    blob.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    corruption = assert_error(lambda: damaged.read_result(job.job_id, **tenant()))
    summary = {
        "job_id": job.job_id,
        "source_revision": SOURCE_REVISION,
        "worker_pids": [checkpoint["pid"], completed["pid"]],
        "first_worker_signal": "SIGKILL",
        "completed_targets": 2,
        "checkpoint_hash": checkpoint["checkpoint_hash"],
        "result_hash": job.result.content_hash,
        "reserved_api_invocations": 5,
        "retained_invocation_evidence": evidence,
        "report_revisions": [first_report, second_report],
        "price_only_numerical_state_unchanged": True,
        "failure_codes": {
            "tenant_isolation": isolation,
            "authorization": auth,
            "stale_lease": stale,
            "structural_idempotency_conflict": conflict,
            "corrupt_result": corruption,
        },
        "changed_structure_job": changed_job.job_id,
        "http_download_status": download.status,
        "browser_download": "not_run",
        "independent_physical_validation": False,
        "design_authority": False,
    }
    (root.parent / "lifecycle-summary.json").write_text(json.dumps(summary, indent=2))
    (root.parent / "report-revision-2.json").write_bytes(download.body)
    return summary


def test_real_process_lifecycle(tmp_path):
    run_lifecycle(tmp_path / "store")


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        child(Path(sys.argv[2]), sys.argv[3])
    else:
        emit(run_lifecycle(Path(sys.argv[1])))
