"""Deterministic CPU oracle for the FGMRES v2 GPU reduction tree.

The oracle mirrors the planned 256-thread/512-value HIP reduction order.  It
is deliberately independent of NumPy/BLAS norm and sparse-matrix routines so
the first device-resident FGMRES slice has a stable numerical comparison
target at block and multistage boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Literal

import numpy as np


FGMRES_GPU_TREE_REFERENCE_V2_VERSION = 2
FGMRES_GPU_TREE_THREADS_PER_BLOCK = 256
FGMRES_GPU_TREE_VALUES_PER_BLOCK = 512
FGMRES_GPU_TREE_MAX_ITERATIONS = 4096

GpuTreeOperation = Literal["lassq_l2", "abs_max_linf", "dot_fp64"]
InitialTerminalStatus = Literal["not_terminal", "converged", "max_iterations"]
FirstColumnGivensPhase = Literal["arnoldi", "candidate"]

_FGMRES_GPU_TREE_BREAKDOWN_TAU = math.ldexp(1.0, -46)
_FGMRES_GPU_TREE_MAX_RESTART_DIMENSION = 16
_FGMRES_GPU_TREE_DBL_MIN_NORMAL = float(np.finfo(np.float64).tiny)
_FGMRES_GPU_TREE_SQRT_EPS = math.ldexp(1.0, -26)
_FGMRES_GPU_TREE_CANDIDATE_RESIDUAL_MASK = (1 << 8) | (1 << 9) | (1 << 10)
_FGMRES_GPU_TREE_COMMITTED_X_L2_BIT = 1 << 11
_FGMRES_GPU_TREE_TRIAL_X_L2_BIT = 1 << 12

_FGMRES_GPU_TREE_TERMINAL_STATUS_CODES = {
    "not_terminal": 0,
    "converged": 1,
    "max_iterations": 2,
    "stagnated": 3,
    "diverged": 4,
    "arnoldi_breakdown": 5,
}
_FGMRES_GPU_TREE_TERMINATION_CODES = {
    "none": 0,
    "converged_happy_breakdown": 2,
    "converged_true_residual": 3,
    "converged_restart_true_residual": 4,
    "max_iterations_exhausted": 10,
    "true_residual_stagnated": 20,
    "true_residual_diverged": 21,
    "arnoldi_triangular_factor_breakdown": 30,
    "arnoldi_invariant_subspace_breakdown": 31,
}
_FGMRES_GPU_TREE_RESTART_HINT_CODES = {
    "none": 0,
    "restart_completed": 1,
    "converged_happy_breakdown": 2,
    "converged_true_residual": 3,
    "arnoldi_invariant_subspace_breakdown": 4,
    "arnoldi_triangular_factor_breakdown": 5,
}
_FGMRES_GPU_TREE_RESTART_FLAG_TRUE_RESIDUAL_REPLAYED = 1 << 0
_FGMRES_GPU_TREE_RESTART_FLAG_SOLVER_L2_PASSED = 1 << 1
_FGMRES_GPU_TREE_RESTART_FLAG_AUTHORITATIVE_LINF_PASSED = 1 << 2
_FGMRES_GPU_TREE_RESTART_FLAG_HAPPY_BREAKDOWN = 1 << 3
_FGMRES_GPU_TREE_RESTART_FLAG_INVARIANT_BREAKDOWN = 1 << 4
_FGMRES_GPU_TREE_RESTART_FLAG_STAGNATION_PLATEAU = 1 << 5
_FGMRES_GPU_TREE_RESTART_FLAG_TINY_UPDATE = 1 << 6
_FGMRES_GPU_TREE_RESTART_FLAG_DIVERGENCE = 1 << 7


class FgmresGpuTreeReferenceV2Error(ValueError):
    """Stable fail-closed error raised by the independent tree oracle."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeReductionV2:
    operation: GpuTreeOperation
    value_count: int
    stage_output_counts: tuple[int, ...]
    value: float


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeInitialReplayV2:
    solution_x: np.ndarray
    operator_value: np.ndarray
    true_residual: np.ndarray
    rhs_l2: FgmresGpuTreeReductionV2
    rhs_linf: FgmresGpuTreeReductionV2
    residual_l2: FgmresGpuTreeReductionV2
    residual_linf: FgmresGpuTreeReductionV2
    solver_tolerance_l2: float
    scaled_residual_linf: float
    solver_l2_passed: bool
    authoritative_linf_passed: bool
    terminal_status: InitialTerminalStatus
    termination_code: str
    operator_apply_count: int


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstArnoldiColumnReplayV2:
    """Immutable deterministic replay of FGMRES Arnoldi column zero."""

    basis_v0: np.ndarray
    jacobi_z0: np.ndarray
    operator_work: np.ndarray
    work_after_first: np.ndarray
    work_after_final: np.ndarray
    basis_v1: np.ndarray
    work_before_l2: FgmresGpuTreeReductionV2
    h00_first_dot: FgmresGpuTreeReductionV2
    after_first_l2: FgmresGpuTreeReductionV2
    dgks_second_pass: bool
    reorthogonalization_count: int
    h00_second_dot: FgmresGpuTreeReductionV2 | None
    h00_first_coefficient: float
    h00_second_coefficient: float
    h00: float
    h10_l2: FgmresGpuTreeReductionV2
    breakdown_threshold: float
    breakdown: bool
    invariant_breakdown: bool
    operator_apply_count: int


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2:
    """Immutable GPU-tree replay of column zero through Givens acceptance."""

    first_column: FgmresGpuTreeFirstArnoldiColumnReplayV2
    basis_v1: np.ndarray
    cycle_beta: float
    solver_tolerance_l2: float
    cycle_width: int
    breakdown_tau: float
    h_next_breakdown_threshold: float
    h_next_invariant_breakdown: bool
    unrotated_h00: float
    unrotated_h10: float
    rotation_norm: float
    rotation_scale: float
    rotation_breakdown_threshold: float
    rotation_breakdown: bool
    cosine0: float
    sine0: float
    rotated_h00: float
    rotated_h10: float
    g0: float
    g1: float
    estimated_residual_l2: float
    invariant_breakdown: bool
    candidate_reason_bits: int
    candidate_required: bool
    phase: FirstColumnGivensPhase
    effective_iterations: int
    arnoldi_step_count: int
    effective_arnoldi_dimension: int
    reorthogonalization_count: int
    operator_apply_count: int
    preconditioner_apply_count: int


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstColumnCandidatePreparationV2:
    """Immutable column-zero candidate state through ``VECTOR_ACCEPT``.

    ``None`` numerical fields are intentional.  They distinguish a fixed-
    schedule candidate gate no-op from an attempted triangular solve, and a
    triangular breakdown from a successfully prepared trial vector.
    """

    through_givens: FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2
    candidate_required: bool
    candidate_reason_bits: int
    backsubstitution_attempted: bool
    triangular_scale: float | None
    pivot_floor: float | None
    triangular_breakdown: bool
    invariant_breakdown: bool
    y0: float | None
    trial_x: np.ndarray | None
    solution_update_l2: FgmresGpuTreeReductionV2 | None
    candidate_vector_valid: bool
    effective_iterations: int
    arnoldi_step_count: int
    effective_arnoldi_dimension: int
    reorthogonalization_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    checkpoint_decision_included: bool
    checkpoint_commit_included: bool


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstColumnCandidateResidualReplayV2:
    """Immutable candidate replay through true-residual L2/Linf metrics.

    ``None`` candidate arrays and reductions identify the two fixed-schedule
    claim-only paths: no candidate was requested, or the preceding triangular
    solve broke down.  A valid replay preserves the committed solution state,
    keeps the prepared trial vector in the nested preparation result, and
    exposes only the candidate operator/residual scratch and the two GPU-tree
    residual metrics.  Checkpoint decision and commit semantics are outside
    this bounded oracle.
    """

    candidate_preparation: FgmresGpuTreeFirstColumnCandidatePreparationV2
    candidate_required: bool
    candidate_reason_bits: int
    triangular_breakdown: bool
    invariant_breakdown: bool
    phase: FirstColumnGivensPhase
    candidate_replay_attempted: bool
    candidate_replay_valid: bool
    candidate_operator_value: np.ndarray | None
    candidate_true_residual: np.ndarray | None
    candidate_l2: FgmresGpuTreeReductionV2 | None
    candidate_linf: FgmresGpuTreeReductionV2 | None
    solution_update_l2: FgmresGpuTreeReductionV2 | None
    trial_x_l2: FgmresGpuTreeReductionV2 | None
    committed_x_l2: FgmresGpuTreeReductionV2 | None
    reduction_valid_mask: int
    effective_iterations: int
    arnoldi_step_count: int
    effective_arnoldi_dimension: int
    reorthogonalization_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    checkpoint_decision_included: bool
    checkpoint_commit_included: bool
    solution_and_true_residual_committed: bool

    @property
    def candidate_operator(self) -> np.ndarray | None:
        """Return the candidate ``A*trial_x`` scratch array, if replayed."""

        return self.candidate_operator_value

    @property
    def candidate_residual(self) -> np.ndarray | None:
        """Return the candidate ``b-A*trial_x`` scratch array, if replayed."""

        return self.candidate_true_residual


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2:
    """Immutable candidate replay through trial/committed solution L2 metrics.

    Scale metrics are needed only for a valid planned-cycle-end candidate that
    fails the dual convergence gate without invariant breakdown or divergence.
    ``None`` policy decisions identify an earlier short-circuit.  The nested
    residual replay remains the sole owner of candidate numeric scratch; this
    result adds only the two deterministic GPU-tree reductions and their mask
    transition.  It deliberately does not decide, commit, or form ``x_scale``.
    """

    candidate_residual: FgmresGpuTreeFirstColumnCandidateResidualReplayV2
    candidate_required: bool
    candidate_reason_bits: int
    triangular_breakdown: bool
    invariant_breakdown: bool
    phase: FirstColumnGivensPhase
    candidate_replay_attempted: bool
    candidate_replay_valid: bool
    planned_cycle_end: bool
    dual_gate_evaluated: bool
    scaled_candidate_residual_linf: float | None
    solver_l2_passed: bool | None
    authoritative_linf_passed: bool | None
    dual_gate_passed: bool | None
    divergence_evaluated: bool
    divergence_threshold_l2: float | None
    divergence_detected: bool | None
    candidate_scale_required: bool
    candidate_scale_metrics_attempted: bool
    candidate_scale_metrics_valid: bool
    solution_update_l2: FgmresGpuTreeReductionV2 | None
    candidate_l2: FgmresGpuTreeReductionV2 | None
    candidate_linf: FgmresGpuTreeReductionV2 | None
    trial_x_l2: FgmresGpuTreeReductionV2 | None
    committed_x_l2: FgmresGpuTreeReductionV2 | None
    x_scale_l2: None
    prior_reduction_valid_mask: int
    trial_x_reduction_valid_mask: int | None
    reduction_valid_mask: int
    effective_iterations: int
    arnoldi_step_count: int
    effective_arnoldi_dimension: int
    reorthogonalization_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    checkpoint_decision_included: bool
    checkpoint_commit_included: bool
    solution_and_true_residual_committed: bool

    @property
    def scale_metrics_required(self) -> bool:
        """Return the exact device predicate for the two scale reductions."""

        return self.candidate_scale_required


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2:
    """One finalized first-restart record produced by the transaction."""

    restart_index: int
    start_iteration: int
    end_iteration: int
    arnoldi_step_count: int
    reorthogonalization_count: int
    termination_hint: str
    termination_hint_code: int
    flags: int
    estimated_residual_l2: float
    true_residual_l2: float
    true_residual_linf: float
    scaled_true_residual: float
    solution_update_l2: float


@dataclass(frozen=True, slots=True)
class FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2:
    """Immutable DECIDE/COMMIT/FINALIZE replay for column zero.

    The result exposes every transaction boundary explicitly.  DECIDE and
    COMMIT preserve the predecessor reduction mask; FINALIZE alone clears it
    and publishes any restart/header outcome.  Committed arrays are replaced
    only when ``commit_required`` is true.
    """

    candidate_scale_metrics: FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2
    start_reduction_valid_mask: int
    decide_reduction_valid_mask: int
    commit_reduction_valid_mask: int
    finalize_reduction_valid_mask: int
    active_during_decide: bool
    active_during_commit: bool
    active_after_finalize: bool
    decision: str
    candidate_required: bool
    candidate_reason_bits: int
    triangular_breakdown: bool
    invariant_breakdown: bool
    planned_cycle_end: bool
    dual_gate_evaluated: bool
    scaled_candidate_residual_linf: float | None
    solver_l2_passed: bool | None
    authoritative_linf_passed: bool | None
    dual_gate_passed: bool | None
    divergence_evaluated: bool
    divergence_threshold_l2: float | None
    divergence_detected: bool | None
    stagnation_evaluated: bool
    stagnation_plateau: bool | None
    tiny_update: bool | None
    x_scale_l2: float | None
    commit_required: bool
    continuation_required: bool
    continuation_kind: str | None
    row_appended: bool
    restart_record: FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2 | None
    pending_terminal_status: str
    pending_terminal_status_code: int
    pending_termination_code: str
    pending_termination_code_value: int
    pending_restart_hint: str
    pending_restart_hint_code: int
    pending_restart_flags: int
    terminal_status: str
    terminal_status_code: int
    termination_code: str
    termination_code_value: int
    phase_after_finalize: str
    final_guard_handoff_required: bool
    column_index_after_finalize: int
    previous_stagnation_checkpoint_count: int
    stagnation_checkpoint_count: int
    previous_false_convergence_count: int
    false_convergence_count: int
    previous_happy_breakdown_count: int
    happy_breakdown_count: int
    previous_checkpoint_l2_before: float
    previous_checkpoint_l2: float
    previous_solution_scale_l2: float
    solution_scale_l2: float
    final_residual_l2: float
    final_residual_linf: float
    final_scaled_residual: float
    solution_x: np.ndarray
    true_residual: np.ndarray
    effective_iterations: int
    arnoldi_step_count: int
    effective_arnoldi_dimension: int
    reorthogonalization_count: int
    operator_apply_count: int
    preconditioner_apply_count: int
    checkpoint_decision_included: bool
    checkpoint_commit_included: bool
    checkpoint_finalize_included: bool
    solution_and_true_residual_committed: bool


@dataclass(frozen=True, slots=True)
class _LassqPair:
    scale: float
    ssq: float


def fgmres_gpu_tree_l2_v2(values: Any) -> FgmresGpuTreeReductionV2:
    """Return the exact scale-first LASSQ tree result and stage counts."""

    vector = _finite_vector(values, "/values")
    pairs = _lassq_stage(vector)
    stage_counts = [len(pairs)]
    while len(pairs) > 1:
        pairs = _lassq_combine_stage(pairs)
        stage_counts.append(len(pairs))
    pair = pairs[0]
    value = pair.scale * math.sqrt(pair.ssq)
    if not math.isfinite(value):
        _fail(
            "fgmres_gpu_tree_l2_overflow",
            "/values",
            "The represented FP64 L2 norm is nonfinite.",
        )
    return FgmresGpuTreeReductionV2(
        operation="lassq_l2",
        value_count=int(vector.size),
        stage_output_counts=tuple(stage_counts),
        value=_exact_zero(value),
    )


def fgmres_gpu_tree_linf_v2(values: Any) -> FgmresGpuTreeReductionV2:
    """Return the exact deterministic absolute-maximum tree result."""

    vector = _finite_vector(values, "/values")
    partials = _max_stage(vector)
    stage_counts = [len(partials)]
    while len(partials) > 1:
        partials = _max_combine_stage(partials)
        stage_counts.append(len(partials))
    return FgmresGpuTreeReductionV2(
        operation="abs_max_linf",
        value_count=int(vector.size),
        stage_output_counts=tuple(stage_counts),
        value=_exact_zero(partials[0]),
    )


def fgmres_gpu_tree_dot_v2(left: Any, right: Any) -> FgmresGpuTreeReductionV2:
    """Return a strict FP64 dot using the exact GPU product/sum tree.

    The first stage forms at most 512 products per 256-thread block.  Later
    stages reduce only the prior stage's partial sums.  Every multiplication
    and addition is checked before it can become an accepted partial; no
    BLAS, NumPy dot, FMA, or order-changing aggregate is used.
    """

    lhs = _finite_vector(left, "/left")
    rhs = _finite_vector(right, "/right")
    if lhs.shape != rhs.shape:
        _fail("fgmres_gpu_tree_dot_shape_mismatch", "/right")
    partials = _dot_product_stage(lhs, rhs)
    stage_counts = [len(partials)]
    while len(partials) > 1:
        partials = _sum_combine_stage(partials, "/reduction/dot/combine")
        stage_counts.append(len(partials))
    return FgmresGpuTreeReductionV2(
        operation="dot_fp64",
        value_count=int(lhs.size),
        stage_output_counts=tuple(stage_counts),
        value=_exact_zero(partials[0]),
    )


def replay_fgmres_gpu_tree_first_arnoldi_column_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    basis_v0: Any,
    jacobi_inverse: Any,
) -> FgmresGpuTreeFirstArnoldiColumnReplayV2:
    """Replay the first positive-Jacobi FGMRES Arnoldi column.

    This is an intentionally small numerical oracle, not a call into the CPU
    FGMRES solver.  It mirrors the fixed device schedule: ``z0=D^-1*v0``,
    sorted-CSR ``A*z0``, first-pass MGS, a strict DGKS decision, an optional
    second pass, and the scale-relative happy-breakdown test.
    """

    v0 = _finite_vector(basis_v0, "/basis_v0")
    inverse = _finite_vector(jacobi_inverse, "/jacobi_inverse")
    if v0.shape != inverse.shape:
        _fail("fgmres_gpu_tree_jacobi_shape_mismatch", "/jacobi_inverse")
    if np.any(inverse <= 0.0):
        _fail(
            "fgmres_gpu_tree_jacobi_inverse_not_positive",
            "/jacobi_inverse",
        )
    checked_row_ptr, checked_columns, checked_values = _validated_csr(
        row_ptr,
        column_indices,
        values,
        int(v0.size),
    )

    z0 = _checked_elementwise_product(
        inverse,
        v0,
        code="fgmres_gpu_tree_jacobi_arithmetic_overflow",
        path="/jacobi_z0",
    )
    operator_work = _sequential_csr_matvec(
        checked_row_ptr,
        checked_columns,
        checked_values,
        z0,
    )
    work_before_l2 = fgmres_gpu_tree_l2_v2(operator_work)
    h00_first = fgmres_gpu_tree_dot_v2(v0, operator_work)
    work_after_first = _checked_mgs_subtract(
        operator_work,
        v0,
        h00_first.value,
        path="/work_after_first",
    )
    after_first_l2 = fgmres_gpu_tree_l2_v2(work_after_first)

    eta_product = 0.717 * work_before_l2.value
    if not math.isfinite(eta_product):
        _fail(
            "fgmres_gpu_tree_dgks_arithmetic_overflow",
            "/dgks_threshold",
        )
    dgks_second_pass = after_first_l2.value < eta_product
    h00_second: FgmresGpuTreeReductionV2 | None = None
    h00 = h00_first.value
    if dgks_second_pass:
        h00_second = fgmres_gpu_tree_dot_v2(v0, work_after_first)
        h00 = h00_first.value + h00_second.value
        if not math.isfinite(h00):
            _fail(
                "fgmres_gpu_tree_hessenberg_arithmetic_overflow",
                "/h00",
            )
        work_after_final = _checked_mgs_subtract(
            work_after_first,
            v0,
            h00_second.value,
            path="/work_after_second",
        )
    else:
        work_after_final = work_after_first.copy()

    h10_l2 = fgmres_gpu_tree_l2_v2(work_after_final)
    breakdown_threshold = 64.0 * float(np.finfo(np.float64).eps) * work_before_l2.value
    if not math.isfinite(breakdown_threshold):
        _fail(
            "fgmres_gpu_tree_breakdown_threshold_overflow",
            "/breakdown_threshold",
        )
    breakdown = h10_l2.value <= breakdown_threshold
    if breakdown:
        basis_v1 = np.zeros_like(work_after_final)
    else:
        basis_v1 = _checked_normalize(
            work_after_final,
            h10_l2.value,
            path="/basis_v1",
        )

    return FgmresGpuTreeFirstArnoldiColumnReplayV2(
        basis_v0=_immutable_f64(v0),
        jacobi_z0=_immutable_f64(z0),
        operator_work=_immutable_f64(operator_work),
        work_after_first=_immutable_f64(work_after_first),
        work_after_final=_immutable_f64(work_after_final),
        basis_v1=_immutable_f64(basis_v1),
        work_before_l2=work_before_l2,
        h00_first_dot=h00_first,
        after_first_l2=after_first_l2,
        dgks_second_pass=dgks_second_pass,
        reorthogonalization_count=int(dgks_second_pass),
        h00_second_dot=h00_second,
        h00_first_coefficient=_exact_zero(h00_first.value),
        h00_second_coefficient=_exact_zero(
            0.0 if h00_second is None else h00_second.value
        ),
        h00=_exact_zero(h00),
        h10_l2=h10_l2,
        breakdown_threshold=_exact_zero(breakdown_threshold),
        breakdown=breakdown,
        invariant_breakdown=breakdown,
        operator_apply_count=1,
    )


def replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    basis_v0: Any,
    jacobi_inverse: Any,
    cycle_beta: float,
    solver_tolerance_l2: float,
    cycle_width: int,
) -> FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2:
    """Replay the first Arnoldi column through normalization and Givens.

    The legacy first-column replay remains the numerical source for the exact
    GPU-tree dot, optional DGKS pass, and H-next LASSQ results.  This extension
    independently applies the accepted CPU ordering to those values:
    H-next invariant test, V1 normalization/no-op, then the column-zero Givens
    rotation and successful recurrence-counter acceptance.
    """

    beta = _positive_float64(
        cycle_beta,
        "/cycle_beta",
        type_code="fgmres_gpu_tree_cycle_beta_type_invalid",
        value_code="fgmres_gpu_tree_cycle_beta_invalid",
    )
    tolerance = _nonnegative_float64(
        solver_tolerance_l2,
        "/solver_tolerance_l2",
    )
    if (
        type(cycle_width) is not int
        or not 1 <= cycle_width <= _FGMRES_GPU_TREE_MAX_RESTART_DIMENSION
    ):
        _fail(
            "fgmres_gpu_tree_cycle_width_invalid",
            "/cycle_width",
        )

    first_column = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=jacobi_inverse,
    )

    tau = _FGMRES_GPU_TREE_BREAKDOWN_TAU
    h_next_threshold = _checked_product(
        tau,
        first_column.work_before_l2.value,
        code="fgmres_gpu_tree_breakdown_threshold_overflow",
        path="/h_next_breakdown_threshold",
    )
    h10 = first_column.h10_l2.value
    h_next_invariant = h10 <= h_next_threshold
    if h_next_invariant:
        basis_v1 = np.zeros_like(first_column.work_after_final)
    else:
        basis_v1 = _checked_normalize(
            first_column.work_after_final,
            h10,
            path="/basis_v1",
        )

    h00 = first_column.h00
    rotation_norm = math.hypot(h00, h10)
    rotation_scale = max(abs(h00), abs(h10))
    rotation_threshold = _checked_product(
        tau,
        rotation_scale,
        code="fgmres_gpu_tree_givens_threshold_overflow",
        path="/rotation_breakdown_threshold",
    )
    rotation_breakdown = (
        not math.isfinite(rotation_norm) or rotation_norm <= rotation_threshold
    )
    if rotation_breakdown:
        cosine0 = 1.0
        sine0 = 0.0
        rotated_h00 = h00
        rotated_h10 = h10
    else:
        cosine0 = h00 / rotation_norm
        sine0 = h10 / rotation_norm
        rotated_h00 = rotation_norm
        rotated_h10 = 0.0
        if not math.isfinite(cosine0) or not math.isfinite(sine0):
            _fail(
                "fgmres_gpu_tree_givens_arithmetic_overflow",
                "/givens",
            )

    g0 = _checked_product(
        cosine0,
        beta,
        code="fgmres_gpu_tree_givens_arithmetic_overflow",
        path="/g/0",
    )
    g1 = _checked_product(
        -sine0,
        beta,
        code="fgmres_gpu_tree_givens_arithmetic_overflow",
        path="/g/1",
    )
    estimated_residual = abs(g1)
    if not math.isfinite(estimated_residual):
        _fail(
            "fgmres_gpu_tree_givens_residual_nonfinite",
            "/estimated_residual_l2",
        )

    invariant_breakdown = h_next_invariant or rotation_breakdown
    candidate_reason_bits = 0
    if estimated_residual <= tolerance:
        candidate_reason_bits |= 1 << 0
    if invariant_breakdown:
        candidate_reason_bits |= 1 << 1
    if cycle_width == 1:
        candidate_reason_bits |= 1 << 2
    candidate_required = candidate_reason_bits != 0
    phase: FirstColumnGivensPhase = "candidate" if candidate_required else "arnoldi"

    return FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2(
        first_column=first_column,
        basis_v1=_immutable_f64(basis_v1),
        cycle_beta=_exact_zero(beta),
        solver_tolerance_l2=_exact_zero(tolerance),
        cycle_width=cycle_width,
        breakdown_tau=tau,
        h_next_breakdown_threshold=_exact_zero(h_next_threshold),
        h_next_invariant_breakdown=h_next_invariant,
        unrotated_h00=_exact_zero(h00),
        unrotated_h10=_exact_zero(h10),
        rotation_norm=_exact_zero(rotation_norm),
        rotation_scale=_exact_zero(rotation_scale),
        rotation_breakdown_threshold=_exact_zero(rotation_threshold),
        rotation_breakdown=rotation_breakdown,
        cosine0=_exact_zero(cosine0),
        sine0=_exact_zero(sine0),
        rotated_h00=_exact_zero(rotated_h00),
        rotated_h10=_exact_zero(rotated_h10),
        g0=_exact_zero(g0),
        g1=_exact_zero(g1),
        estimated_residual_l2=_exact_zero(estimated_residual),
        invariant_breakdown=invariant_breakdown,
        candidate_reason_bits=candidate_reason_bits,
        candidate_required=candidate_required,
        phase=phase,
        effective_iterations=1,
        arnoldi_step_count=1,
        effective_arnoldi_dimension=1,
        reorthogonalization_count=first_column.reorthogonalization_count,
        operator_apply_count=2,
        preconditioner_apply_count=1,
    )


def prepare_fgmres_gpu_tree_first_column_candidate_v2(
    *,
    through_givens: FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2,
    committed_solution: Any,
) -> FgmresGpuTreeFirstColumnCandidatePreparationV2:
    """Prepare the column-zero candidate without checkpoint semantics.

    The arithmetic order is deliberately narrower than a general triangular
    solve: for column zero, ``scale=abs(H00)``, the tail is exact ``+0``,
    ``y0=(g0-0)/H00``, and every trial coordinate forms a checked product then
    a checked sum with FP contraction excluded by construction.  A false
    candidate gate does not inspect ``committed_solution`` or any candidate
    numerical input, matching the fixed device schedule's gated no-op.
    """

    if type(through_givens) is not FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2:
        _fail(
            "fgmres_gpu_tree_candidate_source_type_invalid",
            "/through_givens",
        )
    if (
        type(through_givens.candidate_required) is not bool
        or type(through_givens.candidate_reason_bits) is not int
        or not 0 <= through_givens.candidate_reason_bits <= 0b111
        or through_givens.candidate_required
        != (through_givens.candidate_reason_bits != 0)
    ):
        _fail(
            "fgmres_gpu_tree_candidate_gate_invalid",
            "/through_givens/candidate",
        )

    common = {
        "through_givens": through_givens,
        "candidate_required": through_givens.candidate_required,
        "candidate_reason_bits": through_givens.candidate_reason_bits,
        "effective_iterations": through_givens.effective_iterations,
        "arnoldi_step_count": through_givens.arnoldi_step_count,
        "effective_arnoldi_dimension": through_givens.effective_arnoldi_dimension,
        "reorthogonalization_count": through_givens.reorthogonalization_count,
        "operator_apply_count": through_givens.operator_apply_count,
        "preconditioner_apply_count": through_givens.preconditioner_apply_count,
        "checkpoint_decision_included": False,
        "checkpoint_commit_included": False,
    }
    if not through_givens.candidate_required:
        return FgmresGpuTreeFirstColumnCandidatePreparationV2(
            **common,
            backsubstitution_attempted=False,
            triangular_scale=None,
            pivot_floor=None,
            triangular_breakdown=False,
            invariant_breakdown=through_givens.invariant_breakdown,
            y0=None,
            trial_x=None,
            solution_update_l2=None,
            candidate_vector_valid=False,
        )

    pivot = float(through_givens.rotated_h00)
    if not math.isfinite(pivot):
        _fail(
            "fgmres_gpu_tree_triangular_input_nonfinite",
            "/triangular/h00",
        )
    triangular_scale = abs(pivot)
    pivot_floor = _checked_product(
        through_givens.breakdown_tau,
        triangular_scale,
        code="fgmres_gpu_tree_triangular_threshold_overflow",
        path="/triangular/pivot_floor",
    )
    triangular_breakdown = triangular_scale == 0.0 or abs(pivot) <= pivot_floor
    if triangular_breakdown:
        return FgmresGpuTreeFirstColumnCandidatePreparationV2(
            **common,
            backsubstitution_attempted=True,
            triangular_scale=_exact_zero(triangular_scale),
            pivot_floor=_exact_zero(pivot_floor),
            triangular_breakdown=True,
            invariant_breakdown=True,
            y0=None,
            trial_x=None,
            solution_update_l2=None,
            candidate_vector_valid=False,
        )

    g0 = float(through_givens.g0)
    if not math.isfinite(g0):
        _fail(
            "fgmres_gpu_tree_triangular_input_nonfinite",
            "/triangular/g0",
        )
    numerator = g0 - 0.0
    y0 = numerator / pivot
    if not math.isfinite(numerator) or not math.isfinite(y0):
        _fail(
            "fgmres_gpu_tree_triangular_arithmetic_overflow",
            "/triangular/y0",
        )
    y0 = _exact_zero(y0)

    committed = _finite_vector(committed_solution, "/committed_solution")
    z0 = _finite_vector(
        through_givens.first_column.jacobi_z0,
        "/through_givens/first_column/jacobi_z0",
    )
    if committed.shape != z0.shape:
        _fail(
            "fgmres_gpu_tree_candidate_solution_shape_mismatch",
            "/committed_solution",
        )

    trial = np.empty_like(committed)
    update = np.empty_like(committed)
    for index in range(int(committed.size)):
        projection = _checked_product(
            y0,
            float(z0[index]),
            code="fgmres_gpu_tree_trial_arithmetic_overflow",
            path=f"/trial_x/{index}/product",
        )
        value = _checked_sum(
            float(committed[index]),
            projection,
            code="fgmres_gpu_tree_trial_arithmetic_overflow",
            path=f"/trial_x/{index}/sum",
        )
        trial[index] = _exact_zero(value)
        difference = value - float(committed[index])
        if not math.isfinite(difference):
            _fail(
                "fgmres_gpu_tree_update_arithmetic_overflow",
                f"/solution_update/{index}",
            )
        update[index] = _exact_zero(difference)
    update_l2 = fgmres_gpu_tree_l2_v2(update)

    return FgmresGpuTreeFirstColumnCandidatePreparationV2(
        **common,
        backsubstitution_attempted=True,
        triangular_scale=_exact_zero(triangular_scale),
        pivot_floor=_exact_zero(pivot_floor),
        triangular_breakdown=False,
        invariant_breakdown=through_givens.invariant_breakdown,
        y0=y0,
        trial_x=_immutable_f64(trial),
        solution_update_l2=update_l2,
        candidate_vector_valid=True,
    )


def prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
    *,
    candidate_preparation: FgmresGpuTreeFirstColumnCandidatePreparationV2,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    reduced_load: Any,
) -> FgmresGpuTreeFirstColumnCandidateResidualReplayV2:
    """Replay a prepared candidate through true-residual L2/Linf metrics.

    The candidate-false and triangular-breakdown branches deliberately return
    before inspecting the CSR operator or reduced load.  This mirrors the
    fixed device schedule, where those submissions claim their epochs without
    touching numeric data or reduction scratch.
    """

    if (
        type(candidate_preparation)
        is not FgmresGpuTreeFirstColumnCandidatePreparationV2
    ):
        _fail(
            "fgmres_gpu_tree_candidate_residual_source_type_invalid",
            "/candidate_preparation",
        )
    preparation = candidate_preparation
    through = preparation.through_givens
    if type(through) is not FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2:
        _fail(
            "fgmres_gpu_tree_candidate_residual_source_state_invalid",
            "/candidate_preparation/through_givens",
        )
    candidate_required = preparation.candidate_required
    triangular_breakdown = preparation.triangular_breakdown
    active_candidate = candidate_required and not triangular_breakdown
    expected_phase: FirstColumnGivensPhase = (
        "candidate" if candidate_required else "arnoldi"
    )
    preparation_state_valid = (
        type(candidate_required) is bool
        and type(preparation.candidate_reason_bits) is int
        and 0 <= preparation.candidate_reason_bits <= 0b111
        and candidate_required == (preparation.candidate_reason_bits != 0)
        and type(triangular_breakdown) is bool
        and type(preparation.invariant_breakdown) is bool
        and type(preparation.candidate_vector_valid) is bool
        and through.candidate_required == candidate_required
        and through.candidate_reason_bits == preparation.candidate_reason_bits
        and through.phase == expected_phase
        and preparation.candidate_vector_valid == active_candidate
        and all(
            type(value) is int
            for value in (
                preparation.effective_iterations,
                preparation.arnoldi_step_count,
                preparation.effective_arnoldi_dimension,
                preparation.reorthogonalization_count,
                preparation.operator_apply_count,
                preparation.preconditioner_apply_count,
            )
        )
        and preparation.effective_iterations == 1
        and preparation.arnoldi_step_count == 1
        and preparation.effective_arnoldi_dimension == 1
        and preparation.reorthogonalization_count in (0, 1)
        and preparation.operator_apply_count == 2
        and preparation.preconditioner_apply_count == 1
        and type(preparation.checkpoint_decision_included) is bool
        and type(preparation.checkpoint_commit_included) is bool
        and preparation.checkpoint_decision_included is False
        and preparation.checkpoint_commit_included is False
        and (
            (active_candidate and preparation.trial_x is not None)
            or (not active_candidate and preparation.trial_x is None)
        )
        and (
            (
                active_candidate
                and type(preparation.solution_update_l2) is FgmresGpuTreeReductionV2
            )
            or (not active_candidate and preparation.solution_update_l2 is None)
        )
        and (not triangular_breakdown or preparation.invariant_breakdown)
    )
    if not preparation_state_valid:
        _fail(
            "fgmres_gpu_tree_candidate_residual_source_state_invalid",
            "/candidate_preparation",
        )

    common = {
        "candidate_preparation": preparation,
        "candidate_required": candidate_required,
        "candidate_reason_bits": preparation.candidate_reason_bits,
        "triangular_breakdown": triangular_breakdown,
        "invariant_breakdown": preparation.invariant_breakdown,
        "phase": expected_phase,
        "solution_update_l2": preparation.solution_update_l2,
        "trial_x_l2": None,
        "committed_x_l2": None,
        "effective_iterations": preparation.effective_iterations,
        "arnoldi_step_count": preparation.arnoldi_step_count,
        "effective_arnoldi_dimension": preparation.effective_arnoldi_dimension,
        "reorthogonalization_count": preparation.reorthogonalization_count,
        "preconditioner_apply_count": preparation.preconditioner_apply_count,
        "checkpoint_decision_included": False,
        "checkpoint_commit_included": False,
        "solution_and_true_residual_committed": False,
    }
    if not active_candidate:
        return FgmresGpuTreeFirstColumnCandidateResidualReplayV2(
            **common,
            candidate_replay_attempted=False,
            candidate_replay_valid=False,
            candidate_operator_value=None,
            candidate_true_residual=None,
            candidate_l2=None,
            candidate_linf=None,
            reduction_valid_mask=0,
            operator_apply_count=preparation.operator_apply_count,
        )

    trial = _finite_vector(preparation.trial_x, "/candidate_preparation/trial_x")
    checked_rows, checked_columns, checked_values = _validated_csr(
        row_ptr,
        column_indices,
        values,
        int(trial.size),
    )
    candidate_operator = _sequential_csr_matvec(
        checked_rows,
        checked_columns,
        checked_values,
        trial,
    )
    load = _finite_vector(reduced_load, "/reduced_load")
    if load.shape != candidate_operator.shape:
        _fail(
            "fgmres_gpu_tree_candidate_residual_shape_mismatch",
            "/reduced_load",
        )
    candidate_residual = np.empty_like(load)
    for index in range(int(load.size)):
        residual = float(load[index]) - float(candidate_operator[index])
        if not math.isfinite(residual):
            _fail(
                "fgmres_gpu_tree_candidate_residual_arithmetic_overflow",
                f"/candidate_residual/{index}",
            )
        candidate_residual[index] = _exact_zero(residual)
    candidate_l2 = fgmres_gpu_tree_l2_v2(candidate_residual)
    candidate_linf = fgmres_gpu_tree_linf_v2(candidate_residual)

    return FgmresGpuTreeFirstColumnCandidateResidualReplayV2(
        **common,
        candidate_replay_attempted=True,
        candidate_replay_valid=True,
        candidate_operator_value=_immutable_f64(candidate_operator),
        candidate_true_residual=_immutable_f64(candidate_residual),
        candidate_l2=candidate_l2,
        candidate_linf=candidate_linf,
        reduction_valid_mask=(1 << 8) | (1 << 9) | (1 << 10),
        operator_apply_count=preparation.operator_apply_count + 1,
    )


def prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
    *,
    candidate_residual: FgmresGpuTreeFirstColumnCandidateResidualReplayV2,
    solver_tolerance_l2: float,
    authoritative_tolerance: float,
    rhs_linf: float,
    initial_residual_l2: float,
    divergence_factor: float,
    committed_solution: Any,
) -> FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2:
    """Replay the gated trial/committed solution L2 scale metrics.

    The short-circuit order is part of the oracle contract.  Inactive,
    triangular-breakdown, and non-cycle candidates do not inspect policy or
    committed-solution numeric inputs.  An active planned-cycle candidate
    evaluates the dual gate first, then invariant breakdown, then divergence.
    Only a surviving false-convergence continuation inspects the two solution
    vectors and reduces them in trial-then-committed order.
    """

    if (
        type(candidate_residual)
        is not FgmresGpuTreeFirstColumnCandidateResidualReplayV2
    ):
        _fail(
            "fgmres_gpu_tree_candidate_scale_metrics_source_type_invalid",
            "/candidate_residual",
        )
    residual = candidate_residual
    if not _candidate_scale_metrics_source_state_valid(residual):
        _fail(
            "fgmres_gpu_tree_candidate_scale_metrics_source_state_invalid",
            "/candidate_residual",
        )

    planned_cycle_end = bool(residual.candidate_reason_bits & (1 << 2))
    prior_mask = residual.reduction_valid_mask
    common = {
        "candidate_residual": residual,
        "candidate_required": residual.candidate_required,
        "candidate_reason_bits": residual.candidate_reason_bits,
        "triangular_breakdown": residual.triangular_breakdown,
        "invariant_breakdown": residual.invariant_breakdown,
        "phase": residual.phase,
        "candidate_replay_attempted": residual.candidate_replay_attempted,
        "candidate_replay_valid": residual.candidate_replay_valid,
        "planned_cycle_end": planned_cycle_end,
        "solution_update_l2": residual.solution_update_l2,
        "candidate_l2": residual.candidate_l2,
        "candidate_linf": residual.candidate_linf,
        "x_scale_l2": None,
        "prior_reduction_valid_mask": prior_mask,
        "effective_iterations": residual.effective_iterations,
        "arnoldi_step_count": residual.arnoldi_step_count,
        "effective_arnoldi_dimension": residual.effective_arnoldi_dimension,
        "reorthogonalization_count": residual.reorthogonalization_count,
        "operator_apply_count": residual.operator_apply_count,
        "preconditioner_apply_count": residual.preconditioner_apply_count,
        "checkpoint_decision_included": False,
        "checkpoint_commit_included": False,
        "solution_and_true_residual_committed": False,
    }

    def finish(
        *,
        dual_gate_evaluated: bool = False,
        scaled_candidate_residual_linf: float | None = None,
        solver_l2_passed: bool | None = None,
        authoritative_linf_passed: bool | None = None,
        dual_gate_passed: bool | None = None,
        divergence_evaluated: bool = False,
        divergence_threshold_l2: float | None = None,
        divergence_detected: bool | None = None,
        trial_x_l2: FgmresGpuTreeReductionV2 | None = None,
        committed_x_l2: FgmresGpuTreeReductionV2 | None = None,
        trial_x_reduction_valid_mask: int | None = None,
        reduction_valid_mask: int = prior_mask,
    ) -> FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2:
        scale_required = trial_x_l2 is not None and committed_x_l2 is not None
        return FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2(
            **common,
            dual_gate_evaluated=dual_gate_evaluated,
            scaled_candidate_residual_linf=scaled_candidate_residual_linf,
            solver_l2_passed=solver_l2_passed,
            authoritative_linf_passed=authoritative_linf_passed,
            dual_gate_passed=dual_gate_passed,
            divergence_evaluated=divergence_evaluated,
            divergence_threshold_l2=divergence_threshold_l2,
            divergence_detected=divergence_detected,
            candidate_scale_required=scale_required,
            candidate_scale_metrics_attempted=scale_required,
            candidate_scale_metrics_valid=scale_required,
            trial_x_l2=trial_x_l2,
            committed_x_l2=committed_x_l2,
            trial_x_reduction_valid_mask=trial_x_reduction_valid_mask,
            reduction_valid_mask=reduction_valid_mask,
        )

    active_candidate = (
        residual.candidate_required
        and not residual.triangular_breakdown
        and residual.candidate_replay_valid
    )
    if not active_candidate or not planned_cycle_end:
        return finish()

    tolerance = _nonnegative_float64(
        solver_tolerance_l2,
        "/solver_tolerance_l2",
    )
    authoritative = _nonnegative_float64(
        authoritative_tolerance,
        "/authoritative_tolerance",
    )
    rhs_maximum = _nonnegative_float64(rhs_linf, "/rhs_linf")
    assert residual.candidate_l2 is not None
    assert residual.candidate_linf is not None
    scaled_linf = residual.candidate_linf.value / max(1.0, rhs_maximum)
    if not math.isfinite(scaled_linf):
        _fail(
            "fgmres_gpu_tree_candidate_scale_gate_arithmetic_overflow",
            "/scaled_candidate_residual_linf",
        )
    scaled_linf = _exact_zero(scaled_linf)
    solver_passed = residual.candidate_l2.value <= tolerance
    authoritative_passed = scaled_linf <= authoritative
    dual_passed = solver_passed and authoritative_passed
    gate = {
        "dual_gate_evaluated": True,
        "scaled_candidate_residual_linf": scaled_linf,
        "solver_l2_passed": solver_passed,
        "authoritative_linf_passed": authoritative_passed,
        "dual_gate_passed": dual_passed,
    }
    if dual_passed:
        return finish(**gate)
    if residual.invariant_breakdown:
        return finish(**gate)

    initial_l2 = _nonnegative_float64(
        initial_residual_l2,
        "/initial_residual_l2",
    )
    divergence = _candidate_scale_divergence_factor(divergence_factor)
    divergence_threshold = divergence * max(
        initial_l2,
        _FGMRES_GPU_TREE_DBL_MIN_NORMAL,
    )
    if math.isnan(divergence_threshold) or divergence_threshold < 0.0:
        _fail(
            "fgmres_gpu_tree_candidate_scale_divergence_threshold_invalid",
            "/divergence_threshold_l2",
        )
    divergence_threshold = _exact_zero(divergence_threshold)
    diverged = residual.candidate_l2.value > divergence_threshold
    divergence_state = {
        **gate,
        "divergence_evaluated": True,
        "divergence_threshold_l2": divergence_threshold,
        "divergence_detected": diverged,
    }
    if diverged:
        return finish(**divergence_state)

    trial = _finite_vector(
        residual.candidate_preparation.trial_x,
        "/candidate_residual/candidate_preparation/trial_x",
    )
    trial_l2 = fgmres_gpu_tree_l2_v2(trial)
    trial_mask = prior_mask | _FGMRES_GPU_TREE_TRIAL_X_L2_BIT

    committed = _finite_vector(committed_solution, "/committed_solution")
    if committed.shape != trial.shape:
        _fail(
            "fgmres_gpu_tree_candidate_scale_solution_shape_mismatch",
            "/committed_solution",
        )
    committed_l2 = fgmres_gpu_tree_l2_v2(committed)
    final_mask = trial_mask | _FGMRES_GPU_TREE_COMMITTED_X_L2_BIT
    return finish(
        **divergence_state,
        trial_x_l2=trial_l2,
        committed_x_l2=committed_l2,
        trial_x_reduction_valid_mask=trial_mask,
        reduction_valid_mask=final_mask,
    )


def prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2(
    *,
    candidate_scale_metrics: FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2,
    solver_tolerance_l2: float,
    authoritative_tolerance: float,
    rhs_linf: float,
    initial_residual_l2: float,
    divergence_factor: float,
    committed_solution: Any,
    committed_true_residual: Any,
    previous_checkpoint_l2: float,
    previous_solution_scale_l2: float,
    previous_stagnation_checkpoint_count: int,
    previous_false_convergence_count: int,
    previous_happy_breakdown_count: int,
    stagnation_relative_tolerance: float,
    stagnation_checkpoint_limit: int,
    max_iterations: int,
    restart_dimension: int,
) -> FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2:
    """Replay first-column CHECKPOINT_DECIDE/COMMIT/FINALIZE.

    This is a transaction oracle, not a CPU-solver call.  It preserves the
    predecessor mask through DECIDE and COMMIT, mutates committed arrays only
    under the accepted commit predicate, and exposes row/header state only at
    FINALIZE.  All priority comparisons use the device FP64 operands.
    """

    if (
        type(candidate_scale_metrics)
        is not FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2
    ):
        _fail(
            "fgmres_gpu_tree_checkpoint_transaction_source_type_invalid",
            "/candidate_scale_metrics",
        )
    source = candidate_scale_metrics
    if not _checkpoint_transaction_source_state_valid(source):
        _fail(
            "fgmres_gpu_tree_checkpoint_transaction_source_state_invalid",
            "/candidate_scale_metrics",
        )

    tolerance = _nonnegative_float64(
        solver_tolerance_l2,
        "/solver_tolerance_l2",
    )
    authoritative = _nonnegative_float64(
        authoritative_tolerance,
        "/authoritative_tolerance",
    )
    rhs_maximum = _nonnegative_float64(rhs_linf, "/rhs_linf")
    initial_l2 = _nonnegative_float64(
        initial_residual_l2,
        "/initial_residual_l2",
    )
    divergence = _candidate_scale_divergence_factor(divergence_factor)
    previous_l2 = _nonnegative_float64(
        previous_checkpoint_l2,
        "/previous_checkpoint_l2",
    )
    previous_solution_scale = _nonnegative_float64(
        previous_solution_scale_l2,
        "/previous_solution_scale_l2",
    )
    stagnation_relative = _checkpoint_stagnation_relative_tolerance(
        stagnation_relative_tolerance
    )
    stagnation_limit = _checkpoint_stagnation_limit(stagnation_checkpoint_limit)
    previous_stagnation = _checkpoint_counter(
        previous_stagnation_checkpoint_count,
        "/previous_stagnation_checkpoint_count",
        maximum=stagnation_limit - 1,
    )
    previous_false = _checkpoint_counter(
        previous_false_convergence_count,
        "/previous_false_convergence_count",
    )
    previous_happy = _checkpoint_counter(
        previous_happy_breakdown_count,
        "/previous_happy_breakdown_count",
    )
    if (
        type(max_iterations) is not int
        or not 1 <= max_iterations <= FGMRES_GPU_TREE_MAX_ITERATIONS
        or source.effective_iterations > max_iterations
    ):
        _fail(
            "fgmres_gpu_tree_checkpoint_max_iterations_invalid",
            "/max_iterations",
        )
    if (
        type(restart_dimension) is not int
        or not 1 <= restart_dimension <= _FGMRES_GPU_TREE_MAX_RESTART_DIMENSION
        or source.candidate_residual.candidate_preparation.through_givens.cycle_width
        > restart_dimension
    ):
        _fail(
            "fgmres_gpu_tree_checkpoint_restart_dimension_invalid",
            "/restart_dimension",
        )

    committed_x = _finite_vector_preserve_zero(
        committed_solution,
        "/committed_solution",
    )
    committed_r = _finite_vector_preserve_zero(
        committed_true_residual,
        "/committed_true_residual",
    )
    expected_size = _checkpoint_transaction_vector_size(source)
    if committed_x.size != expected_size or committed_r.shape != committed_x.shape:
        _fail(
            "fgmres_gpu_tree_checkpoint_committed_shape_mismatch",
            "/committed_state",
        )
    committed_residual_l2 = fgmres_gpu_tree_l2_v2(committed_r)
    committed_residual_linf = fgmres_gpu_tree_linf_v2(committed_r)
    committed_scaled = committed_residual_linf.value / max(1.0, rhs_maximum)
    if not math.isfinite(committed_scaled):
        _fail(
            "fgmres_gpu_tree_checkpoint_scaled_residual_invalid",
            "/committed_true_residual",
        )
    committed_scaled = _exact_zero(committed_scaled)

    residual = source.candidate_residual
    active_candidate = (
        source.candidate_required
        and not source.triangular_breakdown
        and source.candidate_replay_valid
    )
    planned_cycle_end = bool(source.candidate_reason_bits & (1 << 2))
    estimated_trigger = bool(source.candidate_reason_bits & (1 << 0))
    solver_passed: bool | None = None
    authoritative_passed: bool | None = None
    dual_passed: bool | None = None
    scaled_candidate: float | None = None
    divergence_evaluated = False
    divergence_threshold: float | None = None
    diverged: bool | None = None
    if active_candidate:
        assert source.candidate_l2 is not None
        assert source.candidate_linf is not None
        scaled_candidate = source.candidate_linf.value / max(1.0, rhs_maximum)
        if not math.isfinite(scaled_candidate):
            _fail(
                "fgmres_gpu_tree_checkpoint_scaled_residual_invalid",
                "/candidate_scaled_residual",
            )
        scaled_candidate = _exact_zero(scaled_candidate)
        solver_passed = source.candidate_l2.value <= tolerance
        authoritative_passed = scaled_candidate <= authoritative
        dual_passed = solver_passed and authoritative_passed
        if planned_cycle_end and not dual_passed and not source.invariant_breakdown:
            divergence_evaluated = True
            divergence_threshold = divergence * max(
                initial_l2,
                _FGMRES_GPU_TREE_DBL_MIN_NORMAL,
            )
            if math.isnan(divergence_threshold) or divergence_threshold < 0.0:
                _fail(
                    "fgmres_gpu_tree_checkpoint_divergence_threshold_invalid",
                    "/divergence_threshold_l2",
                )
            divergence_threshold = _exact_zero(divergence_threshold)
            diverged = source.candidate_l2.value > divergence_threshold

    if not _checkpoint_transaction_policy_matches_source(
        source,
        scaled_candidate_residual_linf=scaled_candidate,
        solver_l2_passed=solver_passed,
        authoritative_linf_passed=authoritative_passed,
        dual_gate_passed=dual_passed,
        divergence_evaluated=divergence_evaluated,
        divergence_threshold_l2=divergence_threshold,
        divergence_detected=diverged,
    ):
        _fail(
            "fgmres_gpu_tree_checkpoint_transaction_policy_mismatch",
            "/candidate_scale_metrics",
        )

    false_count = previous_false
    happy_count = previous_happy
    stagnation_count = previous_stagnation
    stagnation_evaluated = False
    plateau: bool | None = None
    tiny_update: bool | None = None
    x_scale: float | None = None
    commit_required = False
    row_appended = False
    decision = "candidate_inactive"
    continuation_kind: str | None = "same_cycle"
    terminal_status = "not_terminal"
    termination_code = "none"
    restart_hint = "none"
    flags = 0

    if source.triangular_breakdown:
        decision = "triangular_breakdown"
        row_appended = True
        continuation_kind = None
        terminal_status = "arnoldi_breakdown"
        termination_code = "arnoldi_triangular_factor_breakdown"
        restart_hint = "arnoldi_triangular_factor_breakdown"
    elif not active_candidate:
        pass
    else:
        assert solver_passed is not None
        assert authoritative_passed is not None
        assert dual_passed is not None
        flags = _FGMRES_GPU_TREE_RESTART_FLAG_TRUE_RESIDUAL_REPLAYED
        if solver_passed:
            flags |= _FGMRES_GPU_TREE_RESTART_FLAG_SOLVER_L2_PASSED
        if authoritative_passed:
            flags |= _FGMRES_GPU_TREE_RESTART_FLAG_AUTHORITATIVE_LINF_PASSED
        if dual_passed:
            decision = "dual_gate_converged"
            commit_required = True
            row_appended = True
            continuation_kind = None
            terminal_status = "converged"
            if source.invariant_breakdown:
                flags |= _FGMRES_GPU_TREE_RESTART_FLAG_HAPPY_BREAKDOWN
                happy_count += 1
                termination_code = "converged_happy_breakdown"
                restart_hint = "converged_happy_breakdown"
            elif estimated_trigger:
                termination_code = "converged_true_residual"
                restart_hint = "converged_true_residual"
            else:
                termination_code = "converged_restart_true_residual"
                restart_hint = "restart_completed"
        elif source.invariant_breakdown:
            decision = "invariant_breakdown"
            commit_required = True
            row_appended = True
            continuation_kind = None
            terminal_status = "arnoldi_breakdown"
            termination_code = "arnoldi_invariant_subspace_breakdown"
            restart_hint = "arnoldi_invariant_subspace_breakdown"
            flags |= _FGMRES_GPU_TREE_RESTART_FLAG_INVARIANT_BREAKDOWN
        elif not planned_cycle_end:
            decision = "early_false_convergence"
            if estimated_trigger:
                false_count += 1
        elif diverged:
            decision = "diverged"
            commit_required = True
            row_appended = True
            continuation_kind = None
            terminal_status = "diverged"
            termination_code = "true_residual_diverged"
            restart_hint = "restart_completed"
            flags |= _FGMRES_GPU_TREE_RESTART_FLAG_DIVERGENCE
        else:
            if (
                not source.candidate_scale_required
                or source.trial_x_l2 is None
                or source.committed_x_l2 is None
                or source.solution_update_l2 is None
            ):
                _fail(
                    "fgmres_gpu_tree_checkpoint_scale_state_invalid",
                    "/candidate_scale_metrics",
                )
            x_scale = source.trial_x_l2.value + source.committed_x_l2.value
            if not math.isfinite(x_scale):
                _fail(
                    "fgmres_gpu_tree_checkpoint_x_scale_overflow",
                    "/x_scale_l2",
                )
            x_scale = _exact_zero(x_scale)
            plateau_threshold = (1.0 - stagnation_relative) * previous_l2
            tiny_threshold = _FGMRES_GPU_TREE_SQRT_EPS * x_scale
            if not math.isfinite(plateau_threshold) or not math.isfinite(
                tiny_threshold
            ):
                _fail(
                    "fgmres_gpu_tree_checkpoint_stagnation_threshold_invalid",
                    "/stagnation",
                )
            assert source.candidate_l2 is not None
            plateau = source.candidate_l2.value >= plateau_threshold
            tiny_update = source.solution_update_l2.value <= tiny_threshold
            stagnation_evaluated = True
            if plateau:
                flags |= _FGMRES_GPU_TREE_RESTART_FLAG_STAGNATION_PLATEAU
            if tiny_update:
                flags |= _FGMRES_GPU_TREE_RESTART_FLAG_TINY_UPDATE
            stagnation_count = previous_stagnation + 1 if plateau and tiny_update else 0
            commit_required = True
            row_appended = True
            restart_hint = "restart_completed"
            if stagnation_count >= stagnation_limit:
                decision = "stagnated"
                continuation_kind = None
                terminal_status = "stagnated"
                termination_code = "true_residual_stagnated"
            elif source.effective_iterations >= max_iterations:
                decision = "max_iterations"
                continuation_kind = None
                terminal_status = "max_iterations"
                termination_code = "max_iterations_exhausted"
            else:
                decision = "between_restarts"
                continuation_kind = "between_restarts"

    pending_terminal_status = terminal_status
    pending_termination_code = termination_code
    cycle_width = (
        source.candidate_residual.candidate_preparation.through_givens.cycle_width
    )
    final_guard_handoff_required = (
        terminal_status == "max_iterations"
        and termination_code == "max_iterations_exhausted"
        and commit_required
        and row_appended
        and restart_dimension == 1
        and cycle_width == restart_dimension
        and source.arnoldi_step_count == restart_dimension
        and source.effective_iterations == max_iterations == restart_dimension
    )
    if final_guard_handoff_required:
        terminal_status = "not_terminal"
        termination_code = "none"

    if commit_required:
        trial = _finite_vector(
            residual.candidate_preparation.trial_x,
            "/candidate_scale_metrics/candidate_preparation/trial_x",
        )
        candidate_true_residual = _finite_vector(
            residual.candidate_true_residual,
            "/candidate_scale_metrics/candidate_true_residual",
        )
        if (
            trial.shape != committed_x.shape
            or candidate_true_residual.shape != trial.shape
        ):
            _fail(
                "fgmres_gpu_tree_checkpoint_candidate_shape_mismatch",
                "/candidate_state",
            )
        solution_x = _immutable_f64(trial)
        true_residual = _immutable_f64(candidate_true_residual)
        assert source.candidate_l2 is not None
        assert source.candidate_linf is not None
        final_l2 = source.candidate_l2.value
        final_linf = source.candidate_linf.value
        assert scaled_candidate is not None
        final_scaled = scaled_candidate
    else:
        solution_x = _immutable_f64_preserve_zero(committed_x)
        true_residual = _immutable_f64_preserve_zero(committed_r)
        final_l2 = committed_residual_l2.value
        final_linf = committed_residual_linf.value
        final_scaled = committed_scaled

    if source.candidate_scale_required:
        assert x_scale is not None
        solution_scale = x_scale
        assert source.candidate_l2 is not None
        finalized_previous_l2 = source.candidate_l2.value
    else:
        solution_scale = previous_solution_scale
        finalized_previous_l2 = previous_l2

    record: FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2 | None = None
    if row_appended:
        if source.triangular_breakdown:
            record_l2 = committed_residual_l2.value
            record_linf = committed_residual_linf.value
            record_scaled = committed_scaled
            update_l2 = 0.0
        else:
            assert source.candidate_l2 is not None
            assert source.candidate_linf is not None
            assert scaled_candidate is not None
            record_l2 = source.candidate_l2.value
            record_linf = source.candidate_linf.value
            record_scaled = scaled_candidate
            update_l2 = (
                source.solution_update_l2.value
                if source.solution_update_l2 is not None
                else 0.0
            )
        estimated = residual.candidate_preparation.through_givens.estimated_residual_l2
        record = FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2(
            restart_index=1,
            start_iteration=0,
            end_iteration=source.effective_iterations,
            arnoldi_step_count=source.arnoldi_step_count,
            reorthogonalization_count=source.reorthogonalization_count,
            termination_hint=restart_hint,
            termination_hint_code=_FGMRES_GPU_TREE_RESTART_HINT_CODES[restart_hint],
            flags=flags,
            estimated_residual_l2=estimated,
            true_residual_l2=record_l2,
            true_residual_linf=record_linf,
            scaled_true_residual=record_scaled,
            solution_update_l2=update_l2,
        )

    terminal = terminal_status != "not_terminal"
    continuation_required = continuation_kind is not None
    phase_after = (
        "terminal"
        if terminal
        else (
            "between_restarts" if continuation_kind == "between_restarts" else "arnoldi"
        )
    )
    column_index_after = (
        0
        if terminal or final_guard_handoff_required
        else (-1 if continuation_kind == "between_restarts" else 1)
    )
    start_mask = source.reduction_valid_mask
    return FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2(
        candidate_scale_metrics=source,
        start_reduction_valid_mask=start_mask,
        decide_reduction_valid_mask=start_mask,
        commit_reduction_valid_mask=start_mask,
        finalize_reduction_valid_mask=0,
        active_during_decide=True,
        active_during_commit=True,
        active_after_finalize=not terminal,
        decision=decision,
        candidate_required=source.candidate_required,
        candidate_reason_bits=source.candidate_reason_bits,
        triangular_breakdown=source.triangular_breakdown,
        invariant_breakdown=source.invariant_breakdown,
        planned_cycle_end=planned_cycle_end,
        dual_gate_evaluated=active_candidate,
        scaled_candidate_residual_linf=scaled_candidate,
        solver_l2_passed=solver_passed,
        authoritative_linf_passed=authoritative_passed,
        dual_gate_passed=dual_passed,
        divergence_evaluated=divergence_evaluated,
        divergence_threshold_l2=divergence_threshold,
        divergence_detected=diverged,
        stagnation_evaluated=stagnation_evaluated,
        stagnation_plateau=plateau,
        tiny_update=tiny_update,
        x_scale_l2=x_scale,
        commit_required=commit_required,
        continuation_required=continuation_required,
        continuation_kind=continuation_kind,
        row_appended=row_appended,
        restart_record=record,
        pending_terminal_status=pending_terminal_status,
        pending_terminal_status_code=_FGMRES_GPU_TREE_TERMINAL_STATUS_CODES[
            pending_terminal_status
        ],
        pending_termination_code=pending_termination_code,
        pending_termination_code_value=_FGMRES_GPU_TREE_TERMINATION_CODES[
            pending_termination_code
        ],
        pending_restart_hint=restart_hint,
        pending_restart_hint_code=_FGMRES_GPU_TREE_RESTART_HINT_CODES[restart_hint],
        pending_restart_flags=flags,
        terminal_status=terminal_status,
        terminal_status_code=_FGMRES_GPU_TREE_TERMINAL_STATUS_CODES[terminal_status],
        termination_code=termination_code,
        termination_code_value=_FGMRES_GPU_TREE_TERMINATION_CODES[termination_code],
        phase_after_finalize=phase_after,
        final_guard_handoff_required=final_guard_handoff_required,
        column_index_after_finalize=column_index_after,
        previous_stagnation_checkpoint_count=previous_stagnation,
        stagnation_checkpoint_count=stagnation_count,
        previous_false_convergence_count=previous_false,
        false_convergence_count=false_count,
        previous_happy_breakdown_count=previous_happy,
        happy_breakdown_count=happy_count,
        previous_checkpoint_l2_before=previous_l2,
        previous_checkpoint_l2=finalized_previous_l2,
        previous_solution_scale_l2=previous_solution_scale,
        solution_scale_l2=solution_scale,
        final_residual_l2=final_l2,
        final_residual_linf=final_linf,
        final_scaled_residual=final_scaled,
        solution_x=solution_x,
        true_residual=true_residual,
        effective_iterations=source.effective_iterations,
        arnoldi_step_count=source.arnoldi_step_count,
        effective_arnoldi_dimension=source.effective_arnoldi_dimension,
        reorthogonalization_count=source.reorthogonalization_count,
        operator_apply_count=source.operator_apply_count,
        preconditioner_apply_count=source.preconditioner_apply_count,
        checkpoint_decision_included=True,
        checkpoint_commit_included=True,
        checkpoint_finalize_included=True,
        solution_and_true_residual_committed=commit_required,
    )


def replay_fgmres_gpu_tree_first_column_candidate_preparation_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    basis_v0: Any,
    jacobi_inverse: Any,
    cycle_beta: float,
    solver_tolerance_l2: float,
    cycle_width: int,
    committed_solution: Any,
) -> FgmresGpuTreeFirstColumnCandidatePreparationV2:
    """Replay column zero through the bounded candidate ``VECTOR_ACCEPT``."""

    through_givens = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=jacobi_inverse,
        cycle_beta=cycle_beta,
        solver_tolerance_l2=solver_tolerance_l2,
        cycle_width=cycle_width,
    )
    return prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=through_givens,
        committed_solution=committed_solution,
    )


def replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    basis_v0: Any,
    jacobi_inverse: Any,
    cycle_beta: float,
    solver_tolerance_l2: float,
    cycle_width: int,
    committed_solution: Any,
    reduced_load: Any,
) -> FgmresGpuTreeFirstColumnCandidateResidualReplayV2:
    """Replay column zero through candidate true-residual L2/Linf metrics."""

    preparation = replay_fgmres_gpu_tree_first_column_candidate_preparation_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=jacobi_inverse,
        cycle_beta=cycle_beta,
        solver_tolerance_l2=solver_tolerance_l2,
        cycle_width=cycle_width,
        committed_solution=committed_solution,
    )
    return prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=preparation,
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        reduced_load=reduced_load,
    )


def replay_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    basis_v0: Any,
    jacobi_inverse: Any,
    cycle_beta: float,
    solver_tolerance_l2: float,
    cycle_width: int,
    committed_solution: Any,
    reduced_load: Any,
    authoritative_tolerance: float,
    rhs_linf: float,
    initial_residual_l2: float,
    divergence_factor: float,
) -> FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2:
    """Replay column zero through gated trial/committed L2 scale metrics."""

    candidate_residual = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=jacobi_inverse,
        cycle_beta=cycle_beta,
        solver_tolerance_l2=solver_tolerance_l2,
        cycle_width=cycle_width,
        committed_solution=committed_solution,
        reduced_load=reduced_load,
    )
    return prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=candidate_residual,
        solver_tolerance_l2=solver_tolerance_l2,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=rhs_linf,
        initial_residual_l2=initial_residual_l2,
        divergence_factor=divergence_factor,
        committed_solution=committed_solution,
    )


def replay_fgmres_gpu_tree_first_column_checkpoint_transaction_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    basis_v0: Any,
    jacobi_inverse: Any,
    cycle_beta: float,
    solver_tolerance_l2: float,
    cycle_width: int,
    committed_solution: Any,
    committed_true_residual: Any,
    reduced_load: Any,
    authoritative_tolerance: float,
    rhs_linf: float,
    initial_residual_l2: float,
    divergence_factor: float,
    previous_checkpoint_l2: float,
    previous_solution_scale_l2: float,
    previous_stagnation_checkpoint_count: int,
    previous_false_convergence_count: int,
    previous_happy_breakdown_count: int,
    stagnation_relative_tolerance: float,
    stagnation_checkpoint_limit: int,
    max_iterations: int,
    restart_dimension: int,
) -> FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2:
    """Replay raw column-zero inputs through the checkpoint transaction."""

    scale_metrics = replay_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        row_ptr=row_ptr,
        column_indices=column_indices,
        values=values,
        basis_v0=basis_v0,
        jacobi_inverse=jacobi_inverse,
        cycle_beta=cycle_beta,
        solver_tolerance_l2=solver_tolerance_l2,
        cycle_width=cycle_width,
        committed_solution=committed_solution,
        reduced_load=reduced_load,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=rhs_linf,
        initial_residual_l2=initial_residual_l2,
        divergence_factor=divergence_factor,
    )
    return prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2(
        candidate_scale_metrics=scale_metrics,
        solver_tolerance_l2=solver_tolerance_l2,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=rhs_linf,
        initial_residual_l2=initial_residual_l2,
        divergence_factor=divergence_factor,
        committed_solution=committed_solution,
        committed_true_residual=committed_true_residual,
        previous_checkpoint_l2=previous_checkpoint_l2,
        previous_solution_scale_l2=previous_solution_scale_l2,
        previous_stagnation_checkpoint_count=previous_stagnation_checkpoint_count,
        previous_false_convergence_count=previous_false_convergence_count,
        previous_happy_breakdown_count=previous_happy_breakdown_count,
        stagnation_relative_tolerance=stagnation_relative_tolerance,
        stagnation_checkpoint_limit=stagnation_checkpoint_limit,
        max_iterations=max_iterations,
        restart_dimension=restart_dimension,
    )


def replay_fgmres_gpu_tree_initial_v2(
    *,
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    rhs: Any,
    initial_solution: Any,
    absolute_tolerance: float,
    relative_tolerance: float,
    authoritative_tolerance: float,
    max_iterations: int,
) -> FgmresGpuTreeInitialReplayV2:
    """Replay ``x=x0`` and explicit ``r=b-Ax`` through GPU-tree gates."""

    b = _finite_vector(rhs, "/rhs")
    x = _finite_vector(initial_solution, "/initial_solution")
    if b.shape != x.shape:
        _fail(
            "fgmres_gpu_tree_initial_shape_mismatch",
            "/initial_solution",
        )
    checked_row_ptr, checked_columns, checked_values = _validated_csr(
        row_ptr,
        column_indices,
        values,
        int(b.size),
    )
    atol = _nonnegative_float64(absolute_tolerance, "/absolute_tolerance")
    rtol = _nonnegative_float64(relative_tolerance, "/relative_tolerance")
    if atol == 0.0 and rtol == 0.0:
        _fail(
            "fgmres_gpu_tree_tolerance_empty",
            "/tolerance",
            "At least one solver tolerance must be positive.",
        )
    authoritative = _nonnegative_float64(
        authoritative_tolerance,
        "/authoritative_tolerance",
    )
    if (
        type(max_iterations) is not int
        or not 0 <= max_iterations <= FGMRES_GPU_TREE_MAX_ITERATIONS
    ):
        _fail(
            "fgmres_gpu_tree_max_iterations_invalid",
            "/max_iterations",
        )

    operator_value = np.empty_like(x)
    for row in range(int(x.size)):
        accumulator = 0.0
        begin = int(checked_row_ptr[row])
        end = int(checked_row_ptr[row + 1])
        for position in range(begin, end):
            product = float(checked_values[position]) * float(
                x[int(checked_columns[position])]
            )
            updated = accumulator + product
            if not math.isfinite(product) or not math.isfinite(updated):
                _fail(
                    "fgmres_gpu_tree_operator_arithmetic_overflow",
                    f"/row_ptr/{row}",
                )
            accumulator = updated
        operator_value[row] = _exact_zero(accumulator)

    with np.errstate(over="ignore", invalid="ignore"):
        residual = b - operator_value
    if not np.isfinite(residual).all():
        _fail(
            "fgmres_gpu_tree_residual_arithmetic_overflow",
            "/true_residual",
        )
    residual[residual == 0.0] = 0.0

    rhs_l2 = fgmres_gpu_tree_l2_v2(b)
    rhs_linf = fgmres_gpu_tree_linf_v2(b)
    residual_l2 = fgmres_gpu_tree_l2_v2(residual)
    residual_linf = fgmres_gpu_tree_linf_v2(residual)
    with np.errstate(over="ignore", invalid="ignore"):
        relative_product = rtol * rhs_l2.value
    tolerance_l2 = max(atol, relative_product)
    scaled_linf = residual_linf.value / max(1.0, rhs_linf.value)
    if not math.isfinite(tolerance_l2) or not math.isfinite(scaled_linf):
        _fail(
            "fgmres_gpu_tree_gate_arithmetic_overflow",
            "/gate",
        )
    solver_passed = residual_l2.value <= tolerance_l2
    authoritative_passed = scaled_linf <= authoritative
    if solver_passed and authoritative_passed:
        terminal_status: InitialTerminalStatus = "converged"
        termination_code = "converged_initial_true_residual"
    elif max_iterations == 0:
        terminal_status = "max_iterations"
        termination_code = "max_iterations_exhausted"
    else:
        terminal_status = "not_terminal"
        termination_code = "none"

    return FgmresGpuTreeInitialReplayV2(
        solution_x=_immutable_f64(x),
        operator_value=_immutable_f64(operator_value),
        true_residual=_immutable_f64(residual),
        rhs_l2=rhs_l2,
        rhs_linf=rhs_linf,
        residual_l2=residual_l2,
        residual_linf=residual_linf,
        solver_tolerance_l2=_exact_zero(tolerance_l2),
        scaled_residual_linf=_exact_zero(scaled_linf),
        solver_l2_passed=solver_passed,
        authoritative_linf_passed=authoritative_passed,
        terminal_status=terminal_status,
        termination_code=termination_code,
        operator_apply_count=1,
    )


def _dot_product_stage(left: np.ndarray, right: np.ndarray) -> list[float]:
    return [
        _dot_product_reduce_segment(left, right, start)
        for start in range(0, int(left.size), FGMRES_GPU_TREE_VALUES_PER_BLOCK)
    ]


def _dot_product_reduce_segment(
    left: np.ndarray,
    right: np.ndarray,
    start: int,
) -> float:
    lanes = [0.0] * FGMRES_GPU_TREE_THREADS_PER_BLOCK
    for lane in range(FGMRES_GPU_TREE_THREADS_PER_BLOCK):
        first = start + lane
        if first < int(left.size):
            lanes[lane] = _checked_product(
                float(left[first]),
                float(right[first]),
                code="fgmres_gpu_tree_dot_arithmetic_overflow",
                path=f"/reduction/dot/product/{first}",
            )
        second = first + FGMRES_GPU_TREE_THREADS_PER_BLOCK
        if second < int(left.size):
            product = _checked_product(
                float(left[second]),
                float(right[second]),
                code="fgmres_gpu_tree_dot_arithmetic_overflow",
                path=f"/reduction/dot/product/{second}",
            )
            lanes[lane] = _checked_sum(
                lanes[lane],
                product,
                code="fgmres_gpu_tree_dot_arithmetic_overflow",
                path=f"/reduction/dot/block/{start // 512}/lane/{lane}",
            )
    return _sum_reduce_lanes(lanes, "/reduction/dot/block")


def _sum_combine_stage(values: list[float], path: str) -> list[float]:
    return [
        _sum_reduce_segment(tuple(values[start : start + 512]), path, start)
        for start in range(0, len(values), FGMRES_GPU_TREE_VALUES_PER_BLOCK)
    ]


def _sum_reduce_segment(values: tuple[float, ...], path: str, start: int) -> float:
    lanes = [0.0] * FGMRES_GPU_TREE_THREADS_PER_BLOCK
    for lane in range(FGMRES_GPU_TREE_THREADS_PER_BLOCK):
        if lane < len(values):
            lanes[lane] = values[lane]
        second = lane + FGMRES_GPU_TREE_THREADS_PER_BLOCK
        if second < len(values):
            lanes[lane] = _checked_sum(
                lanes[lane],
                values[second],
                code="fgmres_gpu_tree_dot_arithmetic_overflow",
                path=f"{path}/{start // 512}/lane/{lane}",
            )
    return _sum_reduce_lanes(lanes, path)


def _sum_reduce_lanes(lanes: list[float], path: str) -> float:
    offset = FGMRES_GPU_TREE_THREADS_PER_BLOCK // 2
    while offset:
        for lane in range(offset):
            lanes[lane] = _checked_sum(
                lanes[lane],
                lanes[lane + offset],
                code="fgmres_gpu_tree_dot_arithmetic_overflow",
                path=f"{path}/tree/{offset}/{lane}",
            )
        offset //= 2
    return _exact_zero(lanes[0])


def _checked_elementwise_product(
    left: np.ndarray,
    right: np.ndarray,
    *,
    code: str,
    path: str,
) -> np.ndarray:
    output = np.empty_like(left)
    for index in range(int(left.size)):
        output[index] = _exact_zero(
            _checked_product(
                float(left[index]),
                float(right[index]),
                code=code,
                path=f"{path}/{index}",
            )
        )
    return output


def _sequential_csr_matvec(
    row_ptr: np.ndarray,
    column_indices: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    output = np.empty_like(vector)
    for row in range(int(vector.size)):
        accumulator = 0.0
        begin = int(row_ptr[row])
        end = int(row_ptr[row + 1])
        for position in range(begin, end):
            product = _checked_product(
                float(values[position]),
                float(vector[int(column_indices[position])]),
                code="fgmres_gpu_tree_operator_arithmetic_overflow",
                path=f"/row_ptr/{row}/product/{position}",
            )
            accumulator = _checked_sum(
                accumulator,
                product,
                code="fgmres_gpu_tree_operator_arithmetic_overflow",
                path=f"/row_ptr/{row}/sum/{position}",
            )
        output[row] = _exact_zero(accumulator)
    return output


def _checked_mgs_subtract(
    work: np.ndarray,
    basis: np.ndarray,
    coefficient: float,
    *,
    path: str,
) -> np.ndarray:
    output = np.empty_like(work)
    for index in range(int(work.size)):
        projection = _checked_product(
            coefficient,
            float(basis[index]),
            code="fgmres_gpu_tree_mgs_arithmetic_overflow",
            path=f"{path}/{index}/projection",
        )
        updated = float(work[index]) - projection
        if not math.isfinite(updated):
            _fail(
                "fgmres_gpu_tree_mgs_arithmetic_overflow",
                f"{path}/{index}/subtract",
            )
        output[index] = _exact_zero(updated)
    return output


def _checked_normalize(
    values: np.ndarray, denominator: float, *, path: str
) -> np.ndarray:
    if not math.isfinite(denominator) or denominator <= 0.0:
        _fail("fgmres_gpu_tree_normalization_denominator_invalid", path)
    output = np.empty_like(values)
    for index in range(int(values.size)):
        normalized = float(values[index]) / denominator
        if not math.isfinite(normalized):
            _fail(
                "fgmres_gpu_tree_normalization_arithmetic_overflow",
                f"{path}/{index}",
            )
        output[index] = _exact_zero(normalized)
    return output


def _checked_product(
    left: float,
    right: float,
    *,
    code: str,
    path: str,
) -> float:
    product = left * right
    if not math.isfinite(product):
        _fail(code, path)
    return product


def _checked_sum(
    left: float,
    right: float,
    *,
    code: str,
    path: str,
) -> float:
    result = left + right
    if not math.isfinite(result):
        _fail(code, path)
    return result


def _lassq_stage(values: np.ndarray) -> list[_LassqPair]:
    return [
        _lassq_reduce_segment(
            tuple(
                _lassq_value_pair(float(value)) for value in values[start : start + 512]
            )
        )
        for start in range(0, int(values.size), FGMRES_GPU_TREE_VALUES_PER_BLOCK)
    ]


def _lassq_combine_stage(values: list[_LassqPair]) -> list[_LassqPair]:
    return [
        _lassq_reduce_segment(tuple(values[start : start + 512]))
        for start in range(0, len(values), FGMRES_GPU_TREE_VALUES_PER_BLOCK)
    ]


def _lassq_reduce_segment(values: tuple[_LassqPair, ...]) -> _LassqPair:
    lanes = [_lassq_zero_pair() for _ in range(FGMRES_GPU_TREE_THREADS_PER_BLOCK)]
    for lane in range(FGMRES_GPU_TREE_THREADS_PER_BLOCK):
        if lane < len(values):
            lanes[lane] = values[lane]
        second = lane + FGMRES_GPU_TREE_THREADS_PER_BLOCK
        if second < len(values):
            lanes[lane] = _lassq_merge(lanes[lane], values[second])
    offset = FGMRES_GPU_TREE_THREADS_PER_BLOCK // 2
    while offset:
        for lane in range(offset):
            lanes[lane] = _lassq_merge(lanes[lane], lanes[lane + offset])
        offset //= 2
    return lanes[0]


def _max_stage(values: np.ndarray) -> list[float]:
    return [
        _max_reduce_segment(
            tuple(float(value) for value in values[start : start + 512])
        )
        for start in range(0, int(values.size), FGMRES_GPU_TREE_VALUES_PER_BLOCK)
    ]


def _max_combine_stage(values: list[float]) -> list[float]:
    return [
        _max_reduce_segment(tuple(values[start : start + 512]))
        for start in range(0, len(values), FGMRES_GPU_TREE_VALUES_PER_BLOCK)
    ]


def _max_reduce_segment(values: tuple[float, ...]) -> float:
    lanes = [0.0] * FGMRES_GPU_TREE_THREADS_PER_BLOCK
    for lane in range(FGMRES_GPU_TREE_THREADS_PER_BLOCK):
        if lane < len(values):
            lanes[lane] = abs(values[lane])
        second = lane + FGMRES_GPU_TREE_THREADS_PER_BLOCK
        if second < len(values):
            lanes[lane] = max(lanes[lane], abs(values[second]))
    offset = FGMRES_GPU_TREE_THREADS_PER_BLOCK // 2
    while offset:
        for lane in range(offset):
            lanes[lane] = max(lanes[lane], lanes[lane + offset])
        offset //= 2
    return _exact_zero(lanes[0])


def _lassq_zero_pair() -> _LassqPair:
    return _LassqPair(0.0, 1.0)


def _lassq_value_pair(value: float) -> _LassqPair:
    magnitude = abs(value)
    return _lassq_zero_pair() if magnitude == 0.0 else _LassqPair(magnitude, 1.0)


def _lassq_merge(left: _LassqPair, right: _LassqPair) -> _LassqPair:
    if not _lassq_pair_valid(left) or not _lassq_pair_valid(right):
        _fail(
            "fgmres_gpu_tree_lassq_pair_invalid",
            "/reduction/lassq",
        )
    if left.scale == 0.0:
        return right
    if right.scale == 0.0:
        return left
    if left.scale >= right.scale:
        ratio = right.scale / left.scale
        contribution = right.ssq * ratio * ratio
        result = _LassqPair(left.scale, left.ssq + contribution)
    else:
        ratio = left.scale / right.scale
        contribution = left.ssq * ratio * ratio
        result = _LassqPair(right.scale, right.ssq + contribution)
    if not _lassq_pair_valid(result):
        _fail(
            "fgmres_gpu_tree_lassq_arithmetic_overflow",
            "/reduction/lassq",
        )
    return _LassqPair(_exact_zero(result.scale), result.ssq)


def _lassq_pair_valid(value: _LassqPair) -> bool:
    return (
        math.isfinite(value.scale)
        and math.isfinite(value.ssq)
        and value.scale >= 0.0
        and value.ssq >= 1.0
        and (value.scale != 0.0 or value.ssq == 1.0)
    )


def _validated_csr(
    row_ptr: Any,
    column_indices: Any,
    values: Any,
    n: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        raw_rows = np.asarray(row_ptr)
        raw_columns = np.asarray(column_indices)
        raw_numeric = np.asarray(values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FgmresGpuTreeReferenceV2Error(
            "fgmres_gpu_tree_csr_type_invalid",
            "/csr",
        ) from exc
    int32 = np.iinfo(np.int32)
    if (
        raw_rows.ndim != 1
        or raw_columns.ndim != 1
        or raw_numeric.ndim != 1
        or raw_rows.dtype.kind not in "iu"
        or raw_columns.dtype.kind not in "iu"
        or raw_numeric.dtype.kind not in "fiu"
        or raw_rows.dtype.kind == "b"
        or raw_columns.dtype.kind == "b"
        or raw_numeric.dtype.kind == "b"
        or np.any(raw_rows < int32.min)
        or np.any(raw_rows > int32.max)
        or np.any(raw_columns < int32.min)
        or np.any(raw_columns > int32.max)
    ):
        _fail("fgmres_gpu_tree_csr_type_invalid", "/csr")
    rows = np.ascontiguousarray(raw_rows, dtype="<i4")
    columns = np.ascontiguousarray(raw_columns, dtype="<i4")
    numeric = np.ascontiguousarray(raw_numeric, dtype="<f8")
    if (
        rows.ndim != 1
        or columns.ndim != 1
        or numeric.ndim != 1
        or rows.size != n + 1
        or columns.size != numeric.size
        or columns.size < n
        or rows.size == 0
        or int(rows[0]) != 0
        or int(rows[-1]) != int(columns.size)
        or np.any(rows[1:] < rows[:-1])
        or np.any(columns < 0)
        or np.any(columns >= n)
        or not np.isfinite(numeric).all()
    ):
        _fail("fgmres_gpu_tree_csr_invalid", "/csr")
    for row in range(n):
        begin = int(rows[row])
        end = int(rows[row + 1])
        if end > begin and np.any(columns[begin + 1 : end] <= columns[begin : end - 1]):
            _fail("fgmres_gpu_tree_csr_invalid", f"/row_ptr/{row}")
    return rows, columns, numeric


def _finite_vector(values: Any, path: str) -> np.ndarray:
    try:
        raw = np.asarray(values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FgmresGpuTreeReferenceV2Error(
            "fgmres_gpu_tree_vector_type_invalid",
            path,
        ) from exc
    if raw.ndim != 1 or raw.dtype.kind not in "fiu" or raw.dtype.kind == "b":
        _fail("fgmres_gpu_tree_vector_type_invalid", path)
    vector = np.ascontiguousarray(raw, dtype="<f8")
    if vector.ndim != 1 or vector.size == 0:
        _fail("fgmres_gpu_tree_vector_shape_invalid", path)
    if not np.isfinite(vector).all():
        _fail("fgmres_gpu_tree_vector_nonfinite", path)
    vector = vector.copy()
    vector[vector == 0.0] = 0.0
    return vector


def _nonnegative_float64(value: Any, path: str) -> float:
    if type(value) not in (int, float):
        _fail("fgmres_gpu_tree_tolerance_type_invalid", path)
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FgmresGpuTreeReferenceV2Error(
            "fgmres_gpu_tree_tolerance_invalid",
            path,
        ) from exc
    if not math.isfinite(converted) or converted < 0.0:
        _fail("fgmres_gpu_tree_tolerance_invalid", path)
    return converted


def _positive_float64(
    value: Any,
    path: str,
    *,
    type_code: str,
    value_code: str,
) -> float:
    if type(value) not in (int, float):
        _fail(type_code, path)
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FgmresGpuTreeReferenceV2Error(value_code, path) from exc
    if not math.isfinite(converted) or converted <= 0.0:
        _fail(value_code, path)
    return converted


def _candidate_scale_divergence_factor(value: Any) -> float:
    path = "/divergence_factor"
    if type(value) not in (int, float):
        _fail("fgmres_gpu_tree_divergence_factor_type_invalid", path)
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FgmresGpuTreeReferenceV2Error(
            "fgmres_gpu_tree_divergence_factor_invalid",
            path,
        ) from exc
    if not math.isfinite(converted) or converted <= 1.0:
        _fail("fgmres_gpu_tree_divergence_factor_invalid", path)
    return converted


def _candidate_scale_metrics_source_state_valid(
    residual: FgmresGpuTreeFirstColumnCandidateResidualReplayV2,
) -> bool:
    preparation = residual.candidate_preparation
    if type(preparation) is not FgmresGpuTreeFirstColumnCandidatePreparationV2:
        return False
    candidate_required = residual.candidate_required
    triangular_breakdown = residual.triangular_breakdown
    active_candidate = candidate_required and not triangular_breakdown
    expected_phase: FirstColumnGivensPhase = (
        "candidate" if candidate_required else "arnoldi"
    )
    expected_mask = _FGMRES_GPU_TREE_CANDIDATE_RESIDUAL_MASK if active_candidate else 0
    expected_operator_count = preparation.operator_apply_count + int(active_candidate)

    state_valid = (
        type(candidate_required) is bool
        and type(residual.candidate_reason_bits) is int
        and 0 <= residual.candidate_reason_bits <= 0b111
        and candidate_required == (residual.candidate_reason_bits != 0)
        and type(triangular_breakdown) is bool
        and type(residual.invariant_breakdown) is bool
        and residual.phase == expected_phase
        and residual.candidate_required == preparation.candidate_required
        and residual.candidate_reason_bits == preparation.candidate_reason_bits
        and residual.triangular_breakdown == preparation.triangular_breakdown
        and residual.invariant_breakdown == preparation.invariant_breakdown
        and type(residual.candidate_replay_attempted) is bool
        and type(residual.candidate_replay_valid) is bool
        and residual.candidate_replay_attempted == active_candidate
        and residual.candidate_replay_valid == active_candidate
        and residual.solution_update_l2 is preparation.solution_update_l2
        and residual.trial_x_l2 is None
        and residual.committed_x_l2 is None
        and type(residual.reduction_valid_mask) is int
        and residual.reduction_valid_mask == expected_mask
        and all(
            type(value) is int
            for value in (
                residual.effective_iterations,
                residual.arnoldi_step_count,
                residual.effective_arnoldi_dimension,
                residual.reorthogonalization_count,
                residual.operator_apply_count,
                residual.preconditioner_apply_count,
            )
        )
        and residual.effective_iterations == preparation.effective_iterations
        and residual.arnoldi_step_count == preparation.arnoldi_step_count
        and residual.effective_arnoldi_dimension
        == preparation.effective_arnoldi_dimension
        and residual.reorthogonalization_count == preparation.reorthogonalization_count
        and residual.operator_apply_count == expected_operator_count
        and residual.preconditioner_apply_count
        == preparation.preconditioner_apply_count
        and type(residual.checkpoint_decision_included) is bool
        and type(residual.checkpoint_commit_included) is bool
        and type(residual.solution_and_true_residual_committed) is bool
        and residual.checkpoint_decision_included is False
        and residual.checkpoint_commit_included is False
        and residual.solution_and_true_residual_committed is False
    )
    if not state_valid:
        return False
    if not active_candidate:
        return (
            residual.candidate_operator_value is None
            and residual.candidate_true_residual is None
            and residual.candidate_l2 is None
            and residual.candidate_linf is None
        )

    operator = residual.candidate_operator_value
    candidate_vector = residual.candidate_true_residual
    trial = preparation.trial_x
    if (
        type(operator) is not np.ndarray
        or type(candidate_vector) is not np.ndarray
        or type(trial) is not np.ndarray
        or operator.ndim != 1
        or candidate_vector.ndim != 1
        or trial.ndim != 1
        or operator.size == 0
        or operator.shape != candidate_vector.shape
        or operator.shape != trial.shape
        or not np.isfinite(operator).all()
        or not np.isfinite(candidate_vector).all()
        or not np.isfinite(trial).all()
    ):
        return False
    candidate_l2 = residual.candidate_l2
    candidate_linf = residual.candidate_linf
    return (
        _candidate_scale_reduction_valid(
            candidate_l2,
            operation="lassq_l2",
            value_count=int(candidate_vector.size),
        )
        and _candidate_scale_reduction_valid(
            candidate_linf,
            operation="abs_max_linf",
            value_count=int(candidate_vector.size),
        )
        and candidate_l2 is not None
        and candidate_linf is not None
        and candidate_l2.stage_output_counts == candidate_linf.stage_output_counts
    )


def _candidate_scale_reduction_valid(
    reduction: FgmresGpuTreeReductionV2 | None,
    *,
    operation: GpuTreeOperation,
    value_count: int,
) -> bool:
    return (
        type(reduction) is FgmresGpuTreeReductionV2
        and reduction.operation == operation
        and type(reduction.value_count) is int
        and reduction.value_count == value_count
        and type(reduction.stage_output_counts) is tuple
        and len(reduction.stage_output_counts) >= 1
        and all(
            type(count) is int and count >= 1 for count in reduction.stage_output_counts
        )
        and reduction.stage_output_counts[-1] == 1
        and type(reduction.value) is float
        and math.isfinite(reduction.value)
        and reduction.value >= 0.0
    )


def _checkpoint_transaction_source_state_valid(
    source: FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2,
) -> bool:
    residual = source.candidate_residual
    if (
        type(residual) is not FgmresGpuTreeFirstColumnCandidateResidualReplayV2
        or not _candidate_scale_metrics_source_state_valid(residual)
    ):
        return False
    active_candidate = (
        source.candidate_required
        and not source.triangular_breakdown
        and source.candidate_replay_valid
    )
    preparation = residual.candidate_preparation
    planned = bool(source.candidate_reason_bits & (1 << 2))
    base_valid = (
        source.candidate_required == residual.candidate_required
        and source.candidate_reason_bits == residual.candidate_reason_bits
        and source.triangular_breakdown == residual.triangular_breakdown
        and source.invariant_breakdown == residual.invariant_breakdown
        and source.phase == residual.phase
        and source.candidate_replay_attempted == residual.candidate_replay_attempted
        and source.candidate_replay_valid == residual.candidate_replay_valid
        and source.planned_cycle_end == planned
        and source.solution_update_l2 is residual.solution_update_l2
        and source.candidate_l2 is residual.candidate_l2
        and source.candidate_linf is residual.candidate_linf
        and source.x_scale_l2 is None
        and source.prior_reduction_valid_mask == residual.reduction_valid_mask
        and source.effective_iterations == residual.effective_iterations
        and source.arnoldi_step_count == residual.arnoldi_step_count
        and source.effective_arnoldi_dimension == residual.effective_arnoldi_dimension
        and source.reorthogonalization_count == residual.reorthogonalization_count
        and source.operator_apply_count == residual.operator_apply_count
        and source.preconditioner_apply_count == residual.preconditioner_apply_count
        and source.checkpoint_decision_included is False
        and source.checkpoint_commit_included is False
        and source.solution_and_true_residual_committed is False
        and type(source.candidate_scale_required) is bool
        and source.candidate_scale_metrics_attempted == source.candidate_scale_required
        and source.candidate_scale_metrics_valid == source.candidate_scale_required
        and preparation.candidate_vector_valid == active_candidate
        and (
            (active_candidate and type(preparation.trial_x) is np.ndarray)
            or (not active_candidate and preparation.trial_x is None)
        )
    )
    if not base_valid:
        return False

    if source.candidate_scale_required:
        return (
            active_candidate
            and planned
            and source.dual_gate_evaluated is True
            and source.dual_gate_passed is False
            and source.invariant_breakdown is False
            and source.divergence_evaluated is True
            and source.divergence_detected is False
            and _candidate_scale_reduction_valid(
                source.trial_x_l2,
                operation="lassq_l2",
                value_count=source.candidate_l2.value_count,
            )
            and _candidate_scale_reduction_valid(
                source.committed_x_l2,
                operation="lassq_l2",
                value_count=source.candidate_l2.value_count,
            )
            and source.trial_x_reduction_valid_mask
            == _FGMRES_GPU_TREE_CANDIDATE_RESIDUAL_MASK
            | _FGMRES_GPU_TREE_TRIAL_X_L2_BIT
            and source.reduction_valid_mask
            == _FGMRES_GPU_TREE_CANDIDATE_RESIDUAL_MASK
            | _FGMRES_GPU_TREE_TRIAL_X_L2_BIT
            | _FGMRES_GPU_TREE_COMMITTED_X_L2_BIT
        )

    if source.trial_x_l2 is not None or source.committed_x_l2 is not None:
        return False
    if source.trial_x_reduction_valid_mask is not None:
        return False
    expected_mask = _FGMRES_GPU_TREE_CANDIDATE_RESIDUAL_MASK if active_candidate else 0
    if source.reduction_valid_mask != expected_mask:
        return False
    if not active_candidate or not planned:
        return (
            source.dual_gate_evaluated is False
            and source.scaled_candidate_residual_linf is None
            and source.solver_l2_passed is None
            and source.authoritative_linf_passed is None
            and source.dual_gate_passed is None
            and source.divergence_evaluated is False
            and source.divergence_threshold_l2 is None
            and source.divergence_detected is None
        )
    return (
        source.dual_gate_evaluated is True
        and type(source.scaled_candidate_residual_linf) is float
        and type(source.solver_l2_passed) is bool
        and type(source.authoritative_linf_passed) is bool
        and type(source.dual_gate_passed) is bool
        and (
            source.dual_gate_passed
            or source.invariant_breakdown
            or (
                source.divergence_evaluated is True
                and type(source.divergence_threshold_l2) is float
                and source.divergence_detected is True
            )
        )
    )


def _checkpoint_transaction_policy_matches_source(
    source: FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2,
    *,
    scaled_candidate_residual_linf: float | None,
    solver_l2_passed: bool | None,
    authoritative_linf_passed: bool | None,
    dual_gate_passed: bool | None,
    divergence_evaluated: bool,
    divergence_threshold_l2: float | None,
    divergence_detected: bool | None,
) -> bool:
    active_candidate = (
        source.candidate_required
        and not source.triangular_breakdown
        and source.candidate_replay_valid
    )
    if not active_candidate or not source.planned_cycle_end:
        return True
    return (
        source.dual_gate_evaluated is True
        and source.scaled_candidate_residual_linf == scaled_candidate_residual_linf
        and source.solver_l2_passed is solver_l2_passed
        and source.authoritative_linf_passed is authoritative_linf_passed
        and source.dual_gate_passed is dual_gate_passed
        and source.divergence_evaluated is divergence_evaluated
        and source.divergence_threshold_l2 == divergence_threshold_l2
        and source.divergence_detected is divergence_detected
    )


def _checkpoint_transaction_vector_size(
    source: FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2,
) -> int:
    vector = source.candidate_residual.candidate_preparation.through_givens.first_column.basis_v0
    if type(vector) is not np.ndarray or vector.ndim != 1 or vector.size == 0:
        _fail(
            "fgmres_gpu_tree_checkpoint_transaction_source_state_invalid",
            "/candidate_scale_metrics",
        )
    return int(vector.size)


def _checkpoint_stagnation_relative_tolerance(value: Any) -> float:
    converted = _nonnegative_float64(value, "/stagnation_relative_tolerance")
    if converted <= 0.0 or converted >= 1.0:
        _fail(
            "fgmres_gpu_tree_checkpoint_stagnation_relative_tolerance_invalid",
            "/stagnation_relative_tolerance",
        )
    return converted


def _checkpoint_stagnation_limit(value: Any) -> int:
    if type(value) is not int or not 2 <= value <= 16:
        _fail(
            "fgmres_gpu_tree_checkpoint_stagnation_limit_invalid",
            "/stagnation_checkpoint_limit",
        )
    return value


def _checkpoint_counter(value: Any, path: str, *, maximum: int = 4096) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail("fgmres_gpu_tree_checkpoint_counter_invalid", path)
    return value


def _finite_vector_preserve_zero(values: Any, path: str) -> np.ndarray:
    try:
        raw = np.asarray(values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FgmresGpuTreeReferenceV2Error(
            "fgmres_gpu_tree_vector_type_invalid",
            path,
        ) from exc
    if raw.ndim != 1 or raw.dtype.kind not in "fiu" or raw.dtype.kind == "b":
        _fail("fgmres_gpu_tree_vector_type_invalid", path)
    vector = np.ascontiguousarray(raw, dtype="<f8")
    if vector.ndim != 1 or vector.size == 0:
        _fail("fgmres_gpu_tree_vector_shape_invalid", path)
    if not np.isfinite(vector).all():
        _fail("fgmres_gpu_tree_vector_nonfinite", path)
    return vector.copy()


def _immutable_f64_preserve_zero(values: np.ndarray) -> np.ndarray:
    return np.frombuffer(
        bytes(np.ascontiguousarray(values, dtype="<f8").tobytes()),
        dtype="<f8",
    )


def _immutable_f64(values: np.ndarray) -> np.ndarray:
    return np.frombuffer(
        bytes(np.ascontiguousarray(values, dtype="<f8").tobytes()), dtype="<f8"
    )


def _exact_zero(value: float) -> float:
    return 0.0 if value == 0.0 else float(value)


def _fail(code: str, path: str, message: str = "") -> None:
    raise FgmresGpuTreeReferenceV2Error(code, path, message)


__all__ = [
    "FGMRES_GPU_TREE_MAX_ITERATIONS",
    "FGMRES_GPU_TREE_REFERENCE_V2_VERSION",
    "FGMRES_GPU_TREE_THREADS_PER_BLOCK",
    "FGMRES_GPU_TREE_VALUES_PER_BLOCK",
    "FgmresGpuTreeFirstArnoldiColumnReplayV2",
    "FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2",
    "FgmresGpuTreeFirstColumnCandidatePreparationV2",
    "FgmresGpuTreeFirstColumnCandidateResidualReplayV2",
    "FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2",
    "FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2",
    "FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2",
    "FgmresGpuTreeInitialReplayV2",
    "FgmresGpuTreeReductionV2",
    "FgmresGpuTreeReferenceV2Error",
    "fgmres_gpu_tree_dot_v2",
    "fgmres_gpu_tree_l2_v2",
    "fgmres_gpu_tree_linf_v2",
    "prepare_fgmres_gpu_tree_first_column_candidate_residual_v2",
    "prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2",
    "prepare_fgmres_gpu_tree_first_column_candidate_v2",
    "prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2",
    "replay_fgmres_gpu_tree_first_arnoldi_column_v2",
    "replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2",
    "replay_fgmres_gpu_tree_first_column_candidate_preparation_v2",
    "replay_fgmres_gpu_tree_first_column_candidate_residual_v2",
    "replay_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2",
    "replay_fgmres_gpu_tree_first_column_checkpoint_transaction_v2",
    "replay_fgmres_gpu_tree_initial_v2",
]
