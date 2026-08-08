from pathlib import Path

from structural_analysis.model_ir import load_model_ir_v2


def test_contact_model_ir_is_analysis_ready_and_typed() -> None:
    document = load_model_ir_v2(Path("tests/fixtures/model_ir_v2/contact_frictionless_static.json"))
    contact = document.to_dict()["contact"]
    assert document.analysis_ready
    assert document.capability_profile == "contact_frictionless_static_v1"
    assert contact["profile"] == "frictionless_unilateral_gap_active_set.v1"
    assert len(contact["dof_ids"]) == len(contact["contact_ids"]) == 2
