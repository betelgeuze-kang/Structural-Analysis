"""Development capture experiment must retain every slot and original bytes."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def campaign(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("run_rc_material_capture_cost_campaign")


def fixture_plan(campaign):
    pilot = campaign.pilot
    case_ids = [spec[0] for spec in pilot.CASE_SPECS]
    plan = {
        "schema_version": campaign.SCHEMA,
        "source_revision": "a" * 40,
        "source_packet": "/unused/frozen-training-packet",
        "source_packet_inventory_sha256": pilot.ORIGINAL_INVENTORY,
        "source_selection_result_hash": pilot.ORIGINAL_RESULT,
        "source_policy_file_sha256": "0" * 64,
        "policy_hash": pilot.ORIGINAL_POLICY,
        "arithmetic_profile": pilot.ARITHMETIC,
        "cases": [],
        "development_case_ids": case_ids,
        "independent_source_lineage": False,
        "training_or_reserved_case_execution": False,
        "guard": pilot.GATE,
        "guard_hash": campaign._sha(campaign._bytes(pilot.GATE)),
        "schedule": campaign._schedule(case_ids),
        "failure_denominator": 12,
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "minimum_relative_improvement": 0.01,
    }
    plan["plan_hash"] = campaign._sha(campaign._bytes(plan))
    return plan


def test_fixed_f_g_schedule_balances_mode_and_path_order(campaign):
    schedule = campaign._schedule([spec[0] for spec in campaign.pilot.CASE_SPECS])
    assert len(schedule) == 12
    assert [row["slot_index"] for row in schedule] == list(range(12))
    for case_id in [spec[0] for spec in campaign.pilot.CASE_SPECS]:
        for repetition in range(3):
            paired = [
                row
                for row in schedule
                if row["case_id"] == case_id and row["repetition_index"] == repetition
            ]
            assert {row["mode"] for row in paired} == {"cached", "uncached"}
            assert paired[0]["arm_order"] == paired[1]["arm_order"]
    assert [row["mode"] for row in schedule[:4]] == [
        "uncached",
        "cached",
        "cached",
        "uncached",
    ]


def test_resealed_wrong_mode_schedule_is_rejected(tmp_path, campaign):
    plan = fixture_plan(campaign)
    plan["schedule"][1]["mode"] = "uncached"
    plan["plan_hash"] = campaign._sha(
        campaign._bytes(
            {key: value for key, value in plan.items() if key != "plan_hash"}
        )
    )
    campaign._save(tmp_path, "plan.json", campaign._bytes(plan))
    with pytest.raises(ValueError, match="frozen material-capture plan"):
        campaign._read_plan(tmp_path)


def test_missing_slots_remain_unknown_in_twelve_slot_denominator(
    tmp_path, campaign, monkeypatch
):
    plan = fixture_plan(campaign)
    campaign._save(tmp_path, "plan.json", campaign._bytes(plan))
    monkeypatch.setattr(campaign.pilot, "_clean_head", lambda: plan["source_revision"])
    monkeypatch.setattr(campaign, "_inputs", lambda _: None)
    report = campaign.audit(tmp_path, write=False)
    assert report["failure_denominator"] == 12
    assert len(report["slots"]) == 12
    assert all(
        row["status"] == "missing" and row["unknown_work"] for row in report["slots"]
    )
    assert all(row["actual_proposals"] is None for row in report["slots"])
    assert all(
        case["actual_proposals"] is None
        for mode in report["modes"]
        for case in mode["cases"]
    )
    assert all(row["equal_case_mean_ratio"] is None for row in report["modes"])
    assert not report["all_pairs_exact"]
    assert not (tmp_path / "audit.json").exists()


def test_out_of_order_slot_cannot_start(tmp_path, campaign, monkeypatch):
    plan = fixture_plan(campaign)
    campaign._save(tmp_path, "plan.json", campaign._bytes(plan))
    monkeypatch.setattr(campaign.pilot, "_clean_head", lambda: plan["source_revision"])
    with pytest.raises(ValueError, match="previous slot must have"):
        campaign.run_slot(tmp_path, 1)
    assert not (tmp_path / "slot-0001").exists()


def test_audit_rejects_wrong_slot_chain(tmp_path, campaign, monkeypatch):
    plan = fixture_plan(campaign)
    campaign._save(tmp_path, "plan.json", campaign._bytes(plan))
    monkeypatch.setattr(campaign.pilot, "_clean_head", lambda: plan["source_revision"])
    monkeypatch.setattr(campaign, "_inputs", lambda _: None)
    folder = tmp_path / "slot-0000"
    folder.mkdir()
    receipt = {"plan_hash": plan["plan_hash"], "slot": plan["schedule"][0], "pid": 10}
    campaign._save(
        folder,
        "started.json",
        campaign._bytes(
            {
                **receipt,
                "previous_outcome_sha256": "sha256:" + "0" * 64,
                "previous_inventory_sha256": None,
            }
        ),
    )
    campaign._save(folder, "outcome.json", campaign._bytes({**receipt, "status": "raised"}))
    campaign._save(folder, "inventory.json", campaign._bytes(campaign.pilot._inventory(folder)))
    with pytest.raises(ValueError, match="receipt changed"):
        campaign.audit(tmp_path, write=False)


def test_raised_slot_keeps_unknown_proposal_count(tmp_path, campaign, monkeypatch):
    plan = fixture_plan(campaign)
    campaign._save(tmp_path, "plan.json", campaign._bytes(plan))
    monkeypatch.setattr(campaign.pilot, "_clean_head", lambda: plan["source_revision"])
    monkeypatch.setattr(campaign, "_inputs", lambda _: None)
    folder = tmp_path / "slot-0000"
    folder.mkdir()
    receipt = {"plan_hash": plan["plan_hash"], "slot": plan["schedule"][0], "pid": 10}
    campaign._save(
        folder,
        "started.json",
        campaign._bytes(
            {
                **receipt,
                "previous_outcome_sha256": None,
                "previous_inventory_sha256": None,
            }
        ),
    )
    campaign._save(
        folder,
        "outcome.json",
        campaign._bytes(
            {
                **receipt,
                "status": "raised",
                "unknown_work_until_outcome": True,
                "wall_ns": 100,
                "cpu_ns": 100,
                "cost_ledger": {
                    "input_loading_and_preflight": {"wall_ns": 50, "cpu_ns": 50}
                },
            }
        ),
    )
    campaign._save(folder, "inventory.json", campaign._bytes(campaign.pilot._inventory(folder)))
    result = campaign.audit(tmp_path, write=False)
    assert result["slots"][0]["status"] == "raised"
    assert result["slots"][0]["actual_proposals"] is None
    assert result["modes"][0]["cases"][0]["actual_proposals"] is None
    assert result["modes"][0]["equal_case_mean_ratio"] is None


def test_audit_rejects_loading_larger_than_slot(tmp_path, campaign, monkeypatch):
    plan = fixture_plan(campaign)
    campaign._save(tmp_path, "plan.json", campaign._bytes(plan))
    monkeypatch.setattr(campaign.pilot, "_clean_head", lambda: plan["source_revision"])
    monkeypatch.setattr(campaign, "_inputs", lambda _: None)
    folder = tmp_path / "slot-0000"
    folder.mkdir()
    receipt = {"plan_hash": plan["plan_hash"], "slot": plan["schedule"][0], "pid": 10}
    campaign._save(
        folder,
        "started.json",
        campaign._bytes(
            {**receipt, "previous_outcome_sha256": None, "previous_inventory_sha256": None}
        ),
    )
    campaign._save(
        folder,
        "outcome.json",
        campaign._bytes(
            {
                **receipt,
                "status": "raised",
                "unknown_work_until_outcome": True,
                "wall_ns": 100,
                "cpu_ns": 100,
                "cost_ledger": {
                    "input_loading_and_preflight": {"wall_ns": 101, "cpu_ns": 50}
                },
            }
        ),
    )
    campaign._save(folder, "inventory.json", campaign._bytes(campaign.pilot._inventory(folder)))
    with pytest.raises(ValueError, match="input loading timing"):
        campaign.audit(tmp_path, write=False)


def test_capture_cost_scopes_are_kept_separate(campaign):
    entries = []
    for index in range(12):
        entry = {
            "proposal_wall_ns": 5,
            "proposal_guard": {"wall_ns": 2},
            "invocations": [{"wall_ns": 11}],
            "recovery_wall_ns": 3,
        }
        if 2 <= index <= 10:
            entry["committed_material_capture"] = {"wall_ns": 7, "cpu_ns": 6}
        entries.append(entry)
    report = {
        "arms": {
            "proposal": {
                "entries": entries,
                "wall_ns": 1000,
                "cpu_ns": 1000,
                "preload_invocations": [{"wall_ns": 23, "cpu_ns": 22}],
            },
            "secant": {"wall_ns": 900, "cpu_ns": 900},
            "reference": {"wall_ns": 850, "cpu_ns": 850},
        },
        "fresh_reference": {"wall_ns": 950, "cpu_ns": 950},
        "whole_study_wall_ns": 2000,
        "whole_study_cpu_ns": 2000,
    }
    for entry in entries:
        entry["proposal_cpu_ns"] = 5
        entry["proposal_guard"]["cpu_ns"] = 2
        entry["invocations"][0]["cpu_ns"] = 11
        entry["recovery_cpu_ns"] = 3
    cost = campaign._costs(report)
    assert cost["capture_wall_ns"] == 63
    assert cost["capture_cpu_ns"] == 54
    assert cost["proposal_callback_wall_ns"] == 60
    assert cost["guard_callback_wall_ns"] == 24
    assert cost["solver_attempt_wall_ns"] == 132
    assert cost["preload_solver_attempt_wall_ns"] == 23
    assert cost["recovery_wall_ns"] == 36
    assert cost["proposal_path_wall_ns"] == 1000
    del entries[2]["committed_material_capture"]
    with pytest.raises(ValueError, match="capture roster"):
        campaign._costs(report)


def test_capture_cost_rejects_shifted_roster_and_nested_scope(campaign):
    entries = []
    for index in range(12):
        row = {
            "proposal_wall_ns": 5,
            "proposal_cpu_ns": 5,
            "proposal_guard": {"wall_ns": 2, "cpu_ns": 2},
            "invocations": [{"wall_ns": 11, "cpu_ns": 11}],
        }
        if 2 <= index <= 10:
            row["committed_material_capture"] = {"wall_ns": 7, "cpu_ns": 7}
        entries.append(row)
    report = {
        "arms": {
            "proposal": {
                "entries": entries,
                "wall_ns": 1000,
                "cpu_ns": 1000,
                "preload_invocations": [],
            },
            "secant": {"wall_ns": 900, "cpu_ns": 900},
            "reference": {"wall_ns": 850, "cpu_ns": 850},
        },
        "fresh_reference": {"wall_ns": 950, "cpu_ns": 950},
        "whole_study_wall_ns": 2000,
        "whole_study_cpu_ns": 2000,
    }
    assert campaign._costs(report)["capture_wall_ns"] == 63
    entries[2].pop("committed_material_capture")
    entries[1]["committed_material_capture"] = {"wall_ns": 7, "cpu_ns": 7}
    with pytest.raises(ValueError, match="capture roster"):
        campaign._costs(report)
    entries[2]["committed_material_capture"] = entries[1].pop(
        "committed_material_capture"
    )
    entries[2]["committed_material_capture"]["wall_ns"] = 1001
    with pytest.raises(ValueError, match="nested proposal timing"):
        campaign._costs(report)
    for index in range(2, 11):
        entries[index]["committed_material_capture"]["wall_ns"] = 200
    with pytest.raises(ValueError, match="aggregate capture timing"):
        campaign._costs(report)


def test_pair_check_detects_changed_context_or_retry_step(tmp_path, campaign):
    left, right = (tmp_path / name for name in ("left", "right"))
    for folder in (left, right):
        proposal = folder / "benchmark/proposal"
        proposal.mkdir(parents=True)
        for index in range(12):
            (proposal / f"{index:03d}-context.json").write_bytes(b"context")
            (proposal / f"{index:03d}-1-step.json").write_bytes(b"step")
        (proposal / "006-2-step.json").write_bytes(b"retry")
    assert campaign._proposal_bytes_match(left, right)
    (right / "benchmark/proposal/006-2-step.json").write_bytes(b"changed")
    assert not campaign._proposal_bytes_match(left, right)
