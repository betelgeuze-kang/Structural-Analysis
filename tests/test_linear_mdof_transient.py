from __future__ import annotations

import math

import numpy as np
import pytest

from structural_analysis.solvers.linear.transient import (
    LinearMDOFSystem,
    LinearMDOFTransientConfig,
    resume_linear_mdof_transient,
    solve_linear_mdof_transient,
    validate_linear_mdof_checkpoint_authority,
)


def _system(*, damped: bool = True) -> LinearMDOFSystem:
    return LinearMDOFSystem(
        [[2.0, 0.0], [0.0, 1.0]],
        [[0.4, 0.0], [0.0, 0.2]] if damped else [[0.0, 0.0], [0.0, 0.0]],
        [[600.0, -200.0], [-200.0, 200.0]],
        ("floor_1.ux", "floor_2.ux"),
        model_id="two-story-shear",
    )


def test_linear_mdof_dynamic_equilibrium_and_exact_restart() -> None:
    system = _system()
    config = LinearMDOFTransientConfig(time_step_s=0.01)
    time = np.arange(41, dtype=np.float64) * config.time_step_s
    forces = np.column_stack((20.0 * np.sin(8.0 * time), 12.0 * np.sin(5.0 * time)))

    solution = solve_linear_mdof_transient(system, forces, config=config)
    split = 21
    prefix = solve_linear_mdof_transient(system, forces[:split], config=config)
    resumed = resume_linear_mdof_transient(
        system,
        prefix.checkpoints[-1],
        forces[split:],
        config=config,
        checkpoint_chain=prefix.checkpoints,
        force_history_prefix_n=forces[:split],
    )
    joined = (*prefix.checkpoints, *resumed.checkpoints[1:])
    authority = validate_linear_mdof_checkpoint_authority(
        solution.checkpoints[-1],
        system=system,
        config=config,
        checkpoint_chain=solution.checkpoints,
        force_history_prefix_n=forces,
    )

    assert solution.contract_pass is True
    assert solution.fallback_used is False
    assert solution.regularization_used is False
    assert solution.maximum_relative_residual <= config.residual_relative_tolerance
    assert joined == solution.checkpoints
    assert authority.source_authenticated_checkpoint is True
    assert authority.parent_chain_complete is True
    assert authority.deterministic_checkpoint_replay_pass is True


def test_linear_mdof_modal_closed_form_convergence() -> None:
    system = _system(damped=False)
    mass, _, stiffness = system.arrays()
    eigenvalues, eigenvectors = np.linalg.eig(np.linalg.solve(mass, stiffness))
    index = int(np.argmin(eigenvalues))
    omega = math.sqrt(float(eigenvalues[index]))
    mode = np.asarray(eigenvectors[:, index], dtype=np.float64)
    mode /= np.max(np.abs(mode))
    config = LinearMDOFTransientConfig(time_step_s=0.0005)
    sample_count = 1001
    solution = solve_linear_mdof_transient(
        system,
        np.zeros((sample_count, 2)),
        config=config,
        initial_displacement_m=0.01 * mode,
    )
    exact = 0.01 * mode * math.cos(omega * config.time_step_s * (sample_count - 1))
    observed = np.asarray(solution.steps[-1].displacement_m)

    assert np.max(np.abs(observed - exact)) <= 2.0e-7
    assert solution.maximum_absolute_energy_balance_error_j <= 1.0e-12


def test_linear_mdof_rejects_non_positive_definite_mass() -> None:
    with pytest.raises(ValueError, match="positive definite"):
        LinearMDOFSystem(
            [[1.0, 0.0], [0.0, 0.0]],
            [[0.0, 0.0], [0.0, 0.0]],
            [[2.0, -1.0], [-1.0, 2.0]],
            ("d1", "d2"),
        )
