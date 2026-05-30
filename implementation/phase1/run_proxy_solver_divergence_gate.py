#!/usr/bin/env python3
"""Proxy vs solver-stage divergence gate for optimization changes (A-P2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "proxy-solver-divergence-gate.v1"


@dataclass(frozen=True)
class DivergenceRow:
    group_id: str
    issue: str
    cost_proxy_delta: float
    drift_delta_pct: float
    dcr_after: float


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def analyze_changes(
    changes_payload: dict[str, Any],
    *,
    min_cost_proxy_delta: float = 5.0,
    max_drift_delta_pct: float = 0.02,
    max_governing_dcr_after: float = 1.35,
    require_drift_stable_when_cost_moves: bool = True,
) -> dict[str, Any]:
    rows = changes_payload.get("changes") if isinstance(changes_payload.get("changes"), list) else []
    divergences: list[DivergenceRow] = []
    cost_moved = 0
    drift_moved = 0

    for change in rows:
        if not isinstance(change, dict):
            continue
        cost_delta = _safe_float(change.get("cost_proxy_delta"))
        drift_before = _safe_float(change.get("drift_before_pct"))
        drift_after = _safe_float(change.get("drift_after_pct"))
        drift_delta = abs(drift_after - drift_before)
        dcr_after = _safe_float(change.get("governing_member_governing_dcr_after"))
        max_dcr_after = _safe_float(change.get("max_dcr_after"))
        group_id = str(change.get("group_id") or change.get("group_index") or "")
        governing_dcr = dcr_after if dcr_after > 0 else max_dcr_after

        if abs(cost_delta) >= min_cost_proxy_delta:
            cost_moved += 1
        if drift_delta >= max_drift_delta_pct:
            drift_moved += 1

        if governing_dcr > max_governing_dcr_after:
            divergences.append(
                DivergenceRow(
                    group_id=group_id,
                    issue="governing_dcr_after_exceeds_limit",
                    cost_proxy_delta=cost_delta,
                    drift_delta_pct=drift_delta,
                    dcr_after=governing_dcr,
                )
            )
        if (
            require_drift_stable_when_cost_moves
            and abs(cost_delta) >= min_cost_proxy_delta
            and drift_delta < 1e-9
            and governing_dcr <= 0.0
            and max_dcr_after <= 0.0
        ):
            divergences.append(
                DivergenceRow(
                    group_id=group_id,
                    issue="cost_proxy_moved_without_solver_drift_or_dcr_signal",
                    cost_proxy_delta=cost_delta,
                    drift_delta_pct=drift_delta,
                    dcr_after=dcr_after,
                )
            )

    status = "pass" if not divergences else "warn"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim": "Heuristic proxy/solver consistency on optimization change rows; not structural approval.",
        "change_count": len(rows),
        "cost_proxy_moved_rows": cost_moved,
        "drift_moved_rows": drift_moved,
        "divergence_count": len(divergences),
        "thresholds": {
            "min_cost_proxy_delta": min_cost_proxy_delta,
            "max_drift_delta_pct": max_drift_delta_pct,
            "max_governing_dcr_after": max_governing_dcr_after,
            "require_drift_stable_when_cost_moves": require_drift_stable_when_cost_moves,
        },
        "divergences": [
            {
                "group_id": row.group_id,
                "issue": row.issue,
                "cost_proxy_delta": row.cost_proxy_delta,
                "drift_delta_pct": row.drift_delta_pct,
                "dcr_after": row.dcr_after,
            }
            for row in divergences
        ],
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
