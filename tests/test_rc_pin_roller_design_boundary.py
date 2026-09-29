"""Synthetic profile continuity from RC beam input to scoped design estimates."""

from dataclasses import replace
import json

import pytest

from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from tests.test_rc_fiber_pin_roller_beam_public import _model, _payload, _request


def test_pin_roller_quantities_require_opt_in_and_include_overhangs():
    model = _model()
    original = model.canonical_payload()
    with pytest.raises(design.FiberFrameDesignError, match="support_count_unsupported"):
        design.calculate_fiber_frame_member_quantities(model)
    quantities = design.calculate_fiber_frame_member_quantities(
        model, experimental_pin_roller_beam=True
    )
    assert model.canonical_payload() == original
    assert len(quantities["members"]) == 6
    assert sum(row["length_m"] for row in quantities["members"]) == pytest.approx(1.9)
    assert quantities["totals"]["gross_concrete_volume_m3"] == pytest.approx(
        0.4 * 0.6 * 1.9
    )
    assert quantities["totals"]["longitudinal_rebar_mass_kg"] == pytest.approx(
        8 * 0.000387 * 1.9 * 7850
    )
    assert quantities["detailed_takeoff"] is False
    assert "laps_anchorage_hooks" in quantities["excluded_items"]
    refined = _payload()
    for member in refined["elements"]:
        member["integration_order"] = 3
    refined["sections"][0]["concrete_layer_count"] = 8
    assert (
        design.calculate_fiber_frame_member_quantities(
            _model(refined), experimental_pin_roller_beam=True
        )["totals"]
        == quantities["totals"]
    )


@pytest.mark.parametrize("value", [1, "true", None])
def test_pin_roller_quantity_profile_requires_boolean(value):
    with pytest.raises(design.FiberFrameDesignError, match="explicit boolean"):
        design.calculate_fiber_frame_member_quantities(
            _model(), experimental_pin_roller_beam=value
        )


def test_quantity_profiles_cannot_be_combined():
    with pytest.raises(design.FiberFrameDesignError, match="mutually exclusive"):
        design.calculate_fiber_frame_member_quantities(
            _model(),
            experimental_pin_roller_beam=True,
            experimental_two_fixed_endpoints=True,
        )


@pytest.mark.parametrize("invalid", ["geometry", "supports"])
def test_pin_roller_quantity_preflight_keeps_the_solver_boundary(invalid):
    payload = _payload()
    if invalid == "geometry":
        payload["nodes"][3]["coordinates"][1] = 0.01
        reason = "pin_roller_beam_geometry_invalid"
    else:
        payload["supports"][1]["dofs"] = ["UX", "UY"]
        reason = "pin_roller_support_roles_invalid"
    with pytest.raises(design.FiberFrameDesignError, match=reason):
        design.calculate_fiber_frame_member_quantities(
            _model(payload), experimental_pin_roller_beam=True
        )


def test_pin_roller_design_preserves_profile_through_price_solve_and_replay(
    tmp_path,
):
    model = _model()
    original = model.canonical_payload()
    request = _request((-1e-6, -2e-6))
    report = study.compare_rc_control_designs(
        model,
        (
            design.FiberFrameDesignCandidate(
                "narrower", (design.FiberFrameSectionChange("RC1", width_m=0.36),)
            ),
        ),
        request,
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-29", "synthetic test prices; not a quote"
        ),
        source_revision="a" * 40,
        output_directory=tmp_path / "beam",
    )
    assert model.canonical_payload() == original
    assert report["status"] == "complete" and report["verified_count"] == 2
    assert report["selected_candidate_id"] == "narrower"
    assert report["control_request"] == request.to_dict()
    narrower = report["rows"][1]
    assert narrower["quantity_delta"]["gross_concrete_volume_m3"] == pytest.approx(
        -0.04 * 0.6 * 1.9
    )
    assert narrower["quantity_delta"]["longitudinal_rebar_mass_kg"] == 0
    assert narrower["scoped_estimate_reduction"] == pytest.approx(4.56)
    for row in report["rows"]:
        assert row["full_reference_verification_pass"] is True
        assert [item["phase"] for item in row["invocations"]] == [
            "analysis",
            "verification",
        ]
        assert all(not item["unknown_execution_work"] for item in row["invocations"])
        result = json.loads(
            (tmp_path / "beam" / row["artifacts"]["result"]["path"]).read_bytes()
        )
        assert result["request"]["experimental_pin_roller_beam"] is True
        assert result["model"]["compiler_profile"] == (
            "planar_serial_horizontal_pin_roller_beam_explicit_rectangular_rc_direct_control.v1"
        )
        assert result["path"]["accepted_target_prefix_m"] == list(request.targets_m)
        history = result["response_history"]
        assert row["performance"]["accepted_epoch_count"] == len(history)
        for response in history:
            assert {
                (r["node_id"], r["dof"]) for r in response["support_reactions"]
            } == {("N2", "UX"), ("N2", "UY"), ("N6", "UY")}
    for claim in (
        "independent_physical_validation",
        "design_authority",
        "confirmed_currency_savings",
        "release_approved",
    ):
        assert report["claims"][claim] is False


def test_pin_roller_preloaded_design_is_rejected_before_solver_or_output(
    tmp_path, monkeypatch
):
    model = _model()
    original = model.canonical_payload()
    request = replace(
        _request((-1e-6, -2e-6)),
        constant_nodal_loads=(("N4", 0.0, -0.01, 0.0),),
    )
    monkeypatch.setattr(
        study.api,
        "analyze_bounded_rc_fiber_direct_control",
        lambda *_a, **_kw: pytest.fail("unsupported pin-roller preload reached solver"),
    )
    output = tmp_path / "preloaded-beam"
    with pytest.raises(ValueError, match="pin-roller.*constant preloads"):
        study.compare_rc_control_designs(
            model,
            (
                design.FiberFrameDesignCandidate(
                    "narrower", (design.FiberFrameSectionChange("RC1", width_m=0.36),)
                ),
            ),
            request,
            history_limits=design.FiberFrameHistoryLimits(1, 1),
            material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
            prices=design.FiberFrameMaterialPrices(
                100, 1, "KRW", "2026-09-29", "synthetic test prices; not a quote"
            ),
            source_revision="a" * 40,
            output_directory=output,
        )
    assert model.canonical_payload() == original
    assert not output.exists()
