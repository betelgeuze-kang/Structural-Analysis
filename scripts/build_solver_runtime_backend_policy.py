#!/usr/bin/env python3
"""CLI wrapper for solver runtime backend policy receipt generation."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_solver_runtime_backend_policy import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
