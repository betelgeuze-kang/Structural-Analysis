"""Root payload policy under actual cooperating process/SQLite writers."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys

import pytest

from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from tests.test_rc_fiber_job_service import canonical, request


TENANT = "blob-budget-tenant-token-0123456789"
WORKER = "blob-budget-worker-token-0123456789"


def _service(root: Path, cap: int | None = None) -> DurableJobService:
    return DurableJobService(
        root,
        tenant_tokens={"a": TENANT},
        worker_tokens={"worker-a": WORKER},
        max_blob_payload_bytes=cap,
    )


def _request(case: str) -> dict:
    value = request()
    value["case_id"] = case
    return value


def _submit(service: DurableJobService, value: dict, key: str):
    return service.submit_job(
        tenant_id="a",
        authorization_token=TENANT,
        idempotency_key=key,
        request=value,
    )


def _blobs(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / "blobs" / "sha256").rglob("*"))
        if path.is_file()
    }


def _state(root: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(f"file:{root / 'jobs.sqlite3'}?mode=ro", uri=True) as db:
        return {
            name: db.execute(f"SELECT * FROM {name} ORDER BY 1, 2").fetchall()
            for name in ("jobs", "job_events", "job_execution_budgets")
        }


def _policy(root: Path) -> list[tuple]:
    with sqlite3.connect(f"file:{root / 'jobs.sqlite3'}?mode=ro", uri=True) as db:
        return db.execute(
            "SELECT singleton, maximum_bytes FROM job_blob_payload_policy"
        ).fetchall()


_CHILD = r"""
import json
import sys
from structural_analysis.execution.job_service import DurableJobService, JobServiceError

config = json.loads(sys.stdin.readline())
def open_service():
    return DurableJobService(
        config['root'],
        tenant_tokens={'a': 'blob-budget-tenant-token-0123456789'},
        worker_tokens={'worker-a': 'blob-budget-worker-token-0123456789'},
        max_blob_payload_bytes=config['cap'],
    )

try:
    # Writers finish constructor transactions before the synchronization point.
    # Adopters synchronize before opening; no child holds a writer lock here.
    service = open_service() if config['mode'] == 'submit' else None
    print('READY', flush=True)
    if sys.stdin.readline().strip() != 'GO':
        raise RuntimeError('parent did not release the barrier')
    service = service or open_service()
    if config['mode'] == 'submit':
        job = service.submit_job(
            tenant_id='a',
            authorization_token='blob-budget-tenant-token-0123456789',
            idempotency_key=config['key'],
            request=config['request'],
        )
        result = {'status': 'accepted', 'job_id': job.job_id}
    else:
        result = {'status': 'adopted', 'cap': config['cap']}
except JobServiceError as exc:
    result = {'status': 'rejected', 'code': exc.code}
except BaseException as exc:
    result = {'status': 'unexpected', 'type': type(exc).__name__, 'message': str(exc)}
print(json.dumps(result, sort_keys=True), flush=True)
"""


def _compete(configs: list[dict]) -> list[dict]:
    """Release both actual processes only after the readiness lines arrive."""
    children = []
    try:
        for config in configs:
            child = subprocess.Popen(
                [sys.executable, "-u", "-c", _CHILD],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            children.append(child)
            assert child.stdin is not None
            child.stdin.write(json.dumps(config) + "\n")
            child.stdin.flush()
        for child in children:
            assert child.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=45), "child never reached readiness"
            assert child.stdout.readline().strip() == "READY"
        for child in children:
            assert child.stdin is not None
            child.stdin.write("GO\n")
            child.stdin.flush()
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=45)
            assert child.returncode == 0, stderr
            assert not stderr, stderr
            value = json.loads(stdout)
            assert value["status"] != "unexpected", value
            results.append(value)
        return results
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)


def test_two_processes_commit_only_fitting_distinct_schema_valid_request(tmp_path):
    values = [_request(f"concurrent-budget-{index}") for index in range(2)]
    raw = [canonical(value) for value in values]
    assert len(raw[0]) == len(raw[1]) and raw[0] != raw[1]
    cap = len(raw[0])
    # Each actual public request fits by itself, not merely a predicted total.
    for index, value in enumerate(values):
        isolated = tmp_path / f"individually-fitting-{index}"
        _submit(_service(isolated, cap), value, "isolated")
        assert sum(map(len, _blobs(isolated).values())) == cap
    root = tmp_path / "shared"
    _service(root, cap)
    results = _compete(
        [
            {
                "mode": "submit",
                "root": str(root),
                "cap": cap,
                "request": value,
                "key": f"concurrent-{index}",
            }
            for index, value in enumerate(values)
        ]
    )
    winners = [i for i, result in enumerate(results) if result["status"] == "accepted"]
    assert len(winners) == 1, results
    loser = 1 - winners[0]
    assert results[loser] == {
        "status": "rejected",
        "code": "blob_payload_budget_exceeded",
    }
    retained = _blobs(root)
    assert list(retained.values()) == [raw[winners[0]]]
    path = next(iter(retained))
    assert Path(path).name == hashlib.sha256(raw[winners[0]]).hexdigest()
    before = _state(root)
    assert len(before["jobs"]) == len(before["job_events"]) == 1
    reopened = _service(root)
    retry = _submit(reopened, values[winners[0]], f"concurrent-{winners[0]}")
    assert retry.job_id == results[winners[0]]["job_id"]
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        _submit(reopened, values[loser], f"concurrent-{loser}")
    assert _blobs(root) == retained
    assert _state(root) == before


@pytest.mark.parametrize("same", [False, True])
def test_simultaneous_first_policy_adoption_is_coherent(tmp_path, same):
    caps = [17, 17 if same else 23]
    results = _compete(
        [{"mode": "adopt", "root": str(tmp_path), "cap": cap} for cap in caps]
    )
    adopted = [result["cap"] for result in results if result["status"] == "adopted"]
    assert len(adopted) == (2 if same else 1), results
    cap = adopted[0]
    assert _policy(tmp_path) == [(1, cap)]
    _service(tmp_path, cap)
    if not same:
        assert [r for r in results if r["status"] == "rejected"] == [
            {"status": "rejected", "code": "blob_payload_budget_conflict"}
        ]
        with pytest.raises(JobServiceError, match="blob_payload_budget_conflict"):
            _service(tmp_path, next(value for value in caps if value != cap))
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        _submit(_service(tmp_path), _request("policy-reopened"), "new")
    assert not _blobs(tmp_path)
    assert not _state(tmp_path)["jobs"]
    assert _policy(tmp_path) == [(1, cap)]


def test_already_open_unlimited_writer_sees_later_adoption_and_preserves_retry(
    tmp_path,
):
    old_writer = _service(tmp_path)
    value = _request("opened-before-adoption")
    job = _submit(old_writer, value, "first")
    retained = _blobs(tmp_path)
    before = _state(tmp_path)
    # Adoption below existing usage is allowed; no payload is reclaimed.
    _service(tmp_path, 1)
    assert _policy(tmp_path) == [(1, 1)]
    assert sum(map(len, retained.values())) > 1
    assert _submit(old_writer, deepcopy(value), "first") == job
    for writer in (old_writer, _service(tmp_path)):
        with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
            _submit(writer, _request("new-after-adoption"), "new")
    assert _blobs(tmp_path) == retained
    assert _state(tmp_path) == before


def test_policy_survives_sql_rollback_and_reopen_counts_admitted_orphan(tmp_path):
    value = _request("sqlite-rollback-request")
    payload = canonical(value)
    service = _service(tmp_path, len(payload))
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
        db.execute(
            "CREATE TRIGGER reject_test_job BEFORE INSERT ON jobs "
            "BEGIN SELECT RAISE(ABORT, 'injected commit boundary'); END"
        )
    with pytest.raises(JobServiceError, match="job_database_transaction_failed"):
        _submit(service, value, "first")
    retained = _blobs(tmp_path)
    assert list(retained.values()) == [payload]
    assert not _state(tmp_path)["jobs"]
    assert not _state(tmp_path)["job_events"]
    assert _policy(tmp_path) == [(1, len(payload))]
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
        db.execute("DROP TRIGGER reject_test_job")
    reopened = _service(tmp_path)
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        _submit(reopened, _request("new-request-after-sql-rollback"), "other")
    assert _blobs(tmp_path) == retained
    assert not _state(tmp_path)["jobs"]
    # Reusing the actual orphan writes no bytes and remains allowed at the cap.
    accepted = _submit(reopened, value, "first")
    assert (
        reopened.read_request(
            accepted.job_id, tenant_id="a", authorization_token=TENANT
        )
        == payload
    )
    assert _blobs(tmp_path) == retained


def test_conflicting_explicit_policy_cannot_replace_inherited_cap(tmp_path):
    value = _request("immutable-root-policy")
    cap = len(canonical(value))
    original = _service(tmp_path, cap)
    job = _submit(original, value, "first")
    before = _state(tmp_path)
    retained = _blobs(tmp_path)
    with pytest.raises(JobServiceError, match="blob_payload_budget_conflict"):
        _service(tmp_path, cap * 2)
    reopened = _service(tmp_path)
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        _submit(reopened, _request("distinct-policy-request"), "second")
    assert _submit(_service(tmp_path, cap), value, "first") == job
    assert _state(tmp_path) == before
    assert _blobs(tmp_path) == retained
    assert _policy(tmp_path) == [(1, cap)]


_PARTIAL_STAGING_CHILD = r"""
import json
import os
import sys
from structural_analysis.execution import job_service as implementation
from structural_analysis.execution.job_service import DurableJobService

config = json.loads(sys.stdin.readline())
service = DurableJobService(
    config['root'],
    tenant_tokens={'a': 'blob-budget-tenant-token-0123456789'},
    worker_tokens={'worker-a': 'blob-budget-worker-token-0123456789'},
    max_blob_payload_bytes=config['cap'],
)
real_fdopen = os.fdopen
class PartialStream:
    def __init__(self, stream):
        self.stream = stream
    def __enter__(self):
        self.stream.__enter__()
        return self
    def __exit__(self, *args):
        return self.stream.__exit__(*args)
    def write(self, payload):
        partial = payload[:len(payload) // 2]
        self.stream.write(partial)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        path = os.readlink('/proc/self/fd/' + str(self.stream.fileno()))
        print(json.dumps({
            'pid': os.getpid(), 'path': path, 'bytes': os.stat(path).st_size,
        }), flush=True)
        # Parent kills this owned process while the real temporary file and
        # the service's writer transaction are open. No Python cleanup runs.
        sys.stdin.readline()
        raise RuntimeError('parent must kill the paused writer')
    def flush(self):
        return self.stream.flush()
    def fileno(self):
        return self.stream.fileno()

implementation.os.fdopen = lambda fd, mode: PartialStream(real_fdopen(fd, mode))
service.submit_job(
    tenant_id='a', authorization_token='blob-budget-tenant-token-0123456789',
    idempotency_key='killed-writer', request=config['request'],
)
"""


def test_killed_real_writer_leaves_partial_staging_counted_after_reopen(tmp_path):
    value = _request("crash-left-partial-payload")
    payload = canonical(value)
    cap = len(payload)
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", _PARTIAL_STAGING_CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdin is not None and child.stdout is not None
        child.stdin.write(
            json.dumps({"root": str(tmp_path), "cap": cap, "request": value}) + "\n"
        )
        child.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=45), "writer did not stage real bytes"
        staged = json.loads(child.stdout.readline())
        assert staged["pid"] == child.pid and child.poll() is None
        path = Path(staged["path"])
        assert path.is_relative_to(tmp_path / "blobs" / "sha256")
        assert path.name.startswith(".job-blob-")
        assert staged["bytes"] == path.stat().st_size == len(payload) // 2
        assert path.read_bytes() == payload[: len(payload) // 2]
        # WAL readers observe no publication while the real writer is paused.
        assert not _state(tmp_path)["jobs"]
        child.kill()
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode is not None and child.returncode < 0
        assert not stdout and not stderr
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)
    retained = _blobs(tmp_path)
    assert retained == {path.relative_to(tmp_path).as_posix(): payload[: cap // 2]}
    assert _policy(tmp_path) == [(1, cap)]
    reopened = _service(tmp_path)
    before = _state(tmp_path)
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        _submit(reopened, _request("request-after-partial-crash"), "next")
    assert _blobs(tmp_path) == retained
    assert _state(tmp_path) == before
    assert not before["jobs"] and not before["job_events"]
