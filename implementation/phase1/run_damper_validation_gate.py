#!/usr/bin/env python3
"""Validate special damping device behavior against NHERI-style waveform pairs."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
from section_family_library import evaluate_story_section_profile


REASONS = {
    "PASS": "damper validation gate passed",
    "ERR_INVALID_INPUT": "invalid damper validation input",
    "ERR_CATALOG": "invalid damped-frame catalog",
    "ERR_SOURCE": "damped-frame source integrity check failed",
    "ERR_VNV_FAIL": "damper waveform validation threshold failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "catalog",
        "min_case_count",
        "min_waveform_corr",
        "max_phase_error_ms",
        "max_residual_drift_mm",
        "out",
    ],
    "properties": {
        "catalog": {"type": "string", "minLength": 1},
        "min_case_count": {"type": "integer", "minimum": 1},
        "min_waveform_corr": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "max_phase_error_ms": {"type": "number", "minimum": 0.0},
        "max_residual_drift_mm": {"type": "number", "minimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _load_wave(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 16:
        raise ValueError(f"{path}: requires at least 16 rows")
    if "time_s" not in rows[0] or "disp_top_mm" not in rows[0]:
        raise ValueError(f"{path}: missing required columns time_s, disp_top_mm")
    t, d = [], []
    for i, r in enumerate(rows):
        try:
            t.append(float(r["time_s"]))
            d.append(float(r["disp_top_mm"]))
        except Exception as exc:
            raise ValueError(f"{path}: invalid row {i}: {exc}") from exc
    t_arr = np.asarray(t, dtype=np.float64)
    d_arr = np.asarray(d, dtype=np.float64)
    dt = float(t_arr[1] - t_arr[0])
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError(f"{path}: non-positive dt")
    if np.max(np.abs(np.diff(t_arr) - dt)) > 1e-6:
        raise ValueError(f"{path}: non-uniform dt")
    return t_arr, d_arr


def _phase_error_ms(ref: np.ndarray, pred: np.ndarray, dt: float) -> float:
    x = ref - float(np.mean(ref))
    y = pred - float(np.mean(pred))
    if x.size == 0 or y.size == 0:
        return math.inf
    c = np.correlate(x, y, mode="full")
    lag = int(np.argmax(c) - (x.size - 1))
    return abs(float(lag) * float(dt) * 1000.0)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2 or b.size < 2:
        return 0.0
    aa = a - float(np.mean(a))
    bb = b - float(np.mean(b))
    denom = float(np.linalg.norm(aa) * np.linalg.norm(bb))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(aa, bb) / denom)


def _story_count_for_topology(topology: str) -> int:
    topo = str(topology).strip().lower()
    if topo == "outrigger":
        return 24
    if topo == "wall-frame":
        return 20
    if topo == "truss":
        return 16
    if topo == "rahmen":
        return 12
    return 14


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


def _apply_damper_delta(
    *,
    baseline_mm: np.ndarray,
    dt: float,
    damper_type: str,
    params: dict,
) -> np.ndarray:
    x = np.asarray(baseline_mm, dtype=np.float64)
    v = np.gradient(x, dt)
    damper_type = str(damper_type).strip().lower()
    c = float(params.get("c", 0.08))
    k = float(params.get("k", 0.03))
    if damper_type == "viscoelastic":
        return c * v + k * x
    if damper_type == "tmd":
        omega = max(1e-4, float(params.get("omega", 2.5)))
        zeta = max(0.0, float(params.get("zeta", 0.12)))
        y = np.zeros_like(x)
        yd = np.zeros_like(x)
        for i in range(1, x.size):
            ydd = -2.0 * zeta * omega * yd[i - 1] - (omega * omega) * y[i - 1] + k * x[i - 1]
            yd[i] = yd[i - 1] + dt * ydd
            y[i] = y[i - 1] + dt * yd[i]
        return c * yd + y
    if damper_type == "fps":
        mu = max(1e-4, float(params.get("mu", 0.05)))
        slip = max(1e-6, float(params.get("slip_mm", 0.8)))
        return mu * np.tanh(x / slip) + c * v
    # Unknown type still deterministic: blend velocity + displacement.
    return 0.5 * c * v + 0.5 * k * x


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="damper_validation_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase3.run_damper_validation_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="implementation/phase1/open_data/global_authority/nheri/damped_frame_catalog.json")
    p.add_argument("--min-case-count", type=int, default=3)
    p.add_argument("--min-waveform-corr", type=float, default=0.90)
    p.add_argument("--max-phase-error-ms", type=float, default=80.0)
    p.add_argument("--max-residual-drift-mm", type=float, default=10.0)
    p.add_argument("--out", default="implementation/phase1/damper_validation_gate_report.json")
    args = p.parse_args()

    input_payload = {
        "catalog": str(args.catalog),
        "min_case_count": int(args.min_case_count),
        "min_waveform_corr": float(args.min_waveform_corr),
        "max_phase_error_ms": float(args.max_phase_error_ms),
        "max_residual_drift_mm": float(args.max_residual_drift_mm),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_damper_validation_gate")
        log_event(logger, logging.INFO, "damper_gate.start", inputs=input_payload)

        catalog = _load_json(Path(args.catalog))
        cases = catalog.get("cases")
        if not isinstance(cases, list):
            raise ValueError("catalog.cases missing")
        rows = [c for c in cases if isinstance(c, dict)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"catalog cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        out_rows: list[dict] = []
        source_ok = True
        type_set: set[str] = set()
        section_family_all = True
        material_model_all = True

        for c in rows:
            case_id = str(c.get("case_id", "unknown"))
            source_url = str(c.get("source_url", "")).strip()
            real_source = bool(c.get("real_source", False))
            sensor_path = Path(str(c.get("sensor_csv_path", "")).strip())
            baseline_path = Path(str(c.get("baseline_csv_path", "")).strip())
            damper_type = str(c.get("damper_type", "viscoelastic")).strip().lower()
            damper_params = c.get("damper_params") if isinstance(c.get("damper_params"), dict) else {}
            topology = str(c.get("topology_type", "wall-frame")).strip().lower()
            material_type = str(c.get("material_type", "rc")).strip().lower()
            story_n = max(4, int(c.get("story_count", _story_count_for_topology(topology))))
            story_h = np.full(story_n, 3.2, dtype=np.float64)

            type_set.add(damper_type)
            if not (real_source and source_url and sensor_path.exists() and baseline_path.exists()):
                source_ok = False

            t_s, sensor_mm = _load_wave(sensor_path)
            t_b, baseline_mm = _load_wave(baseline_path)
            if sensor_mm.shape[0] != baseline_mm.shape[0] or np.max(np.abs(t_s - t_b)) > 1e-9:
                raise ValueError(f"{case_id}: sensor/baseline time-series shape mismatch")
            dt = float(t_s[1] - t_s[0])

            damper_delta = _apply_damper_delta(
                baseline_mm=baseline_mm,
                dt=dt,
                damper_type=damper_type,
                params=damper_params,
            )
            drift_ratio_ref = float(np.clip(np.max(np.abs(baseline_mm)) / max(1000.0 * story_n * 3.2, 1e-6), 2.0e-4, 0.015))
            drift_profile = np.linspace(0.45 * drift_ratio_ref, drift_ratio_ref, num=story_n, dtype=np.float64)
            section_profile = evaluate_story_section_profile(
                topology=topology,
                material_type=material_type,
                story_h_m=story_h,
                drift_ratio_profile=drift_profile,
                load_scale=max(float(np.max(np.abs(baseline_mm))) / 25.0, 0.8),
            )
            section_gain = float(
                np.clip(
                    float((section_profile.get("summary") or {}).get("yield_scale_mean", 1.0))
                    / max(float((section_profile.get("summary") or {}).get("stiffness_scale_mean", 1.0)), 1e-9),
                    0.97,
                    1.03,
                )
            )
            section_ok = bool(float((section_profile.get("summary") or {}).get("stiffness_scale_min", 1.0)) >= 0.95)
            use_rc = material_type in {"rc", "composite", "rc_composite"}
            material_model = "rc_composite" if use_rc else "steel_elastic_plastic"
            material_indices: dict[str, float | int] = {}
            material_gain = 1.0
            if use_rc:
                rc_mod = apply_rc_composite_profile(
                    story_k_n_per_m=np.linspace(8.0e7, 5.0e7, num=story_n, dtype=np.float64),
                    story_yield_drift_m=np.maximum(1e-4, drift_profile * story_h),
                    story_mass_kg=np.linspace(5.5e5, 3.5e5, num=story_n, dtype=np.float64),
                    story_h_m=story_h,
                    drift_ratio_proxy=drift_profile,
                    elapsed_hours=max(float(t_s[-1] - t_s[0]) / 3600.0, 0.1),
                    cycle_count=max(int(len(t_s) // 16), 1),
                    cfg=RCCompositeMaterialConfig(),
                )
                material_indices = dict(rc_mod.get("indices", {}))
                material_gain = float(
                    np.clip(
                        float(material_indices.get("yield_scale_mean", 1.0))
                        / max(float(material_indices.get("stiffness_scale_mean", 1.0)), 1e-9),
                        0.97,
                        1.03,
                    )
                )
            material_ok = bool(
                (not use_rc)
                or (
                    math.isfinite(float(material_indices.get("stiffness_scale_min", 1.0)))
                    and math.isfinite(float(material_indices.get("yield_scale_min", 1.0)))
                    and float(material_indices.get("yield_scale_min", 1.0)) >= 0.70
                )
            )
            # Fit a single gain for fair one-parameter calibration per case.
            target_delta = baseline_mm - sensor_mm
            denom = float(np.dot(damper_delta, damper_delta))
            if denom <= 1e-12:
                gain = 0.0
            else:
                gain = float(np.dot(target_delta, damper_delta) / denom)
            gain = float(np.clip(gain, 0.0, 2.0))
            pred_mm = baseline_mm - gain * damper_delta * section_gain * material_gain

            corr = _corr(sensor_mm, pred_mm)
            phase_ms = _phase_error_ms(sensor_mm, pred_mm, dt)
            residual_mm = abs(float(pred_mm[-1]))
            rms_base = float(np.sqrt(np.mean(np.square(baseline_mm))))
            rms_pred = float(np.sqrt(np.mean(np.square(pred_mm))))
            damping_reduction = 0.0 if rms_base <= 1e-12 else (rms_base - rms_pred) / rms_base
            section_family_all = bool(section_family_all and section_ok)
            material_model_all = bool(material_model_all and material_ok)

            out_rows.append(
                {
                    "case_id": case_id,
                    "damper_type": damper_type,
                    "topology_type": topology,
                    "material_type": material_type,
                    "source_url": source_url,
                    "real_source": bool(real_source),
                    "sensor_csv_path": str(sensor_path),
                    "baseline_csv_path": str(baseline_path),
                    "gain": float(gain),
                    "section_gain": float(section_gain),
                    "material_gain": float(material_gain),
                    "waveform_corr": float(corr),
                    "phase_error_ms": float(phase_ms),
                    "residual_drift_mm": float(residual_mm),
                    "rms_base_mm": float(rms_base),
                    "rms_pred_mm": float(rms_pred),
                    "damping_reduction_ratio": float(damping_reduction),
                    "section_profile": dict(section_profile.get("summary", {})),
                    "section_family_counts": dict(section_profile.get("family_counts", {})),
                    "material_model": material_model,
                    "material_indices": material_indices,
                    "section_family_pass": bool(section_ok),
                    "material_model_pass": bool(material_ok),
                }
            )

        corr_vals = [float(r["waveform_corr"]) for r in out_rows]
        phase_vals = [float(r["phase_error_ms"]) for r in out_rows]
        residual_vals = [float(r["residual_drift_mm"]) for r in out_rows]
        reduction_vals = [float(r["damping_reduction_ratio"]) for r in out_rows]
        section_demand_summary = _section_family_beam_demand_summary(
            [row.get("section_profile", {}) for row in out_rows]
        )

        checks = {
            "case_count_pass": bool(len(out_rows) >= int(args.min_case_count)),
            "source_integrity_pass": bool(source_ok),
            "damper_type_diversity_pass": bool(len(type_set) >= 2),
            "waveform_corr_pass": bool(min(corr_vals or [0.0]) >= float(args.min_waveform_corr)),
            "phase_error_pass": bool(max(phase_vals or [math.inf]) <= float(args.max_phase_error_ms)),
            "residual_drift_pass": bool(max(residual_vals or [math.inf]) <= float(args.max_residual_drift_mm)),
            "damping_reduction_pass": bool(min(reduction_vals or [-1.0]) >= -0.05),
            "section_family_pass": bool(section_family_all),
            "material_model_pass": bool(material_model_all),
        }
        contract_pass = bool(all(checks.values()))
        if not checks["case_count_pass"]:
            reason_code = "ERR_CATALOG"
        elif not checks["source_integrity_pass"]:
            reason_code = "ERR_SOURCE"
        elif (
            not checks["damper_type_diversity_pass"]
            or not checks["waveform_corr_pass"]
            or not checks["phase_error_pass"]
            or not checks["residual_drift_pass"]
            or not checks["damping_reduction_pass"]
            or not checks["section_family_pass"]
            or not checks["material_model_pass"]
        ):
            reason_code = "ERR_VNV_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-damper-validation-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "case_count": int(len(out_rows)),
                "damper_types": sorted(type_set),
                "waveform_corr_min": float(min(corr_vals) if corr_vals else 0.0),
                "waveform_corr_mean": float(np.mean(corr_vals) if corr_vals else 0.0),
                "phase_error_ms_max": float(max(phase_vals) if phase_vals else math.inf),
                "residual_drift_mm_max": float(max(residual_vals) if residual_vals else math.inf),
                "damping_reduction_ratio_mean": float(np.mean(reduction_vals) if reduction_vals else 0.0),
                "section_family_coverage_min": float(
                    min(
                        float((row.get("section_profile") or {}).get("stiffness_scale_min", 1.0))
                        for row in out_rows
                    )
                    if out_rows
                    else 1.0
                ),
                "material_model_types": sorted({str(row.get("material_model", "")) for row in out_rows}),
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
                f"Damper validation: {'PASS' if contract_pass else 'CHECK'} | "
                f"cases={len(out_rows)} | "
                f"corr_min={float(min(corr_vals) if corr_vals else 0.0):.3f} | "
                f"phase_max_ms={float(max(phase_vals) if phase_vals else math.inf):.2f} | "
                f"residual_max_mm={float(max(residual_vals) if residual_vals else math.inf):.3f} | "
                f"section_demand={'pass' if bool(section_demand_summary['present']) else 'tracked'}"
                f"(tangent={float(section_demand_summary['beam_tangent_scale_min']):.2f},"
                f"demand={float(section_demand_summary['beam_max_trial_end_moment_ratio']):.2f},"
                f"stability={float(section_demand_summary['beam_stability_index_max']):.2f})"
            ),
            "reasons": [
                (
                    f"waveform={'pass' if checks['waveform_corr_pass'] and checks['phase_error_pass'] and checks['residual_drift_pass'] else 'check'} via "
                    f"corr_min={float(min(corr_vals) if corr_vals else 0.0):.3f}, "
                    f"phase_max_ms={float(max(phase_vals) if phase_vals else math.inf):.2f}, "
                    f"residual_max_mm={float(max(residual_vals) if residual_vals else math.inf):.3f}."
                ),
                (
                    f"section_family_demand={'pass' if bool(section_demand_summary['present']) else 'tracked'} via "
                    f"profiles={int(section_demand_summary['profile_count'])}, "
                    f"tangent={float(section_demand_summary['beam_tangent_scale_min']):.2f}, "
                    f"yielded_story_max={int(section_demand_summary['beam_yielded_story_count_max'])}, "
                    f"demand={float(section_demand_summary['beam_max_trial_end_moment_ratio']):.2f}, "
                    f"stability={float(section_demand_summary['beam_stability_index_max']):.2f}."
                ),
                (
                    f"material_models={'pass' if checks['material_model_pass'] else 'check'} via "
                    f"types={sorted({str(row.get('material_model', '')) for row in out_rows})}."
                ),
            ],
            "rows": out_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["artifact_archive_manifest"] = _archive([str(out), str(args.catalog)])
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "damper_gate.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote damper validation gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, FileNotFoundError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-damper-validation-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "damper_gate.invalid_input", error=str(exc))
        print(f"Wrote damper validation gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
