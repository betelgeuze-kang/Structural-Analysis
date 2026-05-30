#!/usr/bin/env python3
"""Attach member_alignment (removed/added/merge) to optimization changes.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_optimization_member_alignment import enrich_changes_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changes-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--baseline-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.json",
    )
    parser.add_argument(
        "--optimized-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    args = parser.parse_args()
    for label, path in (
        ("changes", args.changes_json),
        ("baseline", args.baseline_json),
        ("optimized", args.optimized_json),
    ):
        if not path.is_file():
            print(f"enrich: missing {label}: {path}", file=sys.stderr)
            return 2

    enriched = enrich_changes_file(
        args.changes_json,
        baseline_path=args.baseline_json,
        optimized_path=args.optimized_json,
    )
    alignment = enriched.get("member_alignment") if isinstance(enriched.get("member_alignment"), dict) else {}
    print(
        "enrich: "
        f"removed={len(alignment.get('removed_member_ids') or [])} "
        f"added={len(alignment.get('added_member_ids') or [])} "
        f"merge_actions={alignment.get('group_merge_count', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
