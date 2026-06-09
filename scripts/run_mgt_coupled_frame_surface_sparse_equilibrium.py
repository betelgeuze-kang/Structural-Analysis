#!/usr/bin/env python3
"""CLI wrapper for coupled MGT frame + surface sparse equilibrium."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_coupled_frame_surface_sparse_equilibrium import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
