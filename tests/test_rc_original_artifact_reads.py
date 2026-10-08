"""Authenticated original-byte reads over genuine RC worker artifacts.

Only module fixture creation executes numerical work. Read tests forbid solver
entrypoints and never inject a completed result or checkpoint.
"""

from dataclasses import replace
import hashlib
import json
import shutil
import sqlite3

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as path
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)
from .test_rc_real_process_lifecycle import TENANTS, request, service, tenant, worker


@pytest.fixture(scope="module")
def genuine_stores(tmp_path_factory):
    directory = tmp_path_factory.mktemp("genuine-rc-originals")
    root = directory / "complete"
    current = service(root)
    job = current.submit_job(**tenant(), idempotency_key="originals", request=request())
    claim = current.claim_next(**worker("first"))
    checkpointed = execute_rc_fiber_direct_control_claim(
        current, claim, **worker("first")
    )
    assert checkpointed.status == "checkpointed"
    partial = directory / "partial"
    shutil.copytree(root, partial)
    claim = current.claim_next(**worker("fresh"))
    complete = execute_rc_fiber_direct_control_claim(current, claim, **worker("fresh"))
    assert complete.status == "succeeded"
    return {"complete": root, "partial": partial, "job_id": job.job_id}


@pytest.fixture
def originals(genuine_stores, tmp_path):
    root = tmp_path / "store"
    shutil.copytree(genuine_stores["complete"], root)
    return service(root), genuine_stores["job_id"]


@pytest.fixture(autouse=True)
def no_numerical_dispatch(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Original artifact retrieval must never execute a solver")

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(path, "_execute_raw", forbidden)


def headers(name="a"):
    return {"X-Structural-Tenant": name, "Authorization": f"Bearer {TENANTS[name]}"}


def read_http(current, job_id, role, **kwargs):
    return DurableJobHttpApi(current).handle(
        "GET",
        f"/v1/jobs/{job_id}/{role}",
        headers=kwargs.pop("headers", headers()),
        **kwargs,
    )


def database_rows(current):
    with sqlite3.connect(current.root / "jobs.sqlite3") as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in (
                "jobs",
                "job_events",
                "job_execution_budgets",
                "job_rc_invocation_outcomes",
            )
        }


@pytest.mark.parametrize("role", ["request", "checkpoint"])
def test_exact_original_bytes_media_hash_and_no_state_mutation(originals, role):
    current, job_id = originals
    job = current.get_job(job_id, **tenant())
    reference = getattr(job, role)
    expected = current._blob_path(reference.content_hash).read_bytes()
    before = database_rows(current)
    result = read_http(current, job_id, role)
    assert result.status == 200 and result.body == expected
    assert result.headers["content-type"] == reference.media_type
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["x-structural-artifact-sha256"] == reference.content_hash
    assert "sha256:" + hashlib.sha256(result.body).hexdigest() == reference.content_hash
    assert len(result.body) == reference.byte_length
    assert json.loads(result.body)["schema_version"]
    assert database_rows(current) == before


@pytest.mark.parametrize("role", ["request", "checkpoint"])
@pytest.mark.parametrize(
    "credentials,status", [(None, 401), ("wrong", 401), ("b", 404)]
)
def test_credentials_and_other_tenant_fail_closed(originals, role, credentials, status):
    current, job_id = originals
    supplied = (
        {}
        if credentials is None
        else headers(credentials)
        if credentials == "b"
        else {**headers(), "Authorization": "Bearer wrong"}
    )
    result = read_http(current, job_id, role, headers=supplied)
    assert result.status == status
    payload = json.loads(result.body)
    assert payload["schema_version"] == "structural-analysis-job-http-error.v1"
    assert payload["status"] == "error"
    assert "x-structural-artifact-sha256" not in result.headers


def test_queued_request_reads_but_missing_checkpoint_does_not_exist(tmp_path):
    current = service(tmp_path / "queued")
    job = current.submit_job(**tenant(), idempotency_key="queued", request=request())
    assert read_http(current, job.job_id, "request").status == 200
    response = read_http(current, job.job_id, "checkpoint")
    assert response.status == 400
    assert json.loads(response.body)["error"]["code"] == "artifact_not_published"
    with pytest.raises(JobServiceError, match="artifact_not_published"):
        current.read_checkpoint(job.job_id, **tenant())


@pytest.mark.parametrize("status", ["checkpointed", "running", "failed", "cancelled"])
def test_last_attached_checkpoint_available_in_supported_states(
    genuine_stores, tmp_path, status
):
    root = tmp_path / "state"
    shutil.copytree(genuine_stores["partial"], root)
    current, job_id = service(root), genuine_stores["job_id"]
    original = current.get_job(job_id, **tenant()).checkpoint
    if status in {"running", "failed"}:
        claim = current.claim_next(**worker("fresh"))
        if status == "failed":
            current.fail_job(
                job_id,
                **worker("fresh"),
                lease_token=claim.lease_token,
                error_code="test_interruption",
                retriable=False,
            )
    elif status == "cancelled":
        current.cancel_job(job_id, **tenant())
    assert current.get_job(job_id, **tenant()).status == status
    for role in ("request", "checkpoint"):
        response = read_http(current, job_id, role)
        assert response.status == 200
    assert response.headers["x-structural-artifact-sha256"] == original.content_hash


@pytest.mark.parametrize("role", ["request", "checkpoint"])
@pytest.mark.parametrize("mutation", ["bytes", "missing", "size"])
def test_corrupt_or_missing_attached_artifact_fails_closed(originals, role, mutation):
    current, job_id = originals
    reference = getattr(current.get_job(job_id, **tenant()), role)
    blob = current._blob_path(reference.content_hash)
    if mutation == "bytes":
        raw = blob.read_bytes()
        blob.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    elif mutation == "missing":
        blob.unlink()
    else:
        with sqlite3.connect(current.root / "jobs.sqlite3") as connection:
            connection.execute(
                f"UPDATE jobs SET {role}_size = {role}_size + 1 WHERE job_id = ?",
                (job_id,),
            )
    response = read_http(current, job_id, role)
    assert response.status == 400
    assert json.loads(response.body)["error"]["code"] in {
        "artifact_missing",
        "artifact_integrity_failed",
    }


def test_checkpoint_snapshot_race_never_mislabels_new_bytes(originals, monkeypatch):
    current, job_id = originals
    real_get = current.get_job

    def stale(*args, **kwargs):
        job = real_get(*args, **kwargs)
        return replace(
            job, checkpoint=replace(job.checkpoint, content_hash="sha256:" + "f" * 64)
        )

    monkeypatch.setattr(current, "get_job", stale)
    response = read_http(current, job_id, "checkpoint")
    assert response.status == 409
    assert json.loads(response.body)["error"]["code"] == "artifact_reference_changed"


@pytest.mark.parametrize("role", ["request", "checkpoint"])
def test_body_and_mutating_verbs_are_rejected(originals, role):
    current, job_id = originals
    assert read_http(current, job_id, role, body=b"{}").status == 400
    response = DurableJobHttpApi(current).handle(
        "POST", f"/v1/jobs/{job_id}/{role}", headers=headers()
    )
    assert response.status == 405


@pytest.mark.parametrize("role", ["request", "checkpoint"])
def test_service_methods_enforce_tenant_auth_without_http(originals, role):
    current, job_id = originals
    reader = getattr(current, "read_" + role)
    with pytest.raises(JobServiceError, match="tenant_unauthorized"):
        reader(job_id, tenant_id="a", authorization_token="wrong")
    with pytest.raises(JobServiceError, match="job_not_found"):
        reader(job_id, **tenant("b"))


@pytest.mark.parametrize(
    "role,maximum", [("request", 16 * 1024 * 1024), ("checkpoint", 128 * 1024 * 1024)]
)
def test_size_bound_rejects_before_blob_access(originals, monkeypatch, role, maximum):
    current, job_id = originals
    with sqlite3.connect(current.root / "jobs.sqlite3") as connection:
        connection.execute(
            f"UPDATE jobs SET {role}_size = ? WHERE job_id = ?", (maximum + 1, job_id)
        )

    def forbidden(*args):
        pytest.fail("Oversize reference must fail before filesystem access")

    monkeypatch.setattr(current, "_blob_path", forbidden)
    response = read_http(current, job_id, role)
    assert response.status == 400
    assert json.loads(response.body)["error"]["code"] == "artifact_size_invalid"
