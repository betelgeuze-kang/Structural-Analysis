"""Single-host execution authority outside copied job stores.

Service binding, reservation reconciliation and RC worker lifetime guards use
this primitive. Store activation/recovery is a separate explicit operation.
A caller must hold execution() for the entire computation and child-reaping lifetime,
not merely while reserving an invocation. No distributed or hostile-operator
fencing is provided. Missing state is never silently recreated.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import uuid


class ExecutionAuthorityError(ValueError):
    pass


def install_new_store(staging, destination):
    """Atomically install a completed Linux store without replacing any path."""
    import ctypes

    if sys.platform != "linux":
        raise ExecutionAuthorityError("atomic managed enrollment requires Linux")
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renameat2", None)
    if rename is None:
        raise ExecutionAuthorityError("atomic no-replace rename unavailable")
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(staging), -100, os.fsencode(destination), 1) != 0:
        raise ExecutionAuthorityError(
            "managed destination unavailable; preserve staged store"
        )


@dataclass(frozen=True)
class ExecutionBinding:
    authority_id: str
    generation: int
    root: str


def _integer(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise ExecutionAuthorityError("invalid authority integer")
    return value


class JobExecutionAuthority:
    def __init__(self, directory):
        if sys.platform != "linux":
            raise ExecutionAuthorityError("managed execution requires Linux")
        self.directory = Path(directory).absolute()

    def _root(self, root):
        root = Path(root).resolve()
        directory = self.directory.resolve()
        if root == directory or root in directory.parents or directory in root.parents:
            raise ExecutionAuthorityError("authority and store must be external")
        return str(root)

    @classmethod
    def create(cls, directory, root):
        authority = cls(directory)
        root = authority._root(root)
        # Explicit creation only, with no overwrite or partial-output cleanup.
        authority.directory.mkdir(mode=0o700)
        for name in ("authority.lock", "authority.sqlite3"):
            fd = os.open(
                authority.directory / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            os.fsync(fd)
            os.close(fd)
        identity = str(uuid.uuid4())
        with authority._connection() as db:
            db.executescript("""
                CREATE TABLE authority (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    identity TEXT NOT NULL, generation INTEGER NOT NULL,
                    root TEXT NOT NULL
                );
                CREATE TABLE budgets (
                    job_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                    maximum INTEGER NOT NULL, spent INTEGER NOT NULL,
                    adopted_spent INTEGER NOT NULL
                );
                CREATE TABLE reservations (
                    job_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    generation INTEGER NOT NULL, root TEXT NOT NULL,
                    PRIMARY KEY (job_id, ordinal)
                );
            """)
            db.execute("INSERT INTO authority VALUES (1, ?, 1, ?)", (identity, root))
        fd = os.open(authority.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return authority, ExecutionBinding(identity, 1, root)

    @contextmanager
    def _connection(self):
        path = self.directory / "authority.sqlite3"
        if self.directory.is_symlink() or path.is_symlink() or not path.is_file():
            raise ExecutionAuthorityError("authority unavailable")
        db = None
        try:
            db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except sqlite3.Error as exc:
            raise ExecutionAuthorityError(
                "authority database unavailable or invalid"
            ) from exc
        finally:
            if db is not None:
                db.close()

    @contextmanager
    def _lock(self, *, exclusive=False):
        import fcntl

        fd = None
        try:
            if self.directory.is_symlink():
                raise ExecutionAuthorityError("authority unavailable")
            fd = os.open(
                self.directory / "authority.lock",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ExecutionAuthorityError("authority lock is not a regular file")
            try:
                fcntl.flock(
                    fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
                )
            except BlockingIOError as exc:
                raise ExecutionAuthorityError(
                    "authority busy: execution or activation active"
                ) from exc
            yield fd
        except OSError as exc:
            raise ExecutionAuthorityError("authority lock unavailable") from exc
        finally:
            if fd is not None:
                os.close(fd)

    def _require(self, db, binding):
        if type(binding) is not ExecutionBinding:
            raise ExecutionAuthorityError("invalid execution binding")
        _integer(binding.generation, minimum=1)
        rows = db.execute("SELECT identity, generation, root FROM authority").fetchall()
        if len(rows) != 1 or rows[0] != (
            binding.authority_id,
            binding.generation,
            binding.root,
        ):
            raise ExecutionAuthorityError("stale or invalid execution binding")
        _integer(rows[0][1], minimum=1)
        if self._root(binding.root) != binding.root:
            raise ExecutionAuthorityError("noncanonical store binding")

    @contextmanager
    def execution(self, binding):
        """Hold through computation AND cleanup, yielding a borrowed lock fd.

        Managed numerical children must inherit this descriptor explicitly via
        subprocess pass_fds. Their descriptor keeps activation blocked even if
        the parent loses its own handle. This does not contain arbitrary escaped
        descendants and is not automatic integration with the phase supervisor.
        """
        with self._lock() as fd:
            with self._connection() as db:
                self._require(db, binding)
            yield fd

    def activate(self, binding, new_root):
        root = self._root(new_root)
        if root == binding.root:
            raise ExecutionAuthorityError(
                "activation requires a distinct restored root"
            )
        with self._lock(exclusive=True), self._connection() as db:
            self._require(db, binding)
            generation = _integer(binding.generation + 1, minimum=1)
            db.execute(
                "UPDATE authority SET generation=?, root=? WHERE singleton=1",
                (generation, root),
            )
        return ExecutionBinding(binding.authority_id, generation, root)

    def register_job(self, binding, job_id, request_hash, maximum, *, initial_spent=0):
        """Enroll immutable identity; an old snapshot cannot lower existing spend.

        initial_spent is for explicit adoption of an existing store. Integration
        must authenticate that source and serialize its writers before adoption.
        """
        if not isinstance(job_id, str) or not re.fullmatch(r"job_[0-9a-f]{32}", job_id):
            raise ExecutionAuthorityError("invalid job identity")
        if not isinstance(request_hash, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", request_hash
        ):
            raise ExecutionAuthorityError("invalid request identity")
        _integer(maximum, minimum=1)
        _integer(initial_spent)
        if initial_spent > maximum:
            raise ExecutionAuthorityError("initial spend exceeds limit")
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            row = db.execute(
                "SELECT request_hash, maximum, spent FROM budgets WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO budgets VALUES (?, ?, ?, ?, ?)",
                    (job_id, request_hash, maximum, initial_spent, initial_spent),
                )
                return initial_spent
            if row[:2] != (request_hash, maximum):
                raise ExecutionAuthorityError("immutable job authority mismatch")
            _integer(row[1], minimum=1)
            spent = _integer(row[2])
            if not initial_spent <= spent <= maximum:
                raise ExecutionAuthorityError(
                    "authority spend inconsistent with source"
                )
            self._budget(db, binding, job_id, request_hash)
            return spent

    def _budget(self, db, binding, job_id, request_hash):
        row = db.execute(
            "SELECT request_hash, maximum, spent, adopted_spent FROM budgets WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None or row[0] != request_hash:
            raise ExecutionAuthorityError("unknown or mismatched job authority")
        maximum = _integer(row[1], minimum=1)
        spent, adopted = _integer(row[2]), _integer(row[3])
        if not adopted <= spent <= maximum:
            raise ExecutionAuthorityError("authority reservation journal invalid")
        records = db.execute(
            "SELECT ordinal, generation, root FROM reservations WHERE job_id=? ORDER BY ordinal",
            (job_id,),
        ).fetchall()
        if len(records) != spent - adopted:
            raise ExecutionAuthorityError("authority reservation journal invalid")
        for ordinal, (stored, generation, root) in enumerate(records, adopted + 1):
            if (
                _integer(stored, minimum=1) != ordinal
                or not 1 <= _integer(generation, minimum=1) <= binding.generation
                or not isinstance(root, str)
                or self._root(root) != root
            ):
                raise ExecutionAuthorityError("authority reservation journal invalid")
        return {
            "maximum_attempts": maximum,
            "reserved_attempts": spent,
            "remaining_attempts": maximum - spent,
            "adopted_reserved_attempts": adopted,
        }

    def read_budget(self, binding, job_id, request_hash):
        """Read checked reservations, never infer completed numerical work."""
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            return self._budget(db, binding, job_id, request_hash)

    def read_reservations(self, binding, job_id, request_hash):
        """Return one checked snapshot without inventing adoption or lease history."""
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            budget = self._budget(db, binding, job_id, request_hash)
            records = db.execute(
                "SELECT ordinal, generation, root FROM reservations WHERE job_id=? ORDER BY ordinal",
                (job_id,),
            ).fetchall()
            return {
                "budget": budget,
                "reservations": [
                    {
                        "reserved_attempts": ordinal,
                        "maximum_attempts": budget["maximum_attempts"],
                        "authority_id": binding.authority_id,
                        "authority_generation": generation,
                        "authority_root": root,
                        "execution_work": "unknown",
                    }
                    for ordinal, generation, root in records
                ],
            }

    def reserve(self, binding, job_id, request_hash):
        """Commit spend BEFORE local recording or computation; never refund it."""
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            budget = self._budget(db, binding, job_id, request_hash)
            maximum, spent = budget["maximum_attempts"], budget["reserved_attempts"]
            if spent >= maximum:
                raise ExecutionAuthorityError("execution budget exhausted or invalid")
            db.execute("UPDATE budgets SET spent=? WHERE job_id=?", (spent + 1, job_id))
            db.execute(
                "INSERT INTO reservations VALUES (?, ?, ?, ?)",
                (job_id, spent + 1, binding.generation, binding.root),
            )
        return spent + 1
