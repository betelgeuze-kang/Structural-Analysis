#!/usr/bin/env python3
"""CLI: validate productization delivery evidence artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from validate_productization_delivery_evidence import validate_productization_delivery_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--productization-dir",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release_evidence/productization",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--allow-review-required", action="store_true")
    args = parser.parse_args()

    payload = validate_productization_delivery_evidence(
        productization_dir=args.productization_dir,
        require_bundle_ready=not args.allow_review_required,
    )
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"productization-validate: {payload['status']} missing={len(payload.get('files_missing') or [])}")
    if payload.get("errors"):
        print(f"productization-validate: errors={payload['errors']}", file=sys.stderr)
    return 0 if payload.get("status") == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
