"""Extended planar backend through the durable transport, without promotion claims."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from structural_analysis.api.nonlinear_frame import (
    analyze_nonlinear_frame,
    nonlinear_frame_resume_contract_hash,
    validate_nonlinear_frame_manifest,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.execution import nonlinear_frame_worker as worker
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    sparse_factorization_policy_for_backend,
)
from tests.test_durable_job_service import (
    TENANT_A_TOKEN,
    TENANT_B_TOKEN,
    WORKER_TOKEN,
    _canonical_bytes,
    _claim,
    _model_ir_request,
    _request,
    _service,
)
from tests.test_frame3d_job_service import _request as _frame3d_request


def _headers(*, key="extended-portal", tenant="tenant-a", token=TENANT_A_TOKEN):
    return {
        "Authorization": f"Bearer {token}",
        "X-Structural-Tenant": tenant,
        "Idempotency-Key": key,
    }


def _extended_request():
    request = _request(load_steps=2)
    request["config"]["matrix_backend"] = VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    return request


def _submit_http(service, request, *, key="extended-portal"):
    return DurableJobHttpApi(service).handle(
        "POST", "/v1/jobs", headers=_headers(key=key), body=_canonical_bytes(request)
    )


@pytest.mark.parametrize(
    "backend",
    (
        VECTOR_MATRIX_BACKEND,
        VECTOR_SPARSE_MATRIX_BACKEND,
        VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    ),
)
@pytest.mark.parametrize("model_ir", (False, True), ids=("neutral", "model-ir"))
def test_http_request_retains_each_supported_planar_backend_without_solving(
    tmp_path, monkeypatch, backend, model_ir
):
    def forbidden(*args, **kwargs):
        pytest.fail("submission and configuration decoding must not execute a solver")

    monkeypatch.setattr(worker, "analyze_nonlinear_frame", forbidden)
    monkeypatch.setattr(worker, "analyze_nonlinear_frame_model_ir", forbidden)
    service = _service(tmp_path / "jobs")
    request = _model_ir_request() if model_ir else _request(load_steps=2)
    request["config"]["matrix_backend"] = backend
    response = _submit_http(service, request)
    assert response.status == 202, response.body
    claim = _claim(service)
    persisted = json.loads(claim.request_bytes)
    assert persisted == request
    assert worker._config(persisted["config"]).matrix_backend == backend
    assert claim.job.request.content_hash == canonical_hash(request)


@pytest.mark.parametrize(
    "mutation",
    (
        "unknown-backend",
        "experimental-3d-backend",
        "unbounded-load-steps",
        "unbounded-iterations",
        "invalid-profile",
        "v2-schema-on-v1",
        "frame3d-operation-on-v1",
        "frame3d-result-on-v1",
        "v1-schema-on-v2",
        "planar-operation-on-v2",
        "planar-result-on-v2",
        "planar-backend-in-v2-config",
        "planar-backend-in-v2-solver",
    ),
)
def test_http_rejects_backend_and_schema_promotion_before_claim(tmp_path, mutation):
    service = _service(tmp_path / "jobs")
    request = (
        _frame3d_request()
        if "v2" in mutation and "on-v1" not in mutation
        else _extended_request()
    )
    if mutation == "unknown-backend":
        request["config"]["matrix_backend"] = "scipy_sparse_unbounded"
    elif mutation == "experimental-3d-backend":
        request["config"]["matrix_backend"] = "scipy_sparse_splu_cpu_scalable"
    elif mutation == "unbounded-load-steps":
        request["config"]["load_steps"] = 65
    elif mutation == "unbounded-iterations":
        request["config"]["maximum_iterations"] = 201
    elif mutation == "invalid-profile":
        request["config"]["profile"] = "bounded_frame3d_direct_control.v1"
    elif mutation == "v2-schema-on-v1":
        request["schema_version"] = "structural-analysis-job-request.v2"
    elif mutation == "frame3d-operation-on-v1":
        request["operation"] = "bounded_frame3d_direct_control"
    elif mutation == "frame3d-result-on-v1":
        request["result_contract"] = "bounded-frame3d-job-result.v1"
    elif mutation == "v1-schema-on-v2":
        request["schema_version"] = "structural-analysis-job-request.v1"
    elif mutation == "planar-operation-on-v2":
        request["operation"] = "nonlinear_frame"
    elif mutation == "planar-result-on-v2":
        request["result_contract"] = "unified-nonlinear-frame-result.v1"
    elif mutation == "planar-backend-in-v2-config":
        request["config"]["matrix_backend"] = VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    else:
        request["config"]["solver_config"]["matrix_backend"] = (
            VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
        )
    response = _submit_http(service, request)
    assert response.status == 400, response.body
    assert json.loads(response.body)["status"] == "error"
    assert (
        service.claim_next(worker_id="worker-a", authorization_token=WORKER_TOKEN)
        is None
    )


def test_http_retains_existing_frame3d_typed_request(tmp_path):
    service = _service(tmp_path / "jobs")
    request = _frame3d_request()
    response = _submit_http(service, request)
    assert response.status == 202, response.body
    claim = _claim(service)
    assert json.loads(claim.request_bytes) == request
    assert claim.job.progress_total == len(request["config"]["control_targets"])


@pytest.fixture(scope="module")
def extended_job():
    """One prefix, resumed suffix and uninterrupted 2-step solve, shared by all checks."""
    directory = Path(tempfile.mkdtemp(prefix="structural-durable-extended-sparse-"))
    root = directory / "jobs"
    service = _service(root)
    request = _extended_request()
    submit = _submit_http(service, request)
    assert submit.status == 202, submit.body
    submitted = json.loads(submit.body)
    job_id = submitted["job_id"]
    first_claim = _claim(service)
    (directory / "request.json").write_bytes(first_claim.request_bytes)
    partial = execute_job_claim(
        service,
        first_claim,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        checkpoint_step_budget=1,
    )
    assert partial.status == "checkpointed" and partial.progress_completed == 1
    assert partial.checkpoint is not None
    service = _service(root)
    crash_claim = _claim(service)
    assert crash_claim.checkpoint_bytes is not None
    prefix_bytes = crash_claim.checkpoint_bytes
    (directory / "checkpoint.json").write_bytes(prefix_bytes)
    failed = service.fail_job(
        job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=crash_claim.lease_token,
        error_code="simulated_crash_before_suffix",
        retriable=False,
    )
    assert failed.status == "failed" and failed.can_resume
    http = DurableJobHttpApi(service)
    resume_body = {
        "expected_request_hash": submitted["request"]["content_hash"],
        "expected_checkpoint_hash": partial.checkpoint.content_hash,
    }
    stale = http.handle(
        "POST",
        f"/v1/jobs/{job_id}/resume",
        headers=_headers(),
        body=_canonical_bytes(
            {**resume_body, "expected_checkpoint_hash": "sha256:" + "0" * 64}
        ),
    )
    assert stale.status == 409
    assert (
        json.loads(stale.body)["error"]["code"] == "resume_optimistic_binding_mismatch"
    )
    resumed = http.handle(
        "POST",
        f"/v1/jobs/{job_id}/resume",
        headers=_headers(),
        body=_canonical_bytes(resume_body),
    )
    assert resumed.status == 200, resumed.body
    service = _service(root)
    claim = _claim(service)
    assert claim.checkpoint_bytes == prefix_bytes
    assert claim.job.resume_contract_hash == partial.resume_contract_hash
    captured = []
    original = worker.analyze_nonlinear_frame

    def retain_actual_result(*args, **kwargs):
        result = original(*args, **kwargs)
        captured.append(result)
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(worker, "analyze_nonlinear_frame", retain_actual_result)
        final = execute_job_claim(
            service, claim, worker_id="worker-a", authorization_token=WORKER_TOKEN
        )
    assert len(captured) == 1
    assert final.status == "succeeded" and final.progress_completed == 2
    assert final.progress_total == 2 and not final.can_resume
    http = DurableJobHttpApi(service)
    for name, suffix in (("job", ""), ("result", "/result"), ("evidence", "/evidence")):
        response = http.handle("GET", f"/v1/jobs/{job_id}{suffix}", headers=_headers())
        assert response.status == 200, response.body
        (directory / f"{name}.json").write_bytes(response.body)
    result = json.loads((directory / "result.json").read_bytes())
    validate_nonlinear_frame_manifest(result)
    terminal_bytes = captured[0].checkpoint_artifact()
    (directory / "terminal-checkpoint.json").write_bytes(terminal_bytes)
    config = worker._config(request["config"])
    direct = analyze_nonlinear_frame(
        load_neutral_json_bytes(_canonical_bytes(request["model"])), config
    )
    assert direct.contract_pass
    direct_bytes = direct.checkpoint_artifact()
    (directory / "direct-checkpoint.json").write_bytes(direct_bytes)
    (directory / "direct-result.json").write_bytes(_canonical_bytes(direct.to_dict()))
    assert (
        service.validate_integrity(
            job_id, tenant_id="tenant-a", authorization_token=TENANT_A_TOKEN
        )["contract_pass"]
        is True
    )
    print(f"extended durable job artifacts: {directory}", flush=True)
    return {
        "directory": directory,
        "request": request,
        "job": final,
        "result": result,
        "evidence": json.loads((directory / "evidence.json").read_bytes()),
        "prefix_bytes": prefix_bytes,
        "terminal_bytes": terminal_bytes,
        "direct_bytes": direct_bytes,
        "direct": direct.to_dict(),
        "service": service,
    }


def test_actual_extended_http_worker_resume_preserves_strict_backend_and_evidence(
    extended_job,
):
    result, evidence, job = (extended_job[key] for key in ("result", "evidence", "job"))
    assert (
        result["configuration"]["matrix_backend"]
        == VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    )
    assert result["configuration"]["stiffness_storage"] == "scipy_sparse_csr"
    metrics = result["metrics"]
    policy = sparse_factorization_policy_for_backend(
        VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    )
    assert policy.maximum_exact_condition_equations == 1536
    assert policy.maximum_condition_number_1 == 1e12
    assert policy.minimum_normalized_absolute_pivot == 1e-14
    assert policy.maximum_backward_error == 1e-12
    assert metrics["sparse_factorization_policy_hash"] == policy.policy_hash
    assert metrics["sparse_backend_used"] is True
    assert metrics["native_sparse_assembly_used"] is True
    assert (
        metrics["sparse_factorization_count"] == len(result["convergence_history"]) > 0
    )
    assert (
        metrics["replayed_prefix_step_count"] == metrics["newly_solved_step_count"] == 1
    )
    assert evidence["request_hash"] == canonical_hash(extended_job["request"])
    assert evidence["checkpoint_hash"] == job.checkpoint.content_hash
    assert evidence["result_artifact_hash"] == job.result.content_hash
    assert evidence["validation_report"]["external_level2_attached"] is False
    assert evidence["validation_report"]["exact_engineering_recovery"] is True
    assert evidence["validation_report"]["exact_checkpoint_chain_replay"] is True
    assert evidence["validation_report"]["result_hash"] == result["result_hash"]


def test_actual_extended_resume_matches_uninterrupted_checkpoint_bytes_and_engineering_rows(
    extended_job,
):
    assert extended_job["terminal_bytes"] == extended_job["direct_bytes"]
    for key in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
        "convergence_history",
        "engineering_result_ir",
        "checkpoint",
    ):
        assert extended_job["result"][key] == extended_job["direct"][key], key
    assert extended_job["result"]["configuration"][
        "restart_checkpoint_artifact_hash"
    ] == ("sha256:" + hashlib.sha256(extended_job["prefix_bytes"]).hexdigest())


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("configuration", "matrix_backend", VECTOR_SPARSE_MATRIX_BACKEND),
        ("configuration", "matrix_backend", VECTOR_MATRIX_BACKEND),
        ("configuration", "matrix_backend", "scipy_sparse_splu_cpu_scalable"),
        (
            "metrics",
            "sparse_factorization_policy_hash",
            sparse_factorization_policy_for_backend(
                VECTOR_SPARSE_MATRIX_BACKEND
            ).policy_hash,
        ),
        ("metrics", "sparse_factorization_diagnostics_passed", False),
        ("metrics", "native_sparse_assembly_used", False),
    ),
)
def test_actual_extended_manifest_rejects_rehashed_backend_promotion(
    extended_job, section, field, value
):
    payload = deepcopy(extended_job["result"])
    payload[section][field] = value
    if value == VECTOR_MATRIX_BACKEND:
        payload["configuration"]["stiffness_storage"] = "numpy_dense_ndarray"
    payload["result_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "result_hash"}
    )
    with pytest.raises(
        ValueError, match="backend declaration differs from execution policy"
    ):
        validate_nonlinear_frame_manifest(payload)


def test_actual_extended_checkpoint_rejects_legacy_backend_resume_before_analysis(
    extended_job, tmp_path, monkeypatch
):
    service = _service(tmp_path / "foreign-backend")
    response = _submit_http(service, extended_job["request"])
    assert response.status == 202
    claim = _claim(service)
    config = worker._config(extended_job["request"]["config"])
    model = load_neutral_json_bytes(_canonical_bytes(extended_job["request"]["model"]))
    legacy_hash = nonlinear_frame_resume_contract_hash(
        model, replace(config, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND)
    )
    assert legacy_hash != nonlinear_frame_resume_contract_hash(model, config)
    service.save_checkpoint(
        claim.job.job_id,
        worker_id="worker-a",
        authorization_token=WORKER_TOKEN,
        lease_token=claim.lease_token,
        checkpoint_bytes=extended_job["prefix_bytes"],
        checkpoint_media_type=worker.CHECKPOINT_MEDIA_TYPE,
        progress_completed=1,
        progress_total=2,
        resume_contract_hash=legacy_hash,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("foreign backend resume must be rejected before analysis")

    monkeypatch.setattr(worker, "analyze_nonlinear_frame", forbidden)
    monkeypatch.setattr(worker, "advance_nonlinear_frame_checkpoint", forbidden)
    with pytest.raises(
        worker.NonlinearFrameWorkerError, match="worker_resume_contract_mismatch"
    ):
        execute_job_claim(
            service,
            _claim(service),
            worker_id="worker-a",
            authorization_token=WORKER_TOKEN,
        )


def test_actual_extended_http_artifacts_remain_tenant_scoped(extended_job):
    http = DurableJobHttpApi(extended_job["service"])
    job_id = extended_job["job"].job_id
    for suffix in ("", "/result", "/evidence"):
        response = http.handle(
            "GET",
            f"/v1/jobs/{job_id}{suffix}",
            headers=_headers(tenant="tenant-b", token=TENANT_B_TOKEN),
        )
        assert response.status == 404
