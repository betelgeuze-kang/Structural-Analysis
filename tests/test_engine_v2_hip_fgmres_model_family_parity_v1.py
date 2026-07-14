from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_parity_v1 as family_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityResultV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v1 import (
    HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V1,
    HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V1,
    HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_ID_V1,
    HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_SCOPE_V1,
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1,
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1,
    HipFgmresModelFamilyParityV1Error,
    attest_hip_fgmres_model_family_coverage_v1,
    derive_hip_fgmres_model_family_case_descriptor_v1,
    validate_hip_fgmres_model_family_parity_receipt_v1,
    validate_hip_fgmres_model_family_parity_result_v1,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.model_ir import parse_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_family_parity_v1.schema.json"
)
_ZERO_HASH = "sha256:" + "0" * 64


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _plan(load_pattern_id: str = "LC_AXIAL") -> Any:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    model = parse_model_ir_v2(payload)
    return compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    )


def _fake_exact_case(
    plan: Any,
    *,
    label: str,
    runtime_architecture_base: str = "gfx1030",
    compiled_architecture: str | None = None,
    device_ordinal: int = 0,
    uuid_hex: str = "0102030405060708090a0b0c0d0e0f10",
    pci_bdf: str = "0000:0b:00.0",
) -> HipFgmresModelCaseParityResultV1:
    bindings = SimpleNamespace(
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        symbolic_reuse_hash=plan.symbolic_reuse_hash,
        partition_hash=plan.partition_hash,
        policy_hash=_hash("policy:fixed"),
        cpu_result_hash=_hash(f"cpu:{plan.plan_hash}"),
        runtime_architecture_base=runtime_architecture_base,
        compiled_architecture=(compiled_architecture or runtime_architecture_base),
        device_ordinal=device_ordinal,
        device_identity_receipt_hash=_hash(f"device:{label}"),
        device_uuid_bytes_hex=uuid_hex,
        device_pci_bdf=pci_bdf,
    )
    receipt = SimpleNamespace(
        case_id=_hash(f"case:{label}"),
        receipt_hash=_hash(f"receipt:{label}"),
        bindings=bindings,
    )
    return HipFgmresModelCaseParityResultV1(
        receipt=receipt,  # type: ignore[arg-type]
        _cpu_result=SimpleNamespace(  # type: ignore[arg-type]
            status="converged",
            termination_code="converged_happy_breakdown",
        ),
        _observation_result=SimpleNamespace(),  # type: ignore[arg-type]
        _device_identity_result=SimpleNamespace(),  # type: ignore[arg-type]
        _source_execution_plan=plan,
    )


def _accept_exact_cases(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    def _validate(case: Any) -> Any:
        calls.append(case)
        return case

    monkeypatch.setattr(
        family_module,
        "validate_hip_fgmres_model_case_parity_result_v1",
        _validate,
    )
    monkeypatch.setattr(
        family_module,
        "validate_hip_fgmres_model_case_parity_receipt_v1",
        lambda receipt: receipt,
    )
    return calls


def _coherently_rehash(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            family_module._receipt_payload(draft, include_hash=False)
        ),
    )


def test_empty_package_suite_is_strict_honest_pending_and_nonpromoting() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    result = attest_hip_fgmres_model_family_coverage_v1(())
    receipt = result.receipt

    assert receipt.schema_version == HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V1
    assert (
        receipt.capability_profile
        == HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V1
    )
    assert receipt.evidence_scope == HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V1
    assert receipt.status == "pending_model_cases_and_external_architecture"
    assert receipt.suite.suite_id == HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_ID_V1
    assert receipt.suite.suite_scope == HIP_FGMRES_MODEL_FAMILY_PARITY_SUITE_SCOPE_V1
    assert (
        receipt.suite.required_architecture_bases
        == HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1
    )
    assert (
        receipt.suite.required_slot_ids == HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1
    )
    assert receipt.suite.registered_slot_ids == ()
    assert not receipt.suite.caller_override_allowed
    assert receipt.coverage.validated_input_case_count == 0
    assert receipt.coverage.registered_slot_definition_count == 0
    assert receipt.coverage.expected_matrix_cell_count == 20
    assert receipt.coverage.covered_matrix_cell_count == 0
    assert len(receipt.coverage.missing_cells) == 20
    assert receipt.coverage.incomplete_architecture_bases == ("gfx1030", "gfx1100")
    assert not receipt.claims.fixed_suite_slot_registration_complete
    assert not receipt.claims.fixed_suite_matrix_complete
    assert not receipt.claims.full_model_family_parity_verified
    assert not receipt.claims.multi_architecture_parity_verified
    assert not receipt.claims.serialized_receipt_authoritative
    assert not receipt.claims.unsigned_external_evidence_counted
    assert not receipt.claims.iteration_host_copy_zero_proven
    assert not receipt.claims.result_ir_ready
    assert not receipt.claims.performance_or_speedup_proven
    assert not receipt.claims.signed_evidence
    assert not receipt.claims.commercial_ready
    assert not receipt.promotion_eligible
    assert validate_hip_fgmres_model_family_parity_result_v1(result) is result
    assert validate_hip_fgmres_model_family_parity_receipt_v1(receipt) is receipt
    assert not list(validator.iter_errors(receipt.to_dict()))

    extra = receipt.to_dict()
    extra["caller_family_label"] = "frame_single_axial"
    assert list(validator.iter_errors(extra))


def test_api_has_no_caller_label_suite_or_architecture_override() -> None:
    signature = inspect.signature(attest_hip_fgmres_model_family_coverage_v1)
    assert tuple(signature.parameters) == ("case_results",)
    assert tuple(
        inspect.signature(derive_hip_fgmres_model_family_case_descriptor_v1).parameters
    ) == ("case_result",)

    with pytest.raises(HipFgmresModelFamilyParityV1Error) as list_error:
        attest_hip_fgmres_model_family_coverage_v1([])  # type: ignore[arg-type]
    assert list_error.value.code == (
        "hip_fgmres_model_family_case_results_container_invalid"
    )
    with pytest.raises(HipFgmresModelFamilyParityV1Error) as type_error:
        attest_hip_fgmres_model_family_coverage_v1((SimpleNamespace(),))  # type: ignore[arg-type]
    assert type_error.value.code == "hip_fgmres_model_family_case_result_type_invalid"


def test_exact_case_is_replayed_descriptor_derived_and_left_unregistered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _accept_exact_cases(monkeypatch)
    plan = _plan()
    case = _fake_exact_case(
        plan,
        label="gfx1030-xnack",
        compiled_architecture="gfx1030:xnack-",
    )

    descriptor = derive_hip_fgmres_model_family_case_descriptor_v1(case)
    result = attest_hip_fgmres_model_family_coverage_v1((case,))
    receipt = result.receipt

    assert len(calls) >= 6
    assert descriptor.execution_plan_hash == plan.plan_hash
    assert descriptor.model_ir_content_hash == plan.model_ir_content_hash
    assert descriptor.element_count == plan.element_count
    assert descriptor.global_dof_count == plan.dof_count
    assert descriptor.free_dof_count == plan.array("free_dofs").size
    assert descriptor.reduced_csr_nnz == plan.reduced_nnz
    assert sum(row.element_count for row in descriptor.element_signatures) == 1
    assert tuple(row.name for row in descriptor.metadata_buffer_bindings) == (
        "node_coordinates_m",
        "element_connectivity",
        "element_type",
        "element_formulation_code",
        "element_material_index",
        "element_section_index",
        "material_law_code",
        "section_family_code",
        "element_local_axis_rotation_rad",
        "element_offsets_m",
        "element_release_mask",
        "support_mask",
        "prescribed_values_si",
        "load_vector_si",
    )
    assert receipt.coverage.validated_input_case_count == 1
    assert receipt.coverage.unregistered_input_case_count == 1
    assert receipt.coverage.registered_input_case_count == 0
    assert receipt.coverage.observed_architecture_bases == ("gfx1030",)
    assert receipt.coverage.completed_architecture_bases == ()
    observed = receipt.observed_cases[0]
    assert observed.compiled_architecture == "gfx1030:xnack-"
    assert observed.runtime_architecture_base == "gfx1030"
    assert observed.registration_status == "unregistered_case"
    assert observed.slot_id is None
    assert observed.logical_case_key is None
    assert observed.matrix_cell_id is None
    assert observed.descriptor == descriptor
    assert receipt.status == "pending_model_cases_and_external_architecture"
    assert (
        validate_hip_fgmres_model_family_parity_result_v1(
            result,
            expected_case_results=(case,),
        )
        is result
    )


def test_descriptor_changes_with_authoritative_load_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_exact_cases(monkeypatch)
    axial_plan = _plan("LC_AXIAL")
    weak_plan = _plan("LC_WEAK")
    axial = derive_hip_fgmres_model_family_case_descriptor_v1(
        _fake_exact_case(axial_plan, label="axial")
    )
    weak = derive_hip_fgmres_model_family_case_descriptor_v1(
        _fake_exact_case(weak_plan, label="weak")
    )

    assert axial.descriptor_hash != weak.descriptor_hash
    assert axial.execution_plan_hash != weak.execution_plan_hash
    axial_load = next(
        row for row in axial.metadata_buffer_bindings if row.name == "load_vector_si"
    )
    weak_load = next(
        row for row in weak.metadata_buffer_bindings if row.name == "load_vector_si"
    )
    assert axial_load.content_hash != weak_load.content_hash
    assert axial.load_nonzero_component_mask != weak.load_nonzero_component_mask


def test_architecture_coverage_uses_base_not_suffix_uuid_or_ordinal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_exact_cases(monkeypatch)
    plan = _plan()
    first = _fake_exact_case(
        plan,
        label="device-a",
        compiled_architecture="gfx1030:xnack-:sramecc+",
        device_ordinal=0,
        uuid_hex="0102030405060708090a0b0c0d0e0f10",
        pci_bdf="0000:0b:00.0",
    )
    second = _fake_exact_case(
        plan,
        label="device-b",
        compiled_architecture="gfx1030:sramecc+:xnack-",
        device_ordinal=1,
        uuid_hex="1112131415161718191a1b1c1d1e1f20",
        pci_bdf="0000:0c:00.0",
    )

    receipt = attest_hip_fgmres_model_family_coverage_v1((first, second)).receipt

    assert receipt.coverage.validated_input_case_count == 2
    assert receipt.coverage.observed_architecture_bases == ("gfx1030",)
    assert {row.runtime_architecture_base for row in receipt.observed_cases} == {
        "gfx1030"
    }
    assert {row.compiled_architecture for row in receipt.observed_cases} == {
        "gfx1030:sramecc+:xnack-"
    }
    assert not receipt.claims.multi_architecture_parity_verified
    assert receipt.status == "pending_model_cases_and_external_architecture"


def test_nonrequired_architecture_and_exact_duplicate_input_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_exact_cases(monkeypatch)
    plan = _plan()
    unsupported = _fake_exact_case(
        plan,
        label="gfx90a",
        runtime_architecture_base="gfx90a",
    )
    with pytest.raises(HipFgmresModelFamilyParityV1Error) as architecture_error:
        attest_hip_fgmres_model_family_coverage_v1((unsupported,))
    assert architecture_error.value.code == (
        "hip_fgmres_model_family_architecture_not_in_fixed_suite"
    )

    case = _fake_exact_case(plan, label="same")
    with pytest.raises(HipFgmresModelFamilyParityV1Error) as duplicate_error:
        attest_hip_fgmres_model_family_coverage_v1((case, case))
    assert duplicate_error.value.code == "hip_fgmres_model_family_duplicate_input_case"


@pytest.mark.parametrize(
    ("second_uuid", "second_pci_bdf"),
    (
        ("0102030405060708090a0b0c0d0e0f10", "0000:0c:00.0"),
        ("1112131415161718191a1b1c1d1e1f20", "0000:0b:00.0"),
    ),
)
def test_same_device_identity_cannot_claim_different_architecture_bases(
    monkeypatch: pytest.MonkeyPatch,
    second_uuid: str,
    second_pci_bdf: str,
) -> None:
    _accept_exact_cases(monkeypatch)
    plan = _plan()
    first = _fake_exact_case(plan, label="identity-gfx1030")
    second = _fake_exact_case(
        plan,
        label="identity-gfx1100",
        runtime_architecture_base="gfx1100",
        uuid_hex=second_uuid,
        pci_bdf=second_pci_bdf,
    )

    with pytest.raises(HipFgmresModelFamilyParityV1Error) as error:
        attest_hip_fgmres_model_family_coverage_v1((first, second))
    assert error.value.code == (
        "hip_fgmres_model_family_device_architecture_identity_conflict"
    )


def test_observation_is_built_only_from_detached_validated_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_exact_cases(monkeypatch)
    plan = _plan()
    case = _fake_exact_case(plan, label="snapshot-original")
    original_receipt = case.receipt
    forged_receipt = SimpleNamespace(
        case_id=_hash("case:snapshot-forged"),
        receipt_hash=_hash("receipt:snapshot-forged"),
        bindings=original_receipt.bindings,
    )
    original_observe = family_module._observe_case

    def _mutate_live_case_while_observing(
        receipt_snapshot: Any,
        descriptor: Any,
        *,
        cpu_status: str,
        cpu_termination_code: str,
        path: str,
    ) -> Any:
        assert receipt_snapshot is not case.receipt
        object.__setattr__(case, "receipt", forged_receipt)
        try:
            return original_observe(
                receipt_snapshot,
                descriptor,
                cpu_status=cpu_status,
                cpu_termination_code=cpu_termination_code,
                path=path,
            )
        finally:
            object.__setattr__(case, "receipt", original_receipt)

    monkeypatch.setattr(
        family_module,
        "_observe_case",
        _mutate_live_case_while_observing,
    )

    receipt = attest_hip_fgmres_model_family_coverage_v1((case,)).receipt

    assert receipt.observed_cases[0].case_id == original_receipt.case_id
    assert receipt.observed_cases[0].case_receipt_hash == original_receipt.receipt_hash


def test_duplicate_registered_logical_slot_and_base_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_exact_cases(monkeypatch)
    plan = _plan()
    first = _fake_exact_case(plan, label="registered-a")
    second = _fake_exact_case(
        plan,
        label="registered-b",
        device_ordinal=1,
        uuid_hex="1112131415161718191a1b1c1d1e1f20",
        pci_bdf="0000:0c:00.0",
    )
    descriptor = derive_hip_fgmres_model_family_case_descriptor_v1(first)
    first_slot = replace(
        family_module._FIXED_SUITE_SLOTS_V1[0],
        expected_descriptor_hash=descriptor.descriptor_hash,
        expected_model_ir_content_hash=descriptor.model_ir_content_hash,
        expected_execution_plan_hash=descriptor.execution_plan_hash,
        expected_policy_hash=first.receipt.bindings.policy_hash,
        expected_cpu_result_hash=first.receipt.bindings.cpu_result_hash,
        expected_cpu_status="converged",
        expected_cpu_termination_code="converged_happy_breakdown",
    )
    monkeypatch.setattr(
        family_module,
        "_FIXED_SUITE_SLOTS_V1",
        (first_slot, *family_module._FIXED_SUITE_SLOTS_V1[1:]),
    )

    with pytest.raises(HipFgmresModelFamilyParityV1Error) as error:
        attest_hip_fgmres_model_family_coverage_v1((first, second))
    assert error.value.code == "hip_fgmres_model_family_duplicate_matrix_cell"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    (
        (
            lambda receipt: _coherently_rehash(
                receipt,
                status="fixed_suite_multiarchitecture_parity_verified_non_promoting",
            ),
            "hip_fgmres_model_family_schema_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                claims=replace(receipt.claims, signed_evidence=True),
            ),
            "hip_fgmres_model_family_schema_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                claims=replace(receipt.claims, promotion_eligible=True),
            ),
            "hip_fgmres_model_family_schema_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                coverage=replace(
                    receipt.coverage,
                    validated_input_case_count=False,
                ),
            ),
            "hip_fgmres_model_family_coverage_count_type_invalid",
        ),
    ),
)
def test_coherently_rehashed_broad_claims_and_type_confusion_fail(
    mutate: Any,
    expected_code: str,
) -> None:
    receipt = attest_hip_fgmres_model_family_coverage_v1(()).receipt
    forged = mutate(receipt)

    with pytest.raises(HipFgmresModelFamilyParityV1Error) as error:
        validate_hip_fgmres_model_family_parity_receipt_v1(forged)
    assert error.value.code == expected_code


def test_receipt_hash_and_live_source_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _accept_exact_cases(monkeypatch)
    axial_plan = _plan("LC_AXIAL")
    weak_plan = _plan("LC_WEAK")
    case = _fake_exact_case(axial_plan, label="drift")
    result = attest_hip_fgmres_model_family_coverage_v1((case,))

    with pytest.raises(HipFgmresModelFamilyParityV1Error) as hash_error:
        validate_hip_fgmres_model_family_parity_receipt_v1(
            replace(result.receipt, receipt_hash=_ZERO_HASH)
        )
    assert hash_error.value.code == "hip_fgmres_model_family_receipt_hash_invalid"

    duplicated = _coherently_rehash(
        result.receipt,
        observed_cases=(
            result.receipt.observed_cases[0],
            result.receipt.observed_cases[0],
        ),
    )
    with pytest.raises(HipFgmresModelFamilyParityV1Error) as duplicate_error:
        validate_hip_fgmres_model_family_parity_receipt_v1(duplicated)
    assert duplicate_error.value.code == "hip_fgmres_model_family_duplicate_input_case"

    object.__setattr__(case, "_source_execution_plan", weak_plan)
    with pytest.raises(HipFgmresModelFamilyParityV1Error) as drift_error:
        validate_hip_fgmres_model_family_parity_result_v1(result)
    assert drift_error.value.code in {
        "hip_fgmres_model_family_case_plan_binding_mismatch",
        "hip_fgmres_model_family_plan_identity_changed",
        "hip_fgmres_model_family_result_replay_mismatch",
    }


def test_serialized_receipt_is_structural_only_and_cannot_replace_live_result() -> None:
    result = attest_hip_fgmres_model_family_coverage_v1(())
    receipt = result.receipt

    assert validate_hip_fgmres_model_family_parity_receipt_v1(receipt) is receipt
    assert receipt.claims.serialized_receipt_authoritative is False
    assert receipt.claims.unsigned_external_evidence_counted is False
    assert receipt.claims.signed_evidence is False
    with pytest.raises(HipFgmresModelFamilyParityV1Error) as error:
        attest_hip_fgmres_model_family_coverage_v1((receipt,))  # type: ignore[arg-type]
    assert error.value.code == "hip_fgmres_model_family_case_result_type_invalid"
