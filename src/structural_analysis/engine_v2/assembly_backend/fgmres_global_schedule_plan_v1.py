"""Immutable fixed-program schedule for the HIP FGMRES recurrence-v2 ABI.

The legacy recurrence planner stops after restart one, column zero.  This
module expands the same launch grammar without executing it: the initial
prefix is followed by every one of the ``R * M`` column slots, including the
iteration-budget padding slots, and by one final guard when ``I > 0``.

No live convergence state is accepted by this planner.  Conditional work is
therefore represented only by ``device_gate_source`` metadata; it can never
change the host submission tuple.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_plan import (
    HIP_FGMRES_MAX_ITERATIONS,
    HIP_FGMRES_MAX_RESTART_DIMENSION,
    HIP_FGMRES_REDUCTION_SEGMENT_SIZE,
)


HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-global-schedule-plan.v1"
)
HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_CAPABILITY_PROFILE_V1 = (
    "phase0_hip_fgmres_fixed_global_recurrence_schedule_plan"
)
HIP_FGMRES_GLOBAL_SCHEDULE_SEGMENT_HASH_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-global-schedule-segment-hash.v1"
)

_INT32_MAX = (1 << 31) - 1

_CONTROL_SYMBOL = "engine_v2_fgmres_control_v2"
_VECTOR_SYMBOL = "engine_v2_fgmres_vector_v2"
_SPMV_SYMBOL = "engine_v2_fgmres_csr_spmv_indexed_v2"
_REDUCE_SYMBOL = "engine_v2_fgmres_reduce_v2"

_CONTROL = {
    "INIT": 0,
    "BIND_RHS": 1,
    "INITIAL_GATE": 2,
    "RESTART_BEGIN": 3,
    "PRECONDITION_ACCEPT": 4,
    "OPERATOR_ACCEPT": 5,
    "DOT_ACCEPT": 6,
    "DGKS_DECIDE": 7,
    "ARNOLDI_GIVENS": 8,
    "BACKSUBSTITUTE": 9,
    "VECTOR_ACCEPT": 10,
    "CHECKPOINT_DECIDE": 11,
    "CHECKPOINT_FINALIZE": 12,
    "FINAL_GUARD": 13,
    "PREDECESSOR_VALIDATE": 14,
}
_VECTOR = {
    "COPY_INITIAL_X": 0,
    "FORM_INITIAL_RESIDUAL": 1,
    "APPLY_JACOBI_INDEXED": 2,
    "MGS_SUBTRACT_INDEXED": 3,
    "NORMALIZE_V0": 4,
    "NORMALIZE_V_NEXT": 5,
    "BUILD_TRIAL_X": 6,
    "FORM_CANDIDATE_RESIDUAL": 7,
    "COMMIT_CHECKPOINT": 8,
    "PREFLIGHT_COMMIT_SOURCE": 9,
}
_VECTOR_GATE = {
    "ACTIVE": 0,
    "DGKS_SECOND_PASS": 1,
    "CANDIDATE_REQUIRED": 2,
    "CYCLE_END": 3,
    "COMMIT_REQUIRED": 4,
}
_SPMV = {"INITIAL": 0, "ARNOLDI": 1, "CANDIDATE": 2}
_REDUCTION = {
    "DOT_W_VI": 0,
    "LASSQ_LOAD": 1,
    "LASSQ_TRUE_RESIDUAL": 2,
    "LASSQ_WORK_W": 3,
    "LASSQ_V_M": 4,
    "LASSQ_WORK_W_MINUS_X": 5,
    "LASSQ_SOLUTION_X": 6,
    "LINF_LOAD": 7,
    "LINF_TRUE_RESIDUAL": 8,
    "LINF_V_M": 9,
    "COMBINE_SUM": 10,
    "COMBINE_LASSQ": 11,
    "COMBINE_MAX": 12,
}
_TARGET = {
    "NONE": 0,
    "DOT": 1,
    "RHS_L2": 2,
    "RHS_LINF": 3,
    "INITIAL_L2": 4,
    "INITIAL_LINF": 5,
    "WORK_BEFORE": 6,
    "AFTER_FIRST": 7,
    "H_NEXT": 8,
    "CANDIDATE_L2": 9,
    "CANDIDATE_LINF": 10,
    "UPDATE_L2": 11,
    "COMMITTED_X_L2": 12,
    "TRIAL_X_L2": 13,
}


class HipFgmresGlobalSchedulePlanV1Error(ValueError):
    """Raised when a fixed global schedule cannot be represented exactly."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def hip_fgmres_global_schedule_contract_payload_v1() -> dict[str, Any]:
    """Return the dimension-independent fixed-program recurrence contract.

    This payload is embedded in the recurrence kernel interface identity.  It
    intentionally distinguishes the host's immutable submission coordinates
    from the device epochs retained after an earlier terminal transition.
    """

    return {
        "schema_version": HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_SCHEMA_VERSION_V1,
        "capability_profile": HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_CAPABILITY_PROFILE_V1,
        "dimension_domain": {
            "free_dof_count": "1..INT32_MAX",
            "restart_dimension_M": f"1..{HIP_FGMRES_MAX_RESTART_DIMENSION}",
            "max_iterations_I": f"0..{HIP_FGMRES_MAX_ITERATIONS}",
            "maximum_restart_count_R": "0_if_I=0_else_ceil(I/M)",
        },
        "fixed_host_program": {
            "rows": "initial_prefix + R*(restart_preamble + M*column) + guard_if_I>0",
            "live_convergence_host_branching": False,
            "all_R_times_M_column_slots_submitted": True,
            "final_guard_submitted_iff_I_positive": True,
            "predecessor_validate_before_every_checkpoint": True,
            "checkpoint_rows": [
                "PREDECESSOR_VALIDATE",
                "CHECKPOINT_DECIDE",
                "PREFLIGHT_COMMIT_SOURCE",
                "COMMIT_CHECKPOINT",
                "CHECKPOINT_FINALIZE",
            ],
        },
        "epoch_formulas": {
            "S": "recursive_stage_count(F,ceil(value_count/512))",
            "initial_schedule_end_B": "7+4*S",
            "initial_reduction_end": "4*S",
            "column_schedule_stride_L_j": "20+4*j+(10+2*j)*S",
            "column_reduction_stride": "(10+2*j)*S",
            "restart_schedule_stride_D": "2+2*M^2+18*M+(M^2+9*M)*S",
            "restart_reduction_stride_H": "(M^2+9*M)*S",
            "restart_schedule_base_B_r": "B+(r-1)*D",
            "restart_reduction_base_Q_r": "4*S+(r-1)*H",
            "column_schedule_base_C_rj": ("B_r+2+2*j^2+18*j+(j^2+9*j)*S"),
            "column_reduction_base_q_rj": "Q_r+(j^2+9*j)*S",
            "active_fallthrough_final_schedule_epoch": "B+R*D",
            "active_fallthrough_final_reduction_epoch": "4*S+R*H",
            "first_column_checkpoint_end": "E=29+14*S,Q=14*S",
        },
        "column_numeric_order": {
            "first_mgs_rows": "0..j_inclusive",
            "second_mgs_rows": "0..j_inclusive_always_submitted",
            "dgks_second_pass_gate": "device_dgks_reorth_required",
            "prior_givens_rows": "0..j-1_in_order",
            "new_givens_row": "j",
            "jacobi_and_arnoldi_basis_index": "j",
            "next_basis_index": "j+1",
            "candidate_scratch_basis_index": "M",
            "column_scoped_noncandidate_logical_index": "j",
            "dense_state_reset_at_every_restart": True,
            "next_restart_beta_source": "committed_true_residual_l2",
        },
        "counter_contract": {
            "effective_iterations_after_givens": "cycle_start+j+1",
            "effective_arnoldi_dimension_after_givens": "j+1",
            "preconditioner_apply_count_after_accept": "cycle_start+j+1",
            "operator_apply_count_before_arnoldi": (
                "1+cycle_start+j+(r-1)+false_convergence_count"
            ),
            "operator_apply_count_after_arnoldi": "before_arnoldi+1",
            "candidate_operator_addend": (
                "1_iff_candidate_required_and_not_triangular_breakdown"
            ),
        },
        "terminal_padding_contract": {
            "inactive_launches_preserve_all_device_bytes": True,
            "inactive_launches_preserve_schedule_epoch": True,
            "inactive_launches_preserve_reduction_epoch": True,
            "inactive_launches_read_no_numeric_or_CSR_or_dense_inputs": True,
            "host_submission_coordinates_continue_to_fixed_endpoint": True,
            "host_program_endpoint_is_not_a_terminal_device_epoch_claim": True,
        },
        "final_guard_contract": {
            "mode": "FINAL_GUARD",
            "coordinates": "r=R,column=M-1,row=-1,pass=-1",
            "inactive_behavior": "byte_preserving_no_op",
            "active_required_endpoint": "E=B+R*D,Q=4*S+R*H",
            "active_required_history": (
                "effective_iterations=I,effective_restarts=R,exact_final_restart_row"
            ),
            "active_required_prestate": (
                "phase=arnoldi,status=not_terminal,code=none,all_action_and_pending_fields_clear"
            ),
            "active_handoff_condition": (
                "plain_max_iterations_after_exact_full_final_cycle_I_equals_R_times_M"
            ),
            "checkpoint_finalize_handoff": (
                "commit_candidate_and_final_restart_row_clear_transients_preserve_active_arnoldi"
            ),
            "handoff_postcondition_revalidated_before_guard": True,
            "partial_final_cycle_behavior": (
                "checkpoint_finalize_publishes_max_iterations_before_inactive_guard"
            ),
            "priority_before_handoff": (
                "converged_breakdown_diverged_stagnated_publish_at_checkpoint_finalize"
            ),
            "active_valid_behavior": "claim_one_schedule_epoch_and_publish_max_iterations",
            "active_malformed_behavior": "fail_closed_code_47",
            "absent_when_I_zero": True,
        },
        "complexity_boundary": {
            "restart_dimension_is_compile_time_bounded": True,
            "per_column_vector_and_sparse_operator_work": "O(F+nnz)",
            "per_iteration_host_device_copy": 0,
            "per_iteration_host_synchronization": 0,
            "full_solver_owner_or_parity_implied_by_schedule_alone": False,
        },
    }


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalScheduleLaunchV1:
    """One immutable host submission in the full fixed recurrence program."""

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None = None
    row_index: int | None = None
    pass_index: int | None = None
    vector_gate: int | None = None
    reduction_target: int | None = None
    expected_reduction_epoch: int | None = None
    value_count: int | None = None
    output_count: int | None = None
    final_stage: bool | None = None
    device_gate_source: str | None = None
    reduction_tree_id: str | None = None
    schedule_epoch_advance: int = 1
    reduction_epoch_advance: int = 0

    def legacy_projection(self) -> dict[str, Any]:
        """Return fields shared with the sealed column-zero launch objects."""

        return {
            "name": self.name,
            "submission_kind": self.submission_kind,
            "kernel_symbol": self.kernel_symbol,
            "mode": self.mode,
            "expected_schedule_epoch": self.expected_schedule_epoch,
            "expected_restart": self.expected_restart,
            "expected_column": self.expected_column,
            "logical_index": self.logical_index,
            "row_index": self.row_index,
            "pass_index": self.pass_index,
            "vector_gate": self.vector_gate,
            "reduction_target": self.reduction_target,
            "expected_reduction_epoch": self.expected_reduction_epoch,
            "value_count": self.value_count,
            "output_count": self.output_count,
            "final_stage": self.final_stage,
            "device_gate_source": self.device_gate_source,
            "reduction_tree_id": self.reduction_tree_id,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalColumnScheduleV1:
    """All launches for one always-submitted restart/column slot."""

    restart_index: int
    column_index: int
    global_iteration_slot: int
    within_iteration_budget: bool
    schedule_base: int
    reduction_base: int
    schedule_stride: int
    reduction_stride: int
    launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...]

    @property
    def predecessor_launches(self) -> tuple[HipFgmresGlobalScheduleLaunchV1, ...]:
        """Return the numerical slice through its non-advancing validator."""

        return self.launches[:-4]

    @property
    def checkpoint_launches(self) -> tuple[HipFgmresGlobalScheduleLaunchV1, ...]:
        """Return decide, preflight, commit, and finalize."""

        return self.launches[-4:]


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalRestartScheduleV1:
    """The two-launch restart prefix and all ``M`` column slots."""

    restart_index: int
    cycle_width: int
    schedule_base: int
    reduction_base: int
    schedule_stride: int
    reduction_stride: int
    preamble_launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...]
    columns: tuple[HipFgmresGlobalColumnScheduleV1, ...]

    @property
    def launches(self) -> tuple[HipFgmresGlobalScheduleLaunchV1, ...]:
        return self.preamble_launches + tuple(
            row for column in self.columns for row in column.launches
        )


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalSchedulePlanV1:
    """Pure, immutable expansion of the recurrence-v2 fixed host program."""

    schema_version: str
    capability_profile: str
    free_dof_count: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    reduction_stage_outputs: tuple[int, ...]
    reduction_stage_count: int
    initial_schedule_end: int
    initial_reduction_end: int
    restart_schedule_stride: int
    restart_reduction_stride: int
    final_schedule_epoch: int
    final_reduction_epoch: int
    schedule_end_epoch: int
    initial_launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...]
    restarts: tuple[HipFgmresGlobalRestartScheduleV1, ...]
    final_guard_launch: HipFgmresGlobalScheduleLaunchV1 | None

    @property
    def columns(self) -> tuple[HipFgmresGlobalColumnScheduleV1, ...]:
        return tuple(column for restart in self.restarts for column in restart.columns)

    @property
    def launches(self) -> tuple[HipFgmresGlobalScheduleLaunchV1, ...]:
        rows = self.initial_launches + tuple(
            row for restart in self.restarts for row in restart.launches
        )
        if self.final_guard_launch is not None:
            rows += (self.final_guard_launch,)
        return rows


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalScheduleSegmentV1:
    """One canonical, index-addressed slice of the immutable host program."""

    segment_kind: Literal["full", "sealed_prefix", "continuation"]
    launch_start_index: int
    launch_end_index: int
    launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...]
    canonical_sha256: str

    @property
    def launch_count(self) -> int:
        return self.launch_end_index - self.launch_start_index


@dataclass(frozen=True, slots=True)
class HipFgmresGlobalSealedContinuationV1:
    """Fail-closed partition after the sealed restart-one/column-zero commit.

    ``sealed_prefix`` is exactly the work already owned by the canonical
    predecessor plus sealed four-launch checkpoint transaction.  A continuation
    owner must submit only ``continuation.launches``; submitting ``full`` would
    replay consumed epochs and authority.
    """

    plan: HipFgmresGlobalSchedulePlanV1
    full: HipFgmresGlobalScheduleSegmentV1
    sealed_prefix: HipFgmresGlobalScheduleSegmentV1
    continuation: HipFgmresGlobalScheduleSegmentV1


def compile_hip_fgmres_global_sealed_continuation_v1(
    free_dof_count: int,
    restart_dimension: int,
    max_iterations: int,
) -> HipFgmresGlobalSealedContinuationV1:
    """Compile and partition the global program after its sealed first column.

    An initial-only (``I == 0``) program has no sealed first-column checkpoint,
    so it cannot issue this continuation shape.  That case raises instead of
    accidentally returning the initial prefix as continuation work.
    """

    plan = compile_hip_fgmres_global_schedule_plan_v1(
        free_dof_count,
        restart_dimension,
        max_iterations,
    )
    if plan.max_iterations == 0:
        raise HipFgmresGlobalSchedulePlanV1Error(
            "hip_fgmres_global_schedule_sealed_continuation_unavailable",
            "A sealed continuation requires max_iterations to be positive.",
        )

    first_restart = plan.restarts[0]
    first_column = first_restart.columns[0]
    full_launches = plan.launches
    sealed_prefix_launches = (
        plan.initial_launches + first_restart.preamble_launches + first_column.launches
    )
    prefix_end = len(sealed_prefix_launches)
    continuation_launches = full_launches[prefix_end:]

    result = HipFgmresGlobalSealedContinuationV1(
        plan=plan,
        full=_schedule_segment(
            plan=plan,
            segment_kind="full",
            launch_start_index=0,
            launches=full_launches,
        ),
        sealed_prefix=_schedule_segment(
            plan=plan,
            segment_kind="sealed_prefix",
            launch_start_index=0,
            launches=sealed_prefix_launches,
        ),
        continuation=_schedule_segment(
            plan=plan,
            segment_kind="continuation",
            launch_start_index=prefix_end,
            launches=continuation_launches,
        ),
    )
    _audit_sealed_continuation(result)
    return result


def compile_hip_fgmres_global_schedule_plan_v1(
    free_dof_count: int,
    restart_dimension: int,
    max_iterations: int,
) -> HipFgmresGlobalSchedulePlanV1:
    """Expand the exact ``initial + R*M columns + guard`` host schedule."""

    n = _bounded_int(
        free_dof_count,
        "free_dof_count",
        minimum=1,
        maximum=_INT32_MAX,
    )
    restart = _bounded_int(
        restart_dimension,
        "restart_dimension",
        minimum=1,
        maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
    )
    iterations = _bounded_int(
        max_iterations,
        "max_iterations",
        minimum=0,
        maximum=HIP_FGMRES_MAX_ITERATIONS,
    )
    maximum_restarts = (iterations + restart - 1) // restart if iterations > 0 else 0
    stage_outputs = _reduction_stage_output_counts(n)
    stages = len(stage_outputs)
    initial_schedule_end = 7 + 4 * stages
    initial_reduction_end = 4 * stages
    restart_schedule_stride = (
        2
        + 2 * restart * restart
        + 18 * restart
        + (restart * restart + 9 * restart) * stages
    )
    restart_reduction_stride = (restart * restart + 9 * restart) * stages
    initial_launches = _initial_launches(n, stage_outputs)
    restarts = tuple(
        _restart_schedule(
            n=n,
            restart_dimension=restart,
            max_iterations=iterations,
            restart_index=restart_index,
            stage_outputs=stage_outputs,
            initial_schedule_end=initial_schedule_end,
            initial_reduction_end=initial_reduction_end,
            schedule_stride=restart_schedule_stride,
            reduction_stride=restart_reduction_stride,
        )
        for restart_index in range(1, maximum_restarts + 1)
    )
    final_schedule_epoch = (
        initial_schedule_end + maximum_restarts * restart_schedule_stride
    )
    final_reduction_epoch = (
        initial_reduction_end + maximum_restarts * restart_reduction_stride
    )
    final_guard = None
    if iterations > 0:
        final_guard = _control_launch(
            "FINAL_GUARD",
            "FINAL_GUARD",
            final_schedule_epoch,
            maximum_restarts,
            restart - 1,
            expected_reduction_epoch=final_reduction_epoch,
            device_gate_source="active_after_fixed_program",
        )
    plan = HipFgmresGlobalSchedulePlanV1(
        schema_version=HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_CAPABILITY_PROFILE_V1,
        free_dof_count=n,
        restart_dimension=restart,
        max_iterations=iterations,
        maximum_restart_count=maximum_restarts,
        reduction_stage_outputs=stage_outputs,
        reduction_stage_count=stages,
        initial_schedule_end=initial_schedule_end,
        initial_reduction_end=initial_reduction_end,
        restart_schedule_stride=restart_schedule_stride,
        restart_reduction_stride=restart_reduction_stride,
        final_schedule_epoch=final_schedule_epoch,
        final_reduction_epoch=final_reduction_epoch,
        schedule_end_epoch=final_schedule_epoch + (1 if final_guard else 0),
        initial_launches=initial_launches,
        restarts=restarts,
        final_guard_launch=final_guard,
    )
    _audit_plan(plan)
    return plan


def _initial_launches(
    n: int,
    stage_outputs: tuple[int, ...],
) -> tuple[HipFgmresGlobalScheduleLaunchV1, ...]:
    stages = len(stage_outputs)
    rows: list[HipFgmresGlobalScheduleLaunchV1] = [
        _control_launch("CONTROL_INIT", "INIT", 0, -1, -1),
        _vector_launch(
            "COPY_INITIAL_X", "COPY_INITIAL_X", "ACTIVE", 1, -1, -1, 0, "active"
        ),
    ]
    q = 0
    for metric, first_mode, combine_mode, target in (
        ("rhs_l2", "LASSQ_LOAD", "COMBINE_LASSQ", "RHS_L2"),
        ("rhs_linf", "LINF_LOAD", "COMBINE_MAX", "RHS_LINF"),
    ):
        q = _append_reduction_tree(
            rows,
            name_factory=lambda stage, metric=metric: (
                f"REDUCE_{metric.upper()}_{stage}"
            ),
            tree_id=f"initial:{metric}",
            n=n,
            stage_outputs=stage_outputs,
            schedule_base=2 + q,
            reduction_base=q,
            first_mode=first_mode,
            combine_mode=combine_mode,
            target=target,
            expected_restart=-1,
            expected_column=-1,
            logical_index=0,
            device_gate_source=None,
        )
    rows.extend(
        (
            _control_launch("CONTROL_BIND_RHS", "BIND_RHS", 2 + 2 * stages, -1, -1),
            _spmv_launch(
                "SPMV_INITIAL", "INITIAL", 3 + 2 * stages, -1, -1, 0, "active"
            ),
            _control_launch(
                "CONTROL_OPERATOR_ACCEPT_INITIAL",
                "OPERATOR_ACCEPT",
                4 + 2 * stages,
                -1,
                -1,
            ),
            _vector_launch(
                "FORM_INITIAL_RESIDUAL",
                "FORM_INITIAL_RESIDUAL",
                "ACTIVE",
                5 + 2 * stages,
                -1,
                -1,
                0,
                "active",
            ),
        )
    )
    for metric, first_mode, combine_mode, target in (
        ("initial_l2", "LASSQ_TRUE_RESIDUAL", "COMBINE_LASSQ", "INITIAL_L2"),
        ("initial_linf", "LINF_TRUE_RESIDUAL", "COMBINE_MAX", "INITIAL_LINF"),
    ):
        q = _append_reduction_tree(
            rows,
            name_factory=lambda stage, metric=metric: (
                f"REDUCE_{metric.upper()}_{stage}"
            ),
            tree_id=f"initial:{metric}",
            n=n,
            stage_outputs=stage_outputs,
            schedule_base=6 + q,
            reduction_base=q,
            first_mode=first_mode,
            combine_mode=combine_mode,
            target=target,
            expected_restart=-1,
            expected_column=-1,
            logical_index=0,
            device_gate_source=None,
        )
    rows.append(
        _control_launch("CONTROL_INITIAL_GATE", "INITIAL_GATE", 6 + 4 * stages, -1, -1)
    )
    return tuple(rows)


def _restart_schedule(
    *,
    n: int,
    restart_dimension: int,
    max_iterations: int,
    restart_index: int,
    stage_outputs: tuple[int, ...],
    initial_schedule_end: int,
    initial_reduction_end: int,
    schedule_stride: int,
    reduction_stride: int,
) -> HipFgmresGlobalRestartScheduleV1:
    schedule_base = initial_schedule_end + (restart_index - 1) * schedule_stride
    reduction_base = initial_reduction_end + (restart_index - 1) * reduction_stride
    cycle_width = min(
        restart_dimension,
        max(0, max_iterations - (restart_index - 1) * restart_dimension),
    )
    restart_label = "COLUMN0" if restart_index == 1 else f"RESTART{restart_index}"
    preamble = (
        _control_launch(
            f"RESTART_BEGIN_{restart_label}",
            "RESTART_BEGIN",
            schedule_base,
            restart_index,
            -1,
        ),
        _vector_launch(
            "NORMALIZE_V0"
            if restart_index == 1
            else f"NORMALIZE_V0_RESTART{restart_index}",
            "NORMALIZE_V0",
            "ACTIVE",
            schedule_base + 1,
            restart_index,
            0,
            0,
            "active",
        ),
    )
    columns = tuple(
        _column_schedule(
            n=n,
            restart_dimension=restart_dimension,
            restart_index=restart_index,
            column_index=column_index,
            max_iterations=max_iterations,
            stage_outputs=stage_outputs,
            restart_schedule_base=schedule_base,
            restart_reduction_base=reduction_base,
        )
        for column_index in range(restart_dimension)
    )
    return HipFgmresGlobalRestartScheduleV1(
        restart_index=restart_index,
        cycle_width=cycle_width,
        schedule_base=schedule_base,
        reduction_base=reduction_base,
        schedule_stride=schedule_stride,
        reduction_stride=reduction_stride,
        preamble_launches=preamble,
        columns=columns,
    )


def _column_schedule(
    *,
    n: int,
    restart_dimension: int,
    restart_index: int,
    column_index: int,
    max_iterations: int,
    stage_outputs: tuple[int, ...],
    restart_schedule_base: int,
    restart_reduction_base: int,
) -> HipFgmresGlobalColumnScheduleV1:
    stages = len(stage_outputs)
    column = column_index
    schedule_base = (
        restart_schedule_base
        + 2
        + 2 * column * column
        + 18 * column
        + (column * column + 9 * column) * stages
    )
    reduction_base = restart_reduction_base + (column * column + 9 * column) * stages
    schedule_stride = 20 + 4 * column + (10 + 2 * column) * stages
    reduction_stride = (10 + 2 * column) * stages
    legacy = restart_index == 1 and column == 0
    coord = f"RESTART{restart_index}_COLUMN{column}"
    suffix = "COLUMN0" if legacy else coord
    rows: list[HipFgmresGlobalScheduleLaunchV1] = [
        _vector_launch(
            f"APPLY_JACOBI_{suffix}",
            "APPLY_JACOBI_INDEXED",
            "ACTIVE",
            schedule_base,
            restart_index,
            column,
            column,
            "active",
        ),
        _control_launch(
            f"PRECONDITION_ACCEPT_{suffix}",
            "PRECONDITION_ACCEPT",
            schedule_base + 1,
            restart_index,
            column,
        ),
        _spmv_launch(
            f"SPMV_ARNOLDI_{suffix}",
            "ARNOLDI",
            schedule_base + 2,
            restart_index,
            column,
            column,
            "active",
        ),
        _control_launch(
            f"OPERATOR_ACCEPT_{suffix}",
            "OPERATOR_ACCEPT",
            schedule_base + 3,
            restart_index,
            column,
        ),
    ]
    q = reduction_base
    q = _append_reduction_tree(
        rows,
        name_factory=(
            (lambda stage: f"REDUCE_WORK_BEFORE_{stage}")
            if legacy
            else (lambda stage: f"REDUCE_WORK_BEFORE_{coord}_STAGE{stage}")
        ),
        tree_id="column:work_before" if legacy else f"{coord}:work_before",
        n=n,
        stage_outputs=stage_outputs,
        schedule_base=schedule_base + 4,
        reduction_base=q,
        first_mode="LASSQ_WORK_W",
        combine_mode="COMBINE_LASSQ",
        target="WORK_BEFORE",
        expected_restart=restart_index,
        expected_column=column,
        logical_index=column,
        device_gate_source=None,
    )

    first_pass_base = schedule_base + 4 + stages
    for row_index in range(column + 1):
        row_base = first_pass_base + row_index * (stages + 2)
        q = _append_reduction_tree(
            rows,
            name_factory=(
                (
                    lambda stage, row_index=row_index: (
                        f"REDUCE_DOT_FIRST_PASS_ROW{row_index}_{stage}"
                    )
                )
                if legacy
                else (
                    lambda stage, row_index=row_index: (
                        f"REDUCE_DOT_FIRST_PASS_{coord}_ROW{row_index}_STAGE{stage}"
                    )
                )
            ),
            tree_id=(
                f"column:dot_first_pass_row{row_index}"
                if legacy
                else f"{coord}:dot_first_pass_row{row_index}"
            ),
            n=n,
            stage_outputs=stage_outputs,
            schedule_base=row_base,
            reduction_base=q,
            first_mode="DOT_W_VI",
            combine_mode="COMBINE_SUM",
            target="DOT",
            expected_restart=restart_index,
            expected_column=column,
            logical_index=row_index,
            device_gate_source=None,
        )
        rows.extend(
            (
                _control_launch(
                    (
                        "DOT_ACCEPT_COLUMN0_PASS0"
                        if legacy
                        else f"DOT_ACCEPT_{coord}_ROW{row_index}_PASS0"
                    ),
                    "DOT_ACCEPT",
                    row_base + stages,
                    restart_index,
                    column,
                    row_index=row_index,
                    pass_index=0,
                ),
                _vector_launch(
                    (
                        "MGS_SUBTRACT_COLUMN0_PASS0"
                        if legacy
                        else f"MGS_SUBTRACT_{coord}_ROW{row_index}_PASS0"
                    ),
                    "MGS_SUBTRACT_INDEXED",
                    "ACTIVE",
                    row_base + stages + 1,
                    restart_index,
                    column,
                    row_index,
                    "active",
                ),
            )
        )

    after_first_base = first_pass_base + (column + 1) * (stages + 2)
    q = _append_reduction_tree(
        rows,
        name_factory=(
            (lambda stage: f"REDUCE_AFTER_FIRST_{stage}")
            if legacy
            else (lambda stage: f"REDUCE_AFTER_FIRST_{coord}_STAGE{stage}")
        ),
        tree_id="column:after_first" if legacy else f"{coord}:after_first",
        n=n,
        stage_outputs=stage_outputs,
        schedule_base=after_first_base,
        reduction_base=q,
        first_mode="LASSQ_WORK_W",
        combine_mode="COMBINE_LASSQ",
        target="AFTER_FIRST",
        expected_restart=restart_index,
        expected_column=column,
        logical_index=column,
        device_gate_source=None,
    )
    rows.append(
        _control_launch(
            "DGKS_DECIDE_COLUMN0" if legacy else f"DGKS_DECIDE_{coord}",
            "DGKS_DECIDE",
            after_first_base + stages,
            restart_index,
            column,
            pass_index=0,
        )
    )

    second_pass_base = after_first_base + stages + 1
    for row_index in range(column + 1):
        row_base = second_pass_base + row_index * (stages + 2)
        second_name = (
            f"REDUCE_DOT_SECOND_PASS_ROW{row_index}"
            if legacy
            else f"REDUCE_DOT_SECOND_PASS_{coord}_ROW{row_index}"
        )
        q = _append_reduction_tree(
            rows,
            name_factory=lambda _stage, second_name=second_name: second_name,
            tree_id=second_name,
            n=n,
            stage_outputs=stage_outputs,
            schedule_base=row_base,
            reduction_base=q,
            first_mode="DOT_W_VI",
            combine_mode="COMBINE_SUM",
            target="DOT",
            expected_restart=restart_index,
            expected_column=column,
            logical_index=row_index,
            device_gate_source="dgks_reorth_required",
        )
        rows.extend(
            (
                _control_launch(
                    (
                        f"CONTROL_DOT_ACCEPT_ROW{row_index}_PASS1"
                        if legacy
                        else f"CONTROL_DOT_ACCEPT_{coord}_ROW{row_index}_PASS1"
                    ),
                    "DOT_ACCEPT",
                    row_base + stages,
                    restart_index,
                    column,
                    row_index=row_index,
                    pass_index=1,
                    device_gate_source="dgks_reorth_required",
                ),
                _vector_launch(
                    (
                        f"VECTOR_MGS_SUBTRACT_ROW{row_index}_PASS1"
                        if legacy
                        else f"VECTOR_MGS_SUBTRACT_{coord}_ROW{row_index}_PASS1"
                    ),
                    "MGS_SUBTRACT_INDEXED",
                    "DGKS_SECOND_PASS",
                    row_base + stages + 1,
                    restart_index,
                    column,
                    row_index,
                    "dgks_reorth_required",
                ),
            )
        )

    h_next_base = second_pass_base + (column + 1) * (stages + 2)
    h_name = "REDUCE_H_NEXT" if legacy else f"REDUCE_H_NEXT_{coord}"
    q = _append_reduction_tree(
        rows,
        name_factory=lambda _stage: h_name,
        tree_id=h_name,
        n=n,
        stage_outputs=stage_outputs,
        schedule_base=h_next_base,
        reduction_base=q,
        first_mode="LASSQ_WORK_W",
        combine_mode="COMBINE_LASSQ",
        target="H_NEXT",
        expected_restart=restart_index,
        expected_column=column,
        logical_index=column,
        device_gate_source=None,
    )
    rows.extend(
        (
            _vector_launch(
                "VECTOR_NORMALIZE_V1"
                if legacy
                else f"VECTOR_NORMALIZE_V{column + 1}_{coord}",
                "NORMALIZE_V_NEXT",
                "ACTIVE",
                h_next_base + stages,
                restart_index,
                column,
                column + 1,
                None,
            ),
            _control_launch(
                f"CONTROL_ARNOLDI_GIVENS_{suffix}",
                "ARNOLDI_GIVENS",
                h_next_base + stages + 1,
                restart_index,
                column,
                device_gate_source=None,
            ),
        )
    )

    update_base = h_next_base + stages + 4
    candidate_gate = "candidate_required_and_not_triangular_breakdown"
    rows.extend(
        (
            _control_launch(
                f"CONTROL_BACKSUBSTITUTE_{suffix}",
                "BACKSUBSTITUTE",
                update_base - 2,
                restart_index,
                column,
                device_gate_source="candidate_required",
            ),
            _vector_launch(
                f"VECTOR_BUILD_TRIAL_X_{suffix}",
                "BUILD_TRIAL_X",
                "CANDIDATE_REQUIRED",
                update_base - 1,
                restart_index,
                column,
                column,
                candidate_gate,
            ),
        )
    )
    update_name = f"REDUCE_SOLUTION_UPDATE_L2_{suffix}"
    q = _append_reduction_tree(
        rows,
        name_factory=lambda _stage: update_name,
        tree_id=update_name,
        n=n,
        stage_outputs=stage_outputs,
        schedule_base=update_base,
        reduction_base=q,
        first_mode="LASSQ_WORK_W_MINUS_X",
        combine_mode="COMBINE_LASSQ",
        target="UPDATE_L2",
        expected_restart=restart_index,
        expected_column=column,
        logical_index=column,
        device_gate_source=candidate_gate,
    )
    rows.extend(
        (
            _control_launch(
                f"CONTROL_VECTOR_ACCEPT_TRIAL_{suffix}",
                "VECTOR_ACCEPT",
                update_base + stages,
                restart_index,
                column,
                device_gate_source=candidate_gate,
            ),
            _spmv_launch(
                f"SPMV_CANDIDATE_{suffix}",
                "CANDIDATE",
                update_base + stages + 1,
                restart_index,
                column,
                restart_dimension,
                candidate_gate,
            ),
            _control_launch(
                f"CONTROL_OPERATOR_ACCEPT_CANDIDATE_{suffix}",
                "OPERATOR_ACCEPT",
                update_base + stages + 2,
                restart_index,
                column,
                device_gate_source=candidate_gate,
            ),
            _vector_launch(
                f"VECTOR_FORM_CANDIDATE_RESIDUAL_{suffix}",
                "FORM_CANDIDATE_RESIDUAL",
                "CANDIDATE_REQUIRED",
                update_base + stages + 3,
                restart_index,
                column,
                restart_dimension,
                candidate_gate,
            ),
        )
    )

    metrics_base = update_base + stages + 4
    for group, (
        stem,
        first_mode,
        combine_mode,
        target,
        logical_index,
        gate,
    ) in enumerate(
        (
            (
                "CANDIDATE_L2",
                "LASSQ_V_M",
                "COMBINE_LASSQ",
                "CANDIDATE_L2",
                restart_dimension,
                candidate_gate,
            ),
            (
                "CANDIDATE_LINF",
                "LINF_V_M",
                "COMBINE_MAX",
                "CANDIDATE_LINF",
                restart_dimension,
                candidate_gate,
            ),
            (
                "TRIAL_X_L2",
                "LASSQ_WORK_W",
                "COMBINE_LASSQ",
                "TRIAL_X_L2",
                column,
                "scale_metrics_required",
            ),
            (
                "COMMITTED_X_L2",
                "LASSQ_SOLUTION_X",
                "COMBINE_LASSQ",
                "COMMITTED_X_L2",
                column,
                "scale_metrics_required",
            ),
        )
    ):
        metric_name = f"REDUCE_{stem}_{suffix}"
        q = _append_reduction_tree(
            rows,
            name_factory=lambda _stage, metric_name=metric_name: metric_name,
            tree_id=metric_name,
            n=n,
            stage_outputs=stage_outputs,
            schedule_base=metrics_base + group * stages,
            reduction_base=q,
            first_mode=first_mode,
            combine_mode=combine_mode,
            target=target,
            expected_restart=restart_index,
            expected_column=column,
            logical_index=logical_index,
            device_gate_source=gate,
        )

    checkpoint_base = metrics_base + 4 * stages
    rows.extend(
        (
            _control_launch(
                f"PREDECESSOR_VALIDATE_{suffix}",
                "PREDECESSOR_VALIDATE",
                checkpoint_base,
                restart_index,
                column,
                expected_reduction_epoch=q,
                device_gate_source="active_checkpoint_predecessor",
                schedule_epoch_advance=0,
            ),
            _control_launch(
                f"CHECKPOINT_DECIDE_{suffix}",
                "CHECKPOINT_DECIDE",
                checkpoint_base,
                restart_index,
                column,
                expected_reduction_epoch=q,
            ),
            _vector_launch(
                f"PREFLIGHT_COMMIT_SOURCE_{suffix}",
                "PREFLIGHT_COMMIT_SOURCE",
                "COMMIT_REQUIRED",
                checkpoint_base + 1,
                restart_index,
                column,
                restart_dimension,
                "commit_required",
                expected_reduction_epoch=q,
                schedule_epoch_advance=0,
            ),
            _vector_launch(
                f"COMMIT_CHECKPOINT_{suffix}",
                "COMMIT_CHECKPOINT",
                "COMMIT_REQUIRED",
                checkpoint_base + 1,
                restart_index,
                column,
                restart_dimension,
                "commit_required",
                expected_reduction_epoch=q,
            ),
            _control_launch(
                f"CHECKPOINT_FINALIZE_{suffix}",
                "CHECKPOINT_FINALIZE",
                checkpoint_base + 2,
                restart_index,
                column,
                expected_reduction_epoch=q,
            ),
        )
    )
    if q != reduction_base + reduction_stride:
        raise _internal_error("column reduction stride is inconsistent")
    if checkpoint_base + 3 != schedule_base + schedule_stride:
        raise _internal_error("column schedule stride is inconsistent")
    if len(rows) != schedule_stride + 2:
        raise _internal_error("column physical launch count is inconsistent")
    return HipFgmresGlobalColumnScheduleV1(
        restart_index=restart_index,
        column_index=column,
        global_iteration_slot=(restart_index - 1) * restart_dimension + column,
        within_iteration_budget=(
            (restart_index - 1) * restart_dimension + column < max_iterations
        ),
        schedule_base=schedule_base,
        reduction_base=reduction_base,
        schedule_stride=schedule_stride,
        reduction_stride=reduction_stride,
        launches=tuple(rows),
    )


def _append_reduction_tree(
    rows: list[HipFgmresGlobalScheduleLaunchV1],
    *,
    name_factory: Any,
    tree_id: str,
    n: int,
    stage_outputs: tuple[int, ...],
    schedule_base: int,
    reduction_base: int,
    first_mode: str,
    combine_mode: str,
    target: str,
    expected_restart: int,
    expected_column: int,
    logical_index: int,
    device_gate_source: str | None,
) -> int:
    input_count = n
    for stage, output_count in enumerate(stage_outputs):
        final = stage == len(stage_outputs) - 1
        rows.append(
            HipFgmresGlobalScheduleLaunchV1(
                name=name_factory(stage),
                submission_kind="reduction",
                kernel_symbol=_REDUCE_SYMBOL,
                mode=_REDUCTION[first_mode if stage == 0 else combine_mode],
                expected_schedule_epoch=schedule_base + stage,
                expected_restart=expected_restart,
                expected_column=expected_column,
                logical_index=logical_index,
                reduction_target=_TARGET[target] if final else _TARGET["NONE"],
                expected_reduction_epoch=reduction_base + stage,
                value_count=input_count,
                output_count=output_count,
                final_stage=final,
                device_gate_source=device_gate_source,
                reduction_tree_id=tree_id,
                reduction_epoch_advance=1,
            )
        )
        input_count = output_count
    return reduction_base + len(stage_outputs)


def _control_launch(
    name: str,
    mode: str,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    *,
    row_index: int = -1,
    pass_index: int = -1,
    expected_reduction_epoch: int | None = None,
    device_gate_source: str | None = "always",
    schedule_epoch_advance: int = 1,
) -> HipFgmresGlobalScheduleLaunchV1:
    return HipFgmresGlobalScheduleLaunchV1(
        name=name,
        submission_kind="control",
        kernel_symbol=_CONTROL_SYMBOL,
        mode=_CONTROL[mode],
        expected_schedule_epoch=schedule_epoch,
        expected_restart=expected_restart,
        expected_column=expected_column,
        row_index=row_index,
        pass_index=pass_index,
        expected_reduction_epoch=expected_reduction_epoch,
        device_gate_source=device_gate_source,
        schedule_epoch_advance=schedule_epoch_advance,
    )


def _vector_launch(
    name: str,
    mode: str,
    gate: str,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    logical_index: int,
    device_gate_source: str | None,
    *,
    expected_reduction_epoch: int | None = None,
    schedule_epoch_advance: int = 1,
) -> HipFgmresGlobalScheduleLaunchV1:
    return HipFgmresGlobalScheduleLaunchV1(
        name=name,
        submission_kind="vector",
        kernel_symbol=_VECTOR_SYMBOL,
        mode=_VECTOR[mode],
        expected_schedule_epoch=schedule_epoch,
        expected_restart=expected_restart,
        expected_column=expected_column,
        logical_index=logical_index,
        vector_gate=_VECTOR_GATE[gate],
        expected_reduction_epoch=expected_reduction_epoch,
        device_gate_source=device_gate_source,
        schedule_epoch_advance=schedule_epoch_advance,
    )


def _spmv_launch(
    name: str,
    mode: str,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    logical_index: int,
    device_gate_source: str,
) -> HipFgmresGlobalScheduleLaunchV1:
    return HipFgmresGlobalScheduleLaunchV1(
        name=name,
        submission_kind="spmv",
        kernel_symbol=_SPMV_SYMBOL,
        mode=_SPMV[mode],
        expected_schedule_epoch=schedule_epoch,
        expected_restart=expected_restart,
        expected_column=expected_column,
        logical_index=logical_index,
        device_gate_source=device_gate_source,
    )


def _reduction_stage_output_counts(value_count: int) -> tuple[int, ...]:
    count = (value_count + HIP_FGMRES_REDUCTION_SEGMENT_SIZE - 1) // (
        HIP_FGMRES_REDUCTION_SEGMENT_SIZE
    )
    rows = [count]
    while count > 1:
        count = (count + HIP_FGMRES_REDUCTION_SEGMENT_SIZE - 1) // (
            HIP_FGMRES_REDUCTION_SEGMENT_SIZE
        )
        rows.append(count)
    return tuple(rows)


def _audit_plan(plan: HipFgmresGlobalSchedulePlanV1) -> None:
    schedule_epoch = 0
    reduction_epoch = 0
    for row in plan.launches:
        if row.expected_schedule_epoch != schedule_epoch:
            raise _internal_error(f"schedule discontinuity at {row.name}")
        if (
            row.expected_reduction_epoch is not None
            and row.expected_reduction_epoch != reduction_epoch
        ):
            raise _internal_error(f"reduction discontinuity at {row.name}")
        schedule_epoch += row.schedule_epoch_advance
        reduction_epoch += row.reduction_epoch_advance
    if schedule_epoch != plan.schedule_end_epoch:
        raise _internal_error("final schedule epoch is inconsistent")
    if reduction_epoch != plan.final_reduction_epoch:
        raise _internal_error("final reduction epoch is inconsistent")
    if len(plan.columns) != plan.maximum_restart_count * plan.restart_dimension:
        raise _internal_error("fixed R*M column cardinality is inconsistent")


def _schedule_segment(
    *,
    plan: HipFgmresGlobalSchedulePlanV1,
    segment_kind: Literal["full", "sealed_prefix", "continuation"],
    launch_start_index: int,
    launches: tuple[HipFgmresGlobalScheduleLaunchV1, ...],
) -> HipFgmresGlobalScheduleSegmentV1:
    launch_end_index = launch_start_index + len(launches)
    payload = {
        "schema_version": (HIP_FGMRES_GLOBAL_SCHEDULE_SEGMENT_HASH_SCHEMA_VERSION_V1),
        "global_schedule_schema_version": plan.schema_version,
        "global_schedule_capability_profile": plan.capability_profile,
        "dimensions": {
            "free_dof_count": plan.free_dof_count,
            "restart_dimension": plan.restart_dimension,
            "max_iterations": plan.max_iterations,
            "maximum_restart_count": plan.maximum_restart_count,
            "reduction_stage_outputs": list(plan.reduction_stage_outputs),
            "reduction_stage_count": plan.reduction_stage_count,
        },
        "program_epochs": {
            "initial_schedule_end": plan.initial_schedule_end,
            "initial_reduction_end": plan.initial_reduction_end,
            "restart_schedule_stride": plan.restart_schedule_stride,
            "restart_reduction_stride": plan.restart_reduction_stride,
            "final_schedule_epoch": plan.final_schedule_epoch,
            "final_reduction_epoch": plan.final_reduction_epoch,
            "schedule_end_epoch": plan.schedule_end_epoch,
        },
        "segment": {
            "kind": segment_kind,
            "launch_start_index": launch_start_index,
            "launch_end_index": launch_end_index,
            "launch_count": len(launches),
        },
        # ``asdict`` deliberately binds every dataclass field, including both
        # epoch advances.  A future launch-field addition therefore changes the
        # canonical identity instead of silently escaping it.
        "launches": [asdict(launch) for launch in launches],
    }
    return HipFgmresGlobalScheduleSegmentV1(
        segment_kind=segment_kind,
        launch_start_index=launch_start_index,
        launch_end_index=launch_end_index,
        launches=launches,
        canonical_sha256=canonical_hash(payload),
    )


def _audit_sealed_continuation(
    result: HipFgmresGlobalSealedContinuationV1,
) -> None:
    plan = result.plan
    if plan.max_iterations <= 0 or not plan.restarts:
        raise _internal_error("sealed continuation has no first restart")
    first_restart = plan.restarts[0]
    if not first_restart.columns:
        raise _internal_error("sealed continuation has no first column")
    first_column = first_restart.columns[0]
    expected_prefix = (
        plan.initial_launches + first_restart.preamble_launches + first_column.launches
    )
    final_guard = plan.final_guard_launch
    if final_guard is None:
        raise _internal_error("sealed continuation has no final guard")
    expected_continuation = tuple(
        launch for column in first_restart.columns[1:] for launch in column.launches
    ) + tuple(launch for restart in plan.restarts[1:] for launch in restart.launches)
    expected_continuation += (final_guard,)

    if (
        result.full.segment_kind != "full"
        or result.full.launch_start_index != 0
        or result.full.launch_end_index != len(plan.launches)
        or result.full.launches != plan.launches
    ):
        raise _internal_error("full schedule segment is inconsistent")
    if (
        result.sealed_prefix.segment_kind != "sealed_prefix"
        or result.sealed_prefix.launch_start_index != 0
        or result.sealed_prefix.launch_end_index != len(expected_prefix)
        or result.sealed_prefix.launches != expected_prefix
    ):
        raise _internal_error("sealed prefix segment is inconsistent")
    if (
        result.continuation.segment_kind != "continuation"
        or result.continuation.launch_start_index != len(expected_prefix)
        or result.continuation.launch_end_index != len(plan.launches)
        or result.continuation.launches != expected_continuation
    ):
        raise _internal_error("continuation segment is inconsistent")
    if result.sealed_prefix.launches + result.continuation.launches != plan.launches:
        raise _internal_error("sealed schedule partition has a gap or overlap")
    for segment in (result.full, result.sealed_prefix, result.continuation):
        expected = _schedule_segment(
            plan=plan,
            segment_kind=segment.segment_kind,
            launch_start_index=segment.launch_start_index,
            launches=segment.launches,
        )
        if segment != expected:
            raise _internal_error(
                f"{segment.segment_kind} segment hash is inconsistent"
            )


def _bounded_int(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise HipFgmresGlobalSchedulePlanV1Error(
            "hip_fgmres_global_schedule_dimension_invalid",
            f"{label} must be an exact integer in [{minimum}, {maximum}].",
        )
    return value


def _internal_error(message: str) -> HipFgmresGlobalSchedulePlanV1Error:
    return HipFgmresGlobalSchedulePlanV1Error(
        "hip_fgmres_global_schedule_internal_invariant_failed",
        message,
    )


__all__ = [
    "HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_SCHEMA_VERSION_V1",
    "HIP_FGMRES_GLOBAL_SCHEDULE_SEGMENT_HASH_SCHEMA_VERSION_V1",
    "HipFgmresGlobalColumnScheduleV1",
    "HipFgmresGlobalRestartScheduleV1",
    "HipFgmresGlobalScheduleLaunchV1",
    "HipFgmresGlobalSchedulePlanV1",
    "HipFgmresGlobalSchedulePlanV1Error",
    "HipFgmresGlobalScheduleSegmentV1",
    "HipFgmresGlobalSealedContinuationV1",
    "compile_hip_fgmres_global_sealed_continuation_v1",
    "compile_hip_fgmres_global_schedule_plan_v1",
    "hip_fgmres_global_schedule_contract_payload_v1",
]
