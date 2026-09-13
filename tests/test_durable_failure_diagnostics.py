"""Real failed Newton execution, durable attempts, authorization and atomicity."""

import base64
import json

import pytest

from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.nonlinear_frame_worker import (
    execute_nonlinear_frame_claim,
)
from tests.test_durable_job_service import (
    MutableClock,
    TENANT_A_TOKEN,
    TENANT_B_TOKEN,
    WORKER_TOKEN,
    _request,
    _model_ir_request,
    _service,
)


def submit_failure(service):
    request = _request()
    request["config"]["maximum_iterations"] = 1
    job = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        idempotency_key="failure-diagnostic",
        request=request,
    )
    claim = service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
    assert claim is not None
    return job, claim


def execute_failure(service, claim):
    with pytest.raises(ValueError, match="worker_result_contract_blocked"):
        execute_nonlinear_frame_claim(
            service,
            claim,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
        )


def read(service, job_id, attempt=1):
    return service.read_failure_diagnostic(
        job_id,
        attempt=attempt,
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
    )


def test_actual_failure_survives_reopen_and_retry_with_exact_http_bytes(tmp_path):
    service = _service(tmp_path)
    job, claim = submit_failure(service)
    execute_failure(service, claim)
    original = read(service, job.job_id)
    envelope = json.loads(original)
    assert envelope["binding"]["source_revision"] is None
    assert envelope["binding"]["attempt"] == 1
    source = json.loads(base64.b64decode(envelope["result_bytes_base64"]))
    assert source["metrics"]["observed_load_path"]["convergence_history_row_count"] > 0
    assert (
        source["metrics"]["observed_load_path"]["steps"][-1][
            "failed_step_rollback_exact"
        ]
        is True
    )
    service = _service(tmp_path)
    assert read(service, job.job_id) == original
    view = service.get_job(
        job.job_id, tenant_id="tenant-a", authorization_token=TENANT_A_TOKEN
    )
    assert view.status == "failed" and view.result is None and view.evidence is None
    api = DurableJobHttpApi(service)
    url = f"/v1/jobs/{job.job_id}/failure-diagnostics/1"
    headers = {
        "X-Structural-Tenant": "tenant-a",
        "Authorization": f"Bearer {TENANT_A_TOKEN}",
    }
    response = api.handle("GET", url, headers=headers)
    assert response.status == 200 and response.body == original
    assert api.handle("GET", url).status == 401
    assert (
        api.handle(
            "GET",
            url,
            headers={
                "X-Structural-Tenant": "tenant-b",
                "Authorization": f"Bearer {TENANT_B_TOKEN}",
            },
        ).status
        == 404
    )
    assert api.handle("GET", url, headers=headers, body=b"{}").status == 400
    assert api.handle("GET", url[:-1] + "2", headers=headers).status == 404
    service.resume_failed_job(
        job.job_id,
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        expected_request_hash=job.request.content_hash,
        expected_checkpoint_hash=None,
    )
    retry = service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
    assert retry is not None and retry.job.attempt == 2
    execute_failure(service, retry)
    assert read(service, job.job_id) == original
    assert json.loads(read(service, job.job_id, 2))["binding"]["attempt"] == 2
    with pytest.raises(JobServiceError):
        service.fail_job(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
            error_code="stale",
            nonlinear_failure_result_bytes=base64.b64decode(
                envelope["result_bytes_base64"]
            ),
        )
    assert read(service, job.job_id) == original


def test_failed_transition_rolls_back_diagnostic_reference(tmp_path, monkeypatch):
    service = _service(tmp_path)
    job, claim = submit_failure(service)
    transition = service._transition

    def interrupted(*args, **kwargs):
        if kwargs.get("event_type") == "failed":
            raise RuntimeError("injected transaction interruption")
        return transition(*args, **kwargs)

    monkeypatch.setattr(service, "_transition", interrupted)
    with pytest.raises(RuntimeError, match="transaction interruption"):
        execute_nonlinear_frame_claim(
            service, claim, worker_id="worker-a", authorization_token=WORKER_TOKEN
        )
    assert (
        service.get_job(
            job.job_id, tenant_id="tenant-a", authorization_token=TENANT_A_TOKEN
        ).status
        == "running"
    )
    with pytest.raises(JobServiceError, match="failure_diagnostic_not_recorded"):
        read(service, job.job_id)
    monkeypatch.setattr(service, "_transition", transition)
    execute_failure(service, claim)
    assert json.loads(read(service, job.job_id))["binding"]["attempt"] == 1


def test_missing_attempt_record_is_detected_by_event_chain(tmp_path):
    service = _service(tmp_path)
    job, claim = submit_failure(service)
    execute_failure(service, claim)
    with service._transaction() as connection:
        connection.execute(
            "DELETE FROM job_failure_diagnostics WHERE job_id = ?", (job.job_id,)
        )
    with pytest.raises(JobServiceError, match="failure_diagnostic_integrity_failed"):
        read(service, job.job_id)


def test_expired_lease_cannot_attach_diagnostic(tmp_path):
    clock = MutableClock()
    service = _service(tmp_path, clock=clock)
    job, claim = submit_failure(service)
    clock.advance(1000)
    with pytest.raises(JobServiceError):
        service.fail_job(
            job.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=claim.lease_token,
            error_code="expired",
            nonlinear_failure_result_bytes=b"{}",
        )
    with pytest.raises(JobServiceError, match="failure_diagnostic_not_recorded"):
        read(service, job.job_id)


@pytest.mark.parametrize("change", ["model", "config", "profile"])
def test_service_rejects_failure_from_different_immutable_input(tmp_path, change):
    service = _service(tmp_path)
    job, claim = submit_failure(service)
    execute_failure(service, claim)
    source = base64.b64decode(
        json.loads(read(service, job.job_id))["result_bytes_base64"]
    )
    request = _request()
    request["config"]["maximum_iterations"] = 1
    if change == "model":
        request["model"]["nodes"][2]["coordinates"][1] = 3.1
    elif change == "config":
        request["config"]["maximum_iterations"] = 2
    else:
        request["config"]["profile"] = "corotational_connected_frame2d.v1"
    other = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        idempotency_key="different-input",
        request=request,
    )
    lease = service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
    assert lease is not None and lease.job.job_id == other.job_id
    with pytest.raises(ValueError):
        service.fail_job(
            other.job_id,
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
            lease_token=lease.lease_token,
            error_code="wrong_source",
            nonlinear_failure_result_bytes=source,
        )
    assert (
        service.get_job(
            other.job_id, tenant_id="tenant-a", authorization_token=TENANT_A_TOKEN
        ).status
        == "running"
    )
    with pytest.raises(JobServiceError, match="failure_diagnostic_not_recorded"):
        read(service, other.job_id)


def test_model_ir_failure_uses_submitted_document_identity(tmp_path):
    from structural_analysis.model_ir import parse_model_ir_v2

    service = _service(tmp_path)
    request = _model_ir_request()
    request["config"]["maximum_iterations"] = 1
    job = service.submit_job(
        tenant_id="tenant-a",
        authorization_token=TENANT_A_TOKEN,
        idempotency_key="model-ir-failure",
        request=request,
    )
    claim = service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
    assert claim is not None
    execute_failure(service, claim)
    envelope = json.loads(read(service, job.job_id))
    assert (
        envelope["binding"]["input_checksum"]
        == parse_model_ir_v2(request["model"]).content_hash
    )
