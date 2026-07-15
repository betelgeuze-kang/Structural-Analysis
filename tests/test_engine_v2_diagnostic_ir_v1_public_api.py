from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import structural_analysis.engine_v2 as engine_v2  # noqa: E402
import structural_analysis.engine_v2.assembly_backend as assembly_backend  # noqa: E402
import structural_analysis.engine_v2.contracts as contracts  # noqa: E402
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_diagnostic_ir_v1 as hip_diagnostic,
)
from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_model_family_diagnostic_ir_v1 as family_diagnostic,
)
from structural_analysis.engine_v2.contracts import (  # noqa: E402
    diagnostic_ir_v1,
)


CONTRACT_EXPORTS = (
    "DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE",
    "DIAGNOSTIC_IR_V1_SCHEMA_VERSION",
    "DiagnosticArrayV1",
    "DiagnosticIRV1",
    "DiagnosticIRV1Analysis",
    "DiagnosticIRV1Arrays",
    "DiagnosticIRV1Claims",
    "DiagnosticIRV1Counters",
    "DiagnosticIRV1Error",
    "DiagnosticIRV1InputBindings",
    "DiagnosticIRV1Metrics",
    "DiagnosticIRV1Ordering",
    "DiagnosticIRV1Policy",
    "DiagnosticIRV1RestartRecord",
    "DiagnosticIRV1Termination",
    "DiagnosticSourceProvenanceV1",
    "build_diagnostic_ir_v1",
    "validate_diagnostic_ir_v1",
    "validate_diagnostic_ir_v1_manifest",
    "validate_diagnostic_ir_v1_physics",
)
BRIDGE_EXPORTS = (
    "HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE",
    "HipFgmresDiagnosticIRBridgeResultV1",
    "HipFgmresDiagnosticIRV1Error",
    "build_hip_fgmres_diagnostic_ir_v1",
    "validate_hip_fgmres_diagnostic_ir_v1",
)
FAMILY_EXPORTS = (
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_ARCHITECTURE_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_REQUIRED_SLOT_IDS_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_SCHEMA_VERSION_V1",
    "HIP_FGMRES_MODEL_FAMILY_DIAGNOSTIC_IR_STATUS_V1",
    "HipFgmresModelFamilyDiagnosticIRBindingsV1",
    "HipFgmresModelFamilyDiagnosticIRClaimsV1",
    "HipFgmresModelFamilyDiagnosticIRObservationV1",
    "HipFgmresModelFamilyDiagnosticIRReceiptV1",
    "HipFgmresModelFamilyDiagnosticIRResultV1",
    "HipFgmresModelFamilyDiagnosticIRTotalsV1",
    "HipFgmresModelFamilyDiagnosticIRV1Error",
    "attest_hip_fgmres_model_family_diagnostic_ir_v1",
    "validate_hip_fgmres_model_family_diagnostic_ir_receipt_v1",
    "validate_hip_fgmres_model_family_diagnostic_ir_result_v1",
)
PRIVATE_CONTRACT_NAMES = ("_issue_bridge_diagnostic_ir_v1_ready",)


def test_diagnostic_ir_v1_public_exports_are_identity_stable() -> None:
    assert len(CONTRACT_EXPORTS) == 20
    for exports in (CONTRACT_EXPORTS, BRIDGE_EXPORTS, FAMILY_EXPORTS):
        assert len(exports) == len(set(exports))
    assert tuple(diagnostic_ir_v1.__all__) == CONTRACT_EXPORTS
    assert tuple(hip_diagnostic.__all__) == BRIDGE_EXPORTS
    assert tuple(family_diagnostic.__all__) == FAMILY_EXPORTS

    for name in CONTRACT_EXPORTS:
        assert name in contracts.__all__
        assert name in engine_v2.__all__
        assert getattr(contracts, name) is getattr(diagnostic_ir_v1, name)
        assert getattr(engine_v2, name) is getattr(diagnostic_ir_v1, name)

    for module, exports in (
        (hip_diagnostic, BRIDGE_EXPORTS),
        (family_diagnostic, FAMILY_EXPORTS),
    ):
        for name in exports:
            assert name in assembly_backend.__all__
            assert name in engine_v2.__all__
            assert getattr(assembly_backend, name) is getattr(module, name)
            assert getattr(engine_v2, name) is getattr(module, name)

    assert "build_diagnostic_ir_v1" in CONTRACT_EXPORTS
    for name in PRIVATE_CONTRACT_NAMES:
        assert hasattr(diagnostic_ir_v1, name)
        for implementation_module in (
            diagnostic_ir_v1,
            hip_diagnostic,
            family_diagnostic,
        ):
            assert name not in implementation_module.__all__
        for public_module in (contracts, assembly_backend, engine_v2):
            assert name not in public_module.__all__
            assert not hasattr(public_module, name)


def test_diagnostic_ir_v1_schemas_are_packaged_descriptor_only_resources() -> None:
    for name in (
        "diagnostic_ir_v1.schema.json",
        "hip_fgmres_model_family_diagnostic_ir_v1.schema.json",
    ):
        resource = files("structural_analysis.schemas").joinpath(name)
        assert resource.is_file()
        payload = resource.read_text(encoding="utf-8")
        assert payload.startswith("{")
        assert '"values"' not in payload


def test_diagnostic_ir_v1_public_all_lists_have_no_duplicates_or_missing_names() -> (
    None
):
    for module in (engine_v2, contracts, assembly_backend):
        assert len(module.__all__) == len(set(module.__all__))
        assert not [name for name in module.__all__ if not hasattr(module, name)]
