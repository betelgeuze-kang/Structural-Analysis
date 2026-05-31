#!/usr/bin/env python3
"""Build MIDAS Gen same-mesh result proxy from commercial HF export medians + MGT roundtrip SHA."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from design_optimization.io import load_json
from ingest_midas_gen_same_mesh_result import SCHEMA_VERSION


def _hf_medians(crossval_json: Path) -> dict[str, float]:
    payload = load_json(crossval_json)
    drifts: list[float] = []
    shears: list[float] = []
    tops: list[float] = []
    for case in payload.get("cases") or []:
        if not isinstance(case, dict):
            continue
        for row in case.get("metrics") or []:
            if not isinstance(row, dict):
                continue
            metric = str(row.get("metric") or "")
            if metric == "drift_ratio_pct":
                drifts.append(float(row.get("hf") or 0.0))
            elif metric == "base_shear_kN":
                shears.append(float(row.get("hf") or 0.0))
            elif metric == "top_displacement_m":
                tops.append(float(row.get("hf") or 0.0))
    if not drifts:
        return {}
    return {
        "drift_ratio_pct": float(np.median(drifts)),
        "base_shear_kN": float(np.median(shears)) if shears else 0.0,
        "top_displacement_m": float(np.median(tops)) if tops else 0.0,
    }


def build_midas_gen_same_mesh_result_proxy(
    *,
    roundtrip_json: Path,
    commercial_crossval_json: Path,
) -> dict[str, Any]:
    roundtrip = load_json(roundtrip_json)
    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    medians = _hf_medians(commercial_crossval_json)
    blockers: list[str] = []
    if not medians:
        blockers.append("commercial_hf_medians_missing")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": "midas_gen_export_proxy",
            "note": (
                "Proxy same-mesh metrics from commercial HF export medians aligned to optimized MGT SHA256. "
                "Replace with live MIDAS Gen result JSON when available."
            ),
            "mgt_sha256": str(source.get("sha256") or ""),
            "roundtrip_json": str(roundtrip_json),
            "commercial_crossval_json": str(commercial_crossval_json),
        },
        "metrics": medians,
        "blockers": blockers,
    }
