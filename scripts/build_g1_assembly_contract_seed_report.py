#!/usr/bin/env python3
"""Build a non-promoting G1 assembly contract seed report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.assembly.coupled_static import (  # noqa: E402
    assemble_frame_shell_material_coupled_state,
    default_frame_shell_material_coupled_problem,
    solve_frame_shell_material_coupled,
)
from structural_analysis.assembly.g1_contract import (  # noqa: E402
    G1_ASSEMBLY_CONTRACT_SCHEMA,
    PROHIBITED_RESIDUAL_SUBSTITUTES,
    assemble_g1_state,
    direct_residual_newton_parity_check,
    finite_difference_g1_jvp_check,
)
from structural_analysis.assembly.material_state import (  # noqa: E402
    assemble_state_updated_frame_shell_coupled_material_state,
    assemble_state_updated_material_axial_chain_mesh_state,
    assemble_state_updated_material_newton_state,
    check_frame_shell_coupled_material_load_step_replay,
    check_material_mesh_load_step_replay,
    check_state_updated_material_checkpoint_replay,
    check_state_updated_material_path_history_replay,
    default_state_updated_frame_shell_coupled_material_problem,
    default_state_updated_bilinear_material_breadth_problems,
    frame_shell_coupled_material_load_step_checkpoint_payload,
    material_mesh_load_step_checkpoint_payload,
    material_path_history_checkpoint_payload,
    material_state_checkpoint_payload,
    solve_default_state_updated_material_path_histories,
    solve_state_updated_frame_shell_coupled_material_load_step_history,
    solve_state_updated_frame_shell_coupled_material_newton,
    solve_state_updated_material_mesh_load_step_history,
    solve_state_updated_material_newton,
)
from structural_analysis.assembly.nonlinear_static import (  # noqa: E402
    assemble_axial_chain_state,
    default_phase2_axial_chain_mesh_problem,
    solve_axial_chain_mesh,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_assembly_contract_seed_report.json"
SCHEMA_VERSION = "g1-assembly-contract-seed-report.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def _case_payload(
    *,
    case_id: str,
    assembly_scope: str,
    solution: Any,
    assembly_result: Any,
    jvp_check: dict[str, Any],
    newton_parity_check: dict[str, Any],
    material_state_persistence_replay_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract_check = assembly_result.contract_check()
    contract_pass = (
        solution.status == "ready"
        and bool(solution.metrics.get("contract_pass"))
        and bool(contract_check["contract_pass"])
        and bool(jvp_check["pass"])
        and bool(newton_parity_check["cpu_seed_consistent_newton_gate_passed"])
        and (
            material_state_persistence_replay_check is None
            or bool(material_state_persistence_replay_check["pass"])
        )
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
        and assembly_result.metrics.get("g1_closure_claim") is False
    )
    payload = {
        "case_id": case_id,
        "assembly_scope": assembly_scope,
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "solution_status": solution.status,
        "solution_contract_pass": bool(solution.metrics.get("contract_pass")),
        "regularization_used": solution.metrics.get("regularization_used"),
        "fallback_used": solution.metrics.get("fallback_used"),
        "assembly_result": assembly_result.to_payload(),
        "assembly_contract_check": contract_check,
        "jvp_finite_difference_check": jvp_check,
        "direct_residual_newton_parity_check": newton_parity_check,
        "g1_closure_claim": False,
    }
    if material_state_persistence_replay_check is not None:
        payload["material_state_persistence_replay_check"] = (
            material_state_persistence_replay_check
        )
    return payload


def build_g1_assembly_contract_seed_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )

    axial_problem = default_phase2_axial_chain_mesh_problem()
    axial_solution, axial_state = solve_axial_chain_mesh(axial_problem, config=config)
    axial_assembly = assemble_g1_state(axial_problem, axial_state)
    axial_jvp = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            axial_problem,
            assemble_axial_chain_state(axial_problem, free_u),
        ),
        axial_solution.free_displacements_m,
    )
    axial_newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            axial_problem,
            assemble_axial_chain_state(axial_problem, free_u),
        ),
        axial_solution,
    )
    axial_case = _case_payload(
        case_id=axial_problem.case_id,
        assembly_scope="narrow_axial_chain_seed",
        solution=axial_solution,
        assembly_result=axial_assembly,
        jvp_check=axial_jvp,
        newton_parity_check=axial_newton_parity,
    )

    coupled_problem = default_frame_shell_material_coupled_problem()
    coupled_solution, coupled_state = solve_frame_shell_material_coupled(
        coupled_problem,
        config=config,
    )
    coupled_assembly = assemble_g1_state(coupled_problem, coupled_state)
    coupled_jvp = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            coupled_problem,
            assemble_frame_shell_material_coupled_state(coupled_problem, free_u),
        ),
        coupled_solution.free_displacements_m,
    )
    coupled_newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            coupled_problem,
            assemble_frame_shell_material_coupled_state(coupled_problem, free_u),
        ),
        coupled_solution,
    )
    coupled_case = _case_payload(
        case_id=coupled_problem.case_id,
        assembly_scope="frame_shell_material_coupled_2dof_seed",
        solution=coupled_solution,
        assembly_result=coupled_assembly,
        jvp_check=coupled_jvp,
        newton_parity_check=coupled_newton_parity,
    )

    material_cases = []
    for material_problem in default_state_updated_bilinear_material_breadth_problems():
        material_solution, material_state = solve_state_updated_material_newton(
            material_problem,
            config=config,
        )
        material_assembly = assemble_g1_state(material_problem, material_state)
        material_checkpoint = material_state_checkpoint_payload(
            material_problem,
            material_state,
        )
        material_checkpoint_roundtrip = json.loads(
            json.dumps(material_checkpoint, ensure_ascii=False)
        )
        material_persistence_replay = (
            check_state_updated_material_checkpoint_replay(
                material_checkpoint_roundtrip
            )
        )
        material_jvp = finite_difference_g1_jvp_check(
            lambda free_u, problem=material_problem: assemble_g1_state(
                problem,
                assemble_state_updated_material_newton_state(problem, free_u),
            ),
            material_solution.free_displacements_m,
        )
        material_newton_parity = direct_residual_newton_parity_check(
            lambda free_u, problem=material_problem: assemble_g1_state(
                problem,
                assemble_state_updated_material_newton_state(problem, free_u),
            ),
            material_solution,
        )
        material_cases.append(
            _case_payload(
                case_id=material_problem.case_id,
                assembly_scope=material_problem.assembly_scope,
                solution=material_solution,
                assembly_result=material_assembly,
                jvp_check=material_jvp,
                newton_parity_check=material_newton_parity,
                material_state_persistence_replay_check=(
                    material_persistence_replay
                ),
            )
        )

    material_path_history_cases = []
    material_path_histories = solve_default_state_updated_material_path_histories(
        config=config,
    )
    material_path_history_replay_checks = {}
    for history in material_path_histories:
        history_checkpoint = material_path_history_checkpoint_payload(history)
        history_checkpoint_roundtrip = json.loads(
            json.dumps(history_checkpoint, ensure_ascii=False)
        )
        material_path_history_replay_checks[history.history_id] = (
            check_state_updated_material_path_history_replay(
                history_checkpoint_roundtrip
            )
        )
        for step in history.steps:
            step_problem = step.problem
            step_state = step.state
            step_solution = step.solution
            step_assembly = assemble_g1_state(step_problem, step_state)
            step_checkpoint = material_state_checkpoint_payload(
                step_problem,
                step_state,
            )
            step_checkpoint_roundtrip = json.loads(
                json.dumps(step_checkpoint, ensure_ascii=False)
            )
            step_persistence_replay = (
                check_state_updated_material_checkpoint_replay(
                    step_checkpoint_roundtrip
                )
            )
            step_jvp = finite_difference_g1_jvp_check(
                lambda free_u, problem=step_problem: assemble_g1_state(
                    problem,
                    assemble_state_updated_material_newton_state(
                        problem,
                        free_u,
                    ),
                ),
                step_solution.free_displacements_m,
            )
            step_newton_parity = direct_residual_newton_parity_check(
                lambda free_u, problem=step_problem: assemble_g1_state(
                    problem,
                    assemble_state_updated_material_newton_state(
                        problem,
                        free_u,
                    ),
                ),
                step_solution,
            )
            step_case = _case_payload(
                case_id=step_problem.case_id,
                assembly_scope=step_problem.assembly_scope,
                solution=step_solution,
                assembly_result=step_assembly,
                jvp_check=step_jvp,
                newton_parity_check=step_newton_parity,
                material_state_persistence_replay_check=(
                    step_persistence_replay
                ),
            )
            step_case["material_path_history"] = {
                "history_id": history.history_id,
                "history_step_index": step.history_step_index,
                "step_kind": step.step_kind,
                "external_force_kn": step.external_force_kn,
                "carried_committed_state_previous": (
                    step.carried_committed_state_previous
                ),
                "previous_committed_state_matches_carried_state": (
                    step.previous_committed_state_matches_carried_state
                ),
                "history_checkpoint_replay_pass": bool(
                    material_path_history_replay_checks[history.history_id][
                        "pass"
                    ]
                ),
                "history_chain_replay_pass": bool(
                    material_path_history_replay_checks[history.history_id][
                        "committed_state_chain_replay_pass"
                    ]
                ),
            }
            material_path_history_cases.append(step_case)

    coupled_material_problem = (
        default_state_updated_frame_shell_coupled_material_problem()
    )
    coupled_material_solution, coupled_material_state = (
        solve_state_updated_frame_shell_coupled_material_newton(
            coupled_material_problem,
            config=config,
        )
    )
    coupled_material_assembly = assemble_g1_state(
        coupled_material_problem,
        coupled_material_state,
    )
    coupled_material_jvp = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            coupled_material_problem,
            assemble_state_updated_frame_shell_coupled_material_state(
                coupled_material_problem,
                free_u,
            ),
        ),
        coupled_material_solution.free_displacements_m,
    )
    coupled_material_newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            coupled_material_problem,
            assemble_state_updated_frame_shell_coupled_material_state(
                coupled_material_problem,
                free_u,
            ),
        ),
        coupled_material_solution,
    )
    coupled_material_case = _case_payload(
        case_id=coupled_material_problem.case_id,
        assembly_scope="state_updated_frame_shell_coupled_material_seed",
        solution=coupled_material_solution,
        assembly_result=coupled_material_assembly,
        jvp_check=coupled_material_jvp,
        newton_parity_check=coupled_material_newton_parity,
    )

    coupled_material_load_step_cases = []
    coupled_material_load_step_history = (
        solve_state_updated_frame_shell_coupled_material_load_step_history(
            config=config,
        )
    )
    coupled_material_load_step_checkpoint = (
        frame_shell_coupled_material_load_step_checkpoint_payload(
            coupled_material_load_step_history
        )
    )
    coupled_material_load_step_replay = (
        check_frame_shell_coupled_material_load_step_replay(
            json.loads(
                json.dumps(
                    coupled_material_load_step_checkpoint,
                    ensure_ascii=False,
                )
            )
        )
    )
    for step in coupled_material_load_step_history.steps:
        step_assembly = assemble_g1_state(step.problem, step.state)
        step_jvp = finite_difference_g1_jvp_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_frame_shell_coupled_material_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution.free_displacements_m,
        )
        step_newton_parity = direct_residual_newton_parity_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_frame_shell_coupled_material_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution,
        )
        step_case = _case_payload(
            case_id=step.problem.case_id,
            assembly_scope="state_updated_frame_shell_coupled_material_load_step_history",
            solution=step.solution,
            assembly_result=step_assembly,
            jvp_check=step_jvp,
            newton_parity_check=step_newton_parity,
        )
        step_case["frame_shell_coupled_load_step_history"] = {
            "history_id": coupled_material_load_step_history.history_id,
            "history_step_index": step.history_step_index,
            "step_kind": step.step_kind,
            "external_force_kn": list(step.external_force_kn),
            "carried_component_committed_state_previous": (
                step.carried_component_committed_state_previous
            ),
            "previous_component_committed_state_matches_carried_state": (
                step.previous_component_committed_state_matches_carried_state
            ),
            "history_checkpoint_replay_pass": bool(
                coupled_material_load_step_replay["pass"]
            ),
            "history_chain_replay_pass": bool(
                coupled_material_load_step_replay[
                    "committed_component_state_chain_replay_pass"
                ]
            ),
        }
        coupled_material_load_step_cases.append(step_case)

    material_mesh_load_step_cases = []
    material_mesh_load_step_history = (
        solve_state_updated_material_mesh_load_step_history(config=config)
    )
    material_mesh_load_step_checkpoint = material_mesh_load_step_checkpoint_payload(
        material_mesh_load_step_history
    )
    material_mesh_load_step_replay = check_material_mesh_load_step_replay(
        json.loads(
            json.dumps(
                material_mesh_load_step_checkpoint,
                ensure_ascii=False,
            )
        )
    )
    for step in material_mesh_load_step_history.steps:
        step_assembly = assemble_g1_state(step.problem, step.state)
        step_jvp = finite_difference_g1_jvp_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_material_axial_chain_mesh_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution.free_displacements_m,
        )
        step_newton_parity = direct_residual_newton_parity_check(
            lambda free_u, problem=step.problem: assemble_g1_state(
                problem,
                assemble_state_updated_material_axial_chain_mesh_state(
                    problem,
                    free_u,
                ),
            ),
            step.solution,
        )
        step_case = _case_payload(
            case_id=step.problem.case_id,
            assembly_scope="state_updated_material_axial_chain_mesh_load_step_history",
            solution=step.solution,
            assembly_result=step_assembly,
            jvp_check=step_jvp,
            newton_parity_check=step_newton_parity,
        )
        step_case["material_mesh_load_step_history"] = {
            "history_id": material_mesh_load_step_history.history_id,
            "history_step_index": step.history_step_index,
            "step_kind": step.step_kind,
            "external_force_kn": [
                {"node_index": node, "force_kn": force}
                for node, force in step.external_force_kn
            ],
            "carried_element_committed_state_previous": (
                step.carried_element_committed_state_previous
            ),
            "previous_element_committed_state_matches_carried_state": (
                step.previous_element_committed_state_matches_carried_state
            ),
            "history_checkpoint_replay_pass": bool(
                material_mesh_load_step_replay["pass"]
            ),
            "history_chain_replay_pass": bool(
                material_mesh_load_step_replay[
                    "committed_element_state_chain_replay_pass"
                ]
            ),
        }
        material_mesh_load_step_cases.append(step_case)

    cases = [
        axial_case,
        coupled_case,
        *material_cases,
        *material_path_history_cases,
        coupled_material_case,
        *coupled_material_load_step_cases,
        *material_mesh_load_step_cases,
    ]
    contract_pass = all(row["contract_pass"] for row in cases)
    cpu_seed_newton_gate_passed = all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        for row in cases
    )
    state_updated_material_seed_passed = all(
        row["contract_pass"]
        and bool(
            row["assembly_result"]["material_state_next"].get(
                "state_updated_material_newton"
            )
        )
        for row in material_cases
    )
    material_case_kinds = [
        str(
            row["assembly_result"]["material_state_next"].get(
                "material_case_kind"
            )
        )
        for row in material_cases
    ]
    material_structural_components = sorted(
        {
            str(
                row["assembly_result"]["material_state_next"].get(
                    "structural_component"
                )
            )
            for row in material_cases
        }
    )
    material_families = sorted(
        {
            str(
                row["assembly_result"]["material_state_next"].get(
                    "material_family"
                )
            )
            for row in material_cases
        }
    )
    material_section_integrations = sorted(
        {
            str(
                row["assembly_result"]["material_state_next"].get(
                    "section_integration"
                )
            )
            for row in material_cases
        }
    )
    material_strain_modes = sorted(
        {
            str(row["assembly_result"]["material_state_next"].get("strain_mode"))
            for row in material_cases
        }
    )
    path_dependent_update_case_count = sum(
        1
        for row in material_cases
        if row["assembly_result"]["material_state_next"].get(
            "path_dependent_state_updated"
        )
        is True
    )
    path_dependent_replay_case_count = sum(
        1
        for row in material_cases
        if row["assembly_result"]["material_state_next"].get(
            "path_dependent_state"
        )
        is True
    )
    material_state_persistence_replay_passed = all(
        row.get("material_state_persistence_replay_check", {}).get("pass") is True
        for row in material_cases
    )
    material_jvp_max_relative_error = max(
        (
            float(row["jvp_finite_difference_check"]["relative_error"])
            for row in material_cases
        ),
        default=0.0,
    )
    material_path_history_chain_replay_pass = all(
        replay["pass"]
        and replay["committed_state_chain_replay_pass"]
        and replay["step_replay_pass"]
        for replay in material_path_history_replay_checks.values()
    )
    material_path_history_passed = (
        all(history.committed_state_chain_pass for history in material_path_histories)
        and all(row["contract_pass"] for row in material_path_history_cases)
        and material_path_history_chain_replay_pass
    )
    material_path_history_step_count = len(material_path_history_cases)
    material_path_history_update_step_count = sum(
        history.path_dependent_update_step_count for history in material_path_histories
    )
    material_path_history_checkpoint_replay_pass = all(
        row.get("material_state_persistence_replay_check", {}).get("pass") is True
        for row in material_path_history_cases
    )
    material_path_history_jvp_pass = all(
        row["jvp_finite_difference_check"]["pass"] is True
        for row in material_path_history_cases
    )
    material_path_history_direct_parity_pass = all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        is True
        for row in material_path_history_cases
    )
    material_path_history_committed_chain_pass = all(
        history.committed_state_chain_pass for history in material_path_histories
    )
    coupled_material_state_next = coupled_material_case["assembly_result"][
        "material_state_next"
    ]
    coupled_material_seed_passed = bool(coupled_material_case["contract_pass"])
    coupled_material_load_step_history_passed = (
        coupled_material_load_step_history.committed_component_state_chain_pass
        and bool(coupled_material_load_step_replay["pass"])
        and all(row["contract_pass"] for row in coupled_material_load_step_cases)
    )
    coupled_material_load_step_jvp_pass = all(
        row["jvp_finite_difference_check"]["pass"] is True
        for row in coupled_material_load_step_cases
    )
    coupled_material_load_step_direct_parity_pass = all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        is True
        for row in coupled_material_load_step_cases
    )
    material_mesh_load_step_history_passed = (
        material_mesh_load_step_history.committed_element_state_chain_pass
        and bool(material_mesh_load_step_replay["pass"])
        and all(row["contract_pass"] for row in material_mesh_load_step_cases)
    )
    material_mesh_load_step_jvp_pass = all(
        row["jvp_finite_difference_check"]["pass"] is True
        for row in material_mesh_load_step_cases
    )
    material_mesh_load_step_direct_parity_pass = all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        is True
        for row in material_mesh_load_step_cases
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/assembly/g1_contract.py"),
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                Path("src/structural_analysis/assembly/coupled_static.py"),
                Path("src/structural_analysis/assembly/material_state.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("scripts/build_g1_assembly_contract_seed_report.py"),
                Path("tests/test_g1_assembly_contract.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "promotes_g1_closure": False,
        "g1_closure_claim": False,
        "phase_covered": (
            "phase1_phase2_cpu_seed_contract_newton_parity_and_"
            "state_updated_material_breadth_seeds"
        ),
        "assembly_contract_schema": G1_ASSEMBLY_CONTRACT_SCHEMA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "required_fields": [
            "residual_free",
            "tangent_free",
            "internal_forces",
            "external_forces",
            "material_state_next",
            "metrics",
        ],
        "prohibited_physical_residual_substitutes": list(
            PROHIBITED_RESIDUAL_SUBSTITUTES
        ),
        "fixed_point_residual_promoted_to_physical": False,
        "regularized_fixed_point_substitute": False,
        "cpu_seed_consistent_newton_gate_passed": cpu_seed_newton_gate_passed,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "state_updated_material_newton_seed_passed": state_updated_material_seed_passed,
        "state_updated_material_newton_seed_case_count": len(material_cases),
        "state_updated_material_newton_seed_case_kinds": material_case_kinds,
        "state_updated_material_newton_seed_structural_components": (
            material_structural_components
        ),
        "state_updated_material_newton_seed_material_families": material_families,
        "state_updated_material_newton_seed_section_integrations": (
            material_section_integrations
        ),
        "state_updated_material_newton_seed_strain_modes": material_strain_modes,
        "path_dependent_material_update_seed_case_count": (
            path_dependent_update_case_count
        ),
        "path_dependent_material_replay_seed_case_count": (
            path_dependent_replay_case_count
        ),
        "material_state_persistence_replay_seed_passed": (
            material_state_persistence_replay_passed
        ),
        "material_state_persistence_replay_seed_case_count": len(material_cases),
        "material_jvp_max_relative_error": material_jvp_max_relative_error,
        "state_updated_material_path_history_passed": material_path_history_passed,
        "state_updated_material_path_history_count": len(material_path_histories),
        "state_updated_material_path_history_step_count": (
            material_path_history_step_count
        ),
        "state_updated_material_path_history_update_step_count": (
            material_path_history_update_step_count
        ),
        "state_updated_material_path_history_checkpoint_replay_pass": (
            material_path_history_checkpoint_replay_pass
        ),
        "state_updated_material_path_history_chain_replay_pass": (
            material_path_history_chain_replay_pass
        ),
        "state_updated_material_path_history_jvp_pass": (
            material_path_history_jvp_pass
        ),
        "state_updated_material_path_history_direct_parity_pass": (
            material_path_history_direct_parity_pass
        ),
        "state_updated_material_path_history_committed_chain_pass": (
            material_path_history_committed_chain_pass
        ),
        "state_updated_material_path_history_replay_checks": list(
            material_path_history_replay_checks.values()
        ),
        "state_updated_frame_shell_coupled_material_seed_passed": (
            coupled_material_seed_passed
        ),
        "state_updated_frame_shell_coupled_material_component_updates_pass": (
            coupled_material_state_next.get("frame_material_state_updated") is True
            and coupled_material_state_next.get("shell_material_state_updated") is True
        ),
        "state_updated_frame_shell_coupled_material_jvp_pass": (
            coupled_material_jvp["pass"] is True
        ),
        "state_updated_frame_shell_coupled_material_direct_parity_pass": (
            coupled_material_newton_parity[
                "cpu_seed_consistent_newton_gate_passed"
            ]
            is True
        ),
        "state_updated_frame_shell_coupled_load_step_history_passed": (
            coupled_material_load_step_history_passed
        ),
        "state_updated_frame_shell_coupled_load_step_history_step_count": (
            len(coupled_material_load_step_cases)
        ),
        "state_updated_frame_shell_coupled_load_step_history_update_step_count": (
            coupled_material_load_step_history.path_dependent_update_step_count
        ),
        "state_updated_frame_shell_coupled_load_step_history_checkpoint_replay_pass": (
            coupled_material_load_step_replay["pass"] is True
        ),
        "state_updated_frame_shell_coupled_load_step_history_chain_replay_pass": (
            coupled_material_load_step_replay[
                "committed_component_state_chain_replay_pass"
            ]
            is True
        ),
        "state_updated_frame_shell_coupled_load_step_history_jvp_pass": (
            coupled_material_load_step_jvp_pass
        ),
        "state_updated_frame_shell_coupled_load_step_history_direct_parity_pass": (
            coupled_material_load_step_direct_parity_pass
        ),
        "state_updated_frame_shell_coupled_load_step_history_replay_check": (
            coupled_material_load_step_replay
        ),
        "state_updated_material_mesh_load_step_history_passed": (
            material_mesh_load_step_history_passed
        ),
        "state_updated_material_mesh_load_step_history_step_count": (
            len(material_mesh_load_step_cases)
        ),
        "state_updated_material_mesh_load_step_history_update_step_count": (
            material_mesh_load_step_history.path_dependent_update_step_count
        ),
        "state_updated_material_mesh_load_step_history_checkpoint_replay_pass": (
            material_mesh_load_step_replay["pass"] is True
        ),
        "state_updated_material_mesh_load_step_history_chain_replay_pass": (
            material_mesh_load_step_replay[
                "committed_element_state_chain_replay_pass"
            ]
            is True
        ),
        "state_updated_material_mesh_load_step_history_jvp_pass": (
            material_mesh_load_step_jvp_pass
        ),
        "state_updated_material_mesh_load_step_history_direct_parity_pass": (
            material_mesh_load_step_direct_parity_pass
        ),
        "state_updated_material_mesh_load_step_history_replay_check": (
            material_mesh_load_step_replay
        ),
        "state_updated_material_newton_breadth_seed_coverage_ready": (
            state_updated_material_seed_passed
            and material_state_persistence_replay_passed
            and material_path_history_passed
            and material_path_history_chain_replay_pass
            and coupled_material_seed_passed
            and coupled_material_load_step_history_passed
            and material_mesh_load_step_history_passed
            and {"reinforced_concrete", "steel", "src_composite"}.issubset(
                set(material_families)
            )
            and {"frame_fiber", "layered_shell", "composite_fiber"}.issubset(
                set(material_section_integrations)
            )
            and {"axial", "membrane", "bending", "drilling"}.issubset(
                set(material_strain_modes)
            )
        ),
        "state_updated_material_newton_breadth_closed": False,
        "case_count": len(cases),
        "cases": cases,
        "blockers_remaining": [
            "full_load_gate_not_closed",
            "full_mesh_nonlinear_equilibrium_not_closed",
            "material_newton_breadth_not_closed",
            "production_rocm_hip_residency_not_closed",
            "g1_consistent_residual_jacobian_newton_gate_not_closed_by_cpu_seed",
            "full_load_checkpoint_1p0_not_created_by_this_seed_report",
            "hip_residual_jvp_worker_not_executed_by_this_seed_report",
        ],
        "artifacts": {
            "report": str(out),
            "related_runner_contract": str(
                PRODUCTIZATION / "g1_consistent_newton_full_load_checkpoint_candidate_runner.json"
            ),
            "related_full_load_lane": str(
                PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
            ),
        },
        "claim_boundary": (
            "This report validates the shared AssemblyResult shape, physical "
            "R=F_internal-F_external convention, and central-difference JVP guard "
            "on deterministic CPU seed assemblies, including a path-dependent "
            "state-updated material return-mapping breadth seed suite. It also replays each seed "
            "Newton history through the same physical assembly to verify direct "
            "residual/Newton residual parity and residual descent, including "
            "carried-state unload/reverse/reload path histories and a two-DOF "
            "frame/shell coupled state-updated material seed plus a coupled "
            "frame/shell load-step material-state history and a two-element "
            "state-updated material mesh load-step history. It does not "
            "create a full-load 1.0 checkpoint, prove full-mesh nonlinear "
            "equilibrium, close state-updated material Newton breadth, execute "
            "ROCm/HIP, or promote G1."
        ),
    }
    return payload


def check_g1_assembly_contract_seed_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_g1_assembly_contract_seed_report(repo_root=repo_root, out=out)
    resolved = out if out.is_absolute() else repo_root / out
    if not resolved.exists():
        return False, f"g1_assembly_contract_seed_report_missing:{out.as_posix()}"
    try:
        existing = _read_json(resolved)
    except Exception as exc:
        return False, (
            f"g1_assembly_contract_seed_report_unreadable:{out.as_posix()}:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_assembly_contract_seed_report_mismatch"
    return True, "g1_assembly_contract_seed_report_consistent"


def write_g1_assembly_contract_seed_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_g1_assembly_contract_seed_report(repo_root=repo_root, out=out)
    resolved = out if out.is_absolute() else repo_root / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_g1_assembly_contract_seed_report(out=args.out)
        print(f"G1 assembly contract seed report check: {message}")
        return 0 if ok else 1
    payload = write_g1_assembly_contract_seed_report(out=args.out)
    print(
        "G1 assembly contract seed report: "
        f"{payload['status']} | cases={payload['case_count']} | "
        f"promotes_g1={payload['promotes_g1_closure']}"
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
