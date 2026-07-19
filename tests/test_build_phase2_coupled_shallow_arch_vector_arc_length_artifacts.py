from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_coupled_shallow_arch_vector_arc_length_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_vector_path_and_strict_claim_boundaries() -> None:
    payloads = (
        module.build_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
            repo_root=ROOT
        )
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["equation_count"] == 2
    assert summary["accepted_step_count"] == 28
    assert summary["rejected_step_count"] == 1
    assert summary["rollback_exact"] is True
    assert summary["fallback_count"] == 0
    assert summary["regularization_count"] == 0
    assert summary["maximum_checkpoint_residual_inf_norm_kn"] <= 1.0e-10
    assert summary["maximum_accepted_constraint_residual_m2"] <= 1.0e-12
    assert summary["maximum_coupling_relation_absolute_error_m"] <= 1.0e-12
    assert summary["maximum_reduced_equilibrium_absolute_error_kn"] <= 1.0e-10
    assert summary["first_limit_load_relative_error"] <= 0.01
    assert summary["maximum_tangent_absolute_error_kn_per_m"] <= 1.0e-6
    assert summary["maximum_energy_gradient_absolute_error_kn"] <= 1.0e-7
    assert summary["path_gate_passed"] is True
    assert summary["exact_scalar_reduction_gate_passed"] is True
    assert summary["limit_point_gate_passed"] is True
    assert summary["tangent_energy_finite_difference_gate_passed"] is True
    assert summary["checkpoint_restart_exact"] is True
    assert summary["deterministic_replay_exact"] is True
    assert summary["dense_multi_dof_vector_arc_length_claim"] is True
    assert summary["general_frame_shell_arc_length_claim"] is False
    assert summary["lee_frame_snapthrough_claim"] is False
    assert summary["production_sparse_backend_claim"] is False
    assert summary["production_rocm_hip_parity_claim"] is False
    assert summary["g1_full_building_closure_claim"] is False


def test_builder_result_validates_against_schema() -> None:
    result = (
        module.build_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
            repo_root=ROOT
        )["result"]
    )
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = (
        module.check_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
            repo_root=ROOT,
            result_out=tmp_path / "missing-result.json",
            summary_out=tmp_path / "missing-summary.json",
        )
    )

    assert ok is False
    assert message.startswith("phase2_coupled_vector_arc_length_missing:")


def test_committed_coupled_vector_arc_length_artifacts_match_builder() -> None:
    ok, message = (
        module.check_phase2_coupled_shallow_arch_vector_arc_length_artifacts(
            repo_root=ROOT
        )
    )

    assert ok is True
    assert message == "phase2_coupled_vector_arc_length_consistent"
