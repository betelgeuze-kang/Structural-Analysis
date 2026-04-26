#!/usr/bin/env python3
"""Stress test: noise sensitivity on RWTH test cases (sensor + stiffness noise)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import random
import shlex
import statistics
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "noise sensitivity stress test completed within configured robustness envelope",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CASE_SELECTION": "failed to select required target test cases",
    "ERR_BENCHMARK_RUN": "benchmark run failed under one or more noise scenarios",
    "ERR_METRIC_NAN": "non-finite metric observed in stress run",
    "ERR_ROBUSTNESS_FAIL": "high-noise scenario exceeded configured error envelope",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "out",
        "sensor_noise_levels_pct",
        "stiffness_noise_levels_pct",
        "seeds",
        "target_split",
        "required_case_count",
        "epochs",
        "branches",
        "top_k",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "work_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
        "target_case_ids": {"type": "string"},
        "sensor_noise_levels_pct": {"type": "string", "minLength": 1},
        "stiffness_noise_levels_pct": {"type": "string", "minLength": 1},
        "seeds": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "required_case_count": {"type": "integer", "minimum": 1},
        "epochs": {"type": "integer", "minimum": 1},
        "branches": {"type": "integer", "minimum": 2},
        "top_k": {"type": "integer", "minimum": 2},
        "lr": {"type": "number", "exclusiveMinimum": 0.0},
        "epsilon": {"type": "number", "exclusiveMinimum": 0.0},
        "temperature": {"type": "number", "exclusiveMinimum": 0.0},
        "max_high_noise_drift_p95_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "max_high_noise_base_p95_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
    },
}

METRICS = ("drift_ratio_pct", "base_shear_kN", "mode_shape_mac", "buckling_factor", "equilibrium_residual")


def _parse_pct_levels(text: str) -> list[float]:
    vals: list[float] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        v = float(tok)
        if v < 0.0:
            raise ValueError("noise levels must be >= 0")
        vals.append(v)
    vals = sorted(set(vals))
    if not vals:
        raise ValueError("at least one noise level is required")
    return vals


def _parse_int_list(text: str) -> list[int]:
    vals: list[int] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        vals.append(int(tok))
    vals = sorted(set(vals))
    if not vals:
        raise ValueError("at least one seed is required")
    return vals


def _parse_case_ids(text: str) -> list[str]:
    vals: list[str] = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if tok:
            vals.append(tok)
    return sorted(set(vals))


def _is_finite(x: float) -> bool:
    return math.isfinite(float(x))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-1500:],
        (proc.stderr or "")[-1500:],
    )


def _clip_positive(x: float) -> float:
    return max(1e-12, float(x))


def _clip_mac(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _perturb_metric(metric: str, hf: float, lf: float, sensor_sigma: float, stiff_sigma: float, rng: random.Random) -> tuple[float, float]:
    sensor_delta = rng.gauss(0.0, sensor_sigma) if sensor_sigma > 0.0 else 0.0
    stiff_delta = rng.gauss(0.0, stiff_sigma) if stiff_sigma > 0.0 else 0.0

    if metric == "mode_shape_mac":
        hf_new = _clip_mac(hf - abs(sensor_delta) * 0.08)
        lf_new = _clip_mac(lf - (0.65 * abs(sensor_delta) + 0.45 * abs(stiff_delta)))
        return hf_new, lf_new

    hf_mul = 1.0 + sensor_delta
    if metric in {"drift_ratio_pct", "equilibrium_residual"}:
        lf_mul = 1.0 + 0.40 * sensor_delta + 1.10 * stiff_delta
    elif metric == "base_shear_kN":
        lf_mul = 1.0 + 0.45 * sensor_delta - 0.75 * stiff_delta
    elif metric == "buckling_factor":
        lf_mul = 1.0 + 0.20 * sensor_delta - 1.35 * abs(stiff_delta)
    else:
        lf_mul = 1.0 + sensor_delta + stiff_delta

    hf_new = _clip_positive(hf * hf_mul)
    lf_new = _clip_positive(lf * lf_mul)
    return hf_new, lf_new


def _build_noisy_payload(base: dict, target_case_ids: set[str], sensor_pct: float, stiff_pct: float, seed: int) -> dict:
    payload = json.loads(json.dumps(base))
    sensor_sigma = float(sensor_pct) / 100.0
    stiff_sigma = float(stiff_pct) / 100.0

    for idx, case in enumerate(payload.get("cases", [])):
        if not isinstance(case, dict):
            continue
        cid = str(case.get("case_id", ""))
        if cid not in target_case_ids:
            continue
        rng = random.Random(int(seed) * 1_000_003 + idx * 17 + int(sensor_pct * 100) * 31 + int(stiff_pct * 100) * 53)

        metrics = case.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        for metric in METRICS:
            row = metrics.get(metric)
            if not isinstance(row, dict):
                continue
            hf = float(row.get("hf", 0.0))
            lf = float(row.get("lf", 0.0))
            hf_new, lf_new = _perturb_metric(metric, hf, lf, sensor_sigma, stiff_sigma, rng)
            row["hf"] = float(hf_new)
            row["lf"] = float(lf_new)

        load_scale = float(case.get("load_scale", 1.0))
        residual_norm = float(case.get("residual_norm", 0.2))
        stiff_delta = rng.gauss(0.0, stiff_sigma) if stiff_sigma > 0.0 else 0.0
        sensor_delta = rng.gauss(0.0, sensor_sigma) if sensor_sigma > 0.0 else 0.0
        case["load_scale"] = max(0.05, load_scale * (1.0 - 0.55 * stiff_delta))
        case["residual_norm"] = min(0.98, max(0.01, residual_norm * (1.0 + 0.55 * abs(sensor_delta) + 0.35 * abs(stiff_delta))))

    # Keep public benchmark mirror in sync for selected IDs.
    by_id = {str(c.get("case_id", "")): c for c in payload.get("cases", []) if isinstance(c, dict)}
    for pub in payload.get("public_benchmark_cases", []):
        if not isinstance(pub, dict):
            continue
        cid = str(pub.get("case_id", ""))
        if cid not in target_case_ids:
            continue
        src = by_id.get(cid)
        if not isinstance(src, dict):
            continue
        metrics = src.get("metrics", {})
        if not isinstance(metrics, dict):
            continue
        pub["hf_metrics"] = {m: float((metrics.get(m) or {}).get("hf", 0.0)) for m in METRICS}
    return payload


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    ys = sorted(float(v) for v in xs)
    idx = max(0, min(len(ys) - 1, int(math.ceil(0.95 * len(ys)) - 1)))
    return float(ys[idx])


def _select_target_cases(cases: list[dict], explicit_case_ids: list[str], target_split: str, required_count: int) -> list[str]:
    by_id = {str(c.get("case_id", "")): c for c in cases if isinstance(c, dict)}
    if explicit_case_ids:
        selected = [cid for cid in explicit_case_ids if cid in by_id]
    else:
        if str(target_split) == "all":
            selected = sorted(
                str(c.get("case_id"))
                for c in cases
                if isinstance(c, dict) and str(c.get("case_id", "")).strip()
            )[: int(required_count)]
        else:
            selected = sorted(
                str(c.get("case_id"))
                for c in cases
                if isinstance(c, dict) and str(c.get("split", "")) == str(target_split)
            )[: int(required_count)]
    selected = sorted(set(selected))
    if len(selected) < int(required_count):
        raise ValueError(
            f"target case selection failed: required={required_count}, selected={len(selected)}, split={target_split}"
        )
    return selected


def _archive_outputs(test_name: str, paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name=test_name,
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase1.run_noise_sensitivity_stress")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json")
    p.add_argument("--work-dir", default="implementation/phase1/stress/noise")
    p.add_argument("--out", default="implementation/phase1/noise_sensitivity_stress_report.json")
    p.add_argument("--target-case-ids", default="")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--required-case-count", type=int, default=4)
    p.add_argument("--sensor-noise-levels-pct", default="0,1,3,5")
    p.add_argument("--stiffness-noise-levels-pct", default="0,10")
    p.add_argument("--seeds", default="11,23,47")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--branches", type=int, default=10)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--lr", type=float, default=0.055)
    p.add_argument("--epsilon", type=float, default=0.11)
    p.add_argument("--temperature", type=float, default=0.32)
    p.add_argument("--max-high-noise-drift-p95-pct", type=float, default=15.0)
    p.add_argument("--max-high-noise-base-p95-pct", type=float, default=10.0)
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
        "target_case_ids": str(args.target_case_ids),
        "sensor_noise_levels_pct": str(args.sensor_noise_levels_pct),
        "stiffness_noise_levels_pct": str(args.stiffness_noise_levels_pct),
        "seeds": str(args.seeds),
        "target_split": str(args.target_split),
        "required_case_count": int(args.required_case_count),
        "epochs": int(args.epochs),
        "branches": int(args.branches),
        "top_k": int(args.top_k),
        "lr": float(args.lr),
        "epsilon": float(args.epsilon),
        "temperature": float(args.temperature),
        "max_high_noise_drift_p95_pct": float(args.max_high_noise_drift_p95_pct),
        "max_high_noise_base_p95_pct": float(args.max_high_noise_base_p95_pct),
        "accepted_metric_sources": str(args.accepted_metric_sources),
    }

    out_path = Path(args.out)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    steps: list[dict] = []
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase-stress.run_noise_sensitivity_stress")
        if int(args.top_k) > int(args.branches):
            raise ValueError("top_k cannot exceed branches")

        sensor_levels = _parse_pct_levels(args.sensor_noise_levels_pct)
        stiffness_levels = _parse_pct_levels(args.stiffness_noise_levels_pct)
        seeds = _parse_int_list(args.seeds)

        cases_payload = _load_json(Path(args.cases))
        cases = cases_payload.get("cases", [])
        if not isinstance(cases, list) or not cases:
            raise ValueError("cases payload must include non-empty 'cases'")

        selected_case_ids = _select_target_cases(
            cases=cases,
            explicit_case_ids=_parse_case_ids(args.target_case_ids),
            target_split=str(args.target_split),
            required_count=int(args.required_case_count),
        )
        selected_case_set = set(selected_case_ids)

        log_event(
            logger,
            logging.INFO,
            "noise_stress.start",
            selected_case_ids=selected_case_ids,
            sensor_noise_levels_pct=sensor_levels,
            stiffness_noise_levels_pct=stiffness_levels,
            seeds=seeds,
        )

        scenario_rows: list[dict] = []
        run_failures: list[dict] = []

        for sensor_pct in sensor_levels:
            for stiff_pct in stiffness_levels:
                per_seed_metrics: list[dict] = []
                for seed in seeds:
                    tag = f"s{int(sensor_pct):02d}_k{int(stiff_pct):02d}_seed{int(seed)}"
                    noisy_cases_path = work_dir / f"noisy_cases_{tag}.json"
                    bench_out = work_dir / f"hf_benchmark_{tag}.json"
                    cmp_out = work_dir / f"topk_comparison_{tag}.json"

                    noisy_payload = _build_noisy_payload(
                        base=cases_payload,
                        target_case_ids=selected_case_set,
                        sensor_pct=float(sensor_pct),
                        stiff_pct=float(stiff_pct),
                        seed=int(seed),
                    )
                    noisy_cases_path.write_text(json.dumps(noisy_payload, indent=2), encoding="utf-8")

                    cmd = [
                        sys.executable,
                        "implementation/phase1/benchmark_kpi_contract.py",
                        "--cases",
                        str(noisy_cases_path),
                        "--out",
                        str(bench_out),
                        "--comparison-out",
                        str(cmp_out),
                        "--target-split",
                        str(args.target_split),
                        "--epochs",
                        str(int(args.epochs)),
                        "--branches",
                        str(int(args.branches)),
                        "--top-k",
                        str(int(args.top_k)),
                        "--lr",
                        str(float(args.lr)),
                        "--epsilon",
                        str(float(args.epsilon)),
                        "--temperature",
                        str(float(args.temperature)),
                        "--seed",
                        str(int(seed)),
                        "--max-drift-error-pct",
                        "100.0",
                        "--max-base-shear-error-pct",
                        "100.0",
                        "--max-buckling-factor-error-pct",
                        "100.0",
                        "--min-mode-shape-mac",
                        "0.0",
                        "--require-direct-metrics",
                        "--accepted-metric-sources",
                        str(args.accepted_metric_sources),
                    ]
                    ok, dt, rc, stdout_tail, stderr_tail = _run(cmd)
                    steps.append(
                        {
                            "step": "benchmark_noisy_scenario",
                            "scenario": {"sensor_noise_pct": float(sensor_pct), "stiffness_noise_pct": float(stiff_pct), "seed": int(seed)},
                            "seconds": float(dt),
                            "ok": bool(ok),
                            "return_code": int(rc),
                            "command": shlex.join(cmd),
                            "stdout_tail": stdout_tail,
                            "stderr_tail": stderr_tail,
                        }
                    )
                    if not bench_out.exists():
                        run_failures.append(
                            {
                                "sensor_noise_pct": float(sensor_pct),
                                "stiffness_noise_pct": float(stiff_pct),
                                "seed": int(seed),
                                "return_code": int(rc),
                                "error": "benchmark report missing",
                            }
                        )
                        continue

                    benchmark = _load_json(bench_out)
                    metrics = benchmark.get("metrics", {})
                    drift = float(metrics.get("drift_error_pct", math.nan))
                    base = float(metrics.get("base_shear_error_pct", math.nan))
                    buck = float(metrics.get("buckling_factor_error_pct", math.nan))
                    mac = float(metrics.get("mode_shape_mac", math.nan))
                    if not (_is_finite(drift) and _is_finite(base) and _is_finite(buck) and _is_finite(mac)):
                        run_failures.append(
                            {
                                "sensor_noise_pct": float(sensor_pct),
                                "stiffness_noise_pct": float(stiff_pct),
                                "seed": int(seed),
                                "return_code": int(rc),
                                "error": "non-finite benchmark metrics",
                            }
                        )
                        continue

                    per_seed_metrics.append(
                        {
                            "seed": int(seed),
                            "benchmark_reason_code": str(benchmark.get("reason_code", "")),
                            "benchmark_contract_pass": bool(benchmark.get("contract_pass", False)),
                            "drift_error_pct": drift,
                            "base_shear_error_pct": base,
                            "buckling_factor_error_pct": buck,
                            "mode_shape_mac": mac,
                        }
                    )

                drift_vals = [float(m["drift_error_pct"]) for m in per_seed_metrics]
                base_vals = [float(m["base_shear_error_pct"]) for m in per_seed_metrics]
                buck_vals = [float(m["buckling_factor_error_pct"]) for m in per_seed_metrics]
                mac_vals = [float(m["mode_shape_mac"]) for m in per_seed_metrics]

                scenario_rows.append(
                    {
                        "sensor_noise_pct": float(sensor_pct),
                        "stiffness_noise_pct": float(stiff_pct),
                        "seed_count": len(per_seed_metrics),
                        "drift_error_pct_mean": float(statistics.fmean(drift_vals) if drift_vals else math.nan),
                        "drift_error_pct_p95": float(_p95(drift_vals)),
                        "drift_error_pct_worst": float(max(drift_vals) if drift_vals else math.nan),
                        "base_shear_error_pct_mean": float(statistics.fmean(base_vals) if base_vals else math.nan),
                        "base_shear_error_pct_p95": float(_p95(base_vals)),
                        "base_shear_error_pct_worst": float(max(base_vals) if base_vals else math.nan),
                        "buckling_factor_error_pct_mean": float(statistics.fmean(buck_vals) if buck_vals else math.nan),
                        "mode_shape_mac_mean": float(statistics.fmean(mac_vals) if mac_vals else math.nan),
                        "per_seed": per_seed_metrics,
                    }
                )

        scenario_rows = sorted(scenario_rows, key=lambda r: (float(r["sensor_noise_pct"]), float(r["stiffness_noise_pct"])))
        scenario_count_expected = len(sensor_levels) * len(stiffness_levels)
        scenario_count_actual = len(scenario_rows)

        baseline = next(
            (r for r in scenario_rows if float(r["sensor_noise_pct"]) == 0.0 and float(r["stiffness_noise_pct"]) == 0.0),
            None,
        )
        high_noise = next(
            (
                r
                for r in scenario_rows
                if float(r["sensor_noise_pct"]) == float(max(sensor_levels))
                and float(r["stiffness_noise_pct"]) == float(max(stiffness_levels))
            ),
            None,
        )

        if isinstance(baseline, dict):
            baseline_drift = max(float(baseline["drift_error_pct_mean"]), 1e-9)
            baseline_base = max(float(baseline["base_shear_error_pct_mean"]), 1e-9)
            for row in scenario_rows:
                row["drift_error_blowup_factor"] = float(row["drift_error_pct_mean"]) / baseline_drift
                row["base_shear_error_blowup_factor"] = float(row["base_shear_error_pct_mean"]) / baseline_base

        finite_metrics = True
        for row in scenario_rows:
            for key in (
                "drift_error_pct_mean",
                "drift_error_pct_p95",
                "drift_error_pct_worst",
                "base_shear_error_pct_mean",
                "base_shear_error_pct_p95",
                "base_shear_error_pct_worst",
                "buckling_factor_error_pct_mean",
                "mode_shape_mac_mean",
            ):
                if not _is_finite(float(row.get(key, math.nan))):
                    finite_metrics = False
                    break
            if not finite_metrics:
                break

        noise_sweep_complete = scenario_count_actual == scenario_count_expected
        has_required_case_count = len(selected_case_ids) >= int(args.required_case_count)
        high_noise_available = isinstance(high_noise, dict)
        high_noise_drift_p95 = float(high_noise["drift_error_pct_p95"]) if high_noise_available else math.inf
        high_noise_base_p95 = float(high_noise["base_shear_error_pct_p95"]) if high_noise_available else math.inf
        high_noise_degradation_detected = bool(
            isinstance(high_noise, dict)
            and isinstance(baseline, dict)
            and float(high_noise.get("drift_error_blowup_factor", 0.0)) >= 1.05
        )
        robustness_budget_pass = bool(
            high_noise_drift_p95 <= float(args.max_high_noise_drift_p95_pct)
            and high_noise_base_p95 <= float(args.max_high_noise_base_p95_pct)
        )

        if not has_required_case_count:
            reason_code = "ERR_CASE_SELECTION"
        elif run_failures:
            reason_code = "ERR_BENCHMARK_RUN"
        elif not noise_sweep_complete:
            reason_code = "ERR_BENCHMARK_RUN"
        elif not finite_metrics:
            reason_code = "ERR_METRIC_NAN"
        elif not robustness_budget_pass:
            reason_code = "ERR_ROBUSTNESS_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-noise-sensitivity-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "cases": str(args.cases),
                "target_split": str(args.target_split),
                "required_case_count": int(args.required_case_count),
                "target_case_ids": selected_case_ids,
                "sensor_noise_levels_pct": sensor_levels,
                "stiffness_noise_levels_pct": stiffness_levels,
                "seeds": seeds,
                "epochs": int(args.epochs),
                "branches": int(args.branches),
                "top_k": int(args.top_k),
                "lr": float(args.lr),
                "epsilon": float(args.epsilon),
                "temperature": float(args.temperature),
                "accepted_metric_sources": str(args.accepted_metric_sources),
                "max_high_noise_drift_p95_pct": float(args.max_high_noise_drift_p95_pct),
                "max_high_noise_base_p95_pct": float(args.max_high_noise_base_p95_pct),
            },
            "checks": {
                "has_required_case_count": bool(has_required_case_count),
                "noise_sweep_complete": bool(noise_sweep_complete),
                "finite_metrics": bool(finite_metrics),
                "high_noise_available": bool(high_noise_available),
                "high_noise_degradation_detected": bool(high_noise_degradation_detected),
                "robustness_budget_pass": bool(robustness_budget_pass),
            },
            "summary": {
                "scenario_count_expected": int(scenario_count_expected),
                "scenario_count_actual": int(scenario_count_actual),
                "selected_case_count": len(selected_case_ids),
                "high_noise_drift_error_pct_p95": float(high_noise_drift_p95),
                "high_noise_base_shear_error_pct_p95": float(high_noise_base_p95),
                "baseline_row": baseline,
                "high_noise_row": high_noise,
            },
            "scenario_rows": scenario_rows,
            "failures": run_failures,
            "steps": steps,
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="noise_sensitivity_stress",
            paths=[str(args.out), str(args.work_dir), str(args.cases)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "noise_stress.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=reason_code,
            scenarios=int(scenario_count_actual),
        )
        print(f"Wrote noise sensitivity stress report: {out_path}")
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "noise_stress.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-noise-sensitivity-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="noise_sensitivity_stress",
            paths=[str(args.out), str(args.work_dir), str(args.cases)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote noise sensitivity stress report: {out_path}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "noise_stress.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-noise-sensitivity-stress",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_BENCHMARK_RUN",
            "reason": f"{REASONS['ERR_BENCHMARK_RUN']}: {exc}",
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="noise_sensitivity_stress",
            paths=[str(args.out), str(args.work_dir), str(args.cases)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote noise sensitivity stress report: {out_path}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
