#!/usr/bin/env python3
"""Write RH engineer review HTML packet from template JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template-json",
        type=Path,
        default=PRODUCTIZATION / "rh_signed_closure_packet_template.json",
    )
    parser.add_argument(
        "--bundle-json",
        type=Path,
        default=PRODUCTIZATION / "delivery_evidence_bundle.json",
    )
    parser.add_argument(
        "--output-html",
        type=Path,
        default=PRODUCTIZATION / "rh_engineer_review_packet_template.html",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from build_rh_engineer_review_packet_html import build_rh_engineer_review_packet_html  # noqa: E402

    template = json.loads(args.template_json.read_text(encoding="utf-8")) if args.template_json.is_file() else {}
    bundle = json.loads(args.bundle_json.read_text(encoding="utf-8")) if args.bundle_json.is_file() else {}
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    payload = build_rh_engineer_review_packet_html(template_payload=template, bundle_summary=summary)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.write_text(payload["html"], encoding="utf-8")
    meta_path = args.output_html.with_suffix(".json")
    meta_path.write_text(
        json.dumps({key: value for key, value in payload.items() if key != "html"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"rh-html: {payload['status']} -> {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
