#!/usr/bin/env python3
"""Build narrow state-updated concrete damage Newton evidence artifacts."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.assembly.stateful_axial import (  # noqa: E402
    assemble_stateful_axial_chain,
    finite_difference_stateful_axial_jacobian_check,
    initial_stateful_axial_state,
    run_stateful_axial_load_path,
    single_element_concrete_damage_bar_problem,
    solve_stateful_axial_load_step,
    two_element_concrete_damage_chain_problem,
)
from structural_analysis.materials.concrete_damage import (  # noqa: E402
    DAMAGE_ALGORITHM,
    TANGENT_DEFINITION,
    AsymmetricConcreteDamageMaterial,
    finite_difference_concrete_damage_tangent_check,
    integrate_concrete_damage_history,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_state_updated_concrete_damage_result.json"
DEFAULT_SUMMARY_OUT = (
    PRODUCTIZATION / "phase2_state_updated_concrete_damage_summary.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/state_updated_concrete_damage_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = "phase2-state-updated-concrete-damage-artifacts.v1"
CYCLIC_STRAINS = (
    0.0,
    -0.0005,
    -0.002,
    0.0,
    0.0002,
    0.0,
    -0.003,
    0.0,
    0.0004,
    0.0,
)
STRUCTURE_LOAD_FACTORS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
LOCALIZATION_TIE_BREAK_PROFILE = (
    "first_element_area_imperfection_selects_second_branch.v1"
)
LOCALIZATION_AREA_IMPERFECTION_RATIO = 1.0e-6
LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE = 1.0e-4
LOCALIZATION_PERTURBED_ELEMENT_ID = "bar-1"
LOCALIZATION_SELECTED_ELEMENT_ID = "bar-2"
CLAIM_BOUNDARY = (
    "This receipt verifies one small-strain uniaxial asymmetric concrete damage "
    "seed at material-point, one-element, and two-element displacement-controlled "
    "axial-chain scope. The two-element counter-example uses a versioned "
    "first-element area imperfection solely to select one of two symmetric "
    "localization branches deterministically. It records irreversible "
    "tension/compression damage, "
    "nonnegative damage dissipation, same-parent consistent tangents, commit, and "
    "exact rollback. The two-element post-peak path localizes and is explicit "
    "counter-evidence for mesh objectivity. It does not close crack-band/fracture-"
    "energy regularization, multiaxial concrete, frame-shell integration points, "
    "published/experimental validation, general material breadth, G1, or HIP parity."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _json_differences(
    existing: Any,
    expected: Any,
    path: str = "$",
) -> list[dict[str, Any]]:
    existing_is_number = isinstance(
        existing,
        (int, float, np.integer, np.floating),
    ) and not isinstance(existing, (bool, np.bool_))
    expected_is_number = isinstance(
        expected,
        (int, float, np.integer, np.floating),
    ) and not isinstance(expected, (bool, np.bool_))
    if existing_is_number and expected_is_number:
        existing_number = float(existing)
        expected_number = float(expected)
        signed_zero = bool(
            existing_number == expected_number == 0.0
            and bool(np.signbit(existing_number)) != bool(np.signbit(expected_number))
        )
        if existing_number != expected_number or signed_zero:
            return [
                {
                    "path": path,
                    "existing": existing_number,
                    "expected": expected_number,
                    "kind": "signed_zero" if signed_zero else "value",
                    "absolute_difference": abs(existing_number - expected_number),
                }
            ]
        return []
    if type(existing) is not type(expected):
        return [
            {
                "path": path,
                "existing": existing,
                "expected": expected,
                "kind": "type",
            }
        ]
    if isinstance(existing, dict):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(existing) | set(expected)):
            child = f"{path}.{key}"
            if key not in existing:
                rows.append(
                    {
                        "path": child,
                        "existing": "<missing>",
                        "expected": expected[key],
                        "kind": "missing_existing",
                    }
                )
            elif key not in expected:
                rows.append(
                    {
                        "path": child,
                        "existing": existing[key],
                        "expected": "<missing>",
                        "kind": "missing_expected",
                    }
                )
            else:
                rows.extend(_json_differences(existing[key], expected[key], child))
        return rows
    if isinstance(existing, list):
        rows = []
        if len(existing) != len(expected):
            rows.append(
                {
                    "path": f"{path}.length",
                    "existing": len(existing),
                    "expected": len(expected),
                    "kind": "length",
                }
            )
        for index, (left, right) in enumerate(zip(existing, expected, strict=False)):
            rows.extend(_json_differences(left, right, f"{path}[{index}]"))
        return rows
    if existing != expected:
        return [
            {
                "path": path,
                "existing": existing,
                "expected": expected,
                "kind": "value",
            }
        ]
    return []


def _difference_diagnostic(existing: Any, expected: Any) -> dict[str, Any]:
    rows = _json_differences(_strip_volatile(existing), _strip_volatile(expected))
    absolute = [
        float(row["absolute_difference"])
        for row in rows
        if "absolute_difference" in row
    ]
    return {
        "difference_count": len(rows),
        "first_difference": rows[0] if rows else None,
        "maximum_float_absolute_difference": max(absolute, default=0.0),
        "signed_zero_difference_count": sum(
            row["kind"] == "signed_zero" for row in rows
        ),
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _newton_config(*, max_iterations: int = 30) -> NewtonRaphsonConfig:
    return NewtonRaphsonConfig(
        residual_tolerance=1.0e-9,
        increment_tolerance=1.0e-12,
        max_iterations=max_iterations,
    )


def build_phase2_state_updated_concrete_damage_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    material = AsymmetricConcreteDamageMaterial()
    initial_material_state = material.initial_state()
    tension_response = material.integrate(0.0003, initial_material_state)
    compression_response = material.integrate(-0.002, initial_material_state)
    tension_tangent = finite_difference_concrete_damage_tangent_check(
        material,
        initial_material_state,
        total_strain=0.0003,
    )
    compression_tangent = finite_difference_concrete_damage_tangent_check(
        material,
        initial_material_state,
        total_strain=-0.002,
    )
    cyclic = integrate_concrete_damage_history(material, CYCLIC_STRAINS)
    point_contract_pass = bool(
        tension_response.damage_evolved
        and compression_response.damage_evolved
        and tension_tangent["pass"] is True
        and compression_tangent["pass"] is True
        and cyclic["energy_damage_gate_passed"] is True
        and cyclic["damage_irreversible"] is True
    )

    element_problem = single_element_concrete_damage_bar_problem(material=material)
    element_initial = initial_stateful_axial_state(element_problem)
    element_assembly = assemble_stateful_axial_chain(
        element_problem,
        element_initial,
        target_load_factor=1.0,
        trial_free_displacements_m=np.asarray([], dtype=float),
    )
    expected_stress_mpa = -material.compressive_strength_mpa * math.exp(
        -material.compressive_softening_rate
        * (0.002 - material.compressive_threshold_strain)
    )
    expected_force_kn = expected_stress_mpa * 0.01 * 1000.0
    element_force_error_kn = abs(
        element_assembly.element_responses[0]["internal_force_kn"] - expected_force_kn
    )
    element_contract_pass = bool(
        element_assembly.element_responses[0]["material_response"]["damage_evolved"]
        and element_force_error_kn <= 1.0e-10
        and element_assembly.residual_kn.size == 0
        and abs(sum(element_assembly.reactions_kn)) <= 1.0e-10
    )

    symmetric_structure_problem = two_element_concrete_damage_chain_problem(
        material=material
    )
    perturbed_element = replace(
        symmetric_structure_problem.elements[0],
        area_m2=(
            symmetric_structure_problem.elements[0].area_m2
            * (1.0 - LOCALIZATION_AREA_IMPERFECTION_RATIO)
        ),
    )
    structure_problem = replace(
        symmetric_structure_problem,
        case_id=(
            "phase2_state_updated_concrete_damage_two_element_chain_imperfection_v1"
        ),
        elements=(perturbed_element, symmetric_structure_problem.elements[1]),
    )
    structure_path = run_stateful_axial_load_path(
        structure_problem,
        STRUCTURE_LOAD_FACTORS,
        config=_newton_config(),
    )
    structure_replay = run_stateful_axial_load_path(
        structure_problem,
        STRUCTURE_LOAD_FACTORS,
        config=_newton_config(),
    )
    jacobian_parent = structure_path.steps[4].accepted_state
    jacobian_trial = structure_path.steps[5].trial_solution.free_displacements_m
    structure_jacobian = finite_difference_stateful_axial_jacobian_check(
        structure_problem,
        jacobian_parent,
        target_load_factor=0.6,
        trial_free_displacements_m=jacobian_trial,
        epsilon=1.0e-9,
        relative_tolerance=1.0e-6,
    )
    force_spreads = [
        max(row["internal_force_kn"] for row in step.trial_assembly.element_responses)
        - min(row["internal_force_kn"] for row in step.trial_assembly.element_responses)
        for step in structure_path.steps
    ]
    residual_norms = [
        float(np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf))
        for step in structure_path.steps
    ]
    final_strains = [
        row["total_strain"]
        for row in structure_path.steps[-1].trial_assembly.element_responses
    ]
    final_damage = [
        state.compressive_damage for state in structure_path.final_state.material_states
    ]
    selected_localization_index = int(np.argmax(np.asarray(final_damage, dtype=float)))
    selected_localization_element_id = structure_problem.elements[
        selected_localization_index
    ].element_id
    deterministic_branch_selected = bool(
        perturbed_element.element_id == LOCALIZATION_PERTURBED_ELEMENT_ID
        and selected_localization_element_id == LOCALIZATION_SELECTED_ELEMENT_ID
        and final_damage[1] > final_damage[0]
    )
    localization_observed = bool(
        abs(final_strains[0] - final_strains[1]) > 0.003
        and max(final_damage) > 0.9
        and min(final_damage) <= LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE
    )
    deterministic_replay = bool(
        structure_replay.final_state.state_hash == structure_path.final_state.state_hash
        and structure_replay.to_dict() == structure_path.to_dict()
    )
    structure_contract_pass = bool(
        structure_path.status == "ready"
        and structure_path.contract_pass
        and all(step.committed for step in structure_path.steps)
        and max(force_spreads) <= 1.0e-8
        and max(residual_norms) <= 1.0e-8
        and structure_jacobian["pass"] is True
        and deterministic_replay
        and localization_observed
        and deterministic_branch_selected
    )

    rollback_parent = initial_stateful_axial_state(structure_problem)
    rollback_step = solve_stateful_axial_load_step(
        structure_problem,
        rollback_parent,
        target_load_factor=0.75,
        config=_newton_config(max_iterations=0),
    )
    rollback_exact = bool(
        rollback_step.committed is False
        and rollback_step.metrics["rollback_exact"] is True
        and rollback_step.accepted_state.state_hash == rollback_parent.state_hash
        and rollback_step.accepted_state.canonical_bytes()
        == rollback_parent.canonical_bytes()
    )
    line_search_history_present = bool(
        all(step.trial_solution.line_search_history for step in structure_path.steps)
    )
    fallback_count = sum(
        bool(step.metrics["fallback_used"]) for step in structure_path.steps
    )
    regularization_count = sum(
        bool(step.metrics["regularization_used"]) for step in structure_path.steps
    )
    contract_pass = bool(
        point_contract_pass
        and element_contract_pass
        and structure_contract_pass
        and rollback_exact
        and line_search_history_present
        and fallback_count == 0
        and regularization_count == 0
    )

    result_payload = {
        "schema_version": "phase2-state-updated-concrete-damage-result.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": "analytic_1d_damage_and_axial_chain_truth",
        "analysis_type": "state_updated_concrete_damage_newton_seed",
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "damage_algorithm": DAMAGE_ALGORITHM,
        "tangent_definition": TANGENT_DEFINITION,
        "material_point": {
            "contract_pass": point_contract_pass,
            "parameters": {
                "elastic_modulus_mpa": material.elastic_modulus_mpa,
                "tensile_strength_mpa": material.tensile_strength_mpa,
                "compressive_strength_mpa": material.compressive_strength_mpa,
                "tensile_softening_rate": material.tensile_softening_rate,
                "compressive_softening_rate": material.compressive_softening_rate,
            },
            "tension_response": tension_response.to_dict(),
            "compression_response": compression_response.to_dict(),
            "tension_finite_difference_tangent": tension_tangent,
            "compression_finite_difference_tangent": compression_tangent,
            "cyclic_path": cyclic,
        },
        "element_benchmark": {
            "contract_pass": element_contract_pass,
            "expected_force_kn": expected_force_kn,
            "force_abs_error_kn": element_force_error_kn,
            "assembly": element_assembly.to_dict(),
        },
        "structure_benchmark": {
            "contract_pass": structure_contract_pass,
            "load_factors": list(STRUCTURE_LOAD_FACTORS),
            "maximum_series_force_spread_kn": max(force_spreads),
            "maximum_residual_inf_norm_kn": max(residual_norms),
            "consistent_jacobian_finite_difference": structure_jacobian,
            "deterministic_replay_exact": deterministic_replay,
            "localization_observed": localization_observed,
            "localization_tie_break": {
                "profile": LOCALIZATION_TIE_BREAK_PROFILE,
                "area_imperfection_ratio": LOCALIZATION_AREA_IMPERFECTION_RATIO,
                "nondominant_damage_tolerance": (
                    LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE
                ),
                "perturbed_element_id": perturbed_element.element_id,
                "selected_localization_element_id": (selected_localization_element_id),
                "deterministic_branch_selected": deterministic_branch_selected,
            },
            "final_element_strains": final_strains,
            "final_element_compressive_damage": final_damage,
            "mesh_objectivity_claim": False,
            "path": structure_path.to_dict(),
        },
        "rollback_probe": {
            "exact": rollback_exact,
            "parent_state_hash": rollback_parent.state_hash,
            "accepted_state_hash_after": rollback_step.accepted_state.state_hash,
            "load_step": rollback_step.to_dict(),
        },
        "verification": {
            "material_point_contract_pass": point_contract_pass,
            "element_contract_pass": element_contract_pass,
            "structure_contract_pass": structure_contract_pass,
            "tension_tangent_gate_passed": tension_tangent["pass"],
            "compression_tangent_gate_passed": compression_tangent["pass"],
            "cyclic_energy_damage_gate_passed": cyclic["energy_damage_gate_passed"],
            "rollback_exact_gate_passed": rollback_exact,
            "line_search_history_present": line_search_history_present,
            "fallback_count": fallback_count,
            "regularization_count": regularization_count,
        },
        "state_updated_concrete_seed_contract_pass": contract_pass,
        "mesh_objectivity_claim": False,
        "material_newton_breadth_closure_claim": False,
        "g1_material_newton_breadth_claim": False,
        "production_nonlinear_closure_claim": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator(schema).validate(result_payload)

    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/materials/concrete_damage.py"),
                Path("src/structural_analysis/assembly/stateful_axial.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                SCHEMA_PATH,
                Path("scripts/build_phase2_state_updated_concrete_damage_artifacts.py"),
                Path("tests/test_state_updated_concrete_damage_newton.py"),
                Path(
                    "tests/test_build_phase2_state_updated_concrete_damage_artifacts.py"
                ),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": result_payload["truth_class"],
        "analysis_type": result_payload["analysis_type"],
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "damage_algorithm": DAMAGE_ALGORITHM,
        "tension_damage_tangent_gate_passed": tension_tangent["pass"],
        "compression_damage_tangent_gate_passed": compression_tangent["pass"],
        "cyclic_energy_damage_gate_passed": cyclic["energy_damage_gate_passed"],
        "damage_irreversibility_gate_passed": cyclic["damage_irreversible"],
        "element_benchmark_gate_passed": element_contract_pass,
        "structure_benchmark_gate_passed": structure_contract_pass,
        "structure_jacobian_gate_passed": structure_jacobian["pass"],
        "rollback_exact_gate_passed": rollback_exact,
        "deterministic_replay_exact_gate_passed": deterministic_replay,
        "localization_observed": localization_observed,
        "localization_tie_break_profile": LOCALIZATION_TIE_BREAK_PROFILE,
        "localization_area_imperfection_ratio": (LOCALIZATION_AREA_IMPERFECTION_RATIO),
        "localization_nondominant_damage_tolerance": (
            LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE
        ),
        "perturbed_localization_element_id": perturbed_element.element_id,
        "selected_localization_element_id": selected_localization_element_id,
        "mesh_objectivity_claim": False,
        "line_search_history_present": line_search_history_present,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "state_updated_concrete_seed_contract_pass": contract_pass,
        "material_newton_breadth_closure_claim": False,
        "g1_material_newton_breadth_claim": False,
        "production_nonlinear_closure_claim": False,
        "blockers_remaining": [
            "crack_band_fracture_energy_regularization_not_closed",
            "post_peak_mesh_objectivity_not_closed",
            "multiaxial_concrete_damage_plasticity_not_closed",
            "frame_shell_concrete_integration_point_coupling_not_closed",
            "composite_fiber_partial_interaction_breadth_not_closed",
            "nonlinear_link_device_family_breadth_not_closed",
            "published_or_experimental_concrete_cyclic_validation_not_attached",
            "g1_full_building_material_newton_breadth_not_closed",
            "production_sparse_rocm_hip_material_parity_not_closed",
        ],
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {"result": result_payload, "summary": summary_payload}


def check_phase2_state_updated_concrete_damage_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_state_updated_concrete_damage_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_state_updated_concrete_damage_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_state_updated_concrete_damage_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            diagnostic = _difference_diagnostic(existing, expected[key])
            diagnostic_text = json.dumps(
                diagnostic,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            return False, (
                f"phase2_state_updated_concrete_damage_mismatch:{key}:{diagnostic_text}"
            )
    return True, "phase2_state_updated_concrete_damage_consistent"


def write_phase2_state_updated_concrete_damage_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_state_updated_concrete_damage_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payloads[key]), encoding="utf-8")
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_phase2_state_updated_concrete_damage_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | localization={summary['localization_observed']} | "
        f"mesh_objectivity_claim={summary['mesh_objectivity_claim']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
