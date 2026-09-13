"""Synthetic linear systems exercise the explicit larger sparse Newton scope."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import (
    coo_matrix,
    csc_matrix,
    csr_matrix,
    diags,
    dok_matrix,
    lil_matrix,
)

import structural_analysis.solvers.nonlinear.newton as newton
import structural_analysis.solvers.nonlinear.sparse_factorization as factorization
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKENDS,
    VECTOR_SPARSE_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKENDS,
    NewtonRaphsonConfig,
    newton_raphson_vector,
    sparse_factorization_policy_for_backend,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SparseFactorizationPolicy,
    validate_sparse_factorization_diagnostic_manifest,
)


class _DiagonalProblem:
    case_id = "synthetic_extended_sparse_newton"

    def __init__(self, diagonal: np.ndarray, *, loaded: bool = True) -> None:
        self.matrix = diags(diagonal, format="csr")
        self.rhs = diagonal.copy() if loaded else np.zeros_like(diagonal)

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(self.matrix.shape[0], dtype=np.float64)

    def assemble(self, displacement: np.ndarray):
        return self.matrix @ displacement - self.rhs, self.matrix


@pytest.mark.parametrize(
    "matrix_type", (csr_matrix, csc_matrix, coo_matrix, dok_matrix, lil_matrix)
)
def test_empty_sparse_formats_retain_no_solve_contract_without_dense_copy(
    matrix_type, monkeypatch
):
    class EmptyProblem:
        case_id = "empty_sparse_compatibility"

        def initial_free_displacements_m(self):
            return np.empty(0)

        def assemble(self, _displacement):
            return np.empty(0), matrix_type((0, 0))

    def forbidden(*_args, **_kwargs):
        pytest.fail("empty sparse systems need neither dense conversion nor solve")

    for cls in (csr_matrix, csc_matrix, coo_matrix, dok_matrix, lil_matrix):
        monkeypatch.setattr(cls, "toarray", forbidden)
    monkeypatch.setattr(newton, "_solve_vector_increment", forbidden)
    result = newton_raphson_vector(
        EmptyProblem(),
        config=NewtonRaphsonConfig(
            matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
        ),
    )
    assert result.status == "ready"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["assembly_contract_valid"] is True
    assert result.metrics["reaction_observation_only"] is True
    assert result.metrics["solver_executed"] is False
    assert result.metrics["sparse_factorization_count"] == 0
    assert result.convergence_history == []


def test_extended_policy_changes_only_the_explicit_equation_scope() -> None:
    legacy = sparse_factorization_policy_for_backend(VECTOR_SPARSE_MATRIX_BACKEND)
    extended = sparse_factorization_policy_for_backend(
        VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    )

    assert legacy.to_manifest() == SparseFactorizationPolicy().to_manifest()
    assert legacy.maximum_exact_condition_equations == 256
    assert extended.maximum_exact_condition_equations == 1536
    assert extended.maximum_condition_number_1 == 1.0e12
    assert extended.minimum_normalized_absolute_pivot == 1.0e-14
    assert extended.maximum_backward_error == 1.0e-12
    legacy_body = legacy.to_manifest(include_hash=False)
    extended_body = extended.to_manifest(include_hash=False)
    extended_body["maximum_exact_condition_equations"] = 256
    assert extended_body == legacy_body
    assert extended.policy_hash != legacy.policy_hash
    assert VECTOR_SPARSE_MATRIX_BACKENDS == (
        VECTOR_SPARSE_MATRIX_BACKEND,
        VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    )
    assert VECTOR_MATRIX_BACKENDS == (
        VECTOR_MATRIX_BACKEND,
        *VECTOR_SPARSE_MATRIX_BACKENDS,
    )
    assert NewtonRaphsonConfig().matrix_backend == VECTOR_MATRIX_BACKEND


@pytest.mark.parametrize("backend", (VECTOR_MATRIX_BACKEND, "unknown"))
def test_policy_helper_rejects_backends_without_sparse_diagnostics(backend) -> None:
    with pytest.raises(ValueError, match="unsupported sparse matrix backend"):
        sparse_factorization_policy_for_backend(backend)


@pytest.mark.parametrize("size", (257, 1536))
def test_extended_newton_retains_sparse_receipts_above_legacy_scope(size) -> None:
    problem = _DiagonalProblem(np.full(size, 2.0))
    solution = newton_raphson_vector(
        problem,
        config=NewtonRaphsonConfig(
            matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
        ),
    )

    assert solution.status == "ready"
    assert solution.metrics["contract_pass"] is True
    np.testing.assert_array_equal(solution.free_displacements_m, np.ones(size))
    metrics = solution.metrics
    assert metrics["matrix_backend"] == VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    assert metrics["stiffness_storage"] == "scipy_sparse_csr"
    assert metrics["native_sparse_assembly_used"] is True
    assert metrics["sparse_backend_used"] is True
    assert metrics["sparse_factorization_diagnostics_passed"] is True
    assert metrics["sparse_factorization_count"] == metrics["linear_solve_count"] == 2
    assert metrics["fallback_used"] is False
    assert metrics["regularization_used"] is False
    policy = sparse_factorization_policy_for_backend(
        VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
    ).to_manifest()
    for receipt in metrics["sparse_factorization_diagnostics"]:
        assert validate_sparse_factorization_diagnostic_manifest(receipt) == receipt
        assert receipt["equation_count"] == size
        assert receipt["policy"] == policy
        assert receipt["condition_number_1"] == 1.0


@pytest.mark.parametrize(
    ("backend", "size"),
    (
        (VECTOR_SPARSE_MATRIX_BACKEND, 257),
        (VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND, 1537),
    ),
)
def test_selected_scope_blocks_before_any_factorization_or_dense_fallback(
    monkeypatch, backend, size
) -> None:
    def unexpected_solve(*_args, **_kwargs):
        pytest.fail("an out-of-scope system must not factor or fall back")

    monkeypatch.setattr(factorization, "splu", unexpected_solve)
    monkeypatch.setattr(np.linalg, "solve", unexpected_solve)
    solution = newton_raphson_vector(
        _DiagonalProblem(np.ones(size)),
        config=NewtonRaphsonConfig(matrix_backend=backend),
    )

    assert solution.status == "blocked"
    assert solution.metrics["contract_pass"] is False
    assert (
        solution.metrics["terminal_reason"]
        == "sparse_condition_diagnostic_scope_exceeded"
    )
    assert solution.metrics["sparse_factorization_count"] == 0
    assert solution.metrics["sparse_factorization_diagnostics_passed"] is None
    assert solution.metrics["fallback_used"] is False
    assert solution.metrics["regularization_used"] is False


def test_extended_scope_preserves_strict_condition_failure_and_receipt() -> None:
    solution = newton_raphson_vector(
        _DiagonalProblem(np.asarray([1.0, 1.0e-13])),
        config=NewtonRaphsonConfig(
            matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
        ),
    )

    assert solution.status == "blocked"
    assert (
        solution.metrics["terminal_reason"] == "sparse_condition_number_policy_exceeded"
    )
    assert solution.metrics["sparse_factorization_count"] == 1
    assert solution.metrics["sparse_factorization_diagnostics_passed"] is False
    receipt = solution.metrics["sparse_factorization_diagnostics"][0]
    assert receipt["condition_number_1"] == 1.0e13
    assert receipt["policy"]["maximum_condition_number_1"] == 1.0e12
    assert receipt["policy"]["maximum_exact_condition_equations"] == 1536
    assert validate_sparse_factorization_diagnostic_manifest(receipt) == receipt


def test_extended_scope_cannot_pass_without_factorization_diagnostics(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        newton,
        "_solve_vector_increment",
        lambda _matrix, residual, *, matrix_backend: (np.zeros_like(residual), None),
    )
    solution = newton_raphson_vector(
        _DiagonalProblem(np.ones(2), loaded=False),
        config=NewtonRaphsonConfig(
            matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND
        ),
    )

    assert solution.metrics["residual_gate_passed"] is True
    assert solution.metrics["increment_gate_passed"] is True
    assert solution.status == "blocked"
    assert solution.metrics["contract_pass"] is False
    assert solution.metrics["sparse_factorization_count"] == 0


def test_legacy_increment_retains_default_factorization_call_and_manifest(
    monkeypatch,
) -> None:
    calls = []
    original = newton.factorize_and_solve_sparse

    def legacy_factorization(matrix, rhs):
        solved = original(matrix, rhs)
        calls.append(solved.diagnostic.to_manifest())
        return solved

    monkeypatch.setattr(newton, "factorize_and_solve_sparse", legacy_factorization)
    matrix = diags([2.0, 4.0], format="csr")
    residual = np.asarray([2.0, 4.0])
    increment, receipt = newton._solve_vector_increment(
        matrix, residual, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND
    )

    np.testing.assert_array_equal(increment, [-1.0, -1.0])
    assert calls == [receipt]
    assert receipt == original(matrix, -residual).diagnostic.to_manifest()
