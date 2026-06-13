from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_shell_free_component_state_cleanup import (  # noqa: E402
    _append_residual_history,
    _append_state_history,
    _component_cleanup_dofs,
    _relax_component_state,
)


def test_component_cleanup_dofs_expands_nodes_to_all_six_dofs() -> None:
    dofs = _component_cleanup_dofs(component_nodes={2, 0})

    np.testing.assert_array_equal(
        dofs,
        np.asarray([0, 1, 2, 3, 4, 5, 12, 13, 14, 15, 16, 17], dtype=np.int64),
    )


def test_relax_component_state_scales_only_requested_dofs() -> None:
    u = np.asarray([1.0, -2.0, 3.0, 4.0], dtype=np.float64)
    cleaned, meta = _relax_component_state(
        u=u,
        cleanup_dofs=np.asarray([1, 3, 99], dtype=np.int64),
        relaxation_factor=0.25,
    )

    np.testing.assert_allclose(cleaned, np.asarray([1.0, -0.5, 3.0, 1.0]))
    assert meta["cleanup_dof_count"] == 2
    assert meta["cleanup_max_abs_before_m"] == 4.0
    assert meta["cleanup_max_abs_after_m"] == 1.0
    assert meta["cleanup_delta_linf_m"] == 3.0


def test_append_histories_preserve_checkpoint_schema_alignment() -> None:
    source = np.asarray([1.0, 2.0], dtype=np.float64)
    cleaned = np.asarray([0.0, 2.0], dtype=np.float64)

    states = _append_state_history(
        state_history=np.asarray([[0.5, 2.0]], dtype=np.float64),
        source_u=source,
        cleaned_u=cleaned,
    )
    residuals = _append_residual_history(
        residual_history=None,
        cleaned_residual=np.asarray([0.1, -0.2], dtype=np.float64),
        state_history_count=int(states.shape[0]),
    )

    assert states.shape == (3, 2)
    np.testing.assert_allclose(states[-2], source)
    np.testing.assert_allclose(states[-1], cleaned)
    assert residuals.shape == states.shape
