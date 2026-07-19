#!/usr/bin/env python3
"""Build the fail-closed real-MGT load-coupled adapter receipt."""

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
    MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY,
    audit_load_coupled_problem_at_initial_state,
    build_real_mgt_load_coupled_arc_length_problem,
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
DEFAULT_STORED_DIRECT_RECEIPT = (
    PRODUCTIZATION / "mgt_direct_residual_newton_probe.json"
)
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION / "g1_mgt_load_coupled_arc_length_adapter_receipt.json"
)
DEFAULT_SUMMARY_OUT = (
    PRODUCTIZATION / "g1_mgt_load_coupled_arc_length_adapter_summary.json"
)
DEFAULT_PREDICTOR_VECTOR_OUT = (
    PRODUCTIZATION
    / "g1_mgt_live_full_unit_predictor_free_displacement.f64le"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_load_coupled_arc_length_adapter_v1.schema.json"
)
RECEIPT_SCHEMA_VERSION = (
    "g1-mgt-load-coupled-arc-length-adapter-receipt.v1"
)
SUMMARY_SCHEMA_VERSION = (
    "g1-mgt-load-coupled-arc-length-adapter-summary.v1"
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


def _full_unit_predictor_vector_artifact(
    *,
    repo_root: Path,
    predictor_vector_out: Path,
    problem: Any,
    adapter_metadata: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    values = np.ascontiguousarray(
        problem.full_unit_zero_state_predictor_free_m(),
        dtype="<f8",
    )
    raw = memoryview(values).cast("B").tobytes()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    predictor_audit = adapter_metadata["zero_state_sparse_predictor_audit"]
    full_unit_rows = [
        row
        for row in predictor_audit["predictor_rows"]
        if math.isclose(
            float(row["load_factor"]),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    ]
    if len(full_unit_rows) != 1:
        raise ValueError("exactly one full-unit predictor row is required")
    full_unit_row = full_unit_rows[0]
    residual_tolerance_n = 5.0e-4
    residual_gate = bool(
        float(full_unit_row["residual_inf_n"]) <= residual_tolerance_n
    )
    if not residual_gate:
        raise ValueError("full-unit predictor residual gate failed")
    if digest != predictor_audit["predictor_direction_hash"]:
        raise ValueError("full-unit predictor vector hash mismatch")
    return {
        "schema_version": "g1-mgt-live-full-unit-predictor-vector.v1",
        "status": "ready",
        "artifact_path": _label(repo_root, predictor_vector_out),
        "dtype": "<f8",
        "layout": "C",
        "byte_order": "little",
        "equation_order": "adapter_free_global_dof_order",
        "equation_count": int(values.size),
        "byte_length": int(len(raw)),
        "data_sha256": digest,
        "free_dof_hash": str(adapter_metadata["free_dof_hash"]),
        "reference_load_hash": str(
            adapter_metadata["reference_load_free_hash"]
        ),
        "semantic_load_target": str(
            adapter_metadata["semantic_load_assembly"]["target_name"]
        ),
        "load_factor": 1.0,
        "residual_inf_n": float(full_unit_row["residual_inf_n"]),
        "residual_tolerance_n": residual_tolerance_n,
        "residual_gate_passed": residual_gate,
        "maximum_translation_m": float(
            full_unit_row["maximum_predictor_translation_m"]
        ),
        "persisted_nonlinear_continuation_checkpoint": False,
        "large_vector_binary_trace_claim": False,
        "g1_full_load_checkpoint_claim": False,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "One deterministic free-DOF displacement vector for the full-unit "
            "zero-state LIVE predictor. It is not a continuation trace, an "
            "accepted material/geometric nonlinear checkpoint, a production "
            "ROCm/HIP result, or G1 closure."
        ),
    }, raw


def _stored_receipt_comparison(
    *,
    repo_root: Path,
    stored_receipt_path: Path,
    current_audit: dict[str, Any],
) -> dict[str, Any]:
    absolute_path = _resolve(repo_root, stored_receipt_path)
    stored = _read_json(absolute_path)
    stored_base = stored.get("base_direct_residual")
    stored_checkpoint = stored.get("checkpoint")
    if not isinstance(stored_base, dict) or not isinstance(
        stored_checkpoint,
        dict,
    ):
        raise ValueError("stored direct-residual receipt is missing comparison data")
    stored_residual_n = float(stored_base["direct_residual_inf_n"])
    stored_load_factor = float(stored_checkpoint["load_scale"])
    stored_generated_at = str(stored.get("generated_at") or "")
    stored_source_commit = stored.get("source_commit_sha")
    source_commit_present = bool(
        isinstance(stored_source_commit, str)
        and len(stored_source_commit) == 40
    )
    input_checksums_present = bool(
        isinstance(stored.get("input_checksums"), dict)
        and stored["input_checksums"]
    )
    current_residual_n = float(current_audit["residual_inf_norm_kn"]) * 1000.0
    current_load_factor = float(current_audit["load_factor"])
    difference_n = abs(current_residual_n - stored_residual_n)
    tolerance_n = max(1.0e-6, abs(stored_residual_n) * 1.0e-9)
    load_factor_matches = math.isclose(
        current_load_factor,
        stored_load_factor,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    )
    equivalent = bool(load_factor_matches and difference_n <= tolerance_n)
    return {
        "stored_receipt_path": _label(repo_root, stored_receipt_path),
        "stored_receipt_sha256": file_sha256(absolute_path),
        "stored_receipt_generated_at": stored_generated_at,
        "stored_receipt_source_commit_sha": (
            str(stored_source_commit) if source_commit_present else None
        ),
        "stored_receipt_source_commit_sha_present": source_commit_present,
        "stored_receipt_input_checksums_present": input_checksums_present,
        "stored_receipt_replay_provenance_complete": bool(
            stored_generated_at
            and source_commit_present
            and input_checksums_present
        ),
        "stored_receipt_load_factor": stored_load_factor,
        "current_adapter_load_factor": current_load_factor,
        "comparison_load_factor": current_load_factor,
        "load_factor_matches": load_factor_matches,
        "stored_base_direct_residual_inf_n": stored_residual_n,
        "current_adapter_initial_residual_inf_n": current_residual_n,
        "absolute_difference_n": difference_n,
        "relative_difference_to_stored": (
            difference_n / max(abs(stored_residual_n), 1.0e-30)
        ),
        "current_to_stored_ratio": (
            current_residual_n / max(abs(stored_residual_n), 1.0e-30)
        ),
        "equivalence_absolute_tolerance_n": tolerance_n,
        "stored_receipt_equivalent_to_current_adapter": equivalent,
    }


def _input_paths(
    *,
    mgt_path: Path,
    checkpoint_npz: Path,
    stored_direct_receipt: Path,
) -> list[Path]:
    return [
        mgt_path,
        checkpoint_npz,
        stored_direct_receipt,
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
        Path("implementation/phase1/run_mgt_direct_residual_newton_probe.py"),
        Path(
            "implementation/phase1/"
            "run_mgt_full_frame_6dof_sparse_equilibrium.py"
        ),
        Path(
            "implementation/phase1/"
            "run_mgt_uncoarsened_boundary_global_equilibrium.py"
        ),
        Path(
            "src/structural_analysis/engine_v2/contracts/"
            "current_tangent_operator.py"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "current_tangent_operator_v1.schema.json"
        ),
        SCHEMA_PATH,
        Path("scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py"),
        Path("tests/test_g1_mgt_load_coupled_arc_length_adapter.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path("tests/test_mgt_physical_residual_assembly.py"),
        Path("tests/test_mgt_semantic_load_assembly.py"),
        Path("tests/test_mgt_state_updated_frame_axial_geometry.py"),
        Path("tests/test_parse_mgt_section_material_properties.py"),
        Path("tests/test_build_g1_mgt_load_coupled_arc_length_adapter_receipt.py"),
    ]


def build_g1_mgt_load_coupled_arc_length_adapter_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    stored_direct_receipt: Path = DEFAULT_STORED_DIRECT_RECEIPT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    predictor_vector_out: Path = DEFAULT_PREDICTOR_VECTOR_OUT,
    _write_predictor_vector: bool = False,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    resolved_mgt = _resolve(repo_root, mgt_path)
    resolved_checkpoint = _resolve(repo_root, checkpoint_npz)
    problem, adapter_metadata = (
        build_real_mgt_load_coupled_arc_length_problem(
            mgt_path=resolved_mgt,
            roundtrip_npz=None,
            checkpoint_npz=resolved_checkpoint,
        )
    )
    audit = audit_load_coupled_problem_at_initial_state(problem)
    predictor_vector_artifact, predictor_vector_bytes = (
        _full_unit_predictor_vector_artifact(
            repo_root=repo_root,
            predictor_vector_out=predictor_vector_out,
            problem=problem,
            adapter_metadata=adapter_metadata,
        )
    )
    adapter_metadata["full_unit_predictor_vector_artifact"] = (
        predictor_vector_artifact
    )
    if _write_predictor_vector:
        predictor_target = _resolve(repo_root, predictor_vector_out)
        predictor_target.parent.mkdir(parents=True, exist_ok=True)
        predictor_target.write_bytes(predictor_vector_bytes)
        if (
            predictor_target.stat().st_size
            != predictor_vector_artifact["byte_length"]
            or file_sha256(predictor_target)
            != predictor_vector_artifact["data_sha256"]
        ):
            raise ValueError("persisted predictor vector verification failed")
    comparison = _stored_receipt_comparison(
        repo_root=repo_root,
        stored_receipt_path=stored_direct_receipt,
        current_audit=audit,
    )
    parser_contract_pass = bool(
        adapter_metadata["uncoarsened_parser_report"]["contract_pass"]
    )
    fixed_case_dimensions_pass = bool(
        adapter_metadata["node_count"] == 13_047
        and adapter_metadata["global_dof_count"] == 78_282
        and adapter_metadata["free_equation_count"] == 70_560
        and audit["equation_count"] == 70_560
    )
    checkpoint_binding_pass = bool(
        math.isclose(
            float(adapter_metadata["checkpoint_load_factor"]),
            float(audit["load_factor"]),
            rel_tol=0.0,
            abs_tol=0.0,
        )
        and math.isclose(
            float(audit["load_factor"]),
            0.656,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    )
    component_audit = adapter_metadata["initial_state_component_audit"]
    frame_connectivity_audit = adapter_metadata[
        "frame_connectivity_audit"
    ]
    frame_property_coverage_audit = adapter_metadata[
        "frame_source_property_coverage_audit"
    ]
    zero_map_audit = adapter_metadata["zero_to_unit_free_map_audit"]
    zero_predictor_audit = adapter_metadata[
        "zero_state_sparse_predictor_audit"
    ]
    semantic_load_audit = adapter_metadata["semantic_load_assembly"]
    material_binding = adapter_metadata[
        "material_analysis_property_binding"
    ]
    dgn_alias_audit = adapter_metadata[
        "dgn_material_property_alias_audit"
    ]
    state_invariant_tangent = adapter_metadata[
        "state_invariant_tangent_contract"
    ]
    reference_preconditioner = adapter_metadata[
        "reference_preconditioner_contract"
    ]
    component_audit_pass = bool(
        component_audit["component_sum_matches_internal_exact"]
        and math.isclose(
            float(component_audit["residual_inf_n"]) / 1000.0,
            float(audit["residual_inf_norm_kn"]),
            rel_tol=1.0e-12,
            abs_tol=1.0e-6,
        )
    )
    contract_pass = bool(
        audit["contract_pass"]
        and parser_contract_pass
        and fixed_case_dimensions_pass
        and checkpoint_binding_pass
        and component_audit_pass
        and adapter_metadata["source_material_properties_consumed"]
        and frame_connectivity_audit["frame_connectivity_source"]
        == "elem_conn_ptr/elem_conn_idx"
        and not frame_connectivity_audit[
            "edge_index_used_for_element_binding"
        ]
        and frame_connectivity_audit[
            "skipped_invalid_line_connectivity_count"
        ]
        == 0
        and frame_connectivity_audit["line_element_row_accounting_exact"]
        and adapter_metadata["actual_mgt_semantic_load_case_consumed"]
        and semantic_load_audit["selected_case_row_accounting_exact"]
        and semantic_load_audit["unsupported_selected_row_count"] == 0
        and material_binding["resolution_policy"]
        == "MATERIAL_rows_only.v1"
        and not material_binding["dgn_alias_resolution_enabled"]
        and material_binding["dgn_alias_material_count_applied"] == 0
        and not material_binding["engineer_review_required"]
        and dgn_alias_audit["contract_pass"]
        and dgn_alias_audit[
            "dgn_numeric_elastic_override_consumed_count"
        ]
        == 0
        and dgn_alias_audit["fuzzy_name_match_count"] == 0
        and state_invariant_tangent["available"]
        and state_invariant_tangent[
            "exact_for_adapter_residual_model"
        ]
        and reference_preconditioner["available"]
        and reference_preconditioner["intended_use"]
        == "fixed_right_preconditioner"
        and reference_preconditioner[
            "exact_for_adapter_residual_model"
        ]
        and not reference_preconditioner[
            "approximate_for_state_dependent_adapter"
        ]
        and reference_preconditioner["operator_numeric_values_hash"]
        == state_invariant_tangent["operator_numeric_values_hash"]
    )
    claims = {
        "actual_mgt_frame_shell_spring_residual_adapter_evaluated": bool(
            audit["claims"]["actual_mgt_residual_adapter_evaluated"]
        ),
        "source_material_properties_consumed": bool(
            adapter_metadata["source_material_properties_consumed"]
        ),
        "all_frame_source_material_properties_resolved": bool(
            adapter_metadata[
                "all_frame_source_material_properties_resolved"
            ]
        ),
        "authoritative_element_connectivity_consumed": bool(
            frame_connectivity_audit["frame_connectivity_source"]
            == "elem_conn_ptr/elem_conn_idx"
            and not frame_connectivity_audit[
                "edge_index_used_for_element_binding"
            ]
            and frame_connectivity_audit[
                "skipped_invalid_line_connectivity_count"
            ]
            == 0
            and frame_connectivity_audit[
                "line_element_row_accounting_exact"
            ]
        ),
        "actual_mgt_semantic_load_case_consumed": bool(
            adapter_metadata["actual_mgt_semantic_load_case_consumed"]
            and semantic_load_audit["selected_case_row_accounting_exact"]
            and semantic_load_audit["unsupported_selected_row_count"] == 0
        ),
        "full_unit_semantic_live_predictor_binary_artifact": bool(
            predictor_vector_artifact["residual_gate_passed"]
        ),
        "state_invariant_linear_reference_tangent_bound": bool(
            state_invariant_tangent["available"]
            and state_invariant_tangent[
                "exact_for_adapter_residual_model"
            ]
            and not state_invariant_tangent[
                "nonlinear_current_tangent_claim"
            ]
        ),
        "load_factor_coupled_residual_and_derivative_audited": bool(
            audit["negative_load_derivative_gate_passed"]
        ),
        "two_step_centered_tangent_action_audited": bool(
            audit["tangent_step_comparison_gate_passed"]
        ),
        "initial_state_component_breakdown_recorded": component_audit_pass,
        "zero_to_unit_fixed_free_map_compatible": bool(
            zero_map_audit["fixed_free_map_exact"]
            and zero_map_audit[
                "zero_tangent_on_unit_map_zero_row_count"
            ]
            == 0
            and zero_map_audit[
                "zero_tangent_on_unit_map_zero_diagonal_count"
            ]
            == 0
        ),
        "zero_state_sparse_direct_predictor_contract": bool(
            zero_predictor_audit["contract_pass"]
        ),
        "initial_checkpoint_physical_residual_gate": bool(
            audit["residual_equilibrium_gate_passed"]
        ),
        "stored_direct_residual_receipt_equivalence": bool(
            comparison["stored_receipt_equivalent_to_current_adapter"]
        ),
        "stored_direct_residual_receipt_replay_provenance_complete": bool(
            comparison["stored_receipt_replay_provenance_complete"]
        ),
        "full_arc_length_continuation": False,
        "large_vector_binary_trace": False,
        "engine_v2_production_matrix_free_krylov": False,
        "material_state_commit_rollback": False,
        "production_rocm_hip_nonlinear_parity": False,
        "load_1p0_checkpoint": False,
        "g1_full_building_closure": False,
    }
    blockers = [
        "source_commit_exact_replay_not_claimed_for_dirty_worktree",
        "current_direct_probe_replay_not_executed_by_adapter_receipt_builder",
        "historical_checkpoint_reference_load_contract_not_proven_live",
    ]
    if not claims["actual_mgt_semantic_load_case_consumed"]:
        blockers.append("actual_mgt_semantic_load_case_not_connected")
    if not claims["all_frame_source_material_properties_resolved"]:
        blockers.append(
            "frame_source_material_property_binding_incomplete"
        )
    if not claims["initial_checkpoint_physical_residual_gate"]:
        blockers.append("initial_checkpoint_physical_residual_gate_failed")
    if not claims["zero_to_unit_fixed_free_map_compatible"]:
        blockers.append(
            "zero_to_unit_load_fixed_free_map_or_tangent_incompatible"
        )
    if not claims["zero_state_sparse_direct_predictor_contract"]:
        blockers.append("zero_state_sparse_direct_predictor_contract_failed")
    if not claims["state_invariant_linear_reference_tangent_bound"]:
        blockers.append(
            "state_invariant_linear_reference_tangent_not_bound"
        )
    if not claims["stored_direct_residual_receipt_equivalence"]:
        blockers.append(
            "current_source_diverges_from_stored_direct_residual_receipt"
        )
    if not claims[
        "stored_direct_residual_receipt_replay_provenance_complete"
    ]:
        blockers.append(
            "stored_direct_residual_receipt_missing_source_commit_or_checksums"
        )
    blockers.extend(audit["blockers_remaining"])
    blockers = list(dict.fromkeys(str(item) for item in blockers))
    checksums = input_checksums(
        _input_paths(
            mgt_path=mgt_path,
            checkpoint_npz=checkpoint_npz,
            stored_direct_receipt=stored_direct_receipt,
        ),
        repo_root=repo_root,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    artifacts = {
        "receipt": _label(repo_root, receipt_out),
        "summary": _label(repo_root, summary_out),
        "schema": str(SCHEMA_PATH),
        "full_unit_predictor_vector": _label(
            repo_root,
            predictor_vector_out,
        ),
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "evidence_closure_pass": False,
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "source_commit_exact_replay_claim": False,
        "source_tree_state": "working_tree_with_uncommitted_goal_changes",
        "input_checksums": checksums,
        "case_id": problem.case_id,
        "adapter_metadata": adapter_metadata,
        "initial_state_audit": audit,
        "stored_receipt_comparison": comparison,
        "claims": claims,
        "blockers_remaining": blockers,
        "artifacts": artifacts,
        "claim_boundary": MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY,
    }
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": receipt["status"],
        "contract_pass": contract_pass,
        "evidence_closure_pass": False,
        "source_commit_sha": receipt["source_commit_sha"],
        "engine_version": receipt["engine_version"],
        "source_commit_exact_replay_claim": False,
        "input_checksums": checksums,
        "case_id": problem.case_id,
        "node_count": adapter_metadata["node_count"],
        "frame_element_count": adapter_metadata["frame_element_count"],
        "frame_connectivity_audit": frame_connectivity_audit,
        "frame_source_property_coverage_audit": (
            frame_property_coverage_audit
        ),
        "material_analysis_property_binding": material_binding,
        "dgn_material_property_alias_audit": dgn_alias_audit,
        "reference_preconditioner_contract": reference_preconditioner,
        "global_dof_count": adapter_metadata["global_dof_count"],
        "free_equation_count": adapter_metadata["free_equation_count"],
        "checkpoint_load_factor": adapter_metadata["checkpoint_load_factor"],
        "reference_load_inf_n": adapter_metadata["reference_load_inf_n"],
        "reference_load_contract": adapter_metadata[
            "reference_load_contract"
        ],
        "semantic_load_assembly": semantic_load_audit,
        "full_unit_predictor_vector_artifact": predictor_vector_artifact,
        "source_material_properties_consumed": adapter_metadata[
            "source_material_properties_consumed"
        ],
        "all_frame_source_material_properties_resolved": adapter_metadata[
            "all_frame_source_material_properties_resolved"
        ],
        "material_state_commit_rollback_connected": adapter_metadata[
            "material_state_commit_rollback_connected"
        ],
        "initial_residual_inf_n": (
            float(audit["residual_inf_norm_kn"]) * 1000.0
        ),
        "initial_residual_equilibrium_gate_passed": audit[
            "residual_equilibrium_gate_passed"
        ],
        "zero_state_start_gate": {
            "fixed_free_map_exact": zero_map_audit[
                "fixed_free_map_exact"
            ],
            "zero_state_free_equation_count": zero_map_audit[
                "zero_state_free_equation_count"
            ],
            "unit_load_free_equation_count": zero_map_audit[
                "unit_load_free_equation_count"
            ],
            "zero_tangent_structural_rank_deficiency": zero_map_audit[
                "zero_tangent_structural_rank_deficiency"
            ],
            "free_graph_component_count": zero_map_audit[
                "free_graph_component_count"
            ],
            "free_graph_unanchored_component_count": zero_map_audit[
                "free_graph_unanchored_component_count"
            ],
            "free_graph_unanchored_loaded_component_count": zero_map_audit[
                "free_graph_unanchored_loaded_component_count"
            ],
            "free_graph_loaded_component_count": zero_map_audit[
                "free_graph_loaded_component_count"
            ],
            "free_graph_unanchored_loaded_components": zero_map_audit[
                "free_graph_unanchored_loaded_components"
            ],
            "zero_state_equilibrium_gate_passed": zero_predictor_audit[
                "zero_state_equilibrium_gate_passed"
            ],
            "zero_state_load_direction_gate_passed": zero_predictor_audit[
                "zero_state_load_direction_gate_passed"
            ],
            "sparse_direct_solve_attempted": zero_predictor_audit[
                "sparse_direct_solve_attempted"
            ],
            "loaded_component_count": zero_predictor_audit[
                "loaded_component_count"
            ],
            "solved_component_count": zero_predictor_audit[
                "solved_component_count"
            ],
            "sparse_predictor_contract_pass": zero_predictor_audit[
                "contract_pass"
            ],
            "sparse_predictor_failure": zero_predictor_audit["failure"],
        },
        "dominant_initial_internal_force_component": component_audit[
            "dominant_component_by_free_inf"
        ],
        "dominant_initial_residual_argmax_component": component_audit[
            "dominant_component_at_residual_argmax"
        ],
        "initial_component_internal_force_free_inf_n": component_audit[
            "component_internal_force_free_inf_n"
        ],
        "initial_residual_argmax_global_dof_index": component_audit[
            "residual_argmax_global_dof_index"
        ],
        "initial_residual_argmax_node_id": component_audit[
            "residual_argmax_node_id"
        ],
        "initial_residual_argmax_dof_label": component_audit[
            "residual_argmax_dof_label"
        ],
        "initial_residual_hotspot_connected_frame_element_count": (
            component_audit["hotspot_connected_frame_element_count"]
        ),
        "initial_residual_hotspot_dominant_frame_element_id": (
            component_audit["hotspot_dominant_frame_element_id"]
        ),
        "initial_residual_hotspot_maximum_frame_force_inf_n": (
            component_audit[
                "hotspot_maximum_connected_frame_force_inf_n"
            ]
        ),
        "initial_residual_hotspot_connected_shell_element_count": (
            component_audit["hotspot_connected_shell_element_count"]
        ),
        "initial_residual_hotspot_maximum_translation_jump_m": (
            component_audit[
                "hotspot_maximum_perimeter_translation_jump_m"
            ]
        ),
        "initial_residual_hotspot_maximum_edge_strain_abs": (
            component_audit[
                "hotspot_maximum_perimeter_edge_engineering_strain_abs"
            ]
        ),
        "maximum_negative_load_derivative_error_kn": audit[
            "maximum_negative_load_derivative_error_kn"
        ],
        "negative_load_derivative_relative_error": audit[
            "negative_load_derivative_relative_error"
        ],
        "negative_load_derivative_gate_passed": audit[
            "negative_load_derivative_gate_passed"
        ],
        "maximum_tangent_step_comparison_error_kn": audit[
            "maximum_tangent_step_comparison_error_kn"
        ],
        "tangent_step_comparison_relative_error": audit[
            "tangent_step_comparison_relative_error"
        ],
        "tangent_step_comparison_gate_passed": audit[
            "tangent_step_comparison_gate_passed"
        ],
        "stored_base_direct_residual_inf_n": comparison[
            "stored_base_direct_residual_inf_n"
        ],
        "current_to_stored_residual_ratio": comparison[
            "current_to_stored_ratio"
        ],
        "stored_receipt_equivalent_to_current_adapter": comparison[
            "stored_receipt_equivalent_to_current_adapter"
        ],
        "stored_receipt_replay_provenance_complete": comparison[
            "stored_receipt_replay_provenance_complete"
        ],
        "claims": claims,
        "blockers_remaining": blockers,
        "artifacts": artifacts,
        "claim_boundary": MGT_LOAD_COUPLED_ADAPTER_CLAIM_BOUNDARY,
    }
    return {"receipt": receipt, "summary": summary}


def check_g1_mgt_load_coupled_arc_length_adapter_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    stored_direct_receipt: Path = DEFAULT_STORED_DIRECT_RECEIPT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    predictor_vector_out: Path = DEFAULT_PREDICTOR_VECTOR_OUT,
) -> tuple[bool, str]:
    for label, relative in (("receipt", receipt_out), ("summary", summary_out)):
        if not _resolve(repo_root, relative).is_file():
            return False, f"g1_mgt_load_coupled_adapter_missing:{label}"
    expected = build_g1_mgt_load_coupled_arc_length_adapter_receipt(
        repo_root=repo_root,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        stored_direct_receipt=stored_direct_receipt,
        receipt_out=receipt_out,
        summary_out=summary_out,
        predictor_vector_out=predictor_vector_out,
    )
    for label, relative in (("receipt", receipt_out), ("summary", summary_out)):
        try:
            existing = _read_json(_resolve(repo_root, relative))
        except Exception as exc:
            return False, (
                f"g1_mgt_load_coupled_adapter_unreadable:{label}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[label]):
            return False, f"g1_mgt_load_coupled_adapter_mismatch:{label}"
    predictor_path = _resolve(repo_root, predictor_vector_out)
    if not predictor_path.is_file():
        return False, "g1_mgt_load_coupled_adapter_missing:predictor_vector"
    descriptor = expected["receipt"]["adapter_metadata"][
        "full_unit_predictor_vector_artifact"
    ]
    if (
        predictor_path.stat().st_size != descriptor["byte_length"]
        or file_sha256(predictor_path) != descriptor["data_sha256"]
    ):
        return False, "g1_mgt_load_coupled_adapter_mismatch:predictor_vector"
    return True, "g1_mgt_load_coupled_adapter_consistent"


def write_g1_mgt_load_coupled_arc_length_adapter_receipt(
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    receipt_out = Path(kwargs.get("receipt_out", DEFAULT_RECEIPT_OUT))
    summary_out = Path(kwargs.get("summary_out", DEFAULT_SUMMARY_OUT))
    build_kwargs = dict(kwargs)
    build_kwargs["_write_predictor_vector"] = True
    payloads = build_g1_mgt_load_coupled_arc_length_adapter_receipt(
        **build_kwargs
    )
    for label, relative in (("receipt", receipt_out), ("summary", summary_out)):
        path = _resolve(repo_root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payloads[label]), encoding="utf-8")
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--stored-direct-receipt",
        type=Path,
        default=DEFAULT_STORED_DIRECT_RECEIPT,
    )
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument(
        "--predictor-vector-out",
        type=Path,
        default=DEFAULT_PREDICTOR_VECTOR_OUT,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    kwargs = {
        "repo_root": ROOT,
        "mgt_path": args.mgt_path,
        "checkpoint_npz": args.checkpoint_npz,
        "stored_direct_receipt": args.stored_direct_receipt,
        "receipt_out": args.receipt_out,
        "summary_out": args.summary_out,
        "predictor_vector_out": args.predictor_vector_out,
    }
    if args.check:
        ok, message = check_g1_mgt_load_coupled_arc_length_adapter_receipt(
            **kwargs
        )
        print(message)
        return 0 if ok else 1
    payloads = write_g1_mgt_load_coupled_arc_length_adapter_receipt(**kwargs)
    summary = payloads["summary"]
    print(
        f"{summary['status']} | equations={summary['free_equation_count']} | "
        f"load={summary['checkpoint_load_factor']} | "
        f"initial_residual_n={summary['initial_residual_inf_n']:.12g} | "
        "g1_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
