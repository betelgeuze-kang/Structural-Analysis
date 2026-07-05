from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import csr_matrix


PHASE1 = Path(__file__).resolve().parent.parent / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

SCRIPT_PATH = PHASE1 / "run_g1_active_set_load_parameter_probe.py"
SPEC = importlib.util.spec_from_file_location(
    "run_g1_active_set_load_parameter_probe", SCRIPT_PATH
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_active_set_load_parameter_direction_uses_delta_lambda() -> None:
    k_free = csr_matrix([[1.0, 0.0], [0.0, 1.0]])
    residual = np.asarray([2.0, -1.0], dtype=np.float64)
    load_derivative = np.asarray([-10.0, 0.0], dtype=np.float64)

    direction, delta_load, meta = probe.active_set_load_parameter_direction(
        k_free=k_free,
        residual=residual,
        load_derivative=load_derivative,
        active_rows=np.asarray([0, 1], dtype=np.int64),
        displacement_trust_radius_m=0.1,
        load_trust_radius=0.2,
        support_strongest_per_row=1,
    )

    assert abs(delta_load) > 0.0
    assert np.max(np.abs(direction)) <= 0.1
    assert meta["active_linear_residual_inf_n"] < 2.0
    assert meta["support_column_count"] == 2
