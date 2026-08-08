from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_shell_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_shell", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="a" * 40)


def test_shell_closes_nine_surfaces_in_order(receipt: dict[str, object]) -> None:
    assert receipt["status"] == "ready"
    gate = receipt["stage_gate"]
    assert gate["stage"] == "shell"
    assert gate["stage_index"] == 8
    assert gate["predecessor_stage"] == "nonlinear_mdof"
    assert len(gate["verified_surfaces"]) == 9
    assert gate["blockers"] == []


def test_shell_equilibrium_result_recovery_and_restart(receipt: dict[str, object]) -> None:
    artifacts = receipt["surface_artifacts"]
    assert artifacts["solver"]["maximum_free_residual"] <= 1.0e-10
    assert artifacts["solver"]["fallback_used"] is False
    assert artifacts["solver"]["regularization_used"] is False
    assert artifacts["result_ir"]["manifest"]["authority"]["element_recovery"] == "authoritative"
    assert len(artifacts["recovery"]["element_results"]) == 2
    assert artifacts["checkpoint"]["exact_restart"] is True
    assert artifacts["checkpoint"]["deterministic_repeat"] is True


def test_shell_closed_form_patch_and_workbench(receipt: dict[str, object]) -> None:
    artifacts = receipt["surface_artifacts"]; benchmark = artifacts["benchmark"]
    assert benchmark["relative_energy_error"] <= benchmark["relative_energy_tolerance"]
    assert benchmark["rigid_translation_relative_residual"] <= benchmark["rigid_relative_residual_tolerance"]
    assert artifacts["workbench"]["contour"]["state_tag"] == "contour"


def test_check_replays_recorded_source_commit(tmp_path: Path, receipt: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "shell.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(MODULE, "build_receipt", lambda *, source_commit_sha=None: receipt)
    assert MODULE.main(["--out", str(target), "--check"]) == 0
