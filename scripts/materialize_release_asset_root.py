#!/usr/bin/env python3
"""Materialize manifest-listed release assets into a flat local asset root."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any


DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")
LOCAL_PATH_FIELDS = ("local_path", "source_path", "artifact_path", "path")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_clean_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _is_single_file_name(value: str) -> bool:
    return bool(value) and "/" not in value and "\\" not in value and value not in {".", ".."}


def _manifest_local_path(row: dict[str, Any]) -> tuple[str, str]:
    for field in LOCAL_PATH_FIELDS:
        value = str(row.get(field, "") or "").strip()
        if value:
            return field, value
    return "", ""


def _contains_private_key_marker(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:8192]
    except OSError:
        return False
    return b"PRIVATE KEY" in sample.upper()


def _private_key_error(asset_name: str, source: Path) -> str | None:
    lower_names = (asset_name.lower(), source.name.lower())
    if _contains_private_key_marker(source):
        return f"unsafe private key-like PEM asset: {asset_name}"
    if any(name.endswith(".pem") and not name.endswith(".pub.pem") for name in lower_names):
        return f"unsafe private key-like PEM asset: {asset_name}"
    return None


def _validate_manifest_rows(manifest: Any, required_only: bool) -> tuple[str, list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return "", [], ["manifest root must be an object"]

    release_tag = str(manifest.get("release_tag", "") or "").strip()
    if not release_tag:
        errors.append("manifest release_tag is required")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest artifacts must be a non-empty list")
        return release_tag, [], errors

    rows: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue

        asset_name = str(row.get("asset_name", "") or "").strip()
        local_path_field, local_path = _manifest_local_path(row)
        bytes_value = row.get("bytes")
        sha256 = str(row.get("sha256", "") or "").strip()
        required = row.get("required")
        row_errors = len(errors)

        if not _is_single_file_name(asset_name):
            errors.append(f"artifacts[{index}].asset_name must be a single file name")
        elif asset_name in seen_assets:
            errors.append(f"duplicate asset_name: {asset_name}")
        seen_assets.add(asset_name)

        if not local_path:
            errors.append(f"artifacts[{index}] must define one of: {', '.join(LOCAL_PATH_FIELDS)}")
        elif not _is_clean_relative_path(local_path):
            errors.append(f"artifacts[{index}].{local_path_field} must be a clean relative path")

        if not isinstance(bytes_value, int) or bytes_value <= 0:
            errors.append(f"artifacts[{index}].bytes must be a positive integer")
        if not SHA256_RE.match(sha256):
            errors.append(f"artifacts[{index}].sha256 must be a lowercase 64-char hex digest")
        if not isinstance(required, bool):
            errors.append(f"artifacts[{index}].required must be boolean")

        if len(errors) == row_errors and (required or not required_only):
            rows.append(
                {
                    "asset_name": asset_name,
                    "local_path": local_path,
                    "local_path_field": local_path_field,
                    "bytes": bytes_value,
                    "sha256": sha256,
                    "required": required,
                }
            )
    return release_tag, rows, errors


def _preflight_action(row: dict[str, Any], artifact_root: Path) -> tuple[dict[str, Any], list[str]]:
    asset_name = row["asset_name"]
    source = Path(row["local_path"])
    destination = artifact_root / asset_name
    action: dict[str, Any] = {
        "asset_name": asset_name,
        "required": row["required"],
        "source": str(source),
        "destination": str(destination),
        "local_path_field": row["local_path_field"],
        "manifest_bytes": row["bytes"],
        "manifest_sha256": row["sha256"],
        "status": "pending",
    }
    errors: list[str] = []

    if not source.exists():
        errors.append(f"source artifact missing for {asset_name}: {source}")
        action["status"] = "error"
        return action, errors
    if not source.is_file():
        errors.append(f"source artifact is not a file for {asset_name}: {source}")
        action["status"] = "error"
        return action, errors

    private_key_error = _private_key_error(asset_name, source)
    if private_key_error:
        errors.append(private_key_error)
        action["status"] = "error"

    source_bytes = source.stat().st_size
    source_sha256 = _sha256(source)
    action["source_bytes"] = source_bytes
    action["source_sha256"] = source_sha256
    if source_bytes != row["bytes"]:
        errors.append(f"bytes mismatch for {asset_name} source: manifest={row['bytes']} actual={source_bytes}")
        action["status"] = "error"
    if source_sha256 != row["sha256"]:
        errors.append(f"sha256 mismatch for {asset_name} source: manifest={row['sha256']} actual={source_sha256}")
        action["status"] = "error"

    if destination.exists():
        if not destination.is_file():
            errors.append(f"destination exists and is not a file for {asset_name}: {destination}")
            action["status"] = "error"
            return action, errors
        destination_bytes = destination.stat().st_size
        destination_sha256 = _sha256(destination)
        action["destination_bytes"] = destination_bytes
        action["destination_sha256"] = destination_sha256
        if destination_bytes == row["bytes"] and destination_sha256 == row["sha256"]:
            if action["status"] != "error":
                action["status"] = "already_present"
        else:
            errors.append(f"destination already exists with different content for {asset_name}: {destination}")
            action["status"] = "error"
    elif action["status"] != "error":
        action["status"] = "would_copy"

    return action, errors


def materialize_release_asset_root(
    manifest_path: Path,
    artifact_root: Path,
    *,
    write: bool = False,
    required_only: bool = False,
) -> dict[str, Any]:
    """Preflight and optionally copy manifest assets into a flat artifact root."""

    errors: list[str] = []
    try:
        release_tag, rows, errors = _validate_manifest_rows(_load_json(manifest_path), required_only)
    except (OSError, json.JSONDecodeError) as exc:
        release_tag = ""
        rows = []
        errors = [str(exc)]

    actions: list[dict[str, Any]] = []
    if not errors and artifact_root.exists() and not artifact_root.is_dir():
        errors.append(f"artifact root exists and is not a directory: {artifact_root}")

    if not errors:
        for row in rows:
            action, action_errors = _preflight_action(row, artifact_root)
            actions.append(action)
            errors.extend(action_errors)

    if errors:
        for action in actions:
            if action["status"] in {"pending", "would_copy"}:
                action["status"] = "blocked"
    elif write:
        artifact_root.mkdir(parents=True, exist_ok=True)
        for action in actions:
            if action["status"] == "would_copy":
                shutil.copy2(action["source"], action["destination"])
                destination = Path(action["destination"])
                action["destination_bytes"] = destination.stat().st_size
                action["destination_sha256"] = _sha256(destination)
                if (
                    action["destination_bytes"] != action["manifest_bytes"]
                    or action["destination_sha256"] != action["manifest_sha256"]
                ):
                    errors.append(f"copied artifact failed verification for {action['asset_name']}: {destination}")
                    action["status"] = "error"
                else:
                    action["status"] = "copied"

    copied = sum(1 for action in actions if action["status"] == "copied")
    would_copy = sum(1 for action in actions if action["status"] == "would_copy")
    already_present = sum(1 for action in actions if action["status"] == "already_present")
    blocked = sum(1 for action in actions if action["status"] == "blocked")
    return {
        "ok": not errors,
        "write": write,
        "required_only": required_only,
        "manifest": str(manifest_path),
        "artifact_root": str(artifact_root),
        "release_tag": release_tag,
        "actions": actions,
        "errors": errors,
        "totals": {
            "selected_assets": len(rows),
            "copied": copied,
            "would_copy": would_copy,
            "already_present": already_present,
            "blocked": blocked,
            "errors": len(errors),
        },
    }


def _print_text(result: dict[str, Any]) -> None:
    mode = "write" if result["write"] else "dry-run"
    status = "ok" if result["ok"] else "failed"
    print(f"Release asset root materialization {status} ({mode})")
    print(f"Manifest: {result['manifest']}")
    print(f"Artifact root: {result['artifact_root']}")
    if result["release_tag"]:
        print(f"Release tag: {result['release_tag']}")
    for action in result["actions"]:
        print(f"- {action['asset_name']}: {action['status']} {action['source']} -> {action['destination']}")
    for error in result["errors"]:
        print(f"  error: {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight and optionally copy release artifacts from the manifest "
            "local paths into a flat artifact root. Dry-run is the default; pass --write "
            "to create files."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="Actually copy assets after preflight passes.")
    parser.add_argument(
        "--required-only",
        action="store_true",
        help="Materialize only required manifest assets. By default, all manifest-listed assets are selected.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = materialize_release_asset_root(
        args.manifest,
        args.artifact_root,
        write=args.write,
        required_only=args.required_only,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
