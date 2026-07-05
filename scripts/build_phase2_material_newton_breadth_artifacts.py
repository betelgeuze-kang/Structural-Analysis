#!/usr/bin/env python3
"""Build Phase 2 material-Newton breadth seed artifacts for scalar constitutive laws."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.assembly.g1_contract import (  # noqa: E402
    assemble_g1_state,
    direct_residual_newton_parity_check,
    finite_difference_g1_jvp_check,
)
from structural_analysis.assembly.material_state import (  # noqa: E402
    assemble_state_updated_frame_shell_coupled_material_state,
    assemble_state_updated_material_newton_state,
    check_state_updated_material_checkpoint_replay,
    check_state_updated_material_path_history_replay,
    default_state_updated_frame_shell_coupled_material_problem,
    default_state_updated_bilinear_material_breadth_problems,
    material_path_history_checkpoint_payload,
    material_state_checkpoint_payload,
    solve_default_state_updated_material_path_histories,
    solve_state_updated_frame_shell_coupled_material_newton,
    solve_state_updated_material_newton,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    NewtonRaphsonConfig,
    ScalarAxialEquilibriumProblem,
    ScalarBilinearHardeningAxialReference,
    ScalarNonlinearAxialReference,
    expected_scalar_equilibrium_displacement,
    finite_difference_tangent_check,
    newton_raphson_scalar,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_LAWS_OUT = PRODUCTIZATION / "phase2_material_newton_breadth_scalar_axial_laws.json"
DEFAULT_STATE_UPDATED_SEEDS_OUT = (
    PRODUCTIZATION / "phase2_material_newton_breadth_state_updated_seeds.json"
)
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_material_newton_breadth_summary.json"
SCHEMA_VERSION = "phase2-material-newton-breadth-artifacts.v1"
DISPLACEMENT_TOLERANCE_M = 1.0e-10
MATERIAL_JVP_RELATIVE_ERROR_TOLERANCE = 1.0e-6


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _problem_payload(problem: ScalarAxialEquilibriumProblem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": problem.case_id,
        "truth_class": "analytic_truth",
        "model_kind": problem.model_kind,
        "units": {"length": "m", "force": "kN"},
        "external_force_kn": problem.external_force_kn,
        "initial_displacement_m": problem.initial_displacement_m,
        "residual_contract": RESIDUAL_FORMULA,
        "claim_boundary": (
            "Deterministic scalar axial constitutive reference only. "
            "Not a full mesh, frame, shell, or production nonlinear solver."
        ),
    }
    if isinstance(problem, ScalarNonlinearAxialReference):
        payload.update(
            {
                "linear_stiffness_kn_per_m": problem.linear_stiffness_kn_per_m,
                "cubic_stiffness_kn_per_m3": problem.cubic_stiffness_kn_per_m3,
            }
        )
    elif isinstance(problem, ScalarBilinearHardeningAxialReference):
        payload.update(
            {
                "elastic_stiffness_kn_per_m": problem.elastic_stiffness_kn_per_m,
                "post_yield_stiffness_kn_per_m": problem.post_yield_stiffness_kn_per_m,
                "yield_force_kn": problem.yield_force_kn,
            }
        )
    return payload


def _solution_payload(solution: Any) -> dict[str, Any]:
    metrics = solution.metrics
    return {
        "schema_version": "phase2-material-newton-breadth-scalar-law-result.v1",
        "status": solution.status,
        "contract_pass": bool(metrics.get("contract_pass")),
        "case_id": solution.problem.case_id,
        "truth_class": "analytic_truth",
        "model_kind": solution.problem.model_kind,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "tangent_definition": metrics.get("tangent_definition"),
        "globalization": GLOBALIZATION,
        "matrix_backend": metrics.get("matrix_backend"),
        "sparse_backend_used": metrics.get("sparse_backend_used"),
        "metrics": metrics,
        "convergence_history": solution.convergence_history,
        "line_search_history": solution.line_search_history,
        "unsupported_features": solution.unsupported_features,
        "warnings": solution.warnings,
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "claim_boundary": (
            "This records one scalar material law solved with explicit "
            "R=F_internal-F_external, consistent tangent, backtracking line search, "
            "and separate residual/increment gates. It does not close general material "
            "Newton breadth on meshes, frame/shell/material coupling, sparse production "
            "backends, full-mesh/full-load G1, or GPU/HIP parity."
        ),
    }


def _evaluate_material_law(
    problem: ScalarAxialEquilibriumProblem,
    *,
    config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    solution = newton_raphson_scalar(problem, config=config)
    expected_displacement_m = expected_scalar_equilibrium_displacement(problem)
    displacement_error = abs(solution.displacement_m - expected_displacement_m)
    tangent_check = finite_difference_tangent_check(problem, solution.displacement_m)
    equilibrium_residual = problem.residual(solution.displacement_m)
    metrics = solution.metrics

    residual_gate_passed = bool(metrics.get("residual_gate_passed"))
    increment_gate_passed = bool(metrics.get("increment_gate_passed"))
    no_regularization_or_fallback = (
        metrics.get("regularization_used") is False and metrics.get("fallback_used") is False
    )
    tangent_gate_passed = bool(tangent_check["pass"])
    displacement_gate_passed = displacement_error <= DISPLACEMENT_TOLERANCE_M
    law_contract_pass = (
        solution.status == "ready"
        and bool(metrics.get("contract_pass"))
        and residual_gate_passed
        and increment_gate_passed
        and no_regularization_or_fallback
        and tangent_gate_passed
        and displacement_gate_passed
        and metrics.get("residual_formula") == RESIDUAL_FORMULA
    )

    result_payload = _solution_payload(solution)
    result_payload["problem"] = _problem_payload(problem)
    result_payload["verification"] = {
        "expected_displacement_m": expected_displacement_m,
        "displacement_abs_error_m": displacement_error,
        "displacement_gate_passed": displacement_gate_passed,
        "equilibrium_residual_kn": equilibrium_residual,
        "tangent_finite_difference_check": tangent_check,
        "tangent_gate_passed": tangent_gate_passed,
    }
    return {
        "case_id": problem.case_id,
        "model_kind": problem.model_kind,
        "law_contract_pass": law_contract_pass,
        "residual_gate_passed": residual_gate_passed,
        "increment_gate_passed": increment_gate_passed,
        "tangent_gate_passed": tangent_gate_passed,
        "displacement_gate_passed": displacement_gate_passed,
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "result": result_payload,
    }


def _state_updated_material_seed_row(
    problem: Any,
    *,
    config: NewtonRaphsonConfig,
    solution: Any | None = None,
    state: Any | None = None,
) -> dict[str, Any]:
    if solution is None or state is None:
        solution, state = solve_state_updated_material_newton(problem, config=config)
    assembly_result = assemble_g1_state(problem, state)
    checkpoint = material_state_checkpoint_payload(problem, state)
    checkpoint_replay = check_state_updated_material_checkpoint_replay(
        json.loads(json.dumps(checkpoint, ensure_ascii=False))
    )
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u, seed=problem: assemble_g1_state(
            seed,
            assemble_state_updated_material_newton_state(seed, free_u),
        ),
        solution.free_displacements_m,
    )
    newton_parity = direct_residual_newton_parity_check(
        lambda free_u, seed=problem: assemble_g1_state(
            seed,
            assemble_state_updated_material_newton_state(seed, free_u),
        ),
        solution,
    )
    material_state = dict(assembly_result.material_state_next)
    metrics = solution.metrics
    assembly_contract = assembly_result.contract_check()
    jvp_relative_error = float(jvp_check["relative_error"])
    case_contract_pass = (
        solution.status == "ready"
        and bool(metrics.get("contract_pass"))
        and bool(assembly_contract["contract_pass"])
        and bool(jvp_check["pass"])
        and bool(newton_parity["cpu_seed_consistent_newton_gate_passed"])
        and bool(checkpoint_replay["pass"])
        and metrics.get("regularization_used") is False
        and metrics.get("fallback_used") is False
        and material_state.get("state_updated_material_newton") is True
        and assembly_result.metrics.get("g1_closure_claim") is False
    )
    return {
        "case_id": problem.case_id,
        "assembly_scope": problem.assembly_scope,
        "case_contract_pass": case_contract_pass,
        "solution_status": solution.status,
        "solution_contract_pass": bool(metrics.get("contract_pass")),
        "structural_component": material_state.get("structural_component"),
        "material_case_kind": material_state.get("material_case_kind"),
        "material_family": material_state.get("material_family"),
        "section_integration": material_state.get("section_integration"),
        "strain_mode": material_state.get("strain_mode"),
        "return_mapping": material_state.get("return_mapping"),
        "state_updated_material_newton": (
            material_state.get("state_updated_material_newton") is True
        ),
        "path_dependent_state": material_state.get("path_dependent_state") is True,
        "path_dependent_state_updated": (
            material_state.get("path_dependent_state_updated") is True
        ),
        "residual_gate_passed": bool(metrics.get("residual_gate_passed")),
        "increment_gate_passed": bool(metrics.get("increment_gate_passed")),
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "assembly_contract_pass": bool(assembly_contract["contract_pass"]),
        "jvp_finite_difference_pass": bool(jvp_check["pass"]),
        "jvp_relative_error": jvp_relative_error,
        "direct_residual_newton_parity_pass": bool(
            newton_parity["cpu_seed_consistent_newton_gate_passed"]
        ),
        "direct_solver_residual_match": bool(
            newton_parity["direct_solver_residual_match"]
        ),
        "residual_descent_passed": bool(newton_parity["residual_descent_passed"]),
        "checkpoint_replay_pass": bool(checkpoint_replay["pass"]),
        "material_state_replay_match": bool(
            checkpoint_replay["material_state_replay_match"]
        ),
        "final_displacement_m": float(solution.free_displacements_m[0]),
        "material_state_next": material_state,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "promotes_g1_closure": False,
    }


def _sorted_unique(rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(row.get(key) or "") for row in rows})


def _state_updated_frame_shell_coupled_material_seed_payload(
    *,
    config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    problem = default_state_updated_frame_shell_coupled_material_problem()
    solution, final_state = solve_state_updated_frame_shell_coupled_material_newton(
        problem,
        config=config,
    )
    assembly_result = assemble_g1_state(problem, final_state)
    jvp_check = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_state_updated_frame_shell_coupled_material_state(
                problem,
                free_u,
            ),
        ),
        solution.free_displacements_m,
    )
    direct_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            problem,
            assemble_state_updated_frame_shell_coupled_material_state(
                problem,
                free_u,
            ),
        ),
        solution,
    )
    direct_parity_payload = {
        **direct_parity,
        "pass": bool(direct_parity["cpu_seed_consistent_newton_gate_passed"]),
    }
    material_state = dict(assembly_result.material_state_next)
    frame_material = dict(
        material_state.get("component_material_states", {}).get("frame") or {}
    )
    shell_material = dict(
        material_state.get("component_material_states", {}).get("shell") or {}
    )
    metrics = solution.metrics
    frame_shell_coupled_material_pass = (
        solution.status == "ready"
        and bool(metrics.get("contract_pass"))
        and bool(metrics.get("residual_gate_passed"))
        and bool(metrics.get("increment_gate_passed"))
        and metrics.get("regularization_used") is False
        and metrics.get("fallback_used") is False
        and bool(jvp_check["pass"])
        and bool(direct_parity_payload["pass"])
        and material_state.get("frame_material_state_updated") is True
        and material_state.get("shell_material_state_updated") is True
    )
    return {
        "schema_version": "phase2-state-updated-frame-shell-coupled-material-seed.v1",
        "status": "ready" if frame_shell_coupled_material_pass else "blocked",
        "contract_pass": frame_shell_coupled_material_pass,
        "case_id": problem.case_id,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "state_updated_material_newton": True,
        "frame_shell_state_updated_material_coupling_seed_pass": (
            frame_shell_coupled_material_pass
        ),
        "frame_material_state_updated": (
            material_state.get("frame_material_state_updated") is True
        ),
        "shell_material_state_updated": (
            material_state.get("shell_material_state_updated") is True
        ),
        "residual_gate_passed": bool(metrics.get("residual_gate_passed")),
        "increment_gate_passed": bool(metrics.get("increment_gate_passed")),
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "jvp_finite_difference_pass": bool(jvp_check["pass"]),
        "direct_residual_newton_parity_pass": bool(direct_parity_payload["pass"]),
        "free_dof_count": 2,
        "final_free_displacements_m": [
            float(value) for value in solution.free_displacements_m
        ],
        "final_residual_inf_kn": float(np.max(np.abs(assembly_result.residual_free))),
        "final_jacobian_kn_per_m": assembly_result.tangent_free.tolist(),
        "component_return_mappings": material_state["component_return_mappings"],
        "component_material_states": material_state["component_material_states"],
        "component_internal_forces_kn": material_state[
            "component_internal_forces_kn"
        ],
        "jvp_finite_difference_check": jvp_check,
        "direct_residual_newton_parity_check": direct_parity_payload,
        "convergence_history": solution.convergence_history,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "claim_boundary": (
            "Two-DOF frame/shell coupled seed where each component uses a "
            "state-updated material return mapping and the global residual/Jacobian "
            "includes a symmetric frame-shell coupling tangent. This is still a "
            "small deterministic seed and does not close full-mesh/full-load G1 "
            "material Newton breadth."
        ),
    }


def _build_state_updated_material_path_history_payload(
    *,
    config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    histories: list[dict[str, Any]] = []
    for history in solve_default_state_updated_material_path_histories(
        config=config,
    ):
        history_checkpoint = material_path_history_checkpoint_payload(history)
        history_checkpoint_roundtrip = json.loads(
            json.dumps(history_checkpoint, ensure_ascii=False)
        )
        history_checkpoint_replay = check_state_updated_material_path_history_replay(
            history_checkpoint_roundtrip
        )
        step_rows: list[dict[str, Any]] = []
        for step in history.steps:
            row = _state_updated_material_seed_row(
                step.problem,
                config=config,
                solution=step.solution,
                state=step.state,
            )
            step_rows.append(
                {
                    **row,
                    "history_step_index": step.history_step_index,
                    "external_force_kn": step.external_force_kn,
                    "carried_committed_state_previous": (
                        step.carried_committed_state_previous
                    ),
                    "previous_committed_state_matches_carried_state": (
                        step.previous_committed_state_matches_carried_state
                    ),
                }
            )

        history_passed = history.committed_state_chain_pass and all(
            row["checkpoint_replay_pass"]
            and row["jvp_finite_difference_pass"]
            and row["direct_residual_newton_parity_pass"]
            and row["regularization_used"] is False
            and row["fallback_used"] is False
            for row in step_rows
        ) and bool(history_checkpoint_replay["pass"])
        histories.append(
            {
                "history_id": history.history_id,
                "status": "ready" if history_passed else "blocked",
                "contract_pass": history_passed,
                "step_count": len(step_rows),
                "committed_state_chain_pass": history.committed_state_chain_pass,
                "path_dependent_update_step_count": (
                    history.path_dependent_update_step_count
                ),
                "checkpoint_replay_pass": all(
                    row["checkpoint_replay_pass"] for row in step_rows
                )
                and bool(history_checkpoint_replay["step_replay_pass"]),
                "chain_replay_pass": bool(
                    history_checkpoint_replay[
                        "committed_state_chain_replay_pass"
                    ]
                ),
                "path_history_checkpoint_replay_pass": bool(
                    history_checkpoint_replay["pass"]
                ),
                "path_history_checkpoint_replay_check": (
                    history_checkpoint_replay
                ),
                "jvp_finite_difference_pass": all(
                    row["jvp_finite_difference_pass"] for row in step_rows
                ),
                "direct_residual_newton_parity_pass": all(
                    row["direct_residual_newton_parity_pass"] for row in step_rows
                ),
                "steps": step_rows,
            }
        )

    history_contract_pass = all(history["contract_pass"] for history in histories)
    return {
        "schema_version": "phase2-material-newton-breadth-path-history-seeds.v1",
        "status": "ready" if history_contract_pass else "blocked",
        "contract_pass": history_contract_pass,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "history_count": len(histories),
        "step_count": sum(int(history["step_count"]) for history in histories),
        "path_dependent_update_step_count": sum(
            int(history["path_dependent_update_step_count"])
            for history in histories
        ),
        "checkpoint_replay_pass": all(
            history["checkpoint_replay_pass"] for history in histories
        ),
        "chain_replay_pass": all(
            history["chain_replay_pass"] for history in histories
        ),
        "path_history_checkpoint_replay_pass": all(
            history["path_history_checkpoint_replay_pass"] for history in histories
        ),
        "jvp_finite_difference_pass": all(
            history["jvp_finite_difference_pass"] for history in histories
        ),
        "direct_residual_newton_parity_pass": all(
            history["direct_residual_newton_parity_pass"] for history in histories
        ),
        "committed_state_chain_pass": all(
            history["committed_state_chain_pass"] for history in histories
        ),
        "histories": histories,
        "claim_boundary": (
            "Path-history material Newton seed suite that carries committed "
            "material state from one load step into the next across unload, "
            "reverse-yield, and reload steps. It strengthens path-dependent "
            "state replay evidence but remains a deterministic seed artifact, "
            "not a full-mesh/full-load G1 material Newton breadth closure."
        ),
    }


def _build_state_updated_material_seed_payload(
    *,
    config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    rows = [
        _state_updated_material_seed_row(problem, config=config)
        for problem in default_state_updated_bilinear_material_breadth_problems()
    ]
    material_families = _sorted_unique(rows, "material_family")
    section_integrations = _sorted_unique(rows, "section_integration")
    strain_modes = _sorted_unique(rows, "strain_mode")
    structural_components = _sorted_unique(rows, "structural_component")
    material_case_kinds = [str(row["material_case_kind"]) for row in rows]
    material_jvp_max_relative_error = max(
        (float(row["jvp_relative_error"]) for row in rows),
        default=0.0,
    )
    state_updated_seed_passed = all(row["case_contract_pass"] for row in rows)
    material_state_persistence_replay_passed = all(
        row["checkpoint_replay_pass"] for row in rows
    )
    path_history_payload = _build_state_updated_material_path_history_payload(
        config=config,
    )
    frame_shell_coupled_payload = (
        _state_updated_frame_shell_coupled_material_seed_payload(config=config)
    )
    coverage_ready = (
        state_updated_seed_passed
        and material_state_persistence_replay_passed
        and material_jvp_max_relative_error <= MATERIAL_JVP_RELATIVE_ERROR_TOLERANCE
        and path_history_payload["contract_pass"]
        and frame_shell_coupled_payload["contract_pass"]
        and {"reinforced_concrete", "steel", "src_composite"}.issubset(
            set(material_families)
        )
        and {"frame_fiber", "layered_shell", "composite_fiber"}.issubset(
            set(section_integrations)
        )
        and {"axial", "membrane", "bending", "drilling"}.issubset(
            set(strain_modes)
        )
    )
    return {
        "schema_version": "phase2-material-newton-breadth-state-updated-seeds.v1",
        "status": "ready" if coverage_ready else "blocked",
        "contract_pass": coverage_ready,
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "state_updated_material_newton_seed_passed": state_updated_seed_passed,
        "state_updated_material_newton_seed_case_count": len(rows),
        "state_updated_material_newton_seed_case_kinds": material_case_kinds,
        "state_updated_material_newton_seed_structural_components": (
            structural_components
        ),
        "state_updated_material_newton_seed_material_families": material_families,
        "state_updated_material_newton_seed_section_integrations": (
            section_integrations
        ),
        "state_updated_material_newton_seed_strain_modes": strain_modes,
        "path_dependent_material_update_seed_case_count": sum(
            1 for row in rows if row["path_dependent_state_updated"] is True
        ),
        "path_dependent_material_replay_seed_case_count": sum(
            1 for row in rows if row["path_dependent_state"] is True
        ),
        "material_state_persistence_replay_seed_passed": (
            material_state_persistence_replay_passed
        ),
        "state_updated_material_path_history_passed": (
            path_history_payload["contract_pass"]
        ),
        "state_updated_material_path_history_count": (
            path_history_payload["history_count"]
        ),
        "state_updated_material_path_history_step_count": (
            path_history_payload["step_count"]
        ),
        "state_updated_material_path_history_update_step_count": (
            path_history_payload["path_dependent_update_step_count"]
        ),
        "state_updated_material_path_history_checkpoint_replay_pass": (
            path_history_payload["checkpoint_replay_pass"]
        ),
        "state_updated_material_path_history_chain_replay_pass": (
            path_history_payload["chain_replay_pass"]
        ),
        "state_updated_material_path_history_whole_checkpoint_replay_pass": (
            path_history_payload["path_history_checkpoint_replay_pass"]
        ),
        "state_updated_material_path_history_jvp_pass": (
            path_history_payload["jvp_finite_difference_pass"]
        ),
        "state_updated_material_path_history_direct_parity_pass": (
            path_history_payload["direct_residual_newton_parity_pass"]
        ),
        "state_updated_material_path_history_committed_chain_pass": (
            path_history_payload["committed_state_chain_pass"]
        ),
        "state_updated_frame_shell_coupled_material_seed_pass": (
            frame_shell_coupled_payload["contract_pass"]
        ),
        "state_updated_frame_shell_coupled_material_jvp_pass": (
            frame_shell_coupled_payload["jvp_finite_difference_pass"]
        ),
        "state_updated_frame_shell_coupled_material_direct_parity_pass": (
            frame_shell_coupled_payload["direct_residual_newton_parity_pass"]
        ),
        "state_updated_frame_shell_coupled_material_residual_gate_passed": (
            frame_shell_coupled_payload["residual_gate_passed"]
        ),
        "state_updated_frame_shell_coupled_material_increment_gate_passed": (
            frame_shell_coupled_payload["increment_gate_passed"]
        ),
        "state_updated_frame_shell_coupled_material_component_updates_pass": (
            frame_shell_coupled_payload["frame_material_state_updated"]
            and frame_shell_coupled_payload["shell_material_state_updated"]
        ),
        "material_jvp_max_relative_error": material_jvp_max_relative_error,
        "material_jvp_relative_error_tolerance": (
            MATERIAL_JVP_RELATIVE_ERROR_TOLERANCE
        ),
        "material_jvp_relative_error_pass": (
            material_jvp_max_relative_error <= MATERIAL_JVP_RELATIVE_ERROR_TOLERANCE
        ),
        "frame_material_newton_seed_pass": all(
            row["case_contract_pass"]
            for row in rows
            if str(row["section_integration"]) in {"frame_fiber", "composite_fiber"}
        ),
        "shell_material_newton_seed_pass": all(
            row["case_contract_pass"]
            for row in rows
            if str(row["section_integration"]) == "layered_shell"
        ),
        "state_updated_material_newton_breadth_seed_coverage_ready": coverage_ready,
        "state_updated_material_newton_breadth_closed": False,
        "state_updated_seed_cases": rows,
        "state_updated_path_history_seeds": path_history_payload,
        "state_updated_frame_shell_coupled_material_seed": (
            frame_shell_coupled_payload
        ),
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "frame_shell_material_coupling_not_closed",
            "mesh_load_step_nonlinear_convergence_suite_not_closed",
            "sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
            "general_newton_jacobian_assembly_not_closed",
            "full_load_g1_material_newton_breadth_not_closed_by_seed_artifact",
        ],
        "claim_boundary": (
            "State-updated material Newton breadth seed suite across frame fiber, "
            "layered shell membrane/bending/drilling, steel, reinforced concrete, "
            "SRC/composite, yielded, elastic, unloading, reloading, and reverse "
            "compression return-mapping cases. Each seed uses the physical "
            "F_internal_minus_F_external residual, a consistent algorithmic tangent, "
            "finite-difference JVP, direct residual/Newton residual parity, and "
            "checkpoint replay. It also carries committed material state through "
            "small unload/reverse/reload path histories and a two-DOF frame/shell "
            "coupled state-updated material seed. This remains a deterministic seed "
            "artifact; it does not close full-mesh/full-load material Newton breadth, "
            "sparse production assembly, or ROCm/HIP parity."
        ),
    }


def build_material_newton_breadth_artifacts(
    *,
    repo_root: Path = ROOT,
    laws_out: Path = DEFAULT_LAWS_OUT,
    state_updated_seeds_out: Path = DEFAULT_STATE_UPDATED_SEEDS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    material_laws: tuple[ScalarAxialEquilibriumProblem, ...] = (
        ScalarNonlinearAxialReference(),
        ScalarBilinearHardeningAxialReference(),
    )
    law_results = [
        _evaluate_material_law(problem, config=config) for problem in material_laws
    ]
    state_updated_seed_payload = _build_state_updated_material_seed_payload(
        config=config,
    )
    contract_pass = (
        all(row["law_contract_pass"] for row in law_results)
        and state_updated_seed_payload["contract_pass"]
    )
    model_kinds = [row["model_kind"] for row in law_results]

    laws_payload = {
        "schema_version": "phase2-material-newton-breadth-scalar-laws.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": "analytic_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "material_law_count": len(law_results),
        "model_kinds": model_kinds,
        "solver_config": {
            "residual_tolerance": config.residual_tolerance,
            "increment_tolerance": config.increment_tolerance,
            "max_iterations": config.max_iterations,
        },
        "material_laws": law_results,
        "claim_boundary": (
            "Deterministic scalar material-Newton breadth seed across multiple "
            "constitutive laws using the same explicit F_internal_minus_F_external "
            "residual contract, consistent tangent, residual/increment gates, and "
            "backtracking line search without regularization or fallback false PASS. "
            "This does not close G1 full-mesh/full-load nonlinear equilibrium, general "
            "frame/shell/material coupling, sparse production matrix backends, or "
            "production GPU/HIP gates."
        ),
    }

    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("src/structural_analysis/solvers/nonlinear/__init__.py"),
                Path("src/structural_analysis/assembly/g1_contract.py"),
                Path("src/structural_analysis/assembly/material_state.py"),
                Path("scripts/build_phase2_material_newton_breadth_artifacts.py"),
                Path("scripts/verify_quality_gate.py"),
                Path("tests/test_build_phase2_material_newton_breadth_artifacts.py"),
                Path("tests/test_g1_assembly_contract.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "analysis_type": "nonlinear_static_scalar_material_breadth_seed",
        "truth_class": "analytic_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "matrix_backend": law_results[0]["result"]["matrix_backend"],
        "sparse_backend_used": law_results[0]["result"]["sparse_backend_used"],
        "material_law_count": len(law_results),
        "model_kinds": model_kinds,
        "state_updated_material_newton_seed_passed": (
            state_updated_seed_payload["state_updated_material_newton_seed_passed"]
        ),
        "state_updated_material_newton_seed_case_count": (
            state_updated_seed_payload["state_updated_material_newton_seed_case_count"]
        ),
        "state_updated_material_newton_seed_case_kinds": (
            state_updated_seed_payload["state_updated_material_newton_seed_case_kinds"]
        ),
        "state_updated_material_newton_seed_structural_components": (
            state_updated_seed_payload[
                "state_updated_material_newton_seed_structural_components"
            ]
        ),
        "state_updated_material_newton_seed_material_families": (
            state_updated_seed_payload[
                "state_updated_material_newton_seed_material_families"
            ]
        ),
        "state_updated_material_newton_seed_section_integrations": (
            state_updated_seed_payload[
                "state_updated_material_newton_seed_section_integrations"
            ]
        ),
        "state_updated_material_newton_seed_strain_modes": (
            state_updated_seed_payload[
                "state_updated_material_newton_seed_strain_modes"
            ]
        ),
        "path_dependent_material_update_seed_case_count": (
            state_updated_seed_payload["path_dependent_material_update_seed_case_count"]
        ),
        "path_dependent_material_replay_seed_case_count": (
            state_updated_seed_payload["path_dependent_material_replay_seed_case_count"]
        ),
        "material_state_persistence_replay_seed_passed": (
            state_updated_seed_payload["material_state_persistence_replay_seed_passed"]
        ),
        "state_updated_material_path_history_passed": (
            state_updated_seed_payload["state_updated_material_path_history_passed"]
        ),
        "state_updated_material_path_history_count": (
            state_updated_seed_payload["state_updated_material_path_history_count"]
        ),
        "state_updated_material_path_history_step_count": (
            state_updated_seed_payload[
                "state_updated_material_path_history_step_count"
            ]
        ),
        "state_updated_material_path_history_update_step_count": (
            state_updated_seed_payload[
                "state_updated_material_path_history_update_step_count"
            ]
        ),
        "state_updated_material_path_history_checkpoint_replay_pass": (
            state_updated_seed_payload[
                "state_updated_material_path_history_checkpoint_replay_pass"
            ]
        ),
        "state_updated_material_path_history_chain_replay_pass": (
            state_updated_seed_payload[
                "state_updated_material_path_history_chain_replay_pass"
            ]
        ),
        "state_updated_material_path_history_whole_checkpoint_replay_pass": (
            state_updated_seed_payload[
                "state_updated_material_path_history_whole_checkpoint_replay_pass"
            ]
        ),
        "state_updated_material_path_history_jvp_pass": (
            state_updated_seed_payload[
                "state_updated_material_path_history_jvp_pass"
            ]
        ),
        "state_updated_material_path_history_direct_parity_pass": (
            state_updated_seed_payload[
                "state_updated_material_path_history_direct_parity_pass"
            ]
        ),
        "state_updated_material_path_history_committed_chain_pass": (
            state_updated_seed_payload[
                "state_updated_material_path_history_committed_chain_pass"
            ]
        ),
        "state_updated_frame_shell_coupled_material_seed_pass": (
            state_updated_seed_payload[
                "state_updated_frame_shell_coupled_material_seed_pass"
            ]
        ),
        "state_updated_frame_shell_coupled_material_jvp_pass": (
            state_updated_seed_payload[
                "state_updated_frame_shell_coupled_material_jvp_pass"
            ]
        ),
        "state_updated_frame_shell_coupled_material_direct_parity_pass": (
            state_updated_seed_payload[
                "state_updated_frame_shell_coupled_material_direct_parity_pass"
            ]
        ),
        "state_updated_frame_shell_coupled_material_residual_gate_passed": (
            state_updated_seed_payload[
                "state_updated_frame_shell_coupled_material_residual_gate_passed"
            ]
        ),
        "state_updated_frame_shell_coupled_material_increment_gate_passed": (
            state_updated_seed_payload[
                "state_updated_frame_shell_coupled_material_increment_gate_passed"
            ]
        ),
        "state_updated_frame_shell_coupled_material_component_updates_pass": (
            state_updated_seed_payload[
                "state_updated_frame_shell_coupled_material_component_updates_pass"
            ]
        ),
        "material_jvp_max_relative_error": (
            state_updated_seed_payload["material_jvp_max_relative_error"]
        ),
        "material_jvp_relative_error_tolerance": (
            state_updated_seed_payload["material_jvp_relative_error_tolerance"]
        ),
        "material_jvp_relative_error_pass": (
            state_updated_seed_payload["material_jvp_relative_error_pass"]
        ),
        "frame_material_newton_seed_pass": (
            state_updated_seed_payload["frame_material_newton_seed_pass"]
        ),
        "shell_material_newton_seed_pass": (
            state_updated_seed_payload["shell_material_newton_seed_pass"]
        ),
        "state_updated_material_newton_breadth_seed_coverage_ready": (
            state_updated_seed_payload[
                "state_updated_material_newton_breadth_seed_coverage_ready"
            ]
        ),
        "state_updated_material_newton_breadth_closed": False,
        "law_summaries": [
            {
                "case_id": row["case_id"],
                "model_kind": row["model_kind"],
                "law_contract_pass": row["law_contract_pass"],
                "residual_gate_passed": row["residual_gate_passed"],
                "increment_gate_passed": row["increment_gate_passed"],
                "tangent_gate_passed": row["tangent_gate_passed"],
                "displacement_gate_passed": row["displacement_gate_passed"],
                "regularization_used": row["regularization_used"],
                "fallback_used": row["fallback_used"],
                "displacement_m": row["result"]["metrics"]["displacement_m"],
                "relative_residual": row["result"]["metrics"]["relative_residual"],
                "final_increment_abs_m": row["result"]["metrics"]["final_increment_abs_m"],
            }
            for row in law_results
        ],
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "frame_shell_material_coupling_not_closed",
            "mesh_load_step_nonlinear_convergence_suite_not_closed",
            "sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
            "general_newton_jacobian_assembly_not_closed",
            "full_load_g1_material_newton_breadth_not_closed_by_seed_artifact",
        ],
        "artifacts": {
            "scalar_axial_laws": str(laws_out),
            "state_updated_material_seeds": str(state_updated_seeds_out),
            "summary": str(summary_out),
            "related_scalar_newton_globalization_summary": str(
                PRODUCTIZATION / "phase2_newton_globalization_summary.json"
            ),
        },
        "claim_boundary": (
            "Deterministic material-Newton breadth seeds using the explicit "
            "F_internal_minus_F_external residual contract. This includes scalar "
            "analytic material laws plus a state-updated frame/shell/composite "
            "return-mapping seed suite with material-state checkpoint replay and "
            "finite-difference JVP checks, plus committed-state path histories for "
            "unload/reverse/reload sequences and a two-DOF frame/shell coupled "
            "state-updated material seed. It does not close G1 full-mesh/full-load "
            "nonlinear equilibrium, sparse production matrix backends, or production "
            "GPU/HIP gates."
        ),
    }
    return {
        "laws": laws_payload,
        "state_updated_seeds": state_updated_seed_payload,
        "summary": summary_payload,
    }


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def check_material_newton_breadth_artifacts(
    *,
    repo_root: Path = ROOT,
    laws_out: Path = DEFAULT_LAWS_OUT,
    state_updated_seeds_out: Path = DEFAULT_STATE_UPDATED_SEEDS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_material_newton_breadth_artifacts(
        repo_root=repo_root,
        laws_out=laws_out,
        state_updated_seeds_out=state_updated_seeds_out,
        summary_out=summary_out,
    )
    targets = {
        "laws": laws_out,
        "state_updated_seeds": state_updated_seeds_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_material_newton_breadth_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_material_newton_breadth_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_material_newton_breadth_mismatch:{key}"
    return True, "phase2_material_newton_breadth_consistent"


def write_material_newton_breadth_artifacts(
    *,
    repo_root: Path = ROOT,
    laws_out: Path = DEFAULT_LAWS_OUT,
    state_updated_seeds_out: Path = DEFAULT_STATE_UPDATED_SEEDS_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_material_newton_breadth_artifacts(
        repo_root=repo_root,
        laws_out=laws_out,
        state_updated_seeds_out=state_updated_seeds_out,
        summary_out=summary_out,
    )
    for key, path in {
        "laws": laws_out,
        "state_updated_seeds": state_updated_seeds_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laws-out", type=Path, default=DEFAULT_LAWS_OUT)
    parser.add_argument(
        "--state-updated-seeds-out",
        type=Path,
        default=DEFAULT_STATE_UPDATED_SEEDS_OUT,
    )
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_material_newton_breadth_artifacts(
            laws_out=args.laws_out,
            state_updated_seeds_out=args.state_updated_seeds_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 material Newton breadth check: {message}")
        return 0 if ok else 1
    artifacts = write_material_newton_breadth_artifacts(
        laws_out=args.laws_out,
        state_updated_seeds_out=args.state_updated_seeds_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 material Newton breadth: "
        f"{summary['status']} | laws={summary['material_law_count']} | "
        f"model_kinds={summary['model_kinds']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
