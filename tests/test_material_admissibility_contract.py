from __future__ import annotations

import json
from pathlib import Path

import pytest

from implementation.phase1.rc_constitutive_library import (
    BondSlipMaterial,
    CompositeActionMaterial,
    ConcreteCyclicState,
    ConcreteMaterial,
    SteelMaterial,
    concrete_cyclic_response,
    confined_concrete,
)
from structural_analysis.assembly.nonlinear_static import (
    CubicSpringAxialMaterialLaw,
    StrainCubicAxialMaterialLaw,
)
from structural_analysis.materials import (
    ConfinedConcreteMaterial,
    ElasticIsotropicMaterial,
    MaterialAdmissibility,
    MaterialPathNotAdmissibleError,
    require_scalar_loading_path_admissible,
    scalar_loading_path_demand,
)
from structural_analysis.model import ElasticMaterial
from structural_analysis.model_ir import validate_model_ir_v2


EXPECTED_FIELDS = {
    "loading_domain",
    "supports_unloading",
    "supports_reversal",
    "supports_cyclic",
    "supports_tension",
    "supports_compression",
    "supports_multiaxial",
}


def test_shared_material_admissibility_contract_has_required_fields() -> None:
    contract = MaterialAdmissibility(
        loading_domain="monotonic_compression",
        supports_unloading=False,
        supports_reversal=False,
        supports_cyclic=False,
        supports_tension=False,
        supports_compression=True,
        supports_multiaxial=False,
    )

    assert set(contract.to_dict()) == EXPECTED_FIELDS
    assert contract.to_dict()["loading_domain"] == "monotonic_compression"


def test_scalar_loading_demand_detects_unloading_reversal_and_cyclic_path() -> None:
    demand = scalar_loading_path_demand((100.0, 20.0, -120.0, 80.0))

    assert demand.requires_tension is True
    assert demand.requires_compression is True
    assert demand.requires_unloading is True
    assert demand.requires_reversal is True
    assert demand.requires_cyclic is True


def test_unsupported_reversal_is_blocked_before_material_execution() -> None:
    contract = MaterialAdmissibility(
        loading_domain="monotonic_compression",
        supports_unloading=False,
        supports_reversal=False,
        supports_cyclic=False,
        supports_tension=False,
        supports_compression=True,
        supports_multiaxial=False,
    )

    with pytest.raises(
        MaterialPathNotAdmissibleError,
        match="material_loading_path_not_admissible",
    ):
        require_scalar_loading_path_admissible(
            contract,
            (-10.0, -2.0, -12.0),
            owner="confined_concrete",
        )


def test_core_material_contracts_publish_explicit_admissibility() -> None:
    elastic = ElasticIsotropicMaterial(
        material_id="E1",
        elastic_modulus=2.0e8,
        poisson_ratio=0.3,
    )
    cubic = CubicSpringAxialMaterialLaw()
    strain_cubic = StrainCubicAxialMaterialLaw(length_m=2.0)

    assert set(elastic.admissibility.to_dict()) == EXPECTED_FIELDS
    assert elastic.supports_multiaxial is True
    assert cubic.admissibility.supports_cyclic is True
    assert strain_cubic.admissibility.supports_cyclic is True


def test_canonical_elastic_material_exposes_same_authoritative_contract() -> None:
    material = ElasticMaterial.from_mapping(
        {
            "id": "M1",
            "type": "elastic",
            "elastic_modulus": 2.0e8,
            "poisson_ratio": 0.3,
        }
    )

    assert set(material.admissibility.to_dict()) == EXPECTED_FIELDS
    assert material.supports_multiaxial is True


def test_canonical_elastic_material_preserves_nondefault_admissibility() -> None:
    material = ElasticMaterial(
        id="M1",
        elastic_modulus=2.0e8,
        supports_unloading=False,
        supports_reversal=False,
        supports_cyclic=False,
    )

    restored = ElasticMaterial.from_mapping(material.to_dict())

    assert restored.admissibility == material.admissibility
    assert restored.to_dict() == material.to_dict()


def test_model_ir_v2_accepts_additive_material_admissibility_contract() -> None:
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "model_ir_v2"
        / "frame_cantilever_all_modes.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["materials"][0]["admissibility"] = {
        "loading_domain": "finite_linear_elastic_3d",
        "supports_unloading": True,
        "supports_reversal": True,
        "supports_cyclic": True,
        "supports_tension": True,
        "supports_compression": True,
        "supports_multiaxial": True,
    }

    report = validate_model_ir_v2(payload)

    assert report.contract_valid is True


def test_phase1_material_contracts_declare_conservative_path_support() -> None:
    concrete = ConcreteMaterial()
    steel = SteelMaterial()
    bond = BondSlipMaterial()
    composite = CompositeActionMaterial()

    assert set(concrete.admissibility.to_dict()) == EXPECTED_FIELDS
    assert concrete.supports_cyclic is True
    assert bond.supports_cyclic is True
    assert steel.supports_cyclic is False
    assert composite.supports_cyclic is False


def test_phase1_confined_concrete_reversal_guard_follows_declared_support() -> None:
    monotonic = ConcreteMaterial(
        supports_unloading=False,
        supports_reversal=False,
        supports_cyclic=False,
    )
    confined = confined_concrete(monotonic, 1.2)
    state = ConcreteCyclicState(
        previous_strain=-0.002,
        previous_stress_mpa=-20.0,
        last_increment_sign=-1,
    )

    with pytest.raises(
        MaterialPathNotAdmissibleError,
        match="unsupported=unloading,reversal,cyclic",
    ):
        concrete_cyclic_response(-0.001, state=state, mat=confined)


def test_authoritative_confined_concrete_blocks_unloading_before_response() -> None:
    material = ConfinedConcreteMaterial()
    loaded = material.integrate(-0.002, material.initial_state())

    with pytest.raises(
        MaterialPathNotAdmissibleError,
        match="unsupported=unloading",
    ):
        material.integrate(-0.001, loaded.state)
