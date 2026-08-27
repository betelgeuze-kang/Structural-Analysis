#!/usr/bin/env python3
"""Build one actual-MGT matrix-free current-tangent FGMRES smoke receipt."""

from __future__ import annotations

import argparse
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
    / "g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke_v1.schema.json"
)
SCHEMA_VERSION = (
    "g1-mgt-state-updated-frame-axial-matrix-free-fgmres-smoke.v1"
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


NON_NUMERICAL_REPLAY_WRAPPER_PATHS = frozenset(
    {
        "scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py",
        "tests/test_build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py",
    }
)


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
            and key not in NON_NUMERICAL_REPLAY_WRAPPER_PATHS
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
        Path("src/structural_analysis/solvers/nonlinear/vector_arc_length.py"),
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
            "build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py"
        ),
        Path("tests/test_matrix_free_cpu_fgmres_state_tangent.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path(
            "tests/"
            "test_build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py"
        ),
    ]


def _solver_config() -> MatrixFreeCPUFGMRESConfig:
    return MatrixFreeCPUFGMRESConfig(
        max_iterations=12,
        restart_length=8,
        relative_tolerance_l2=1.0e-8,
        absolute_tolerance_l2_kn=1.0e-10,
        explicit_residual_tolerance_inf_kn=1.0e-7,
    )


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
    historical_problem, metadata = (
        build_real_mgt_load_coupled_arc_length_problem(
            mgt_path=resolved_mgt,
            roundtrip_npz=None,
            checkpoint_npz=resolved_checkpoint,
            apply_state_updated_frame_axial_geometry=True,
        )
    )
    problem = historical_problem.zero_state_problem()
    predictor = problem.full_unit_zero_state_predictor_free_m()
    load_factor = 1.0
    initial_residual_kn = problem.residual_kn(predictor, load_factor)
    right_hand_side_kn = -initial_residual_kn
    config = _solver_config()
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=config,
    )
    solve = solver.solve_at_state(
        problem,
        predictor,
        right_hand_side_kn,
        load_factor=load_factor,
        solve_id="actual-full-unit-predictor-newton-correction",
    )
    correction = np.asarray(solve.solution_free, dtype=np.float64)
    independent_linear_residual_kn = (
        problem.consistent_state_tangent_action_kn_per_m(
            predictor,
            load_factor,
            correction,
        )
        - right_hand_side_kn
    )
    trial = predictor + correction
    trial_residual_kn = problem.residual_kn(trial, load_factor)
    initial_residual_inf_n = float(
        np.linalg.norm(initial_residual_kn, ord=np.inf) * 1000.0
    )
    trial_residual_inf_n = float(
        np.linalg.norm(trial_residual_kn, ord=np.inf) * 1000.0
    )
    reduction_ratio = trial_residual_inf_n / max(
        initial_residual_inf_n,
        1.0e-30,
    )
    independent_linear_residual_inf_kn = float(
        np.linalg.norm(independent_linear_residual_kn, ord=np.inf)
    )
    predictor_audit = metadata["zero_state_sparse_predictor_audit"]
    full_predictor_rows = [
        row
        for row in predictor_audit["predictor_rows"]
        if math.isclose(
            float(row["load_factor"]),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    ]
    if len(full_predictor_rows) != 1:
        raise ValueError("full-unit predictor audit row is not unique")
    recorded_initial_residual_inf_n = float(
        full_predictor_rows[0]["residual_inf_n"]
    )
    initial_replay_matches = bool(
        math.isclose(
            initial_residual_inf_n,
            recorded_initial_residual_inf_n,
            rel_tol=1.0e-12,
            abs_tol=1.0e-9,
        )
    )
    binding = metadata["material_analysis_property_binding"]
    coverage = metadata["frame_source_property_coverage_audit"]
    geometry = metadata["state_updated_frame_axial_geometry"]
    preconditioner_contract = metadata[
        "reference_preconditioner_contract"
    ]
    residual_contract = metadata["residual_evaluation_contract"]
    residual_parent_audit = metadata[
        "residual_parent_equivalence_audit"
    ]
    tangent_receipt = solve.receipt
    operator_binding = tangent_receipt["operator_binding"]
    recurrence = tangent_receipt["recurrence"]
    contract_pass = bool(
        metadata["free_equation_count"] == 70_560
        and binding["dgn_alias_resolution_enabled"]
        and binding["dgn_alias_material_count_applied"] == 24
        and binding["engineer_review_required"]
        and coverage["exact_source_property_coverage"]
        and coverage["resolved_source_property_element_count"] == 5_572
        and geometry["connected_to_physical_residual"]
        and geometry["connected_to_consistent_state_tangent_action"]
        and geometry["consistent_state_tangent_action_mode"]
        == "analytic_reference_plus_exact_finite_chord_axial_correction"
        and residual_contract["mode"]
        == (
            "reference_csr_plus_load_frame_delta_plus_"
            "finite_chord_correction"
        )
        and residual_contract[
            "reference_csr_parent_matches_analytic_tangent"
        ]
        and residual_contract[
            "finite_chord_correction_parent_matches_analytic_tangent"
        ]
        and residual_contract["residual_formula_hash"]
        == canonical_hash(residual_contract["residual_formula"])
        and residual_parent_audit["contract_pass"]
        and residual_parent_audit["parent_repeat_bytes_exact"]
        and residual_parent_audit["parent_component_gate_passed"]
        and preconditioner_contract["available"]
        and preconditioner_contract[
            "approximate_for_state_dependent_adapter"
        ]
        and not preconditioner_contract["production_preconditioner_claim"]
        and tangent_receipt["contract_pass"]
        and tangent_receipt["matrix_free_current_state_operator_action"]
        and not tangent_receipt["materialized_current_tangent"]
        and tangent_receipt["operator_binding_ready"]
        and operator_binding["status"] == "ready"
        and operator_binding["equation_count"] == metadata["free_equation_count"]
        and operator_binding["free_equation_order_data_hash"]
        == metadata["free_dof_hash"]
        and operator_binding["residual_formula_hash"]
        == residual_contract["residual_formula_hash"]
        and operator_binding["reference_load_free_n_data_hash"]
        == metadata["reference_load_free_hash"]
        and operator_binding["current_tangent_action_contract"]
        == MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
        and operator_binding["current_tangent_operator_profile"]
        == "reference_csr_load_frame_delta_finite_chord_axial.v1"
        and operator_binding["operator_callback_outputs_in_contract"]
        is True
        and tangent_receipt[
            "deterministic_host_recurrence_arithmetic_claim"
        ]
        and recurrence["profile"] == MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE
        and recurrence["accumulation_profile"]
        == MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE
        and recurrence["deterministic_host_arithmetic"]
        and recurrence["operator_callback_outputs_in_contract"]
        and not recurrence["preconditioner_callback_outputs_in_contract"]
        and not tangent_receipt[
            "cross_platform_deterministic_recurrence_claim"
        ]
        and tangent_receipt["explicit_residual_inf_kn"]
        <= config.explicit_residual_tolerance_inf_kn
        and independent_linear_residual_inf_kn
        <= config.explicit_residual_tolerance_inf_kn
        and initial_replay_matches
        and trial_residual_inf_n < initial_residual_inf_n
        and reduction_ratio <= 1.0e-3
    )
    engineer_review_required = bool(binding["engineer_review_required"])
    blockers = [
        "dgn_exact_type_name_material_inheritance_engineer_review_required",
        "single_newton_correction_smoke_not_continuation",
        "full_corotational_frame_not_implemented",
        "production_preconditioner_effectiveness_not_established",
        "engine_v2_end_to_end_preconditioner_determinism_not_connected",
        "production_rocm_hip_nonlinear_parity_not_executed",
        "accepted_semantic_live_load_1p0_checkpoint_not_produced",
        "g1_full_building_closure_not_established",
    ]
    if not contract_pass:
        blockers.insert(0, "matrix_free_current_tangent_smoke_failed")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "diagnostic_execution_ready": contract_pass,
        "readiness_pass": False,
        "engineer_review_required": engineer_review_required,
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
        "case_id": (
            "g1_real_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke"
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
            "probe_load_factor": load_factor,
            "probe_state": "full_unit_zero_state_linear_predictor",
        },
        "adapter_binding": {
            "material_analysis_property_binding": binding,
            "frame_source_property_coverage_audit": coverage,
            "state_updated_frame_axial_geometry": geometry,
            "residual_evaluation_contract": residual_contract,
            "residual_parent_equivalence_audit": residual_parent_audit,
            "reference_preconditioner_contract": preconditioner_contract,
        },
        "tangent_solve": tangent_receipt,
        "newton_correction_probe": {
            "schema_version": (
                "g1-mgt-state-updated-frame-axial-newton-correction-probe.v1"
            ),
            "load_factor": load_factor,
            "initial_state_data_hash": array_data_hash(predictor),
            "initial_residual_inf_n": initial_residual_inf_n,
            "recorded_predictor_residual_inf_n": (
                recorded_initial_residual_inf_n
            ),
            "initial_residual_replay_matches": initial_replay_matches,
            "right_hand_side_inf_kn": float(
                np.linalg.norm(right_hand_side_kn, ord=np.inf)
            ),
            "correction_data_hash": array_data_hash(correction),
            "correction_inf_m": float(
                np.linalg.norm(correction, ord=np.inf)
            ),
            "independent_linear_residual_data_hash": array_data_hash(
                independent_linear_residual_kn
            ),
            "independent_linear_residual_inf_kn": (
                independent_linear_residual_inf_kn
            ),
            "independent_linear_residual_tolerance_inf_kn": (
                config.explicit_residual_tolerance_inf_kn
            ),
            "trial_state_data_hash": array_data_hash(trial),
            "trial_residual_inf_n": trial_residual_inf_n,
            "full_step_alpha": 1.0,
            "residual_reduction_ratio": reduction_ratio,
            "residual_reduction_gate": 1.0e-3,
            "residual_reduction_gate_passed": bool(
                reduction_ratio <= 1.0e-3
            ),
            "accepted_state_committed": False,
            "contract_pass": bool(
                tangent_receipt["contract_pass"]
                and independent_linear_residual_inf_kn
                <= config.explicit_residual_tolerance_inf_kn
                and initial_replay_matches
                and reduction_ratio <= 1.0e-3
            ),
        },
        "claims": {
            "actual_mgt_current_state_matrix_free_tangent_solve": bool(
                tangent_receipt["contract_pass"]
            ),
            "actual_mgt_operator_binding_ready": bool(
                tangent_receipt["operator_binding_ready"]
            ),
            "current_tangent_operator_formula_parent_arrays_bound": bool(
                recurrence["operator_callback_outputs_in_contract"]
            ),
            "deterministic_host_recurrence_arithmetic": bool(
                tangent_receipt[
                    "deterministic_host_recurrence_arithmetic_claim"
                ]
            ),
            "residual_tangent_parent_consistency_audited": bool(
                residual_parent_audit["contract_pass"]
            ),
            "residual_formula_hash_verified": bool(
                residual_contract["residual_formula_hash"]
                == canonical_hash(residual_contract["residual_formula"])
            ),
            "fixed_reference_csr_right_preconditioner_factorized": True,
            "explicit_linear_residual_gate_passed": bool(
                tangent_receipt["contract_pass"]
                and independent_linear_residual_inf_kn
                <= config.explicit_residual_tolerance_inf_kn
            ),
            "one_full_step_newton_residual_reduction": bool(
                reduction_ratio <= 1.0e-3
            ),
            "accepted_state_committed": False,
            "full_nonlinear_continuation": False,
            "full_corotational_frame": False,
            "production_matrix_free_krylov": False,
            "cross_platform_deterministic_recurrence": False,
            "production_rocm_hip_nonlinear_parity": False,
            "accepted_semantic_live_load_1p0_checkpoint": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": blockers,
        "artifacts": {
            "receipt": _label(repo_root, receipt_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": (
            "This receipt covers one uncommitted Newton correction at the "
            "actual semantic-LIVE full-unit linear predictor. FGMRES applies "
            "the analytic current state-tangent callback without materializing "
            "the current Jacobian and uses a fixed zero-state reference CSR LU "
            "only as a diagnostic right preconditioner. The residual and "
            "tangent share their reference/load-delta/finite-chord parents; "
            "their residual formula, free-equation order, reference load, and "
            "current-tangent action are hash-bound. Host dot/norm, projected "
            "solve, and basis-update accumulation use the Engine v2 ordered "
            "Python-fsum profile; component summation is retained only as an "
            "audited diagnostic. Callback operator and SciPy SuperLU output "
            "remain outside the deterministic arithmetic contract. "
            "The explicit residual "
            "and one-step reduction gates do not establish continuation, a "
            "production/deterministic Engine v2 solver, HIP parity, an accepted "
            "load-1.0 checkpoint, or G1 closure."
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
) -> tuple[bool, str]:
    target = _resolve(repo_root, receipt_out)
    if not target.is_file():
        return False, "g1_mgt_state_updated_matrix_free_fgmres_smoke_missing"
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
            "g1_mgt_state_updated_matrix_free_fgmres_smoke_unreadable:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_mgt_state_updated_matrix_free_fgmres_smoke_mismatch"
    return True, "g1_mgt_state_updated_matrix_free_fgmres_smoke_consistent"


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
    solve = payload["tangent_solve"]
    probe = payload["newton_correction_probe"]
    print(
        f"{payload['status']} | iterations={solve['iteration_count']} | "
        f"explicit_residual_kn={solve['explicit_residual_inf_kn']:.12g} | "
        f"trial_residual_n={probe['trial_residual_inf_n']:.12g} | "
        "continuation=false | g1_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
