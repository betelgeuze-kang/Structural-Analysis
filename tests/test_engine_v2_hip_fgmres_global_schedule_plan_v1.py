from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, fields, replace

import pytest

import structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 as schedule_module
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_SCHEMA_VERSION_V1,
    HIP_FGMRES_GLOBAL_SCHEDULE_SEGMENT_HASH_SCHEMA_VERSION_V1,
    HipFgmresGlobalScheduleLaunchV1,
    HipFgmresGlobalSchedulePlanV1Error,
    compile_hip_fgmres_global_sealed_continuation_v1,
    compile_hip_fgmres_global_schedule_plan_v1,
    hip_fgmres_global_schedule_contract_payload_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (
    canonical_first_column_predecessor_launches_v2,
    first_column_checkpoint_transaction_launches_v2,
)


def test_global_schedule_expands_exact_formula_and_padded_iteration_slot() -> None:
    plan = compile_hip_fgmres_global_schedule_plan_v1(513, 2, 5)

    assert plan.schema_version == HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_SCHEMA_VERSION_V1
    assert (
        plan.capability_profile == HIP_FGMRES_GLOBAL_SCHEDULE_PLAN_CAPABILITY_PROFILE_V1
    )
    assert plan.reduction_stage_outputs == (2, 1)
    assert plan.reduction_stage_count == 2
    assert plan.initial_schedule_end == 7 + 4 * 2 == 15
    assert plan.initial_reduction_end == 4 * 2 == 8
    assert plan.maximum_restart_count == 3
    assert (
        plan.restart_schedule_stride == 2 + 2 * 2**2 + 18 * 2 + (2**2 + 9 * 2) * 2 == 90
    )
    assert plan.restart_reduction_stride == (2**2 + 9 * 2) * 2 == 44
    assert [restart.schedule_base for restart in plan.restarts] == [15, 105, 195]
    assert [restart.reduction_base for restart in plan.restarts] == [8, 52, 96]
    assert [restart.cycle_width for restart in plan.restarts] == [2, 2, 1]
    assert len(plan.columns) == plan.maximum_restart_count * plan.restart_dimension == 6
    assert [column.within_iteration_budget for column in plan.columns] == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert [column.schedule_stride for column in plan.restarts[0].columns] == [
        20 + 10 * 2,
        20 + 4 + 12 * 2,
    ]
    assert [column.reduction_stride for column in plan.restarts[0].columns] == [
        10 * 2,
        12 * 2,
    ]
    assert plan.final_schedule_epoch == 15 + 3 * 90 == 285
    assert plan.final_reduction_epoch == 8 + 3 * 44 == 140
    assert plan.final_guard_launch is not None
    assert plan.final_guard_launch.mode == 13
    assert plan.final_guard_launch.expected_schedule_epoch == 285
    assert plan.final_guard_launch.expected_reduction_epoch == 140
    assert plan.schedule_end_epoch == 286


@pytest.mark.parametrize("free_dof_count", (1, 513, 262_145))
def test_first_column_projection_exactly_matches_sealed_legacy_schedules(
    free_dof_count: int,
) -> None:
    plan = compile_hip_fgmres_global_schedule_plan_v1(free_dof_count, 3, 3)
    first_restart = plan.restarts[0]
    first_column = first_restart.columns[0]
    predecessor = (
        plan.initial_launches
        + first_restart.preamble_launches
        + first_column.predecessor_launches
    )

    assert [row.legacy_projection() for row in predecessor] == [
        asdict(row)
        for row in canonical_first_column_predecessor_launches_v2(free_dof_count, 3)
    ]
    legacy_transaction = []
    first_column_checkpoint_launches = first_column.checkpoint_launches
    for row in first_column_checkpoint_launches:
        assert row.expected_restart == 1
        assert row.expected_column == 0
    for row in first_column_checkpoint_transaction_launches_v2(free_dof_count, 3):
        payload = asdict(row)
        payload["reduction_tree_id"] = None
        legacy_transaction.append(payload)
    assert [
        row.legacy_projection() for row in first_column_checkpoint_launches
    ] == legacy_transaction


def test_each_column_contains_row_zero_through_j_for_both_mgs_passes() -> None:
    plan = compile_hip_fgmres_global_schedule_plan_v1(513, 4, 4)

    for column in plan.columns:
        first_accepts = [
            row
            for row in column.launches
            if row.submission_kind == "control"
            and row.mode == 6
            and row.pass_index == 0
        ]
        second_accepts = [
            row
            for row in column.launches
            if row.submission_kind == "control"
            and row.mode == 6
            and row.pass_index == 1
        ]
        first_subtracts = [
            row
            for row in column.launches
            if row.submission_kind == "vector"
            and row.mode == 3
            and row.vector_gate == 0
        ]
        second_subtracts = [
            row
            for row in column.launches
            if row.submission_kind == "vector"
            and row.mode == 3
            and row.vector_gate == 1
        ]
        expected_rows = list(range(column.column_index + 1))
        assert [row.row_index for row in first_accepts] == expected_rows
        assert [row.row_index for row in second_accepts] == expected_rows
        assert [row.logical_index for row in first_subtracts] == expected_rows
        assert [row.logical_index for row in second_subtracts] == expected_rows
        assert len(column.launches) == column.schedule_stride + 2


def test_every_column_ends_in_sealed_five_launch_checkpoint_transaction() -> None:
    plan = compile_hip_fgmres_global_schedule_plan_v1(1, 3, 4)

    for column in plan.columns:
        tail = column.launches[-5:]
        checkpoint_epoch = column.schedule_base + column.schedule_stride - 3
        assert [row.mode for row in tail] == [14, 11, 9, 8, 12]
        assert [row.submission_kind for row in tail] == [
            "control",
            "control",
            "vector",
            "vector",
            "control",
        ]
        assert [row.expected_schedule_epoch for row in tail] == [
            checkpoint_epoch,
            checkpoint_epoch,
            checkpoint_epoch + 1,
            checkpoint_epoch + 1,
            checkpoint_epoch + 2,
        ]
        assert [row.schedule_epoch_advance for row in tail] == [0, 1, 0, 1, 1]
        assert {row.expected_reduction_epoch for row in tail} == {
            column.reduction_base + column.reduction_stride
        }


def test_zero_iteration_schedule_has_initial_prefix_only_and_no_final_guard() -> None:
    plan = compile_hip_fgmres_global_schedule_plan_v1(513, 16, 0)

    assert plan.maximum_restart_count == 0
    assert plan.restarts == ()
    assert plan.columns == ()
    assert plan.final_guard_launch is None
    assert plan.final_schedule_epoch == plan.initial_schedule_end
    assert plan.final_reduction_epoch == plan.initial_reduction_end
    assert plan.schedule_end_epoch == plan.initial_schedule_end
    assert plan.launches == plan.initial_launches


def test_sealed_continuation_partitions_full_program_without_gap_or_replay() -> None:
    partition = compile_hip_fgmres_global_sealed_continuation_v1(513, 2, 5)
    plan = partition.plan
    first_restart = plan.restarts[0]
    first_column = first_restart.columns[0]

    expected_prefix = (
        plan.initial_launches + first_restart.preamble_launches + first_column.launches
    )
    expected_continuation = (
        first_restart.columns[1].launches
        + tuple(launch for restart in plan.restarts[1:] for launch in restart.launches)
        + (plan.final_guard_launch,)
    )

    assert len(partition.full.launches) == 298
    assert len(partition.sealed_prefix.launches) == 59
    assert len(partition.continuation.launches) == 239
    assert partition.full.launches == plan.launches
    assert partition.sealed_prefix.launches == expected_prefix
    assert partition.continuation.launches == expected_continuation
    assert (
        partition.sealed_prefix.launches + partition.continuation.launches
        == partition.full.launches
    )
    assert partition.sealed_prefix.launch_start_index == 0
    assert partition.sealed_prefix.launch_end_index == 59
    assert partition.continuation.launch_start_index == 59
    assert partition.continuation.launch_end_index == 298
    assert [launch.mode for launch in partition.sealed_prefix.launches[-5:]] == [
        14,
        11,
        9,
        8,
        12,
    ]
    assert partition.continuation.launches[0] == first_restart.columns[1].launches[0]
    assert partition.continuation.launches[-1] is plan.final_guard_launch


def test_single_iteration_single_column_continuation_is_guard_only() -> None:
    partition = compile_hip_fgmres_global_sealed_continuation_v1(1, 1, 1)

    assert partition.sealed_prefix.launch_count == 45
    assert partition.continuation.launch_count == 1
    assert partition.continuation.launches == (partition.plan.final_guard_launch,)
    assert partition.continuation.launches[0].name == "FINAL_GUARD"
    assert partition.continuation.launches[0].mode == 13


def test_partial_final_restart_remains_in_immutable_continuation_suffix() -> None:
    partition = compile_hip_fgmres_global_sealed_continuation_v1(513, 3, 4)
    plan = partition.plan

    assert [restart.cycle_width for restart in plan.restarts] == [3, 1]
    assert [column.within_iteration_budget for column in plan.restarts[-1].columns] == [
        True,
        False,
        False,
    ]
    for column in plan.restarts[-1].columns:
        assert all(
            launch in partition.continuation.launches for launch in column.launches
        )
    assert partition.continuation.launches[-1] is plan.final_guard_launch
    assert (
        partition.sealed_prefix.launch_count + partition.continuation.launch_count
        == partition.full.launch_count
    )


def test_zero_iteration_cannot_be_misrepresented_as_sealed_continuation() -> None:
    initial_only = compile_hip_fgmres_global_schedule_plan_v1(513, 16, 0)
    assert initial_only.launches

    with pytest.raises(HipFgmresGlobalSchedulePlanV1Error) as error:
        compile_hip_fgmres_global_sealed_continuation_v1(513, 16, 0)

    assert (
        error.value.code == "hip_fgmres_global_schedule_sealed_continuation_unavailable"
    )
    assert "positive" in error.value.message


def test_segment_hashes_are_canonical_deterministic_and_fresh() -> None:
    first = compile_hip_fgmres_global_sealed_continuation_v1(513, 2, 5)
    second = compile_hip_fgmres_global_sealed_continuation_v1(513, 2, 5)

    assert (
        HIP_FGMRES_GLOBAL_SCHEDULE_SEGMENT_HASH_SCHEMA_VERSION_V1
        == "structural-analysis-hip-fgmres-global-schedule-segment-hash.v1"
    )
    assert first == second
    assert first is not second
    assert first.full is not second.full
    assert first.sealed_prefix is not second.sealed_prefix
    assert first.continuation is not second.continuation
    assert first.full.launches is not second.full.launches
    assert first.full.canonical_sha256 == second.full.canonical_sha256
    assert first.sealed_prefix.canonical_sha256 == second.sealed_prefix.canonical_sha256
    assert first.continuation.canonical_sha256 == second.continuation.canonical_sha256
    assert first.full.canonical_sha256 == (
        "sha256:ef29ee3c39ae97a5cc7b2aef2fa1d2e3e0ed515f538f6ed4616aeb3c6caf9161"
    )
    assert first.sealed_prefix.canonical_sha256 == (
        "sha256:cc9cf20737ded502a63b25c160eb8947f25d8fef97cd2db403928ec9b713b3a2"
    )
    assert first.continuation.canonical_sha256 == (
        "sha256:5684374c333cdc8bc14cd88dc36fb8ea0dd13b3c670b37e015cf0990ac98d22f"
    )
    assert (
        len(
            {
                first.full.canonical_sha256,
                first.sealed_prefix.canonical_sha256,
                first.continuation.canonical_sha256,
            }
        )
        == 3
    )
    assert all(
        segment.canonical_sha256.startswith("sha256:")
        and len(segment.canonical_sha256) == 71
        for segment in (first.full, first.sealed_prefix, first.continuation)
    )


def test_segment_hash_binds_every_abi_relevant_launch_field() -> None:
    partition = compile_hip_fgmres_global_sealed_continuation_v1(513, 2, 5)
    baseline = partition.full
    original = baseline.launches[0]

    for field in fields(HipFgmresGlobalScheduleLaunchV1):
        value = getattr(original, field.name)
        if value is None:
            mutated_value: object = "mutated-none"
        elif isinstance(value, bool):
            mutated_value = not value
        elif isinstance(value, int):
            mutated_value = value + 1
        else:
            mutated_value = value + ":mutated"
        mutated_launch = replace(original, **{field.name: mutated_value})
        mutated_segment = schedule_module._schedule_segment(
            plan=partition.plan,
            segment_kind="full",
            launch_start_index=0,
            launches=(mutated_launch,) + baseline.launches[1:],
        )
        assert mutated_segment.canonical_sha256 != baseline.canonical_sha256, field.name


def test_sealed_continuation_segments_are_deeply_immutable() -> None:
    partition = compile_hip_fgmres_global_sealed_continuation_v1(513, 2, 5)

    with pytest.raises(FrozenInstanceError):
        partition.continuation.launch_start_index = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        partition.continuation.launches[0].mode = 999  # type: ignore[misc]


def test_global_schedule_is_deterministic_and_deeply_immutable() -> None:
    first = compile_hip_fgmres_global_schedule_plan_v1(513, 2, 5)
    second = compile_hip_fgmres_global_schedule_plan_v1(513, 2, 5)

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.max_iterations = 6  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.columns[0].column_index = 9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.launches[0].mode = 13  # type: ignore[misc]


def test_global_schedule_semantic_contract_is_fresh_and_binds_terminal_no_op() -> None:
    first = hip_fgmres_global_schedule_contract_payload_v1()
    second = hip_fgmres_global_schedule_contract_payload_v1()

    assert first == second
    assert first is not second
    assert first["fixed_host_program"] is not second["fixed_host_program"]
    assert first["epoch_formulas"] == {
        "S": "recursive_stage_count(F,ceil(value_count/512))",
        "initial_schedule_end_B": "7+4*S",
        "initial_reduction_end": "4*S",
        "column_schedule_stride_L_j": "20+4*j+(10+2*j)*S",
        "column_reduction_stride": "(10+2*j)*S",
        "restart_schedule_stride_D": "2+2*M^2+18*M+(M^2+9*M)*S",
        "restart_reduction_stride_H": "(M^2+9*M)*S",
        "restart_schedule_base_B_r": "B+(r-1)*D",
        "restart_reduction_base_Q_r": "4*S+(r-1)*H",
        "column_schedule_base_C_rj": "B_r+2+2*j^2+18*j+(j^2+9*j)*S",
        "column_reduction_base_q_rj": "Q_r+(j^2+9*j)*S",
        "active_fallthrough_final_schedule_epoch": "B+R*D",
        "active_fallthrough_final_reduction_epoch": "4*S+R*H",
        "first_column_checkpoint_end": "E=29+14*S,Q=14*S",
    }
    assert first["terminal_padding_contract"] == {
        "inactive_launches_preserve_all_device_bytes": True,
        "inactive_launches_preserve_schedule_epoch": True,
        "inactive_launches_preserve_reduction_epoch": True,
        "inactive_launches_read_no_numeric_or_CSR_or_dense_inputs": True,
        "host_submission_coordinates_continue_to_fixed_endpoint": True,
        "host_program_endpoint_is_not_a_terminal_device_epoch_claim": True,
    }
    assert first["final_guard_contract"]["inactive_behavior"] == (
        "byte_preserving_no_op"
    )
    final_guard = first["final_guard_contract"]
    assert final_guard["active_handoff_condition"] == (
        "plain_max_iterations_after_exact_full_final_cycle_I_equals_R_times_M"
    )
    assert final_guard["checkpoint_finalize_handoff"] == (
        "commit_candidate_and_final_restart_row_clear_transients_preserve_active_arnoldi"
    )
    assert final_guard["handoff_postcondition_revalidated_before_guard"] is True
    assert final_guard["partial_final_cycle_behavior"] == (
        "checkpoint_finalize_publishes_max_iterations_before_inactive_guard"
    )
    assert final_guard["priority_before_handoff"] == (
        "converged_breakdown_diverged_stagnated_publish_at_checkpoint_finalize"
    )
    assert first["complexity_boundary"]["per_iteration_host_device_copy"] == 0
    assert first["complexity_boundary"]["per_iteration_host_synchronization"] == 0
    assert not first["complexity_boundary"][
        "full_solver_owner_or_parity_implied_by_schedule_alone"
    ]

    first["fixed_host_program"]["checkpoint_rows"].append("MUTATED")
    assert "MUTATED" not in second["fixed_host_program"]["checkpoint_rows"]


@pytest.mark.parametrize(
    ("free_dof_count", "restart_dimension", "max_iterations"),
    (
        (False, 2, 5),
        (0, 2, 5),
        (1, False, 5),
        (1, 0, 5),
        (1, 17, 5),
        (1, 2, False),
        (1, 2, -1),
        (1, 2, 4097),
    ),
)
def test_global_schedule_rejects_noncanonical_dimensions(
    free_dof_count: object,
    restart_dimension: object,
    max_iterations: object,
) -> None:
    with pytest.raises(HipFgmresGlobalSchedulePlanV1Error) as error:
        compile_hip_fgmres_global_schedule_plan_v1(
            free_dof_count,  # type: ignore[arg-type]
            restart_dimension,  # type: ignore[arg-type]
            max_iterations,  # type: ignore[arg-type]
        )
    assert error.value.code == "hip_fgmres_global_schedule_dimension_invalid"
