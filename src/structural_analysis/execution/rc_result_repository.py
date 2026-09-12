"""Single-host persistent originals for trusted RC evaluation sessions.

This adapter reuses DurableJobService authorization, SQLite transactions and
immutable artifact I/O. It is not an external receipt importer. Only the trusted
session's completed analysis/replay can call the private publisher. Local storage
and the configured service host are trusted; a hash does not authenticate a
filesystem attacker. POSIX local filesystems only in this first implementation.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from time import monotonic, sleep
from typing import Iterator

from structural_analysis.execution.job_service import DurableJobService


_MAX_MANIFEST = 1024 * 1024
_MAX_SNAPSHOT = 128 * 1024 * 1024


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _encode(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _identifier(value: str) -> None:
    if type(value) is not str or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("invalid persistent physics key")
    if any(c not in "0123456789abcdef" for c in value[7:]):
        raise ValueError("invalid persistent physics key")


class RCResultRepository:
    """Tenant-bound index of internally verified immutable RC snapshots.

    Capacity bounds referenced snapshot bytes, not total database/blob-directory
    size: interrupted writes can leave unreferenced immutable blobs. No automatic
    garbage collection or external import is provided. Tokens never enter a
    manifest, result, filename or log. Host-issued service credentials are required.
    """

    def __init__(
        self,
        service: DurableJobService,
        *,
        tenant_id: str,
        authorization_token: str,
        scope_id: str,
        max_entries: int = 256,
        max_bytes: int = 512 * 1024 * 1024,
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        if os.name != "posix":
            raise ValueError("persistent RC reuse currently requires POSIX local storage")
        if type(service) is not DurableJobService:
            raise ValueError("existing durable job service required")
        if type(scope_id) is not str or not scope_id or len(scope_id) > 128:
            raise ValueError("bounded scope required")
        if type(max_entries) is not int or not 1 <= max_entries <= 4096:
            raise ValueError("persistent entry capacity must be in [1, 4096]")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 4 * 1024**3:
            raise ValueError("persistent referenced-byte capacity must be in [1, 4 GiB]")
        if (
            type(lock_timeout_seconds) not in (int, float)
            or not math.isfinite(lock_timeout_seconds)
            or not 0 < lock_timeout_seconds <= 3600
        ):
            raise ValueError("lock timeout must be finite and in (0, 3600]")
        self._service = service
        self._tenant = tenant_id
        self._token = authorization_token
        self.scope_id = scope_id
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._timeout = float(lock_timeout_seconds)
        self._authorize(scope_id)
        self._locks = service.root / "rc-result-locks"
        self._locks.mkdir(mode=0o700, exist_ok=True)
        self._paths_safe()
        with service._transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rc_verified_result_index_v1 ("
                "tenant TEXT NOT NULL, scope TEXT NOT NULL, physics_key TEXT NOT NULL, "
                "manifest_hash TEXT NOT NULL, manifest_size INTEGER NOT NULL, "
                "snapshot_bytes INTEGER NOT NULL, "
                "PRIMARY KEY (tenant, scope, physics_key))"
            )

    def _paths_safe(self) -> None:
        # Trusted local filesystem, not a hostile concurrent path-replacement API.
        root = self._service.root
        for path in (root, self._service._blob_root, self._service._db_path, self._locks):
            current = path
            while current != root.parent:
                if current.is_symlink():
                    raise ValueError("symlink in persistent result storage")
                if current == root:
                    break
                current = current.parent

    def _authorize(self, scope_id: str) -> None:
        self._service._authorize_tenant(self._tenant, self._token)
        if scope_id != self.scope_id:
            raise ValueError("persistent result ownership mismatch")

    @contextmanager
    def reservation(self, key: str, scope_id: str) -> Iterator[None]:
        """One physical evaluation per key at a time; OS releases locks on death.

        A busy worker never triggers speculative duplicate solving. Timeout is an
        explicit error; no stale PID guessing, lock-file deletion or stolen lease.
        No database transaction is held while a nonlinear solver is running.
        """
        import fcntl

        self._authorize(scope_id)
        self._paths_safe()
        _identifier(key)
        name = _digest(_encode({"tenant": self._tenant, "scope": scope_id, "key": key}))[7:]
        path = self._locks / name
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("persistent reservation is not a regular file")
            deadline = monotonic() + self._timeout
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if monotonic() >= deadline:
                        raise TimeoutError("verified-result reservation is busy") from None
                    sleep(min(0.02, max(0.0, deadline - monotonic())))
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _read(self, reference: dict, maximum: int) -> bytes:
        if type(reference) is not dict or set(reference) != {"hash", "size"}:
            raise ValueError("invalid persistent artifact reference")
        _identifier(reference["hash"])
        if type(reference["size"]) is not int or not 0 <= reference["size"] <= maximum:
            raise ValueError("invalid persistent artifact length")
        path = self._service._blob_path(reference["hash"])
        if path.parent.is_symlink():
            raise ValueError("symlink in persistent artifact directory")
        return self._service._read_blob(
            reference["hash"], reference["size"], maximum_bytes=maximum
        )

    def _load(self, key: str, scope_id: str):
        """Private transport read. Session still validates seal, work and physics key."""
        self._authorize(scope_id)
        self._paths_safe()
        _identifier(key)
        connection = self._service._connect()
        try:
            indexed = connection.execute(
                "SELECT * FROM rc_verified_result_index_v1 "
                "WHERE tenant=? AND scope=? AND physics_key=?",
                (self._tenant, scope_id, key),
            ).fetchone()
        finally:
            connection.close()
        if indexed is None:
            return None
        from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
        from structural_analysis.benchmark.rc_control_reuse import _Snapshot

        raw = self._read(
            {"hash": indexed["manifest_hash"], "size": indexed["manifest_size"]},
            _MAX_MANIFEST,
        )
        value = strict_json_object_bytes(raw, maximum_bytes=_MAX_MANIFEST)
        if (
            set(value) != {"schema", "key", "tenant", "scope", "row", "artifacts", "seal", "size"}
            or value["schema"] != "persistent-rc-original.v1"
            or value["key"] != key
            or value["tenant"] != self._tenant
            or value["scope"] != scope_id
            or type(value["size"]) is not int
            or not 0 < value["size"] <= _MAX_SNAPSHOT
            or value["size"] != indexed["snapshot_bytes"]
            or type(value["artifacts"]) is not dict
            or not 1 <= len(value["artifacts"]) <= 16
        ):
            raise ValueError("persistent original identity or size mismatch")
        row = self._read(value["row"], _MAX_MANIFEST)
        consumed = len(row)
        artifacts = []
        for name, reference in sorted(value["artifacts"].items()):
            if type(name) is not str or not name or not name.replace("_", "").isalnum():
                raise ValueError("invalid persistent artifact role")
            data = self._read(reference, value["size"] - consumed)
            consumed += len(data)
            artifacts.append((name, data))
        if consumed != value["size"]:
            raise ValueError("persistent snapshot size mismatch")
        entry = _Snapshot(key, row, tuple(artifacts), value["seal"])
        entry.check()
        return entry

    def _publish(self, entry, scope_id: str) -> bool:
        """Internal session-only admission, after successful output publication."""
        self._authorize(scope_id)
        self._paths_safe()
        entry.check()
        _identifier(entry.key)
        if entry.byte_length > min(self._max_bytes, _MAX_SNAPSHOT):
            return False
        with self._service._transaction() as connection:
            prior = connection.execute(
                "SELECT 1 FROM rc_verified_result_index_v1 "
                "WHERE tenant=? AND scope=? AND physics_key=?",
                (self._tenant, scope_id, entry.key),
            ).fetchone()
            if prior is not None:
                # First successful original remains immutable, including on forced replay.
                self._load(entry.key, scope_id)
                return True
            capacity = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(snapshot_bytes), 0) "
                "FROM rc_verified_result_index_v1 WHERE tenant=?",
                (self._tenant,),
            ).fetchone()
            if capacity[0] >= self._max_entries or capacity[1] + entry.byte_length > self._max_bytes:
                return False

            def put(raw: bytes) -> dict:
                reference = self._service._put_blob(
                    raw, role="evidence", media_type="application/json", maximum_bytes=_MAX_SNAPSHOT
                )
                return {"hash": reference.content_hash, "size": reference.byte_length}

            value = {
                "schema": "persistent-rc-original.v1",
                "key": entry.key,
                "tenant": self._tenant,
                "scope": scope_id,
                "row": put(entry.row_bytes),
                "artifacts": {name: put(raw) for name, raw in entry.artifacts},
                "seal": entry.seal,
                "size": entry.byte_length,
            }
            manifest = _encode(value)
            if len(manifest) > _MAX_MANIFEST:
                raise ValueError("persistent manifest exceeds limit")
            reference = put(manifest)
            connection.execute(
                "INSERT INTO rc_verified_result_index_v1 VALUES (?, ?, ?, ?, ?, ?)",
                (self._tenant, scope_id, entry.key, reference["hash"], reference["size"], entry.byte_length),
            )
        return True


def open_local_rc_repository(
    root: Path, *, tenant_id: str, authorization_token: str, scope_id: str
) -> RCResultRepository:
    """Dedicated local CLI store, with first-owner credentials pinned on disk.

    Reopening with a different token cannot silently reconfigure host authority.
    Protect this directory with OS permissions. Anyone who controls it can replace
    its credential verifier; this is not a defense against the local OS owner.
    """
    import hmac
    import re
    import secrets

    from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes

    if type(tenant_id) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", tenant_id):
        raise ValueError("invalid local tenant identifier")
    if type(authorization_token) is not str or len(authorization_token.encode()) < 16:
        raise ValueError("local store token must contain at least 16 UTF-8 bytes")
    requested = Path(root).absolute()
    for path in (requested, *requested.parents):
        if path.is_symlink():
            raise ValueError("symlink in local repository root")
    requested.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials = requested / "rc-local-owner.json"
    expected = {
        "schema": "local-rc-owner.v1", "tenant": tenant_id,
        "token_hash": _digest(b"local-rc-owner.v1\0" + tenant_id.encode() + b"\0" + authorization_token.encode()),
    }
    encoded = _encode(expected)
    # Initialization is separate from result registration and stores no raw token.
    try:
        descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if credentials.is_symlink() or not credentials.is_file():
            raise ValueError("invalid local owner file") from None
        with credentials.open("rb") as stream:
            previous = strict_json_object_bytes(stream.read(4097), maximum_bytes=4096)
        if set(previous) != set(expected) or previous.get("schema") != expected["schema"] or previous.get("tenant") != tenant_id:
            raise ValueError("local repository ownership mismatch")
        if type(previous.get("token_hash")) is not str or not hmac.compare_digest(previous["token_hash"], expected["token_hash"]):
            raise ValueError("local repository authorization failed")
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    service = DurableJobService(
        requested, tenant_tokens={tenant_id: authorization_token},
        worker_tokens={"rc-local-internal": secrets.token_urlsafe(32)},
        worker_tenants={"rc-local-internal": [tenant_id]},
    )
    return RCResultRepository(
        service, tenant_id=tenant_id, authorization_token=authorization_token, scope_id=scope_id
    )
