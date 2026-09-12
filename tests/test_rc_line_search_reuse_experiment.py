"""Boundaries of the serial research-only, immediate assembly reuse experiment."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location(
    "reuse_experiment",
    Path(__file__).resolve().parents[1] / "scripts/diagnose_rc_control_line_search_reuse.py",
)
experiment = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(experiment)


class Adapter:
    pass


def setup():
    calls = []
    result = (np.array([2.0]), np.array([[3.0]]))

    def dispatch(problem, coordinates, **kwargs):
        calls.append((problem, coordinates, kwargs))
        return result

    return experiment.ImmediateLineSearchReuse(dispatch, adapter_type=Adapter), calls, result


def test_one_use_copy_and_original_recorder_only_on_real_dispatch():
    reuse, calls, result = setup()
    adapter, recorder = Adapter(), object()
    reuse(adapter, np.array([1.0]), phase="line_search", recorder=recorder)
    result[0][0] = 99  # retained arrays cannot alias a mutable dispatch result
    hit = reuse(adapter, np.array([1.0]), phase="primary_iteration", recorder=recorder)
    assert hit[0][0] == 2 and reuse.hits == 1 and len(calls) == 1
    assert calls[0][2]["recorder"] is recorder
    reuse(adapter, np.array([1.0]), phase="primary_iteration", recorder=recorder)
    assert len(calls) == 2  # consumed, never a persistent coordinate cache


@pytest.mark.parametrize("boundary", [
    "new_adapter", "subclass", "compensation", "final_observation",
    "terminal_refinement", "blocked_observation", "coordinate", "dtype", "signed_zero",
])
def test_cache_does_not_cross_identity_arithmetic_or_observation_boundaries(boundary):
    reuse, calls, _ = setup()
    adapter = Adapter()
    x = np.array([0.0])
    reuse(adapter, x, phase="line_search")
    problem, phase, compensation = adapter, "primary_iteration", None
    if boundary == "new_adapter":
        problem = Adapter()
    elif boundary == "subclass":
        problem = type("Derived", (Adapter,), {})()
    elif boundary == "compensation":
        compensation = np.array([0.0])
    elif boundary in ("final_observation", "terminal_refinement", "blocked_observation"):
        phase = boundary
    elif boundary == "coordinate":
        x = np.array([1.0])
    elif boundary == "dtype":
        x = x.astype(np.float32)
    elif boundary == "signed_zero":
        x = np.array([-0.0])
    reuse(problem, x, phase=phase, compensation=compensation)
    assert len(calls) == 2 and reuse.hits == 0
    reuse(adapter, np.array([0.0]), phase="primary_iteration")
    assert len(calls) == 3  # intervening call invalidates the entry


def test_exception_is_preserved_and_invalidates_previous_entry():
    reuse, calls, _ = setup()
    adapter = Adapter()
    reuse(adapter, np.array([1.0]), phase="line_search")
    original = reuse.dispatch
    error = RuntimeError("assembly failed")

    def fail(*args, **kwargs):
        raise error

    reuse.dispatch = fail
    with pytest.raises(RuntimeError) as observed:
        reuse(adapter, np.array([2.0]), phase="line_search")
    assert observed.value is error
    reuse.dispatch = original
    reuse(adapter, np.array([1.0]), phase="primary_iteration")
    assert len(calls) == 2 and reuse.hits == 0
