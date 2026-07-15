from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import gc
import hashlib
import inspect
from types import SimpleNamespace
from typing import Any, Callable
import weakref

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_result_ir_v2 as bridge_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    HipFgmresFixtureReplayV1,
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityResultV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v2 import (
    HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE,
    HipFgmresResultIRBridgeResultV2,
    HipFgmresResultIRV2Error,
    build_hip_fgmres_result_ir_v2,
    validate_hip_fgmres_result_ir_v2,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.result_ir_v2 import _receipt_hash
from structural_analysis.engine_v2.contracts import result_ir_v2 as result_ir_module
from structural_analysis.engine_v2.contracts.state_ir import (
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def converged_slot() -> HipFgmresFixtureReplayV1:
    slot = load_hip_fgmres_fixture_registry_v1().slot("frame_single_axial")
    assert slot.cpu_result.status == "converged"
    assert slot.cpu_result.solver_tolerance_passed
    assert slot.cpu_result.authoritative_plan_tolerance_passed
    return slot


def _case_result() -> HipFgmresModelCaseParityResultV1:
    # The live authority getter itself is replaced by the controlled capture
    # below. Keeping the exact public type still exercises the caller boundary.
    return object.__new__(HipFgmresModelCaseParityResultV1)


def _capture(
    slot: HipFgmresFixtureReplayV1,
    *,
    negative_zero_solution: bool = False,
    cpu_result: Any | None = None,
) -> bridge_module._LiveAuthorityCaptureV2:
    plan = slot.execution_plan
    cpu = slot.cpu_result if cpu_result is None else cpu_result
    solution = np.asarray(slot.cpu_result.reduced_solution, dtype="<f8").copy()
    if negative_zero_solution:
        zero_indices = np.flatnonzero(solution == 0.0)
        assert zero_indices.size
        solution[int(zero_indices[0])] = -0.0
    solution_x = solution.tobytes(order="C")
    true_residual = np.asarray(slot.cpu_result.true_residual, dtype="<f8").tobytes(
        order="C"
    )
    solution_hash = sha256_prefixed(solution_x)
    residual_hash = sha256_prefixed(true_residual)
    terminal_hash = _hash("terminal-observation")
    export_receipt_hash = _hash("completion-export-receipt")
    export_payload_hash = _hash("completion-export-payload")
    device_hash = _hash("device-identity")
    claims_not_ready = SimpleNamespace(result_ir_ready=False, solution_ready=False)

    bindings = SimpleNamespace(
        execution_plan_id=plan.plan_id,
        execution_plan_hash=plan.plan_hash,
        cpu_result_hash=cpu.result_hash,
        terminal_observation_receipt_hash=terminal_hash,
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
        actual_backend="hip",
        bindings=bindings,
        dimensions=SimpleNamespace(
            global_dof_count=plan.dof_count,
            free_dof_count=len(plan.free_dofs),
        ),
        case_id=slot.slot_id,
        receipt_hash=_hash("case-parity"),
        claims=claims_not_ready,
    )
    observation_receipt = SimpleNamespace(
        actual_backend="hip",
        status="terminal_converged",
        outcome=SimpleNamespace(terminal_status="converged"),
        receipt_hash=terminal_hash,
        bindings=SimpleNamespace(
            solution_payload_sha256=solution_hash,
            true_residual_payload_sha256=residual_hash,
        ),
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
    device_result = SimpleNamespace(receipt=device_receipt)
    export_receipt = SimpleNamespace(
        actual_backend="hip",
        receipt_hash=export_receipt_hash,
        payload_hash=export_payload_hash,
        dimensions=SimpleNamespace(
            free_dof_count=len(plan.free_dofs),
            solution_byte_count=len(solution_x),
            true_residual_byte_count=len(true_residual),
        ),
        buffers=(
            SimpleNamespace(role="solution_x", payload_sha256=solution_hash),
            SimpleNamespace(role="true_residual", payload_sha256=residual_hash),
            SimpleNamespace(role="solve_record", payload_sha256=_hash("solve-record")),
        ),
        claims=claims_not_ready,
    )
    export_result = SimpleNamespace(
        receipt=export_receipt,
        payload_hash=export_payload_hash,
    )
    published = SimpleNamespace(
        solution_x=solution_x,
        true_residual=true_residual,
        receipt_hash=export_receipt_hash,
        payload_hash=export_payload_hash,
        buffer_payload_hashes=(solution_hash, residual_hash, _hash("solve-record")),
    )
    return bridge_module._LiveAuthorityCaptureV2(
        authority=SimpleNamespace(snapshot=("controlled-live-authority",)),  # type: ignore[arg-type]
        source_case_identity_token=object(),
        receipt=parity_receipt,  # type: ignore[arg-type]
        plan=plan,
        cpu_result=cpu,
        observation_result=observation_result,  # type: ignore[arg-type]
        device_identity_result=device_result,  # type: ignore[arg-type]
        export_result=export_result,  # type: ignore[arg-type]
        publication_authority=object(),  # type: ignore[arg-type]
        published_result=published,  # type: ignore[arg-type]
        solution_x=solution_x,
        true_residual=true_residual,
        authority_snapshot_hash=_hash("authority-snapshot"),
    )


def _install_capture(
    monkeypatch: pytest.MonkeyPatch,
    capture: bridge_module._LiveAuthorityCaptureV2,
) -> None:
    monkeypatch.setattr(bridge_module, "_capture_live_authority", lambda _case: capture)


def _build(
    monkeypatch: pytest.MonkeyPatch,
    slot: HipFgmresFixtureReplayV1,
    *,
    negative_zero_solution: bool = False,
) -> tuple[
    bridge_module._LiveAuthorityCaptureV2,
    HipFgmresResultIRBridgeResultV2,
]:
    capture = _capture(slot, negative_zero_solution=negative_zero_solution)
    _install_capture(monkeypatch, capture)
    result = build_hip_fgmres_result_ir_v2(_case_result())
    return capture, result


def test_bridge_preserves_raw_hip_solution_and_recovers_detached_result_ir(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    capture, result = _build(
        monkeypatch,
        converged_slot,
        negative_zero_solution=True,
    )
    assert validate_hip_fgmres_result_ir_v2(result) is result
    assert result.result_ir is result.receipt
    assert result.source_execution_plan is converged_slot.execution_plan
    assert result.receipt.capability_profile == (
        "hip_fgmres_sparse_plan_recovery_linear_static"
    )
    assert HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE == (
        "hip_fgmres_retained_completion_sparse_result_ir_v2"
    )

    plan = converged_slot.execution_plan
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    constrained = np.asarray(plan.constrained_dofs, dtype=np.int64)
    raw_solution = np.frombuffer(capture.solution_x, dtype="<f8")
    assert np.any(np.signbit(raw_solution[raw_solution == 0.0]))
    assert result._source_seal.solution_x == capture.solution_x
    assert result._source_seal.true_residual == capture.true_residual
    with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
        issuance = bridge_module._BRIDGE_RESULT_ISSUANCES[result]
    assert (
        issuance.source_case_identity_token
        is result._source_seal._source_case_identity_token
        is capture.source_case_identity_token
    )
    assert not hasattr(issuance, "source_case_result_identity")
    assert not hasattr(issuance, "source_authority_identity")
    displacement = result.receipt.arrays.displacements_si.values.reshape(-1)
    normalized_solution = raw_solution.copy()
    normalized_solution[normalized_solution == 0.0] = 0.0
    np.testing.assert_array_equal(displacement[free], normalized_solution)
    assert not np.any(np.signbit(displacement[free][displacement[free] == 0.0]))
    assert not np.any(displacement[constrained])
    assert not np.any(np.signbit(displacement[constrained]))

    residual = result.receipt.arrays.residual_si.values.reshape(-1)
    reactions = result.receipt.arrays.reactions_si.values.reshape(-1)
    np.testing.assert_allclose(
        residual, plan.residual(displacement), rtol=0.0, atol=0.0
    )
    np.testing.assert_array_equal(reactions[free], np.zeros(free.size))
    np.testing.assert_allclose(
        reactions[constrained], residual[constrained], rtol=0.0, atol=0.0
    )
    np.testing.assert_allclose(
        result.receipt.arrays.exported_free_residual_si.values,
        np.frombuffer(capture.true_residual, dtype="<f8"),
        rtol=0.0,
        atol=0.0,
    )
    assert result.receipt.arrays.element_end_forces_local_si.shape == (
        plan.element_count,
        2,
        6,
    )
    assert result.receipt.arrays.element_strain_energy_j.shape == (plan.element_count,)
    assert result.receipt.energy.total_strain_energy_j == pytest.approx(
        float(np.sum(result.receipt.arrays.element_strain_energy_j.values))
    )

    assert result.accepted_state.role == "committed"
    assert result.accepted_state.epoch == 0
    assert result.evaluated_trial_state.role == "trial"
    assert result.evaluated_trial_state.parent_state_hash == (
        result.accepted_state.state_hash
    )
    assert result.committed_state.role == "committed"
    assert result.committed_state.parent_state_hash == (
        result.evaluated_trial_state.state_hash
    )
    assert result.evaluated_trial_state.iteration == (
        converged_slot.cpu_result.iteration_count
    )

    provenance = result.receipt.source_provenance
    assert provenance.solution_payload_sha256 == sha256_prefixed(capture.solution_x)
    assert provenance.exported_free_residual_payload_sha256 == sha256_prefixed(
        capture.true_residual
    )
    assert provenance.case_parity_receipt_hash == capture.receipt.receipt_hash
    assert provenance.additional_device_operation_count == 0
    assert provenance.additional_d2h_operation_count == 0
    assert provenance.additional_solve_count == 0
    assert provenance.additional_export_count == 0
    assert provenance.fallback_count == 0

    assert capture.receipt.claims.result_ir_ready is False
    assert capture.observation_result.receipt.claims.result_ir_ready is False
    assert capture.export_result.receipt.claims.result_ir_ready is False
    assert result.receipt.claims.result_ir_verified is True
    assert result.receipt.claims.result_ir_ready is True
    assert result.receipt.claims.commercial_ready is False
    assert result.receipt.claims.promotion_eligible is False

    # Detached validation cannot consult the monkeypatched live capture again.
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda _case: (_ for _ in ()).throw(AssertionError("live replay forbidden")),
    )
    assert validate_hip_fgmres_result_ir_v2(result) is result
    assert result.to_manifest() == result.receipt.to_manifest()


def test_bridge_rejects_nonconverged_cpu_source_before_recovery(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    nonconverged = replace(
        converged_slot.cpu_result,
        status="max_iterations",
        solver_tolerance_passed=False,
        authoritative_plan_tolerance_passed=False,
    )
    capture = _capture(converged_slot, cpu_result=nonconverged)
    _install_capture(monkeypatch, capture)
    with pytest.raises(HipFgmresResultIRV2Error) as error:
        build_hip_fgmres_result_ir_v2(_case_result())
    assert error.value.code == "hip_fgmres_result_ir_v2_cpu_not_converged"


def test_bridge_rejects_noncanonical_warm_start(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    capture = _capture(converged_slot)
    _install_capture(monkeypatch, capture)
    plan = converged_slot.execution_plan
    initial = create_initial_state(plan)
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[plan.free_dofs[0]] = np.nextafter(0.0, 1.0)
    trial = open_trial_state(initial, displacement, expected_plan=plan)
    warm = commit_trial_state(initial, trial, expected_plan=plan)

    with pytest.raises(HipFgmresResultIRV2Error) as error:
        build_hip_fgmres_result_ir_v2(_case_result(), accepted_state=warm)
    assert error.value.code == "hip_fgmres_result_ir_v2_warm_start_unsupported"


def test_bridge_publishes_nothing_if_live_authority_changes_during_recovery(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    first = _capture(converged_slot)
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
        raise AssertionError("a changed live source must not publish a detached seal")

    monkeypatch.setattr(bridge_module, "_make_detached_seal", forbidden_seal)
    with pytest.raises(HipFgmresResultIRV2Error) as error:
        build_hip_fgmres_result_ir_v2(_case_result())
    assert error.value.code == "hip_fgmres_result_ir_v2_live_authority_changed"
    assert seal_called is False


def test_live_case_binding_uses_non_recycled_identity_token(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    case = _case_result()
    capture = _capture(converged_slot)
    _install_capture(monkeypatch, capture)
    result = build_hip_fgmres_result_ir_v2(case)
    assert (
        result._source_seal._source_case_identity_token
        is capture.source_case_identity_token
    )
    assert (
        bridge_module._validate_hip_fgmres_result_ir_v2_against_live_case(
            result,
            case,
        )
        is result
    )

    serially_identical_other_case = replace(
        capture,
        source_case_identity_token=object(),
    )
    _install_capture(monkeypatch, serially_identical_other_case)
    with pytest.raises(HipFgmresResultIRV2Error) as error:
        bridge_module._validate_hip_fgmres_result_ir_v2_against_live_case(
            result,
            case,
        )
    assert error.value.code == "hip_fgmres_result_ir_v2_live_case_identity_mismatch"


@pytest.mark.parametrize(
    ("forge", "expected_code"),
    (
        (
            lambda result: replace(
                result,
                _source_seal=replace(
                    result._source_seal,
                    solution_x=(
                        bytes([result._source_seal.solution_x[0] ^ 1])
                        + result._source_seal.solution_x[1:]
                    ),
                ),
            ),
            "hip_fgmres_result_ir_v2_detached_payload_invalid",
        ),
        (
            lambda result: replace(
                result,
                _source_seal=replace(
                    result._source_seal,
                    capture_hash=_hash("forged-capture"),
                ),
            ),
            "hip_fgmres_result_ir_v2_source_seal_hash_mismatch",
        ),
        (
            lambda result: replace(
                result,
                receipt=replace(result.receipt, result_ir_hash=_hash("forged-result")),
            ),
            "hip_fgmres_result_ir_v2_detached_provenance_mismatch",
        ),
    ),
    ids=("raw_payload", "seal", "result"),
)
def test_detached_validator_rejects_raw_seal_and_result_tampering(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
    forge: Callable[[HipFgmresResultIRBridgeResultV2], HipFgmresResultIRBridgeResultV2],
    expected_code: str,
) -> None:
    _, result = _build(monkeypatch, converged_slot)
    forged = forge(result)
    with pytest.raises(HipFgmresResultIRV2Error) as error:
        validate_hip_fgmres_result_ir_v2(forged)
    assert error.value.code == expected_code


def test_factory_issuance_rejects_direct_replace_copy_and_coherent_rehash(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    _, result = _build(monkeypatch, converged_slot)

    direct = HipFgmresResultIRBridgeResultV2(
        receipt=result.receipt,
        accepted_state=result.accepted_state,
        evaluated_trial_state=result.evaluated_trial_state,
        committed_state=result.committed_state,
        _source_execution_plan=result.source_execution_plan,
        _source_seal=result._source_seal,
    )
    candidates = (direct, replace(result), copy.copy(result))
    for candidate in candidates:
        with pytest.raises(HipFgmresResultIRV2Error) as error:
            validate_hip_fgmres_result_ir_v2(candidate)
        assert error.value.code == "hip_fgmres_result_ir_v2_issuance_unavailable"
    with pytest.raises(TypeError, match="mappingproxy"):
        copy.deepcopy(result)

    attacker_case_hash = _hash("attacker-case-parity")
    attacker_device_hash = _hash("attacker-device-identity")
    provenance = replace(
        result.receipt.source_provenance,
        case_parity_receipt_hash=attacker_case_hash,
        device_identity_receipt_hash=attacker_device_hash,
        device_uuid_bytes_hex="fedcba9876543210fedcba9876543210",
    )
    receipt = replace(
        result.receipt,
        source_provenance=provenance,
        result_ir_hash="sha256:" + "0" * 64,
    )
    receipt = replace(receipt, result_ir_hash=_receipt_hash(receipt.to_dict()))
    seal = replace(
        result._source_seal,
        case_parity_receipt_hash=attacker_case_hash,
        device_identity_receipt_hash=attacker_device_hash,
        source_provenance=provenance,
        result_ir_hash=receipt.result_ir_hash,
        capture_hash="sha256:" + "0" * 64,
    )
    seal = replace(
        seal,
        capture_hash=canonical_hash(bridge_module._detached_seal_payload(seal)),
    )
    coherently_rehashed = replace(result, receipt=receipt, _source_seal=seal)
    with pytest.raises(HipFgmresResultIRV2Error) as error:
        validate_hip_fgmres_result_ir_v2(coherently_rehashed)
    assert error.value.code == "hip_fgmres_result_ir_v2_detached_replay_invalid"


def test_factory_issuance_registry_is_thread_safe_weak_and_post_close_stable(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    def exercise_issued_result() -> tuple[weakref.ReferenceType[Any], int]:
        _, result = _build(monkeypatch, converged_slot)
        with ThreadPoolExecutor(max_workers=8) as executor:
            validated = tuple(
                executor.map(validate_hip_fgmres_result_ir_v2, (result,) * 32)
            )
        assert all(candidate is result for candidate in validated)
        return weakref.ref(result), len(bridge_module._BRIDGE_RESULT_ISSUANCES)

    reference, during = exercise_issued_result()
    gc.collect()
    assert reference() is None
    assert len(bridge_module._BRIDGE_RESULT_ISSUANCES) < during


def test_final_issuance_rejects_exact_clone_and_coherently_rehashed_clone(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    _, result = _build(monkeypatch, converged_slot)

    exact_clone = replace(result)
    with pytest.raises(HipFgmresResultIRV2Error) as exact_error:
        validate_hip_fgmres_result_ir_v2(exact_clone)
    assert exact_error.value.code == "hip_fgmres_result_ir_v2_issuance_unavailable"

    forged_receipt = replace(
        result.receipt,
        result_id="Result.coherently-rehashed-clone.v2",
        result_ir_hash=bridge_module._ZERO_HASH,
    )
    forged_receipt = replace(
        forged_receipt,
        result_ir_hash=result_ir_module._receipt_hash(forged_receipt.to_dict()),
    )
    seal_draft = replace(
        result._source_seal,
        result_ir_hash=forged_receipt.result_ir_hash,
        capture_hash=bridge_module._ZERO_HASH,
    )
    forged_seal = replace(
        seal_draft,
        capture_hash=bridge_module.canonical_hash(
            bridge_module._detached_seal_payload(seal_draft)
        ),
    )
    coherent_clone = replace(
        result,
        receipt=forged_receipt,
        _source_seal=forged_seal,
    )
    with pytest.raises(HipFgmresResultIRV2Error) as coherent_error:
        validate_hip_fgmres_result_ir_v2(coherent_clone)
    assert (
        coherent_error.value.code == "hip_fgmres_result_ir_v2_detached_replay_invalid"
    )


def test_final_issuance_rejects_cross_result_registry_transplant(
    monkeypatch: pytest.MonkeyPatch,
    converged_slot: HipFgmresFixtureReplayV1,
) -> None:
    _, first = _build(monkeypatch, converged_slot)
    _, second = _build(monkeypatch, converged_slot)
    with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
        first_issuance = bridge_module._BRIDGE_RESULT_ISSUANCES[first]
        second_issuance = bridge_module._BRIDGE_RESULT_ISSUANCES[second]
        bridge_module._BRIDGE_RESULT_ISSUANCES[second] = first_issuance
    try:
        with pytest.raises(HipFgmresResultIRV2Error) as error:
            validate_hip_fgmres_result_ir_v2(second)
        assert error.value.code == ("hip_fgmres_result_ir_v2_issuance_binding_mismatch")
    finally:
        with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
            bridge_module._BRIDGE_RESULT_ISSUANCES[second] = second_issuance


def test_bridge_factory_ast_has_no_solver_export_or_device_operation_call() -> None:
    tree = ast.parse(inspect.getsource(build_hip_fgmres_result_ir_v2))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    calls.update(
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    )
    forbidden = {
        "solve_cpu_fgmres_reference_v1",
        "solve_sparse_execution_plan_v2",
        "solve_linear_static",
        "export_completion_buffers",
        "enqueue",
        "fence",
        "synchronize",
        "launch",
        "allocate",
        "hipMalloc",
        "hipMemcpy",
    }
    assert forbidden.isdisjoint(calls)
    assert {call for call in calls if "native" in call.lower()} == {
        "_require_converged_native_source"
    }
    assert not any(
        token in call.lower()
        for call in calls
        for token in ("enqueue", "fence", "device_launch", "device_alloc")
    )
