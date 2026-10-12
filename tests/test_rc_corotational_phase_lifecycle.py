"""Real controlled children test v7 transport, deadlines, cleanup and guard custody.

These subprocesses perform no numerical calculation. Process groups and the
direct child's inherited guard are bounded Linux lifecycle evidence, without
claims of arbitrary descendant containment, resource quotas or physics.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time

import pytest

from structural_analysis.execution import rc_corotational_phase_supervisor as supervisor
from structural_analysis.execution import rc_fiber_phase_supervisor as common
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.rc_corotational_job_request import (
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_phase_policy import (
    RCCorotationalPhasePolicy,
)
from tests.test_rc_corotational_job_contract import isolated_request


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="authored Linux phase profile"
)


@pytest.fixture(autouse=True)
def no_parent_numerical_execution_or_source_identity(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("controlled-child lifecycle test invoked a numerical API")

    for name in (
        "analyze_rc_corotational_control",
        "validate_rc_corotational_control_artifacts",
        "solve_stateful_corotational_fiber_frame2d_load_step",
        "run_corotational_control_subdivision",
        "_source_identity",
    ):
        monkeypatch.setattr(
            f"structural_analysis.api.rc_corotational_control.{name}", forbidden
        )


def _run(policy, *, phase="analysis", lease_check=lambda: None, authority_fd=None):
    request = isolated_request()
    request["execution_config"]["phase_execution_policy"] = policy.to_dict()
    return supervisor.run_rc_corotational_phase(
        phase=phase,
        request_bytes=rc_corotational_job_canonical_bytes(request),
        completed_before=0,
        completed_after=2,
        restart=None,
        result=None if phase == "analysis" else b"synthetic-original-result",
        checkpoint=None if phase == "analysis" else b"synthetic-original-checkpoint",
        policy=policy,
        lease_check=lease_check,
        authority_fd=authority_fd,
    )


def _script(tmp_path, monkeypatch, body, *, transport=True):
    script = tmp_path / "controlled-child.py"
    prefix = "import os,sys,time,signal,runpy,json\nfrom pathlib import Path\n"
    prefix += f"boot=runpy.run_path({str(common._BOOTSTRAP_PATH)!r})\n"
    prefix += "boot['_arm_parent_death_signal'](int(sys.argv[1]))\n"
    prefix += "solver_imported_before_arming=any(k.startswith(('numpy','structural_analysis')) for k in sys.modules)\n"
    if transport:
        for root in reversed(common._dependency_paths()):
            prefix += f"sys.path.insert(0,{root!r})\n"
        prefix += f"sys.path.insert(0,{str(supervisor._SOURCE_ROOT)!r})\n"
        prefix += f"ns=runpy.run_path({str(Path(supervisor.__file__).resolve())!r},run_name='controlled_transport')\n"
        # All replies below are authored transport records, not child API calls.
        prefix += "def forbidden(*args,**kwargs): raise RuntimeError('controlled child cannot execute numerical API')\n"
        prefix += "ns['_execute_child']=forbidden\n"
    script.write_text(prefix + body)
    monkeypatch.setattr(
        supervisor,
        "_child_argv",
        lambda parent: [sys.executable, "-I", str(script), str(parent)],
    )


def _blocking_script(
    tmp_path, monkeypatch, *, ignore_term=False, descendant=False, fd=None
):
    marker = tmp_path / "ready.json"
    body = "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n" if ignore_term else ""
    body += "descendant=None\n"
    if descendant:
        body += "import subprocess\n"
        body += "child=subprocess.Popen([sys.executable,'-I','-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])\n"
        body += "descendant=child.pid\n"
    body += "guard_inode=None\n"
    if fd is not None:
        body += f"guard_inode=os.fstat({fd}).st_ino\n"
    body += f"Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid(),'descendant':descendant,'guard_inode':guard_inode,'armed':True,'solver_imported_before_arming':solver_imported_before_arming}}))\n"
    body += "while True: time.sleep(0.01)\n"
    _script(tmp_path, monkeypatch, body, transport=False)
    return marker


def _reply_code(*, phase="analysis", body="", error_type=None, work=None):
    output = (
        b"synthetic-result" if phase == "analysis" and error_type is None else None,
        b"synthetic-checkpoint" if phase == "analysis" and error_type is None else None,
        common._json({"synthetic_report": True})
        if phase == "verification" and error_type is None
        else None,
        common._json(work) if work is not None else None,
    )
    return (
        "metadata,segments=ns['_read_input_frame']()\n"
        "w0=time.perf_counter_ns();c0=time.process_time_ns()\n"
        + body
        + "\nc1=time.process_time_ns();w1=time.perf_counter_ns()\n"
        + f"output={output!r}\n"
        + "reply={'schema_version':ns['_SCHEMA'],'identity':metadata['identity'],'policy':metadata['policy'],"
        + f"'status':{'raised' if error_type else 'returned'!r},'error_type':{error_type!r},"
        + "'timing':{'wall_ns':w1-w0,'process_cpu_ns':c1-c0},"
        + "'measurement':{'wall_started_ns':w0,'wall_finished_ns':w1,'cpu_started_ns':c0,'cpu_finished_ns':c1},"
        + "'segment_hashes':[ns['common']._hash(v) for v in output]}\n"
    )


def _write_reply_code(**kwargs):
    return _reply_code(**kwargs) + (
        "for part in ns['_frame_parts'](reply,output): sys.stdout.buffer.write(part)\n"
        "sys.stdout.buffer.flush()\n"
    )


def _running(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return stat[stat.rfind(")") + 2 :].split()[0] != "Z"


def _assert_reaped(pid):
    assert not _running(pid)
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


def _cleanup_marker(marker):
    if not marker.exists():
        return
    pid = json.loads(marker.read_text())["pid"]
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return  # Numeric PID/PGID ownership has ended; do not signal a reused PID.
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    until = time.monotonic() + 2
    while time.monotonic() < until:
        try:
            waited, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if waited:
            return
        time.sleep(0.01)


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_real_blocking_v7_child_timeout_reaps_direct_child(
    tmp_path, monkeypatch, phase
):
    marker = _blocking_script(tmp_path, monkeypatch)
    try:
        with pytest.raises(common.RCFiberPhaseError) as captured:
            _run(RCCorotationalPhasePolicy(1_000, 1_000, 80), phase=phase)
        error = captured.value
        data = json.loads(marker.read_text())
        assert error.code == f"rc_corotational_worker_{phase}_timeout"
        assert data["armed"] and not data["solver_imported_before_arming"]
        assert error.cleanup["pid"] == data["pid"]
        assert error.cleanup["direct_child_reaped"]
        assert error.cleanup["returncode"] == -signal.SIGTERM
        _assert_reaped(data["pid"])
    finally:
        _cleanup_marker(marker)


def test_real_term_ignoring_v7_child_is_killed_and_group_descendant_stops(
    tmp_path, monkeypatch
):
    marker = _blocking_script(tmp_path, monkeypatch, ignore_term=True, descendant=True)
    try:
        with pytest.raises(common.RCFiberPhaseError) as captured:
            _run(RCCorotationalPhasePolicy(1_000, 1_000, 80))
        error = captured.value
        data = json.loads(marker.read_text())
        assert error.code == "rc_corotational_worker_analysis_timeout"
        assert error.cleanup["signals_sent"] == ["SIGTERM", "SIGKILL"]
        assert error.cleanup["returncode"] == -signal.SIGKILL
        assert error.cleanup["cleanup_wall_ns"] >= 80_000_000
        _assert_reaped(data["pid"])
        until = time.monotonic() + 2
        while _running(data["descendant"]) and time.monotonic() < until:
            time.sleep(0.01)
        assert not _running(data["descendant"])
        # This pytest process owns only its direct child, not the orphan's reap.
    finally:
        _cleanup_marker(marker)


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_v7_lease_lost_keeps_actual_cleanup_and_original_cause(
    tmp_path, monkeypatch, phase
):
    marker = _blocking_script(tmp_path, monkeypatch, ignore_term=True)
    expected = JobServiceError("lease_token_invalid", "/lease", "controlled lease loss")

    def lease():
        if marker.exists():
            raise expected

    try:
        with pytest.raises(common.RCFiberPhaseError) as captured:
            _run(
                RCCorotationalPhasePolicy(5_000, 5_000, 50),
                phase=phase,
                lease_check=lease,
            )
        error = captured.value
        data = json.loads(marker.read_text())
        assert error.code == f"rc_corotational_worker_{phase}_lease_lost"
        assert error.cleanup["pid"] == data["pid"]
        assert error.cleanup["direct_child_reaped"]
        assert error.cleanup["signals_sent"] == ["SIGTERM", "SIGKILL"]
        assert error.cleanup["returncode"] == -signal.SIGKILL
        assert error.__cause__.__cause__ is expected
        _assert_reaped(data["pid"])
    finally:
        _cleanup_marker(marker)


@pytest.mark.parametrize(
    "kind", ("old_magic", "oversized_result", "truncated", "hash_mismatch", "trailing")
)
def test_real_corotational_ipc_corruption_is_unaccounted_and_reaped(
    tmp_path, monkeypatch, kind
):
    body = "metadata,segments=ns['_read_input_frame']()\n"
    if kind == "old_magic":
        body += "sys.stdout.buffer.write(ns['common']._HEADER.pack(ns['common']._MAGIC,1,1,0,0,0));sys.stdout.buffer.flush()\n"
    elif kind == "oversized_result":
        body += "sys.stdout.buffer.write(ns['common']._HEADER.pack(ns['_MAGIC'],1,ns['_RESULT_MAX_BYTES']+1,0,0,0));sys.stdout.buffer.flush()\n"
    elif kind == "truncated":
        body += "sys.stdout.buffer.write(b'SA-RC-CORO');sys.stdout.buffer.flush()\n"
    else:
        body = _reply_code()
        if kind == "hash_mismatch":
            body += "reply['segment_hashes'][0]=ns['common']._hash(b'different')\n"
        body += "for part in ns['_frame_parts'](reply,output): sys.stdout.buffer.write(part)\n"
        if kind == "trailing":
            body += "sys.stdout.buffer.write(b'trailing')\n"
        body += "sys.stdout.buffer.flush()\n"
    _script(tmp_path, monkeypatch, body)
    with pytest.raises(common.RCFiberPhaseError) as captured:
        _run(RCCorotationalPhasePolicy(5_000, 5_000, 80))
    assert captured.value.code == "rc_corotational_worker_analysis_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]
    _assert_reaped(captured.value.cleanup["pid"])


@pytest.mark.parametrize(
    "mutation",
    (
        "reply['schema_version']=ns['common']._SCHEMA",
        "reply['policy']['analysis_timeout_ms']+=1",
        "reply['identity']['planned_after']+=1",
        "reply['identity']['chunk_request_hash']='sha256:'+('a'*64)",
        "reply['timing']['process_cpu_ns']=False",
        "reply['measurement']['wall_started_ns']=0",
    ),
)
def test_real_v7_reply_policy_identity_or_clock_drift_is_rejected(
    tmp_path, monkeypatch, mutation
):
    code = _reply_code() + mutation + "\n"
    code += "for part in ns['_frame_parts'](reply,output): sys.stdout.buffer.write(part)\nsys.stdout.buffer.flush()\n"
    _script(tmp_path, monkeypatch, code)
    with pytest.raises(common.RCFiberPhaseError) as captured:
        _run(RCCorotationalPhasePolicy(5_000, 5_000, 80))
    assert captured.value.code == "rc_corotational_worker_analysis_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]
    _assert_reaped(captured.value.cleanup["pid"])


def test_real_complete_v7_reply_cannot_override_late_child_exit(tmp_path, monkeypatch):
    marker = tmp_path / "reply-sent.json"
    code = _write_reply_code()
    code += f"Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid()}}))\n"
    code += (
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\nwhile True: time.sleep(0.01)\n"
    )
    _script(tmp_path, monkeypatch, code)
    try:
        with pytest.raises(common.RCFiberPhaseError) as captured:
            _run(RCCorotationalPhasePolicy(1_500, 1_500, 50))
        assert marker.exists()  # Complete, measured IPC preceded the actual cutoff.
        assert captured.value.code == "rc_corotational_worker_analysis_timeout"
        assert captured.value.cleanup["returncode"] == -signal.SIGKILL
        _assert_reaped(json.loads(marker.read_text())["pid"])
    finally:
        _cleanup_marker(marker)


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_controlled_v7_reply_has_measured_child_clocks_and_complete_reaping(
    tmp_path, monkeypatch, phase
):
    _script(
        tmp_path, monkeypatch, _write_reply_code(phase=phase, body="time.sleep(0.01)")
    )
    reply = _run(RCCorotationalPhasePolicy(5_000, 5_000, 80), phase=phase)
    assert reply.status == "returned"
    assert type(reply.timing["wall_ns"]) is int and reply.timing["wall_ns"] > 0
    assert (
        type(reply.timing["process_cpu_ns"]) is int
        and reply.timing["process_cpu_ns"] > 0
    )
    assert reply.supervisor_timing["wall_ns"] >= reply.timing["wall_ns"]
    assert reply.supervisor_timing["direct_child_reaped"]
    assert reply.supervisor_timing["child_returncode"] == 0
    if phase == "analysis":
        assert reply.raw_result == b"synthetic-result"
        assert reply.native_checkpoint == b"synthetic-checkpoint"
    else:
        assert reply.verification_report == {"synthetic_report": True}
    _assert_reaped(reply.supervisor_timing["child_pid"])


@pytest.mark.parametrize("typed_work", (False, True))
def test_measured_v7_raised_child_reply_preserves_partial_work_custody(
    tmp_path, monkeypatch, typed_work
):
    work = (
        {
            "preload_solver_calls": 1,
            "restart_replay_solver_calls": 0,
            "control_solver_calls": 3,
            "unavailable_execution_work": True,
        }
        if typed_work
        else None
    )
    error_type = "RCCorotationalControlExecutionError" if typed_work else "ValueError"
    _script(tmp_path, monkeypatch, _write_reply_code(error_type=error_type, work=work))
    reply = _run(RCCorotationalPhasePolicy(5_000, 5_000, 80))
    assert reply.status == "raised" and reply.error_type == error_type
    assert reply.raw_result is None and reply.native_checkpoint is None
    assert reply.artifact_error_report == work
    assert type(reply.timing["process_cpu_ns"]) is int
    assert reply.supervisor_timing["child_returncode"] == 0
    _assert_reaped(reply.supervisor_timing["child_pid"])


def test_real_inherited_guard_remains_locked_until_v7_child_is_reaped(
    tmp_path, monkeypatch
):
    lock_path = tmp_path / "authored-guard.lock"
    guard = lock_path.open("a+b")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    inode = os.fstat(guard.fileno()).st_ino
    fd = guard.fileno()
    marker = _blocking_script(tmp_path, monkeypatch, ignore_term=True, fd=fd)
    inherited_lock_observed = []

    def lease():
        if marker.exists() and not guard.closed:
            assert json.loads(marker.read_text())["guard_inode"] == inode
            guard.close()  # The child must retain its inherited open-file description.
            with lock_path.open("a+b") as contender:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            inherited_lock_observed.append(True)

    try:
        with pytest.raises(common.RCFiberPhaseError) as captured:
            _run(
                RCCorotationalPhasePolicy(1_000, 1_000, 50),
                lease_check=lease,
                authority_fd=fd,
            )
        assert captured.value.code == "rc_corotational_worker_analysis_timeout"
        assert inherited_lock_observed == [True]
        assert captured.value.cleanup["direct_child_reaped"]
        _assert_reaped(json.loads(marker.read_text())["pid"])
        with lock_path.open("a+b") as contender:
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(contender, fcntl.LOCK_UN)
    finally:
        if not guard.closed:
            guard.close()
        _cleanup_marker(marker)
