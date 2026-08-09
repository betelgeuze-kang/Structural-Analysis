from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_frame3d_direct_control_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_frame3d_direct_control", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_direct_control_closes_nine_surfaces_after_load_control() -> None:
    payload = MODULE.build_receipt(source_commit_sha="2" * 40)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["stage_gate"]["predecessor_stage"] == "frame3d_load_control"
    assert payload["predecessor_replay"]["current_source_replay_executed"] is True
    assert len(payload["stage_gate"]["verified_surfaces"]) == 9
    assert payload["stage_gate"]["blockers"] == []


def test_direct_control_reversal_equilibrium_and_restart_are_exact() -> None:
    payload = MODULE.build_receipt(source_commit_sha="3" * 40)
    solver = payload["surface_artifacts"]["solver"]
    checkpoint = payload["surface_artifacts"]["checkpoint"]
    benchmark = payload["surface_artifacts"]["benchmark"]

    assert solver["targets_m"] == [2.5e-5, 5.0e-5, -2.5e-5]
    assert solver["fallback_used"] is False
    assert solver["regularization_used"] is False
    assert checkpoint["exact_restart"] is True
    assert checkpoint["parent_state_immutability_enforced"] is True
    assert benchmark["load_factor_absolute_error"] <= 1.0e-8
    assert benchmark["deterministic_repeat"] is True


def test_direct_control_result_ir_binds_three_state_and_material_epochs() -> None:
    payload = MODULE.build_receipt(source_commit_sha="4" * 40)
    result = payload["surface_artifacts"]["result_ir"]["manifest"]
    recovery = payload["surface_artifacts"]["recovery"]

    assert result["authority"]["displacement"] == "authoritative"
    assert result["authority"]["material_state"] == "authoritative"
    assert result["bindings"]["state_epoch"] == 3
    assert result["load_factor"] < 0.0
    assert recovery["axial_material_response"]["yielded"] is False
    assert recovery["final_residual_inf_n"] <= 1.0e-4


def test_check_replays_recorded_source_commit(tmp_path: Path) -> None:
    target = tmp_path / "direct-control.json"
    payload = MODULE.build_receipt(source_commit_sha="5" * 40)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert MODULE.main(["--out", str(target), "--check"]) == 0
