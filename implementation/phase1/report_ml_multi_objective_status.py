#!/usr/bin/env python3
"""Honest ML / multi-objective optimization status (A-P3); no false AI claims."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml_surrogate_production_gate import probe_ml_surrogate_production_gate


SCHEMA_VERSION = "ml-multi-objective-status.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]

RUNNER_PATHS = (
    REPO_ROOT / "implementation/phase1/run_design_optimization_cost_reduction.py",
    REPO_ROOT / "implementation/phase1/run_design_optimization_solver_loop.py",
    REPO_ROOT / "implementation/phase1/design_optimization_env.py",
)

ML_PRODUCTION_PATTERNS = (
    r"\bfrom\s+implementation\.phase1\.train_",
    r"\btrain_neural_operator_surrogate\b",
    r"\bneural_operator_surrogate\b",
    r"\bNSGA[\w]*\b",
    r"\bpareto_front\b",
    r"\bimport\s+sklearn\b",
    r"\bimport\s+tensorflow\b",
)


def _grep_ml_production_refs(path: Path) -> list[str]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    hits: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if any(re.search(pattern, stripped, re.I) for pattern in ML_PRODUCTION_PATTERNS):
            hits.append(stripped[:160])
    return hits[:8]


def build_ml_multi_objective_status(
    *,
    pareto_archive_json: Path | None = None,
) -> dict[str, Any]:
    runner_hits: dict[str, list[str]] = {str(path.name): _grep_ml_production_refs(path) for path in RUNNER_PATHS}
    production_ml_wired = any(runner_hits.values())
    pareto_path = pareto_archive_json or (
        REPO_ROOT
        / "implementation/phase1/release_evidence/productization/optimization_pareto_research_archive.json"
    )
    pareto_payload: dict[str, Any] = {}
    if pareto_path.is_file():
        import json

        pareto_payload = json.loads(pareto_path.read_text(encoding="utf-8"))
    pareto_ready = str(pareto_payload.get("status") or "") == "research_archive_ready"
    pareto_count = int(pareto_payload.get("pareto_front_count") or 0)
    ml_gate = probe_ml_surrogate_production_gate()
    production_ml_wired = production_ml_wired or bool(ml_gate.get("production_ml_wired"))
    if production_ml_wired:
        overall_status = "production_shadow_solver_gated_ready"
    elif pareto_ready:
        overall_status = "research_archive_ready"
    else:
        overall_status = "not_started"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": overall_status,
        "production_ml_wired": production_ml_wired,
        "multi_objective_pareto_wired": False,
        "research_pareto_archive_ready": pareto_ready,
        "research_pareto_front_count": pareto_count,
        "ml_surrogate_production_gate": ml_gate,
        "claim": (
            "Production optimization remains solver/code gated; validated ML may run only in "
            "shadow_with_solver_fallback mode and cannot bypass hard gates."
        ),
        "runner_static_scan": runner_hits,
        "pareto_archive_path": str(pareto_path) if pareto_path.is_file() else "",
        "next_step": (
            "Broaden checkpoint validation beyond the current bounded design-optimization state before using "
            "surrogate output for autonomous design action ranking."
        )
        if production_ml_wired
        else "Build validated checkpoint with dataset/model cards, OOD gate, and solver fallback receipt.",
    }
