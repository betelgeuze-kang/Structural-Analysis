"""Checkpoint reassembly contracts; no Newton solves or public API requests."""

from copy import copy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d_engineering_recovery as recovery,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKENDS,
)
from tests.test_corotational_fiber_frame_sparse import _portal_problem


def _commit(problem, parent, assembly):
    return StatefulCorotationalFiberFrame2DCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=problem.contract_hash,
        epoch=parent.epoch + 1,
        step_index=parent.step_index + 1,
        load_factor=assembly.target_load_factor,
        parent_state_hash=parent.state_hash,
        global_displacements=tuple(assembly.global_displacements),
        element_states=assembly.trial_element_states,
    )


def _balanced_transition(*, intermediate=False, rotation_scale=4.0):
    """Manufacture equilibrium by prescribing loads from one assembly, not solving.

    These synthetic stored transitions test recovery consistency, not acceptance
    by Newton or independent physical validation.
    """
    problem = replace(_portal_problem(), rotation_coordinate_scale_m=rotation_scale)
    coordinates = np.asarray([1e-4, -2e-5, -4e-5, 1.2e-4, -2.1e-5, -4.5e-5])
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)

    def transition(current_problem):
        parent = initial_stateful_corotational_fiber_frame2d_checkpoint(current_problem)
        if intermediate:
            prior = assemble_stateful_corotational_fiber_frame2d(
                current_problem,
                parent,
                target_load_factor=0.25,
                trial_free_coordinates_m=coordinates * 0.5,
            )
            parent = _commit(current_problem, parent, prior)
        assembly = assemble_stateful_corotational_fiber_frame2d(
            current_problem,
            parent,
            target_load_factor=0.5,
            trial_free_coordinates_m=coordinates,
        )
        return parent, assembly

    _, probe = transition(problem)
    problem = replace(
        problem,
        reference_external_loads=tuple(
            (dof, float(probe.internal_loads_global[dof] * 2.0))
            for dof in problem.free_global_dofs
        ),
    )
    parent, assembly = transition(problem)
    terminal = _commit(problem, parent, assembly)
    assert np.array_equal(assembly.residual_kn, np.zeros(len(problem.free_global_dofs)))
    assert initial.epoch == 0
    return problem, parent, terminal, assembly


@pytest.fixture(scope="module", params=[False, True], ids=["genesis", "intermediate"])
def transition(request):
    return _balanced_transition(intermediate=request.param)


def _recover(transition, backend=VECTOR_MATRIX_BACKEND, tolerance=1e-10):
    problem, parent, terminal, _ = transition
    return recovery.recover_corotational_checkpoint_transition(
        problem,
        parent,
        terminal,
        matrix_backend=backend,
        residual_tolerance=tolerance,
    )


@pytest.mark.parametrize("backend", VECTOR_MATRIX_BACKENDS)
def test_exact_si_projection_for_each_backend_without_newton(transition, backend):
    problem, parent, terminal, assembly = transition
    before = (
        problem.contract_hash,
        parent.canonical_bytes(),
        terminal.canonical_bytes(),
    )
    result = _recover(transition, backend)
    assert dict(result.counts) == {"node": 4, "member": 3, "section": 9, "fiber": 126}
    displacement = np.asarray(terminal.global_displacements).reshape(4, 3)
    assert (
        result.arrays["node_translation_m"].tobytes() == displacement[:, :2].tobytes()
    )
    assert result.arrays["node_rotation_rad"].tobytes() == displacement[:, 2].tobytes()
    assert (
        result.arrays["reaction_force_n"].tobytes()
        == (assembly.reactions_global.reshape(4, 3)[:, :2] * 1000.0).tobytes()
    )
    assert result.metrics["terminal_state_bytes_exact"] is True
    assert result.metrics["free_residual_relative"] == 0.0
    assert result.metrics["solver_terminal_relative_residual"] == 0.0
    assert all(not value.flags.writeable for value in result.arrays.values())
    assert before == (
        problem.contract_hash,
        parent.canonical_bytes(),
        terminal.canonical_bytes(),
    )
    if backend != VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND:
        assert result.terminal_assembly_hash == canonical_hash(assembly.to_dict())
    repeated = _recover(transition, backend)
    assert result.terminal_assembly_hash == repeated.terminal_assembly_hash
    assert dict(result.order_hashes) == dict(repeated.order_hashes)
    assert {k: v.tobytes() for k, v in result.arrays.items()} == {
        k: v.tobytes() for k, v in repeated.arrays.items()
    }


@pytest.mark.parametrize(
    "value", [True, False, 0, -1.0, float("nan"), float("inf"), "1e-10", None]
)
def test_invalid_tolerance_rejected_before_assembly(transition, monkeypatch, value):
    monkeypatch.setattr(
        recovery,
        "assemble_stateful_corotational_fiber_frame2d",
        lambda *a, **k: pytest.fail("assembly entered"),
    )
    with pytest.raises(recovery.CorotationalFiberFrameEngineeringRecoveryError):
        _recover(transition, tolerance=value)


@pytest.mark.parametrize("value", [None, True, "numpy_dense_ndarray", "unknown"])
def test_backend_is_an_explicit_supported_enum(transition, value):
    with pytest.raises(recovery.CorotationalFiberFrameEngineeringRecoveryError):
        _recover(transition, backend=value)


@pytest.mark.parametrize(
    "field,value", [("role", "trial"), ("epoch", True), ("step_index", True)]
)
def test_rehashed_constructor_invariant_mutation_rejected(transition, field, value):
    problem, parent, terminal, assembly = transition
    damaged = copy(terminal)
    object.__setattr__(damaged, field, value)
    object.__setattr__(damaged, "state_hash", damaged.compute_state_hash())
    with pytest.raises(recovery.CorotationalFiberFrameEngineeringRecoveryError):
        _recover((problem, parent, damaged, assembly))


@pytest.mark.parametrize("mutation", ["parent", "load", "epoch"])
def test_rehashed_ancestry_load_and_epoch_mismatch_rejected(transition, mutation):
    problem, parent, terminal, assembly = transition
    changes = (
        {"parent_state_hash": "sha256:" + "a" * 64}
        if mutation == "parent"
        else (
            {"load_factor": parent.load_factor}
            if mutation == "load"
            else {"epoch": terminal.epoch + 1, "step_index": terminal.step_index + 1}
        )
    )
    damaged = replace(terminal, **changes, state_hash="")
    with pytest.raises(recovery.CorotationalFiberFrameEngineeringRecoveryError):
        _recover((problem, parent, damaged, assembly))


def test_physical_residual_is_required_even_for_self_consistent_state(transition):
    problem, parent, terminal, assembly = transition
    changed_problem = replace(problem, reference_external_loads=((9, 1000.0),))
    changed_parent = replace(
        parent, problem_contract_hash=changed_problem.contract_hash, state_hash=""
    )
    changed_terminal = replace(
        terminal,
        problem_contract_hash=changed_problem.contract_hash,
        parent_state_hash=changed_parent.state_hash,
        state_hash="",
    )
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError,
        match="consistency_gate_failed",
    ):
        _recover((changed_problem, changed_parent, changed_terminal, assembly))


def test_common_projection_preserves_independent_solver_residual_gate(transition):
    problem, _, terminal, assembly = transition
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError,
        match="consistency_gate_failed",
    ):
        recovery._project_recovery(
            problem,
            terminal,
            assembly,
            terminal_assembly_hash=canonical_hash(assembly.to_dict()),
            residual_tolerance=1e-10,
            solver_relative_residual=1.0,
        )


def test_displacement_inverse_roundtrip_is_not_relaxed(transition, monkeypatch):
    problem, parent, terminal, assembly = transition
    original = recovery.assemble_stateful_corotational_fiber_frame2d

    def one_ulp_displacement(*args, **kwargs):
        replay = original(*args, **kwargs)
        displaced = replay.global_displacements.copy()
        displaced[problem.free_global_dofs[-1]] = np.nextafter(
            displaced[problem.free_global_dofs[-1]], np.inf
        )
        return SimpleNamespace(**{**vars(replay), "global_displacements": displaced})

    monkeypatch.setattr(
        recovery, "assemble_stateful_corotational_fiber_frame2d", one_ulp_displacement
    )
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError,
        match="terminal_replay_mismatch",
    ):
        _recover((problem, parent, terminal, assembly))


def test_recovery_rechecks_sources_after_projection(transition, monkeypatch):
    problem, parent, terminal, assembly = transition
    terminal = copy(terminal)
    project = recovery._project_recovery

    def mutate_after_projection(*args, **kwargs):
        result = project(*args, **kwargs)
        object.__setattr__(terminal, "load_factor", 0.75)
        object.__setattr__(terminal, "state_hash", terminal.compute_state_hash())
        return result

    monkeypatch.setattr(recovery, "_project_recovery", mutate_after_projection)
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError, match="source_mutated"
    ):
        _recover((problem, parent, terminal, assembly))


def test_rehashed_material_state_cannot_replace_reassembly(transition):
    problem, parent, terminal, assembly = transition
    element = terminal.element_states[0]
    basic = element.basic_beam_state
    section = basic.integration_point_states[0]
    steel = replace(section.fiber_states[-1], backstress_mpa=1.0)
    section = replace(section, fiber_states=(*section.fiber_states[:-1], steel))
    basic = replace(
        basic, integration_point_states=(section, *basic.integration_point_states[1:])
    )
    element = replace(element, basic_beam_state=basic)
    changed = replace(
        terminal, element_states=(element, *terminal.element_states[1:]), state_hash=""
    )
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError,
        match="terminal_replay_mismatch",
    ):
        _recover((problem, parent, changed, assembly))


def test_mutated_problem_positive_scale_is_revalidated(transition):
    problem, parent, terminal, assembly = transition
    problem = copy(problem)
    object.__setattr__(problem, "rotation_coordinate_scale_m", -4.0)
    parent = replace(parent, problem_contract_hash=problem.contract_hash, state_hash="")
    terminal = replace(
        terminal,
        problem_contract_hash=problem.contract_hash,
        parent_state_hash=parent.state_hash,
        state_hash="",
    )
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError, match="positive"
    ):
        _recover((problem, parent, terminal, assembly))


@pytest.mark.parametrize("backend", VECTOR_MATRIX_BACKENDS)
def test_reaction_only_transition_retains_prescribed_rotation(backend):
    problem = replace(
        _portal_problem(),
        fixed_global_dofs=tuple(range(12)),
        prescribed_displacements=((8, 2e-6), (9, 1e-5)),
    )
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        parent,
        target_load_factor=0.5,
        trial_free_coordinates_m=(),
    )
    terminal = _commit(problem, parent, assembly)
    result = _recover((problem, parent, terminal, assembly), backend)
    assert result.arrays["node_rotation_rad"][2] == 1e-6
    assert result.metrics["free_residual_relative"] == 0.0
    np.testing.assert_array_equal(
        result.arrays["reaction_force_n"],
        (assembly.internal_loads_global - assembly.external_loads_global).reshape(4, 3)[
            :, :2
        ]
        * 1000,
    )


def _unvalidated_path_fixture(transition):
    """Unit-test only the existing _recover gates, without creating an adapter."""
    problem, parent, terminal, _ = transition
    problem = replace(
        problem,
        reference_external_loads=tuple(
            (dof, value / 2) for dof, value in problem.reference_external_loads
        ),
    )
    parent = replace(parent, problem_contract_hash=problem.contract_hash, state_hash="")
    assembly = assemble_stateful_corotational_fiber_frame2d(
        problem,
        parent,
        target_load_factor=1.0,
        trial_free_coordinates_m=(
            np.asarray(terminal.global_displacements)
            / problem.physical_coordinate_scale
        )[list(problem.free_global_dofs)],
    )
    terminal = _commit(problem, parent, assembly)
    solution = SimpleNamespace(
        config=SimpleNamespace(
            matrix_backend=VECTOR_MATRIX_BACKEND, residual_tolerance=1e-10
        ),
        metrics={"relative_residual": 0.0},
    )
    step = SimpleNamespace(
        parent_checkpoint=parent,
        trial_assembly=assembly,
        trial_solution=solution,
        committed=True,
        metrics={},
    )
    adapter = SimpleNamespace(
        _compilation=SimpleNamespace(_problem=problem),
        _path=SimpleNamespace(steps=[step], final_checkpoint=terminal),
    )
    return adapter


@pytest.mark.parametrize(
    "mutation", ["load", "committed", "assembly", "solver_residual", "source"]
)
def test_existing_path_authority_gates_still_precede_public_recovery(
    transition, monkeypatch, mutation
):
    adapter = _unvalidated_path_fixture(transition)
    monkeypatch.setattr(
        recovery, "_validated_source_manifest", lambda value: {"stable": True}
    )
    reference = recovery._recover(adapter, source_manifest_before={"stable": True})
    assert reference.metrics["terminal_state_bytes_exact"] is True
    step = adapter._path.steps[-1]
    if mutation == "load":
        adapter._path.final_checkpoint = replace(
            adapter._path.final_checkpoint, load_factor=0.75, state_hash=""
        )
    elif mutation == "committed":
        step.committed = False
    elif mutation == "assembly":
        step.trial_assembly = SimpleNamespace(to_dict=lambda: {"changed": True})
    elif mutation == "solver_residual":
        step.trial_solution.metrics["relative_residual"] = None
    else:
        monkeypatch.setattr(
            recovery, "_validated_source_manifest", lambda value: {"changed": True}
        )
    with pytest.raises(recovery.CorotationalFiberFrameEngineeringRecoveryError):
        recovery._recover(adapter, source_manifest_before={"stable": True})
