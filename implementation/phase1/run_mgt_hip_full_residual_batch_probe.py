#!/usr/bin/env python3
"""Validate a single native HIP full residual batch replay for G1."""

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

from mgt_frame_force_based_assembly import prepack_frame_force_based_assembly  # noqa: E402
from mgt_physical_residual_assembly import assemble_physical_internal_forces_batch  # noqa: E402
from mgt_shell_force_based_assembly import _cached_shell_operator  # noqa: E402
from run_mgt_direct_residual_newton_probe import DEFAULT_CHECKPOINT, PRODUCTIZATION  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_hip_full_residual_composed_probe import _finite_float, _jvp_comparison  # noqa: E402
from run_mgt_residual_batch_replay_probe import (  # noqa: E402
    _candidate_state_batch,
    _max_abs,
    _summary_seconds,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-hip-full-residual-batch-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_hip_full_residual_batch_post_shell_followup66_probe.json"
HIP_SOURCE = PHASE1 / "hip_full_residual_batch_replay.cpp"
HIP_BINARY = PRODUCTIZATION / "bin/hip_full_residual_batch_replay"
ROCM_DEVICE_LIB_PATH = (
    PHASE1 / "third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
)


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


def run_mgt_hip_full_residual_batch_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    shell_pressure_load_path_policy: str = "attached_components_only",
    batch_size: int = 64,
    reps: int = 3,
    perturbation_scale: float = 1.0e-6,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
    residual_tolerance_n: float = 1.0e-3,
) -> dict[str, Any]:
    started = time.perf_counter()
    build = _build_binary(hipcc=hipcc, force_rebuild=force_rebuild)
    if not bool(build.get("ok")):
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "fail",
            "reason": "hip_full_residual_bridge_build_failed",
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
    frame_elements = list(setup_meta["_frame_elements"])
    elem_type_code = np.asarray(setup_meta["_elem_type_code"], dtype=np.int32)
    elem_section_id = np.asarray(setup_meta["_elem_section_id"], dtype=np.int32)
    elem_material_id = np.asarray(setup_meta["_elem_material_id"], dtype=np.int32)
    conn_ptr = np.asarray(setup_meta["_conn_ptr"], dtype=np.int64)
    conn_idx = np.asarray(setup_meta["_conn_idx"], dtype=np.int64)
    section_props = setup_meta["_section_props"]
    material_props = setup_meta["_material_props"]
    plate_thickness_props = setup_meta["_plate_thickness_props"]
    base_axial_forces = setup_meta["_base_axial_forces"]
    spring_stiffness = setup_meta["_spring_stiffness"]
    load_scale = float(setup_meta["load_scale"])
    frame_gravity_load_scale = float(setup_meta["frame_gravity_load_scale"])

    _k, f_ext, free, base_residual, rhs, base_meta = assemble_residual(u0)
    states, state_meta = _candidate_state_batch(
        u0=u0,
        free=free,
        batch_size=batch_size,
        perturbation_scale=perturbation_scale,
    )
    axial_forces = {
        int(elem_id): float(force) * frame_gravity_load_scale * load_scale
        for elem_id, force in base_axial_forces.items()
    }
    prepack_started = time.perf_counter()
    frame_force_cache = prepack_frame_force_based_assembly(
        node_xyz=node_xyz,
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    frame_prepack_seconds = float(time.perf_counter() - prepack_started)

    shell_operator_cache: dict[str, Any] = {}
    shell_started = time.perf_counter()
    shell_stiffness, shell_meta, shell_cache_hit = _cached_shell_operator(
        u=states[0],
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
        shell_operator_cache=shell_operator_cache,
    )
    shell_build_seconds = float(time.perf_counter() - shell_started)
    shell_csr = shell_stiffness.tocsr()
    spring_csr = spring_stiffness.tocsr()

    cpu_batch_times: list[float] = []
    cpu_residual_batch = np.zeros((0, int(free.size)), dtype=np.float64)
    cpu_batch_meta: dict[str, Any] = {}
    for _rep in range(max(int(reps), 1)):
        cpu_started = time.perf_counter()
        cpu_f_int_batch, cpu_batch_meta = assemble_physical_internal_forces_batch(
            u_batch=states,
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            elem_type_code=elem_type_code,
            elem_section_id=elem_section_id,
            elem_material_id=elem_material_id,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            section_props=section_props,
            material_props=material_props,
            plate_thickness_props=plate_thickness_props,
            spring_stiffness=spring_stiffness,
            base_axial_forces=base_axial_forces,
            frame_gravity_load_scale=frame_gravity_load_scale,
            load_scale=load_scale,
            shell_operator_cache=shell_operator_cache,
            frame_force_cache=frame_force_cache,
        )
        cpu_residual_batch = np.asarray(cpu_f_int_batch[:, free] - np.asarray(f_ext[free]), dtype=np.float64)
        cpu_batch_times.append(float(time.perf_counter() - cpu_started))
    cpu_batch_mean = float(np.mean(np.asarray(cpu_batch_times, dtype=np.float64)))

    with tempfile.TemporaryDirectory(prefix="mgt_hip_full_residual_batch_") as tmp_name:
        tmp_dir = Path(tmp_name)
        frame_dofs_path = tmp_dir / "frame_dofs.i64"
        frame_stiffness_path = tmp_dir / "frame_stiffness.f64"
        shell_row_ptr_path = tmp_dir / "shell_row_ptr.i64"
        shell_col_idx_path = tmp_dir / "shell_col_idx.i64"
        shell_values_path = tmp_dir / "shell_values.f64"
        spring_row_ptr_path = tmp_dir / "spring_row_ptr.i64"
        spring_col_idx_path = tmp_dir / "spring_col_idx.i64"
        spring_values_path = tmp_dir / "spring_values.f64"
        states_path = tmp_dir / "states.f64"
        f_ext_path = tmp_dir / "f_ext.f64"
        free_path = tmp_dir / "free.i64"
        hip_output_path = tmp_dir / "hip_full_residual.f64"

        np.asarray(frame_force_cache.dofs, dtype=np.int64).tofile(frame_dofs_path)
        np.asarray(frame_force_cache.element_stiffness, dtype=np.float64).tofile(frame_stiffness_path)
        np.asarray(shell_csr.indptr, dtype=np.int64).tofile(shell_row_ptr_path)
        np.asarray(shell_csr.indices, dtype=np.int64).tofile(shell_col_idx_path)
        np.asarray(shell_csr.data, dtype=np.float64).tofile(shell_values_path)
        np.asarray(spring_csr.indptr, dtype=np.int64).tofile(spring_row_ptr_path)
        np.asarray(spring_csr.indices, dtype=np.int64).tofile(spring_col_idx_path)
        np.asarray(spring_csr.data, dtype=np.float64).tofile(spring_values_path)
        np.asarray(states, dtype=np.float64).tofile(states_path)
        np.asarray(f_ext, dtype=np.float64).tofile(f_ext_path)
        np.asarray(free, dtype=np.int64).tofile(free_path)

        hip_payload, hip_subprocess_seconds = _run_hip_bridge(
            frame_dofs_path=frame_dofs_path,
            frame_stiffness_path=frame_stiffness_path,
            shell_row_ptr_path=shell_row_ptr_path,
            shell_col_idx_path=shell_col_idx_path,
            shell_values_path=shell_values_path,
            spring_row_ptr_path=spring_row_ptr_path,
            spring_col_idx_path=spring_col_idx_path,
            spring_values_path=spring_values_path,
            states_path=states_path,
            f_ext_path=f_ext_path,
            free_path=free_path,
            output_path=hip_output_path,
            frame_element_count=int(frame_force_cache.dofs.shape[0]),
            n_dof=int(states.shape[1]),
            shell_nnz=int(shell_csr.nnz),
            spring_nnz=int(spring_csr.nnz),
            free_count=int(free.size),
            batch_size=int(states.shape[0]),
            reps=max(int(reps), 1),
        )
        if not hip_output_path.exists():
            payload = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "fail",
                "reason": "hip_full_residual_bridge_output_missing",
                "mgt_path": str(mgt_path),
                "checkpoint_npz": str(checkpoint_npz),
                "batch_size": int(states.shape[0]),
                "dof_count": int(u0.size),
                "build": build,
                "hip": hip_payload,
                "runtime_seconds": float(time.perf_counter() - started),
                "claim_boundary": "HIP full residual bridge execution failed before output comparison; no G1 gate claim.",
            }
            if output_json is not None:
                output_json.parent.mkdir(parents=True, exist_ok=True)
                output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return payload
        hip_residual_batch = np.fromfile(hip_output_path, dtype=np.float64).reshape(cpu_residual_batch.shape)

    residual_diff = np.asarray(hip_residual_batch - cpu_residual_batch, dtype=np.float64)
    max_abs_residual_difference = _max_abs(residual_diff)
    relative_residual_difference_inf = max_abs_residual_difference / max(_max_abs(cpu_residual_batch), 1.0)
    jvp = _jvp_comparison(
        cpu_residual=cpu_residual_batch,
        hip_residual=hip_residual_batch,
        state_meta=state_meta,
    )
    kernel_mean_seconds = _finite_float(hip_payload.get("kernel_elapsed_ms_mean"), 0.0) / 1000.0
    absolute_tolerance_n = 2.0e-6
    relative_tolerance_inf = 1.0e-10
    comparison_pass = bool(hip_payload.get("ok") is True) and (
        max_abs_residual_difference <= absolute_tolerance_n
        or relative_residual_difference_inf <= relative_tolerance_inf
    )
    base_cpu_residual_inf = float(np.max(np.abs(cpu_residual_batch[0]))) if cpu_residual_batch.size else 0.0
    base_hip_residual_inf = float(np.max(np.abs(hip_residual_batch[0]))) if hip_residual_batch.size else 0.0
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if comparison_pass else "warn",
        "mgt_path": str(mgt_path),
        "checkpoint_npz": str(checkpoint_npz),
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "batch_size": int(states.shape[0]),
        "dof_count": int(u0.size),
        "free_dof_count": int(free.size),
        "reps": int(max(int(reps), 1)),
        "perturbation_scale": float(perturbation_scale),
        "residual_tolerance_n": float(residual_tolerance_n),
        "base_direct_residual_inf_n": _max_abs(base_residual),
        "base_cpu_batch_residual_inf_n": base_cpu_residual_inf,
        "base_hip_full_residual_inf_n": base_hip_residual_inf,
        "hip_full_residual_gate_ready": bool(base_hip_residual_inf <= float(residual_tolerance_n)),
        "rhs_inf_n": _max_abs(rhs),
        "frame_prepack_seconds": frame_prepack_seconds,
        "shell_operator_build_seconds": shell_build_seconds,
        "shell_operator_cache_hit": bool(shell_cache_hit),
        "cpu_full_residual_batch": _summary_seconds(cpu_batch_times),
        "hip_full_residual_kernel_mean_seconds": kernel_mean_seconds,
        "hip_full_residual_kernel_speedup_vs_cpu_batch_mean": cpu_batch_mean
        / max(kernel_mean_seconds, 1.0e-12),
        "hip_subprocess_seconds": hip_subprocess_seconds,
        "max_abs_residual_difference_n": max_abs_residual_difference,
        "relative_residual_difference_inf": relative_residual_difference_inf,
        "comparison_tolerances": {
            "absolute_tolerance_n": absolute_tolerance_n,
            "relative_tolerance_inf": relative_tolerance_inf,
            "pass_rule": "hip_ok_and_abs_le_tolerance_or_relative_le_tolerance",
        },
        "jvp_comparison": jvp,
        "state_meta_sample": state_meta[: min(len(state_meta), 8)],
        "backend_contract": {
            "full_residual_vector_on_native_hip": True,
            "jvp_available_from_batch_residual_differences": bool(int(states.shape[0]) > 1),
            "uses_native_hip_frame_kernel": True,
            "uses_native_hip_shell_kernel": True,
            "uses_native_hip_spring_kernel": True,
            "subtracts_external_load_on_native_hip": True,
            "returns_free_dof_residual_only": True,
            "single_subprocess_boundary": True,
            "persistent_in_process_worker": False,
            "rust_ffi_worker": False,
        },
        "operator_sizes": {
            "frame_element_count": int(frame_force_cache.dofs.shape[0]),
            "shell_nnz": int(shell_csr.nnz),
            "spring_nnz": int(spring_csr.nnz),
        },
        "base_meta_summary": {
            "residual_only_assembly": bool(base_meta.get("residual_only_assembly")),
            "shell_operator_cache_size": int(base_meta.get("shell_operator_cache_size") or 0),
            "free_dof_count": int(base_meta.get("free_dof_count") or 0),
        },
        "cpu_batch_meta": cpu_batch_meta,
        "shell_meta": shell_meta,
        "build": build,
        "hip": hip_payload,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "This validates a single native HIP subprocess boundary that assembles "
            "the G1 frame+shell+spring full residual and residual-difference JVP "
            "batch for free DOFs. It is stronger than separate component replay, "
            "but it is not yet a persistent in-process Rust/HIP worker and does "
            "not claim residual gate closure."
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
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--perturbation-scale", type=float, default=1.0e-6)
    parser.add_argument("--hipcc", type=Path, default=Path("/opt/rocm/bin/hipcc"))
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_hip_full_residual_batch_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        batch_size=args.batch_size,
        reps=args.reps,
        perturbation_scale=args.perturbation_scale,
        hipcc=args.hipcc,
        force_rebuild=bool(args.force_rebuild),
        residual_tolerance_n=args.residual_tolerance_n,
    )
    print(
        "mgt-hip-full-residual-batch: "
        f"status={payload['status']} "
        f"diff={payload.get('max_abs_residual_difference_n', 0.0):.6g} "
        f"base={payload.get('base_hip_full_residual_inf_n', 0.0):.6g} "
        f"speedup={payload.get('hip_full_residual_kernel_speedup_vs_cpu_batch_mean', 0.0):.3f}x "
        f"runtime={payload.get('runtime_seconds', 0.0):.3f}s -> {args.output_json}"
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
