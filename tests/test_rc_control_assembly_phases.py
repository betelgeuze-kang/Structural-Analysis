"""Incomplete and failed evidence cannot masquerade as zero successful work."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark.rc_control_assembly_phases import (
    summarize_rc_control_assembly_phases,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha


def path(status="raised"):
    work = {
        "schema_version": "vector-newton-assembly-dispatch-work.v1",
        "call_count": 1,
        "returned_count": int(status == "returned"),
        "exception_count": int(status == "raised"),
        "in_flight_count": int(status == "started"),
        "calls": [{"ordinal": 1, "phase": "line_search", "status": status}],
    }
    return {
        "status": "incomplete",
        "entries": [{"invocations": [{"newton_assembly_work": work}]}],
    }


def summarize(p):
    p = deepcopy(p)
    p["path_hash"] = _sha(_bytes(p))
    return summarize_rc_control_assembly_phases(p)


def test_failed_dispatch_is_retained_without_success_claim():
    result = summarize(path())
    assert result["phase_counts"] == {"line_search": 1}
    assert result["raised_dispatch_count"] == 1
    assert result["path_status"] == "incomplete"
    assert result["physical_validation"] is False


def test_missing_record_preserves_partial_counts_and_unknown_total():
    p = path("returned")
    p["preload_invocations"] = [{}]
    result = summarize(p)
    assert result["observed_phase_counts"] == {"line_search": 1}
    assert result["missing_record_count"] == 1
    assert result["phase_counts"] is result["dispatch_count"] is None


def test_inflight_dispatch_is_observed_but_not_complete_work():
    result = summarize(path("started"))
    assert result["observed_phase_counts"] == {"line_search": 1}
    assert result["in_flight_count"] == 1
    assert result["phase_counts"] is result["dispatch_count"] is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("call_count", True),
        ("returned_count", 1),
        ("exception_count", 0),
        ("line_search_reuse_hit_count", -1),
    ],
)
def test_inconsistent_or_invalid_counts_rejected(key, value):
    p = path()
    p["entries"][0]["invocations"][0]["newton_assembly_work"][key] = value
    with pytest.raises(ValueError):
        summarize(p)


def test_tampered_path_hash_rejected():
    p = path()
    p["path_hash"] = _sha(_bytes(p))
    p["status"] = "complete"
    with pytest.raises(ValueError, match="hash differs"):
        summarize_rc_control_assembly_phases(p)


def test_reuse_hits_are_not_counted_as_dispatches():
    p = path("returned")
    p["entries"][0]["invocations"][0]["newton_assembly_work"][
        "line_search_reuse_hit_count"
    ] = 3
    result = summarize(p)
    assert result["observed_line_search_reuse_hits"] == 3
    assert result["dispatch_count"] == 1


def timed_path(status="returned"):
    from structural_analysis.solvers.nonlinear.assembly_work import (
        ASSEMBLY_TIMING_SCOPE,
    )

    p = path(status)
    work = p["entries"][0]["invocations"][0]["newton_assembly_work"]
    work["timing_scope"] = ASSEMBLY_TIMING_SCOPE
    work["wall_ns"] = 17 if status != "started" else None
    work["calls"][0]["wall_ns"] = work["wall_ns"]
    return p


@pytest.mark.parametrize("status", ["returned", "raised"])
def test_timed_completed_dispatches_include_failures(status):
    result = summarize(timed_path(status))
    assert result["phase_wall_ns"] == {"line_search": 17}
    assert result["physical_validation"] is False


def test_partial_or_mixed_timing_stays_unknown():
    p = timed_path("started")
    assert summarize(p)["phase_wall_ns"] is None
    p = timed_path()
    p["preload_invocations"] = path()["entries"][0]["invocations"]
    assert summarize(p)["phase_wall_ns"] is None


@pytest.mark.parametrize("value", [True, -1, None, 1.5])
def test_invalid_timing_value_rejected(value):
    p = timed_path()
    p["entries"][0]["invocations"][0]["newton_assembly_work"]["calls"][0]["wall_ns"] = (
        value
    )
    with pytest.raises(ValueError):
        summarize(p)


def test_inconsistent_timing_total_rejected():
    p = timed_path()
    p["entries"][0]["invocations"][0]["newton_assembly_work"]["wall_ns"] = 18
    with pytest.raises(ValueError, match="timing total"):
        summarize(p)
