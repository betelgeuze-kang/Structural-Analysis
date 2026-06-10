#!/usr/bin/env python3
"""CLI wrapper for the MGT surface shell bending/drilling smoke solve."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_surface_shell_bending_tangent import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
