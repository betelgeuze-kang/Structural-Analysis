from __future__ import annotations

from pathlib import Path

from structural_analysis.model_ir import load_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "tests/fixtures/model_ir_v2/mdof_linear_transient.json"


def test_mdof_linear_transient_model_ir_is_analysis_ready() -> None:
    document = load_model_ir_v2(MODEL)
    dynamics = document.to_dict()["dynamics"]

    assert document.analysis_ready is True
    assert document.capability_profile == "mdof_linear_transient_v1"
    assert dynamics["profile"] == "newmark_average_acceleration_linear_mdof.v1"
    assert len(dynamics["dof_ids"]) == 2
    assert dynamics["checkpoint_authority"] == "source_authenticated_checkpoint"
