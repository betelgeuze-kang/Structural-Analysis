"""Plan-bound fixed-rank projection for the Engine v2 Phase 0 AI path.

This module deliberately implements one small numerical primitive.  Candidate
physical free-DOF displacement vectors are mapped to square-root-energy
coordinates with the ExecutionPlan's Jacobi energy map,

``D = 1 / sqrt(diag(K_ff))`` and ``u_free = D x``,

then orthonormalized with deterministic two-pass modified Gram-Schmidt.  A
projection is applied as ``Q(Q^T v)`` through dot/AXPY loops; an explicit
``Q Q^T`` matrix is never constructed.

The artifact retains the source candidates as immutable little-endian FP64
bytes.  Validation can therefore replay basis construction instead of merely
trusting a caller-provided basis hash.  This is a bounded Phase 0 primitive,
not an AI acceptance gate or an authoritative solver result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)

FIXED_RANK_PROJECTION_SCHEMA_VERSION = (
    "structural-analysis-fixed-rank-projection.v1"
)
FIXED_RANK_PROJECTION_ALGORITHM_VERSION = "two_pass_mgs_jacobi_scaled.v1"
MAX_PROJECTION_RANK = 16
DEFAULT_DROP_TOLERANCE = 1.0e-12
_ORTHOGONALITY_TOLERANCE = 1.0e-10


class ProjectionError(ValueError):
    """Fail-closed projection contract error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class ProjectionComplexityReceipt:
    """Exact bounded-work receipt for basis construction and one application.

    ``multiply_count``, ``dot_count``, and ``axpy_count`` describe one call to
    :func:`apply_fixed_rank_projection`.  The orthogonalization fields describe
    the deterministic basis-build replay.  Counts refer to scalar multiplies
    where named ``*_multiply_count`` and vector-kernel invocations where named
    ``dot_count`` or ``axpy_count``.
    """

    n: int
    k: int
    nnz: int
    candidate_count: int
    rank_cap: int
    basis_scaling_multiply_count: int
    orthogonalization_dot_count: int
    orthogonalization_axpy_count: int
    orthogonalization_multiply_count: int
    normalization_divide_count: int
    multiply_count: int
    dot_count: int
    axpy_count: int
    basis_elements: int
    source_vector_elements: int
    dense_projector_elements: int
    max_dense_square_dimension: int
    projection_complexity: str
    orthonormalization_complexity: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True)
class FixedRankProjection:
    """Immutable, plan-bound orthonormal projection basis."""

    schema_version: str
    algorithm_version: str
    plan_hash: str
    operator_hash: str
    pattern_hash: str
    free_dof_count: int
    candidate_count: int
    rank_cap: int
    retained_rank: int
    drop_tolerance: float
    orthogonality_error_frobenius: float
    orthogonality_error_max_abs: float
    scaling_diagonal: np.ndarray
    candidate_vectors: np.ndarray
    basis_q: np.ndarray
    complexity_receipt: ProjectionComplexityReceipt
    projection_hash: str

    def apply(self, vector: Any) -> np.ndarray:
        """Return the immutable implicit projection ``Q(Q^T vector)``."""

        return apply_fixed_rank_projection(self, vector)

    def scale_free_vector(self, vector: Any) -> np.ndarray:
        """Map a physical free-DOF displacement ``u`` to ``x=D^-1 u``."""

        checked = _coerce_free_vector(vector, self.free_dof_count)
        result = checked / self.scaling_diagonal
        if not np.all(np.isfinite(result)):
            _fail(
                "projection_scaled_vector_non_finite",
                "/scaled_vector",
                "Jacobi scaling produced a non-finite vector.",
            )
        return immutable_array(result, dtype="<f8")

    def unscale_free_vector(self, vector: Any) -> np.ndarray:
        """Map a square-root-energy vector ``x`` back to ``u=D x``."""

        checked = _coerce_free_vector(vector, self.free_dof_count)
        result = self.scaling_diagonal * checked
        if not np.all(np.isfinite(result)):
            _fail(
                "projection_unscaled_vector_non_finite",
                "/unscaled_vector",
                "Jacobi unscaling produced a non-finite vector.",
            )
        return immutable_array(result, dtype="<f8")

    def to_manifest(self) -> dict[str, Any]:
        """Return the bounded JSON receipt without embedding O(Nk) values."""

        return _projection_manifest(self, include_projection_hash=True)


def build_fixed_rank_projection(
    plan: ExecutionPlan,
    candidate_vectors: Any,
    *,
    rank_cap: int = MAX_PROJECTION_RANK,
    drop_tolerance: float = DEFAULT_DROP_TOLERANCE,
) -> FixedRankProjection:
    """Build and validate a deterministic fixed-rank projection artifact.

    Candidate columns have shape ``(free_dof_count, candidate_count)``.  The
    count is deliberately bounded by ``rank_cap``; accepting an unbounded
    stream and truncating it silently would invalidate the advertised
    ``O(N k^2)`` construction contract.
    """

    _validate_rank_policy(rank_cap, drop_tolerance)
    try:
        validate_execution_plan(plan)
    except Exception as exc:
        if isinstance(exc, ProjectionError):  # pragma: no cover - defensive
            raise
        raise ProjectionError(
            "projection_execution_plan_invalid",
            "/plan",
            f"ExecutionPlan validation failed: {exc}",
        ) from exc

    free_dofs = plan.array("free_dofs")
    free_dof_count = int(free_dofs.size)
    candidates = _coerce_candidate_matrix(candidate_vectors, free_dof_count)
    candidate_count = int(candidates.shape[1])
    if candidate_count > rank_cap:
        _fail(
            "projection_candidate_count_exceeds_rank_cap",
            "/candidate_vectors/shape/1",
            f"Candidate count {candidate_count} exceeds rank cap {rank_cap}.",
        )

    scaling = _scaling_from_plan(plan)
    basis, dot_count, axpy_count = _two_pass_modified_gram_schmidt(
        scaling,
        candidates,
        drop_tolerance=drop_tolerance,
    )
    retained_rank = int(basis.shape[1])
    if retained_rank == 0:
        _fail(
            "projection_basis_rank_zero",
            "/basis_q",
            "Every candidate was zero or linearly dependent at the drop tolerance.",
        )

    error_frobenius, error_max_abs = _orthogonality_errors(basis)
    if (
        not np.isfinite(error_frobenius)
        or not np.isfinite(error_max_abs)
        or error_frobenius > _ORTHOGONALITY_TOLERANCE
    ):
        _fail(
            "projection_basis_not_orthonormal",
            "/basis_q",
            "Two-pass MGS did not meet the Phase 0 orthogonality tolerance.",
        )

    complexity = _complexity_receipt(
        plan=plan,
        n=free_dof_count,
        k=retained_rank,
        candidate_count=candidate_count,
        rank_cap=rank_cap,
        orthogonalization_dot_count=dot_count,
        orthogonalization_axpy_count=axpy_count,
    )
    provisional = FixedRankProjection(
        schema_version=FIXED_RANK_PROJECTION_SCHEMA_VERSION,
        algorithm_version=FIXED_RANK_PROJECTION_ALGORITHM_VERSION,
        plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        pattern_hash=plan.pattern_hash,
        free_dof_count=free_dof_count,
        candidate_count=candidate_count,
        rank_cap=rank_cap,
        retained_rank=retained_rank,
        drop_tolerance=float(drop_tolerance),
        orthogonality_error_frobenius=error_frobenius,
        orthogonality_error_max_abs=error_max_abs,
        scaling_diagonal=scaling,
        candidate_vectors=candidates,
        basis_q=basis,
        complexity_receipt=complexity,
        projection_hash="sha256:" + ("0" * 64),
    )
    artifact = replace(provisional, projection_hash=_projection_hash(provisional))
    validate_fixed_rank_projection(artifact, expected_plan=plan)
    return artifact


def apply_fixed_rank_projection(
    projection: FixedRankProjection,
    vector: Any,
    *,
    expected_plan: ExecutionPlan | None = None,
) -> np.ndarray:
    """Apply ``Q(Q^T v)`` with exactly ``k`` dot and ``k`` AXPY operations."""

    validate_fixed_rank_projection(projection, expected_plan=expected_plan)
    checked = _coerce_free_vector(vector, projection.free_dof_count)
    result = np.zeros(projection.free_dof_count, dtype="<f8")
    for column_index in range(projection.retained_rank):
        column = projection.basis_q[:, column_index]
        coefficient = float(np.dot(column, checked))
        if not np.isfinite(coefficient):
            _fail(
                "projection_coefficient_non_finite",
                "/projection/coefficients",
                "Projection dot product produced a non-finite coefficient.",
            )
        result += coefficient * column
    if not np.all(np.isfinite(result)):
        _fail(
            "projection_result_non_finite",
            "/projection/result",
            "Projection produced a non-finite result.",
        )
    return immutable_array(result, dtype="<f8")


def validate_fixed_rank_projection(
    projection: FixedRankProjection,
    *,
    expected_plan: ExecutionPlan | None = None,
) -> None:
    """Revalidate storage, plan binding, two-pass MGS replay, and all receipts."""

    if not isinstance(projection, FixedRankProjection):
        _fail(
            "projection_type_invalid",
            "/",
            "Expected a FixedRankProjection instance.",
        )
    if projection.schema_version != FIXED_RANK_PROJECTION_SCHEMA_VERSION:
        _fail(
            "projection_schema_version_mismatch",
            "/schema_version",
            "Unsupported projection schema version.",
        )
    if projection.algorithm_version != FIXED_RANK_PROJECTION_ALGORITHM_VERSION:
        _fail(
            "projection_algorithm_version_mismatch",
            "/algorithm_version",
            "Unsupported projection algorithm version.",
        )
    _validate_rank_policy(projection.rank_cap, projection.drop_tolerance)
    if projection.free_dof_count <= 0:
        _fail(
            "projection_free_dof_count_invalid",
            "/free_dof_count",
            "Free DOF count must be positive.",
        )
    if not 1 <= projection.candidate_count <= projection.rank_cap:
        _fail(
            "projection_candidate_count_invalid",
            "/candidate_count",
            "Candidate count must lie in [1, rank_cap].",
        )
    if not 1 <= projection.retained_rank <= projection.candidate_count:
        _fail(
            "projection_retained_rank_invalid",
            "/retained_rank",
            "Retained rank must lie in [1, candidate_count].",
        )

    expected_shapes = {
        "scaling_diagonal": (projection.free_dof_count,),
        "candidate_vectors": (
            projection.free_dof_count,
            projection.candidate_count,
        ),
        "basis_q": (projection.free_dof_count, projection.retained_rank),
    }
    for name, shape in expected_shapes.items():
        array = getattr(projection, name)
        if not isinstance(array, np.ndarray) or array.dtype.str != "<f8":
            _fail(
                "projection_array_dtype_invalid",
                f"/{name}/dtype",
                f"{name} must use little-endian float64.",
            )
        if array.shape != shape:
            _fail(
                "projection_array_shape_invalid",
                f"/{name}/shape",
                f"Expected {shape}, received {array.shape}.",
            )
        if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
            _fail(
                "projection_array_storage_invalid",
                f"/{name}",
                f"{name} must be C-contiguous and backed by immutable bytes.",
            )
        if not np.all(np.isfinite(array)):
            _fail(
                "projection_array_non_finite",
                f"/{name}",
                f"{name} contains a non-finite value.",
            )
    if np.any(projection.scaling_diagonal <= 0.0):
        _fail(
            "projection_scaling_not_positive",
            "/scaling_diagonal",
            "Every Jacobi scaling entry must be positive.",
        )

    if expected_plan is not None:
        try:
            validate_execution_plan(expected_plan)
        except Exception as exc:
            raise ProjectionError(
                "projection_execution_plan_invalid",
                "/plan",
                f"ExecutionPlan validation failed: {exc}",
            ) from exc
        bindings = (
            (projection.plan_hash, expected_plan.plan_hash, "plan_hash"),
            (projection.operator_hash, expected_plan.operator_hash, "operator_hash"),
            (projection.pattern_hash, expected_plan.pattern_hash, "pattern_hash"),
            (
                projection.free_dof_count,
                int(expected_plan.array("free_dofs").size),
                "free_dof_count",
            ),
        )
        for actual, expected, field in bindings:
            if actual != expected:
                _fail(
                    "projection_plan_binding_mismatch",
                    f"/{field}",
                    f"Projection {field} does not match the ExecutionPlan.",
                )
        expected_scaling = _scaling_from_plan(expected_plan)
        if not np.array_equal(projection.scaling_diagonal, expected_scaling):
            _fail(
                "projection_scaling_plan_mismatch",
                "/scaling_diagonal",
                "Scaling is not 1/sqrt(diag(K_ff)) for the bound plan.",
            )

    replay_basis, replay_dot_count, replay_axpy_count = (
        _two_pass_modified_gram_schmidt(
            projection.scaling_diagonal,
            projection.candidate_vectors,
            drop_tolerance=projection.drop_tolerance,
        )
    )
    if replay_basis.shape != projection.basis_q.shape or not np.array_equal(
        replay_basis, projection.basis_q
    ):
        _fail(
            "projection_basis_replay_mismatch",
            "/basis_q",
            "Basis differs from deterministic two-pass MGS replay.",
        )

    error_frobenius, error_max_abs = _orthogonality_errors(projection.basis_q)
    if (
        error_frobenius != projection.orthogonality_error_frobenius
        or error_max_abs != projection.orthogonality_error_max_abs
    ):
        _fail(
            "projection_orthogonality_receipt_mismatch",
            "/orthogonality_error",
            "Stored orthogonality error differs from the basis.",
        )
    if error_frobenius > _ORTHOGONALITY_TOLERANCE:
        _fail(
            "projection_basis_not_orthonormal",
            "/basis_q",
            "Basis exceeds the Phase 0 orthogonality tolerance.",
        )

    receipt_plan = expected_plan
    if receipt_plan is not None:
        expected_complexity = _complexity_receipt(
            plan=receipt_plan,
            n=projection.free_dof_count,
            k=projection.retained_rank,
            candidate_count=projection.candidate_count,
            rank_cap=projection.rank_cap,
            orthogonalization_dot_count=replay_dot_count,
            orthogonalization_axpy_count=replay_axpy_count,
        )
        if projection.complexity_receipt != expected_complexity:
            _fail(
                "projection_complexity_receipt_mismatch",
                "/complexity_receipt",
                "Complexity receipt does not match exact replay counts.",
            )
    else:
        _validate_complexity_receipt_without_plan(
            projection.complexity_receipt,
            projection=projection,
            dot_count=replay_dot_count,
            axpy_count=replay_axpy_count,
        )

    if projection.projection_hash != _projection_hash(projection):
        _fail(
            "projection_hash_mismatch",
            "/projection_hash",
            "Projection aggregate hash does not match the artifact.",
        )


def _validate_rank_policy(rank_cap: int, drop_tolerance: float) -> None:
    if isinstance(rank_cap, (bool, np.bool_)) or not isinstance(
        rank_cap, (int, np.integer)
    ):
        _fail(
            "projection_rank_cap_invalid",
            "/rank_cap",
            "Rank cap must be an integer.",
        )
    if not 1 <= int(rank_cap) <= MAX_PROJECTION_RANK:
        _fail(
            "projection_rank_cap_invalid",
            "/rank_cap",
            f"Rank cap must lie in [1, {MAX_PROJECTION_RANK}].",
        )
    if (
        isinstance(drop_tolerance, (bool, np.bool_))
        or not isinstance(drop_tolerance, (int, float, np.integer, np.floating))
        or not np.isfinite(drop_tolerance)
        or float(drop_tolerance) <= 0.0
    ):
        _fail(
            "projection_drop_tolerance_invalid",
            "/drop_tolerance",
            "Drop tolerance must be finite and positive.",
        )


def _coerce_candidate_matrix(value: Any, free_dof_count: int) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProjectionError(
            "projection_candidate_vectors_invalid",
            "/candidate_vectors",
            "Candidate vectors cannot be represented as float64.",
        ) from exc
    if array.ndim != 2 or array.shape[0] != free_dof_count or array.shape[1] == 0:
        _fail(
            "projection_candidate_shape_invalid",
            "/candidate_vectors/shape",
            f"Expected shape ({free_dof_count}, m) with m >= 1.",
        )
    if not np.all(np.isfinite(array)):
        _fail(
            "projection_candidate_non_finite",
            "/candidate_vectors",
            "Candidate vectors must contain only finite values.",
        )
    return immutable_array(array, dtype="<f8")


def _coerce_free_vector(value: Any, free_dof_count: int) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProjectionError(
            "projection_vector_invalid",
            "/vector",
            "Vector cannot be represented as float64.",
        ) from exc
    if array.shape != (free_dof_count,):
        _fail(
            "projection_vector_shape_invalid",
            "/vector/shape",
            f"Expected ({free_dof_count},), received {array.shape}.",
        )
    if not np.all(np.isfinite(array)):
        _fail(
            "projection_vector_non_finite",
            "/vector",
            "Projection input must contain only finite values.",
        )
    return immutable_array(array, dtype="<f8")


def _scaling_from_plan(plan: ExecutionPlan) -> np.ndarray:
    free = plan.array("free_dofs")
    stiffness = plan.array("global_stiffness_dense")
    diagonal = np.asarray(stiffness[free, free], dtype="<f8")
    if diagonal.shape != (free.size,) or not np.all(np.isfinite(diagonal)):
        _fail(
            "projection_stiffness_diagonal_non_finite",
            "/plan/compiled_operator/stiffness",
            "K_ff diagonal must be a finite free-DOF vector.",
        )
    if np.any(diagonal <= 0.0):
        indices = np.flatnonzero(diagonal <= 0.0)
        _fail(
            "projection_stiffness_diagonal_not_positive",
            "/plan/compiled_operator/stiffness",
            "K_ff diagonal must be strictly positive; invalid reduced indices "
            + ",".join(str(int(index)) for index in indices[:8]),
        )
    scaling = 1.0 / np.sqrt(diagonal)
    if not np.all(np.isfinite(scaling)) or np.any(scaling <= 0.0):
        _fail(
            "projection_scaling_non_finite",
            "/scaling_diagonal",
            "1/sqrt(diag(K_ff)) produced an invalid scaling value.",
        )
    return immutable_array(scaling, dtype="<f8")


def _two_pass_modified_gram_schmidt(
    scaling: np.ndarray,
    candidates: np.ndarray,
    *,
    drop_tolerance: float,
) -> tuple[np.ndarray, int, int]:
    n, candidate_count = candidates.shape
    columns: list[np.ndarray] = []
    dot_count = 0
    axpy_count = 0
    for candidate_index in range(candidate_count):
        work = np.asarray(
            candidates[:, candidate_index] / scaling, dtype="<f8"
        ).copy()
        if not np.all(np.isfinite(work)):
            _fail(
                "projection_scaled_candidate_non_finite",
                f"/candidate_vectors/{candidate_index}",
                "Jacobi scaling produced a non-finite candidate.",
            )
        reference_norm = _stable_norm(work)
        for _pass_index in range(2):
            for column in columns:
                coefficient = float(np.dot(column, work))
                dot_count += 1
                if not np.isfinite(coefficient):
                    _fail(
                        "projection_mgs_coefficient_non_finite",
                        f"/candidate_vectors/{candidate_index}",
                        "MGS dot product produced a non-finite coefficient.",
                    )
                work -= coefficient * column
                axpy_count += 1
        residual_norm = _stable_norm(work)
        if reference_norm == 0.0 or residual_norm <= drop_tolerance * reference_norm:
            continue
        column = work / residual_norm
        if not np.all(np.isfinite(column)):
            _fail(
                "projection_mgs_normalization_non_finite",
                f"/candidate_vectors/{candidate_index}",
                "MGS normalization produced a non-finite basis column.",
            )
        columns.append(column)
    if columns:
        basis = np.column_stack(columns)
    else:
        basis = np.empty((n, 0), dtype="<f8")
    return immutable_array(basis, dtype="<f8"), dot_count, axpy_count


def _stable_norm(vector: np.ndarray) -> float:
    scale = float(np.max(np.abs(vector))) if vector.size else 0.0
    if scale == 0.0:
        return 0.0
    normalized = vector / scale
    norm = scale * float(np.sqrt(np.dot(normalized, normalized)))
    if not np.isfinite(norm):
        _fail(
            "projection_norm_non_finite",
            "/basis_q",
            "Vector norm overflowed or became non-finite.",
        )
    return norm


def _orthogonality_errors(basis: np.ndarray) -> tuple[float, float]:
    rank = int(basis.shape[1])
    gram_error = basis.T @ basis - np.eye(rank, dtype="<f8")
    frobenius = float(np.linalg.norm(gram_error, ord="fro"))
    max_abs = float(np.max(np.abs(gram_error))) if rank else 0.0
    return frobenius, max_abs


def _complexity_receipt(
    *,
    plan: ExecutionPlan,
    n: int,
    k: int,
    candidate_count: int,
    rank_cap: int,
    orthogonalization_dot_count: int,
    orthogonalization_axpy_count: int,
) -> ProjectionComplexityReceipt:
    nnz = int(plan.array("reduced_csr_column_indices").size)
    return ProjectionComplexityReceipt(
        n=n,
        k=k,
        nnz=nnz,
        candidate_count=candidate_count,
        rank_cap=rank_cap,
        basis_scaling_multiply_count=n * candidate_count,
        orthogonalization_dot_count=orthogonalization_dot_count,
        orthogonalization_axpy_count=orthogonalization_axpy_count,
        orthogonalization_multiply_count=(
            n
            * (
                orthogonalization_dot_count
                + orthogonalization_axpy_count
            )
        ),
        normalization_divide_count=n * k,
        multiply_count=2 * n * k,
        dot_count=k,
        axpy_count=k,
        basis_elements=n * k,
        source_vector_elements=n * candidate_count,
        dense_projector_elements=0,
        max_dense_square_dimension=k,
        projection_complexity="O(Nk)",
        orthonormalization_complexity="O(Nk^2)",
    )


def _validate_complexity_receipt_without_plan(
    receipt: ProjectionComplexityReceipt,
    *,
    projection: FixedRankProjection,
    dot_count: int,
    axpy_count: int,
) -> None:
    if not isinstance(receipt, ProjectionComplexityReceipt):
        _fail(
            "projection_complexity_receipt_invalid",
            "/complexity_receipt",
            "Expected a ProjectionComplexityReceipt.",
        )
    n = projection.free_dof_count
    k = projection.retained_rank
    expected_values: dict[str, int | str] = {
        "n": n,
        "k": k,
        "candidate_count": projection.candidate_count,
        "rank_cap": projection.rank_cap,
        "basis_scaling_multiply_count": n * projection.candidate_count,
        "orthogonalization_dot_count": dot_count,
        "orthogonalization_axpy_count": axpy_count,
        "orthogonalization_multiply_count": n * (dot_count + axpy_count),
        "normalization_divide_count": n * k,
        "multiply_count": 2 * n * k,
        "dot_count": k,
        "axpy_count": k,
        "basis_elements": n * k,
        "source_vector_elements": n * projection.candidate_count,
        "dense_projector_elements": 0,
        "max_dense_square_dimension": k,
        "projection_complexity": "O(Nk)",
        "orthonormalization_complexity": "O(Nk^2)",
    }
    if receipt.nnz < 0:
        _fail(
            "projection_complexity_receipt_invalid",
            "/complexity_receipt/nnz",
            "NNZ must be non-negative.",
        )
    for field, expected in expected_values.items():
        if getattr(receipt, field, None) != expected:
            _fail(
                "projection_complexity_receipt_mismatch",
                f"/complexity_receipt/{field}",
                f"Expected {expected!r}.",
            )
    if receipt.max_dense_square_dimension > k:
        _fail(
            "projection_dense_square_bound_exceeded",
            "/complexity_receipt/max_dense_square_dimension",
            "Dense square dimension exceeds retained rank.",
        )


def _projection_manifest(
    projection: FixedRankProjection,
    *,
    include_projection_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": projection.schema_version,
        "algorithm_version": projection.algorithm_version,
        "plan_binding": {
            "plan_hash": projection.plan_hash,
            "operator_hash": projection.operator_hash,
            "pattern_hash": projection.pattern_hash,
        },
        "free_dof_count": projection.free_dof_count,
        "candidate_count": projection.candidate_count,
        "rank_cap": projection.rank_cap,
        "retained_rank": projection.retained_rank,
        "drop_tolerance": projection.drop_tolerance,
        "orthogonality": {
            "norm": "frobenius",
            "error_frobenius": projection.orthogonality_error_frobenius,
            "error_max_abs": projection.orthogonality_error_max_abs,
            "tolerance": _ORTHOGONALITY_TOLERANCE,
        },
        "arrays": {
            "scaling_diagonal": _array_descriptor(
                "scaling_diagonal", projection.scaling_diagonal
            ),
            "candidate_vectors": _array_descriptor(
                "candidate_vectors", projection.candidate_vectors
            ),
            "basis_q": _array_descriptor("basis_q", projection.basis_q),
        },
        "complexity_receipt": projection.complexity_receipt.to_dict(),
        "implementation_constraints": {
            "basis_construction": "deterministic_two_pass_modified_gram_schmidt",
            "projection_application": "Q(Q^T v)",
            "explicit_dense_projector": False,
            "reverse_mode_autograd": False,
        },
        "claim_boundary": "phase0_fixed_rank_projection_primitive_only",
    }
    if include_projection_hash:
        payload["projection_hash"] = projection.projection_hash
    return payload


def _array_descriptor(name: str, array: np.ndarray) -> dict[str, Any]:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return {
        **metadata,
        "data_hash": array_data_hash(array),
        "content_hash": array_content_hash(metadata, array),
    }


def _projection_hash(projection: FixedRankProjection) -> str:
    return canonical_hash(
        _projection_manifest(projection, include_projection_hash=False)
    )


def _fail(code: str, path: str, message: str) -> None:
    raise ProjectionError(code, path, message)


__all__ = [
    "DEFAULT_DROP_TOLERANCE",
    "FIXED_RANK_PROJECTION_ALGORITHM_VERSION",
    "FIXED_RANK_PROJECTION_SCHEMA_VERSION",
    "MAX_PROJECTION_RANK",
    "FixedRankProjection",
    "ProjectionComplexityReceipt",
    "ProjectionError",
    "apply_fixed_rank_projection",
    "build_fixed_rank_projection",
    "validate_fixed_rank_projection",
]
