#!/usr/bin/env python3
"""Guard against pushing this repo to an unintended Git remote."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_EXPECTED_SLUG = "betelgeuze-kang/Structural-Analysis"
DEFAULT_FORBIDDEN_SLUGS = ("betelgeuze-kang/Monet-wedding",)
PROTECTED_REMOTE_NAMES = ("origin",)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that protected Git remotes point at the intended "
            "repository slug. Use --remote-file for fixture-based checks."
        )
    )
    parser.add_argument(
        "--expected-slug",
        default=DEFAULT_EXPECTED_SLUG,
        help=f"Expected owner/repo slug. Default: {DEFAULT_EXPECTED_SLUG}",
    )
    parser.add_argument(
        "--forbidden-slug",
        action="append",
        default=list(DEFAULT_FORBIDDEN_SLUGS),
        help="Owner/repo slug that must not appear in any configured remote.",
    )
    parser.add_argument(
        "--protected-remote",
        action="append",
        default=list(PROTECTED_REMOTE_NAMES),
        help="Remote name that must point at --expected-slug.",
    )
    parser.add_argument(
        "--remote-file",
        type=Path,
        help="Read `git remote -v` text from a fixture file instead of Git.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable diagnostics.",
    )
    parser.add_argument("--show-ok", action="store_true", help="Print a success line.")
    return parser.parse_args(argv)


def _git_remote_verbose() -> str:
    proc = subprocess.run(
        ["git", "remote", "-v"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def canonical_slug(remote_url: str) -> str | None:
    """Extract owner/repo from common HTTPS, SSH, and git remote URL forms."""
    cleaned = remote_url.strip()
    cleaned = re.sub(r"\s+\((fetch|push)\)$", "", cleaned)
    cleaned = cleaned.removesuffix(".git")

    patterns = (
        r"github\.com[:/](?P<owner>[^/\s:]+)/(?P<repo>[^/\s]+)$",
        r"^git@github\.com:(?P<owner>[^/\s:]+)/(?P<repo>[^/\s]+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return None


def parse_remote_verbose(text: str) -> dict[str, list[str]]:
    remotes: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        remotes.setdefault(name, [])
        if url not in remotes[name]:
            remotes[name].append(url)
    return remotes


def _normalize_slug(slug: str) -> str:
    return slug.removesuffix(".git")


def check_remotes(
    remotes: dict[str, list[str]],
    *,
    expected_slug: str = DEFAULT_EXPECTED_SLUG,
    forbidden_slugs: tuple[str, ...] = DEFAULT_FORBIDDEN_SLUGS,
    protected_remote_names: tuple[str, ...] = PROTECTED_REMOTE_NAMES,
) -> list[str]:
    expected = _normalize_slug(expected_slug)
    forbidden = {_normalize_slug(slug) for slug in forbidden_slugs}
    errors: list[str] = []

    expected_seen = False
    for name, urls in sorted(remotes.items()):
        for url in urls:
            slug = canonical_slug(url)
            if slug == expected:
                expected_seen = True
            if slug in forbidden:
                errors.append(f"forbidden remote target configured: {name} -> {url}")

    for name in protected_remote_names:
        urls = remotes.get(name)
        if not urls:
            continue
        protected_slugs = {canonical_slug(url) for url in urls}
        if protected_slugs != {expected}:
            rendered = ", ".join(urls)
            errors.append(f"protected remote `{name}` must point to {expected}: {rendered}")

    if not expected_seen:
        errors.append(f"expected remote target not configured: {expected}")

    return errors


def build_report(
    remote_text: str,
    *,
    expected_slug: str = DEFAULT_EXPECTED_SLUG,
    forbidden_slugs: tuple[str, ...] = DEFAULT_FORBIDDEN_SLUGS,
    protected_remote_names: tuple[str, ...] = PROTECTED_REMOTE_NAMES,
) -> dict[str, object]:
    remotes = parse_remote_verbose(remote_text)
    errors = check_remotes(
        remotes,
        expected_slug=expected_slug,
        forbidden_slugs=forbidden_slugs,
        protected_remote_names=protected_remote_names,
    )
    return {
        "errors": errors,
        "expected_slug": _normalize_slug(expected_slug),
        "ok": not errors,
        "remotes": remotes,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    remote_text = args.remote_file.read_text(encoding="utf-8") if args.remote_file else _git_remote_verbose()
    report = build_report(
        remote_text,
        expected_slug=args.expected_slug,
        forbidden_slugs=tuple(args.forbidden_slug),
        protected_remote_names=tuple(args.protected_remote),
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["errors"]:
        print("Git remote safety check failed:", file=sys.stderr)
        for error in report["errors"]:
            print(f"- {error}", file=sys.stderr)
    elif args.show_ok:
        print("Git remote safety OK")

    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
