from __future__ import annotations

from implementation.phase1.steel_constitutive_library import SteelMaterial, steel_response


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


def test_steel_response_caps_strength_and_tangent_at_fracture_limit() -> None:
    mat = SteelMaterial(fy_mpa=355.0, hardening_ratio=0.02, fu_mpa=540.0, fracture_strain=0.12)

    fractured = steel_response(0.15, mat)

    assert fractured.state_tag == "fracture_limit"
    assert fractured.tangent_mpa == 0.0
    assert abs(fractured.stress_mpa) <= mat.fu_mpa
