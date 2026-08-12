from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_structural_runtime_ffi_r1.py"
SPEC = importlib.util.spec_from_file_location("check_structural_runtime_ffi_r1", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
r1 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r1
SPEC.loader.exec_module(r1)


def test_r1_workspace_membership_and_source_exports_are_frozen() -> None:
    payload = r1.check_r1(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["expected_exports"] == payload["source_exports"]
    assert payload["expected_status_codes"] == payload["source_status_codes"]
    assert payload["binary_exports"] is None
    assert payload["expected_exports"] == [
        "phase1_rust_nonlinear_frame_ndtha_solve",
        "phase1_rust_nonlinear_frame_solve",
        "phase1_rust_scale_inplace_f32",
        "phase1_rust_track_lf_solve_point_load",
        "phase1_rust_version",
    ]


def test_r1_lower_gate_keeps_layout_golden_and_claim_boundaries() -> None:
    inventory = json.loads(
        (ROOT / r1.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )

    assert inventory["transition_step"] in {"R1", "R2", "R3"}
    assert inventory["abi_version"] == 3
    assert len(inventory["layouts"]) == 7
    assert set(inventory["golden_cases"]) == {
        "track_pinned_euler_9",
        "scale_f32_4",
        "nonlinear_static_3_story",
        "nonlinear_ndtha_2_story_3_step",
    }
    assert inventory["package"]["standalone_output_name_preserved"] is True
    assert inventory["package"]["legacy_lock_retained_for_rollback"] is True
    for boundary in ("C++", "sa_get_api_v1", "checkpoint/restart", "product E2E"):
        assert boundary in inventory["claim_boundary"]


def test_r1_checker_fails_closed_on_export_inventory_drift(tmp_path: Path) -> None:
    inventory = json.loads(
        (ROOT / r1.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    inventory["exports"] = inventory["exports"][:-1]
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r1.check_r1(ROOT, path)

    assert payload["contract_pass"] is False
    assert "r1_inventory_export_set_invalid" in payload["blockers"]
    assert "r1_source_export_set_mismatch" in payload["blockers"]
