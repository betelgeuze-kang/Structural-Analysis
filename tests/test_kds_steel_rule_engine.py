from __future__ import annotations

from implementation.phase1.kds_steel_rule_engine import (
    SteelMemberCapacity,
    SteelMemberDemand,
    evaluate_steel_member,
    governing_result,
)


def test_kds_steel_rule_engine_returns_beam_checks() -> None:
    results = evaluate_steel_member(
        member_type="beam",
        demand=SteelMemberDemand(axial_kN=120.0, shear_kN=180.0, moment_kNm=1550.0, buckling_factor=2.4),
        capacity=SteelMemberCapacity(
            axial_kN=1800.0,
            shear_kN=320.0,
            moment_kNm=2000.0,
            buckling_factor_min=1.8,
            panel_zone_shear_kN=300.0,
            connection_shear_kN=280.0,
            connection_rotation_mrad=90.0,
        ),
    )

    assert [row.component for row in results] == [
        "flexure",
        "shear",
        "web_local_buckling",
    ]
    assert all(row.clause.startswith("KDS-STEEL-BEAM-") for row in results)
    assert governing_result(results).component == "flexure"


def test_kds_steel_rule_engine_returns_connection_and_panel_zone_checks() -> None:
    results = evaluate_steel_member(
        member_type="connection",
        topology_type="jointed-frame",
        demand=SteelMemberDemand(
            shear_kN=140.0,
            moment_kNm=720.0,
            buckling_factor=2.0,
            panel_zone_shear_kN=210.0,
            connection_shear_kN=140.0,
            connection_rotation_mrad=42.0,
        ),
        capacity=SteelMemberCapacity(
            axial_kN=1200.0,
            shear_kN=260.0,
            moment_kNm=1400.0,
            buckling_factor_min=1.6,
            panel_zone_shear_kN=240.0,
            connection_shear_kN=180.0,
            connection_rotation_mrad=50.0,
        ),
    )

    assert [row.component for row in results] == [
        "connection_shear",
        "connection_rotation",
        "panel_zone_shear",
    ]
    assert results[-1].clause == "KDS-STEEL-PZ-SHEAR-001"
    assert governing_result(results).component == "panel_zone_shear"
