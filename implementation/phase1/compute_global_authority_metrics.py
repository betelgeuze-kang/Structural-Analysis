#!/usr/bin/env python3
"""Compute authority-track metrics from raw benchmark/sensor CSV files.

Modes:
- sac: structural KPI + 5-component member-force errors from HF/LF CSV pairs
- nheri: waveform correlation / phase error / residual drift from sensor-baseline CSV
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np


REASONS = {
    "PASS": "authority metrics computed",
    "ERR_INVALID_INPUT": "invalid input argument",
    "ERR_FILE_MISSING": "input csv missing",
    "ERR_COLUMN_MISSING": "required metric column missing",
    "ERR_NUMERIC": "numeric conversion failed",
}


SAC_ALIASES = {
    "case_id": ("case_id",),
    "drift": ("drift_error_pct", "drift_ratio_pct", "max_drift_ratio_pct", "story_drift_pct"),
    "base_shear": ("base_shear_error_pct", "base_shear_kN", "base_shear_kn"),
    "mac": ("mode_shape_mac", "mac", "mac_mode1"),
    "axial": ("axial_force_kN", "axial_force", "member_axial_force_kN"),
    "shear_y": ("shear_force_y_kN", "shear_y_kN", "vy_kN", "vy"),
    "shear_z": ("shear_force_z_kN", "shear_z_kN", "vz_kN", "vz"),
    "moment_y": ("bending_moment_y_kNm", "moment_y_kNm", "my_kNm", "my"),
    "moment_z": ("bending_moment_z_kNm", "moment_z_kNm", "mz_kNm", "mz"),
}

NHERI_ALIASES = {
    "time": ("time_s", "time", "t"),
    "disp": ("disp_top_mm", "disp_mm", "displacement_mm", "top_disp_mm"),
}


def _load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        headers = [str(x) for x in (rdr.fieldnames or [])]
    return rows, headers


def _resolve(headers: Iterable[str], aliases: tuple[str, ...]) -> str | None:
    hs = {str(h).strip() for h in headers if str(h).strip()}
    for c in aliases:
        if c in hs:
            return c
    return None


def _to_float(v: object) -> float:
    return float(str(v).strip())


def _p95(values: list[float]) -> float:
    if not values:
        return math.inf
    xs = sorted(float(v) for v in values)
    i = max(0, min(len(xs) - 1, int(math.ceil(0.95 * len(xs))) - 1))
    return float(xs[i])


def _err_pct(hf: float, lf: float) -> float:
    return abs(lf - hf) / max(abs(hf), 1e-9) * 100.0


def _compute_sac(args: argparse.Namespace) -> tuple[dict, int]:
    hf_rows, hf_headers = _load_csv(Path(args.hf_csv))
    lf_rows, lf_headers = _load_csv(Path(args.lf_csv))

    case_hf = _resolve(hf_headers, SAC_ALIASES["case_id"]) or "case_id"
    case_lf = _resolve(lf_headers, SAC_ALIASES["case_id"]) or "case_id"
    hf_map = {str(r.get(case_hf, "")).strip(): r for r in hf_rows if str(r.get(case_hf, "")).strip()}
    lf_map = {str(r.get(case_lf, "")).strip(): r for r in lf_rows if str(r.get(case_lf, "")).strip()}
    common_ids = sorted(set(hf_map.keys()) & set(lf_map.keys()))
    if not common_ids:
        return {
            "schema_version": "1.0",
            "run_id": "global-authority-metrics-sac",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_source": "direct_reference",
            "checks": {
                "drift_within_5pct": False,
                "base_shear_within_5pct": False,
                "mac_above_095": False,
                "member_force_components_5d_pass": False,
            },
            "metrics": {},
            "contract_pass": False,
            "reason_code": "ERR_COLUMN_MISSING",
            "reason": "no overlapping case_id between hf/lf csv",
        }, 1

    hf_cols = {
        "drift": _resolve(hf_headers, SAC_ALIASES["drift"]),
        "base_shear": _resolve(hf_headers, SAC_ALIASES["base_shear"]),
        "mac": _resolve(hf_headers, SAC_ALIASES["mac"]),
        "axial": _resolve(hf_headers, SAC_ALIASES["axial"]),
        "shear_y": _resolve(hf_headers, SAC_ALIASES["shear_y"]),
        "shear_z": _resolve(hf_headers, SAC_ALIASES["shear_z"]),
        "moment_y": _resolve(hf_headers, SAC_ALIASES["moment_y"]),
        "moment_z": _resolve(hf_headers, SAC_ALIASES["moment_z"]),
    }
    lf_cols = {
        "drift": _resolve(lf_headers, SAC_ALIASES["drift"]),
        "base_shear": _resolve(lf_headers, SAC_ALIASES["base_shear"]),
        "mac": _resolve(lf_headers, SAC_ALIASES["mac"]),
        "axial": _resolve(lf_headers, SAC_ALIASES["axial"]),
        "shear_y": _resolve(lf_headers, SAC_ALIASES["shear_y"]),
        "shear_z": _resolve(lf_headers, SAC_ALIASES["shear_z"]),
        "moment_y": _resolve(lf_headers, SAC_ALIASES["moment_y"]),
        "moment_z": _resolve(lf_headers, SAC_ALIASES["moment_z"]),
    }

    missing = [k for k in ("drift", "base_shear") if not (hf_cols[k] and lf_cols[k])]
    if missing:
        return {
            "schema_version": "1.0",
            "run_id": "global-authority-metrics-sac",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_source": "direct_reference",
            "checks": {
                "drift_within_5pct": False,
                "base_shear_within_5pct": False,
                "mac_above_095": False,
                "member_force_components_5d_pass": False,
            },
            "metrics": {"missing_columns": missing},
            "contract_pass": False,
            "reason_code": "ERR_COLUMN_MISSING",
            "reason": f"missing columns: {','.join(missing)}",
        }, 1

    drift_errs: list[float] = []
    shear_errs: list[float] = []
    mac_values: list[float] = []
    mf_errs: dict[str, list[float]] = {k: [] for k in ("axial", "shear_y", "shear_z", "moment_y", "moment_z")}
    for cid in common_ids:
        hr = hf_map[cid]
        lr = lf_map[cid]
        try:
            drift_errs.append(_err_pct(_to_float(hr[hf_cols["drift"]]), _to_float(lr[lf_cols["drift"]])))
            shear_errs.append(_err_pct(_to_float(hr[hf_cols["base_shear"]]), _to_float(lr[lf_cols["base_shear"]])))
            mac_col = lf_cols["mac"] or hf_cols["mac"]
            if mac_col is not None:
                src = lr if mac_col in lr else hr
                mac_values.append(_to_float(src[mac_col]))
            for comp in mf_errs.keys():
                hcol = hf_cols.get(comp)
                lcol = lf_cols.get(comp)
                if hcol and lcol:
                    mf_errs[comp].append(_err_pct(_to_float(hr[hcol]), _to_float(lr[lcol])))
        except Exception:
            return {
                "schema_version": "1.0",
                "run_id": "global-authority-metrics-sac",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "metric_source": "direct_reference",
                "checks": {
                    "drift_within_5pct": False,
                    "base_shear_within_5pct": False,
                    "mac_above_095": False,
                    "member_force_components_5d_pass": False,
                },
                "metrics": {"case_id": cid},
                "contract_pass": False,
                "reason_code": "ERR_NUMERIC",
                "reason": f"numeric parse failed at case_id={cid}",
            }, 1

    drift_error_pct = _p95(drift_errs)
    base_shear_error_pct = _p95(shear_errs)
    mode_shape_mac = float(np.median(np.asarray(mac_values, dtype=np.float64))) if mac_values else 0.0
    mf_p95 = {k: _p95(v) for k, v in mf_errs.items()}
    mf_covered = [k for k, v in mf_errs.items() if len(v) > 0]
    member_force_components_5d_pass = bool(len(mf_covered) == 5 and all(float(mf_p95[k]) <= float(args.max_member_force_error_pct) for k in mf_covered))

    checks = {
        "drift_within_5pct": bool(drift_error_pct <= float(args.max_error_pct)),
        "base_shear_within_5pct": bool(base_shear_error_pct <= float(args.max_error_pct)),
        "mac_above_095": bool(mode_shape_mac >= float(args.min_mac)),
        "member_force_components_5d_pass": bool(member_force_components_5d_pass),
    }
    payload = {
        "schema_version": "1.0",
        "run_id": "global-authority-metrics-sac",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metric_source": "direct_reference",
        "inputs": {
            "hf_csv": str(args.hf_csv),
            "lf_csv": str(args.lf_csv),
            "case_count": int(len(common_ids)),
        },
        "checks": checks,
        "metrics": {
            "drift_error_pct": float(drift_error_pct),
            "base_shear_error_pct": float(base_shear_error_pct),
            "mode_shape_mac": float(mode_shape_mac),
            "member_force_error_pct_p95": {
                "axial": float(mf_p95["axial"]),
                "shear_y": float(mf_p95["shear_y"]),
                "shear_z": float(mf_p95["shear_z"]),
                "moment_y": float(mf_p95["moment_y"]),
                "moment_z": float(mf_p95["moment_z"]),
            },
            "member_force_component_count": int(len(mf_covered)),
        },
        "contract_pass": bool(all(checks.values())),
        "reason_code": "PASS" if bool(all(checks.values())) else "ERR_COLUMN_MISSING",
        "reason": REASONS["PASS"] if bool(all(checks.values())) else "sac metrics threshold failed",
    }
    return payload, 0 if payload["contract_pass"] else 1


def _pick_series(rows: list[dict[str, str]], headers: list[str], explicit_col: str | None, alias_key: str) -> tuple[np.ndarray, str | None]:
    col = str(explicit_col or "").strip()
    if col and col in headers:
        vals = np.asarray([_to_float(r[col]) for r in rows], dtype=np.float64)
        return vals, col
    c = _resolve(headers, NHERI_ALIASES[alias_key])
    if c is not None:
        vals = np.asarray([_to_float(r[c]) for r in rows], dtype=np.float64)
        return vals, c
    return np.asarray([], dtype=np.float64), None


def _compute_nheri(args: argparse.Namespace) -> tuple[dict, int]:
    sensor_rows, sensor_headers = _load_csv(Path(args.sensor_csv))
    base_rows, base_headers = _load_csv(Path(args.baseline_csv))
    n = min(len(sensor_rows), len(base_rows))
    if n <= 2:
        payload = {
            "schema_version": "1.0",
            "run_id": "global-authority-metrics-nheri",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_source": "direct_reference",
            "checks": {
                "waveform_corr_pass": False,
                "phase_error_pass": False,
                "residual_drift_pass": False,
            },
            "metrics": {},
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": "sensor/baseline row count too small",
        }
        return payload, 1

    sensor_rows = sensor_rows[:n]
    base_rows = base_rows[:n]
    s, scol = _pick_series(sensor_rows, sensor_headers, getattr(args, "sensor_disp_col", None), "disp")
    b, bcol = _pick_series(base_rows, base_headers, getattr(args, "baseline_disp_col", None), "disp")
    if s.size != n or b.size != n:
        payload = {
            "schema_version": "1.0",
            "run_id": "global-authority-metrics-nheri",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_source": "direct_reference",
            "checks": {
                "waveform_corr_pass": False,
                "phase_error_pass": False,
                "residual_drift_pass": False,
            },
            "metrics": {},
            "contract_pass": False,
            "reason_code": "ERR_COLUMN_MISSING",
            "reason": "missing displacement columns in sensor/baseline",
        }
        return payload, 1

    # Estimate dt from time column if available.
    ts, tcol_s = _pick_series(sensor_rows, sensor_headers, getattr(args, "time_col", None), "time")
    dt = float(args.default_dt)
    if ts.size >= 3:
        dts = np.diff(ts)
        dts = dts[np.isfinite(dts)]
        if dts.size:
            med = float(np.median(dts))
            if med > 0:
                dt = med

    s0 = s - float(np.mean(s))
    b0 = b - float(np.mean(b))
    denom = float(np.linalg.norm(s0) * np.linalg.norm(b0))
    waveform_corr = float(np.dot(s0, b0) / denom) if denom > 1e-12 else 0.0

    # Phase shift by lag that maximizes normalized cross-correlation.
    xcorr = np.correlate(s0, b0, mode="full")
    lag = int(np.argmax(np.abs(xcorr)) - (n - 1))
    phase_error_ms = abs(float(lag) * dt * 1000.0)
    residual_drift_mm = abs(float(s[-1] - b[-1]))

    checks = {
        "waveform_corr_pass": bool(waveform_corr >= float(args.min_waveform_corr)),
        "phase_error_pass": bool(phase_error_ms <= float(args.max_phase_error_ms)),
        "residual_drift_pass": bool(residual_drift_mm <= float(args.max_residual_drift_mm)),
    }
    payload = {
        "schema_version": "1.0",
        "run_id": "global-authority-metrics-nheri",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metric_source": "direct_reference",
        "inputs": {
            "sensor_csv": str(args.sensor_csv),
            "baseline_csv": str(args.baseline_csv),
            "sample_count": int(n),
            "sensor_disp_col": str(scol or ""),
            "baseline_disp_col": str(bcol or ""),
            "time_col": str(tcol_s or ""),
            "dt_s": float(dt),
        },
        "checks": checks,
        "metrics": {
            "waveform_corr": float(waveform_corr),
            "phase_error_ms": float(phase_error_ms),
            "residual_drift_mm": float(residual_drift_mm),
        },
        "contract_pass": bool(all(checks.values())),
        "reason_code": "PASS" if bool(all(checks.values())) else "ERR_NUMERIC",
        "reason": REASONS["PASS"] if bool(all(checks.values())) else "nheri metrics threshold failed",
    }
    return payload, 0 if payload["contract_pass"] else 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("sac", "nheri"), required=True)
    p.add_argument("--out", required=True)

    # SAC mode
    p.add_argument("--hf-csv", default="")
    p.add_argument("--lf-csv", default="")
    p.add_argument("--max-error-pct", type=float, default=5.0)
    p.add_argument("--min-mac", type=float, default=0.95)
    p.add_argument("--max-member-force-error-pct", type=float, default=5.0)

    # NHERI mode
    p.add_argument("--sensor-csv", default="")
    p.add_argument("--baseline-csv", default="")
    p.add_argument("--sensor-disp-col", default="")
    p.add_argument("--baseline-disp-col", default="")
    p.add_argument("--time-col", default="")
    p.add_argument("--default-dt", type=float, default=0.01)
    p.add_argument("--min-waveform-corr", type=float, default=0.95)
    p.add_argument("--max-phase-error-ms", type=float, default=15.0)
    p.add_argument("--max-residual-drift-mm", type=float, default=3.0)
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.mode == "sac":
            if not str(args.hf_csv).strip() or not str(args.lf_csv).strip():
                raise ValueError("hf_csv/lf_csv required for sac mode")
            payload, code = _compute_sac(args)
        else:
            if not str(args.sensor_csv).strip() or not str(args.baseline_csv).strip():
                raise ValueError("sensor_csv/baseline_csv required for nheri mode")
            payload, code = _compute_nheri(args)
    except FileNotFoundError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": f"global-authority-metrics-{args.mode}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_source": "direct_reference",
            "contract_pass": False,
            "reason_code": "ERR_FILE_MISSING",
            "reason": f"{REASONS['ERR_FILE_MISSING']}: {exc}",
        }
        code = 1
    except Exception as exc:  # noqa: BLE001
        payload = {
            "schema_version": "1.0",
            "run_id": f"global-authority-metrics-{args.mode}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_source": "direct_reference",
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        code = 1

    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote authority metrics report: {out}")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
