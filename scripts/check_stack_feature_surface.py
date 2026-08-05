#!/usr/bin/env python3
"""Validate that a stacked PR still contains its declared feature surface.

The check is intentionally local and deterministic. It verifies literal paths,
workflow references, and import probes without consulting GitHub metadata, so a
branch reconstruction cannot silently drop files while metadata checks remain
green.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "stack-feature-surface.v1"
_PATH_LIST_KEYS = (
    "core_feature_paths",
    "guard_paths",
    "workflow_referenced_paths",
)


class FeatureSurfaceError(ValueError):
    """Raised when the manifest itself is malformed or unsafe."""


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FeatureSurfaceError("manifest must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise FeatureSurfaceError(f"schema_version must equal {SCHEMA_VERSION}")
    feature_id = payload.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise FeatureSurfaceError("feature_id must be a non-empty string")
    return payload


def _relative_paths(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(
        not isinstance(row, str) or not row.strip() for row in value
    ):
        raise FeatureSurfaceError(f"{key} must be a list of non-empty strings")
    normalized = [row.replace("\\", "/") for row in value]
    if len(set(normalized)) != len(normalized):
        raise FeatureSurfaceError(f"{key} contains duplicate paths")
    for relative in normalized:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise FeatureSurfaceError(f"unsafe relative path in {key}: {relative}")
    return normalized


def _import_modules(payload: Mapping[str, Any]) -> list[str]:
    value = payload.get("import_modules", [])
    if not isinstance(value, list) or any(
        not isinstance(row, str) or not row.strip() for row in value
    ):
        raise FeatureSurfaceError("import_modules must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise FeatureSurfaceError("import_modules contains duplicate modules")
    return list(value)


def validate_feature_surface(
    manifest_path: Path,
    *,
    repo_root: Path,
    run_import_probes: bool = True,
) -> dict[str, Any]:
    root = repo_root.resolve()
    manifest = _load_manifest(manifest_path)
    path_groups = {key: _relative_paths(manifest, key) for key in _PATH_LIST_KEYS}
    import_modules = _import_modules(manifest)

    all_declared_paths: list[str] = []
    for key in ("core_feature_paths", "guard_paths"):
        all_declared_paths.extend(path_groups[key])
    if len(set(all_declared_paths)) != len(all_declared_paths):
        raise FeatureSurfaceError("declared feature and guard paths overlap")

    missing_paths = [
        relative
        for relative in all_declared_paths
        if not (root / relative).is_file()
    ]

    workflow_path = manifest.get("workflow_path")
    if not isinstance(workflow_path, str) or not workflow_path.strip():
        raise FeatureSurfaceError("workflow_path must be a non-empty string")
    workflow_relative = workflow_path.replace("\\", "/")
    workflow_candidate = Path(workflow_relative)
    if workflow_candidate.is_absolute() or ".." in workflow_candidate.parts:
        raise FeatureSurfaceError("workflow_path must be a safe relative path")
    workflow_file = root / workflow_relative
    workflow_source = (
        workflow_file.read_text(encoding="utf-8") if workflow_file.is_file() else ""
    )
    missing_workflow_references = [
        relative
        for relative in path_groups["workflow_referenced_paths"]
        if relative not in workflow_source
    ]

    import_failures: list[dict[str, str]] = []
    if run_import_probes:
        for module_name in import_modules:
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # pragma: no cover - diagnostic payload
                import_failures.append(
                    {
                        "module": module_name,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

    contract_pass = not (
        missing_paths
        or not workflow_file.is_file()
        or missing_workflow_references
        or import_failures
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_id": manifest["feature_id"],
        "manifest_path": manifest_path.resolve().relative_to(root).as_posix(),
        "workflow_path": workflow_relative,
        "declared_path_count": len(all_declared_paths),
        "missing_paths": missing_paths,
        "workflow_exists": workflow_file.is_file(),
        "missing_workflow_references": missing_workflow_references,
        "import_modules": import_modules,
        "import_failures": import_failures,
        "contract_pass": contract_pass,
    }


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--skip-import-probes", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", type=Path)
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    manifest = args.manifest
    if not manifest.is_absolute():
        manifest = root / manifest
    try:
        payload = validate_feature_surface(
            manifest,
            repo_root=root,
            run_import_probes=not args.skip_import_probes,
        )
    except (FeatureSurfaceError, OSError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "feature_id": "unavailable",
            "contract_pass": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if args.write is not None:
        output = args.write if args.write.is_absolute() else root / args.write
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_serialized(payload), encoding="utf-8")
    if args.json:
        print(_serialized(payload), end="")
    else:
        print(
            "stack feature surface: "
            + ("pass" if payload.get("contract_pass") is True else "blocked")
        )
    return 0 if payload.get("contract_pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
