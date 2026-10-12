"""Native concrete-state custody over synthetic, actually solved cyclic states.

These checks establish constitutive-state admission, not specimen validation,
public replay bypass, or authenticated report injection.
"""

from dataclasses import replace
import json
from pathlib import Path
from typing import cast

import pytest

from structural_analysis.assembly import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d_checkpoint_io as checkpoint_io,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.elements.axial_curvature_section import AxialCurvatureSection
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.materials import concrete_damage
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageState,
)
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityState,
)


TURNS = (0.0, 0.005, 0.01, -0.005, -0.01, 0.005)
TARGETS = tuple(
    start + (stop - start) * index / 10
    for start, stop in zip(TURNS[:-1], TURNS[1:])
    for index in range(1, 11)
)
SPLIT = 25


def _problem():
    coordinates = ((0.0, 0.0), (0.0, 1.0))
    section = make_rectangular_stateful_rc_fiber_section(
        width_m=0.2,
        depth_m=0.2,
        cover_m=0.03,
        concrete_layer_count=8,
        top_bar_count=2,
        bottom_bar_count=2,
        bar_area_m2=0.0002,
        section_id="synthetic-concrete-admission",
        steel=BilinearCombinedHardeningSteel(
            elastic_modulus_mpa=200000,
            yield_stress_mpa=400,
            isotropic_hardening_modulus_mpa=1000,
            kinematic_hardening_modulus_mpa=1000,
        ),
        concrete=AsymmetricConcreteDamageMaterial(
            elastic_modulus_mpa=30000,
            tensile_strength_mpa=3,
            compressive_strength_mpa=30,
            tensile_softening_rate=20,
            compressive_softening_rate=20,
        ),
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="synthetic-native-concrete-admission",
        node_coordinates_m=coordinates,
        members=(
            StatefulCorotationalFiberFrame2DMember(
                member_id="member",
                node_i=0,
                node_j=1,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=coordinates,
                    section=cast(AxialCurvatureSection, section),
                    integration_order=3,
                    element_id="member",
                ),
            ),
        ),
        fixed_global_dofs=(0, 1, 2),
        reference_external_loads=((3, 1.0),),
        fixed_external_loads=((4, -10.0),),
        rotation_coordinate_scale_m=1.0,
    )


@pytest.fixture(scope="module")
def cyclic_record():
    checkout = Path(__file__).resolve().parents[1]
    assert Path(concrete_damage.__file__).resolve() == (
        checkout / "src/structural_analysis/materials/concrete_damage.py"
    )
    assert Path(checkpoint_io.__file__).resolve() == (
        checkout
        / "src/structural_analysis/assembly"
        / "stateful_corotational_fiber_frame2d_checkpoint_io.py"
    )
    problem = _problem()
    options = dict(
        control_global_dof=3,
        allow_reversal=True,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=40,
        ),
    )
    preload = solve_stateful_corotational_fiber_frame2d_load_step(
        problem,
        initial_stateful_corotational_fiber_frame2d_checkpoint(problem),
        target_load_factor=0.0,
    )
    assert preload.committed
    full = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, TARGETS, initial_checkpoint=preload.accepted_checkpoint, **options
    )
    prefix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        TARGETS[:SPLIT],
        initial_checkpoint=preload.accepted_checkpoint,
        **options,
    )
    assert full.contract_pass and prefix.contract_pass
    assert all(step.committed for step in (*full.steps, *prefix.steps))
    original = prefix.final_checkpoint
    original_bytes = original.canonical_bytes()
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(problem, original)
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, problem)
    resumed = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        TARGETS[SPLIT:],
        initial_checkpoint=restored,
        **options,
    )
    assert resumed.contract_pass
    assert original.canonical_bytes() == original_bytes
    assert restored.canonical_bytes() == original_bytes
    assert raw == dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem, restored
    )
    assert resumed.final_checkpoint.canonical_bytes() == (
        full.final_checkpoint.canonical_bytes()
    )
    return problem, original, raw, full.final_checkpoint


def test_genuine_nonlinear_cyclic_checkpoint_roundtrip_and_restart(cyclic_record):
    problem, original, raw, terminal = cyclic_record
    section = problem.members[0].element.section
    material_states = [
        state
        for point in terminal.element_states[
            0
        ].basic_beam_state.integration_point_states
        for state in point.fiber_states
    ]
    concrete_states = [
        state for state in material_states if type(state) is ConcreteDamageState
    ]
    steel_states = [
        state for state in material_states if type(state) is UniaxialPlasticityState
    ]
    assert concrete_states and steel_states
    assert max(state.tensile_damage for state in concrete_states) > 0
    assert max(state.compressive_damage for state in concrete_states) > 0
    assert (
        max(state.dissipated_energy_density_mj_per_m3 for state in concrete_states) > 0
    )
    assert max(state.accumulated_plastic_strain for state in steel_states) > 0
    for state in concrete_states:
        section.concrete.validate_state_admissibility(state)
    assert original.epoch == SPLIT + 1
    assert terminal.epoch == len(TARGETS) + 1
    assert original.global_displacements[3] == pytest.approx(TARGETS[SPLIT - 1])
    assert terminal.global_displacements[3] == pytest.approx(TARGETS[-1])
    assert raw == dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem, original
    )


def _forged_container(problem, original, corruption):
    element = original.element_states[0]
    basic = element.basic_beam_state
    point = basic.integration_point_states[0]
    index = next(
        i
        for i, state in enumerate(point.fiber_states)
        if type(state) is ConcreteDamageState
    )
    if corruption == "zero_history_energy":
        impossible = ConcreteDamageState(dissipated_energy_density_mj_per_m3=1.0)
        invariant = "dissipated energy"
    else:
        assert corruption == "zero_history_damage"
        impossible = ConcreteDamageState(compressive_damage=0.5)
        invariant = "damage is inconsistent"
    section = problem.members[0].element.section
    with pytest.raises(ValueError, match=invariant):
        section.concrete.validate_state_admissibility(impossible)
    fibers = list(point.fiber_states)
    fibers[index] = impossible
    forged_point = replace(point, fiber_states=tuple(fibers))
    forged_basic = replace(
        basic,
        integration_point_states=(forged_point, *basic.integration_point_states[1:]),
    )
    forged_element = replace(element, basic_beam_state=forged_basic)
    forged = replace(
        original,
        element_states=(forged_element, *original.element_states[1:]),
        state_hash="",
    )
    # Rebuild each enclosing hash, keeping the original geometry and ancestry.
    for before, after in (
        (point, forged_point),
        (basic, forged_basic),
        (element, forged_element),
        (original, forged),
    ):
        assert before.state_hash != after.state_hash
        assert before.canonical_bytes() != after.canonical_bytes()
    assert forged.state_hash == forged.compute_state_hash()
    assert forged.problem_contract_hash == original.problem_contract_hash
    assert forged.parent_state_hash == original.parent_state_hash
    assert forged.global_displacements == original.global_displacements
    assert (forged.epoch, forged.step_index) == (original.epoch, original.step_index)
    payload = forged.to_dict()
    checkpoint_io._validate_schema(payload)
    raw = checkpoint_io._artifact_json_bytes(payload)
    assert json.loads(raw)["state_hash"] == forged.compute_state_hash()
    decoded = checkpoint_io._restore_corotational_element_state(
        problem.members[0].element.initial_state(),
        payload["element_states"][0],
        path="/element_states/0",
    )
    assert decoded.canonical_bytes() == forged_element.canonical_bytes()
    return forged, forged_point, raw, invariant


@pytest.mark.parametrize("corruption", ("zero_history_energy", "zero_history_damage"))
@pytest.mark.parametrize("entrypoint", ("section", "frame", "dump", "load"))
def test_native_admission_rejects_coherently_rehashed_impossible_concrete(
    cyclic_record, corruption, entrypoint
):
    problem, original, original_raw, _terminal = cyclic_record
    original_bytes = original.canonical_bytes()
    original_layers = (
        original.element_states[0].basic_beam_state.integration_point_states[0],
        original.element_states[0].basic_beam_state,
        original.element_states[0],
        original,
    )
    layer_bytes = tuple(layer.canonical_bytes() for layer in original_layers)
    forged, point, raw, invariant = _forged_container(problem, original, corruption)
    try:
        with pytest.raises(ValueError) as rejected:
            if entrypoint == "section":
                problem.members[0].element.section.validate_state(point)
            elif entrypoint == "frame":
                validate_stateful_corotational_fiber_frame2d_checkpoint(problem, forged)
            elif entrypoint == "dump":
                dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
                    problem, forged
                )
            else:
                assert entrypoint == "load"
                load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, problem)
        cause = rejected.value
        while cause.__cause__ is not None:
            cause = cause.__cause__
        assert invariant in str(cause)
    finally:
        assert original.canonical_bytes() == original_bytes
        assert (
            tuple(layer.canonical_bytes() for layer in original_layers) == layer_bytes
        )
        assert (
            original_raw
            == dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
                problem, original
            )
        )
