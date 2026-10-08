"""Synthetic control files exercise lifecycle failures, never kernel enforcement."""

import os
from pathlib import Path
import sys

import pytest

from structural_analysis.execution import rc_cgroup_allocation as allocation
from structural_analysis.execution import rc_cgroup_observer as observer
from structural_analysis.execution.rc_resource_boundary import (
    BoundaryAdmission,
    BoundaryLimits,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux cgroup adapter")


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    def controls(path):
        values = {
            "cgroup.type": "domain\n",
            "cgroup.controllers": "memory pids cpu\n",
            "cgroup.subtree_control": "memory pids cpu\n",
            "cgroup.events": "populated 0\n",
            "memory.max": "",
            "pids.max": "",
            "cpu.max": "",
            "cgroup.kill": "",
            "cgroup.max.depth": "",
            "cgroup.max.descendants": "",
        }
        for name, value in values.items():
            (path / name).write_text(value)

    controls(tmp_path)
    original_mkdir, original_rmdir = os.mkdir, os.rmdir

    def mkdir(name, mode=0o777, *, dir_fd=None):
        original_mkdir(name, mode, dir_fd=dir_fd)
        if dir_fd is not None and name.startswith("rc-job-"):
            controls(Path(os.readlink(f"/proc/self/fd/{dir_fd}")) / name)

    def rmdir(name, *, dir_fd=None):
        if dir_fd is not None and name.startswith("rc-job-"):
            path = Path(os.readlink(f"/proc/self/fd/{dir_fd}")) / name
            for item in path.iterdir():
                if item.is_file():
                    item.unlink()
        original_rmdir(name, dir_fd=dir_fd)

    monkeypatch.setattr(observer, "_filesystem_type", lambda fd: "cgroup2")
    monkeypatch.setattr(os, "mkdir", mkdir)
    monkeypatch.setattr(os, "rmdir", rmdir)
    info = tmp_path.stat()
    admission = BoundaryAdmission(info.st_dev, info.st_ino, True)
    return tmp_path, admission


def prepare(kernel, **kwargs):
    path, admission = kernel
    return allocation.allocate_boundary(
        str(path), admission, BoundaryLimits(4096, 8, 1000, 10000), **kwargs
    )


def test_allocate_verify_cleanup_only_owned_child(kernel):
    path, _ = kernel
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    b = prepare(kernel)
    child = path / b.name
    assert (child / "memory.max").read_text() == "4096"
    assert (child / "cpu.max").read_text() == "1000 10000"
    assert (child / "cgroup.max.depth").read_text() == "0"
    fd = b._child_fd
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"
    assert not child.exists()
    assert {p.name: p.read_bytes() for p in path.iterdir()} == before
    with pytest.raises(OSError):
        os.fstat(fd)


def test_unenabled_controller_prevents_allocation(kernel):
    path, _ = kernel
    (path / "cgroup.subtree_control").write_text("memory pids")
    with pytest.raises(ValueError, match="controllers"):
        prepare(kernel)
    assert not list(path.glob("rc-job-*"))


def test_limit_readback_failure_cleans_new_scope(kernel, monkeypatch):
    original = allocation._control
    monkeypatch.setattr(
        allocation,
        "_control",
        lambda fd, name: "max" if name == "memory.max" else original(fd, name),
    )
    with pytest.raises(allocation.BoundarySetupError) as error:
        prepare(kernel)
    assert error.value.cleanup["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"
    assert "readback mismatch" in str(error.value.__cause__)
    assert not list(kernel[0].glob("rc-job-*"))


def test_kill_failure_remains_unknown_and_can_retry(kernel, monkeypatch):
    b = prepare(kernel)
    original = b._write
    monkeypatch.setattr(
        b, "_write", lambda *args: (_ for _ in ()).throw(PermissionError("denied"))
    )
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    assert (kernel[0] / b.name).exists()
    os.fstat(b._child_fd)
    monkeypatch.setattr(b, "_write", original)
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"


def test_populated_timeout_is_not_empty(kernel):
    b = prepare(kernel, cleanup_timeout_ms=1)
    (kernel[0] / b.name / "cgroup.events").write_text("populated 1\n")
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    (kernel[0] / b.name / "cgroup.events").write_text("populated 0\n")
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"


def test_replaced_scope_is_not_killed_or_removed(kernel):
    path, _ = kernel
    b = prepare(kernel)
    moved = path / "held-original"
    (path / b.name).rename(moved)
    (path / b.name).mkdir()
    replacement = path / b.name
    (replacement / "cgroup.kill").write_text("")
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    assert (replacement / "cgroup.kill").read_text() == ""
    assert (moved / "cgroup.kill").read_text() == ""
    # Restore fixture identity solely so the test releases retained descriptors.
    for item in replacement.iterdir():
        item.unlink()
    replacement.rmdir()
    moved.rename(replacement)
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"


def test_missing_event_never_becomes_success(kernel):
    b = prepare(kernel)
    event = kernel[0] / b.name / "cgroup.events"
    event.unlink()
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    event.write_text("populated 0\n")
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"


@pytest.mark.parametrize("value", [True, 0, -1, 5001, 1.5])
def test_invalid_cleanup_budget_does_not_create(kernel, value):
    with pytest.raises(ValueError):
        prepare(kernel, cleanup_timeout_ms=value)
    assert not list(kernel[0].glob("rc-job-*"))


def test_existing_name_is_never_adopted(kernel, monkeypatch):
    class Fixed:
        hex = "a" * 32

    monkeypatch.setattr(allocation.uuid, "uuid4", lambda: Fixed())
    existing = kernel[0] / ("rc-job-" + Fixed.hex)
    existing.mkdir()
    (existing / "sentinel").write_text("preserve")
    with pytest.raises(allocation.BoundarySetupError) as error:
        prepare(kernel)
    assert isinstance(error.value.__cause__, FileExistsError)
    assert error.value.cleanup["status"] == "NO_SCOPE_CREATED"
    assert (
        error.value.boundary.close_and_observe_empty()["status"] == "NO_SCOPE_CREATED"
    )
    assert (existing / "sentinel").read_text() == "preserve"


def test_setup_and_cleanup_failures_preserve_both_outcomes(kernel, monkeypatch):
    original = allocation.CgroupAllocation._write

    def fail(self, name, value):
        if name == "memory.max":
            raise OSError("original limit failure")
        if name == "cgroup.kill":
            raise PermissionError("cleanup denied")
        return original(self, name, value)

    monkeypatch.setattr(allocation.CgroupAllocation, "_write", fail)
    with pytest.raises(allocation.BoundarySetupError) as error:
        prepare(kernel)
    assert "original limit failure" in str(error.value.__cause__)
    assert error.value.cleanup["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    assert "cleanup denied" in error.value.cleanup["reason"]
    monkeypatch.setattr(allocation.CgroupAllocation, "_write", original)
    assert (
        error.value.boundary.close_and_observe_empty()["status"]
        == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"
    )


def test_symlink_control_is_not_written(kernel):
    b = prepare(kernel)
    path = kernel[0] / b.name / "cgroup.kill"
    path.unlink()
    target = kernel[0] / "outside-sentinel"
    target.write_text("preserve")
    path.symlink_to(target)
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    assert target.read_text() == "preserve"
    path.unlink()
    path.write_text("")
    assert b.close_and_observe_empty()["status"] == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"


def test_unwritable_kill_interface_prevents_ready_allocation(kernel, monkeypatch):
    original = os.open

    def deny_kill(path, flags, *args, **kwargs):
        if path == "cgroup.kill" and flags & os.O_WRONLY:
            raise PermissionError("kill interface denied")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", deny_kill)
    with pytest.raises(allocation.BoundarySetupError) as error:
        prepare(kernel)
    assert "kill interface denied" in str(error.value.__cause__)
    assert error.value.cleanup["status"] == "OWNED_SCOPE_CLEANUP_UNKNOWN"
    monkeypatch.setattr(os, "open", original)
    assert (
        error.value.boundary.close_and_observe_empty()["status"]
        == "OWNED_SCOPE_REMOVED_EMPTY_OBSERVED"
    )
