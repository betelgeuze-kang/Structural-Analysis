#!/usr/bin/env python3
"""Build a bounded receipt for fully constrained stateful nonlinear paths."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
from itertools import pairwise
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
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
    StatefulAxialChainProblem,
    run_stateful_axial_load_path,
    single_element_bilinear_link_problem,
    single_element_composite_section_bar_problem,
    single_element_concrete_damage_bar_problem,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    create_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (  # noqa: E402
    create_execution_plan_reduced_csr,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "stateful_nonlinear_no_solve_reaction_only.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "stateful_nonlinear_no_solve_reaction_only_v1.schema.json"
)
SCHEMA_VERSION = "stateful-nonlinear-no-solve-reaction-only.v1"
LOAD_FACTORS = (0.5, 1.0)
REACTION_BALANCE_TOLERANCE_KN = 1.0e-10
CLAIM_BOUNDARY = (
    "This local deterministic receipt covers three fully constrained, "
    "prescribed-displacement, one-element stateful axial fixtures. With zero "
    "free equations it validates assembly, observes reactions, and atomically "
    "commits constitutive state without entering Newton recurrence, a linear "
    "solve, line search, residual norm, or increment norm. Ready means the "
    "no-solve state-transition contract passed; it is not a Newton convergence "
    "claim and does not close full-building equilibrium, material breadth, G1, "
    "production ROCm/HIP parity, external validation, or release readiness."
)

ProblemFactory = Callable[[], StatefulAxialChainProblem]
CASE_FACTORIES: tuple[tuple[str, ProblemFactory], ...] = (
    ("uniaxial_concrete_damage", single_element_concrete_damage_bar_problem),
    ("perfect_bond_composite_section", single_element_composite_section_bar_problem),
    ("bilinear_force_deformation_link", single_element_bilinear_link_problem),
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _fixture_hash(character: str) -> str:
    return "sha256:" + character * 64


def _engine_v2_fully_constrained_reference() -> dict[str, Any]:
    dof_count = 12
    free_dofs = np.asarray([], dtype="<i4")
    constrained_dofs = np.arange(dof_count, dtype="<i4")
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    execution_plan = create_execution_plan(
        model_ir_content_hash=_fixture_hash("1"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_fixture_hash("2"),
        solver_entity_mapping_hash=_fixture_hash("3"),
        solver_artifact_hash=_fixture_hash("4"),
        load_pattern_id="fully-constrained-reference",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_fixture_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained_dofs,
        free_dofs=free_dofs,
        csr_row_ptr=np.arange(
            0,
            dof_count * dof_count + 1,
            dof_count,
            dtype="<i8",
        ),
        csr_column_indices=np.tile(
            np.arange(dof_count, dtype="<i4"),
            dof_count,
        ),
    )
    identity = create_execution_plan_reduced_csr(
        execution_plan,
        operator_numeric_values_hash=_fixture_hash("6"),
    )
    manifest = identity.to_manifest()
    return {
        "identity_hash": identity.identity_hash,
        "terminal_disposition": identity.terminal_disposition,
        "free_count": identity.free_count,
        "free_nnz": identity.free_nnz,
        "free_csr_row_ptr": identity.array("free_csr_row_ptr").tolist(),
        "free_csr_column_index_count": int(
            identity.array("free_csr_column_indices").size
        ),
        "free_csr_global_value_index_count": int(
            identity.array("free_csr_global_value_indices").size
        ),
        "solver_executed": manifest["claim_boundary"]["solver_executed"],
        "fully_constrained_recurrence_allowed": manifest["claim_boundary"][
            "fully_constrained_recurrence_allowed"
        ],
    }


def _step_receipt(step: Any) -> dict[str, Any]:
    solver = step.trial_solution
    solver_metrics = solver.metrics
    step_metrics = step.metrics
    assembly = step.trial_assembly
    reaction_balance_abs_kn = abs(float(np.sum(assembly.reactions_kn)))
    parent_binding_exact = bool(
        step.parent_state.state_hash == assembly.parent_state_hash
        == step_metrics["parent_state_hash"]
        == step_metrics["trial_parent_state_hash"]
    )
    accepted_binding_exact = bool(
        step.accepted_state.state_hash
        == step_metrics["accepted_state_hash_after"]
    )
    contract_pass = bool(
        step.status == "ready"
        and step.committed
        and solver.status == "ready"
        and solver_metrics.get("contract_pass") is True
        and solver_metrics.get("assembly_contract_valid") is True
        and solver_metrics.get("terminal_disposition")
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        and step_metrics.get("terminal_disposition")
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        and solver_metrics.get("solver_executed") is False
        and step_metrics.get("solver_executed") is False
        and solver_metrics.get("active_equation_count") == 0
        and step_metrics.get("active_equation_count") == 0
        and solver_metrics.get("newton_iteration_count") == 0
        and solver_metrics.get("linear_solve_count") == 0
        and solver_metrics.get("line_search_step_count") == 0
        and solver.convergence_history == []
        and solver.line_search_history == []
        and assembly.residual_kn.shape == (0,)
        and assembly.jacobian_kn_per_m.shape == (0, 0)
        and solver_metrics.get("residual_norm_applicable") is False
        and solver_metrics.get("increment_norm_applicable") is False
        and step_metrics.get("residual_gate_applicable") is False
        and step_metrics.get("increment_gate_applicable") is False
        and solver_metrics.get("residual_gate_passed") is None
        and solver_metrics.get("increment_gate_passed") is None
        and step_metrics.get("residual_gate_passed") is None
        and step_metrics.get("increment_gate_passed") is None
        and solver_metrics.get("convergence_claim") is False
        and step_metrics.get("convergence_claim") is False
        and solver_metrics.get("reaction_observation_only") is True
        and step_metrics.get("no_solve_reaction_only") is True
        and step_metrics.get("terminal_contract_pass") is True
        and step_metrics.get("iterative_solver_contract_pass") is False
        and step_metrics.get("no_solve_contract_pass") is True
        and step_metrics.get("material_state_changed") is True
        and solver_metrics.get("regularization_used") is False
        and solver_metrics.get("fallback_used") is False
        and parent_binding_exact
        and accepted_binding_exact
        and reaction_balance_abs_kn <= REACTION_BALANCE_TOLERANCE_KN
    )
    return {
        "load_factor": assembly.target_load_factor,
        "status": step.status,
        "contract_pass": contract_pass,
        "committed": step.committed,
        "parent_state_hash": step.parent_state.state_hash,
        "accepted_state_hash": step.accepted_state.state_hash,
        "parent_binding_exact": parent_binding_exact,
        "accepted_binding_exact": accepted_binding_exact,
        "active_equation_count": 0,
        "residual_dimension": int(assembly.residual_kn.size),
        "jacobian_shape": list(assembly.jacobian_kn_per_m.shape),
        "terminal_disposition": solver_metrics["terminal_disposition"],
        "terminal_reason": solver_metrics["terminal_reason"],
        "solver_executed": solver_metrics["solver_executed"],
        "newton_iteration_count": solver_metrics["newton_iteration_count"],
        "linear_solve_count": solver_metrics["linear_solve_count"],
        "line_search_step_count": solver_metrics["line_search_step_count"],
        "matrix_backend": solver_metrics["matrix_backend"],
        "residual_norm_applicable": solver_metrics["residual_norm_applicable"],
        "increment_norm_applicable": solver_metrics["increment_norm_applicable"],
        "residual_gate_passed": solver_metrics["residual_gate_passed"],
        "increment_gate_passed": solver_metrics["increment_gate_passed"],
        "convergence_claim": solver_metrics["convergence_claim"],
        "reaction_observation_only": solver_metrics["reaction_observation_only"],
        "terminal_contract_pass": step_metrics["terminal_contract_pass"],
        "iterative_solver_contract_pass": step_metrics[
            "iterative_solver_contract_pass"
        ],
        "no_solve_contract_pass": step_metrics["no_solve_contract_pass"],
        "material_state_changed": step_metrics["material_state_changed"],
        "reaction_balance_abs_kn": reaction_balance_abs_kn,
        "regularization_used": solver_metrics["regularization_used"],
        "fallback_used": solver_metrics["fallback_used"],
    }


def _case_receipt(
    material_family: str,
    factory: ProblemFactory,
) -> dict[str, Any]:
    problem = factory()
    path = run_stateful_axial_load_path(problem, LOAD_FACTORS)
    replay = run_stateful_axial_load_path(problem, LOAD_FACTORS)
    steps = [_step_receipt(step) for step in path.steps]
    deterministic_replay_exact = bool(path.to_dict() == replay.to_dict())
    final_state_hash_replay_exact = bool(
        path.final_state.state_hash == replay.final_state.state_hash
    )
    state_hash_chain_exact = bool(
        steps
        and steps[0]["parent_state_hash"] == path.initial_state.state_hash
        and all(
            current["accepted_state_hash"] == following["parent_state_hash"]
            for current, following in pairwise(steps)
        )
        and steps[-1]["accepted_state_hash"] == path.final_state.state_hash
    )
    maximum_reaction_balance_abs_kn = max(
        (float(step["reaction_balance_abs_kn"]) for step in steps),
        default=float("inf"),
    )
    contract_pass = bool(
        problem.free_node_indices == ()
        and path.status == "ready"
        and path.contract_pass
        and len(steps) == len(LOAD_FACTORS)
        and all(step["contract_pass"] for step in steps)
        and deterministic_replay_exact
        and final_state_hash_replay_exact
        and state_hash_chain_exact
        and path.initial_state.state_hash != path.final_state.state_hash
        and maximum_reaction_balance_abs_kn <= REACTION_BALANCE_TOLERANCE_KN
    )
    return {
        "case_id": problem.case_id,
        "material_family": material_family,
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "active_equation_count": len(problem.free_node_indices),
        "terminal_disposition": NO_SOLVE_REACTION_ONLY_DISPOSITION,
        "initial_state_hash": path.initial_state.state_hash,
        "final_state_hash": path.final_state.state_hash,
        "committed_step_count": sum(step["committed"] is True for step in steps),
        "material_state_changed": bool(
            path.initial_state.state_hash != path.final_state.state_hash
        ),
        "state_hash_chain_exact": state_hash_chain_exact,
        "deterministic_replay_exact": deterministic_replay_exact,
        "final_state_hash_replay_exact": final_state_hash_replay_exact,
        "maximum_reaction_balance_abs_kn": maximum_reaction_balance_abs_kn,
        "newton_iteration_count": sum(
            int(step["newton_iteration_count"]) for step in steps
        ),
        "linear_solve_count": sum(int(step["linear_solve_count"]) for step in steps),
        "line_search_step_count": sum(
            int(step["line_search_step_count"]) for step in steps
        ),
        "solver_executed": any(step["solver_executed"] is True for step in steps),
        "residual_norm_applicable": any(
            step["residual_norm_applicable"] is True for step in steps
        ),
        "increment_norm_applicable": any(
            step["increment_norm_applicable"] is True for step in steps
        ),
        "convergence_claim": any(
            step["convergence_claim"] is True for step in steps
        ),
        "regularization_count": sum(
            step["regularization_used"] is True for step in steps
        ),
        "fallback_count": sum(step["fallback_used"] is True for step in steps),
        "steps": steps,
    }


def build_stateful_nonlinear_no_solve_reaction_only_artifact(
    *,
    repo_root: Path = ROOT,
    output: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    cases = [_case_receipt(family, factory) for family, factory in CASE_FACTORIES]
    engine_v2_reference = _engine_v2_fully_constrained_reference()
    engine_v2_disposition = str(engine_v2_reference["terminal_disposition"])
    engine_v2_terminal_disposition_aligned = bool(
        engine_v2_disposition
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        and engine_v2_reference["free_count"] == 0
        and engine_v2_reference["free_nnz"] == 0
        and engine_v2_reference["free_csr_row_ptr"] == [0]
        and engine_v2_reference["free_csr_column_index_count"] == 0
        and engine_v2_reference["free_csr_global_value_index_count"] == 0
        and engine_v2_reference["solver_executed"] is False
        and engine_v2_reference["fully_constrained_recurrence_allowed"] is False
    )
    maximum_reaction_balance_abs_kn = max(
        float(case["maximum_reaction_balance_abs_kn"]) for case in cases
    )
    contract_pass = bool(
        len(cases) == len(CASE_FACTORIES)
        and all(case["contract_pass"] for case in cases)
        and sum(int(case["newton_iteration_count"]) for case in cases) == 0
        and sum(int(case["linear_solve_count"]) for case in cases) == 0
        and sum(int(case["line_search_step_count"]) for case in cases) == 0
        and not any(case["solver_executed"] for case in cases)
        and not any(case["residual_norm_applicable"] for case in cases)
        and not any(case["increment_norm_applicable"] for case in cases)
        and not any(case["convergence_claim"] for case in cases)
        and sum(int(case["regularization_count"]) for case in cases) == 0
        and sum(int(case["fallback_count"]) for case in cases) == 0
        and maximum_reaction_balance_abs_kn <= REACTION_BALANCE_TOLERANCE_KN
        and engine_v2_terminal_disposition_aligned
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/assembly/stateful_axial.py"),
                Path(
                    "src/structural_analysis/engine_v2/contracts/"
                    "execution_plan_reduced_csr.py"
                ),
                Path(
                    "src/structural_analysis/engine_v2/contracts/"
                    "execution_plan.py"
                ),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("src/structural_analysis/solvers/nonlinear/__init__.py"),
                SCHEMA_PATH,
                Path(
                    "scripts/"
                    "build_stateful_nonlinear_no_solve_reaction_only_artifact.py"
                ),
                Path("tests/test_nonlinear_fully_constrained_no_solve.py"),
                Path(
                    "tests/"
                    "test_build_stateful_nonlinear_no_solve_reaction_only_artifact.py"
                ),
                Path("docs/stateful-nonlinear-no-solve-reaction-only.md"),
            ],
            repo_root=repo_root,
        ),
        "reused_evidence": False,
        "reuse_policy": "fresh_local_deterministic_fixture_recomputation",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "truth_class": "deterministic_local_stateful_axial_fixture_truth",
        "analysis_type": "fully_constrained_prescribed_displacement_state_transition",
        "evidence_scope": "three_one_element_stateful_axial_fixtures",
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "terminal_disposition": NO_SOLVE_REACTION_ONLY_DISPOSITION,
        "engine_v2_terminal_disposition": engine_v2_disposition,
        "engine_v2_reference": engine_v2_reference,
        "load_factors": list(LOAD_FACTORS),
        "reaction_balance_tolerance_kn": REACTION_BALANCE_TOLERANCE_KN,
        "cases": cases,
        "verification": {
            "case_count": len(cases),
            "ready_case_count": sum(case["status"] == "ready" for case in cases),
            "committed_step_count": sum(
                int(case["committed_step_count"]) for case in cases
            ),
            "material_state_changed_case_count": sum(
                case["material_state_changed"] is True for case in cases
            ),
            "deterministic_replay_exact_case_count": sum(
                case["deterministic_replay_exact"] is True for case in cases
            ),
            "state_hash_chain_exact_case_count": sum(
                case["state_hash_chain_exact"] is True for case in cases
            ),
            "maximum_reaction_balance_abs_kn": maximum_reaction_balance_abs_kn,
            "newton_iteration_count": sum(
                int(case["newton_iteration_count"]) for case in cases
            ),
            "linear_solve_count": sum(
                int(case["linear_solve_count"]) for case in cases
            ),
            "line_search_step_count": sum(
                int(case["line_search_step_count"]) for case in cases
            ),
            "solver_executed": any(case["solver_executed"] for case in cases),
            "residual_norm_applicable": any(
                case["residual_norm_applicable"] for case in cases
            ),
            "increment_norm_applicable": any(
                case["increment_norm_applicable"] for case in cases
            ),
            "convergence_claim": any(case["convergence_claim"] for case in cases),
            "regularization_count": sum(
                int(case["regularization_count"]) for case in cases
            ),
            "fallback_count": sum(int(case["fallback_count"]) for case in cases),
            "engine_v2_terminal_disposition_aligned": (
                engine_v2_terminal_disposition_aligned
            ),
        },
        "newton_convergence_claim": False,
        "full_building_equilibrium_claim": False,
        "material_newton_breadth_closure_claim": False,
        "g1_closure_claim": False,
        "production_rocm_hip_parity_claim": False,
        "external_validation_claim": False,
        "release_readiness_claim": False,
        "blockers_remaining": [
            "free_equation_newton_recurrence_not_exercised_by_this_receipt",
            "general_frame_shell_material_coupling_not_closed",
            "full_building_full_load_equilibrium_not_closed",
            "production_sparse_rocm_hip_parity_not_closed",
            "external_validation_not_attached",
        ],
        "artifact_path": str(output),
        "schema_path": str(SCHEMA_PATH),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)
    return payload


def check_stateful_nonlinear_no_solve_reaction_only_artifact(
    *,
    repo_root: Path = ROOT,
    output: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_stateful_nonlinear_no_solve_reaction_only_artifact(
        repo_root=repo_root,
        output=output,
    )
    path = output if output.is_absolute() else repo_root / output
    if not path.is_file():
        return False, f"stateful_nonlinear_no_solve_missing:{output}"
    try:
        existing = _read_json(path)
    except Exception as exc:
        return False, (
            f"stateful_nonlinear_no_solve_unreadable:{output}:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "stateful_nonlinear_no_solve_mismatch"
    return True, "stateful_nonlinear_no_solve_consistent"


def write_stateful_nonlinear_no_solve_reaction_only_artifact(
    *,
    repo_root: Path = ROOT,
    output: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_stateful_nonlinear_no_solve_reaction_only_artifact(
        repo_root=repo_root,
        output=output,
    )
    path = output if output.is_absolute() else repo_root / output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_stateful_nonlinear_no_solve_reaction_only_artifact(
            repo_root=ROOT,
            output=args.output,
        )
        print(message)
        return 0 if ok else 1
    payload = write_stateful_nonlinear_no_solve_reaction_only_artifact(
        repo_root=ROOT,
        output=args.output,
    )
    verification = payload["verification"]
    print(
        f"{payload['status']} | cases={verification['ready_case_count']}/"
        f"{verification['case_count']} | solver_executed="
        f"{verification['solver_executed']} | convergence_claim="
        f"{verification['convergence_claim']}"
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
