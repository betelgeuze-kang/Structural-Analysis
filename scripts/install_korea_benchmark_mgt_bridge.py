#!/usr/bin/env python3
"""Install repo benchmark MGT into medium/large Korean source artifact paths (local only).

Copies midas_generator_33.optimized.mgt for pipeline/roundtrip validation until
operators attach real competition files. Receipt tags these as attach_provenance
repo_benchmark_bridge (sha256 match).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
KOREA = REPO_ROOT / "implementation/phase1/open_data/korea"

DEFAULT_TARGETS = (
    "koneps_goyang_changneung_powerplant_design_service",
    "lh_bucheon_yeokgok_a1_housing_native_baseline",
    "lh_happy_city_5_1_native_baseline",
    "lh_newtown_highrise_block_competition",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--targets",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help="source_id values under collected/artifacts/",
    )
    parser.add_argument("--also-curated", action="store_true", help="Update curated/*.mgt siblings")
    args = parser.parse_args()

    if not BENCHMARK.is_file():
        print(f"benchmark MGT missing: {BENCHMARK}", file=sys.stderr)
        return 1

    for source_id in args.targets:
        dest_dir = KOREA / "collected" / "artifacts" / source_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{source_id}.mgt"
        shutil.copy2(BENCHMARK, dest)
        print(f"installed {dest.stat().st_size} bytes -> {dest}")
        if args.also_curated:
            curated = KOREA / "curated" / f"{source_id}.mgt"
            if curated.parent.is_dir():
                shutil.copy2(BENCHMARK, curated)
                print(f"  curated -> {curated}")

    print("Next: python3 scripts/run_korean_medium_large_ingest_pipeline.py --run-roundtrip-parse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
