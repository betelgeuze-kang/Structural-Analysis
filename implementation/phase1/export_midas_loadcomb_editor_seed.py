#!/usr/bin/env python3
"""Export MIDAS LOADCOMB preview text from embedded editor seed metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from implementation.phase1.load_combination_engine import export_midas_loadcomb_from_model_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-json", required=True, help="Model JSON with embedded load_combination_editor_seed metadata.")
    parser.add_argument("--out", required=True, help="Output .mgt preview path for the LOADCOMB block.")
    parser.add_argument("--no-comments", action="store_true", help="Omit LOADCOMB header comments.")
    args = parser.parse_args()

    model_path = Path(args.model_json)
    out_path = Path(args.out)
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    text = export_midas_loadcomb_from_model_payload(payload, include_comments=not args.no_comments)
    if not text.strip():
        raise SystemExit("No exportable load combination editor seed found in model payload.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote LOADCOMB export preview: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
