#!/usr/bin/env python3
"""CLI: MGT integrity check + story-model reanalysis pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_native_reanalysis_pipeline import run_mgt_native_reanalysis_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument(
        "--changes-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--state-npz",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--fail-on-blocked", action="store_true")
    parser.add_argument(
        "--sync-provenance",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Sync roundtrip source.sha256 to on-disk MGT before checks.",
    )
    parser.add_argument(
        "--refresh-parse",
        action="store_true",
        help="Re-parse optimized MGT into roundtrip JSON (slow).",
    )
    args = parser.parse_args()

    for label, path in (
        ("roundtrip", args.roundtrip_json),
        ("changes", args.changes_json),
        ("state", args.state_npz),
    ):
        if not path.is_file():
            print(f"mgt-pipeline: missing {label}: {path}", file=sys.stderr)
            return 2

    payload = run_mgt_native_reanalysis_pipeline(
        roundtrip_json=args.roundtrip_json,
        changes_json=args.changes_json,
        state_npz=args.state_npz,
        refresh_parse=args.refresh_parse,
        sync_provenance=args.sync_provenance,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"mgt-pipeline: {payload['status']} -> {args.output_json}")
    if args.fail_on_blocked and payload.get("status") == "blocked":
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
