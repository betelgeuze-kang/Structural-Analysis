#!/usr/bin/env python3
"""Validate the R1 lower gate for the frozen legacy Rust ABI v3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("native/compatibility/structural_runtime_ffi_v3.json")
SOURCE_EXPORT_RE = re.compile(
    r"#\[no_mangle\]\s*pub\s+(?:unsafe\s+)?extern\s+\"C\"\s+fn\s+([A-Za-z0-9_]+)"
)
RAW_STATUS_RE = re.compile(
    r"pub\s+const\s+[A-Z0-9_]+:\s*i32\s*=\s*(-\d+)\s*;"
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _cargo_metadata(repo_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    completed = subprocess.run(
        [
            "cargo",
            "metadata",
            "--manifest-path",
            str(repo_root / "native" / "Cargo.toml"),
            "--format-version",
            "1",
            "--locked",
            "--no-deps",
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        lines = completed.stderr.strip().splitlines()
        return None, lines[-1] if lines else f"exit_{completed.returncode}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"
    return payload, None


def _library_exports(path: Path) -> tuple[list[str] | None, str | None]:
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
        lines = completed.stderr.strip().splitlines()
        return None, lines[-1] if lines else f"nm_exit_{completed.returncode}"
    exports = sorted(
        line.split()[-1]
        for line in completed.stdout.splitlines()
        if line.split()
    )
    return exports, None


def check_r1(
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
    blockers: list[str] = []
    try:
        inventory = _load_json(resolved_inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _report([f"r1_inventory_invalid:{exc}"], [], [], None, [], [])

    if inventory.get("schema_version") != "structural-runtime-ffi-compatibility.v1":
        blockers.append("r1_inventory_schema_version_invalid")
    transition_step = inventory.get("transition_step")
    if transition_step not in {"R1", "R2", "R3"}:
        blockers.append("r1_inventory_transition_step_invalid")
    if inventory.get("abi_version") != 3:
        blockers.append("r1_inventory_abi_version_invalid")

    package = inventory.get("package")
    if not isinstance(package, dict):
        blockers.append("r1_inventory_package_invalid")
        package = {}
    expected_manifest = str(package.get("manifest", ""))
    expected_exports = sorted(
        str(value) for value in inventory.get("exports", []) if str(value)
    )
    if len(expected_exports) != 5 or len(expected_exports) != len(set(expected_exports)):
        blockers.append("r1_inventory_export_set_invalid")
    status_groups = inventory.get("status_codes")
    expected_status_groups = {
        "track",
        "inplace_scale",
        "nonlinear_static",
        "nonlinear_ndtha",
    }
    status_groups_valid = (
        isinstance(status_groups, dict)
        and set(status_groups) == expected_status_groups
        and all(
            isinstance(values, list)
            and values
            and all(isinstance(value, int) for value in values)
            and len(values) == len(set(values))
            and 0 in values
            for values in status_groups.values()
        )
    )
    if not status_groups_valid:
        blockers.append("r1_inventory_status_groups_invalid")
        expected_status_codes: list[int] = []
    else:
        expected_status_codes = sorted(
            {
                int(value)
                for values in status_groups.values()
                for value in values
                if value < 0
            }
        )
        if not expected_status_codes:
            blockers.append("r1_inventory_status_codes_invalid")
    layouts = inventory.get("layouts")
    if not isinstance(layouts, dict) or len(layouts) != 7:
        blockers.append("r1_inventory_layout_set_invalid")
    golden_cases = inventory.get("golden_cases")
    if not isinstance(golden_cases, dict) or set(golden_cases) != {
        "track_pinned_euler_9",
        "scale_f32_4",
        "nonlinear_static_3_story",
        "nonlinear_ndtha_2_story_3_step",
    }:
        blockers.append("r1_inventory_golden_case_set_invalid")

    source_path = repo_root / "implementation/phase1/structural_runtime_ffi/src/lib.rs"
    try:
        source_text = source_path.read_text(encoding="utf-8")
        source_exports = sorted(SOURCE_EXPORT_RE.findall(source_text))
    except OSError as exc:
        blockers.append(f"r1_source_unreadable:{exc}")
        source_exports = []
    raw_abi_path = (
        repo_root
        / "native/crates/structural-ffi-sys/src/legacy_runtime_v3.rs"
    )
    try:
        raw_abi_text = raw_abi_path.read_text(encoding="utf-8")
        source_status_codes = sorted(
            {int(value) for value in RAW_STATUS_RE.findall(raw_abi_text)}
        )
    except OSError as exc:
        blockers.append(f"r1_raw_abi_source_unreadable:{exc}")
        source_status_codes = []
    if source_exports != expected_exports:
        blockers.append("r1_source_export_set_mismatch")
    if source_status_codes != expected_status_codes:
        blockers.append("r1_source_status_code_set_mismatch")

    owners_path = repo_root / "native" / "compatibility-owners.json"
    try:
        owners = _load_json(owners_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"r1_compatibility_owners_invalid:{exc}")
        owners = {}
    owner_rows = owners.get("entries", []) if isinstance(owners, dict) else []
    owner = next(
        (
            row
            for row in owner_rows
            if isinstance(row, dict) and row.get("legacy_manifest") == expected_manifest
        ),
        None,
    )
    if owner is None:
        blockers.append("r1_compatibility_owner_missing")
    else:
        if owner.get("migration_owner") != "structural-runtime":
            blockers.append("r1_compatibility_owner_invalid")
        if owner.get("transition_step") != transition_step:
            blockers.append("r1_compatibility_transition_step_invalid")
        if owner.get("workspace_member") is not True:
            blockers.append("r1_compatibility_workspace_member_false")
        if owner.get("legacy_abi_preserved") is not True:
            blockers.append("r1_compatibility_abi_not_preserved")
        if owner.get("removal_allowed") is not False:
            blockers.append("r1_compatibility_removal_not_fail_closed")

    if not (repo_root / "implementation/phase1/structural_runtime_ffi/Cargo.lock").is_file():
        blockers.append("r1_rollback_lock_missing")

    metadata, metadata_error = _cargo_metadata(repo_root)
    if metadata_error is not None or metadata is None:
        blockers.append(f"r1_cargo_metadata_failed:{metadata_error}")
    else:
        resolved_manifest = (repo_root / expected_manifest).resolve()
        matches = [
            row
            for row in metadata.get("packages", [])
            if Path(str(row.get("manifest_path", ""))).resolve() == resolved_manifest
        ]
        if len(matches) != 1:
            blockers.append("r1_workspace_package_count_mismatch")
        else:
            row = matches[0]
            if row.get("name") != package.get("name"):
                blockers.append("r1_workspace_package_name_mismatch")
            if row.get("version") != package.get("version"):
                blockers.append("r1_workspace_package_version_mismatch")
            if row.get("rust_version") != package.get("rust_version"):
                blockers.append("r1_workspace_package_msrv_mismatch")
            targets = row.get("targets", [])
            matching_targets = [
                target
                for target in targets
                if target.get("name") == package.get("name")
                and sorted(target.get("crate_types", []))
                == sorted(package.get("crate_types", []))
            ]
            if len(matching_targets) != 1:
                blockers.append("r1_workspace_crate_types_mismatch")
            if row.get("id") not in metadata.get("workspace_members", []):
                blockers.append("r1_package_not_in_workspace_members")
        if Path(str(metadata.get("workspace_root", ""))).resolve() != (repo_root / "native").resolve():
            blockers.append("r1_workspace_root_mismatch")

    binary_exports: list[str] | None = None
    if library_path is not None:
        resolved_library = library_path if library_path.is_absolute() else repo_root / library_path
        binary_exports, library_error = _library_exports(resolved_library)
        if library_error is not None:
            blockers.append(f"r1_binary_export_check_failed:{library_error}")
        elif binary_exports != expected_exports:
            blockers.append("r1_binary_export_set_mismatch")

    return _report(
        blockers,
        expected_exports,
        source_exports,
        binary_exports,
        expected_status_codes,
        source_status_codes,
    )


def _report(
    blockers: list[str],
    expected_exports: list[str],
    source_exports: list[str],
    binary_exports: list[str] | None,
    expected_status_codes: list[int],
    source_status_codes: list[int],
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "structural-runtime-ffi-r1-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "expected_exports": expected_exports,
        "source_exports": source_exports,
        "binary_exports": binary_exports,
        "expected_status_codes": expected_status_codes,
        "source_status_codes": source_status_codes,
        "blockers": blockers,
        "claim_boundary": (
            "This check proves R1 membership and frozen ABI inventory only. It does not "
            "promote the legacy numerical implementation or product E2E."
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
    payload = check_r1(args.repo_root, args.inventory, args.library)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Structural runtime FFI R1: {payload['status']}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
