from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_contact_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_contact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def receipt() -> dict[str, object]:
    return MODULE.build_receipt(source_commit_sha="a" * 40)


def test_contact_closes_nine_surfaces_in_order(receipt: dict[str, object]) -> None:
    assert receipt["status"] == "ready"
    gate = receipt["stage_gate"]
    assert gate["stage"] == "contact" and gate["stage_index"] == 9
    assert gate["predecessor_stage"] == "shell"
    assert len(gate["verified_surfaces"]) == 9 and gate["blockers"] == []


def test_contact_kkt_result_and_restart(receipt: dict[str, object]) -> None:
    artifacts = receipt["surface_artifacts"]; solver = artifacts["solver"]
    assert solver["active_contact_ids"] == ["C1"]
    assert solver["maximum_equilibrium_residual_n"] <= 1.0e-10
    assert solver["maximum_penetration_m"] <= 1.0e-12
    assert solver["minimum_contact_multiplier_n"] >= 0.0
    assert solver["maximum_complementarity_n_m"] <= 1.0e-12
    assert solver["fallback_used"] is False and solver["regularization_used"] is False
    assert artifacts["result_ir"]["manifest"]["authority"]["kkt_metrics"] == "authoritative"
    assert artifacts["checkpoint"]["exact_restart"] is True and artifacts["checkpoint"]["deterministic_repeat"] is True


def test_contact_closed_form_breadth_and_workbench(receipt: dict[str, object]) -> None:
    artifacts = receipt["surface_artifacts"]; benchmark = artifacts["benchmark"]
    assert benchmark["maximum_displacement_error_m"] <= benchmark["displacement_tolerance_m"]
    assert benchmark["maximum_multiplier_error_n"] <= benchmark["multiplier_tolerance_n"]
    assert benchmark["active_set_breadth_pass"] is True and len(benchmark["active_set_breadth_cases"]) == 4
    assert artifacts["workbench"]["contact_multiplier_contour"]["state_tag"] == "contour"


def test_check_replays_recorded_source_commit(tmp_path: Path, receipt: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "contact.json"; target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(MODULE, "build_receipt", lambda *, source_commit_sha=None: receipt)
    assert MODULE.main(["--out", str(target), "--check"]) == 0
