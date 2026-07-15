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
    fgmres_result_ir_v2 as hip_result_ir,
)
from structural_analysis.engine_v2.contracts import result_ir_v2  # noqa: E402


CONTRACT_EXPORTS = (
    "RESULT_IR_V2_CAPABILITY_PROFILE",
    "RESULT_IR_V2_SCHEMA_VERSION",
    "ResultArrayV2",
    "ResultIRV2",
    "ResultIRV2Error",
    "ResultIRV2SourceProvenance",
    "ResultIRV2ValidationError",
    "build_result_ir_v2",
    "validate_result_ir_v2",
    "validate_result_ir_v2_against_sources",
    "validate_result_ir_v2_manifest",
    "validate_result_ir_v2_physics",
)
BRIDGE_EXPORTS = tuple(hip_result_ir.__all__)


def test_result_ir_v2_contract_and_bridge_public_exports_are_identity_stable() -> None:
    for name in CONTRACT_EXPORTS:
        assert name in result_ir_v2.__all__
        assert name in contracts.__all__
        assert name in engine_v2.__all__
        assert getattr(contracts, name) is getattr(result_ir_v2, name)
        assert getattr(engine_v2, name) is getattr(result_ir_v2, name)

    for name in BRIDGE_EXPORTS:
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__
        assert getattr(assembly_backend, name) is getattr(hip_result_ir, name)
        assert getattr(engine_v2, name) is getattr(hip_result_ir, name)


def test_result_ir_v2_schema_is_a_packaged_descriptor_only_resource() -> None:
    resource = files("structural_analysis.schemas").joinpath("result_ir_v2.schema.json")
    assert resource.is_file()
    payload = resource.read_text(encoding="utf-8")
    assert payload.startswith("{")
    assert '"values"' not in payload


def test_result_ir_v2_public_all_lists_have_no_duplicates_or_missing_names() -> None:
    for module in (engine_v2, contracts, assembly_backend):
        assert len(module.__all__) == len(set(module.__all__))
        assert not [name for name in module.__all__ if not hasattr(module, name)]
