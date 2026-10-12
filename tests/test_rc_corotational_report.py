"""Synthetic service-owned report custody; no numerical or source execution.

Zero-state transport fixtures are intentionally not physical result evidence.
Only saved contracts, history projection, authorization and spend are tested.
"""

from copy import deepcopy
import json
import sqlite3

import pytest

from structural_analysis.execution import job_service as implementation
from structural_analysis.execution import rc_corotational_job_contract as contract
from structural_analysis.execution import rc_corotational_report as reports
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import (
    JobServiceError,
    build_job_completion_evidence,
)
from . import test_rc_corotational_job_contract as pure
from . import test_rc_fiber_job_service as seams
from .test_rc_corotational_job_contract import (
    no_numerical_execution_or_source_identity as no_numerical_execution_or_source_identity,
)
from .test_rc_fiber_job_service import no_solver as no_solver


def expected(job):
    return {
        "expected_request_hash": job.request.content_hash,
        "expected_result_artifact_hash": job.result.content_hash,
        "expected_evidence_artifact_hash": job.evidence.content_hash,
    }


def read(service, job, **kwargs):
    return service.read_rc_corotational_report(
        job.job_id, **seams.tenant(), **(expected(job) | kwargs)
    )


def headers(job):
    return {
        "X-Structural-Tenant": "a",
        "Authorization": f"Bearer {seams.TENANT}",
        "X-Structural-Expected-Request-Hash": job.request.content_hash,
        "X-Structural-Expected-Result-Hash": job.result.content_hash,
        "X-Structural-Expected-Evidence-Hash": job.evidence.content_hash,
    }


def numerical_state(service, job):
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        return {
            table: connection.execute(
                f"SELECT * FROM {table} WHERE job_id=? ORDER BY 1, 2", (job.job_id,)
            ).fetchall()
            for table in (
                "jobs",
                "job_events",
                "job_execution_budgets",
                "job_rc_invocation_outcomes",
                "job_rc_quantity_reports",
            )
        }


@pytest.fixture(params=["v6", "v7"])
def completed(tmp_path, monkeypatch, request):
    return make_completed(tmp_path, monkeypatch, request.param)


def make_completed(tmp_path, monkeypatch, version, *, record_unknown=False):
    payload = pure.request() if version == "v6" else pure.isolated_request()
    payload["config"]["maximum_attempt_count"] = 255
    payload["config"]["fixed_nodal_loads"] = [["N3", "FX", -0.01]]
    # The synthetic fixture constructs native ancestry for the exact fixed-load
    # problem; it does not establish fixed-load equilibrium or material truth.
    compiler = pure.compile_rc_corotational_control_model
    monkeypatch.setattr(
        pure,
        "compile_rc_corotational_control_model",
        lambda model: compiler(model, fixed_nodal_loads=(("N3", "FX", -0.01),)),
    )
    pair = pure.pair if version == "v6" else pure.isolated_pair
    clock = seams.Clock()
    service = seams.service(tmp_path / "store", clock)
    job = seams.submit(service, payload)
    first = seams.claim(service)
    a1, v1, raw1 = pair(payload)
    for value in (a1, v1):
        ordinal = seams.reserve(service, first)
        seams.record(service, first, ordinal, value)
    receipt1 = pure.receipt(payload, a1, v1)
    checkpoint = contract.build_rc_corotational_job_payload(
        payload, [receipt1], pure.budget(), raw1
    )
    typed = pure.validate_rc_corotational_job_request(payload)
    service.save_checkpoint(
        job.job_id,
        **seams.lease(first),
        checkpoint_bytes=seams.canonical(checkpoint),
        checkpoint_media_type="application/json",
        progress_completed=1,
        progress_total=255,
        resume_contract_hash=typed.resume_contract_hash,
    )
    abandoned = seams.claim(service)
    assert seams.reserve(service, abandoned) == 3
    if record_unknown:
        interrupted, _, _ = pair(payload, before=1, restart=raw1)
        interrupted = pure.isolated_raised(deepcopy(interrupted), unaccounted=True)
        seams.record(service, abandoned, 3, interrupted)
    clock.advance()
    second = seams.claim(service)
    a2, v2, raw2 = pair(payload, before=1, after=3, ready=True, restart=raw1)
    for row in a2["api_result"]["responses"]:
        row["nodes"][2]["external_loads_kn_knm"][0] = -0.01
    # Preserve an intermediate signed global response for export contract tests.
    # It is a synthetic observation, not a numerical or physical assertion.
    a2["api_result"]["responses"][1]["load_factor"] = -0.25
    a2["api_result"]["responses"][1]["nodes"][2]["external_loads_kn_knm"][1] = -2.0
    a2["api_result"]["responses"][1]["nodes"][2]["reactions_kn_knm"][1] = -0.0
    for value in (a2, v2):
        ordinal = seams.reserve(service, second)
        seams.record(service, second, ordinal, value)
    receipt2 = pure.receipt(payload, a2, v2, (4, 5))
    result = contract.build_rc_corotational_job_payload(
        payload, [receipt1, receipt2], pure.budget(5), raw2, a2["api_result"], True
    )
    validation = contract.validate_rc_corotational_job_result(
        result, typed, pure.budget(5), checkpoint=checkpoint
    )
    raw = seams.canonical(result)
    proof = build_job_completion_evidence(
        job_id=job.job_id,
        request_hash=job.request.content_hash,
        checkpoint_hash=seams.sha(seams.canonical(checkpoint)),
        result_bytes=raw,
        validator_id=contract.RC_COROTATIONAL_JOB_VALIDATOR_ID,
        validation_report=validation,
    )
    final = service.complete_job(
        job.job_id,
        **seams.lease(second),
        result_bytes=raw,
        result_media_type="application/vnd.structural-analysis.rc-corotational-job-result+json",
        evidence=proof,
    )
    return service, final


def test_reopen_download_exact_bytes_and_read_only_spend(completed):
    service, job = completed
    before = numerical_state(service, job)
    raw = read(service, job)
    report = json.loads(raw)
    assert raw == read(seams.service(service.root), job)
    assert report["schema_version"] == reports.RC_COROTATIONAL_REPORT_SCHEMA_VERSION
    assert report["report_hash"] == seams.sha(
        seams.canonical(
            {key: value for key, value in report.items() if key != "report_hash"}
        )
    )
    assert (
        report["bindings"]["original_artifacts"]["evidence"]["content_hash"]
        == job.evidence.content_hash
    )
    assert report["bindings"]["recorded_source_identity"] == "a" * 64
    assert report["bindings"]["source_revision_is_execution_attestation"] is False
    assert report["structural_authority"] == contract.RC_COROTATIONAL_JOB_AUTHORITY
    assert report["progress"] == {
        "control_solver_attempts": {"completed": 3, "maximum": 255},
        "authored_targets": {"completed": 2, "total": 2},
        "accepted_response_states": 3,
    }
    assert report["execution"]["pending_ordinals"] == [3]
    assert report["execution"]["unknown_execution_work"] is True
    assert [row["ordinal"] for row in report["execution"]["invocations"]] == [
        1,
        2,
        4,
        5,
    ]
    assert report["execution"]["known_work"] == {
        "preload_solver_calls": 4,
        "restart_replay_solver_calls": 2,
        "control_solver_calls": 6,
    }
    assert report["execution"]["budget"] == pure.budget(5)
    assert report["derivation"] == {
        "version": "rc_corotational_nodal_report.v1",
        "fresh_analysis_invocations": 0,
        "fresh_verification_invocations": 0,
        "source_fingerprint_invocations": 0,
        "new_structural_authority": False,
    }
    response = DurableJobHttpApi(service).handle(
        "GET", f"/v1/jobs/{job.job_id}/rc-corotational-report", headers=headers(job)
    )
    assert response.status == 200 and response.body == raw
    assert response.headers["x-structural-report-sha256"] == seams.sha(raw)
    assert response.headers["x-structural-report-id"] == "rcc_" + seams.sha(raw)[7:]
    assert "attachment" in response.headers["content-disposition"]
    assert numerical_state(service, job) == before


def test_nodal_units_signed_loads_and_accepted_history_without_member_tables(completed):
    service, job = completed
    raw = read(service, job)
    report = json.loads(raw)
    assert report["units"]["displacement_units"] == ["m", "m", "rad"]
    assert report["units"]["load_units"] == ["kN", "kN", "kN*m"]
    assert report["units"]["load_factor"] == "1"
    assert report["units"]["reaction_definition"].endswith("free_dofs_zero")
    assert report["declarations"]["fixed_nodal_loads"] == [["N3", "FX", -0.01]]
    assert [row["phase"] for row in report["responses"]] == [
        "preload",
        "control",
        "control",
    ]
    assert report["responses"][1]["load_factor"] == -0.25
    assert report["responses"][1]["nodes"][2]["external_loads_kn_knm"][:2] == [
        -0.01,
        -2.0,
    ]
    assert b'"reactions_kn_knm":[0.0,-0.0,0.0]' in raw
    assert all(
        "members" not in row and "fiber_results" not in row
        for row in report["responses"]
    )


@pytest.mark.parametrize(
    "key",
    [
        "expected_request_hash",
        "expected_result_artifact_hash",
        "expected_evidence_artifact_hash",
    ],
)
def test_missing_and_conflicting_expected_originals(completed, key):
    service, job = completed
    with pytest.raises(JobServiceError, match="rc_corotational_report_source_required"):
        read(service, job, **{key: None})
    with pytest.raises(JobServiceError, match="rc_corotational_report_source_conflict"):
        read(service, job, **{key: "sha256:" + "f" * 64})
    values = headers(job)
    header = {
        "expected_request_hash": "X-Structural-Expected-Request-Hash",
        "expected_result_artifact_hash": "X-Structural-Expected-Result-Hash",
        "expected_evidence_artifact_hash": "X-Structural-Expected-Evidence-Hash",
    }[key]
    values.pop(header)
    api = DurableJobHttpApi(service)
    route = f"/v1/jobs/{job.job_id}/rc-corotational-report"
    assert api.handle("GET", route, headers=values).status == 400
    values[header] = "sha256:" + "f" * 64
    assert api.handle("GET", route, headers=values).status == 409


def test_tenant_authorization_and_methods(completed):
    service, job = completed
    for credentials in (
        {"tenant_id": "b", "authorization_token": seams.OTHER},
        {"tenant_id": "a", "authorization_token": "invalid"},
    ):
        with pytest.raises(JobServiceError, match="job_not_found|tenant_unauthorized"):
            service.read_rc_corotational_report(
                job.job_id, **credentials, **expected(job)
            )
    route = f"/v1/jobs/{job.job_id}/rc-corotational-report"
    api = DurableJobHttpApi(service)
    values = headers(job) | {"Authorization": "Bearer invalid"}
    assert api.handle("GET", route, headers=values).status == 401
    assert api.handle("POST", route, headers=headers(job)).status == 405
    assert api.handle("GET", route, headers=headers(job), body=b"{}").status == 400


def test_queued_and_legacy_jobs_do_not_gain_a_corotational_report(tmp_path):
    service = seams.service(tmp_path / "store")
    queued = seams.submit(service, pure.request())
    sources = {
        "expected_request_hash": queued.request.content_hash,
        "expected_result_artifact_hash": seams.RESUME,
        "expected_evidence_artifact_hash": seams.RESUME,
    }
    with pytest.raises(
        JobServiceError, match="rc_corotational_report_job_not_succeeded"
    ):
        service.read_rc_corotational_report(queued.job_id, **seams.tenant(), **sources)
    legacy = seams.submit(service, seams.request(), key="legacy")
    sources["expected_request_hash"] = legacy.request.content_hash
    with pytest.raises(JobServiceError, match="rc_corotational_report_job_unsupported"):
        service.read_rc_corotational_report(legacy.job_id, **seams.tenant(), **sources)


@pytest.mark.parametrize(
    "column,value",
    [("progress_completed", 4), ("progress_total", 256), ("checkpoint_hash", None)],
)
def test_counter_or_retained_checkpoint_tampering_is_rejected(completed, column, value):
    service, job = completed
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.execute(
            f"UPDATE jobs SET {column}=? WHERE job_id=?", (value, job.job_id)
        )
    with pytest.raises(JobServiceError, match="job_projection_integrity_failed"):
        read(service, job)


def test_budget_and_event_tampering_is_rejected(completed):
    service, job = completed
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE job_execution_budgets SET reserved_attempts=4 WHERE job_id=?",
            (job.job_id,),
        )
    with pytest.raises(JobServiceError, match="execution_budget_integrity_failed"):
        read(service, job)
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE job_execution_budgets SET reserved_attempts=5 WHERE job_id=?",
            (job.job_id,),
        )
        connection.execute(
            "UPDATE job_events SET occurred_at='changed' WHERE job_id=? AND revision=0",
            (job.job_id,),
        )
    with pytest.raises(JobServiceError, match="event_chain_integrity_failed"):
        read(service, job)


def test_coherent_evidence_rehash_does_not_change_validator_authority(completed):
    service, job = completed
    evidence = json.loads(service.read_evidence(job.job_id, **seams.tenant()))
    evidence["validator_id"] = "synthetic.untrusted.validator"
    raw = seams.canonical(evidence)
    digest = seams.sha(raw)
    path = service._blob_path(digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    with sqlite3.connect(service.root / "jobs.sqlite3") as connection:
        connection.row_factory = sqlite3.Row
        event = connection.execute(
            "SELECT * FROM job_events WHERE job_id=? AND event_type='completed'",
            (job.job_id,),
        ).fetchone()
        payload = json.loads(event["payload_json"])
        payload["evidence_hash"] = digest
        event_hash, payload_json = implementation._event_hash(
            job_id=job.job_id,
            revision=event["revision"],
            event_type=event["event_type"],
            status=event["status"],
            occurred_at=event["occurred_at"],
            payload=payload,
            previous_event_hash=event["previous_event_hash"],
        )
        connection.execute(
            "UPDATE job_events SET payload_json=?,event_hash=? WHERE job_id=? AND revision=?",
            (payload_json, event_hash, job.job_id, event["revision"]),
        )
        connection.execute(
            "UPDATE jobs SET evidence_hash=?,evidence_size=?,terminal_event_hash=? WHERE job_id=?",
            (digest, len(raw), event_hash, job.job_id),
        )
    altered = service.get_job(job.job_id, **seams.tenant())
    assert service.validate_integrity(job.job_id, **seams.tenant())["contract_pass"]
    with pytest.raises(
        JobServiceError, match="rc_corotational_report_original_invalid"
    ):
        read(service, altered)


def test_legacy_quantity_report_remains_unsupported(completed):
    service, job = completed
    with pytest.raises(JobServiceError, match="rc_quantity_job_unsupported"):
        service.create_rc_quantity_report(
            job.job_id,
            **seams.tenant(),
            expected_request_hash=job.request.content_hash,
            expected_result_artifact_hash=job.result.content_hash,
            declared_prices=None,
        )


def test_recorded_failed_invocation_retains_unknown_work_and_unavailable_cpu(
    tmp_path, monkeypatch
):
    service, job = make_completed(tmp_path, monkeypatch, "v7", record_unknown=True)
    report = json.loads(read(service, job))
    execution = report["execution"]
    assert execution["recorded_invocation_count"] == 5
    assert execution["pending_ordinals"] == []
    assert execution["unknown_execution_work"] is True
    failed = execution["invocations"][2]
    assert failed["ordinal"] == 3 and failed["status"] == "raised"
    assert failed["timing"]["process_cpu_ns"] is None
    assert failed["work"] is None and failed["unavailable_execution_work"] is True
    assert failed["phase_supervision"]["status"] == "unaccounted"


def test_report_reads_one_snapshot_even_when_counters_change_mid_read(
    completed, monkeypatch
):
    service, job = completed
    prior = read(service, job)
    original = service._job_row
    changed = []

    def read_then_change(connection, job_id):
        row = original(connection, job_id)
        with sqlite3.connect(service.root / "jobs.sqlite3") as writer:
            writer.execute(
                "UPDATE jobs SET progress_completed=4 WHERE job_id=?", (job_id,)
            )
        changed.append(True)
        return row

    with monkeypatch.context() as patch:
        patch.setattr(service, "_job_row", read_then_change)
        assert read(service, job) == prior
    assert changed == [True]
    with pytest.raises(JobServiceError, match="job_projection_integrity_failed"):
        read(service, job)


def test_report_byte_bound_rejects_export_without_mutating_job(completed, monkeypatch):
    service, job = completed
    before = numerical_state(service, job)
    monkeypatch.setattr(reports, "RC_COROTATIONAL_REPORT_MAX_BYTES", 1)
    with pytest.raises(JobServiceError, match="rc_corotational_report_too_large"):
        read(service, job)
    assert numerical_state(service, job) == before
