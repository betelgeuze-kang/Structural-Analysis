"""The experimental gate uses only the already accepted prefix."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


PATH = Path(__file__).resolve().parents[1] / "scripts/run_rc_cost_gate_development_pilot.py"
SPEC = importlib.util.spec_from_file_location("rc_cost_gate_development_pilot", PATH)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def test_pre_capture_gate_has_exact_declared_schedule():
    decisions = [
        pilot.allow_cost_gate(
            SimpleNamespace(accepted_targets_m=tuple(range(index + 1))), 12
        )
        for index in range(12)
    ]
    assert decisions == [False, False, *([True] * 9), False]


def test_pre_capture_gate_rejects_changed_path_length_or_prefix():
    context = SimpleNamespace(accepted_targets_m=(0.0, 1.0, 2.0))
    with pytest.raises(ValueError, match="twelve-target"):
        pilot.allow_cost_gate(context, 11)
    with pytest.raises(ValueError, match="accepted prefix"):
        pilot.allow_cost_gate(SimpleNamespace(accepted_targets_m=()), 12)
