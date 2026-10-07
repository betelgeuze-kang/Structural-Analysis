"""Owned cgroup allocation and bounded cleanup; not yet a worker launch adapter.

Only an externally admitted, dedicated parent may be used. No parent controllers
or limits are changed. This does not establish process enrollment, escape
resistance, reaping, storage quotas, or whole-job resource qualification.
Exclusive-parent authority must exclude concurrent external renames/removals;
cgroup directory removal has no atomic compare-inode operation. This adapter is
not a security boundary against another actor with the same delegation rights.
"""

from __future__ import annotations

from contextlib import ExitStack
import os
import stat
import time
import uuid

from .rc_cgroup_observer import (
    _control,
    _populated,
    observe_boundary,
    open_boundary_parent,
)
from .rc_resource_boundary import BoundaryAdmission, BoundaryLimits, preflight_boundary


class BoundarySetupError(RuntimeError):
    """Retain ownership after failed setup so uncertain cleanup can be retried."""

    def __init__(self, boundary: CgroupAllocation, cleanup: dict[str, str]):
        super().__init__("cgroup setup failed; inspect cleanup outcome")
        self.boundary = boundary
        self.cleanup = cleanup


class CgroupAllocation:
    def __init__(self, stack: ExitStack, parent_fd: int, timeout_ms: int):
        self._stack = stack
        self._parent_fd = parent_fd
        self._child_fd: int | None = None
        self._identity: tuple[int, int] | None = None
        self._created = False
        self._closed = False
        self._terminal_status: str | None = None
        self._timeout_ms = timeout_ms
        self.name = "rc-job-" + uuid.uuid4().hex

    def _check_identity(self) -> int:
        if self._closed or self._child_fd is None or self._identity is None:
            raise ValueError("owned boundary descriptor unavailable")
        held = os.fstat(self._child_fd)
        named = os.stat(self.name, dir_fd=self._parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(named.st_mode)
            or (held.st_dev, held.st_ino) != self._identity
            or (named.st_dev, named.st_ino) != self._identity
        ):
            raise ValueError("owned boundary identity changed")
        return self._child_fd

    def _open_write_control(self, name: str) -> int:
        parent = self._check_identity()
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent,
        )
        try:
            actual = os.fstat(fd)
            if not stat.S_ISREG(actual.st_mode) or actual.st_dev != self._identity[0]:
                raise ValueError("invalid cgroup control file")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _write(self, name: str, value: str) -> None:
        fd = self._open_write_control(name)
        try:
            encoded = value.encode("ascii")
            if os.write(fd, encoded) != len(encoded):
                raise OSError("partial cgroup control write")
        finally:
            os.close(fd)

    def close_and_observe_empty(self) -> dict[str, str]:
        """Kill only the owned scope, observe emptiness, then remove its directory.

        UNKNOWN keeps descriptors available for a later retry. Empty cgroup
        observation is not evidence that a parent has reaped exited processes.
        """
        if self._closed:
            return {"status": self._terminal_status}
        if not self._created:
            self._stack.close()
            self._closed = True
            self._terminal_status = "NO_SCOPE_CREATED"
            return {"status": self._terminal_status}
        try:
            child = self._check_identity()
            self._write("cgroup.kill", "1")
            deadline = time.monotonic_ns() + self._timeout_ms * 1_000_000
            while _populated(_control(child, "cgroup.events")):
                remaining = deadline - time.monotonic_ns()
                if remaining <= 0:
                    raise TimeoutError("owned scope remains populated")
                time.sleep(min(0.01, remaining / 1_000_000_000))
            self._check_identity()
            os.rmdir(self.name, dir_fd=self._parent_fd)
        except (OSError, ValueError) as exc:
            return {"status": "OWNED_SCOPE_CLEANUP_UNKNOWN", "reason": str(exc)}
        self._stack.close()
        self._closed = True
        self._terminal_status = "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"
        return {"status": self._terminal_status}


def allocate_boundary(
    parent_path: str,
    admission: BoundaryAdmission,
    limits: BoundaryLimits,
    *,
    cleanup_timeout_ms: int = 1000,
) -> CgroupAllocation:
    """Create a new leaf after fresh preflight and verify every requested limit.

    This is opt-in: callers need actual exclusive-parent authority, not just a
    fabricated admission object. Existing scopes are never adopted or reused.
    """
    if type(cleanup_timeout_ms) is not int or not 1 <= cleanup_timeout_ms <= 5000:
        raise ValueError("invalid cleanup timeout")
    stack = ExitStack()
    boundary = None
    try:
        parent = stack.enter_context(open_boundary_parent(parent_path, admission))
        observation = observe_boundary(parent)
        writes = preflight_boundary(
            limits,
            admission,
            observation,
            now_monotonic_ns=time.monotonic_ns(),
            maximum_age_ns=1_000_000_000,
        )
        boundary = CgroupAllocation(stack, parent, cleanup_timeout_ms)
        os.mkdir(boundary.name, mode=0o700, dir_fd=parent)
        boundary._created = True
        child = os.open(
            boundary.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=parent,
        )
        boundary._child_fd = child
        stack.callback(os.close, child)
        identity = os.fstat(child)
        boundary._identity = (identity.st_dev, identity.st_ino)
        child_observation = observe_boundary(child)
        if child_observation.populated:
            raise ValueError("new scope is unexpectedly populated")
        # A leaf still contains forked descendants, including separate sessions.
        # Prevent nested cgroup creation so cleanup never recursively deletes.
        writes |= {"cgroup.max.depth": "0", "cgroup.max.descendants": "0"}
        for name, value in writes.items():
            boundary._write(name, value)
            if " ".join(_control(child, name).split()) != value:
                raise ValueError(f"cgroup limit readback mismatch: {name}")
        # Opening proves the kill control is writable now without issuing a kill.
        # Permissions can still change later: cleanup remains fail-closed.
        kill_fd = boundary._open_write_control("cgroup.kill")
        os.close(kill_fd)
        return boundary
    except BaseException as exc:
        if boundary is None:
            stack.close()
            raise
        cleanup = boundary.close_and_observe_empty()
        raise BoundarySetupError(boundary, cleanup) from exc
