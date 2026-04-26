#!/usr/bin/env python3
"""Nonlinear pushover collapse stress gate for Rust frame solver.

Purpose:
- force yielding/plastic hinge activation (plastic_story_count > 0)
- verify Newton convergence under progressively amplified lateral load
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics

import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile
from section_family_library import evaluate_story_section_profile
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    build_story_load_profile,
    solve_nonlinear_frame,
)
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "nonlinear pushover stress passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CASES": "benchmark cases missing/invalid",
    "ERR_ENGINE_FAIL": "rust nonlinear engine diverged under pushover stress",
    "ERR_PLASTICITY_NOT_TRIGGERED": "plastic hinges were not triggered in one or more cases",
    "ERR_COLLAPSE_PATH_FAIL": "collapse path monotonicity or severity checks failed",
}


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "target_split",
        "min_case_count",
        "max_case_count",
        "load_factors",
        "yield_drift_scale",
        "min_plastic_story_count",
        "min_drift_amplification",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "load_factors": {"type": "string", "minLength": 3},
        "yield_drift_scale": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "min_plastic_story_count": {"type": "integer", "minimum": 1},
        "min_drift_amplification": {"type": "number", "exclusiveMinimum": 1.0},
        "hardening_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pdelta_factor": {"type": "number", "minimum": 0.0},
        "tolerance": {"type": "number", "exclusiveMinimum": 0.0},
        "max_iter": {"type": "integer", "minimum": 1},
        "material_model": {"type": "string", "enum": ["steel_elastic_plastic", "rc_composite"]},
        "rc_cracking_strain": {"type": "number", "exclusiveMinimum": 0.0},
        "rc_creep_rate_per_hour": {"type": "number", "minimum": 0.0},
        "rc_bond_slip_ratio_ref": {"type": "number", "exclusiveMinimum": 0.0},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_levels(text: str) -> list[float]:
    vals: list[float] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        v = float(tok)
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError("load factor must be finite and > 0")
        vals.append(float(v))
    vals = sorted(set(vals))
    if len(vals) < 2:
        raise ValueError("at least two load factors are required")
    return vals


def _story_count_for_topology(topology: str) -> int:
    t = str(topology).strip().lower()
    if t == "outrigger":
        return 24
    if t == "wall-frame":
        return 20
    if t == "truss":
        return 16
    if t == "rahmen":
        return 12
    return 14


def _build_story_stiffness_from_drift(
    *,
    floor_load_n: np.ndarray,
    story_h_m: np.ndarray,
    drift_ratio_hf: float,
) -> np.ndarray:
    n = int(story_h_m.shape[0])
    s = np.linspace(1.0, 1.25, num=n, dtype=np.float64)
    shear = np.cumsum(np.flip(floor_load_n))
    shear = np.flip(shear)
    drift_ratio_target = max(1e-6, float(drift_ratio_hf))
    drift_denom = np.maximum(story_h_m * s, 1e-9)
    base = float(np.max(shear / drift_denom) / drift_ratio_target)
    return np.maximum(1e3, base) * s


def _drift_ratio_pct(u_story: np.ndarray, story_h_m: np.ndarray) -> float:
    if u_story.size == 0:
        return 0.0
    du = np.diff(np.concatenate([[0.0], u_story]))
    return 100.0 * float(np.max(np.abs(du / np.maximum(story_h_m, 1e-9))))


def _validate_metric_source(cases: list[dict], accepted: set[str]) -> tuple[bool, list[str]]:
    bad: list[str] = []
    for i, c in enumerate(cases):
        src = str(c.get("metric_source", "")).strip()
        if src not in accepted:
            bad.append(str(c.get("case_id", f"case-{i}")))
    return len(bad) == 0, bad


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="nonlinear_pushover_stress",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase3.run_nonlinear_pushover_stress")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--min-case-count", type=int, default=3)
    p.add_argument("--max-case-count", type=int, default=6)
    p.add_argument("--load-factors", default="1.0,1.25,1.5,2.0,3.0")
    p.add_argument("--yield-drift-scale", type=float, default=0.45)
    p.add_argument("--min-plastic-story-count", type=int, default=1)
    p.add_argument("--min-drift-amplification", type=float, default=1.8)
    p.add_argument("--hardening-ratio", type=float, default=0.2)
    p.add_argument("--pdelta-factor", type=float, default=0.0)
    p.add_argument("--tolerance", type=float, default=1e-7)
    p.add_argument("--max-iter", type=int, default=120)
    p.add_argument("--material-model", choices=["steel_elastic_plastic", "rc_composite"], default="rc_composite")
    p.add_argument("--rc-cracking-strain", type=float, default=2.2e-4)
    p.add_argument("--rc-creep-rate-per-hour", type=float, default=0.008)
    p.add_argument("--rc-bond-slip-ratio-ref", type=float, default=0.003)
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    p.add_argument("--out", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "target_split": str(args.target_split),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "load_factors": str(args.load_factors),
        "yield_drift_scale": float(args.yield_drift_scale),
        "min_plastic_story_count": int(args.min_plastic_story_count),
        "min_drift_amplification": float(args.min_drift_amplification),
        "hardening_ratio": float(args.hardening_ratio),
        "pdelta_factor": float(args.pdelta_factor),
        "tolerance": float(args.tolerance),
        "max_iter": int(args.max_iter),
        "material_model": str(args.material_model),
        "rc_cracking_strain": float(args.rc_cracking_strain),
        "rc_creep_rate_per_hour": float(args.rc_creep_rate_per_hour),
        "rc_bond_slip_ratio_ref": float(args.rc_bond_slip_ratio_ref),
        "accepted_metric_sources": str(args.accepted_metric_sources),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_nonlinear_pushover_stress")
        log_event(logger, 20, "pushover.start", inputs=input_payload)
        factors = _parse_levels(args.load_factors)

        payload = _load_json(Path(args.cases))
        cases = payload.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError("cases[] missing")
        rows = [c for c in cases if isinstance(c, dict)]
        if str(args.target_split) != "all":
            rows = [c for c in rows if str(c.get("split", "")) == str(args.target_split)]
        rows = rows[: int(args.max_case_count)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"selected cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        accepted_sources = {x.strip() for x in str(args.accepted_metric_sources).split(",") if x.strip()}
        metric_source_ok, metric_source_bad = _validate_metric_source(rows, accepted_sources)

        cfg = RustNonlinearFrameConfig(
            tolerance=float(args.tolerance),
            max_iter=int(args.max_iter),
            hardening_ratio=float(args.hardening_ratio),
            pdelta_factor=float(args.pdelta_factor),
        )

        case_rows: list[dict] = []
        converged_all = True
        plastic_all = True
        collapse_path_all = True
        peak_plastic: list[int] = []
        first_yield_factors: list[float] = []
        drift_amplifications: list[float] = []
        material_effect_rows: list[dict] = []
        material_all_ok = True

        for c in rows:
            case_id = str(c.get("case_id", "unknown"))
            topology = str(c.get("topology_type", "rahmen"))
            material_type = str(c.get("material_type", "steel")).strip().lower()
            story_count = _story_count_for_topology(topology)
            story_h = np.full(story_count, 3.2, dtype=np.float64)

            metrics = c.get("metrics") if isinstance(c.get("metrics"), dict) else {}
            drift_hf_pct = float(((metrics.get("drift_ratio_pct") or {}).get("hf", 0.0)))
            base_hf_kn = float(((metrics.get("base_shear_kN") or {}).get("hf", 0.0)))
            load_scale = float(c.get("load_scale", 1.0))

            drift_hf = max(1e-6, drift_hf_pct / 100.0)
            base_hf_n = max(1.0, base_hf_kn * 1000.0)
            floor_load_base = build_story_load_profile(story_count, base_hf_n, mode="triangular")
            k_story = _build_story_stiffness_from_drift(
                floor_load_n=floor_load_base,
                story_h_m=story_h,
                drift_ratio_hf=drift_hf,
            )
            section_profile = evaluate_story_section_profile(
                topology=topology,
                material_type=material_type,
                story_h_m=story_h,
                drift_ratio_profile=np.linspace(drift_hf * 1.05, drift_hf * 0.95, num=story_count, dtype=np.float64),
                load_scale=load_scale,
            )
            k_story = k_story * np.asarray(section_profile["story_stiffness_scale"], dtype=np.float64)

            yield_story = np.full(
                story_count,
                max(1e-5, drift_hf * float(np.mean(story_h)) * float(args.yield_drift_scale)),
                dtype=np.float64,
            )
            yield_story = yield_story * np.asarray(section_profile["story_yield_scale"], dtype=np.float64)
            axial_story = (4.2e6 * float(load_scale)) * np.linspace(1.25, 0.85, num=story_count, dtype=np.float64)
            mass_story = (2.1e5 * float(load_scale)) * np.linspace(1.25, 0.85, num=story_count, dtype=np.float64)
            use_rc = bool(str(args.material_model) == "rc_composite" or material_type in {"rc", "composite", "rc_composite"})
            rc_cfg = RCCompositeMaterialConfig(
                cracking_strain=float(args.rc_cracking_strain),
                creep_rate_per_hour=float(args.rc_creep_rate_per_hour),
                bond_slip_ratio_ref=float(args.rc_bond_slip_ratio_ref),
            )
            material_indices: dict[str, float] = {
                "cracking_index_mean": 0.0,
                "creep_index_mean": 0.0,
                "bond_slip_index_mean": 0.0,
            }

            runs: list[dict] = []
            drift_series: list[float] = []
            plastic_series: list[int] = []
            first_yield: float | None = None
            case_converged = True
            for lf_idx, lf in enumerate(factors):
                floor_load = floor_load_base * float(lf)
                k_eff = k_story
                y_eff = yield_story
                if use_rc:
                    rc_step = apply_rc_composite_profile(
                        story_k_n_per_m=k_story,
                        story_yield_drift_m=yield_story,
                        story_mass_kg=mass_story,
                        story_h_m=story_h,
                        drift_ratio_proxy=np.full(story_count, drift_hf * float(lf), dtype=np.float64),
                        elapsed_hours=0.5 * float(lf_idx + 1),
                        cycle_count=40 * (lf_idx + 1),
                        cfg=rc_cfg,
                    )
                    k_eff = np.asarray(rc_step.get("story_k_n_per_m", k_story), dtype=np.float64)
                    y_eff = np.asarray(rc_step.get("story_yield_drift_m", yield_story), dtype=np.float64)
                    idx = rc_step.get("indices")
                    if isinstance(idx, dict):
                        material_indices = {str(k): float(v) for k, v in idx.items() if isinstance(v, (int, float))}
                solved = solve_nonlinear_frame(
                    story_k_n_per_m=k_eff,
                    story_h_m=story_h,
                    story_axial_n=axial_story,
                    story_yield_drift_m=y_eff,
                    floor_load_n=floor_load,
                    cfg=cfg,
                )
                converged = bool(solved.get("converged", False) and int(solved.get("status", 0)) == 0)
                case_converged = bool(case_converged and converged)
                if not converged:
                    converged_all = False

                u_story = np.asarray(solved.get("u_story_m", []), dtype=np.float64)
                drift_pred_pct = _drift_ratio_pct(u_story, story_h)
                plastic_count = int(solved.get("plastic_story_count", 0))
                if first_yield is None and plastic_count > 0:
                    first_yield = float(lf)
                drift_series.append(float(drift_pred_pct))
                plastic_series.append(int(plastic_count))

                runs.append(
                    {
                        "load_factor": float(lf),
                        "converged": bool(converged),
                        "iterations": int(solved.get("iterations", 0)),
                        "residual_inf": float(solved.get("residual_inf", math.inf)),
                        "line_search_backtracks": int(solved.get("line_search_backtracks", 0)),
                        "plastic_story_count": int(plastic_count),
                        "top_displacement_m": float(solved.get("top_displacement_m", math.inf)),
                        "base_shear_kN": float(solved.get("base_shear_kn", math.inf)),
                        "drift_ratio_pct": float(drift_pred_pct),
                    }
                )

            peak_plastic_count = max(plastic_series) if plastic_series else 0
            peak_drift = max(drift_series) if drift_series else 0.0
            baseline_drift = drift_series[0] if drift_series else 0.0
            drift_amp = peak_drift / max(1e-9, baseline_drift)
            monotonic_drift = all((drift_series[i + 1] + 1e-9) >= drift_series[i] for i in range(len(drift_series) - 1))
            monotonic_plastic = all((plastic_series[i + 1]) >= plastic_series[i] for i in range(len(plastic_series) - 1))

            case_plastic_ok = bool(first_yield is not None and peak_plastic_count >= int(args.min_plastic_story_count))
            case_collapse_ok = bool(monotonic_drift and monotonic_plastic and drift_amp >= float(args.min_drift_amplification))

            plastic_all = bool(plastic_all and case_plastic_ok)
            collapse_path_all = bool(collapse_path_all and case_collapse_ok)
            if first_yield is not None:
                first_yield_factors.append(float(first_yield))
            peak_plastic.append(int(peak_plastic_count))
            drift_amplifications.append(float(drift_amp))
            material_ok = bool(
                (not use_rc)
                or (
                    float(material_indices.get("cracking_index_mean", 0.0)) > 0.0
                    and float(material_indices.get("stiffness_scale_mean", 1.0)) < 1.0
                )
            )
            material_all_ok = bool(material_all_ok and material_ok)
            material_effect_rows.append(
                {
                    "case_id": case_id,
                    "use_rc_composite_model": bool(use_rc),
                    "material_model_pass": bool(material_ok),
                    "indices": material_indices,
                    "section_profile_summary": dict(section_profile.get("summary", {})),
                    "section_family_counts": dict(section_profile.get("family_counts", {})),
                }
            )

            case_rows.append(
                {
                    "case_id": case_id,
                    "split": str(c.get("split", "")),
                    "topology_type": topology,
                    "hazard_type": str(c.get("hazard_type", "")),
                    "hf_reference": {
                        "drift_ratio_pct": float(drift_hf_pct),
                        "base_shear_kN": float(base_hf_kn),
                    },
                    "checks": {
                        "converged_all_load_levels": bool(case_converged),
                        "plasticity_triggered": bool(case_plastic_ok),
                        "collapse_path_pass": bool(case_collapse_ok),
                    },
                    "summary": {
                        "first_yield_load_factor": float(first_yield) if first_yield is not None else None,
                        "peak_plastic_story_count": int(peak_plastic_count),
                        "drift_amplification": float(drift_amp),
                        "monotonic_drift_pass": bool(monotonic_drift),
                        "monotonic_plastic_pass": bool(monotonic_plastic),
                        "material_model": "rc_composite" if use_rc else "steel_elastic_plastic",
                        "material_indices": material_indices,
                        "section_profile": dict(section_profile.get("summary", {})),
                        "section_family_counts": dict(section_profile.get("family_counts", {})),
                    },
                    "runs": runs,
                    "section_probe_head": list(section_profile.get("detail_rows", []))[:12],
                }
            )

        checks = {
            "metric_source_pass": bool(metric_source_ok),
            "all_cases_converged": bool(converged_all),
            "plasticity_triggered_all_cases": bool(plastic_all),
            "collapse_path_pass": bool(collapse_path_all),
            "min_plastic_story_count_pass": bool(all(v >= int(args.min_plastic_story_count) for v in peak_plastic)),
            "material_model_pass": bool(material_all_ok),
            "section_family_pass": bool(all(float(((row.get("section_profile_summary") or {}).get("stiffness_scale_min", 1.0)) >= 0.95) for row in material_effect_rows)),
        }
        contract_pass = bool(all(checks.values()))

        if not checks["metric_source_pass"]:
            reason_code = "ERR_CASES"
        elif not checks["all_cases_converged"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not checks["plasticity_triggered_all_cases"] or not checks["min_plastic_story_count_pass"]:
            reason_code = "ERR_PLASTICITY_NOT_TRIGGERED"
        elif not checks["material_model_pass"]:
            reason_code = "ERR_COLLAPSE_PATH_FAIL"
        elif not checks["collapse_path_pass"]:
            reason_code = "ERR_COLLAPSE_PATH_FAIL"
        else:
            reason_code = "PASS"

        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-pushover-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "case_count": len(case_rows),
                "load_factors": factors,
                "first_yield_load_factor_mean": statistics.fmean(first_yield_factors) if first_yield_factors else None,
                "peak_plastic_story_count_min": min(peak_plastic) if peak_plastic else 0,
                "peak_plastic_story_count_mean": statistics.fmean(peak_plastic) if peak_plastic else 0.0,
                "drift_amplification_min": min(drift_amplifications) if drift_amplifications else 0.0,
                "drift_amplification_mean": statistics.fmean(drift_amplifications) if drift_amplifications else 0.0,
                "metric_source_invalid_case_ids": metric_source_bad,
                "material_model": str(args.material_model),
            },
            "rows": case_rows,
            "material_effect_rows": material_effect_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }

        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        archive_manifest = _archive([str(out), str(args.cases)])
        if archive_manifest:
            report["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, 20, "pushover.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote nonlinear pushover stress report: {out}")
        if not contract_pass:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-pushover-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, 40, "pushover.invalid_input", error=str(exc))
        print(f"Wrote nonlinear pushover stress report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
