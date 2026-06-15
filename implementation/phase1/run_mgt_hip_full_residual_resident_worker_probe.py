#!/usr/bin/env python3
"""Validate resident native HIP full-residual worker replay for G1."""

from __future__ import annotations

import argparse
import json
import sys
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
from mgt_hip_full_residual_backend import HipFullResidualResidentWorkerBackend  # noqa: E402
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


SCHEMA_VERSION = "mgt-hip-full-residual-resident-worker-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_hip_full_residual_resident_worker_followup373_probe.json"


def _failure_payload(
    *,
    reason: str,
    started: float,
    mgt_path: Path,
    checkpoint_npz: Path,
    output_json: Path | None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "fail",
        "reason": reason,
        "mgt_path": str(mgt_path),
        "checkpoint_npz": str(checkpoint_npz),
        "details": details or {},
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": "Resident HIP worker setup failed; no G1 HIP residency or residual gate claim.",
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def run_mgt_hip_full_residual_resident_worker_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    shell_pressure_load_path_policy: str = "structural_components_only",
    batch_size: int = 4,
    reps: int = 3,
    perturbation_scale: float = 1.0e-6,
    hipcc: Path = Path("/opt/rocm/bin/hipcc"),
    force_rebuild: bool = False,
    residual_tolerance_n: float = 1.0e-3,
) -> dict[str, Any]:
    started = time.perf_counter()
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

    try:
        with HipFullResidualResidentWorkerBackend.prepare(
            frame_dofs=frame_force_cache.dofs,
            frame_stiffness=frame_force_cache.element_stiffness,
            shell_csr=shell_csr,
            spring_csr=spring_csr,
            f_ext=f_ext,
            free=free,
            hipcc=hipcc,
            force_rebuild=bool(force_rebuild),
        ) as worker:
            resident_residual_first, resident_meta_first = worker.evaluate(states, reps=reps)
            resident_residual_second, resident_meta_second = worker.evaluate(states, reps=reps)
    except Exception as exc:  # pragma: no cover - captured in probe JSON on non-HIP hosts
        return _failure_payload(
            reason="hip_full_residual_resident_worker_failed",
            started=started,
            mgt_path=mgt_path,
            checkpoint_npz=checkpoint_npz,
            output_json=output_json,
            details={"error": str(exc)},
        )

    residual_diff = np.asarray(resident_residual_second - cpu_residual_batch, dtype=np.float64)
    first_second_diff = np.asarray(resident_residual_second - resident_residual_first, dtype=np.float64)
    max_abs_residual_difference = _max_abs(residual_diff)
    max_abs_repeat_difference = _max_abs(first_second_diff)
    relative_residual_difference_inf = max_abs_residual_difference / max(_max_abs(cpu_residual_batch), 1.0)
    jvp = _jvp_comparison(
        cpu_residual=cpu_residual_batch,
        hip_residual=resident_residual_second,
        state_meta=state_meta,
    )
    kernel_mean_seconds = _finite_float(resident_meta_second.get("hip_kernel_mean_seconds"), 0.0)
    absolute_tolerance_n = 2.0e-6
    relative_tolerance_inf = 1.0e-10
    comparison_pass = (
        max_abs_residual_difference <= absolute_tolerance_n
        or relative_residual_difference_inf <= relative_tolerance_inf
    )
    base_cpu_residual_inf = float(np.max(np.abs(cpu_residual_batch[0]))) if cpu_residual_batch.size else 0.0
    base_resident_residual_inf = (
        float(np.max(np.abs(resident_residual_second[0]))) if resident_residual_second.size else 0.0
    )
    worker_pid_stable = bool(
        resident_meta_first.get("worker_pid") == resident_meta_second.get("worker_pid")
        and int(resident_meta_second.get("worker_evaluation_count") or 0) == 2
    )
    residency_pass = bool(
        worker_pid_stable
        and resident_meta_first.get("operator_buffers_device_resident")
        and resident_meta_second.get("operator_buffers_device_resident")
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if comparison_pass and residency_pass else "warn",
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
        "base_resident_worker_residual_inf_n": base_resident_residual_inf,
        "resident_worker_residual_gate_ready": bool(base_resident_residual_inf <= float(residual_tolerance_n)),
        "rhs_inf_n": _max_abs(rhs),
        "frame_prepack_seconds": frame_prepack_seconds,
        "shell_operator_build_seconds": shell_build_seconds,
        "shell_operator_cache_hit": bool(shell_cache_hit),
        "cpu_full_residual_batch": _summary_seconds(cpu_batch_times),
        "resident_worker_kernel_mean_seconds": kernel_mean_seconds,
        "resident_worker_kernel_speedup_vs_cpu_batch_mean": cpu_batch_mean / max(kernel_mean_seconds, 1.0e-12),
        "resident_worker_roundtrip_seconds_second_eval": float(
            resident_meta_second.get("worker_roundtrip_seconds") or 0.0
        ),
        "worker_pid_stable_across_evaluations": worker_pid_stable,
        "resident_worker_evaluation_count": int(resident_meta_second.get("worker_evaluation_count") or 0),
        "operator_buffers_device_resident": bool(resident_meta_second.get("operator_buffers_device_resident")),
        "max_abs_residual_difference_n": max_abs_residual_difference,
        "max_abs_repeat_difference_n": max_abs_repeat_difference,
        "relative_residual_difference_inf": relative_residual_difference_inf,
        "comparison_tolerances": {
            "absolute_tolerance_n": absolute_tolerance_n,
            "relative_tolerance_inf": relative_tolerance_inf,
            "pass_rule": "resident_ok_and_abs_le_tolerance_or_relative_le_tolerance",
        },
        "jvp_comparison": jvp,
        "backend_contract": {
            "full_residual_vector_on_native_hip": True,
            "jvp_available_from_batch_residual_differences": bool(int(states.shape[0]) > 1),
            "uses_native_hip_frame_kernel": True,
            "uses_native_hip_shell_kernel": True,
            "uses_native_hip_spring_kernel": True,
            "subtracts_external_load_on_native_hip": True,
            "returns_free_dof_residual_only": True,
            "single_subprocess_boundary": False,
            "persistent_process_worker": True,
            "operator_buffers_device_resident": bool(resident_meta_second.get("operator_buffers_device_resident")),
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
        "resident_worker_first_meta": resident_meta_first,
        "resident_worker_second_meta": resident_meta_second,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": (
            "This validates a long-lived native HIP process worker for G1 full "
            "residual/JVP batch replay: operator buffers stay resident across two "
            "evaluations with the same worker PID. It narrows the production HIP "
            "lane gap, but does not yet claim an in-process Rust FFI worker or "
            "material Newton consistency closure."
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
        choices=("all_components", "attached_components_only", "structural_components_only"),
        default="structural_components_only",
    )
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--perturbation-scale", type=float, default=1.0e-6)
    parser.add_argument("--hipcc", type=Path, default=Path("/opt/rocm/bin/hipcc"))
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--residual-tolerance-n", type=float, default=1.0e-3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_mgt_hip_full_residual_resident_worker_probe(
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
        "mgt-hip-full-residual-resident-worker: "
        f"status={payload['status']} "
        f"diff={payload.get('max_abs_residual_difference_n', 0.0):.6g} "
        f"base={payload.get('base_resident_worker_residual_inf_n', 0.0):.6g} "
        f"resident={payload.get('operator_buffers_device_resident', False)} "
        f"evals={payload.get('resident_worker_evaluation_count', 0)} "
        f"speedup={payload.get('resident_worker_kernel_speedup_vs_cpu_batch_mean', 0.0):.3f}x "
        f"runtime={payload.get('runtime_seconds', 0.0):.3f}s -> {args.output_json}"
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
