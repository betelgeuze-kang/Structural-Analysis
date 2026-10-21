"""Tiny elastic public RC execution demonstrates invocation-local factor reuse."""

import inspect
import json
from pathlib import Path
import runpy

from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear import newton
from structural_analysis.solvers.nonlinear.newton import VECTOR_SPARSE_MATRIX_BACKEND
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    sparse_factorization_reuse_statistics,
)


def test_public_sparse_elastic_steps_reuse_exact_tangent_with_fresh_rhs_receipts(
    monkeypatch,
):
    payload = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/benchmark_native_steel_batch.py"
        )
    )["public_payload"](1, 2)
    # Keep the small generated case in its elastic branch so the tangent is exact.
    payload["loads"][0]["components"]["FY"] = -0.01
    model = load_neutral_json_bytes(json.dumps(payload).encode())
    config = PublicRCFiberFrameConfig(
        load_steps=2, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND
    )
    calls = []
    original = newton.factorize_and_solve_sparse

    def tracked(*args, **kwargs):
        before = sparse_factorization_reuse_statistics()
        solved = original(*args, **kwargs)
        after = sparse_factorization_reuse_statistics()
        calls.append((before, after, solved.diagnostic.to_manifest()))
        return solved

    monkeypatch.setattr(newton, "factorize_and_solve_sparse", tracked)
    first = analyze_public_rc_fiber_frame(model, config)
    first_calls, calls[:] = calls[:], []
    repeated = analyze_public_rc_fiber_frame(model, config)
    second_calls, calls[:] = calls[:], []
    # Unwrap invocation-only reuse decorators for a calculation-equivalent control.
    uncached = inspect.unwrap(analyze_public_rc_fiber_frame)(model, config)

    assert first.status == repeated.status == uncached.status == "ready"
    assert validate_public_rc_fiber_frame_result(first).contract_pass
    assert first.to_dict() == repeated.to_dict() == uncached.to_dict()
    assert first.checkpoint_artifact() == uncached.checkpoint_artifact()
    for invocation in (first_calls, second_calls):
        assert len(invocation) >= 2
        assert invocation[0][0]["hits"] == invocation[0][0]["misses"] == 0
        assert invocation[-1][1]["hits"] >= 1
        assert invocation[-1][1]["publications"] == 1
        receipts = [entry[2] for entry in invocation]
        assert len({entry["input_numeric_hash"] for entry in receipts}) == 1
        assert len({entry["rhs_hash"] for entry in receipts}) > 1
        assert all(entry["contract_pass"] for entry in receipts)
        assert all(not entry["fallback_used"] for entry in receipts)
        assert all(not entry["regularization_used"] for entry in receipts)
    assert calls and all(not entry[0]["active"] for entry in calls)
    assert sparse_factorization_reuse_statistics() == {"active": False}
