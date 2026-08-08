from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_frame3d_load_control_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_frame3d_load_control", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_load_control_closes_nine_surfaces_after_linear_predecessor() -> None:
    payload = MODULE.build_receipt(source_commit_sha="d" * 40)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["stage_gate"]["predecessor_stage"] == "frame3d_linear"
    assert payload["predecessor_replay"]["input_checksums_unchanged"] is True
    assert len(payload["stage_gate"]["verified_surfaces"]) == 9
    assert payload["stage_gate"]["blockers"] == []


def test_load_control_reaches_full_load_with_equilibrium_and_exact_restart() -> None:
    payload = MODULE.build_receipt(source_commit_sha="e" * 40)
    solver = payload["surface_artifacts"]["solver"]
    recovery = payload["surface_artifacts"]["recovery"]
    checkpoint = payload["surface_artifacts"]["checkpoint"]

    assert solver["load_factors"] == [0.25, 0.5, 1.0]
    assert solver["contract_pass"] is True
    assert solver["fallback_used"] is False
    assert solver["regularization_used"] is False
    assert recovery["free_residual_inf_n"] <= 1.0e-4
    assert checkpoint["checkpoint"]["load_factor"] == 1.0
    assert checkpoint["exact_restart"] is True


def test_load_control_uses_authoritative_nonlinear_result_and_bound_viewer() -> None:
    payload = MODULE.build_receipt(source_commit_sha="f" * 40)
    result = payload["surface_artifacts"]["result_ir"]["manifest"]
    viewer = payload["surface_artifacts"]["workbench"]["viewer_payload"]

    assert result["authority"]["displacement"] == "authoritative"
    assert result["authority"]["material_state"] == "authoritative"
    assert result["claim_boundary"]["residual_and_increment_terminal_gate"] is True
    assert result["claim_boundary"]["fallback_or_regularization_promoted"] is False
    assert viewer["model_identity"]["canonical_model_checksum"].startswith("sha256:")
