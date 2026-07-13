#!/usr/bin/env python3
"""Emit a strict Engine v2 native HIP capability receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.hip import (  # noqa: E402
    probe_hip_capability,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe libamdhip64 without allocating an Engine v2 context."
    )
    parser.add_argument("--device-ordinal", type=int, default=0)
    parser.add_argument("--runtime-library", type=Path)
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = probe_hip_capability(
            runtime_library=args.runtime_library,
            device_ordinal=args.device_ordinal,
        )
        rendered = json.dumps(
            receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        )
        if args.out is None:
            print(rendered)
        else:
            args.out.write_text(rendered + "\n", encoding="utf-8")
        return 0 if receipt.status == "ready" else 2
    except (OSError, TypeError, ValueError) as exc:
        print(f"HIP probe contract error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
