"""No cgroup writes: synthetic enrollment plus one owned, gated dummy process."""

from contextlib import ExitStack
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from structural_analysis.execution import rc_cgroup_guardian as guardian

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux pidfd/cgroup contract"
)


@pytest.fixture
def state(monkeypatch):
    data = SimpleNamespace(
        members=set(),
        generation=88,
        alive=True,
        closed=False,
        writes=[],
        cleanup="OWNED_SCOPE_REMOVED_EMPTY_OBSERVED",
    )
    stack = ExitStack()

    def identity():
        if data.closed:
            raise ValueError("scope closed")
        return 99

    def write(name, value):
        data.writes.append((name, value))
        data.members = {int(value)}

    def close():
        if data.cleanup == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED":
            data.closed = True
            stack.close()
        return {"status": data.cleanup}

    data.allocation = SimpleNamespace(
        _stack=stack,
        _identity=(28, 999),
        _check_identity=identity,
        _write=write,
        close_and_observe_empty=close,
    )
    monkeypatch.setattr(guardian, "_owned_live_generation", lambda pid: data.generation)
    monkeypatch.setattr(guardian, "_member_pids", lambda fd: data.members)

    def live(fd):
        if not data.alive:
            raise ValueError("dead pidfd")

    monkeypatch.setattr(guardian, "_pidfd_live", live)
    monkeypatch.setattr(
        os, "pidfd_open", lambda pid, flags: os.open("/dev/null", os.O_RDONLY)
    )
    yield data
    stack.close()


def test_success_requires_membership_and_generation_observation(state):
    b = guardian.GuardianBoundary(state.allocation)
    b.enrol_guardian(4321)
    result = b.observe_guardian_enrolment(4321)
    assert state.writes == [("cgroup.procs", "4321")]
    assert result == {
        "status": "ACTUAL_OS_GUARDIAN_ENROLMENT_OBSERVED",
        "pid": 4321,
        "start_ticks": 88,
        "scope_device": 28,
        "scope_inode": 999,
    }
    assert (
        b.close_and_observe_empty()["status"]
        == "ACTUAL_OS_DESCENDANT_SCOPE_EMPTY_OBSERVED"
    )
    with pytest.raises(ValueError):
        b.observe_guardian_enrolment(4321)


@pytest.mark.parametrize("failure", ["generation", "membership", "dead", "closed"])
def test_post_registration_drift_blocks_gate_and_is_sticky(state, failure):
    b = guardian.GuardianBoundary(state.allocation)
    b.enrol_guardian(4321)
    if failure == "generation":
        state.generation += 1
    if failure == "membership":
        state.members = {4321, 5555}
    if failure == "dead":
        state.alive = False
    if failure == "closed":
        state.closed = True
    with pytest.raises(ValueError):
        b.observe_guardian_enrolment(4321)
    state.generation, state.members, state.alive, state.closed = 88, {4321}, True, False
    with pytest.raises(ValueError):
        b.observe_guardian_enrolment(4321)


def test_nonempty_scope_never_receives_migration(state):
    state.members = {5555}
    b = guardian.GuardianBoundary(state.allocation)
    with pytest.raises(ValueError):
        b.enrol_guardian(4321)
    assert state.writes == []
    state.members = set()
    with pytest.raises(ValueError):
        b.enrol_guardian(4321)


def test_failed_write_cannot_become_observed_success(state):
    def fail(*args):
        raise PermissionError("migration denied")

    state.allocation._write = fail
    b = guardian.GuardianBoundary(state.allocation)
    with pytest.raises(PermissionError):
        b.enrol_guardian(4321)
    with pytest.raises(ValueError):
        b.observe_guardian_enrolment(4321)


def test_wrong_pid_and_repeat_enrollment_rejected(state):
    b = guardian.GuardianBoundary(state.allocation)
    b.enrol_guardian(4321)
    with pytest.raises(ValueError):
        b.observe_guardian_enrolment(4322)
    with pytest.raises(ValueError):
        b.enrol_guardian(4321)


def test_no_observation_without_enrollment(state):
    with pytest.raises(ValueError):
        guardian.GuardianBoundary(state.allocation).observe_guardian_enrolment(4321)


def test_cleanup_unknown_never_translates_to_actual_empty(state):
    b = guardian.GuardianBoundary(state.allocation)
    b.enrol_guardian(4321)
    state.cleanup = "OWNED_SCOPE_CLEANUP_UNKNOWN"
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    with pytest.raises(ValueError):
        b.observe_guardian_enrolment(4321)


def test_closed_allocation_never_acquires_process_handle(state, monkeypatch):
    state.closed = True
    monkeypatch.setattr(
        os, "pidfd_open", lambda *args: pytest.fail("acquired after close")
    )
    with pytest.raises(ValueError):
        guardian.GuardianBoundary(state.allocation).enrol_guardian(4321)


@pytest.mark.parametrize("members", ["garbage", "0", "-12", "+12", "１２"])
def test_malformed_membership_rejected(monkeypatch, members):
    monkeypatch.setattr(guardian, "_control", lambda *args: members)
    with pytest.raises(ValueError):
        guardian._member_pids(99)


def test_duplicate_kernel_membership_is_accepted(monkeypatch):
    monkeypatch.setattr(guardian, "_control", lambda *args: "42\n42\n43\n")
    assert guardian._member_pids(99) == {42, 43}


def test_actual_owned_child_identity_and_pidfd_without_migration():
    # No solver, gate opening, listener, or cgroup control writes.
    child = subprocess.Popen(
        [sys.executable, "-c", "import os; os.read(0, 1)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    fd = None
    try:
        generation = guardian._owned_live_generation(child.pid)
        assert generation > 0
        fd = os.pidfd_open(child.pid, 0)
        guardian._pidfd_live(fd)
        assert guardian._owned_live_generation(child.pid) == generation
        child.stdin.close()
        child.wait(timeout=5)
        with pytest.raises(ValueError):
            guardian._pidfd_live(fd)
        with pytest.raises(ChildProcessError):
            guardian._owned_live_generation(child.pid)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        if fd is not None:
            os.close(fd)
        if child.stdin is not None and not child.stdin.closed:
            child.stdin.close()


def test_current_process_is_not_an_owned_child():
    with pytest.raises(ValueError):
        guardian._owned_live_generation(os.getpid())


@pytest.fixture
def plan():
    return {
        "interface": "rc-b-E2-before-gate-descendant-boundary.v1",
        "guardian_enrolment_before_native_gate": True,
        "separate_browser_PG_covered": True,
        "all_descendant_cleanup_required": True,
        "linux_cgroup_v2": {
            "schema_version": "rc-cgroup-v2-boundary-config.v1",
            "parent_path": "/owned/task",
            "parent_device": 28,
            "parent_inode": 999,
            "exclusive_task_parent": True,
            "memory_bytes": 4096,
            "process_count": 8,
            "cpu_quota_us": None,
            "cpu_period_us": None,
            "cleanup_timeout_ms": 1000,
        },
    }


def test_adapter_factory_passes_exact_authored_configuration(plan, state, monkeypatch):
    from structural_analysis.execution import rc_cgroup_allocation

    calls = []

    def allocate(path, admission, limits, **kwargs):
        calls.append((path, admission, limits, kwargs))
        return state.allocation

    monkeypatch.setattr(rc_cgroup_allocation, "allocate_boundary", allocate)
    b = guardian.prepare_boundary(plan)
    assert isinstance(b, guardian.GuardianBoundary)
    assert len(calls) == 1
    path, admission, limits, kwargs = calls[0]
    assert path == "/owned/task"
    assert (admission.device, admission.inode, admission.exclusive_task_parent) == (
        28,
        999,
        True,
    )
    assert (limits.memory_bytes, limits.process_count) == (4096, 8)
    assert kwargs == {"cleanup_timeout_ms": 1000}


@pytest.mark.parametrize(
    "mutation", ["extra", "flag", "interface", "config_extra", "schema", "unpaired_cpu"]
)
def test_invalid_plan_cannot_allocate(plan, monkeypatch, mutation):
    from structural_analysis.execution import rc_cgroup_allocation

    monkeypatch.setattr(
        rc_cgroup_allocation,
        "allocate_boundary",
        lambda *args, **kwargs: pytest.fail("invalid plan allocated"),
    )
    if mutation == "extra":
        plan["unreviewed_override"] = True
    if mutation == "flag":
        plan["guardian_enrolment_before_native_gate"] = 1
    if mutation == "interface":
        plan["interface"] = "after-gate"
    if mutation == "config_extra":
        plan["linux_cgroup_v2"]["enable_parent_controllers"] = True
    if mutation == "schema":
        plan["linux_cgroup_v2"]["schema_version"] = "unknown"
    if mutation == "unpaired_cpu":
        plan["linux_cgroup_v2"]["cpu_quota_us"] = 1000
    with pytest.raises(ValueError):
        guardian.prepare_boundary(plan)


def test_factory_binding_failure_preserves_unknown_scope_handle(
    plan, state, monkeypatch
):
    from structural_analysis.execution import rc_cgroup_allocation

    state.allocation.name = "rc-job-test-owned"
    state.cleanup = "OWNED_SCOPE_CLEANUP_UNKNOWN"
    monkeypatch.setattr(
        rc_cgroup_allocation,
        "allocate_boundary",
        lambda *args, **kwargs: state.allocation,
    )

    def fail(*args):
        raise RuntimeError("binding failed")

    monkeypatch.setattr(guardian, "GuardianBoundary", fail)
    with pytest.raises(rc_cgroup_allocation.BoundarySetupError) as error:
        guardian.prepare_boundary(plan)
    assert error.value.boundary is state.allocation
    assert error.value.cleanup["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    assert "binding failed" in str(error.value.__cause__)
    assert "rc-job-test-owned" in str(error.value)
    assert "OWNED_SCOPE_CLEANUP_UNKNOWN" in str(error.value)
