#!/usr/bin/env python3
"""Validate the release-artifact manifest used after artifact externalization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys
from typing import Any


SCHEMA_VERSION = "structural_analysis_release_artifacts_manifest.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(row: dict[str, Any], artifact_root: Path | None) -> Path:
    local_path = Path(str(row.get("local_path", "") or ""))
    if artifact_root is None:
        return local_path
    return artifact_root / Path(str(row.get("asset_name", "") or local_path.name))


def _is_clean_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _validate_artifact_integrity(row: dict[str, Any], candidate: Path, errors: list[str]) -> None:
    asset_name = str(row.get("asset_name", "") or "").strip()
    bytes_value = row.get("bytes")
    sha256 = str(row.get("sha256", "") or "").strip()
    if not candidate.is_file():
        errors.append(f"artifact file missing: {candidate}")
        return
    actual_bytes = candidate.stat().st_size
    if actual_bytes != bytes_value:
        errors.append(f"bytes mismatch for {asset_name}: manifest={bytes_value} actual={actual_bytes}")
    actual_sha = _sha256(candidate)
    if actual_sha != sha256:
        errors.append(f"sha256 mismatch for {asset_name}: manifest={sha256} actual={actual_sha}")


def validate_manifest_structure(manifest: Any) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"], []

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not str(manifest.get("release_tag", "") or "").strip():
        errors.append("release_tag is required")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        return errors, []

    valid_rows: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    seen_local_paths: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        row_error_count = len(errors)
        asset_name = str(row.get("asset_name", "") or "").strip()
        local_path = str(row.get("local_path", "") or "").strip()
        sha256 = str(row.get("sha256", "") or "").strip()
        bytes_value = row.get("bytes")
        if not asset_name:
            errors.append(f"artifacts[{index}].asset_name is required")
        elif "/" in asset_name or "\\" in asset_name or asset_name in {".", ".."}:
            errors.append(f"artifacts[{index}].asset_name must be a single file name")
        if asset_name in seen_assets:
            errors.append(f"duplicate asset_name: {asset_name}")
        seen_assets.add(asset_name)
        if not local_path:
            errors.append(f"artifacts[{index}].local_path is required")
        elif not _is_clean_relative_path(local_path):
            errors.append(f"artifacts[{index}].local_path must be a clean relative path")
        elif not local_path.startswith("implementation/phase1/release/"):
            errors.append(f"artifacts[{index}].local_path must point under implementation/phase1/release/")
        if local_path in seen_local_paths:
            errors.append(f"duplicate local_path: {local_path}")
        seen_local_paths.add(local_path)
        if not SHA256_RE.match(sha256):
            errors.append(f"artifacts[{index}].sha256 must be a lowercase 64-char hex digest")
        if not isinstance(bytes_value, int) or bytes_value <= 0:
            errors.append(f"artifacts[{index}].bytes must be a positive integer")
        if not isinstance(row.get("required"), bool):
            errors.append(f"artifacts[{index}].required must be boolean")
        if len(errors) == row_error_count:
            valid_rows.append(row)
    return errors, valid_rows


def validate_manifest(
    manifest: Any,
    *,
    artifact_root: Path | None = None,
    structure_only: bool = False,
    require_artifacts: bool = False,
) -> list[str]:
    errors, valid_rows = validate_manifest_structure(manifest)
    if errors or structure_only:
        return errors

    for row in valid_rows:
        candidate = _artifact_path(row, artifact_root)
        should_check_local = artifact_root is not None or require_artifacts or candidate.exists()
        if should_check_local:
            _validate_artifact_integrity(row, candidate, errors)
    return errors


def build_hydration_preflight(manifest: Any, *, artifact_root: Path | None = None) -> dict[str, Any]:
    """Describe whether manifest artifacts are already present or need hydration.

    This is intentionally a preflight, not an integrity gate. It lets clean CI
    validate the evidence manifest contract without requiring generated release
    reports to be present in the source checkout.
    """

    errors, valid_rows = validate_manifest_structure(manifest)
    rows: list[dict[str, Any]] = []
    for row in valid_rows:
        candidate = _artifact_path(row, artifact_root)
        exists = candidate.is_file()
        rows.append(
            {
                "asset_name": str(row.get("asset_name", "") or ""),
                "expected_bytes": row.get("bytes"),
                "expected_sha256": str(row.get("sha256", "") or ""),
                "required": bool(row.get("required")),
                "hydrate_target": str(candidate),
                "present": exists,
                "actual_bytes": candidate.stat().st_size if exists else None,
                "status": "present" if exists else "hydrate_required",
            }
        )

    required_missing = [row for row in rows if row["required"] and not row["present"]]
    optional_missing = [row for row in rows if not row["required"] and not row["present"]]
    present = [row for row in rows if row["present"]]
    return {
        "ok": not errors,
        "mode": "artifact_root" if artifact_root is not None else "source_checkout",
        "contract": (
            "Missing generated release artifacts are expected in a clean source checkout. "
            "Validate structure in CI, then hydrate/reuse release assets and run full integrity "
            "with --artifact-root or --require-artifacts."
        ),
        "errors": errors,
        "totals": {
            "manifest_assets": len(rows),
            "present": len(present),
            "required_missing": len(required_missing),
            "optional_missing": len(optional_missing),
        },
        "present": present,
        "required_missing": required_missing,
        "optional_missing": optional_missing,
    }


def _print_hydration_preflight(summary: dict[str, Any]) -> None:
    print("Release artifact hydration preflight")
    print(f"Mode: {summary['mode']}")
    print(f"Contract: {summary['contract']}")
    totals = summary["totals"]
    print(
        "Totals: "
        f"manifest={totals['manifest_assets']} present={totals['present']} "
        f"required_missing={totals['required_missing']} optional_missing={totals['optional_missing']}"
    )
    for label, key in (
        ("Hydrate required", "required_missing"),
        ("Hydrate optional", "optional_missing"),
        ("Already present", "present"),
    ):
        for row in summary[key]:
            print(
                f"{label}: {row['asset_name']} "
                f"target={row['hydrate_target']} expected_bytes={row['expected_bytes']}"
            )
    if summary["errors"]:
        print("Release artifact hydration preflight failed:", file=sys.stderr)
        for error in summary["errors"]:
            print(f"- {error}", file=sys.stderr)
    else:
        print("Release artifact hydration preflight OK (no local artifact bytes required)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifact-root", default="")
    parser.add_argument(
        "--hydrate-preflight",
        action="store_true",
        help=(
            "Validate manifest structure and report which generated artifacts need hydration "
            "without failing merely because clean CI lacks local release files."
        ),
    )
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="Validate manifest schema, paths, and digest/size fields without reading artifact files.",
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Require local_path artifacts to exist and match sha256/bytes when --artifact-root is not used.",
    )
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root) if str(args.artifact_root).strip() else None
    if args.hydrate_preflight and (args.structure_only or args.require_artifacts):
        parser.error("--hydrate-preflight cannot be combined with --structure-only or --require-artifacts")
    if args.structure_only and (artifact_root is not None or args.require_artifacts):
        parser.error("--structure-only cannot be combined with --artifact-root or --require-artifacts")
    manifest = _load_json(Path(args.manifest))
    if args.hydrate_preflight:
        summary = build_hydration_preflight(manifest, artifact_root=artifact_root)
        _print_hydration_preflight(summary)
        return 0 if summary["ok"] else 1
    errors = validate_manifest(
        manifest,
        artifact_root=artifact_root,
        structure_only=args.structure_only,
        require_artifacts=args.require_artifacts,
    )
    if errors:
        print("Release artifact manifest check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.structure_only:
        print("Release artifact manifest OK (source-repo structure only; artifact bytes/sha not checked)")
    elif artifact_root is not None:
        print("Release artifact manifest OK (artifact-root asset integrity checked)")
    elif args.require_artifacts:
        print("Release artifact manifest OK (local artifact integrity required and checked)")
    else:
        print("Release artifact manifest OK (structure checked; existing local artifacts checked when present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
