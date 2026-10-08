"""Pure preflight checks: no kernel writes, processes, or solver executions."""

from dataclasses import replace

import pytest

from structural_analysis.execution.rc_resource_boundary import (
    BoundaryAdmission,
    BoundaryLimits,
    BoundaryObservation,
    preflight_boundary,
)


ADMISSION = BoundaryAdmission(42, 123, True)
OBSERVATION = BoundaryObservation(
    42,
    123,
    "cgroup2",
    "domain",
    frozenset({"memory", "pids", "cpu"}),
    frozenset({"memory", "pids", "cpu"}),
    False,
    100,
)


def check(limits=None, admission=ADMISSION, observation=OBSERVATION, **kwargs):
    return preflight_boundary(
        limits or BoundaryLimits(4096, 8),
        admission,
        observation,
        now_monotonic_ns=kwargs.get("now", 101),
        maximum_age_ns=kwargs.get("age", 10),
    )


def test_memory_and_process_limits_do_not_claim_cpu_or_storage_bounds():
    assert check() == {"memory.max": "4096", "pids.max": "8"}


def test_cpu_bandwidth_requires_explicit_paired_limits():
    assert check(BoundaryLimits(4096, 8, 2000, 10000))["cpu.max"] == "2000 10000"


@pytest.mark.parametrize(
    "field,value",
    [
        ("memory_bytes", True),
        ("memory_bytes", 0),
        ("memory_bytes", 2**63),
        ("process_count", -1),
        ("process_count", 1.5),
        ("cpu_quota_us", 2000),
        ("cpu_period_us", 10000),
    ],
)
def test_invalid_limits_fail_before_any_adapter_activity(field, value):
    with pytest.raises(ValueError):
        BoundaryLimits(**({"memory_bytes": 4096, "process_count": 8} | {field: value}))


@pytest.mark.parametrize(
    "quota,period", [(True, 1000), (999, 1000), (1000, 999), (1000, 1000001)]
)
def test_invalid_cpu_range(quota, period):
    with pytest.raises(ValueError):
        BoundaryLimits(4096, 8, quota, period)


@pytest.mark.parametrize(
    "changes",
    [
        {"device": 43},
        {"inode": 124},
        {"filesystem": "tmpfs"},
        {"cgroup_type": "threaded"},
        {"cgroup_type": "domain invalid"},
        {"populated": True},
        {"populated": 0},
        {"available_controllers": frozenset({"memory"})},
        {"enabled_child_controllers": frozenset()},
        {"available_controllers": "memory pids cpu"},
        {"observed_monotonic_ns": 102},
        {"observed_monotonic_ns": 0},
    ],
)
def test_drift_and_unsupported_boundaries_rejected(changes):
    with pytest.raises(ValueError):
        check(observation=replace(OBSERVATION, **changes))


def test_available_cpu_is_insufficient_when_not_enabled_for_children():
    with pytest.raises(ValueError, match="controllers"):
        check(
            BoundaryLimits(4096, 8, 2000, 10000),
            observation=replace(
                OBSERVATION,
                enabled_child_controllers=frozenset({"memory", "pids"}),
            ),
        )


@pytest.mark.parametrize("exclusive", [False, 1, "true", None])
def test_shared_scope_is_not_admitted(exclusive):
    with pytest.raises(ValueError):
        check(admission=replace(ADMISSION, exclusive_task_parent=exclusive))


@pytest.mark.parametrize(
    "kwargs", [{"now": True}, {"age": 0}, {"age": -1}, {"now": 111}]
)
def test_invalid_or_expired_observation_clock(kwargs):
    with pytest.raises(ValueError):
        check(**kwargs)
