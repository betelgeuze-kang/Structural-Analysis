#!/usr/bin/env python3
"""Validate bounded native distribution E2E receipts without promoting C6."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
EXPECTED_KEYS = {
    "schema_version",
    "backend_profile",
    "linkage",
    "release_id",
    "source_sha256",
    "bundle_manifest_sha256",
    "installed_backend_receipt_sha256",
    "c2_receipt_sha256",
    "approved_device_runner",
    "single_product_abi",
    "python_lookup_count",
    "node_lookup_count",
    "install_passed",
    "update_passed",
    "rollback_passed",
    "package_consumer_passed",
    "workbench_restart_passed",
    "workbench_direct_parity_passed",
    "result_ir_sha256",
    "report_pdf_sha256",
    "fallback_count",
    "authority",
}
INSTALLED_BACKEND_KEYS = {
    "schema_version",
    "backend_profile",
    "device_name",
    "cpu_backend",
    "execution_backend",
    "device_id",
    "cpu_backend_parity",
    "repeat_bitwise",
    "fp64",
    "deterministic",
    "fallback_count",
    "operator_device_resident",
    "h2d_bytes",
    "d2h_bytes",
    "synchronization_count",
    "kernel_launch_count",
    "device_buffer_bytes",
}


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("receipt must be a JSON object")
    return payload


def validate(
    payload: dict[str, Any],
    *,
    manifest: Path | None,
    installed_backend_receipt: Path | None,
    c2_receipt: Path | None,
    require_backend: str | None,
    require_authority: bool,
) -> list[str]:
    errors: list[str] = []
    if set(payload) != EXPECTED_KEYS:
        errors.append("receipt keys differ from the exact v1 contract")
    if payload.get("schema_version") != "structural-native-distribution-e2e.v1":
        errors.append("schema_version must be structural-native-distribution-e2e.v1")
    backend = payload.get("backend_profile")
    if backend not in {"cpu_only", "rocm"}:
        errors.append("backend_profile must be cpu_only or rocm")
    if require_backend is not None and backend != require_backend:
        errors.append(f"backend_profile must be {require_backend}")
    linkage = payload.get("linkage")
    if linkage not in {"shared", "static"}:
        errors.append("linkage must be shared or static")
    if backend == "rocm" and linkage != "shared":
        errors.append("ROCm distribution receipt must use shared linkage")
    for name in (
        "source_sha256",
        "bundle_manifest_sha256",
        "result_ir_sha256",
        "report_pdf_sha256",
        "installed_backend_receipt_sha256",
    ):
        if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
            errors.append(f"{name} must be a lowercase SHA-256 identity")
    for name in (
        "single_product_abi",
        "install_passed",
        "update_passed",
        "rollback_passed",
        "package_consumer_passed",
        "workbench_restart_passed",
        "workbench_direct_parity_passed",
    ):
        if payload.get(name) is not True:
            errors.append(f"{name} must be true")
    for name in ("python_lookup_count", "node_lookup_count", "fallback_count"):
        if type(payload.get(name)) is not int or payload[name] != 0:
            errors.append(f"{name} must be integer zero")
    expected_authority = "hosted_cpu_c5" if backend == "cpu_only" else "approved_rocm_c5"
    if payload.get("authority") != expected_authority:
        errors.append(f"authority must be {expected_authority} for {backend}")
    if not isinstance(payload.get("release_id"), str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,128}", payload["release_id"]
    ):
        errors.append("release_id is not a portable bounded token")
    if backend == "cpu_only":
        if payload.get("approved_device_runner") is not False:
            errors.append("CPU receipt approved_device_runner must be false")
        if payload.get("c2_receipt_sha256") is not None:
            errors.append("CPU receipt must not claim a C2 device receipt")
    else:
        if payload.get("approved_device_runner") is not True:
            errors.append("ROCm receipt approved_device_runner must be true")
        if not isinstance(payload.get("c2_receipt_sha256"), str) or not SHA256.fullmatch(
            payload["c2_receipt_sha256"]
        ):
            errors.append("ROCm c2_receipt_sha256 must be a SHA-256 identity")
    if installed_backend_receipt is not None:
        digest = "sha256:" + hashlib.sha256(installed_backend_receipt.read_bytes()).hexdigest()
        if payload.get("installed_backend_receipt_sha256") != digest:
            errors.append("installed backend receipt hash does not match")
        installed = read_json(installed_backend_receipt)
        if set(installed) != INSTALLED_BACKEND_KEYS:
            errors.append("installed backend receipt keys differ from the exact v1 contract")
        if installed.get("schema_version") != "structural-native-installed-backend.v1":
            errors.append("installed backend receipt schema is invalid")
        if installed.get("backend_profile") != backend:
            errors.append("installed backend receipt profile does not match")
        for name in ("cpu_backend_parity", "repeat_bitwise", "fp64", "deterministic"):
            if installed.get(name) is not True:
                errors.append(f"installed backend {name} must be true")
        if installed.get("fallback_count") != 0:
            errors.append("installed backend fallback_count must be zero")
        if installed.get("cpu_backend") != 1:
            errors.append("installed backend CPU reference identity must be 1")
        if backend == "cpu_only":
            expected_installed = {
                "execution_backend": 1,
                "device_id": -1,
                "operator_device_resident": False,
                "h2d_bytes": 0,
                "d2h_bytes": 0,
                "synchronization_count": 0,
                "kernel_launch_count": 0,
                "device_buffer_bytes": 0,
            }
            for name, expected in expected_installed.items():
                if installed.get(name) != expected:
                    errors.append(f"installed CPU backend {name} is invalid")
        else:
            expected_installed = {
                "execution_backend": 2,
                "device_id": 0,
                "operator_device_resident": True,
            }
            for name, expected in expected_installed.items():
                if installed.get(name) != expected:
                    errors.append(f"installed ROCm backend {name} is invalid")
            for name in (
                "h2d_bytes",
                "d2h_bytes",
                "synchronization_count",
                "kernel_launch_count",
                "device_buffer_bytes",
            ):
                value = installed.get(name)
                if type(value) is not int or value <= 0:
                    errors.append(f"installed ROCm backend {name} must be positive")
    if c2_receipt is not None:
        digest = "sha256:" + hashlib.sha256(c2_receipt.read_bytes()).hexdigest()
        if payload.get("c2_receipt_sha256") != digest:
            errors.append("C2 receipt hash does not match")
        c2 = read_json(c2_receipt)
        expected_c2 = {
            "schema_version": "native-full-residual-backend-hip-receipt.v1",
            "backend": "amd_rocm_hip",
            "fallback_count": 0,
            "fp64": True,
            "deterministic": True,
            "operator_device_resident": True,
            "cpu_hip_parity": True,
            "hip_repeat_bitwise": True,
            "single_entry_symbol": "sa_get_api_v1",
            "parity_pass": True,
        }
        for name, expected in expected_c2.items():
            if c2.get(name) != expected:
                errors.append(f"C2 receipt {name} is invalid")
    if manifest is not None:
        digest = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
        if payload.get("bundle_manifest_sha256") != digest:
            errors.append("bundle_manifest_sha256 does not match the supplied manifest")
        manifest_payload = read_json(manifest)
        expected_profile = "cpu_only" if backend == "cpu_only" else "rocm"
        if manifest_payload.get("backend_profile") != expected_profile:
            errors.append("receipt backend does not match distribution manifest")
        if manifest_payload.get("release_id") != payload.get("release_id"):
            errors.append("receipt release does not match distribution manifest")
        if manifest_payload.get("source_sha256") != payload.get("source_sha256"):
            errors.append("receipt source identity does not match distribution manifest")
        expected_execution_authority = (
            "cpu_build_candidate" if backend == "cpu_only" else "rocm_build_candidate"
        )
        if manifest_payload.get("execution_authority") != expected_execution_authority:
            errors.append("distribution manifest has an invalid build-time authority")
    if require_authority:
        if manifest is None:
            errors.append("authoritative validation requires the distribution manifest")
        if installed_backend_receipt is None:
            errors.append("authoritative validation requires the installed backend receipt")
        if backend == "rocm" and c2_receipt is None:
            errors.append("authoritative ROCm validation requires the C2 execution receipt")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--installed-backend-receipt", type=Path)
    parser.add_argument("--c2-receipt", type=Path)
    parser.add_argument("--require-backend", choices=("cpu_only", "rocm"))
    parser.add_argument("--require-authority", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        payload = read_json(arguments.receipt)
        errors = validate(
            payload,
            manifest=arguments.manifest,
            installed_backend_receipt=arguments.installed_backend_receipt,
            c2_receipt=arguments.c2_receipt,
            require_backend=arguments.require_backend,
            require_authority=arguments.require_authority,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors = [str(error)]
        payload = {}
    result = {
        "schema_version": "structural-native-distribution-receipt-validation.v1",
        "valid": not errors,
        "authoritative": bool(arguments.require_authority and not errors),
        "backend_profile": payload.get("backend_profile"),
        "authority": payload.get("authority"),
        "errors": errors,
    }
    if arguments.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    elif errors:
        for error in errors:
            print(error, file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
