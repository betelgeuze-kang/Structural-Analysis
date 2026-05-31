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


def _resolve_sds(params: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Use explicit SDS if given, else derive SDS = 2.5 * Z * Fa (KDS 41 17 00 short-period plateau)."""
    explicit = params.get("SDS") if params.get("SDS") is not None else params.get("sds")
    if explicit is not None:
        return float(explicit), {"sds_basis": "explicit_SDS_in_params"}
    zone_z = float(params.get("zone_factor_Z") or params.get("Z") or 0.11)
    fa = float(params.get("Fa") or params.get("site_coefficient_Fa") or 1.4)
    sds = 2.5 * zone_z * fa
    return sds, {
        "sds_basis": "derived_2p5_Z_Fa",
        "zone_factor_Z": zone_z,
        "site_coefficient_Fa": fa,
        "site_class": params.get("site_class"),
        "seismic_zone": params.get("seismic_zone"),
    }


def compute_equivalent_static_cs(
    *,
    params: dict[str, Any] | None = None,
    height_m: float | None = None,
) -> dict[str, Any]:
    """Cs = SDS / (R * Ie) — equivalent-static lateral coefficient (short-period plateau)."""
    params = params or load_kds_seismic_design_params()
    sds, sds_meta = _resolve_sds(params)
    r_factor = float(params.get("R") or params.get("response_modification_factor") or 5.0)
    ie = float(params.get("Ie") or params.get("importance_factor") or 1.0)
    r_factor = max(r_factor, 1.0)
    ie = max(ie, 1.0)
    cs_raw = sds / (r_factor * ie)
    # KDS minimum equivalent-static coefficient floor.
    cs_floor = 0.01
    cs = max(cs_raw, cs_floor)

    if height_m is not None and float(height_m) < 20.0:
        regime = "low_rise_gravity_dominant"
        period_note = "short period on constant-acceleration plateau; Cs=SDS/(R*Ie) governs"
    else:
        regime = "general"
        period_note = "T-dependent SD1/(T*R*Ie) cap not applied; verify for taller/flexible structures"

    return {
        "cs": float(cs),
        "cs_raw": float(cs_raw),
        "cs_floor_applied": bool(cs < cs_raw + 1e-12 and cs_raw < cs_floor),
        "SDS": float(sds),
        "R": r_factor,
        "Ie": ie,
        "formula": "Cs = SDS / (R * Ie)",
        "code_basis": "KDS 41 17 00 equivalent-static simplification (project params file)",
        "height_regime": regime,
        "period_assumption": period_note,
        "sds_derivation": sds_meta,
        "params_source": str(params.get("_path") or DEFAULT_PARAMS_PATH),
    }
