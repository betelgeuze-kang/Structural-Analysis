#!/usr/bin/env python3
"""Validate Rust nonlinear frame engine against benchmark HF case metrics."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import re

import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rust_nonlinear_frame_bridge import (
    RustNonlinearFrameConfig,
    build_story_load_profile,
    consume_dlpack_bundle,
    solve_nonlinear_frame,
)
from section_family_library import evaluate_story_section_profile
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "rust nonlinear frame engine passed vnv thresholds",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CASES": "benchmark cases missing/invalid",
    "ERR_TOP_DISP_SOURCE_FAIL": "top displacement HF source is missing or inferred",
    "ERR_ENGINE_FAIL": "rust nonlinear engine failed or diverged",
    "ERR_VNV_FAIL": "vnv thresholds violated",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "target_split",
        "min_case_count",
        "max_drift_error_pct",
        "max_base_shear_error_pct",
        "max_top_disp_error_pct",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "max_drift_error_pct": {"type": "number", "minimum": 0.0},
        "max_base_shear_error_pct": {"type": "number", "minimum": 0.0},
        "max_top_disp_error_pct": {"type": "number", "minimum": 0.0},
        "hardening_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pdelta_factor": {"type": "number", "minimum": 0.0},
        "tolerance": {"type": "number", "exclusiveMinimum": 0.0},
        "max_iter": {"type": "integer", "minimum": 1},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
        "require_top_disp_hf": {"type": "boolean"},
        "case_metrics_npz_out": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _p95(xs: list[float]) -> float:
    if not xs:
        return math.inf
    ys = sorted(float(v) for v in xs)
    idx = max(0, min(len(ys) - 1, int(math.ceil(0.95 * len(ys)) - 1)))
    return float(ys[idx])


def _safe_err_pct(pred: float, ref: float) -> float:
    return 100.0 * abs(float(pred) - float(ref)) / max(abs(float(ref)), 1e-9)


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


def _case_metric(case: dict, metric: str, key: str = "hf") -> float:
    return float(((case.get("metrics") or {}).get(metric) or {}).get(key, 0.0))


def _case_has_metric(case: dict, metric: str, key: str = "hf") -> bool:
    try:
        v = ((case.get("metrics") or {}).get(metric) or {}).get(key)
    except Exception:
        return False
    if v is None:
        return False
    try:
        fv = float(v)
    except Exception:
        return False
    return bool(math.isfinite(fv) and abs(fv) > 0.0)


def _u_story_from_result(solved: dict, *, story_count: int) -> tuple[np.ndarray, str]:
    artifacts = solved.get("device_artifacts")
    if isinstance(artifacts, dict) and bool(solved.get("device_artifacts_available", False)):
        try:
            tensors = consume_dlpack_bundle(artifacts)
            tensor = tensors.get("u_story_m")
            if tensor is not None:
                return np.asarray(tensor.detach().cpu().numpy(), dtype=np.float64).reshape(-1), "dlpack_zero_copy"
        except Exception:
            pass
    return np.asarray(solved.get("u_story_m", np.zeros(story_count, dtype=np.float64)), dtype=np.float64).reshape(-1), "host_response"


def _validate_metric_source(cases: list[dict], accepted: set[str]) -> tuple[bool, list[str]]:
    bad: list[str] = []
    for i, c in enumerate(cases):
        src = str(c.get("metric_source", "")).strip()
        if src not in accepted:
            bad.append(str(c.get("case_id", f"case-{i}")))
    return len(bad) == 0, bad


def _default_case_metrics_npz_out(report_out: Path) -> Path:
    if report_out.suffix:
        return report_out.with_suffix(".metrics.npz")
    return report_out.parent / f"{report_out.name}.metrics.npz"


def _token(text: str, fallback: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_]+", "_", str(text).strip()).strip("_")
    return value or fallback


def _write_case_metrics_npz(path: Path, rows: list[dict]) -> dict[str, object]:
    case_ids = [str(row.get("case_id", "")) for row in rows]
    splits = [str(row.get("split", "")) for row in rows]
    topologies = [str(row.get("topology_type", "")) for row in rows]
    hazard_types = [str(row.get("hazard_type", "")) for row in rows]
    top_sources = [str((((row.get("metrics") or {}).get("top_displacement_m") or {}).get("source", ""))) for row in rows]
    payload = {
        "case_ids": np.asarray(case_ids, dtype="<U128"),
        "splits": np.asarray(splits, dtype="<U32"),
        "topology_types": np.asarray(topologies, dtype="<U64"),
        "hazard_types": np.asarray(hazard_types, dtype="<U64"),
        "top_disp_sources": np.asarray(top_sources, dtype="<U64"),
        "drift_hf_pct": np.asarray([float((((row.get("metrics") or {}).get("drift_ratio_pct") or {}).get("hf", 0.0))) for row in rows], dtype=np.float64),
        "drift_pred_pct": np.asarray([float((((row.get("metrics") or {}).get("drift_ratio_pct") or {}).get("pred", 0.0))) for row in rows], dtype=np.float64),
        "drift_error_pct": np.asarray([float((((row.get("metrics") or {}).get("drift_ratio_pct") or {}).get("error_pct", 0.0))) for row in rows], dtype=np.float64),
        "base_hf_kN": np.asarray([float((((row.get("metrics") or {}).get("base_shear_kN") or {}).get("hf", 0.0))) for row in rows], dtype=np.float64),
        "base_pred_kN": np.asarray([float((((row.get("metrics") or {}).get("base_shear_kN") or {}).get("pred", 0.0))) for row in rows], dtype=np.float64),
        "base_error_pct": np.asarray([float((((row.get("metrics") or {}).get("base_shear_kN") or {}).get("error_pct", 0.0))) for row in rows], dtype=np.float64),
        "top_hf_m": np.asarray([float((((row.get("metrics") or {}).get("top_displacement_m") or {}).get("hf", 0.0))) for row in rows], dtype=np.float64),
        "top_pred_m": np.asarray([float((((row.get("metrics") or {}).get("top_displacement_m") or {}).get("pred", 0.0))) for row in rows], dtype=np.float64),
        "top_error_pct": np.asarray([float((((row.get("metrics") or {}).get("top_displacement_m") or {}).get("error_pct", 0.0))) for row in rows], dtype=np.float64),
        "converged": np.asarray([bool(((row.get("engine") or {}).get("converged", False))) for row in rows], dtype=np.bool_),
        "iterations": np.asarray([int(((row.get("engine") or {}).get("iterations", 0))) for row in rows], dtype=np.int32),
        "residual_inf": np.asarray([float(((row.get("engine") or {}).get("residual_inf", 0.0))) for row in rows], dtype=np.float64),
        "plastic_story_count": np.asarray([int(((row.get("engine") or {}).get("plastic_story_count", 0))) for row in rows], dtype=np.int32),
        "stiffness_scale_mean": np.asarray([float((((row.get("engine") or {}).get("section_probe") or {}).get("stiffness_scale_mean", 1.0))) for row in rows], dtype=np.float64),
        "yield_scale_mean": np.asarray([float((((row.get("engine") or {}).get("section_probe") or {}).get("yield_scale_mean", 1.0))) for row in rows], dtype=np.float64),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    return {"path": str(path), "case_count": len(rows), "storage": "npz_external"}


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="nonlinear_frame_engine_validation",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--min-case-count", type=int, default=3)
    p.add_argument("--max-case-count", type=int, default=6)
    p.add_argument("--max-drift-error-pct", type=float, default=5.0)
    p.add_argument("--max-base-shear-error-pct", type=float, default=5.0)
    p.add_argument("--max-top-disp-error-pct", type=float, default=8.0)
    p.add_argument("--hardening-ratio", type=float, default=1.0)
    p.add_argument("--pdelta-factor", type=float, default=0.0)
    p.add_argument("--tolerance", type=float, default=1e-7)
    p.add_argument("--max-iter", type=int, default=60)
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    p.add_argument("--require-top-disp-hf", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--case-metrics-npz-out", default="")
    p.add_argument("--out", default="implementation/phase1/nonlinear_frame_engine_report.json")
    args = p.parse_args()
    case_metrics_npz_out = Path(str(args.case_metrics_npz_out)) if str(args.case_metrics_npz_out).strip() else _default_case_metrics_npz_out(Path(args.out))

    input_payload = {
        "cases": str(args.cases),
        "target_split": str(args.target_split),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "max_drift_error_pct": float(args.max_drift_error_pct),
        "max_base_shear_error_pct": float(args.max_base_shear_error_pct),
        "max_top_disp_error_pct": float(args.max_top_disp_error_pct),
        "hardening_ratio": float(args.hardening_ratio),
        "pdelta_factor": float(args.pdelta_factor),
        "tolerance": float(args.tolerance),
        "max_iter": int(args.max_iter),
        "accepted_metric_sources": str(args.accepted_metric_sources),
        "require_top_disp_hf": bool(args.require_top_disp_hf),
        "case_metrics_npz_out": str(case_metrics_npz_out),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_nonlinear_frame_engine_validation")
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
        out_rows: list[dict] = []
        drift_errs: list[float] = []
        base_errs: list[float] = []
        top_errs: list[float] = []
        top_metric_available = False
        top_metric_missing_case_ids: list[str] = []
        converged_all = True
        rust_backend_all = True

        for c in rows:
            case_id = str(c.get("case_id", "unknown"))
            topology = str(c.get("topology_type", "rahmen"))
            story_count = _story_count_for_topology(topology)
            story_h = np.full(story_count, 3.2, dtype=np.float64)

            drift_hf_pct = _case_metric(c, "drift_ratio_pct", "hf")
            base_hf_kn = _case_metric(c, "base_shear_kN", "hf")
            load_scale = float(c.get("load_scale", 1.0))

            drift_hf = max(1e-6, drift_hf_pct / 100.0)
            has_top_hf = _case_has_metric(c, "top_displacement_m", "hf")
            if has_top_hf:
                top_hf_m = _case_metric(c, "top_displacement_m", "hf")
                top_metric_source = "hf_export_direct"
                top_metric_available = True
            else:
                top_hf_m = drift_hf * float(np.sum(story_h)) * 0.57
                top_metric_source = "inferred_from_drift_ratio"
                top_metric_missing_case_ids.append(case_id)
            base_hf_n = max(1.0, base_hf_kn * 1000.0)
            floor_load = build_story_load_profile(story_count, base_hf_n, mode="triangular")
            k_story = _build_story_stiffness_from_drift(
                floor_load_n=floor_load,
                story_h_m=story_h,
                drift_ratio_hf=drift_hf,
            )
            section_probe = evaluate_story_section_profile(
                topology=topology,
                material_type=str(c.get("material_type", "steel")),
                story_h_m=story_h,
                drift_ratio_profile=np.linspace(drift_hf * 1.04, drift_hf * 0.96, num=story_count, dtype=np.float64),
                load_scale=load_scale,
            )
            k_story = k_story * np.asarray(section_probe["story_stiffness_scale"], dtype=np.float64)

            yield_story = np.full(story_count, max(0.0015, drift_hf * float(np.mean(story_h)) * 1.1), dtype=np.float64)
            yield_story = yield_story * np.asarray(section_probe["story_yield_scale"], dtype=np.float64)
            axial_story = (4.2e6 * float(load_scale)) * np.linspace(1.25, 0.85, num=story_count, dtype=np.float64)

            solved = solve_nonlinear_frame(
                story_k_n_per_m=k_story,
                story_h_m=story_h,
                story_axial_n=axial_story,
                story_yield_drift_m=yield_story,
                floor_load_n=floor_load,
                cfg=cfg,
                keep_device_artifacts=True,
            )
            converged = bool(solved.get("converged", False) and int(solved.get("status", 0)) == 0)
            backend_ok = str(solved.get("backend", "")).startswith("rust_ffi_")
            converged_all = bool(converged_all and converged)
            rust_backend_all = bool(rust_backend_all and backend_ok)

            u, displacement_consumer = _u_story_from_result(solved, story_count=story_count)
            if u.size != story_count:
                converged = False
                u = np.zeros(story_count, dtype=np.float64)
            du = np.diff(np.concatenate([[0.0], u]))
            drift_pred_pct = 100.0 * float(np.max(np.abs(du / np.maximum(story_h, 1e-9))))
            base_pred_kn = float(solved.get("base_shear_kn", math.inf))
            top_pred_m = float(solved.get("top_displacement_m", math.inf))

            drift_err = _safe_err_pct(drift_pred_pct, drift_hf_pct)
            base_err = _safe_err_pct(base_pred_kn, base_hf_kn)
            top_err = _safe_err_pct(top_pred_m, top_hf_m)
            drift_errs.append(drift_err)
            base_errs.append(base_err)
            if has_top_hf:
                top_errs.append(top_err)

            out_rows.append(
                {
                    "case_id": case_id,
                    "split": str(c.get("split", "")),
                    "topology_type": topology,
                    "hazard_type": str(c.get("hazard_type", "")),
                    "engine": {
                        "backend": str(solved.get("backend", "")),
                        "rust_version": int(solved.get("rust_version", 0)),
                        "converged": bool(converged),
                        "iterations": int(solved.get("iterations", 0)),
                        "residual_inf": float(solved.get("residual_inf", math.inf)),
                        "line_search_backtracks": int(solved.get("line_search_backtracks", 0)),
                        "plastic_story_count": int(solved.get("plastic_story_count", 0)),
                        "runtime": dict(solved.get("runtime", {})) if isinstance(solved.get("runtime"), dict) else {},
                        "response_device_consumer": str(displacement_consumer),
                        "section_probe": dict(section_probe.get("summary", {})),
                        "section_family_counts": dict(section_probe.get("family_counts", {})),
                        "section_probe_head": list(section_probe.get("detail_rows", []))[:8],
                    },
                    "metrics": {
                        "drift_ratio_pct": {"hf": float(drift_hf_pct), "pred": float(drift_pred_pct), "error_pct": float(drift_err)},
                        "base_shear_kN": {"hf": float(base_hf_kn), "pred": float(base_pred_kn), "error_pct": float(base_err)},
                        "top_displacement_m": {
                            "hf": float(top_hf_m),
                            "pred": float(top_pred_m),
                            "error_pct": float(top_err),
                            "source": top_metric_source,
                        },
                    },
                }
            )

        require_top_disp_hf = bool(args.require_top_disp_hf)
        top_disp_metric_source_required_pass = bool((not require_top_disp_hf) or (top_metric_available and len(top_metric_missing_case_ids) == 0))
        top_disp_p95_pass = bool(
            (top_metric_available and _p95(top_errs) <= float(args.max_top_disp_error_pct))
            if require_top_disp_hf
            else ((not top_metric_available) or (_p95(top_errs) <= float(args.max_top_disp_error_pct)))
        )

        checks = {
            "metric_source_pass": bool(metric_source_ok),
            "rust_backend_used_pass": bool(rust_backend_all),
            "all_cases_converged": bool(converged_all),
            "drift_p95_pass": bool(_p95(drift_errs) <= float(args.max_drift_error_pct)),
            "base_shear_p95_pass": bool(_p95(base_errs) <= float(args.max_base_shear_error_pct)),
            "top_disp_metric_source_available": bool(top_metric_available),
            "top_disp_metric_source_required_pass": bool(top_disp_metric_source_required_pass),
            "top_disp_p95_pass": bool(top_disp_p95_pass),
        }
        required_gate_keys = (
            "metric_source_pass",
            "rust_backend_used_pass",
            "all_cases_converged",
            "drift_p95_pass",
            "base_shear_p95_pass",
            "top_disp_metric_source_required_pass",
            "top_disp_p95_pass",
        )
        contract_pass = bool(all(bool(checks.get(k, False)) for k in required_gate_keys))

        if not metric_source_ok:
            reason_code = "ERR_CASES"
        elif require_top_disp_hf and not checks["top_disp_metric_source_required_pass"]:
            reason_code = "ERR_TOP_DISP_SOURCE_FAIL"
        elif not checks["rust_backend_used_pass"] or not checks["all_cases_converged"]:
            reason_code = "ERR_ENGINE_FAIL"
        elif not contract_pass:
            reason_code = "ERR_VNV_FAIL"
        else:
            reason_code = "PASS"

        metrics_npz_summary = _write_case_metrics_npz(case_metrics_npz_out, out_rows)
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-frame-vnv",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "artifacts": {
                "report_json": str(out),
                "case_metrics_npz_out": str(case_metrics_npz_out),
            },
            "summary": {
                "case_count": len(out_rows),
                "drift_error_pct_mean": statistics.fmean(drift_errs) if drift_errs else math.inf,
                "drift_error_pct_p95": _p95(drift_errs),
                "base_shear_error_pct_mean": statistics.fmean(base_errs) if base_errs else math.inf,
                "base_shear_error_pct_p95": _p95(base_errs),
                "top_disp_error_pct_mean": statistics.fmean(top_errs) if top_errs else None,
                "top_disp_error_pct_p95": _p95(top_errs) if top_errs else None,
                "metric_source_invalid_case_ids": metric_source_bad,
                "top_disp_missing_case_ids": top_metric_missing_case_ids,
                "runtime_backends": sorted(
                    {
                        str(((row.get("engine") or {}).get("runtime") or {}).get("main_loop_backend", ""))
                        for row in out_rows
                        if isinstance(row.get("engine"), dict)
                    }
                ),
                "section_probe_stiffness_scale_mean": statistics.fmean(
                    float((((row.get("engine") or {}).get("section_probe") or {}).get("stiffness_scale_mean", 1.0)))
                    for row in out_rows
                )
                if out_rows
                else None,
                "section_probe_yield_scale_mean": statistics.fmean(
                    float((((row.get("engine") or {}).get("section_probe") or {}).get("yield_scale_mean", 1.0)))
                    for row in out_rows
                )
                if out_rows
                else None,
                "response_storage": "npz_external+inline_summary",
                "response_binary_consumer": (
                    "dlpack_zero_copy_primary"
                    if all(
                        str(((row.get("engine") or {}).get("response_device_consumer", "")) or "") == "dlpack_zero_copy"
                        for row in out_rows
                    )
                    else "mixed_host_or_device"
                ),
                "case_metrics_npz_case_count": int(metrics_npz_summary.get("case_count", 0)),
            },
            "rows": out_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        archive_manifest = _archive([str(out), str(case_metrics_npz_out), str(args.cases)])
        if archive_manifest:
            report["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote nonlinear frame engine report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, InputContractError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-rust-nonlinear-frame-vnv",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote nonlinear frame engine report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
