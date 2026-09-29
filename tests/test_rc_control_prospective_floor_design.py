"""Opt-in force-response eligibility uses an accepted, freshly replayed target."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.units.schema import UnitSystem


MODEL = Path("examples/research/rc_reuse_campaign/pin-roller-replication.model.json")
REQUEST = Path("examples/research/rc_reuse_campaign/pin-roller-replication.request.json")


def _inputs():
    request = decode_bounded_rc_fiber_direct_control_request(REQUEST.read_bytes())
    return {
        "baseline": load_neutral_json(MODEL),
        "candidates": tuple(
            design.FiberFrameDesignCandidate(
                candidate_id, (design.FiberFrameSectionChange("RC1", width_m=width),)
            )
            for candidate_id, width in (("w34", 0.34), ("w42", 0.42))
        ),
        "request": request,
        "history_limits": design.FiberFrameHistoryLimits(1.0, 1.0),
        "material_limits": design.FiberFrameMaterialHistoryLimits(1.0, 1.0, 1.0),
        "prices": design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-29", "invented regression arithmetic"
        ),
        "source_revision": "a" * 40,
    }


def _floor():
    return {
        "target_index": 2,
        "target_control_displacement_m": -0.00014,
        "minimum_load_factor": 180.0,
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"target_index": True}, "authored target index"),
        ({"target_index": 4}, "authored target index"),
        ({"target_control_displacement_m": -0.00013}, "authored displacement"),
        ({"minimum_load_factor": 0}, "positive finite"),
        ({"minimum_load_factor": -1}, "positive finite"),
        ({"minimum_load_factor": float("inf")}, "positive finite"),
        ({"minimum_load_factor": True}, "positive finite"),
        ({"unknown": 1}, "exact force-response floor fields"),
    ],
)
def test_invalid_floor_rejects_before_output_or_solver(tmp_path, monkeypatch, change, message):
    arguments = _inputs()
    floor = _floor() | change

    def forbidden(*args, **kwargs):
        pytest.fail("invalid floor reached the numerical solver")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    output = tmp_path / "comparison"
    with pytest.raises(ValueError, match=message):
        study.compare_rc_control_designs(
            **arguments, force_response_floor=floor, output_directory=output
        )
    assert not output.exists()


@pytest.mark.parametrize("change", ["no_loads", "wrong_unit", "not_pin_roller", "preload"])
def test_floor_requires_fixed_pin_roller_reference_loads(tmp_path, change):
    arguments = _inputs()
    if change == "no_loads":
        arguments["baseline"] = replace(arguments["baseline"], loads=[])
    elif change == "wrong_unit":
        arguments["baseline"] = replace(
            arguments["baseline"], units=UnitSystem("m", "N")
        )
    elif change == "not_pin_roller":
        arguments["request"] = replace(
            arguments["request"], experimental_pin_roller_beam=False
        )
    else:
        arguments["request"] = replace(
            arguments["request"], constant_nodal_loads=(("N4", 0.0, -1.0, 0.0),)
        )
    output = tmp_path / "comparison"
    with pytest.raises(ValueError):
        study.compare_rc_control_designs(
            **arguments, force_response_floor=_floor(), output_directory=output
        )
    assert not output.exists()


def test_verified_indexed_floor_changes_actual_eligible_selection(tmp_path):
    arguments = _inputs()
    floor = _floor()
    output = tmp_path / "comparison"
    report = study.compare_rc_control_designs(
        **arguments, force_response_floor=floor, output_directory=output
    )
    assert report["schema_version"] == study.FORCE_RESPONSE_FLOOR_SCHEMA
    assert report["force_response_floor"] == floor
    assert report["status"] == "complete"
    assert report["selected_candidate_id"] == "w42"
    rows = {row["candidate_id"]: row for row in report["rows"]}
    assert set(rows) == {"baseline", "w34", "w42"}
    assert rows["w34"]["material_estimate"]["total"] < rows["w42"]["material_estimate"]["total"]
    for candidate_id in ("baseline", "w34", "w42"):
        row = rows[candidate_id]
        assert row["full_reference_verification_pass"] is True
        original = json.loads((output / row["artifacts"]["result"]["path"]).read_bytes())
        factor = original["response_history"][2]["load_factor"]
        assert row["performance"]["load_factor_at_target"] == factor
        assert row["screens"]["load_factor_at_target"] == {
            "value": factor,
            "limit": 180.0,
            "status": "pass" if factor >= 180.0 else "fail",
            "comparison": "at_least",
        }
        assert row["selection_eligible"] is (factor >= 180.0)
    assert rows["w34"]["selection_eligible"] is False
    assert rows["w42"]["selection_eligible"] is True

    original = json.loads(
        (output / rows["w42"]["artifacts"]["result"]["path"]).read_bytes()
    )
    original["path"]["attempts"][2]["target_control_displacement_m"] = -0.00013
    with pytest.raises(ValueError, match="accepted target checkpoint"):
        study._verified_indexed_load_factor(original, arguments["request"], floor)
    original["path"]["attempts"][2]["target_control_displacement_m"] = -0.00014
    original["response_history"][2]["load_factor"] = float("nan")
    with pytest.raises(ValueError, match="accepted target checkpoint"):
        study._verified_indexed_load_factor(original, arguments["request"], floor)
