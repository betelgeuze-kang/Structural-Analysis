#!/usr/bin/env python3
"""Build the N1 stateful-material matrix-free Newton breadth receipt.

This is a deliberately bounded constitutive breadth gate.  It exercises four
stateful axial material families through the same residual, current-tangent,
line-search, increment-gate, commit, rollback, and restart implementation used
by the reusable CPU matrix-free Newton path.  Full-building frame/shell
material coupling remains outside this receipt and is disclosed explicitly.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import (  # noqa: E402
    commit_bound_input_metadata,
    engine_version,
)
from structural_analysis.assembly.stateful_axial import (  # noqa: E402
    StatefulAxialChainProblem,
    initial_stateful_axial_state,
    two_element_bilinear_link_chain_problem,
    two_element_composite_section_chain_problem,
    two_element_concrete_damage_chain_problem,
    two_element_stateful_steel_chain_problem,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (  # noqa: E402
    LoadControlledMatrixFreeNewtonConfig,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
)
from structural_analysis.solvers.nonlinear.stateful_axial_matrix_free_newton import (  # noqa: E402
    STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION,
    STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE,
    finite_difference_stateful_axial_matrix_free_tangent_check,
    run_stateful_axial_matrix_free_load_path,
    solve_stateful_axial_matrix_free_load_step,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION / "n1_stateful_material_matrix_free_newton_breadth_receipt.json"
)
SCHEMA_VERSION = "n1-stateful-material-matrix-free-newton-breadth-receipt.v1"
CLAIM_BOUNDARY = (
    "This receipt proves a four-family stateful axial constitutive breadth gate "
    "through the reusable CPU matrix-free Newton path. It verifies physical "
    "residual/current-tangent consistency, physical-merit line search, residual "
    "and increment acceptance, immutable-parent trial evaluation, atomic material "
    "commit, byte-exact failed-step rollback, byte-exact midpoint restart, and "
    "zero fallback/regularization through load factor 1.0. It does not prove that "
    "stateful materials are connected to the actual MGT full-building frame/shell "
    "operator, production Krylov/preconditioning, ROCm/HIP parity, or N1/G1 closure."
)


ProblemFactory = Callable[[], StatefulAxialChainProblem]
FAMILIES: tuple[tuple[str, ProblemFactory, tuple[float, ...]], ...] = (
    ("steel_combined_hardening", two_element_stateful_steel_chain_problem, (0.5, 1.0)),
    (
        "asymmetric_concrete_damage",
        two_element_concrete_damage_chain_problem,
        (0.25, 0.5, 0.75, 1.0),
    ),
    (
        "parallel_steel_concrete_section",
        two_element_composite_section_chain_problem,
        (0.25, 0.5, 0.75, 1.0),
    ),
    ("bilinear_combined_hardening_link", two_element_bilinear_link_chain_problem, (0.5, 1.0)),
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


def _config(*, maximum_newton_iterations: int = 8) -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=1.0e-9,
        increment_absolute_tolerance_inf_m=1.0e-12,
        increment_relative_tolerance=1.0e-9,
        tangent_solve_residual_tolerance_inf_kn=1.0e-9,
        maximum_newton_iterations=maximum_newton_iterations,
    )


def _input_paths() -> tuple[Path, ...]:
    return (
        Path("src/structural_analysis/assembly/stateful_axial.py"),
        Path("src/structural_analysis/materials/bilinear_link.py"),
        Path("src/structural_analysis/materials/composite_section.py"),
        Path("src/structural_analysis/materials/concrete_damage.py"),
        Path("src/structural_analysis/materials/uniaxial_plasticity.py"),
        Path("src/structural_analysis/solvers/nonlinear/load_controlled_matrix_free_newton.py"),
        Path("src/structural_analysis/solvers/nonlinear/matrix_free_fgmres.py"),
        Path("src/structural_analysis/solvers/nonlinear/newton.py"),
        Path("src/structural_analysis/solvers/nonlinear/stateful_axial_matrix_free_newton.py"),
        Path("scripts/build_n1_stateful_material_matrix_free_newton_breadth_receipt.py"),
        Path("scripts/release_evidence_metadata.py"),
        Path("tests/test_build_n1_stateful_material_matrix_free_newton_breadth_receipt.py"),
    )


def _family_row(
    family: str,
    factory: ProblemFactory,
    load_factors: tuple[float, ...],
) -> dict[str, Any]:
    problem = factory()
    config = _config()
    one_shot = run_stateful_axial_matrix_free_load_path(
        problem,
        load_factors,
        config=config,
    )
    replay = run_stateful_axial_matrix_free_load_path(
        problem,
        load_factors,
        config=config,
    )
    split = max(1, len(load_factors) // 2)
    prefix = run_stateful_axial_matrix_free_load_path(
        problem,
        load_factors[:split],
        config=config,
    )
    resumed = run_stateful_axial_matrix_free_load_path(
        problem,
        load_factors[split:],
        initial_state=prefix.final_state,
        config=config,
    )

    final_step = one_shot.steps[-1]
    final_step_problem = final_step.step_problem
    free = list(problem.free_node_indices)
    parent_free = np.asarray(
        final_step.parent_state.displacements_m,
        dtype=np.float64,
    )[free]
    final_free = np.asarray(
        final_step.accepted_state.displacements_m,
        dtype=np.float64,
    )[free]
    direction = np.linspace(
        0.4,
        -0.7 if final_step_problem.equation_count > 1 else 0.4,
        final_step_problem.equation_count,
        dtype=np.float64,
    )
    tangent_check = finite_difference_stateful_axial_matrix_free_tangent_check(
        final_step_problem,
        displacement_increments_m=final_free - parent_free,
        increment_load_factor=1.0,
        direction_m=direction,
    )

    initial = initial_stateful_axial_state(problem)
    failed = solve_stateful_axial_matrix_free_load_step(
        problem,
        initial,
        target_load_factor=1.0,
        config=_config(maximum_newton_iterations=1),
    )
    exact_restart = bool(
        prefix.status == "ready"
        and resumed.status == "ready"
        and resumed.final_state.state_hash == one_shot.final_state.state_hash
        and resumed.final_state.canonical_bytes()
        == one_shot.final_state.canonical_bytes()
    )
    deterministic_replay = bool(
        replay.final_state.state_hash == one_shot.final_state.state_hash
        and replay.final_state.canonical_bytes()
        == one_shot.final_state.canonical_bytes()
        and replay.to_dict() == one_shot.to_dict()
    )
    step_rows = [
        {
            "step_index": step.accepted_state.step_index,
            "load_factor": step.accepted_state.load_factor,
            "committed": step.committed,
            "parent_state_hash": step.parent_state.state_hash,
            "accepted_state_hash": step.accepted_state.state_hash,
            "final_residual_inf_kn": step.metrics["final_residual_inf_kn"],
            "residual_and_increment_acceptance_gate": step.metrics[
                "residual_and_increment_acceptance_gate"
            ],
            "tangent_solve_count": step.metrics["tangent_solve_count"],
            "fallback_count": step.metrics["fallback_count"],
            "regularization_count": step.metrics["regularization_count"],
            "material_state_changed": step.metrics["material_state_changed"],
            "parent_state_unchanged_during_trial": step.metrics[
                "parent_state_unchanged_during_trial"
            ],
            "maximum_line_search_backtrack_count": step.metrics[
                "maximum_line_search_backtrack_count"
            ],
        }
        for step in one_shot.steps
    ]
    final_residual = max(
        float(step.metrics["final_residual_inf_kn"])
        for step in one_shot.steps
    )
    fallback_count = sum(
        int(step.metrics["fallback_count"]) for step in one_shot.steps
    )
    regularization_count = sum(
        int(step.metrics["regularization_count"]) for step in one_shot.steps
    )
    tangent_solve_count = sum(
        int(step.metrics["tangent_solve_count"]) for step in one_shot.steps
    )
    rollback_exact = bool(
        failed.status == "blocked"
        and not failed.committed
        and failed.metrics["rollback_exact"] is True
        and failed.accepted_state.state_hash == initial.state_hash
        and failed.accepted_state.canonical_bytes() == initial.canonical_bytes()
    )
    contract_pass = bool(
        one_shot.status == "ready"
        and one_shot.contract_pass
        and one_shot.final_state.load_factor == 1.0
        and all(step.committed for step in one_shot.steps)
        and all(
            step.metrics["residual_and_increment_acceptance_gate"]
            for step in one_shot.steps
        )
        and all(
            step.metrics["parent_state_unchanged_during_trial"]
            for step in one_shot.steps
        )
        and any(
            step.metrics["material_state_changed"]
            for step in one_shot.steps
        )
        and tangent_solve_count > 0
        and tangent_check["contract_pass"] is True
        and final_residual <= config.residual_tolerance_inf_kn
        and fallback_count == 0
        and regularization_count == 0
        and rollback_exact
        and exact_restart
        and deterministic_replay
    )
    return {
        "family": family,
        "case_id": problem.case_id,
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "node_count": problem.node_count,
        "element_count": len(problem.elements),
        "free_equation_count": len(problem.free_node_indices),
        "load_factors": list(load_factors),
        "final_load_factor": one_shot.final_state.load_factor,
        "initial_state_hash": one_shot.initial_state.state_hash,
        "final_state_hash": one_shot.final_state.state_hash,
        "final_material_state_hashes": [
            state.state_hash for state in one_shot.final_state.material_states
        ],
        "maximum_committed_residual_inf_kn": final_residual,
        "tangent_solve_count": tangent_solve_count,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "material_state_changed": any(
            step.metrics["material_state_changed"] for step in one_shot.steps
        ),
        "finite_difference_current_tangent": tangent_check,
        "failed_step_probe": {
            "status": failed.status,
            "terminal_reason": failed.newton_result.terminal_reason,
            "rollback_exact": rollback_exact,
            "accepted_state_hash_before": initial.state_hash,
            "accepted_state_hash_after": failed.accepted_state.state_hash,
            "material_state_commit_performed": failed.committed,
        },
        "checkpoint_restart": {
            "split_after_load_factor": load_factors[split - 1],
            "checkpoint_state_hash": prefix.final_state.state_hash,
            "one_shot_final_state_hash": one_shot.final_state.state_hash,
            "resumed_final_state_hash": resumed.final_state.state_hash,
            "byte_exact": exact_restart,
        },
        "deterministic_replay_byte_exact": deterministic_replay,
        "steps": step_rows,
    }


def build_receipt(
    *,
    repo_root: Path = ROOT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source = commit_bound_input_metadata(
        _input_paths(),
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    family_rows = [
        _family_row(family, factory, factors)
        for family, factory, factors in FAMILIES
    ]
    source_exact = bool(source["source_input_provenance"]["contract_pass"])
    family_contract = bool(
        len(family_rows) == len(FAMILIES)
        and all(row["contract_pass"] for row in family_rows)
    )
    fallback_count = sum(int(row["fallback_count"]) for row in family_rows)
    regularization_count = sum(
        int(row["regularization_count"]) for row in family_rows
    )
    contract_pass = bool(
        source_exact
        and family_contract
        and fallback_count == 0
        and regularization_count == 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source["source_commit_sha"],
        "engine_version": engine_version(repo_root),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "source_commit_exact_replay_claim": source_exact,
        "source_input_provenance": source["source_input_provenance"],
        "input_checksums": source["input_checksums"],
        "analysis_type": "stateful_axial_material_matrix_free_newton_breadth",
        "profile": STATEFUL_AXIAL_MATRIX_FREE_NEWTON_PROFILE,
        "residual_formula": RESIDUAL_FORMULA,
        "residual_formula_hash": RESIDUAL_FORMULA_HASH,
        "current_tangent_action_contract": (
            STATEFUL_AXIAL_MATRIX_FREE_CURRENT_TANGENT_ACTION
        ),
        "line_search_merit": "half_squared_physical_residual_l2.v1",
        "target_load_factor": 1.0,
        "material_family_count": len(family_rows),
        "material_families": [row["family"] for row in family_rows],
        "family_contract_pass": family_contract,
        "fallback_count": fallback_count,
        "regularization_count": regularization_count,
        "all_family_residual_gates_passed": all(
            row["maximum_committed_residual_inf_kn"] <= 1.0e-9
            for row in family_rows
        ),
        "all_family_increment_gates_passed": all(
            all(step["residual_and_increment_acceptance_gate"] for step in row["steps"])
            for row in family_rows
        ),
        "all_family_tangent_checks_passed": all(
            row["finite_difference_current_tangent"]["contract_pass"]
            for row in family_rows
        ),
        "all_family_material_commits_observed": all(
            row["material_state_changed"] for row in family_rows
        ),
        "all_family_failed_step_rollbacks_byte_exact": all(
            row["failed_step_probe"]["rollback_exact"] for row in family_rows
        ),
        "all_family_checkpoint_restarts_byte_exact": all(
            row["checkpoint_restart"]["byte_exact"] for row in family_rows
        ),
        "all_family_deterministic_replays_byte_exact": all(
            row["deterministic_replay_byte_exact"] for row in family_rows
        ),
        "family_rows": family_rows,
        "claims": {
            "stateful_material_matrix_free_newton_family_breadth": contract_pass,
            "trial_commit_rollback": contract_pass,
            "exact_restart": contract_pass,
            "load_scale_at_least_one": contract_pass,
            "fallback_zero": fallback_count == 0,
            "regularization_zero": regularization_count == 0,
            "actual_mgt_full_mesh_material_coupling": False,
            "full_frame_shell_material_newton": False,
            "production_krylov": False,
            "rocm_hip_parity": False,
            "n1_closure": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "actual_mgt_full_mesh_stateful_material_coupling_not_connected",
            "full_frame_shell_material_consistent_operator_not_connected",
            "production_preconditioner_effectiveness_not_established",
            "production_rocm_hip_nonlinear_parity_not_executed",
        ],
        "artifacts": {"receipt": str(receipt_out)},
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _stored_source_commit(repo_root: Path, receipt_out: Path) -> str | None:
    path = receipt_out if receipt_out.is_absolute() else repo_root / receipt_out
    if not path.is_file():
        return None
    source = _read_json(path).get("source_commit_sha")
    return str(source) if isinstance(source, str) and source else None


def check_receipt(
    *,
    repo_root: Path = ROOT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
) -> tuple[bool, str]:
    path = receipt_out if receipt_out.is_absolute() else repo_root / receipt_out
    if not path.is_file():
        return False, f"n1_material_breadth_receipt_missing:{receipt_out}"
    existing = _read_json(path)
    expected = build_receipt(
        repo_root=repo_root,
        receipt_out=receipt_out,
        source_commit_sha=_stored_source_commit(repo_root, receipt_out),
    )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "n1_material_breadth_receipt_mismatch"
    return True, "n1_material_breadth_receipt_consistent"


def write_receipt(
    *,
    repo_root: Path = ROOT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_receipt(
        repo_root=repo_root,
        receipt_out=receipt_out,
        source_commit_sha=source_commit_sha,
    )
    path = receipt_out if receipt_out.is_absolute() else repo_root / receipt_out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_receipt(
            repo_root=ROOT,
            receipt_out=args.receipt_out,
        )
        print(message)
        return 0 if ok else 1
    payload = write_receipt(
        repo_root=ROOT,
        receipt_out=args.receipt_out,
        source_commit_sha=args.source_commit_sha,
    )
    print(
        f"{payload['status']} | families={payload['material_family_count']} | "
        f"fallback={payload['fallback_count']} | "
        f"regularization={payload['regularization_count']}"
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
