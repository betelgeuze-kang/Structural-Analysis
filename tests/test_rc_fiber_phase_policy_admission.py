"""Authored phase bounds cannot silently default, coerce or change a job."""
from copy import deepcopy

import pytest

from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.rc_fiber_job_contract import rc_fiber_job_resume_contract_hash
from structural_analysis.execution.rc_fiber_phase_policy import RCFiberPhasePolicy
from tests.test_rc_fiber_durable_worker import _request, _service, _submit


@pytest.mark.parametrize('field', ['analysis_timeout_ms', 'verification_timeout_ms', 'termination_grace_ms'])
@pytest.mark.parametrize('value', [True, 1.0, '1', 0, -1, 3600001, None])
def test_invalid_authored_phase_bounds_reject_before_payload_write(tmp_path, field, value):
    service = _service(tmp_path)
    request = _request()
    policy = RCFiberPhasePolicy(10000, 10000, 50).to_dict()
    policy[field] = value
    request['execution_config']['phase_execution_policy'] = policy
    with pytest.raises(JobServiceError):
        _submit(service, request)
    assert not [p for p in (tmp_path/'blobs').rglob('*') if p.is_file()]


def test_authored_policy_is_part_of_idempotency_and_restart_identity(tmp_path):
    service = _service(tmp_path)
    request = _request()
    request['execution_config']['phase_execution_policy'] = RCFiberPhasePolicy(10000, 10000, 50).to_dict()
    accepted = _submit(service, request)
    assert _submit(service, deepcopy(request)) == accepted
    changed = deepcopy(request)
    changed['execution_config']['phase_execution_policy']['analysis_timeout_ms'] += 1
    assert rc_fiber_job_resume_contract_hash(changed) != rc_fiber_job_resume_contract_hash(request)
    with pytest.raises(JobServiceError, match='idempotency_conflict'):
        _submit(service, changed)
