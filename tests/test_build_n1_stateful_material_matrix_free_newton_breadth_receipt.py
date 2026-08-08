from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_n1_stateful_material_matrix_free_newton_breadth_receipt.py"
SPEC = importlib.util.spec_from_file_location(
    "build_n1_stateful_material_matrix_free_newton_breadth_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_material_breadth_builder_closes_four_stateful_families() -> None:
    payload = module.build_receipt(repo_root=ROOT)

    # The source gate is intentionally evaluated separately because the test
    # may run against uncommitted builder edits before the evidence source commit.
    assert payload["family_contract_pass"] is True
    assert payload["material_family_count"] == 4
    assert payload["material_families"] == [
        "steel_combined_hardening",
        "asymmetric_concrete_damage",
        "parallel_steel_concrete_section",
        "bilinear_combined_hardening_link",
    ]
    assert payload["target_load_factor"] == 1.0
    assert payload["fallback_count"] == 0
    assert payload["regularization_count"] == 0
    assert payload["all_family_residual_gates_passed"] is True
    assert payload["all_family_increment_gates_passed"] is True
    assert payload["all_family_tangent_checks_passed"] is True
    assert payload["all_family_material_commits_observed"] is True
    assert payload["all_family_failed_step_rollbacks_byte_exact"] is True
    assert payload["all_family_checkpoint_restarts_byte_exact"] is True
    assert payload["all_family_deterministic_replays_byte_exact"] is True
    assert all(row["final_load_factor"] == 1.0 for row in payload["family_rows"])
    assert all(row["tangent_solve_count"] > 0 for row in payload["family_rows"])
    assert all(
        row["failed_step_probe"]["terminal_reason"]
        == "maximum_newton_iterations_exhausted"
        for row in payload["family_rows"]
    )
    assert payload["claims"]["actual_mgt_full_mesh_material_coupling"] is False
    assert payload["claims"]["n1_closure"] is False
    assert payload["claims"]["g1_closure"] is False


def test_committed_material_breadth_receipt_replays_exactly() -> None:
    receipt = ROOT / module.DEFAULT_RECEIPT_OUT
    if not receipt.is_file():
        return
    payload = module._read_json(receipt)
    ok, message = module.check_receipt(repo_root=ROOT)

    assert ok is True, message
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["source_commit_exact_replay_claim"] is True
    assert payload["source_input_provenance"]["contract_pass"] is True
