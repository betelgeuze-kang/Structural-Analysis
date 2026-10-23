"""Direct CSR trial equivalence and admission; no frame solve or benchmark run."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from structural_analysis.assembly import stateful_fiber_frame2d_direct_sparse as module
from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
    make_two_member_stateful_fiber_l_frame,
)
from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D


@pytest.fixture(autouse=True)
def clear_pattern_cache():
    module._topology_plan.cache_clear()
    yield
    module._topology_plan.cache_clear()


def compare(problem, trial, load=0.75):
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    before = parent.canonical_bytes()
    dense = assemble_stateful_fiber_frame2d(
        problem, parent, target_load_factor=load, trial_free_coordinates_m=trial
    )
    actual = module.assemble_stateful_fiber_frame2d_direct_sparse(
        problem, parent, target_load_factor=load, trial_free_coordinates_m=trial
    )
    assert actual.parent_checkpoint_hash == dense.parent_checkpoint_hash
    assert actual.free_global_dofs == dense.free_global_dofs
    for name in (
        "generalized_coordinates_m",
        "global_displacements",
        "residual_kn",
        "internal_loads_global",
        "external_loads_global",
        "reactions_global",
    ):
        assert getattr(actual, name).tobytes() == getattr(dense, name).tobytes()
    assert (
        actual.jacobian_kn_per_m.toarray().tobytes()
        == dense.jacobian_kn_per_m.tobytes()
    )
    assert actual.jacobian_kn_per_m.has_sorted_indices
    assert actual.jacobian_kn_per_m.has_canonical_format
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
def test_direct_csr_matches_dense_bitwise(factory, magnitude):
    problem = factory()
    compare(problem, np.linspace(-magnitude, magnitude, len(problem.free_global_dofs)))


def test_vectors_and_csr_buffers_are_immutable_and_accounted():
    problem = make_two_member_stateful_fiber_l_frame()
    actual = compare(problem, np.zeros(len(problem.free_global_dofs)))
    arrays = [
        getattr(actual, name)
        for name in (
            "generalized_coordinates_m",
            "global_displacements",
            "residual_kn",
            "internal_loads_global",
            "external_loads_global",
            "reactions_global",
        )
    ]
    arrays += [
        actual.jacobian_kn_per_m.data,
        actual.jacobian_kn_per_m.indices,
        actual.jacobian_kn_per_m.indptr,
    ]
    assert actual.allocated_bytes == sum(array.nbytes for array in arrays)
    assert actual.pattern_nnz == actual.jacobian_kn_per_m.nnz
    for array in arrays:
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_no_global_dense_tangent_allocation(monkeypatch):
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    original = np.zeros

    def guarded(shape, *args, **kwargs):
        assert shape != (problem.global_dof_count, problem.global_dof_count)
        return original(shape, *args, **kwargs)

    monkeypatch.setattr(np, "zeros", guarded)
    module.assemble_stateful_fiber_frame2d_direct_sparse(
        problem,
        parent,
        target_load_factor=0.1,
        trial_free_coordinates_m=np.zeros(len(problem.free_global_dofs)),
    )


@pytest.mark.parametrize(
    "load,trial",
    [
        (float("nan"), np.zeros(6)),
        (float("inf"), np.zeros(6)),
        (True, np.zeros(6)),
        (0.1, np.zeros(5)),
        (0.1, [0, 0, float("inf"), 0, 0, 0]),
    ],
)
def test_invalid_inputs_are_rejected_before_member_integration(
    monkeypatch, load, trial
):
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    monkeypatch.setattr(
        StatefulFiberBeam2D,
        "integrate",
        lambda *args: pytest.fail("integration after invalid admission"),
    )
    with pytest.raises(ValueError):
        module.assemble_stateful_fiber_frame2d_direct_sparse(
            problem, parent, target_load_factor=load, trial_free_coordinates_m=trial
        )


def test_checkpoint_tampering_and_response_parent_are_rejected(monkeypatch):
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    bad = replace(parent, case_id="wrong-case", state_hash="")
    with pytest.raises(ValueError, match="case_id"):
        module.assemble_stateful_fiber_frame2d_direct_sparse(
            problem, bad, target_load_factor=0.1, trial_free_coordinates_m=np.zeros(6)
        )
    monkeypatch.setattr(
        StatefulFiberBeam2D,
        "integrate",
        lambda *args: SimpleNamespace(parent_state_hash="sha256:" + "0" * 64),
    )
    with pytest.raises(ValueError, match="parent_state_hash"):
        module.assemble_stateful_fiber_frame2d_direct_sparse(
            problem,
            parent,
            target_load_factor=0.1,
            trial_free_coordinates_m=np.zeros(6),
        )


def test_all_structural_zeros_and_tiny_values_are_retained(monkeypatch):
    problem = make_two_element_stateful_fiber_cantilever()
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)

    def tiny(self, displacement, committed):
        return SimpleNamespace(
            parent_state_hash=committed.state_hash,
            internal_force_local=np.zeros(6),
            consistent_tangent_local=np.full((6, 6), 1e-290),
            state=committed,
        )

    monkeypatch.setattr(StatefulFiberBeam2D, "integrate", tiny)
    actual = module.assemble_stateful_fiber_frame2d_direct_sparse(
        problem, parent, target_load_factor=0.1, trial_free_coordinates_m=np.zeros(6)
    )
    dense = assemble_stateful_fiber_frame2d(
        problem, parent, target_load_factor=0.1, trial_free_coordinates_m=np.zeros(6)
    )
    assert (
        actual.jacobian_kn_per_m.toarray().tobytes()
        == dense.jacobian_kn_per_m.tobytes()
    )
    assert np.any(
        (actual.jacobian_kn_per_m.data != 0)
        & (np.abs(actual.jacobian_kn_per_m.data) < 1e-280)
    )
    assert actual.jacobian_kn_per_m.nnz == actual.pattern_nnz


def test_current_topology_values_invalidate_old_pattern_and_old_checkpoint():
    problem = make_two_element_stateful_fiber_cantilever()
    old = initial_stateful_fiber_frame2d_checkpoint(problem)
    compare(problem, np.zeros(6))
    assert module._topology_plan.cache_info().misses == 1
    object.__setattr__(problem, "fixed_global_dofs", (0, 1, 2, 3))
    with pytest.raises(ValueError, match="problem_contract_hash"):
        module.assemble_stateful_fiber_frame2d_direct_sparse(
            problem, old, target_load_factor=0.1, trial_free_coordinates_m=np.zeros(5)
        )
    compare(problem, np.zeros(5))
    assert module._topology_plan.cache_info().misses == 2
    object.__setattr__(problem.members[0], "node_i", 2)
    object.__setattr__(problem.members[0], "node_j", 1)
    compare(problem, np.zeros(5))
    assert module._topology_plan.cache_info().misses == 3


def test_empty_free_system_is_an_empty_csr():
    problem = replace(
        make_two_element_stateful_fiber_cantilever(), fixed_global_dofs=tuple(range(9))
    )
    actual = compare(problem, np.empty(0))
    assert actual.jacobian_kn_per_m.shape == (0, 0) and actual.pattern_nnz == 0


def test_pure_tuple_topology_cache_cannot_be_forced_into_a_stale_pattern():
    problem = make_two_element_stateful_fiber_cantilever()
    dofs = tuple(problem.member_global_dofs(member) for member in problem.members)
    plan = module._topology_plan(
        problem.global_dof_count, problem.free_global_dofs, dofs
    )
    assert isinstance(plan, tuple)
    with pytest.raises(AttributeError):
        object.__setattr__(plan, "indices", (0,))
    assert (
        module._topology_plan(problem.global_dof_count, problem.free_global_dofs, dofs)
        is plan
    )


def test_noninitial_parent_trial_is_equivalent_and_preserves_parent_bytes():
    problem = make_two_member_stateful_fiber_l_frame()
    initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    first = assemble_stateful_fiber_frame2d(
        problem,
        initial,
        target_load_factor=0.5,
        trial_free_coordinates_m=np.linspace(-0.002, 0.002, 6),
    )
    parent = StatefulFiberFrame2DCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=problem.contract_hash,
        epoch=1,
        step_index=1,
        load_factor=0.5,
        parent_state_hash=initial.state_hash,
        global_displacements=tuple(first.global_displacements),
        element_states=first.trial_element_states,
    )
    before = parent.canonical_bytes()
    options = {
        "target_load_factor": -0.25,
        "trial_free_coordinates_m": np.linspace(0.001, -0.001, 6),
    }
    dense = assemble_stateful_fiber_frame2d(problem, parent, **options)
    actual = module.assemble_stateful_fiber_frame2d_direct_sparse(
        problem, parent, **options
    )
    assert actual.residual_kn.tobytes() == dense.residual_kn.tobytes()
    assert (
        actual.jacobian_kn_per_m.toarray().tobytes()
        == dense.jacobian_kn_per_m.tobytes()
    )
    assert parent.canonical_bytes() == before
