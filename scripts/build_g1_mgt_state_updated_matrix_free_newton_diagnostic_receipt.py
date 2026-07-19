#!/usr/bin/env python3
"""Build the actual-MGT state-updated matrix-free Newton diagnostic receipt."""

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
PHASE1_ROOT = ROOT / "implementation" / "phase1"
for candidate in (SCRIPT_DIR, SRC_ROOT, PHASE1_ROOT):
    candidate_text = str(candidate)
    while candidate_text in sys.path:
        sys.path.remove(candidate_text)
    sys.path.insert(0, candidate_text)

from g1_mgt_load_coupled_arc_length_adapter import (  # noqa: E402
    MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT,
    build_real_mgt_load_coupled_arc_length_problem,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE,
    MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
    MatrixFreeCPUFGMRESConfig,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
)
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_relaxed_checkpoints/"
    "accepted_load_0p656.npz"
)
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION / "g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_state_updated_matrix_free_newton_diagnostic_v1.schema.json"
)
SCHEMA_VERSION = "g1-mgt-state-updated-matrix-free-newton-diagnostic-receipt.v1"
CASE_ID = "g1_real_mgt_state_updated_matrix_free_newton_diagnostic"
LOAD_FACTOR = 1.0
RESIDUAL_GATE_KN = 5.0e-7
MAXIMUM_NEWTON_ATTEMPTS = 2
CLAIM_BOUNDARY = (
    "This receipt starts from the actual-MGT full-unit zero-state linear "
    "predictor and evaluates at most two full Newton corrections at lambda=1. "
    "Each tangent system uses the analytic current-state action and a fixed "
    "zero-state CSR LU only as a right preconditioner, with independent raw "
    "tangent-residual replay. Both systems bind the same free-equation order, "
    "residual formula, reference load, current-tangent action, and reference "
    "preconditioner hashes, and use the ordered Python-fsum host recurrence. "
    "Operator formulas and parent arrays are hash-bound, while backend parity "
    "and SciPy SuperLU outputs remain outside that arithmetic contract. "
    "Cancellation-stable finite-chord extension, "
    "correction, and tangent formulas let both full steps descend and the "
    "second in-memory diagnostic state passes the local residual gate. "
    "This is not globalized continuation, a persisted load-1 checkpoint, a "
    "production Krylov/HIP result, a full corotational/material model, or G1 "
    "closure."
)


def _config() -> MatrixFreeCPUFGMRESConfig:
    return MatrixFreeCPUFGMRESConfig(
        max_iterations=30,
        restart_length=15,
        relative_tolerance_l2=1.0e-6,
        absolute_tolerance_l2_kn=1.0e-10,
        explicit_residual_tolerance_inf_kn=RESIDUAL_GATE_KN,
    )


def _json_text(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _label(repo_root: Path, path: Path) -> str:
    absolute = _resolve(repo_root, path).resolve()
    try:
        return absolute.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _input_paths(*, mgt_path: Path, checkpoint_npz: Path) -> list[Path]:
    return [
        mgt_path,
        checkpoint_npz,
        Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
        Path("implementation/phase1/mgt_frame_force_based_assembly.py"),
        Path("implementation/phase1/mgt_physical_residual_assembly.py"),
        Path("implementation/phase1/mgt_semantic_load_assembly.py"),
        Path("implementation/phase1/mgt_state_updated_frame_axial_geometry.py"),
        Path("implementation/phase1/parse_mgt_section_material_properties.py"),
        Path("implementation/phase1/parse_midas_mgt_to_json_npz.py"),
        Path("src/structural_analysis/solvers/nonlinear/matrix_free_fgmres.py"),
        Path("src/structural_analysis/engine_v2/contracts/_canonical.py"),
        Path("src/structural_analysis/engine_v2/contracts/current_tangent_operator.py"),
        Path("src/structural_analysis/schemas/current_tangent_operator_v1.schema.json"),
        SCHEMA_PATH,
        Path(
            "scripts/"
            "build_g1_mgt_state_updated_matrix_free_newton_"
            "diagnostic_receipt.py"
        ),
        Path("tests/test_matrix_free_cpu_fgmres_state_tangent.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path(
            "tests/"
            "test_build_g1_mgt_state_updated_matrix_free_newton_"
            "diagnostic_receipt.py"
        ),
    ]


def _attempt(
    *,
    problem: Any,
    solver: Any,
    accepted_state_m: np.ndarray,
    attempt_index: int,
) -> tuple[dict[str, Any], np.ndarray, bool]:
    state_before = np.ascontiguousarray(accepted_state_m, dtype=np.float64)
    state_before_bytes = memoryview(state_before).cast("B").tobytes()
    residual_before = problem.residual_kn(state_before, LOAD_FACTOR)
    before_inf = float(np.linalg.norm(residual_before, ord=np.inf))
    before_l2 = float(np.linalg.norm(residual_before))
    tangent_solve = solver.solve_at_state(
        problem,
        state_before,
        -residual_before,
        load_factor=LOAD_FACTOR,
        solve_id=f"actual-mgt-full-load-newton-{attempt_index}",
    )
    correction = np.asarray(
        tangent_solve.solution_free,
        dtype=np.float64,
    )
    trial_state = np.ascontiguousarray(
        state_before + correction,
        dtype=np.float64,
    )
    trial_residual = problem.residual_kn(trial_state, LOAD_FACTOR)
    trial_inf = float(np.linalg.norm(trial_residual, ord=np.inf))
    trial_l2 = float(np.linalg.norm(trial_residual))
    residual_descent = bool(trial_inf < before_inf)
    accepted = bool(tangent_solve.contract_pass and residual_descent)
    if accepted:
        state_after = trial_state.copy()
        rejection_reason = None
        rollback_exercised = False
        rollback_byte_exact = False
    else:
        state_after = state_before.copy()
        rejection_reason = (
            "tangent_solve_contract_failed"
            if not tangent_solve.contract_pass
            else "full_step_nonlinear_residual_not_descending"
        )
        rollback_exercised = True
        rollback_byte_exact = bool(
            memoryview(state_after).cast("B").tobytes() == state_before_bytes
        )
    after_residual = problem.residual_kn(state_after, LOAD_FACTOR)
    accepted_after_inf = float(np.linalg.norm(after_residual, ord=np.inf))
    accepted_after_l2 = float(np.linalg.norm(after_residual))
    row = {
        "attempt_index": attempt_index,
        "accepted": accepted,
        "rejection_reason": rejection_reason,
        "state_before_data_hash": array_data_hash(state_before),
        "trial_state_data_hash": array_data_hash(trial_state),
        "state_after_data_hash": array_data_hash(state_after),
        "before_residual_inf_kn": before_inf,
        "before_residual_l2_kn": before_l2,
        "trial_residual_inf_kn": trial_inf,
        "trial_residual_l2_kn": trial_l2,
        "accepted_after_residual_inf_kn": accepted_after_inf,
        "accepted_after_residual_l2_kn": accepted_after_l2,
        "residual_descent": residual_descent,
        "trial_residual_reduction_factor_inf": before_inf / trial_inf,
        "correction_inf_m": float(np.linalg.norm(correction, ord=np.inf)),
        "relative_correction_inf": float(
            np.linalg.norm(correction, ord=np.inf)
            / max(np.linalg.norm(trial_state, ord=np.inf), 1.0e-300)
        ),
        "trial_residual_gate_passed": bool(trial_inf <= RESIDUAL_GATE_KN),
        "rollback_exercised": rollback_exercised,
        "rollback_byte_exact": rollback_byte_exact,
        "tangent_solve": tangent_solve.receipt,
    }
    return row, state_after, accepted


def build_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_mgt = _resolve(repo_root, mgt_path)
    resolved_checkpoint = _resolve(repo_root, checkpoint_npz)
    problem, adapter_metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=resolved_mgt,
        roundtrip_npz=None,
        checkpoint_npz=resolved_checkpoint,
        apply_state_updated_frame_axial_geometry=True,
    )
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )
    initial_state = np.ascontiguousarray(
        problem.full_unit_zero_state_predictor_free_m(),
        dtype=np.float64,
    )
    initial_residual = problem.residual_kn(initial_state, LOAD_FACTOR)
    initial_inf = float(np.linalg.norm(initial_residual, ord=np.inf))
    initial_l2 = float(np.linalg.norm(initial_residual))
    accepted_state = initial_state.copy()
    attempts: list[dict[str, Any]] = []
    for attempt_index in range(1, MAXIMUM_NEWTON_ATTEMPTS + 1):
        row, accepted_state, accepted = _attempt(
            problem=problem,
            solver=solver,
            accepted_state_m=accepted_state,
            attempt_index=attempt_index,
        )
        attempts.append(row)
        if not accepted:
            break
    final_residual = problem.residual_kn(accepted_state, LOAD_FACTOR)
    final_inf = float(np.linalg.norm(final_residual, ord=np.inf))
    final_l2 = float(np.linalg.norm(final_residual))
    residual_gate_passed = bool(final_inf <= RESIDUAL_GATE_KN)
    geometry = adapter_metadata["state_updated_frame_axial_geometry"]
    semantic = adapter_metadata["semantic_load_assembly"]
    coverage = adapter_metadata["frame_source_property_coverage_audit"]
    alias_audit = adapter_metadata["dgn_material_property_alias_audit"]
    preconditioner = adapter_metadata["reference_preconditioner_contract"]
    residual_contract = adapter_metadata["residual_evaluation_contract"]
    residual_parent_audit = adapter_metadata["residual_parent_equivalence_audit"]
    first = attempts[0] if attempts else None
    second = attempts[1] if len(attempts) > 1 else None
    tangent_receipts = [row["tangent_solve"] for row in attempts]
    contract_pass = bool(
        problem.equation_count == 70_560
        and semantic["actual_mgt_semantic_load_target_consumed"]
        and semantic["target_name"] == "LIVE"
        and coverage["exact_source_property_coverage"]
        and alias_audit["contract_pass"]
        and alias_audit["engineer_review_required"]
        and geometry["state_updated_frame_axial_geometry_applied"]
        and geometry["connected_to_physical_residual"]
        and geometry["connected_to_consistent_state_tangent_action"]
        and geometry["consistent_state_tangent_action_mode"]
        == "analytic_reference_plus_exact_finite_chord_axial_correction"
        and geometry["finite_chord_extension_evaluation"]
        == "difference_of_squares_cancellation_stable"
        and geometry["finite_chord_correction_evaluation"]
        == "second_order_decomposition_cancellation_stable"
        and residual_contract["mode"]
        == ("reference_csr_plus_load_frame_delta_plus_finite_chord_correction")
        and residual_contract["reference_csr_parent_matches_analytic_tangent"]
        and residual_contract["load_frame_delta_parent_matches_analytic_tangent"]
        and residual_contract["finite_chord_correction_parent_matches_analytic_tangent"]
        and residual_contract["residual_formula_hash"]
        == canonical_hash(residual_contract["residual_formula"])
        and residual_parent_audit["contract_pass"]
        and residual_parent_audit["parent_component_gate_passed"]
        and residual_parent_audit["parent_repeat_bytes_exact"]
        and preconditioner["available"]
        and preconditioner["intended_use"] == "fixed_right_preconditioner"
        and preconditioner["approximate_for_state_dependent_adapter"]
        and len(attempts) == 2
        and first is not None
        and first["accepted"]
        and first["residual_descent"]
        and second is not None
        and second["accepted"]
        and second["residual_descent"]
        and second["trial_residual_gate_passed"]
        and not second["rollback_exercised"]
        and not second["rollback_byte_exact"]
        and all(row["contract_pass"] for row in tangent_receipts)
        and all(row["fallback_count"] == 0 for row in tangent_receipts)
        and all(row["regularization_count"] == 0 for row in tangent_receipts)
        and all(row["operator_binding_ready"] for row in tangent_receipts)
        and len({row["operator_binding"]["binding_hash"] for row in tangent_receipts})
        == 1
        and all(
            row["operator_binding"]["free_equation_order_data_hash"]
            == adapter_metadata["free_dof_hash"]
            and row["operator_binding"]["residual_formula_hash"]
            == residual_contract["residual_formula_hash"]
            and row["operator_binding"]["reference_load_free_n_data_hash"]
            == adapter_metadata["reference_load_free_hash"]
            and row["operator_binding"]["current_tangent_action_contract"]
            == MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
            and row["operator_binding"]["current_tangent_operator_profile"]
            == "reference_csr_load_frame_delta_finite_chord_axial.v1"
            and row["deterministic_host_recurrence_arithmetic_claim"]
            and row["recurrence"]["profile"]
            == MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE
            and row["recurrence"]["accumulation_profile"]
            == MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE
            and row["recurrence"]["operator_callback_outputs_in_contract"]
            and not row["recurrence"]["preconditioner_callback_outputs_in_contract"]
            and not row["cross_platform_deterministic_recurrence_claim"]
            for row in tangent_receipts
        )
        and final_inf < initial_inf
        and residual_gate_passed
    )
    claims = {
        "actual_mgt_semantic_live_load_consumed": True,
        "exact_source_derived_alias_frame_property_coverage": bool(
            coverage["exact_source_property_coverage"]
        ),
        "dgn_alias_engineer_review_required": bool(
            alias_audit["engineer_review_required"]
        ),
        "analytic_current_state_tangent_action": True,
        "fixed_zero_state_csr_right_preconditioner": True,
        "local_cpu_matrix_free_state_tangent_diagnostic": True,
        "all_tangent_solves_operator_bound": bool(
            tangent_receipts
            and all(row["operator_binding_ready"] for row in tangent_receipts)
        ),
        "all_tangent_solves_deterministic_host_arithmetic": bool(
            tangent_receipts
            and all(
                row["deterministic_host_recurrence_arithmetic_claim"]
                for row in tangent_receipts
            )
        ),
        "all_tangent_operator_formula_parent_arrays_bound": bool(
            tangent_receipts
            and all(
                row["recurrence"]["operator_callback_outputs_in_contract"]
                for row in tangent_receipts
            )
        ),
        "explicit_tangent_residual_replay": True,
        "cancellation_stable_finite_chord_evaluation": True,
        "residual_parent_operator_matches_analytic_tangent": True,
        "residual_formula_hash_verified": bool(
            residual_contract["residual_formula_hash"]
            == canonical_hash(residual_contract["residual_formula"])
        ),
        "first_full_newton_step_residual_descent": bool(first and first["accepted"]),
        "second_full_newton_step_residual_descent": bool(
            second and second["accepted"] and second["residual_descent"]
        ),
        "full_load_residual_gate_passed": residual_gate_passed,
        "globalized_newton": False,
        "full_nonlinear_continuation": False,
        "persisted_load_1p0_checkpoint": False,
        "full_corotational_frame": False,
        "material_state_commit_rollback": False,
        "production_matrix_free_state_tangent_krylov": False,
        "cross_platform_deterministic_recurrence": False,
        "production_rocm_hip_nonlinear_parity": False,
        "g1_full_building_closure": False,
    }
    blockers = [
        "dgn_exact_type_name_material_inheritance_engineer_review_required",
        "full_corotational_frame_not_implemented",
        "material_state_commit_rollback_not_connected",
        "full_nonlinear_continuation_not_executed",
        "persisted_semantic_live_load_1p0_checkpoint_not_created",
        "production_matrix_free_state_tangent_krylov_not_executed",
        "end_to_end_preconditioner_determinism_not_verified",
        "production_rocm_hip_nonlinear_parity_not_verified",
        "g1_full_building_closure_not_established",
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "readiness_pass": False,
        "evidence_closure_pass": False,
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "source_commit_exact_replay_claim": False,
        "source_tree_state": "working_tree_with_uncommitted_goal_changes",
        "input_checksums": input_checksums(
            _input_paths(
                mgt_path=mgt_path,
                checkpoint_npz=checkpoint_npz,
            ),
            repo_root=repo_root,
        ),
        "case_id": CASE_ID,
        "inputs": {
            "mgt_path": _label(repo_root, mgt_path),
            "mgt_sha256": file_sha256(resolved_mgt),
            "operator_checkpoint": _label(repo_root, checkpoint_npz),
            "operator_checkpoint_sha256": file_sha256(resolved_checkpoint),
            "initial_state_policy": "full_unit_zero_state_linear_predictor",
            "load_factor": LOAD_FACTOR,
            "free_equation_count": problem.equation_count,
            "initial_state_data_hash": array_data_hash(initial_state),
        },
        "adapter_binding": {
            "actual_mgt_semantic_live_target_consumed": bool(
                semantic["actual_mgt_semantic_load_target_consumed"]
            ),
            "semantic_target_name": semantic["target_name"],
            "frame_element_count": coverage["frame_element_count"],
            "exact_frame_source_property_coverage": coverage[
                "exact_source_property_coverage"
            ],
            "dgn_alias_contract_pass": alias_audit["contract_pass"],
            "dgn_alias_engineer_review_required": alias_audit[
                "engineer_review_required"
            ],
            "state_updated_frame_axial_geometry": geometry,
            "residual_evaluation_contract": residual_contract,
            "residual_parent_equivalence_audit": residual_parent_audit,
            "reference_preconditioner_contract": preconditioner,
        },
        "solver_binding": {
            "profile": solver.profile,
            "contract_hash": solver.contract_hash,
            "reference_preconditioner_contract": (
                solver.reference_preconditioner_contract
            ),
            "reference_preconditioner_pattern_hash": (
                solver.reference_preconditioner_pattern_hash
            ),
            "reference_preconditioner_values_hash": (
                solver.reference_preconditioner_values_hash
            ),
            "operator_binding": dict(solver.operator_binding),
            "recurrence_profile": MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
            "accumulation_profile": (MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE),
            "deterministic_host_recurrence_arithmetic": True,
            "operator_callback_formula_parent_arrays_bound": True,
            "cross_platform_end_to_end_deterministic_claim": False,
            "config": solver.config.contract_payload(),
        },
        "newton_attempts": attempts,
        "metrics": {
            "maximum_newton_attempts": MAXIMUM_NEWTON_ATTEMPTS,
            "attempt_count": len(attempts),
            "accepted_attempt_count": sum(1 for row in attempts if row["accepted"]),
            "rejected_attempt_count": sum(1 for row in attempts if not row["accepted"]),
            "initial_residual_inf_kn": initial_inf,
            "initial_residual_l2_kn": initial_l2,
            "final_accepted_residual_inf_kn": final_inf,
            "final_accepted_residual_l2_kn": final_l2,
            "residual_gate_kn": RESIDUAL_GATE_KN,
            "residual_gate_passed": residual_gate_passed,
            "accepted_residual_reduction_factor_inf": initial_inf / final_inf,
            "final_accepted_state_data_hash": array_data_hash(accepted_state),
            "total_tangent_iteration_count": sum(
                row["iteration_count"] for row in tangent_receipts
            ),
            "total_tangent_operator_action_count": sum(
                row["operator_action_count"] for row in tangent_receipts
            ),
            "maximum_tangent_explicit_residual_inf_kn": max(
                row["explicit_residual_inf_kn"] for row in tangent_receipts
            ),
            "fallback_count": 0,
            "regularization_count": 0,
            "line_search_executed": False,
        },
        "claims": claims,
        "blockers_remaining": blockers,
        "artifacts": {
            "receipt": _label(repo_root, receipt_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    return payload


def check_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
) -> tuple[bool, str]:
    target = _resolve(repo_root, receipt_out)
    if not target.is_file():
        return False, "g1_mgt_state_updated_matrix_free_newton_missing"
    expected = build_receipt(
        repo_root=repo_root,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        receipt_out=receipt_out,
    )
    try:
        existing = _read_json(target)
    except Exception as exc:
        return False, (
            "g1_mgt_state_updated_matrix_free_newton_unreadable:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_mgt_state_updated_matrix_free_newton_mismatch"
    return True, "g1_mgt_state_updated_matrix_free_newton_consistent"


def write_receipt(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    receipt_out = Path(kwargs.get("receipt_out", DEFAULT_RECEIPT_OUT))
    payload = build_receipt(**kwargs)
    target = _resolve(repo_root, receipt_out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    kwargs = {
        "repo_root": args.repo_root,
        "mgt_path": args.mgt,
        "checkpoint_npz": args.checkpoint,
        "receipt_out": args.receipt_out,
    }
    if args.check:
        passed, reason = check_receipt(**kwargs)
        print(reason)
        return 0 if passed else 1
    payload = write_receipt(**kwargs)
    metrics = payload["metrics"]
    print(
        f"{payload['status']} | equations="
        f"{payload['inputs']['free_equation_count']} | attempts="
        f"{metrics['accepted_attempt_count']}/"
        f"{metrics['rejected_attempt_count']} | residual_n="
        f"{metrics['final_accepted_residual_inf_kn'] * 1000.0:.12g} | "
        "g1_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
