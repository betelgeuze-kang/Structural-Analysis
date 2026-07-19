#!/usr/bin/env python3
"""Build source-bound analytic receipts for modal and linear-buckling kernels."""

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
from jsonschema.exceptions import SchemaError, ValidationError
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.benchmark.geometric_nonlinear import (  # noqa: E402
    assemble_euler_column_system,
)
from structural_analysis.solvers._generalized_eigen import (  # noqa: E402
    SEMANTIC_HASH_PROFILE,
    raw_modes_sha256,
    semantic_modes_sha256,
)
from structural_analysis.solvers.buckling import (  # noqa: E402
    BucklingAnalysisError,
    solve_linear_buckling,
)
from structural_analysis.solvers.modal import (  # noqa: E402
    ModalAnalysisError,
    solve_modal_modes,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_modal_buckling_kernel_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_modal_buckling_kernel_summary.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/modal_buckling_kernel_v1.schema.json"
)
RESULT_SCHEMA_VERSION = "phase2-modal-buckling-kernel-result.v1"
SUMMARY_SCHEMA_VERSION = "phase2-modal-buckling-kernel-artifacts.v1"
NUMERIC_SERIALIZATION_PROFILE = "binary64-json-round-trip-plus-semantic-12e"
TOLERANCE_POLICY = {
    "modal_eigenvalue_relative_tolerance": 1.0e-12,
    "diagonal_buckling_relative_tolerance": 1.0e-12,
    "euler_column_relative_tolerance": 3.0e-6,
    "residual_relative_tolerance": 1.0e-9,
    "orthogonality_tolerance": 1.0e-8,
    "cluster_relative_tolerance": 1.0e-10,
}
BLOCKERS_REMAINING = [
    "whole_model_modal_assembly_not_connected",
    "whole_model_buckling_assembly_not_connected",
    "independent_code_to_code_evidence_not_attached",
    "published_or_experimental_modal_buckling_evidence_not_attached",
    "sparse_production_path_not_verified",
    "rocm_hip_modal_buckling_parity_not_verified",
    "verification_level_2_not_achieved",
    "release_readiness_not_established",
]
CLAIM_BOUNDARY = (
    "This receipt proves only strict dense symmetric generalized-eigen matrix "
    "kernels for K phi = omega^2 M phi and K phi = lambda Kg phi. It covers a "
    "closed-form two-DOF modal system, a diagonal buckling problem with singular "
    "geometric stiffness, a finite-element Euler-column bridge to pi^2 EI/L^2, "
    "and deterministic coordinate-axis bases for complete repeated-eigenvalue "
    "clusters. It does not prove whole-model mass or geometric-stiffness assembly, "
    "a general frame/shell modal or buckling workflow, sparse or ROCm/HIP parity, "
    "an independent second solver, published or experimental validation, "
    "Verification Level 2, commercial equivalence, or release readiness."
)
SOURCE_PATHS = (
    Path("src/structural_analysis/solvers/_generalized_eigen.py"),
    Path("src/structural_analysis/solvers/modal/__init__.py"),
    Path("src/structural_analysis/solvers/modal/solver.py"),
    Path("src/structural_analysis/solvers/buckling/__init__.py"),
    Path("src/structural_analysis/solvers/buckling/solver.py"),
    Path("src/structural_analysis/benchmark/geometric_nonlinear.py"),
    SCHEMA_PATH,
    Path("scripts/build_phase2_modal_buckling_kernel_artifacts.py"),
    Path("tests/test_modal_generalized_eigen_v1.py"),
    Path("tests/test_buckling_generalized_eigen_v1.py"),
    Path("tests/test_build_phase2_modal_buckling_kernel_artifacts.py"),
)


class ModalBucklingArtifactError(ValueError):
    """Fail-closed modal/buckling receipt error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    return _hash_value(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )


def _json_data(value: Any) -> Any:
    return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False))


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ModalBucklingArtifactError(f"artifact_root_invalid:{path}")
    return payload


def _source_checksums(repo_root: Path) -> dict[str, str]:
    checksums = input_checksums(SOURCE_PATHS, repo_root=repo_root)
    missing = [path for path, checksum in checksums.items() if checksum == "missing"]
    if missing:
        raise ModalBucklingArtifactError("source_missing:" + ",".join(missing))
    return checksums


def _relative_error(expected: float, actual: float) -> float:
    return abs(actual - expected) / abs(expected)


def _modal_two_dof_case() -> dict[str, Any]:
    stiffness = np.asarray([[2.0, -1.0], [-1.0, 1.0]], dtype=np.float64)
    mass = np.eye(2, dtype=np.float64)
    first = solve_modal_modes(stiffness, mass, mode_count=2)
    second = solve_modal_modes(stiffness, mass, mode_count=2)
    expected = [(3.0 - math.sqrt(5.0)) / 2.0, (3.0 + math.sqrt(5.0)) / 2.0]
    actual = [mode.eigenvalue_rad2_per_s2 for mode in first.modes]
    maximum_error = max(
        _relative_error(reference, computed)
        for reference, computed in zip(expected, actual, strict=True)
    )
    maximum_residual = max(mode.residual_relative_inf for mode in first.modes)
    contract_pass = bool(
        first.contract_pass
        and maximum_error
        <= TOLERANCE_POLICY["modal_eigenvalue_relative_tolerance"]
        and maximum_residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and first.mass_orthogonality_error_inf
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and first.stiffness_diagonalization_error_inf
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and first.raw_result_hash == second.raw_result_hash
        and first.semantic_result_hash == second.semantic_result_hash
        and not first.regularization_applied
        and not first.fallback_used
    )
    return {
        "case_id": "analytic_two_dof_shear_modal",
        "truth_basis": "analytic_closed_form",
        "expected_eigenvalues": expected,
        "actual_eigenvalues": actual,
        "mass_normalized_modes": [list(mode.mass_normalized_shape) for mode in first.modes],
        "maximum_eigenvalue_relative_error": maximum_error,
        "maximum_residual_relative_inf": maximum_residual,
        "mass_orthogonality_error_inf": first.mass_orthogonality_error_inf,
        "stiffness_diagonalization_error_inf": first.stiffness_diagonalization_error_inf,
        "stiffness_matrix_hash": first.stiffness_matrix_hash,
        "mass_matrix_hash": first.mass_matrix_hash,
        "raw_result_hash": first.raw_result_hash,
        "semantic_result_hash": first.semantic_result_hash,
        "deterministic_replay_raw_exact": first.raw_result_hash == second.raw_result_hash,
        "deterministic_replay_semantic_exact": (
            first.semantic_result_hash == second.semantic_result_hash
        ),
        "regularization_applied": first.regularization_applied,
        "fallback_used": first.fallback_used,
        "contract_pass": contract_pass,
    }


def _diagonal_buckling_case() -> dict[str, Any]:
    stiffness = np.diag([6.0, 8.0, 10.0])
    geometric = np.diag([3.0, 2.0, 0.0])
    first = solve_linear_buckling(stiffness, geometric, mode_count=2)
    second = solve_linear_buckling(stiffness, geometric, mode_count=2)
    expected = [2.0, 4.0]
    actual = [mode.load_factor for mode in first.modes]
    maximum_error = max(
        _relative_error(reference, computed)
        for reference, computed in zip(expected, actual, strict=True)
    )
    maximum_residual = max(mode.residual_relative_inf for mode in first.modes)
    contract_pass = bool(
        first.contract_pass
        and first.finite_positive_eigenvalue_count == 2
        and first.geometric_stiffness_positive_rank == 2
        and maximum_error
        <= TOLERANCE_POLICY["diagonal_buckling_relative_tolerance"]
        and maximum_residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and first.stiffness_orthogonality_error_inf
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and first.geometric_diagonalization_error_inf
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and first.raw_result_hash == second.raw_result_hash
        and first.semantic_result_hash == second.semantic_result_hash
        and not first.regularization_applied
        and not first.fallback_used
    )
    return {
        "case_id": "analytic_diagonal_buckling_singular_kg",
        "truth_basis": "analytic_closed_form",
        "expected_load_factors": expected,
        "actual_load_factors": actual,
        "stiffness_normalized_modes": [
            list(mode.stiffness_normalized_shape) for mode in first.modes
        ],
        "finite_positive_eigenvalue_count": first.finite_positive_eigenvalue_count,
        "geometric_stiffness_positive_rank": first.geometric_stiffness_positive_rank,
        "maximum_load_factor_relative_error": maximum_error,
        "maximum_residual_relative_inf": maximum_residual,
        "stiffness_orthogonality_error_inf": first.stiffness_orthogonality_error_inf,
        "geometric_diagonalization_error_inf": (
            first.geometric_diagonalization_error_inf
        ),
        "stiffness_matrix_hash": first.stiffness_matrix_hash,
        "geometric_stiffness_matrix_hash": first.geometric_stiffness_matrix_hash,
        "raw_result_hash": first.raw_result_hash,
        "semantic_result_hash": first.semantic_result_hash,
        "deterministic_replay_raw_exact": first.raw_result_hash == second.raw_result_hash,
        "deterministic_replay_semantic_exact": (
            first.semantic_result_hash == second.semantic_result_hash
        ),
        "regularization_applied": first.regularization_applied,
        "fallback_used": first.fallback_used,
        "contract_pass": contract_pass,
    }


def _euler_column_case() -> dict[str, Any]:
    system = assemble_euler_column_system(element_count=16)
    first = solve_linear_buckling(
        system.elastic_stiffness,
        system.unit_compression_geometric_stiffness,
        mode_count=1,
    )
    second = solve_linear_buckling(
        system.elastic_stiffness,
        system.unit_compression_geometric_stiffness,
        mode_count=1,
    )
    expected = math.pi**2 * system.flexural_rigidity_kn_m2 / system.length_m**2
    actual = first.critical_load_factor
    relative_error = _relative_error(expected, actual)
    residual = first.modes[0].residual_relative_inf
    contract_pass = bool(
        first.contract_pass
        and relative_error <= TOLERANCE_POLICY["euler_column_relative_tolerance"]
        and residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and first.raw_result_hash == second.raw_result_hash
        and first.semantic_result_hash == second.semantic_result_hash
        and not first.symmetry_projection_applied
        and not first.regularization_applied
        and not first.fallback_used
    )
    return {
        "case_id": "pinned_pinned_euler_column_16_element",
        "truth_basis": "analytic_closed_form_with_fe_convergence_bridge",
        "element_count": system.element_count,
        "length_m": system.length_m,
        "flexural_rigidity_kn_m2": system.flexural_rigidity_kn_m2,
        "expected_critical_load_kn": expected,
        "actual_critical_load_kn": actual,
        "critical_mode_stiffness_normalized": list(
            first.modes[0].stiffness_normalized_shape
        ),
        "critical_load_relative_error": relative_error,
        "residual_relative_inf": residual,
        "stiffness_matrix_hash": first.stiffness_matrix_hash,
        "geometric_stiffness_matrix_hash": first.geometric_stiffness_matrix_hash,
        "raw_result_hash": first.raw_result_hash,
        "semantic_result_hash": first.semantic_result_hash,
        "deterministic_replay_raw_exact": first.raw_result_hash == second.raw_result_hash,
        "deterministic_replay_semantic_exact": (
            first.semantic_result_hash == second.semantic_result_hash
        ),
        "symmetry_projection_applied": first.symmetry_projection_applied,
        "regularization_applied": first.regularization_applied,
        "fallback_used": first.fallback_used,
        "contract_pass": contract_pass,
    }


def _cluster_rejection_flags() -> tuple[bool, bool]:
    modal_rejected = False
    buckling_rejected = False
    try:
        solve_modal_modes(np.diag([4.0, 4.0, 9.0]), np.eye(3), mode_count=1)
    except ModalAnalysisError as exc:
        modal_rejected = "cuts a repeated or clustered" in str(exc)
    try:
        solve_linear_buckling(
            np.diag([4.0, 4.0, 9.0]),
            np.eye(3),
            mode_count=1,
        )
    except BucklingAnalysisError as exc:
        buckling_rejected = "cuts a repeated or clustered" in str(exc)
    return modal_rejected, buckling_rejected


def _repeated_eigenspace_case() -> dict[str, Any]:
    matrix = np.diag([4.0, 4.0, 9.0])
    identity = np.eye(3, dtype=np.float64)
    modal_first = solve_modal_modes(matrix, identity, mode_count=3)
    modal_second = solve_modal_modes(matrix, identity, mode_count=3)
    buckling_first = solve_linear_buckling(matrix, identity, mode_count=3)
    buckling_second = solve_linear_buckling(matrix, identity, mode_count=3)
    modal_rejected, buckling_rejected = _cluster_rejection_flags()
    expected_axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    modal_axes = [list(mode.max_component_normalized_shape) for mode in modal_first.modes]
    buckling_axes = [
        list(mode.max_component_normalized_shape) for mode in buckling_first.modes
    ]
    contract_pass = bool(
        modal_axes == expected_axes
        and buckling_axes == expected_axes
        and modal_first.raw_result_hash == modal_second.raw_result_hash
        and modal_first.semantic_result_hash == modal_second.semantic_result_hash
        and buckling_first.raw_result_hash == buckling_second.raw_result_hash
        and buckling_first.semantic_result_hash == buckling_second.semantic_result_hash
        and modal_rejected
        and buckling_rejected
        and not modal_first.regularization_applied
        and not modal_first.fallback_used
        and not buckling_first.regularization_applied
        and not buckling_first.fallback_used
    )
    return {
        "case_id": "complete_repeated_eigenvalue_cluster",
        "truth_basis": "coordinate_axis_projector_invariant",
        "modal_eigenvalues": [
            mode.eigenvalue_rad2_per_s2 for mode in modal_first.modes
        ],
        "modal_normalized_modes": [
            list(mode.mass_normalized_shape) for mode in modal_first.modes
        ],
        "modal_axis_basis": modal_axes,
        "modal_raw_result_hash": modal_first.raw_result_hash,
        "modal_semantic_result_hash": modal_first.semantic_result_hash,
        "modal_replay_raw_exact": (
            modal_first.raw_result_hash == modal_second.raw_result_hash
        ),
        "modal_replay_semantic_exact": (
            modal_first.semantic_result_hash == modal_second.semantic_result_hash
        ),
        "modal_incomplete_cluster_rejected": modal_rejected,
        "buckling_load_factors": [mode.load_factor for mode in buckling_first.modes],
        "buckling_normalized_modes": [
            list(mode.stiffness_normalized_shape) for mode in buckling_first.modes
        ],
        "buckling_axis_basis": buckling_axes,
        "buckling_raw_result_hash": buckling_first.raw_result_hash,
        "buckling_semantic_result_hash": buckling_first.semantic_result_hash,
        "buckling_replay_raw_exact": (
            buckling_first.raw_result_hash == buckling_second.raw_result_hash
        ),
        "buckling_replay_semantic_exact": (
            buckling_first.semantic_result_hash
            == buckling_second.semantic_result_hash
        ),
        "buckling_incomplete_cluster_rejected": buckling_rejected,
        "regularization_applied": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
    }


def _mode_matrix(rows: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise ModalBucklingArtifactError("stored_mode_matrix_invalid")
    return matrix.T


def _validate_recorded_hashes(payload: dict[str, Any]) -> None:
    verification = payload["verification"]
    checks = (
        ("modal_two_dof", "actual_eigenvalues", "mass_normalized_modes"),
        (
            "buckling_singular_geometric",
            "actual_load_factors",
            "stiffness_normalized_modes",
        ),
        (
            "euler_column",
            "actual_critical_load_kn",
            "critical_mode_stiffness_normalized",
        ),
    )
    for case_name, value_key, mode_key in checks:
        case = verification[case_name]
        values = case[value_key]
        rows = case[mode_key]
        if case_name == "euler_column":
            values = [values]
            rows = [rows]
        modes = _mode_matrix(rows)
        if case["raw_result_hash"] != raw_modes_sha256(values, modes):
            raise ModalBucklingArtifactError(f"raw_result_hash_invalid:{case_name}")
        if case["semantic_result_hash"] != semantic_modes_sha256(values, modes):
            raise ModalBucklingArtifactError(
                f"semantic_result_hash_invalid:{case_name}"
            )
    repeated = verification["repeated_eigenspace"]
    for prefix, value_key, mode_key in (
        ("modal", "modal_eigenvalues", "modal_normalized_modes"),
        (
            "buckling",
            "buckling_load_factors",
            "buckling_normalized_modes",
        ),
    ):
        values = repeated[value_key]
        modes = _mode_matrix(repeated[mode_key])
        if repeated[f"{prefix}_raw_result_hash"] != raw_modes_sha256(values, modes):
            raise ModalBucklingArtifactError(
                f"raw_result_hash_invalid:repeated_{prefix}"
            )
        if repeated[f"{prefix}_semantic_result_hash"] != semantic_modes_sha256(
            values,
            modes,
        ):
            raise ModalBucklingArtifactError(
                f"semantic_result_hash_invalid:repeated_{prefix}"
            )


def _validate_result(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    require_current_sources: bool,
) -> None:
    schema = _read_json(repo_root / SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise ModalBucklingArtifactError("result_schema_invalid") from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise ModalBucklingArtifactError("artifact_hash_invalid")
    checksums = payload["source"]["input_checksums"]
    if payload["source"]["source_set_hash"] != _hash_value(checksums):
        raise ModalBucklingArtifactError("source_set_hash_invalid")
    if require_current_sources and checksums != _source_checksums(repo_root):
        raise ModalBucklingArtifactError("sources_stale")
    _validate_recorded_hashes(payload)
    rows = list(payload["verification"].values())
    expected_contract = all(row["contract_pass"] is True for row in rows)
    if payload["contract_pass"] is not expected_contract:
        raise ModalBucklingArtifactError("result_contract_pass_invalid")
    expected_summary = {
        "case_count": 4,
        "passing_case_count": sum(row["contract_pass"] is True for row in rows),
        "modal_kernel_contract_pass": payload["verification"]["modal_two_dof"][
            "contract_pass"
        ],
        "buckling_kernel_contract_pass": payload["verification"][
            "buckling_singular_geometric"
        ]["contract_pass"],
        "euler_column_bridge_contract_pass": payload["verification"]["euler_column"][
            "contract_pass"
        ],
        "repeated_eigenspace_contract_pass": payload["verification"][
            "repeated_eigenspace"
        ]["contract_pass"],
        "contract_pass": expected_contract,
    }
    if payload["summary"] != expected_summary:
        raise ModalBucklingArtifactError("result_summary_invalid")


def _stable_projection(value: Any) -> Any:
    volatile = {
        "artifact_hash",
        "generated_at",
        "raw_result_hash",
        "result_artifact_hash",
        "source_commit_sha",
        "modal_raw_result_hash",
        "buckling_raw_result_hash",
    }
    if isinstance(value, dict):
        return {
            key: _stable_projection(item)
            for key, item in sorted(value.items())
            if key not in volatile
        }
    if isinstance(value, list):
        return [_stable_projection(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ModalBucklingArtifactError("non_finite_reproduction_value")
        return format(value, ".12e")
    return value


def build_phase2_modal_buckling_kernel_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    source_checksums = _source_checksums(repo_root)
    verification = {
        "modal_two_dof": _modal_two_dof_case(),
        "buckling_singular_geometric": _diagonal_buckling_case(),
        "euler_column": _euler_column_case(),
        "repeated_eigenspace": _repeated_eigenspace_case(),
    }
    contract_pass = all(row["contract_pass"] is True for row in verification.values())
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "numeric_serialization_profile": NUMERIC_SERIALIZATION_PROFILE,
        "semantic_hash_profile": SEMANTIC_HASH_PROFILE,
        "status": "partial" if contract_pass else "blocked",
        "truth_class": "analytic_and_semianalytic_matrix_kernel_truth",
        "analysis_scope": "dense_symmetric_generalized_eigen_matrix_kernels",
        "source": {
            "input_checksums": source_checksums,
            "source_set_hash": _hash_value(source_checksums),
        },
        "tolerance_policy": dict(TOLERANCE_POLICY),
        "verification": verification,
        "summary": {
            "case_count": 4,
            "passing_case_count": sum(
                row["contract_pass"] is True for row in verification.values()
            ),
            "modal_kernel_contract_pass": verification["modal_two_dof"][
                "contract_pass"
            ],
            "buckling_kernel_contract_pass": verification[
                "buckling_singular_geometric"
            ]["contract_pass"],
            "euler_column_bridge_contract_pass": verification["euler_column"][
                "contract_pass"
            ],
            "repeated_eigenspace_contract_pass": verification[
                "repeated_eigenspace"
            ]["contract_pass"],
            "contract_pass": contract_pass,
        },
        "claims": {
            "modal_matrix_kernel_evidence": verification["modal_two_dof"][
                "contract_pass"
            ],
            "buckling_matrix_kernel_evidence": verification[
                "buckling_singular_geometric"
            ]["contract_pass"],
            "repeated_eigenspace_determinism_evidence": verification[
                "repeated_eigenspace"
            ]["contract_pass"],
            "euler_column_analytic_bridge_evidence": verification["euler_column"][
                "contract_pass"
            ],
            "whole_model_modal_workflow": False,
            "whole_model_buckling_workflow": False,
            "independent_code_to_code_evidence": False,
            "published_or_experimental_evidence": False,
            "sparse_rocm_hip_parity": False,
            "verification_level_2": False,
            "release_readiness": False,
        },
        "blockers_remaining": list(BLOCKERS_REMAINING),
        "claim_boundary": CLAIM_BOUNDARY,
        "contract_pass": contract_pass,
    }
    result["artifact_hash"] = _artifact_hash(result)
    result = _json_data(result)
    _validate_result(result, repo_root=repo_root, require_current_sources=True)
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "status": result["status"],
        "contract_pass": result["contract_pass"],
        "case_count": result["summary"]["case_count"],
        "passing_case_count": result["summary"]["passing_case_count"],
        "modal_kernel_contract_pass": result["summary"][
            "modal_kernel_contract_pass"
        ],
        "buckling_kernel_contract_pass": result["summary"][
            "buckling_kernel_contract_pass"
        ],
        "euler_column_bridge_contract_pass": result["summary"][
            "euler_column_bridge_contract_pass"
        ],
        "repeated_eigenspace_contract_pass": result["summary"][
            "repeated_eigenspace_contract_pass"
        ],
        "semantic_hash_profile": SEMANTIC_HASH_PROFILE,
        "result_artifact_hash": result["artifact_hash"],
        "source_set_hash": result["source"]["source_set_hash"],
        "claims": result["claims"],
        "blockers_remaining": list(BLOCKERS_REMAINING),
        "artifacts": {
            "result": str(result_out),
            "summary": str(summary_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {"result": result, "summary": _json_data(summary)}


def _validate_summary(summary: dict[str, Any], result: dict[str, Any]) -> None:
    if summary.get("schema_version") != SUMMARY_SCHEMA_VERSION:
        raise ModalBucklingArtifactError("summary_schema_version_invalid")
    for key in (
        "status",
        "contract_pass",
        "case_count",
        "passing_case_count",
        "modal_kernel_contract_pass",
        "buckling_kernel_contract_pass",
        "euler_column_bridge_contract_pass",
        "repeated_eigenspace_contract_pass",
    ):
        expected = result["summary"].get(key, result.get(key))
        if summary.get(key) != expected:
            raise ModalBucklingArtifactError(f"summary_result_mismatch:{key}")
    if summary.get("result_artifact_hash") != result["artifact_hash"]:
        raise ModalBucklingArtifactError("summary_result_artifact_hash_mismatch")
    if summary.get("source_set_hash") != result["source"]["source_set_hash"]:
        raise ModalBucklingArtifactError("summary_source_set_hash_mismatch")
    if summary.get("claims") != result["claims"]:
        raise ModalBucklingArtifactError("summary_claims_mismatch")


def check_phase2_modal_buckling_kernel_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    repo_root = repo_root.resolve()
    resolved_result = result_out if result_out.is_absolute() else repo_root / result_out
    resolved_summary = summary_out if summary_out.is_absolute() else repo_root / summary_out
    for path in (resolved_result, resolved_summary):
        if not path.is_file():
            return False, f"phase2_modal_buckling_kernel_missing:{path}"
    try:
        existing = {
            "result": _read_json(resolved_result),
            "summary": _read_json(resolved_summary),
        }
        _validate_result(
            existing["result"],
            repo_root=repo_root,
            require_current_sources=True,
        )
        _validate_summary(existing["summary"], existing["result"])
        expected = build_phase2_modal_buckling_kernel_artifacts(
            repo_root=repo_root,
            result_out=result_out,
            summary_out=summary_out,
        )
    except Exception as exc:
        return False, f"phase2_modal_buckling_kernel_invalid:{exc}"
    for key in ("result", "summary"):
        if _stable_projection(existing[key]) != _stable_projection(expected[key]):
            return False, f"phase2_modal_buckling_kernel_mismatch:{key}"
    return True, "phase2_modal_buckling_kernel_consistent"


def write_phase2_modal_buckling_kernel_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_modal_buckling_kernel_artifacts(
        repo_root=repo_root,
        result_out=result_out,
        summary_out=summary_out,
    )
    for key, relative in (("result", result_out), ("summary", summary_out)):
        path = relative if relative.is_absolute() else repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payloads[key]), encoding="utf-8")
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-out", type=Path, default=DEFAULT_RESULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_phase2_modal_buckling_kernel_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_modal_buckling_kernel_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | cases={summary['passing_case_count']}/"
        f"{summary['case_count']} | level2={summary['claims']['verification_level_2']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
