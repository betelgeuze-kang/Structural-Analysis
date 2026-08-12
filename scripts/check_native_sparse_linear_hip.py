#!/usr/bin/env python3
"""Validate the bounded native sparse-linear HIP implementation and live receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICE_LIB_PATH = Path(
    "implementation/phase1/third_party/rocm_device_libs/opt/rocm-5.7.1/amdgcn/bitcode"
)

REQUIRED_TOKENS = {
    "native/cmake/StructuralHip.cmake": (
        "STRUCTURAL_HIP_DEVICE_LIB_PATH",
        "--rocm-device-lib-path=",
        'CMAKE_HIP_COMPILER_ID STREQUAL "Clang"',
    ),
    "native/cpp/src/solver_cpu/sparse_linear.hpp": (
        "validate_sparse_spd_problem",
        "CPU and accelerator backends",
    ),
    "native/cpp/CMakeLists.txt": (
        "structural_solver_hip",
        "STRUCTURAL_SPARSE_HIP_SOURCE_SHA256",
        "STRUCTURAL_SPARSE_HIP_DEVICE_LIB_SHA256",
    ),
    "native/cpp/src/hip/sparse_linear_hip.hip.cpp": (
        "sparse_pcg_kernel",
        "single_block_fixed_tree_fp64.v1",
        "validate_sparse_spd_problem",
        "hipStreamSynchronize",
    ),
    "native/cpp/tests/hip/sparse_linear_hip_parity_test.hip.cpp": (
        "max_solution_absolute_error",
        "max_true_residual_absolute_error",
        "exact_initial_profile_count",
        "numerical_status_parity",
        "host_iteration_control_transfer_count",
        'fallback_count\\\":0',
    ),
    ".github/workflows/native-hip-dedicated.yml": (
        "environment: native-hip-approved",
        "runs-on: [self-hosted, linux, x64, rocm, structural-approved]",
        "structural_sparse_linear_hip_parity_tests",
        "check_native_sparse_linear_hip.py",
        "native-sparse-linear-hip-receipt.json",
    ),
    "docs/native/sparse-linear-hip-c2.md": (
        "C2 candidate",
        "native-hip-approved",
        "fallback_count=0",
        "C6",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_source_sha256(root: Path) -> str:
    header = (root / "native/cpp/src/hip/sparse_linear_hip.hpp").read_text(
        encoding="utf-8"
    )
    source = (root / "native/cpp/src/hip/sparse_linear_hip.hip.cpp").read_text(
        encoding="utf-8"
    )
    return hashlib.sha256((header + source).encode("utf-8")).hexdigest()


def expected_device_library_sha256(device_lib_path: Path, architecture: str) -> str:
    suffix = architecture.split(":", 1)[0]
    if not suffix.startswith("gfx"):
        raise ValueError("receipt architecture is not a gfx target")
    files = (
        device_lib_path / "ocml.bc",
        device_lib_path / "ockl.bc",
        device_lib_path / f"oclc_isa_version_{suffix[3:]}.bc",
    )
    hashes = "".join(_sha256(path) for path in files)
    return hashlib.sha256(hashes.encode("ascii")).hexdigest()


def _positive_integer(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_receipt(
    payload: dict[str, Any], root: Path, device_lib_path: Path
) -> list[str]:
    blockers: list[str] = []
    exact_values: dict[str, object] = {
        "schema_version": "native-sparse-linear-hip-receipt.v1",
        "backend": "amd_rocm_hip",
        "reduction_profile": "single_block_fixed_tree_fp64.v1",
        "profile_count": 4,
        "exact_initial_profile_count": 1,
        "failure_profile_count": 4,
        "solve_count": 13,
        "h2d_transfer_count": 53,
        "d2h_transfer_count": 26,
        "synchronization_count": 13,
        "kernel_launch_count": 13,
        "fallback_count": 0,
        "fp64": True,
        "deterministic": True,
        "device_resident_iterations": True,
        "host_intermediate_state_transfer_count": 0,
        "host_iteration_control_transfer_count": 0,
        "iteration_parity": True,
        "numerical_status_parity": True,
        "parity_pass": True,
    }
    for key, expected in exact_values.items():
        if payload.get(key) != expected:
            blockers.append(f"sparse_hip_receipt_value_invalid:{key}")
    for key in (
        "runtime_version",
        "driver_version",
        "h2d_bytes",
        "d2h_bytes",
        "peak_device_buffer_bytes",
        "vram_total_bytes",
        "vram_free_before_bytes",
        "vram_free_after_alloc_bytes",
    ):
        if not _positive_integer(payload, key):
            blockers.append(f"sparse_hip_receipt_positive_integer_invalid:{key}")
    for key in (
        "device_name",
        "architecture",
        "compiler_version",
        "compiled_architectures",
    ):
        if not isinstance(payload.get(key), str) or not payload[key]:
            blockers.append(f"sparse_hip_receipt_string_invalid:{key}")
    device_id = payload.get("device_id")
    if not isinstance(device_id, int) or isinstance(device_id, bool) or device_id < 0:
        blockers.append("sparse_hip_receipt_device_id_invalid")
    architecture = payload.get("architecture")
    compiled = payload.get("compiled_architectures")
    if isinstance(architecture, str) and isinstance(compiled, str):
        if architecture.split(":", 1)[0] not in compiled.split(";"):
            blockers.append("sparse_hip_receipt_runtime_compile_architecture_mismatch")
    tolerances = {
        "max_solution_absolute_error": 2.0e-11,
        "max_true_residual_absolute_error": 2.0e-11,
        "max_metric_absolute_error": 2.0e-10,
    }
    for key, maximum in tolerances.items():
        value = payload.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0.0
            or value > maximum
        ):
            blockers.append(f"sparse_hip_receipt_parity_tolerance_failed:{key}")
    peak = payload.get("peak_device_buffer_bytes")
    total = payload.get("vram_total_bytes")
    free_before = payload.get("vram_free_before_bytes")
    free_after = payload.get("vram_free_after_alloc_bytes")
    if all(isinstance(value, int) for value in (peak, total, free_before, free_after)):
        if peak >= total or free_before > total or free_after > total:
            blockers.append("sparse_hip_receipt_vram_counters_invalid")
    expected_source = expected_source_sha256(root)
    if payload.get("kernel_source_sha256") != expected_source:
        blockers.append("sparse_hip_receipt_kernel_source_sha256_mismatch")
    try:
        expected_device_lib = expected_device_library_sha256(
            device_lib_path, str(architecture)
        )
    except (OSError, ValueError) as exc:
        blockers.append(f"sparse_hip_device_library_unreadable:{exc}")
    else:
        if payload.get("device_library_sha256") != expected_device_lib:
            blockers.append("sparse_hip_receipt_device_library_sha256_mismatch")
    return blockers


def _approved_runner_context(root: Path) -> tuple[bool, dict[str, str], list[str]]:
    fields = {
        "github_actions": os.environ.get("GITHUB_ACTIONS", ""),
        "runner_environment": os.environ.get("RUNNER_ENVIRONMENT", ""),
        "approval_environment": os.environ.get(
            "NATIVE_HIP_APPROVAL_ENVIRONMENT", ""
        ),
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "github_sha": os.environ.get("GITHUB_SHA", ""),
        "github_workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", ""),
        "runner_name": os.environ.get("RUNNER_NAME", ""),
    }
    blockers: list[str] = []
    if fields["github_actions"] != "true":
        blockers.append("sparse_hip_approval_not_github_actions")
    if fields["runner_environment"] != "self-hosted":
        blockers.append("sparse_hip_approval_runner_not_self_hosted")
    if fields["approval_environment"] != "native-hip-approved":
        blockers.append("sparse_hip_approval_environment_mismatch")
    if not fields["github_run_id"].isdigit() or int(fields["github_run_id"] or 0) <= 0:
        blockers.append("sparse_hip_approval_run_id_invalid")
    if "native-hip-dedicated.yml@" not in fields["github_workflow_ref"]:
        blockers.append("sparse_hip_approval_workflow_ref_invalid")
    if not fields["runner_name"]:
        blockers.append("sparse_hip_approval_runner_name_missing")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        blockers.append("sparse_hip_approval_git_head_unreadable")
    else:
        if fields["github_sha"] != head:
            blockers.append("sparse_hip_approval_sha_mismatch")
    return not blockers, fields, blockers


def check_native_sparse_linear_hip(
    repo_root: Path = ROOT,
    *,
    receipt_path: Path | None = None,
    device_lib_path: Path | None = None,
    require_approved_runner: bool = False,
) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"sparse_hip_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"sparse_hip_evidence_token_missing:{relative}:{token}")

    receipt_valid = False
    receipt: dict[str, Any] | None = None
    if receipt_path is not None:
        resolved_receipt = receipt_path if receipt_path.is_absolute() else root / receipt_path
        try:
            loaded = json.loads(resolved_receipt.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("receipt must be an object")
            receipt = loaded
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"sparse_hip_receipt_invalid:{exc}")
        else:
            resolved_device_lib = device_lib_path or DEFAULT_DEVICE_LIB_PATH
            if not resolved_device_lib.is_absolute():
                resolved_device_lib = root / resolved_device_lib
            receipt_blockers = _validate_receipt(receipt, root, resolved_device_lib)
            blockers.extend(receipt_blockers)
            receipt_valid = not receipt_blockers

    approved, approval_fields, approval_blockers = _approved_runner_context(root)
    if require_approved_runner:
        blockers.extend(approval_blockers)
        if receipt_path is None:
            blockers.append("sparse_hip_approved_receipt_required")
    authoritative_c2 = receipt_valid and approved and require_approved_runner
    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-sparse-linear-hip-validation.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "implementation_status": "C2 candidate",
        "authoritative_c2": authoritative_c2,
        "receipt_valid": receipt_valid,
        "approval_context": approval_fields if require_approved_runner else None,
        "receipt": receipt,
        "blockers": blockers,
        "claim_boundary": (
            "A local source-bound live receipt proves only a sparse PCG C2 candidate. "
            "Authoritative C2 additionally requires the protected native-hip-approved "
            "self-hosted workflow context; this does not promote C3, close sparse "
            "checkpoint/product paths, broader Krylov/Newton families, or C6."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--device-lib-path", type=Path)
    parser.add_argument("--require-approved-runner", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = check_native_sparse_linear_hip(
        args.root,
        receipt_path=args.receipt,
        device_lib_path=args.device_lib_path,
        require_approved_runner=args.require_approved_runner,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native sparse HIP contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
