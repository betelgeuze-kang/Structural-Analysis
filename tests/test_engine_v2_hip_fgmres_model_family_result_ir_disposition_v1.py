from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass, replace
import inspect
from types import SimpleNamespace
from typing import Any, Callable

from jsonschema import ValidationError
import numpy as np
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
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_result_ir_disposition_v1 as disposition_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_result_ir_v2 as bridge_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_audited_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2,
    attest_hip_fgmres_model_family_audited_parity_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v2 import (
    HipFgmresResultIRBridgeResultV2,
    HipFgmresResultIRV2Error,
    build_hip_fgmres_result_ir_v2,
    validate_hip_fgmres_result_ir_v2,
)
from structural_analysis.engine_v2.contracts._canonical import sha256_prefixed
from structural_analysis.engine_v2.contracts import result_ir_v2 as result_ir_module

from tests.test_engine_v2_hip_fgmres_model_family_audited_parity_v2 import (
    _sources,
)
from tests.test_engine_v2_hip_fgmres_result_ir_v2 import (
    _capture,
    _hash,
)


READY_SLOT_IDS = (
    "frame_single_axial",
    "frame_single_weak_axis_bending",
    "frame_single_strong_axis_bending",
    "frame_single_torsion",
    "frame_serial_later_column",
    "truss_single_axial",
    "recurrence_initial_or_early_terminal",
)
EXPECTED_NONCONVERGED_SLOT_IDS = (
    "frame_single_rotated_local_axis_bending",
    "recurrence_later_restart_partial_final_cycle",
    "recurrence_exact_full_final_cycle_guard",
)


@dataclass(slots=True)
class _SyntheticFamily:
    registry: Any
    audited_result: Any
    source_snapshot: Any
    cases_by_slot: dict[str, Any]
    captures_by_case_identity: dict[int, Any]
    ready_bridges: tuple[HipFgmresResultIRBridgeResultV2, ...]
    disposition_result: Any


def _setattr(namespace: Any, name: str, value: Any) -> None:
    object.__setattr__(namespace, name, value)


def _canonical_f64(values: Any) -> np.ndarray:
    result = np.asarray(values, dtype="<f8").copy(order="C")
    result[result == 0.0] = 0.0
    result.setflags(write=False)
    return result


def _align_capture(
    slot: Any,
    case: Any,
    row: Any,
    *,
    force_converged: bool = False,
) -> Any:
    """Build a GPU-free live-capture double aligned to one retained case row."""

    plan = slot.execution_plan
    cpu = slot.cpu_result
    if force_converged:
        solution = _canonical_f64(slot.direct_solution)
        displacement = np.zeros(plan.dof_count, dtype="<f8")
        displacement[np.asarray(plan.free_dofs, dtype=np.int64)] = solution
        exported_residual = _canonical_f64(
            -plan.residual(displacement)[np.asarray(plan.free_dofs, dtype=np.int64)]
        )
        cpu = replace(
            cpu,
            status="converged",
            termination_code="converged_happy_breakdown",
            final_residual_l2=float(np.linalg.norm(exported_residual)),
            final_residual_linf=(
                float(np.max(np.abs(exported_residual)))
                if exported_residual.size
                else 0.0
            ),
            scaled_true_residual=0.0,
            solver_tolerance_passed=True,
            authoritative_plan_tolerance_passed=True,
            reduced_solution=solution,
            true_residual=exported_residual,
            result_hash=_hash(f"forced-converged-cpu:{slot.slot_id}"),
        )
    else:
        solution = _canonical_f64(cpu.reduced_solution)
        exported_residual = _canonical_f64(cpu.true_residual)

    capture = _capture(slot, cpu_result=cpu)
    solution_x = solution.tobytes(order="C")
    true_residual = exported_residual.tobytes(order="C")
    solution_hash = sha256_prefixed(solution_x)
    residual_hash = sha256_prefixed(true_residual)
    terminal_hash = _hash(f"terminal:{slot.slot_id}")
    solve_record_hash = _hash(f"solve-record:{slot.slot_id}")

    receipt = capture.receipt
    receipt.actual_backend = "hip"
    receipt.case_id = case.receipt.case_id
    receipt.receipt_hash = case.receipt.receipt_hash
    receipt.claims = SimpleNamespace(result_ir_ready=False, solution_ready=False)
    receipt.dimensions.global_dof_count = plan.dof_count
    receipt.dimensions.free_dof_count = len(plan.free_dofs)
    bindings = receipt.bindings
    bindings.execution_plan_id = plan.plan_id
    bindings.execution_plan_hash = plan.plan_hash
    bindings.cpu_result_hash = cpu.result_hash
    bindings.terminal_observation_receipt_hash = terminal_hash
    bindings.completion_export_receipt_hash = row.completion_export_receipt_hash
    bindings.completion_export_payload_hash = row.completion_export_payload_hash
    bindings.device_identity_receipt_hash = row.device_identity_receipt_hash
    bindings.compiled_architecture = row.compiled_architecture
    bindings.runtime_architecture_base = row.runtime_architecture_base
    bindings.device_ordinal = row.device_ordinal
    bindings.device_uuid_bytes_hex = row.device_uuid_bytes_hex
    bindings.device_pci_bdf = row.device_pci_bdf

    observation = capture.observation_result.receipt
    observation.receipt_hash = terminal_hash
    observation.bindings.solution_payload_sha256 = solution_hash
    observation.bindings.true_residual_payload_sha256 = residual_hash

    device = capture.device_identity_result.receipt
    device.receipt_hash = row.device_identity_receipt_hash
    device.architecture.expected_compiled.normalized = row.compiled_architecture
    device.architecture.runtime.base = row.runtime_architecture_base
    device.device.selected_ordinal = row.device_ordinal
    device.device.uuid_bytes_hex = row.device_uuid_bytes_hex
    device.device.pci_bdf = row.device_pci_bdf

    export = capture.export_result.receipt
    export.receipt_hash = row.completion_export_receipt_hash
    export.payload_hash = row.completion_export_payload_hash
    export.dimensions.solution_byte_count = len(solution_x)
    export.dimensions.true_residual_byte_count = len(true_residual)
    export.buffers = (
        SimpleNamespace(role="solution_x", payload_sha256=solution_hash),
        SimpleNamespace(role="true_residual", payload_sha256=residual_hash),
        SimpleNamespace(role="solve_record", payload_sha256=solve_record_hash),
    )
    capture.export_result.payload_hash = row.completion_export_payload_hash

    published = capture.published_result
    published.solution_x = solution_x
    published.true_residual = true_residual
    published.receipt_hash = row.completion_export_receipt_hash
    published.payload_hash = row.completion_export_payload_hash
    published.buffer_payload_hashes = (
        solution_hash,
        residual_hash,
        solve_record_hash,
    )
    authority = SimpleNamespace(
        snapshot=(
            "synthetic-family-result-ir",
            slot.slot_id,
            row.case_receipt_hash,
            row.completion_export_payload_hash,
        )
    )
    return replace(
        capture,
        authority=authority,
        plan=plan,
        cpu_result=cpu,
        solution_x=solution_x,
        true_residual=true_residual,
        authority_snapshot_hash=_hash(f"authority-snapshot:{slot.slot_id}"),
    )


def _with_capture_resolver(
    captures: dict[int, Any],
    action: Callable[[], Any],
) -> Any:
    original = bridge_module._capture_live_authority

    def resolve(case: Any) -> Any:
        try:
            return captures[id(case)]
        except KeyError as exc:  # pragma: no cover - defensive test harness guard
            raise AssertionError("foreign model-case capture requested") from exc

    bridge_module._capture_live_authority = resolve
    try:
        return action()
    finally:
        bridge_module._capture_live_authority = original


def _enrich_case_authorities_before_audit(source: Any, registry: Any) -> None:
    """Complete test doubles before v0.2.42 captures their live snapshot."""

    family = source._family_result
    cases_by_hash = {case.receipt.receipt_hash: case for case in family._case_results}
    for source_row in source.receipt.observations:
        case = cases_by_hash[source_row.case_receipt_hash]
        slot = registry.slot(source_row.slot_id)
        bindings = case.receipt.bindings
        terminal_hash = _hash(f"terminal:{slot.slot_id}")
        solution_hash = sha256_prefixed(
            _canonical_f64(slot.cpu_result.reduced_solution).tobytes(order="C")
        )
        residual_hash = sha256_prefixed(
            _canonical_f64(slot.cpu_result.true_residual).tobytes(order="C")
        )
        bindings.terminal_observation_receipt_hash = terminal_hash
        case.receipt.actual_backend = "hip"
        case.receipt.vectors = (
            SimpleNamespace(
                name="solution_x",
                hip_or_candidate_sha256=solution_hash,
            ),
            SimpleNamespace(
                name="true_residual",
                hip_or_candidate_sha256=residual_hash,
            ),
            SimpleNamespace(
                name="true_residual_replay",
                hip_or_candidate_sha256=residual_hash,
            ),
        )
        case._observation_result.receipt = SimpleNamespace(
            receipt_hash=terminal_hash,
        )
        export_result = case._observation_result._source_export_result
        export_result.receipt = SimpleNamespace(
            receipt_hash=bindings.completion_export_receipt_hash,
            payload_hash=bindings.completion_export_payload_hash,
        )
        case._device_identity_result.receipt = SimpleNamespace(
            receipt_hash=bindings.device_identity_receipt_hash,
        )


def _make_family(registry: Any) -> _SyntheticFamily:
    source, ordinals = _sources(registry)
    _enrich_case_authorities_before_audit(source, registry)
    audited_result = attest_hip_fgmres_model_family_audited_parity_v2(
        source,
        tuple(reversed(ordinals)),
    )
    family = audited_result._transfer_composition_result._family_result
    cases_by_hash = {case.receipt.receipt_hash: case for case in family._case_results}
    rows_by_slot = {row.slot_id: row for row in audited_result.receipt.observations}
    cases_by_slot = {
        slot_id: cases_by_hash[rows_by_slot[slot_id].case_receipt_hash]
        for slot_id in HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
    }
    captures = {
        id(cases_by_slot[slot_id]): _align_capture(
            registry.slot(slot_id),
            cases_by_slot[slot_id],
            rows_by_slot[slot_id],
        )
        for slot_id in READY_SLOT_IDS
    }

    def build_ready() -> tuple[HipFgmresResultIRBridgeResultV2, ...]:
        return tuple(
            build_hip_fgmres_result_ir_v2(
                cases_by_slot[slot_id],
                result_id=f"Result.{slot_id}.v2",
            )
            for slot_id in READY_SLOT_IDS
        )

    ready_bridges = _with_capture_resolver(captures, build_ready)
    source_snapshots: list[Any] = []
    capture_live_source = disposition_module._capture_live_source

    def capture_and_retain(candidate: Any) -> Any:
        snapshot = capture_live_source(candidate)
        source_snapshots.append(snapshot)
        return snapshot

    disposition_module._capture_live_source = capture_and_retain
    try:
        disposition_result = _with_capture_resolver(
            captures,
            lambda: (
                disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
                    audited_result,
                    tuple(reversed(ready_bridges)),
                )
            ),
        )
    finally:
        disposition_module._capture_live_source = capture_live_source
    assert len(source_snapshots) == 3
    return _SyntheticFamily(
        registry=registry,
        audited_result=audited_result,
        source_snapshot=source_snapshots[-1],
        cases_by_slot=cases_by_slot,
        captures_by_case_identity=captures,
        ready_bridges=ready_bridges,
        disposition_result=disposition_result,
    )


def _forced_ready_bridge_for_excluded_slot(
    fixture: _SyntheticFamily,
    slot_id: str,
) -> HipFgmresResultIRBridgeResultV2:
    assert slot_id in EXPECTED_NONCONVERGED_SLOT_IDS
    row = next(
        row
        for row in fixture.audited_result.receipt.observations
        if row.slot_id == slot_id
    )
    case = fixture.cases_by_slot[slot_id]
    capture = _align_capture(
        fixture.registry.slot(slot_id),
        case,
        row,
        force_converged=True,
    )
    return _with_capture_resolver(
        {id(case): capture},
        lambda: build_hip_fgmres_result_ir_v2(
            case,
            result_id=f"Result.forced-ready.{slot_id}.v2",
        ),
    )


def _foreign_ready_bridge(
    fixture: _SyntheticFamily,
) -> HipFgmresResultIRBridgeResultV2:
    slot_id = READY_SLOT_IDS[0]
    row = next(
        row
        for row in fixture.audited_result.receipt.observations
        if row.slot_id == slot_id
    )
    case = fixture.cases_by_slot[slot_id]
    capture = _align_capture(fixture.registry.slot(slot_id), case, row)
    capture.receipt.case_id = "Case.foreign-result-ir-source.v1"
    capture.receipt.receipt_hash = _hash("foreign-case-receipt")
    foreign_case = object.__new__(type(case))
    return _with_capture_resolver(
        {id(foreign_case): capture},
        lambda: build_hip_fgmres_result_ir_v2(
            foreign_case,
            result_id="Result.foreign-family-source.v2",
        ),
    )


def _install_cached_source(
    monkeypatch: pytest.MonkeyPatch,
    fixture: _SyntheticFamily,
) -> None:
    def capture(candidate: Any) -> Any:
        if candidate is not fixture.audited_result:
            raise AssertionError("unexpected audited source")
        return fixture.source_snapshot

    monkeypatch.setattr(disposition_module, "_capture_live_source", capture)
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda case: fixture.captures_by_case_identity[id(case)],
    )


def _rehash_disposition_receipt(receipt: Any, **changes: Any) -> Any:
    draft = replace(
        receipt,
        receipt_hash=disposition_module._ZERO_HASH,
        **changes,
    )
    return replace(
        draft,
        receipt_hash=disposition_module.canonical_hash(
            disposition_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _coherently_rehashed_bridge_clone(
    result: HipFgmresResultIRBridgeResultV2,
) -> HipFgmresResultIRBridgeResultV2:
    forged_receipt = replace(
        result.receipt,
        result_id="Result.coherently-rehashed-family-clone.v2",
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
    return replace(
        result,
        receipt=forged_receipt,
        _source_seal=forged_seal,
    )


@pytest.fixture(scope="module")
def sealed_registry() -> Any:
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
    if hasattr(disposition_module, "load_hip_fgmres_fixture_registry_v1"):
        monkeypatch.setattr(
            disposition_module,
            "load_hip_fgmres_fixture_registry_v1",
            lambda: registry,
        )
    if hasattr(
        disposition_module,
        "validate_hip_fgmres_fixture_registry_result_v1",
    ):
        monkeypatch.setattr(
            disposition_module,
            "validate_hip_fgmres_fixture_registry_result_v1",
            lambda result: result,
        )

    yield registry
    monkeypatch.undo()


@pytest.fixture(scope="module")
def synthetic_family(sealed_registry: Any) -> _SyntheticFamily:
    return _make_family(sealed_registry)


@pytest.fixture(scope="module")
def foreign_family(sealed_registry: Any) -> _SyntheticFamily:
    return _make_family(sealed_registry)


def test_exact_ten_slot_disposition_is_canonical_bounded_and_replayable(
    synthetic_family: _SyntheticFamily,
) -> None:
    result = synthetic_family.disposition_result
    assert (
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
            result
        )
        is result
    )
    receipt = result.receipt
    assert tuple(row.slot_id for row in receipt.observations) == (
        HIP_FGMRES_MODEL_FAMILY_AUDITED_PARITY_REQUIRED_SLOT_IDS_V2
    )
    assert (
        tuple(
            row.slot_id
            for row in receipt.observations
            if type(row)
            is disposition_module.HipFgmresModelFamilyResultIRReadyObservationV1
        )
        == READY_SLOT_IDS
    )
    assert (
        tuple(
            row.slot_id
            for row in receipt.observations
            if type(row)
            is disposition_module.HipFgmresModelFamilyResultIRNotIssuedObservationV1
        )
        == EXPECTED_NONCONVERGED_SLOT_IDS
    )
    assert all(
        row.disposition == "ready_result_ir_v2"
        and row.result_array_count == 6
        and row.additional_device_operation_count == 0
        and row.additional_d2h_operation_count == 0
        and row.additional_solve_count == 0
        and row.additional_export_count == 0
        and row.fallback_count == 0
        for row in receipt.observations
        if type(row)
        is disposition_module.HipFgmresModelFamilyResultIRReadyObservationV1
    )
    assert all(
        row.disposition == "not_issued_nonconverged"
        and row.result_ir_absence_reason == "source_not_converged"
        and row.result_ir_materialized is False
        and row.solver_tolerance_passed is False
        and row.authoritative_plan_tolerance_passed is False
        for row in receipt.observations
        if type(row)
        is disposition_module.HipFgmresModelFamilyResultIRNotIssuedObservationV1
    )
    totals = receipt.totals
    assert totals.required_slot_count == 10
    assert totals.ready_result_ir_v2_count == 7
    assert totals.not_issued_nonconverged_count == 3
    assert totals.ready_result_array_count == 42
    assert totals.ready_result_array_byte_count == 3336
    assert totals.ready_detached_raw_payload_byte_count == 688
    assert totals.upstream_completion_export_blocking_d2h_attempt_count == 30
    assert totals.upstream_completion_export_blocking_d2h_success_count == 30
    assert totals.upstream_completion_export_blocking_d2h_failure_count == 0
    assert totals.upstream_completion_export_byte_count == 4408
    assert totals.result_ir_projection_additional_device_operation_count == 0
    assert totals.result_ir_projection_additional_d2h_operation_count == 0
    assert totals.result_ir_projection_additional_solve_count == 0
    assert totals.result_ir_projection_additional_export_count == 0
    assert totals.result_ir_projection_fallback_count == 0
    claims = receipt.claims
    assert claims.canonical_ten_slot_disposition_verified
    assert claims.seven_converged_result_ir_v2_verified
    assert claims.three_nonconverged_result_ir_v2_not_issued
    assert claims.post_close_detached_value_validation_supported
    assert not claims.registry_validation_cpu_reference_replay_zero_proven
    assert not claims.exact_ten_slot_result_ir_v2_ready
    assert not claims.all_ten_solution_ready
    assert not claims.nonconverged_state_committed
    assert not claims.performance_or_speedup_proven
    assert not claims.end_to_end_o_n_verified
    assert not claims.commercial_ready
    assert not claims.promotion_eligible

    canonical = _with_capture_resolver(
        synthetic_family.captures_by_case_identity,
        lambda: (
            disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
                synthetic_family.audited_result,
                synthetic_family.ready_bridges,
            )
        ),
    )
    assert canonical.receipt == receipt
    assert canonical.result_ir_bridges == synthetic_family.ready_bridges
    assert result.result_ir_bridges == synthetic_family.ready_bridges


@pytest.mark.parametrize("slot_id", EXPECTED_NONCONVERGED_SLOT_IDS)
def test_v2_bridge_rejects_each_registered_nonconverged_source(
    synthetic_family: _SyntheticFamily,
    slot_id: str,
) -> None:
    row = next(
        row
        for row in synthetic_family.audited_result.receipt.observations
        if row.slot_id == slot_id
    )
    case = synthetic_family.cases_by_slot[slot_id]
    capture = _align_capture(synthetic_family.registry.slot(slot_id), case, row)
    with pytest.raises(HipFgmresResultIRV2Error) as error:
        _with_capture_resolver(
            {id(case): capture},
            lambda: build_hip_fgmres_result_ir_v2(
                case,
                result_id=f"Result.rejected.{slot_id}.v2",
            ),
        )
    assert error.value.code == "hip_fgmres_result_ir_v2_cpu_not_converged"


@pytest.mark.parametrize("slot_id", EXPECTED_NONCONVERGED_SLOT_IDS)
def test_each_nonconverged_result_ir_injection_is_explicitly_forbidden(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
    slot_id: str,
) -> None:
    forced = _forced_ready_bridge_for_excluded_slot(synthetic_family, slot_id)
    assert validate_hip_fgmres_result_ir_v2(forced) is forced
    _install_cached_source(monkeypatch, synthetic_family)
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            synthetic_family.ready_bridges + (forced,),
        )
    assert error.value.code == (
        "hip_fgmres_family_result_ir_disposition_nonconverged_bridge_forbidden"
    )


@pytest.mark.parametrize(
    "invalid_bridges",
    (
        lambda rows: rows[:-1],
        lambda rows: rows[:-1] + (rows[0],),
        lambda rows: list(rows),
    ),
    ids=("missing", "duplicate_identity", "non_tuple"),
)
def test_missing_duplicate_and_non_tuple_bridge_sets_fail_closed(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
    invalid_bridges: Callable[[tuple[Any, ...]], Any],
) -> None:
    _install_cached_source(monkeypatch, synthetic_family)
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            invalid_bridges(synthetic_family.ready_bridges),
        )
    assert error.value.code == (
        "hip_fgmres_family_result_ir_disposition_bridge_set_invalid"
    )


def test_foreign_case_bridge_is_rejected_before_ready_slot_accounting(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign = _foreign_ready_bridge(synthetic_family)
    assert validate_hip_fgmres_result_ir_v2(foreign) is foreign
    _install_cached_source(monkeypatch, synthetic_family)
    bridges = (*synthetic_family.ready_bridges[:-1], foreign)
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            bridges,
        )
    assert error.value.code == (
        "hip_fgmres_family_result_ir_disposition_foreign_bridge"
    )


@pytest.mark.parametrize(
    "forge",
    (
        lambda result, fixture: replace(result),
        lambda result, fixture: replace(
            result,
            _source_execution_plan=fixture.registry.slot(
                "frame_single_weak_axis_bending"
            ).execution_plan,
        ),
        lambda result, fixture: replace(
            result,
            receipt=replace(
                result.receipt,
                source_provenance=replace(
                    result.receipt.source_provenance,
                    case_id="Case.forged.v1",
                ),
            ),
        ),
    ),
    ids=("exact_clone", "plan_transplant", "case_provenance"),
)
def test_bridge_clone_plan_and_case_provenance_forgery_fail_closed(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
    forge: Callable[[HipFgmresResultIRBridgeResultV2, _SyntheticFamily], Any],
) -> None:
    _install_cached_source(monkeypatch, synthetic_family)
    forged = forge(synthetic_family.ready_bridges[0], synthetic_family)
    bridges = (forged, *synthetic_family.ready_bridges[1:])
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            bridges,
        )
    assert error.value.code == (
        "hip_fgmres_family_result_ir_disposition_bridge_invalid"
    )


def test_exact_issued_bridge_plan_and_provenance_mutation_fail_closed(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cached_source(monkeypatch, synthetic_family)
    bridge = synthetic_family.ready_bridges[0]
    original_plan = bridge._source_execution_plan
    object.__setattr__(
        bridge,
        "_source_execution_plan",
        synthetic_family.registry.slot("frame_single_weak_axis_bending").execution_plan,
    )
    try:
        with pytest.raises(
            disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
        ) as plan_error:
            disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
                synthetic_family.audited_result,
                synthetic_family.ready_bridges,
            )
        assert plan_error.value.code == (
            "hip_fgmres_family_result_ir_disposition_bridge_invalid"
        )
    finally:
        object.__setattr__(bridge, "_source_execution_plan", original_plan)

    original_provenance = bridge.receipt.source_provenance
    object.__setattr__(
        bridge.receipt,
        "source_provenance",
        replace(
            original_provenance,
            case_id="Case.mutated-issued-bridge.v1",
            case_parity_receipt_hash=_hash("mutated-issued-case-receipt"),
        ),
    )
    try:
        with pytest.raises(
            disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
        ) as provenance_error:
            disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
                synthetic_family.audited_result,
                synthetic_family.ready_bridges,
            )
        assert provenance_error.value.code == (
            "hip_fgmres_family_result_ir_disposition_bridge_invalid"
        )
    finally:
        object.__setattr__(
            bridge.receipt,
            "source_provenance",
            original_provenance,
        )


def test_coherently_rehashed_bridge_clone_and_issuance_transplant_fail_closed(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cached_source(monkeypatch, synthetic_family)
    coherent = _coherently_rehashed_bridge_clone(synthetic_family.ready_bridges[0])
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as coherent_error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            (coherent, *synthetic_family.ready_bridges[1:]),
        )
    assert coherent_error.value.code == (
        "hip_fgmres_family_result_ir_disposition_bridge_invalid"
    )

    target = synthetic_family.ready_bridges[0]
    donor = synthetic_family.ready_bridges[1]
    with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
        target_issuance = bridge_module._BRIDGE_RESULT_ISSUANCES[target]
        bridge_module._BRIDGE_RESULT_ISSUANCES[target] = (
            bridge_module._BRIDGE_RESULT_ISSUANCES[donor]
        )
    try:
        with pytest.raises(
            disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
        ) as transplant_error:
            disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
                synthetic_family.audited_result,
                synthetic_family.ready_bridges,
            )
        assert transplant_error.value.code == (
            "hip_fgmres_family_result_ir_disposition_bridge_invalid"
        )
    finally:
        with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
            bridge_module._BRIDGE_RESULT_ISSUANCES[target] = target_issuance


def test_source_change_during_factory_is_detected_before_issuance(
    synthetic_family: _SyntheticFamily,
    foreign_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = iter(
        (
            synthetic_family.source_snapshot,
            synthetic_family.source_snapshot,
            foreign_family.source_snapshot,
        )
    )
    monkeypatch.setattr(
        disposition_module,
        "_capture_live_source",
        lambda _source: next(captures),
    )
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda case: synthetic_family.captures_by_case_identity[id(case)],
    )
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            synthetic_family.ready_bridges,
        )
    assert error.value.code == (
        "hip_fgmres_family_result_ir_disposition_source_changed"
    )


def test_serially_identical_cross_run_bridge_splice_is_rejected_by_live_identity(
    synthetic_family: _SyntheticFamily,
    foreign_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cached_source(monkeypatch, synthetic_family)
    local = synthetic_family.ready_bridges[0]
    foreign = foreign_family.ready_bridges[0]
    assert (
        foreign.receipt.source_provenance.case_parity_receipt_hash
        == local.receipt.source_provenance.case_parity_receipt_hash
    )
    assert (
        foreign.source_execution_plan.plan_hash == local.source_execution_plan.plan_hash
    )
    spliced = (foreign, *synthetic_family.ready_bridges[1:])
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as error:
        disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
            synthetic_family.audited_result,
            spliced,
        )
    assert error.value.code == (
        "hip_fgmres_family_result_ir_disposition_bridge_live_case_invalid"
    )


def test_result_clone_source_receipt_swap_and_issuance_transplant_fail_closed(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = synthetic_family.disposition_result
    exact_clone = replace(result)
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as clone_error:
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
            exact_clone
        )
    assert clone_error.value.code == (
        "hip_fgmres_family_result_ir_disposition_issuance_unavailable"
    )

    forged_bindings = replace(
        result.receipt.bindings,
        source_audited_receipt_hash=_hash("coherent-source-receipt-clone"),
    )
    forged_attestation = disposition_module.canonical_hash(
        {
            "capability_profile": result.receipt.capability_profile,
            "registry_hash": forged_bindings.registry_hash,
            "source_audited_receipt_hash": (
                forged_bindings.source_audited_receipt_hash
            ),
            "disposition_binding_hashes": [
                row.disposition_binding_hash for row in result.receipt.observations
            ],
        }
    )
    coherent_receipt = _rehash_disposition_receipt(
        result.receipt,
        bindings=forged_bindings,
        attestation_id=forged_attestation,
    )
    assert (
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(
            coherent_receipt
        )
        is coherent_receipt
    )
    coherent_clone = replace(result, receipt=coherent_receipt)
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as coherent_error:
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
            coherent_clone
        )
    assert coherent_error.value.code == (
        "hip_fgmres_family_result_ir_disposition_issuance_unavailable"
    )

    original_source = result._source_audited_receipt
    object.__setattr__(
        result,
        "_source_audited_receipt",
        replace(original_source),
    )
    try:
        with pytest.raises(
            disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
        ) as source_error:
            disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
                result
            )
        assert source_error.value.code == (
            "hip_fgmres_family_result_ir_disposition_issuance_binding_mismatch"
        )
    finally:
        object.__setattr__(result, "_source_audited_receipt", original_source)

    _install_cached_source(monkeypatch, synthetic_family)
    donor = disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1(
        synthetic_family.audited_result,
        synthetic_family.ready_bridges,
    )
    with disposition_module._ISSUANCE_LOCK:
        original_issuance = disposition_module._ISSUANCES[result]
        disposition_module._ISSUANCES[result] = disposition_module._ISSUANCES[donor]
    try:
        with pytest.raises(
            disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
        ) as transplant_error:
            disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
                result
            )
        assert transplant_error.value.code == (
            "hip_fgmres_family_result_ir_disposition_issuance_binding_mismatch"
        )
    finally:
        with disposition_module._ISSUANCE_LOCK:
            disposition_module._ISSUANCES[result] = original_issuance


def test_receipt_claim_flip_stale_hash_and_strict_schema_fail_closed(
    synthetic_family: _SyntheticFamily,
) -> None:
    receipt = synthetic_family.disposition_result.receipt
    promoted_claims = replace(
        receipt.claims,
        exact_ten_slot_result_ir_v2_ready=True,
    )
    promoted = _rehash_disposition_receipt(receipt, claims=promoted_claims)
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as claim_error:
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(
            promoted
        )
    assert claim_error.value.code == (
        "hip_fgmres_family_result_ir_disposition_schema_invalid"
    )

    stale = replace(receipt, receipt_hash=_hash("stale-family-disposition"))
    with pytest.raises(
        disposition_module.HipFgmresModelFamilyResultIRDispositionV1Error
    ) as hash_error:
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_receipt_v1(
            stale
        )
    assert hash_error.value.code == (
        "hip_fgmres_family_result_ir_disposition_receipt_hash_invalid"
    )

    payload = disposition_module._receipt_payload(receipt, include_hash=True)
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        disposition_module._schema_validator().validate(payload)


def test_json_schema_alone_rejects_noncanonical_slot_truth_tables(
    synthetic_family: _SyntheticFamily,
) -> None:
    payload = disposition_module._receipt_payload(
        synthetic_family.disposition_result.receipt,
        include_hash=True,
    )
    validator = disposition_module._schema_validator()
    validator.validate(payload)

    arbitrary_required_slot = deepcopy(payload)
    arbitrary_required_slot["bindings"]["required_slot_ids"][0] = (
        "arbitrary_unregistered_slot"
    )

    reordered_required_slots = deepcopy(payload)
    required_ids = reordered_required_slots["bindings"]["required_slot_ids"]
    required_ids[0], required_ids[1] = required_ids[1], required_ids[0]

    duplicate_observation_slot = deepcopy(payload)
    duplicate_observation_slot["observations"][1]["slot_id"] = (
        duplicate_observation_slot["observations"][0]["slot_id"]
    )

    reordered_observations = deepcopy(payload)
    observations = reordered_observations["observations"]
    observations[0], observations[1] = observations[1], observations[0]

    promoted_nonconverged = deepcopy(payload)
    forged_ready = deepcopy(promoted_nonconverged["observations"][0])
    forged_ready["slot_id"] = promoted_nonconverged["observations"][4]["slot_id"]
    promoted_nonconverged["observations"][4] = forged_ready

    ten_duplicate_ready = deepcopy(payload)
    ready_row = deepcopy(ten_duplicate_ready["observations"][0])
    ten_duplicate_ready["observations"] = [deepcopy(ready_row) for _ in range(10)]

    for invalid in (
        arbitrary_required_slot,
        reordered_required_slots,
        duplicate_observation_slot,
        reordered_observations,
        promoted_nonconverged,
        ten_duplicate_ready,
    ):
        with pytest.raises(ValidationError):
            validator.validate(invalid)


def test_detached_result_validation_never_replays_live_audited_contexts(
    synthetic_family: _SyntheticFamily,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = synthetic_family.disposition_result

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("detached validation must not replay live audited state")

    monkeypatch.setattr(
        disposition_module,
        "validate_hip_fgmres_model_family_audited_parity_result_v2",
        forbidden,
    )
    monkeypatch.setattr(disposition_module, "_capture_live_source", forbidden)
    assert (
        disposition_module.validate_hip_fgmres_model_family_result_ir_disposition_result_v1(
            result
        )
        is result
    )
    assert result.to_manifest() == result.receipt.to_dict()
    assert not hasattr(result, "_source_audited_result")
    assert result._source_audited_receipt is synthetic_family.audited_result.receipt


def test_disposition_factory_ast_has_no_solver_export_or_device_operations() -> None:
    factory = disposition_module.attest_hip_fgmres_model_family_result_ir_disposition_v1
    tree = ast.parse(inspect.getsource(factory))
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
    forbidden_calls = {
        "solve_cpu_fgmres_reference_v1",
        "solve_sparse_execution_plan_v2",
        "solve_linear_static",
        "build_hip_fgmres_result_ir_v2",
        "export_completion_buffers",
        "enqueue",
        "fence",
        "synchronize",
        "launch",
        "allocate",
        "hipMalloc",
        "hipMemcpy",
    }
    assert forbidden_calls.isdisjoint(calls)
    assert not any(
        token in call.lower()
        for call in calls
        for token in (
            "enqueue",
            "fence",
            "device_launch",
            "device_alloc",
            "memcpy",
        )
    )

    module_tree = ast.parse(inspect.getsource(disposition_module))
    imported_leaves = {
        node.module.rsplit(".", 1)[-1]
        for node in ast.walk(module_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported_leaves.isdisjoint(
        {
            "cpu_fgmres",
            "fgmres_completion_export_v1",
            "fgmres_rtc_v2",
            "native",
            "linear_static",
            "sparse_linear_static",
        }
    )
