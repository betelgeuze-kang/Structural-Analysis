#!/usr/bin/env python3
"""Write RH closure checklist JSON for authority workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_rh_closure_checklist import SCHEMA_VERSION, build_rh_closure_checklist  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rh-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json",
    )
    parser.add_argument(
        "--bundle-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release_evidence/productization/rh_closure_checklist.json",
    )
    args = parser.parse_args()

    rh = json.loads(args.rh_json.read_text(encoding="utf-8")) if args.rh_json.is_file() else {}
    bundle = json.loads(args.bundle_json.read_text(encoding="utf-8")) if args.bundle_json.is_file() else {}
    payload = build_rh_closure_checklist(rh_payload=rh, bundle=bundle)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"rh-checklist: {payload['status']} ({payload['open_count']} open) -> {args.output_json}")
    return 0 if payload.get("schema_version") == SCHEMA_VERSION else 1


if __name__ == "__main__":
    raise SystemExit(main())
