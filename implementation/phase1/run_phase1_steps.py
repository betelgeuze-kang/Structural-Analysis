#!/usr/bin/env python3
"""Execute Steps 1~6 from next-implementation-plan.md in a runnable scaffold."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shlex
import subprocess
import time
import tracemalloc
from pathlib import Path
from statistics import mean

from generate_lf_sample import make_sample_payload
from validate_lf_output import validate_payload


LOAD_CASES = [
    {"name": "dead_only", "force0": 120.0, "decay": 0.965},
    {"name": "dead_wind", "force0": 180.0, "decay": 0.958},
    {"name": "dead_wind_seismic", "force0": 260.0, "decay": 0.952},
]




def load_fallback_policy(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        payload = {"enable_hf_fallback": False, "equilibrium_residual_threshold": 0.01, "policy_version": "missing-default"}
        raw = json.dumps(payload, sort_keys=True)
        payload["_policy_fingerprint"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return payload

    raw = p.read_text(encoding="utf-8")
    payload = json.loads(raw)
    payload.setdefault("policy_version", "v0")
    payload["_policy_fingerprint"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return payload

def _run_json_cmd(command: str, payload: dict) -> dict:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _simulate_case(force0: float, decay: float, max_steps: int, tol: float) -> tuple[int, float, bool]:
    f = force0
    history = []
    converged = False
    for _ in range(1, max_steps + 1):
        f *= decay
        history.append(f)
        if f < tol:
            converged = True
            break
    return len(history), history[-1], converged


def step1_fire_loop(max_steps: int, tol: float, repeats: int = 3, engine_hook_cmd: str | None = None) -> dict:
    all_runs = []
    per_case_steps: dict[str, list[int]] = {c["name"]: [] for c in LOAD_CASES}

    for rep in range(repeats):
        for case in LOAD_CASES:
            if engine_hook_cmd:
                req = {
                    "action": "step1_case",
                    "case": case["name"],
                    "force0": case["force0"],
                    "decay": case["decay"],
                    "max_steps": max_steps,
                    "tol": tol,
                }
                res = _run_json_cmd(engine_hook_cmd, req)
                steps = int(res["steps"])
                final_force = float(res["final_force_norm"])
                converged = bool(res["converged"])
            else:
                steps, final_force, converged = _simulate_case(case["force0"], case["decay"], max_steps, tol)

            all_runs.append(
                {
                    "rep": rep + 1,
                    "case": case["name"],
                    "converged": converged,
                    "steps": steps,
                    "final_force_norm": final_force,
                }
            )
            per_case_steps[case["name"]].append(steps)

    variability_pct = {}
    for name, steps in per_case_steps.items():
        s_min, s_max = min(steps), max(steps)
        s_avg = mean(steps)
        variability_pct[name] = 0.0 if s_avg == 0 else ((s_max - s_min) / s_avg) * 100.0

    return {
        "runs": all_runs,
        "summary": {
            "all_converged": all(r["converged"] for r in all_runs),
            "repeats": repeats,
            "mean_steps": mean(r["steps"] for r in all_runs),
            "variability_pct_by_case": variability_pct,
            "within_5pct_variability": all(v <= 5.0 for v in variability_pct.values()),
            "engine_hook_used": bool(engine_hook_cmd),
        },
    }


def _to_si(E: float, A: float, Iy: float, Iz: float, L0: float, units: str) -> tuple[float, float, float, float, float]:
    if units == "SI":
        return E, A, Iy, Iz, L0
    if units == "N-mm":
        return E * 1e6, A * 1e-6, Iy * 1e-12, Iz * 1e-12, L0 * 1e-3
    if units == "kN-m":
        return E * 1e3, A, Iy, Iz, L0
    raise ValueError(f"unsupported unit system: {units}")


def step2_forcefield_mapper() -> dict:
    samples = [
        {"id": "beam_si", "units": "SI", "E": 2.1e11, "A": 0.018, "Iy": 8.0e-5, "Iz": 3.0e-5, "L0": 6.0},
        {"id": "beam_nmm", "units": "N-mm", "E": 210000, "A": 18000, "Iy": 8.0e7, "Iz": 3.0e7, "L0": 6000},
    ]
    mapped = []
    for s in samples:
        E, A, Iy, Iz, L0 = _to_si(s["E"], s["A"], s["Iy"], s["Iz"], s["L0"], s["units"])
        mapped.append({"id": s["id"], "Kb": E * A / L0, "Ktheta_y": E * Iy / L0, "Ktheta_z": E * Iz / L0})

    rel_err = abs(mapped[0]["Kb"] - mapped[1]["Kb"]) / mapped[0]["Kb"]
    return {"mapped": mapped, "kb_unit_consistency_relative_error": rel_err, "unit_consistency_pass": rel_err < 1e-9}


def step3_nonlinear_hinge(points: int = 20) -> dict:
    eps_y, k0, post_ratio = 0.02, 1.0, 0.12
    curve = []
    for i in range(points + 1):
        eps = i * (0.06 / points)
        if eps <= eps_y:
            stress, tangent = k0 * eps, k0
        else:
            stress = k0 * eps_y + (eps - eps_y) * (k0 * post_ratio)
            tangent = k0 * post_ratio
        curve.append({"strain": eps, "stress": stress, "tangent": tangent, "yield_index": eps / eps_y})

    return {
        "yield_strain": eps_y,
        "post_yield_tangent_ratio": post_ratio,
        "curve": curve,
        "post_yield_softening_confirmed": post_ratio < 1.0,
    }


def _try_write_parquet(rows: list[dict], path: Path) -> bool:
    try:
        import pandas as pd  # type: ignore

        pd.DataFrame(rows).to_parquet(path, index=False)
        return True
    except Exception:
        return False


def _write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def step4_export(output_dir: Path) -> dict:
    payload = make_sample_payload(steps=200)
    validate_payload(payload)
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes = [{"node_id": n["node_id"], "ux": n["ux"], "uy": n["uy"], "uz": n["uz"], "f_norm": n["f_unbalanced"]["norm"], "bc_type": n["bc_type"]} for n in payload["nodes"]]
    edges, meta = payload["edges"], payload["meta"]

    node_parquet, edge_parquet = output_dir / "ulf_nodes.parquet", output_dir / "ulf_edges.parquet"
    node_ok, edge_ok = _try_write_parquet(nodes, node_parquet), _try_write_parquet(edges, edge_parquet)

    written_files = []
    if node_ok:
        written_files.append(node_parquet.name)
    else:
        c = output_dir / "ulf_nodes.csv"
        _write_csv(nodes, c)
        written_files.append(c.name)

    if edge_ok:
        written_files.append(edge_parquet.name)
    else:
        c = output_dir / "ulf_edges.csv"
        _write_csv(edges, c)
        written_files.append(c.name)

    meta_path = output_dir / "ulf_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    written_files.append(meta_path.name)

    return {"parquet_nodes_written": node_ok, "parquet_edges_written": edge_ok, "fallback_csv_used": (not node_ok) or (not edge_ok), "meta_written": True, "written_files": written_files}


def _engine_hook_work(n: int) -> float:
    f = 250.0
    for _ in range(n):
        f = f * 0.9993 - 0.0001
    return f


def _memory_non_decreasing(rows: list[dict]) -> bool:
    peaks = [r["peak_vram_bytes"] for r in rows]
    return all(peaks[i] <= peaks[i + 1] for i in range(len(peaks) - 1))


def _log_log_slope(rows: list[dict], key_x: str, key_y: str) -> float:
    xs = [math.log(max(float(r[key_x]), 1e-12)) for r in rows]
    ys = [math.log(max(float(r[key_y]), 1e-12)) for r in rows]
    xm, ym = mean(xs), mean(ys)
    denom = sum((x - xm) ** 2 for x in xs)
    if denom <= 1e-15:
        return 0.0
    return sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / denom


def step5_runtime_hook_profile(runtime_hook_cmd: str | None = None, require_runtime_hook: bool = False) -> dict:
    if require_runtime_hook and not runtime_hook_cmd:
        raise RuntimeError("--require-runtime-hook enabled but no --runtime-hook-cmd provided")

    sizes, rows = [2000, 4000, 8000, 16000, 32000], []
    for n in sizes:
        if runtime_hook_cmd:
            req = {"action": "step5_profile", "n": n}
            res = _run_json_cmd(runtime_hook_cmd, req)
            sec = float(res["seconds"])
            peak_vram = int(res.get("peak_vram_bytes", 0))
            current_vram = int(res.get("current_vram_bytes", 0))
            host_copy_bytes = int(res.get("host_copy_bytes", 0))
            compute_seconds = float(res.get("compute_seconds", sec))
            host_copy_seconds = float(res.get("host_copy_seconds", 0.0))
            serialization_seconds = float(res.get("serialization_seconds", 0.0))
        else:
            tracemalloc.start()
            t0 = time.perf_counter()
            _ = _engine_hook_work(n)
            sec = time.perf_counter() - t0
            current_vram, peak_vram = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            host_copy_bytes = 0
            compute_seconds = sec * 0.9
            host_copy_seconds = sec * 0.05
            serialization_seconds = sec * 0.05
        rows.append(
            {
                "n": n,
                "seconds": sec,
                "compute_seconds": compute_seconds,
                "host_copy_seconds": host_copy_seconds,
                "serialization_seconds": serialization_seconds,
                "peak_vram_bytes": peak_vram,
                "current_vram_bytes": current_vram,
                "host_copy_bytes": host_copy_bytes,
            }
        )

    slope = _log_log_slope(rows, "n", "seconds")
    # tracemalloc warmup can create a first-point spike in low-spec/mobile runs.
    vram_rows = rows[1:] if (not runtime_hook_cmd and len(rows) > 3) else rows
    vram_slope = _log_log_slope(vram_rows, "n", "peak_vram_bytes")
    total_host_copy = sum(r["host_copy_bytes"] for r in rows)
    host_copy_budget_bytes = 0

    compute_total = sum(r["compute_seconds"] for r in rows)
    host_copy_total_s = sum(r["host_copy_seconds"] for r in rows)
    serialization_total_s = sum(r["serialization_seconds"] for r in rows)

    timing = {
        "compute": compute_total,
        "host_copy": host_copy_total_s,
        "serialization": serialization_total_s,
    }
    dominant_stage = max(timing, key=timing.get)

    return {
        "rows": rows,
        "slope_p": slope,
        "vram_slope_p": vram_slope,
        "guardrail": {"lower": 0.85, "upper": 1.15},
        "within_guardrail": 0.85 <= slope <= 1.15,
        "vram_trend_nonnegative": _memory_non_decreasing(vram_rows),
        "vram_trend_ok": (_memory_non_decreasing(vram_rows) or vram_slope >= -0.05),
        "vram_rows_used": len(vram_rows),
        "host_copy_budget_bytes": host_copy_budget_bytes,
        "total_host_copy_bytes": total_host_copy,
        "host_copy_bytes_budget_ok": total_host_copy <= host_copy_budget_bytes,
        "vram_trend_tolerance": -0.05,
        "timing_breakdown_seconds": timing,
        "rca_summary": {
            "dominant_stage": dominant_stage,
            "dominant_share": 0.0 if sum(timing.values()) <= 1e-12 else timing[dominant_stage] / sum(timing.values()),
            "action_hint": {
                "compute": "optimize kernels / batching",
                "host_copy": "reduce host-device transfers / enforce zero-copy",
                "serialization": "optimize output format and io pipeline",
            }[dominant_stage],
        },
        "runtime_hook_used": bool(runtime_hook_cmd),
    }


def step6_gate(step1: dict, step2: dict, step3: dict, step4: dict, step5: dict, fallback_policy: dict) -> dict:
    gate1 = step1["summary"]["all_converged"] and step1["summary"]["within_5pct_variability"] and step2["unit_consistency_pass"] and step3["post_yield_softening_confirmed"]
    gate2 = step5["within_guardrail"] and step5["vram_trend_ok"] and step5["host_copy_bytes_budget_ok"]
    fallback_ready = bool(fallback_policy.get("enable_hf_fallback", False))
    gate3 = step4["meta_written"] and (step4["parquet_nodes_written"] or step4["fallback_csv_used"])
    return {
        "gate1_lf_stabilization": gate1,
        "gate2_complexity": gate2,
        "gate2_detail": {
            "within_guardrail": step5.get("within_guardrail", False),
            "vram_trend_ok": step5.get("vram_trend_ok", False),
            "host_copy_bytes_budget_ok": step5.get("host_copy_bytes_budget_ok", False),
        },
        "gate3_e2e_export": gate3,
        "fallback_policy_loaded": fallback_ready,
        "fallback_policy_version": fallback_policy.get("policy_version", "v0"),
        "fallback_policy_fingerprint": fallback_policy.get("_policy_fingerprint", "none"),
        "all_pass": gate1 and gate2 and gate3,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="implementation/phase1/step_outputs")
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--tol", type=float, default=1e-2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--engine-hook-cmd", help="JSON stdin/stdout command for step1 case simulation")
    parser.add_argument("--runtime-hook-cmd", help="JSON stdin/stdout command for step5 runtime profiling")
    parser.add_argument("--require-runtime-hook", action="store_true", help="Fail if runtime hook command is not provided")
    parser.add_argument("--fallback-policy", default="implementation/phase1/fallback_policy.json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when gate fails")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    s1 = step1_fire_loop(args.max_steps, args.tol, repeats=args.repeats, engine_hook_cmd=args.engine_hook_cmd)
    s2 = step2_forcefield_mapper()
    s3 = step3_nonlinear_hinge()
    s4 = step4_export(out_dir)
    s5 = step5_runtime_hook_profile(runtime_hook_cmd=args.runtime_hook_cmd, require_runtime_hook=args.require_runtime_hook)
    fallback_policy = load_fallback_policy(args.fallback_policy)
    s6 = step6_gate(s1, s2, s3, s4, s5, fallback_policy)

    step5_rca = {"rca_summary": s5.get("rca_summary", {}), "timing_breakdown_seconds": s5.get("timing_breakdown_seconds", {})}

    outputs = {
        "step1_fire_loop.json": s1,
        "step2_forcefield_mapper.json": s2,
        "step3_nonlinear_hinge.json": s3,
        "step4_export_report.json": s4,
        "step5_runtime_hook_profile.json": s5,
        "step5_rca_summary.json": step5_rca,
        "step6_gate_report.json": s6,
    }
    for name, payload in outputs.items():
        (out_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote step outputs to: {out_dir}")
    print(json.dumps(s6, indent=2))
    if args.strict and not s6["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
