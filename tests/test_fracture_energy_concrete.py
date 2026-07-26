from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.benchmark.fracture_energy_concrete import (
    FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION,
    build_fracture_energy_concrete_mesh_objectivity_benchmark,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    FRACTURE_ENERGY_DAMAGE_ALGORITHM,
    FractureEnergyConcreteDamageMaterial,
    finite_difference_concrete_damage_tangent_check,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("characteristic_length_m", (0.005, 0.01, 0.02))
def test_crack_opening_traction_and_energy_are_length_invariant(
    characteristic_length_m: float,
) -> None:
    material = FractureEnergyConcreteDamageMaterial(
        characteristic_length_m=characteristic_length_m,
        tensile_fracture_energy_n_per_m=100.0,
    )
    fracture_energy_mj_per_m2 = 100.0 / 1.0e6
    crack_opening_m = 3.0e-4
    expected_traction = material.tensile_strength_mpa * math.exp(
        -material.tensile_strength_mpa * crack_opening_m / fracture_energy_mj_per_m2
    )
    strain = (
        expected_traction / material.elastic_modulus_mpa
        + crack_opening_m / characteristic_length_m
    )

    response = material.integrate(strain, material.initial_state())

    assert material.damage_algorithm == FRACTURE_ENERGY_DAMAGE_ALGORITHM
    assert response.stress_mpa == pytest.approx(expected_traction, abs=1.0e-12)
    assert (
        response.state.dissipated_energy_density_mj_per_m3
        * characteristic_length_m
        * 1.0e6
    ) == pytest.approx(100.0, rel=7.0e-4)


@pytest.mark.parametrize("strain", (0.002, -0.002))
def test_fracture_energy_material_tangent_matches_same_parent_difference(
    strain: float,
) -> None:
    material = FractureEnergyConcreteDamageMaterial(characteristic_length_m=0.01)
    initial = material.initial_state()
    check = finite_difference_concrete_damage_tangent_check(
        material,
        initial,
        total_strain=strain,
        epsilon=1.0e-8,
        relative_tolerance=1.0e-7,
    )

    assert check["damage_algorithm"] == FRACTURE_ENERGY_DAMAGE_ALGORITHM
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert initial == material.initial_state()


def test_fracture_energy_material_fails_closed_for_nonmonotone_mapping() -> None:
    with pytest.raises(ValueError, match="crack-band mapping"):
        FractureEnergyConcreteDamageMaterial(
            characteristic_length_m=1.0,
            tensile_fracture_energy_n_per_m=10.0,
        )


def test_mesh_objectivity_benchmark_is_deterministic_hashed_and_bounded() -> None:
    first = build_fracture_energy_concrete_mesh_objectivity_benchmark()
    repeated = build_fracture_energy_concrete_mesh_objectivity_benchmark()
    body = deepcopy(first)
    artifact_hash = body.pop("artifact_hash")
    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/fracture_energy_concrete_mesh_objectivity_v1.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(first)
    assert first == repeated
    assert first["schema_version"] == (
        FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION
    )
    assert artifact_hash == canonical_hash(body)
    assert first["status"] == "candidate_verified"
    assert first["contract_pass"] is True
    assert all(first["checks"].values())
    assert first["metrics"]["maximum_rc_force_history_scaled_linf"] <= 1.0e-8
    assert first["metrics"]["concrete_fracture_energy_spread_relative"] <= 1.0e-12
    assert [row["mesh_count"] for row in first["mesh_cases"]] == [2, 4, 8]
    assert all(
        row["localized_element_indices"] == [row["mesh_count"] - 1]
        for row in first["mesh_cases"]
    )
    assert first["claims"]["bounded_seeded_rc_tie_mesh_objectivity"] is True
    assert first["claims"]["arbitrary_rc_frame_or_shell_mesh_objectivity"] is False
    assert first["claims"]["published_or_external_validation"] is False


def test_benchmark_hash_detects_semantic_tampering() -> None:
    receipt = build_fracture_energy_concrete_mesh_objectivity_benchmark()
    tampered = deepcopy(receipt)
    tampered["mesh_cases"][0]["total_rc_force_history_kn"][-1] += 1.0e-3
    claimed = tampered.pop("artifact_hash")

    assert canonical_hash(tampered) != claimed


def test_committed_benchmark_receipt_has_no_generator_drift() -> None:
    expected = build_fracture_energy_concrete_mesh_objectivity_benchmark()
    committed = json.loads(
        (
            ROOT
            / "artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json"
        ).read_text(encoding="utf-8")
    )

    assert committed == expected
