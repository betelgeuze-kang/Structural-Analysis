from __future__ import annotations

import ast
from copy import copy, deepcopy
from dataclasses import dataclass, replace
import inspect
from typing import Any, Callable

from jsonschema import ValidationError
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_diagnostic_ir_v1 as bridge_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_diagnostic_ir_v1 as family_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_diagnostic_ir_v1 import (
    HipFgmresDiagnosticIRBridgeResultV1,
    build_hip_fgmres_diagnostic_ir_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_diagnostic_ir_v1 import (
    HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1,
    HipFgmresModelFamilyDiagnosticIRV1Error,
    attest_hip_fgmres_model_family_diagnostic_ir_v1,
    validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1,
    validate_hip_fgmres_model_family_diagnostic_ir_result_v1,
)
from tests.test_engine_v2_hip_fgmres_diagnostic_ir_v1 import (
    _capture as _diagnostic_capture,
)
from tests.test_engine_v2_hip_fgmres_model_family_result_ir_disposition_v1 import (
    EXPECTED_NONCONVERGED_SLOT_IDS,
    _SyntheticFamily,
    _make_family,
    sealed_registry as _source_sealed_registry,
)


@dataclass(slots=True)
class _DiagnosticFamily:
    family: _SyntheticFamily
    captures_by_case_identity: dict[int, Any]
    bridges: tuple[HipFgmresDiagnosticIRBridgeResultV1, ...]
    result: Any
    disposition_manifest_before: dict[str, Any]


@pytest.fixture(scope="module")
def family_registry() -> Any:
    source = _source_sealed_registry.__wrapped__()
    registry = next(source)
    try:
        yield registry
    finally:
        with pytest.raises(StopIteration):
            next(source)


def _aligned_diagnostic_capture(
    family: _SyntheticFamily,
    slot_id: str,
) -> Any:
    slot = family.registry.slot(slot_id)
    case = family.cases_by_slot[slot_id]
    audited = next(
        row
        for row in family.audited_result.receipt.observations
        if row.slot_id == slot_id
    )
    disposition = next(
        row
        for row in family.disposition_result.receipt.observations
        if row.slot_id == slot_id
    )
    capture = _diagnostic_capture(slot)
    receipt = capture.receipt
    receipt.case_id = case.receipt.case_id
    receipt.receipt_hash = audited.case_receipt_hash
    bindings = receipt.bindings
    bindings.terminal_observation_receipt_hash = (
        disposition.terminal_observation_receipt_hash
    )
    bindings.completion_export_context_id = disposition.completion_export_context_id
    bindings.completion_export_receipt_hash = audited.completion_export_receipt_hash
    bindings.completion_export_payload_hash = audited.completion_export_payload_hash
    bindings.device_identity_receipt_hash = audited.device_identity_receipt_hash
    bindings.compiled_architecture = audited.compiled_architecture
    bindings.runtime_architecture_base = audited.runtime_architecture_base
    bindings.device_ordinal = audited.device_ordinal
    bindings.device_uuid_bytes_hex = audited.device_uuid_bytes_hex
    bindings.device_pci_bdf = audited.device_pci_bdf

    observation = capture.observation_result.receipt
    observation.receipt_hash = disposition.terminal_observation_receipt_hash
    observation.bindings.completion_export_context_id = (
        disposition.completion_export_context_id
    )
    device = capture.device_identity_result.receipt
    device.receipt_hash = audited.device_identity_receipt_hash
    device.architecture.expected_compiled.normalized = audited.compiled_architecture
    device.architecture.runtime.base = audited.runtime_architecture_base
    device.device.selected_ordinal = audited.device_ordinal
    device.device.uuid_bytes_hex = audited.device_uuid_bytes_hex
    device.device.pci_bdf = audited.device_pci_bdf

    export = capture.export_result
    export.receipt.receipt_hash = audited.completion_export_receipt_hash
    export.receipt.payload_hash = audited.completion_export_payload_hash
    export.payload_hash = audited.completion_export_payload_hash
    capture.published_result.receipt_hash = audited.completion_export_receipt_hash
    capture.published_result.payload_hash = audited.completion_export_payload_hash
    return capture


def _build_diagnostic_bridges(
    family: _SyntheticFamily,
) -> tuple[dict[int, Any], tuple[HipFgmresDiagnosticIRBridgeResultV1, ...]]:
    captures = {
        id(family.cases_by_slot[slot_id]): _aligned_diagnostic_capture(
            family,
            slot_id,
        )
        for slot_id in EXPECTED_NONCONVERGED_SLOT_IDS
    }
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda case: captures[id(case)],
    )
    try:
        bridges = tuple(
            build_hip_fgmres_diagnostic_ir_v1(
                family.cases_by_slot[slot_id],
                diagnostic_id=f"Diagnostic.{slot_id}.v1",
            )
            for slot_id in EXPECTED_NONCONVERGED_SLOT_IDS
        )
    finally:
        monkeypatch.undo()
    return captures, bridges


def _install_live_sources(
    monkeypatch: pytest.MonkeyPatch,
    fixture: _DiagnosticFamily,
) -> None:
    monkeypatch.setattr(
        family_module,
        "_capture_live_source",
        lambda audited: (
            fixture.family.source_snapshot
            if audited is fixture.family.audited_result
            else (_ for _ in ()).throw(AssertionError("unexpected audited source"))
        ),
    )
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda case: fixture.captures_by_case_identity[id(case)],
    )


@pytest.fixture(scope="module")
def diagnostic_family(family_registry: Any) -> _DiagnosticFamily:
    family = _make_family(family_registry)
    captures, bridges = _build_diagnostic_bridges(family)
    disposition_manifest_before = deepcopy(family.disposition_result.receipt.to_dict())
    monkeypatch = pytest.MonkeyPatch()
    temporary = _DiagnosticFamily(
        family=family,
        captures_by_case_identity=captures,
        bridges=bridges,
        result=None,
        disposition_manifest_before=disposition_manifest_before,
    )
    _install_live_sources(monkeypatch, temporary)
    try:
        result = attest_hip_fgmres_model_family_diagnostic_ir_v1(
            family.audited_result,
            family.disposition_result,
            tuple(reversed(bridges)),
        )
    finally:
        monkeypatch.undo()
    temporary.result = result
    return temporary


@pytest.fixture(scope="module")
def foreign_diagnostic_family(family_registry: Any) -> _DiagnosticFamily:
    family = _make_family(family_registry)
    captures, bridges = _build_diagnostic_bridges(family)
    return _DiagnosticFamily(
        family=family,
        captures_by_case_identity=captures,
        bridges=bridges,
        result=None,
        disposition_manifest_before=deepcopy(
            family.disposition_result.receipt.to_dict()
        ),
    )


def test_exact_three_slot_manifest_preserves_the_seven_three_disposition(
    diagnostic_family: _DiagnosticFamily,
) -> None:
    result = diagnostic_family.result
    assert validate_hip_fgmres_model_family_diagnostic_ir_result_v1(result) is result
    assert result._source_result_ir_disposition is (
        diagnostic_family.family.disposition_result
    )
    assert result._source_audited_receipt is (
        diagnostic_family.family.audited_result.receipt
    )
    assert result._source_result_ir_disposition.receipt.to_dict() == (
        diagnostic_family.disposition_manifest_before
    )
    assert tuple(row.slot_id for row in result.receipt.observations) == (
        HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1
    )
    assert result.diagnostic_bridges == diagnostic_family.bridges

    totals = result.receipt.totals
    assert (
        totals.required_diagnostic_slot_count,
        totals.ready_result_ir_v2_count,
        totals.ready_diagnostic_ir_v1_count,
    ) == (3, 7, 3)
    assert (
        totals.diagnostic_global_dof_count,
        totals.diagnostic_element_count,
        totals.diagnostic_free_dof_count,
        totals.diagnostic_csr_nnz,
    ) == (72, 9, 54, 1080)
    assert (
        totals.diagnostic_array_count,
        totals.diagnostic_array_byte_count,
        totals.diagnostic_detached_raw_export_payload_byte_count,
    ) == (9, 1584, 1872)
    assert (
        totals.upstream_completion_export_blocking_d2h_attempt_count,
        totals.upstream_completion_export_blocking_d2h_success_count,
        totals.upstream_completion_export_blocking_d2h_failure_count,
        totals.upstream_completion_export_byte_count,
    ) == (9, 9, 0, 1872)
    assert totals.sparse_residual_replay_count == 3
    assert all(
        value == 0
        for name, value in totals.to_dict().items()
        if name.startswith("diagnostic_projection_")
    )

    claims = result.receipt.claims
    assert claims.seven_converged_result_ir_v2_preserved
    assert claims.three_nonconverged_diagnostic_ir_v1_verified
    assert claims.partial_iterates_preserved
    assert claims.nonconverged_state_commit_zero
    assert not claims.exact_ten_slot_result_ir_v2_ready
    assert not claims.all_ten_solution_ready
    assert not claims.all_ten_converged
    assert not claims.diagnostic_ir_is_solution_result
    assert not claims.commercial_ready
    assert not claims.promotion_eligible


def test_observations_bind_raw_exports_and_canonical_diagnostic_arrays_separately(
    diagnostic_family: _DiagnosticFamily,
) -> None:
    observations = diagnostic_family.result.receipt.observations
    assert tuple(row.diagnostic_array_byte_count for row in observations) == (
        240,
        672,
        672,
    )
    assert tuple(
        row.detached_raw_export_payload_byte_count for row in observations
    ) == (360, 792, 720)
    for row, bridge in zip(
        observations,
        diagnostic_family.bridges,
        strict=True,
    ):
        assert row.source_solution_payload_sha256 == (
            bridge._source_seal.solution_payload_sha256
        )
        assert row.exported_free_residual_payload_sha256 == (
            bridge._source_seal.true_residual_payload_sha256
        )
        assert row.solve_record_payload_sha256 == (
            bridge._source_seal.solve_record_payload_sha256
        )
        assert row.committed_state_hash is None
        assert row.rollback_state_hash == row.accepted_state_hash
        assert (
            row.upstream_completion_export_blocking_d2h_attempt_count,
            row.upstream_completion_export_blocking_d2h_success_count,
            row.upstream_completion_export_blocking_d2h_failure_count,
        ) == (3, 3, 0)
        assert (
            row.additional_device_operation_count,
            row.additional_d2h_operation_count,
            row.additional_solve_count,
            row.additional_export_count,
            row.fallback_count,
            row.state_commit_count,
        ) == (0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "invalid",
    (
        lambda bridges: bridges[:-1],
        lambda bridges: bridges[:-1] + (bridges[0],),
        lambda bridges: list(bridges),
    ),
    ids=("missing", "duplicate", "non_tuple"),
)
def test_missing_duplicate_and_non_tuple_bridge_sets_fail_closed(
    diagnostic_family: _DiagnosticFamily,
    monkeypatch: pytest.MonkeyPatch,
    invalid: Callable[[tuple[Any, ...]], Any],
) -> None:
    _install_live_sources(monkeypatch, diagnostic_family)
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as error:
        attest_hip_fgmres_model_family_diagnostic_ir_v1(
            diagnostic_family.family.audited_result,
            diagnostic_family.family.disposition_result,
            invalid(diagnostic_family.bridges),
        )
    assert error.value.code == ("hip_fgmres_family_diagnostic_ir_v1_bridge_set_invalid")


def test_serially_identical_cross_run_bridge_splice_fails_live_token_binding(
    diagnostic_family: _DiagnosticFamily,
    foreign_diagnostic_family: _DiagnosticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = diagnostic_family.bridges[0]
    foreign = foreign_diagnostic_family.bridges[0]
    assert foreign.receipt.to_dict() == local.receipt.to_dict()
    assert foreign._source_seal.case_parity_receipt_hash == (
        local._source_seal.case_parity_receipt_hash
    )
    _install_live_sources(monkeypatch, diagnostic_family)
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as error:
        attest_hip_fgmres_model_family_diagnostic_ir_v1(
            diagnostic_family.family.audited_result,
            diagnostic_family.family.disposition_result,
            (foreign, *diagnostic_family.bridges[1:]),
        )
    assert error.value.code == (
        "hip_fgmres_family_diagnostic_ir_v1_live_bridge_invalid"
    )


def test_source_change_during_triple_capture_is_rejected(
    diagnostic_family: _DiagnosticFamily,
    foreign_diagnostic_family: _DiagnosticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = iter(
        (
            diagnostic_family.family.source_snapshot,
            diagnostic_family.family.source_snapshot,
            foreign_diagnostic_family.family.source_snapshot,
        )
    )
    monkeypatch.setattr(
        family_module,
        "_capture_live_source",
        lambda _audited: next(snapshots),
    )
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda case: diagnostic_family.captures_by_case_identity[id(case)],
    )
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as error:
        attest_hip_fgmres_model_family_diagnostic_ir_v1(
            diagnostic_family.family.audited_result,
            diagnostic_family.family.disposition_result,
            diagnostic_family.bridges,
        )
    assert error.value.code == "hip_fgmres_family_diagnostic_ir_v1_source_changed"


def test_post_close_validation_never_recaptures_live_authority(
    diagnostic_family: _DiagnosticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("detached validation consulted a live authority")

    monkeypatch.setattr(family_module, "_capture_live_source", forbidden)
    monkeypatch.setattr(
        family_module,
        "_validate_hip_fgmres_diagnostic_ir_v1_against_live_case",
        forbidden,
    )
    monkeypatch.setattr(bridge_module, "_capture_live_authority", forbidden)
    assert (
        validate_hip_fgmres_model_family_diagnostic_ir_result_v1(
            diagnostic_family.result
        )
        is diagnostic_family.result
    )


def test_process_local_family_and_bridge_clone_issuance_cannot_be_recycled(
    diagnostic_family: _DiagnosticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = diagnostic_family.result
    direct = type(result)(
        receipt=result.receipt,
        _source_audited_receipt=result._source_audited_receipt,
        _source_result_ir_disposition=result._source_result_ir_disposition,
        _diagnostic_bridges=result._diagnostic_bridges,
    )
    for clone in (direct, replace(result), copy(result)):
        with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as result_error:
            validate_hip_fgmres_model_family_diagnostic_ir_result_v1(clone)
        assert result_error.value.code == (
            "hip_fgmres_family_diagnostic_ir_v1_issuance_unavailable"
        )

    first_row = result.receipt.observations[0]
    forged_row = replace(
        first_row,
        device_uuid_bytes_hex="fedcba9876543210fedcba9876543210",
        diagnostic_binding_hash=family_module._ZERO_HASH,
    )
    forged_row = replace(
        forged_row,
        diagnostic_binding_hash=family_module.canonical_hash(
            family_module._observation_payload(
                forged_row,
                include_binding_hash=False,
            )
        ),
    )
    forged_observations = (forged_row, *result.receipt.observations[1:])
    bindings = result.receipt.bindings
    forged_attestation_id = family_module.canonical_hash(
        {
            "profile": (
                family_module.HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1
            ),
            "registry_hash": bindings.registry_hash,
            "source_audited_receipt_hash": bindings.source_audited_receipt_hash,
            "source_result_ir_disposition_receipt_hash": (
                bindings.source_result_ir_disposition_receipt_hash
            ),
            "observation_binding_hashes": [
                row.diagnostic_binding_hash for row in forged_observations
            ],
        }
    )
    forged_receipt = replace(
        result.receipt,
        observations=forged_observations,
        attestation_id=forged_attestation_id,
        receipt_hash=family_module._ZERO_HASH,
    )
    forged_receipt = replace(
        forged_receipt,
        receipt_hash=family_module.canonical_hash(
            family_module._receipt_payload(forged_receipt, include_hash=False)
        ),
    )
    assert (
        validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(forged_receipt)
        is forged_receipt
    )
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as coherent_error:
        validate_hip_fgmres_model_family_diagnostic_ir_result_v1(
            replace(result, receipt=forged_receipt)
        )
    assert coherent_error.value.code == (
        "hip_fgmres_family_diagnostic_ir_v1_issuance_unavailable"
    )

    _install_live_sources(monkeypatch, diagnostic_family)
    cloned_bridge = replace(diagnostic_family.bridges[0])
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as bridge_error:
        attest_hip_fgmres_model_family_diagnostic_ir_v1(
            diagnostic_family.family.audited_result,
            diagnostic_family.family.disposition_result,
            (cloned_bridge, *diagnostic_family.bridges[1:]),
        )
    assert bridge_error.value.code == (
        "hip_fgmres_family_diagnostic_ir_v1_bridge_invalid"
    )


def test_strict_schema_rejects_claim_order_and_extension_forgery(
    diagnostic_family: _DiagnosticFamily,
) -> None:
    manifest = diagnostic_family.result.to_manifest()
    extra = deepcopy(manifest)
    extra["unsupported_extension"] = True
    with pytest.raises(ValidationError):
        family_module._schema_validator().validate(extra)

    reordered = deepcopy(manifest)
    reordered["observations"] = list(reversed(reordered["observations"]))
    with pytest.raises(ValidationError):
        family_module._schema_validator().validate(reordered)

    promoted = deepcopy(manifest)
    promoted["claims"]["all_ten_solution_ready"] = True
    with pytest.raises(ValidationError):
        family_module._schema_validator().validate(promoted)

    forged_claims = replace(
        diagnostic_family.result.receipt.claims,
        all_ten_solution_ready=True,
    )
    forged_receipt = replace(
        diagnostic_family.result.receipt,
        claims=forged_claims,
        receipt_hash=family_module._ZERO_HASH,
    )
    forged_receipt = replace(
        forged_receipt,
        receipt_hash=family_module.canonical_hash(
            family_module._receipt_payload(forged_receipt, include_hash=False)
        ),
    )
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as error:
        validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(forged_receipt)
    assert error.value.code == "hip_fgmres_family_diagnostic_ir_v1_schema_invalid"


def test_detached_receipt_rejects_rollback_and_byte_redistribution_rehashes(
    diagnostic_family: _DiagnosticFamily,
) -> None:
    source = diagnostic_family.result.receipt

    def reissue(observations: tuple[Any, ...]):
        attestation_id = family_module.canonical_hash(
            {
                "profile": (
                    family_module.HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1
                ),
                "registry_hash": source.bindings.registry_hash,
                "source_audited_receipt_hash": (
                    source.bindings.source_audited_receipt_hash
                ),
                "source_result_ir_disposition_receipt_hash": (
                    source.bindings.source_result_ir_disposition_receipt_hash
                ),
                "observation_binding_hashes": [
                    row.diagnostic_binding_hash for row in observations
                ],
            }
        )
        draft = replace(
            source,
            observations=observations,
            attestation_id=attestation_id,
            receipt_hash=family_module._ZERO_HASH,
        )
        return replace(
            draft,
            receipt_hash=family_module.canonical_hash(
                family_module._receipt_payload(draft, include_hash=False)
            ),
        )

    def rehash_row(row: Any, **changes: Any) -> Any:
        draft = replace(
            row,
            **changes,
            diagnostic_binding_hash=family_module._ZERO_HASH,
        )
        return replace(
            draft,
            diagnostic_binding_hash=family_module.canonical_hash(
                family_module._observation_payload(
                    draft,
                    include_binding_hash=False,
                )
            ),
        )

    rows = source.observations
    wrong_rollback = rehash_row(
        rows[0],
        rollback_state_hash=rows[0].evaluated_trial_state_hash,
    )
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as rollback_error:
        validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(
            reissue((wrong_rollback, *rows[1:])),
        )
    assert rollback_error.value.code == (
        "hip_fgmres_family_diagnostic_ir_v1_observation_invalid"
    )

    larger = rehash_row(
        rows[0],
        diagnostic_array_byte_count=rows[0].diagnostic_array_byte_count + 8,
    )
    smaller = rehash_row(
        rows[1],
        diagnostic_array_byte_count=rows[1].diagnostic_array_byte_count - 8,
    )
    with pytest.raises(HipFgmresModelFamilyDiagnosticIRV1Error) as byte_error:
        validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1(
            reissue((larger, smaller, rows[2])),
        )
    assert byte_error.value.code == (
        "hip_fgmres_family_diagnostic_ir_v1_observation_invalid"
    )


def test_composition_factory_ast_has_no_builder_solve_export_device_or_commit_call() -> (
    None
):
    tree = ast.parse(inspect.getsource(attest_hip_fgmres_model_family_diagnostic_ir_v1))
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
    assert "build_hip_fgmres_diagnostic_ir_v1" not in calls
    assert not any(
        token in call.lower()
        for call in calls
        for token in ("solve", "export", "device", "d2h", "commit_trial_state")
    )
