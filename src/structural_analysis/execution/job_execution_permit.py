"""Pinned same-host job locks; metadata lives in the caller's durable database.

Only explicit initialization creates a namespace. Registration creates a new
job's persistent lock file; existing pins are never repaired or recreated.
Callers own database transactions and must keep the returned permit through
publication, child cleanup and heartbeat shutdown. Inherited descriptors share
its flock: close handles, never explicitly unlock them. This is cooperating
Linux/local-filesystem custody, not hostile-operator or distributed fencing.
"""

import errno
import os
from pathlib import Path
import re
import stat
import sys


class ExecutionPermitError(ValueError):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def _fail(kind, detail):
    raise ExecutionPermitError(f"job_execution_permit_{kind}", detail)


_NAMESPACE_COLUMNS = ("namespace_key", "directory", "device", "inode")
_JOB_COLUMNS = ("namespace_key", "job_id", "request_hash", "device", "inode")


def _require_schema(db):
    for table, columns in (
        ("job_execution_permit_namespaces", _NAMESPACE_COLUMNS),
        ("job_execution_permit_jobs", _JOB_COLUMNS),
    ):
        rows = db.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            _fail("migration_required", "Pinned permit metadata is absent.")
        primary_keys = (
            (1, 0, 0, 0) if columns == _NAMESPACE_COLUMNS else (1, 2, 0, 0, 0)
        )
        if (
            tuple(row[1] for row in rows) != columns
            or any(row[2] != "TEXT" or row[3] != 1 for row in rows)
            or tuple(row[5] for row in rows) != primary_keys
        ):
            _fail("invalid", "Pinned permit metadata schema differs.")


def create_execution_permit_schema(db):
    """Explicit fresh-state schema creation; never migrate existing metadata."""
    existing = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('job_execution_permit_namespaces', 'job_execution_permit_jobs')"
        )
    }
    if existing:
        _fail("migration_required", "Permit schema creation requires fresh state.")
    db.execute(
        "CREATE TABLE job_execution_permit_namespaces ("
        "namespace_key TEXT NOT NULL PRIMARY KEY, directory TEXT NOT NULL, "
        "device TEXT NOT NULL, inode TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE job_execution_permit_jobs ("
        "namespace_key TEXT NOT NULL, job_id TEXT NOT NULL, request_hash TEXT NOT NULL, "
        "device TEXT NOT NULL, inode TEXT NOT NULL, PRIMARY KEY(namespace_key, job_id), "
        "FOREIGN KEY(namespace_key) REFERENCES job_execution_permit_namespaces(namespace_key))"
    )


def _key(namespace_key):
    if (
        type(namespace_key) is not str
        or re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", namespace_key) is None
    ):
        _fail("invalid", "Invalid permit namespace identity.")


def _job(job_id, request_hash):
    if type(job_id) is not str or re.fullmatch(r"job_[0-9a-f]{32}", job_id) is None:
        _fail("invalid", "Invalid permit job identity.")
    if (
        type(request_hash) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", request_hash) is None
    ):
        _fail("invalid", "Invalid permit request identity.")


def _directory(directory):
    if sys.platform != "linux":
        _fail("unavailable", "Execution permits require Linux.")
    path = Path(directory)
    if not path.is_absolute() or ".." in path.parts:
        _fail("invalid", "Permit directory must be an absolute canonical path.")
    return path


def _pin(value):
    return str(value.st_dev), str(value.st_ino)


def _valid_pin(device, inode):
    for value, minimum in ((device, 0), (inode, 1)):
        if (
            type(value) is not str
            or re.fullmatch(r"0|[1-9][0-9]{0,19}", value) is None
            or not minimum <= int(value) <= 2**64 - 1
        ):
            _fail("invalid", "Permit inode metadata is invalid.")


def _walk_directory(path):
    """Open every component without following symlinks, retaining the final fd."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            following = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _check_directory_path(path, fd, expected=None):
    observed, named = os.fstat(fd), os.stat(path, follow_symlinks=False)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or observed.st_nlink < 1
        or _pin(observed) != _pin(named)
        or (expected is not None and _pin(observed) != expected)
    ):
        _fail("invalid", "Permit namespace inode differs from its retained pin.")
    return _pin(observed)


def initialize_execution_permit_namespace(db, *, directory, namespace_key):
    """Create and pin one fresh namespace; preserve partial creation on failure."""
    _require_schema(db)
    _key(namespace_key)
    path = _directory(directory)
    if (
        db.execute(
            "SELECT 1 FROM job_execution_permit_namespaces WHERE namespace_key=?",
            (namespace_key,),
        ).fetchone()
        is not None
    ):
        _fail("migration_required", "Permit namespace is already initialized.")
    parent = fd = None
    try:
        parent = _walk_directory(path.parent)
        os.mkdir(path.name, mode=0o700, dir_fd=parent)
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent,
        )
        device, inode = _check_directory_path(path, fd)
        os.fsync(fd)
        os.fsync(parent)
        db.execute(
            "INSERT INTO job_execution_permit_namespaces VALUES (?, ?, ?, ?)",
            (namespace_key, str(path), device, inode),
        )
    except FileExistsError as error:
        raise ExecutionPermitError(
            "job_execution_permit_migration_required",
            "Unregistered permit namespace already exists; preserve it.",
        ) from error
    except OSError as error:
        raise ExecutionPermitError(
            "job_execution_permit_unavailable", "Permit namespace unavailable."
        ) from error
    finally:
        for descriptor in (fd, parent):
            if descriptor is not None:
                os.close(descriptor)


def _open_namespace(db, directory, namespace_key):
    _require_schema(db)
    _key(namespace_key)
    path = _directory(directory)
    row = db.execute(
        "SELECT directory, device, inode FROM job_execution_permit_namespaces "
        "WHERE namespace_key=?",
        (namespace_key,),
    ).fetchone()
    if row is None:
        _fail("migration_required", "Permit namespace pin is absent.")
    if type(row[0]) is not str or row[0] != str(path):
        _fail("invalid", "Permit namespace path differs from its retained binding.")
    _valid_pin(row[1], row[2])
    fd = _walk_directory(path)
    try:
        _check_directory_path(path, fd, (row[1], row[2]))
        return path, fd
    except BaseException:
        os.close(fd)
        raise


def validate_execution_permit_namespace(db, *, directory, namespace_key):
    try:
        _path, fd = _open_namespace(db, directory, namespace_key)
        os.close(fd)
    except OSError as error:
        raise ExecutionPermitError(
            "job_execution_permit_unavailable", "Pinned permit namespace unavailable."
        ) from error


def _check_job_path(directory, directory_fd, name, fd, expected=None):
    _check_directory_path(directory, directory_fd)
    observed = os.fstat(fd)
    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(observed.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or observed.st_nlink != 1
        or named.st_nlink != 1
        or _pin(observed) != _pin(named)
        or (expected is not None and _pin(observed) != expected)
    ):
        _fail("invalid", "Job permit inode/type/link count differs from its pin.")
    return _pin(observed)


def _registered_job(db, directory, namespace_key, job_id, request_hash):
    _job(job_id, request_hash)
    path, directory_fd = _open_namespace(db, directory, namespace_key)
    fd = None
    try:
        row = db.execute(
            "SELECT request_hash, device, inode FROM job_execution_permit_jobs "
            "WHERE namespace_key=? AND job_id=?",
            (namespace_key, job_id),
        ).fetchone()
        if row is None:
            _fail("migration_required", "Registered job permit pin is absent.")
        if row[0] != request_hash:
            _fail("invalid", "Job permit request identity differs.")
        _valid_pin(row[1], row[2])
        name = f"{job_id}.lock"
        fd = os.open(
            name,
            os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
        _check_job_path(path, directory_fd, name, fd, (row[1], row[2]))
        return path, directory_fd, name, fd, (row[1], row[2])
    except BaseException:
        for descriptor in (fd, directory_fd):
            if descriptor is not None:
                os.close(descriptor)
        raise


def validate_execution_permit_registration(
    db, *, directory, namespace_key, job_id, request_hash
):
    try:
        _path, directory_fd, _name, fd, _expected = _registered_job(
            db, directory, namespace_key, job_id, request_hash
        )
        os.close(fd)
        os.close(directory_fd)
    except OSError as error:
        raise ExecutionPermitError(
            "job_execution_permit_unavailable", "Registered job permit unavailable."
        ) from error


def register_execution_permit(db, *, directory, namespace_key, job_id, request_hash):
    """Allocate a new job file/pin in the caller's transaction, or validate it."""
    _job(job_id, request_hash)
    _require_schema(db)
    if (
        db.execute(
            "SELECT 1 FROM job_execution_permit_jobs WHERE namespace_key=? AND job_id=?",
            (namespace_key, job_id),
        ).fetchone()
        is not None
    ):
        return validate_execution_permit_registration(
            db,
            directory=directory,
            namespace_key=namespace_key,
            job_id=job_id,
            request_hash=request_hash,
        )
    directory_fd = fd = None
    try:
        path, directory_fd = _open_namespace(db, directory, namespace_key)
        name = f"{job_id}.lock"
        fd = os.open(
            name,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        device, inode = _check_job_path(path, directory_fd, name, fd)
        os.fsync(fd)
        os.fsync(directory_fd)
        db.execute(
            "INSERT INTO job_execution_permit_jobs VALUES (?, ?, ?, ?, ?)",
            (namespace_key, job_id, request_hash, device, inode),
        )
    except FileExistsError as error:
        raise ExecutionPermitError(
            "job_execution_permit_migration_required",
            "Unregistered job lock exists; preserve it rather than adopting it.",
        ) from error
    except OSError as error:
        raise ExecutionPermitError(
            "job_execution_permit_unavailable", "New job permit unavailable."
        ) from error
    finally:
        for descriptor in (fd, directory_fd):
            if descriptor is not None:
                os.close(descriptor)


class ExecutionPermit:
    """Own a job lock and directory handle; yield a borrowed inheritable fd."""

    def __init__(self, fd, directory_fd):
        self._fd, self._directory_fd = fd, directory_fd

    @property
    def fd(self):
        if self._fd is None:
            _fail("unavailable", "Execution permit is already closed.")
        return self._fd

    def fileno(self):
        return self.fd

    def close(self):
        handles = self._fd, self._directory_fd
        self._fd = self._directory_fd = None
        for descriptor in handles:
            if descriptor is not None:
                os.close(descriptor)

    def __enter__(self):
        return self.fd

    def __exit__(self, *_exc):
        self.close()


def acquire_execution_permit(db, *, directory, namespace_key, job_id, request_hash):
    """Acquire immediately; caller releases its DB transaction before execution."""
    if sys.platform != "linux":
        _fail("unavailable", "Execution permits require Linux.")
    import fcntl

    directory_fd = fd = None
    try:
        path, directory_fd, name, fd, expected = _registered_job(
            db, directory, namespace_key, job_id, request_hash
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EACCES):
                raise ExecutionPermitError(
                    "job_execution_permit_busy", "Another execution owns this job."
                ) from error
            raise
        _check_job_path(path, directory_fd, name, fd, expected)
        result = ExecutionPermit(fd, directory_fd)
        fd = directory_fd = None
        return result
    except OSError as error:
        raise ExecutionPermitError(
            "job_execution_permit_unavailable", "Pinned job permit unavailable."
        ) from error
    finally:
        for descriptor in (fd, directory_fd):
            if descriptor is not None:
                os.close(descriptor)
