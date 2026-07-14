from __future__ import annotations

from dataclasses import replace
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_family_parity_v2 as family_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityResultV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2,
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2,
    HipFgmresModelFamilyParityV2Error,
    attest_hip_fgmres_model_family_coverage_v2,
    validate_hip_fgmres_model_family_parity_receipt_v2,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_family_parity_v2.schema.json"
)


@pytest.fixture(scope="module")
def registry():
    return load_hip_fgmres_fixture_registry_v1()


@pytest.fixture
def sealed_sources(monkeypatch: pytest.MonkeyPatch, registry):
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
    return registry


def _hash(label: str) -> str:
    return canonical_hash({"test_label": label})


def _rehash_receipt(receipt: Any, **changes: Any) -> Any:
    draft = replace(
        receipt,
        receipt_hash="sha256:" + "0" * 64,
        **changes,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            family_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _fake_case(
    registry: Any,
    slot_id: str,
    *,
    architecture: str = "gfx1030",
    label: str | None = None,
    uuid_hex: str | None = None,
    pci_bdf: str | None = None,
    fgmres_plan_hash: str | None = None,
) -> HipFgmresModelCaseParityResultV1:
    slot = registry.slot(slot_id)
    identity_label = label or f"{architecture}:{slot_id}"
    architecture_index = (
        HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2.index(
            architecture
        )
    )
    bindings = SimpleNamespace(
        model_ir_content_hash=slot.model.content_hash,
        execution_plan_hash=slot.execution_plan.plan_hash,
        fgmres_plan_hash=fgmres_plan_hash or slot.fgmres_plan.plan_hash,
        recurrence_plan_hash=slot.recurrence_plan.plan_hash,
        policy_hash=slot.policy.policy_hash,
        cpu_result_hash=slot.cpu_result.result_hash,
        runtime_architecture_base=architecture,
        compiled_architecture=architecture,
        device_ordinal=architecture_index,
        device_identity_receipt_hash=_hash(f"device-receipt:{identity_label}"),
        runtime_library_sha256=_hash(f"runtime:{architecture}"),
        device_uuid_bytes_hex=(
            uuid_hex
            or ("01" * 16 if architecture == "gfx1030" else "02" * 16)
        ),
        device_pci_bdf=(
            pci_bdf
            or ("0000:0b:00.0" if architecture == "gfx1030" else "0000:0c:00.0")
        ),
        kernel_identity_hash=_hash(f"kernel:{architecture}"),
        kernel_source_sha256=_hash("kernel-source"),
    )
    receipt = SimpleNamespace(
        bindings=bindings,
        case_id=_hash(f"case:{identity_label}"),
        receipt_hash=_hash(f"case-receipt:{identity_label}"),
    )
    return HipFgmresModelCaseParityResultV1(
        receipt=receipt,  # type: ignore[arg-type]
        _cpu_result=slot.cpu_result,
        _observation_result=SimpleNamespace(),  # type: ignore[arg-type]
        _device_identity_result=SimpleNamespace(),  # type: ignore[arg-type]
        _source_execution_plan=slot.execution_plan,
    )


def test_empty_v2_receipt_is_registry_bound_pending_and_nonpromoting(
    sealed_sources,
) -> None:
    result = attest_hip_fgmres_model_family_coverage_v2(())
    receipt = result.receipt

    assert tuple(
        inspect.signature(attest_hip_fgmres_model_family_coverage_v2).parameters
    ) == ("case_results",)
    assert receipt.status == "pending_primary_gfx1030_and_external_gfx1100"
    assert receipt.required_slot_ids == HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
    assert receipt.coverage.expected_matrix_cell_count == 20
    assert receipt.coverage.covered_matrix_cell_count == 0
    assert len(receipt.coverage.missing_cells) == 20
    assert receipt.claims.fixed_package_registry_replayed
    assert not receipt.claims.primary_gfx1030_fixed_suite_complete
    assert not receipt.claims.full_model_family_parity_verified
    assert not receipt.claims.multiarchitecture_parity_verified
    assert not receipt.claims.signed_evidence
    assert not receipt.claims.promotion_eligible
    assert validate_hip_fgmres_model_family_parity_receipt_v2(receipt) is receipt


def test_schema_is_strict_for_serialized_non_authoritative_receipt(
    sealed_sources,
) -> None:
    receipt = attest_hip_fgmres_model_family_coverage_v2(()).receipt.to_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(receipt))
    receipt["external_signed_receipts"] = []
    assert list(validator.iter_errors(receipt))


def test_one_exact_live_case_classifies_to_one_registry_cell(sealed_sources) -> None:
    case = _fake_case(sealed_sources, "frame_serial_later_column")
    receipt = attest_hip_fgmres_model_family_coverage_v2((case,)).receipt

    assert receipt.status == "partial_fixed_suite_hardware_observation"
    assert receipt.coverage.covered_matrix_cell_count == 1
    assert receipt.coverage.covered_cells == (
        "gfx1030:frame_serial_later_column",
    )
    assert receipt.observations[0].slot_id == "frame_serial_later_column"
    assert receipt.observations[0].runtime_architecture_base == "gfx1030"


def test_full_gfx1030_fixed_suite_is_bounded_primary_lane_only(
    sealed_sources,
) -> None:
    cases = tuple(
        _fake_case(sealed_sources, slot_id)
        for slot_id in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
    )
    receipt = attest_hip_fgmres_model_family_coverage_v2(cases).receipt

    assert receipt.status == (
        "primary_gfx1030_fixed_suite_complete_external_gfx1100_pending"
    )
    assert receipt.coverage.covered_matrix_cell_count == 10
    assert receipt.coverage.completed_architecture_bases == ("gfx1030",)
    assert receipt.claims.primary_gfx1030_fixed_suite_complete
    assert not receipt.claims.unsigned_fixed_suite_two_architecture_matrix_observed
    assert not receipt.claims.full_model_family_parity_verified
    assert not receipt.claims.multiarchitecture_parity_verified
    assert not receipt.claims.signed_evidence
    assert not receipt.promotion_eligible


def test_unsigned_live_twenty_cell_matrix_never_becomes_broad_or_signed_claim(
    sealed_sources,
) -> None:
    cases = tuple(
        _fake_case(sealed_sources, slot_id, architecture=architecture)
        for architecture in HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        for slot_id in HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V2
    )
    receipt = attest_hip_fgmres_model_family_coverage_v2(cases).receipt

    assert receipt.coverage.covered_matrix_cell_count == 20
    assert receipt.claims.unsigned_fixed_suite_two_architecture_matrix_observed
    assert not receipt.claims.full_model_family_parity_verified
    assert not receipt.claims.multiarchitecture_parity_verified
    assert not receipt.claims.signed_evidence
    assert not receipt.claims.promotion_eligible
    assert not receipt.promotion_eligible


def test_wrong_registered_plan_hash_is_fail_closed(sealed_sources) -> None:
    case = _fake_case(
        sealed_sources,
        "frame_single_axial",
        fgmres_plan_hash=_hash("forged-fgmres-plan"),
    )
    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        attest_hip_fgmres_model_family_coverage_v2((case,))
    assert error.value.code == (
        "hip_fgmres_model_family_v2_exact_slot_match_required"
    )


def test_duplicate_slot_architecture_cell_is_rejected(sealed_sources) -> None:
    first = _fake_case(sealed_sources, "frame_single_axial", label="first")
    second = _fake_case(sealed_sources, "frame_single_axial", label="second")
    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        attest_hip_fgmres_model_family_coverage_v2((first, second))
    assert error.value.code == "hip_fgmres_model_family_v2_duplicate_matrix_cell"


def test_detached_receipt_cannot_hide_duplicate_matrix_cell(sealed_sources) -> None:
    receipt = attest_hip_fgmres_model_family_coverage_v2(
        (_fake_case(sealed_sources, "frame_single_axial"),)
    ).receipt
    first = receipt.observations[0]
    case_receipt_hash = _hash("detached-duplicate-case-receipt")
    device_receipt_hash = _hash("detached-duplicate-device-receipt")
    second = replace(
        first,
        case_id=_hash("detached-duplicate-case"),
        case_receipt_hash=case_receipt_hash,
        device_identity_receipt_hash=device_receipt_hash,
        matrix_cell_id=canonical_hash(
            {
                "logical_case_key": first.logical_case_key,
                "runtime_architecture_base": first.runtime_architecture_base,
                "device_identity_receipt_hash": device_receipt_hash,
                "case_receipt_hash": case_receipt_hash,
            }
        ),
    )
    observations = (first, second)
    forged = _rehash_receipt(
        receipt,
        observations=observations,
        coverage=family_module._coverage(observations),
    )

    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        validate_hip_fgmres_model_family_parity_receipt_v2(forged)
    assert error.value.code == "hip_fgmres_model_family_v2_duplicate_matrix_cell"


def test_detached_receipt_is_bound_to_current_package_registry(
    sealed_sources,
) -> None:
    receipt = attest_hip_fgmres_model_family_coverage_v2(()).receipt
    forged = _rehash_receipt(
        receipt,
        registry_hash=_hash("forged-registry"),
    )

    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        validate_hip_fgmres_model_family_parity_receipt_v2(forged)
    assert error.value.code == (
        "hip_fgmres_model_family_v2_registry_identity_mismatch"
    )


@pytest.mark.parametrize(
    "field",
    ("slot_registration_hash", "case_fingerprint", "logical_case_key"),
)
def test_detached_receipt_rejects_forged_registry_or_derived_binding(
    sealed_sources,
    field: str,
) -> None:
    receipt = attest_hip_fgmres_model_family_coverage_v2(
        (_fake_case(sealed_sources, "frame_single_axial"),)
    ).receipt
    observation = receipt.observations[0]
    changed = {field: _hash(f"forged-{field}")}
    if field == "logical_case_key":
        changed["matrix_cell_id"] = _hash("forged-matrix-cell")
    forged_observation = replace(observation, **changed)
    forged = _rehash_receipt(
        receipt,
        observations=(forged_observation,),
    )

    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        validate_hip_fgmres_model_family_parity_receipt_v2(forged)
    assert error.value.code in {
        "hip_fgmres_model_family_v2_observation_registry_mismatch",
        "hip_fgmres_model_family_v2_observation_derived_binding_mismatch",
    }


def test_one_architecture_cannot_mix_device_or_kernel_identity(
    sealed_sources,
) -> None:
    first = _fake_case(sealed_sources, "frame_single_axial")
    second = _fake_case(
        sealed_sources,
        "frame_single_torsion",
        uuid_hex="03" * 16,
    )
    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        attest_hip_fgmres_model_family_coverage_v2((first, second))
    assert error.value.code == (
        "hip_fgmres_model_family_v2_architecture_device_inconsistent"
    )


@pytest.mark.parametrize(
    ("second_uuid", "second_pci"),
    (
        ("04" * 16, "0000:0e:00.0"),
        ("05" * 16, "0000:0d:00.0"),
    ),
)
def test_uuid_or_pci_identity_cannot_be_relabelled_across_isa_bases(
    sealed_sources,
    second_uuid: str,
    second_pci: str,
) -> None:
    uuid = "04" * 16
    pci = "0000:0d:00.0"
    first = _fake_case(
        sealed_sources,
        "frame_single_axial",
        architecture="gfx1030",
        uuid_hex=uuid,
        pci_bdf=pci,
    )
    second = _fake_case(
        sealed_sources,
        "frame_single_torsion",
        architecture="gfx1100",
        uuid_hex=second_uuid,
        pci_bdf=second_pci,
    )
    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        attest_hip_fgmres_model_family_coverage_v2((first, second))
    assert error.value.code == (
        "hip_fgmres_model_family_v2_cross_architecture_identity_conflict"
    )


def test_serialized_or_structural_stub_cannot_fill_live_case_cell(
    sealed_sources,
) -> None:
    with pytest.raises(HipFgmresModelFamilyParityV2Error) as error:
        attest_hip_fgmres_model_family_coverage_v2((SimpleNamespace(),))  # type: ignore[arg-type]
    assert error.value.code == "hip_fgmres_model_family_v2_case_type_invalid"
