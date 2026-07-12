#!/usr/bin/env python3
"""Run Ruff and bytecode compilation for one product CI ownership lane."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_SCRIPT = ROOT / "scripts" / "check_product_ci_boundaries.py"
CHUNK_SIZE = 150


def _load_boundary_module():
    spec = importlib.util.spec_from_file_location(
        "check_product_ci_boundaries",
        BOUNDARY_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load product CI boundary checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _chunks(values: list[str], size: int = CHUNK_SIZE) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _run(command: list[str]) -> None:
    print(" ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def run_lane(*, lane: str, ruff: bool, compile_python: bool) -> int:
    module = _load_boundary_module()
    report = module.build_report(repo_root=ROOT)
    if not report["contract_pass"]:
        print("Product CI boundary contract is blocked:", file=sys.stderr)
        for blocker in report["blockers"]:
            print(f"- {blocker}", file=sys.stderr)
        return 2

    paths = [str(path) for path in report["lane_paths"][lane]]
    if not paths:
        print(f"Product CI lane {lane}: no tracked Python paths")
        return 0

    if ruff:
        for chunk in _chunks(paths):
            # Explicit path lists normally override Ruff's configured excludes.
            # Preserve repository exclusions for vendored/generated trees while
            # still linting every owned non-excluded path in the lane.
            _run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--force-exclude",
                    *chunk,
                ]
            )
    if compile_python:
        for chunk in _chunks(paths):
            _run([sys.executable, "-m", "py_compile", *chunk])

    print(f"Product CI lane {lane}: PASS | python_paths={len(paths)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    module = _load_boundary_module()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=module.LANES, required=True)
    parser.add_argument("--ruff", action="store_true")
    parser.add_argument("--compile", dest="compile_python", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.ruff and not args.compile_python:
        args.ruff = True
        args.compile_python = True
    return run_lane(
        lane=args.lane,
        ruff=args.ruff,
        compile_python=args.compile_python,
    )


if __name__ == "__main__":
    raise SystemExit(main())
