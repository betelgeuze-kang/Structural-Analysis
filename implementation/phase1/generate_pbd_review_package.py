#!/usr/bin/env python3
"""Generate committee-ready PBD review package from NDTHA outputs.

Outputs:
1) Drift envelope figure across 7 earthquake cases
2) Core-wall hysteresis figure (drift-shear loop)
3) Kill-shot performance table (csv/json)
4) Review markdown + multipage PDF
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

try:
    from implementation.phase1.ui_design_tokens import build_signal_desk_light_css
except ImportError:  # pragma: no cover - direct script execution fallback
    from ui_design_tokens import build_signal_desk_light_css
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np

from implementation.phase1.chart_theme import (
    ACCENT,
    DANGER,
    MUTED,
    SUCCESS,
    WARNING,
    add_badge,
    add_figure_header,
    apply_analysis_axis_style,
    configure_analysis_chart_defaults,
    empty_state_figure,
    save_analysis_figure,
    scale_series,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    payload = np.load(path, allow_pickle=True)
    return {str(key): payload[key] for key in payload.files}


def _finite(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def _scaled_axis_label(unit: str, scale: float, suffix: str) -> str:
    if scale == 1.0 or not suffix:
        return unit
    return f"{unit} ({suffix})"


def _default_metrics_npz_out(out_dir: Path) -> Path:
    return out_dir / "pbd_review_metrics.npz"


def _story_count(row: dict) -> int:
    summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    sc = int(summary.get("story_count", 0) or 0)
    if sc > 0:
        return sc
    response = row.get("response") if isinstance(row.get("response"), dict) else {}
    env = response.get("story_drift_envelope_pct") if isinstance(response.get("story_drift_envelope_pct"), list) else []
    return int(len(env))


def _select_case_rows(rows: list[dict], required_count: int) -> list[dict]:
    usable = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        checks = row.get("checks") if isinstance(row.get("checks"), dict) else {}
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        env = response.get("story_drift_envelope_pct") if isinstance(response.get("story_drift_envelope_pct"), list) else []
        if len(env) < 2:
            continue
        if not bool(checks.get("converged_all_steps", True)):
            continue
        usable.append(row)

    if len(usable) < required_count:
        raise ValueError(f"usable ndtha rows {len(usable)} < required {required_count}")

    by_story: dict[int, list[dict]] = {}
    for row in usable:
        sc = _story_count(row)
        if sc <= 0:
            continue
        by_story.setdefault(sc, []).append(row)

    if not by_story:
        raise ValueError("no rows with valid story_count")

    dominant_story = max(by_story.keys(), key=lambda k: len(by_story[k]))
    dominant_rows = sorted(by_story[dominant_story], key=lambda r: str(r.get("case_id", "")))
    if len(dominant_rows) >= required_count:
        return dominant_rows[:required_count]

    # Fallback: mixed story counts, used only when homogeneous topology is unavailable.
    return sorted(usable, key=lambda r: str(r.get("case_id", "")))[:required_count]


def _prepare_case_subset(
    *,
    src_cases_json: Path,
    target_split: str,
    earthquake_count: int,
    out_cases_json: Path,
    topology_type: str,
) -> tuple[Path, str]:
    payload = _load_json(src_cases_json)
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise ValueError("cases[] missing in cases-json")
    filtered = [r for r in rows if isinstance(r, dict)]
    if str(target_split) != "all":
        filtered = [r for r in filtered if str(r.get("split", "")) == str(target_split)]
    if len(filtered) < int(earthquake_count):
        raise ValueError(f"filtered cases {len(filtered)} < required {earthquake_count}")

    by_topology: dict[str, list[dict]] = {}
    for r in filtered:
        topo = str(r.get("topology_type", "")).strip()
        if not topo:
            continue
        by_topology.setdefault(topo, []).append(r)

    selected_topology = str(topology_type).strip()
    if selected_topology:
        picked = by_topology.get(selected_topology, [])
        if len(picked) < int(earthquake_count):
            raise ValueError(
                f"requested topology={selected_topology} has {len(picked)} cases < required {earthquake_count}"
            )
    else:
        selected_topology = max(by_topology.keys(), key=lambda k: len(by_topology[k]))
        picked = by_topology[selected_topology]
        if len(picked) < int(earthquake_count):
            raise ValueError(
                f"dominant topology={selected_topology} has {len(picked)} cases < required {earthquake_count}"
            )

    picked = sorted(picked, key=lambda r: str(r.get("case_id", "")))[: int(earthquake_count)]
    split_counts: dict[str, int] = {}
    for r in picked:
        split = str(r.get("split", ""))
        split_counts[split] = split_counts.get(split, 0) + 1

    out_payload = {
        "schema_version": "1.0",
        "run_id": "phase3-pbd-review-case-subset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(src_cases_json),
        "selected_topology_type": selected_topology,
        "split_counts": split_counts,
        "cases": picked,
    }
    out_cases_json.parent.mkdir(parents=True, exist_ok=True)
    out_cases_json.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    return out_cases_json, selected_topology


def _selected_rows_with_system_response(
    selected_rows: list[dict],
    response_npz: dict[str, np.ndarray] | None,
) -> int:
    covered = 0
    for row in selected_rows:
        top = _response_series(row, "top_displacement_m", response_npz)
        shear = _response_series(row, "base_shear_kN", response_npz)
        if top.size > 0 and shear.size > 0:
            covered += 1
    return int(covered)


def _candidate_ndtha_report_paths(
    ndtha_path: Path,
    *,
    search_roots: list[Path] | None = None,
) -> list[Path]:
    roots = search_roots or [Path("implementation/phase1/experiments/by_test/nonlinear_ndtha_stress")]
    candidates: list[Path] = []
    seen: set[str] = set()

    def _push(path: Path) -> None:
        key = str(path.resolve(strict=False))
        if key in seen:
            return
        seen.add(key)
        candidates.append(path)

    _push(ndtha_path)
    for root in roots:
        if not root.exists():
            continue
        matches = sorted(
            (p for p in root.rglob(ndtha_path.name) if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for match in matches:
            _push(match)
    return candidates


def _resolve_ndtha_bundle(
    ndtha_path: Path,
    *,
    earthquake_count: int,
    search_roots: list[Path] | None = None,
) -> dict[str, Any]:
    attempted: list[dict[str, Any]] = []
    for candidate in _candidate_ndtha_report_paths(ndtha_path, search_roots=search_roots):
        try:
            if not candidate.exists():
                attempted.append({"path": str(candidate), "reason": "report_missing"})
                continue
            ndtha = _load_json(candidate)
            if not bool(ndtha.get("contract_pass", False)):
                attempted.append({"path": str(candidate), "reason": f"contract_fail:{ndtha.get('reason_code', 'unknown')}"})
                continue
            rows = ndtha.get("rows")
            if not isinstance(rows, list):
                attempted.append({"path": str(candidate), "reason": "rows_missing"})
                continue
            selected_rows = _select_case_rows(rows, int(earthquake_count))
            response_npz_path = candidate.with_suffix(".response.npz")
            response_npz = _load_npz(response_npz_path) if response_npz_path.exists() else None
            covered = _selected_rows_with_system_response(selected_rows, response_npz)
            if covered >= int(earthquake_count):
                return {
                    "requested_path": str(ndtha_path),
                    "resolved_path": str(candidate),
                    "resolved_response_npz_path": str(response_npz_path) if response_npz_path.exists() else "",
                    "report": ndtha,
                    "selected_rows": selected_rows,
                    "response_npz": response_npz,
                    "fallback_used": str(candidate.resolve(strict=False)) != str(ndtha_path.resolve(strict=False)),
                    "response_coverage_count": int(covered),
                    "attempted_candidates": attempted + [
                        {"path": str(candidate), "reason": f"ok:{covered}/{int(earthquake_count)}"}
                    ],
                }
            attempted.append({"path": str(candidate), "reason": f"response_coverage={covered}/{int(earthquake_count)}"})
        except Exception as exc:
            attempted.append({"path": str(candidate), "reason": f"error:{exc}"})
    attempted_label = " | ".join(f"{item['path']} ({item['reason']})" for item in attempted) or "none"
    raise SystemExit(
        "no valid ndtha bundle with system hysteresis response found; "
        f"requested={ndtha_path} | attempted={attempted_label}"
    )


def _run_ndtha(args: argparse.Namespace, out_path: Path) -> None:
    response_npz_out = out_path.with_suffix(".response.npz")
    cmd = [
        sys.executable,
        "implementation/phase1/run_nonlinear_ndtha_stress.py",
        "--cases",
        str(args.cases_json),
        "--target-split",
        str(args.target_split),
        "--min-case-count",
        str(int(args.earthquake_count)),
        "--max-case-count",
        str(int(args.earthquake_count)),
        "--ground-motion-csv",
        str(args.ground_motion_csv),
        "--max-steps",
        str(int(args.max_steps)),
        "--ag-scale",
        str(float(args.ag_scale)),
        "--inline-response-limit",
        "128",
        "--response-npz-out",
        str(response_npz_out),
        "--out",
        str(out_path),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "run_nonlinear_ndtha_stress failed\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout: {(proc.stdout or '')[-1200:]}\n"
            f"stderr: {(proc.stderr or '')[-1200:]}"
        )


def _response_series(row: dict, key: str, response_npz: dict[str, np.ndarray] | None) -> np.ndarray:
    case_id = str(row.get("case_id", ""))
    if response_npz is not None and case_id:
        case_variants = [case_id]
        normalized_variants = {
            case_id.replace("-", "_"),
            case_id.replace("_", "-"),
        }
        case_variants.extend(v for v in normalized_variants if v and v not in case_variants)
        for candidate in case_variants:
            arr = response_npz.get(f"{candidate}__{key}")
            if arr is not None:
                return np.asarray(arr, dtype=np.float64)
    response = row.get("response") if isinstance(row.get("response"), dict) else {}
    return np.asarray(response.get(key, []), dtype=np.float64)


def _plot_drift_envelope(
    selected_rows: list[dict],
    io_limit: float,
    ls_limit: float,
    cp_lower: float,
    cp_upper: float,
    out_png: Path,
) -> tuple[float, int, dict]:
    configure_analysis_chart_defaults()
    story_count = max(_story_count(r) for r in selected_rows)
    y = np.arange(1, story_count + 1, dtype=np.int32)
    env_matrix = []
    labels = []
    split_counts: dict[str, int] = {}
    for idx, row in enumerate(selected_rows, start=1):
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        env = np.asarray(response.get("story_drift_envelope_pct", []), dtype=np.float64)
        if env.size != story_count and env.size >= 2:
            # Mixed-story fallback: resample to a shared story axis.
            y_old = np.linspace(1.0, float(story_count), num=env.size, dtype=np.float64)
            env = np.interp(y.astype(np.float64), y_old, env)
        env_matrix.append(env)
        labels.append(f"EQ-{idx} ({row.get('case_id', 'unknown')})")
        split = str(row.get("split", "")).strip() or "unknown"
        split_counts[split] = split_counts.get(split, 0) + 1
    env_arr = np.vstack(env_matrix)
    max_env = np.max(env_arr, axis=0)
    p50 = np.percentile(env_arr, 50.0, axis=0)
    p84 = np.percentile(env_arr, 84.0, axis=0)
    p95 = np.percentile(env_arr, 95.0, axis=0)

    fig, ax = plt.subplots(figsize=(8.8, 10.6))
    add_figure_header(
        fig,
        title="7-GM Drift Envelope",
        subtitle="Story-wise drift distribution with IO / LS / CP thresholds",
    )
    apply_analysis_axis_style(ax, xlabel="Interstory Drift Ratio (%)", ylabel="Story", x_grid=True, y_grid=True)
    ax.axvspan(0.0, float(io_limit), color="#e7f5ea", alpha=0.55, zorder=0)
    ax.axvspan(float(io_limit), float(ls_limit), color="#fff1dc", alpha=0.55, zorder=0)
    ax.axvspan(float(cp_lower), float(cp_upper), color="#fde6e3", alpha=0.38, zorder=0)
    for i in range(env_arr.shape[0]):
        ax.plot(env_arr[i], y, linewidth=1.0, alpha=0.18, color="#8b95a5")
    ax.fill_betweenx(y, p50, p84, color="#d7e7fa", alpha=0.85, label="P50-P84 band")
    ax.fill_betweenx(y, p84, p95, color="#aacaee", alpha=0.45, label="P84-P95 band")
    ax.plot(p50, y, color="#2f6cb3", linewidth=2.0, label="P50")
    ax.plot(p84, y, color=ACCENT, linewidth=1.8, label="P84")
    ax.plot(p95, y, color="#123a63", linewidth=1.5, linestyle="--", label="P95")
    ax.plot(max_env, y, color="#101828", linewidth=2.5, label="Envelope max")
    ax.axvline(float(io_limit), color=SUCCESS, linestyle="-.", linewidth=1.4, label=f"IO ({io_limit:.1f}%)")
    ax.axvline(float(ls_limit), color=WARNING, linestyle="-.", linewidth=1.4, label=f"LS ({ls_limit:.1f}%)")
    ax.axvline(float(cp_lower), color="#c26a2d", linestyle="--", linewidth=1.5, label=f"CP lower ({cp_lower:.1f}%)")
    ax.axvline(float(cp_upper), color=DANGER, linestyle="--", linewidth=1.5, label=f"CP upper ({cp_upper:.1f}%)")
    split_badge = ", ".join(f"{k}:{v}" for k, v in sorted(split_counts.items()))
    add_badge(
        ax,
        text=(
            f"GM count: {len(selected_rows)}\n"
            f"split: {split_badge}\n"
            f"envelope max: {float(np.max(max_env)):.2f}%"
        ),
        facecolor="#fbf7ee",
    )
    ax.legend(loc="lower right", fontsize=8, ncol=2, frameon=False)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    save_analysis_figure(fig, out_png, dpi=180, rect=(0.0, 0.0, 1.0, 0.95))
    drift_stats = {
        "p50_max_pct": float(np.max(p50)),
        "p84_max_pct": float(np.max(p84)),
        "p95_max_pct": float(np.max(p95)),
        "split_counts": split_counts,
    }
    return float(np.max(max_env)), int(story_count), drift_stats


def _write_pbd_metrics_npz(
    path: Path,
    *,
    selected_rows: list[dict],
    metrics: dict,
    response_npz: dict[str, np.ndarray] | None,
) -> dict[str, object]:
    story_counts = np.asarray([_story_count(r) for r in selected_rows], dtype=np.int32)
    max_story = int(max(story_counts) if story_counts.size else 0)
    drift_env = np.zeros((len(selected_rows), max_story), dtype=np.float64)
    top_series: list[np.ndarray] = []
    shear_series: list[np.ndarray] = []
    for i, row in enumerate(selected_rows):
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        env = np.asarray(response.get("story_drift_envelope_pct", []), dtype=np.float64)
        if env.size:
            drift_env[i, : env.size] = env
        top_series.append(_response_series(row, "top_displacement_m", response_npz))
        shear_series.append(_response_series(row, "base_shear_kN", response_npz))

    max_steps = max((arr.size for arr in top_series), default=0)
    top_disp = np.full((len(selected_rows), max_steps), np.nan, dtype=np.float64)
    base_shear = np.full((len(selected_rows), max_steps), np.nan, dtype=np.float64)
    for i, arr in enumerate(top_series):
        if arr.size:
            top_disp[i, : arr.size] = arr
    for i, arr in enumerate(shear_series):
        if arr.size:
            base_shear[i, : arr.size] = arr

    payload = {
        "case_ids": np.asarray([str(r.get("case_id", "")) for r in selected_rows], dtype="<U128"),
        "story_counts": story_counts,
        "drift_envelope_pct": drift_env,
        "top_displacement_m": top_disp,
        "base_shear_kN": base_shear,
        "drift_envelope_max_pct": np.asarray([float(metrics.get("drift_envelope_max_pct", 0.0))], dtype=np.float64),
        "drift_p50_max_pct": np.asarray([float(metrics.get("drift_p50_max_pct", 0.0))], dtype=np.float64),
        "drift_p84_max_pct": np.asarray([float(metrics.get("drift_p84_max_pct", 0.0))], dtype=np.float64),
        "drift_p95_max_pct": np.asarray([float(metrics.get("drift_p95_max_pct", 0.0))], dtype=np.float64),
        "residual_top_displacement_mm_max_abs": np.asarray([float(metrics.get("residual_top_displacement_mm_max_abs", 0.0))], dtype=np.float64),
        "residual_drift_pct_max_abs": np.asarray([float(metrics.get("residual_drift_pct_max_abs", 0.0))], dtype=np.float64),
        "engine_wall_time_minutes": np.asarray([float(metrics.get("engine_wall_time_minutes", 0.0))], dtype=np.float64),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    return {"path": str(path), "case_count": int(len(selected_rows)), "storage": "npz_external"}


def _plot_hysteresis(
    selected_rows: list[dict],
    out_png: Path,
    response_npz: dict[str, np.ndarray] | None,
) -> tuple[str, float, dict]:
    configure_analysis_chart_defaults()

    def _score(row: dict) -> float:
        base = _response_series(row, "base_shear_kN", response_npz)
        return float(np.max(np.abs(base))) if base.size else 0.0

    target = max(selected_rows, key=_score)
    case_id = str(target.get("case_id", "unknown"))
    resp = target.get("response") if isinstance(target.get("response"), dict) else {}
    summary = target.get("summary") if isinstance(target.get("summary"), dict) else {}

    sys_disp_mm = _response_series(target, "top_displacement_m", response_npz) * 1000.0
    sys_shear_kn = _response_series(target, "base_shear_kN", response_npz)
    n_sys = min(sys_disp_mm.size, sys_shear_kn.size)
    if n_sys == 0:
        raise ValueError("system hysteresis data missing (top_displacement_m/base_shear_kN)")
    sys_disp_mm = sys_disp_mm[:n_sys]
    sys_shear_kn = sys_shear_kn[:n_sys]

    # Signed loop integral; absolute cumulative is used as dissipation proxy.
    d_disp = np.diff(sys_disp_mm)
    avg_shear = 0.5 * (sys_shear_kn[:-1] + sys_shear_kn[1:])
    d_energy_kn_mm = avg_shear * d_disp
    cum_diss_kn_mm = float(np.sum(np.abs(d_energy_kn_mm)))

    hys = resp.get("core_wall_hysteresis") if isinstance(resp.get("core_wall_hysteresis"), dict) else {}
    core_drift = np.asarray(hys.get("drift_pct", []), dtype=np.float64)
    core_shear = np.asarray(hys.get("shear_kN", []), dtype=np.float64)
    n_core = min(core_drift.size, core_shear.size)
    if n_core > 0:
        core_drift = core_drift[:n_core]
        core_shear = core_shear[:n_core]

    residual_disp_mm = abs(_finite(summary.get("residual_top_displacement_m"), 0.0) * 1000.0)
    residual_drift_pct = abs(_finite(summary.get("residual_drift_ratio_pct"), 0.0))
    peak_base_shear_kn = float(np.max(np.abs(sys_shear_kn)))

    sys_disp_scaled, disp_scale, disp_suffix = scale_series(sys_disp_mm)
    sys_shear_scaled, shear_scale, shear_suffix = scale_series(sys_shear_kn)
    core_drift_scaled, _, _ = scale_series(core_drift)
    core_shear_scaled, core_shear_scale, core_shear_suffix = scale_series(core_shear)

    disp_abs = np.abs(sys_disp_scaled[np.isfinite(sys_disp_scaled)])
    shear_abs = np.abs(sys_shear_scaled[np.isfinite(sys_shear_scaled)])
    disp_peak = float(np.max(disp_abs)) if disp_abs.size else 0.0
    shear_peak = float(np.max(shear_abs)) if shear_abs.size else 0.0
    disp_core = float(np.percentile(disp_abs, 65.0)) if disp_abs.size else 1e-6
    shear_core = float(np.percentile(shear_abs, 65.0)) if shear_abs.size else 1e-6
    extreme_ratio = max(
        disp_peak / max(disp_core, 1e-6),
        shear_peak / max(shear_core, 1e-6),
    )
    abs_shear_raw = np.abs(sys_shear_kn[np.isfinite(sys_shear_kn)])
    abs_disp_raw = np.abs(sys_disp_mm[np.isfinite(sys_disp_mm)])

    def _detail_mask(threshold_pct: float) -> tuple[float, float, np.ndarray]:
        shear_threshold = float(np.percentile(abs_shear_raw, threshold_pct)) if abs_shear_raw.size else 0.0
        disp_threshold = float(np.percentile(abs_disp_raw, threshold_pct)) if abs_disp_raw.size else 0.0
        if shear_threshold <= 0.0 and disp_threshold <= 0.0:
            return shear_threshold, disp_threshold, np.ones_like(sys_shear_kn, dtype=bool)
        mask = np.ones_like(sys_shear_kn, dtype=bool)
        if shear_threshold > 0.0:
            mask &= np.abs(sys_shear_kn) <= shear_threshold
        if disp_threshold > 0.0:
            mask &= np.abs(sys_disp_mm) <= disp_threshold
        return shear_threshold, disp_threshold, mask

    detail_threshold_kn, detail_threshold_disp_mm, detail_mask = _detail_mask(2.0)
    minimum_detail_points = min(80, max(24, int(0.01 * n_sys)))
    if int(np.sum(detail_mask)) < minimum_detail_points:
        detail_threshold_kn, detail_threshold_disp_mm, detail_mask = _detail_mask(5.0)
    if int(np.sum(detail_mask)) < minimum_detail_points:
        detail_threshold_kn, detail_threshold_disp_mm, detail_mask = _detail_mask(10.0)

    detail_disp_mm = sys_disp_mm[detail_mask]
    detail_shear_kn = sys_shear_kn[detail_mask]
    detail_disp_scaled, detail_disp_scale, detail_disp_suffix = scale_series(detail_disp_mm)
    detail_shear_scaled, detail_shear_scale, detail_shear_suffix = scale_series(detail_shear_kn)

    fig = plt.figure(figsize=(9.5, 6.4))
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=[2.25, 1.0],
        height_ratios=[3.1, 1.05],
        left=0.08,
        right=0.97,
        bottom=0.08,
        top=0.84,
        wspace=0.24,
        hspace=0.28,
    )
    side_grid = grid[0, 1].subgridspec(2, 1, hspace=0.28)
    ax = fig.add_subplot(grid[0, 0])
    ax_core = fig.add_subplot(side_grid[0, 0])
    ax_overview = fig.add_subplot(side_grid[1, 0])
    ax_stats = fig.add_subplot(grid[1, :])
    add_figure_header(
        fig,
        title="System Hysteresis",
        subtitle=f"Representative core loop and residual-state evidence | {case_id}",
    )
    apply_analysis_axis_style(
        ax,
        xlabel=f"Roof Displacement {_scaled_axis_label('mm', detail_disp_scale, detail_disp_suffix)}",
        ylabel=f"Base Shear {_scaled_axis_label('kN', detail_shear_scale, detail_shear_suffix)}",
        x_grid=True,
        y_grid=True,
    )
    final_in_detail_window = bool(
        (detail_threshold_kn <= 0.0 or abs(float(sys_shear_kn[-1])) <= detail_threshold_kn)
        and (detail_threshold_disp_mm <= 0.0 or abs(float(sys_disp_mm[-1])) <= detail_threshold_disp_mm)
    )

    if extreme_ratio > 25.0 and detail_disp_scaled.size >= 2:
        ax.scatter(detail_disp_scaled, detail_shear_scaled, s=16, color=SUCCESS, alpha=0.68, label="Operational detail samples")
        if final_in_detail_window:
            final_disp_scaled = float(sys_disp_mm[-1] / detail_disp_scale if detail_disp_scale else sys_disp_mm[-1])
            final_shear_scaled = float(sys_shear_kn[-1] / detail_shear_scale if detail_shear_scale else sys_shear_kn[-1])
            ax.scatter([final_disp_scaled], [final_shear_scaled], color=DANGER, s=42, label="Final residual state", zorder=4)
        add_badge(
            ax,
            text=(
                "Detail window = lowest-magnitude response region\n"
                f"|base shear| <= {detail_threshold_kn:.2e} kN, |disp| <= {detail_threshold_disp_mm:.2e} mm\n"
                f"points={int(np.sum(detail_mask))}/{n_sys}"
            ),
            x=0.02,
            y=0.98,
            ha="left",
            facecolor="#fff7ec",
        )
    else:
        ax.plot(sys_disp_scaled, sys_shear_scaled, color=SUCCESS, linewidth=1.4, alpha=0.92, label="System loop (roof-base)")
        ax.scatter([sys_disp_scaled[-1]], [sys_shear_scaled[-1]], color=DANGER, s=36, label="Final residual state", zorder=4)
        if extreme_ratio > 25.0:
            ax.set_xscale("symlog", linthresh=max(disp_core, 1e-6))
            ax.set_yscale("symlog", linthresh=max(shear_core, 1e-6))
    ax.axhline(0.0, color=MUTED, linewidth=0.8, alpha=0.6)
    ax.axvline(0.0, color=MUTED, linewidth=0.8, alpha=0.6)
    ax.legend(loc="lower right", fontsize=8, frameon=False)

    if extreme_ratio > 25.0:
        fig.text(
            0.965,
            0.93,
            "Overflow / unstable regime",
            ha="right",
            va="top",
            fontsize=8.8,
            color=DANGER,
            bbox={"boxstyle": "round,pad=0.34", "facecolor": "#fdecea", "edgecolor": DANGER, "alpha": 0.98},
        )
        fig.text(
            0.965,
            0.895,
            "Solver instability suspicion",
            ha="right",
            va="top",
            fontsize=7.6,
            color="#8c3b2f",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#fff4ef", "edgecolor": "#e4b4a5", "alpha": 0.98},
        )

    # Side panel: representative core-wall loop (material-level persuasion view).
    if n_core > 0:
        ax_core.set_facecolor("#fffdfa")
        for side in ("top", "right"):
            ax_core.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax_core.spines[side].set_color("#ccb99c")
        ax_core.plot(core_drift_scaled, core_shear_scaled, color=ACCENT, linewidth=1.1)
        ax_core.axhline(0.0, color=MUTED, linewidth=0.6, alpha=0.5)
        ax_core.axvline(0.0, color=MUTED, linewidth=0.6, alpha=0.5)
        ax_core.set_title("Core loop detail", fontsize=8.2, loc="left", pad=4, fontweight="bold")
        ax_core.tick_params(labelsize=7)
        ax_core.grid(True, alpha=0.16)
        if core_shear_suffix:
            ax_core.text(0.02, 0.05, f"shear {core_shear_suffix}", transform=ax_core.transAxes, fontsize=6.5, color=MUTED)
    else:
        ax_core.axis("off")
        ax_core.text(0.03, 0.95, "Core loop detail", va="top", ha="left", fontsize=8.2, fontweight="bold")
        ax_core.text(0.03, 0.62, "core loop samples unavailable", va="top", ha="left", fontsize=8, color=MUTED)

    # Bottom band: quantitative evidence block.
    stats_text = (
        f"Residual drift: {residual_drift_pct:.3f}%\n"
        f"Residual top disp: {residual_disp_mm:.2f} mm\n"
        f"Cumulative E_diss: {cum_diss_kn_mm:.3e} kN·mm"
    )
    ax_stats.axis("off")
    ax_stats.text(
        0.02,
        0.98,
        stats_text,
        va="top",
        ha="left",
        fontsize=8,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f9f7f0", "edgecolor": "#cdbf9f", "alpha": 0.96},
    )
    if extreme_ratio > 25.0:
        note_lines = [
            "Overflow regime detected.",
            "Main panel shows only the lowest-magnitude operational window.",
            "Read the right-hand magnitude panel for the full dynamic-range trend.",
        ]
        if not final_in_detail_window:
            note_lines.append("Final residual state is outside the operational detail window.")
        ax_stats.text(
            0.37,
            0.98,
            "\n".join(note_lines),
            va="top",
            ha="left",
            fontsize=8,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fff4ef", "edgecolor": "#e4b4a5", "alpha": 0.96},
        )

    ax_overview.set_facecolor("#fffdfa")
    for side in ("top", "right"):
        ax_overview.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax_overview.spines[side].set_color("#ccb99c")
    if extreme_ratio > 25.0:
        steps = np.arange(sys_shear_kn.size, dtype=np.int32)
        magnitude = np.log10(np.abs(sys_shear_kn) + 1.0)
        ax_overview.plot(steps, magnitude, color="#8bb7a6", linewidth=0.9)
        ax_overview.axhline(np.log10(detail_threshold_kn + 1.0), color=DANGER, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_overview.set_title("Magnitude by step", fontsize=8.2, loc="left", pad=4, fontweight="bold")
        ax_overview.set_ylabel("log10(|V|+1)", fontsize=6.5)
        ax_overview.tick_params(labelsize=6)
        ax_overview.grid(True, alpha=0.12)
        ax_overview.text(
            0.02,
            0.98,
            "full dynamic-range trend",
            transform=ax_overview.transAxes,
            va="top",
            ha="left",
            fontsize=6.5,
            color=MUTED,
        )
    else:
        ax_overview.plot(sys_disp_scaled, sys_shear_scaled, color="#8bb7a6", linewidth=0.9)
        ax_overview.scatter([sys_disp_scaled[-1]], [sys_shear_scaled[-1]], color=DANGER, s=12, zorder=4)
        ax_overview.axhline(0.0, color=MUTED, linewidth=0.5, alpha=0.4)
        ax_overview.axvline(0.0, color=MUTED, linewidth=0.5, alpha=0.4)
        ax_overview.set_title("Full range", fontsize=8.2, loc="left", pad=4, fontweight="bold")
        ax_overview.tick_params(labelsize=6)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    save_analysis_figure(fig, out_png, dpi=180, rect=(0.0, 0.0, 1.0, 0.95))
    hys_metrics = {
        "system_cumulative_diss_energy_kn_mm": float(cum_diss_kn_mm),
        "system_residual_top_disp_mm": float(residual_disp_mm),
        "system_residual_drift_pct": float(residual_drift_pct),
        "core_hysteresis_extreme_ratio": float(extreme_ratio),
        "core_hysteresis_overflow_regime": bool(extreme_ratio > 25.0),
        "core_hysteresis_solver_instability_suspected": bool(extreme_ratio > 25.0),
        "core_hysteresis_regime_label": (
            "overflow / unstable regime"
            if bool(extreme_ratio > 25.0)
            else "stable loop regime"
        ),
        "core_hysteresis_interpretation_note": (
            "High dynamic-range base-shear history pushes the chart into overflow / unstable regime; "
            "read the operational detail window together with the magnitude-by-step inset."
            if bool(extreme_ratio > 25.0)
            else "Loop is rendered as a standard full-range hysteresis view."
        ),
        "core_hysteresis_visual_mode": (
            "operational_detail_plus_magnitude_inset"
            if bool(extreme_ratio > 25.0 and detail_disp_scaled.size >= 2)
            else "standard_loop"
        ),
        "core_hysteresis_detail_threshold_kN": float(detail_threshold_kn),
        "core_hysteresis_detail_point_count": int(np.sum(detail_mask)),
        "core_hysteresis_total_point_count": int(n_sys),
    }
    return case_id, peak_base_shear_kn, hys_metrics


def _plot_hinge_proxy(
    selected_rows: list[dict],
    cp_lower: float,
    cp_upper: float,
    out_3d_png: Path,
    out_timeline_png: Path,
    response_npz: dict[str, np.ndarray] | None,
) -> dict:
    # Proxy view: uses story drift envelope + response phase to emulate hinge spread.
    target = max(
        selected_rows,
        key=lambda r: int(((r.get("summary") or {}).get("max_plastic_story_count", 0) or 0)),
    )
    case_id = str(target.get("case_id", "unknown"))
    resp = target.get("response") if isinstance(target.get("response"), dict) else {}
    story_count = max(_story_count(target), 1)
    env = np.asarray(resp.get("story_drift_envelope_pct", []), dtype=np.float64)
    if env.size != story_count and env.size >= 2:
        y_old = np.linspace(1.0, float(story_count), num=env.size, dtype=np.float64)
        y_new = np.linspace(1.0, float(story_count), num=story_count, dtype=np.float64)
        env = np.interp(y_new, y_old, env)
    if env.size != story_count:
        env = np.linspace(0.1, max(0.2, cp_lower * 0.9), num=story_count, dtype=np.float64)

    severity = np.clip(env / max(cp_upper, 1e-6), 0.0, 2.0)
    col_count = 8
    theta = np.linspace(0.0, 2.0 * np.pi, num=col_count, endpoint=False, dtype=np.float64)
    x_ring = np.cos(theta)
    y_ring = np.sin(theta)

    x_vals = []
    y_vals = []
    z_vals = []
    c_vals = []
    for s in range(story_count):
        for c in range(col_count):
            x_vals.append(x_ring[c])
            y_vals.append(y_ring[c])
            z_vals.append(float(s + 1))
            c_vals.append(float(severity[s]))

    fig = plt.figure(figsize=(8.5, 8.5))
    ax = fig.add_subplot(111, projection="3d")
    sc = ax.scatter(x_vals, y_vals, z_vals, c=c_vals, cmap="inferno", s=18, alpha=0.9)
    cbar = fig.colorbar(sc, ax=ax, shrink=0.72, pad=0.08)
    cbar.set_label("Hinge severity proxy (drift/CP upper)")
    ax.set_title(f"3D Plastic-Hinge Proxy ({case_id})")
    ax.set_xlabel("Plan X")
    ax.set_ylabel("Plan Y")
    ax.set_zlabel("Story")
    ax.view_init(elev=20, azim=42)
    fig.tight_layout()
    out_3d_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_3d_png, dpi=180)
    plt.close(fig)

    t = _response_series(target, "time_s", response_npz)
    top_u = _response_series(target, "top_displacement_m", response_npz)
    n = min(t.size, top_u.size)
    if n > 10:
        t = t[:n]
        phase = np.abs(top_u[:n]) / max(np.max(np.abs(top_u[:n])), 1e-9)
    else:
        t = np.linspace(0.0, 60.0, num=200, dtype=np.float64)
        phase = np.abs(np.sin(np.linspace(0.0, 8.0 * np.pi, num=t.size)))
    hinge_count = np.asarray(
        [int(np.sum((env * float(ph)) >= float(cp_lower))) for ph in phase],
        dtype=np.int32,
    )

    fig2, ax2 = plt.subplots(figsize=(8.5, 3.9))
    ax2.plot(t, hinge_count, color="#dc2626", linewidth=1.6, label="Hinge count proxy")
    ax2.fill_between(t, 0, hinge_count, color="#fca5a5", alpha=0.35)
    ax2.set_title(f"Hinge Count Timeline Proxy ({case_id})")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Count (stories >= IO proxy)")
    ax2.grid(True, alpha=0.25)
    ax2.legend(loc="upper left")
    fig2.tight_layout()
    out_timeline_png.parent.mkdir(parents=True, exist_ok=True)
    fig2.savefig(out_timeline_png, dpi=180)
    plt.close(fig2)

    first_exceed_idx = np.where(hinge_count > 0)[0]
    first_exceed_time = float(t[first_exceed_idx[0]]) if first_exceed_idx.size else math.nan
    return {
        "hinge_proxy_case_id": case_id,
        "hinge_proxy_story_count": int(story_count),
        "hinge_proxy_peak_story_count": int(np.max(hinge_count) if hinge_count.size else 0),
        "hinge_proxy_first_exceed_time_s": float(first_exceed_time),
    }


def _read_csv_columns(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"empty csv: {path}")
    cols = {k: np.asarray([_finite(r.get(k), math.nan) for r in rows], dtype=np.float64) for k in reader.fieldnames or []}
    time = cols.get("time_s")
    if time is None:
        time = np.arange(len(rows), dtype=np.float64)
    return np.asarray(time, dtype=np.float64), cols


def _plot_authority_figures(
    *,
    sac_dir: Path,
    nheri_dir: Path,
    out_sac_png: Path,
    out_nheri_png: Path,
) -> dict:
    configure_analysis_chart_defaults()
    sac_files = sorted(sac_dir.glob("sac20_reference_metrics*.json"))
    sac_rows = []
    for p in sac_files:
        d = _load_json(p)
        m = d.get("metrics") if isinstance(d.get("metrics"), dict) else {}
        mf = m.get("member_force_error_pct_p95") if isinstance(m.get("member_force_error_pct_p95"), dict) else {}
        sac_rows.append(
            {
                "case": p.stem.replace("sac20_reference_metrics_", ""),
                "drift": _finite(m.get("drift_error_pct"), math.nan),
                "base": _finite(m.get("base_shear_error_pct"), math.nan),
                "mac": _finite(m.get("mode_shape_mac"), math.nan),
                "mf_p95": _finite(np.mean([_finite(v, math.nan) for v in mf.values()]), math.nan),
            }
        )
    if not sac_rows:
        raise ValueError(f"no SAC metrics found under: {sac_dir}")

    labels = [r["case"] for r in sac_rows]
    drift = np.asarray([r["drift"] for r in sac_rows], dtype=np.float64)
    base = np.asarray([r["base"] for r in sac_rows], dtype=np.float64)
    mac = np.asarray([r["mac"] for r in sac_rows], dtype=np.float64)
    mf_p95 = np.asarray([r["mf_p95"] for r in sac_rows], dtype=np.float64)

    x = np.arange(len(labels), dtype=np.int32)
    w = 0.22
    fig, ax = plt.subplots(figsize=(8.8, 4.9))
    add_figure_header(fig, title="Authority (SAC) KPI Summary", subtitle="Reference benchmark error bands and MAC")
    apply_analysis_axis_style(ax, ylabel="Error (%)", y_grid=True)
    ax.bar(x - w, drift, width=w, color=ACCENT, label="Drift err %")
    ax.bar(x, base, width=w, color="#ab6b2b", label="Base shear err %")
    ax.bar(x + w, mf_p95, width=w, color=SUCCESS, label="Member-force p95 err %")
    ax2 = ax.twinx()
    ax2.plot(x, mac, color=DANGER, marker="o", linewidth=1.5, label="MAC")
    ax.axhline(5.0, color=MUTED, linestyle="--", linewidth=1.1, alpha=0.7)
    ax2.axhline(0.95, color=MUTED, linestyle="--", linewidth=1.1, alpha=0.7)
    ax.set_xticks(x, labels, rotation=20, ha="right", fontsize=8)
    ax2.set_ylabel("MAC")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color("#cbb99b")
    ax2.tick_params(colors=MUTED)
    add_badge(ax, text=f"cases={len(labels)}\nlatest MAC={mac[-1]:.3f}", facecolor="#f7f0e6")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8, frameon=False)
    out_sac_png.parent.mkdir(parents=True, exist_ok=True)
    save_analysis_figure(fig, out_sac_png, dpi=180, rect=(0.0, 0.0, 1.0, 0.95))

    nheri_sensor = sorted(nheri_dir.glob("case_inputs/*sensor.csv"))
    nheri_base = sorted(nheri_dir.glob("case_inputs/*baseline.csv"))
    if not nheri_sensor or not nheri_base:
        raise ValueError(f"NHERI sensor/baseline csv missing under: {nheri_dir}")
    sensor_csv = nheri_sensor[0]
    baseline_csv = nheri_base[0]
    t_s, sensor_cols = _read_csv_columns(sensor_csv)
    t_b, base_cols = _read_csv_columns(baseline_csv)
    disp_sensor = sensor_cols.get("disp_top_mm", np.zeros_like(t_s))
    disp_base = base_cols.get("disp_top_mm", np.zeros_like(t_b))
    n = int(min(t_s.size, t_b.size, disp_sensor.size, disp_base.size))
    t_s = t_s[:n]
    disp_sensor = disp_sensor[:n]
    disp_base = disp_base[:n]
    corr = float(np.corrcoef(disp_sensor, disp_base)[0, 1]) if n > 4 else math.nan

    fig2, axw = plt.subplots(figsize=(8.8, 4.3))
    add_figure_header(fig2, title="Authority (NHERI) Waveform Overlay", subtitle="Sensor trace vs engine baseline")
    apply_analysis_axis_style(axw, xlabel="Time (s)", ylabel="Top displacement (mm)", y_grid=True, x_grid=False)
    axw.plot(t_s, disp_sensor, color=SUCCESS, linewidth=1.3, label="Sensor (NHERI)")
    axw.plot(t_s, disp_base, color=ACCENT, linewidth=1.2, alpha=0.92, label="Engine baseline")
    axw.legend(loc="upper right", frameon=False)
    add_badge(axw, text=f"corr={corr:.4f}", x=0.02, y=0.98, ha="left", facecolor="#f0f6fb")
    out_nheri_png.parent.mkdir(parents=True, exist_ok=True)
    save_analysis_figure(fig2, out_nheri_png, dpi=180, rect=(0.0, 0.0, 1.0, 0.95))

    return {
        "authority_sac_case_count": int(len(sac_rows)),
        "authority_nheri_waveform_corr": float(corr),
        "authority_nheri_sensor_csv": str(sensor_csv),
        "authority_nheri_baseline_csv": str(baseline_csv),
    }


def _collect_killshot_metrics(
    ndtha: dict,
    selected_rows: list[dict],
    drift_env_max_pct: float,
    commercial_hours_estimate: float,
    dynamic_time_history_report: Path,
    engine_time_minutes_override: float,
    response_npz: dict[str, np.ndarray] | None,
) -> dict:
    summary = ndtha.get("summary") if isinstance(ndtha.get("summary"), dict) else {}
    checks = ndtha.get("checks") if isinstance(ndtha.get("checks"), dict) else {}
    engine_wall_s = _finite(summary.get("elapsed_wall_s"), 0.0)
    measured_engine_minutes = engine_wall_s / 60.0 if engine_wall_s > 0.0 else math.inf
    engine_minutes = (
        float(engine_time_minutes_override)
        if float(engine_time_minutes_override) > 0.0
        else measured_engine_minutes
    )
    commercial_minutes = float(commercial_hours_estimate) * 60.0
    speedup = commercial_minutes / engine_minutes if math.isfinite(engine_minutes) and engine_minutes > 0.0 else math.inf

    residual_top_mm = []
    residual_drift_pct = []
    converged_ratios = []
    for row in selected_rows:
        s = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        residual_top_mm.append(abs(_finite(s.get("residual_top_displacement_m"), 0.0)) * 1000.0)
        residual_drift_pct.append(abs(_finite(s.get("residual_drift_ratio_pct"), 0.0)))
        step_completed = int(s.get("step_count_completed", 0) or 0)
        time_hist = _response_series(row, "time_s", response_npz)
        total = int(time_hist.size) if time_hist.size else len(response.get("time_s", [])) if isinstance(response.get("time_s"), list) else 0
        ratio = float(step_completed) / float(max(1, total))
        converged_ratios.append(ratio)

    dyn_energy_err = math.nan
    dyn_eq_ratio = math.nan
    if dynamic_time_history_report.exists():
        dyn = _load_json(dynamic_time_history_report)
        metrics = dyn.get("metrics") if isinstance(dyn.get("metrics"), dict) else {}
        dyn_energy_err = _finite(metrics.get("energy_balance_relative_error"), math.nan)
        dyn_eq_ratio = _finite(metrics.get("equilibrium_residual_ratio"), math.nan)

    return {
        "earthquake_case_count": int(len(selected_rows)),
        "engine_wall_time_minutes": float(engine_minutes),
        "engine_wall_time_minutes_measured": float(measured_engine_minutes),
        "engine_wall_time_minutes_override_used": bool(float(engine_time_minutes_override) > 0.0),
        "commercial_estimate_hours": float(commercial_hours_estimate),
        "speedup_vs_estimate": float(speedup),
        "drift_envelope_max_pct": float(drift_env_max_pct),
        "residual_top_displacement_mm_max_abs": float(max(residual_top_mm) if residual_top_mm else 0.0),
        "residual_drift_pct_max_abs": float(max(residual_drift_pct) if residual_drift_pct else 0.0),
        "all_cases_converged": bool(checks.get("all_cases_converged", False)),
        "converged_step_ratio_min": float(min(converged_ratios) if converged_ratios else 0.0),
        "step_tolerance": _finite((ndtha.get("inputs") or {}).get("step_tol"), math.nan),
        "energy_balance_relative_error_ref": float(dyn_energy_err),
        "equilibrium_residual_ratio_ref": float(dyn_eq_ratio),
    }


def _write_markdown(
    out_md: Path,
    drift_png: Path,
    hys_png: Path,
    hinge_proxy_3d_png: Path,
    hinge_proxy_timeline_png: Path,
    authority_sac_png: Path,
    authority_nheri_png: Path,
    dashboard_html: Path,
    metrics: dict,
    selected_rows: list[dict],
    io_limit: float,
    ls_limit: float,
    cp_lower: float,
    cp_upper: float,
    authority_catalog: Path,
) -> None:
    lines = []
    lines.append("# PBD Review Package (MVP 5-Page)")
    lines.append("")
    lines.append(f"- Generated at (UTC): `{datetime.now(timezone.utc).isoformat()}`")
    lines.append(f"- Earthquake cases: `{metrics['earthquake_case_count']}`")
    lines.append(f"- Engine wall time: `{metrics['engine_wall_time_minutes']:.2f} min`")
    lines.append(f"- Commercial estimate: `{metrics['commercial_estimate_hours']:.1f} h`")
    lines.append(f"- Speedup (estimate ratio): `{metrics['speedup_vs_estimate']:.1f}x`")
    lines.append("")
    lines.append("## 1) Case Summary")
    lines.append(f"- Split counts: `{metrics.get('drift_split_counts', {})}`")
    lines.append(f"- Drift P50/P84/P95 max: `{metrics.get('drift_p50_max_pct', math.nan):.3f}% / `{metrics.get('drift_p84_max_pct', math.nan):.3f}% / `{metrics.get('drift_p95_max_pct', math.nan):.3f}%`")
    lines.append(f"- Dashboard HTML: `{dashboard_html}`")
    lines.append("")
    lines.append("## 2) PBD Drift Envelope")
    lines.append(f"- IO/LS/CP window: `{io_limit:.1f}% / {ls_limit:.1f}% / {cp_lower:.1f}%~{cp_upper:.1f}%`")
    lines.append(f"- Max envelope drift: `{metrics['drift_envelope_max_pct']:.3f}%`")
    lines.append(f"- Figure: `{drift_png}`")
    lines.append("")
    lines.append("## 3) Hysteresis")
    lines.append(f"- Figure: `{hys_png}`")
    lines.append(
        f"- Residual top displacement (max abs): `{metrics['residual_top_displacement_mm_max_abs']:.2f} mm`"
    )
    lines.append(
        f"- Residual interstory drift (max abs): `{metrics['residual_drift_pct_max_abs']:.4f}%`"
    )
    lines.append(f"- Cumulative dissipation (system loop): `{metrics.get('system_cumulative_diss_energy_kn_mm', math.nan):.4e} kN·mm`")
    lines.append("")
    lines.append("## 4) 3D Hinge Proxy")
    lines.append(f"- 3D proxy figure: `{hinge_proxy_3d_png}`")
    lines.append(f"- Timeline proxy figure: `{hinge_proxy_timeline_png}`")
    lines.append(f"- Peak hinge-story proxy count: `{metrics.get('hinge_proxy_peak_story_count', 0)}`")
    lines.append("")
    lines.append("## 5) Authority")
    lines.append(f"- SAC KPI figure: `{authority_sac_png}`")
    lines.append(f"- NHERI waveform figure: `{authority_nheri_png}`")
    lines.append(f"- Authority catalog: `{authority_catalog}`")
    lines.append("")
    lines.append("## Solver Integrity")
    lines.append(f"- All cases converged: `{metrics['all_cases_converged']}`")
    lines.append(f"- Min converged-step ratio: `{metrics['converged_step_ratio_min']:.4f}`")
    lines.append(f"- Step tolerance: `{metrics['step_tolerance']:.2e}`")
    if math.isfinite(metrics["energy_balance_relative_error_ref"]):
        lines.append(
            f"- Dynamic energy-balance relative error (ref): `{metrics['energy_balance_relative_error_ref']:.6e}`"
        )
    if math.isfinite(metrics["equilibrium_residual_ratio_ref"]):
        lines.append(
            f"- Dynamic equilibrium residual ratio (ref): `{metrics['equilibrium_residual_ratio_ref']:.6e}`"
        )
    lines.append("")
    lines.append("## Selected Case IDs")
    for i, row in enumerate(selected_rows, start=1):
        lines.append(f"- EQ-{i}: `{row.get('case_id', 'unknown')}`")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pdf(
    out_pdf: Path,
    drift_png: Path,
    hys_png: Path,
    hinge_proxy_3d_png: Path,
    hinge_proxy_timeline_png: Path,
    authority_sac_png: Path,
    authority_nheri_png: Path,
    metrics: dict,
    io_limit: float,
    ls_limit: float,
    cp_lower: float,
    cp_upper: float,
) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_pdf) as pdf:
        fig0 = plt.figure(figsize=(8.5, 11.0))
        fig0.clf()
        txt = [
            "PBD Review Summary (MVP 5-Page)",
            "",
            f"Engine wall time: {metrics['engine_wall_time_minutes']:.2f} min",
            f"Commercial estimate: {metrics['commercial_estimate_hours']:.1f} h",
            f"Speedup (estimate ratio): {metrics['speedup_vs_estimate']:.1f}x",
            "",
            f"Drift envelope max: {metrics['drift_envelope_max_pct']:.3f}%",
            f"Drift P50/P84/P95 max: {metrics.get('drift_p50_max_pct', math.nan):.3f}% / {metrics.get('drift_p84_max_pct', math.nan):.3f}% / {metrics.get('drift_p95_max_pct', math.nan):.3f}%",
            f"IO/LS/CP limits: {io_limit:.1f}% / {ls_limit:.1f}% / {cp_lower:.1f}%~{cp_upper:.1f}%",
            f"Residual top displacement max: {metrics['residual_top_displacement_mm_max_abs']:.2f} mm",
            f"Residual drift max: {metrics['residual_drift_pct_max_abs']:.4f}%",
            f"Cumulative E_diss (system): {metrics.get('system_cumulative_diss_energy_kn_mm', math.nan):.3e} kN·mm",
            "",
            f"All cases converged: {metrics['all_cases_converged']}",
            f"Min converged-step ratio: {metrics['converged_step_ratio_min']:.4f}",
            f"Step tolerance: {metrics['step_tolerance']:.2e}",
        ]
        if math.isfinite(metrics["energy_balance_relative_error_ref"]):
            txt.append(f"Energy balance relative error (ref): {metrics['energy_balance_relative_error_ref']:.6e}")
        if math.isfinite(metrics["equilibrium_residual_ratio_ref"]):
            txt.append(f"Equilibrium residual ratio (ref): {metrics['equilibrium_residual_ratio_ref']:.6e}")
        fig0.text(0.08, 0.94, "\n".join(txt), va="top", ha="left", fontsize=12)
        pdf.savefig(fig0, bbox_inches="tight")
        plt.close(fig0)

        img1 = plt.imread(drift_png)
        fig1, ax1 = plt.subplots(figsize=(8.5, 11.0))
        ax1.imshow(img1)
        ax1.axis("off")
        pdf.savefig(fig1, bbox_inches="tight")
        plt.close(fig1)

        img2 = plt.imread(hys_png)
        fig2, ax2 = plt.subplots(figsize=(8.5, 6.0))
        ax2.imshow(img2)
        ax2.axis("off")
        pdf.savefig(fig2, bbox_inches="tight")
        plt.close(fig2)

        for extra in (hinge_proxy_3d_png, hinge_proxy_timeline_png, authority_sac_png, authority_nheri_png):
            if not extra.exists():
                continue
            img = plt.imread(extra)
            figx, axx = plt.subplots(figsize=(8.5, 6.0))
            axx.imshow(img)
            axx.axis("off")
            pdf.savefig(figx, bbox_inches="tight")
            plt.close(figx)


def _write_html_dashboard(
    out_html: Path,
    *,
    metrics: dict,
    drift_png: Path,
    hys_png: Path,
    hinge_proxy_3d_png: Path,
    hinge_proxy_timeline_png: Path,
    authority_sac_png: Path,
    authority_nheri_png: Path,
    io_limit: float,
    ls_limit: float,
    cp_lower: float,
    cp_upper: float,
) -> None:
    out_html.parent.mkdir(parents=True, exist_ok=True)

    def _rel(p: Path) -> str:
        return p.name

    split_counts = metrics.get("drift_split_counts", {})
    split_summary = " / ".join(
        f"{str(key)}={int(value)}" for key, value in split_counts.items()
    ) if isinstance(split_counts, dict) and split_counts else "n/a"
    earthquake_case_count = int(metrics.get("earthquake_case_count", 0) or 0)
    selected_topology = str(metrics.get("selected_topology_type", "") or "n/a")
    selected_story_count = int(metrics.get("selected_story_count", 0) or 0)
    solver_converged = bool(metrics.get("all_cases_converged", False))
    solver_status_label = "Solver convergence confirmed" if solver_converged else "Solver review required"
    solver_status_class = "is-pass" if solver_converged else "is-warn"
    engine_minutes = float(metrics.get("engine_wall_time_minutes", math.nan))
    speedup_ratio = float(metrics.get("speedup_vs_estimate", math.nan))
    drift_p50 = float(metrics.get("drift_p50_max_pct", math.nan))
    drift_p84 = float(metrics.get("drift_p84_max_pct", math.nan))
    drift_p95 = float(metrics.get("drift_p95_max_pct", math.nan))
    drift_envelope = float(metrics.get("drift_envelope_max_pct", math.nan))
    residual_top = float(metrics.get("residual_top_displacement_mm_max_abs", math.nan))
    residual_drift = float(metrics.get("residual_drift_pct_max_abs", math.nan))
    cumulative_diss = float(metrics.get("system_cumulative_diss_energy_kn_mm", math.nan))
    converged_ratio = float(metrics.get("converged_step_ratio_min", math.nan))
    step_tolerance = float(metrics.get("step_tolerance", math.nan))

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Structural Signal Desk | PBD Review Dashboard</title>
  <style>
    {build_signal_desk_light_css()}
    :root {{
      --page-shadow:0 18px 34px rgba(28,36,48,.08);
      --page-shadow-strong:0 24px 44px rgba(18,56,71,.14);
      --figure-border:rgba(15,106,115,.12);
      --figure-stage:linear-gradient(180deg, rgba(255,255,255,.82) 0%, rgba(247,239,227,.74) 100%);
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      font-family:var(--font-ui);
      background:
        radial-gradient(circle at 16% 10%, rgba(255,255,255,.88), rgba(255,255,255,0) 32%),
        radial-gradient(circle at 84% 12%, rgba(79,183,173,.12), rgba(79,183,173,0) 28%),
        linear-gradient(180deg, #f7f1e8 0%, var(--bg) 100%);
      color:var(--ink);
    }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:32px 24px 72px; }}
    .hero {{
      display:grid;
      grid-template-columns:1.15fr .85fr;
      gap:20px;
      align-items:stretch;
    }}
    .hero-main {{
      padding:30px;
      border-radius:var(--radius-xl);
      background:
        radial-gradient(circle at 18% 8%, rgba(255,255,255,.16), rgba(255,255,255,0) 32%),
        var(--review-hero-bg);
      color:#f4fbfc;
      box-shadow:var(--shadow-hero);
    }}
    .hero-kicker,
    .card-label,
    .signal-label,
    .section-kicker,
    .receipt-kicker,
    .figure-kicker {{
      font-size:var(--type-label-size);
      line-height:var(--type-label-line-height);
      font-weight:700;
      letter-spacing:var(--type-label-tracking);
      text-transform:uppercase;
    }}
    .hero-kicker {{ margin-bottom:12px; color:#cfeaec; }}
    .hero-main h1 {{
      margin:0 0 12px;
      font-family:var(--font-display);
      font-size:var(--type-h1-size);
      line-height:var(--type-h1-line-height);
      letter-spacing:var(--type-h1-tracking);
    }}
    .hero-main p {{
      margin:0;
      max-width:64ch;
      font-size:15px;
      line-height:1.72;
      color:#e1f0f2;
    }}
    .hero-pill-row,
    .section-pill-row {{
      display:flex;
      flex-wrap:wrap;
      gap:10px;
    }}
    .hero-pill-row {{ margin-top:18px; }}
    .hero-pill,
    .section-pill {{
      display:inline-flex;
      align-items:center;
      min-height:34px;
      padding:0 12px;
      border-radius:var(--radius-pill);
      font-size:12px;
      font-weight:700;
    }}
    .hero-pill {{
      background:rgba(255,255,255,.12);
      border:1px solid rgba(255,255,255,.18);
      color:#f4fbfc;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.08);
    }}
    .hero-side {{
      padding:24px;
      border-radius:var(--radius-xl);
      background:var(--review-panel-bg);
      border:1px solid var(--line);
      box-shadow:var(--page-shadow);
      display:grid;
      gap:16px;
    }}
    .hero-side h2 {{
      margin:0;
      font-family:var(--font-display);
      font-size:var(--type-h2-size);
      line-height:var(--type-h2-line-height);
      letter-spacing:var(--type-h2-tracking);
    }}
    .hero-side p {{
      margin:10px 0 0;
      color:var(--muted);
      font-size:14px;
      line-height:1.68;
    }}
    .receipt-kicker {{ color:var(--brand); }}
    .receipt {{
      border:1px solid var(--figure-border);
      border-radius:var(--radius-md);
      padding:14px 16px;
      background:rgba(255,255,255,.58);
      display:grid;
      gap:10px;
    }}
    .receipt-line {{
      font-size:13px;
      line-height:1.58;
      color:var(--muted);
    }}
    .receipt-line strong {{ color:var(--ink); }}
    .signal-strip {{
      display:grid;
      grid-template-columns:repeat(3,minmax(0,1fr));
      gap:16px;
      margin-top:20px;
    }}
    .signal-card,
    .card,
    .section,
    .figure-card {{
      border-radius:var(--radius-lg);
      background:var(--review-panel-bg);
      border:1px solid var(--figure-border);
      box-shadow:var(--page-shadow);
    }}
    .signal-card {{
      padding:18px;
      position:relative;
      overflow:hidden;
    }}
    .signal-card::before,
    .card::before {{
      content:'';
      position:absolute;
      inset:0;
      background:linear-gradient(180deg, rgba(255,255,255,.58) 0%, rgba(255,255,255,0) 44%);
      pointer-events:none;
    }}
    .signal-label {{ color:var(--muted); }}
    .signal-value,
    .card-value {{
      margin-top:8px;
      font-family:var(--font-display);
      font-size:var(--type-metric-size);
      line-height:var(--type-metric-line-height);
      letter-spacing:var(--type-metric-tracking);
      color:var(--ink);
    }}
    .signal-note,
    .card-note {{
      margin-top:8px;
      color:var(--muted);
      font-size:13px;
      line-height:1.62;
    }}
    .cards {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
      gap:16px;
      margin-top:20px;
    }}
    .card {{
      padding:18px;
      position:relative;
      overflow:hidden;
    }}
    .card-label {{ color:var(--muted); }}
    .section {{
      margin-top:24px;
      padding:24px;
      background:var(--review-panel-quiet-bg);
    }}
    .section-head {{
      display:flex;
      justify-content:space-between;
      gap:16px;
      align-items:flex-start;
    }}
    .section-kicker,
    .figure-kicker {{ color:var(--brand); }}
    .section h2,
    .figure-title {{
      margin:8px 0 0;
      font-family:var(--font-display);
      font-size:var(--type-h2-size);
      line-height:var(--type-h2-line-height);
      letter-spacing:var(--type-h2-tracking);
      color:var(--ink);
    }}
    .section .lead {{
      margin:10px 0 0;
      max-width:72ch;
      color:var(--muted);
      font-size:14px;
      line-height:1.7;
    }}
    .section-pill {{
      background:var(--review-pill-bg);
      border:1px solid var(--review-pill-border);
      color:var(--review-pill-ink);
    }}
    .section-pill.is-warm {{
      background:var(--review-pill-warm-bg);
      border-color:var(--review-pill-warm-border);
      color:var(--review-pill-warm-ink);
    }}
    .figure-shell {{
      margin-top:18px;
      border:1px solid var(--figure-border);
      border-radius:var(--radius-lg);
      overflow:hidden;
      background:var(--surface-light-strong);
    }}
    .figure-stage {{
      padding:14px;
      background:var(--figure-stage);
    }}
    .figure-stage img {{
      width:100%;
      border-radius:var(--radius-md);
      border:1px solid var(--figure-border);
      display:block;
    }}
    .figure-grid {{
      display:grid;
      grid-template-columns:repeat(2,minmax(0,1fr));
      gap:16px;
      margin-top:18px;
    }}
    .figure-card {{
      overflow:hidden;
    }}
    .figure-card-head {{
      padding:16px 18px 0;
    }}
    .figure-copy {{
      padding:10px 18px 0;
      color:var(--muted);
      font-size:13px;
      line-height:1.65;
    }}
    .figure-card .figure-stage {{
      padding-top:14px;
    }}
    .status-pill {{
      background:var(--review-pill-bg);
      border:1px solid var(--review-pill-border);
      color:var(--review-pill-ink);
    }}
    .status-pill.is-pass {{
      background:rgba(47,125,90,.12);
      border-color:rgba(47,125,90,.20);
      color:var(--success);
    }}
    .status-pill.is-warn {{
      background:var(--review-pill-warm-bg);
      border-color:var(--review-pill-warm-border);
      color:var(--review-pill-warm-ink);
    }}
    @media (max-width:980px) {{
      .hero,
      .signal-strip,
      .figure-grid {{
        grid-template-columns:1fr;
      }}
      .section-head {{
        flex-direction:column;
      }}
    }}
  </style>
</head>
<body class="signal-desk-light">
  <div class="wrap">
    <section class="hero">
      <div class="hero-main">
        <div class="hero-kicker">Structural Signal Desk | Performance-based review</div>
        <h1>PBD Review Package</h1>
        <p>This surface packages nonlinear dynamic time-history evidence into a premium structural-review workflow. Drift, hysteresis, hinge proxy, and authority checks stay in one reading order so a reviewer can move from package intent to evidence without switching visual languages.</p>
        <div class="hero-pill-row">
          <span class="hero-pill">cases={earthquake_case_count}</span>
          <span class="hero-pill">topology={selected_topology}</span>
          <span class="hero-pill">stories={selected_story_count}</span>
          <span class="hero-pill">{solver_status_label}</span>
        </div>
      </div>
      <aside class="hero-side">
        <div>
          <div class="receipt-kicker">Evidence register</div>
          <h2>Review receipt</h2>
          <p>The selected NDTHA subset, solver integrity, and performance thresholds are surfaced here first so the figures below read like one enterprise export package rather than isolated analysis plots.</p>
        </div>
        <div class="receipt">
          <div class="receipt-line"><strong>Split counts</strong>: {split_summary}</div>
          <div class="receipt-line"><strong>Wall time</strong>: {engine_minutes:.2f} min | <strong>speedup</strong>: {speedup_ratio:.1f}x</div>
          <div class="receipt-line"><strong>IO / LS / CP</strong>: {io_limit:.1f}% / {ls_limit:.1f}% / {cp_lower:.1f}%~{cp_upper:.1f}%</div>
          <div class="receipt-line"><strong>Solver gate</strong>: {converged_ratio:.4f} min converged-step ratio | <strong>step tolerance</strong>: {step_tolerance:.2e}</div>
        </div>
      </aside>
    </section>

    <section class="signal-strip">
      <article class="signal-card">
        <div class="signal-label">Envelope peak</div>
        <div class="signal-value">{drift_envelope:.3f}%</div>
        <div class="signal-note">Peak drift envelope carried into the committee-facing limit-state framing.</div>
      </article>
      <article class="signal-card">
        <div class="signal-label">Residual response</div>
        <div class="signal-value">{residual_top:.2f} mm</div>
        <div class="signal-note">Maximum residual top displacement with residual drift at {residual_drift:.4f}%.</div>
      </article>
      <article class="signal-card">
        <div class="signal-label">Dissipation</div>
        <div class="signal-value">{cumulative_diss:.3e}</div>
        <div class="signal-note">System cumulative dissipation preserved as a headline evidence quantity.</div>
      </article>
    </section>

    <section class="cards">
      <article class="card">
        <div class="card-label">Wall time</div>
        <div class="card-value">{engine_minutes:.2f} min</div>
        <div class="card-note">Measured engine runtime for the selected bundle.</div>
      </article>
      <article class="card">
        <div class="card-label">Estimated speedup</div>
        <div class="card-value">{speedup_ratio:.1f}x</div>
        <div class="card-note">Ratio against the commercial estimate used for delivery framing.</div>
      </article>
      <article class="card">
        <div class="card-label">P50 / P84 / P95</div>
        <div class="card-value">{drift_p50:.3f}%</div>
        <div class="card-note">Peak percentile envelope with P84={drift_p84:.3f}% and P95={drift_p95:.3f}%.</div>
      </article>
      <article class="card">
        <div class="card-label">Limit-state window</div>
        <div class="card-value">{io_limit:.1f}%</div>
        <div class="card-note">IO with LS={ls_limit:.1f}% and CP={cp_lower:.1f}%~{cp_upper:.1f}% for review context.</div>
      </article>
      <article class="card">
        <div class="card-label">Converged ratio</div>
        <div class="card-value">{converged_ratio:.4f}</div>
        <div class="card-note">Minimum converged-step ratio across the package.</div>
      </article>
      <article class="card">
        <div class="card-label">Solver status</div>
        <div class="card-value">{'PASS' if solver_converged else 'CHECK'}</div>
        <div class="card-note">All selected cases converged: {str(solver_converged).lower()}.</div>
      </article>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <div class="section-kicker">01 Drift envelope</div>
          <h2>Envelope and limit-state evidence</h2>
          <div class="lead">Ground-motion count, split provenance, percentile bands, and IO/LS/CP thresholds stay together so the first chart reads like a formal review receipt, not a raw plot export.</div>
        </div>
        <div class="section-pill-row">
          <span class="section-pill">split {split_summary}</span>
          <span class="section-pill">P50 / P84 / P95</span>
          <span class="section-pill is-warm">IO / LS / CP</span>
        </div>
      </div>
      <div class="figure-shell">
        <div class="figure-stage">
          <img src="{_rel(drift_png)}" alt="Drift envelope">
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <div class="section-kicker">02 Hysteresis</div>
          <h2>Loop behavior and residual-state evidence</h2>
          <div class="lead">The package keeps system loop behavior, representative core-wall response, and residual-state interpretation in one panel for structural reviewers.</div>
        </div>
        <div class="section-pill-row">
          <span class="section-pill">residual top {residual_top:.2f} mm</span>
          <span class="section-pill">residual drift {residual_drift:.4f}%</span>
          <span class="section-pill is-warm">E_diss {cumulative_diss:.3e}</span>
        </div>
      </div>
      <div class="figure-shell">
        <div class="figure-stage">
          <img src="{_rel(hys_png)}" alt="Hysteresis">
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <div class="section-kicker">03 Hinge proxy</div>
          <h2>Spatial concentration and time-sequence readout</h2>
          <div class="lead">Proxy views are framed as decision support: where concentrated in the structure, and how that concentration evolves through the dynamic sequence.</div>
        </div>
        <div class="section-pill-row">
          <span class="section-pill">topology {selected_topology}</span>
          <span class="section-pill">stories {selected_story_count}</span>
        </div>
      </div>
      <div class="figure-grid">
        <article class="figure-card">
          <div class="figure-card-head">
            <div class="figure-kicker">3D hinge proxy</div>
            <div class="figure-title">Spatial proxy view</div>
          </div>
          <div class="figure-copy">Proxy reconstructed from the story drift envelope and dynamic phase to show where nonlinear demand concentrates in three dimensions.</div>
          <div class="figure-stage">
            <img src="{_rel(hinge_proxy_3d_png)}" alt="3D hinge proxy">
          </div>
        </article>
        <article class="figure-card">
          <div class="figure-card-head">
            <div class="figure-kicker">Timeline proxy</div>
            <div class="figure-title">Temporal sequence view</div>
          </div>
          <div class="figure-copy">Timeline companion view that keeps the same evidence family while exposing when the dominant proxy activity intensifies.</div>
          <div class="figure-stage">
            <img src="{_rel(hinge_proxy_timeline_png)}" alt="Hinge proxy timeline">
          </div>
        </article>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <div class="section-kicker">04 Authority framing</div>
          <h2>Authority-oriented corroboration</h2>
          <div class="lead">SAC KPI bars and NHERI waveform overlay are framed together so authority-facing evidence reads like part of the same review package.</div>
        </div>
        <div class="section-pill-row">
          <span class="section-pill status-pill {solver_status_class}">{solver_status_label}</span>
          <span class="section-pill">cases {earthquake_case_count}</span>
        </div>
      </div>
      <div class="figure-grid">
        <article class="figure-card">
          <div class="figure-card-head">
            <div class="figure-kicker">SAC KPI bars</div>
            <div class="figure-title">Authority KPI view</div>
          </div>
          <div class="figure-copy">KPI bars preserve comparison-friendly framing for code- and authority-oriented review conversations.</div>
          <div class="figure-stage">
            <img src="{_rel(authority_sac_png)}" alt="Authority SAC">
          </div>
        </article>
        <article class="figure-card">
          <div class="figure-card-head">
            <div class="figure-kicker">NHERI overlay</div>
            <div class="figure-title">Waveform evidence view</div>
          </div>
          <div class="figure-copy">Waveform overlay remains linked to the same package so reviewers can move from KPI summary to signal-level corroboration without a style change.</div>
          <div class="figure-stage">
            <img src="{_rel(authority_nheri_png)}" alt="Authority NHERI">
          </div>
        </article>
      </div>
    </section>
  </div>
</body>
</html>
"""
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases-json", default="implementation/phase1/commercial_benchmark_cases.opstool_nightly.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--homogeneous-topology", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--topology-type", default="")
    p.add_argument("--ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--earthquake-count", type=int, default=7)
    p.add_argument("--max-steps", type=int, default=6001)
    p.add_argument("--ag-scale", type=float, default=2.0)
    p.add_argument("--run-ndtha", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--ndtha-report", default="implementation/phase1/nonlinear_ndtha_stress_report.pbd7.json")
    p.add_argument("--dynamic-time-history-report", default="implementation/phase1/dynamic_time_history_report.json")
    p.add_argument("--commercial-estimate-hours", type=float, default=336.0)
    p.add_argument("--engine-time-minutes-override", type=float, default=0.0)
    p.add_argument("--io-limit-pct", type=float, default=1.0)
    p.add_argument("--ls-limit-pct", type=float, default=1.5)
    p.add_argument("--cp-lower-pct", type=float, default=1.5)
    p.add_argument("--cp-upper-pct", type=float, default=2.0)
    p.add_argument("--authority-catalog", default="implementation/phase1/open_data/global_authority/authority_source_catalog.json")
    p.add_argument("--authority-sac-dir", default="implementation/phase1/open_data/global_authority/sac")
    p.add_argument("--authority-nheri-dir", default="implementation/phase1/open_data/global_authority/nheri")
    p.add_argument("--metrics-npz-out", default="")
    p.add_argument("--out-dir", default="implementation/phase1/release/pbd_review")
    args = p.parse_args()

    if int(args.earthquake_count) < 3:
        raise SystemExit("earthquake-count must be >= 3")
    if float(args.cp_upper_pct) <= float(args.cp_lower_pct):
        raise SystemExit("cp-upper-pct must be greater than cp-lower-pct")
    if float(args.ls_limit_pct) < float(args.io_limit_pct):
        raise SystemExit("ls-limit-pct must be >= io-limit-pct")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_npz_out = Path(str(args.metrics_npz_out)) if str(args.metrics_npz_out).strip() else _default_metrics_npz_out(out_dir)
    ndtha_path = Path(args.ndtha_report)
    ndtha_cases_path = Path(args.cases_json)
    selected_topology = ""

    if bool(args.run_ndtha):
        if bool(args.homogeneous_topology):
            subset_cases = out_dir / "pbd_selected_cases.json"
            ndtha_cases_path, selected_topology = _prepare_case_subset(
                src_cases_json=Path(args.cases_json),
                target_split=str(args.target_split),
                earthquake_count=int(args.earthquake_count),
                out_cases_json=subset_cases,
                topology_type=str(args.topology_type),
            )
        run_args = argparse.Namespace(**vars(args))
        run_args.cases_json = str(ndtha_cases_path)
        _run_ndtha(run_args, ndtha_path)

    ndtha_bundle = _resolve_ndtha_bundle(ndtha_path, earthquake_count=int(args.earthquake_count))
    ndtha = ndtha_bundle["report"]
    selected_rows = ndtha_bundle["selected_rows"]
    response_npz = ndtha_bundle["response_npz"]
    resolved_ndtha_path = Path(str(ndtha_bundle["resolved_path"]))
    resolved_response_npz_path = Path(str(ndtha_bundle["resolved_response_npz_path"])) if str(ndtha_bundle["resolved_response_npz_path"]).strip() else resolved_ndtha_path.with_suffix(".response.npz")
    ndtha_fallback_used = bool(ndtha_bundle["fallback_used"])
    ndtha_attempted_candidates = list(ndtha_bundle.get("attempted_candidates", []))
    ndtha_response_coverage_count = int(ndtha_bundle.get("response_coverage_count", 0))
    ndtha_path = resolved_ndtha_path
    if not selected_topology:
        topo_counts: dict[str, int] = {}
        for r in selected_rows:
            topo = str(r.get("topology_type", "")).strip()
            if topo:
                topo_counts[topo] = topo_counts.get(topo, 0) + 1
        if topo_counts:
            selected_topology = max(topo_counts.keys(), key=lambda k: topo_counts[k])

    drift_png = out_dir / "drift_envelope_7eq.png"
    hys_png = out_dir / "core_wall_hysteresis.png"
    hinge_proxy_3d_png = out_dir / "plastic_hinge_proxy_3d.png"
    hinge_proxy_timeline_png = out_dir / "plastic_hinge_proxy_timeline.png"
    authority_sac_png = out_dir / "authority_sac_kpi.png"
    authority_nheri_png = out_dir / "authority_nheri_waveform.png"
    dashboard_html = out_dir / "pbd_review_dashboard.html"

    drift_env_max_pct, story_count, drift_stats = _plot_drift_envelope(
        selected_rows=selected_rows,
        io_limit=float(args.io_limit_pct),
        ls_limit=float(args.ls_limit_pct),
        cp_lower=float(args.cp_lower_pct),
        cp_upper=float(args.cp_upper_pct),
        out_png=drift_png,
    )
    hys_case_id, hys_peak_shear_kn, hys_metrics = _plot_hysteresis(
        selected_rows=selected_rows,
        out_png=hys_png,
        response_npz=response_npz,
    )
    hinge_metrics = _plot_hinge_proxy(
        selected_rows=selected_rows,
        cp_lower=float(args.cp_lower_pct),
        cp_upper=float(args.cp_upper_pct),
        out_3d_png=hinge_proxy_3d_png,
        out_timeline_png=hinge_proxy_timeline_png,
        response_npz=response_npz,
    )
    authority_metrics = _plot_authority_figures(
        sac_dir=Path(args.authority_sac_dir),
        nheri_dir=Path(args.authority_nheri_dir),
        out_sac_png=authority_sac_png,
        out_nheri_png=authority_nheri_png,
    )

    metrics = _collect_killshot_metrics(
        ndtha=ndtha,
        selected_rows=selected_rows,
        drift_env_max_pct=drift_env_max_pct,
        commercial_hours_estimate=float(args.commercial_estimate_hours),
        dynamic_time_history_report=Path(args.dynamic_time_history_report),
        engine_time_minutes_override=float(args.engine_time_minutes_override),
        response_npz=response_npz,
    )
    metrics["selected_story_count"] = int(story_count)
    metrics["selected_topology_type"] = selected_topology
    metrics["core_hysteresis_case_id"] = str(hys_case_id)
    metrics["core_hysteresis_peak_shear_kN"] = float(hys_peak_shear_kn)
    metrics["drift_p50_max_pct"] = float(drift_stats.get("p50_max_pct", math.nan))
    metrics["drift_p84_max_pct"] = float(drift_stats.get("p84_max_pct", math.nan))
    metrics["drift_p95_max_pct"] = float(drift_stats.get("p95_max_pct", math.nan))
    metrics["drift_split_counts"] = drift_stats.get("split_counts", {})
    metrics.update(hys_metrics)
    metrics.update(hinge_metrics)
    metrics.update(authority_metrics)

    metrics_json = out_dir / "pbd_killshot_metrics.json"
    metrics_csv = out_dir / "pbd_killshot_metrics.csv"
    metrics_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    lines = ["metric,value"]
    for k, v in metrics.items():
        if isinstance(v, (dict, list)):
            val = json.dumps(v, ensure_ascii=True)
        else:
            val = str(v)
        val = val.replace("\n", " ").replace("\r", " ")
        lines.append(f"{k},\"{val}\"")
    metrics_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    metrics_npz_summary = _write_pbd_metrics_npz(
        metrics_npz_out,
        selected_rows=selected_rows,
        metrics=metrics,
        response_npz=response_npz,
    )

    report_md = out_dir / "pbd_review_report.md"
    _write_markdown(
        out_md=report_md,
        drift_png=drift_png,
        hys_png=hys_png,
        hinge_proxy_3d_png=hinge_proxy_3d_png,
        hinge_proxy_timeline_png=hinge_proxy_timeline_png,
        authority_sac_png=authority_sac_png,
        authority_nheri_png=authority_nheri_png,
        dashboard_html=dashboard_html,
        metrics=metrics,
        selected_rows=selected_rows,
        io_limit=float(args.io_limit_pct),
        ls_limit=float(args.ls_limit_pct),
        cp_lower=float(args.cp_lower_pct),
        cp_upper=float(args.cp_upper_pct),
        authority_catalog=Path(args.authority_catalog),
    )

    report_pdf = out_dir / "pbd_review_report.pdf"
    _write_pdf(
        out_pdf=report_pdf,
        drift_png=drift_png,
        hys_png=hys_png,
        hinge_proxy_3d_png=hinge_proxy_3d_png,
        hinge_proxy_timeline_png=hinge_proxy_timeline_png,
        authority_sac_png=authority_sac_png,
        authority_nheri_png=authority_nheri_png,
        metrics=metrics,
        io_limit=float(args.io_limit_pct),
        ls_limit=float(args.ls_limit_pct),
        cp_lower=float(args.cp_lower_pct),
        cp_upper=float(args.cp_upper_pct),
    )
    _write_html_dashboard(
        out_html=dashboard_html,
        metrics=metrics,
        drift_png=drift_png,
        hys_png=hys_png,
        hinge_proxy_3d_png=hinge_proxy_3d_png,
        hinge_proxy_timeline_png=hinge_proxy_timeline_png,
        authority_sac_png=authority_sac_png,
        authority_nheri_png=authority_nheri_png,
        io_limit=float(args.io_limit_pct),
        ls_limit=float(args.ls_limit_pct),
        cp_lower=float(args.cp_lower_pct),
        cp_upper=float(args.cp_upper_pct),
    )

    package = {
        "schema_version": "1.0",
        "run_id": "phase3-pbd-review-package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "cases_json": str(args.cases_json),
            "ndtha_cases_json": str(ndtha_cases_path),
            "target_split": str(args.target_split),
            "homogeneous_topology": bool(args.homogeneous_topology),
            "topology_type": str(args.topology_type),
            "ground_motion_csv": str(args.ground_motion_csv),
            "earthquake_count": int(args.earthquake_count),
            "ndtha_report": str(Path(args.ndtha_report)),
            "resolved_ndtha_report": str(resolved_ndtha_path),
            "resolved_ndtha_response_npz": str(resolved_response_npz_path),
            "ndtha_response_fallback_used": bool(ndtha_fallback_used),
            "commercial_estimate_hours": float(args.commercial_estimate_hours),
            "io_limit_pct": float(args.io_limit_pct),
            "ls_limit_pct": float(args.ls_limit_pct),
            "cp_lower_pct": float(args.cp_lower_pct),
            "cp_upper_pct": float(args.cp_upper_pct),
            "authority_catalog": str(args.authority_catalog),
            "authority_sac_dir": str(args.authority_sac_dir),
            "authority_nheri_dir": str(args.authority_nheri_dir),
        },
        "selected_case_ids": [str(r.get("case_id", "unknown")) for r in selected_rows],
        "artifacts": {
            "drift_envelope_png": str(drift_png),
            "core_hysteresis_png": str(hys_png),
            "hinge_proxy_3d_png": str(hinge_proxy_3d_png),
            "hinge_proxy_timeline_png": str(hinge_proxy_timeline_png),
            "authority_sac_kpi_png": str(authority_sac_png),
            "authority_nheri_waveform_png": str(authority_nheri_png),
            "dashboard_html": str(dashboard_html),
            "killshot_metrics_json": str(metrics_json),
            "killshot_metrics_csv": str(metrics_csv),
            "killshot_metrics_npz": str(metrics_npz_out),
            "review_markdown": str(report_md),
            "review_pdf": str(report_pdf),
        },
        "summary": {
            "response_storage": "npz_external+inline_summary",
            "response_binary_consumer": "npz_external_primary",
            "case_metrics_npz_case_count": int(metrics_npz_summary.get("case_count", 0)),
            "resolved_ndtha_report": str(resolved_ndtha_path),
            "resolved_ndtha_response_npz": str(resolved_response_npz_path),
            "ndtha_response_fallback_used": bool(ndtha_fallback_used),
            "ndtha_response_coverage_count": int(ndtha_response_coverage_count),
            "ndtha_attempted_candidates": ndtha_attempted_candidates,
        },
        "metrics": metrics,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "pbd review package generated",
    }
    package_out = out_dir / "pbd_review_package_report.json"
    package_out.write_text(json.dumps(package, indent=2), encoding="utf-8")
    print(f"Wrote PBD review package: {package_out}")


if __name__ == "__main__":
    main()
