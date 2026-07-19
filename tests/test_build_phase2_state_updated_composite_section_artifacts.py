from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_phase2_state_updated_composite_section_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_state_updated_composite_section_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_perfect_bond_composite_without_breadth_promotion() -> None:
    payloads = module.build_phase2_state_updated_composite_section_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert result["state_updated_composite_seed_contract_pass"] is True
    assert result["perfect_bond_only"] is True
    assert result["composite_section_breadth_closure_claim"] is False
    assert result["material_newton_breadth_closure_claim"] is False
    assert result["g1_material_newton_breadth_claim"] is False
    assert result["production_nonlinear_closure_claim"] is False
    assert result["residual_formula"] == "F_internal_minus_F_external"
    assert result["composite_algorithm"] == (
        "iso_strain_parallel_constituent_integration"
    )
    assert result["material_point"]["contract_pass"] is True
    assert all(
        row["finite_difference_tangent"]["pass"]
        for row in result["material_point"]["point_rows"]
    )
    assert result["material_point"]["cyclic_path"]["energy_gate_passed"] is True
    assert result["material_point"]["cyclic_path"][
        "constituent_state_gate_passed"
    ] is True
    assert result["element_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["constituent_states_updated"] is True
    assert result["structure_benchmark"]["deterministic_replay_exact"] is True
    assert result["structure_benchmark"][
        "consistent_jacobian_finite_difference"
    ]["pass"] is True
    assert result["rollback_probe"]["exact"] is True
    assert result["verification"]["fallback_count"] == 0
    assert result["verification"]["regularization_count"] == 0

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["material_point_tangent_gate_passed"] is True
    assert summary["cyclic_energy_gate_passed"] is True
    assert summary["constituent_state_gate_passed"] is True
    assert summary["element_benchmark_gate_passed"] is True
    assert summary["structure_benchmark_gate_passed"] is True
    assert summary["structure_jacobian_gate_passed"] is True
    assert summary["rollback_exact_gate_passed"] is True
    assert summary["deterministic_replay_exact_gate_passed"] is True
    assert summary["perfect_bond_only"] is True
    assert "partial_interaction_connector_slip_not_closed" in summary[
        "blockers_remaining"
    ]
    assert "perfect-bond iso-strain" in summary["claim_boundary"]


def test_builder_check_reports_missing_composite_section_artifacts(
    tmp_path: Path,
) -> None:
    ok, message = module.check_phase2_state_updated_composite_section_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_state_updated_composite_section_missing:")


def test_committed_composite_section_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_state_updated_composite_section_artifacts(
        repo_root=ROOT
    )

    assert ok is True
    assert message == "phase2_state_updated_composite_section_consistent"
