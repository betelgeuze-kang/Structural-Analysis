#!/usr/bin/env python3
"""KDS 41–style equivalent-static seismic coefficient (Cs) for model-derived base shear."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from design_optimization.io import load_json


SCHEMA_VERSION = "kds-seismic-design-params.v1"
DEFAULT_PARAMS_PATH = (
    Path(__file__).resolve().parent / "open_data" / "kds" / "seismic_design_params.json"
)


def load_kds_seismic_design_params(path: Path | None = None) -> dict[str, Any]:
    params_path = path or Path(
        str(os.environ.get("PHASE1_KDS_SEISMIC_PARAMS_JSON") or DEFAULT_PARAMS_PATH)
    )
    if not params_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "SDS": 0.225,
            "R": 5.0,
            "Ie": 1.0,
            "note": "Built-in low-rise default (edit open_data/kds/seismic_design_params.json)",
            "_path": str(params_path),
        }
    payload = load_json(params_path)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["_path"] = str(params_path)
        return payload
    return {"_path": str(params_path)}


def compute_equivalent_static_cs(
    *,
    params: dict[str, Any] | None = None,
    height_m: float | None = None,
) -> dict[str, Any]:
    """Cs = SDS / (R * Ie) — simplified equivalent-static lateral force coefficient."""
    params = params or load_kds_seismic_design_params()
    sds = float(params.get("SDS") or params.get("sds") or 0.225)
    r_factor = float(params.get("R") or params.get("response_modification_factor") or 5.0)
    ie = float(params.get("Ie") or params.get("importance_factor") or 1.0)
    r_factor = max(r_factor, 1.0)
    ie = max(ie, 1.0)
    cs = sds / (r_factor * ie)

    if height_m is not None and float(height_m) < 20.0:
        regime = "low_rise_gravity_dominant"
    else:
        regime = "general"

    return {
        "cs": float(cs),
        "SDS": sds,
        "R": r_factor,
        "Ie": ie,
        "formula": "Cs = SDS / (R * Ie)",
        "code_basis": "KDS 41 0000 equivalent-static simplification (project params file)",
        "height_regime": regime,
        "params_source": str(params.get("_path") or DEFAULT_PARAMS_PATH),
    }
