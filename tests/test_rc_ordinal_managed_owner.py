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
    current, authority, _binding, job = setup(tmp_path)
    _claimed, credentials = claim(current)
    reserve(current, job, credentials)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("DROP TABLE ordinal_credit_reservations")
    with pytest.raises(JobServiceError, match="ordinal_solver_authority_rejected"):
        current.read_ordinal_solver_budget(job.job_id, **credentials)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("DROP TABLE ordinal_credit_budgets")
    with pytest.raises(JobServiceError, match="prior API spend"):
        current.read_ordinal_solver_budget(job.job_id, **credentials)


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
