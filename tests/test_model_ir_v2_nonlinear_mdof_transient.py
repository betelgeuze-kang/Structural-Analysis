from __future__ import annotations

from pathlib import Path

from structural_analysis.model_ir import load_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]


def test_nonlinear_mdof_model_ir_binds_story_materials_and_force_source() -> None:
    document = load_model_ir_v2(
        ROOT / "tests/fixtures/model_ir_v2/nonlinear_mdof_transient.json"
    )
    dynamics = document.to_dict()["dynamics"]
    assert document.analysis_ready is True
    assert document.capability_profile == "nonlinear_mdof_transient_v1"
    assert dynamics["profile"] == "newmark_consistent_newton_bilinear_shear_mdof.v1"
    assert len(dynamics["stories"]) == 2
    assert all(row["yield_force_n"] > 0.0 for row in dynamics["stories"])
