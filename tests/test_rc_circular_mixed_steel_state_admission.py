"""Authored circular-fiber state custody; no measured material or specimen claim."""

from dataclasses import replace
import json
import math
from pathlib import Path

import pytest

from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.assembly import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d_checkpoint_io as checkpoint_io,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def _compiled_problem(law_difference):
    data = json.loads(
        (
            Path(__file__).parents[1]
            / "examples/public_rc_fiber_frame_explicit_layers.json"
        ).read_text()
    )
    data["nodes"][1]["coordinates"] = [1.0, 0.0, 0.0]
    data["supports"].append({"node": "N2", "dofs": ["UY", "RZ"]})
    data["loads"][0]["components"].update(FX=10000.0, FY=0.0)
    steel, concrete, other = data["materials"]
    other.update(
        elastic_modulus_mpa=steel["elastic_modulus_mpa"],
        yield_stress_mpa=steel["yield_stress_mpa"],
    )
    if law_difference == "yield":
        other["yield_stress_mpa"] = 100.0
    else:
        other["kinematic_hardening_modulus_mpa"] = 17000.0
    # Elastic authored concrete isolates steel custody from softening failures.
    concrete.update(tensile_strength_mpa=1e6, compressive_strength_mpa=1e6)
    layer = data["sections"][0]["steel_layers"][0]
    data["sections"][0]["steel_layers"] = [
        dict(
            layer,
            id=layer_id,
            y_m=y,
            steel_material=material,
            circular_integration_points=4,
        )
        for layer_id, y, material in (
            ("bottom", -0.25, "steel"),
            ("top", 0.25, "hanger"),
        )
    ]
    model = load_neutral_json_bytes(json.dumps(data).encode())
    return compile_rc_corotational_control_model(
        model, experimental_fixed_guided_axial=True
    ).problem


@pytest.mark.parametrize("law_difference", ["yield", "kinematic"])
def test_circular_mixed_steel_cyclic_checkpoint_rejects_coherent_law_swap(
    law_difference,
):
    problem = _compiled_problem(law_difference)
    section = problem.members[0].element.section
    point_indices = [
        i
        for i, fiber in enumerate(section.fibers)
        if fiber.fiber_id.startswith("steel-circular-")
    ]
    assert len(point_indices) == 8
    assert all(
        math.isfinite(section.fibers[i].area_m2)
        and section.fibers[i].area_m2 > 0.0
        and math.isfinite(section.fibers[i].y_m)
        for i in point_indices
    )
    targets = (0.003, -0.004, 0.005, -0.002, 0.004)
    full = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, targets, control_global_dof=3, allow_reversal=True
    )
    prefix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, targets[:3], control_global_dof=3, allow_reversal=True
    )
    assert full.contract_pass and prefix.contract_pass
    parent = prefix.final_checkpoint
    original_bytes = parent.canonical_bytes()
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(problem, parent)
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, problem)
    assert restored.canonical_bytes() == original_bytes
    resumed = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets[3:],
        initial_checkpoint=restored,
        control_global_dof=3,
        allow_reversal=True,
    )
    assert resumed.contract_pass
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )

    element = restored.element_states[0]
    basic = element.basic_beam_state
    state = basic.integration_point_states[0]
    assert all(
        state.fiber_states[i].accumulated_plastic_strain > 0.0 for i in point_indices
    )
    left, right = (
        next(
            i
            for i in point_indices
            if section.fibers[i].fiber_id.startswith(f"steel-circular-{layer}-")
        )
        for layer in ("bottom", "top")
    )
    fibers = list(state.fiber_states)
    fibers[left], fibers[right] = fibers[right], fibers[left]
    swapped_section = replace(state, fiber_states=tuple(fibers))
    swapped_basic = replace(
        basic,
        integration_point_states=(swapped_section, *basic.integration_point_states[1:]),
    )
    swapped_element = replace(element, basic_beam_state=swapped_basic)
    forged = replace(restored, element_states=(swapped_element,), state_hash="")
    assert forged.state_hash == forged.compute_state_hash()
    assert forged.state_hash != restored.state_hash
    assert forged.global_displacements == restored.global_displacements
    assert forged.problem_contract_hash == restored.problem_contract_hash

    # Prove schema, canonical bytes and nested hashes pass before law admission.
    payload = forged.to_dict()
    checkpoint_io._validate_schema(payload)
    forged_raw = checkpoint_io._artifact_json_bytes(payload)
    decoded_element = checkpoint_io._restore_corotational_element_state(
        problem.members[0].element.initial_state(),
        payload["element_states"][0],
        path="/element_states/0",
    )
    assert decoded_element.canonical_bytes() == swapped_element.canonical_bytes()
    assert json.loads(forged_raw)["state_hash"] == forged.compute_state_hash()

    invariant = "energy" if law_difference == "yield" else "backstress"
    for operation in (
        lambda: validate_stateful_corotational_fiber_frame2d_checkpoint(
            problem, forged
        ),
        lambda: dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
            problem, forged
        ),
        lambda: load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
            forged_raw, problem
        ),
    ):
        with pytest.raises(ValueError) as rejected:
            operation()
        cause = rejected.value
        while cause.__cause__ is not None:
            cause = cause.__cause__
        assert invariant in str(cause)
    assert parent.canonical_bytes() == original_bytes
    assert restored.canonical_bytes() == original_bytes
    assert (
        dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(problem, parent)
        == raw
    )
