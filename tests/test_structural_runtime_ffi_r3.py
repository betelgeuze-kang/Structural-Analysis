from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "check_structural_runtime_ffi_r3.py"
SPEC = importlib.util.spec_from_file_location("check_structural_runtime_ffi_r3", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
r3 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r3
SPEC.loader.exec_module(r3)


def test_r3_tracks_each_cpu_family_without_overpromoting_later_gates() -> None:
    payload = r3.check_r3(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["lower_gate_pass"] is True
    assert payload["capability_gate"] == "C1"
    assert payload["capability_gates"] == {
        "track_point_load_cpu": "C1",
        "nonlinear_static_cpu": "C1",
        "nonlinear_ndtha_cpu": "C1",
    }
    assert payload["product_exports"] is None
    assert len(payload["legacy_exports"]) == 5


def test_r3_inventory_keeps_family_specific_parity_boundaries_explicit() -> None:
    inventory = json.loads(
        (ROOT / r3.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )

    assert inventory["transition_step"] == "R3"
    assert inventory["r3_track_point_load"] == r3.EXPECTED_R3
    parity = inventory["r3_track_point_load"]["parity"]
    assert parity["python_full_vector"] == "pass"
    assert parity["legacy_rotation_endpoints"] == "intentional_product_divergence"
    assert parity["c1_promoted"] is True
    assert parity["c2_hip"] == "open"

    assert (
        inventory["r3_nonlinear_static"]
        == r3.EXPECTED_NONLINEAR_STATIC_R3
    )
    nonlinear_parity = inventory["r3_nonlinear_static"]["parity"]
    assert nonlinear_parity["legacy_rust_full_result"] == "pass"
    assert nonlinear_parity["python_full_result_matrix"] == "pass"
    assert nonlinear_parity["nonconvergence_taxonomy"] == "pass"
    assert nonlinear_parity["c1_promoted"] is True
    assert nonlinear_parity["c2_hip"] == "open"

    assert inventory["r3_nonlinear_ndtha"] == r3.EXPECTED_NONLINEAR_NDTHA_R3
    ndtha_parity = inventory["r3_nonlinear_ndtha"]["parity"]
    assert ndtha_parity["legacy_rust_full_result"] == "pass"
    assert ndtha_parity["failure_atomicity"] == "pass"
    assert ndtha_parity["collapse_terminal_mapping"] == "pass"
    assert ndtha_parity["python_full_result_matrix"] == "pass"
    assert ndtha_parity["nonconvergence_taxonomy"] == "pass"
    assert ndtha_parity["c1_promoted"] is True
    assert ndtha_parity["c2_hip"] == "open"


def test_r3_checker_fails_closed_on_inventory_gate_drift(tmp_path: Path) -> None:
    inventory = json.loads(
        (ROOT / r3.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    inventory["r3_track_point_load"]["capability_gate"] = "C3"
    path = tmp_path / "overpromoted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r3.check_r3(ROOT, path)

    assert payload["contract_pass"] is False
    assert "r3_track_inventory_invalid" in payload["blockers"]


def test_r3_checker_fails_closed_on_nonlinear_static_gate_drift(
    tmp_path: Path,
) -> None:
    inventory = json.loads(
        (ROOT / r3.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    inventory["r3_nonlinear_static"]["capability_gate"] = "C2"
    path = tmp_path / "nonlinear-hip-overpromoted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r3.check_r3(ROOT, path)

    assert payload["contract_pass"] is False
    assert "r3_nonlinear_static_inventory_invalid" in payload["blockers"]


def test_r3_checker_fails_closed_on_nonlinear_ndtha_gate_drift(
    tmp_path: Path,
) -> None:
    inventory = json.loads(
        (ROOT / r3.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    inventory["r3_nonlinear_ndtha"]["capability_gate"] = "C2"
    path = tmp_path / "ndtha-hip-overpromoted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r3.check_r3(ROOT, path)

    assert payload["contract_pass"] is False
    assert "r3_nonlinear_ndtha_inventory_invalid" in payload["blockers"]
