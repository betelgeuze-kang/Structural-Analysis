#!/usr/bin/env python3
"""Commercial-readiness qualification suite for mega-structure dynamics.

This runner enforces a strict 7-axis gate:
1) real-source integrity
2) scale-out (PR: 1M/3M, Nightly: +10M)
3) noise robustness under realistic perturbations
4) GPU strict policy
5) O(N)-friendly scaling regression
6) phase-aware dynamics quality
7) OOD safety gate
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "commercial-readiness qualification passed",
    "ERR_INVALID_INPUT": "invalid qualification input",
    "ERR_REAL_SOURCE_FAIL": "real-source integrity gate failed",
    "ERR_BENCHMARK_FAIL": "accuracy benchmark gate failed",
    "ERR_NOISE_ROBUSTNESS_FAIL": "noise robustness gate failed",
    "ERR_NOISE_CONVERGENCE_FAIL": "noise convergence gate failed",
    "ERR_PHASE_DYNAMICS_FAIL": "phase dynamics gate failed",
    "ERR_OOD_FAIL": "OOD safety gate failed",
    "ERR_SCALEOUT_FAIL": "scale-out gate failed",
    "ERR_GPU_STRICT_FAIL": "gpu strict gate failed",
    "ERR_COMMERCIAL_FAIL": "commercial grade gate failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "model_cases",
        "ci_mode",
        "work_dir",
        "out",
    ],
    "properties": {
        "model_cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "ci_mode": {"type": "string", "enum": ["pr", "nightly"]},
        "force_rerun": {"type": "boolean"},
        "reuse_existing_if_present": {"type": "boolean"},
        "require_gpu_strict": {"type": "boolean"},
        "benchmark_epochs": {"type": "integer", "minimum": 1},
        "benchmark_branches": {"type": "integer", "minimum": 2},
        "benchmark_top_k": {"type": "integer", "minimum": 2},
        "noise_epochs": {"type": "integer", "minimum": 1},
        "noise_required_case_count": {"type": "integer", "minimum": 1},
        "noise_sensor_levels_pct": {"type": "string", "minLength": 1},
        "noise_stiffness_levels_pct": {"type": "string", "minLength": 1},
        "noise_seeds": {"type": "string", "minLength": 1},
        "convergence_seeds": {"type": "string", "minLength": 1},
        "convergence_stiffness_levels_pct": {"type": "string", "minLength": 1},
        "scale_levels_pr": {"type": "string", "minLength": 1},
        "scale_levels_nightly": {"type": "string", "minLength": 1},
        "scale_levels_io": {"type": "string", "minLength": 1},
        "opensees_edge_list_json": {"type": "string", "minLength": 1},
        "max_drift_error_pct": {"type": "number", "minimum": 0.0},
        "max_base_shear_error_pct": {"type": "number", "minimum": 0.0},
        "min_mode_shape_mac": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_buckling_factor_error_pct": {"type": "number", "minimum": 0.0},
        "max_high_noise_drift_p95_pct": {"type": "number", "minimum": 0.0},
        "max_high_noise_base_p95_pct": {"type": "number", "minimum": 0.0},
        "min_wave_corr": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "max_post_phase_error_deg": {"type": "number", "minimum": 0.0},
        "max_post_lag_ms": {"type": "number", "minimum": 0.0},
        "min_ood_recall": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_ood_false_negative_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_scaleout_memory_slope": {"type": "number", "minimum": 0.0},
        "max_scaleout_latency_slope": {"type": "number", "minimum": 0.0},
        "scaleout_max_projection_ratio": {"type": "number", "minimum": 0.0},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
        "forbid_toy_cases": {"type": "boolean"},
        "min_source_families": {"type": "integer", "minimum": 1},
        "min_measured_source_families": {"type": "integer", "minimum": 1},
        "min_measured_case_count": {"type": "integer", "minimum": 1},
        "require_measured_dynamic_targets": {"type": "boolean"},
        "require_shell_beam_mix_cases": {"type": "boolean"},
        "min_total_case_count": {"type": "integer", "minimum": 1},
        "min_unique_topology_types": {"type": "integer", "minimum": 1},
        "min_unique_hazard_types": {"type": "integer", "minimum": 1},
        "work_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _parse_csv(text: str) -> list[str]:
    return [x.strip() for x in str(text).split(",") if x.strip()]


def _safe_label(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(text)).strip("_") or "model"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run(
    *,
    step: str,
    cmd: list[str],
    report_path: Path,
    force_rerun: bool,
    reuse_existing_if_present: bool,
    reuse_validator=None,
    steps: list[dict],
) -> bool:
    reusable_existing = False
    if report_path.exists():
        try:
            existing = json.loads(report_path.read_text(encoding="utf-8"))
            reusable_existing = isinstance(existing, dict) and any(
                key in existing for key in ("contract_pass", "pass", "all_pass")
            )
            if reusable_existing and callable(reuse_validator):
                reusable_existing = bool(reuse_validator(existing))
        except Exception:
            reusable_existing = False
    if (not force_rerun) and reuse_existing_if_present and reusable_existing:
        steps.append(
            {
                "step": step,
                "ok": True,
                "reused_existing": True,
                "seconds": 0.0,
                "return_code": 0,
                "command": shlex.join(cmd),
                "report_path": str(report_path),
            }
        )
        return True
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    steps.append(
        {
            "step": step,
            "ok": bool(proc.returncode == 0),
            "reused_existing": False,
            "seconds": float(dt),
            "return_code": int(proc.returncode),
            "command": shlex.join(cmd),
            "report_path": str(report_path),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    )
    return proc.returncode == 0


def _metric_source_gate(cases_payload: dict, accepted: set[str]) -> tuple[bool, list[str], int]:
    rows = cases_payload.get("cases")
    if not isinstance(rows, list) or not rows:
        return False, ["cases[] missing"], 0
    bad: list[str] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            bad.append(f"case[{i}] not object")
            continue
        src = str(row.get("metric_source", "")).strip()
        if not src:
            bad.append(f"{row.get('case_id', f'case-{i}')}: metric_source missing")
        elif src not in accepted:
            bad.append(f"{row.get('case_id', f'case-{i}')}: metric_source={src}")
    return len(bad) == 0, bad, len(rows)


def _contains_toy_marker(path: Path, payload: dict) -> tuple[bool, list[str]]:
    # "atwood" is an official measured benchmark candidate, not a toy marker.
    markers = ("toy", "synthetic", "sanity", "sample", "demo", "mock")
    hits: list[str] = []

    def _scan_text(label: str, text: object) -> None:
        s = str(text).strip().lower()
        if not s:
            return
        for tok in markers:
            if tok in s:
                hits.append(f"{label}:{tok}")
                break

    _scan_text("path", str(path))
    if isinstance(payload, dict):
        _scan_text("run_id", payload.get("run_id", ""))
        src = payload.get("source")
        if isinstance(src, dict):
            for k in ("dataset", "source_name", "id", "url", "name"):
                _scan_text(f"source.{k}", src.get(k, ""))
        rows = payload.get("cases")
        if isinstance(rows, list):
            for i, row in enumerate(rows[:10]):
                if not isinstance(row, dict):
                    continue
                _scan_text(f"cases[{i}].case_id", row.get("case_id", ""))
                _scan_text(f"cases[{i}].source_name", row.get("source_name", ""))
    return (len(hits) > 0), hits[:20]


def _benchmark_report_matches_cases_sha(existing: dict, expected_cases_sha256: str) -> bool:
    if not isinstance(existing, dict):
        return False
    report_sha = str(existing.get("source_cases_sha256", "")).strip()
    if not report_sha:
        return False
    return report_sha == str(expected_cases_sha256).strip()


def _public_hf_count(payload: dict) -> int:
    rows = payload.get("public_benchmark_cases")
    if isinstance(rows, list):
        return len(rows)
    return 0


def _is_measured_dynamic_case(row: dict) -> bool:
    metric_source = str(row.get("metric_source", "")).strip().lower()
    if metric_source == "open_data_measurement":
        return True
    hf_source = row.get("hf_source")
    if isinstance(hf_source, dict):
        provider = str(hf_source.get("provider", "")).strip().lower()
        dataset = str(hf_source.get("dataset", "")).strip().lower()
        extraction = str(hf_source.get("hf_metric_extraction", "")).strip().lower()
        if provider == "open_data_measurement":
            return True
        if dataset.startswith("zenodo:") and "measured" in extraction:
            return True
    return False


def _wave_corr_from_phase_report(phase_report: dict) -> float:
    rows = phase_report.get("trajectory_head")
    if not isinstance(rows, list) or len(rows) < 4:
        return float("nan")
    ref = []
    post = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            ref.append(float(r["u_ref"]))
            post.append(float(r["u_post"]))
        except Exception:
            continue
    if len(ref) < 4:
        return float("nan")
    try:
        mu_r = statistics.fmean(ref)
        mu_p = statistics.fmean(post)
    except Exception:
        return float("nan")
    vr = sum((x - mu_r) ** 2 for x in ref)
    vp = sum((x - mu_p) ** 2 for x in post)
    if vr <= 1e-12 or vp <= 1e-12:
        return float("nan")
    cov = sum((x - mu_r) * (y - mu_p) for x, y in zip(ref, post))
    return float(cov / math.sqrt(vr * vp))


def _grade(*, commercial: bool, pre_commercial: bool, research: bool) -> str:
    if commercial:
        return "Commercial"
    if pre_commercial:
        return "Pre-Commercial"
    if research:
        return "Research"
    return "Failing"


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="megastructure_commercial_readiness",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase1.run_megastructure_commercial_readiness")
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model-cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json"
        ),
    )
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--ci-mode", choices=["pr", "nightly"], default="nightly")
    p.add_argument("--force-rerun", action="store_true")
    p.add_argument("--reuse-existing-if-present", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-gpu-strict", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--benchmark-epochs", type=int, default=120)
    p.add_argument("--benchmark-branches", type=int, default=10)
    p.add_argument("--benchmark-top-k", type=int, default=3)
    p.add_argument("--noise-epochs", type=int, default=24)
    p.add_argument("--noise-required-case-count", type=int, default=4)
    p.add_argument("--noise-sensor-levels-pct", default="0.5,1,2,5")
    p.add_argument("--noise-stiffness-levels-pct", default="0,10")
    p.add_argument("--noise-seeds", default="11,23,47")
    p.add_argument("--convergence-seeds", default="11,23,47")
    p.add_argument("--convergence-stiffness-levels-pct", default="10")
    p.add_argument("--scale-levels-pr", default="1000000,3000000")
    p.add_argument("--scale-levels-nightly", default="1000000,3000000,10000000")
    p.add_argument("--scale-levels-io", default="1000000,3000000")
    p.add_argument("--opensees-edge-list-json", default="implementation/phase1/open_data/megastructure/opensees_edges.json")
    p.add_argument("--max-drift-error-pct", type=float, default=5.0)
    p.add_argument("--max-base-shear-error-pct", type=float, default=5.0)
    p.add_argument("--min-mode-shape-mac", type=float, default=0.95)
    p.add_argument("--max-buckling-factor-error-pct", type=float, default=5.0)
    p.add_argument("--max-high-noise-drift-p95-pct", type=float, default=15.0)
    p.add_argument("--max-high-noise-base-p95-pct", type=float, default=10.0)
    p.add_argument("--min-wave-corr", type=float, default=0.90)
    p.add_argument("--max-post-phase-error-deg", type=float, default=8.0)
    p.add_argument("--max-post-lag-ms", type=float, default=8.0)
    p.add_argument("--min-ood-recall", type=float, default=0.92)
    p.add_argument("--max-ood-false-negative-ratio", type=float, default=0.08)
    p.add_argument("--max-scaleout-memory-slope", type=float, default=1.35)
    p.add_argument("--max-scaleout-latency-slope", type=float, default=1.60)
    p.add_argument("--scaleout-max-projection-ratio", type=float, default=25000.0)
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    p.add_argument("--forbid-toy-cases", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--min-source-families", type=int, default=2)
    p.add_argument("--min-measured-source-families", type=int, default=1)
    p.add_argument("--min-measured-case-count", type=int, default=3)
    p.add_argument("--require-measured-dynamic-targets", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--require-shell-beam-mix-cases", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--min-total-case-count", type=int, default=12)
    p.add_argument("--min-unique-topology-types", type=int, default=3)
    p.add_argument("--min-unique-hazard-types", type=int, default=2)
    p.add_argument("--work-dir", default="implementation/phase1/stress/commercial_readiness")
    p.add_argument("--out", default="implementation/phase1/commercial_readiness_report.json")
    args = p.parse_args()

    input_payload = {
        "model_cases": str(args.model_cases),
        "target_split": str(args.target_split),
        "ci_mode": str(args.ci_mode),
        "force_rerun": bool(args.force_rerun),
        "reuse_existing_if_present": bool(args.reuse_existing_if_present),
        "require_gpu_strict": bool(args.require_gpu_strict),
        "benchmark_epochs": int(args.benchmark_epochs),
        "benchmark_branches": int(args.benchmark_branches),
        "benchmark_top_k": int(args.benchmark_top_k),
        "noise_epochs": int(args.noise_epochs),
        "noise_required_case_count": int(args.noise_required_case_count),
        "noise_sensor_levels_pct": str(args.noise_sensor_levels_pct),
        "noise_stiffness_levels_pct": str(args.noise_stiffness_levels_pct),
        "noise_seeds": str(args.noise_seeds),
        "convergence_seeds": str(args.convergence_seeds),
        "convergence_stiffness_levels_pct": str(args.convergence_stiffness_levels_pct),
        "scale_levels_pr": str(args.scale_levels_pr),
        "scale_levels_nightly": str(args.scale_levels_nightly),
        "scale_levels_io": str(args.scale_levels_io),
        "opensees_edge_list_json": str(args.opensees_edge_list_json),
        "max_drift_error_pct": float(args.max_drift_error_pct),
        "max_base_shear_error_pct": float(args.max_base_shear_error_pct),
        "min_mode_shape_mac": float(args.min_mode_shape_mac),
        "max_buckling_factor_error_pct": float(args.max_buckling_factor_error_pct),
        "max_high_noise_drift_p95_pct": float(args.max_high_noise_drift_p95_pct),
        "max_high_noise_base_p95_pct": float(args.max_high_noise_base_p95_pct),
        "min_wave_corr": float(args.min_wave_corr),
        "max_post_phase_error_deg": float(args.max_post_phase_error_deg),
        "max_post_lag_ms": float(args.max_post_lag_ms),
        "min_ood_recall": float(args.min_ood_recall),
        "max_ood_false_negative_ratio": float(args.max_ood_false_negative_ratio),
        "max_scaleout_memory_slope": float(args.max_scaleout_memory_slope),
        "max_scaleout_latency_slope": float(args.max_scaleout_latency_slope),
        "scaleout_max_projection_ratio": float(args.scaleout_max_projection_ratio),
        "accepted_metric_sources": str(args.accepted_metric_sources),
        "forbid_toy_cases": bool(args.forbid_toy_cases),
        "min_source_families": int(args.min_source_families),
        "min_measured_source_families": int(args.min_measured_source_families),
        "min_measured_case_count": int(args.min_measured_case_count),
        "require_measured_dynamic_targets": bool(args.require_measured_dynamic_targets),
        "require_shell_beam_mix_cases": bool(args.require_shell_beam_mix_cases),
        "min_total_case_count": int(args.min_total_case_count),
        "min_unique_topology_types": int(args.min_unique_topology_types),
        "min_unique_hazard_types": int(args.min_unique_hazard_types),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    steps: list[dict] = []

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_megastructure_commercial_readiness")
        if int(args.benchmark_top_k) > int(args.benchmark_branches):
            raise ValueError("benchmark_top_k cannot exceed benchmark_branches")

        model_paths = [Path(x) for x in _parse_csv(args.model_cases)]
        if len(model_paths) < 1:
            raise ValueError("at least one model case file is required")
        accepted_sources = {x.strip() for x in str(args.accepted_metric_sources).split(",") if x.strip()}

        log_event(logger, logging.INFO, "commercial_readiness.start", model_count=len(model_paths), ci_mode=str(args.ci_mode))

        model_rows: list[dict] = []
        real_source_all_ok = True
        benchmark_all_ok = True
        noise_all_ok = True
        convergence_all_ok = True
        all_source_families: set[str] = set()
        measured_source_families: set[str] = set()
        total_shell_beam_mix_cases = 0
        total_measured_shell_beam_mix_cases = 0
        total_measured_case_count = 0
        total_case_count = 0
        global_topology_types: set[str] = set()
        global_hazard_types: set[str] = set()

        for mp in model_paths:
            label = _safe_label(mp.stem)
            mdir = work_dir / "models" / label
            mdir.mkdir(parents=True, exist_ok=True)
            bench_out = mdir / "hf_benchmark.json"
            cmp_out = mdir / "topk_comparison.json"
            noise_out = mdir / "noise_sensitivity.json"
            conv_out = mdir / "noise_convergence.json"

            cases_payload = _load_json(mp)
            toy_detected, toy_hits = _contains_toy_marker(mp, cases_payload)
            metric_ok, metric_errors, case_count = _metric_source_gate(cases_payload, accepted_sources)
            public_hf_count = _public_hf_count(cases_payload)
            case_rows = cases_payload.get("cases") if isinstance(cases_payload.get("cases"), list) else []
            source_families = sorted(
                {
                    str(r.get("source_family", "")).strip()
                    for r in case_rows
                    if isinstance(r, dict) and str(r.get("source_family", "")).strip()
                }
            )
            topology_types = sorted(
                {
                    str(r.get("topology_type", "")).strip()
                    for r in case_rows
                    if isinstance(r, dict) and str(r.get("topology_type", "")).strip()
                }
            )
            hazard_types = sorted(
                {
                    str(r.get("hazard_type", "")).strip()
                    for r in case_rows
                    if isinstance(r, dict) and str(r.get("hazard_type", "")).strip()
                }
            )
            shell_beam_mix_case_count = sum(
                1
                for r in case_rows
                if isinstance(r, dict) and str(r.get("element_mix", "unknown")).strip().lower() == "shell_beam_mix"
            )
            measured_rows = [r for r in case_rows if isinstance(r, dict) and _is_measured_dynamic_case(r)]
            measured_case_count = len(measured_rows)
            measured_row_source_families = sorted(
                {
                    str(r.get("source_family", "")).strip()
                    for r in measured_rows
                    if str(r.get("source_family", "")).strip()
                }
            )
            measured_shell_beam_mix_case_count = sum(
                1
                for r in measured_rows
                if str(r.get("element_mix", "unknown")).strip().lower() == "shell_beam_mix"
            )
            all_source_families.update(source_families)
            measured_source_families.update(measured_row_source_families)
            global_topology_types.update(topology_types)
            global_hazard_types.update(hazard_types)
            total_case_count += int(case_count)
            total_shell_beam_mix_cases += int(shell_beam_mix_case_count)
            total_measured_case_count += int(measured_case_count)
            total_measured_shell_beam_mix_cases += int(measured_shell_beam_mix_case_count)
            source_ok = bool(
                mp.exists()
                and metric_ok
                and public_hf_count >= 3
                and len(source_families) >= 1
                and (not bool(args.require_shell_beam_mix_cases) or shell_beam_mix_case_count > 0)
                and (not bool(args.forbid_toy_cases) or (not toy_detected))
            )
            source_provenance = {
                "cases_path": str(mp),
                "cases_sha256": _sha256(mp) if mp.exists() else "",
                "case_count": int(case_count),
                "public_hf_case_count": int(public_hf_count),
                "source_families": source_families,
                "source_family_count": len(source_families),
                "measured_case_count": int(measured_case_count),
                "measured_source_families": measured_row_source_families,
                "measured_source_family_count": len(measured_row_source_families),
                "measured_shell_beam_mix_case_count": int(measured_shell_beam_mix_case_count),
                "topology_type_count": len(topology_types),
                "hazard_type_count": len(hazard_types),
                "shell_beam_mix_case_count": int(shell_beam_mix_case_count),
                "toy_marker_detected": bool(toy_detected),
                "toy_marker_hits": toy_hits[:20],
                "metric_source_gate_pass": bool(metric_ok),
                "metric_source_gate_errors": metric_errors[:20],
            }

            bench_cmd = [
                sys.executable,
                "implementation/phase1/benchmark_kpi_contract.py",
                "--cases",
                str(mp),
                "--out",
                str(bench_out),
                "--comparison-out",
                str(cmp_out),
                "--target-split",
                str(args.target_split),
                "--epochs",
                str(int(args.benchmark_epochs)),
                "--branches",
                str(int(args.benchmark_branches)),
                "--top-k",
                str(int(args.benchmark_top_k)),
                "--seed",
                "23",
                "--max-drift-error-pct",
                str(float(args.max_drift_error_pct)),
                "--max-base-shear-error-pct",
                str(float(args.max_base_shear_error_pct)),
                "--min-mode-shape-mac",
                str(float(args.min_mode_shape_mac)),
                "--max-buckling-factor-error-pct",
                str(float(args.max_buckling_factor_error_pct)),
                "--require-direct-metrics",
                "--accepted-metric-sources",
                str(args.accepted_metric_sources),
            ]
            ok_bench = _run(
                step=f"benchmark_{label}",
                cmd=bench_cmd,
                report_path=bench_out,
                force_rerun=bool(args.force_rerun),
                reuse_existing_if_present=bool(args.reuse_existing_if_present),
                reuse_validator=lambda existing, expected_sha=source_provenance["cases_sha256"]: _benchmark_report_matches_cases_sha(
                    existing, expected_sha
                ),
                steps=steps,
            )

            noise_cmd = [
                sys.executable,
                "implementation/phase1/run_noise_sensitivity_stress.py",
                "--cases",
                str(mp),
                "--target-split",
                str(args.target_split),
                "--required-case-count",
                str(int(args.noise_required_case_count)),
                "--sensor-noise-levels-pct",
                str(args.noise_sensor_levels_pct),
                "--stiffness-noise-levels-pct",
                str(args.noise_stiffness_levels_pct),
                "--seeds",
                str(args.noise_seeds),
                "--epochs",
                str(int(args.noise_epochs)),
                "--branches",
                str(int(args.benchmark_branches)),
                "--top-k",
                str(int(args.benchmark_top_k)),
                "--accepted-metric-sources",
                str(args.accepted_metric_sources),
                "--out",
                str(noise_out),
            ]
            ok_noise = _run(
                step=f"noise_{label}",
                cmd=noise_cmd,
                report_path=noise_out,
                force_rerun=bool(args.force_rerun),
                reuse_existing_if_present=bool(args.reuse_existing_if_present),
                steps=steps,
            )

            conv_cmd = [
                sys.executable,
                "implementation/phase1/run_noise_convergence_gate.py",
                "--cases",
                str(mp),
                "--target-split",
                str(args.target_split),
                "--limit-cases",
                str(int(args.noise_required_case_count)),
                "--seeds",
                str(args.convergence_seeds),
                "--stiffness-noise-levels",
                str(args.convergence_stiffness_levels_pct),
                "--out",
                str(conv_out),
            ]
            ok_conv = _run(
                step=f"convergence_{label}",
                cmd=conv_cmd,
                report_path=conv_out,
                force_rerun=bool(args.force_rerun),
                reuse_existing_if_present=bool(args.reuse_existing_if_present),
                steps=steps,
            )

            bench = _load_json(bench_out)
            noise = _load_json(noise_out)
            conv = _load_json(conv_out)
            bmet = bench.get("metrics") if isinstance(bench.get("metrics"), dict) else {}
            nsum = noise.get("summary") if isinstance(noise.get("summary"), dict) else {}
            csum = conv.get("summary") if isinstance(conv.get("summary"), dict) else {}

            accuracy_ok = bool(
                ok_bench
                and bool(bench.get("contract_pass", False))
                and float(bmet.get("drift_error_pct", math.inf)) <= float(args.max_drift_error_pct)
                and float(bmet.get("base_shear_error_pct", math.inf)) <= float(args.max_base_shear_error_pct)
                and float(bmet.get("mode_shape_mac", -math.inf)) >= float(args.min_mode_shape_mac)
                and float(bmet.get("buckling_factor_error_pct", math.inf)) <= float(args.max_buckling_factor_error_pct)
            )

            noise_ok = bool(
                ok_noise
                and bool(noise.get("contract_pass", False))
                and float(nsum.get("high_noise_drift_error_pct_p95", math.inf)) <= float(args.max_high_noise_drift_p95_pct)
                and float(nsum.get("high_noise_base_shear_error_pct_p95", math.inf)) <= float(args.max_high_noise_base_p95_pct)
            )

            conv_ok = bool(
                ok_conv
                and bool(conv.get("contract_pass", False))
                and int(csum.get("fail_count", 1)) == 0
            )

            model_rows.append(
                {
                    "model_id": label,
                    "cases_path": str(mp),
                    "source_provenance": source_provenance,
                    "checks": {
                        "real_source_pass": bool(source_ok),
                        "accuracy_pass": bool(accuracy_ok),
                        "noise_robustness_pass": bool(noise_ok),
                        "noise_convergence_pass": bool(conv_ok),
                    },
                    "metrics": {
                        "drift_error_pct": float(bmet.get("drift_error_pct", math.inf)),
                        "base_shear_error_pct": float(bmet.get("base_shear_error_pct", math.inf)),
                        "mode_shape_mac": float(bmet.get("mode_shape_mac", -math.inf)),
                        "buckling_factor_error_pct": float(bmet.get("buckling_factor_error_pct", math.inf)),
                        "high_noise_drift_error_pct_p95": float(nsum.get("high_noise_drift_error_pct_p95", math.inf)),
                        "high_noise_base_shear_error_pct_p95": float(nsum.get("high_noise_base_shear_error_pct_p95", math.inf)),
                        "noise_convergence_fail_count": int(csum.get("fail_count", 1)),
                    },
                    "reports": {
                        "benchmark": str(bench_out),
                        "comparison": str(cmp_out),
                        "noise_sensitivity": str(noise_out),
                        "noise_convergence": str(conv_out),
                    },
                }
            )

            real_source_all_ok = bool(real_source_all_ok and source_ok)
            benchmark_all_ok = bool(benchmark_all_ok and accuracy_ok)
            noise_all_ok = bool(noise_all_ok and noise_ok)
            convergence_all_ok = bool(convergence_all_ok and conv_ok)

        source_family_gate_ok = bool(len(all_source_families) >= int(args.min_source_families))
        measured_source_family_gate_ok = bool(
            (not bool(args.require_measured_dynamic_targets))
            or len(measured_source_families) >= int(args.min_measured_source_families)
        )
        measured_case_gate_ok = bool(
            (not bool(args.require_measured_dynamic_targets))
            or total_measured_case_count >= int(args.min_measured_case_count)
        )
        measured_dynamic_target_gate_ok = bool(
            (not bool(args.require_measured_dynamic_targets))
            or (total_measured_case_count > 0 and len(measured_source_families) > 0)
        )
        shell_beam_mix_gate_ok = bool((not bool(args.require_shell_beam_mix_cases)) or total_shell_beam_mix_cases > 0)
        case_count_gate_ok = bool(total_case_count >= int(args.min_total_case_count))
        topology_diversity_gate_ok = bool(len(global_topology_types) >= int(args.min_unique_topology_types))
        hazard_diversity_gate_ok = bool(len(global_hazard_types) >= int(args.min_unique_hazard_types))
        benchmark_breadth_gate_ok = bool(
            source_family_gate_ok
            and measured_source_family_gate_ok
            and measured_case_gate_ok
            and measured_dynamic_target_gate_ok
            and shell_beam_mix_gate_ok
            and case_count_gate_ok
            and topology_diversity_gate_ok
            and hazard_diversity_gate_ok
        )

        phase_out = work_dir / "phase_correction_assimilation_report.json"
        phase_cmd = [
            sys.executable,
            "implementation/phase1/phase_correction_assimilation.py",
            "--max-post-phase-error-deg",
            str(float(args.max_post_phase_error_deg)),
            "--max-post-lag-ms",
            str(float(args.max_post_lag_ms)),
            "--out",
            str(phase_out),
        ]
        ok_phase = _run(
            step="phase_correction",
            cmd=phase_cmd,
            report_path=phase_out,
            force_rerun=bool(args.force_rerun),
            reuse_existing_if_present=bool(args.reuse_existing_if_present),
            steps=steps,
        )
        phase = _load_json(phase_out)
        phase_metrics = phase.get("metrics") if isinstance(phase.get("metrics"), dict) else {}
        wave_corr = _wave_corr_from_phase_report(phase)
        phase_ok = bool(
            ok_phase
            and bool(phase.get("contract_pass", False))
            and float(phase_metrics.get("post_phase_error_deg", math.inf)) <= float(args.max_post_phase_error_deg)
            and abs(float(phase_metrics.get("post_time_lag_ms", math.inf))) <= float(args.max_post_lag_ms)
            and math.isfinite(wave_corr)
            and float(wave_corr) >= float(args.min_wave_corr)
        )

        ood_out = work_dir / "heterogeneous_soil_ood_report.json"
        ood_cmd = [
            sys.executable,
            "implementation/phase1/heterogeneous_soil_ood_gate.py",
            "--min-recall",
            str(float(args.min_ood_recall)),
            "--max-false-negative-ratio",
            str(float(args.max_ood_false_negative_ratio)),
            "--out",
            str(ood_out),
        ]
        ok_ood = _run(
            step="soil_ood",
            cmd=ood_cmd,
            report_path=ood_out,
            force_rerun=bool(args.force_rerun),
            reuse_existing_if_present=bool(args.reuse_existing_if_present),
            steps=steps,
        )
        ood = _load_json(ood_out)
        ood_metrics = ood.get("metrics") if isinstance(ood.get("metrics"), dict) else {}
        ood_ok = bool(
            ok_ood
            and bool(ood.get("contract_pass", False))
            and float(ood_metrics.get("recall", 0.0)) >= float(args.min_ood_recall)
            and float(ood_metrics.get("false_negative_ratio", math.inf)) <= float(args.max_ood_false_negative_ratio)
        )

        f1_out = work_dir / "multiscale_l3_streaming_report.json"
        f1_cmd = [
            sys.executable,
            "implementation/phase1/multiscale_l3_streaming_profile.py",
            "--out",
            str(f1_out),
        ]
        ok_f1 = _run(
            step="multiscale_l3",
            cmd=f1_cmd,
            report_path=f1_out,
            force_rerun=bool(args.force_rerun),
            reuse_existing_if_present=bool(args.reuse_existing_if_present),
            steps=steps,
        )
        f1 = _load_json(f1_out)
        f1_ok = bool(ok_f1 and bool(f1.get("contract_pass", False)))

        part_out = work_dir / "partitioned_scaleout_report.json"
        dof_levels = str(args.scale_levels_pr) if str(args.ci_mode) == "pr" else str(args.scale_levels_nightly)
        part_cmd = [
            sys.executable,
            "implementation/phase1/run_partitioned_scaleout.py",
            "--dof-levels",
            dof_levels,
            "--branches",
            "64",
            "--chunk-candidates",
            "64,32,16,8,4,2,1",
            "--ci-mode",
            str(args.ci_mode),
            "--edge-list-json",
            str(args.opensees_edge_list_json),
            "--require-real-graph",
            "--max-projection-ratio",
            str(float(args.scaleout_max_projection_ratio)),
            "--out",
            str(part_out),
        ]
        if bool(args.require_gpu_strict):
            part_cmd.append("--gpu-strict")
        ok_part = _run(
            step="partitioned_scaleout",
            cmd=part_cmd,
            report_path=part_out,
            force_rerun=bool(args.force_rerun),
            reuse_existing_if_present=bool(args.reuse_existing_if_present),
            steps=steps,
        )
        part = _load_json(part_out)
        cpx = part.get("complexity_regression") if isinstance(part.get("complexity_regression"), dict) else {}
        part_checks = part.get("checks") if isinstance(part.get("checks"), dict) else {}
        mem_slope = float(cpx.get("memory_loglog_slope", math.inf))
        lat_slope = float(cpx.get("latency_loglog_slope", math.inf))
        mode_scale_pass_key = "pr_scale_pass" if str(args.ci_mode) == "pr" else "nightly_scale_pass"
        part_ok = bool(
            ok_part
            and bool(part.get("contract_pass", False))
            and bool(part_checks.get(mode_scale_pass_key, False))
            and bool(part_checks.get("real_graph_used", False))
            and math.isfinite(mem_slope)
            and math.isfinite(lat_slope)
            and mem_slope <= float(args.max_scaleout_memory_slope)
            and lat_slope <= float(args.max_scaleout_latency_slope)
        )

        scaleout_io_out = work_dir / "scaleout_io_profile_report.json"
        scaleout_cmd = [
            sys.executable,
            "implementation/phase1/run_scaleout_io_profile.py",
            "--runtime-hook-cmd",
            "python3 implementation/phase1/rust_hip_md3bead_hook.py",
            "--producer-cmd",
            "python3 implementation/phase1/rust_hip_md3bead_hook.py",
            "--dof-levels",
            str(args.scale_levels_io),
            "--out",
            str(scaleout_io_out),
        ]
        if bool(args.require_gpu_strict):
            scaleout_cmd.append("--gpu-strict")
        ok_scale_io = _run(
            step="scaleout_io",
            cmd=scaleout_cmd,
            report_path=scaleout_io_out,
            force_rerun=bool(args.force_rerun),
            reuse_existing_if_present=bool(args.reuse_existing_if_present),
            steps=steps,
        )
        scaleout_io = _load_json(scaleout_io_out)
        scale_checks = scaleout_io.get("checks") if isinstance(scaleout_io.get("checks"), dict) else {}
        scaleout_io_ok = bool(
            ok_scale_io
            and bool(scaleout_io.get("contract_pass", False))
            and bool(scale_checks.get("probe_pass", False))
            and bool(scale_checks.get("has_1m_plus", False))
            and bool(scale_checks.get("scaleout_1m_microbatch_pass", False))
        )
        gpu_strict_ok = bool(
            (not bool(args.require_gpu_strict))
            or (
                bool(scale_checks.get("gpu_strict_pass", False))
                and bool(part_checks.get("gpu_strict_pass", False))
            )
        )
        scaleout_ok = bool(f1_ok and part_ok and scaleout_io_ok)

        checks = {
            "real_source_pass": bool(
                real_source_all_ok
                and benchmark_breadth_gate_ok
            ),
            "benchmark_breadth_pass": bool(benchmark_breadth_gate_ok),
            "source_family_pass": bool(source_family_gate_ok),
            "measured_dynamic_targets_pass": bool(measured_dynamic_target_gate_ok),
            "measured_source_family_pass": bool(measured_source_family_gate_ok),
            "measured_case_count_pass": bool(measured_case_gate_ok),
            "shell_beam_mix_pass": bool(shell_beam_mix_gate_ok),
            "case_count_pass": bool(case_count_gate_ok),
            "topology_diversity_pass": bool(topology_diversity_gate_ok),
            "hazard_diversity_pass": bool(hazard_diversity_gate_ok),
            "accuracy_pass": bool(benchmark_all_ok),
            "noise_robustness_pass": bool(noise_all_ok),
            "noise_convergence_pass": bool(convergence_all_ok),
            "phase_dynamics_pass": bool(phase_ok),
            "ood_safety_pass": bool(ood_ok),
            "scaleout_pass": bool(scaleout_ok),
            "gpu_strict_pass": bool(gpu_strict_ok),
            "on_scaling_regression_pass": bool(
                math.isfinite(mem_slope)
                and math.isfinite(lat_slope)
                and mem_slope <= float(args.max_scaleout_memory_slope)
                and lat_slope <= float(args.max_scaleout_latency_slope)
            ),
        }

        research_pass = bool(checks["real_source_pass"] and checks["accuracy_pass"])
        pre_commercial_pass = bool(research_pass and checks["noise_robustness_pass"] and checks["noise_convergence_pass"] and checks["scaleout_pass"] and checks["gpu_strict_pass"])
        commercial_pass = bool(pre_commercial_pass and checks["phase_dynamics_pass"] and checks["ood_safety_pass"] and checks["on_scaling_regression_pass"])

        if not checks["real_source_pass"]:
            reason_code = "ERR_REAL_SOURCE_FAIL"
        elif not checks["accuracy_pass"]:
            reason_code = "ERR_BENCHMARK_FAIL"
        elif not checks["noise_robustness_pass"]:
            reason_code = "ERR_NOISE_ROBUSTNESS_FAIL"
        elif not checks["noise_convergence_pass"]:
            reason_code = "ERR_NOISE_CONVERGENCE_FAIL"
        elif not checks["phase_dynamics_pass"]:
            reason_code = "ERR_PHASE_DYNAMICS_FAIL"
        elif not checks["ood_safety_pass"]:
            reason_code = "ERR_OOD_FAIL"
        elif not checks["scaleout_pass"]:
            reason_code = "ERR_SCALEOUT_FAIL"
        elif not checks["gpu_strict_pass"]:
            reason_code = "ERR_GPU_STRICT_FAIL"
        elif not commercial_pass:
            reason_code = "ERR_COMMERCIAL_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-megastructure-commercial-readiness",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "grade": {
                "label": _grade(
                    commercial=bool(commercial_pass),
                    pre_commercial=bool(pre_commercial_pass),
                    research=bool(research_pass),
                ),
                "research_pass": bool(research_pass),
                "pre_commercial_pass": bool(pre_commercial_pass),
                "commercial_pass": bool(commercial_pass),
            },
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": bool(commercial_pass),
                "full_commercial_replacement_ready": False,
                "recommended_use": (
                    "Use this engine to automate the dominant, time-consuming 95-99% of repeated analysis, "
                    "screening, packaging, and optimization workflows. Keep the residual 1-5% under licensed "
                    "engineer review, legacy-tool cross-check, and formal sign-off workflows."
                ),
            },
            "residual_holdout_categories": [
                {
                    "id": "licensed_engineer_review_required",
                    "owner": "기술사",
                    "label": "Licensed Engineer Review",
                    "scope": "non-standard interpretation, final judgment, exceptional irregularity, and member-level edge cases",
                },
                {
                    "id": "legacy_tool_cross_validation_required",
                    "owner": "기존툴+기술사",
                    "label": "Legacy Tool Cross-Validation",
                    "scope": "novel load paths, authority-critical submodels, and residual niche workflows outside the accelerated envelope",
                },
                {
                    "id": "legal_authority_signoff_required",
                    "owner": "기술사/기존 승인 workflow",
                    "label": "Legal Sign-Off",
                    "scope": "formal seal, legal submission, and authority-facing responsibility that remains outside automated scope",
                },
            ],
            "model_rows": model_rows,
            "global_metrics": {
                "source_family_count": len(all_source_families),
                "source_families": sorted(all_source_families),
                "measured_source_family_count": len(measured_source_families),
                "measured_source_families": sorted(measured_source_families),
                "measured_case_count": int(total_measured_case_count),
                "total_case_count": int(total_case_count),
                "topology_type_count": len(global_topology_types),
                "topology_types": sorted(global_topology_types),
                "hazard_type_count": len(global_hazard_types),
                "hazard_types": sorted(global_hazard_types),
                "shell_beam_mix_case_count": int(total_shell_beam_mix_cases),
                "measured_shell_beam_mix_case_count": int(total_measured_shell_beam_mix_cases),
                "wave_corr_post": float(wave_corr) if math.isfinite(wave_corr) else None,
                "post_phase_error_deg": float(phase_metrics.get("post_phase_error_deg", math.inf)),
                "post_time_lag_ms": float(phase_metrics.get("post_time_lag_ms", math.inf)),
                "ood_recall": float(ood_metrics.get("recall", math.nan)),
                "ood_false_negative_ratio": float(ood_metrics.get("false_negative_ratio", math.nan)),
                "scaleout_memory_loglog_slope": float(mem_slope) if math.isfinite(mem_slope) else None,
                "scaleout_latency_loglog_slope": float(lat_slope) if math.isfinite(lat_slope) else None,
            },
            "reports": {
                "phase_dynamics": str(phase_out),
                "soil_ood": str(ood_out),
                "multiscale_l3": str(f1_out),
                "partitioned_scaleout": str(part_out),
                "scaleout_io": str(scaleout_io_out),
            },
            "steps": steps,
            "contract_pass": bool(reason_code == "PASS"),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive(
            [str(out), str(work_dir), str(phase_out), str(ood_out), str(f1_out), str(part_out), str(scaleout_io_out)]
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "commercial_readiness.completed", reason_code=reason_code, grade=payload["grade"]["label"])
        print(f"Wrote commercial readiness report: {out}")
        if reason_code != "PASS":
            raise SystemExit(1)

    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-megastructure-commercial-readiness",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "steps": steps,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote commercial readiness report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
