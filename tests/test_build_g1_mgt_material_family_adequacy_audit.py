from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_material_family_adequacy_audit.py"
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_material_family_adequacy_audit",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_committed_material_family_adequacy_audit_is_current() -> None:
    passed, reason = module.check(root=ROOT)
    assert passed, reason


def test_material_family_audit_keeps_nonlinear_source_gap_visible() -> None:
    payload = json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8"))
    assert payload["operator_binding"]["all_geometry_arrays_exact"] is True
    assert payload["operator_binding"]["property_fallback_count"] == 0
    assert payload["material_fixture"]["element_count"] == 5_572
    assert payload["material_fixture"]["family_counts"] == {
        "CONC": 2_182,
        "SRC": 1_692,
        "STEEL": 1_692,
        "USER": 6,
    }
    assert payload["accepted_state_audit"]["load_factor"] == 1.0
    assert payload["accepted_state_audit"]["free_equation_count"] == 70_560
    assert payload["source_adequacy"][
        "authoritative_nonlinear_parameter_set_complete"
    ] is False
    assert all(
        payload["source_adequacy"]["missing_authoritative_nonlinear_fields"].values()
    )
    assert payload["claims"][
        "nonlinear_material_family_breadth_connected_to_equilibrium"
    ] is False
    assert payload["claims"]["g1_closure"] is False
