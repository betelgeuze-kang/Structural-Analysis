"""Frozen protocol and failure-accounting checks; no numerical qualification."""

import hashlib
import importlib.util
import json
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
