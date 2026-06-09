#!/usr/bin/env python3
"""CLI wrapper for full line-element 6-DOF frame sparse equilibrium solve."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_full_frame_6dof_sparse_equilibrium import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
