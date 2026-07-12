from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = ROOT / "implementation/phase1/release_evidence/productization"


def _read(name: str) -> dict[str, object]:
    payload = json.loads((PRODUCTIZATION / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_tracked_phase1_summary_exposes_authoritative_frame_contract() -> None:
    summary = _read("phase1_core_api_contract_summary.json")
    contract = summary["authoritative_linear_static_contract"]

    assert summary["schema_version"] == "phase1-core-api-contract-artifacts.v2"
    assert summary["contract_pass"] is True
    assert "linear_static_3d_frame_cpu_reference_v1" in summary[
        "supported_preview_analysis_types"
    ]
    assert contract["status"] == "ready"
    assert contract["contract_pass"] is True
    assert contract["solver_path_id"] == "authoritative_cpu_linear_fea_3d_v1"
    assert contract["load_case"] == "LC1"
    assert contract["python_api_cli_equal"] is True
    assert contract["viewer_source"] == "authoritative_solver_result"
    assert contract["viewer_solver_path_id"] == contract["solver_path_id"]
    assert contract["fallback_used"] is False
    assert contract["regularization_used"] is False


def test_tracked_frame_result_and_cli_result_are_identical() -> None:
    result = _read("phase1_core_api_frame_result.json")
    cli_result = _read("phase1_core_api_frame_cli_result.json")
    report = _read("phase1_core_api_frame_report.json")
    cli_report = _read("phase1_core_api_frame_cli_report.json")

    assert result == cli_result
    assert report == cli_report
    assert result["status"] == "ready"
    assert result["solver"] == "authoritative_cpu_linear_fea_3d_v1"
    assert result["metrics"]["claim_boundary"] == (
        "linear_static_3d_frame_cpu_reference_v1"
    )
    assert result["metrics"]["viewer_payload"]["solver_path_id"] == result["solver"]
    assert report["contract_pass"] is True
