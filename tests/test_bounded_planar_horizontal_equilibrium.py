"""Global statics regressions independent of rounded external solver values."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_result,
)
from structural_analysis.model_ir import parse_model_ir_v2


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize(
    ("fixture", "horizontal_force_n"),
    [
        ("bounded_planar_frame_alpha.model-ir.v2.json", 0.0),
        ("bounded_planar_frame_alpha.model-ir.v2.json", -1000.0),
        ("bounded_planar_frame_alpha.model-ir.v2.json", 1000.0),
        ("bounded_planar_settlement.model-ir.v2.json", -1000.0),
        ("bounded_planar_settlement.model-ir.v2.json", 1000.0),
    ],
)
def test_horizontal_support_reaction_balances_declared_dead_load(
    fixture: str, horizontal_force_n: float
) -> None:
    payload = json.loads((EXAMPLES / fixture).read_text(encoding="utf-8"))
    # Both beams are initially horizontal, with no horizontal distributed load
    # or self-weight. Only N1 constrains UX. Consequently global statics gives
    # R_N1_X = -F_N2_X regardless of axial stiffness, offsets or end releases.
    assert [node["coordinates_m"][1] for node in payload["nodes"]] == [0.0, 0.0]
    assert [
        row["node_id"] for row in payload["constraints"] if "UX" in row["dofs"]
    ] == ["N1"]
    for element in payload["elements"]:
        load = element["uniform_distributed_load_local"]
        assert load["behavior"] == "dead"
        assert load["basis"] == "initial_member_local"
        assert load["qx_n_per_m"] == 0.0
        for offset in element["offsets"].values():
            assert offset[1:] == [0.0, 0.0]
    pattern = payload["load_patterns"][0]
    assert pattern["self_weight"] == [0.0, 0.0, 0.0]
    if horizontal_force_n:
        template = json.loads(
            (EXAMPLES / "bounded_planar_settlement.model-ir.v2.json").read_text(
                encoding="utf-8"
            )
        )["load_patterns"][0]["nodal_loads"][0]
        load = deepcopy(template)
        load["components_si"]["FX"] = horizontal_force_n
        pattern["nodal_loads"] = [load]
    else:
        pattern["nodal_loads"] = []

    document = parse_model_ir_v2(payload)
    result = analyze_nonlinear_frame_model_ir(
        document,
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=4,
            residual_tolerance=1.0e-9,
            maximum_iterations=80,
        ),
    )
    assert result.status == "ready" and result.contract_pass
    assert validate_nonlinear_frame_result(result).contract_pass
    assert result.input_checksum == document.content_hash
    assert result.metrics["committed_step_count"] == 4
    assert result.metrics["exact_engineering_recovery"] is True
    assert result.metrics["exact_checkpoint_chain_replay"] is True
    horizontal_reactions = [
        row for row in result.support_reactions if row["dof"] == "UX"
    ]
    assert [row["node_id"] for row in horizontal_reactions] == ["N1"]
    reaction = float(horizontal_reactions[0]["value_si"])
    # Retain the existing code-to-code absolute/relative tolerance, without
    # using an external free-DOF residual as a physical support reaction.
    tolerance = 1.0e-10 + 1.0e-10 * max(abs(horizontal_force_n), 1.0)
    assert math.isfinite(reaction)
    assert abs(math.fsum((reaction, horizontal_force_n))) <= tolerance
