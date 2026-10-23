import json
from pathlib import Path
import runpy

import numpy as np
import pytest

from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.assembly import stateful_fiber_frame2d_solver as solver
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear.newton import VECTOR_SPARSE_MATRIX_BACKEND


def _numbers(value):
    if isinstance(value, dict):
        return [number for key in sorted(value) for number in _numbers(value[key])]
    if isinstance(value, (tuple, list)):
        return [number for item in value for number in _numbers(item)]
    return [float(value)] if type(value) in (float, int) else []


def test_public_sparse_path_replays_and_restarts_with_existing_authority_gates(
    monkeypatch,
):
    payload = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/benchmark_native_steel_batch.py"
        )
    )["public_payload"](1, 2)
    model = load_neutral_json_bytes(json.dumps(payload).encode())
    calls = []
    original = solver.assemble_stateful_fiber_frame2d_direct_sparse

    def tracked(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result.pattern_nnz)
        return result

    monkeypatch.setattr(
        solver, "assemble_stateful_fiber_frame2d_direct_sparse", tracked
    )
    dense = analyze_public_rc_fiber_frame(model, PublicRCFiberFrameConfig(load_steps=2))
    config = PublicRCFiberFrameConfig(
        load_steps=2, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND
    )
    sparse = analyze_public_rc_fiber_frame(model, config)
    assert (
        calls and sparse.configuration["matrix_backend"] == VECTOR_SPARSE_MATRIX_BACKEND
    )
    assert dense.status == sparse.status == "ready"
    assert validate_public_rc_fiber_frame_result(sparse).contract_pass
    assert (
        sparse.metrics["fallback_count"] == sparse.metrics["regularization_count"] == 0
    )
    for name in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
    ):
        np.testing.assert_allclose(
            _numbers(getattr(sparse, name)),
            _numbers(getattr(dense, name)),
            rtol=1e-12,
            # Force entries include cancellation near zero; 1e-10 N is only
            # the cross-backend comparison floor, not a solver tolerance.
            atol=1e-10,
        )
    restarted = analyze_public_rc_fiber_frame(
        model, config, restart_checkpoint_chain=sparse.checkpoint_artifact()
    )
    assert (
        restarted.status == "ready"
        and validate_public_rc_fiber_frame_result(restarted).contract_pass
    )
    assert restarted.checkpoint_artifact() == sparse.checkpoint_artifact()


@pytest.mark.parametrize("backend", [None, True, "", "gpu", "unknown"])
def test_unknown_cpu_backend_rejected_before_execution(backend):
    with pytest.raises(ValueError, match="matrix_backend"):
        PublicRCFiberFrameConfig(matrix_backend=backend)
