#!/usr/bin/env python3
"""Download and verify manifest-listed assets from a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen as urllib_urlopen


GITHUB_API = "https://api.github.com"
DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")
DEFAULT_TIMEOUT_SECONDS = 120


class HydrateReleaseAssetsError(RuntimeError):
    """Raised when release asset hydration cannot be completed safely."""


def _token_from_env(token_env: str) -> str | None:
    token = os.environ.get(token_env)
    if token:
        return token
    if token_env == "GITHUB_TOKEN":
        return os.environ.get("GH_TOKEN") or None
    return None


def _headers(token: str | None, *, accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "arch-struct-analysis-release-asset-hydrator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _repo_parts(repo: str) -> tuple[str, str]:
    parts = [part.strip() for part in repo.split("/")]
    if len(parts) != 2 or not all(parts):
        raise HydrateReleaseAssetsError("--repo must be in owner/name format")
    return parts[0], parts[1]


def _release_by_tag_url(repo: str, tag: str) -> str:
    owner, name = _repo_parts(repo)
    return f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(name, safe='')}/releases/tags/{quote(tag, safe='')}"


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


def _contains_private_key_marker(path: Path) -> bool:
    try:
        return b"PRIVATE KEY" in path.read_bytes()[:8192].upper()
    except OSError:
        return False


def _asset_is_private_key_like(asset_name: str) -> bool:
    lower_name = asset_name.lower()
    return lower_name.endswith(".pem") and not lower_name.endswith(".pub.pem")


def _manifest_rows(manifest: Any, *, tag_override: str = "", required_only: bool = False) -> tuple[str, list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return "", [], ["manifest root must be an object"]

    release_tag = str(tag_override or manifest.get("release_tag", "") or "").strip()
    if not release_tag:
        errors.append("release_tag is required")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest artifacts must be a non-empty list")
        return release_tag, [], errors

    rows: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        row_error_count = len(errors)
        asset_name = str(artifact.get("asset_name", artifact.get("name", "")) or "").strip()
        local_path = str(artifact.get("local_path", "") or "").strip()
        bytes_value = artifact.get("bytes")
        sha256 = str(artifact.get("sha256", "") or "").strip()
        required = artifact.get("required")

        if not _is_single_file_name(asset_name):
            errors.append(f"artifacts[{index}].asset_name must be a single file name")
        elif asset_name in seen_assets:
            errors.append(f"duplicate asset_name: {asset_name}")
        seen_assets.add(asset_name)

        if local_path and not _is_clean_relative_path(local_path):
            errors.append(f"artifacts[{index}].local_path must be a clean relative path")
        if not isinstance(bytes_value, int) or bytes_value <= 0:
            errors.append(f"artifacts[{index}].bytes must be a positive integer")
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            errors.append(f"artifacts[{index}].sha256 must be a lowercase 64-char hex digest")
        if not isinstance(required, bool):
            errors.append(f"artifacts[{index}].required must be boolean")
        if _asset_is_private_key_like(asset_name):
            errors.append(f"unsafe private key-like asset name: {asset_name}")

        if len(errors) == row_error_count and (required or not required_only):
            rows.append(
                {
                    "asset_name": asset_name,
                    "bytes": bytes_value,
                    "sha256": sha256,
                    "required": required,
                    "local_path": local_path,
                }
            )
    return release_tag, rows, errors


def _release_payload(
    repo: str,
    tag: str,
    *,
    token: str | None,
    urlopen: Callable[..., Any],
) -> Any:
    request = Request(_release_by_tag_url(repo, tag), headers=_headers(token))
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise HydrateReleaseAssetsError(
                "GitHub release was not found. Check the tag, repository visibility, and token permissions."
            ) from exc
        raise HydrateReleaseAssetsError(f"GitHub API returned HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise HydrateReleaseAssetsError(f"GitHub API request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise HydrateReleaseAssetsError(f"GitHub API response was not valid JSON: {exc}") from exc


def _release_assets_by_name(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise HydrateReleaseAssetsError("GitHub release response must be an object")
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise HydrateReleaseAssetsError("GitHub release response assets must be a list")

    by_name: dict[str, dict[str, Any]] = {}
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise HydrateReleaseAssetsError(f"release assets[{index}] must be an object")
        name = asset.get("name")
        size = asset.get("size")
        api_url = asset.get("url")
        if not isinstance(name, str) or not name.strip():
            raise HydrateReleaseAssetsError(f"release assets[{index}].name must be a non-empty string")
        if not isinstance(size, int) or size < 0:
            raise HydrateReleaseAssetsError(f"release assets[{index}].size must be a non-negative integer")
        if not isinstance(api_url, str) or not api_url.strip():
            raise HydrateReleaseAssetsError(f"release assets[{index}].url must be a non-empty string")
        by_name.setdefault(name, {"name": name, "size": size, "url": api_url})
    return by_name


def _download_asset_bytes(
    api_url: str,
    *,
    token: str | None,
    urlopen: Callable[..., Any],
) -> bytes:
    request = Request(api_url, headers=_headers(token, accept="application/octet-stream"))
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return response.read()
    except HTTPError as exc:
        raise HydrateReleaseAssetsError(f"GitHub asset download returned HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise HydrateReleaseAssetsError(f"GitHub asset download failed: {exc.reason}") from exc


def _existing_status(destination: Path, row: dict[str, Any]) -> tuple[str, int | None, str | None]:
    if not destination.exists():
        return "missing", None, None
    if not destination.is_file():
        return "conflict", None, None
    actual_bytes = destination.stat().st_size
    actual_sha = _sha256(destination)
    if actual_bytes == row["bytes"] and actual_sha == row["sha256"]:
        return "already_present", actual_bytes, actual_sha
    return "mismatched", actual_bytes, actual_sha


def hydrate_github_release_assets(
    *,
    repo: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    artifact_root: Path,
    tag: str = "",
    token_env: str = "GITHUB_TOKEN",
    write: bool = False,
    required_only: bool = False,
    replace_mismatched: bool = False,
    urlopen: Callable[..., Any] = urllib_urlopen,
) -> dict[str, Any]:
    """Plan and optionally download GitHub Release assets into a flat root."""

    errors: list[str] = []
    try:
        release_tag, rows, errors = _manifest_rows(
            _load_json(manifest_path),
            tag_override=tag,
            required_only=required_only,
        )
    except (OSError, json.JSONDecodeError) as exc:
        release_tag = ""
        rows = []
        errors = [str(exc)]

    token = _token_from_env(token_env)
    assets_by_name: dict[str, dict[str, Any]] = {}
    if not errors:
        try:
            assets_by_name = _release_assets_by_name(_release_payload(repo, release_tag, token=token, urlopen=urlopen))
        except HydrateReleaseAssetsError as exc:
            errors.append(str(exc))

    actions: list[dict[str, Any]] = []
    if not errors and artifact_root.exists() and not artifact_root.is_dir():
        errors.append(f"artifact root exists and is not a directory: {artifact_root}")

    if not errors:
        for row in rows:
            asset_name = row["asset_name"]
            destination = artifact_root / asset_name
            action: dict[str, Any] = {
                "asset_name": asset_name,
                "required": row["required"],
                "destination": str(destination),
                "manifest_bytes": row["bytes"],
                "manifest_sha256": row["sha256"],
                "status": "pending",
            }
            release_asset = assets_by_name.get(asset_name)
            if release_asset is None:
                errors.append(f"release asset missing for {asset_name}")
                action["status"] = "error"
                actions.append(action)
                continue
            action["release_size"] = release_asset["size"]
            action["release_url"] = release_asset["url"]
            if release_asset["size"] != row["bytes"]:
                errors.append(f"release asset size mismatch for {asset_name}: manifest={row['bytes']} actual={release_asset['size']}")
                action["status"] = "error"
                actions.append(action)
                continue

            existing, actual_bytes, actual_sha = _existing_status(destination, row)
            action["existing_status"] = existing
            if actual_bytes is not None:
                action["destination_bytes"] = actual_bytes
            if actual_sha is not None:
                action["destination_sha256"] = actual_sha
            if existing == "already_present":
                action["status"] = "already_present"
            elif existing == "missing":
                action["status"] = "would_download"
            elif existing == "mismatched" and replace_mismatched:
                action["status"] = "would_replace"
            elif existing == "mismatched":
                errors.append(f"destination already exists with different content for {asset_name}: {destination}")
                action["status"] = "error"
            else:
                errors.append(f"destination exists and is not a file for {asset_name}: {destination}")
                action["status"] = "error"
            actions.append(action)

    if errors:
        for action in actions:
            if action["status"] in {"pending", "would_download", "would_replace"}:
                action["status"] = "blocked"
    elif write:
        artifact_root.mkdir(parents=True, exist_ok=True)
        for action in actions:
            if action["status"] not in {"would_download", "would_replace"}:
                continue
            asset_name = action["asset_name"]
            payload = _download_asset_bytes(str(action["release_url"]), token=token, urlopen=urlopen)
            destination = Path(action["destination"])
            tmp = destination.with_name(f".{destination.name}.tmp")
            tmp.write_bytes(payload)
            if _contains_private_key_marker(tmp):
                tmp.unlink(missing_ok=True)
                errors.append(f"unsafe private key-like PEM asset content: {asset_name}")
                action["status"] = "error"
                continue
            actual_bytes = tmp.stat().st_size
            actual_sha = _sha256(tmp)
            action["downloaded_bytes"] = actual_bytes
            action["downloaded_sha256"] = actual_sha
            if actual_bytes != action["manifest_bytes"] or actual_sha != action["manifest_sha256"]:
                tmp.unlink(missing_ok=True)
                errors.append(
                    f"downloaded asset failed verification for {asset_name}: "
                    f"manifest_bytes={action['manifest_bytes']} actual_bytes={actual_bytes} "
                    f"manifest_sha256={action['manifest_sha256']} actual_sha256={actual_sha}"
                )
                action["status"] = "error"
                continue
            tmp.replace(destination)
            action["status"] = "downloaded"

    return {
        "ok": not errors,
        "write": write,
        "required_only": required_only,
        "replace_mismatched": replace_mismatched,
        "repo": repo,
        "manifest": str(manifest_path),
        "artifact_root": str(artifact_root),
        "release_tag": release_tag,
        "actions": actions,
        "errors": errors,
        "totals": {
            "selected_assets": len(rows),
            "already_present": sum(1 for action in actions if action["status"] == "already_present"),
            "would_download": sum(1 for action in actions if action["status"] == "would_download"),
            "would_replace": sum(1 for action in actions if action["status"] == "would_replace"),
            "downloaded": sum(1 for action in actions if action["status"] == "downloaded"),
            "blocked": sum(1 for action in actions if action["status"] == "blocked"),
            "errors": len(errors),
        },
    }


def _print_text(result: dict[str, Any]) -> None:
    mode = "write" if result["write"] else "dry-run"
    status = "ok" if result["ok"] else "failed"
    print(f"GitHub release asset hydration {status} ({mode})")
    print(f"Repo: {result['repo']}")
    print(f"Release tag: {result['release_tag']}")
    print(f"Artifact root: {result['artifact_root']}")
    for action in result["actions"]:
        print(f"- {action['asset_name']}: {action['status']} -> {action['destination']}")
    for error in result["errors"]:
        print(f"  error: {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download manifest-listed GitHub Release assets into a flat artifact root "
            "and verify each file against manifest SHA/bytes. Dry-run is the default."
        )
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--tag", default="", help="Override manifest release_tag.")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--write", action="store_true", help="Actually download assets after preflight passes.")
    parser.add_argument("--required-only", action="store_true", help="Hydrate only required manifest assets.")
    parser.add_argument(
        "--replace-mismatched",
        action="store_true",
        help="Replace files in artifact-root when their bytes/sha do not match the manifest.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = hydrate_github_release_assets(
            repo=args.repo,
            manifest_path=args.manifest,
            artifact_root=args.artifact_root,
            tag=args.tag,
            token_env=args.token_env,
            write=args.write,
            required_only=args.required_only,
            replace_mismatched=args.replace_mismatched,
        )
    except (OSError, ValueError, HydrateReleaseAssetsError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "write": args.write,
            "repo": args.repo,
            "manifest": str(args.manifest),
            "artifact_root": str(args.artifact_root),
            "release_tag": args.tag,
            "actions": [],
            "errors": [str(exc)],
            "totals": {"selected_assets": 0, "errors": 1},
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
