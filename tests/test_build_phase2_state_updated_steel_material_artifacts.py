from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_phase2_state_updated_steel_material_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_state_updated_steel_material_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_state_updated_steel_without_material_breadth_promotion() -> None:
    payloads = module.build_phase2_state_updated_steel_material_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert result["state_updated_steel_seed_contract_pass"] is True
    assert result["material_newton_breadth_closure_claim"] is False
    assert result["g1_material_newton_breadth_claim"] is False
    assert result["production_nonlinear_closure_claim"] is False
    assert result["residual_formula"] == "F_internal_minus_F_external"
    assert result["return_mapping_algorithm"] == (
        "backward_euler_1d_radial_return"
    )
    assert len(result["material_point_variants"]) == 3
    assert all(
        row["point_contract_pass"] for row in result["material_point_variants"]
    )
    assert all(
        row["finite_difference_tangent"]["pass"]
        for row in result["material_point_variants"]
    )
    assert all(
        row["cyclic_path"]["energy_dissipation_gate_passed"]
        for row in result["material_point_variants"]
    )
    assert result["element_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["deterministic_replay_exact"] is True
    assert result["structure_benchmark"][
        "consistent_jacobian_finite_difference"
    ]["pass"] is True
    assert result["rollback_probe"]["exact"] is True
    assert result["verification"]["fallback_count"] == 0
    assert result["verification"]["regularization_count"] == 0

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["material_variant_ids"] == [
        "steel_bilinear_isotropic_hardening_1d",
        "steel_bilinear_kinematic_hardening_1d",
        "steel_bilinear_combined_hardening_1d",
    ]
    assert summary["cyclic_energy_dissipation_gate_passed"] is True
    assert summary["material_tangent_finite_difference_gate_passed"] is True
    assert summary["element_benchmark_gate_passed"] is True
    assert summary["structure_benchmark_gate_passed"] is True
    assert summary["structure_jacobian_gate_passed"] is True
    assert summary["rollback_exact_gate_passed"] is True
    assert summary["deterministic_replay_exact_gate_passed"] is True
    assert summary["fallback_count"] == 0
    assert summary["regularization_count"] == 0
    assert summary["material_newton_breadth_closure_claim"] is False
    assert "concrete_damage_multiaxial_mesh_objectivity_not_closed" in summary[
        "blockers_remaining"
    ]
    assert "small-strain uniaxial steel" in summary["claim_boundary"]


def test_builder_check_reports_missing_state_updated_material_artifacts(
    tmp_path: Path,
) -> None:
    ok, message = module.check_phase2_state_updated_steel_material_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_state_updated_steel_material_missing:")


def test_committed_generated_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_state_updated_steel_material_artifacts(
        repo_root=ROOT
    )

    assert ok is True
    assert message == "phase2_state_updated_steel_material_consistent"
