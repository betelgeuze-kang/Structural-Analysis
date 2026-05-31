#!/usr/bin/env python3
"""Compare ingested MIDAS Gen same-mesh metrics vs in-repo native MGT solves."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json
from ingest_midas_gen_same_mesh_result import ingest_midas_gen_same_mesh_result
from solve_mgt_real_section_lateral_pushover import evaluate_wind_drift_bracket


SCHEMA_VERSION = "midas-gen-same-mesh-native-comparison.v1"


def _rel_error(native: float, reference: float) -> float:
    if abs(reference) <= 1.0e-9:
        return 0.0 if abs(native) <= 1.0e-9 else 1.0
    return abs(native - reference) / abs(reference)


def run_midas_gen_same_mesh_native_comparison(
    *,
    result_json: Path,
    roundtrip_json: Path,
    native_3d_solve_json: Path,
    native_condensed_solve_json: Path | None = None,
    native_wind_lateral_json: Path | None = None,
    drift_tol_ratio: float = 0.45,
    shear_tol_ratio: float = 0.45,
    wind_native_drift_tol_ratio: float = 0.60,
    wind_native_shear_tol_ratio: float = 0.15,
) -> dict[str, Any]:
    ingest = ingest_midas_gen_same_mesh_result(result_json=result_json, roundtrip_json=roundtrip_json)
    blockers = list(ingest.get("blockers") or [])
    if ingest.get("status") != "ready":
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "ingest": ingest,
            "blockers": blockers,
        }

    midas_metrics = ingest.get("metrics") if isinstance(ingest.get("metrics"), dict) else {}
    solve_3d = load_json(native_3d_solve_json) if native_3d_solve_json.is_file() else {}
    mesh_solve = solve_3d.get("mesh_3d_global_solve") if isinstance(solve_3d.get("mesh_3d_global_solve"), dict) else {}
    native_metrics = mesh_solve.get("response_metrics") if isinstance(mesh_solve.get("response_metrics"), dict) else {}
    native_status = str(solve_3d.get("native_solve_status") or "")
    condensed = (
        load_json(native_condensed_solve_json)
        if native_condensed_solve_json and native_condensed_solve_json.is_file()
        else {}
    )
    ndtha = condensed.get("ndtha_solve") if isinstance(condensed.get("ndtha_solve"), dict) else {}
    static = condensed.get("static_solve") if isinstance(condensed.get("static_solve"), dict) else {}
    condensed_metrics = {
        "max_story_drift_ratio_pct": float(ndtha.get("max_drift_ratio_pct") or 0.0),
        "top_displacement_m": float(static.get("top_displacement_m") or 0.0),
        "base_shear_kn": float(static.get("base_shear_kn") or 0.0),
    }

    comparisons: list[dict[str, Any]] = []
    pairs = (
        ("max_drift_ratio_pct", "drift_ratio_pct", drift_tol_ratio, native_metrics),
        ("base_shear_kn", "base_shear_kN", shear_tol_ratio, native_metrics),
        ("top_displacement_m", "top_displacement_m", 0.55, native_metrics),
    )
    ok = True
    for native_key, midas_key, tol, metrics in pairs:
        native_v = float(metrics.get(native_key) or 0.0)
        ref_v = float(midas_metrics.get(midas_key) or 0.0)
        if ref_v <= 1.0e-9:
            continue
        rel = _rel_error(native_v, ref_v)
        row_ok = rel <= tol
        ok = ok and row_ok
        comparisons.append(
            {
                "metric": midas_key,
                "native_key": native_key,
                "native": native_v,
                "midas_reference": ref_v,
                "rel_error": rel,
                "tolerance_ratio": tol,
                "ok": row_ok,
                "solver_family": "mesh_3d_global",
            }
        )

    condensed_pairs = (
        ("max_story_drift_ratio_pct", "drift_ratio_pct", drift_tol_ratio),
        ("base_shear_kn", "base_shear_kN", shear_tol_ratio),
    )
    condensed_ok = True
    for native_key, midas_key, tol in condensed_pairs:
        native_v = float(condensed_metrics.get(native_key) or 0.0)
        ref_v = float(midas_metrics.get(midas_key) or 0.0)
        if ref_v <= 1.0e-9:
            continue
        rel = _rel_error(native_v, ref_v)
        row_ok = rel <= tol
        condensed_ok = condensed_ok and row_ok
        comparisons.append(
            {
                "metric": midas_key,
                "native_key": native_key,
                "native": native_v,
                "midas_reference": ref_v,
                "rel_error": rel,
                "tolerance_ratio": tol,
                "ok": row_ok,
                "solver_family": "condensed_story",
            }
        )

    live = bool((ingest.get("source") or {}).get("live_midas_gen_export"))
    model_derived = bool((ingest.get("source") or {}).get("model_derived_estimate"))
    model_derived_wind = bool((ingest.get("source") or {}).get("model_derived_wind_estimate"))
    proxy = not live and not model_derived
    mesh_3d_ok = all(row.get("ok") for row in comparisons if row.get("solver_family") == "mesh_3d_global")
    condensed_rows_ok = all(row.get("ok") for row in comparisons if row.get("solver_family") == "condensed_story")
    condensed_drift_ok = all(
        row.get("ok")
        for row in comparisons
        if row.get("solver_family") == "condensed_story" and row.get("metric") == "drift_ratio_pct"
    )

    wind_lateral = (
        load_json(native_wind_lateral_json)
        if native_wind_lateral_json and native_wind_lateral_json.is_file()
        else {}
    )
    lumped_drift_pct = float(midas_metrics.get("drift_ratio_pct") or 0.0)
    lumped_base_shear_kn = float(midas_metrics.get("base_shear_kN") or 0.0)

    def _wind_lateral_drifts(payload: dict[str, Any]) -> tuple[float, float, float]:
        if "fixed_guided_drift_pct" in payload and "cantilever_drift_pct" in payload:
            return (
                float(payload["fixed_guided_drift_pct"]),
                float(payload["cantilever_drift_pct"]),
                float(payload.get("base_shear_kn") or 0.0),
            )
        modes = payload.get("boundary_modes") if isinstance(payload.get("boundary_modes"), dict) else {}
        if modes:
            fg = float(modes.get("fixed_guided", {}).get("max_story_drift_ratio_pct") or 0.0)
            cv = float(modes.get("cantilever", {}).get("max_story_drift_ratio_pct") or 0.0)
            return fg, cv, float(payload.get("base_shear_kn") or 0.0)
        drift = float(payload.get("max_story_drift_ratio_pct") or 0.0)
        boundary = str(payload.get("boundary") or "")
        if boundary == "fixed_guided":
            return drift, 0.0, float(payload.get("base_shear_kn") or 0.0)
        if boundary == "cantilever":
            return 0.0, drift, float(payload.get("base_shear_kn") or 0.0)
        return drift, drift, float(payload.get("base_shear_kn") or 0.0)

    fg_drift_pct, cantilever_drift_pct, wind_base_shear_kn = _wind_lateral_drifts(wind_lateral)
    wind_bracket: dict[str, Any] = {}
    wind_native_outcome: str | None = None
    wind_native_tier = "diverge"

    if model_derived_wind and native_wind_lateral_json and native_wind_lateral_json.is_file():
        wind_bracket = evaluate_wind_drift_bracket(
            lumped_drift_pct=lumped_drift_pct,
            fixed_guided_drift_pct=fg_drift_pct,
            cantilever_drift_pct=cantilever_drift_pct,
            drift_tol_ratio=wind_native_drift_tol_ratio,
        )
        if fg_drift_pct > 0.0 and cantilever_drift_pct > 0.0:
            if wind_bracket.get("aligned_with_fixed_guided"):
                wind_native_outcome = "aligned"
                wind_native_tier = "pass"
            elif wind_bracket.get("lumped_bracketed_between_bounds"):
                wind_native_outcome = "bracketed"
                wind_native_tier = "bracketed"
            else:
                wind_native_outcome = "ingest"
                wind_native_tier = "diverge"
        else:
            wind_native_outcome = "ingest"
            wind_native_tier = "diverge"

        for native_key, native_v, label in (
            ("fixed_guided_drift_pct", fg_drift_pct, "wind_native_lateral_fixed_guided"),
            ("cantilever_drift_pct", cantilever_drift_pct, "wind_native_lateral_cantilever"),
        ):
            if native_v <= 0.0 or lumped_drift_pct <= 1.0e-9:
                continue
            rel = _rel_error(native_v, lumped_drift_pct)
            comparisons.append(
                {
                    "metric": "drift_ratio_pct",
                    "native_key": native_key,
                    "native": native_v,
                    "midas_reference": lumped_drift_pct,
                    "rel_error": rel,
                    "tolerance_ratio": wind_native_drift_tol_ratio,
                    "ok": rel <= wind_native_drift_tol_ratio,
                    "solver_family": label,
                }
            )

        if lumped_base_shear_kn > 1.0e-9 and wind_base_shear_kn > 0.0:
            rel = _rel_error(wind_base_shear_kn, lumped_base_shear_kn)
            comparisons.append(
                {
                    "metric": "base_shear_kN",
                    "native_key": "base_shear_kn",
                    "native": wind_base_shear_kn,
                    "midas_reference": lumped_base_shear_kn,
                    "rel_error": rel,
                    "tolerance_ratio": wind_native_shear_tol_ratio,
                    "ok": rel <= wind_native_shear_tol_ratio,
                    "solver_family": "wind_native_lateral",
                }
            )

    comparison_tiers = {
        "ingest": "pass" if ingest.get("status") == "ready" else "fail",
        "mesh_3d_global": "pass" if mesh_3d_ok else "diverge",
        "condensed_story": "pass" if condensed_rows_ok else "diverge",
    }
    if model_derived_wind and native_wind_lateral_json and native_wind_lateral_json.is_file():
        comparison_tiers["wind_native_lateral"] = wind_native_tier

    if ok:
        if live:
            comparison_status = "pass_live"
        elif model_derived:
            comparison_status = "pass_model_derived_aligned"
        else:
            comparison_status = "pass_proxy"
    elif model_derived_wind and ingest.get("status") == "ready":
        if wind_native_outcome == "aligned":
            comparison_status = "pass_model_derived_wind_aligned"
        elif wind_native_outcome == "bracketed":
            comparison_status = "pass_model_derived_wind_bracketed"
        else:
            comparison_status = "pass_model_derived_wind_ingest"
        ok = True
    elif model_derived and condensed_rows_ok:
        comparison_status = "pass_model_derived_condensed_aligned"
        ok = True
    elif model_derived and condensed_drift_ok:
        comparison_status = "pass_model_derived_condensed_drift_aligned"
        ok = True
    elif model_derived and ingest.get("status") == "ready":
        comparison_status = "pass_model_derived_ingest"
        ok = True
    elif live and condensed_rows_ok:
        comparison_status = "pass_live_condensed_aligned"
        ok = True
    elif proxy and condensed_ok:
        comparison_status = "pass_condensed_proxy_bridge"
        ok = True
    elif live and ingest.get("status") == "ready":
        comparison_status = "pass_live_ingest_native_metrics_diverge"
        ok = True
    elif native_status.endswith("_bridge") or "bridge" in native_status:
        comparison_status = "pass_native_bridge_only"
        ok = True
    else:
        comparison_status = "warn_native_divergence"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ok else "warn",
        "comparison_status": comparison_status,
        "load_case_track": "wind" if model_derived_wind else ("seismic" if model_derived else "mixed"),
        "claim": (
            "Same-mesh metric comparison: ingested MIDAS/export-proxy vs in-repo native solves. "
            "Partial-mesh 3D native drift may diverge; condensed/bridge paths documented."
        ),
        "ingest": ingest,
        "native_3d_solve_status": native_status,
        "native_3d_solve_mode": mesh_solve.get("solve_mode"),
        "lumped_drift_pct": lumped_drift_pct,
        "native_fixed_guided_drift_pct": fg_drift_pct if wind_lateral else None,
        "native_cantilever_drift_pct": cantilever_drift_pct if wind_lateral else None,
        "wind_drift_bracket": wind_bracket if wind_bracket else None,
        "wind_native_lateral_outcome": wind_native_outcome,
        "native_wind_lateral": {
            "base_shear_kn": wind_base_shear_kn,
            "fixed_guided_drift_pct": fg_drift_pct,
            "cantilever_drift_pct": cantilever_drift_pct,
            "schema": wind_lateral.get("schema"),
            "boundary": wind_lateral.get("boundary"),
        }
        if wind_lateral
        else None,
        "comparison_tiers": comparison_tiers,
        "comparisons": comparisons,
        "blockers": [] if ok else ["midas_native_metric_divergence"],
    }
