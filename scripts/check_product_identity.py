#!/usr/bin/env python3
"""Verify every current product metadata surface against one canonical manifest."""

from __future__ import annotations

import argparse
import ast
import configparser
import json
from pathlib import Path
import re
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_MANIFEST = Path("artifacts/manifests/product_identity.json")
SEMVER = re.compile(r"^0\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _python_constants(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                values[target.id] = value.value
    return values


def build_report(
    repo_root: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    root = repo_root.resolve()
    manifest_file = manifest_path if manifest_path.is_absolute() else root / manifest_path
    identity = _json(manifest_file)
    expected_name = str(identity.get("distribution_name", "")).strip()
    expected_import = str(identity.get("import_package", "")).strip()
    expected_display = str(identity.get("display_name", "")).strip()
    expected_version = str(identity.get("version", "")).strip()
    expected_engine = f"{expected_name}@{expected_version}"
    blockers: list[str] = []

    if identity.get("schema_version") != "structural-analysis-product-identity.v1":
        blockers.append("identity_manifest_schema_version_invalid")
    if not expected_name:
        blockers.append("identity_manifest_distribution_name_missing")
    if not expected_import:
        blockers.append("identity_manifest_import_package_missing")
    if not expected_display:
        blockers.append("identity_manifest_display_name_missing")
    if not SEMVER.fullmatch(expected_version):
        blockers.append("identity_manifest_version_not_pre_1_0_semver")

    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    project = pyproject.get("project", {})
    if project.get("name") != expected_name:
        blockers.append("pyproject_distribution_name_mismatch")
    if project.get("version") != expected_version:
        blockers.append("pyproject_version_mismatch")

    setup = configparser.ConfigParser()
    setup.read(root / "setup.cfg", encoding="utf-8")
    if setup.get("metadata", "name", fallback="") != expected_name:
        blockers.append("setup_cfg_distribution_name_mismatch")
    if setup.get("metadata", "version", fallback="") != expected_version:
        blockers.append("setup_cfg_version_mismatch")

    package = _json(root / "package.json")
    package_lock = _json(root / "package-lock.json")
    lock_root = package_lock.get("packages", {}).get("", {})
    metadata_rows = {
        "package_json": (package.get("name"), package.get("version")),
        "package_lock": (package_lock.get("name"), package_lock.get("version")),
        "package_lock_root": (lock_root.get("name"), lock_root.get("version")),
    }
    for surface, (name, version) in metadata_rows.items():
        if name != expected_name:
            blockers.append(f"{surface}_distribution_name_mismatch")
        if version != expected_version:
            blockers.append(f"{surface}_version_mismatch")

    runtime = _python_constants(root / "src/structural_analysis/product_identity.py")
    expected_runtime = {
        "DISTRIBUTION_NAME": expected_name,
        "IMPORT_PACKAGE": expected_import,
        "DISPLAY_NAME": expected_display,
        "FALLBACK_VERSION": expected_version,
    }
    for key, expected in expected_runtime.items():
        if runtime.get(key) != expected:
            blockers.append(f"runtime_identity_{key.lower()}_mismatch")

    readme = (root / "README.md").read_text(encoding="utf-8")
    if not readme.startswith(f"# {expected_display}\n"):
        blockers.append("readme_display_name_mismatch")
    frontend_contract = (
        root / "scripts/verify-frontend-build-contract.mjs"
    ).read_text(encoding="utf-8")
    if f"packageJson.name !== '{expected_name}'" not in frontend_contract:
        blockers.append("frontend_contract_distribution_name_mismatch")

    legacy_names = [
        str(value).strip()
        for value in identity.get("legacy_distribution_names", [])
        if str(value).strip()
    ]
    legacy_hits: list[str] = []
    for scan_root in (root / "src", root / "scripts"):
        for path in sorted(scan_root.rglob("*")):
            if (
                not path.is_file()
                or path.suffix
                not in {".py", ".js", ".mjs", ".ts", ".tsx", ".json"}
            ):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(legacy in text for legacy in legacy_names):
                legacy_hits.append(path.relative_to(root).as_posix())
    if legacy_hits:
        blockers.append("legacy_distribution_name_in_current_product_surface")

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "product-identity-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "canonical_manifest": manifest_file.relative_to(root).as_posix(),
        "identity": {
            "distribution_name": expected_name,
            "import_package": expected_import,
            "display_name": expected_display,
            "version": expected_version,
            "engine_version": expected_engine,
            "release_stage": identity.get("release_stage"),
        },
        "checked_metadata_surfaces": [
            "pyproject.toml",
            "setup.cfg",
            "package.json",
            "package-lock.json",
            "src/structural_analysis/product_identity.py",
            "README.md",
            "scripts/verify-frontend-build-contract.mjs",
        ],
        "legacy_distribution_name_hits": legacy_hits,
        "blockers": blockers,
        "claim_boundary": identity.get("claim_boundary", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, args.manifest)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"product identity: {report['status']} "
            f"({report['identity']['engine_version']})"
        )
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
