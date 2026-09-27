"""Bind a tested PR merge parent to the named base branch without full history."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class RefIdentityError(ValueError):
    """A tested merge ref cannot be tied to the named PR base."""


def verify_base_ref(
    *,
    repository: str,
    base_ref: str,
    event_base_sha: str,
    tested_base_sha: str,
    fetch: Callable[[str], Mapping[str, object]],
) -> bool:
    """Return whether the event base advanced, or reject a stale/unrelated ref."""
    if not REPOSITORY_RE.fullmatch(repository):
        raise RefIdentityError("invalid base repository")
    if not base_ref or base_ref.startswith("refs/"):
        raise RefIdentityError("invalid named base branch")
    if not SHA_RE.fullmatch(event_base_sha) or not SHA_RE.fullmatch(tested_base_sha):
        raise RefIdentityError("invalid base commit SHA")

    ref_path = f"repos/{repository}/git/ref/heads/{quote(base_ref, safe='')}"
    ref_payload = fetch(ref_path)
    if ref_payload.get("ref") != f"refs/heads/{base_ref}":
        raise RefIdentityError("named base branch identity mismatch")
    ref_object = ref_payload.get("object")
    if not isinstance(ref_object, dict) or ref_object.get("sha") != tested_base_sha:
        raise RefIdentityError("merge-ref base parent is not the current base tip")

    if event_base_sha == tested_base_sha:
        return False
    compare_path = f"repos/{repository}/compare/{event_base_sha}...{tested_base_sha}"
    comparison = fetch(compare_path)
    merge_base = comparison.get("merge_base_commit")
    if (
        comparison.get("status") != "ahead"
        or comparison.get("behind_by") != 0
        or not isinstance(merge_base, dict)
        or merge_base.get("sha") != event_base_sha
    ):
        raise RefIdentityError("merge-ref base parent does not descend from event base")
    return True


def _github_fetch(path: str, *, token: str) -> Mapping[str, object]:
    request = Request(
        f"https://api.github.com/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "structural-native-pr-ref-gate",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RefIdentityError("GitHub base-ref API request failed") from exc
    if not isinstance(payload, dict):
        raise RefIdentityError("GitHub base-ref API returned a non-object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--event-base-sha", required=True)
    parser.add_argument("--tested-base-sha", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GitHub read-only token is required", file=sys.stderr)
        return 1
    try:
        advanced = verify_base_ref(
            repository=args.repository,
            base_ref=args.base_ref,
            event_base_sha=args.event_base_sha,
            tested_base_sha=args.tested_base_sha,
            fetch=lambda path: _github_fetch(path, token=token),
        )
    except RefIdentityError as exc:
        print(f"native PR base-ref verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"native_pr_base_ref_verified: base_advanced={str(advanced).lower()} "
        f"tested_base_sha={args.tested_base_sha}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
