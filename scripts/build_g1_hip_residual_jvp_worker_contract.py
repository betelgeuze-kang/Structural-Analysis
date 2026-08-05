#!/usr/bin/env python3
"""Build a contract-test receipt for the production HIP residual/JVP worker.

This script intentionally uses ``execution_kind=contract_test``. It verifies the
worker state machine and physical residual/JVP gate, but it must remain blocked on
actual hardware execution, kernel invocation, HIP Krylov, retained JVP rows, and
accepted-state HIP tangent refresh.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np

from structural_analysis.engine_v2_backends.hip_residual_jvp_worker import (
    HIPRuntimeEvidence,
    execute_hip_residual_jvp_worker_probe,
    validate_hip_residual_jvp_worker_receipt,
)


def _residual(state: np.ndarray) -> np.ndarray:
    x, y = state
    return np.asarray([x * x + 2.0 * y, np.sin(x) - y * y], dtype=np.float64)


def _jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
    x, y = state
    return np.asarray(
        [
            2.0 * x * direction[0] + 2.0 * direction[1],
            np.cos(x) * direction[0] - 2.0 * y * direction[1],
        ],
        dtype=np.float64,
    )


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    runtime = HIPRuntimeEvidence(
        execution_kind="contract_test",
        source_commit_sha=args.source_commit,
        binary_sha256="sha256:" + "0" * 64,
        backend_id="hip_residual_jvp_worker_contract_test",
        device_architecture=None,
        available_device_nodes=(),
        hardware_receipt_hash=None,
        hip_kernel_invocation_count=0,
        residual_kernel_invocation_count=0,
        jvp_kernel_invocation_count=0,
        hip_krylov_solver_used=False,
        accepted_state_tangent_refresh_hip_used=False,
        accepted_state_tangent_refresh_cpu_used=False,
        jvp_rows_retained=False,
        cpu_fallback_used=False,
        regularization_used=False,
        mid_step_d2h_count=0,
    )
    receipt = execute_hip_residual_jvp_worker_probe(
        runtime=runtime,
        accepted_state=[0.4, -0.2],
        direction=[1.0, 0.5],
        residual=_residual,
        jacobian_vector_product=_jvp,
    )
    validate_hip_residual_jvp_worker_receipt(receipt)
    if receipt.directional_gate_passed is not True:
        raise SystemExit("contract_test_directional_gate_failed")
    if receipt.production_path_ready is not False:
        raise SystemExit("contract_test_improperly_promoted_to_production")
    required_blockers = {
        "actual_hip_hardware_execution_missing",
        "hip_kernel_invocation_missing",
        "hip_residual_kernel_invocation_missing",
        "hip_jvp_kernel_invocation_missing",
        "hip_krylov_solver_not_used",
        "jvp_rows_not_retained",
        "accepted_state_tangent_refresh_not_on_hip",
    }
    missing = required_blockers - set(receipt.blockers)
    if missing:
        raise SystemExit("contract_test_required_blockers_missing:" + ",".join(sorted(missing)))
    payload = receipt.to_dict()
    payload["contract_test_only"] = True
    payload["actual_hip_hardware_execution"] = False
    payload["g1_full_load_checkpoint_created"] = False
    _write_json(args.out, payload)
    if args.json:
        print(_serialized(payload), end="")
    else:
        print(
            "G1 HIP residual/JVP worker contract: diagnostic pass | "
            f"production blockers={len(receipt.blockers)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
