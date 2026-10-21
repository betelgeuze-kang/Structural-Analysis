"""Exact sparse terminal/recovery/FD compatibility on small generated frames."""

from dataclasses import replace
import json
from pathlib import Path
import runpy

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from structural_analysis.api import nonlinear_fiber_frame as api
from structural_analysis.assembly import stateful_fiber_frame2d_direct_sparse as sparse
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_recovery as recovery,
)
from structural_analysis.assembly import stateful_fiber_frame2d_solver as solver
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_terminal_receipt as terminal,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.benchmark import (
    stateful_fiber_frame2d_diagnostics as diagnostic,
)
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
)


def _compare(problem, parent, free, target=0.75):
    before = parent.canonical_bytes()
    options = dict(target_load_factor=target, trial_free_coordinates_m=free)
    control = assemble_stateful_fiber_frame2d(problem, parent, **options)
    actual = sparse.assemble_stateful_fiber_frame2d_direct_sparse_terminal(
        problem, parent, **options
    )
    assert type(actual) is sparse.DirectSparseFiberFrameAssembly
    assert type(actual.jacobian_kn_per_m) is csr_matrix
    assert actual.to_dict() == control.to_dict()
    assert json.dumps(actual.to_dict()) == json.dumps(control.to_dict())
    assert (
        actual.jacobian_kn_per_m.toarray().tobytes()
        == control.jacobian_kn_per_m.tobytes()
    )
    for name in (
        "generalized_coordinates_m",
        "global_displacements",
        "residual_kn",
        "internal_loads_global",
        "external_loads_global",
        "reactions_global",
    ):
        assert getattr(actual, name).tobytes() == getattr(control, name).tobytes()
        assert not getattr(actual, name).flags.writeable
    assert tuple(
        state.canonical_bytes() for state in actual.trial_element_states
    ) == tuple(state.canonical_bytes() for state in control.trial_element_states)
    assert len(actual.member_assemblies) == len(problem.members)
    for member in actual.member_assemblies:
        for name in (
            "transformation_global_to_local",
            "internal_load_global",
            "consistent_tangent_global",
        ):
            assert not getattr(member, name).flags.writeable
    assert parent.canonical_bytes() == before
    return actual


@pytest.mark.parametrize(
    "factory",
    [
        make_two_element_stateful_fiber_cantilever,
        make_two_member_stateful_fiber_l_frame,
        lambda: make_two_element_stateful_fiber_cantilever(angle_rad=0.617),
    ],
)
@pytest.mark.parametrize("magnitude", [0.0, 1e-7, -3e-5, 0.002])
def test_terminal_members_states_vectors_and_legacy_bytes_match_dense(
    factory, magnitude
):
    problem = factory()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    _compare(
        problem,
        parent,
        np.linspace(-magnitude, magnitude, len(problem.free_global_dofs)),
    )


def test_noninitial_terminal_reversal_and_empty_free_serialization_are_exact():
    problem = make_two_member_stateful_fiber_l_frame()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    trial = _compare(problem, initial, np.linspace(-0.002, 0.002, 6), target=0.5)
    parent = StatefulFiberFrame2DCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=problem.contract_hash,
        epoch=1,
        step_index=1,
        load_factor=0.5,
        parent_state_hash=initial.state_hash,
        global_displacements=tuple(trial.global_displacements),
        element_states=trial.trial_element_states,
    )
    _compare(problem, parent, np.linspace(0.001, -0.001, 6), target=-0.25)
    fixed = replace(problem, fixed_global_dofs=tuple(range(problem.global_dof_count)))
    empty = _compare(
        fixed, initial_stateful_fiber_frame2d_checkpoint(fixed), np.empty(0)
    )
    assert empty.jacobian_kn_per_m.shape == (0, 0)


def test_terminal_assembly_avoids_global_square_but_legacy_free_dense_is_explicit(
    monkeypatch,
):
    problem = make_two_member_stateful_fiber_l_frame()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    original = np.zeros
    shapes = []

    def zeros(shape, *args, **kwargs):
        shapes.append(shape)
        if isinstance(shape, tuple) and shape == (problem.global_dof_count,) * 2:
            pytest.fail("global dense tangent allocated in terminal assembly")
        return original(shape, *args, **kwargs)

    monkeypatch.setattr(np, "zeros", zeros)
    actual = sparse.assemble_stateful_fiber_frame2d_direct_sparse_terminal(
        problem, parent, target_load_factor=0.1, trial_free_coordinates_m=np.zeros(6)
    )
    actual.to_dict()
    assert (len(problem.free_global_dofs),) * 2 in shapes


@pytest.mark.parametrize(
    "backend", [VECTOR_MATRIX_BACKEND, VECTOR_SPARSE_MATRIX_BACKEND]
)
def test_fd_retains_all_columns_same_parent_and_exact_legacy_payload(
    monkeypatch, backend
):
    problem = make_two_member_stateful_fiber_l_frame()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    options = dict(
        target_load_factor=0.25, trial_free_coordinates_m=np.linspace(-1e-6, 1e-6, 6)
    )
    expected = diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check(
        problem, parent, **options
    )
    before = parent.canonical_bytes()
    calls = []
    name = (
        "assemble_stateful_fiber_frame2d_direct_sparse"
        if backend == VECTOR_SPARSE_MATRIX_BACKEND
        else "assemble_stateful_fiber_frame2d"
    )
    original = getattr(diagnostic, name)

    def tracked(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append((args[1], np.array(kwargs["trial_free_coordinates_m"], copy=True)))
        return result

    monkeypatch.setattr(diagnostic, name, tracked)
    actual = diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check(
        problem, parent, matrix_backend=backend, **options
    )
    assert actual == expected and actual["pass"]
    assert len(calls) == 2 * len(problem.free_global_dofs) + 1
    assert all(record[0] is parent for record in calls)
    for column in range(6):
        direction = np.zeros(6)
        direction[column] = 1e-8
        assert (
            calls[1 + 2 * column][1].tobytes()
            == (options["trial_free_coordinates_m"] + direction).tobytes()
        )
        assert (
            calls[2 + 2 * column][1].tobytes()
            == (options["trial_free_coordinates_m"] - direction).tobytes()
        )
    assert parent.canonical_bytes() == before


@pytest.mark.parametrize("backend", [None, True, "", "gpu"])
def test_fd_unknown_backend_refuses_before_assembly(monkeypatch, backend):
    monkeypatch.setattr(
        diagnostic,
        "assemble_stateful_fiber_frame2d",
        lambda *a, **k: pytest.fail("assembly"),
    )
    with pytest.raises(ValueError, match="matrix_backend"):
        diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check(
            None,
            None,
            matrix_backend=backend,
            target_load_factor=0.0,
            trial_free_coordinates_m=[],
        )


def test_sparse_solver_terminal_and_rollback_are_exact_legacy_compatible(monkeypatch):
    problem = make_two_member_stateful_fiber_l_frame()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    config = NewtonRaphsonConfig(
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND, max_iterations=40
    )
    actual = solver.solve_stateful_fiber_frame2d_load_step(
        problem, initial, target_load_factor=0.25, config=config
    )
    assert (
        actual.committed
        and type(actual.trial_assembly) is sparse.DirectSparseFiberFrameAssembly
    )
    monkeypatch.setattr(
        solver,
        "assemble_stateful_fiber_frame2d_direct_sparse_terminal",
        assemble_stateful_fiber_frame2d,
    )
    control = solver.solve_stateful_fiber_frame2d_load_step(
        problem, initial, target_load_factor=0.25, config=config
    )
    assert actual.to_dict() == control.to_dict()
    monkeypatch.undo()
    blocked = solver.solve_stateful_fiber_frame2d_load_step(
        problem,
        initial,
        target_load_factor=1.0,
        config=replace(config, max_iterations=0),
    )
    assert not blocked.committed and blocked.accepted_checkpoint is initial
    assert blocked.metrics["rollback_exact"] is True


def test_public_sparse_control_keeps_dense_terminal_recovery_and_fd_only(monkeypatch):
    payload = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/benchmark_native_steel_batch.py"
        )
    )["public_payload"](1, 2)
    payload["sections"][0]["width_m"] = 0.401
    model = load_neutral_json_bytes(json.dumps(payload).encode())
    config = api.PublicRCFiberFrameConfig(
        load_steps=2, matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND
    )
    actual = api.analyze_public_rc_fiber_frame(model, config)
    assert (
        actual.status == "ready"
        and api.validate_public_rc_fiber_frame_result(actual).contract_pass
    )
    assert isinstance(actual.checkpoint_artifact(), bytes)
    original_fd = diagnostic.finite_difference_stateful_fiber_frame2d_tangent_check

    def old_fd(*args, **kwargs):
        kwargs["matrix_backend"] = VECTOR_MATRIX_BACKEND
        return original_fd(*args, **kwargs)

    with monkeypatch.context() as old:
        old.setattr(
            solver,
            "assemble_stateful_fiber_frame2d_direct_sparse_terminal",
            assemble_stateful_fiber_frame2d,
        )
        old.setattr(
            recovery,
            "assemble_stateful_fiber_frame2d_direct_sparse_terminal",
            assemble_stateful_fiber_frame2d,
        )
        old.setattr(
            terminal, "finite_difference_stateful_fiber_frame2d_tangent_check", old_fd
        )
        control = api.analyze_public_rc_fiber_frame(model, config)
        assert (
            control.status == "ready"
            and api.validate_public_rc_fiber_frame_result(control).contract_pass
        )
    assert actual.to_dict() == control.to_dict()
    assert actual.checkpoint_artifact() == control.checkpoint_artifact()
    restarted = api.analyze_public_rc_fiber_frame(
        model, config, restart_checkpoint_chain=actual.checkpoint_artifact()
    )
    assert (
        restarted.status == "ready"
        and api.validate_public_rc_fiber_frame_result(restarted).contract_pass
    )
    assert restarted.checkpoint_artifact() == actual.checkpoint_artifact()
