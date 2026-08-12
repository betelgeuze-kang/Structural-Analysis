from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "native" / "cpp"


def _compile_and_run(tmp_path: Path) -> dict[str, np.ndarray]:
    compiler = shutil.which("c++")
    assert compiler is not None, "a C++20 compiler is required for the sparse CPU oracle lane"
    executable = tmp_path / "sparse-linear-parity"
    command = [
        compiler,
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(CPP / "src" / "solver_cpu"),
        str(CPP / "tests" / "solver_cpu" / "sparse_linear_parity_dump.cpp"),
        str(CPP / "src" / "solver_cpu" / "sparse_linear.cpp"),
        "-o",
        str(executable),
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    completed = subprocess.run(
        [str(executable)], cwd=ROOT, check=True, capture_output=True, text=True
    )
    parsed: dict[str, np.ndarray] = {}
    for line in completed.stdout.splitlines():
        name, *values = line.split("|")
        assert name and values and name not in parsed
        parsed[name] = np.asarray([float(value) for value in values], dtype=np.float64)
    return parsed


def _cases() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    return {
        "spd5": (
            np.asarray(
                [
                    [4.0, -1.0, 0.0, 0.0, 0.0],
                    [-1.0, 4.0, -1.0, 0.0, 0.0],
                    [0.0, -1.0, 4.0, -1.0, 0.0],
                    [0.0, 0.0, -1.0, 3.0, -1.0],
                    [0.0, 0.0, 0.0, -1.0, 2.0],
                ],
                dtype=np.float64,
            ),
            np.asarray([6.0, -12.0, 18.0, -20.0, 14.0], dtype=np.float64),
        ),
        "irregular6": (
            np.asarray(
                [
                    [10.0, 2.0, 0.0, 0.0, 1.0, 0.0],
                    [2.0, 9.0, -1.0, 0.0, 0.0, 1.0],
                    [0.0, -1.0, 8.0, 2.0, 0.0, 0.0],
                    [0.0, 0.0, 2.0, 7.0, -1.0, 0.0],
                    [1.0, 0.0, 0.0, -1.0, 6.0, 1.0],
                    [0.0, 1.0, 0.0, 0.0, 1.0, 5.0],
                ],
                dtype=np.float64,
            ),
            np.asarray([9.0, -10.5, 6.0, 17.5, -9.0, 10.5], dtype=np.float64),
        ),
        "scaled4": (
            np.diag(np.asarray([1.0e-6, 2.0e-2, 3.0e2, 4.0e6], dtype=np.float64)),
            np.asarray([2.0e-6, -6.0e-2, 1.2e3, -2.0e7], dtype=np.float64),
        ),
        "zero5": (
            np.asarray(
                [
                    [4.0, -1.0, 0.0, 0.0, 0.0],
                    [-1.0, 4.0, -1.0, 0.0, 0.0],
                    [0.0, -1.0, 4.0, -1.0, 0.0],
                    [0.0, 0.0, -1.0, 3.0, -1.0],
                    [0.0, 0.0, 0.0, -1.0, 2.0],
                ],
                dtype=np.float64,
            ),
            np.zeros(5, dtype=np.float64),
        ),
    }


def test_sparse_pcg_matches_independent_numpy_dense_solve(tmp_path: Path) -> None:
    actual = _compile_and_run(tmp_path)
    cases = _cases()
    assert set(actual) == {
        *(f"{name}.solution" for name in cases),
        *(f"{name}.metrics" for name in cases),
    }
    for name, (matrix, right_hand_side) in cases.items():
        expected = np.linalg.solve(matrix, right_hand_side)
        solution = actual[f"{name}.solution"]
        metrics = actual[f"{name}.metrics"]
        np.testing.assert_allclose(
            solution,
            expected,
            rtol=2.0e-12,
            atol=2.0e-12,
            err_msg=name,
        )
        residual = right_hand_side - matrix @ solution
        assert metrics.shape == (7,)
        assert metrics[0] == 0.0  # SolverStatus::converged
        assert metrics[6] == 0.0  # fallback_count
        assert metrics[2] == np.linalg.norm(right_hand_side, ord=np.inf)
        np.testing.assert_allclose(
            metrics[3], np.linalg.norm(residual, ord=np.inf), rtol=0.0, atol=5.0e-14
        )
        np.testing.assert_allclose(
            metrics[4], np.linalg.norm(residual), rtol=0.0, atol=5.0e-14
        )
        assert np.all(np.isfinite(metrics))
        if name == "zero5":
            assert metrics[1] == 0.0
        else:
            assert 1.0 <= metrics[1] <= matrix.shape[0]


def test_sparse_oracle_matrix_covers_irregular_and_scaled_spd_profiles() -> None:
    cases = _cases()
    assert set(cases) == {"spd5", "irregular6", "scaled4", "zero5"}
    for matrix, _ in cases.values():
        np.testing.assert_array_equal(matrix, matrix.T)
        assert np.min(np.linalg.eigvalsh(matrix)) > 0.0
    assert np.count_nonzero(cases["irregular6"][0]) == 20
    assert np.linalg.cond(cases["scaled4"][0]) == 4.0e12
