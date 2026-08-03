from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_profile_scoped_product_states.py"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_profile_scoped_product_states",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _developer_preview_state(source_commit: str = "a" * 40) -> dict:
    return module.build_developer_preview_state(
        source_commit_sha=source_commit,
        developer_preview_status=module.DEFAULT_DP_STATUS,
    )


def _commercial_state(source_commit: str = "b" * 40) -> dict:
    return module.build_commercial_state(
        source_commit_sha=source_commit,
        developer_preview_state=_developer_preview_state(source_commit),
        customer_shadow_status=module.DEFAULT_CUSTOMER_SHADOW,
        license_closure=module.DEFAULT_LICENSE_CLOSURE,
        workstation_readiness=module.DEFAULT_WORKSTATION,
        external_vv_receipt=module.DEFAULT_EXTERNAL_VV,
    )


def test_developer_preview_state_does_not_consume_commercial_inputs() -> None:
    state = _developer_preview_state()

    assert state["schema_version"] == "developer-preview-product-state.v1"
    assert state["target_profile"] == "planar_frame_verified_alpha.v1"
    assert state["contract_pass"] is True
    assert state["commercial_inputs_consumed"] == []
    assert "developer_preview_status" in state["inputs"]
    assert all(
        not blocker.startswith((
            "license::",
            "customer_shadow::",
            "commercial_sla::",
            "g1::",
        ))
        for blocker in state["blockers"]
    )
    assert "product_license" in state["future_commercial_gates"]
    assert state["final_gate_count"] == 9


def test_commercial_state_is_acyclic_and_does_not_consume_legacy_pm_report() -> None:
    state = _commercial_state()

    assert state["schema_version"] == "bounded-planar-commercial-product-state.v2"
    assert state["target_profile"] == "bounded_planar_limited_commercial"
    assert state["product_scope"] == "bounded_planar_cpu"
    assert state["contract_pass"] is True
    assert state["state_ready"] is False
    assert state["status"] == "blocked"
    assert state["legacy_pm_report_consumed"] is False
    assert state["legacy_cyclic_inputs_consumed"] == []
    assert state["dependency_dag"]["acyclic"] is True
    assert state["gpu_required_for_scope"] is False
    assert state["g1_required_for_scope"] is False
    consumed = {
        row["path"] for row in state["inputs"].values()
    }
    assert consumed.isdisjoint(module.LEGACY_CYCLIC_INPUTS)
    assert "developer_preview_not_ready" in state["blockers"]
    assert "customer_shadow_not_ready" in state["blockers"]
    assert "product_license_not_ready" in state["blockers"]
    assert "independent_operator_attestation_missing" in state["blockers"]
    assert "verification_level_2_not_achieved" in state["blockers"]
    assert "fresh_code_to_code_execution_missing" in state["blockers"]


def test_profile_scoped_state_cli_writes_both_artifacts(tmp_path: Path) -> None:
    dp_out = tmp_path / "developer-preview.json"
    commercial_out = tmp_path / "commercial.json"

    assert module.main([
        "--source-commit",
        "c" * 40,
        "--developer-preview-out",
        str(dp_out),
        "--commercial-out",
        str(commercial_out),
    ]) == 0

    dp = json.loads(dp_out.read_text(encoding="utf-8"))
    commercial = json.loads(commercial_out.read_text(encoding="utf-8"))
    assert dp["source_commit_sha"] == "c" * 40
    assert commercial["source_commit_sha"] == "c" * 40
    assert dp["target_profile"] != commercial["target_profile"]
    assert commercial["legacy_pm_report_consumed"] is False
    assert commercial["dependency_dag"]["acyclic"] is True
