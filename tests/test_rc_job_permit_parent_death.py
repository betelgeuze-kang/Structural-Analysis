"""Real killed worker, inherited two-fd custody and adopted direct-child reap.

The controlled phase never imports or executes a numerical solver. A dedicated
observer owns its subreaper setting. This is cooperating Linux process evidence,
not escaped-descendant containment, whole-job cost or specimen qualification.
"""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from structural_analysis.execution import rc_fiber_phase_supervisor as common


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux fd/death custody"
)


@pytest.mark.parametrize("armed", (False, True))
def test_killed_worker_cannot_admit_replacement_while_direct_child_holds_guards(
    tmp_path, armed
):
    repo = Path(__file__).parents[1]
    roots = [str(repo / "src"), str(repo), *common._dependency_paths()]
    imports = f"import sys\nsys.path[:0]={roots!r}\n"
    marker, gate, clock = (tmp_path / name for name in ("child.json", "gate", "clock"))
    child, parent, observer = (
        tmp_path / name for name in ("child.py", "parent.py", "observer.py")
    )
    child.write_text(f"""import os,sys,time,json,runpy
from pathlib import Path
boot=runpy.run_path({str(common._BOOTSTRAP_PATH)!r})
armed={armed!r}
if armed: boot['_arm_parent_death_signal'](int(sys.argv[1]))
guards=[{{'fd':int(arg),'device':os.fstat(int(arg)).st_dev,'inode':os.fstat(int(arg)).st_ino}} for arg in sys.argv[2:]]
assert len(guards)==2 and guards[0]['inode']!=guards[1]['inode']
Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid(),'armed':armed,'guards':guards,'solver_imported':any(k.startswith('numpy') or k.startswith('structural_analysis') for k in sys.modules)}}))
limit=time.monotonic()+8
while not armed and not Path({str(gate)!r}).exists() and time.monotonic()<limit: time.sleep(.005)
if not armed: boot['_arm_parent_death_signal'](int(sys.argv[1]))
while True: time.sleep(.01)
""")
    parent.write_text(
        imports
        + f"""from pathlib import Path
from datetime import datetime
from structural_analysis.execution import rc_corotational_phase_supervisor as phase
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.api import rc_corotational_control as api
from tests.test_rc_corotational_isolated_worker import helpers,service
def forbidden(*args,**kwargs): raise AssertionError('controlled test called numerical API')
api.analyze_rc_corotational_control=forbidden
api.validate_rc_corotational_control_artifacts=forbidden
api._source_identity=forbidden
clock=lambda:datetime.fromisoformat(Path({str(clock)!r}).read_text())
current=service(Path({str(tmp_path / "source")!r}),clock=clock)
claim=current.claim_next(**helpers.WORKER,lease_seconds=30)
assert claim is not None
original=phase.run_rc_corotational_phase
def controlled(**kwargs):
    assert kwargs['authority_fd'] is not None and kwargs['job_guard_fd'] is not None
    phase._child_argv=lambda expected:[sys.executable,'-I',{str(child)!r},str(expected),str(kwargs['authority_fd']),str(kwargs['job_guard_fd'])]
    return original(**kwargs)
phase.run_rc_corotational_phase=controlled
execute_job_claim(current,claim,**helpers.WORKER,lease_seconds=30)
"""
    )
    observer.write_text(
        imports
        + f"""import os,time,json,ctypes,signal
from pathlib import Path
from datetime import datetime
from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_store_backup import backup_job_store,restore_job_store
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.execution import rc_fiber_phase_supervisor as common
from structural_analysis.execution import rc_corotational_phase_supervisor as phase
from structural_analysis.api import rc_corotational_control as api
from tests.test_rc_corotational_isolated_worker import helpers,service,request
def forbidden(*args,**kwargs): raise AssertionError('busy observer called numerical API or phase')
api.analyze_rc_corotational_control=forbidden
api.validate_rc_corotational_control_artifacts=forbidden
api._source_identity=forbidden
phase.run_rc_corotational_phase=forbidden
import subprocess
libc=ctypes.CDLL(None,use_errno=True)
if libc.prctl(36,1,0,0,0)!=0: raise OSError(ctypes.get_errno(),'test subreaper unavailable')
base=Path({str(tmp_path)!r});clock_path=Path({str(clock)!r})
clock_path.write_text('2026-10-12T00:00:00+00:00')
clock=lambda:datetime.fromisoformat(clock_path.read_text())
authority,binding=JobExecutionAuthority.create(base/'authority',base/'source')
current=service(base/'source',clock=clock,execution_authority=authority,execution_binding=binding)
job=current.submit_job(**helpers.TENANT,idempotency_key='killed-worker',request=request())
snapshot=backup_job_store(base/'source',base/'backup',maximum_bytes=10_000_000)
options={{'manifest_sha256':snapshot['manifest_sha256'],'maximum_bytes':10_000_000}}
restore_job_store(base/'backup',base/'restored',**options)
parent=subprocess.Popen([sys.executable,'-I',{str(parent)!r}],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=common._child_environment())
child_pid=None;reaped=False
try:
    limit=time.monotonic()+6
    while not Path({str(marker)!r}).exists() and time.monotonic()<limit: time.sleep(.005)
    if not Path({str(marker)!r}).exists(): raise RuntimeError('child never retained both guard descriptors')
    data=json.loads(Path({str(marker)!r}).read_text());child_pid=data['pid']
    assert not data['solver_imported'] and data['armed']=={armed!r}
    os.kill(parent.pid,signal.SIGKILL)
    limit=time.monotonic()+2
    while os.waitid(os.P_PID,parent.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None and time.monotonic()<limit: time.sleep(.005)
    clock_path.write_text('2026-10-12T00:00:31+00:00')
    fresh=service(base/'source',clock=clock)
    replacement=fresh.claim_next(**helpers.SECOND,lease_seconds=30)
    assert replacement is not None and replacement.job.attempt==2
    credentials=dict(helpers.SECOND,lease_token=replacement.lease_token)
    before=fresh.get_job(job.job_id,**helpers.TENANT).to_dict()
    evidence=fresh.read_rc_invocation_evidence(job.job_id,**helpers.TENANT)
    assert evidence['pending_ordinals']==[1] and evidence['execution_budget']['reserved_attempts']==1
    if not {armed!r}:
        assert os.waitid(os.P_PID,child_pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None
        try: execute_job_claim(fresh,replacement,**helpers.SECOND,lease_seconds=30)
        except JobServiceError as error: assert error.code=='job_execution_permit_busy'
        else: raise AssertionError('replacement admitted while inherited job guard still alive')
        assert fresh.get_job(job.job_id,**helpers.TENANT).to_dict()==before
        assert fresh.read_rc_invocation_evidence(job.job_id,**helpers.TENANT)==evidence
        try: activate_managed_restore(base/'backup',base/'restored',**options)
        except ValueError as error: assert 'authority busy' in str(error)
        else: raise AssertionError('activation admitted while inherited generation guard still alive')
        Path({str(gate)!r}).write_text('release after observed parent death')
    limit=time.monotonic()+3;observed=None
    while time.monotonic()<limit:
        observed=os.waitid(os.P_PID,child_pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        if observed is not None: break
        time.sleep(.005)
    assert observed is not None
    # Exit closes kernel descriptors before an adopted zombie is reaped. The
    # claim is no active numerical overlap, not exclusion until orphan reaping.
    with fresh.job_execution_permit(job.job_id,expected_request_hash=job.request.content_hash,**credentials) as fd: os.fstat(fd)
    waited,status=os.waitpid(child_pid,os.WNOHANG);assert waited==child_pid;reaped=True
    child_returncode=os.waitstatus_to_exitcode(status)
    assert child_returncode==(-signal.SIGKILL if {armed!r} else 125)
    parent.wait(timeout=2);assert parent.returncode==-signal.SIGKILL
    activated=activate_managed_restore(base/'backup',base/'restored',**options)
    assert activated['generation']==2
    try: fresh.reserve_execution_attempt(job.job_id,**credentials)
    except JobServiceError as error: assert error.code=='execution_authority_rejected'
    else: raise AssertionError('old generation not fenced')
    restored=service(base/'restored',clock=clock)
    resumed=restored.claim_next(**helpers.SECOND,lease_seconds=30)
    assert resumed is not None and resumed.job.job_id==job.job_id
    retained=restored.read_rc_invocation_evidence(job.job_id,**helpers.TENANT)
    assert retained['pending_ordinals']==[1] and retained['execution_budget']['reserved_attempts']==1
    assert restored.validate_integrity(job.job_id,**helpers.TENANT)['contract_pass']
    print(json.dumps({{'armed':data['armed'],'inherited_guard_count':len(data['guards']),'prearm_busy_replacement_checked':not {armed!r},'parent_returncode':parent.returncode,'child_returncode':child_returncode,'direct_child_exit_observed_before_new_admission':True,'adopted_direct_child_reaped':True,'restored_generation':activated['generation'],'retained_unknown_ordinals':retained['pending_ordinals'],'reserved_api_invocations':retained['execution_budget']['reserved_attempts'],'numerical_api_called':False,'independent_physical_validation':False}}))
finally:
    if parent.returncode is None:
        try:
            os.waitid(os.P_PID,parent.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            os.killpg(parent.pid,signal.SIGKILL)
        except (ChildProcessError,ProcessLookupError): pass
        parent.wait(timeout=2)
    if child_pid is not None and not reaped:
        try:
            os.waitid(os.P_PID,child_pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            os.killpg(child_pid,signal.SIGKILL)
            os.waitpid(child_pid,0)
        except (ChildProcessError,ProcessLookupError): pass
"""
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(observer)], capture_output=True, timeout=18
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    proof = json.loads(completed.stdout)
    (tmp_path / "parent-death-proof.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    assert proof["inherited_guard_count"] == 2
    assert proof["adopted_direct_child_reaped"]
    assert proof["retained_unknown_ordinals"] == [1]
    assert proof["numerical_api_called"] is False
