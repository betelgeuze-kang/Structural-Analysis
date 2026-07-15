from __future__ import annotations

import ast
import copy
from dataclasses import replace
import gc
import inspect
from types import SimpleNamespace
from typing import Any
import weakref

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_result_ir_v1 as aggregate_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_fixture_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_model_family_v1 as family_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_result_ir_v2 as bridge_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_fixture_registry_v1 import (
    load_hip_fgmres_all_converged_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_model_family_v1 import (
    attest_hip_fgmres_all_converged_model_family_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_result_ir_v1 import (
    HipFgmresAllConvergedResultIRV1Error,
    attest_hip_fgmres_all_converged_result_ir_v1,
    validate_hip_fgmres_all_converged_result_ir_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityResultV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v2 import (
    build_hip_fgmres_result_ir_v2,
)
from structural_analysis.engine_v2.contracts import result_ir_v2 as result_ir_module
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)

from tests.test_engine_v2_hip_fgmres_all_converged_model_family_v1 import (
    _controlled_cases,
)
from tests.test_engine_v2_hip_fgmres_result_ir_v2 import _capture, _hash


@pytest.fixture(scope="module")
def registry():
    return load_hip_fgmres_all_converged_fixture_registry_v1()


def _aligned_bridge_capture(slot, case, family_capture, family_row):
    capture = _capture(slot, cpu_result=slot.cpu_result)
    solution_x = capture.solution_x
    solution = np.frombuffer(solution_x, dtype="<f8")
    displacement = np.zeros(slot.execution_plan.dof_count, dtype="<f8")
    displacement[np.asarray(slot.execution_plan.free_dofs, dtype=np.int64)] = solution
    true_residual = np.asarray(
        -slot.execution_plan.residual(displacement)[
            np.asarray(slot.execution_plan.free_dofs, dtype=np.int64)
        ],
        dtype="<f8",
    ).tobytes(order="C")
    solution_hash = sha256_prefixed(solution_x)
    residual_hash = sha256_prefixed(true_residual)
    solve_record_hash = _hash(f"solve-record:{slot.slot_id}")

    receipt = capture.receipt
    receipt.case_id = case.receipt.case_id
    receipt.receipt_hash = case.receipt.receipt_hash
    bindings = receipt.bindings
    bindings.execution_plan_id = slot.execution_plan.plan_id
    bindings.execution_plan_hash = slot.execution_plan.plan_hash
    bindings.cpu_result_hash = slot.cpu_result.result_hash
    bindings.terminal_observation_receipt_hash = (
        family_row.terminal_observation_receipt_hash
    )
    bindings.completion_export_receipt_hash = family_row.completion_export_receipt_hash
    bindings.completion_export_payload_hash = family_row.completion_export_payload_hash
    bindings.device_identity_receipt_hash = family_row.device_identity_receipt_hash
    bindings.compiled_architecture = "gfx1030"
    bindings.runtime_architecture_base = "gfx1030"
    bindings.device_ordinal = family_row.device_ordinal
    bindings.device_uuid_bytes_hex = family_row.device_uuid_bytes_hex
    bindings.device_pci_bdf = family_row.device_pci_bdf

    observation = capture.observation_result.receipt
    observation.receipt_hash = family_row.terminal_observation_receipt_hash
    observation.bindings.solution_payload_sha256 = solution_hash
    observation.bindings.true_residual_payload_sha256 = residual_hash

    device = capture.device_identity_result.receipt
    device.receipt_hash = family_row.device_identity_receipt_hash
    device.device.selected_ordinal = family_row.device_ordinal
    device.device.uuid_bytes_hex = family_row.device_uuid_bytes_hex
    device.device.pci_bdf = family_row.device_pci_bdf

    export = capture.export_result.receipt
    export.receipt_hash = family_row.completion_export_receipt_hash
    export.payload_hash = family_row.completion_export_payload_hash
    export.buffers = (
        SimpleNamespace(role="solution_x", payload_sha256=solution_hash),
        SimpleNamespace(role="true_residual", payload_sha256=residual_hash),
        SimpleNamespace(role="solve_record", payload_sha256=solve_record_hash),
    )
    capture.export_result.payload_hash = family_row.completion_export_payload_hash
    published = capture.published_result
    published.true_residual = true_residual
    published.receipt_hash = family_row.completion_export_receipt_hash
    published.payload_hash = family_row.completion_export_payload_hash
    published.buffer_payload_hashes = (
        solution_hash,
        residual_hash,
        solve_record_hash,
    )
    return replace(
        capture,
        source_case_identity_token=family_capture.source_case_identity_token,
        authority=SimpleNamespace(snapshot=("all-converged", slot.slot_id)),
        authority_snapshot_hash=family_capture.authority_snapshot_hash,
        true_residual=true_residual,
    )


def _make_sources(monkeypatch: pytest.MonkeyPatch, registry):
    cases, family_captures = _controlled_cases(monkeypatch, registry)
    family = attest_hip_fgmres_all_converged_model_family_v1(cases)
    captures = {
        id(case): _aligned_bridge_capture(
            slot,
            case,
            family_captures[id(case)],
            family_row,
        )
        for slot, case, family_row in zip(
            registry.slots,
            family.case_results,
            family.receipt.observations,
            strict=True,
        )
    }

    def resolve(case: Any):
        try:
            return captures[id(case)]
        except KeyError as exc:
            raise AssertionError("foreign case capture requested") from exc

    monkeypatch.setattr(bridge_module, "_capture_live_authority", resolve)
    monkeypatch.setattr(
        aggregate_module,
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        lambda: registry,
    )
    bridges = tuple(
        build_hip_fgmres_result_ir_v2(
            case,
            result_id=f"Result.all-converged.{slot.slot_id}.v2",
        )
        for slot, case in zip(registry.slots, family.case_results, strict=True)
    )
    return family, bridges, captures


def test_all_converged_result_ir_canonicalizes_and_validates_after_close(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    result = attest_hip_fgmres_all_converged_result_ir_v1(
        family,
        tuple(reversed(bridges)),
    )

    assert result.result_ir_bridges == bridges
    totals = result.receipt.totals
    assert (
        totals.required_slot_count,
        totals.ready_result_ir_v2_count,
        totals.solution_ready_count,
        totals.not_issued_count,
        totals.diagnostic_ir_count,
        totals.unique_result_ir_bridge_count,
        totals.committed_state_count,
    ) == (10, 10, 10, 0, 0, 10, 10)
    assert (
        totals.package_global_dof_count,
        totals.package_element_count,
        totals.package_free_dof_count,
        totals.package_csr_nnz,
    ) == (168, 18, 103, 2304)
    assert totals.result_array_count == 60
    assert totals.result_array_byte_count == 6728
    assert totals.detached_raw_payload_byte_count == 1648
    assert (
        totals.upstream_completion_export_blocking_d2h_attempt_count,
        totals.upstream_completion_export_blocking_d2h_success_count,
        totals.upstream_completion_export_blocking_d2h_failure_count,
        totals.upstream_completion_export_byte_count,
    ) == (30, 30, 0, 4288)
    assert result.receipt.claims.exact_ten_result_ir_v2_ready is True
    assert result.receipt.claims.actual_hardware_execution_verified is False
    assert result.receipt.claims.hardware_gate_completed is False
    assert result.receipt.claims.commercial_ready is False

    monkeypatch.setattr(
        aggregate_module,
        "_capture_family_source",
        lambda _result: (_ for _ in ()).throw(AssertionError("live family replay")),
    )
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda _case: (_ for _ in ()).throw(AssertionError("live case replay")),
    )
    assert validate_hip_fgmres_all_converged_result_ir_result_v1(result) is result
    assert result.to_manifest()["receipt_hash"] == result.receipt.receipt_hash


def test_all_converged_result_ir_rejects_missing_foreign_and_unissued_clone(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    family, bridges, captures = _make_sources(monkeypatch, registry)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="bridge_set_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(family, bridges[:-1])
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="bridge_set_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(family, list(bridges))  # type: ignore[arg-type]
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="bridge_set_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(
            family,
            (bridges[0], *bridges[:-1]),
        )

    first_case = family.case_results[0]
    foreign_case = object.__new__(HipFgmresModelCaseParityResultV1)
    foreign_capture = replace(
        captures[id(first_case)],
        source_case_identity_token=object(),
    )
    original = bridge_module._capture_live_authority
    monkeypatch.setattr(
        bridge_module,
        "_capture_live_authority",
        lambda _case: foreign_capture,
    )
    foreign_bridge = build_hip_fgmres_result_ir_v2(
        foreign_case,
        result_id="Result.foreign-serial-clone.v2",
    )
    monkeypatch.setattr(bridge_module, "_capture_live_authority", original)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="bridge_live_case_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(
            family,
            (foreign_bridge, *bridges[1:]),
        )

    result = attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="issuance_unavailable",
    ):
        validate_hip_fgmres_all_converged_result_ir_result_v1(replace(result))


def test_all_converged_result_ir_rejects_bridge_clones_rehashes_and_transplants(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    first, second = bridges[:2]
    direct = type(first)(
        receipt=first.receipt,
        accepted_state=first.accepted_state,
        evaluated_trial_state=first.evaluated_trial_state,
        committed_state=first.committed_state,
        _source_execution_plan=first.source_execution_plan,
        _source_seal=first._source_seal,
    )
    plan_transplant = replace(
        first,
        _source_execution_plan=second.source_execution_plan,
    )
    provenance_transplant = replace(
        first,
        receipt=replace(
            first.receipt,
            source_provenance=second.receipt.source_provenance,
        ),
    )
    state_transplant = replace(first, accepted_state=second.accepted_state)
    candidates = (
        direct,
        replace(first),
        copy.copy(first),
        plan_transplant,
        provenance_transplant,
        state_transplant,
    )
    for candidate in candidates:
        with pytest.raises(
            HipFgmresAllConvergedResultIRV1Error,
            match="bridge_invalid",
        ):
            attest_hip_fgmres_all_converged_result_ir_v1(
                family,
                (candidate, *bridges[1:]),
            )
    with pytest.raises(TypeError, match="mappingproxy"):
        copy.deepcopy(first)

    forged_receipt = replace(
        first.receipt,
        result_id="Result.coherently-rehashed-aggregate-attack.v2",
        result_ir_hash=bridge_module._ZERO_HASH,
    )
    forged_receipt = replace(
        forged_receipt,
        result_ir_hash=result_ir_module._receipt_hash(forged_receipt.to_dict()),
    )
    seal_draft = replace(
        first._source_seal,
        result_ir_hash=forged_receipt.result_ir_hash,
        capture_hash=bridge_module._ZERO_HASH,
    )
    forged_seal = replace(
        seal_draft,
        capture_hash=canonical_hash(bridge_module._detached_seal_payload(seal_draft)),
    )
    coherently_rehashed = replace(
        first,
        receipt=forged_receipt,
        _source_seal=forged_seal,
    )
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="bridge_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(
            family,
            (coherently_rehashed, *bridges[1:]),
        )

    clone = replace(first)
    with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
        bridge_module._BRIDGE_RESULT_ISSUANCES[clone] = (
            bridge_module._BRIDGE_RESULT_ISSUANCES[second]
        )
    try:
        with pytest.raises(
            HipFgmresAllConvergedResultIRV1Error,
            match="bridge_invalid",
        ):
            attest_hip_fgmres_all_converged_result_ir_v1(
                family,
                (clone, *bridges[1:]),
            )
    finally:
        with bridge_module._BRIDGE_RESULT_ISSUANCE_LOCK:
            bridge_module._BRIDGE_RESULT_ISSUANCES.pop(clone, None)


@pytest.mark.parametrize("change_at", (2, 3))
def test_all_converged_result_ir_rejects_second_and_final_family_capture_race(
    monkeypatch: pytest.MonkeyPatch,
    registry,
    change_at: int,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    original = aggregate_module._capture_family_source
    stable = original(family)
    calls = 0

    def capture(_family, _registry_transaction=None):
        nonlocal calls
        calls += 1
        if calls == change_at:
            return replace(stable, family_identity_token=object())
        return stable

    monkeypatch.setattr(aggregate_module, "_capture_family_source", capture)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="family_changed",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)


def _rehash_aggregate_receipt(receipt):
    draft = replace(receipt, receipt_hash=aggregate_module._ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            aggregate_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _rehash_aggregate_row(row):
    draft = replace(row, aggregate_binding_hash=aggregate_module._ZERO_HASH)
    return replace(
        draft,
        aggregate_binding_hash=canonical_hash(
            aggregate_module._observation_payload(
                draft,
                include_binding_hash=False,
            )
        ),
    )


def _rehash_aggregate_observations(receipt, observations):
    draft = replace(receipt, observations=tuple(observations))
    attestation_id = canonical_hash(
        {
            "capability_profile": draft.capability_profile,
            "registry_hash": draft.bindings.registry_hash,
            "source_family_receipt_hash": draft.bindings.source_family_receipt_hash,
            "aggregate_binding_hashes": [
                row.aggregate_binding_hash for row in draft.observations
            ],
        }
    )
    return _rehash_aggregate_receipt(replace(draft, attestation_id=attestation_id))


def test_all_converged_result_ir_rejects_coherent_receipt_and_row_forgeries(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    result = attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)

    for false_claim in (
        "commercial_ready",
        "actual_hardware_execution_verified",
        "hardware_gate_completed",
    ):
        forged_claims = replace(result.receipt.claims, **{false_claim: True})
        claim_receipt = _rehash_aggregate_receipt(
            replace(result.receipt, claims=forged_claims)
        )
        with pytest.raises(
            HipFgmresAllConvergedResultIRV1Error,
            match="schema_invalid",
        ) as exc_info:
            aggregate_module.validate_hip_fgmres_all_converged_result_ir_receipt_v1(
                claim_receipt
            )
        assert exc_info.value.path == f"/claims/{false_claim}"

    rows = list(result.receipt.observations)
    rows[0] = _rehash_aggregate_row(
        replace(rows[0], result_array_byte_count=rows[0].result_array_byte_count + 8)
    )
    rows[1] = _rehash_aggregate_row(
        replace(rows[1], result_array_byte_count=rows[1].result_array_byte_count - 8)
    )
    redistributed = _rehash_aggregate_receipt(
        replace(result.receipt, observations=tuple(rows))
    )
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="observation_invalid",
    ):
        aggregate_module.validate_hip_fgmres_all_converged_result_ir_receipt_v1(
            redistributed
        )

    duplicate_case_rows = list(result.receipt.observations)
    duplicate_case_rows[1] = _rehash_aggregate_row(
        replace(
            duplicate_case_rows[1],
            case_id=duplicate_case_rows[0].case_id,
            case_receipt_hash=duplicate_case_rows[0].case_receipt_hash,
        )
    )
    coherent_case_duplicate = _rehash_aggregate_observations(
        result.receipt,
        duplicate_case_rows,
    )
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="duplicate_bridge_case",
    ) as exc_info:
        aggregate_module.validate_hip_fgmres_all_converged_result_ir_receipt_v1(
            coherent_case_duplicate
        )
    assert exc_info.value.path == "/bridges/1"

    duplicated_rows = list(result.receipt.observations)
    duplicated_rows[1] = duplicated_rows[0]
    schema_duplicate = _rehash_aggregate_receipt(
        replace(result.receipt, observations=tuple(duplicated_rows))
    )
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="schema_invalid",
    ):
        aggregate_module.validate_hip_fgmres_all_converged_result_ir_receipt_v1(
            schema_duplicate
        )

    schema_only_receipt = replace(result.receipt)
    assert (
        aggregate_module.validate_hip_fgmres_all_converged_result_ir_receipt_v1(
            schema_only_receipt
        )
        is schema_only_receipt
    )
    schema_only_result = replace(result, receipt=schema_only_receipt)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="issuance_unavailable",
    ):
        validate_hip_fgmres_all_converged_result_ir_result_v1(schema_only_result)

    second = attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
    with aggregate_module._ISSUANCE_LOCK:
        first_issuance = aggregate_module._ISSUANCES[result]
        second_issuance = aggregate_module._ISSUANCES[second]
        aggregate_module._ISSUANCES[result] = second_issuance
    try:
        with pytest.raises(
            HipFgmresAllConvergedResultIRV1Error,
            match="issuance_binding_mismatch",
        ):
            validate_hip_fgmres_all_converged_result_ir_result_v1(result)
    finally:
        with aggregate_module._ISSUANCE_LOCK:
            aggregate_module._ISSUANCES[result] = first_issuance


def test_all_converged_result_ir_module_has_no_direct_native_or_device_path() -> None:
    tree = ast.parse(inspect.getsource(aggregate_module))
    forbidden_exact = {
        "build_hip_fgmres_result_ir_v2",
        "build_result_ir_v2",
        "solve_cpu_fgmres_reference_v1",
        "solve",
        "export",
        "launch",
        "allocate",
        "synchronize",
        "copy_device_to_host",
        "__import__",
        "import_module",
        "eval",
        "exec",
    }
    forbidden_fragments = (
        "allocate",
        "device",
        "d2h",
        "enqueue",
        "export",
        "h2d",
        "hipmalloc",
        "hipmemcpy",
        "kernel",
        "launch",
        "native",
        "synchronize",
    )
    imported_names = {
        alias.name.rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_names = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    for name in imported_names | called_names:
        lowered = name.lower()
        assert name not in forbidden_exact
        assert not lowered.startswith(("build_", "solve_"))
        assert not any(fragment in lowered for fragment in forbidden_fragments)

    dynamic_getattrs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
    ]
    assert dynamic_getattrs
    assert all(
        len(node.args) == 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "self"
        and isinstance(node.args[1], ast.Name)
        and node.args[1].id == "name"
        for node in dynamic_getattrs
    )
    assert aggregate_module.__all__
    assert "_ISSUANCES" not in aggregate_module.__all__
    assert "_AggregateIssuanceV1" not in aggregate_module.__all__
    assert "_capture_family_source" not in aggregate_module.__all__
    assert "build_hip_fgmres_result_ir_v2" not in aggregate_module.__all__


def test_all_converged_result_ir_replay_counts_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    family_replays = 0
    detached_registry_replays = 0
    family_captures = 0
    fast_registry_checks = 0
    original_capture = aggregate_module._capture_family_source
    original_refresh = family_module._refresh_fixed_registry_replay_transaction_v1

    def load_family_registry():
        nonlocal family_replays
        family_replays += 1
        return registry

    def load_detached_registry():
        nonlocal detached_registry_replays
        detached_registry_replays += 1
        return registry

    def capture_family_source(family_result, registry_transaction=None):
        nonlocal family_captures
        family_captures += 1
        return original_capture(family_result, registry_transaction)

    def refresh_registry(transaction):
        nonlocal fast_registry_checks
        fast_registry_checks += 1
        return original_refresh(transaction)

    monkeypatch.setattr(
        family_module,
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        load_family_registry,
    )
    monkeypatch.setattr(
        aggregate_module,
        "load_hip_fgmres_all_converged_fixture_registry_v1",
        load_detached_registry,
    )
    monkeypatch.setattr(
        aggregate_module,
        "_capture_family_source",
        capture_family_source,
    )
    monkeypatch.setattr(
        family_module,
        "_refresh_fixed_registry_replay_transaction_v1",
        refresh_registry,
    )

    result = attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
    assert family_replays == 1
    assert detached_registry_replays == 0
    assert family_captures == 3
    assert fast_registry_checks == 3

    family_replays = 0
    detached_registry_replays = 0
    family_captures = 0
    fast_registry_checks = 0
    assert validate_hip_fgmres_all_converged_result_ir_result_v1(result) is result
    assert family_replays == 0
    assert detached_registry_replays == 1
    assert family_captures == 0
    assert fast_registry_checks == 0

    detached_registry_replays = 0
    assert (
        aggregate_module.validate_hip_fgmres_all_converged_result_ir_receipt_v1(
            result.receipt
        )
        is result.receipt
    )
    assert detached_registry_replays == 1


@pytest.mark.parametrize("resource_kind", ("registry", "model"))
@pytest.mark.parametrize("refresh_index", (1, 2), ids=("second", "final"))
def test_all_converged_result_ir_rejects_raw_drift_between_live_captures(
    monkeypatch: pytest.MonkeyPatch,
    registry,
    resource_kind: str,
    refresh_index: int,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    target = (
        registry_module._REGISTRY_RESOURCE
        if resource_kind == "registry"
        else registry.slots[0].model_resource
    )
    original_read = registry_module._read_fixed_resource
    target_reads = 0

    def read_resource(name):
        nonlocal target_reads
        raw = original_read(name)
        if name == target:
            target_reads += 1
            if target_reads == refresh_index:
                return raw + b"\n"
        return raw

    monkeypatch.setattr(registry_module, "_read_fixed_resource", read_resource)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="family_authority_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
    assert target_reads == refresh_index


@pytest.mark.parametrize("resource_kind", ("registry", "model"))
def test_all_converged_result_ir_rejects_raw_drift_after_final_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    registry,
    resource_kind: str,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)
    target = (
        registry_module._REGISTRY_RESOURCE
        if resource_kind == "registry"
        else registry.slots[0].model_resource
    )
    original_evaluate = aggregate_module._evaluate
    original_read = registry_module._read_fixed_resource
    evaluations = 0
    drift_active = False

    def evaluate(source, source_bridges):
        nonlocal evaluations, drift_active
        evaluated = original_evaluate(source, source_bridges)
        evaluations += 1
        if evaluations == 3:
            drift_active = True
        return evaluated

    def read_resource(name):
        raw = original_read(name)
        return raw + b"\n" if drift_active and name == target else raw

    monkeypatch.setattr(aggregate_module, "_evaluate", evaluate)
    monkeypatch.setattr(registry_module, "_read_fixed_resource", read_resource)
    with pytest.raises(
        HipFgmresAllConvergedResultIRV1Error,
        match="family_authority_invalid",
    ):
        attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
    assert evaluations == 3


def test_all_converged_result_ir_weak_issuance_is_collected_and_token_not_reused(
    monkeypatch: pytest.MonkeyPatch,
    registry,
) -> None:
    family, bridges, _ = _make_sources(monkeypatch, registry)

    def issue_once():
        result = attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
        with aggregate_module._ISSUANCE_LOCK:
            token = aggregate_module._ISSUANCES[result].mint
            size = len(aggregate_module._ISSUANCES)
        return weakref.ref(result), token, size

    reference, old_token, during = issue_once()
    gc.collect()
    assert reference() is None
    assert len(aggregate_module._ISSUANCES) < during

    replacement = attest_hip_fgmres_all_converged_result_ir_v1(family, bridges)
    with aggregate_module._ISSUANCE_LOCK:
        assert aggregate_module._ISSUANCES[replacement].mint is not old_token
