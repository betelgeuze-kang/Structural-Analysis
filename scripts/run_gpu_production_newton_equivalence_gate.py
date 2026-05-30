#!/usr/bin/env python3
"""CLI: production GPU Newton vs closed-form equivalence on story fingerprint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_gpu_production_newton_equivalence_gate import build_gpu_production_newton_equivalence_gate  # noqa: E402


def main() -> int:
    productization = REPO_ROOT / "implementation/phase1/release_evidence/productization"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-npz",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz",
    )
    parser.add_argument("--output-json", type=Path, default=productization / "gpu_production_newton_equivalence_gate.json")
    args = parser.parse_args()
    payload = build_gpu_production_newton_equivalence_gate(state_npz_path=args.state_npz)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gpu-equiv: {payload['status']} -> {args.output_json}")
    return 0 if payload.get("production_newton_equivalent_to_closed_form") else 1


if __name__ == "__main__":
    raise SystemExit(main())
