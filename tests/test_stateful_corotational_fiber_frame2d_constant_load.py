from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check,
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    compile_corotational_fiber_frame_general_profile,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    compile_corotational_fiber_frame_portal_profile,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    assemble_stateful_corotational_fiber_frame2d_sparse,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse_state import (
    assemble_stateful_corotational_fiber_frame2d_sparse_state,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
    validate_fiber_frame_execution_topology_against_problem,
)
from tests.test_stateful_corotational_fiber_frame2d_displacement_control import (
    _two_base_portal_problem,
)


def _loaded_portal(case_id: str):
    return replace(
        _two_base_portal_problem(case_id),
        constant_external_loads=((7, -0.02), (10, -0.02)),
    )


def _check_load_and_reaction_balance(problem, assembly) -> None:
    expected_external = (
        problem.constant_external_load_vector()
        + assembly.target_load_factor * problem.reference_external_load_vector()
    )
    np.testing.assert_array_equal(assembly.external_loads_global, expected_external)
    physical_residual = assembly.internal_loads_global - expected_external
    fixed = list(problem.fixed_global_dofs)
    free = list(problem.free_global_dofs)
    np.testing.assert_array_equal(
        assembly.reactions_global[fixed], physical_residual[fixed]
    )
    np.testing.assert_allclose(physical_residual[free], 0.0, atol=1.0e-9)
    np.testing.assert_allclose(
        np.sum(assembly.reactions_global[1::3]) + np.sum(expected_external[1::3]),
        0.0,
        atol=1.0e-9,
    )


def test_constant_channel_preloads_two_base_portal_at_zero_reference_factor() -> None:
    problem = _loaded_portal("direct-control-constant-preload")
    original = _two_base_portal_problem(problem.case_id)
    assert original.contract_hash == (
        "sha256:8ef720460cd1f527e0bf698489e0a25314c3a52daab7d5d88e75e16f7e867d71"
    )
    assert replace(original, constant_external_loads=()).contract_hash == (
        original.contract_hash
    )
    assert problem.contract_hash != original.contract_hash
    assert not problem.constant_external_load_vector().flags.writeable

    genesis = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    preload = solve_stateful_corotational_fiber_frame2d_load_step(
        problem, genesis, target_load_factor=0.0
    )

    assert preload.committed is True
    assert preload.accepted_checkpoint.epoch == 1
    assert preload.accepted_checkpoint.load_factor == 0.0
    assert preload.accepted_checkpoint.parent_state_hash == genesis.state_hash
    assert preload.accepted_checkpoint.problem_contract_hash == problem.contract_hash
    assert preload.accepted_checkpoint.canonical_bytes() != genesis.canonical_bytes()
    _check_load_and_reaction_balance(problem, preload.trial_assembly)
    np.testing.assert_array_equal(
        preload.trial_assembly.partial_residual_load_factor_derivative_global,
        -problem.reference_external_load_vector(),
    )


def test_constant_preload_cyclic_path_restarts_and_keeps_axial_load() -> None:
    problem = _loaded_portal("direct-control-constant-cyclic")
    genesis = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    preload = solve_stateful_corotational_fiber_frame2d_load_step(
        problem, genesis, target_load_factor=0.0
    )
    assert preload.committed is True
    parent = preload.accepted_checkpoint
    parent_control = parent.global_displacements[9]
    targets = tuple(
        parent_control + offset for offset in (-1.0e-5, -2.0e-5, -1.0e-5, 1.0e-5)
    )
    kwargs = {
        "control_global_dof": 9,
        "allow_reversals": True,
        "maximum_reversals": 1,
    }
    baseline = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, targets, initial_checkpoint=parent, **kwargs
    )
    assert baseline.contract_pass is True
    assert baseline.final_checkpoint.global_displacements[9] == targets[-1]
    for step in baseline.steps:
        _check_load_and_reaction_balance(problem, step.trial_assembly)
        assert step.accepted_checkpoint.problem_contract_hash == problem.contract_hash

    persisted = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem, baseline.steps[0].accepted_checkpoint
    )
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        persisted, problem
    )
    suffix = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, targets[1:], initial_checkpoint=restored, **kwargs
    )
    assert suffix.contract_pass is True
    assert suffix.final_checkpoint.canonical_bytes() == (
        baseline.final_checkpoint.canonical_bytes()
    )
    with pytest.raises(ValueError, match="does not match the supplied frame problem"):
        load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
            persisted,
            replace(problem, constant_external_loads=((7, -0.021), (10, -0.02))),
        )

    parent_bytes = restored.canonical_bytes()
    blocked = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem,
        targets[1:],
        initial_checkpoint=restored,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=0
        ),
        **kwargs,
    )
    assert blocked.status == "blocked"
    assert blocked.steps[0].metrics["rollback_exact"] is True
    assert blocked.final_checkpoint is restored
    assert blocked.final_checkpoint.canonical_bytes() == parent_bytes

    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem=problem,
        accepted_checkpoint=parent,
        control_global_dof=9,
        target_control_displacement_m=targets[0],
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(),
    )
    check = finite_difference_stateful_corotational_fiber_frame2d_displacement_control_linearization_check(
        step_problem
    )
    assert check["parent_binding_passed"] is True
    assert check["load_factor_column_max_abs_error_kn"] < 1.0e-7


@pytest.mark.parametrize(
    ("loads", "message"),
    (
        (((7, float("nan")),), "finite"),
        (((7, float("inf")),), "finite"),
        (((7, True),), "finite"),
        (((12, -1.0),), "out of range"),
        (((7, -1.0), (7, -2.0)), "unique"),
        (([7, -1.0],), "(dof, value)"),
    ),
)
def test_constant_load_contract_rejects_invalid_rows(loads, message) -> None:
    with pytest.raises(ValueError, match=message):
        replace(
            _two_base_portal_problem("direct-control-constant-invalid"),
            constant_external_loads=loads,
        )


def test_constant_channel_fails_closed_at_sparse_and_typed_boundaries() -> None:
    problem = _loaded_portal("direct-control-constant-internal-only")
    original = _two_base_portal_problem(problem.case_id)
    genesis = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    kwargs = {
        "target_load_factor": 0.0,
        "trial_free_coordinates_m": np.zeros(len(problem.free_global_dofs)),
    }
    with pytest.raises(ValueError, match="constant external loads"):
        assemble_stateful_corotational_fiber_frame2d_sparse(problem, genesis, **kwargs)
    with pytest.raises(ValueError, match="constant external loads"):
        assemble_stateful_corotational_fiber_frame2d_sparse_state(
            problem, genesis, **kwargs
        )
    sparse_original = assemble_stateful_corotational_fiber_frame2d_sparse_state(
        original,
        initial_stateful_corotational_fiber_frame2d_checkpoint(original),
        **kwargs,
    )
    with pytest.raises(ValueError, match="constant external loads"):
        replace(sparse_original, _source_problem=problem)
    source_hash = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="constant_external_load_unsupported"):
        compile_corotational_fiber_frame_portal_profile(
            problem, model_content_hash=source_hash
        )
    with pytest.raises(ValueError, match="constant_external_load_unsupported"):
        compile_corotational_fiber_frame_general_profile(
            problem, model_content_hash=source_hash
        )
    with pytest.raises(ValueError, match="constant_external_load_unsupported"):
        compile_stateful_fiber_frame2d_execution_topology(
            problem, model_ir_content_hash=source_hash
        )
    topology = compile_stateful_fiber_frame2d_execution_topology(
        original, model_ir_content_hash=source_hash
    )
    with pytest.raises(ValueError, match="constant_external_load_unsupported"):
        validate_fiber_frame_execution_topology_against_problem(problem, topology)
