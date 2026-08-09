from __future__ import annotations

import numpy as np
import pytest

from structural_analysis.solvers.nonlinear.mdof_transient import (
    BilinearStory,
    NonlinearMDOFTransientConfig,
    NonlinearMDOFTransientError,
    NonlinearShearBuilding,
    resume_nonlinear_mdof_transient,
    solve_nonlinear_mdof_transient,
    validate_nonlinear_mdof_checkpoint_authority,
)


def _system() -> NonlinearShearBuilding:
    return NonlinearShearBuilding(
        [[0.5, 0.0], [0.0, 0.3]],
        [[0.5, 0.0], [0.0, 0.3]],
        (BilinearStory("S1", 1000.0, 5.0, 0.05), BilinearStory("S2", 800.0, 4.0, 0.05)),
        ("Floor1_UX", "Floor2_UX"),
        model_id="two-story-bilinear-shear",
    )


def _forces() -> np.ndarray:
    return np.asarray(
        [[0, 0], [5, 3], [10, 8], [15, 12], [5, 5], [-10, -8], [-15, -12], [0, 0], [12, 10], [0, 0]],
        dtype=np.float64,
    )


def test_nonlinear_mdof_commits_material_states_and_restarts_exactly() -> None:
    system = _system()
    config = NonlinearMDOFTransientConfig(time_step_s=0.01)
    forces = _forces()
    solution = solve_nonlinear_mdof_transient(system, forces, config=config)
    split = 6
    prefix = solve_nonlinear_mdof_transient(system, forces[:split], config=config)
    resumed = resume_nonlinear_mdof_transient(
        system, prefix.checkpoints[-1], forces[split:], config=config,
        checkpoint_chain=prefix.checkpoints, force_history_prefix_kn=forces[:split],
    )
    authority = validate_nonlinear_mdof_checkpoint_authority(
        solution.checkpoints[-1], system=system, config=config,
        checkpoint_chain=solution.checkpoints, force_history_prefix_kn=forces,
    )

    assert solution.contract_pass is True
    assert solution.yielded_step_count > 0
    assert solution.material_trial_commit_rollback is True
    assert solution.fallback_used is False
    assert solution.regularization_used is False
    assert (*prefix.checkpoints, *resumed.checkpoints[1:]) == solution.checkpoints
    assert authority.source_authenticated_checkpoint is True
    assert authority.material_state_replay_pass is True
    assert sum(state.plastic_dissipation_kn_m for state in solution.checkpoints[-1].material_states) > 0.0


def test_nonlinear_mdof_failed_step_leaves_accepted_checkpoint_immutable() -> None:
    system = _system()
    config = NonlinearMDOFTransientConfig(time_step_s=0.01)
    accepted = solve_nonlinear_mdof_transient(system, _forces()[:2], config=config).checkpoints[-1]
    accepted_manifest = accepted.to_dict()
    failing = NonlinearMDOFTransientConfig(
        time_step_s=0.01,
        residual_relative_tolerance=1.0e-14,
        residual_absolute_tolerance_kn=1.0e-14,
        maximum_iterations=1,
    )
    with pytest.raises(NonlinearMDOFTransientError, match="rolled back exactly"):
        # The nonlinear return mapping changes trial states, but no reference to
        # those trial states can replace the immutable accepted checkpoint.
        from structural_analysis.solvers.nonlinear import mdof_transient as module

        module._advance(system, failing, accepted, np.asarray([[200.0, -150.0]]))

    assert accepted.to_dict() == accepted_manifest
