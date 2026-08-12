#!/usr/bin/env python3
"""Validate the bounded R3 track CPU product path and its fail-closed claim boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

import check_structural_runtime_ffi_r2 as r2


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = r2.DEFAULT_INVENTORY

EXPECTED_R3 = {
    "family": "track_point_load",
    "capability_gate": "C0",
    "cpp_target": "structural_solver_cpu",
    "abi_version": "0x00010002",
    "api_entry": "sa_get_api_v1",
    "api_slot": "track_point_load_solve",
    "legacy_exports_preserved": True,
    "fallback_count": 0,
    "owners": {
        "cpp_cpu_kernel": "native/cpp/src/solver_cpu/track_point_load.cpp",
        "c_abi": "native/cpp/include/structural/abi_v1.h",
        "rust_safe_wrapper": "native/crates/structural-ffi/src/lib.rs",
    },
    "verification": {
        "cpp_unit": "native/cpp/tests/solver_cpu/track_point_load_test.cpp",
        "c_abi_contract": "native/cpp/tests/abi/track_point_load_contract_test.cpp",
        "rust_ffi_parity": "native/crates/structural-ffi/tests/track_point_load_parity.rs",
        "python_boundary": "tests/test_native_track_point_load_python_parity.py",
        "checker": "scripts/check_structural_runtime_ffi_r3.py",
    },
    "parity": {
        "legacy_rust": "pass",
        "python_displacement_residual": "pass",
        "python_rotation_interior": "pass",
        "python_rotation_endpoints": "blocked",
        "python_endpoint_max_abs_delta": 0.00003436580346133486,
        "c1_promoted": False,
        "c2_hip": "open",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _dynamic_exports(path: Path) -> tuple[list[str] | None, str | None]:
    if not path.is_file():
        return None, f"library_missing:{path}"
    completed = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        return None, detail[-1] if detail else f"nm_exit_{completed.returncode}"
    return sorted(line.split()[-1] for line in completed.stdout.splitlines() if line.split()), None


def check_r3(
    repo_root: Path = ROOT,
    inventory_path: Path = DEFAULT_INVENTORY,
    legacy_library: Path | None = None,
    product_library: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    resolved_inventory = (
        inventory_path if inventory_path.is_absolute() else repo_root / inventory_path
    )
    lower_gate = r2.check_r2(repo_root, resolved_inventory, legacy_library)
    blockers = [f"r3_lower_gate:{value}" for value in lower_gate["blockers"]]

    try:
        inventory = _load_json(resolved_inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r3_inventory_invalid:{exc}")
        return _report(blockers, lower_gate, None)
    if inventory.get("transition_step") != "R3":
        blockers.append("r3_inventory_transition_step_invalid")
    r3_inventory = inventory.get("r3_track_point_load")
    if r3_inventory != EXPECTED_R3:
        blockers.append("r3_track_inventory_invalid")

    for group in (EXPECTED_R3["owners"], EXPECTED_R3["verification"]):
        for role, relative_path in group.items():
            if not (repo_root / relative_path).is_file():
                blockers.append(f"r3_owned_file_missing:{role}")

    sources = {
        "cmake": repo_root / "native/cpp/CMakeLists.txt",
        "header": repo_root / "native/cpp/include/structural/abi_v1.h",
        "abi": repo_root / "native/cpp/src/abi/abi_v1.cpp",
        "kernel": repo_root / EXPECTED_R3["owners"]["cpp_cpu_kernel"],
        "rust": repo_root / EXPECTED_R3["owners"]["rust_safe_wrapper"],
    }
    source_text: dict[str, str] = {}
    for role, path in sources.items():
        try:
            source_text[role] = path.read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"r3_source_unreadable:{role}:{exc}")
            source_text[role] = ""
    required_tokens = {
        "cmake": ("add_library(structural_solver_cpu", "structural_solver_cpu structural_c_abi_v1"),
        "header": (
            "#define SA_ABI_V1_2 UINT32_C(0x00010002)",
            "sa_track_point_load_solve_fn_v1 track_point_load_solve",
            "SA_CAPABILITY_TRACK_POINT_LOAD_CPU",
        ),
        "abi": ("track_point_load_boundary", "SA_ERR_NONCONVERGENCE"),
        "kernel": ("solve_track_point_load", "conjugate_gradient"),
        "rust": ("pub fn load_track_point_load", "pub fn solve_track_point_load"),
    }
    for role, tokens in required_tokens.items():
        for token in tokens:
            if token not in source_text[role]:
                blockers.append(f"r3_source_token_missing:{role}:{token}")

    try:
        capabilities = _load_json(repo_root / "native/capabilities.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r3_capabilities_invalid:{exc}")
        capabilities = {}
    capability = capabilities.get("capabilities", {}).get("track_point_load_cpu", {})
    if not isinstance(capability, dict) or capability.get("status") != "implemented":
        blockers.append("r3_track_capability_not_implemented")
    else:
        if capability.get("cutover_gate") != "C0":
            blockers.append("r3_track_capability_overpromoted")
        claim = str(capability.get("claim", ""))
        for boundary in ("blocks C1", "HIP C2", "restart", "product E2E"):
            if boundary not in claim:
                blockers.append(f"r3_track_claim_boundary_missing:{boundary}")

    product_exports: list[str] | None = None
    if product_library is not None:
        resolved_library = (
            product_library if product_library.is_absolute() else repo_root / product_library
        )
        product_exports, export_error = _dynamic_exports(resolved_library)
        if export_error is not None:
            blockers.append(f"r3_product_export_check_failed:{export_error}")
        elif product_exports != ["sa_get_api_v1"]:
            blockers.append("r3_product_export_set_mismatch")

    return _report(blockers, lower_gate, product_exports)


def _report(
    blockers: list[str],
    lower_gate: dict[str, object],
    product_exports: list[str] | None,
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "structural-runtime-ffi-r3-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "lower_gate_pass": lower_gate.get("contract_pass") is True,
        "legacy_exports": lower_gate.get("expected_exports", []),
        "product_exports": product_exports,
        "capability_gate": "C0",
        "blockers": blockers,
        "claim_boundary": (
            "R3 proves one C++ CPU track family, ABI v1.2 and safe Rust compatibility parity. "
            "Python endpoint rotation still blocks C1 and no HIP C2 or runtime cutover is claimed."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--legacy-library", type=Path)
    parser.add_argument("--product-library", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_r3(
        args.repo_root,
        args.inventory,
        args.legacy_library,
        args.product_library,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Structural runtime FFI R3: {payload['status']}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
