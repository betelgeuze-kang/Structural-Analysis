"""Current-source full and restarted numerical paths through isolated phases."""
import json
import sys

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy
from tests.test_rc_fiber_durable_worker import (
    TENANT_AUTH, _claim, _evidence, _native, _request, _run, _service, _submit,
)


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux phase isolation')
def test_current_full_and_restarted_isolated_results_match_inline(tmp_path, monkeypatch):
    results = []
    for name, chunk_size, isolated in [('inline', 3, False), ('isolated', 3, True),
                                       ('restarted', 1, True)]:
        root = tmp_path / name
        request = _request(chunk_size=chunk_size)
        if isolated:
            request['execution_config']['phase_execution_policy'] = RCFiberPhasePolicy(
                30000, 30000, 100).to_dict()
        service = _service(root)
        job = _submit(service, request)
        with monkeypatch.context() as patch:
            if isolated:
                def forbidden(*args, **kwargs):
                    pytest.fail('isolated numerics must not execute in parent')
                patch.setattr(api, 'analyze_bounded_rc_fiber_direct_control', forbidden)
                patch.setattr(api, 'validate_bounded_rc_fiber_direct_control_artifacts', forbidden)
            for _ in range(3 // chunk_size):
                service = _service(root)
                job = _run(service, _claim(service))
        assert job.status == 'succeeded'
        evidence = _evidence(service, job.job_id, **TENANT_AUTH)
        assert len(evidence['records']) == 2 * (3 // chunk_size)
        for record in evidence['records']:
            outcome = record['outcome']
            assert outcome['status'] == 'returned'
            assert outcome['timing']['wall_ns'] > 0
            assert outcome['timing']['process_cpu_ns'] > 0
            if outcome['phase'] == 'verification':
                assert outcome['verification_report']['fresh_source_execution_invoked']
                assert outcome['verification_report']['contract_pass']
        results.append(json.loads(service.read_result(job.job_id, **TENANT_AUTH)))
    assert _native(results[0]) == _native(results[1]) == _native(results[2])
