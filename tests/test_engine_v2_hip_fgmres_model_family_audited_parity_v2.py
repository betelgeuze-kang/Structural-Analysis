from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_audited_parity_v2 as audited_module,
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
from structural_analysis.engine_v2.assembly_backend.fgmres_global_schedule_plan_v1 import (
    compile_hip_fgmres_global_sealed_continuation_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_iteration_host_transfer_audit_v1 import (
    HipFgmresIterationHostTransferAuditExecutionContextV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_audited_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2,
    HipFgmresModelFamilyAuditedParityV2Error,
    attest_hip_fgmres_model_family_audited_parity_v2,
    validate_hip_fgmres_model_family_audited_parity_receipt_v2,
    validate_hip_fgmres_model_family_audited_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_host_transfer_audit_v1 import (
    attest_hip_fgmres_model_family_host_transfer_audit_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_launch_fence_audit_v1 import (
    HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1,
    HipFgmresRecurrenceLaunchFenceAuditResultV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_launch_fence_ledger_v1 import (
    HipFgmresRtcOperationCounterV1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from tests.test_engine_v2_hip_fgmres_model_family_host_transfer_audit_v1 import (
    _fake_family_and_contexts,
    _rehash_audit_receipt,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _cleanup_failed_canonical_chain,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_family_audited_parity_v2.schema.json"
)


def _hash(label: str) -> str:
    return canonical_hash({"family_audited_parity_test": label})


def _fake_ordinal_context(
    transfer_context: HipFgmresIterationHostTransferAuditExecutionContextV1,
    slot: Any,
    *,
    index: int,
) -> HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1:
    transfer_result = transfer_context.result
    assert transfer_result is not None
    if not hasattr(transfer_context, "_canonical"):
        transfer_context._canonical = object()
        transfer_context._global_context = object()
        transfer_context._completion_capability = object()
        transfer_context._kernel = object()
    transfer = transfer_result.receipt
    transfer_bindings = transfer.bindings
    schedule = compile_hip_fgmres_global_sealed_continuation_v1(
        slot.recurrence_plan.free_dof_count,
        slot.recurrence_plan.restart_dimension,
        slot.recurrence_plan.max_iterations,
    )
    package = audited_module._fixed_package_slot_semantics(slot, schedule)
    full_launch_count = transfer.dimensions.full_program_launch_count
    assert full_launch_count == schedule.full.launch_count
    total_calls = 8 + full_launch_count + 3
    counter = lambda count: HipFgmresRtcOperationCounterV1(  # noqa: E731
        attempt_count=count,
        success_count=count,
        rejected_count=0,
        ambiguous_count=0,
        in_flight_count=0,
    )
    receipt = SimpleNamespace(
        actual_backend="hip",
        context_id=_hash(f"ordinal-context:{slot.slot_id}"),
        receipt_hash=_hash(f"ordinal-receipt:{slot.slot_id}"),
        bindings=SimpleNamespace(
            canonical_context_id=transfer_bindings.canonical_context_id,
            canonical_open_receipt_hash=(transfer_bindings.canonical_open_receipt_hash),
            canonical_fenced_receipt_hash=(
                transfer_bindings.canonical_fenced_receipt_hash
            ),
            sealed_checkpoint_context_id=(
                transfer_bindings.sealed_checkpoint_context_id
            ),
            sealed_checkpoint_receipt_hash=(
                transfer_bindings.sealed_checkpoint_receipt_hash
            ),
            global_context_id=transfer_bindings.global_context_id,
            global_receipt_hash=transfer_bindings.global_receipt_hash,
            completion_receipt_hash=transfer_bindings.completion_receipt_hash,
            recurrence_plan_hash=transfer_bindings.recurrence_plan_hash,
            recurrence_kernel_abi_hash=(transfer_bindings.recurrence_kernel_abi_hash),
            combined_recurrence_abi_hash=(
                transfer_bindings.combined_recurrence_abi_hash
            ),
            kernel_identity_hash=transfer_bindings.kernel_identity_hash,
            kernel_source_sha256=transfer_bindings.kernel_source_sha256,
            canonical_schedule_hash=package["canonical_schedule_hash"],
            checkpoint_schedule_hash=package["checkpoint_schedule_hash"],
            global_full_schedule_hash=(transfer_bindings.global_full_schedule_hash),
            sealed_prefix_schedule_hash=(transfer_bindings.sealed_prefix_schedule_hash),
            continuation_schedule_hash=(transfer_bindings.continuation_schedule_hash),
            direct_generation_binding_hash=(
                transfer_bindings.direct_generation_binding_hash
            ),
            physical_projection_hash=(transfer_bindings.physical_projection_hash),
            program_descriptor_hash=package["program_descriptor_hash"],
            architecture=transfer_bindings.architecture,
            device_ordinal=transfer_bindings.device_ordinal,
        ),
        dimensions=SimpleNamespace(
            free_dof_count=transfer.dimensions.free_dof_count,
            restart_dimension=slot.recurrence_plan.restart_dimension,
            max_iterations=slot.recurrence_plan.max_iterations,
            maximum_restart_count=transfer.dimensions.maximum_restart_count,
            reduction_stage_count=schedule.plan.reduction_stage_count,
            full_program_launch_count=full_launch_count,
            total_native_call_count=total_calls,
        ),
        telemetry=SimpleNamespace(
            memset=counter(8),
            launch=counter(full_launch_count),
            fence=counter(3),
            operation_ordinal_delta=total_calls,
            event_sequence_delta=2 * total_calls,
        ),
    )
    result = HipFgmresRecurrenceLaunchFenceAuditResultV1(receipt=receipt)
    context = object.__new__(HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1)
    context._lock = threading.RLock()
    context._state = "sealed"
    context._result = result
    context._canonical = transfer_context._canonical
    context._global_context = transfer_context._global_context
    context._completion_capability = transfer_context._completion_capability
    context._kernel = transfer_context._kernel
    context._test_index = index
    return context


def _sources(registry: Any) -> tuple[Any, tuple[Any, ...]]:
    family, transfer_contexts = _fake_family_and_contexts(registry)
    for case in family._case_results:
        case.receipt.bindings.kernel_source_sha256 = (
            audited_module.HIP_FGMRES_RTC_SOURCE_SHA256_V2
        )
    family = family_module.attest_hip_fgmres_model_family_coverage_v2(
        family._case_results
    )
    for slot_id, transfer_context in zip(
        HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2,
        transfer_contexts,
        strict=True,
    ):
        slot = registry.slot(slot_id)
        schedule = compile_hip_fgmres_global_sealed_continuation_v1(
            slot.recurrence_plan.free_dof_count,
            slot.recurrence_plan.restart_dimension,
            slot.recurrence_plan.max_iterations,
        )
        package = audited_module._fixed_package_slot_semantics(slot, schedule)
        transfer_result = transfer_context.result
        assert transfer_result is not None
        transfer_receipt = transfer_result.receipt
        transfer_context._result = replace(
            transfer_result,
            receipt=_rehash_audit_receipt(
                replace(
                    transfer_receipt,
                    bindings=replace(
                        transfer_receipt.bindings,
                        completion_receipt_hash=(
                            transfer_receipt.bindings.global_receipt_hash
                        ),
                        recurrence_kernel_abi_hash=(
                            package["recurrence_kernel_abi_hash"]
                        ),
                        combined_recurrence_abi_hash=(
                            package["combined_recurrence_abi_hash"]
                        ),
                        kernel_source_sha256=package["kernel_source_sha256"],
                        global_full_schedule_hash=schedule.full.canonical_sha256,
                        sealed_prefix_schedule_hash=(
                            schedule.sealed_prefix.canonical_sha256
                        ),
                        continuation_schedule_hash=(
                            schedule.continuation.canonical_sha256
                        ),
                    ),
                    dimensions=replace(
                        transfer_receipt.dimensions,
                        full_program_launch_count=schedule.full.launch_count,
                    ),
                )
            ),
        )
    composition = attest_hip_fgmres_model_family_host_transfer_audit_v1(
        family,
        transfer_contexts,
    )
    ordinals = tuple(
        _fake_ordinal_context(
            transfer_context,
            registry.slot(slot_id),
            index=index,
        )
        for index, (slot_id, transfer_context) in enumerate(
            zip(
                HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2,
                transfer_contexts,
                strict=True,
            )
        )
    )
    return composition, ordinals


def _rehash(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, receipt_hash="sha256:" + "0" * 64, **changes)
    if "observations" in changes and "attestation_id" not in changes:
        draft = replace(
            draft,
            attestation_id=canonical_hash(
                {
                    "capability_profile": (
                        audited_module.HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_CAPABILITY_PROFILE_V2
                    ),
                    "registry_hash": draft.bindings.registry_hash,
                    "source_transfer_audit_receipt_hash": (
                        draft.bindings.source_transfer_audit_receipt_hash
                    ),
                    "source_family_receipt_hash": (
                        draft.bindings.source_family_receipt_hash
                    ),
                    "triple_binding_hashes": [
                        row.triple_binding_hash for row in draft.observations
                    ],
                }
            ),
        )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            audited_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _rehash_row(row: Any, **changes: Any) -> Any:
    draft = replace(
        row,
        triple_binding_hash="sha256:" + "0" * 64,
        **changes,
    )
    return replace(
        draft,
        triple_binding_hash=canonical_hash(
            audited_module._observation_payload(
                draft,
                include_triple_hash=False,
            )
        ),
    )


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
    monkeypatch.setattr(
        audited_module,
        "load_hip_fgmres_fixture_registry_v1",
        lambda: registry,
    )

    def validate_ordinal(result: Any, *, expected_context: Any) -> Any:
        assert expected_context.result is result
        return result

    monkeypatch.setattr(
        audited_module,
        "validate_hip_fgmres_recurrence_launch_fence_audit_result_v1",
        validate_ordinal,
    )
    yield registry
    monkeypatch.undo()


def test_exact_ten_slot_three_authority_composition_is_canonical_and_narrow(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    reversed_ordinals = tuple(reversed(ordinals))
    result = attest_hip_fgmres_model_family_audited_parity_v2(
        source,
        reversed_ordinals,
    )
    assert isinstance(
        reversed_ordinals[0].result.receipt.telemetry.memset,
        HipFgmresRtcOperationCounterV1,
    )
    assert (
        validate_hip_fgmres_model_family_audited_parity_result_v2(
            result,
            expected_transfer_composition_result=source,
            expected_ordinal_contexts=reversed_ordinals,
        )
        is result
    )
    receipt = result.receipt
    assert tuple(row.slot_id for row in receipt.observations) == (
        HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
    )
    assert receipt.totals.paired_slot_count == 10
    assert receipt.totals.recurrence_program_copy_attempt_count == 0
    assert receipt.totals.completion_export_blocking_d2h_attempt_count == 30
    assert receipt.totals.completion_export_blocking_d2h_success_count == 30
    assert receipt.totals.completion_export_byte_count == 4408
    assert receipt.totals.ordinal_memset_attempt_count == 80
    assert receipt.totals.ordinal_memset_success_count == 80
    assert receipt.totals.ordinal_memset_rejected_count == 0
    assert receipt.totals.ordinal_memset_ambiguous_count == 0
    assert receipt.totals.ordinal_memset_in_flight_count == 0
    assert receipt.totals.ordinal_fence_attempt_count == 30
    assert receipt.totals.ordinal_fence_success_count == 30
    assert receipt.totals.ordinal_fence_rejected_count == 0
    assert receipt.totals.ordinal_fence_ambiguous_count == 0
    assert receipt.totals.ordinal_fence_in_flight_count == 0
    assert receipt.totals.ordinal_launch_attempt_count == (
        receipt.totals.ordinal_launch_success_count
    )
    assert receipt.totals.ordinal_launch_rejected_count == 0
    assert receipt.totals.ordinal_launch_ambiguous_count == 0
    assert receipt.totals.ordinal_launch_in_flight_count == 0
    assert receipt.claims.three_retained_authority_families_replayed
    assert receipt.claims.transfer_and_ordinal_lineage_cross_bound
    assert receipt.claims.per_slot_fixed_recurrence_descriptor_order_replayed
    assert not receipt.claims.external_gfx1100_fixed_suite_audited
    assert not receipt.claims.iteration_host_copy_zero_proven
    assert not receipt.claims.device_kernel_semantic_execution_proven
    assert not receipt.claims.result_ir_verified
    assert not (
        receipt.claims.hostile_same_process_mutation_or_interposition_resistance
    )
    assert not receipt.claims.commercial_ready


def test_missing_duplicate_foreign_and_wrong_expected_contexts_fail_closed(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as missing:
        attest_hip_fgmres_model_family_audited_parity_v2(
            source,
            ordinals[:-1],
        )
    assert missing.value.code == (
        "hip_fgmres_family_audited_parity_context_count_invalid"
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as duplicate:
        attest_hip_fgmres_model_family_audited_parity_v2(
            source,
            ordinals[:-1] + (ordinals[0],),
        )
    assert duplicate.value.code == (
        "hip_fgmres_family_audited_parity_duplicate_context"
    )
    result = attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    _, foreign = _sources(sealed_sources)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as changed:
        validate_hip_fgmres_model_family_audited_parity_result_v2(
            result,
            expected_ordinal_contexts=(foreign[0], *ordinals[1:]),
        )
    assert changed.value.code == (
        "hip_fgmres_family_audited_parity_expected_contexts_changed"
    )


def test_ordinal_lifecycle_and_serially_identical_cross_run_splice_fail_closed(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    ordinals[0]._state = "context_ready"
    ordinals[0]._result = None
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as unsealed:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert unsealed.value.code == (
        "hip_fgmres_family_audited_parity_context_not_sealed"
    )

    source, ordinals = _sources(sealed_sources)
    ordinals[0]._state = "poisoned"
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as poisoned:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert poisoned.value.code == (
        "hip_fgmres_family_audited_parity_context_not_sealed"
    )

    source, ordinals = _sources(sealed_sources)
    ordinals[0]._state = "closed"
    assert attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)

    source, _ = _sources(sealed_sources)
    _, foreign_ordinals = _sources(sealed_sources)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as cross_run:
        attest_hip_fgmres_model_family_audited_parity_v2(
            source,
            foreign_ordinals,
        )
    assert cross_run.value.code == (
        "hip_fgmres_family_audited_parity_lineage_binding_mismatch"
    )


def test_cross_run_global_and_common_lineage_splices_are_rejected(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    first = ordinals[0].result
    assert first is not None
    first.receipt.bindings.global_context_id = _hash("foreign-global")
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as foreign:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert foreign.value.code == (
        "hip_fgmres_family_audited_parity_global_join_invalid"
    )

    source, ordinals = _sources(sealed_sources)
    first = ordinals[0].result
    assert first is not None
    first.receipt.bindings.kernel_identity_hash = _hash("foreign-kernel")
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as lineage:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert lineage.value.code == (
        "hip_fgmres_family_audited_parity_lineage_binding_mismatch"
    )

    source, ordinals = _sources(sealed_sources)
    ordinals[0]._global_context = object()
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as identity:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert identity.value.code == (
        "hip_fgmres_family_audited_parity_lineage_binding_mismatch"
    )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("canonical_context_id", _hash("foreign-canonical")),
        ("sealed_checkpoint_receipt_hash", _hash("foreign-sealed")),
        ("recurrence_kernel_abi_hash", _hash("foreign-abi")),
        ("global_full_schedule_hash", _hash("foreign-schedule")),
        ("physical_projection_hash", _hash("foreign-projection")),
        ("device_ordinal", 1),
    ),
)
def test_each_common_lineage_family_is_cross_bound(
    sealed_sources,
    field_name: str,
    replacement: Any,
) -> None:
    source, ordinals = _sources(sealed_sources)
    first = ordinals[0].result
    assert first is not None
    setattr(first.receipt.bindings, field_name, replacement)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as mismatch:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert mismatch.value.code == (
        "hip_fgmres_family_audited_parity_lineage_binding_mismatch"
    )


def test_result_replay_detects_context_result_and_source_identity_changes(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    result = attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    ordinals[0]._result = ordinals[1].result
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as changed:
        validate_hip_fgmres_model_family_audited_parity_result_v2(result)
    assert changed.value.code == (
        "hip_fgmres_family_audited_parity_ordinal_authority_invalid"
    )

    source, ordinals = _sources(sealed_sources)
    result = attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    other_source, _ = _sources(sealed_sources)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as source_changed:
        validate_hip_fgmres_model_family_audited_parity_result_v2(
            result,
            expected_transfer_composition_result=other_source,
        )
    assert source_changed.value.code == (
        "hip_fgmres_family_audited_parity_source_changed"
    )

    source, ordinals = _sources(sealed_sources)
    object.__setattr__(
        source.receipt.bindings,
        "registry_hash",
        _hash("mutated-source-registry"),
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as mutated_source:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert mutated_source.value.code == (
        "hip_fgmres_family_audited_parity_source_invalid"
    )

    source, ordinals = _sources(sealed_sources)
    first = ordinals[0].result
    second = ordinals[1].result
    assert first is not None and second is not None
    second.receipt.receipt_hash = first.receipt.receipt_hash
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as duplicate:
        attest_hip_fgmres_model_family_audited_parity_v2(source, ordinals)
    assert duplicate.value.code == (
        "hip_fgmres_family_audited_parity_duplicate_authority"
    )


def test_detached_claim_order_hash_counter_and_exact_type_forgery_fail_closed(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    receipt = attest_hip_fgmres_model_family_audited_parity_v2(
        source,
        ordinals,
    ).receipt
    claims = replace(receipt.claims, iteration_host_copy_zero_proven=True)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error):
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(receipt, claims=claims)
        )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error):
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(receipt, observations=tuple(reversed(receipt.observations)))
        )
    forged_row = replace(
        receipt.observations[0],
        triple_binding_hash=_hash("forged-triple"),
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error):
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(
                receipt,
                observations=(forged_row, *receipt.observations[1:]),
            )
        )
    changed_counter = _rehash_row(
        receipt.observations[0],
        ordinal_launch_success_count=(
            receipt.observations[0].ordinal_launch_success_count + 1
        ),
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error):
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(
                receipt,
                observations=(changed_counter, *receipt.observations[1:]),
            )
        )
    forged_logical = _rehash_row(
        receipt.observations[0],
        logical_case_key=_hash("forged-logical-case"),
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error):
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(
                receipt,
                observations=(forged_logical, *receipt.observations[1:]),
            )
        )
    zero_launch = _rehash_row(
        receipt.observations[0],
        ordinal_launch_attempt_count=0,
        ordinal_launch_success_count=0,
        ordinal_total_native_call_count=11,
        ordinal_operation_delta=11,
        ordinal_event_delta=22,
    )
    forged_rows = (zero_launch, *receipt.observations[1:])
    forged_totals = audited_module._totals_from_observations(
        forged_rows,
        receipt.totals,
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error):
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(
                receipt,
                observations=forged_rows,
                totals=forged_totals,
            )
        )
    float_totals = replace(receipt.totals, paired_slot_count=10.0)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as aliased:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(receipt, totals=float_totals)
        )
    assert aliased.value.code == "hip_fgmres_family_audited_parity_type_invalid"


def test_detached_zero_launch_and_unsafe_json_integer_fail_closed(
    sealed_sources,
) -> None:
    source, ordinals = _sources(sealed_sources)
    receipt = attest_hip_fgmres_model_family_audited_parity_v2(
        source,
        ordinals,
    ).receipt
    row = receipt.observations[0]
    zero_launch = _rehash_row(
        row,
        ordinal_launch_attempt_count=0,
        ordinal_launch_success_count=0,
        ordinal_operation_delta=11,
        ordinal_event_delta=22,
        ordinal_total_native_call_count=11,
    )
    zero_rows = (zero_launch, *receipt.observations[1:])
    zero_totals = audited_module._totals_from_observations(
        zero_rows,
        receipt.totals,
    )
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as zero:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(receipt, observations=zero_rows, totals=zero_totals)
        )
    assert zero.value.code == ("hip_fgmres_family_audited_parity_schema_invalid")

    unsafe = _rehash_row(row, device_ordinal=9_007_199_254_740_992)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as overflow:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(
                receipt,
                observations=(unsafe, *receipt.observations[1:]),
            )
        )
    assert overflow.value.code == ("hip_fgmres_family_audited_parity_schema_invalid")

    boolean = _rehash_row(row, device_ordinal=True)
    with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as bool_alias:
        validate_hip_fgmres_model_family_audited_parity_receipt_v2(
            _rehash(
                receipt,
                observations=(boolean, *receipt.observations[1:]),
            )
        )
    assert bool_alias.value.code == ("hip_fgmres_family_audited_parity_schema_invalid")


def test_detached_fixed_package_identity_fields_fail_closed(sealed_sources) -> None:
    source, ordinals = _sources(sealed_sources)
    receipt = attest_hip_fgmres_model_family_audited_parity_v2(
        source,
        ordinals,
    ).receipt
    fields = (
        "recurrence_kernel_abi_hash",
        "combined_recurrence_abi_hash",
        "canonical_schedule_hash",
        "checkpoint_schedule_hash",
        "program_descriptor_hash",
        "kernel_source_sha256",
    )
    for field in fields:
        if field == "kernel_source_sha256":
            observations = tuple(
                _rehash_row(row, **{field: _hash(f"forged:{field}")})
                for row in receipt.observations
            )
        else:
            observations = (
                _rehash_row(
                    receipt.observations[0],
                    **{field: _hash(f"forged:{field}")},
                ),
                *receipt.observations[1:],
            )
        with pytest.raises(HipFgmresModelFamilyAuditedParityV2Error) as error:
            validate_hip_fgmres_model_family_audited_parity_receipt_v2(
                _rehash(receipt, observations=observations)
            )
        assert error.value.code == (
            "hip_fgmres_family_audited_parity_observation_invalid"
        )


def test_factory_is_retained_authority_only_and_schema_is_strict(
    sealed_sources,
    monkeypatch,
) -> None:
    source, ordinals = _sources(sealed_sources)

    factory_tree = ast.parse(
        inspect.getsource(attest_hip_fgmres_model_family_audited_parity_v2)
    )
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        for node in ast.walk(factory_tree)
    )
    direct_calls = {
        node.func.id
        for node in ast.walk(factory_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert direct_calls == {
        "_validate_transfer_composition",
        "_capture_ordinal_authorities",
        "_evaluate",
        "HipFgmresModelFamilyAuditedParityResultV2",
        "validate_hip_fgmres_model_family_audited_parity_result_v2",
    }
    module_tree = ast.parse(Path(audited_module.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(module_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    forbidden_import_leaves = {
        "native",
        "rtc",
        "cpu_fgmres",
        "sparse_linear_static",
        "linear_static",
        "fgmres_completion_export_v1",
    }
    assert not {module.rsplit(".", 1)[-1] for module in imported_modules}.intersection(
        forbidden_import_leaves
    )
    rtc_imports = {
        alias.name
        for node in ast.walk(module_tree)
        if isinstance(node, ast.ImportFrom) and node.module == "fgmres_rtc_v2"
        for alias in node.names
    }
    assert rtc_imports == {
        "canonical_first_column_predecessor_launches_v2",
        "first_column_checkpoint_transaction_launches_v2",
    }

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("composition factory must not solve, export, or seal")

    monkeypatch.setattr(
        HipFgmresIterationHostTransferAuditExecutionContextV1,
        "export_completion_buffers",
        forbidden,
    )
    monkeypatch.setattr(
        HipFgmresRecurrenceLaunchFenceAuditExecutionContextV1,
        "seal_terminal_fence",
        forbidden,
    )
    payload = attest_hip_fgmres_model_family_audited_parity_v2(
        source,
        ordinals,
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


def test_failed_canonical_chain_closes_audits_before_native_chain() -> None:
    events: list[str] = []
    primary = RuntimeError("canonical enqueue failed")
    audit_cleanup_error = RuntimeError("audit cleanup failed")

    def close_audits() -> None:
        events.append("audits")
        raise audit_cleanup_error

    class ChainContext:
        closed = False

        def close(self) -> None:
            events.append("native-chain")

    _cleanup_failed_canonical_chain(
        primary,
        close_audits,
        ("canonical", ChainContext()),
    )
    assert events == ["audits", "native-chain"]
    assert getattr(primary, "_engine_v2_cleanup_failures") == (audit_cleanup_error,)
