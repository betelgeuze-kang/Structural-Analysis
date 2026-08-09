from pathlib import Path

from structural_analysis.model_ir import load_model_ir_v2


FIXTURE = Path("tests/fixtures/model_ir_v2/shell_square_linear_static.json")


def test_shell_model_ir_is_analysis_ready() -> None:
    document = load_model_ir_v2(FIXTURE)
    payload = document.to_dict()

    assert document.analysis_ready
    assert document.capability_profile == "shell_linear_static_v1"
    assert [row["family_id"] for row in payload["sections"]] == ["shell_3"]
    assert all(row["type"] == "shell_3" and len(row["node_ids"]) == 3 for row in payload["elements"])
