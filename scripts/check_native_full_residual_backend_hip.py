#!/usr/bin/env python3
"""Validate the product-table full-residual HIP candidate and approved-runner receipt."""

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
    "native/cpp/include/structural/abi_v1.h": (
        "SA_CAPABILITY_BACKEND_SELECTOR",
        "sa_backend_get_api_fn_v1",
        "sa_full_residual_status_v1",
    ),
    "native/cpp/src/hip/full_residual_hip.hip.cpp": (
        "deterministic_full_residual_kernel",
        "validate_full_residual_evaluation",
        "hipStreamSynchronize",
        "STRUCTURAL_FULL_RESIDUAL_HIP_SOURCE_SHA256",
    ),
    "native/cpp/src/abi/abi_v1.cpp": (
        "full_residual_create_hip_boundary",
        "full_residual_hip_device_status",
        "SA_ERR_BACKEND_UNAVAILABLE",
    ),
    "implementation/phase1/mgt_hip_full_residual_ffi/src/lib.rs": (
        'dlsym(handle, c"sa_get_api_v1".as_ptr())',
        "SA_CAPABILITY_BACKEND_SELECTOR",
        "full_residual_evaluate",
    ),
    "native/cpp/tests/hip/full_residual_backend_hip_parity_test.hip.cpp": (
        "CPU/HIP full-residual parity",
        "HIP full-residual repeat is bitwise deterministic",
        'single_entry_symbol\\\":\\\"sa_get_api_v1',
    ),
    ".github/workflows/native-hip-dedicated.yml": (
        "environment: native-hip-approved",
        "runs-on: [self-hosted, linux, x64, rocm, structural-approved]",
        "structural_full_residual_backend_hip_parity_tests",
        "check_native_full_residual_backend_hip.py",
    ),
    "docs/native/full-residual-backend-hip-c2.md": (
        "C2 candidate",
        "native-hip-approved",
        "sa_get_api_v1",
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
    header = (root / "native/cpp/src/hip/full_residual_hip.hpp").read_text(
        encoding="utf-8"
    )
    source = (root / "native/cpp/src/hip/full_residual_hip.hip.cpp").read_text(
        encoding="utf-8"
    )
    return hashlib.sha256((header + source).encode("utf-8")).hexdigest()


def expected_device_library_sha256(path: Path, architecture: str) -> str:
    gfx = architecture.split(":", 1)[0]
    if not gfx.startswith("gfx"):
        raise ValueError("receipt architecture is not a gfx target")
    hashes = "".join(
        _sha256(candidate)
        for candidate in (
            path / "ocml.bc",
            path / "ockl.bc",
            path / f"oclc_isa_version_{gfx[3:]}.bc",
        )
    )
    return hashlib.sha256(hashes.encode("ascii")).hexdigest()


def _positive(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_receipt(
    payload: dict[str, Any], root: Path, device_lib_path: Path
) -> list[str]:
    blockers: list[str] = []
    exact = {
        "schema_version": "native-full-residual-backend-hip-receipt.v1",
        "backend": "amd_rocm_hip",
        "operator_h2d_transfer_count": 10,
        "eval_h2d_transfer_count": 1,
        "eval_d2h_transfer_count": 1,
        "operator_synchronization_count": 1,
        "eval_synchronization_count": 1,
        "kernel_launch_count": 4,
        "fallback_count": 0,
        "fp64": True,
        "deterministic": True,
        "operator_device_resident": True,
        "eval_buffers_reused": True,
        "cpu_hip_parity": True,
        "hip_repeat_bitwise": True,
        "single_entry_symbol": "sa_get_api_v1",
        "parity_pass": True,
    }
    for key, expected in exact.items():
        if payload.get(key) != expected:
            blockers.append(f"full_residual_hip_receipt_value_invalid:{key}")
    for key in (
        "runtime_version",
        "driver_version",
        "operator_h2d_bytes",
        "eval_h2d_bytes",
        "eval_d2h_bytes",
        "device_buffer_bytes",
        "vram_total_bytes",
        "vram_free_before_bytes",
        "vram_free_after_bytes",
    ):
        if not _positive(payload, key):
            blockers.append(f"full_residual_hip_receipt_positive_invalid:{key}")
    for key in (
        "device_name",
        "architecture",
        "compiler_version",
        "compiled_architectures",
    ):
        if not isinstance(payload.get(key), str) or not payload[key]:
            blockers.append(f"full_residual_hip_receipt_string_invalid:{key}")
    device_id = payload.get("device_id")
    if not isinstance(device_id, int) or isinstance(device_id, bool) or device_id != 0:
        blockers.append("full_residual_hip_receipt_device_id_invalid")
    error = payload.get("max_residual_absolute_error")
    if (
        not isinstance(error, (int, float))
        or isinstance(error, bool)
        or error < 0.0
        or error > 2.0e-12
    ):
        blockers.append("full_residual_hip_receipt_parity_tolerance_failed")
    architecture = str(payload.get("architecture", ""))
    compiled = str(payload.get("compiled_architectures", ""))
    if architecture.split(":", 1)[0] not in compiled.split(";"):
        blockers.append("full_residual_hip_runtime_compile_architecture_mismatch")
    if payload.get("kernel_source_sha256") != expected_source_sha256(root):
        blockers.append("full_residual_hip_kernel_source_sha256_mismatch")
    try:
        expected_device = expected_device_library_sha256(device_lib_path, architecture)
    except (OSError, ValueError) as exc:
        blockers.append(f"full_residual_hip_device_library_unreadable:{exc}")
    else:
        if payload.get("device_library_sha256") != expected_device:
            blockers.append("full_residual_hip_device_library_sha256_mismatch")
    total = payload.get("vram_total_bytes")
    resident = payload.get("device_buffer_bytes")
    free_before = payload.get("vram_free_before_bytes")
    free_after = payload.get("vram_free_after_bytes")
    if all(isinstance(value, int) for value in (total, resident, free_before, free_after)):
        if resident >= total or free_before > total or free_after > total:
            blockers.append("full_residual_hip_vram_counters_invalid")
    return blockers


def _approval(root: Path) -> tuple[bool, dict[str, str], list[str]]:
    fields = {
        "github_actions": os.environ.get("GITHUB_ACTIONS", ""),
        "runner_environment": os.environ.get("RUNNER_ENVIRONMENT", ""),
        "approval_environment": os.environ.get("NATIVE_HIP_APPROVAL_ENVIRONMENT", ""),
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "github_sha": os.environ.get("GITHUB_SHA", ""),
        "github_workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", ""),
        "runner_name": os.environ.get("RUNNER_NAME", ""),
    }
    blockers: list[str] = []
    if fields["github_actions"] != "true":
        blockers.append("full_residual_hip_approval_not_github_actions")
    if fields["runner_environment"] != "self-hosted":
        blockers.append("full_residual_hip_approval_runner_not_self_hosted")
    if fields["approval_environment"] != "native-hip-approved":
        blockers.append("full_residual_hip_approval_environment_mismatch")
    if not fields["github_run_id"].isdigit() or int(fields["github_run_id"] or 0) <= 0:
        blockers.append("full_residual_hip_approval_run_id_invalid")
    if "native-hip-dedicated.yml@" not in fields["github_workflow_ref"]:
        blockers.append("full_residual_hip_approval_workflow_ref_invalid")
    if not fields["runner_name"]:
        blockers.append("full_residual_hip_approval_runner_name_missing")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        blockers.append("full_residual_hip_approval_git_head_unreadable")
    else:
        if fields["github_sha"] != head:
            blockers.append("full_residual_hip_approval_sha_mismatch")
    return not blockers, fields, blockers


def check(
    root: Path,
    receipt_path: Path | None,
    device_lib_path: Path,
    require_approved_runner: bool,
) -> dict[str, object]:
    root = root.resolve()
    blockers: list[str] = []
    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"full_residual_hip_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"full_residual_hip_token_missing:{relative}:{token}")
    hip_source = root / "native/cpp/src/hip/full_residual_hip.hip.cpp"
    if hip_source.is_file() and "atomicAdd" in hip_source.read_text(encoding="utf-8"):
        blockers.append("full_residual_hip_nondeterministic_atomic_reduction_present")

    receipt: dict[str, Any] | None = None
    receipt_valid = False
    if receipt_path is not None:
        resolved = receipt_path if receipt_path.is_absolute() else root / receipt_path
        try:
            loaded = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("receipt must be an object")
            receipt = loaded
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"full_residual_hip_receipt_invalid:{exc}")
        else:
            device_path = device_lib_path
            if not device_path.is_absolute():
                device_path = root / device_path
            receipt_blockers = _validate_receipt(receipt, root, device_path)
            blockers.extend(receipt_blockers)
            receipt_valid = not receipt_blockers
    approved, approval_fields, approval_blockers = _approval(root)
    if require_approved_runner:
        blockers.extend(approval_blockers)
        if receipt_path is None:
            blockers.append("full_residual_hip_approved_receipt_required")
    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-full-residual-backend-hip-validation.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "implementation_status": "C2 candidate",
        "authoritative_c2": receipt_valid and approved and require_approved_runner,
        "receipt_valid": receipt_valid,
        "approval_context": approval_fields if require_approved_runner else None,
        "receipt": receipt,
        "blockers": blockers,
        "claim_boundary": (
            "Source and compile checks prove only an H4/C2 candidate. Authoritative C2 requires "
            "a source-bound live receipt from native-hip-approved; this does not close broader "
            "solver C2, checkpoint/product gates, legacy removal, or C6."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--device-lib-path", type=Path, default=DEFAULT_DEVICE_LIB_PATH)
    parser.add_argument("--require-approved-runner", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = check(
        args.root,
        args.receipt,
        args.device_lib_path,
        args.require_approved_runner,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native full-residual HIP contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
