#!/usr/bin/env python3
"""CLI: build optimization Pareto research archive from cost-reduction changes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_optimization_pareto_research_archive import build_optimization_pareto_research_archive  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changes-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/optimization_pareto_research_archive.json",
    )
    args = parser.parse_args()
    payload = build_optimization_pareto_research_archive(changes_json=args.changes_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"pareto-archive: {payload['status']} front={payload['pareto_front_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
