#!/usr/bin/env python3
"""Story-model reanalysis check from optimization state (E-P1 / A-P1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from design_optimization.io import load_json, load_npz
from design_optimization_env import DesignOptimizationConfig
from run_design_optimization_solver_loop import _solver_stage_state


SCHEMA_VERSION = "story-model-reanalysis-receipt.v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def apply_optimization_changes_to_state(
    state: dict[str, np.ndarray],
    changes: list[dict[str, Any]],
) -> dict[str, np.ndarray]:
    """Apply final after_* fields from change rows onto group-indexed state arrays."""
    updated = {key: np.asarray(value).copy() for key, value in state.items()}
    rebar = updated.get("rebar_ratio")
    thickness = updated.get("thickness_scale")
    max_dcr = updated.get("max_dcr")
    group_count = int(rebar.shape[0]) if rebar is not None else 0
    if group_count <= 0:
        return updated

    if thickness is None:
        updated["thickness_scale"] = np.ones(group_count, dtype=np.float64)
        thickness = updated["thickness_scale"]
    if max_dcr is None:
        updated["max_dcr"] = np.zeros(group_count, dtype=np.float64)
        max_dcr = updated["max_dcr"]

    for change in changes:
        if not isinstance(change, dict):
            continue
        group_index = int(change.get("group_index", -1))
        if group_index < 0 or group_index >= group_count:
            continue
        if "after_rebar_ratio" in change:
            rebar[group_index] = _safe_float(change.get("after_rebar_ratio"), float(rebar[group_index]))
        if "after_thickness_scale" in change:
            thickness[group_index] = _safe_float(change.get("after_thickness_scale"), float(thickness[group_index]))
        if "max_dcr_after" in change:
            max_dcr[group_index] = _safe_float(change.get("max_dcr_after"), float(max_dcr[group_index]))
        if "governing_member_governing_dcr_after" in change:
            member_dcr = updated.get("member_governing_dcr")
            if member_dcr is not None and group_index < member_dcr.shape[0]:
                member_dcr[group_index] = _safe_float(
                    change.get("governing_member_governing_dcr_after"),
                    float(member_dcr[group_index]),
                )

    updated["rebar_ratio"] = rebar
    updated["thickness_scale"] = thickness
    updated["max_dcr"] = max_dcr
    return updated


def run_story_model_reanalysis(
    *,
    state_npz_path: Path,
    changes_payload: dict[str, Any] | None = None,
    cfg: DesignOptimizationConfig | None = None,
) -> dict[str, Any]:
    state = load_npz(state_npz_path)
    changes = changes_payload.get("changes") if isinstance(changes_payload, dict) else None
    if isinstance(changes, list) and changes:
        state = apply_optimization_changes_to_state(state, changes)

    config = cfg or DesignOptimizationConfig()
    stage = _solver_stage_state(state=state, cfg=config)
    drift_pct = _safe_float(stage.get("max_drift_pct"))
    residual_drift_pct = _safe_float(stage.get("residual_drift_pct"))
    governing_dcr = _safe_float(stage.get("max_dcr"), float(np.max(np.asarray(state.get("max_dcr", [0.0]), dtype=np.float64))))
    converged = bool(stage.get("converged_all_steps", False))
    collapsed = bool(stage.get("collapsed", False))
    feasible = bool(stage.get("feasible", False))

    status = "pass"
    blockers: list[str] = []
    if not converged:
        blockers.append("ndtha_not_converged")
        status = "warn"
    if collapsed:
        blockers.append("ndtha_collapsed")
        status = "blocked"
    if drift_pct > float(config.drift_limit_pct):
        blockers.append("drift_limit_exceeded")
        status = "blocked"
    if governing_dcr > float(config.dcr_limit):
        blockers.append("dcr_limit_exceeded")
        if status == "pass":
            status = "warn"
    if not feasible and status == "pass":
        status = "warn"
        blockers.append("stage_not_feasible")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim": "Reduced story shear-building reanalysis on optimization terminal state; not licensed approval.",
        "state_npz_path": str(state_npz_path),
        "change_count": len(changes) if isinstance(changes, list) else 0,
        "metrics": {
            "max_drift_ratio_pct": drift_pct,
            "residual_drift_ratio_pct": residual_drift_pct,
            "governing_max_dcr": round(governing_dcr, 4),
            "drift_limit_pct": float(config.drift_limit_pct),
            "dcr_limit": float(config.dcr_limit),
            "feasible": feasible,
            "violation_score": _safe_float(stage.get("violation_score")),
        },
        "solver": {
            "backend_static": str(stage.get("backend_static") or ""),
            "backend_ndtha": str(stage.get("backend_ndtha") or ""),
            "converged_all_steps": converged,
            "collapsed": collapsed,
            "static_converged": bool(stage.get("static_converged", False)),
        },
        "blockers": blockers,
    }


def build_mgt_reanalysis_provenance(*, roundtrip_json: Path, mgt_path: Path | None = None) -> dict[str, Any]:
    payload = load_json(roundtrip_json)
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    resolved_mgt = mgt_path or Path(str(source.get("path") or ""))
    if not resolved_mgt.is_absolute():
        repo_root = Path(__file__).resolve().parents[2]
        resolved_mgt = repo_root / resolved_mgt
    parser = payload.get("parser") if isinstance(payload.get("parser"), dict) else {}
    section_counts = parser.get("section_counts") if isinstance(parser.get("section_counts"), dict) else {}
    return {
        "schema_version": "mgt-reanalysis-provenance.v1",
        "mgt_path": str(resolved_mgt),
        "mgt_exists": resolved_mgt.is_file(),
        "mgt_sha256": str(source.get("sha256") or ""),
        "element_count": int(section_counts.get("ELEMENT") or 0),
        "node_count": int(section_counts.get("NODE") or 0),
        "native_solve_status": "not_wired",
        "story_model_proxy_status": "wired_via_state_npz",
        "note": "MGT native solver loop not connected; story-model check uses optimization state NPZ.",
    }
