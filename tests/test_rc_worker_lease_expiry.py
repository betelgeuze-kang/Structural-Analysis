"""Confirmed RC lease expiry and real SQLite contention; no numerical execution."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import Event
import time

import pytest

from structural_analysis.api import rc_corotational_control as corotational_api
from structural_analysis.api import rc_fiber_frame_direct_control as fiber_api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution import rc_fiber_direct_control_worker as worker
from structural_analysis.execution.job_service import DurableJobService, JobServiceError


TENANT = dict(tenant_id="tenant", authorization_token="lease-tenant-token-0123456789")
WORKER = dict(worker_id="worker", authorization_token="lease-worker-token-0123456789")
SECOND = dict(worker_id="second", authorization_token="lease-second-token-0123456789")


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 12, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def no_numerical_api(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Lease tests must not execute numerical analysis or verification")

    for api, names in (
        (
            fiber_api,
            (
                "analyze_bounded_rc_fiber_direct_control",
                "validate_bounded_rc_fiber_direct_control_artifacts",
                "run_stateful_fiber_frame2d_control_path",
            ),
        ),
        (
            corotational_api,
            (
                "analyze_rc_corotational_control",
                "validate_rc_corotational_control_artifacts",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(api, name, forbidden)


def leased(tmp_path):
    clock = Clock()
    service = DurableJobService(
        tmp_path / "store",
        tenant_tokens={"tenant": TENANT["authorization_token"]},
        worker_tokens={
            "worker": WORKER["authorization_token"],
            "second": SECOND["authorization_token"],
        },
        worker_tenants={"worker": {"tenant"}, "second": {"tenant"}},
        clock=clock,
    )
    request = {
        "schema_version": "structural-analysis-job-request.v3",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "lease-contention",
        "model": json.loads(
            (
                Path(__file__).parents[1]
                / "examples/public_rc_fiber_frame_l_frame_material_history.json"
            ).read_bytes()
        ),
        "config": BoundedRCFiberDirectControlRequest(7, (-1e-6, -2e-6)).to_dict(),
        "source_revision": "b" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {
            "chunk_target_count": 1,
            "maximum_api_invocations": 4,
        },
    }
    job = service.submit_job(**TENANT, idempotency_key="lease", request=request)
    claim = service.claim_next(**WORKER, lease_seconds=5)
    assert claim is not None and claim.job.job_id == job.job_id
    credentials = dict(WORKER, lease_token=claim.lease_token)
    initial = service.heartbeat(job.job_id, **credentials, lease_seconds=5)
    return service, clock, claim, credentials, initial


def keeper_for(service, claim, credentials, initial):
    return worker._LeaseKeeper(
        service, claim.job.job_id, credentials, 5, initial_lease=initial
    )


def immediate_first_renewal(keeper, monkeypatch, confirmed=None):
    original_wait = keeper.stopped.wait
    first = True

    def wait(timeout):
        nonlocal first
        if first:
            first = False
            return False
        if confirmed is not None:
            confirmed.set()  # The real heartbeat and its confirmation returned.
        return original_wait(timeout)

    monkeypatch.setattr(keeper.stopped, "wait", wait)


def test_initial_confirmed_lease_is_required_and_expired_lease_refused(tmp_path):
    service, clock, claim, credentials, initial = leased(tmp_path)
    with pytest.raises(TypeError, match="initial_lease"):
        worker._LeaseKeeper(service, claim.job.job_id, credentials, 5)
    for invalid in (
        replace(initial, job_id="other"),
        replace(initial, status="queued", lease_expires_at=None),
        replace(initial, lease_expires_at="2026-10-12T00:00:05"),
    ):
        with pytest.raises(JobServiceError, match="confirmed_lease_invalid"):
            keeper_for(service, claim, credentials, invalid)
    clock.advance(5)
    with pytest.raises(JobServiceError, match="lease_expired"):
        keeper_for(service, claim, credentials, initial)


def test_monotonic_deadline_refuses_frozen_service_clock_and_cannot_revive(
    tmp_path, monkeypatch
):
    service, clock, claim, credentials, initial = leased(tmp_path)
    monotonic_ns = [1_000_000]
    monkeypatch.setattr(worker.time, "monotonic_ns", lambda: monotonic_ns[0])
    keeper = keeper_for(service, claim, credentials, initial)
    keeper.check()
    monotonic_ns[0] += 5_000_000_000
    with pytest.raises(JobServiceError, match="lease_expired"):
        keeper.check()
    # The service's frozen clock may still accept a heartbeat, but that cannot
    # revive a worker that has already observed its conservative deadline.
    renewed = service.heartbeat(claim.job.job_id, **credentials, lease_seconds=5)
    with pytest.raises(JobServiceError, match="lease_expired"):
        keeper._confirm(renewed)


def test_successfully_confirmed_background_renewal_extends_custody(
    tmp_path, monkeypatch
):
    service, clock, claim, credentials, initial = leased(tmp_path)
    keeper = keeper_for(service, claim, credentials, initial)
    confirmed = Event()
    immediate_first_renewal(keeper, monkeypatch, confirmed)
    clock.advance(4)
    with keeper:
        assert confirmed.wait(5)
        clock.advance(2)
        keeper.check()  # Initial lease expired; confirmed renewal has not.
        clock.advance(3)
        with pytest.raises(JobServiceError, match="lease_expired"):
            keeper.check()


def test_failure_latched_during_clock_read_cannot_return_success(tmp_path, monkeypatch):
    service, clock, claim, credentials, initial = leased(tmp_path)
    keeper = keeper_for(service, claim, credentials, initial)
    failure = RuntimeError("background heartbeat failed during clock read")

    def clock_with_latched_renewal_failure():
        keeper.failure = failure
        return clock()

    monkeypatch.setattr(service, "_clock", clock_with_latched_renewal_failure)
    with pytest.raises(JobServiceError, match="lease_renewal_failed") as caught:
        keeper.check()
    assert caught.value.__cause__ is failure


def test_check_expires_while_actual_sqlite_heartbeat_is_blocked_and_spend_survives(
    tmp_path, monkeypatch
):
    service, clock, claim, credentials, initial = leased(tmp_path)
    ordinal = service.reserve_execution_attempt(claim.job.job_id, **credentials)
    assert ordinal == 1
    entered = Event()
    heartbeat_errors = []
    original_open = service._open_configured_connection
    original_heartbeat = service.heartbeat

    def traced_open():
        connection = original_open()

        def trace(statement):
            if statement == "BEGIN IMMEDIATE":
                entered.set()  # SQLite is about to wait on the real write lock.

        connection.set_trace_callback(trace)
        return connection

    def heartbeat(*args, **kwargs):
        try:
            return original_heartbeat(*args, **kwargs)
        except Exception as error:
            heartbeat_errors.append(error)
            raise

    keeper = keeper_for(service, claim, credentials, initial)
    immediate_first_renewal(keeper, monkeypatch)
    monkeypatch.setattr(service, "_open_configured_connection", traced_open)
    monkeypatch.setattr(service, "heartbeat", heartbeat)
    lock = sqlite3.connect(tmp_path / "store/jobs.sqlite3", timeout=0)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with keeper:
            try:
                assert entered.wait(5)
                assert keeper.thread.is_alive() and not heartbeat_errors
                clock.advance(6)  # Expire the 5s lease while SQLite allows 30s wait.
                began = time.perf_counter()
                with pytest.raises(JobServiceError, match="lease_expired"):
                    keeper.check()
                assert time.perf_counter() - began < 1.0
                assert keeper.thread.is_alive() and not heartbeat_errors
            finally:
                lock.rollback()  # Allow real heartbeat to recheck time after lock.
    finally:
        lock.close()
    assert len(heartbeat_errors) == 1
    assert isinstance(heartbeat_errors[0], JobServiceError)
    assert heartbeat_errors[0].code == "lease_expired"
    assert not keeper.thread.is_alive()
    view = service.get_job(claim.job.job_id, **TENANT)
    assert view.lease_expires_at == initial.lease_expires_at
    assert view.progress_completed == 0 and view.checkpoint is view.result is None
    evidence = service.read_rc_invocation_evidence(claim.job.job_id, **TENANT)
    assert evidence["execution_budget"]["reserved_attempts"] == 1
    assert evidence["pending_ordinals"] == [1]
    assert evidence["pending_execution_work"] == "unknown"
    successor = service.claim_next(**SECOND, lease_seconds=5)
    assert successor is not None
    assert successor.job.attempt == claim.job.attempt + 1
    assert successor.request_bytes == claim.request_bytes
    assert (
        service.read_execution_budget(
            successor.job.job_id, **SECOND, lease_token=successor.lease_token
        )["reserved_attempts"]
        == 1
    )
    with pytest.raises(JobServiceError, match="lease_unauthorized"):
        original_heartbeat(claim.job.job_id, **credentials, lease_seconds=5)
