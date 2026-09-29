"""Frozen protocol and failure-accounting checks; no numerical qualification."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from subprocess import CompletedProcess

import pytest


SOURCE = Path(__file__).resolve().parents[1]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_packet_precedes_numerical_work_and_preserves_physical_scope(tmp_path):
    runner = _script("run_rc_pin_roller_budget_study")
    output = tmp_path / "packet"
    plan = runner.prepare_packet(SOURCE, output, "a" * 40)
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
        runner.prepare_packet(SOURCE, output, "a" * 40)


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
