from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_completion_export_v1 as completion_export_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_terminal_outcome_observation_v1 as observation_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    HipFgmresCompletionExportResultV1,
    HipFgmresCompletionExportV1Error,
    open_hip_fgmres_completion_export_context_v1,
    validate_hip_fgmres_completion_export_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_EVIDENCE_SCOPE_V1,
    HipFgmresTerminalOutcomeObservationV1Error,
    observe_hip_fgmres_terminal_outcome_v1,
    validate_hip_fgmres_terminal_outcome_observation_receipt_v1,
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_completion_export_v1 import (
    _BlockingCopyProbe,
    _completion_sources,
    _fence_global,
)
from tests.test_engine_v2_hip_fgmres_global_recurrence_context_v1 import (
    _close_stack,
    _open_stack,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_terminal_outcome_observation_v1.schema.json"
)
_ZERO_HASH = "sha256:" + "0" * 64
_HEADER_BYTES = 192
_RESTART_BYTES = 72
_ABI = hip_fgmres_solve_record_abi_payload_v2()
_STATUS_CODES = _ABI["terminal_status_codes"]
_TERMINATION_CODES = _ABI["termination_codes"]
_HINT_CODES = _ABI["restart_hint_codes"]
_FLAG_BITS = _ABI["restart_flag_bits"]
_ALLOWED_FAILURE_ERROR_MASKS_BY_CODE = {
    40: frozenset({1, 16}),
    41: frozenset({4, 8, 12, 64, 72}),
    42: frozenset({1, 2, 4, 6, 8, 10, 12, 14, 16}),
    43: frozenset({4, 8, 12, 32, 36, 40, 44}),
    44: frozenset({8}),
    45: frozenset({8}),
    46: frozenset({4, 8, 12}),
    47: frozenset({1, 4, 8, 12}),
}
_DISALLOWED_FAILURE_ERROR_MASK_BY_CODE = {
    40: 2,
    41: 1,
    42: 32,
    43: 1,
    44: 4,
    45: 4,
    46: 1,
    47: 2,
}

_TERMINATION_STATUS = {
    "converged_initial_true_residual": "converged",
    "converged_happy_breakdown": "converged",
    "converged_true_residual": "converged",
    "converged_restart_true_residual": "converged",
    "max_iterations_exhausted": "max_iterations",
    "true_residual_stagnated": "stagnated",
    "true_residual_diverged": "diverged",
    "arnoldi_triangular_factor_breakdown": "arnoldi_breakdown",
    "arnoldi_invariant_subspace_breakdown": "arnoldi_breakdown",
    "invalid_input_or_control": "numerical_failure",
    "nonfinite_arithmetic": "numerical_failure",
    "operator_application_failed": "numerical_failure",
    "orthogonalization_failed": "numerical_failure",
    "givens_rotation_failed": "numerical_failure",
    "triangular_solve_failed": "numerical_failure",
    "true_residual_replay_failed": "numerical_failure",
    "restart_state_failed": "numerical_failure",
}
_NUMERICAL_FAILURES = tuple(
    name
    for name, value in sorted(
        _TERMINATION_CODES.items(),
        key=lambda item: item[1],
    )
    if 40 <= value <= 47
)
_VALID_TERMINATIONS = (
    "converged_initial_true_residual",
    "converged_happy_breakdown",
    "converged_true_residual",
    "converged_restart_true_residual",
    "max_iterations_exhausted",
    "true_residual_stagnated",
    "true_residual_diverged",
    "arnoldi_triangular_factor_breakdown",
    "arnoldi_invariant_subspace_breakdown",
    *_NUMERICAL_FAILURES,
)


@dataclass
class _ExportHarness:
    stack: dict[str, Any]
    context: Any
    template: HipFgmresCompletionExportResultV1
    policy: Any
    probe: _BlockingCopyProbe

    def close(self) -> None:
        if not self.context.closed:
            self.context.close()
        _close_stack(self.stack)


def _descriptor(name: str, *, restart: bool) -> dict[str, Any]:
    key = "restart_fields" if restart else "header_fields"
    return next(field for field in _ABI[key] if field["name"] == name)


def _write_field(
    payload: bytearray,
    name: str,
    value: int | float,
    *,
    restart_index: int | None = None,
) -> None:
    descriptor = _descriptor(name, restart=restart_index is not None)
    base = 0
    if restart_index is not None:
        base = _HEADER_BYTES + restart_index * _RESTART_BYTES
    format_code = "<i" if descriptor["dtype"] == "i32" else "<d"
    struct.pack_into(format_code, payload, base + descriptor["offset_bytes"], value)


def _flag(*names: str) -> int:
    return sum(1 << int(_FLAG_BITS[name]) for name in names)


def _terminal_payloads(
    policy: Any,
    free_dof_count: int,
    termination: str,
) -> tuple[bytes, bytes, bytes]:
    """Build one exact little-endian terminal v2 solve-record payload."""

    status = _TERMINATION_STATUS[termination]
    numerical_failure = status == "numerical_failure"
    converged = status == "converged"
    initial_terminal = termination == "converged_initial_true_residual"
    maximum_restarts = policy.maximum_restart_count
    assert policy.restart_dimension == 2
    assert policy.max_iterations == 4
    assert maximum_restarts == 2

    final_residual = 0.0 if converged else 1.0
    initial_residual = (
        float.fromhex("0x1p-40")
        if termination == "true_residual_diverged"
        else (0.0 if initial_terminal else 1.0)
    )
    rhs_l2 = 2.0
    rhs_linf = 2.0
    scaled_residual = final_residual / rhs_linf
    solver_tolerance = max(
        policy.absolute_tolerance,
        policy.relative_tolerance * rhs_l2,
    )

    rows: list[dict[str, int | float]] = []
    if termination in {
        "max_iterations_exhausted",
        "true_residual_stagnated",
    }:
        for index in range(maximum_restarts):
            start = index * policy.restart_dimension
            end = min(start + policy.restart_dimension, policy.max_iterations)
            flags = _flag(
                "true_residual_replayed",
                "stagnation_plateau",
            )
            if (
                termination == "true_residual_stagnated"
                or index == maximum_restarts - 1
            ):
                flags |= _flag("tiny_update")
            rows.append(
                {
                    "restart_index": index + 1,
                    "start_iteration": start,
                    "end_iteration": end,
                    "arnoldi_step_count": end - start,
                    "reorthogonalization_count": 0,
                    "termination_hint": _HINT_CODES["restart_completed"],
                    "flags": flags,
                    "reserved_i32_0": 0,
                    "estimated_residual_l2": final_residual,
                    "true_residual_l2": final_residual,
                    "true_residual_linf": final_residual,
                    "scaled_true_residual": scaled_residual,
                    "solution_update_l2": 0.0,
                }
            )
    elif not initial_terminal and not numerical_failure:
        hint_by_termination = {
            "converged_happy_breakdown": "converged_happy_breakdown",
            "converged_true_residual": "converged_true_residual",
            "converged_restart_true_residual": "restart_completed",
            "true_residual_stagnated": "restart_completed",
            "true_residual_diverged": "restart_completed",
            "arnoldi_triangular_factor_breakdown": (
                "arnoldi_triangular_factor_breakdown"
            ),
            "arnoldi_invariant_subspace_breakdown": (
                "arnoldi_invariant_subspace_breakdown"
            ),
        }
        end_iteration = (
            policy.restart_dimension
            if termination
            in {
                "converged_restart_true_residual",
                "true_residual_diverged",
            }
            else 1
        )
        flags = 0
        if termination != "arnoldi_triangular_factor_breakdown":
            flags |= _flag("true_residual_replayed")
        if converged:
            flags |= _flag("solver_l2_passed", "authoritative_linf_passed")
        if termination == "converged_happy_breakdown":
            flags |= _flag("happy_breakdown")
        elif termination == "true_residual_stagnated":
            flags |= _flag("stagnation_plateau", "tiny_update")
        elif termination == "true_residual_diverged":
            flags |= _flag("divergence")
        elif termination == "arnoldi_invariant_subspace_breakdown":
            flags |= _flag("invariant_breakdown")
        rows.append(
            {
                "restart_index": 1,
                "start_iteration": 0,
                "end_iteration": end_iteration,
                "arnoldi_step_count": end_iteration,
                "reorthogonalization_count": 0,
                "termination_hint": _HINT_CODES[hint_by_termination[termination]],
                "flags": flags,
                "reserved_i32_0": 0,
                "estimated_residual_l2": final_residual,
                "true_residual_l2": final_residual,
                "true_residual_linf": final_residual,
                "scaled_true_residual": scaled_residual,
                "solution_update_l2": 0.0,
            }
        )

    effective_iterations = int(rows[-1]["end_iteration"]) if rows else 0
    effective_restarts = len(rows)
    effective_dimension = int(rows[-1]["arnoldi_step_count"]) if rows else 0
    replayed_restarts = sum(
        bool(int(row["flags"]) & _flag("true_residual_replayed")) for row in rows
    )
    error_bits = 0
    if numerical_failure:
        termination_value = _TERMINATION_CODES[termination]
        error_bits = min(_ALLOWED_FAILURE_ERROR_MASKS_BY_CODE[termination_value])

    header: dict[str, int | float] = {
        "recurrence_abi_version": HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
        "active": 0,
        "terminal_status": _STATUS_CODES[status],
        "termination_code": _TERMINATION_CODES[termination],
        "device_error_bits": error_bits,
        "scheduled_iterations": policy.max_iterations,
        "effective_iterations": 0 if numerical_failure else effective_iterations,
        "scheduled_restarts": maximum_restarts,
        "effective_restarts": 0 if numerical_failure else effective_restarts,
        "effective_arnoldi_dimension": (
            0 if numerical_failure else effective_dimension
        ),
        "happy_breakdown_count": int(termination == "converged_happy_breakdown"),
        "stagnation_checkpoint_count": (
            policy.stagnation_checkpoint_limit
            if termination == "true_residual_stagnated"
            else (1 if termination == "max_iterations_exhausted" else 0)
        ),
        "false_convergence_count": 0,
        "operator_apply_count": (
            1 if numerical_failure else 1 + effective_iterations + replayed_restarts
        ),
        "preconditioner_apply_count": (
            0 if numerical_failure else effective_iterations
        ),
        "restart_dimension": policy.restart_dimension,
        "rhs_l2": rhs_l2,
        "rhs_linf": rhs_linf,
        "solver_tolerance_l2": solver_tolerance,
        "authoritative_tolerance_scaled_linf": (policy.authoritative_tolerance),
        "initial_residual_l2": initial_residual,
        "final_residual_l2": final_residual,
        "final_residual_linf": final_residual,
        "final_scaled_residual": scaled_residual,
        "previous_checkpoint_residual_l2": initial_residual,
        "solution_update_l2": 0.0,
        "solution_scale_l2": 0.0,
        "estimated_residual_l2": final_residual,
        "arnoldi_work_l2": 0.0 if initial_terminal else 1.0,
        "arnoldi_breakdown_threshold": (
            0.0 if initial_terminal else float.fromhex("0x1p-46")
        ),
        "triangular_scale": 0.0 if initial_terminal else 1.0,
        "reserved_f64_0": 0.0,
    }
    record = bytearray(_HEADER_BYTES + _RESTART_BYTES * maximum_restarts)
    for name, value in header.items():
        _write_field(record, name, value)
    for index, row in enumerate(rows):
        for name, value in row.items():
            _write_field(record, name, value, restart_index=index)

    solution = np.zeros(free_dof_count, dtype="<f8")
    residual = np.zeros(free_dof_count, dtype="<f8")
    residual[0] = final_residual
    if termination == "nonfinite_arithmetic":
        solution.fill(np.finfo(np.float64).max)
        residual.fill(np.finfo(np.float64).max)
    return solution.tobytes(), residual.tobytes(), bytes(record)


def _mutated_field(
    payload: bytes,
    name: str,
    value: int | float,
    *,
    restart_index: int | None = None,
) -> bytes:
    mutated = bytearray(payload)
    _write_field(mutated, name, value, restart_index=restart_index)
    return bytes(mutated)


def _open_actual_export(monkeypatch: pytest.MonkeyPatch) -> _ExportHarness:
    stack = _open_stack(monkeypatch, restart_dimension=2, max_iterations=4)
    context = None
    try:
        completion = _fence_global(stack)
        probe = _BlockingCopyProbe()
        probe.install(monkeypatch, stack["runtime"])
        context = open_hip_fgmres_completion_export_context_v1(
            stack["global"].context,
            completion,
        ).context
        policy = completion_export_module._completion_export_policy_snapshot(
            context._authority
        )
        sources = _completion_sources(stack)
        free_dof_count = sources[0].nbytes // 8
        payloads = _terminal_payloads(
            policy,
            free_dof_count,
            "converged_initial_true_residual",
        )
        for source, payload in zip(sources, payloads, strict=True):
            assert source.nbytes == len(payload)
            stack["runtime"].allocations[int(source.pointer_snapshot)][:] = payload
        result = context.export()
        assert probe.calls == [
            (int(source.pointer_snapshot), int(source.nbytes)) for source in sources
        ]
        return _ExportHarness(stack, context, result, policy, probe)
    except BaseException:
        if context is not None and not context.closed:
            context.close()
        _close_stack(stack)
        raise


def _reseal_test_export(
    harness: _ExportHarness,
    payloads: tuple[bytes, bytes, bytes],
) -> HipFgmresCompletionExportResultV1:
    """Install a test-local final seal after one authoritative real export.

    The completion exporter itself is exercised exactly once by
    ``_open_actual_export``.  Re-sealing keeps the expensive recurrence stack
    fixed while letting the observer's exhaustive terminal-code matrix run
    through its public provenance gate rather than calling its private parser.
    """

    template = harness.template
    bundle_hash = completion_export_module._bundle_hash(payloads)
    buffers = tuple(
        replace(
            row,
            payload_sha256=completion_export_module._sha256_bytes(payload),
        )
        for row, payload in zip(template.receipt.buffers, payloads, strict=True)
    )
    receipt_draft = replace(
        template.receipt,
        buffers=buffers,
        payload_hash=bundle_hash,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        receipt_draft,
        receipt_hash=canonical_hash(
            completion_export_module._receipt_payload(
                receipt_draft,
                include_hash=False,
            )
        ),
    )
    result = replace(
        template,
        receipt=receipt,
        solution_x=payloads[0],
        true_residual=payloads[1],
        solve_record=payloads[2],
        payload_hash=bundle_hash,
    )
    seal = completion_export_module._published_result_authority(
        result,
        harness.policy,
    )
    snapshot = completion_export_module._published_result_authority_snapshot(seal)
    with harness.context._lock:
        harness.context._publication = result
        harness.context._result = result
        harness.context._published_result_authority_state = (seal, snapshot)
        harness.context._state = "exported"
    validate_hip_fgmres_completion_export_result_v1(
        result,
        expected_context=harness.context,
    )
    return result


def _rehashed_observation_receipt(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            observation_module._receipt_payload(draft, include_hash=False)
        ),
    )


def test_terminal_outcome_observes_complete_terminal_code_table_and_preserves_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _open_actual_export(monkeypatch)
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        free_dof_count = harness.template.receipt.dimensions.free_dof_count

        for termination in _VALID_TERMINATIONS:
            payloads = _terminal_payloads(
                harness.policy,
                free_dof_count,
                termination,
            )
            result = _reseal_test_export(harness, payloads)
            source_receipt = result.receipt
            source_receipt_identity = id(source_receipt)
            source_manifest = source_receipt.to_dict()
            source_payloads = (
                result.solution_x,
                result.true_residual,
                result.solve_record,
            )

            observed = observe_hip_fgmres_terminal_outcome_v1(
                result,
                expected_export_context=harness.context,
            )
            receipt = observed.receipt
            outcome = observed.outcome
            status = _TERMINATION_STATUS[termination]
            numerical_failure = status == "numerical_failure"
            expected_class = (
                "converged"
                if status == "converged"
                else ("numerical_failure" if numerical_failure else "not_converged")
            )
            assert outcome.outcome_class == expected_class
            assert outcome.active == 0
            assert outcome.terminal_status == status
            assert outcome.terminal_status_code == _STATUS_CODES[status]
            assert outcome.termination_code == termination
            assert outcome.termination_code_value == _TERMINATION_CODES[termination]
            assert bool(outcome.device_error_names) is numerical_failure
            assert (
                receipt.status
                == {
                    "converged": "terminal_converged",
                    "not_converged": "terminal_not_converged",
                    "numerical_failure": "terminal_numerical_failure",
                }[expected_class]
            )
            assert receipt.evidence_scope == (
                HIP_FGMRES_TERMINAL_OUTCOME_OBSERVATION_EVIDENCE_SCOPE_V1
            )
            assert receipt.bindings.completion_export_receipt_hash == (
                source_receipt.receipt_hash
            )
            assert receipt.bindings.completion_export_payload_hash == (
                source_receipt.payload_hash
            )
            assert receipt.bindings.solve_record_payload_sha256 == (
                source_receipt.buffers[2].payload_sha256
            )
            assert receipt.outcome_hash == canonical_hash(outcome.to_dict())
            assert receipt.receipt_hash == canonical_hash(
                observation_module._receipt_payload(receipt, include_hash=False)
            )
            assert receipt.telemetry.completion_export_source_result_count == 1
            assert receipt.telemetry.solve_record_payload_count == 1
            assert receipt.telemetry.published_terminal_outcome_count == 1
            assert receipt.telemetry.additional_d2h_operation_count == 0
            assert receipt.telemetry.kernel_launch_count == 0
            assert receipt.claims.process_local_export_provenance_verified
            assert receipt.claims.authoritative_terminal_status_proven
            assert not receipt.claims.authoritative_completion_or_solution_receipt
            assert not receipt.claims.numerical_parity_verified
            assert not receipt.claims.solution_ready
            assert not receipt.claims.result_ir_ready
            assert not receipt.claims.performance_or_speedup_proven
            assert not receipt.claims.commercial_ready
            assert not receipt.claims.promotion_eligible
            if numerical_failure:
                assert not outcome.record_metrics_authoritative
                assert outcome.metrics is None
                assert outcome.true_residual_record_metrics_match is None
                assert outcome.observed_solution_x_l2 is None
                assert outcome.observed_true_residual_l2 is None
                assert outcome.observed_true_residual_linf is None
                if termination == "nonfinite_arithmetic":
                    assert outcome.solution_x_all_finite
                    assert outcome.true_residual_all_finite
                    assert np.frombuffer(result.solution_x, dtype="<f8").min() == (
                        np.finfo(np.float64).max
                    )
            else:
                assert outcome.record_metrics_authoritative
                assert outcome.metrics is not None
                assert outcome.true_residual_record_metrics_match is True
                assert outcome.solution_x_all_finite
                assert outcome.true_residual_all_finite
                assert outcome.observed_solution_x_l2 is None

            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                receipt,
                expected_export_result=result,
                expected_export_context=harness.context,
            )
            validate_hip_fgmres_terminal_outcome_observation_result_v1(
                observed,
                expected_export_result=result,
                expected_export_context=harness.context,
            )
            manifest = observed.to_manifest()
            validator.validate(manifest)
            assert id(result.receipt) == source_receipt_identity
            assert result.receipt.to_dict() == source_manifest
            assert (
                result.solution_x,
                result.true_residual,
                result.solve_record,
            ) == source_payloads
            assert not result.receipt.claims.solve_record_semantics_interpreted
            assert not result.receipt.claims.actual_terminal_outcome_host_observed
            assert not result.receipt.claims.authoritative_terminal_status_proven

        assert harness.probe.calls and len(harness.probe.calls) == 3
        assert (
            _terminal_payloads(
                harness.policy,
                free_dof_count,
                "converged_initial_true_residual",
            )[2][:8]
            == b"\x02\x00\x00\x00\x00\x00\x00\x00"
        )

        for termination in _NUMERICAL_FAILURES:
            termination_value = _TERMINATION_CODES[termination]
            base_payloads = _terminal_payloads(
                harness.policy,
                free_dof_count,
                termination,
            )
            for allowed_mask in sorted(
                _ALLOWED_FAILURE_ERROR_MASKS_BY_CODE[termination_value]
            ):
                payloads = (
                    base_payloads[0],
                    base_payloads[1],
                    _mutated_field(
                        base_payloads[2],
                        "device_error_bits",
                        allowed_mask,
                    ),
                )
                result = _reseal_test_export(harness, payloads)
                observed_allowed = observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
                assert observed_allowed.outcome.termination_code == termination
                assert observed_allowed.outcome.device_error_bits == allowed_mask
                observed = observed_allowed

        for termination in (
            "nonfinite_arithmetic",
            "operator_application_failed",
        ):
            base_payloads = _terminal_payloads(
                harness.policy,
                free_dof_count,
                termination,
            )
            payloads = (
                base_payloads[0],
                base_payloads[1],
                _mutated_field(
                    base_payloads[2],
                    "operator_apply_count",
                    0,
                ),
            )
            result = _reseal_test_export(harness, payloads)
            observed_pre_restart = observe_hip_fgmres_terminal_outcome_v1(
                result,
                expected_export_context=harness.context,
            )
            assert observed_pre_restart.outcome.termination_code == termination
            assert observed_pre_restart.outcome.counters.operator_apply_count == 0
            observed = observed_pre_restart

        strict_manifest = observed.to_manifest()
        strict_manifest["unexpected"] = True
        with pytest.raises(ValidationError):
            validator.validate(strict_manifest)
    finally:
        harness.close()


def test_terminal_outcome_rejects_invalid_record_and_payload_matrix_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _open_actual_export(monkeypatch)
    try:
        free_dof_count = harness.template.receipt.dimensions.free_dof_count
        initial = _terminal_payloads(
            harness.policy,
            free_dof_count,
            "converged_initial_true_residual",
        )
        true_convergence = _terminal_payloads(
            harness.policy,
            free_dof_count,
            "converged_true_residual",
        )
        maximum = _terminal_payloads(
            harness.policy,
            free_dof_count,
            "max_iterations_exhausted",
        )
        failure = _terminal_payloads(
            harness.policy,
            free_dof_count,
            "invalid_input_or_control",
        )
        initial_metric_mismatch = _mutated_field(
            initial[2],
            "initial_residual_l2",
            1.0,
        )
        initial_metric_mismatch = _mutated_field(
            initial_metric_mismatch,
            "previous_checkpoint_residual_l2",
            1.0,
        )

        row_gap = bytearray(maximum[2])
        row_gap[_HEADER_BYTES : _HEADER_BYTES + _RESTART_BYTES] = bytes(_RESTART_BYTES)
        zero_residual = np.zeros(free_dof_count, dtype="<f8").tobytes()
        excessive_replay_record = _mutated_field(
            true_convergence[2],
            "false_convergence_count",
            1,
        )
        invalid_failure_progress = _mutated_field(
            failure[2],
            "effective_restarts",
            1,
        )
        invalid_failure_progress = _mutated_field(
            invalid_failure_progress,
            "effective_iterations",
            1,
        )
        pre_restart_operator_overcount = _terminal_payloads(
            harness.policy,
            free_dof_count,
            "nonfinite_arithmetic",
        )
        pre_restart_operator_overcount = (
            pre_restart_operator_overcount[0],
            pre_restart_operator_overcount[1],
            _mutated_field(
                pre_restart_operator_overcount[2],
                "operator_apply_count",
                2,
            ),
        )
        historical_failure_record = _mutated_field(
            maximum[2],
            "terminal_status",
            _STATUS_CODES["numerical_failure"],
        )
        historical_failure_record = _mutated_field(
            historical_failure_record,
            "termination_code",
            _TERMINATION_CODES["nonfinite_arithmetic"],
        )
        historical_failure_record = _mutated_field(
            historical_failure_record,
            "device_error_bits",
            4,
        )
        historical_failure_payloads = (
            maximum[0],
            maximum[1],
            historical_failure_record,
        )
        historical_result = _reseal_test_export(
            harness,
            historical_failure_payloads,
        )
        historical_observed = observe_hip_fgmres_terminal_outcome_v1(
            historical_result,
            expected_export_context=harness.context,
        )
        assert historical_observed.outcome.termination_code == ("nonfinite_arithmetic")
        assert (
            sum(row.populated for row in historical_observed.outcome.restart_rows) == 2
        )
        forged_history_flags = _mutated_field(
            historical_failure_record,
            "flags",
            _flag(
                "true_residual_replayed",
                "solver_l2_passed",
                "stagnation_plateau",
            ),
            restart_index=0,
        )
        later_triangular_record = bytearray(maximum[2])
        for name, value in (
            ("terminal_status", _STATUS_CODES["arnoldi_breakdown"]),
            (
                "termination_code",
                _TERMINATION_CODES["arnoldi_triangular_factor_breakdown"],
            ),
            ("stagnation_checkpoint_count", 0),
            ("operator_apply_count", 6),
            ("solution_update_l2", 0.25),
            ("solution_scale_l2", 1.0),
        ):
            _write_field(later_triangular_record, name, value)
        _write_field(
            later_triangular_record,
            "solution_update_l2",
            0.25,
            restart_index=0,
        )
        _write_field(
            later_triangular_record,
            "termination_hint",
            _HINT_CODES["arnoldi_triangular_factor_breakdown"],
            restart_index=1,
        )
        _write_field(later_triangular_record, "flags", 0, restart_index=1)
        _write_field(
            later_triangular_record,
            "solution_update_l2",
            0.0,
            restart_index=1,
        )
        later_triangular_result = _reseal_test_export(
            harness,
            (maximum[0], maximum[1], bytes(later_triangular_record)),
        )
        later_triangular = observe_hip_fgmres_terminal_outcome_v1(
            later_triangular_result,
            expected_export_context=harness.context,
        )
        assert later_triangular.outcome.termination_code == (
            "arnoldi_triangular_factor_breakdown"
        )
        assert later_triangular.outcome.restart_rows[-2].solution_update_l2 == 0.25
        assert later_triangular.outcome.restart_rows[-1].solution_update_l2 == 0.0
        assert later_triangular.outcome.metrics is not None
        assert later_triangular.outcome.metrics.solution_update_l2 == 0.25

        changed_triangular_record = bytearray(later_triangular_record)
        for name, value in (
            ("final_residual_l2", 0.5),
            ("final_residual_linf", 0.5),
            ("final_scaled_residual", 0.25),
        ):
            _write_field(changed_triangular_record, name, value)
        for name, value in (
            ("true_residual_l2", 0.5),
            ("true_residual_linf", 0.5),
            ("scaled_true_residual", 0.25),
        ):
            _write_field(
                changed_triangular_record,
                name,
                value,
                restart_index=1,
            )
        changed_residual = np.zeros(free_dof_count, dtype="<f8")
        changed_residual[0] = 0.5
        changed_triangular_result = _reseal_test_export(
            harness,
            (
                maximum[0],
                changed_residual.tobytes(),
                bytes(changed_triangular_record),
            ),
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as changed:
            observe_hip_fgmres_terminal_outcome_v1(
                changed_triangular_result,
                expected_export_context=harness.context,
            )
        assert changed.value.code == (
            "hip_fgmres_terminal_outcome_triangular_residual_invalid"
        )

        retained_tiny_record = bytearray(later_triangular_record)
        _write_field(retained_tiny_record, "solution_update_l2", 0.0)
        _write_field(retained_tiny_record, "solution_scale_l2", 0.0)
        _write_field(
            retained_tiny_record,
            "solution_update_l2",
            0.0,
            restart_index=0,
        )
        retained_tiny_result = _reseal_test_export(
            harness,
            (maximum[0], maximum[1], bytes(retained_tiny_record)),
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as tiny:
            observe_hip_fgmres_terminal_outcome_v1(
                retained_tiny_result,
                expected_export_context=harness.context,
            )
        assert tiny.value.code == (
            "hip_fgmres_terminal_outcome_tiny_update_flag_invalid"
        )
        cases = (
            (
                "unknown_status",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(initial[2], "terminal_status", 99),
                ),
                "hip_fgmres_terminal_outcome_status_invalid",
            ),
            (
                "unknown_termination",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(initial[2], "termination_code", 99),
                ),
                "hip_fgmres_terminal_outcome_termination_code_invalid",
            ),
            (
                "status_code_mismatch",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(
                        initial[2],
                        "terminal_status",
                        _STATUS_CODES["max_iterations"],
                    ),
                ),
                "hip_fgmres_terminal_outcome_status_code_mismatch",
            ),
            (
                "initial_metric_mismatch",
                (initial[0], initial[1], initial_metric_mismatch),
                "hip_fgmres_terminal_outcome_initial_metric_invalid",
            ),
            (
                "arnoldi_threshold_mismatch",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        true_convergence[2],
                        "arnoldi_breakdown_threshold",
                        0.0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_terminal_restart_invalid",
            ),
            (
                "nontriangular_zero_scale",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        true_convergence[2],
                        "triangular_scale",
                        0.0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_terminal_restart_invalid",
            ),
            (
                "nontriangular_zero_work",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        _mutated_field(
                            true_convergence[2],
                            "arnoldi_work_l2",
                            0.0,
                        ),
                        "arnoldi_breakdown_threshold",
                        0.0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_terminal_restart_invalid",
            ),
            (
                "uncommitted_solution_scale",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        true_convergence[2],
                        "solution_scale_l2",
                        123.0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_uncommitted_solution_scale_invalid",
            ),
            (
                "unknown_device_error_bit",
                (
                    failure[0],
                    failure[1],
                    _mutated_field(failure[2], "device_error_bits", 1 << 15),
                ),
                "hip_fgmres_terminal_outcome_device_error_bits_invalid",
            ),
            (
                "missing_device_error",
                (
                    failure[0],
                    failure[1],
                    _mutated_field(failure[2], "device_error_bits", 0),
                ),
                "hip_fgmres_terminal_outcome_device_error_status_mismatch",
            ),
            (
                "restart_row_gap",
                (maximum[0], maximum[1], bytes(row_gap)),
                "hip_fgmres_terminal_outcome_restart_rows_not_contiguous",
            ),
            (
                "reserved_header",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(initial[2], "reserved_f64_0", 1.0),
                ),
                "hip_fgmres_terminal_outcome_reserved_header_invalid",
            ),
            (
                "reserved_restart",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        true_convergence[2],
                        "reserved_i32_0",
                        1,
                        restart_index=0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_restart_reserved_invalid",
            ),
            (
                "nonfinite_metric",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(initial[2], "final_residual_l2", float("nan")),
                ),
                "hip_fgmres_terminal_outcome_metric_invalid",
            ),
            (
                "counter_relationship",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(initial[2], "effective_iterations", 5),
                ),
                "hip_fgmres_terminal_outcome_counter_relationship_invalid",
            ),
            (
                "scaled_metric",
                (
                    initial[0],
                    initial[1],
                    _mutated_field(initial[2], "final_scaled_residual", 1.0),
                ),
                "hip_fgmres_terminal_outcome_scaled_metric_invalid",
            ),
            (
                "unknown_restart_hint",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        true_convergence[2],
                        "termination_hint",
                        99,
                        restart_index=0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_restart_hint_invalid",
            ),
            (
                "restart_flags_out_of_range",
                (
                    true_convergence[0],
                    true_convergence[1],
                    _mutated_field(
                        true_convergence[2],
                        "flags",
                        256,
                        restart_index=0,
                    ),
                ),
                "hip_fgmres_terminal_outcome_restart_flags_invalid",
            ),
            (
                "payload_record_metric_mismatch",
                (maximum[0], zero_residual, maximum[2]),
                "hip_fgmres_terminal_outcome_payload_metrics_invalid",
            ),
            (
                "false_convergence_plus_replay_exceeds_effective_iterations",
                (
                    true_convergence[0],
                    true_convergence[1],
                    excessive_replay_record,
                ),
                "hip_fgmres_terminal_outcome_replay_count_invalid",
            ),
            (
                "failure_progress_dimension_not_exact",
                (
                    failure[0],
                    failure[1],
                    invalid_failure_progress,
                ),
                "hip_fgmres_terminal_outcome_failure_progress_invalid",
            ),
            (
                "pre_restart_failure_operator_overcount",
                pre_restart_operator_overcount,
                "hip_fgmres_terminal_outcome_failure_counter_invalid",
            ),
            (
                "historical_failure_solver_gate_forgery",
                (maximum[0], maximum[1], forged_history_flags),
                "hip_fgmres_terminal_outcome_failure_history_flag_invalid",
            ),
        )

        for label, payloads, expected_code in cases:
            result = _reseal_test_export(harness, payloads)
            source_manifest = result.receipt.to_dict()
            with pytest.raises(
                HipFgmresTerminalOutcomeObservationV1Error,
                match=expected_code,
            ) as failed:
                observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
            assert failed.value.code == expected_code, label
            assert result.receipt.to_dict() == source_manifest

        for termination in _NUMERICAL_FAILURES:
            termination_value = _TERMINATION_CODES[termination]
            base_payloads = _terminal_payloads(
                harness.policy,
                free_dof_count,
                termination,
            )
            disallowed_mask = _DISALLOWED_FAILURE_ERROR_MASK_BY_CODE[termination_value]
            assert (
                disallowed_mask
                not in (_ALLOWED_FAILURE_ERROR_MASKS_BY_CODE[termination_value])
            )
            payloads = (
                base_payloads[0],
                base_payloads[1],
                _mutated_field(
                    base_payloads[2],
                    "device_error_bits",
                    disallowed_mask,
                ),
            )
            result = _reseal_test_export(harness, payloads)
            with pytest.raises(
                HipFgmresTerminalOutcomeObservationV1Error
            ) as incompatible:
                observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
            assert incompatible.value.code == (
                "hip_fgmres_terminal_outcome_device_error_termination_mismatch"
            )
    finally:
        harness.close()


def test_terminal_outcome_receipt_schema_hash_and_exact_scalar_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _open_actual_export(monkeypatch)
    try:
        result = harness.template
        observed = observe_hip_fgmres_terminal_outcome_v1(
            result,
            expected_export_context=harness.context,
        )
        receipt = observed.receipt
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(receipt.to_dict())
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as missing:
            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(receipt)
        assert missing.value.code == ("hip_fgmres_terminal_outcome_provenance_required")
        validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
            receipt,
            expected_export_result=result,
            expected_export_context=harness.context,
        )

        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as bad_hash:
            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                replace(receipt, receipt_hash=_ZERO_HASH),
                expected_export_result=result,
                expected_export_context=harness.context,
            )
        assert bad_hash.value.code == (
            "hip_fgmres_terminal_outcome_receipt_hash_invalid"
        )

        stale_outcome_hash = _rehashed_observation_receipt(
            receipt,
            outcome_hash=_ZERO_HASH,
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as stale:
            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                stale_outcome_hash,
                expected_export_result=result,
                expected_export_context=harness.context,
            )
        assert stale.value.code == (
            "hip_fgmres_terminal_outcome_receipt_semantics_invalid"
        )

        bool_dimension = _rehashed_observation_receipt(
            receipt,
            dimensions=replace(receipt.dimensions, free_dof_count=True),
        )
        bool_counters = replace(
            receipt.outcome.counters,
            effective_iterations=False,
        )
        bool_outcome = replace(receipt.outcome, counters=bool_counters)
        bool_counter = _rehashed_observation_receipt(
            receipt,
            outcome=bool_outcome,
            outcome_hash=canonical_hash(bool_outcome.to_dict()),
        )
        integer_claim = _rehashed_observation_receipt(
            receipt,
            claims=replace(receipt.claims, commercial_ready=0),
        )
        integer_metric_value = replace(
            receipt.outcome.metrics,
            final_residual_l2=0,
        )
        integer_metric_outcome = replace(
            receipt.outcome,
            metrics=integer_metric_value,
        )
        integer_metric = _rehashed_observation_receipt(
            receipt,
            outcome=integer_metric_outcome,
            outcome_hash=canonical_hash(integer_metric_outcome.to_dict()),
        )
        for forged, expected_code in (
            (
                bool_dimension,
                "hip_fgmres_terminal_outcome_dimension_type_invalid",
            ),
            (bool_counter, "hip_fgmres_terminal_outcome_counter_type_invalid"),
            (integer_claim, "hip_fgmres_terminal_outcome_claim_type_invalid"),
            (integer_metric, "hip_fgmres_terminal_outcome_metric_type_invalid"),
        ):
            with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as typed:
                validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                    forged,
                    expected_export_result=result,
                    expected_export_context=harness.context,
                )
            assert typed.value.code == expected_code

        negative_zero_policy = replace(
            receipt.policy,
            absolute_tolerance=-0.0,
        )
        assert canonical_hash(negative_zero_policy.to_dict()) == (
            receipt.bindings.policy_hash
        )
        signed_zero_forgery = _rehashed_observation_receipt(
            receipt,
            policy=negative_zero_policy,
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as signed:
            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                signed_zero_forgery,
                expected_export_result=result,
                expected_export_context=harness.context,
            )
        assert signed.value.code == "hip_fgmres_terminal_outcome_policy_invalid"

        nonfinite_claim = replace(
            receipt.outcome,
            solution_x_all_finite=False,
        )
        nonfinite_claim_forgery = _rehashed_observation_receipt(
            receipt,
            outcome=nonfinite_claim,
            outcome_hash=canonical_hash(nonfinite_claim.to_dict()),
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as finite:
            nonfinite_claim_forgery.to_dict()
        assert finite.value.code == (
            "hip_fgmres_terminal_outcome_receipt_schema_invalid"
        )

        negative_zero_row = replace(
            receipt.outcome.restart_rows[0],
            estimated_residual_l2=-0.0,
        )
        negative_zero_outcome = replace(
            receipt.outcome,
            restart_rows=(
                negative_zero_row,
                *receipt.outcome.restart_rows[1:],
            ),
        )
        negative_zero_row_forgery = _rehashed_observation_receipt(
            receipt,
            outcome=negative_zero_outcome,
            outcome_hash=canonical_hash(negative_zero_outcome.to_dict()),
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as empty:
            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                negative_zero_row_forgery,
                expected_export_result=result,
                expected_export_context=harness.context,
            )
        assert empty.value.code == ("hip_fgmres_terminal_outcome_empty_restart_invalid")

        forged_dimensions = replace(
            receipt.dimensions,
            free_dof_count=receipt.dimensions.free_dof_count + 1,
            inspected_host_payload_byte_count=(
                receipt.dimensions.inspected_host_payload_byte_count + 16
            ),
        )
        wrong_backend = _rehashed_observation_receipt(
            receipt,
            actual_backend=(
                "hip" if receipt.actual_backend == "test_double" else "test_double"
            ),
        )
        wrong_dimensions = _rehashed_observation_receipt(
            receipt,
            dimensions=forged_dimensions,
            telemetry=replace(
                receipt.telemetry,
                inspected_host_payload_byte_count=(
                    receipt.telemetry.inspected_host_payload_byte_count + 16
                ),
            ),
        )
        for forged in (wrong_backend, wrong_dimensions):
            with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as bound:
                validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                    forged,
                    expected_export_result=result,
                    expected_export_context=harness.context,
                )
            assert bound.value.code == (
                "hip_fgmres_terminal_outcome_source_binding_invalid"
            )

        alternate_payloads = _terminal_payloads(
            harness.policy,
            receipt.dimensions.free_dof_count,
            "max_iterations_exhausted",
        )
        alternate_source = replace(
            result,
            solution_x=alternate_payloads[0],
            true_residual=alternate_payloads[1],
            solve_record=alternate_payloads[2],
        )
        forged_outcome = observation_module._decode_and_validate_outcome(
            alternate_source,
            policy=receipt.policy,
        )
        semantic_forgery = _rehashed_observation_receipt(
            receipt,
            status="terminal_not_converged",
            outcome=forged_outcome,
            outcome_hash=canonical_hash(forged_outcome.to_dict()),
        )
        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as replay:
            validate_hip_fgmres_terminal_outcome_observation_receipt_v1(
                semantic_forgery,
                expected_export_result=result,
                expected_export_context=harness.context,
            )
        assert replay.value.code == "hip_fgmres_terminal_outcome_replay_mismatch"
    finally:
        harness.close()


def test_terminal_outcome_requires_final_publication_expected_context_and_source_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _open_actual_export(monkeypatch)
    try:
        result = harness.template
        source_receipt = result.receipt
        source_manifest = source_receipt.to_dict()
        observed = observe_hip_fgmres_terminal_outcome_v1(
            result,
            expected_export_context=harness.context,
        )
        assert result.receipt is source_receipt
        assert result.receipt.to_dict() == source_manifest

        with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as context_type:
            observe_hip_fgmres_terminal_outcome_v1(
                result,
                expected_export_context=object(),  # type: ignore[arg-type]
            )
        assert context_type.value.code == (
            "hip_fgmres_terminal_outcome_expected_context_invalid"
        )
        assert context_type.value.path == "/expected_export_context"

        original_publication = harness.context._publication
        with harness.context._lock:
            harness.context._result = None
            harness.context._publication = result
        try:
            with pytest.raises(HipFgmresCompletionExportV1Error) as pending_only:
                observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
            assert pending_only.value.code == (
                "hip_fgmres_completion_export_final_publication_invalid"
            )
        finally:
            with harness.context._lock:
                harness.context._result = result
                harness.context._publication = original_publication

        authority_state = harness.context._published_result_authority_state
        assert authority_state is not None
        seal = authority_state[0]
        original_seal_hash = seal.receipt_hash
        object.__setattr__(seal, "receipt_hash", _ZERO_HASH)
        try:
            with pytest.raises(HipFgmresCompletionExportV1Error) as broken_seal:
                observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
            assert broken_seal.value.code == (
                "hip_fgmres_completion_export_final_publication_invalid"
            )
        finally:
            object.__setattr__(seal, "receipt_hash", original_seal_hash)

        original_authority_state = harness.context._published_result_authority_state
        assert original_authority_state is not None
        harness.context._published_result_authority_state = (seal, ())
        try:
            with pytest.raises(HipFgmresCompletionExportV1Error) as torn_seal:
                observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
            assert torn_seal.value.code == (
                "hip_fgmres_completion_export_final_publication_invalid"
            )
        finally:
            harness.context._published_result_authority_state = original_authority_state

        original_record = result.solve_record
        rebound_record = bytes(bytearray(original_record))
        assert (
            rebound_record == original_record and rebound_record is not original_record
        )
        object.__setattr__(result, "solve_record", rebound_record)
        try:
            with pytest.raises(HipFgmresCompletionExportV1Error) as rebound:
                observe_hip_fgmres_terminal_outcome_v1(
                    result,
                    expected_export_context=harness.context,
                )
            assert rebound.value.code == (
                "hip_fgmres_completion_export_final_publication_invalid"
            )
        finally:
            object.__setattr__(result, "solve_record", original_record)

        original_decode = observation_module._decode_and_validate_outcome
        original_receipt = result.receipt

        def rebind_receipt_after_decode(*args: Any, **kwargs: Any) -> Any:
            outcome = original_decode(*args, **kwargs)
            object.__setattr__(result, "receipt", replace(original_receipt))
            return outcome

        try:
            with monkeypatch.context() as race:
                race.setattr(
                    observation_module,
                    "_decode_and_validate_outcome",
                    rebind_receipt_after_decode,
                )
                with pytest.raises(
                    HipFgmresTerminalOutcomeObservationV1Error
                ) as changed_during_observation:
                    observe_hip_fgmres_terminal_outcome_v1(
                        result,
                        expected_export_context=harness.context,
                    )
            assert changed_during_observation.value.code == (
                "hip_fgmres_terminal_outcome_export_receipt_changed"
            )
        finally:
            object.__setattr__(result, "receipt", original_receipt)

        original_source = observed._source_export_result
        foreign_identity = replace(result)
        object.__setattr__(
            observed,
            "_source_export_result",
            foreign_identity,
        )
        try:
            with pytest.raises(HipFgmresTerminalOutcomeObservationV1Error) as source:
                validate_hip_fgmres_terminal_outcome_observation_result_v1(
                    observed,
                    expected_export_result=result,
                    expected_export_context=harness.context,
                )
            assert source.value.code == ("hip_fgmres_terminal_outcome_source_mismatch")
        finally:
            object.__setattr__(
                observed,
                "_source_export_result",
                original_source,
            )

        original_source_context = observed._source_export_context
        object.__setattr__(observed, "_source_export_context", object())
        try:
            with pytest.raises(
                HipFgmresTerminalOutcomeObservationV1Error
            ) as source_context:
                validate_hip_fgmres_terminal_outcome_observation_result_v1(
                    observed,
                    expected_export_result=result,
                    expected_export_context=harness.context,
                )
            assert source_context.value.code == (
                "hip_fgmres_terminal_outcome_source_context_type_invalid"
            )
        finally:
            object.__setattr__(
                observed,
                "_source_export_context",
                original_source_context,
            )

        validate_hip_fgmres_terminal_outcome_observation_result_v1(
            observed,
            expected_export_result=result,
            expected_export_context=harness.context,
        )
        assert result.receipt is source_receipt
        assert result.receipt.to_dict() == source_manifest
    finally:
        harness.close()
