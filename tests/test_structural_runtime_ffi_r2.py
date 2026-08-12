from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "check_structural_runtime_ffi_r2.py"
SPEC = importlib.util.spec_from_file_location("check_structural_runtime_ffi_r2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
r2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r2
SPEC.loader.exec_module(r2)


def test_r2_owns_raw_wire_and_adapter_contracts_under_the_r1_lower_gate() -> None:
    payload = r2.check_r2(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["lower_gate_pass"] is True
    assert payload["wire_golden_hashes_match"] is True
    assert len(payload["wire_golden_sha256"]) == 4
    assert payload["binary_exports"] is None


def test_r2_inventory_maps_each_compatibility_role_to_one_owner() -> None:
    inventory = json.loads(
        (ROOT / r2.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )

    assert inventory["transition_step"] == "R2"
    assert inventory["ownership"] == r2.EXPECTED_OWNERSHIP
    assert inventory["verification"] == r2.EXPECTED_VERIFICATION
    assert set(inventory["wire_golden_sha256"]) == {
        "native/tests/fixtures/legacy_runtime_v3/inplace_scale_f32.json",
        "native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json",
        "native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json",
        "native/tests/fixtures/legacy_runtime_v3/track_point_load.json",
    }


def test_r2_checker_fails_closed_on_neutral_golden_hash_drift(tmp_path: Path) -> None:
    inventory = json.loads(
        (ROOT / r2.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    fixture = next(iter(inventory["wire_golden_sha256"]))
    inventory["wire_golden_sha256"][fixture] = "0" * 64
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r2.check_r2(ROOT, path)

    assert payload["contract_pass"] is False
    assert f"r2_wire_golden_hash_mismatch:{fixture}" in payload["blockers"]
