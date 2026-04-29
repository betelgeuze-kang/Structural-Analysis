#!/usr/bin/env python3
"""Report worktree drift in categories that are easy to triage."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

from check_generated_worktree_clean import _is_generated_artifact


CATEGORIES = (
    "generated_drift",
    "asset_deletions",
    "source_changes",
    "other_changes",
)
ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
SOURCE_SUFFIXES = (
    ".py",
    ".sh",
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".rst",
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify git worktree drift without modifying files. By default, "
            "reads `git status --porcelain=v1`; use --status-file for fixtures."
        )
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        help="Read git status --porcelain=v1 output from a fixture file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the text report.",
    )
    parser.add_argument(
        "--fail-on-generated",
        action="store_true",
        help="Exit 1 when generated artifact drift is present.",
    )
    return parser.parse_args(argv)


def _git_status_porcelain() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return _split_lines(proc.stdout)


def _read_status_file(path: Path) -> list[str]:
    return _split_lines(path.read_text(encoding="utf-8"))


def _split_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _decode_porcelain_path(path_text: str) -> str:
    path_text = path_text.strip()
    if path_text.startswith('"') and path_text.endswith('"'):
        try:
            decoded = ast.literal_eval(path_text)
        except (SyntaxError, ValueError):
            return path_text.strip('"')
        decoded_text = str(decoded)
        try:
            return decoded_text.encode("latin-1").decode("utf-8")
        except UnicodeError:
            return decoded_text
    return path_text


def _parse_status_line(line: str) -> tuple[str, str] | None:
    if len(line) < 4:
        return None
    status = line[:2]
    path_text = line[3:]
    if " -> " in path_text:
        path_text = path_text.rsplit(" -> ", 1)[1]
    return status, _decode_porcelain_path(path_text)


def _is_deletion(status: str) -> bool:
    return "D" in status


def _has_suffix(path: str, suffixes: tuple[str, ...]) -> bool:
    return path.lower().endswith(suffixes)


def classify_status(lines: list[str]) -> dict[str, list[str]]:
    report = {category: [] for category in CATEGORIES}

    for line in lines:
        parsed = _parse_status_line(line)
        if parsed is None:
            continue
        status, path = parsed

        if _is_generated_artifact(path):
            report["generated_drift"].append(path)
        elif _is_deletion(status) and _has_suffix(path, ASSET_SUFFIXES):
            report["asset_deletions"].append(path)
        elif _has_suffix(path, SOURCE_SUFFIXES):
            report["source_changes"].append(path)
        else:
            report["other_changes"].append(path)

    return report


def _with_counts(report: dict[str, list[str]]) -> dict[str, object]:
    return {
        "counts": {category: len(report[category]) for category in CATEGORIES},
        **report,
    }


def _print_text_report(report: dict[str, list[str]]) -> None:
    print("Worktree drift report")
    for category in CATEGORIES:
        paths = report[category]
        print(f"{category}: {len(paths)}")
        for path in paths:
            print(f"  - {path}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    lines = _read_status_file(args.status_file) if args.status_file else _git_status_porcelain()
    report = classify_status(lines)

    if args.json:
        print(json.dumps(_with_counts(report), indent=2, ensure_ascii=False))
    else:
        _print_text_report(report)

    if args.fail_on_generated and report["generated_drift"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
