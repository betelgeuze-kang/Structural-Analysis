"""Incomplete schedules and unaccounted preload costs cannot qualify repeats."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "constant_repetition_summary", ROOT / "scripts/summarize_rc_constant_repetitions.py"
)
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def declarations():
    return {"repeat_count_after_admission": 3, "cases": ["a", "b"]}, {
        "failure": None,
        "rows": [
            {
                "stage": f"repeat-{i}",
                "exit_code": 0,
                "audits": [{"case": name, "exit_code": 0} for name in ("a", "b")],
            }
            for i in (1, 2, 3)
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "failed",
        "audit_missing",
        "audit_failed",
        "bool_exit",
        "duplicate_case",
    ],
)
def test_incomplete_or_relabelled_recorded_schedule_is_rejected(change):
    plan, outcome = declarations()
    if change == "missing":
        outcome["rows"].pop()
    elif change == "duplicate":
        outcome["rows"][2] = deepcopy(outcome["rows"][0])
    elif change == "failed":
        outcome["failure"] = {"kind": "KeyboardInterrupt"}
    elif change == "audit_missing":
        outcome["rows"][1]["audits"].pop()
    elif change == "audit_failed":
        outcome["rows"][1]["audits"][0]["exit_code"] = 1
    elif change == "bool_exit":
        outcome["rows"][1]["exit_code"] = False
    else:
        plan["cases"] = ["a", "a"]
    with pytest.raises(ValueError):
        summary.complete_schedule(plan, outcome)


def test_complete_recorded_schedule_only_passes_coverage_screen():
    # This helper does not authenticate these synthetic receipts or run an audit.
    summary.complete_schedule(*declarations())


def test_original_timing_counts_preload_solve_and_recovery(tmp_path):
    (tmp_path / "preload-recovery-outcome.json").write_text(
        json.dumps({"status": "returned", "wall_ns": 4, "cpu_ns": 2})
    )
    path = {
        "accepted_target_count": 1,
        "wall_ns": 40,
        "cpu_ns": 25,
        "preload_invocations": [{"wall_ns": 5, "cpu_ns": 2}],
        "entries": [
            {
                "proposal_wall_ns": 3,
                "proposal_cpu_ns": 1,
                "recovery_wall_ns": 6,
                "recovery_cpu_ns": 3,
                "invocations": [{"wall_ns": 10, "cpu_ns": 6}],
            }
        ],
    }
    costs = summary.original_path_costs(tmp_path, path, {"core_calls": 2})
    assert costs["core_wall_ns"] == 15 and costs["recovery_wall_ns"] == 10
    assert costs["core_cpu_ns"] == 8 and costs["recovery_cpu_ns"] == 5
    path["wall_ns"] = 27
    with pytest.raises(ValueError, match="nested time"):
        summary.original_path_costs(tmp_path, path, {"core_calls": 2})
    path["wall_ns"] = 40
    path["preload_invocations"][0]["wall_ns"] = -1
    with pytest.raises(ValueError, match="timing unavailable"):
        summary.original_path_costs(tmp_path, path, {"core_calls": 2})


def test_dispersion_retains_three_samples_and_signed_regression():
    result = summary.dist([-0.5, 1.0, -2.0])
    assert result["samples"] == [-0.5, 1.0, -2.0]
    assert result["median"] == -0.5 and result["minimum"] == -2.0
    with pytest.raises(ValueError, match="three paired"):
        summary.dist([1.0, 1.0])
