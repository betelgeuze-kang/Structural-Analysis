#!/usr/bin/env python3
"""Validate the R4 product-workspace cutover and standalone rollback boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import check_structural_runtime_ffi_r1 as r1
import check_structural_runtime_ffi_r3 as r3


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = r3.DEFAULT_INVENTORY

EXPECTED_R4 = {
    "product_workspace": "native/Cargo.toml",
    "product_lockfile": "native/Cargo.lock",
    "standalone_manifest": "implementation/phase1/structural_runtime_ffi/Cargo.toml",
    "standalone_lockfile": "implementation/phase1/structural_runtime_ffi/Cargo.lock",
    "product_api_entry": "sa_get_api_v1",
    "product_workspace_member": False,
    "product_dependency": False,
    "product_parity_authority": "language_neutral_goldens",
    "legacy_exports_preserved": True,
    "legacy_package_disposition": "rollback_deprecation_only",
    "runtime_owners": {
        "job_checkpoint_cancel": "native/crates/structural-runtime/src/job.rs",
        "ndtha_checkpoint": "native/crates/structural-runtime/src/checkpoint.rs",
        "runtime_dispatch": "native/crates/structural-runtime/src/lib.rs",
    },
    "product_parity_tests": [
        "native/crates/structural-ffi/tests/track_point_load_parity.rs",
        "native/crates/structural-ffi/tests/nonlinear_static_parity.rs",
        "native/crates/structural-ffi/tests/nonlinear_ndtha_parity.rs",
    ],
    "deprecated_consumers": [
        "implementation/phase1/rust_track_lf_bridge.py",
        "implementation/phase1/rust_nonlinear_frame_bridge.py",
        "implementation/phase1/structural_runtime_hook.py",
    ],
    "deprecation": {
        "started": True,
        "removal_allowed": False,
        "removal_gate": "C6",
        "rollback_lock_retained": True,
        "consumer_removal_required": True,
    },
    "verification": {
        "checker": "scripts/check_structural_runtime_ffi_r4.py",
        "contract_test": "tests/test_structural_runtime_ffi_r4.py",
        "legacy_abi_test": (
            "implementation/phase1/structural_runtime_ffi/tests/abi_v3_contract.rs"
        ),
        "legacy_adapter_test": (
            "implementation/phase1/structural_runtime_ffi/tests/contracts_adapter.rs"
        ),
    },
}

RUNTIME_OWNER_TOKENS = {
    "job_checkpoint_cancel": (
        "pub fn publish_checkpoint",
        "pub fn request_cancel",
        "DurableJobStatusV1",
    ),
    "ndtha_checkpoint": ("pub struct NonlinearNdthaCheckpoint", "checkpoint_hash"),
    "runtime_dispatch": ("pub struct Runtime", "pub use job::"),
}

PRODUCT_TEST_TOKENS = {
    "native/crates/structural-ffi/tests/track_point_load_parity.rs": (
        "legacy_runtime_v3/track_point_load.json",
        "frozen_neutral_legacy_boundary",
    ),
    "native/crates/structural-ffi/tests/nonlinear_static_parity.rs": (
        "legacy_runtime_v3/nonlinear_static.json",
        "frozen_neutral_legacy_result",
    ),
    "native/crates/structural-ffi/tests/nonlinear_ndtha_parity.rs": (
        "legacy_runtime_v3/nonlinear_ndtha.json",
        "complete_frozen_legacy_rust_result",
    ),
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _read_text(path: Path, label: str, blockers: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"r4_file_unreadable:{label}:{exc}")
        return ""


def _product_source_references(repo_root: Path) -> list[str]:
    references: list[str] = []
    source_root = repo_root / "native" / "crates"
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or not (path.suffix == ".rs" or path.name == "Cargo.toml"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            references.append(path.relative_to(repo_root).as_posix())
            continue
        if "structural_runtime_ffi" in text:
            references.append(path.relative_to(repo_root).as_posix())
    return references


def check_r4(
    repo_root: Path = ROOT,
    inventory_path: Path = DEFAULT_INVENTORY,
    legacy_library: Path | None = None,
    product_library: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    resolved_inventory = (
        inventory_path if inventory_path.is_absolute() else repo_root / inventory_path
    )
    lower_gate = r3.check_r3(
        repo_root,
        resolved_inventory,
        legacy_library,
        product_library,
    )
    blockers = [f"r4_lower_gate:{value}" for value in lower_gate["blockers"]]

    try:
        inventory = _load_json(resolved_inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r4_inventory_invalid:{exc}")
        return _report(blockers, lower_gate, [], [], [])
    if inventory.get("transition_step") != "R4":
        blockers.append("r4_inventory_transition_step_invalid")
    if inventory.get("r4_runtime_cutover") != EXPECTED_R4:
        blockers.append("r4_cutover_inventory_invalid")

    try:
        owners = _load_json(repo_root / "native/compatibility-owners.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r4_compatibility_owners_invalid:{exc}")
        owners = {}
    owner = next(
        (
            row
            for row in owners.get("entries", [])
            if isinstance(row, dict)
            and row.get("legacy_manifest") == EXPECTED_R4["standalone_manifest"]
        ),
        None,
    )
    if owner is None:
        blockers.append("r4_compatibility_owner_missing")
    else:
        for field, expected in (
            ("transition_step", "R4"),
            ("workspace_member", False),
            ("legacy_abi_preserved", True),
            ("removal_allowed", False),
        ):
            if owner.get(field) != expected:
                blockers.append(f"r4_compatibility_owner_{field}_invalid")

    product_metadata, product_error = r1._cargo_metadata(repo_root)
    product_packages: list[str] = []
    if product_error is not None or product_metadata is None:
        blockers.append(f"r4_product_metadata_failed:{product_error}")
    else:
        product_packages = sorted(
            str(package.get("name", ""))
            for package in product_metadata.get("packages", [])
        )
        if "structural_runtime_ffi" in product_packages:
            blockers.append("r4_legacy_package_in_product_metadata")
        for package in product_metadata.get("packages", []):
            dependency_names = {
                str(dependency.get("name", ""))
                for dependency in package.get("dependencies", [])
            }
            if "structural_runtime_ffi" in dependency_names:
                blockers.append(
                    "r4_product_dependency_present:" + str(package.get("name", ""))
                )

    standalone_metadata, standalone_error = r1._legacy_cargo_metadata(
        repo_root, EXPECTED_R4["standalone_manifest"]
    )
    standalone_packages: list[str] = []
    if standalone_error is not None or standalone_metadata is None:
        blockers.append(f"r4_standalone_metadata_failed:{standalone_error}")
    else:
        standalone_packages = sorted(
            str(package.get("name", ""))
            for package in standalone_metadata.get("packages", [])
        )
        legacy_rows = [
            package
            for package in standalone_metadata.get("packages", [])
            if package.get("name") == "structural_runtime_ffi"
        ]
        if len(legacy_rows) != 1:
            blockers.append("r4_standalone_package_count_mismatch")
        else:
            dependency_names = {
                str(dependency.get("name", ""))
                for dependency in legacy_rows[0].get("dependencies", [])
            }
            if not {"structural-contracts", "structural-ffi-sys"}.issubset(
                dependency_names
            ):
                blockers.append("r4_standalone_contract_dependencies_missing")

    product_lock = _read_text(
        repo_root / EXPECTED_R4["product_lockfile"], "product_lock", blockers
    )
    if re.search(r'^name = "structural_runtime_ffi"$', product_lock, re.MULTILINE):
        blockers.append("r4_legacy_package_in_product_lock")
    standalone_lock = _read_text(
        repo_root / EXPECTED_R4["standalone_lockfile"], "standalone_lock", blockers
    )
    if not re.search(
        r'^name = "structural_runtime_ffi"$', standalone_lock, re.MULTILINE
    ):
        blockers.append("r4_legacy_package_missing_from_standalone_lock")

    standalone_manifest = _read_text(
        repo_root / EXPECTED_R4["standalone_manifest"],
        "standalone_manifest",
        blockers,
    )
    if re.search(r"^workspace\s*=", standalone_manifest, re.MULTILINE):
        blockers.append("r4_standalone_manifest_still_attached_to_product_workspace")

    product_references = _product_source_references(repo_root)
    blockers.extend(
        f"r4_product_source_references_legacy_crate:{path}"
        for path in product_references
    )

    for role, relative_path in EXPECTED_R4["runtime_owners"].items():
        text = _read_text(repo_root / relative_path, f"runtime_owner:{role}", blockers)
        for token in RUNTIME_OWNER_TOKENS[role]:
            if token not in text:
                blockers.append(f"r4_runtime_owner_token_missing:{role}:{token}")

    for relative_path in EXPECTED_R4["product_parity_tests"]:
        text = _read_text(repo_root / relative_path, "product_parity_test", blockers)
        if "structural_runtime_ffi" in text:
            blockers.append(f"r4_product_parity_imports_legacy_crate:{relative_path}")
        for token in PRODUCT_TEST_TOKENS[relative_path]:
            if token not in text:
                blockers.append(f"r4_product_parity_token_missing:{relative_path}:{token}")

    deprecated_consumers: list[str] = []
    for relative_path in EXPECTED_R4["deprecated_consumers"]:
        text = _read_text(repo_root / relative_path, "deprecated_consumer", blockers)
        deprecated_consumers.append(relative_path)
        if "structural_runtime_ffi" not in text and "rust_track_lf_bridge" not in text:
            blockers.append(f"r4_deprecated_consumer_boundary_missing:{relative_path}")

    return _report(
        blockers,
        lower_gate,
        product_packages,
        standalone_packages,
        deprecated_consumers,
    )


def _report(
    blockers: list[str],
    lower_gate: dict[str, object],
    product_packages: list[str],
    standalone_packages: list[str],
    deprecated_consumers: list[str],
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "structural-runtime-ffi-r4-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "lower_gate_pass": lower_gate.get("contract_pass") is True,
        "product_workspace_dependency": False if not blockers else None,
        "legacy_abi_preserved": len(lower_gate.get("legacy_exports", [])) == 5,
        "product_packages": product_packages,
        "standalone_packages": standalone_packages,
        "deprecated_consumers": deprecated_consumers,
        "removal_allowed": False,
        "blockers": blockers,
        "claim_boundary": (
            "R4 proves that the frozen legacy Rust ABI is absent from the native product "
            "Cargo workspace, lockfile, dependency graph and Rust product tests. The unchanged "
            "five-symbol package remains a separately locked rollback/deprecation artifact. "
            "Deprecated Python consumers, approved-device HIP C2 and global C6 removal remain open."
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
    payload = check_r4(
        args.repo_root,
        args.inventory,
        args.legacy_library,
        args.product_library,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Structural runtime FFI R4: {payload['status']}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
