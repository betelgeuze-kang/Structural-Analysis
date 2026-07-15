from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_iteration_host_transfer_audit_v1 as audit_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_host_transfer_audit_v1 as composition_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_parity_v2 as family_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_iteration_host_transfer_audit_v1 import (
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1,
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_FENCE_BOUNDARY_V1,
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1,
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_START_BOUNDARY_V1,
    HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EXPORT_BOUNDARY_V1,
    HipFgmresHostTransferDeltaV1,
    HipFgmresHostTransferPhaseV1,
    HipFgmresIterationHostTransferAuditBindingsV1,
    HipFgmresIterationHostTransferAuditClaimsV1,
    HipFgmresIterationHostTransferAuditDimensionsV1,
    HipFgmresIterationHostTransferAuditExecutionContextV1,
    HipFgmresIterationHostTransferAuditReceiptV1,
    HipFgmresIterationHostTransferAuditResultV1,
    HipFgmresIterationHostTransferAuditWindowV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_host_transfer_audit_v1 import (
    HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1,
    HipFgmresModelFamilyHostTransferAuditV1Error,
    attest_hip_fgmres_model_family_host_transfer_audit_v1,
    validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1,
    validate_hip_fgmres_model_family_host_transfer_audit_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v2 import (
    attest_hip_fgmres_model_family_coverage_v2,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_model_family_parity_v2 import _fake_case
from tests.test_engine_v2_hip_fgmres_model_family_parity_v2_hardware import (
    _attach_cleanup_failures,
    _run_all_cleanup_steps,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_family_host_transfer_audit_v1.schema.json"
)


def _hash(label: str) -> str:
    return canonical_hash({"family_transfer_audit_test": label})


def _zero_delta() -> HipFgmresHostTransferDeltaV1:
    return HipFgmresHostTransferDeltaV1(0, 0, 0, 0, 0)


def _rehash_audit_receipt(
    receipt: HipFgmresIterationHostTransferAuditReceiptV1,
) -> HipFgmresIterationHostTransferAuditReceiptV1:
    return replace(
        receipt,
        receipt_hash=canonical_hash(
            audit_module._receipt_payload(receipt, include_hash=False)
        ),
    )


def _rehash_composition(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, receipt_hash="sha256:" + "0" * 64, **changes)
    if "observations" in changes and "attestation_id" not in changes:
        draft = replace(
            draft,
            attestation_id=canonical_hash(
                {
                    "capability_profile": composition_module.HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_CAPABILITY_PROFILE_V1,
                    "registry_hash": draft.bindings.registry_hash,
                    "source_family_receipt_hash": (
                        draft.bindings.source_family_receipt_hash
                    ),
                    "pair_binding_hashes": [
                        row.pair_binding_hash for row in draft.observations
                    ],
                }
            ),
        )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            composition_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _rehash_observation(observation: Any, **changes: Any) -> Any:
    draft = replace(
        observation,
        pair_binding_hash="sha256:" + "0" * 64,
        **changes,
    )
    return replace(
        draft,
        pair_binding_hash=canonical_hash(
            composition_module._observation_payload(
                draft,
                include_pair_hash=False,
            )
        ),
    )


def _fake_audit_context(
    case: Any,
    slot: Any,
    *,
    index: int,
) -> HipFgmresIterationHostTransferAuditExecutionContextV1:
    case_bindings = case.receipt.bindings
    free_dof_count = slot.recurrence_plan.free_dof_count
    maximum_restart_count = slot.recurrence_plan.maximum_restart_count
    export_bytes = 16 * free_dof_count + 192 + 72 * maximum_restart_count
    export_context = SimpleNamespace(label=f"export-context:{slot.slot_id}")
    export_result = SimpleNamespace(label=f"export-result:{slot.slot_id}")
    case._observation_result._source_export_context = export_context
    case._observation_result._source_export_result = export_result

    context_id = _hash(f"audit-context:{slot.slot_id}")
    bindings = HipFgmresIterationHostTransferAuditBindingsV1(
        canonical_context_id=_hash(f"canonical:{slot.slot_id}"),
        canonical_open_receipt_hash=_hash(f"canonical-open:{slot.slot_id}"),
        canonical_fenced_receipt_hash=_hash(f"canonical-fenced:{slot.slot_id}"),
        sealed_checkpoint_context_id=_hash(f"sealed:{slot.slot_id}"),
        sealed_checkpoint_receipt_hash=_hash(f"sealed-receipt:{slot.slot_id}"),
        global_context_id=case_bindings.global_context_id,
        global_receipt_hash=case_bindings.global_receipt_hash,
        completion_receipt_hash=_hash(f"completion:{slot.slot_id}"),
        completion_export_context_id=(case_bindings.completion_export_context_id),
        completion_export_receipt_hash=(case_bindings.completion_export_receipt_hash),
        completion_export_payload_hash=(case_bindings.completion_export_payload_hash),
        recurrence_plan_hash=case_bindings.recurrence_plan_hash,
        recurrence_kernel_abi_hash=_hash(f"recurrence-abi:{slot.slot_id}"),
        combined_recurrence_abi_hash=_hash(f"combined-abi:{slot.slot_id}"),
        kernel_identity_hash=case_bindings.kernel_identity_hash,
        kernel_source_sha256=case_bindings.kernel_source_sha256,
        global_full_schedule_hash=_hash(f"full-schedule:{slot.slot_id}"),
        sealed_prefix_schedule_hash=_hash(f"prefix-schedule:{slot.slot_id}"),
        continuation_schedule_hash=_hash(f"continuation:{slot.slot_id}"),
        direct_generation_binding_hash=_hash(f"direct:{slot.slot_id}"),
        physical_projection_hash=_hash(f"projection:{slot.slot_id}"),
        architecture="gfx1030",
        device_ordinal=0,
        runtime_scope=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_RUNTIME_SCOPE_V1,
        native_loader_bound_runtime=True,
    )
    zero_phase = HipFgmresHostTransferPhaseV1(
        sequence_delta=0,
        h2d_async=_zero_delta(),
        d2h_async=_zero_delta(),
        d2h_blocking=_zero_delta(),
    )
    export_phase = HipFgmresHostTransferPhaseV1(
        sequence_delta=6,
        h2d_async=_zero_delta(),
        d2h_async=_zero_delta(),
        d2h_blocking=HipFgmresHostTransferDeltaV1(
            attempt_count=3,
            success_count=3,
            failure_count=0,
            bytes_attempted=export_bytes,
            bytes_succeeded=export_bytes,
        ),
    )
    start_sequence = 100 * index
    draft = HipFgmresIterationHostTransferAuditReceiptV1(
        status="exported",
        context_id=context_id,
        evidence_scope=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        bindings=bindings,
        window=HipFgmresIterationHostTransferAuditWindowV1(
            start_boundary=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_START_BOUNDARY_V1,
            fence_boundary=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_FENCE_BOUNDARY_V1,
            export_boundary=HIP_FGMRES_ITERATION_HOST_TRANSFER_AUDIT_EXPORT_BOUNDARY_V1,
            start_sequence=start_sequence,
            fence_sequence=start_sequence,
            export_sequence=start_sequence + 6,
            start_in_flight_count=0,
            fence_in_flight_count=0,
            export_in_flight_count=0,
            recurrence_program=zero_phase,
            completion_export=export_phase,
        ),
        dimensions=HipFgmresIterationHostTransferAuditDimensionsV1(
            free_dof_count=free_dof_count,
            maximum_restart_count=maximum_restart_count,
            full_program_launch_count=1,
            solution_byte_count=8 * free_dof_count,
            true_residual_byte_count=8 * free_dof_count,
            solve_record_byte_count=192 + 72 * maximum_restart_count,
            total_export_byte_count=export_bytes,
        ),
        claims=HipFgmresIterationHostTransferAuditClaimsV1(
            canonical_to_global_fence_lineage_bound=True,
            exact_bound_runtime_copy_counter_bound=True,
            recurrence_program_bound_runtime_copy_attempt_zero=True,
            post_fence_exact_three_blocking_d2h=True,
            post_fence_export_byte_count_exact=True,
            same_runtime_device_stream_lineage_bound=True,
        ),
        receipt_hash="sha256:" + "0" * 64,
    )
    receipt = _rehash_audit_receipt(draft)
    audit_result = HipFgmresIterationHostTransferAuditResultV1(
        receipt=receipt,
        completion_export_context=export_context,  # type: ignore[arg-type]
        completion_export_result=export_result,  # type: ignore[arg-type]
    )
    context = object.__new__(HipFgmresIterationHostTransferAuditExecutionContextV1)
    context._lock = threading.RLock()
    context._state = "exported"
    context._result = audit_result
    return context


def _fake_family_and_contexts(
    registry: Any,
) -> tuple[Any, tuple[HipFgmresIterationHostTransferAuditExecutionContextV1, ...]]:
    cases: list[Any] = []
    contexts: list[HipFgmresIterationHostTransferAuditExecutionContextV1] = []
    for index, slot_id in enumerate(
        HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
    ):
        slot = registry.slot(slot_id)
        case = _fake_case(registry, slot_id)
        bindings = case.receipt.bindings
        bindings.completion_export_context_id = _hash(f"export-context:{slot_id}")
        bindings.completion_export_receipt_hash = _hash(f"export-receipt:{slot_id}")
        bindings.completion_export_payload_hash = _hash(f"export-payload:{slot_id}")
        bindings.global_context_id = _hash(f"global-context:{slot_id}")
        bindings.global_receipt_hash = _hash(f"global-receipt:{slot_id}")
        case.receipt.dimensions = SimpleNamespace(
            free_dof_count=slot.recurrence_plan.free_dof_count,
            maximum_restart_count=slot.recurrence_plan.maximum_restart_count,
        )
        context = _fake_audit_context(case, slot, index=index)
        cases.append(case)
        contexts.append(context)
    family = attest_hip_fgmres_model_family_coverage_v2(tuple(cases))
    return family, tuple(contexts)


@pytest.fixture(scope="module")
def sealed_sources():
    registry = load_hip_fgmres_fixture_registry_v1()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        family_module,
        "load_hip_fgmres_fixture_registry_v1",
        lambda: registry,
    )
    monkeypatch.setattr(
        family_module,
        "validate_hip_fgmres_model_case_parity_result_v1",
        lambda case: case,
    )
    monkeypatch.setattr(
        composition_module,
        "load_hip_fgmres_fixture_registry_v1",
        lambda: registry,
    )
    monkeypatch.setattr(
        composition_module,
        "validate_hip_fgmres_model_family_parity_result_v2",
        lambda result: result,
    )
    monkeypatch.setattr(
        composition_module,
        "validate_hip_fgmres_iteration_host_transfer_audit_result_v1",
        lambda result, *, expected_context: result,
    )
    yield registry
    monkeypatch.undo()


def test_exact_ten_slot_composition_is_canonical_and_narrow(sealed_sources) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    reversed_contexts = tuple(reversed(contexts))
    result = attest_hip_fgmres_model_family_host_transfer_audit_v1(
        family,
        reversed_contexts,
    )
    assert (
        validate_hip_fgmres_model_family_host_transfer_audit_result_v1(
            result,
            expected_family_result=family,
            expected_audit_contexts=reversed_contexts,
        )
        is result
    )
    receipt = result.receipt
    assert tuple(row.slot_id for row in receipt.observations) == (
        HIP_FGMRES_MODEL_FAMILY_HOST_TRANSFER_AUDIT_REQUIRED_SLOT_IDS_V1
    )
    assert receipt.totals.paired_slot_count == 10
    assert receipt.totals.recurrence_program_copy_attempt_count == 0
    assert receipt.totals.completion_export_blocking_d2h_attempt_count == 30
    assert receipt.totals.completion_export_blocking_d2h_success_count == 30
    assert receipt.totals.completion_export_byte_count == 4408
    assert receipt.claims.case_parity_and_audit_same_export_identity_bound
    assert receipt.claims.ten_same_process_audit_authorities_captured_while_exported
    assert receipt.claims.composition_factory_reuses_retained_export_identity_only
    assert receipt.claims.per_slot_bound_runtime_recurrence_copy_attempt_zero
    assert not receipt.claims.external_gfx1100_fixed_suite_audited
    assert not receipt.claims.iteration_host_copy_zero_proven
    assert not (
        receipt.claims.whole_process_additional_device_solve_or_export_absence_proven
    )
    assert not receipt.claims.standalone_receipt_provenance_authenticity
    assert not receipt.claims.commercial_ready


def test_context_count_duplicate_and_wrong_expected_order_fail_closed(
    sealed_sources,
) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as missing:
        attest_hip_fgmres_model_family_host_transfer_audit_v1(
            family,
            contexts[:-1],
        )
    assert missing.value.code == (
        "hip_fgmres_family_transfer_audit_context_count_invalid"
    )
    duplicate = contexts[:-1] + (contexts[0],)
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as repeated:
        attest_hip_fgmres_model_family_host_transfer_audit_v1(family, duplicate)
    assert repeated.value.code == ("hip_fgmres_family_transfer_audit_duplicate_context")
    result = attest_hip_fgmres_model_family_host_transfer_audit_v1(
        family,
        tuple(reversed(contexts)),
    )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as changed:
        validate_hip_fgmres_model_family_host_transfer_audit_result_v1(
            result,
            expected_audit_contexts=contexts,
        )
    assert changed.value.code == (
        "hip_fgmres_family_transfer_audit_expected_contexts_changed"
    )

    _, foreign_contexts = _fake_family_and_contexts(sealed_sources)
    expected_with_foreign = list(reversed(contexts))
    expected_with_foreign[0] = foreign_contexts[0]
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as foreign:
        validate_hip_fgmres_model_family_host_transfer_audit_result_v1(
            result,
            expected_audit_contexts=tuple(expected_with_foreign),
        )
    assert foreign.value.code == (
        "hip_fgmres_family_transfer_audit_expected_contexts_changed"
    )


def test_source_family_and_composition_registry_identity_are_atomic(
    sealed_sources,
    monkeypatch,
) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    changed_registry = replace(
        sealed_sources,
        registry_bytes_sha256=_hash("changed-registry-bytes"),
        registry_hash=_hash("changed-registry"),
    )
    monkeypatch.setattr(
        composition_module,
        "load_hip_fgmres_fixture_registry_v1",
        lambda: changed_registry,
    )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as changed:
        attest_hip_fgmres_model_family_host_transfer_audit_v1(family, contexts)
    assert changed.value.code == (
        "hip_fgmres_family_transfer_audit_source_registry_identity_mismatch"
    )


def test_export_identity_and_lineage_swap_are_rejected(sealed_sources) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    first_case = family._case_results[0]
    first_case._observation_result._source_export_result = object()
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as identity:
        attest_hip_fgmres_model_family_host_transfer_audit_v1(family, contexts)
    assert identity.value.code == (
        "hip_fgmres_family_transfer_audit_export_identity_mismatch"
    )

    family, contexts = _fake_family_and_contexts(sealed_sources)
    first_result = contexts[0].result
    assert first_result is not None
    forged_bindings = replace(
        first_result.receipt.bindings,
        kernel_identity_hash=_hash("foreign-kernel"),
    )
    contexts[0]._result = replace(
        first_result,
        receipt=_rehash_audit_receipt(
            replace(first_result.receipt, bindings=forged_bindings)
        ),
    )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as lineage:
        attest_hip_fgmres_model_family_host_transfer_audit_v1(family, contexts)
    assert lineage.value.code == (
        "hip_fgmres_family_transfer_audit_lineage_binding_mismatch"
    )


def test_detached_claim_order_pair_and_exact_type_forgery_are_rejected(
    sealed_sources,
) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    receipt = attest_hip_fgmres_model_family_host_transfer_audit_v1(
        family,
        contexts,
    ).receipt
    forged_claims = replace(receipt.claims, iteration_host_copy_zero_proven=True)
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error):
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
            _rehash_composition(receipt, claims=forged_claims)
        )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error):
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
            _rehash_composition(
                receipt,
                observations=tuple(reversed(receipt.observations)),
            )
        )
    forged_row = replace(
        receipt.observations[0],
        pair_binding_hash=_hash("forged-pair"),
    )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error):
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
            _rehash_composition(
                receipt,
                observations=(forged_row, *receipt.observations[1:]),
            )
        )
    float_totals = replace(receipt.totals, paired_slot_count=10.0)
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as aliased:
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
            _rehash_composition(receipt, totals=float_totals)
        )
    assert aliased.value.code == "hip_fgmres_family_transfer_audit_type_invalid"


def test_detached_impossible_context_and_device_projections_are_rejected(
    sealed_sources,
) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    receipt = attest_hip_fgmres_model_family_host_transfer_audit_v1(
        family,
        contexts,
    ).receipt

    duplicate_context = _rehash_observation(
        receipt.observations[1],
        audit_context_id=receipt.observations[0].audit_context_id,
        global_context_id=receipt.observations[0].global_context_id,
    )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as duplicate:
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
            _rehash_composition(
                receipt,
                observations=(
                    receipt.observations[0],
                    duplicate_context,
                    *receipt.observations[2:],
                ),
            )
        )
    assert duplicate.value.code == (
        "hip_fgmres_family_transfer_audit_duplicate_observation"
    )

    inconsistent_device = _rehash_observation(
        receipt.observations[1],
        device_ordinal=1,
        kernel_identity_hash=_hash("other-kernel-on-same-architecture"),
    )
    with pytest.raises(HipFgmresModelFamilyHostTransferAuditV1Error) as inconsistent:
        validate_hip_fgmres_model_family_host_transfer_audit_receipt_v1(
            _rehash_composition(
                receipt,
                observations=(
                    receipt.observations[0],
                    inconsistent_device,
                    *receipt.observations[2:],
                ),
            )
        )
    assert inconsistent.value.code == (
        "hip_fgmres_family_transfer_audit_architecture_device_inconsistent"
    )


def test_valid_payload_schema_is_strict_at_every_object_level(
    sealed_sources,
) -> None:
    family, contexts = _fake_family_and_contexts(sealed_sources)
    payload = attest_hip_fgmres_model_family_host_transfer_audit_v1(
        family,
        contexts,
    ).receipt.to_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(payload)
    for path in ("top", "bindings", "observation", "totals", "claims"):
        forged = deepcopy(payload)
        target = {
            "top": forged,
            "bindings": forged["bindings"],
            "observation": forged["observations"][0],
            "totals": forged["totals"],
            "claims": forged["claims"],
        }[path]
        target["unexpected"] = True
        with pytest.raises(ValidationError):
            validator.validate(forged)


def test_hardware_cleanup_runs_every_step_and_preserves_primary_failure() -> None:
    calls: list[str] = []

    def fail(label: str, exception: BaseException) -> None:
        calls.append(label)
        raise exception

    with pytest.raises(ValueError, match="first") as raised:
        _run_all_cleanup_steps(
            (
                lambda: fail("first", ValueError("first")),
                lambda: fail("second", RuntimeError("second")),
                lambda: calls.append("third"),
            )
        )
    assert calls == ["first", "second", "third"]
    assert tuple(
        type(exc) for exc in getattr(raised.value, "_engine_v2_cleanup_failures")
    ) == (RuntimeError,)

    primary = LookupError("primary")
    cleanup = OSError("cleanup")
    _attach_cleanup_failures(primary, [cleanup])
    assert getattr(primary, "_engine_v2_cleanup_failures") == (cleanup,)
