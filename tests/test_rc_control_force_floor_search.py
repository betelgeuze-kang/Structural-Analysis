"""Prospectively frozen price search changes real eligible selections."""

import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_force_floor_search as search
from structural_analysis.benchmark.rc_control_force_floor_cli import (
    FLOOR_INPUT_SCHEMA,
    read_force_response_floor,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def inputs():
    root = Path("examples/research/rc_reuse_campaign")
    return {
        "baseline": load_neutral_json(root / "pin-roller-replication.model.json"),
        "candidates": tuple(
            design.FiberFrameDesignCandidate(
                candidate_id, (design.FiberFrameSectionChange("RC1", width_m=width),)
            )
            for candidate_id, width in (("w34", 0.34), ("w42", 0.42))
        ),
        "request": decode_bounded_rc_fiber_direct_control_request(
            (root / "pin-roller-replication.request.json").read_bytes()
        ),
        "force_response_floor": {
            "target_index": 2,
            "target_control_displacement_m": -0.00014,
            "minimum_load_factor": 180.0,
        },
        "history_limits": design.FiberFrameHistoryLimits(1.0, 1.0),
        "material_limits": design.FiberFrameMaterialHistoryLimits(1.0, 1.0, 1.0),
        "prices": design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-29", "invented regression arithmetic"
        ),
        "source_revision": "a" * 40,
        "full_analysis_budget": 3,
    }


def test_price_and_oracle_use_frozen_floor_before_first_solve(tmp_path, monkeypatch):
    args = inputs()
    output = tmp_path / "search"
    solver = study.api.analyze_bounded_rc_fiber_direct_control
    seen = []

    def checked_solver(*solver_args, **solver_kwargs):
        plan = json.loads((output / "plan.json").read_bytes())
        assert plan["force_response_floor"] == args["force_response_floor"]
        assert plan["plans"]["price_order"]["shortlist"] == ["w34", "w42"]
        seen.append(plan["plan_hash"])
        return solver(*solver_args, **solver_kwargs)

    monkeypatch.setattr(
        study.api, "analyze_bounded_rc_fiber_direct_control", checked_solver
    )
    report = search.compare_rc_control_force_floor_price_search(
        **args, output_directory=output
    )
    plan = json.loads((output / "plan.json").read_bytes())
    assert seen and set(seen) == {plan["plan_hash"]}
    assert report["plan_hash"] == plan["plan_hash"]
    assert plan["learned_policy_used"] is False
    assert report["schema_version"] == search.SEARCH_SCHEMA
    assert report["arms"]["price_order"]["selected_candidate_id"] == "w42"
    assert report["oracle"]["selected_candidate_id"] == "w42"
    assert report["candidate_cost_optimality_audit"]["status"] == "complete"
    assert report["candidate_cost_optimality_audit"][
        "pool_minimum_feasible_candidate_ids"
    ] == ["w42"]
    assert (
        report["candidate_cost_optimality_audit"]["arms"]["price_order"][
            "matches_pool_minimum"
        ]
        is True
    )
    assert report["claims"]["net_ai_savings_proved"] is False
    for name in ("price_order", "exhaustive_oracle"):
        comparison = json.loads((output / name / "comparison.json").read_bytes())
        assert comparison["force_response_floor"] == plan["force_response_floor"]
        assert comparison["selected_candidate_id"] == "w42"


def test_bad_floor_and_budget_reject_before_any_search_output(tmp_path):
    args = inputs()
    for change in (
        {
            "force_response_floor": args["force_response_floor"]
            | {"minimum_load_factor": 0}
        },
        {"full_analysis_budget": True},
        {"full_analysis_budget": 4},
        {"protocol_binding": {"protocol_commit": "a" * 40}},
    ):
        output = tmp_path / f"bad-{len(list(tmp_path.iterdir()))}"
        with pytest.raises(ValueError):
            search.compare_rc_control_force_floor_price_search(
                **(args | change), output_directory=output
            )
        assert not output.exists()


def test_floor_cli_rejects_ambiguous_json(tmp_path):
    input_path = tmp_path / "floor.json"
    input_path.write_text(
        '{"schema_version":"' + FLOOR_INPUT_SCHEMA + '",'
        '"target_index":2,"target_index":3,'
        '"target_control_displacement_m":-0.00014,"minimum_load_factor":180}'
    )
    with pytest.raises(ValueError, match="duplicate"):
        read_force_response_floor(input_path)
