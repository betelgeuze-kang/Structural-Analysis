from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.run_steel_composite_constitutive_gate import build_report, main


def test_build_report_passes_default_benchmark_matrix() -> None:
    report = build_report()

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["steel"]["row_count"] == 16
    assert report["summary"]["steel"]["pass_count"] == 16
    assert report["summary"]["composite"]["row_count"] == 12
    assert report["summary"]["composite"]["pass_count"] == 12
    assert report["summary"]["steel"]["yield_ratio_max"] > 1.0
    assert report["summary"]["steel"]["buckling_strength_retention_ratio_min"] < 1.0
    assert report["summary"]["steel"]["fracture_strain_ratio_max"] >= 1.0
    assert "compression_local_buckling" in report["summary"]["steel"]["state_tags"]
    assert "fracture_limit" in report["summary"]["steel"]["state_tags"]
    assert report["summary"]["composite"]["action_ratio_min"] > 0.0
    assert report["summary"]["composite"]["action_ratio_max"] == 1.0
    assert report["summary"]["composite"]["tension_carry_ratio_min"] == 0.10
    assert report["summary"]["composite"]["connector_state_tags"] == [
        "full_interaction",
        "partial_interaction",
        "residual_interaction",
    ]
    assert report["checks"]["steel_state_coverage_pass"] is True
    assert report["checks"]["steel_yield_ratio_pass"] is True
    assert report["checks"]["steel_post_yield_tangent_pass"] is True
    assert report["checks"]["steel_local_buckling_pass"] is True
    assert report["checks"]["steel_fracture_pass"] is True
    assert report["checks"]["steel_fracture_ratio_pass"] is True
    assert report["checks"]["composite_state_coverage_pass"] is True
    assert report["checks"]["composite_partial_interaction_pass"] is True
    assert report["checks"]["composite_slip_pass"] is True
    assert report["checks"]["composite_tension_limit_pass"] is True
    assert report["checks"]["composite_tension_ratio_pass"] is True
    assert report["checks"]["composite_residual_gain_pass"] is True
    assert "steel_constitutive_library" in report["summary"]["libraries"]
    assert "composite_constitutive_library" in report["summary"]["libraries"]
    assert "bond_slip_interface" in report["summary"]["libraries"]
    assert "steel=16/16(states=4" in report["summary_line"]
    assert "composite=12/12(conn=3" in report["summary_line"]


def test_main_fails_when_required_steel_rows_exceed_available_matrix(tmp_path: Path) -> None:
    out = tmp_path / "steel_composite_constitutive_gate_report.json"

    rc = main(
        [
            "--min-steel-rows",
            "17",
            "--out",
            str(out),
        ]
    )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_STEEL_CONSTITUTIVE"
    assert report["summary"]["steel"]["row_count"] == 16
    assert report["checks"]["steel_rows_sufficient"] is False
