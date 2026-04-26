from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_contact_readiness_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_contact_readiness_gate_passes_for_bounded_wheel_rail_contact_evidence(tmp_path: Path) -> None:
    schema_path = tmp_path / "vehicle_model_schema.json"
    vti_path = tmp_path / "vti_coupled_solver_report.json"
    whitebox_path = tmp_path / "whitebox_validation_report.md"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    out_path = tmp_path / "contact_readiness_report.json"

    _write_json(
        schema_path,
        {
            "type": "object",
            "properties": {
                "contact_model": {"type": "string", "enum": ["hertzian", "custom"]},
                "hertz_contact": {"type": "object", "properties": {"contact_stiffness_N_m_3_2": {"type": "number"}}},
            },
        },
    )
    _write_json(
        vti_path,
        {
            "checks": {
                "finite_response": True,
                "coupling_converged_ratio_pass": True,
                "adaptive_newton_converged_pass": True,
            },
            "metrics": {
                "converged_ratio": 0.99375,
                "max_contact_force_n": 6.522349912820334,
            },
            "inputs": {"config": {"hertz_k_n_m_3_2": 1.05e9}},
        },
    )
    _write_text(
        whitebox_path,
        "\n".join(
            [
                "# White-box Validation Report",
                "",
                "| Domain | Case | Metric | LF rel err | GNN rel err | Improved |",
                "|---|---|---:|---:|---:|---:|",
                "| track | track_moving_load_span | contact_force_kN | 0.0324 | 0.0048 | true |",
            ]
        ),
    )
    _write_text(
        roadmap_path,
        "\n".join(
            [
                "- contact / gap / uplift / compression-only 계열 부족",
                "- gap, uplift, bearing, isolator, friction, pounding",
            ]
        ),
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--vehicle-model-schema",
            str(schema_path),
            "--vti-report",
            str(vti_path),
            "--whitebox-report",
            str(whitebox_path),
            "--roadmap",
            str(roadmap_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["contact_schema_pass"] is True
    assert payload["checks"]["contact_solver_evidence_pass"] is True
    assert payload["checks"]["contact_whitebox_evidence_pass"] is True
    assert payload["checks"]["structural_contact_gap_tracked"] is True
    assert payload["coverage_scope"] == "wheel_rail_hertzian_contact_only"
    assert payload["coverage_grade"] == "bounded_contact_ready"
    assert payload["summary_line"].startswith("Contact readiness: PASS")
    assert "structural_contact=tracked_gap" in payload["summary_line"]


def test_contact_readiness_gate_classifies_gap_when_contact_evidence_is_missing(tmp_path: Path) -> None:
    schema_path = tmp_path / "vehicle_model_schema.json"
    vti_path = tmp_path / "vti_coupled_solver_report.json"
    whitebox_path = tmp_path / "whitebox_validation_report.md"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    out_path = tmp_path / "contact_readiness_report.json"

    _write_json(
        schema_path,
        {
            "type": "object",
            "properties": {
                "contact_model": {"type": "string", "enum": ["hertzian", "custom"]},
                "hertz_contact": {"type": "object"},
            },
        },
    )
    _write_json(
        vti_path,
        {
            "checks": {
                "finite_response": True,
                "coupling_converged_ratio_pass": False,
                "adaptive_newton_converged_pass": False,
            },
            "metrics": {
                "converged_ratio": 0.25,
                "max_contact_force_n": 0.0,
            },
            "inputs": {"config": {"hertz_k_n_m_3_2": 0.0}},
        },
    )
    _write_text(
        whitebox_path,
        "\n".join(
            [
                "# White-box Validation Report",
                "",
                "| Domain | Case | Metric | LF rel err | GNN rel err | Improved |",
                "|---|---|---:|---:|---:|---:|",
                "| track | track_moving_load_span | disp_max_mm | 0.0677 | 0.0129 | true |",
            ]
        ),
    )
    _write_text(roadmap_path, "- contact / gap / uplift / compression-only 계열 부족")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--vehicle-model-schema",
            str(schema_path),
            "--vti-report",
            str(vti_path),
            "--whitebox-report",
            str(whitebox_path),
            "--roadmap",
            str(roadmap_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CONTACT_SOLVER_EVIDENCE_FAIL"
    assert payload["checks"]["contact_schema_pass"] is True
    assert payload["checks"]["contact_solver_evidence_pass"] is False
    assert payload["checks"]["contact_whitebox_evidence_pass"] is False
    assert payload["coverage_grade"] == "tracked_gap"
    assert payload["summary_line"].startswith("Contact readiness: GAP")
    assert "solver=no" in payload["summary_line"]
