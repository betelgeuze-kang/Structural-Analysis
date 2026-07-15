from __future__ import annotations

import ast
import copy
from dataclasses import replace
import hashlib
import inspect
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_diagnostic_ir_v1 as bridge_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    HipFgmresFixtureReplayV1,
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
    HipFgmresModelCaseParityResultV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    decode_hip_fgmres_detached_completion_payload_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_diagnostic_ir_v1 import (
    HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE,
    HipFgmresDiagnosticIRBridgeResultV1,
    HipFgmresDiagnosticIRV1Error,
    build_hip_fgmres_diagnostic_ir_v1,
    validate_hip_fgmres_diagnostic_ir_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.diagnostic_ir_v1 import (
    DiagnosticIRV1Claims,
    _receipt_hash,
)
from tests.test_engine_v2_hip_fgmres_external_signed_evidence_v1 import (
    _policy_snapshot,
    _terminal_payloads,
)


NONCONVERGED_SLOT_IDS = (
    "frame_single_rotated_local_axis_bending",
    "recurrence_later_restart_partial_final_cycle",
    "recurrence_exact_full_final_cycle_guard",
)


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def registry() -> Any:
    return load_hip_fgmres_fixture_registry_v1()


@pytest.fixture(scope="module")
def nonconverged_slot(registry: Any) -> HipFgmresFixtureReplayV1:
    slot = registry.slot(NONCONVERGED_SLOT_IDS[0])
    assert slot.cpu_result.status == "max_iterations"
    assert slot.cpu_result.termination_code == "max_iterations_exhausted"
    return slot


@pytest.fixture(scope="module")
def converged_slot(registry: Any) -> HipFgmresFixtureReplayV1:
    slot = registry.slot("frame_single_axial")
    assert slot.cpu_result.status == "converged"
    return slot


def _case_result() -> HipFgmresModelCaseParityResultV1:
    return object.__new__(HipFgmresModelCaseParityResultV1)


def _capture(
    slot: HipFgmresFixtureReplayV1,
    *,
    cpu_result: Any | None = None,
    source_case_identity_token: object | None = None,
) -> bridge_module._LiveAuthorityCaptureV2:
    plan = slot.execution_plan
    cpu = slot.cpu_result if cpu_result is None else cpu_result
    solution_x, true_residual, solve_record = _terminal_payloads(slot)
    policy = _policy_snapshot(slot)
    outcome = decode_hip_fgmres_detached_completion_payload_v1(
        solution_x=solution_x,
        true_residual=true_residual,
        solve_record=solve_record,
        free_dof_count=len(plan.free_dofs),
        maximum_restart_count=policy.maximum_restart_count,
        policy=policy,
    )
    solution_hash = sha256_prefixed(solution_x)
    residual_hash = sha256_prefixed(true_residual)
    record_hash = sha256_prefixed(solve_record)
    observation_id = _hash(f"terminal-observation-id:{slot.slot_id}")
    observation_hash = _hash(f"terminal-observation:{slot.slot_id}")
    outcome_hash = canonical_hash(outcome.to_dict())
    context_id = _hash(f"completion-export-context:{slot.slot_id}")
    export_receipt_hash = _hash(f"completion-export-receipt:{slot.slot_id}")
    export_payload_hash = _hash(f"completion-export-payload:{slot.slot_id}")
    source_binding_hash = _hash(f"source-binding:{slot.slot_id}")
    device_hash = _hash(f"device-identity:{slot.slot_id}")
    claims_not_ready = SimpleNamespace(result_ir_ready=False, solution_ready=False)

    bindings = SimpleNamespace(
        execution_plan_id=plan.plan_id,
        execution_plan_hash=plan.plan_hash,
        cpu_result_hash=cpu.result_hash,
        terminal_observation_id=observation_id,
        terminal_observation_receipt_hash=observation_hash,
        completion_export_context_id=context_id,
        completion_export_receipt_hash=export_receipt_hash,
        completion_export_payload_hash=export_payload_hash,
        device_identity_receipt_hash=device_hash,
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_uuid_bytes_hex="0123456789abcdef0123456789abcdef",
        device_pci_bdf="0000:03:00.0",
    )
    parity_receipt = SimpleNamespace(
        schema_version=HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
        actual_backend="hip",
        bindings=bindings,
        dimensions=SimpleNamespace(
            global_dof_count=plan.dof_count,
            free_dof_count=len(plan.free_dofs),
            maximum_restart_count=policy.maximum_restart_count,
        ),
        case_id=slot.slot_id,
        receipt_hash=_hash(f"case-parity:{slot.slot_id}"),
        claims=claims_not_ready,
    )
    observation_bindings = SimpleNamespace(
        completion_export_context_id=context_id,
        completion_export_source_binding_hash=source_binding_hash,
        solution_payload_sha256=solution_hash,
        true_residual_payload_sha256=residual_hash,
        solve_record_payload_sha256=record_hash,
    )
    observation_receipt = SimpleNamespace(
        actual_backend="hip",
        status=(
            "terminal_not_converged"
            if outcome.outcome_class == "not_converged"
            else "terminal_converged"
        ),
        observation_id=observation_id,
        policy=policy,
        outcome=outcome,
        outcome_hash=outcome_hash,
        receipt_hash=observation_hash,
        bindings=observation_bindings,
        claims=claims_not_ready,
    )
    observation_result = SimpleNamespace(receipt=observation_receipt)
    device_receipt = SimpleNamespace(
        actual_backend="hip",
        receipt_hash=device_hash,
        architecture=SimpleNamespace(
            expected_compiled=SimpleNamespace(normalized="gfx1030"),
            runtime=SimpleNamespace(base="gfx1030"),
        ),
        device=SimpleNamespace(
            selected_ordinal=0,
            uuid_bytes_hex="0123456789abcdef0123456789abcdef",
            pci_bdf="0000:03:00.0",
        ),
    )
    export_receipt = SimpleNamespace(
        actual_backend="hip",
        receipt_hash=export_receipt_hash,
        payload_hash=export_payload_hash,
        bindings=SimpleNamespace(source_binding_hash=source_binding_hash),
        dimensions=SimpleNamespace(
            free_dof_count=len(plan.free_dofs),
            solution_byte_count=len(solution_x),
            true_residual_byte_count=len(true_residual),
            solve_record_byte_count=len(solve_record),
        ),
        buffers=(
            SimpleNamespace(role="solution_x", payload_sha256=solution_hash),
            SimpleNamespace(role="true_residual", payload_sha256=residual_hash),
            SimpleNamespace(role="solve_record", payload_sha256=record_hash),
        ),
        claims=claims_not_ready,
    )
    export_result = SimpleNamespace(
        receipt=export_receipt,
        payload_hash=export_payload_hash,
        solve_record=solve_record,
    )
    published = SimpleNamespace(
        solution_x=solution_x,
        true_residual=true_residual,
        solve_record=solve_record,
        receipt_hash=export_receipt_hash,
        payload_hash=export_payload_hash,
        buffer_payload_hashes=(solution_hash, residual_hash, record_hash),
    )
    return bridge_module._LiveAuthorityCaptureV2(
        authority=SimpleNamespace(snapshot=("controlled-live-authority",)),
        source_case_identity_token=(
            object()
            if source_case_identity_token is None
            else source_case_identity_token
        ),
        receipt=parity_receipt,
        plan=plan,
        cpu_result=cpu,
        observation_result=observation_result,
        device_identity_result=SimpleNamespace(receipt=device_receipt),
        export_result=export_result,
        publication_authority=object(),
        published_result=published,
        solution_x=solution_x,
        true_residual=true_residual,
        authority_snapshot_hash=_hash(f"authority-snapshot:{slot.slot_id}"),
    )


def _install_capture(
    monkeypatch: pytest.MonkeyPatch,
    capture: bridge_module._LiveAuthorityCaptureV2,
) -> None:
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda _case: capture,
    )


def _build(
    monkeypatch: pytest.MonkeyPatch,
    slot: HipFgmresFixtureReplayV1,
) -> tuple[
    bridge_module._LiveAuthorityCaptureV2,
    HipFgmresDiagnosticIRBridgeResultV1,
]:
    capture = _capture(slot)
    _install_capture(monkeypatch, capture)
    return capture, build_hip_fgmres_diagnostic_ir_v1(_case_result())


def test_bridge_materializes_raw_max_iterations_as_rolled_back_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    nonconverged_slot: HipFgmresFixtureReplayV1,
) -> None:
    capture, result = _build(monkeypatch, nonconverged_slot)
    assert validate_hip_fgmres_diagnostic_ir_v1(result) is result
    assert result.diagnostic_ir is result.receipt
    assert result.source_execution_plan is nonconverged_slot.execution_plan
    assert HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE == (
        "hip_fgmres_retained_max_iterations_diagnostic_ir_v1"
    )

    seal = result._source_seal
    assert seal.solution_x == capture.solution_x
    assert seal.true_residual == capture.true_residual
    assert seal.solve_record is not capture.export_result.solve_record
    assert seal.solve_record == capture.export_result.solve_record
    assert sha256_prefixed(seal.solution_x) == seal.solution_payload_sha256
    assert sha256_prefixed(seal.true_residual) == (seal.true_residual_payload_sha256)
    assert sha256_prefixed(seal.solve_record) == seal.solve_record_payload_sha256

    plan = nonconverged_slot.execution_plan
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    displacement = result.receipt.arrays.partial_displacement_si.values.reshape(-1)
    np.testing.assert_array_equal(
        displacement[free], np.frombuffer(capture.solution_x, dtype="<f8")
    )
    np.testing.assert_array_equal(displacement[constrained], 0.0)
    np.testing.assert_array_equal(
        result.receipt.arrays.residual_si.values.reshape(-1),
        plan.residual(displacement),
    )
    np.testing.assert_array_equal(
        result.receipt.arrays.exported_free_residual_si.values.reshape(-1),
        np.frombuffer(capture.true_residual, dtype="<f8"),
    )

    assert result.accepted_state.role == "committed"
    assert result.accepted_state.epoch == 0
    assert result.evaluated_trial_state.role == "trial"
    assert result.evaluated_trial_state.parent_state_hash == (
        result.accepted_state.state_hash
    )
    assert result.rollback_state is result.accepted_state
    assert not hasattr(result, "committed_state")
    assert result.receipt.termination.status == "max_iterations"
    assert result.receipt.termination.termination_code == ("max_iterations_exhausted")
    assert result.receipt.claims.committed_state_created is False
    assert result.receipt.claims.solution_ready is False
    assert result.receipt.claims.result_ir_ready is False

    provenance = result.receipt.source_provenance
    assert provenance.solution_payload_sha256 == sha256_prefixed(capture.solution_x)
    assert provenance.exported_free_residual_payload_sha256 == sha256_prefixed(
        capture.true_residual
    )
    assert provenance.solve_record_payload_sha256 == sha256_prefixed(
        capture.export_result.solve_record
    )
    assert provenance.case_parity_receipt_hash == capture.receipt.receipt_hash
    assert provenance.additional_device_operation_count == 0
    assert provenance.additional_d2h_operation_count == 0
    assert provenance.additional_solve_count == 0
    assert provenance.additional_export_count == 0
    assert provenance.fallback_count == 0

    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda _case: (_ for _ in ()).throw(AssertionError("live replay forbidden")),
    )
    assert validate_hip_fgmres_diagnostic_ir_v1(result) is result
    assert result.to_manifest() == result.receipt.to_manifest()


@pytest.mark.parametrize("slot_id", NONCONVERGED_SLOT_IDS)
def test_each_registered_max_iterations_slot_is_diagnostic_ready(
    monkeypatch: pytest.MonkeyPatch,
    registry: Any,
    slot_id: str,
) -> None:
    slot = registry.slot(slot_id)
    _, result = _build(monkeypatch, slot)
    assert result.receipt.termination.counters.iteration_count == (
        slot.cpu_result.policy.max_iterations
    )
    assert result.rollback_state is result.accepted_state
    assert validate_hip_fgmres_diagnostic_ir_v1(result) is result


@pytest.mark.parametrize("source_kind", ("converged", "different_failure"))
def test_bridge_rejects_converged_and_non_exact_failure_sources(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
    nonconverged_slot: HipFgmresFixtureReplayV1,
    source_kind: str,
) -> None:
    if source_kind == "converged":
        capture = _capture(converged_slot)
    else:
        changed_cpu = replace(
            nonconverged_slot.cpu_result,
            status="stagnated",
            termination_code="true_residual_stagnated",
        )
        capture = _capture(nonconverged_slot, cpu_result=changed_cpu)
    _install_capture(monkeypatch, capture)
    with pytest.raises(HipFgmresDiagnosticIRV1Error) as error:
        build_hip_fgmres_diagnostic_ir_v1(_case_result())
    assert error.value.code == "hip_fgmres_diagnostic_ir_v1_cpu_status_invalid"


def test_bridge_publishes_nothing_if_live_authority_changes(
    monkeypatch: pytest.MonkeyPatch,
    nonconverged_slot: HipFgmresFixtureReplayV1,
) -> None:
    first = _capture(nonconverged_slot)
    second = replace(first, authority=object())
    captures = iter((first, second))
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda _case: next(captures),
    )
    seal_called = False

    def forbidden_seal(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal seal_called
        seal_called = True
        raise AssertionError("changed live authority must not publish")

    monkeypatch.setattr(bridge_module, "_make_detached_seal", forbidden_seal)
    with pytest.raises(HipFgmresDiagnosticIRV1Error) as error:
        build_hip_fgmres_diagnostic_ir_v1(_case_result())
    assert error.value.code == "hip_fgmres_diagnostic_ir_v1_live_authority_changed"
    assert seal_called is False


def test_private_live_case_binding_uses_non_recycled_identity_token(
    monkeypatch: pytest.MonkeyPatch,
    nonconverged_slot: HipFgmresFixtureReplayV1,
) -> None:
    case = _case_result()
    capture = _capture(nonconverged_slot)
    _install_capture(monkeypatch, capture)
    result = build_hip_fgmres_diagnostic_ir_v1(case)
    assert (
        bridge_module._validate_hip_fgmres_diagnostic_ir_v1_against_live_case(
            result, case
        )
        is result
    )

    other_run = replace(capture, source_case_identity_token=object())
    _install_capture(monkeypatch, other_run)
    with pytest.raises(HipFgmresDiagnosticIRV1Error) as error:
        bridge_module._validate_hip_fgmres_diagnostic_ir_v1_against_live_case(
            result, case
        )
    assert error.value.code == (
        "hip_fgmres_diagnostic_ir_v1_live_case_identity_mismatch"
    )


@pytest.mark.parametrize("field", ("solution_x", "true_residual", "solve_record"))
def test_detached_validator_rejects_each_raw_payload_tamper(
    monkeypatch: pytest.MonkeyPatch,
    nonconverged_slot: HipFgmresFixtureReplayV1,
    field: str,
) -> None:
    _, result = _build(monkeypatch, nonconverged_slot)
    payload = getattr(result._source_seal, field)
    tampered = bytes([payload[0] ^ 1]) + payload[1:]
    forged = replace(
        result,
        _source_seal=replace(result._source_seal, **{field: tampered}),
    )
    with pytest.raises(HipFgmresDiagnosticIRV1Error):
        validate_hip_fgmres_diagnostic_ir_v1(forged)


def test_exact_clone_and_cross_result_issuance_transplant_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    nonconverged_slot: HipFgmresFixtureReplayV1,
) -> None:
    _, first = _build(monkeypatch, nonconverged_slot)
    direct = HipFgmresDiagnosticIRBridgeResultV1(
        receipt=first.receipt,
        accepted_state=first.accepted_state,
        evaluated_trial_state=first.evaluated_trial_state,
        rollback_state=first.rollback_state,
        _source_execution_plan=first.source_execution_plan,
        _source_seal=first._source_seal,
    )
    for clone in (direct, replace(first), copy.copy(first)):
        with pytest.raises(HipFgmresDiagnosticIRV1Error) as clone_error:
            validate_hip_fgmres_diagnostic_ir_v1(clone)
        assert clone_error.value.code == (
            "hip_fgmres_diagnostic_ir_v1_issuance_unavailable"
        )
    with pytest.raises(TypeError, match="mappingproxy"):
        copy.deepcopy(first)

    attacker_case_hash = _hash("attacker-case-parity")
    attacker_device_hash = _hash("attacker-device-identity")
    provenance = replace(
        first.receipt.source_provenance,
        case_parity_receipt_hash=attacker_case_hash,
        device_identity_receipt_hash=attacker_device_hash,
        device_uuid_bytes_hex="fedcba9876543210fedcba9876543210",
    )
    receipt = replace(
        first.receipt,
        source_provenance=provenance,
        claims=DiagnosticIRV1Claims(),
        diagnostic_ir_hash=bridge_module._ZERO_HASH,
    )
    receipt = replace(receipt, diagnostic_ir_hash=_receipt_hash(receipt.to_dict()))
    seal = replace(
        first._source_seal,
        case_parity_receipt_hash=attacker_case_hash,
        device_identity_receipt_hash=attacker_device_hash,
        source_provenance=provenance,
        diagnostic_ir_hash=receipt.diagnostic_ir_hash,
        capture_hash=bridge_module._ZERO_HASH,
    )
    seal = replace(
        seal,
        capture_hash=canonical_hash(bridge_module._detached_seal_payload(seal)),
    )
    coherently_rehashed = replace(first, receipt=receipt, _source_seal=seal)
    with pytest.raises(HipFgmresDiagnosticIRV1Error) as coherent_error:
        validate_hip_fgmres_diagnostic_ir_v1(coherently_rehashed)
    assert coherent_error.value.code == (
        "hip_fgmres_diagnostic_ir_v1_issuance_unavailable"
    )

    _, second = _build(monkeypatch, nonconverged_slot)
    with bridge_module._DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK:
        first_issuance = bridge_module._DIAGNOSTIC_BRIDGE_ISSUANCES[first]
        second_issuance = bridge_module._DIAGNOSTIC_BRIDGE_ISSUANCES[second]
        bridge_module._DIAGNOSTIC_BRIDGE_ISSUANCES[second] = first_issuance
    try:
        with pytest.raises(HipFgmresDiagnosticIRV1Error) as transplant_error:
            validate_hip_fgmres_diagnostic_ir_v1(second)
        assert transplant_error.value.code == (
            "hip_fgmres_diagnostic_ir_v1_issuance_binding_mismatch"
        )
    finally:
        with bridge_module._DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK:
            bridge_module._DIAGNOSTIC_BRIDGE_ISSUANCES[second] = second_issuance


def test_factory_ast_has_no_solve_export_device_d2h_or_commit_call() -> None:
    factory_tree = ast.parse(inspect.getsource(build_hip_fgmres_diagnostic_ir_v1))
    calls = {
        node.func.id
        for node in ast.walk(factory_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    calls.update(
        node.func.attr
        for node in ast.walk(factory_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    )
    assert not any(
        token in call.lower()
        for call in calls
        for token in ("solve", "export", "device", "d2h", "commit_trial_state")
    )

    module_tree = ast.parse(inspect.getsource(bridge_module))
    imported_names = {
        alias.name
        for node in ast.walk(module_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "commit_trial_state" not in imported_names
    assert not any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "commit_trial_state")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "commit_trial_state"
            )
        )
        for node in ast.walk(module_tree)
    )
