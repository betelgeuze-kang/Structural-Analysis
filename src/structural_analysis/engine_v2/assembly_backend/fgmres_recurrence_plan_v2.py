"""Compile-time allocation and ABI overlay for HIP FGMRES recurrence v2.

This module deliberately remains a plan-only contract.  It validates and
snapshots one exact :class:`HipFgmresPlanV1`, preserves all seven borrowed and
nine owned v1 extents, and appends only the 256-byte device control state
required by the fixed host launch schedule.  It does not allocate memory,
compile a kernel, enqueue work, or claim numerical readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_global_schedule_plan_v1 import (
    hip_fgmres_global_schedule_contract_payload_v1,
)
from .fgmres_plan import (
    HIP_FGMRES_RECURRENCE_ABI_VERSION as HIP_FGMRES_RECURRENCE_ABI_VERSION_V1,
    HipFgmresBufferPlanV1,
    HipFgmresPlanV1,
    HipFgmresPlanV1Error,
    compile_hip_fgmres_plan_v1,
    hip_fgmres_solve_record_abi_payload_v1,
    validate_hip_fgmres_plan_v1,
)


HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION = (
    "structural-analysis-hip-fgmres-recurrence-plan.v2"
)
HIP_FGMRES_RECURRENCE_PLAN_V2_CAPABILITY_PROFILE = (
    "phase0_hip_fixed_restart_fgmres_full_recurrence_abi_plan"
)
HIP_FGMRES_RECURRENCE_ABI_VERSION_V2 = 2
HIP_FGMRES_CONTROL_ABI_VERSION_V2 = 2
HIP_FGMRES_CONTROL_STATE_BYTES_V2 = 256

_ZERO_HASH = "sha256:" + "0" * 64
_FIRST_COLUMN_CANDIDATE_PREPARATION_SCHEDULE_HASH_V2 = (
    "sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec"
)
_FIRST_COLUMN_CANDIDATE_RESIDUAL_SCHEDULE_HASH_V2 = (
    "sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3"
)
_FIRST_COLUMN_CANDIDATE_SCALE_METRICS_SCHEDULE_HASH_V2 = (
    "sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8"
)
_FIRST_COLUMN_PREDECESSOR_VALIDATION_SCHEDULE_HASH_V2 = (
    "sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58"
)
_CONTROL_BUFFER_NAME = "fgmres_control_state_v2"
_KERNEL_SYMBOLS = (
    "engine_v2_fgmres_control_v2",
    "engine_v2_fgmres_vector_v2",
    "engine_v2_fgmres_csr_spmv_indexed_v2",
    "engine_v2_fgmres_reduce_v2",
)

_CONTROL_I32_FIELDS = (
    "control_abi_version",
    "phase",
    "free_dof_count",
    "restart_dimension",
    "max_iterations",
    "maximum_restart_count",
    "restart_index",
    "cycle_start_iteration",
    "cycle_width",
    "column_index",
    "arnoldi_step_count",
    "reorthogonalization_count",
    "dgks_reorth_required",
    "invariant_breakdown",
    "candidate_required",
    "candidate_reason_bits",
    "triangular_breakdown",
    "commit_required",
    "continuation_required",
    "pending_terminal_status",
    "pending_termination_code",
    "pending_restart_hint",
    "pending_restart_flags",
    "stagnation_checkpoint_limit",
    "reduction_epoch",
    "reduction_valid_mask",
    "failure_origin",
    "next_expected_restart",
    "schedule_epoch",
    "predecessor_validation_state",
    "predecessor_mask_snapshot",
    "predecessor_reduction_epoch_snapshot",
)
_CONTROL_F64_FIELDS = (
    "absolute_tolerance",
    "relative_tolerance",
    "authoritative_tolerance",
    "stagnation_relative_tolerance",
    "divergence_factor",
    "cycle_beta",
    "dot_coefficient",
    "work_before_l2",
    "after_first_l2",
    "h_next_l2",
    "candidate_l2",
    "candidate_linf",
    "solution_update_l2",
    "committed_x_l2",
    "trial_x_l2",
    "x_scale_l2",
)
_PHASE_CODES = {
    "uninitialized": 0,
    "rhs_metrics": 1,
    "initial_state": 2,
    "restart_ready": 3,
    "arnoldi": 4,
    "dgks_second_pass": 5,
    "candidate": 6,
    "checkpoint_commit": 7,
    "between_restarts": 8,
    "terminal": 9,
    "failed": 10,
}
_CONTROL_MODE_CODES = {
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
_PREDECESSOR_VALIDATION_STATE_CODES = {
    "empty": 0,
    "armed": 1,
    "consumed": 2,
    "commit_preflighted": 3,
}
_FIRST_COLUMN_PREDECESSOR_MASK_DOMAIN = (0, 1792, 7936)
_VECTOR_MODE_CODES = {
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
_VECTOR_GATE_CODES = {
    "ACTIVE": 0,
    "DGKS_SECOND_PASS": 1,
    "CANDIDATE_REQUIRED": 2,
    "CYCLE_END": 3,
    "COMMIT_REQUIRED": 4,
}
_SPMV_MODE_CODES = {
    "INITIAL": 0,
    "ARNOLDI": 1,
    "CANDIDATE": 2,
}
_REDUCTION_MODE_CODES = {
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
_REDUCTION_TARGET_CODES = {
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
_REDUCTION_VALID_BITS = {
    name: bit
    for bit, name in enumerate(
        name for name in _REDUCTION_TARGET_CODES if name != "NONE"
    )
}
_CANDIDATE_REASON_BITS = {
    "estimated_l2_trigger": 0,
    "invariant_or_rotation_breakdown": 1,
    "planned_cycle_end": 2,
}
_FAILURE_ORIGIN_CODES = {
    "none": 0,
    "control": 1,
    "vector": 2,
    "csr_spmv": 3,
    "reduction": 4,
}
_DEVICE_ERROR_BITS = {
    "invalid_control_or_geometry": 0,
    "csr_structure": 1,
    "nonfinite_input": 2,
    "arithmetic_overflow": 3,
    "record_abi": 4,
    "jacobi_inverse": 5,
    "invalid_reduction_pair": 6,
}
_REDUCTION_TARGET_FIELDS = {
    "DOT": ("dot_coefficient", 176, "DOT_ACCEPT"),
    "RHS_L2": ("candidate_l2", 208, "BIND_RHS"),
    "RHS_LINF": ("candidate_linf", 216, "BIND_RHS"),
    "INITIAL_L2": ("candidate_l2", 208, "INITIAL_GATE"),
    "INITIAL_LINF": ("candidate_linf", 216, "INITIAL_GATE"),
    "WORK_BEFORE": ("work_before_l2", 184, "DGKS_DECIDE"),
    "AFTER_FIRST": ("after_first_l2", 192, "DGKS_DECIDE"),
    "H_NEXT": ("h_next_l2", 200, "ARNOLDI_GIVENS"),
    "CANDIDATE_L2": ("candidate_l2", 208, "CHECKPOINT_DECIDE"),
    "CANDIDATE_LINF": ("candidate_linf", 216, "CHECKPOINT_DECIDE"),
    "UPDATE_L2": ("solution_update_l2", 224, "CHECKPOINT_DECIDE"),
    "COMMITTED_X_L2": ("committed_x_l2", 232, "CHECKPOINT_FINALIZE"),
    "TRIAL_X_L2": ("trial_x_l2", 240, "CHECKPOINT_DECIDE"),
}


def _field_layout(
    names: tuple[str, ...], *, dtype: str, start_offset: int
) -> list[dict[str, Any]]:
    item_size = 4 if dtype == "i32" else 8
    return [
        {
            "name": name,
            "dtype": dtype,
            "offset_bytes": start_offset + index * item_size,
        }
        for index, name in enumerate(names)
    ]


def hip_fgmres_solve_record_abi_payload_v2() -> dict[str, Any]:
    """Return a fresh v2-producer view of the public solve-record ABI.

    The byte extent, field offsets, and public status/code maps remain
    compatible with the v1 artifact.  The producer recurrence version is
    intentionally 2, so a v2 kernel can never truthfully emit a v1 producer
    identity.
    """

    payload = hip_fgmres_solve_record_abi_payload_v1()
    if payload["recurrence_abi_version"] != HIP_FGMRES_RECURRENCE_ABI_VERSION_V1:
        raise RuntimeError("Unexpected source solve-record ABI version.")
    payload["recurrence_abi_version"] = HIP_FGMRES_RECURRENCE_ABI_VERSION_V2
    payload["producer_contract"] = "single_v2_code_object_only"
    payload["header_initial_values"] = {"recurrence_abi_version": 2}
    return payload


def hip_fgmres_control_state_abi_payload_v2() -> dict[str, Any]:
    """Return a fresh canonical description of the 256-byte control ABI."""

    return {
        "control_abi_version": HIP_FGMRES_CONTROL_ABI_VERSION_V2,
        "byte_order": "little_endian",
        "byte_length": HIP_FGMRES_CONTROL_STATE_BYTES_V2,
        "required_alignment_bytes": 8,
        "layout": "32*i32+16*f64",
        "fields": _field_layout(
            _CONTROL_I32_FIELDS,
            dtype="i32",
            start_offset=0,
        )
        + _field_layout(
            _CONTROL_F64_FIELDS,
            dtype="f64",
            start_offset=128,
        ),
        "transient_zero_fields": [
            "predecessor_validation_state",
            "predecessor_mask_snapshot",
            "predecessor_reduction_epoch_snapshot",
        ],
        "post_init_values": {
            "control_abi_version": 2,
            "phase": _PHASE_CODES["rhs_metrics"],
            "restart_index": 0,
            "column_index": -1,
            "reduction_epoch": 0,
            "reduction_valid_mask": 0,
            "failure_origin": 0,
            "schedule_epoch": 1,
            "predecessor_validation_state": 0,
            "predecessor_mask_snapshot": 0,
            "predecessor_reduction_epoch_snapshot": 0,
        },
        "phase_codes": dict(_PHASE_CODES),
        "control_mode_codes": dict(_CONTROL_MODE_CODES),
        "vector_mode_codes": dict(_VECTOR_MODE_CODES),
        "vector_gate_codes": dict(_VECTOR_GATE_CODES),
        "spmv_mode_codes": dict(_SPMV_MODE_CODES),
        "reduction_mode_codes": dict(_REDUCTION_MODE_CODES),
        "reduction_target_codes": dict(_REDUCTION_TARGET_CODES),
        "reduction_valid_bits": dict(_REDUCTION_VALID_BITS),
        "reduction_target_fields": {
            name: {
                "field": field,
                "offset_bytes": offset,
                "valid_bit": _REDUCTION_VALID_BITS[name],
                "consumed_by_control_mode": consumer,
            }
            for name, (field, offset, consumer) in _REDUCTION_TARGET_FIELDS.items()
        },
        "reduction_target_none_contract": {
            "code": 0,
            "publishes_control_scalar": False,
            "sets_reduction_valid_bit": False,
        },
        "transient_norm_slot_alias_contract": {
            "rhs_targets": ["RHS_L2", "RHS_LINF"],
            "rhs_consumer": "BIND_RHS",
            "rhs_consumer_clears_valid_bits": True,
            "initial_targets": ["INITIAL_L2", "INITIAL_LINF"],
            "initial_consumer": "INITIAL_GATE",
            "initial_metrics_may_overwrite_only_after_rhs_bits_cleared": True,
        },
        "candidate_reason_bits": dict(_CANDIDATE_REASON_BITS),
        "failure_origin_codes": dict(_FAILURE_ORIGIN_CODES),
        "predecessor_validation_state_codes": dict(_PREDECESSOR_VALIDATION_STATE_CODES),
        "predecessor_validation_contract": {
            "validator_control_mode": "PREDECESSOR_VALIDATE",
            "validator_control_mode_code": _CONTROL_MODE_CODES["PREDECESSOR_VALIDATE"],
            "admitted_mask_domain": list(_FIRST_COLUMN_PREDECESSOR_MASK_DOMAIN),
            "validator_preserves_schedule_epoch": True,
            "validator_preserves_reduction_epoch": True,
            "validator_arms_exact_mask_snapshot": True,
            "checkpoint_decide_consumes_armed_state": True,
            "checkpoint_preflight_vector_mode": "PREFLIGHT_COMMIT_SOURCE",
            "checkpoint_preflight_vector_mode_code": _VECTOR_MODE_CODES[
                "PREFLIGHT_COMMIT_SOURCE"
            ],
            "checkpoint_preflight_transitions_consumed_or_legacy_empty_to_commit_preflighted": (
                True
            ),
            "checkpoint_preflight_preserves_mask_and_reduction_epoch_snapshots": (True),
            "commit_preflighted_state_is_standalone_success_verdict": False,
            "checkpoint_commit_requires_commit_preflighted_state": True,
            "checkpoint_finalize_clears_commit_preflighted_state": True,
            "legacy_caller_attested_empty_state_retained_through_checkpoint_decide": (
                True
            ),
            "legacy_commit_preflighted_snapshots_are_exact_zero": True,
            "actual_mask_host_observed": False,
        },
        "whole_buffer_zeroed_before_init": True,
        "init_zero_prestate_exception": {
            "allowed_control_mode": "INIT",
            "required_prestate": "all_256_bytes_exact_zero",
            "only_exception_to_control_abi_field_validation": True,
            "nonzero_malformed_prestate_rejected": True,
        },
        "transient_validation_fields_zero_outside_checkpoint_transaction": True,
        "host_scalar_publish_allowed_during_recurrence": False,
    }


def hip_fgmres_first_column_partial_schedule_payload_v2() -> dict[str, Any]:
    """Return the canonical first-restart/column-zero schedule boundary.

    ``S`` is the exact launch count of one recursive 512-value reduction
    tree, including its first stage and every combine stage.  The payload is
    deliberately symbolic in ``S`` and ``M`` so one module ABI covers every
    admitted plan while still fixing every launch coordinate and transition.
    The enclosing kernel ABI publishes a canonical hash of this fresh value.
    """

    return {
        "schedule_contract_version": (
            "structural-analysis-hip-fgmres-first-column-partial-schedule.v2"
        ),
        "scope": {
            "restart_numbering": "one_based",
            "restart_index": 1,
            "column_index": 0,
            "included_through": "DGKS_DECIDE",
            "schedule_epoch_B_owner": "RESTART_BEGIN",
            "initial_final_guard_at_B_allowed": False,
            "first_pass_mgs_included": True,
            "device_dgks_decision_included": True,
            "second_pass_mgs_included": False,
            "h_next_reduction_included": False,
            "givens_included": False,
            "candidate_included": False,
            "checkpoint_commit_included": False,
            "full_column_complete": False,
            "full_recurrence_complete": False,
        },
        "symbols": {
            "F": "free_dof_count",
            "M": "restart_dimension",
            "I": "max_iterations",
            "S": "recursive_stage_count(F,ceil(F/512))",
            "B": "7+4*S",
        },
        "start_state": {
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
        },
        "launches": [
            {
                "name": "CONTROL_RESTART_BEGIN",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "RESTART_BEGIN",
                "expected_schedule_epoch": "B",
                "expected_restart": 1,
                "expected_column": -1,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "restart_ready",
                "phase_after": "arnoldi",
                "accepted_effect": (
                    "restart_index=1,column_index=0,next_expected_restart=2,"
                    "effective_restarts=1,cycle_start_iteration=0,"
                    "cycle_width=min(M,I),cycle_beta=initial_true_residual_l2,"
                    "zero_dense_then_set_g[0]=cycle_beta"
                ),
            },
            {
                "name": "VECTOR_NORMALIZE_V0",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "NORMALIZE_V0",
                "gate": "ACTIVE",
                "expected_schedule_epoch": "B+1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "V[0,k]=true_residual[k]/cycle_beta",
            },
            {
                "name": "VECTOR_APPLY_JACOBI",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "APPLY_JACOBI_INDEXED",
                "gate": "ACTIVE",
                "expected_schedule_epoch": "B+2",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "Z[0,k]=inverse_diagonal[k]*V[0,k]",
            },
            {
                "name": "CONTROL_PRECONDITION_ACCEPT",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "PRECONDITION_ACCEPT",
                "expected_schedule_epoch": "B+3",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "preconditioner_apply_count=0->1",
            },
            {
                "name": "SPMV_ARNOLDI",
                "symbol": "engine_v2_fgmres_csr_spmv_indexed_v2",
                "mode": "ARNOLDI",
                "expected_schedule_epoch": "B+4",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "work_w=A*Z[0]",
            },
            {
                "name": "CONTROL_OPERATOR_ACCEPT",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "OPERATOR_ACCEPT",
                "expected_schedule_epoch": "B+5",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "operator_apply_count=1->2",
            },
            {
                "name": "REDUCE_WORK_BEFORE",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_WORK_W",
                "combine_mode": "COMBINE_LASSQ",
                "expected_schedule_epoch": "13+q",
                "expected_reduction_epoch": "q=4*S..5*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "intermediate_target": "NONE",
                "final_target": "WORK_BEFORE",
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "final_stage_sets_valid_bit_5_mask_32",
            },
            {
                "name": "REDUCE_DOT_FIRST_PASS_ROW0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "DOT_W_VI",
                "combine_mode": "COMBINE_SUM",
                "expected_schedule_epoch": "13+q",
                "expected_reduction_epoch": "q=5*S..6*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "orthogonalization_row": 0,
                "orthogonalization_pass": 0,
                "intermediate_target": "NONE",
                "final_target": "DOT",
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "final_stage_sets_valid_bit_0_mask_33",
            },
            {
                "name": "CONTROL_DOT_ACCEPT_ROW0_PASS0",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "DOT_ACCEPT",
                "expected_schedule_epoch": "13+6*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": 0,
                "pass_index": 0,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "required_valid_mask": 33,
                "result_valid_mask": 32,
                "accepted_effect": (
                    "y[0]=dot_coefficient,H[0,0]+=y[0],"
                    "clear_DOT_bit_and_dot_coefficient"
                ),
            },
            {
                "name": "VECTOR_MGS_SUBTRACT_ROW0_PASS0",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "MGS_SUBTRACT_INDEXED",
                "gate": "ACTIVE",
                "expected_schedule_epoch": "14+6*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "orthogonalization_row": 0,
                "orthogonalization_pass": 0,
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "work_w[k]-=y[0]*V[0,k]",
            },
            {
                "name": "REDUCE_AFTER_FIRST",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_WORK_W",
                "combine_mode": "COMBINE_LASSQ",
                "expected_schedule_epoch": "15+q",
                "expected_reduction_epoch": "q=6*S..7*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "intermediate_target": "NONE",
                "final_target": "AFTER_FIRST",
                "phase_before": "arnoldi",
                "phase_after": "arnoldi",
                "accepted_effect": "final_stage_sets_valid_bit_6_mask_96",
            },
            {
                "name": "CONTROL_DGKS_DECIDE_PASS0",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "DGKS_DECIDE",
                "expected_schedule_epoch": "15+7*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": 0,
                "phase_before": "arnoldi",
                "phase_after": (
                    "dgks_second_pass_if_after_first_lt_0.717_times_"
                    "work_before_else_arnoldi"
                ),
                "required_valid_mask": 96,
                "result_valid_mask": 0,
                "accepted_effect": (
                    "set_dgks_reorth_required,consume_WORK_BEFORE_and_"
                    "AFTER_FIRST_bits,preserve_work_before_l2"
                ),
            },
        ],
        "reduction_validity_contract": {
            "target_codes": {"DOT": 1, "WORK_BEFORE": 6, "AFTER_FIRST": 7},
            "valid_bits": {"DOT": 0, "WORK_BEFORE": 5, "AFTER_FIRST": 6},
            "mask_at_start": 0,
            "mask_after_work_before": 32,
            "mask_after_dot": 33,
            "dot_accept_consumes": ["DOT"],
            "mask_after_dot_accept": 32,
            "mask_after_after_first": 96,
            "dgks_decide_consumes": ["WORK_BEFORE", "AFTER_FIRST"],
            "mask_after_dgks_decide": 0,
            "intermediate_stages_use_none_target": True,
            "only_final_stages_publish_named_target": True,
        },
        "dense_transient_contract": {
            "offset_unit": "fp64_elements_from_dense_base",
            "h_0_0_element_offset": 0,
            "h_0_0_byte_offset": 0,
            "g_0_element_offset": "M*(M+1)+2*M",
            "g_0_byte_offset": "8*(M*(M+1)+2*M)",
            "y_0_element_offset": "M*(M+1)+3*M+1",
            "y_0_byte_offset": "8*(M*(M+1)+3*M+1)",
            "restart_begin_h_initialization": "H[:,:]=0",
            "restart_begin_g_initialization": "g[:]=0;g[0]=cycle_beta",
            "dot_accept_update": "y[0]=dot_coefficient;H[0,0]+=y[0]",
            "mgs_coefficient_source": "y[0]",
            "y_storage_before_backsolve": "triangular_solution_alias",
            "mgs_reads_h_0_0_directly": False,
        },
        "counter_acceptance_contract": {
            "multi_block_launches_increment_record_counters": False,
            "restart_begin_accepts_effective_restarts": "0->1",
            "precondition_accept_accepts_count": "0->1",
            "operator_accept_accepts_count": "1->2",
            "effective_iterations_incremented": False,
            "arnoldi_step_count_incremented": False,
            "reorthogonalization_count_incremented": False,
            "late_multiblock_failure_before_accept_may_leave_count_unadvanced": True,
            "failure_count_parity_proven": False,
        },
        "end_state": {
            "schedule_epoch": "16+7*S",
            "reduction_epoch": "7*S",
            "phase": (
                "dgks_second_pass_if_after_first_lt_0.717_times_"
                "work_before_else_arnoldi"
            ),
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 0,
            "arnoldi_step_count": 0,
            "reorthogonalization_count": 0,
            "operator_apply_count": 2,
            "preconditioner_apply_count": 1,
            "reduction_valid_mask": 0,
            "dgks_reorth_required": "1_if_after_first<0.717*work_before_else_0",
        },
    }


def hip_fgmres_first_column_completion_schedule_payload_v2() -> dict[str, Any]:
    """Return the canonical column-zero continuation through Givens accept.

    This payload starts at the exact terminal state of
    :func:`hip_fgmres_first_column_partial_schedule_payload_v2`.  It preserves
    the four-symbol ABI and fixes the gated DGKS second pass, H-next tree,
    multi-block V1 normalization, and the following single-block Givens
    acceptance without claiming the candidate envelope or a full recurrence.
    """

    partial = hip_fgmres_first_column_partial_schedule_payload_v2()
    return {
        "schedule_contract_version": (
            "structural-analysis-hip-fgmres-first-column-completion-schedule.v2"
        ),
        "predecessor_contract": {
            "schedule_contract_version": partial["schedule_contract_version"],
            "schedule_hash": canonical_hash(partial),
            "required_end_schedule_epoch": "16+7*S",
            "required_end_reduction_epoch": "7*S",
            "required_end_reduction_valid_mask": 0,
        },
        "scope": {
            "restart_numbering": "one_based",
            "restart_index": 1,
            "column_index": 0,
            "included_from": "DGKS_DECIDE_ACCEPTED_STATE",
            "included_through": "ARNOLDI_GIVENS",
            "dgks_second_pass_included": True,
            "h_next_reduction_included": True,
            "v_next_normalization_included": True,
            "givens_included": True,
            "normalization_precedes_givens": True,
            "vector_accept_used_for_v_next": False,
            "candidate_envelope_included": False,
            "backsubstitute_included": False,
            "checkpoint_commit_included": False,
            "full_recurrence_complete": False,
        },
        "symbols": {
            "F": "free_dof_count",
            "M": "restart_dimension",
            "I": "max_iterations",
            "S": "recursive_stage_count(F,ceil(F/512))",
            "tau": "64*binary64_epsilon=2^-46",
        },
        "start_state": {
            "schedule_epoch": "16+7*S",
            "reduction_epoch": "7*S",
            "phase": "dgks_second_pass_if_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 0,
            "arnoldi_step_count": 0,
            "reorthogonalization_count": 0,
            "operator_apply_count": 2,
            "preconditioner_apply_count": 1,
            "reduction_valid_mask": 0,
            "dgks_reorth_required": "0_or_1_from_strict_dgks_decision",
        },
        "launches": [
            {
                "name": "REDUCE_DOT_SECOND_PASS_ROW0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "DOT_W_VI",
                "combine_mode": "COMBINE_SUM",
                "gate_source": "dgks_reorth_required",
                "expected_schedule_epoch": "16+q",
                "expected_reduction_epoch": "q=7*S..8*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "orthogonalization_row": 0,
                "orthogonalization_pass": 1,
                "intermediate_target": "NONE",
                "final_target": "DOT",
                "phase_before": "dgks_second_pass_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": "final_stage_sets_DOT_valid_bit_0_mask_1",
                "gate_false_effect": (
                    "claim_schedule_and_reduction_epochs_without_numeric_"
                    "read_write_or_target_publish"
                ),
            },
            {
                "name": "CONTROL_DOT_ACCEPT_ROW0_PASS1",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "DOT_ACCEPT",
                "gate_source": "dgks_reorth_required",
                "expected_schedule_epoch": "16+8*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": 0,
                "pass_index": 1,
                "phase_before": "dgks_second_pass_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "required_valid_mask": "1_if_gate_true_else_0",
                "result_valid_mask": 0,
                "gate_true_effect": (
                    "y[0]=dot_coefficient,H[0,0]=checked(H[0,0]+y[0]),"
                    "clear_DOT_bit_and_dot_coefficient"
                ),
                "gate_false_effect": "y[0]=positive_zero,H[0,0]_unchanged",
            },
            {
                "name": "VECTOR_MGS_SUBTRACT_ROW0_PASS1",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "MGS_SUBTRACT_INDEXED",
                "gate": "DGKS_SECOND_PASS",
                "expected_schedule_epoch": "17+8*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "orthogonalization_row": 0,
                "orthogonalization_pass": 1,
                "phase_before": "dgks_second_pass_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": "work_w[k]=checked(work_w[k]-y[0]*V[0,k])",
                "gate_false_effect": "claim_schedule_without_vector_read_or_write",
            },
            {
                "name": "REDUCE_H_NEXT",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_WORK_W",
                "combine_mode": "COMBINE_LASSQ",
                "expected_schedule_epoch": "18+q",
                "expected_reduction_epoch": "q=8*S..9*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "intermediate_target": "NONE",
                "final_target": "H_NEXT",
                "phase_before": "dgks_second_pass_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "accepted_effect": "final_stage_sets_H_NEXT_valid_bit_7_mask_128",
            },
            {
                "name": "VECTOR_NORMALIZE_V1",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "NORMALIZE_V_NEXT",
                "gate": "ACTIVE",
                "expected_schedule_epoch": "18+9*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 1,
                "phase_before": "dgks_second_pass_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "required_valid_mask": 128,
                "result_valid_mask": 128,
                "accepted_effect": (
                    "if_h_next_le_tau_times_work_before_set_invariant_and_"
                    "V[1,:]=positive_zero_else_V[1,k]=checked(work_w[k]/h_next)"
                ),
            },
            {
                "name": "CONTROL_ARNOLDI_GIVENS_COLUMN0",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "ARNOLDI_GIVENS",
                "expected_schedule_epoch": "19+9*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "dgks_second_pass_if_required_else_arnoldi",
                "phase_after": "candidate_if_reason_bits_nonzero_else_arnoldi",
                "required_valid_mask": 128,
                "result_valid_mask": 0,
                "accepted_effect": (
                    "accept_normalized_or_breakdown_zero_V1,apply_column0_"
                    "givens,publish_metrics_and_counts,retain_column_0"
                ),
            },
        ],
        "gated_second_pass_contract": {
            "host_schedule_is_flag_independent": True,
            "all_S_dot_stages_submitted_for_both_gate_values": True,
            "gate_false_claims_schedule_epoch": True,
            "gate_false_claims_reduction_epoch": True,
            "gate_false_reads_numeric_vectors": False,
            "gate_false_writes_reduction_scratch": False,
            "gate_false_publishes_dot_target_or_valid_bit": False,
            "gate_false_dot_accept_requires_mask": 0,
            "gate_false_mgs_reads_or_writes_vector": False,
            "gate_true_dot_accept_requires_mask": 1,
            "reorthogonalization_count_increments_at_givens_accept_only": True,
        },
        "reduction_validity_contract": {
            "target_codes": {"DOT": 1, "H_NEXT": 8},
            "valid_bits": {"DOT": 0, "H_NEXT": 7},
            "mask_at_start": 0,
            "mask_after_second_dot": "1_if_dgks_required_else_0",
            "dot_accept_consumes": ["DOT_if_dgks_required"],
            "mask_after_second_dot_accept": 0,
            "mask_after_h_next": 128,
            "normalization_preserves": ["H_NEXT"],
            "givens_consumes": ["H_NEXT"],
            "mask_at_end": 0,
            "intermediate_stages_use_none_target": True,
            "only_active_final_stages_publish_named_target": True,
        },
        "arithmetic_contract": {
            "binary64_epsilon_hex": "0x1.0000000000000p-52",
            "tau_hex": "0x1.0000000000000p-46",
            "tau_decimal": 1.4210854715202004e-14,
            "fp_contraction_allowed": False,
            "second_dot": "fixed_256_thread_512_value_product_then_sum_tree",
            "h_accumulation": "H[0,0]=checked(H[0,0]+second_dot)",
            "second_mgs": "work_w[k]=checked(work_w[k]-second_dot*V[0,k])",
            "h_next": "fixed_256_thread_512_value_scale_first_LASSQ(work_w)",
            "invariant_breakdown_threshold": "tau*work_before_l2",
            "invariant_breakdown_comparison": "h_next_l2<=threshold",
            "threshold_has_unit_floor": False,
            "normalize_before_givens": True,
            "normalization_breakdown_effect": "V[1,:]=positive_zero_without_division",
            "normalization_active_effect": "V[1,k]=checked(work_w[k]/h_next_l2)",
            "rotation_prior_row_count": 0,
            "rotation_upper": "u=H[0,0]",
            "rotation_lower": "l=H[1,0]=h_next_l2",
            "rotation_norm": "rho=hypot(u,l)",
            "rotation_scale": "max(abs(u),abs(l))",
            "rotation_breakdown_threshold": "tau*rotation_scale",
            "rotation_breakdown_comparison": (
                "not_finite(rho)_or_rho<=rotation_breakdown_threshold"
            ),
            "rotation_breakdown_effect": (
                "invariant_breakdown=1,c[0]=1,s[0]=0,H_entries_unchanged"
            ),
            "rotation_active_effect": (
                "c[0]=u/rho,s[0]=l/rho,H[0,0]=rho,H[1,0]=positive_zero"
            ),
            "signed_rotation_convention": ("[u';l']=[c*u+s*l;-s*u+c*l],g[1]=-s*g_old"),
            "g_update_order": (
                "g_old=g[0];g[0]=checked(c[0]*g_old);g[1]=checked(-s[0]*g_old)"
            ),
            "estimated_residual": "abs(g[1])",
            "all_stored_zero_values_are_positive_zero": True,
        },
        "dense_contract": {
            "offset_unit": "fp64_elements_from_dense_base",
            "h_0_0_element_offset": 0,
            "h_1_0_element_offset": 1,
            "c_0_element_offset": "M*(M+1)",
            "s_0_element_offset": "M*(M+1)+M",
            "g_0_element_offset": "M*(M+1)+2*M",
            "g_1_element_offset": "M*(M+1)+2*M+1",
            "y_0_element_offset": "M*(M+1)+3*M+1",
            "y_0_role_before_givens": "second_pass_dot_transient_or_positive_zero",
            "rotation_only_breakdown_retains_normalized_unused_V1": True,
        },
        "candidate_contract": {
            "reason_bits": {
                "estimated_l2_trigger": 0,
                "invariant_or_rotation_breakdown": 1,
                "planned_cycle_end": 2,
            },
            "estimated_l2_trigger": "estimated_residual_l2<=solver_tolerance_l2",
            "breakdown_trigger": "invariant_breakdown!=0",
            "planned_cycle_end_trigger": "column_index+1>=cycle_width",
            "reason_bits_are_bitwise_or": True,
            "candidate_required": "1_if_reason_bits_nonzero_else_0",
            "phase_after_givens": "candidate_if_required_else_arnoldi",
            "candidate_schedule_included_here": False,
        },
        "counter_record_acceptance_contract": {
            "normalization_changes_counters_or_public_record": False,
            "givens_is_the_accept_after_multiblock_normalization": True,
            "effective_iterations": "0->1",
            "arnoldi_step_count": "0->1",
            "effective_arnoldi_dimension": "0->1",
            "reorthogonalization_count": "0->dgks_reorth_required",
            "operator_apply_count": "preserve_2",
            "preconditioner_apply_count": "preserve_1",
            "happy_breakdown_count": "preserve_0_until_true_residual_checkpoint",
            "record_estimated_residual_l2": {
                "offset_bytes": 152,
                "value": "abs(g[1])",
            },
            "record_arnoldi_work_l2": {
                "offset_bytes": 160,
                "value": "work_before_l2",
            },
            "record_arnoldi_breakdown_threshold": {
                "offset_bytes": 168,
                "value": "tau*work_before_l2",
            },
            "solution_and_true_residual_record_fields_change": False,
            "late_normalization_failure_advances_counts_or_record_metrics": False,
        },
        "column_phase_contract": {
            "column_index_after_givens": 0,
            "candidate_required_true_phase": "candidate",
            "candidate_required_false_phase": "arnoldi",
            "fixed_candidate_envelope_uses_expected_column": 0,
            "no_candidate_envelope_still_submitted_as_gated_noops": True,
            "advance_to_column_1_at_givens_or_normalization": False,
            "advance_authority": "future_CHECKPOINT_FINALIZE_column_boundary",
        },
        "end_state": {
            "schedule_epoch": "20+9*S",
            "reduction_epoch": "9*S",
            "phase": "candidate_if_reason_bits_nonzero_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "reorthogonalization_count": "0_or_1_from_consumed_dgks_flag",
            "operator_apply_count": 2,
            "preconditioner_apply_count": 1,
            "reduction_valid_mask": 0,
            "dgks_reorth_required": 0,
            "candidate_required": "1_if_candidate_reason_bits_nonzero_else_0",
            "candidate_reason_bits": "bitwise_or_of_bits_0_1_2",
            "solution_and_true_residual_committed": False,
        },
    }


def hip_fgmres_first_column_candidate_preparation_schedule_payload_v2() -> dict[
    str, Any
]:
    """Return the canonical column-zero candidate-preparation prefix.

    The prefix starts at the exact accepted end of the first-column
    through-Givens contract.  It fixes scale-relative back substitution,
    construction of the trial solution, the deterministic solution-update
    norm, and its single-block acceptance.  Candidate SpMV/true-residual
    replay and every checkpoint decision or commit remain outside this
    contract.
    """

    completion = hip_fgmres_first_column_completion_schedule_payload_v2()
    return {
        "schedule_contract_version": (
            "structural-analysis-hip-fgmres-first-column-candidate-"
            "preparation-schedule.v2"
        ),
        "predecessor_contract": {
            "schedule_contract_version": completion["schedule_contract_version"],
            "schedule_hash": canonical_hash(completion),
            "required_end_schedule_epoch": "20+9*S",
            "required_end_reduction_epoch": "9*S",
            "required_end_reduction_valid_mask": 0,
        },
        "scope": {
            "restart_numbering": "one_based",
            "restart_index": 1,
            "column_index": 0,
            "included_from": "ARNOLDI_GIVENS_ACCEPTED_STATE",
            "included_through": "VECTOR_ACCEPT",
            "candidate_preparation_included": True,
            "backsubstitute_included": True,
            "trial_vector_build_included": True,
            "solution_update_l2_included": True,
            "vector_accept_included": True,
            "candidate_false_claim_only": True,
            "triangular_breakdown_claim_only_after_backsubstitute": True,
            "candidate_true_residual_included": False,
            "candidate_spmv_included": False,
            "checkpoint_decide_included": False,
            "checkpoint_commit_included": False,
            "full_recurrence_complete": False,
        },
        "symbols": {
            "F": "free_dof_count",
            "M": "restart_dimension",
            "S": "recursive_stage_count(F,ceil(F/512))",
            "tau": "64*binary64_epsilon=2^-46",
        },
        "start_state": {
            "schedule_epoch": "20+9*S",
            "reduction_epoch": "9*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": 2,
            "preconditioner_apply_count": 1,
            "reduction_valid_mask": 0,
            "candidate_required": "0_or_1_from_candidate_reason_bits",
            "triangular_breakdown": 0,
            "invariant_breakdown": "0_or_1_from_givens",
        },
        "launches": [
            {
                "name": "CONTROL_BACKSUBSTITUTE_COLUMN0",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "BACKSUBSTITUTE",
                "gate_source": "candidate_required",
                "expected_schedule_epoch": "20+9*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "required_valid_mask": 0,
                "result_valid_mask": 0,
                "gate_true_success_effect": (
                    "triangular_scale=abs(H[0,0]),y[0]=checked(g[0]/H[0,0]),"
                    "triangular_breakdown=0,invariant_breakdown=preserve"
                ),
                "gate_true_pivot_breakdown_effect": (
                    "triangular_scale=abs(H[0,0]),y[0]=positive_zero,"
                    "triangular_breakdown=1,invariant_breakdown=1"
                ),
                "gate_false_effect": (
                    "claim_schedule_without_dense_read_or_write_and_preserve_"
                    "triangular_breakdown_zero_and_invariant_breakdown"
                ),
            },
            {
                "name": "VECTOR_BUILD_TRIAL_X_COLUMN0",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "BUILD_TRIAL_X",
                "gate": "CANDIDATE_REQUIRED",
                "numeric_gate": "candidate_required_and_not_triangular_breakdown",
                "expected_schedule_epoch": "21+9*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": ("work_w[k]=checked(solution_x[k]+y[0]*Z[0,k])"),
                "gate_false_effect": (
                    "claim_schedule_without_solution_basis_dense_or_work_"
                    "vector_read_or_write"
                ),
            },
            {
                "name": "REDUCE_SOLUTION_UPDATE_L2_COLUMN0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_WORK_W_MINUS_X",
                "combine_mode": "COMBINE_LASSQ",
                "numeric_gate": "candidate_required_and_not_triangular_breakdown",
                "expected_schedule_epoch": "22+q",
                "expected_reduction_epoch": "q=9*S..10*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "intermediate_target": "NONE",
                "final_target": "UPDATE_L2",
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": "final_stage_sets_UPDATE_L2_valid_bit_10_mask_1024",
                "gate_false_effect": (
                    "claim_all_schedule_and_reduction_epochs_without_numeric_"
                    "read_write_or_target_publish"
                ),
            },
            {
                "name": "CONTROL_VECTOR_ACCEPT_TRIAL_COLUMN0",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "VECTOR_ACCEPT",
                "gate_source": ("candidate_required_and_not_triangular_breakdown"),
                "expected_schedule_epoch": "22+10*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "required_valid_mask": (
                    "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
                ),
                "result_valid_mask": "same_as_required_valid_mask",
                "gate_true_effect": (
                    "accept_finite_nonnegative_solution_update_l2_and_"
                    "preserve_UPDATE_L2_for_future_CHECKPOINT_DECIDE"
                ),
                "gate_false_effect": (
                    "claim_schedule_without_scalar_vector_or_record_mutation"
                ),
            },
        ],
        "backsubstitution_contract": {
            "active_count": 1,
            "upper_factor_scale": "max_abs(H[0:1,0:1])=abs(H[0,0])",
            "pivot": "H[0,0]",
            "pivot_floor": "tau*upper_factor_scale",
            "pivot_breakdown_comparison": (
                "upper_factor_scale==0_or_abs(pivot)<=pivot_floor"
            ),
            "pivot_floor_has_unit_floor": False,
            "nonfinite_scale_or_pivot_is_arithmetic_failure": True,
            "triangular_solution": "y[0]=checked(g[0]/H[0,0])",
            "candidate_false_reads_or_writes_dense": False,
            "pivot_breakdown_promotes_invariant_breakdown": True,
            "success_preserves_preexisting_invariant_breakdown": True,
            "candidate_false_preserves_preexisting_invariant_breakdown": True,
            "triangular_scale_record_offset_bytes": 176,
        },
        "trial_vector_contract": {
            "formula": "work_w[k]=solution_x[k]+y[0]*Z[0,k]",
            "evaluation_order": "multiply_then_add_without_fp_contraction",
            "all_stored_zero_values_are_positive_zero": True,
            "work_w_role_after_build": "candidate_trial_x",
            "additional_O_F_workspace_allowed": False,
        },
        "gated_preparation_contract": {
            "host_schedule_is_candidate_flag_independent": True,
            "all_four_launch_groups_submitted_for_both_candidate_values": True,
            "all_S_update_stages_submitted_for_all_gate_values": True,
            "candidate_false_claims_schedule_epochs": True,
            "candidate_false_claims_reduction_epochs": True,
            "candidate_false_reads_numeric_data": False,
            "candidate_false_writes_numeric_data_or_reduction_scratch": False,
            "candidate_false_publishes_target_or_valid_bit": False,
            "triangular_breakdown_claims_remaining_schedule_epochs": True,
            "triangular_breakdown_claims_update_reduction_epochs": True,
            "triangular_breakdown_reads_or_writes_trial_numeric_data": False,
            "triangular_breakdown_publishes_update_target_or_valid_bit": False,
        },
        "reduction_validity_contract": {
            "target_code": {"UPDATE_L2": 11},
            "valid_bit": {"UPDATE_L2": 10},
            "mask_at_start": 0,
            "mask_after_update_tree": (
                "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
            ),
            "vector_accept_requires": (
                "UPDATE_L2_if_candidate_required_and_not_triangular_breakdown_else_none"
            ),
            "vector_accept_preserves": ["UPDATE_L2_if_present"],
            "mask_at_end": (
                "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
            ),
            "future_consumer": "CHECKPOINT_DECIDE",
            "intermediate_stages_use_none_target": True,
            "only_active_final_stage_publishes_named_target": True,
        },
        "dense_contract": {
            "offset_unit": "fp64_elements_from_dense_base",
            "h_0_0_element_offset": 0,
            "g_0_element_offset": "M*(M+1)+2*M",
            "y_0_element_offset": "M*(M+1)+3*M+1",
            "z_0_element_formula": "basis_z_base[0*F+k]",
        },
        "counter_phase_contract": {
            "effective_restarts": "preserve_1",
            "effective_iterations": "preserve_1",
            "arnoldi_step_count": "preserve_1",
            "effective_arnoldi_dimension": "preserve_1",
            "operator_apply_count": "preserve_2",
            "preconditioner_apply_count": "preserve_1",
            "phase": "preserve_candidate_if_required_else_arnoldi",
            "column_index": "preserve_0",
            "candidate_required": "preserve",
            "candidate_reason_bits": "preserve",
            "invariant_breakdown": (
                "preserve_unless_active_pivot_breakdown_promotes_to_1"
            ),
            "solution_and_true_residual_committed": False,
        },
        "end_state": {
            "schedule_epoch": "23+10*S",
            "reduction_epoch": "10*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": 2,
            "preconditioner_apply_count": 1,
            "candidate_required": "preserved_0_or_1",
            "candidate_reason_bits": "preserved_bitwise_or_of_bits_0_1_2",
            "triangular_breakdown": (
                "1_only_if_active_scale_relative_pivot_breaks_else_0"
            ),
            "invariant_breakdown": (
                "1_if_preexisting_or_active_pivot_breakdown_else_0"
            ),
            "reduction_valid_mask": (
                "1024_if_candidate_required_and_not_triangular_breakdown_else_0"
            ),
            "solution_and_true_residual_committed": False,
        },
    }


def hip_fgmres_first_column_candidate_residual_schedule_payload_v2() -> dict[str, Any]:
    """Return the canonical candidate SpMV and residual-metrics prefix.

    The fixed host schedule always submits every launch.  Device-side gates
    make the entire prefix a claim-only numeric no-op unless a candidate is
    required and back substitution remained nonsingular.  The prefix stops
    after raw candidate L2/Linf publication and before trial/committed solution
    norms or any checkpoint decision.
    """

    preparation = hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    preparation_hash = canonical_hash(preparation)
    if preparation_hash != _FIRST_COLUMN_CANDIDATE_PREPARATION_SCHEDULE_HASH_V2:
        raise RuntimeError("Unexpected candidate-preparation predecessor hash.")
    active = "candidate_required_and_not_triangular_breakdown"
    return {
        "schedule_contract_version": (
            "structural-analysis-hip-fgmres-first-column-candidate-residual-schedule.v2"
        ),
        "predecessor_contract": {
            "schedule_contract_version": preparation["schedule_contract_version"],
            "schedule_hash": preparation_hash,
            "required_end_schedule_epoch": "23+10*S",
            "required_end_reduction_epoch": "10*S",
            "required_active_end_reduction_valid_mask": 1024,
            "required_inactive_end_reduction_valid_mask": 0,
        },
        "scope": {
            "restart_numbering": "one_based",
            "restart_index": 1,
            "column_index": 0,
            "included_from": "CANDIDATE_PREPARATION_ACCEPTED_STATE",
            "included_through": "CANDIDATE_LINF_FINAL_STAGE",
            "candidate_spmv_included": True,
            "candidate_operator_accept_included": True,
            "candidate_residual_formation_included": True,
            "candidate_l2_included": True,
            "candidate_linf_included": True,
            "candidate_false_claim_only": True,
            "triangular_breakdown_claim_only": True,
            "trial_x_l2_included": False,
            "committed_x_l2_included": False,
            "checkpoint_decide_included": False,
            "checkpoint_commit_included": False,
            "full_recurrence_complete": False,
        },
        "symbols": {
            "F": "free_dof_count",
            "M": "restart_dimension",
            "S": "recursive_stage_count(F,ceil(F/512))",
            "q": "absolute_reduction_epoch",
        },
        "active_predicate": {
            "expression": active,
            "candidate_required_value": 1,
            "triangular_breakdown_value": 0,
            "evaluated_on_device_for_every_submitted_launch": True,
            "host_submission_depends_on_predicate": False,
        },
        "start_state": {
            "schedule_epoch": "23+10*S",
            "reduction_epoch": "10*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": 2,
            "preconditioner_apply_count": 1,
            "candidate_required": "preserved_0_or_1",
            "candidate_reason_bits": "preserved_bitwise_or_of_bits_0_1_2",
            "triangular_breakdown": "preserved_0_or_1",
            "invariant_breakdown": "preserved_0_or_1",
            "reduction_valid_mask": "1024_if_active_predicate_else_0",
            "work_w_role": "candidate_trial_x_if_active_predicate",
            "solution_and_true_residual_committed": False,
        },
        "launches": [
            {
                "name": "SPMV_CANDIDATE_COLUMN0",
                "symbol": "engine_v2_fgmres_csr_spmv_indexed_v2",
                "mode": "CANDIDATE",
                "numeric_gate": active,
                "expected_schedule_epoch": "23+10*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": "M",
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": "V[M,k]=checked(A*work_w)[k]",
                "gate_false_effect": (
                    "claim_schedule_without_csr_work_w_basis_v_solution_or_"
                    "scratch_access"
                ),
            },
            {
                "name": "CONTROL_OPERATOR_ACCEPT_CANDIDATE_COLUMN0",
                "symbol": "engine_v2_fgmres_control_v2",
                "mode": "OPERATOR_ACCEPT",
                "gate_source": active,
                "expected_schedule_epoch": "24+10*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "required_valid_mask": "1024_if_active_predicate_else_0",
                "result_valid_mask": "same_as_required_valid_mask",
                "gate_true_effect": "operator_apply_count=2->3",
                "gate_false_effect": (
                    "claim_schedule_without_operator_count_scalar_or_record_mutation"
                ),
            },
            {
                "name": "VECTOR_FORM_CANDIDATE_RESIDUAL_COLUMN0",
                "symbol": "engine_v2_fgmres_vector_v2",
                "mode": "FORM_CANDIDATE_RESIDUAL",
                "gate": "CANDIDATE_REQUIRED",
                "numeric_gate": active,
                "expected_schedule_epoch": "25+10*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": "M",
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": "V[M,k]=checked(reduced_load[k]-V[M,k])",
                "gate_false_effect": (
                    "claim_schedule_without_load_basis_v_work_w_solution_or_"
                    "scratch_access"
                ),
            },
            {
                "name": "REDUCE_CANDIDATE_L2_COLUMN0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_V_M",
                "combine_mode": "COMBINE_LASSQ",
                "numeric_gate": active,
                "expected_schedule_epoch": "26+q",
                "expected_reduction_epoch": "q=10*S..11*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": "M",
                "intermediate_target": "NONE",
                "final_target": "CANDIDATE_L2",
                "final_target_code": 9,
                "final_valid_bit": 8,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": (
                    "final_stage_publishes_raw_candidate_l2_and_sets_bit_8_"
                    "mask_1024_to_1280"
                ),
                "gate_false_effect": (
                    "claim_all_schedule_and_reduction_epochs_without_basis_v_"
                    "reduction_scratch_or_target_access"
                ),
            },
            {
                "name": "REDUCE_CANDIDATE_LINF_COLUMN0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LINF_V_M",
                "combine_mode": "COMBINE_MAX",
                "numeric_gate": active,
                "expected_schedule_epoch": "26+q",
                "expected_reduction_epoch": "q=11*S..12*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": "M",
                "intermediate_target": "NONE",
                "final_target": "CANDIDATE_LINF",
                "final_target_code": 10,
                "final_valid_bit": 9,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": (
                    "final_stage_publishes_raw_candidate_linf_and_sets_bit_9_"
                    "mask_1280_to_1792"
                ),
                "gate_false_effect": (
                    "claim_all_schedule_and_reduction_epochs_without_basis_v_"
                    "reduction_scratch_or_target_access"
                ),
            },
        ],
        "candidate_residual_contract": {
            "candidate_spmv_formula": "V[M]=A*work_w",
            "candidate_residual_formula": "V[M]=reduced_load-V[M]",
            "candidate_residual_formation_is_in_place": True,
            "candidate_residual_storage_after_active_replay": "V[M]",
            "candidate_trial_storage_after_active_replay": "work_w",
            "solution_x_modified": False,
            "true_residual_modified": False,
            "additional_O_F_workspace_allowed": False,
        },
        "always_submit_gated_contract": {
            "host_schedule_is_gate_independent": True,
            "all_five_launch_groups_submitted_for_all_gate_values": True,
            "all_2S_reduction_stages_submitted_for_all_gate_values": True,
            "inactive_claims_all_schedule_epochs": True,
            "inactive_claims_all_reduction_epochs": True,
            "inactive_reads_csr": False,
            "inactive_reads_reduced_load": False,
            "inactive_reads_work_w": False,
            "inactive_reads_or_writes_basis_v_M": False,
            "inactive_reads_or_writes_solution_x": False,
            "inactive_reads_or_writes_reduction_scratch": False,
            "inactive_reads_or_writes_reduction_targets": False,
            "inactive_operator_apply_count": 2,
            "inactive_reduction_valid_mask": 0,
        },
        "reduction_validity_contract": {
            "target_codes": {"CANDIDATE_L2": 9, "CANDIDATE_LINF": 10},
            "valid_bits": {"CANDIDATE_L2": 8, "CANDIDATE_LINF": 9},
            "active_mask_at_start": 1024,
            "active_mask_after_candidate_l2": 1280,
            "active_mask_after_candidate_linf": 1792,
            "inactive_mask_at_all_epochs": 0,
            "update_l2_bit_preserved": True,
            "intermediate_stages_use_none_target": True,
            "only_active_final_stages_publish_named_targets": True,
            "future_consumer": "CHECKPOINT_DECIDE",
        },
        "numeric_policy_contract": {
            "candidate_l2_algorithm": "scale_first_lassq_fp64",
            "candidate_l2_input_finiteness_required": True,
            "represented_fp64_final_l2_overflow_policy": (
                "terminal_nonfinite_arithmetic_failure"
            ),
            "represented_fp64_final_l2_overflow_exact_cpu_parity_claimed": False,
            "cpu_edge_difference": (
                "cpu_early_candidate_gate_false_may_continue_while_device_"
                "reduction_fails_closed"
            ),
            "candidate_linf_published_value": "raw_max_abs_candidate_residual",
            "scaled_candidate_linf_persisted": False,
            "candidate_scaled_residual_decision_included": False,
        },
        "counter_phase_contract": {
            "effective_restarts": "preserve_1",
            "effective_iterations": "preserve_1",
            "arnoldi_step_count": "preserve_1",
            "effective_arnoldi_dimension": "preserve_1",
            "preconditioner_apply_count": "preserve_1",
            "operator_apply_count": "3_if_active_predicate_else_preserve_2",
            "phase": "preserve_candidate_if_required_else_arnoldi",
            "column_index": "preserve_0",
            "candidate_required": "preserve",
            "candidate_reason_bits": "preserve",
            "triangular_breakdown": "preserve",
            "invariant_breakdown": "preserve",
            "solution_and_true_residual_committed": False,
        },
        "stop_boundary": {
            "stops_before": [
                "TRIAL_X_L2",
                "COMMITTED_X_L2",
                "CHECKPOINT_DECIDE",
            ],
            "checkpoint_decision_or_commit_performed": False,
            "reduction_target_consumer_metadata_modified": False,
            "solution_and_true_residual_committed": False,
        },
        "end_state": {
            "schedule_epoch": "26+12*S",
            "reduction_epoch": "12*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": "3_if_active_predicate_else_2",
            "preconditioner_apply_count": 1,
            "candidate_required": "preserved_0_or_1",
            "candidate_reason_bits": "preserved_bitwise_or_of_bits_0_1_2",
            "triangular_breakdown": "preserved_0_or_1",
            "invariant_breakdown": "preserved_0_or_1",
            "reduction_valid_mask": "1792_if_active_predicate_else_0",
            "basis_v_M_role": "candidate_residual_if_active_else_unchanged",
            "work_w_role": "candidate_trial_x_if_active_else_unchanged",
            "candidate_l2_linf": "raw_published_if_active_else_unmodified",
            "solution_and_true_residual_committed": False,
        },
    }


def hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2() -> dict[
    str, Any
]:
    """Return the canonical gated trial/committed solution-norm prefix.

    Both LASSQ trees are always submitted.  They claim their fixed epochs but
    touch no vector, scratch, or target storage unless the device-only
    ``scale_metrics_required`` predicate survives the CPU-priority checkpoint
    gates.  The prefix deliberately stops before ``CHECKPOINT_DECIDE``.
    """

    residual = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    residual_hash = canonical_hash(residual)
    if residual_hash != _FIRST_COLUMN_CANDIDATE_RESIDUAL_SCHEDULE_HASH_V2:
        raise RuntimeError("Unexpected candidate-residual predecessor hash.")
    return {
        "schedule_contract_version": (
            "structural-analysis-hip-fgmres-first-column-candidate-scale-"
            "metrics-schedule.v2"
        ),
        "predecessor_contract": {
            "schedule_contract_version": residual["schedule_contract_version"],
            "schedule_hash": residual_hash,
            "required_end_schedule_epoch": "26+12*S",
            "required_end_reduction_epoch": "12*S",
            "required_inactive_end_reduction_valid_mask": 0,
            "required_active_end_reduction_valid_mask": 1792,
        },
        "scope": {
            "restart_numbering": "one_based",
            "restart_index": 1,
            "column_index": 0,
            "included_from": "CANDIDATE_RESIDUAL_METRICS_ACCEPTED_STATE",
            "included_through": "COMMITTED_X_L2_FINAL_STAGE",
            "trial_x_l2_included": True,
            "committed_x_l2_included": True,
            "device_scale_metrics_predicate_included": True,
            "fixed_claim_only_when_predicate_false": True,
            "checkpoint_decide_included": False,
            "checkpoint_finalize_included": False,
            "checkpoint_commit_included": False,
            "x_scale_l2_included": False,
            "full_recurrence_complete": False,
        },
        "symbols": {
            "F": "free_dof_count",
            "S": "recursive_stage_count(F,ceil(F/512))",
            "q": "absolute_reduction_epoch",
            "DBL_MIN_NORMAL": "0x1p-1022",
        },
        "scale_metrics_required_contract": {
            "storage": "device_only_nonpersistent_predicate",
            "host_submission_depends_on_predicate": False,
            "expression": (
                "active_candidate_and_planned_cycle_end_bit2_and_not_dual_gate_"
                "and_not_invariant_breakdown_and_not_diverged"
            ),
            "evaluation_priority": [
                "active_candidate",
                "planned_cycle_end_bit2",
                "dual_gate",
                "invariant_breakdown",
                "divergence",
            ],
            "active_candidate": ("candidate_required_and_not_triangular_breakdown"),
            "planned_cycle_end": "candidate_reason_bits_bit_2_is_set",
            "dual_gate": {
                "solver_l2_passed": "candidate_l2<=solver_tolerance_l2",
                "scaled_linf_formula": ("candidate_linf/max(1.0,rhs_linf)"),
                "authoritative_linf_passed": ("scaled_linf<=authoritative_tolerance"),
                "passed": "solver_l2_passed_and_authoritative_linf_passed",
                "scaled_linf_persisted": False,
            },
            "invariant_gate": "invariant_breakdown==0",
            "divergence": {
                "base": "max(initial_residual_l2,DBL_MIN_NORMAL)",
                "DBL_MIN_NORMAL": "0x1p-1022",
                "threshold": "divergence_factor*base",
                "comparison": "candidate_l2>threshold",
                "comparison_is_strict": True,
                "threshold_product_positive_infinity_means_diverged": False,
                "threshold_product_positive_infinity_is_arithmetic_error": False,
            },
            "false_predicate_preserves_cpu_terminal_priority": True,
        },
        "start_state": {
            "schedule_epoch": "26+12*S",
            "reduction_epoch": "12*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": "3_if_active_candidate_else_2",
            "preconditioner_apply_count": 1,
            "candidate_required": "preserved_0_or_1",
            "candidate_reason_bits": "preserved_bitwise_or_of_bits_0_1_2",
            "triangular_breakdown": "preserved_0_or_1",
            "invariant_breakdown": "preserved_0_or_1",
            "reduction_valid_mask": "1792_if_active_candidate_else_0",
            "basis_v_M_role": "candidate_residual_if_active_else_unchanged",
            "work_w_role": "candidate_trial_x_if_active_else_unchanged",
            "solution_and_true_residual_committed": False,
        },
        "launches": [
            {
                "name": "REDUCE_TRIAL_X_L2_COLUMN0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_WORK_W",
                "combine_mode": "COMBINE_LASSQ",
                "numeric_gate": "scale_metrics_required",
                "expected_schedule_epoch": "26+q",
                "expected_reduction_epoch": "q=12*S..13*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "intermediate_target": "NONE",
                "final_target": "TRIAL_X_L2",
                "final_target_code": 13,
                "final_valid_bit": 12,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": (
                    "final_stage_publishes_trial_x_l2_and_sets_bit_12_mask_1792_to_5888"
                ),
                "gate_false_effect": (
                    "claim_all_schedule_and_reduction_epochs_without_work_w_"
                    "reduction_scratch_or_target_access"
                ),
            },
            {
                "name": "REDUCE_COMMITTED_X_L2_COLUMN0",
                "symbol": "engine_v2_fgmres_reduce_v2",
                "first_mode": "LASSQ_SOLUTION_X",
                "combine_mode": "COMBINE_LASSQ",
                "numeric_gate": "scale_metrics_required",
                "expected_schedule_epoch": "26+q",
                "expected_reduction_epoch": "q=13*S..14*S-1",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": 0,
                "intermediate_target": "NONE",
                "final_target": "COMMITTED_X_L2",
                "final_target_code": 12,
                "final_valid_bit": 11,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after": "unchanged",
                "gate_true_effect": (
                    "final_stage_publishes_committed_x_l2_and_sets_bit_11_mask_"
                    "5888_to_7936"
                ),
                "gate_false_effect": (
                    "claim_all_schedule_and_reduction_epochs_without_solution_x_"
                    "reduction_scratch_or_target_access"
                ),
            },
        ],
        "always_submit_gated_contract": {
            "host_schedule_is_predicate_independent": True,
            "both_launch_groups_submitted_for_all_predicate_values": True,
            "all_2S_reduction_stages_submitted_for_all_predicate_values": True,
            "predicate_false_claims_all_schedule_epochs": True,
            "predicate_false_claims_all_reduction_epochs": True,
            "predicate_false_reads_work_w": False,
            "predicate_false_reads_solution_x": False,
            "predicate_false_reads_or_writes_reduction_scratch": False,
            "predicate_false_reads_or_writes_reduction_targets": False,
            "predicate_false_mutates_solution_or_true_residual": False,
        },
        "reduction_validity_contract": {
            "target_codes": {"TRIAL_X_L2": 13, "COMMITTED_X_L2": 12},
            "valid_bits": {"TRIAL_X_L2": 12, "COMMITTED_X_L2": 11},
            "inactive_candidate_mask_at_all_epochs": 0,
            "active_predicate_false_mask_at_all_epochs": 1792,
            "scale_metrics_mask_at_start": 1792,
            "scale_metrics_mask_after_trial_x_l2": 5888,
            "scale_metrics_mask_after_committed_x_l2": 7936,
            "candidate_update_and_residual_bits_preserved": True,
            "intermediate_stages_use_none_target": True,
            "only_predicate_true_final_stages_publish_named_targets": True,
        },
        "target_lifetime_contract": {
            "existing_consumer_metadata_modified": False,
            "trial_x_l2": {
                "field": "trial_x_l2",
                "offset_bytes": 240,
                "valid_bit": 12,
                "future_consumer": "CHECKPOINT_DECIDE",
            },
            "committed_x_l2": {
                "field": "committed_x_l2",
                "offset_bytes": 232,
                "valid_bit": 11,
                "future_checkpoint_decide_access": "read_only_without_consume",
                "future_consumer": "CHECKPOINT_FINALIZE",
                "bit_and_value_preserved_at_slice_end": True,
                "future_checkpoint_finalize_must_clear": True,
            },
        },
        "numeric_policy_contract": {
            "algorithm": "scale_first_lassq_fp64",
            "input_finiteness_required_only_when_predicate_true": True,
            "trial_x_l2_represented_overflow_policy": (
                "terminal_nonfinite_arithmetic_failure_if_predicate_true"
            ),
            "committed_x_l2_represented_overflow_policy": (
                "terminal_nonfinite_arithmetic_failure_if_predicate_true"
            ),
            "predicate_false_overflow_or_nonfinite_sources_inspected": False,
            "divergence_threshold_positive_infinity_is_not_l2_overflow": True,
        },
        "counter_phase_contract": {
            "effective_restarts": "preserve_1",
            "effective_iterations": "preserve_1",
            "arnoldi_step_count": "preserve_1",
            "effective_arnoldi_dimension": "preserve_1",
            "operator_apply_count": "preserve_3_if_active_candidate_else_2",
            "preconditioner_apply_count": "preserve_1",
            "phase": "preserve_candidate_if_required_else_arnoldi",
            "column_index": "preserve_0",
            "candidate_required": "preserve",
            "candidate_reason_bits": "preserve",
            "triangular_breakdown": "preserve",
            "invariant_breakdown": "preserve",
            "solution_and_true_residual_committed": False,
        },
        "stop_boundary": {
            "stops_before": ["CHECKPOINT_DECIDE"],
            "checkpoint_decision_or_finalize_performed": False,
            "checkpoint_commit_performed": False,
            "x_scale_l2_computed_or_persisted": False,
            "solution_and_true_residual_committed": False,
        },
        "end_state": {
            "schedule_epoch": "26+14*S",
            "reduction_epoch": "14*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": "3_if_active_candidate_else_2",
            "preconditioner_apply_count": 1,
            "candidate_required": "preserved_0_or_1",
            "candidate_reason_bits": "preserved_bitwise_or_of_bits_0_1_2",
            "triangular_breakdown": "preserved_0_or_1",
            "invariant_breakdown": "preserved_0_or_1",
            "scale_metrics_required": "device_only_nonpersistent",
            "reduction_valid_mask": (
                "7936_if_scale_metrics_required_else_1792_if_active_candidate_else_0"
            ),
            "trial_x_l2": "published_if_scale_metrics_required_else_unmodified",
            "committed_x_l2": (
                "published_and_preserved_if_scale_metrics_required_else_unmodified"
            ),
            "x_scale_l2": "not_computed_or_persisted",
            "solution_and_true_residual_committed": False,
        },
    }


def hip_fgmres_first_column_predecessor_validation_schedule_payload_v2() -> dict[
    str, Any
]:
    """Return the non-advancing device validation/seal boundary.

    The validator runs after the canonical candidate-scale prefix, checks the
    actual device-only checkpoint admission state, and arms an exact mask and
    reduction-epoch snapshot without advancing either epoch.  A later
    ``CHECKPOINT_DECIDE`` may consume that seal; the host never receives the
    actual mask scalar or the device validation outcome here.
    """

    scale = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    scale_hash = canonical_hash(scale)
    if scale_hash != _FIRST_COLUMN_CANDIDATE_SCALE_METRICS_SCHEDULE_HASH_V2:
        raise RuntimeError(
            "Unexpected candidate-scale predecessor for device validation."
        )
    return {
        "schedule_version": 1,
        "scope": {
            "restart_index": 1,
            "column_index": 0,
            "standalone_device_validator": True,
            "checkpoint_transaction_included": False,
            "later_columns_or_restarts_included": False,
        },
        "predecessor_contract": {
            "schedule_hash": scale_hash,
            "required_schedule_epoch": "26+14*S",
            "required_reduction_epoch": "14*S",
            "admitted_reduction_valid_masks": list(
                _FIRST_COLUMN_PREDECESSOR_MASK_DOMAIN
            ),
        },
        "launch": {
            "name": "PREDECESSOR_VALIDATE_COLUMN0",
            "symbol": _KERNEL_SYMBOLS[0],
            "submission_kind": "control",
            "control_mode": "PREDECESSOR_VALIDATE",
            "control_mode_code": _CONTROL_MODE_CODES["PREDECESSOR_VALIDATE"],
            "expected_schedule_epoch": "26+14*S",
            "required_reduction_epoch": "14*S",
            "expected_restart": 1,
            "expected_column": 0,
            "row_index": -1,
            "pass_index": -1,
            "device_gate": "active_checkpoint_predecessor",
        },
        "seal_contract": {
            "state_field": "predecessor_validation_state",
            "mask_snapshot_field": "predecessor_mask_snapshot",
            "reduction_epoch_snapshot_field": ("predecessor_reduction_epoch_snapshot"),
            "empty_state": _PREDECESSOR_VALIDATION_STATE_CODES["empty"],
            "armed_state": _PREDECESSOR_VALIDATION_STATE_CODES["armed"],
            "consumed_state": _PREDECESSOR_VALIDATION_STATE_CODES["consumed"],
            "success_advances_schedule_epoch": False,
            "success_advances_reduction_epoch": False,
            "duplicate_validation_allowed": False,
            "allowed_mask_change_after_validation": False,
            "consumer": "CHECKPOINT_DECIDE",
            "final_clear_authority": "CHECKPOINT_FINALIZE",
        },
        "host_observation_contract": {
            "actual_mask_host_observed": False,
            "validation_outcome_host_observed": False,
            "device_fence_alone_is_host_success_verdict": False,
        },
        "end_state": {
            "schedule_epoch": "26+14*S",
            "reduction_epoch": "14*S",
            "predecessor_validation_state": "armed_if_valid_else_terminal_failure",
            "reduction_valid_mask": "device_only_preserved_exact_value",
        },
    }


def hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2() -> dict[
    str, Any
]:
    """Return the canonical first-column checkpoint transaction.

    The four launches form one indivisible successful schedule boundary.
    ``CHECKPOINT_DECIDE`` validates and derives only pending device state,
    ``PREFLIGHT_COMMIT_SOURCE`` performs a non-advancing parallel source scan,
    ``COMMIT_CHECKPOINT`` conditionally transfers vector ownership, and
    ``CHECKPOINT_FINALIZE`` is the sole public solve-record writer and the sole
    successful-path reduction-validity clear authority.  Later columns,
    restarts, and ``FINAL_GUARD`` remain outside this narrow contract.
    """

    scale = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    scale_hash = canonical_hash(scale)
    if scale_hash != _FIRST_COLUMN_CANDIDATE_SCALE_METRICS_SCHEDULE_HASH_V2:
        raise RuntimeError("Unexpected candidate scale-metrics predecessor hash.")
    return {
        "schedule_contract_version": (
            "structural-analysis-hip-fgmres-first-column-checkpoint-"
            "transaction-schedule.v2"
        ),
        "predecessor_contract": {
            "schedule_contract_version": scale["schedule_contract_version"],
            "schedule_hash": scale_hash,
            "required_end_schedule_epoch": "26+14*S",
            "required_end_reduction_epoch": "14*S",
            "required_end_reduction_valid_masks": [0, 1792, 7936],
            "required_inactive_or_triangular_mask": 0,
            "required_active_scale_false_mask": 1792,
            "required_active_scale_true_mask": 7936,
        },
        "scope": {
            "restart_numbering": "one_based",
            "restart_index": 1,
            "column_index": 0,
            "included_from": "CANDIDATE_SCALE_METRICS_ACCEPTED_STATE",
            "included_through": "CHECKPOINT_FINALIZE_COLUMN0",
            "checkpoint_decide_included": True,
            "checkpoint_source_preflight_included": True,
            "checkpoint_commit_included": True,
            "checkpoint_finalize_included": True,
            "invalid_source_destination_failure_atomicity_contract_included": True,
            "x_scale_l2_included": True,
            "restart_record_finalize_included": True,
            "later_column_included": False,
            "later_restart_included": False,
            "final_guard_included": False,
            "additional_reduction_stages": 0,
            "additional_vector_preflight_launches": 1,
            "full_recurrence_complete": False,
        },
        "symbols": {
            "F": "free_dof_count",
            "M": "restart_dimension",
            "S": "recursive_stage_count(F,ceil(F/512))",
            "DBL_MIN_NORMAL": "0x1p-1022",
            "SQRT_EPS": "0x1p-26",
        },
        "start_state": {
            "schedule_epoch": "26+14*S",
            "reduction_epoch": "14*S",
            "phase": "candidate_if_candidate_required_else_arnoldi",
            "restart_index": 1,
            "next_expected_restart": 2,
            "column_index": 0,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": "3_if_active_candidate_else_2",
            "preconditioner_apply_count": 1,
            "active": 1,
            "candidate_required": "preserved_0_or_1",
            "candidate_reason_bits": "preserved_bitwise_or_of_bits_0_1_2",
            "triangular_breakdown": "preserved_0_or_1",
            "invariant_breakdown": "preserved_0_or_1",
            "reduction_valid_mask": (
                "0_or_1792_or_7936_from_exact_predecessor_predicate"
            ),
            "solution_x_role": "committed_solution",
            "true_residual_role": "committed_true_residual",
            "work_w_role": "candidate_trial_solution_if_active_else_unchanged",
            "basis_v_M_role": "candidate_true_residual_if_active_else_unchanged",
        },
        "launches": [
            {
                "name": "CHECKPOINT_DECIDE_COLUMN0",
                "symbol": "engine_v2_fgmres_control_v2",
                "control_mode": "CHECKPOINT_DECIDE",
                "control_mode_code": 11,
                "expected_schedule_epoch": "26+14*S",
                "required_reduction_epoch": "14*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "candidate_if_required_else_arnoldi",
                "phase_after_success": "checkpoint_commit",
                "device_gate_source": "always",
                "admitted_reduction_valid_masks": [0, 1792, 7936],
                "reduction_valid_mask_effect": "preserve_exact",
                "active_effect": "preserve_1_until_finalize_on_nonfailure",
                "allowed_writes": [
                    "commit_required",
                    "continuation_required",
                    "pending_terminal_status",
                    "pending_termination_code",
                    "pending_restart_hint",
                    "pending_restart_flags",
                    "x_scale_l2_if_scale_path",
                    "phase",
                ],
                "solve_record_header_or_restart_row_writes": False,
            },
            {
                "name": "PREFLIGHT_COMMIT_SOURCE_COLUMN0",
                "symbol": "engine_v2_fgmres_vector_v2",
                "vector_mode": "PREFLIGHT_COMMIT_SOURCE",
                "vector_mode_code": 9,
                "vector_gate": "COMMIT_REQUIRED",
                "vector_gate_code": 4,
                "expected_schedule_epoch": "27+14*S",
                "required_reduction_epoch": "14*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": "M",
                "phase_before": "checkpoint_commit",
                "phase_after": "unchanged",
                "device_gate_source": "commit_required",
                "admitted_reduction_valid_masks": [0, 1792, 7936],
                "reduction_valid_mask_effect": "preserve_exact",
                "schedule_epoch_effect": "preserve_exact_nonadvancing",
                "reduction_epoch_effect": "preserve_exact_nonadvancing",
                "preflight_state_effect": (
                    "legacy_empty_0_or_sealed_consumed_2_to_commit_preflighted_3"
                ),
                "snapshot_effect": "preserve_exact_without_mutation",
                "gate_true_effect": (
                    "parallel_isfinite_scan_of_work_w_k_and_basis_v_M_k_without_"
                    "destination_access"
                ),
                "gate_false_effect": (
                    "publish_commit_preflighted_state_without_reading_or_writing_"
                    "sources_or_destinations"
                ),
                "solve_record_header_or_restart_row_writes": (
                    "failure_diagnostics_only"
                ),
                "active_effect": (
                    "preserve_1_if_all_sources_finite_else_terminal_failure"
                ),
            },
            {
                "name": "COMMIT_CHECKPOINT_COLUMN0",
                "symbol": "engine_v2_fgmres_vector_v2",
                "vector_mode": "COMMIT_CHECKPOINT",
                "vector_mode_code": 8,
                "vector_gate": "COMMIT_REQUIRED",
                "vector_gate_code": 4,
                "expected_schedule_epoch": "27+14*S",
                "required_reduction_epoch": "14*S",
                "expected_restart": 1,
                "expected_column": 0,
                "logical_index": "M",
                "phase_before": "checkpoint_commit",
                "phase_after": "unchanged",
                "device_gate_source": "commit_required",
                "admitted_reduction_valid_masks": [0, 1792, 7936],
                "reduction_valid_mask_effect": "preserve_exact",
                "required_preflight_state": "commit_preflighted_3",
                "required_preflight_success_conjunction": (
                    "state_3_and_active_1_and_no_device_error_and_exact_legacy_or_"
                    "sealed_snapshot_shape"
                ),
                "gate_true_effect": (
                    "solution_x[k]=exact_zero(work_w[k]);true_residual[k]="
                    "exact_zero(V[M,k])"
                ),
                "gate_false_effect": (
                    "claim_schedule_epoch_without_reading_or_writing_work_w_"
                    "solution_x_V_M_or_true_residual"
                ),
                "solve_record_header_or_restart_row_writes": False,
                "active_effect": "preserve_1_until_finalize",
            },
            {
                "name": "CHECKPOINT_FINALIZE_COLUMN0",
                "symbol": "engine_v2_fgmres_control_v2",
                "control_mode": "CHECKPOINT_FINALIZE",
                "control_mode_code": 12,
                "expected_schedule_epoch": "28+14*S",
                "required_reduction_epoch": "14*S",
                "expected_restart": 1,
                "expected_column": 0,
                "row_index": -1,
                "pass_index": -1,
                "phase_before": "checkpoint_commit",
                "phase_after": (
                    "outcome_selected_terminal_between_restarts_arnoldi_or_"
                    "final_guard_handoff"
                ),
                "device_gate_source": "always",
                "admitted_reduction_valid_masks": [0, 1792, 7936],
                "reduction_valid_mask_effect": "clear_exact_to_0_on_success",
                "required_preflight_state": "commit_preflighted_3",
                "successful_preflight_state_effect": (
                    "clear_state_and_mask_and_reduction_epoch_snapshots_to_zero"
                ),
                "sole_restart_row_writer": True,
                "sole_solve_record_header_writer_in_transaction": True,
                "sole_terminal_status_and_phase_publish_authority": True,
                "sole_successful_path_target_and_validity_clear_authority": True,
            },
        ],
        "fixed_submission_contract": {
            "four_launches_always_submitted": True,
            "host_submission_depends_on_candidate_or_outcome": False,
            "host_submission_depends_on_source_finiteness": False,
            "preflight_launch_advances_schedule_epoch": False,
            "preflight_launch_advances_reduction_epoch": False,
            "commit_launch_claims_epoch_when_commit_required_false": True,
            "successful_transaction_is_single_hashed_schedule_slice": True,
            "checkpoint_decide_only_boundary_is_publishable": False,
            "checkpoint_commit_only_boundary_is_publishable": False,
            "full_final_cycle_requires_later_final_guard_launch": True,
            "successful_end_schedule_epoch": "29+14*S",
            "successful_end_reduction_epoch": "14*S",
        },
        "commit_source_preflight_contract": {
            "vector_mode": "PREFLIGHT_COMMIT_SOURCE",
            "vector_mode_code": _VECTOR_MODE_CODES["PREFLIGHT_COMMIT_SOURCE"],
            "kernel_symbol": "engine_v2_fgmres_vector_v2",
            "fixed_four_symbol_interface_preserved": True,
            "logical_index": "M",
            "launch_geometry": "ceil(F/256)_blocks_of_256_threads",
            "source_element_formulas": ["work_w[k]", "basis_v[M*F+k]"],
            "source_lane_predicate": ("isfinite(work_w[k])&&isfinite(basis_v[M*F+k])"),
            "gate_true_scans_every_lane": True,
            "gate_false_reads_sources": False,
            "gate_false_reads_or_writes_destinations": False,
            "preflight_reads_or_writes_solution_x": False,
            "preflight_reads_or_writes_true_residual": False,
            "preflight_writes_work_w_or_basis_v_M": False,
            "preflight_mutates_mask_snapshot": False,
            "preflight_mutates_reduction_epoch_snapshot": False,
            "legacy_state_transition": "empty_0_to_commit_preflighted_3",
            "legacy_snapshot_shape": "mask_0_and_reduction_epoch_0",
            "sealed_state_transition": "consumed_2_to_commit_preflighted_3",
            "sealed_snapshot_shape": "exact_live_mask_and_reduction_epoch",
            "commit_preflighted_state_is_success_verdict": False,
            "success_interpretation_boundary": (
                "later_same_stream_commit_observes_state_3_active_1_no_device_"
                "error_and_exact_snapshot_shape"
            ),
            "duplicate_preflight_is_terminal_invalid_control": True,
            "malformed_state_or_snapshot_is_terminal_invalid_control": True,
            "additional_F_vector_workspace_count": 0,
            "additional_device_allocation_count": 0,
            "raw_iteration_h2d_count": 0,
            "raw_iteration_d2h_count": 0,
            "intermediate_host_sync_count": 0,
            "host_finiteness_branch": False,
            "operation_complexity_scope": "parallel_O_F_constant_work_per_lane",
            "end_to_end_O_N_proven": False,
            "authoritative_predecessor_proven": False,
            "authoritative_checkpoint_transaction_proven": False,
        },
        "decision_priority_contract": {
            "evaluation_priority": [
                "dual_gate_convergence",
                "invariant_breakdown",
                "planned_cycle_end_divergence",
                "planned_cycle_end_stagnation",
                "max_iterations",
            ],
            "dual_gate": {
                "solver_l2_passed": "candidate_l2<=solver_tolerance_l2",
                "scaled_linf": "candidate_linf/max(1.0,rhs_linf)",
                "authoritative_linf_passed": ("scaled_linf<=authoritative_tolerance"),
                "passed": "solver_l2_passed_and_authoritative_linf_passed",
                "comparisons_are_inclusive": True,
            },
            "divergence": {
                "evaluated_only_if_planned_cycle_end_bit2": True,
                "base": "max(initial_residual_l2,DBL_MIN_NORMAL)",
                "threshold": "divergence_factor*base",
                "comparison": "candidate_l2>threshold",
                "comparison_is_strict": True,
                "positive_infinity_threshold_is_error": False,
                "positive_infinity_threshold_is_diverged": False,
            },
            "stagnation": {
                "evaluated_only_after_dual_invariant_and_divergence_fail": True,
                "x_scale_l2": "trial_x_l2+committed_x_l2",
                "unit_floor_applied": False,
                "plateau": (
                    "candidate_l2>=(1-stagnation_relative_tolerance)*"
                    "previous_checkpoint_residual_l2"
                ),
                "tiny_update": "solution_update_l2<=0x1p-26*x_scale_l2",
                "comparisons_are_inclusive": True,
                "new_streak": ("old_streak+1_if_plateau_and_tiny_update_else_0"),
                "terminal": "new_streak>=stagnation_checkpoint_limit",
            },
            "max_iterations": {
                "evaluated_after_stagnation": True,
                "terminal": (
                    "effective_iterations==max_iterations_unless_exact_full_"
                    "final_cycle_handoff"
                ),
            },
        },
        "outcome_contract": [
            {
                "name": "candidate_not_required_same_cycle",
                "condition": "candidate_required==0",
                "commit_required": 0,
                "continuation_required": 1,
                "restart_row_written": False,
                "terminal_status": 0,
                "termination_code": 0,
                "restart_hint": 0,
                "restart_flags": 0,
                "final_phase": "arnoldi",
                "final_column_index": 1,
            },
            {
                "name": "triangular_factor_breakdown",
                "condition": "candidate_required==1_and_triangular_breakdown==1",
                "commit_required": 0,
                "continuation_required": 0,
                "restart_row_written": True,
                "restart_row_residual_source": "previous_committed_header_metrics",
                "restart_row_solution_update_l2": 0.0,
                "terminal_status": 5,
                "termination_code": 30,
                "restart_hint": 5,
                "restart_flags": 0,
                "final_phase": "terminal",
            },
            {
                "name": "happy_breakdown_converged",
                "condition": "active_candidate_and_dual_gate_and_invariant_breakdown",
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 1,
                "termination_code": 2,
                "restart_hint": 2,
                "restart_flags": 15,
                "happy_flag_set_and_invariant_flag_clear": True,
                "final_phase": "terminal",
            },
            {
                "name": "estimated_trigger_true_residual_converged",
                "condition": (
                    "active_candidate_and_dual_gate_and_not_invariant_and_reason_bit0"
                ),
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 1,
                "termination_code": 3,
                "restart_hint": 3,
                "restart_flags": 7,
                "final_phase": "terminal",
            },
            {
                "name": "planned_end_true_residual_converged",
                "condition": (
                    "active_candidate_and_dual_gate_and_not_invariant_and_"
                    "not_reason_bit0_and_reason_bit2"
                ),
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 1,
                "termination_code": 4,
                "restart_hint": 1,
                "restart_flags": 7,
                "final_phase": "terminal",
            },
            {
                "name": "invariant_subspace_breakdown",
                "condition": "active_candidate_and_not_dual_gate_and_invariant",
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 5,
                "termination_code": 31,
                "restart_hint": 4,
                "restart_flags": (
                    "bit0_replayed_or_individual_gate_bits_or_bit4_invariant"
                ),
                "happy_flag_clear_and_invariant_flag_set": True,
                "final_phase": "terminal",
            },
            {
                "name": "planned_end_diverged",
                "condition": (
                    "active_candidate_and_planned_bit2_and_not_dual_and_not_"
                    "invariant_and_candidate_l2_strictly_above_divergence_threshold"
                ),
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 4,
                "termination_code": 21,
                "restart_hint": 1,
                "restart_flags": (
                    "bit0_replayed_or_individual_gate_bits_or_bit7_divergence"
                ),
                "final_phase": "terminal",
            },
            {
                "name": "planned_end_stagnated",
                "condition": "scale_path_and_new_streak_at_least_limit",
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 3,
                "termination_code": 20,
                "restart_hint": 1,
                "restart_flags": (
                    "bit0_replayed_or_individual_gate_bits_or_actual_bit5_"
                    "plateau_or_actual_bit6_tiny"
                ),
                "final_phase": "terminal",
            },
            {
                "name": "planned_end_max_iterations_checkpoint_terminal",
                "condition": (
                    "scale_path_and_not_stagnated_and_effective_iterations_"
                    "equals_max_iterations_and_not_exact_full_final_cycle"
                ),
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "terminal_status": 2,
                "termination_code": 10,
                "restart_hint": 1,
                "restart_flags": (
                    "bit0_replayed_or_individual_gate_bits_or_actual_plateau_"
                    "and_tiny_bits"
                ),
                "final_phase": "terminal",
            },
            {
                "name": "planned_end_max_iterations_final_guard_handoff",
                "condition": (
                    "scale_path_and_not_stagnated_and_effective_iterations_"
                    "equals_max_iterations_and_restart_R_column_M_minus_1_and_"
                    "max_iterations_equals_R_times_M"
                ),
                "commit_required": 1,
                "continuation_required": 0,
                "restart_row_written": True,
                "pending_terminal_status_before_finalize": 2,
                "pending_termination_code_before_finalize": 10,
                "terminal_status": 0,
                "termination_code": 0,
                "restart_hint": 1,
                "restart_flags": (
                    "bit0_replayed_or_individual_gate_bits_or_actual_plateau_"
                    "and_tiny_bits"
                ),
                "final_phase": "arnoldi",
                "final_column_index": "M-1",
                "final_guard_required": True,
                "handoff_postcondition": "exact_final_guard_exhausted_shape",
            },
            {
                "name": "planned_end_continue_next_restart",
                "condition": "scale_path_and_not_stagnated_and_not_max_iterations",
                "commit_required": 1,
                "continuation_required": 1,
                "restart_row_written": True,
                "terminal_status": 0,
                "termination_code": 0,
                "restart_hint": 1,
                "restart_flags": (
                    "bit0_replayed_or_individual_gate_bits_or_actual_plateau_"
                    "and_tiny_bits"
                ),
                "final_phase": "between_restarts",
                "final_column_index": -1,
                "next_expected_restart": 2,
            },
            {
                "name": "early_false_convergence_same_cycle",
                "condition": (
                    "active_candidate_and_reason_bit0_and_not_dual_and_not_"
                    "invariant_and_not_planned_bit2"
                ),
                "commit_required": 0,
                "continuation_required": 1,
                "restart_row_written": False,
                "false_convergence_count_effect": "+1",
                "terminal_status": 0,
                "termination_code": 0,
                "restart_hint": 0,
                "restart_flags": 0,
                "final_phase": "arnoldi",
                "final_column_index": 1,
            },
        ],
        "pending_state_contract": {
            "checkpoint_decide_is_only_pending_state_writer": True,
            "checkpoint_decide_writes_solve_record_header": False,
            "checkpoint_decide_writes_restart_row": False,
            "checkpoint_decide_writes_solution_or_true_residual": False,
            "pending_fields": [
                "commit_required",
                "continuation_required",
                "pending_terminal_status",
                "pending_termination_code",
                "pending_restart_hint",
                "pending_restart_flags",
            ],
            "active_must_remain_1_until_finalize_on_nonfailure": True,
            "pending_algorithmic_terminal_is_not_public_before_finalize": True,
            "full_final_cycle_pending_max_is_cleared_into_guard_handoff": True,
        },
        "reduction_validity_lifetime_contract": {
            "start_masks": [0, 1792, 7936],
            "after_checkpoint_decide_masks": [0, 1792, 7936],
            "after_commit_source_preflight_masks": [0, 1792, 7936],
            "after_commit_checkpoint_masks": [0, 1792, 7936],
            "after_checkpoint_finalize_mask": 0,
            "checkpoint_decide_preserves_exact_mask": True,
            "commit_source_preflight_preserves_exact_mask": True,
            "commit_checkpoint_preserves_exact_mask": True,
            "checkpoint_finalize_is_only_successful_path_clear_authority": True,
            "checkpoint_decide_target_scalar_access": "read_only_validation",
            "checkpoint_decide_mutates_target_scalars": False,
            "commit_source_preflight_target_scalar_access": "none",
            "commit_checkpoint_target_scalar_access": "none",
            "existing_target_consumer_metadata_semantics": (
                "algorithmic_reader_not_reduction_validity_clear_authority"
            ),
            "candidate_l2": {"target_code": 9, "valid_bit": 8, "offset": 208},
            "candidate_linf": {
                "target_code": 10,
                "valid_bit": 9,
                "offset": 216,
            },
            "solution_update_l2": {
                "target_code": 11,
                "valid_bit": 10,
                "offset": 224,
            },
            "committed_x_l2": {
                "target_code": 12,
                "valid_bit": 11,
                "offset": 232,
                "checkpoint_decide_access": "read_only",
                "commit_checkpoint_access": "none",
                "checkpoint_finalize_action": "publish_scale_if_valid_then_clear",
            },
            "trial_x_l2": {
                "target_code": 13,
                "valid_bit": 12,
                "offset": 240,
            },
            "mask_zero_path_target_scalar_access": False,
        },
        "commit_ownership_contract": {
            "commit_point": "COMMIT_CHECKPOINT_vector_launch",
            "preflight_precedes_commit_on_same_stream": True,
            "preflight_is_nonadvancing_global_kernel_boundary": True,
            "before_commit": {
                "solution_x": "committed_solution",
                "true_residual": "committed_true_residual",
                "work_w": "candidate_trial_solution",
                "basis_v_M": "candidate_true_residual",
            },
            "commit_required_true": {
                "solution_x": "exact_copy_from_work_w",
                "true_residual": "exact_copy_from_basis_v_M",
                "work_w": "source_only_preserved",
                "basis_v_M": "source_only_preserved",
            },
            "commit_required_false_reads_or_writes_work_w": False,
            "commit_required_false_reads_or_writes_solution_x": False,
            "commit_required_false_reads_or_writes_basis_v_M": False,
            "commit_required_false_reads_or_writes_true_residual": False,
            "solve_record_publish_after_commit_only": True,
        },
        "invalid_source_destination_atomicity_contract": {
            "scope": (
                "registered_nonoverlapping_allocations_and_exclusive_same_stream_"
                "transaction_only"
            ),
            "invalid_predicate": (
                "any_nonfinite_lane_in_work_w_or_basis_v_M_when_commit_required"
            ),
            "detection_launch": "PREFLIGHT_COMMIT_SOURCE_COLUMN0",
            "detection_precedes_any_destination_access": True,
            "source_buffers": ["work_w", "basis_v_M"],
            "destination_buffers": ["solution_x", "true_residual"],
            "preflight_destination_access": "none",
            "invalid_successor_commit_destination_access": "none",
            "solution_x_entire_byte_range_unchanged": True,
            "true_residual_entire_byte_range_unchanged": True,
            "source_byte_ranges_preserved": True,
            "failure_diagnostics_may_mutate_control_or_solve_record": True,
            "device_error": "nonfinite_input",
            "device_error_mask": 4,
            "failure_origin": "vector",
            "failure_origin_code": 2,
            "terminal_status": 6,
            "termination_code": 47,
            "failure_schedule_epoch": "27+14*S",
            "failure_reduction_epoch": "14*S",
            "algorithmic_restart_row_written": False,
            "additional_F_vector_workspace_count": 0,
            "raw_iteration_d2h_count": 0,
            "host_finiteness_branch": False,
            "parallel_valid_path_work": "O(F)",
            "arbitrary_device_fault_atomicity_proven": False,
            "concurrent_external_writer_atomicity_proven": False,
            "raw_pointer_range_nonoverlap_authoritative": False,
            "authoritative_solver_or_solution_receipt": False,
            "end_to_end_O_N_proven": False,
        },
        "pointer_alias_contract": {
            "all_arguments_are_exact_allocation_base_pointers": True,
            "host_shifted_pointer_allowed": False,
            "commit_source_destination_alias_allowed": False,
            "forbidden_exact_alias_pairs": [
                ["work_w_base", "solution_x_base"],
                ["basis_v_base", "true_residual_base"],
                ["work_w_base", "true_residual_base"],
                ["basis_v_base", "solution_x_base"],
                ["solution_x_base", "true_residual_base"],
            ],
            "basis_v_M_address": "basis_v_base+M*F",
            "logical_index_is_separate_argument": True,
            "commit_required_false_still_requires_canonical_allocation_lineage": True,
        },
        "finalize_record_contract": {
            "sole_writer": "CHECKPOINT_FINALIZE",
            "restart_row_written_for": [
                "triangular_factor_breakdown",
                "every_commit_required_true_outcome",
            ],
            "restart_row_not_written_for": [
                "candidate_not_required_same_cycle",
                "early_false_convergence_same_cycle",
            ],
            "active_candidate_row_metrics": (
                "candidate_l2_candidate_linf_scaled_linf_solution_update_l2"
            ),
            "triangular_row_metrics": (
                "previous_committed_residual_metrics_and_zero_solution_update"
            ),
            "header_final_metrics_change_only_if_commit_required": True,
            "solution_scale_l2": ("publish_x_scale_only_on_scale_path_else_preserve"),
            "happy_breakdown_count": "+1_only_for_happy_breakdown_converged",
            "false_convergence_count": (
                "+1_only_for_same_cycle_active_reason_bit0_dual_fail_no_commit_no_row"
            ),
            "stagnation_checkpoint_count": (
                "new_streak_only_on_scale_path_else_preserve"
            ),
            "previous_checkpoint_residual_l2": (
                "candidate_l2_on_scale_path_else_preserve"
            ),
            "pending_fields_cleared_after_publish": True,
            "candidate_state_fields_reset_after_publish": True,
        },
        "counter_contract": {
            "effective_restarts": "preserve_1",
            "effective_iterations": "preserve_1",
            "arnoldi_step_count": "preserve_1",
            "effective_arnoldi_dimension": "preserve_1",
            "operator_apply_count": "preserve_3_if_active_candidate_else_2",
            "preconditioner_apply_count": "preserve_1",
            "next_expected_restart": "preserve_2",
            "same_cycle_continuation_column_index": "0_to_1",
            "planned_nonterminal_column_index": "0_to_-1",
        },
        "numeric_failure_contract": {
            "x_scale_formula": "trial_x_l2+committed_x_l2",
            "unit_floor_applied": False,
            "nonfinite_or_positive_infinity_sum_is_failure": True,
            "device_error": "arithmetic_overflow",
            "device_error_mask": 8,
            "terminal_status": 6,
            "termination_code": 47,
            "failure_origin": "control",
            "failure_timing": "checkpoint_decide_pre_commit",
            "solution_x_and_true_residual_preserved": True,
            "algorithmic_result_metrics_or_restart_row_written": False,
            "terminal_failure_status_code_and_device_error_header_written": True,
            "cpu_history_append_edge_exact_parity_claimed": False,
            "failure_transition_is_not_success_end_state": True,
        },
        "success_end_state": {
            "schedule_epoch": "29+14*S",
            "reduction_epoch": "14*S",
            "reduction_valid_mask": 0,
            "predecessor_validation_state": 0,
            "predecessor_mask_snapshot": 0,
            "predecessor_reduction_epoch_snapshot": 0,
            "active": "0_if_checkpoint_terminal_else_1",
            "phase": (
                "terminal_or_between_restarts_or_arnoldi_including_guard_handoff"
            ),
            "column_index": (
                "0_if_checkpoint_terminal_or_guard_handoff_else_-1_if_between_"
                "restarts_else_1"
            ),
            "restart_index": 1,
            "next_expected_restart": 2,
            "effective_restarts": 1,
            "effective_iterations": 1,
            "arnoldi_step_count": 1,
            "effective_arnoldi_dimension": 1,
            "operator_apply_count": "3_if_active_candidate_else_2",
            "preconditioner_apply_count": 1,
            "public_record_matches_committed_vector_ownership": True,
            "later_column_or_restart_executed": False,
            "final_guard_executed": False,
            "final_guard_handoff_may_be_required": True,
        },
    }


def hip_fgmres_recurrence_kernel_abi_payload_v2() -> dict[str, Any]:
    """Return the fresh canonical four-symbol recurrence interface payload."""

    first_column_partial_schedule = (
        hip_fgmres_first_column_partial_schedule_payload_v2()
    )
    first_column_completion_schedule = (
        hip_fgmres_first_column_completion_schedule_payload_v2()
    )
    first_column_candidate_preparation_schedule = (
        hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
    )
    first_column_candidate_residual_schedule = (
        hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
    )
    first_column_candidate_scale_metrics_schedule = (
        hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
    )
    first_column_predecessor_validation_schedule = (
        hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
    )
    if (
        canonical_hash(first_column_predecessor_validation_schedule)
        != _FIRST_COLUMN_PREDECESSOR_VALIDATION_SCHEDULE_HASH_V2
    ):
        raise RuntimeError("Unexpected predecessor-validation schedule hash.")
    first_column_checkpoint_transaction_schedule = (
        hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
    )
    return {
        "recurrence_abi_version": 2,
        "language_linkage": "extern_C",
        "symbols": list(_KERNEL_SYMBOLS),
        "signatures": {
            "engine_v2_fgmres_control_v2": (
                "void(int control_mode,int expected_schedule_epoch,"
                "int expected_restart,"
                "int expected_column,int row_index,int pass_index,"
                "int free_dof_count,int restart_dimension,"
                "int max_iterations,int maximum_restart_count,"
                "int stagnation_checkpoint_limit,double absolute_tolerance,"
                "double relative_tolerance,double authoritative_tolerance,"
                "double stagnation_relative_tolerance,double divergence_factor,"
                "double* dense_base,unsigned char* control_state_base,"
                "unsigned char* solve_record_base)"
            ),
            "engine_v2_fgmres_vector_v2": (
                "void(int vector_mode,int vector_gate,"
                "int expected_schedule_epoch,int expected_restart,"
                "int expected_column,int free_dof_count,"
                "int logical_index,const double* reduced_state_base,"
                "const double* reduced_load_base,"
                "const double* inverse_diagonal_base,double* solution_x_base,"
                "double* true_residual_base,double* work_w_base,"
                "double* basis_v_base,double* basis_z_base,"
                "const double* dense_base,unsigned char* control_state_base,"
                "unsigned char* solve_record_base)"
            ),
            "engine_v2_fgmres_csr_spmv_indexed_v2": (
                "void(int spmv_mode,int expected_schedule_epoch,"
                "int expected_restart,int expected_column,"
                "int free_dof_count,int nonzero_count,"
                "int logical_index,const int* row_ptr_base,"
                "const int* column_indices_base,const double* values_base,"
                "const double* solution_x_base,double* work_w_base,"
                "double* basis_v_base,const double* basis_z_base,"
                "unsigned char* control_state_base,"
                "unsigned char* solve_record_base)"
            ),
            "engine_v2_fgmres_reduce_v2": (
                "void(int reduction_mode,int reduction_target,"
                "int expected_schedule_epoch,"
                "int expected_restart,int expected_column,"
                "int expected_reduction_epoch,int value_count,int logical_index,"
                "const double* reduced_load_base,"
                "const double* solution_x_base,"
                "const double* true_residual_base,const double* work_w_base,"
                "const double* basis_v_base,"
                "const double* reduction_input_base,"
                "double* reduction_output_base,"
                "unsigned char* control_state_base,"
                "unsigned char* solve_record_base)"
            ),
        },
        "pointer_contract": "allocation_base_pointers_only",
        "host_shifted_pointer_arguments_allowed": False,
        "logical_index_is_separate_i32_argument": True,
        "global_fixed_recurrence_schedule": (
            hip_fgmres_global_schedule_contract_payload_v1()
        ),
        "launch_sequence_guard": {
            "all_symbols_require_expected_schedule_epoch": True,
            "all_symbols_require_expected_restart_and_column": True,
            "control_requires_explicit_row_and_pass": True,
            "reduce_requires_expected_reduction_epoch": True,
            "pre_restart_or_noncolumn_sentinel": -1,
            "schedule_epoch_initial_value": 0,
            "schedule_epoch_after_init": 1,
            "initial_schedule_stage_count": (
                "S=recursive_stage_count(F,ceil(value_count/512))"
            ),
            "initial_mode_schedule": {
                "CONTROL_INIT": "schedule=0 -> 1,phase=rhs_metrics",
                "VECTOR_COPY_INITIAL_X": "schedule=1",
                "RHS_L2_REDUCTION": "schedule=2..1+S,reduction_epoch=0..S-1",
                "RHS_LINF_REDUCTION": ("schedule=2+S..1+2S,reduction_epoch=S..2S-1"),
                "CONTROL_BIND_RHS": ("schedule=2+2S,phase=rhs_metrics->initial_state"),
                "SPMV_INITIAL": "schedule=3+2S",
                "CONTROL_OPERATOR_ACCEPT": "schedule=4+2S",
                "VECTOR_FORM_INITIAL_RESIDUAL": "schedule=5+2S",
                "INITIAL_L2_REDUCTION": (
                    "schedule=6+2S..5+3S,reduction_epoch=2S..3S-1"
                ),
                "INITIAL_LINF_REDUCTION": (
                    "schedule=6+3S..5+4S,reduction_epoch=3S..4S-1"
                ),
                "CONTROL_INITIAL_GATE": "schedule=6+4S",
            },
            "admission_checks_before_schedule_epoch_increment": [
                "control_or_zero_init_abi",
                "expected_schedule_epoch",
                "expected_restart",
                "expected_column",
                "mode_specific_geometry_and_gate",
            ],
            "admission_mismatch_advances_schedule_epoch": False,
            "schedule_epoch_increments_once_after_admitted_active_or_gated_stage": (
                True
            ),
            "nonadvancing_mode_exceptions": {
                "control": ["PREDECESSOR_VALIDATE"],
                "vector": ["PREFLIGHT_COMMIT_SOURCE"],
            },
            "schedule_epoch_rejects_duplicate_skip_or_reorder": True,
            "coordinate_contract": {
                "initial_metrics_expected_restart": -1,
                "initial_metrics_stored_restart_index": 0,
                "restart_begin_expected_restart_source": "next_expected_restart",
                "restart_begin_expected_column": -1,
                "restart_begin_is_exception_to_active_restart_equality": True,
                "restart_begin_accepted_transition": (
                    "restart_index=expected_restart,column_index=0,"
                    "next_expected_restart=expected_restart+1"
                ),
                "schedule_epoch_B_formula": "7+4*S",
                "schedule_epoch_B_unique_mode": "RESTART_BEGIN",
                "final_guard_allowed_at_schedule_epoch_B": False,
                "outside_column_expected_column": -1,
                "active_restart_must_equal_stored_restart_index": True,
                "active_column_must_equal_stored_column_index": True,
            },
            "mismatch_sets_invalid_control_or_geometry": True,
            "mismatch_mutates_counters_or_published_scalars": False,
            "reduction_epoch_increments_only_after_valid_stage": True,
            "late_lane_data_error_may_follow_block0_epoch_increment": True,
            "late_lane_data_error_sets_device_error_and_active_zero": True,
            "schedule_epoch_increment_claims_global_data_validity": False,
            "multi_block_epoch_owner": "block_0_only",
            "nonzero_blocks_read_or_mutate_schedule_epoch": False,
            "nonzero_blocks_read_or_mutate_reduction_epoch": False,
        },
        "control_launch_geometry": {"grid_blocks": 1, "block_threads": 1},
        "vector_launch_geometry": {
            "grid_blocks": "ceil(F/256)",
            "block_threads": 256,
        },
        "spmv_launch_geometry": {
            "grid_blocks": "ceil(F/256)",
            "block_threads": 256,
        },
        "reduction_launch_geometry": {
            "block_threads": 256,
            "values_per_block": 512,
            "first_stage_grid_blocks": "ceil(value_count/512)",
            "combine_stage_grid_blocks": "ceil(partial_count/512)",
            "fixed_tree": "256_threads_512_values",
            "intermediate_output_condition": "output_count>=2",
            "intermediate_target": "NONE",
            "intermediate_publishes_scalar_or_valid_bit": False,
            "final_output_count": 1,
            "final_requires_named_non_none_target": True,
            "duplicate_valid_target_is_terminal_invalid_control": True,
            "combine_input_output_base_must_differ": True,
            "named_mode_target_compatibility": {
                "DOT_W_VI": ["DOT"],
                "LASSQ_LOAD": ["RHS_L2"],
                "LASSQ_TRUE_RESIDUAL": ["INITIAL_L2"],
                "LASSQ_WORK_W": [
                    "WORK_BEFORE",
                    "AFTER_FIRST",
                    "H_NEXT",
                    "TRIAL_X_L2",
                ],
                "LASSQ_V_M": ["CANDIDATE_L2"],
                "LASSQ_WORK_W_MINUS_X": ["UPDATE_L2"],
                "LASSQ_SOLUTION_X": ["COMMITTED_X_L2"],
                "LINF_LOAD": ["RHS_LINF"],
                "LINF_TRUE_RESIDUAL": ["INITIAL_LINF"],
                "LINF_V_M": ["CANDIDATE_LINF"],
                "COMBINE_SUM": ["DOT"],
                "COMBINE_LASSQ": [
                    "RHS_L2",
                    "INITIAL_L2",
                    "WORK_BEFORE",
                    "AFTER_FIRST",
                    "H_NEXT",
                    "CANDIDATE_L2",
                    "UPDATE_L2",
                    "COMMITTED_X_L2",
                    "TRIAL_X_L2",
                ],
                "COMBINE_MAX": ["RHS_LINF", "INITIAL_LINF", "CANDIDATE_LINF"],
            },
        },
        "first_column_partial_schedule": first_column_partial_schedule,
        "first_column_partial_schedule_hash": canonical_hash(
            first_column_partial_schedule
        ),
        "first_column_completion_schedule": first_column_completion_schedule,
        "first_column_completion_schedule_hash": canonical_hash(
            first_column_completion_schedule
        ),
        "first_column_candidate_preparation_schedule": (
            first_column_candidate_preparation_schedule
        ),
        "first_column_candidate_preparation_schedule_hash": canonical_hash(
            first_column_candidate_preparation_schedule
        ),
        "first_column_candidate_residual_schedule": (
            first_column_candidate_residual_schedule
        ),
        "first_column_candidate_residual_schedule_hash": canonical_hash(
            first_column_candidate_residual_schedule
        ),
        "first_column_candidate_scale_metrics_schedule": (
            first_column_candidate_scale_metrics_schedule
        ),
        "first_column_candidate_scale_metrics_schedule_hash": canonical_hash(
            first_column_candidate_scale_metrics_schedule
        ),
        "first_column_predecessor_validation_schedule": (
            first_column_predecessor_validation_schedule
        ),
        "first_column_predecessor_validation_schedule_hash": canonical_hash(
            first_column_predecessor_validation_schedule
        ),
        "first_column_checkpoint_transaction_schedule": (
            first_column_checkpoint_transaction_schedule
        ),
        "first_column_checkpoint_transaction_schedule_hash": canonical_hash(
            first_column_checkpoint_transaction_schedule
        ),
        "device_error_bits": dict(_DEVICE_ERROR_BITS),
        "device_error_masks": {
            name: 1 << bit for name, bit in _DEVICE_ERROR_BITS.items()
        },
        "control_state_abi_hash": canonical_hash(
            hip_fgmres_control_state_abi_payload_v2()
        ),
        "solve_record_abi_hash": canonical_hash(
            hip_fgmres_solve_record_abi_payload_v2()
        ),
        "active_mask_source": "solve_record_header.active",
        "device_error_state": "solve_record_header.device_error_bits",
        "single_code_object_required": True,
    }


def _base_index_layout_payload_v2() -> dict[str, Any]:
    return {
        "pointer_contract": "allocation_base_plus_explicit_logical_index",
        "host_shifted_pointer_arguments_allowed": False,
        "basis_v": {
            "logical_shape": "(M+1,F)",
            "element_formula": "basis_v_base[i*F+k]",
            "index_ranges": "0<=i<=M,0<=k<F",
        },
        "preconditioned_basis_z": {
            "logical_shape": "(M,F)",
            "element_formula": "basis_z_base[i*F+k]",
            "index_ranges": "0<=i<M,0<=k<F",
        },
        "hessenberg": {
            "logical_shape": "(M+1,M)",
            "element_formula": "dense_base[j*(M+1)+i]",
            "index_ranges": "0<=i<=M,0<=j<M",
            "layout": "column_major_(M+1)_by_M",
        },
        "packed_dense_offsets": {
            "hessenberg": "offset=0,length=M*(M+1)",
            "givens_cos": "offset=M*(M+1),length=M",
            "givens_sin": "offset=M*(M+1)+M,length=M",
            "least_squares_rhs": "offset=M*(M+1)+2*M,length=M+1",
            "triangular_solution": "offset=M*(M+1)+3*M+1,length=M",
        },
        "packed_dense_scalar_count": "M*M+5*M+1",
        "work_w_aliases": ["arnoldi_work", "candidate_trial_x"],
        "basis_v_last_row_aliases": [
            "candidate_spmv",
            "candidate_residual_scratch",
        ],
        "additional_O_F_workspace_allowed": False,
    }


class HipFgmresRecurrencePlanV2Error(ValueError):
    """Fail-closed recurrence-plan error with a stable code and JSON pointer."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresRecurrencePlanV2:
    """Immutable recurrence-v2 overlay on one exact FGMRES plan v1."""

    schema_version: str
    capability_profile: str
    plan_id: str
    plan_hash: str
    memory_layout_hash: str
    control_state_abi_hash: str
    solve_record_abi_hash: str
    kernel_module_abi_hash: str

    source_fgmres_schema_version: str
    source_fgmres_capability_profile: str
    source_fgmres_plan_id: str
    source_fgmres_plan_hash: str
    source_fgmres_memory_layout_hash: str
    source_execution_plan_hash: str
    source_free_space_plan_hash: str
    source_policy_hash: str

    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    restart_dimension: int
    max_iterations: int
    maximum_restart_count: int
    reduction_partial_count: int
    packed_dense_scalar_count: int

    buffers: tuple[HipFgmresBufferPlanV1, ...]
    borrowed_device_byte_span: int
    source_owned_device_byte_length: int
    owned_device_byte_length: int

    _source_fgmres_plan: HipFgmresPlanV1 = dataclass_field(
        repr=False,
        compare=False,
    )

    def buffer(self, name: str) -> HipFgmresBufferPlanV1:
        for row in self.buffers:
            if row.name == name:
                return row
        raise KeyError(f"Unknown HIP FGMRES recurrence-v2 buffer: {name}")

    def to_dict(self) -> dict[str, Any]:
        control_abi = hip_fgmres_control_state_abi_payload_v2()
        solve_record_abi = hip_fgmres_solve_record_abi_payload_v2()
        kernel_abi = hip_fgmres_recurrence_kernel_abi_payload_v2()
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "plan_id": self.plan_id,
            "source_fgmres_plan_contract": {
                "schema_version": self.source_fgmres_schema_version,
                "capability_profile": self.source_fgmres_capability_profile,
                "plan_id": self.source_fgmres_plan_id,
                "plan_hash": self.source_fgmres_plan_hash,
                "memory_layout_hash": self.source_fgmres_memory_layout_hash,
                "execution_plan_hash": self.source_execution_plan_hash,
                "free_space_plan_hash": self.source_free_space_plan_hash,
                "policy_hash": self.source_policy_hash,
                "exact_v1_semantic_replay_required": True,
                "v1_compatibility_artifact_retained": True,
            },
            "dimensions": {
                "global_dof_count": self.global_dof_count,
                "free_dof_count": self.free_dof_count,
                "reduced_csr_nnz": self.reduced_csr_nnz,
                "restart_dimension": self.restart_dimension,
                "max_iterations": self.max_iterations,
                "maximum_restart_count": self.maximum_restart_count,
                "reduction_segment_size": 512,
                "reduction_partial_count": self.reduction_partial_count,
                "packed_dense_scalar_count": self.packed_dense_scalar_count,
            },
            "algorithm_contract": {
                "recurrence_abi_version": 2,
                "method": "fixed_restart_right_preconditioned_fgmres",
                "scalar_type": "fp64",
                "right_preconditioner": "positive_unshifted_jacobi",
                "orthogonalization": "dgks_conditional_two_pass_mgs",
                "dgks_eta": 0.717,
                "breakdown_epsilon_multiplier": 64.0,
                "true_residual_equation": "r=b-Ax",
                "fixed_host_schedule": True,
                "submitted_column_count": "R*M",
                "planned_raw_iteration_h2d_count": 0,
                "planned_raw_iteration_d2h_count": 0,
                "planned_raw_iteration_sync_count": 0,
                "planned_raw_iteration_allocation_count": 0,
                "single_v2_code_object_required": True,
                "v1_and_v2_module_mixing_allowed": False,
                "solve_record_producer_recurrence_abi_version": 2,
                "base_pointer_plus_logical_index_only": True,
                "host_shifted_pointer_arguments_allowed": False,
                "dense_lstsq_or_pinv_fallback_allowed": False,
                "silent_solver_fallback_allowed": False,
            },
            "kernel_module_contract": {
                "symbol_count": len(_KERNEL_SYMBOLS),
                "symbols": list(_KERNEL_SYMBOLS),
                "single_code_object": True,
                "active_mask_source": "solve_record_header.active",
                "device_error_state": "solve_record_header.device_error_bits",
                "control_state_abi_hash": self.control_state_abi_hash,
                "solve_record_abi_hash": self.solve_record_abi_hash,
                "interface": kernel_abi,
                "kernel_module_abi_hash": self.kernel_module_abi_hash,
            },
            "memory_plan": {
                "buffer_order": [row.name for row in self.buffers],
                "borrowed_buffer_count": 7,
                "owned_buffer_count": 10,
                "borrowed_device_byte_span": self.borrowed_device_byte_span,
                "source_v1_owned_device_byte_length": (
                    self.source_owned_device_byte_length
                ),
                "owned_device_byte_length": self.owned_device_byte_length,
                "additional_peak_device_bytes_planned": (self.owned_device_byte_length),
                "incremental_owned_device_bytes_over_v1": 256,
                "control_state_storage_formula": "256",
                "control_state_abi": control_abi,
                "control_state_abi_hash": self.control_state_abi_hash,
                "solve_record_abi": solve_record_abi,
                "solve_record_abi_hash": self.solve_record_abi_hash,
                "base_index_layout": _base_index_layout_payload_v2(),
                "buffers": [row.to_dict() for row in self.buffers],
                "memory_layout_hash": self.memory_layout_hash,
            },
            "runtime_lineage_requirements": {
                "context_open_must_bind_exact_v2_plan": True,
                "context_open_must_bind_exact_latest_free_space_apply": True,
                "context_open_must_acquire_exclusive_primitive_child": True,
                "same_runtime_device_and_stream_required": True,
                "all_buffer_arguments_are_allocation_bases": True,
                "logical_indices_are_separate_scalar_arguments": True,
            },
            "claim_boundary": {
                "compile_time_plan_only": True,
                "control_abi_planned": True,
                "full_recurrence_interface_planned": True,
                "first_column_partial_schedule_contract_complete": True,
                "first_column_completion_schedule_contract_complete": True,
                "first_column_candidate_preparation_schedule_contract_complete": (True),
                "first_column_candidate_residual_schedule_contract_complete": True,
                "first_column_candidate_scale_metrics_schedule_contract_complete": (
                    True
                ),
                "first_column_predecessor_validation_schedule_contract_complete": (
                    True
                ),
                "first_column_checkpoint_transaction_schedule_contract_complete": (
                    True
                ),
                "first_column_commit_source_preflight_contract_complete": True,
                "invalid_source_destination_failure_atomicity_contract_complete": (
                    True
                ),
                "invalid_source_destination_failure_atomicity_runtime_proven": False,
                "authoritative_checkpoint_transaction_proven": False,
                "first_arnoldi_column_recurrence_schedule_contract_complete": True,
                "first_pass_mgs_schedule_contract_complete": True,
                "device_dgks_decision_schedule_contract_complete": True,
                "second_pass_mgs_schedule_contract_complete": True,
                "h_next_schedule_contract_complete": True,
                "v_next_schedule_contract_complete": True,
                "givens_schedule_contract_complete": True,
                "candidate_schedule_contract_complete": False,
                "candidate_envelope_schedule_contract_complete": False,
                "checkpoint_commit_schedule_contract_complete": False,
                "full_recurrence_schedule_contract_complete": False,
                "operator_apply_count_failure_parity_proven": False,
                "device_recurrence_implemented": False,
                "kernel_compiled": False,
                "device_allocation_performed": False,
                "execution_performed": False,
                "live_solver_ready": False,
                "solution_ready": False,
                "iteration_host_copy_zero_proven": False,
                "native_recurrence_parity": False,
                "end_to_end_O_N_proven": False,
                "speedup_proven": False,
                "result_ir_integrated": False,
                "spd_proven": False,
                "pcg_ready": False,
                "promotion_eligible": False,
                "commercial_ready": False,
                "schema_only_validation_authoritative": False,
                "python_semantic_replay_required": True,
            },
            "plan_hash": self.plan_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def compile_hip_fgmres_recurrence_plan_v2(
    source_plan: HipFgmresPlanV1,
) -> HipFgmresRecurrencePlanV2:
    """Compile the immutable recurrence-v2 ABI overlay without runtime work."""

    witness = _validated_source_snapshot(source_plan)
    artifact = _build_from_source(witness)
    validate_hip_fgmres_recurrence_plan_v2(
        artifact,
        expected_source_plan=source_plan,
    )
    return artifact


def validate_hip_fgmres_recurrence_plan_v2(
    artifact: HipFgmresRecurrencePlanV2,
    *,
    expected_source_plan: HipFgmresPlanV1 | None = None,
) -> None:
    """Replay the v1 source and every v2 extent, ABI, identity, and hash."""

    if type(artifact) is not HipFgmresRecurrencePlanV2:
        _raise(
            "hip_fgmres_recurrence_plan_type_invalid",
            "/",
            "Expected an exact HipFgmresRecurrencePlanV2 instance.",
        )
    if (
        type(artifact.buffers) is not tuple
        or any(type(row) is not HipFgmresBufferPlanV1 for row in artifact.buffers)
        or type(artifact._source_fgmres_plan) is not HipFgmresPlanV1
    ):
        _fail("hip_fgmres_recurrence_plan_container_invalid", "/")

    source = _validated_source_snapshot(artifact._source_fgmres_plan)
    if expected_source_plan is not None:
        if type(expected_source_plan) is not HipFgmresPlanV1:
            _fail(
                "hip_fgmres_recurrence_expected_source_invalid",
                "/source_fgmres_plan_contract",
            )
        expected_witness = _validated_source_snapshot(expected_source_plan)
        if expected_witness.plan_hash != source.plan_hash:
            _fail(
                "hip_fgmres_recurrence_expected_source_mismatch",
                "/source_fgmres_plan_contract/plan_hash",
            )

    try:
        manifest = artifact.to_dict()
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise HipFgmresRecurrencePlanV2Error(
            "hip_fgmres_recurrence_manifest_invalid",
            "/",
            f"Cannot build recurrence-v2 manifest: {exc}",
        ) from exc
    errors = sorted(
        _schema_validator().iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipFgmresRecurrencePlanV2Error(
            "hip_fgmres_recurrence_schema_invalid",
            path,
            error.message,
        )

    _validate_exact_scalar_types(artifact)
    if artifact.schema_version != HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION:
        _fail("hip_fgmres_recurrence_schema_mismatch", "/schema_version")
    if artifact.capability_profile != HIP_FGMRES_RECURRENCE_PLAN_V2_CAPABILITY_PROFILE:
        _fail("hip_fgmres_recurrence_profile_mismatch", "/capability_profile")

    expected = _build_from_source(source)
    source_bindings = (
        (
            artifact.source_fgmres_schema_version,
            source.schema_version,
            "schema_version",
        ),
        (
            artifact.source_fgmres_capability_profile,
            source.capability_profile,
            "capability_profile",
        ),
        (artifact.source_fgmres_plan_id, source.plan_id, "plan_id"),
        (artifact.source_fgmres_plan_hash, source.plan_hash, "plan_hash"),
        (
            artifact.source_fgmres_memory_layout_hash,
            source.memory_layout_hash,
            "memory_layout_hash",
        ),
        (
            artifact.source_execution_plan_hash,
            source.source_execution_plan_hash,
            "execution_plan_hash",
        ),
        (
            artifact.source_free_space_plan_hash,
            source.source_free_space_plan_hash,
            "free_space_plan_hash",
        ),
        (artifact.source_policy_hash, source.policy.policy_hash, "policy_hash"),
    )
    for actual, required, name in source_bindings:
        if actual != required:
            _fail(
                "hip_fgmres_recurrence_source_binding_mismatch",
                f"/source_fgmres_plan_contract/{name}",
            )

    dimension_names = (
        "global_dof_count",
        "free_dof_count",
        "reduced_csr_nnz",
        "restart_dimension",
        "max_iterations",
        "maximum_restart_count",
        "reduction_partial_count",
        "packed_dense_scalar_count",
    )
    for name in dimension_names:
        if getattr(artifact, name) != getattr(expected, name):
            _fail(
                "hip_fgmres_recurrence_dimension_mismatch",
                f"/dimensions/{name}",
            )

    if artifact.buffers != expected.buffers:
        _fail(
            "hip_fgmres_recurrence_buffer_plan_mismatch",
            "/memory_plan/buffers",
        )
    if [row.name for row in artifact.buffers] != [row.name for row in expected.buffers]:
        _fail(
            "hip_fgmres_recurrence_buffer_order_mismatch",
            "/memory_plan/buffer_order",
        )
    for name, manifest_name in (
        ("borrowed_device_byte_span", "borrowed_device_byte_span"),
        (
            "source_owned_device_byte_length",
            "source_v1_owned_device_byte_length",
        ),
        ("owned_device_byte_length", "owned_device_byte_length"),
    ):
        if getattr(artifact, name) != getattr(expected, name):
            _fail(
                "hip_fgmres_recurrence_extent_mismatch",
                f"/memory_plan/{manifest_name}",
            )

    required_control_hash = canonical_hash(hip_fgmres_control_state_abi_payload_v2())
    required_record_hash = canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
    required_kernel_hash = canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2())
    for actual, required, name in (
        (
            artifact.control_state_abi_hash,
            required_control_hash,
            "control_state_abi_hash",
        ),
        (
            artifact.solve_record_abi_hash,
            required_record_hash,
            "solve_record_abi_hash",
        ),
        (
            artifact.kernel_module_abi_hash,
            required_kernel_hash,
            "kernel_module_abi_hash",
        ),
    ):
        if actual != required:
            _fail(
                "hip_fgmres_recurrence_abi_hash_mismatch",
                f"/kernel_module_contract/{name}",
            )

    if artifact.memory_layout_hash != _memory_layout_hash(artifact):
        _fail(
            "hip_fgmres_recurrence_memory_layout_hash_mismatch",
            "/memory_plan/memory_layout_hash",
        )
    if artifact.plan_id != _plan_id(artifact):
        _fail("hip_fgmres_recurrence_plan_id_mismatch", "/plan_id")
    if artifact.plan_hash != _plan_hash(artifact):
        _fail("hip_fgmres_recurrence_plan_hash_mismatch", "/plan_hash")
    if manifest != expected.to_dict():
        _fail("hip_fgmres_recurrence_semantic_replay_mismatch", "/")


def _validated_source_snapshot(source: HipFgmresPlanV1) -> HipFgmresPlanV1:
    if type(source) is not HipFgmresPlanV1:
        _raise(
            "hip_fgmres_recurrence_source_invalid",
            "/source_fgmres_plan_contract",
            "Source must be an exact HipFgmresPlanV1.",
        )
    try:
        validate_hip_fgmres_plan_v1(
            source,
            expected_execution_plan=source._source_execution_plan,
            expected_free_space_plan=source._source_free_space_plan,
        )
        witness = compile_hip_fgmres_plan_v1(
            source._source_execution_plan,
            source._source_free_space_plan,
            source.policy,
        )
        source_manifest = source.to_dict()
        witness_manifest = witness.to_dict()
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        HipFgmresPlanV1Error,
    ) as exc:
        raise HipFgmresRecurrencePlanV2Error(
            "hip_fgmres_recurrence_source_invalid",
            getattr(exc, "path", "/source_fgmres_plan_contract"),
            f"{getattr(exc, 'code', type(exc).__name__)}: "
            f"{getattr(exc, 'message', str(exc))}",
        ) from exc
    if witness_manifest != source_manifest:
        _fail(
            "hip_fgmres_recurrence_source_replay_mismatch",
            "/source_fgmres_plan_contract",
        )
    return witness


def _build_from_source(source: HipFgmresPlanV1) -> HipFgmresRecurrencePlanV2:
    buffers = tuple(replace(row) for row in source.buffers) + (
        HipFgmresBufferPlanV1(
            name=_CONTROL_BUFFER_NAME,
            ownership="owned",
            dtype="|u1",
            shape=(HIP_FGMRES_CONTROL_STATE_BYTES_V2,),
            element_count=HIP_FGMRES_CONTROL_STATE_BYTES_V2,
            byte_length=HIP_FGMRES_CONTROL_STATE_BYTES_V2,
            access="read_write",
            source="fgmres_recurrence_context_v2",
            initialization="async_h2d_zero_once_before_control_init",
            extent_formula="256",
        ),
    )
    control_hash = canonical_hash(hip_fgmres_control_state_abi_payload_v2())
    record_hash = canonical_hash(hip_fgmres_solve_record_abi_payload_v2())
    kernel_hash = canonical_hash(hip_fgmres_recurrence_kernel_abi_payload_v2())
    artifact = HipFgmresRecurrencePlanV2(
        schema_version=HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION,
        capability_profile=HIP_FGMRES_RECURRENCE_PLAN_V2_CAPABILITY_PROFILE,
        plan_id="HipFgmresRecurrencePlan:" + "0" * 24,
        plan_hash=_ZERO_HASH,
        memory_layout_hash=_ZERO_HASH,
        control_state_abi_hash=control_hash,
        solve_record_abi_hash=record_hash,
        kernel_module_abi_hash=kernel_hash,
        source_fgmres_schema_version=source.schema_version,
        source_fgmres_capability_profile=source.capability_profile,
        source_fgmres_plan_id=source.plan_id,
        source_fgmres_plan_hash=source.plan_hash,
        source_fgmres_memory_layout_hash=source.memory_layout_hash,
        source_execution_plan_hash=source.source_execution_plan_hash,
        source_free_space_plan_hash=source.source_free_space_plan_hash,
        source_policy_hash=source.policy.policy_hash,
        global_dof_count=source.global_dof_count,
        free_dof_count=source.free_dof_count,
        reduced_csr_nnz=source.reduced_csr_nnz,
        restart_dimension=source.restart_dimension,
        max_iterations=source.max_iterations,
        maximum_restart_count=source.maximum_restart_count,
        reduction_partial_count=source.reduction_partial_count,
        packed_dense_scalar_count=source.packed_dense_scalar_count,
        buffers=buffers,
        borrowed_device_byte_span=source.borrowed_device_byte_span,
        source_owned_device_byte_length=source.owned_device_byte_length,
        owned_device_byte_length=(
            source.owned_device_byte_length + HIP_FGMRES_CONTROL_STATE_BYTES_V2
        ),
        _source_fgmres_plan=source,
    )
    artifact = replace(artifact, memory_layout_hash=_memory_layout_hash(artifact))
    artifact = replace(artifact, plan_id=_plan_id(artifact))
    return replace(artifact, plan_hash=_plan_hash(artifact))


def _validate_exact_scalar_types(artifact: HipFgmresRecurrencePlanV2) -> None:
    for name in (
        "global_dof_count",
        "free_dof_count",
        "reduced_csr_nnz",
        "restart_dimension",
        "reduction_partial_count",
        "packed_dense_scalar_count",
        "borrowed_device_byte_span",
        "source_owned_device_byte_length",
        "owned_device_byte_length",
    ):
        if type(getattr(artifact, name)) is not int or getattr(artifact, name) <= 0:
            _fail(
                "hip_fgmres_recurrence_scalar_type_invalid",
                f"/dimensions/{name}",
            )
    for name in ("max_iterations", "maximum_restart_count"):
        if type(getattr(artifact, name)) is not int or getattr(artifact, name) < 0:
            _fail(
                "hip_fgmres_recurrence_scalar_type_invalid",
                f"/dimensions/{name}",
            )
    for name in (
        "schema_version",
        "capability_profile",
        "plan_id",
        "plan_hash",
        "memory_layout_hash",
        "control_state_abi_hash",
        "solve_record_abi_hash",
        "kernel_module_abi_hash",
        "source_fgmres_schema_version",
        "source_fgmres_capability_profile",
        "source_fgmres_plan_id",
        "source_fgmres_plan_hash",
        "source_fgmres_memory_layout_hash",
        "source_execution_plan_hash",
        "source_free_space_plan_hash",
        "source_policy_hash",
    ):
        if type(getattr(artifact, name)) is not str:
            _fail(
                "hip_fgmres_recurrence_scalar_type_invalid",
                f"/{name}",
            )


def _memory_layout_hash(artifact: HipFgmresRecurrencePlanV2) -> str:
    memory = artifact.to_dict()["memory_plan"]
    memory.pop("memory_layout_hash")
    return canonical_hash(
        {
            "recurrence_abi_version": 2,
            "source_v1_memory_layout_hash": (artifact.source_fgmres_memory_layout_hash),
            "kernel_module_abi_hash": artifact.kernel_module_abi_hash,
            "memory_plan": memory,
        }
    )


def _plan_id(artifact: HipFgmresRecurrencePlanV2) -> str:
    digest = canonical_hash(
        {
            "source_fgmres_plan_hash": artifact.source_fgmres_plan_hash,
            "memory_layout_hash": artifact.memory_layout_hash,
            "control_state_abi_hash": artifact.control_state_abi_hash,
            "solve_record_abi_hash": artifact.solve_record_abi_hash,
            "kernel_module_abi_hash": artifact.kernel_module_abi_hash,
        }
    )
    return "HipFgmresRecurrencePlan:" + digest.removeprefix("sha256:")[:24]


def _plan_hash(artifact: HipFgmresRecurrencePlanV2) -> str:
    payload = artifact.to_dict()
    payload.pop("plan_hash")
    return canonical_hash(payload)


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "hip_fgmres_recurrence_plan_v2.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresRecurrencePlanV2Error(code, path, message or code)


def _raise(code: str, path: str, message: str) -> None:
    raise HipFgmresRecurrencePlanV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_CONTROL_ABI_VERSION_V2",
    "HIP_FGMRES_CONTROL_STATE_BYTES_V2",
    "HIP_FGMRES_RECURRENCE_ABI_VERSION_V2",
    "HIP_FGMRES_RECURRENCE_PLAN_V2_CAPABILITY_PROFILE",
    "HIP_FGMRES_RECURRENCE_PLAN_V2_SCHEMA_VERSION",
    "HipFgmresRecurrencePlanV2",
    "HipFgmresRecurrencePlanV2Error",
    "compile_hip_fgmres_recurrence_plan_v2",
    "hip_fgmres_control_state_abi_payload_v2",
    "hip_fgmres_first_column_candidate_preparation_schedule_payload_v2",
    "hip_fgmres_first_column_candidate_residual_schedule_payload_v2",
    "hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2",
    "hip_fgmres_first_column_predecessor_validation_schedule_payload_v2",
    "hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2",
    "hip_fgmres_first_column_completion_schedule_payload_v2",
    "hip_fgmres_first_column_partial_schedule_payload_v2",
    "hip_fgmres_recurrence_kernel_abi_payload_v2",
    "hip_fgmres_solve_record_abi_payload_v2",
    "validate_hip_fgmres_recurrence_plan_v2",
]
