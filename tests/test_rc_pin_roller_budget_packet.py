"""Frozen protocol and failure-accounting checks; no numerical qualification."""

import hashlib
import importlib.util
import json
import subprocess
import sys
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
            "prediction": {"abstained": False},
            "predicted_screens": {
                "maximum_absolute_fiber_strain": {
                    "value": values[cid],
                    "limit": .1585,
                    "status": "pass" if cid in ("w50", "w54") else "fail",
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
        "pool": [{"candidate_id": "baseline"}] + [
            {"candidate_id": cid, "material_estimate": {"total": price}}
            for cid, price in prices.items()
        ],
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
    pre = {
        "ranking_strategy": "feasibility_then_cheaper_boundary.v1",
        "online_widths_m": [0.42, 0.34, 0.38, 0.46, 0.50, 0.54],
        "full_analysis_budget_per_online_arm_including_baseline": 3,
    }
    violations = []
    audit.check_frozen_ranking(pre, plan, lambda ok, reason: violations.append(reason) if not ok else None)
    assert violations == []
    damaged = deepcopy(plan)
    damaged["ranking"]["rows"][2]["relative_exceedance"] = 0.0
    damaged["plans"]["learned_order"]["shortlist"] = ["w50", "w54"]
    audit.check_frozen_ranking(pre, damaged, lambda ok, reason: violations.append(reason) if not ok else None)
    assert "w46 boundary score differs from frozen prediction" in violations
    assert "boundary learned shortlist unexpected" in violations


def test_new_replication_protocol_is_frozen_before_any_numerical_work(tmp_path):
    from scripts import run_rc_pin_roller_replication as runner
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True
    ).strip()
    output = tmp_path / "packet"
    plan = runner.prepare_packet(SOURCE, output, revision)
    protocol = json.loads((SOURCE / runner.PROTOCOL).read_bytes())
    assert plan["protocol_commit"] == runner.PROTOCOL_COMMIT
    assert plan["protocol_sha256"] == runner.PROTOCOL_SHA
    assert plan["training_widths_m"] == protocol["training_widths_m"]
    assert plan["online_widths_m"] == protocol["online_widths_m"]
    assert plan["ranking_strategy"] == protocol["ranking_strategy"]
    assert not set(plan["training_widths_m"]) & set(plan["online_widths_m"])
    assert not (output / "training").exists()
    assert not (output / "search").exists()
    source_model = json.loads((SOURCE / protocol["source_model"]).read_bytes())
    online = json.loads((output / "inputs" / "online-model.json").read_bytes())
    assert online["sections"][0]["width_m"] == protocol["online_widths_m"][0]
    assert online["supports"] == source_model["supports"]
    assert online["loads"] == source_model["loads"]
    assert (output / "inputs" / "request.json").read_bytes() == (
        SOURCE / protocol["source_request"]
    ).read_bytes()
    with pytest.raises(FileExistsError):
        runner.prepare_packet(SOURCE, output, revision)


def test_ranking_audit_uses_new_pool_and_rejects_posthoc_shortlist():
    audit = _script("audit_rc_pin_roller_budget_study")
    prices = {"w34": 1.0, "w38": 2.0, "w42": 3.0, "w46": 4.0, "w52": 5.0}
    predictions = [
        {
            "candidate_id": cid,
            "estimate": price,
            "prediction": {"abstained": False},
            "ranking_tier": 0 if cid == "w46" else 2,
            "predicted_screens": {
                "maximum_absolute_fiber_strain": {
                    "value": 0.1 if cid == "w46" else 0.21 + i * 0.01,
                    "limit": 0.2,
                    "status": "pass" if cid == "w46" else "fail",
                }
            },
        }
        for i, (cid, price) in enumerate(prices.items())
    ]
    order, ranking = candidate_ranking(
        predictions, "feasibility_then_cheaper_boundary.v1"
    )
    pre = {
        "ranking_strategy": "feasibility_then_cheaper_boundary.v1",
        "online_widths_m": [0.44, 0.34, 0.38, 0.42, 0.46, 0.52],
        "full_analysis_budget_per_online_arm_including_baseline": 3,
    }
    plan = {
        "schema_version": "experimental-rc-control-candidate-search-plan.v3",
        "pool": [{"candidate_id": "baseline"}] + [
            {"candidate_id": cid, "material_estimate": {"total": price}}
            for cid, price in prices.items()
        ],
        "plans": {
            "price_order": {"ordering": list(prices), "shortlist": list(prices)[:2]},
            "learned_order": {"ordering": order, "shortlist": order[:2]},
        },
        "predictions": predictions,
        "ranking": ranking,
    }
    violations = []
    audit.check_frozen_ranking(pre, plan, lambda ok, reason: violations.append(reason) if not ok else None)
    assert violations == []
    changed = deepcopy(plan)
    changed["plans"]["learned_order"]["shortlist"] = ["w52", "w34"]
    audit.check_frozen_ranking(pre, changed, lambda ok, reason: violations.append(reason) if not ok else None)
    assert "boundary learned shortlist unexpected" in violations


def test_incomplete_replication_audit_keeps_unknown_total_cost(tmp_path):
    packet = tmp_path / "packet"
    packet.mkdir()
    (packet / "plan.json").write_text('{"schema":"interrupted"}\n')
    (packet / "training-outcome.json").write_text(
        '{"phase":"training","status":"failed","wall_ns":123,"unknown_work_until_outcome":true}\n'
    )
    output = tmp_path / "audit.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SOURCE / "scripts" / "audit_rc_pin_roller_budget_study.py"),
            "--protocol",
            "examples/research/rc_reuse_campaign/pin-roller-replication.protocol.json",
            "--packet", str(packet),
            "--output", str(output),
        ],
        cwd=SOURCE,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    result = json.loads(output.read_bytes())
    assert result["status"] == "incomplete_or_unverifiable"
    assert result["total_evaluation_cost_ns"] is None
    assert result["selected_candidate_id"] is None
    assert result["launcher_phase_outcomes"]["training"]["wall_ns"] == 123
    assert result["launcher_phase_outcomes"]["search"] is None


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


def _verified_row_claims():
    first = {
        "node_displacements": [{"UX_m": 3.0, "UY_m": 4.0, "UZ_m": 0.0}],
        "fiber_results": [
            {"material_kind": "concrete", "strain": -0.25, "material_state": {"tensile_damage": 0.1, "compressive_damage": 0.2}},
            {"material_kind": "steel", "strain": 0.125, "material_state": {"accumulated_plastic_strain": 0.05}},
        ],
        "load_factor": 2.0,
    }
    last = {
        "node_displacements": [{"UX_m": 0.0, "UY_m": 6.0, "UZ_m": 8.0}],
        "fiber_results": [
            {"material_kind": "concrete", "strain": -0.125, "material_state": {"tensile_damage": 0.3, "compressive_damage": 0.4}},
            {"material_kind": "steel", "strain": 0.0625, "material_state": {"accumulated_plastic_strain": 0.1}},
        ],
        "load_factor": -1.0,
    }
    result = {"response_history": [first, last]}
    request = {}
    performance = {
        "maximum_translation_m": 10.0,
        "maximum_absolute_fiber_strain": 0.25,
        "terminal_maximum_translation_m": 10.0,
        "terminal_maximum_absolute_fiber_strain": 0.125,
        "maximum_steel_accumulated_plastic_strain": 0.1,
        "maximum_concrete_tensile_damage": 0.3,
        "maximum_concrete_compressive_damage": 0.4,
        "terminal_load_factor": -1.0,
        "minimum_load_factor": -1.0,
        "maximum_load_factor": 2.0,
        "accepted_epoch_count": 2,
    }
    comparison = {
        "history_limits": {"maximum_absolute_fiber_strain": 0.3},
        "material_limits": {"maximum_steel_accumulated_plastic_strain": 0.2},
        "terminal_limits": {"maximum_translation_m": 12.0},
    }
    row = {
        "candidate_id": "w54",
        "performance": performance,
        "screens": {
            "maximum_absolute_fiber_strain": {"value": 0.25, "limit": 0.3, "status": "pass"},
            "maximum_steel_accumulated_plastic_strain": {"value": 0.1, "limit": 0.2, "status": "pass"},
            "terminal_maximum_translation_m": {"value": 10.0, "limit": 12.0, "status": "pass"},
        },
        "selection_eligible": True,
    }
    comparison["rows"] = [row]
    return result, request, comparison


@pytest.mark.parametrize("mutation", ["eligibility", "coherent_screen", "metric_type"])
def test_rehashed_row_claims_must_match_own_original_result(mutation):
    audit = _script("audit_rc_pin_roller_budget_study")
    result, request, comparison = _verified_row_claims()
    row = comparison["rows"][0]
    assert audit.verified_row_claim_violations(row, result, comparison, request) == []
    if mutation == "eligibility":
        row["selection_eligible"] = False
    elif mutation == "coherent_screen":
        row["screens"]["maximum_absolute_fiber_strain"] = {"value": 0.6, "limit": 0.3, "status": "fail"}
        row["selection_eligible"] = False
    else:
        row["performance"]["maximum_concrete_compressive_damage"] = False
    comparison["report_hash"] = audit.sha(audit.canonical(comparison))
    assert audit.check_hash_object(comparison, "report_hash")
    violations = audit.verified_row_claim_violations(row, result, comparison, request)
    assert violations
    if mutation == "eligibility":
        assert violations == ["selection eligibility differs from original result screens"]
    elif mutation == "coherent_screen":
        assert "screens differ from original result and frozen limits" in violations
    else:
        assert "performance differs from original result history" in violations


def test_preload_is_included_in_whole_history_but_not_terminal_metrics():
    audit = _script("audit_rc_pin_roller_budget_study")
    result, _, comparison = _verified_row_claims()
    result = deepcopy(result)
    result["preload_response"] = {
        "node_displacements": [{"UX_m": 0.0, "UY_m": 0.0, "UZ_m": 12.0}],
        "fiber_results": [
            {"material_kind": "concrete", "strain": -0.5, "material_state": {"tensile_damage": 0.0, "compressive_damage": 0.0}},
        ],
        "load_factor": 0.0,
    }
    request = {"constant_nodal_loads": [{"node_id": "N1"}]}
    performance = audit.derived_performance(result, request)
    assert performance["maximum_translation_m"] == 12.0
    assert performance["maximum_absolute_fiber_strain"] == 0.5
    assert performance["terminal_maximum_translation_m"] == 10.0
    assert performance["terminal_maximum_absolute_fiber_strain"] == 0.125
    assert performance["accepted_epoch_count"] == 3
    assert audit.verified_row_claim_violations(comparison["rows"][0], result, comparison, request)
