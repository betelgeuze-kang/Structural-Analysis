"""Explicit single-host activation of a verified managed-store restoration.

The external generation commits before the destination binding. A crash in
between fences both stores; retrying with the same sealed backup and destination
completes the binding. No execution, lease rewrite or budget refund occurs here.
"""

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3

from .job_execution_authority import (
    ExecutionAuthorityError,
    ExecutionBinding,
    JobExecutionAuthority,
)
from .job_store_backup import (
    BACKUP_PENDING,
    RESTORE_PENDING,
    _Budget,
    _backup_inventory,
    _database_checks,
    _safe,
    _sync_directory,
    verify_job_store_backup,
)


def _binding(db):
    if db.execute("PRAGMA application_id").fetchone() != (1380140373,):
        raise ValueError("managed backup required")
    rows = db.execute(
        "SELECT directory, identity, generation, root FROM job_execution_authority_binding"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("invalid managed binding")
    directory, identity, generation, root = rows[0]
    if type(generation) is not int or not 1 <= generation < 2**63 - 1:
        raise ValueError("invalid managed generation")
    return directory, ExecutionBinding(identity, generation, root)


def _verify_restored_bytes(root, files, budget):
    for name, expected in files.items():
        path = root / name
        _safe(path)
        if path.stat().st_size != expected["bytes"]:
            raise ValueError("restored member differs")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while data := stream.read(65536):
                budget.check(len(data))
                budget.used += len(data)
                size += len(data)
                digest.update(data)
        if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
            raise ValueError("restored member differs")


def activate_managed_restore(
    source,
    destination,
    *,
    manifest_sha256,
    maximum_bytes,
    maximum_files=10000,
    timeout_seconds=60,
    expected_generation=None,
    expected_root=None,
):
    """Activate or finish the same interrupted activation; never recreate authority.

    Bounds cover each verification pass separately, with one overall deadline.
    Already activated returns binding confirmation only, not a fresh integrity
    qualification of a store which may since have executed jobs.
    """
    budget = _Budget(maximum_bytes, maximum_files, timeout_seconds)
    verify_job_store_backup(
        source,
        manifest_sha256=manifest_sha256,
        maximum_bytes=maximum_bytes,
        maximum_files=maximum_files,
        timeout_seconds=timeout_seconds,
    )
    budget.check()
    source, destination = Path(source).absolute(), Path(destination).absolute()
    _safe(source, directory=True)
    _safe(destination, directory=True)
    source, destination = source.resolve(), destination.resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError("separate backup and restored roots required")
    files = _backup_inventory(source, manifest_sha256, budget)
    with closing(
        sqlite3.connect(
            (source / "jobs.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True
        )
    ) as db:
        directory, snapshot = _binding(db)
    authority = JobExecutionAuthority(directory)
    previous = snapshot
    if (expected_generation is None) != (expected_root is None):
        raise ValueError("expected generation and root must be supplied together")
    if expected_generation is not None:
        if (
            type(expected_generation) is not int
            or not snapshot.generation <= expected_generation < 2**63 - 1
        ):
            raise ValueError("invalid expected generation")
        previous = ExecutionBinding(
            snapshot.authority_id, expected_generation, authority._root(expected_root)
        )
    root = authority._root(destination)
    if root == previous.root:
        raise ValueError("restoration must use a distinct root")
    following = ExecutionBinding(previous.authority_id, previous.generation + 1, root)
    for name in (
        BACKUP_PENDING,
        RESTORE_PENDING,
        ".job-store-authority.pending",
        "backup-manifest.json",
    ):
        path = destination / name
        if path.exists() or path.is_symlink():
            raise ValueError("incomplete or sealed destination")
    for name in (
        "jobs.sqlite3",
        "jobs.sqlite3-journal",
        "jobs.sqlite3-wal",
        "jobs.sqlite3-shm",
    ):
        path = destination / name
        if path.exists() or path.is_symlink():
            _safe(path)
    _safe(destination / "jobs.sqlite3")
    with authority._lock(exclusive=True):
        with authority._connection() as db:
            try:
                authority._require(db, previous)
                moved = False
            except ExecutionAuthorityError:
                authority._require(db, following)
                moved = True
        # Opening rw permits SQLite's own hot-journal recovery after interruption.
        # Cooperating source/target writers are excluded by the authority lock.
        with closing(
            sqlite3.connect(
                (destination / "jobs.sqlite3").as_uri() + "?mode=rw",
                uri=True,
                timeout=0,
            )
        ) as target:
            target.set_progress_handler(lambda: _deadline_expired(budget), 1000)
            target.execute("PRAGMA synchronous=FULL")
            target.execute("BEGIN IMMEDIATE")
            target_directory, target_binding = _binding(target)
            if target_directory != directory:
                raise ValueError("restored authority differs")
            if moved and target_binding == following:
                budget.check()
                _sync_directory(destination)
                return {
                    "status": "already_activated",
                    "generation": following.generation,
                    "service_started": False,
                    "application_integrity_checked": False,
                }
            if target_binding != snapshot:
                raise ValueError("restored binding differs from sealed backup")
            _verify_restored_bytes(destination, files, budget)
            _database_checks(destination, files, budget)
            budget.check()
            if not moved:
                with authority._connection() as db:
                    authority._require(db, previous)
                    db.execute(
                        "UPDATE authority SET generation=?, root=? WHERE singleton=1",
                        (following.generation, following.root),
                    )
            # From this point the old root is fenced even if this commit fails.
            target.execute(
                "UPDATE job_execution_authority_binding SET generation=?, root=? WHERE singleton=1",
                (following.generation, following.root),
            )
            target.commit()
        _sync_directory(destination)
    return {
        "status": "activated",
        "generation": following.generation,
        "service_started": False,
        "application_integrity_checked": False,
    }


def _deadline_expired(budget):
    import time

    return int(time.monotonic() >= budget.deadline)
