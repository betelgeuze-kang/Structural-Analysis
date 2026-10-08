"""Read-only adapter tests; tmpfs fixtures are never enforcement receipts."""

import os
import sys
from dataclasses import replace

import pytest

from structural_analysis.execution import rc_cgroup_observer as observer
from structural_analysis.execution.rc_resource_boundary import (
    BoundaryAdmission,
    BoundaryLimits,
    preflight_boundary,
)


pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux cgroup descriptor contract"
)


@pytest.fixture
def parent(tmp_path, monkeypatch):
    for name, value in {
        "cgroup.type": "domain\n",
        "cgroup.controllers": "cpu memory pids\n",
        "cgroup.subtree_control": "memory pids\n",
        "cgroup.events": "populated 0\nfrozen 0\n",
    }.items():
        (tmp_path / name).write_text(value)
    identity = tmp_path.stat()
    admission = BoundaryAdmission(identity.st_dev, identity.st_ino, True)
    monkeypatch.setattr(observer, "_filesystem_type", lambda fd: "cgroup2")
    return tmp_path, admission


def test_observation_connects_to_preflight_without_cpu_delegation(parent):
    path, admission = parent
    with observer.open_boundary_parent(str(path), admission) as fd:
        result = observer.observe_boundary(fd)
        assert preflight_boundary(
            BoundaryLimits(4096, 8),
            admission,
            result,
            now_monotonic_ns=result.observed_monotonic_ns,
            maximum_age_ns=1,
        ) == {"memory.max": "4096", "pids.max": "8"}
        with pytest.raises(ValueError, match="controllers"):
            preflight_boundary(
                BoundaryLimits(4096, 8, 1000, 1000),
                admission,
                result,
                now_monotonic_ns=result.observed_monotonic_ns,
                maximum_age_ns=1,
            )
    with pytest.raises(OSError):
        os.fstat(fd)


def test_real_non_cgroup_directory_is_rejected(tmp_path):
    s = tmp_path.stat()
    with pytest.raises(ValueError, match="filesystem"):
        with observer.open_boundary_parent(
            str(tmp_path), BoundaryAdmission(s.st_dev, s.st_ino, True)
        ):
            pytest.fail("ordinary filesystem admitted")


@pytest.mark.parametrize(
    "text", ["", "populated 2\n", "populated 0\npopulated 1\n", "populated\n"]
)
def test_missing_or_malformed_events_rejected(parent, text):
    path, admission = parent
    (path / "cgroup.events").write_text(text)
    with observer.open_boundary_parent(str(path), admission) as fd:
        with pytest.raises(ValueError):
            observer.observe_boundary(fd)


@pytest.mark.parametrize(
    "name,value",
    [
        ("cgroup.type", "threaded"),
        ("cgroup.controllers", "cpu cpu"),
        ("cgroup.subtree_control", "+memory"),
        ("cgroup.events", "x" * 4097),
    ],
)
def test_invalid_controls_rejected(parent, name, value):
    path, admission = parent
    (path / name).write_text(value)
    with observer.open_boundary_parent(str(path), admission) as fd:
        with pytest.raises(ValueError):
            observer.observe_boundary(fd)


def test_control_symlink_rejected(parent):
    path, admission = parent
    (path / "cgroup.events").unlink()
    (path / "cgroup.events").symlink_to(path / "cgroup.controllers")
    with observer.open_boundary_parent(str(path), admission) as fd:
        with pytest.raises(OSError):
            observer.observe_boundary(fd)


def test_parent_symlink_rejected(parent, tmp_path_factory):
    path, admission = parent
    link = tmp_path_factory.mktemp("links") / "scope"
    link.symlink_to(path, target_is_directory=True)
    with pytest.raises(OSError):
        with observer.open_boundary_parent(str(link), admission):
            pytest.fail("symlink admitted")


def test_identity_drift_rejected(parent):
    path, admission = parent
    with pytest.raises(ValueError, match="identity"):
        with observer.open_boundary_parent(
            str(path), replace(admission, inode=admission.inode + 1)
        ):
            pytest.fail("changed identity admitted")


@pytest.mark.parametrize("path", ["relative", "/", "/tmp/../tmp", "/tmp//x", "/tmp/"])
def test_noncanonical_path_rejected(path):
    with pytest.raises(ValueError):
        with observer.open_boundary_parent(path, BoundaryAdmission(0, 1, True)):
            pytest.fail("noncanonical path admitted")


def test_held_descriptor_survives_path_replacement(parent):
    path, admission = parent
    with observer.open_boundary_parent(str(path), admission) as fd:
        moved = path.with_name(path.name + "-moved")
        path.rename(moved)
        path.mkdir()
        result = observer.observe_boundary(fd)
        assert result.inode == admission.inode
        assert result.inode != path.stat().st_ino


def test_observation_is_read_only(parent):
    path, admission = parent
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    with observer.open_boundary_parent(str(path), admission) as fd:
        observer.observe_boundary(fd)
    assert {p.name: p.read_bytes() for p in path.iterdir()} == before


def test_fifo_control_rejected_without_blocking(parent):
    path, admission = parent
    (path / "cgroup.events").unlink()
    os.mkfifo(path / "cgroup.events")
    with observer.open_boundary_parent(str(path), admission) as fd:
        with pytest.raises(ValueError, match="regular file"):
            observer.observe_boundary(fd)


def test_missing_control_is_not_an_empty_scope(parent):
    path, admission = parent
    (path / "cgroup.events").unlink()
    with observer.open_boundary_parent(str(path), admission) as fd:
        with pytest.raises(FileNotFoundError):
            observer.observe_boundary(fd)
