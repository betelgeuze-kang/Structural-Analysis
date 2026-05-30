#!/usr/bin/env python3
"""CLI: run story-model reanalysis receipt from solver state NPZ."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_story_model_reanalysis import (  # noqa: E402
    build_mgt_reanalysis_provenance,
    run_story_model_reanalysis,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-npz",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz",
    )
    parser.add_argument(
        "--changes-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    if not args.state_npz.is_file():
        print(f"story-reanalysis: missing state npz: {args.state_npz}", file=sys.stderr)
        return 2

    changes = {}
    if args.changes_json.is_file():
        changes = json.loads(args.changes_json.read_text(encoding="utf-8"))

    receipt = run_story_model_reanalysis(state_npz_path=args.state_npz, changes_payload=changes)
    mgt = build_mgt_reanalysis_provenance(roundtrip_json=args.roundtrip_json)
    payload = {"story_model_reanalysis": receipt, "mgt_provenance": mgt}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"story-reanalysis: {receipt['status']} drift={receipt['metrics']['max_drift_ratio_pct']:.3f}%")
    if args.fail_on_blocked and receipt.get("status") == "blocked":
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
