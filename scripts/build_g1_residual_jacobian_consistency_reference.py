#!/usr/bin/env python3
"""Build a source-bound reference receipt for the G1 directional gate.

The executed operator is a bounded nonlinear reference used to verify the gate
implementation itself. It is not the production G1 full-mesh operator and cannot
close G1 or HIP readiness.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np

from structural_analysis.solvers.nonlinear.residual_jacobian_consistency import (
    probe_residual_jacobian_directional_consistency,
    validate_directional_receipt,
)


def _residual(state: np.ndarray) -> np.ndarray:
    x, y, z = state
    return np.asarray(
        [
            x * x + 2.0 * y - z,
            np.sin(x) + y * y * y + 0.5 * z,
            x * y + np.exp(0.2 * z),
        ],
        dtype=np.float64,
    )


def _jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
    x, y, z = state
    jacobian = np.asarray(
        [
            [2.0 * x, 2.0, -1.0],
            [np.cos(x), 3.0 * y * y, 0.5],
            [y, x, 0.2 * np.exp(0.2 * z)],
        ],
        dtype=np.float64,
    )
    return jacobian @ direction


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
    receipt = probe_residual_jacobian_directional_consistency(
        source_commit_sha=args.source_commit,
        operator_id="g1_directional_gate_reference_operator.v1",
        backend_id="cpu_fp64_reference",
        accepted_state=np.asarray([0.4, -0.2, 0.7]),
        direction=np.asarray([2.0, -1.0, 0.5]),
        residual=_residual,
        jacobian_vector_product=_jvp,
    )
    validate_directional_receipt(receipt)
    payload = receipt.to_dict()
    payload["g1_operator_executed"] = False
    payload["production_hip_worker_executed"] = False
    payload["full_load_checkpoint_created"] = False
    _write_json(args.out, payload)
    if args.json:
        print(_serialized(payload), end="")
    else:
        print(
            "G1 residual/Jacobian directional reference: "
            f"{'pass' if receipt.consistent_residual_jacobian_newton_gate_passed else 'blocked'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
