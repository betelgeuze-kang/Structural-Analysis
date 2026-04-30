#!/usr/bin/env python3
"""Publish manifest-listed assets to a GitHub Release.

The script deliberately uploads only the assets accepted by
prepare_release_upload_plan.py. It never wildcard-uploads a release directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen as urllib_urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from prepare_release_upload_plan import DEFAULT_MANIFEST, prepare_release_upload_plan  # noqa: E402


GITHUB_API = "https://api.github.com"
UPLOADS_API = "https://uploads.github.com"
DEFAULT_TIMEOUT_SECONDS = 60


class PublishReleaseError(RuntimeError):
    """Raised when release publication cannot proceed safely."""


def _token_from_env(token_env: str) -> str | None:
    token = os.environ.get(token_env)
    if token:
        return token
    if token_env == "GITHUB_TOKEN":
        return os.environ.get("GH_TOKEN") or None
    return None


def _repo_parts(repo: str) -> tuple[str, str]:
    parts = [part.strip() for part in repo.split("/")]
    if len(parts) != 2 or not all(parts):
        raise PublishReleaseError("--repo must be in owner/name format")
    return parts[0], parts[1]


def _api_url(repo: str, suffix: str) -> str:
    owner, name = _repo_parts(repo)
    return f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(name, safe='')}{suffix}"


def _uploads_url(repo: str, release_id: int, asset_name: str) -> str:
    owner, name = _repo_parts(repo)
    query = urlencode({"name": asset_name})
    return (
        f"{UPLOADS_API}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        f"/releases/{release_id}/assets?{query}"
    )


def _headers(token: str, *, content_type: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "User-Agent": "arch-struct-analysis-release-publisher",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _read_json_response(response: Any) -> Any:
    return json.loads(response.read().decode("utf-8"))


def _json_request(
    method: str,
    url: str,
    *,
    token: str,
    payload: Any | None = None,
    urlopen: Callable[..., Any] = urllib_urlopen,
) -> Any:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=_headers(token), method=method)
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return _read_json_response(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise
        raise PublishReleaseError(f"GitHub API returned HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise PublishReleaseError(f"GitHub API request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise PublishReleaseError(f"GitHub API response was not valid JSON: {exc}") from exc


def _require_tag_ref(repo: str, tag: str, *, token: str, urlopen: Callable[..., Any]) -> None:
    url = _api_url(repo, f"/git/ref/tags/{quote(tag, safe='')}")
    try:
        _json_request("GET", url, token=token, urlopen=urlopen)
    except HTTPError as exc:
        if exc.code == 404:
            raise PublishReleaseError(
                f"Git tag {tag!r} is not visible through the GitHub API. "
                "Push the tag before publishing release assets."
            ) from exc
        raise


def _get_release_by_tag(repo: str, tag: str, *, token: str, urlopen: Callable[..., Any]) -> Any | None:
    url = _api_url(repo, f"/releases/tags/{quote(tag, safe='')}")
    try:
        return _json_request("GET", url, token=token, urlopen=urlopen)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _create_release(
    repo: str,
    tag: str,
    *,
    token: str,
    name: str | None,
    body: str | None,
    draft: bool,
    prerelease: bool,
    urlopen: Callable[..., Any],
) -> Any:
    payload = {
        "tag_name": tag,
        "name": name or tag,
        "body": body or "",
        "draft": draft,
        "prerelease": prerelease,
    }
    return _json_request("POST", _api_url(repo, "/releases"), token=token, payload=payload, urlopen=urlopen)


def _asset_rows(release_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(release_payload, dict):
        raise PublishReleaseError("release response must be an object")
    assets = release_payload.get("assets")
    if not isinstance(assets, list):
        raise PublishReleaseError("release response assets must be a list")
    rows: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise PublishReleaseError(f"release assets[{index}] must be an object")
        name = asset.get("name")
        size = asset.get("size")
        asset_id = asset.get("id")
        if not isinstance(name, str) or not name:
            raise PublishReleaseError(f"release assets[{index}].name must be a non-empty string")
        if not isinstance(size, int) or size < 0:
            raise PublishReleaseError(f"release assets[{index}].size must be a non-negative integer")
        row = {"name": name, "size": size}
        if isinstance(asset_id, int):
            row["id"] = asset_id
        rows.append(row)
    return rows


def _delete_asset(repo: str, asset_id: int, *, token: str, urlopen: Callable[..., Any]) -> None:
    url = _api_url(repo, f"/releases/assets/{asset_id}")
    request = Request(url, headers=_headers(token), method="DELETE")
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS):
            return
    except HTTPError as exc:
        raise PublishReleaseError(f"GitHub asset delete returned HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise PublishReleaseError(f"GitHub asset delete failed: {exc.reason}") from exc


def _upload_asset(
    repo: str,
    release_id: int,
    asset: dict[str, Any],
    *,
    token: str,
    urlopen: Callable[..., Any],
) -> dict[str, Any]:
    path = Path(str(asset["path"]))
    data = path.read_bytes()
    url = _uploads_url(repo, release_id, str(asset["asset_name"]))
    request = Request(
        url,
        data=data,
        headers=_headers(token, content_type="application/octet-stream"),
        method="POST",
    )
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            payload = _read_json_response(response)
    except HTTPError as exc:
        raise PublishReleaseError(
            f"GitHub upload failed for {asset['asset_name']}: HTTP {exc.code}: {exc.reason}"
        ) from exc
    except URLError as exc:
        raise PublishReleaseError(f"GitHub upload failed for {asset['asset_name']}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise PublishReleaseError(
            f"GitHub upload response was not valid JSON for {asset['asset_name']}: {exc}"
        ) from exc

    uploaded_name = payload.get("name") if isinstance(payload, dict) else None
    uploaded_size = payload.get("size") if isinstance(payload, dict) else None
    if uploaded_name != asset["asset_name"]:
        raise PublishReleaseError(f"uploaded asset name mismatch for {asset['asset_name']}")
    if uploaded_size != asset["bytes"]:
        raise PublishReleaseError(
            f"uploaded asset size mismatch for {asset['asset_name']}: "
            f"expected={asset['bytes']} actual={uploaded_size}"
        )
    result = {"name": uploaded_name, "size": uploaded_size}
    asset_id = payload.get("id")
    if isinstance(asset_id, int):
        result["id"] = asset_id
    return result


def _release_listing(release_payload: Any) -> dict[str, Any]:
    if not isinstance(release_payload, dict):
        raise PublishReleaseError("release response must be an object")
    payload: dict[str, Any] = {"assets": _asset_rows(release_payload)}
    tag_name = release_payload.get("tag_name")
    html_url = release_payload.get("html_url")
    if isinstance(tag_name, str) and tag_name:
        payload["tag_name"] = tag_name
    if isinstance(html_url, str) and html_url:
        payload["html_url"] = html_url
    return payload


def publish_release_assets(
    *,
    repo: str,
    manifest_path: Path,
    artifact_root: Path,
    token_env: str = "GITHUB_TOKEN",
    name: str | None = None,
    body: str | None = None,
    draft: bool = False,
    prerelease: bool = False,
    replace_existing: bool = False,
    dry_run: bool = False,
    assets_out: Path | None = None,
    urlopen: Callable[..., Any] = urllib_urlopen,
) -> dict[str, Any]:
    """Create or update a GitHub Release using a safe upload plan."""

    plan = prepare_release_upload_plan(manifest_path, artifact_root)
    if dry_run:
        summary = {
            "ok": True,
            "dry_run": True,
            "repo": repo,
            "release_tag": plan["release_tag"],
            "upload_assets": plan["upload_assets"],
            "totals": plan["totals"],
        }
        if assets_out:
            assets_out.write_text(
                json.dumps(
                    {
                        "assets": [
                            {"name": asset["asset_name"], "size": asset["bytes"]}
                            for asset in plan["upload_assets"]
                        ],
                        "tag_name": plan["release_tag"],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        return summary

    token = _token_from_env(token_env)
    if not token:
        raise PublishReleaseError(
            f"Missing GitHub token. Set {token_env} or GH_TOKEN before publishing release assets."
        )

    tag = plan["release_tag"]
    _require_tag_ref(repo, tag, token=token, urlopen=urlopen)
    release = _get_release_by_tag(repo, tag, token=token, urlopen=urlopen)
    release_created = False
    if release is None:
        release = _create_release(
            repo,
            tag,
            token=token,
            name=name,
            body=body,
            draft=draft,
            prerelease=prerelease,
            urlopen=urlopen,
        )
        release_created = True

    release_id = release.get("id") if isinstance(release, dict) else None
    if not isinstance(release_id, int):
        raise PublishReleaseError("release response id must be an integer")

    existing_by_name = {row["name"]: row for row in _asset_rows(release)}
    duplicate_names = [asset["asset_name"] for asset in plan["upload_assets"] if asset["asset_name"] in existing_by_name]
    if duplicate_names and not replace_existing:
        raise PublishReleaseError(
            "release already has manifest asset(s): "
            + ", ".join(sorted(duplicate_names))
            + ". Re-run with --replace-existing to delete and replace them."
        )

    deleted_assets: list[dict[str, Any]] = []
    for name_to_replace in duplicate_names:
        existing = existing_by_name[name_to_replace]
        asset_id = existing.get("id")
        if not isinstance(asset_id, int):
            raise PublishReleaseError(f"existing asset {name_to_replace} has no integer id")
        _delete_asset(repo, asset_id, token=token, urlopen=urlopen)
        deleted_assets.append(existing)

    uploaded_assets = [
        _upload_asset(repo, release_id, asset, token=token, urlopen=urlopen)
        for asset in plan["upload_assets"]
    ]
    final_release = _get_release_by_tag(repo, tag, token=token, urlopen=urlopen)
    if final_release is None:
        raise PublishReleaseError("release disappeared after upload")
    listing = _release_listing(final_release)
    if assets_out:
        assets_out.write_text(json.dumps(listing, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "dry_run": False,
        "repo": repo,
        "release_tag": tag,
        "release_created": release_created,
        "release_id": release_id,
        "deleted_assets": deleted_assets,
        "uploaded_assets": uploaded_assets,
        "asset_listing": listing,
        "totals": {
            "deleted_assets": len(deleted_assets),
            "uploaded_assets": len(uploaded_assets),
            "listed_assets": len(listing["assets"]),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create/update a GitHub Release and upload only manifest-listed assets "
            "from a fresh flat artifact root."
        )
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--name", help="Optional release name. Defaults to the manifest release tag.")
    parser.add_argument("--body", help="Optional release body.")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--prerelease", action="store_true")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete same-named existing release assets before uploading fresh manifest assets.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the local upload plan without calling GitHub or requiring a token.",
    )
    parser.add_argument(
        "--assets-out",
        type=Path,
        help="Optional path for the normalized release asset listing JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = publish_release_assets(
            repo=args.repo,
            manifest_path=args.manifest,
            artifact_root=args.artifact_root,
            token_env=args.token_env,
            name=args.name,
            body=args.body,
            draft=args.draft,
            prerelease=args.prerelease,
            replace_existing=args.replace_existing,
            dry_run=args.dry_run,
            assets_out=args.assets_out,
        )
    except (OSError, ValueError, PublishReleaseError, json.JSONDecodeError) as exc:
        print(f"GitHub release publication failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
