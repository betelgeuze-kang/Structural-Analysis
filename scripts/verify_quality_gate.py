#!/usr/bin/env python3
"""Run release-quality gates with explicit PR and full modes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _python() -> str:
    return sys.executable


def _npm() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _pr_commands(*, p1_failure_mode: str = "core") -> list[list[str]]:
    source_boundary = [
        _python(),
        "scripts/plan_source_boundary_cleanup.py",
        "--large-file-threshold-mib",
        "10",
        "--allowlist-manifest",
        "implementation/phase1/source_boundary_allowlist.json",
        "--fail-on-candidates",
    ]
    p1_failure_flag = "--fail-blocked" if p1_failure_mode == "blocked" else "--fail-core-open"
    return [
        [_python(), "scripts/check_repo_hygiene.py", "--show-ok"],
        source_boundary,
        [_python(), "scripts/report_source_boundary_footprint.py", "--check"],
        [_python(), "scripts/check_git_remote_safety.py", "--show-ok"],
        [_python(), "-m", "ruff", "check", "."],
        [_python(), "scripts/check_p0_closure_status.py", "--json", "--fail-core-open"],
        [_python(), "scripts/check_p1_readiness_status.py", "--json", p1_failure_flag],
        [_python(), "scripts/check_p1_benchmark_breadth_status.py", "--json", p1_failure_flag],
        [_npm(), "ci"],
        [
            _python(),
            "scripts/verify_release_artifacts_manifest.py",
            "--manifest",
            "implementation/phase1/release_artifacts_manifest.json",
            "--structure-only",
        ],
        [
            _python(),
            "scripts/verify_open_data_external_artifacts_manifest.py",
            "--manifest",
            "implementation/phase1/open_data_external_artifacts_manifest.json",
            "--structure-only",
        ],
        [_npm(), "run", "verify:frontend-contract"],
        [_npm(), "run", "build"],
        [_npm(), "run", "verify:viewer-manifest"],
        [_python(), "scripts/verify_structure_viewer_contracts.py"],
        [_npm(), "run", "verify:frontend-browser-smoke", "--", "--mode", "minimal"],
        [
            _python(),
            "-m",
            "pytest",
            "-q",
            "tests/test_project_ops_api_service.py",
            "tests/test_source_boundary_ci_contract.py",
            "tests/test_source_boundary_footprint_report.py",
        ],
    ]


def _command_groups(mode: str) -> list[list[str]]:
    if mode == "pr":
        return _pr_commands(p1_failure_mode="core")
    return [
        [_python(), "scripts/check_p0_closure_status.py", "--json", "--fail-open"],
        *_pr_commands(p1_failure_mode="blocked"),
        [_python(), "-m", "pytest", "-q"],
        [_npm(), "run", "verify:frontend-browser-smoke"],
        [_npm(), "run", "verify:viewer-report-pdf"],
        [_npm(), "run", "verify:viewer-performance-probe"],
        [_npm(), "run", "verify:viewer-visual-regression"],
        [
            _python(),
            "scripts/report_commercialization_level.py",
            "--closure-mode",
            "conditional",
            "--fail-below",
            "9.0",
        ],
        [_python(), "scripts/check_workstation_delivery_readiness.py", "--json"],
        [_python(), "scripts/check_independent_product_readiness.py", "--json"],
        [_python(), "scripts/check_generated_worktree_clean.py", "--show-ok"],
        ["git", "diff", "--check"],
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pr", "full"), default="pr")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for command in _command_groups(args.mode):
        print(" ".join(command), flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            return int(result.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
