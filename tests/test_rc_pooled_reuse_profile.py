"""Bind the pooled runner's selected assembly reuse profile across its receipts."""

import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "rc-control-immediate-line-search-reuse.v1"


@pytest.mark.parametrize("reuse", [False, True])
def test_pooled_runner_freezes_profile_and_passes_it_to_child(
    tmp_path, monkeypatch, reuse
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    runner = importlib.import_module("run_rc_pooled_runtime_campaign")
    cases = [SimpleNamespace(case_id="train", split="train"),
             SimpleNamespace(case_id="reserved", split="holdout")]
    monkeypatch.setattr(runner, "inputs", lambda *_: (cases, [], None, [], []))
    policy = SimpleNamespace(policy_hash="policy", to_dict=lambda: {"policy_hash": "policy"})
    monkeypatch.setattr(runner.learning, "_fit", lambda *args, **kwargs: policy)
    calls = []

    def child(received_cases, samples, selected_policy, **kwargs):
        assert received_cases is cases
        assert samples == [] and selected_policy is policy
        calls.append(kwargs)
        return {"result_hash": "result", "selected_strategy": "secant"}

    monkeypatch.setattr(runner, "run_rc_control_runtime_selection", child)
    output = tmp_path / "study"
    argv = [
        "run_rc_pooled_runtime_campaign.py",
        "--old-labels", str(tmp_path / "old"),
        "--new-labels", str(tmp_path / "new"),
        "--source-revision", "a" * 40,
        "--output", str(output),
    ]
    if reuse:
        argv.append("--reuse-line-search-assembly")
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    declared = json.loads((output / "plan.json").read_text())
    assert declared["selected_assembly_reuse_profile"] == (PROFILE if reuse else None)
    assert len(calls) == 1
    assert calls[0]["reuse_line_search_assembly"] is reuse
    assert calls[0]["withholding_strategy"] == "connected_training_groups"


@pytest.mark.parametrize("reuse", [False, True])
def test_pooled_audit_rejects_profile_drift_in_child_and_benchmark(
    monkeypatch, reuse
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    audit = importlib.import_module("audit_rc_pooled_runtime_campaign")
    key = "line_search_assembly_reuse"
    chosen = {key: PROFILE} if reuse else {}
    source = {"selected_assembly_reuse_profile": PROFILE if reuse else None}
    plan = {
        "source_revision": "source",
        "cases": [{"case_id": "train", "split": "train",
                   "model_hash": "model", "request": {"targets_m": [0.001]}}],
        **chosen,
    }
    result = dict(chosen)
    report = {
        "source_revision": "source", "model_checksum": "model",
        "request": {"targets_m": [0.001]}, **chosen,
    }

    audit.require_assembly_reuse_profile(source, plan, result)
    audit.require_report_binding(plan, "train", report)

    def drift(receipt):
        changed = dict(receipt)
        if reuse:
            changed.pop(key)
        else:
            changed[key] = PROFILE
        return changed

    with pytest.raises(ValueError, match="selected assembly reuse profile differs"):
        audit.require_assembly_reuse_profile(source, drift(plan), result)
    with pytest.raises(ValueError, match="selected assembly reuse profile differs"):
        audit.require_assembly_reuse_profile(source, plan, drift(result))
    with pytest.raises(ValueError, match="comparison assembly reuse profile binding"):
        audit.require_report_binding(plan, "train", drift(report))
    with pytest.raises(ValueError, match="unsupported selected assembly reuse profile"):
        audit.require_assembly_reuse_profile(
            {"selected_assembly_reuse_profile": "unknown"}, plan, result
        )
