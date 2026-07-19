from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_phase2_geometric_nonlinear_benchmark_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_geometric_nonlinear_benchmark_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_three_gates_without_geometric_breadth_promotion() -> None:
    payloads = module.build_phase2_geometric_nonlinear_benchmark_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert result["implemented_benchmarks_contract_pass"] is True
    assert result["verification"]["deterministic_replay_exact"] is True
    assert all(
        row["contract_pass"] for row in result["benchmarks"].values()
    )
    assert result["geometric_nonlinear_benchmark_breadth_claim"] is False
    assert result["general_frame_pdelta_claim"] is False
    assert result["lee_frame_snapthrough_claim"] is False
    assert result["arc_length_path_following_claim"] is False
    assert result["continuum_cantilever_large_rotation_claim"] is False
    assert result["general_2d_3d_geometric_stiffness_claim"] is False

    assert summary["status"] == "partial"
    assert summary["contract_pass"] is True
    assert summary["euler_column_gate_passed"] is True
    assert summary["euler_finest_relative_error"] <= 3.0e-6
    assert summary["euler_minimum_convergence_order"] >= 3.7
    assert summary["modal_pdelta_column_gate_passed"] is True
    assert summary["modal_pdelta_maximum_relative_error"] <= 1.0e-10
    assert summary["two_bar_shallow_arch_gate_passed"] is True
    assert summary["deterministic_replay_exact"] is True
    assert "lee_frame_snapthrough_not_implemented" in summary["blockers_remaining"]
    assert "not a general frame solver" in summary["claim_boundary"]


def test_builder_result_validates_against_schema() -> None:
    payload = module.build_phase2_geometric_nonlinear_benchmark_artifacts(
        repo_root=ROOT
    )["result"]
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = module.check_phase2_geometric_nonlinear_benchmark_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_geometric_nonlinear_benchmark_missing:")


def test_committed_geometric_nonlinear_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_geometric_nonlinear_benchmark_artifacts(
        repo_root=ROOT
    )

    assert ok is True
    assert message == "phase2_geometric_nonlinear_benchmark_consistent"
