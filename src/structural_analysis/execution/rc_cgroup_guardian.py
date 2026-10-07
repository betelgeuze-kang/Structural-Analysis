"""Before-gate enrollment interface for the externally admitted E2 bridge.

The bridge must retain exclusive reaping ownership of its gated direct child
through enrollment and observation. This module never opens the native G gate.
It is not authority to migrate arbitrary processes or use a shared parent scope.
"""

from __future__ import annotations

import os
import select

from .rc_cgroup_allocation import CgroupAllocation
from .rc_cgroup_observer import _control


def _owned_live_generation(pid: int) -> int:
    if type(pid) is not int or pid <= 1 or pid == os.getpid():
        raise ValueError("a live owned direct child is required")
    # WNOWAIT preserves the bridge's Popen reaping authority. The bridge must
    # not concurrently wait/reap this child, otherwise PID migration is unsafe.
    if os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
        raise ValueError("guardian exited before enrollment")
    with open(f"/proc/{pid}/stat", "rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096 or not raw.startswith(f"{pid} (".encode()):
        raise ValueError("invalid guardian process identity")
    end = raw.rfind(b")")
    fields = raw[end + 1 :].split()
    if end < 0 or len(fields) < 20 or fields[0] in {b"Z", b"X", b"x"}:
        raise ValueError("guardian is not live")
    if int(fields[1]) != os.getpid():
        raise ValueError("guardian is not an owned direct child")
    generation = int(fields[19])
    if generation <= 0:
        raise ValueError("invalid guardian generation")
    return generation


def _pidfd_live(fd: int) -> None:
    poll = select.poll()
    poll.register(fd, select.POLLIN)
    if poll.poll(0):
        raise ValueError("guardian process handle is no longer live")


def _member_pids(fd: int) -> set[int]:
    values = _control(fd, "cgroup.procs").split()
    if any(
        not value.isascii() or not value.isdecimal() or int(value) <= 1
        for value in values
    ):
        raise ValueError("invalid cgroup process membership")
    # The kernel may list a migrating process more than once; order is undefined.
    return {int(value) for value in values}


class GuardianBoundary:
    """One gated guardian per successfully allocated dedicated leaf."""

    def __init__(self, allocation: CgroupAllocation):
        self._allocation = allocation
        self._pid: int | None = None
        self._generation: int | None = None
        self._pidfd: int | None = None
        self._verified = False
        self._rejected = False

    def enrol_guardian(self, pid: int) -> None:
        if self._pid is not None or self._rejected:
            raise ValueError("guardian enrollment already attempted")
        # Mark attempts before any fallible action. A failed attempt cannot be
        # repurposed for a different child or interpreted as successful later.
        self._rejected = True
        self._allocation._check_identity()
        generation = _owned_live_generation(pid)
        pidfd = os.pidfd_open(pid, 0)
        self._allocation._stack.callback(os.close, pidfd)
        self._pid, self._pidfd, self._generation = pid, pidfd, generation
        _pidfd_live(pidfd)
        if _owned_live_generation(pid) != generation:
            raise ValueError("guardian generation changed")
        scope = self._allocation._check_identity()
        if _member_pids(scope):
            raise ValueError("guardian scope is not empty before enrollment")
        self._allocation._write("cgroup.procs", str(pid))
        _pidfd_live(pidfd)
        if _owned_live_generation(pid) != generation or _member_pids(scope) != {pid}:
            raise ValueError("guardian enrollment did not preserve exact membership")
        self._verified = True
        self._rejected = False

    def observe_guardian_enrolment(self, pid: int) -> dict[str, str | int]:
        if (
            not self._verified
            or self._rejected
            or type(pid) is not int
            or pid != self._pid
        ):
            raise ValueError("guardian enrollment is not verified")
        try:
            _pidfd_live(self._pidfd)
            if _owned_live_generation(pid) != self._generation:
                raise ValueError("guardian generation changed after enrollment")
            scope = self._allocation._check_identity()
            if _member_pids(scope) != {pid}:
                raise ValueError("guardian exact membership changed before gate")
        except BaseException:
            self._rejected = True
            raise
        return {
            "status": "ACTUAL_OS_GUARDIAN_ENROLMENT_OBSERVED",
            "pid": pid,
            "start_ticks": self._generation,
            "scope_device": self._allocation._identity[0],
            "scope_inode": self._allocation._identity[1],
        }

    def close_and_observe_empty(self) -> dict[str, str]:
        self._verified = False
        outcome = self._allocation.close_and_observe_empty()
        if outcome["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED":
            return {"status": "ACTUAL_OS_DESCENDANT_SCOPE_EMPTY_OBSERVED"}
        return outcome


def prepare_boundary(plan: dict) -> GuardianBoundary:
    """Adapter entrypoint for an exact-plan, externally reviewed E2 admission.

    The bridge validates the root admission and pinned adapter/source receipts
    before invoking this entrypoint. These declarations are configuration, not
    evidence that delegation, ownership or enforcement has been established.
    """
    from .rc_cgroup_allocation import BoundarySetupError, allocate_boundary
    from .rc_resource_boundary import BoundaryAdmission, BoundaryLimits

    keys = {
        "interface",
        "guardian_enrolment_before_native_gate",
        "separate_browser_PG_covered",
        "all_descendant_cleanup_required",
        "linux_cgroup_v2",
    }
    if type(plan) is not dict or set(plan) != keys:
        raise ValueError("invalid guardian boundary plan")
    if plan["interface"] != "rc-b-E2-before-gate-descendant-boundary.v1" or any(
        plan[key] is not True for key in keys - {"interface", "linux_cgroup_v2"}
    ):
        raise ValueError("before-gate descendant boundary contract required")
    config = plan["linux_cgroup_v2"]
    required = {
        "schema_version",
        "parent_path",
        "parent_device",
        "parent_inode",
        "exclusive_task_parent",
        "memory_bytes",
        "process_count",
        "cpu_quota_us",
        "cpu_period_us",
        "cleanup_timeout_ms",
    }
    if (
        type(config) is not dict
        or set(config) != required
        or config["schema_version"] != "rc-cgroup-v2-boundary-config.v1"
    ):
        raise ValueError("invalid cgroup boundary configuration")
    limits = BoundaryLimits(
        config["memory_bytes"],
        config["process_count"],
        config["cpu_quota_us"],
        config["cpu_period_us"],
    )
    admission = BoundaryAdmission(
        config["parent_device"], config["parent_inode"], config["exclusive_task_parent"]
    )
    owned = allocate_boundary(
        config["parent_path"],
        admission,
        limits,
        cleanup_timeout_ms=config["cleanup_timeout_ms"],
    )
    try:
        return GuardianBoundary(owned)
    except BaseException as exc:
        cleanup = owned.close_and_observe_empty()
        raise BoundarySetupError(owned, cleanup) from exc
