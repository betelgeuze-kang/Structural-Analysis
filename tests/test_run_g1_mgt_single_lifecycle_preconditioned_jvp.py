from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def _runner():
    path = ROOT / "scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py"
    spec = importlib.util.spec_from_file_location("single_lifecycle_jvp", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def test_schema_claims_only_the_composition_primitive() -> None:
    runner = _runner(); schema = json.loads((ROOT / runner.SCHEMA).read_text(encoding="utf-8")); Draft202012Validator.check_schema(schema)
    claims = schema["properties"]["claims"]["properties"]
    assert claims["single_device_lifecycle"] == {"const": True}
    assert claims["mid_composition_d2h_zero"] == {"const": True}
    assert claims["persistent_factor_buffers"] == {"const": True}
    assert claims["arnoldi_fgmres_recurrence"] == {"const": False}
    assert claims["production_fgmres"] == {"const": False}
    assert claims["g1_closure"] == {"const": False}


def test_composite_source_reuses_source_of_record_kernels() -> None:
    runner = _runner(); source = (ROOT / runner.SOURCE).read_text(encoding="utf-8")
    for token in ("#include \"engine_v2_sparse_lu_apply.hip.cpp\"", "#include \"engine_v2_current_tangent_operator.hip.cpp\"", "d_preconditioned_direction", "current_tangent_action_kernel", "mid_composition_d2h_transfer_count\\\":0", "hipStreamSynchronize"):
        assert token in source


def test_runtime_comparison_rejects_host_bridge() -> None:
    runner = _runner()
    assert "mid_composition_d2h_transfer_count" in runner.compare.__code__.co_consts
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "runtime[\"mid_composition_d2h_transfer_count\"] == 0" in source


def test_check_fails_closed_when_missing(tmp_path: Path) -> None:
    runner = _runner(); passed, reason = runner.check(root=tmp_path, out=Path("missing.json"))
    assert passed is False
    assert reason == "g1_mgt_single_lifecycle_preconditioned_jvp_receipt_missing"
