"""Fail-closed preflight for a separately authorized RC cgroup adapter.

This module evaluates observations only. It neither grants delegation nor creates,
migrates into, or changes a cgroup. A passing result is not enforcement evidence.
Memory charging is not whole-job RSS accounting; CPU bandwidth is not total CPU
time. Swap, disk blocks, inodes, WAL growth, and process reaping are outside this
contract. The adapter must verify a real kernel observation and exclusive-parent
authority separately; a caller-created observation alone cannot grant either.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundaryLimits:
    memory_bytes: int
    process_count: int
    cpu_quota_us: int | None = None
    cpu_period_us: int | None = None

    def __post_init__(self) -> None:
        for value in (self.memory_bytes, self.process_count):
            if type(value) is not int or not 1 <= value <= 2**63 - 1:
                raise ValueError("limits must be bounded positive integers")
        if (self.cpu_quota_us is None) != (self.cpu_period_us is None):
            raise ValueError("CPU quota and period must be provided together")
        if self.cpu_quota_us is not None:
            if (
                type(self.cpu_quota_us) is not int
                or not 1000 <= self.cpu_quota_us <= 2**63 - 1
            ):
                raise ValueError("invalid CPU quota")
            if (
                type(self.cpu_period_us) is not int
                or not 1000 <= self.cpu_period_us <= 1_000_000
            ):
                raise ValueError("invalid CPU period")


@dataclass(frozen=True, slots=True)
class BoundaryObservation:
    """Bounded observations supplied by a future OS adapter, not caller authority."""

    device: int
    inode: int
    filesystem: str
    cgroup_type: str
    available_controllers: frozenset[str]
    enabled_child_controllers: frozenset[str]
    populated: bool
    observed_monotonic_ns: int


@dataclass(frozen=True, slots=True)
class BoundaryAdmission:
    """Exact directory identity admitted externally for exclusive task use."""

    device: int
    inode: int
    exclusive_task_parent: bool


def preflight_boundary(
    limits: BoundaryLimits,
    admission: BoundaryAdmission,
    observation: BoundaryObservation,
    *,
    now_monotonic_ns: int,
    maximum_age_ns: int,
) -> dict[str, str]:
    """Return intended child writes only after all supplied preconditions pass.

    The OS adapter must repeat identity and controller checks at allocation and
    read back every child limit. Never apply these writes to the parent itself.
    """
    if not isinstance(limits, BoundaryLimits):
        raise ValueError("invalid boundary limits")
    if not isinstance(admission, BoundaryAdmission) or not isinstance(
        observation, BoundaryObservation
    ):
        raise ValueError("invalid boundary observations")
    for value in (admission.device, observation.device):
        if type(value) is not int or value < 0:
            raise ValueError("invalid device identity")
    for value in (admission.inode, observation.inode):
        if type(value) is not int or value <= 0:
            raise ValueError("invalid inode identity")
    for value in (now_monotonic_ns, maximum_age_ns, observation.observed_monotonic_ns):
        if type(value) is not int or value < 0:
            raise ValueError("invalid observation clock")
    age = now_monotonic_ns - observation.observed_monotonic_ns
    if maximum_age_ns == 0 or not 0 <= age <= maximum_age_ns:
        raise ValueError("stale or future boundary observation")
    if admission.exclusive_task_parent is not True:
        raise ValueError("exclusive task parent admission required")
    if (admission.device, admission.inode) != (observation.device, observation.inode):
        raise ValueError("boundary identity changed")
    if observation.filesystem != "cgroup2" or observation.cgroup_type != "domain":
        raise ValueError("cgroup v2 domain required")
    if observation.populated is not False:
        raise ValueError("task parent must be observed empty")
    required = {"memory", "pids"}
    if limits.cpu_quota_us is not None:
        required.add("cpu")
    for controllers in (
        observation.available_controllers,
        observation.enabled_child_controllers,
    ):
        if type(controllers) is not frozenset or any(
            type(item) is not str for item in controllers
        ):
            raise ValueError("invalid controller observation")
        if not required <= controllers:
            raise ValueError("required child controllers are not delegated and enabled")
    writes = {
        "memory.max": str(limits.memory_bytes),
        "pids.max": str(limits.process_count),
    }
    if limits.cpu_quota_us is not None:
        writes["cpu.max"] = f"{limits.cpu_quota_us} {limits.cpu_period_us}"
    return writes
