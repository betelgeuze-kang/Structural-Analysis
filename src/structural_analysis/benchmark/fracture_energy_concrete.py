"""Source-bound crack-band concrete and RC-tie mesh-objectivity benchmark."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
import numpy as np

from structural_analysis.assembly.stateful_axial import (
    StatefulAxialChainProblem,
    StatefulAxialElement,
    StatefulUniaxialMaterial,
    run_stateful_axial_load_path,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    FRACTURE_ENERGY_DAMAGE_ALGORITHM,
    FRACTURE_ENERGY_TANGENT_DEFINITION,
    ConcreteDamageState,
    FractureEnergyConcreteDamageMaterial,
    finite_difference_concrete_damage_tangent_check,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION = (
    "fracture-energy-concrete-mesh-objectivity-benchmark.v1"
)
FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "fracture_energy_concrete_mesh_objectivity_v1.schema.json"
)
FRACTURE_ENERGY_CONCRETE_BENCHMARK_PROFILE = (
    "localized_crack_band_rc_tie_2_4_8_meshes.v1"
)
FRACTURE_ENERGY_CONCRETE_NUMERIC_SERIALIZATION = "canonical_json_binary64_round_trip"
FRACTURE_ENERGY_CONCRETE_TRUTH_CLASS = (
    "repository_generated_bounded_mechanics_candidate"
)
FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY = (
    "This candidate verifies a uniaxial exponential traction-opening crack-band "
    "law and a seeded single-crack reinforced-concrete tie idealization at 2, 4, "
    "and 8 concrete elements. Continuous reinforcement is one global parallel "
    "tie, perfect bond is assumed at the end sections, and localization is "
    "prescribed by a terminal concrete element with 3.0 MPa tensile strength "
    "while the other elements are 10 percent stronger at 3.3 MPa. It does not "
    "establish multiaxial concrete, confinement, bond slip, arbitrary "
    "localization, frame or shell mesh objectivity, published or external "
    "validation, independent engineering review, design authority, or release "
    "readiness."
)
FRACTURE_ENERGY_CONCRETE_BLOCKERS_REMAINING = (
    "arbitrary_frame_or_shell_localization_not_verified",
    "multiaxial_and_confined_concrete_not_verified",
    "bond_slip_not_verified",
    "published_or_external_validation_not_included",
    "independent_engineering_review_not_included",
    "release_readiness_not_established",
)

_SOURCE_PATHS = (
    Path("src/structural_analysis/benchmark/fracture_energy_concrete.py"),
    Path("src/structural_analysis/benchmark/__init__.py"),
    Path("src/structural_analysis/materials/concrete_damage.py"),
    Path("src/structural_analysis/materials/__init__.py"),
    Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
    Path("src/structural_analysis/assembly/stateful_axial.py"),
    Path("src/structural_analysis/solvers/nonlinear/newton.py"),
    Path("src/structural_analysis/engine_v2/contracts/_canonical.py"),
    FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_PATH,
    Path("scripts/build_fracture_energy_concrete_benchmark.py"),
    Path("tests/test_fracture_energy_concrete.py"),
    Path("docs/fracture-energy-concrete-mesh-objectivity.md"),
    Path("artifacts/manifests/capabilities.yaml"),
)
_HASH_ZERO = "sha256:" + "0" * 64
_MESH_COUNTS = (2, 4, 8)
_CRACK_OPENINGS_M = (0.0, 1.0e-5, 5.0e-5, 1.0e-4, 3.0e-4)
_LENGTH_M = 0.04
_GROSS_AREA_M2 = 0.01
_REINFORCEMENT_RATIO = 0.01
_TERMINAL_DISPLACEMENT_M = 3.5e-4
_LOAD_STEP_COUNT = 50
_TENSILE_FRACTURE_ENERGY_N_PER_M = 100.0
_TERMINAL_TENSILE_STRENGTH_MPA = 3.0
_OTHER_TENSILE_STRENGTH_MPA = 3.3


class FractureEnergyConcreteBenchmarkError(ValueError):
    """Fail-closed fracture-energy receipt error."""


def _repo_root(path: Path | None) -> Path:
    return (path or Path(__file__).resolve().parents[3]).resolve()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _source_checksums(repo_root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for relative in _SOURCE_PATHS:
        path = repo_root / relative
        if not path.is_file():
            raise FractureEnergyConcreteBenchmarkError(
                f"fracture_energy_source_missing:{relative.as_posix()}"
            )
        checksums[relative.as_posix()] = _file_hash(path)
    return checksums


def _scaled_linf(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    if left_array.shape != right_array.shape or left_array.size == 0:
        raise FractureEnergyConcreteBenchmarkError(
            "fracture_energy_force_history_shape_invalid"
        )
    return float(np.max(np.abs(left_array - right_array))) / max(
        1.0,
        float(np.max(np.abs(left_array))),
        float(np.max(np.abs(right_array))),
    )


def _material(
    characteristic_length_m: float,
    *,
    tensile_strength_mpa: float,
) -> FractureEnergyConcreteDamageMaterial:
    return FractureEnergyConcreteDamageMaterial(
        elastic_modulus_mpa=30_000.0,
        tensile_strength_mpa=tensile_strength_mpa,
        compressive_strength_mpa=30.0,
        characteristic_length_m=characteristic_length_m,
        tensile_fracture_energy_n_per_m=_TENSILE_FRACTURE_ENERGY_N_PER_M,
        compressive_fracture_energy_n_per_m=20_000.0,
        history_tolerance=1.0e-14,
    )


def _mesh_case(mesh_count: int) -> dict[str, Any]:
    element_length = _LENGTH_M / mesh_count
    concrete_area = _GROSS_AREA_M2 * (1.0 - _REINFORCEMENT_RATIO)
    elements = tuple(
        StatefulAxialElement(
            element_id=f"concrete-{index + 1}",
            node_i=index,
            node_j=index + 1,
            length_m=element_length,
            area_m2=concrete_area,
            material=cast(
                StatefulUniaxialMaterial,
                _material(
                    element_length,
                    tensile_strength_mpa=(
                        _TERMINAL_TENSILE_STRENGTH_MPA
                        if index == mesh_count - 1
                        else _OTHER_TENSILE_STRENGTH_MPA
                    ),
                ),
            ),
        )
        for index in range(mesh_count)
    )
    problem = StatefulAxialChainProblem(
        case_id=f"fracture_energy_rc_tie_mesh_{mesh_count}",
        node_count=mesh_count + 1,
        elements=elements,
        fixed_nodes=(0,),
        reference_external_forces_kn=(),
        reference_prescribed_displacements_m=((mesh_count, _TERMINAL_DISPLACEMENT_M),),
    )
    targets = tuple(
        index / _LOAD_STEP_COUNT for index in range(1, _LOAD_STEP_COUNT + 1)
    )
    newton_config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-9,
        increment_tolerance=1.0e-12,
        max_iterations=80,
    )
    path = run_stateful_axial_load_path(
        problem,
        targets,
        config=newton_config,
    )
    replay = run_stateful_axial_load_path(
        problem,
        targets,
        config=newton_config,
    )
    path_state_hashes = [step.accepted_state.state_hash for step in path.steps]
    replay_state_hashes = [step.accepted_state.state_hash for step in replay.steps]

    steel = BilinearCombinedHardeningSteel()
    steel_state = steel.initial_state()
    steel_area = _GROSS_AREA_M2 * _REINFORCEMENT_RATIO
    concrete_force_history: list[float] = []
    reinforcement_force_history: list[float] = []
    total_force_history: list[float] = []
    maximum_equilibrium_spread = 0.0
    for step, target in zip(path.steps, targets, strict=True):
        concrete_forces = [
            float(row["internal_force_kn"])
            for row in step.trial_assembly.element_responses
        ]
        maximum_equilibrium_spread = max(
            maximum_equilibrium_spread,
            max(concrete_forces) - min(concrete_forces),
        )
        concrete_force = math.fsum(concrete_forces) / len(concrete_forces)
        global_strain = target * _TERMINAL_DISPLACEMENT_M / _LENGTH_M
        steel_response = steel.integrate(global_strain, steel_state)
        steel_state = steel_response.state
        reinforcement_force = steel_response.stress_mpa * steel_area * 1_000.0
        concrete_force_history.append(concrete_force)
        reinforcement_force_history.append(reinforcement_force)
        total_force_history.append(concrete_force + reinforcement_force)

    final_states = path.final_state.material_states
    concrete_dissipated_energy_j = 0.0
    localized_indices: list[int] = []
    final_damage: list[float] = []
    for index, (element, state) in enumerate(
        zip(problem.elements, final_states, strict=True)
    ):
        if type(state) is not ConcreteDamageState:
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_mesh_state_type_invalid"
            )
        damage = state.tensile_damage
        final_damage.append(damage)
        if damage > 0.5:
            localized_indices.append(index)
        concrete_dissipated_energy_j += (
            state.dissipated_energy_density_mj_per_m3
            * element.length_m
            * element.area_m2
            * 1.0e6
        )
    expected_energy_j = _TENSILE_FRACTURE_ENERGY_N_PER_M * concrete_area
    fallback_count = sum(
        step.metrics.get("fallback_used") is True for step in path.steps
    )
    regularization_count = sum(
        step.metrics.get("regularization_used") is True for step in path.steps
    )
    checks = {
        "path_contract_pass": path.contract_pass,
        "all_steps_committed": bool(
            len(path.steps) == _LOAD_STEP_COUNT
            and all(step.committed for step in path.steps)
        ),
        "equilibrium_pass": maximum_equilibrium_spread <= 1.0e-8,
        "single_seeded_localization": localized_indices == [mesh_count - 1],
        "deterministic_state_replay": bool(
            replay.contract_pass
            and path.final_state.state_hash == replay.final_state.state_hash
            and path_state_hashes == replay_state_hashes
        ),
        "zero_fallback": fallback_count == 0,
        "zero_regularization": regularization_count == 0,
        "terminal_displacement_exact": bool(
            path.final_state.displacements_m[-1] == _TERMINAL_DISPLACEMENT_M
        ),
        "fracture_energy_saturation_pass": bool(
            abs(concrete_dissipated_energy_j - expected_energy_j) / expected_energy_j
            <= 5.0e-4
        ),
    }
    return {
        "mesh_count": mesh_count,
        "element_length_m": element_length,
        "problem_case_id": problem.case_id,
        "step_count": len(path.steps),
        "terminal_state_hash": path.final_state.state_hash,
        "accepted_state_path_hash": canonical_hash(path_state_hashes),
        "replay_accepted_state_path_hash": canonical_hash(replay_state_hashes),
        "status": path.status,
        "contract_pass": all(checks.values()),
        "concrete_force_history_kn": concrete_force_history,
        "reinforcement_force_history_kn": reinforcement_force_history,
        "total_rc_force_history_kn": total_force_history,
        "terminal_displacement_m": _TERMINAL_DISPLACEMENT_M,
        "maximum_equilibrium_force_spread_kn": maximum_equilibrium_spread,
        "concrete_dissipated_energy_j": concrete_dissipated_energy_j,
        "expected_tensile_fracture_energy_j": expected_energy_j,
        "fracture_energy_relative_error": abs(
            concrete_dissipated_energy_j - expected_energy_j
        )
        / expected_energy_j,
        "localized_element_indices": localized_indices,
        "final_tensile_damage": final_damage,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "checks": checks,
    }


def _configuration() -> dict[str, Any]:
    return {
        "mesh_counts": list(_MESH_COUNTS),
        "length_m": _LENGTH_M,
        "gross_area_m2": _GROSS_AREA_M2,
        "reinforcement_ratio": _REINFORCEMENT_RATIO,
        "terminal_displacement_m": _TERMINAL_DISPLACEMENT_M,
        "load_step_count": _LOAD_STEP_COUNT,
        "tensile_fracture_energy_n_per_m": (_TENSILE_FRACTURE_ENERGY_N_PER_M),
        "terminal_tensile_strength_mpa": _TERMINAL_TENSILE_STRENGTH_MPA,
        "other_tensile_strength_mpa": _OTHER_TENSILE_STRENGTH_MPA,
        "seeded_localization": ("terminal_nominal_ft_others_10_percent_higher"),
        "reinforcement_idealization": "single_global_parallel_tie",
    }


def build_fracture_energy_concrete_mesh_objectivity_benchmark(
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build the deterministic, source-bound, non-promoting benchmark receipt."""

    root = _repo_root(repo_root)
    opening_rows: list[dict[str, Any]] = []
    maximum_traction_error = 0.0
    opening_energy_by_length: list[float] = []
    tangent_checks: list[dict[str, Any]] = []
    for mesh_count in _MESH_COUNTS:
        characteristic_length = _LENGTH_M / mesh_count
        material = _material(
            characteristic_length,
            tensile_strength_mpa=_TERMINAL_TENSILE_STRENGTH_MPA,
        )
        rows: list[dict[str, float]] = []
        for crack_opening in _CRACK_OPENINGS_M:
            energy_mj_per_m2 = material.tensile_fracture_energy_n_per_m / 1.0e6
            expected_traction = material.tensile_strength_mpa * math.exp(
                -material.tensile_strength_mpa * crack_opening / energy_mj_per_m2
            )
            strain = (
                expected_traction / material.elastic_modulus_mpa
                + crack_opening / characteristic_length
            )
            response = material.integrate(strain, material.initial_state())
            traction_error = abs(response.stress_mpa - expected_traction)
            maximum_traction_error = max(maximum_traction_error, traction_error)
            rows.append(
                {
                    "crack_opening_m": crack_opening,
                    "total_strain": strain,
                    "traction_mpa": response.stress_mpa,
                    "expected_traction_mpa": expected_traction,
                    "dissipated_energy_mj_per_m2": (
                        response.state.dissipated_energy_density_mj_per_m3
                        * characteristic_length
                    ),
                }
            )
        opening_energy_by_length.append(rows[-1]["dissipated_energy_mj_per_m2"])
        opening_rows.append(
            {
                "mesh_count": mesh_count,
                "characteristic_length_m": characteristic_length,
                "material_contract_hash": canonical_hash(asdict(material)),
                "rows": rows,
            }
        )
        tangent_checks.extend(
            finite_difference_concrete_damage_tangent_check(
                material,
                material.initial_state(),
                total_strain=strain,
                epsilon=1.0e-8,
                relative_tolerance=1.0e-7,
            )
            for strain in (0.002, -0.002)
        )

    mesh_cases = [_mesh_case(mesh_count) for mesh_count in _MESH_COUNTS]
    reference_force = mesh_cases[0]["total_rc_force_history_kn"]
    force_parity = [
        _scaled_linf(reference_force, row["total_rc_force_history_kn"])
        for row in mesh_cases[1:]
    ]
    energy_values = [row["concrete_dissipated_energy_j"] for row in mesh_cases]
    energy_spread_relative = (max(energy_values) - min(energy_values)) / max(
        max(energy_values), 1.0e-30
    )
    opening_energy_spread = max(opening_energy_by_length) - min(
        opening_energy_by_length
    )
    fallback_count = sum(row["fallback_count"] for row in mesh_cases)
    regularization_count = sum(row["regularization_count"] for row in mesh_cases)
    checks = {
        "implicit_tangent_finite_difference_pass": all(
            row["pass"] is True for row in tangent_checks
        ),
        "traction_opening_length_invariant": maximum_traction_error <= 1.0e-12,
        "opening_energy_length_invariant": opening_energy_spread <= 1.0e-15,
        "all_mesh_cases_pass": all(row["contract_pass"] for row in mesh_cases),
        "rc_force_history_mesh_objective": (max(force_parity, default=0.0) <= 1.0e-8),
        "fracture_energy_mesh_objective": energy_spread_relative <= 1.0e-12,
        "zero_fallback_and_regularization": bool(
            fallback_count == 0 and regularization_count == 0
        ),
    }
    contract_pass = all(checks.values())
    checksums = _source_checksums(root)
    payload: dict[str, Any] = {
        "schema_version": FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION,
        "artifact_hash": _HASH_ZERO,
        "numeric_serialization_profile": (
            FRACTURE_ENERGY_CONCRETE_NUMERIC_SERIALIZATION
        ),
        "truth_class": FRACTURE_ENERGY_CONCRETE_TRUTH_CLASS,
        "source": {
            "input_checksums": checksums,
            "source_set_hash": canonical_hash(checksums),
        },
        "status": "candidate_verified" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "profile": FRACTURE_ENERGY_CONCRETE_BENCHMARK_PROFILE,
        "material_algorithm": FRACTURE_ENERGY_DAMAGE_ALGORITHM,
        "tangent_definition": FRACTURE_ENERGY_TANGENT_DEFINITION,
        "configuration": _configuration(),
        "traction_opening_cases": opening_rows,
        "tangent_checks": tangent_checks,
        "mesh_cases": mesh_cases,
        "metrics": {
            "maximum_traction_absolute_error_mpa": maximum_traction_error,
            "maximum_rc_force_history_scaled_linf": max(force_parity, default=0.0),
            "concrete_fracture_energy_spread_relative": energy_spread_relative,
            "opening_energy_spread_mj_per_m2": opening_energy_spread,
            "fallback_count": fallback_count,
            "regularization_count": regularization_count,
        },
        "checks": checks,
        "claims": {
            "uniaxial_fracture_energy_regularization": contract_pass,
            "bounded_seeded_rc_tie_mesh_objectivity": contract_pass,
            "arbitrary_rc_frame_or_shell_mesh_objectivity": False,
            "multiaxial_or_confined_concrete": False,
            "bond_slip": False,
            "published_or_external_validation": False,
            "independent_engineering_review": False,
            "release_readiness": False,
        },
        "limitations": [
            "uniaxial_tension_compression_only",
            "seeded_single_localization_band",
            "global_parallel_reinforcement_tie",
            "no_confinement_bond_slip_or_multiaxial_coupling",
            "no_arbitrary_frame_or_shell_localization_claim",
            "no_published_or_external_benchmark_credit",
        ],
        "blockers_remaining": list(FRACTURE_ENERGY_CONCRETE_BLOCKERS_REMAINING),
        "claim_boundary": FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY,
    }
    payload["artifact_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    _validate_schema_and_semantics(payload, repo_root=root)
    return payload


def _assert_finite(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_nonfinite_number"
            )
        return
    if isinstance(value, list):
        for item in value:
            _assert_finite(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_finite(item)


def _close(left: Any, right: Any) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1.0e-13, abs_tol=1.0e-15)


def _validate_schema_and_semantics(
    payload: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    _assert_finite(payload)
    try:
        schema = json.loads(
            (repo_root / FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_PATH).read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (OSError, json.JSONDecodeError, SchemaError, ValidationError) as error:
        raise FractureEnergyConcreteBenchmarkError(
            "fracture_energy_schema_invalid"
        ) from error

    without_hash = {
        key: value for key, value in payload.items() if key != "artifact_hash"
    }
    if payload["artifact_hash"] != canonical_hash(without_hash):
        raise FractureEnergyConcreteBenchmarkError(
            "fracture_energy_artifact_hash_mismatch"
        )
    checksums = payload["source"]["input_checksums"]
    expected_source_paths = {path.as_posix() for path in _SOURCE_PATHS}
    if set(checksums) != expected_source_paths:
        raise FractureEnergyConcreteBenchmarkError("fracture_energy_source_set_invalid")
    if payload["source"]["source_set_hash"] != canonical_hash(checksums):
        raise FractureEnergyConcreteBenchmarkError(
            "fracture_energy_source_set_hash_mismatch"
        )
    if payload["configuration"] != _configuration():
        raise FractureEnergyConcreteBenchmarkError(
            "fracture_energy_configuration_invalid"
        )

    maximum_traction_error = 0.0
    opening_energies: list[float] = []
    for mesh_count, case in zip(
        _MESH_COUNTS, payload["traction_opening_cases"], strict=True
    ):
        characteristic_length = _LENGTH_M / mesh_count
        if case["mesh_count"] != mesh_count or not _close(
            case["characteristic_length_m"], characteristic_length
        ):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_opening_case_identity_invalid"
            )
        material = _material(
            characteristic_length,
            tensile_strength_mpa=_TERMINAL_TENSILE_STRENGTH_MPA,
        )
        if case["material_contract_hash"] != canonical_hash(asdict(material)):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_material_contract_hash_invalid"
            )
        for crack_opening, row in zip(_CRACK_OPENINGS_M, case["rows"], strict=True):
            energy = _TENSILE_FRACTURE_ENERGY_N_PER_M / 1.0e6
            expected_traction = _TERMINAL_TENSILE_STRENGTH_MPA * math.exp(
                -_TERMINAL_TENSILE_STRENGTH_MPA * crack_opening / energy
            )
            expected_strain = (
                expected_traction / material.elastic_modulus_mpa
                + crack_opening / characteristic_length
            )
            if not (
                _close(row["crack_opening_m"], crack_opening)
                and _close(row["total_strain"], expected_strain)
                and _close(row["expected_traction_mpa"], expected_traction)
            ):
                raise FractureEnergyConcreteBenchmarkError(
                    "fracture_energy_opening_reference_invalid"
                )
            maximum_traction_error = max(
                maximum_traction_error,
                abs(float(row["traction_mpa"]) - expected_traction),
            )
        opening_energies.append(float(case["rows"][-1]["dissipated_energy_mj_per_m2"]))

    tangent_pass = True
    expected_tangent_strains = (0.002, -0.002) * len(_MESH_COUNTS)
    for expected_strain, tangent in zip(
        expected_tangent_strains, payload["tangent_checks"], strict=True
    ):
        expected_absolute_error = abs(
            float(tangent["finite_difference_tangent_mpa"])
            - float(tangent["analytic_consistent_tangent_mpa"])
        )
        expected_relative_error = expected_absolute_error / max(
            abs(float(tangent["finite_difference_tangent_mpa"])),
            abs(float(tangent["analytic_consistent_tangent_mpa"])),
            1.0,
        )
        expected_pass = bool(
            expected_relative_error <= float(tangent["relative_tolerance"])
            and tangent["same_committed_parent_state"] is True
        )
        if (
            tangent["damage_algorithm"] != FRACTURE_ENERGY_DAMAGE_ALGORITHM
            or tangent["tangent_definition"] != FRACTURE_ENERGY_TANGENT_DEFINITION
            or tangent["active_branch"]
            != ("tension" if expected_strain > 0.0 else "compression")
            or not _close(tangent["total_strain"], expected_strain)
            or not _close(tangent["finite_difference_epsilon"], 1.0e-8)
            or not _close(tangent["relative_tolerance"], 1.0e-7)
            or not _close(tangent["absolute_error_mpa"], expected_absolute_error)
            or not _close(tangent["relative_error"], expected_relative_error)
            or tangent["pass"] is not expected_pass
        ):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_tangent_check_invalid"
            )
        tangent_pass = tangent_pass and expected_pass

    mesh_cases = payload["mesh_cases"]
    concrete_area = _GROSS_AREA_M2 * (1.0 - _REINFORCEMENT_RATIO)
    expected_energy = _TENSILE_FRACTURE_ENERGY_N_PER_M * concrete_area
    for mesh_count, case in zip(_MESH_COUNTS, mesh_cases, strict=True):
        expected_checks = {
            "path_contract_pass": case["status"] == "ready",
            "all_steps_committed": case["step_count"] == _LOAD_STEP_COUNT,
            "equilibrium_pass": (case["maximum_equilibrium_force_spread_kn"] <= 1.0e-8),
            "single_seeded_localization": (
                case["localized_element_indices"] == [mesh_count - 1]
            ),
            "deterministic_state_replay": (
                case["accepted_state_path_hash"]
                == case["replay_accepted_state_path_hash"]
            ),
            "zero_fallback": case["fallback_count"] == 0,
            "zero_regularization": case["regularization_count"] == 0,
            "terminal_displacement_exact": (
                case["terminal_displacement_m"] == _TERMINAL_DISPLACEMENT_M
            ),
            "fracture_energy_saturation_pass": (
                abs(float(case["concrete_dissipated_energy_j"]) - expected_energy)
                / expected_energy
                <= 5.0e-4
            ),
        }
        histories = (
            case["concrete_force_history_kn"],
            case["reinforcement_force_history_kn"],
            case["total_rc_force_history_kn"],
        )
        if any(len(history) != _LOAD_STEP_COUNT for history in histories):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_force_history_length_invalid"
            )
        if any(
            not _close(total, concrete + steel)
            for concrete, steel, total in zip(*histories, strict=True)
        ):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_total_force_history_invalid"
            )
        relative_energy_error = (
            abs(float(case["concrete_dissipated_energy_j"]) - expected_energy)
            / expected_energy
        )
        if not (
            case["mesh_count"] == mesh_count
            and case["problem_case_id"]
            == f"fracture_energy_rc_tie_mesh_{mesh_count}"
            and len(case["final_tensile_damage"]) == mesh_count
            and _close(case["element_length_m"], _LENGTH_M / mesh_count)
            and _close(case["expected_tensile_fracture_energy_j"], expected_energy)
            and _close(case["fracture_energy_relative_error"], relative_energy_error)
            and case["checks"] == expected_checks
            and case["contract_pass"] is all(expected_checks.values())
        ):
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_mesh_case_semantics_invalid"
            )

    force_parity = [
        _scaled_linf(
            mesh_cases[0]["total_rc_force_history_kn"],
            case["total_rc_force_history_kn"],
        )
        for case in mesh_cases[1:]
    ]
    energy_values = [float(case["concrete_dissipated_energy_j"]) for case in mesh_cases]
    energy_spread = (max(energy_values) - min(energy_values)) / max(
        max(energy_values), 1.0e-30
    )
    opening_energy_spread = max(opening_energies) - min(opening_energies)
    fallback_count = sum(case["fallback_count"] for case in mesh_cases)
    regularization_count = sum(case["regularization_count"] for case in mesh_cases)
    metrics = payload["metrics"]
    if not (
        _close(
            metrics["maximum_traction_absolute_error_mpa"],
            maximum_traction_error,
        )
        and _close(
            metrics["maximum_rc_force_history_scaled_linf"],
            max(force_parity, default=0.0),
        )
        and _close(metrics["concrete_fracture_energy_spread_relative"], energy_spread)
        and _close(metrics["opening_energy_spread_mj_per_m2"], opening_energy_spread)
        and metrics["fallback_count"] == fallback_count
        and metrics["regularization_count"] == regularization_count
    ):
        raise FractureEnergyConcreteBenchmarkError("fracture_energy_metrics_invalid")
    expected_checks = {
        "implicit_tangent_finite_difference_pass": tangent_pass,
        "traction_opening_length_invariant": maximum_traction_error <= 1.0e-12,
        "opening_energy_length_invariant": opening_energy_spread <= 1.0e-15,
        "all_mesh_cases_pass": all(case["contract_pass"] for case in mesh_cases),
        "rc_force_history_mesh_objective": (max(force_parity, default=0.0) <= 1.0e-8),
        "fracture_energy_mesh_objective": energy_spread <= 1.0e-12,
        "zero_fallback_and_regularization": bool(
            fallback_count == 0 and regularization_count == 0
        ),
    }
    contract_pass = all(expected_checks.values())
    claims = payload["claims"]
    if not (
        payload["checks"] == expected_checks
        and payload["contract_pass"] is contract_pass
        and payload["status"] == ("candidate_verified" if contract_pass else "blocked")
        and claims["uniaxial_fracture_energy_regularization"] is contract_pass
        and claims["bounded_seeded_rc_tie_mesh_objectivity"] is contract_pass
        and payload["blockers_remaining"]
        == list(FRACTURE_ENERGY_CONCRETE_BLOCKERS_REMAINING)
        and payload["claim_boundary"]
        == FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY
    ):
        raise FractureEnergyConcreteBenchmarkError(
            "fracture_energy_claim_semantics_invalid"
        )


def validate_fracture_energy_concrete_mesh_objectivity_benchmark(
    payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
    require_current_sources: bool = True,
    rerun: bool = True,
) -> dict[str, Any]:
    """Validate schema, hashes, semantics, current sources, and reproduction."""

    root = _repo_root(repo_root)
    _validate_schema_and_semantics(payload, repo_root=root)
    if require_current_sources and payload["source"]["input_checksums"] != (
        _source_checksums(root)
    ):
        raise FractureEnergyConcreteBenchmarkError("fracture_energy_sources_stale")
    if rerun:
        expected = build_fracture_energy_concrete_mesh_objectivity_benchmark(
            repo_root=root
        )
        if payload != expected:
            raise FractureEnergyConcreteBenchmarkError(
                "fracture_energy_current_reproduction_mismatch"
            )
    return payload


__all__ = [
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_CLAIM_BOUNDARY",
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_PROFILE",
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_PATH",
    "FRACTURE_ENERGY_CONCRETE_BENCHMARK_SCHEMA_VERSION",
    "FRACTURE_ENERGY_CONCRETE_BLOCKERS_REMAINING",
    "FRACTURE_ENERGY_CONCRETE_NUMERIC_SERIALIZATION",
    "FRACTURE_ENERGY_CONCRETE_TRUTH_CLASS",
    "FractureEnergyConcreteBenchmarkError",
    "build_fracture_energy_concrete_mesh_objectivity_benchmark",
    "validate_fracture_energy_concrete_mesh_objectivity_benchmark",
]
