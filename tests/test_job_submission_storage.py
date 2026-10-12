"""Rejected idempotency conflicts must not accumulate request payloads."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from structural_analysis.execution.job_service import JobServiceError
from tests.test_rc_fiber_durable_worker import TENANT_AUTH, _request, _service


def payloads(root):
    return {p.relative_to(root): p.read_bytes()
            for p in (root / "blobs").rglob("*") if p.is_file()}


def test_conflicting_retries_leave_store_payloads_unchanged(tmp_path):
    service = _service(tmp_path)
    request = _request()
    job = service.submit_job(**TENANT_AUTH, idempotency_key="same", request=request)
    before = payloads(tmp_path)
    for index in range(8):
        with pytest.raises(JobServiceError) as exc:
            service.submit_job(**TENANT_AUTH, idempotency_key="same",
                               request=request | {"case_id": f"rejected-{index}"})
        assert exc.value.code == "idempotency_conflict"
    assert payloads(tmp_path) == before
    assert service.get_job(job.job_id, **TENANT_AUTH) == job
    assert service.validate_integrity(job.job_id, **TENANT_AUTH)["contract_pass"]


def test_simultaneous_distinct_requests_persist_only_winner(tmp_path):
    services = [_service(tmp_path) for _ in range(4)]
    barrier = Barrier(len(services))

    def submit(index):
        barrier.wait(timeout=10)
        try:
            return services[index].submit_job(
                **TENANT_AUTH, idempotency_key="race",
                request=_request() | {"case_id": f"racer-{index}"})
        except JobServiceError as exc:
            assert exc.code == "idempotency_conflict"
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(submit, range(4)))
    winners = [job for job in outcomes if job is not None]
    assert len(winners) == 1
    assert len(payloads(tmp_path)) == 1
    assert services[0].validate_integrity(winners[0].job_id, **TENANT_AUTH)["contract_pass"]


def test_exact_retry_preserves_missing_payload_repair_and_corruption_rejection(tmp_path):
    service = _service(tmp_path)
    request = _request()
    kwargs = dict(TENANT_AUTH, idempotency_key="retry", request=request)
    job = service.submit_job(**kwargs)
    path = next(p for p in (tmp_path / "blobs").rglob("*") if p.is_file())
    original = path.read_bytes()
    path.unlink()
    assert service.submit_job(**kwargs) == job
    assert path.read_bytes() == original
    path.write_bytes(b"corrupt")
    with pytest.raises(JobServiceError):
        service.submit_job(**kwargs)
    assert path.read_bytes() == b"corrupt"
