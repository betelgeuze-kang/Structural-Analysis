"""The experimental gate uses only the already accepted prefix."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts/run_rc_cost_gate_development_pilot.py"
)
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


def test_original_packet_entry_must_match_pinned_inventory(tmp_path):
    path = tmp_path / "fold/model.json"
    path.parent.mkdir()
    path.write_bytes(b'{"one":1}')
    entries = {
        "fold/model.json": {
            "byte_length": 9,
            "sha256": pilot.hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    }
    assert (
        pilot._verified_packet_bytes(tmp_path, entries, "fold/model.json")
        == path.read_bytes()
    )
    path.write_bytes(b'{"one":2}')
    with pytest.raises(ValueError, match="differs from inventory"):
        pilot._verified_packet_bytes(tmp_path, entries, "fold/model.json")


def _make_fake_slot(root, plan, slot, case):
    folder = root / f"slot-{slot['slot_index']:04d}"
    folder.mkdir()
    benchmark = folder / "benchmark"
    benchmark.mkdir()
    request = case["request"]
    entries = [
        {
            "target_index": index,
            "target_m": target,
            "proposal_guard": {
                "status": "returned",
                "allow_proposal": 2 <= index <= 10,
            },
            "proposal_decision": (
                "proposed"
                if 2 <= index <= 10
                else "abstained_to_reference"
                if index == 0
                else "abstained_to_secant"
            ),
        }
        for index, target in enumerate(request["targets_m"])
    ]
    paths = {}
    for name in (*slot["arm_order"], "fresh-reference"):
        path = {
            "schema_version": "fixture.v1",
            "strategy": name,
            "entries": entries if name == "proposal" else [],
            "response_history": [],
            "terminal_checkpoint": {},
            "preload_response": {},
        }
        path["path_hash"] = pilot._sha(pilot._bytes(path))
        (benchmark / name).mkdir()
        pilot._save(benchmark / name, "path.json", pilot._bytes(path))
        paths[name] = {
            key: value
            for key, value in path.items()
            if key
            not in ("response_history", "terminal_checkpoint", "preload_response")
        }
    report = {
        "source_revision": plan["source_revision"],
        "proposal_identity": plan["policy_hash"],
        "proposal_guard": {"identity": plan["guard_hash"]},
        "arm_order": slot["arm_order"],
        "model_checksum": case["model_hash"],
        "request": request,
        "absolute_tolerance": plan["absolute_tolerance"],
        "relative_tolerance": plan["relative_tolerance"],
        "capture_material_state": True,
        "material_capture_scope": "proposal-only",
        "proposal_requested": True,
        "proposal_abstention_strategy": "secant",
        **pilot.learning._arithmetic_kwargs(pilot.ARITHMETIC),
        "arms": {name: paths[name] for name in slot["arm_order"]},
        "fresh_reference": paths["fresh-reference"],
    }
    report["report_hash"] = pilot._sha(pilot._bytes(report))
    pilot._save(benchmark, "comparison.json", pilot._bytes(report))
    score = {
        "full_comparison_pass": True,
        "execution_work": {"unknown_work": False},
        "proposal_over_secant_path_wall_ratio": 0.98,
        "actual_proposed_count": 9,
    }
    outcome = {
        "plan_hash": plan["plan_hash"],
        "slot": slot,
        "status": "completed",
        "report_hash": report["report_hash"],
        "score": score,
        "unknown_work_until_outcome": False,
    }
    pilot._save(folder, "outcome.json", pilot._bytes(outcome))
    pilot._save(folder, "inventory.json", pilot._bytes(pilot._inventory(folder)))


def test_audit_rejects_resealed_f_g_benchmark_tree_transplant(tmp_path, monkeypatch):
    cases = []
    schedule = []
    for index, case_id in enumerate(("development-pilot-f", "development-pilot-g")):
        request = {"targets_m": [float(target + index) for target in range(12)]}
        cases.append(
            {
                "case_id": case_id,
                "split": "validation",
                "static_model_gate": "not_rejected",
                "model_hash": f"sha256:fixture-model-{index}",
                "request_hash": pilot._sha(pilot._bytes(request)),
                "request": request,
            }
        )
        schedule.append(
            {
                "slot_index": index,
                "case_id": case_id,
                "arm_order": ["reference", "secant", "proposal"],
            }
        )
    plan = {
        "schema_version": pilot.SCHEMA,
        "source_revision": "fixture-head",
        "policy_hash": "fixture-policy",
        "guard": pilot.GATE,
        "guard_hash": pilot._sha(pilot._bytes(pilot.GATE)),
        "arithmetic_profile": pilot.ARITHMETIC,
        "cases": cases,
        "development_case_ids": [row["case_id"] for row in cases],
        "schedule": schedule,
        "failure_denominator": 2,
        "minimum_relative_improvement": 0.01,
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
    }
    plan["plan_hash"] = pilot._sha(pilot._bytes(plan))
    pilot._save(tmp_path, "plan.json", pilot._bytes(plan))
    for slot, case in zip(schedule, cases):
        _make_fake_slot(tmp_path, plan, slot, case)
    monkeypatch.setattr(pilot, "_audit_original_histories", lambda *_: None)
    monkeypatch.setattr(
        pilot,
        "_runtime_score",
        lambda *_: {
            "full_comparison_pass": True,
            "execution_work": {"unknown_work": False},
            "proposal_over_secant_path_wall_ratio": 0.98,
        },
    )
    monkeypatch.setattr(pilot, "_actual_proposal_count", lambda *_: 9)
    assert pilot.audit(tmp_path, write=False)["predeclared_path_screen_pass"] is True

    first = tmp_path / "slot-0000"
    second = tmp_path / "slot-0001"
    (first / "benchmark").rename(tmp_path / "transplant")
    (second / "benchmark").rename(first / "benchmark")
    (tmp_path / "transplant").rename(second / "benchmark")
    for folder in (first, second):
        outcome = pilot._json(folder / "outcome.json")
        outcome["report_hash"] = pilot._json(folder / "benchmark/comparison.json")[
            "report_hash"
        ]
        (folder / "outcome.json").write_bytes(pilot._bytes(outcome))
        (folder / "inventory.json").write_bytes(pilot._bytes(pilot._inventory(folder)))
    with pytest.raises(ValueError, match="model or request differs"):
        pilot.audit(tmp_path, write=False)


def test_audit_rejects_changed_tolerance_and_guard_bits():
    request = {"targets_m": [float(target) for target in range(12)]}
    case = {
        "case_id": "development-pilot-f",
        "split": "validation",
        "static_model_gate": "not_rejected",
        "model_hash": "model-f",
        "request_hash": pilot._sha(pilot._bytes(request)),
    }
    plan = {
        "guard": pilot.GATE,
        "guard_hash": pilot._sha(pilot._bytes(pilot.GATE)),
        "cases": [case],
        "development_case_ids": [case["case_id"]],
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "arithmetic_profile": pilot.ARITHMETIC,
    }
    slot = {"case_id": case["case_id"]}
    report = {
        "model_checksum": "model-f",
        "request": request,
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "capture_material_state": True,
        "material_capture_scope": "proposal-only",
        "proposal_requested": True,
        "proposal_abstention_strategy": "secant",
        **pilot.learning._arithmetic_kwargs(pilot.ARITHMETIC),
        "arms": {
            "proposal": {
                "entries": [
                    {
                        "target_index": index,
                        "target_m": target,
                        "proposal_guard": {
                            "status": "returned",
                            "allow_proposal": 2 <= index <= 10,
                        },
                        "proposal_decision": (
                            "proposed"
                            if 2 <= index <= 10
                            else "abstained_to_reference"
                            if index == 0
                            else "abstained_to_secant"
                        ),
                    }
                    for index, target in enumerate(request["targets_m"])
                ]
            }
        },
    }
    pilot._audit_slot_contract(plan, slot, report)
    report["relative_tolerance"] = 1e-3
    with pytest.raises(ValueError, match="comparison or execution config"):
        pilot._audit_slot_contract(plan, slot, report)
    report["relative_tolerance"] = 1e-8
    report["arms"]["proposal"]["entries"][11]["proposal_guard"]["allow_proposal"] = True
    with pytest.raises(ValueError, match="per-target guard"):
        pilot._audit_slot_contract(plan, slot, report)


def test_cli_returns_failure_for_raised_slot_and_failed_audit(monkeypatch, capsys):
    monkeypatch.setattr(pilot, "run_slot", lambda *_: {"status": "raised"})
    monkeypatch.setattr(
        sys, "argv", ["pilot", "slot", "--output", "/tmp/pilot", "--index", "0"]
    )
    assert pilot.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "raised"
    monkeypatch.setattr(
        pilot,
        "audit",
        lambda *_, **kwargs: {
            "predeclared_path_screen_pass": False,
            "slots": [{"status": "missing"}],
        },
    )
    monkeypatch.setattr(
        sys, "argv", ["pilot", "audit", "--output", "/tmp/pilot", "--verify-only"]
    )
    assert pilot.main() == 1
    assert json.loads(capsys.readouterr().out)["predeclared_path_screen_pass"] is False
