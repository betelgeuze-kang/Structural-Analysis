#!/usr/bin/env python3
"""CLI: generate Korean public-structure source catalog (default + medium/large extension seed)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.generate_korean_source_catalog import main  # noqa: E402

if __name__ == "__main__":
    main()
