"""Read-only, descriptor-anchored Linux cgroup v2 observations.

Observation does not grant ownership or enforce a limit. Callers must retain the
parent descriptor and repeat preflight immediately before any future allocation.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import PurePosixPath
import re
import stat
import sys
import time
from collections.abc import Iterator

from .rc_resource_boundary import BoundaryAdmission, BoundaryObservation

_MAX_CONTROL_BYTES = 4096


def _bounded_read(fd: int, limit: int) -> str:
    data = bytearray()
    while len(data) <= limit:
        block = os.read(fd, min(4096, limit + 1 - len(data)))
        if not block:
            return data.decode("ascii", errors="strict")
        data.extend(block)
    raise ValueError("oversized cgroup observation")


def _control(parent_fd: int, name: str) -> str:
    fd = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=parent_fd,
    )
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("cgroup control is not a regular file")
        return _bounded_read(fd, _MAX_CONTROL_BYTES)
    finally:
        os.close(fd)


def _filesystem_type(fd: int) -> str:
    # The kernel's mount ID binds mountinfo to the held descriptor, even when the
    # directory has been renamed. A path-prefix match would not provide this.
    with open(f"/proc/self/fdinfo/{fd}", "rb") as info:
        raw = info.read(4097)
    if len(raw) > 4096:
        raise ValueError("oversized descriptor information")
    ids = re.findall(rb"^mnt_id:\s*([0-9]+)$", raw, re.MULTILINE)
    if len(ids) != 1:
        raise ValueError("missing or ambiguous descriptor mount ID")
    with open("/proc/self/mountinfo", "rb") as mounts:
        raw_mounts = mounts.read(1_048_577)
    if len(raw_mounts) > 1_048_576:
        raise ValueError("oversized mount information")
    matches = []
    for line in raw_mounts.splitlines():
        left, sep, right = line.partition(b" - ")
        fields = left.split()
        if fields and fields[0] == ids[0]:
            if not sep or not right.split():
                raise ValueError("malformed mount information")
            matches.append(right.split()[0].decode("ascii"))
    if len(matches) != 1:
        raise ValueError("descriptor mount cannot be identified")
    return matches[0]


def _controllers(text: str) -> frozenset[str]:
    values = text.split()
    if len(values) != len(set(values)) or any(
        not re.fullmatch(r"[a-z][a-z0-9_]*", v) for v in values
    ):
        raise ValueError("malformed controller observation")
    return frozenset(values)


def _populated(text: str) -> bool:
    entries = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] in entries or parts[1] not in {"0", "1"}:
            raise ValueError("malformed cgroup events")
        entries[parts[0]] = parts[1]
    if "populated" not in entries:
        raise ValueError("missing populated event")
    return entries["populated"] == "1"


def observe_boundary(parent_fd: int) -> BoundaryObservation:
    """Read a held parent without writing controls or resolving its path again."""
    if sys.platform != "linux":
        raise ValueError("Linux cgroup observation required")
    started = time.monotonic_ns()
    identity = os.fstat(parent_fd)
    if not stat.S_ISDIR(identity.st_mode) or _filesystem_type(parent_fd) != "cgroup2":
        raise ValueError("descriptor must refer to a cgroup v2 directory")
    kind = _control(parent_fd, "cgroup.type").strip()
    if kind != "domain":
        raise ValueError("cgroup v2 domain required")
    available = _controllers(_control(parent_fd, "cgroup.controllers"))
    enabled = _controllers(_control(parent_fd, "cgroup.subtree_control"))
    populated = _populated(_control(parent_fd, "cgroup.events"))
    return BoundaryObservation(
        identity.st_dev,
        identity.st_ino,
        "cgroup2",
        kind,
        available,
        enabled,
        populated,
        started,
    )


@contextmanager
def open_boundary_parent(path: str, admission: BoundaryAdmission) -> Iterator[int]:
    """Open every directory component without following links; check exact pin.

    The admission must come from an external ownership decision. Identity alone
    is not permission to use an existing application or shared service scope.
    """
    if sys.platform != "linux" or type(path) is not str:
        raise ValueError("absolute Linux boundary path required")
    parts = path.split("/")
    if (
        not path.startswith("/")
        or path == "/"
        or any(p in {".", "..", ""} for p in parts[1:])
    ):
        raise ValueError("canonical absolute boundary path required")
    if (
        not isinstance(admission, BoundaryAdmission)
        or admission.exclusive_task_parent is not True
    ):
        raise ValueError("exclusive task parent admission required")
    if (
        type(admission.device) is not int
        or admission.device < 0
        or type(admission.inode) is not int
        or admission.inode <= 0
    ):
        raise ValueError("invalid admitted identity")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in PurePosixPath(path).parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != (admission.device, admission.inode):
            raise ValueError("boundary identity changed")
        if _filesystem_type(fd) != "cgroup2":
            raise ValueError("cgroup v2 filesystem required")
        yield fd
    finally:
        os.close(fd)
