from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "implementation"
    / "phase1"
    / "run_g1_frame_tangent_fd_epsilon_sweep_probe.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_g1_frame_tangent_fd_epsilon_sweep_probe", SCRIPT_PATH
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_frame_tangent_fd_epsilon_sweep_detects_step_artifact() -> None:
    x = np.asarray([2.0], dtype=np.float64)
    p = np.asarray([1.0], dtype=np.float64)
    tangent_action = np.asarray([0.25], dtype=np.float64)

    def quantized_frame_force(values: np.ndarray) -> np.ndarray:
        exact = 1000.0 + 0.25 * np.asarray(values, dtype=np.float64)
        return np.round(exact, decimals=2)

    summary = probe.frame_tangent_fd_epsilon_sweep_summary(
        x=x,
        p=p,
        frame_component_fn=quantized_frame_force,
        frame_tangent_action=tangent_action,
        residual_inf_n=1.0,
        eps_values=(1.0, 1.0e-6),
        selected_rows=[0],
    )

    assert summary["default_eps_artifact_likely"] is True
    assert summary["fd_step_sensitivity_observed"] is True
    assert summary["best_eps_row"]["eps"] == 1.0
    assert summary["default_eps_row"]["eps"] == probe.DEFAULT_JVP_EPS
    assert summary["default_to_best_gap_ratio"] > 100.0
