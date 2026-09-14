"""Discovery and bounded subprocess controls; no test claims actual GPU execution."""

import sys
import time

import pytest
from structural_analysis.engine_v2_backends import local_amd_diagnostic as amd


def test_current_environment_has_no_acceleration_claim():
    result = amd.diagnose_amd_environment()
    assert not any(result["claims"].values())


def test_missing_runtime(monkeypatch):
    monkeypatch.setattr(amd.sys, "platform", "linux")
    monkeypatch.setattr(amd.shutil, "which", lambda name: None)
    result = amd.diagnose_amd_environment()
    assert result["status"] == "rocminfo_unavailable"
    assert result["probe"] is None


def test_reported_agent_is_not_a_qualified_solver(monkeypatch):
    monkeypatch.setattr(amd.sys, "platform", "linux")
    monkeypatch.setattr(amd.shutil, "which", lambda name: "/explicit-fixture/rocminfo")
    monkeypatch.setattr(
        amd,
        "_command",
        lambda command: {
            "status": "completed",
            "output_bytes": 30,
            "output_sha256": "a" * 64,
            "text": "  Name: gfx1030\n Name: gfx1030\n Name: cpu\nsecret-not-for-report",
        },
    )
    result = amd.diagnose_amd_environment()
    assert result["observed_agents"] == ["gfx1030"]
    assert result["status"] == "agents_detected_not_qualified"
    assert "secret-not-for-report" not in str(result)
    assert not any(result["claims"].values())


@pytest.mark.parametrize(
    "code,timeout,limit,expected",
    [
        ("print('ok')", 2, 100, "completed"),
        ("import sys;sys.exit(2)", 2, 100, "nonzero_exit"),
        ("import time;time.sleep(4)", 0.1, 100, "timeout"),
        ("print('x'*100000)", 2, 10, "output_limit"),
    ],
)
def test_subprocess_bounds(code, timeout, limit, expected):
    start = time.monotonic()
    result = amd._command(
        [sys.executable, "-c", code], timeout=timeout, maximum_bytes=limit
    )
    assert result["status"] == expected
    assert result["output_bytes"] <= limit
    assert time.monotonic() - start < 4


def test_nonlinux_never_launches(monkeypatch):
    monkeypatch.setattr(amd.sys, "platform", "win32")
    result = amd.diagnose_amd_environment()
    assert result["status"] == "unsupported_platform"
