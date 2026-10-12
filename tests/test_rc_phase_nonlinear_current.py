"""Layered nonlinear reversal through actual isolated durable API phases."""
import json
from pathlib import Path
import sys

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import BoundedRCFiberDirectControlRequest
from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy
from tests.test_rc_fiber_durable_worker import TENANT_AUTH, _claim, _evidence, _native, _request, _run, _service, _submit
from tests.test_rc_nonlinear_reversal_integration import SEARCH, TARGETS
from tests.test_rc_pin_roller_main import beam


def nonlinear_request(chunk_size, isolated):
    request = _request(chunk_size=chunk_size)
    request['schema_version'] = 'structural-analysis-job-request.v4'
    request['model'] = beam()
    layers = json.loads((Path(__file__).parents[1]/'examples/public_rc_fiber_frame_explicit_layers.json').read_text())
    request['model'].update({key: layers[key] for key in ('materials', 'sections')})
    for material in request['model']['materials']:
        if material['type'] == 'bilinear_combined_hardening_steel':
            material['yield_stress_mpa'] = 4.0 if material['id'] == 'steel' else 8.0
    request['config'] = BoundedRCFiberDirectControlRequest(
        10, TARGETS, allow_reversals=True, maximum_reversals=3,
        experimental_pin_roller_beam=True, solver_config=SEARCH).to_dict()
    if isolated:
        request['execution_config']['phase_execution_policy'] = RCFiberPhasePolicy(300000, 300000, 100).to_dict()
    return request


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux phase isolation')
def test_damaged_yielded_reversal_exact_across_isolated_full_and_restart(tmp_path):
    terminal = []
    for name, chunk_size, isolated in [('inline', 14, False), ('isolated', 14, True), ('split', 11, True)]:
        root = tmp_path/name
        service = _service(root)
        job = _submit(service, nonlinear_request(chunk_size, isolated))
        chunks = (len(TARGETS)+chunk_size-1)//chunk_size
        for _ in range(chunks):
            service = _service(root)
            job = _run(service, _claim(service))
        assert job.status == 'succeeded'
        result = json.loads(service.read_result(job.job_id, **TENANT_AUTH))
        assert result['completed_target_count'] == len(TARGETS)
        evidence = _evidence(service, job.job_id, **TENANT_AUTH)
        assert evidence['pending_ordinals'] == []
        assert len(evidence['records']) == 2*chunks
        for item in evidence['records']:
            assert item['outcome']['status'] == 'returned'
            if item['outcome']['phase'] == 'verification':
                assert item['outcome']['verification_report']['contract_pass']
                assert item['outcome']['verification_report']['fresh_source_execution_invoked']
        terminal.append(_native(result))
    assert terminal[0] == terminal[1] == terminal[2]
    def values(obj, key):
        if isinstance(obj, dict):
            if key in obj:
                yield obj[key]
            for value in obj.values():
                yield from values(value, key)
        elif isinstance(obj, list):
            for value in obj:
                yield from values(value, key)
    checkpoint = json.loads(terminal[0])
    assert max(values(checkpoint, 'tensile_damage')) > .03
    assert max(values(checkpoint, 'accumulated_plastic_strain')) > 2e-4
