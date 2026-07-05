from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import eye


PHASE1 = Path(__file__).resolve().parent.parent / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

SCRIPT_PATH = PHASE1 / "run_g1_true_newton_mu_sweep_from_active_set_probe.py"
SPEC = importlib.util.spec_from_file_location(
    "run_g1_true_newton_mu_sweep_from_active_set_probe", SCRIPT_PATH
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_mu_sweep_reports_best_descent_for_linear_fixture() -> None:
    target = np.asarray([1.0], dtype=np.float64)

    def residual_fn(x: np.ndarray) -> np.ndarray:
        return np.asarray(x, dtype=np.float64) - target

    summary = probe.true_newton_mu_sweep_summary(
        residual_fn=residual_fn,
        x=np.asarray([0.0], dtype=np.float64),
        k_state=eye(1, format="csr"),
        mu_values=(1.0, 0.1, 0.0),
        regularization_mode="relative_diagonal_shift",
        alphas=(1.0, 0.5),
    )

    assert summary["descent_observed"] is True
    assert summary["best_mu"] == 0.0
    assert summary["best_residual_inf_n"] == 0.0
    assert summary["best_improvement_inf_n"] == 1.0
    assert summary["factorable_mu_count"] == 3
