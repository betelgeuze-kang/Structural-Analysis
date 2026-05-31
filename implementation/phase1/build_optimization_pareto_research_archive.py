#!/usr/bin/env python3
"""Build non-dominated Pareto archive from optimization change rows (research track, not production ML)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json


SCHEMA_VERSION = "optimization-pareto-research-archive.v1"


def _objective_tuple(row: dict[str, Any]) -> tuple[float, float, float]:
    cost = float(row.get("cost_proxy_after") or row.get("cost_proxy_before") or 0.0)
    dcr = float(row.get("governing_member_governing_dcr_after") or row.get("max_dcr_after") or 0.0)
    drift = float(row.get("drift_after_pct") or row.get("drift_before_pct") or 0.0)
    return cost, dcr, drift


def _dominates(a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _pareto_front(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = [(row, _objective_tuple(row)) for row in rows]
    front: list[dict[str, Any]] = []
    for row, obj in points:
        if any(_dominates(other_obj, obj) for _, other_obj in points if other_obj != obj):
            continue
        front.append(
            {
                "group_id": row.get("group_id"),
                "action_name": row.get("action_name"),
                "objectives": {
                    "cost_proxy_after": obj[0],
                    "governing_dcr_after": obj[1],
                    "drift_after_pct": obj[2],
                },
            }
        )
    return front


def build_optimization_pareto_research_archive(
    *,
    changes_json: Path,
) -> dict[str, Any]:
    payload = load_json(changes_json)
    changes = [row for row in (payload.get("changes") or []) if isinstance(row, dict)]
    candidates = [
        row
        for row in changes
        if str(row.get("selection_gate") or "") in {"hard_gate_pass", "soft_gate_pass", "selected"}
        or str(row.get("reason_selected") or "").startswith("selected")
    ]
    if not candidates:
        candidates = changes
    front = _pareto_front(candidates)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "research_archive_ready" if front else "empty",
        "claim": (
            "Pareto archive from applied optimization change rows (cost vs DCR vs drift). "
            "Research-track only; production search remains deterministic greedy."
        ),
        "source_changes_json": str(changes_json),
        "candidate_count": len(candidates),
        "pareto_front_count": len(front),
        "pareto_front": front[:64],
        "production_pareto_wired": False,
    }
