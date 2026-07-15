from __future__ import annotations

import copy
from dataclasses import replace
import gc
from types import SimpleNamespace
import weakref

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_model_family_v1 as family_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_fixture_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_fixture_registry_v1 import (
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_model_family_v1 import (
    HipFgmresAllConvergedModelFamilyV1Error,
    attest_hip_fgmres_all_converged_model_family_v1,
    validate_hip_fgmres_all_converged_model_family_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityResultV1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


@pytest.fixture(scope="module")
def registry():
    return load_hip_fgmres_all_converged_fixture_registry_v1()


def _controlled_cases(monkeypatch: pytest.MonkeyPatch, registry):
    captures = {}
    cases = []
    for index, slot in enumerate(registry.slots):
        bindings = SimpleNamespace(
            model_ir_content_hash=slot.model.content_hash,
            execution_plan_hash=slot.execution_plan.plan_hash,
            fgmres_plan_hash=slot.fgmres_plan.plan_hash,
            recurrence_plan_hash=slot.recurrence_plan.plan_hash,
            policy_hash=slot.policy.policy_hash,
            cpu_result_hash=slot.cpu_result.result_hash,
            terminal_observation_receipt_hash=canonical_hash(
                {"terminal": slot.slot_id}
            ),
            completion_export_context_id=f"ExportContext.{index}",
            completion_export_receipt_hash=canonical_hash(
                {"export_receipt": slot.slot_id}
            ),
            completion_export_payload_hash=canonical_hash(
                {"export_payload": slot.slot_id}
            ),
            device_identity_receipt_hash=canonical_hash(
                {"device": "controlled-gfx1030"}
            ),
            kernel_identity_hash=canonical_hash({"kernel": "controlled"}),
            kernel_source_sha256=canonical_hash({"kernel_source": "controlled"}),
            runtime_library_sha256=canonical_hash({"runtime": "controlled"}),
            compiled_architecture="gfx1030",
            runtime_architecture_base="gfx1030",
            device_ordinal=0,
            device_uuid_bytes_hex="01" * 16,
            device_pci_bdf="0000:01:00.0",
        )
        receipt = SimpleNamespace(
            case_id=f"Case.all-converged.{index}",
            receipt_hash=canonical_hash({"case": slot.slot_id}),
            bindings=bindings,
        )
        case = HipFgmresModelCaseParityResultV1(
            receipt=receipt,
            _cpu_result=slot.cpu_result,
            _observation_result=object(),
            _device_identity_result=object(),
            _source_execution_plan=slot.execution_plan,
        )
        capture = family_module._CaseSourceCaptureV1(
            case_result=case,
            source_case_identity_token=object(),
            receipt=receipt,
            plan=slot.execution_plan,
            cpu_result=slot.cpu_result,
            authority_snapshot_hash=canonical_hash({"authority": slot.slot_id}),
        )
        captures[id(case)] = capture
        cases.append(case)

    monkeypatch.setattr(
        family_module,
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        lambda: registry,
    )
    monkeypatch.setattr(
        family_module,
        "_capture_case_source",
        lambda case: captures[id(case)],
    )
    return tuple(cases), captures


def test_all_converged_family_canonicalizes_and_issues_exact_live_authority(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)

    result = attest_hip_fgmres_all_converged_model_family_v1(tuple(reversed(cases)))

    assert result.case_results == cases
    assert tuple(row.slot_id for row in result.receipt.observations) == tuple(
        row.slot_id for row in registry.slots
    )
    assert result.receipt.totals.package_global_dof_count == 168
    assert result.receipt.totals.package_element_count == 18
    assert result.receipt.totals.package_free_dof_count == 103
    assert result.receipt.totals.package_csr_nnz == 2304
    assert result.receipt.claims.result_ir_verified is False
    assert result.receipt.claims.actual_hardware_execution_verified is False
    assert result.receipt.claims.hardware_gate_completed is False
    assert result.receipt.claims.commercial_ready is False
    assert result.receipt.to_dict()["receipt_hash"] == result.receipt.receipt_hash
    assert validate_hip_fgmres_all_converged_model_family_result_v1(result) is result


def test_all_converged_family_rejects_missing_duplicate_and_unissued_clone(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="case_set_invalid",
    ):
        attest_hip_fgmres_all_converged_model_family_v1(cases[:-1])
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="case_set_invalid",
    ):
        attest_hip_fgmres_all_converged_model_family_v1(list(cases))  # type: ignore[arg-type]
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="case_set_invalid",
    ):
        attest_hip_fgmres_all_converged_model_family_v1((*cases[:-1], cases[0]))

    result = attest_hip_fgmres_all_converged_model_family_v1(cases)
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="issuance_unavailable",
    ):
        validate_hip_fgmres_all_converged_model_family_result_v1(replace(result))
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="issuance_unavailable",
    ):
        validate_hip_fgmres_all_converged_model_family_result_v1(copy.copy(result))

    unissued_case_clone = replace(cases[0])
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="case_authority_invalid",
    ):
        attest_hip_fgmres_all_converged_model_family_v1(
            (unissued_case_clone, *cases[1:])
        )


def test_all_converged_family_rejects_identity_race(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, captures = _controlled_cases(monkeypatch, registry)
    target = cases[0]
    calls = 0

    def capture(case):
        nonlocal calls
        base = captures[id(case)]
        if case is target:
            calls += 1
            if calls > 1:
                return replace(base, source_case_identity_token=object())
        return base

    monkeypatch.setattr(family_module, "_capture_case_source", capture)
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="source_changed",
    ):
        attest_hip_fgmres_all_converged_model_family_v1(cases)


def test_all_converged_family_rejects_coherent_source_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, captures = _controlled_cases(monkeypatch, registry)
    target = cases[0]
    calls = 0

    def capture(case):
        nonlocal calls
        base = captures[id(case)]
        if case is target:
            calls += 1
            if calls > 1:
                return replace(base, receipt=copy.copy(base.receipt))
        return base

    monkeypatch.setattr(family_module, "_capture_case_source", capture)
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="case_capture_invalid",
    ):
        attest_hip_fgmres_all_converged_model_family_v1(cases)


def _rehash_family_receipt(receipt):
    draft = replace(receipt, receipt_hash=family_module._ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            family_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _rehash_family_row(row):
    draft = replace(row, observation_binding_hash=family_module._ZERO_HASH)
    return replace(
        draft,
        observation_binding_hash=canonical_hash(
            family_module._observation_payload(
                draft,
                include_binding_hash=False,
            )
        ),
    )


def _rehash_family_observations(receipt, observations):
    draft = replace(receipt, observations=tuple(observations))
    attestation_id = canonical_hash(
        {
            "capability_profile": draft.capability_profile,
            "registry_hash": draft.bindings.registry_hash,
            "observation_binding_hashes": [
                row.observation_binding_hash for row in draft.observations
            ],
        }
    )
    return _rehash_family_receipt(replace(draft, attestation_id=attestation_id))


def test_all_converged_family_rejects_coherent_claim_and_issuance_transplants(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)
    first = attest_hip_fgmres_all_converged_model_family_v1(cases)

    for false_claim in (
        "commercial_ready",
        "actual_hardware_execution_verified",
        "hardware_gate_completed",
    ):
        forged_claims = replace(first.receipt.claims, **{false_claim: True})
        forged_receipt = _rehash_family_receipt(
            replace(first.receipt, claims=forged_claims)
        )
        with pytest.raises(
            HipFgmresAllConvergedModelFamilyV1Error,
            match="schema_invalid",
        ) as exc_info:
            family_module.validate_hip_fgmres_all_converged_model_family_receipt_v1(
                forged_receipt
            )
        assert exc_info.value.path == f"/claims/{false_claim}"

    for duplicate_field in ("case_id", "case_receipt_hash"):
        rows = list(first.receipt.observations)
        updates = {duplicate_field: getattr(rows[0], duplicate_field)}
        if duplicate_field == "case_receipt_hash":
            updates["logical_case_key"] = canonical_hash(
                {
                    "registry_slot_registration_hash": (rows[1].slot_registration_hash),
                    "case_receipt_hash": rows[0].case_receipt_hash,
                    "source_case_identity_bound": True,
                    "authority_snapshot_hash": rows[1].authority_snapshot_hash,
                }
            )
        rows[1] = _rehash_family_row(replace(rows[1], **updates))
        duplicate_receipt = _rehash_family_observations(first.receipt, rows)
        with pytest.raises(
            HipFgmresAllConvergedModelFamilyV1Error,
            match="duplicate_case",
        ) as exc_info:
            family_module.validate_hip_fgmres_all_converged_model_family_receipt_v1(
                duplicate_receipt
            )
        assert exc_info.value.path == "/cases"

    schema_only_receipt = replace(first.receipt)
    assert (
        family_module.validate_hip_fgmres_all_converged_model_family_receipt_v1(
            schema_only_receipt
        )
        is schema_only_receipt
    )
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="issuance_unavailable",
    ):
        validate_hip_fgmres_all_converged_model_family_result_v1(
            replace(first, receipt=schema_only_receipt)
        )

    second = attest_hip_fgmres_all_converged_model_family_v1(cases)
    with family_module._ISSUANCE_LOCK:
        first_issuance = family_module._ISSUANCES[first]
        second_issuance = family_module._ISSUANCES[second]
        family_module._ISSUANCES[first] = second_issuance
    try:
        with pytest.raises(
            HipFgmresAllConvergedModelFamilyV1Error,
            match="issuance_binding_mismatch",
        ):
            validate_hip_fgmres_all_converged_model_family_result_v1(first)
    finally:
        with family_module._ISSUANCE_LOCK:
            family_module._ISSUANCES[first] = first_issuance

    assert "_ISSUANCES" not in family_module.__all__
    assert "_FamilyIssuanceV1" not in family_module.__all__
    assert "_capture_case_source" not in family_module.__all__


def test_all_converged_family_replay_counts_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)
    loads = 0
    fast_registry_checks = 0
    original_refresh = family_module._refresh_fixed_registry_replay_transaction_v1

    def load_registry():
        nonlocal loads
        loads += 1
        return registry

    def refresh_registry(transaction):
        nonlocal fast_registry_checks
        fast_registry_checks += 1
        return original_refresh(transaction)

    monkeypatch.setattr(
        family_module,
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        load_registry,
    )
    monkeypatch.setattr(
        family_module,
        "_refresh_fixed_registry_replay_transaction_v1",
        refresh_registry,
    )
    result = attest_hip_fgmres_all_converged_model_family_v1(cases)
    assert loads == 1
    assert fast_registry_checks == 1

    loads = 0
    fast_registry_checks = 0
    assert validate_hip_fgmres_all_converged_model_family_result_v1(result) is result
    assert loads == 1
    assert fast_registry_checks == 0

    loads = 0
    fast_registry_checks = 0
    assert (
        family_module.validate_hip_fgmres_all_converged_model_family_receipt_v1(
            result.receipt
        )
        is result.receipt
    )
    assert loads == 1
    assert fast_registry_checks == 0


@pytest.mark.parametrize(
    "resource_kind",
    ("registry", "model"),
)
def test_all_converged_family_rejects_raw_drift_after_final_case_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    registry,
    resource_kind: str,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)
    target = (
        registry_module._REGISTRY_RESOURCE
        if resource_kind == "registry"
        else registry.slots[0].model_resource
    )
    original_evaluate = family_module._evaluate_cases
    original_read = registry_module._read_fixed_resource
    evaluations = 0
    drift_active = False

    def evaluate(case_results, registry_result):
        nonlocal evaluations, drift_active
        evaluated = original_evaluate(case_results, registry_result)
        evaluations += 1
        if evaluations == 3:
            drift_active = True
        return evaluated

    def read_resource(name):
        raw = original_read(name)
        return raw + b"\n" if drift_active and name == target else raw

    monkeypatch.setattr(family_module, "_evaluate_cases", evaluate)
    monkeypatch.setattr(registry_module, "_read_fixed_resource", read_resource)

    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="registry_invalid",
    ):
        attest_hip_fgmres_all_converged_model_family_v1(cases)
    assert evaluations == 3


def test_all_converged_family_rejects_retained_registry_mutation_and_fresh_drift(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)
    result = attest_hip_fgmres_all_converged_model_family_v1(cases)
    original_hash = registry.registry_hash
    object.__setattr__(registry, "registry_hash", canonical_hash({"mutated": True}))
    try:
        with pytest.raises(
            HipFgmresAllConvergedModelFamilyV1Error,
            match="issuance_binding_mismatch",
        ):
            validate_hip_fgmres_all_converged_model_family_result_v1(result)
    finally:
        object.__setattr__(registry, "registry_hash", original_hash)

    drifted = replace(
        registry,
        registry_hash=canonical_hash({"fresh_registry_drift": True}),
    )
    monkeypatch.setattr(
        family_module,
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        lambda: drifted,
    )
    with pytest.raises(
        HipFgmresAllConvergedModelFamilyV1Error,
        match="registry_binding_mismatch",
    ):
        validate_hip_fgmres_all_converged_model_family_result_v1(result)


def test_all_converged_family_weak_issuance_is_collected_and_token_not_reused(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    cases, _ = _controlled_cases(monkeypatch, registry)

    def issue_once():
        result = attest_hip_fgmres_all_converged_model_family_v1(cases)
        with family_module._ISSUANCE_LOCK:
            token = family_module._ISSUANCES[result].mint
            size = len(family_module._ISSUANCES)
        return weakref.ref(result), token, size

    reference, old_token, during = issue_once()
    gc.collect()
    assert reference() is None
    assert len(family_module._ISSUANCES) < during

    replacement = attest_hip_fgmres_all_converged_model_family_v1(cases)
    with family_module._ISSUANCE_LOCK:
        assert family_module._ISSUANCES[replacement].mint is not old_token
