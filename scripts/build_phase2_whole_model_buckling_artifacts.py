#!/usr/bin/env python3
"""Build source-bound receipts for bounded whole-model linear buckling."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import (  # noqa: E402
    ANALYSIS_ENGINE_VERSION,
    CLAIM_BOUNDARY_VERSION,
    AnalysisConfig,
    analyze,
    load_model,
)
from structural_analysis.analyses.buckling import (  # noqa: E402
    AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
    BUCKLING_CLAIM_BOUNDARY,
    BUCKLING_EIGEN_BACKEND,
    BUCKLING_MODE_SHAPE_STORAGE_PROFILE,
    MAX_DENSE_BUCKLING_FREE_DOF,
)
from structural_analysis.assembly.buckling import (  # noqa: E402
    GEOMETRIC_STIFFNESS_FORMULATION,
    GEOMETRIC_STIFFNESS_SIGN_CONVENTION,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_whole_model_buckling_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_whole_model_buckling_summary.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/whole_model_buckling_v1.schema.json"
)
RESULT_SCHEMA_VERSION = "phase2-whole-model-buckling-result.v1"
SUMMARY_SCHEMA_VERSION = "phase2-whole-model-buckling-artifacts.v1"
NUMERIC_SERIALIZATION_PROFILE = "binary64-json-round-trip-plus-semantic-12e"
TOLERANCE_POLICY = {
    "euler_load_relative_tolerance": 3.0e-6,
    "load_scale_invariance_relative_tolerance": 1.0e-12,
    "residual_relative_tolerance": 1.0e-8,
    "orthogonality_tolerance": 1.0e-8,
    "repeated_eigenvalue_relative_tolerance": 1.0e-10,
    "compression_force_relative_tolerance": 1.0e-12,
}
BLOCKERS_REMAINING = [
    "general_frame_shell_linear_buckling_not_verified",
    "mixed_tension_compression_reference_not_supported",
    "distributed_thermal_settlement_follower_loads_not_supported",
    "nonlinear_buckling_and_imperfection_sensitivity_not_connected",
    "sparse_buckling_backend_not_connected",
    "large_mode_binary_vector_artifacts_not_connected",
    "rocm_hip_buckling_parity_not_verified",
    "independent_code_to_code_buckling_evidence_not_attached",
    "verification_level_2_not_achieved",
    "release_readiness_not_established",
]
CLAIM_BOUNDARY = (
    "This receipt proves a bounded public-API whole-model linear-buckling slice "
    "for explicit 3D frame, beam, and column elements. It runs the authoritative "
    "dense linear-static solver at reference load factor 1.0, recovers constant "
    "element axial compression, assembles a positive-semidefinite consistent "
    "Euler-Bernoulli initial-stress matrix, and solves K phi = lambda Kg phi with "
    "the strict symmetric generalized-eigen kernel. It covers two-plane Euler "
    "column convergence, physical critical-load invariance under reference-load "
    "scaling, deterministic replay, complete repeated-mode cluster selection, "
    "and fail-closed tension or zero-compression reference states. It does not "
    "prove general frame/shell stability, truss or shell geometric stiffness, "
    "mixed tension-compression initial stress, distributed/thermal/settlement/"
    "follower load conversion, nonlinear buckling, imperfection sensitivity, "
    "sparse or large-mode execution, ROCm/HIP parity, an independent second-solver "
    "buckling comparison, Verification Level 2, commercial equivalence, or release "
    "readiness."
)
SOURCE_PATHS = (
    Path("src/structural_analysis/__init__.py"),
    Path("src/structural_analysis/api/core.py"),
    Path("src/structural_analysis/api/cli.py"),
    Path("src/structural_analysis/analyses/__init__.py"),
    Path("src/structural_analysis/analyses/buckling.py"),
    Path("src/structural_analysis/analyses/linear_static.py"),
    Path("src/structural_analysis/assembly/__init__.py"),
    Path("src/structural_analysis/assembly/buckling.py"),
    Path("src/structural_analysis/assembly/linear_static.py"),
    Path("src/structural_analysis/elements/frame3d.py"),
    Path("src/structural_analysis/solvers/_generalized_eigen.py"),
    Path("src/structural_analysis/solvers/buckling/solver.py"),
    SCHEMA_PATH,
    Path("scripts/build_phase2_whole_model_buckling_artifacts.py"),
    Path("tests/test_whole_model_buckling_analysis.py"),
    Path("tests/test_build_phase2_whole_model_buckling_artifacts.py"),
)


class WholeModelBucklingArtifactError(ValueError):
    """Fail-closed whole-model buckling receipt error."""


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
        raise WholeModelBucklingArtifactError(f"artifact_root_invalid:{path}")
    return payload


def _source_checksums(repo_root: Path) -> dict[str, str]:
    checksums = input_checksums(SOURCE_PATHS, repo_root=repo_root)
    missing = [path for path, checksum in checksums.items() if checksum == "missing"]
    if missing:
        raise WholeModelBucklingArtifactError("source_missing:" + ",".join(missing))
    return checksums


def _relative_error(expected: float, actual: float) -> float:
    return abs(actual - expected) / abs(expected)


def _column_payload(
    *,
    element_count: int = 16,
    iy: float = 6.0e-5,
    iz: float = 8.0e-5,
    axial_load_kn: float = -100.0,
) -> dict[str, object]:
    length = 3.0
    nodes = [
        {
            "id": f"N{index}",
            "coordinates": [length * index / element_count, 0.0, 0.0],
        }
        for index in range(element_count + 1)
    ]
    elements = [
        {
            "id": f"E{index}",
            "type": "frame",
            "nodes": [f"N{index}", f"N{index + 1}"],
            "section": "S1",
            "material": "M1",
        }
        for index in range(element_count)
    ]
    supports: list[dict[str, object]] = []
    for index in range(element_count + 1):
        dofs = ["RX"]
        if index == 0:
            dofs.append("UX")
        if index in {0, element_count}:
            dofs.extend(["UY", "UZ"])
        supports.append({"node": f"N{index}", "dofs": dofs})
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.3,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": iy,
                "iz": iz,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [
            {
                "node": f"N{element_count}",
                "components": [axial_load_kn, 0.0, 0.0, 0.0, 0.0, 0.0],
            }
        ],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
    }


def _run_model(
    payload: dict[str, object],
    *,
    mode_count: int,
    filename: str,
) -> dict[str, Any]:
    with TemporaryDirectory(prefix="whole-model-buckling-") as raw_directory:
        path = Path(raw_directory) / filename
        path.write_text(
            json.dumps(payload, allow_nan=False, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        result = analyze(
            load_model(path),
            AnalysisConfig(
                analysis_type="linear_buckling",
                mode_count=mode_count,
                tolerance=1.0e-8,
                eigen_backend=BUCKLING_EIGEN_BACKEND,
            ),
        )
    return _json_data(result.to_dict())


def _ready_metrics(result: dict[str, Any], *, case_id: str) -> dict[str, Any]:
    if result["status"] != "ready":
        raise WholeModelBucklingArtifactError(f"case_not_ready:{case_id}")
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        raise WholeModelBucklingArtifactError(f"case_metrics_invalid:{case_id}")
    return metrics


def _euler_two_plane_case() -> dict[str, Any]:
    payload = _column_payload()
    first = _run_model(payload, mode_count=2, filename="euler-column.json")
    second = _run_model(payload, mode_count=2, filename="euler-column.json")
    metrics = _ready_metrics(first, case_id="euler_two_plane")
    replay = _ready_metrics(second, case_id="euler_two_plane_replay")
    expected = sorted(
        [
            math.pi**2 * 2.0e8 * 6.0e-5 / 3.0**2 / 100.0,
            math.pi**2 * 2.0e8 * 8.0e-5 / 3.0**2 / 100.0,
        ]
    )
    actual = [row["load_factor"] for row in metrics["modes"]]
    maximum_error = max(
        _relative_error(reference, computed)
        for reference, computed in zip(expected, actual, strict=True)
    )
    maximum_residual = max(row["residual_relative_inf"] for row in metrics["modes"])
    compressions = [
        row["reference_compression_force_kn"]
        for row in metrics["reference_member_compression_forces"]
    ]
    maximum_compression_error = max(abs(value - 100.0) / 100.0 for value in compressions)
    contract_pass = bool(
        first["solver"] == AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID
        and first["unsupported_features"] == []
        and metrics["mode_count"] == 2
        and metrics["free_dof_count"] == 80
        and maximum_error <= TOLERANCE_POLICY["euler_load_relative_tolerance"]
        and maximum_residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and metrics["stiffness_orthogonality_error_inf"]
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and metrics["geometric_diagonalization_error_inf"]
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and maximum_compression_error
        <= TOLERANCE_POLICY["compression_force_relative_tolerance"]
        and metrics["raw_result_hash"] == replay["raw_result_hash"]
        and metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_two_plane_pinned_euler_column_16_element",
        "truth_basis": "analytic_euler_load_with_finite_element_convergence",
        "public_status": first["status"],
        "solver_id": first["solver"],
        "element_count": 16,
        "free_dof_count": metrics["free_dof_count"],
        "reference_compression_force_kn": 100.0,
        "expected_load_factors": expected,
        "actual_load_factors": actual,
        "maximum_load_factor_relative_error": maximum_error,
        "maximum_reference_compression_relative_error": maximum_compression_error,
        "maximum_residual_relative_inf": maximum_residual,
        "stiffness_orthogonality_error_inf": (
            metrics["stiffness_orthogonality_error_inf"]
        ),
        "geometric_diagonalization_error_inf": (
            metrics["geometric_diagonalization_error_inf"]
        ),
        "stiffness_matrix_hash": metrics["stiffness_matrix_hash"],
        "geometric_stiffness_matrix_hash": (
            metrics["geometric_stiffness_matrix_hash"]
        ),
        "reference_load_pattern_hash": metrics["reference_load_pattern_hash"],
        "raw_result_hash": metrics["raw_result_hash"],
        "semantic_result_hash": metrics["semantic_result_hash"],
        "deterministic_replay_raw_exact": (
            metrics["raw_result_hash"] == replay["raw_result_hash"]
        ),
        "deterministic_replay_semantic_exact": (
            metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        ),
        "regularization_used": metrics["regularization_used"],
        "fallback_used": metrics["fallback_used"],
        "contract_pass": contract_pass,
    }


def _load_scale_case() -> dict[str, Any]:
    low = _run_model(
        _column_payload(axial_load_kn=-100.0),
        mode_count=1,
        filename="reference-100.json",
    )
    high = _run_model(
        _column_payload(axial_load_kn=-200.0),
        mode_count=1,
        filename="reference-200.json",
    )
    low_metrics = _ready_metrics(low, case_id="load_scale_100")
    high_metrics = _ready_metrics(high, case_id="load_scale_200")
    low_factor = low_metrics["critical_load_factor"]
    high_factor = high_metrics["critical_load_factor"]
    low_physical = low_factor * 100.0
    high_physical = high_factor * 200.0
    physical_error = _relative_error(low_physical, high_physical)
    factor_ratio_error = _relative_error(0.5, high_factor / low_factor)
    contract_pass = bool(
        low["status"] == "ready"
        and high["status"] == "ready"
        and physical_error
        <= TOLERANCE_POLICY["load_scale_invariance_relative_tolerance"]
        and factor_ratio_error
        <= TOLERANCE_POLICY["load_scale_invariance_relative_tolerance"]
        and low_metrics["stiffness_matrix_hash"]
        == high_metrics["stiffness_matrix_hash"]
        and low_metrics["geometric_stiffness_matrix_hash"]
        != high_metrics["geometric_stiffness_matrix_hash"]
        and low_metrics["regularization_used"] is False
        and high_metrics["regularization_used"] is False
        and low_metrics["fallback_used"] is False
        and high_metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_reference_load_scale_invariance",
        "truth_basis": "linear_reference_load_homogeneity_invariant",
        "low_reference_load_kn": 100.0,
        "high_reference_load_kn": 200.0,
        "low_reference_critical_load_factor": low_factor,
        "high_reference_critical_load_factor": high_factor,
        "low_reference_physical_critical_load_kn": low_physical,
        "high_reference_physical_critical_load_kn": high_physical,
        "physical_critical_load_relative_error": physical_error,
        "load_factor_ratio_relative_error": factor_ratio_error,
        "stiffness_matrix_hash_equal": (
            low_metrics["stiffness_matrix_hash"]
            == high_metrics["stiffness_matrix_hash"]
        ),
        "geometric_stiffness_matrix_hash_distinct": (
            low_metrics["geometric_stiffness_matrix_hash"]
            != high_metrics["geometric_stiffness_matrix_hash"]
        ),
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
    }


def _repeated_cluster_case() -> dict[str, Any]:
    payload = _column_payload(iy=8.0e-5, iz=8.0e-5)
    cut = _run_model(payload, mode_count=1, filename="symmetric-column.json")
    complete = _run_model(payload, mode_count=2, filename="symmetric-column.json")
    replay_result = _run_model(
        payload,
        mode_count=2,
        filename="symmetric-column.json",
    )
    metrics = _ready_metrics(complete, case_id="repeated_complete")
    replay = _ready_metrics(replay_result, case_id="repeated_complete_replay")
    factors = [row["load_factor"] for row in metrics["modes"]]
    relative_gap = abs(factors[1] - factors[0]) / max(factors)
    cut_kinds = [row.get("kind") for row in cut["unsupported_features"]]
    cut_detail = " | ".join(
        str(row.get("detail", "")) for row in cut["unsupported_features"]
    )
    contract_pass = bool(
        cut["status"] == "blocked"
        and cut_kinds == ["buckling_generalized_eigen_contract_failed"]
        and "cuts a repeated" in cut_detail
        and complete["status"] == "ready"
        and metrics["mode_count"] == 2
        and relative_gap
        <= TOLERANCE_POLICY["repeated_eigenvalue_relative_tolerance"]
        and metrics["raw_result_hash"] == replay["raw_result_hash"]
        and metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_symmetric_column_repeated_cluster",
        "truth_basis": "complete_repeated_eigenspace_selection_invariant",
        "incomplete_selection_status": cut["status"],
        "incomplete_selection_blocker_kind": cut_kinds[0] if cut_kinds else "",
        "incomplete_selection_detail": cut_detail,
        "complete_selection_status": complete["status"],
        "complete_load_factors": factors,
        "repeated_load_factor_relative_gap": relative_gap,
        "raw_result_hash": metrics["raw_result_hash"],
        "semantic_result_hash": metrics["semantic_result_hash"],
        "deterministic_replay_raw_exact": (
            metrics["raw_result_hash"] == replay["raw_result_hash"]
        ),
        "deterministic_replay_semantic_exact": (
            metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        ),
        "regularization_used": metrics["regularization_used"],
        "fallback_used": metrics["fallback_used"],
        "contract_pass": contract_pass,
    }


def _reference_sign_case() -> dict[str, Any]:
    tension = _run_model(
        _column_payload(axial_load_kn=100.0),
        mode_count=1,
        filename="tension.json",
    )
    transverse_payload = _column_payload()
    transverse_payload["loads"] = [
        {"node": "N16", "components": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]}
    ]
    no_compression = _run_model(
        transverse_payload,
        mode_count=1,
        filename="no-compression.json",
    )
    tension_kinds = [row.get("kind") for row in tension["unsupported_features"]]
    no_compression_kinds = [
        row.get("kind") for row in no_compression["unsupported_features"]
    ]
    contract_pass = bool(
        tension["status"] == "blocked"
        and bool(tension_kinds)
        and set(tension_kinds) == {"buckling_reference_tension_not_supported"}
        and no_compression["status"] == "blocked"
        and bool(no_compression_kinds)
        and set(no_compression_kinds) == {"buckling_reference_compression_missing"}
        and tension["metrics"]["regularization_used"] is False
        and tension["metrics"]["fallback_used"] is False
        and no_compression["metrics"]["regularization_used"] is False
        and no_compression["metrics"]["fallback_used"] is False
    )
    return {
        "case_id": "public_reference_axial_sign_fail_closed",
        "truth_basis": "positive_compression_initial_stress_sign_invariant",
        "tension_status": tension["status"],
        "tension_blocker_kind": tension_kinds[0] if tension_kinds else "",
        "zero_compression_status": no_compression["status"],
        "zero_compression_blocker_kind": (
            no_compression_kinds[0] if no_compression_kinds else ""
        ),
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
    }


def _validate_derived_values(payload: dict[str, Any]) -> None:
    verification = payload["verification"]
    euler = verification["euler_two_plane"]
    maximum_error = max(
        _relative_error(reference, actual)
        for reference, actual in zip(
            euler["expected_load_factors"],
            euler["actual_load_factors"],
            strict=True,
        )
    )
    if euler["maximum_load_factor_relative_error"] != maximum_error:
        raise WholeModelBucklingArtifactError("euler_error_invalid")
    scale = verification["reference_load_scale"]
    physical_error = _relative_error(
        scale["low_reference_physical_critical_load_kn"],
        scale["high_reference_physical_critical_load_kn"],
    )
    if scale["physical_critical_load_relative_error"] != physical_error:
        raise WholeModelBucklingArtifactError("load_scale_error_invalid")
    repeated = verification["repeated_cluster"]
    factors = repeated["complete_load_factors"]
    relative_gap = abs(factors[1] - factors[0]) / max(factors)
    if repeated["repeated_load_factor_relative_gap"] != relative_gap:
        raise WholeModelBucklingArtifactError("repeated_cluster_gap_invalid")


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
        raise WholeModelBucklingArtifactError("result_schema_invalid") from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise WholeModelBucklingArtifactError("artifact_hash_invalid")
    checksums = payload["source"]["input_checksums"]
    if payload["source"]["source_set_hash"] != _hash_value(checksums):
        raise WholeModelBucklingArtifactError("source_set_hash_invalid")
    if require_current_sources and checksums != _source_checksums(repo_root):
        raise WholeModelBucklingArtifactError("sources_stale")
    _validate_derived_values(payload)
    rows = list(payload["verification"].values())
    expected_contract = all(row["contract_pass"] is True for row in rows)
    expected_summary = {
        "case_count": 4,
        "passing_case_count": sum(row["contract_pass"] is True for row in rows),
        "euler_two_plane_contract_pass": payload["verification"][
            "euler_two_plane"
        ]["contract_pass"],
        "reference_load_scale_contract_pass": payload["verification"][
            "reference_load_scale"
        ]["contract_pass"],
        "repeated_cluster_contract_pass": payload["verification"][
            "repeated_cluster"
        ]["contract_pass"],
        "reference_sign_contract_pass": payload["verification"]["reference_sign"][
            "contract_pass"
        ],
        "contract_pass": expected_contract,
    }
    if payload["contract_pass"] is not expected_contract:
        raise WholeModelBucklingArtifactError("result_contract_pass_invalid")
    if payload["summary"] != expected_summary:
        raise WholeModelBucklingArtifactError("result_summary_invalid")


def _stable_projection(value: Any) -> Any:
    volatile = {
        "artifact_hash",
        "generated_at",
        "raw_result_hash",
        "result_artifact_hash",
        "source_commit_sha",
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
            raise WholeModelBucklingArtifactError("non_finite_reproduction_value")
        return format(value, ".12e")
    return value


def build_phase2_whole_model_buckling_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    source_checksums = _source_checksums(repo_root)
    verification = {
        "euler_two_plane": _euler_two_plane_case(),
        "reference_load_scale": _load_scale_case(),
        "repeated_cluster": _repeated_cluster_case(),
        "reference_sign": _reference_sign_case(),
    }
    contract_pass = all(row["contract_pass"] is True for row in verification.values())
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "numeric_serialization_profile": NUMERIC_SERIALIZATION_PROFILE,
        "status": "partial" if contract_pass else "blocked",
        "truth_class": "analytic_and_invariant_whole_model_linear_buckling_truth",
        "analysis_scope": "public_api_dense_reference_state_frame_linear_buckling",
        "solver_contract": {
            "solver_id": AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
            "eigen_backend": BUCKLING_EIGEN_BACKEND,
            "maximum_dense_free_dof_count": MAX_DENSE_BUCKLING_FREE_DOF,
            "geometric_stiffness_formulation": GEOMETRIC_STIFFNESS_FORMULATION,
            "geometric_stiffness_sign_convention": (
                GEOMETRIC_STIFFNESS_SIGN_CONVENTION
            ),
            "reference_load_factor": 1.0,
            "mode_shape_storage_profile": BUCKLING_MODE_SHAPE_STORAGE_PROFILE,
            "claim_boundary": BUCKLING_CLAIM_BOUNDARY,
        },
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
            "euler_two_plane_contract_pass": verification["euler_two_plane"][
                "contract_pass"
            ],
            "reference_load_scale_contract_pass": verification[
                "reference_load_scale"
            ]["contract_pass"],
            "repeated_cluster_contract_pass": verification["repeated_cluster"][
                "contract_pass"
            ],
            "reference_sign_contract_pass": verification["reference_sign"][
                "contract_pass"
            ],
            "contract_pass": contract_pass,
        },
        "claims": {
            "whole_model_frame_linear_buckling_evidence": contract_pass,
            "reference_static_initial_stress_assembly_evidence": bool(
                verification["euler_two_plane"]["contract_pass"]
                and verification["reference_load_scale"]["contract_pass"]
            ),
            "repeated_cluster_fail_closed_evidence": verification[
                "repeated_cluster"
            ]["contract_pass"],
            "reference_axial_sign_fail_closed_evidence": verification[
                "reference_sign"
            ]["contract_pass"],
            "general_frame_shell_linear_buckling": False,
            "mixed_tension_compression_reference": False,
            "nonlinear_buckling_or_imperfection_sensitivity": False,
            "sparse_buckling_backend": False,
            "large_mode_binary_vector_artifacts": False,
            "rocm_hip_buckling_parity": False,
            "independent_code_to_code_or_verification_level_2": False,
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
        **result["summary"],
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
        raise WholeModelBucklingArtifactError("summary_schema_version_invalid")
    for key in ("status", "contract_pass", *result["summary"]):
        expected = result["summary"].get(key, result.get(key))
        if summary.get(key) != expected:
            raise WholeModelBucklingArtifactError(f"summary_result_mismatch:{key}")
    if summary.get("result_artifact_hash") != result["artifact_hash"]:
        raise WholeModelBucklingArtifactError("summary_result_artifact_hash_mismatch")
    if summary.get("source_set_hash") != result["source"]["source_set_hash"]:
        raise WholeModelBucklingArtifactError("summary_source_set_hash_mismatch")
    if summary.get("claims") != result["claims"]:
        raise WholeModelBucklingArtifactError("summary_claims_mismatch")


def check_phase2_whole_model_buckling_artifacts(
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
            return False, f"phase2_whole_model_buckling_missing:{path}"
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
        expected = build_phase2_whole_model_buckling_artifacts(
            repo_root=repo_root,
            result_out=result_out,
            summary_out=summary_out,
        )
    except Exception as exc:
        return False, f"phase2_whole_model_buckling_invalid:{exc}"
    for key in ("result", "summary"):
        if _stable_projection(existing[key]) != _stable_projection(expected[key]):
            return False, f"phase2_whole_model_buckling_mismatch:{key}"
    return True, "phase2_whole_model_buckling_consistent"


def write_phase2_whole_model_buckling_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_whole_model_buckling_artifacts(
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
        ok, message = check_phase2_whole_model_buckling_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_whole_model_buckling_artifacts(
        repo_root=ROOT,
        result_out=args.result_out,
        summary_out=args.summary_out,
    )
    summary = payloads["summary"]
    print(
        f"{summary['status']} | cases={summary['passing_case_count']}/"
        f"{summary['case_count']} | level2="
        f"{summary['claims']['independent_code_to_code_or_verification_level_2']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
