"""Sparse fixed-rank coarse correction for the Engine v2 CPU FGMRES oracle.

The coarse space is compiled from physical free-DOF candidate modes without
materializing a dense ``N x N`` projector.  Candidate modes are mapped to
Jacobi square-root-energy coordinates, orthonormalized by deterministic
two-pass modified Gram-Schmidt, and mapped back to physical coordinates.

For physical basis ``Z`` and reduced sparse operator ``A`` the retained small
operator is ``E = Z.T A Z``.  One right-preconditioner application is

``z_c = Z E^-1 Z.T r``
``M^-1 r = z_c + diag(A)^-1 (r - A z_c)``.

``A Z`` is retained, so an application costs ``O(Nk + k^2)`` for fixed
``k <= 16`` and performs no additional CSR matvec.  This module is a
deterministic CPU diagnostic and a concrete integration seam for a later HIP
AMG/DD hierarchy.  It is not evidence of AMG, domain decomposition,
mesh-independent iteration counts, end-to-end ``O(N)``, or product readiness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)

from .cpu_fgmres import (
    CpuFgmresArrayDescriptor,
    CpuFgmresReferenceError,
    FgmresPolicyV1,
    FgmresRestartRecord,
    FgmresStatus,
    _array_descriptor,
    _csr_matvec,
    _fgmres_core,
    _finite_dot,
    _initial_reduced_state,
    _linf,
    _positive_jacobi_inverse,
    _stable_l2,
    _validate_result_semantics,
    validate_fgmres_policy_v1,
)

CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION = (
    "structural-analysis-cpu-fgmres-fixed-rank-coarse-space.v1"
)
CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION = (
    "structural-analysis-cpu-fgmres-fixed-rank-coarse-result.v1"
)
CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1 = (
    "phase0_cpu_sparse_fixed_rank_multiplicative_coarse_fgmres_reference"
)
CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1 = (
    "jacobi_energy_two_pass_mgs_multiplicative_coarse.v1"
)

MAX_CPU_FGMRES_COARSE_RANK_V1 = 16
DEFAULT_CPU_FGMRES_COARSE_DROP_TOLERANCE_V1 = 1.0e-12
DEFAULT_CPU_FGMRES_COARSE_CONDITION_LIMIT_V1 = 1.0e12
_ORTHOGONALITY_TOLERANCE = 1.0e-10
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARTIFACT_ARRAY_NAMES = (
    "inverse_sqrt_diagonal",
    "candidate_vectors",
    "scaled_basis_q",
    "physical_basis_z",
    "operator_basis_az",
    "coarse_operator_e",
    "coarse_cholesky_l",
)
_RESULT_ARRAY_NAMES = ("reduced_solution", "true_residual")


class CpuFgmresFixedRankCoarseError(RuntimeError):
    """Fail-closed coarse-space error with a stable code and JSON path."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class CpuFgmresCoarseArrayDescriptorV1:
    """Hash-only descriptor for one immutable coarse-space array."""

    name: str
    dtype: str
    shape: tuple[int, ...]
    byte_length: int
    data_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
        }


@dataclass(frozen=True, slots=True)
class CpuFgmresCoarseComplexityReceiptV1:
    """Exact bounded dimensions and vector-kernel counts for the artifact."""

    free_dof_count: int
    reduced_nnz: int
    candidate_count: int
    retained_rank: int
    rank_cap: int
    basis_scaling_multiply_count: int
    orthogonalization_dot_count: int
    orthogonalization_axpy_count: int
    normalization_divide_count: int
    operator_basis_csr_apply_count: int
    operator_basis_csr_multiply_count: int
    coarse_operator_dot_count: int
    per_apply_coarse_rhs_dot_count: int
    per_apply_forward_substitution_row_count: int
    per_apply_backward_substitution_row_count: int
    per_apply_basis_axpy_count: int
    per_apply_operator_basis_axpy_count: int
    per_apply_jacobi_multiply_count: int
    retained_scalar_count: int
    dense_projector_elements: int
    max_dense_square_dimension: int
    build_complexity: str
    application_complexity: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CpuFgmresCoarseSolveComplexityReceiptV1:
    """Exact aggregate coarse work implied by one FGMRES solve."""

    free_dof_count: int
    retained_rank: int
    preconditioner_apply_count: int
    total_coarse_rhs_dot_count: int
    total_small_forward_solve_count: int
    total_small_backward_solve_count: int
    total_basis_axpy_count: int
    total_operator_basis_axpy_count: int
    total_jacobi_multiply_count: int
    additional_csr_apply_count_inside_preconditioner: int
    dense_projector_elements: int
    max_dense_square_dimension: int
    runtime_complexity: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CpuFgmresFixedRankCoarseSpaceV1:
    """Immutable sparse-plan-bound fixed-rank coarse-space artifact."""

    schema_version: str
    capability_profile: str
    algorithm_version: str
    execution_plan_hash: str
    operator_hash: str
    numeric_snapshot_hash: str
    symbolic_reuse_hash: str
    partition_hash: str
    free_dof_count: int
    reduced_nnz: int
    candidate_count: int
    rank_cap: int
    retained_rank: int
    drop_tolerance: float
    condition_limit: float
    scaled_orthogonality_error_frobenius: float
    scaled_orthogonality_error_max_abs: float
    coarse_operator_condition_estimate: float
    descriptors: tuple[CpuFgmresCoarseArrayDescriptorV1, ...]
    inverse_sqrt_diagonal: np.ndarray
    candidate_vectors: np.ndarray
    scaled_basis_q: np.ndarray
    physical_basis_z: np.ndarray
    operator_basis_az: np.ndarray
    coarse_operator_e: np.ndarray
    coarse_cholesky_l: np.ndarray
    complexity_receipt: CpuFgmresCoarseComplexityReceiptV1
    coarse_space_hash: str
    _source_execution_plan: ExecutionPlanV2 = dataclass_field(
        repr=False,
        compare=False,
    )

    def array(self, name: str) -> np.ndarray:
        if name not in _ARTIFACT_ARRAY_NAMES:
            raise KeyError(name)
        return getattr(self, name)

    def apply(self, residual: Any) -> np.ndarray:
        return apply_cpu_fgmres_fixed_rank_coarse_v1(self, residual)

    def to_dict(self) -> dict[str, Any]:
        validate_cpu_fgmres_fixed_rank_coarse_space_v1(self)
        return _coarse_space_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class CpuFgmresFixedRankCoarseResultV1:
    """Deterministic CPU FGMRES result using the fixed-rank coarse space."""

    schema_version: str
    capability_profile: str
    algorithm_version: str
    status: FgmresStatus
    termination_code: str
    execution_plan_hash: str
    operator_hash: str
    numeric_snapshot_hash: str
    partition_hash: str
    initial_reduced_state_hash: str
    rhs_hash: str
    coarse_space_hash: str
    policy: FgmresPolicyV1
    iteration_count: int
    restart_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    initial_residual_l2: float
    solver_tolerance_l2: float
    final_residual_l2: float
    final_residual_linf: float
    scaled_true_residual: float
    solver_tolerance_passed: bool
    authoritative_plan_tolerance_passed: bool
    history: tuple[FgmresRestartRecord, ...]
    descriptors: tuple[CpuFgmresArrayDescriptor, ...]
    reduced_solution: np.ndarray
    true_residual: np.ndarray
    complexity_receipt: CpuFgmresCoarseSolveComplexityReceiptV1
    result_hash: str

    def array(self, name: str) -> np.ndarray:
        if name not in _RESULT_ARRAY_NAMES:
            raise KeyError(name)
        return getattr(self, name)

    def to_dict(self) -> dict[str, Any]:
        validate_cpu_fgmres_fixed_rank_coarse_result_v1_shallow(self)
        return _result_payload(self, include_hash=True)


def build_cpu_fgmres_fixed_rank_coarse_space_v1(
    plan: ExecutionPlanV2,
    candidate_vectors: Any,
    *,
    rank_cap: int = MAX_CPU_FGMRES_COARSE_RANK_V1,
    drop_tolerance: float = DEFAULT_CPU_FGMRES_COARSE_DROP_TOLERANCE_V1,
    condition_limit: float = DEFAULT_CPU_FGMRES_COARSE_CONDITION_LIMIT_V1,
) -> CpuFgmresFixedRankCoarseSpaceV1:
    """Compile an energy-scaled fixed-rank coarse space from sparse CSR."""

    _validate_policy(rank_cap, drop_tolerance, condition_limit)
    _validate_plan(plan)
    free_dof_count = int(plan.array("free_dofs").size)
    candidates = _coerce_candidate_matrix(candidate_vectors, free_dof_count)
    candidate_count = int(candidates.shape[1])
    if candidate_count > rank_cap:
        _fail(
            "cpu_fgmres_coarse_candidate_count_exceeds_rank_cap",
            "/candidate_vectors/shape/1",
        )
    derived = _derive_arrays(
        plan,
        candidates,
        drop_tolerance=drop_tolerance,
        condition_limit=condition_limit,
    )
    (
        inverse_sqrt,
        scaled_basis,
        physical_basis,
        operator_basis,
        coarse_operator,
        cholesky,
        dot_count,
        axpy_count,
        orthogonality_frobenius,
        orthogonality_max_abs,
        condition_estimate,
    ) = derived
    retained_rank = int(scaled_basis.shape[1])
    arrays = (
        inverse_sqrt,
        candidates,
        scaled_basis,
        physical_basis,
        operator_basis,
        coarse_operator,
        cholesky,
    )
    descriptors = tuple(
        _coarse_array_descriptor(name, array)
        for name, array in zip(_ARTIFACT_ARRAY_NAMES, arrays, strict=True)
    )
    complexity = _complexity_receipt(
        free_dof_count=free_dof_count,
        reduced_nnz=int(plan.reduced_nnz),
        candidate_count=candidate_count,
        retained_rank=retained_rank,
        rank_cap=rank_cap,
        orthogonalization_dot_count=dot_count,
        orthogonalization_axpy_count=axpy_count,
    )
    draft = CpuFgmresFixedRankCoarseSpaceV1(
        schema_version=CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION,
        capability_profile=CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1,
        algorithm_version=CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        symbolic_reuse_hash=plan.symbolic_reuse_hash,
        partition_hash=plan.partition_hash,
        free_dof_count=free_dof_count,
        reduced_nnz=int(plan.reduced_nnz),
        candidate_count=candidate_count,
        rank_cap=int(rank_cap),
        retained_rank=retained_rank,
        drop_tolerance=float(drop_tolerance),
        condition_limit=float(condition_limit),
        scaled_orthogonality_error_frobenius=orthogonality_frobenius,
        scaled_orthogonality_error_max_abs=orthogonality_max_abs,
        coarse_operator_condition_estimate=condition_estimate,
        descriptors=descriptors,
        inverse_sqrt_diagonal=inverse_sqrt,
        candidate_vectors=candidates,
        scaled_basis_q=scaled_basis,
        physical_basis_z=physical_basis,
        operator_basis_az=operator_basis,
        coarse_operator_e=coarse_operator,
        coarse_cholesky_l=cholesky,
        complexity_receipt=complexity,
        coarse_space_hash=_ZERO_HASH,
        _source_execution_plan=plan,
    )
    artifact = replace(
        draft,
        coarse_space_hash=canonical_hash(
            _coarse_space_payload(draft, include_hash=False)
        ),
    )
    return validate_cpu_fgmres_fixed_rank_coarse_space_v1(
        artifact,
        expected_plan=plan,
    )


def validate_cpu_fgmres_fixed_rank_coarse_space_v1(
    artifact: CpuFgmresFixedRankCoarseSpaceV1,
    *,
    expected_plan: ExecutionPlanV2 | None = None,
) -> CpuFgmresFixedRankCoarseSpaceV1:
    """Replay sparse construction, factorization, storage, and all hashes."""

    if type(artifact) is not CpuFgmresFixedRankCoarseSpaceV1:
        _fail("cpu_fgmres_coarse_space_type_invalid", "/")
    if (
        artifact.schema_version != CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION
        or artifact.capability_profile
        != CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1
        or artifact.algorithm_version
        != CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1
    ):
        _fail("cpu_fgmres_coarse_space_version_invalid", "/schema_version")
    _validate_policy(
        artifact.rank_cap,
        artifact.drop_tolerance,
        artifact.condition_limit,
    )
    if (
        type(artifact.free_dof_count) is not int
        or artifact.free_dof_count <= 0
        or type(artifact.reduced_nnz) is not int
        or artifact.reduced_nnz < artifact.free_dof_count
        or type(artifact.candidate_count) is not int
        or not 1 <= artifact.candidate_count <= artifact.rank_cap
        or type(artifact.retained_rank) is not int
        or not 1 <= artifact.retained_rank <= artifact.candidate_count
    ):
        _fail("cpu_fgmres_coarse_dimension_invalid", "/dimensions")
    numeric_metrics = (
        artifact.scaled_orthogonality_error_frobenius,
        artifact.scaled_orthogonality_error_max_abs,
        artifact.coarse_operator_condition_estimate,
    )
    if any(
        type(value) is not float or not math.isfinite(value) or value < 0.0
        for value in numeric_metrics
    ):
        _fail("cpu_fgmres_coarse_metric_invalid", "/quality")
    if (
        artifact.scaled_orthogonality_error_frobenius > _ORTHOGONALITY_TOLERANCE
        or artifact.coarse_operator_condition_estimate > artifact.condition_limit
    ):
        _fail("cpu_fgmres_coarse_quality_invalid", "/quality")
    if (
        type(artifact.descriptors) is not tuple
        or tuple(row.name for row in artifact.descriptors) != _ARTIFACT_ARRAY_NAMES
    ):
        _fail("cpu_fgmres_coarse_descriptor_set_invalid", "/arrays")
    expected_shapes = (
        (artifact.free_dof_count,),
        (artifact.free_dof_count, artifact.candidate_count),
        (artifact.free_dof_count, artifact.retained_rank),
        (artifact.free_dof_count, artifact.retained_rank),
        (artifact.free_dof_count, artifact.retained_rank),
        (artifact.retained_rank, artifact.retained_rank),
        (artifact.retained_rank, artifact.retained_rank),
    )
    for index, (name, shape) in enumerate(
        zip(_ARTIFACT_ARRAY_NAMES, expected_shapes, strict=True)
    ):
        array = artifact.array(name)
        descriptor = artifact.descriptors[index]
        if (
            type(descriptor) is not CpuFgmresCoarseArrayDescriptorV1
            or type(array) is not np.ndarray
            or array.dtype.str != "<f8"
            or array.shape != shape
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
            or not np.isfinite(array).all()
            or descriptor != _coarse_array_descriptor(name, array)
        ):
            _fail("cpu_fgmres_coarse_array_invalid", f"/arrays/{index}")
    if np.any(artifact.inverse_sqrt_diagonal <= 0.0) or np.any(
        np.diag(artifact.coarse_cholesky_l) <= 0.0
    ):
        _fail("cpu_fgmres_coarse_factor_invalid", "/arrays")
    if np.any(np.triu(artifact.coarse_cholesky_l, k=1) != 0.0):
        _fail("cpu_fgmres_coarse_factor_not_lower_triangular", "/arrays/6")

    if type(artifact._source_execution_plan) is not ExecutionPlanV2:
        _fail("cpu_fgmres_coarse_source_plan_missing", "/source_execution_plan")
    plan = artifact._source_execution_plan
    if expected_plan is not None and plan is not expected_plan:
        _fail("cpu_fgmres_coarse_expected_plan_mismatch", "/source_execution_plan")
    _validate_plan(plan)
    bindings = (
        (artifact.execution_plan_hash, plan.plan_hash),
        (artifact.operator_hash, plan.operator_hash),
        (artifact.numeric_snapshot_hash, plan.numeric_snapshot_hash),
        (artifact.symbolic_reuse_hash, plan.symbolic_reuse_hash),
        (artifact.partition_hash, plan.partition_hash),
        (artifact.free_dof_count, int(plan.array("free_dofs").size)),
        (artifact.reduced_nnz, int(plan.reduced_nnz)),
    )
    if any(actual != expected for actual, expected in bindings):
        _fail("cpu_fgmres_coarse_plan_binding_mismatch", "/bindings")
    replay = _derive_arrays(
        plan,
        artifact.candidate_vectors,
        drop_tolerance=artifact.drop_tolerance,
        condition_limit=artifact.condition_limit,
    )
    replay_arrays = (replay[0], replay[1], replay[2], replay[3], replay[4], replay[5])
    stored_arrays = (
        artifact.inverse_sqrt_diagonal,
        artifact.scaled_basis_q,
        artifact.physical_basis_z,
        artifact.operator_basis_az,
        artifact.coarse_operator_e,
        artifact.coarse_cholesky_l,
    )
    if any(
        not np.array_equal(actual, expected)
        for actual, expected in zip(stored_arrays, replay_arrays, strict=True)
    ):
        _fail("cpu_fgmres_coarse_replay_array_mismatch", "/arrays")
    expected_metrics = (replay[8], replay[9], replay[10])
    if numeric_metrics != expected_metrics:
        _fail("cpu_fgmres_coarse_replay_metric_mismatch", "/quality")
    expected_complexity = _complexity_receipt(
        free_dof_count=artifact.free_dof_count,
        reduced_nnz=artifact.reduced_nnz,
        candidate_count=artifact.candidate_count,
        retained_rank=artifact.retained_rank,
        rank_cap=artifact.rank_cap,
        orthogonalization_dot_count=replay[6],
        orthogonalization_axpy_count=replay[7],
    )
    if artifact.complexity_receipt != expected_complexity:
        _fail("cpu_fgmres_coarse_complexity_mismatch", "/complexity")
    _validate_schema(
        _coarse_space_schema(),
        _coarse_space_payload(artifact, include_hash=True),
    )
    if artifact.coarse_space_hash != canonical_hash(
        _coarse_space_payload(artifact, include_hash=False)
    ):
        _fail("cpu_fgmres_coarse_space_hash_mismatch", "/coarse_space_hash")
    return artifact


def apply_cpu_fgmres_fixed_rank_coarse_v1(
    artifact: CpuFgmresFixedRankCoarseSpaceV1,
    residual: Any,
    *,
    expected_plan: ExecutionPlanV2 | None = None,
) -> np.ndarray:
    """Validate then apply the multiplicative coarse/Jacobi operator once."""

    validate_cpu_fgmres_fixed_rank_coarse_space_v1(
        artifact,
        expected_plan=expected_plan,
    )
    vector = _coerce_vector(residual, artifact.free_dof_count, "/residual")
    return immutable_array(_apply_coarse_unchecked(artifact, vector), dtype="<f8")


def solve_cpu_fgmres_fixed_rank_coarse_v1(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    coarse_space: CpuFgmresFixedRankCoarseSpaceV1,
    *,
    initial_full_state: np.ndarray | None = None,
) -> CpuFgmresFixedRankCoarseResultV1:
    """Run fixed-restart FGMRES with the bound fixed-rank right preconditioner."""

    _validate_plan(plan)
    validate_fgmres_policy_v1(policy)
    validate_cpu_fgmres_fixed_rank_coarse_space_v1(
        coarse_space,
        expected_plan=plan,
    )
    result = _solve_unchecked(
        plan,
        policy,
        coarse_space,
        initial_full_state=initial_full_state,
    )
    return validate_cpu_fgmres_fixed_rank_coarse_result_v1(
        result,
        expected_plan=plan,
        expected_policy=policy,
        expected_coarse_space=coarse_space,
        expected_initial_full_state=initial_full_state,
    )


def validate_cpu_fgmres_fixed_rank_coarse_result_v1(
    result: CpuFgmresFixedRankCoarseResultV1,
    *,
    expected_plan: ExecutionPlanV2,
    expected_policy: FgmresPolicyV1,
    expected_coarse_space: CpuFgmresFixedRankCoarseSpaceV1,
    expected_initial_full_state: np.ndarray | None = None,
) -> CpuFgmresFixedRankCoarseResultV1:
    """Validate sparse residual, solver semantics, coarse counts, and replay."""

    validate_cpu_fgmres_fixed_rank_coarse_result_v1_shallow(result)
    _validate_plan(expected_plan)
    validate_fgmres_policy_v1(expected_policy)
    validate_cpu_fgmres_fixed_rank_coarse_space_v1(
        expected_coarse_space,
        expected_plan=expected_plan,
    )
    if result.policy != expected_policy:
        _fail("cpu_fgmres_coarse_result_policy_mismatch", "/policy")
    bindings = (
        (result.execution_plan_hash, expected_plan.plan_hash),
        (result.operator_hash, expected_plan.operator_hash),
        (result.numeric_snapshot_hash, expected_plan.numeric_snapshot_hash),
        (result.partition_hash, expected_plan.partition_hash),
        (result.coarse_space_hash, expected_coarse_space.coarse_space_hash),
    )
    if any(actual != expected for actual, expected in bindings):
        _fail("cpu_fgmres_coarse_result_binding_mismatch", "/bindings")
    free = expected_plan.array("free_dofs").astype(np.int64, copy=False)
    initial = _initial_reduced_state(
        expected_plan,
        free,
        expected_initial_full_state,
    )
    rhs = immutable_array(expected_plan.array("global_load")[free], dtype="<f8")
    if result.initial_reduced_state_hash != array_data_hash(
        initial
    ) or result.rhs_hash != array_data_hash(rhs):
        _fail("cpu_fgmres_coarse_result_source_hash_mismatch", "/bindings")
    if tuple(row.name for row in result.descriptors) != _RESULT_ARRAY_NAMES:
        _fail("cpu_fgmres_coarse_result_descriptor_set_invalid", "/arrays")
    for index, name in enumerate(_RESULT_ARRAY_NAMES):
        array = result.array(name)
        if (
            type(array) is not np.ndarray
            or array.dtype.str != "<f8"
            or array.shape != (free.size,)
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
            or not np.isfinite(array).all()
            or result.descriptors[index] != _array_descriptor(name, array)
        ):
            _fail("cpu_fgmres_coarse_result_array_invalid", f"/arrays/{index}")
    row_ptr = expected_plan.array("reduced_csr_row_ptr")
    columns = expected_plan.array("reduced_csr_column_indices")
    values = expected_plan.array("reduced_stiffness_csr_values")
    replay_residual = rhs - _csr_matvec(
        row_ptr,
        columns,
        values,
        result.reduced_solution,
    )
    replay_residual[replay_residual == 0.0] = 0.0
    initial_residual = rhs - _csr_matvec(row_ptr, columns, values, initial)
    initial_residual[initial_residual == 0.0] = 0.0
    if not np.array_equal(result.true_residual, replay_residual):
        _fail("cpu_fgmres_coarse_result_residual_mismatch", "/arrays/1")
    final_l2 = _stable_l2(result.true_residual)
    final_linf = _linf(result.true_residual)
    scaled = final_linf / max(1.0, _linf(rhs))
    expected_metrics = (
        _stable_l2(initial_residual),
        max(
            expected_policy.absolute_tolerance,
            expected_policy.relative_tolerance * _stable_l2(rhs),
        ),
        final_l2,
        final_linf,
        scaled,
        final_l2 <= result.solver_tolerance_l2,
        scaled <= expected_plan.residual_tolerance,
    )
    actual_metrics = (
        result.initial_residual_l2,
        result.solver_tolerance_l2,
        result.final_residual_l2,
        result.final_residual_linf,
        result.scaled_true_residual,
        result.solver_tolerance_passed,
        result.authoritative_plan_tolerance_passed,
    )
    if actual_metrics != expected_metrics:
        _fail("cpu_fgmres_coarse_result_metric_mismatch", "/metrics")
    try:
        _validate_result_semantics(
            result,  # type: ignore[arg-type]
            initial_solution=initial,
            initial_residual=initial_residual,
            rhs=rhs,
        )
    except CpuFgmresReferenceError as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_result_semantics_invalid",
            exc.path,
            exc.code,
        ) from exc
    expected_complexity = _solve_complexity_receipt(
        expected_coarse_space,
        result.preconditioner_apply_count,
    )
    if result.complexity_receipt != expected_complexity:
        _fail("cpu_fgmres_coarse_result_complexity_mismatch", "/complexity")
    if result.result_hash != canonical_hash(
        _result_payload(result, include_hash=False)
    ):
        _fail("cpu_fgmres_coarse_result_hash_mismatch", "/result_hash")
    replayed = _solve_unchecked(
        expected_plan,
        expected_policy,
        expected_coarse_space,
        initial_full_state=expected_initial_full_state,
    )
    if (
        _result_payload(result, include_hash=True)
        != _result_payload(replayed, include_hash=True)
        or not np.array_equal(result.reduced_solution, replayed.reduced_solution)
        or not np.array_equal(result.true_residual, replayed.true_residual)
    ):
        _fail("cpu_fgmres_coarse_result_replay_mismatch", "/")
    return result


def validate_cpu_fgmres_fixed_rank_coarse_result_v1_shallow(
    result: CpuFgmresFixedRankCoarseResultV1,
) -> CpuFgmresFixedRankCoarseResultV1:
    if (
        type(result) is not CpuFgmresFixedRankCoarseResultV1
        or result.schema_version
        != CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION
        or result.capability_profile
        != CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1
        or result.algorithm_version != CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1
        or type(result.policy) is not FgmresPolicyV1
        or type(result.history) is not tuple
        or any(type(row) is not FgmresRestartRecord for row in result.history)
        or type(result.descriptors) is not tuple
        or any(type(row) is not CpuFgmresArrayDescriptor for row in result.descriptors)
        or type(result.complexity_receipt)
        is not CpuFgmresCoarseSolveComplexityReceiptV1
        or not _valid_hash(result.result_hash)
    ):
        _fail("cpu_fgmres_coarse_result_type_invalid", "/")
    _validate_schema(
        _result_schema(),
        _result_payload(result, include_hash=True),
    )
    return result


def _solve_unchecked(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    coarse_space: CpuFgmresFixedRankCoarseSpaceV1,
    *,
    initial_full_state: np.ndarray | None,
) -> CpuFgmresFixedRankCoarseResultV1:
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    initial = _initial_reduced_state(plan, free, initial_full_state)
    rhs = immutable_array(plan.array("global_load")[free], dtype="<f8")
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    inverse_diagonal = _positive_jacobi_inverse(row_ptr, columns, values)
    outcome = _fgmres_core(
        matvec=lambda vector: _csr_matvec(row_ptr, columns, values, vector),
        rhs=rhs,
        initial_solution=initial,
        inverse_diagonal=inverse_diagonal,
        policy=policy,
        authoritative_tolerance=plan.residual_tolerance,
        right_preconditioner=lambda vector: _apply_coarse_unchecked(
            coarse_space,
            vector,
        ),
    )
    solution = immutable_array(outcome.solution, dtype="<f8")
    residual = immutable_array(outcome.residual, dtype="<f8")
    final_l2 = _stable_l2(residual)
    final_linf = _linf(residual)
    scaled = final_linf / max(1.0, _linf(rhs))
    draft = CpuFgmresFixedRankCoarseResultV1(
        schema_version=CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION,
        capability_profile=CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1,
        algorithm_version=CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1,
        status=outcome.status,
        termination_code=outcome.termination_code,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        partition_hash=plan.partition_hash,
        initial_reduced_state_hash=array_data_hash(initial),
        rhs_hash=array_data_hash(rhs),
        coarse_space_hash=coarse_space.coarse_space_hash,
        policy=policy,
        iteration_count=outcome.iteration_count,
        restart_count=outcome.restart_count,
        operator_apply_count=outcome.operator_apply_count,
        preconditioner_apply_count=outcome.preconditioner_apply_count,
        initial_residual_l2=outcome.initial_residual_l2,
        solver_tolerance_l2=outcome.tolerance_l2,
        final_residual_l2=final_l2,
        final_residual_linf=final_linf,
        scaled_true_residual=scaled,
        solver_tolerance_passed=final_l2 <= outcome.tolerance_l2,
        authoritative_plan_tolerance_passed=scaled <= plan.residual_tolerance,
        history=outcome.history,
        descriptors=(
            _array_descriptor("reduced_solution", solution),
            _array_descriptor("true_residual", residual),
        ),
        reduced_solution=solution,
        true_residual=residual,
        complexity_receipt=_solve_complexity_receipt(
            coarse_space,
            outcome.preconditioner_apply_count,
        ),
        result_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        result_hash=canonical_hash(_result_payload(draft, include_hash=False)),
    )


def _derive_arrays(
    plan: ExecutionPlanV2,
    candidates: np.ndarray,
    *,
    drop_tolerance: float,
    condition_limit: float,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    int,
    int,
    float,
    float,
    float,
]:
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    inverse_diagonal = _positive_jacobi_inverse(row_ptr, columns, values)
    inverse_sqrt = immutable_array(np.sqrt(inverse_diagonal), dtype="<f8")
    scaled_basis, dot_count, axpy_count = _two_pass_mgs(
        inverse_sqrt,
        candidates,
        drop_tolerance=drop_tolerance,
    )
    retained_rank = int(scaled_basis.shape[1])
    if retained_rank == 0:
        _fail("cpu_fgmres_coarse_basis_rank_zero", "/candidate_vectors")
    orthogonality_frobenius, orthogonality_max_abs = _orthogonality_errors(scaled_basis)
    if orthogonality_frobenius > _ORTHOGONALITY_TOLERANCE:
        _fail("cpu_fgmres_coarse_basis_not_orthonormal", "/scaled_basis_q")
    try:
        with np.errstate(over="raise", invalid="raise"):
            physical_basis = immutable_array(
                inverse_sqrt[:, None] * scaled_basis,
                dtype="<f8",
            )
    except FloatingPointError as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_physical_basis_nonfinite",
            "/physical_basis_z",
            type(exc).__name__,
        ) from exc
    operator_basis_mutable = np.empty_like(physical_basis)
    for column_index in range(retained_rank):
        try:
            operator_basis_mutable[:, column_index] = _csr_matvec(
                row_ptr,
                columns,
                values,
                physical_basis[:, column_index],
            )
        except (FloatingPointError, OverflowError, ValueError) as exc:
            raise CpuFgmresFixedRankCoarseError(
                "cpu_fgmres_coarse_operator_basis_failed",
                f"/operator_basis_az/{column_index}",
                type(exc).__name__,
            ) from exc
    operator_basis = immutable_array(operator_basis_mutable, dtype="<f8")
    coarse_mutable = np.zeros((retained_rank, retained_rank), dtype="<f8")
    for row in range(retained_rank):
        for column in range(row, retained_rank):
            value = _coarse_dot(
                physical_basis[:, row],
                operator_basis[:, column],
                "/coarse_operator_e",
            )
            coarse_mutable[row, column] = value
            coarse_mutable[column, row] = value
    if not np.isfinite(coarse_mutable).all():
        _fail("cpu_fgmres_coarse_operator_nonfinite", "/coarse_operator_e")
    try:
        eigenvalues = np.linalg.eigvalsh(coarse_mutable)
    except np.linalg.LinAlgError as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_eigensolve_failed",
            "/coarse_operator_e",
            type(exc).__name__,
        ) from exc
    smallest = float(eigenvalues[0])
    largest = float(eigenvalues[-1])
    if (
        not math.isfinite(smallest)
        or not math.isfinite(largest)
        or smallest <= 0.0
        or largest <= 0.0
    ):
        _fail("cpu_fgmres_coarse_operator_not_spd", "/coarse_operator_e")
    condition_estimate = largest / smallest
    if not math.isfinite(condition_estimate) or condition_estimate > condition_limit:
        _fail("cpu_fgmres_coarse_operator_ill_conditioned", "/coarse_operator_e")
    try:
        cholesky_mutable = np.linalg.cholesky(coarse_mutable)
    except np.linalg.LinAlgError as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_cholesky_failed",
            "/coarse_operator_e",
            type(exc).__name__,
        ) from exc
    coarse = immutable_array(coarse_mutable, dtype="<f8")
    cholesky = immutable_array(cholesky_mutable, dtype="<f8")
    return (
        inverse_sqrt,
        scaled_basis,
        physical_basis,
        operator_basis,
        coarse,
        cholesky,
        dot_count,
        axpy_count,
        orthogonality_frobenius,
        orthogonality_max_abs,
        float(condition_estimate),
    )


def _apply_coarse_unchecked(
    artifact: CpuFgmresFixedRankCoarseSpaceV1,
    residual: np.ndarray,
) -> np.ndarray:
    rank = artifact.retained_rank
    coarse_rhs = np.empty(rank, dtype="<f8")
    for index in range(rank):
        coarse_rhs[index] = _coarse_dot(
            artifact.physical_basis_z[:, index],
            residual,
            "/preconditioner/coarse_rhs",
        )
    coefficients = _cholesky_solve(artifact.coarse_cholesky_l, coarse_rhs)
    coarse_correction = np.zeros(artifact.free_dof_count, dtype="<f8")
    coarse_image = np.zeros(artifact.free_dof_count, dtype="<f8")
    try:
        with np.errstate(over="raise", invalid="raise"):
            for index in range(rank):
                coefficient = float(coefficients[index])
                coarse_correction += coefficient * artifact.physical_basis_z[:, index]
                coarse_image += coefficient * artifact.operator_basis_az[:, index]
            inverse_diagonal = artifact.inverse_sqrt_diagonal**2
            result = coarse_correction + inverse_diagonal * (residual - coarse_image)
    except FloatingPointError as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_application_nonfinite",
            "/preconditioner",
            type(exc).__name__,
        ) from exc
    if result.shape != (artifact.free_dof_count,) or not np.isfinite(result).all():
        _fail("cpu_fgmres_coarse_application_nonfinite", "/preconditioner")
    result[result == 0.0] = 0.0
    return np.ascontiguousarray(result, dtype="<f8")


def _cholesky_solve(lower: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    count = int(rhs.size)
    forward = np.empty(count, dtype="<f8")
    for row in range(count):
        tail = _coarse_dot(
            lower[row, :row],
            forward[:row],
            "/preconditioner/forward_solve",
        )
        pivot = float(lower[row, row])
        value = (float(rhs[row]) - tail) / pivot
        if not math.isfinite(value):
            _fail("cpu_fgmres_coarse_forward_solve_nonfinite", "/preconditioner")
        forward[row] = value
    result = np.empty(count, dtype="<f8")
    for row in range(count - 1, -1, -1):
        tail = _coarse_dot(
            lower[row + 1 :, row],
            result[row + 1 :],
            "/preconditioner/backward_solve",
        )
        pivot = float(lower[row, row])
        value = (float(forward[row]) - tail) / pivot
        if not math.isfinite(value):
            _fail("cpu_fgmres_coarse_backward_solve_nonfinite", "/preconditioner")
        result[row] = value
    return result


def _two_pass_mgs(
    inverse_sqrt_diagonal: np.ndarray,
    candidates: np.ndarray,
    *,
    drop_tolerance: float,
) -> tuple[np.ndarray, int, int]:
    count, candidate_count = candidates.shape
    columns: list[np.ndarray] = []
    dot_count = 0
    axpy_count = 0
    for candidate_index in range(candidate_count):
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                work = np.asarray(
                    candidates[:, candidate_index] / inverse_sqrt_diagonal,
                    dtype="<f8",
                ).copy()
        except FloatingPointError as exc:
            raise CpuFgmresFixedRankCoarseError(
                "cpu_fgmres_coarse_scaled_candidate_nonfinite",
                f"/candidate_vectors/{candidate_index}",
                type(exc).__name__,
            ) from exc
        reference_norm = _stable_l2(work)
        for _pass_index in range(2):
            for column in columns:
                coefficient = _coarse_dot(
                    column,
                    work,
                    f"/candidate_vectors/{candidate_index}",
                )
                dot_count += 1
                try:
                    with np.errstate(over="raise", invalid="raise"):
                        work -= coefficient * column
                except FloatingPointError as exc:
                    raise CpuFgmresFixedRankCoarseError(
                        "cpu_fgmres_coarse_orthogonalization_nonfinite",
                        f"/candidate_vectors/{candidate_index}",
                        type(exc).__name__,
                    ) from exc
                axpy_count += 1
        residual_norm = _stable_l2(work)
        if reference_norm == 0.0 or residual_norm <= drop_tolerance * reference_norm:
            continue
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                column = work / residual_norm
        except FloatingPointError as exc:
            raise CpuFgmresFixedRankCoarseError(
                "cpu_fgmres_coarse_basis_nonfinite",
                f"/candidate_vectors/{candidate_index}",
                type(exc).__name__,
            ) from exc
        if not np.isfinite(column).all():
            _fail("cpu_fgmres_coarse_basis_nonfinite", "/candidate_vectors")
        columns.append(column)
    basis = np.column_stack(columns) if columns else np.empty((count, 0), dtype="<f8")
    return immutable_array(basis, dtype="<f8"), dot_count, axpy_count


def _orthogonality_errors(basis: np.ndarray) -> tuple[float, float]:
    rank = int(basis.shape[1])
    error = np.empty((rank, rank), dtype="<f8")
    for row in range(rank):
        for column in range(rank):
            value = _coarse_dot(
                basis[:, row],
                basis[:, column],
                "/scaled_basis_q",
            )
            error[row, column] = value - (1.0 if row == column else 0.0)
    return _stable_l2(error.reshape(-1)), _linf(error.reshape(-1))


def _complexity_receipt(
    *,
    free_dof_count: int,
    reduced_nnz: int,
    candidate_count: int,
    retained_rank: int,
    rank_cap: int,
    orthogonalization_dot_count: int,
    orthogonalization_axpy_count: int,
) -> CpuFgmresCoarseComplexityReceiptV1:
    retained_scalar_count = (
        free_dof_count
        + free_dof_count * candidate_count
        + 3 * free_dof_count * retained_rank
        + 2 * retained_rank * retained_rank
    )
    return CpuFgmresCoarseComplexityReceiptV1(
        free_dof_count=free_dof_count,
        reduced_nnz=reduced_nnz,
        candidate_count=candidate_count,
        retained_rank=retained_rank,
        rank_cap=rank_cap,
        basis_scaling_multiply_count=free_dof_count * candidate_count,
        orthogonalization_dot_count=orthogonalization_dot_count,
        orthogonalization_axpy_count=orthogonalization_axpy_count,
        normalization_divide_count=free_dof_count * retained_rank,
        operator_basis_csr_apply_count=retained_rank,
        operator_basis_csr_multiply_count=reduced_nnz * retained_rank,
        coarse_operator_dot_count=retained_rank * (retained_rank + 1) // 2,
        per_apply_coarse_rhs_dot_count=retained_rank,
        per_apply_forward_substitution_row_count=retained_rank,
        per_apply_backward_substitution_row_count=retained_rank,
        per_apply_basis_axpy_count=retained_rank,
        per_apply_operator_basis_axpy_count=retained_rank,
        per_apply_jacobi_multiply_count=free_dof_count,
        retained_scalar_count=retained_scalar_count,
        dense_projector_elements=0,
        max_dense_square_dimension=retained_rank,
        build_complexity="O(nnz*k + N*k^2 + k^3)",
        application_complexity="O(N*k + k^2)",
    )


def _solve_complexity_receipt(
    artifact: CpuFgmresFixedRankCoarseSpaceV1,
    apply_count: int,
) -> CpuFgmresCoarseSolveComplexityReceiptV1:
    rank = artifact.retained_rank
    return CpuFgmresCoarseSolveComplexityReceiptV1(
        free_dof_count=artifact.free_dof_count,
        retained_rank=rank,
        preconditioner_apply_count=apply_count,
        total_coarse_rhs_dot_count=apply_count * rank,
        total_small_forward_solve_count=apply_count,
        total_small_backward_solve_count=apply_count,
        total_basis_axpy_count=apply_count * rank,
        total_operator_basis_axpy_count=apply_count * rank,
        total_jacobi_multiply_count=apply_count * artifact.free_dof_count,
        additional_csr_apply_count_inside_preconditioner=0,
        dense_projector_elements=0,
        max_dense_square_dimension=rank,
        runtime_complexity="O(I*(N*k+k^2)) with fixed k; solver-wide O(N) unproven",
    )


def _validate_policy(
    rank_cap: int,
    drop_tolerance: float,
    condition_limit: float,
) -> None:
    if type(rank_cap) is not int or not 1 <= rank_cap <= MAX_CPU_FGMRES_COARSE_RANK_V1:
        _fail("cpu_fgmres_coarse_rank_cap_invalid", "/rank_cap")
    if (
        type(drop_tolerance) is not float
        or not math.isfinite(drop_tolerance)
        or drop_tolerance <= 0.0
        or drop_tolerance >= 1.0
    ):
        _fail("cpu_fgmres_coarse_drop_tolerance_invalid", "/drop_tolerance")
    if (
        type(condition_limit) is not float
        or not math.isfinite(condition_limit)
        or condition_limit <= 1.0
    ):
        _fail("cpu_fgmres_coarse_condition_limit_invalid", "/condition_limit")


def _validate_plan(plan: ExecutionPlanV2) -> None:
    if type(plan) is not ExecutionPlanV2:
        _fail("cpu_fgmres_coarse_plan_type_invalid", "/plan")
    try:
        validate_execution_plan_v2(plan)
    except Exception as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_plan_invalid",
            "/plan",
            type(exc).__name__,
        ) from exc


def _coerce_candidate_matrix(value: Any, free_dof_count: int) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_candidates_invalid",
            "/candidate_vectors",
            type(exc).__name__,
        ) from exc
    if array.ndim != 2 or array.shape[0] != free_dof_count or array.shape[1] == 0:
        _fail("cpu_fgmres_coarse_candidate_shape_invalid", "/candidate_vectors")
    if not np.isfinite(array).all():
        _fail("cpu_fgmres_coarse_candidate_nonfinite", "/candidate_vectors")
    return immutable_array(array, dtype="<f8")


def _coerce_vector(value: Any, count: int, path: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_vector_invalid",
            path,
            type(exc).__name__,
        ) from exc
    if array.shape != (count,) or not np.isfinite(array).all():
        _fail("cpu_fgmres_coarse_vector_invalid", path)
    return np.ascontiguousarray(array, dtype="<f8")


def _coarse_array_descriptor(
    name: str,
    array: np.ndarray,
) -> CpuFgmresCoarseArrayDescriptorV1:
    return CpuFgmresCoarseArrayDescriptorV1(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in array.shape),
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
    )


def _coarse_dot(left: np.ndarray, right: np.ndarray, path: str) -> float:
    try:
        return _finite_dot(left, right)
    except (FloatingPointError, OverflowError, ValueError) as exc:
        raise CpuFgmresFixedRankCoarseError(
            "cpu_fgmres_coarse_dot_failed",
            path,
            type(exc).__name__,
        ) from exc


def _coarse_space_payload(
    artifact: CpuFgmresFixedRankCoarseSpaceV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "capability_profile": artifact.capability_profile,
        "algorithm_version": artifact.algorithm_version,
        "bindings": {
            "execution_plan_hash": artifact.execution_plan_hash,
            "operator_hash": artifact.operator_hash,
            "numeric_snapshot_hash": artifact.numeric_snapshot_hash,
            "symbolic_reuse_hash": artifact.symbolic_reuse_hash,
            "partition_hash": artifact.partition_hash,
        },
        "dimensions": {
            "free_dof_count": artifact.free_dof_count,
            "reduced_nnz": artifact.reduced_nnz,
            "candidate_count": artifact.candidate_count,
            "rank_cap": artifact.rank_cap,
            "retained_rank": artifact.retained_rank,
        },
        "policy": {
            "drop_tolerance": artifact.drop_tolerance,
            "condition_limit": artifact.condition_limit,
        },
        "quality": {
            "scaled_orthogonality_error_frobenius": (
                artifact.scaled_orthogonality_error_frobenius
            ),
            "scaled_orthogonality_error_max_abs": (
                artifact.scaled_orthogonality_error_max_abs
            ),
            "coarse_operator_condition_estimate": (
                artifact.coarse_operator_condition_estimate
            ),
        },
        "arrays": [row.to_dict() for row in artifact.descriptors],
        "complexity": artifact.complexity_receipt.to_dict(),
        "claims": {
            "sparse_execution_plan_v2_bound": True,
            "jacobi_square_root_energy_scaling": True,
            "deterministic_two_pass_modified_gram_schmidt": True,
            "fixed_rank_bounded": True,
            "multiplicative_coarse_then_jacobi": True,
            "explicit_dense_n_by_n_projector": False,
            "reverse_mode_autograd_used": False,
            "hip_execution": False,
            "amg_hierarchy": False,
            "domain_decomposition": False,
            "mesh_independent_iterations_proven": False,
            "end_to_end_o_n_proven": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["coarse_space_hash"] = artifact.coarse_space_hash
    return payload


def _result_payload(
    result: CpuFgmresFixedRankCoarseResultV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "capability_profile": result.capability_profile,
        "algorithm_version": result.algorithm_version,
        "status": result.status,
        "termination_code": result.termination_code,
        "bindings": {
            "execution_plan_hash": result.execution_plan_hash,
            "operator_hash": result.operator_hash,
            "numeric_snapshot_hash": result.numeric_snapshot_hash,
            "partition_hash": result.partition_hash,
            "initial_reduced_state_hash": result.initial_reduced_state_hash,
            "rhs_hash": result.rhs_hash,
            "coarse_space_hash": result.coarse_space_hash,
            "source_policy_hash": result.policy.policy_hash,
        },
        "policy": _effective_policy_payload(result.policy),
        "counts": {
            "iteration_count": result.iteration_count,
            "restart_count": result.restart_count,
            "operator_apply_count": result.operator_apply_count,
            "preconditioner_apply_count": result.preconditioner_apply_count,
        },
        "metrics": {
            "initial_residual_l2": result.initial_residual_l2,
            "solver_tolerance_l2": result.solver_tolerance_l2,
            "final_residual_l2": result.final_residual_l2,
            "final_residual_linf": result.final_residual_linf,
            "scaled_true_residual": result.scaled_true_residual,
            "solver_tolerance_passed": result.solver_tolerance_passed,
            "authoritative_plan_tolerance_passed": (
                result.authoritative_plan_tolerance_passed
            ),
        },
        "history": [row.to_dict() for row in result.history],
        "arrays": [row.to_dict() for row in result.descriptors],
        "complexity": result.complexity_receipt.to_dict(),
        "claims": {
            "cpu_reference": True,
            "fixed_restart": True,
            "right_preconditioned": True,
            "positive_unshifted_jacobi_smoother": True,
            "fixed_rank_coarse_correction": True,
            "true_residual_replay": True,
            "additional_csr_apply_inside_preconditioner": False,
            "explicit_dense_n_by_n_projector": False,
            "fallback_used": False,
            "hip_execution": False,
            "amg_hierarchy": False,
            "domain_decomposition": False,
            "mesh_independent_iterations_proven": False,
            "end_to_end_o_n_proven": False,
            "speedup_proven": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["result_hash"] = result.result_hash
    return payload


def _effective_policy_payload(policy: FgmresPolicyV1) -> dict[str, Any]:
    """Serialize recurrence controls without relabelling Jacobi as effective."""

    validate_fgmres_policy_v1(policy)
    return {
        "schema_version": "structural-analysis-cpu-fgmres-coarse-policy.v1",
        "source_policy_schema_version": policy.schema_version,
        "source_policy_hash": policy.policy_hash,
        "method": "fixed_restart_right_preconditioned_fgmres",
        "restart_dimension": policy.restart_dimension,
        "max_iterations": policy.max_iterations,
        "absolute_tolerance": policy.absolute_tolerance,
        "relative_tolerance": policy.relative_tolerance,
        "stagnation_checkpoint_limit": policy.stagnation_checkpoint_limit,
        "stagnation_relative_tolerance": policy.stagnation_relative_tolerance,
        "divergence_factor": policy.divergence_factor,
        "orthogonalization": "dgks_conditional_two_pass_mgs",
        "source_policy_preconditioner": "positive_unshifted_jacobi_right",
        "effective_preconditioner": (
            "fixed_rank_multiplicative_coarse_then_positive_unshifted_jacobi_right"
        ),
        "solver_norm": "l2",
        "authoritative_norm": "scaled_true_residual_linf",
        "fallback_forbidden": True,
    }


@lru_cache(maxsize=1)
def _coarse_space_schema() -> dict[str, Any]:
    path = (
        Path(__file__).parents[2]
        / "schemas"
        / "cpu_fgmres_fixed_rank_coarse_space_v1.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    path = (
        Path(__file__).parents[2]
        / "schemas"
        / "cpu_fgmres_fixed_rank_coarse_result_v1.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(schema: dict[str, Any], payload: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("cpu_fgmres_coarse_schema_invalid", path, error.message)


def _valid_hash(value: Any) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


def _fail(code: str, path: str, message: str = "") -> None:
    raise CpuFgmresFixedRankCoarseError(code, path, message)


__all__ = [
    "CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1",
    "CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1",
    "CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION",
    "CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION",
    "DEFAULT_CPU_FGMRES_COARSE_CONDITION_LIMIT_V1",
    "DEFAULT_CPU_FGMRES_COARSE_DROP_TOLERANCE_V1",
    "MAX_CPU_FGMRES_COARSE_RANK_V1",
    "CpuFgmresCoarseArrayDescriptorV1",
    "CpuFgmresCoarseComplexityReceiptV1",
    "CpuFgmresCoarseSolveComplexityReceiptV1",
    "CpuFgmresFixedRankCoarseError",
    "CpuFgmresFixedRankCoarseResultV1",
    "CpuFgmresFixedRankCoarseSpaceV1",
    "apply_cpu_fgmres_fixed_rank_coarse_v1",
    "build_cpu_fgmres_fixed_rank_coarse_space_v1",
    "solve_cpu_fgmres_fixed_rank_coarse_v1",
    "validate_cpu_fgmres_fixed_rank_coarse_result_v1",
    "validate_cpu_fgmres_fixed_rank_coarse_result_v1_shallow",
    "validate_cpu_fgmres_fixed_rank_coarse_space_v1",
]
