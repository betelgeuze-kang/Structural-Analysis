#!/usr/bin/env python3
"""Write RH signed-closure packet template JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_rh_signed_closure_packet_template import build_rh_signed_closure_packet_template  # noqa: E402

PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rh-json",
        type=Path,
        default=PRODUCTIZATION / "residual_holdout_closure_updates.json",
    )
    parser.add_argument(
        "--checklist-json",
        type=Path,
        default=PRODUCTIZATION / "rh_closure_checklist.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PRODUCTIZATION / "rh_signed_closure_packet_template.json",
    )
    args = parser.parse_args()

    rh = json.loads(args.rh_json.read_text(encoding="utf-8")) if args.rh_json.is_file() else {}
    checklist = json.loads(args.checklist_json.read_text(encoding="utf-8")) if args.checklist_json.is_file() else {}
    payload = build_rh_signed_closure_packet_template(rh_payload=rh, checklist=checklist)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"rh-template: {payload['status']} ({payload['open_count']} open) -> {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
