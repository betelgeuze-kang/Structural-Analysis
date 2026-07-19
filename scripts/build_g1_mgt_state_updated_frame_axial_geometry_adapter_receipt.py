#!/usr/bin/env python3
"""Build the actual-MGT state-updated frame axial adapter receipt."""

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
    build_real_mgt_load_coupled_arc_length_problem,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.current_tangent_operator import (  # noqa: E402
    CURRENT_TANGENT_OPERATOR_PROFILE,
    CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR,
    validate_current_tangent_operator_manifest,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
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
    / "g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_state_updated_frame_axial_geometry_adapter_v1.schema.json"
)
SCHEMA_VERSION = (
    "g1-mgt-state-updated-frame-axial-geometry-adapter-receipt.v1"
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
        Path("implementation/phase1/mgt_shell_load_path.py"),
        Path(
            "implementation/phase1/"
            "mgt_state_updated_frame_axial_geometry.py"
        ),
        Path("implementation/phase1/parse_mgt_section_material_properties.py"),
        Path("implementation/phase1/parse_midas_mgt_to_json_npz.py"),
        Path(
            "implementation/phase1/"
            "run_mgt_coupled_frame_surface_sparse_equilibrium.py"
        ),
        Path(
            "implementation/phase1/"
            "run_mgt_full_frame_6dof_sparse_equilibrium.py"
        ),
        Path(
            "implementation/phase1/"
            "run_mgt_uncoarsened_boundary_global_equilibrium.py"
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
            "build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py"
        ),
        Path("tests/test_g1_mgt_load_coupled_arc_length_adapter.py"),
        Path("tests/test_mgt_physical_residual_assembly.py"),
        Path("tests/test_mgt_state_updated_frame_axial_geometry.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path("tests/test_parse_mgt_section_material_properties.py"),
        Path(
            "tests/"
            "test_build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py"
        ),
    ]


def _full_unit_predictor_row(
    predictor_audit: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        row
        for row in predictor_audit["predictor_rows"]
        if math.isclose(
            float(row["load_factor"]),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    ]
    if len(rows) != 1:
        raise ValueError("predictor audit must contain one full-unit row")
    return rows[0]


def _callback_replay(
    *,
    problem: Any,
    predictor_audit: dict[str, Any],
) -> dict[str, Any]:
    zero = np.zeros(problem.equation_count, dtype=np.float64)
    predictor = np.asarray(
        problem.full_unit_zero_state_predictor_free_m(),
        dtype=np.float64,
    )
    direction_scale = float(np.linalg.norm(predictor, ord=np.inf))
    if not math.isfinite(direction_scale) or direction_scale <= 0.0:
        raise ValueError("full-unit predictor direction must be nonzero")
    direction = predictor / direction_scale

    zero_residual_inf_n = float(
        np.linalg.norm(problem.residual_kn(zero, 0.0), ord=np.inf)
        * 1000.0
    )
    full_residual_inf_n = float(
        np.linalg.norm(problem.residual_kn(predictor, 1.0), ord=np.inf)
        * 1000.0
    )
    full_row = _full_unit_predictor_row(predictor_audit)
    recorded_full_residual_inf_n = float(full_row["residual_inf_n"])
    replay_tolerance_n = max(
        1.0e-9,
        1.0e-12 * max(abs(recorded_full_residual_inf_n), 1.0),
    )
    replay_matches = bool(
        abs(full_residual_inf_n - recorded_full_residual_inf_n)
        <= replay_tolerance_n
    )

    tangent_at_zero = problem.consistent_state_tangent_action_kn_per_m(
        zero,
        1.0,
        direction,
    )
    tangent_at_predictor = problem.consistent_state_tangent_action_kn_per_m(
        predictor,
        1.0,
        direction,
    )
    centered_reference_step_m = 2.0e-7
    centered_tangent_at_predictor = (
        problem.tangent_action_at_step_kn_per_m(
            predictor,
            1.0,
            direction,
            difference_step_m=centered_reference_step_m,
        )
    )
    analytic_centered_error_inf_kn_per_m = float(
        np.linalg.norm(
            tangent_at_predictor - centered_tangent_at_predictor,
            ord=np.inf,
        )
    )
    analytic_centered_reference_inf_kn_per_m = max(
        float(
            np.linalg.norm(
                centered_tangent_at_predictor,
                ord=np.inf,
            )
        ),
        1.0e-30,
    )
    analytic_centered_relative_error = (
        analytic_centered_error_inf_kn_per_m
        / analytic_centered_reference_inf_kn_per_m
    )
    analytic_centered_relative_tolerance = 5.0e-3
    analytic_centered_gate_passed = bool(
        analytic_centered_error_inf_kn_per_m <= 1.0e-5
        or analytic_centered_relative_error
        <= analytic_centered_relative_tolerance
    )
    tangent_difference_inf_kn_per_m = float(
        np.linalg.norm(
            tangent_at_predictor - tangent_at_zero,
            ord=np.inf,
        )
    )
    tangent_reference_inf_kn_per_m = max(
        float(np.linalg.norm(tangent_at_zero, ord=np.inf)),
        float(np.linalg.norm(tangent_at_predictor, ord=np.inf)),
        1.0e-30,
    )
    tangent_state_dependence_tolerance_kn_per_m = max(
        1.0e-9,
        1.0e-12 * tangent_reference_inf_kn_per_m,
    )
    tangent_state_dependence_detected = bool(
        tangent_difference_inf_kn_per_m
        > tangent_state_dependence_tolerance_kn_per_m
    )
    finite = bool(
        math.isfinite(zero_residual_inf_n)
        and math.isfinite(full_residual_inf_n)
        and np.all(np.isfinite(tangent_at_zero))
        and np.all(np.isfinite(tangent_at_predictor))
        and np.all(np.isfinite(centered_tangent_at_predictor))
    )
    return {
        "schema_version": (
            "g1-mgt-state-updated-frame-axial-callback-replay.v1"
        ),
        "equation_count": int(problem.equation_count),
        "zero_state_residual_inf_n": zero_residual_inf_n,
        "full_unit_predictor_residual_inf_n": full_residual_inf_n,
        "recorded_full_unit_predictor_residual_inf_n": (
            recorded_full_residual_inf_n
        ),
        "predictor_residual_replay_tolerance_n": replay_tolerance_n,
        "predictor_residual_replay_matches": replay_matches,
        "tangent_probe_load_factor": 1.0,
        "tangent_probe_direction": (
            "full_unit_zero_state_predictor_normalized_by_infinity_norm"
        ),
        "tangent_state_difference_inf_kn_per_m": (
            tangent_difference_inf_kn_per_m
        ),
        "tangent_state_dependence_tolerance_kn_per_m": (
            tangent_state_dependence_tolerance_kn_per_m
        ),
        "tangent_state_dependence_detected": (
            tangent_state_dependence_detected
        ),
        "analytic_centered_reference_step_m": centered_reference_step_m,
        "analytic_centered_error_inf_kn_per_m": (
            analytic_centered_error_inf_kn_per_m
        ),
        "analytic_centered_relative_error": (
            analytic_centered_relative_error
        ),
        "analytic_centered_relative_tolerance": (
            analytic_centered_relative_tolerance
        ),
        "analytic_centered_gate_passed": analytic_centered_gate_passed,
        "finite": finite,
        "contract_pass": bool(
            finite
            and zero_residual_inf_n <= 1.0e-9
            and replay_matches
            and tangent_state_dependence_detected
            and analytic_centered_gate_passed
        ),
    }


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
    problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=resolved_mgt,
        roundtrip_npz=None,
        checkpoint_npz=resolved_checkpoint,
        apply_state_updated_frame_axial_geometry=True,
    )

    binding = metadata["material_analysis_property_binding"]
    alias_audit = metadata["dgn_material_property_alias_audit"]
    coverage = metadata["frame_source_property_coverage_audit"]
    connectivity = metadata["frame_connectivity_audit"]
    geometry = metadata["state_updated_frame_axial_geometry"]
    tangent_contract = metadata["state_invariant_tangent_contract"]
    residual_contract = metadata["residual_evaluation_contract"]
    residual_parent_audit = metadata[
        "residual_parent_equivalence_audit"
    ]
    reference_preconditioner = metadata[
        "reference_preconditioner_contract"
    ]
    predictor_audit = metadata["zero_state_sparse_predictor_audit"]
    callback_replay = _callback_replay(
        problem=problem,
        predictor_audit=predictor_audit,
    )
    current_tangent_operator = problem.current_tangent_operator
    if current_tangent_operator is None:
        raise ValueError(
            "state-updated adapter lacks a current-tangent operator contract"
        )
    current_tangent_manifest = dict(
        validate_current_tangent_operator_manifest(
            current_tangent_operator.to_manifest()
        )
    )
    current_tangent_binding = (
        problem.matrix_free_current_tangent_operator_binding()
    )
    if current_tangent_binding is None:
        raise ValueError("state-updated adapter lacks an operator binding")
    current_tangent_contract_pass = bool(
        current_tangent_manifest["profile"]
        == CURRENT_TANGENT_OPERATOR_PROFILE
        and current_tangent_manifest["contract_hash"]
        == current_tangent_operator.contract_hash
        and current_tangent_manifest["dimensions"]["equation_count"]
        == problem.equation_count
        and current_tangent_manifest["dimensions"]["global_dof_count"]
        == metadata["global_dof_count"]
        and current_tangent_manifest["dimensions"]["frame_element_count"]
        == metadata["frame_element_count"]
        and current_tangent_manifest["dimensions"]["geometry_element_count"]
        == metadata["frame_element_count"]
        and current_tangent_binding[
            "current_tangent_operator_contract_hash"
        ]
        == current_tangent_operator.contract_hash
        and current_tangent_binding[
            "current_tangent_operator_array_bundle_hash"
        ]
        == current_tangent_operator.array_bundle_hash
        and current_tangent_binding[
            "operator_callback_reference_evaluator"
        ]
        == CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
        and current_tangent_binding[
            "operator_callback_outputs_in_contract"
        ]
        is True
        and callback_replay["analytic_centered_gate_passed"]
    )

    diagnostic_execution_ready = bool(
        metadata["roundtrip_generated_uncoarsened"]
        and metadata["uncoarsened_parser_report"]["contract_pass"]
        and metadata["node_count"] == 13_047
        and metadata["element_count"] == 12_728
        and metadata["free_equation_count"] == 70_560
        and connectivity["frame_connectivity_source"]
        == "elem_conn_ptr/elem_conn_idx"
        and not connectivity["edge_index_used_for_element_binding"]
        and connectivity["line_element_row_accounting_exact"]
        and binding["dgn_alias_resolution_enabled"]
        and binding["resolution_policy"]
        == "exact_normalized_type_and_name_unique_source_material.v1"
        and binding["dgn_alias_material_count_applied"] == 24
        and binding["resolved_material_count"] == 30
        and binding["engineer_review_required"]
        and alias_audit["contract_pass"]
        and alias_audit["dgn_numeric_elastic_override_consumed_count"] == 0
        and alias_audit["fuzzy_name_match_count"] == 0
        and coverage["exact_source_property_coverage"]
        and coverage["resolved_source_property_element_count"] == 5_572
        and coverage["unresolved_source_property_element_count"] == 0
        and geometry["state_updated_frame_axial_geometry_applied"]
        and geometry["connected_to_physical_residual"]
        and geometry["connected_to_consistent_state_tangent_action"]
        and geometry["consistent_state_tangent_action_mode"]
        == "analytic_reference_plus_exact_finite_chord_axial_correction"
        and not geometry["connected_to_centered_tangent_action"]
        and geometry[
            "centered_tangent_action_available_for_independent_audit"
        ]
        and geometry["real_property_element_count"] == 5_572
        and geometry["property_fallback_count"] == 0
        and geometry["conservative_energy_gradient"]
        and geometry["consistent_tangent_action_available"]
        and not geometry["full_corotational_frame_claim"]
        and tangent_contract["status"] == "blocked"
        and not tangent_contract["available"]
        and tangent_contract["operator_classification"]
        == "state_dependent_frame_axial_geometry"
        and tangent_contract["current_state_reassembly_required"]
        and not tangent_contract["exact_for_adapter_residual_model"]
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
        and residual_contract[
            "component_force_assembly_retained_for_diagnostics"
        ]
        and residual_contract["schema_version"]
        == "mgt-residual-evaluation-contract.v1"
        and residual_contract["residual_formula_hash"]
        == canonical_hash(residual_contract["residual_formula"])
        and not residual_contract["promotes_g1_closure"]
        and residual_parent_audit["applicable"]
        and residual_parent_audit["contract_pass"]
        and residual_parent_audit["parent_repeat_bytes_exact"]
        and residual_parent_audit["parent_component_gate_passed"]
        and reference_preconditioner["available"]
        and reference_preconditioner["intended_use"]
        == "fixed_right_preconditioner"
        and not reference_preconditioner[
            "exact_for_adapter_residual_model"
        ]
        and reference_preconditioner[
            "approximate_for_state_dependent_adapter"
        ]
        and not reference_preconditioner[
            "factorization_executed_by_adapter"
        ]
        and predictor_audit["contract_pass"]
        and predictor_audit["remainder_classification"]
        == "measurable_quadratic"
        and predictor_audit[
            "measurable_quadratic_remainder_gate_passed"
        ]
        and predictor_audit["quadratic_remainder_gate_passed"]
        and not predictor_audit["linear_model_consistency_gate_passed"]
        and predictor_audit["minimum_observed_remainder_order"] is not None
        and 1.8
        <= float(predictor_audit["minimum_observed_remainder_order"])
        <= 2.2
        and callback_replay["contract_pass"]
        and current_tangent_contract_pass
    )
    engineer_review_required = bool(
        binding["engineer_review_required"]
        and alias_audit["engineer_review_required"]
    )
    readiness_pass = bool(
        diagnostic_execution_ready and not engineer_review_required
    )
    blockers = [
        "dgn_exact_type_name_material_inheritance_engineer_review_required",
        "full_corotational_frame_not_implemented",
        "full_nonlinear_continuation_not_executed",
        "production_matrix_free_state_tangent_krylov_not_executed",
        "current_tangent_operator_hip_execution_not_performed",
        "production_rocm_hip_nonlinear_parity_not_executed",
        "accepted_semantic_live_load_1p0_checkpoint_not_produced",
        "g1_full_building_closure_not_established",
    ]
    if not diagnostic_execution_ready:
        blockers.insert(0, "state_updated_adapter_diagnostic_contract_failed")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if diagnostic_execution_ready else "blocked",
        "contract_pass": diagnostic_execution_ready,
        "readiness_pass": readiness_pass,
        "diagnostic_execution_ready": diagnostic_execution_ready,
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
        "case_id": "g1_real_mgt_state_updated_frame_axial_geometry_adapter",
        "inputs": {
            "mgt_path": _label(repo_root, mgt_path),
            "mgt_sha256": file_sha256(resolved_mgt),
            "checkpoint_npz": _label(repo_root, checkpoint_npz),
            "checkpoint_sha256": file_sha256(resolved_checkpoint),
            "roundtrip_derivation": metadata["roundtrip_derivation"],
            "roundtrip_generated_uncoarsened": metadata[
                "roundtrip_generated_uncoarsened"
            ],
            "roundtrip_sha256": metadata["roundtrip_sha256"],
            "node_count": metadata["node_count"],
            "element_count": metadata["element_count"],
            "frame_element_count": metadata["frame_element_count"],
            "global_dof_count": metadata["global_dof_count"],
            "free_equation_count": metadata["free_equation_count"],
            "semantic_load_case": metadata["reference_load_contract"][
                "load_case"
            ],
            "historical_checkpoint_equilibrium_claim": False,
        },
        "frame_connectivity_audit": connectivity,
        "material_analysis_property_binding": binding,
        "dgn_material_property_alias_audit": alias_audit,
        "frame_source_property_coverage_audit": coverage,
        "state_updated_frame_axial_geometry": geometry,
        "state_dependent_tangent_contract": tangent_contract,
        "current_tangent_operator_contract": {
            "manifest": current_tangent_manifest,
            "operator_binding": current_tangent_binding,
            "array_total_byte_length": sum(
                int(row["byte_length"])
                for row in current_tangent_manifest["array_descriptors"]
            ),
            "residual_centered_difference_gate_passed": callback_replay[
                "analytic_centered_gate_passed"
            ],
            "operator_callback_outputs_in_contract": True,
            "cpu_reference_evaluator_executed": True,
            "hip_execution": False,
            "cpu_hip_numerical_parity": False,
            "contract_pass": current_tangent_contract_pass,
        },
        "residual_evaluation_contract": residual_contract,
        "residual_parent_equivalence_audit": residual_parent_audit,
        "reference_preconditioner_contract": reference_preconditioner,
        "zero_state_sparse_predictor_audit": predictor_audit,
        "callback_replay": callback_replay,
        "claims": {
            "actual_mgt_source_and_semantic_live_load_consumed": True,
            "authoritative_element_connectivity_consumed": True,
            "dgn_exact_type_name_source_alias_applied": True,
            "dgn_numeric_elastic_override_consumed": False,
            "dgn_alias_engineer_review_required": engineer_review_required,
            "exact_frame_source_property_coverage_after_alias": bool(
                coverage["exact_source_property_coverage"]
            ),
            "synthetic_property_fallback_used": False,
            "finite_chord_axial_geometry_connected_to_physical_residual": bool(
                geometry["connected_to_physical_residual"]
            ),
            "finite_chord_axial_geometry_connected_to_consistent_state_tangent": bool(
                geometry["connected_to_consistent_state_tangent_action"]
            ),
            "measurable_quadratic_predictor_remainder": bool(
                predictor_audit[
                    "measurable_quadratic_remainder_gate_passed"
                ]
            ),
            "state_dependent_tangent_action_detected": bool(
                callback_replay["tangent_state_dependence_detected"]
            ),
            "backend_neutral_current_tangent_operator_contract": (
                current_tangent_contract_pass
            ),
            "operator_callback_formula_and_parent_arrays_in_contract": (
                current_tangent_contract_pass
            ),
            "residual_parent_matches_analytic_tangent": bool(
                residual_contract[
                    "reference_csr_parent_matches_analytic_tangent"
                ]
                and residual_contract[
                    "finite_chord_correction_parent_matches_analytic_tangent"
                ]
            ),
            "residual_formula_hash_verified": bool(
                residual_contract["residual_formula_hash"]
                == canonical_hash(residual_contract["residual_formula"])
            ),
            "residual_parent_component_equivalence_audited": bool(
                residual_parent_audit["contract_pass"]
            ),
            "zero_state_reference_preconditioner_exposed": bool(
                reference_preconditioner["available"]
            ),
            "full_corotational_frame": False,
            "full_nonlinear_continuation": False,
            "production_matrix_free_state_tangent_krylov": False,
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
            "This receipt connects conservative finite-chord frame axial "
            "geometry to the actual uncoarsened MGT semantic-LIVE residual "
            "and analytic consistent state-tangent callback. The solve "
            "residual uses the same reference CSR, load-frame delta, and "
            "finite-chord correction parents as that tangent; the component "
            "sum remains a scale-relative diagnostic cross-check. Property "
            "binding uses exact unique "
            "DGN-MATL "
            "type/name aliases to source *MATERIAL elastic properties. The "
            "aliases consume no DGN numeric elastic fields or synthetic "
            "fallback and remain engineer-review-required. Bending and torsion "
            "remain reference-geometry terms. This is not a full corotational "
            "frame, nonlinear continuation, production Krylov/HIP result, "
            "accepted load-1.0 checkpoint, or G1 closure."
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
        return False, "g1_mgt_state_updated_frame_axial_adapter_missing"
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
            "g1_mgt_state_updated_frame_axial_adapter_unreadable:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_mgt_state_updated_frame_axial_adapter_mismatch"
    return True, "g1_mgt_state_updated_frame_axial_adapter_consistent"


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
    predictor = payload["zero_state_sparse_predictor_audit"]
    print(
        f"{payload['status']} | equations="
        f"{payload['inputs']['free_equation_count']} | "
        f"remainder={predictor['remainder_classification']} | "
        f"order={predictor['minimum_observed_remainder_order']:.12g} | "
        "g1_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
