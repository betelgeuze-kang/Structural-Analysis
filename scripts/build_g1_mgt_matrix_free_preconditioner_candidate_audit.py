#!/usr/bin/env python3
"""Audit fixed-SuperLU and nodal block-Jacobi matrix-free preconditioners."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import scipy
from scipy.sparse.linalg import spilu


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
from build_g1_mgt_hip_current_tangent_host_parser_receipt import (  # noqa: E402
    SCHEMA_VERSION as HIP_CURRENT_TANGENT_HOST_PARSER_SCHEMA_VERSION,
    validate_receipt as validate_hip_current_tangent_host_parser_receipt,
)
from mgt_sparse_linear_solver import (  # noqa: E402
    build_node_block_jacobi_preconditioner,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)
from run_g1_mgt_hip_current_tangent_hardware_parity import (  # noqa: E402
    DEFAULT_ACTION_OUT as HIP_CURRENT_TANGENT_ACTION_ARTIFACT,
    DEFAULT_OUT as HIP_CURRENT_TANGENT_HARDWARE_RECEIPT,
    SCHEMA_VERSION as HIP_CURRENT_TANGENT_HARDWARE_SCHEMA_VERSION,
    validate_receipt as validate_hip_current_tangent_hardware_receipt,
)
from run_engine_v2_hip_sparse_lu_apply import (  # noqa: E402
    COMPILE_RECEIPT_SCHEMA_VERSION as HIP_SPARSE_LU_COMPILE_SCHEMA_VERSION,
    validate_compile_receipt as validate_hip_sparse_lu_compile_receipt,
)
from run_engine_v2_hip_current_tangent_operator import (  # noqa: E402
    COMPILE_RECEIPT_SCHEMA_VERSION as HIP_CURRENT_TANGENT_COMPILE_SCHEMA_VERSION,
    validate_compile_receipt as validate_hip_current_tangent_compile_receipt,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.current_tangent_operator import (  # noqa: E402
    CURRENT_TANGENT_OPERATOR_PROFILE,
    CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR,
    validate_current_tangent_operator_manifest,
)
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
    HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
    HIP_CURRENT_TANGENT_FIXTURE_VERSION,
    HIP_CURRENT_TANGENT_PARITY_PROFILE,
    HIP_CURRENT_TANGENT_SCHEDULE_PROFILE,
    create_hip_current_tangent_operator_fixture,
)
from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import (  # noqa: E402
    HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
    HIP_SPARSE_LU_APPLY_SCHEDULE_PROFILE,
    create_hip_sparse_lu_apply_fixture,
)
from structural_analysis.solvers.nonlinear.canonical_sparse_lu import (  # noqa: E402
    CANONICAL_SPARSE_LU_APPLY_PROFILE,
    CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION,
    CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE,
    CANONICAL_SPARSE_LU_PROFILE,
    create_canonical_sparse_lu_binary_artifact_bundle,
    create_canonical_sparse_lu_factor,
    read_canonical_sparse_lu_binary_artifacts,
    write_canonical_sparse_lu_binary_artifacts,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE,
    MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE,
    MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE,
    MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
    MatrixFreeCPUFGMRESConfig,
    _operator_binding_payload,
    _run_fgmres,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
    create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu,
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
    PRODUCTIZATION / "g1_mgt_matrix_free_preconditioner_candidate_audit.json"
)
HIP_SPARSE_LU_COMPILE_RECEIPT = (
    PRODUCTIZATION / "engine_v2_hip_sparse_lu_apply_compile_receipt.json"
)
HIP_CURRENT_TANGENT_COMPILE_RECEIPT = (
    PRODUCTIZATION / "engine_v2_hip_current_tangent_operator_compile_receipt.json"
)
HIP_CURRENT_TANGENT_HOST_PARSER_RECEIPT = (
    PRODUCTIZATION / "g1_mgt_hip_current_tangent_host_parser_receipt.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_matrix_free_preconditioner_candidate_audit_v1.schema.json"
)
SCHEMA_VERSION = "g1-mgt-matrix-free-preconditioner-candidate-audit.v1"
CASE_ID = "g1_real_mgt_matrix_free_preconditioner_candidate_audit"
LOAD_FACTOR = 1.0
RESIDUAL_GATE_KN = 5.0e-7


def _config(*, max_iterations: int) -> MatrixFreeCPUFGMRESConfig:
    return MatrixFreeCPUFGMRESConfig(
        max_iterations=max_iterations,
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
        HIP_SPARSE_LU_COMPILE_RECEIPT,
        HIP_CURRENT_TANGENT_COMPILE_RECEIPT,
        HIP_CURRENT_TANGENT_HOST_PARSER_RECEIPT,
        HIP_CURRENT_TANGENT_HARDWARE_RECEIPT,
        HIP_CURRENT_TANGENT_ACTION_ARTIFACT,
        Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
        Path("implementation/phase1/mgt_sparse_linear_solver.py"),
        Path("src/structural_analysis/solvers/nonlinear/matrix_free_fgmres.py"),
        Path("src/structural_analysis/solvers/nonlinear/canonical_sparse_lu.py"),
        Path(
            "src/structural_analysis/schemas/"
            "canonical_sparse_lu_binary_artifacts_v1.schema.json"
        ),
        Path("src/structural_analysis/solvers/nonlinear/__init__.py"),
        Path("src/structural_analysis/engine_v2/contracts/_canonical.py"),
        Path("src/structural_analysis/engine_v2/contracts/current_tangent_operator.py"),
        Path("src/structural_analysis/schemas/current_tangent_operator_v1.schema.json"),
        SCHEMA_PATH,
        Path("scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py"),
        Path("scripts/run_engine_v2_hip_sparse_lu_apply.py"),
        Path("scripts/run_engine_v2_hip_current_tangent_operator.py"),
        Path("scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py"),
        Path("scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py"),
        Path(
            "implementation/phase1/hip_kernels/"
            "engine_v2_current_tangent_operator.hip.cpp"
        ),
        Path(
            "src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "hip_current_tangent_operator_compile_receipt_v1.schema.json"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "hip_current_tangent_operator_parity_v1.schema.json"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "g1_mgt_hip_current_tangent_host_parser_receipt_v1.schema.json"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "g1_mgt_hip_current_tangent_hardware_parity_receipt_v1.schema.json"
        ),
        Path("tests/test_build_g1_mgt_matrix_free_preconditioner_candidate_audit.py"),
        Path("tests/test_engine_v2_canonical_contract.py"),
        Path("tests/test_canonical_sparse_lu_factor.py"),
        Path("tests/test_matrix_free_cpu_fgmres_state_tangent.py"),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
        Path("tests/test_engine_v2_hip_current_tangent_operator.py"),
        Path("tests/test_engine_v2_hip_current_tangent_operator_runner.py"),
        Path("tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py"),
        Path("tests/test_run_g1_mgt_hip_current_tangent_hardware_parity.py"),
        Path("tests/test_g1_mgt_load_coupled_arc_length_adapter.py"),
    ]


def _observation_at(
    observations: list[dict[str, Any]],
    iteration: int,
) -> dict[str, Any]:
    rows = [row for row in observations if row["iteration"] == iteration]
    if len(rows) != 1:
        raise ValueError(f"explicit observation {iteration} is not unique")
    return rows[0]


def _sparse_factor_component_payload(matrix: Any) -> dict[str, Any]:
    csr = matrix.tocsr(copy=True)
    csr.sum_duplicates()
    csr.sort_indices()
    pattern_hash = canonical_hash(
        {
            "shape": [int(csr.shape[0]), int(csr.shape[1])],
            "row_pointer_data_hash": array_data_hash(
                np.asarray(csr.indptr, dtype="<i8")
            ),
            "column_index_data_hash": array_data_hash(
                np.asarray(csr.indices, dtype="<i8")
            ),
        }
    )
    return {
        "nnz": int(csr.nnz),
        "pattern_hash": pattern_hash,
        "numeric_values_hash": array_data_hash(np.asarray(csr.data, dtype="<f8")),
    }


def _canonical_factor_from_superlu(
    factorization: Any,
    *,
    source_operator_pattern_hash: str,
    source_operator_numeric_values_hash: str,
) -> Any:
    lower = factorization.L.tocsr(copy=True)
    upper = factorization.U.tocsr(copy=True)
    lower.sum_duplicates()
    upper.sum_duplicates()
    lower.sort_indices()
    upper.sort_indices()
    return create_canonical_sparse_lu_factor(
        lower_row_pointer=lower.indptr,
        lower_column_indices=lower.indices,
        lower_numeric_values=lower.data,
        upper_row_pointer=upper.indptr,
        upper_column_indices=upper.indices,
        upper_numeric_values=upper.data,
        row_permutation=factorization.perm_r,
        column_permutation=factorization.perm_c,
        source_operator_pattern_hash=source_operator_pattern_hash,
        source_operator_numeric_values_hash=(source_operator_numeric_values_hash),
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
    hip_current_tangent_host_parser_receipt = (
        validate_hip_current_tangent_host_parser_receipt(
            _read_json(repo_root / HIP_CURRENT_TANGENT_HOST_PARSER_RECEIPT),
            repo_root=repo_root,
            require_current_sources=True,
        )
    )
    hip_current_tangent_host_parser_receipt_pass = bool(
        hip_current_tangent_host_parser_receipt["schema_version"]
        == HIP_CURRENT_TANGENT_HOST_PARSER_SCHEMA_VERSION
        and hip_current_tangent_host_parser_receipt["contract_pass"] is True
        and hip_current_tangent_host_parser_receipt["contract_scope"]
        == "actual_mgt_dual_target_compile_and_host_fixture_parser_only"
        and [
            row["architecture"]
            for row in hip_current_tangent_host_parser_receipt["targets"]
        ]
        == ["gfx1030", "gfx1100"]
        and all(
            row["target_compile"] is True
            and row["host_fixture_parser_execution"] is True
            and row["host_fixture_validation"]["contract_pass"] is True
            and row["host_fixture_validation"]["equation_count"] == 70_560
            and row["host_fixture_validation"]["fixture_byte_length"] == 36_123_072
            and row["host_fixture_validation"]["actual_hardware_execution"] is False
            and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
            for row in hip_current_tangent_host_parser_receipt["targets"]
        )
        and hip_current_tangent_host_parser_receipt["claims"][
            "actual_mgt_dual_target_host_fixture_parser_execution"
        ]
        is True
        and hip_current_tangent_host_parser_receipt["claims"][
            "actual_hardware_execution"
        ]
        is False
        and hip_current_tangent_host_parser_receipt["claims"][
            "current_tangent_action_executed"
        ]
        is False
        and hip_current_tangent_host_parser_receipt["claims"][
            "cpu_hip_numerical_parity"
        ]
        is False
    )
    hip_current_tangent_hardware_receipt = (
        validate_hip_current_tangent_hardware_receipt(
            _read_json(repo_root / HIP_CURRENT_TANGENT_HARDWARE_RECEIPT),
            repo_root=repo_root,
            require_current_sources=True,
            require_action_artifact=True,
        )
    )
    hip_current_tangent_hardware_receipt_pass = bool(
        hip_current_tangent_hardware_receipt["schema_version"]
        == HIP_CURRENT_TANGENT_HARDWARE_SCHEMA_VERSION
        and hip_current_tangent_hardware_receipt["contract_pass"] is True
        and hip_current_tangent_hardware_receipt["contract_scope"]
        == "actual_mgt_single_state_direction_local_gfx1030_hardware_parity"
        and hip_current_tangent_hardware_receipt["host_parser_prerequisite"][
            "receipt_hash"
        ]
        == hip_current_tangent_host_parser_receipt["receipt_hash"]
        and hip_current_tangent_hardware_receipt["hardware_execution"][
            "actual_hardware"
        ]
        is True
        and hip_current_tangent_hardware_receipt["hardware_execution"]["gcn_arch_name"]
        == "gfx1030"
        and hip_current_tangent_hardware_receipt["hardware_execution"][
            "runtime_metadata"
        ]["kernel_invocation_count"]
        == 1
        and hip_current_tangent_hardware_receipt["hardware_execution"][
            "runtime_metadata"
        ]["mid_action_d2h_transfer_count"]
        == 0
        and hip_current_tangent_hardware_receipt["comparison"]["generic_comparison"][
            "contract_pass"
        ]
        is True
        and hip_current_tangent_hardware_receipt["comparison"]["generic_comparison"][
            "device_order_cpu_max_abs_error_n_per_m"
        ]
        == 0.0
        and hip_current_tangent_hardware_receipt["comparison"]["actual_mgt_context"][
            "device_order_bitwise_match"
        ]
        is True
        and hip_current_tangent_hardware_receipt["claims"][
            "actual_mgt_current_tangent_action_executed"
        ]
        is True
        and hip_current_tangent_hardware_receipt["claims"]["cpu_hip_numerical_parity"]
        is True
        and hip_current_tangent_hardware_receipt["claims"][
            "device_resident_current_tangent_fgmres"
        ]
        is False
        and hip_current_tangent_hardware_receipt["claims"][
            "production_preconditioner_integration"
        ]
        is False
        and hip_current_tangent_hardware_receipt["claims"][
            "independent_gfx1100_hardware_execution"
        ]
        is False
        and hip_current_tangent_hardware_receipt["claims"]["performance"] is False
        and hip_current_tangent_hardware_receipt["claims"]["g1_full_building_closure"]
        is False
    )
    hip_current_tangent_compile_receipt = validate_hip_current_tangent_compile_receipt(
        _read_json(repo_root / HIP_CURRENT_TANGENT_COMPILE_RECEIPT),
        repo_root=repo_root,
        require_current_sources=True,
    )
    hip_current_tangent_compile_contract_pass = bool(
        hip_current_tangent_compile_receipt["schema_version"]
        == HIP_CURRENT_TANGENT_COMPILE_SCHEMA_VERSION
        and hip_current_tangent_compile_receipt["contract_pass"] is True
        and hip_current_tangent_compile_receipt["contract_scope"]
        == "target_compile_and_host_fixture_parser_only"
        and [
            row["architecture"]
            for row in hip_current_tangent_compile_receipt["targets"]
        ]
        == ["gfx1030", "gfx1100"]
        and all(
            row["target_compile"] is True
            and row["host_fixture_parser_execution"] is True
            and row["host_fixture_validation"]["contract_pass"] is True
            and row["host_fixture_validation"]["equation_count"] == 5
            and row["host_fixture_validation"]["actual_hardware_execution"] is False
            and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
            for row in hip_current_tangent_compile_receipt["targets"]
        )
        and hip_current_tangent_compile_receipt["claims"][
            "dual_target_host_fixture_parser_execution"
        ]
        is True
        and hip_current_tangent_compile_receipt["claims"]["actual_hardware_execution"]
        is False
        and hip_current_tangent_compile_receipt["claims"][
            "actual_mgt_current_tangent_action"
        ]
        is False
        and hip_current_tangent_compile_receipt["claims"]["numerical_parity"] is False
    )
    hip_sparse_lu_compile_receipt = validate_hip_sparse_lu_compile_receipt(
        _read_json(repo_root / HIP_SPARSE_LU_COMPILE_RECEIPT),
        repo_root=repo_root,
        require_current_sources=True,
    )
    hip_sparse_lu_compile_contract_pass = bool(
        hip_sparse_lu_compile_receipt["schema_version"]
        == HIP_SPARSE_LU_COMPILE_SCHEMA_VERSION
        and hip_sparse_lu_compile_receipt["contract_pass"] is True
        and hip_sparse_lu_compile_receipt["contract_scope"]
        == "target_compile_and_host_fixture_parser_only"
        and [row["architecture"] for row in hip_sparse_lu_compile_receipt["targets"]]
        == ["gfx1030", "gfx1100"]
        and all(
            row["target_compile"] is True
            and row["host_fixture_parser_execution"] is True
            and row["host_fixture_validation"]["contract_pass"] is True
            and row["host_fixture_validation"]["actual_hardware_execution"] is False
            and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
            for row in hip_sparse_lu_compile_receipt["targets"]
        )
        and hip_sparse_lu_compile_receipt["claims"][
            "dual_target_host_fixture_parser_execution"
        ]
        is True
        and hip_sparse_lu_compile_receipt["claims"]["actual_hardware_execution"]
        is False
        and hip_sparse_lu_compile_receipt["claims"]["numerical_parity"] is False
    )
    historical_problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=resolved_mgt,
        roundtrip_npz=None,
        checkpoint_npz=resolved_checkpoint,
        apply_state_updated_frame_axial_geometry=True,
    )
    problem = historical_problem.zero_state_problem()
    state = np.ascontiguousarray(
        problem.full_unit_zero_state_predictor_free_m(),
        dtype=np.float64,
    )
    residual = problem.residual_kn(state, LOAD_FACTOR)
    right_hand_side = np.ascontiguousarray(-residual, dtype=np.float64)
    current_tangent_operator = problem.current_tangent_operator
    if current_tangent_operator is None:
        raise ValueError(
            "actual problem lacks a backend-neutral current-tangent contract"
        )
    current_tangent_operator_manifest = dict(
        validate_current_tangent_operator_manifest(
            current_tangent_operator.to_manifest()
        )
    )
    raw_state_tangent_action = problem.state_tangent_action_free_n_per_m
    if not callable(raw_state_tangent_action):
        raise ValueError("actual problem lacks the independent analytic callback")
    predictor_direction = np.ascontiguousarray(
        state / np.linalg.norm(state, ord=np.inf),
        dtype=np.float64,
    )
    right_hand_side_direction = np.ascontiguousarray(
        right_hand_side / np.linalg.norm(right_hand_side, ord=np.inf),
        dtype=np.float64,
    )
    current_tangent_operator_parity_rows: list[dict[str, Any]] = []
    for probe_name, direction in (
        ("normalized_full_unit_predictor", predictor_direction),
        ("normalized_current_right_hand_side", right_hand_side_direction),
    ):
        contract_action_n_per_m = np.ascontiguousarray(
            current_tangent_operator.apply_n_per_m(
                state,
                LOAD_FACTOR,
                direction,
            ),
            dtype=np.float64,
        )
        analytic_callback_action_n_per_m = np.ascontiguousarray(
            raw_state_tangent_action(
                state,
                LOAD_FACTOR,
                direction,
            ),
            dtype=np.float64,
        )
        difference_inf_n_per_m = float(
            np.linalg.norm(
                contract_action_n_per_m - analytic_callback_action_n_per_m,
                ord=np.inf,
            )
        )
        reference_inf_n_per_m = max(
            float(
                np.linalg.norm(
                    analytic_callback_action_n_per_m,
                    ord=np.inf,
                )
            ),
            1.0e-30,
        )
        absolute_tolerance_n_per_m = max(
            1.0e-8,
            1.0e-11 * reference_inf_n_per_m,
        )
        current_tangent_operator_parity_rows.append(
            {
                "probe": probe_name,
                "state_data_hash": array_data_hash(state),
                "direction_data_hash": array_data_hash(direction),
                "contract_action_data_hash": array_data_hash(contract_action_n_per_m),
                "analytic_callback_action_data_hash": array_data_hash(
                    analytic_callback_action_n_per_m
                ),
                "action_bytes_exact": bool(
                    np.array_equal(
                        contract_action_n_per_m,
                        analytic_callback_action_n_per_m,
                    )
                ),
                "difference_inf_n_per_m": difference_inf_n_per_m,
                "reference_inf_n_per_m": reference_inf_n_per_m,
                "relative_difference": (difference_inf_n_per_m / reference_inf_n_per_m),
                "relative_tolerance": 1.0e-11,
                "absolute_tolerance_n_per_m": (absolute_tolerance_n_per_m),
                "gate_passed": bool(
                    difference_inf_n_per_m <= absolute_tolerance_n_per_m
                ),
            }
        )
    current_tangent_operator_parity_pass = bool(
        len(current_tangent_operator_parity_rows) == 2
        and all(row["gate_passed"] for row in current_tangent_operator_parity_rows)
    )
    actual_current_tangent_hip_fixture = create_hip_current_tangent_operator_fixture(
        current_tangent_operator,
        free_displacements_m=state,
        load_factor=LOAD_FACTOR,
        free_direction_m=right_hand_side_direction,
    )
    actual_current_tangent_hip_fixture_manifest = (
        actual_current_tangent_hip_fixture.to_manifest()
    )
    with TemporaryDirectory(
        prefix="g1_mgt_hip_current_tangent_fixture_",
    ) as temporary_directory:
        actual_current_tangent_hip_fixture_path = (
            Path(temporary_directory) / "actual_mgt_current_tangent_fixture.bin"
        )
        actual_current_tangent_hip_fixture_payload = (
            actual_current_tangent_hip_fixture.to_bytes()
        )
        actual_current_tangent_hip_fixture_payload_hash = (
            "sha256:"
            + hashlib.sha256(actual_current_tangent_hip_fixture_payload).hexdigest()
        )
        actual_current_tangent_hip_fixture_path.write_bytes(
            actual_current_tangent_hip_fixture_payload
        )
        actual_current_tangent_hip_fixture_file_byte_length = (
            actual_current_tangent_hip_fixture_path.stat().st_size
        )
        actual_current_tangent_hip_fixture_readback_hash = file_sha256(
            actual_current_tangent_hip_fixture_path
        )
        del actual_current_tangent_hip_fixture_payload
    actual_current_tangent_hip_fixture_roundtrip_pass = bool(
        actual_current_tangent_hip_fixture_file_byte_length
        == actual_current_tangent_hip_fixture_manifest["fixture_byte_length"]
        and actual_current_tangent_hip_fixture_payload_hash
        == actual_current_tangent_hip_fixture_readback_hash
        == actual_current_tangent_hip_fixture_manifest["fixture_hash"]
    )
    actual_current_tangent_hip_fixture_contract_pass = bool(
        actual_current_tangent_hip_fixture_manifest["schema_version"]
        == HIP_CURRENT_TANGENT_FIXTURE_VERSION
        and actual_current_tangent_hip_fixture_manifest["parity_profile"]
        == HIP_CURRENT_TANGENT_PARITY_PROFILE
        and actual_current_tangent_hip_fixture_manifest["schedule_profile"]
        == HIP_CURRENT_TANGENT_SCHEDULE_PROFILE
        and actual_current_tangent_hip_fixture_manifest["execution_profile"]
        == HIP_CURRENT_TANGENT_EXECUTION_PROFILE
        and actual_current_tangent_hip_fixture_manifest["accumulation_profile"]
        == HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE
        and actual_current_tangent_hip_fixture_manifest["operator_contract_hash"]
        == current_tangent_operator.contract_hash
        and actual_current_tangent_hip_fixture_manifest["load_factor"] == LOAD_FACTOR
        and actual_current_tangent_hip_fixture_manifest["dimensions"]
        == {
            "equation_count": 70_560,
            "global_dof_count": 78_282,
            "reference_nnz": 1_262_462,
            "frame_element_count": 5_572,
            "geometry_element_count": 5_572,
            "frame_incidence_count": 61_494,
            "geometry_incidence_count": 61_494,
        }
        and actual_current_tangent_hip_fixture_manifest[
            "expected_kernel_invocation_count"
        ]
        == 1
        and actual_current_tangent_hip_fixture_manifest["binary_profile"]
        == "canonical_little_endian_mixed_numeric.v1"
        and len(actual_current_tangent_hip_fixture_manifest["arrays"]) == 21
        and actual_current_tangent_hip_fixture_manifest["fixture_byte_length"]
        == 36_123_072
        and actual_current_tangent_hip_fixture_roundtrip_pass
    )
    actual_current_tangent_hip_host_parser_binding_pass = bool(
        hip_current_tangent_host_parser_receipt_pass
        and hip_current_tangent_host_parser_receipt["fixture"]["fixture_hash"]
        == actual_current_tangent_hip_fixture_manifest["fixture_hash"]
        and hip_current_tangent_host_parser_receipt["fixture"]["operator_contract_hash"]
        == actual_current_tangent_hip_fixture_manifest["operator_contract_hash"]
        and hip_current_tangent_host_parser_receipt["fixture"]["schedule_contract_hash"]
        == actual_current_tangent_hip_fixture_manifest["schedule_contract_hash"]
        and hip_current_tangent_host_parser_receipt["fixture"][
            "execution_contract_hash"
        ]
        == actual_current_tangent_hip_fixture_manifest["execution_contract_hash"]
        and hip_current_tangent_host_parser_receipt["fixture"]["dimensions"]
        == actual_current_tangent_hip_fixture_manifest["dimensions"]
        and hip_current_tangent_host_parser_receipt["fixture"]["fixture_byte_length"]
        == actual_current_tangent_hip_fixture_manifest["fixture_byte_length"]
        and hip_current_tangent_host_parser_receipt["inputs"]["state_data_hash"]
        == array_data_hash(state)
        and hip_current_tangent_host_parser_receipt["inputs"]["direction_data_hash"]
        == array_data_hash(right_hand_side_direction)
        and hip_current_tangent_host_parser_receipt["synthetic_compile_receipt"][
            "receipt_hash"
        ]
        == hip_current_tangent_compile_receipt["receipt_hash"]
        and all(
            row["host_fixture_validation"]["fixture_hash"]
            == actual_current_tangent_hip_fixture_manifest["fixture_hash"]
            for row in hip_current_tangent_host_parser_receipt["targets"]
        )
    )
    actual_current_tangent_hip_hardware_binding_pass = bool(
        hip_current_tangent_hardware_receipt_pass
        and hip_current_tangent_hardware_receipt["fixture"]["fixture_hash"]
        == actual_current_tangent_hip_fixture_manifest["fixture_hash"]
        and hip_current_tangent_hardware_receipt["fixture"]["operator_contract_hash"]
        == actual_current_tangent_hip_fixture_manifest["operator_contract_hash"]
        and hip_current_tangent_hardware_receipt["fixture"]["schedule_contract_hash"]
        == actual_current_tangent_hip_fixture_manifest["schedule_contract_hash"]
        and hip_current_tangent_hardware_receipt["fixture"]["execution_contract_hash"]
        == actual_current_tangent_hip_fixture_manifest["execution_contract_hash"]
        and hip_current_tangent_hardware_receipt["fixture"]["dimensions"]
        == actual_current_tangent_hip_fixture_manifest["dimensions"]
        and hip_current_tangent_hardware_receipt["inputs"]["state_data_hash"]
        == array_data_hash(state)
        and hip_current_tangent_hardware_receipt["inputs"]["direction_data_hash"]
        == array_data_hash(right_hand_side_direction)
        and hip_current_tangent_hardware_receipt["host_parser_prerequisite"][
            "fixture_hash"
        ]
        == actual_current_tangent_hip_fixture_manifest["fixture_hash"]
        and hip_current_tangent_hardware_receipt["comparison"]["actual_mgt_context"][
            "fixture_hash"
        ]
        == actual_current_tangent_hip_fixture_manifest["fixture_hash"]
        and hip_current_tangent_hardware_receipt["hardware_execution"][
            "action_artifact"
        ]["data_hash"]
        == hip_current_tangent_hardware_receipt["comparison"]["generic_comparison"][
            "action_data_hash"
        ]
        and hip_current_tangent_hardware_receipt["comparison"]["generic_comparison"][
            "canonical_cpu_max_abs_error_n_per_m"
        ]
        <= hip_current_tangent_hardware_receipt["comparison"]["generic_comparison"][
            "comparison_tolerance_n_per_m"
        ]
        and actual_current_tangent_hip_host_parser_binding_pass
    )

    baseline_solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(max_iterations=30),
    )
    baseline = baseline_solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=LOAD_FACTOR,
        solve_id="fixed-reference-splu-baseline",
    )
    baseline_receipt = baseline.receipt
    baseline_operator_binding = dict(baseline_solver.operator_binding)
    baseline_profile = baseline_solver.profile
    baseline_contract_hash = baseline_solver.contract_hash
    baseline_config = baseline_solver.config.contract_payload()
    baseline_reference_pattern_hash = (
        baseline_solver.reference_preconditioner_pattern_hash
    )
    baseline_reference_values_hash = (
        baseline_solver.reference_preconditioner_values_hash
    )
    current_tangent_descriptor_by_name = {
        row["name"]: row
        for row in current_tangent_operator_manifest["array_descriptors"]
    }
    current_tangent_reference_pattern_hash = canonical_hash(
        {
            "row_pointer_hash": current_tangent_descriptor_by_name[
                "reference_row_pointer"
            ]["data_hash"],
            "column_index_hash": current_tangent_descriptor_by_name[
                "reference_column_indices"
            ]["data_hash"],
            "shape": [problem.equation_count, problem.equation_count],
        }
    )
    current_tangent_operator_contract_pass = bool(
        current_tangent_operator_manifest["profile"] == CURRENT_TANGENT_OPERATOR_PROFILE
        and current_tangent_operator_manifest["contract_hash"]
        == current_tangent_operator.contract_hash
        and current_tangent_operator_manifest["array_bundle_hash"]
        == current_tangent_operator.array_bundle_hash
        and current_tangent_operator_manifest["dimensions"]["equation_count"]
        == problem.equation_count
        and current_tangent_operator_manifest["dimensions"]["global_dof_count"]
        == metadata["global_dof_count"]
        and current_tangent_operator_manifest["dimensions"]["frame_element_count"]
        == metadata["frame_element_count"]
        and current_tangent_operator_manifest["dimensions"]["geometry_element_count"]
        == metadata["frame_element_count"]
        and current_tangent_reference_pattern_hash == baseline_reference_pattern_hash
        and current_tangent_descriptor_by_name["reference_values_n_per_m"]["data_hash"]
        == baseline_reference_values_hash
        and baseline_operator_binding["current_tangent_operator_contract_hash"]
        == current_tangent_operator.contract_hash
        and baseline_operator_binding["current_tangent_operator_array_bundle_hash"]
        == current_tangent_operator.array_bundle_hash
        and baseline_operator_binding["current_tangent_operator_profile"]
        == CURRENT_TANGENT_OPERATOR_PROFILE
        and baseline_operator_binding["operator_callback_reference_evaluator"]
        == CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
        and baseline_operator_binding["operator_callback_outputs_in_contract"] is True
        and current_tangent_operator_parity_pass
    )
    del baseline_solver
    candidate_operator_binding_before = _operator_binding_payload(
        problem,
        case_id=problem.case_id,
        equation_count=problem.equation_count,
    )
    state_data_hash_before = array_data_hash(state)
    right_hand_side_data_hash_before = array_data_hash(right_hand_side)

    free_global_dofs = problem.free_equation_global_dofs
    if free_global_dofs is None:
        raise ValueError("actual problem lacks a free-equation order")
    reference_csr = problem.reference_preconditioner_free_csr_n_per_m()
    block_inverse, block_meta = build_node_block_jacobi_preconditioner(
        reference_csr,
        free_global_dofs=free_global_dofs,
    )
    block_inverse.sort_indices()

    def operator(direction_m: np.ndarray) -> np.ndarray:
        return problem.consistent_state_tangent_action_kn_per_m(
            state,
            LOAD_FACTOR,
            direction_m,
        )

    def block_preconditioner(vector_kn: np.ndarray) -> np.ndarray:
        return np.asarray(
            block_inverse @ (vector_kn * 1000.0),
            dtype=np.float64,
        )

    candidate_config = _config(max_iterations=120)
    candidate = _run_fgmres(
        operator=operator,
        preconditioner=block_preconditioner,
        right_hand_side_kn=right_hand_side,
        config=candidate_config,
    )

    host_ilut_drop_tolerance = 1.0e-6
    host_ilut_fill_factor = 20.0
    host_ilut_column_permutation = "COLAMD"
    host_ilut_factor = spilu(
        reference_csr.tocsc(),
        drop_tol=host_ilut_drop_tolerance,
        fill_factor=host_ilut_fill_factor,
        permc_spec=host_ilut_column_permutation,
    )
    host_ilut_lower = _sparse_factor_component_payload(host_ilut_factor.L)
    host_ilut_upper = _sparse_factor_component_payload(host_ilut_factor.U)
    host_ilut_row_permutation_hash = array_data_hash(
        np.asarray(host_ilut_factor.perm_r, dtype="<i8")
    )
    host_ilut_column_permutation_hash = array_data_hash(
        np.asarray(host_ilut_factor.perm_c, dtype="<i8")
    )
    host_ilut_canonical_factor = _canonical_factor_from_superlu(
        host_ilut_factor,
        source_operator_pattern_hash=baseline_reference_pattern_hash,
        source_operator_numeric_values_hash=baseline_reference_values_hash,
    )
    host_ilut_factor_manifest = host_ilut_canonical_factor.manifest()
    host_ilut_binary_bundle = create_canonical_sparse_lu_binary_artifact_bundle(
        host_ilut_canonical_factor,
        artifact_uri_prefix=("artifact://g1-mgt-preconditioner/host-ilut"),
    )
    host_ilut_binary_manifest = host_ilut_binary_bundle.to_manifest()
    with TemporaryDirectory(
        prefix="g1_mgt_canonical_ilut_",
    ) as temporary_directory:
        binary_directory = Path(temporary_directory) / "factor"
        write_canonical_sparse_lu_binary_artifacts(
            host_ilut_binary_bundle,
            binary_directory,
        )
        host_ilut_reloaded_factor = read_canonical_sparse_lu_binary_artifacts(
            host_ilut_binary_bundle,
            binary_directory,
        )
        host_ilut_binary_file_count = len(tuple(binary_directory.iterdir()))
        host_ilut_binary_total_byte_length = sum(
            path.stat().st_size for path in binary_directory.iterdir()
        )
    host_ilut_binary_roundtrip_pass = bool(
        host_ilut_reloaded_factor.contract_hash
        == host_ilut_canonical_factor.contract_hash
        == host_ilut_binary_manifest["factor_contract_hash"]
        and host_ilut_reloaded_factor.manifest() == host_ilut_factor_manifest
        and host_ilut_binary_manifest["schema_version"]
        == CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION
        and host_ilut_binary_manifest["storage_profile"]
        == CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE
        and host_ilut_binary_file_count == 8
        and host_ilut_binary_total_byte_length
        == host_ilut_binary_manifest["total_byte_length"]
    )
    host_ilut_hip_fixture = create_hip_sparse_lu_apply_fixture(
        host_ilut_reloaded_factor,
        right_hand_side_kn=right_hand_side,
    )
    host_ilut_hip_lower_level_widths = np.diff(
        host_ilut_hip_fixture.lower_level_pointer
    )
    host_ilut_hip_upper_level_widths = np.diff(
        host_ilut_hip_fixture.upper_level_pointer
    )
    host_ilut_hip_schedule_arrays = (
        host_ilut_hip_fixture.lower_level_pointer,
        host_ilut_hip_fixture.lower_level_rows,
        host_ilut_hip_fixture.upper_level_pointer,
        host_ilut_hip_fixture.upper_level_rows,
    )
    host_ilut_hip_schedule_total_byte_length = sum(
        int(array.nbytes) for array in host_ilut_hip_schedule_arrays
    )
    host_ilut_hip_declared_fixture_binary_byte_length = int(
        48
        + host_ilut_factor_manifest["total_byte_length"]
        + host_ilut_hip_schedule_total_byte_length
        + right_hand_side.nbytes
    )
    host_ilut_hip_schedule_contract_pass = bool(
        host_ilut_hip_fixture.dimension == 70_560
        and host_ilut_hip_fixture.factor.contract_hash
        == host_ilut_factor_manifest["contract_hash"]
        and host_ilut_hip_fixture.right_hand_side_kn.shape == (70_560,)
        and np.array_equal(
            host_ilut_hip_fixture.right_hand_side_kn,
            right_hand_side,
        )
        and host_ilut_hip_fixture.lower_level_rows.size == 70_560
        and host_ilut_hip_fixture.upper_level_rows.size == 70_560
        and host_ilut_hip_fixture.expected_kernel_invocation_count
        == (
            host_ilut_hip_fixture.lower_level_count
            + host_ilut_hip_fixture.upper_level_count
            + 2
        )
        and host_ilut_hip_schedule_total_byte_length > 1_000_000
        and host_ilut_hip_declared_fixture_binary_byte_length
        > host_ilut_binary_manifest["total_byte_length"]
    )
    host_ilut_superlu_reference_apply = np.ascontiguousarray(
        host_ilut_factor.solve(right_hand_side * 1000.0),
        dtype=np.float64,
    )
    host_ilut_canonical_apply = host_ilut_reloaded_factor.solve_kn_to_m(right_hand_side)
    host_ilut_canonical_repeat_apply = host_ilut_reloaded_factor.solve_kn_to_m(
        right_hand_side
    )
    host_ilut_apply_difference_inf_m = float(
        np.max(np.abs(host_ilut_canonical_apply - host_ilut_superlu_reference_apply))
    )
    host_ilut_apply_repeat_byte_exact = bool(
        np.array_equal(
            host_ilut_canonical_apply,
            host_ilut_canonical_repeat_apply,
        )
    )
    del host_ilut_binary_bundle
    del host_ilut_canonical_factor
    del host_ilut_factor
    host_ilut_canonical_factor = host_ilut_reloaded_factor
    with TemporaryDirectory(
        prefix="g1_mgt_hip_sparse_lu_fixture_",
    ) as temporary_directory:
        host_ilut_hip_fixture_path = (
            Path(temporary_directory) / "actual_mgt_sparse_lu_fixture.bin"
        )
        host_ilut_hip_fixture_payload = host_ilut_hip_fixture.to_bytes()
        host_ilut_hip_fixture_payload_hash = (
            "sha256:" + hashlib.sha256(host_ilut_hip_fixture_payload).hexdigest()
        )
        host_ilut_hip_fixture_path.write_bytes(host_ilut_hip_fixture_payload)
        host_ilut_hip_fixture_file_byte_length = (
            host_ilut_hip_fixture_path.stat().st_size
        )
        host_ilut_hip_fixture_readback_hash = file_sha256(host_ilut_hip_fixture_path)
        del host_ilut_hip_fixture_payload
    host_ilut_hip_fixture_roundtrip_pass = bool(
        host_ilut_hip_fixture_file_byte_length
        == host_ilut_hip_declared_fixture_binary_byte_length
        and host_ilut_hip_fixture_payload_hash == host_ilut_hip_fixture_readback_hash
    )
    host_ilut_config = _config(max_iterations=30)
    host_ilut_state_solver = (
        create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu(
            problem,
            factor=host_ilut_canonical_factor,
            binary_artifact_manifest=host_ilut_binary_manifest,
            config=host_ilut_config,
        )
    )
    host_ilut_solve = host_ilut_state_solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=LOAD_FACTOR,
        solve_id="canonical-host-ilut-current-tangent",
    )
    host_ilut_candidate = host_ilut_solve.receipt
    host_ilut_solver_profile = host_ilut_state_solver.profile
    host_ilut_solver_contract_hash = host_ilut_state_solver.contract_hash
    host_ilut_state_operator_binding_hash = host_ilut_candidate[
        "state_operator_binding_hash"
    ]
    host_ilut_solver_preconditioner = host_ilut_candidate["preconditioner"]
    host_ilut_solver_recurrence = host_ilut_candidate["recurrence"]
    host_ilut_solver_operator_binding = host_ilut_candidate["operator_binding"]
    host_ilut_solver_solution = np.ascontiguousarray(
        host_ilut_solve.solution_free,
        dtype=np.float64,
    )
    candidate_operator_binding_after = _operator_binding_payload(
        problem,
        case_id=problem.case_id,
        equation_count=problem.equation_count,
    )
    same_operator_binding = bool(
        candidate_operator_binding_before
        == candidate_operator_binding_after
        == baseline_operator_binding
    )
    state_and_right_hand_side_unchanged = bool(
        array_data_hash(state) == state_data_hash_before
        and array_data_hash(right_hand_side) == right_hand_side_data_hash_before
    )
    candidate_solution = np.ascontiguousarray(
        candidate["solution_m"],
        dtype=np.float64,
    )
    candidate_residual = np.ascontiguousarray(
        candidate["explicit_residual_kn"],
        dtype=np.float64,
    )
    independent_residual = np.ascontiguousarray(
        operator(candidate_solution) - right_hand_side,
        dtype=np.float64,
    )
    host_ilut_solution = host_ilut_solver_solution
    host_ilut_residual = np.ascontiguousarray(
        right_hand_side - operator(host_ilut_solution),
        dtype=np.float64,
    )
    host_ilut_independent_residual = np.ascontiguousarray(
        operator(host_ilut_solution) - right_hand_side,
        dtype=np.float64,
    )
    explicit_observations = candidate["explicit_observations"]
    observation_30 = _observation_at(explicit_observations, 30)
    observation_120 = _observation_at(explicit_observations, 120)
    final_inf = float(np.max(np.abs(candidate_residual)))
    independent_inf = float(np.max(np.abs(independent_residual)))
    host_ilut_final_inf = float(np.max(np.abs(host_ilut_residual)))
    host_ilut_independent_inf = float(np.max(np.abs(host_ilut_independent_residual)))
    initial_inf = float(np.max(np.abs(right_hand_side)))
    host_ilut_state_tangent_solver_integration_pass = bool(
        host_ilut_solver_profile == MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE
        and host_ilut_candidate["profile"] == host_ilut_solver_profile
        and host_ilut_candidate["contract_hash"] == host_ilut_solver_contract_hash
        and host_ilut_solver_operator_binding == baseline_operator_binding
        and host_ilut_solver_preconditioner["profile"]
        == MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE
        and host_ilut_solver_preconditioner["pattern_hash"]
        == baseline_reference_pattern_hash
        and host_ilut_solver_preconditioner["numeric_values_hash"]
        == baseline_reference_values_hash
        and host_ilut_solver_preconditioner["factor_contract_hash"]
        == host_ilut_canonical_factor.contract_hash
        and host_ilut_solver_preconditioner["binary_artifact_bundle_hash"]
        == host_ilut_binary_manifest["bundle_hash"]
        and host_ilut_solver_preconditioner["binary_artifact_bundle_bound"] is True
        and host_ilut_solver_recurrence["operator_callback_outputs_in_contract"] is True
        and host_ilut_solver_recurrence["preconditioner_callback_outputs_in_contract"]
        is True
        and host_ilut_candidate["matrix_free_current_state_operator_action"] is True
        and host_ilut_candidate["materialized_current_tangent"] is False
        and host_ilut_candidate["solution_data_hash"]
        == array_data_hash(host_ilut_solution)
        and host_ilut_candidate["explicit_residual_data_hash"]
        == array_data_hash(host_ilut_residual)
        and host_ilut_candidate["production_solver_claim"] is False
        and host_ilut_candidate["rocm_hip_parity_claim"] is False
    )
    block_pattern_hash = canonical_hash(
        {
            "shape": [problem.equation_count, problem.equation_count],
            "row_pointer_data_hash": array_data_hash(
                np.asarray(block_inverse.indptr, dtype="<i8")
            ),
            "column_index_data_hash": array_data_hash(
                np.asarray(block_inverse.indices, dtype="<i8")
            ),
        }
    )
    block_values_hash = array_data_hash(np.asarray(block_inverse.data, dtype="<f8"))
    candidate_counterevidence_pass = bool(
        not candidate["converged"]
        and candidate["terminal_reason"] == "max_iterations"
        and candidate["iteration_count"] == 120
        and candidate["restart_count"] == 7
        and candidate["operator_action_count"] == 129
        and candidate["preconditioner_application_count"] == 120
        and len(explicit_observations) == 9
        and observation_30["explicit_residual_inf_kn"] > RESIDUAL_GATE_KN
        and observation_120["explicit_residual_inf_kn"] > RESIDUAL_GATE_KN
        and observation_120["explicit_residual_inf_kn"]
        < observation_30["explicit_residual_inf_kn"]
        and final_inf == observation_120["explicit_residual_inf_kn"]
        and independent_inf == final_inf
        and np.array_equal(independent_residual, -candidate_residual)
        and same_operator_binding
        and state_and_right_hand_side_unchanged
    )
    host_ilut_factor_contract_pass = bool(
        host_ilut_factor_manifest["profile"] == CANONICAL_SPARSE_LU_PROFILE
        and host_ilut_factor_manifest["dimension"] == problem.equation_count
        and host_ilut_factor_manifest["source_operator_pattern_hash"]
        == baseline_reference_pattern_hash
        and host_ilut_factor_manifest["source_operator_numeric_values_hash"]
        == baseline_reference_values_hash
        and host_ilut_factor_manifest["factor_nnz"]
        == host_ilut_lower["nnz"] + host_ilut_upper["nnz"]
        and host_ilut_factor_manifest["array_count"] == 8
        and host_ilut_factor_manifest["total_byte_length"] > 0
        and host_ilut_factor_manifest["apply_contract"]["profile"]
        == CANONICAL_SPARSE_LU_APPLY_PROFILE
        and host_ilut_binary_roundtrip_pass
        and host_ilut_binary_manifest["artifact_count"] == 8
        and host_ilut_binary_manifest["total_byte_length"]
        == host_ilut_factor_manifest["total_byte_length"]
        and host_ilut_apply_repeat_byte_exact
        and host_ilut_apply_difference_inf_m <= 1.0e-9
        and host_ilut_state_tangent_solver_integration_pass
    )
    host_ilut_diagnostic_effectiveness_pass = bool(
        host_ilut_solve.contract_pass
        and host_ilut_candidate["converged"]
        and host_ilut_candidate["terminal_reason"] == "converged_explicit_residual"
        and host_ilut_candidate["iteration_count"] <= 30
        and host_ilut_final_inf <= RESIDUAL_GATE_KN
        and host_ilut_independent_inf == host_ilut_final_inf
        and np.array_equal(
            host_ilut_independent_residual,
            -host_ilut_residual,
        )
        and same_operator_binding
        and state_and_right_hand_side_unchanged
        and host_ilut_factor_contract_pass
    )
    contract_pass = bool(
        metadata["free_equation_count"] == 70_560
        and hip_current_tangent_compile_contract_pass
        and actual_current_tangent_hip_fixture_contract_pass
        and actual_current_tangent_hip_host_parser_binding_pass
        and actual_current_tangent_hip_hardware_binding_pass
        and hip_sparse_lu_compile_contract_pass
        and current_tangent_operator_contract_pass
        and host_ilut_hip_schedule_contract_pass
        and host_ilut_hip_fixture_roundtrip_pass
        and baseline.contract_pass
        and baseline_receipt["operator_binding_ready"]
        and baseline_receipt["deterministic_host_recurrence_arithmetic_claim"]
        and baseline_receipt["explicit_residual_inf_kn"] <= RESIDUAL_GATE_KN
        and block_meta["block_count"] == 12_606
        and block_meta["singular_block_count"] == 0
        and block_inverse.nnz == 408_132
        and candidate_counterevidence_pass
        and host_ilut_diagnostic_effectiveness_pass
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "diagnostic_execution_ready": contract_pass,
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
            "checkpoint_npz": _label(repo_root, checkpoint_npz),
            "checkpoint_sha256": file_sha256(resolved_checkpoint),
            "load_factor": LOAD_FACTOR,
            "state_policy": "full_unit_zero_state_linear_predictor",
            "equation_count": problem.equation_count,
            "state_data_hash": array_data_hash(state),
            "right_hand_side_data_hash": array_data_hash(right_hand_side),
            "right_hand_side_inf_kn": initial_inf,
        },
        "operator_binding": baseline_operator_binding,
        "current_tangent_operator_contract": {
            "manifest": current_tangent_operator_manifest,
            "reference_preconditioner_pattern_hash": (
                current_tangent_reference_pattern_hash
            ),
            "reference_preconditioner_numeric_values_hash": (
                current_tangent_descriptor_by_name["reference_values_n_per_m"][
                    "data_hash"
                ]
            ),
            "array_total_byte_length": sum(
                int(row["byte_length"])
                for row in current_tangent_operator_manifest["array_descriptors"]
            ),
            "analytic_callback_parity_probes": (current_tangent_operator_parity_rows),
            "analytic_callback_parity_pass": (current_tangent_operator_parity_pass),
            "operator_callback_outputs_in_contract": True,
            "cpu_reference_evaluator_executed": True,
            "hip_execution": actual_current_tangent_hip_hardware_binding_pass,
            "cpu_hip_numerical_parity": (
                actual_current_tangent_hip_hardware_binding_pass
            ),
            "contract_pass": current_tangent_operator_contract_pass,
        },
        "hip_current_tangent_execution_preparation": {
            "compile_evidence": {
                "receipt": str(HIP_CURRENT_TANGENT_COMPILE_RECEIPT),
                "schema_version": hip_current_tangent_compile_receipt["schema_version"],
                "receipt_hash": hip_current_tangent_compile_receipt["receipt_hash"],
                "contract_scope": hip_current_tangent_compile_receipt["contract_scope"],
                "compiler": hip_current_tangent_compile_receipt["compiler"],
                "targets": hip_current_tangent_compile_receipt["targets"],
                "dual_target_compile_pass": (hip_current_tangent_compile_contract_pass),
                "dual_target_host_fixture_parser_execution": (
                    hip_current_tangent_compile_contract_pass
                ),
                "host_parser_fixture_scope": ("five_equation_synthetic_fixture_only"),
            },
            "actual_mgt_host_parser_receipt": {
                "receipt": str(HIP_CURRENT_TANGENT_HOST_PARSER_RECEIPT),
                "schema_version": (
                    hip_current_tangent_host_parser_receipt["schema_version"]
                ),
                "receipt_hash": hip_current_tangent_host_parser_receipt["receipt_hash"],
                "contract_scope": hip_current_tangent_host_parser_receipt[
                    "contract_scope"
                ],
                "compiler": hip_current_tangent_host_parser_receipt["compiler"],
                "targets": hip_current_tangent_host_parser_receipt["targets"],
                "synthetic_and_actual_parser_binary_identity": (
                    hip_current_tangent_host_parser_receipt["claims"][
                        "synthetic_and_actual_parser_binary_identity"
                    ]
                ),
                "dual_target_host_fixture_parser_execution": (
                    hip_current_tangent_host_parser_receipt["claims"][
                        "actual_mgt_dual_target_host_fixture_parser_execution"
                    ]
                ),
                "hip_runtime_api_call_count": 0,
                "actual_hardware_execution": False,
                "current_tangent_action_executed": False,
                "cpu_hip_numerical_parity": False,
                "contract_pass": (actual_current_tangent_hip_host_parser_binding_pass),
            },
            "actual_mgt_hardware_parity_receipt": {
                "receipt": str(HIP_CURRENT_TANGENT_HARDWARE_RECEIPT),
                "schema_version": hip_current_tangent_hardware_receipt[
                    "schema_version"
                ],
                "receipt_hash": hip_current_tangent_hardware_receipt["receipt_hash"],
                "contract_scope": hip_current_tangent_hardware_receipt[
                    "contract_scope"
                ],
                "device_name": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["device_name"],
                "gcn_arch_name": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["gcn_arch_name"],
                "binary_sha256": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["binary_sha256"],
                "binary_byte_length": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["binary_byte_length"],
                "runtime_output_hash": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["runtime_output_hash"],
                "action_artifact": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["action_artifact"],
                "kernel_invocation_count": hip_current_tangent_hardware_receipt[
                    "hardware_execution"
                ]["runtime_metadata"]["kernel_invocation_count"],
                "mid_action_d2h_transfer_count": (
                    hip_current_tangent_hardware_receipt["hardware_execution"][
                        "runtime_metadata"
                    ]["mid_action_d2h_transfer_count"]
                ),
                "blocking_d2h_synchronization_count": (
                    hip_current_tangent_hardware_receipt["hardware_execution"][
                        "runtime_metadata"
                    ]["blocking_d2h_synchronization_count"]
                ),
                "canonical_cpu_max_abs_error_n_per_m": (
                    hip_current_tangent_hardware_receipt["comparison"][
                        "generic_comparison"
                    ]["canonical_cpu_max_abs_error_n_per_m"]
                ),
                "comparison_tolerance_n_per_m": (
                    hip_current_tangent_hardware_receipt["comparison"][
                        "generic_comparison"
                    ]["comparison_tolerance_n_per_m"]
                ),
                "canonical_relative_max_error": (
                    hip_current_tangent_hardware_receipt["comparison"][
                        "actual_mgt_context"
                    ]["canonical_relative_max_error"]
                ),
                "device_order_cpu_max_abs_error_n_per_m": (
                    hip_current_tangent_hardware_receipt["comparison"][
                        "generic_comparison"
                    ]["device_order_cpu_max_abs_error_n_per_m"]
                ),
                "device_order_bitwise_match": (
                    hip_current_tangent_hardware_receipt["comparison"][
                        "actual_mgt_context"
                    ]["device_order_bitwise_match"]
                ),
                "actual_hardware_execution": True,
                "cpu_hip_numerical_parity": True,
                "independent_gfx1100_hardware_execution": False,
                "contract_pass": (actual_current_tangent_hip_hardware_binding_pass),
            },
            "actual_mgt_fixture": {
                "fixture_schema_version": (
                    actual_current_tangent_hip_fixture_manifest["schema_version"]
                ),
                "fixture_hash": (
                    actual_current_tangent_hip_fixture_manifest["fixture_hash"]
                ),
                "parity_profile": (
                    actual_current_tangent_hip_fixture_manifest["parity_profile"]
                ),
                "schedule_profile": (
                    actual_current_tangent_hip_fixture_manifest["schedule_profile"]
                ),
                "execution_profile": (
                    actual_current_tangent_hip_fixture_manifest["execution_profile"]
                ),
                "accumulation_profile": (
                    actual_current_tangent_hip_fixture_manifest["accumulation_profile"]
                ),
                "operator_contract_hash": (
                    actual_current_tangent_hip_fixture_manifest[
                        "operator_contract_hash"
                    ]
                ),
                "schedule_contract_hash": (
                    actual_current_tangent_hip_fixture_manifest[
                        "schedule_contract_hash"
                    ]
                ),
                "execution_contract_hash": (
                    actual_current_tangent_hip_fixture_manifest[
                        "execution_contract_hash"
                    ]
                ),
                "load_factor": (
                    actual_current_tangent_hip_fixture_manifest["load_factor"]
                ),
                "state_data_hash": array_data_hash(state),
                "direction_data_hash": array_data_hash(right_hand_side_direction),
                "dimensions": (
                    actual_current_tangent_hip_fixture_manifest["dimensions"]
                ),
                "expected_kernel_invocation_count": (
                    actual_current_tangent_hip_fixture_manifest[
                        "expected_kernel_invocation_count"
                    ]
                ),
                "binary_profile": (
                    actual_current_tangent_hip_fixture_manifest["binary_profile"]
                ),
                "array_count": len(
                    actual_current_tangent_hip_fixture_manifest["arrays"]
                ),
                "fixture_byte_length": (
                    actual_current_tangent_hip_fixture_manifest["fixture_byte_length"]
                ),
                "fixture_binary_materialized": True,
                "fixture_binary_ephemeral": True,
                "fixture_binary_sha256": (
                    actual_current_tangent_hip_fixture_payload_hash
                ),
                "fixture_binary_readback_sha256": (
                    actual_current_tangent_hip_fixture_readback_hash
                ),
                "fixture_binary_roundtrip_pass": (
                    actual_current_tangent_hip_fixture_roundtrip_pass
                ),
                "fixture_binary_persisted": False,
                "actual_mgt_fixture_contract_pass": (
                    actual_current_tangent_hip_fixture_contract_pass
                ),
                "host_fixture_parser_execution": True,
                "host_fixture_parser_target_count": 2,
                "host_fixture_parser_hip_runtime_api_call_count": 0,
                "host_fixture_parser_binding_pass": (
                    actual_current_tangent_hip_host_parser_binding_pass
                ),
                "device_execution": (actual_current_tangent_hip_hardware_binding_pass),
                "cpu_hip_numerical_parity": (
                    actual_current_tangent_hip_hardware_binding_pass
                ),
            },
            "actual_hardware_execution": (
                actual_current_tangent_hip_hardware_binding_pass
            ),
            "numerical_parity": (actual_current_tangent_hip_hardware_binding_pass),
            "production_current_tangent_fgmres": False,
            "performance": False,
            "contract_pass": bool(
                hip_current_tangent_compile_contract_pass
                and actual_current_tangent_hip_fixture_contract_pass
                and actual_current_tangent_hip_host_parser_binding_pass
                and actual_current_tangent_hip_hardware_binding_pass
            ),
        },
        "host_recurrence_contract": {
            "profile": MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
            "accumulation_profile": (MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE),
            "deterministic_host_arithmetic": True,
            "operator_callback_outputs_in_contract": True,
            "preconditioner_callback_outputs_in_contract": False,
            "cross_platform_end_to_end_deterministic_claim": False,
        },
        "fixed_reference_splu_baseline": {
            "profile": baseline_profile,
            "contract_hash": baseline_contract_hash,
            "config": baseline_config,
            "iteration_count": baseline_receipt["iteration_count"],
            "operator_action_count": baseline_receipt["operator_action_count"],
            "explicit_residual_inf_kn": baseline_receipt["explicit_residual_inf_kn"],
            "solution_data_hash": baseline_receipt["solution_data_hash"],
            "residual_gate_passed": bool(
                baseline_receipt["explicit_residual_inf_kn"] <= RESIDUAL_GATE_KN
            ),
            "production_preconditioner_claim": False,
        },
        "node_block_jacobi_candidate": {
            "profile": "free_global_node_6x6_block_jacobi_inverse.v1",
            "construction": {
                "block_count": int(block_meta["block_count"]),
                "singular_block_count": int(block_meta["singular_block_count"]),
                "inverse_operator_nnz": int(block_inverse.nnz),
                "inverse_pattern_hash": block_pattern_hash,
                "inverse_numeric_values_hash": block_values_hash,
                "source_force_unit": "N",
                "apply_input_force_unit": "kN",
                "apply_output_displacement_unit": "m",
                "input_conversion_to_n": 1000.0,
                "batched_numpy_linalg_inverse": True,
                "deterministic_construction_claim": False,
                "fallback_exercised": bool(block_meta["singular_block_count"] > 0),
            },
            "config": candidate_config.contract_payload(),
            "converged": bool(candidate["converged"]),
            "terminal_reason": candidate["terminal_reason"],
            "iteration_count": int(candidate["iteration_count"]),
            "restart_count": int(candidate["restart_count"]),
            "operator_action_count": int(candidate["operator_action_count"]),
            "preconditioner_application_count": int(
                candidate["preconditioner_application_count"]
            ),
            "explicit_residual_check_count": int(
                candidate["explicit_residual_check_count"]
            ),
            "explicit_observations": explicit_observations,
            "iteration_30_explicit_residual_inf_kn": observation_30[
                "explicit_residual_inf_kn"
            ],
            "iteration_120_explicit_residual_inf_kn": observation_120[
                "explicit_residual_inf_kn"
            ],
            "iteration_30_to_120_residual_ratio": float(
                observation_120["explicit_residual_inf_kn"]
                / observation_30["explicit_residual_inf_kn"]
            ),
            "final_explicit_residual_l2_kn": float(
                candidate["explicit_observations"][-1]["explicit_residual_l2_kn"]
            ),
            "final_explicit_residual_inf_kn": final_inf,
            "independent_residual_inf_kn": independent_inf,
            "solution_data_hash": array_data_hash(candidate_solution),
            "explicit_residual_data_hash": array_data_hash(candidate_residual),
            "independent_residual_data_hash": array_data_hash(independent_residual),
            "residual_gate_kn": RESIDUAL_GATE_KN,
            "residual_gate_passed": bool(final_inf <= RESIDUAL_GATE_KN),
            "residual_gate_exceedance_factor": final_inf / RESIDUAL_GATE_KN,
            "initial_to_final_reduction_factor": initial_inf / final_inf,
            "candidate_counterevidence_pass": candidate_counterevidence_pass,
            "portable_apply_topology_candidate": True,
            "production_preconditioner_effectiveness_claim": False,
            "hip_apply_parity_claim": False,
            "performance_claim": False,
        },
        "host_ilut_candidate": {
            "profile": "canonical_csr_ilut_fixed_reference_factor.v1",
            "construction": {
                "factorization_backend": ("scipy.sparse.linalg.spilu_superlu"),
                "scipy_version": scipy.__version__,
                "drop_tolerance": host_ilut_drop_tolerance,
                "fill_factor": host_ilut_fill_factor,
                "column_permutation": host_ilut_column_permutation,
                "reference_preconditioner_contract_hash": (baseline_contract_hash),
                "reference_matrix_nnz": int(reference_csr.nnz),
                "lower_factor": host_ilut_lower,
                "upper_factor": host_ilut_upper,
                "factor_nnz": int(host_ilut_lower["nnz"] + host_ilut_upper["nnz"]),
                "factor_fill_ratio": float(
                    (host_ilut_lower["nnz"] + host_ilut_upper["nnz"])
                    / reference_csr.nnz
                ),
                "row_permutation_data_hash": (host_ilut_row_permutation_hash),
                "column_permutation_data_hash": (host_ilut_column_permutation_hash),
                "factor_contract_hash": (host_ilut_canonical_factor.contract_hash),
                "deterministic_construction_claim": False,
                "serialized_backend_neutral_factor_artifact_claim": (
                    host_ilut_binary_roundtrip_pass
                ),
            },
            "canonical_factor_manifest": host_ilut_factor_manifest,
            "canonical_binary_artifact_manifest": (host_ilut_binary_manifest),
            "apply_backend": ("canonical_csr_sparse_lu_ordered_python_fsum"),
            "source_force_unit": "N",
            "apply_input_force_unit": "kN",
            "apply_output_displacement_unit": "m",
            "input_conversion_to_n": 1000.0,
            "superlu_reference_apply_solution_data_hash": array_data_hash(
                host_ilut_superlu_reference_apply
            ),
            "canonical_apply_solution_data_hash": array_data_hash(
                host_ilut_canonical_apply
            ),
            "canonical_repeat_apply_solution_data_hash": array_data_hash(
                host_ilut_canonical_repeat_apply
            ),
            "canonical_apply_repeat_byte_exact": (host_ilut_apply_repeat_byte_exact),
            "canonical_apply_superlu_difference_inf_m": (
                host_ilut_apply_difference_inf_m
            ),
            "canonical_factor_contract_pass": (host_ilut_factor_contract_pass),
            "full_scale_ephemeral_binary_roundtrip_pass": (
                host_ilut_binary_roundtrip_pass
            ),
            "ephemeral_binary_file_count": host_ilut_binary_file_count,
            "ephemeral_binary_total_byte_length": (host_ilut_binary_total_byte_length),
            "factor_artifact_bytes_persisted": False,
            "state_tangent_solver_integration": {
                "profile": host_ilut_solver_profile,
                "contract_hash": host_ilut_solver_contract_hash,
                "state_operator_binding_hash": (host_ilut_state_operator_binding_hash),
                "operator_binding_hash": baseline_operator_binding["binding_hash"],
                "preconditioner_profile": host_ilut_solver_preconditioner["profile"],
                "factor_contract_hash": host_ilut_solver_preconditioner[
                    "factor_contract_hash"
                ],
                "binary_artifact_bundle_hash": (
                    host_ilut_solver_preconditioner["binary_artifact_bundle_hash"]
                ),
                "canonical_factor_source_binding_pass": bool(
                    host_ilut_solver_preconditioner["pattern_hash"]
                    == baseline_reference_pattern_hash
                    and host_ilut_solver_preconditioner["numeric_values_hash"]
                    == baseline_reference_values_hash
                ),
                "binary_artifact_bundle_bound": (
                    host_ilut_solver_preconditioner["binary_artifact_bundle_bound"]
                ),
                "preconditioner_callback_outputs_in_contract": (
                    host_ilut_solver_recurrence[
                        "preconditioner_callback_outputs_in_contract"
                    ]
                ),
                "operator_callback_outputs_in_contract": (
                    host_ilut_solver_recurrence["operator_callback_outputs_in_contract"]
                ),
                "matrix_free_current_state_operator_action": (
                    host_ilut_candidate["matrix_free_current_state_operator_action"]
                ),
                "materialized_current_tangent": host_ilut_candidate[
                    "materialized_current_tangent"
                ],
                "integration_pass": (host_ilut_state_tangent_solver_integration_pass),
                "production_solver_claim": host_ilut_candidate[
                    "production_solver_claim"
                ],
                "rocm_hip_parity_claim": host_ilut_candidate["rocm_hip_parity_claim"],
            },
            "config": host_ilut_config.contract_payload(),
            "converged": bool(host_ilut_candidate["converged"]),
            "terminal_reason": host_ilut_candidate["terminal_reason"],
            "iteration_count": int(host_ilut_candidate["iteration_count"]),
            "restart_count": int(host_ilut_candidate["restart_count"]),
            "operator_action_count": int(host_ilut_candidate["operator_action_count"]),
            "preconditioner_application_count": int(
                host_ilut_candidate["preconditioner_application_count"]
            ),
            "explicit_residual_check_count": int(
                host_ilut_candidate["explicit_residual_check_count"]
            ),
            "explicit_observations": host_ilut_candidate["explicit_observations"],
            "final_explicit_residual_l2_kn": float(
                host_ilut_candidate["explicit_observations"][-1][
                    "explicit_residual_l2_kn"
                ]
            ),
            "final_explicit_residual_inf_kn": host_ilut_final_inf,
            "independent_residual_inf_kn": host_ilut_independent_inf,
            "solution_data_hash": array_data_hash(host_ilut_solution),
            "explicit_residual_data_hash": array_data_hash(host_ilut_residual),
            "independent_residual_data_hash": array_data_hash(
                host_ilut_independent_residual
            ),
            "residual_gate_kn": RESIDUAL_GATE_KN,
            "residual_gate_passed": bool(host_ilut_final_inf <= RESIDUAL_GATE_KN),
            "initial_to_final_reduction_factor": (initial_inf / host_ilut_final_inf),
            "cpu_diagnostic_effectiveness_pass": (
                host_ilut_diagnostic_effectiveness_pass
            ),
            "factor_apply_topology_portable_in_principle": True,
            "serialized_backend_neutral_factor_contract_implemented": True,
            "production_preconditioner_effectiveness_claim": False,
            "hip_apply_parity_claim": False,
            "performance_claim": False,
        },
        "hip_triangular_apply_compile_evidence": {
            "receipt": str(HIP_SPARSE_LU_COMPILE_RECEIPT),
            "schema_version": hip_sparse_lu_compile_receipt["schema_version"],
            "receipt_hash": hip_sparse_lu_compile_receipt["receipt_hash"],
            "contract_scope": hip_sparse_lu_compile_receipt["contract_scope"],
            "compiler": hip_sparse_lu_compile_receipt["compiler"],
            "targets": hip_sparse_lu_compile_receipt["targets"],
            "dual_target_compile_pass": (hip_sparse_lu_compile_contract_pass),
            "dual_target_host_fixture_parser_execution": (
                hip_sparse_lu_compile_contract_pass
            ),
            "actual_mgt_dependency_schedule": {
                "schedule_profile": HIP_SPARSE_LU_APPLY_SCHEDULE_PROFILE,
                "execution_profile": HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
                "factor_contract_hash": (host_ilut_hip_fixture.factor.contract_hash),
                "right_hand_side_data_hash": array_data_hash(
                    host_ilut_hip_fixture.right_hand_side_kn
                ),
                "dimension": host_ilut_hip_fixture.dimension,
                "lower_nnz": int(
                    host_ilut_hip_fixture.factor.lower_numeric_values.size
                ),
                "upper_nnz": int(
                    host_ilut_hip_fixture.factor.upper_numeric_values.size
                ),
                "lower_level_count": (host_ilut_hip_fixture.lower_level_count),
                "upper_level_count": (host_ilut_hip_fixture.upper_level_count),
                "lower_maximum_level_width": int(
                    np.max(host_ilut_hip_lower_level_widths)
                ),
                "upper_maximum_level_width": int(
                    np.max(host_ilut_hip_upper_level_widths)
                ),
                "lower_level_pointer_data_hash": array_data_hash(
                    host_ilut_hip_fixture.lower_level_pointer
                ),
                "lower_level_rows_data_hash": array_data_hash(
                    host_ilut_hip_fixture.lower_level_rows
                ),
                "upper_level_pointer_data_hash": array_data_hash(
                    host_ilut_hip_fixture.upper_level_pointer
                ),
                "upper_level_rows_data_hash": array_data_hash(
                    host_ilut_hip_fixture.upper_level_rows
                ),
                "schedule_contract_hash": (
                    host_ilut_hip_fixture.schedule_contract_hash
                ),
                "expected_kernel_invocation_count": (
                    host_ilut_hip_fixture.expected_kernel_invocation_count
                ),
                "schedule_array_total_byte_length": (
                    host_ilut_hip_schedule_total_byte_length
                ),
                "declared_fixture_binary_byte_length": (
                    host_ilut_hip_declared_fixture_binary_byte_length
                ),
                "schedule_constructed": (host_ilut_hip_schedule_contract_pass),
                "fixture_binary_materialized": True,
                "fixture_binary_ephemeral": True,
                "fixture_binary_sha256": (host_ilut_hip_fixture_payload_hash),
                "fixture_binary_readback_sha256": (host_ilut_hip_fixture_readback_hash),
                "fixture_binary_roundtrip_pass": (host_ilut_hip_fixture_roundtrip_pass),
                "fixture_binary_persisted": False,
                "device_execution": False,
            },
            "actual_hardware_execution": False,
            "numerical_parity": False,
            "actual_mgt_factor_apply": False,
            "production_scale_factor_apply": False,
            "production_current_tangent_fgmres": False,
            "performance": False,
        },
        "comparison": {
            "same_operator_binding": same_operator_binding,
            "operator_binding_rechecked_before_and_after": (same_operator_binding),
            "same_state_and_right_hand_side": (state_and_right_hand_side_unchanged),
            "state_and_right_hand_side_hashes_unchanged": (
                state_and_right_hand_side_unchanged
            ),
            "same_host_recurrence_profile": True,
            "baseline_gate_passed": bool(baseline.contract_pass),
            "node_block_jacobi_gate_passed": bool(final_inf <= RESIDUAL_GATE_KN),
            "node_block_jacobi_iteration_budget_over_baseline": 40.0,
            "node_block_jacobi_final_residual_over_baseline": float(
                final_inf / baseline_receipt["explicit_residual_inf_kn"]
            ),
            "node_block_jacobi_is_insufficient_at_120_iterations": True,
            "host_ilut_gate_passed": host_ilut_diagnostic_effectiveness_pass,
            "host_ilut_iterations_over_baseline": float(
                host_ilut_candidate["iteration_count"]
                / baseline_receipt["iteration_count"]
            ),
            "host_ilut_final_residual_over_baseline": float(
                host_ilut_final_inf / baseline_receipt["explicit_residual_inf_kn"]
            ),
            "effective_host_factorized_candidate_identified": (
                host_ilut_diagnostic_effectiveness_pass
            ),
            "canonical_factor_contract_and_ordered_cpu_apply_implemented": (
                host_ilut_factor_contract_pass
            ),
            "canonical_factor_current_tangent_solver_api_integrated": (
                host_ilut_state_tangent_solver_integration_pass
            ),
            "persisted_factor_artifact_and_hip_apply_required": True,
            "stronger_backend_neutral_preconditioner_required": True,
            "contract_pass": contract_pass,
        },
        "claims": {
            "actual_mgt_preconditioner_candidate_compared": contract_pass,
            "fixed_reference_splu_baseline_gate_passed": bool(baseline.contract_pass),
            "node_block_jacobi_portable_apply_topology_candidate": True,
            "node_block_jacobi_120_iteration_gate_passed": False,
            "node_block_jacobi_production_effectiveness": False,
            "deterministic_node_block_inverse_construction": False,
            "host_ilut_cpu_diagnostic_effectiveness": (
                host_ilut_diagnostic_effectiveness_pass
            ),
            "deterministic_host_ilut_factor_construction": False,
            "canonical_backend_neutral_ilut_factor_contract": (
                host_ilut_factor_contract_pass
            ),
            "serialized_backend_neutral_ilut_factor_artifact": (
                host_ilut_binary_roundtrip_pass
            ),
            "full_scale_ephemeral_ilut_factor_binary_roundtrip": (
                host_ilut_binary_roundtrip_pass
            ),
            "backend_neutral_ilut_triangular_apply": (host_ilut_factor_contract_pass),
            "actual_current_tangent_canonical_factor_cpu_integration": (
                host_ilut_state_tangent_solver_integration_pass
            ),
            "backend_neutral_current_tangent_operator_contract": (
                current_tangent_operator_contract_pass
            ),
            "actual_current_tangent_analytic_callback_parity_probes": (
                current_tangent_operator_parity_pass
            ),
            "operator_callback_formula_and_parent_arrays_in_contract": (
                current_tangent_operator_contract_pass
            ),
            "actual_mgt_current_tangent_hip_fixture_constructed": (
                actual_current_tangent_hip_fixture_contract_pass
            ),
            "actual_mgt_current_tangent_hip_fixture_ephemeral_roundtrip": (
                actual_current_tangent_hip_fixture_roundtrip_pass
            ),
            "hip_current_tangent_operator_dual_target_compile": (
                hip_current_tangent_compile_contract_pass
            ),
            "hip_current_tangent_fixture_parser_dual_target_execution": (
                hip_current_tangent_compile_contract_pass
            ),
            "actual_mgt_current_tangent_host_parser_execution": (
                actual_current_tangent_hip_host_parser_binding_pass
            ),
            "actual_mgt_current_tangent_hip_execution": (
                actual_current_tangent_hip_hardware_binding_pass
            ),
            "actual_mgt_current_tangent_cpu_hip_numerical_parity": (
                actual_current_tangent_hip_hardware_binding_pass
            ),
            "actual_mgt_hip_dependency_schedule_constructed": (
                host_ilut_hip_schedule_contract_pass
            ),
            "actual_mgt_hip_fixture_binary_ephemeral_roundtrip": (
                host_ilut_hip_fixture_roundtrip_pass
            ),
            "hip_triangular_fixture_parser_dual_target_execution": (
                hip_sparse_lu_compile_contract_pass
            ),
            "hip_triangular_factor_apply_dual_target_compile": (
                hip_sparse_lu_compile_contract_pass
            ),
            "cross_platform_end_to_end_determinism": False,
            "production_rocm_hip_preconditioner_parity": False,
            "production_matrix_free_krylov": False,
            "performance": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "node_block_jacobi_effectiveness_gate_failed",
            "deterministic_node_block_inverse_construction_not_implemented",
            "host_ilut_factor_construction_is_scipy_superlu_specific",
            "canonical_factor_release_artifact_not_persisted",
            "hip_triangular_factor_apply_not_executed",
            "production_rocm_hip_preconditioner_apply_not_executed",
            "production_matrix_free_krylov_not_established",
            "g1_full_building_closure_not_established",
        ],
        "artifacts": {
            "receipt": _label(repo_root, receipt_out),
            "schema": str(SCHEMA_PATH),
            "factor_contract_module": (
                "src/structural_analysis/solvers/nonlinear/canonical_sparse_lu.py"
            ),
            "factor_binary_artifact_schema": (
                "src/structural_analysis/schemas/"
                "canonical_sparse_lu_binary_artifacts_v1.schema.json"
            ),
            "hip_triangular_apply_source": (
                "implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp"
            ),
            "hip_triangular_apply_compile_receipt": str(HIP_SPARSE_LU_COMPILE_RECEIPT),
            "hip_current_tangent_operator_module": (
                "src/structural_analysis/engine_v2_backends/"
                "hip_current_tangent_operator.py"
            ),
            "hip_current_tangent_operator_source": (
                "implementation/phase1/hip_kernels/"
                "engine_v2_current_tangent_operator.hip.cpp"
            ),
            "hip_current_tangent_operator_compile_receipt": str(
                HIP_CURRENT_TANGENT_COMPILE_RECEIPT
            ),
            "hip_current_tangent_actual_mgt_host_parser_receipt": str(
                HIP_CURRENT_TANGENT_HOST_PARSER_RECEIPT
            ),
            "hip_current_tangent_actual_mgt_host_parser_builder": (
                "scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py"
            ),
            "hip_current_tangent_actual_mgt_host_parser_schema": (
                "src/structural_analysis/schemas/"
                "g1_mgt_hip_current_tangent_host_parser_receipt_v1.schema.json"
            ),
            "hip_current_tangent_actual_mgt_hardware_receipt": str(
                HIP_CURRENT_TANGENT_HARDWARE_RECEIPT
            ),
            "hip_current_tangent_actual_mgt_hardware_action": str(
                HIP_CURRENT_TANGENT_ACTION_ARTIFACT
            ),
            "hip_current_tangent_actual_mgt_hardware_runner": (
                "scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py"
            ),
            "hip_current_tangent_actual_mgt_hardware_schema": (
                "src/structural_analysis/schemas/"
                "g1_mgt_hip_current_tangent_hardware_parity_receipt_v1.schema.json"
            ),
        },
        "claim_boundary": (
            "This bounded actual-MGT audit compares the existing fixed "
            "reference SuperLU diagnostic, a free-global-node 6x6 block-"
            "Jacobi candidate, and a host SciPy/SuperLU ILUT factor under the "
            "same state, right-hand side, operator binding, and ordered host "
            "recurrence. The block-Jacobi apply "
            "topology is portable, but its current batched NumPy inverse "
            "construction is not a deterministic backend contract and its "
            "120-iteration residual misses the local gate. The host ILUT "
            "candidate passes the diagnostic residual gate. Its factor is "
            "copied into immutable canonical little-endian CSR/permutation "
            "arrays and applied by ordered Python-fsum triangular solves, so "
            "the factor/apply contract no longer calls SciPy after "
            "construction. All eight roughly model-scale factor arrays are "
            "also written as canonical little-endian binaries, hash-validated, "
            "reloaded, bound with their bundle hash to the matrix-free "
            "current-tangent solver API, and used for the diagnostic solve in "
            "an ephemeral full-scale roundtrip. Factor construction remains "
            "SciPy/SuperLU-"
            "specific, no release factor artifact is retained, and the HIP "
            "triangular apply has warning-free gfx1030/gfx1100 target compile "
            "evidence. Its dependency-level schedule is constructed and "
            "hash-bound for the actual 70,560-equation factor without "
            "retaining a release artifact. The complete roughly 205 MB HIP "
            "fixture is materialized ephemerally and its streaming readback "
            "hash is verified. Both target binaries also execute the small "
            "host-only parser path with zero HIP runtime calls, but no device "
            "triangular-factor apply has occurred. The backend-neutral "
            "current-tangent "
            "parents, normalized current right-hand-side direction, and "
            "deterministic free-row incidence schedules are also serialized "
            "into a roughly 36 MB actual-MGT HIP fixture, hash-validated by "
            "an ephemeral file roundtrip, and not retained. The same "
            "byte-identical gfx1030/gfx1100 binaries recorded by the "
            "five-equation compile receipt also parse this full actual-MGT "
            "fixture through their host-only path with zero HIP runtime API "
            "calls. A local Radeon RX 6900 XT gfx1030 run additionally "
            "executes this fixture in one kernel with zero mid-action D2H "
            "transfers. Its persisted little-endian action is bitwise equal "
            "to the device-order CPU reference and within the canonical CPU "
            "tolerance. This remains one state, direction, and local device "
            "receipt. The audit therefore "
            "identifies an effectiveness and portable-contract frontier without "
            "establishing device-resident FGMRES/preconditioning, independent "
            "gfx1100 parity, performance, or G1 closure."
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
        return False, "g1_mgt_preconditioner_candidate_audit_missing"
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
            f"g1_mgt_preconditioner_candidate_audit_unreadable:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_mgt_preconditioner_candidate_audit_mismatch"
    return True, "g1_mgt_preconditioner_candidate_audit_consistent"


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
    block_candidate = payload["node_block_jacobi_candidate"]
    host_ilut_candidate = payload["host_ilut_candidate"]
    print(
        f"{payload['status']} | block_jacobi_iterations="
        f"{block_candidate['iteration_count']} | block_jacobi_residual_kn="
        f"{block_candidate['final_explicit_residual_inf_kn']:.12g} | "
        f"host_ilut_iterations={host_ilut_candidate['iteration_count']} | "
        f"host_ilut_residual_kn="
        f"{host_ilut_candidate['final_explicit_residual_inf_kn']:.12g} | "
        "production=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
