#!/usr/bin/env python3
"""Build the solver runtime backend policy receipt for productization evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "solver-runtime-backend-policy.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_solver_runtime_backend_policy(*, productization_dir: Path = PRODUCTIZATION) -> dict[str, Any]:
    rocm_receipt = _load(productization_dir / "gpu_rocm_workstation_receipt.json")
    rocm_probe = _load(productization_dir / "mgt_rocm_sparse_solver_probe.json")
    direct_residual = _load(productization_dir / "mgt_direct_residual_newton_probe.json")

    torch_rocm = rocm_receipt.get("torch_rocm_probe")
    if not isinstance(torch_rocm, dict):
        torch_rocm = {}
    tool_paths = rocm_receipt.get("tool_paths")
    if not isinstance(tool_paths, dict):
        tool_paths = {}

    rocm_hardware_ready = bool(rocm_receipt.get("rocm_hardware_ready"))
    torch_rocm_runtime_ready = bool(rocm_receipt.get("torch_rocm_runtime_ready"))
    target_hardware_match = bool(rocm_receipt.get("target_hardware_match"))
    rocm_sparse_probe_present = rocm_probe.get("schema_version") == "mgt-rocm-sparse-solver-probe.v1"
    direct_residual_present = (
        direct_residual.get("schema_version") == "mgt-direct-residual-newton-probe.v1"
    )

    official_backend = "amd_rocm_hip"
    gpu_required_for_closure = True
    cpu_diagnostic_promotes_solver_closure = False
    cpu_fallback_allowed_for_official_solver_closure = False
    cpu_solver_fallback_detected = False
    nvidia_smi_required = False
    rocm_closure_ready = bool(rocm_probe.get("rocm_sparse_solver_probe_ready"))
    torch_device_label = torch_rocm.get("torch_device_tensor_device")
    torch_device_label_is_rocm_compat_alias = (
        bool(torch_rocm.get("torch_version_hip"))
        and isinstance(torch_device_label, str)
        and torch_device_label.startswith("cuda")
    )

    blockers: list[str] = []
    if not rocm_hardware_ready:
        blockers.append("rocm_hardware_not_ready")
    if not torch_rocm_runtime_ready:
        blockers.append("torch_rocm_runtime_not_ready")
    if not target_hardware_match:
        blockers.append("target_6900xt_hardware_not_matched")
    if not rocm_sparse_probe_present:
        blockers.append("mgt_rocm_sparse_solver_probe_missing")
    if not direct_residual_present:
        blockers.append("mgt_direct_residual_diagnostic_missing")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if not blockers else "blocked",
        "official_solver_compute_backend": official_backend,
        "official_solver_backend": official_backend,
        "official_solver_backend_family": "rocm_hip",
        "official_gpu_device_label_policy": rocm_receipt.get("pytorch_device_label_policy"),
        "gpu_required_for_commercial_solver_closure": gpu_required_for_closure,
        "nvidia_smi_required": nvidia_smi_required,
        "nvidia_smi_detected": bool(tool_paths.get("nvidia_smi")),
        "rocm_smi_detected": bool(tool_paths.get("rocm_smi")),
        "rocminfo_detected": bool(tool_paths.get("rocminfo")),
        "hipcc_detected": bool(tool_paths.get("hipcc")),
        "torch_version": torch_rocm.get("torch_version"),
        "torch_version_hip": torch_rocm.get("torch_version_hip"),
        "torch_device_label": torch_device_label,
        "torch_device_label_is_pytorch_rocm_compat_alias": torch_device_label_is_rocm_compat_alias,
        "device_names": rocm_receipt.get("device_names") or torch_rocm.get("device_names") or [],
        "gfx_targets": rocm_receipt.get("gfx_targets") or [],
        "rocm_hardware_ready": rocm_hardware_ready,
        "torch_rocm_runtime_ready": torch_rocm_runtime_ready,
        "target_hardware_match": target_hardware_match,
        "rocm_sparse_probe_present": rocm_sparse_probe_present,
        "rocm_sparse_solver_probe_ready": rocm_closure_ready,
        "line_frame_rocm_sparse_solver_ready": bool(
            rocm_probe.get("line_frame_rocm_sparse_solver_ready")
        ),
        "shell_coupled_rocm_sparse_solver_ready": bool(
            rocm_probe.get("surface_shell_rocm_sparse_equilibrium_ready")
            and rocm_probe.get("coupled_frame_shell_rocm_sparse_equilibrium_ready")
        ),
        "cpu_diagnostic_artifacts": [
            {
                "artifact": "mgt_direct_residual_newton_probe.json",
                "present": direct_residual_present,
                "status": direct_residual.get("status"),
                "purpose": "physical_residual_diagnostic_only",
                "promotes_solver_closure": cpu_diagnostic_promotes_solver_closure,
            }
        ],
        "cpu_diagnostic_promotes_solver_closure": cpu_diagnostic_promotes_solver_closure,
        "cpu_solver_fallback_detected": cpu_solver_fallback_detected,
        "cpu_fallback_allowed_for_official_solver_closure": cpu_fallback_allowed_for_official_solver_closure,
        "cpu_reference_allowed_for_validation_replay": True,
        "claim_boundary": (
            "Commercial solver closure on this workstation is an AMD ROCm/HIP lane. "
            "CPU direct-residual receipts may diagnose physics gaps but cannot promote G1/G9 "
            "solver closure. CPU reference solutions inside ROCm receipts are validation replay "
            "references only, not accepted fallback solver backends."
        ),
        "blockers": blockers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PRODUCTIZATION / "solver_runtime_backend_policy.json",
    )
    args = parser.parse_args(argv)
    payload = build_solver_runtime_backend_policy(productization_dir=args.productization_dir)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"solver-runtime-backend-policy: {payload['status']} -> {args.output_json}")
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
