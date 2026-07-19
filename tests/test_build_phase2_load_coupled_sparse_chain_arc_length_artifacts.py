from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_load_coupled_sparse_chain_arc_length_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_load_coupled_sparse_contract_and_boundaries() -> None:
    payloads = (
        module.build_phase2_load_coupled_sparse_chain_arc_length_artifacts(
            repo_root=ROOT
        )
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["equation_count"] == 12
    assert summary["accepted_step_count"] == 6
    assert summary["rejected_step_count"] == 1
    assert summary["rollback_exact"] is True
    assert summary["final_primary_displacement_m"] >= 0.20
    assert summary["final_load_factor"] < 0.0
    assert summary["operator_mode"] == "state_tangent_operator"
    assert summary["equilibrium_linearization_mode"] == (
        "load_factor_coupled_residual"
    )
    assert summary["global_dof_count"] == 72
    assert summary["free_equation_count"] == 12
    assert summary["global_csr_nnz"] == 94
    assert summary["reduced_csr_nnz"] == 34
    assert summary["dense_free_matrix_entry_count"] == 144
    assert summary["dense_tangent_materialized_by_production_path"] is False
    assert summary["sparse_gate_passed"] is True
    assert summary["load_coupling_gate_passed"] is True
    assert summary["displacement_jacobian_gate_passed"] is True
    assert summary["negative_load_derivative_gate_passed"] is True
    assert summary["load_linearization_primary_rhs_varies"] is True
    assert summary["tangent_solve_count"] == 61
    assert summary["maximum_tangent_solve_iteration_count"] == 12
    assert summary[
        "maximum_tangent_solve_explicit_residual_inf_norm_kn"
    ] <= 1.0e-9
    assert summary["unique_operator_numeric_values_hash_count"] >= 2
    assert summary["exact_chain_reduction_gate_passed"] is True
    assert summary["dense_reference_gate_passed"] is True
    assert summary["deterministic_replay_exact"] is True
    assert summary["checkpoint_restart_exact"] is True
    assert summary["negative_load_branch_reached"] is True
    assert summary["fallback_count"] == 0
    assert summary["regularization_count"] == 0
    assert summary[
        "load_factor_coupled_residual_jacobian_arc_length_claim"
    ] is True
    assert summary[
        "sparse_state_operator_arc_length_integration_claim"
    ] is True
    assert summary["dense_tangent_materialization_avoided_claim"] is True
    assert summary[
        "engine_v2_cpu_fgmres_every_production_tangent_solve_claim"
    ] is True
    assert summary[
        "real_mgt_frame_shell_material_adapter_connected_claim"
    ] is False
    assert summary["production_scale_sparse_preconditioner_claim"] is False
    assert summary["production_rocm_hip_nonlinear_parity_claim"] is False
    assert summary["g1_full_building_closure_claim"] is False


def test_builder_result_validates_against_schema() -> None:
    result = (
        module.build_phase2_load_coupled_sparse_chain_arc_length_artifacts(
            repo_root=ROOT
        )["result"]
    )
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = (
        module.check_phase2_load_coupled_sparse_chain_arc_length_artifacts(
            repo_root=ROOT,
            result_out=tmp_path / "missing-result.json",
            summary_out=tmp_path / "missing-summary.json",
        )
    )

    assert ok is False
    assert message.startswith("phase2_load_coupled_sparse_chain_missing:")


def test_committed_load_coupled_sparse_artifacts_match_builder() -> None:
    ok, message = (
        module.check_phase2_load_coupled_sparse_chain_arc_length_artifacts(
            repo_root=ROOT
        )
    )

    assert ok is True
    assert message == "phase2_load_coupled_sparse_chain_consistent"
