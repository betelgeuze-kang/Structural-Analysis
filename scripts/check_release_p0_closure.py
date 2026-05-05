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


def _manifest_artifact_index(manifest: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(manifest, dict):
        return {}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in artifacts:
        if not isinstance(row, dict):
            continue
        asset_name = str(row.get("asset_name", "") or "").strip()
        if asset_name:
            rows[asset_name] = row
    return rows


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _upload_plan_evidence_status(
    *,
    upload_plan_json: Path | None,
    manifest: Any,
    release_tag: str,
) -> dict[str, Any]:
    if upload_plan_json is None:
        return {
            "checked": False,
            "evidence_json": None,
            "evidence_ok": None,
            "errors": [],
            "counts": {},
        }

    errors: list[str] = []
    try:
        payload = _load_json(upload_plan_json)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "checked": True,
            "evidence_json": str(upload_plan_json),
            "evidence_ok": False,
            "errors": [str(exc)],
            "counts": {},
        }
    if not isinstance(payload, dict):
        return {
            "checked": True,
            "evidence_json": str(upload_plan_json),
            "evidence_ok": False,
            "errors": ["upload plan evidence root must be an object"],
            "counts": {},
        }

    if payload.get("ok") is not True:
        errors.append("upload plan evidence ok must be true")
    if release_tag and str(payload.get("release_tag", "") or "") != release_tag:
        errors.append(
            f"upload plan release_tag mismatch: manifest={release_tag} "
            f"evidence={payload.get('release_tag', '')}"
        )
    for error in _json_list(payload.get("errors")):
        errors.append(f"upload plan evidence error: {error}")

    manifest_rows = _manifest_artifact_index(manifest)
    upload_assets = payload.get("upload_assets")
    if not isinstance(upload_assets, list):
        errors.append("upload plan upload_assets must be a list")
        upload_assets = []

    seen: set[str] = set()
    for index, row in enumerate(upload_assets):
        if not isinstance(row, dict):
            errors.append(f"upload plan upload_assets[{index}] must be an object")
            continue
        asset_name = str(row.get("asset_name", "") or "").strip()
        if not asset_name:
            errors.append(f"upload plan upload_assets[{index}].asset_name is required")
            continue
        if asset_name in seen:
            errors.append(f"upload plan duplicate asset: {asset_name}")
        seen.add(asset_name)
        manifest_row = manifest_rows.get(asset_name)
        if manifest_row is None:
            errors.append(f"upload plan contains non-manifest asset: {asset_name}")
            continue
        expected_bytes = manifest_row.get("bytes")
        actual_bytes = row.get("bytes")
        if actual_bytes != expected_bytes:
            errors.append(
                f"upload plan bytes mismatch for {asset_name}: "
                f"manifest={expected_bytes} evidence={actual_bytes}"
            )
        expected_sha = str(manifest_row.get("sha256", "") or "")
        actual_sha = str(row.get("sha256", "") or "")
        if actual_sha != expected_sha:
            errors.append(
                f"upload plan sha256 mismatch for {asset_name}: "
                f"manifest={expected_sha} evidence={actual_sha}"
            )
        expected_required = bool(manifest_row.get("required", False))
        if row.get("required") is not expected_required:
            errors.append(
                f"upload plan required mismatch for {asset_name}: "
                f"manifest={expected_required} evidence={row.get('required')}"
            )

    for asset_name in sorted(set(manifest_rows) - seen):
        errors.append(f"upload plan missing manifest asset: {asset_name}")

    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    return {
        "checked": True,
        "evidence_json": str(upload_plan_json),
        "evidence_ok": not errors,
        "errors": errors,
        "counts": {
            "manifest_assets": totals.get("manifest_assets", len(manifest_rows)),
            "upload_assets": totals.get("upload_assets", len(upload_assets)),
            "extra_files": totals.get("extra_files", len(_json_list(payload.get("extra_files")))),
            "errors": len(errors),
        },
    }


def _merge_upload_plan_status(
    base_status: dict[str, Any],
    evidence_status: dict[str, Any],
) -> dict[str, Any]:
    checked = bool(base_status.get("checked")) or bool(evidence_status.get("checked"))
    errors = list(base_status.get("errors", [])) + list(evidence_status.get("errors", []))
    if not checked:
        ok: bool | None = None
    else:
        ok = not errors and (
            not bool(base_status.get("checked")) or base_status.get("ok") is True
        ) and (
            not bool(evidence_status.get("checked")) or evidence_status.get("evidence_ok") is True
        )
    return {
        **base_status,
        "checked": checked,
        "ok": ok,
        "errors": errors,
        "evidence_json": evidence_status.get("evidence_json"),
        "evidence_ok": evidence_status.get("evidence_ok"),
        "evidence_counts": evidence_status.get("counts", {}),
    }


def _metadata_preflight_status(metadata_preflight_json: Path | None, manifest: Any) -> dict[str, Any]:
    if metadata_preflight_json is None:
        return {
            "checked": False,
            "ok": None,
            "evidence_json": None,
            "errors": [],
            "counts": {},
        }

    errors: list[str] = []
    try:
        payload = _load_json(metadata_preflight_json)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "checked": True,
            "ok": False,
            "evidence_json": str(metadata_preflight_json),
            "errors": [str(exc)],
            "counts": {},
        }
    if not isinstance(payload, dict):
        return {
            "checked": True,
            "ok": False,
            "evidence_json": str(metadata_preflight_json),
            "errors": ["metadata preflight evidence root must be an object"],
            "counts": {},
        }

    if payload.get("ok") is not True:
        errors.append("metadata preflight ok must be true")
    for error in _json_list(payload.get("manifest_errors", payload.get("errors"))):
        errors.append(f"metadata preflight manifest error: {error}")

    manifest_rows = _manifest_artifact_index(manifest)
    present = payload.get("present")
    if not isinstance(present, list):
        errors.append("metadata preflight present must be a list")
        present = []

    seen: set[str] = set()
    for index, row in enumerate(present):
        if not isinstance(row, dict):
            errors.append(f"metadata preflight present[{index}] must be an object")
            continue
        asset_name = str(row.get("asset_name", "") or "").strip()
        if not asset_name:
            errors.append(f"metadata preflight present[{index}].asset_name is required")
            continue
        if asset_name in seen:
            errors.append(f"metadata preflight duplicate asset: {asset_name}")
        seen.add(asset_name)
        manifest_row = manifest_rows.get(asset_name)
        if manifest_row is None:
            errors.append(f"metadata preflight contains non-manifest asset: {asset_name}")
            continue
        expected_bytes = manifest_row.get("bytes")
        actual_expected_bytes = row.get("expected_bytes")
        if actual_expected_bytes != expected_bytes:
            errors.append(
                f"metadata preflight bytes mismatch for {asset_name}: "
                f"manifest={expected_bytes} evidence={actual_expected_bytes}"
            )
        actual_bytes = row.get("actual_bytes")
        if actual_bytes is not None and actual_bytes != expected_bytes:
            errors.append(
                f"metadata preflight actual bytes mismatch for {asset_name}: "
                f"manifest={expected_bytes} evidence={actual_bytes}"
            )
        expected_sha = str(manifest_row.get("sha256", "") or "")
        actual_expected_sha = str(row.get("expected_sha256", "") or "")
        if actual_expected_sha != expected_sha:
            errors.append(
                f"metadata preflight sha256 mismatch for {asset_name}: "
                f"manifest={expected_sha} evidence={actual_expected_sha}"
            )
        expected_required = bool(manifest_row.get("required", False))
        if row.get("required") is not expected_required:
            errors.append(
                f"metadata preflight required mismatch for {asset_name}: "
                f"manifest={expected_required} evidence={row.get('required')}"
            )
        if str(row.get("status", "") or "") != "present":
            errors.append(f"metadata preflight asset is not present: {asset_name}")

    for asset_name in sorted(set(manifest_rows) - seen):
        errors.append(f"metadata preflight missing manifest asset: {asset_name}")
    for key in ("required_missing", "optional_missing"):
        for row in _json_list(payload.get(key)):
            if isinstance(row, dict):
                name = str(row.get("asset_name", row.get("name", "")) or "")
            else:
                name = str(row)
            errors.append(f"metadata preflight {key} contains {name or 'unknown asset'}")

    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    return {
        "checked": True,
        "ok": not errors,
        "evidence_json": str(metadata_preflight_json),
        "errors": errors,
        "counts": {
            "manifest_assets": totals.get("manifest_assets", len(manifest_rows)),
            "present": totals.get("present", len(present)),
            "required_missing": totals.get("required_missing", 0),
            "optional_missing": totals.get("optional_missing", 0),
            "errors": len(errors),
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


def _post_publish_roundtrip_status(roundtrip_json: Path | None, manifest: Any) -> dict[str, Any]:
    if roundtrip_json is None:
        return {
            "checked": False,
            "ok": None,
            "evidence_json": None,
            "errors": [],
            "counts": {},
        }

    errors: list[str] = []
    try:
        payload = _load_json(roundtrip_json)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "checked": True,
            "ok": False,
            "evidence_json": str(roundtrip_json),
            "errors": [str(exc)],
            "counts": {},
        }
    if not isinstance(payload, dict):
        return {
            "checked": True,
            "ok": False,
            "evidence_json": str(roundtrip_json),
            "errors": ["post-publish roundtrip evidence root must be an object"],
            "counts": {},
        }
    if payload.get("ok") is not True:
        errors.append("post-publish roundtrip ok must be true")
    for error in _json_list(payload.get("errors")):
        errors.append(f"post-publish roundtrip evidence error: {error}")

    manifest_rows = _manifest_artifact_index(manifest)
    actions = payload.get("actions")
    if not isinstance(actions, list):
        errors.append("post-publish roundtrip actions must be a list")
        actions = []

    seen: set[str] = set()
    for index, row in enumerate(actions):
        if not isinstance(row, dict):
            errors.append(f"post-publish roundtrip actions[{index}] must be an object")
            continue
        asset_name = str(row.get("asset_name", "") or "").strip()
        if not asset_name:
            errors.append(f"post-publish roundtrip actions[{index}].asset_name is required")
            continue
        if asset_name in seen:
            errors.append(f"post-publish roundtrip duplicate asset: {asset_name}")
        seen.add(asset_name)
        manifest_row = manifest_rows.get(asset_name)
        if manifest_row is None:
            errors.append(f"post-publish roundtrip contains non-manifest asset: {asset_name}")
            continue
        status = str(row.get("status", "") or "")
        if status not in {"already_present", "downloaded"}:
            errors.append(f"post-publish roundtrip asset is not verified: {asset_name} status={status}")
        expected_bytes = manifest_row.get("bytes")
        if row.get("manifest_bytes") != expected_bytes:
            errors.append(
                f"post-publish roundtrip manifest bytes mismatch for {asset_name}: "
                f"manifest={expected_bytes} evidence={row.get('manifest_bytes')}"
            )
        expected_sha = str(manifest_row.get("sha256", "") or "")
        if str(row.get("manifest_sha256", "") or "") != expected_sha:
            errors.append(
                f"post-publish roundtrip manifest sha256 mismatch for {asset_name}: "
                f"manifest={expected_sha} evidence={row.get('manifest_sha256')}"
            )
        actual_bytes = row.get("downloaded_bytes", row.get("destination_bytes"))
        if actual_bytes is not None and actual_bytes != expected_bytes:
            errors.append(
                f"post-publish roundtrip actual bytes mismatch for {asset_name}: "
                f"manifest={expected_bytes} evidence={actual_bytes}"
            )
        actual_sha = str(row.get("downloaded_sha256", row.get("destination_sha256", "")) or "")
        if actual_sha and actual_sha != expected_sha:
            errors.append(
                f"post-publish roundtrip actual sha256 mismatch for {asset_name}: "
                f"manifest={expected_sha} evidence={actual_sha}"
            )

    for asset_name in sorted(set(manifest_rows) - seen):
        errors.append(f"post-publish roundtrip missing manifest asset: {asset_name}")

    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    return {
        "checked": True,
        "ok": not errors,
        "evidence_json": str(roundtrip_json),
        "errors": errors,
        "counts": {
            "manifest_assets": len(manifest_rows),
            "selected_assets": totals.get("selected_assets", len(actions)),
            "already_present": totals.get("already_present", 0),
            "downloaded": totals.get("downloaded", 0),
            "errors": len(errors),
        },
    }


def _split_error_message(message: str) -> list[str]:
    if not message:
        return ["unknown error"]
    return [part.strip() for part in message.split(";") if part.strip()]


def build_status(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    promoted_manifest_json: Path | None = None,
    artifact_root: Path | None = None,
    assets_json: Path | None = None,
    upload_plan_json: Path | None = None,
    metadata_preflight_json: Path | None = None,
    post_publish_roundtrip_json: Path | None = None,
    require_all: bool = False,
    require_exact: bool = True,
    tag_ref_present: bool | None = None,
) -> dict[str, Any]:
    """Return a no-network P0 closure status composed from existing checks."""

    publication_manifest_path = promoted_manifest_json or manifest_path
    manifest_status, manifest = _manifest_status(publication_manifest_path)
    release_tag = ""
    if isinstance(manifest, dict):
        release_tag = str(manifest.get("release_tag", "") or "")

    upload_checked = artifact_root is not None or upload_plan_json is not None
    metadata_checked = metadata_preflight_json is not None
    roundtrip_checked = post_publish_roundtrip_json is not None
    upload_status = _merge_upload_plan_status(
        _upload_plan_status(publication_manifest_path, artifact_root),
        _upload_plan_evidence_status(
            upload_plan_json=upload_plan_json,
            manifest=manifest,
            release_tag=release_tag,
        ),
    ) if manifest_status["ok"] else {
        "checked": upload_checked,
        "ok": False if upload_checked else None,
        "artifact_root": str(artifact_root) if artifact_root is not None else None,
        "errors": ["skipped because manifest structure is invalid"] if upload_checked else [],
        "counts": {},
        "evidence_json": str(upload_plan_json) if upload_plan_json is not None else None,
        "evidence_ok": False if upload_plan_json is not None else None,
        "evidence_counts": {},
    }
    metadata_status = _metadata_preflight_status(
        metadata_preflight_json,
        manifest,
    ) if manifest_status["ok"] else {
        "checked": metadata_checked,
        "ok": False if metadata_checked else None,
        "evidence_json": str(metadata_preflight_json) if metadata_preflight_json is not None else None,
        "errors": ["skipped because manifest structure is invalid"] if metadata_checked else [],
        "counts": {},
    }
    asset_status = _asset_listing_status(
        publication_manifest_path,
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
    roundtrip_status = _post_publish_roundtrip_status(
        post_publish_roundtrip_json,
        manifest,
    ) if manifest_status["ok"] else {
        "checked": roundtrip_checked,
        "ok": False if roundtrip_checked else None,
        "evidence_json": str(post_publish_roundtrip_json) if post_publish_roundtrip_json is not None else None,
        "errors": ["skipped because manifest structure is invalid"] if roundtrip_checked else [],
        "counts": {},
    }
    tag_status = _tag_ref_status(tag_ref_present)

    upload_closed = not bool(upload_status.get("checked")) or upload_status["ok"] is True
    metadata_closed = not bool(metadata_status.get("checked")) or metadata_status["ok"] is True
    roundtrip_closed = not bool(roundtrip_status.get("checked")) or roundtrip_status["ok"] is True
    p0_closed = (
        manifest_status["ok"] is True
        and tag_ref_present is True
        and asset_status["ok"] is True
        and upload_closed
        and metadata_closed
        and roundtrip_closed
    )
    return {
        "ok": p0_closed,
        "p0_closed": p0_closed,
        "status": "closed" if p0_closed else "unclosed",
        "release_tag": release_tag,
        "source_manifest": str(manifest_path),
        "publication_manifest": str(publication_manifest_path),
        "publication_manifest_source": "promoted" if promoted_manifest_json is not None else "local",
        "manifest": manifest_status,
        "tag_ref": tag_status,
        "asset_listing": asset_status,
        "upload_plan": upload_status,
        "metadata_preflight": metadata_status,
        "post_publish_roundtrip": roundtrip_status,
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

    metadata = status["metadata_preflight"]
    if not metadata["checked"]:
        print("Metadata preflight: not checked")
    else:
        metadata_label = "ok" if metadata["ok"] else "error"
        counts = _format_counts(metadata["counts"])
        suffix = f" ({counts})" if counts else ""
        print(f"Metadata preflight: {metadata_label}{suffix}")
        for error in metadata["errors"]:
            print(f"  - {error}")

    roundtrip = status["post_publish_roundtrip"]
    if not roundtrip["checked"]:
        print("Post-publish roundtrip: not checked")
    else:
        roundtrip_label = "ok" if roundtrip["ok"] else "error"
        counts = _format_counts(roundtrip["counts"])
        suffix = f" ({counts})" if counts else ""
        print(f"Post-publish roundtrip: {roundtrip_label}{suffix}")
        for error in roundtrip["errors"]:
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
    parser.add_argument(
        "--promoted-manifest-json",
        type=Path,
        help=(
            "Use this already-promoted release manifest as the publication evidence baseline. "
            "This keeps stale repo-local manifests from reopening a release that is already "
            "published and promoted elsewhere."
        ),
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--assets-json", type=Path)
    parser.add_argument("--upload-plan-json", type=Path)
    parser.add_argument("--metadata-preflight-json", type=Path)
    parser.add_argument("--post-publish-roundtrip-json", type=Path)
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
        promoted_manifest_json=args.promoted_manifest_json,
        artifact_root=args.artifact_root,
        assets_json=args.assets_json,
        upload_plan_json=args.upload_plan_json,
        metadata_preflight_json=args.metadata_preflight_json,
        post_publish_roundtrip_json=args.post_publish_roundtrip_json,
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
