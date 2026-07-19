#!/usr/bin/env python3
"""Build narrow state-updated force-deformation bilinear-link artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
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
    single_element_bilinear_link_problem,
    solve_stateful_axial_load_step,
    two_element_bilinear_link_chain_problem,
)
from structural_analysis.materials.bilinear_link import (  # noqa: E402
    RETURN_MAPPING_ALGORITHM,
    TANGENT_DEFINITION,
    BilinearCombinedHardeningLink,
    finite_difference_link_tangent_check,
    integrate_link_deformation_history,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_state_updated_bilinear_link_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_state_updated_bilinear_link_summary.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/state_updated_bilinear_link_v1.schema.json"
)
SUMMARY_SCHEMA_VERSION = "phase2-state-updated-bilinear-link-artifacts.v1"
CYCLIC_DEFORMATIONS_M = (0.0, 0.005, 0.03, 0.0, -0.03, 0.0, 0.03, 0.0)
STRUCTURE_LOAD_FACTORS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
CLAIM_BOUNDARY = (
    "This receipt verifies one translational 1D bilinear force-deformation link "
    "with combined linear isotropic/kinematic hardening at material-point, one-"
    "element, and two-element scope. It records a native kN-m return mapping, "
    "cyclic dissipation, same-parent consistent tangent, commit, and exact rollback. "
    "It does not close gap/contact, friction, compression-only, uplift, viscous or "
    "viscoelastic devices, multi-DOF coupling, rate dependence, degradation/pinching, "
    "frame-shell connection integration, published validation, G1, or HIP parity."
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


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _config(*, max_iterations: int = 20) -> NewtonRaphsonConfig:
    return NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=max_iterations,
    )


def build_phase2_state_updated_bilinear_link_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    material = BilinearCombinedHardeningLink()
    initial_material_state = material.initial_state()
    point_response = material.integrate(0.03, initial_material_state)
    point_tangent = finite_difference_link_tangent_check(
        material,
        initial_material_state,
        deformation_m=0.03,
    )
    cyclic = integrate_link_deformation_history(
        material,
        CYCLIC_DEFORMATIONS_M,
    )
    point_contract_pass = bool(
        point_response.yielded
        and abs(point_response.final_yield_function_kn) <= 1.0e-10
        and point_tangent["pass"] is True
        and cyclic["energy_gate_passed"] is True
        and cyclic["plastic_flow_reversal_count"] >= 3
    )

    element_problem = single_element_bilinear_link_problem(material=material)
    element_initial = initial_stateful_axial_state(element_problem)
    element_assembly = assemble_stateful_axial_chain(
        element_problem,
        element_initial,
        target_load_factor=1.0,
        trial_free_displacements_m=np.asarray([], dtype=float),
    )
    element_row = element_assembly.element_responses[0]
    element_force_error_kn = abs(
        element_row["internal_force_kn"] - point_response.force_kn
    )
    element_tangent_error = abs(
        element_row["tangent_kn_per_m"] - point_response.consistent_tangent_kn_per_m
    )
    element_contract_pass = bool(
        element_row["response_kind"] == "force_deformation"
        and element_row["total_strain"] is None
        and element_force_error_kn <= 1.0e-10
        and element_tangent_error <= 1.0e-10
        and element_assembly.residual_kn.size == 0
        and abs(sum(element_assembly.reactions_kn)) <= 1.0e-10
    )

    structure_problem = two_element_bilinear_link_chain_problem(material=material)
    structure_path = run_stateful_axial_load_path(
        structure_problem,
        STRUCTURE_LOAD_FACTORS,
        config=_config(),
    )
    structure_replay = run_stateful_axial_load_path(
        structure_problem,
        STRUCTURE_LOAD_FACTORS,
        config=_config(),
    )
    structure_jacobian = finite_difference_stateful_axial_jacobian_check(
        structure_problem,
        structure_path.steps[4].accepted_state,
        target_load_factor=0.6,
        trial_free_displacements_m=(
            structure_path.steps[5].trial_solution.free_displacements_m
        ),
    )
    force_spreads = [
        max(row["internal_force_kn"] for row in step.trial_assembly.element_responses)
        - min(row["internal_force_kn"] for row in step.trial_assembly.element_responses)
        for step in structure_path.steps
    ]
    deformation_spreads = [
        max(
            row["generalized_deformation"]
            for row in step.trial_assembly.element_responses
        )
        - min(
            row["generalized_deformation"]
            for row in step.trial_assembly.element_responses
        )
        for step in structure_path.steps
    ]
    residual_norms = [
        float(np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf))
        for step in structure_path.steps
    ]
    deterministic_replay = bool(
        structure_replay.final_state.state_hash == structure_path.final_state.state_hash
        and structure_replay.to_dict() == structure_path.to_dict()
    )
    structure_contract_pass = bool(
        structure_path.status == "ready"
        and structure_path.contract_pass
        and all(step.committed for step in structure_path.steps)
        and max(force_spreads) <= 1.0e-10
        and max(deformation_spreads) <= 1.0e-12
        and max(residual_norms) <= 1.0e-10
        and structure_jacobian["pass"] is True
        and deterministic_replay
        and all(
            state.accumulated_plastic_deformation_m > 0.0
            for state in structure_path.final_state.material_states
        )
    )

    rollback_parent = initial_stateful_axial_state(structure_problem)
    rollback_step = solve_stateful_axial_load_step(
        structure_problem,
        rollback_parent,
        target_load_factor=1.0,
        config=_config(max_iterations=0),
    )
    rollback_exact = bool(
        rollback_step.committed is False
        and rollback_step.metrics["rollback_exact"] is True
        and rollback_step.accepted_state.state_hash == rollback_parent.state_hash
        and rollback_step.accepted_state.canonical_bytes()
        == rollback_parent.canonical_bytes()
    )
    line_search_history_present = all(
        bool(step.trial_solution.line_search_history) for step in structure_path.steps
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
        "schema_version": "phase2-state-updated-bilinear-link-result.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": "analytic_1d_force_deformation_link_truth",
        "analysis_type": "state_updated_bilinear_link_newton_seed",
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "return_mapping_algorithm": RETURN_MAPPING_ALGORITHM,
        "tangent_definition": TANGENT_DEFINITION,
        "material_point": {
            "contract_pass": point_contract_pass,
            "parameters": {
                "initial_stiffness_kn_per_m": material.initial_stiffness_kn_per_m,
                "yield_force_kn": material.yield_force_kn,
                "isotropic_hardening_kn_per_m": (material.isotropic_hardening_kn_per_m),
                "kinematic_hardening_kn_per_m": (material.kinematic_hardening_kn_per_m),
            },
            "monotonic_response": point_response.to_dict(),
            "finite_difference_tangent": point_tangent,
            "cyclic_path": cyclic,
        },
        "element_benchmark": {
            "contract_pass": element_contract_pass,
            "force_abs_error_kn": element_force_error_kn,
            "tangent_abs_error_kn_per_m": element_tangent_error,
            "assembly": element_assembly.to_dict(),
        },
        "structure_benchmark": {
            "contract_pass": structure_contract_pass,
            "load_factors": list(STRUCTURE_LOAD_FACTORS),
            "maximum_series_force_spread_kn": max(force_spreads),
            "maximum_link_deformation_spread_m": max(deformation_spreads),
            "maximum_residual_inf_norm_kn": max(residual_norms),
            "consistent_jacobian_finite_difference": structure_jacobian,
            "deterministic_replay_exact": deterministic_replay,
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
            "cyclic_energy_gate_passed": cyclic["energy_gate_passed"],
            "rollback_exact_gate_passed": rollback_exact,
            "line_search_history_present": line_search_history_present,
            "fallback_count": fallback_count,
            "regularization_count": regularization_count,
        },
        "state_updated_bilinear_link_seed_contract_pass": contract_pass,
        "link_spring_material_breadth_closure_claim": False,
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
                Path("src/structural_analysis/materials/bilinear_link.py"),
                Path("src/structural_analysis/assembly/stateful_axial.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                SCHEMA_PATH,
                Path("scripts/build_phase2_state_updated_bilinear_link_artifacts.py"),
                Path("tests/test_state_updated_bilinear_link_newton.py"),
                Path(
                    "tests/test_build_phase2_state_updated_bilinear_link_artifacts.py"
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
        "return_mapping_algorithm": RETURN_MAPPING_ALGORITHM,
        "material_point_tangent_gate_passed": point_tangent["pass"],
        "cyclic_energy_gate_passed": cyclic["energy_gate_passed"],
        "element_benchmark_gate_passed": element_contract_pass,
        "structure_benchmark_gate_passed": structure_contract_pass,
        "structure_jacobian_gate_passed": structure_jacobian["pass"],
        "rollback_exact_gate_passed": rollback_exact,
        "deterministic_replay_exact_gate_passed": deterministic_replay,
        "line_search_history_present": line_search_history_present,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "state_updated_bilinear_link_seed_contract_pass": contract_pass,
        "link_spring_material_breadth_closure_claim": False,
        "material_newton_breadth_closure_claim": False,
        "g1_material_newton_breadth_claim": False,
        "production_nonlinear_closure_claim": False,
        "blockers_remaining": [
            "gap_contact_link_family_not_closed",
            "friction_link_family_not_closed",
            "compression_only_uplift_link_family_not_closed",
            "viscous_viscoelastic_device_family_not_closed",
            "multi_dof_coupled_link_not_closed",
            "rate_dependence_degradation_pinching_not_closed",
            "frame_shell_connection_link_integration_not_closed",
            "published_or_experimental_link_validation_not_attached",
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


def check_phase2_state_updated_bilinear_link_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_phase2_state_updated_bilinear_link_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        if not path.is_file():
            return False, f"phase2_state_updated_bilinear_link_missing:{relative}"
        try:
            existing = _read_json(path)
        except Exception as exc:
            return False, (
                f"phase2_state_updated_bilinear_link_unreadable:{relative}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_state_updated_bilinear_link_mismatch:{key}"
    return True, "phase2_state_updated_bilinear_link_consistent"


def write_phase2_state_updated_bilinear_link_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_state_updated_bilinear_link_artifacts(
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
        ok, message = check_phase2_state_updated_bilinear_link_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_state_updated_bilinear_link_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | "
        f"energy={summary['cyclic_energy_gate_passed']} | "
        f"rollback={summary['rollback_exact_gate_passed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
