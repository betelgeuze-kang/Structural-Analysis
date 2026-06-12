#!/usr/bin/env python3
"""CLI wrapper for building the validated ML surrogate checkpoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_ml_surrogate_checkpoint import (  # noqa: E402
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_STATE_NPZ,
    PRODUCTIZATION,
    build_ml_surrogate_checkpoint,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-npz", type=Path, default=DEFAULT_STATE_NPZ)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_ml_surrogate_checkpoint(
        state_npz=args.state_npz,
        checkpoint_dir=args.checkpoint_dir,
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "ml_surrogate_checkpoint_manifest.json")
    print(
        "ml-surrogate-checkpoint: "
        f"status={payload['status']} validation={payload['validation_pass']} "
        f"ood={payload['ood_pass']} -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
