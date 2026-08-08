from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_mdof_linear_transient_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_mdof_linear_transient", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="9" * 40)


def test_mdof_linear_transient_closes_nine_surfaces_after_sdof(
    receipt: dict[str, object],
) -> None:
    assert receipt["status"] == "ready"
    assert receipt["contract_pass"] is True
    gate = receipt["stage_gate"]
    assert gate["predecessor_stage"] == "sdof_authenticated_transient"
    assert gate["stage_index"] == 6
    assert len(gate["verified_surfaces"]) == 9
    assert gate["blockers"] == []


def test_mdof_checkpoint_and_vector_result_are_authoritative(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    checkpoint = artifacts["checkpoint"]
    authority = checkpoint["source_authority_receipt"]
    result = artifacts["result_ir"]["manifest"]

    assert checkpoint["exact_restart"] is True
    assert authority["source_authenticated_checkpoint"] is True
    assert authority["parent_chain_complete"] is True
    assert authority["dynamic_equilibrium_replay_pass"] is True
    assert authority["newmark_kinematic_replay_pass"] is True
    assert authority["deterministic_checkpoint_replay_pass"] is True
    assert result["analysis_type"] == "mdof_linear_transient"
    assert result["authority"]["response_history"] == "authoritative"
    assert result["checkpoint"]["authority"] == "source_authenticated_checkpoint"
    assert len(result["dof_ids"]) == 2
    assert len(result["history"]) == 21
    assert len(result["history"][-1]["displacement_m"]) == 2


def test_mdof_solver_benchmark_and_workbench_pass_without_fallback(
    receipt: dict[str, object],
) -> None:
    artifacts = receipt["surface_artifacts"]
    solver = artifacts["solver"]
    benchmark = artifacts["benchmark"]
    workbench = artifacts["workbench"]

    assert solver["linear_solve_count"] == 20
    assert solver["maximum_relative_residual"] <= 1.0e-10
    assert solver["fallback_used"] is False
    assert solver["regularization_used"] is False
    assert benchmark["maximum_absolute_error_m"] <= benchmark["tolerance_m"]
    assert benchmark["deterministic_repeat"] is True
    assert len(workbench["time_history_cards"]) == 2


def test_check_replays_recorded_source_commit(
    tmp_path: Path, receipt: dict[str, object]
) -> None:
    target = tmp_path / "mdof-linear-transient.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert MODULE.main(["--out", str(target), "--check"]) == 0
