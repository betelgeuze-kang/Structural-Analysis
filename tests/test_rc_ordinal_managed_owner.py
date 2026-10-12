"""Trusted owner credits, actual suffix children and immutable saved custody.

Tiny authored software models only; these tests do not qualify a specimen.
"""

from copy import deepcopy
from dataclasses import replace
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import gc

import pytest

from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution import rc_corotational_ordinal_worker as worker
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    validate_rc_corotational_ordinal_job_request,
)
from tests.test_rc_corotational_ordinal_job_request import ordinal_request

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux shared owner and isolated children"
)
TENANT = dict(tenant_id="tenant", authorization_token="ordinal-tenant-secret")
WORKER = dict(worker_id="worker", authorization_token="ordinal-worker-secret")


def byte_snapshot(root):
    # SQLite SHM contains volatile read marks. Database, WAL, blobs and binding
    # bytes remain in this durable snapshot; SHM is not a persisted ledger.
    empty = hashlib.sha256(b"").hexdigest()
    result = {
        name + "-wal": empty
        for name in ("jobs.sqlite3", "authority.sqlite3")
        if (root / name).is_file()
    }
    for p in root.rglob("*"):
        if p.is_symlink():
            pytest.fail("unexpected alias in owned snapshot")
        if p.is_file():
            if (
                p.name.startswith(".env")
                or p.name.endswith(".env")
                or ".env." in p.name
            ):
                pytest.fail("restricted file in owned snapshot")
            relative = p.relative_to(root).as_posix()
            if relative in {"jobs.sqlite3-shm", "authority.sqlite3-shm"}:
                continue
            result[relative] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def sqlite_journal_observation(root):
    return {
        name: {
            "present": (root / name).exists(),
            "bytes": (root / name).stat().st_size if (root / name).exists() else None,
        }
        for name in (
            "jobs.sqlite3-shm",
            "jobs.sqlite3-wal",
            "authority.sqlite3-shm",
            "authority.sqlite3-wal",
        )
    }


def rehash_authored_events(current, job_id, change):
    """Coherently edit a tiny owned fixture; external owner is not rewritten."""
    from structural_analysis.execution.job_service import _event_hash

    with current._connect() as db:
        events = db.execute(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY revision", (job_id,)
        ).fetchall()
        previous, reservations = None, {}
        for event in events:
            payload = json.loads(event["payload_json"])
            change(event, payload)
            if event["event_type"] == "rc_invocation_recorded":
                payload["reservation_event_hash"] = reservations[payload["ordinal"]]
                db.execute(
                    "UPDATE job_rc_invocation_outcomes SET reservation_event_hash=? WHERE job_id=? AND ordinal=?",
                    (payload["reservation_event_hash"], job_id, payload["ordinal"]),
                )
            digest, encoded = _event_hash(
                job_id=job_id,
                revision=event["revision"],
                event_type=event["event_type"],
                status=event["status"],
                occurred_at=event["occurred_at"],
                payload=payload,
                previous_event_hash=previous,
            )
            db.execute(
                "UPDATE job_events SET payload_json=?,previous_event_hash=?,event_hash=? WHERE job_id=? AND revision=?",
                (encoded, previous, digest, job_id, event["revision"]),
            )
            if event["event_type"] == "execution_attempt_reserved":
                reservations[payload["reserved_attempts"]] = digest
            previous = digest
        db.execute(
            "UPDATE jobs SET terminal_event_hash=? WHERE job_id=?", (previous, job_id)
        )
        db.commit()


def pure_historical_restore(current, job, payload, tmp_path, monkeypatch):
    from structural_analysis.execution import (
        rc_corotational_ordinal_job_request as requests,
    )
    from structural_analysis.assembly import (
        stateful_corotational_fiber_frame2d_ordinal_driver as driver,
    )
    from structural_analysis.assembly import (
        stateful_corotational_fiber_frame2d_ordinal_history as history,
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "historical source admission cannot fingerprint, assemble, solve or launch"
        )

    with monkeypatch.context() as patches:
        patches.setattr(requests, "_source_identity", forbidden)
        patches.setattr(driver, "_source_identity", forbidden)
        patches.setattr(driver, "run_ordinal_history", forbidden)
        patches.setattr(driver, "solve_scheduled_control_step", forbidden)
        patches.setattr(driver, "assemble_scheduled_frame", forbidden)
        patches.setattr(history, "solve_scheduled_control_step", forbidden)
        patches.setattr(worker.common.subprocess, "Popen", forbidden)
        before = byte_snapshot(current.root)
        original_journal_before = sqlite_journal_observation(current.root)
        owner_before = byte_snapshot(current._execution_authority.directory)
        assert current.validate_integrity(job.job_id, **TENANT)["contract_pass"]
        original = current.read_rc_invocation_evidence(job.job_id, **TENANT)
        with current._connect() as db:
            db.execute("BEGIN")
            row = current._job_row(db, job.job_id)
            typed = current._ordinal_typed_for_row(db, row)
            budget = current._ordinal_solver_budget(db, row)
        assert (
            current.submit_job(
                **TENANT, idempotency_key="ordinal-test", request=payload
            ).job_id
            == job.job_id
        )
        assert byte_snapshot(current.root) == before
        assert byte_snapshot(current._execution_authority.directory) == owner_before
        original_journal_after = sqlite_journal_observation(current.root)
        historical_status = current.get_job(job.job_id, **TENANT).status
        backed = backup_job_store(
            current.root, tmp_path / "historical-backup", maximum_bytes=20_000_000
        )
        restore_job_store(
            tmp_path / "historical-backup",
            tmp_path / "historical-restored",
            manifest_sha256=backed["manifest_sha256"],
            maximum_bytes=20_000_000,
        )
        activate_managed_restore(
            tmp_path / "historical-backup",
            tmp_path / "historical-restored",
            manifest_sha256=backed["manifest_sha256"],
            maximum_bytes=20_000_000,
            expected_generation=current._execution_binding.generation,
            expected_root=str(current.root),
        )
        fresh = service(tmp_path / "historical-restored")
        restored_journal_opened = sqlite_journal_observation(fresh.root)
        # Initialize this restored SQLite read connection before its protected
        # baseline. A first read may create an empty WAL; WAL data is never
        # excluded from the ensuing durable-byte checks.
        assert fresh.get_job(job.job_id, **TENANT).status == historical_status
        with pytest.raises(JobServiceError, match="execution_authority_rejected"):
            current.get_job(job.job_id, **TENANT)
        reader = fresh._connect()
        try:
            reader.execute("BEGIN")
            reader.execute(
                "SELECT job_id FROM jobs WHERE job_id=?", (job.job_id,)
            ).fetchone()
            restored_before, activated_owner = (
                byte_snapshot(fresh.root),
                byte_snapshot(fresh._execution_authority.directory),
            )
            assert fresh.validate_integrity(job.job_id, **TENANT)["contract_pass"]
            assert fresh.read_rc_invocation_evidence(job.job_id, **TENANT) == original
            with fresh._connect() as db:
                db.execute("BEGIN")
                row = fresh._job_row(db, job.job_id)
                assert (
                    fresh._ordinal_typed_for_row(db, row).execution_source_identity
                    == typed.execution_source_identity
                )
                assert fresh._ordinal_solver_budget(db, row) == budget
            assert byte_snapshot(fresh.root) == restored_before
            assert (
                byte_snapshot(fresh._execution_authority.directory) == activated_owner
            )
        finally:
            reader.rollback()
            reader.close()
        (tmp_path / "historical-sqlite-journal-observation.json").write_text(
            json.dumps(
                {
                    "original_before": original_journal_before,
                    "original_after": original_journal_after,
                    "restored_opened": restored_journal_opened,
                    "restored_after_reads": sqlite_journal_observation(fresh.root),
                    "absence_and_zero_byte_known_wal_have_equal_durable_content": True,
                    "nonempty_wal_data_db_blobs_binding_owner_grants_remain_strict": True,
                    "all_filesystem_bytes_unchanged_claim": False,
                },
                sort_keys=True,
            )
        )
    return original, budget, fresh


def service(root, **options):
    return DurableJobService(
        root,
        tenant_tokens={TENANT["tenant_id"]: TENANT["authorization_token"]},
        worker_tokens={WORKER["worker_id"]: WORKER["authorization_token"]},
        worker_tenants={WORKER["worker_id"]: {TENANT["tenant_id"]}},
        **options,
    )


def setup(tmp_path, payload=None):
    root = tmp_path / "source"
    authority, binding = JobExecutionAuthority.create(tmp_path / "authority", root)
    current = service(root, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(
        **TENANT,
        idempotency_key="ordinal-test",
        request=ordinal_request() if payload is None else payload,
    )
    return current, authority, binding, job


def claim(current):
    result = current.claim_next(**WORKER, lease_seconds=300)
    assert result is not None
    return result, dict(WORKER, lease_token=result.lease_token)


def reserve(
    current,
    job,
    credentials,
    *,
    ceiling=2,
    phase="production",
    prior=None,
    native=None,
    records=3,
):
    ordinal = current.reserve_execution_attempt(job.job_id, **credentials)
    grant = current.reserve_ordinal_solver_credits(
        job.job_id,
        **credentials,
        phase=phase,
        api_ordinal=ordinal,
        ceiling=ceiling,
        expected_checkpoint_hash=prior,
        native_input_sha256=native,
        record_limit=records,
    )
    return ordinal, grant


def test_native_same_g_new_p_hold_and_charged_suffix_report_reopen(
    tmp_path, monkeypatch
):
    current, authority, binding, job = setup(tmp_path)
    popen = worker.common.subprocess.Popen
    children = []

    def observed_popen(*args, **kwargs):
        guards = kwargs.get("pass_fds")
        assert type(guards) is tuple and len(guards) == 2 and guards[0] != guards[1]
        inherited = [os.readlink(f"/proc/self/fd/{fd}") for fd in guards]
        child = popen(*args, **kwargs)
        assert [os.readlink(f"/proc/{child.pid}/fd/{fd}") for fd in guards] == inherited
        children.append(child.pid)
        return child

    monkeypatch.setattr(worker.common.subprocess, "Popen", observed_popen)
    first, _ = claim(current)
    from structural_analysis.execution.job_worker import execute_job_claim

    saved = execute_job_claim(current, first, **WORKER)
    assert saved.status == "checkpointed" and saved.progress_completed == 3
    raw = current.read_checkpoint(job.job_id, **TENANT)
    wrapper = json.loads(raw)
    assert wrapper["api_result"]["work"]["solver_invocations"] == 2
    assert wrapper["api_result"]["work"]["hold_records"] == 1
    snapshots = wrapper["api_result"]["events"]
    assert (
        snapshots[0]["mechanical_state_hash"] == snapshots[1]["mechanical_state_hash"]
    )
    assert (
        snapshots[2]["mechanical_state_hash"] != snapshots[1]["mechanical_state_hash"]
    )
    assert all(
        e["accepted_state"]["external_loads_global"] is not None for e in snapshots
    )
    second, credentials = claim(current)
    final = worker.execute_rc_corotational_ordinal_claim(current, second, **WORKER)
    assert (
        final.status == "succeeded"
        and final.progress_completed == final.progress_total == 4
    )
    assert len(children) == 4
    for pid in children:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    (tmp_path / "successful-child-custody.json").write_text(
        json.dumps(
            {
                "child_pids": children,
                "child_count": 4,
                "all_reaped": True,
                "inherited_distinct_authority_and_job_guard_descriptors": True,
            },
            sort_keys=True,
        )
    )
    result = json.loads(current.read_result(job.job_id, **TENANT))
    assert result["solver_credit_budget"]["production"]["reserved"] == 4
    assert result["solver_credit_budget"]["verification"]["reserved"] == 4
    assert [r["production_credits_used"] for r in result["receipts"]] == [2, 1]
    assert [r["verification_credits_used"] for r in result["receipts"]] == [2, 1]
    assert (
        result["receipts"][-1]["prior_checkpoint_hash"] == saved.checkpoint.content_hash
    )
    assert (
        result["receipts"][-1]["validation_report"]["prefix_replay_solver_invocations"]
        == 0
    )

    def forbidden(*args, **kwargs):
        pytest.fail(
            "saved report must not solve, assemble or fingerprint current source"
        )

    for name in (
        "structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver._source_identity",
        "structural_analysis.execution.rc_corotational_ordinal_job_request._source_identity",
        "structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver.run_ordinal_history",
        "structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver.assemble_scheduled_frame",
    ):
        monkeypatch.setattr(name, forbidden)
    before_db = (current.root / "jobs.sqlite3").read_bytes()
    before_authority = (authority.directory / "authority.sqlite3").read_bytes()
    sources = dict(
        expected_request_hash=final.request.content_hash,
        expected_result_artifact_hash=final.result.content_hash,
        expected_evidence_artifact_hash=final.evidence.content_hash,
    )
    from structural_analysis.execution import job_service as service_module
    from structural_analysis.execution import (
        rc_corotational_ordinal_report as report_module,
    )

    originals_parser = service_module._strict_json_object
    original_builder = report_module.build_ordinal_report
    outcome_ids = set()
    highwater = []

    def observed_parser(data, path):
        parsed = originals_parser(data, path)
        if path == "/outcome":
            # Preserve exact JSON dict types. Identity integers do not retain
            # original blobs; reachable GC objects expose accidental aggregation.
            assert gc.is_tracked(parsed)
            outcome_ids.add(id(parsed))
            highwater.append(sum(id(obj) in outcome_ids for obj in gc.get_objects()))
        return parsed

    def single_use_report(request, result, evidence, **refs):
        stream = evidence["invocations"]
        assert iter(stream) is stream
        answer = original_builder(request, result, evidence, **refs)
        with pytest.raises(StopIteration):
            next(stream)
        return answer

    monkeypatch.setattr(service_module, "_strict_json_object", observed_parser)
    monkeypatch.setattr(report_module, "build_ordinal_report", single_use_report)
    report = current.read_rc_ordinal_report(job.job_id, **TENANT, **sources)
    assert max(highwater) <= 3  # one current entry + at most one accepted pair
    assert (
        service(current.root).read_rc_ordinal_report(job.job_id, **TENANT, **sources)
        == report
    )
    assert current.validate_integrity(job.job_id, **TENANT)["contract_pass"]
    assert (current.root / "jobs.sqlite3").read_bytes() == before_db
    assert (authority.directory / "authority.sqlite3").read_bytes() == before_authority
    parsed = json.loads(report)
    assert len(parsed["samples"]) == 4
    assert [r["ordinal"] for r in parsed["samples"]] == list(range(4))
    assert parsed["authority"]["experimental_physical_validation"] is False


def test_held_only_suffix_has_zero_grants_without_solver_callback(tmp_path):
    payload = ordinal_request([(-1e-6, 0.01)] * 4)
    payload["execution_config"].update(
        attempt_limit_per_call=1,
        record_limit_per_call=1,
        production_solver_budget=1,
        verification_solver_budget=1,
    )
    current, _authority, _binding, job = setup(tmp_path, payload)
    first, _ = claim(current)
    saved = worker.execute_rc_corotational_ordinal_claim(current, first, **WORKER)
    assert saved.progress_completed == 1
    for i in range(1, 4):
        next_claim, _ = claim(current)
        view = worker.execute_rc_corotational_ordinal_claim(
            current, next_claim, **WORKER
        )
        assert view.progress_completed == i + 1
    result = json.loads(current.read_result(job.job_id, **TENANT))
    assert [r["production_credits_used"] for r in result["receipts"]] == [1, 0, 0, 0]
    assert [g["ceiling"] for g in result["solver_credit_budget"]["reservations"]] == [
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert result["solver_credit_budget"]["production"]["reserved"] == 1
    assert result["solver_credit_budget"]["verification"]["reserved"] == 1
    assert result["receipts"][-1]["verification_work"]["solver_invocations"] == 0
    assert result["receipts"][-1]["verification_work"]["hold_records"] == 1


def test_credit_duplicate_reservation_zero_firstrow_and_exhaustion_reject(tmp_path):
    payload = ordinal_request()
    payload["execution_config"]["production_solver_budget"] = 2
    current, authority, binding, job = setup(tmp_path, payload)
    _claimed, credentials = claim(current)
    ordinal, grant = reserve(current, job, credentials)
    with pytest.raises(JobServiceError, match="already consumed"):
        current.reserve_ordinal_solver_credits(
            job.job_id,
            **credentials,
            phase="production",
            api_ordinal=ordinal,
            ceiling=2,
            expected_checkpoint_hash=None,
            native_input_sha256=None,
            record_limit=3,
        )
    with pytest.raises(JobServiceError, match="ordinal_solver_credit_zero_forbidden"):
        reserve(current, job, credentials, ceiling=0)
    with pytest.raises(JobServiceError, match="budget exhausted"):
        reserve(current, job, credentials, ceiling=1)
    budget = current.read_ordinal_solver_budget(job.job_id, **credentials)
    assert budget["production"] == {"maximum": 2, "reserved": 2, "remaining": 0}
    assert budget["reservations"] == [grant]
    assert (
        authority.read_ordinal_credits(
            binding, job.job_id, job.request.content_hash, grant["context_hash"]
        )
        == budget
    )


def test_solver_credit_external_commit_interruption_imports_unknown_no_refund(
    tmp_path, monkeypatch
):
    current, authority, binding, job = setup(tmp_path)
    _claimed, credentials = claim(current)
    ordinal = current.reserve_execution_attempt(job.job_id, **credentials)
    transition = current._transition

    def interrupted(*args, **kwargs):
        if kwargs.get("event_type") == "ordinal_solver_credit_reserved":
            raise RuntimeError("credit local commit interrupted")
        return transition(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(current, "_transition", interrupted)
        with pytest.raises(RuntimeError, match="credit local commit interrupted"):
            current.reserve_ordinal_solver_credits(
                job.job_id,
                **credentials,
                phase="production",
                api_ordinal=ordinal,
                ceiling=2,
                expected_checkpoint_hash=None,
                native_input_sha256=None,
                record_limit=3,
            )
    reopened = service(current.root)
    snapshot = reopened.read_ordinal_solver_budget(job.job_id, **credentials)
    assert snapshot["production"]["reserved"] == 2
    with sqlite3.connect(current.root / "jobs.sqlite3") as db:
        imported = json.loads(
            db.execute(
                "SELECT payload_json FROM job_events WHERE event_type='ordinal_solver_credit_imported'"
            ).fetchone()[0]
        )
    assert imported["execution_work"] == "unknown"
    assert snapshot == authority.read_ordinal_credits(
        binding, job.job_id, job.request.content_hash, snapshot["context_hash"]
    )
    with pytest.raises(JobServiceError, match="already consumed"):
        reopened.reserve_ordinal_solver_credits(
            job.job_id,
            **credentials,
            phase="production",
            api_ordinal=ordinal,
            ceiling=2,
            expected_checkpoint_hash=None,
            native_input_sha256=None,
            record_limit=3,
        )


def test_actual_credit_reserving_process_death_preserves_spend(tmp_path):
    current, authority, binding, job = setup(tmp_path)
    _claimed, credentials = claim(current)
    program = """import json,os,signal,sys
from tests.test_rc_ordinal_managed_owner import service
current=service(sys.argv[1]); args=json.loads(sys.argv[3]); job=sys.argv[2]
ordinal=current.reserve_execution_attempt(job,**args)
current.reserve_ordinal_solver_credits(job,**args,phase="production",api_ordinal=ordinal,ceiling=2,expected_checkpoint_hash=None,native_input_sha256=None,record_limit=3)
os.kill(os.getpid(),signal.SIGKILL)
"""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(current.root),
            job.job_id,
            json.dumps(credentials),
        ],
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == -signal.SIGKILL, proc.stderr.decode()
    snapshot = service(current.root).read_ordinal_solver_budget(
        job.job_id, **credentials
    )
    assert (
        snapshot["production"]["reserved"] == 2 and len(snapshot["reservations"]) == 1
    )
    journal = current.read_rc_invocation_evidence(job.job_id, **TENANT)
    assert journal["pending_ordinals"] == [1] and not journal["invocations"]
    assert (
        authority.read_ordinal_credits(
            binding, job.job_id, job.request.content_hash, snapshot["context_hash"]
        )
        == snapshot
    )


def test_child_process_failure_reaps_and_keeps_unknown_ceiling(tmp_path, monkeypatch):
    current, authority, binding, job = setup(tmp_path)
    next_claim, credentials = claim(current)
    monkeypatch.setattr(
        worker,
        "_child_argv",
        lambda parent: [sys.executable, "-I", "-c", "raise SystemExit(7)"],
    )
    with pytest.raises(worker.common.RCFiberPhaseError):
        worker.execute_rc_corotational_ordinal_claim(current, next_claim, **WORKER)
    journal = current.read_rc_invocation_evidence(job.job_id, **TENANT)
    outcome = json.loads(
        current.read_rc_invocation_artifact(job.job_id, **TENANT, ordinal=1)
    )
    assert outcome["status"] == "raised" and outcome["credits_used"] is None
    assert outcome["unavailable_execution_work"] is True
    assert outcome["phase_supervision"]["cleanup"]["direct_child_reaped"] is True
    assert journal["execution_budget"]["reserved_attempts"] == 1
    snapshot = authority.read_ordinal_credits(
        binding, job.job_id, job.request.content_hash, outcome["context_hash"]
    )
    assert snapshot["production"]["reserved"] == 2
    assert snapshot["verification"]["reserved"] == 0


def test_copied_root_refuses_owner_and_old_restore_retains_unknown_credits(tmp_path):
    current, authority, binding, job = setup(tmp_path)
    first, _ = claim(current)
    saved = worker.execute_rc_corotational_ordinal_claim(current, first, **WORKER)
    checkpoint = current.read_checkpoint(job.job_id, **TENANT)
    backup, restored, copied = (tmp_path / n for n in ("backup", "restored", "copied"))
    receipt = backup_job_store(current.root, backup, maximum_bytes=20_000_000)
    options = dict(manifest_sha256=receipt["manifest_sha256"], maximum_bytes=20_000_000)
    shutil.copytree(current.root, copied)
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        service(copied)
    next_claim, credentials = claim(current)
    native = base64.b64decode(
        json.loads(checkpoint)["terminal_checkpoint_artifact_base64"]
    )
    reserve(
        current,
        job,
        credentials,
        prior=saved.checkpoint.content_hash,
        native="sha256:" + hashlib.sha256(native).hexdigest(),
    )
    restore_job_store(backup, restored, **options)
    activated = activate_managed_restore(backup, restored, **options)
    assert activated["generation"] == 2
    with pytest.raises(JobServiceError, match="execution_authority_rejected"):
        current.read_ordinal_solver_budget(job.job_id, **credentials)
    fresh = service(restored)
    restored_claim, fresh_creds = claim(fresh)
    snapshot = fresh.read_ordinal_solver_budget(job.job_id, **fresh_creds)
    assert (
        snapshot["production"]["reserved"] == 4
        and snapshot["verification"]["reserved"] == 2
    )
    assert fresh.read_checkpoint(job.job_id, **TENANT) == checkpoint
    completed = worker.execute_rc_corotational_ordinal_claim(
        fresh, restored_claim, **WORKER
    )
    assert completed.status == "succeeded"
    final = json.loads(fresh.read_result(job.job_id, **TENANT))
    assert final["solver_credit_budget"]["production"]["reserved"] == 6
    assert [r["production_ordinal"] for r in final["receipts"]] == [1, 4]
    report = json.loads(
        fresh.read_rc_ordinal_report(
            job.job_id,
            **TENANT,
            expected_request_hash=completed.request.content_hash,
            expected_result_artifact_hash=completed.result.content_hash,
            expected_evidence_artifact_hash=completed.evidence.content_hash,
        )
    )
    assert report["unknown_reserved_api_ordinals"] == [3]
    assert report["unknown_solver_grant_api_ordinals"] == [3]
    assert report["known_solver_invocations"] == {"production": 3, "verification": 3}
    assert len(report["samples"]) == 4


def test_verification_credit_exhaustion_refuses_before_either_child(
    tmp_path, monkeypatch
):
    payload = ordinal_request([(-1e-6, 0.01), (-2e-6, 0.02)])
    payload["execution_config"]["verification_solver_budget"] = 1
    payload["execution_config"]["record_limit_per_call"] = 1
    current, _authority, _binding, job = setup(tmp_path, payload)
    first, _ = claim(current)
    saved = worker.execute_rc_corotational_ordinal_claim(current, first, **WORKER)
    assert saved.progress_completed == 1
    original_checkpoint = current.read_checkpoint(job.job_id, **TENANT)
    second, _ = claim(current)

    def forbidden(**kwargs):
        pytest.fail("no child may start without both immutable credit grants")

    monkeypatch.setattr(worker, "run_ordinal_phase", forbidden)
    with pytest.raises(worker.RCOrdinalWorkerError, match="solver_budget_exhausted"):
        worker.execute_rc_corotational_ordinal_claim(current, second, **WORKER)
    assert (
        current.read_rc_invocation_evidence(job.job_id, **TENANT)["execution_budget"][
            "reserved_attempts"
        ]
        == 2
    )
    assert current.read_checkpoint(job.job_id, **TENANT) == original_checkpoint


def test_rehashed_native_prefix_never_authorizes_a_different_owned_input(tmp_path):
    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
        canonical_hash,
        json_bytes,
    )
    from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
        _native,
    )

    current, _authority, _binding, job = setup(tmp_path)
    first, _ = claim(current)
    saved = worker.execute_rc_corotational_ordinal_claim(current, first, **WORKER)
    original = current.read_checkpoint(job.job_id, **TENANT)
    typed = validate_rc_corotational_ordinal_job_request(first.request_bytes)
    wrapper = json.loads(original)
    raw = base64.b64decode(wrapper["terminal_checkpoint_artifact_base64"])
    native = json.loads(raw)
    native["ledger_hash"] = "sha256:" + "d" * 64
    native["artifact_hash"] = canonical_hash(
        {k: v for k, v in native.items() if k != "artifact_hash"}
    )
    changed = json_bytes(native)
    # Structural self-consistency is explicitly weaker than owner custody.
    assert _native(typed, changed).next_ordinal == 3
    second, credentials = claim(current)
    ordinal = current.reserve_execution_attempt(job.job_id, **credentials)
    with pytest.raises(JobServiceError, match="ordinal_native_prefix_mismatch"):
        current.reserve_ordinal_solver_credits(
            job.job_id,
            **credentials,
            phase="production",
            api_ordinal=ordinal,
            ceiling=2,
            expected_checkpoint_hash=saved.checkpoint.content_hash,
            native_input_sha256="sha256:" + hashlib.sha256(changed).hexdigest(),
            record_limit=3,
        )
    forged = deepcopy(wrapper)
    forged["terminal_checkpoint_artifact_base64"] = base64.b64encode(changed).decode()
    forged["checkpoint_hash"] = (
        "sha256:"
        + hashlib.sha256(
            worker.common._json(
                {k: v for k, v in forged.items() if k != "checkpoint_hash"}
            )
        ).hexdigest()
    )
    counterfeit = replace(second, checkpoint_bytes=worker.common._json(forged))
    with pytest.raises(worker.RCOrdinalWorkerError, match="checkpoint_binding_changed"):
        worker.execute_rc_corotational_ordinal_claim(current, counterfeit, **WORKER)
    assert current.read_checkpoint(job.job_id, **TENANT) == original


def test_missing_or_partial_credit_namespace_cannot_reset_spent_ceiling(tmp_path):
    current, authority, binding, job = setup(tmp_path)
    _claimed, credentials = claim(current)
    reserve(current, job, credentials)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("DROP TABLE ordinal_credit_reservations")
    with pytest.raises(JobServiceError, match="ordinal_solver_authority_rejected"):
        current.read_ordinal_solver_budget(job.job_id, **credentials)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("DROP TABLE ordinal_credit_budgets")
    with pytest.raises(
        JobServiceError, match="ordinal_solver_authority_rejected"
    ) as error:
        current.read_ordinal_solver_budget(job.job_id, **credentials)
    assert error.value.code == "ordinal_solver_authority_rejected"
    assert (
        authority.read_budget(binding, job.job_id, job.request.content_hash)[
            "reserved_attempts"
        ]
        == 1
    )
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name IN ('ordinal_credit_budgets','ordinal_credit_reservations')"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize("ceiling", [True, 3, 256])
def test_operation_grant_bounds_reject_before_owner_spend(tmp_path, ceiling):
    current, _authority, _binding, job = setup(tmp_path)
    _claimed, credentials = claim(current)
    with pytest.raises(JobServiceError, match="ordinal_solver_grant_bounds_invalid"):
        reserve(current, job, credentials, ceiling=ceiling)
    assert not current.read_ordinal_solver_budget(job.job_id, **credentials)[
        "reservations"
    ]


def test_pending_subdivision_checkpoint_advances_work_without_row_or_epoch(tmp_path):
    payload = ordinal_request([(0.0, 0.0), (0.0, 1.0)])
    payload["config"]["solver_config"]["maximum_iterations"] = 0
    payload["execution_config"].update(
        attempt_limit_per_call=1, record_limit_per_call=1
    )
    current, _authority, _binding, job = setup(tmp_path, payload)
    first, _ = claim(current)
    initial = worker.execute_rc_corotational_ordinal_claim(current, first, **WORKER)
    assert initial.status == "checkpointed" and initial.progress_completed == 1
    original = json.loads(current.read_checkpoint(job.job_id, **TENANT))
    second, _ = claim(current)
    subdivided = worker.execute_rc_corotational_ordinal_claim(current, second, **WORKER)
    assert subdivided.status == "checkpointed" and subdivided.progress_completed == 1
    updated = json.loads(current.read_checkpoint(job.job_id, **TENANT))
    old_native = json.loads(
        base64.b64decode(original["terminal_checkpoint_artifact_base64"])
    )
    new_native = json.loads(
        base64.b64decode(updated["terminal_checkpoint_artifact_base64"])
    )
    assert new_native["mechanical"] == old_native["mechanical"]
    assert new_native["next_ordinal"] == old_native["next_ordinal"] == 1
    assert new_native["pending_positions"] == [[1, 1], [1, 0]]
    assert updated["api_result"]["work"]["failed_attempts"] == 1
    assert len(updated["receipts"]) == 2
    assert (
        updated["receipts"][-1]["prior_checkpoint_hash"]
        == initial.checkpoint.content_hash
    )
    assert current.validate_integrity(job.job_id, **TENANT)["contract_pass"]


def test_bootstrap_exact_ordinal_entry_does_not_admit_same_name_outside_source(
    tmp_path,
):
    marker = tmp_path / "imported"
    wrong = tmp_path / "rc_corotational_ordinal_worker.py"
    wrong.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            str(worker.common._BOOTSTRAP_PATH),
            str(os.getpid()),
            str(worker._SOURCE_ROOT),
            str(wrong),
            "[]",
        ],
        capture_output=True,
        timeout=10,
    )
    assert child.returncode != 0
    assert b"entry differs from its source root" in child.stderr
    assert not marker.exists()


def test_actual_worker_parent_death_kills_inherited_child_and_retains_unknown_255(
    tmp_path,
    monkeypatch,
):
    payload = ordinal_request(
        [(-1e-6 * (1 + i % 2), 0.01 + 0.001 * i) for i in range(300)]
    )
    payload["config"]["maximum_solver_attempts"] = 300
    payload["execution_config"].update(
        attempt_limit_per_call=255,
        record_limit_per_call=255,
        production_solver_budget=300,
        verification_solver_budget=300,
    )
    current, authority, binding, job = setup(tmp_path, payload)
    next_claim, credentials = claim(current)
    marker = tmp_path / "numerical-child.json"
    runner = """import json,sys
from pathlib import Path
from tests.test_rc_ordinal_managed_owner import service,WORKER
from structural_analysis.execution import rc_corotational_ordinal_worker as w
from structural_analysis.execution.job_service import JobClaim
s=service(sys.argv[1]); tenant=dict(tenant_id="tenant",authorization_token="ordinal-tenant-secret")
job=s.get_job(sys.argv[2],**tenant); request=s.read_request(job.job_id,**tenant)
claim=JobClaim(job,sys.argv[3],request,None)
original=w.common.subprocess.Popen
def tracked(*args,**kwargs):
 child=original(*args,**kwargs)
 Path(sys.argv[4]).write_text(json.dumps({"child_pid":child.pid,"guards":list(kwargs["pass_fds"])}))
 return child
w.common.subprocess.Popen=tracked
w.execute_rc_corotational_ordinal_claim(s,claim,**WORKER)
"""
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            runner,
            str(current.root),
            job.job_id,
            next_claim.lease_token,
            str(marker),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if parent.poll() is not None:
                _out, err = parent.communicate()
                pytest.fail(f"ordinal parent ended before death test: {err.decode()}")
            if marker.exists():
                record = json.loads(marker.read_bytes())
                child_pid = record["child_pid"]
                try:
                    maps = Path(f"/proc/{child_pid}/maps").read_text()
                except FileNotFoundError:
                    maps = ""
                # NumPy imports happen AFTER bootstrap's prctl/parent-race check.
                if "numpy" in maps:
                    assert len(record["guards"]) == 2
                    assert all(
                        Path(f"/proc/{child_pid}/fd/{fd}").exists()
                        for fd in record["guards"]
                    )
                    break
            time.sleep(0.01)
        else:
            pytest.fail("live isolated ordinal child was not observed")
        parent.kill()
        assert parent.wait(timeout=10) == -signal.SIGKILL
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                state = (
                    Path(f"/proc/{child_pid}/stat")
                    .read_text()
                    .split(") ", 1)[1]
                    .split()[0]
                )
            except FileNotFoundError:
                state = "missing"
            if state in ("Z", "missing"):
                break
            time.sleep(0.01)
        else:
            pytest.fail("inherited child survived parent SIGKILL")
        # A dead parent's child may await the system reaper; it has no open
        # descriptors and cannot retain a managed/job permit or run numerics.
        if state == "Z":
            assert not list(Path(f"/proc/{child_pid}/fd").iterdir())
        with current.execution_guard():
            with current.job_execution_permit(
                job.job_id,
                **credentials,
                expected_request_hash=job.request.content_hash,
            ) as permit:
                assert type(permit) is int
        credits = current.read_ordinal_solver_budget(job.job_id, **credentials)
        assert credits["production"]["reserved"] == 255
        assert credits["verification"]["reserved"] == 0
        assert len(credits["reservations"]) == 1
        journal = current.read_rc_invocation_evidence(job.job_id, **TENANT)
        assert journal["pending_ordinals"] == [1] and not journal["invocations"]
        assert current.get_job(job.job_id, **TENANT).checkpoint is None
        (tmp_path / "parent-death-custody.json").write_text(
            json.dumps(
                {
                    "parent_pid": parent.pid,
                    "parent_reaped_returncode": parent.returncode,
                    "direct_child_pid": child_pid,
                    "direct_child_observed_state": state,
                    "numerical_child_dead": True,
                    "child_descriptors_closed": True,
                    "managed_and_job_guards_reacquired": True,
                    "unknown_production_ceiling": 255,
                    "actual_solver_count": None,
                    "reaped_by_dead_parent": False,
                },
                sort_keys=True,
            )
        )
        assert (
            authority.read_ordinal_credits(
                binding, job.job_id, job.request.content_hash, credits["context_hash"]
            )
            == credits
        )
        historical, recovered, _fresh = pure_historical_restore(
            current, job, payload, tmp_path, monkeypatch
        )
        assert historical["pending_ordinals"] == [1]
        assert recovered["production"]["reserved"] == 255
        assert recovered["verification"]["reserved"] == 0
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=10)


def test_first_failed_subdivision_checkpoint_at_zero_cursor_keeps_trusted_native_input(
    tmp_path,
):
    payload = ordinal_request([(-1e-6, 0.01)])
    payload["config"]["solver_config"]["maximum_iterations"] = 0
    payload["execution_config"].update(
        attempt_limit_per_call=1, record_limit_per_call=1
    )
    current, _authority, _binding, job = setup(tmp_path, payload)
    first, _ = claim(current)
    saved = worker.execute_rc_corotational_ordinal_claim(current, first, **WORKER)
    assert saved.status == "checkpointed" and saved.progress_completed == 0
    original = json.loads(current.read_checkpoint(job.job_id, **TENANT))
    native = json.loads(
        base64.b64decode(original["terminal_checkpoint_artifact_base64"])
    )
    assert native["mechanical"]["certified"] is False
    assert native["solver_invocations"] == 1 and native["mechanical_commits"] == 0
    second, _ = claim(current)
    repeated = worker.execute_rc_corotational_ordinal_claim(current, second, **WORKER)
    assert repeated.progress_completed == 0 and repeated.status == "checkpointed"
    updated = json.loads(current.read_checkpoint(job.job_id, **TENANT))
    assert (
        updated["receipts"][-1]["restart_input_sha256"]
        == original["receipts"][-1]["checkpoint_sha256"]
    )
    assert (
        updated["receipts"][-1]["prior_checkpoint_hash"]
        == saved.checkpoint.content_hash
    )
    assert updated["api_result"]["work"]["failed_attempts"] == 1
    assert current.validate_integrity(job.job_id, **TENANT)["contract_pass"]


def test_matching_blocked_suffix_retains_both_phases_and_reports_native_failure(
    tmp_path, monkeypatch
):
    payload = ordinal_request([(-1e-6, 0.01)])
    payload["config"]["maximum_subdivision_depth"] = 0
    payload["config"]["solver_config"]["maximum_iterations"] = 0
    payload["execution_config"].update(
        attempt_limit_per_call=100, record_limit_per_call=1
    )
    current, authority, binding, job = setup(tmp_path, payload)
    typed = validate_rc_corotational_ordinal_job_request(payload)
    initial, _plan, _config = typed.prepare()
    from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
        initial_mechanical_checkpoint,
    )

    genesis = initial_mechanical_checkpoint(
        initial, typed.context_hash
    ).frame_checkpoint
    children = []
    original_popen = worker.common.subprocess.Popen

    def observed(*args, **kwargs):
        assert len(kwargs["pass_fds"]) == 2
        assert kwargs["pass_fds"][0] != kwargs["pass_fds"][1]
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(worker.common.subprocess, "Popen", observed)
    claimed, _credentials = claim(current)
    from structural_analysis.execution.job_worker import execute_job_claim

    with pytest.raises(worker.RCOrdinalWorkerError, match="rc_ordinal_native_blocked"):
        execute_job_claim(current, claimed, **WORKER)
    assert len(children) == 2 and all(c.returncode == 0 for c in children)
    failed = current.get_job(job.job_id, **TENANT)
    assert failed.status == "failed" and failed.progress_completed == 0
    assert failed.checkpoint is failed.result is None
    with current._connect() as connection:
        event = connection.execute(
            "SELECT payload_json FROM job_events WHERE job_id=? AND event_type='failed'",
            (job.job_id,),
        ).fetchone()
    assert json.loads(event[0])["error_code"] == "rc_ordinal_native_blocked"
    evidence = current.read_rc_invocation_evidence(job.job_id, **TENANT)
    assert evidence["execution_budget"]["reserved_attempts"] == 2
    assert evidence["pending_ordinals"] == []
    assert [r["ordinal"] for r in evidence["invocations"]] == [1, 2]
    production = json.loads(
        current.read_rc_invocation_artifact(job.job_id, ordinal=1, **TENANT)
    )
    verification = json.loads(
        current.read_rc_invocation_artifact(job.job_id, ordinal=2, **TENANT)
    )
    api, report = production["api_result"], verification["verification_report"]
    assert production["status"] == verification["status"] == "returned"
    assert production["credits_used"] == verification["credits_used"] == 1
    assert api["status"] == "blocked" and report["contract_pass"] is False
    assert report["artifact_contract_pass"] is True
    from structural_analysis.execution.rc_corotational_job_request import (
        rc_corotational_job_canonical_bytes,
    )

    assert (
        report["result_artifact_sha256"]
        == "sha256:"
        + hashlib.sha256(rc_corotational_job_canonical_bytes(api)).hexdigest()
    )
    native_bytes = base64.b64decode(
        production["checkpoint_artifact_base64"], validate=True
    )
    assert (
        report["continuation_sha256"]
        == "sha256:" + hashlib.sha256(native_bytes).hexdigest()
    )
    assert report["replay_work"] == api["work"]
    assert api["work"]["mechanical_commits"] == 0
    assert api["work"]["failed_attempts"] == 1
    assert api["events"][0]["rollback_exact"] is True
    from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
        _native,
    )

    native = _native(typed, native_bytes)
    assert (
        native.mechanical.frame_checkpoint.canonical_bytes()
        == genesis.canonical_bytes()
    )
    credits = authority.read_ordinal_credits(
        binding, job.job_id, job.request.content_hash, typed.context_hash
    )
    assert all(
        credits[phase]["reserved"] == 100 for phase in ("production", "verification")
    )
    assert len(credits["reservations"]) == 2
    assert all(
        outcome["phase_supervision"]["supervisor"]["direct_child_reaped"] is True
        for outcome in (production, verification)
    )
    (tmp_path / "matching-blocked-child-custody.json").write_text(
        json.dumps(
            {
                "direct_child_pids": [c.pid for c in children],
                "returncodes": [c.returncode for c in children],
                "direct_children_reaped_by_live_parent": True,
                "api_reserved": 2,
                "reserved_each_phase": 100,
                "known_each_phase": 1,
                "accepted_checkpoint": False,
                "numeric_prefix_replay": False,
                "durable_byte_checks_exclude_volatile_sqlite_shm": True,
            },
            sort_keys=True,
        )
    )

    # Simulate the former submitted-event shape while retaining the genuine
    # recorded production originals and external context of these real children.
    def remove_old_source_pin(event, payload):
        if event["revision"] == 0:
            payload.pop("ordinal_source_identity")
            payload.pop("ordinal_context_hash")

    rehash_authored_events(current, job.job_id, remove_old_source_pin)
    historical, recovered, fresh = pure_historical_restore(
        current, job, payload, tmp_path, monkeypatch
    )
    assert historical["pending_ordinals"] == []
    assert (
        recovered["production"]["reserved"]
        == recovered["verification"]["reserved"]
        == 100
    )
    # Rehash every local layer coherently after changing only the native source
    # claim. The separate external context still rejects this fabricated claim.
    from structural_analysis.engine_v2.contracts._canonical import canonical_hash

    edited = deepcopy(production)
    native_payload = json.loads(base64.b64decode(edited["checkpoint_artifact_base64"]))
    native_payload["source_identity"] = "sha256:" + "0" * 64
    native_payload["artifact_hash"] = canonical_hash(
        {k: v for k, v in native_payload.items() if k != "artifact_hash"}
    )
    altered_native = rc_corotational_job_canonical_bytes(native_payload)
    edited["checkpoint_artifact_base64"] = base64.b64encode(altered_native).decode(
        "ascii"
    )
    edited["api_result"]["continuation_sha256"] = (
        "sha256:" + hashlib.sha256(altered_native).hexdigest()
    )
    edited["api_result"]["result_hash"] = (
        "sha256:"
        + hashlib.sha256(
            rc_corotational_job_canonical_bytes(
                {k: v for k, v in edited["api_result"].items() if k != "result_hash"}
            )
        ).hexdigest()
    )
    altered = rc_corotational_job_canonical_bytes(edited)
    digest = hashlib.sha256(altered).hexdigest()
    path = fresh.root / "blobs" / "sha256" / digest[:2] / digest
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(altered)
    with fresh._connect() as db:
        db.execute(
            "UPDATE job_rc_invocation_outcomes SET outcome_hash=?,outcome_size=? WHERE job_id=? AND ordinal=1",
            ("sha256:" + digest, len(altered), job.job_id),
        )
        db.commit()

    def changed_original(event, value):
        if event["event_type"] == "rc_invocation_recorded" and value["ordinal"] == 1:
            value.update(outcome_hash="sha256:" + digest, outcome_size=len(altered))

    rehash_authored_events(fresh, job.job_id, changed_original)
    from structural_analysis.execution import (
        rc_corotational_ordinal_job_request as requests,
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("source forgery cannot select the current code identity")

    monkeypatch.setattr(requests, "_source_identity", forbidden)
    before, owner_before = (
        byte_snapshot(fresh.root),
        byte_snapshot(fresh._execution_authority.directory),
    )
    with pytest.raises(JobServiceError, match="ordinal_original_source_invalid"):
        fresh.read_rc_invocation_evidence(job.job_id, **TENANT)
    assert (
        byte_snapshot(fresh.root) == before
        and byte_snapshot(fresh._execution_authority.directory) == owner_before
    )


@pytest.mark.parametrize(
    "field",
    [
        "ordinal_source_identity",
        "ordinal_context_hash",
        "request_hash",
        "external_context",
        "missing_legacy_source",
    ],
)
def test_rehashed_submitted_source_cannot_override_external_context(
    tmp_path, monkeypatch, field
):
    payload = ordinal_request()
    current, authority, binding, job = setup(tmp_path, payload)

    def changed(event, value):
        if event["revision"] != 0:
            return
        if field == "missing_legacy_source":
            value.pop("ordinal_source_identity")
            value.pop("ordinal_context_hash")
        elif field != "external_context":
            value[field] = "sha256:" + "0" * 64

    if field == "external_context":
        with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
            db.execute(
                "UPDATE ordinal_credit_budgets SET context_hash=? WHERE job_id=?",
                ("sha256:" + "0" * 64, job.job_id),
            )
    else:
        rehash_authored_events(current, job.job_id, changed)
    from structural_analysis.execution import (
        rc_corotational_ordinal_job_request as requests,
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("unproven historical source cannot inspect current source")

    monkeypatch.setattr(requests, "_source_identity", forbidden)
    before, owner_before = (
        byte_snapshot(current.root),
        byte_snapshot(authority.directory),
    )
    with pytest.raises(JobServiceError, match="ordinal_original_source_invalid"):
        current.read_rc_invocation_evidence(job.job_id, **TENANT)
    assert (
        byte_snapshot(current.root) == before
        and byte_snapshot(authority.directory) == owner_before
    )
