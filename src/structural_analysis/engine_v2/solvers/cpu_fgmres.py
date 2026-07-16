"""Deterministic CPU oracle for fixed-restart right-preconditioned FGMRES.

This implementation is intentionally independent of SciPy's iterative solvers.
SciPy direct CSR remains a test oracle only; it is never a runtime fallback.
The recurrence uses ``r=b-Ax``, positive unshifted Jacobi right
preconditioning, incremental Givens QR, DGKS-triggered second-pass MGS, and
authoritative true-residual replay at every restart boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Literal

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

FGMRES_POLICY_V1_SCHEMA_VERSION = "structural-analysis-fgmres-policy.v1"
CPU_FGMRES_REFERENCE_RESULT_V1_SCHEMA_VERSION = (
    "structural-analysis-cpu-fgmres-reference-result.v1"
)
CPU_FGMRES_REFERENCE_CAPABILITY_PROFILE = (
    "phase0_cpu_fixed_restart_right_preconditioned_fgmres_reference"
)
CPU_FGMRES_CHECKPOINT_HISTORY_V2_SCHEMA_VERSION = (
    "structural-analysis-cpu-fgmres-checkpoint-history.v2"
)
CPU_FGMRES_CHECKPOINT_HISTORY_V2_CAPABILITY_PROFILE = (
    "phase0_cpu_fgmres_committed_checkpoint_vector_history_reference"
)

FgmresStatus = Literal[
    "converged",
    "max_iterations",
    "stagnated",
    "diverged",
    "arnoldi_breakdown",
    "numerical_failure",
]

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EPS = float(np.finfo(np.float64).eps)
_SQRT_EPS = float(np.sqrt(_EPS))
_DGKS_ETA = 0.717
_BREAKDOWN_MULTIPLIER = 64.0
_ARRAY_NAMES = ("reduced_solution", "true_residual")


class CpuFgmresReferenceError(RuntimeError):
    """Stable fail-closed CPU FGMRES reference error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class FgmresPolicyV1:
    restart_dimension: int
    max_iterations: int
    absolute_tolerance: float
    relative_tolerance: float
    stagnation_checkpoint_limit: int
    stagnation_relative_tolerance: float
    divergence_factor: float
    policy_hash: str

    @property
    def schema_version(self) -> str:
        return FGMRES_POLICY_V1_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_fgmres_policy_v1(self)
        return _policy_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class FgmresRestartRecord:
    restart_index: int
    start_iteration: int
    end_iteration: int
    arnoldi_step_count: int
    preconditioner_apply_count: int
    reorthogonalization_count: int
    estimated_residual_l2: float
    true_residual_l2: float
    true_residual_linf: float
    scaled_true_residual: float
    solution_update_l2: float
    termination_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class CpuFgmresArrayDescriptor:
    name: str
    dtype: Literal["<f8"]
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
class CpuFgmresReferenceResultV1:
    status: FgmresStatus
    termination_code: str
    execution_plan_hash: str
    operator_hash: str
    numeric_snapshot_hash: str
    partition_hash: str
    initial_reduced_state_hash: str
    rhs_hash: str
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
    result_hash: str

    @property
    def schema_version(self) -> str:
        return CPU_FGMRES_REFERENCE_RESULT_V1_SCHEMA_VERSION

    def array(self, name: str) -> np.ndarray:
        if name not in _ARRAY_NAMES:
            raise KeyError(name)
        return getattr(self, name)

    def to_dict(self) -> dict[str, Any]:
        return _result_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class CpuFgmresCheckpointVectorV2:
    """One immutable CPU accepted-state vector pair for a restart row."""

    restart_index: int
    solution: np.ndarray
    true_residual: np.ndarray
    solution_sha256: str
    true_residual_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "restart_index": self.restart_index,
            "solution": {
                "dtype": "<f8",
                "shape": list(self.solution.shape),
                "byte_length": int(self.solution.nbytes),
                "sha256": self.solution_sha256,
            },
            "true_residual": {
                "dtype": "<f8",
                "shape": list(self.true_residual.shape),
                "byte_length": int(self.true_residual.nbytes),
                "sha256": self.true_residual_sha256,
            },
        }


@dataclass(frozen=True, slots=True)
class CpuFgmresCheckpointHistoryResultV2:
    """Additive deterministic CPU result retaining every committed checkpoint."""

    schema_version: str
    capability_profile: str
    base_result: CpuFgmresReferenceResultV1
    checkpoints: tuple[CpuFgmresCheckpointVectorV2, ...]
    checkpoint_bundle_hash: str
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_cpu_fgmres_checkpoint_history_result_v2_shallow(self)
        return _checkpoint_history_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class _CoreOutcome:
    status: FgmresStatus
    termination_code: str
    solution: np.ndarray
    residual: np.ndarray
    iteration_count: int
    restart_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    initial_residual_l2: float
    tolerance_l2: float
    history: tuple[FgmresRestartRecord, ...]


def compile_fgmres_policy_v1(
    *,
    restart_dimension: int = 16,
    max_iterations: int = 64,
    absolute_tolerance: float = 0.0,
    relative_tolerance: float = 1.0e-10,
    stagnation_checkpoint_limit: int = 2,
    stagnation_relative_tolerance: float = _SQRT_EPS,
    divergence_factor: float = 1.0e8,
) -> FgmresPolicyV1:
    """Compile a bounded deterministic FGMRES policy."""

    draft = FgmresPolicyV1(
        restart_dimension,
        max_iterations,
        absolute_tolerance,
        relative_tolerance,
        stagnation_checkpoint_limit,
        stagnation_relative_tolerance,
        divergence_factor,
        _ZERO_HASH,
    )
    _validate_fgmres_policy_fields(draft)
    checked = replace(
        draft,
        policy_hash=canonical_hash(_policy_payload(draft, include_hash=False)),
    )
    return validate_fgmres_policy_v1(checked)


def validate_fgmres_policy_v1(policy: FgmresPolicyV1) -> FgmresPolicyV1:
    _validate_fgmres_policy_fields(policy)
    if not _valid_hash(policy.policy_hash) or policy.policy_hash != canonical_hash(
        _policy_payload(policy, include_hash=False)
    ):
        _fail("fgmres_policy_hash_mismatch", "/policy_hash")
    return policy


def _validate_fgmres_policy_fields(policy: FgmresPolicyV1) -> None:
    if type(policy) is not FgmresPolicyV1:
        _fail("fgmres_policy_type_invalid", "/")
    if (
        type(policy.restart_dimension) is not int
        or not 1 <= policy.restart_dimension <= 16
    ):
        _fail("fgmres_restart_dimension_invalid", "/restart_dimension")
    if type(policy.max_iterations) is not int or not 0 <= policy.max_iterations <= 4096:
        _fail("fgmres_max_iterations_invalid", "/max_iterations")
    if (
        type(policy.stagnation_checkpoint_limit) is not int
        or not 2 <= policy.stagnation_checkpoint_limit <= 16
    ):
        _fail(
            "fgmres_stagnation_checkpoint_limit_invalid",
            "/stagnation_checkpoint_limit",
        )
    for name, allow_zero in (
        ("absolute_tolerance", True),
        ("relative_tolerance", True),
        ("stagnation_relative_tolerance", False),
        ("divergence_factor", False),
    ):
        value = getattr(policy, name)
        if (
            type(value) is not float
            or not math.isfinite(value)
            or (value < 0.0 if allow_zero else value <= 0.0)
        ):
            _fail(f"fgmres_{name}_invalid", f"/{name}")
    if policy.absolute_tolerance == 0.0 and policy.relative_tolerance == 0.0:
        _fail("fgmres_tolerance_empty", "/tolerance")
    if policy.stagnation_relative_tolerance >= 1.0:
        _fail(
            "fgmres_stagnation_relative_tolerance_invalid",
            "/stagnation_relative_tolerance",
        )
    if policy.divergence_factor <= 1.0:
        _fail("fgmres_divergence_factor_invalid", "/divergence_factor")


def solve_cpu_fgmres_reference_v1(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    *,
    initial_full_state: np.ndarray | None = None,
) -> CpuFgmresReferenceResultV1:
    """Solve ``K_ff x = F_f`` without an iterative-library fallback."""

    validate_execution_plan_v2(plan)
    validate_fgmres_policy_v1(policy)
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    initial_reduced = _initial_reduced_state(plan, free, initial_full_state)
    rhs = immutable_array(plan.array("global_load")[free], dtype="<f8")
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    inverse_diagonal = _positive_jacobi_inverse(row_ptr, columns, values)

    def matvec(vector: np.ndarray) -> np.ndarray:
        return _csr_matvec(row_ptr, columns, values, vector)

    outcome = _fgmres_core(
        matvec=matvec,
        rhs=rhs,
        initial_solution=initial_reduced,
        inverse_diagonal=inverse_diagonal,
        policy=policy,
        authoritative_tolerance=plan.residual_tolerance,
    )
    result = _build_result(plan, policy, initial_reduced, rhs, outcome)
    validate_cpu_fgmres_reference_result_v1(
        result,
        expected_plan=plan,
        expected_policy=policy,
        expected_initial_full_state=initial_full_state,
    )
    return result


def solve_cpu_fgmres_checkpoint_history_v2(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    *,
    initial_full_state: np.ndarray | None = None,
) -> CpuFgmresCheckpointHistoryResultV2:
    """Replay the CPU oracle while retaining each published checkpoint pair."""

    validate_execution_plan_v2(plan)
    validate_fgmres_policy_v1(policy)
    result = _solve_cpu_fgmres_checkpoint_history_v2_unchecked(
        plan,
        policy,
        initial_full_state=initial_full_state,
    )
    return validate_cpu_fgmres_checkpoint_history_result_v2(
        result,
        expected_plan=plan,
        expected_policy=policy,
        expected_initial_full_state=initial_full_state,
    )


def validate_cpu_fgmres_checkpoint_history_result_v2(
    result: CpuFgmresCheckpointHistoryResultV2,
    *,
    expected_plan: ExecutionPlanV2,
    expected_policy: FgmresPolicyV1,
    expected_initial_full_state: np.ndarray | None = None,
) -> CpuFgmresCheckpointHistoryResultV2:
    """Validate vector lineage, sparse residual replay, metrics, and determinism."""

    validate_cpu_fgmres_checkpoint_history_result_v2_shallow(result)
    validate_execution_plan_v2(expected_plan)
    validate_fgmres_policy_v1(expected_policy)
    validate_cpu_fgmres_reference_result_v1(
        result.base_result,
        expected_plan=expected_plan,
        expected_policy=expected_policy,
        expected_initial_full_state=expected_initial_full_state,
    )
    base = result.base_result
    if len(result.checkpoints) != len(base.history):
        _fail("cpu_fgmres_checkpoint_history_count_invalid", "/checkpoints")
    free = expected_plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = immutable_array(expected_plan.array("global_load")[free], dtype="<f8")
    row_ptr = expected_plan.array("reduced_csr_row_ptr")
    columns = expected_plan.array("reduced_csr_column_indices")
    values = expected_plan.array("reduced_stiffness_csr_values")
    previous = _initial_reduced_state(
        expected_plan,
        free,
        expected_initial_full_state,
    )
    for index, (checkpoint, history_row) in enumerate(
        zip(result.checkpoints, base.history, strict=True)
    ):
        if (
            checkpoint.restart_index != index + 1
            or checkpoint.restart_index != history_row.restart_index
            or checkpoint.solution.shape != (free.size,)
            or checkpoint.true_residual.shape != (free.size,)
            or checkpoint.solution.dtype.str != "<f8"
            or checkpoint.true_residual.dtype.str != "<f8"
            or not checkpoint.solution.flags.c_contiguous
            or not checkpoint.true_residual.flags.c_contiguous
            or not has_immutable_bytes_backing(checkpoint.solution)
            or not has_immutable_bytes_backing(checkpoint.true_residual)
            or not np.isfinite(checkpoint.solution).all()
            or not np.isfinite(checkpoint.true_residual).all()
            or checkpoint.solution_sha256 != array_data_hash(checkpoint.solution)
            or checkpoint.true_residual_sha256
            != array_data_hash(checkpoint.true_residual)
        ):
            _fail(
                "cpu_fgmres_checkpoint_vector_invalid",
                f"/checkpoints/{index}",
            )
        try:
            with np.errstate(over="raise", invalid="raise"):
                replay = rhs - _csr_matvec(
                    row_ptr,
                    columns,
                    values,
                    checkpoint.solution,
                )
        except (FloatingPointError, OverflowError, ValueError) as exc:
            _fail(
                "cpu_fgmres_checkpoint_residual_replay_failed",
                f"/checkpoints/{index}/true_residual",
                type(exc).__name__,
            )
        replay[replay == 0.0] = 0.0
        update = checkpoint.solution - previous
        if (
            not np.array_equal(replay, checkpoint.true_residual)
            or _stable_l2(checkpoint.true_residual) != history_row.true_residual_l2
            or _linf(checkpoint.true_residual) != history_row.true_residual_linf
            or _linf(checkpoint.true_residual) / max(1.0, _linf(rhs))
            != history_row.scaled_true_residual
            or _stable_l2(update) != history_row.solution_update_l2
        ):
            _fail(
                "cpu_fgmres_checkpoint_metric_invalid",
                f"/checkpoints/{index}",
            )
        previous = checkpoint.solution
    expected_bundle_hash = canonical_hash([row.to_dict() for row in result.checkpoints])
    if (
        result.checkpoint_bundle_hash != expected_bundle_hash
        or result.result_hash
        != canonical_hash(_checkpoint_history_payload(result, include_hash=False))
    ):
        _fail("cpu_fgmres_checkpoint_history_hash_invalid", "/result_hash")
    replayed = _solve_cpu_fgmres_checkpoint_history_v2_unchecked(
        expected_plan,
        expected_policy,
        initial_full_state=expected_initial_full_state,
    )
    if _checkpoint_history_payload(
        result, include_hash=True
    ) != _checkpoint_history_payload(replayed, include_hash=True) or any(
        not np.array_equal(left.solution, right.solution)
        or not np.array_equal(left.true_residual, right.true_residual)
        for left, right in zip(
            result.checkpoints,
            replayed.checkpoints,
            strict=True,
        )
    ):
        _fail("cpu_fgmres_checkpoint_history_replay_mismatch", "/")
    return result


def validate_cpu_fgmres_checkpoint_history_result_v2_shallow(
    result: CpuFgmresCheckpointHistoryResultV2,
) -> CpuFgmresCheckpointHistoryResultV2:
    if (
        type(result) is not CpuFgmresCheckpointHistoryResultV2
        or result.schema_version != CPU_FGMRES_CHECKPOINT_HISTORY_V2_SCHEMA_VERSION
        or result.capability_profile
        != CPU_FGMRES_CHECKPOINT_HISTORY_V2_CAPABILITY_PROFILE
        or type(result.base_result) is not CpuFgmresReferenceResultV1
        or type(result.checkpoints) is not tuple
        or any(
            type(row) is not CpuFgmresCheckpointVectorV2 for row in result.checkpoints
        )
        or not _valid_hash(result.checkpoint_bundle_hash)
        or not _valid_hash(result.result_hash)
    ):
        _fail("cpu_fgmres_checkpoint_history_type_invalid", "/")
    _validate_schema(
        _checkpoint_history_schema(),
        _checkpoint_history_payload(result, include_hash=True),
    )
    return result


def validate_cpu_fgmres_reference_result_v1(
    result: CpuFgmresReferenceResultV1,
    *,
    expected_plan: ExecutionPlanV2,
    expected_policy: FgmresPolicyV1,
    expected_initial_full_state: np.ndarray | None = None,
) -> CpuFgmresReferenceResultV1:
    """Validate bindings, arrays, true residual, and deterministic replay."""

    if type(result) is not CpuFgmresReferenceResultV1:
        _fail("cpu_fgmres_result_type_invalid", "/")
    validate_execution_plan_v2(expected_plan)
    validate_fgmres_policy_v1(expected_policy)
    if type(result.policy) is not FgmresPolicyV1:
        _fail("cpu_fgmres_policy_type_invalid", "/policy")
    if result.policy != expected_policy:
        _fail("cpu_fgmres_policy_mismatch", "/policy")
    if (
        type(result.history) is not tuple
        or any(type(row) is not FgmresRestartRecord for row in result.history)
        or type(result.descriptors) is not tuple
        or any(type(row) is not CpuFgmresArrayDescriptor for row in result.descriptors)
    ):
        _fail("cpu_fgmres_result_container_invalid", "/")
    payload = _result_payload(result, include_hash=True)
    _validate_schema(_result_schema(), payload)
    bindings = (
        (result.execution_plan_hash, expected_plan.plan_hash),
        (result.operator_hash, expected_plan.operator_hash),
        (result.numeric_snapshot_hash, expected_plan.numeric_snapshot_hash),
        (result.partition_hash, expected_plan.partition_hash),
        (result.policy.policy_hash, expected_policy.policy_hash),
    )
    if any(actual != expected for actual, expected in bindings):
        _fail("cpu_fgmres_binding_mismatch", "/bindings")
    free = expected_plan.array("free_dofs").astype(np.int64, copy=False)
    initial_reduced = _initial_reduced_state(
        expected_plan, free, expected_initial_full_state
    )
    rhs = immutable_array(expected_plan.array("global_load")[free], dtype="<f8")
    if result.initial_reduced_state_hash != array_data_hash(
        initial_reduced
    ) or result.rhs_hash != array_data_hash(rhs):
        _fail("cpu_fgmres_source_hash_mismatch", "/bindings")
    if tuple(row.name for row in result.descriptors) != _ARRAY_NAMES:
        _fail("cpu_fgmres_descriptor_set_invalid", "/arrays")
    descriptor_map = {row.name: row for row in result.descriptors}
    if len(descriptor_map) != 2:
        _fail("cpu_fgmres_descriptor_set_invalid", "/arrays")
    for name in _ARRAY_NAMES:
        array = result.array(name)
        if (
            type(array) is not np.ndarray
            or array.dtype.str != "<f8"
            or array.shape != (free.size,)
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
            or not np.isfinite(array).all()
            or np.any(np.signbit(array[array == 0.0]))
            or _array_descriptor(name, array) != descriptor_map[name]
        ):
            _fail("cpu_fgmres_array_invalid", f"/arrays/{name}")
    try:
        with np.errstate(over="raise", invalid="raise"):
            actual_residual = rhs - _csr_matvec(
                expected_plan.array("reduced_csr_row_ptr"),
                expected_plan.array("reduced_csr_column_indices"),
                expected_plan.array("reduced_stiffness_csr_values"),
                result.reduced_solution,
            )
    except (FloatingPointError, OverflowError, ValueError) as error:
        _fail(
            "cpu_fgmres_residual_replay_failed",
            "/arrays/reduced_solution",
            type(error).__name__,
        )
    actual_residual[actual_residual == 0.0] = 0.0
    if not np.array_equal(actual_residual, result.true_residual):
        _fail("cpu_fgmres_true_residual_mismatch", "/arrays/true_residual")
    try:
        with np.errstate(over="raise", invalid="raise"):
            initial_residual = rhs - _csr_matvec(
                expected_plan.array("reduced_csr_row_ptr"),
                expected_plan.array("reduced_csr_column_indices"),
                expected_plan.array("reduced_stiffness_csr_values"),
                initial_reduced,
            )
    except (FloatingPointError, OverflowError, ValueError) as error:
        _fail(
            "cpu_fgmres_initial_residual_replay_failed",
            "/initial_full_state",
            type(error).__name__,
        )
    initial_residual[initial_residual == 0.0] = 0.0
    final_l2 = _stable_l2(actual_residual)
    final_linf = _linf(actual_residual)
    rhs_linf = _linf(rhs)
    scaled = final_linf / max(1.0, rhs_linf)
    if any(
        (
            result.final_residual_l2 != final_l2,
            result.final_residual_linf != final_linf,
            result.scaled_true_residual != scaled,
            result.solver_tolerance_passed != (final_l2 <= result.solver_tolerance_l2),
            result.authoritative_plan_tolerance_passed
            != (scaled <= expected_plan.residual_tolerance),
            (result.status == "converged")
            != (
                result.solver_tolerance_passed
                and result.authoritative_plan_tolerance_passed
            ),
        )
    ):
        _fail("cpu_fgmres_metric_mismatch", "/metrics")
    _validate_result_semantics(
        result,
        initial_solution=initial_reduced,
        initial_residual=initial_residual,
        rhs=rhs,
    )
    expected_hash = canonical_hash(_result_payload(result, include_hash=False))
    if result.result_hash != expected_hash:
        _fail("cpu_fgmres_result_hash_mismatch", "/result_hash")
    replayed = solve_cpu_fgmres_reference_v1_unchecked(
        expected_plan,
        expected_policy,
        initial_full_state=expected_initial_full_state,
    )
    if (
        _result_payload(result, include_hash=True)
        != _result_payload(replayed, include_hash=True)
        or not np.array_equal(result.reduced_solution, replayed.reduced_solution)
        or not np.array_equal(result.true_residual, replayed.true_residual)
    ):
        _fail("cpu_fgmres_replay_mismatch", "/")
    return result


def solve_cpu_fgmres_reference_v1_unchecked(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    *,
    initial_full_state: np.ndarray | None = None,
) -> CpuFgmresReferenceResultV1:
    """Internal deterministic replay without recursive validation."""

    free = plan.array("free_dofs").astype(np.int64, copy=False)
    initial_reduced = _initial_reduced_state(plan, free, initial_full_state)
    rhs = immutable_array(plan.array("global_load")[free], dtype="<f8")
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    inverse_diagonal = _positive_jacobi_inverse(row_ptr, columns, values)
    outcome = _fgmres_core(
        matvec=lambda vector: _csr_matvec(row_ptr, columns, values, vector),
        rhs=rhs,
        initial_solution=initial_reduced,
        inverse_diagonal=inverse_diagonal,
        policy=policy,
        authoritative_tolerance=plan.residual_tolerance,
    )
    return _build_result(plan, policy, initial_reduced, rhs, outcome)


def _solve_cpu_fgmres_checkpoint_history_v2_unchecked(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    *,
    initial_full_state: np.ndarray | None,
) -> CpuFgmresCheckpointHistoryResultV2:
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    initial_reduced = _initial_reduced_state(plan, free, initial_full_state)
    rhs = immutable_array(plan.array("global_load")[free], dtype="<f8")
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    inverse_diagonal = _positive_jacobi_inverse(row_ptr, columns, values)
    checkpoints: list[CpuFgmresCheckpointVectorV2] = []

    def capture(
        record: FgmresRestartRecord,
        solution: np.ndarray,
        residual: np.ndarray,
    ) -> None:
        solution_snapshot = immutable_array(solution, dtype="<f8")
        residual_snapshot = immutable_array(residual, dtype="<f8")
        checkpoints.append(
            CpuFgmresCheckpointVectorV2(
                restart_index=record.restart_index,
                solution=solution_snapshot,
                true_residual=residual_snapshot,
                solution_sha256=array_data_hash(solution_snapshot),
                true_residual_sha256=array_data_hash(residual_snapshot),
            )
        )

    outcome = _fgmres_core(
        matvec=lambda vector: _csr_matvec(row_ptr, columns, values, vector),
        rhs=rhs,
        initial_solution=initial_reduced,
        inverse_diagonal=inverse_diagonal,
        policy=policy,
        authoritative_tolerance=plan.residual_tolerance,
        checkpoint_sink=capture,
    )
    base = _build_result(plan, policy, initial_reduced, rhs, outcome)
    rows = tuple(checkpoints)
    bundle_hash = canonical_hash([row.to_dict() for row in rows])
    draft = CpuFgmresCheckpointHistoryResultV2(
        schema_version=CPU_FGMRES_CHECKPOINT_HISTORY_V2_SCHEMA_VERSION,
        capability_profile=CPU_FGMRES_CHECKPOINT_HISTORY_V2_CAPABILITY_PROFILE,
        base_result=base,
        checkpoints=rows,
        checkpoint_bundle_hash=bundle_hash,
        result_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        result_hash=canonical_hash(
            _checkpoint_history_payload(draft, include_hash=False)
        ),
    )


def _validate_result_semantics(
    result: CpuFgmresReferenceResultV1,
    *,
    initial_solution: np.ndarray,
    initial_residual: np.ndarray,
    rhs: np.ndarray,
) -> None:
    count_names = (
        "iteration_count",
        "restart_count",
        "operator_apply_count",
        "preconditioner_apply_count",
    )
    metric_names = (
        "initial_residual_l2",
        "solver_tolerance_l2",
        "final_residual_l2",
        "final_residual_linf",
        "scaled_true_residual",
    )
    if any(type(getattr(result, name)) is not int for name in count_names):
        _fail("cpu_fgmres_count_type_invalid", "/counts")
    if any(type(getattr(result, name)) is not float for name in metric_names):
        _fail("cpu_fgmres_metric_type_invalid", "/metrics")
    if (
        type(result.solver_tolerance_passed) is not bool
        or type(result.authoritative_plan_tolerance_passed) is not bool
    ):
        _fail("cpu_fgmres_metric_type_invalid", "/metrics")

    expected_initial_l2 = _stable_l2(initial_residual)
    expected_tolerance_l2 = max(
        result.policy.absolute_tolerance,
        result.policy.relative_tolerance * _stable_l2(rhs),
    )
    if (
        result.initial_residual_l2 != expected_initial_l2
        or result.solver_tolerance_l2 != expected_tolerance_l2
    ):
        _fail("cpu_fgmres_initial_metric_mismatch", "/metrics")
    if (
        result.iteration_count > result.policy.max_iterations
        or result.operator_apply_count < 1 + result.iteration_count
    ):
        _fail("cpu_fgmres_count_invariant_invalid", "/counts")

    if result.status == "numerical_failure":
        if result.restart_count not in {
            len(result.history),
            len(result.history) + 1,
        } or not (
            result.iteration_count
            <= result.preconditioner_apply_count
            <= result.iteration_count + 1
        ):
            _fail("cpu_fgmres_failure_count_invariant_invalid", "/counts")
    elif (
        result.restart_count != len(result.history)
        or result.preconditioner_apply_count != result.iteration_count
    ):
        _fail("cpu_fgmres_count_invariant_invalid", "/counts")

    cursor = 0
    step_total = 0
    for index, row in enumerate(result.history, start=1):
        row_metrics = (
            row.estimated_residual_l2,
            row.true_residual_l2,
            row.true_residual_linf,
            row.scaled_true_residual,
            row.solution_update_l2,
        )
        if (
            type(row.restart_index) is not int
            or type(row.start_iteration) is not int
            or type(row.end_iteration) is not int
            or type(row.arnoldi_step_count) is not int
            or type(row.preconditioner_apply_count) is not int
            or type(row.reorthogonalization_count) is not int
            or any(type(value) is not float for value in row_metrics)
            or any(not math.isfinite(value) or value < 0.0 for value in row_metrics)
            or row.restart_index != index
            or row.start_iteration != cursor
            or row.end_iteration - row.start_iteration != row.arnoldi_step_count
            or not 1 <= row.arnoldi_step_count <= result.policy.restart_dimension
            or row.preconditioner_apply_count != row.arnoldi_step_count
            or not 0 <= row.reorthogonalization_count <= row.arnoldi_step_count
            or row.true_residual_linf > row.true_residual_l2
            or row.scaled_true_residual != row.true_residual_linf / max(1.0, _linf(rhs))
        ):
            _fail("cpu_fgmres_history_invariant_invalid", f"/history/{index - 1}")
        if index < len(result.history) and row.termination_hint != "restart_completed":
            _fail("cpu_fgmres_history_hint_invalid", f"/history/{index - 1}")
        cursor = row.end_iteration
        step_total += row.arnoldi_step_count

    if result.status == "numerical_failure":
        if step_total > result.iteration_count:
            _fail("cpu_fgmres_failure_history_invalid", "/history")
    elif step_total != result.iteration_count:
        _fail("cpu_fgmres_history_count_mismatch", "/history")

    if result.history and result.status != "numerical_failure":
        last = result.history[-1]
        expected_hint = {
            "converged_happy_breakdown": "converged_happy_breakdown",
            "converged_true_residual": "converged_true_residual",
            "converged_restart_true_residual": "restart_completed",
            "max_iterations_exhausted": "restart_completed",
            "true_residual_stagnated": "restart_completed",
            "true_residual_diverged": "restart_completed",
            "arnoldi_invariant_subspace_breakdown": (
                "arnoldi_invariant_subspace_breakdown"
            ),
            "arnoldi_triangular_factor_breakdown": (
                "arnoldi_triangular_factor_breakdown"
            ),
        }.get(result.termination_code)
        if (
            last.end_iteration != result.iteration_count
            or last.true_residual_l2 != result.final_residual_l2
            or last.true_residual_linf != result.final_residual_linf
            or last.scaled_true_residual != result.scaled_true_residual
            or expected_hint is None
            or last.termination_hint != expected_hint
        ):
            _fail("cpu_fgmres_terminal_history_mismatch", "/history")

    divergence_observed = result.final_residual_l2 > (
        result.policy.divergence_factor
        * max(result.initial_residual_l2, np.finfo(float).tiny)
    )
    if (result.status == "diverged") != divergence_observed:
        _fail("cpu_fgmres_divergence_terminal_invalid", "/status")

    if result.termination_code == "converged_initial_true_residual":
        if (
            result.iteration_count != 0
            or result.restart_count != 0
            or result.operator_apply_count != 1
            or result.preconditioner_apply_count != 0
            or result.history
            or not np.array_equal(result.reduced_solution, initial_solution)
        ):
            _fail("cpu_fgmres_initial_terminal_invalid", "/")
        if not np.array_equal(result.true_residual, initial_residual):
            _fail("cpu_fgmres_initial_terminal_invalid", "/arrays/true_residual")
    elif result.status == "max_iterations":
        if result.iteration_count != result.policy.max_iterations:
            _fail("cpu_fgmres_max_iteration_terminal_invalid", "/counts")
    elif result.iteration_count == 0 and result.status != "numerical_failure":
        _fail("cpu_fgmres_zero_iteration_terminal_invalid", "/counts")
    if result.iteration_count == 0 and (
        not np.array_equal(result.reduced_solution, initial_solution)
        or not np.array_equal(result.true_residual, initial_residual)
        or result.history
    ):
        _fail("cpu_fgmres_zero_iteration_state_invalid", "/arrays")


def _fgmres_core(
    *,
    matvec: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    initial_solution: np.ndarray,
    inverse_diagonal: np.ndarray,
    policy: FgmresPolicyV1,
    authoritative_tolerance: float,
    checkpoint_sink: (
        Callable[[FgmresRestartRecord, np.ndarray, np.ndarray], None] | None
    ) = None,
) -> _CoreOutcome:
    validate_fgmres_policy_v1(policy)
    if (
        type(authoritative_tolerance) is not float
        or not math.isfinite(authoritative_tolerance)
        or authoritative_tolerance < 0.0
    ):
        _fail(
            "cpu_fgmres_authoritative_tolerance_invalid",
            "/authoritative_tolerance",
        )
    b = np.ascontiguousarray(rhs, dtype="<f8")
    x = np.ascontiguousarray(initial_solution, dtype="<f8").copy()
    inverse = np.ascontiguousarray(inverse_diagonal, dtype="<f8")
    if b.shape != x.shape or b.shape != inverse.shape or b.ndim != 1 or b.size == 0:
        _fail("cpu_fgmres_core_shape_invalid", "/core")
    if not np.isfinite(b).all() or not np.isfinite(x).all():
        _fail("cpu_fgmres_core_input_nonfinite", "/core")
    if not np.isfinite(inverse).all() or np.any(inverse <= 0.0):
        _fail("cpu_fgmres_jacobi_invalid", "/preconditioner")
    operator_apply_count = 0

    def apply(vector: np.ndarray) -> np.ndarray:
        nonlocal operator_apply_count
        result = np.ascontiguousarray(matvec(vector), dtype="<f8")
        operator_apply_count += 1
        if result.shape != b.shape or not np.isfinite(result).all():
            raise FloatingPointError("operator application is nonfinite or malformed")
        result[result == 0.0] = 0.0
        return result

    try:
        with np.errstate(over="raise", invalid="raise"):
            residual = b - apply(x)
    except Exception as error:
        _fail(
            "cpu_fgmres_initial_operator_application_failed",
            "/core/operator",
            type(error).__name__,
        )
    residual[residual == 0.0] = 0.0
    initial_l2 = _stable_l2(residual)
    rhs_l2 = _stable_l2(b)
    tolerance_l2 = max(
        policy.absolute_tolerance,
        policy.relative_tolerance * rhs_l2,
    )
    if not all(math.isfinite(value) for value in (initial_l2, rhs_l2, tolerance_l2)):
        _fail(
            "cpu_fgmres_initial_residual_or_tolerance_nonfinite",
            "/core/tolerance",
        )
    if _both_gates(residual, b, tolerance_l2, authoritative_tolerance):
        return _CoreOutcome(
            "converged",
            "converged_initial_true_residual",
            x,
            residual,
            0,
            0,
            operator_apply_count,
            0,
            initial_l2,
            tolerance_l2,
            (),
        )
    if policy.max_iterations == 0:
        return _CoreOutcome(
            "max_iterations",
            "max_iterations_exhausted",
            x,
            residual,
            0,
            0,
            operator_apply_count,
            0,
            initial_l2,
            tolerance_l2,
            (),
        )

    history: list[FgmresRestartRecord] = []
    iteration_count = 0
    restart_count = 0
    preconditioner_apply_count = 0
    stagnant_checkpoints = 0
    previous_true_l2 = initial_l2
    while iteration_count < policy.max_iterations:
        restart_count += 1
        cycle_start = iteration_count
        beta = _stable_l2(residual)
        if not math.isfinite(beta) or beta <= 0.0:
            return _terminal_outcome(
                "numerical_failure",
                "restart_residual_norm_invalid",
                x,
                residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                history,
            )
        remaining = policy.max_iterations - iteration_count
        width = min(policy.restart_dimension, remaining)
        n = b.size
        basis_v = np.zeros((width + 1, n), dtype="<f8")
        basis_z = np.zeros((width, n), dtype="<f8")
        hessenberg = np.zeros((width + 1, width), dtype="<f8")
        cosine = np.zeros(width, dtype="<f8")
        sine = np.zeros(width, dtype="<f8")
        g = np.zeros(width + 1, dtype="<f8")
        basis_v[0] = residual / beta
        g[0] = beta
        step_count = 0
        reorthogonalization_count = 0
        estimated_residual = beta
        invariant_breakdown = False
        candidate_x: np.ndarray | None = None
        candidate_residual: np.ndarray | None = None
        candidate_step_count = 0
        candidate_code = ""
        for column in range(width):
            with np.errstate(over="ignore", invalid="ignore"):
                z = inverse * basis_v[column]
            if not np.isfinite(z).all():
                return _terminal_outcome(
                    "numerical_failure",
                    "preconditioner_application_nonfinite",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            basis_z[column] = z
            preconditioner_apply_count += 1
            try:
                work = apply(z)
            except Exception:
                return _terminal_outcome(
                    "numerical_failure",
                    "arnoldi_operator_application_failed",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            work_before = _stable_l2(work)
            if not math.isfinite(work_before):
                return _terminal_outcome(
                    "numerical_failure",
                    "arnoldi_work_norm_nonfinite",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            try:
                for row in range(column + 1):
                    coefficient = _finite_dot(work, basis_v[row])
                    with np.errstate(over="raise", invalid="raise"):
                        hessenberg[row, column] += coefficient
                        work -= coefficient * basis_v[row]
            except (FloatingPointError, OverflowError):
                return _terminal_outcome(
                    "numerical_failure",
                    "arnoldi_orthogonalization_failed",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            after_first = _stable_l2(work)
            if after_first < _DGKS_ETA * work_before:
                reorthogonalization_count += 1
                try:
                    for row in range(column + 1):
                        coefficient = _finite_dot(work, basis_v[row])
                        with np.errstate(over="raise", invalid="raise"):
                            hessenberg[row, column] += coefficient
                            work -= coefficient * basis_v[row]
                except (FloatingPointError, OverflowError):
                    return _terminal_outcome(
                        "numerical_failure",
                        "arnoldi_reorthogonalization_failed",
                        x,
                        residual,
                        iteration_count,
                        restart_count,
                        operator_apply_count,
                        preconditioner_apply_count,
                        initial_l2,
                        tolerance_l2,
                        history,
                    )
            h_next = _stable_l2(work)
            if not math.isfinite(h_next):
                return _terminal_outcome(
                    "numerical_failure",
                    "arnoldi_norm_nonfinite",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            hessenberg[column + 1, column] = h_next
            breakdown_threshold = _BREAKDOWN_MULTIPLIER * _EPS * work_before
            invariant_breakdown = h_next <= breakdown_threshold
            if not invariant_breakdown:
                basis_v[column + 1] = work / h_next
            for row in range(column):
                upper = hessenberg[row, column]
                lower = hessenberg[row + 1, column]
                with np.errstate(over="ignore", invalid="ignore"):
                    rotated_upper = cosine[row] * upper + sine[row] * lower
                    rotated_lower = -sine[row] * upper + cosine[row] * lower
                if not math.isfinite(float(rotated_upper)) or not math.isfinite(
                    float(rotated_lower)
                ):
                    return _terminal_outcome(
                        "numerical_failure",
                        "givens_rotation_arithmetic_failed",
                        x,
                        residual,
                        iteration_count,
                        restart_count,
                        operator_apply_count,
                        preconditioner_apply_count,
                        initial_l2,
                        tolerance_l2,
                        history,
                    )
                hessenberg[row, column] = rotated_upper
                hessenberg[row + 1, column] = rotated_lower
            upper = float(hessenberg[column, column])
            lower = float(hessenberg[column + 1, column])
            rotation_norm = math.hypot(upper, lower)
            rotation_scale = max(abs(upper), abs(lower))
            if (
                not math.isfinite(rotation_norm)
                or rotation_norm <= _BREAKDOWN_MULTIPLIER * _EPS * rotation_scale
            ):
                invariant_breakdown = True
                cosine[column] = 1.0
                sine[column] = 0.0
            else:
                cosine[column] = upper / rotation_norm
                sine[column] = lower / rotation_norm
                hessenberg[column, column] = rotation_norm
                hessenberg[column + 1, column] = 0.0
            g_current = float(g[column])
            g[column] = cosine[column] * g_current
            g[column + 1] = -sine[column] * g_current
            iteration_count += 1
            step_count += 1
            estimated_residual = abs(float(g[column + 1]))
            if not math.isfinite(estimated_residual):
                return _terminal_outcome(
                    "numerical_failure",
                    "givens_residual_nonfinite",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            if estimated_residual <= tolerance_l2 or invariant_breakdown:
                try:
                    y = _back_substitute(hessenberg, g, step_count)
                except (FloatingPointError, OverflowError):
                    return _terminal_outcome(
                        "numerical_failure",
                        "triangular_solve_arithmetic_failed",
                        x,
                        residual,
                        iteration_count,
                        restart_count,
                        operator_apply_count,
                        preconditioner_apply_count,
                        initial_l2,
                        tolerance_l2,
                        history,
                    )
                if y is None:
                    invariant_breakdown = True
                else:
                    try:
                        candidate_x = _basis_update(x, basis_z, y, step_count)
                        with np.errstate(over="raise", invalid="raise"):
                            candidate_residual = b - apply(candidate_x)
                        candidate_step_count = step_count
                    except Exception:
                        return _terminal_outcome(
                            "numerical_failure",
                            "candidate_true_residual_failed",
                            x,
                            residual,
                            iteration_count,
                            restart_count,
                            operator_apply_count,
                            preconditioner_apply_count,
                            initial_l2,
                            tolerance_l2,
                            history,
                        )
                    candidate_residual[candidate_residual == 0.0] = 0.0
                    if _both_gates(
                        candidate_residual,
                        b,
                        tolerance_l2,
                        authoritative_tolerance,
                    ):
                        candidate_code = (
                            "converged_happy_breakdown"
                            if invariant_breakdown
                            else "converged_true_residual"
                        )
                        try:
                            with np.errstate(over="raise", invalid="raise"):
                                update = candidate_x - x
                            update_l2 = _stable_l2(update)
                        except (FloatingPointError, OverflowError):
                            update_l2 = float("inf")
                        if not math.isfinite(update_l2):
                            return _terminal_outcome(
                                "numerical_failure",
                                "restart_state_nonfinite",
                                x,
                                residual,
                                iteration_count,
                                restart_count,
                                operator_apply_count,
                                preconditioner_apply_count,
                                initial_l2,
                                tolerance_l2,
                                history,
                            )
                        _publish_restart_record(
                            history,
                            _restart_record(
                                restart_count,
                                cycle_start,
                                iteration_count,
                                step_count,
                                reorthogonalization_count,
                                estimated_residual,
                                candidate_residual,
                                b,
                                update_l2,
                                candidate_code,
                            ),
                            solution=candidate_x,
                            residual=candidate_residual,
                            checkpoint_sink=checkpoint_sink,
                        )
                        return _CoreOutcome(
                            "converged",
                            candidate_code,
                            candidate_x,
                            candidate_residual,
                            iteration_count,
                            restart_count,
                            operator_apply_count,
                            preconditioner_apply_count,
                            initial_l2,
                            tolerance_l2,
                            tuple(history),
                        )
                if invariant_breakdown:
                    break
        if (
            candidate_x is None
            or candidate_residual is None
            or candidate_step_count != step_count
        ):
            try:
                y = _back_substitute(hessenberg, g, step_count)
            except (FloatingPointError, OverflowError):
                return _terminal_outcome(
                    "numerical_failure",
                    "triangular_solve_arithmetic_failed",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            if y is None:
                _publish_restart_record(
                    history,
                    _restart_record(
                        restart_count,
                        cycle_start,
                        iteration_count,
                        step_count,
                        reorthogonalization_count,
                        estimated_residual,
                        residual,
                        b,
                        0.0,
                        "arnoldi_triangular_factor_breakdown",
                    ),
                    solution=x,
                    residual=residual,
                    checkpoint_sink=checkpoint_sink,
                )
                return _terminal_outcome(
                    "arnoldi_breakdown",
                    "arnoldi_triangular_factor_breakdown",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            try:
                candidate_x = _basis_update(x, basis_z, y, step_count)
                with np.errstate(over="raise", invalid="raise"):
                    candidate_residual = b - apply(candidate_x)
                candidate_step_count = step_count
            except Exception:
                return _terminal_outcome(
                    "numerical_failure",
                    "restart_true_residual_failed",
                    x,
                    residual,
                    iteration_count,
                    restart_count,
                    operator_apply_count,
                    preconditioner_apply_count,
                    initial_l2,
                    tolerance_l2,
                    history,
                )
            candidate_residual[candidate_residual == 0.0] = 0.0
        try:
            with np.errstate(over="raise", invalid="raise"):
                update = candidate_x - x
            update_l2 = _stable_l2(update)
        except (FloatingPointError, OverflowError):
            update_l2 = float("inf")
        true_l2 = _stable_l2(candidate_residual)
        if not all(math.isfinite(value) for value in (update_l2, true_l2)):
            return _terminal_outcome(
                "numerical_failure",
                "restart_state_nonfinite",
                x,
                residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                history,
            )
        hint = (
            "arnoldi_invariant_subspace_breakdown"
            if invariant_breakdown
            else "restart_completed"
        )
        _publish_restart_record(
            history,
            _restart_record(
                restart_count,
                cycle_start,
                iteration_count,
                step_count,
                reorthogonalization_count,
                estimated_residual,
                candidate_residual,
                b,
                update_l2,
                hint,
            ),
            solution=candidate_x,
            residual=candidate_residual,
            checkpoint_sink=checkpoint_sink,
        )
        if _both_gates(candidate_residual, b, tolerance_l2, authoritative_tolerance):
            return _CoreOutcome(
                "converged",
                "converged_restart_true_residual",
                candidate_x,
                candidate_residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                tuple(history),
            )
        if invariant_breakdown:
            return _CoreOutcome(
                "arnoldi_breakdown",
                "arnoldi_invariant_subspace_breakdown",
                candidate_x,
                candidate_residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                tuple(history),
            )
        if true_l2 > policy.divergence_factor * max(initial_l2, np.finfo(float).tiny):
            return _CoreOutcome(
                "diverged",
                "true_residual_diverged",
                candidate_x,
                candidate_residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                tuple(history),
            )
        candidate_scale = _stable_l2(candidate_x)
        previous_scale = _stable_l2(x)
        x_scale = candidate_scale + previous_scale
        if not all(
            math.isfinite(value) for value in (candidate_scale, previous_scale, x_scale)
        ):
            return _CoreOutcome(
                "numerical_failure",
                "restart_state_nonfinite",
                x,
                residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                tuple(history),
            )
        plateau = (
            true_l2 >= (1.0 - policy.stagnation_relative_tolerance) * previous_true_l2
        )
        tiny_update = update_l2 <= _SQRT_EPS * x_scale
        stagnant_checkpoints = (
            stagnant_checkpoints + 1 if plateau and tiny_update else 0
        )
        x = candidate_x
        residual = candidate_residual
        previous_true_l2 = true_l2
        if stagnant_checkpoints >= policy.stagnation_checkpoint_limit:
            return _CoreOutcome(
                "stagnated",
                "true_residual_stagnated",
                x,
                residual,
                iteration_count,
                restart_count,
                operator_apply_count,
                preconditioner_apply_count,
                initial_l2,
                tolerance_l2,
                tuple(history),
            )
    return _CoreOutcome(
        "max_iterations",
        "max_iterations_exhausted",
        x,
        residual,
        iteration_count,
        restart_count,
        operator_apply_count,
        preconditioner_apply_count,
        initial_l2,
        tolerance_l2,
        tuple(history),
    )


def _terminal_outcome(
    status: FgmresStatus,
    code: str,
    solution: np.ndarray,
    residual: np.ndarray,
    iteration_count: int,
    restart_count: int,
    operator_apply_count: int,
    preconditioner_apply_count: int,
    initial_l2: float,
    tolerance_l2: float,
    history: list[FgmresRestartRecord],
) -> _CoreOutcome:
    return _CoreOutcome(
        status,
        code,
        solution,
        residual,
        iteration_count,
        restart_count,
        operator_apply_count,
        preconditioner_apply_count,
        initial_l2,
        tolerance_l2,
        tuple(history),
    )


def _restart_record(
    restart_index: int,
    start_iteration: int,
    end_iteration: int,
    step_count: int,
    reorthogonalization_count: int,
    estimated_residual: float,
    residual: np.ndarray,
    rhs: np.ndarray,
    update_l2: float,
    hint: str,
) -> FgmresRestartRecord:
    true_l2 = _stable_l2(residual)
    true_linf = _linf(residual)
    scaled = true_linf / max(1.0, _linf(rhs))
    return FgmresRestartRecord(
        restart_index,
        start_iteration,
        end_iteration,
        step_count,
        step_count,
        reorthogonalization_count,
        estimated_residual,
        true_l2,
        true_linf,
        scaled,
        update_l2,
        hint,
    )


def _publish_restart_record(
    history: list[FgmresRestartRecord],
    record: FgmresRestartRecord,
    *,
    solution: np.ndarray,
    residual: np.ndarray,
    checkpoint_sink: (
        Callable[[FgmresRestartRecord, np.ndarray, np.ndarray], None] | None
    ),
) -> None:
    history.append(record)
    if checkpoint_sink is not None:
        checkpoint_sink(record, solution, residual)


def _back_substitute(
    hessenberg: np.ndarray, g: np.ndarray, count: int
) -> np.ndarray | None:
    if count <= 0:
        return None
    y = np.zeros(count, dtype="<f8")
    scale = float(np.max(np.abs(hessenberg[:count, :count])))
    if not math.isfinite(scale):
        raise FloatingPointError("triangular factor scale is nonfinite")
    if scale == 0.0:
        return None
    pivot_floor = _BREAKDOWN_MULTIPLIER * _EPS * scale
    for row in range(count - 1, -1, -1):
        pivot = float(hessenberg[row, row])
        if not math.isfinite(pivot):
            raise FloatingPointError("triangular pivot is nonfinite")
        if abs(pivot) <= pivot_floor:
            return None
        tail = _finite_dot(hessenberg[row, row + 1 : count], y[row + 1 :])
        value = (float(g[row]) - tail) / pivot
        if not math.isfinite(value):
            raise FloatingPointError("triangular solution is nonfinite")
        y[row] = value
    return y


def _basis_update(
    base: np.ndarray, basis_z: np.ndarray, y: np.ndarray, count: int
) -> np.ndarray:
    result = base.copy()
    for index in range(count):
        result += float(y[index]) * basis_z[index]
    if not np.isfinite(result).all():
        raise FloatingPointError("basis solution update is nonfinite")
    result[result == 0.0] = 0.0
    return result


def _positive_jacobi_inverse(
    row_ptr: np.ndarray, columns: np.ndarray, values: np.ndarray
) -> np.ndarray:
    count = row_ptr.size - 1
    diagonal = np.empty(count, dtype="<f8")
    for row in range(count):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        matches = np.flatnonzero(columns[begin:end] == row)
        if matches.size != 1:
            _fail("cpu_fgmres_jacobi_diagonal_missing", f"/matrix/row/{row}")
        value = float(values[begin + int(matches[0])])
        if not math.isfinite(value) or value <= 0.0:
            _fail("cpu_fgmres_jacobi_diagonal_nonpositive", f"/matrix/row/{row}")
        diagonal[row] = value
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        inverse = 1.0 / diagonal
    if not np.isfinite(inverse).all() or np.any(inverse <= 0.0):
        _fail("cpu_fgmres_jacobi_inverse_invalid", "/matrix/diagonal")
    return np.ascontiguousarray(inverse, dtype="<f8")


def _csr_matvec(
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    result = np.empty(row_ptr.size - 1, dtype="<f8")
    for row in range(result.size):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        result[row] = _finite_dot(values[begin:end], vector[columns[begin:end]])
    result[result == 0.0] = 0.0
    return result


def _finite_dot(left: np.ndarray, right: np.ndarray) -> float:
    if left.size != right.size:
        raise FloatingPointError("dot shape mismatch")
    try:
        with np.errstate(over="raise", invalid="raise"):
            value = math.fsum(
                float(left[index]) * float(right[index]) for index in range(left.size)
            )
    except (FloatingPointError, OverflowError, ValueError) as error:
        raise FloatingPointError("dot arithmetic failed") from error
    if not math.isfinite(value):
        raise FloatingPointError("dot is nonfinite")
    return 0.0 if value == 0.0 else value


def _stable_l2(vector: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for raw in vector:
        value = abs(float(raw))
        if not math.isfinite(value):
            return float("inf")
        if value == 0.0:
            continue
        if scale < value:
            ratio = 0.0 if scale == 0.0 else scale / value
            sumsq = 1.0 + sumsq * ratio * ratio
            scale = value
        else:
            ratio = value / scale
            sumsq += ratio * ratio
    result = 0.0 if scale == 0.0 else scale * math.sqrt(sumsq)
    return result if math.isfinite(result) else float("inf")


def _linf(vector: np.ndarray) -> float:
    if vector.size == 0:
        return 0.0
    value = float(np.max(np.abs(vector)))
    return value if math.isfinite(value) else float("inf")


def _both_gates(
    residual: np.ndarray,
    rhs: np.ndarray,
    tolerance_l2: float,
    authoritative_tolerance: float,
) -> bool:
    l2 = _stable_l2(residual)
    scaled_linf = _linf(residual) / max(1.0, _linf(rhs))
    return bool(
        math.isfinite(l2)
        and math.isfinite(scaled_linf)
        and l2 <= tolerance_l2
        and scaled_linf <= authoritative_tolerance
    )


def _initial_reduced_state(
    plan: ExecutionPlanV2,
    free: np.ndarray,
    initial_full_state: np.ndarray | None,
) -> np.ndarray:
    if initial_full_state is None:
        return immutable_array(np.zeros(free.size, dtype="<f8"), dtype="<f8")
    if (
        type(initial_full_state) is not np.ndarray
        or initial_full_state.dtype.str != "<f8"
        or initial_full_state.shape != (plan.dof_count,)
        or not np.isfinite(initial_full_state).all()
    ):
        _fail("cpu_fgmres_initial_state_invalid", "/initial_full_state")
    constrained = plan.array("constrained_dofs")
    if np.any(initial_full_state[constrained] != 0.0) or np.any(
        np.signbit(initial_full_state[constrained])
    ):
        _fail("cpu_fgmres_constrained_state_nonzero", "/initial_full_state")
    reduced = np.ascontiguousarray(initial_full_state[free], dtype="<f8")
    reduced[reduced == 0.0] = 0.0
    return immutable_array(reduced, dtype="<f8")


def _build_result(
    plan: ExecutionPlanV2,
    policy: FgmresPolicyV1,
    initial_reduced: np.ndarray,
    rhs: np.ndarray,
    outcome: _CoreOutcome,
) -> CpuFgmresReferenceResultV1:
    solution = immutable_array(outcome.solution, dtype="<f8")
    residual = immutable_array(outcome.residual, dtype="<f8")
    descriptors = (
        _array_descriptor("reduced_solution", solution),
        _array_descriptor("true_residual", residual),
    )
    final_l2 = _stable_l2(residual)
    final_linf = _linf(residual)
    scaled = final_linf / max(1.0, _linf(rhs))
    solver_pass = final_l2 <= outcome.tolerance_l2
    authoritative_pass = scaled <= plan.residual_tolerance
    draft = CpuFgmresReferenceResultV1(
        outcome.status,
        outcome.termination_code,
        plan.plan_hash,
        plan.operator_hash,
        plan.numeric_snapshot_hash,
        plan.partition_hash,
        array_data_hash(initial_reduced),
        array_data_hash(rhs),
        policy,
        outcome.iteration_count,
        outcome.restart_count,
        outcome.operator_apply_count,
        outcome.preconditioner_apply_count,
        outcome.initial_residual_l2,
        outcome.tolerance_l2,
        final_l2,
        final_linf,
        scaled,
        solver_pass,
        authoritative_pass,
        outcome.history,
        descriptors,
        solution,
        residual,
        _ZERO_HASH,
    )
    return replace(
        draft,
        result_hash=canonical_hash(_result_payload(draft, include_hash=False)),
    )


def _array_descriptor(name: str, array: np.ndarray) -> CpuFgmresArrayDescriptor:
    return CpuFgmresArrayDescriptor(
        name,
        "<f8",
        tuple(int(value) for value in array.shape),
        int(array.nbytes),
        array_data_hash(array),
    )


def _policy_payload(policy: FgmresPolicyV1, *, include_hash: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": policy.schema_version,
        "method": "fixed_restart_right_preconditioned_fgmres",
        "restart_dimension": policy.restart_dimension,
        "max_iterations": policy.max_iterations,
        "absolute_tolerance": policy.absolute_tolerance,
        "relative_tolerance": policy.relative_tolerance,
        "stagnation_checkpoint_limit": policy.stagnation_checkpoint_limit,
        "stagnation_relative_tolerance": policy.stagnation_relative_tolerance,
        "divergence_factor": policy.divergence_factor,
        "orthogonalization": "dgks_conditional_two_pass_mgs",
        "preconditioner": "positive_unshifted_jacobi_right",
        "solver_norm": "l2",
        "authoritative_norm": "scaled_true_residual_linf",
        "fallback_forbidden": True,
    }
    if include_hash:
        payload["policy_hash"] = policy.policy_hash
    return payload


def _result_payload(
    result: CpuFgmresReferenceResultV1, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "capability_profile": CPU_FGMRES_REFERENCE_CAPABILITY_PROFILE,
        "status": result.status,
        "termination_code": result.termination_code,
        "bindings": {
            "execution_plan_hash": result.execution_plan_hash,
            "operator_hash": result.operator_hash,
            "numeric_snapshot_hash": result.numeric_snapshot_hash,
            "partition_hash": result.partition_hash,
            "initial_reduced_state_hash": result.initial_reduced_state_hash,
            "rhs_hash": result.rhs_hash,
            "policy_hash": result.policy.policy_hash,
        },
        "policy": result.policy.to_dict(),
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
        "claims": {
            "cpu_reference": True,
            "fixed_restart": True,
            "right_preconditioned": True,
            "positive_unshifted_jacobi": True,
            "true_residual_replay": True,
            "scipy_iterative_solver_used": False,
            "fallback_used": False,
            "hip_execution": False,
            "iteration_host_copy_zero_proven": False,
            "end_to_end_o_n_proven": False,
            "speedup_proven": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["result_hash"] = result.result_hash
    return payload


def _checkpoint_history_payload(
    result: CpuFgmresCheckpointHistoryResultV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "capability_profile": result.capability_profile,
        "base_result_hash": result.base_result.result_hash,
        "execution_plan_hash": result.base_result.execution_plan_hash,
        "policy_hash": result.base_result.policy.policy_hash,
        "checkpoint_count": len(result.checkpoints),
        "checkpoints": [row.to_dict() for row in result.checkpoints],
        "checkpoint_bundle_hash": result.checkpoint_bundle_hash,
        "claims": {
            "deterministic_cpu_reference_replayed": True,
            "committed_checkpoint_solution_vectors_retained": True,
            "committed_checkpoint_true_residual_vectors_retained": True,
            "sparse_true_residual_replayed_per_checkpoint": True,
            "hip_execution": False,
            "fallback_used": False,
            "performance_or_speedup_proven": False,
            "commercial_ready": False,
        },
    }
    if include_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    path = (
        Path(__file__).parents[2]
        / "schemas"
        / "cpu_fgmres_reference_result_v1.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _checkpoint_history_schema() -> dict[str, Any]:
    path = (
        Path(__file__).parents[2]
        / "schemas"
        / "cpu_fgmres_checkpoint_history_v2.schema.json"
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
        _fail("cpu_fgmres_result_schema_invalid", path, error.message)


def _valid_hash(value: Any) -> bool:
    return type(value) is str and _HASH_RE.fullmatch(value) is not None


def _fail(code: str, path: str, message: str = "") -> None:
    raise CpuFgmresReferenceError(code, path, message)
