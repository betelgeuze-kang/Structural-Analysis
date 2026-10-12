"""Real process/pipe/death/reaping contracts, plus one tiny real source API case.

Synthetic children exercise transport and lifecycle only. They do not attest a
runtime, simulate numerical nonconvergence, measure acceleration, or qualify
arbitrary descendant containment, memory/disk quotas or physical accuracy.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import errno
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.execution import rc_fiber_phase_supervisor as supervisor
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy
from tests.test_rc_fiber_durable_worker import _bytes, _request


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="authored Linux phase profile"
)


def _request_bytes(policy, *, padding=0):
    request = _request()
    request["execution_config"]["phase_execution_policy"] = policy.to_dict()
    if padding:
        # Transport-only child does not compile this deliberately annotated model.
        request["model"]["synthetic_transport_padding"] = "p" * padding
    return _bytes(request)


def _run(policy, *, phase="analysis", lease_check=lambda: None, padding=0):
    return supervisor.run_rc_fiber_phase(
        phase=phase,
        request_bytes=_request_bytes(policy, padding=padding),
        completed_before=0,
        completed_after=1,
        restart=None,
        policy=policy,
        lease_check=lease_check,
        result=None if phase == "analysis" else b"synthetic-original-analysis",
        checkpoint=None if phase == "analysis" else b"synthetic-original-native",
    )


def _script(tmp_path, monkeypatch, body, *, setup_transport=True):
    script = tmp_path / "child.py"
    prefix = """import os,sys,time,signal,runpy,json
from pathlib import Path
"""
    prefix += f"boot=runpy.run_path({str(supervisor._BOOTSTRAP_PATH)!r})\n"
    prefix += "boot['_arm_parent_death_signal'](int(sys.argv[1]))\n"
    if setup_transport:
        prefix += f"ns=runpy.run_path({str(Path(supervisor.__file__).resolve())!r},run_name='synthetic_transport')\n"
    script.write_text(prefix + body)
    monkeypatch.setattr(
        supervisor,
        "_child_argv",
        lambda parent: [sys.executable, "-I", str(script), str(parent)],
    )
    return script


def _blocking_script(tmp_path, monkeypatch, *, ignore_term=False, descendant=False):
    marker = tmp_path / "ready.json"
    body = "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n" if ignore_term else ""
    body += "descendant=None\n"
    if descendant:
        body += "import subprocess\n"
        body += "child=subprocess.Popen([sys.executable,'-I','-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])\n"
        body += "descendant=child.pid\n"
    body += f"Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid(),'descendant':descendant,'armed':True}}))\n"
    body += "while True: time.sleep(0.01)\n"
    _script(tmp_path, monkeypatch, body, setup_transport=False)
    return marker


def _reply_code(
    body="",
    *,
    phase="analysis",
    raw=b"synthetic-result",
    native=None,
    report=None,
    error_type=None,
    artifact_error=None,
):
    # Source-clocks are actual readings in this synthetic child; no numerical
    # correctness is implied by a complete transport reply.
    start = "metadata,segments=ns['_read_input_frame']()\nw0=time.perf_counter_ns();c0=time.process_time_ns()\n"
    start += body + "\nc1=time.process_time_ns();w1=time.perf_counter_ns()\n"
    start += "reply={'schema_version':ns['_SCHEMA'],'identity':metadata['identity'],'status':"
    start += repr("raised" if error_type else "returned")
    start += f",'error_type':{error_type!r},'timing':{{'wall_ns':w1-w0,'process_cpu_ns':c1-c0}},'measurement':{{'wall_started_ns':w0,'wall_finished_ns':w1,'cpu_started_ns':c0,'cpu_finished_ns':c1}}}}\n"
    values = (
        raw if phase == "analysis" and not error_type else None,
        native if phase == "analysis" and not error_type else None,
        supervisor._json(report)
        if phase == "verification" and not error_type
        else None,
        supervisor._json(artifact_error) if artifact_error is not None else None,
    )
    start += f"output={values!r}\n"
    return start


def _write_reply_code(**kwargs):
    return (
        _reply_code(**kwargs) + "ns['_write_frame'](sys.stdout.buffer,reply,output)\n"
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
    if marker.exists():
        data = json.loads(marker.read_text())
        try:
            os.waitid(os.P_PID, data["pid"], os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return  # Never signal a numeric PID/PGID after it has been reaped.
        try:
            os.killpg(data["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass
        until = time.monotonic() + 2
        while time.monotonic() < until:
            try:
                waited, _status = os.waitpid(data["pid"], os.WNOHANG)
            except ChildProcessError:
                return
            if waited:
                return
            time.sleep(0.01)


@pytest.fixture(scope="module")
def real_phase_artifacts():
    policy = RCFiberPhasePolicy(20_000, 20_000, 250)
    request = _request_bytes(policy)
    result = supervisor.run_rc_fiber_phase(
        phase="analysis",
        request_bytes=request,
        completed_before=0,
        completed_after=1,
        restart=None,
        policy=policy,
        lease_check=lambda: None,
    )
    verification = supervisor.run_rc_fiber_phase(
        phase="verification",
        request_bytes=request,
        completed_before=0,
        completed_after=1,
        restart=None,
        result=result.raw_result,
        checkpoint=result.native_checkpoint,
        policy=policy,
        lease_check=lambda: None,
    )
    return policy, request, result, verification


def test_real_api_exact_artifacts_distinct_children_and_measured_scopes(
    real_phase_artifacts,
):
    policy, request, result, verified = real_phase_artifacts
    assert result.status == verified.status == "returned"
    original = api.BoundedRCFiberDirectControlResult(
        result.raw_result, result.native_checkpoint
    )
    assert original.contract_pass
    assert original.checkpoint_artifact_bytes() == result.native_checkpoint
    assert len(result.raw_result) > 64 * 1024  # Real output exceeds a pipe buffer.
    assert verified.verification_report["contract_pass"]
    assert verified.verification_report["fresh_source_execution_invoked"]
    assert verified.verification_report["verified_result_hash"] == original.result_hash
    assert (
        result.supervisor_timing["child_pid"] != verified.supervisor_timing["child_pid"]
    )
    for value in (result, verified):
        assert value.timing["wall_ns"] > 0 and value.timing["process_cpu_ns"] > 0
        assert value.supervisor_timing["wall_ns"] >= value.timing["wall_ns"]
        assert value.supervisor_timing["direct_child_reaped"]
        assert value.supervisor_timing["child_returncode"] == 0
        _assert_reaped(value.supervisor_timing["child_pid"])
    assert (
        json.loads(request)["execution_config"]["phase_execution_policy"]
        == policy.to_dict()
    )
    # Frozen reply and defensive report/timing copies do not expose mutable bytes.
    with pytest.raises(FrozenInstanceError):
        result.status = "raised"
    result.timing["wall_ns"] = -1
    assert result.timing["wall_ns"] > 0
    verified.verification_report["contract_pass"] = False
    assert verified.verification_report["contract_pass"]


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_real_blocking_child_cutoff_is_reaped_and_has_no_measured_reply(
    tmp_path, monkeypatch, phase
):
    marker = _blocking_script(tmp_path, monkeypatch)
    policy = RCFiberPhasePolicy(1000, 1000, 100)
    try:
        with pytest.raises(supervisor.RCFiberPhaseError) as captured:
            _run(policy, phase=phase)
        error = captured.value
        assert error.code == f"rc_fiber_worker_{phase}_timeout"
        data = json.loads(marker.read_text())
        assert data["armed"] and error.cleanup["pid"] == data["pid"]
        assert error.cleanup["direct_child_reaped"]
        assert error.cleanup["returncode"] == -signal.SIGTERM
        _assert_reaped(data["pid"])
    finally:
        _cleanup_marker(marker)


def test_real_term_ignoring_child_requires_kill_and_group_descendant_stops(
    tmp_path, monkeypatch
):
    marker = _blocking_script(tmp_path, monkeypatch, ignore_term=True, descendant=True)
    try:
        with pytest.raises(supervisor.RCFiberPhaseError) as captured:
            _run(RCFiberPhasePolicy(1000, 1000, 80))
        error = captured.value
        data = json.loads(marker.read_text())
        assert error.code == "rc_fiber_worker_analysis_timeout"
        assert error.cleanup["signals_sent"] == ["SIGTERM", "SIGKILL"]
        assert error.cleanup["returncode"] == -signal.SIGKILL
        assert error.cleanup["cleanup_wall_ns"] >= 80_000_000
        _assert_reaped(data["pid"])
        until = time.monotonic() + 2
        while _running(data["descendant"]) and time.monotonic() < until:
            time.sleep(0.01)
        assert not _running(data["descendant"])
        # Only direct-child waitpid is ours; no claim that this parent reaped an orphan.
    finally:
        _cleanup_marker(marker)


def test_lease_failure_kills_real_child_then_propagates_exact_authority_error(
    tmp_path, monkeypatch
):
    marker = _blocking_script(tmp_path, monkeypatch, ignore_term=True)
    expected = JobServiceError(
        "lease_token_invalid", "/lease", "synthetic lease takeover"
    )
    seen = []

    def lease():
        seen.append(time.perf_counter_ns())
        if marker.exists():
            raise expected

    try:
        with pytest.raises(JobServiceError) as captured:
            _run(RCFiberPhasePolicy(5000, 5000, 50), lease_check=lease)
        assert captured.value is expected
        assert len(seen) >= 2
        _assert_reaped(json.loads(marker.read_text())["pid"])
    finally:
        _cleanup_marker(marker)


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_incremental_input_large_output_and_stderr_drain_before_wait(
    tmp_path, monkeypatch, phase
):
    body = "os.write(sys.stderr.fileno(),b'e'*(4*65536))\n"
    if phase == "analysis":
        code = _write_reply_code(body=body, raw=b"r" * (4 * 65536), native=b"n" * 1024)
    else:
        code = _write_reply_code(
            body=body,
            phase=phase,
            report={"synthetic_report": True, "padding": "r" * (4 * 65536)},
        )
    _script(tmp_path, monkeypatch, code)
    reply = _run(RCFiberPhasePolicy(5000, 5000, 100), phase=phase, padding=4 * 65536)
    assert reply.status == "returned"
    assert reply.supervisor_timing["stderr_byte_count"] == 4 * 65536
    assert reply.supervisor_timing["stderr_retained_bytes"] == 65536
    assert reply.supervisor_timing["stderr_truncated"]
    if phase == "analysis":
        assert (
            reply.raw_result == b"r" * (4 * 65536)
            and reply.native_checkpoint == b"n" * 1024
        )
    else:
        assert reply.verification_report["padding"] == "r" * (4 * 65536)
    _assert_reaped(reply.supervisor_timing["child_pid"])


@pytest.mark.parametrize(
    "kind",
    (
        "oversized_result",
        "oversized_metadata",
        "truncated",
        "hash_mismatch",
        "trailing",
    ),
)
def test_real_invalid_frames_rejected_without_accounted_reply(
    tmp_path, monkeypatch, kind
):
    body = "metadata,segments=ns['_read_input_frame']()\n"
    if kind == "oversized_result":
        body += "sys.stdout.buffer.write(ns['_HEADER'].pack(ns['_MAGIC'],1,ns['_RESULT_MAX_BYTES']+1,0,0,0));sys.stdout.buffer.flush()\n"
    elif kind == "oversized_metadata":
        body += "sys.stdout.buffer.write(ns['_HEADER'].pack(ns['_MAGIC'],ns['_METADATA_MAX_BYTES']+1,0,0,0,0));sys.stdout.buffer.flush()\n"
    elif kind == "truncated":
        body += "sys.stdout.buffer.write(b'SA-RC');sys.stdout.buffer.flush()\n"
    else:
        body = _reply_code()
        if kind == "hash_mismatch":
            body += (
                "reply['segment_hashes']=[ns['_hash'](b'different'),None,None,None]\n"
            )
            body += "for part in ns['_frame_parts'](reply,output): sys.stdout.buffer.write(part)\nsys.stdout.buffer.flush()\n"
        else:
            body += "ns['_write_frame'](sys.stdout.buffer,reply,output)\nsys.stdout.buffer.write(b'trailing');sys.stdout.buffer.flush()\n"
    _script(tmp_path, monkeypatch, body)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]
    _assert_reaped(captured.value.cleanup["pid"])


@pytest.mark.parametrize(
    "field",
    (
        "phase",
        "job_request_hash",
        "chunk_request_hash",
        "completed_before",
        "completed_after",
        "restart_input_sha256",
        "analysis_result_sha256",
        "analysis_checkpoint_sha256",
        "source_revision",
        "source_hashes",
    ),
)
def test_real_source_range_and_original_input_binding_mismatch_rejected(
    tmp_path, monkeypatch, field
):
    body = _reply_code()
    body += f"reply['identity'][{field!r}]={'{}' if field == 'source_hashes' else repr('different-binding')}\n"
    body += "ns['_write_frame'](sys.stdout.buffer,reply,output)\n"
    _script(tmp_path, monkeypatch, body)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]
    _assert_reaped(captured.value.cleanup["pid"])


@pytest.mark.parametrize(
    "mutation",
    (
        "reply['timing']['wall_ns']=-1",
        "reply['timing']['process_cpu_ns']=False",
        "reply['timing']['extra']=0",
        "reply['timing']['wall_ns']+=1",
        "reply['measurement']['wall_started_ns']=0",
        "reply['measurement']['wall_finished_ns']=2**62",
        "reply['measurement']['cpu_finished_ns']=reply['measurement']['cpu_started_ns']-1",
        "reply['measurement']['cpu_finished_ns']=2**62;reply['timing']['process_cpu_ns']=2**62-reply['measurement']['cpu_started_ns']",
    ),
)
def test_real_incomplete_or_impossible_source_timing_rejected(
    tmp_path, monkeypatch, mutation
):
    body = (
        _reply_code()
        + mutation
        + "\nns['_write_frame'](sys.stdout.buffer,reply,output)\n"
    )
    _script(tmp_path, monkeypatch, body)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]


def test_complete_reply_does_not_override_late_child_exit_deadline(
    tmp_path, monkeypatch
):
    marker = tmp_path / "reply-sent.json"
    code = _write_reply_code()
    code += f"Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid()}}))\n"
    code += (
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\nwhile True: time.sleep(0.01)\n"
    )
    _script(tmp_path, monkeypatch, code)
    try:
        with pytest.raises(supervisor.RCFiberPhaseError) as captured:
            _run(RCFiberPhasePolicy(1000, 1000, 50))
        assert marker.exists()  # Actual complete frame preceded the cutoff.
        assert captured.value.code == "rc_fiber_worker_analysis_timeout"
        assert captured.value.cleanup["returncode"] == -signal.SIGKILL
        _assert_reaped(json.loads(marker.read_text())["pid"])
    finally:
        _cleanup_marker(marker)


def test_cleanup_signal_failure_remains_explicit_even_if_child_is_later_reaped(
    tmp_path, monkeypatch
):
    marker = _blocking_script(tmp_path, monkeypatch, ignore_term=True)
    original = supervisor._signal_group

    def denied_term(process, sig, diagnostics):
        if sig == signal.SIGTERM:
            diagnostics["signal_errors"].append(
                {"signal": "SIGTERM", "errno": errno.EPERM}
            )
        else:
            original(process, sig, diagnostics)

    monkeypatch.setattr(supervisor, "_signal_group", denied_term)
    try:
        with pytest.raises(supervisor.RCFiberPhaseError) as captured:
            _run(RCFiberPhasePolicy(1000, 1000, 50))
        assert captured.value.code == "rc_fiber_worker_analysis_cleanup_failed"
        assert captured.value.cleanup["direct_child_reaped"]
        assert captured.value.cleanup["signal_errors"] == [
            {"signal": "SIGTERM", "errno": errno.EPERM}
        ]
        _assert_reaped(json.loads(marker.read_text())["pid"])
    finally:
        _cleanup_marker(marker)


@pytest.mark.parametrize("coretype", ("Haswell", "Nehalem"))
def test_child_environment_has_no_auth_or_loader_environment(
    tmp_path, monkeypatch, coretype
):
    monkeypatch.setenv("STRUCTURAL_SERVICE_TOKEN", "synthetic-token-not-forwarded")
    monkeypatch.setenv("LD_PRELOAD", "/synthetic-invalid-loader.so")
    monkeypatch.setenv("PYTHONPATH", "/synthetic-injected-import")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")
    monkeypatch.setenv("OPENBLAS_CORETYPE", coretype)
    body = _reply_code(phase="verification", report={"placeholder": True})
    body += "output=(None,None,ns['_json']({'environment':dict(os.environ)}),None)\n"
    body += "ns['_write_frame'](sys.stdout.buffer,reply,output)\n"
    _script(tmp_path, monkeypatch, body)
    reply = _run(RCFiberPhasePolicy(5000, 5000, 100), phase="verification")
    environment = reply.verification_report["environment"]
    assert "STRUCTURAL_SERVICE_TOKEN" not in environment
    assert "LD_PRELOAD" not in environment and "PYTHONPATH" not in environment
    assert environment["OPENBLAS_NUM_THREADS"] == "2"
    assert environment["OPENBLAS_CORETYPE"] == coretype
    _assert_reaped(reply.supervisor_timing["child_pid"])


@pytest.mark.parametrize(
    "coretype", ("", "Haswell ", "Haswell\n", "../Haswell", "Háswell", "H" * 65)
)
def test_child_environment_drops_unbounded_dispatch_values(monkeypatch, coretype):
    monkeypatch.setenv("OPENBLAS_CORETYPE", coretype)
    assert "OPENBLAS_CORETYPE" not in supervisor._child_environment()


@pytest.mark.parametrize(
    "error_type", ("ValueError", "BoundedRCFiberDirectControlArtifactError")
)
def test_measured_child_exception_retains_structured_type_and_original_report(
    tmp_path, monkeypatch, error_type
):
    # This is an explicit API failure seam inside a real fresh child. The typed
    # ArtifactError constructor/serializer and transport are real, its metrics synthetic.
    prefix = (
        "\n".join(
            f"sys.path.insert(0,{value!r})"
            for value in reversed(supervisor._dependency_paths())
        )
        + "\n"
    )
    prefix += f"sys.path.insert(0,{str(supervisor._SOURCE_ROOT)!r})\n"
    prefix += (
        "from structural_analysis.api import rc_fiber_frame_direct_control as api\n"
    )
    prefix += "payload={'model':{'synthetic':True},'request':{'synthetic':True},'status':'ready','metrics':{'control_work':{'unknown_solver_work_attempt_count':3}}}\n"
    prefix += "def fail(*args,**kwargs):\n"
    if error_type == "ValueError":
        prefix += "    raise ValueError('synthetic API ordinary exception')\n"
    else:
        prefix += "    raise api.BoundedRCFiberDirectControlArtifactError('synthetic API export exception',payload)\n"
    prefix += "api.analyze_bounded_rc_fiber_direct_control=fail\n"
    prefix += "metadata,segments=ns['_read_input_frame']()\nreply,output=ns['_execute_child'](metadata,segments)\nns['_write_frame'](sys.stdout.buffer,reply,output)\n"
    _script(tmp_path, monkeypatch, prefix)
    reply = _run(RCFiberPhasePolicy(20_000, 20_000, 100))
    assert reply.status == "raised" and reply.error_type == error_type
    assert reply.raw_result is None and reply.native_checkpoint is None
    assert reply.timing["wall_ns"] > 0 and reply.timing["process_cpu_ns"] > 0
    if error_type == "ValueError":
        assert reply.artifact_error_report is None
    else:
        assert reply.artifact_error_report["execution_metrics"] == {
            "control_work": {"unknown_solver_work_attempt_count": 3}
        }
        assert reply.artifact_error_report["state_or_restart_export_available"] is False
        reply.artifact_error_report["contract_pass"] = True
        assert reply.artifact_error_report["contract_pass"] is False
    _assert_reaped(reply.supervisor_timing["child_pid"])


@pytest.mark.parametrize("armed", (False, True))
def test_real_parent_sigkill_before_after_arming_direct_child_is_observed_reaped(
    tmp_path, armed
):
    # A dedicated observer subreaper adopts only this test's processes. No global
    # pytest/process-tree subreaper setting or host/cgroup mutation is needed.
    marker, gate = tmp_path / "child-ready.json", tmp_path / "arm-gate"
    child = tmp_path / "death-child.py"
    child.write_text(f"""import os,sys,time,runpy,json
from pathlib import Path
boot=runpy.run_path({str(supervisor._BOOTSTRAP_PATH)!r})
marker=Path({str(marker)!r});gate=Path({str(gate)!r})
armed={armed!r}
if armed: boot['_arm_parent_death_signal'](int(sys.argv[1]))
marker.write_text(json.dumps({{'pid':os.getpid(),'armed':armed,'solver_imported':any(k.startswith('numpy') or k.startswith('structural_analysis') for k in sys.modules)}}))
limit=time.monotonic()+8
while not armed and not gate.exists() and time.monotonic()<limit: time.sleep(0.005)
if not armed: boot['_arm_parent_death_signal'](int(sys.argv[1]))
while True: time.sleep(0.01)
""")
    parent = tmp_path / "death-parent.py"
    parent.write_text(f"""import os,sys,time,subprocess
subprocess.Popen([sys.executable,'-I',{str(child)!r},str(os.getpid())])
while True: time.sleep(0.01)
""")
    observer = tmp_path / "death-observer.py"
    observer.write_text(f"""import os,sys,time,json,ctypes,signal,subprocess
from pathlib import Path
libc=ctypes.CDLL(None,use_errno=True)
if libc.prctl(36,1,0,0,0)!=0: raise OSError(ctypes.get_errno(),'test subreaper unavailable')
parent=subprocess.Popen([sys.executable,'-I',{str(parent)!r}],start_new_session=True)
marker=Path({str(marker)!r});gate=Path({str(gate)!r})
child_pid=None;child_reaped=False
try:
    limit=time.monotonic()+6
    while not marker.exists() and time.monotonic()<limit: time.sleep(0.005)
    data=json.loads(marker.read_text());child_pid=data['pid']
    killed_ns=time.monotonic_ns();os.kill(parent.pid,signal.SIGKILL)
    death_limit=time.monotonic()+2
    while os.waitid(os.P_PID,parent.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None and time.monotonic()<death_limit: time.sleep(0.005)
    if not data['armed']: gate.write_text('release arming after observed parent death')
    limit=time.monotonic()+3;status=None
    while time.monotonic()<limit:
        observed,exit_status=os.waitpid(child_pid,os.WNOHANG)
        if observed: status=exit_status;break
        time.sleep(0.005)
    if status is None: raise RuntimeError('direct child death/reap not confirmed')
    child_reaped=True
    try: os.killpg(parent.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    parent.wait(timeout=2)
    print(json.dumps({{'marker':data,'parent_returncode':parent.returncode,'child_exitcode':os.waitstatus_to_exitcode(status),'direct_child_reaped':True,'observed_after_parent_kill_ns':time.monotonic_ns()-killed_ns}}))
finally:
    if parent.returncode is None:
        try:
            os.waitid(os.P_PID,parent.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            os.killpg(parent.pid,signal.SIGKILL)
        except (ChildProcessError,ProcessLookupError): pass
        parent.wait(timeout=2)
    if child_pid is not None and not child_reaped:
        try:
            os.waitid(os.P_PID,child_pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            os.kill(child_pid,signal.SIGKILL)
            os.waitpid(child_pid,0)
        except (ChildProcessError,ProcessLookupError): pass
""")
    completed = subprocess.run(
        [sys.executable, "-I", str(observer)], capture_output=True, timeout=15
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    proof = json.loads(completed.stdout)
    (tmp_path / "parent-death-proof.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    assert proof["parent_returncode"] == -signal.SIGKILL
    assert proof["marker"]["armed"] is armed and not proof["marker"]["solver_imported"]
    assert proof["child_exitcode"] == (-signal.SIGKILL if armed else 125)
    assert proof["direct_child_reaped"] and not _running(proof["marker"]["pid"])


@pytest.mark.parametrize(
    "change",
    (
        "mutable_bytes",
        "wrong_policy",
        "wrong_range",
        "noncanonical",
        "unsupported_platform",
    ),
)
def test_invalid_authored_input_rejects_before_child_launch(
    tmp_path, monkeypatch, change
):
    calls = []
    monkeypatch.setattr(
        supervisor, "_child_argv", lambda parent: calls.append(parent) or []
    )
    policy = RCFiberPhasePolicy(5000, 5000, 100)
    request = _request_bytes(policy)
    kwargs = dict(
        phase="analysis",
        request_bytes=request,
        completed_before=0,
        completed_after=1,
        restart=None,
        policy=policy,
        lease_check=lambda: None,
    )
    if change == "mutable_bytes":
        kwargs["request_bytes"] = bytearray(request)
    elif change == "wrong_policy":
        kwargs["policy"] = RCFiberPhasePolicy(5001, 5000, 100)
    elif change == "wrong_range":
        kwargs["completed_after"] = 2
    elif change == "noncanonical":
        kwargs["request_bytes"] = json.dumps(json.loads(request), indent=2).encode()
    else:
        monkeypatch.setattr(supervisor.sys, "platform", "unsupported-test-platform")
    with pytest.raises(supervisor.RCFiberPhaseError):
        supervisor.run_rc_fiber_phase(**kwargs)
    assert calls == []


def test_deep_malformed_request_json_rejects_as_phase_error_before_launch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supervisor, "_child_argv", lambda parent: calls.append(parent) or []
    )
    nested = b'{"nested":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        supervisor.run_rc_fiber_phase(
            phase="analysis",
            request_bytes=nested,
            completed_before=0,
            completed_after=1,
            restart=None,
            policy=RCFiberPhasePolicy(5000, 5000, 100),
            lease_check=lambda: None,
        )
    assert captured.value.code == "rc_fiber_worker_analysis_transport_invalid"
    assert calls == []


@pytest.mark.parametrize("role", ("metadata", "verification_report"))
def test_real_deep_malformed_json_is_unaccounted_transport_failure(
    tmp_path, monkeypatch, role
):
    if role == "metadata":
        code = "metadata,segments=ns['_read_input_frame']()\n"
        code += "raw=b'{\"nested\":'+b'['*1500+b'0'+b']'*1500+b'}'\n"
        code += "sys.stdout.buffer.write(ns['_HEADER'].pack(ns['_MAGIC'],len(raw),0,0,0,0));sys.stdout.buffer.write(raw);sys.stdout.buffer.flush()\n"
        phase = "analysis"
    else:
        code = _reply_code(phase="verification", report={"placeholder": True})
        code += "raw=b'{\"nested\":'+b'['*1500+b'0'+b']'*1500+b'}'\n"
        code += "output=(None,None,raw,None)\nns['_write_frame'](sys.stdout.buffer,reply,output)\n"
        phase = "verification"
    _script(tmp_path, monkeypatch, code)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100), phase=phase)
    assert captured.value.code == f"rc_fiber_worker_{phase}_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]
    _assert_reaped(captured.value.cleanup["pid"])


def test_successful_reply_cannot_hide_group_cleanup_error(tmp_path, monkeypatch):
    _script(tmp_path, monkeypatch, _write_reply_code())
    original = supervisor._signal_group

    def denied_completed_group(process, sig, diagnostics):
        if sig == signal.SIGKILL and supervisor._observe_exit(process) is not None:
            diagnostics["signal_errors"].append(
                {"signal": "SIGKILL", "errno": errno.EPERM}
            )
        else:
            original(process, sig, diagnostics)

    monkeypatch.setattr(supervisor, "_signal_group", denied_completed_group)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_cleanup_failed"
    assert captured.value.cleanup["direct_child_reaped"]
    assert captured.value.cleanup["prior_cleanup"]["signal_errors"] == [
        {"signal": "SIGKILL", "errno": errno.EPERM}
    ]
    _assert_reaped(captured.value.cleanup["pid"])


@pytest.mark.parametrize(
    "kind",
    (
        "missing_typed_report",
        "typed_report_wrong_claims",
        "typed_report_integer_contract",
        "typed_report_integer_claim",
        "report_on_ordinary_exception",
    ),
)
def test_structured_exception_contract_corruption_rejected_before_measured_reply(
    tmp_path, monkeypatch, kind
):
    report = api.BoundedRCFiberDirectControlArtifactError(
        "synthetic export failure",
        {"model": {}, "request": {}, "status": "ready", "metrics": {}},
    ).to_dict()
    if kind == "typed_report_wrong_claims":
        report["claims"]["release_approved"] = True
    elif kind == "typed_report_integer_contract":
        report["contract_pass"] = 0
    elif kind == "typed_report_integer_claim":
        report["claims"]["release_approved"] = 0
    body = _reply_code(
        error_type="ValueError"
        if kind == "report_on_ordinary_exception"
        else "BoundedRCFiberDirectControlArtifactError",
        artifact_error=None if kind == "missing_typed_report" else report,
    )
    body += "ns['_write_frame'](sys.stdout.buffer,reply,output)\n"
    _script(tmp_path, monkeypatch, body)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_transport_invalid"
    assert captured.value.cleanup["direct_child_reaped"]


@pytest.mark.parametrize("handler", (signal.SIG_IGN, lambda _sig, _frame: None))
@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_nondefault_sigchld_refuses_without_host_mutation_or_launch(
    monkeypatch, handler, phase
):
    actual = signal.getsignal(signal.SIGCHLD)
    monkeypatch.setattr(supervisor.signal, "getsignal", lambda _signal: handler)
    calls = []
    monkeypatch.setattr(
        supervisor, "_child_argv", lambda parent: calls.append(parent) or []
    )
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100), phase=phase)
    assert captured.value.code == f"rc_fiber_worker_{phase}_unsupported"
    assert calls == []
    # The guard reads the handler; it never installs or restores one itself.
    monkeypatch.undo()
    assert signal.getsignal(signal.SIGCHLD) is actual


def test_group_signal_observes_owned_zombie_before_explicit_reap(tmp_path, monkeypatch):
    _script(tmp_path, monkeypatch, _write_reply_code())
    original = supervisor._signal_group
    events = []

    def observe_signal(process, sig, diagnostics):
        observed = os.waitid(
            os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
        )
        events.append(
            {
                "pid": process.pid,
                "signal": signal.Signals(sig).name,
                "owned_exited_child": observed is not None,
                "reaped_returncode_before_signal": process.returncode,
            }
        )
        assert observed is not None and process.returncode is None
        assert observed.si_status == 0
        original(process, sig, diagnostics)

    monkeypatch.setattr(supervisor, "_signal_group", observe_signal)
    reply = _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert events == [
        {
            "pid": reply.supervisor_timing["child_pid"],
            "signal": "SIGKILL",
            "owned_exited_child": True,
            "reaped_returncode_before_signal": None,
        }
    ]
    (tmp_path / "owned-before-signal-proof.json").write_text(
        json.dumps(events, indent=2) + "\n"
    )
    _assert_reaped(reply.supervisor_timing["child_pid"])


def test_actual_competing_reaper_echild_refuses_numeric_group_signals(
    tmp_path, monkeypatch
):
    _script(tmp_path, monkeypatch, _write_reply_code())
    original = supervisor._observe_exit
    reaped = []
    signals = []

    def steal_reap(process):
        observed = original(process)
        if observed is not None:
            reaped.append({"pid": process.pid, "returncode": process.wait(timeout=1)})
            raise ChildProcessError("synthetic external reaper consumed exact child")
        return observed

    monkeypatch.setattr(supervisor, "_observe_exit", steal_reap)
    monkeypatch.setattr(supervisor, "_signal_group", lambda *args: signals.append(args))
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_cleanup_failed"
    assert captured.value.cleanup["ownership_lost"]
    assert captured.value.cleanup["direct_child_reaped"] is False
    assert signals == [] and len(reaped) == 1
    _assert_reaped(reaped[0]["pid"])


@pytest.mark.parametrize("phase", ("analysis", "verification"))
def test_selector_creation_failure_keeps_phase_code_and_never_launches(
    monkeypatch, phase
):
    launches = []

    def fail_selector():
        raise OSError(errno.EMFILE, "synthetic selector descriptor exhaustion")

    monkeypatch.setattr(supervisor.selectors, "DefaultSelector", fail_selector)
    monkeypatch.setattr(
        supervisor.subprocess, "Popen", lambda *args, **kwargs: launches.append(args)
    )
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100), phase=phase)
    assert captured.value.code == f"rc_fiber_worker_{phase}_transport_invalid"
    assert captured.value.cleanup == {}
    assert launches == []


@pytest.mark.parametrize("stage", ("set_blocking", "selector_registration"))
def test_real_launch_setup_failure_closes_every_owned_pipe_and_reaps(
    tmp_path, monkeypatch, stage
):
    marker = _blocking_script(tmp_path, monkeypatch)
    original_popen = supervisor.subprocess.Popen
    children = []

    def launch(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(supervisor.subprocess, "Popen", launch)
    if stage == "set_blocking":
        monkeypatch.setattr(
            supervisor.os,
            "set_blocking",
            lambda *_args: (_ for _ in ()).throw(
                OSError(errno.EIO, "synthetic pipe setup failure")
            ),
        )
    else:
        original_factory = supervisor.selectors.DefaultSelector

        class FailingSelector:
            def __init__(self):
                self.owned = original_factory()
                self.count = 0

            def register(self, *args):
                self.count += 1
                if self.count == 2:
                    raise OSError(errno.EIO, "synthetic stdout selector setup failure")
                return self.owned.register(*args)

            def close(self):
                self.owned.close()

        monkeypatch.setattr(supervisor.selectors, "DefaultSelector", FailingSelector)
    try:
        with pytest.raises(supervisor.RCFiberPhaseError) as captured:
            _run(RCFiberPhasePolicy(5000, 5000, 100))
        assert captured.value.code == "rc_fiber_worker_analysis_transport_invalid"
        assert captured.value.cleanup["direct_child_reaped"]
        assert len(children) == 1
        process = children[0]
        assert all(
            stream.closed for stream in (process.stdin, process.stdout, process.stderr)
        )
        _assert_reaped(process.pid)
    finally:
        _cleanup_marker(marker)


def test_positive_pid_one_is_not_artificially_excluded_before_parent_recheck(tmp_path):
    # PID1 is a legitimate container worker. We do not signal host PID1 or need
    # a privileged PID namespace: a real fresh child arms for expected PID1 and
    # then verifies its actual parent. Here that parent is this pytest process.
    child = tmp_path / "pid-one-bootstrap.py"
    child.write_text(
        "import runpy,os\n"
        f"boot=runpy.run_path({str(supervisor._BOOTSTRAP_PATH)!r})\n"
        "boot['_arm_parent_death_signal'](1)\n"
        "print('positive parent PID accepted and current parent matched')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(child)], capture_output=True, timeout=5
    )
    assert completed.stderr == b""
    if os.getpid() == 1:
        assert completed.returncode == 0
    else:
        assert completed.returncode == 125 and completed.stdout == b""


def test_actual_competing_reaper_after_observation_cannot_synthesize_exit_zero(
    tmp_path, monkeypatch
):
    _script(tmp_path, monkeypatch, _write_reply_code())
    original = supervisor._signal_group
    stolen = []

    def signal_then_steal_wait(process, sig, diagnostics):
        original(process, sig, diagnostics)
        if sig == signal.SIGKILL:
            waited, status = os.waitpid(process.pid, os.WNOHANG)
            assert waited == process.pid
            stolen.append(
                {"pid": waited, "actual_exitcode": os.waitstatus_to_exitcode(status)}
            )
            # Deliberately leave Popen.returncode unset: its wait implementation
            # would mask the subsequent ECHILD as a fabricated successful exit0.
            assert process.returncode is None

    monkeypatch.setattr(supervisor, "_signal_group", signal_then_steal_wait)
    with pytest.raises(supervisor.RCFiberPhaseError) as captured:
        _run(RCFiberPhasePolicy(5000, 5000, 100))
    assert captured.value.code == "rc_fiber_worker_analysis_cleanup_failed"
    assert captured.value.cleanup["ownership_lost"]
    assert captured.value.cleanup["direct_child_reaped"] is False
    assert len(stolen) == 1 and stolen[0]["actual_exitcode"] == 0
    _assert_reaped(stolen[0]["pid"])


def test_browser_integer_spelling_preserves_original_identity_and_typed_chunk(real_phase_artifacts):
    policy, original_request, original, _ = real_phase_artifacts
    def browser_numbers(value):
        if type(value) is float and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: browser_numbers(item) for key, item in value.items()}
        if isinstance(value, list):
            return [browser_numbers(item) for item in value]
        return value
    request = json.loads(original_request)
    request["config"] = browser_numbers(request["config"])
    browser_request = _bytes(request)
    assert browser_request != original_request
    before = supervisor._input_metadata('analysis', original_request, 0, 1, None, None, None, policy)
    after = supervisor._input_metadata('analysis', browser_request, 0, 1, None, None, None, policy)
    assert before['identity']['job_request_hash'] != after['identity']['job_request_hash']
    assert before['identity']['chunk_request_hash'] == after['identity']['chunk_request_hash']
    result = supervisor.run_rc_fiber_phase(
        phase='analysis', request_bytes=browser_request, completed_before=0,
        completed_after=1, restart=None, policy=policy, lease_check=lambda: None)
    assert result.raw_result == original.raw_result
    assert result.native_checkpoint == original.native_checkpoint
    verified = supervisor.run_rc_fiber_phase(
        phase='verification', request_bytes=browser_request, completed_before=0,
        completed_after=1, restart=None, result=result.raw_result,
        checkpoint=result.native_checkpoint, policy=policy, lease_check=lambda: None)
    assert verified.verification_report['contract_pass']
    assert verified.verification_report['fresh_source_execution_invoked']
