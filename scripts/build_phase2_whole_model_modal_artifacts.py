#!/usr/bin/env python3
"""Build source-bound receipts for the bounded whole-model modal API path."""

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
from structural_analysis.analyses.modal import (  # noqa: E402
    AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
    EIGEN_BACKEND,
    MAX_DENSE_MODAL_FREE_DOF,
    MODAL_CLAIM_BOUNDARY,
    MODE_SHAPE_STORAGE_PROFILE,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_RESULT_OUT = PRODUCTIZATION / "phase2_whole_model_modal_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_whole_model_modal_summary.json"
SCHEMA_PATH = Path("src/structural_analysis/schemas/whole_model_modal_v1.schema.json")
RESULT_SCHEMA_VERSION = "phase2-whole-model-modal-result.v1"
SUMMARY_SCHEMA_VERSION = "phase2-whole-model-modal-artifacts.v1"
NUMERIC_SERIALIZATION_PROFILE = "binary64-json-round-trip-plus-semantic-12e"
TOLERANCE_POLICY = {
    "eigenvalue_relative_tolerance": 2.0e-12,
    "residual_relative_tolerance": 1.0e-9,
    "orthogonality_tolerance": 1.0e-8,
    "effective_mass_ratio_absolute_tolerance": 1.0e-12,
    "repeated_eigenvalue_relative_tolerance": 1.0e-12,
}
BLOCKERS_REMAINING = [
    "general_frame_shell_modal_workflow_not_verified",
    "nodal_lumped_mass_not_connected",
    "sparse_modal_backend_not_connected",
    "large_mode_binary_vector_artifacts_not_connected",
    "rocm_hip_modal_parity_not_verified",
    "independent_code_to_code_modal_evidence_not_attached",
    "verification_level_2_not_achieved",
    "release_readiness_not_established",
]
CLAIM_BOUNDARY = (
    "This receipt proves a bounded public-API whole-model modal slice for explicit "
    "3D frame and truss elements using dense binary64 stiffness matrices, element "
    "consistent mass assembled from explicit kg/m3 material density, and the strict "
    "symmetric generalized-eigen kernel. It covers one-element cantilever bending "
    "and axial analytic checks, free-free rigid-body-mode exclusion, deterministic "
    "replay, directional effective-mass bookkeeping, and fail-closed repeated-mode "
    "cluster selection. It does not prove a general frame/shell workflow, nodal or "
    "nonstructural lumped mass, sparse extraction, binary large-mode vector storage, "
    "ROCm/HIP parity, an independent second-solver modal comparison, Verification "
    "Level 2, commercial equivalence, or release readiness."
)
SOURCE_PATHS = (
    Path("src/structural_analysis/__init__.py"),
    Path("src/structural_analysis/api/core.py"),
    Path("src/structural_analysis/api/cli.py"),
    Path("src/structural_analysis/analyses/__init__.py"),
    Path("src/structural_analysis/analyses/modal.py"),
    Path("src/structural_analysis/assembly/__init__.py"),
    Path("src/structural_analysis/assembly/modal.py"),
    Path("src/structural_analysis/elements/axial.py"),
    Path("src/structural_analysis/elements/frame3d.py"),
    Path("src/structural_analysis/model_ir/loader.py"),
    Path("src/structural_analysis/model_ir/types.py"),
    Path("src/structural_analysis/solvers/_generalized_eigen.py"),
    Path("src/structural_analysis/solvers/modal/solver.py"),
    SCHEMA_PATH,
    Path("scripts/build_phase2_whole_model_modal_artifacts.py"),
    Path("tests/test_whole_model_modal_analysis.py"),
    Path("tests/test_build_phase2_whole_model_modal_artifacts.py"),
)


class WholeModelModalArtifactError(ValueError):
    """Fail-closed whole-model modal receipt error."""


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
        raise WholeModelModalArtifactError(f"artifact_root_invalid:{path}")
    return payload


def _source_checksums(repo_root: Path) -> dict[str, str]:
    checksums = input_checksums(SOURCE_PATHS, repo_root=repo_root)
    missing = [path for path, checksum in checksums.items() if checksum == "missing"]
    if missing:
        raise WholeModelModalArtifactError("source_missing:" + ",".join(missing))
    return checksums


def _relative_error(expected: float, actual: float) -> float:
    return abs(actual - expected) / abs(expected)


def _frame_payload(
    *,
    iy: float = 5.0e-5,
    iz: float = 8.0e-5,
    supports: list[dict[str, object]] | None = None,
    element_type: str = "frame",
) -> dict[str, object]:
    if supports is None:
        supports = [
            {"node": "N1", "dofs": "all"},
            {"node": "N2", "dofs": ["UX", "UZ", "RX", "RY"]},
        ]
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": element_type,
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 2.0e8,
                "poisson_ratio": 0.3,
                "density": 7850.0,
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
        "loads": [],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
    }


def _axial_payload() -> dict[str, object]:
    payload = _frame_payload(element_type="truss")
    payload["sections"] = [{"id": "S1", "type": "axial", "area": 0.02}]
    payload["supports"] = [
        {"node": "N1", "dofs": "all"},
        {"node": "N2", "dofs": ["UY", "UZ"]},
    ]
    return payload


def _run_model(
    payload: dict[str, object],
    *,
    mode_count: int,
    tolerance: float,
    filename: str,
) -> dict[str, Any]:
    with TemporaryDirectory(prefix="whole-model-modal-") as raw_directory:
        path = Path(raw_directory) / filename
        path.write_text(
            json.dumps(payload, allow_nan=False, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        result = analyze(
            load_model(path),
            AnalysisConfig(
                analysis_type="modal",
                mode_count=mode_count,
                tolerance=tolerance,
                eigen_backend=EIGEN_BACKEND,
            ),
        )
    return _json_data(result.to_dict())


def _ready_metrics(result: dict[str, Any], *, case_id: str) -> dict[str, Any]:
    if result["status"] != "ready":
        raise WholeModelModalArtifactError(f"case_not_ready:{case_id}")
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        raise WholeModelModalArtifactError(f"case_metrics_invalid:{case_id}")
    return metrics


def _cantilever_case() -> dict[str, Any]:
    first = _run_model(
        _frame_payload(),
        mode_count=2,
        tolerance=1.0e-10,
        filename="cantilever.json",
    )
    second = _run_model(
        _frame_payload(),
        mode_count=2,
        tolerance=1.0e-10,
        filename="cantilever.json",
    )
    metrics = _ready_metrics(first, case_id="cantilever")
    replay = _ready_metrics(second, case_id="cantilever_replay")
    dimensionless = (12.4801921537537, 1211.5198078462463)
    scale = (2.0e8 * 8.0e-5) / ((7850.0 * 0.02 / 1000.0) * 2.0**4)
    expected = [value * scale for value in dimensionless]
    actual = [row["eigenvalue_rad2_per_s2"] for row in metrics["modes"]]
    maximum_error = max(
        _relative_error(reference, computed)
        for reference, computed in zip(expected, actual, strict=True)
    )
    maximum_residual = max(row["residual_relative_inf"] for row in metrics["modes"])
    cumulative_uy = metrics["modes"][-1]["directional_participation"]["UY"][
        "cumulative_effective_modal_mass_ratio"
    ]
    contract_pass = bool(
        first["solver"] == AUTHORITATIVE_CPU_MODAL_SOLVER_ID
        and first["unsupported_features"] == []
        and metrics["free_dof_count"] == 2
        and metrics["mode_count"] == 2
        and metrics["rigid_mode_count"] == 0
        and maximum_error <= TOLERANCE_POLICY["eigenvalue_relative_tolerance"]
        and maximum_residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and metrics["mass_orthogonality_error_inf"]
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and metrics["stiffness_diagonalization_error_inf"]
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and abs(cumulative_uy - 1.0)
        <= TOLERANCE_POLICY["effective_mass_ratio_absolute_tolerance"]
        and metrics["raw_result_hash"] == replay["raw_result_hash"]
        and metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_frame_cantilever_consistent_mass",
        "truth_basis": "one_element_euler_bernoulli_consistent_mass_closed_form",
        "public_status": first["status"],
        "solver_id": first["solver"],
        "free_dof_count": metrics["free_dof_count"],
        "mode_count": metrics["mode_count"],
        "rigid_mode_count": metrics["rigid_mode_count"],
        "expected_eigenvalues_rad2_per_s2": expected,
        "actual_eigenvalues_rad2_per_s2": actual,
        "maximum_eigenvalue_relative_error": maximum_error,
        "maximum_residual_relative_inf": maximum_residual,
        "mass_orthogonality_error_inf": metrics["mass_orthogonality_error_inf"],
        "stiffness_diagonalization_error_inf": metrics[
            "stiffness_diagonalization_error_inf"
        ],
        "total_physical_mass_kg": metrics["total_physical_mass_kg"],
        "uy_cumulative_effective_modal_mass_ratio": cumulative_uy,
        "stiffness_matrix_hash": metrics["stiffness_matrix_hash"],
        "mass_matrix_hash": metrics["mass_matrix_hash"],
        "free_dof_map_hash": metrics["free_dof_map_hash"],
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


def _axial_case() -> dict[str, Any]:
    first = _run_model(
        _axial_payload(),
        mode_count=1,
        tolerance=1.0e-10,
        filename="axial.json",
    )
    second = _run_model(
        _axial_payload(),
        mode_count=1,
        tolerance=1.0e-10,
        filename="axial.json",
    )
    metrics = _ready_metrics(first, case_id="axial")
    replay = _ready_metrics(second, case_id="axial_replay")
    expected = 3.0 * 2.0e8 * 1000.0 / (7850.0 * 2.0**2)
    actual = metrics["modes"][0]["eigenvalue_rad2_per_s2"]
    relative_error = _relative_error(expected, actual)
    residual = metrics["modes"][0]["residual_relative_inf"]
    contract_pass = bool(
        first["solver"] == AUTHORITATIVE_CPU_MODAL_SOLVER_ID
        and first["unsupported_features"] == []
        and metrics["free_dof_count"] == 1
        and metrics["mode_count"] == 1
        and metrics["rigid_mode_count"] == 0
        and relative_error <= TOLERANCE_POLICY["eigenvalue_relative_tolerance"]
        and residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and metrics["raw_result_hash"] == replay["raw_result_hash"]
        and metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_truss_axial_consistent_mass",
        "truth_basis": "one_element_axial_consistent_mass_closed_form",
        "public_status": first["status"],
        "solver_id": first["solver"],
        "free_dof_count": metrics["free_dof_count"],
        "mode_count": metrics["mode_count"],
        "rigid_mode_count": metrics["rigid_mode_count"],
        "expected_eigenvalue_rad2_per_s2": expected,
        "actual_eigenvalue_rad2_per_s2": actual,
        "eigenvalue_relative_error": relative_error,
        "residual_relative_inf": residual,
        "total_physical_mass_kg": metrics["total_physical_mass_kg"],
        "stiffness_matrix_hash": metrics["stiffness_matrix_hash"],
        "mass_matrix_hash": metrics["mass_matrix_hash"],
        "free_dof_map_hash": metrics["free_dof_map_hash"],
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


def _free_free_case() -> dict[str, Any]:
    payload = _frame_payload(supports=[])
    first = _run_model(
        payload,
        mode_count=6,
        tolerance=1.0e-9,
        filename="free-free.json",
    )
    second = _run_model(
        payload,
        mode_count=6,
        tolerance=1.0e-9,
        filename="free-free.json",
    )
    metrics = _ready_metrics(first, case_id="free_free")
    replay = _ready_metrics(second, case_id="free_free_replay")
    frequencies = [row["frequency_hz"] for row in metrics["modes"]]
    maximum_residual = max(row["residual_relative_inf"] for row in metrics["modes"])
    contract_pass = bool(
        first["solver"] == AUTHORITATIVE_CPU_MODAL_SOLVER_ID
        and first["unsupported_features"] == []
        and metrics["free_dof_count"] == 12
        and metrics["rigid_mode_count"] == 6
        and metrics["mode_count"] == 6
        and len(frequencies) == 6
        and min(frequencies) > 0.0
        and maximum_residual <= TOLERANCE_POLICY["residual_relative_tolerance"]
        and metrics["mass_orthogonality_error_inf"]
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and metrics["stiffness_diagonalization_error_inf"]
        <= TOLERANCE_POLICY["orthogonality_tolerance"]
        and metrics["raw_result_hash"] == replay["raw_result_hash"]
        and metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_free_free_frame_rigid_mode_exclusion",
        "truth_basis": "three_dimensional_rigid_body_mode_invariant",
        "public_status": first["status"],
        "solver_id": first["solver"],
        "free_dof_count": metrics["free_dof_count"],
        "expected_rigid_mode_count": 6,
        "actual_rigid_mode_count": metrics["rigid_mode_count"],
        "positive_mode_count": metrics["mode_count"],
        "positive_frequencies_hz": frequencies,
        "minimum_positive_frequency_hz": min(frequencies),
        "maximum_residual_relative_inf": maximum_residual,
        "mass_orthogonality_error_inf": metrics["mass_orthogonality_error_inf"],
        "stiffness_diagonalization_error_inf": metrics[
            "stiffness_diagonalization_error_inf"
        ],
        "stiffness_matrix_hash": metrics["stiffness_matrix_hash"],
        "mass_matrix_hash": metrics["mass_matrix_hash"],
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


def _repeated_cluster_case() -> dict[str, Any]:
    supports = [
        {"node": "N1", "dofs": "all"},
        {"node": "N2", "dofs": ["UX", "RX"]},
    ]
    payload = _frame_payload(iy=8.0e-5, iz=8.0e-5, supports=supports)
    cut = _run_model(
        payload,
        mode_count=1,
        tolerance=1.0e-9,
        filename="symmetric-frame.json",
    )
    complete = _run_model(
        payload,
        mode_count=2,
        tolerance=1.0e-9,
        filename="symmetric-frame.json",
    )
    replay_result = _run_model(
        payload,
        mode_count=2,
        tolerance=1.0e-9,
        filename="symmetric-frame.json",
    )
    metrics = _ready_metrics(complete, case_id="repeated_complete")
    replay = _ready_metrics(replay_result, case_id="repeated_complete_replay")
    eigenvalues = [row["eigenvalue_rad2_per_s2"] for row in metrics["modes"]]
    relative_gap = abs(eigenvalues[1] - eigenvalues[0]) / max(eigenvalues)
    cut_kinds = [row.get("kind") for row in cut["unsupported_features"]]
    cut_detail = " | ".join(
        str(row.get("detail", "")) for row in cut["unsupported_features"]
    )
    contract_pass = bool(
        cut["status"] == "blocked"
        and cut_kinds == ["modal_generalized_eigen_contract_failed"]
        and "cuts a repeated" in cut_detail
        and complete["status"] == "ready"
        and complete["solver"] == AUTHORITATIVE_CPU_MODAL_SOLVER_ID
        and complete["unsupported_features"] == []
        and metrics["mode_count"] == 2
        and relative_gap
        <= TOLERANCE_POLICY["repeated_eigenvalue_relative_tolerance"]
        and metrics["raw_result_hash"] == replay["raw_result_hash"]
        and metrics["semantic_result_hash"] == replay["semantic_result_hash"]
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    return {
        "case_id": "public_symmetric_bending_repeated_cluster",
        "truth_basis": "complete_repeated_eigenspace_selection_invariant",
        "incomplete_selection_status": cut["status"],
        "incomplete_selection_blocker_kind": cut_kinds[0] if cut_kinds else "",
        "incomplete_selection_detail": cut_detail,
        "complete_selection_status": complete["status"],
        "solver_id": complete["solver"],
        "complete_mode_count": metrics["mode_count"],
        "complete_eigenvalues_rad2_per_s2": eigenvalues,
        "complete_frequencies_hz": [row["frequency_hz"] for row in metrics["modes"]],
        "repeated_eigenvalue_relative_gap": relative_gap,
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


def _validate_derived_values(payload: dict[str, Any]) -> None:
    verification = payload["verification"]
    cantilever = verification["cantilever_bending"]
    cantilever_error = max(
        _relative_error(reference, actual)
        for reference, actual in zip(
            cantilever["expected_eigenvalues_rad2_per_s2"],
            cantilever["actual_eigenvalues_rad2_per_s2"],
            strict=True,
        )
    )
    if cantilever["maximum_eigenvalue_relative_error"] != cantilever_error:
        raise WholeModelModalArtifactError("cantilever_error_invalid")
    axial = verification["axial_bar"]
    axial_error = _relative_error(
        axial["expected_eigenvalue_rad2_per_s2"],
        axial["actual_eigenvalue_rad2_per_s2"],
    )
    if axial["eigenvalue_relative_error"] != axial_error:
        raise WholeModelModalArtifactError("axial_error_invalid")
    repeated = verification["repeated_cluster"]
    eigenvalues = repeated["complete_eigenvalues_rad2_per_s2"]
    relative_gap = abs(eigenvalues[1] - eigenvalues[0]) / max(eigenvalues)
    if repeated["repeated_eigenvalue_relative_gap"] != relative_gap:
        raise WholeModelModalArtifactError("repeated_cluster_gap_invalid")


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
        raise WholeModelModalArtifactError("result_schema_invalid") from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise WholeModelModalArtifactError("artifact_hash_invalid")
    checksums = payload["source"]["input_checksums"]
    if payload["source"]["source_set_hash"] != _hash_value(checksums):
        raise WholeModelModalArtifactError("source_set_hash_invalid")
    if require_current_sources and checksums != _source_checksums(repo_root):
        raise WholeModelModalArtifactError("sources_stale")
    _validate_derived_values(payload)
    rows = list(payload["verification"].values())
    expected_contract = all(row["contract_pass"] is True for row in rows)
    expected_summary = {
        "case_count": 4,
        "passing_case_count": sum(row["contract_pass"] is True for row in rows),
        "cantilever_bending_contract_pass": payload["verification"][
            "cantilever_bending"
        ]["contract_pass"],
        "axial_bar_contract_pass": payload["verification"]["axial_bar"][
            "contract_pass"
        ],
        "free_free_rigid_mode_contract_pass": payload["verification"][
            "free_free_rigid_modes"
        ]["contract_pass"],
        "repeated_cluster_contract_pass": payload["verification"][
            "repeated_cluster"
        ]["contract_pass"],
        "contract_pass": expected_contract,
    }
    if payload["contract_pass"] is not expected_contract:
        raise WholeModelModalArtifactError("result_contract_pass_invalid")
    if payload["summary"] != expected_summary:
        raise WholeModelModalArtifactError("result_summary_invalid")


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
            raise WholeModelModalArtifactError("non_finite_reproduction_value")
        return format(value, ".12e")
    return value


def build_phase2_whole_model_modal_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    source_checksums = _source_checksums(repo_root)
    verification = {
        "cantilever_bending": _cantilever_case(),
        "axial_bar": _axial_case(),
        "free_free_rigid_modes": _free_free_case(),
        "repeated_cluster": _repeated_cluster_case(),
    }
    contract_pass = all(row["contract_pass"] is True for row in verification.values())
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "numeric_serialization_profile": NUMERIC_SERIALIZATION_PROFILE,
        "status": "partial" if contract_pass else "blocked",
        "truth_class": "analytic_and_invariant_whole_model_modal_truth",
        "analysis_scope": "public_api_dense_consistent_mass_frame_truss_modal",
        "solver_contract": {
            "solver_id": AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
            "eigen_backend": EIGEN_BACKEND,
            "maximum_dense_free_dof_count": MAX_DENSE_MODAL_FREE_DOF,
            "mass_formulation": "element_consistent_mass_frame_truss_v1",
            "material_density_unit": "kg_per_m3",
            "mass_matrix_unit": "kN_s2_per_m",
            "mode_shape_storage_profile": MODE_SHAPE_STORAGE_PROFILE,
            "claim_boundary": MODAL_CLAIM_BOUNDARY,
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
            "cantilever_bending_contract_pass": verification[
                "cantilever_bending"
            ]["contract_pass"],
            "axial_bar_contract_pass": verification["axial_bar"]["contract_pass"],
            "free_free_rigid_mode_contract_pass": verification[
                "free_free_rigid_modes"
            ]["contract_pass"],
            "repeated_cluster_contract_pass": verification["repeated_cluster"][
                "contract_pass"
            ],
            "contract_pass": contract_pass,
        },
        "claims": {
            "whole_model_frame_truss_modal_evidence": contract_pass,
            "consistent_mass_assembly_evidence": bool(
                verification["cantilever_bending"]["contract_pass"]
                and verification["axial_bar"]["contract_pass"]
            ),
            "rigid_body_mode_exclusion_evidence": verification[
                "free_free_rigid_modes"
            ]["contract_pass"],
            "repeated_cluster_fail_closed_evidence": verification[
                "repeated_cluster"
            ]["contract_pass"],
            "general_frame_shell_modal_workflow": False,
            "nodal_lumped_mass_support": False,
            "sparse_modal_backend": False,
            "large_mode_binary_vector_artifacts": False,
            "rocm_hip_modal_parity": False,
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
        raise WholeModelModalArtifactError("summary_schema_version_invalid")
    for key in ("status", "contract_pass", *result["summary"]):
        expected = result["summary"].get(key, result.get(key))
        if summary.get(key) != expected:
            raise WholeModelModalArtifactError(f"summary_result_mismatch:{key}")
    if summary.get("result_artifact_hash") != result["artifact_hash"]:
        raise WholeModelModalArtifactError("summary_result_artifact_hash_mismatch")
    if summary.get("source_set_hash") != result["source"]["source_set_hash"]:
        raise WholeModelModalArtifactError("summary_source_set_hash_mismatch")
    if summary.get("claims") != result["claims"]:
        raise WholeModelModalArtifactError("summary_claims_mismatch")


def check_phase2_whole_model_modal_artifacts(
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
            return False, f"phase2_whole_model_modal_missing:{path}"
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
        expected = build_phase2_whole_model_modal_artifacts(
            repo_root=repo_root,
            result_out=result_out,
            summary_out=summary_out,
        )
    except Exception as exc:
        return False, f"phase2_whole_model_modal_invalid:{exc}"
    for key in ("result", "summary"):
        if _stable_projection(existing[key]) != _stable_projection(expected[key]):
            return False, f"phase2_whole_model_modal_mismatch:{key}"
    return True, "phase2_whole_model_modal_consistent"


def write_phase2_whole_model_modal_artifacts(
    *,
    repo_root: Path = ROOT,
    result_out: Path = DEFAULT_RESULT_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    payloads = build_phase2_whole_model_modal_artifacts(
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
        ok, message = check_phase2_whole_model_modal_artifacts(
            repo_root=ROOT,
            result_out=args.result_out,
            summary_out=args.summary_out,
        )
        print(message)
        return 0 if ok else 1
    payloads = write_phase2_whole_model_modal_artifacts(
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
