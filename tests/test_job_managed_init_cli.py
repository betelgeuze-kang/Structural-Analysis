"""Operator initialization and fresh-runtime authentication on managed stores."""

import json
import sqlite3
import subprocess
import sys

import pytest

from structural_analysis.execution import job_managed_init_cli as initializer
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)
from tests.test_job_execution_authority_service import service
from tests.test_rc_real_process_lifecycle import request, tenant, worker

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux managed store")


def test_cli_initializes_and_fresh_runtime_performs_real_rc_job(tmp_path):
    root, authority = tmp_path / "store", tmp_path / "authority"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.execution.job_managed_init_cli",
            str(root),
            str(authority),
            "--maximum-blob-bytes",
            "10000000",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "initialized"
    assert receipt["service_started"] is False
    assert receipt["credentials_persisted"] is False
    assert receipt["jobs_submitted"] == 0
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    current = service(root)  # Real runtime credentials, unrelated to initialization.
    job = current.submit_job(
        **tenant(), idempotency_key="actual-runtime", request=request()
    )
    for expected in ("checkpointed", "succeeded"):
        current = service(root)
        claim = current.claim_next(**worker("first"), lease_seconds=60)
        assert (
            execute_rc_fiber_direct_control_claim(
                current, claim, **worker("first"), lease_seconds=60
            ).status
            == expected
        )
    evidence = current.read_rc_invocation_evidence(job.job_id, **tenant())
    assert evidence["execution_budget"]["reserved_attempts"] == 4
    assert evidence["pending_ordinals"] == []


def test_initialization_does_not_persist_temporary_credentials(tmp_path, monkeypatch):
    token = "ephemeral-initialization-test-only-0123456789"
    monkeypatch.setattr(initializer.secrets, "token_urlsafe", lambda n: token)
    root = tmp_path / "store"
    receipt = initializer.initialize_managed_store(
        root, tmp_path / "authority", maximum_blob_bytes=1_000_000
    )
    assert token not in json.dumps(receipt)
    for path in root.rglob("*"):
        if path.is_file():
            assert token.encode() not in path.read_bytes()
    with sqlite3.connect(root / "jobs.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


@pytest.mark.parametrize("managed", [False, True])
def test_existing_store_is_preserved_without_creating_another_authority(
    tmp_path, managed
):
    root = tmp_path / "store"
    if managed:
        initializer.initialize_managed_store(
            root, tmp_path / "authority", maximum_blob_bytes=1_000_000
        )
    else:
        service(root)
    before = (root / "jobs.sqlite3").read_bytes()
    other = tmp_path / "other-authority"
    with pytest.raises(ValueError, match="new store root"):
        initializer.initialize_managed_store(root, other, maximum_blob_bytes=1_000_000)
    assert not other.exists()
    assert (root / "jobs.sqlite3").read_bytes() == before


@pytest.mark.parametrize("budget", [0, -1, True, 2**63])
def test_invalid_budget_does_not_create_state(tmp_path, budget):
    with pytest.raises(ValueError, match="positive integer blob budget"):
        initializer.initialize_managed_store(
            tmp_path / "store", tmp_path / "authority", maximum_blob_bytes=budget
        )
    assert list(tmp_path.iterdir()) == []


def test_failed_enrollment_preserves_created_authority(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("simulated store initialization interruption")

    monkeypatch.setattr(initializer, "DurableJobService", unavailable)
    authority = tmp_path / "authority"
    with pytest.raises(OSError, match="simulated store initialization interruption"):
        initializer.initialize_managed_store(
            tmp_path / "store", authority, maximum_blob_bytes=1_000_000
        )
    before = (authority / "authority.sqlite3").read_bytes()
    with pytest.raises(FileExistsError):
        initializer.initialize_managed_store(
            tmp_path / "store", authority, maximum_blob_bytes=1_000_000
        )
    assert (authority / "authority.sqlite3").read_bytes() == before
