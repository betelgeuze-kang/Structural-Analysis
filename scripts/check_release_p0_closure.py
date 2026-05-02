#!/usr/bin/env python3
"""Compose offline release checks into a P0 closure status gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_release_asset_listing import check_release_asset_listing  # noqa: E402
from prepare_release_upload_plan import prepare_release_upload_plan  # noqa: E402
from verify_release_artifacts_manifest import SCHEMA_VERSION as _RELEASE_MANIFEST_SCHEMA_VERSION  # noqa: E402
from verify_release_artifacts_manifest import validate_manifest  # noqa: E402


DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")
RELEASE_MANIFEST_SCHEMA_VERSION = _RELEASE_MANIFEST_SCHEMA_VERSION


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tag_ref_status(tag_ref_present: bool | None) -> dict[str, Any]:
    if tag_ref_present is True:
        status = "present"
    elif tag_ref_present is False:
        status = "missing"
    else:
        status = "unknown"
    return {"present": tag_ref_present, "status": status}


def _manifest_status(manifest_path: Path) -> tuple[dict[str, Any], Any | None]:
    try:
        manifest = _load_json(manifest_path)
        errors = validate_manifest(manifest, structure_only=True)
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "path": str(manifest_path), "errors": [str(exc)]}, None

    release_tag = ""
    if isinstance(manifest, dict):
        release_tag = str(manifest.get("release_tag", "") or "")
    return {
        "ok": not errors,
        "path": str(manifest_path),
        "release_tag": release_tag,
        "errors": errors,
    }, manifest


def _upload_plan_status(manifest_path: Path, artifact_root: Path | None) -> dict[str, Any]:
    if artifact_root is None:
        return {"checked": False, "ok": None, "artifact_root": None, "errors": [], "counts": {}}

    try:
        plan = prepare_release_upload_plan(manifest_path, artifact_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "checked": True,
            "ok": False,
            "artifact_root": str(artifact_root),
            "errors": _split_error_message(str(exc)),
            "counts": {},
        }

    totals = plan.get("totals", {})
    return {
        "checked": True,
        "ok": True,
        "artifact_root": str(artifact_root),
        "errors": [],
        "counts": {
            "manifest_assets": totals.get("manifest_assets", 0),
            "selected_assets": totals.get("selected_assets", 0),
            "upload_assets": totals.get("upload_assets", 0),
            "extra_files": totals.get("extra_files", 0),
            "errors": totals.get("errors", 0),
        },
    }


def _asset_listing_status(
    manifest_path: Path,
    assets_json: Path | None,
    *,
    require_all: bool,
    require_exact: bool,
) -> dict[str, Any]:
    if assets_json is None:
        return {
            "checked": False,
            "ok": None,
            "assets_json": None,
            "require_all": require_all,
            "require_exact": require_exact,
            "errors": [],
            "counts": {},
        }

    try:
        summary = check_release_asset_listing(
            manifest_path,
            assets_json,
            require_all=require_all,
            require_exact=require_exact,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "checked": True,
            "ok": False,
            "assets_json": str(assets_json),
            "require_all": require_all,
            "require_exact": require_exact,
            "errors": [str(exc)],
            "counts": {},
        }

    totals = summary.get("totals", {})
    missing_required = totals.get("missing_required", len(summary.get("missing_required", [])))
    missing_optional = totals.get("missing_optional", len(summary.get("missing_optional", [])))
    size_mismatches = totals.get("size_mismatches", len(summary.get("size_mismatches", [])))
    extra_assets = totals.get("extra_assets", len(summary.get("extra_assets", [])))
    exact_ok = not require_exact or (
        missing_required == 0
        and missing_optional == 0
        and size_mismatches == 0
        and extra_assets == 0
    )
    return {
        "checked": True,
        "ok": bool(summary.get("ok")) and missing_required == 0 and size_mismatches == 0 and exact_ok,
        "assets_json": str(assets_json),
        "require_all": require_all,
        "require_exact": require_exact,
        "errors": [],
        "counts": {
            "manifest_assets": totals.get("manifest_assets", 0),
            "listed_assets": totals.get("listed_assets", 0),
            "matched": totals.get("matched", 0),
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "mismatched": size_mismatches,
            "extra_assets": extra_assets,
        },
    }


def _split_error_message(message: str) -> list[str]:
    if not message:
        return ["unknown error"]
    return [part.strip() for part in message.split(";") if part.strip()]


def build_status(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    artifact_root: Path | None = None,
    assets_json: Path | None = None,
    require_all: bool = False,
    require_exact: bool = True,
    tag_ref_present: bool | None = None,
) -> dict[str, Any]:
    """Return a no-network P0 closure status composed from existing checks."""

    manifest_status, manifest = _manifest_status(manifest_path)
    release_tag = ""
    if isinstance(manifest, dict):
        release_tag = str(manifest.get("release_tag", "") or "")

    upload_status = _upload_plan_status(manifest_path, artifact_root) if manifest_status["ok"] else {
        "checked": artifact_root is not None,
        "ok": False if artifact_root is not None else None,
        "artifact_root": str(artifact_root) if artifact_root is not None else None,
        "errors": ["skipped because manifest structure is invalid"] if artifact_root is not None else [],
        "counts": {},
    }
    asset_status = _asset_listing_status(
        manifest_path,
        assets_json,
        require_all=require_all,
        require_exact=require_exact,
    ) if manifest_status["ok"] else {
        "checked": assets_json is not None,
        "ok": False if assets_json is not None else None,
        "assets_json": str(assets_json) if assets_json is not None else None,
        "require_all": require_all,
        "require_exact": require_exact,
        "errors": ["skipped because manifest structure is invalid"] if assets_json is not None else [],
        "counts": {},
    }
    tag_status = _tag_ref_status(tag_ref_present)

    upload_closed = artifact_root is None or upload_status["ok"] is True
    p0_closed = (
        manifest_status["ok"] is True
        and tag_ref_present is True
        and asset_status["ok"] is True
        and upload_closed
    )
    return {
        "ok": p0_closed,
        "p0_closed": p0_closed,
        "status": "closed" if p0_closed else "unclosed",
        "release_tag": release_tag,
        "manifest": manifest_status,
        "tag_ref": tag_status,
        "asset_listing": asset_status,
        "upload_plan": upload_status,
    }


def _format_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return ""
    return " ".join(f"{key}={value}" for key, value in counts.items())


def _print_text(status: dict[str, Any]) -> None:
    release_tag = status["release_tag"] or "(unknown release)"
    print(f"P0 closure: {status['status']} for {release_tag}")

    manifest = status["manifest"]
    manifest_label = "ok" if manifest["ok"] else "error"
    print(f"Manifest: {manifest_label} ({manifest['path']})")
    for error in manifest["errors"]:
        print(f"  - {error}")

    tag_ref = status["tag_ref"]
    print(f"Tag ref: {tag_ref['status']}")

    assets = status["asset_listing"]
    if not assets["checked"]:
        print("Asset listing: not checked")
    else:
        asset_label = "ok" if assets["ok"] else "error"
        counts = _format_counts(assets["counts"])
        suffix = f" ({counts})" if counts else ""
        print(f"Asset listing: {asset_label}{suffix}")
        for error in assets["errors"]:
            print(f"  - {error}")

    upload = status["upload_plan"]
    if not upload["checked"]:
        print("Upload plan: not checked")
    else:
        upload_label = "ok" if upload["ok"] else "error"
        counts = _format_counts(upload["counts"])
        suffix = f" ({counts})" if counts else ""
        print(f"Upload plan: {upload_label}{suffix}")
        for error in upload["errors"]:
            print(f"  - {error}")


def _parse_tag_ref_present(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("--tag-ref-present must be true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report P0 release closure status by composing local manifest, upload-plan, "
            "and offline asset-listing checks. This command never fetches network data "
            "and never uploads assets. Asset listing checks are exact by default for P0 closure."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--assets-json", type=Path)
    parser.add_argument("--require-all", action="store_true")
    parser.set_defaults(require_exact=True)
    parser.add_argument(
        "--require-exact",
        dest="require_exact",
        action="store_true",
        help="Require the published asset listing to exactly match manifest names and sizes. Enabled by default.",
    )
    parser.add_argument(
        "--allow-non-exact",
        dest="require_exact",
        action="store_false",
        help="Diagnostic mode only: allow optional missing or extra listed assets when checking P0 closure.",
    )
    parser.add_argument("--tag-ref-present", type=_parse_tag_ref_present, choices=(True, False))
    parser.add_argument("--fail-unclosed", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON status.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    status = build_status(
        manifest_path=args.manifest,
        artifact_root=args.artifact_root,
        assets_json=args.assets_json,
        require_all=args.require_all,
        require_exact=args.require_exact,
        tag_ref_present=args.tag_ref_present,
    )

    if args.json:
        print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    else:
        _print_text(status)

    if args.fail_unclosed and not status["p0_closed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
