from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


PHASE1 = Path(__file__).resolve().parent.parent / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

SCRIPT_PATH = PHASE1 / "run_g1_active_frontier_residual_ownership_probe.py"
SPEC = importlib.util.spec_from_file_location(
    "run_g1_active_frontier_residual_ownership_probe", SCRIPT_PATH
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_residual_ownership_breakdown_infers_external_load_from_components() -> None:
    residual = np.asarray([5.0, -2.0, 0.5], dtype=np.float64)
    component_forces = {
        "frame": np.asarray([1.0, -0.25, 0.1], dtype=np.float64),
        "shell_bending_drilling": np.asarray([0.25, -3.0, 0.2], dtype=np.float64),
    }
    load_derivative = np.asarray([-4.0, -1.0, 0.0], dtype=np.float64)

    result = probe.residual_ownership_breakdown(
        residual=residual,
        component_forces=component_forces,
        free=np.asarray([0, 1, 2], dtype=np.int64),
        node_id=np.asarray([10], dtype=np.int64),
        top_count=2,
        load_derivative=load_derivative,
    )

    top = result["top_rows"][0]
    assert top["residual_n"] == 5.0
    assert top["internal_sum_n"] == 1.25
    assert top["inferred_external_load_n"] == -3.75
    assert top["dominant_internal_component"] == "frame"
    assert top["balance_driver"] == "external_load_balance"
    assert top["node_id"] == 10
    assert top["dof_label"] == "UX"
    assert top["load_derivative_n_per_load"] == -4.0
    assert result["top_row_balance_driver_counts"]["external_load_balance"] == 1


def test_residual_ownership_breakdown_accepts_global_component_arrays() -> None:
    residual = np.asarray([2.0, -3.0], dtype=np.float64)
    frame_global = np.zeros(8, dtype=np.float64)
    shell_global = np.zeros(8, dtype=np.float64)
    frame_global[2] = 0.5
    frame_global[7] = -1.0
    shell_global[2] = 4.0
    shell_global[7] = 0.25

    result = probe.residual_ownership_breakdown(
        residual=residual,
        component_forces={
            "frame": frame_global,
            "shell_bending_drilling": shell_global,
        },
        free=np.asarray([2, 7], dtype=np.int64),
        node_id=np.asarray([100, 101], dtype=np.int64),
        top_count=2,
    )

    top = result["top_rows"][0]
    assert top["global_dof"] == 7
    assert top["node_id"] == 101
    assert top["internal_sum_n"] == -0.75
    assert top["inferred_external_load_n"] == 2.25
    assert top["dominant_internal_component"] == "frame"
    assert result["component_inf_n"]["shell_bending_drilling"] == 4.0
