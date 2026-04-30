#!/usr/bin/env python3
"""Validate externalized open-data artifact manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_SCHEMA_VERSION = 1
VALID_DISPOSITIONS = {"externalize", "allowlist"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_clean_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest_structure(manifest: Any) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"], []
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        return errors, []

    valid_rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        row_error_count = len(errors)
        path = str(row.get("path", "") or "").strip()
        sha256 = str(row.get("sha256", "") or "").strip()
        source_family = str(row.get("source_family", "") or "").strip()
        disposition = str(row.get("disposition", "") or "").strip()
        bytes_value = row.get("bytes")

        if not _is_clean_relative_path(path):
            errors.append(f"artifacts[{index}].path must be a clean relative path")
        elif not path.startswith("implementation/phase1/open_data/"):
            errors.append(f"artifacts[{index}].path must point under implementation/phase1/open_data/")
        if path in seen_paths:
            errors.append(f"duplicate path: {path}")
        seen_paths.add(path)
        if not isinstance(bytes_value, int) or bytes_value <= 0:
            errors.append(f"artifacts[{index}].bytes must be a positive integer")
        if not SHA256_RE.match(sha256):
            errors.append(f"artifacts[{index}].sha256 must be a lowercase 64-char hex digest")
        if not source_family:
            errors.append(f"artifacts[{index}].source_family is required")
        if disposition not in VALID_DISPOSITIONS:
            errors.append(f"artifacts[{index}].disposition must be one of {sorted(VALID_DISPOSITIONS)}")
        if len(errors) == row_error_count:
            valid_rows.append(row)
    return errors, valid_rows


def validate_manifest(
    manifest: Any,
    *,
    artifact_root: Path | None = None,
    require_artifacts: bool = False,
    structure_only: bool = False,
) -> list[str]:
    errors, valid_rows = validate_manifest_structure(manifest)
    if errors or structure_only:
        return errors

    for row in valid_rows:
        relative_path = Path(str(row["path"]))
        candidate = artifact_root / relative_path if artifact_root is not None else relative_path
        if not candidate.exists() and not require_artifacts and artifact_root is None:
            continue
        if not candidate.is_file():
            errors.append(f"artifact file missing: {candidate}")
            continue
        actual_bytes = candidate.stat().st_size
        if actual_bytes != row["bytes"]:
            errors.append(f"bytes mismatch for {row['path']}: manifest={row['bytes']} actual={actual_bytes}")
        actual_sha = _sha256(candidate)
        if actual_sha != row["sha256"]:
            errors.append(f"sha256 mismatch for {row['path']}: manifest={row['sha256']} actual={actual_sha}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--require-artifacts", action="store_true")
    parser.add_argument("--structure-only", action="store_true")
    args = parser.parse_args(argv)
    if args.structure_only and (args.artifact_root is not None or args.require_artifacts):
        parser.error("--structure-only cannot be combined with --artifact-root or --require-artifacts")

    errors = validate_manifest(
        _load_json(Path(args.manifest)),
        artifact_root=args.artifact_root,
        require_artifacts=args.require_artifacts,
        structure_only=args.structure_only,
    )
    if errors:
        print("Open-data external artifact manifest check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.structure_only:
        print("Open-data external artifact manifest OK (structure only)")
    elif args.artifact_root is not None or args.require_artifacts:
        print("Open-data external artifact manifest OK (artifact integrity checked)")
    else:
        print("Open-data external artifact manifest OK (structure checked; existing local artifacts checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
