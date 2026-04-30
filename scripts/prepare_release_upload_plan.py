#!/usr/bin/env python3
"""Build a safe GitHub Release upload plan from manifest-listed artifacts only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")


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


def _manifest_rows(manifest: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")
    release_tag = str(manifest.get("release_tag", "") or "").strip()
    if not release_tag:
        raise ValueError("manifest release_tag is required")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifest artifacts must be a non-empty list")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict):
            raise ValueError(f"artifacts[{index}] must be an object")
        asset_name = str(row.get("asset_name", "") or "").strip()
        sha256 = str(row.get("sha256", "") or "").strip()
        bytes_value = row.get("bytes")
        required = row.get("required")
        if not asset_name:
            raise ValueError(f"artifacts[{index}].asset_name is required")
        if "/" in asset_name or "\\" in asset_name or asset_name in {".", ".."}:
            raise ValueError(f"artifacts[{index}].asset_name must be a single file name")
        if asset_name in seen:
            raise ValueError(f"duplicate asset_name: {asset_name}")
        seen.add(asset_name)
        if not isinstance(bytes_value, int) or bytes_value <= 0:
            raise ValueError(f"artifacts[{index}].bytes must be a positive integer")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ValueError(f"artifacts[{index}].sha256 must be a 64-character digest")
        if not isinstance(required, bool):
            raise ValueError(f"artifacts[{index}].required must be boolean")
        rows.append(
            {
                "asset_name": asset_name,
                "bytes": bytes_value,
                "sha256": sha256,
                "required": required,
            }
        )
    return release_tag, rows


def _relative_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return sorted(files)


def prepare_release_upload_plan(
    manifest_path: Path,
    artifact_root: Path,
    *,
    required_only: bool = False,
) -> dict[str, Any]:
    """Return a release upload plan or raise ValueError for unsafe inputs."""

    if not artifact_root.is_dir():
        raise ValueError(f"artifact root is not a directory: {artifact_root}")

    release_tag, rows = _manifest_rows(_load_json(manifest_path))
    selected_rows = [row for row in rows if row["required"] or not required_only]
    selected_names = {row["asset_name"] for row in selected_rows}

    upload_assets: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in selected_rows:
        candidate = artifact_root / row["asset_name"]
        if not candidate.is_file():
            errors.append(f"missing asset: {row['asset_name']}")
            continue
        actual_bytes = candidate.stat().st_size
        if actual_bytes != row["bytes"]:
            errors.append(
                f"bytes mismatch for {row['asset_name']}: "
                f"manifest={row['bytes']} actual={actual_bytes}"
            )
            continue
        actual_sha = _sha256(candidate)
        if actual_sha != row["sha256"]:
            errors.append(
                f"sha256 mismatch for {row['asset_name']}: "
                f"manifest={row['sha256']} actual={actual_sha}"
            )
            continue
        upload_assets.append(
            {
                "asset_name": row["asset_name"],
                "path": str(candidate),
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "required": row["required"],
            }
        )

    root_files = _relative_files(artifact_root)
    extra_files = [name for name in root_files if name not in selected_names]
    plan = {
        "ok": not errors,
        "release_tag": release_tag,
        "artifact_root": str(artifact_root),
        "required_only": required_only,
        "upload_assets": upload_assets,
        "extra_files": extra_files,
        "errors": errors,
        "totals": {
            "manifest_assets": len(rows),
            "selected_assets": len(selected_rows),
            "upload_assets": len(upload_assets),
            "extra_files": len(extra_files),
            "errors": len(errors),
        },
    }
    if errors:
        raise ValueError("; ".join(errors))
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a safe upload plan from a fresh release asset root. "
            "Only manifest-listed asset_name files are included; extra files are reported "
            "so operators do not wildcard-upload stale bundles or private keys."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Optional JSON output path for the upload plan.")
    parser.add_argument(
        "--required-only",
        action="store_true",
        help="Plan only required manifest assets and ignore optional manifest assets.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = prepare_release_upload_plan(
            args.manifest,
            args.artifact_root,
            required_only=args.required_only,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Release upload plan check failed: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(plan, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
