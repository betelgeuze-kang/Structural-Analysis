#!/usr/bin/env python3
"""RC/composite benchmark-lock proxy gate.

This gate does not claim public experimental closure. It fixes a deterministic
benchmark slice for the three dominant RC fidelity risks:
- cracking
- bond-slip
- creep/shrinkage
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from rc_composite_material_model import RCCompositeMaterialConfig, apply_rc_composite_profile
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "rc benchmark lock gate passed",
    "ERR_INVALID_INPUT": "invalid rc benchmark gate input",
    "ERR_CASES": "rc benchmark cases missing or invalid",
    "ERR_BENCHMARK_LOCK_FAIL": "one or more rc benchmark families violated expected ranges",
}


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cases", "min_case_count", "out"],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "authority_catalog": {"type": "string", "minLength": 1},
        "require_authority": {"type": "boolean"},
        "min_authority_case_count": {"type": "integer", "minimum": 1},
        "min_case_count": {"type": "integer", "minimum": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(x: object, default: float = math.nan) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    return v if math.isfinite(v) else default


def _range_pass(value: float, bounds: list[float] | tuple[float, float]) -> bool:
    if len(bounds) != 2:
        return False
    lo = _finite(bounds[0], math.nan)
    hi = _finite(bounds[1], math.nan)
    if not math.isfinite(lo) or not math.isfinite(hi):
        return False
    return bool(lo <= float(value) <= hi)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_authority_track(*, catalog_path: Path, min_case_count: int) -> tuple[list[dict[str, Any]], dict[str, bool], dict[str, Any]]:
    catalog = _load_json(catalog_path)
    tracks = catalog.get("tracks") if isinstance(catalog.get("tracks"), dict) else {}
    nheri = tracks.get("nheri") if isinstance(tracks.get("nheri"), dict) else {}
    raw_cases = nheri.get("cases") if isinstance(nheri.get("cases"), list) else []
    rows: list[dict[str, Any]] = []
    public_source_pass = True
    integrity_pass = True
    waveform_pass = True
    for idx, case in enumerate(raw_cases):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id", f"authority-{idx}"))
        source_url = str(case.get("source_url", "")).strip()
        sensor_path = Path(str(case.get("sensor_csv_path", "")))
        baseline_path = Path(str(case.get("baseline_csv_path", "")))
        waveform_path = Path(str(case.get("waveform_metrics_path", "")))
        manifest_path = waveform_path.with_name(waveform_path.name.replace("_waveform_metrics.json", "_source_manifest.json"))
        sensor_sha_expected = str(case.get("sensor_csv_sha256", "")).strip().lower()
        baseline_sha_expected = str(case.get("baseline_csv_sha256", "")).strip().lower()

        sensor_exists = sensor_path.exists()
        baseline_exists = baseline_path.exists()
        waveform_exists = waveform_path.exists()
        manifest_exists = manifest_path.exists()
        sensor_sha_actual = _sha256_file(sensor_path) if sensor_exists else ""
        baseline_sha_actual = _sha256_file(baseline_path) if baseline_exists else ""
        sensor_sha_ok = bool(sensor_exists and sensor_sha_expected and sensor_sha_actual == sensor_sha_expected)
        baseline_sha_ok = bool(baseline_exists and baseline_sha_expected and baseline_sha_actual == baseline_sha_expected)

        waveform = _load_json(waveform_path) if waveform_exists else {}
        manifest = _load_json(manifest_path) if manifest_exists else {}
        waveform_checks = waveform.get("checks") if isinstance(waveform.get("checks"), dict) else {}
        waveform_metrics = waveform.get("metrics") if isinstance(waveform.get("metrics"), dict) else {}

        real_source = bool(case.get("real_source", False))
        source_url_ok = source_url.startswith("https://")
        manifest_source_ok = bool(
            manifest.get("source_url", "") == source_url
            and str(manifest.get("source_sha256", "")).strip().lower() == sensor_sha_expected
        )
        case_waveform_pass = bool(
            waveform.get("contract_pass", False)
            and bool(waveform_checks.get("waveform_corr_pass", False))
            and bool(waveform_checks.get("phase_error_pass", False))
            and bool(waveform_checks.get("residual_drift_pass", False))
        )
        case_integrity_pass = bool(sensor_sha_ok and baseline_sha_ok and manifest_exists and manifest_source_ok)
        case_public_pass = bool(real_source and source_url_ok)
        case_pass = bool(case_public_pass and case_integrity_pass and case_waveform_pass)

        public_source_pass = bool(public_source_pass and case_public_pass)
        integrity_pass = bool(integrity_pass and case_integrity_pass)
        waveform_pass = bool(waveform_pass and case_waveform_pass)

        rows.append(
            {
                "case_id": case_id,
                "authority_family": "nheri_public_experiment",
                "source_url": source_url,
                "sensor_csv_path": str(sensor_path),
                "baseline_csv_path": str(baseline_path),
                "waveform_metrics_path": str(waveform_path),
                "source_manifest_path": str(manifest_path),
                "sensor_sha256_expected": sensor_sha_expected,
                "sensor_sha256_actual": sensor_sha_actual,
                "baseline_sha256_expected": baseline_sha_expected,
                "baseline_sha256_actual": baseline_sha_actual,
                "metric_values": {
                    "waveform_corr": _finite(waveform_metrics.get("waveform_corr"), math.nan),
                    "phase_error_ms": _finite(waveform_metrics.get("phase_error_ms"), math.nan),
                    "residual_drift_mm": _finite(waveform_metrics.get("residual_drift_mm"), math.nan),
                },
                "metric_checks": {
                    "waveform_corr_pass": bool(waveform_checks.get("waveform_corr_pass", False)),
                    "phase_error_pass": bool(waveform_checks.get("phase_error_pass", False)),
                    "residual_drift_pass": bool(waveform_checks.get("residual_drift_pass", False)),
                },
                "integrity_checks": {
                    "real_source": real_source,
                    "source_url_ok": source_url_ok,
                    "sensor_sha_ok": sensor_sha_ok,
                    "baseline_sha_ok": baseline_sha_ok,
                    "manifest_exists": manifest_exists,
                    "manifest_source_ok": manifest_source_ok,
                },
                "case_pass": case_pass,
            }
        )

    checks = {
        "authority_case_count_pass": len(rows) >= int(min_case_count),
        "authority_public_source_pass": bool(public_source_pass),
        "authority_source_integrity_pass": bool(integrity_pass),
        "authority_waveform_pass": bool(waveform_pass),
        "authority_track_pass": bool(rows and all(bool(row.get("case_pass", False)) for row in rows)),
    }
    summary = {
        "authority_case_count": len(rows),
        "authority_pass_count": sum(1 for row in rows if bool(row.get("case_pass", False))),
        "authority_source_family": "nheri_public_experiment",
    }
    return rows, checks, summary


def _case_family_pass(row: dict[str, Any]) -> bool:
    checks = row.get("metric_checks")
    if not isinstance(checks, dict):
        return False
    return bool(all(bool(v) for v in checks.values()))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/open_data/rc/rc_benchmark_lock_cases.json")
    p.add_argument("--authority-catalog", default="implementation/phase1/open_data/global_authority/authority_source_catalog.json")
    p.add_argument("--require-authority", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--min-authority-case-count", type=int, default=3)
    p.add_argument("--min-case-count", type=int, default=4)
    p.add_argument("--out", default="implementation/phase1/rc_benchmark_lock_report.json")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "authority_catalog": str(args.authority_catalog),
        "require_authority": bool(args.require_authority),
        "min_authority_case_count": int(args.min_authority_case_count),
        "min_case_count": int(args.min_case_count),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_rc_benchmark_lock_gate")
        payload = _load_json(Path(args.cases))
        raw_cases = payload.get("cases")
        if not isinstance(raw_cases, list) or len(raw_cases) < int(args.min_case_count):
            raise ValueError("rc benchmark cases missing or below min_case_count")

        rows: list[dict[str, Any]] = []
        family_pass: dict[str, bool] = {}
        finite_pass = True

        for idx, case in enumerate(raw_cases):
            if not isinstance(case, dict):
                raise ValueError(f"cases[{idx}] must be object")
            case_id = str(case.get("case_id", f"case-{idx}"))
            family = str(case.get("benchmark_family", "unknown"))
            expected = case.get("expected_ranges")
            if not isinstance(expected, dict) or not expected:
                raise ValueError(f"{case_id}: expected_ranges missing")

            rc_out = apply_rc_composite_profile(
                story_k_n_per_m=np.asarray(case.get("story_k_n_per_m", []), dtype=np.float64),
                story_yield_drift_m=np.asarray(case.get("story_yield_drift_m", []), dtype=np.float64),
                story_mass_kg=np.asarray(case.get("story_mass_kg", []), dtype=np.float64),
                story_h_m=np.asarray(case.get("story_h_m", []), dtype=np.float64),
                drift_ratio_proxy=np.asarray(case.get("drift_ratio_proxy", []), dtype=np.float64),
                elapsed_hours=float(case.get("elapsed_hours", 0.0)),
                cycle_count=int(case.get("cycle_count", 0)),
                cfg=RCCompositeMaterialConfig(),
            )
            metrics = rc_out.get("indices") if isinstance(rc_out.get("indices"), dict) else {}
            metric_checks: dict[str, bool] = {}
            metric_values: dict[str, float] = {}
            for metric_name, bounds in expected.items():
                value = _finite(metrics.get(metric_name), math.nan)
                metric_values[str(metric_name)] = value
                finite_pass = bool(finite_pass and math.isfinite(value))
                metric_checks[str(metric_name)] = _range_pass(value, bounds)

            row = {
                "case_id": case_id,
                "benchmark_family": family,
                "elapsed_hours": float(case.get("elapsed_hours", 0.0)),
                "cycle_count": int(case.get("cycle_count", 0)),
                "metric_values": metric_values,
                "expected_ranges": expected,
                "metric_checks": metric_checks,
                "case_pass": bool(all(metric_checks.values())),
            }
            rows.append(row)
            family_pass[family] = bool(family_pass.get(family, True) and row["case_pass"])

        authority_rows: list[dict[str, Any]] = []
        authority_checks: dict[str, bool] = {
            "authority_case_count_pass": True,
            "authority_public_source_pass": True,
            "authority_source_integrity_pass": True,
            "authority_waveform_pass": True,
            "authority_track_pass": True,
        }
        authority_summary: dict[str, Any] = {
            "authority_case_count": 0,
            "authority_pass_count": 0,
            "authority_source_family": "disabled",
        }
        if bool(args.require_authority):
            authority_rows, authority_checks, authority_summary = _load_authority_track(
                catalog_path=Path(args.authority_catalog),
                min_case_count=int(args.min_authority_case_count),
            )

        checks = {
            "case_count_pass": len(rows) >= int(args.min_case_count),
            "finite_pass": bool(finite_pass),
            "all_ranges_pass": bool(all(row["case_pass"] for row in rows)),
            "cracking_case_pass": bool(family_pass.get("cyclic_wall_cracking", False)),
            "bond_slip_case_pass": bool(family_pass.get("bond_slip_pullout", False)),
            "creep_case_pass": bool(family_pass.get("creep_shrinkage_column", False)),
            "slab_wall_case_pass": bool(family_pass.get("slab_wall_interaction", False)),
            **authority_checks,
        }
        contract_pass = bool(all(checks.values()))
        reason_code = "PASS" if contract_pass else "ERR_BENCHMARK_LOCK_FAIL"
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-rc-benchmark-lock-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "case_count": len(rows),
                "family_count": len({str(row.get("benchmark_family", "")) for row in rows}),
                "families": sorted({str(row.get("benchmark_family", "")) for row in rows}),
                "authority_case_count": int(authority_summary.get("authority_case_count", 0)),
                "authority_pass_count": int(authority_summary.get("authority_pass_count", 0)),
                "validation_mode": "hybrid_authority_locked" if bool(args.require_authority) else "proxy_only",
            },
            "rows": rows,
            "authority_rows": authority_rows,
            "contract_pass": contract_pass,
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote RC benchmark lock report: {out}")
        if not contract_pass:
            raise SystemExit(1)
    except (ValueError, FileNotFoundError, InputContractError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-rc-benchmark-lock-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote RC benchmark lock report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
