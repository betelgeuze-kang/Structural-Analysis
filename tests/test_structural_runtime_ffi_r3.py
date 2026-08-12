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


def test_r3_adds_one_cpu_family_without_overpromoting_cutover_gates() -> None:
    payload = r3.check_r3(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["lower_gate_pass"] is True
    assert payload["capability_gate"] == "C0"
    assert payload["product_exports"] is None
    assert len(payload["legacy_exports"]) == 5


def test_r3_inventory_keeps_python_and_hip_boundaries_explicit() -> None:
    inventory = json.loads(
        (ROOT / r3.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )

    assert inventory["transition_step"] == "R3"
    assert inventory["r3_track_point_load"] == r3.EXPECTED_R3
    parity = inventory["r3_track_point_load"]["parity"]
    assert parity["python_rotation_endpoints"] == "blocked"
    assert parity["c1_promoted"] is False
    assert parity["c2_hip"] == "open"


def test_r3_checker_fails_closed_on_capability_overpromotion(tmp_path: Path) -> None:
    inventory = json.loads(
        (ROOT / r3.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    inventory["r3_track_point_load"]["capability_gate"] = "C3"
    path = tmp_path / "overpromoted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r3.check_r3(ROOT, path)

    assert payload["contract_pass"] is False
    assert "r3_track_inventory_invalid" in payload["blockers"]
