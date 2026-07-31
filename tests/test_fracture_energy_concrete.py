from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.benchmark.fracture_energy_concrete import (
    FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION,
    FractureEnergyConcreteBenchmarkError,
    build_fracture_energy_concrete_mesh_objectivity_benchmark,
    validate_fracture_energy_concrete_mesh_objectivity_benchmark,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    FRACTURE_ENERGY_DAMAGE_ALGORITHM,
    FRACTURE_ENERGY_TANGENT_DEFINITION,
    FractureEnergyConcreteDamageMaterial,
    finite_difference_concrete_damage_tangent_check,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT / "src/structural_analysis/schemas/"
    "fracture_energy_concrete_mesh_objectivity_v1.schema.json"
)
ARTIFACT_PATH = (
    ROOT / "artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json"
)


def _rehash(payload: dict[str, Any]) -> None:
    payload["artifact_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )


@pytest.fixture(scope="module")
def benchmark() -> dict[str, Any]:
    return build_fracture_energy_concrete_mesh_objectivity_benchmark(repo_root=ROOT)


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
    assert material.tangent_definition == FRACTURE_ENERGY_TANGENT_DEFINITION
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
    assert check["tangent_definition"] == FRACTURE_ENERGY_TANGENT_DEFINITION
    assert check["pass"] is True
    assert check["same_committed_parent_state"] is True
    assert initial == material.initial_state()


def test_fracture_energy_material_fails_closed_for_invalid_mapping() -> None:
    with pytest.raises(ValueError, match="crack-band mapping"):
        FractureEnergyConcreteDamageMaterial(
            characteristic_length_m=1.0,
            tensile_fracture_energy_n_per_m=10.0,
        )
    with pytest.raises(ValueError, match=r"must be (?:a )?finite"):
        FractureEnergyConcreteDamageMaterial(characteristic_length_m=math.nan)


def test_mesh_objectivity_benchmark_is_deterministic_hashed_and_bounded(
    benchmark: dict[str, Any],
) -> None:
    repeated = build_fracture_energy_concrete_mesh_objectivity_benchmark(repo_root=ROOT)
    body = deepcopy(benchmark)
    artifact_hash = body.pop("artifact_hash")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(benchmark)
    assert benchmark == repeated
    assert benchmark["schema_version"] == (
        FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION
    )
    assert artifact_hash == canonical_hash(body)
    assert benchmark["status"] == "candidate_verified"
    assert benchmark["contract_pass"] is True
    assert all(benchmark["checks"].values())
    assert benchmark["metrics"]["maximum_rc_force_history_scaled_linf"] <= (1.0e-8)
    assert benchmark["metrics"]["concrete_fracture_energy_spread_relative"] <= 1.0e-12
    assert [row["mesh_count"] for row in benchmark["mesh_cases"]] == [2, 4, 8]
    assert all(
        row["localized_element_indices"] == [row["mesh_count"] - 1]
        for row in benchmark["mesh_cases"]
    )
    assert all(
        row["accepted_state_path_hash"] == row["replay_accepted_state_path_hash"]
        for row in benchmark["mesh_cases"]
    )
    assert benchmark["claims"]["bounded_seeded_rc_tie_mesh_objectivity"] is True
    assert benchmark["claims"]["arbitrary_rc_frame_or_shell_mesh_objectivity"] is False
    assert benchmark["claims"]["published_or_external_validation"] is False
    assert benchmark["claims"]["independent_engineering_review"] is False
    assert benchmark["claims"]["release_readiness"] is False


def test_semantic_validation_rejects_rehashed_force_tampering(
    benchmark: dict[str, Any],
) -> None:
    tampered = deepcopy(benchmark)
    tampered["mesh_cases"][0]["total_rc_force_history_kn"][-1] += 1.0e-3
    _rehash(tampered)

    with pytest.raises(
        FractureEnergyConcreteBenchmarkError,
        match="total_force_history_invalid",
    ):
        validate_fracture_energy_concrete_mesh_objectivity_benchmark(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
            rerun=False,
        )


def test_schema_rejects_rehashed_claim_promotion(
    benchmark: dict[str, Any],
) -> None:
    tampered = deepcopy(benchmark)
    tampered["claims"]["release_readiness"] = True
    _rehash(tampered)

    with pytest.raises(
        FractureEnergyConcreteBenchmarkError,
        match="schema_invalid",
    ):
        validate_fracture_energy_concrete_mesh_objectivity_benchmark(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
            rerun=False,
        )


def test_current_source_validation_rejects_rehashed_stale_source(
    benchmark: dict[str, Any],
) -> None:
    tampered = deepcopy(benchmark)
    first_path = next(iter(tampered["source"]["input_checksums"]))
    tampered["source"]["input_checksums"][first_path] = "sha256:" + "0" * 64
    tampered["source"]["source_set_hash"] = canonical_hash(
        tampered["source"]["input_checksums"]
    )
    _rehash(tampered)

    with pytest.raises(
        FractureEnergyConcreteBenchmarkError,
        match="sources_stale",
    ):
        validate_fracture_energy_concrete_mesh_objectivity_benchmark(
            tampered,
            repo_root=ROOT,
            require_current_sources=True,
            rerun=False,
        )


def test_committed_receipt_is_current_source_bound_and_reproducible() -> None:
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))

    validated = validate_fracture_energy_concrete_mesh_objectivity_benchmark(
        committed,
        repo_root=ROOT,
        require_current_sources=True,
        rerun=True,
    )

    assert validated["contract_pass"] is True
