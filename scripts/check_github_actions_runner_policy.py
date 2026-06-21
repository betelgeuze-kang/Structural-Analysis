#!/usr/bin/env python3
"""Check that GitHub Actions workflows avoid paid GitHub-hosted runners by default."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW_DIR = Path(".github/workflows")
GITHUB_HOSTED_LABEL_RE = re.compile(
    r"\b(?:ubuntu|windows|macos)-(?:latest|\d{2}\.\d{2})\b|"
    r"\b(?:ubuntu|windows|macos)-latest-(?:\d+core|\w+)\b",
    flags=re.IGNORECASE,
)


def _workflow_files(workflow_dir: Path) -> list[Path]:
    if not workflow_dir.exists():
        return []
    return sorted(
        path
        for path in workflow_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )


def _display_path(path: Path, workflow_dir: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        if workflow_dir.name == "workflows" and workflow_dir.parent.name == ".github":
            return str(Path(".github/workflows") / path.name)
        return str(path)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _clean_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        return ""
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    return value.strip().strip('"').strip("'")


def _collect_nested_list_values(
    *,
    lines: list[str],
    start_index: int,
    parent_indent: int,
) -> tuple[list[str], int]:
    values: list[str] = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if _indent(line) <= parent_indent:
            break
        if stripped.startswith("- "):
            value = _clean_scalar(stripped[2:])
            if value:
                values.append(value)
        index += 1
    return values, index


def _runs_on_entries(lines: list[str]) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped.startswith("runs-on:"):
            index += 1
            continue
        line_number = index + 1
        runs_on_indent = _indent(line)
        inline_value = _clean_scalar(stripped.split(":", 1)[1])
        if inline_value:
            entries.append((line_number, inline_value))
            index += 1
            continue

        values: list[str] = []
        child_index = index + 1
        while child_index < len(lines):
            child = lines[child_index]
            child_stripped = child.strip()
            if not child_stripped or child_stripped.startswith("#"):
                child_index += 1
                continue
            child_indent = _indent(child)
            if child_indent <= runs_on_indent:
                break
            if child_stripped.startswith("- "):
                value = _clean_scalar(child_stripped[2:])
                if value:
                    values.append(value)
                child_index += 1
                continue
            if child_stripped.startswith("labels:"):
                label_value = _clean_scalar(child_stripped.split(":", 1)[1])
                if label_value:
                    values.append(label_value)
                    child_index += 1
                    continue
                nested, next_index = _collect_nested_list_values(
                    lines=lines,
                    start_index=child_index + 1,
                    parent_indent=child_indent,
                )
                values.extend(nested)
                child_index = next_index
                continue
            child_index += 1
        entries.append((line_number, ", ".join(values)))
        index = child_index
    return entries


def check_runner_policy(*, workflow_dir: Path = DEFAULT_WORKFLOW_DIR) -> dict[str, Any]:
    workflow_dir = workflow_dir if workflow_dir.is_absolute() else ROOT / workflow_dir
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for workflow in _workflow_files(workflow_dir):
        rel_path = _display_path(workflow, workflow_dir)
        lines = workflow.read_text(encoding="utf-8").splitlines()
        for line_number, value in _runs_on_entries(lines):
            github_hosted = bool(GITHUB_HOSTED_LABEL_RE.search(value))
            uses_self_hosted_default = "self-hosted" in value
            row = {
                "workflow": rel_path,
                "line": line_number,
                "runs_on": value,
                "github_hosted_label": github_hosted,
                "self_hosted_default": uses_self_hosted_default,
                "ok": bool(not github_hosted and uses_self_hosted_default),
            }
            rows.append(row)
            if github_hosted:
                blockers.append(f"{rel_path}:{line_number}:github_hosted_runner_label:{value}")
            elif not uses_self_hosted_default:
                blockers.append(f"{rel_path}:{line_number}:self_hosted_default_missing:{value}")
    if not rows:
        blockers.append(f"{_display_path(workflow_dir, workflow_dir)}:runs_on_missing")
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "github-actions-runner-policy.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "workflow_count": len(_workflow_files(workflow_dir)),
        "runs_on_count": len(rows),
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": (
            "This is a repository workflow policy check only. It does not mutate billing, "
            "install a self-hosted runner, verify runner online status, or create CI streak evidence."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-dir", type=Path, default=DEFAULT_WORKFLOW_DIR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_runner_policy(workflow_dir=args.workflow_dir)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"GitHub Actions runner policy: {payload['status']}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
