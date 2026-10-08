"""Synthetic trusted-worker seams test report custody, never solver truth.

The original RC result validator alone is stubbed in the synthetic completed
job fixture. Real request compilation, service evidence/invocation bindings,
report quantities/prices, authorization, transactions and blob reads remain.
"""

from copy import deepcopy
import json
import sqlite3

import pytest

from structural_analysis.execution import job_http_api as http
from structural_analysis.execution import rc_fiber_job_contract as contract
from structural_analysis.execution.job_service import (
    JobServiceError,
    build_job_completion_evidence,
)
from . import test_rc_fiber_job_service as seams
from .test_rc_fiber_quantity_report import (
    no_numerical_execution as no_numerical_execution,
)
from .test_rc_fiber_quantity_report import prices


@pytest.fixture
def completed(tmp_path, monkeypatch):
    service = seams.service(tmp_path / "store")
    request = seams.request()
    request["config"]["targets_m"] = [-0.0001]
    seams.submit(service, request)
    claim = seams.claim(service)
    receipt = seams.synthetic_pair(service, claim)
    receipt["receipt_hash"] = contract._hash(receipt)
    model, _ = contract.validate_rc_fiber_job_request(request)
    value = {
        "schema_version": request["result_contract"],
        "synthetic_orchestration_only": True,
        "receipts": [receipt],
        "profile": contract.RC_FIBER_JOB_PROFILE,
        "request_hash": contract.rc_fiber_job_request_hash(request),
        "resume_contract_hash": contract.rc_fiber_job_resume_contract_hash(request),
        "api_result": {
            "result_hash": seams.RESUME,
            "model": {
                "canonical_model_checksum": model.canonical_model_checksum,
                "compiler_profile": "synthetic-pure-contract-seam",
            },
        },
        "authority": dict(contract.RC_FIBER_JOB_AUTHORITY),
    }
    value["result_hash"] = contract._hash(value)
    validation = {
        "contract_pass": True,
        "result_hash": value["result_hash"],
        "receipt_hashes": [receipt["receipt_hash"]],
        "synthetic_pure_contract_seam": True,
    }
    monkeypatch.setattr(
        contract,
        "validate_rc_fiber_job_result",
        lambda *args, **kwargs: deepcopy(validation),
    )
    raw = seams.canonical(value)
    proof = build_job_completion_evidence(
        job_id=claim.job.job_id,
        request_hash=claim.job.request.content_hash,
        checkpoint_hash=None,
        result_bytes=raw,
        validation_report=validation,
        validator_id=contract.RC_FIBER_JOB_VALIDATOR_ID,
    )
    job = service.complete_job(
        claim.job.job_id,
        **seams.lease(claim),
        result_bytes=raw,
        result_media_type="application/json",
        evidence=proof,
    )
    return service, job


def source(job):
    return {
        "expected_request_hash": job.request.content_hash,
        "expected_result_artifact_hash": job.result.content_hash,
    }


def create(service, job, declaration=None):
    return service.create_rc_quantity_report(
        job.job_id, **seams.tenant(), **source(job), declared_prices=declaration
    )


def read(service, job, reference):
    return service.read_rc_quantity_report(
        job.job_id, reference["report_id"], **seams.tenant()
    )


def numerical_state(service, job):
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        return {
            table: connection.execute(
                f"SELECT * FROM {table} WHERE job_id = ? ORDER BY 1, 2", (job.job_id,)
            ).fetchall()
            for table in (
                "jobs",
                "job_events",
                "job_rc_invocation_outcomes",
                "job_execution_budgets",
            )
        }


def test_reprice_reopen_and_raw_download_preserve_original_numerical_state(completed):
    service, job = completed
    before = numerical_state(service, job)
    empty = create(service, job)
    first = create(service, job, prices())
    second = create(service, job, prices(source="later caller declaration"))
    assert [r["revision"] for r in (empty, first, second)] == [1, 2, 3]
    assert create(service, job, prices()) == first
    old_raw = read(service, job, first)
    reopened = seams.service(service.root)
    assert read(reopened, job, first) == old_raw
    index = reopened.list_rc_quantity_reports(
        job.job_id, **seams.tenant(), after_revision=1, limit=1
    )
    assert index["reports"] == [first] and index["next_after_revision"] == 2
    body = json.loads(old_raw)
    assert body["bindings"]["original_artifacts"]["checkpoint"] is None
    assert body["bindings"]["terminal_native_checkpoint_sha256"] == seams.sha(
        b"synthetic-checkpoint"
    )
    assert json.loads(read(service, job, empty))["material_estimate"] is None
    assert numerical_state(service, job) == before
    response = http.DurableJobHttpApi(reopened).handle(
        "GET",
        f"/v1/jobs/{job.job_id}/rc-quantity-reports/{first['report_id']}",
        headers={"X-Structural-Tenant": "a", "Authorization": f"Bearer {seams.TENANT}"},
    )
    assert response.status == 200 and response.body == old_raw
    assert response.headers["x-structural-report-sha256"] == first["content_hash"]
    assert "attachment" in response.headers["content-disposition"]


def test_signed_zero_and_integer_prices_share_normalized_raw_revision(completed):
    service, job = completed
    first = create(service, job, prices(concrete_per_m3=0, rebar_per_kg=0))
    assert (
        create(service, job, prices(concrete_per_m3=-0.0, rebar_per_kg=-0.0)) == first
    )
    assert create(service, job, prices(concrete_per_m3=0.0, rebar_per_kg=0.0)) == first
    assert json.loads(read(service, job, first))["material_estimate"]["total"] == 0.0


@pytest.mark.parametrize("operation", ["create", "list", "read"])
@pytest.mark.parametrize(
    "credentials",
    [
        {"tenant_id": "b", "authorization_token": seams.OTHER},
        {"tenant_id": "a", "authorization_token": "invalid"},
    ],
)
def test_other_tenant_and_invalid_token_cannot_access_companion(
    completed, operation, credentials
):
    service, job = completed
    reference = create(service, job)
    with pytest.raises(JobServiceError, match="job_not_found|tenant_unauthorized"):
        if operation == "create":
            service.create_rc_quantity_report(
                job.job_id, **credentials, **source(job), declared_prices=None
            )
        elif operation == "list":
            service.list_rc_quantity_reports(job.job_id, **credentials)
        else:
            service.read_rc_quantity_report(
                job.job_id, reference["report_id"], **credentials
            )


def test_wrong_optimistic_source_and_missing_report_are_rejected(completed):
    service, job = completed
    for key in source(job):
        arguments = {**source(job), key: "sha256:" + "f" * 64}
        with pytest.raises(JobServiceError, match="rc_quantity_source_conflict"):
            service.create_rc_quantity_report(
                job.job_id, **seams.tenant(), **arguments, declared_prices=None
            )
    with pytest.raises(JobServiceError, match="rc_quantity_report_not_found"):
        service.read_rc_quantity_report(job.job_id, "rcq_" + "f" * 64, **seams.tenant())


def test_coherent_report_rehash_cannot_replace_quantity_derivation(completed):
    service, job = completed
    reference = create(service, job, prices())
    value = json.loads(read(service, job, reference))
    value["quantities"]["members"][0]["length_m"] *= 2
    value["quantities"]["quantity_hash"] = contract._hash(
        {k: v for k, v in value["quantities"].items() if k != "quantity_hash"}
    )
    value["report_hash"] = contract._hash(
        {k: v for k, v in value.items() if k != "report_hash"}
    )
    raw = seams.canonical(value)
    digest = seams.sha(raw)
    path = service.root / "blobs/sha256" / digest[7:9] / digest[7:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    identifier = "rcq_" + digest[7:]
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE job_rc_quantity_reports SET report_id=?,content_hash=?,byte_length=? WHERE job_id=?",
            (identifier, digest, len(raw), job.job_id),
        )
    with pytest.raises(JobServiceError, match="rc_quantity_report_integrity_failed"):
        service.read_rc_quantity_report(job.job_id, identifier, **seams.tenant())


def test_raw_blob_tamper_is_rejected(completed):
    service, job = completed
    reference = create(service, job)
    path = (
        service.root
        / "blobs/sha256"
        / reference["content_hash"][7:9]
        / reference["content_hash"][7:]
    )
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(JobServiceError, match="artifact_integrity_failed"):
        read(service, job, reference)


@pytest.mark.parametrize(
    "field", ["result_hash", "evidence_hash", "progress_completed"]
)
def test_completed_event_custody_and_success_projection_are_required(completed, field):
    service, job = completed
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        if field == "progress_completed":
            connection.execute(
                "UPDATE jobs SET progress_completed=0 WHERE job_id=?", (job.job_id,)
            )
        else:
            ref = getattr(job, "result" if field == "result_hash" else "evidence")
            payload = service._blob_path(ref.content_hash).read_bytes() + b"\n"
            digest = seams.sha(payload)
            path = service._blob_path(digest)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            size_field = "result_size" if field == "result_hash" else "evidence_size"
            connection.execute(
                f"UPDATE jobs SET {field}=?,{size_field}=? WHERE job_id=?",
                (digest, len(payload), job.job_id),
            )
            if field == "result_hash":
                # Preserve every other parsed binding, including the updated
                # evidence's raw-result hash. Only the completed event still
                # records the original byte set; a generic semantic check
                # alone must not admit this coherent custody replacement.
                evidence = json.loads(
                    service._blob_path(job.evidence.content_hash).read_bytes()
                )
                evidence["result_artifact_hash"] = digest
                rewritten = seams.canonical(evidence)
                evidence_digest = seams.sha(rewritten)
                evidence_path = service._blob_path(evidence_digest)
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_path.write_bytes(rewritten)
                connection.execute(
                    "UPDATE jobs SET evidence_hash=?,evidence_size=? WHERE job_id=?",
                    (evidence_digest, len(rewritten), job.job_id),
                )
    updated = service.get_job(job.job_id, **seams.tenant())
    with pytest.raises(JobServiceError):
        create(service, updated)
    assert (
        service.list_rc_quantity_reports(job.job_id, **seams.tenant())["reports"] == []
    )


@pytest.mark.parametrize("failure", ["blob", "index"])
def test_storage_failure_never_publishes_report_index(completed, monkeypatch, failure):
    service, job = completed
    before = numerical_state(service, job)
    if failure == "blob":

        def fail(*args, **kwargs):
            raise JobServiceError(
                "artifact_write_failed", "/report", "Injected task-owned failure"
            )

        monkeypatch.setattr(service, "_put_blob", fail)
    else:
        with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
            connection.execute(
                "CREATE TRIGGER reject_report BEFORE INSERT ON job_rc_quantity_reports BEGIN SELECT RAISE(ABORT, 'injected report-index failure'); END"
            )
    with pytest.raises(JobServiceError):
        create(service, job)
    assert (
        service.list_rc_quantity_reports(job.job_id, **seams.tenant())["reports"] == []
    )
    assert numerical_state(service, job) == before


@pytest.mark.parametrize(
    "status", ["queued", "running", "checkpointed", "failed", "cancelled"]
)
def test_non_success_cannot_create_report(tmp_path, monkeypatch, status):
    service = seams.service(tmp_path)
    job = seams.submit(service)
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE jobs SET status=? WHERE job_id=?", (status, job.job_id)
        )
    monkeypatch.setattr(service, "validate_integrity", lambda *args, **kwargs: {})
    with pytest.raises(JobServiceError, match="rc_quantity_job_not_succeeded"):
        service.create_rc_quantity_report(
            job.job_id,
            **seams.tenant(),
            expected_request_hash=job.request.content_hash,
            expected_result_artifact_hash="sha256:" + "a" * 64,
            declared_prices=None,
        )


def test_http_create_exact_fields_bounds_and_pagination(completed):
    service, job = completed
    transport = http.DurableJobHttpApi(service)
    path = f"/v1/jobs/{job.job_id}/rc-quantity-reports"
    headers = {"X-Structural-Tenant": "a", "Authorization": f"Bearer {seams.TENANT}"}
    payload = {**source(job), "declared_prices": prices()}
    response = transport.handle(
        "POST", path, headers=headers, body=seams.canonical(payload)
    )
    assert response.status == 200
    assert json.loads(response.body)["revision"] == 1
    for bad in (
        {**payload, "model": {}},
        {**source(job)},
        {**payload, "declared_prices": prices(currency="usd")},
    ):
        assert (
            transport.handle(
                "POST", path, headers=headers, body=seams.canonical(bad)
            ).status
            == 400
        )
    assert (
        transport.handle(
            "POST", path, headers=headers, body=b" " * (16 * 1024 + 1)
        ).status
        == 413
    )
    assert transport.handle("GET", path, headers=headers, body=b"{}").status == 400
    for value in ("-1", "1.0", "True", "101"):
        assert (
            transport.handle(
                "GET", path, headers={**headers, "X-Structural-Report-Limit": value}
            ).status
            == 400
        )
    assert (
        len(json.loads(transport.handle("GET", path, headers=headers).body)["reports"])
        == 1
    )
