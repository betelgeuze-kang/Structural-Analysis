"""HTTP storage capacity boundaries; no solver or physical validation runs."""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

import pytest

from structural_analysis.execution.job_http_api import (
    JOB_HTTP_API_PROFILE,
    DurableJobHttpApi,
)
from structural_analysis.execution.job_service import DurableJobService
from tests.test_durable_job_service import MutableClock, _request as planar_request
from tests.test_rc_fiber_job_service import canonical, request as rc_request


TENANT = "blob-http-tenant-token-0123456789"
OTHER = "blob-http-other-token-0123456789"
WORKER = "blob-http-worker-token-0123456789"
OTHER_WORKER = "blob-http-other-worker-token-0123456789"


def _service(root: Path, cap: int, clock=None) -> DurableJobService:
    return DurableJobService(
        root,
        tenant_tokens={"a": TENANT, "b": OTHER},
        worker_tokens={"worker-a": WORKER, "worker-b": OTHER_WORKER},
        worker_tenants={"worker-a": {"a"}, "worker-b": {"b"}},
        clock=clock,
        max_blob_payload_bytes=cap,
    )


def _headers(key="first") -> dict[str, str]:
    return {
        "Authorization": "Bearer " + TENANT,
        "X-Structural-Tenant": "a",
        "Idempotency-Key": key,
    }


def _post(app, value, key="first", headers=None):
    return app.handle(
        "POST",
        "/v1/jobs",
        headers=_headers(key) if headers is None else headers,
        body=canonical(value),
    )


def _assert_error(response, status: int, code: str):
    assert response.status == status
    body = json.loads(response.body)
    assert set(body) == {"schema_version", "status", "error", "api_profile"}
    assert body["schema_version"] == "structural-analysis-job-http-error.v1"
    assert body["api_profile"] == JOB_HTTP_API_PROFILE
    assert body["status"] == "error"
    assert set(body["error"]) == {"code", "detail"}
    assert body["error"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "application/json"
    for token in (TENANT, OTHER, WORKER, OTHER_WORKER):
        assert token.encode() not in response.body


def _namespace(root: Path) -> dict[str, tuple]:
    """Observe entries without following links or opening special files."""
    observed = {}

    def visit(path: Path):
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        if stat.S_ISREG(info.st_mode):
            detail = hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISLNK(info.st_mode):
            detail = os.readlink(path)
        else:
            detail = None
        observed[name] = (stat.S_IFMT(info.st_mode), info.st_size, detail)
        if stat.S_ISDIR(info.st_mode):
            for entry in sorted(path.iterdir()):
                visit(entry)

    visit(root / "blobs" / "sha256")
    return observed


def _sql_state(root: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(f"file:{root / 'jobs.sqlite3'}?mode=ro", uri=True) as db:
        names = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {
            name: db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
            for name in names
        }


def _second(value: dict) -> dict:
    value = deepcopy(value)
    value["case_id"] = "distinct-storage-capacity-request"
    return value


def _worker_body(claim, **extra) -> bytes:
    return canonical(
        {"worker_id": "worker-a", "lease_token": claim.lease_token, **extra}
    )


def _checkpoint_body(claim, *, lease_token=None, progress=1) -> bytes:
    return canonical(
        {
            "worker_id": "worker-a",
            "lease_token": claim.lease_token if lease_token is None else lease_token,
            "checkpoint_base64": base64.b64encode(
                b"synthetic storage checkpoint"
            ).decode(),
            "checkpoint_media_type": "application/json",
            "progress_completed": progress,
            "progress_total": claim.job.progress_total,
            "resume_contract_hash": "sha256:" + "a" * 64,
        }
    )


def _claim(service):
    claim = service.claim_next(
        worker_id="worker-a", authorization_token=WORKER, lease_seconds=5
    )
    assert claim is not None
    return claim


def test_capacity_is_http_503_with_exact_envelope_and_no_rejected_mutation(tmp_path):
    value = rc_request()
    app = DurableJobHttpApi(_service(tmp_path, len(canonical(value))))
    first = _post(app, value)
    assert first.status == 202
    before_files = _namespace(tmp_path)
    before_sql = _sql_state(tmp_path)
    _assert_error(
        _post(app, _second(value), "second"), 503, "blob_payload_budget_exceeded"
    )
    assert _namespace(tmp_path) == before_files
    assert _sql_state(tmp_path) == before_sql
    # Exact retry is still usable and does not write a second payload/event.
    assert _post(app, deepcopy(value)).body == first.body
    assert _namespace(tmp_path) == before_files
    assert _sql_state(tmp_path) == before_sql
    job_id = json.loads(first.body)["job_id"]
    read = app.handle("GET", f"/v1/jobs/{job_id}/request", headers=_headers())
    assert read.status == 200 and read.body == canonical(value)


@pytest.mark.parametrize(
    "kind",
    ["unexpected_file", "symlink_root", "symlink_prefix", "symlink_file", "fifo"],
)
def test_real_unsafe_namespace_returns_http_503_without_follow_or_cleanup(
    tmp_path, kind
):
    value = rc_request()
    app = DurableJobHttpApi(_service(tmp_path, 1024 * 1024))
    blob_root = tmp_path / "blobs" / "sha256"
    outside = tmp_path / "outside-payload"
    outside.write_bytes(b"outside bytes must not be read, changed or removed")
    prefix = blob_root / "aa"
    if kind == "unexpected_file":
        (blob_root / "unexpected-entry").write_bytes(b"retained invalid entry")
    elif kind == "symlink_root":
        preserved = tmp_path / "preserved-sha256"
        blob_root.rename(preserved)
        blob_root.symlink_to(preserved, target_is_directory=True)
    elif kind == "symlink_prefix":
        prefix.symlink_to(tmp_path, target_is_directory=True)
    else:
        prefix.mkdir()
        target = prefix / ("a" * 64)
        if kind == "symlink_file":
            target.symlink_to(outside)
        else:
            os.mkfifo(target)
    outside_before = (outside.read_bytes(), outside.stat().st_size)
    before_files = _namespace(tmp_path)
    before_sql = _sql_state(tmp_path)
    _assert_error(_post(app, value), 503, "blob_payload_inventory_invalid")
    assert _namespace(tmp_path) == before_files
    assert _sql_state(tmp_path) == before_sql
    assert (outside.read_bytes(), outside.stat().st_size) == outside_before


@pytest.mark.parametrize("location", ["request", "execution_config"])
def test_clients_cannot_override_constructor_budget_at_either_request_level(
    tmp_path, location
):
    value = rc_request()
    app = DurableJobHttpApi(_service(tmp_path, 1))
    if location == "request":
        value["max_blob_payload_bytes"] = 2**63 - 1
    else:
        value["execution_config"]["max_blob_payload_bytes"] = 2**63 - 1
    before_files = _namespace(tmp_path)
    before_sql = _sql_state(tmp_path)
    _assert_error(_post(app, value), 400, "job_schema_invalid")
    assert _namespace(tmp_path) == before_files
    assert _sql_state(tmp_path) == before_sql


@pytest.mark.parametrize("invalid_inventory", [False, True])
def test_original_auth_idempotency_contract_and_lease_errors_precede_storage(
    tmp_path, invalid_inventory
):
    value = planar_request()
    clock = MutableClock()
    service = _service(tmp_path, len(canonical(value)), clock)
    app = DurableJobHttpApi(service)
    first = _post(app, value)
    assert first.status == 202
    claim = _claim(service)
    job_id = claim.job.job_id
    if invalid_inventory:
        (tmp_path / "blobs" / "sha256" / "unexpected-entry").write_bytes(b"unsafe")
    before_files = _namespace(tmp_path)
    before_sql = _sql_state(tmp_path)
    _assert_error(
        _post(
            app,
            _second(value),
            "next",
            headers={
                **_headers("next"),
                "Authorization": "Bearer wrong-token-with-valid-length",
            },
        ),
        401,
        "tenant_unauthorized",
    )
    _assert_error(_post(app, _second(value)), 409, "idempotency_conflict")
    invalid = _second(value)
    invalid["config"]["load_steps"] = False
    _assert_error(_post(app, invalid, "invalid"), 400, "job_schema_invalid")
    _assert_error(
        app.handle(
            "GET",
            f"/v1/jobs/{job_id}",
            headers={"Authorization": "Bearer " + OTHER, "X-Structural-Tenant": "b"},
        ),
        404,
        "job_not_found",
    )
    worker_headers = {"Authorization": "Bearer " + WORKER}
    route = f"/v1/worker/jobs/{job_id}/checkpoint"
    _assert_error(
        app.handle(
            "POST",
            route,
            headers={"Authorization": "Bearer wrong-worker-with-valid-length"},
            body=_checkpoint_body(claim),
        ),
        401,
        "worker_unauthorized",
    )
    other_worker_body = json.loads(_checkpoint_body(claim))
    other_worker_body["worker_id"] = "worker-b"
    _assert_error(
        app.handle(
            "POST",
            route,
            headers={"Authorization": "Bearer " + OTHER_WORKER},
            body=canonical(other_worker_body),
        ),
        403,
        "worker_tenant_forbidden",
    )
    _assert_error(
        app.handle(
            "POST",
            route,
            headers=worker_headers,
            body=_checkpoint_body(claim, lease_token="wrong-lease-token"),
        ),
        409,
        "lease_unauthorized",
    )
    _assert_error(
        app.handle(
            "POST",
            route,
            headers=worker_headers,
            body=_checkpoint_body(claim, progress=0),
        ),
        400,
        "checkpoint_progress_invalid",
    )
    # This valid lease and semantically valid legacy storage checkpoint reaches
    # admission; its rejection must keep both blob and durable state unchanged.
    _assert_error(
        app.handle("POST", route, headers=worker_headers, body=_checkpoint_body(claim)),
        503,
        "blob_payload_inventory_invalid"
        if invalid_inventory
        else "blob_payload_budget_exceeded",
    )
    clock.advance(6)
    _assert_error(
        app.handle("POST", route, headers=worker_headers, body=_checkpoint_body(claim)),
        409,
        "lease_expired",
    )
    assert _namespace(tmp_path) == before_files
    assert _sql_state(tmp_path) == before_sql


@pytest.mark.parametrize("invalid_inventory", [False, True])
@pytest.mark.parametrize("operation", ["heartbeat", "fail", "cancel", "recover"])
def test_reads_and_no_blob_lifecycle_continue_at_storage_boundary(
    tmp_path, invalid_inventory, operation
):
    value = planar_request()
    clock = MutableClock()
    service = _service(tmp_path, len(canonical(value)), clock)
    app = DurableJobHttpApi(service)
    submitted = _post(app, value)
    assert submitted.status == 202
    job_id = json.loads(submitted.body)["job_id"]
    # The existing cancellation contract accepts queued/checkpointed jobs.
    # Other no-blob operations require the existing running worker lease.
    claim = None if operation == "cancel" else _claim(service)
    if invalid_inventory:
        (tmp_path / "blobs" / "sha256" / "unexpected-entry").write_bytes(b"unsafe")
    before_files = _namespace(tmp_path)
    for suffix in ("", "/request"):
        read = app.handle("GET", f"/v1/jobs/{job_id}{suffix}", headers=_headers())
        assert read.status == 200
        if suffix:
            assert read.body == canonical(value)
    worker_headers = {"Authorization": "Bearer " + WORKER}
    if operation == "cancel":
        response = app.handle("POST", f"/v1/jobs/{job_id}/cancel", headers=_headers())
        assert (
            response.status == 200
            and json.loads(response.body)["status"] == "cancelled"
        )
    elif operation == "recover":
        assert claim is not None
        clock.advance(6)
        response = app.handle(
            "POST",
            "/v1/worker/claims",
            headers=worker_headers,
            body=canonical({"worker_id": "worker-a", "lease_seconds": 5}),
        )
        assert response.status == 200
        recovered = json.loads(response.body)
        assert recovered["job"]["job_id"] == job_id
        assert recovered["job"]["attempt"] == claim.job.attempt + 1
        assert recovered["lease_token"] != claim.lease_token
    else:
        assert claim is not None
        extra = (
            {"lease_seconds": 5}
            if operation == "heartbeat"
            else {"error_code": "synthetic_storage_failure", "retriable": False}
        )
        response = app.handle(
            "POST",
            f"/v1/worker/jobs/{job_id}/{operation}",
            headers=worker_headers,
            body=_worker_body(claim, **extra),
        )
        assert response.status == 200
        assert json.loads(response.body)["status"] == (
            "running" if operation == "heartbeat" else "failed"
        )
    assert _namespace(tmp_path) == before_files


def test_malformed_persisted_policy_is_http_503_and_cannot_be_bypassed(tmp_path):
    value = rc_request()
    app = DurableJobHttpApi(_service(tmp_path, len(canonical(value))))
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
        db.execute("PRAGMA ignore_check_constraints = ON")
        db.execute("UPDATE job_blob_payload_policy SET maximum_bytes = 'malformed'")
    before_files = _namespace(tmp_path)
    before_sql = _sql_state(tmp_path)
    _assert_error(_post(app, value), 503, "blob_payload_policy_invalid")
    _assert_error(
        _post(
            app,
            value,
            headers={
                **_headers(),
                "Authorization": "Bearer wrong-token-with-valid-length",
            },
        ),
        401,
        "tenant_unauthorized",
    )
    assert _namespace(tmp_path) == before_files
    assert _sql_state(tmp_path) == before_sql
