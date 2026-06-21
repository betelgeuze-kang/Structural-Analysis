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


def _runs_on_value(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("runs-on:"):
        return None
    return stripped.split(":", 1)[1].strip().strip('"').strip("'")


def check_runner_policy(*, workflow_dir: Path = DEFAULT_WORKFLOW_DIR) -> dict[str, Any]:
    workflow_dir = workflow_dir if workflow_dir.is_absolute() else ROOT / workflow_dir
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for workflow in _workflow_files(workflow_dir):
        rel_path = _display_path(workflow, workflow_dir)
        for line_number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            value = _runs_on_value(line)
            if value is None:
                continue
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
