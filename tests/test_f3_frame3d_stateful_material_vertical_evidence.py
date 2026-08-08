from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_frame3d_stateful_material_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_frame3d_stateful_material", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="6" * 40)


def test_stateful_material_closes_nine_surfaces_after_direct_control(
    receipt: dict[str, object],
) -> None:
    assert receipt["status"] == "ready"
    assert receipt["contract_pass"] is True
    gate = receipt["stage_gate"]
    assert gate["predecessor_stage"] == "frame3d_direct_control"
    assert len(gate["verified_surfaces"]) == 9
    assert gate["blockers"] == []


def test_stateful_material_cyclic_history_and_restart_are_physical(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    solver = artifacts["solver"]
    checkpoint = artifacts["checkpoint"]
    benchmark = artifacts["benchmark"]

    assert solver["load_factors"] == [0.5, 1.0, -1.0, 0.25]
    assert solver["material_commit_rollback_supported"] is True
    assert solver["fallback_used"] is False
    assert solver["regularization_used"] is False
    assert checkpoint["exact_restart"] is True
    assert checkpoint["material_state"]["accumulated_plastic_strain"] > 0.0
    assert checkpoint["material_state"]["dissipated_energy_density_mj_per_m3"] > 0.0
    assert benchmark["displacement_absolute_error_m"] <= 1.0e-9
    assert benchmark["factorization_diagnostics_pass"] is True


def test_stateful_result_ir_binds_four_state_and_material_epochs(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    result = artifacts["result_ir"]["manifest"]

    assert result["authority"]["displacement"] == "authoritative"
    assert result["authority"]["material_state"] == "authoritative"
    assert result["bindings"]["state_epoch"] == 4
    assert result["load_factor"] == 0.25
    assert artifacts["recovery"]["final_residual_inf_n"] <= 1.0e-4


def test_check_replays_recorded_source_commit(
    tmp_path: Path, receipt: dict[str, object]
) -> None:
    target = tmp_path / "stateful-material.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert MODULE.main(["--out", str(target), "--check"]) == 0
