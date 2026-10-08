"""Rejected stores release owned SQLite handles while diagnostics remain alive."""

import os
from pathlib import Path
import sqlite3

import pytest

from structural_analysis.execution import job_service
from structural_analysis.execution.job_service import DurableJobService, JobServiceError


def open_store(root):
    return DurableJobService(
        root,
        tenant_tokens={"tenant": "tenant-token-0123456789"},
        worker_tokens={"worker": "worker-token-0123456789"},
    )


def retained_store_descriptors(root):
    found = []
    for descriptor in Path("/proc/self/fd").iterdir():
        try:
            target = os.readlink(descriptor)
        except FileNotFoundError:
            continue
        if target.startswith(str(root.resolve()) + "/"):
            found.append(target)
    return found


@pytest.mark.skipif(not Path('/proc/self/fd').is_dir(), reason="Linux FD observation")
def test_repeated_corrupt_store_rejection_releases_handles_without_gc(tmp_path):
    root = tmp_path / "corrupt"
    root.mkdir()
    database = root / "jobs.sqlite3"
    original = b"not a sqlite database" * 100
    database.write_bytes(original)
    errors = []
    for _ in range(8):
        try:
            open_store(root)
        except JobServiceError as error:
            assert error.code == "job_database_open_failed"
            errors.append(error)  # Retain traceback/diagnostics as a caller may.
        else:
            pytest.fail("corrupt database accepted")
    assert len(errors) == 8
    assert database.read_bytes() == original
    assert retained_store_descriptors(root) == []


@pytest.mark.parametrize("failing_statement", [1, 2, 3])
def test_each_connection_setup_failure_closes_owned_connection(
    tmp_path, monkeypatch, failing_statement
):
    connections = []

    class FailingConnection(sqlite3.Connection):
        statements = 0

        def execute(self, *args, **kwargs):
            self.statements += 1
            if self.statements == failing_statement:
                raise sqlite3.DatabaseError("synthetic setup failure")
            return super().execute(*args, **kwargs)

    connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs, factory=FailingConnection)
        connections.append(connection)
        return connection

    monkeypatch.setattr(job_service.sqlite3, "connect", tracked_connect)
    with pytest.raises(JobServiceError, match="job_database_open_failed"):
        open_store(tmp_path / "store")
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].cursor()


def test_failed_connect_preserves_database_error_without_owned_connection(
    tmp_path, monkeypatch
):
    def failed_connect(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic open refusal")

    monkeypatch.setattr(job_service.sqlite3, "connect", failed_connect)
    with pytest.raises(JobServiceError, match="job_database_open_failed"):
        open_store(tmp_path / "store")


def test_successful_connection_remains_usable_until_transaction_returns(tmp_path):
    service = open_store(tmp_path / "store")
    with service._transaction() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.cursor()
