#!/usr/bin/env python3
"""Build the actual-MGT state-updated matrix-free Newton path receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
    commit_bound_input_metadata,
    engine_version,
    file_sha256,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (  # noqa: E402
    AdaptiveLoadControlledMatrixFreeNewtonConfig,
    LoadControlledMatrixFreeNewtonConfig,
    adaptive_load_controlled_matrix_free_newton_continuation,
    load_controlled_matrix_free_newton_continuation,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE,
    MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
    MATRIX_FREE_CPU_FGMRES_SCHEMA_VERSION,
    MatrixFreeCPUFGMRESConfig,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path(
    "implementation/phase1/open_data/midas/"
    "midas_generator_33.optimized.mgt"
)
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION
    / "mgt_uncoarsened_boundary_pdelta_relaxed_checkpoints/"
    "accepted_load_0p656.npz"
)
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION
    / "g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.json"
)
DEFAULT_FINAL_VECTOR_OUT = (
    PRODUCTIZATION
    / "g1_mgt_state_updated_frame_axial_live_load_1p0_diagnostic_"
    "free_displacement.f64le"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_v1.schema.json"
)
SCHEMA_VERSION = (
    "g1-mgt-state-updated-frame-axial-matrix-free-newton-continuation-receipt.v1"
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


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
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _matrix_free_solve_receipts(payload: Any) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("schema_version") == MATRIX_FREE_CPU_FGMRES_SCHEMA_VERSION:
                receipts.append(value)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return receipts


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
        Path(
            "implementation/phase1/"
            "mgt_state_updated_frame_axial_geometry.py"
        ),
        Path("implementation/phase1/parse_mgt_section_material_properties.py"),
        Path("implementation/phase1/parse_midas_mgt_to_json_npz.py"),
        Path(
            "src/structural_analysis/solvers/nonlinear/"
            "matrix_free_fgmres.py"
        ),
        Path(
            "src/structural_analysis/solvers/nonlinear/"
            "load_controlled_matrix_free_newton.py"
        ),
        Path("src/structural_analysis/engine_v2/contracts/_canonical.py"),
        Path(
            "src/structural_analysis/engine_v2/contracts/"
            "current_tangent_operator.py"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "current_tangent_operator_v1.schema.json"
        ),
        SCHEMA_PATH,
        Path(
            "scripts/"
            "build_g1_mgt_state_updated_frame_axial_matrix_free_newton_"
            "continuation_receipt.py"
        ),
        Path("tests/test_matrix_free_cpu_fgmres_state_tangent.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path("tests/test_load_controlled_matrix_free_newton.py"),
        Path(
            "tests/"
            "test_build_g1_mgt_state_updated_frame_axial_matrix_free_newton_"
            "continuation_receipt.py"
        ),
    ]


def _linear_solver_config() -> MatrixFreeCPUFGMRESConfig:
    return MatrixFreeCPUFGMRESConfig(
        max_iterations=12,
        restart_length=8,
        relative_tolerance_l2=1.0e-8,
        absolute_tolerance_l2_kn=1.0e-10,
        explicit_residual_tolerance_inf_kn=1.0e-7,
    )


def _continuation_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(0.25, 0.5, 0.75, 1.0),
        residual_tolerance_inf_kn=5.0e-7,
        increment_absolute_tolerance_inf_m=1.0e-10,
        increment_relative_tolerance=1.0e-4,
        tangent_solve_residual_tolerance_inf_kn=1.0e-7,
        maximum_newton_iterations=4,
        maximum_line_search_backtracks=6,
        line_search_reduction=0.5,
        minimum_line_search_alpha=1.0 / 64.0,
    )


def _strict_g1_gate_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=5.0e-7,
        increment_absolute_tolerance_inf_m=1.0e-10,
        increment_relative_tolerance=1.0e-4,
        tangent_solve_residual_tolerance_inf_kn=1.0e-7,
        maximum_newton_iterations=4,
        maximum_line_search_backtracks=6,
        line_search_reduction=0.5,
        minimum_line_search_alpha=1.0 / 64.0,
    )


def _iteration_limited_rollback_config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(1.0,),
        residual_tolerance_inf_kn=5.0e-7,
        increment_absolute_tolerance_inf_m=1.0e-10,
        increment_relative_tolerance=1.0e-4,
        tangent_solve_residual_tolerance_inf_kn=1.0e-7,
        maximum_newton_iterations=1,
        maximum_line_search_backtracks=6,
        line_search_reduction=0.5,
        minimum_line_search_alpha=1.0 / 64.0,
    )


def _adaptive_continuation_config() -> AdaptiveLoadControlledMatrixFreeNewtonConfig:
    return AdaptiveLoadControlledMatrixFreeNewtonConfig(
        target_load_factor=1.0,
        initial_step_size=1.0,
        minimum_step_size=0.125,
        maximum_step_size=1.0,
        failed_step_reduction=0.5,
        fast_step_growth=2.0,
        fast_newton_solve_threshold=1,
        maximum_attempt_count=16,
        step_config=_iteration_limited_rollback_config(),
    )


def _vector_artifact(
    *,
    repo_root: Path,
    path: Path,
    values: np.ndarray,
    load_factor: float,
    residual_inf_n: float,
) -> tuple[dict[str, Any], bytes]:
    canonical = np.ascontiguousarray(values, dtype="<f8")
    raw = memoryview(canonical).cast("B").tobytes()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return {
        "schema_version": (
            "g1-mgt-state-updated-frame-axial-live-load-1p0-"
            "diagnostic-vector.v1"
        ),
        "status": "ready",
        "artifact_path": _label(repo_root, path),
        "dtype": "<f8",
        "layout": "C",
        "byte_order": "little",
        "equation_order": "adapter_free_global_dof_order",
        "equation_count": int(canonical.size),
        "byte_length": int(len(raw)),
        "data_sha256": digest,
        "data_hash": array_data_hash(canonical),
        "load_factor": float(load_factor),
        "residual_inf_n": float(residual_inf_n),
        "local_residual_tolerance_n": 0.0005,
        "local_residual_gate_passed": bool(residual_inf_n <= 0.0005),
        "accepted_displacement_checkpoint": True,
        "engineer_review_required": True,
        "full_corotational_frame_checkpoint_claim": False,
        "production_solver_checkpoint_claim": False,
        "g1_full_load_checkpoint_claim": False,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This binary64 vector is the accepted displacement checkpoint of "
            "the diagnostic finite-chord axial load-controlled path and passes "
            "the local 0.0005 N residual gate. It depends on engineer-review-"
            "required DGN identity aliases and a reference-geometry bending/"
            "torsion model. It is not a production, full-corotational, HIP, or "
            "authoritative G1 checkpoint."
        ),
    }, raw


def _local_quadratic_convergence_audit(
    *,
    problem: Any,
    solver: Any,
    reference_state_m: np.ndarray,
    reference_residual_inf_n: float,
) -> dict[str, Any]:
    predictor = np.asarray(
        problem.full_unit_zero_state_predictor_free_m(),
        dtype=np.float64,
    )
    predictor_inf_m = float(np.linalg.norm(predictor, ord=np.inf))
    if not math.isfinite(predictor_inf_m) or predictor_inf_m <= 0.0:
        raise ValueError("quadratic audit predictor direction is invalid")
    direction = predictor / predictor_inf_m
    rows: list[dict[str, Any]] = []
    observed_orders: list[float] = []
    for probe_index, perturbation_m in enumerate(
        (4.0e-6, 2.0e-6, 1.0e-6),
        start=1,
    ):
        state = np.asarray(reference_state_m, dtype=np.float64) + (
            perturbation_m * direction
        )
        residual_before_kn = np.asarray(
            problem.residual_kn(state, 1.0),
            dtype=np.float64,
        )
        right_hand_side_kn = -residual_before_kn
        solve = solver.solve_at_state(
            problem,
            state,
            right_hand_side_kn,
            load_factor=1.0,
            solve_id=f"actual-local-quadratic-probe-{probe_index}",
        )
        correction_m = np.asarray(solve.solution_free, dtype=np.float64)
        independent_linear_residual_kn = np.asarray(
            problem.consistent_state_tangent_action_kn_per_m(
                state,
                1.0,
                correction_m,
            )
            - right_hand_side_kn,
            dtype=np.float64,
        )
        corrected_state_m = state + correction_m
        residual_after_kn = np.asarray(
            problem.residual_kn(corrected_state_m, 1.0),
            dtype=np.float64,
        )
        residual_before_inf_n = float(
            np.linalg.norm(residual_before_kn, ord=np.inf) * 1000.0
        )
        residual_after_inf_n = float(
            np.linalg.norm(residual_after_kn, ord=np.inf) * 1000.0
        )
        observed_order: float | None = None
        if rows:
            previous = rows[-1]
            observed_order = math.log(
                residual_after_inf_n
                / float(previous["residual_after_inf_n"])
            ) / math.log(
                perturbation_m / float(previous["perturbation_inf_m"])
            )
            observed_orders.append(observed_order)
        rows.append(
            {
                "probe_index": probe_index,
                "perturbation_inf_m": perturbation_m,
                "state_data_hash": array_data_hash(state),
                "residual_before_data_hash": array_data_hash(
                    residual_before_kn
                ),
                "residual_before_inf_n": residual_before_inf_n,
                "correction_data_hash": array_data_hash(correction_m),
                "correction_inf_m": float(
                    np.linalg.norm(correction_m, ord=np.inf)
                ),
                "independent_linear_residual_inf_kn": float(
                    np.linalg.norm(
                        independent_linear_residual_kn,
                        ord=np.inf,
                    )
                ),
                "corrected_state_data_hash": array_data_hash(
                    corrected_state_m
                ),
                "corrected_state_reference_difference_inf_m": float(
                    np.linalg.norm(
                        corrected_state_m - reference_state_m,
                        ord=np.inf,
                    )
                ),
                "residual_after_data_hash": array_data_hash(
                    residual_after_kn
                ),
                "residual_after_inf_n": residual_after_inf_n,
                "residual_after_over_perturbation_squared_n_per_m2": (
                    residual_after_inf_n / perturbation_m**2
                ),
                "residual_descent": bool(
                    residual_after_inf_n < residual_before_inf_n
                ),
                "observed_order_from_previous": observed_order,
                "tangent_solve": dict(solve.receipt),
            }
        )
    normalized_coefficients = [
        float(
            row[
                "residual_after_over_perturbation_squared_n_per_m2"
            ]
        )
        for row in rows
    ]
    coefficient_relative_spread = (
        (max(normalized_coefficients) - min(normalized_coefficients))
        / max(normalized_coefficients)
    )
    minimum_order = min(observed_orders)
    maximum_order = max(observed_orders)
    contract_pass = bool(
        reference_residual_inf_n <= 0.0005
        and len(rows) == 3
        and len(observed_orders) == 2
        and minimum_order >= 1.95
        and maximum_order <= 2.05
        and coefficient_relative_spread <= 1.0e-3
        and all(bool(row["residual_descent"]) for row in rows)
        and all(
            float(row["independent_linear_residual_inf_kn"])
            <= 1.0e-7
            for row in rows
        )
        and all(bool(row["tangent_solve"]["contract_pass"]) for row in rows)
        and all(
            int(row["tangent_solve"]["fallback_count"]) == 0
            and int(row["tangent_solve"]["regularization_count"]) == 0
            for row in rows
        )
    )
    return {
        "schema_version": (
            "g1-mgt-state-updated-frame-axial-local-quadratic-"
            "convergence-audit.v1"
        ),
        "status": "ready" if contract_pass else "blocked",
        "reference_load_factor": 1.0,
        "reference_state_data_hash": array_data_hash(reference_state_m),
        "reference_residual_inf_n": reference_residual_inf_n,
        "perturbation_direction": (
            "full_unit_zero_state_predictor_normalized_by_infinity_norm"
        ),
        "perturbation_direction_data_hash": array_data_hash(direction),
        "perturbation_inf_m": [4.0e-6, 2.0e-6, 1.0e-6],
        "rows": rows,
        "minimum_observed_order": minimum_order,
        "maximum_observed_order": maximum_order,
        "quadratic_order_lower_gate": 1.95,
        "quadratic_order_upper_gate": 2.05,
        "normalized_coefficient_relative_spread": (
            coefficient_relative_spread
        ),
        "normalized_coefficient_relative_spread_gate": 1.0e-3,
        "fallback_count": sum(
            int(row["tangent_solve"]["fallback_count"]) for row in rows
        ),
        "regularization_count": sum(
            int(row["tangent_solve"]["regularization_count"])
            for row in rows
        ),
        "contract_pass": contract_pass,
        "local_directional_quadratic_convergence_claim": contract_pass,
        "global_quadratic_convergence_claim": False,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "Three actual-model perturbations along one normalized predictor "
            "direction are halved, and one full analytic-current-tangent "
            "Newton correction is applied at each state. The corrected "
            "residual scales quadratically within the stated order and "
            "coefficient gates. This is a local directional test, not global "
            "quadratic convergence, full-corotational/material closure, "
            "production/HIP evidence, or G1 closure."
        ),
    }


def build_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    final_vector_out: Path = DEFAULT_FINAL_VECTOR_OUT,
    _write_final_vector: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_mgt = _resolve(repo_root, mgt_path)
    resolved_checkpoint = _resolve(repo_root, checkpoint_npz)
    source_metadata = commit_bound_input_metadata(
        _input_paths(
            mgt_path=mgt_path,
            checkpoint_npz=checkpoint_npz,
        ),
        repo_root=repo_root,
    )
    source_provenance = source_metadata["source_input_provenance"]
    source_exact = bool(source_provenance["contract_pass"])
    source_commit_sha = str(source_metadata["source_commit_sha"])
    historical_problem, metadata = (
        build_real_mgt_load_coupled_arc_length_problem(
            mgt_path=resolved_mgt,
            roundtrip_npz=None,
            checkpoint_npz=resolved_checkpoint,
            apply_state_updated_frame_axial_geometry=True,
            source_commit_sha=(source_commit_sha if source_exact else "unavailable"),
        )
    )
    problem = historical_problem.zero_state_problem()
    linear_config = _linear_solver_config()
    continuation_config = _continuation_config()
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=linear_config,
    )
    one_shot = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=continuation_config,
    )
    midpoint_rows = [
        row for row in one_shot.checkpoints if row.load_factor == 0.5
    ]
    if len(midpoint_rows) != 1:
        raise ValueError("one-shot path lacks a unique load-0.5 checkpoint")
    midpoint = midpoint_rows[0]
    restarted = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=continuation_config,
        checkpoint=midpoint,
    )
    strict_gate_config = _strict_g1_gate_config()
    strict_gate = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=strict_gate_config,
    )
    rollback_config = _iteration_limited_rollback_config()
    rollback_probe = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=rollback_config,
    )
    adaptive_config = _adaptive_continuation_config()
    adaptive = adaptive_load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=adaptive_config,
    )
    adaptive_midpoint_rows = [
        row for row in adaptive.checkpoints if row.load_factor == 0.5
    ]
    if len(adaptive_midpoint_rows) != 1:
        raise ValueError("adaptive path lacks a unique load-0.5 checkpoint")
    adaptive_midpoint = adaptive_midpoint_rows[0]
    adaptive_restarted = (
        adaptive_load_controlled_matrix_free_newton_continuation(
            problem,
            solver,
            config=adaptive_config,
            checkpoint=adaptive_midpoint,
        )
    )
    final_vectors_exact = bool(
        np.array_equal(
            one_shot.final_free_displacements_m,
            restarted.final_free_displacements_m,
        )
    )
    final_state_hash_exact = bool(
        one_shot.final_checkpoint.state_hash
        == restarted.final_checkpoint.state_hash
    )
    final_data_hash_exact = bool(
        array_data_hash(one_shot.final_free_displacements_m)
        == array_data_hash(restarted.final_free_displacements_m)
    )
    restart_contract_pass = bool(
        restarted.status == "ready"
        and restarted.metrics["contract_pass"]
        and restarted.metrics["restart_checkpoint_consumed"]
        and restarted.initial_checkpoint.state_hash == midpoint.state_hash
        and final_vectors_exact
        and final_state_hash_exact
        and final_data_hash_exact
    )
    if len(strict_gate.attempts) != 1:
        raise ValueError("strict-gate probe lacks one full-load attempt")
    strict_gate_attempt = strict_gate.attempts[0]
    strict_gate_residual_inf_n = float(
        strict_gate.metrics["final_residual_inf_kn"] * 1000.0
    )
    strict_gate_contract_pass = bool(
        strict_gate.status == "ready"
        and strict_gate.terminal_reason == "target_load_factor_reached"
        and strict_gate.metrics["contract_pass"]
        and strict_gate.metrics["target_load_factor_reached"]
        and strict_gate.metrics["accepted_step_count"] == 1
        and strict_gate.metrics["failed_step_count"] == 0
        and strict_gate.metrics["checkpoint_count"] == 2
        and strict_gate.metrics["tangent_solve_count"] == 2
        and strict_gate.metrics["fallback_count"] == 0
        and strict_gate.metrics["regularization_count"] == 0
        and strict_gate.metrics["residual_and_increment_acceptance_gate"]
        and strict_gate_residual_inf_n <= 0.0005
        and strict_gate_attempt["accepted"]
        and not strict_gate_attempt["rollback_performed"]
        and strict_gate_attempt["rollback_exact"]
    )
    local_quadratic_convergence_audit = (
        _local_quadratic_convergence_audit(
            problem=problem,
            solver=solver,
            reference_state_m=strict_gate.final_free_displacements_m,
            reference_residual_inf_n=strict_gate_residual_inf_n,
        )
    )
    if len(rollback_probe.attempts) != 1:
        raise ValueError("iteration-limited probe lacks one failed attempt")
    rollback_attempt = rollback_probe.attempts[0]
    rejected_trial_residual_inf_n = float(
        rollback_attempt["history"][-1]["residual_inf_kn"] * 1000.0
    )
    rollback_contract_pass = bool(
        rollback_probe.status == "blocked"
        and rollback_probe.terminal_reason
        == "maximum_newton_iterations_exhausted"
        and not rollback_probe.metrics["contract_pass"]
        and not rollback_probe.metrics["target_load_factor_reached"]
        and rollback_probe.metrics["accepted_step_count"] == 0
        and rollback_probe.metrics["failed_step_count"] == 1
        and rollback_probe.metrics["checkpoint_count"] == 1
        and rollback_probe.metrics["tangent_solve_count"] == 1
        and rollback_probe.metrics["fallback_count"] == 0
        and rollback_probe.metrics["regularization_count"] == 0
        and rollback_probe.metrics["rollback_exact"]
        and not rollback_attempt["accepted"]
        and rollback_attempt["rollback_performed"]
        and rollback_attempt["rollback_exact"]
        and rollback_attempt["accepted_state_hash_before"]
        == rollback_attempt["accepted_state_hash_after"]
        and rollback_probe.initial_checkpoint.state_hash
        == rollback_probe.final_checkpoint.state_hash
        and rejected_trial_residual_inf_n > 0.0005
    )
    adaptive_final_vectors_exact = bool(
        np.array_equal(
            adaptive.final_free_displacements_m,
            adaptive_restarted.final_free_displacements_m,
        )
    )
    adaptive_final_state_hash_exact = bool(
        adaptive.final_checkpoint.state_hash
        == adaptive_restarted.final_checkpoint.state_hash
    )
    adaptive_final_data_hash_exact = bool(
        array_data_hash(adaptive.final_free_displacements_m)
        == array_data_hash(adaptive_restarted.final_free_displacements_m)
    )
    adaptive_attempt_targets = [
        float(row["target_load_factor"]) for row in adaptive.attempts
    ]
    adaptive_attempt_outcomes = [
        str(row["outcome"]) for row in adaptive.attempts
    ]
    adaptive_contract_pass = bool(
        adaptive.status == "ready"
        and adaptive.terminal_reason == "target_load_factor_reached"
        and adaptive.metrics["contract_pass"]
        and adaptive.metrics["target_load_factor_reached"]
        and adaptive.metrics["attempt_count"] == 5
        and adaptive.metrics["accepted_step_count"] == 3
        and adaptive.metrics["failed_step_count"] == 2
        and adaptive.metrics["failed_step_reduction_count"] == 2
        and adaptive.metrics["fast_step_growth_count"] == 2
        and adaptive.metrics["checkpoint_count"] == 4
        and adaptive.metrics["tangent_solve_count"] == 5
        and adaptive.metrics["fallback_count"] == 0
        and adaptive.metrics["regularization_count"] == 0
        and adaptive.metrics["rollback_exact"]
        and adaptive.metrics["residual_and_increment_acceptance_gate"]
        and adaptive.metrics["final_residual_inf_kn"]
        <= adaptive_config.step_config.residual_tolerance_inf_kn
        and adaptive_attempt_targets == [1.0, 0.5, 1.0, 0.75, 1.0]
        and adaptive_attempt_outcomes
        == [
            "rolled_back",
            "committed",
            "rolled_back",
            "committed",
            "committed",
        ]
        and all(
            bool(row["rollback_exact"])
            for row in adaptive.attempts
            if not bool(row["accepted"])
        )
        and adaptive_restarted.status == "ready"
        and adaptive_restarted.metrics["contract_pass"]
        and adaptive_restarted.metrics["restart_checkpoint_consumed"]
        and adaptive_restarted.initial_checkpoint.state_hash
        == adaptive_midpoint.state_hash
        and adaptive_final_vectors_exact
        and adaptive_final_state_hash_exact
        and adaptive_final_data_hash_exact
    )
    final_residual_inf_n = float(
        one_shot.metrics["final_residual_inf_kn"] * 1000.0
    )
    vector_artifact, vector_bytes = _vector_artifact(
        repo_root=repo_root,
        path=final_vector_out,
        values=one_shot.final_free_displacements_m,
        load_factor=one_shot.final_checkpoint.load_factor,
        residual_inf_n=final_residual_inf_n,
    )
    if _write_final_vector:
        target = _resolve(repo_root, final_vector_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(vector_bytes)
        if (
            target.stat().st_size != vector_artifact["byte_length"]
            or file_sha256(target) != vector_artifact["data_sha256"]
        ):
            raise ValueError("persisted final diagnostic vector mismatch")

    binding = metadata["material_analysis_property_binding"]
    coverage = metadata["frame_source_property_coverage_audit"]
    geometry = metadata["state_updated_frame_axial_geometry"]
    reference_preconditioner = metadata[
        "reference_preconditioner_contract"
    ]
    residual_contract = metadata["residual_evaluation_contract"]
    residual_parent_audit = metadata[
        "residual_parent_equivalence_audit"
    ]
    one_shot_payload = one_shot.to_dict()
    restarted_payload = restarted.to_dict()
    solve_receipts = _matrix_free_solve_receipts(
        [
            one_shot_payload,
            restarted_payload,
            strict_gate.to_dict(),
            rollback_probe.to_dict(),
            adaptive.to_dict(),
            adaptive_restarted.to_dict(),
            local_quadratic_convergence_audit,
        ]
    )
    operator_binding_hashes = sorted(
        {
            str(receipt["operator_binding"]["binding_hash"])
            for receipt in solve_receipts
            if receipt.get("operator_binding_ready")
        }
    )
    preconditioner_pattern_hashes = sorted(
        {
            str(receipt["preconditioner"]["pattern_hash"])
            for receipt in solve_receipts
        }
    )
    preconditioner_values_hashes = sorted(
        {
            str(receipt["preconditioner"]["numeric_values_hash"])
            for receipt in solve_receipts
        }
    )
    expected_solve_receipt_count = 20
    operator_recurrence_binding_contract_pass = bool(
        len(solve_receipts) == expected_solve_receipt_count
        and len(operator_binding_hashes) == 1
        and len(preconditioner_pattern_hashes) == 1
        and len(preconditioner_values_hashes) == 1
        and all(
            receipt["contract_pass"]
            and receipt["operator_binding_ready"]
            and receipt["operator_binding"]["status"] == "ready"
            and receipt["operator_binding"]["equation_count"]
            == metadata["free_equation_count"]
            and receipt["operator_binding"]["free_equation_order_data_hash"]
            == metadata["free_dof_hash"]
            and receipt["operator_binding"]["residual_formula_hash"]
            == residual_contract["residual_formula_hash"]
            and receipt["operator_binding"][
                "reference_load_free_n_data_hash"
            ]
            == metadata["reference_load_free_hash"]
            and receipt["operator_binding"]["current_tangent_action_contract"]
            == MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
            and receipt["operator_binding"]["current_tangent_operator_profile"]
            == "reference_csr_load_frame_delta_finite_chord_axial.v1"
            and receipt["deterministic_host_recurrence_arithmetic_claim"]
            and receipt["recurrence"]["profile"]
            == MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE
            and receipt["recurrence"]["accumulation_profile"]
            == MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE
            and receipt["recurrence"]["deterministic_host_arithmetic"]
            and receipt["recurrence"][
                "operator_callback_outputs_in_contract"
            ]
            and not receipt["recurrence"][
                "preconditioner_callback_outputs_in_contract"
            ]
            and not receipt["cross_platform_deterministic_recurrence_claim"]
            and not receipt["production_solver_claim"]
            and not receipt["rocm_hip_parity_claim"]
            for receipt in solve_receipts
        )
    )
    operator_recurrence_binding_audit = {
        "schema_version": (
            "g1-mgt-matrix-free-operator-recurrence-binding-audit.v1"
        ),
        "status": (
            "ready" if operator_recurrence_binding_contract_pass else "blocked"
        ),
        "solve_receipt_count": len(solve_receipts),
        "expected_solve_receipt_count": expected_solve_receipt_count,
        "all_solve_receipts_operator_bound": bool(
            solve_receipts
            and all(
                receipt["operator_binding_ready"] for receipt in solve_receipts
            )
        ),
        "operator_binding_hashes": operator_binding_hashes,
        "single_operator_binding_hash": bool(
            len(operator_binding_hashes) == 1
        ),
        "free_equation_order_data_hash": metadata["free_dof_hash"],
        "residual_formula_hash": residual_contract["residual_formula_hash"],
        "reference_load_free_n_data_hash": metadata[
            "reference_load_free_hash"
        ],
        "current_tangent_action_contract": (
            MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
        ),
        "recurrence_profile": MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
        "accumulation_profile": MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE,
        "all_solve_receipts_use_deterministic_host_arithmetic": bool(
            solve_receipts
            and all(
                receipt[
                    "deterministic_host_recurrence_arithmetic_claim"
                ]
                for receipt in solve_receipts
            )
        ),
        "reference_preconditioner_pattern_hashes": (
            preconditioner_pattern_hashes
        ),
        "reference_preconditioner_values_hashes": (
            preconditioner_values_hashes
        ),
        "operator_callback_formula_parent_arrays_bound": True,
        "operator_callback_outputs_in_deterministic_contract": False,
        "preconditioner_callback_outputs_in_deterministic_contract": False,
        "cross_platform_end_to_end_deterministic_claim": False,
        "production_solver_claim": False,
        "rocm_hip_parity_claim": False,
        "contract_pass": operator_recurrence_binding_contract_pass,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "All 20 tangent solves bind the same actual-MGT free-equation "
            "order, residual formula, reference load, current-tangent action, "
            "and fixed reference-preconditioner hashes. Their host recurrence "
            "uses ordered Python-fsum arithmetic. Operator formulas and parent "
            "arrays are hash-bound, while backend evaluation parity and SciPy "
            "SuperLU outputs remain outside that arithmetic contract, "
            "so this is not cross-platform end-to-end determinism, production "
            "Krylov, HIP parity, or G1 closure."
        ),
    }
    contract_pass = bool(
        binding["dgn_alias_resolution_enabled"]
        and binding["dgn_alias_material_count_applied"] == 24
        and binding["engineer_review_required"]
        and coverage["exact_source_property_coverage"]
        and coverage["resolved_source_property_element_count"] == 5_572
        and geometry["connected_to_physical_residual"]
        and geometry["connected_to_consistent_state_tangent_action"]
        and geometry["consistent_state_tangent_action_mode"]
        == "analytic_reference_plus_exact_finite_chord_axial_correction"
        and geometry["finite_chord_extension_evaluation"]
        == "difference_of_squares_cancellation_stable"
        and geometry["finite_chord_correction_evaluation"]
        == "second_order_decomposition_cancellation_stable"
        and not geometry["full_corotational_frame_claim"]
        and residual_contract["mode"]
        == (
            "reference_csr_plus_load_frame_delta_plus_"
            "finite_chord_correction"
        )
        and residual_contract[
            "reference_csr_parent_matches_analytic_tangent"
        ]
        and residual_contract[
            "load_frame_delta_parent_matches_analytic_tangent"
        ]
        and residual_contract[
            "finite_chord_correction_parent_matches_analytic_tangent"
        ]
        and residual_contract["residual_formula_hash"]
        == canonical_hash(residual_contract["residual_formula"])
        and residual_parent_audit["contract_pass"]
        and residual_parent_audit["parent_repeat_bytes_exact"]
        and residual_parent_audit["parent_component_gate_passed"]
        and reference_preconditioner["available"]
        and reference_preconditioner[
            "approximate_for_state_dependent_adapter"
        ]
        and not reference_preconditioner["production_preconditioner_claim"]
        and one_shot.status == "ready"
        and one_shot.metrics["contract_pass"]
        and one_shot.metrics["target_load_factor_reached"]
        and one_shot.metrics["accepted_step_count"] == 4
        and one_shot.metrics["failed_step_count"] == 0
        and one_shot.metrics["tangent_solve_count"] == 4
        and one_shot.metrics["fallback_count"] == 0
        and one_shot.metrics["regularization_count"] == 0
        and one_shot.metrics["residual_and_increment_acceptance_gate"]
        and one_shot.metrics["maximum_accepted_relative_increment"]
        <= continuation_config.increment_relative_tolerance
        and one_shot.metrics["final_residual_inf_kn"]
        <= continuation_config.residual_tolerance_inf_kn
        and restart_contract_pass
        and strict_gate_contract_pass
        and local_quadratic_convergence_audit["contract_pass"]
        and operator_recurrence_binding_contract_pass
        and rollback_contract_pass
        and adaptive_contract_pass
        and vector_artifact["local_residual_gate_passed"]
    )
    engineer_review_required = bool(binding["engineer_review_required"])
    blockers = [
        "dgn_exact_type_name_material_inheritance_engineer_review_required",
        "full_corotational_frame_not_implemented",
        "full_frame_shell_material_consistent_operator_not_connected",
        "material_state_commit_rollback_not_connected",
        "arc_length_branch_not_executed",
        "production_preconditioner_effectiveness_not_established",
        "engine_v2_end_to_end_preconditioner_determinism_not_connected",
        "production_rocm_hip_nonlinear_parity_not_executed",
        "authoritative_g1_checkpoint_contract_not_satisfied",
        "g1_full_building_closure_not_established",
    ]
    if not source_exact:
        blockers.insert(0, "source_commit_exact_replay_not_proven")
    if not contract_pass:
        blockers.insert(0, "actual_state_updated_newton_path_contract_failed")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "diagnostic_execution_ready": contract_pass,
        "readiness_pass": False,
        "engineer_review_required": engineer_review_required,
        "evidence_closure_pass": False,
        "source_commit_sha": source_commit_sha,
        "engine_version": engine_version(repo_root),
        "source_commit_exact_replay_claim": source_exact,
        "source_tree_state": (
            "commit_bound_inputs_exact"
            if source_exact
            else "working_tree_input_divergence"
        ),
        "input_checksums": source_metadata["input_checksums"],
        "case_id": (
            "g1_real_mgt_state_updated_frame_axial_matrix_free_newton_"
            "continuation"
        ),
        "inputs": {
            "mgt_path": _label(repo_root, mgt_path),
            "mgt_sha256": file_sha256(resolved_mgt),
            "checkpoint_npz": _label(repo_root, checkpoint_npz),
            "checkpoint_sha256": file_sha256(resolved_checkpoint),
            "node_count": metadata["node_count"],
            "element_count": metadata["element_count"],
            "frame_element_count": metadata["frame_element_count"],
            "global_dof_count": metadata["global_dof_count"],
            "free_equation_count": metadata["free_equation_count"],
            "semantic_load_case": metadata["reference_load_contract"][
                "load_case"
            ],
            "initial_state_policy": problem.initial_state_policy,
            "target_load_factors": list(
                continuation_config.target_load_factors
            ),
        },
        "adapter_binding": {
            "material_analysis_property_binding": binding,
            "frame_source_property_coverage_audit": coverage,
            "state_updated_frame_axial_geometry": geometry,
            "residual_evaluation_contract": residual_contract,
            "residual_parent_equivalence_audit": residual_parent_audit,
            "reference_preconditioner_contract": reference_preconditioner,
        },
        "linear_solver_config": linear_config.contract_payload(),
        "matrix_free_operator_recurrence_binding_audit": (
            operator_recurrence_binding_audit
        ),
        "continuation": one_shot_payload,
        "restart_replay": {
            "schema_version": (
                "g1-mgt-state-updated-frame-axial-newton-restart-replay.v1"
            ),
            "restart_load_factor": midpoint.load_factor,
            "restart_checkpoint": midpoint.descriptor(),
            "restart_result": restarted_payload,
            "restart_checkpoint_consumed": bool(
                restarted.metrics["restart_checkpoint_consumed"]
            ),
            "final_vector_bytes_exact": final_vectors_exact,
            "final_state_hash_exact": final_state_hash_exact,
            "final_data_hash_exact": final_data_hash_exact,
            "contract_pass": restart_contract_pass,
        },
        "strict_g1_gate_full_load_probe": {
            "schema_version": (
                "g1-mgt-state-updated-frame-axial-strict-g1-gate-"
                "full-load-probe.v1"
            ),
            "configured_residual_tolerance_inf_n": float(
                strict_gate_config.residual_tolerance_inf_kn * 1000.0
            ),
            "result": strict_gate.to_dict(),
            "final_residual_inf_n": strict_gate_residual_inf_n,
            "full_load_target_reached": bool(
                strict_gate.metrics["target_load_factor_reached"]
            ),
            "residual_gate_passed": bool(
                strict_gate_residual_inf_n <= 0.0005
            ),
            "rollback_performed": bool(
                strict_gate_attempt["rollback_performed"]
            ),
            "contract_pass": strict_gate_contract_pass,
            "claim_boundary": (
                "This actual-model probe takes one direct zero-to-full-load "
                "step, converges in two Newton corrections, and passes the "
                "local 0.0005 N residual-plus-increment gate. It is a bounded "
                "finite-chord axial CPU diagnostic, not an authoritative G1 "
                "checkpoint or broader frame/shell/material closure claim."
            ),
        },
        "local_quadratic_convergence_audit": (
            local_quadratic_convergence_audit
        ),
        "iteration_limited_failure_rollback": {
            "schema_version": (
                "g1-mgt-state-updated-frame-axial-iteration-limited-"
                "failure-rollback.v1"
            ),
            "configured_residual_tolerance_inf_n": float(
                rollback_config.residual_tolerance_inf_kn * 1000.0
            ),
            "configured_maximum_newton_iterations": (
                rollback_config.maximum_newton_iterations
            ),
            "failure_result": rollback_probe.to_dict(),
            "rejected_trial_residual_inf_n": rejected_trial_residual_inf_n,
            "accepted_state_hash_before": rollback_attempt[
                "accepted_state_hash_before"
            ],
            "accepted_state_hash_after": rollback_attempt[
                "accepted_state_hash_after"
            ],
            "initial_final_checkpoint_state_hash_exact": bool(
                rollback_probe.initial_checkpoint.state_hash
                == rollback_probe.final_checkpoint.state_hash
            ),
            "rollback_performed": bool(
                rollback_attempt["rollback_performed"]
            ),
            "rollback_exact": bool(rollback_attempt["rollback_exact"]),
            "contract_pass": rollback_contract_pass,
            "claim_boundary": (
                "This actual-model control-flow probe uses the same 0.0005 N "
                "gate but deliberately allows only one Newton correction. The "
                "remaining 0.002323 N trial therefore fails, and the zero "
                "accepted checkpoint is restored exactly. It proves bounded "
                "displacement rollback, not material-state rollback or a "
                "physical convergence limitation."
            ),
        },
        "adaptive_step_reduction_replay": {
            "schema_version": (
                "g1-mgt-state-updated-frame-axial-adaptive-step-"
                "reduction-replay.v1"
            ),
            "result": adaptive.to_dict(),
            "restart_load_factor": adaptive_midpoint.load_factor,
            "restart_checkpoint": adaptive_midpoint.descriptor(),
            "restart_result": adaptive_restarted.to_dict(),
            "final_vector_bytes_exact": adaptive_final_vectors_exact,
            "final_state_hash_exact": adaptive_final_state_hash_exact,
            "final_data_hash_exact": adaptive_final_data_hash_exact,
            "contract_pass": adaptive_contract_pass,
            "claim_boundary": (
                "With one Newton correction allowed per attempted load step, "
                "the actual model naturally rejects direct 0-to-1 and "
                "0.5-to-1 trials, restores each accepted checkpoint exactly, "
                "halves the step, and reaches load factor 1.0 through accepted "
                "0.5, 0.75, and 1.0 checkpoints. This is adaptive CPU "
                "control-flow evidence for the finite-chord axial diagnostic, "
                "not material-state rollback, arc-length, production/HIP, an "
                "authoritative G1 checkpoint, or G1 closure."
            ),
        },
        "final_vector_artifact": vector_artifact,
        "claims": {
            "actual_mgt_state_updated_axial_load_controlled_continuation": bool(
                one_shot.metrics["contract_pass"]
            ),
            "all_actual_tangent_solves_operator_bound": bool(
                operator_recurrence_binding_audit["contract_pass"]
            ),
            "all_actual_tangent_solves_deterministic_host_arithmetic": bool(
                operator_recurrence_binding_audit[
                    "all_solve_receipts_use_deterministic_host_arithmetic"
                ]
            ),
            "all_actual_tangent_operator_formula_parent_arrays_bound": bool(
                operator_recurrence_binding_audit[
                    "operator_callback_formula_parent_arrays_bound"
                ]
            ),
            "residual_tangent_parent_consistency_audited": bool(
                residual_parent_audit["contract_pass"]
            ),
            "residual_formula_hash_verified": bool(
                residual_contract["residual_formula_hash"]
                == canonical_hash(residual_contract["residual_formula"])
            ),
            "semantic_live_target_load_1p0_reached": bool(
                one_shot.metrics["target_load_factor_reached"]
            ),
            "accepted_displacement_checkpoints": bool(one_shot.checkpoints),
            "residual_and_increment_acceptance_gate": bool(
                one_shot.metrics["residual_and_increment_acceptance_gate"]
            ),
            "diagnostic_load_1p0_binary_checkpoint": bool(
                vector_artifact["local_residual_gate_passed"]
            ),
            "local_g1_candidate_residual_gate_passed": bool(
                one_shot.metrics["final_residual_inf_kn"]
                <= continuation_config.residual_tolerance_inf_kn
            ),
            "direct_full_load_local_residual_gate_passed": (
                strict_gate_contract_pass
            ),
            "actual_local_directional_quadratic_convergence": bool(
                local_quadratic_convergence_audit["contract_pass"]
            ),
            "midpoint_restart_exact": restart_contract_pass,
            "actual_iteration_limited_failure_rollback_exercised": bool(
                rollback_contract_pass
            ),
            "actual_adaptive_step_reduction_path": bool(
                adaptive_contract_pass
            ),
            "actual_adaptive_failed_step_rollback_exact": bool(
                adaptive.metrics["failed_step_count"] > 0
                and adaptive.metrics["rollback_exact"]
            ),
            "adaptive_midpoint_restart_exact": bool(
                adaptive_final_vectors_exact
                and adaptive_final_state_hash_exact
                and adaptive_final_data_hash_exact
            ),
            "material_state_commit_rollback": False,
            "full_corotational_frame": False,
            "arc_length_branch": False,
            "production_matrix_free_krylov": False,
            "cross_platform_deterministic_recurrence": False,
            "production_rocm_hip_nonlinear_parity": False,
            "g1_full_load_checkpoint": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": blockers,
        "artifacts": {
            "receipt": _label(repo_root, receipt_out),
            "schema": str(SCHEMA_PATH),
            "final_vector": _label(repo_root, final_vector_out),
        },
        "claim_boundary": (
            "This receipt reaches semantic-LIVE load factor 1.0 through four "
            "accepted load-controlled Newton targets for the actual finite-"
            "chord axial adapter, with matrix-free analytic current-tangent "
            "FGMRES solves, a shared residual/tangent parent decomposition, "
            "residual-plus-increment step acceptance, and exact "
            "midpoint restart. Every accepted checkpoint passes the local "
            "0.0005 N residual gate; a separate direct zero-to-full-load probe "
            "passes it in two Newton corrections. A one-correction-limited "
            "actual-model probe separately verifies exact displacement rollback. "
            "A bounded one-correction adaptive replay also rejects two actual "
            "large-step trials, reduces the step after exact rollback, reaches "
            "the target, and restarts byte-exactly from load factor 0.5. "
            "A three-scale perturbation audit around the converged direct "
            "full-load state records local directional Newton order near two. "
            "All 20 tangent solves bind the same free-equation order, residual "
            "formula, reference load, current-tangent action, and reference-"
            "preconditioner hashes while using the ordered Python-fsum host "
            "recurrence. Callback operator and SciPy SuperLU outputs remain "
            "outside that deterministic arithmetic contract. "
            "DGN identity aliases still require engineer review; bending/torsion "
            "remain reference geometry. The receipt is not full-corotational, "
            "material-state, arc-length, production/deterministic Engine v2, "
            "HIP, authoritative G1-checkpoint, or G1-closure evidence."
        ),
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
    final_vector_out: Path = DEFAULT_FINAL_VECTOR_OUT,
) -> tuple[bool, str]:
    receipt_target = _resolve(repo_root, receipt_out)
    vector_target = _resolve(repo_root, final_vector_out)
    if not receipt_target.is_file():
        return False, "g1_state_updated_newton_continuation_receipt_missing"
    if not vector_target.is_file():
        return False, "g1_state_updated_newton_continuation_vector_missing"
    expected = build_receipt(
        repo_root=repo_root,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        receipt_out=receipt_out,
        final_vector_out=final_vector_out,
    )
    try:
        existing = _read_json(receipt_target)
    except Exception as exc:
        return False, (
            "g1_state_updated_newton_continuation_receipt_unreadable:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_state_updated_newton_continuation_receipt_mismatch"
    descriptor = expected["final_vector_artifact"]
    if (
        vector_target.stat().st_size != descriptor["byte_length"]
        or file_sha256(vector_target) != descriptor["data_sha256"]
    ):
        return False, "g1_state_updated_newton_continuation_vector_mismatch"
    return True, "g1_state_updated_newton_continuation_consistent"


def write_receipt(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    receipt_out = Path(kwargs.get("receipt_out", DEFAULT_RECEIPT_OUT))
    build_kwargs = dict(kwargs)
    build_kwargs["_write_final_vector"] = True
    payload = build_receipt(**build_kwargs)
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
    parser.add_argument(
        "--final-vector-out",
        type=Path,
        default=DEFAULT_FINAL_VECTOR_OUT,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    kwargs = {
        "repo_root": args.repo_root,
        "mgt_path": args.mgt,
        "checkpoint_npz": args.checkpoint,
        "receipt_out": args.receipt_out,
        "final_vector_out": args.final_vector_out,
    }
    if args.check:
        passed, reason = check_receipt(**kwargs)
        print(reason)
        return 0 if passed else 1
    payload = write_receipt(**kwargs)
    metrics = payload["continuation"]["metrics"]
    print(
        f"{payload['status']} | accepted_steps="
        f"{metrics['accepted_step_count']} | tangent_solves="
        f"{metrics['tangent_solve_count']} | final_residual_n="
        f"{metrics['final_residual_inf_kn'] * 1000.0:.12g} | "
        "g1_checkpoint=false | g1_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
