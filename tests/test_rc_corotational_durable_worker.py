"""Actual tiny source execution through durable leases; no physical qualification."""

from dataclasses import asdict, replace
from pathlib import Path
import json
import sqlite3

import pytest

from structural_analysis.execution.job_service import (
    DurableJobService,
    JobServiceError,
    validate_job_view,
)
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

TENANT = dict(
    tenant_id="tenant", authorization_token="corotational-tenant-token-0123456789"
)
WORKER = dict(
    worker_id="worker", authorization_token="corotational-worker-token-0123456789"
)
SECOND = dict(
    worker_id="second", authorization_token="corotational-second-token-0123456789"
)


def request():
    model = (
        Path(__file__).parents[1]
        / "examples/public_rc_fiber_frame_l_frame_material_history.json"
    )
    return json.loads(
        json.dumps(
            {
                "schema_version": "structural-analysis-job-request.v6",
                "operation": "bounded_rc_corotational_control",
                "case_id": "durable-corotational-test",
                "model": json.loads(model.read_bytes()),
                "source_revision": "b" * 40,
                "result_contract": "bounded-rc-corotational-job-result.v1",
                "config": {
                    "control_node_id": "N3",
                    "control_component": "UY",
                    "targets_m": [-1e-6, -2e-6, -1.5e-6],
                    "fixed_nodal_loads": [["N3", "FX", -0.01]],
                    "config": asdict(
                        StatefulCorotationalFiberFrame2DDisplacementControlConfig()
                    ),
                    "preload_config": asdict(NewtonRaphsonConfig()),
                    "maximum_attempt_count": 255,
                    "maximum_subdivision_depth": 8,
                    "experimental_pin_roller_beam": False,
                    "experimental_fixed_guided_axial": False,
                },
                "execution_config": {
                    "attempt_limit_per_call": 1,
                    "maximum_api_invocations": 100,
                },
            }
        )
    )


def service_at(path):
    return DurableJobService(
        path,
        tenant_tokens={"tenant": TENANT["authorization_token"]},
        worker_tokens={
            "worker": WORKER["authorization_token"],
            "second": SECOND["authorization_token"],
        },
        worker_tenants={"worker": {"tenant"}, "second": {"tenant"}},
    )


def test_actual_pause_reopen_other_worker_and_final_publication(tmp_path):
    service = service_at(tmp_path / "store")
    payload = request()
    payload["execution_config"].update(
        attempt_limit_per_call=2, maximum_api_invocations=6
    )
    job = service.submit_job(**TENANT, idempotency_key="two-chunks", request=payload)
    assert (
        service.submit_job(
            **TENANT, idempotency_key="two-chunks", request=payload
        ).job_id
        == job.job_id
    )
    first = service.claim_next(**WORKER, lease_seconds=300)
    assert first is not None
    assert service.claim_next(**SECOND, lease_seconds=300) is None
    saved = execute_job_claim(service, first, **WORKER)
    assert saved.status == "checkpointed"
    assert saved.progress_completed == 2
    assert saved.progress_total == 255  # maximum control attempts, not targets
    reopened = service_at(tmp_path / "store")
    second = reopened.claim_next(**SECOND, lease_seconds=300)
    assert second is not None
    with pytest.raises(JobServiceError):
        execute_job_claim(reopened, first, **WORKER)
    assert (
        reopened.read_rc_invocation_evidence(job.job_id, **TENANT)["execution_budget"][
            "reserved_attempts"
        ]
        == 2
    )
    completed = execute_job_claim(reopened, second, **SECOND)
    assert completed.status == "succeeded"
    assert completed.progress_completed == 3
    assert completed.progress_total == 255
    assert completed.to_dict()["schema_version"] == "structural-analysis-job-view.v2"
    assert completed.to_dict()["progress"]["unit"] == "control_solver_attempts"
    validate_job_view(completed)
    observed_view = service_at(tmp_path / "store").get_job(job.job_id, **TENANT)
    assert observed_view.progress_completed == 3
    assert observed_view.progress_unit == "control_solver_attempts"
    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
        event = connection.execute(
            "SELECT payload_json FROM job_events WHERE job_id=? AND event_type='completed'",
            (job.job_id,),
        ).fetchone()
        assert json.loads(event[0])["progress_completed"] == 3
    old_view = completed.to_dict()
    old_view["schema_version"] = "structural-analysis-job-view.v1"
    old_view["progress"].pop("unit")
    with pytest.raises(JobServiceError, match="job_view"):
        validate_job_view(old_view)
    result = json.loads(reopened.read_result(job.job_id, **TENANT))
    assert result["progress_completed"] == 3
    assert result["progress_unit"] == "control_solver_attempts"
    assert result["execution_budget"]["reserved_attempts"] == 4
    assert result["api_result"]["contract_pass"]
    assert len(result["receipts"]) == 2
    assert reopened.validate_integrity(job.job_id, **TENANT)["contract_pass"]

    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
        retained = connection.execute(
            "SELECT checkpoint_hash, checkpoint_size, checkpoint_media_type, "
            "resume_contract_hash FROM jobs WHERE job_id=?",
            (job.job_id,),
        ).fetchone()
        connection.execute(
            "UPDATE jobs SET checkpoint_hash=NULL, checkpoint_size=NULL, "
            "checkpoint_media_type=NULL, resume_contract_hash=NULL WHERE job_id=?",
            (job.job_id,),
        )
    with pytest.raises(JobServiceError, match="job_projection_integrity_failed"):
        reopened.validate_integrity(job.job_id, **TENANT)
    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE jobs SET checkpoint_hash=?, checkpoint_size=?, "
            "checkpoint_media_type=?, resume_contract_hash=? WHERE job_id=?",
            (*retained, job.job_id),
        )
    assert reopened.validate_integrity(job.job_id, **TENANT)["contract_pass"]
    with pytest.raises(JobServiceError, match="rc_quantity_job_unsupported"):
        reopened.create_rc_quantity_report(
            job.job_id,
            **TENANT,
            expected_request_hash=completed.request.content_hash,
            expected_result_artifact_hash=completed.result.content_hash,
            declared_prices=None,
        )
    # Hash-bound artifacts/events remain intact; only mutable SQLite counters change.
    for column, forged, original in (
        ("progress_completed", 4, 3),
        ("progress_total", 256, 255),
    ):
        with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
            connection.execute(
                f"UPDATE jobs SET {column}=? WHERE job_id=?", (forged, job.job_id)
            )
        with pytest.raises(JobServiceError, match="job_projection_integrity_failed"):
            reopened.validate_integrity(job.job_id, **TENANT)
        with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
            connection.execute(
                f"UPDATE jobs SET {column}=? WHERE job_id=?", (original, job.job_id)
            )
    assert reopened.validate_integrity(job.job_id, **TENANT)["contract_pass"]


def test_verification_budget_exhaustion_does_not_publish_success(tmp_path):
    service = service_at(tmp_path / "store")
    payload = request()
    payload["execution_config"]["maximum_api_invocations"] = 1
    job = service.submit_job(
        **TENANT, idempotency_key="insufficient-verification", request=payload
    )
    claim = service.claim_next(**WORKER, lease_seconds=300)
    with pytest.raises(JobServiceError, match="execution_attempt_budget_exhausted"):
        execute_job_claim(service, claim, **WORKER)
    observed = service.get_job(job.job_id, **TENANT)
    assert observed.status == "failed"
    assert observed.progress_completed == 0
    assert (
        service.read_rc_invocation_evidence(job.job_id, **TENANT)["execution_budget"][
            "reserved_attempts"
        ]
        == 1
    )
    assert observed.result is None
    assert service.validate_integrity(job.job_id, **TENANT)["contract_pass"]
    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE jobs SET progress_completed=1 WHERE job_id=?", (job.job_id,)
        )
    with pytest.raises(JobServiceError, match="job_projection_integrity_failed"):
        service.validate_integrity(job.job_id, **TENANT)


def test_corrupted_claim_checkpoint_rejected_before_new_reservation(tmp_path):
    service = service_at(tmp_path / "store")
    job = service.submit_job(**TENANT, idempotency_key="corruption", request=request())
    first = service.claim_next(**WORKER, lease_seconds=300)
    execute_job_claim(service, first, **WORKER)
    assert service.validate_integrity(job.job_id, **TENANT)["contract_pass"]

    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE jobs SET progress_completed=2 WHERE job_id=?", (job.job_id,)
        )
    with pytest.raises(JobServiceError, match="job_projection_integrity_failed"):
        service.validate_integrity(job.job_id, **TENANT)
    with sqlite3.connect(tmp_path / "store" / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE jobs SET progress_completed=1 WHERE job_id=?", (job.job_id,)
        )
    claim = service.claim_next(**SECOND, lease_seconds=300)
    assert claim is not None
    corrupted = replace(claim, checkpoint_bytes=claim.checkpoint_bytes + b" ")
    with pytest.raises(ValueError, match="checkpoint_binding_changed"):
        execute_job_claim(service, corrupted, **SECOND)
    assert (
        service.read_rc_invocation_evidence(job.job_id, **TENANT)["execution_budget"][
            "reserved_attempts"
        ]
        == 2
    )
    assert service.get_job(job.job_id, **TENANT).status == "failed"
    assert service.validate_integrity(job.job_id, **TENANT)["contract_pass"]


def test_integrity_uses_one_snapshot_when_heartbeat_commits_mid_read(
    tmp_path, monkeypatch
):
    path = tmp_path / "store"
    service = service_at(path)
    concurrent = service_at(path)
    job = service.submit_job(**TENANT, idempotency_key="snapshot", request=request())
    claim = service.claim_next(**WORKER, lease_seconds=300)
    before = service.get_job(job.job_id, **TENANT)
    original_read = service._job_row
    renewed = []

    def read_then_renew(connection, job_id):
        row = original_read(connection, job_id)
        renewed.append(
            concurrent.heartbeat(
                job_id, **WORKER, lease_token=claim.lease_token, lease_seconds=300
            )
        )
        return row

    with monkeypatch.context() as patch:
        patch.setattr(service, "_job_row", read_then_renew)
        report = service.validate_integrity(job.job_id, **TENANT)
    assert report["contract_pass"]
    assert report["event_count"] == before.revision + 1
    assert len(renewed) == 1
    assert renewed[0].revision == before.revision + 1
    assert service.validate_integrity(job.job_id, **TENANT)["contract_pass"]
