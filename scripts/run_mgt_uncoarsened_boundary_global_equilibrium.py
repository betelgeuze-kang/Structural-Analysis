#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
sys.path.insert(0, str(PHASE1))

from run_mgt_uncoarsened_boundary_global_equilibrium import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
