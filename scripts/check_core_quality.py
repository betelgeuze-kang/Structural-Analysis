#!/usr/bin/env python3
"""Run the bounded public-core typecheck and branch-coverage gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "artifacts" / "manifests" / "core_quality.json"


def load_manifest() -> dict[str, Any]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "structural-analysis-core-quality.v1":
        raise ValueError("unsupported core-quality manifest schema")
    return payload


def typecheck_command(payload: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "-m",
        str(payload["typecheck"]["tool"]),
        *[str(path) for path in payload["typecheck"]["paths"]],
    ]


def coverage_commands(
    payload: dict[str, Any], *, data_file: Path
) -> tuple[list[str], list[str]]:
    tests = [str(path) for path in payload["coverage"]["tests"]]
    run = [sys.executable, "-m", "coverage", "run", "-m", "pytest", *tests]
    report = [
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--fail-under={int(payload['coverage']['minimum_percent'])}",
    ]
    return run, report


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(" ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def check_contract(payload: dict[str, Any]) -> None:
    paths = payload["typecheck"]["paths"]
    tests = payload["coverage"]["tests"]
    matrix = payload["compatibility_matrix"]
    missing = [path for path in [*paths, *tests] if not (ROOT / path).exists()]
    if missing:
        raise ValueError(f"core-quality manifest references missing paths: {missing}")
    coordinates = len(matrix["operating_systems"]) * len(matrix["python_versions"])
    if coordinates != matrix["required_coordinate_count"]:
        raise ValueError("compatibility matrix coordinate count is inconsistent")
    if int(payload["coverage"]["minimum_percent"]) < 80:
        raise ValueError("bounded public-core coverage threshold may not be below 80%")


def run(*, contract_only: bool, typecheck_only: bool, coverage_only: bool) -> int:
    payload = load_manifest()
    check_contract(payload)
    if contract_only:
        print("Core quality contract: PASS")
        return 0

    if not coverage_only:
        _run(typecheck_command(payload))
    if not typecheck_only:
        with tempfile.TemporaryDirectory(prefix="structural-analysis-coverage-") as tmp:
            data_file = Path(tmp) / ".coverage"
            env = os.environ.copy()
            env["COVERAGE_FILE"] = str(data_file)
            run_command, report_command = coverage_commands(
                payload,
                data_file=data_file,
            )
            _run(run_command, env=env)
            _run(report_command, env=env)
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
    return run(
        contract_only=args.contract_only,
        typecheck_only=args.typecheck_only,
        coverage_only=args.coverage_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
