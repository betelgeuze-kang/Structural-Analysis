from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.linalg import eigh


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "native" / "cpp"


def _compile_and_run(tmp_path: Path) -> dict[str, np.ndarray]:
    compiler = shutil.which("c++")
    assert compiler is not None, "a C++20 compiler is required for the eigen oracle lane"
    executable = tmp_path / "generalized-eigen-parity"
    command = [
        compiler,
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(CPP / "src" / "solver_cpu"),
        str(CPP / "tests" / "solver_cpu" / "generalized_eigen_parity_dump.cpp"),
        str(CPP / "src" / "solver_cpu" / "generalized_eigen.cpp"),
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


@dataclass(frozen=True)
class EigenCase:
    operator: np.ndarray
    metric: np.ndarray
    scale: np.ndarray
    mode_count: int
    kind: str


def _cases() -> dict[str, EigenCase]:
    return {
        "modal_two": EigenCase(
            np.asarray([[2.0, -1.0], [-1.0, 1.0]], dtype=np.float64),
            np.eye(2, dtype=np.float64),
            np.ones(2, dtype=np.float64),
            2,
            "modal",
        ),
        "modal_scaled": EigenCase(
            np.asarray(
                [[8.0, -2.0, 0.5], [-2.0, 6.0, -1.0], [0.5, -1.0, 5.0]],
                dtype=np.float64,
            ),
            np.asarray(
                [[2.0, 0.2, 0.0], [0.2, 3.0, 0.1], [0.0, 0.1, 1.5]],
                dtype=np.float64,
            ),
            np.asarray([0.25, 1.0, 2.0], dtype=np.float64),
            3,
            "modal",
        ),
        "modal_rigid": EigenCase(
            np.diag([0.0, 4.0, 9.0]).astype(np.float64),
            np.eye(3, dtype=np.float64),
            np.ones(3, dtype=np.float64),
            2,
            "modal",
        ),
        "buckling_singular": EigenCase(
            np.diag([6.0, 8.0, 10.0]).astype(np.float64),
            np.diag([3.0, 2.0, 0.0]).astype(np.float64),
            np.ones(3, dtype=np.float64),
            2,
            "buckling",
        ),
        "buckling_scaled": EigenCase(
            np.asarray(
                [[7.0, -1.0, 0.5], [-1.0, 9.0, -1.5], [0.5, -1.5, 6.0]],
                dtype=np.float64,
            ),
            np.asarray(
                [[2.0, 0.2, 0.0], [0.2, 1.0, 0.1], [0.0, 0.1, 0.5]],
                dtype=np.float64,
            ),
            np.asarray([1.0, 0.2, 3.0], dtype=np.float64),
            3,
            "buckling",
        ),
        "buckling_tiny": EigenCase(
            np.eye(2, dtype=np.float64),
            np.diag([1.0e-15, 0.0]).astype(np.float64),
            np.ones(2, dtype=np.float64),
            1,
            "buckling",
        ),
    }


def _canonical_sign(vector: np.ndarray) -> np.ndarray:
    result = np.asarray(vector, dtype=np.float64).copy()
    pivot = int(np.argmax(np.abs(result)))
    if result[pivot] < 0.0:
        result *= -1.0
    return result


def _oracle(case: EigenCase) -> tuple[np.ndarray, np.ndarray, int]:
    scale = case.scale
    if case.kind == "modal":
        solve_operator = scale[:, None] * case.operator * scale[None, :]
        solve_metric = scale[:, None] * case.metric * scale[None, :]
        values, vectors = eigh(solve_operator, solve_metric, driver="gvd")
        spectral_scale = max(float(np.max(np.abs(values))), 1.0)
        positive = np.flatnonzero(values > 1.0e-12 * spectral_scale)
        rigid_count = int(np.count_nonzero(values <= 1.0e-12 * spectral_scale))
        indices = positive[: case.mode_count]
        solve_vectors = np.column_stack(
            [_canonical_sign(vectors[:, index]) for index in indices]
        )
        physical = scale[:, None] * solve_vectors
        rayleigh = np.asarray(
            [
                float(physical[:, column] @ case.operator @ physical[:, column])
                for column in range(case.mode_count)
            ],
            dtype=np.float64,
        )
        return rayleigh, physical, rigid_count

    solve_stiffness = scale[:, None] * case.operator * scale[None, :]
    solve_geometric = scale[:, None] * case.metric * scale[None, :]
    reciprocals, vectors = eigh(solve_geometric, solve_stiffness, driver="gvd")
    reciprocal_scale = max(float(np.max(np.abs(reciprocals))), np.finfo(float).tiny)
    candidates = [
        (1.0 / float(value), index)
        for index, value in enumerate(reciprocals.tolist())
        if float(value) > 1.0e-12 * reciprocal_scale
    ]
    candidates.sort(key=lambda item: item[0])
    selected = candidates[: case.mode_count]
    solve_vectors = np.column_stack(
        [_canonical_sign(vectors[:, index]) for _value, index in selected]
    )
    physical = scale[:, None] * solve_vectors
    loads = np.asarray(
        [
            float(physical[:, column] @ case.operator @ physical[:, column])
            / float(physical[:, column] @ case.metric @ physical[:, column])
            for column in range(case.mode_count)
        ],
        dtype=np.float64,
    )
    return loads, physical, len(candidates)


def test_dense_generalized_eigen_matches_independent_scipy_oracle(
    tmp_path: Path,
) -> None:
    actual = _compile_and_run(tmp_path)
    for name, case in _cases().items():
        values, shapes, count = _oracle(case)
        np.testing.assert_allclose(
            actual[f"{name}.values"], values, rtol=5.0e-11, atol=5.0e-13, err_msg=name
        )
        for mode in range(case.mode_count):
            np.testing.assert_allclose(
                actual[f"{name}.mode{mode}"],
                shapes[:, mode],
                rtol=5.0e-10,
                atol=5.0e-12,
                err_msg=f"{name}.mode{mode}",
            )
            mode_metrics = actual[f"{name}.mode_metrics{mode}"]
            np.testing.assert_allclose(
                mode_metrics[0], 1.0, rtol=0.0, atol=2.0e-12
            )
            assert mode_metrics[2] <= 1.0e-10
        metrics = actual[f"{name}.metrics"]
        assert metrics[0] == 0.0  # SolverStatus::converged
        assert metrics[-1] == 0.0  # fallback_count
        if case.kind == "modal":
            assert metrics[1] == count
            assert metrics[2] <= 1.0e-10
            assert metrics[3] <= 1.0e-10
        else:
            assert metrics[1] == count
            assert metrics[2] == np.count_nonzero(
                np.linalg.eigvalsh(case.metric)
                > 1.0e-12
                * max(np.max(np.abs(np.linalg.eigvalsh(case.metric))), np.finfo(float).tiny)
            )
            assert metrics[4] <= 1.0e-8
            assert metrics[5] <= 1.0e-8


def test_generalized_eigen_oracle_matrix_covers_required_contract_edges() -> None:
    cases = _cases()
    assert set(cases) == {
        "modal_two",
        "modal_scaled",
        "modal_rigid",
        "buckling_singular",
        "buckling_scaled",
        "buckling_tiny",
    }
    assert np.linalg.matrix_rank(cases["buckling_singular"].metric) == 2
    assert cases["modal_rigid"].operator[0, 0] == 0.0
    assert cases["buckling_tiny"].metric[0, 0] == 1.0e-15
    assert not np.all(cases["modal_scaled"].scale == 1.0)
    assert not np.all(cases["buckling_scaled"].scale == 1.0)
