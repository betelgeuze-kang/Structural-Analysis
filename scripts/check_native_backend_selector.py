#!/usr/bin/env python3
"""Validate the ABI v1.12 backend selector and frozen HIP compatibility adapter."""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_EXPORTS = {"sa_get_api_v1"}
ADAPTER_EXPORTS = {
    "mgt_rust_hip_full_residual_create",
    "mgt_rust_hip_full_residual_destroy",
    "mgt_rust_hip_full_residual_device_name",
    "mgt_rust_hip_full_residual_eval",
    "mgt_rust_hip_full_residual_ffi_version",
    "mgt_rust_hip_full_residual_last_error",
    "mgt_rust_hip_full_residual_load_library",
}
REQUIRED_TOKENS = {
    "native/cpp/include/structural/abi_v1.h": (
        "SA_ABI_V1_12",
        "SA_CAPABILITY_BACKEND_SELECTOR",
        "SA_API_V1_11_MIN_SIZE ((uint32_t)offsetof(sa_api_v1, backend_get_api))",
        "sa_backend_get_api_fn_v1 backend_get_api",
    ),
    "native/cpp/src/abi/abi_v1.cpp": (
        "full_residual_create_cpu_boundary",
        "full_residual_create_hip_boundary",
        "SA_ERR_BACKEND_UNAVAILABLE",
        "SA_CAPABILITY_BACKEND_SELECTOR",
    ),
    "native/crates/structural-ffi/src/backend.rs": (
        "pub enum ExecutionBackend",
        "pub struct FullResidualContext",
        "PhantomData<Rc<()>>",
        "pub fn evaluate(",
        "&mut self,",
    ),
    "implementation/phase1/mgt_hip_full_residual_ffi/src/lib.rs": (
        'dlsym(handle, c"sa_get_api_v1".as_ptr())',
        "SA_CAPABILITY_BACKEND_SELECTOR",
        "SA_EXECUTION_BACKEND_HIP",
        "catch_unwind",
    ),
    "native/compatibility-owners.json": (
        '"transition_step": "H3"',
        '"legacy_abi_preserved": true',
        '"removal_allowed": false',
    ),
}
FORBIDDEN_ADAPTER_TOKENS = (
    'dlsym(handle, c"mgt_hip_full_residual_create',
    'dlsym(handle, c"mgt_hip_full_residual_eval',
    'dlsym(handle, c"mgt_hip_full_residual_destroy',
    'dlsym(handle, c"mgt_hip_full_residual_device_name',
)


def _exports(path: Path) -> set[str]:
    completed = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        fields[-1]
        for line in completed.stdout.splitlines()
        if (fields := line.split())
    }


def _dynamic_cpu_fail_closed(product: Path, adapter: Path) -> tuple[int, str]:
    library = ctypes.CDLL(str(adapter.resolve()))
    load = library.mgt_rust_hip_full_residual_load_library
    load.argtypes = [ctypes.c_char_p]
    load.restype = ctypes.c_int
    last_error = library.mgt_rust_hip_full_residual_last_error
    last_error.argtypes = []
    last_error.restype = ctypes.c_char_p
    version = library.mgt_rust_hip_full_residual_ffi_version
    version.argtypes = []
    version.restype = ctypes.c_uint32
    if version() != 1:
        return -1, "legacy adapter version is not 1"
    code = int(load(str(product.resolve()).encode("utf-8")))
    raw_message = last_error()
    message = raw_message.decode("utf-8", errors="replace") if raw_message else ""
    return code, message


def check_native_backend_selector(
    root: Path = ROOT,
    *,
    product_library: Path | None = None,
    adapter_library: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    blockers: list[str] = []
    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"backend_selector_source_unreadable:{relative}:{exc}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"backend_selector_token_missing:{relative}:{token}")

    adapter_source = root / "implementation/phase1/mgt_hip_full_residual_ffi/src/lib.rs"
    try:
        adapter_text = adapter_source.read_text(encoding="utf-8")
    except OSError:
        adapter_text = ""
    if adapter_text.count("unsafe { dlsym(") != 1:
        blockers.append("backend_selector_adapter_dlsym_call_count_invalid")
    for token in FORBIDDEN_ADAPTER_TOKENS:
        if token in adapter_text:
            blockers.append(f"backend_selector_adapter_forbidden_symbol_lookup:{token}")

    binary_report: dict[str, Any] | None = None
    if (product_library is None) != (adapter_library is None):
        blockers.append("backend_selector_binary_pair_incomplete")
    elif product_library is not None and adapter_library is not None:
        product = product_library if product_library.is_absolute() else root / product_library
        adapter = adapter_library if adapter_library.is_absolute() else root / adapter_library
        binary_report = {
            "product_library": str(product),
            "adapter_library": str(adapter),
        }
        if not product.is_file():
            blockers.append("backend_selector_product_library_missing")
        if not adapter.is_file():
            blockers.append("backend_selector_adapter_library_missing")
        if product.is_file() and adapter.is_file():
            try:
                product_exports = _exports(product)
                adapter_exports = _exports(adapter)
            except (OSError, subprocess.CalledProcessError) as exc:
                blockers.append(f"backend_selector_export_scan_failed:{exc}")
            else:
                binary_report["product_exports"] = sorted(product_exports)
                binary_report["adapter_exports"] = sorted(adapter_exports)
                if product_exports != PRODUCT_EXPORTS:
                    blockers.append("backend_selector_product_exports_invalid")
                if adapter_exports != ADAPTER_EXPORTS:
                    blockers.append("backend_selector_adapter_exports_invalid")
            try:
                code, message = _dynamic_cpu_fail_closed(product, adapter)
            except (AttributeError, OSError) as exc:
                blockers.append(f"backend_selector_dynamic_smoke_failed:{exc}")
            else:
                binary_report["cpu_only_load_code"] = code
                binary_report["cpu_only_load_error"] = message
                if code != -3 or "without HIP" not in message:
                    blockers.append("backend_selector_cpu_only_adapter_did_not_fail_closed")

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "native-backend-selector-validation.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "binary_validation": binary_report,
        "blockers": blockers,
        "claim_boundary": (
            "This proves the append-only v1.12 selector shape, one-symbol adapter lookup, "
            "frozen adapter exports, and CPU-only no-fallback behavior when binaries are supplied. "
            "It is not an approved HIP C2 receipt or C6 removal evidence."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--product-library", type=Path)
    parser.add_argument("--adapter-library", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = check_native_backend_selector(
        args.root,
        product_library=args.product_library,
        adapter_library=args.adapter_library,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native backend selector: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not report["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
