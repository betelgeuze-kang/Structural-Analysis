"""Real subprocess interruption and durable authority; synthetic child workloads.

Blocking child entries use the production parent-death arming function but do
not call the numerical solver. A fresh real first analysis/verification produces
our prefix. These tests prove lifecycle/state behavior, not numerical speed or
whole-worker, memory, disk, arbitrary-descendant or hardware qualification.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import ctypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from textwrap import dedent
import time

import pytest

from structural_analysis.execution import rc_fiber_direct_control_worker as worker
from structural_analysis.execution import rc_fiber_phase_supervisor as supervisor
from structural_analysis.execution.job_service import JobServiceError
from tests.test_rc_fiber_durable_worker import (
    Clock,
    TENANT_AUTH,
    _bytes,
    _claim,
    _credentials,
    _evidence,
    _request,
    _run,
    _service,
    _submit,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux phase lifecycle")
ROOT = Path(__file__).resolve().parents[1]
POLICY = {
    "schema_version": "bounded-rc-fiber-phase-execution-policy.v1",
    "analysis_timeout_ms": 5_000,
    "verification_timeout_ms": 5_000,
    "termination_grace_ms": 50,
}


@pytest.fixture(scope="module")
def isolated_prefix(tmp_path_factory):
    directory = tmp_path_factory.mktemp("rc-isolated-lifecycle-prefix")
    request = _request()
    request["execution_config"]["phase_execution_policy"] = deepcopy(POLICY)
    service = _service(directory / "store")
    job = _submit(service, request)
    saved = _run(service, _claim(service))
    assert saved.status == "checkpointed" and saved.progress_completed == 1
    checkpoint = service.read_checkpoint(job.job_id, **TENANT_AUTH)
    evidence = _evidence(service, job.job_id, **TENANT_AUTH)
    assert evidence["pending_ordinals"] == []
    assert [r["ordinal"] for r in evidence["records"]] == [1, 2]
    for record in evidence["records"]:
        assert record["outcome"]["status"] == "returned"
        assert record["outcome"]["timing"]["process_cpu_ns"] > 0
    (directory / "request.json").write_bytes(_bytes(request))
    (directory / "checkpoint.json").write_bytes(checkpoint)
    (directory / "evidence.json").write_bytes(_bytes(evidence))
    return directory, job.job_id, checkpoint, evidence


def _prefix_copy(isolated_prefix, tmp_path, clock=None):
    directory, job_id, checkpoint, evidence = isolated_prefix
    shutil.copytree(directory / "store", tmp_path / "store")
    service = _service(tmp_path / "store", clock)
    claim = _claim(service)
    assert claim.job.job_id == job_id and claim.checkpoint_bytes == checkpoint
    assert _evidence(service, job_id, **TENANT_AUTH)["records"] == evidence["records"]
    return service, claim


def _blocking_entry(directory):
    entry = directory / "blocking-phase.py"
    entry.write_text(
        "import os,runpy,signal,sys\n"
        "from pathlib import Path\n"
        "bootstrap=runpy.run_path(sys.argv[2])\n"
        "bootstrap['_arm_parent_death_signal'](int(sys.argv[1]))\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "marker=Path(sys.argv[3]);temporary=marker.with_suffix('.tmp')\n"
        "temporary.write_text(str(os.getpid()));temporary.replace(marker)\n"
        "while True: signal.pause()\n"
    )
    return entry


def _pid_live(pid):
    try:
        # A zombie is no longer executing. Parent-death tests additionally reap
        # adopted children; ordinary timeout tests require supervisor reaping.
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def _wait_marker(marker, parent=None):
    limit = time.monotonic() + 15
    while time.monotonic() < limit:
        if marker.exists():
            return int(marker.read_text())
        if parent is not None and parent.poll() is not None:
            raise AssertionError(
                f"worker parent exited {parent.returncode} before child readiness"
            )
        time.sleep(0.01)
    raise AssertionError("blocking child did not become ready")


def _assert_no_live_pid(pid):
    limit = time.monotonic() + 3
    while time.monotonic() < limit and _pid_live(pid):
        time.sleep(0.01)
    assert not _pid_live(pid), f"child {pid} still executes"


def _block_phase(monkeypatch, entry, marker, phase):
    original = supervisor.run_rc_fiber_phase

    def run(**kwargs):
        if kwargs["phase"] != phase:
            return original(**kwargs)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                supervisor,
                "_child_argv",
                lambda expected: [
                    sys.executable,
                    "-I",
                    str(entry),
                    str(expected),
                    str(supervisor._BOOTSTRAP_PATH),
                    str(marker),
                ],
            )
            return original(**kwargs)

    monkeypatch.setattr(supervisor, "run_rc_fiber_phase", run)


@pytest.mark.parametrize("phase,ordinal", [("analysis", 3), ("verification", 4)])
def test_real_phase_timeout_reaps_child_retains_prefix_and_unknown(
    isolated_prefix, tmp_path, monkeypatch, phase, ordinal
):
    service, claim = _prefix_copy(isolated_prefix, tmp_path)
    marker = tmp_path / "child-ready"
    _block_phase(monkeypatch, _blocking_entry(tmp_path), marker, phase)
    with pytest.raises(worker.RCFiberDirectControlWorkerError) as caught:
        _run(service, claim)
    assert caught.value.code == f"rc_fiber_worker_{phase}_timeout"
    pid = _wait_marker(marker)
    _assert_no_live_pid(pid)
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)  # Supervisor already reaped its direct child.
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.error_code == caught.value.code
    assert failed.checkpoint == claim.job.checkpoint and failed.progress_completed == 1
    assert failed.result is failed.evidence is None
    assert (
        service.read_checkpoint(failed.job_id, **TENANT_AUTH) == claim.checkpoint_bytes
    )
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    assert evidence["pending_ordinals"] == [ordinal]
    assert evidence["execution_budget"]["reserved_attempts"] == ordinal
    assert evidence["records"][:2] == isolated_prefix[3]["records"]
    assert [r["ordinal"] for r in evidence["records"]] == list(range(1, ordinal))
    if phase == "verification":
        assert evidence["records"][-1]["outcome"]["phase"] == "analysis"
        assert evidence["records"][-1]["outcome"]["status"] == "returned"
    (tmp_path / "interruption-proof.json").write_bytes(
        _bytes(
            {
                "phase": phase,
                "error_code": caught.value.code,
                "direct_child_pid": pid,
                "direct_child_no_longer_live_and_reaped": True,
                "verified_prefix_unchanged": True,
                "pending_ordinals": evidence["pending_ordinals"],
                "workload": "synthetic blocking entry; real production supervisor/service",
            }
        )
    )


def test_observed_lease_failure_cleans_child_without_mutating_successor(
    isolated_prefix, tmp_path, monkeypatch
):
    service, claim = _prefix_copy(isolated_prefix, tmp_path)
    marker = tmp_path / "child-ready"
    _block_phase(monkeypatch, _blocking_entry(tmp_path), marker, "analysis")
    original_check = worker._LeaseKeeper.check
    successor = []

    def check(lease):
        original_check(lease)
        if marker.exists() and not successor:
            service.fail_job(
                claim.job.job_id,
                **_credentials(claim),
                error_code="synthetic_retriable_takeover",
                retriable=True,
            )
            successor.append(_claim(service))
            raise JobServiceError(
                "rc_fiber_worker_lease_renewal_failed",
                "/lease",
                "Synthetic keeper failure after a real replacement lease.",
            )

    monkeypatch.setattr(worker._LeaseKeeper, "check", check)
    with pytest.raises(JobServiceError, match="lease_renewal_failed"):
        _run(service, claim)
    pid = _wait_marker(marker)
    _assert_no_live_pid(pid)
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)
    current = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert current.status == "running" and current.revision == successor[0].job.revision
    assert current.checkpoint == successor[0].job.checkpoint == claim.job.checkpoint
    assert successor[0].checkpoint_bytes == claim.checkpoint_bytes
    assert current.result is current.evidence is None
    evidence = _evidence(service, current.job_id, **TENANT_AUTH)
    assert evidence["pending_ordinals"] == [3]
    assert evidence["records"] == isolated_prefix[3]["records"]


@contextmanager
def _test_subreaper():
    # Only this test process adopts its OWN descendants; restore on every path.
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    try:
        yield
    finally:
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def _cleanup_owned_child(pid):
    try:
        observed = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return  # Another reaper owns it; never signal a reusable numeric PID.
    if observed is None:
        os.kill(pid, signal.SIGKILL)  # Owned live child cannot be reused yet.
    assert os.waitpid(pid, 0)[0] == pid


@pytest.mark.parametrize("phase,ordinal", [("analysis", 3), ("verification", 4)])
def test_real_parent_sigkill_reopens_exact_prefix_and_abandoned_ordinal(
    isolated_prefix, tmp_path, phase, ordinal
):
    with _test_subreaper():
        parent = None
        child_pid = None
        child_reaped = False
        marker = tmp_path / "child-ready"
        try:
            service, claim = _prefix_copy(isolated_prefix, tmp_path)
            # Requeue our unused claim so the separate actual parent claims itself.
            service.fail_job(
                claim.job.job_id,
                **_credentials(claim),
                error_code="test_parent_setup",
                retriable=True,
            )
            marker = tmp_path / "child-ready"
            entry = _blocking_entry(tmp_path)
            parent_code = dedent(r"""
        import json,sys
        from pathlib import Path
        from structural_analysis.execution import rc_fiber_phase_supervisor as s
        from tests.test_rc_fiber_durable_worker import _service,_claim,_run
        store,entry,marker,phase=sys.argv[1:]
        original=s.run_rc_fiber_phase
        def run(**kw):
         if kw['phase']!=phase:return original(**kw)
         old=s._child_argv
         try:
          s._child_argv=lambda expected:[sys.executable,'-I',entry,str(expected),str(s._BOOTSTRAP_PATH),marker]
          return original(**kw)
         finally:s._child_argv=old
        s.run_rc_fiber_phase=run
        service=_service(Path(store))
        _run(service,_claim(service))
        """)
            with (tmp_path / "parent.log").open("wb") as log:
                parent = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        parent_code,
                        str(tmp_path / "store"),
                        str(entry),
                        str(marker),
                        phase,
                    ],
                    cwd=ROOT,
                    env={
                        "PATH": "/usr/bin:/bin",
                        "PYTHONPATH": str(ROOT / "src") + ":" + str(ROOT),
                    },
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                child_pid = _wait_marker(marker, parent)
                parent.kill()
                assert parent.wait(timeout=5) == -9
                _assert_no_live_pid(child_pid)
                # PDEATHSIG stops the direct child. The test guardian reaps the
                # adopted orphan; it is not a production guardian claim.
                waited_pid, child_status = os.waitpid(child_pid, 0)
                child_reaped = True
                assert waited_pid == child_pid
                child_returncode = os.waitstatus_to_exitcode(child_status)
                assert child_returncode == -signal.SIGKILL
            clock = Clock()
            clock.advance(301)
            reopened = _service(tmp_path / "store", clock)
            before = reopened.get_job(claim.job.job_id, **TENANT_AUTH)
            assert before.status == "running" and before.progress_completed == 1
            assert (
                reopened.read_checkpoint(before.job_id, **TENANT_AUTH)
                == claim.checkpoint_bytes
            )
            evidence = _evidence(reopened, before.job_id, **TENANT_AUTH)
            assert evidence["pending_ordinals"] == [ordinal]
            assert evidence["execution_budget"]["reserved_attempts"] == ordinal
            assert evidence["records"][:2] == isolated_prefix[3]["records"]
            replacement = _claim(reopened)
            assert replacement.checkpoint_bytes == claim.checkpoint_bytes
            assert replacement.job.attempt > claim.job.attempt
            with pytest.raises(JobServiceError, match="reservation_lease_mismatch"):
                reopened.record_rc_invocation_outcome(
                    before.job_id,
                    **_credentials(replacement),
                    ordinal=ordinal,
                    outcome=evidence["records"][0]["outcome"],
                )
            assert _evidence(reopened, before.job_id, **TENANT_AUTH)[
                "pending_ordinals"
            ] == [ordinal]
            (tmp_path / "parent-death-proof.json").write_bytes(
                _bytes(
                    {
                        "phase": phase,
                        "parent_returncode": parent.returncode,
                        "child_pid": child_pid,
                        "child_returncode": child_returncode,
                        "direct_child_stopped_by_parent_death": True,
                        "test_guardian_reaped_adopted_child": True,
                        "pending_ordinals": evidence["pending_ordinals"],
                        "prefix_exact_after_reopen": True,
                        "arbitrary_descendant_containment_claimed": False,
                    }
                )
            )
        finally:
            if parent is not None and parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
            if not child_reaped:
                if child_pid is None and marker.exists():
                    child_pid = int(marker.read_text())
                if child_pid is not None:
                    _cleanup_owned_child(child_pid)


def test_policy_worker_unsupported_platform_reserves_and_launches_nothing(
    tmp_path, monkeypatch
):
    request = _request()
    request["execution_config"]["phase_execution_policy"] = deepcopy(POLICY)
    service = _service(tmp_path / "store")
    job = _submit(service, request)
    claim = _claim(service)
    monkeypatch.setattr(worker.sys, "platform", "unsupported-test-platform")
    monkeypatch.setattr(
        supervisor, "run_rc_fiber_phase", lambda **kw: pytest.fail("unsupported launch")
    )
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError, match="phase_platform_unsupported"
    ):
        _run(service, claim)
    failed = service.get_job(job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.result is failed.checkpoint is None
    evidence = _evidence(service, job.job_id, **TENANT_AUTH)
    assert evidence["execution_budget"]["reserved_attempts"] == 0
    assert evidence["pending_ordinals"] == [] and evidence["records"] == []


@pytest.mark.parametrize("handler", [signal.SIG_IGN, lambda *_: None])
def test_nondefault_sigchld_rejected_before_reservation(tmp_path, monkeypatch, handler):
    request = _request()
    request["execution_config"]["phase_execution_policy"] = deepcopy(POLICY)
    service = _service(tmp_path / "store")
    job = _submit(service, request)
    monkeypatch.setattr(worker.signal, "getsignal", lambda which: handler)
    monkeypatch.setattr(
        supervisor, "run_rc_fiber_phase", lambda **kw: pytest.fail("unsupported launch")
    )
    with pytest.raises(
        worker.RCFiberDirectControlWorkerError, match="phase_reaping_unsupported"
    ):
        _run(service, _claim(service))
    failed = service.get_job(job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.result is failed.checkpoint is None
    evidence = _evidence(service, job.job_id, **TENANT_AUTH)
    assert evidence["execution_budget"]["reserved_attempts"] == 0
    assert evidence["pending_ordinals"] == [] and evidence["records"] == []


@pytest.mark.parametrize("phase,ordinal", [("analysis", 3), ("verification", 4)])
@pytest.mark.parametrize("raised", [False, True, "integer_contract", "integer_claim"])
def test_malformed_business_reply_stays_unknown_and_phase_specific(
    isolated_prefix, tmp_path, monkeypatch, phase, ordinal, raised
):
    service, claim = _prefix_copy(isolated_prefix, tmp_path)
    original = supervisor.run_rc_fiber_phase

    def malformed(**kwargs):
        if kwargs["phase"] != phase:
            return original(**kwargs)
        # Deliberately bypass validated IPC to test the worker reconstruction
        # boundary. This forged reply is not a real child measurement.
        artifact_error_bytes = b"{}" if raised else None
        if type(raised) is str:
            report = worker.api.BoundedRCFiberDirectControlArtifactError(
                "synthetic export failure",
                {"model": {}, "request": {}, "status": "ready", "metrics": {}},
            ).to_dict()
            if raised == "integer_contract":
                report["contract_pass"] = 0
            else:
                report["claims"]["release_approved"] = 0
            artifact_error_bytes = supervisor._json(report)
        return supervisor.RCFiberPhaseReply(
            status="raised" if raised else "returned",
            _timing_bytes=b'{"wall_ns":1,"process_cpu_ns":1}',
            raw_result=b"{}" if phase == "analysis" and not raised else None,
            _verification_bytes=b"{}"
            if phase == "verification" and not raised
            else None,
            error_type="BoundedRCFiberDirectControlArtifactError" if raised else None,
            _artifact_error_bytes=artifact_error_bytes,
            native_checkpoint=None,
            _supervisor_bytes=b"{}",
        )

    monkeypatch.setattr(supervisor, "run_rc_fiber_phase", malformed)
    with pytest.raises(worker.RCFiberDirectControlWorkerError) as caught:
        _run(service, claim)
    assert caught.value.code == f"rc_fiber_worker_{phase}_transport_invalid"
    failed = service.get_job(claim.job.job_id, **TENANT_AUTH)
    assert failed.status == "failed" and failed.checkpoint == claim.job.checkpoint
    assert failed.result is failed.evidence is None
    assert (
        service.read_checkpoint(failed.job_id, **TENANT_AUTH) == claim.checkpoint_bytes
    )
    evidence = _evidence(service, failed.job_id, **TENANT_AUTH)
    assert evidence["pending_ordinals"] == [ordinal]
    assert evidence["execution_budget"]["reserved_attempts"] == ordinal
    assert [r["ordinal"] for r in evidence["records"]] == list(range(1, ordinal))
    assert evidence["records"][:2] == isolated_prefix[3]["records"]
