"""Bounded, content-bound JSON access for trusted local replay workspaces.

Only file metadata/digests are retained, not all decoded artifacts. At most one
file per operand is decoded by a comparison. Limits bound encoded input, not
process RSS. The workspace must not have a concurrent writer; detected changes
fail closed. This is not a multi-user filesystem sandbox.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

MAX_STUDY_FILES = 20_000
MAX_STUDY_BYTES = 512 * 1024**2
MAX_FILE_BYTES = 256 * 1024**2
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class _Entry:
    size: int
    sha256: str


def _paths(root: Path) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("local original artifact directory required")
    paths = {}
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError("local original artifact required; symlink directory")
        for name in sorted(files):
            if not name.endswith(".json"):
                continue
            path = Path(directory) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or not path.resolve().is_relative_to(root):
                raise ValueError("local original artifact required")
            total += info.st_size
            if info.st_size > MAX_FILE_BYTES or total > MAX_STUDY_BYTES:
                raise ValueError("study replay byte/file budget exceeded")
            paths[path.relative_to(root).as_posix()] = path
            if len(paths) > MAX_STUDY_FILES:
                raise ValueError("study replay byte/file budget exceeded")
    return dict(sorted(paths.items()))


def _open_regular(path: Path, root: Path):
    # Refuse symlinks at every path component before opening the final file.
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("local original artifact required; symlink")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise ValueError("regular bounded artifact file required")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _fingerprint(path: Path, root: Path) -> _Entry:
    digest = hashlib.sha256()
    count = 0
    with _open_regular(path, root) as stream:
        while chunk := stream.read(_CHUNK):
            count += len(chunk)
            if count > MAX_FILE_BYTES:
                raise ValueError("study replay byte/file budget exceeded")
            digest.update(chunk)
    return _Entry(count, digest.hexdigest())


def _validate_value(raw: bytes, name: str) -> dict:
    value = strict_json_object_bytes(raw, maximum_bytes=MAX_FILE_BYTES)
    for key in ("report_hash", "path_hash", "step_hash"):
        if key in value:
            body = {k: v for k, v in value.items() if k != key}
            expected = canonical_hash(body) if key == "step_hash" else _sha(_bytes(body))
            if value[key] != expected:
                raise ValueError(f"original {key} mismatch: {name}")
    return value


class ReplayStudyFiles(Mapping[str, dict]):
    """Read-only metadata index; each lookup freshly verifies the bound bytes."""

    def __init__(self, root: Path):
        original = Path(root)
        if original.is_symlink():
            raise ValueError("local original artifact directory required")
        self.root = original.resolve()
        paths = _paths(self.root)
        self._entries = {}
        total = 0
        for name, path in paths.items():
            # Bind and validate the very same read. The final full inventory
            # recheck remains below; no metadata-only or mtime shortcut is used.
            with _open_regular(path, self.root) as stream:
                size = os.fstat(stream.fileno()).st_size
                if total + size > MAX_STUDY_BYTES:
                    raise ValueError("study replay byte/file budget exceeded")
                raw = stream.read(size + 1)
            if len(raw) != size:
                raise ValueError(f"artifact changed during initial scan: {name}")
            entry = _Entry(size, hashlib.sha256(raw).hexdigest())
            total += entry.size
            if total > MAX_STUDY_BYTES:
                raise ValueError("study replay byte/file budget exceeded")
            value = _validate_value(raw, name)
            self._entries[name] = entry
            del value, raw
        self.verify_unchanged()

    def __getitem__(self, name: str) -> dict:
        entry = self._entries[name]  # Exact index membership forbids arbitrary paths.
        with _open_regular(self.root / name, self.root) as stream:
            raw = stream.read(entry.size + 1)
        if len(raw) != entry.size or hashlib.sha256(raw).hexdigest() != entry.sha256:
            raise ValueError(f"artifact changed during replay: {name}")
        return _validate_value(raw, name)

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def verify_unchanged(self) -> None:
        paths = _paths(self.root)
        if paths.keys() != self._entries.keys():
            raise ValueError("artifact roster changed during replay")
        for name, path in paths.items():
            if _fingerprint(path, self.root) != self._entries[name]:
                raise ValueError(f"artifact changed during replay: {name}")
