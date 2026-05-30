#!/usr/bin/env python3
"""CLI: build signed RH closure packets and apply to residual holdout sidecar."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from design_optimization.io import load_json  # noqa: E402
from finalize_rh_signed_closure import (  # noqa: E402
    apply_rh_signed_closure_packets,
    build_all_rh_signed_closure_packets,
)


def main() -> int:
    productization = REPO_ROOT / "implementation/phase1/release_evidence/productization"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-json", type=Path, default=productization / "delivery_evidence_bundle.json")
    parser.add_argument("--rh-json", type=Path, default=productization / "residual_holdout_closure_updates.json")
    parser.add_argument("--packet-dir", type=Path, default=productization / "rh_signed_closure_packets")
    parser.add_argument("--output-json", type=Path, default=productization / "residual_holdout_closure_updates.json")
    args = parser.parse_args()

    bundle = load_json(args.bundle_json)
    rh = load_json(args.rh_json)
    build_all_rh_signed_closure_packets(rh_payload=rh, bundle=bundle, out_dir=args.packet_dir)
    updated = apply_rh_signed_closure_packets(rh_payload=rh, bundle=bundle, packet_dir=args.packet_dir)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    closed = sum(
        1
        for row in (updated.get("updates") or {}).values()
        if isinstance(row, dict) and str(row.get("status") or "") == "closed"
    )
    print(f"rh-closure: closed={closed} status={updated.get('rh_closure_status')} -> {args.output_json}")
    return 0 if updated.get("rh_closure_status") == "closed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
