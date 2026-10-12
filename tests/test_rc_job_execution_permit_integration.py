"""Real cooperating processes test RC job exclusion and backup boundaries.

No numerical API, source fingerprint or scientific qualification is exercised.
Worker bodies below are controlled seams; service leases, permits, SQLite
custody, external generation fencing and heartbeat joins are real.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys
from threading import Event, Thread, current_thread

import pytest

from structural_analysis.execution import rc_corotational_control_worker as coro_worker
from structural_analysis.execution import rc_fiber_direct_control_worker as fiber_worker
from structural_analysis.execution import rc_fiber_phase_supervisor as common
from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from tests.test_rc_corotational_job_contract import request as coro_request
from tests.test_rc_fiber_durable_worker import _request as fiber_request


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux pinned flock custody"
)
TENANT = {
    "tenant_id": "tenant",
    "authorization_token": "controlled-permit-tenant-0123456789",
}
FIRST = {
    "worker_id": "first",
    "authorization_token": "controlled-permit-first-0123456789",
}
SECOND = {
    "worker_id": "second",
    "authorization_token": "controlled-permit-second-0123456789",
}
LIMIT = 10 * 1024 * 1024
SOURCE = Path(__file__).resolve().parents[1] / "src"


class Clock:
    def __init__(self):
        self.value = datetime.now(timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def service(root, **options):
    return DurableJobService(
        root,
        tenant_tokens={"tenant": TENANT["authorization_token"]},
        worker_tokens={
            x["worker_id"]: x["authorization_token"] for x in (FIRST, SECOND)
        },
        worker_tenants={"first": {"tenant"}, "second": {"tenant"}},
        **options,
    )


def setup(tmp_path, *, profile="corotational", managed=False):
    clock, root = Clock(), tmp_path / "source"
    authority = binding = None
    if managed:
        authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(
        root, clock=clock, execution_authority=authority, execution_binding=binding
    )
    payload = coro_request() if profile == "corotational" else fiber_request()
    job = current.submit_job(
        **TENANT, idempotency_key="controlled-job", request=payload
    )
    claim = current.claim_next(**FIRST, lease_seconds=300)
    assert claim is not None and claim.job.job_id == job.job_id
    return current, claim, clock, authority, binding


@pytest.fixture(autouse=True)
def forbid_numerical_apis_and_source_fingerprints(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("permit integration invoked numerical API/source fingerprint")

    for module, names in (
        (
            "structural_analysis.api.rc_fiber_frame_direct_control",
            (
                "analyze_bounded_rc_fiber_direct_control",
                "validate_bounded_rc_fiber_direct_control_artifacts",
            ),
        ),
        (
            "structural_analysis.api.rc_corotational_control",
            (
                "analyze_rc_corotational_control",
                "validate_rc_corotational_control_artifacts",
                "_source_identity",
            ),
        ),
        (
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision",
            ("_source_identity",),
        ),
    ):
        for name in names:
            monkeypatch.setattr(f"{module}.{name}", forbidden)


def permit(current, claim, credentials):
    return current.job_execution_permit(
        claim.job.job_id,
        expected_request_hash=claim.job.request.content_hash,
        **credentials,
        lease_token=claim.lease_token,
    )


def snapshot(current):
    with sqlite3.connect(current.root / "jobs.sqlite3") as db:
        return {
            name: db.execute(f"SELECT * FROM {name} ORDER BY 1,2").fetchall()
            for name in ("jobs", "job_events", "job_execution_budgets")
        }


_CHILD = r"""import sys,json,os
from datetime import datetime
sys.path[:0]=json.loads(sys.argv[2])
sys.path.insert(0,sys.argv[1])
from structural_analysis.execution.job_service import DurableJobService,JobServiceError
from structural_analysis.api import rc_fiber_frame_direct_control as fiber,rc_corotational_control as coro
def forbidden(*args,**kwargs): raise AssertionError('controlled permit child invoked numerical API/source fingerprint')
fiber.analyze_bounded_rc_fiber_direct_control=forbidden
fiber.validate_bounded_rc_fiber_direct_control_artifacts=forbidden
coro.analyze_rc_corotational_control=forbidden
coro.validate_rc_corotational_control_artifacts=forbidden
coro._source_identity=forbidden
cfg=json.loads(sys.stdin.readline())
now=datetime.fromisoformat(cfg['clock'].replace('Z','+00:00'))
s=DurableJobService(cfg['root'],tenant_tokens=cfg['tenants'],worker_tokens=cfg['workers'],worker_tenants={'first':{'tenant'},'second':{'tenant'}},clock=lambda:now)
try:
    with s.execution_guard() as generation_fd:
        with s.job_execution_permit(cfg['job_id'],expected_request_hash=cfg['request_hash'],**cfg['credentials'],lease_token=cfg['lease_token']) as fd:
            print(json.dumps({'status':'acquired','inode':os.fstat(fd).st_ino,'generation_guard':generation_fd is not None}),flush=True)
            if cfg['mode']=='hold': sys.stdin.readline()
except JobServiceError as e:
    if cfg['mode']!='probe': raise
    print(json.dumps({'status':'rejected','code':e.code}),flush=True)
"""


def child_config(current, claim, credentials, *, mode):
    return {
        "root": str(current.root),
        "clock": current._now()[0],
        "tenants": {"tenant": TENANT["authorization_token"]},
        "workers": {x["worker_id"]: x["authorization_token"] for x in (FIRST, SECOND)},
        "job_id": claim.job.job_id,
        "request_hash": claim.job.request.content_hash,
        "credentials": credentials,
        "lease_token": claim.lease_token,
        "mode": mode,
    }


def read_ready(child):
    with selectors.DefaultSelector() as ready:
        ready.register(child.stdout, selectors.EVENT_READ)
        assert ready.select(15), "controlled permit child did not become ready"
    line = child.stdout.readline()
    assert line, (
        child.stderr.read() if child.poll() is not None else "child pipe closed"
    )
    return json.loads(line)


@contextmanager
def holder(current, claim, credentials):
    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            _CHILD,
            str(SOURCE),
            json.dumps(common._dependency_paths()),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
    )
    acquired_ready = False
    try:
        child.stdin.write(
            json.dumps(child_config(current, claim, credentials, mode="hold")) + "\n"
        )
        child.stdin.flush()
        acquired = read_ready(child)
        assert acquired["status"] == "acquired"
        acquired_ready = True
        yield acquired
    finally:
        if child.poll() is None:
            try:
                child.stdin.write("release\n")
                child.stdin.flush()
            except BrokenPipeError:
                pass
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        error = child.stderr.read()
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()
        if acquired_ready:
            assert child.returncode == 0, error


def probe(current, claim, credentials):
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _CHILD,
            str(SOURCE),
            json.dumps(common._dependency_paths()),
        ],
        input=json.dumps(child_config(current, claim, credentials, mode="probe"))
        + "\n",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


def worker_entry(profile):
    if profile == "corotational":
        return (
            coro_worker,
            "_execute",
            coro_worker.execute_rc_corotational_control_claim,
        )
    return (
        fiber_worker,
        "_execute_rc_fiber_direct_control_claim",
        fiber_worker.execute_rc_fiber_direct_control_claim,
    )


@pytest.mark.parametrize("profile", ("fiber", "corotational"))
@pytest.mark.parametrize("managed", (False, True))
def test_replacement_claim_is_busy_without_row_event_budget_or_api_change_then_retries_same_claim(
    tmp_path, monkeypatch, profile, managed
):
    current, old, clock, _authority, _binding = setup(
        tmp_path, profile=profile, managed=managed
    )
    module, body_name, execute = worker_entry(profile)
    admitted = []

    def controlled_body(current, claim, **options):
        admitted.append((claim.lease_token, os.fstat(options["job_guard_fd"]).st_ino))
        return claim.job

    monkeypatch.setattr(module, body_name, controlled_body)
    with holder(current, old, FIRST) as held:
        assert held["generation_guard"] is managed
        clock.advance(301)
        replacement = current.claim_next(**SECOND, lease_seconds=300)
        assert replacement is not None
        assert replacement.job.job_id == old.job.job_id
        assert replacement.lease_token != old.lease_token
        before = snapshot(current)
        with pytest.raises(JobServiceError) as captured:
            execute(current, replacement, **SECOND)
        assert captured.value.code == "job_execution_permit_busy"
        assert snapshot(current) == before
        assert admitted == []
        assert (
            current.read_rc_invocation_evidence(old.job.job_id, **TENANT)[
                "execution_budget"
            ]["reserved_attempts"]
            == 0
        )
    assert execute(current, replacement, **SECOND) == replacement.job
    assert admitted == [(replacement.lease_token, held["inode"])]
    assert snapshot(current) == before


@pytest.mark.parametrize("managed", (False, True))
def test_different_jobs_hold_real_exclusive_permits_independently(tmp_path, managed):
    current, first, _clock, _authority, _binding = setup(tmp_path, managed=managed)
    second_job = current.submit_job(
        **TENANT, idempotency_key="other-job", request=coro_request()
    )
    second = current.claim_next(**SECOND, lease_seconds=300)
    assert second is not None and second.job.job_id == second_job.job_id
    with holder(current, first, FIRST), holder(current, second, SECOND):
        before = snapshot(current)
        for claim, credentials in ((first, FIRST), (second, SECOND)):
            assert probe(current, claim, credentials) == {
                "status": "rejected",
                "code": "job_execution_permit_busy",
            }
        assert snapshot(current) == before
    with permit(current, first, FIRST), permit(current, second, SECOND):
        pass


def test_managed_backup_restore_keeps_external_job_pin_spend_and_fences_old_source(
    tmp_path,
):
    current, claim, clock, authority, _binding = setup(tmp_path, managed=True)
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    with holder(current, claim, FIRST) as held:
        namespace_stat = authority.permit_directory.stat()
        receipt = backup_job_store(current.root, backup, maximum_bytes=LIMIT)
        options = {
            "manifest_sha256": receipt["manifest_sha256"],
            "maximum_bytes": LIMIT,
        }
        assert (
            current.reserve_execution_attempt(
                claim.job.job_id, **FIRST, lease_token=claim.lease_token
            )
            == 1
        )
        restore_job_store(backup, restored, **options)
        with pytest.raises(ValueError, match="authority busy"):
            activate_managed_restore(backup, restored, **options)
        assert authority.permit_directory.stat().st_ino == namespace_stat.st_ino
    assert activate_managed_restore(backup, restored, **options)["generation"] == 2
    assert authority.permit_directory.stat().st_ino == namespace_stat.st_ino
    assert (
        authority.permit_directory / f"{claim.job.job_id}.lock"
    ).stat().st_ino == held["inode"]
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(current.root, clock=clock)
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        with permit(current, claim, FIRST):
            pytest.fail("fenced source acquired a permit")
    clock.advance(301)
    fresh = service(restored, clock=clock)
    replacement = fresh.claim_next(**SECOND, lease_seconds=300)
    assert replacement is not None
    with permit(fresh, replacement, SECOND) as fd:
        assert os.fstat(fd).st_ino == held["inode"]
    evidence = fresh.read_rc_invocation_evidence(claim.job.job_id, **TENANT)
    assert evidence["execution_budget"]["reserved_attempts"] == 1
    assert evidence["pending_ordinals"] == [1]


def test_unmanaged_backup_excludes_runtime_locks_and_copy_has_independent_namespace(
    tmp_path,
):
    current, claim, clock, _authority, _binding = setup(tmp_path)
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    assert (
        current.reserve_execution_attempt(
            claim.job.job_id, **FIRST, lease_token=claim.lease_token
        )
        == 1
    )
    with holder(current, claim, FIRST) as held:
        before = snapshot(current)
        receipt = backup_job_store(current.root, backup, maximum_bytes=LIMIT)
        options = {
            "manifest_sha256": receipt["manifest_sha256"],
            "maximum_bytes": LIMIT,
        }
        manifest = json.loads((backup / "backup-manifest.json").read_bytes())
        assert not any("execution-permit" in name for name in manifest["files"])
        assert not (backup / ".job-execution-permits").exists()
        restore_job_store(backup, restored, **options)
        assert not (restored / ".job-execution-permits").exists()
        clone = service(restored, clock=clock)
        with permit(clone, claim, FIRST) as fd:
            assert os.fstat(fd).st_ino != held["inode"]
            assert (
                clone.reserve_execution_attempt(
                    claim.job.job_id, **FIRST, lease_token=claim.lease_token
                )
                == 2
            )
            assert probe(current, claim, FIRST)["code"] == "job_execution_permit_busy"
        assert snapshot(current) == before
        assert (
            clone.read_rc_invocation_evidence(claim.job.job_id, **TENANT)[
                "execution_budget"
            ]["reserved_attempts"]
            == 2
        )
        assert (
            current.read_rc_invocation_evidence(claim.job.job_id, **TENANT)[
                "execution_budget"
            ]["reserved_attempts"]
            == 1
        )
    # This independence is expressly not copied-store/distributed fencing.


@pytest.mark.parametrize("member", ("namespace", "job"))
def test_fresh_service_rejects_replaced_unmanaged_pin_while_old_process_holds_it(
    tmp_path, member
):
    current, claim, clock, _authority, _binding = setup(tmp_path)
    with holder(current, claim, FIRST):
        directory = current.root / ".job-execution-permits"
        path = (
            directory
            if member == "namespace"
            else directory / f"{claim.job.job_id}.lock"
        )
        retained = tmp_path / "retained-original-pin"
        path.rename(retained)
        if member == "namespace":
            path.mkdir(mode=0o700)
        else:
            path.touch(mode=0o600)
        before = snapshot(current)
        fresh = service(current.root, clock=clock)
        with pytest.raises(JobServiceError) as captured:
            with permit(fresh, claim, FIRST):
                pytest.fail("replacement pin admitted while original process lives")
        assert captured.value.code == "job_execution_permit_invalid"
        assert snapshot(current) == before
        assert retained.exists() and path.exists()


@pytest.mark.parametrize("profile", ("fiber", "corotational"))
def test_actual_heartbeat_join_keeps_worker_job_permit_until_renewal_thread_ends(
    tmp_path, monkeypatch, profile
):
    current, claim, _clock, _authority, _binding = setup(
        tmp_path, profile=profile, managed=True
    )
    module, body_name, execute = worker_entry(profile)
    renewal_started, release_renewal, body_exiting = Event(), Event(), Event()
    outcomes, failures = [], []
    original_heartbeat = current.heartbeat

    def heartbeat(*args, **kwargs):
        if current_thread().name == "rc-fiber-job-lease":
            renewal_started.set()
            assert release_renewal.wait(15), "controlled renewal was not released"
        return original_heartbeat(*args, **kwargs)

    def controlled_body(current, claim, **options):
        credentials = {
            "worker_id": options["worker_id"],
            "authorization_token": options["authorization_token"],
            "lease_token": claim.lease_token,
        }
        confirmed = current.heartbeat(claim.job.job_id, **credentials, lease_seconds=9)
        with fiber_worker._LeaseKeeper(
            current, claim.job.job_id, credentials, 9, initial_lease=confirmed
        ):
            assert renewal_started.wait(6)
            body_exiting.set()
            return claim.job  # Actual keeper __exit__ must block in thread.join().

    def run():
        try:
            outcomes.append(execute(current, claim, **FIRST, lease_seconds=9))
        except BaseException as error:
            failures.append(error)

    monkeypatch.setattr(current, "heartbeat", heartbeat)
    monkeypatch.setattr(module, body_name, controlled_body)
    worker = Thread(target=run, name="controlled-permit-worker")
    worker.start()
    try:
        assert body_exiting.wait(8)
        assert worker.is_alive() and renewal_started.is_set()
        before = snapshot(current)
        assert probe(current, claim, FIRST) == {
            "status": "rejected",
            "code": "job_execution_permit_busy",
        }
        assert worker.is_alive() and snapshot(current) == before
        assert (
            current.read_rc_invocation_evidence(claim.job.job_id, **TENANT)[
                "execution_budget"
            ]["reserved_attempts"]
            == 0
        )
    finally:
        release_renewal.set()
        worker.join(15)
    assert not worker.is_alive() and not failures
    assert outcomes == [claim.job]
    with permit(current, claim, FIRST):
        pass
