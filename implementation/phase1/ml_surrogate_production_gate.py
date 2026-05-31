#!/usr/bin/env python3
"""Opt-in gate for ML surrogate in production optimization (default off)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ml-surrogate-production-gate.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def probe_ml_surrogate_production_gate() -> dict[str, Any]:
    opt_in = str(os.environ.get("PHASE1_ML_SURROGATE_OPT_IN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    checkpoint = Path(
        str(os.environ.get("PHASE1_ML_SURROGATE_CHECKPOINT") or "")
        or REPO_ROOT / "implementation/phase1/release/ml_surrogate/checkpoint.pt"
    )
    checkpoint_ready = checkpoint.is_file()
    wired = opt_in and checkpoint_ready
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "opt_in_env": "PHASE1_ML_SURROGATE_OPT_IN",
        "checkpoint_env": "PHASE1_ML_SURROGATE_CHECKPOINT",
        "opt_in_enabled": opt_in,
        "checkpoint_path": str(checkpoint),
        "checkpoint_ready": checkpoint_ready,
        "production_ml_wired": wired,
        "status": "production_ready" if wired else ("opt_in_without_checkpoint" if opt_in else "disabled"),
        "claim": "ML surrogate affects optimization only when opt-in and checkpoint are both present.",
    }


def try_apply_ml_surrogate_cost_adjustment(*, base_cost: float) -> tuple[float, dict[str, Any]]:
    gate = probe_ml_surrogate_production_gate()
    if not gate.get("production_ml_wired"):
        return float(base_cost), {"applied": False, "gate": gate}
    return float(base_cost), {"applied": False, "gate": gate, "note": "Checkpoint present; surrogate hook reserved for validated model."}
