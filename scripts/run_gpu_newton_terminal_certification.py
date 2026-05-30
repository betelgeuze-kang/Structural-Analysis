#!/usr/bin/env python3
"""CLI: run GPU Newton terminal certification against CPU Rust reference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from gpu_newton_terminal_certification import certify_gpu_newton_terminal  # noqa: E402


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
        / "implementation/phase1/release_evidence/productization/gpu_newton_terminal_certification.json",
    )
    parser.add_argument(
        "--production-equivalence-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/gpu_production_newton_equivalence_gate.json",
    )
    args = parser.parse_args()
    if not args.state_npz.is_file():
        print(f"gpu-newton-cert: missing {args.state_npz}", file=sys.stderr)
        return 2
    equiv_path = args.production_equivalence_json if args.production_equivalence_json.is_file() else None
    payload = certify_gpu_newton_terminal(
        state_npz_path=args.state_npz,
        production_equivalence_path=equiv_path,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gpu-newton-cert: {payload['status']} proven={payload['gpu_newton_terminal_proven']} -> {args.output_json}")
    return 0 if payload.get("gpu_newton_terminal_proven") else 1


if __name__ == "__main__":
    raise SystemExit(main())
