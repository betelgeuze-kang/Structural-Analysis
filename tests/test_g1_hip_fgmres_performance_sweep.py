from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_g1_hip_fgmres_performance_sweep.py"
SPEC = importlib.util.spec_from_file_location("g1_hip_sweep", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = MODULE; SPEC.loader.exec_module(MODULE)


def test_sweep_problem_has_known_unit_solution_and_positive_jacobi() -> None:
    for dimension in MODULE.DIMENSIONS:
        row_ptr, columns, values, rhs = MODULE._problem(dimension)
        result = np.zeros(dimension)
        for row in range(dimension):
            result[row] = sum(values[position] for position in range(row_ptr[row], row_ptr[row + 1]))
        np.testing.assert_array_equal(result, rhs)
        assert values.size == 3 * dimension - 2


def test_fixture_and_checkpoint_binary_headers_are_bound_to_dimension() -> None:
    dimension, nnz, cases = struct.unpack_from("<QQQ", MODULE._fixture_bytes(264), 8)
    assert (dimension, nnz, cases) == (264, 790, 2)
    checkpoint_dimension, iterations, matvecs, restart = struct.unpack_from("<QQQQ", MODULE._checkpoint_bytes(264), 8)
    assert (checkpoint_dimension, iterations, matvecs, restart) == (264, 1, 3, 1)


def test_cpu_reference_converges_with_physical_residual() -> None:
    result = MODULE._cpu_solve(66, 2)
    assert result["iteration_count"] > 0 and result["matvec_count"] > 0
    assert result["maximum_physical_residual_n"] <= 1.0e-9
