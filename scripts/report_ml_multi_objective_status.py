#!/usr/bin/env python3
"""CLI: report honest ML / multi-objective status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from report_ml_multi_objective_status import build_ml_multi_objective_status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release_evidence/productization/ml_multi_objective_status.json",
    )
    args = parser.parse_args()
    payload = build_ml_multi_objective_status()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"ml-status: {payload['status']} production_ml_wired={payload['production_ml_wired']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
