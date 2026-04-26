from __future__ import annotations

from implementation.phase1.bond_slip_interface import (
    BondSlipMaterial,
    bond_slip_interaction_response,
    bond_slip_response,
)


def test_bond_slip_response_tracks_elastic_softening_and_residual_branches() -> None:
    mat = BondSlipMaterial(k0_kn_per_mm=100.0, slip_y_mm=0.5, slip_u_mm=2.0, residual_ratio=0.25)

    elastic = bond_slip_response(0.25, mat)
    softening = bond_slip_response(1.0, mat)
    residual = bond_slip_response(2.5, mat)

    assert elastic.state_tag == "bond_elastic"
    assert elastic.stress_mpa == 25.0
    assert softening.state_tag == "bond_softening"
    assert softening.tangent_mpa < 0.0
    assert residual.state_tag == "bond_residual"
    assert residual.tangent_mpa == 0.0


def test_bond_slip_interaction_response_degrades_from_full_to_residual() -> None:
    mat = BondSlipMaterial(interaction_y=8.0e-4, interaction_u=4.0e-3, residual_ratio=0.25)

    full = bond_slip_interaction_response(1.0e-4, mat)
    partial = bond_slip_interaction_response(2.0e-3, mat)
    residual = bond_slip_interaction_response(6.0e-3, mat)

    assert full.state_tag == "full_interaction"
    assert full.interaction_ratio == 1.0
    assert partial.state_tag == "partial_interaction"
    assert mat.residual_ratio < partial.interaction_ratio < 1.0
    assert residual.state_tag == "residual_interaction"
    assert residual.interaction_ratio == mat.residual_ratio
