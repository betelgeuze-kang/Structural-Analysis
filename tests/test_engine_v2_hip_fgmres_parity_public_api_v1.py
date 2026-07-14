from __future__ import annotations

from importlib.resources import files

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
import structural_analysis.engine_v2.backends.hip as hip_backend


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
DEVICE_EXPORTS = (
    "HIP_DEVICE_IDENTITY_SCHEMA_VERSION_V1",
    "HipDeviceIdentityReceiptV1",
    "HipDeviceIdentityResultV1",
    "attest_hip_device_identity_v1",
    "normalize_hip_gcn_architecture_v1",
    "validate_hip_device_identity_receipt_v1",
    "validate_hip_device_identity_result_v1",
)


def test_parity_and_device_identity_surfaces_are_exported_from_engine_v2() -> None:
    for name in (*CASE_EXPORTS, *FAMILY_EXPORTS):
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(assembly_backend, name)
    for name in DEVICE_EXPORTS:
        assert name in hip_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(hip_backend, name)


def test_parity_and_device_identity_schemas_are_package_resources() -> None:
    schema_root = files("structural_analysis.schemas")
    for name in (
        "hip_device_identity_v1.schema.json",
        "hip_fgmres_model_case_parity_v1.schema.json",
        "hip_fgmres_model_family_parity_v1.schema.json",
    ):
        resource = schema_root.joinpath(name)
        assert resource.is_file()
        assert resource.read_text(encoding="utf-8").startswith("{")


def test_public_all_lists_have_no_duplicates_or_missing_attributes() -> None:
    for module in (engine_v2, assembly_backend, hip_backend):
        assert len(module.__all__) == len(set(module.__all__))
        assert not [name for name in module.__all__ if not hasattr(module, name)]
