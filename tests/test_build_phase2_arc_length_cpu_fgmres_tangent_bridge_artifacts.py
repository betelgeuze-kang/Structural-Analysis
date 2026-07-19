from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_tangent_bridge_and_claim_boundaries() -> None:
    payloads = module.build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["state_row_count"] == 3
    assert summary["tangent_solve_count"] == 6
    assert summary["all_tangent_solves_ready"] is True
    assert summary["positive_negative_positive_determinant_coverage"] is True
    assert summary["schur_augmented_correction_equivalence"] is True
    assert summary["deterministic_replay_exact"] is True
    assert summary["maximum_correction_absolute_error"] <= 1.0e-12
    assert summary["maximum_augmented_linear_residual_inf_norm"] <= 1.0e-12
    assert summary["maximum_tangent_solve_explicit_residual_inf_norm"] <= 1.0e-12
    assert summary["maximum_tangent_solve_iteration_count"] == 2
    assert summary["fallback_count"] == 0
    assert summary["regularization_count"] == 0
    assert len(summary["tangent_solve_hashes"]) == 6
    assert summary["engine_v2_cpu_fgmres_tangent_bridge_claim"] is True
    assert summary["schur_augmented_increment_equivalence_claim"] is True
    assert summary["indefinite_tangent_solve_claim"] is True
    assert summary["complete_arc_length_backend_integration_claim"] is False
    assert summary["frame_shell_residual_assembly_claim"] is False
    assert summary["production_sparse_nonlinear_backend_claim"] is False
    assert summary["production_rocm_hip_parity_claim"] is False
    assert summary["g1_full_building_closure_claim"] is False


def test_builder_result_validates_against_schema() -> None:
    result = module.build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts(
        repo_root=ROOT
    )["result"]
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = (
        module.check_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts(
            repo_root=ROOT,
            result_out=tmp_path / "missing-result.json",
            summary_out=tmp_path / "missing-summary.json",
        )
    )

    assert ok is False
    assert message.startswith("phase2_arc_length_fgmres_bridge_missing:")


def test_committed_arc_length_fgmres_bridge_artifacts_match_builder() -> None:
    ok, message = (
        module.check_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts(
            repo_root=ROOT
        )
    )

    assert ok is True
    assert message == "phase2_arc_length_fgmres_bridge_consistent"
