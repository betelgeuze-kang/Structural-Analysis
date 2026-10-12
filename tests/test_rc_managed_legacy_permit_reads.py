"""Legacy managed reads retain custody without creating execution permits.

Only the synthetic result-validator seam is stubbed. Stored artifact hashes,
service event chains, external reservation journals and worker admission are
real. No numerical API, numerical validation or source fingerprint is allowed.
"""

from contextlib import closing
from dataclasses import dataclass
import hashlib
import sqlite3
import shutil
import sys

import pytest

from structural_analysis.execution import rc_corotational_control_worker as coro_worker
from structural_analysis.execution import rc_fiber_direct_control_worker as fiber_worker
from structural_analysis.execution.job_execution_authority import (
    ExecutionAuthorityError,
    JobExecutionAuthority,
)
from structural_analysis.execution.job_execution_permit import ExecutionPermitError
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from tests import test_rc_fiber_job_service as seams
from tests.test_rc_corotational_job_contract import request as coro_request


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux managed pins")


@pytest.fixture(autouse=True)
def no_numerical_execution(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("legacy permit read regression invoked numerical execution")

    for module, names in (
        (
            "structural_analysis.api.rc_fiber_frame_direct_control",
            (
                "analyze_bounded_rc_fiber_direct_control",
                "validate_bounded_rc_fiber_direct_control_artifacts",
                "run_stateful_fiber_frame2d_control_path",
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
        (
            "structural_analysis.solvers.nonlinear.newton",
            ("newton_raphson_vector",),
        ),
        (
            "structural_analysis.assembly.stateful_fiber_frame2d_control_path",
            ("_execute_raw",),
        ),
    ):
        for name in names:
            monkeypatch.setattr(f"{module}.{name}", forbidden)


def _service(root, clock, **options):
    return DurableJobService(
        root,
        tenant_tokens={"a": seams.TENANT},
        worker_tokens={"worker-a": seams.WORKER},
        worker_tenants={"worker-a": {"a"}},
        clock=clock,
        **options,
    )


def _rows(path, tables):
    with closing(sqlite3.connect(path)) as db:
        return {
            table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in tables
        }


def _state(current, authority):
    return {
        "jobs": _rows(
            current.root / "jobs.sqlite3",
            (
                "jobs",
                "job_events",
                "job_execution_budgets",
                "job_rc_invocation_outcomes",
                "job_rc_quantity_reports",
            ),
        ),
        "authority": _rows(
            authority.directory / "authority.sqlite3",
            ("authority", "budgets", "reservations"),
        ),
        "blobs": {
            str(path.relative_to(current.root)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in (current.root / "blobs" / "sha256").rglob("*")
            if path.is_file()
        },
    }


def _assert_no_permit_migration(current, authority):
    assert not authority.permit_directory.exists()
    assert not (current.root / ".job-execution-permits").exists()
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('job_execution_permit_namespaces','job_execution_permit_jobs')"
        ).fetchall() == []


@dataclass
class LegacyStore:
    current: DurableJobService
    authority: JobExecutionAuthority
    binding: object
    clock: object
    completed: object
    fiber_claim: object
    coro_claim: object
    queued: object
    result_bytes: bytes
    evidence_bytes: bytes
    original_state: dict
    completed_budget: dict
    completed_reservations: dict

    def reopen(self):
        return _service(self.current.root, self.clock)


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    clock = seams.Clock()
    current = _service(
        root, clock, execution_authority=authority, execution_binding=binding
    )
    payload = seams.request()
    payload["config"]["targets_m"] = [-0.0001]
    seams.submit(current, payload, key="synthetic-completed")
    completed_claim = seams.claim(current)
    _, _, result_bytes, _, proof = seams.synthetic_admission_artifacts(
        current, completed_claim, monkeypatch, marker="legacy-permit-custody-only"
    )
    completed = current.complete_job(
        completed_claim.job.job_id,
        **seams.lease(completed_claim),
        result_bytes=result_bytes,
        result_media_type="application/json",
        evidence=proof,
    )
    assert completed.status == "succeeded"
    evidence_bytes = current.read_evidence(completed.job_id, **seams.tenant())
    seams.submit(current, key="live-fiber-claim")
    fiber_claim = seams.claim(current)
    seams.submit(current, coro_request(), key="live-corotational-claim")
    coro_claim = seams.claim(current)
    queued = seams.submit(current, key="queued-claim-admission")
    completed_budget = authority.read_budget(
        binding, completed.job_id, completed.request.content_hash
    )
    completed_reservations = authority.read_reservations(
        binding, completed.job_id, completed.request.content_hash
    )
    original_state = _state(current, authority)

    # Only this fixture's temporary runtime namespace is removed. Core binding,
    # budgets, reservation records, jobs, event bytes and blobs stay untouched.
    assert authority.permit_directory.parent == tmp_path / "authority"
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        db.execute("DROP TABLE job_execution_permit_jobs")
        db.execute("DROP TABLE job_execution_permit_namespaces")
        db.commit()
    shutil.rmtree(authority.permit_directory)
    assert _state(current, authority) == original_state
    _assert_no_permit_migration(current, authority)
    return LegacyStore(
        current,
        authority,
        binding,
        clock,
        completed,
        fiber_claim,
        coro_claim,
        queued,
        result_bytes,
        evidence_bytes,
        original_state,
        completed_budget,
        completed_reservations,
    )


def test_legacy_completed_reads_preserve_artifacts_spend_and_namespace(legacy):
    current = legacy.reopen()
    completed = legacy.completed
    assert current.get_job(completed.job_id, **seams.tenant()) == completed
    assert current.read_result(completed.job_id, **seams.tenant()) == legacy.result_bytes
    assert (
        current.read_evidence(completed.job_id, **seams.tenant())
        == legacy.evidence_bytes
    )
    assert current.validate_integrity(completed.job_id, **seams.tenant())["contract_pass"]
    evidence = current.read_rc_invocation_evidence(completed.job_id, **seams.tenant())
    assert evidence["execution_budget"]["reserved_attempts"] == 2
    assert len(evidence["invocations"]) == 2
    assert evidence["pending_ordinals"] == []
    assert legacy.authority.read_budget(
        legacy.binding, completed.job_id, completed.request.content_hash
    ) == legacy.completed_budget
    assert legacy.authority.read_reservations(
        legacy.binding, completed.job_id, completed.request.content_hash
    ) == legacy.completed_reservations
    assert _state(current, legacy.authority) == legacy.original_state
    _assert_no_permit_migration(current, legacy.authority)


@pytest.mark.parametrize(
    "operation",
    (
        "register_existing",
        "register_new",
        "reserve_authority",
        "reserve_service",
        "claim_next",
        "fiber_worker",
        "corotational_worker",
    ),
)
def test_legacy_execution_is_blocked_without_spend_or_lease_changes(legacy, operation):
    current = legacy.reopen()
    claim = legacy.fiber_claim
    authority, binding = legacy.authority, legacy.binding
    with pytest.raises((ExecutionPermitError, JobServiceError)) as error:
        if operation == "register_existing":
            authority.register_job(
                binding, claim.job.job_id, claim.job.request.content_hash, 6
            )
        elif operation == "register_new":
            authority.register_job(binding, "job_" + "e" * 32, "sha256:" + "e" * 64, 6)
        elif operation == "reserve_authority":
            authority.reserve(binding, claim.job.job_id, claim.job.request.content_hash)
        elif operation == "reserve_service":
            current.reserve_execution_attempt(claim.job.job_id, **seams.lease(claim))
        elif operation == "claim_next":
            current.claim_next(
                worker_id="worker-a", authorization_token=seams.WORKER, lease_seconds=5
            )
        else:
            execute = fiber_worker.execute_rc_fiber_direct_control_claim
            if operation == "corotational_worker":
                claim = legacy.coro_claim
                execute = coro_worker.execute_rc_corotational_control_claim
            execute(
                current,
                claim,
                worker_id="worker-a",
                authorization_token=seams.WORKER,
                lease_seconds=5,
            )
    assert error.value.code == "job_execution_permit_migration_required"
    assert _state(current, authority) == legacy.original_state
    assert current.get_job(legacy.queued.job_id, **seams.tenant()).status == "queued"
    _assert_no_permit_migration(current, authority)


def test_legacy_read_still_rejects_stale_generation(legacy):
    with closing(sqlite3.connect(legacy.authority.directory / "authority.sqlite3")) as db:
        db.execute("UPDATE authority SET generation=generation+1")
        db.commit()
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        legacy.reopen()
    with pytest.raises(ExecutionAuthorityError, match="stale or invalid"):
        legacy.authority.read_budget(
            legacy.binding,
            legacy.completed.job_id,
            legacy.completed.request.content_hash,
        )
    _assert_no_permit_migration(legacy.current, legacy.authority)


@pytest.mark.parametrize("corruption", ("spent_count", "reservation_ordinal"))
def test_legacy_verified_reads_still_reject_corrupt_authority_journal(legacy, corruption):
    with closing(sqlite3.connect(legacy.authority.directory / "authority.sqlite3")) as db:
        if corruption == "spent_count":
            db.execute(
                "UPDATE budgets SET spent=spent+1 WHERE job_id=?",
                (legacy.completed.job_id,),
            )
        else:
            db.execute(
                "UPDATE reservations SET ordinal=99 WHERE job_id=? AND ordinal=1",
                (legacy.completed.job_id,),
            )
        db.commit()
    current = legacy.reopen()
    with pytest.raises(ExecutionAuthorityError, match="journal invalid"):
        legacy.authority.read_budget(
            legacy.binding,
            legacy.completed.job_id,
            legacy.completed.request.content_hash,
        )
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.validate_integrity(legacy.completed.job_id, **seams.tenant())
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.read_rc_invocation_evidence(legacy.completed.job_id, **seams.tenant())
    _assert_no_permit_migration(current, legacy.authority)
