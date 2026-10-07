"""Operator-only backup to new roots on trusted local filesystems.

Copies only the service DB and immutable blobs, never configuration or credentials.
A SQLite writer reservation serializes cooperating service writers while taking
an online DB snapshot and copying blobs. No live restore or overwrite is offered.
Bounds are cooperative payload/time checks, not filesystem quotas or hard I/O
latency guarantees. Restored job leases and application state are not rewritten.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

_BLOB = re.compile(r"blobs/sha256/([0-9a-f]{2})/([0-9a-f]{64})\Z")
_SCHEMA = "durable-job-store-backup.v1"


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate backup JSON key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("nonfinite backup JSON value")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except RecursionError as exc:
        raise ValueError("backup JSON nesting exceeds supported depth") from exc


class _Budget:
    def __init__(self, maximum_bytes, maximum_files, timeout_seconds):
        for value in (maximum_bytes, maximum_files, timeout_seconds):
            if type(value) is not int or not 1 <= value <= 2**63 - 1:
                raise ValueError("positive integer backup bounds required")
        if maximum_files > 100_000 or timeout_seconds > 3600:
            raise ValueError("backup file/time bound exceeds supported range")
        self.limit = maximum_bytes
        self.files = maximum_files
        self.used = 0
        self.deadline = time.monotonic() + timeout_seconds

    def check(self, extra=0):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("backup operation deadline exceeded")
        if self.used + extra > self.limit:
            raise ValueError("backup payload budget exceeded")


def _safe(path: Path, *, directory=False):
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("symlink in backup path")
    mode = path.stat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError("invalid backup file type")


def _roots(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    _safe(source, directory=True)
    _safe(destination.parent, directory=True)
    source, destination = (
        source.resolve(),
        destination.parent.resolve() / destination.name,
    )
    if (
        destination == source
        or destination.is_relative_to(source)
        or destination.exists()
        or destination.is_symlink()
    ):
        raise ValueError("new external destination required")
    return source, destination


def _relative(name):
    if name == "jobs.sqlite3":
        return
    match = _BLOB.fullmatch(name)
    if not match or match[1] != match[2][:2]:
        raise ValueError("invalid backup member path")


def _copy(source, destination, budget):
    _safe(source)
    size = source.stat().st_size
    budget.check(size)
    if budget.files <= 0:
        raise ValueError("backup file count exceeded")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0
    with source.open("rb") as inp, destination.open("xb") as out:
        os.fchmod(out.fileno(), 0o600)
        while data := inp.read(65536):
            budget.check(written + len(data))
            written += len(data)
            if written > size:
                raise ValueError("source changed during backup")
            digest.update(data)
            out.write(data)
        out.flush()
        os.fsync(out.fileno())
    if written != size:
        raise ValueError("source changed during backup")
    budget.used += written
    budget.files -= 1
    return {"bytes": written, "sha256": digest.hexdigest()}


def _database_checks(root, files, budget):
    with closing(
        sqlite3.connect((root / "jobs.sqlite3").as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.set_progress_handler(lambda: int(time.monotonic() >= budget.deadline), 1000)
        if (
            db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
            or db.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise ValueError("backup database integrity failed")

        def reference(digest, size=None):
            if not isinstance(digest, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", digest
            ):
                raise ValueError("invalid stored artifact reference")
            suffix = digest[7:]
            item = files.get(f"blobs/sha256/{suffix[:2]}/{suffix}")
            if item is None or (
                size is not None and (type(size) is not int or size != item["bytes"])
            ):
                raise ValueError("backup artifact reference missing or mismatched")

        refs = {
            "jobs": [
                (name + "_hash", name + "_size")
                for name in ("request", "checkpoint", "result", "evidence")
            ],
            "job_rc_invocation_outcomes": [("outcome_hash", "outcome_size")],
            "job_failure_diagnostics": [
                ("content_hash", "byte_length"),
                ("checkpoint_hash", None),
            ],
            "job_rc_quantity_reports": [("content_hash", "byte_length")],
        }
        for table, columns in refs.items():
            for digest_column, size_column in columns:
                for digest, size in db.execute(
                    f"SELECT {digest_column}, {size_column or 'NULL'} FROM {table}"
                ):
                    budget.check()
                    if digest is not None:
                        if size_column is not None and type(size) is not int:
                            raise ValueError("invalid stored artifact length")
                        reference(digest, size)
        # Event history may retain a checkpoint which is no longer in jobs.
        for (payload,) in db.execute("SELECT payload_json FROM job_events"):
            budget.check()
            if not isinstance(payload, str) or len(payload.encode()) > 16 * 1024 * 1024:
                raise ValueError("stored event payload exceeds bound")
            pending = [(_strict_json(payload), 0)]
            while pending:
                value, depth = pending.pop()
                if depth > 64:
                    raise ValueError("stored event nesting exceeds bound")
                if isinstance(value, dict):
                    if {"content_hash", "byte_length"} <= value.keys():
                        if type(value["byte_length"]) is not int:
                            raise ValueError("invalid event artifact length")
                        reference(value["content_hash"], value["byte_length"])
                    pending.extend((item, depth + 1) for item in value.values())
                elif isinstance(value, list):
                    pending.extend((item, depth + 1) for item in value)
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rc_verified_result_index_v1'"
        ).fetchone():
            for digest, size in db.execute(
                "SELECT manifest_hash, manifest_size FROM rc_verified_result_index_v1"
            ):
                reference(digest, size)
                if size > 1024 * 1024:
                    raise ValueError("persistent manifest exceeds bound")
                key = digest[7:]
                manifest = _strict_json(
                    (root / f"blobs/sha256/{key[:2]}/{key}").read_bytes()
                )
                for item in [manifest["row"], *manifest["artifacts"].values()]:
                    if type(item["size"]) is not int:
                        raise ValueError("invalid persistent artifact length")
                    reference(item["hash"], item["size"])


def backup_job_store(
    source, destination, *, maximum_bytes, maximum_files=10000, timeout_seconds=60
):
    """Return a manifest digest to retain separately for later restore checks.

    Failure may leave a partial new directory. Only a successfully returned
    digest admits a backup for later verification. No source or existing
    destination is deleted or overwritten.
    """
    budget = _Budget(maximum_bytes, maximum_files, timeout_seconds)
    source, destination = _roots(source, destination)
    _safe(source / "jobs.sqlite3")
    _safe(source / "blobs/sha256", directory=True)
    files = {}
    with closing(
        sqlite3.connect(
            (source / "jobs.sqlite3").as_uri() + "?mode=rw",
            uri=True,
            timeout=0,
            isolation_level=None,
        )
    ) as lock:
        lock.execute("BEGIN IMMEDIATE")
        try:
            destination.mkdir(mode=0o700)
            target = destination / "jobs.sqlite3"
            with (
                closing(
                    sqlite3.connect(
                        (source / "jobs.sqlite3").as_uri() + "?mode=ro",
                        uri=True,
                        timeout=0,
                    )
                ) as reader,
                closing(sqlite3.connect(target)) as writer,
            ):
                page_size = reader.execute("PRAGMA page_size").fetchone()[0]
                reader.backup(
                    writer,
                    pages=64,
                    sleep=0.001,
                    progress=lambda status, remaining, total: budget.check(
                        total * page_size
                    ),
                )
                writer.execute("PRAGMA journal_mode=DELETE")
            os.chmod(target, 0o600)
            size = target.stat().st_size
            budget.check(size)
            budget.used += size
            budget.files -= 1
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                while block := stream.read(65536):
                    budget.check()
                    digest.update(block)
            files["jobs.sqlite3"] = {"bytes": size, "sha256": digest.hexdigest()}
            with os.scandir(source / "blobs/sha256") as prefixes:
                for prefix in prefixes:
                    if not re.fullmatch(r"[0-9a-f]{2}", prefix.name):
                        raise ValueError("invalid blob prefix")
                    _safe(Path(prefix.path), directory=True)
                    with os.scandir(prefix.path) as entries:
                        for entry in entries:
                            # Uncommitted service staging files are not artifacts.
                            if entry.name.startswith(".job-blob-"):
                                continue
                            name = f"blobs/sha256/{prefix.name}/{entry.name}"
                            _relative(name)
                            item = _copy(Path(entry.path), destination / name, budget)
                            if item["sha256"] != entry.name:
                                raise ValueError("content-addressed blob differs")
                            files[name] = item
            _database_checks(destination, files, budget)
        finally:
            lock.rollback()
    manifest = {
        "schema": _SCHEMA,
        "files": files,
        "application_integrity_checked": False,
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("backup manifest exceeds bound")
    with (destination / "backup-manifest.json").open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "files": len(files),
        "payload_bytes": budget.used,
    }


def restore_job_store(
    source,
    destination,
    *,
    manifest_sha256,
    maximum_bytes,
    maximum_files=10000,
    timeout_seconds=60,
):
    """Verify against a separately retained digest; restore only to a new root."""
    budget = _Budget(maximum_bytes, maximum_files, timeout_seconds)
    source, destination = _roots(source, destination)
    manifest_path = source / "backup-manifest.json"
    _safe(manifest_path)
    with manifest_path.open("rb") as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    if (
        len(raw) > 16 * 1024 * 1024
        or hashlib.sha256(raw).hexdigest() != manifest_sha256
    ):
        raise ValueError("backup manifest digest differs")
    manifest = _strict_json(raw)
    if (
        type(manifest) is not dict
        or set(manifest) != {"schema", "files", "application_integrity_checked"}
        or manifest["schema"] != _SCHEMA
        or manifest["application_integrity_checked"] is not False
    ):
        raise ValueError("unsupported backup manifest")
    files = manifest["files"]
    if (
        type(files) is not dict
        or "jobs.sqlite3" not in files
        or len(files) > maximum_files
    ):
        raise ValueError("invalid backup inventory")
    for name, item in files.items():
        _relative(name)
        if (
            type(item) is not dict
            or set(item) != {"bytes", "sha256"}
            or type(item["bytes"]) is not int
            or item["bytes"] < 0
            or not isinstance(item["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        ):
            raise ValueError("invalid backup file record")
        if name != "jobs.sqlite3" and item["sha256"] != name.rsplit("/", 1)[1]:
            raise ValueError("backup content address differs")
    budget.check(sum(item["bytes"] for item in files.values()))
    destination.mkdir(mode=0o700)
    for name, expected in files.items():
        actual = _copy(source / name, destination / name, budget)
        if actual != expected:
            raise ValueError("backup member differs")
    _database_checks(destination, files, budget)
    return {
        "files": len(files),
        "payload_bytes": budget.used,
        "application_integrity_checked": False,
    }
