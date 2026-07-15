from __future__ import annotations

from importlib.resources import files

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
import structural_analysis.engine_v2.backends.hip as hip_backend
import structural_analysis.engine_v2.evidence as evidence
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_key_enrollment_v1 as external_key_enrollment,
    fgmres_external_reviewer_root_bootstrap_v1 as external_reviewer_bootstrap,
    fgmres_external_release_identity_v1 as external_release_identity,
    fgmres_external_replay_ledger_v1 as external_replay_ledger,
    fgmres_external_replay_ledger_v2 as external_replay_ledger_v2,
    fgmres_external_signed_evidence_v2 as external_signed_evidence_v2,
    fgmres_external_trust_anchor_registry_v2 as external_trust_registry_v2,
    fgmres_iteration_host_transfer_audit_v1 as iteration_host_transfer_audit,
    fgmres_model_family_audited_parity_v2 as model_family_audited_parity,
    fgmres_model_family_host_transfer_audit_v1 as model_family_transfer_audit,
    fgmres_model_family_parity_v2 as model_family_v2,
    fgmres_model_family_result_ir_disposition_v1 as model_family_result_ir_disposition,
    fgmres_recurrence_launch_fence_audit_v1 as recurrence_launch_fence_audit,
)
from structural_analysis.engine_v2.evidence import (
    dependency_lock_v1,
    durable_replay_ledger_v1,
    source_artifact_v1,
    wheel_artifact_v1,
)


CASE_EXPORTS = (
    "HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1",
    "HipFgmresModelCaseParityReceiptV1",
    "HipFgmresModelCaseParityResultV1",
    "attest_hip_fgmres_model_case_parity_v1",
    "validate_hip_fgmres_model_case_parity_receipt_v1",
    "validate_hip_fgmres_model_case_parity_result_v1",
)
FAMILY_EXPORTS = (
    "HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V1",
    "HIP_FGMRES_MODEL_FAMILY_REQUIRED_SLOT_IDS_V1",
    "HipFgmresModelFamilyCaseDescriptorV1",
    "HipFgmresModelFamilyParityReceiptV1",
    "HipFgmresModelFamilyParityResultV1",
    "attest_hip_fgmres_model_family_coverage_v1",
    "derive_hip_fgmres_model_family_case_descriptor_v1",
    "validate_hip_fgmres_model_family_parity_receipt_v1",
    "validate_hip_fgmres_model_family_parity_result_v1",
)
EXTERNAL_EXPORTS = (
    "HIP_FGMRES_FIXTURE_REGISTRY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2",
    "HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V1",
    "HipFgmresExternalTrustAnchorRegistryResultV1",
    "HipFgmresExternalChallengeV1",
    "HipFgmresExternalReleaseBindingV1",
    "HipFgmresExternalSignedEvidenceReceiptV1",
    "load_hip_fgmres_external_trust_anchor_registry_v1",
    "compile_hip_fgmres_external_release_binding_v1",
    "issue_hip_fgmres_external_evidence_challenge_v1",
    "verify_hip_fgmres_external_signed_evidence_v1",
    "decode_hip_fgmres_detached_completion_payload_v1",
    "replay_hip_fgmres_detached_model_case_numerics_v1",
)
DEVICE_EXPORTS = (
    "HIP_DEVICE_IDENTITY_SCHEMA_VERSION_V1",
    "HipDeviceIdentityReceiptV1",
    "HipDeviceIdentityResultV1",
    "attest_hip_device_identity_v1",
    "normalize_hip_gcn_architecture_v1",
    "validate_hip_device_identity_receipt_v1",
    "validate_hip_device_identity_result_v1",
)
ARTIFACT_EVIDENCE_MODULES = (
    source_artifact_v1,
    wheel_artifact_v1,
    dependency_lock_v1,
    durable_replay_ledger_v1,
)
RELEASE_IDENTITY_EXPORTS = tuple(external_release_identity.__all__)
REPLAY_LEDGER_EXPORTS = tuple(external_replay_ledger.__all__)
KEY_ENROLLMENT_EXPORTS = tuple(external_key_enrollment.__all__)
REVIEWER_BOOTSTRAP_EXPORTS = tuple(external_reviewer_bootstrap.__all__)
TRUST_REGISTRY_V2_EXPORTS = tuple(external_trust_registry_v2.__all__)
SIGNED_EVIDENCE_V2_EXPORTS = tuple(external_signed_evidence_v2.__all__)
REPLAY_LEDGER_V2_EXPORTS = tuple(external_replay_ledger_v2.__all__)
ITERATION_HOST_TRANSFER_AUDIT_EXPORTS = tuple(iteration_host_transfer_audit.__all__)
RECURRENCE_LAUNCH_FENCE_AUDIT_EXPORTS = tuple(recurrence_launch_fence_audit.__all__)
MODEL_FAMILY_V2_EXPORTS = tuple(model_family_v2.__all__)
MODEL_FAMILY_TRANSFER_AUDIT_EXPORTS = tuple(model_family_transfer_audit.__all__)
MODEL_FAMILY_AUDITED_PARITY_EXPORTS = tuple(model_family_audited_parity.__all__)
MODEL_FAMILY_RESULT_IR_DISPOSITION_EXPORTS = tuple(
    model_family_result_ir_disposition.__all__
)


def test_parity_and_device_identity_surfaces_are_exported_from_engine_v2() -> None:
    for name in (*CASE_EXPORTS, *FAMILY_EXPORTS, *EXTERNAL_EXPORTS):
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(assembly_backend, name)
    for name in DEVICE_EXPORTS:
        assert name in hip_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(hip_backend, name)


def test_release_identity_surfaces_are_exported_from_engine_v2() -> None:
    for name in RELEASE_IDENTITY_EXPORTS:
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(assembly_backend, name) is getattr(
            external_release_identity, name
        )
        assert getattr(engine_v2, name) is getattr(external_release_identity, name)


def test_external_replay_ledger_surfaces_are_exported_from_engine_v2() -> None:
    for name in REPLAY_LEDGER_EXPORTS:
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(assembly_backend, name) is getattr(external_replay_ledger, name)
        assert getattr(engine_v2, name) is getattr(external_replay_ledger, name)


def test_external_signed_identity_v2_surfaces_are_exported_from_engine_v2() -> None:
    for module, names in (
        (external_key_enrollment, KEY_ENROLLMENT_EXPORTS),
        (external_reviewer_bootstrap, REVIEWER_BOOTSTRAP_EXPORTS),
        (external_trust_registry_v2, TRUST_REGISTRY_V2_EXPORTS),
        (external_signed_evidence_v2, SIGNED_EVIDENCE_V2_EXPORTS),
        (external_replay_ledger_v2, REPLAY_LEDGER_V2_EXPORTS),
    ):
        for name in names:
            assert name in assembly_backend.__all__
            assert name in engine_v2.__all__
            assert getattr(assembly_backend, name) is getattr(module, name)
            assert getattr(engine_v2, name) is getattr(module, name)


def test_iteration_host_transfer_audit_surfaces_are_exported_from_engine_v2() -> None:
    for module, names in (
        (iteration_host_transfer_audit, ITERATION_HOST_TRANSFER_AUDIT_EXPORTS),
        (recurrence_launch_fence_audit, RECURRENCE_LAUNCH_FENCE_AUDIT_EXPORTS),
        (model_family_v2, MODEL_FAMILY_V2_EXPORTS),
        (model_family_transfer_audit, MODEL_FAMILY_TRANSFER_AUDIT_EXPORTS),
        (model_family_audited_parity, MODEL_FAMILY_AUDITED_PARITY_EXPORTS),
        (
            model_family_result_ir_disposition,
            MODEL_FAMILY_RESULT_IR_DISPOSITION_EXPORTS,
        ),
    ):
        for name in names:
            assert name in assembly_backend.__all__
            assert name in engine_v2.__all__
            assert getattr(assembly_backend, name) is getattr(module, name)
            assert getattr(engine_v2, name) is getattr(module, name)
    assert "HipFgmresRtcOperationCounterV1" in assembly_backend.__all__
    assert "HipFgmresRtcOperationCounterV1" in engine_v2.__all__
    assert (
        engine_v2.HipFgmresRtcOperationCounterV1
        is assembly_backend.HipFgmresRtcOperationCounterV1
    )


def test_artifact_identity_surfaces_are_exported_from_evidence_package() -> None:
    for module in ARTIFACT_EVIDENCE_MODULES:
        for name in module.__all__:
            assert name in evidence.__all__
            assert getattr(evidence, name) is getattr(module, name)


def test_parity_and_device_identity_schemas_are_package_resources() -> None:
    schema_root = files("structural_analysis.schemas")
    for name in (
        "hip_device_identity_v1.schema.json",
        "hip_fgmres_model_case_parity_v1.schema.json",
        "hip_fgmres_model_family_parity_v1.schema.json",
        "hip_fgmres_fixture_registry_v1.schema.json",
        "hip_fgmres_model_family_parity_v2.schema.json",
        "hip_fgmres_external_trust_anchor_registry_v1.schema.json",
        "hip_fgmres_external_signed_evidence_v1.schema.json",
        "hip_fgmres_external_signed_evidence_receipt_v1.schema.json",
        "hip_fgmres_external_release_identity_v1.schema.json",
        "durable_replay_ledger_receipts_v1.schema.json",
        "hip_fgmres_external_replay_ledger_receipt_v1.schema.json",
        "hip_fgmres_external_signed_evidence_v2.schema.json",
        "hip_fgmres_external_signed_evidence_receipt_v2.schema.json",
        "hip_fgmres_external_replay_ledger_receipt_v2.schema.json",
        "hip_fgmres_external_key_enrollment_v1.schema.json",
        "hip_fgmres_external_trust_anchor_registry_v2.schema.json",
        "hip_fgmres_external_reviewer_root_bootstrap_v1.schema.json",
        "hip_fgmres_iteration_host_transfer_audit_v1.schema.json",
        "hip_fgmres_recurrence_launch_fence_audit_v1.schema.json",
        "hip_fgmres_model_family_host_transfer_audit_v1.schema.json",
        "hip_fgmres_model_family_audited_parity_v2.schema.json",
        "hip_fgmres_model_family_result_ir_disposition_v1.schema.json",
    ):
        resource = schema_root.joinpath(name)
        assert resource.is_file()
        assert resource.read_text(encoding="utf-8").startswith("{")

    trust_registry = files(
        "structural_analysis.engine_v2.assembly_backend.fixtures."
        "fgmres_external_trust_anchors_v1"
    ).joinpath("registry.v1.json")
    assert trust_registry.is_file()
    assert b'"keys": []' in trust_registry.read_bytes()

    trust_registry_v2 = files(
        "structural_analysis.engine_v2.assembly_backend.fixtures."
        "fgmres_external_trust_anchors_v2"
    ).joinpath("registry.v2.json")
    assert trust_registry_v2.is_file()
    assert b'"reviewer_authorities": []' in trust_registry_v2.read_bytes()

    reviewer_bootstrap = files(
        "structural_analysis.engine_v2.assembly_backend.fixtures."
        "fgmres_external_reviewer_root_bootstrap_v1"
    ).joinpath("status.v1.json")
    assert reviewer_bootstrap.is_file()
    assert (
        b'"status": "pending_independent_reviewer_root_material"'
        in reviewer_bootstrap.read_bytes()
    )


def test_public_all_lists_have_no_duplicates_or_missing_attributes() -> None:
    for module in (engine_v2, assembly_backend, hip_backend, evidence):
        assert len(module.__all__) == len(set(module.__all__))
        assert not [name for name in module.__all__ if not hasattr(module, name)]
