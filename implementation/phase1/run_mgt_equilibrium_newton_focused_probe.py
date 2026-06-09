#!/usr/bin/env python3
"""Focused equilibrium Newton probe from an accepted checkpoint."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from mgt_equilibrium_replay import run_equilibrium_newton  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_direct_residual_newton_probe import DEFAULT_CHECKPOINT, PRODUCTIZATION  # noqa: E402
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-equilibrium-newton-focused-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_equilibrium_newton_focused_probe.json"


def run_mgt_equilibrium_newton_focused_probe(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
    max_newton_iterations: int = 8,
    residual_tolerance_n: float = 5.0e-4,
    prefer_host_ilu: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    assemble_residual, setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
    )
    u0 = np.asarray(setup_meta["u0"])
    _stiffness, _f_ext, _free, base_residual, _rhs, _meta = assemble_residual(u0)
    base_residual_inf = float(np.max(np.abs(base_residual))) if base_residual.size else 0.0
    newton = run_equilibrium_newton(
        u0=u0,
        assemble_residual=assemble_residual,
        max_newton_iterations=max_newton_iterations,
        residual_tolerance_n=residual_tolerance_n,
        prefer_host_ilu=prefer_host_ilu,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if newton["converged"] else "partial",
        "equilibrium_newton_ready": bool(newton["converged"]),
        "checkpoint": setup_meta.get("checkpoint"),
        "load_scale": setup_meta.get("load_scale"),
        "base_residual_inf_n": base_residual_inf,
        "initial_residual_inf_n": newton.get("initial_residual_inf_n"),
        "final_residual_inf_n": newton.get("final_residual_inf_n"),
        "accepted_newton_iteration_count": newton.get("accepted_newton_iteration_count"),
        "residual_tolerance_n": float(residual_tolerance_n),
        "newton_iterations": newton.get("iterations"),
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "Equilibrium Newton on the physical residual R=F_int-F_ext with tangent J delta_u=-R, "
            "host ILU + ROCm matvec GMRES when available, and residual-norm line search."
        ),
        "blockers": [] if newton["converged"] else ["equilibrium_newton_gate_not_closed"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-newton-iterations", type=int, default=8)
    args = parser.parse_args()
    payload = run_mgt_equilibrium_newton_focused_probe(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.output_json,
        max_newton_iterations=args.max_newton_iterations,
    )
    print(
        "equilibrium-newton-focused:",
        payload["status"],
        f"final={payload.get('final_residual_inf_n')}",
        "->",
        args.output_json,
    )
    return 0 if payload.get("equilibrium_newton_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
