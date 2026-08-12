from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "check_structural_runtime_ffi_r4.py"
SPEC = importlib.util.spec_from_file_location("check_structural_runtime_ffi_r4", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
r4 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r4
SPEC.loader.exec_module(r4)


def test_r4_detaches_the_legacy_runtime_from_the_product_workspace() -> None:
    payload = r4.check_r4(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["lower_gate_pass"] is True
    assert payload["product_workspace_dependency"] is False
    assert payload["legacy_abi_preserved"] is True
    assert "structural_runtime_ffi" not in payload["product_packages"]
    assert payload["standalone_packages"] == ["structural_runtime_ffi"]
    assert payload["removal_allowed"] is False


def test_r4_inventory_starts_deprecation_without_claiming_c6_removal() -> None:
    inventory = json.loads(
        (ROOT / r4.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )

    assert inventory["transition_step"] == "R4"
    assert inventory["r4_runtime_cutover"] == r4.EXPECTED_R4
    deprecation = inventory["r4_runtime_cutover"]["deprecation"]
    assert deprecation == {
        "started": True,
        "removal_allowed": False,
        "removal_gate": "C6",
        "rollback_lock_retained": True,
        "consumer_removal_required": True,
    }
    for boundary in ("HIP C2", "global Python decommission", "symbol removal"):
        assert boundary in inventory["claim_boundary"]


def test_r4_checker_fails_closed_if_product_dependency_is_reintroduced(
    tmp_path: Path,
) -> None:
    inventory = json.loads(
        (ROOT / r4.DEFAULT_INVENTORY).read_text(encoding="utf-8")
    )
    inventory["r4_runtime_cutover"]["product_dependency"] = True
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    payload = r4.check_r4(ROOT, path)

    assert payload["contract_pass"] is False
    assert "r4_cutover_inventory_invalid" in payload["blockers"]
