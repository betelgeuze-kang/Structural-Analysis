from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_modal_buckling_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_modal_buckling", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="7" * 40)


def test_modal_buckling_closes_nine_surfaces_after_stateful_material(
    receipt: dict[str, object],
) -> None:
    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    gate = receipt["stage_gate"]
    assert gate["predecessor_stage"] == "frame3d_stateful_material"
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


def test_modal_buckling_result_ir_and_checkpoint_are_authoritative(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    modal = artifacts["result_ir"]["modal"]
    buckling = artifacts["result_ir"]["linear_buckling"]

    assert modal["authority"]["frequencies"] == "authoritative"
    assert modal["authority"]["mode_shapes"] == "authoritative"
    assert buckling["authority"]["load_factors"] == "authoritative"
    assert buckling["authority"]["mode_shapes"] == "authoritative"
    assert artifacts["checkpoint"]["exact_restart"] is True
    assert modal["checkpoint"]["mode_count"] == 2
    assert buckling["checkpoint"]["mode_count"] == 2


def test_modal_buckling_matches_closed_form_without_fallback(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    solver = artifacts["solver"]
    benchmark = artifacts["benchmark"]

    assert solver["fallback_count"] == 0
    assert solver["regularization_count"] == 0
    assert solver["maximum_residual_relative_inf"] <= 1.0e-8
    assert benchmark["maximum_modal_relative_error"] <= 2.0e-12
    assert benchmark["maximum_buckling_relative_error"] <= 0.01
    assert benchmark["deterministic_replay"] is True


def test_check_replays_recorded_source_commit(
    tmp_path: Path, receipt: dict[str, object]
) -> None:
    target = tmp_path / "modal-buckling.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert MODULE.main(["--out", str(target), "--check"]) == 0
