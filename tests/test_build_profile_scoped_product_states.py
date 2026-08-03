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


def test_developer_preview_state_does_not_consume_commercial_inputs() -> None:
    state = module.build_developer_preview_state(
        source_commit_sha="a" * 40,
        developer_preview_status=module.DEFAULT_DP_STATUS,
    )

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


def test_commercial_state_remains_fail_closed_on_pm_provenance() -> None:
    state = module.build_commercial_state(
        source_commit_sha="b" * 40,
        pm_report=module.DEFAULT_PM_REPORT,
    )

    assert state["schema_version"] == "commercial-release-product-state.v1"
    assert state["contract_pass"] is True
    assert state["state_ready"] is False
    assert state["status"] == "blocked"
    assert state["release_claims_fail_closed"] is True
    assert "source_provenance::input_not_reproducible_at_declared_commit" in state[
        "blockers"
    ]


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
