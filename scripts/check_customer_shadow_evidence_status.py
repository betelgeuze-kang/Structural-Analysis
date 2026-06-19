#!/usr/bin/env python3
"""Wrapper for the customer shadow evidence status gate."""

from __future__ import annotations

from pathlib import Path
import runpy


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "implementation/phase1/check_customer_shadow_evidence_status.py"


if __name__ == "__main__":
    runpy.run_path(str(TARGET), run_name="__main__")
