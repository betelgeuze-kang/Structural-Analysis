from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_phase1_core_api_contract_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase1_core_api_contract_artifacts",
    SCRIPT_PATH,
)
build_phase1_core_api_contract_artifacts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_phase1_core_api_contract_artifacts
assert SPEC.loader is not None
SPEC.loader.exec_module(build_phase1_core_api_contract_artifacts)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "model_out": tmp_path / "phase1_core_api_sample_model.json",
        "result_out": tmp_path / "phase1_core_api_model_health_result.json",
        "report_out": tmp_path / "phase1_core_api_model_health_report.json",
        "cli_result_out": tmp_path / "phase1_core_api_cli_model_health_result.json",
        "cli_report_out": tmp_path / "phase1_core_api_cli_model_health_report.json",
        "frame_model_out": tmp_path / "phase1_core_api_frame_sample_model.json",
        "frame_result_out": tmp_path / "phase1_core_api_frame_result.json",
        "frame_report_out": tmp_path / "phase1_core_api_frame_report.json",
        "frame_cli_result_out": tmp_path / "phase1_core_api_frame_cli_result.json",
        "frame_cli_report_out": tmp_path / "phase1_core_api_frame_cli_report.json",
        "summary_out": tmp_path / "phase1_core_api_contract_summary.json",
    }


def test_contract_artifacts_cover_model_health_and_authoritative_frame_path(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)

    artifacts = build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )

    result = json.loads(paths["result_out"].read_text(encoding="utf-8"))
    report = json.loads(paths["report_out"].read_text(encoding="utf-8"))
    cli_result = json.loads(paths["cli_result_out"].read_text(encoding="utf-8"))
    cli_report = json.loads(paths["cli_report_out"].read_text(encoding="utf-8"))
    frame_result = json.loads(paths["frame_result_out"].read_text(encoding="utf-8"))
    frame_report = json.loads(paths["frame_report_out"].read_text(encoding="utf-8"))
    frame_cli_result = json.loads(
        paths["frame_cli_result_out"].read_text(encoding="utf-8")
    )
    frame_cli_report = json.loads(
        paths["frame_cli_report_out"].read_text(encoding="utf-8")
    )
    summary = json.loads(paths["summary_out"].read_text(encoding="utf-8"))

    assert artifacts["result"]["status"] == "ready"
    assert artifacts["cli_result"] == artifacts["result"]
    assert artifacts["cli_report"] == artifacts["report"]
    assert result["analysis_type"] == "model_health"
    assert result["engine_version"]
    assert result["input_checksum"].startswith("sha256:")
    assert result["convergence_history"][0]["status"] == "ready"
    assert result["claim_boundary_version"] == "developer-preview-core-api-v1"
    assert report["status"] == "pass"
    assert report["contract_pass"] is True
    assert report["unsupported_fields"] == []
    assert cli_result == result
    assert cli_report == report

    assert frame_result["status"] == "ready"
    assert frame_result["analysis_type"] == "linear_static"
    assert frame_result["solver"] == "authoritative_cpu_linear_fea_3d_v1"
    assert frame_result["metrics"]["claim_boundary"] == (
        "linear_static_3d_frame_cpu_reference_v1"
    )
    assert frame_result["metrics"]["production_fail_closed"] is True
    assert frame_result["metrics"]["fallback_used"] is False
    assert frame_result["metrics"]["regularization_used"] is False
    assert frame_result["metrics"]["viewer_payload"]["source"] == (
        "authoritative_solver_result"
    )
    assert frame_result["metrics"]["viewer_payload"]["solver_path_id"] == (
        frame_result["solver"]
    )
    assert frame_report["status"] == "pass"
    assert frame_report["contract_pass"] is True
    assert frame_cli_result == frame_result
    assert frame_cli_report == frame_report

    assert summary["schema_version"] == "phase1-core-api-contract-artifacts.v3"
    assert summary["contract_pass"] is True
    assert "source_commit_sha" in summary
    assert summary["engine_version"]
    assert summary["reused_evidence"] is False
    assert summary["input_checksums"]
    assert summary["invocation_surfaces"] == [
        "python_api",
        "cli",
        "gui_json_consumption",
    ]
    assert summary["supported_preview_analysis_types"] == [
        "model_health",
        "linear_static_axial_truss",
        "linear_static_3d_frame_cpu_reference_v1",
        "nonlinear_static_material_mesh_axial_chain",
    ]

    cli_contract = summary["cli_contract"]
    assert cli_contract["status"] == "ready"
    assert cli_contract["contract_pass"] is True
    assert cli_contract["entry_point"] == (
        "structural-analysis = structural_analysis.api.cli:main"
    )
    assert cli_contract["module_command"] == "python -m structural_analysis.api.cli"
    assert cli_contract["same_result_schema_as_python_api"] is True
    assert cli_contract["same_validation_report_schema_as_python_api"] is True
    assert cli_contract["api_result_checksum"] == cli_contract["cli_result_checksum"]
    assert cli_contract["api_validation_report_checksum"] == (
        cli_contract["cli_validation_report_checksum"]
    )

    reference_contract = summary["reference_validation_contract"]
    assert reference_contract["status"] == "ready"
    assert reference_contract["contract_pass"] is True
    assert reference_contract["python_api_blocks_reference_mismatch"] is True
    assert reference_contract["cli_blocks_reference_mismatch"] is True
    assert reference_contract["python_api_blocked_fields"] == [
        "reference_mismatch:node_count"
    ]
    assert reference_contract["cli_blocked_fields"] == [
        "reference_mismatch:node_count"
    ]

    frame_contract = summary["authoritative_linear_static_contract"]
    assert frame_contract["status"] == "ready"
    assert frame_contract["contract_pass"] is True
    assert frame_contract["solver_path_id"] == "authoritative_cpu_linear_fea_3d_v1"
    assert frame_contract["degrees_of_freedom"] == [
        "UX",
        "UY",
        "UZ",
        "RX",
        "RY",
        "RZ",
    ]
    assert frame_contract["python_api_cli_equal"] is True
    assert frame_contract["viewer_source"] == "authoritative_solver_result"
    assert frame_contract["viewer_solver_path_id"] == frame_contract["solver_path_id"]
    assert frame_contract["fallback_used"] is False
    assert frame_contract["regularization_used"] is False

    configuration_guard = summary["public_configuration_guard"]
    assert configuration_guard["status"] == "ready"
    assert configuration_guard["contract_pass"] is True
    assert configuration_guard["expected_unsupported_kinds"] == [
        "nonlinear_static_material_mesh_tolerance_invalid",
        "nonlinear_static_material_mesh_max_iterations_invalid",
    ]
    assert configuration_guard["observed_unsupported_kinds"] == (
        configuration_guard["expected_unsupported_kinds"]
    )
    assert configuration_guard["python_api_status"] == "blocked"
    assert configuration_guard["python_api_contract_pass"] is False
    assert configuration_guard["cli_returncode"] == 2
    assert configuration_guard["cli_status"] == "blocked"
    assert configuration_guard["cli_contract_pass"] is False
    assert configuration_guard["python_api_cli_equal"] is True
    assert configuration_guard["strict_json_serializable"] is True
    assert configuration_guard["solver_executed"] is False
    assert configuration_guard["convergence_claim"] is False
    assert configuration_guard["regularization_used"] is False
    assert configuration_guard["fallback_used"] is False

    schema_validation = summary["schema_validation"]
    assert schema_validation["contract_pass"] is True
    assert all(row["schema_valid"] is True for row in schema_validation["checks"].values())
    assert summary["model_input_checksum"] == result["input_checksum"]
    assert summary["expected_model_input_checksum"] == result["input_checksum"]
    assert summary["frame_model_input_checksum"] == frame_result["input_checksum"]
    assert summary["expected_frame_model_input_checksum"] == frame_result["input_checksum"]
    assert summary["artifacts"]["frame_result"] == str(paths["frame_result_out"])
    assert "6-DOF CPU Euler-Bernoulli frame/truss" in summary["claim_boundary"]
    assert "blocked before solver execution" in summary["claim_boundary"]
    assert "shell coupling" in summary["claim_boundary"]


def test_check_detects_model_health_contract_artifact_drift(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )

    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )
    assert ok is True
    assert message == "phase1_core_api_contract_consistent"

    result = json.loads(paths["result_out"].read_text(encoding="utf-8"))
    result["status"] = "blocked"
    _write_json(paths["result_out"], result)

    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )
    assert ok is False
    assert message == "phase1_core_api_contract_mismatch:result"


def test_check_detects_authoritative_frame_contract_artifact_drift(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )

    frame_result = json.loads(paths["frame_result_out"].read_text(encoding="utf-8"))
    frame_result["solver"] = "stale-frame-solver"
    _write_json(paths["frame_result_out"], frame_result)

    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )
    assert ok is False
    assert message == "phase1_core_api_contract_mismatch:frame_result"


def test_check_detects_cli_contract_artifact_drift(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )

    cli_result = json.loads(paths["cli_result_out"].read_text(encoding="utf-8"))
    cli_result["claim_boundary_version"] = "stale-cli-boundary"
    _write_json(paths["cli_result_out"], cli_result)

    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        **paths,
    )
    assert ok is False
    assert message == "phase1_core_api_contract_mismatch:cli_result"
