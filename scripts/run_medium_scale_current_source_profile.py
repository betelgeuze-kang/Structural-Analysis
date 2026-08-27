#!/usr/bin/env python3
"""Run and validate the current-source five-case medium-scale profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.benchmark.medium_scale_execution import (  # noqa: E402
    build_medium_scale_execution_receipt,
    execute_medium_scale_case,
    json_text,
    validate_medium_scale_execution_receipt,
)


DEFAULT_OUT = Path(
    "artifacts/medium-scale/current-source/medium-scale-execution.v1.json"
)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _source_commit_sha(explicit: str | None) -> str:
    head = _git("rev-parse", "--verify", "HEAD^{commit}")
    if explicit is not None and explicit != head:
        raise ValueError("explicit source SHA does not match checked-out HEAD")
    return explicit or head


def _source_tree_clean() -> bool:
    return not _git("status", "--porcelain=v1", "--untracked-files=all")


def _write(path: Path, payload: dict[str, object]) -> None:
    resolved = path if path.is_absolute() else ROOT / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json_text(payload), encoding="utf-8")


def _validate_file(path: Path, *, require_pass: bool) -> int:
    resolved = path if path.is_absolute() else ROOT / path
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("medium-scale receipt must contain a JSON object")
    validate_medium_scale_execution_receipt(payload)
    if require_pass and payload.get("contract_pass") is not True:
        print("medium-scale current-source profile: blocked", file=sys.stderr)
        return 1
    print(
        "medium-scale current-source profile: "
        f"{payload.get('status')} "
        f"({payload.get('summary', {}).get('technical_execution_credit_count', 0)}/5 technical)",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-sha")
    parser.add_argument("--worker", metavar="CASE_ID")
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--require-pass", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.worker:
        payload = execute_medium_scale_case(args.worker)
        sys.stdout.write(json_text(payload))
        return 0 if payload["contract_pass"] else 1
    if args.validate is not None:
        return _validate_file(args.validate, require_pass=args.require_pass)

    source_sha = _source_commit_sha(args.source_sha)
    payload = build_medium_scale_execution_receipt(
        source_commit_sha=source_sha,
        source_tree_clean=_source_tree_clean(),
        worker_command=[sys.executable, str(Path(__file__).resolve())],
    )
    _write(args.out, payload)
    print(
        "medium-scale current-source profile: "
        f"{payload['status']} "
        f"({payload['summary']['technical_execution_credit_count']}/5 technical; "
        f"{payload['summary']['scientific_medium_benchmark_credit_count']}/5 scientific; "
        f"{payload['summary']['native_medium_product_authority_count']}/5 native)",
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
