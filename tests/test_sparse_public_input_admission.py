"""Public option and malformed-matrix admission without any eigen solve."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from structural_analysis.solvers import sparse_generalized_eigen as public
from structural_analysis.solvers import sparse_live_modal_pipeline as live


_APIS = ("solve_sparse_modal_modes", "solve_sparse_linear_buckling")
_PRE_MATRIX_ENTRIES = []
_SOLVER_ENTRIES = []
_ACCEPTED_OPTION_SENTINELS = []
_MATRIX_CONVERSIONS = []


class _MatrixAdmissionReached(Exception):
    """Stop an accepted option before any matrix conversion."""


@pytest.fixture(scope="module", autouse=True)
def record_admission_boundaries(record_testsuite_property):
    yield
    origin = Path(public.__file__).resolve()
    record_testsuite_property("public_module_origin", str(origin))
    record_testsuite_property(
        "public_module_sha256", hashlib.sha256(origin.read_bytes()).hexdigest()
    )
    record_testsuite_property("unexpected_pre_matrix_entries", len(_PRE_MATRIX_ENTRIES))
    record_testsuite_property("unexpected_solver_entries", len(_SOLVER_ENTRIES))
    record_testsuite_property(
        "accepted_option_sentinel_hits", len(_ACCEPTED_OPTION_SENTINELS)
    )
    record_testsuite_property("matrix_conversion_attempts", len(_MATRIX_CONVERSIONS))


def _forbid(name, attempts):
    def refused(*args, **kwargs):
        attempts.append(name)
        if name in ("issparse", "_as_csr"):
            _PRE_MATRIX_ENTRIES.append(name)
        else:
            _SOLVER_ENTRIES.append(name)
        raise AssertionError(f"Input admission reached forbidden {name}")

    return refused


@pytest.fixture
def no_matrix_or_solver(monkeypatch):
    attempts = {"pre_matrix": [], "solver": []}
    for name in ("issparse", "_as_csr"):
        monkeypatch.setattr(public, name, _forbid(name, attempts["pre_matrix"]))
    for name in ("eigsh", "splu", "_extreme_eigenvalues"):
        monkeypatch.setattr(public, name, _forbid(name, attempts["solver"]))
    monkeypatch.setattr(
        live.LiveModalProofPipeline, "run", _forbid("live pipeline", attempts["solver"])
    )
    return attempts


@pytest.mark.parametrize("api_name", _APIS)
@pytest.mark.parametrize(
    "invalid_limit",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(1.0, id="integral-float"),
        pytest.param(1.5, id="fractional-float"),
        pytest.param("2", id="string"),
        pytest.param(1j, id="complex"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="infinity"),
    ],
)
def test_invalid_iteration_limit_rejected_before_matrix_work(
    no_matrix_or_solver, api_name, invalid_limit
):
    with pytest.raises(public.SparseGeneralizedEigenError) as caught:
        getattr(public, api_name)(
            object(), object(), mode_count=1, maximum_iterations=invalid_limit
        )

    assert str(caught.value) == "maximum_iterations must be a positive integer or None"
    assert caught.value.stage == "input"
    assert caught.value.statistics is None
    assert caught.value.cumulative_cost is None
    assert caught.value.certificate_diagnostics is None
    assert no_matrix_or_solver == {"pre_matrix": [], "solver": []}


@pytest.mark.parametrize("api_name", _APIS)
@pytest.mark.parametrize("valid_limit", [None, 1, 4])
def test_valid_iteration_limit_reaches_matrix_admission(
    no_matrix_or_solver, monkeypatch, api_name, valid_limit
):
    first, second = object(), object()
    marker = _MatrixAdmissionReached()
    observed = []
    monkeypatch.setattr(public, "issparse", lambda value: False)

    def stop(value, name):
        observed.append((value, name))
        _ACCEPTED_OPTION_SENTINELS.append(api_name)
        raise marker

    monkeypatch.setattr(public, "_as_csr", stop)
    with pytest.raises(_MatrixAdmissionReached) as caught:
        getattr(public, api_name)(
            first, second, mode_count=1, maximum_iterations=valid_limit
        )
    assert caught.value is marker
    assert observed == [(first, "stiffness")]
    assert no_matrix_or_solver == {"pre_matrix": [], "solver": []}


@pytest.mark.parametrize("api_name", _APIS)
@pytest.mark.parametrize("matrix_index", [0, 1], ids=["stiffness", "second-matrix"])
def test_unrepresentable_matrix_value_is_a_public_error_before_solver_work(
    monkeypatch, api_name, matrix_index
):
    solver_entries = []
    for name in ("eigsh", "splu", "_extreme_eigenvalues", "_same_shape"):
        monkeypatch.setattr(public, name, _forbid(name, solver_entries))
    monkeypatch.setattr(
        live.LiveModalProofPipeline, "run", _forbid("live pipeline", solver_entries)
    )
    constructor = public.csr_matrix

    def counted_conversion(*args, **kwargs):
        _MATRIX_CONVERSIONS.append(api_name)
        return constructor(*args, **kwargs)

    monkeypatch.setattr(public, "csr_matrix", counted_conversion)
    matrices = [
        [[1 if i == j else 0 for j in range(4)] for i in range(4)] for _ in range(2)
    ]
    matrices[matrix_index][0][0] = 10**1000
    name = (
        "stiffness"
        if matrix_index == 0
        else "mass"
        if api_name == "solve_sparse_modal_modes"
        else "geometric_stiffness_per_unit_load"
    )

    with pytest.raises(public.SparseGeneralizedEigenError) as caught:
        getattr(public, api_name)(*matrices, mode_count=1)

    assert str(caught.value) == f"{name} must be a numeric matrix"
    assert isinstance(caught.value.__cause__, (TypeError, ValueError, OverflowError))
    assert solver_entries == []
