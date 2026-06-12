#!/usr/bin/env python3
"""Wrapper for AI input normalization and code-reasoning guard artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.build_ai_input_code_guard_artifacts import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
