#!/usr/bin/env python3
"""Run actual-MGT sparse-LU and accepted-state JVP in one HIP lifecycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np
from scipy.sparse.linalg import spilu


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PHASE1 = ROOT / "implementation" / "phase1"
for candidate in (SCRIPT_DIR, SRC, PHASE1):
    value = str(candidate)
    while value in sys.path:
        sys.path.remove(value)
    sys.path.insert(0, value)

from g1_mgt_load_coupled_arc_length_adapter import build_real_mgt_load_coupled_arc_length_problem  # noqa: E402
from release_evidence_metadata import engine_version, file_sha256, git_head, input_checksums  # noqa: E402
from run_engine_v2_hip_sparse_lu_apply import _detect_architecture, _resolve_device_lib_path, _resolve_hipcc, _run  # noqa: E402
from run_g1_mgt_accepted_state_hip_sparse_lu_parity import (  # noqa: E402
    DEFAULT_CHECKPOINT, DEFAULT_MGT, DEFAULT_OUT as PRECONDITIONER_RECEIPT,
    DEFAULT_SOLUTION_OUT as PRECONDITIONER_SOLUTION, FILL_FACTOR, DROP_TOLERANCE,
    COLUMN_PERMUTATION, WHEEL, _canonical_factor_from_superlu, _operator_hashes,
    validate_receipt as validate_preconditioner_receipt,
)
from structural_analysis.engine_v2.contracts._canonical import array_data_hash, canonical_hash, immutable_array, sha256_prefixed  # noqa: E402
from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import HIPSparseLUApplyReference, _device_order_apply, create_hip_sparse_lu_apply_fixture  # noqa: E402
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import create_hip_current_tangent_operator_fixture, create_hip_current_tangent_operator_reference  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SOURCE = Path("implementation/phase1/hip_kernels/engine_v2_mgt_preconditioned_jvp.hip.cpp")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_single_lifecycle_preconditioned_jvp_receipt.json"
DEFAULT_ACTION_OUT = PRODUCTIZATION / "g1_mgt_single_lifecycle_preconditioned_jvp_action.f64le"
SCHEMA = Path("src/structural_analysis/schemas/g1_mgt_single_lifecycle_preconditioned_jvp_v1.schema.json")
SCHEMA_VERSION = "g1-mgt-single-lifecycle-preconditioned-jvp-receipt.v1"
N = 70_560
VECTOR_BYTES = N * 8
SOURCE_PATHS = (
    DEFAULT_MGT, DEFAULT_CHECKPOINT, PRECONDITIONER_RECEIPT, PRECONDITIONER_SOLUTION, WHEEL,
    SOURCE,
    Path("implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp"),
    Path("implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp"),
    Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
    Path("src/structural_analysis/engine_v2_backends/hip_sparse_lu_apply.py"),
    Path("src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py"),
    Path("scripts/run_g1_mgt_accepted_state_hip_sparse_lu_parity.py"),
    Path("scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py"),
    SCHEMA,
    Path("tests/test_run_g1_mgt_single_lifecycle_preconditioned_jvp.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative(root: Path, path: Path) -> str:
    return _resolve(root, path).resolve().relative_to(root.resolve()).as_posix()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("receipt_must_be_object")
    return value


def _receipt_hash(payload: dict[str, Any]) -> str:
    return canonical_hash({key: value for key, value in payload.items() if key != "receipt_hash"})


def _clean(root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *(_relative(root, p) for p in SOURCE_PATHS)],
        cwd=root, check=True, capture_output=True, text=True,
    )
    return not result.stdout.strip()


def _prior_direction(root: Path, receipt: dict[str, Any]) -> np.ndarray:
    item = receipt["hardware_execution"]["solution_artifact"]
    path = _resolve(root, Path(item["path"])); raw = path.read_bytes()
    if len(raw) != VECTOR_BYTES or file_sha256(path) != item["file_sha256"]:
        raise ValueError("prior_preconditioner_artifact_invalid")
    return immutable_array(np.frombuffer(raw, dtype="<f8"), dtype="<f8")


def build_references(*, root: Path) -> tuple[Any, HIPSparseLUApplyReference, Any, dict[str, Any]]:
    prior = validate_preconditioner_receipt(
        _read(root / PRECONDITIONER_RECEIPT), repo_root=root,
        require_current_sources=True, require_solution_artifact=True,
    )
    prior_direction = _prior_direction(root, prior)
    problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=root / DEFAULT_MGT, roundtrip_npz=None,
        checkpoint_npz=root / DEFAULT_CHECKPOINT,
        apply_state_updated_frame_axial_geometry=True, source_commit_sha=git_head(root),
    )
    state = np.ascontiguousarray(problem.initial_free_displacements_m(), dtype="<f8")
    if state.shape != (N,) or problem.initial_load_factor() != 1.0:
        raise RuntimeError("single_lifecycle_accepted_state_invalid")
    residual_kn = np.ascontiguousarray(problem.residual_kn(state, 1.0), dtype="<f8")
    rhs_kn = np.ascontiguousarray(-residual_kn, dtype="<f8")
    csr = problem.reference_preconditioner_free_csr_n_per_m()
    pattern_hash, values_hash = _operator_hashes(csr)
    factorization = spilu(
        csr.tocsc(), drop_tol=DROP_TOLERANCE, fill_factor=FILL_FACTOR,
        permc_spec=COLUMN_PERMUTATION,
    )
    factor = _canonical_factor_from_superlu(
        factorization, source_operator_pattern_hash=pattern_hash,
        source_operator_numeric_values_hash=values_hash,
    )
    sparse_fixture = create_hip_sparse_lu_apply_fixture(factor, right_hand_side_kn=rhs_kn)
    sparse_reference = HIPSparseLUApplyReference(
        fixture=sparse_fixture,
        canonical_solution_m=immutable_array(factor.solve_kn_to_m(rhs_kn), dtype="<f8"),
        device_order_solution_m=immutable_array(_device_order_apply(sparse_fixture), dtype="<f8"),
    )
    if not np.array_equal(sparse_reference.device_order_solution_m, prior_direction):
        raise RuntimeError("single_lifecycle_prior_preconditioner_identity_mismatch")
    operator = problem.current_tangent_operator
    if operator is None: raise RuntimeError("single_lifecycle_current_tangent_missing")
    tangent_fixture = create_hip_current_tangent_operator_fixture(
        operator, free_displacements_m=state, load_factor=1.0,
        free_direction_m=sparse_reference.device_order_solution_m,
    )
    tangent_reference = create_hip_current_tangent_operator_reference(tangent_fixture)
    return sparse_fixture, sparse_reference, tangent_reference, {
        "state": state, "residual_kn": residual_kn, "rhs_kn": rhs_kn,
        "metadata": metadata, "prior": prior, "pattern_hash": pattern_hash,
        "values_hash": values_hash,
    }


def _compile_execute(*, root: Path, sparse_fixture: Any, tangent_fixture: Any,
                     hipcc: str, rocm_path: str, device_lib_path: str,
                     timeout: float) -> dict[str, Any]:
    compiler = _resolve_hipcc(hipcc); libs = _resolve_device_lib_path(root, device_lib_path)
    architecture = _detect_architecture(root, "rocminfo")
    if architecture != "gfx1030": raise RuntimeError("single_lifecycle_requires_local_gfx1030")
    version = _run([str(compiler), "--version"], cwd=root, timeout=30)
    with tempfile.TemporaryDirectory(prefix="g1-mgt-single-lifecycle-") as raw:
        temp = Path(raw); sparse_path = temp / "sparse.bin"; tangent_path = temp / "tangent.bin"; binary = temp / "runner"
        sparse_path.write_bytes(sparse_fixture.to_bytes()); tangent_path.write_bytes(tangent_fixture.to_bytes())
        command = [str(compiler), f"--rocm-path={rocm_path}", f"--rocm-device-lib-path={libs}",
                   f"--offload-arch={architecture}", str(root / SOURCE), "-O2", "-Werror",
                   "-ffp-contract=off", "-std=c++17", "-o", str(binary)]
        compiled = _run(command, cwd=root, timeout=180)
        if compiled.returncode != 0: raise RuntimeError("single_lifecycle_compile_failed:" + compiled.stderr[-1200:].replace("\n", " "))
        binary_hash = file_sha256(binary); binary_size = binary.stat().st_size
        executed = _run([str(binary), str(sparse_path), str(tangent_path)], cwd=root, timeout=timeout)
        if executed.returncode != 0: raise RuntimeError("single_lifecycle_execution_failed:" + executed.stderr[-1200:].replace("\n", " "))
        runtime = json.loads(executed.stdout.strip().splitlines()[-1])
    return {
        "runtime": runtime, "binary_sha256": binary_hash, "binary_byte_length": binary_size,
        "compiler": {"path": str(compiler), "version_first_line": version.stdout.splitlines()[0],
                     "version_output_sha256": sha256_prefixed(version.stdout.encode())},
    }


def compare(runtime: dict[str, Any], *, sparse_reference: HIPSparseLUApplyReference,
            tangent_reference: Any) -> dict[str, Any]:
    expected_fields = {
        "schema_version", "status", "cpu_backend", "device_name", "gcn_arch_name",
        "equation_count", "preconditioner_kernel_invocation_count",
        "current_tangent_kernel_invocation_count", "total_kernel_invocation_count",
        "preconditioner_apply_count", "matvec_count", "persistent_factor_buffers",
        "persistent_operator_buffers", "single_stream_composition",
        "mid_composition_d2h_transfer_count", "final_d2h_transfer_count", "h2d_bytes",
        "d2h_bytes", "tracked_peak_device_allocation_bytes",
        "device_lifecycle_wall_time_ms", "preconditioned_direction_m", "jvp_action_n",
    }
    if set(runtime) != expected_fields: raise ValueError("single_lifecycle_runtime_fields_invalid")
    direction = immutable_array(runtime["preconditioned_direction_m"], dtype="<f8")
    action = immutable_array(runtime["jvp_action_n"], dtype="<f8")
    canonical_direction_error = float(np.max(np.abs(direction - sparse_reference.canonical_solution_m)))
    device_direction_error = float(np.max(np.abs(direction - sparse_reference.device_order_solution_m)))
    canonical_action_error = float(np.max(np.abs(action - tangent_reference.canonical_action_n_per_m)))
    device_action_error = float(np.max(np.abs(action - tangent_reference.device_order_action_n_per_m)))
    direction_tol = 1.0e-11; action_tol = max(1.0e-6, float(np.max(np.abs(tangent_reference.canonical_action_n_per_m))) * 1.0e-11)
    contract = bool(
        runtime["schema_version"] == "engine-v2-mgt-preconditioned-jvp-output.v1"
        and runtime["status"] == "ok" and runtime["cpu_backend"] is False
        and runtime["gcn_arch_name"] == "gfx1030" and runtime["equation_count"] == N
        and runtime["persistent_factor_buffers"] is True and runtime["persistent_operator_buffers"] is True
        and runtime["single_stream_composition"] is True
        and runtime["mid_composition_d2h_transfer_count"] == 0
        and runtime["preconditioner_apply_count"] == 1 and runtime["matvec_count"] == 1
        and device_direction_error == 0.0 and device_action_error == 0.0
        and canonical_direction_error <= direction_tol and canonical_action_error <= action_tol
    )
    return {
        "contract_pass": contract,
        "preconditioned_direction_data_hash": array_data_hash(direction),
        "canonical_direction_max_abs_error_m": canonical_direction_error,
        "device_order_direction_max_abs_error_m": device_direction_error,
        "direction_tolerance_m": direction_tol,
        "jvp_action_data_hash": array_data_hash(action),
        "canonical_action_max_abs_error_n": canonical_action_error,
        "device_order_action_max_abs_error_n": device_action_error,
        "action_tolerance_n": action_tol,
    }


def _artifact(root: Path, path: Path, action: np.ndarray) -> tuple[dict[str, Any], bytes]:
    vector = immutable_array(action, dtype="<f8"); raw = vector.tobytes(); digest = sha256_prefixed(raw)
    return ({"path": _relative(root, path), "format": "canonical_little_endian_float64_vector.v1",
             "dtype": "<f8", "shape": [N], "byte_length": len(raw), "file_sha256": digest,
             "data_hash": array_data_hash(vector), "persisted": True}, raw)


def run(*, root: Path = ROOT, out: Path = DEFAULT_OUT, action_out: Path = DEFAULT_ACTION_OUT,
        hipcc: str = "/opt/rocm-6.0.2/bin/hipcc", rocm_path: str = "/opt/rocm-6.0.2",
        device_lib_path: str = "", timeout: float = 600) -> tuple[dict[str, Any], bytes]:
    root = root.resolve()
    if not _clean(root): raise RuntimeError("single_lifecycle_requires_clean_source_paths")
    sparse_fixture, sparse_reference, tangent_reference, context = build_references(root=root)
    execution = _compile_execute(root=root, sparse_fixture=sparse_fixture,
                                 tangent_fixture=tangent_reference.fixture, hipcc=hipcc,
                                 rocm_path=rocm_path, device_lib_path=device_lib_path, timeout=timeout)
    runtime = execution["runtime"]; comparison = compare(runtime, sparse_reference=sparse_reference, tangent_reference=tangent_reference)
    if comparison["contract_pass"] is not True: raise RuntimeError("single_lifecycle_cpu_hip_parity_failed")
    action_manifest, action_bytes = _artifact(root, action_out, np.asarray(runtime["jvp_action_n"], dtype="<f8"))
    metadata = dict(runtime); metadata.pop("preconditioned_direction_m"); metadata.pop("jvp_action_n")
    prior = context["prior"]
    payload = {
        "schema_version": SCHEMA_VERSION, "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "contract_pass": True,
        "contract_scope": "actual_mgt_full_load_single_device_lifecycle_preconditioned_jvp_local_gfx1030",
        "source": {"repository_commit_sha": git_head(root), "source_paths_clean_at_execution": _clean(root),
                   "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root), "engine_version": engine_version(root)},
        "runtime": {"backend": "amd_rocm_hip", "device_name": runtime["device_name"], "gcn_arch_name": runtime["gcn_arch_name"],
                    "device_nodes": ["/dev/kfd", "/dev/dri/renderD128"], "compiler": execution["compiler"],
                    "binary_sha256": execution["binary_sha256"], "binary_byte_length": execution["binary_byte_length"],
                    "wheel": {"path": WHEEL.as_posix(), "sha256": file_sha256(root / WHEEL), "bound_at_execution": True}},
        "accepted_state": {"checkpoint": DEFAULT_CHECKPOINT.as_posix(), "checkpoint_sha256": file_sha256(root / DEFAULT_CHECKPOINT),
                           "load_factor": 1.0, "equation_count": N, "state_data_hash": array_data_hash(context["state"]),
                           "physical_residual_inf_kn": float(np.linalg.norm(context["residual_kn"], ord=np.inf)),
                           "right_hand_side_data_hash": array_data_hash(context["rhs_kn"])},
        "fixtures": {"sparse_lu_fixture_hash": sparse_fixture.fixture_hash,
                     "sparse_lu_factor_contract_hash": sparse_fixture.factor.contract_hash,
                     "current_tangent_fixture_hash": tangent_reference.fixture.fixture_hash,
                     "current_tangent_operator_contract_hash": tangent_reference.fixture.operator.contract_hash,
                     "prior_sparse_lu_receipt_hash": prior["receipt_hash"]},
        "hardware_execution": {"actual_hardware": True, "runtime_metadata": metadata,
                               "runtime_output_hash": canonical_hash(runtime), "action_artifact": action_manifest},
        "comparison": comparison,
        "claims": {"actual_mgt_full_load_accepted_state": True, "actual_production_size_sparse_lu": True,
                   "actual_accepted_state_current_tangent_jvp": True, "single_device_lifecycle": True,
                   "persistent_factor_buffers": True, "persistent_operator_buffers": True,
                   "single_stream_preconditioner_then_jvp": True, "mid_composition_d2h_zero": True,
                   "cpu_hip_numerical_parity": True, "arnoldi_fgmres_recurrence": False,
                   "production_fgmres": False, "independent_gfx1100": False, "g1_closure": False},
        "blockers_remaining": ["arnoldi_recurrence_not_connected_to_composite_operator",
                               "multiple_krylov_preconditioner_and_matvec_iterations_not_executed",
                               "independent_gfx1100_run_not_available",
                               "full_device_newton_line_search_material_checkpoint_lifecycle_not_established"],
        "artifacts": {"receipt": _relative(root, out), "action_vector": _relative(root, action_out),
                      "schema": SCHEMA.as_posix(), "runner": "scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py",
                      "hip_source": SOURCE.as_posix()},
        "claim_boundary": (
            "This receipt proves one actual production-size right-preconditioned current-tangent operation for the 70,560-equation MGT model at the accepted load-scale 1.0 state. Canonical sparse-LU factor buffers and current-tangent operator/state buffers remain allocated in one HIP process, and one stream executes M^-1 r followed immediately by A(u_accepted)(M^-1 r) with zero device-to-host transfer between the operations. Only the two terminal vectors are copied after both operations complete, and both stages match their device-order CPU references bitwise. This is the required persistent composition primitive, but it is one preconditioner apply and one matvec only: Arnoldi orthogonalization, restarted FGMRES iterations, equation scaling, Newton update, line search, material commit/rollback, checkpoint/ResultIR emission, independent gfx1100 evidence, and G1 closure remain outside this receipt."
        ),
    }
    payload["receipt_hash"] = _receipt_hash(payload); validate(payload, root=root, current=True); return payload, action_bytes


def validate(payload: dict[str, Any], *, root: Path = ROOT, current: bool = False, artifact: bool = False) -> dict[str, Any]:
    schema = _read(root / SCHEMA); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload): raise ValueError("single_lifecycle_receipt_hash_mismatch")
    if current and payload["source"]["input_checksums"] != input_checksums(SOURCE_PATHS, repo_root=root): raise ValueError("single_lifecycle_sources_stale")
    if artifact:
        item = payload["hardware_execution"]["action_artifact"]; path = _resolve(root, Path(item["path"]))
        if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]: raise ValueError("single_lifecycle_artifact_invalid")
    return payload


def write(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs.get("root", ROOT)).resolve(); out = Path(kwargs.get("out", DEFAULT_OUT)); action = Path(kwargs.get("action_out", DEFAULT_ACTION_OUT))
    payload, raw = run(**kwargs); _resolve(root, action).write_bytes(raw); _resolve(root, out).write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return validate(payload, root=root, current=True, artifact=True)


def check(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> tuple[bool, str]:
    path = _resolve(root, out)
    if not path.is_file(): return False, "g1_mgt_single_lifecycle_preconditioned_jvp_receipt_missing"
    try: validate(_read(path), root=root, current=True, artifact=True)
    except Exception as exc: return False, f"g1_mgt_single_lifecycle_preconditioned_jvp_receipt_invalid:{exc}"
    return True, "g1_mgt_single_lifecycle_preconditioned_jvp_receipt_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--out", type=Path, default=DEFAULT_OUT); parser.add_argument("--action-out", type=Path, default=DEFAULT_ACTION_OUT); parser.add_argument("--check", action="store_true"); args = parser.parse_args(argv)
    if args.check:
        passed, reason = check(out=args.out); print(reason); return 0 if passed else 1
    payload = write(out=args.out, action_out=args.action_out); meta = payload["hardware_execution"]["runtime_metadata"]
    print(f"partial | single_device_lifecycle=true | mid_d2h=0 | kernels={meta['total_kernel_invocation_count']} | wall_ms={meta['device_lifecycle_wall_time_ms']}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
