#!/usr/bin/env python3
"""Helpers for discovering project registry portfolio inputs."""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_FILENAMES = (
    "project_registry.json",
    "release_registry.json",
    "native_authoring_project_registry.json",
)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _normalize_path_specs(items: list[Path | str] | None) -> list[str]:
    if not items:
        return []
    values = [str(item).strip() for item in items if str(item).strip()]
    return _dedupe_preserve_order(values)


def _normalize_glob_specs(items: list[str] | None) -> list[str]:
    if not items:
        return []
    values = [str(item).strip() for item in items if str(item).strip()]
    return _dedupe_preserve_order(values)


def _canonical_path_key(path: Path) -> str:
    return str(path.resolve(strict=False))


def _sorted_unique_paths(paths: list[Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for path in sorted(paths, key=lambda candidate: str(candidate)):
        key = _canonical_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def _expand_directory(directory: Path, *, filename_patterns: tuple[str, ...]) -> list[Path]:
    matches: list[Path] = []
    for pattern in filename_patterns:
        matches.extend(path for path in directory.rglob(pattern) if path.is_file())
    return _sorted_unique_paths(matches)


def _expand_glob(pattern: str) -> list[Path]:
    matches = [Path(match) for match in glob.glob(pattern, recursive=True)]
    return _sorted_unique_paths([path for path in matches if path.is_file()])


def discover_project_registry_paths(
    *,
    registry_paths: list[Path | str] | None = None,
    registry_dirs: list[Path | str] | None = None,
    registry_globs: list[str] | None = None,
    filename_patterns: tuple[str, ...] = DEFAULT_REGISTRY_FILENAMES,
) -> dict[str, Any]:
    path_specs = _normalize_path_specs(registry_paths)
    directory_specs = _normalize_path_specs(registry_dirs)
    glob_specs = _normalize_glob_specs(registry_globs)

    discovered_paths: list[Path] = []
    source_details: dict[str, dict[str, Any]] = {}
    missing_inputs: list[dict[str, str]] = []
    unmatched_inputs: list[dict[str, str]] = []
    duplicate_registry_paths: list[str] = []
    duplicate_keys: set[str] = set()
    seen_paths: set[str] = set()

    def register_path(path: Path, *, source_kind: str, source_spec: str) -> None:
        canonical_key = _canonical_path_key(path)
        if canonical_key in seen_paths:
            if canonical_key not in duplicate_keys:
                duplicate_registry_paths.append(str(path))
                duplicate_keys.add(canonical_key)
            detail = source_details[canonical_key]
            detail["source_kinds"] = _dedupe_preserve_order(detail["source_kinds"] + [source_kind])
            detail["source_specs"] = _dedupe_preserve_order(detail["source_specs"] + [source_spec])
            return

        seen_paths.add(canonical_key)
        discovered_paths.append(path)
        source_details[canonical_key] = {
            "path": str(path),
            "source_kinds": [source_kind],
            "source_specs": [source_spec],
        }

    for spec in path_specs:
        if glob.has_magic(spec):
            matches = _expand_glob(spec)
            if not matches:
                unmatched_inputs.append({"kind": "path_glob", "value": spec})
                continue
            for path in matches:
                register_path(path, source_kind="glob", source_spec=spec)
            continue

        path = Path(spec)
        if path.is_file():
            register_path(path, source_kind="path", source_spec=spec)
            continue
        if path.is_dir():
            matches = _expand_directory(path, filename_patterns=filename_patterns)
            if not matches:
                unmatched_inputs.append({"kind": "path_directory", "value": spec})
                continue
            for match in matches:
                register_path(match, source_kind="directory", source_spec=spec)
            continue
        missing_inputs.append({"kind": "path", "value": spec})

    for spec in directory_specs:
        directory = Path(spec)
        if not directory.exists():
            missing_inputs.append({"kind": "directory", "value": spec})
            continue
        if not directory.is_dir():
            missing_inputs.append({"kind": "directory_not_dir", "value": spec})
            continue
        matches = _expand_directory(directory, filename_patterns=filename_patterns)
        if not matches:
            unmatched_inputs.append({"kind": "directory", "value": spec})
            continue
        for path in matches:
            register_path(path, source_kind="directory", source_spec=spec)

    for pattern in glob_specs:
        matches = _expand_glob(pattern)
        if not matches:
            unmatched_inputs.append({"kind": "glob", "value": pattern})
            continue
        for path in matches:
            register_path(path, source_kind="glob", source_spec=pattern)

    registry_paths_out = [Path(detail["path"]) for detail in source_details.values()]
    scan = {
        "filename_patterns": list(filename_patterns),
        "path_inputs": path_specs,
        "directory_inputs": directory_specs,
        "glob_inputs": glob_specs,
        "discovered_registry_paths": [str(path) for path in registry_paths_out],
        "source_details": [
            {
                "path": str(detail["path"]),
                "source_kinds": list(detail["source_kinds"]),
                "source_specs": list(detail["source_specs"]),
            }
            for detail in sorted(source_details.values(), key=lambda item: str(item["path"]))
        ],
        "missing_inputs": missing_inputs,
        "unmatched_inputs": unmatched_inputs,
        "duplicate_registry_paths": duplicate_registry_paths,
        "summary": {
            "path_input_count": len(path_specs),
            "directory_input_count": len(directory_specs),
            "glob_input_count": len(glob_specs),
            "discovered_registry_count": len(registry_paths_out),
            "missing_input_count": len(missing_inputs),
            "unmatched_input_count": len(unmatched_inputs),
            "duplicate_registry_count": len(duplicate_registry_paths),
        },
    }
    return {
        "registry_paths": registry_paths_out,
        "source_details_by_key": source_details,
        "scan": scan,
    }
