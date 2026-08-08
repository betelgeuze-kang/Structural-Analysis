#!/usr/bin/env python3
"""Run a source-bound gfx1030 HIP FGMRES model-size performance sweep."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

import numpy as np
from jsonschema import Draft202012Validator
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import LinearOperator, gmres

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from structural_analysis.engine_v2.contracts._canonical import canonical_hash  # noqa: E402

SOURCE = Path("implementation/phase1/hip_kernels/engine_v2_fgmres_recurrence.hip.cpp")
SCHEMA = Path("src/structural_analysis/schemas/g1_hip_fgmres_performance_sweep_v1.schema.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/g1_hip_fgmres_gfx1030_performance_sweep.json")
WHEEL = Path("dist/structural_analysis-0.3.0-py3-none-any.whl")
DIMENSIONS = (66, 264, 1056, 4092, 70560)
SOURCE_PATHS = (SOURCE, SCHEMA, Path("scripts/run_g1_hip_fgmres_performance_sweep.py"), Path("tests/test_g1_hip_fgmres_performance_sweep.py"))


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with (ROOT / path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _problem(dimension: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if dimension < 2 or dimension > 70560:
        raise ValueError("sweep_dimension_out_of_range")
    row_ptr = [0]; columns: list[int] = []; values: list[float] = []
    rhs = np.empty(dimension, dtype=np.float64)
    for row in range(dimension):
        if row > 0:
            columns.append(row - 1); values.append(-1.0)
        columns.append(row); values.append(4.0)
        if row + 1 < dimension:
            columns.append(row + 1); values.append(-1.0)
        row_ptr.append(len(columns)); rhs[row] = 3.0 if row in (0, dimension - 1) else 2.0
    return np.asarray(row_ptr, dtype=np.int64), np.asarray(columns, dtype=np.int32), np.asarray(values), rhs


def _fixture_bytes(dimension: int) -> bytes:
    row_ptr, columns, values, rhs = _problem(dimension)
    scale = np.ones(dimension); initial = np.zeros(dimension); inverse_diagonal = np.full(dimension, 0.25)
    chunks = [struct.pack("<8sQQQ", b"EV2FGR01", dimension, values.size, 2), row_ptr.tobytes(), columns.tobytes(), values.tobytes(), rhs.tobytes(), scale.tobytes(), initial.tobytes(), inverse_diagonal.tobytes()]
    chunks.extend((
        struct.pack("<QQddd", 24, 24, 1.0e-10, 1.0e-12, 1.0e-14),
        struct.pack("<QQddd", 2, 1, 1.0e-30, 0.0, 1.0e-14),
    ))
    return b"".join(chunks)


def _checkpoint_bytes(dimension: int) -> bytes:
    _, _, _, rhs = _problem(dimension)
    threshold = float(np.linalg.norm(rhs) * 1.0e-30)
    return b"".join((
        struct.pack("<8sQQQQd", b"EV2FGCP1", dimension, 1, 3, 1, threshold),
        np.zeros(dimension, dtype=np.float64).tobytes(), rhs.tobytes(),
    ))


def _cpu_solve(dimension: int, repetitions: int) -> dict[str, Any]:
    row_ptr, columns, values, rhs = _problem(dimension); matrix = csr_matrix((values, columns, row_ptr), shape=(dimension, dimension))
    timings: list[float] = []; iteration_counts: list[int] = []; matvec_counts: list[int] = []; residuals: list[float] = []; solution_errors: list[float] = []
    for _ in range(repetitions):
        matvec_count = 0; iteration_count = 0
        def apply(vector: np.ndarray) -> np.ndarray:
            nonlocal matvec_count
            matvec_count += 1; return matrix @ vector
        def observe(_value: float) -> None:
            nonlocal iteration_count
            iteration_count += 1
        operator = LinearOperator(matrix.shape, matvec=apply, dtype=np.float64)
        start = time.perf_counter(); solution, info = gmres(operator, rhs, M=LinearOperator(matrix.shape, matvec=lambda vector: 0.25 * vector, dtype=np.float64), restart=24, maxiter=24, rtol=1.0e-10, atol=1.0e-12, callback=observe, callback_type="pr_norm"); elapsed = (time.perf_counter() - start) * 1000.0
        if info != 0:
            raise RuntimeError(f"cpu_gmres_failed:{dimension}:{info}")
        timings.append(elapsed); iteration_counts.append(iteration_count); matvec_counts.append(matvec_count); residuals.append(float(np.linalg.norm(matrix @ solution - rhs, ord=np.inf))); solution_errors.append(float(np.max(np.abs(solution - 1.0))))
    return {"implementation": "scipy.sparse.linalg.gmres", "wall_time_samples_ms": timings, "wall_time_median_ms": statistics.median(timings), "iteration_count": max(iteration_counts), "matvec_count": max(matvec_counts), "maximum_physical_residual_n": max(residuals), "maximum_exact_solution_error": max(solution_errors)}


def _compile(binary: Path, hipcc: Path, architecture: str) -> dict[str, Any]:
    version = subprocess.run([str(hipcc), "--version"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    device_libs = ROOT / "implementation/phase1/third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
    command = [str(hipcc), "--rocm-path=/opt/rocm-6.0.2", f"--rocm-device-lib-path={device_libs}", f"--offload-arch={architecture}", "-DENGINE_V2_FGMRES_MAXIMUM_FIXTURE_DIMENSION=70560", str(ROOT / SOURCE), "-O2", "-std=c++17", "-o", str(binary)]
    compiled = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, timeout=180)
    if compiled.returncode != 0:
        raise RuntimeError("hip_sweep_compile_failed:" + compiled.stderr[-1000:].replace("\n", " "))
    return {"path": str(hipcc), "version_first_line": version.splitlines()[0], "version_output_sha256": "sha256:" + hashlib.sha256(version.encode()).hexdigest(), "binary_sha256": "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()}


def _execute(binary: Path, fixture: Path, checkpoint: Path) -> tuple[dict[str, Any], float]:
    start = time.perf_counter(); result = subprocess.run([str(binary), str(fixture), str(checkpoint)], cwd=ROOT, check=False, capture_output=True, text=True, timeout=120); elapsed = (time.perf_counter() - start) * 1000.0
    if result.returncode != 0:
        raise RuntimeError("hip_sweep_execution_failed:" + result.stderr[-1000:].replace("\n", " "))
    return json.loads(result.stdout.strip().splitlines()[-1]), elapsed


def _case(dimension: int, binary: Path, temporary: Path, repetitions: int) -> dict[str, Any]:
    fixture = temporary / f"fixture-{dimension}.bin"; checkpoint = temporary / f"checkpoint-{dimension}.bin"
    fixture.write_bytes(_fixture_bytes(dimension)); checkpoint.write_bytes(_checkpoint_bytes(dimension))
    _execute(binary, fixture, checkpoint)
    outputs: list[dict[str, Any]] = []; process_ms: list[float] = []
    for _ in range(repetitions):
        output, elapsed = _execute(binary, fixture, checkpoint); outputs.append(output); process_ms.append(elapsed)
    first = outputs[0]; converged = first["cases"][0]
    stable_fields = ("executed_matvec_count", "preconditioner_apply_count", "h2d_bytes", "d2h_bytes", "tracked_peak_device_allocation_bytes", "workspace_dimension")
    if any(any(row[field] != first[field] for field in stable_fields) for row in outputs[1:]):
        raise RuntimeError(f"hip_sweep_telemetry_not_deterministic:{dimension}")
    if not converged["converged"] or converged["terminal_reason"] != "converged_scaled_residual" or first["mid_recurrence_host_transfer_count"] != 0 or first["gcn_arch_name"] != "gfx1030":
        raise RuntimeError(f"hip_sweep_runtime_contract_failed:{dimension}")
    row_ptr, columns, values, rhs = _problem(dimension); matrix = csr_matrix((values, columns, row_ptr), shape=(dimension, dimension)); gpu_solution = np.asarray(converged["solution"])
    gpu_physical_residual = float(np.linalg.norm(matrix @ gpu_solution - rhs, ord=np.inf)); gpu_solution_error = float(np.max(np.abs(gpu_solution - 1.0)))
    if gpu_physical_residual > 5.0e-8 or gpu_solution_error > 2.0e-8:
        raise RuntimeError(f"hip_sweep_terminal_parity_failed:{dimension}")
    cpu = _cpu_solve(dimension, repetitions); lifecycle = [float(row["device_lifecycle_wall_time_ms"]) for row in outputs]
    return {
        "dimension": dimension, "nnz": int(_problem(dimension)[2].size), "repetitions": repetitions,
        "gpu": {"krylov_iteration_count": int(converged["iteration_count"]), "matvec_count": int(first["executed_matvec_count"]), "preconditioner_apply_count": int(first["preconditioner_apply_count"]), "h2d_bytes": int(first["h2d_bytes"]), "d2h_bytes": int(first["d2h_bytes"]), "mid_recurrence_host_transfer_count": int(first["mid_recurrence_host_transfer_count"]), "tracked_peak_device_allocation_bytes": int(first["tracked_peak_device_allocation_bytes"]), "device_lifecycle_wall_time_samples_ms": lifecycle, "device_lifecycle_wall_time_median_ms": statistics.median(lifecycle), "process_wall_time_samples_ms": process_ms, "process_wall_time_median_ms": statistics.median(process_ms), "terminal_scaled_l2": float(converged["scaled_l2_history"][-1]), "maximum_physical_residual_n": gpu_physical_residual, "maximum_exact_solution_error": gpu_solution_error},
        "cpu": cpu,
        "speedup": {"device_lifecycle_vs_cpu_solver": cpu["wall_time_median_ms"] / statistics.median(lifecycle), "gpu_process_vs_cpu_solver": cpu["wall_time_median_ms"] / statistics.median(process_ms)},
    }


def build_receipt(*, repetitions: int = 3) -> dict[str, Any]:
    if repetitions < 2:
        raise ValueError("sweep_repetitions_too_small")
    source_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *(path.as_posix() for path in SOURCE_PATHS)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if source_status:
        raise RuntimeError("hip_sweep_requires_clean_source_paths")
    hipcc = Path("/opt/rocm-6.0.2/bin/hipcc"); wheel = ROOT / WHEEL
    if not hipcc.is_file() or not wheel.is_file() or not Path("/dev/kfd").exists() or not Path("/dev/dri/renderD128").exists():
        raise RuntimeError("hip_sweep_runtime_prerequisite_missing")
    with tempfile.TemporaryDirectory(prefix="g1-hip-fgmres-sweep-") as name:
        temporary = Path(name); binary = temporary / "engine_v2_fgmres_recurrence"; compiler = _compile(binary, hipcc, "gfx1030")
        cases = [_case(dimension, binary, temporary, repetitions) for dimension in DIMENSIONS]
    payload = {
        "schema_version": "g1-hip-fgmres-performance-sweep.v1", "receipt_hash": "sha256:" + "0" * 64,
        "source": {"repository_commit_sha": _git("rev-parse", "HEAD"), "source_paths_clean_at_execution": True, "input_checksums": {path.as_posix(): _sha_file(path) for path in SOURCE_PATHS}},
        "runtime": {"backend": "amd_rocm_hip", "device_name": "AMD Radeon RX 6900 XT", "gcn_arch_name": "gfx1030", "device_nodes": ["/dev/kfd", "/dev/dri/renderD128"], "compiler": compiler, "wheel": {"path": WHEEL.as_posix(), "sha256": _sha_file(WHEEL), "bound_at_execution": True}},
        "sweep": {"dimensions": list(DIMENSIONS), "cases": cases},
        "claims": {"actual_gfx1030_hardware": True, "bounded_model_size_performance_sweep": True, "mid_recurrence_d2h_zero": all(row["gpu"]["mid_recurrence_host_transfer_count"] == 0 for row in cases), "synthetic_70560_equation_lifecycle": any(row["dimension"] == 70560 for row in cases), "production_mgt_70560_operator": False, "independent_gfx1100": False, "cross_device_performance": False},
        "blockers_remaining": ["production_mgt_70560_operator_performance_not_measured", "production_operator_and_preconditioner_breadth_not_measured", "independent_gfx1100_run_not_available", "cross_device_performance_sweep_not_available"],
        "contract_pass": True,
        "claim_boundary": "Actual current-source gfx1030 lifecycle sweep for synthetic tridiagonal SPD reduced-CSR fixtures from 66 through 70,560 equations. Reports exact runtime counters and CPU comparison without claiming the 70,560-equation production MGT shell operator, production preconditioner breadth, gfx1100, or cross-device performance.",
    }
    payload["receipt_hash"] = canonical_hash({key: value for key, value in payload.items() if key != "receipt_hash"})
    validate_receipt(payload, require_current_sources=True); return payload


def validate_receipt(payload: dict[str, Any], *, require_current_sources: bool) -> dict[str, Any]:
    schema = json.loads((ROOT / SCHEMA).read_text(encoding="utf-8")); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(payload)
    expected = canonical_hash({key: value for key, value in payload.items() if key != "receipt_hash"})
    if payload["receipt_hash"] != expected:
        raise ValueError("hip_sweep_receipt_hash_mismatch")
    if require_current_sources:
        current = {path.as_posix(): _sha_file(path) for path in SOURCE_PATHS}
        if current != payload["source"]["input_checksums"]:
            raise ValueError("hip_sweep_sources_stale")
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", payload["source"]["repository_commit_sha"], "HEAD"], cwd=ROOT).returncode == 0
        if not ancestor:
            raise ValueError("hip_sweep_source_commit_not_ancestor")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--out", type=Path, default=DEFAULT_OUT); parser.add_argument("--repetitions", type=int, default=3); parser.add_argument("--check", action="store_true"); args = parser.parse_args(argv)
    path = args.out if args.out.is_absolute() else ROOT / args.out
    if args.check:
        try: validate_receipt(json.loads(path.read_text(encoding="utf-8")), require_current_sources=True)
        except Exception as exc: print(f"g1_hip_fgmres_performance_sweep_invalid:{exc}"); return 1
        print("g1_hip_fgmres_performance_sweep_consistent"); return 0
    receipt = build_receipt(repetitions=args.repetitions); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ready | gfx1030 | sizes={receipt['sweep']['dimensions']} | max_vram={max(row['gpu']['tracked_peak_device_allocation_bytes'] for row in receipt['sweep']['cases'])}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
