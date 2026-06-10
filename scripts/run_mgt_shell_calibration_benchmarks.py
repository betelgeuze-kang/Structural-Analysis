#!/usr/bin/env python3
"""CLI wrapper for MGT shell calibration benchmarks."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_shell_calibration_benchmarks import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
