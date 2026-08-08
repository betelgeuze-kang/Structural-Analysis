#!/usr/bin/env python3
"""Gate actual-MGT scaled FGMRES in one persistent gfx1030 lifecycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve_triangular

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

from release_evidence_metadata import engine_version, file_sha256, git_head, input_checksums  # noqa: E402
from build_g1_mgt_full_load_checkpoint_bridge import deterministic_npz_bytes  # noqa: E402
from run_engine_v2_hip_sparse_lu_apply import _detect_architecture, _resolve_device_lib_path, _resolve_hipcc, _run  # noqa: E402
from run_g1_mgt_accepted_state_hip_sparse_lu_parity import DEFAULT_CHECKPOINT, DEFAULT_MGT, WHEEL  # noqa: E402
from run_g1_mgt_single_lifecycle_preconditioned_jvp import build_references  # noqa: E402
from structural_analysis.engine_v2.contracts._canonical import array_data_hash, canonical_hash, sha256_prefixed  # noqa: E402
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import create_hip_current_tangent_operator_fixture, create_hip_current_tangent_operator_reference  # noqa: E402

PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SOURCE = Path("implementation/phase1/hip_kernels/engine_v2_mgt_fgmres.hip.cpp")
SCHEMA = Path("src/structural_analysis/schemas/g1_mgt_device_fgmres_v1.schema.json")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_device_fgmres_receipt.json"
DEFAULT_SOLUTION = PRODUCTIZATION / "g1_mgt_device_fgmres_solution.f64le"
DEFAULT_RESIDUAL = PRODUCTIZATION / "g1_mgt_device_fgmres_residual.f64le"
DEFAULT_ACCEPTED_STATE = PRODUCTIZATION / "g1_mgt_device_fgmres_accepted_state.f64le"
DEFAULT_NONLINEAR_RESIDUAL = PRODUCTIZATION / "g1_mgt_device_fgmres_nonlinear_residual.f64le"
DEFAULT_CHECKPOINT_OUT = PRODUCTIZATION / "g1_mgt_device_fgmres_checkpoint.npz"
VERSION = "g1-mgt-device-fgmres-receipt.v1"
N = 70_560
SOURCE_PATHS = (
    DEFAULT_MGT, DEFAULT_CHECKPOINT, WHEEL, SOURCE,
    Path("implementation/phase1/hip_kernels/engine_v2_mgt_preconditioned_jvp.hip.cpp"),
    Path("implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp"),
    Path("implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp"),
    Path("scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py"),
    Path("scripts/build_g1_mgt_full_load_checkpoint_bridge.py"),
    Path("scripts/run_g1_mgt_device_fgmres.py"), SCHEMA,
    Path("tests/test_run_g1_mgt_device_fgmres.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative(root: Path, path: Path) -> str:
    return _resolve(root, path).resolve().relative_to(root.resolve()).as_posix()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("receipt_must_be_object")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash({k: v for k, v in payload.items() if k != "receipt_hash"})


def _clean(root: Path) -> bool:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--",
                             *(_relative(root, p) for p in SOURCE_PATHS)], cwd=root,
                            check=True, capture_output=True, text=True)
    return not result.stdout.strip()


def _artifact(root: Path, path: Path, vector: np.ndarray) -> tuple[dict[str, Any], bytes]:
    value = np.ascontiguousarray(vector, dtype="<f8"); raw = value.tobytes()
    return ({"path": _relative(root, path), "dtype": "<f8", "shape": [N],
             "byte_length": len(raw), "file_sha256": sha256_prefixed(raw),
             "data_hash": array_data_hash(value)}, raw)


def _checkpoint(root: Path, path: Path, *, context: dict[str, Any],
                accepted_state: np.ndarray, nonlinear_residual_n: np.ndarray,
                correction: np.ndarray) -> tuple[dict[str, Any], bytes]:
    operator = context["problem"].current_tangent_operator
    free = np.asarray(operator.array("free_global_dofs"), dtype="<i8")
    global_state = np.array(
        operator.array("background_global_displacements_m"), dtype="<f8", copy=True)
    global_state[free] = accepted_state
    binding = context["problem"].exact_restart_binding()
    state_hash = canonical_hash({
        "schema_version": "g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1",
        "load_factor": 1.0,
        "free_displacement_data_hash": array_data_hash(accepted_state),
        "free_equation_order_data_hash": array_data_hash(free),
        "equilibrium_operator_binding_hash": binding["equilibrium_operator_binding_hash"],
    })
    with np.load(root / DEFAULT_CHECKPOINT, allow_pickle=False) as seed:
        node_id = np.asarray(seed["node_id"], dtype="<i8")
    arrays = {
        "accepted_state_hash": np.asarray(state_hash),
        "checkpoint_schema": np.asarray("g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1"),
        "displacement_u": np.ascontiguousarray(global_state, dtype="<f8"),
        "dof_per_node": np.asarray(6, dtype="<i4"),
        "equilibrium_operator_binding_hash": np.asarray(binding["equilibrium_operator_binding_hash"]),
        "final_increment_inf_m": np.asarray(float(np.linalg.norm(correction, ord=np.inf)), dtype="<f8"),
        "fixed_point_relative_increment": np.asarray(
            float(np.linalg.norm(correction, ord=np.inf)) /
            max(float(np.linalg.norm(accepted_state, ord=np.inf)), 1.0e-30), dtype="<f8"),
        "free_displacement_data_hash": np.asarray(array_data_hash(accepted_state)),
        "free_displacements_m": np.ascontiguousarray(accepted_state, dtype="<f8"),
        "free_equation_order_data_hash": np.asarray(array_data_hash(free)),
        "free_global_dofs": free,
        "load_scale": np.asarray(1.0, dtype="<f8"),
        "max_translation_m": np.asarray(float(np.max(np.abs(global_state.reshape(-1, 6)[:, :3]))), dtype="<f8"),
        "model_source_sha256": np.asarray(binding["model_source_sha256"]),
        "node_id": node_id,
        "residual_inf_n": np.asarray(float(np.linalg.norm(nonlinear_residual_n, ord=np.inf)), dtype="<f8"),
        "schema_version": np.asarray("g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1"),
        "source_commit_sha": np.asarray(binding["source_commit_sha"]),
    }
    started = time.perf_counter(); raw = deterministic_npz_bytes(arrays)
    overhead = time.perf_counter() - started
    if raw != deterministic_npz_bytes(arrays):
        raise RuntimeError("device_fgmres_checkpoint_not_deterministic")
    with np.load(BytesIO(raw), allow_pickle=False) as replay:
        if set(replay.files) != set(arrays) or not all(
            np.array_equal(replay[name], value) for name, value in arrays.items()):
            raise RuntimeError("device_fgmres_checkpoint_exact_reload_failed")
        if not np.array_equal(replay["free_displacements_m"], accepted_state):
            raise RuntimeError("device_fgmres_checkpoint_exact_restart_failed")
    return ({"path": _relative(root, path), "schema": str(arrays["schema_version"]),
             "byte_length": len(raw), "file_sha256": sha256_prefixed(raw),
             "accepted_state_hash": state_hash, "free_displacement_data_hash": array_data_hash(accepted_state),
             "exact_reload": True, "exact_restart_terminal_state": True,
             "serialization_overhead_seconds": overhead,
             "source_commit_sha": binding["source_commit_sha"],
             "model_source_sha256": binding["model_source_sha256"],
             "equilibrium_operator_binding_hash": binding["equilibrium_operator_binding_hash"]}, raw)


def _compile_run(root: Path, sparse: Any, tangent: Any, reference_force_n: float,
                 hipcc: str, rocm_path: str, device_lib_path: str, timeout: float) -> dict[str, Any]:
    compiler = _resolve_hipcc(hipcc); libs = _resolve_device_lib_path(root, device_lib_path)
    architecture = _detect_architecture(root, "rocminfo")
    if architecture != "gfx1030": raise RuntimeError("device_fgmres_requires_local_gfx1030")
    with tempfile.TemporaryDirectory(prefix="g1-mgt-device-fgmres-") as raw:
        temp = Path(raw); sp = temp / "sparse.bin"; tp = temp / "tangent.bin"
        binary = temp / "fgmres"; cross = temp / "fgmres-gfx1100"
        solution = temp / "solution.bin"; residual = temp / "residual.bin"
        accepted_state = temp / "accepted-state.bin"; nonlinear_residual = temp / "nonlinear-residual.bin"
        sp.write_bytes(sparse.to_bytes()); tp.write_bytes(tangent.to_bytes())
        base = [str(compiler), f"--rocm-path={rocm_path}", f"--rocm-device-lib-path={libs}"]
        tail = [str(root / SOURCE), "-O2", "-Werror", "-ffp-contract=off", "-std=c++17"]
        for arch, output in (("gfx1030", binary), ("gfx1100", cross)):
            built = _run([*base, f"--offload-arch={arch}", *tail, "-o", str(output)], cwd=root, timeout=180)
            if built.returncode: raise RuntimeError(f"device_fgmres_{arch}_compile_failed:" + built.stderr[-1000:])
        executed = _run([str(binary), str(sp), str(tp), repr(reference_force_n),
                         str(solution), str(residual), str(accepted_state), str(nonlinear_residual)],
                        cwd=root, timeout=timeout)
        if executed.returncode: raise RuntimeError("device_fgmres_execution_failed:" + executed.stderr[-1000:])
        runtime = json.loads(executed.stdout.strip().splitlines()[-1])
        return {"runtime": runtime, "solution": np.fromfile(solution, dtype="<f8"),
                "residual": np.fromfile(residual, dtype="<f8"),
                "accepted_state": np.fromfile(accepted_state, dtype="<f8"),
                "nonlinear_residual": np.fromfile(nonlinear_residual, dtype="<f8"),
                "binary_sha256": file_sha256(binary), "binary_byte_length": binary.stat().st_size,
                "gfx1100_cross_binary_sha256": file_sha256(cross),
                "compiler_version": _run([str(compiler), "--version"], cwd=root, timeout=30).stdout.splitlines()[0]}


def _cpu_baseline(*, sparse: Any, context: dict[str, Any],
                  reference_force_n: float) -> dict[str, Any]:
    factor = sparse.factor; n = factor.dimension; restart = 6
    lower = csr_matrix((factor.lower_numeric_values, factor.lower_column_indices,
                        factor.lower_row_pointer), shape=(n, n))
    upper = csr_matrix((factor.upper_numeric_values, factor.upper_column_indices,
                        factor.upper_row_pointer), shape=(n, n))

    def precondition(vector: np.ndarray) -> np.ndarray:
        rhs_n = vector * reference_force_n
        permuted = rhs_n[factor.inverse_row_permutation]
        low = spsolve_triangular(lower, permuted, lower=True)
        high = spsolve_triangular(upper, low, lower=False)
        return np.asarray(high[factor.column_permutation], dtype=np.float64)

    operator = context["problem"].current_tangent_operator
    state = context["state"]
    rhs_n = context["rhs_kn"] * 1000.0
    started = time.perf_counter()
    scaled_rhs = rhs_n / reference_force_n
    beta = float(np.linalg.norm(scaled_rhs))
    basis = np.zeros((restart + 1, n), dtype=np.float64)
    directions = np.zeros((restart, n), dtype=np.float64)
    hessenberg = np.zeros((restart + 1, restart), dtype=np.float64)
    basis[0] = scaled_rhs / beta
    for column in range(restart):
        directions[column] = precondition(basis[column])
        work = np.asarray(operator.apply_n_per_m(
            state, 1.0, directions[column]), dtype=np.float64) / reference_force_n
        for _pass in range(2):
            for row in range(column + 1):
                coefficient = float(np.dot(basis[row], work))
                hessenberg[row, column] += coefficient
                work -= coefficient * basis[row]
        hessenberg[column + 1, column] = float(np.linalg.norm(work))
        basis[column + 1] = work / hessenberg[column + 1, column]
    target = np.zeros(restart + 1, dtype=np.float64); target[0] = beta
    coefficients = np.linalg.lstsq(hessenberg, target, rcond=None)[0]
    correction = coefficients @ directions
    linear_action_n = np.asarray(
        operator.apply_n_per_m(state, 1.0, correction), dtype=np.float64)
    linear_residual_inf_n = float(np.linalg.norm(rhs_n - linear_action_n, ord=np.inf))
    alphas = (1.0, 0.5, 0.25, 0.125, 0.0625)
    base_l2 = float(np.linalg.norm(-rhs_n))
    candidates = []
    selected = None
    for alpha in alphas:
        residual_n = np.asarray(
            context["problem"].residual_kn(state + alpha * correction, 1.0),
            dtype=np.float64) * 1000.0
        l2 = float(np.linalg.norm(residual_n)); inf = float(np.linalg.norm(residual_n, ord=np.inf))
        candidates.append({"alpha": alpha, "residual_l2_n": l2, "residual_inf_n": inf})
        if selected is None and l2 <= (1.0 - 1.0e-4 * alpha) * base_l2:
            selected = len(candidates) - 1
    wall = time.perf_counter() - started
    if selected is None: raise RuntimeError("cpu_baseline_line_search_failed")
    return {"wall_seconds": wall, "krylov_iterations": restart,
            "preconditioner_apply_count": restart, "matvec_count": restart + 1,
            "physical_residual_evaluation_count": len(alphas),
            "terminal_linear_residual_inf_n": linear_residual_inf_n,
            "selected_index": selected, "accepted_alpha": alphas[selected],
            "accepted_residual_inf_n": candidates[selected]["residual_inf_n"],
            "candidate_rows": candidates,
            "correction_data_hash": array_data_hash(np.ascontiguousarray(correction, dtype="<f8"))}


def run(*, root: Path = ROOT, out: Path = DEFAULT_OUT, solution_out: Path = DEFAULT_SOLUTION,
        residual_out: Path = DEFAULT_RESIDUAL, accepted_state_out: Path = DEFAULT_ACCEPTED_STATE,
        nonlinear_residual_out: Path = DEFAULT_NONLINEAR_RESIDUAL,
        checkpoint_out: Path = DEFAULT_CHECKPOINT_OUT,
        hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
        rocm_path: str = "/opt/rocm-6.0.2", device_lib_path: str = "", timeout: float = 600
        ) -> tuple[dict[str, Any], bytes, bytes, bytes, bytes, bytes]:
    root = root.resolve()
    if not _clean(root): raise RuntimeError("device_fgmres_requires_clean_source_paths")
    sparse, _, tangent, context = build_references(root=root)
    reference_load_kn = np.asarray(context["problem"].reference_load_kn(), dtype=np.float64)
    reference_force_n = max(1.0, float(np.max(np.abs(reference_load_kn))) * 1000.0)
    execution = _compile_run(root, sparse, tangent.fixture, reference_force_n,
                             hipcc, rocm_path, device_lib_path, timeout)
    cpu_baseline = _cpu_baseline(
        sparse=sparse, context=context, reference_force_n=reference_force_n)
    runtime = execution["runtime"]; solution = execution["solution"]; residual = execution["residual"]
    accepted_state = execution["accepted_state"]; nonlinear_residual = execution["nonlinear_residual"]
    if any(value.shape != (N,) for value in (solution, residual, accepted_state, nonlinear_residual)):
        raise RuntimeError("device_fgmres_output_shape_invalid")
    replay_fixture = create_hip_current_tangent_operator_fixture(
        context["problem"].current_tangent_operator,
        free_displacements_m=context["state"], load_factor=1.0, free_direction_m=solution)
    replay = create_hip_current_tangent_operator_reference(replay_fixture)
    expected_residual = context["rhs_kn"] * 1000.0 - replay.device_order_action_n_per_m
    replay_error = float(np.max(np.abs(residual - expected_residual)))
    expected_nonlinear_residual = np.asarray(
        context["problem"].residual_kn(accepted_state, 1.0), dtype=np.float64) * 1000.0
    nonlinear_replay_error = float(np.max(np.abs(
        nonlinear_residual - expected_nonlinear_residual)))
    nonlinear_parity_tolerance_n = 2.0e-6
    contract = bool(runtime["status"] == "ok" and runtime["gcn_arch_name"] == "gfx1030"
                    and runtime["krylov_iterations"] == 6 and runtime["preconditioner_apply_count"] == 6
                    and runtime["matvec_count"] == 7 and runtime["mid_iteration_d2h_transfer_count"] == 0
                    and runtime["physical_residual_inf_n"] <= 1.0e-9 and replay_error <= 1.0e-18
                    and runtime["accepted_alpha"] == 1.0
                    and runtime["accepted_nonlinear_residual_inf_n"] <= 5.0e-4
                    and nonlinear_replay_error <= nonlinear_parity_tolerance_n)
    if not contract: raise RuntimeError("device_fgmres_contract_failed")
    solution_item, solution_raw = _artifact(root, solution_out, solution)
    residual_item, residual_raw = _artifact(root, residual_out, residual)
    accepted_state_item, accepted_state_raw = _artifact(root, accepted_state_out, accepted_state)
    nonlinear_residual_item, nonlinear_residual_raw = _artifact(
        root, nonlinear_residual_out, nonlinear_residual)
    checkpoint_item, checkpoint_raw = _checkpoint(
        root, checkpoint_out, context=context, accepted_state=accepted_state,
        nonlinear_residual_n=nonlinear_residual, correction=solution)
    scaling = {"schema_version": "equation-scaling-mgt-translation-free.v1",
               "reference_force_policy": "max_translation_or_equivalent_moment_with_floor.v1",
               "minimum_reference_force_n": 1.0, "reference_force_n": reference_force_n,
               "free_equation_scope": True, "translation_equation_count": N,
               "scale_vector_data_hash": array_data_hash(np.full(N, reference_force_n, dtype="<f8"))}
    payload = {
        "schema_version": VERSION, "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "contract_pass": True,
        "contract_scope": "actual_mgt_full_load_scaled_fgmres_single_device_lifecycle_local_gfx1030",
        "source": {"repository_commit_sha": git_head(root), "source_paths_clean_at_execution": True,
                   "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root), "engine_version": engine_version(root)},
        "runtime": {"backend": "amd_rocm_hip", "device_name": runtime["device_name"],
                    "gcn_arch_name": runtime["gcn_arch_name"], "device_nodes": ["/dev/kfd", "/dev/dri/renderD128"],
                    "compiler_version": execution["compiler_version"], "binary_sha256": execution["binary_sha256"],
                    "binary_byte_length": execution["binary_byte_length"],
                    "gfx1100_cross_compile_binary_sha256": execution["gfx1100_cross_binary_sha256"],
                    "wheel_sha256": file_sha256(root / WHEEL)},
        "accepted_state": {"checkpoint": DEFAULT_CHECKPOINT.as_posix(), "checkpoint_sha256": file_sha256(root / DEFAULT_CHECKPOINT),
                           "load_factor": 1.0, "equation_count": N, "state_data_hash": array_data_hash(context["state"]),
                           "right_hand_side_data_hash": array_data_hash(context["rhs_kn"])},
        "equation_scaling": scaling, "hardware_execution": runtime,
        "performance": {"cpu_baseline": cpu_baseline,
                        "gpu_device_lifecycle_wall_seconds": runtime["device_lifecycle_wall_time_ms"] / 1000.0,
                        "speedup_vs_cpu": cpu_baseline["wall_seconds"] /
                        (runtime["device_lifecycle_wall_time_ms"] / 1000.0),
                        "terminal_resultir_parity": False,
                        "terminal_resultir_parity_reason": "authoritative_resultir_not_emitted_without_material_state_bundle"},
        "comparison": {"terminal_physical_residual_cpu_replay_max_abs_error_n": replay_error,
                       "terminal_physical_residual_tolerance_n": 1.0e-9,
                       "accepted_nonlinear_residual_cpu_replay_max_abs_error_n": nonlinear_replay_error,
                       "accepted_nonlinear_residual_parity_tolerance_n": nonlinear_parity_tolerance_n,
                       "accepted_nonlinear_residual_cpu_inf_n": float(np.linalg.norm(expected_nonlinear_residual, ord=np.inf)),
                       "solution_artifact": solution_item, "residual_artifact": residual_item,
                       "accepted_state_artifact": accepted_state_item,
                       "nonlinear_residual_artifact": nonlinear_residual_item,
                       "checkpoint_artifact": checkpoint_item},
        "claims": {"actual_mgt_full_load_accepted_state": True, "production_size_fgmres": True,
                   "two_pass_mgs_arnoldi": True, "device_givens_and_backsolve": True,
                   "equation_scaling": True, "terminal_physical_residual_replay": True,
                   "single_device_lifecycle": True, "mid_iteration_d2h_zero": True,
                   "newton_update_on_device": True, "physical_line_search_on_device": True,
                   "nonlinear_convergence_gate_on_device": True,
                   "checkpoint_emitted": True, "exact_restart": True,
                   "gfx1100_cross_compile": True, "independent_gfx1100_run": False,
                   "material_commit_rollback": False, "resultir_diagnosticir": False,
                   "g1_closure": False},
        "blockers_remaining": ["independent_gfx1100_hardware_run_not_available",
                               "material_commit_rollback_not_established",
                               "resultir_diagnosticir_not_established"],
        "claim_boundary": "Actual 70,560-equation accepted-state right-preconditioned FGMRES executes six two-pass-MGS Arnoldi iterations, device Givens rotations and backsolve, finite-chord physical-residual line-search candidates, accepted-state update, and a nonlinear convergence gate in one gfx1030 lifecycle with zero iteration-time D2H. The accepted state is emitted through the deterministic full-load checkpoint schema and exact-reloaded. gfx1100 is cross-compiled only; material commit/rollback, ResultIR, DiagnosticIR, and independent gfx1100 hardware remain unclaimed."
    }
    payload["receipt_hash"] = _hash(payload); validate(payload, root=root, current=True)
    return (payload, solution_raw, residual_raw, accepted_state_raw,
            nonlinear_residual_raw, checkpoint_raw)


def validate(payload: dict[str, Any], *, root: Path = ROOT, current: bool = False, artifacts: bool = False) -> dict[str, Any]:
    schema = _read(root / SCHEMA); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload): raise ValueError("device_fgmres_receipt_hash_mismatch")
    if current and payload["source"]["input_checksums"] != input_checksums(SOURCE_PATHS, repo_root=root):
        raise ValueError("device_fgmres_sources_stale")
    if artifacts:
        for key in ("solution_artifact", "residual_artifact", "accepted_state_artifact", "nonlinear_residual_artifact", "checkpoint_artifact"):
            item = payload["comparison"][key]; path = _resolve(root, Path(item["path"]))
            if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]:
                raise ValueError("device_fgmres_artifact_invalid")
    return payload


def write(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs.get("root", ROOT)).resolve(); out = Path(kwargs.get("out", DEFAULT_OUT))
    solution = Path(kwargs.get("solution_out", DEFAULT_SOLUTION)); residual = Path(kwargs.get("residual_out", DEFAULT_RESIDUAL))
    accepted = Path(kwargs.get("accepted_state_out", DEFAULT_ACCEPTED_STATE))
    nonlinear = Path(kwargs.get("nonlinear_residual_out", DEFAULT_NONLINEAR_RESIDUAL))
    checkpoint = Path(kwargs.get("checkpoint_out", DEFAULT_CHECKPOINT_OUT))
    payload, sr, rr, ar, nr, cr = run(**kwargs)
    _resolve(root, solution).write_bytes(sr); _resolve(root, residual).write_bytes(rr)
    _resolve(root, accepted).write_bytes(ar); _resolve(root, nonlinear).write_bytes(nr)
    _resolve(root, checkpoint).write_bytes(cr)
    _resolve(root, out).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return validate(payload, root=root, current=True, artifacts=True)


def check(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> tuple[bool, str]:
    try: validate(_read(_resolve(root, out)), root=root, current=True, artifacts=True)
    except Exception as exc: return False, f"g1_mgt_device_fgmres_receipt_invalid:{exc}"
    return True, "g1_mgt_device_fgmres_receipt_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        passed, reason = check(); print(reason); return 0 if passed else 1
    payload = write(); runmeta = payload["hardware_execution"]
    print(f"partial | fgmres={runmeta['krylov_iterations']} | residual_inf_n={runmeta['physical_residual_inf_n']:.3e} | mid_d2h=0")
    return 0


if __name__ == "__main__": raise SystemExit(main())
