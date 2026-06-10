#!/usr/bin/env python3
"""CLI wrapper for the native MGT modal and buckling eigen solver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_native_modal_buckling_solver import (  # noqa: E402
    DEFAULT_CROSSVAL,
    DEFAULT_ROUNDTRIP,
    PRODUCTIZATION,
    run_mgt_native_modal_buckling_solver,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--commercial-crossval-json", type=Path, default=DEFAULT_CROSSVAL)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_native_modal_buckling_solver.json")
    parser.add_argument("--max-elements", type=int, default=420)
    parser.add_argument("--mode-count", type=int, default=4)
    args = parser.parse_args()

    payload = run_mgt_native_modal_buckling_solver(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        commercial_crossval_json=args.commercial_crossval_json,
        output_json=args.output_json,
        max_elements=args.max_elements,
        mode_count=args.mode_count,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "mgt-native-modal-buckling: "
        f"status={payload.get('status')} "
        f"modes={(payload.get('modal_solve') or {}).get('mode_count')} "
        f"critical={(payload.get('buckling_solve') or {}).get('critical_load_factor')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
