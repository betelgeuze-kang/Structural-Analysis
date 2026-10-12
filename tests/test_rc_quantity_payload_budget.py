"""Quantity report persistence shares the durable root's retained-byte cap."""

import pytest

from structural_analysis.execution.job_service import JobServiceError
from tests.test_job_blob_payload_budget import capped, used
from tests.test_rc_fiber_quantity_report_service import (
    completed as completed_fixture,
    create,
    numerical_state,
    prices,
    read,
)


@pytest.fixture
def completed_report(tmp_path, monkeypatch):
    return completed_fixture.__wrapped__(tmp_path, monkeypatch)


def test_quantity_revision_denial_preserves_originals_and_existing_report(completed_report):
    service, job = completed_report
    reference = create(service, job)
    original = read(service, job, reference)
    retained = used(service.root)
    before = numerical_state(service, job)
    capped(service.root, retained)
    # An instance predating policy adoption must enforce it too.
    assert create(service, job) == reference
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        create(service, job, prices())
    assert used(service.root) == retained
    assert numerical_state(service, job) == before
    assert read(service, job, reference) == original


def test_quantity_write_works_with_inherited_available_capacity(completed_report):
    service, job = completed_report
    retained = used(service.root)
    capped(service.root, retained + 1024 * 1024)
    reopened = capped(service.root, None)
    reference = create(reopened, job, prices())
    raw = read(reopened, job, reference)
    assert used(service.root) == retained + len(raw)
    assert create(service, job, prices()) == reference
