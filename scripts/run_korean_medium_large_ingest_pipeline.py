#!/usr/bin/env python3
"""CLI: regenerate catalog, collect, and verify medium/large Korean MGT attachments."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.run_korean_medium_large_ingest_pipeline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
