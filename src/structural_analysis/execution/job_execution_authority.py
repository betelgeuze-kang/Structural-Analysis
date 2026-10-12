"""Single-host execution authority outside copied job stores.

Service binding, reservation reconciliation and RC worker lifetime guards use
this primitive. Store activation/recovery is a separate explicit operation.
A caller must hold execution() for the entire computation and child-reaping lifetime,
not merely while reserving an invocation. No distributed or hostile-operator
fencing is provided. Missing state is never silently recreated.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import uuid

from .job_execution_permit import (
    acquire_execution_permit,
    create_execution_permit_schema,
    initialize_execution_permit_namespace,
    register_execution_permit,
    validate_execution_permit_namespace,
    validate_execution_permit_registration,
)


class ExecutionAuthorityError(ValueError):
    pass


def _credit_hash(value, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ExecutionAuthorityError("invalid ordinal credit digest")
    return value


def _credit_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _ordinal_credit_schema(db):
    names = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('ordinal_credit_budgets','ordinal_credit_reservations')"
        )
    }
    if names and len(names) != 2:
        raise ExecutionAuthorityError("partial ordinal credit namespace")
    if not names:
        db.execute(
            "CREATE TABLE ordinal_credit_budgets (job_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, context_hash TEXT NOT NULL, production_max INTEGER NOT NULL, verification_max INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE ordinal_credit_reservations (job_id TEXT NOT NULL, credit_ordinal INTEGER NOT NULL, api_ordinal INTEGER NOT NULL, phase TEXT NOT NULL, ceiling INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, PRIMARY KEY(job_id,credit_ordinal), UNIQUE(job_id,api_ordinal))"
        )


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
        self.permit_directory = self.directory / "job-execution-permits"

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
            create_execution_permit_schema(db)
            initialize_execution_permit_namespace(
                db, directory=authority.permit_directory, namespace_key="managed"
            )
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
        # Older authorities remain readable without constructing permit state.
        # Once either new table exists, validate the complete pinned namespace:
        # a partial schema or replaced namespace must not become a legacy read.
        if (
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE name IN "
                "('job_execution_permit_namespaces', 'job_execution_permit_jobs')"
            ).fetchone()
            is not None
        ):
            validate_execution_permit_namespace(
                db, directory=self.permit_directory, namespace_key="managed"
            )

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

    @contextmanager
    def execution_permit(self, binding, job_id, request_hash):
        """Hold one job exclusively without retaining the authority transaction.

        Busy acquisition never changes a lease or reserves an invocation. The
        caller must separately inherit the generation execution() descriptor and
        this descriptor into numerical children, and retain both until cleanup.
        """
        permit = None
        with self._lock():
            try:
                with self._connection() as db:
                    self._require(db, binding)
                    self._budget(db, binding, job_id, request_hash)
                    permit = acquire_execution_permit(
                        db,
                        directory=self.permit_directory,
                        namespace_key="managed",
                        job_id=job_id,
                        request_hash=request_hash,
                    )
                yield permit.fd
            finally:
                if permit is not None:
                    permit.close()

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
                register_execution_permit(
                    db,
                    directory=self.permit_directory,
                    namespace_key="managed",
                    job_id=job_id,
                    request_hash=request_hash,
                )
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

    def _budget(self, db, binding, job_id, request_hash, *, require_permit=True):
        row = db.execute(
            "SELECT request_hash, maximum, spent, adopted_spent FROM budgets WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None or row[0] != request_hash:
            raise ExecutionAuthorityError("unknown or mismatched job authority")
        if require_permit:
            validate_execution_permit_registration(
                db,
                directory=self.permit_directory,
                namespace_key="managed",
                job_id=job_id,
                request_hash=request_hash,
            )
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
            return self._budget(db, binding, job_id, request_hash, require_permit=False)

    def read_reservations(self, binding, job_id, request_hash):
        """Return one checked snapshot without inventing adoption or lease history."""
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            budget = self._budget(
                db, binding, job_id, request_hash, require_permit=False
            )
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

    def register_ordinal_credits(
        self,
        binding,
        job_id,
        request_hash,
        context_hash,
        production_max,
        verification_max,
    ):
        """Explicit new-profile registration in this SAME external owner database."""
        _credit_hash(request_hash)
        _credit_hash(context_hash)
        for v in (production_max, verification_max):
            if type(v) is not int or not 1 <= v <= 1000000:
                raise ExecutionAuthorityError(
                    "invalid whole-path ordinal solver ceiling"
                )
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            api_budget = self._budget(db, binding, job_id, request_hash)
            if (
                api_budget["reserved_attempts"]
                and not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='ordinal_credit_budgets'"
                ).fetchone()
            ):
                raise ExecutionAuthorityError(
                    "missing ordinal namespace cannot adopt prior API spend"
                )
            _ordinal_credit_schema(db)
            wanted = (request_hash, context_hash, production_max, verification_max)
            row = db.execute(
                "SELECT request_hash,context_hash,production_max,verification_max FROM ordinal_credit_budgets WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                if api_budget["reserved_attempts"]:
                    raise ExecutionAuthorityError(
                        "missing ordinal registration cannot adopt prior spend"
                    )
                db.execute(
                    "INSERT INTO ordinal_credit_budgets VALUES (?,?,?,?,?)",
                    (job_id, *wanted),
                )
            elif row != wanted:
                raise ExecutionAuthorityError(
                    "immutable ordinal solver authority mismatch"
                )
            return self._ordinal_credits(
                db, binding, job_id, request_hash, context_hash
            )

    def _ordinal_credits(self, db, binding, job_id, request_hash, context_hash):
        self._budget(db, binding, job_id, request_hash)
        # Read NEVER creates or repairs a missing credit namespace.
        names = {
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE name IN ('ordinal_credit_budgets','ordinal_credit_reservations')"
            )
        }
        if len(names) != 2:
            raise ExecutionAuthorityError("ordinal solver authority unavailable")
        row = db.execute(
            "SELECT request_hash,context_hash,production_max,verification_max FROM ordinal_credit_budgets WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None or row[:2] != (request_hash, context_hash):
            raise ExecutionAuthorityError("ordinal solver request/context mismatch")
        maxima = {"production": row[2], "verification": row[3]}
        spent = {k: 0 for k in maxima}
        grants = []
        records = db.execute(
            "SELECT credit_ordinal,api_ordinal,phase,ceiling,payload_json,payload_hash FROM ordinal_credit_reservations WHERE job_id=? ORDER BY credit_ordinal",
            (job_id,),
        ).fetchall()
        for ordinal, record in enumerate(records, 1):
            c, a, phase, ceiling, raw, digest = record
            if (
                c != ordinal
                or type(a) is not int
                or a < 1
                or phase not in maxima
                or type(ceiling) is not int
                or not 0 <= ceiling <= 255
            ):
                raise ExecutionAuthorityError("ordinal credit journal invalid")
            payload = json.loads(raw)
            fields = {
                "schema_version",
                "job_request_hash",
                "context_hash",
                "credit_ordinal",
                "api_ordinal",
                "phase",
                "ceiling",
                "completed_before",
                "prior_checkpoint_hash",
                "native_input_sha256",
                "record_limit",
                "authority_id",
                "authority_generation",
                "authority_root",
                "worker_id",
                "lease_token_hash",
            }
            if (
                type(payload) is not dict
                or set(payload) != fields
                or payload["schema_version"]
                != "rc-ordinal-solver-credit-reservation.v1"
                or any(
                    type(payload[k]) is not int
                    for k in (
                        "credit_ordinal",
                        "api_ordinal",
                        "ceiling",
                        "completed_before",
                        "record_limit",
                        "authority_generation",
                    )
                )
                or not 0 <= payload["completed_before"] <= 65536
                or not 1 <= payload["record_limit"] <= 255
                or type(payload["worker_id"]) is not str
                or not payload["worker_id"]
            ):
                raise ExecutionAuthorityError(
                    "ordinal credit payload shape/types invalid"
                )
            _credit_hash(payload["prior_checkpoint_hash"], nullable=True)
            _credit_hash(payload["native_input_sha256"], nullable=True)
            _credit_hash(payload["lease_token_hash"])
            if (
                _credit_json(payload) != raw
                or "sha256:" + hashlib.sha256(raw.encode()).hexdigest() != digest
            ):
                raise ExecutionAuthorityError("ordinal credit event hash mismatch")
            api = db.execute(
                "SELECT generation,root FROM reservations WHERE job_id=? AND ordinal=?",
                (job_id, a),
            ).fetchone()
            if (
                api is None
                or payload.get("credit_ordinal") != c
                or payload.get("api_ordinal") != a
                or payload.get("phase") != phase
                or payload.get("ceiling") != ceiling
                or payload.get("job_request_hash") != request_hash
                or payload.get("context_hash") != context_hash
                or payload.get("authority_id") != binding.authority_id
                or (payload.get("authority_generation"), payload.get("authority_root"))
                != api
            ):
                raise ExecutionAuthorityError(
                    "ordinal credits differ from original API reservation"
                )
            spent[phase] += ceiling
            grants.append(dict(payload, grant_hash=digest))
        if any(
            type(maxima[k]) is not int
            or not 1 <= maxima[k] <= 1000000
            or spent[k] > maxima[k]
            for k in maxima
        ):
            raise ExecutionAuthorityError("ordinal solver ceiling exceeded")
        return {
            "context_hash": context_hash,
            "production": {
                "maximum": maxima["production"],
                "reserved": spent["production"],
                "remaining": maxima["production"] - spent["production"],
            },
            "verification": {
                "maximum": maxima["verification"],
                "reserved": spent["verification"],
                "remaining": maxima["verification"] - spent["verification"],
            },
            "reservations": grants,
        }

    def read_ordinal_credits(self, binding, job_id, request_hash, context_hash):
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            return self._ordinal_credits(
                db, binding, job_id, request_hash, context_hash
            )

    def reserve_ordinal_credits(
        self,
        binding,
        job_id,
        request_hash,
        context_hash,
        *,
        api_ordinal,
        phase,
        ceiling,
        completed_before,
        prior_checkpoint_hash,
        native_input_sha256,
        record_limit,
        worker_id,
        lease_token_hash,
    ):
        """Nonrefundable bounded solver grant BEFORE launch; a duplicate never relaunches."""
        _credit_hash(request_hash)
        _credit_hash(context_hash)
        _credit_hash(prior_checkpoint_hash, nullable=True)
        _credit_hash(native_input_sha256, nullable=True)
        _credit_hash(lease_token_hash)
        if (
            phase not in ("production", "verification")
            or type(ceiling) is not int
            or not 0 <= ceiling <= 255
            or type(record_limit) is not int
            or not 1 <= record_limit <= 255
            or type(completed_before) is not int
            or not 0 <= completed_before <= 65536
            or type(worker_id) is not str
            or not worker_id
        ):
            raise ExecutionAuthorityError("invalid ordinal solver reservation")
        _integer(api_ordinal, minimum=1)
        with self._lock(), self._connection() as db:
            self._require(db, binding)
            snapshot = self._ordinal_credits(
                db, binding, job_id, request_hash, context_hash
            )
            api = db.execute(
                "SELECT generation,root FROM reservations WHERE job_id=? AND ordinal=?",
                (job_id, api_ordinal),
            ).fetchone()
            if api != (binding.generation, binding.root):
                raise ExecutionAuthorityError(
                    "ordinal launch needs current-generation API reservation"
                )
            if any(g["api_ordinal"] == api_ordinal for g in snapshot["reservations"]):
                raise ExecutionAuthorityError(
                    "ordinal API reservation already consumed; unknown work cannot relaunch"
                )
            if ceiling > snapshot[phase]["remaining"]:
                raise ExecutionAuthorityError(
                    "whole-path ordinal solver budget exhausted"
                )
            ordinal = len(snapshot["reservations"]) + 1
            payload = {
                "schema_version": "rc-ordinal-solver-credit-reservation.v1",
                "job_request_hash": request_hash,
                "context_hash": context_hash,
                "credit_ordinal": ordinal,
                "api_ordinal": api_ordinal,
                "phase": phase,
                "ceiling": ceiling,
                "completed_before": completed_before,
                "prior_checkpoint_hash": prior_checkpoint_hash,
                "native_input_sha256": native_input_sha256,
                "record_limit": record_limit,
                "authority_id": binding.authority_id,
                "authority_generation": binding.generation,
                "authority_root": binding.root,
                "worker_id": worker_id,
                "lease_token_hash": lease_token_hash,
            }
            raw = _credit_json(payload)
            digest = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
            db.execute(
                "INSERT INTO ordinal_credit_reservations VALUES (?,?,?,?,?,?,?)",
                (job_id, ordinal, api_ordinal, phase, ceiling, raw, digest),
            )
            return dict(payload, grant_hash=digest)
