"""Pinned primitive and real flock custody only; no API or source fingerprints."""

from contextlib import closing
from dataclasses import replace
import multiprocessing
import os
import sqlite3
import subprocess
import sys

import pytest

from structural_analysis.execution.job_execution_authority import (
    ExecutionAuthorityError,
    JobExecutionAuthority,
)
from structural_analysis.execution.job_execution_permit import (
    ExecutionPermitError,
    acquire_execution_permit,
    create_execution_permit_schema,
    initialize_execution_permit_namespace,
    register_execution_permit,
    validate_execution_permit_namespace,
    validate_execution_permit_registration,
)


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux flock custody")
JOB = "job_" + "a" * 32
OTHER_JOB = "job_" + "c" * 32
REQUEST = "sha256:" + "b" * 64


def local(tmp_path):
    database = tmp_path / "jobs.sqlite3"
    params = dict(
        directory=tmp_path / ".job-execution-permits",
        namespace_key="unmanaged:" + "d" * 64,
        job_id=JOB,
        request_hash=REQUEST,
    )
    with closing(sqlite3.connect(database)) as db:
        create_execution_permit_schema(db)
        initialize_execution_permit_namespace(
            db, directory=params["directory"], namespace_key=params["namespace_key"]
        )
        register_execution_permit(db, **params)
        db.commit()
    return database, params


def acquire(database, params):
    with closing(sqlite3.connect(database)) as db:
        return acquire_execution_permit(db, **params)


def assert_code(kind, call):
    with pytest.raises(ExecutionPermitError) as caught:
        call()
    assert caught.value.code == "job_execution_permit_" + kind


def hold_managed(directory, binding, ready, release):
    authority = JobExecutionAuthority(directory)
    with (
        authority.execution(binding),
        authority.execution_permit(binding, JOB, REQUEST),
    ):
        ready.set()
        assert release.wait(15)


def test_pins_are_durable_and_registration_is_stable_while_held(tmp_path):
    database, params = local(tmp_path)
    path = params["directory"] / f"{JOB}.lock"
    before = path.stat()
    with acquire(database, params) as fd:
        assert os.fstat(fd).st_ino == before.st_ino
        with closing(sqlite3.connect(database)) as db:
            register_execution_permit(db, **params)
            validate_execution_permit_registration(db, **params)
            row = db.execute(
                "SELECT request_hash,device,inode FROM job_execution_permit_jobs"
            ).fetchone()
            assert row == (REQUEST, str(before.st_dev), str(before.st_ino))
            namespace = db.execute(
                "SELECT directory,device,inode FROM job_execution_permit_namespaces"
            ).fetchone()
            stamp = params["directory"].stat()
            assert namespace == (
                str(params["directory"]),
                str(stamp.st_dev),
                str(stamp.st_ino),
            )
    assert path.stat().st_ino == before.st_ino
    assert params["directory"].stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600


def test_busy_is_immediate_distinct_and_has_no_database_mutation(tmp_path):
    database, params = local(tmp_path)
    with closing(sqlite3.connect(database)) as db:
        before = db.iterdump()
        before = tuple(before)
    with acquire(database, params):
        assert_code("busy", lambda: acquire(database, params))
        with closing(sqlite3.connect(database)) as db:
            assert tuple(db.iterdump()) == before
    with acquire(database, params):
        pass


def test_different_jobs_can_hold_exclusive_permits_concurrently(tmp_path):
    database, params = local(tmp_path)
    other = dict(params, job_id=OTHER_JOB)
    with closing(sqlite3.connect(database)) as db:
        register_execution_permit(db, **other)
        db.commit()
    with acquire(database, params), acquire(database, other):
        assert_code("busy", lambda: acquire(database, params))
        assert_code("busy", lambda: acquire(database, other))


def test_last_descriptor_close_releases_flock_without_unlocking_duplicate(tmp_path):
    database, params = local(tmp_path)
    permit = acquire(database, params)
    inherited = os.dup(permit.fd)
    permit.close()
    try:
        assert_code("busy", lambda: acquire(database, params))
        assert_code("unavailable", permit.fileno)
        permit.close()  # Repeated close cannot close a reused descriptor.
        assert_code("busy", lambda: acquire(database, params))
    finally:
        os.close(inherited)
    with acquire(database, params):
        pass


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_id", True),
        ("job_id", "../job_" + "a" * 32),
        ("request_hash", "b" * 64),
        ("request_hash", False),
        ("namespace_key", "../managed"),
        ("namespace_key", True),
    ],
)
def test_invalid_names_and_request_identity_are_rejected(tmp_path, field, value):
    database, params = local(tmp_path)
    changed = dict(params)
    changed[field] = value
    assert_code("invalid", lambda: acquire(database, changed))


def test_valid_other_request_cannot_change_registered_job_pin(tmp_path):
    database, params = local(tmp_path)
    changed = dict(params, request_hash="sha256:" + "e" * 64)
    with closing(sqlite3.connect(database)) as db:
        assert_code("invalid", lambda: register_execution_permit(db, **changed))
    assert_code("invalid", lambda: acquire(database, changed))
    with acquire(database, params):
        pass


@pytest.mark.parametrize("member", ["namespace", "job"])
def test_fresh_database_reader_rejects_replaced_inode_even_while_old_fd_held(
    tmp_path, member
):
    database, params = local(tmp_path)
    with acquire(database, params):
        path = params["directory"]
        if member == "job":
            path = path / f"{JOB}.lock"
            path.rename(tmp_path / "retained-old-job")
            path.touch()
        else:
            path.rename(tmp_path / "retained-old-namespace")
            path.mkdir()
        assert_code("invalid", lambda: acquire(database, params))


@pytest.mark.parametrize("member", ["namespace", "job"])
def test_existing_state_missing_file_is_not_recreated(tmp_path, member):
    database, params = local(tmp_path)
    path = params["directory"]
    if member == "job":
        path = path / f"{JOB}.lock"
        path.unlink()
    else:
        path.rename(tmp_path / "retained-namespace")
    with closing(sqlite3.connect(database)) as db:
        assert_code("unavailable", lambda: register_execution_permit(db, **params))
    assert not path.exists()


@pytest.mark.parametrize("member", ["namespace", "job"])
def test_symlinks_cannot_alias_a_pinned_namespace_or_job(tmp_path, member):
    database, params = local(tmp_path)
    path = params["directory"]
    if member == "job":
        path = path / f"{JOB}.lock"
    retained = tmp_path / "retained"
    path.rename(retained)
    path.symlink_to(retained, target_is_directory=member == "namespace")
    assert_code("unavailable", lambda: acquire(database, params))


def test_initialization_does_not_follow_an_ancestor_symlink(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(original, target_is_directory=True)
    with closing(sqlite3.connect(tmp_path / "jobs.sqlite3")) as db:
        create_execution_permit_schema(db)
        assert_code(
            "unavailable",
            lambda: initialize_execution_permit_namespace(
                db, directory=alias / "locks", namespace_key="local"
            ),
        )
    assert not (original / "locks").exists()


def test_hardlinked_job_lock_fails_closed(tmp_path):
    database, params = local(tmp_path)
    os.link(params["directory"] / f"{JOB}.lock", tmp_path / "other-link")
    assert_code("invalid", lambda: acquire(database, params))


@pytest.mark.parametrize("kind", ["fifo", "directory"])
def test_lock_file_type_is_regular_and_fifo_open_never_waits(tmp_path, kind):
    database, params = local(tmp_path)
    path = params["directory"] / f"{JOB}.lock"
    path.rename(tmp_path / "retained")
    if kind == "fifo":
        os.mkfifo(path)
        assert_code("invalid", lambda: acquire(database, params))
    else:
        path.mkdir()
        assert_code("unavailable", lambda: acquire(database, params))


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM job_execution_permit_namespaces",
        "DELETE FROM job_execution_permit_jobs",
        "DROP TABLE job_execution_permit_jobs",
    ],
)
def test_missing_pin_or_schema_is_explicit_migration_required(tmp_path, sql):
    database, params = local(tmp_path)
    with closing(sqlite3.connect(database)) as db:
        db.execute(sql)
        db.commit()
    assert_code("migration_required", lambda: acquire(database, params))
    assert (params["directory"] / f"{JOB}.lock").is_file()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE job_execution_permit_jobs SET inode='01'",
        "UPDATE job_execution_permit_jobs SET device='-1'",
        "UPDATE job_execution_permit_namespaces SET inode='18446744073709551616'",
        "UPDATE job_execution_permit_namespaces SET directory='relative'",
    ],
)
def test_malformed_pin_metadata_cannot_admit_execution(tmp_path, sql):
    database, params = local(tmp_path)
    with closing(sqlite3.connect(database)) as db:
        db.execute(sql)
        db.commit()
    assert_code("invalid", lambda: acquire(database, params))


def test_fresh_initialization_and_orphan_registration_never_adopt_or_repair(tmp_path):
    database, params = local(tmp_path)
    with closing(sqlite3.connect(database)) as db:
        assert_code("migration_required", lambda: create_execution_permit_schema(db))
        assert_code(
            "migration_required",
            lambda: initialize_execution_permit_namespace(
                db,
                directory=params["directory"],
                namespace_key=params["namespace_key"],
            ),
        )
        db.execute("DELETE FROM job_execution_permit_jobs")
        assert_code(
            "migration_required", lambda: register_execution_permit(db, **params)
        )
        db.rollback()
    with acquire(database, params):
        pass


def test_missing_schema_does_not_silently_initialize_existing_database(tmp_path):
    params = dict(directory=tmp_path / "locks", namespace_key="local")
    with closing(sqlite3.connect(tmp_path / "jobs.sqlite3")) as db:
        assert_code(
            "migration_required",
            lambda: validate_execution_permit_namespace(db, **params),
        )
        assert db.execute("SELECT name FROM sqlite_master").fetchall() == []
    assert not params["directory"].exists()


def test_managed_restore_reuses_pins_and_fences_old_generation(tmp_path):
    authority, old = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(old, JOB, REQUEST, 8)
    pin = (authority.permit_directory / f"{JOB}.lock").stat().st_ino
    restored = authority.activate(old, tmp_path / "restored")
    reopened = JobExecutionAuthority(authority.directory)
    assert reopened.register_job(restored, JOB, REQUEST, 8) == 0
    with reopened.execution_permit(restored, JOB, REQUEST):
        with pytest.raises(ExecutionAuthorityError, match="stale"):
            with authority.execution_permit(old, JOB, REQUEST):
                pytest.fail("stale generation admitted")
    assert (authority.permit_directory / f"{JOB}.lock").stat().st_ino == pin


def test_managed_busy_and_other_job_execution_cross_processes(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    authority.register_job(binding, OTHER_JOB, REQUEST, 8)
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    child = ctx.Process(
        target=hold_managed, args=(authority.directory, binding, ready, release)
    )
    child.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ExecutionPermitError, match="permit_busy"):
            with authority.execution_permit(binding, JOB, REQUEST):
                pytest.fail("overlapping job admitted")
        with authority.execution_permit(binding, OTHER_JOB, REQUEST):
            pass
        assert authority.read_budget(binding, JOB, REQUEST)["reserved_attempts"] == 0
        with pytest.raises(ExecutionAuthorityError, match="busy"):
            authority.activate(binding, tmp_path / "restored")
    finally:
        release.set()
        child.join(15)
        if child.is_alive():
            child.kill()
            child.join()
    assert child.exitcode == 0
    with authority.execution_permit(binding, JOB, REQUEST):
        pass


def test_inherited_job_and_generation_handles_outlive_parent_context_closes(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    child = None
    try:
        with (
            authority.execution(binding) as generation_fd,
            authority.execution_permit(binding, JOB, REQUEST) as job_fd,
        ):
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import os,sys; [os.fstat(int(x)) for x in sys.argv[1:]]; "
                    "print('ready',flush=True); sys.stdin.buffer.read(1)",
                    str(generation_fd),
                    str(job_fd),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                pass_fds=(generation_fd, job_fd),
            )
            assert child.stdout.readline() == b"ready\n"
        with pytest.raises(ExecutionPermitError, match="permit_busy"):
            with authority.execution_permit(binding, JOB, REQUEST):
                pytest.fail("inherited job permit released early")
        with pytest.raises(ExecutionAuthorityError, match="busy"):
            authority.activate(binding, tmp_path / "restored")
        child.stdin.close()
        assert child.wait(timeout=10) == 0
        with authority.execution_permit(binding, JOB, REQUEST):
            pass
        assert authority.activate(binding, tmp_path / "restored").generation == 2
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            for stream in (child.stdin, child.stdout):
                if not stream.closed:
                    stream.close()


def test_missing_managed_schema_requires_migration_and_pin_loss_never_refunds(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    assert authority.reserve(binding, JOB, REQUEST) == 1
    path = authority.permit_directory / f"{JOB}.lock"
    path.unlink()
    assert_code("unavailable", lambda: authority.reserve(binding, JOB, REQUEST))
    assert authority.read_budget(binding, JOB, REQUEST)["reserved_attempts"] == 1
    assert (
        authority.read_reservations(binding, JOB, REQUEST)["reservations"][0][
            "reserved_attempts"
        ]
        == 1
    )
    assert not path.exists()
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        assert db.execute(
            "SELECT spent FROM budgets WHERE job_id=?", (JOB,)
        ).fetchone() == (1,)
        db.execute("DROP TABLE job_execution_permit_jobs")
        db.commit()
    reopened = JobExecutionAuthority(authority.directory)
    with pytest.raises(ExecutionPermitError, match="migration_required"):
        with reopened.execution(binding):
            pytest.fail("old authority silently migrated")


def legacy_authority(tmp_path):
    """Remove only new state in a temporary fixture, leaving the old journal."""
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    authority.reserve(binding, JOB, REQUEST)
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        db.execute("DROP TABLE job_execution_permit_jobs")
        db.execute("DROP TABLE job_execution_permit_namespaces")
        db.commit()
    (authority.permit_directory / f"{JOB}.lock").unlink()
    authority.permit_directory.rmdir()
    return JobExecutionAuthority(authority.directory), binding


def test_legacy_managed_binding_and_journal_reads_create_nothing_and_do_not_spend(
    tmp_path,
):
    authority, binding = legacy_authority(tmp_path)
    database = authority.directory / "authority.sqlite3"
    before = database.read_bytes()
    inventory = sorted(path.name for path in authority.directory.iterdir())
    with authority.execution(binding) as fd:
        os.fstat(fd)
    assert authority.read_budget(binding, JOB, REQUEST) == {
        "maximum_attempts": 8,
        "reserved_attempts": 1,
        "remaining_attempts": 7,
        "adopted_reserved_attempts": 0,
    }
    reservations = authority.read_reservations(binding, JOB, REQUEST)
    assert reservations["budget"]["reserved_attempts"] == 1
    assert reservations["reservations"] == [
        {
            "reserved_attempts": 1,
            "maximum_attempts": 8,
            "authority_id": binding.authority_id,
            "authority_generation": binding.generation,
            "authority_root": binding.root,
            "execution_work": "unknown",
        }
    ]
    with pytest.raises(ExecutionPermitError, match="migration_required"):
        with authority.execution_permit(binding, JOB, REQUEST):
            pytest.fail("legacy job computation admitted")
    for mutation in (
        lambda: authority.reserve(binding, JOB, REQUEST),
        lambda: authority.register_job(binding, JOB, REQUEST, 8),
        lambda: authority.register_job(binding, OTHER_JOB, REQUEST, 8),
    ):
        assert_code("migration_required", mutation)
    assert sorted(path.name for path in authority.directory.iterdir()) == inventory
    assert not authority.permit_directory.exists()
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM reservations",
        "UPDATE reservations SET generation=99",
        "UPDATE reservations SET root='relative'",
        "UPDATE budgets SET spent=2",
    ],
)
def test_legacy_read_compatibility_still_rejects_corrupt_journals(tmp_path, sql):
    authority, binding = legacy_authority(tmp_path)
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        db.execute(sql)
        db.commit()
    for read in (authority.read_budget, authority.read_reservations):
        with pytest.raises(ExecutionAuthorityError, match="journal invalid"):
            read(binding, JOB, REQUEST)
    assert not authority.permit_directory.exists()


def test_legacy_read_compatibility_still_rejects_stale_binding(tmp_path):
    authority, binding = legacy_authority(tmp_path)
    stale = replace(binding, generation=binding.generation + 1)
    with pytest.raises(ExecutionAuthorityError, match="stale"):
        with authority.execution(stale):
            pytest.fail("stale generation admitted")
    for read in (authority.read_budget, authority.read_reservations):
        with pytest.raises(ExecutionAuthorityError, match="stale"):
            read(stale, JOB, REQUEST)
    assert not authority.permit_directory.exists()


def test_fresh_authority_namespace_replacement_is_not_treated_as_legacy_read(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    authority.permit_directory.rename(tmp_path / "retained-old-namespace")
    authority.permit_directory.mkdir()
    reopened = JobExecutionAuthority(authority.directory)
    for read in (reopened.read_budget, reopened.read_reservations):
        assert_code("invalid", lambda: read(binding, JOB, REQUEST))


def test_failed_job_pin_transaction_preserves_orphan_without_adopting_it(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        db.execute(
            "CREATE TRIGGER reject_job BEFORE INSERT ON budgets "
            "BEGIN SELECT RAISE(ABORT,'injected write failure'); END"
        )
        db.commit()
    with pytest.raises(ExecutionAuthorityError):
        authority.register_job(binding, JOB, REQUEST, 8)
    path = authority.permit_directory / f"{JOB}.lock"
    assert path.exists()
    with closing(sqlite3.connect(authority.directory / "authority.sqlite3")) as db:
        assert db.execute("SELECT * FROM budgets").fetchall() == []
        assert db.execute("SELECT * FROM job_execution_permit_jobs").fetchall() == []
        db.execute("DROP TRIGGER reject_job")
        db.commit()
    assert_code(
        "migration_required", lambda: authority.register_job(binding, JOB, REQUEST, 8)
    )
