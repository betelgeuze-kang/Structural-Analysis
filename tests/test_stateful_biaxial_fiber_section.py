from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    FractureEnergyConcreteDamageMaterial,
)
from structural_analysis.materials.confined_concrete import ConfinedConcreteMaterial
from structural_analysis.materials.stateful_biaxial_fiber_section import (
    StatefulBiaxialFiberSection,
    StatefulBiaxialSectionFiber,
    finite_difference_biaxial_fiber_section_tangent_check,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


def _steel() -> BilinearCombinedHardeningSteel:
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=10_000.0,
        kinematic_hardening_modulus_mpa=10_000.0,
        material_id="biaxial-section-steel",
    )


def _symmetric_steel_section() -> StatefulBiaxialFiberSection:
    steel = _steel()
    return StatefulBiaxialFiberSection(
        fibers=tuple(
            StatefulBiaxialSectionFiber(
                fiber_id=f"steel-{index}",
                y_m=y,
                z_m=z,
                area_m2=0.0025,
                material=steel,
            )
            for index, (y, z) in enumerate(
                ((-0.15, -0.10), (-0.15, 0.10), (0.15, -0.10), (0.15, 0.10))
            )
        ),
        section_id="symmetric-steel-biaxial",
    )


def test_biaxial_fiber_section_initial_resultants_and_tangent() -> None:
    section = _symmetric_steel_section()
    initial = section.initial_state()
    response = section.integrate((0.0, 0.0, 0.0), initial)

    np.testing.assert_allclose(response.resultants, 0.0, atol=0.0, rtol=0.0)
    expected_ea = 200_000.0 * 0.01 * 1000.0
    expected_eiy = 200_000.0 * (4.0 * 0.0025 * 0.10**2) * 1000.0
    expected_eiz = 200_000.0 * (4.0 * 0.0025 * 0.15**2) * 1000.0
    np.testing.assert_allclose(
        response.consistent_tangent,
        np.diag((expected_ea, expected_eiy, expected_eiz)),
        atol=1.0e-10,
        rtol=1.0e-14,
    )
    assert response.state == initial
    assert response.state.state_hash == initial.state_hash


def test_biaxial_fiber_section_same_parent_plastic_tangent() -> None:
    section = _symmetric_steel_section()
    parent = section.initial_state()
    check = finite_difference_biaxial_fiber_section_tangent_check(
        section,
        parent,
        generalized_strain=(1.6e-3, 8.0e-4, -6.0e-4),
    )

    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert check["relative_inf_error"] <= 3.0e-6
    response = section.integrate((1.6e-3, 8.0e-4, -6.0e-4), parent)
    assert response.yielded_steel_fiber_count == 4
    assert response.dissipated_energy_mj_per_m > 0.0
    assert parent == section.initial_state()


def test_mixed_fiber_material_states_are_distinct_and_replay_exactly() -> None:
    steel = _steel()
    concrete = AsymmetricConcreteDamageMaterial(material_id="biaxial-concrete")
    fracture = FractureEnergyConcreteDamageMaterial(
        characteristic_length_m=0.1,
        tensile_fracture_energy_n_per_m=1000.0,
        compressive_fracture_energy_n_per_m=100_000.0,
        material_id="biaxial-fracture-concrete",
    )
    confined = ConfinedConcreteMaterial(
        effective_lateral_pressure_mpa=2.0,
        material_id="biaxial-confined-concrete",
    )
    section = StatefulBiaxialFiberSection(
        fibers=(
            StatefulBiaxialSectionFiber("steel", -0.1, -0.1, 0.001, steel),
            StatefulBiaxialSectionFiber("damage", 0.1, -0.1, 0.004, concrete),
            StatefulBiaxialSectionFiber("fracture", -0.1, 0.1, 0.004, fracture),
            StatefulBiaxialSectionFiber("confined", 0.1, 0.1, 0.004, confined),
        ),
        section_id="mixed-biaxial-materials",
    )
    parent = section.initial_state()
    response = section.integrate((-8.0e-4, 2.0e-3, -1.0e-3), parent)
    replay = section.integrate(
        response.generalized_strain,
        response.state,
    )

    assert len({type(state) for state in response.state.fiber_states}) == 3
    assert response.parent_state_hash == parent.state_hash
    assert replay.state == response.state
    assert replay.state.state_hash == response.state.state_hash
    assert response.consistent_tangent.flags.writeable is False
    assert response.to_dict()["claim_boundary"]


def test_biaxial_fiber_section_rejects_tampered_state_contract() -> None:
    section = _symmetric_steel_section()
    other = StatefulBiaxialFiberSection(
        fibers=section.fibers,
        section_id="different-section-id",
    )
    with pytest.raises(ValueError, match="section_id"):
        section.integrate((0.0, 0.0, 0.0), other.initial_state())
