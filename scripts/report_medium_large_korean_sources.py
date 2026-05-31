#!/usr/bin/env python3
"""CLI: medium/large Korean public-structure source report."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.report_medium_large_korean_sources import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
