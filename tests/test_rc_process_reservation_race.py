"""Real-process RC claim/reservation races within one durable store."""

import multiprocessing

from structural_analysis.execution.job_service import JobServiceError
from tests.test_rc_real_process_lifecycle import request, service, tenant, worker


def _contender(root, barrier, outputs, operation, job_id, lease_token):
    current = service(root)
    barrier.wait(timeout=30)
    if operation == "claim":
        claim = current.claim_next(**worker("first"), lease_seconds=60)
        outputs.put(None if claim is None else (claim.job.job_id, claim.lease_token))
        return
    reserved, rejected = [], []
    for _ in range(3):
        try:
            reserved.append(
                current.reserve_execution_attempt(
                    job_id, **worker("first"), lease_token=lease_token
                )
            )
        except JobServiceError as error:
            rejected.append(error.code)
    outputs.put((reserved, rejected))


def _race(root, operation, job_id=None, lease_token=None):
    # Spawn fresh interpreters: no inherited connection or in-process lock can
    # serialize the workers on behalf of the durable service.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(4)
    outputs = context.Queue()
    processes = [
        context.Process(
            target=_contender,
            args=(root, barrier, outputs, operation, job_id, lease_token),
        )
        for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        results = [outputs.get(timeout=45) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        return results
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(timeout=10)
        outputs.close()
        outputs.join_thread()


def test_rc_claim_and_budget_are_atomic_across_processes(tmp_path):
    current = service(tmp_path)
    job = current.submit_job(
        **tenant(), idempotency_key="process-race", request=request()
    )
    claims = _race(tmp_path, "claim")
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    job_id, lease_token = winners[0]
    assert job_id == job.job_id
    results = _race(tmp_path, "reserve", job_id, lease_token)
    ordinals = sorted(ordinal for reserved, _ in results for ordinal in reserved)
    rejections = [error for _, errors in results for error in errors]
    assert ordinals == list(range(1, 9))
    assert rejections == ["execution_attempt_budget_exhausted"] * 4
    # Reopening must retain reservations, including work not actually executed.
    reopened = service(tmp_path)
    assert reopened.read_execution_budget(
        job_id, **worker("first"), lease_token=lease_token
    ) == {"maximum_attempts": 8, "reserved_attempts": 8, "remaining_attempts": 0}
