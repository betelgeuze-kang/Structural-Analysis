from __future__ import annotations

from implementation.phase1.special_link_library import (
    BearingLink,
    CompressionOnlyLink,
    FrictionLink,
    GapLink,
    PoundingLink,
    UpliftLink,
    SUPPORTED_LINKS,
    build_default_special_link_library,
)


def test_special_link_library_exposes_all_contact_categories() -> None:
    library = build_default_special_link_library()
    assert sorted(library) == sorted(SUPPORTED_LINKS)


def test_gap_uplift_and_compression_only_links_are_unilateral() -> None:
    gap = GapLink(stiffness=1000.0, gap_opening=0.01)
    uplift = UpliftLink(stiffness=1000.0)
    compression = CompressionOnlyLink(stiffness=1000.0)

    assert gap.evaluate(0.005).force == 0.0
    assert gap.evaluate(0.02).force > 0.0
    assert uplift.evaluate(0.005).force == 0.0
    assert uplift.evaluate(-0.005).force > 0.0
    assert compression.evaluate(-0.005).force == 0.0
    assert compression.evaluate(0.005).force > 0.0


def test_bearing_friction_and_pounding_links_switch_branches() -> None:
    bearing = BearingLink(elastic_stiffness=1000.0, yield_force=10.0, post_yield_ratio=0.2)
    friction = FrictionLink(tangential_stiffness=1000.0, friction_coefficient=0.3, normal_force=100.0)
    pounding = PoundingLink(contact_stiffness=1000.0, damping=10.0, impact_gap=0.01)

    assert bearing.evaluate(0.005).state_label == 'elastic'
    assert bearing.evaluate(0.02).state_label == 'post-yield'
    assert friction.evaluate(0.005).state_label == 'stick'
    assert friction.evaluate(0.05).state_label == 'slip'
    assert pounding.evaluate(0.005, velocity=0.2).state_label == 'separated'
    assert pounding.evaluate(0.02, velocity=0.2).state_label == 'impact'
