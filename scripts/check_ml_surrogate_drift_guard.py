#!/usr/bin/env python3
"""CI gate: enforce ML surrogate drift guard status.

Exits non-zero if the drift guard fired (status=guard_fired,
decision=disarm_recommended) or if the production ML surrogate is
wired but the gate was forced disabled. Used by CI to block merges when
the shadow inference is no longer within the validated drift band.

Usage:
  python3 scripts/check_ml_surrogate_drift_guard.py [--receipt PATH] [--fail-closed]

Defaults:
  --receipt implementation/phase1/release_evidence/productization/ml_surrogate_drift_guard_receipt.json
  --fail-closed  (default: True, fail when guard fires)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/ml_surrogate_drift_guard_receipt.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--fail-closed",
        action="store_true",
        default=True,
        help="Return non-zero when guard fires (default).",
    )
    parser.add_argument(
        "--no-fail-closed",
        dest="fail_closed",
        action="store_false",
        help="Always return 0 (smoke mode).",
    )
    args = parser.parse_args()
    if not args.receipt.is_file():
        print(f"check-ml-surrogate-drift-guard: receipt missing -> {args.receipt}", file=sys.stderr)
        return 2
    payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    decision = str(payload.get("drift_guard_decision") or "")
    status = str(payload.get("status") or "")
    breach_count = int(payload.get("drift_breach_count") or 0)
    if status == "guard_fired" or decision == "disarm_recommended":
        print(
            f"check-ml-surrogate-drift-guard: FAIL decision={decision} breaches={breach_count} "
            f"status={status} -> {args.receipt}",
            file=sys.stderr,
        )
        return 1 if args.fail_closed else 0
    if status not in {"ready"}:
        print(
            f"check-ml-surrogate-drift-guard: FAIL status={status} decision={decision} "
            f"-> {args.receipt}",
            file=sys.stderr,
        )
        return 1 if args.fail_closed else 0
    print(
        f"check-ml-surrogate-drift-guard: PASS decision={decision} breaches={breach_count} "
        f"-> {args.receipt}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
