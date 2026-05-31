#!/usr/bin/env python3
"""Print resolved MIDAS same-mesh result JSON path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from resolve_midas_same_mesh_result_path import resolve_midas_same_mesh_result_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, required=True)
    args = parser.parse_args()
    path, kind = resolve_midas_same_mesh_result_path(roundtrip_json=args.roundtrip_json)
    print(f"{path}\t{kind}")
    return 0 if path.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
