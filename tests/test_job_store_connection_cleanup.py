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
            # Existing stores are rejected by the read-only authority preflight,
            # before the writable connection setup can begin.
            assert error.code == "execution_authority_invalid"
            assert isinstance(error.__cause__, sqlite3.DatabaseError)
            errors.append(error)  # Retain traceback/diagnostics as a caller may.
        else:
            pytest.fail("corrupt database accepted")
    assert len(errors) == 8
    assert database.read_bytes() == original
    assert not database.with_name("jobs.sqlite3-wal").exists()
    assert not database.with_name("jobs.sqlite3-shm").exists()
    assert retained_store_descriptors(root) == []


@pytest.mark.parametrize("failing_statement", [1, 2, 3, 4])
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


@pytest.mark.parametrize("failing_statement", [1, 2])
def test_readonly_authority_preflight_failure_closes_connection(
    tmp_path, monkeypatch, failing_statement
):
    root = tmp_path / "legacy"
    root.mkdir()
    database = root / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE legacy (value INTEGER)")
    connection.commit()
    connection.close()
    original = database.read_bytes()
    connections = []
    calls = []
    connect = sqlite3.connect

    class FailingReadConnection(sqlite3.Connection):
        statements = 0

        def execute(self, *args, **kwargs):
            self.statements += 1
            if self.statements == failing_statement:
                raise sqlite3.DatabaseError("synthetic read-only preflight failure")
            return super().execute(*args, **kwargs)

    def tracked_connect(*args, **kwargs):
        calls.append((args, kwargs.copy()))
        connection = connect(*args, **kwargs, factory=FailingReadConnection)
        connections.append(connection)
        return connection

    monkeypatch.setattr(job_service.sqlite3, "connect", tracked_connect)
    with pytest.raises(JobServiceError, match="execution_authority_invalid") as error:
        open_store(root)
    assert isinstance(error.value.__cause__, sqlite3.DatabaseError)
    assert len(connections) == 1
    assert calls[0][0] == (database.as_uri() + "?mode=ro",)
    assert calls[0][1] == {"uri": True}
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].cursor()
    assert database.read_bytes() == original
    assert not database.with_name("jobs.sqlite3-wal").exists()
    assert not database.with_name("jobs.sqlite3-shm").exists()
