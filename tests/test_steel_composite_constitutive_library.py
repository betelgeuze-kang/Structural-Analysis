from __future__ import annotations

from implementation.phase1.rc_constitutive_library import (
    CompositeActionMaterial,
    SteelMaterial,
    composite_action_response,
    steel_response,
)


def test_steel_response_optionally_softens_in_compression_after_local_buckling() -> None:
    elastic_plastic = SteelMaterial(fy_mpa=355.0, hardening_ratio=0.02, fracture_strain=0.12)
    local_buckling = SteelMaterial(
        fy_mpa=355.0,
        hardening_ratio=0.02,
        fracture_strain=0.12,
        local_buckling_strain=0.025,
        post_buckling_residual_ratio=0.35,
    )

    unbuckled = steel_response(-0.05, elastic_plastic)
    buckled = steel_response(-0.05, local_buckling)

    assert unbuckled.state_tag == "plastic_hardening"
    assert buckled.state_tag == "compression_local_buckling"
    assert abs(buckled.stress_mpa) < abs(unbuckled.stress_mpa)
    assert buckled.tangent_mpa < 0.0


def test_composite_action_response_degrades_with_connector_slip() -> None:
    mat = CompositeActionMaterial(
        connector_slip_y_strain=8.0e-4,
        connector_slip_u_strain=4.0e-3,
        residual_action_ratio=0.25,
    )

    full = composite_action_response(
        steel_strain=-0.0025,
        concrete_strain=-0.0012,
        slip_strain=1.0e-4,
        mat=mat,
    )
    slipped = composite_action_response(
        steel_strain=-0.0025,
        concrete_strain=-0.0012,
        slip_strain=6.0e-3,
        mat=mat,
    )

    assert full.connector_state_tag == "full_interaction"
    assert slipped.connector_state_tag == "residual_interaction"
    assert full.action_ratio > slipped.action_ratio
    assert abs(full.stress_mpa) > abs(slipped.stress_mpa)
    assert abs(full.tangent_mpa) > abs(slipped.tangent_mpa)


def test_composite_action_response_limits_concrete_tension_participation() -> None:
    mat = CompositeActionMaterial(
        connector_slip_y_strain=8.0e-4,
        connector_slip_u_strain=4.0e-3,
        residual_action_ratio=0.25,
        concrete_tension_carry_ratio=0.10,
    )

    tension_limited = composite_action_response(
        steel_strain=0.0015,
        concrete_strain=0.0010,
        slip_strain=1.0e-4,
        mat=mat,
    )
    tension_carried = composite_action_response(
        steel_strain=0.0015,
        concrete_strain=0.0010,
        slip_strain=1.0e-4,
        mat=CompositeActionMaterial(
            connector_slip_y_strain=8.0e-4,
            connector_slip_u_strain=4.0e-3,
            residual_action_ratio=0.25,
            concrete_tension_carry_ratio=1.0,
        ),
    )

    assert tension_limited.concrete.state_tag == "tension_softening"
    assert tension_limited.action_ratio == 1.0
    assert tension_limited.stress_mpa < tension_carried.stress_mpa
