#!/usr/bin/env python3
"""Validate a live MIDAS Gen export and install it as the canonical same-mesh result JSON."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from validate_midas_gen_same_mesh_result import validate_midas_gen_same_mesh_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-result-json", type=Path, required=True)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument(
        "--install-path",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json",
    )
    args = parser.parse_args()
    validation = validate_midas_gen_same_mesh_result(
        result_json=args.live_result_json,
        roundtrip_json=args.roundtrip_json,
    )
    if validation.get("status") != "pass":
        print(f"install blocked: {validation.get('failed_checks')}", file=sys.stderr)
        return 1
    if not validation.get("live_export_ready"):
        print("install blocked: source.kind must be midas_gen_live_export", file=sys.stderr)
        return 1
    args.install_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.live_result_json, args.install_path)
    print(f"installed: {args.install_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
