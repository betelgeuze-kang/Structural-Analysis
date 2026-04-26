#!/usr/bin/env python3
"""Construction-sequence gate: creep/shrinkage/differential-shortening preload."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

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
    "PASS": "construction-sequence gate passed",
    "ERR_INVALID_INPUT": "invalid construction-sequence input",
    "ERR_CASES": "insufficient benchmark cases",
    "ERR_ENGINE_FAIL": "rust nonlinear frame solver failed in one or more stages",
    "ERR_VNV_FAIL": "construction-sequence V&V threshold failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "target_split",
        "min_case_count",
        "max_case_count",
        "stage_count",
        "construction_years",
        "shrinkage_final_strain",
        "core_shortening_bias",
        "perimeter_shortening_bias",
        "min_diff_shortening_mm",
        "min_initial_stress_mpa",
        "max_initial_stress_mpa",
        "max_stage_drift_pct",
        "require_rust_backend",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "stage_count": {"type": "integer", "minimum": 4},
        "construction_years": {"type": "number", "exclusiveMinimum": 0.0},
        "rc_cracking_strain": {"type": "number", "exclusiveMinimum": 0.0},
        "rc_creep_rate_per_hour": {"type": "number", "minimum": 0.0},
        "rc_bond_slip_ratio_ref": {"type": "number", "exclusiveMinimum": 0.0},
        "shrinkage_final_strain": {"type": "number", "exclusiveMinimum": 0.0},
        "core_shortening_bias": {"type": "number", "exclusiveMinimum": 0.0},
        "perimeter_shortening_bias": {"type": "number", "exclusiveMinimum": 0.0},
        "min_diff_shortening_mm": {"type": "number", "minimum": 0.0},
        "min_initial_stress_mpa": {"type": "number", "minimum": 0.0},
        "max_initial_stress_mpa": {"type": "number", "exclusiveMinimum": 0.0},
        "max_stage_drift_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "require_rust_backend": {"type": "boolean"},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _story_count_for_topology(topology: str) -> int:
    t = str(topology).strip().lower()
    if t == "outrigger":
        return 28
    if t == "wall-frame":
        return 22
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
    denom = np.maximum(story_h_m * s, 1e-9)
    base = float(np.max(shear / denom) / drift_ratio_target)
    return np.maximum(1e3, base) * s


def _drift_ratio_pct(u_story: np.ndarray, story_h_m: np.ndarray) -> float:
    if u_story.size == 0:
        return 0.0
    du = np.diff(np.concatenate([[0.0], u_story]))
    return 100.0 * float(np.max(np.abs(du / np.maximum(story_h_m, 1e-9))))


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="construction_sequence_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def _section_family_beam_demand_summary(section_profiles: list[dict]) -> dict[str, float | int | bool]:
    profiles = [item for item in section_profiles if isinstance(item, dict)]
    if not profiles:
        return {
            "present": False,
            "profile_count": 0,
            "beam_tangent_scale_min": 0.0,
            "beam_tangent_scale_mean": 0.0,
            "beam_yielded_story_count_max": 0,
            "beam_max_trial_end_moment_ratio": 0.0,
            "beam_stability_index_max": 0.0,
            "beam_strain_energy_total_n_m": 0.0,
        }
    tangent_values = [float(profile.get("beam_tangent_scale_min", 0.0) or 0.0) for profile in profiles]
    yielded_values = [int(profile.get("beam_yielded_story_count", 0) or 0) for profile in profiles]
    demand_values = [float(profile.get("beam_max_trial_end_moment_ratio", 0.0) or 0.0) for profile in profiles]
    stability_values = [float(profile.get("beam_stability_index_max", 0.0) or 0.0) for profile in profiles]
    energy_values = [float(profile.get("beam_strain_energy_total_n_m", 0.0) or 0.0) for profile in profiles]
    return {
        "present": bool(len(profiles) > 0 and min(tangent_values, default=0.0) > 0.0 and sum(energy_values) > 0.0),
        "profile_count": len(profiles),
        "beam_tangent_scale_min": float(min(tangent_values) if tangent_values else 0.0),
        "beam_tangent_scale_mean": float(np.mean(tangent_values) if tangent_values else 0.0),
        "beam_yielded_story_count_max": int(max(yielded_values) if yielded_values else 0),
        "beam_max_trial_end_moment_ratio": float(max(demand_values) if demand_values else 0.0),
        "beam_stability_index_max": float(max(stability_values) if stability_values else 0.0),
        "beam_strain_energy_total_n_m": float(sum(energy_values)),
    }


def main() -> None:
    logger = get_logger("phase3.run_construction_sequence_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--min-case-count", type=int, default=2)
    p.add_argument("--max-case-count", type=int, default=4)
    p.add_argument("--stage-count", type=int, default=24)
    p.add_argument("--construction-years", type=float, default=4.0)
    p.add_argument("--rc-cracking-strain", type=float, default=2.2e-4)
    p.add_argument("--rc-creep-rate-per-hour", type=float, default=0.008)
    p.add_argument("--rc-bond-slip-ratio-ref", type=float, default=0.003)
    p.add_argument("--shrinkage-final-strain", type=float, default=3.0e-4)
    p.add_argument("--core-shortening-bias", type=float, default=1.10)
    p.add_argument("--perimeter-shortening-bias", type=float, default=0.93)
    p.add_argument("--min-diff-shortening-mm", type=float, default=2.0)
    p.add_argument("--min-initial-stress-mpa", type=float, default=1.0)
    p.add_argument("--max-initial-stress-mpa", type=float, default=120.0)
    p.add_argument("--max-stage-drift-pct", type=float, default=12.0)
    p.add_argument("--require-rust-backend", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--out", default="implementation/phase1/construction_sequence_gate_report.json")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "target_split": str(args.target_split),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "stage_count": int(args.stage_count),
        "construction_years": float(args.construction_years),
        "rc_cracking_strain": float(args.rc_cracking_strain),
        "rc_creep_rate_per_hour": float(args.rc_creep_rate_per_hour),
        "rc_bond_slip_ratio_ref": float(args.rc_bond_slip_ratio_ref),
        "shrinkage_final_strain": float(args.shrinkage_final_strain),
        "core_shortening_bias": float(args.core_shortening_bias),
        "perimeter_shortening_bias": float(args.perimeter_shortening_bias),
        "min_diff_shortening_mm": float(args.min_diff_shortening_mm),
        "min_initial_stress_mpa": float(args.min_initial_stress_mpa),
        "max_initial_stress_mpa": float(args.max_initial_stress_mpa),
        "max_stage_drift_pct": float(args.max_stage_drift_pct),
        "require_rust_backend": bool(args.require_rust_backend),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_construction_sequence_gate")
        log_event(logger, logging.INFO, "construction_gate.start", inputs=input_payload)

        payload = _load_json(Path(args.cases))
        cases = payload.get("cases")
        if not isinstance(cases, list):
            raise ValueError("cases[] missing")
        rows = [c for c in cases if isinstance(c, dict)]
        if str(args.target_split) != "all":
            rows = [c for c in rows if str(c.get("split", "")) == str(args.target_split)]
        rows = rows[: int(args.max_case_count)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"selected cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        cfg = RustNonlinearFrameConfig(
            tolerance=1e-7,
            max_iter=80,
            hardening_ratio=0.20,
            pdelta_factor=1.0,
        )
        mat_cfg = RCCompositeMaterialConfig(
            cracking_strain=float(args.rc_cracking_strain),
            creep_rate_per_hour=float(args.rc_creep_rate_per_hour),
            bond_slip_ratio_ref=float(args.rc_bond_slip_ratio_ref),
        )

        out_rows: list[dict] = []
        converged_all = True
        rust_backend_all = True
        monotonic_load_all = True
        max_stage_drift_all = 0.0
        diff_shortening_vals: list[float] = []
        init_stress_vals: list[float] = []
        creep_indices: list[float] = []
        shrinkage_indices: list[float] = []
        section_profile_rows: list[dict] = []

        stage_count = int(args.stage_count)
        total_hours = float(args.construction_years) * 365.0 * 24.0

        for case in rows:
            case_id = str(case.get("case_id", "unknown"))
            topology = str(case.get("topology_type", "rahmen"))
            n_story = _story_count_for_topology(topology)
            story_h = np.full(n_story, 3.2, dtype=np.float64)
            height_total = float(np.sum(story_h))

            drift_hf_pct = float((((case.get("metrics") or {}).get("drift_ratio_pct") or {}).get("hf", 1.2)))
            base_hf_kn = float((((case.get("metrics") or {}).get("base_shear_kN") or {}).get("hf", 1000.0)))
            base_hf_n = max(1.0, base_hf_kn * 1000.0)

            floor_load_full = build_story_load_profile(n_story, base_hf_n, mode="triangular")
            story_k_full = _build_story_stiffness_from_drift(
                floor_load_n=floor_load_full,
                story_h_m=story_h,
                drift_ratio_hf=max(drift_hf_pct / 100.0, 1e-6),
            )
            story_mass = np.linspace(5.0e5, 3.2e5, num=n_story, dtype=np.float64)
            story_yield_base = np.maximum(1e-4, 0.60 * (drift_hf_pct / 100.0) * story_h)
            story_axial_base = (4.4e6 * float(case.get("load_scale", 1.0))) * np.linspace(1.30, 0.85, num=n_story, dtype=np.float64)

            case_stages: list[dict] = []
            prev_load_scale = -1.0
            case_converged = True
            case_rust_ok = True
            case_max_drift = 0.0

            for s in range(1, stage_count + 1):
                load_scale = float(s / stage_count)
                elapsed_h = total_hours * load_scale
                monotonic_load = bool(load_scale >= prev_load_scale - 1e-12)
                prev_load_scale = load_scale
                monotonic_load_all = bool(monotonic_load_all and monotonic_load)

                construction_load_scale = 0.72 * load_scale
                floor_load = floor_load_full * construction_load_scale
                drift_proxy = np.linspace(0.0002, 0.0012, num=n_story, dtype=np.float64) * load_scale
                section_profile = evaluate_story_section_profile(
                    topology=topology,
                    material_type=str(case.get("material_type", "rc_composite")),
                    story_h_m=story_h,
                    drift_ratio_profile=drift_proxy,
                    load_scale=construction_load_scale,
                )
                rc_mod = apply_rc_composite_profile(
                    story_k_n_per_m=story_k_full * np.asarray(section_profile["story_stiffness_scale"], dtype=np.float64),
                    story_yield_drift_m=story_yield_base * np.asarray(section_profile["story_yield_scale"], dtype=np.float64),
                    story_mass_kg=story_mass,
                    story_h_m=story_h,
                    drift_ratio_proxy=drift_proxy,
                    elapsed_hours=float(elapsed_h),
                    cycle_count=s * 3,
                    cfg=mat_cfg,
                )

                k_mod = np.asarray(rc_mod["story_k_n_per_m"], dtype=np.float64)
                y_mod = np.asarray(rc_mod["story_yield_drift_m"], dtype=np.float64)
                m_mod = np.asarray(rc_mod["story_mass_kg"], dtype=np.float64)
                idx = rc_mod.get("indices") if isinstance(rc_mod.get("indices"), dict) else {}
                creep_idx = float(idx.get("creep_index_mean", 0.0))
                creep_indices.append(creep_idx)

                solve = solve_nonlinear_frame(
                    story_k_n_per_m=k_mod,
                    story_h_m=story_h,
                    story_axial_n=story_axial_base * construction_load_scale,
                    story_yield_drift_m=y_mod,
                    floor_load_n=floor_load,
                    cfg=cfg,
                )
                retry_count = 0
                if not bool(solve.get("converged", False)):
                    retry_cfg = RustNonlinearFrameConfig(
                        tolerance=1e-6,
                        max_iter=120,
                        hardening_ratio=0.24,
                        pdelta_factor=0.82,
                    )
                    solve_retry = solve_nonlinear_frame(
                        story_k_n_per_m=k_mod,
                        story_h_m=story_h,
                        story_axial_n=story_axial_base * construction_load_scale,
                        story_yield_drift_m=y_mod,
                        floor_load_n=floor_load,
                        cfg=retry_cfg,
                    )
                    if bool(solve_retry.get("converged", False)):
                        solve = solve_retry
                    retry_count = 1
                converged = bool(solve.get("converged", False) and int(solve.get("status", 0)) == 0)
                rust_ok = bool(str(solve.get("backend", "")).startswith("rust_ffi_"))
                case_converged = bool(case_converged and converged)
                case_rust_ok = bool(case_rust_ok and rust_ok)

                u = np.asarray(solve.get("u_story_m", []), dtype=np.float64)
                stage_drift_pct = _drift_ratio_pct(u, story_h)
                case_max_drift = max(case_max_drift, stage_drift_pct)
                max_stage_drift_all = max(max_stage_drift_all, stage_drift_pct)

                shrink_idx = float(1.0 - math.exp(-elapsed_h / max(total_hours * 0.45, 1.0)))
                shrinkage_indices.append(shrink_idx)
                shrink_strain = float(args.shrinkage_final_strain) * shrink_idx
                top_disp = float(solve.get("top_displacement_m", 0.0))
                core_shortening_m = (float(args.core_shortening_bias) * 0.12 * top_disp) + (0.35 * shrink_strain * height_total)
                perimeter_shortening_m = (float(args.perimeter_shortening_bias) * 0.11 * top_disp) + (0.30 * shrink_strain * height_total)
                diff_mm = abs(core_shortening_m - perimeter_shortening_m) * 1000.0
                diff_shortening_vals.append(diff_mm)

                # Elastic estimate of preload stress from differential shortening.
                e_eff_pa = 30.0e9
                init_stress_mpa = (e_eff_pa * abs(core_shortening_m - perimeter_shortening_m) / max(height_total, 1e-9)) / 1.0e6
                init_stress_vals.append(float(init_stress_mpa))

                case_stages.append(
                    {
                        "stage": int(s),
                        "load_scale": float(load_scale),
                        "construction_load_scale": float(construction_load_scale),
                        "elapsed_hours": float(elapsed_h),
                        "converged": bool(converged),
                        "rust_backend_ok": bool(rust_ok),
                        "retry_count": int(retry_count),
                        "drift_ratio_pct": float(stage_drift_pct),
                        "top_displacement_m": float(top_disp),
                        "core_shortening_mm": float(core_shortening_m * 1000.0),
                        "perimeter_shortening_mm": float(perimeter_shortening_m * 1000.0),
                        "differential_shortening_mm": float(diff_mm),
                        "initial_stress_mpa": float(init_stress_mpa),
                        "creep_index_mean": float(creep_idx),
                        "shrinkage_index": float(shrink_idx),
                        "stiffness_scale_min": float(idx.get("stiffness_scale_min", 1.0)),
                        "yield_scale_min": float(idx.get("yield_scale_min", 1.0)),
                        "section_profile": dict(section_profile.get("summary", {})),
                        "section_family_counts": dict(section_profile.get("family_counts", {})),
                    }
                )
                section_profile_rows.append(dict(section_profile.get("summary", {})))

            converged_all = bool(converged_all and case_converged)
            rust_backend_all = bool(rust_backend_all and case_rust_ok)
            case_section_demand = _section_family_beam_demand_summary(
                [stage.get("section_profile", {}) for stage in case_stages]
            )
            out_rows.append(
                {
                    "case_id": case_id,
                    "split": str(case.get("split", "")),
                    "topology_type": topology,
                    "stage_count": int(stage_count),
                    "converged_all_stages": bool(case_converged),
                    "rust_backend_ok_all_stages": bool(case_rust_ok),
                    "max_stage_drift_pct": float(case_max_drift),
                    "max_differential_shortening_mm": float(max(s["differential_shortening_mm"] for s in case_stages)),
                    "max_initial_stress_mpa": float(max(s["initial_stress_mpa"] for s in case_stages)),
                    "stages_head": case_stages[:64],
                    "stages_tail": case_stages[-8:],
                    "section_probe_head": [stage.get("section_profile", {}) for stage in case_stages[:8]],
                    "section_profile_demand": case_section_demand,
                }
            )

        section_demand_summary = _section_family_beam_demand_summary(section_profile_rows)
        checks = {
            "case_count_pass": bool(len(rows) >= int(args.min_case_count)),
            "all_stages_converged": bool(converged_all),
            "rust_backend_used_pass": bool(rust_backend_all),
            "stagewise_monotonic_load_pass": bool(monotonic_load_all),
            "creep_shrinkage_applied": bool(
                float(np.mean(creep_indices or [0.0])) > 0.05 and float(np.mean(shrinkage_indices or [0.0])) > 0.05
            ),
            "differential_shortening_detected": bool(max(diff_shortening_vals or [0.0]) >= float(args.min_diff_shortening_mm)),
            "initial_stress_nonzero": bool(max(init_stress_vals or [0.0]) >= float(args.min_initial_stress_mpa)),
            "initial_stress_upper_bound_pass": bool(max(init_stress_vals or [0.0]) <= float(args.max_initial_stress_mpa)),
            "drift_guard_pass": bool(max_stage_drift_all <= float(args.max_stage_drift_pct)),
            "section_family_pass": bool(
                all(
                    float(stage.get("section_profile", {}).get("stiffness_scale_min", 1.0)) >= 0.95
                    for row in out_rows
                    for stage in row.get("stages_head", [])
                )
            ),
        }
        contract_pass = bool(all(checks.values()))
        if not checks["case_count_pass"]:
            reason_code = "ERR_CASES"
        elif not checks["all_stages_converged"] or (bool(args.require_rust_backend) and not checks["rust_backend_used_pass"]):
            reason_code = "ERR_ENGINE_FAIL"
        elif not contract_pass:
            reason_code = "ERR_VNV_FAIL"
        else:
            reason_code = "PASS"

        report = {
            "schema_version": "1.0",
            "run_id": "phase3-construction-sequence-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "case_count": int(len(rows)),
                "stage_count": int(stage_count),
                "construction_years": float(args.construction_years),
                "max_stage_drift_pct_all_cases": float(max_stage_drift_all),
                "max_differential_shortening_mm": float(max(diff_shortening_vals or [0.0])),
                "max_initial_stress_mpa": float(max(init_stress_vals or [0.0])),
                "mean_initial_stress_mpa": float(np.mean(init_stress_vals or [0.0])),
                "mean_creep_index": float(np.mean(creep_indices or [0.0])),
                "mean_shrinkage_index": float(np.mean(shrinkage_indices or [0.0])),
                "section_family_beam_tangent_scale_min": float(section_demand_summary["beam_tangent_scale_min"]),
                "section_family_beam_tangent_scale_mean": float(section_demand_summary["beam_tangent_scale_mean"]),
                "section_family_beam_yielded_story_count_max": int(
                    section_demand_summary["beam_yielded_story_count_max"]
                ),
                "section_family_beam_max_trial_end_moment_ratio": float(
                    section_demand_summary["beam_max_trial_end_moment_ratio"]
                ),
                "section_family_beam_stability_index_max": float(
                    section_demand_summary["beam_stability_index_max"]
                ),
                "section_family_beam_strain_energy_total_n_m": float(
                    section_demand_summary["beam_strain_energy_total_n_m"]
                ),
            },
            "summary_line": (
                f"Construction sequence: {'PASS' if contract_pass else 'CHECK'} | "
                f"cases={len(rows)} | "
                f"stages={stage_count} | "
                f"diff_shortening_max_mm={float(max(diff_shortening_vals or [0.0])):.2f} | "
                f"init_stress_max_mpa={float(max(init_stress_vals or [0.0])):.2f} | "
                f"section_demand={'pass' if bool(section_demand_summary['present']) else 'tracked'}"
                f"(tangent={float(section_demand_summary['beam_tangent_scale_min']):.2f},"
                f"demand={float(section_demand_summary['beam_max_trial_end_moment_ratio']):.2f},"
                f"stability={float(section_demand_summary['beam_stability_index_max']):.2f})"
            ),
            "reasons": [
                (
                    f"stage_execution={'pass' if checks['all_stages_converged'] and checks['stagewise_monotonic_load_pass'] else 'check'} via "
                    f"cases={len(rows)}, stages={stage_count}, max_drift_pct={float(max_stage_drift_all):.3f}."
                ),
                (
                    f"creep_shrinkage={'pass' if checks['creep_shrinkage_applied'] and checks['differential_shortening_detected'] and checks['initial_stress_nonzero'] else 'check'} via "
                    f"diff_shortening_max_mm={float(max(diff_shortening_vals or [0.0])):.2f}, "
                    f"init_stress_max_mpa={float(max(init_stress_vals or [0.0])):.2f}, "
                    f"mean_creep={float(np.mean(creep_indices or [0.0])):.3f}."
                ),
                (
                    f"section_family_demand={'pass' if bool(section_demand_summary['present']) else 'tracked'} via "
                    f"profiles={int(section_demand_summary['profile_count'])}, "
                    f"tangent={float(section_demand_summary['beam_tangent_scale_min']):.2f}, "
                    f"yielded_story_max={int(section_demand_summary['beam_yielded_story_count_max'])}, "
                    f"demand={float(section_demand_summary['beam_max_trial_end_moment_ratio']):.2f}, "
                    f"stability={float(section_demand_summary['beam_stability_index_max']):.2f}."
                ),
            ],
            "rows": out_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact_archive_manifest"] = _archive([str(out), str(args.cases)])
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "construction_gate.completed",
            contract_pass=bool(contract_pass),
            reason_code=reason_code,
            case_count=int(len(rows)),
        )
        print(f"Wrote construction sequence gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, FileNotFoundError, InputContractError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-construction-sequence-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "construction_gate.invalid_input", error=str(exc))
        print(f"Wrote construction sequence gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
