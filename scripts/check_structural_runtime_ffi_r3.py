#!/usr/bin/env python3
"""Validate bounded R3 CPU product slices and their fail-closed claim boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import check_structural_runtime_ffi_r2 as r2


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = r2.DEFAULT_INVENTORY

EXPECTED_R3 = {
    "family": "track_point_load",
    "capability_gate": "C1",
    "cpp_target": "structural_solver_cpu",
    "abi_version": "0x00010002",
    "api_entry": "sa_get_api_v1",
    "api_slot": "track_point_load_solve",
    "legacy_exports_preserved": True,
    "fallback_count": 0,
    "c1_profile": {
        "node_count": 9,
        "point_position_m": 5.0,
        "support_types": ["pinned", "fixed"],
        "theories": ["euler", "timoshenko"],
        "absolute_tolerance": 1.0e-15,
    },
    "product_goldens": {
        "native/tests/fixtures/solver_cpu/track_point_load_fixed_euler_python_c1.json": (
            "30412b6fe9dc1cfbe5f86336a9d89b551d69538330dd07e7322ac655920eb85e"
        ),
        "native/tests/fixtures/solver_cpu/track_point_load_fixed_timoshenko_python_c1.json": (
            "5baecde7cdc15f75433a312f0fae5565ec742544d09422808649dd1fb6b25337"
        ),
        "native/tests/fixtures/solver_cpu/track_point_load_pinned_timoshenko_python_c1.json": (
            "5151e7d13fb5e8f3843d62d16303b7eed864653b165a952330bed9d92915c185"
        ),
        "native/tests/fixtures/solver_cpu/track_point_load_python_c1.json": (
            "268ad1318cc90042ec598ebdc9ec1e15534bc8e5153c0efeccbc5faa43fad282"
        ),
    },
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
        "legacy_displacement_residual": "pass",
        "legacy_rotation_interior": "pass",
        "legacy_rotation_endpoints": "intentional_product_divergence",
        "legacy_endpoint_max_abs_delta": 0.00003436580346133486,
        "python_full_vector": "pass",
        "c1_promoted": True,
        "c2_hip": "open",
    },
}

EXPECTED_NONLINEAR_STATIC_R3 = {
    "family": "nonlinear_static",
    "capability_gate": "C0",
    "cpp_target": "structural_solver_cpu",
    "abi_version": "0x00010003",
    "api_entry": "sa_get_api_v1",
    "api_slot": "nonlinear_static_solve",
    "legacy_exports_preserved": True,
    "fallback_count": 0,
    "c0_profile": {
        "story_count": 3,
        "absolute_tolerance": 1.0e-15,
        "fixture": "native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json",
        "fixture_sha256": (
            "57df412800943da8fdd2214a88cadd314b1620c7b2c707a15f56f4828a3a9ab0"
        ),
    },
    "owners": {
        "cpp_cpu_kernel": "native/cpp/src/solver_cpu/nonlinear_static.cpp",
        "c_abi": "native/cpp/include/structural/abi_v1.h",
        "rust_safe_wrapper": "native/crates/structural-ffi/src/lib.rs",
    },
    "verification": {
        "cpp_unit": "native/cpp/tests/solver_cpu/nonlinear_static_test.cpp",
        "c_abi_contract": "native/cpp/tests/abi/nonlinear_static_contract_test.cpp",
        "rust_ffi_parity": "native/crates/structural-ffi/tests/nonlinear_static_parity.rs",
        "checker": "scripts/check_structural_runtime_ffi_r3.py",
    },
    "parity": {
        "legacy_rust_full_result": "pass",
        "python_oracle": "open",
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
    nonlinear_inventory = inventory.get("r3_nonlinear_static")
    if nonlinear_inventory != EXPECTED_NONLINEAR_STATIC_R3:
        blockers.append("r3_nonlinear_static_inventory_invalid")

    for family, expected in (
        ("track", EXPECTED_R3),
        ("nonlinear_static", EXPECTED_NONLINEAR_STATIC_R3),
    ):
        for group in (expected["owners"], expected["verification"]):
            for role, relative_path in group.items():
                if not (repo_root / relative_path).is_file():
                    blockers.append(f"r3_owned_file_missing:{family}:{role}")

    for relative_path, expected_hash in EXPECTED_R3["product_goldens"].items():
        product_golden_path = repo_root / relative_path
        try:
            product_golden_bytes = product_golden_path.read_bytes()
        except OSError as exc:
            blockers.append(f"r3_product_golden_unreadable:{relative_path}:{exc}")
            continue
        actual_hash = hashlib.sha256(product_golden_bytes).hexdigest()
        if actual_hash != expected_hash:
            blockers.append(f"r3_product_golden_sha256_mismatch:{relative_path}")
        try:
            product_case = json.loads(product_golden_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            blockers.append(f"r3_product_golden_invalid:{relative_path}:{exc}")
            continue
        if (
            not isinstance(product_case, dict)
            or product_case.get("schema_version") != "structural-runtime-compat.v3"
            or product_case.get("operation") != "track_point_load"
        ):
            blockers.append(f"r3_product_golden_contract_invalid:{relative_path}")

    nonlinear_profile = EXPECTED_NONLINEAR_STATIC_R3["c0_profile"]
    nonlinear_fixture_relative = nonlinear_profile["fixture"]
    nonlinear_fixture_path = repo_root / nonlinear_fixture_relative
    try:
        nonlinear_fixture_bytes = nonlinear_fixture_path.read_bytes()
    except OSError as exc:
        blockers.append(f"r3_nonlinear_static_fixture_unreadable:{exc}")
    else:
        nonlinear_fixture_hash = hashlib.sha256(nonlinear_fixture_bytes).hexdigest()
        if nonlinear_fixture_hash != nonlinear_profile["fixture_sha256"]:
            blockers.append("r3_nonlinear_static_fixture_sha256_mismatch")
        try:
            nonlinear_case = json.loads(nonlinear_fixture_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            blockers.append(f"r3_nonlinear_static_fixture_invalid:{exc}")
        else:
            nonlinear_config = (
                nonlinear_case.get("config")
                if isinstance(nonlinear_case, dict)
                else None
            )
            if (
                not isinstance(nonlinear_case, dict)
                or nonlinear_case.get("schema_version")
                != "structural-runtime-compat.v3"
                or nonlinear_case.get("operation") != "nonlinear_static"
                or not isinstance(nonlinear_config, dict)
                or nonlinear_config.get("story_count")
                != nonlinear_profile["story_count"]
            ):
                blockers.append("r3_nonlinear_static_fixture_contract_invalid")

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
        "cmake": ("structural_solver_cpu STATIC", "structural_solver_cpu structural_c_abi_v1"),
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

    nonlinear_sources = {
        "cmake": sources["cmake"],
        "header": sources["header"],
        "abi": sources["abi"],
        "kernel": repo_root
        / EXPECTED_NONLINEAR_STATIC_R3["owners"]["cpp_cpu_kernel"],
        "rust": sources["rust"],
    }
    nonlinear_required_tokens = {
        "cmake": ("src/solver_cpu/nonlinear_static.cpp",),
        "header": (
            "#define SA_ABI_V1_3 UINT32_C(0x00010003)",
            "sa_nonlinear_static_solve_fn_v1 nonlinear_static_solve",
            "SA_CAPABILITY_NONLINEAR_STATIC_CPU",
        ),
        "abi": ("nonlinear_static_boundary", "SA_ERR_NONCONVERGENCE"),
        "kernel": ("solve_nonlinear_static", "solve_tridiagonal"),
        "rust": ("pub fn load_nonlinear_static", "pub fn solve_nonlinear_static"),
    }
    for role, path in nonlinear_sources.items():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"r3_source_unreadable:nonlinear_static:{role}:{exc}")
            continue
        for token in nonlinear_required_tokens[role]:
            if token not in text:
                blockers.append(
                    f"r3_source_token_missing:nonlinear_static:{role}:{token}"
                )

    try:
        capabilities = _load_json(repo_root / "native/capabilities.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r3_capabilities_invalid:{exc}")
        capabilities = {}
    capability = capabilities.get("capabilities", {}).get("track_point_load_cpu", {})
    if not isinstance(capability, dict) or capability.get("status") != "implemented":
        blockers.append("r3_track_capability_not_implemented")
    else:
        if capability.get("cutover_gate") != "C1":
            blockers.append("r3_track_capability_gate_invalid")
        claim = str(capability.get("claim", ""))
        for boundary in (
            "Python C1",
            "9-node midpoint-load",
            "legacy Rust",
            "broader input-space",
            "HIP C2",
            "restart",
            "product E2E",
        ):
            if boundary not in claim:
                blockers.append(f"r3_track_claim_boundary_missing:{boundary}")

    nonlinear_capability = capabilities.get("capabilities", {}).get(
        "nonlinear_static_cpu", {}
    )
    if (
        not isinstance(nonlinear_capability, dict)
        or nonlinear_capability.get("status") != "implemented"
    ):
        blockers.append("r3_nonlinear_static_capability_not_implemented")
    else:
        if nonlinear_capability.get("cutover_gate") != "C0":
            blockers.append("r3_nonlinear_static_capability_gate_invalid")
        nonlinear_claim = str(nonlinear_capability.get("claim", ""))
        for boundary in (
            "ABI v1.3",
            "frozen legacy Rust parity",
            "3-story compatibility case only",
            "Python C1",
            "broader nonlinear input-space",
            "HIP C2",
            "restart",
            "product E2E",
        ):
            if boundary not in nonlinear_claim:
                blockers.append(
                    f"r3_nonlinear_static_claim_boundary_missing:{boundary}"
                )

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
        "capability_gate": "C1",
        "capability_gates": {
            "track_point_load_cpu": "C1",
            "nonlinear_static_cpu": "C0",
        },
        "blockers": blockers,
        "claim_boundary": (
            "R3 proves track Python C1 full-vector parity only for the four-case 9-node "
            "midpoint-load matrix, plus nonlinear static C0 parity only for one frozen "
            "3-story legacy Rust case through ABI v1.3. Independent nonlinear Python C1, "
            "broader input-space parity, HIP C2 and runtime cutover remain open."
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
