"""Small synthetic public diagnostics regressions; no physical qualification."""

from dataclasses import fields, is_dataclass, replace
from fractions import Fraction
import json

import numpy as np
import pytest
from scipy.sparse import coo_matrix, diags, eye

from structural_analysis.solvers import sparse_generalized_eigen as public
from structural_analysis.solvers import sparse_live_modal_pipeline as live


def _chain():
    rows, columns, stiffness, mass = [], [], [], []
    q = float(1 / 6)
    for index in range(5):
        a, b = index, index + 1
        rows.extend((a, b, a, b))
        columns.extend((a, b, b, a))
        stiffness.extend((1.0, 1.0, -1.0, -1.0))
        mass.extend((2 * q, 2 * q, q, q))
    return (
        coo_matrix((stiffness, (rows, columns)), shape=(6, 6)).tocsr(),
        coo_matrix((mass, (rows, columns)), shape=(6, 6)).tocsr(),
    )


def _assert_exact_transport(original, transported):
    """Compare every source field without using the production serializer."""
    if isinstance(original, Fraction):
        assert set(transported) == {"numerator", "denominator"}
        assert type(transported["numerator"]) is str
        assert type(transported["denominator"]) is str
        assert transported["numerator"] == str(original.numerator)
        assert transported["denominator"] == str(original.denominator)
        assert Fraction(
            int(transported["numerator"]), int(transported["denominator"])
        ) == original
    elif is_dataclass(original):
        assert set(transported) == {field.name for field in fields(original)}
        for field in fields(original):
            _assert_exact_transport(
                getattr(original, field.name), transported[field.name]
            )
    elif isinstance(original, dict):
        assert set(transported) == set(original)
        for name, value in original.items():
            _assert_exact_transport(value, transported[name])
    elif isinstance(original, (tuple, list)):
        assert isinstance(transported, list)
        assert len(transported) == len(original)
        for value, exported in zip(original, transported, strict=True):
            _assert_exact_transport(value, exported)
    else:
        assert transported == original


def _capture_pipeline(monkeypatch, transform=None):
    original = live.LiveModalProofPipeline.run
    seen = []

    def recorded(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if transform is not None:
            result = transform(result)
        seen.append(result)
        return result

    monkeypatch.setattr(live.LiveModalProofPipeline, "run", recorded)
    return seen


def _assert_diagnostics(diagnostics):
    assert diagnostics["schema_version"] == (
        "structural-analysis-sparse-modal-diagnostics.v1"
    )
    assert diagnostics["cost_scope"] == "live_modal_proof_pipeline_only"
    assert diagnostics["serialized_proof_authority_verified"] is False
    assert json.loads(json.dumps(diagnostics, allow_nan=False)) == diagnostics


def _assert_retained(error, pipeline_result, stage):
    diagnostics = error.certificate_diagnostics
    _assert_diagnostics(diagnostics)
    assert error.stage == diagnostics["stage"] == stage
    assert error.cumulative_cost == pipeline_result.cumulative_cost
    assert diagnostics["cumulative_cost"] == pipeline_result.cumulative_cost
    assert error.cumulative_cost["provider_attempts"] > 0
    assert error.cumulative_cost["work_units"] > 0
    _assert_exact_transport(pipeline_result.certificate, diagnostics["certificate"])
    for name in (
        "public_threshold_guard", "stiffness_psd_guard", "mass_spd_guard"
    ):
        _assert_exact_transport(getattr(pipeline_result, name), diagnostics[name])


def test_coupled_success_exports_exact_json_diagnostics(monkeypatch):
    seen = _capture_pipeline(monkeypatch)
    solution = public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    assert len(seen) == 1
    result = seen[0]
    diagnostics = solution.certificate_diagnostics
    _assert_diagnostics(diagnostics)
    assert diagnostics["stage"] == "complete"
    assert diagnostics["cumulative_cost"] == result.cumulative_cost
    assert diagnostics["cumulative_cost"]["provider_attempts"] > 0
    assert (
        diagnostics["cumulative_cost"]["constructors"]
        == diagnostics["cumulative_cost"]["closes"]
    )
    _assert_exact_transport(result.certificate, diagnostics["certificate"])
    _assert_exact_transport(result.certificate.statistics, diagnostics["statistics"])
    for name in (
        "public_threshold_guard", "stiffness_psd_guard", "mass_spd_guard"
    ):
        _assert_exact_transport(getattr(result, name), diagnostics[name])
    shift = diagnostics["public_threshold_guard"]["exact_shift"]
    assert int(shift["denominator"]) > 2**53
    exported = json.loads(json.dumps(solution.to_dict(), allow_nan=False))
    assert exported["certificate_diagnostics"] == diagnostics


@pytest.mark.parametrize("maximum_iterations", [None, 2])
def test_diagonal_preserves_legacy_dictionary_shape(maximum_iterations):
    solution = public.solve_sparse_modal_modes(
        diags([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], format="csr"),
        eye(6, format="csr"), mode_count=1,
        maximum_iterations=maximum_iterations,
    )
    assert solution.certificate_diagnostics is None
    assert "certificate_diagnostics" not in solution.to_dict()
    json.dumps(solution.to_dict(), allow_nan=False)


@pytest.mark.parametrize("maximum_iterations", [0, -1, True, 1.5])
@pytest.mark.parametrize("coupled", [False, True])
def test_invalid_iterations_stop_before_native_operations(
    monkeypatch, maximum_iterations, coupled
):
    matrices = _chain() if coupled else (
        diags(range(6), format="csr"), eye(6, format="csr")
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid public options reached matrix or native work")

    monkeypatch.setattr(public, "_as_csr", forbidden)
    monkeypatch.setattr(public, "eigsh", forbidden)
    monkeypatch.setattr(public, "splu", forbidden)
    monkeypatch.setattr(live.LiveModalProofPipeline, "run", forbidden)
    with pytest.raises(
        public.SparseGeneralizedEigenError, match="maximum_iterations"
    ) as caught:
        public.solve_sparse_modal_modes(
            *matrices, mode_count=1, maximum_iterations=maximum_iterations
        )
    assert caught.value.stage == "input"
    assert caught.value.statistics is None
    assert caught.value.cumulative_cost is None
    assert caught.value.certificate_diagnostics is None


@pytest.mark.parametrize(
    "guard_name", ["public_threshold_guard", "stiffness_psd_guard", "mass_spd_guard"]
)
def test_guard_custody_refusal_preserves_paid_diagnostics(monkeypatch, guard_name):
    def changed(result):
        guard = replace(
            getattr(result, guard_name), stiffness_input_hash="sha256:" + "0" * 64
        )
        return replace(result, **{guard_name: guard})

    seen = _capture_pipeline(monkeypatch, changed)
    with pytest.raises(public.SparseGeneralizedEigenError, match="custody") as caught:
        public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    assert len(seen) == 1
    _assert_retained(caught.value, seen[0], "public_guards")


def test_incomplete_export_retains_successful_pipeline_cost(monkeypatch):
    def changed(result):
        return replace(result, subspace=replace(result.subspace, clusters=()))

    seen = _capture_pipeline(monkeypatch, changed)
    with pytest.raises(
        public.SparseGeneralizedEigenError, match="complete positive prefix"
    ) as caught:
        public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    assert len(seen) == 1
    _assert_retained(caught.value, seen[0], "public_export")


def test_public_residual_failure_retains_successful_pipeline_cost(monkeypatch):
    seen = _capture_pipeline(monkeypatch)

    def wrong_direction(vectors, *args, **kwargs):
        damaged = np.zeros_like(vectors)
        damaged[0, 0] = 1.0
        return damaged

    monkeypatch.setattr(public, "_canonicalize_sparse_clusters", wrong_direction)
    with pytest.raises(
        public.SparseGeneralizedEigenError, match="residual gate"
    ) as caught:
        public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    assert len(seen) == 1
    _assert_retained(caught.value, seen[0], "public_metrics")


def test_final_hash_failure_keeps_cause_and_paid_diagnostics(monkeypatch):
    seen = _capture_pipeline(monkeypatch)
    failure = ValueError("synthetic final hash failure")

    def refuse(*args, **kwargs):
        raise failure

    monkeypatch.setattr(public, "semantic_modes_sha256", refuse)
    with pytest.raises(
        public.SparseGeneralizedEigenError, match="synthetic final hash failure"
    ) as caught:
        public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    assert caught.value.__cause__ is failure
    assert len(seen) == 1
    _assert_retained(caught.value, seen[0], "public_export")


def test_tight_pipeline_budget_preserves_real_spend_and_cause(monkeypatch):
    pipeline = live.LiveModalProofPipeline(
        budget=live.LiveModalPipelineBudget(maximum_count_requests=1)
    )
    monkeypatch.setattr(live, "LiveModalProofPipeline", lambda: pipeline)
    with pytest.raises(public.SparseGeneralizedEigenError) as caught:
        public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    error = caught.value
    cause = error.__cause__
    assert isinstance(cause, live.LiveModalPipelineBudgetExceeded)
    assert cause.__cause__ is not None
    assert error.stage == cause.stage
    assert error.cumulative_cost == cause.cumulative_cost == pipeline.statistics
    assert error.cumulative_cost["provider_attempts"] > 0
    assert error.cumulative_cost["work_units"] > 0
    assert error.cumulative_cost["sealed"] is True
    _assert_diagnostics(error.certificate_diagnostics)
    assert error.certificate_diagnostics["cumulative_cost"] == pipeline.statistics


def test_extraction_failure_keeps_completed_certificate_and_guards(monkeypatch):
    failure = RuntimeError("synthetic extraction failure")

    def refuse(*args, **kwargs):
        raise failure

    monkeypatch.setattr(live.subspace, "extract_certified_sparse_modal_subspace", refuse)
    with pytest.raises(
        public.SparseGeneralizedEigenError, match="synthetic extraction failure"
    ) as caught:
        public.solve_sparse_modal_modes(*_chain(), mode_count=1)
    error = caught.value
    cause = error.__cause__
    assert isinstance(cause, live.LiveModalPipelineError)
    assert cause.__cause__ is failure
    assert error.stage == cause.stage == "extraction"
    assert error.cumulative_cost == cause.cumulative_cost
    assert error.cumulative_cost["provider_attempts"] > 0
    diagnostics = error.certificate_diagnostics
    _assert_diagnostics(diagnostics)
    for name in (
        "certificate", "public_threshold_guard", "stiffness_psd_guard", "mass_spd_guard"
    ):
        assert getattr(cause, name) is not None
        _assert_exact_transport(getattr(cause, name), diagnostics[name])


@pytest.mark.parametrize("arguments", [(), ("failure",), ("a", "b")])
def test_public_error_preserves_legacy_constructor_arguments(arguments):
    error = public.SparseGeneralizedEigenError(*arguments)
    assert error.args == arguments
    assert str(error) == str(ValueError(*arguments))
    assert error.stage is None
    assert error.cumulative_cost is None
    assert error.certificate_diagnostics is None
