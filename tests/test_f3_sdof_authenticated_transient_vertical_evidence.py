from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_sdof_authenticated_transient_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_sdof_authenticated_transient", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="8" * 40)


def test_sdof_transient_closes_nine_surfaces_after_modal_buckling(
    receipt: dict[str, object],
) -> None:
    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    gate = receipt["stage_gate"]
    assert gate["predecessor_stage"] == "modal_buckling"
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


def test_sdof_checkpoint_is_source_authenticated_and_exactly_resumable(
    receipt: dict[str, object],
) -> None:
    checkpoint = receipt["surface_artifacts"]["checkpoint"]
    authority = checkpoint["source_authority_receipt"]

    assert checkpoint["exact_restart"] is True
    assert checkpoint["source_authenticated_resume"] is True
    assert authority["source_authenticated_checkpoint"] is True
    assert authority["parent_chain_complete"] is True
    assert authority["newmark_kinematic_replay_pass"] is True
    assert authority["dynamic_equilibrium_replay_pass"] is True
    assert authority["external_work_replay_pass"] is True
    assert authority["damping_dissipation_replay_pass"] is True
    assert authority["plastic_dissipation_replay_pass"] is True


def test_sdof_result_ir_and_benchmark_have_no_fallback(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    solver = artifacts["solver"]
    result = artifacts["result_ir"]["manifest"]
    benchmark = artifacts["benchmark"]

    assert result["authority"]["response_history"] == "authoritative"
    assert result["authority"]["material_state"] == "authoritative"
    assert result["checkpoint"]["authority"] == "source_authenticated_checkpoint"
    assert len(result["history"]) == 21
    assert solver["yielded_step_count"] > 0
    assert solver["fallback_used"] is False
    assert solver["regularization_used"] is False
    assert benchmark["linear_absolute_error_m"] <= 2.0e-6
    assert benchmark["cyclic_plastic_history_nonzero"] is True


def test_check_replays_recorded_source_commit(
    tmp_path: Path, receipt: dict[str, object]
) -> None:
    target = tmp_path / "sdof-transient.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert MODULE.main(["--out", str(target), "--check"]) == 0
