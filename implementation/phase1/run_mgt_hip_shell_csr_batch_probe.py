#!/usr/bin/env python3
"""Validate native HIP shell CSR batch replay against the G1 CPU shell path."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_shell_force_based_assembly import _cached_shell_operator  # noqa: E402
from run_mgt_direct_residual_newton_probe import DEFAULT_CHECKPOINT, PRODUCTIZATION  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-hip-shell-csr-batch-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_hip_shell_csr_batch_followup40_probe.json"
HIP_SOURCE = PHASE1 / "hip_shell_csr_batch_replay.cpp"
HIP_BINARY = PRODUCTIZATION / "bin/hip_shell_csr_batch_replay"
ROCM_DEVICE_LIB_PATH = (
    PHASE1 / "third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
)


def _max_abs(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(arr))) if arr.size else 0.0


def _candidate_state_batch(
    *,
    u0: np.ndarray,
    free: np.ndarray,
    batch_size: int,
    perturbation_scale: float,
) -> np.ndarray:
    u_ref = np.asarray(u0, dtype=np.float64)
    free_dofs = np.asarray(free, dtype=np.int64)
    size = max(int(batch_size), 1)
    rows = np.repeat(u_ref[None, :], size, axis=0)
    if size == 1 or free_dofs.size == 0:
        return rows
    selected = np.linspace(0, free_dofs.size - 1, num=size - 1, dtype=np.int64)
    for row_index, free_index in enumerate(selected.tolist(), start=1):
        global_dof = int(free_dofs[int(free_index)])
        sign = -1.0 if row_index % 2 == 0 else 1.0
        epsilon = sign * float(perturbation_scale) * max(abs(float(u_ref[global_dof])), 1.0)
        rows[row_index, global_dof] += epsilon
    return rows


def _summary_seconds(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min_seconds": float(np.min(arr)) if arr.size else 0.0,
        "mean_seconds": float(np.mean(arr)) if arr.size else 0.0,
        "max_seconds": float(np.max(arr)) if arr.size else 0.0,
    }


def _build_binary(*, hipcc: Path, force_rebuild: bool = False) -> dict[str, Any]:
    HIP_BINARY.parent.mkdir(parents=True, exist_ok=True)
    needs_build = bool(force_rebuild) or not HIP_BINARY.exists()
    if HIP_BINARY.exists() and HIP_SOURCE.exists():
        needs_build = needs_build or HIP_SOURCE.stat().st_mtime > HIP_BINARY.stat().st_mtime
    command = [
        str(hipcc),
        "-O3",
        "-std=c++17",
        "--offload-arch=gfx1030",
    ]
    if ROCM_DEVICE_LIB_PATH.exists():
        command.append(f"--rocm-device-lib-path={ROCM_DEVICE_LIB_PATH}")
    command.extend([str(HIP_SOURCE), "-o", str(HIP_BINARY)])
    if not needs_build:
        return {
            "attempted": False,
            "ok": True,
            "binary": str(HIP_BINARY),
            "source": str(HIP_SOURCE),
            "command": command,
            "reason": "binary_current",
        }
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "binary": str(HIP_BINARY),
        "source": str(HIP_SOURCE),
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "seconds": float(time.perf_counter() - started),
    }


def _run_hip_bridge(
    *,
    row_ptr_path: Path,
    col_idx_path: Path,
    values_path: Path,
    states_path: Path,
    output_path: Path,
    n_rows: int,
    n_dof: int,
    nnz: int,
    batch_size: int,
    reps: int,
) -> tuple[dict[str, Any], float]:
    command = [
        str(HIP_BINARY),
        "--row-ptr",
        str(row_ptr_path),
        "--col-idx",
        str(col_idx_path),
        "--values",
        str(values_path),
        "--states",
        str(states_path),
        "--output",
        str(output_path),
        "--n-rows",
        str(n_rows),
        "--n-dof",
        str(n_dof),
        "--nnz",
        str(nnz),
        "--batch-size",
        str(batch_size),
        "--reps",
        str(reps),
    ]
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    elapsed = float(time.perf_counter() - started)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    payload.update(
        {
            "command": command,
            "returncode": int(proc.returncode),
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "subprocess_seconds": elapsed,
        }
    )
    return payload, elapsed


def run_mgt_hip_shell_csr_batch_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    shell_pressure_load_path_policy: str = "attached_components_only",
    include_membrane: bool = True,
    batch_size: int = 64,
    reps: int = 20,
    perturbation_scale: float = 1.0e-6,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    build = _build_binary(hipcc=hipcc, force_rebuild=force_rebuild)
    if not bool(build.get("ok")):
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "fail",
            "reason": "hip_shell_csr_bridge_build_failed",
            "build": build,
            "claim_boundary": "Build failure only; no G1 residual gate claim.",
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload

    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )
    u0 = np.asarray(setup_meta["u0"], dtype=np.float64)
    node_xyz = np.asarray(setup_meta["_node_xyz"], dtype=np.float64)
    elem_type_code = np.asarray(setup_meta["_elem_type_code"], dtype=np.int32)
    elem_section_id = np.asarray(setup_meta["_elem_section_id"], dtype=np.int32)
    elem_material_id = np.asarray(setup_meta["_elem_material_id"], dtype=np.int32)
    conn_ptr = np.asarray(setup_meta["_conn_ptr"], dtype=np.int64)
    conn_idx = np.asarray(setup_meta["_conn_idx"], dtype=np.int64)
    material_props = setup_meta["_material_props"]
    plate_thickness_props = setup_meta["_plate_thickness_props"]
    _k, _f_ext, free, base_residual, rhs, _meta = assemble_residual(u0)
    states = _candidate_state_batch(
        u0=u0,
        free=free,
        batch_size=batch_size,
        perturbation_scale=perturbation_scale,
    )

    shell_cache: dict[str, Any] = {}
    shell_started = time.perf_counter()
    shell_stiffness, shell_meta, cache_hit = _cached_shell_operator(
        u=states[0],
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=include_membrane,
        shell_operator_cache=shell_cache,
    )
    shell_build_seconds = float(time.perf_counter() - shell_started)
    shell_csr = shell_stiffness.tocsr()

    cpu_times: list[float] = []
    cpu_shell = np.zeros((0, int(u0.size)), dtype=np.float64)
    for _rep in range(max(int(reps), 1)):
        cpu_started = time.perf_counter()
        cpu_shell = np.asarray(shell_csr @ states.T, dtype=np.float64).T
        cpu_times.append(float(time.perf_counter() - cpu_started))
    cpu_mean = float(np.mean(np.asarray(cpu_times, dtype=np.float64)))

    with tempfile.TemporaryDirectory(prefix="mgt_hip_shell_csr_batch_") as tmp_name:
        tmp_dir = Path(tmp_name)
        row_ptr_path = tmp_dir / "row_ptr.i64"
        col_idx_path = tmp_dir / "col_idx.i64"
        values_path = tmp_dir / "values.f64"
        states_path = tmp_dir / "states.f64"
        hip_output_path = tmp_dir / "hip_shell_force.f64"
        np.asarray(shell_csr.indptr, dtype=np.int64).tofile(row_ptr_path)
        np.asarray(shell_csr.indices, dtype=np.int64).tofile(col_idx_path)
        np.asarray(shell_csr.data, dtype=np.float64).tofile(values_path)
        np.asarray(states, dtype=np.float64).tofile(states_path)
        hip_payload, hip_subprocess_seconds = _run_hip_bridge(
            row_ptr_path=row_ptr_path,
            col_idx_path=col_idx_path,
            values_path=values_path,
            states_path=states_path,
            output_path=hip_output_path,
            n_rows=int(shell_csr.shape[0]),
            n_dof=int(states.shape[1]),
            nnz=int(shell_csr.nnz),
            batch_size=int(states.shape[0]),
            reps=max(int(reps), 1),
        )
        if not hip_output_path.exists():
            payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "fail",
                "reason": "hip_shell_csr_bridge_output_missing",
                "mgt_path": str(mgt_path),
                "checkpoint_npz": str(checkpoint_npz),
                "include_membrane": bool(include_membrane),
                "batch_size": int(states.shape[0]),
                "dof_count": int(u0.size),
                "shell_nnz": int(shell_csr.nnz),
                "build": build,
                "hip": hip_payload,
                "hip_subprocess_seconds": hip_subprocess_seconds,
                "runtime_seconds": float(time.perf_counter() - started),
                "claim_boundary": "HIP bridge execution failed before output comparison; no G1 gate claim.",
            }
            if output_json is not None:
                output_json.parent.mkdir(parents=True, exist_ok=True)
                output_json.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            return payload
        hip_shell = np.fromfile(hip_output_path, dtype=np.float64).reshape(cpu_shell.shape)

    diff = np.asarray(hip_shell - cpu_shell, dtype=np.float64)
    max_abs_difference = _max_abs(diff)
    relative_difference_inf = max_abs_difference / max(_max_abs(cpu_shell), 1.0)
    hip_kernel_mean_seconds = float(hip_payload.get("kernel_elapsed_ms_mean") or 0.0) / 1000.0
    absolute_tolerance_n = 2.0e-6
    relative_tolerance_inf = 1.0e-10
    comparison_pass = bool(hip_payload.get("ok") is True) and (
        max_abs_difference <= absolute_tolerance_n
        or relative_difference_inf <= relative_tolerance_inf
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if comparison_pass else "warn",
        "mgt_path": str(mgt_path),
        "checkpoint_npz": str(checkpoint_npz),
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "include_membrane": bool(include_membrane),
        "batch_size": int(states.shape[0]),
        "dof_count": int(u0.size),
        "free_dof_count": int(free.size),
        "shell_shape": [int(shell_csr.shape[0]), int(shell_csr.shape[1])],
        "shell_nnz": int(shell_csr.nnz),
        "reps": int(max(int(reps), 1)),
        "perturbation_scale": float(perturbation_scale),
        "base_direct_residual_inf_n": _max_abs(base_residual),
        "rhs_inf_n": _max_abs(rhs),
        "shell_operator_build_seconds": shell_build_seconds,
        "shell_operator_cache_hit": bool(cache_hit),
        "cpu_shell_batch": _summary_seconds(cpu_times),
        "hip_shell_batch_kernel_mean_seconds": hip_kernel_mean_seconds,
        "hip_shell_batch_kernel_speedup_vs_cpu_mean": cpu_mean / max(hip_kernel_mean_seconds, 1.0e-12),
        "hip_subprocess_seconds": hip_subprocess_seconds,
        "max_abs_shell_force_difference_n": max_abs_difference,
        "relative_shell_force_difference_inf": relative_difference_inf,
        "comparison_tolerances": {
            "absolute_tolerance_n": absolute_tolerance_n,
            "relative_tolerance_inf": relative_tolerance_inf,
            "pass_rule": "hip_ok_and_abs_le_tolerance_or_relative_le_tolerance",
        },
        "cpu_shell_force_inf_n": _max_abs(cpu_shell),
        "hip_shell_force_inf_n": _max_abs(hip_shell),
        "shell_meta": shell_meta,
        "build": build,
        "hip": hip_payload,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "Validates native HIP shell CSR batch replay against the G1 CPU shell "
            "operator path. This covers shell internal-force replay only; full "
            "frame+shell+spring residual gate closure remains separate work."
        ),
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--shell-pressure-load-path-policy",
        choices=("all_components", "attached_components_only"),
        default="attached_components_only",
    )
    parser.add_argument("--include-membrane", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--reps", type=int, default=20)
    parser.add_argument("--perturbation-scale", type=float, default=1.0e-6)
    parser.add_argument("--hipcc", type=Path, default=Path("/opt/rocm/bin/hipcc"))
    parser.add_argument("--force-rebuild", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_hip_shell_csr_batch_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        include_membrane=bool(args.include_membrane),
        batch_size=args.batch_size,
        reps=args.reps,
        perturbation_scale=args.perturbation_scale,
        hipcc=args.hipcc,
        force_rebuild=bool(args.force_rebuild),
    )
    print(
        "mgt-hip-shell-csr-batch: "
        f"status={payload['status']} "
        f"diff={payload.get('max_abs_shell_force_difference_n', 0.0):.6g} "
        f"speedup={payload.get('hip_shell_batch_kernel_speedup_vs_cpu_mean', 0.0):.3f}x "
        f"runtime={payload.get('runtime_seconds', 0.0):.3f}s -> {args.output_json}"
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
