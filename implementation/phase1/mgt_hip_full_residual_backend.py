#!/usr/bin/env python3
"""Reusable native HIP full-residual batch backend for G1 probes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

PHASE1 = Path(__file__).resolve().parent
PRODUCTIZATION = PHASE1 / "release_evidence" / "productization"
HIP_SOURCE = PHASE1 / "hip_full_residual_batch_replay.cpp"
HIP_BINARY = PRODUCTIZATION / "bin/hip_full_residual_batch_replay"
ROCM_DEVICE_LIB_PATH = (
    PHASE1 / "third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
)


def build_hip_full_residual_binary(
    *,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
) -> dict[str, Any]:
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


def _run_hip_full_residual_bridge(
    *,
    frame_dofs_path: Path,
    frame_stiffness_path: Path,
    shell_row_ptr_path: Path,
    shell_col_idx_path: Path,
    shell_values_path: Path,
    spring_row_ptr_path: Path,
    spring_col_idx_path: Path,
    spring_values_path: Path,
    states_path: Path,
    f_ext_path: Path,
    free_path: Path,
    output_path: Path,
    frame_element_count: int,
    n_dof: int,
    shell_nnz: int,
    spring_nnz: int,
    free_count: int,
    batch_size: int,
    reps: int,
) -> tuple[dict[str, Any], float]:
    command = [
        str(HIP_BINARY),
        "--frame-dofs",
        str(frame_dofs_path),
        "--frame-stiffness",
        str(frame_stiffness_path),
        "--shell-row-ptr",
        str(shell_row_ptr_path),
        "--shell-col-idx",
        str(shell_col_idx_path),
        "--shell-values",
        str(shell_values_path),
        "--spring-row-ptr",
        str(spring_row_ptr_path),
        "--spring-col-idx",
        str(spring_col_idx_path),
        "--spring-values",
        str(spring_values_path),
        "--states",
        str(states_path),
        "--f-ext",
        str(f_ext_path),
        "--free",
        str(free_path),
        "--output",
        str(output_path),
        "--frame-element-count",
        str(frame_element_count),
        "--n-dof",
        str(n_dof),
        "--shell-nnz",
        str(shell_nnz),
        "--spring-nnz",
        str(spring_nnz),
        "--free-count",
        str(free_count),
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


@dataclass
class HipFullResidualBatchBackend:
    """Prepared file-backed HIP residual evaluator with reusable operator buffers."""

    temp_dir: tempfile.TemporaryDirectory[str]
    frame_dofs_path: Path
    frame_stiffness_path: Path
    shell_row_ptr_path: Path
    shell_col_idx_path: Path
    shell_values_path: Path
    spring_row_ptr_path: Path
    spring_col_idx_path: Path
    spring_values_path: Path
    f_ext_path: Path
    free_path: Path
    frame_element_count: int
    n_dof: int
    shell_nnz: int
    spring_nnz: int
    free_count: int
    build: dict[str, Any]
    operator_write_seconds: float

    @classmethod
    def prepare(
        cls,
        *,
        frame_dofs: np.ndarray,
        frame_stiffness: np.ndarray,
        shell_csr: Any,
        spring_csr: Any,
        f_ext: np.ndarray,
        free: np.ndarray,
        hipcc: Path = Path("/opt/rocm/bin/hipcc"),
        force_rebuild: bool = False,
    ) -> "HipFullResidualBatchBackend":
        build = build_hip_full_residual_binary(hipcc=hipcc, force_rebuild=force_rebuild)
        if not bool(build.get("ok")):
            raise RuntimeError("hip full residual binary build failed")
        temp_dir = tempfile.TemporaryDirectory(prefix="mgt_hip_full_residual_backend_")
        root = Path(temp_dir.name)
        started = time.perf_counter()
        frame_dofs_path = root / "frame_dofs.i64"
        frame_stiffness_path = root / "frame_stiffness.f64"
        shell_row_ptr_path = root / "shell_row_ptr.i64"
        shell_col_idx_path = root / "shell_col_idx.i64"
        shell_values_path = root / "shell_values.f64"
        spring_row_ptr_path = root / "spring_row_ptr.i64"
        spring_col_idx_path = root / "spring_col_idx.i64"
        spring_values_path = root / "spring_values.f64"
        f_ext_path = root / "f_ext.f64"
        free_path = root / "free.i64"
        np.asarray(frame_dofs, dtype=np.int64).tofile(frame_dofs_path)
        np.asarray(frame_stiffness, dtype=np.float64).tofile(frame_stiffness_path)
        np.asarray(shell_csr.indptr, dtype=np.int64).tofile(shell_row_ptr_path)
        np.asarray(shell_csr.indices, dtype=np.int64).tofile(shell_col_idx_path)
        np.asarray(shell_csr.data, dtype=np.float64).tofile(shell_values_path)
        np.asarray(spring_csr.indptr, dtype=np.int64).tofile(spring_row_ptr_path)
        np.asarray(spring_csr.indices, dtype=np.int64).tofile(spring_col_idx_path)
        np.asarray(spring_csr.data, dtype=np.float64).tofile(spring_values_path)
        np.asarray(f_ext, dtype=np.float64).tofile(f_ext_path)
        np.asarray(free, dtype=np.int64).tofile(free_path)
        return cls(
            temp_dir=temp_dir,
            frame_dofs_path=frame_dofs_path,
            frame_stiffness_path=frame_stiffness_path,
            shell_row_ptr_path=shell_row_ptr_path,
            shell_col_idx_path=shell_col_idx_path,
            shell_values_path=shell_values_path,
            spring_row_ptr_path=spring_row_ptr_path,
            spring_col_idx_path=spring_col_idx_path,
            spring_values_path=spring_values_path,
            f_ext_path=f_ext_path,
            free_path=free_path,
            frame_element_count=int(np.asarray(frame_dofs).shape[0]),
            n_dof=int(np.asarray(f_ext).size),
            shell_nnz=int(shell_csr.nnz),
            spring_nnz=int(spring_csr.nnz),
            free_count=int(np.asarray(free).size),
            build=build,
            operator_write_seconds=float(time.perf_counter() - started),
        )

    def evaluate(self, states: np.ndarray, *, reps: int = 1) -> tuple[np.ndarray, dict[str, Any]]:
        state_batch = np.asarray(states, dtype=np.float64)
        if state_batch.ndim != 2:
            raise ValueError("states must be a 2D array shaped (batch, n_dof)")
        if int(state_batch.shape[1]) != int(self.n_dof):
            raise ValueError(f"state n_dof {state_batch.shape[1]} does not match backend n_dof {self.n_dof}")
        root = Path(self.temp_dir.name)
        states_path = root / "states.f64"
        output_path = root / "hip_full_residual.f64"
        np.asarray(state_batch, dtype=np.float64).tofile(states_path)
        hip_payload, subprocess_seconds = _run_hip_full_residual_bridge(
            frame_dofs_path=self.frame_dofs_path,
            frame_stiffness_path=self.frame_stiffness_path,
            shell_row_ptr_path=self.shell_row_ptr_path,
            shell_col_idx_path=self.shell_col_idx_path,
            shell_values_path=self.shell_values_path,
            spring_row_ptr_path=self.spring_row_ptr_path,
            spring_col_idx_path=self.spring_col_idx_path,
            spring_values_path=self.spring_values_path,
            states_path=states_path,
            f_ext_path=self.f_ext_path,
            free_path=self.free_path,
            output_path=output_path,
            frame_element_count=self.frame_element_count,
            n_dof=self.n_dof,
            shell_nnz=self.shell_nnz,
            spring_nnz=self.spring_nnz,
            free_count=self.free_count,
            batch_size=int(state_batch.shape[0]),
            reps=max(int(reps), 1),
        )
        if not output_path.exists():
            raise RuntimeError(f"hip full residual output missing: {hip_payload}")
        residual = np.fromfile(output_path, dtype=np.float64).reshape(
            (int(state_batch.shape[0]), int(self.free_count))
        )
        meta = {
            "backend": "native_hip_full_residual_batch",
            "single_subprocess_boundary": True,
            "persistent_in_process_worker": False,
            "batch_size": int(state_batch.shape[0]),
            "free_dof_count": int(self.free_count),
            "operator_write_seconds": float(self.operator_write_seconds),
            "hip_subprocess_seconds": float(subprocess_seconds),
            "hip_kernel_mean_seconds": float(hip_payload.get("kernel_elapsed_ms_mean") or 0.0) / 1000.0,
            "build": self.build,
            "hip": hip_payload,
            "operator_sizes": {
                "frame_element_count": int(self.frame_element_count),
                "shell_nnz": int(self.shell_nnz),
                "spring_nnz": int(self.spring_nnz),
            },
        }
        return np.asarray(residual, dtype=np.float64), meta
