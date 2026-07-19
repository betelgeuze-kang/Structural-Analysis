from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_arc_length_cpu_fgmres_continuation_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_complete_short_path_and_claim_boundaries() -> None:
    payloads = module.build_phase2_arc_length_cpu_fgmres_continuation_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["accepted_step_count"] == 6
    assert summary["tangent_solver_mode"] == "materialized_tangent_matrix"
    assert summary["rejected_step_count"] == 1
    assert summary["rollback_exact"] is True
    assert summary["final_primary_displacement_m"] >= 0.20
    assert summary["final_load_factor"] < 0.0
    assert summary["tangent_solve_count"] == 57
    assert summary["maximum_tangent_solve_iteration_count"] == 2
    assert summary[
        "maximum_tangent_solve_explicit_residual_inf_norm_kn"
    ] <= 1.0e-12
    assert summary["path_gate_passed"] is True
    assert summary["limit_point_crossed"] is True
    assert summary["negative_load_branch_reached"] is True
    assert summary["external_tangent_integration_gate_passed"] is True
    assert summary["all_tangent_solves_ready"] is True
    assert summary["rollback_evidence_passed"] is True
    assert summary["checkpoint_restart_exact"] is True
    assert summary["deterministic_replay_exact"] is True
    assert summary["dense_augmented_reference_gate_passed"] is True
    assert summary[
        "maximum_dense_reference_displacement_absolute_error_m"
    ] <= 1.0e-12
    assert summary[
        "maximum_dense_reference_load_factor_absolute_error"
    ] <= 1.0e-12
    assert summary["fallback_count"] == 0
    assert summary["regularization_count"] == 0
    assert len(summary["tangent_solve_hashes"]) == 57
    assert summary[
        "complete_short_path_cpu_fgmres_arc_length_integration_claim"
    ] is True
    assert summary["engine_v2_cpu_fgmres_every_tangent_solve_claim"] is True
    assert summary["general_frame_shell_arc_length_claim"] is False
    assert summary["production_scale_sparse_preconditioner_claim"] is False
    assert summary["production_rocm_hip_nonlinear_parity_claim"] is False
    assert summary["g1_full_building_closure_claim"] is False


def test_builder_result_validates_against_schema() -> None:
    result = module.build_phase2_arc_length_cpu_fgmres_continuation_artifacts(
        repo_root=ROOT
    )["result"]
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = (
        module.check_phase2_arc_length_cpu_fgmres_continuation_artifacts(
            repo_root=ROOT,
            result_out=tmp_path / "missing-result.json",
            summary_out=tmp_path / "missing-summary.json",
        )
    )

    assert ok is False
    assert message.startswith("phase2_arc_length_fgmres_continuation_missing:")


def test_committed_arc_length_fgmres_continuation_artifacts_match_builder() -> None:
    ok, message = (
        module.check_phase2_arc_length_cpu_fgmres_continuation_artifacts(
            repo_root=ROOT
        )
    )

    assert ok is True
    assert message == "phase2_arc_length_fgmres_continuation_consistent"
