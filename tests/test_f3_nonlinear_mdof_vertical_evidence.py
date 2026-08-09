from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_nonlinear_mdof_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_nonlinear_mdof", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="a" * 40)


def test_nonlinear_mdof_closes_nine_surfaces_in_order(
    receipt: dict[str, object],
) -> None:
    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    gate = receipt["stage_gate"]
    assert gate["stage"] == "nonlinear_mdof"
    assert gate["stage_index"] == 7
    assert gate["predecessor_stage"] == "mdof_linear_transient"
    assert gate["vertical_stage_contract_passed"] is True
    assert gate["public_product_promotion_passed"] is False
    assert gate["technical_blockers"] == []
    assert gate["promotion_blockers"] == [
        "external_vv_signature_verification_waived",
        "planar_product_replay_prerequisite_not_bound",
        "planar_external_vv_prerequisite_not_bound",
        "predecessor_stage_not_promoted",
    ]
    assert gate["blockers"] == gate["promotion_blockers"]
    assert len(gate["verified_surfaces"]) == 9


def test_nonlinear_mdof_material_commit_rollback_and_checkpoint(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    solver = artifacts["solver"]
    checkpoint = artifacts["checkpoint"]
    authority = checkpoint["source_authority_receipt"]
    assert solver["yielded_step_count"] > 0
    assert solver["material_trial_commit_rollback"] is True
    assert solver["fallback_used"] is False
    assert solver["regularization_used"] is False
    assert checkpoint["exact_restart"] is True
    assert checkpoint["forced_failure_trial_observed"] is True
    assert checkpoint["forced_failure_rollback_exact"] is True
    assert authority["source_authenticated_checkpoint"] is True
    assert authority["material_state_replay_pass"] is True


def test_nonlinear_mdof_result_and_elastic_limit_vv(receipt: dict[str, object]) -> None:
    artifacts = receipt["surface_artifacts"]
    result = artifacts["result_ir"]["manifest"]
    benchmark = artifacts["benchmark"]
    assert result["authority"]["response_history"] == "authoritative"
    assert result["authority"]["material_state"] == "authoritative"
    assert len(result["terminal_story_material_states"]) == 2
    assert artifacts["recovery"]["plastic_dissipation_j"] > 0.0
    assert (
        benchmark["maximum_absolute_displacement_difference_m"]
        <= benchmark["tolerance_m"]
    )
    assert benchmark["yielded_step_count"] == 0


def test_check_replays_recorded_source_commit(
    tmp_path: Path,
    receipt: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "nonlinear-mdof.json"
    target.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        MODULE,
        "build_receipt",
        lambda *, source_commit_sha=None: receipt,
    )
    assert MODULE.main(["--out", str(target), "--check"]) == 0
