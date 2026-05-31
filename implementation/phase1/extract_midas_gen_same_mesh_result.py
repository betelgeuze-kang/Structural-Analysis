#!/usr/bin/env python3
"""Extract same-mesh KPIs directly from the optimized MGT model (model-derived estimate).

This is NOT a licensed MIDAS Gen solver run. It rigorously computes the quantities that
exist in the model file (seismic mass/weight, height) and an equivalent-static base shear
under a documented seismic coefficient. Drift/top-displacement are code-target estimates and
are flagged with explicit assumptions + confidence, because the in-repo partial beam submesh
is not a valid full-building lateral model.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from design_optimization.io import load_json
from ingest_midas_gen_same_mesh_result import SCHEMA_VERSION
from kds_equivalent_static_cs import compute_equivalent_static_cs

G_ACCEL = 9.80665


def _section(text: str, name: str) -> str:
    match = re.search(r"^\*" + name + r"\b.*?(?=^\*[A-Z])", text, re.S | re.M)
    return match.group(0) if match else ""


def _total_nodal_mass_ton(mgt_text: str) -> float:
    section = _section(mgt_text, "NODALMASS")
    total = 0.0
    for line in section.splitlines():
        line = line.strip()
        if not line or line[0] in "*;":
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                total += float(parts[1])
            except ValueError:
                continue
    return total


def _drift_from_condensed_solve(condensed_solve_json: Path | None) -> dict[str, Any] | None:
    if not condensed_solve_json or not condensed_solve_json.is_file():
        return None
    payload = load_json(condensed_solve_json)
    ndtha = payload.get("ndtha_solve") if isinstance(payload.get("ndtha_solve"), dict) else {}
    static = payload.get("static_solve") if isinstance(payload.get("static_solve"), dict) else {}
    drift = float(ndtha.get("max_drift_ratio_pct") or 0.0)
    if drift <= 0.0:
        return None
    return {
        "drift_ratio_pct": drift,
        "base_shear_kn": float(static.get("base_shear_kn") or 0.0),
        "provenance": "condensed_story_ndtha",
        "confidence": "medium",
        "note": "From in-repo condensed story NDTHA (same MGT mesh fingerprint); not MIDAS Gen.",
    }


def extract_midas_gen_same_mesh_result(
    *,
    mgt_path: Path,
    roundtrip_json: Path,
    condensed_solve_json: Path | None = None,
    seismic_coefficient: float | None = None,
    assumed_elastic_drift_pct: float | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not mgt_path.is_file():
        blockers.append("mgt_missing")
    roundtrip = load_json(roundtrip_json) if roundtrip_json.is_file() else {}
    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    mgt_text = mgt_path.read_text(encoding="utf-8", errors="ignore") if mgt_path.is_file() else ""

    mass_ton = _total_nodal_mass_ton(mgt_text)
    seismic_weight_kn = mass_ton * G_ACCEL / 1.0  # mass(ton)*g -> kN (ton*m/s^2 = kN)

    npz = roundtrip_json.with_suffix(".npz")
    height_m = 0.0
    if npz.is_file():
        with np.load(npz, allow_pickle=False) as archive:
            z = np.asarray(archive["node_xyz"], dtype=np.float64)[:, 2]
            height_m = float(np.max(z) - np.min(z))

    kds_cs = compute_equivalent_static_cs(height_m=height_m)
    cs = float(
        seismic_coefficient
        if seismic_coefficient is not None
        else float(os.environ.get("PHASE1_MIDAS_SEISMIC_CS") or kds_cs["cs"])
    )
    base_shear_kn = cs * seismic_weight_kn

    condensed_drift = _drift_from_condensed_solve(condensed_solve_json)
    if condensed_drift:
        drift_pct = float(condensed_drift["drift_ratio_pct"])
        drift_confidence = str(condensed_drift["confidence"])
        drift_provenance = str(condensed_drift["provenance"])
        drift_basis = str(condensed_drift["note"])
    else:
        drift_pct = float(
            assumed_elastic_drift_pct
            if assumed_elastic_drift_pct is not None
            else os.environ.get("PHASE1_MIDAS_ASSUMED_DRIFT_PCT", 0.4)
        )
        drift_confidence = "low"
        drift_provenance = "code_target_estimate"
        drift_basis = "engineering placeholder pending full-mesh/Gen lateral run"
    top_displacement_m = drift_pct / 100.0 * height_m

    if mass_ton <= 0.0:
        blockers.append("nodal_mass_not_found")
    if height_m <= 0.0:
        blockers.append("height_unresolved")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": "model_derived_estimate",
            "mgt_sha256": str(source.get("sha256") or ""),
            "roundtrip_json": str(roundtrip_json),
            "mgt_path": str(mgt_path),
            "midas_model_name": mgt_path.stem,
            "note": (
                "Model-derived same-mesh estimate computed in-repo from MGT nodal mass/geometry. "
                "NOT a licensed MIDAS Gen solver run. base_shear is equivalent-static (Cs*W); "
                "drift/top_displacement are code-target estimates pending a full-mesh lateral solve."
            ),
        },
        "metrics": {
            "drift_ratio_pct": top_displacement_m / max(height_m, 1e-9) * 100.0,
            "base_shear_kN": base_shear_kn,
            "top_displacement_m": top_displacement_m,
        },
        "derivation": {
            "seismic_mass_ton": mass_ton,
            "seismic_weight_kN": seismic_weight_kn,
            "building_height_m": height_m,
            "gravity_dominant_low_rise": height_m < 20.0,
        },
        "assumptions": {
            "seismic_coefficient_cs": cs,
            "cs_basis": kds_cs,
            "assumed_elastic_drift_pct": drift_pct,
            "drift_basis": drift_basis,
        },
        "metric_provenance": {
            "base_shear_kN": "computed_cs_times_weight",
            "seismic_weight_kN": "computed_from_model_nodal_mass",
            "drift_ratio_pct": drift_provenance,
            "top_displacement_m": drift_provenance,
        },
        "confidence": {
            "base_shear_kN": "medium",
            "drift_ratio_pct": drift_confidence,
            "top_displacement_m": drift_confidence,
        },
        "kds_seismic": kds_cs,
        "condensed_story_bridge": condensed_drift,
        "blockers": blockers,
    }
