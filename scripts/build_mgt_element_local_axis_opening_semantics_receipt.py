#!/usr/bin/env python3
"""CLI wrapper for the MGT element local-axis/opening semantics receipt."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_mgt_element_local_axis_opening_semantics_receipt import main  # noqa: E402


if __name__ == "__main__":
    main()
