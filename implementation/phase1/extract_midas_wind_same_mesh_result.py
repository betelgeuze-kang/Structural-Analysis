#!/usr/bin/env python3
"""Wind-load same-mesh KPIs from the optimized MGT model (matches the model's WIND load cases).

This model defines DEAD/LIVE/WIND load cases only (no seismic), so the wind track is the
design-consistent comparison. We assemble a story profile from the MGT NPZ condensed model,
scale story mass to the real total nodal mass, and run the in-repo wind workflow under
documented KDS 41 12 00 site params. Base shear and drift are model-derived (not MIDAS Gen).
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from assemble_mgt_mesh_condensed_story import assemble_story_model_from_mgt_npz
from design_optimization.io import load_json
from ingest_midas_gen_same_mesh_result import SCHEMA_VERSION
from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_material_properties,
    parse_mgt_section_properties,
)
from solve_mgt_beam_mesh_3d_global import _beam_props
from wind_workflow import run_wind_workflow

STEEL_E_PA = 210000.0e6
LATERAL_MIN_HEIGHT_FRACTION = 0.5

G_ACCEL = 9.80665
DEFAULT_WIND_PARAMS_PATH = (
    Path(__file__).resolve().parent / "open_data" / "kds" / "wind_design_params.json"
)

ACCIDENTAL_TORSION_BASIS = (
    "simplified rigid-diaphragm uniform-stiffness accidental torsion "
    "(ASCE-style ±5% eccentricity)"
)

DEFAULT_ANGLE_SWEEP_DEG: tuple[float, ...] = (0.0, 22.5, 45.0, 67.5, 90.0, 112.5, 135.0, 157.5)


def _angle_sweep_envelope(
    base_shear_x_kN: float,
    base_shear_y_kN: float,
    drift_pct: float,
    *,
    angles_deg: tuple[float, ...] = DEFAULT_ANGLE_SWEEP_DEG,
) -> list[dict[str, Any]]:
    """Project X/Y wind base shears onto a discrete set of attack angles.

    Convention: angle 0 deg = full +X load; angle 90 deg = full +Y load.
    Linear superposition is used for the strength case (V(θ) = Vx cosθ + Vy sinθ),
    which is the same assumption the in-repo wind workflow uses for the
    along-X and along-Y envelopes. Drift scales with the same projection.
    """
    out: list[dict[str, Any]] = []
    vx = float(base_shear_x_kN)
    vy = float(base_shear_y_kN)
    base_drift = float(drift_pct)
    for angle in angles_deg:
        theta = math.radians(float(angle))
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        v_theta = vx * cos_t + vy * sin_t
        drift_theta = base_drift * math.sqrt(cos_t * cos_t + sin_t * sin_t)
        out.append(
            {
                "angle_deg": float(angle),
                "base_shear_theta_kN": float(v_theta),
                "drift_theta_pct": float(drift_theta),
                "cos_theta": float(cos_t),
                "sin_theta": float(sin_t),
            }
        )
    return out


def _accidental_torsion_amplification(
    plan_b_m: float,
    plan_d_m: float,
    *,
    ecc_fraction: float = 0.05,
) -> dict[str, float]:
    """Rigid-diaphragm uniform-stiffness accidental torsion corner drift amplification.

    For load along X, eccentricity uses perpendicular plan width B; corner lever arm D/2.
    amp_y swaps B and D roles.
    """
    b = max(float(plan_b_m), 1e-9)
    d = max(float(plan_d_m), 1e-9)

    def _amp(perp_m: float, parallel_m: float) -> float:
        bp = max(perp_m, 1e-9)
        dp = max(parallel_m, 1e-9)
        return 1.0 + 6.0 * ecc_fraction * bp * (dp / 2.0) / (bp**2 + dp**2)

    amp_x = _amp(b, d)
    amp_y = _amp(d, b)
    return {
        "amp_x": amp_x,
        "amp_y": amp_y,
        "governing_amplification": max(amp_x, amp_y),
    }


def _total_nodal_mass_ton(mgt_text: str) -> float:
    import re

    match = re.search(r"^\*NODALMASS\b.*?(?=^\*[A-Z])", mgt_text, re.S | re.M)
    if not match:
        return 0.0
    total = 0.0
    for line in match.group(0).splitlines():
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


def _mechanics_lateral_stiffness_kNpm(
    npz_path: Path,
    *,
    section_props: dict[int, dict[str, Any]] | None = None,
    material_props: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mechanics-based sway stiffness from full-height column lines: K = sum 12*E*I/H^3.

    Near-vertical segments are grouped by plan (x,y) rounded to 0.1 m. Lines shorter than
    half the building height are skipped (mesh stubs / secondary members). When section and
    material tables are supplied, uses parsed min(Iy,Iz) and E; otherwise _beam_props fallback.
    """
    from collections import defaultdict

    sections = section_props or {}
    materials = material_props or {}

    with np.load(npz_path, allow_pickle=False) as archive:
        xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int64)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int64)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int64)

    building_height_m = float(xyz[:, 2].max() - xyz[:, 2].min())
    min_column_height_m = LATERAL_MIN_HEIGHT_FRACTION * building_height_m

    beam_idx = np.where(elem_type_code == 1)[0]
    columns: dict[
        tuple[float, float],
        list[tuple[float, float, int, int]],
    ] = defaultdict(list)
    n_cols = edge_index.shape[1]
    for idx in beam_idx:
        if idx >= n_cols:
            continue
        i = int(edge_index[0, idx])
        j = int(edge_index[1, idx])
        if i < 0 or j < 0 or i >= xyz.shape[0] or j >= xyz.shape[0]:
            continue
        pi = xyz[i]
        pj = xyz[j]
        dz = abs(pj[2] - pi[2])
        plan = float(np.hypot(pj[0] - pi[0], pj[1] - pi[1]))
        length = float(np.hypot(plan, dz))
        if length < 0.2 or dz / max(length, 1e-9) <= 0.7:
            continue
        key = (
            round((pi[0] + pj[0]) / 2.0, 1),
            round((pi[1] + pj[1]) / 2.0, 1),
        )
        columns[key].append(
            (
                min(pi[2], pj[2]),
                max(pj[2], pi[2]),
                int(elem_section_id[idx]),
                int(elem_material_id[idx]),
            )
        )

    k_total = 0.0
    heights: list[float] = []
    real_column_lines = 0
    column_line_count = 0
    for segments in columns.values():
        z_min = min(s[0] for s in segments)
        z_max = max(s[1] for s in segments)
        height_raw = z_max - z_min
        if height_raw < min_column_height_m:
            continue
        height = max(height_raw, 0.5)
        column_line_count += 1
        med_section = int(np.median([s[2] for s in segments]))
        med_material = int(np.median([s[3] for s in segments]))
        sec = sections.get(med_section)
        mat = materials.get(med_material)
        if sec is not None and mat is not None:
            iy = float(min(sec["Iy_m4"], sec["Iz_m4"]))
            e_pa = float(mat["E_kN_per_m2"]) * 1000.0
            k_total += 12.0 * e_pa * iy / height**3
            real_column_lines += 1
        else:
            props = _beam_props(length_m=height, section_id=med_section)
            k_total += 12.0 * STEEL_E_PA * props.iy_m4 / height**3
        heights.append(height)

    real_fraction = (
        float(real_column_lines) / float(column_line_count) if column_line_count else 0.0
    )

    return {
        "lateral_k_total_kNpm": k_total / 1000.0,
        "column_line_count": column_line_count,
        "full_height_column_line_count": column_line_count,
        "lateral_building_height_m": building_height_m,
        "lateral_min_height_fraction": LATERAL_MIN_HEIGHT_FRACTION,
        "lateral_min_column_height_m": min_column_height_m,
        "avg_column_height_m": float(np.mean(heights)) if heights else 0.0,
        "real_section_column_line_fraction": real_fraction,
        "real_section_column_line_count": real_column_lines,
    }


def _load_wind_params(path: Path | None) -> dict[str, Any]:
    params_path = path or Path(
        str(os.environ.get("PHASE1_KDS_WIND_PARAMS_JSON") or DEFAULT_WIND_PARAMS_PATH)
    )
    if params_path.is_file():
        payload = load_json(params_path)
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["_path"] = str(params_path)
            return payload
    return {"_path": str(params_path)}


def extract_midas_wind_same_mesh_result(
    *,
    mgt_path: Path,
    roundtrip_json: Path,
    wind_params_json: Path | None = None,
    max_wind_stories: int = 12,
    basic_wind_speed_mps: float | None = None,
    exposure: str | None = None,
    angle_sweep_deg: tuple[float, ...] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    roundtrip = load_json(roundtrip_json) if roundtrip_json.is_file() else {}
    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    npz = roundtrip_json.with_suffix(".npz")
    if not npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "blockers": ["roundtrip_npz_missing"],
        }

    with np.load(npz, allow_pickle=False) as archive:
        xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
    plan_dim_x_m = float(xyz[:, 0].max() - xyz[:, 0].min())
    plan_dim_y_m = float(xyz[:, 1].max() - xyz[:, 1].min())
    height_m = float(xyz[:, 2].max() - xyz[:, 2].min())

    mgt_text = mgt_path.read_text(encoding="utf-8", errors="ignore") if mgt_path.is_file() else ""
    total_mass_ton = _total_nodal_mass_ton(mgt_text)
    if total_mass_ton <= 0.0:
        blockers.append("nodal_mass_not_found")

    story = assemble_story_model_from_mgt_npz(roundtrip_npz=npz)
    micro_h = np.asarray(story["story_h_m"], dtype=np.float64)
    micro_k = np.asarray(story["story_k_n_per_m"], dtype=np.float64) / 1000.0  # kN/m
    micro_m = np.asarray(story["story_mass_kg"], dtype=np.float64)
    n_micro = micro_h.size

    # Aggregate fine mesh levels into a coarse story profile for the wind workflow.
    n_stories = max(2, min(int(max_wind_stories), n_micro))
    bins = np.array_split(np.arange(n_micro), n_stories)
    heights: list[float] = []
    stiffness: list[float] = []
    mass_weights: list[float] = []
    for idx_group in bins:
        if idx_group.size == 0:
            continue
        heights.append(float(np.sum(micro_h[idx_group])))
        # series stiffness of stacked micro-springs
        inv = np.sum(1.0 / np.clip(micro_k[idx_group], 1e-9, None))
        stiffness.append(float(1.0 / inv) if inv > 0 else float(np.mean(micro_k[idx_group])))
        mass_weights.append(float(np.sum(micro_m[idx_group])))

    mass_weights_arr = np.asarray(mass_weights, dtype=np.float64)
    mass_share = mass_weights_arr / max(float(np.sum(mass_weights_arr)), 1e-9)
    story_masses_t = (mass_share * max(total_mass_ton, 1.0)).tolist()

    wind_params = _load_wind_params(wind_params_json)
    # CLI/explicit overrides win over the JSON params for real-site runs.
    resolved_wind_speed = (
        float(basic_wind_speed_mps)
        if basic_wind_speed_mps is not None
        else float(wind_params.get("basic_wind_speed_mps", 30.0))
    )
    resolved_exposure = str(exposure if exposure else wind_params.get("exposure", "B")).upper()
    # Empirical period: low-rise rigid -> ~0.05*H; floor to a small value.
    period_s = max(0.1, 0.05 * height_m)
    payload = {
        "site": {
            "basic_wind_speed_mps": resolved_wind_speed,
            "exposure": resolved_exposure,
            "topographic_factor": float(wind_params.get("topographic_factor", 1.0)),
            "directionality_factor": float(wind_params.get("directionality_factor", 0.85)),
            "importance_factor": float(wind_params.get("importance_factor", 1.0)),
            "gust_factor": float(wind_params.get("gust_factor", 0.85)),
        },
        "building": {
            "name": mgt_path.stem,
            "plan_dim_x_m": max(plan_dim_x_m, 1.0),
            "plan_dim_y_m": max(plan_dim_y_m, 1.0),
            "story_heights_m": heights,
            "story_masses_t": story_masses_t,
            "story_stiffness_kNpm": stiffness,
            "fundamental_period_s": period_s,
            "damping_ratio": float(wind_params.get("damping_ratio", 0.02)),
            "force_coefficient": float(wind_params.get("force_coefficient", 1.3)),
            "across_wind_factor": float(wind_params.get("across_wind_factor", 1.2)),
        },
    }

    report = run_wind_workflow(payload)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    drift_summary = (
        report.get("drift_summary") if isinstance(report.get("drift_summary"), dict) else {}
    )
    base_shear_x = float(summary.get("base_shear_strength_x_kN") or 0.0)
    base_shear_y = float(summary.get("base_shear_strength_y_kN") or 0.0)
    governing_base_shear = max(base_shear_x, base_shear_y)
    governing_direction = "X" if base_shear_x >= base_shear_y else "Y"

    # Drift uses a mechanics-based sway stiffness from the actual column lines (sum 12*E*I/H^3),
    # consistent with the in-repo 3D beam solver property model. The condensed story_k is a synthetic
    # vertical-chain spring (not lateral) and is only a last-resort fallback.
    parsed_props = (
        load_mgt_section_material_properties(mgt_path)
        if mgt_path.is_file()
        else {"sections": {}, "materials": {}}
    )
    section_props = parsed_props.get("sections") if isinstance(parsed_props.get("sections"), dict) else {}
    material_props = (
        parsed_props.get("materials") if isinstance(parsed_props.get("materials"), dict) else {}
    )
    if not section_props and mgt_text:
        section_props = parse_mgt_section_properties(mgt_text)
    if not material_props and mgt_text:
        material_props = parse_mgt_material_properties(mgt_text)

    lateral = _mechanics_lateral_stiffness_kNpm(
        npz,
        section_props=section_props,
        material_props=material_props,
    )
    lateral_k_total_kNpm = float(lateral.get("lateral_k_total_kNpm") or 0.0)
    real_fraction = float(lateral.get("real_section_column_line_fraction") or 0.0)
    if real_fraction >= 0.8 and lateral.get("column_line_count", 0) >= 4:
        drift_basis = "mechanics_real_section"
        drift_confidence = "high"
    else:
        drift_basis = "mechanics"
        drift_confidence = "medium"
    if lateral_k_total_kNpm <= 0.0 or lateral.get("column_line_count", 0) < 4:
        lateral_k_total_kNpm = float(np.sum(micro_k))
        drift_basis = "condensed_parallel_proxy"
        drift_confidence = "low"
    top_disp_m = governing_base_shear / max(lateral_k_total_kNpm, 1e-9)
    drift_pct = (top_disp_m / max(height_m, 1e-9)) * 100.0
    if drift_pct > 100.0:
        blockers.append("drift_estimate_implausible")

    plan_b_m = max(plan_dim_y_m, 1.0)
    plan_d_m = max(plan_dim_x_m, 1.0)
    torsion = _accidental_torsion_amplification(plan_b_m, plan_d_m)
    corner_drift_pct = drift_pct * torsion["governing_amplification"]

    wind_directional: dict[str, Any] = {
        "base_shear_x_kN": base_shear_x,
        "base_shear_y_kN": base_shear_y,
        "governing_direction": governing_direction,
        "crosswind_bias_ratio": float(
            summary.get("occupant_comfort_crosswind_bias_ratio") or 0.0
        ),
        "serviceability_status": str(summary.get("serviceability_status") or ""),
        "occupant_comfort_class": str(summary.get("occupant_comfort_class") or ""),
        "top_peak_acceleration_mg": float(summary.get("top_peak_acceleration_mg") or 0.0),
        "top_rms_acceleration_mg": float(summary.get("top_rms_acceleration_mg") or 0.0),
        "max_story_drift_ratio_service": float(
            summary.get("max_story_drift_ratio_service") or 0.0
        ),
        "strength_governing_case_id": str(
            drift_summary.get("strength_governing_case_id") or ""
        ),
        "strength_governing_story": int(drift_summary.get("strength_governing_story") or 0),
        "accidental_torsion": {
            "ecc_fraction": 0.05,
            "amp_x": torsion["amp_x"],
            "amp_y": torsion["amp_y"],
            "governing_amplification": torsion["governing_amplification"],
            "basis": ACCIDENTAL_TORSION_BASIS,
        },
        "angle_sweep": _angle_sweep_envelope(
            base_shear_x,
            base_shear_y,
            drift_pct,
            angles_deg=tuple(angle_sweep_deg) if angle_sweep_deg else DEFAULT_ANGLE_SWEEP_DEG,
        ),
        "angle_sweep_basis": (
            "Linear projection of X/Y wind-workflow base shear onto each attack angle "
            "(V(θ)=Vx cosθ + Vy sinθ). Drift scales with the same projection. "
            "Same along-X/along-Y convention the in-repo wind workflow uses."
        ),
    }
    if wind_directional["angle_sweep"]:
        envelope_peak = max(wind_directional["angle_sweep"], key=lambda r: abs(float(r["base_shear_theta_kN"])))
        wind_directional["governing_angle_deg"] = float(envelope_peak.get("angle_deg") or 0.0)
        wind_directional["envelope_max_base_shear_kN"] = float(envelope_peak.get("base_shear_theta_kN") or 0.0)
        wind_directional["envelope_max_drift_pct"] = float(envelope_peak.get("drift_theta_pct") or 0.0)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": "model_derived_wind_estimate",
            "mgt_sha256": str(source.get("sha256") or ""),
            "roundtrip_json": str(roundtrip_json),
            "mgt_path": str(mgt_path),
            "midas_model_name": mgt_path.stem,
            "load_case": "WIND (model-defined)",
            "note": (
                "Wind-load same-mesh estimate from in-repo wind workflow (KDS 41 12 00 site params). "
                "Matches the model's WIND load cases (this model has no seismic case). NOT a MIDAS Gen run."
            ),
        },
        "metrics": {
            "drift_ratio_pct": drift_pct,
            "corner_drift_ratio_pct": corner_drift_pct,
            "base_shear_kN": governing_base_shear,
            "top_displacement_m": top_disp_m,
        },
        "wind_directional": wind_directional,
        "derivation": {
            "plan_dim_x_m": plan_dim_x_m,
            "plan_dim_y_m": plan_dim_y_m,
            "building_height_m": height_m,
            "total_nodal_mass_ton": total_mass_ton,
            "wind_story_count": len(heights),
            "base_shear_x_kN": base_shear_x,
            "base_shear_y_kN": base_shear_y,
            "fundamental_period_s": period_s,
        },
        "assumptions": {
            "wind_params": {k: v for k, v in wind_params.items() if k != "_path"},
            "wind_params_source": wind_params.get("_path"),
            "resolved_basic_wind_speed_mps": resolved_wind_speed,
            "resolved_exposure": resolved_exposure,
            "period_basis": "empirical 0.05*H low-rise rigid estimate",
            "lateral_stiffness_kNpm": lateral_k_total_kNpm,
            "lateral_stiffness_basis": drift_basis,
            "lateral_column_line_count": lateral.get("column_line_count", 0),
            "lateral_full_height_column_count": lateral.get("full_height_column_line_count", 0),
            "lateral_building_height_m": lateral.get("lateral_building_height_m", 0.0),
            "lateral_min_height_fraction": lateral.get(
                "lateral_min_height_fraction", LATERAL_MIN_HEIGHT_FRACTION
            ),
            "lateral_avg_column_height_m": lateral.get("avg_column_height_m", 0.0),
            "real_section_column_line_fraction": real_fraction,
            "real_section_column_line_count": lateral.get("real_section_column_line_count", 0),
            "drift_basis": (
                "mechanics-based sway stiffness K=sum(12*E*I/H^3) over full-height column lines "
                "(H >= 0.5*building_height; MGT-parsed min(Iy,Iz) and material E)"
                if drift_basis == "mechanics_real_section"
                else (
                    "mechanics-based sway stiffness K=sum(12*E*I/H^3) over full-height column lines "
                    "(representative section I, steel-representative E)"
                    if drift_basis == "mechanics"
                    else "fallback: parallel sum of condensed vertical-chain springs (no column lines found)"
                )
            ),
        },
        "metric_provenance": {
            "base_shear_kN": "in_repo_wind_workflow_strength",
            "drift_ratio_pct": f"lateral_stiffness_{drift_basis}",
            "corner_drift_ratio_pct": "translational_drift_x_accidental_torsion_amplification",
            "top_displacement_m": f"lateral_stiffness_{drift_basis}",
        },
        "confidence": {
            "base_shear_kN": "medium",
            "drift_ratio_pct": drift_confidence,
            "corner_drift_ratio_pct": drift_confidence,
            "top_displacement_m": drift_confidence,
        },
        "blockers": blockers,
    }
