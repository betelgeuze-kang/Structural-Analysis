"""Local reuse and finite-pool termination: arithmetic controls + real RC solves.

Tiny authored cases establish plumbing and specified invariants, not validation
against physical experiments, a code-compliant design, or GPU performance.
"""

from __future__ import annotations

from dataclasses import replace
import itertools
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as reference
from structural_analysis.benchmark import rc_control_reuse as reuse
from structural_analysis.benchmark import rc_control_cost_search as search
from structural_analysis.benchmark import rc_control_local_search_cli as cli
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '9b21d748d4273b6850d99220a48907f6300fd98a'


@pytest.fixture
def model():
    return load_neutral_json_bytes(
        (ROOT / 'examples/public_rc_fiber_frame_cantilever.json').read_bytes(),
        source_path='authored-local-research-example.json')


@pytest.fixture
def control_request():
    return BoundedRCFiberDirectControlRequest(
        control_global_dof=4, targets_m=(1e-5, 2e-5, -1e-5),
        allow_reversals=True, maximum_reversals=2,
        constant_nodal_loads=(('N2', -600., 0., 0.),))


@pytest.fixture
def options():
    return {'history_limits': design.FiberFrameHistoryLimits(.1, .01),
            'material_limits': design.FiberFrameMaterialHistoryLimits(.1, 1., 1.),
            'prices': design.FiberFrameMaterialPrices(100., 2., 'KRW', '2026-09-12', 'synthetic, not a quote')}


def candidate(name, width):
    return design.FiberFrameDesignCandidate(name, (design.FiberFrameSectionChange('RC1', width_m=width),))


def session(**kwargs):
    return reuse.RCControlResultSession(source_revision=SOURCE, scope_id='research', **kwargs)


def evaluate(s, model, control_request, options, path, **kwargs):
    return s.evaluate(model, control_request, scope_id='research', output_directory=path, **(options | kwargs))


def pool(values):
    return [{'candidate_id': name, 'material_estimate': {
        'total': cost, 'currency': 'KRW', 'scope': 'synthetic-control',
        'price_table_hash': 'sha256:' + 'a' * 64}} for name, cost in values.items()]


def test_bound_agrees_with_every_possible_completion():
    costs = {'baseline': 4., 'cheap': 2., 'equal': 2., 'costly': 7.}
    for assigned in itertools.product((None, False, True), repeat=4):
        outcomes = dict(zip(costs, assigned))
        bound = search.finite_pool_cost_bound(pool(costs), outcomes)
        unknown = [name for name in costs if outcomes[name] is None]
        assert bound['unverified_response_candidate_ids'] == sorted(unknown)
        if bound['status'] == 'pool_minimum_confirmed':
            # This tests the price theorem against every still-possible physical
            # outcome; it does not manufacture a structural verification.
            for fill in itertools.product((False, True), repeat=len(unknown)):
                complete = outcomes | dict(zip(unknown, fill))
                minimum = min(costs[name] for name in costs if complete[name])
                assert bound['pool_minimum_feasible_estimate'] == minimum
        else:
            assert bound['pool_minimum_feasible_estimate'] is None


@pytest.mark.parametrize('unknown_cost,confirmed,ties_known', [(1.,False,None),(2.,True,False),(3.,True,True)])
def test_cheaper_unknown_blocks_but_ties_and_expensive_unknown_are_explicit(unknown_cost, confirmed, ties_known):
    bound = search.finite_pool_cost_bound(pool({'baseline':2.,'other':unknown_cost}), {'baseline':True,'other':None})
    assert (bound['status']=='pool_minimum_confirmed') is confirmed
    assert bound['response_coverage_complete'] is False
    assert bound['all_minimum_cost_ties_verified'] is ties_known
    assert bound['global_design_optimality_proved'] is False


def test_zero_cost_ties_are_valid_without_division():
    b=search.finite_pool_cost_bound(pool({'baseline':0.,'tie':0.}), {'baseline':True,'tie':None})
    assert b['pool_minimum_feasible_estimate']==0
    assert b['all_minimum_cost_ties_verified'] is False


@pytest.mark.parametrize('value',[True,False,None,'1',float('nan'),float('inf'),-1.])
def test_invalid_costs_reject(value):
    with pytest.raises(ValueError):
        search.finite_pool_cost_bound(pool({'baseline':value}), {'baseline':True})


@pytest.mark.parametrize('value',[0,1,'false',[],{}])
def test_nonboolean_outcomes_reject(value):
    with pytest.raises(ValueError):
        search.finite_pool_cost_bound(pool({'baseline':1.}), {'baseline':value})


@pytest.mark.parametrize('field',['currency','scope','price_table_hash'])
def test_cost_basis_mismatch_reject(field):
    rows=pool({'baseline':1.,'other':2.})
    rows[1]['material_estimate'][field]='different'
    with pytest.raises(ValueError, match='cost bases'):
        search.finite_pool_cost_bound(rows, {'baseline':True,'other':None})


@pytest.mark.parametrize('mode',['empty','duplicate','missing-baseline','missing-outcome','extra-outcome'])
def test_pool_coverage_reject(mode):
    rows=pool({'baseline':1.})
    outcomes={'baseline':True}
    if mode=='empty':
        rows=[]
    if mode=='duplicate':
        rows=rows+rows
    if mode=='missing-baseline':
        rows=pool({'other':1.})
        outcomes={'other':True}
    if mode=='missing-outcome':
        outcomes={}
    if mode=='extra-outcome':
        outcomes['other']=False
    with pytest.raises(ValueError):
        search.finite_pool_cost_bound(rows,outcomes)


def test_real_reprice_rescreen_and_immutable_originals(model, control_request, options, tmp_path):
    s=session()
    first=evaluate(s,model,control_request,options,tmp_path/'fresh')
    assert first['row']['full_reference_verification_pass'] is True
    assert first['new_work']['known_counters']['attempted_step_count']==8  # preload + 3, twice
    assert first['fresh_reference_verification_this_call'] is True
    original={role:(tmp_path/'fresh'/meta['path']).read_bytes() for role,meta in first['row']['artifacts'].items()}
    original_result=json.loads(original['result'])
    assert len(original_result['response_history'])==3
    second=evaluate(s,model,control_request,options,tmp_path/'repriced',
        prices=replace(options['prices'],concrete_per_m3=150.),allow_new_analysis=False)
    assert second['mode']=='verified_original_reused'
    assert second['new_work']['api_invocation_count']==0
    assert all(v==0 for v in second['new_work']['known_counters'].values())
    assert second['fresh_reference_verification_this_call'] is False
    assert second['row']['invocations']==[]
    assert second['original_work_not_recharged']==first['new_work']
    assert second['row']['material_estimate']['total']-first['row']['material_estimate']['total']==pytest.approx(36.)
    for role,meta in second['row']['artifacts'].items():
        assert (tmp_path/'repriced'/meta['path']).read_bytes()==original[role]
    value=first['row']['performance']['maximum_absolute_fiber_strain']
    third=evaluate(s,model,control_request,options,tmp_path/'rescreen',
        history_limits=design.FiberFrameHistoryLimits(.1,value*.5),allow_new_analysis=False)
    assert third['row']['full_reference_verification_pass'] is True
    assert third['row']['selection_eligible'] is False
    assert third['new_work']['api_invocation_count']==0
    # Caller mutation cannot rewrite the internal snapshot.
    second['row']['performance']['maximum_absolute_fiber_strain']=999.
    fourth=evaluate(s,model,control_request,options,tmp_path/'again',allow_new_analysis=False)
    assert fourth['row']['performance']['maximum_absolute_fiber_strain']==value
    assert s.retained_bytes>0


@pytest.mark.parametrize('change',['load','targets','tolerance','material','section','source-provenance'])
def test_changed_physics_needs_new_analysis(model, control_request, options, tmp_path, change):
    s=session()
    evaluate(s,model,control_request,options,tmp_path/'first')
    if change=='load':
        control_request=replace(control_request,constant_nodal_loads=(('N2',-601.,0.,0.),))
    if change=='targets':
        control_request=replace(control_request,targets_m=(1e-5,3e-5,-1e-5))
    if change=='tolerance':
        control_request=replace(control_request,solver_config=replace(control_request.solver_config,newton=replace(control_request.solver_config.newton,residual_tolerance=2e-8)))
    if change=='material':
        model.materials[0]['yield_stress_mpa']=251.
    if change=='section':
        model=design.apply_fiber_frame_section_changes(model,candidate('wider',.5))
    if change=='source-provenance':
        model=replace(model,source_path='another-original.json')
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(s,model,control_request,options,tmp_path/'miss',allow_new_analysis=False)
    assert not (tmp_path/'miss').exists()


def test_forced_fresh_and_new_session_do_not_inherit_credit(model,control_request,options,tmp_path):
    s=session()
    first=evaluate(s,model,control_request,options,tmp_path/'first')
    fresh=evaluate(s,model,control_request,options,tmp_path/'forced',fresh=True)
    assert fresh['new_work']==first['new_work']
    assert fresh['mode']=='fresh_reference_and_replay'
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(session(),model,control_request,options,tmp_path/'new-process-equivalent',allow_new_analysis=False)
    s.clear()
    assert s.retained_bytes==0
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(s,model,control_request,options,tmp_path/'cleared',allow_new_analysis=False)


def test_scope_and_source_change_reject_before_output(model,control_request,options,tmp_path,monkeypatch):
    s=session()
    evaluate(s,model,control_request,options,tmp_path/'first')
    with pytest.raises(ValueError,match='ownership'):
        s.evaluate(model,control_request,scope_id='another-user-label',output_directory=tmp_path/'foreign',**options)
    assert not (tmp_path/'foreign').exists()
    monkeypatch.setattr(reuse,'_runtime_fingerprint',lambda:'changed-source-or-runtime')
    with pytest.raises(ValueError,match='source/runtime'):
        evaluate(s,model,control_request,options,tmp_path/'changed')
    assert not (tmp_path/'changed').exists()


def test_corrupt_memory_entry_is_not_used(model,control_request,options,tmp_path):
    s=session()
    first=evaluate(s,model,control_request,options,tmp_path/'first')
    key=first['physics_key']
    s._entries[key]=replace(s._entries[key],row_bytes=b'{}')
    with pytest.raises(ValueError,match='integrity'):
        evaluate(s,model,control_request,options,tmp_path/'corrupt')
    assert not (tmp_path/'corrupt').exists()


def test_small_cache_limit_does_not_truncate_or_claim_reuse(model,control_request,options,tmp_path):
    s=session(max_bytes=1)
    result=evaluate(s,model,control_request,options,tmp_path/'first')
    assert result['row']['status']=='verified'
    assert result['retained_for_reuse'] is False
    assert s.retained_bytes==0
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(s,model,control_request,options,tmp_path/'miss',allow_new_analysis=False)


def test_lru_evicts_without_exceeding_bound(model,control_request,options,tmp_path):
    s=session(max_entries=1)
    a=evaluate(s,model,control_request,options,tmp_path/'a')
    evaluate(s,design.apply_fiber_frame_section_changes(model,candidate('wide',.5)),control_request,options,tmp_path/'b')
    assert len(s._entries)==1 and a['physics_key'] not in s._entries
    assert s.retained_bytes<=64*1024*1024


@pytest.mark.parametrize('field,value',[('max_entries',True),('max_entries',0),('max_entries',129),('max_bytes',False),('max_bytes',0),('max_bytes',2**31)])
def test_invalid_retention_limits_reject(field,value):
    with pytest.raises(ValueError):
        session(**{field:value})


def test_existing_output_never_overwritten(model,control_request,options,tmp_path):
    target=tmp_path/'existing'
    target.mkdir()
    (target/'sentinel').write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        evaluate(session(),model,control_request,options,target)
    assert (target/'sentinel').read_bytes()==b'preserve'


def test_failed_verification_is_exported_but_not_cached(model,control_request,options,tmp_path,monkeypatch):
    s=session()
    original=reference._evaluate_design_row
    def failed(*args,**kwargs):
        row=original(*args,**kwargs)
        row['full_reference_verification_pass']=False
        row['status']='verification_blocked'
        row['selection_eligible']=False
        return row
    # Explicit fault injection AFTER a real solve. Not a physical validation.
    monkeypatch.setattr(reference,'_evaluate_design_row',failed)
    report=evaluate(s,model,control_request,options,tmp_path/'failed')
    assert report['row']['status']=='verification_blocked'
    assert s.retained_bytes==0
    assert (tmp_path/'failed/evaluation.json').exists()
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(s,model,control_request,options,tmp_path/'no-hit',allow_new_analysis=False)


def test_real_search_matches_fresh_exhaustive_and_skips_expensive(model,control_request,options,tmp_path):
    choices=(candidate('cheap',.35),candidate('middle',.45),candidate('costly',.5))
    s=session()
    report=search.run_rc_control_cost_search(model,choices,control_request,session=s,scope_id='research',
        output_directory=tmp_path/'search',max_new_model_analyses=2,**options)
    oracle=reference.compare_rc_control_designs(model,choices,control_request,source_revision=SOURCE,
        output_directory=tmp_path/'oracle',**options)
    assert report['status']=='pool_minimum_confirmed'
    assert report['cost_bound']['selected_candidate_id']==oracle['selected_candidate_id']=='cheap'
    assert report['new_model_evaluations']==2
    assert report['new_work']['known_counters']['attempted_step_count']==16
    assert sum(i['work']['attempted_step_count'] for r in oracle['rows'] for i in r['invocations'])==32
    assert report['cost_bound']['unverified_response_candidate_ids']==['costly','middle']
    assert report['cost_bound']['response_coverage_complete'] is False
    # A second local repricing run uses only the two verified originals.
    again=search.run_rc_control_cost_search(model,choices,control_request,session=s,scope_id='research',
        output_directory=tmp_path/'again',max_new_model_analyses=0,
        **(options|{'prices':replace(options['prices'],concrete_per_m3=200.)}))
    assert again['status']=='pool_minimum_confirmed'
    assert again['new_model_evaluations']==0 and again['reused_model_evaluations']==2
    assert again['new_work']['api_invocation_count']==0


def test_budget_does_not_call_unknown_cheaper_infeasible(model,control_request,options,tmp_path):
    choices=(candidate('cheap',.35),candidate('costly',.5))
    report=search.run_rc_control_cost_search(model,choices,control_request,session=session(),scope_id='research',
        output_directory=tmp_path/'limited',max_new_model_analyses=1,**options)
    assert report['status']=='cheaper_outcomes_unknown'
    assert report['cost_bound']['pool_minimum_feasible_estimate'] is None
    assert report['outcomes']['cheap'] is None
    assert report['new_model_evaluations']==1


def test_known_constraint_failure_and_unchecked_ties(model,control_request,options,tmp_path):
    choices=(candidate('cheap',.35),design.FiberFrameDesignCandidate('same', (design.FiberFrameSectionChange('RC1',cover_m=.045),)),candidate('expensive',.5))
    s=session()
    base=evaluate(s,model,control_request,options,tmp_path/'base')
    low=design.apply_fiber_frame_section_changes(model,choices[0])
    c=evaluate(s,low,control_request,options,tmp_path/'low')
    a=base['row']['performance']['maximum_absolute_fiber_strain']
    b=c['row']['performance']['maximum_absolute_fiber_strain']
    assert b>a
    report=search.run_rc_control_cost_search(model,choices,control_request,session=s,scope_id='research',
        output_directory=tmp_path/'screened',max_new_model_analyses=0,
        **(options|{'history_limits':design.FiberFrameHistoryLimits(.1,(a+b)/2)}))
    assert report['status']=='pool_minimum_confirmed'
    assert report['outcomes']['cheap'] is False
    assert report['cost_bound']['selected_candidate_id']=='baseline'
    assert report['cost_bound']['all_minimum_cost_ties_verified'] is False
    assert report['outcomes']['same'] is None


@pytest.mark.parametrize('budget',[True,-1,18,1.5,'2'])
def test_bad_budget_rejects_before_output(model,control_request,options,tmp_path,budget):
    with pytest.raises(ValueError):
        search.run_rc_control_cost_search(model,(candidate('cheap',.35),),control_request,
            session=session(),scope_id='research',output_directory=tmp_path/'bad',max_new_model_analyses=budget,**options)
    assert not (tmp_path/'bad').exists()


@pytest.mark.parametrize('order',[('cheap',),('cheap','cheap'),['cheap','costly'],('costly','unknown')])
def test_invalid_schedule_rejects(model,control_request,options,tmp_path,order):
    with pytest.raises(ValueError):
        search.run_rc_control_cost_search(model,(candidate('cheap',.35),candidate('costly',.5)),control_request,
            session=session(),scope_id='research',output_directory=tmp_path/'bad',candidate_order=order,**options)
    assert not (tmp_path/'bad').exists()


def test_no_budget_leaves_all_unverified(model,control_request,options,tmp_path):
    report=search.run_rc_control_cost_search(model,(candidate('cheap',.35),),control_request,
        session=session(),scope_id='research',output_directory=tmp_path/'zero',max_new_model_analyses=0,**options)
    assert report['status']=='no_verified_selection'
    assert report['new_model_evaluations']==0
    assert all(v is None for v in report['outcomes'].values())


def test_source_context_and_originals_are_frozen_in_plan(model,control_request,options,tmp_path):
    report=search.run_rc_control_cost_search(model,(candidate('cheap',.35),candidate('costly',.5)),control_request,
        session=session(),scope_id='research',output_directory=tmp_path/'plan',candidate_order=('costly','cheap'),**options)
    plan=json.loads((tmp_path/'plan/plan.json').read_bytes())
    h=plan.pop('plan_hash')
    assert reference._sha(reference._bytes(plan))==h==report['plan_hash']
    assert plan['evaluation_order']==['baseline','costly','cheap']
    assert plan['request']['constant_nodal_loads'][0]['FX_kN']==-600.
    assert plan['source_revision_is_attestation'] is False
    assert report['claims']['exhaustive_oracle_executed'] is False


def test_unknown_work_stops_scheduling_and_stays_unverified(model,control_request,options,tmp_path,monkeypatch):
    original=reuse.RCControlResultSession.evaluate
    def unknown(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        result['new_work']['unknown_work']=True
        result['row']['full_reference_verification_pass']=False
        return result
    monkeypatch.setattr(reuse.RCControlResultSession,'evaluate',unknown)
    result=search.run_rc_control_cost_search(model,(candidate('cheap',.35),candidate('costly',.5)),control_request,
        session=session(),scope_id='research',output_directory=tmp_path/'stop',**options)
    assert result['status']=='unknown_work_stop'
    assert result['new_model_evaluations']==1
    assert all(v is None for v in result['outcomes'].values())
    assert all(r['status']=='not_run_after_unknown_numerical_work' for r in result['records'][1:])


def experiment_file(path, options, concrete=None):
    from dataclasses import asdict
    prices=options['prices'] if concrete is None else replace(options['prices'],concrete_per_m3=concrete)
    value={'schema_version':'rc-fiber-design-experiment.v3',
           'candidates':[{'candidate_id':'cheap','changes':[{'section_id':'RC1','width_m':.35}]},
                         {'candidate_id':'costly','changes':[{'section_id':'RC1','width_m':.5}]}],
           'prices':asdict(prices),'terminal_limits':None,
           'history_limits':asdict(options['history_limits']),
           'material_history_limits':asdict(options['material_limits'])}
    path.write_text(json.dumps(value))
    return path


def test_cli_repricing_scenarios_share_one_global_budget(control_request,options,tmp_path,capsys):
    req=tmp_path/'request.json'
    req.write_bytes(reference._bytes(control_request.to_dict()))
    first=experiment_file(tmp_path/'one.json',options)
    second=experiment_file(tmp_path/'two.json',options,200.)
    result=cli.main(['--model',str(ROOT/'examples/public_rc_fiber_frame_cantilever.json'),
        '--request',str(req),'--experiment',str(first),'--experiment',str(second),
        '--source-revision',SOURCE,'--max-new-model-analyses','2','--output',str(tmp_path/'batch')])
    assert result==0
    summary=json.loads(capsys.readouterr().out)
    assert summary['remaining_new_model_budget']==0
    assert summary['requested_scenario_count']==2
    assert [r['new_model_evaluations'] for r in summary['scenarios']]==[2,0]
    assert summary['scenarios'][1]['reused_model_evaluations']==2
    assert summary['scenarios'][1]['new_work']['api_invocation_count']==0
    assert summary['persistent_cache'] is False
    assert json.loads((tmp_path/'batch/batch.json').read_bytes())==summary


def test_cli_rejects_ambiguous_model_before_output(control_request,options,tmp_path,capsys):
    req=tmp_path/'request.json'
    req.write_bytes(reference._bytes(control_request.to_dict()))
    exp=experiment_file(tmp_path/'exp.json',options)
    bad=tmp_path/'duplicate.json'
    bad.write_bytes(b'{"nodes": [], "nodes": []}')
    result=cli.main(['--model',str(bad),'--request',str(req),'--experiment',str(exp),
                    '--source-revision',SOURCE,'--output',str(tmp_path/'out')])
    assert result==1
    assert 'failed' in capsys.readouterr().err
    assert not (tmp_path/'out').exists()


def test_reused_result_does_not_suppress_fresh_scientific_comparison(model,control_request,options,tmp_path):
    s=session()
    evaluate(s,model,control_request,options,tmp_path/'cache')
    report=reference.compare_rc_control_designs(model,(candidate('cheap',.35),),control_request,
        source_revision=SOURCE,output_directory=tmp_path/'scientific',**options)
    assert report['schema_version']=='experimental-rc-control-design-comparison.v1'
    assert all(len(row['invocations'])==2 for row in report['rows'])
    assert all(row['full_reference_verification_pass'] for row in report['rows'])
    assert sum(i['work']['attempted_step_count'] for row in report['rows'] for i in row['invocations'])==16


def test_concurrent_identical_evaluations_do_not_duplicate_solve(model,control_request,options,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s=session()
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures=[workers.submit(evaluate,s,model,control_request,options,tmp_path/f'thread-{i}') for i in range(2)]
        results=[f.result() for f in futures]
    assert sorted(r['mode'] for r in results)==['fresh_reference_and_replay','verified_original_reused']
    assert sum(r['new_work']['api_invocation_count'] for r in results)==2


def test_unknown_work_is_not_cached(model,control_request,options,tmp_path,monkeypatch):
    original=reference._evaluate_design_row
    def unknown(*args,**kwargs):
        row=original(*args,**kwargs)
        row['invocations'][0]['unknown_execution_work']=True
        return row
    monkeypatch.setattr(reference,'_evaluate_design_row',unknown)
    s=session()
    result=evaluate(s,model,control_request,options,tmp_path/'uncounted')
    assert result['new_work']['unknown_work'] is True
    assert s.retained_bytes==0
    assert result['retained_for_reuse'] is False


def test_unknown_work_alone_cannot_confirm_incumbent(model, control_request, options, tmp_path, monkeypatch):
    """Fault injection retains a good response but removes work certainty only."""
    original = reference._evaluate_design_row

    def uncounted(*args, **kwargs):
        row = original(*args, **kwargs)
        assert row['full_reference_verification_pass'] is True
        row['invocations'][0]['unknown_execution_work'] = True
        return row

    monkeypatch.setattr(reference, '_evaluate_design_row', uncounted)
    result = search.run_rc_control_cost_search(
        model, (candidate('costly', .5),), control_request,
        session=session(), scope_id='research', output_directory=tmp_path/'unknown', **options)
    assert result['status'] == 'unknown_work_stop'
    assert result['cost_bound']['pool_minimum_feasible_estimate'] is None
    assert result['cost_bound']['selected_candidate_id'] is None
    assert result['outcomes'] == {'baseline': None, 'costly': None}
    assert result['records'][1]['status'] == 'not_run_after_unknown_numerical_work'


def test_publication_failure_never_admits_fresh_cache(model, control_request, options, tmp_path, monkeypatch):
    original = reference._save

    def fail_report(root, relative, data):
        if relative == 'evaluation.json':
            raise OSError('injected final report publication failure')
        return original(root, relative, data)

    s = session()
    with monkeypatch.context() as scoped:
        scoped.setattr(reference, '_save', fail_report)
        with pytest.raises(OSError, match='publication'):
            evaluate(s, model, control_request, options, tmp_path/'publication-failed')
    assert s.retained_bytes == 0
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(s, model, control_request, options, tmp_path/'no-credit', allow_new_analysis=False)
    assert not (tmp_path/'no-credit').exists()


def test_real_zero_price_baseline_confirms_minimum_without_tie_claim(model, control_request, options, tmp_path):
    zero = replace(options['prices'], concrete_per_m3=0.0, rebar_per_kg=0.0)
    result = search.run_rc_control_cost_search(
        model, (candidate('alternative', .5),), control_request,
        session=session(), scope_id='research', output_directory=tmp_path/'zero-prices',
        **(options | {'prices': zero}))
    assert result['new_model_evaluations'] == 1
    assert result['status'] == 'pool_minimum_confirmed'
    assert result['cost_bound']['pool_minimum_feasible_estimate'] == 0.0
    assert result['cost_bound']['all_minimum_cost_ties_verified'] is False
    assert result['cost_bound']['response_coverage_complete'] is False


@pytest.mark.parametrize('field,value', [
    ('fresh', 0), ('fresh', 'false'), ('allow_new_analysis', 1), ('allow_new_analysis', None),
])
def test_execution_options_require_booleans(model, control_request, options, tmp_path, field, value):
    with pytest.raises(ValueError, match='boolean'):
        evaluate(session(), model, control_request, options, tmp_path/'bad-option', **{field: value})
    assert not (tmp_path/'bad-option').exists()
