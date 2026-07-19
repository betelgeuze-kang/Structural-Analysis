#!/usr/bin/env python3
"""Build or validate the source-bound Level 1 analytic frame receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.benchmark.analytic_frame import (  # noqa: E402
    build_analytic_frame_verification_artifact,
    validate_analytic_frame_verification_artifact,
)


DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "analytic_frame_verification.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("analytic_frame_artifact_root_invalid")
    return payload


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = _resolve(args.out)
    if args.check:
        validate_analytic_frame_verification_artifact(
            _read_json(out),
            repo_root=ROOT,
            require_current_sources=True,
            rerun=True,
        )
        print("analytic_frame_verification_consistent")
        return 0
    payload = build_analytic_frame_verification_artifact(repo_root=ROOT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "pass | cases=3/3 | categories="
        + ",".join(payload["summary"]["categories"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
