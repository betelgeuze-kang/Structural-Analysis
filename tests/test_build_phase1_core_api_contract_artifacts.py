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
SPEC = importlib.util.spec_from_file_location("build_phase1_core_api_contract_artifacts", SCRIPT_PATH)
build_phase1_core_api_contract_artifacts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_phase1_core_api_contract_artifacts
assert SPEC.loader is not None
SPEC.loader.exec_module(build_phase1_core_api_contract_artifacts)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_contract_artifacts_are_generated_from_core_api_path(tmp_path: Path) -> None:
    model_out = tmp_path / "phase1_core_api_sample_model.json"
    result_out = tmp_path / "phase1_core_api_model_health_result.json"
    report_out = tmp_path / "phase1_core_api_model_health_report.json"
    cli_result_out = tmp_path / "phase1_core_api_cli_model_health_result.json"
    cli_report_out = tmp_path / "phase1_core_api_cli_model_health_report.json"
    summary_out = tmp_path / "phase1_core_api_contract_summary.json"

    artifacts = build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
    )

    result = json.loads(result_out.read_text(encoding="utf-8"))
    report = json.loads(report_out.read_text(encoding="utf-8"))
    cli_result = json.loads(cli_result_out.read_text(encoding="utf-8"))
    cli_report = json.loads(cli_report_out.read_text(encoding="utf-8"))
    summary = json.loads(summary_out.read_text(encoding="utf-8"))

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
    assert summary["contract_pass"] is True
    assert summary["invocation_surfaces"] == ["python_api", "cli", "gui_json_consumption"]
    cli_contract = summary["cli_contract"]
    assert cli_contract["status"] == "ready"
    assert cli_contract["contract_pass"] is True
    assert cli_contract["entry_point"] == "structural-analysis = structural_analysis.api.cli:main"
    assert cli_contract["module_command"] == "python -m structural_analysis.api.cli"
    assert cli_contract["same_result_schema_as_python_api"] is True
    assert cli_contract["same_validation_report_schema_as_python_api"] is True
    assert cli_contract["api_result_checksum"] == cli_contract["cli_result_checksum"]
    assert cli_contract["api_validation_report_checksum"] == (
        cli_contract["cli_validation_report_checksum"]
    )
    assert cli_contract["result_input_checksum"] == result["input_checksum"]
    assert cli_contract["report_input_checksum"] == report["input_checksum"]
    assert cli_contract["result_claim_boundary_version"] == "developer-preview-core-api-v1"
    assert cli_contract["report_claim_boundary_version"] == "developer-preview-core-api-v1"
    schema_validation = summary["schema_validation"]
    assert schema_validation["contract_pass"] is True
    assert schema_validation["result_schema"] == "src/structural_analysis/schemas/result.schema.json"
    assert schema_validation["validation_report_schema"] == (
        "src/structural_analysis/schemas/validation_report.schema.json"
    )
    assert {
        key: row["schema_valid"]
        for key, row in schema_validation["checks"].items()
    } == {
        "python_api_result": True,
        "python_api_validation_report": True,
        "cli_result": True,
        "cli_validation_report": True,
    }
    assert summary["model_input_checksum"] == result["input_checksum"]
    assert summary["expected_model_input_checksum"] == result["input_checksum"]
    assert summary["artifacts"]["cli_result"] == str(cli_result_out)
    assert summary["artifacts"]["cli_validation_report"] == str(cli_report_out)
    assert summary["supported_preview_analysis_types"] == [
        "model_health",
        "linear_static_axial_truss",
        "nonlinear_static_material_mesh_axial_chain",
    ]
    assert "CLI emits the same JSON envelopes as the Python API" in summary["claim_boundary"]
    assert "narrow axial-truss linear_static" in summary["claim_boundary"]
    assert "1D material-mesh nonlinear_static preview paths" in summary["claim_boundary"]
    assert "do not close general linear frame/shell" in summary["claim_boundary"]


def test_check_detects_contract_artifact_drift(tmp_path: Path) -> None:
    model_out = tmp_path / "phase1_core_api_sample_model.json"
    result_out = tmp_path / "phase1_core_api_model_health_result.json"
    report_out = tmp_path / "phase1_core_api_model_health_report.json"
    cli_result_out = tmp_path / "phase1_core_api_cli_model_health_result.json"
    cli_report_out = tmp_path / "phase1_core_api_cli_model_health_report.json"
    summary_out = tmp_path / "phase1_core_api_contract_summary.json"

    build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
    )
    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
    )
    assert ok is True
    assert message == "phase1_core_api_contract_consistent"

    result = json.loads(result_out.read_text(encoding="utf-8"))
    result["status"] = "blocked"
    _write_json(result_out, result)

    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
    )
    assert ok is False
    assert message == "phase1_core_api_contract_mismatch:result"


def test_check_detects_cli_contract_artifact_drift(tmp_path: Path) -> None:
    model_out = tmp_path / "phase1_core_api_sample_model.json"
    result_out = tmp_path / "phase1_core_api_model_health_result.json"
    report_out = tmp_path / "phase1_core_api_model_health_report.json"
    cli_result_out = tmp_path / "phase1_core_api_cli_model_health_result.json"
    cli_report_out = tmp_path / "phase1_core_api_cli_model_health_report.json"
    summary_out = tmp_path / "phase1_core_api_contract_summary.json"

    build_phase1_core_api_contract_artifacts.write_contract_artifacts(
        repo_root=tmp_path,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
    )

    cli_result = json.loads(cli_result_out.read_text(encoding="utf-8"))
    cli_result["claim_boundary_version"] = "stale-cli-boundary"
    _write_json(cli_result_out, cli_result)

    ok, message = build_phase1_core_api_contract_artifacts.check_contract_artifacts(
        repo_root=tmp_path,
        model_out=model_out,
        result_out=result_out,
        report_out=report_out,
        cli_result_out=cli_result_out,
        cli_report_out=cli_report_out,
        summary_out=summary_out,
    )
    assert ok is False
    assert message == "phase1_core_api_contract_mismatch:cli_result"
