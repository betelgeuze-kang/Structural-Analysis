#!/usr/bin/env python3
"""CLI wrapper for material/element tangent support matrix generation."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from build_material_element_tangent_support_matrix import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
