#!/usr/bin/env python3
"""Run the bounded public-core typecheck and branch-coverage gate."""

from __future__ import annotations

import argparse
import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("artifacts/manifests/core_quality.json")
SCHEMA_VERSION = "structural-analysis-core-quality.v1"
REQUIRED_OPERATING_SYSTEMS = [
    "ubuntu-latest",
    "windows-latest",
    "macos-latest",
]
REQUIRED_PYTHON_VERSIONS = ["3.10", "3.12", "3.13"]
MINIMUM_BRANCH_COVERAGE = 85


def _resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def load_manifest(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    payload = json.loads(_resolve(root, manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("core-quality manifest must contain a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported core-quality manifest schema_version")
    return payload


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    rows = [str(item).strip() for item in value]
    if any(not row for row in rows):
        raise ValueError(f"{field} cannot contain empty values")
    if len(rows) != len(set(rows)):
        raise ValueError(f"{field} cannot contain duplicate values")
    return rows


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _coverage_config(path: Path) -> tuple[bool, int, list[str]]:
    parser = configparser.ConfigParser()
    if not parser.read(path, encoding="utf-8"):
        raise ValueError(f"coverage config is unreadable: {path}")
    try:
        branch = parser.getboolean("run", "branch")
        fail_under = parser.getint("report", "fail_under")
        sources = [
            row.strip()
            for row in parser.get("run", "source").splitlines()
            if row.strip()
        ]
    except (configparser.Error, ValueError) as exc:
        raise ValueError(f"coverage config is invalid: {exc}") from exc
    return branch, fail_under, sources


def check_contract(payload: dict[str, Any], *, root: Path = ROOT) -> None:
    typecheck = _mapping(payload.get("typecheck"), field="typecheck")
    coverage = _mapping(payload.get("coverage"), field="coverage")
    matrix = _mapping(
        payload.get("compatibility_matrix"),
        field="compatibility_matrix",
    )

    if typecheck.get("tool") != "mypy":
        raise ValueError("bounded typecheck tool must be mypy")
    if coverage.get("tool") != "coverage.py":
        raise ValueError("bounded coverage tool must be coverage.py")

    typecheck_paths = _string_list(typecheck.get("paths"), field="typecheck.paths")
    coverage_tests = _string_list(coverage.get("tests"), field="coverage.tests")
    coverage_sources = _string_list(
        coverage.get("sources"),
        field="coverage.sources",
    )
    referenced_paths = [
        str(typecheck.get("config", "")),
        str(coverage.get("config", "")),
        *typecheck_paths,
        *coverage_tests,
    ]
    missing = [
        path
        for path in referenced_paths
        if not path or not _resolve(root, path).exists()
    ]
    if missing:
        raise ValueError(f"core-quality manifest references missing paths: {missing}")

    minimum_percent = int(coverage.get("minimum_percent") or 0)
    if coverage.get("branch") is not True:
        raise ValueError("coverage.branch must remain true")
    if minimum_percent < MINIMUM_BRANCH_COVERAGE:
        raise ValueError(
            "bounded public-core branch coverage threshold may not be below "
            f"{MINIMUM_BRANCH_COVERAGE}%"
        )

    config_branch, config_fail_under, config_sources = _coverage_config(
        _resolve(root, str(coverage["config"]))
    )
    if config_branch is not True:
        raise ValueError("coverage config must enable branch measurement")
    if config_fail_under != minimum_percent:
        raise ValueError("coverage config and manifest thresholds differ")
    if config_sources != coverage_sources:
        raise ValueError("coverage config and manifest sources differ")

    operating_systems = _string_list(
        matrix.get("operating_systems"),
        field="compatibility_matrix.operating_systems",
    )
    python_versions = _string_list(
        matrix.get("python_versions"),
        field="compatibility_matrix.python_versions",
    )
    if operating_systems != REQUIRED_OPERATING_SYSTEMS:
        raise ValueError("compatibility matrix operating systems were weakened")
    if python_versions != REQUIRED_PYTHON_VERSIONS:
        raise ValueError("compatibility matrix Python versions were weakened")
    coordinates = len(operating_systems) * len(python_versions)
    if coordinates != int(matrix.get("required_coordinate_count") or 0):
        raise ValueError("compatibility matrix coordinate count is inconsistent")
    if coordinates != 9:
        raise ValueError("compatibility matrix must retain all 9 coordinates")
    workflow = str(matrix.get("workflow") or "")
    if not workflow or not _resolve(root, workflow).is_file():
        raise ValueError("compatibility matrix workflow is missing")


def typecheck_command(payload: dict[str, Any]) -> list[str]:
    typecheck = _mapping(payload["typecheck"], field="typecheck")
    return [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        str(typecheck["config"]),
        *_string_list(typecheck["paths"], field="typecheck.paths"),
    ]


def coverage_commands(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    coverage = _mapping(payload["coverage"], field="coverage")
    config = str(coverage["config"])
    tests = _string_list(coverage["tests"], field="coverage.tests")
    run = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        f"--rcfile={config}",
        "-m",
        "pytest",
        "-q",
        *tests,
    ]
    report = [
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--rcfile={config}",
        f"--fail-under={int(coverage['minimum_percent'])}",
    ]
    return run, report


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def run(
    *,
    contract_only: bool,
    typecheck_only: bool,
    coverage_only: bool,
) -> int:
    payload = load_manifest()
    check_contract(payload)
    if contract_only:
        print("Core quality contract: PASS")
        return 0

    if not coverage_only:
        _run(typecheck_command(payload))
    if not typecheck_only:
        with tempfile.TemporaryDirectory(prefix="structural-analysis-coverage-") as tmp:
            env = os.environ.copy()
            env["COVERAGE_FILE"] = str(Path(tmp) / ".coverage")
            coverage_run, coverage_report = coverage_commands(payload)
            _run(coverage_run, env=env)
            _run(coverage_report, env=env)
    print("Core quality gate: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--contract-only", action="store_true")
    mode.add_argument("--typecheck-only", action="store_true")
    mode.add_argument("--coverage-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(
            contract_only=args.contract_only,
            typecheck_only=args.typecheck_only,
            coverage_only=args.coverage_only,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"Core quality contract: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
