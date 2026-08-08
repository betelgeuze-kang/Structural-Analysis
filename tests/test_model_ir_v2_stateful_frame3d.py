from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from structural_analysis.model_ir import load_model_ir_v2, validate_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_stateful_steel.json"


def test_stateful_frame3d_model_ir_is_analysis_ready_and_hash_bound() -> None:
    document = load_model_ir_v2(FIXTURE)
    payload = document.to_dict()

    assert document.analysis_ready is True
    assert document.capability_profile == "frame3d_stateful_nonlinear_3d_v1"
    assert payload["materials"][0]["law_id"] == "bilinear_combined_hardening_steel"
    assert payload["materials"][0]["state_schema"] == {
        "stateful": True,
        "state_update_epoch": "accepted_state",
        "supports_trial_commit_rollback": True,
    }
    assert payload["load_patterns"][0]["analysis_type"] == "nonlinear_static"
    assert document.content_hash.startswith("sha256:")


def test_stateful_material_contract_rejects_missing_hardening_and_false_state() -> None:
    payload = load_model_ir_v2(FIXTURE).to_dict()
    missing = deepcopy(payload)
    del missing["materials"][0]["parameters"]["kinematic_hardening_modulus_pa"]
    false_state = deepcopy(payload)
    false_state["materials"][0]["state_schema"]["stateful"] = False

    assert validate_model_ir_v2(missing).schema_valid is False
    assert validate_model_ir_v2(false_state).schema_valid is False


def test_linear_material_profile_remains_valid() -> None:
    linear = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
    document = load_model_ir_v2(linear)

    assert document.capability_profile == "engine_v2_phase0_linear_3d"
    assert document.analysis_ready is True
