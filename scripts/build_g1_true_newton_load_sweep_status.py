#!/usr/bin/env python3
"""Build a non-promoting G1 true-Newton load sweep status receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "implementation" / "phase1"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from run_g1_true_newton_reference_candidate import (  # noqa: E402
    run_g1_true_newton_reference_candidate,
)


SCHEMA_VERSION = "g1-true-newton-load-sweep-status.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_true_newton_load_sweep_status.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_LOAD_SCALES = (0.656, 0.75, 1.0)
DEFAULT_MAX_NEWTON_STEPS = 4
DEFAULT_RESIDUAL_GATE_N = 5.0e-4
FULL_LOAD_TOLERANCE = 1.0e-12


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _candidate_row(payload: dict[str, Any]) -> dict[str, Any]:
    true_candidate = payload.get("true_newton_candidate")
    true_candidate = true_candidate if isinstance(true_candidate, dict) else {}
    modified = payload.get("modified_newton_baseline")
    modified = modified if isinstance(modified, dict) else {}
    initial = _float_or_none(true_candidate.get("initial_residual_n"))
    final = _float_or_none(true_candidate.get("final_residual_n"))
    reduction = _float_or_none(true_candidate.get("total_reduction_ratio"))
    residual_descent = bool(
        initial is not None and final is not None and final < initial
    )
    return {
        "load_scale": _float_or_none(payload.get("load_scale")),
        "status": str(payload.get("status") or ""),
        "reason_code": str(payload.get("reason_code") or ""),
        "uses_real_mgt_model": payload.get("uses_real_mgt_model") is True,
        "true_newton_steps": int(true_candidate.get("steps") or 0),
        "true_newton_initial_residual_n": initial,
        "true_newton_final_residual_n": final,
        "true_newton_total_reduction_ratio": reduction,
        "true_newton_monotonic_residual_decrease": bool(
            true_candidate.get("monotonic_residual_decrease") is True
        ),
        "true_newton_residual_descent_observed": residual_descent,
        "true_newton_residual_gate_passed": bool(
            true_candidate.get("residual_gate_passed") is True
        ),
        "true_newton_stop_reason": str(true_candidate.get("stop_reason") or ""),
        "modified_newton_final_residual_n": _float_or_none(
            modified.get("final_residual_n")
        ),
        "true_newton_faster_than_modified": bool(
            payload.get("true_newton_faster_than_modified") is True
        ),
    }


def _parse_load_scales(value: str) -> tuple[float, ...]:
    parsed = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not parsed:
        raise argparse.ArgumentTypeError("at least one load scale is required")
    return parsed


def _full_load_row(rows: list[dict[str, Any]], required_load_scale: float) -> dict[str, Any]:
    for row in rows:
        load_scale = _float_or_none(row.get("load_scale"))
        if load_scale is not None and abs(load_scale - required_load_scale) <= FULL_LOAD_TOLERANCE:
            return row
    return {}


def build_g1_true_newton_load_sweep_status(
    *,
    repo_root: Path = ROOT,
    load_scales: tuple[float, ...] = DEFAULT_LOAD_SCALES,
    required_load_scale: float = 1.0,
    max_newton_steps: int = DEFAULT_MAX_NEWTON_STEPS,
    residual_gate_n: float = DEFAULT_RESIDUAL_GATE_N,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for load_scale in load_scales:
        candidate = run_g1_true_newton_reference_candidate(
            load_scale=float(load_scale),
            max_newton_steps=int(max_newton_steps),
            residual_gate_n=float(residual_gate_n),
            output_json=None,
        )
        rows.append(_candidate_row(candidate))

    observed = [
        float(row["load_scale"])
        for row in rows
        if _float_or_none(row.get("load_scale")) is not None
    ]
    max_attempted_load_scale = max(observed) if observed else None
    full_load = _full_load_row(rows, required_load_scale)
    full_load_attempted = bool(full_load)
    full_load_residual_descent = bool(
        full_load.get("true_newton_residual_descent_observed") is True
    )
    full_load_gate_passed = bool(
        full_load.get("true_newton_residual_gate_passed") is True
    )
    blockers: list[str] = []
    if not full_load_attempted:
        blockers.append("full_load_true_newton_probe_not_attempted")
    if full_load_attempted and not full_load_residual_descent:
        blockers.append("full_load_true_newton_residual_descent_not_observed")
    if not full_load_gate_passed:
        blockers.append("full_load_true_newton_residual_gate_not_passed")
    blockers.extend(
        [
            "full_load_checkpoint_not_created_by_true_newton_sweep",
            "production_rocm_hip_not_executed_by_true_newton_sweep",
            "full_mesh_nonlinear_equilibrium_not_proven_by_true_newton_sweep",
        ]
    )
    status = (
        "partial"
        if full_load_attempted and full_load_residual_descent
        else "blocked"
    )
    contract_pass = bool(rows and all(row["uses_real_mgt_model"] for row in rows))
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_true_newton_load_sweep_status.py"),
                Path("implementation/phase1/run_g1_true_newton_reference_candidate.py"),
                Path("implementation/phase1/run_g1_regularized_reference_newton_candidate.py"),
                Path("implementation/phase1/run_g1_mgt_physical_line_search_smoke.py"),
                Path("implementation/phase1/g1_assembled_tangent_solve.py"),
                Path("implementation/phase1/g1_regularized_direction.py"),
            ],
            reused_evidence=False,
            reuse_policy="executes_non_promoting_true_newton_load_sweep_on_real_mgt_residual",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": contract_pass,
        "evidence_closure_pass": False,
        "promotes_g1_closure": False,
        "summary_line": (
            "G1 true-Newton load sweep: "
            f"{status.upper()} | max_load={max_attempted_load_scale} | "
            f"full_load_descent={full_load_residual_descent} | "
            f"full_load_gate={full_load_gate_passed}"
        ),
        "required_load_scale": float(required_load_scale),
        "max_attempted_load_scale": max_attempted_load_scale,
        "max_newton_steps": int(max_newton_steps),
        "residual_gate_n": float(residual_gate_n),
        "full_load_attempted": full_load_attempted,
        "full_load_true_newton_residual_descent_observed": full_load_residual_descent,
        "full_load_true_newton_residual_gate_passed": full_load_gate_passed,
        "full_load_true_newton_final_residual_n": _float_or_none(
            full_load.get("true_newton_final_residual_n")
        ),
        "full_load_true_newton_total_reduction_ratio": _float_or_none(
            full_load.get("true_newton_total_reduction_ratio")
        ),
        "rows": rows,
        "blockers": blockers,
        "next_actions": [
            "turn_true_newton_full_load_descent_into_loadable_checkpoint_candidate",
            "connect_live_g1_runner_to_same_residual_jacobian_contract",
            "rerun_full_load_hip_newton_lane_with_checkpoint",
        ],
        "claim_boundary": (
            "This receipt records a non-promoting true-Newton load sweep. A full-load "
            "residual descent observation is not a G1 closure, not a full-load "
            "checkpoint, not full-mesh nonlinear equilibrium, and not production "
            "ROCm/HIP residual/JVP proof."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# G1 True-Newton Load Sweep Status",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `max_attempted_load_scale`: `{payload['max_attempted_load_scale']}`",
        f"- `full_load_true_newton_final_residual_n`: `{payload['full_load_true_newton_final_residual_n']}`",
        "",
        "| Load Scale | Steps | Initial Residual N | Final Residual N | Descent | Gate |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            "| "
            f"`{row['load_scale']}` | "
            f"`{row['true_newton_steps']}` | "
            f"`{row['true_newton_initial_residual_n']}` | "
            f"`{row['true_newton_final_residual_n']}` | "
            f"`{row['true_newton_residual_descent_observed']}` | "
            f"`{row['true_newton_residual_gate_passed']}` |"
        )
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Claim Boundary", "", payload["claim_boundary"], ""])
    return "\n".join(lines)


def write_g1_true_newton_load_sweep_status(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    load_scales: tuple[float, ...] = DEFAULT_LOAD_SCALES,
    required_load_scale: float = 1.0,
    max_newton_steps: int = DEFAULT_MAX_NEWTON_STEPS,
    residual_gate_n: float = DEFAULT_RESIDUAL_GATE_N,
) -> dict[str, Any]:
    payload = build_g1_true_newton_load_sweep_status(
        repo_root=repo_root,
        load_scales=load_scales,
        required_load_scale=required_load_scale,
        max_newton_steps=max_newton_steps,
        residual_gate_n=residual_gate_n,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--load-scales", type=_parse_load_scales, default=DEFAULT_LOAD_SCALES)
    parser.add_argument("--required-load-scale", type=float, default=1.0)
    parser.add_argument("--max-newton-steps", type=int, default=DEFAULT_MAX_NEWTON_STEPS)
    parser.add_argument("--residual-gate-n", type=float, default=DEFAULT_RESIDUAL_GATE_N)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_g1_true_newton_load_sweep_status(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
        load_scales=args.load_scales,
        required_load_scale=args.required_load_scale,
        max_newton_steps=args.max_newton_steps,
        residual_gate_n=args.residual_gate_n,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
