#!/usr/bin/env python3
"""Fetch GitHub Release asset listing metadata without downloading binaries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen as urllib_urlopen


GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 30


class FetchReleaseAssetsError(RuntimeError):
    """Raised when release asset metadata cannot be fetched or normalized."""


def _token_from_env(token_env: str) -> str | None:
    token = os.environ.get(token_env)
    if token:
        return token
    if token_env == "GITHUB_TOKEN":
        return os.environ.get("GH_TOKEN") or None
    return None


def _release_by_tag_url(repo: str, tag: str) -> str:
    parts = repo.split("/")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise FetchReleaseAssetsError("--repo must be in owner/name format")
    owner, name = (quote(part.strip(), safe="") for part in parts)
    return f"{GITHUB_API}/repos/{owner}/{name}/releases/tags/{quote(tag, safe='')}"


def _request_for(repo: str, tag: str, token_env: str) -> Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "arch-struct-analysis-release-asset-fetcher",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _token_from_env(token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return Request(_release_by_tag_url(repo, tag), headers=headers)


def _read_release_json(
    request: Request,
    *,
    urlopen: Callable[..., Any],
) -> Any:
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise FetchReleaseAssetsError(
                "GitHub release was not found. Check for a private repository, "
                "missing release/tag, or missing/insufficient auth token."
            ) from exc
        raise FetchReleaseAssetsError(f"GitHub API returned HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise FetchReleaseAssetsError(f"GitHub API request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise FetchReleaseAssetsError(f"GitHub API response was not valid JSON: {exc}") from exc


def _normalize_release(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FetchReleaseAssetsError("GitHub release response must be an object")

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise FetchReleaseAssetsError("GitHub release response assets must be a list")

    normalized_assets: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise FetchReleaseAssetsError(f"assets[{index}] must be an object")
        name = asset.get("name")
        size = asset.get("size")
        if not isinstance(name, str) or not name.strip():
            raise FetchReleaseAssetsError(f"assets[{index}].name must be a non-empty string")
        if not isinstance(size, int) or size < 0:
            raise FetchReleaseAssetsError(f"assets[{index}].size must be a non-negative integer")
        normalized_assets.append({"name": name, "size": size})

    result: dict[str, Any] = {"assets": normalized_assets}
    tag_name = payload.get("tag_name")
    html_url = payload.get("html_url")
    if isinstance(html_url, str) and html_url:
        result["html_url"] = html_url
    if isinstance(tag_name, str) and tag_name:
        result["tag_name"] = tag_name
    return result


def fetch_release_assets(
    repo: str,
    tag: str,
    *,
    token_env: str = "GITHUB_TOKEN",
    urlopen: Callable[..., Any] = urllib_urlopen,
) -> dict[str, Any]:
    """Fetch and normalize release asset name/size metadata."""

    request = _request_for(repo, tag, token_env)
    return _normalize_release(_read_release_json(request, urlopen=urlopen))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch GitHub Release asset metadata in the JSON shape consumed by "
            "scripts/check_release_asset_listing.py. This only lists metadata "
            "and never downloads release asset binaries."
        )
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format.")
    parser.add_argument("--tag", required=True, help="Release tag to fetch.")
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing a GitHub token. Defaults to GITHUB_TOKEN with GH_TOKEN fallback.",
    )
    parser.add_argument("--out", type=Path, help="Optional path to also write the JSON payload.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = fetch_release_assets(args.repo, args.tag, token_env=args.token_env)
        output = json.dumps(payload, sort_keys=True)
        if args.out:
            args.out.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0
    except (FetchReleaseAssetsError, OSError) as exc:
        print(f"Release asset metadata fetch error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
