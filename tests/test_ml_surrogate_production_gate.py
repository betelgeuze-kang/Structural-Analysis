#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from ml_surrogate_production_gate import probe_ml_surrogate_production_gate  # noqa: E402


def test_ml_gate_disabled_by_default() -> None:
    os.environ.pop("PHASE1_ML_SURROGATE_OPT_IN", None)
    payload = probe_ml_surrogate_production_gate()
    assert payload["production_ml_wired"] is False
    assert payload["status"] == "disabled"
