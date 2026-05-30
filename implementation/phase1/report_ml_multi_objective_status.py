#!/usr/bin/env python3
"""Honest ML / multi-objective optimization status (A-P3); no false AI claims."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ml-multi-objective-status.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]

RUNNER_PATHS = (
    REPO_ROOT / "implementation/phase1/run_design_optimization_cost_reduction.py",
    REPO_ROOT / "implementation/phase1/run_design_optimization_solver_loop.py",
    REPO_ROOT / "implementation/phase1/design_optimization_env.py",
)


def _grep_ml_imports(path: Path) -> list[str]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    hits: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\b(import|from)\s+.*\b(torch|onnx|sklearn|tensorflow)\b", stripped, re.I):
            hits.append(stripped[:160])
        if re.search(r"\b(train_|surrogate|neural_operator|nsga)\b", stripped, re.I):
            hits.append(stripped[:160])
    return hits[:8]


def build_ml_multi_objective_status() -> dict[str, Any]:
    runner_hits: dict[str, list[str]] = {str(path.name): _grep_ml_imports(path) for path in RUNNER_PATHS}
    production_ml_wired = not any(runner_hits.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "not_started",
        "production_ml_wired": production_ml_wired,
        "multi_objective_pareto_wired": False,
        "claim": "Production optimization remains deterministic greedy/heuristic; ML/Pareto are research-track only.",
        "runner_static_scan": runner_hits,
        "next_step": "Optional: wire validated surrogate behind explicit opt-in flag before any AI marketing claim.",
    }
