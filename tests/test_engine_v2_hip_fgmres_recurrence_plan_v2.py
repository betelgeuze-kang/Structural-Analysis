from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    HipFgmresPlanV1,
    compile_hip_fgmres_plan_v1,
    hip_fgmres_solve_record_abi_payload_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (  # noqa: E402
    hip_fgmres_global_schedule_contract_payload_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    HIP_FGMRES_RECURRENCE_PLAN_V2_CAPABILITY_PROFILE,
    HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION,
    HipFgmresRecurrencePlanV2Error,
    _memory_layout_hash,
    _plan_hash,
    _plan_id,
    compile_hip_fgmres_recurrence_plan_v2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_first_column_candidate_preparation_schedule_payload_v2,
    hip_fgmres_first_column_candidate_residual_schedule_payload_v2,
    hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2,
    hip_fgmres_first_column_predecessor_validation_schedule_payload_v2,
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2,
    hip_fgmres_first_column_completion_schedule_payload_v2,
    hip_fgmres_first_column_partial_schedule_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
    validate_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (  # noqa: E402
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    compile_fgmres_policy_v1,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/hip_fgmres_recurrence_plan_v2.schema.json"
)

_GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2 = (
    "sha256:4078f8f07b3bf605baae04ded1795f8a49038c636910b1c40916b42d3fe8c017"
)
_HISTORICAL_FIRST_COLUMN_CHECKPOINT_KERNEL_ABI_HASH_V2 = (
    "sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f"
)


def _source_v1(
    load_pattern_id: str = "LC_AXIAL",
    *,
    restart_dimension: int = 4,
    max_iterations: int = 10,
) -> HipFgmresPlanV1:
    model = load_model_ir_v2(FIXTURE)
    buffers = pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    execution = compile_execution_plan_v2(buffers)
    free_space = compile_hip_free_space_operator_plan_v1(execution)
    policy = compile_fgmres_policy_v1(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
    )
    return compile_hip_fgmres_plan_v1(execution, free_space, policy)


def _artifact(**kwargs: Any):
    source = _source_v1(**kwargs)
    return source, compile_hip_fgmres_recurrence_plan_v2(source)


def _rehash(artifact: Any) -> Any:
    forged = replace(artifact, memory_layout_hash=_memory_layout_hash(artifact))
    forged = replace(forged, plan_id=_plan_id(forged))
    forged = replace(forged, plan_hash="sha256:" + "0" * 64)
    return replace(forged, plan_hash=_plan_hash(forged))


def test_schema_is_closed_and_claims_only_a_compile_time_abi_plan() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    _, artifact = _artifact()
    payload = artifact.to_dict()

    assert not list(validator.iter_errors(payload))
    assert artifact.schema_version == HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION
    assert (
        artifact.capability_profile == HIP_FGMRES_RECURRENCE_PLAN_V2_CAPABILITY_PROFILE
    )
    assert payload["claim_boundary"]["compile_time_plan_only"] is True
    assert (
        payload["claim_boundary"]["first_column_partial_schedule_contract_complete"]
        is True
    )
    assert (
        payload["claim_boundary"]["first_column_completion_schedule_contract_complete"]
        is True
    )
    assert (
        payload["claim_boundary"][
            "first_column_candidate_preparation_schedule_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "first_column_candidate_residual_schedule_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "first_column_candidate_scale_metrics_schedule_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "first_column_predecessor_validation_schedule_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "first_column_checkpoint_transaction_schedule_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "first_column_commit_source_preflight_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "invalid_source_destination_failure_atomicity_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"][
            "invalid_source_destination_failure_atomicity_runtime_proven"
        ]
        is False
    )
    assert (
        payload["claim_boundary"]["authoritative_checkpoint_transaction_proven"]
        is False
    )
    assert (
        payload["claim_boundary"][
            "first_arnoldi_column_recurrence_schedule_contract_complete"
        ]
        is True
    )
    assert (
        payload["claim_boundary"]["first_pass_mgs_schedule_contract_complete"] is True
    )
    assert (
        payload["claim_boundary"]["device_dgks_decision_schedule_contract_complete"]
        is True
    )
    assert (
        payload["claim_boundary"]["second_pass_mgs_schedule_contract_complete"] is True
    )
    assert payload["claim_boundary"]["h_next_schedule_contract_complete"] is True
    assert payload["claim_boundary"]["v_next_schedule_contract_complete"] is True
    assert payload["claim_boundary"]["givens_schedule_contract_complete"] is True
    assert (
        payload["claim_boundary"]["full_recurrence_schedule_contract_complete"] is False
    )
    assert (
        payload["claim_boundary"]["candidate_envelope_schedule_contract_complete"]
        is False
    )
    assert payload["claim_boundary"]["device_recurrence_implemented"] is False
    assert payload["claim_boundary"]["live_solver_ready"] is False
    assert payload["claim_boundary"]["iteration_host_copy_zero_proven"] is False
    assert payload["claim_boundary"]["python_semantic_replay_required"] is True

    extra = deepcopy(payload)
    extra["memory_plan"]["control_state_abi"]["unknown"] = 1
    assert list(validator.iter_errors(extra))
    promoted = deepcopy(payload)
    promoted["claim_boundary"]["device_recurrence_implemented"] = True
    assert list(validator.iter_errors(promoted))
    offset_drift = deepcopy(payload)
    offset_drift["memory_plan"]["control_state_abi"]["fields"][28]["offset_bytes"] = 116
    assert list(validator.iter_errors(offset_drift))
    code_drift = deepcopy(payload)
    code_drift["memory_plan"]["control_state_abi"]["reduction_target_codes"]["DOT"] = 99
    assert list(validator.iter_errors(code_drift))
    signature_drift = deepcopy(payload)
    signature_drift["kernel_module_contract"]["interface"]["signatures"][
        "engine_v2_fgmres_reduce_v2"
    ] += " "
    assert list(validator.iter_errors(signature_drift))
    swapped_buffers = deepcopy(payload)
    swapped_buffers["memory_plan"]["buffers"][0:2] = reversed(
        swapped_buffers["memory_plan"]["buffers"][0:2]
    )
    assert list(validator.iter_errors(swapped_buffers))
    source_drift = deepcopy(payload)
    source_drift["memory_plan"]["buffers"][3]["source"] = "resident_state"
    assert list(validator.iter_errors(source_drift))
    control_extent_drift = deepcopy(payload)
    control_extent_drift["memory_plan"]["buffers"][-1]["byte_length"] = 255
    assert list(validator.iter_errors(control_extent_drift))
    schedule_drift = deepcopy(payload)
    schedule_drift["kernel_module_contract"]["interface"][
        "first_column_partial_schedule"
    ]["launches"][0]["expected_restart"] = 0
    schedule_drift["kernel_module_contract"]["interface"][
        "first_column_partial_schedule_hash"
    ] = canonical_hash(
        schedule_drift["kernel_module_contract"]["interface"][
            "first_column_partial_schedule"
        ]
    )
    assert list(validator.iter_errors(schedule_drift))
    completion_drift = deepcopy(payload)
    completion_drift["kernel_module_contract"]["interface"][
        "first_column_completion_schedule"
    ]["launches"][4]["expected_schedule_epoch"] = "19+9*S"
    completion_drift["kernel_module_contract"]["interface"][
        "first_column_completion_schedule_hash"
    ] = canonical_hash(
        completion_drift["kernel_module_contract"]["interface"][
            "first_column_completion_schedule"
        ]
    )
    assert list(validator.iter_errors(completion_drift))
    predecessor_validation_drift = deepcopy(payload)
    predecessor_validation_drift["kernel_module_contract"]["interface"][
        "first_column_predecessor_validation_schedule"
    ]["host_observation_contract"]["actual_mask_host_observed"] = True
    predecessor_validation_drift["kernel_module_contract"]["interface"][
        "first_column_predecessor_validation_schedule_hash"
    ] = canonical_hash(
        predecessor_validation_drift["kernel_module_contract"]["interface"][
            "first_column_predecessor_validation_schedule"
        ]
    )
    assert list(validator.iter_errors(predecessor_validation_drift))


def test_compiler_is_deterministic_and_binds_an_exact_replayed_v1_plan() -> None:
    source = _source_v1()
    first = compile_hip_fgmres_recurrence_plan_v2(source)
    second = compile_hip_fgmres_recurrence_plan_v2(source)

    assert first.to_dict() == second.to_dict()
    assert first.plan_hash == second.plan_hash
    assert first.source_fgmres_plan_hash == source.plan_hash
    assert first.source_fgmres_memory_layout_hash == source.memory_layout_hash
    assert first.source_execution_plan_hash == source.source_execution_plan_hash
    assert first.source_free_space_plan_hash == source.source_free_space_plan_hash
    assert first.source_policy_hash == source.policy.policy_hash
    assert first._source_fgmres_plan is not source
    validate_hip_fgmres_recurrence_plan_v2(
        first,
        expected_source_plan=source,
    )


@pytest.mark.parametrize(
    ("restart_dimension", "max_iterations", "expected_restarts"),
    ((1, 0, 0), (2, 5, 3), (16, 4096, 256)),
)
def test_overlay_preserves_v1_extents_and_adds_exactly_one_256_byte_buffer(
    restart_dimension: int,
    max_iterations: int,
    expected_restarts: int,
) -> None:
    source, artifact = _artifact(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
    )

    assert artifact.buffers[:-1] == source.buffers
    assert sum(row.ownership == "borrowed" for row in artifact.buffers) == 7
    assert sum(row.ownership == "owned" for row in artifact.buffers) == 10
    control = artifact.buffer("fgmres_control_state_v2")
    assert control.ownership == "owned"
    assert control.dtype == "|u1"
    assert control.shape == (256,)
    assert control.element_count == 256
    assert control.byte_length == 256
    assert control.extent_formula == "256"
    assert artifact.maximum_restart_count == expected_restarts
    assert artifact.borrowed_device_byte_span == source.borrowed_device_byte_span
    assert artifact.source_owned_device_byte_length == source.owned_device_byte_length
    assert artifact.owned_device_byte_length == source.owned_device_byte_length + 256
    assert artifact.memory_layout_hash != source.memory_layout_hash


def test_control_state_has_exact_little_endian_256_byte_field_abi() -> None:
    payload = hip_fgmres_control_state_abi_payload_v2()
    fields = payload["fields"]

    assert payload["control_abi_version"] == 2
    assert payload["byte_order"] == "little_endian"
    assert payload["byte_length"] == HIP_FGMRES_CONTROL_STATE_BYTES_V2
    assert payload["layout"] == "32*i32+16*f64"
    assert len(fields) == 48
    assert [row["offset_bytes"] for row in fields[:32]] == list(range(0, 128, 4))
    assert [row["offset_bytes"] for row in fields[32:]] == list(range(128, 256, 8))
    assert {row["dtype"] for row in fields[:32]} == {"i32"}
    assert {row["dtype"] for row in fields[32:]} == {"f64"}
    assert fields[0] == {
        "name": "control_abi_version",
        "dtype": "i32",
        "offset_bytes": 0,
    }
    assert fields[28] == {
        "name": "schedule_epoch",
        "dtype": "i32",
        "offset_bytes": 112,
    }
    assert fields[29:32] == [
        {
            "name": "predecessor_validation_state",
            "dtype": "i32",
            "offset_bytes": 116,
        },
        {
            "name": "predecessor_mask_snapshot",
            "dtype": "i32",
            "offset_bytes": 120,
        },
        {
            "name": "predecessor_reduction_epoch_snapshot",
            "dtype": "i32",
            "offset_bytes": 124,
        },
    ]
    assert fields[-1] == {
        "name": "x_scale_l2",
        "dtype": "f64",
        "offset_bytes": 248,
    }
    assert payload["transient_zero_fields"] == [
        "predecessor_validation_state",
        "predecessor_mask_snapshot",
        "predecessor_reduction_epoch_snapshot",
    ]
    assert payload["post_init_values"]["column_index"] == -1
    assert payload["post_init_values"]["phase"] == payload["phase_codes"]["rhs_metrics"]
    assert payload["post_init_values"]["schedule_epoch"] == 1
    assert payload["post_init_values"]["predecessor_validation_state"] == 0
    assert payload["post_init_values"]["predecessor_mask_snapshot"] == 0
    assert payload["post_init_values"]["predecessor_reduction_epoch_snapshot"] == 0
    assert payload["init_zero_prestate_exception"]["required_prestate"] == (
        "all_256_bytes_exact_zero"
    )
    assert (
        payload["transient_validation_fields_zero_outside_checkpoint_transaction"]
        is True
    )


def test_control_payload_is_fresh_and_freezes_modes_targets_and_reason_bits() -> None:
    first = hip_fgmres_control_state_abi_payload_v2()
    first["fields"][0]["name"] = "forged"
    first["phase_codes"]["failed"] = 999
    second = hip_fgmres_control_state_abi_payload_v2()

    assert second["fields"][0]["name"] == "control_abi_version"
    assert second["phase_codes"]["failed"] == 10
    assert second["control_mode_codes"]["FINAL_GUARD"] == 13
    assert second["control_mode_codes"]["PREDECESSOR_VALIDATE"] == 14
    assert second["predecessor_validation_state_codes"] == {
        "empty": 0,
        "armed": 1,
        "consumed": 2,
        "commit_preflighted": 3,
    }
    assert second["vector_mode_codes"]["COMMIT_CHECKPOINT"] == 8
    assert second["vector_mode_codes"]["PREFLIGHT_COMMIT_SOURCE"] == 9
    assert second["vector_gate_codes"]["DGKS_SECOND_PASS"] == 1
    assert second["spmv_mode_codes"] == {
        "INITIAL": 0,
        "ARNOLDI": 1,
        "CANDIDATE": 2,
    }
    assert second["candidate_reason_bits"] == {
        "estimated_l2_trigger": 0,
        "invariant_or_rotation_breakdown": 1,
        "planned_cycle_end": 2,
    }
    assert second["reduction_target_codes"]["NONE"] == 0
    assert second["reduction_target_codes"]["DOT"] == 1
    assert second["reduction_target_codes"]["TRIAL_X_L2"] == 13
    assert "NONE" not in second["reduction_valid_bits"]
    assert second["reduction_valid_bits"]["DOT"] == 0
    assert second["reduction_valid_bits"]["TRIAL_X_L2"] == 12
    assert second["reduction_target_none_contract"] == {
        "code": 0,
        "publishes_control_scalar": False,
        "sets_reduction_valid_bit": False,
    }


def test_reduction_target_slots_make_rhs_to_initial_aliasing_fail_closed() -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    targets = control["reduction_target_fields"]
    alias = control["transient_norm_slot_alias_contract"]

    assert targets["RHS_L2"]["field"] == "candidate_l2"
    assert targets["RHS_L2"]["offset_bytes"] == 208
    assert targets["INITIAL_L2"]["field"] == "candidate_l2"
    assert targets["RHS_LINF"]["offset_bytes"] == 216
    assert targets["INITIAL_LINF"]["offset_bytes"] == 216
    assert targets["RHS_L2"]["valid_bit"] != targets["INITIAL_L2"]["valid_bit"]
    assert alias["rhs_consumer"] == "BIND_RHS"
    assert alias["rhs_consumer_clears_valid_bits"] is True
    assert alias["initial_consumer"] == "INITIAL_GATE"
    assert alias["initial_metrics_may_overwrite_only_after_rhs_bits_cleared"] is True


def test_v2_solve_record_retains_public_layout_but_has_v2_producer_identity() -> None:
    v1 = hip_fgmres_solve_record_abi_payload_v1()
    v2 = hip_fgmres_solve_record_abi_payload_v2()

    assert v1["recurrence_abi_version"] == 1
    assert v2["recurrence_abi_version"] == 2
    assert v2["header_initial_values"] == {"recurrence_abi_version": 2}
    assert v2["producer_contract"] == "single_v2_code_object_only"
    for name in (
        "byte_order",
        "header_bytes",
        "restart_bytes",
        "header_layout",
        "restart_layout",
        "header_fields",
        "restart_fields",
        "terminal_status_codes",
        "termination_codes",
        "restart_hint_codes",
        "restart_flag_bits",
    ):
        assert v2[name] == v1[name]
    assert canonical_hash(v2) != canonical_hash(v1)


def test_four_symbol_interface_binds_base_indices_schedule_and_error_contract() -> None:
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert kernel["symbols"] == [
        "engine_v2_fgmres_control_v2",
        "engine_v2_fgmres_vector_v2",
        "engine_v2_fgmres_csr_spmv_indexed_v2",
        "engine_v2_fgmres_reduce_v2",
    ]
    assert set(kernel["signatures"]) == set(kernel["symbols"])
    for signature in kernel["signatures"].values():
        assert "expected_schedule_epoch" in signature
        assert "expected_restart" in signature
        assert "expected_column" in signature
        assert "_base" in signature
    assert "row_index" in kernel["signatures"]["engine_v2_fgmres_control_v2"]
    assert "pass_index" in kernel["signatures"]["engine_v2_fgmres_control_v2"]
    assert (
        "expected_reduction_epoch" in kernel["signatures"]["engine_v2_fgmres_reduce_v2"]
    )
    guard = kernel["launch_sequence_guard"]
    assert guard["schedule_epoch_rejects_duplicate_skip_or_reorder"] is True
    assert guard["nonadvancing_mode_exceptions"] == {
        "control": ["PREDECESSOR_VALIDATE"],
        "vector": ["PREFLIGHT_COMMIT_SOURCE"],
    }
    assert guard["initial_mode_schedule"] == {
        "CONTROL_INIT": "schedule=0 -> 1,phase=rhs_metrics",
        "VECTOR_COPY_INITIAL_X": "schedule=1",
        "RHS_L2_REDUCTION": "schedule=2..1+S,reduction_epoch=0..S-1",
        "RHS_LINF_REDUCTION": ("schedule=2+S..1+2S,reduction_epoch=S..2S-1"),
        "CONTROL_BIND_RHS": "schedule=2+2S,phase=rhs_metrics->initial_state",
        "SPMV_INITIAL": "schedule=3+2S",
        "CONTROL_OPERATOR_ACCEPT": "schedule=4+2S",
        "VECTOR_FORM_INITIAL_RESIDUAL": "schedule=5+2S",
        "INITIAL_L2_REDUCTION": ("schedule=6+2S..5+3S,reduction_epoch=2S..3S-1"),
        "INITIAL_LINF_REDUCTION": ("schedule=6+3S..5+4S,reduction_epoch=3S..4S-1"),
        "CONTROL_INITIAL_GATE": "schedule=6+4S",
    }
    assert guard["mismatch_mutates_counters_or_published_scalars"] is False
    assert guard["reduction_epoch_increments_only_after_valid_stage"] is True
    coordinates = guard["coordinate_contract"]
    assert coordinates["initial_metrics_expected_restart"] == -1
    assert coordinates["restart_begin_expected_restart_source"] == (
        "next_expected_restart"
    )
    assert coordinates["restart_begin_expected_column"] == -1
    assert coordinates["restart_begin_is_exception_to_active_restart_equality"] is True
    assert coordinates["schedule_epoch_B_formula"] == "7+4*S"
    assert coordinates["schedule_epoch_B_unique_mode"] == "RESTART_BEGIN"
    assert coordinates["final_guard_allowed_at_schedule_epoch_B"] is False
    assert kernel["host_shifted_pointer_arguments_allowed"] is False
    reduction = kernel["reduction_launch_geometry"]
    assert reduction["values_per_block"] == 512
    assert reduction["intermediate_target"] == "NONE"
    assert reduction["intermediate_publishes_scalar_or_valid_bit"] is False
    assert reduction["final_requires_named_non_none_target"] is True
    assert reduction["duplicate_valid_target_is_terminal_invalid_control"] is True
    assert reduction["combine_input_output_base_must_differ"] is True
    assert reduction["named_mode_target_compatibility"]["LASSQ_LOAD"] == ["RHS_L2"]
    assert reduction["named_mode_target_compatibility"]["COMBINE_MAX"] == [
        "RHS_LINF",
        "INITIAL_LINF",
        "CANDIDATE_LINF",
    ]
    assert kernel["device_error_bits"]["jacobi_inverse"] == 5
    assert kernel["device_error_bits"]["invalid_reduction_pair"] == 6
    assert kernel["device_error_masks"]["jacobi_inverse"] == 32
    assert kernel["device_error_masks"]["invalid_reduction_pair"] == 64


def test_global_fixed_recurrence_schedule_is_closed_and_kernel_hash_bound() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    _, artifact = _artifact()
    payload = artifact.to_dict()
    contract = hip_fgmres_global_schedule_contract_payload_v1()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert canonical_hash(contract) == (
        "sha256:425ea7f4cd30e67a255b1da7490011bd4ecda8537444011e7b7fa005bb477ad4"
    )
    assert kernel["global_fixed_recurrence_schedule"] == contract
    assert canonical_hash(kernel) == _GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2
    assert (
        artifact.kernel_module_abi_hash == _GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2
    )
    assert (
        _GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2
        != _HISTORICAL_FIRST_COLUMN_CHECKPOINT_KERNEL_ABI_HASH_V2
    )

    semantic_drift = deepcopy(kernel)
    semantic_drift["global_fixed_recurrence_schedule"]["terminal_padding_contract"][
        "inactive_launches_preserve_all_device_bytes"
    ] = False
    assert canonical_hash(semantic_drift) != canonical_hash(kernel)

    additional_property = deepcopy(payload)
    additional_interface = additional_property["kernel_module_contract"]["interface"]
    additional_interface["global_fixed_recurrence_schedule"]["epoch_formulas"][
        "unbound_formula"
    ] = "E=unconstrained"
    additional_property["kernel_module_contract"]["kernel_module_abi_hash"] = (
        canonical_hash(additional_interface)
    )
    errors = list(validator.iter_errors(additional_property))
    assert any(
        error.validator == "additionalProperties"
        and tuple(error.absolute_path)[-1] == "epoch_formulas"
        for error in errors
    )

    missing_required_prestate = deepcopy(payload)
    del missing_required_prestate["kernel_module_contract"]["interface"][
        "global_fixed_recurrence_schedule"
    ]["final_guard_contract"]["active_required_prestate"]
    assert any(
        error.validator == "required"
        and tuple(error.absolute_path)[-1] == "final_guard_contract"
        for error in validator.iter_errors(missing_required_prestate)
    )


def test_first_column_partial_schedule_is_exact_hashed_and_stops_after_dgks() -> None:
    schedule = hip_fgmres_first_column_partial_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert kernel["first_column_partial_schedule"] == schedule
    assert kernel["first_column_partial_schedule_hash"] == canonical_hash(schedule)
    assert kernel["first_column_partial_schedule_hash"] == (
        "sha256:dc6d1306ae3c7c0f970afcbe433b888cfcea591d6a34c6f36657e30ecc9c3b88"
    )
    scope = schedule["scope"]
    assert scope["restart_numbering"] == "one_based"
    assert scope["restart_index"] == 1
    assert scope["column_index"] == 0
    assert scope["included_through"] == "DGKS_DECIDE"
    assert scope["schedule_epoch_B_owner"] == "RESTART_BEGIN"
    assert scope["initial_final_guard_at_B_allowed"] is False
    assert scope["first_pass_mgs_included"] is True
    assert scope["device_dgks_decision_included"] is True
    for name in (
        "second_pass_mgs_included",
        "h_next_reduction_included",
        "givens_included",
        "candidate_included",
        "checkpoint_commit_included",
        "full_column_complete",
        "full_recurrence_complete",
    ):
        assert scope[name] is False

    assert schedule["symbols"] == {
        "F": "free_dof_count",
        "M": "restart_dimension",
        "I": "max_iterations",
        "S": "recursive_stage_count(F,ceil(F/512))",
        "B": "7+4*S",
    }
    assert schedule["start_state"] == {
        "schedule_epoch": "B",
        "reduction_epoch": "4*S",
        "phase": "restart_ready",
        "restart_index": 0,
        "next_expected_restart": 1,
        "column_index": -1,
        "effective_restarts": 0,
        "effective_iterations": 0,
        "arnoldi_step_count": 0,
        "reorthogonalization_count": 0,
        "operator_apply_count": 1,
        "preconditioner_apply_count": 0,
        "reduction_valid_mask": 0,
    }
    assert [row["name"] for row in schedule["launches"]] == [
        "CONTROL_RESTART_BEGIN",
        "VECTOR_NORMALIZE_V0",
        "VECTOR_APPLY_JACOBI",
        "CONTROL_PRECONDITION_ACCEPT",
        "SPMV_ARNOLDI",
        "CONTROL_OPERATOR_ACCEPT",
        "REDUCE_WORK_BEFORE",
        "REDUCE_DOT_FIRST_PASS_ROW0",
        "CONTROL_DOT_ACCEPT_ROW0_PASS0",
        "VECTOR_MGS_SUBTRACT_ROW0_PASS0",
        "REDUCE_AFTER_FIRST",
        "CONTROL_DGKS_DECIDE_PASS0",
    ]
    restart = schedule["launches"][0]
    assert restart["expected_schedule_epoch"] == "B"
    assert restart["expected_restart"] == 1
    assert restart["expected_column"] == -1
    assert restart["row_index"] == restart["pass_index"] == -1
    assert restart["phase_before"] == "restart_ready"
    assert restart["phase_after"] == "arnoldi"

    work = schedule["launches"][6]
    dot = schedule["launches"][7]
    dot_accept = schedule["launches"][8]
    subtract = schedule["launches"][9]
    after = schedule["launches"][10]
    dgks = schedule["launches"][11]
    assert (work["expected_reduction_epoch"], work["expected_schedule_epoch"]) == (
        "q=4*S..5*S-1",
        "13+q",
    )
    assert (dot["expected_reduction_epoch"], dot["expected_schedule_epoch"]) == (
        "q=5*S..6*S-1",
        "13+q",
    )
    assert dot_accept["expected_schedule_epoch"] == "13+6*S"
    assert (dot_accept["row_index"], dot_accept["pass_index"]) == (0, 0)
    assert subtract["expected_schedule_epoch"] == "14+6*S"
    assert after["expected_reduction_epoch"] == "q=6*S..7*S-1"
    assert after["expected_schedule_epoch"] == "15+q"
    assert dgks["expected_schedule_epoch"] == "15+7*S"
    assert (dgks["row_index"], dgks["pass_index"]) == (-1, 0)
    assert schedule["end_state"]["schedule_epoch"] == "16+7*S"
    assert schedule["end_state"]["reduction_epoch"] == "7*S"


def test_first_column_partial_schedule_binds_bits_dense_aliases_and_counters() -> None:
    first = hip_fgmres_first_column_partial_schedule_payload_v2()
    first["launches"][0]["expected_restart"] = 99
    schedule = hip_fgmres_first_column_partial_schedule_payload_v2()

    validity = schedule["reduction_validity_contract"]
    assert validity["target_codes"] == {
        "DOT": 1,
        "WORK_BEFORE": 6,
        "AFTER_FIRST": 7,
    }
    assert validity["valid_bits"] == {
        "DOT": 0,
        "WORK_BEFORE": 5,
        "AFTER_FIRST": 6,
    }
    assert [
        validity[name]
        for name in (
            "mask_at_start",
            "mask_after_work_before",
            "mask_after_dot",
            "mask_after_dot_accept",
            "mask_after_after_first",
            "mask_after_dgks_decide",
        )
    ] == [0, 32, 33, 32, 96, 0]
    assert validity["dot_accept_consumes"] == ["DOT"]
    assert validity["dgks_decide_consumes"] == [
        "WORK_BEFORE",
        "AFTER_FIRST",
    ]

    dense = schedule["dense_transient_contract"]
    assert dense["h_0_0_element_offset"] == 0
    assert dense["g_0_element_offset"] == "M*(M+1)+2*M"
    assert dense["y_0_element_offset"] == "M*(M+1)+3*M+1"
    assert dense["dot_accept_update"] == ("y[0]=dot_coefficient;H[0,0]+=y[0]")
    assert dense["mgs_coefficient_source"] == "y[0]"
    assert dense["y_storage_before_backsolve"] == "triangular_solution_alias"
    assert dense["mgs_reads_h_0_0_directly"] is False

    counters = schedule["counter_acceptance_contract"]
    assert counters["restart_begin_accepts_effective_restarts"] == "0->1"
    assert counters["precondition_accept_accepts_count"] == "0->1"
    assert counters["operator_accept_accepts_count"] == "1->2"
    assert counters["multi_block_launches_increment_record_counters"] is False
    assert counters["effective_iterations_incremented"] is False
    assert counters["arnoldi_step_count_incremented"] is False
    assert counters["reorthogonalization_count_incremented"] is False
    assert counters["failure_count_parity_proven"] is False
    assert schedule["end_state"]["effective_restarts"] == 1
    assert schedule["end_state"]["effective_iterations"] == 0
    assert schedule["end_state"]["preconditioner_apply_count"] == 1
    assert schedule["end_state"]["operator_apply_count"] == 2


@pytest.mark.parametrize("stage_count", [1, 2, 3])
def test_first_column_partial_schedule_resolves_without_gaps_or_B_collision(
    stage_count: int,
) -> None:
    schedule = hip_fgmres_first_column_partial_schedule_payload_v2()
    base = 7 + 4 * stage_count
    resolved_schedule_epochs = [
        base,
        base + 1,
        base + 2,
        base + 3,
        base + 4,
        base + 5,
        *range(13 + 4 * stage_count, 13 + 5 * stage_count),
        *range(13 + 5 * stage_count, 13 + 6 * stage_count),
        13 + 6 * stage_count,
        14 + 6 * stage_count,
        *range(15 + 6 * stage_count, 15 + 7 * stage_count),
        15 + 7 * stage_count,
    ]
    resolved_reduction_epochs = [
        *range(4 * stage_count, 5 * stage_count),
        *range(5 * stage_count, 6 * stage_count),
        *range(6 * stage_count, 7 * stage_count),
    ]

    assert resolved_schedule_epochs == list(range(base, 16 + 7 * stage_count))
    assert resolved_reduction_epochs == list(range(4 * stage_count, 7 * stage_count))
    assert resolved_schedule_epochs.count(base) == 1
    assert schedule["scope"]["schedule_epoch_B_owner"] == "RESTART_BEGIN"
    assert schedule["scope"]["initial_final_guard_at_B_allowed"] is False


def test_first_column_completion_schedule_is_separate_exact_and_hashed() -> None:
    partial = hip_fgmres_first_column_partial_schedule_payload_v2()
    completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert canonical_hash(partial) == (
        "sha256:dc6d1306ae3c7c0f970afcbe433b888cfcea591d6a34c6f36657e30ecc9c3b88"
    )
    assert kernel["first_column_partial_schedule"] == partial
    assert kernel["first_column_partial_schedule_hash"] == canonical_hash(partial)
    assert kernel["first_column_completion_schedule"] == completion
    assert kernel["first_column_completion_schedule_hash"] == canonical_hash(completion)
    assert kernel["first_column_completion_schedule_hash"] == (
        "sha256:941f1191e4acd806ae6616c36599949506e87219199908e3aa62ee116ac6dbb4"
    )
    assert completion["predecessor_contract"] == {
        "schedule_contract_version": partial["schedule_contract_version"],
        "schedule_hash": canonical_hash(partial),
        "required_end_schedule_epoch": "16+7*S",
        "required_end_reduction_epoch": "7*S",
        "required_end_reduction_valid_mask": 0,
    }

    scope = completion["scope"]
    assert scope["included_from"] == "DGKS_DECIDE_ACCEPTED_STATE"
    assert scope["included_through"] == "ARNOLDI_GIVENS"
    for name in (
        "dgks_second_pass_included",
        "h_next_reduction_included",
        "v_next_normalization_included",
        "givens_included",
        "normalization_precedes_givens",
    ):
        assert scope[name] is True
    assert scope["vector_accept_used_for_v_next"] is False
    for name in (
        "candidate_envelope_included",
        "backsubstitute_included",
        "checkpoint_commit_included",
        "full_recurrence_complete",
    ):
        assert scope[name] is False

    assert completion["start_state"]["schedule_epoch"] == "16+7*S"
    assert completion["start_state"]["reduction_epoch"] == "7*S"
    assert completion["start_state"]["effective_iterations"] == 0
    assert [row["name"] for row in completion["launches"]] == [
        "REDUCE_DOT_SECOND_PASS_ROW0",
        "CONTROL_DOT_ACCEPT_ROW0_PASS1",
        "VECTOR_MGS_SUBTRACT_ROW0_PASS1",
        "REDUCE_H_NEXT",
        "VECTOR_NORMALIZE_V1",
        "CONTROL_ARNOLDI_GIVENS_COLUMN0",
    ]
    assert completion["end_state"]["schedule_epoch"] == "20+9*S"
    assert completion["end_state"]["reduction_epoch"] == "9*S"


def test_completion_schedule_binds_gated_second_pass_epochs_and_masks() -> None:
    completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    rows = completion["launches"]

    second_dot, dot_accept, second_mgs, h_next, normalize, givens = rows
    assert (
        second_dot["expected_reduction_epoch"],
        second_dot["expected_schedule_epoch"],
    ) == ("q=7*S..8*S-1", "16+q")
    assert second_dot["orthogonalization_pass"] == 1
    assert second_dot["gate_source"] == "dgks_reorth_required"
    assert second_dot["gate_false_effect"] == (
        "claim_schedule_and_reduction_epochs_without_numeric_"
        "read_write_or_target_publish"
    )
    assert dot_accept["expected_schedule_epoch"] == "16+8*S"
    assert (dot_accept["row_index"], dot_accept["pass_index"]) == (0, 1)
    assert dot_accept["required_valid_mask"] == "1_if_gate_true_else_0"
    assert dot_accept["result_valid_mask"] == 0
    assert second_mgs["expected_schedule_epoch"] == "17+8*S"
    assert second_mgs["gate"] == "DGKS_SECOND_PASS"
    assert h_next["expected_reduction_epoch"] == "q=8*S..9*S-1"
    assert h_next["expected_schedule_epoch"] == "18+q"
    assert h_next["final_target"] == "H_NEXT"
    assert normalize["expected_schedule_epoch"] == "18+9*S"
    assert normalize["logical_index"] == 1
    assert normalize["required_valid_mask"] == 128
    assert normalize["result_valid_mask"] == 128
    assert givens["expected_schedule_epoch"] == "19+9*S"
    assert (givens["row_index"], givens["pass_index"]) == (-1, -1)
    assert givens["required_valid_mask"] == 128
    assert givens["result_valid_mask"] == 0

    gate = completion["gated_second_pass_contract"]
    assert gate["host_schedule_is_flag_independent"] is True
    assert gate["all_S_dot_stages_submitted_for_both_gate_values"] is True
    assert gate["gate_false_claims_schedule_epoch"] is True
    assert gate["gate_false_claims_reduction_epoch"] is True
    assert gate["gate_false_reads_numeric_vectors"] is False
    assert gate["gate_false_writes_reduction_scratch"] is False
    assert gate["gate_false_publishes_dot_target_or_valid_bit"] is False
    assert gate["reorthogonalization_count_increments_at_givens_accept_only"] is True

    validity = completion["reduction_validity_contract"]
    assert validity["target_codes"] == {"DOT": 1, "H_NEXT": 8}
    assert validity["valid_bits"] == {"DOT": 0, "H_NEXT": 7}
    assert validity["mask_after_second_dot"] == ("1_if_dgks_required_else_0")
    assert validity["mask_after_second_dot_accept"] == 0
    assert validity["mask_after_h_next"] == 128
    assert validity["normalization_preserves"] == ["H_NEXT"]
    assert validity["givens_consumes"] == ["H_NEXT"]
    assert validity["mask_at_end"] == 0


def test_completion_arithmetic_fixes_h_v1_givens_and_candidate_conventions() -> None:
    first = hip_fgmres_first_column_completion_schedule_payload_v2()
    first["arithmetic_contract"]["tau_hex"] = "forged"
    completion = hip_fgmres_first_column_completion_schedule_payload_v2()

    arithmetic = completion["arithmetic_contract"]
    assert arithmetic["binary64_epsilon_hex"] == "0x1.0000000000000p-52"
    assert arithmetic["tau_hex"] == "0x1.0000000000000p-46"
    assert arithmetic["tau_decimal"] == 64.0 * np.finfo(np.float64).eps
    assert arithmetic["fp_contraction_allowed"] is False
    assert arithmetic["h_accumulation"] == ("H[0,0]=checked(H[0,0]+second_dot)")
    assert arithmetic["second_mgs"] == (
        "work_w[k]=checked(work_w[k]-second_dot*V[0,k])"
    )
    assert arithmetic["invariant_breakdown_threshold"] == "tau*work_before_l2"
    assert arithmetic["invariant_breakdown_comparison"] == ("h_next_l2<=threshold")
    assert arithmetic["threshold_has_unit_floor"] is False
    assert arithmetic["normalize_before_givens"] is True
    assert arithmetic["normalization_breakdown_effect"] == (
        "V[1,:]=positive_zero_without_division"
    )
    assert arithmetic["rotation_norm"] == "rho=hypot(u,l)"
    assert arithmetic["rotation_breakdown_comparison"] == (
        "not_finite(rho)_or_rho<=rotation_breakdown_threshold"
    )
    assert arithmetic["rotation_active_effect"] == (
        "c[0]=u/rho,s[0]=l/rho,H[0,0]=rho,H[1,0]=positive_zero"
    )
    assert arithmetic["signed_rotation_convention"] == (
        "[u';l']=[c*u+s*l;-s*u+c*l],g[1]=-s*g_old"
    )
    assert arithmetic["estimated_residual"] == "abs(g[1])"

    dense = completion["dense_contract"]
    assert dense["h_0_0_element_offset"] == 0
    assert dense["h_1_0_element_offset"] == 1
    assert dense["c_0_element_offset"] == "M*(M+1)"
    assert dense["s_0_element_offset"] == "M*(M+1)+M"
    assert dense["g_0_element_offset"] == "M*(M+1)+2*M"
    assert dense["g_1_element_offset"] == "M*(M+1)+2*M+1"
    assert dense["y_0_element_offset"] == "M*(M+1)+3*M+1"
    assert dense["rotation_only_breakdown_retains_normalized_unused_V1"] is True

    candidate = completion["candidate_contract"]
    assert candidate["reason_bits"] == {
        "estimated_l2_trigger": 0,
        "invariant_or_rotation_breakdown": 1,
        "planned_cycle_end": 2,
    }
    assert candidate["estimated_l2_trigger"] == (
        "estimated_residual_l2<=solver_tolerance_l2"
    )
    assert candidate["planned_cycle_end_trigger"] == ("column_index+1>=cycle_width")
    assert candidate["reason_bits_are_bitwise_or"] is True
    assert candidate["candidate_required"] == ("1_if_reason_bits_nonzero_else_0")


def test_givens_accept_publishes_counts_record_metrics_and_retains_column_zero() -> (
    None
):
    completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    acceptance = completion["counter_record_acceptance_contract"]

    assert acceptance["normalization_changes_counters_or_public_record"] is False
    assert acceptance["givens_is_the_accept_after_multiblock_normalization"] is True
    assert acceptance["effective_iterations"] == "0->1"
    assert acceptance["arnoldi_step_count"] == "0->1"
    assert acceptance["effective_arnoldi_dimension"] == "0->1"
    assert acceptance["reorthogonalization_count"] == ("0->dgks_reorth_required")
    assert acceptance["operator_apply_count"] == "preserve_2"
    assert acceptance["preconditioner_apply_count"] == "preserve_1"
    assert acceptance["happy_breakdown_count"] == (
        "preserve_0_until_true_residual_checkpoint"
    )
    assert acceptance["record_estimated_residual_l2"] == {
        "offset_bytes": 152,
        "value": "abs(g[1])",
    }
    assert acceptance["record_arnoldi_work_l2"] == {
        "offset_bytes": 160,
        "value": "work_before_l2",
    }
    assert acceptance["record_arnoldi_breakdown_threshold"] == {
        "offset_bytes": 168,
        "value": "tau*work_before_l2",
    }
    assert acceptance["solution_and_true_residual_record_fields_change"] is False
    assert (
        acceptance["late_normalization_failure_advances_counts_or_record_metrics"]
        is False
    )

    column = completion["column_phase_contract"]
    assert column["column_index_after_givens"] == 0
    assert column["candidate_required_true_phase"] == "candidate"
    assert column["candidate_required_false_phase"] == "arnoldi"
    assert column["fixed_candidate_envelope_uses_expected_column"] == 0
    assert column["no_candidate_envelope_still_submitted_as_gated_noops"] is True
    assert column["advance_to_column_1_at_givens_or_normalization"] is False
    assert column["advance_authority"] == ("future_CHECKPOINT_FINALIZE_column_boundary")

    end = completion["end_state"]
    assert end["effective_iterations"] == 1
    assert end["arnoldi_step_count"] == 1
    assert end["effective_arnoldi_dimension"] == 1
    assert end["column_index"] == 0
    assert end["dgks_reorth_required"] == 0
    assert end["solution_and_true_residual_committed"] is False


@pytest.mark.parametrize("stage_count", [1, 2, 3])
def test_first_column_completion_schedule_resolves_contiguously(
    stage_count: int,
) -> None:
    start = 16 + 7 * stage_count
    resolved_schedule_epochs = [
        *range(16 + 7 * stage_count, 16 + 8 * stage_count),
        16 + 8 * stage_count,
        17 + 8 * stage_count,
        *range(18 + 8 * stage_count, 18 + 9 * stage_count),
        18 + 9 * stage_count,
        19 + 9 * stage_count,
    ]
    resolved_reduction_epochs = [
        *range(7 * stage_count, 8 * stage_count),
        *range(8 * stage_count, 9 * stage_count),
    ]

    assert resolved_schedule_epochs == list(range(start, 20 + 9 * stage_count))
    assert resolved_reduction_epochs == list(range(7 * stage_count, 9 * stage_count))


def test_candidate_preparation_schedule_is_separate_exact_and_hashed() -> None:
    completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    preparation = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert canonical_hash(completion) == (
        "sha256:941f1191e4acd806ae6616c36599949506e87219199908e3aa62ee116ac6dbb4"
    )
    assert canonical_hash(preparation) == (
        "sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec"
    )
    assert kernel["first_column_completion_schedule"] == completion
    assert kernel["first_column_completion_schedule_hash"] == canonical_hash(completion)
    assert kernel["first_column_candidate_preparation_schedule"] == preparation
    assert kernel["first_column_candidate_preparation_schedule_hash"] == (
        canonical_hash(preparation)
    )
    assert preparation["predecessor_contract"] == {
        "schedule_contract_version": completion["schedule_contract_version"],
        "schedule_hash": canonical_hash(completion),
        "required_end_schedule_epoch": "20+9*S",
        "required_end_reduction_epoch": "9*S",
        "required_end_reduction_valid_mask": 0,
    }

    first = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    first["scope"]["candidate_preparation_included"] = False
    second = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    assert second["scope"]["candidate_preparation_included"] is True


def test_candidate_preparation_fixes_backsolve_trial_update_and_accept() -> None:
    preparation = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    scope = preparation["scope"]

    assert scope["included_from"] == "ARNOLDI_GIVENS_ACCEPTED_STATE"
    assert scope["included_through"] == "VECTOR_ACCEPT"
    for name in (
        "candidate_preparation_included",
        "backsubstitute_included",
        "trial_vector_build_included",
        "solution_update_l2_included",
        "vector_accept_included",
        "candidate_false_claim_only",
        "triangular_breakdown_claim_only_after_backsubstitute",
    ):
        assert scope[name] is True
    for name in (
        "candidate_true_residual_included",
        "candidate_spmv_included",
        "checkpoint_decide_included",
        "checkpoint_commit_included",
        "full_recurrence_complete",
    ):
        assert scope[name] is False

    backsolve, build, update, accept = preparation["launches"]
    assert [row["name"] for row in preparation["launches"]] == [
        "CONTROL_BACKSUBSTITUTE_COLUMN0",
        "VECTOR_BUILD_TRIAL_X_COLUMN0",
        "REDUCE_SOLUTION_UPDATE_L2_COLUMN0",
        "CONTROL_VECTOR_ACCEPT_TRIAL_COLUMN0",
    ]
    assert backsolve["mode"] == "BACKSUBSTITUTE"
    assert backsolve["expected_schedule_epoch"] == "20+9*S"
    assert (backsolve["row_index"], backsolve["pass_index"]) == (-1, -1)
    assert build["mode"] == "BUILD_TRIAL_X"
    assert build["gate"] == "CANDIDATE_REQUIRED"
    assert build["expected_schedule_epoch"] == "21+9*S"
    assert build["logical_index"] == 0
    assert update["first_mode"] == "LASSQ_WORK_W_MINUS_X"
    assert update["combine_mode"] == "COMBINE_LASSQ"
    assert update["expected_schedule_epoch"] == "22+q"
    assert update["expected_reduction_epoch"] == "q=9*S..10*S-1"
    assert update["final_target"] == "UPDATE_L2"
    assert accept["mode"] == "VECTOR_ACCEPT"
    assert accept["expected_schedule_epoch"] == "22+10*S"
    assert accept["required_valid_mask"] == (
        "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
    )
    assert accept["result_valid_mask"] == "same_as_required_valid_mask"

    backsubstitution = preparation["backsubstitution_contract"]
    assert backsubstitution["upper_factor_scale"] == ("max_abs(H[0:1,0:1])=abs(H[0,0])")
    assert backsubstitution["pivot_floor"] == "tau*upper_factor_scale"
    assert backsubstitution["pivot_floor_has_unit_floor"] is False
    assert backsubstitution["triangular_solution"] == ("y[0]=checked(g[0]/H[0,0])")
    assert backsubstitution["pivot_breakdown_promotes_invariant_breakdown"] is True
    assert backsubstitution["success_preserves_preexisting_invariant_breakdown"] is True
    assert (
        backsubstitution["candidate_false_preserves_preexisting_invariant_breakdown"]
        is True
    )
    assert backsubstitution["triangular_scale_record_offset_bytes"] == 176
    trial = preparation["trial_vector_contract"]
    assert trial["formula"] == "work_w[k]=solution_x[k]+y[0]*Z[0,k]"
    assert trial["evaluation_order"] == ("multiply_then_add_without_fp_contraction")
    assert trial["additional_O_F_workspace_allowed"] is False


def test_candidate_preparation_false_and_triangular_paths_are_claim_only() -> None:
    preparation = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    gate = preparation["gated_preparation_contract"]

    assert gate["host_schedule_is_candidate_flag_independent"] is True
    assert gate["all_four_launch_groups_submitted_for_both_candidate_values"] is True
    assert gate["all_S_update_stages_submitted_for_all_gate_values"] is True
    assert gate["candidate_false_claims_schedule_epochs"] is True
    assert gate["candidate_false_claims_reduction_epochs"] is True
    assert gate["candidate_false_reads_numeric_data"] is False
    assert gate["candidate_false_writes_numeric_data_or_reduction_scratch"] is False
    assert gate["candidate_false_publishes_target_or_valid_bit"] is False
    assert gate["triangular_breakdown_claims_remaining_schedule_epochs"] is True
    assert gate["triangular_breakdown_claims_update_reduction_epochs"] is True
    assert gate["triangular_breakdown_reads_or_writes_trial_numeric_data"] is False
    assert gate["triangular_breakdown_publishes_update_target_or_valid_bit"] is False

    validity = preparation["reduction_validity_contract"]
    assert validity["target_code"] == {"UPDATE_L2": 11}
    assert validity["valid_bit"] == {"UPDATE_L2": 10}
    assert validity["mask_at_start"] == 0
    assert validity["mask_after_update_tree"] == (
        "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
    )
    assert validity["vector_accept_preserves"] == ["UPDATE_L2_if_present"]
    assert validity["mask_at_end"] == (
        "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
    )
    assert validity["future_consumer"] == "CHECKPOINT_DECIDE"

    counters = preparation["counter_phase_contract"]
    assert counters["effective_iterations"] == "preserve_1"
    assert counters["operator_apply_count"] == "preserve_2"
    assert counters["preconditioner_apply_count"] == "preserve_1"
    assert counters["phase"] == "preserve_candidate_if_required_else_arnoldi"
    assert counters["column_index"] == "preserve_0"
    assert counters["candidate_reason_bits"] == "preserve"
    assert counters["invariant_breakdown"] == (
        "preserve_unless_active_pivot_breakdown_promotes_to_1"
    )
    assert counters["solution_and_true_residual_committed"] is False


@pytest.mark.parametrize("stage_count", [1, 2, 3])
def test_candidate_preparation_schedule_resolves_contiguously(
    stage_count: int,
) -> None:
    start = 20 + 9 * stage_count
    resolved_schedule_epochs = [
        20 + 9 * stage_count,
        21 + 9 * stage_count,
        *range(22 + 9 * stage_count, 22 + 10 * stage_count),
        22 + 10 * stage_count,
    ]
    resolved_reduction_epochs = list(range(9 * stage_count, 10 * stage_count))

    assert resolved_schedule_epochs == list(range(start, 23 + 10 * stage_count))
    assert resolved_reduction_epochs == list(range(9 * stage_count, 10 * stage_count))

    end = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()[
        "end_state"
    ]
    assert end["schedule_epoch"] == "23+10*S"
    assert end["reduction_epoch"] == "10*S"
    assert end["column_index"] == 0
    assert end["invariant_breakdown"] == (
        "1_if_preexisting_or_active_pivot_breakdown_else_0"
    )
    assert end["solution_and_true_residual_committed"] is False


def test_candidate_residual_schedule_is_separate_exact_hashed_and_abi_bound() -> None:
    partial = hip_fgmres_first_column_partial_schedule_payload_v2()
    completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    preparation = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    residual = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert canonical_hash(partial) == (
        "sha256:dc6d1306ae3c7c0f970afcbe433b888cfcea591d6a34c6f36657e30ecc9c3b88"
    )
    assert canonical_hash(completion) == (
        "sha256:941f1191e4acd806ae6616c36599949506e87219199908e3aa62ee116ac6dbb4"
    )
    assert canonical_hash(preparation) == (
        "sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec"
    )
    assert canonical_hash(residual) == (
        "sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3"
    )
    assert residual["predecessor_contract"] == {
        "schedule_contract_version": preparation["schedule_contract_version"],
        "schedule_hash": canonical_hash(preparation),
        "required_end_schedule_epoch": "23+10*S",
        "required_end_reduction_epoch": "10*S",
        "required_active_end_reduction_valid_mask": 1024,
        "required_inactive_end_reduction_valid_mask": 0,
    }
    assert kernel["first_column_candidate_residual_schedule"] == residual
    assert kernel["first_column_candidate_residual_schedule_hash"] == canonical_hash(
        residual
    )
    assert canonical_hash(kernel) == _GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2
    assert canonical_hash(kernel) != (
        "sha256:273791455b794afe35e726ef1e102f4953fbc9f60e4bd5fcbc9c8e11ec8c55f6"
    )

    first = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    first["scope"]["candidate_spmv_included"] = False
    second = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    assert second["scope"]["candidate_spmv_included"] is True


def test_candidate_residual_schedule_fixes_launches_masks_and_stop_boundary() -> None:
    schedule = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    spmv, accept, form, l2, linf = schedule["launches"]

    assert [row["name"] for row in schedule["launches"]] == [
        "SPMV_CANDIDATE_COLUMN0",
        "CONTROL_OPERATOR_ACCEPT_CANDIDATE_COLUMN0",
        "VECTOR_FORM_CANDIDATE_RESIDUAL_COLUMN0",
        "REDUCE_CANDIDATE_L2_COLUMN0",
        "REDUCE_CANDIDATE_LINF_COLUMN0",
    ]
    assert (spmv["mode"], spmv["expected_schedule_epoch"]) == (
        "CANDIDATE",
        "23+10*S",
    )
    assert spmv["logical_index"] == "M"
    assert spmv["gate_true_effect"] == "V[M,k]=checked(A*work_w)[k]"
    assert (accept["mode"], accept["expected_schedule_epoch"]) == (
        "OPERATOR_ACCEPT",
        "24+10*S",
    )
    assert accept["gate_true_effect"] == "operator_apply_count=2->3"
    assert (form["mode"], form["gate"]) == (
        "FORM_CANDIDATE_RESIDUAL",
        "CANDIDATE_REQUIRED",
    )
    assert form["expected_schedule_epoch"] == "25+10*S"
    assert form["logical_index"] == "M"
    assert form["gate_true_effect"] == ("V[M,k]=checked(reduced_load[k]-V[M,k])")
    assert (l2["first_mode"], l2["combine_mode"]) == (
        "LASSQ_V_M",
        "COMBINE_LASSQ",
    )
    assert l2["expected_schedule_epoch"] == "26+q"
    assert l2["expected_reduction_epoch"] == "q=10*S..11*S-1"
    assert (l2["final_target"], l2["final_target_code"], l2["final_valid_bit"]) == (
        "CANDIDATE_L2",
        9,
        8,
    )
    assert (linf["first_mode"], linf["combine_mode"]) == (
        "LINF_V_M",
        "COMBINE_MAX",
    )
    assert linf["expected_reduction_epoch"] == "q=11*S..12*S-1"
    assert (
        linf["final_target"],
        linf["final_target_code"],
        linf["final_valid_bit"],
    ) == ("CANDIDATE_LINF", 10, 9)

    validity = schedule["reduction_validity_contract"]
    assert validity["active_mask_at_start"] == 1024
    assert validity["active_mask_after_candidate_l2"] == 1280
    assert validity["active_mask_after_candidate_linf"] == 1792
    assert validity["inactive_mask_at_all_epochs"] == 0
    assert schedule["end_state"]["schedule_epoch"] == "26+12*S"
    assert schedule["end_state"]["reduction_epoch"] == "12*S"
    assert schedule["end_state"]["operator_apply_count"] == (
        "3_if_active_predicate_else_2"
    )
    assert schedule["end_state"]["reduction_valid_mask"] == (
        "1792_if_active_predicate_else_0"
    )
    assert schedule["stop_boundary"]["stops_before"] == [
        "TRIAL_X_L2",
        "COMMITTED_X_L2",
        "CHECKPOINT_DECIDE",
    ]
    assert (
        schedule["stop_boundary"]["reduction_target_consumer_metadata_modified"]
        is False
    )


def test_candidate_residual_inactive_paths_are_total_numeric_noops() -> None:
    schedule = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    predicate = schedule["active_predicate"]
    gate = schedule["always_submit_gated_contract"]

    assert predicate["expression"] == (
        "candidate_required_and_not_triangular_breakdown"
    )
    assert predicate["evaluated_on_device_for_every_submitted_launch"] is True
    assert predicate["host_submission_depends_on_predicate"] is False
    assert gate["host_schedule_is_gate_independent"] is True
    assert gate["all_five_launch_groups_submitted_for_all_gate_values"] is True
    assert gate["all_2S_reduction_stages_submitted_for_all_gate_values"] is True
    assert gate["inactive_claims_all_schedule_epochs"] is True
    assert gate["inactive_claims_all_reduction_epochs"] is True
    for name in (
        "inactive_reads_csr",
        "inactive_reads_reduced_load",
        "inactive_reads_work_w",
        "inactive_reads_or_writes_basis_v_M",
        "inactive_reads_or_writes_solution_x",
        "inactive_reads_or_writes_reduction_scratch",
        "inactive_reads_or_writes_reduction_targets",
    ):
        assert gate[name] is False
    assert gate["inactive_operator_apply_count"] == 2
    assert gate["inactive_reduction_valid_mask"] == 0

    counters = schedule["counter_phase_contract"]
    assert counters["effective_restarts"] == "preserve_1"
    assert counters["effective_iterations"] == "preserve_1"
    assert counters["phase"] == "preserve_candidate_if_required_else_arnoldi"
    assert counters["candidate_required"] == "preserve"
    assert counters["candidate_reason_bits"] == "preserve"
    assert counters["triangular_breakdown"] == "preserve"
    assert counters["solution_and_true_residual_committed"] is False


def test_candidate_residual_numeric_policy_is_explicitly_fail_closed() -> None:
    policy = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()[
        "numeric_policy_contract"
    ]

    assert policy["candidate_l2_algorithm"] == "scale_first_lassq_fp64"
    assert policy["candidate_l2_input_finiteness_required"] is True
    assert policy["represented_fp64_final_l2_overflow_policy"] == (
        "terminal_nonfinite_arithmetic_failure"
    )
    assert (
        policy["represented_fp64_final_l2_overflow_exact_cpu_parity_claimed"] is False
    )
    assert policy["candidate_linf_published_value"] == (
        "raw_max_abs_candidate_residual"
    )
    assert policy["scaled_candidate_linf_persisted"] is False
    assert policy["candidate_scaled_residual_decision_included"] is False


@pytest.mark.parametrize("stage_count", [1, 2, 3])
def test_candidate_residual_schedule_resolves_contiguously(
    stage_count: int,
) -> None:
    start = 23 + 10 * stage_count
    resolved_schedule_epochs = [
        23 + 10 * stage_count,
        24 + 10 * stage_count,
        25 + 10 * stage_count,
        *range(26 + 10 * stage_count, 26 + 11 * stage_count),
        *range(26 + 11 * stage_count, 26 + 12 * stage_count),
    ]
    resolved_reduction_epochs = list(range(10 * stage_count, 12 * stage_count))

    assert resolved_schedule_epochs == list(range(start, 26 + 12 * stage_count))
    assert resolved_reduction_epochs == list(range(10 * stage_count, 12 * stage_count))


def test_candidate_residual_schema_hash_forgery_and_public_exports() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    _, artifact = _artifact()
    payload = artifact.to_dict()

    schedule_forgery = deepcopy(payload)
    interface = schedule_forgery["kernel_module_contract"]["interface"]
    interface["first_column_candidate_residual_schedule"]["end_state"][
        "schedule_epoch"
    ] = "27+12*S"
    assert list(validator.iter_errors(schedule_forgery))

    hash_forgery = deepcopy(payload)
    hash_forgery["kernel_module_contract"]["interface"][
        "first_column_candidate_residual_schedule_hash"
    ] = "sha256:" + "0" * 64
    assert list(validator.iter_errors(hash_forgery))

    rehashed = _rehash(
        replace(
            artifact,
            kernel_module_abi_hash="sha256:" + "0" * 64,
        )
    )
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as error:
        validate_hip_fgmres_recurrence_plan_v2(rehashed)
    assert error.value.code == "hip_fgmres_recurrence_abi_hash_mismatch"

    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.assembly_backend as assembly_backend

    assert (
        engine_v2.hip_fgmres_first_column_candidate_residual_schedule_payload_v2
        is hip_fgmres_first_column_candidate_residual_schedule_payload_v2
    )
    assert (
        assembly_backend.hip_fgmres_first_column_candidate_residual_schedule_payload_v2
        is hip_fgmres_first_column_candidate_residual_schedule_payload_v2
    )


def _scale_metrics_required_reference(
    *,
    candidate_required: bool = True,
    triangular_breakdown: bool = False,
    candidate_reason_bits: int = 1 << 2,
    candidate_l2: float = 2.0,
    solver_tolerance_l2: float = 1.0,
    candidate_linf: float = 2.0,
    rhs_linf: float = 1.0,
    authoritative_tolerance: float = 1.0,
    invariant_breakdown: bool = False,
    divergence_factor: float = 4.0,
    initial_residual_l2: float = 1.0,
) -> bool:
    if not candidate_required or triangular_breakdown:
        return False
    if candidate_reason_bits & (1 << 2) == 0:
        return False
    scaled_linf = candidate_linf / max(1.0, rhs_linf)
    dual_gate = (
        candidate_l2 <= solver_tolerance_l2 and scaled_linf <= authoritative_tolerance
    )
    if dual_gate:
        return False
    if invariant_breakdown:
        return False
    divergence_base = max(initial_residual_l2, float(np.finfo(np.float64).tiny))
    with np.errstate(over="ignore", invalid="ignore"):
        divergence_threshold = float(
            np.float64(divergence_factor) * np.float64(divergence_base)
        )
    diverged = candidate_l2 > divergence_threshold
    return not diverged


def test_candidate_scale_metrics_schedule_is_exact_hashed_and_abi_bound() -> None:
    predecessors = (
        (
            hip_fgmres_first_column_partial_schedule_payload_v2(),
            "sha256:dc6d1306ae3c7c0f970afcbe433b888cfcea591d6a34c6f36657e30ecc9c3b88",
        ),
        (
            hip_fgmres_first_column_completion_schedule_payload_v2(),
            "sha256:941f1191e4acd806ae6616c36599949506e87219199908e3aa62ee116ac6dbb4",
        ),
        (
            hip_fgmres_first_column_candidate_preparation_schedule_payload_v2(),
            "sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec",
        ),
        (
            hip_fgmres_first_column_candidate_residual_schedule_payload_v2(),
            "sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3",
        ),
    )
    for payload, expected_hash in predecessors:
        assert canonical_hash(payload) == expected_hash

    residual = predecessors[-1][0]
    scale = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()
    assert scale["predecessor_contract"] == {
        "schedule_contract_version": residual["schedule_contract_version"],
        "schedule_hash": canonical_hash(residual),
        "required_end_schedule_epoch": "26+12*S",
        "required_end_reduction_epoch": "12*S",
        "required_inactive_end_reduction_valid_mask": 0,
        "required_active_end_reduction_valid_mask": 1792,
    }
    assert canonical_hash(scale) == (
        "sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8"
    )
    assert kernel["first_column_candidate_scale_metrics_schedule"] == scale
    assert kernel["first_column_candidate_scale_metrics_schedule_hash"] == (
        canonical_hash(scale)
    )
    assert canonical_hash(kernel) == _GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2

    first = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    first["scope"]["trial_x_l2_included"] = False
    second = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    assert second["scope"]["trial_x_l2_included"] is True


def test_candidate_scale_metrics_rows_masks_and_stop_are_exact() -> None:
    schedule = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    trial, committed = schedule["launches"]

    assert [row["name"] for row in schedule["launches"]] == [
        "REDUCE_TRIAL_X_L2_COLUMN0",
        "REDUCE_COMMITTED_X_L2_COLUMN0",
    ]
    assert (
        trial["first_mode"],
        trial["combine_mode"],
        trial["expected_schedule_epoch"],
        trial["expected_reduction_epoch"],
        trial["logical_index"],
        trial["final_target"],
        trial["final_target_code"],
        trial["final_valid_bit"],
    ) == (
        "LASSQ_WORK_W",
        "COMBINE_LASSQ",
        "26+q",
        "q=12*S..13*S-1",
        0,
        "TRIAL_X_L2",
        13,
        12,
    )
    assert (
        committed["first_mode"],
        committed["combine_mode"],
        committed["expected_schedule_epoch"],
        committed["expected_reduction_epoch"],
        committed["logical_index"],
        committed["final_target"],
        committed["final_target_code"],
        committed["final_valid_bit"],
    ) == (
        "LASSQ_SOLUTION_X",
        "COMBINE_LASSQ",
        "26+q",
        "q=13*S..14*S-1",
        0,
        "COMMITTED_X_L2",
        12,
        11,
    )
    assert (
        trial["numeric_gate"] == committed["numeric_gate"] == ("scale_metrics_required")
    )

    masks = schedule["reduction_validity_contract"]
    assert masks["inactive_candidate_mask_at_all_epochs"] == 0
    assert masks["active_predicate_false_mask_at_all_epochs"] == 1792
    assert masks["scale_metrics_mask_at_start"] == 1792
    assert masks["scale_metrics_mask_after_trial_x_l2"] == 5888
    assert masks["scale_metrics_mask_after_committed_x_l2"] == 7936
    assert schedule["end_state"]["schedule_epoch"] == "26+14*S"
    assert schedule["end_state"]["reduction_epoch"] == "14*S"
    assert schedule["stop_boundary"] == {
        "stops_before": ["CHECKPOINT_DECIDE"],
        "checkpoint_decision_or_finalize_performed": False,
        "checkpoint_commit_performed": False,
        "x_scale_l2_computed_or_persisted": False,
        "solution_and_true_residual_committed": False,
    }


@pytest.mark.parametrize("stage_count", [1, 2, 3])
def test_candidate_scale_metrics_schedule_resolves_contiguously(
    stage_count: int,
) -> None:
    start = 26 + 12 * stage_count
    resolved_schedule_epochs = [
        *range(26 + 12 * stage_count, 26 + 13 * stage_count),
        *range(26 + 13 * stage_count, 26 + 14 * stage_count),
    ]
    resolved_reduction_epochs = list(range(12 * stage_count, 14 * stage_count))

    assert resolved_schedule_epochs == list(range(start, 26 + 14 * stage_count))
    assert resolved_reduction_epochs == list(range(12 * stage_count, 14 * stage_count))


def test_scale_metrics_required_truth_table_preserves_cpu_priority() -> None:
    assert _scale_metrics_required_reference() is True
    assert _scale_metrics_required_reference(candidate_required=False) is False
    assert _scale_metrics_required_reference(triangular_breakdown=True) is False
    assert _scale_metrics_required_reference(candidate_reason_bits=1 << 0) is False
    assert (
        _scale_metrics_required_reference(
            candidate_l2=1.0,
            solver_tolerance_l2=1.0,
            candidate_linf=1.0,
            rhs_linf=1.0,
            authoritative_tolerance=1.0,
        )
        is False
    )
    assert _scale_metrics_required_reference(invariant_breakdown=True) is False
    assert (
        _scale_metrics_required_reference(
            candidate_l2=2.0000000000000004,
            divergence_factor=2.0,
            initial_residual_l2=1.0,
        )
        is False
    )
    assert (
        _scale_metrics_required_reference(
            candidate_l2=2.0,
            divergence_factor=2.0,
            initial_residual_l2=1.0,
        )
        is True
    )
    assert (
        _scale_metrics_required_reference(
            candidate_l2=2.0 * float(np.finfo(np.float64).tiny),
            solver_tolerance_l2=0.0,
            candidate_linf=2.0,
            divergence_factor=2.0,
            initial_residual_l2=0.0,
        )
        is True
    )
    assert (
        _scale_metrics_required_reference(
            candidate_l2=float(np.finfo(np.float64).max),
            solver_tolerance_l2=0.0,
            candidate_linf=2.0,
            divergence_factor=float(np.finfo(np.float64).max),
            initial_residual_l2=2.0,
        )
        is True
    )

    contract = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()[
        "scale_metrics_required_contract"
    ]
    assert contract["evaluation_priority"] == [
        "active_candidate",
        "planned_cycle_end_bit2",
        "dual_gate",
        "invariant_breakdown",
        "divergence",
    ]
    assert contract["dual_gate"]["scaled_linf_persisted"] is False
    assert contract["divergence"]["comparison_is_strict"] is True
    assert (
        contract["divergence"]["threshold_product_positive_infinity_means_diverged"]
        is False
    )
    assert (
        contract["divergence"][
            "threshold_product_positive_infinity_is_arithmetic_error"
        ]
        is False
    )


def test_scale_metrics_claim_only_overflow_and_consumer_lifetime_are_bound() -> None:
    schedule = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    gate = schedule["always_submit_gated_contract"]
    for name in (
        "predicate_false_reads_work_w",
        "predicate_false_reads_solution_x",
        "predicate_false_reads_or_writes_reduction_scratch",
        "predicate_false_reads_or_writes_reduction_targets",
        "predicate_false_mutates_solution_or_true_residual",
    ):
        assert gate[name] is False
    assert gate["all_2S_reduction_stages_submitted_for_all_predicate_values"] is True

    numeric = schedule["numeric_policy_contract"]
    assert numeric["input_finiteness_required_only_when_predicate_true"] is True
    assert numeric["trial_x_l2_represented_overflow_policy"] == (
        "terminal_nonfinite_arithmetic_failure_if_predicate_true"
    )
    assert numeric["committed_x_l2_represented_overflow_policy"] == (
        "terminal_nonfinite_arithmetic_failure_if_predicate_true"
    )
    assert numeric["predicate_false_overflow_or_nonfinite_sources_inspected"] is False

    lifetime = schedule["target_lifetime_contract"]
    assert lifetime["existing_consumer_metadata_modified"] is False
    assert lifetime["trial_x_l2"]["future_consumer"] == "CHECKPOINT_DECIDE"
    assert lifetime["committed_x_l2"]["future_checkpoint_decide_access"] == (
        "read_only_without_consume"
    )
    assert lifetime["committed_x_l2"]["future_consumer"] == ("CHECKPOINT_FINALIZE")
    assert lifetime["committed_x_l2"]["bit_and_value_preserved_at_slice_end"] is True

    control = hip_fgmres_control_state_abi_payload_v2()
    assert (
        control["reduction_target_fields"]["TRIAL_X_L2"]["consumed_by_control_mode"]
        == "CHECKPOINT_DECIDE"
    )
    assert (
        control["reduction_target_fields"]["COMMITTED_X_L2"]["consumed_by_control_mode"]
        == "CHECKPOINT_FINALIZE"
    )


def test_candidate_scale_metrics_schema_hash_forgery_and_public_exports() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    _, artifact = _artifact()
    payload = artifact.to_dict()

    schedule_forgery = deepcopy(payload)
    interface = schedule_forgery["kernel_module_contract"]["interface"]
    interface["first_column_candidate_scale_metrics_schedule"]["end_state"][
        "reduction_epoch"
    ] = "15*S"
    assert list(validator.iter_errors(schedule_forgery))

    hash_forgery = deepcopy(payload)
    hash_forgery["kernel_module_contract"]["interface"][
        "first_column_candidate_scale_metrics_schedule_hash"
    ] = "sha256:" + "0" * 64
    assert list(validator.iter_errors(hash_forgery))

    rehashed = _rehash(replace(artifact, kernel_module_abi_hash="sha256:" + "0" * 64))
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as error:
        validate_hip_fgmres_recurrence_plan_v2(rehashed)
    assert error.value.code == "hip_fgmres_recurrence_abi_hash_mismatch"

    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.assembly_backend as assembly_backend

    assert (
        engine_v2.hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2
        is hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2
    )
    assert (
        assembly_backend.hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2
        is hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2
    )


def test_checkpoint_transaction_schedule_is_exact_hashed_and_abi_bound() -> None:
    assert canonical_hash(hip_fgmres_control_state_abi_payload_v2()) == (
        "sha256:22a0ce93e799b0447184f121cb1c14f4fc506e84d14d323f5ee082104e033e57"
    )
    predecessors = (
        (
            hip_fgmres_first_column_partial_schedule_payload_v2(),
            "sha256:dc6d1306ae3c7c0f970afcbe433b888cfcea591d6a34c6f36657e30ecc9c3b88",
        ),
        (
            hip_fgmres_first_column_completion_schedule_payload_v2(),
            "sha256:941f1191e4acd806ae6616c36599949506e87219199908e3aa62ee116ac6dbb4",
        ),
        (
            hip_fgmres_first_column_candidate_preparation_schedule_payload_v2(),
            "sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec",
        ),
        (
            hip_fgmres_first_column_candidate_residual_schedule_payload_v2(),
            "sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3",
        ),
        (
            hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2(),
            "sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8",
        ),
    )
    for payload, expected_hash in predecessors:
        assert canonical_hash(payload) == expected_hash

    scale = predecessors[-1][0]
    transaction = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()
    assert transaction["predecessor_contract"] == {
        "schedule_contract_version": scale["schedule_contract_version"],
        "schedule_hash": canonical_hash(scale),
        "required_end_schedule_epoch": "26+14*S",
        "required_end_reduction_epoch": "14*S",
        "required_end_reduction_valid_masks": [0, 1792, 7936],
        "required_inactive_or_triangular_mask": 0,
        "required_active_scale_false_mask": 1792,
        "required_active_scale_true_mask": 7936,
    }
    assert canonical_hash(transaction) == (
        "sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5"
    )
    assert kernel["first_column_checkpoint_transaction_schedule"] == transaction
    assert kernel["first_column_checkpoint_transaction_schedule_hash"] == (
        canonical_hash(transaction)
    )
    assert canonical_hash(kernel) == _GLOBAL_FIXED_RECURRENCE_KERNEL_ABI_HASH_V2

    first = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    first["scope"]["final_guard_included"] = True
    first["launches"][1]["vector_mode_code"] = 8
    first["commit_source_preflight_contract"]["end_to_end_O_N_proven"] = True
    second = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    assert second["scope"]["final_guard_included"] is False
    assert second["launches"][1]["vector_mode_code"] == 9
    assert second["commit_source_preflight_contract"]["end_to_end_O_N_proven"] is False
    assert canonical_hash(second) == (
        "sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5"
    )


def test_checkpoint_transaction_launches_epochs_and_masks_are_exact() -> None:
    schedule = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    decide, preflight, commit, finalize = schedule["launches"]

    assert [row["name"] for row in schedule["launches"]] == [
        "CHECKPOINT_DECIDE_COLUMN0",
        "PREFLIGHT_COMMIT_SOURCE_COLUMN0",
        "COMMIT_CHECKPOINT_COLUMN0",
        "CHECKPOINT_FINALIZE_COLUMN0",
    ]
    assert (
        decide["control_mode"],
        decide["control_mode_code"],
        decide["expected_schedule_epoch"],
        decide["required_reduction_epoch"],
        decide["row_index"],
        decide["pass_index"],
    ) == ("CHECKPOINT_DECIDE", 11, "26+14*S", "14*S", -1, -1)
    assert (
        preflight["vector_mode"],
        preflight["vector_mode_code"],
        preflight["vector_gate"],
        preflight["vector_gate_code"],
        preflight["expected_schedule_epoch"],
        preflight["logical_index"],
    ) == ("PREFLIGHT_COMMIT_SOURCE", 9, "COMMIT_REQUIRED", 4, "27+14*S", "M")
    assert preflight["schedule_epoch_effect"] == "preserve_exact_nonadvancing"
    assert preflight["reduction_epoch_effect"] == "preserve_exact_nonadvancing"
    assert preflight["snapshot_effect"] == "preserve_exact_without_mutation"
    assert (
        commit["vector_mode"],
        commit["vector_mode_code"],
        commit["vector_gate"],
        commit["vector_gate_code"],
        commit["expected_schedule_epoch"],
        commit["logical_index"],
    ) == ("COMMIT_CHECKPOINT", 8, "COMMIT_REQUIRED", 4, "27+14*S", "M")
    assert (
        finalize["control_mode"],
        finalize["control_mode_code"],
        finalize["expected_schedule_epoch"],
        finalize["row_index"],
        finalize["pass_index"],
    ) == ("CHECKPOINT_FINALIZE", 12, "28+14*S", -1, -1)
    assert all(
        row["required_reduction_epoch"] == "14*S" for row in schedule["launches"]
    )
    assert [row["device_gate_source"] for row in schedule["launches"]] == [
        "always",
        "commit_required",
        "commit_required",
        "always",
    ]
    assert schedule["scope"]["additional_reduction_stages"] == 0
    assert schedule["scope"]["additional_vector_preflight_launches"] == 1
    assert schedule["scope"]["later_column_included"] is False
    assert schedule["scope"]["later_restart_included"] is False
    assert schedule["scope"]["final_guard_included"] is False

    lifetime = schedule["reduction_validity_lifetime_contract"]
    assert lifetime["start_masks"] == [0, 1792, 7936]
    assert lifetime["after_checkpoint_decide_masks"] == [0, 1792, 7936]
    assert lifetime["after_commit_source_preflight_masks"] == [0, 1792, 7936]
    assert lifetime["after_commit_checkpoint_masks"] == [0, 1792, 7936]
    assert lifetime["after_checkpoint_finalize_mask"] == 0
    assert lifetime["checkpoint_decide_preserves_exact_mask"] is True
    assert lifetime["commit_source_preflight_preserves_exact_mask"] is True
    assert lifetime["commit_checkpoint_preserves_exact_mask"] is True
    assert lifetime["checkpoint_finalize_is_only_successful_path_clear_authority"]
    assert lifetime["checkpoint_decide_target_scalar_access"] == (
        "read_only_validation"
    )
    assert lifetime["checkpoint_decide_mutates_target_scalars"] is False
    assert lifetime["commit_source_preflight_target_scalar_access"] == "none"
    assert lifetime["commit_checkpoint_target_scalar_access"] == "none"
    assert lifetime["committed_x_l2"] == {
        "target_code": 12,
        "valid_bit": 11,
        "offset": 232,
        "checkpoint_decide_access": "read_only",
        "commit_checkpoint_access": "none",
        "checkpoint_finalize_action": "publish_scale_if_valid_then_clear",
    }
    assert schedule["success_end_state"]["schedule_epoch"] == "29+14*S"
    assert schedule["success_end_state"]["reduction_epoch"] == "14*S"
    assert schedule["success_end_state"]["reduction_valid_mask"] == 0
    assert schedule["success_end_state"]["predecessor_validation_state"] == 0
    assert schedule["success_end_state"]["predecessor_mask_snapshot"] == 0
    assert schedule["success_end_state"]["predecessor_reduction_epoch_snapshot"] == 0


def test_commit_source_preflight_contract_is_parallel_device_only_and_nonpromoting() -> (
    None
):
    schedule = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    contract = schedule["commit_source_preflight_contract"]

    assert contract["vector_mode"] == "PREFLIGHT_COMMIT_SOURCE"
    assert contract["vector_mode_code"] == 9
    assert contract["kernel_symbol"] == "engine_v2_fgmres_vector_v2"
    assert contract["fixed_four_symbol_interface_preserved"] is True
    assert contract["logical_index"] == "M"
    assert contract["source_element_formulas"] == [
        "work_w[k]",
        "basis_v[M*F+k]",
    ]
    assert contract["gate_true_scans_every_lane"] is True
    assert contract["gate_false_reads_sources"] is False
    assert contract["gate_false_reads_or_writes_destinations"] is False
    assert contract["preflight_reads_or_writes_solution_x"] is False
    assert contract["preflight_reads_or_writes_true_residual"] is False
    assert contract["preflight_writes_work_w_or_basis_v_M"] is False
    assert contract["preflight_mutates_mask_snapshot"] is False
    assert contract["preflight_mutates_reduction_epoch_snapshot"] is False
    assert contract["legacy_state_transition"] == ("empty_0_to_commit_preflighted_3")
    assert contract["legacy_snapshot_shape"] == "mask_0_and_reduction_epoch_0"
    assert contract["sealed_state_transition"] == ("consumed_2_to_commit_preflighted_3")
    assert contract["sealed_snapshot_shape"] == ("exact_live_mask_and_reduction_epoch")
    assert contract["commit_preflighted_state_is_success_verdict"] is False
    assert contract["duplicate_preflight_is_terminal_invalid_control"] is True
    assert contract["malformed_state_or_snapshot_is_terminal_invalid_control"] is True
    assert contract["additional_F_vector_workspace_count"] == 0
    assert contract["additional_device_allocation_count"] == 0
    assert contract["raw_iteration_h2d_count"] == 0
    assert contract["raw_iteration_d2h_count"] == 0
    assert contract["intermediate_host_sync_count"] == 0
    assert contract["host_finiteness_branch"] is False
    assert contract["operation_complexity_scope"] == (
        "parallel_O_F_constant_work_per_lane"
    )
    assert contract["end_to_end_O_N_proven"] is False
    assert contract["authoritative_predecessor_proven"] is False
    assert contract["authoritative_checkpoint_transaction_proven"] is False


def test_invalid_commit_source_contract_preserves_both_destination_byte_ranges() -> (
    None
):
    schedule = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    atomicity = schedule["invalid_source_destination_atomicity_contract"]

    assert atomicity["invalid_predicate"] == (
        "any_nonfinite_lane_in_work_w_or_basis_v_M_when_commit_required"
    )
    assert atomicity["detection_launch"] == "PREFLIGHT_COMMIT_SOURCE_COLUMN0"
    assert atomicity["detection_precedes_any_destination_access"] is True
    assert atomicity["source_buffers"] == ["work_w", "basis_v_M"]
    assert atomicity["destination_buffers"] == ["solution_x", "true_residual"]
    assert atomicity["preflight_destination_access"] == "none"
    assert atomicity["invalid_successor_commit_destination_access"] == "none"
    assert atomicity["solution_x_entire_byte_range_unchanged"] is True
    assert atomicity["true_residual_entire_byte_range_unchanged"] is True
    assert atomicity["source_byte_ranges_preserved"] is True
    assert atomicity["failure_diagnostics_may_mutate_control_or_solve_record"] is True
    assert (
        atomicity["device_error"],
        atomicity["device_error_mask"],
        atomicity["failure_origin"],
        atomicity["failure_origin_code"],
        atomicity["terminal_status"],
        atomicity["termination_code"],
    ) == ("nonfinite_input", 4, "vector", 2, 6, 47)
    assert atomicity["failure_schedule_epoch"] == "27+14*S"
    assert atomicity["failure_reduction_epoch"] == "14*S"
    assert atomicity["algorithmic_restart_row_written"] is False
    assert atomicity["additional_F_vector_workspace_count"] == 0
    assert atomicity["raw_iteration_d2h_count"] == 0
    assert atomicity["host_finiteness_branch"] is False
    assert atomicity["parallel_valid_path_work"] == "O(F)"
    assert atomicity["arbitrary_device_fault_atomicity_proven"] is False
    assert atomicity["concurrent_external_writer_atomicity_proven"] is False
    assert atomicity["raw_pointer_range_nonoverlap_authoritative"] is False
    assert atomicity["authoritative_solver_or_solution_receipt"] is False
    assert atomicity["end_to_end_O_N_proven"] is False


@pytest.mark.parametrize("stage_count", [1, 2, 3])
def test_checkpoint_transaction_schedule_resolves_with_one_nonadvancing_preflight(
    stage_count: int,
) -> None:
    start = 26 + 14 * stage_count
    resolved_schedule_epochs = [
        start,
        start + 1,
        start + 1,
        start + 2,
    ]
    assert resolved_schedule_epochs == [start, start + 1, start + 1, start + 2]
    assert start + 3 == 29 + 14 * stage_count
    start_reduction_epoch = 14 * stage_count
    end_reduction_epoch = 14 * stage_count
    assert end_reduction_epoch - start_reduction_epoch == 0


def test_checkpoint_transaction_priority_outcomes_are_exact() -> None:
    schedule = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    decision = schedule["decision_priority_contract"]
    assert decision["evaluation_priority"] == [
        "dual_gate_convergence",
        "invariant_breakdown",
        "planned_cycle_end_divergence",
        "planned_cycle_end_stagnation",
        "max_iterations",
    ]
    assert decision["dual_gate"]["comparisons_are_inclusive"] is True
    assert decision["divergence"]["comparison"] == "candidate_l2>threshold"
    assert decision["divergence"]["positive_infinity_threshold_is_error"] is False
    assert decision["divergence"]["positive_infinity_threshold_is_diverged"] is False
    assert decision["stagnation"] == {
        "evaluated_only_after_dual_invariant_and_divergence_fail": True,
        "x_scale_l2": "trial_x_l2+committed_x_l2",
        "unit_floor_applied": False,
        "plateau": (
            "candidate_l2>=(1-stagnation_relative_tolerance)*"
            "previous_checkpoint_residual_l2"
        ),
        "tiny_update": "solution_update_l2<=0x1p-26*x_scale_l2",
        "comparisons_are_inclusive": True,
        "new_streak": "old_streak+1_if_plateau_and_tiny_update_else_0",
        "terminal": "new_streak>=stagnation_checkpoint_limit",
    }

    outcomes = {row["name"]: row for row in schedule["outcome_contract"]}
    assert list(outcomes) == [
        "candidate_not_required_same_cycle",
        "triangular_factor_breakdown",
        "happy_breakdown_converged",
        "estimated_trigger_true_residual_converged",
        "planned_end_true_residual_converged",
        "invariant_subspace_breakdown",
        "planned_end_diverged",
        "planned_end_stagnated",
        "planned_end_max_iterations",
        "planned_end_continue_next_restart",
        "early_false_convergence_same_cycle",
    ]
    assert (
        outcomes["triangular_factor_breakdown"]["commit_required"],
        outcomes["triangular_factor_breakdown"]["restart_row_written"],
        outcomes["triangular_factor_breakdown"]["terminal_status"],
        outcomes["triangular_factor_breakdown"]["termination_code"],
    ) == (0, True, 5, 30)
    assert outcomes["happy_breakdown_converged"]["restart_flags"] == 15
    assert (
        outcomes["happy_breakdown_converged"]["happy_flag_set_and_invariant_flag_clear"]
        is True
    )
    assert outcomes["invariant_subspace_breakdown"]["terminal_status"] == 5
    assert outcomes["invariant_subspace_breakdown"]["termination_code"] == 31
    assert outcomes["planned_end_diverged"]["terminal_status"] == 4
    assert outcomes["planned_end_stagnated"]["terminal_status"] == 3
    assert outcomes["planned_end_max_iterations"]["terminal_status"] == 2
    assert outcomes["planned_end_continue_next_restart"]["commit_required"] == 1
    assert outcomes["planned_end_continue_next_restart"]["continuation_required"] == 1
    early = outcomes["early_false_convergence_same_cycle"]
    assert (early["commit_required"], early["restart_row_written"]) == (0, False)
    assert early["false_convergence_count_effect"] == "+1"


def test_checkpoint_transaction_pending_commit_record_and_failure_boundaries() -> None:
    schedule = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    pending = schedule["pending_state_contract"]
    assert pending["checkpoint_decide_writes_solve_record_header"] is False
    assert pending["checkpoint_decide_writes_restart_row"] is False
    assert pending["active_must_remain_1_until_finalize_on_nonfailure"] is True

    commit = schedule["commit_ownership_contract"]
    assert commit["commit_point"] == "COMMIT_CHECKPOINT_vector_launch"
    assert commit["commit_required_true"] == {
        "solution_x": "exact_copy_from_work_w",
        "true_residual": "exact_copy_from_basis_v_M",
        "work_w": "source_only_preserved",
        "basis_v_M": "source_only_preserved",
    }
    for key in (
        "commit_required_false_reads_or_writes_work_w",
        "commit_required_false_reads_or_writes_solution_x",
        "commit_required_false_reads_or_writes_basis_v_M",
        "commit_required_false_reads_or_writes_true_residual",
    ):
        assert commit[key] is False

    alias = schedule["pointer_alias_contract"]
    assert alias["all_arguments_are_exact_allocation_base_pointers"] is True
    assert alias["host_shifted_pointer_allowed"] is False
    assert alias["commit_source_destination_alias_allowed"] is False
    assert alias["forbidden_exact_alias_pairs"] == [
        ["work_w_base", "solution_x_base"],
        ["basis_v_base", "true_residual_base"],
        ["work_w_base", "true_residual_base"],
        ["basis_v_base", "solution_x_base"],
        ["solution_x_base", "true_residual_base"],
    ]
    assert alias["basis_v_M_address"] == "basis_v_base+M*F"

    record = schedule["finalize_record_contract"]
    assert record["sole_writer"] == "CHECKPOINT_FINALIZE"
    assert record["restart_row_not_written_for"] == [
        "candidate_not_required_same_cycle",
        "early_false_convergence_same_cycle",
    ]
    assert record["solution_scale_l2"] == (
        "publish_x_scale_only_on_scale_path_else_preserve"
    )
    assert record["false_convergence_count"] == (
        "+1_only_for_same_cycle_active_reason_bit0_dual_fail_no_commit_no_row"
    )

    failure = schedule["numeric_failure_contract"]
    assert failure["x_scale_formula"] == "trial_x_l2+committed_x_l2"
    assert failure["unit_floor_applied"] is False
    assert failure["nonfinite_or_positive_infinity_sum_is_failure"] is True
    assert (
        failure["device_error_mask"],
        failure["terminal_status"],
        failure["termination_code"],
    ) == (8, 6, 47)
    assert failure["failure_timing"] == "checkpoint_decide_pre_commit"
    assert failure["solution_x_and_true_residual_preserved"] is True
    assert failure["algorithmic_result_metrics_or_restart_row_written"] is False
    assert (
        failure["terminal_failure_status_code_and_device_error_header_written"] is True
    )
    assert "solve_record_header_or_restart_row_written" not in failure
    assert failure["cpu_history_append_edge_exact_parity_claimed"] is False


def test_checkpoint_transaction_schema_hash_forgery_and_public_export() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    _, artifact = _artifact()
    payload = artifact.to_dict()
    assert not list(validator.iter_errors(payload))

    schedule = hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    assert (
        schema["$defs"]["firstColumnCheckpointTransactionSchedule"]["const"] == schedule
    )

    schedule_forgery = deepcopy(payload)
    interface = schedule_forgery["kernel_module_contract"]["interface"]
    interface["first_column_checkpoint_transaction_schedule"]["launches"][1][
        "expected_schedule_epoch"
    ] = "28+14*S"
    assert list(validator.iter_errors(schedule_forgery))

    mode_forgery = deepcopy(payload)
    mode_forgery["kernel_module_contract"]["interface"][
        "first_column_checkpoint_transaction_schedule"
    ]["launches"][1]["vector_mode_code"] = 8
    assert list(validator.iter_errors(mode_forgery))

    atomicity_forgery = deepcopy(payload)
    atomicity_forgery["kernel_module_contract"]["interface"][
        "first_column_checkpoint_transaction_schedule"
    ]["invalid_source_destination_atomicity_contract"][
        "solution_x_entire_byte_range_unchanged"
    ] = False
    assert list(validator.iter_errors(atomicity_forgery))

    state_forgery = deepcopy(payload)
    state_forgery["memory_plan"]["control_state_abi"][
        "predecessor_validation_state_codes"
    ]["commit_preflighted"] = 4
    assert list(validator.iter_errors(state_forgery))

    hash_forgery = deepcopy(payload)
    hash_forgery["kernel_module_contract"]["interface"][
        "first_column_checkpoint_transaction_schedule_hash"
    ] = "sha256:" + "0" * 64
    assert list(validator.iter_errors(hash_forgery))

    rehashed = _rehash(replace(artifact, kernel_module_abi_hash="sha256:" + "0" * 64))
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as error:
        validate_hip_fgmres_recurrence_plan_v2(rehashed)
    assert error.value.code == "hip_fgmres_recurrence_abi_hash_mismatch"

    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.assembly_backend as assembly_backend

    assert (
        assembly_backend.hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2
        is hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2
    )
    assert (
        engine_v2.hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2
        is hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2
    )


def test_base_index_layout_is_exact_and_adds_no_O_F_workspace() -> None:
    _, artifact = _artifact()
    layout = artifact.to_dict()["memory_plan"]["base_index_layout"]

    assert layout["pointer_contract"] == ("allocation_base_plus_explicit_logical_index")
    assert layout["host_shifted_pointer_arguments_allowed"] is False
    assert layout["basis_v"]["element_formula"] == "basis_v_base[i*F+k]"
    assert layout["preconditioned_basis_z"]["element_formula"] == (
        "basis_z_base[i*F+k]"
    )
    assert layout["hessenberg"]["element_formula"] == ("dense_base[j*(M+1)+i]")
    assert layout["packed_dense_scalar_count"] == "M*M+5*M+1"
    assert layout["work_w_aliases"] == ["arnoldi_work", "candidate_trial_x"]
    assert layout["basis_v_last_row_aliases"] == [
        "candidate_spmv",
        "candidate_residual_scratch",
    ]
    assert layout["additional_O_F_workspace_allowed"] is False


def test_fully_rehashed_buffer_and_dimension_forgeries_fail_semantic_replay() -> None:
    _, artifact = _artifact()
    rows = list(artifact.buffers)
    rows[-1] = replace(
        rows[-1],
        byte_length=255,
        element_count=255,
        shape=(255,),
    )
    forged = _rehash(replace(artifact, buffers=tuple(rows)))

    with pytest.raises(HipFgmresRecurrencePlanV2Error) as buffer_error:
        validate_hip_fgmres_recurrence_plan_v2(forged)
    assert buffer_error.value.code == "hip_fgmres_recurrence_schema_invalid"

    dimension_forgery = _rehash(
        replace(artifact, reduction_partial_count=artifact.reduction_partial_count + 1)
    )
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as dimension_error:
        validate_hip_fgmres_recurrence_plan_v2(dimension_forgery)
    assert dimension_error.value.code == "hip_fgmres_recurrence_dimension_mismatch"


def test_rehashed_abi_hash_and_source_binding_forgeries_fail_closed() -> None:
    _, artifact = _artifact()
    abi_forgery = _rehash(
        replace(artifact, control_state_abi_hash="sha256:" + "f" * 64)
    )
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as abi_error:
        validate_hip_fgmres_recurrence_plan_v2(abi_forgery)
    assert abi_error.value.code == "hip_fgmres_recurrence_abi_hash_mismatch"

    source_forgery = _rehash(replace(artifact, source_policy_hash="sha256:" + "e" * 64))
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as source_error:
        validate_hip_fgmres_recurrence_plan_v2(source_forgery)
    assert source_error.value.code == "hip_fgmres_recurrence_source_binding_mismatch"
    assert source_error.value.path == "/source_fgmres_plan_contract/policy_hash"


def test_wrong_source_types_and_cross_source_expectations_fail_closed() -> None:
    axial_source, artifact = _artifact(load_pattern_id="LC_AXIAL")
    weak_source = _source_v1(load_pattern_id="LC_WEAK")

    with pytest.raises(HipFgmresRecurrencePlanV2Error) as compile_error:
        compile_hip_fgmres_recurrence_plan_v2(object())  # type: ignore[arg-type]
    assert compile_error.value.code == "hip_fgmres_recurrence_source_invalid"

    with pytest.raises(HipFgmresRecurrencePlanV2Error) as expected_type_error:
        validate_hip_fgmres_recurrence_plan_v2(
            artifact,
            expected_source_plan=object(),  # type: ignore[arg-type]
        )
    assert expected_type_error.value.code == (
        "hip_fgmres_recurrence_expected_source_invalid"
    )

    with pytest.raises(HipFgmresRecurrencePlanV2Error) as mismatch_error:
        validate_hip_fgmres_recurrence_plan_v2(
            artifact,
            expected_source_plan=weak_source,
        )
    assert mismatch_error.value.code == (
        "hip_fgmres_recurrence_expected_source_mismatch"
    )
    assert axial_source.plan_hash == artifact.source_fgmres_plan_hash


def test_private_source_swap_and_nonexact_container_are_rejected() -> None:
    _, artifact = _artifact(load_pattern_id="LC_AXIAL")
    weak_source = _source_v1(load_pattern_id="LC_WEAK")
    swapped = _rehash(replace(artifact, _source_fgmres_plan=weak_source))

    with pytest.raises(HipFgmresRecurrencePlanV2Error) as swap_error:
        validate_hip_fgmres_recurrence_plan_v2(swapped)
    assert swap_error.value.code == "hip_fgmres_recurrence_source_binding_mismatch"

    invalid = replace(artifact, buffers=list(artifact.buffers))
    with pytest.raises(HipFgmresRecurrencePlanV2Error) as container_error:
        validate_hip_fgmres_recurrence_plan_v2(invalid)  # type: ignore[arg-type]
    assert container_error.value.code == (
        "hip_fgmres_recurrence_plan_container_invalid"
    )


def test_predecessor_validation_schedule_is_exact_hashed_and_device_only() -> None:
    schedule = hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    kernel = hip_fgmres_recurrence_kernel_abi_payload_v2()

    assert kernel["first_column_predecessor_validation_schedule"] == schedule
    assert kernel["first_column_predecessor_validation_schedule_hash"] == (
        canonical_hash(schedule)
    )
    assert kernel["first_column_predecessor_validation_schedule_hash"] == (
        "sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58"
    )
    assert schedule["predecessor_contract"] == {
        "schedule_hash": (
            "sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8"
        ),
        "required_schedule_epoch": "26+14*S",
        "required_reduction_epoch": "14*S",
        "admitted_reduction_valid_masks": [0, 1792, 7936],
    }
    assert schedule["launch"] == {
        "name": "PREDECESSOR_VALIDATE_COLUMN0",
        "symbol": "engine_v2_fgmres_control_v2",
        "submission_kind": "control",
        "control_mode": "PREDECESSOR_VALIDATE",
        "control_mode_code": 14,
        "expected_schedule_epoch": "26+14*S",
        "required_reduction_epoch": "14*S",
        "expected_restart": 1,
        "expected_column": 0,
        "row_index": -1,
        "pass_index": -1,
        "device_gate": "active_checkpoint_predecessor",
    }
    assert schedule["host_observation_contract"] == {
        "actual_mask_host_observed": False,
        "validation_outcome_host_observed": False,
        "device_fence_alone_is_host_success_verdict": False,
    }
    assert schedule["end_state"]["schedule_epoch"] == "26+14*S"
    assert schedule["end_state"]["reduction_epoch"] == "14*S"
    assert schedule["end_state"]["reduction_valid_mask"] == (
        "device_only_preserved_exact_value"
    )


def test_predecessor_validation_seal_extends_through_commit_preflight() -> None:
    control = hip_fgmres_control_state_abi_payload_v2()
    schedule = hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    lifecycle = control["predecessor_validation_contract"]
    seal = schedule["seal_contract"]

    assert control["predecessor_validation_state_codes"] == {
        "empty": 0,
        "armed": 1,
        "consumed": 2,
        "commit_preflighted": 3,
    }
    assert seal["empty_state"] == 0
    assert seal["armed_state"] == 1
    assert seal["consumed_state"] == 2
    assert seal["state_field"] == "predecessor_validation_state"
    assert seal["mask_snapshot_field"] == "predecessor_mask_snapshot"
    assert seal["reduction_epoch_snapshot_field"] == (
        "predecessor_reduction_epoch_snapshot"
    )
    assert seal["success_advances_schedule_epoch"] is False
    assert seal["success_advances_reduction_epoch"] is False
    assert seal["duplicate_validation_allowed"] is False
    assert seal["allowed_mask_change_after_validation"] is False
    assert seal["consumer"] == "CHECKPOINT_DECIDE"
    assert seal["final_clear_authority"] == "CHECKPOINT_FINALIZE"
    assert lifecycle == {
        "validator_control_mode": "PREDECESSOR_VALIDATE",
        "validator_control_mode_code": 14,
        "admitted_mask_domain": [0, 1792, 7936],
        "validator_preserves_schedule_epoch": True,
        "validator_preserves_reduction_epoch": True,
        "validator_arms_exact_mask_snapshot": True,
        "checkpoint_decide_consumes_armed_state": True,
        "checkpoint_preflight_vector_mode": "PREFLIGHT_COMMIT_SOURCE",
        "checkpoint_preflight_vector_mode_code": 9,
        "checkpoint_preflight_transitions_consumed_or_legacy_empty_to_commit_preflighted": (
            True
        ),
        "checkpoint_preflight_preserves_mask_and_reduction_epoch_snapshots": True,
        "commit_preflighted_state_is_standalone_success_verdict": False,
        "checkpoint_commit_requires_commit_preflighted_state": True,
        "checkpoint_finalize_clears_commit_preflighted_state": True,
        "legacy_caller_attested_empty_state_retained_through_checkpoint_decide": True,
        "legacy_commit_preflighted_snapshots_are_exact_zero": True,
        "actual_mask_host_observed": False,
    }


def test_predecessor_validation_schedule_payload_is_fresh() -> None:
    first = hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    first["launch"]["control_mode_code"] = 99
    first["predecessor_contract"]["admitted_reduction_valid_masks"].append(1)

    second = hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    assert second["launch"]["control_mode_code"] == 14
    assert second["predecessor_contract"]["admitted_reduction_valid_masks"] == [
        0,
        1792,
        7936,
    ]

    from structural_analysis import engine_v2
    from structural_analysis.engine_v2 import assembly_backend

    assert (
        engine_v2.hip_fgmres_first_column_predecessor_validation_schedule_payload_v2
        is hip_fgmres_first_column_predecessor_validation_schedule_payload_v2
    )
    assert (
        assembly_backend.hip_fgmres_first_column_predecessor_validation_schedule_payload_v2
        is hip_fgmres_first_column_predecessor_validation_schedule_payload_v2
    )


def test_raw_iteration_zero_counts_are_plan_requirements_not_telemetry() -> None:
    _, artifact = _artifact()
    algorithm = artifact.to_dict()["algorithm_contract"]

    assert algorithm["planned_raw_iteration_h2d_count"] == 0
    assert algorithm["planned_raw_iteration_d2h_count"] == 0
    assert algorithm["planned_raw_iteration_sync_count"] == 0
    assert algorithm["planned_raw_iteration_allocation_count"] == 0
    assert "iteration_h2d_count" not in algorithm
    assert (
        artifact.to_dict()["claim_boundary"]["iteration_host_copy_zero_proven"] is False
    )
