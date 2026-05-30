#!/usr/bin/env python3
"""CLI: GPU Newton certification honesty checklist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_gpu_newton_certification_checklist import build_gpu_newton_certification_checklist  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-npz",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/gpu_newton_certification_checklist.json",
    )
    args = parser.parse_args()
    if not args.state_npz.is_file():
        print(f"gpu-newton-checklist: missing {args.state_npz}", file=sys.stderr)
        return 2

    payload = build_gpu_newton_certification_checklist(state_npz_path=args.state_npz)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gpu-newton-checklist: {payload['status']} -> {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
