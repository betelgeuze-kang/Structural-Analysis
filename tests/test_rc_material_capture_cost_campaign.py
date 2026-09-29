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
    assert all(row["equal_case_mean_ratio"] is None for row in report["modes"])
    assert not report["all_pairs_exact"]
    assert not (tmp_path / "audit.json").exists()


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
            "proposal": {"entries": entries, "wall_ns": 1000},
            "secant": {"wall_ns": 900},
        }
    }
    cost = campaign._costs(report)
    assert cost["capture_wall_ns"] == 63
    assert cost["capture_cpu_ns"] == 54
    assert cost["proposal_callback_wall_ns"] == 60
    assert cost["guard_callback_wall_ns"] == 24
    assert cost["solver_attempt_wall_ns"] == 132
    assert cost["recovery_wall_ns"] == 36
    assert cost["proposal_path_wall_ns"] == 1000
    del entries[2]["committed_material_capture"]
    with pytest.raises(ValueError, match="capture roster"):
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
