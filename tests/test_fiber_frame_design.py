from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import (
    load_neutral_json,
    load_neutral_json_bytes,
)


MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_cantilever.json"
)
REVISION = "a" * 40
CONFIG = PublicRCFiberFrameConfig(load_steps=2)


@pytest.fixture
def model():
    return load_neutral_json(MODEL_PATH)


@pytest.fixture
def prices():
    return design.FiberFrameMaterialPrices(
        100.0, 2.0, "USD", "2026-09-08", "synthetic test prices; not a quote"
    )


@pytest.fixture(scope="module")
def comparison():
    return design.compare_public_rc_fiber_frame_designs(
        load_neutral_json(MODEL_PATH),
        (
            design.FiberFrameDesignCandidate(
                "narrow", (design.FiberFrameSectionChange("RC1", width_m=0.35),)
            ),
            design.FiberFrameDesignCandidate(
                "invalid-cover", (design.FiberFrameSectionChange("RC1", cover_m=2.0),)
            ),
        ),
        CONFIG,
        prices=design.FiberFrameMaterialPrices(
            100.0, 2.0, "USD", "2026-09-08", "synthetic test prices; not a quote"
        ),
        terminal_limits=design.FiberFrameTerminalLimits(0.1, 0.1),
        source_revision=REVISION,
    )


def test_section_change_detaches_source_and_changes_only_authored_section(model):
    before = model.canonical_payload()
    candidate = design.FiberFrameDesignCandidate(
        "bars", (design.FiberFrameSectionChange("RC1", top_bar_count=3),)
    )
    changed = design.apply_fiber_frame_section_changes(model, candidate)
    assert model.canonical_payload() == before
    assert changed.canonical_model_checksum != model.canonical_model_checksum
    assert changed.input_checksum != model.input_checksum
    for name in ("nodes", "elements", "materials", "loads", "supports"):
        assert getattr(changed, name) == getattr(model, name)
    changed.sections[0]["width_m"] = 3
    assert model.canonical_payload() == before


def test_quantities_are_member_geometry_not_integration_fiber_sums(model):
    quantities = design.calculate_fiber_frame_member_quantities(model)
    assert quantities["totals"]["gross_concrete_volume_m3"] == pytest.approx(
        0.4 * 0.6 * 3
    )
    assert quantities["totals"]["longitudinal_rebar_mass_kg"] == pytest.approx(
        8 * 0.000387 * 3 * 7850
    )
    assert quantities["detailed_takeoff"] is False
    assert "laps_anchorage_hooks" in quantities["excluded_items"]
    model.elements[0]["integration_order"] = 3
    model.sections[0]["concrete_layer_count"] = 8
    refined = design.calculate_fiber_frame_member_quantities(model)
    assert refined["totals"] == quantities["totals"]


def test_member_quantities_sum_shared_section_once_per_physical_member(model):
    payload = model.canonical_payload()
    payload["nodes"].append({"id": "N3", "coordinates": [5.0, 0.0, 0.0]})
    payload["elements"].append(
        {**payload["elements"][0], "id": "M2", "nodes": ["N2", "N3"]}
    )
    payload["loads"][0]["node"] = "N3"
    chain = load_neutral_json_bytes(json.dumps(payload).encode())
    quantities = design.calculate_fiber_frame_member_quantities(chain)
    assert len(quantities["members"]) == 2
    assert quantities["totals"]["gross_concrete_volume_m3"] == pytest.approx(
        0.4 * 0.6 * 5
    )


def test_real_candidate_reanalysis_and_invalid_case_remain_in_denominator(comparison):
    report = comparison.to_dict()
    assert report["status"] == "partial"
    baseline, narrow, invalid = report["rows"]
    assert baseline["full_reference_verification_pass"] is True
    assert narrow["full_reference_verification_pass"] is True
    assert baseline["result"]["result_hash"] != narrow["result"]["result_hash"]
    assert baseline["result"]["checkpoint"]["terminal_epoch"] == 2
    assert narrow["result"]["checkpoint"]["terminal_epoch"] == 2
    assert (
        narrow["performance"]["terminal_maximum_translation_m"]
        > baseline["performance"]["terminal_maximum_translation_m"]
    )
    assert narrow["difference_from_baseline"]["quantity_delta"][
        "gross_concrete_volume_m3"
    ] == pytest.approx(-0.05 * 0.6 * 3)
    assert narrow["difference_from_baseline"][
        "scoped_material_estimate_reduction"
    ] == pytest.approx(9)
    assert (
        narrow["material_estimate"]["price_table_hash"]
        == baseline["material_estimate"]["price_table_hash"]
    )
    assert invalid["status"] == "invalid_or_unsupported"
    assert invalid["full_reference_verification_pass"] is False
    assert invalid["quantities"] is None
    assert invalid["difference_from_baseline"] is None
    assert report["runtime"]["reference_analysis_request_count"] == 3
    assert report["runtime"]["known_solver_execution_count"] == 2
    assert report["selection"]["candidate_id"] == "narrow"
    assert report["claims"]["all_requested_models_verified"] is False
    assert report["claims"]["confirmed_currency_savings"] is False
    assert (
        canonical_hash({k: v for k, v in report.items() if k != "report_hash"})
        == report["report_hash"]
    )
    report["rows"][0]["candidate_id"] = "tampered"
    assert comparison.to_dict()["rows"][0]["candidate_id"] == "baseline"


def test_absent_prices_and_explicit_limit_failure_cannot_select(
    model, monkeypatch, comparison
):
    # Reuse already solver-verified immutable results to test the decision boundary.
    cached = [deepcopy(row) for row in comparison.to_dict()["rows"][:2]]
    original_evaluate = design._evaluate_design
    results = {}
    actual = design.public_api.analyze_public_rc_fiber_frame

    def read_once(m, cfg):
        checksum = m.canonical_model_checksum
        if checksum not in results:
            results[checksum] = actual(m, cfg)
        return results[checksum]

    monkeypatch.setattr(design.public_api, "analyze_public_rc_fiber_frame", read_once)
    row = original_evaluate(
        "baseline",
        model,
        CONFIG,
        None,
        design.FiberFrameTerminalLimits(1e-15, 1e-15),
        7850,
    )
    assert row["full_reference_verification_pass"] is True
    assert row["terminal_limit_status"] == "fail"
    assert row["material_estimate"] is None
    assert len(row["violated_terminal_limits"]) == 2
    assert cached[0]["terminal_limit_status"] == "pass"


def test_exception_is_retained_without_false_solver_or_cost_claim(
    model, prices, monkeypatch
):
    def failed(*args, **kwargs):
        raise RuntimeError("test injected failure")

    monkeypatch.setattr(design.public_api, "analyze_public_rc_fiber_frame", failed)
    result = design.compare_public_rc_fiber_frame_designs(
        model,
        (
            design.FiberFrameDesignCandidate(
                "narrow", (design.FiberFrameSectionChange("RC1", width_m=0.35),)
            ),
        ),
        CONFIG,
        prices=prices,
        source_revision=REVISION,
    ).to_dict()
    assert result["status"] == "partial"
    assert result["selection"]["candidate_id"] is None
    assert result["runtime"]["known_solver_execution_count"] == 0
    assert result["runtime"]["unknown_solver_execution_count"] == 2
    assert all(
        row["failure"]["exception_type"] == "RuntimeError" and row["result"] is None
        for row in result["rows"]
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_m": True},
        {"depth_m": float("inf")},
        {"bar_area_m2": 0},
        {"top_bar_count": 2.5},
        {"bottom_bar_count": 0},
    ],
)
def test_invalid_section_values_rejected(kwargs):
    with pytest.raises(design.FiberFrameDesignError):
        design.FiberFrameSectionChange("RC1", **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"concrete_per_m3": -1},
        {"rebar_per_kg": float("nan")},
        {"currency": "usd"},
        {"as_of": "2026-02-30"},
        {"source": ""},
    ],
)
def test_invalid_price_basis_rejected(kwargs):
    values = dict(
        concrete_per_m3=100,
        rebar_per_kg=2,
        currency="USD",
        as_of="2026-09-08",
        source="test",
    )
    with pytest.raises(design.FiberFrameDesignError):
        design.FiberFrameMaterialPrices(**{**values, **kwargs})


def test_noop_and_duplicate_physical_candidates_rejected_before_solve(
    model, monkeypatch
):
    def should_not_run(*args, **kwargs):
        pytest.fail("invalid experiment must be rejected before solving")

    monkeypatch.setattr(
        design.public_api, "analyze_public_rc_fiber_frame", should_not_run
    )
    unchanged = design.FiberFrameDesignCandidate(
        "same", (design.FiberFrameSectionChange("RC1", width_m=0.4),)
    )
    with pytest.raises(design.FiberFrameDesignError, match="must change"):
        design.compare_public_rc_fiber_frame_designs(
            model, (unchanged,), source_revision=REVISION
        )
    changes = (design.FiberFrameSectionChange("RC1", width_m=0.35),)
    with pytest.raises(design.FiberFrameDesignError, match="same physical model"):
        design.compare_public_rc_fiber_frame_designs(
            model,
            (
                design.FiberFrameDesignCandidate("one", changes),
                design.FiberFrameDesignCandidate("two", changes),
            ),
            source_revision=REVISION,
        )


def test_derived_quantity_overflow_and_unsupported_profile_rejected(model):
    with pytest.raises(design.FiberFrameDesignError):
        design.calculate_fiber_frame_member_quantities(
            model, rebar_density_kg_per_m3=10**400
        )
    model.elements[0]["type"] = "unimplemented"
    with pytest.raises(design.FiberFrameDesignError, match="unsupported quantity"):
        design.calculate_fiber_frame_member_quantities(model)
