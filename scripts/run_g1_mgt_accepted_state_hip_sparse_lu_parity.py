#!/usr/bin/env python3
"""Run or validate full-load accepted-state MGT HIP sparse-LU parity."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

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
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)
from run_engine_v2_hip_sparse_lu_apply import (  # noqa: E402
    SOURCE_PATH as HIP_SOURCE_PATH,
    _detect_architecture,
    _resolve_device_lib_path,
    _resolve_hipcc,
    _run,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import (  # noqa: E402
    HIPSparseLUApplyReference,
    _device_order_apply,
    compare_hip_sparse_lu_apply_output,
    create_hip_sparse_lu_apply_fixture,
)
from structural_analysis.solvers.nonlinear.canonical_sparse_lu import (  # noqa: E402
    create_canonical_sparse_lu_factor,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
)
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION / "g1_mgt_state_updated_frame_axial_full_load_checkpoint.npz"
)
DEFAULT_OUT = (
    PRODUCTIZATION / "g1_mgt_accepted_state_hip_sparse_lu_parity_receipt.json"
)
DEFAULT_SOLUTION_OUT = (
    PRODUCTIZATION / "g1_mgt_accepted_state_hip_sparse_lu_solution.f64le"
)
WHEEL = Path("dist/structural_analysis-0.3.0-py3-none-any.whl")
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_accepted_state_hip_sparse_lu_parity_v1.schema.json"
)
SCHEMA_VERSION = "g1-mgt-accepted-state-hip-sparse-lu-parity-receipt.v1"
CASE_ID = "g1_actual_mgt_full_load_accepted_state_hip_sparse_lu_parity"
CONTRACT_SCOPE = "actual_mgt_full_load_accepted_state_local_gfx1030_sparse_lu_apply"
EQUATION_COUNT = 70_560
LOAD_FACTOR = 1.0
DROP_TOLERANCE = 1.0e-6
FILL_FACTOR = 20.0
COLUMN_PERMUTATION = "COLAMD"
SOLUTION_FORMAT = "canonical_little_endian_float64_vector.v1"
SOLUTION_DTYPE = "<f8"
SOLUTION_BYTE_LENGTH = EQUATION_COUNT * 8
SOURCE_PATHS = (
    DEFAULT_MGT,
    DEFAULT_CHECKPOINT,
    WHEEL,
    HIP_SOURCE_PATH,
    Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
    Path("src/structural_analysis/engine_v2_backends/hip_sparse_lu_apply.py"),
    Path("src/structural_analysis/solvers/nonlinear/canonical_sparse_lu.py"),
    Path("scripts/run_engine_v2_hip_sparse_lu_apply.py"),
    Path("scripts/run_g1_mgt_accepted_state_hip_sparse_lu_parity.py"),
    SCHEMA_PATH,
    Path("tests/test_run_g1_mgt_accepted_state_hip_sparse_lu_parity.py"),
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(repo_root: Path, path: Path) -> str:
    return _resolve(repo_root, path).resolve().relative_to(repo_root.resolve()).as_posix()


def _receipt_hash(payload: dict[str, Any]) -> str:
    return canonical_hash({key: value for key, value in payload.items() if key != "receipt_hash"})


def _source_paths_clean(repo_root: Path) -> bool:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *(_repo_relative(repo_root, path) for path in SOURCE_PATHS),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


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
        source_operator_numeric_values_hash=source_operator_numeric_values_hash,
    )


def _operator_hashes(reference_csr: Any) -> tuple[str, str]:
    reference_csr.sort_indices()
    return (
        canonical_hash(
            {
                "shape": [int(value) for value in reference_csr.shape],
                "row_pointer_data_hash": array_data_hash(
                    np.asarray(reference_csr.indptr, dtype="<i8")
                ),
                "column_index_data_hash": array_data_hash(
                    np.asarray(reference_csr.indices, dtype="<i8")
                ),
            }
        ),
        array_data_hash(np.asarray(reference_csr.data, dtype="<f8")),
    )


def build_actual_reference(
    *,
    repo_root: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
) -> tuple[HIPSparseLUApplyReference, dict[str, Any], dict[str, float]]:
    started = time.perf_counter()
    problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=_resolve(repo_root, mgt_path),
        roundtrip_npz=None,
        checkpoint_npz=_resolve(repo_root, checkpoint_npz),
        apply_state_updated_frame_axial_geometry=True,
        source_commit_sha=git_head(repo_root),
    )
    problem_seconds = time.perf_counter() - started
    state = np.ascontiguousarray(problem.initial_free_displacements_m(), dtype="<f8")
    load_factor = problem.initial_load_factor()
    if state.shape != (EQUATION_COUNT,) or load_factor != LOAD_FACTOR:
        raise RuntimeError("g1_mgt_accepted_state_checkpoint_contract_invalid")
    with np.load(_resolve(repo_root, checkpoint_npz), allow_pickle=False) as checkpoint:
        checkpoint_state = np.asarray(checkpoint["free_displacements_m"], dtype="<f8")
        checkpoint_free_dofs = np.asarray(checkpoint["free_global_dofs"], dtype="<i8")
        accepted_state_hash = str(np.asarray(checkpoint["accepted_state_hash"]).item())
        checkpoint_residual_inf_n = float(np.asarray(checkpoint["residual_inf_n"]).item())
    if not np.array_equal(state, checkpoint_state):
        raise RuntimeError("g1_mgt_accepted_state_vector_mismatch")
    if not np.array_equal(problem.free_equation_global_dofs, checkpoint_free_dofs):
        raise RuntimeError("g1_mgt_free_equation_order_mismatch")
    residual_kn = np.ascontiguousarray(problem.residual_kn(state, load_factor), dtype="<f8")
    right_hand_side_kn = np.ascontiguousarray(-residual_kn, dtype="<f8")
    residual_inf_kn = float(np.linalg.norm(residual_kn, ord=np.inf))
    if not np.isfinite(residual_inf_kn) or residual_inf_kn <= 0.0:
        raise RuntimeError("g1_mgt_accepted_state_residual_invalid")
    if not np.isclose(residual_inf_kn * 1000.0, checkpoint_residual_inf_n, rtol=1.0e-7, atol=1.0e-12):
        raise RuntimeError("g1_mgt_accepted_state_residual_checkpoint_mismatch")
    reference_csr = problem.reference_preconditioner_free_csr_n_per_m()
    pattern_hash, values_hash = _operator_hashes(reference_csr)
    factor_started = time.perf_counter()
    superlu = spilu(
        reference_csr.tocsc(),
        drop_tol=DROP_TOLERANCE,
        fill_factor=FILL_FACTOR,
        permc_spec=COLUMN_PERMUTATION,
    )
    factor_seconds = time.perf_counter() - factor_started
    factor = _canonical_factor_from_superlu(
        superlu,
        source_operator_pattern_hash=pattern_hash,
        source_operator_numeric_values_hash=values_hash,
    )
    fixture_started = time.perf_counter()
    fixture = create_hip_sparse_lu_apply_fixture(
        factor,
        right_hand_side_kn=right_hand_side_kn,
    )
    fixture_seconds = time.perf_counter() - fixture_started
    canonical_started = time.perf_counter()
    canonical_solution = immutable_array(factor.solve_kn_to_m(right_hand_side_kn), dtype="<f8")
    canonical_seconds = time.perf_counter() - canonical_started
    device_order_started = time.perf_counter()
    device_order_solution = immutable_array(_device_order_apply(fixture), dtype="<f8")
    device_order_seconds = time.perf_counter() - device_order_started
    reference = HIPSparseLUApplyReference(
        fixture=fixture,
        canonical_solution_m=canonical_solution,
        device_order_solution_m=device_order_solution,
    )
    context = {
        "adapter_metadata": metadata,
        "accepted_state_hash": accepted_state_hash,
        "state_data_hash": array_data_hash(state),
        "free_equation_order_data_hash": array_data_hash(checkpoint_free_dofs),
        "physical_residual_data_hash": array_data_hash(residual_kn),
        "right_hand_side_data_hash": array_data_hash(right_hand_side_kn),
        "physical_residual_inf_kn": residual_inf_kn,
        "checkpoint_residual_inf_n": checkpoint_residual_inf_n,
        "reference_operator_pattern_hash": pattern_hash,
        "reference_operator_numeric_values_hash": values_hash,
    }
    timings = {
        "problem_build_seconds": problem_seconds,
        "host_factorization_seconds": factor_seconds,
        "fixture_schedule_seconds": fixture_seconds,
        "canonical_cpu_apply_seconds": canonical_seconds,
        "device_order_cpu_apply_seconds": device_order_seconds,
    }
    return reference, context, timings


def _compile_and_execute(
    reference: HIPSparseLUApplyReference,
    *,
    repo_root: Path,
    hipcc: str,
    rocminfo: str,
    rocm_path: str,
    device_lib_path: str,
    runtime_timeout: float,
) -> dict[str, Any]:
    compiler = _resolve_hipcc(hipcc)
    device_libs = _resolve_device_lib_path(repo_root, device_lib_path)
    architecture = _detect_architecture(repo_root, rocminfo)
    if architecture != "gfx1030":
        raise RuntimeError("g1_mgt_sparse_lu_local_architecture_not_gfx1030")
    version = _run([str(compiler), "--version"], cwd=repo_root, timeout=30.0)
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError("g1_mgt_sparse_lu_hipcc_version_failed")
    with tempfile.TemporaryDirectory(prefix="g1-mgt-accepted-sparse-lu-") as raw:
        temporary = Path(raw)
        fixture_path = temporary / "actual_mgt_sparse_lu_fixture.bin"
        binary_path = temporary / "engine_v2_sparse_lu_apply"
        fixture_path.write_bytes(reference.fixture.to_bytes())
        command = [
            str(compiler),
            f"--rocm-path={rocm_path}",
            f"--rocm-device-lib-path={device_libs}",
            f"--offload-arch={architecture}",
            str(repo_root / HIP_SOURCE_PATH),
            "-O2",
            "-Werror",
            "-ffp-contract=off",
            "-std=c++17",
            "-o",
            str(binary_path),
        ]
        compiled = _run(command, cwd=repo_root, timeout=180.0)
        if compiled.returncode != 0:
            raise RuntimeError("g1_mgt_sparse_lu_compile_failed:" + compiled.stderr[-1000:].replace("\n", " "))
        binary_sha256 = file_sha256(binary_path)
        binary_byte_length = binary_path.stat().st_size
        execution_started = time.perf_counter()
        executed = _run(
            [str(binary_path), str(fixture_path)],
            cwd=repo_root,
            timeout=runtime_timeout,
        )
        process_wall_time_ms = (time.perf_counter() - execution_started) * 1000.0
        if executed.returncode != 0:
            raise RuntimeError("g1_mgt_sparse_lu_execution_failed:" + executed.stderr[-1000:].replace("\n", " "))
        try:
            runtime_output = json.loads(executed.stdout.strip().splitlines()[-1])
        except Exception as exc:
            raise RuntimeError("g1_mgt_sparse_lu_runtime_output_invalid") from exc
    return {
        "architecture": architecture,
        "compiler": {
            "path": str(compiler),
            "version_first_line": version.stdout.splitlines()[0],
            "version_output_sha256": sha256_prefixed(version.stdout.encode("utf-8")),
        },
        "compile_command": command[:-2] + ["<temporary-binary>"],
        "binary_sha256": binary_sha256,
        "binary_byte_length": binary_byte_length,
        "fixture_file_sha256": reference.fixture.fixture_hash,
        "fixture_file_byte_length": len(reference.fixture.to_bytes()),
        "process_wall_time_ms": process_wall_time_ms,
        "runtime_output": runtime_output,
    }


def _device_telemetry(reference: HIPSparseLUApplyReference) -> dict[str, int]:
    fixture = reference.fixture
    factor = fixture.factor
    uploaded = (
        factor.lower_row_pointer.nbytes
        + factor.lower_column_indices.nbytes
        + factor.lower_numeric_values.nbytes
        + factor.upper_row_pointer.nbytes
        + factor.upper_column_indices.nbytes
        + factor.upper_numeric_values.nbytes
        + factor.row_permutation.nbytes
        + factor.column_permutation.nbytes
        + fixture.lower_level_rows.nbytes
        + fixture.upper_level_rows.nbytes
        + fixture.right_hand_side_kn.nbytes
    )
    vector_bytes = fixture.dimension * 8
    return {
        "h2d_bytes": int(uploaded),
        "d2h_bytes": int(vector_bytes),
        "mid_apply_d2h_bytes": 0,
        "tracked_peak_device_allocation_bytes": int(uploaded + 4 * vector_bytes),
    }


def _solution_artifact(
    *,
    repo_root: Path,
    solution_out: Path,
    solution: np.ndarray,
) -> tuple[dict[str, Any], bytes]:
    vector = immutable_array(solution, dtype=SOLUTION_DTYPE)
    if vector.shape != (EQUATION_COUNT,):
        raise ValueError("g1_mgt_sparse_lu_solution_shape_invalid")
    raw = vector.tobytes(order="C")
    if len(raw) != SOLUTION_BYTE_LENGTH:
        raise ValueError("g1_mgt_sparse_lu_solution_size_invalid")
    digest = sha256_prefixed(raw)
    return (
        {
            "path": _repo_relative(repo_root, solution_out),
            "format": SOLUTION_FORMAT,
            "dtype": SOLUTION_DTYPE,
            "shape": [EQUATION_COUNT],
            "byte_length": len(raw),
            "file_sha256": digest,
            "data_hash": array_data_hash(vector),
            "persisted": True,
        },
        raw,
    )


def build_receipt_from_execution(
    *,
    repo_root: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
    out_path: Path,
    solution_out: Path,
    reference: HIPSparseLUApplyReference,
    context: dict[str, Any],
    timings: dict[str, float],
    execution: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    runtime_output = execution["runtime_output"]
    comparison = compare_hip_sparse_lu_apply_output(reference, runtime_output)
    if comparison["contract_pass"] is not True:
        raise RuntimeError("g1_mgt_sparse_lu_cpu_hip_parity_failed")
    solution = immutable_array(runtime_output["solution_m"], dtype=SOLUTION_DTYPE)
    solution_manifest, solution_bytes = _solution_artifact(
        repo_root=repo_root,
        solution_out=solution_out,
        solution=solution,
    )
    runtime_metadata = dict(runtime_output)
    runtime_metadata.pop("solution_m")
    fixture_manifest = reference.fixture.to_manifest()
    factor_manifest = reference.fixture.factor.manifest()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "contract_scope": CONTRACT_SCOPE,
        "source": {
            "repository_commit_sha": git_head(repo_root),
            "source_paths_clean_at_execution": _source_paths_clean(repo_root),
            "input_checksums": input_checksums(SOURCE_PATHS, repo_root=repo_root),
            "engine_version": engine_version(repo_root),
        },
        "runtime": {
            "backend": "amd_rocm_hip",
            "device_name": runtime_output["device_name"],
            "gcn_arch_name": runtime_output["gcn_arch_name"],
            "device_nodes": ["/dev/kfd", "/dev/dri/renderD128"],
            "compiler": execution["compiler"],
            "binary_sha256": execution["binary_sha256"],
            "binary_byte_length": execution["binary_byte_length"],
            "wheel": {
                "path": WHEEL.as_posix(),
                "sha256": file_sha256(repo_root / WHEEL),
                "bound_at_execution": True,
            },
        },
        "accepted_state": {
            "mgt_path": _repo_relative(repo_root, mgt_path),
            "mgt_sha256": file_sha256(_resolve(repo_root, mgt_path)),
            "checkpoint_npz": _repo_relative(repo_root, checkpoint_npz),
            "checkpoint_sha256": file_sha256(_resolve(repo_root, checkpoint_npz)),
            "load_factor": LOAD_FACTOR,
            "equation_count": EQUATION_COUNT,
            "state_policy": "full_load_checkpoint_accepted_free_displacements",
            "accepted_state_hash": context["accepted_state_hash"],
            "state_data_hash": context["state_data_hash"],
            "free_equation_order_data_hash": context["free_equation_order_data_hash"],
            "physical_residual_data_hash": context["physical_residual_data_hash"],
            "right_hand_side_policy": "negative_physical_residual_at_accepted_state",
            "right_hand_side_data_hash": context["right_hand_side_data_hash"],
            "physical_residual_inf_kn": context["physical_residual_inf_kn"],
            "checkpoint_residual_inf_n": context["checkpoint_residual_inf_n"],
        },
        "preconditioner": {
            "profile": "fixed_reference_host_spilu_canonical_sparse_lu.v1",
            "factorization_backend": "scipy.sparse.linalg.spilu_superlu",
            "scipy_version": scipy.__version__,
            "drop_tolerance": DROP_TOLERANCE,
            "fill_factor": FILL_FACTOR,
            "column_permutation": COLUMN_PERMUTATION,
            "reference_operator_pattern_hash": context["reference_operator_pattern_hash"],
            "reference_operator_numeric_values_hash": context["reference_operator_numeric_values_hash"],
            "factor_manifest": factor_manifest,
            "fixture_manifest": fixture_manifest,
            "factor_persisted": False,
            "fixture_persisted": False,
        },
        "hardware_execution": {
            "actual_hardware": True,
            "runtime_metadata": runtime_metadata,
            "runtime_output_hash": canonical_hash(runtime_output),
            "fixture_file_sha256": execution["fixture_file_sha256"],
            "fixture_file_byte_length": execution["fixture_file_byte_length"],
            "process_wall_time_ms": execution["process_wall_time_ms"],
            "telemetry": _device_telemetry(reference),
            "solution_artifact": solution_manifest,
        },
        "host_timings": timings,
        "comparison": comparison,
        "claims": {
            "actual_mgt_full_load_accepted_state": True,
            "actual_mgt_70560_factor_apply": True,
            "production_scale_level_schedule": True,
            "actual_gfx1030_hardware": True,
            "mid_apply_d2h_zero": runtime_metadata["mid_apply_d2h_transfer_count"] == 0,
            "cpu_hip_numerical_parity": True,
            "production_current_tangent_fgmres": False,
            "persistent_factor_across_krylov_iterations": False,
            "independent_gfx1100": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "current_tangent_operator_and_preconditioner_not_integrated_in_one_device_fgmres",
            "factor_not_persisted_across_krylov_iterations",
            "factorization_is_host_scipy_superlu_specific",
            "independent_gfx1100_run_not_available",
            "same_clean_source_cross_device_receipt_not_available",
            "g1_full_building_device_newton_closure_not_established",
        ],
        "artifacts": {
            "receipt": _repo_relative(repo_root, out_path),
            "solution_vector": _repo_relative(repo_root, solution_out),
            "schema": SCHEMA_PATH.as_posix(),
            "runner": "scripts/run_g1_mgt_accepted_state_hip_sparse_lu_parity.py",
            "hip_source": HIP_SOURCE_PATH.as_posix(),
        },
        "claim_boundary": (
            "This receipt proves one actual 70,560-equation canonical sparse-LU "
            "preconditioner apply on the local AMD Radeon RX 6900 XT gfx1030. "
            "Its RHS is the negative physical residual evaluated at the accepted "
            "load-scale 1.0 MGT checkpoint, and the full production-size dependency "
            "schedule executes without an intermediate device-to-host transfer. "
            "It does not claim that the factor is retained across Krylov iterations, "
            "that current-tangent JVP and preconditioning execute inside one device "
            "FGMRES lifecycle, that host SciPy/SuperLU factor construction is a "
            "production factorization backend, that gfx1100 was executed, or that G1 "
            "is closed."
        ),
    }
    if payload["source"]["source_paths_clean_at_execution"] is not True:
        raise RuntimeError("g1_mgt_sparse_lu_requires_clean_source_paths")
    payload["receipt_hash"] = _receipt_hash(payload)
    validate_receipt(payload, repo_root=repo_root, require_current_sources=True)
    return payload, solution_bytes


def _read_solution_artifact(payload: dict[str, Any], *, repo_root: Path) -> np.ndarray:
    artifact = payload["hardware_execution"]["solution_artifact"]
    path = _resolve(repo_root, Path(artifact["path"]))
    raw = path.read_bytes()
    if len(raw) != artifact["byte_length"] or file_sha256(path) != artifact["file_sha256"]:
        raise ValueError("g1_mgt_sparse_lu_solution_artifact_mismatch")
    solution = immutable_array(np.frombuffer(raw, dtype=np.dtype(SOLUTION_DTYPE)), dtype=SOLUTION_DTYPE)
    if array_data_hash(solution) != artifact["data_hash"]:
        raise ValueError("g1_mgt_sparse_lu_solution_data_hash_mismatch")
    return solution


def validate_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool = False,
    require_solution_artifact: bool = False,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("g1_mgt_sparse_lu_receipt_hash_mismatch")
    if require_current_sources:
        expected = input_checksums(SOURCE_PATHS, repo_root=repo_root)
        if payload["source"]["input_checksums"] != expected:
            raise ValueError("g1_mgt_sparse_lu_source_checksums_stale")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", payload["source"]["repository_commit_sha"], "HEAD"],
            cwd=repo_root,
        ).returncode == 0
        if not ancestor:
            raise ValueError("g1_mgt_sparse_lu_source_commit_not_ancestor")
    if require_solution_artifact:
        solution = _read_solution_artifact(payload, repo_root=repo_root)
        if array_data_hash(solution) != payload["comparison"]["solution_data_hash"]:
            raise ValueError("g1_mgt_sparse_lu_solution_comparison_hash_mismatch")
    return payload


def run_hardware_parity(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    out_path: Path = DEFAULT_OUT,
    solution_out: Path = DEFAULT_SOLUTION_OUT,
    hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
    rocminfo: str = "rocminfo",
    rocm_path: str = "/opt/rocm-6.0.2",
    device_lib_path: str = "",
    runtime_timeout: float = 300.0,
) -> tuple[dict[str, Any], bytes]:
    repo_root = repo_root.resolve()
    for required in (Path("/dev/kfd"), Path("/dev/dri/renderD128"), repo_root / WHEEL):
        if not required.exists():
            raise RuntimeError(f"g1_mgt_sparse_lu_runtime_prerequisite_missing:{required}")
    if not _source_paths_clean(repo_root):
        raise RuntimeError("g1_mgt_sparse_lu_requires_clean_source_paths")
    reference, context, timings = build_actual_reference(
        repo_root=repo_root,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    execution = _compile_and_execute(
        reference,
        repo_root=repo_root,
        hipcc=hipcc,
        rocminfo=rocminfo,
        rocm_path=rocm_path,
        device_lib_path=device_lib_path,
        runtime_timeout=runtime_timeout,
    )
    return build_receipt_from_execution(
        repo_root=repo_root,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        out_path=out_path,
        solution_out=solution_out,
        reference=reference,
        context=context,
        timings=timings,
        execution=execution,
    )


def write_receipt(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    out_path = Path(kwargs.get("out_path", DEFAULT_OUT))
    solution_out = Path(kwargs.get("solution_out", DEFAULT_SOLUTION_OUT))
    payload, solution_bytes = run_hardware_parity(**kwargs)
    solution_target = _resolve(repo_root, solution_out)
    receipt_target = _resolve(repo_root, out_path)
    solution_target.parent.mkdir(parents=True, exist_ok=True)
    receipt_target.parent.mkdir(parents=True, exist_ok=True)
    solution_target.write_bytes(solution_bytes)
    receipt_target.write_text(_json_text(payload), encoding="utf-8")
    return validate_receipt(
        _read_json(receipt_target),
        repo_root=repo_root,
        require_current_sources=True,
        require_solution_artifact=True,
    )


def check_receipt(*, repo_root: Path = ROOT, out_path: Path = DEFAULT_OUT) -> tuple[bool, str]:
    target = _resolve(repo_root, out_path)
    if not target.is_file():
        return False, "g1_mgt_accepted_state_hip_sparse_lu_receipt_missing"
    try:
        validate_receipt(
            _read_json(target),
            repo_root=repo_root,
            require_current_sources=True,
            require_solution_artifact=True,
        )
    except Exception as exc:
        return False, f"g1_mgt_accepted_state_hip_sparse_lu_receipt_invalid:{exc}"
    return True, "g1_mgt_accepted_state_hip_sparse_lu_receipt_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--solution-out", type=Path, default=DEFAULT_SOLUTION_OUT)
    parser.add_argument("--hipcc", default="/opt/rocm-6.0.2/bin/hipcc")
    parser.add_argument("--rocminfo", default="rocminfo")
    parser.add_argument("--rocm-path", default="/opt/rocm-6.0.2")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--runtime-timeout", type=float, default=300.0)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        passed, reason = check_receipt(repo_root=args.repo_root, out_path=args.out)
        print(reason)
        return 0 if passed else 1
    payload = write_receipt(
        repo_root=args.repo_root,
        mgt_path=args.mgt,
        checkpoint_npz=args.checkpoint,
        out_path=args.out,
        solution_out=args.solution_out,
        hipcc=args.hipcc,
        rocminfo=args.rocminfo,
        rocm_path=args.rocm_path,
        device_lib_path=args.device_lib_path,
        runtime_timeout=args.runtime_timeout,
    )
    print(
        "partial | actual_mgt_accepted_state=true | equations=70560 | "
        f"arch={payload['runtime']['gcn_arch_name']} | "
        f"kernel_invocations={payload['hardware_execution']['runtime_metadata']['kernel_invocation_count']} | "
        f"canonical_error_m={payload['comparison']['canonical_cpu_max_abs_error_m']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
