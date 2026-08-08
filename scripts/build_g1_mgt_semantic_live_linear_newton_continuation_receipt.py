#!/usr/bin/env python3
"""Build the actual-MGT linear-reference Newton continuation receipt."""

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
    build_real_mgt_load_coupled_arc_length_problem,
)
from g1_mgt_semantic_live_linear_newton_continuation import (  # noqa: E402
    LinearReferenceNewtonCheckpoint,
    LinearReferenceNewtonConfig,
    run_linear_reference_newton_continuation,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
)
DEFAULT_OPERATOR_CHECKPOINT = (
    PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_relaxed_checkpoints/"
    "accepted_load_0p656.npz"
)
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION / "g1_mgt_semantic_live_linear_newton_continuation_receipt.json"
)
DEFAULT_SUMMARY_OUT = (
    PRODUCTIZATION / "g1_mgt_semantic_live_linear_newton_continuation_summary.json"
)
DEFAULT_RESTART_VECTOR_OUT = (
    PRODUCTIZATION
    / "g1_mgt_semantic_live_linear_newton_restart_0p75_free_displacement.f64le"
)
DEFAULT_FULL_LOAD_VECTOR_OUT = (
    PRODUCTIZATION
    / "g1_mgt_semantic_live_linear_newton_full_load_free_displacement.f64le"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_semantic_live_linear_newton_continuation_v1.schema.json"
)
RECEIPT_SCHEMA_VERSION = "g1-mgt-semantic-live-linear-newton-continuation-receipt.v1"
SUMMARY_SCHEMA_VERSION = "g1-mgt-semantic-live-linear-newton-continuation-summary.v1"
VECTOR_SCHEMA_VERSION = "g1-mgt-semantic-live-linear-newton-checkpoint-vector.v1"
CLAIM_BOUNDARY = (
    "This receipt proves deterministic zero-state adaptive load-controlled "
    "Newton control flow for the current actual-MGT semantic LIVE adapter "
    "using its state-invariant linear reference-geometry CSR Jacobian. It "
    "does not prove a raw-*MATERIAL-complete model. An exact unique type/name "
    "source-derived DGN-MATL alias contract is available for this input, but "
    "the aliases are not applied by this linear-reference path and remain "
    "engineer-review-required. The receipt also does not prove a state-updated "
    "nonlinear tangent, quadratic convergence, material commit/rollback, "
    "arc-length branch, production Krylov/HIP execution, G1 checkpoint, or "
    "G1 closure."
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


def _vector_bytes(values: np.ndarray) -> bytes:
    canonical = np.ascontiguousarray(values, dtype="<f8")
    return memoryview(canonical).cast("B").tobytes()


def _bytes_sha256(values: bytes) -> str:
    return "sha256:" + hashlib.sha256(values).hexdigest()


def _checkpoint_vector_artifact(
    *,
    repo_root: Path,
    output_path: Path,
    role: str,
    checkpoint: LinearReferenceNewtonCheckpoint,
    problem: Any,
    tolerance_n: float,
) -> tuple[dict[str, Any], bytes]:
    raw = _vector_bytes(checkpoint.free_displacements_m)
    residual_inf_n = float(
        np.linalg.norm(
            problem.residual_free_n(
                checkpoint.free_displacements_m,
                checkpoint.load_factor,
            ),
            ord=np.inf,
        )
    )
    return {
        "schema_version": VECTOR_SCHEMA_VERSION,
        "status": "ready" if residual_inf_n <= tolerance_n else "blocked",
        "role": role,
        "artifact_path": _label(repo_root, output_path),
        "dtype": "<f8",
        "layout": "C",
        "byte_order": "little",
        "equation_order": "adapter_free_global_dof_order",
        "equation_count": int(checkpoint.free_displacements_m.size),
        "byte_length": len(raw),
        "data_sha256": _bytes_sha256(raw),
        "checkpoint": checkpoint.descriptor(),
        "residual_inf_n": residual_inf_n,
        "residual_tolerance_n": tolerance_n,
        "residual_gate_passed": bool(residual_inf_n <= tolerance_n),
        "linear_reference_geometry_checkpoint": True,
        "persisted_nonlinear_continuation_checkpoint": False,
        "g1_full_load_checkpoint_claim": False,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "A deterministic little-endian free-DOF vector for one accepted "
            "state of the linear reference-geometry diagnostic only."
        ),
    }, raw


def _reload_checkpoint(
    *,
    checkpoint: LinearReferenceNewtonCheckpoint,
    raw: bytes,
) -> LinearReferenceNewtonCheckpoint:
    values = np.frombuffer(raw, dtype="<f8").copy()
    return LinearReferenceNewtonCheckpoint(
        schema_version=checkpoint.schema_version,
        case_id=checkpoint.case_id,
        path_contract_hash=checkpoint.path_contract_hash,
        step_index=checkpoint.step_index,
        load_factor=checkpoint.load_factor,
        free_displacements_m=values,
        state_hash=checkpoint.state_hash,
        source_commit_sha=checkpoint.source_commit_sha,
        model_source_sha256=checkpoint.model_source_sha256,
        equilibrium_operator_binding_hash=(
            checkpoint.equilibrium_operator_binding_hash
        ),
    )


def _rollback_probe_config() -> LinearReferenceNewtonConfig:
    return LinearReferenceNewtonConfig(
        target_load_factor=0.25,
        initial_load_increment=0.25,
        minimum_load_increment=0.25,
        maximum_load_increment=0.25,
        successful_step_growth=1.0,
        failed_step_reduction=0.5,
        maximum_attempt_count=2,
        maximum_newton_iterations=1,
    )


def _input_paths(
    *,
    mgt_path: Path,
    operator_checkpoint: Path,
) -> list[Path]:
    return [
        mgt_path,
        operator_checkpoint,
        Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
        Path(
            "implementation/phase1/g1_mgt_semantic_live_linear_newton_continuation.py"
        ),
        Path("implementation/phase1/mgt_frame_force_based_assembly.py"),
        Path("implementation/phase1/mgt_physical_residual_assembly.py"),
        Path("implementation/phase1/mgt_semantic_load_assembly.py"),
        Path("implementation/phase1/parse_mgt_section_material_properties.py"),
        Path("implementation/phase1/parse_midas_mgt_to_json_npz.py"),
        Path("src/structural_analysis/engine_v2/contracts/current_tangent_operator.py"),
        Path("src/structural_analysis/schemas/current_tangent_operator_v1.schema.json"),
        SCHEMA_PATH,
        Path(
            "scripts/build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py"
        ),
        Path("tests/test_g1_mgt_semantic_live_linear_newton_continuation.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path(
            "tests/"
            "test_build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py"
        ),
    ]


def build_g1_mgt_semantic_live_linear_newton_continuation_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    operator_checkpoint: Path = DEFAULT_OPERATOR_CHECKPOINT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    restart_vector_out: Path = DEFAULT_RESTART_VECTOR_OUT,
    full_load_vector_out: Path = DEFAULT_FULL_LOAD_VECTOR_OUT,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    repo_root = repo_root.resolve()
    problem, adapter_metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=_resolve(repo_root, mgt_path),
        roundtrip_npz=None,
        checkpoint_npz=_resolve(repo_root, operator_checkpoint),
    )
    zero_problem = problem.zero_state_problem()
    config = LinearReferenceNewtonConfig()
    direct = run_linear_reference_newton_continuation(
        problem=zero_problem,
        config=config,
    )
    restart_candidates = [
        row
        for row in direct.checkpoints
        if math.isclose(
            row.load_factor,
            0.75,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    ]
    if len(restart_candidates) != 1:
        raise ValueError("direct continuation must contain one lambda=0.75 state")
    restart_checkpoint = restart_candidates[0]
    restart_artifact, restart_raw = _checkpoint_vector_artifact(
        repo_root=repo_root,
        output_path=restart_vector_out,
        role="restart_checkpoint",
        checkpoint=restart_checkpoint,
        problem=zero_problem,
        tolerance_n=config.residual_tolerance_n,
    )
    reloaded_checkpoint = _reload_checkpoint(
        checkpoint=restart_checkpoint,
        raw=restart_raw,
    )
    restarted = run_linear_reference_newton_continuation(
        problem=zero_problem,
        config=config,
        checkpoint=reloaded_checkpoint,
    )
    full_load_artifact, full_load_raw = _checkpoint_vector_artifact(
        repo_root=repo_root,
        output_path=full_load_vector_out,
        role="full_load_checkpoint",
        checkpoint=direct.final_checkpoint,
        problem=zero_problem,
        tolerance_n=config.residual_tolerance_n,
    )
    rollback_probe = run_linear_reference_newton_continuation(
        problem=zero_problem,
        config=_rollback_probe_config(),
    )

    direct_final_raw = _vector_bytes(direct.final_checkpoint.free_displacements_m)
    restarted_final_raw = _vector_bytes(restarted.final_checkpoint.free_displacements_m)
    restart_replay = {
        "status": "ready",
        "serialized_checkpoint_load_factor": (reloaded_checkpoint.load_factor),
        "serialized_checkpoint_data_sha256": _bytes_sha256(restart_raw),
        "serialized_checkpoint_state_hash": reloaded_checkpoint.state_hash,
        "checkpoint_state_hash_validated_on_reload": True,
        "serialization_roundtrip_byte_exact": bool(
            np.array_equal(
                reloaded_checkpoint.free_displacements_m,
                restart_checkpoint.free_displacements_m,
            )
        ),
        "restart_checkpoint_consumed": bool(
            restarted.metrics["restart_checkpoint_consumed"]
        ),
        "direct_final_data_sha256": _bytes_sha256(direct_final_raw),
        "restarted_final_data_sha256": _bytes_sha256(restarted_final_raw),
        "final_displacement_bytes_identical": bool(
            direct_final_raw == restarted_final_raw
        ),
        "direct_final_state_hash": direct.final_checkpoint.state_hash,
        "restarted_final_state_hash": restarted.final_checkpoint.state_hash,
        "final_state_hash_identical": bool(
            direct.final_checkpoint.state_hash == restarted.final_checkpoint.state_hash
        ),
        "direct_final_residual_inf_n": direct.metrics["final_residual_inf_n"],
        "restarted_final_residual_inf_n": restarted.metrics["final_residual_inf_n"],
    }
    restart_replay["contract_pass"] = bool(
        restarted.status == "ready"
        and restart_replay["serialization_roundtrip_byte_exact"]
        and restart_replay["restart_checkpoint_consumed"]
        and restart_replay["final_displacement_bytes_identical"]
        and restart_replay["final_state_hash_identical"]
    )
    restart_replay["status"] = "ready" if restart_replay["contract_pass"] else "blocked"

    rollback_metrics = rollback_probe.metrics
    rollback_contract_pass = bool(
        rollback_probe.status == "partial"
        and rollback_probe.terminal_reason == "minimum_load_increment_exhausted"
        and rollback_metrics["failed_step_count"] == 1
        and rollback_metrics["failed_step_rollback_exercised"]
        and rollback_metrics["rollback_exact"]
        and rollback_probe.final_checkpoint.load_factor == 0.0
        and np.count_nonzero(rollback_probe.final_checkpoint.free_displacements_m) == 0
    )
    rollback_audit = {
        **rollback_probe.to_dict(),
        "actual_linear_failed_step_rollback_contract_pass": (rollback_contract_pass),
    }

    property_coverage = adapter_metadata["frame_source_property_coverage_audit"]
    adapter_binding = {
        "case_id": zero_problem.case_id,
        "initial_state_policy": zero_problem.initial_state_policy,
        "initial_load_factor": zero_problem.initial_load_factor(),
        "historical_checkpoint_free_vector_used_as_initial_state": False,
        "historical_checkpoint_used_for_operator_binding": True,
        "historical_checkpoint_nonfree_displacement_inf_m": (
            adapter_metadata["checkpoint_nonfree_displacement_inf_m"]
        ),
        "node_count": adapter_metadata["node_count"],
        "global_dof_count": adapter_metadata["global_dof_count"],
        "free_equation_count": adapter_metadata["free_equation_count"],
        "free_dof_hash": adapter_metadata["free_dof_hash"],
        "reference_load_free_hash": adapter_metadata["reference_load_free_hash"],
        "reference_load_inf_n": adapter_metadata["reference_load_inf_n"],
        "semantic_load_assembly": adapter_metadata["semantic_load_assembly"],
        "state_invariant_tangent_contract": adapter_metadata[
            "state_invariant_tangent_contract"
        ],
        "frame_source_property_coverage_audit": property_coverage,
        "material_analysis_property_binding": adapter_metadata[
            "material_analysis_property_binding"
        ],
        "dgn_material_property_alias_audit": adapter_metadata[
            "dgn_material_property_alias_audit"
        ],
        "all_frame_source_material_properties_resolved": adapter_metadata[
            "all_frame_source_material_properties_resolved"
        ],
        "state_updated_frame_axial_geometry_applied": adapter_metadata[
            "apply_state_updated_frame_axial_geometry"
        ],
    }
    direct_payload = direct.to_dict()
    direct_claims = direct_payload["claims"]
    tangent_contract = adapter_binding["state_invariant_tangent_contract"]
    material_binding = adapter_binding["material_analysis_property_binding"]
    dgn_alias_audit = adapter_binding["dgn_material_property_alias_audit"]
    contract_pass = bool(
        direct.status == "ready"
        and direct.final_checkpoint.load_factor == 1.0
        and direct.metrics["residual_gate_passed"]
        and direct.metrics["fallback_count"] == 0
        and direct.metrics["regularization_count"] == 0
        and direct.tangent_consistency_audit["all_gates_passed"]
        and direct_claims["actual_mgt_semantic_live_load"]
        and direct_claims["full_load_linear_reference_checkpoint"]
        and restart_replay["contract_pass"]
        and rollback_contract_pass
        and restart_artifact["residual_gate_passed"]
        and full_load_artifact["residual_gate_passed"]
        and tangent_contract["exact_for_adapter_residual_model"]
        and zero_problem.initial_state_policy == "zero_state"
        and zero_problem.initial_load_factor() == 0.0
        and np.count_nonzero(zero_problem.initial_free_displacements_m()) == 0
        and adapter_binding["historical_checkpoint_nonfree_displacement_inf_m"] == 0.0
    )
    claims = {
        "actual_mgt_semantic_live_load_consumed": bool(
            direct_claims["actual_mgt_semantic_live_load"]
        ),
        "zero_state_initial_policy": True,
        "adaptive_load_controlled_newton_path": bool(
            direct_claims["adaptive_load_stepping"]
        ),
        "line_search_history_recorded": bool(
            direct_claims["line_search_history_recorded"]
        ),
        "state_invariant_linear_reference_tangent": True,
        "full_load_linear_reference_checkpoint": bool(
            direct_claims["full_load_linear_reference_checkpoint"]
        ),
        "persisted_linear_reference_restart_checkpoint": bool(
            restart_artifact["residual_gate_passed"]
        ),
        "persisted_linear_reference_full_load_checkpoint": bool(
            full_load_artifact["residual_gate_passed"]
        ),
        "restart_replay_byte_identical": bool(restart_replay["contract_pass"]),
        "actual_linear_failed_step_rollback_exact": (rollback_contract_pass),
        "source_property_coverage_complete": bool(
            adapter_binding["all_frame_source_material_properties_resolved"]
        ),
        "raw_material_table_property_coverage_complete": bool(
            adapter_binding["all_frame_source_material_properties_resolved"]
        ),
        "dgn_exact_type_name_alias_contract_pass": bool(
            dgn_alias_audit["contract_pass"]
        ),
        "dgn_alias_applied_to_linear_reference_adapter": bool(
            material_binding["dgn_alias_resolution_enabled"]
        ),
        "dgn_alias_engineer_review_required": bool(
            dgn_alias_audit["engineer_review_required"]
        ),
        "dgn_numeric_elastic_override_consumed": bool(
            dgn_alias_audit["dgn_numeric_elastic_override_consumed_count"]
        ),
        "nonlinear_current_tangent": False,
        "quadratic_convergence": False,
        "material_state_commit_rollback": False,
        "full_arc_length_continuation": False,
        "production_matrix_free_krylov": False,
        "production_rocm_hip_nonlinear_parity": False,
        "g1_full_load_checkpoint": False,
        "g1_full_building_closure": False,
    }
    blockers = [
        "source_commit_exact_replay_not_claimed_for_dirty_worktree",
        "raw_material_table_binding_incomplete_source_derived_alias_available",
        "dgn_exact_type_name_material_inheritance_engineer_review_required",
        "state_updated_nonlinear_current_tangent_not_connected",
        "quadratic_convergence_not_demonstrated",
        "material_state_commit_rollback_not_connected",
        "nonlinear_failed_step_rollback_not_demonstrated",
        "arc_length_branch_not_executed",
        "production_matrix_free_krylov_not_connected",
        "production_rocm_hip_nonlinear_parity_not_verified",
        "g1_full_load_checkpoint_not_created",
    ]
    if claims["raw_material_table_property_coverage_complete"]:
        blockers.remove(
            "raw_material_table_binding_incomplete_source_derived_alias_available"
        )
    if not claims["dgn_alias_engineer_review_required"]:
        blockers.remove(
            "dgn_exact_type_name_material_inheritance_engineer_review_required"
        )
    checksums = input_checksums(
        _input_paths(
            mgt_path=mgt_path,
            operator_checkpoint=operator_checkpoint,
        ),
        repo_root=repo_root,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    artifacts = {
        "receipt": _label(repo_root, receipt_out),
        "summary": _label(repo_root, summary_out),
        "schema": str(SCHEMA_PATH),
        "restart_checkpoint_vector": _label(
            repo_root,
            restart_vector_out,
        ),
        "full_load_checkpoint_vector": _label(
            repo_root,
            full_load_vector_out,
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
        "case_id": zero_problem.case_id,
        "adapter_binding": adapter_binding,
        "direct_continuation": direct_payload,
        "restart_checkpoint_artifact": restart_artifact,
        "full_load_checkpoint_artifact": full_load_artifact,
        "restart_replay_audit": restart_replay,
        "failed_step_rollback_audit": rollback_audit,
        "claims": claims,
        "blockers_remaining": blockers,
        "artifacts": artifacts,
        "claim_boundary": CLAIM_BOUNDARY,
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
        "case_id": zero_problem.case_id,
        "operator_classification": direct_payload["operator_classification"],
        "free_equation_count": zero_problem.equation_count,
        "checkpoint_load_factors": [row.load_factor for row in direct.checkpoints],
        "final_residual_inf_n": direct.metrics["final_residual_inf_n"],
        "maximum_tangent_solve_explicit_residual_inf_n": direct.metrics[
            "maximum_tangent_solve_explicit_residual_inf_n"
        ],
        "maximum_tangent_consistency_error_inf_kn": (
            direct.tangent_consistency_audit["maximum_error_inf_kn"]
        ),
        "restart_replay_byte_identical": restart_replay[
            "final_displacement_bytes_identical"
        ],
        "actual_linear_failed_step_rollback_exact": (rollback_contract_pass),
        "source_property_coverage_complete": claims[
            "source_property_coverage_complete"
        ],
        "raw_material_table_property_coverage_complete": claims[
            "raw_material_table_property_coverage_complete"
        ],
        "dgn_exact_type_name_alias_contract_pass": claims[
            "dgn_exact_type_name_alias_contract_pass"
        ],
        "dgn_alias_engineer_review_required": claims[
            "dgn_alias_engineer_review_required"
        ],
        "claims": claims,
        "blockers_remaining": blockers,
        "artifacts": artifacts,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return (
        {"receipt": receipt, "summary": summary},
        {
            "restart_checkpoint_vector": restart_raw,
            "full_load_checkpoint_vector": full_load_raw,
        },
    )


def check_g1_mgt_semantic_live_linear_newton_continuation_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    operator_checkpoint: Path = DEFAULT_OPERATOR_CHECKPOINT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    restart_vector_out: Path = DEFAULT_RESTART_VECTOR_OUT,
    full_load_vector_out: Path = DEFAULT_FULL_LOAD_VECTOR_OUT,
) -> tuple[bool, str]:
    outputs = (
        ("receipt", receipt_out),
        ("summary", summary_out),
        ("restart_checkpoint_vector", restart_vector_out),
        ("full_load_checkpoint_vector", full_load_vector_out),
    )
    for label, relative in outputs:
        if not _resolve(repo_root, relative).is_file():
            return False, f"g1_linear_newton_continuation_missing:{label}"
    expected_payloads, expected_binaries = (
        build_g1_mgt_semantic_live_linear_newton_continuation_receipt(
            repo_root=repo_root,
            mgt_path=mgt_path,
            operator_checkpoint=operator_checkpoint,
            receipt_out=receipt_out,
            summary_out=summary_out,
            restart_vector_out=restart_vector_out,
            full_load_vector_out=full_load_vector_out,
        )
    )
    for label, relative in (("receipt", receipt_out), ("summary", summary_out)):
        try:
            existing = _read_json(_resolve(repo_root, relative))
        except Exception as exc:
            return False, (
                f"g1_linear_newton_continuation_unreadable:{label}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected_payloads[label]):
            return False, f"g1_linear_newton_continuation_mismatch:{label}"
    binary_paths = {
        "restart_checkpoint_vector": restart_vector_out,
        "full_load_checkpoint_vector": full_load_vector_out,
    }
    for label, expected in expected_binaries.items():
        path = _resolve(repo_root, binary_paths[label])
        if path.read_bytes() != expected:
            return False, f"g1_linear_newton_continuation_mismatch:{label}"
    return True, "g1_linear_newton_continuation_consistent"


def write_g1_mgt_semantic_live_linear_newton_continuation_receipt(
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    receipt_out = Path(kwargs.get("receipt_out", DEFAULT_RECEIPT_OUT))
    summary_out = Path(kwargs.get("summary_out", DEFAULT_SUMMARY_OUT))
    restart_vector_out = Path(
        kwargs.get("restart_vector_out", DEFAULT_RESTART_VECTOR_OUT)
    )
    full_load_vector_out = Path(
        kwargs.get("full_load_vector_out", DEFAULT_FULL_LOAD_VECTOR_OUT)
    )
    payloads, binaries = build_g1_mgt_semantic_live_linear_newton_continuation_receipt(
        **kwargs
    )
    for label, relative in (("receipt", receipt_out), ("summary", summary_out)):
        path = _resolve(repo_root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payloads[label]), encoding="utf-8")
    for label, relative in (
        ("restart_checkpoint_vector", restart_vector_out),
        ("full_load_checkpoint_vector", full_load_vector_out),
    ):
        path = _resolve(repo_root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(binaries[label])
        if file_sha256(path) != _bytes_sha256(binaries[label]):
            raise ValueError(f"persisted {label} verification failed")
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument(
        "--operator-checkpoint",
        type=Path,
        default=DEFAULT_OPERATOR_CHECKPOINT,
    )
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument(
        "--restart-vector-out",
        type=Path,
        default=DEFAULT_RESTART_VECTOR_OUT,
    )
    parser.add_argument(
        "--full-load-vector-out",
        type=Path,
        default=DEFAULT_FULL_LOAD_VECTOR_OUT,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    kwargs = {
        "repo_root": ROOT,
        "mgt_path": args.mgt_path,
        "operator_checkpoint": args.operator_checkpoint,
        "receipt_out": args.receipt_out,
        "summary_out": args.summary_out,
        "restart_vector_out": args.restart_vector_out,
        "full_load_vector_out": args.full_load_vector_out,
    }
    if args.check:
        ok, message = check_g1_mgt_semantic_live_linear_newton_continuation_receipt(
            **kwargs
        )
        print(message)
        return 0 if ok else 1
    payloads = write_g1_mgt_semantic_live_linear_newton_continuation_receipt(**kwargs)
    summary = payloads["summary"]
    print(
        f"{summary['status']} | equations={summary['free_equation_count']} | "
        f"load_path={summary['checkpoint_load_factors']} | "
        f"residual_n={summary['final_residual_inf_n']:.12g} | "
        "g1_closure=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
