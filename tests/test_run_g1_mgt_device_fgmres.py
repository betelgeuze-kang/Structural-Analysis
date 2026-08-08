from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_g1_mgt_device_fgmres as gate


def test_committed_receipt_is_current_and_artifacts_are_bound() -> None:
    passed, reason = gate.check(root=ROOT)
    assert passed, reason


def test_receipt_keeps_remaining_hardware_and_nonlinear_boundaries_visible() -> None:
    payload = json.loads((ROOT / gate.DEFAULT_OUT).read_text(encoding="utf-8"))
    assert payload["claims"]["production_size_fgmres"] is True
    assert payload["claims"]["mid_iteration_d2h_zero"] is True
    assert payload["claims"]["newton_update_on_device"] is True
    assert payload["claims"]["physical_line_search_on_device"] is True
    assert payload["claims"]["nonlinear_convergence_gate_on_device"] is True
    assert payload["claims"]["checkpoint_emitted"] is True
    assert payload["claims"]["exact_restart"] is True
    assert payload["claims"]["independent_gfx1100_run"] is False
    assert payload["claims"]["material_commit_rollback"] is True
    assert payload["claims"]["actual_mgt_elastic_material_state_bundle"] is True
    assert payload["claims"][
        "actual_mgt_material_family_fixture_device_bound"
    ] is True
    assert payload["claims"]["nonlinear_material_family_breadth"] is False
    lifecycle = payload["material_lifecycle"]
    assert lifecycle["integration_point_count"] == 5_572
    assert lifecycle["family_fixture"]["geometry_order_exact"] is True
    assert lifecycle["family_fixture"]["family_counts"] == {
        "CONC": 2_182,
        "SRC": 1_692,
        "STEEL": 1_692,
        "USER": 6,
    }
    assert lifecycle["field_names"][-4:] == [
        "material_family_code",
        "source_primary_elastic_modulus_mpa",
        "source_secondary_elastic_modulus_mpa",
        "source_elastic_stress_mpa",
    ]
    assert lifecycle["trial_count"] == 2
    assert lifecycle["commit_count"] == 1
    assert lifecycle["rollback_count"] == 1
    assert lifecycle["mid_lifecycle_d2h_transfer_count"] == 0
    assert lifecycle["rollback_state_bitwise_exact"] is True
    assert lifecycle["material_state_bundle"]["entry_count"] == 5_572
    assert lifecycle["material_state_bundle"]["committed_epoch"] == 1
    assert lifecycle["material_state_bundle"]["rollback_returns_exact_accepted_object"] is True
    assert payload["claims"]["resultir_diagnosticir"] is False
    assert payload["claims"]["g1_closure"] is False
