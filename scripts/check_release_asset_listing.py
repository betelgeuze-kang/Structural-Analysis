#!/usr/bin/env python3
"""Preflight GitHub Release asset metadata against the release manifest.

This helper intentionally reads only listing metadata from an offline JSON file.
It never downloads release assets and never modifies release artifact files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_manifest_artifacts(manifest: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")

    release_tag = str(manifest.get("release_tag", "") or "")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("manifest artifacts must be a list")

    rows: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ValueError(f"manifest artifacts[{index}] must be an object")
        name = str(artifact.get("asset_name", artifact.get("name", "")) or "").strip()
        bytes_value = artifact.get("bytes")
        required = artifact.get("required", False)
        if not name:
            raise ValueError(f"manifest artifacts[{index}] asset_name is required")
        if not isinstance(bytes_value, int) or bytes_value < 0:
            raise ValueError(f"manifest artifacts[{index}] bytes must be a non-negative integer")
        if not isinstance(required, bool):
            raise ValueError(f"manifest artifacts[{index}] required must be boolean")
        rows.append({"name": name, "bytes": bytes_value, "required": required})
    return release_tag, rows


def _looks_like_asset(row: Any) -> bool:
    return isinstance(row, dict) and "name" in row and "size" in row


def _extract_asset_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("assets"), list):
            return _extract_asset_rows(payload["assets"])
        if isinstance(payload.get("release"), dict) and isinstance(payload["release"].get("assets"), list):
            return _extract_asset_rows(payload["release"]["assets"])
        raise ValueError("assets JSON object must contain an assets list")

    if not isinstance(payload, list):
        raise ValueError("assets JSON must be an array or an object containing assets")

    if all(_looks_like_asset(row) for row in payload):
        return payload

    flattened: list[dict[str, Any]] = []
    for row in payload:
        if isinstance(row, dict) and isinstance(row.get("assets"), list):
            flattened.extend(_extract_asset_rows(row["assets"]))
    if flattened:
        return flattened

    raise ValueError("assets JSON list must contain asset objects or release objects with assets")


def _extract_assets(payload: Any) -> dict[str, int]:
    assets: dict[str, int] = {}
    for index, row in enumerate(_extract_asset_rows(payload)):
        name = str(row.get("name", "") or "").strip()
        size = row.get("size")
        if not name:
            raise ValueError(f"assets[{index}].name is required")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"assets[{index}].size must be a non-negative integer")
        if name not in assets:
            assets[name] = size
    return assets


def check_release_asset_listing(
    manifest_path: Path,
    assets_json_path: Path,
    *,
    require_all: bool = False,
) -> dict[str, Any]:
    release_tag, manifest_artifacts = _extract_manifest_artifacts(_load_json(manifest_path))
    listed_assets = _extract_assets(_load_json(assets_json_path))

    matched: list[dict[str, Any]] = []
    missing_required: list[dict[str, Any]] = []
    missing_optional: list[dict[str, Any]] = []
    size_mismatches: list[dict[str, Any]] = []
    manifest_names: set[str] = set()

    for artifact in manifest_artifacts:
        name = artifact["name"]
        expected_bytes = artifact["bytes"]
        required = artifact["required"]
        manifest_names.add(name)

        if name not in listed_assets:
            missing = {"name": name, "expected_bytes": expected_bytes}
            if required:
                missing_required.append(missing)
            else:
                missing_optional.append(missing)
            continue

        actual_bytes = listed_assets[name]
        if actual_bytes != expected_bytes:
            size_mismatches.append(
                {
                    "name": name,
                    "expected_bytes": expected_bytes,
                    "actual_bytes": actual_bytes,
                    "required": required,
                }
            )
            continue

        matched.append({"name": name, "bytes": expected_bytes, "required": required})

    extra_assets = [
        {"name": name, "bytes": listed_assets[name]}
        for name in sorted(set(listed_assets) - manifest_names)
    ]

    should_fail = bool(size_mismatches) or bool(require_all and missing_required)
    return {
        "ok": not should_fail,
        "exit_code": 1 if should_fail else 0,
        "release_tag": release_tag,
        "matched": matched,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "size_mismatches": size_mismatches,
        "extra_assets": extra_assets,
        "totals": {
            "manifest_assets": len(manifest_artifacts),
            "listed_assets": len(listed_assets),
            "matched": len(matched),
            "missing_required": len(missing_required),
            "missing_optional": len(missing_optional),
            "size_mismatches": len(size_mismatches),
            "extra_assets": len(extra_assets),
        },
    }


def _print_human(summary: dict[str, Any]) -> None:
    totals = summary["totals"]
    print(f"Release asset listing preflight for {summary['release_tag'] or '(unknown release)'}")
    print(
        "Totals: "
        f"manifest={totals['manifest_assets']} listed={totals['listed_assets']} "
        f"matched={totals['matched']} missing_required={totals['missing_required']} "
        f"missing_optional={totals['missing_optional']} mismatched={totals['size_mismatches']} "
        f"extra={totals['extra_assets']}"
    )

    for label, key in (
        ("Missing required", "missing_required"),
        ("Missing optional", "missing_optional"),
        ("Size mismatch", "size_mismatches"),
        ("Extra asset", "extra_assets"),
    ):
        for row in summary[key]:
            if key == "size_mismatches":
                print(
                    f"{label}: {row['name']} "
                    f"expected={row['expected_bytes']} actual={row['actual_bytes']}"
                )
            elif key == "extra_assets":
                print(f"{label}: {row['name']} bytes={row['bytes']}")
            else:
                print(f"{label}: {row['name']} expected={row['expected_bytes']}")

    has_warnings = bool(summary["missing_required"] or summary["missing_optional"] or summary["extra_assets"])
    if summary["ok"] and has_warnings:
        print("Release asset listing preflight completed with warnings")
    elif summary["ok"]:
        print("Release asset listing preflight OK")
    else:
        print("Release asset listing preflight failed", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare GitHub Release asset name/size listing metadata against "
            "implementation/phase1/release_artifacts_manifest.json before any large SHA download. "
            "Size mismatches always fail. Missing required assets are warnings by default and "
            "fail only with --require-all. Optional missing assets never fail."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--assets-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON summary.")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Fail when any required manifest asset is missing from the release asset listing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        summary = check_release_asset_listing(
            args.manifest,
            args.assets_json,
            require_all=args.require_all,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "exit_code": 2, "error": str(exc)}, sort_keys=True))
        else:
            print(f"Release asset listing preflight error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        _print_human(summary)
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
