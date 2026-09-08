"""Bounded small-displacement RC control, separate from public J1-J5 authority.

The low-load cantilever remains in its elastic range using the existing RC
materials. The compiled L-frame retains the published steel/concrete laws;
finite differences are assembler checks, not an independent physical benchmark.
"""

from copy import copy, deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import (
    initial_stateful_fiber_frame2d_checkpoint,
    solve_stateful_fiber_frame2d_load_step,
)
from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


ROOT = Path(__file__).resolve().parents[1]
RC_MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
Config = control.StatefulFiberFrame2DDisplacementControlConfig
Adapter = control.StatefulFiberFrame2DDisplacementControlStepAdapter
solve_control = control.solve_stateful_fiber_frame2d_displacement_control_step

# Exact first 15 targets of the declared continuation-refinement development
# probe. The final value below is one bounded unloading step, not a full cycle.
# Do not reconstruct these floats with linspace or search for a passing target.
YIELDED_RC_TARGETS_M = (
    -0.0004,
    -0.0008,
    -0.0012000000000000001,
    -0.0016,
    -0.002,
    -0.0024000000000000002,
    -0.0028,
    -0.0032,
    -0.0036,
    -0.004,
    -0.0044,
    -0.0048000000000000004,
    -0.0052,
    -0.0056,
    -0.006,
    -0.0056,
)


def _fiber_states(checkpoint):
    return tuple(
        state
        for element in checkpoint.element_states
        for section in element.integration_point_states
        for state in section.fiber_states
    )


def _forbid(*args, **kwargs):
    pytest.fail("this boundary must reject before numerical execution")


@pytest.fixture(autouse=True)
def no_public_analysis(monkeypatch):
    # Compilation below is allowed. None of these internal checks invokes the
    # public analysis/recovery pipeline or changes its authority contract.
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", _forbid)


@pytest.fixture(scope="module")
def rc_problem():
    compiled, blockers, _ = public_api._compile(load_neutral_json(RC_MODEL))
    assert compiled is not None and not blockers
    return compiled.problem


@pytest.fixture(scope="module")
def elastic_pair():
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    parent_bytes = parent.canonical_bytes()
    force = solve_stateful_fiber_frame2d_load_step(
        problem, parent, target_load_factor=1.0
    )
    assert force.status == "ready" and force.committed is True
    target = force.accepted_checkpoint.global_displacements[7]
    direct = solve_control(
        problem, parent, control_global_dof=7, target_control_displacement_m=target
    )
    assert parent.canonical_bytes() == parent_bytes
    return SimpleNamespace(
        problem=problem,
        parent=parent,
        parent_bytes=parent_bytes,
        force=force,
        direct=direct,
        target=target,
    )


def test_low_load_direct_control_matches_existing_force_path(elastic_pair):
    pair = elastic_pair
    result = pair.direct
    assert result.status == "ready" and result.committed is True
    assert pair.target < 0.0
    expected_tip = -10.0 * 3.0**3 / (3.0 * 253_200.0)
    assert result.accepted_checkpoint.global_displacements[7] == pytest.approx(
        expected_tip, abs=1.0e-12
    )
    np.testing.assert_allclose(
        result.accepted_checkpoint.global_displacements,
        pair.force.accepted_checkpoint.global_displacements,
        rtol=1.0e-10,
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        result.trial_assembly.reactions_global,
        pair.force.trial_assembly.reactions_global,
        rtol=1.0e-9,
        atol=1.0e-8,
    )
    assert result.accepted_checkpoint.load_factor == pytest.approx(1.0, abs=1.0e-9)
    assert result.accepted_checkpoint.epoch == pair.parent.epoch + 1
    assert result.accepted_checkpoint.parent_state_hash == pair.parent.state_hash
    assert result.parent_checkpoint is pair.parent
    assert result.metrics["control_gate_passed"] is True
    assert result.metrics["equilibrium_gate_passed"] is True
    assert result.metrics["solver_contract_pass"] is True
    assert result.metrics["section_and_element_parent_binding_passed"] is True
    assert result.metrics["parent_checkpoint_immutable"] is True
    steel = [
        state
        for state in _fiber_states(result.accepted_checkpoint)
        if type(state) is UniaxialPlasticityState
    ]
    assert steel and all(state.accumulated_plastic_strain == 0.0 for state in steel)


def test_accepted_state_initial_coordinates_preserve_rotation_and_load_scale(
    elastic_pair,
):
    pair = elastic_pair
    parent = pair.direct.accepted_checkpoint
    config = Config(load_factor_coordinate_scale_m=0.007)
    adapter = Adapter(pair.problem, parent, 7, 1.1 * pair.target, config)
    z = adapter.initial_free_displacements_m()
    expected = (
        np.asarray(parent.global_displacements) / pair.problem.physical_coordinate_scale
    )[list(pair.problem.free_global_dofs)]
    np.testing.assert_array_equal(z[:-1], expected)
    assert z[-1] == parent.load_factor * config.load_factor_coordinate_scale_m
    assert adapter.reference_force_scale() > 0.0
    assert isinstance(adapter.case_id, str) and adapter.case_id
    z[:] = 0.0
    assert parent.global_displacements[7] == pytest.approx(pair.target, abs=1.0e-12)


def test_augmented_jacobian_matches_finite_difference_with_original_rc_materials(
    rc_problem,
):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    original = parent.canonical_bytes()
    config = Config(load_factor_coordinate_scale_m=0.003)
    adapter = Adapter(rc_problem, parent, 7, -1.0e-6, config)
    z = adapter.initial_free_displacements_m()
    z[:-1] = np.linspace(-2.0e-8, 3.0e-8, len(z) - 1)
    z[-1] = 0.04 * config.load_factor_coordinate_scale_m
    residual, tangent = adapter.assemble(z)
    assert residual.shape == (len(z),) and tangent.shape == (len(z), len(z))
    assert np.all(np.isfinite(residual)) and np.all(np.isfinite(tangent))
    increment = 1.0e-9
    numerical = np.empty_like(tangent)
    for index in range(len(z)):
        delta = np.zeros_like(z)
        delta[index] = increment
        plus, _ = adapter.assemble(z + delta)
        minus, _ = adapter.assemble(z - delta)
        numerical[:, index] = (plus - minus) / (2.0 * increment)
    np.testing.assert_allclose(tangent, numerical, rtol=2.0e-7, atol=1.0e-5)
    free = list(rc_problem.free_global_dofs)
    expected_load_column = (
        -rc_problem.physical_coordinate_scale[free]
        * rc_problem.reference_external_load_vector()[free]
        / config.load_factor_coordinate_scale_m
    )
    np.testing.assert_allclose(tangent[:-1, -1], expected_load_column, rtol=1.0e-14)
    assert tangent[-1, -1] == 0.0
    assert parent.canonical_bytes() == original


def test_compiled_rc_recipe_keeps_original_material_thresholds_and_fiber_layout(
    rc_problem,
):
    assert rc_problem.node_coordinates_m == ((0.0, 0.0), (2.0, 0.0), (2.0, 1.5))
    assert rc_problem.reference_external_load_vector()[7] == -150.0
    for member in rc_problem.members:
        section = member.element.section
        assert member.element.integration_order == 3
        assert len(section.fibers) == 14
        assert section.steel.elastic_modulus_mpa == 200_000.0
        assert section.steel.yield_stress_mpa == 250.0
        assert section.steel.isotropic_hardening_modulus_mpa == 3_000.0
        assert section.steel.kinematic_hardening_modulus_mpa == 5_000.0
        assert section.concrete.elastic_modulus_mpa == 30_000.0
        assert section.concrete.tensile_strength_mpa == 3.0
        assert section.concrete.compressive_strength_mpa == 30.0
        assert section.concrete.tensile_softening_rate == 3_000.0
        assert section.concrete.compressive_softening_rate == 400.0
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    assert len(_fiber_states(parent)) == 84
    assert (
        sum(type(state) is UniaxialPlasticityState for state in _fiber_states(parent))
        == 12
    )


@pytest.mark.parametrize(
    "coordinates", [[], [0.0], [False] * 7, [float("nan")] * 7, [0j] * 7]
)
def test_invalid_augmented_coordinates_fail_before_material_trial(
    rc_problem, monkeypatch, coordinates
):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    adapter = Adapter(rc_problem, parent, 7, -1.0e-6, Config())
    monkeypatch.setattr(control, "assemble_stateful_fiber_frame2d", _forbid)
    with pytest.raises((TypeError, ValueError)):
        adapter.observe(coordinates)


def test_same_target_as_parent_is_rejected_before_newton(rc_problem, monkeypatch):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    with pytest.raises(ValueError, match="differ from the parent"):
        solve_control(
            rc_problem, parent, control_global_dof=7, target_control_displacement_m=0.0
        )


@pytest.mark.parametrize("dof", [True, 7.0, -1, 9, 0, 1, 2, 8])
def test_invalid_or_nontranslational_control_fails_before_solver(
    rc_problem, monkeypatch, dof
):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    original = parent.canonical_bytes()
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    monkeypatch.setattr(control, "assemble_stateful_fiber_frame2d", _forbid)
    with pytest.raises((TypeError, ValueError)):
        solve_control(
            rc_problem,
            parent,
            control_global_dof=dof,
            target_control_displacement_m=-1.0e-6,
        )
    assert parent.canonical_bytes() == original


@pytest.mark.parametrize(
    "target", [True, float("nan"), float("inf"), -float("inf"), "-0.01", None]
)
def test_invalid_target_fails_before_solver(rc_problem, monkeypatch, target):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    monkeypatch.setattr(control, "assemble_stateful_fiber_frame2d", _forbid)
    with pytest.raises((TypeError, ValueError)):
        solve_control(
            rc_problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=target,
        )


@pytest.mark.parametrize(
    "name", ["control_tolerance_m", "load_factor_coordinate_scale_m"]
)
@pytest.mark.parametrize("value", [0.0, -1.0, True, float("inf"), float("nan")])
def test_control_scaling_configuration_requires_positive_finite_numbers(name, value):
    with pytest.raises((TypeError, ValueError)):
        Config(**{name: value})


@pytest.mark.parametrize(
    "newton",
    [
        None,
        object(),
        NewtonRaphsonConfig(max_iterations=201),
        NewtonRaphsonConfig(matrix_backend="scipy_sparse_splu_cpu_exact_256"),
    ],
)
def test_unsupported_newton_configuration_is_not_promoted(newton):
    with pytest.raises((TypeError, ValueError)):
        Config(newton=newton)


def test_configuration_hash_binds_control_and_solver_settings():
    config = Config()
    altered = (
        replace(config, control_tolerance_m=2.0e-12),
        replace(config, load_factor_coordinate_scale_m=0.002),
        replace(config, newton=replace(config.newton, residual_tolerance=2.0e-10)),
    )
    assert len({config.contract_hash, *(item.contract_hash for item in altered)}) == 4
    assert Config().to_manifest() == config.to_manifest()


@pytest.mark.parametrize(
    "mutation", ["disconnected_node", "too_many_nodes", "reference_on_support_only"]
)
def test_unsupported_problem_shape_fails_before_assembly(monkeypatch, mutation):
    base = make_two_element_stateful_fiber_cantilever()
    if mutation == "disconnected_node":
        problem = replace(
            base, node_coordinates_m=base.node_coordinates_m + ((7.0, 7.0),)
        )
    elif mutation == "reference_on_support_only":
        problem = replace(base, reference_external_loads=((1, -10.0),))
    else:
        problem = replace(
            base,
            node_coordinates_m=tuple((1.5 * index, 0.0) for index in range(17)),
            members=tuple(
                replace(
                    base.members[0],
                    member_id=f"bounded-member-{index}",
                    element=replace(
                        base.members[0].element,
                        element_id=f"bounded-member-{index}",
                    ),
                    node_i=index,
                    node_j=index + 1,
                )
                for index in range(16)
            ),
        )
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    original = parent.canonical_bytes()
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    monkeypatch.setattr(control, "assemble_stateful_fiber_frame2d", _forbid)
    with pytest.raises((TypeError, ValueError)):
        solve_control(
            problem, parent, control_global_dof=7, target_control_displacement_m=-1.0e-6
        )
    assert parent.canonical_bytes() == original


@pytest.mark.parametrize("mutation", ["other_problem", "changed_after_construction"])
def test_parent_source_or_hash_mismatch_cannot_enter_newton(
    rc_problem, monkeypatch, mutation
):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    if mutation == "other_problem":
        parent = initial_stateful_fiber_frame2d_checkpoint(
            replace(rc_problem, case_id="different-source")
        )
    else:
        parent = copy(parent)
        object.__setattr__(parent, "load_factor", 0.5)
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    with pytest.raises((TypeError, ValueError)):
        solve_control(
            rc_problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=-1.0e-6,
        )


@pytest.mark.parametrize("missing_gate", ["control", "equilibrium"])
def test_newton_ready_metadata_cannot_override_physical_gates(
    elastic_pair, monkeypatch, missing_gate
):
    pair = elastic_pair
    coordinates = pair.direct.trial_solution.free_displacements_m.copy()
    if missing_gate == "control":
        coordinates[:] = 0.0  # unloaded equilibrium, wrong authored target
    else:
        coordinates[-1] = 0.0  # correct displacement, missing external load
    forged = replace(pair.direct.trial_solution, free_displacements_m=coordinates)
    calls = []

    def counterfeit_solution(*args, **kwargs):
        calls.append(1)
        return forged

    monkeypatch.setattr(control, "newton_raphson_vector", counterfeit_solution)
    result = solve_control(
        pair.problem,
        pair.parent,
        control_global_dof=7,
        target_control_displacement_m=pair.target,
    )
    assert calls == [1]
    assert result.status == "blocked" and result.committed is False
    assert result.metrics[f"{missing_gate}_gate_passed"] is False
    assert result.accepted_checkpoint is pair.parent
    assert result.metrics["rollback_exact"] is True
    assert pair.parent.canonical_bytes() == pair.parent_bytes


def test_zero_newton_iteration_budget_preserves_exact_parent(rc_problem):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    original = parent.canonical_bytes()
    result = solve_control(
        rc_problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=-1.0e-6,
        config=Config(newton=NewtonRaphsonConfig(max_iterations=0)),
    )
    assert result.status == "blocked" and result.committed is False
    assert result.accepted_checkpoint is parent
    assert result.metrics["rollback_exact"] is True
    assert parent.canonical_bytes() == original
    assert all(
        state.accumulated_plastic_strain == 0.0
        for state in _fiber_states(parent)
        if type(state) is UniaxialPlasticityState
    )


def test_assembly_exception_keeps_original_parent(rc_problem, monkeypatch):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    original = parent.canonical_bytes()
    failure = RuntimeError("synthetic assembly failure")

    def rejected_assembly(*args, **kwargs):
        raise failure

    monkeypatch.setattr(control, "assemble_stateful_fiber_frame2d", rejected_assembly)
    with pytest.raises(RuntimeError) as caught:
        solve_control(
            rc_problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=-1.0e-6,
        )
    assert caught.value is failure
    assert parent.canonical_bytes() == original


def test_step_payload_is_detached_and_binds_full_checkpoint_sources(elastic_pair):
    result = elastic_pair.direct
    payload = result.to_dict()
    assert payload["parent_checkpoint"] == result.parent_checkpoint.to_dict()
    assert payload["accepted_checkpoint"] == result.accepted_checkpoint.to_dict()
    assert payload["step_hash"] == result.step_hash
    assert (
        canonical_hash(
            {key: value for key, value in payload.items() if key != "step_hash"}
        )
        == result.step_hash
    )
    original = result.to_dict()
    payload["metrics"]["control_gate_passed"] = False
    payload["accepted_checkpoint"]["load_factor"] = 0.0
    assert result.to_dict() == original


@pytest.fixture(scope="module")
def yielded_rc_prefix(rc_problem):
    """One actual 16-step path; no retry, target discovery or public analysis."""
    directory = Path(tempfile.mkdtemp(prefix="structural-rc-direct-control-step-"))
    print(f"RC direct-control regression artifacts: {directory}", flush=True)
    model_bytes = RC_MODEL.read_bytes()
    assert hashlib.sha256(model_bytes).hexdigest() == (
        "9f2a66f86fd5443574032ff4a55f3de09995094808f20c1b7f34ac403de6b59d"
    )
    (directory / "model.json").write_bytes(model_bytes)
    config = Config(newton=NewtonRaphsonConfig(max_iterations=40))
    (directory / "protocol.json").write_text(
        json.dumps(
            {
                "scope": "fixed original RC prefix and one unloading step",
                "targets_m": YIELDED_RC_TARGETS_M,
                "control_global_dof": 7,
                "config": config.to_manifest(),
                "maximum_core_calls": 16,
                "public_analysis_calls": 0,
                "retry_or_target_search": False,
                "source_probe": "structural-rc-direct-control-refined-probe.lvdv8zev",
            },
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    states = [parent]
    original_bytes = [parent.canonical_bytes()]
    steps = []
    for index, target in enumerate(YIELDED_RC_TARGETS_M):
        assert index < 16
        try:
            step = solve_control(
                rc_problem,
                parent,
                control_global_dof=7,
                target_control_displacement_m=target,
                config=config,
            )
        except Exception as error:
            (directory / "failure.json").write_text(
                json.dumps(
                    {
                        "index": index,
                        "target_m": target,
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                    allow_nan=False,
                ),
                encoding="utf-8",
            )
            raise
        (directory / f"step-{index:02d}.json").write_text(
            json.dumps(step.to_dict(), sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        assert step.status == "ready" and step.committed is True, (index, step.metrics)
        assert step.parent_checkpoint is parent
        parent = step.accepted_checkpoint
        states.append(parent)
        original_bytes.append(parent.canonical_bytes())
        steps.append(step)
    return SimpleNamespace(
        directory=directory,
        problem=rc_problem,
        config=config,
        steps=tuple(steps),
        states=tuple(states),
        original_bytes=tuple(original_bytes),
    )


def _steel_memory(checkpoint):
    return tuple(
        state.accumulated_plastic_strain
        for state in _fiber_states(checkpoint)
        if type(state) is UniaxialPlasticityState
    )


def test_yielded_rc_prefix_has_positive_committed_not_merely_trial_plastic_memory(
    yielded_rc_prefix,
):
    fixture = yielded_rc_prefix
    assert len(fixture.steps) == 16 and len(fixture.states) == 17
    assert all(max(_steel_memory(state)) == 0.0 for state in fixture.states[:15])
    first_yield = fixture.states[15]
    assert first_yield.epoch == 15 and first_yield.step_index == 15
    assert first_yield.global_displacements[7] == pytest.approx(-0.006, abs=1.0e-12)
    assert max(_steel_memory(first_yield)) == pytest.approx(
        7.86764100277988e-6, rel=1.0e-5, abs=1.0e-12
    )
    assert max(_steel_memory(first_yield)) > 0.0
    # The assertion reads the committed checkpoint, then binds it back to the
    # final assembly; a trial yielded counter alone cannot satisfy this test.
    assert (
        first_yield.element_states
        == fixture.steps[14].trial_assembly.trial_element_states
    )


def test_yielded_rc_every_accepted_step_keeps_all_parent_states_and_gates(
    yielded_rc_prefix,
):
    fixture = yielded_rc_prefix
    for index, step in enumerate(fixture.steps):
        parent, child = fixture.states[index : index + 2]
        assert parent.canonical_bytes() == fixture.original_bytes[index]
        assert child.canonical_bytes() == fixture.original_bytes[index + 1]
        assert child.parent_state_hash == parent.state_hash
        assert child.epoch == parent.epoch + 1
        assert step.metrics["config_hash"] == fixture.config.contract_hash
        assert step.metrics["parent_checkpoint_immutable"] is True
        assert step.metrics["section_and_element_parent_binding_passed"] is True
        assert step.metrics["control_gate_passed"] is True
        assert step.metrics["equilibrium_gate_passed"] is True
        assert step.metrics["solver_contract_pass"] is True
        assert (
            step.metrics["relative_equilibrium"]
            <= fixture.config.newton.residual_tolerance
        )
        assert (
            abs(step.metrics["control_error_m"]) <= fixture.config.control_tolerance_m
        )
        assert child.load_factor == step.metrics["solved_load_factor"]
        for before, after in zip(
            _steel_memory(parent), _steel_memory(child), strict=True
        ):
            assert after >= before
        for row, old_element, new_element in zip(
            step.trial_assembly.member_assemblies,
            parent.element_states,
            child.element_states,
            strict=True,
        ):
            assert row.response.parent_state_hash == old_element.state_hash
            assert row.response.state == new_element
            for response, old_section, new_section in zip(
                row.response.section_responses,
                old_element.integration_point_states,
                new_element.integration_point_states,
                strict=True,
            ):
                assert response.parent_state_hash == old_section.state_hash
                assert response.state == new_section
                assert new_section.step_index == old_section.step_index + 1


def test_yielded_rc_one_unloading_step_retains_memory_without_claiming_new_yield(
    yielded_rc_prefix,
):
    before, after = yielded_rc_prefix.states[-2:]
    assert before.global_displacements[7] < after.global_displacements[7] < 0.0
    assert after.global_displacements[7] == pytest.approx(-0.0056, abs=1.0e-12)
    assert max(_steel_memory(before)) > 0.0
    np.testing.assert_allclose(
        _steel_memory(after), _steel_memory(before), rtol=0.0, atol=1.0e-15
    )
    # Retained positive accumulated strain is material memory, not evidence of
    # a new plastic increment during unloading or of a complete reversal cycle.
    assert after.parent_state_hash == before.state_hash


def test_huge_integer_target_is_a_value_error_before_newton(rc_problem, monkeypatch):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    with pytest.raises(ValueError):
        solve_control(
            rc_problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=10**1000,
        )


def test_underflowed_control_equation_weight_is_rejected_before_assembly(
    rc_problem, monkeypatch
):
    parent = initial_stateful_fiber_frame2d_checkpoint(rc_problem)
    config = Config(
        newton=NewtonRaphsonConfig(residual_tolerance=1.0e-300),
        control_tolerance_m=1.0e300,
    )
    monkeypatch.setattr(control, "newton_raphson_vector", _forbid)
    monkeypatch.setattr(control, "assemble_stateful_fiber_frame2d", _forbid)
    with pytest.raises(ValueError, match="weight.*positive"):
        Adapter(rc_problem, parent, 7, -1.0e-6, config)


@pytest.mark.parametrize("field", ["residual_kn", "free_displacements_m"])
def test_ready_newton_metric_must_match_actual_coordinates_and_assembly(
    elastic_pair, monkeypatch, field
):
    pair = elastic_pair
    original = pair.direct.trial_solution
    metrics = dict(original.metrics)
    values = list(metrics[field])
    values[0] += 0.1
    metrics[field] = values

    def detached_metric(adapter, *, config):
        # Bind the actual current adapter/config so only the altered metric
        # contradicts the unchanged, physically converged final coordinates.
        return replace(original, problem=adapter, config=config, metrics=metrics)

    monkeypatch.setattr(control, "newton_raphson_vector", detached_metric)
    result = solve_control(
        pair.problem,
        pair.parent,
        control_global_dof=7,
        target_control_displacement_m=pair.target,
    )
    assert result.metrics["control_gate_passed"] is True
    assert result.metrics["equilibrium_gate_passed"] is True
    assert result.metrics["solver_assembly_coordinate_residual_binding_passed"] is False
    assert result.status == "blocked" and result.committed is False
    assert result.metrics["rollback_exact"] is True
    assert result.accepted_checkpoint is pair.parent
    assert pair.parent.canonical_bytes() == pair.parent_bytes


@pytest.mark.parametrize(
    "branch",
    [
        "solver_metrics",
        "convergence_history",
        "line_search_history",
        "unsupported_features",
        "step_config",
    ],
)
def test_nested_returned_metadata_is_detached_from_step_and_solver_config(
    elastic_pair, branch
):
    step = elastic_pair.direct
    original = deepcopy(step.to_dict())
    original_hash = step.step_hash
    original_solver_config = asdict(step.trial_solution.config)
    payload = step.to_dict()
    trial = payload["trial_solution"]
    if branch == "solver_metrics":
        trial["metrics"]["free_displacements_m"][0] += 0.1
    elif branch == "convergence_history":
        assert trial["convergence_history"]
        trial["convergence_history"][0]["free_displacements_m"][0] += 0.1
    elif branch == "line_search_history":
        assert trial["line_search_history"]
        trial["line_search_history"][0]["newton_increment_m"][0] += 0.1
    elif branch == "unsupported_features":
        trial["unsupported_features"].append({"code": "test-only-mutation"})
    else:
        payload["metrics"]["config"]["newton"]["residual_tolerance"] *= 1000.0
    assert payload != original
    assert step.to_dict() == original
    assert step.step_hash == original_hash
    assert asdict(step.trial_solution.config) == original_solver_config
    assert step.parent_checkpoint.canonical_bytes() == elastic_pair.parent_bytes
