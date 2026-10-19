"""Public tolerance admission only: no numeric matrices or solver execution."""

from __future__ import annotations

import pytest

from structural_analysis.solvers import sparse_generalized_eigen as public
from structural_analysis.solvers import sparse_live_modal_pipeline as live


_SHARED_FIELDS = (
    "symmetry_relative_tolerance",
    "positive_semidefinite_relative_tolerance",
    "cluster_relative_tolerance",
    "residual_relative_tolerance",
    "orthogonality_tolerance",
    "arpack_tolerance",
)
_API_FIELDS = (
    ("solve_sparse_modal_modes", (*_SHARED_FIELDS, "rigid_mode_relative_tolerance")),
    (
        "solve_sparse_linear_buckling",
        (*_SHARED_FIELDS, "finite_mode_relative_tolerance"),
    ),
)
_OPTION_CASES = [
    pytest.param(api, field, id=f"{api}-{field}")
    for api, fields in _API_FIELDS
    for field in fields
]
_INVALID_VALUES = (
    pytest.param(-1, id="negative"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param(None, id="none"),
    pytest.param("invalid", id="invalid-string"),
    pytest.param(1j, id="complex"),
    pytest.param(10**1000, id="overflowing-integer"),
)
_FORBIDDEN_ENTRY_ATTEMPTS = []
_MATRIX_ADMISSION_SENTINEL_HITS = []


class _MatrixAdmissionReached(Exception):
    """A test-only marker emitted before any matrix conversion."""


@pytest.fixture(scope="module", autouse=True)
def _record_zero_numeric_entry(record_testsuite_property):
    yield
    record_testsuite_property(
        "forbidden_matrix_or_native_entry_attempts", len(_FORBIDDEN_ENTRY_ATTEMPTS)
    )
    record_testsuite_property(
        "matrix_admission_sentinel_hits", len(_MATRIX_ADMISSION_SENTINEL_HITS)
    )
    assert _FORBIDDEN_ENTRY_ATTEMPTS == []


@pytest.fixture
def no_numeric_entry(monkeypatch):
    attempts = []

    def forbid(name):
        def refused(*args, **kwargs):
            attempts.append(name)
            _FORBIDDEN_ENTRY_ATTEMPTS.append(name)
            raise AssertionError(f"Tolerance admission reached forbidden {name}")

        return refused

    for name in ("issparse", "_as_csr", "eigsh", "splu"):
        monkeypatch.setattr(public, name, forbid(name))
    monkeypatch.setattr(
        live.LiveModalProofPipeline, "run", forbid("LiveModalProofPipeline.run")
    )
    yield attempts
    assert attempts == []


@pytest.mark.parametrize("api_name,field", _OPTION_CASES)
@pytest.mark.parametrize("bad_value", _INVALID_VALUES)
def test_invalid_tolerance_is_public_input_error_before_any_matrix_work(
    no_numeric_entry, api_name, field, bad_value
):
    api = getattr(public, api_name)
    with pytest.raises(public.SparseGeneralizedEigenError) as caught:
        api(object(), object(), mode_count=1, **{field: bad_value})

    error = caught.value
    assert str(error) == f"{field} must be finite and non-negative"
    assert error.stage == "input"
    assert error.statistics is None
    assert error.cumulative_cost is None
    assert error.certificate_diagnostics is None
    assert error.__cause__ is not None
    assert isinstance(
        error.__cause__, (public.GeneralizedEigenContractError, OverflowError)
    )
    assert not isinstance(error.__cause__, public.SparseGeneralizedEigenError)
    assert no_numeric_entry == []


@pytest.mark.parametrize(
    "api_name,fields", [pytest.param(api, fields, id=api) for api, fields in _API_FIELDS]
)
@pytest.mark.parametrize(
    "valid_value",
    (
        pytest.param(0.0, id="zero"),
        pytest.param(1.0e-9, id="positive-number"),
        pytest.param("1.0e-9", id="convertible-string"),
    ),
)
def test_valid_tolerances_reach_only_matrix_admission_sentinel(
    monkeypatch, no_numeric_entry, api_name, fields, valid_value
):
    first, second = object(), object()
    marker = _MatrixAdmissionReached("input options accepted; matrix work prohibited")
    observed = []

    # Sparse detection is only a type probe here, with no numeric object supplied.
    monkeypatch.setattr(public, "issparse", lambda value: False)

    def stop_before_matrix_conversion(value, name):
        observed.append((value, name))
        _MATRIX_ADMISSION_SENTINEL_HITS.append(api_name)
        raise marker

    monkeypatch.setattr(public, "_as_csr", stop_before_matrix_conversion)
    with pytest.raises(_MatrixAdmissionReached) as caught:
        getattr(public, api_name)(
            first,
            second,
            mode_count=1,
            **{field: valid_value for field in fields},
        )

    assert caught.value is marker
    assert observed == [(first, "stiffness")]
    assert no_numeric_entry == []
