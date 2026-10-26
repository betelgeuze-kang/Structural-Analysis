"""Tenant HTTP control contracts; all computation is forbidden in this module."""

import json
from uuid import uuid4

import pytest

from structural_analysis.execution.job_http_api import DurableJobHttpApi
from tests.test_rc_fiber_job_service import (
    OTHER,
    TENANT,
    canonical,
    claim,
    lease,
    no_solver as no_solver,
    service,
    sha,
    submit,
    tenant,
)


def headers(tenant_id="a", token=TENANT):
    return {"X-Structural-Tenant": tenant_id, "Authorization": f"Bearer {token}"}


def endpoint(job):
    return f"/v1/jobs/{job.job_id}/rc-control"


def read_control(current, job):
    response = DurableJobHttpApi(current).handle(
        "GET", endpoint(job), headers=headers()
    )
    assert response.status == 200, response.body
    return json.loads(response.body)


def command(view, action="pause", control_id=None):
    return {
        "schema_version": "rc-job-control-request.v1",
        "control_id": control_id or f"rc-control-{uuid4()}",
        "action": action,
        "expected_request_hash": view["job"]["request_hash"],
        "expected_checkpoint_hash": view["job"]["checkpoint_hash"],
        "expected_control_revision": view["control_revision"],
        "expected_attempt": view["job"]["attempt"],
    }


def send_control(current, job, payload):
    response = DurableJobHttpApi(current).handle(
        "POST", endpoint(job), headers=headers(), body=canonical(payload)
    )
    assert response.status == 200, response.body
    return json.loads(response.body)


def test_control_http_is_tenant_scoped_read_only_and_lease_secret_free(
    tmp_path, monkeypatch
):
    current = service(tmp_path)
    job = submit(current)
    app = DurableJobHttpApi(current)
    before = current.get_job(job.job_id, **tenant()).to_dict()

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Control metadata must not hydrate full saved artifacts or invocation outcomes"
        )

    for name in (
        "_validate_integrity_snapshot",
        "_rc_invocation_rows",
        "_checkpoint_for_row",
    ):
        monkeypatch.setattr(current, name, forbidden)
    view = read_control(current, job)
    assert view["state"] == "available" and view["last_command"] is None
    assert view["control_revision"] == 0
    assert view["can_pause"] and view["can_cancel"]
    assert not view["can_resume_control"]
    assert current.get_job(job.job_id, **tenant()).to_dict() == before
    for method, body in (("GET", b""), ("POST", canonical(command(view)))):
        foreign = app.handle(
            method, endpoint(job), headers=headers("b", OTHER), body=body
        )
        assert foreign.status == 404
        absent = app.handle(
            method, endpoint(job), headers={"X-Structural-Tenant": "a"}, body=body
        )
        assert absent.status == 401
        wrong = app.handle(
            method, endpoint(job), headers=headers("a", OTHER), body=body
        )
        assert wrong.status == 401
        for response in (foreign, absent, wrong):
            assert TENANT.encode() not in response.body
            assert b"lease_token" not in response.body
    assert current.get_job(job.job_id, **tenant()).to_dict() == before
    response = app.handle("GET", endpoint(job), headers=headers())
    assert response.headers["cache-control"] == "no-store"
    assert b"lease_token" not in response.body


def test_old_command_receipt_and_latest_control_view_remain_distinct(tmp_path):
    current = service(tmp_path)
    job = submit(current)
    original = current.get_job(job.job_id, **tenant()).to_dict()
    pause = command(read_control(current, job))
    accepted = send_control(current, job, pause)
    assert set(accepted) == {
        "schema_version",
        "control_id",
        "command_hash",
        "accepted_control_revision",
        "view",
    }
    assert accepted["schema_version"] == "rc-job-control-command-result.v1"
    assert accepted["command_hash"] == sha(canonical(pause))
    assert accepted["accepted_control_revision"] == 1
    assert accepted["view"]["state"] == "paused"
    resume = command(accepted["view"], "resume")
    resumed = send_control(current, job, resume)
    assert resumed["view"]["state"] == "available"
    snapshot = current.get_job(job.job_id, **tenant()).to_dict()
    retry = send_control(current, job, pause)
    assert retry["control_id"] == pause["control_id"]
    assert retry["accepted_control_revision"] == 1
    assert retry["command_hash"] == accepted["command_hash"]
    assert retry["view"] == resumed["view"]
    assert retry["view"]["last_command"]["control_id"] == resume["control_id"]
    assert current.get_job(job.job_id, **tenant()).to_dict() == snapshot
    assert snapshot["request"] == original["request"]
    assert snapshot["attempt"] == original["attempt"]
    assert current.validate_integrity(job.job_id, **tenant())["contract_pass"]
    altered = {**pause, "action": "cancel"}
    rejected = DurableJobHttpApi(current).handle(
        "POST", endpoint(job), headers=headers(), body=canonical(altered)
    )
    assert rejected.status == 409
    assert json.loads(rejected.body)["error"]["code"] == "rc_control_id_conflict"
    assert current.get_job(job.job_id, **tenant()).to_dict() == snapshot


def test_control_cas_ignores_heartbeat_revision_but_rejects_new_stale_command(tmp_path):
    current = service(tmp_path)
    job = submit(current)
    active = claim(current)
    observed = read_control(current, job)
    current.heartbeat(job.job_id, **lease(active), lease_seconds=5)
    pause = command(observed)
    accepted = send_control(current, job, pause)
    assert accepted["view"]["state"] == "pause_pending"
    assert accepted["view"]["job"]["status"] == "running"
    snapshot = current.get_job(job.job_id, **tenant()).to_dict()
    stale = command(observed, "cancel")
    result = DurableJobHttpApi(current).handle(
        "POST", endpoint(job), headers=headers(), body=canonical(stale)
    )
    assert result.status == 409
    assert json.loads(result.body)["error"]["code"] == "rc_control_source_conflict"
    assert current.get_job(job.job_id, **tenant()).to_dict() == snapshot


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": True},
        {"expected_attempt": True},
        {"expected_control_revision": False},
        {"expected_attempt": -1},
        {"expected_control_revision": 0.5},
        {"action": "stop"},
        {"expected_request_hash": "a" * 64},
        {"expected_checkpoint_hash": "invalid"},
        {"control_id": "rc-control-not-a-uuid"},
        {"schema_version": "rc-job-control-request.v2"},
    ],
)
def test_malformed_control_fields_never_append_events(tmp_path, change):
    current = service(tmp_path)
    job = submit(current)
    before = current.get_job(job.job_id, **tenant()).to_dict()
    payload = {**command(read_control(current, job)), **change}
    response = DurableJobHttpApi(current).handle(
        "POST", endpoint(job), headers=headers(), body=canonical(payload)
    )
    assert response.status == 400
    assert current.get_job(job.job_id, **tenant()).to_dict() == before


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b"null",
        b"\xff",
        b'{"action":"pause","action":"cancel"}',
        b'{"expected_attempt":NaN}',
    ],
)
def test_malformed_control_json_is_rejected_without_mutation(tmp_path, body):
    current = service(tmp_path)
    job = submit(current)
    before = current.get_job(job.job_id, **tenant()).to_dict()
    response = DurableJobHttpApi(current).handle(
        "POST", endpoint(job), headers=headers(), body=body
    )
    assert response.status == 400
    assert current.get_job(job.job_id, **tenant()).to_dict() == before


def test_control_route_method_body_and_size_bounds(tmp_path):
    current = service(tmp_path)
    job = submit(current)
    app = DurableJobHttpApi(current)
    before = current.get_job(job.job_id, **tenant()).to_dict()
    assert app.handle("GET", endpoint(job), headers=headers(), body=b"{}").status == 400
    for method in ("PUT", "PATCH", "DELETE"):
        assert app.handle(method, endpoint(job), headers=headers()).status == 405
    for suffix in ("?action=cancel", "#cancel", "/resume"):
        assert (
            app.handle(
                "POST", endpoint(job) + suffix, headers=headers(), body=b"{}"
            ).status
            == 404
        )
    assert (
        app.handle(
            "POST", endpoint(job), headers=headers(), body=b" " * (16 * 1024 + 1)
        ).status
        == 413
    )
    assert current.get_job(job.job_id, **tenant()).to_dict() == before


def test_legacy_cancel_cannot_bypass_control_cas_on_paused_job(tmp_path):
    current = service(tmp_path)
    job = submit(current)
    paused = send_control(current, job, command(read_control(current, job)))
    result = DurableJobHttpApi(current).handle(
        "POST", f"/v1/jobs/{job.job_id}/cancel", headers=headers()
    )
    assert result.status == 409
    assert json.loads(result.body)["error"]["code"] == "rc_control_route_required"
    assert read_control(current, job) == paused["view"]


def test_control_route_rejects_generic_frame_without_changing_legacy_cancel(tmp_path):
    from tests.test_durable_job_service import _request

    current = service(tmp_path)
    job = submit(current, payload=_request())
    app = DurableJobHttpApi(current)
    before = current.get_job(job.job_id, **tenant()).to_dict()
    unsupported = app.handle("GET", endpoint(job), headers=headers())
    assert unsupported.status == 400
    assert (
        json.loads(unsupported.body)["error"]["code"]
        == "rc_control_operation_unsupported"
    )
    assert current.get_job(job.job_id, **tenant()).to_dict() == before
    cancelled = app.handle("POST", f"/v1/jobs/{job.job_id}/cancel", headers=headers())
    assert cancelled.status == 200
    assert json.loads(cancelled.body)["status"] == "cancelled"
