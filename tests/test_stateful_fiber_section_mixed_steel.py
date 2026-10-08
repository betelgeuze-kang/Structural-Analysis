"""Mixed constituent mechanics and persistence; no specimen-law calibration."""

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.materials.stateful_fiber_section import (
    FiberSectionNewtonConfig,
    finite_difference_stateful_fiber_section_tangent_check,
    make_rectangular_stateful_rc_fiber_section,
    solve_stateful_fiber_section_resultants,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


def mixed_section():
    original = make_rectangular_stateful_rc_fiber_section()
    fibers = tuple(
        replace(f, area_m2=f.area_m2 / 2) if f.fiber_id == "steel-top-layer" else f
        for f in original.fibers
    )
    other = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=195000,
        yield_stress_mpa=100,
        material_id="synthetic-top-steel",
    )
    return replace(
        original, fibers=fibers, steel_overrides=(("steel-top-layer", other),)
    )


def test_legacy_hash_is_preserved_and_elastic_stiffness_uses_each_area_and_modulus():
    original = make_rectangular_stateful_rc_fiber_section()
    assert (
        original.contract_hash
        == "sha256:dd63b15b8a78e6080b9839e629cec511d2802f2980dccdbb7042788e4a468f39"
    )
    section = mixed_section()
    old = original.integrate((0, 0), original.initial_state()).consistent_tangent
    actual = section.integrate((0, 0), section.initial_state()).consistent_tangent
    # Only the top layer changes. Independent elastic sum A*E*[1,-y]^T*[1,-y].
    y, area = 0.25, 0.001548
    expected = old + (area / 2 * 195000 - area * 200000) * 1000 * np.outer(
        [1, -y], [1, -y]
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-9)
    assert actual[0, 1] != 0
    assert section.contract_hash != original.contract_hash


def test_independent_yielding_and_reversal_preserve_each_constituent_history():
    section = mixed_section()
    parent = section.initial_state()
    response = section.integrate((0.00075, 0), parent)
    assert response.fiber_responses[-1].yielded
    assert not response.fiber_responses[-2].yielded
    history = [(0.00075, 0), (-0.003, 0.004), (0.002, -0.006), (-0.001, 0.003)]
    saved = parent.canonical_bytes()
    independent = [
        section.steel.initial_state(),
        section.steel_overrides[0][1].initial_state(),
    ]
    laws = [section.steel, section.steel_overrides[0][1]]
    state = parent
    energies = []
    for strain, curvature in history:
        before = state.canonical_bytes()
        result = section.integrate((strain, curvature), state)
        assert state.canonical_bytes() == before
        for j, fiber in enumerate(section.fibers[-2:]):
            expected = laws[j].integrate(strain - curvature * fiber.y_m, independent[j])
            independent[j] = expected.state
            assert (
                result.state.fiber_states[-2 + j].canonical_bytes()
                == expected.state.canonical_bytes()
            )
        state = result.state
        energies.append(result.dissipated_energy_mj_per_m)
    assert parent.canonical_bytes() == saved
    assert energies == sorted(energies) and energies[-1] > 0
    rebuilt = mixed_section()
    assert (
        rebuilt.integrate((0, 0), state).state.canonical_bytes()
        == section.integrate((0, 0), state).state.canonical_bytes()
    )
    check = finite_difference_stateful_fiber_section_tangent_check(section, parent)
    assert check["pass"]
    failed = solve_stateful_fiber_section_resultants(
        section,
        state,
        target_resultants=(1e6, 1e6),
        config=FiberSectionNewtonConfig(maximum_iterations=0),
    )
    assert not failed.committed and failed.accepted_state is state
    assert failed.metrics["rollback_exact"]


@pytest.mark.parametrize(
    "overrides",
    [
        [],
        (("missing", BilinearCombinedHardeningSteel()),),
        (("concrete-00", BilinearCombinedHardeningSteel()),),
        (("steel-top-layer", object()),),
        (("steel-top-layer", BilinearCombinedHardeningSteel()),) * 2,
        (("steel-top-layer",),),
    ],
)
def test_invalid_material_assignments_are_rejected(overrides):
    with pytest.raises(ValueError):
        replace(make_rectangular_stateful_rc_fiber_section(), steel_overrides=overrides)


def test_assignment_order_is_canonical_and_material_changes_invalidate_history():
    base = mixed_section()
    assignments = base.steel_overrides + (("steel-bottom-layer", base.steel),)
    a, b = [replace(base, steel_overrides=x) for x in (assignments, assignments[::-1])]
    assert a.contract_hash == b.contract_hash
    other = replace(base.steel_overrides[0][1], yield_stress_mpa=110)
    changed = replace(base, steel_overrides=(("steel-top-layer", other),))
    assert changed.contract_hash != base.contract_hash
    with pytest.raises(ValueError, match="section_contract_hash"):
        changed.integrate((0, 0), base.initial_state())
    with pytest.raises(ValueError, match="existing steel fiber"):
        base.steel_material_for("unknown")


def test_frame_checkpoint_and_material_projection_bind_distinct_steel():
    from structural_analysis.assembly import (
        dump_stateful_fiber_frame2d_checkpoint_bytes,
        initial_stateful_fiber_frame2d_checkpoint,
        load_stateful_fiber_frame2d_checkpoint_bytes,
    )
    from structural_analysis.assembly.stateful_fiber_frame2d_material_state_bundle import (
        create_initial_fiber_frame_material_state_projection,
    )
    from structural_analysis.benchmark import make_two_element_stateful_fiber_cantilever

    original = make_two_element_stateful_fiber_cantilever()
    section = mixed_section()
    problem = replace(
        original,
        members=tuple(
            replace(m, element=replace(m.element, section=section))
            for m in original.members
        ),
    )
    checkpoint = initial_stateful_fiber_frame2d_checkpoint(problem)
    raw = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, checkpoint)
    restored = load_stateful_fiber_frame2d_checkpoint_bytes(raw, problem)
    assert restored.canonical_bytes() == checkpoint.canonical_bytes()
    with pytest.raises(ValueError):
        load_stateful_fiber_frame2d_checkpoint_bytes(raw, original)
    projection = create_initial_fiber_frame_material_state_projection(
        problem,
        restored,
        model_ir_content_hash="sha256:" + "1" * 64,
        execution_plan_hash="sha256:" + "2" * 64,
        solver_state_hash="sha256:" + "3" * 64,
    )
    assert any(
        entry.material_type_id == "synthetic-top-steel"
        for entry in projection.bundle.entries
    )


@pytest.mark.parametrize("yield_stress", [100, 404])
def test_mixed_steel_terminal_recovery_replays_bound_constituent_laws(
    monkeypatch, yield_stress
):
    from tests import test_stateful_fiber_frame2d_nonlinear_terminal_receipt as helper
    from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
        create_fiber_frame_nonlinear_numerical_result_adapter,
    )
    from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_recovery import (
        create_fiber_frame_nonlinear_recovery_operator,
    )

    original = helper.make_two_member_stateful_fiber_l_frame()
    members = []
    for member in original.members:
        section = member.element.section
        different = replace(
            section.steel,
            elastic_modulus_mpa=195000,
            yield_stress_mpa=yield_stress,
            material_id="synthetic-recovery-steel",
        )
        section = replace(section, steel_overrides=(("steel-top-layer", different),))
        members.append(
            replace(member, element=replace(member.element, section=section))
        )
    mixed = replace(original, members=tuple(members))
    monkeypatch.setattr(helper, "make_two_member_stateful_fiber_l_frame", lambda: mixed)
    if yield_stress == 100:
        # Preserve the original failed full-load case, not an easier load path.
        # This is an observed bounded Newton failure, not a capacity prediction.
        path = helper.run_stateful_fiber_frame2d_load_path(
            mixed,
            helper.LOAD_FACTORS,
            config=helper.NewtonRaphsonConfig(max_iterations=40),
        )
        assert not path.contract_pass
        assert [step.committed for step in path.steps] == [True, True, True, False]
        failed = path.steps[-1]
        assert failed.metrics["rollback_exact"]
        assert (
            failed.accepted_checkpoint.canonical_bytes()
            == failed.parent_checkpoint.canonical_bytes()
        )
        from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
            StatefulFiberFrame2DCheckpointChainArtifactError,
        )

        with pytest.raises(StatefulFiberFrame2DCheckpointChainArtifactError):
            helper._artifacts()
        return
    (
        problem,
        path,
        checkpoints,
        plan,
        scaling,
        kinematic,
        material,
        execution_state,
        terminal,
    ) = helper._artifacts()
    assert path.contract_pass
    adapter = create_fiber_frame_nonlinear_numerical_result_adapter(
        problem,
        plan,
        scaling,
        checkpoints,
        kinematic,
        material,
        execution_state,
        path,
        terminal,
    )
    operator = create_fiber_frame_nonlinear_recovery_operator(adapter)
    assert operator.state_bytes_exact
    expected = np.asarray(
        [
            stress
            for member in path.steps[-1].trial_assembly.member_assemblies
            for section in member.response.section_responses
            for stress in section.fiber_stresses_mpa
        ]
    )
    np.testing.assert_array_equal(operator.array("fiber_stress_mpa"), expected)
