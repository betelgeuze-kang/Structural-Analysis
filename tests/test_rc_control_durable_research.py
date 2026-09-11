"""Real small RC solves plus explicitly isolated failure/lease controls."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_rc_control_local_research import model as model, control_request as control_request, options as options, candidate
from structural_analysis.benchmark.rc_control_durable import DurableRCControlResultSession
from structural_analysis.benchmark.rc_control_reuse import NewAnalysisRequired
from structural_analysis.benchmark.rc_control_cost_search import run_rc_control_cost_search
from structural_analysis.benchmark import rc_control_durable as durable
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.execution.job_service import JobServiceError

SOURCE = '4a856164a999aefb8204fd63eb8bbb150862d463'
TENANT = 'fixture-tenant-token-long'
WORKER = 'fixture-worker-token-long'


def session(root, **kwargs):
    return DurableRCControlResultSession(
        store_root=root, source_revision=SOURCE, scope_id='lab',
        authorization_token=TENANT, worker_token=WORKER, **kwargs)


def evaluate(s, m, r, opts, out, **kwargs):
    return s.evaluate(m, r, scope_id='lab', output_directory=out, **(opts | kwargs))


def test_reopen_reprice_and_rescreen_preserve_originals(model, control_request, options, tmp_path):
    root = tmp_path/'store'
    first = evaluate(session(root), model, control_request, options, tmp_path/'first')
    assert first['row']['full_reference_verification_pass']
    assert first['new_work']['known_counters']['attempted_step_count'] == 8
    second = evaluate(session(root), model, control_request, options, tmp_path/'second',
                      allow_new_analysis=False, prices=replace(options['prices'], concrete_per_m3=150.))
    assert second['mode'] == 'verified_durable_original_reused'
    assert second['new_work']['api_invocation_count'] == 0
    assert second['row']['material_estimate']['total'] - first['row']['material_estimate']['total'] == pytest.approx(36.)
    assert not second['fresh_reference_verification_this_call']
    for role in first['row']['artifacts']:
        assert (tmp_path/'first'/first['row']['artifacts'][role]['path']).read_bytes() == (tmp_path/'second'/second['row']['artifacts'][role]['path']).read_bytes()
    strict = replace(options['history_limits'], maximum_translation_m=1e-12)
    third = evaluate(session(root), model, control_request, options, tmp_path/'third',
                     history_limits=strict, allow_new_analysis=False)
    assert third['row']['full_reference_verification_pass'] and not third['row']['selection_eligible']
    assert third['new_work']['api_invocation_count'] == 0
    assert all(type(v) is int and v >= 0 for v in third['timings_ns'].values())
    assert TENANT not in json.dumps(third) and WORKER not in json.dumps(third)


def test_chunk_boundary_pause_resume_matches_fresh(model, control_request, options, tmp_path):
    args = dict(chunk_target_count=2, max_chunks_per_call=1)
    first = evaluate(session(tmp_path/'store', **args), model, control_request, options, tmp_path/'prefix')
    assert first['job']['status'] == 'checkpointed'
    assert first['job']['progress']['completed_steps'] == 2
    assert not first['row']['full_reference_verification_pass']
    assert first['new_work']['known_counters']['attempted_step_count'] == 6
    final = evaluate(session(tmp_path/'store', **args), model, control_request, options, tmp_path/'final')
    assert final['job']['status'] == 'succeeded'
    assert final['new_work']['known_counters']['attempted_step_count'] == 8
    fresh = evaluate(session(tmp_path/'other'), model, control_request, options, tmp_path/'fresh')
    payload = lambda row, root: json.loads((root/row['row']['artifacts']['result']['path']).read_bytes())['api_result']
    assert payload(final,tmp_path/'final')['response_history'] == payload(fresh,tmp_path/'fresh')['response_history']


def test_second_interpreter_reuses_without_calling_worker(model, control_request, options, tmp_path):
    root = tmp_path/'store'
    evaluate(session(root), model, control_request, options, tmp_path/'first')
    # CanonicalModel.to_dict retains provenance, needed for identical physics key.
    input_file = tmp_path/'input.json'
    from dataclasses import asdict
    input_file.write_text(json.dumps({'model': model.to_dict(), 'request': control_request.to_dict(),
        'history': asdict(options['history_limits']), 'material': asdict(options['material_limits']),
        'prices': asdict(options['prices'])}))
    program = '''
import json, sys
from pathlib import Path
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.api.rc_fiber_frame_direct_control_request import decode_bounded_rc_fiber_direct_control_request
from structural_analysis.benchmark.fiber_frame_design import FiberFrameHistoryLimits, FiberFrameMaterialHistoryLimits, FiberFrameMaterialPrices
from structural_analysis.benchmark.rc_control_durable import DurableRCControlResultSession
import structural_analysis.benchmark.rc_control_durable as d
v=json.loads(Path(sys.argv[1]).read_text())
# Reconstruct the exact serialized canonical dataclass, not a new source path.
from dataclasses import fields
from structural_analysis.model.schema import UnitSystem, CoordinateSystem
args={f.name:v['model'][f.name] for f in fields(CanonicalModel) if f.name in v['model']}
args['units']=UnitSystem(**args['units'])
args['coordinate_system']=CoordinateSystem(**args['coordinate_system'])
m=CanonicalModel(**args)
r=decode_bounded_rc_fiber_direct_control_request(v['request'])
def forbidden(*a,**kw): raise AssertionError('worker called on disk hit')
d.execute_rc_fiber_direct_control_claim=forbidden
s=DurableRCControlResultSession(store_root=Path(sys.argv[2]),source_revision=sys.argv[4],scope_id='lab',authorization_token='fixture-tenant-token-long',worker_token='fixture-worker-token-long')
o=s.evaluate(m,r,scope_id='lab',output_directory=Path(sys.argv[3]),history_limits=FiberFrameHistoryLimits(**v['history']),material_limits=FiberFrameMaterialHistoryLimits(**v['material']),prices=FiberFrameMaterialPrices(**v['prices']),allow_new_analysis=False)
print(json.dumps({'mode':o['mode'],'new_work':o['new_work']}))
'''
    process = subprocess.run([sys.executable,'-c',program,str(input_file),str(root),str(tmp_path/'second'),SOURCE],
                             capture_output=True,text=True,timeout=25)
    assert process.returncode == 0, process.stderr
    result=json.loads(process.stdout)
    assert result['new_work']['api_invocation_count']==0


def test_source_or_load_change_cannot_reuse(model, control_request, options, tmp_path):
    root=tmp_path/'store'
    evaluate(session(root),model,control_request,options,tmp_path/'first')
    changed=replace(control_request,constant_nodal_loads=(('N2',-601.,0.,0.),))
    with pytest.raises(NewAnalysisRequired):
        evaluate(session(root),model,changed,options,tmp_path/'miss',allow_new_analysis=False)
    assert not (tmp_path/'miss').exists()


def test_corrupt_result_rejected_before_export(model, control_request, options, tmp_path):
    s=session(tmp_path/'store')
    first=evaluate(s,model,control_request,options,tmp_path/'first')
    service=s._store(first['physics_key'])
    path=service._blob_path(first['job']['result']['content_hash'])
    path.write_bytes(b'{}')
    with pytest.raises(JobServiceError):
        evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'corrupt',allow_new_analysis=False)
    assert not (tmp_path/'corrupt').exists()


def test_export_failure_keeps_only_completed_durable_result(model,control_request,options,tmp_path,monkeypatch):
    original=study._save
    def fail(root,name,raw):
        if name=='evaluation.json': raise OSError('disk full simulation')
        return original(root,name,raw)
    with monkeypatch.context() as m:
        m.setattr(study,'_save',fail)
        with pytest.raises(OSError,match='disk full'):
            evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'failed-export')
    result=evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'recovered',allow_new_analysis=False)
    assert result['mode']=='verified_durable_original_reused'
    assert result['row']['full_reference_verification_pass']


def test_cancelled_job_is_not_automatically_retried(model,control_request,options,tmp_path):
    s=session(tmp_path/'store',chunk_target_count=1,max_chunks_per_call=1)
    first=evaluate(s,model,control_request,options,tmp_path/'prefix')
    service=s._store(first['physics_key'])
    with pytest.raises(JobServiceError):
        service.cancel_job(first['job']['job_id'],tenant_id='lab',authorization_token='wrong-secret')
    service.cancel_job(first['job']['job_id'],tenant_id='lab',authorization_token=TENANT)
    result=evaluate(s,model,control_request,options,tmp_path/'cancelled')
    assert result['job']['status']=='cancelled'
    assert not result['row']['selection_eligible']
    assert result['new_work']['api_invocation_count']==0


def test_candidate_search_reuses_after_session_recreation(model,control_request,options,tmp_path):
    candidates=(candidate('cheap',.35),candidate('costly',.5))
    def run(s,out,budget):
        return run_rc_control_cost_search(model,candidates,control_request,session=s,scope_id='lab',
              output_directory=out,max_new_model_analyses=budget,**options)
    a=run(session(tmp_path/'store'),tmp_path/'a',2)
    b=run(session(tmp_path/'store'),tmp_path/'b',0)
    assert a['status']==b['status']=='pool_minimum_confirmed'
    assert a['new_work']['known_counters']['attempted_step_count']==16
    assert b['new_model_evaluations']==0 and b['reused_model_evaluations']==2
    assert b['new_work']['api_invocation_count']==0


def test_failed_worker_cannot_publish_a_reusable_result(model,control_request,options,tmp_path,monkeypatch):
    original=durable.execute_rc_fiber_direct_control_claim
    def failed(service,claim,**kwargs):
        service.fail_job(claim.job.job_id,worker_id='local-rc',authorization_token=WORKER,
                         lease_token=claim.lease_token,error_code='test_failure',retriable=False)
        return service.get_job(claim.job.job_id,tenant_id='lab',authorization_token=TENANT)
    monkeypatch.setattr(durable,'execute_rc_fiber_direct_control_claim',failed)
    first=evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'failed')
    assert first['job']['status']=='failed'
    monkeypatch.setattr(durable,'execute_rc_fiber_direct_control_claim',original)
    with pytest.raises(NewAnalysisRequired):
        evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'nohit',allow_new_analysis=False)


@pytest.mark.parametrize('name,value',[('chunk_target_count',0),('chunk_target_count',True),('max_chunks_per_call',0),('max_chunks_per_call',256)])
def test_bad_chunk_limits(name,value,tmp_path):
    with pytest.raises(ValueError): session(tmp_path/'unused',**{name:value})
    assert not (tmp_path/'unused').exists()


def test_symlink_store_rejected(tmp_path):
    target=tmp_path/'target';target.mkdir();link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'): session(link)


def test_bounded_parallel_batch_real_models(model, control_request, options, tmp_path):
    from structural_analysis.benchmark.rc_control_local_batch import run_local_rc_batch
    from structural_analysis.benchmark import fiber_frame_design as d
    wider=d.apply_fiber_frame_section_changes(model,candidate('wide',.5))
    result=run_local_rc_batch({'one':model,'two':wider},control_request,
        session=session(tmp_path/'store'),scope_id='lab',output_directory=tmp_path/'batch',
        max_workers=2,**options)
    assert result['requested_count']==2
    assert all(r['verified'] for r in result['records'].values())
    assert sum(r['new_work']['known_counters']['attempted_step_count'] for r in result['records'].values())==16
    assert result['claims']['hard_memory_limit'] is False


def test_batch_stop_and_budget_leave_unrequested(model, control_request, options, tmp_path):
    from threading import Event
    from structural_analysis.benchmark.rc_control_local_batch import run_local_rc_batch
    stop=Event();stop.set()
    result=run_local_rc_batch({'one':model},control_request,session=session(tmp_path/'store'),
        scope_id='lab',output_directory=tmp_path/'stopped',stop_event=stop,**options)
    assert result['requested_count']==0 and result['records']['one']['status']=='unrequested'
    result=run_local_rc_batch({'one':model},control_request,session=session(tmp_path/'store'),
        scope_id='lab',output_directory=tmp_path/'zero',max_requested_models=0,**options)
    assert result['requested_count']==0


def test_durable_cli_cross_invocation(model, control_request, options, tmp_path, monkeypatch, capsys):
    from structural_analysis.benchmark.rc_control_durable_cli import main
    from test_rc_control_local_research import experiment_file
    monkeypatch.setenv('STRUCTURAL_RC_TENANT_TOKEN',TENANT)
    monkeypatch.setenv('STRUCTURAL_RC_WORKER_TOKEN',WORKER)
    root=Path(__file__).resolve().parents[1]
    req=tmp_path/'request.json'; req.write_bytes(study._bytes(control_request.to_dict()))
    exp=experiment_file(tmp_path/'experiment.json',options)
    args=['--model',str(root/'examples/public_rc_fiber_frame_cantilever.json'),'--request',str(req),
          '--experiment',str(exp),'--source-revision',SOURCE,'--store',str(tmp_path/'store')]
    assert main(args+['--output',str(tmp_path/'first'),'--max-new-model-analyses','2'])==0
    capsys.readouterr()
    assert main(args+['--output',str(tmp_path/'second'),'--max-new-model-analyses','0'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['scenarios'][0]['new_work']['api_invocation_count']==0
    assert result['scenarios'][0]['reused_model_evaluations']==2


def test_lost_lease_without_numerical_reservation_can_be_reclaimed(model, control_request, options, tmp_path, monkeypatch):
    import sqlite3
    real=durable.execute_rc_fiber_direct_control_claim
    class Halt(BaseException): pass
    def killed(*args,**kwargs): raise Halt()
    s=session(tmp_path/'store')
    monkeypatch.setattr(durable,'execute_rc_fiber_direct_control_claim',killed)
    with pytest.raises(Halt): evaluate(s,model,control_request,options,tmp_path/'killed')
    databases=list((tmp_path/'store').glob('*/jobs.sqlite3'))
    assert len(databases)==1
    # Controlled clock-fault injection; no physical/numerical record is edited.
    with sqlite3.connect(databases[0]) as db:
        db.execute('UPDATE jobs SET lease_expires_us=0')
    monkeypatch.setattr(durable,'execute_rc_fiber_direct_control_claim',real)
    result=evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'recovered')
    assert result['row']['full_reference_verification_pass']
    assert result['new_work']['known_counters']['attempted_step_count']==8


def test_abandoned_numerical_reservation_is_not_retried(model, control_request, options, tmp_path, monkeypatch):
    import sqlite3
    class Halt(BaseException): pass
    real=durable.execute_rc_fiber_direct_control_claim
    def killed(service,claim,**kwargs):
        service.reserve_execution_attempt(claim.job.job_id,worker_id='local-rc',
            authorization_token=WORKER,lease_token=claim.lease_token)
        raise Halt()
    monkeypatch.setattr(durable,'execute_rc_fiber_direct_control_claim',killed)
    with pytest.raises(Halt): evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'killed')
    monkeypatch.setattr(durable,'execute_rc_fiber_direct_control_claim',real)
    for database in (tmp_path/'store').glob('*/jobs.sqlite3'):
        with sqlite3.connect(database) as db: db.execute('UPDATE jobs SET lease_expires_us=0')
    result=evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'blocked')
    assert result['historical_unknown_work']
    assert not result['row']['full_reference_verification_pass']
    assert result['new_work']['api_invocation_count']==0


def test_simultaneous_same_physics_does_not_double_charge_work(model, control_request, options, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    a,b=session(tmp_path/'store'),session(tmp_path/'store')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(evaluate,s,model,control_request,options,tmp_path/f'run-{i}') for i,s in enumerate((a,b))]
        results=[f.result() for f in futures]
    assert sum(r['new_work']['api_invocation_count'] for r in results)==2
    assert sum(r['new_work']['known_counters'].get('attempted_step_count',0) for r in results)==8
    final=evaluate(session(tmp_path/'store'),model,control_request,options,tmp_path/'final',allow_new_analysis=False)
    assert final['row']['full_reference_verification_pass']
