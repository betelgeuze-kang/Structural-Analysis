#!/usr/bin/env python3
"""Standardize a preconditioned-equilibrium checkpoint for direct-residual resume."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from run_mgt_direct_residual_newton_probe import _load_checkpoint  # noqa: E402
from run_mgt_equilibrium_newton_setup import build_direct_residual_assembler  # noqa: E402
from run_mgt_equilibrium_preconditioned_zero_probe import (  # noqa: E402
    DEFAULT_FINAL_CHECKPOINT,
    PRODUCTIZATION,
    write_preconditioned_checkpoint,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import DEFAULT_MGT  # noqa: E402


SCHEMA_VERSION = "mgt-preconditioned-checkpoint-standardization.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_equilibrium_preconditioned_continuation_checkpoint_standardization.json"
DEFAULT_STANDARD_CHECKPOINT = (
    PRODUCTIZATION / "mgt_equilibrium_preconditioned_continuation_standard_checkpoint.npz"
)


def run_mgt_preconditioned_checkpoint_standardization(
    *,
    mgt_path: Path = DEFAULT_MGT,
    source_checkpoint_npz: Path = DEFAULT_FINAL_CHECKPOINT,
    output_checkpoint_npz: Path = DEFAULT_STANDARD_CHECKPOINT,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    source_meta, source_u, state_history, residual_history = _load_checkpoint(
        source_checkpoint_npz
    )
    assemble_residual, _setup_meta = build_direct_residual_assembler(
        mgt_path=mgt_path,
        checkpoint_npz=source_checkpoint_npz,
    )
    _k, _f_ext, _free, residual, rhs, _meta = assemble_residual(source_u)
    output_meta = write_preconditioned_checkpoint(
        path=output_checkpoint_npz,
        source_checkpoint_npz=source_checkpoint_npz,
        source_checkpoint_meta=source_meta,
        start_u=source_u,
        final_u=source_u,
        start_residual=np.asarray(residual, dtype=np.float64),
        final_residual=np.asarray(residual, dtype=np.float64),
        final_rhs=np.asarray(rhs, dtype=np.float64),
        loaded_state_history=state_history,
        loaded_residual_history=residual_history,
        accepted_iteration_count=int(source_meta.get("accepted_state_history_count") or 0),
    )
    reloaded_meta, reloaded_u, reloaded_state_history, reloaded_residual_history = (
        _load_checkpoint(output_checkpoint_npz)
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready"
        if reloaded_meta.get("checkpoint_schema") == "mgt-direct-residual-newton-state.v1"
        else "partial",
        "source_checkpoint": source_meta,
        "output_checkpoint": output_meta,
        "reloaded_checkpoint": reloaded_meta,
        "state_vector_equal": bool(np.array_equal(source_u, reloaded_u)),
        "state_history_count": (
            int(reloaded_state_history.shape[0])
            if reloaded_state_history is not None and reloaded_state_history.ndim == 2
            else 0
        ),
        "residual_history_count": (
            int(reloaded_residual_history.shape[0])
            if reloaded_residual_history is not None and reloaded_residual_history.ndim == 2
            else 0
        ),
        "runtime_metrics": {"total_seconds": time.perf_counter() - started},
        "claim_boundary": (
            "This receipt standardizes an already accepted preconditioned-equilibrium "
            "checkpoint into the direct-residual Newton checkpoint schema. It does not "
            "claim new residual descent or close the physical residual gate."
        ),
    }
    payload["ready"] = bool(
        payload["status"] == "ready"
        and payload["state_vector_equal"]
        and payload["state_history_count"] >= 1
        and payload["residual_history_count"] >= 1
    )
    payload["blockers"] = [] if payload["ready"] else ["checkpoint_standardization_not_ready"]
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
    parser.add_argument("--source-checkpoint-npz", type=Path, default=DEFAULT_FINAL_CHECKPOINT)
    parser.add_argument("--output-checkpoint-npz", type=Path, default=DEFAULT_STANDARD_CHECKPOINT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = run_mgt_preconditioned_checkpoint_standardization(
        mgt_path=args.mgt_path,
        source_checkpoint_npz=args.source_checkpoint_npz,
        output_checkpoint_npz=args.output_checkpoint_npz,
        output_json=args.output_json,
    )
    print(
        "mgt-preconditioned-checkpoint-standardization:",
        payload.get("status"),
        f"residual={payload.get('output_checkpoint', {}).get('residual_inf_n')}",
        "->",
        args.output_json,
    )
    return 0 if payload.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
