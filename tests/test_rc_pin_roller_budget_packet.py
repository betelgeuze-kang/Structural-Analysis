"""Frozen protocol and failure-accounting checks; no numerical qualification."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from structural_analysis.benchmark.rc_control_candidate_ranking import (
    candidate_ranking,
)


SOURCE = Path(__file__).resolve().parents[1]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "strategy",
    ("feasibility_then_price.v1", "feasibility_then_cheaper_boundary.v1"),
)
def test_frozen_packet_precedes_numerical_work_and_preserves_physical_scope(
    tmp_path, strategy
):
    runner = _script("run_rc_pin_roller_budget_study")
    output = tmp_path / "packet"
    plan = runner.prepare_packet(SOURCE, output, "a" * 40, strategy)
    assert plan["ranking_strategy"] == strategy
    assert plan["full_analysis_budget_per_online_arm_including_baseline"] == 3
    assert plan["full_pool_size_including_baseline"] == 6
    assert not set(plan["training_widths_m"]) & set(plan["online_widths_m"])
    assert plan["evaluate_exhaustive_oracle_after_online_arms"] is True
    assert plan["line_search_assembly_reuse"] is False
    assert plan["cost_dominance_pruning"] is False
    assert not (output / "training").exists()
    assert not (output / "search").exists()
    for name, expected in plan["input_sha256"].items():
        assert expected == "sha256:" + hashlib.sha256((output / "inputs" / name).read_bytes()).hexdigest()
    assert (output / "inputs" / "request.json").read_bytes() == (
        SOURCE / runner.REQUEST
    ).read_bytes()
    online = json.loads((output / "inputs" / "online-model.json").read_bytes())
    original = json.loads((SOURCE / runner.MODEL).read_bytes())
    assert online["sections"][0]["width_m"] == 0.42
    assert online["supports"] == original["supports"]
    assert online["loads"] == original["loads"]
    prices = json.loads((output / "inputs" / "online-experiment.json").read_bytes())[
        "prices"
    ]
    assert prices["concrete_per_m3"] == 100
    assert prices["rebar_per_kg"] == 1
    assert "Invented" in prices["source"]
    with pytest.raises(FileExistsError):
        runner.prepare_packet(SOURCE, output, "a" * 40, strategy)


def test_unsupported_strategy_does_not_create_a_packet(tmp_path):
    runner = _script("run_rc_pin_roller_budget_study")
    output = tmp_path / "packet"
    with pytest.raises(ValueError, match="unsupported ranking strategy"):
        runner.prepare_packet(SOURCE, output, "a" * 40, "unknown")
    assert not output.exists()


def test_boundary_audit_checks_declared_order_and_independent_scores():
    audit = _script("audit_rc_pin_roller_budget_study")
    prices = {"w34": 84.9, "w38": 89.5, "w46": 98.6, "w50": 103.2, "w54": 107.7}
    values = {"w34": .159036, "w38": .158871, "w46": .158539, "w50": .158300, "w54": .158190}
    predictions = [
        {
            "candidate_id": cid,
            "estimate": price,
            "ranking_tier": 0 if cid in ("w50", "w54") else 2,
            "predicted_screens": {
                "maximum_absolute_fiber_strain": {
                    "value": values[cid],
                    "limit": .1585,
                }
            },
        }
        for cid, price in prices.items()
    ]
    order, ranking = candidate_ranking(
        predictions, "feasibility_then_cheaper_boundary.v1"
    )
    assert order == ["w50", "w46", "w38", "w34", "w54"]
    plan = {
        "schema_version": "experimental-rc-control-candidate-search-plan.v3",
        "plans": {
            "price_order": {
                "ordering": ["w34", "w38", "w46", "w50", "w54"],
                "shortlist": ["w34", "w38"],
            },
            "learned_order": {"ordering": order, "shortlist": order[:2]},
        },
        "predictions": predictions,
        "ranking": ranking,
    }
    pre = {"ranking_strategy": "feasibility_then_cheaper_boundary.v1"}
    violations = []
    audit.check_frozen_ranking(pre, plan, lambda ok, reason: violations.append(reason) if not ok else None)
    assert violations == []
    damaged = deepcopy(plan)
    damaged["ranking"]["rows"][2]["relative_exceedance"] = 0.0
    damaged["plans"]["learned_order"]["shortlist"] = ["w50", "w54"]
    audit.check_frozen_ranking(pre, damaged, lambda ok, reason: violations.append(reason) if not ok else None)
    assert "w46 boundary score differs from frozen prediction" in violations
    assert "boundary learned shortlist unexpected" in violations


def test_failed_phase_retains_unknown_work_and_original_stderr(tmp_path, monkeypatch):
    runner = _script("run_rc_pin_roller_budget_study")
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 2, "", "solver error"),
    )
    with pytest.raises(RuntimeError, match="training failed"):
        runner._execute(SOURCE, tmp_path, "training", ["train"])
    outcome = json.loads((tmp_path / "training-outcome.json").read_bytes())
    assert outcome["status"] == "failed"
    assert outcome["unknown_work_until_outcome"] is True
    assert outcome["exit_code"] == 2
    assert (tmp_path / "training-stderr.txt").read_text() == "solver error"
    assert (tmp_path / "training-started.json").is_file()


def test_auditor_rejects_duplicate_json_keys(tmp_path):
    audit = _script("audit_rc_pin_roller_budget_study")
    file = tmp_path / "ambiguous.json"
    file.write_text('{"screens":{"limit":"pass","limit":"fail"}}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        audit.load(file)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_auditor_rejects_nonfinite_json_tokens(tmp_path, token):
    audit = _script("audit_rc_pin_roller_budget_study")
    file = tmp_path / "nonfinite.json"
    file.write_text('{"value":' + token + "}")
    with pytest.raises(ValueError, match="non-finite JSON token"):
        audit.load(file)
