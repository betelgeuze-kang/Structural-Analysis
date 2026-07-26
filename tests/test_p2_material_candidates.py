from __future__ import annotations

import json

import pytest

import structural_analysis.materials as materials
from structural_analysis.materials.bond_slip import (
    BondSlipMaterial,
    BondSlipState,
    bond_slip_envelope,
    integrate_bond_slip,
    integrate_bond_slip_history,
)
from structural_analysis.materials.confined_concrete import (
    ConfinedConcreteMaterial,
    ConfinedConcreteState,
    StatefulConfinedConcreteResponse,
    confined_concrete_response,
    finite_difference_confined_concrete_tangent,
)
from structural_analysis.materials.partial_composite import (
    CondensedPartialCompositeAxialMaterial,
    CondensedPartialCompositeAxialState,
    PartialCompositeMaterial,
    PartialCompositeState,
    integrate_partial_composite,
)


def test_mander_envelope_strength_peak_and_tangent_contract() -> None:
    unconfined = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=0.0)
    confined = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)

    assert unconfined.confinement_strength_gain == pytest.approx(1.0)
    assert confined.confinement_strength_gain > 1.0
    assert confined.confined_peak_strain > unconfined.confined_peak_strain
    peak = confined_concrete_response(-confined.confined_peak_strain, confined)
    assert peak.branch == "peak"
    assert peak.stress_mpa == pytest.approx(-confined.confined_compressive_strength_mpa)
    assert peak.consistent_tangent_mpa == pytest.approx(0.0, abs=1.0e-10)
    assert confined_concrete_response(1.0e-4, confined).stress_mpa == 0.0

    for strain in (-0.001, -0.008):
        check = finite_difference_confined_concrete_tangent(
            confined,
            strain=strain,
            epsilon=1.0e-9,
        )
        assert check["relative_error"] <= 2.0e-8


def test_confined_concrete_is_explicitly_bounded_and_validated() -> None:
    material = ConfinedConcreteMaterial(
        effective_lateral_pressure_mpa=1.5,
        ultimate_compressive_strain=0.03,
    )
    residual = confined_concrete_response(-0.04, material)
    assert residual.branch == "residual_cutoff"
    assert residual.consistent_tangent_mpa == 0.0
    assert residual.stress_mpa < 0.0
    assert "multiaxial" in residual.claim_boundary
    with pytest.raises(ValueError, match="ultimate_compressive_strain"):
        ConfinedConcreteMaterial(
            effective_lateral_pressure_mpa=8.0,
            ultimate_compressive_strain=0.002,
        )


def test_bond_slip_envelope_and_same_parent_tangent() -> None:
    material = BondSlipMaterial()
    elastic = bond_slip_envelope(0.2e-3, material)
    softening = bond_slip_envelope(1.5e-3, material)
    residual = bond_slip_envelope(5.0e-3, material)

    assert elastic[2] == "elastic"
    assert elastic[1] > 0.0
    assert softening[2] == "softening"
    assert softening[1] < 0.0
    assert residual[2] == "residual"
    assert residual[1] == 0.0

    parent = BondSlipState()
    slip = 1.5e-3
    epsilon = 1.0e-9
    center = integrate_bond_slip(slip, parent, material)
    forward = integrate_bond_slip(slip + epsilon, parent, material)
    backward = integrate_bond_slip(slip - epsilon, parent, material)
    finite_difference = (forward.force_n - backward.force_n) / (2.0 * epsilon)
    assert center.consistent_tangent_n_per_m == pytest.approx(
        finite_difference,
        rel=1.0e-9,
    )
    assert center.committed_state_hash == parent.state_hash
    assert parent == BondSlipState()


def test_bond_slip_cyclic_reversals_degrade_deterministically() -> None:
    history = (0.2e-3, 1.4e-3, -0.2e-3, -1.8e-3, 0.3e-3, 4.0e-3)
    first = integrate_bond_slip_history(history)
    second = integrate_bond_slip_history(history)

    assert [row.to_dict() for row in first] == [row.to_dict() for row in second]
    assert first[-1].state.reversal_count == 2
    assert first[-1].state.stiffness_degradation > 0.0
    assert first[-1].state.strength_degradation > 0.0
    assert any(row.reversal for row in first)
    assert any(row.unloading for row in first)
    assert first[-1].branch == "degraded_residual"
    assert first[-1].interaction_ratio == pytest.approx(
        BondSlipMaterial().residual_strength_ratio
    )
    json.dumps(first[-1].to_dict(), allow_nan=False, sort_keys=True)


def test_partial_composite_keeps_constituent_and_connector_authority_separate() -> None:
    material = PartialCompositeMaterial()
    parent = PartialCompositeState()
    full = integrate_partial_composite(
        steel_strain=1.0e-4,
        concrete_strain=1.0e-4,
        interface_slip_m=0.2e-3,
        committed_state=parent,
        material=material,
    )
    partial = integrate_partial_composite(
        steel_strain=2.0e-4,
        concrete_strain=0.5e-4,
        interface_slip_m=1.5e-3,
        committed_state=parent,
        material=material,
    )

    assert full.interaction_ratio == 1.0
    assert 0.0 < partial.interaction_ratio < 1.0
    assert full.combined_axial_force_n == pytest.approx(100_000.0)
    assert partial.combined_axial_force_n == pytest.approx(110_000.0)
    assert partial.generalized_tangent[0][0] == material.steel_axial_rigidity_n
    assert partial.generalized_tangent[1][1] == material.concrete_axial_rigidity_n
    assert partial.generalized_tangent[2][2] < 0.0
    assert partial.committed_state_hash == parent.state_hash
    assert partial.state.state_hash == partial.connector_response.state.state_hash
    assert "distributed beam" in partial.to_dict()["claim_boundary"]


def test_material_namespace_exports_p2_candidates() -> None:
    assert materials.ConfinedConcreteMaterial is ConfinedConcreteMaterial
    assert materials.BondSlipMaterial is BondSlipMaterial
    assert materials.PartialCompositeMaterial is PartialCompositeMaterial
    assert materials.ConfinedConcreteState is ConfinedConcreteState
    assert (
        materials.CondensedPartialCompositeAxialMaterial
        is CondensedPartialCompositeAxialMaterial
    )


def test_confined_concrete_stateful_envelope_replay_is_idempotent() -> None:
    material = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)
    parent = material.initial_state()
    first = material.integrate(-8.0e-4, parent)
    replay = material.integrate(-8.0e-4, first.state)

    assert type(first) is StatefulConfinedConcreteResponse
    assert first.committed_state_hash == parent.state_hash
    assert first.state.maximum_compressive_strain == pytest.approx(8.0e-4)
    assert replay.state == first.state
    assert replay.state.state_hash == first.state.state_hash


def test_condensed_partial_interaction_material_tangent_and_reversal_state() -> None:
    material = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.0,
        reference_area_m2=0.005,
    )
    parent = material.initial_state()
    strain = 2.0e-4
    epsilon = 1.0e-9
    center = material.integrate(strain, parent)
    forward = material.integrate(strain + epsilon, parent)
    backward = material.integrate(strain - epsilon, parent)
    finite_difference = (forward.stress_mpa - backward.stress_mpa) / (
        2.0 * epsilon
    )

    assert center.consistent_tangent_mpa == pytest.approx(
        finite_difference,
        rel=2.0e-9,
    )
    assert center.interface_slip_m > 0.0
    assert center.committed_state_hash == parent.state_hash
    assert parent == CondensedPartialCompositeAxialState()

    reverse = material.integrate(-1.0e-4, center.state)
    connector = reverse.state.component_state.connector_state
    assert connector.reversal_count == 1
    assert connector.stiffness_degradation > 0.0
    assert reverse.partial_composite_response.connector_response.unloading is True
    assert abs(reverse.internal_equilibrium_residual_n) <= (
        material.local_equilibrium_absolute_tolerance_n
    )


def test_condensed_partial_interaction_failed_trial_keeps_parent_exact() -> None:
    material = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.0,
        reference_area_m2=0.005,
        maximum_local_iterations=1,
    )
    parent = material.initial_state()
    parent_bytes = parent.canonical_bytes()

    with pytest.raises(RuntimeError, match="did not converge"):
        material.integrate(5.0e-3, parent)

    assert parent == material.initial_state()
    assert parent.canonical_bytes() == parent_bytes
