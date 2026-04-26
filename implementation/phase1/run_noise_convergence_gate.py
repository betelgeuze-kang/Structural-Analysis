#!/usr/bin/env python3
"""Noise convergence gate using adaptive-damped Newton solver.

Enforces seed-level convergence under stiffness perturbations.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import random

import numpy as np

from experiment_artifact_archive import archive_test_outputs
from newton_adaptive_damping import AdaptiveNewtonConfig, solve_with_adaptive_damping
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "noise convergence gate passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CASES": "invalid or empty cases input",
    "ERR_CONVERGENCE_FAIL": "one or more seed/noise scenarios failed convergence",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cases", "seeds", "stiffness_noise_levels", "out"],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "limit_cases": {"type": "integer", "minimum": 1},
        "seeds": {"type": "string", "minLength": 1},
        "stiffness_noise_levels": {"type": "string", "minLength": 1},
        "stage_noise_thresholds": {"type": "string", "minLength": 1},
        "stagewise_execution": {"type": "boolean"},
        "stop_on_stage_fail": {"type": "boolean"},
        "min_seed_count": {"type": "integer", "minimum": 3},
        "min_topology_types": {"type": "integer", "minimum": 1},
        "min_hazard_types": {"type": "integer", "minimum": 1},
        "min_split_types": {"type": "integer", "minimum": 1},
        "max_iter": {"type": "integer", "minimum": 1},
        "tol": {"type": "number", "exclusiveMinimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _parse_ints(text: str) -> list[int]:
    out = sorted(set(int(t.strip()) for t in str(text).split(",") if t.strip()))
    if not out:
        raise ValueError("empty integer list")
    return out


def _parse_noise_levels(text: str) -> list[float]:
    base = sorted(set(abs(float(t.strip())) for t in str(text).split(",") if t.strip()))
    if not base:
        raise ValueError("empty noise list")
    levels = {0.0}
    for x in base:
        levels.add(-x)
        levels.add(x)
    return sorted(levels)


def _parse_stage_thresholds(text: str) -> list[float]:
    out = sorted(set(max(0.0, float(t.strip())) for t in str(text).split(",") if t.strip()))
    if not out:
        raise ValueError("empty stage threshold list")
    return out


def _load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise ValueError("cases file missing cases[]")
    out = [r for r in rows if isinstance(r, dict)]
    if not out:
        raise ValueError("cases[] empty")
    return out


def _case_key(case: dict) -> tuple[str, str, str]:
    return (
        str(case.get("topology_type", "unknown")),
        str(case.get("hazard_type", "unknown")),
        str(case.get("split", "unknown")),
    )


def _select_diverse_cases(rows: list[dict], limit: int) -> list[dict]:
    if len(rows) <= int(limit):
        return list(rows)
    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        buckets[_case_key(row)].append(row)

    selected: list[dict] = []
    active = sorted(buckets.keys())
    while active and len(selected) < int(limit):
        next_active: list[tuple[str, str, str]] = []
        for key in active:
            bucket = buckets[key]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            if bucket:
                next_active.append(key)
            if len(selected) >= int(limit):
                break
        active = next_active

    if len(selected) < int(limit):
        seen = {str(c.get("case_id", f"id-{i}")) for i, c in enumerate(selected)}
        for row in rows:
            cid = str(row.get("case_id", ""))
            if cid and cid in seen:
                continue
            selected.append(row)
            if len(selected) >= int(limit):
                break
    return selected[: int(limit)]


def _build_stages(noise_levels: list[float], thresholds: list[float]) -> list[dict]:
    stages: list[dict] = []
    seen: set[tuple[float, ...]] = set()
    for idx, thr in enumerate(thresholds, start=1):
        lv = sorted({float(x) for x in noise_levels if abs(float(x)) <= float(thr) + 1e-12})
        if not lv:
            continue
        sig = tuple(lv)
        if sig in seen:
            continue
        seen.add(sig)
        stages.append(
            {
                "stage_id": f"S{idx:02d}_abs_le_{float(thr):g}",
                "threshold_abs_noise_pct": float(thr),
                "noise_levels": lv,
            }
        )

    full = tuple(sorted(float(x) for x in noise_levels))
    if full and full not in seen:
        stages.append(
            {
                "stage_id": f"S{len(stages) + 1:02d}_full",
                "threshold_abs_noise_pct": max(abs(float(x)) for x in noise_levels),
                "noise_levels": list(full),
            }
        )
    return stages


def _case_target(case: dict) -> np.ndarray:
    m = case.get("metrics", {})
    if not isinstance(m, dict):
        m = {}

    def _hf(metric: str, default: float) -> float:
        row = m.get(metric, {})
        if isinstance(row, dict) and "hf" in row:
            return float(row.get("hf", default))
        return float(default)

    # normalized target vector for stable optimization
    return np.array([
        _hf("drift_ratio_pct", 0.02),
        _hf("base_shear_kN", 1000.0) / 1000.0,
        _hf("buckling_factor", 2.0),
    ], dtype=float)


def _build_system(target: np.ndarray, stiffness_scale: float, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = random.Random(int(seed))
    # SPD linear part + mild nonlinearity term
    a = np.array(
        [
            [1.35, 0.04, 0.00],
            [0.05, 1.10, 0.03],
            [0.00, 0.02, 1.25],
        ],
        dtype=float,
    )
    a = a * float(stiffness_scale)
    b = np.array([0.08, 0.06, 0.05], dtype=float)
    x_ref = target.copy()
    # perturb x_ref slightly by seed (simulating observation uncertainty)
    x_ref = x_ref + np.array([rng.uniform(-0.01, 0.01) for _ in range(3)], dtype=float)
    c = a @ x_ref + b * np.tanh(x_ref)
    return a, b, c


def _make_residual_jac(a: np.ndarray, b: np.ndarray, c: np.ndarray):
    def residual_fn(x: np.ndarray) -> np.ndarray:
        return a @ x + b * np.tanh(x) - c

    def jacobian_fn(x: np.ndarray) -> np.ndarray:
        d = 1.0 - np.tanh(x) ** 2
        return a + np.diag(b * d)

    return residual_fn, jacobian_fn


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
    logger = get_logger("phase3.run_noise_convergence_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.atwood_open.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--limit-cases", type=int, default=12)
    p.add_argument("--seeds", default="7,11,19,23,31,47,59")
    p.add_argument("--stiffness-noise-levels", default="5,10")
    p.add_argument("--stage-noise-thresholds", default="0,5,10")
    p.add_argument("--stagewise-execution", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--stop-on-stage-fail", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--min-seed-count", type=int, default=3)
    p.add_argument("--min-topology-types", type=int, default=2)
    p.add_argument("--min-hazard-types", type=int, default=2)
    p.add_argument("--min-split-types", type=int, default=1)
    p.add_argument("--max-iter", type=int, default=80)
    p.add_argument("--tol", type=float, default=1e-6)
    p.add_argument("--out", default="implementation/phase1/noise_convergence_gate_report.json")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "target_split": str(args.target_split),
        "limit_cases": int(args.limit_cases),
        "seeds": str(args.seeds),
        "stiffness_noise_levels": str(args.stiffness_noise_levels),
        "stage_noise_thresholds": str(args.stage_noise_thresholds),
        "stagewise_execution": bool(args.stagewise_execution),
        "stop_on_stage_fail": bool(args.stop_on_stage_fail),
        "min_seed_count": int(args.min_seed_count),
        "min_topology_types": int(args.min_topology_types),
        "min_hazard_types": int(args.min_hazard_types),
        "min_split_types": int(args.min_split_types),
        "max_iter": int(args.max_iter),
        "tol": float(args.tol),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_noise_convergence_gate")
        rows = _load_cases(Path(args.cases))
        seeds = _parse_ints(args.seeds)
        noise_levels = _parse_noise_levels(args.stiffness_noise_levels)
        stage_thresholds = _parse_stage_thresholds(args.stage_noise_thresholds)

        split = str(args.target_split)
        if split != "all":
            rows = [r for r in rows if str(r.get("split", "")) == split]
        if not rows:
            raise ValueError("no cases selected")

        rows = _select_diverse_cases(rows, int(args.limit_cases))
        cfg = AdaptiveNewtonConfig(max_iter=int(args.max_iter), tol=float(args.tol))

        topology_types = {str(r.get("topology_type", "unknown")) for r in rows}
        hazard_types = {str(r.get("hazard_type", "unknown")) for r in rows}
        split_types = {str(r.get("split", "unknown")) for r in rows}

        stage_defs = _build_stages(noise_levels=noise_levels, thresholds=stage_thresholds)
        if not bool(args.stagewise_execution):
            stage_defs = [
                {
                    "stage_id": "S01_full",
                    "threshold_abs_noise_pct": max(abs(float(x)) for x in noise_levels),
                    "noise_levels": sorted(noise_levels),
                }
            ]

        matrix: list[dict] = []
        stage_rows: list[dict] = []
        fail_count = 0
        scenario_count = 0
        for stage in stage_defs:
            stage_id = str(stage["stage_id"])
            stage_levels = [float(x) for x in stage["noise_levels"]]
            stage_scenarios = 0
            stage_fails = 0

            for case in rows:
                cid = str(case.get("case_id", "unknown"))
                target = _case_target(case)
                topo = str(case.get("topology_type", "unknown"))
                hazard = str(case.get("hazard_type", "unknown"))
                case_split = str(case.get("split", "unknown"))
                for seed in seeds:
                    for nl in stage_levels:
                        scenario_count += 1
                        stage_scenarios += 1
                        stiffness_scale = max(0.5, 1.0 + float(nl) / 100.0)
                        a, b, c = _build_system(target, stiffness_scale=stiffness_scale, seed=seed)
                        residual_fn, jac_fn = _make_residual_jac(a, b, c)

                        init = np.array([0.0, 0.0, 0.0], dtype=float)
                        result = solve_with_adaptive_damping(init, residual_fn, jac_fn, cfg)
                        converged = bool(result.get("converged", False))
                        if not converged:
                            fail_count += 1
                            stage_fails += 1

                        matrix.append(
                            {
                                "stage_id": stage_id,
                                "case_id": cid,
                                "topology_type": topo,
                                "hazard_type": hazard,
                                "split": case_split,
                                "seed": int(seed),
                                "stiffness_noise_pct": float(nl),
                                "stiffness_scale": float(stiffness_scale),
                                "converged": converged,
                                "iterations": int(result.get("iterations", 0)),
                                "residual_norm_final": float(result.get("residual_norm_final", math.inf)),
                                "line_search_backtracks": int(result.get("line_search_backtracks", 0)),
                            }
                        )

            stage_pass = bool(stage_scenarios > 0 and stage_fails == 0)
            stage_rows.append(
                {
                    "stage_id": stage_id,
                    "threshold_abs_noise_pct": float(stage["threshold_abs_noise_pct"]),
                    "noise_levels": stage_levels,
                    "scenario_count": int(stage_scenarios),
                    "fail_count": int(stage_fails),
                    "stage_pass": bool(stage_pass),
                    "completed": True,
                }
            )
            if bool(args.stop_on_stage_fail) and not stage_pass:
                break

        planned_stage_count = len(stage_defs)
        completed_stage_count = len(stage_rows)
        stagewise_execution_pass = bool(
            completed_stage_count == planned_stage_count and all(bool(s.get("stage_pass", False)) for s in stage_rows)
        )

        min_seed_count = int(args.min_seed_count)
        min_topology_types = int(args.min_topology_types)
        min_hazard_types = int(args.min_hazard_types)
        min_split_types = int(args.min_split_types)
        has_required_core = {11, 23, 47}.issubset(set(seeds))
        requested_abs_noise_levels = sorted({abs(float(x)) for x in noise_levels if abs(float(x)) > 0.0})
        requested_noise_pairs_present = all(
            (-float(level) in noise_levels and float(level) in noise_levels) for level in requested_abs_noise_levels
        )

        checks = {
            "has_required_seeds": bool(has_required_core),
            "has_seed_diversity": bool(len(seeds) >= min_seed_count),
            "includes_plus_minus_10": (-10.0 in noise_levels and 10.0 in noise_levels),
            "includes_plus_minus_5": (-5.0 in noise_levels and 5.0 in noise_levels),
            "requested_noise_pairs_present": bool(requested_noise_pairs_present),
            "case_diversity_pass": bool(
                len(topology_types) >= min_topology_types
                and len(hazard_types) >= min_hazard_types
                and len(split_types) >= min_split_types
            ),
            "stagewise_execution_pass": bool(stagewise_execution_pass),
            "all_converged": bool(fail_count == 0),
            "scenario_count_nonzero": bool(scenario_count > 0),
        }
        contract_pass = bool(
            checks["has_required_seeds"]
            and checks["has_seed_diversity"]
            and checks["requested_noise_pairs_present"]
            and checks["case_diversity_pass"]
            and checks["stagewise_execution_pass"]
            and checks["all_converged"]
            and checks["scenario_count_nonzero"]
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-noise-convergence-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "selected_case_count": len(rows),
                "seed_count": len(seeds),
                "noise_level_count": len(noise_levels),
                "requested_abs_noise_levels": requested_abs_noise_levels,
                "scenario_count": int(scenario_count),
                "fail_count": int(fail_count),
                "planned_stage_count": int(planned_stage_count),
                "completed_stage_count": int(completed_stage_count),
                "topology_type_count": len(topology_types),
                "hazard_type_count": len(hazard_types),
                "split_type_count": len(split_types),
            },
            "stage_rows": stage_rows,
            "rows": matrix,
            "contract_pass": bool(contract_pass),
            "reason_code": "PASS" if contract_pass else "ERR_CONVERGENCE_FAIL",
            "reason": REASONS["PASS"] if contract_pass else REASONS["ERR_CONVERGENCE_FAIL"],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="noise_convergence_gate",
            paths=[str(args.out), str(args.cases)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, logging.INFO, "noise_convergence.completed", contract_pass=contract_pass, scenarios=scenario_count)
        print(f"Wrote noise convergence gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, InputContractError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-noise-convergence-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name="noise_convergence_gate",
            paths=[str(args.out), str(args.cases)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote noise convergence gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
