#!/usr/bin/env python3
"""Verify that legacy replay executables are product-library consumers, not kernel owners."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPLAY_SOURCES = {
    "frame_force_batch": Path("implementation/phase1/hip_frame_force_batch_replay.cpp"),
    "shell_csr_batch": Path("implementation/phase1/hip_shell_csr_batch_replay.cpp"),
    "full_residual_batch": Path("implementation/phase1/hip_full_residual_batch_replay.cpp"),
    "full_residual_worker": Path(
        "implementation/phase1/hip_full_residual_resident_worker.cpp"
    ),
}
ADAPTER_HEADER = Path("implementation/phase1/product_full_residual_replay.hpp")
BUILD_HELPER = Path("implementation/phase1/mgt_hip_full_residual_backend.py")
PROBE_BUILDERS = (
    Path("implementation/phase1/run_mgt_hip_frame_force_batch_probe.py"),
    Path("implementation/phase1/run_mgt_hip_shell_csr_batch_probe.py"),
    Path("implementation/phase1/run_mgt_hip_full_residual_batch_probe.py"),
)
CMAKE_TEST_GRAPH = Path("native/cpp/tests/CMakeLists.txt")
SA_EXECUTION_BACKEND_HIP_PY = 2
FORBIDDEN_KERNEL_TOKENS = (
    "__global__",
    "hipLaunchKernel",
    "hipMalloc",
    "hipFree",
    "hipMemcpy",
    "hipMemset",
    "hipDeviceSynchronize",
    "hipGetDevice",
    "hip_runtime.h",
)
FORBIDDEN_DYNAMIC_LOOKUP_TOKENS = ("dlopen", "dlsym", "LoadLibrary", "GetProcAddress")


def _read(path: Path, blockers: list[str], label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"replay_product_link_unreadable:{label}:{exc}")
        return ""


def _binary_contract(path: Path) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    undefined = subprocess.run(
        ["nm", "-D", "--undefined-only", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if undefined.returncode != 0:
        blockers.append(f"binary_nm_failed:{path}:{undefined.returncode}")
        return blockers, []
    sa_symbols = sorted(
        {
            match.group(1)
            for line in undefined.stdout.splitlines()
            if (match := re.search(r"\b(sa_[A-Za-z0-9_]+)(?:@.*)?$", line))
        }
    )
    if sa_symbols != ["sa_get_api_v1"]:
        blockers.append(f"binary_product_symbol_set_mismatch:{path}")
    dynamic = subprocess.run(
        ["readelf", "-d", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if dynamic.returncode != 0:
        blockers.append(f"binary_readelf_failed:{path}:{dynamic.returncode}")
    elif "libstructural_c_abi_v1.so" not in dynamic.stdout:
        blockers.append(f"binary_product_library_dependency_missing:{path}")
    return blockers, sa_symbols


def check_replay_product_link(
    repo_root: Path = ROOT,
    binaries: tuple[Path, ...] = (),
    receipts: tuple[Path, ...] = (),
    require_hip_receipts: bool = False,
) -> dict[str, Any]:
    root = repo_root.resolve()
    blockers: list[str] = []
    header = _read(root / ADAPTER_HEADER, blockers, "adapter_header")
    for token in (
        '#include "structural/abi_v1.h"',
        "sa_get_api_v1",
        "backend_get_api",
        "SA_EXECUTION_BACKEND_HIP",
        "fallback_count",
        "ProductContext",
        "run_self_test",
    ):
        if token not in header:
            blockers.append(f"replay_adapter_header_token_missing:{token}")
    for token in (*FORBIDDEN_KERNEL_TOKENS, *FORBIDDEN_DYNAMIC_LOOKUP_TOKENS):
        if token in header:
            blockers.append(f"replay_adapter_header_forbidden_token:{token}")

    source_checks: dict[str, dict[str, Any]] = {}
    for role, relative_path in REPLAY_SOURCES.items():
        source = _read(root / relative_path, blockers, role)
        forbidden = sorted(
            token
            for token in (*FORBIDDEN_KERNEL_TOKENS, *FORBIDDEN_DYNAMIC_LOOKUP_TOKENS)
            if token in source
        )
        if forbidden:
            blockers.extend(
                f"replay_source_owns_kernel_or_loader:{role}:{token}"
                for token in forbidden
            )
        for token in (
            '#include "product_full_residual_replay.hpp"',
            "replay::ProductContext",
            "replay::run_self_test",
        ):
            if token not in source:
                blockers.append(f"replay_source_product_token_missing:{role}:{token}")
        source_checks[role] = {
            "path": relative_path.as_posix(),
            "forbidden_tokens": forbidden,
            "product_adapter": not forbidden
            and '#include "product_full_residual_replay.hpp"' in source,
        }

    helper = _read(root / BUILD_HELPER, blockers, "build_helper")
    for token in (
        "def build_product_replay_binary(",
        "build_hip_full_residual_ffi_library(",
        '"-std=c++20"',
        '"-lstructural_c_abi_v1"',
        '"-Wl,-rpath,$ORIGIN"',
        '"single_entry_symbol": "sa_get_api_v1"',
    ):
        if token not in helper:
            blockers.append(f"replay_build_helper_token_missing:{token}")
    helper_start = helper.find("def build_product_replay_binary(")
    helper_end = helper.find("def build_hip_full_residual_ffi_library(")
    consumer_build = helper[helper_start:helper_end]
    for token in ('"--offload-arch=', '"-std=c++17"'):
        if token in consumer_build:
            blockers.append(f"replay_consumer_direct_hip_compile:{token}")

    for builder_path in PROBE_BUILDERS:
        builder = _read(root / builder_path, blockers, builder_path.name)
        if "build_product_replay_binary" not in builder:
            blockers.append(f"replay_probe_product_builder_missing:{builder_path}")
        if "--offload-arch" in builder:
            blockers.append(f"replay_probe_direct_hip_compile:{builder_path}")

    cmake = _read(root / CMAKE_TEST_GRAPH, blockers, "cmake_test_graph")
    for source in REPLAY_SOURCES.values():
        if source.name not in cmake:
            blockers.append(f"replay_cmake_source_missing:{source.name}")
    for token in (
        "structural_add_product_replay_consumer",
        "target_link_libraries(",
        "PRIVATE structural_c_abi_v1",
        "--self-test --backend cpu",
    ):
        if token not in cmake:
            blockers.append(f"replay_cmake_product_link_token_missing:{token}")

    binary_symbols: dict[str, list[str]] = {}
    for binary in binaries:
        resolved = binary if binary.is_absolute() else root / binary
        if not resolved.is_file():
            blockers.append(f"replay_binary_missing:{resolved}")
            continue
        binary_blockers, symbols = _binary_contract(resolved)
        blockers.extend(binary_blockers)
        binary_symbols[str(binary)] = symbols

    receipt_roles: dict[str, str] = {}
    for receipt in receipts:
        resolved = receipt if receipt.is_absolute() else root / receipt
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            blockers.append(f"replay_receipt_invalid:{resolved}:{exc}")
            continue
        if not isinstance(payload, dict):
            blockers.append(f"replay_receipt_root_invalid:{resolved}")
            continue
        role = str(payload.get("role", ""))
        receipt_roles[str(receipt)] = role
        expected = {
            "schema_version": "native-replay-product-link.v1",
            "ok": True,
            "single_entry_symbol": "sa_get_api_v1",
            "product_library_linked": True,
            "kernel_owner": "structural_c_abi_v1",
            "backend": "hip",
            "execution_backend": SA_EXECUTION_BACKEND_HIP_PY,
            "fallback_count": 0,
            "fp64": True,
            "deterministic": True,
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                blockers.append(f"replay_receipt_field_mismatch:{resolved}:{key}")
    if require_hip_receipts:
        expected_roles = {
            "frame_force_batch",
            "shell_csr_batch",
            "full_residual_batch",
            "full_residual_resident_worker",
        }
        if set(receipt_roles.values()) != expected_roles:
            blockers.append("replay_approved_hip_receipt_role_set_mismatch")

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "native-replay-product-link-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "single_entry_symbol": "sa_get_api_v1",
        "kernel_owner": "structural_c_abi_v1",
        "replay_sources": source_checks,
        "binary_symbols": binary_symbols,
        "receipt_roles": receipt_roles,
        "blockers": blockers,
        "claim_boundary": (
            "This check proves that the four legacy replay/worker executables compile as "
            "host-side consumers of the v1.12 product backend and own no HIP kernel or "
            "dynamic symbol loader. Approved-device execution freshness remains separate."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--binary", action="append", type=Path, default=[])
    parser.add_argument("--receipt", action="append", type=Path, default=[])
    parser.add_argument("--require-hip-receipts", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_replay_product_link(
        repo_root=args.repo_root,
        binaries=tuple(args.binary),
        receipts=tuple(args.receipt),
        require_hip_receipts=bool(args.require_hip_receipts),
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "native-replay-product-link: "
            f"status={payload['status']} blockers={len(payload['blockers'])}"
        )
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
