from __future__ import annotations

import math

import pytest

from implementation.phase1.foundation_link_library import (
    PileHeadSpring,
    PySoilSpring,
    QzSoilSpring,
    TzSoilSpring,
    build_default_foundation_link_library,
    build_foundation_support_search_candidates,
    describe_foundation_link_library,
)


def test_foundation_link_library_exposes_expected_links() -> None:
    library = build_default_foundation_link_library()
    assert sorted(library) == ["p-y", "pile_head", "q-z", "t-z"]


def test_foundation_springs_switch_expected_branches() -> None:
    py_link = PySoilSpring(lateral_stiffness=1000.0, yield_force=10.0, post_yield_ratio=0.2)
    tz_link = TzSoilSpring(axial_stiffness=1200.0, shaft_capacity=12.0, residual_ratio=0.5)
    qz_link = QzSoilSpring(tip_stiffness=1500.0, tip_capacity=20.0)
    pile_head = PileHeadSpring(rotational_stiffness=2000.0, yield_moment=20.0, post_yield_ratio=0.1)

    assert py_link.evaluate(0.005).state_label == "elastic"
    assert py_link.evaluate(0.03).state_label == "plastic"
    assert tz_link.evaluate(0.005).state_label == "elastic"
    assert tz_link.evaluate(0.03).state_label == "residual"
    assert qz_link.evaluate(0.005).state_label == "mobilizing"
    assert qz_link.evaluate(0.03).state_label == "capped"
    assert pile_head.evaluate(0.005).state_label == "elastic"
    assert pile_head.evaluate(0.03).state_label == "post-yield"


def test_foundation_support_search_candidates_expose_patch_geometry() -> None:
    candidates = {
        str(row["link_name"]): row
        for row in build_foundation_support_search_candidates(
            pile_diameter_m=0.7,
            embedment_depth_m=8.0,
            support_spacing_m=3.6,
        )
    }

    assert sorted(candidates) == ["p-y", "pile_head", "q-z", "t-z"]
    assert candidates["p-y"]["contact_family"] == "soil_lateral_interface"
    assert candidates["p-y"]["node_to_surface_proxy"] is True
    assert candidates["p-y"]["search_patch_area_m2"] == pytest.approx(0.7 * 8.0)
    assert candidates["t-z"]["search_patch_area_m2"] == pytest.approx(math.pi * 0.7 * 8.0)
    assert candidates["q-z"]["search_patch_area_m2"] == pytest.approx(math.pi * (0.35**2))
    assert candidates["pile_head"]["node_to_surface_proxy"] is False
    assert candidates["pile_head"]["search_patch_area_m2"] == pytest.approx(3.6 * 3.6)
    assert candidates["q-z"]["support_candidate_ready"] is True


def test_describe_foundation_link_library_includes_search_ready_response_surface() -> None:
    description = describe_foundation_link_library()

    py_row = description["p-y"]
    pile_head_row = description["pile_head"]

    assert py_row["contact_family"] == "soil_lateral_interface"
    assert py_row["contact_search_axis"] == "local-x"
    assert py_row["support_candidate_ready"] is True
    assert py_row["search_patch_area_m2"] > 0.0
    assert py_row["search_radius_m"] > 0.0
    assert py_row["sample_probe_tangent"] > 0.0
    assert py_row["sample_response_ratio"] > 1.0

    assert pile_head_row["contact_family"] == "pile_head_fixity_interface"
    assert pile_head_row["contact_search_axis"] == "rotation-y"
    assert pile_head_row["node_to_surface_proxy"] is False
    assert pile_head_row["support_candidate_ready"] is True
