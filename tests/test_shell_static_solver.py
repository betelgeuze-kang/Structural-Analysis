from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.solvers.linear.shell_static import (
    ShellStaticError,
    ShellStaticModel,
    resume_shell_static,
    solve_shell_static,
)


def _cantilever_panel() -> ShellStaticModel:
    load = np.zeros(24)
    load[2 * 6 + 2] = -1_000.0
    load[3 * 6 + 2] = -1_000.0
    return ShellStaticModel(
        model_id="shell-square-cantilever-v1",
        node_ids=("N1", "N2", "N3", "N4"),
        node_coordinates_m=((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)),
        element_ids=("S1", "S2"),
        element_connectivity=((0, 2, 3), (0, 3, 1)),
        elastic_modulus_pa=210.0e9,
        poisson_ratio=0.3,
        thickness_m=0.1,
        restrained_dofs=tuple(range(12)),
        load_global_n_nm=load,
    )


def test_shell_static_closes_physical_equilibrium_without_fallback() -> None:
    result = solve_shell_static(_cantilever_panel())

    assert result.contract_pass
    assert not result.fallback_used
    assert not result.regularization_used
    assert result.free_dof_count == 12
    assert result.maximum_free_residual <= 1.0e-10
    assert result.displacement_global[2 * 6 + 2] < 0.0
    assert result.displacement_global[3 * 6 + 2] < 0.0
    assert result.strain_energy_j == pytest.approx(result.external_work_j, rel=2.0e-13)
    assert sum(item.strain_energy_j for item in result.element_results) == pytest.approx(
        result.strain_energy_j, rel=2.0e-13
    )
    assert sum(result.reaction_global_n_nm[2::6]) == pytest.approx(2_000.0, abs=1.0e-9)


def test_shell_static_exact_restart_and_tamper_rejection() -> None:
    model = _cantilever_panel()
    solved = solve_shell_static(model)

    assert resume_shell_static(model, solved.checkpoint) == solved
    damaged = replace(
        solved.checkpoint,
        displacement_global=(solved.checkpoint.displacement_global[0] + 1.0,) + solved.checkpoint.displacement_global[1:],
    )
    with pytest.raises(ShellStaticError, match="hash mismatch"):
        resume_shell_static(model, damaged)


def test_shell_static_rejects_a_mechanism_instead_of_regularizing() -> None:
    model = _cantilever_panel()
    mechanism = ShellStaticModel(
        model_id=model.model_id,
        node_ids=model.node_ids,
        node_coordinates_m=model.node_coordinates_m,
        element_ids=model.element_ids,
        element_connectivity=model.element_connectivity,
        elastic_modulus_pa=model.elastic_modulus_pa,
        poisson_ratio=model.poisson_ratio,
        thickness_m=model.thickness_m,
        restrained_dofs=tuple(range(6)),
        load_global_n_nm=model.load_global_n_nm,
    )
    with pytest.raises(ShellStaticError, match="singular"):
        solve_shell_static(mechanism)
