#!/usr/bin/env python3
"""Validate R2 raw/wire ownership while retaining the frozen ABI v3 lower gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import check_structural_runtime_ffi_r1 as r1


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = r1.DEFAULT_INVENTORY

EXPECTED_OWNERSHIP = {
    "wire_schema": "native/crates/structural-contracts/schemas/legacy_runtime_v3.schema.json",
    "wire_types": "native/crates/structural-contracts/src/legacy_runtime.rs",
    "raw_abi_mirror": "native/crates/structural-ffi-sys/src/legacy_runtime_v3.rs",
    "legacy_adapter": "implementation/phase1/structural_runtime_ffi/src/contracts.rs",
    "legacy_runtime": "implementation/phase1/structural_runtime_ffi/src/runtime.rs",
    "legacy_ffi": "implementation/phase1/structural_runtime_ffi/src/ffi.rs",
    "public_facade": "implementation/phase1/structural_runtime_ffi/src/lib.rs",
}
EXPECTED_VERIFICATION = {
    "rust_contract_test": "implementation/phase1/structural_runtime_ffi/tests/abi_v3_contract.rs",
    "adapter_contract_test": "implementation/phase1/structural_runtime_ffi/tests/contracts_adapter.rs",
    "wire_contract_test": "native/crates/structural-contracts/tests/legacy_runtime_wire.rs",
    "symbol_checker": "scripts/check_structural_runtime_ffi_r2.py",
}
RAW_TYPES = {
    "TrackSolveConfig",
    "TrackSolveResult",
    "InplaceScaleStats",
    "NlFrameSolveConfig",
    "NlFrameSolveResult",
    "NlFrameNdthaConfig",
    "NlFrameNdthaResult",
}
ADAPTER_FUNCTIONS = {
    "track_case_v3",
    "inplace_scale_case_v3",
    "nonlinear_static_case_v3",
    "nonlinear_ndtha_case_v3",
}
WIRE_TYPES = {
    "TrackCaseV3",
    "InplaceScaleCaseV3",
    "NonlinearStaticCaseV3",
    "NonlinearNdthaCaseV3",
    "LegacyRuntimeCaseV3",
}
RUNTIME_FUNCTIONS = {
    "apply_euler_operator",
    "assemble_internal_and_tangent",
    "cg_solve_euler",
    "compute_story_response",
    "displacement_gradient",
    "dot",
    "fill_point_load",
    "ghost_at",
    "max_abs",
    "solve_ndtha_step",
    "solve_tridiagonal",
    "validate_cfg",
    "validate_ndtha_cfg",
    "validate_nl_cfg",
    "vec_norm_inf",
    "vec_norm_l2",
}
EXPECTED_GOLDEN_PATHS = frozenset(
    {
        "native/tests/fixtures/legacy_runtime_v3/inplace_scale_f32.json",
        "native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json",
        "native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json",
        "native/tests/fixtures/legacy_runtime_v3/track_point_load.json",
    }
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _read_owned_files(
    repo_root: Path,
    ownership: dict[str, str],
    blockers: list[str],
) -> dict[str, str]:
    texts: dict[str, str] = {}
    for role, relative_path in ownership.items():
        path = repo_root / relative_path
        try:
            texts[role] = path.read_text(encoding="utf-8")
        except OSError as exc:
            blockers.append(f"r2_owned_file_unreadable:{role}:{exc}")
    return texts


def check_r2(
    repo_root: Path = ROOT,
    inventory_path: Path = DEFAULT_INVENTORY,
    library_path: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    resolved_inventory = (
        inventory_path
        if inventory_path.is_absolute()
        else repo_root / inventory_path
    )
    lower_gate = r1.check_r1(repo_root, resolved_inventory, library_path)
    blockers = [f"r2_lower_gate:{value}" for value in lower_gate["blockers"]]

    try:
        inventory = _load_json(resolved_inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r2_inventory_invalid:{exc}")
        return _report(blockers, lower_gate, {}, {})

    if inventory.get("transition_step") not in {"R2", "R3"}:
        blockers.append("r2_inventory_transition_step_invalid")

    ownership = inventory.get("ownership")
    if ownership != EXPECTED_OWNERSHIP:
        blockers.append("r2_ownership_map_invalid")
        ownership = EXPECTED_OWNERSHIP
    verification = inventory.get("verification")
    if verification != EXPECTED_VERIFICATION:
        blockers.append("r2_verification_map_invalid")
    else:
        for role, relative_path in verification.items():
            if not (repo_root / relative_path).is_file():
                blockers.append(f"r2_verification_file_missing:{role}")

    texts = _read_owned_files(repo_root, ownership, blockers)
    raw_text = texts.get("raw_abi_mirror", "")
    raw_defined = set(re.findall(r"pub\s+struct\s+([A-Za-z0-9_]+)", raw_text))
    if not RAW_TYPES.issubset(raw_defined):
        blockers.append("r2_raw_abi_type_set_incomplete")

    runtime_text = texts.get("legacy_runtime", "")
    runtime_defined_types = set(
        re.findall(r"pub\s+struct\s+([A-Za-z0-9_]+)", runtime_text)
    )
    if RAW_TYPES & runtime_defined_types:
        blockers.append("r2_raw_abi_types_still_owned_by_oracle")
    runtime_defined_functions = set(
        re.findall(r"pub\(crate\)\s+fn\s+([A-Za-z0-9_]+)", runtime_text)
    )
    if not RUNTIME_FUNCTIONS.issubset(runtime_defined_functions):
        blockers.append("r2_legacy_runtime_function_set_incomplete")
    if any(
        token in runtime_text
        for token in ("#[no_mangle]", 'extern "C"', "*const ", "*mut ", "std::slice")
    ):
        blockers.append("r2_legacy_runtime_contains_ffi_boundary")

    ffi_text = texts.get("legacy_ffi", "")
    if "use crate::runtime" not in ffi_text:
        blockers.append("r2_legacy_ffi_runtime_dependency_missing")
    if RUNTIME_FUNCTIONS & set(
        re.findall(r"(?:pub\(crate\)\s+)?fn\s+([A-Za-z0-9_]+)", ffi_text)
    ):
        blockers.append("r2_numerical_function_still_owned_by_ffi")

    facade_text = texts.get("public_facade", "")
    if "pub use structural_ffi_sys::legacy_runtime_v3" not in facade_text:
        blockers.append("r2_raw_abi_reexport_missing")
    if "pub use ffi::" not in facade_text:
        blockers.append("r2_legacy_export_reexport_missing")

    adapter_text = texts.get("legacy_adapter", "")
    adapter_defined = set(
        re.findall(r"pub\s+fn\s+([A-Za-z0-9_]+)", adapter_text)
    )
    if not ADAPTER_FUNCTIONS.issubset(adapter_defined):
        blockers.append("r2_adapter_function_set_incomplete")

    wire_text = texts.get("wire_types", "")
    wire_defined = set(
        re.findall(r"pub\s+(?:struct|enum)\s+([A-Za-z0-9_]+)", wire_text)
    )
    if not WIRE_TYPES.issubset(wire_defined):
        blockers.append("r2_wire_type_set_incomplete")
    if "pub fn parse_legacy_runtime_case_v3" not in wire_text:
        blockers.append("r2_strict_wire_parser_missing")

    schema_text = texts.get("wire_schema", "")
    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError:
        blockers.append("r2_wire_schema_invalid_json")
        schema = {}
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        blockers.append("r2_wire_schema_draft_invalid")
    lowered_schema = schema_text.lower()
    if any(token in lowered_schema for token in ("ptr_before", "ptr_after", "address")):
        blockers.append("r2_wire_schema_contains_process_pointer")

    expected_hashes = inventory.get("wire_golden_sha256")
    actual_hashes: dict[str, str] = {}
    if (
        not isinstance(expected_hashes, dict)
        or set(expected_hashes) != EXPECTED_GOLDEN_PATHS
    ):
        blockers.append("r2_wire_golden_hash_inventory_invalid")
        expected_hashes = {}
    for relative_path in sorted(EXPECTED_GOLDEN_PATHS):
        expected_hash = expected_hashes.get(relative_path)
        if not isinstance(expected_hash, str) or re.fullmatch(
            r"[0-9a-f]{64}", expected_hash
        ) is None:
            blockers.append("r2_wire_golden_hash_entry_invalid")
        path = repo_root / relative_path
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            blockers.append(f"r2_wire_golden_unreadable:{relative_path}:{exc}")
            continue
        actual_hashes[relative_path] = digest
        if digest != expected_hash:
            blockers.append(f"r2_wire_golden_hash_mismatch:{relative_path}")

    metadata, metadata_error = r1._cargo_metadata(repo_root)
    if metadata_error is not None or metadata is None:
        blockers.append(f"r2_cargo_metadata_failed:{metadata_error}")
    else:
        packages = [
            package
            for package in metadata.get("packages", [])
            if package.get("name") == "structural_runtime_ffi"
        ]
        if len(packages) != 1:
            blockers.append("r2_workspace_package_count_mismatch")
        else:
            dependency_names = {
                dependency.get("name")
                for dependency in packages[0].get("dependencies", [])
            }
            if not {"structural-contracts", "structural-ffi-sys"}.issubset(
                dependency_names
            ):
                blockers.append("r2_contract_dependencies_missing")

    return _report(blockers, lower_gate, expected_hashes, actual_hashes)


def _report(
    blockers: list[str],
    lower_gate: dict[str, object],
    expected_hashes: dict[str, str],
    actual_hashes: dict[str, str],
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "structural-runtime-ffi-r2-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "lower_gate_pass": lower_gate.get("contract_pass") is True,
        "expected_exports": lower_gate.get("expected_exports", []),
        "binary_exports": lower_gate.get("binary_exports"),
        "wire_golden_sha256": dict(sorted(actual_hashes.items())),
        "wire_golden_hashes_match": expected_hashes == actual_hashes,
        "blockers": blockers,
        "claim_boundary": (
            "This check proves R2 raw ABI ownership, neutral wire contracts, adapters and "
            "frozen R1 compatibility only. The legacy Rust runtime and FFI are physically "
            "separated, but numerical authority remains in the compatibility runtime."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_r2(args.repo_root, args.inventory, args.library)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Structural runtime FFI R2: {payload['status']}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
