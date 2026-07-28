"""Focused contracts for bounded sparse Frame3D displacement control."""

from __future__ import annotations

import numpy as np
import pytest

import structural_analysis.assembly.stateful_corotational_frame3d_displacement_control as direct_module
import structural_analysis.assembly.stateful_corotational_frame3d_sparse as sparse_module
from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION,
    StatefulCorotationalFrame3DDisplacementControlConfig,
    StatefulCorotationalFrame3DDisplacementControlError,
    solve_stateful_corotational_frame3d_displacement_control_path,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseModel,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    solve_stateful_corotational_frame3d_sparse_load_path,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.materials.confined_concrete import (
    ConfinedConcreteMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


def _section(
    *,
    elastic_modulus_kn_per_m2: float = 2.0e8,
) -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.02,
            e_n_per_m2=elastic_modulus_kn_per_m2,
            g_n_per_m2=8.0e7,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )


def _steel() -> BilinearCombinedHardeningSteel:
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id="direct-control-steel",
    )


def _model(
    *,
    reference_load: tuple[float, ...] | None = None,
    restrained_dofs: tuple[int, ...] = tuple(range(6)),
    model_id: str = "direct-control-axial",
) -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 12
    load[6] = 6_000.0
    if reference_load is not None:
        load = list(reference_load)
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, _section()),),
        restrained_dofs=restrained_dofs,
        reference_load_kn=tuple(load),
        model_id=model_id,
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, (_steel(),))


def test_axial_direct_control_matches_closed_form_and_publishes_scaled_gates() -> None:
    model = _model()
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    result = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        (5.0e-4,),
        control_global_dof=6,
        config=config,
    )
    step = result.steps[0]

    assert result.schema_version == (
        STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION
    )
    assert result.direct_control_contract_hash == config.contract_hash
    assert result.target_control_displacements_m == (5.0e-4,)
    assert step.solved_load_factor == pytest.approx(1.0 / 6.0, rel=1.0e-10)
    assert step.checkpoint.displacement[6] == pytest.approx(5.0e-4)
    assert step.control_reference_m == pytest.approx(5.0e-4)
    assert step.scaled_control_error == pytest.approx(0.0, abs=1.0e-12)
    assert step.scaled_control_tolerance > 0.0
    assert step.augmented_scaled_condition_number > 0.0
    assert all(step.convergence_checks.values())
    assert step.equation_scaling.scaled_residual_norm >= 0.0
    assert step.equation_scaling.scaled_increment_norm >= 0.0
    assert all(
        row.contract_pass for row in step.factorization_diagnostics
    )
    assert result.regularization_used is False
    assert result.fallback_used is False
    assert result.contract_pass is True


def test_moment_loading_controls_transverse_dof_with_augmented_line_search() -> None:
    load = [0.0] * 12
    load[11] = 10.0
    model = _model(
        reference_load=tuple(load),
        model_id="direct-control-moment-cantilever",
    )
    result = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        (1.0e-2,),
        control_global_dof=7,
        config=StatefulCorotationalFrame3DDisplacementControlConfig(),
    )
    step = result.steps[0]

    assert step.checkpoint.displacement[7] == pytest.approx(1.0e-2)
    assert step.solved_load_factor == pytest.approx(8.0000333338, rel=2.0e-8)
    assert any(alpha < 1.0 for alpha in step.accepted_line_search_alphas)
    assert step.convergence_trace[0]["control_reference_m"] == pytest.approx(
        1.0e-2
    )
    assert step.convergence_trace[0]["condition_scope"] == (
        "dimensionless_augmented_equilibrium_control_jacobian"
    )
    assert step.convergence_trace[0]["equation_scaling"][
        "rotation_residual_norm"
    ] >= 0.0
    assert all(step.convergence_checks.values())


def test_scaled_augmented_jacobian_matches_displacement_and_load_differences() -> None:
    load = [0.0] * 12
    load[11] = 10.0
    model = _model(
        reference_load=tuple(load),
        model_id="direct-control-augmented-linearization",
    )
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.solver_config,
    )
    scaling = sparse_module._equation_scaling(model, config.solver_config)
    control_free_index = model.free_dofs.index(7)
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    displacement[7] = 5.0e-4
    displacement[11] = 2.0e-4
    target = 1.0e-3
    control_reference = 1.0e-3
    load_factor = 0.4
    center = direct_module._direct_trial(
        model=model,
        parent=parent,
        target=target,
        control_free_index=control_free_index,
        displacement=displacement,
        load_factor=load_factor,
        scaling=scaling,
        control_reference=control_reference,
    )
    augmented = center.augmented_tangent.toarray()
    step = 1.0e-6

    for column in (control_free_index, model.free_dofs.index(11)):
        physical_step = scaling.increment_scales[column] * step
        plus_displacement = displacement.copy()
        minus_displacement = displacement.copy()
        plus_displacement[model.free_dofs[column]] += physical_step
        minus_displacement[model.free_dofs[column]] -= physical_step
        plus = direct_module._direct_trial(
            model=model,
            parent=parent,
            target=target,
            control_free_index=control_free_index,
            displacement=plus_displacement,
            load_factor=load_factor,
            scaling=scaling,
            control_reference=control_reference,
        )
        minus = direct_module._direct_trial(
            model=model,
            parent=parent,
            target=target,
            control_free_index=control_free_index,
            displacement=minus_displacement,
            load_factor=load_factor,
            scaling=scaling,
            control_reference=control_reference,
        )
        finite_difference = (
            plus.augmented_residual - minus.augmented_residual
        ) / (2.0 * step)
        np.testing.assert_allclose(
            augmented[:, column],
            finite_difference,
            rtol=2.0e-5,
            atol=2.0e-6,
        )

    plus_load = direct_module._direct_trial(
        model=model,
        parent=parent,
        target=target,
        control_free_index=control_free_index,
        displacement=displacement,
        load_factor=load_factor + step,
        scaling=scaling,
        control_reference=control_reference,
    )
    minus_load = direct_module._direct_trial(
        model=model,
        parent=parent,
        target=target,
        control_free_index=control_free_index,
        displacement=displacement,
        load_factor=load_factor - step,
        scaling=scaling,
        control_reference=control_reference,
    )
    finite_load_column = (
        plus_load.augmented_residual - minus_load.augmented_residual
    ) / (2.0 * step)
    np.testing.assert_allclose(
        augmented[:, -1],
        finite_load_column,
        rtol=1.0e-10,
        atol=1.0e-10,
    )


def test_direct_control_path_resume_and_reversal_are_checkpoint_exact() -> None:
    model = _model()
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    targets = (5.0e-4, 1.0e-3, -5.0e-4)
    one_shot = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets,
        control_global_dof=6,
        config=config,
    )
    prefix = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets[:2],
        control_global_dof=6,
        config=config,
    )
    resumed = solve_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets[2:],
        control_global_dof=6,
        config=config,
        resume_from=prefix.final_checkpoint,
    )

    assert one_shot.final_checkpoint == resumed.final_checkpoint
    assert one_shot.final_checkpoint.parent_checkpoint_hash == (
        prefix.final_checkpoint.checkpoint_hash
    )
    assert one_shot.final_checkpoint.displacement[6] == pytest.approx(-5.0e-4)
    assert one_shot.final_checkpoint.load_factor == pytest.approx(-1.0 / 6.0)
    assert one_shot.exact_checkpoint_resume_supported is True
    assert one_shot.parent_state_immutability_enforced is True
    assert all(
        step.checkpoint.parent_checkpoint_hash
        == one_shot.checkpoints[index].checkpoint_hash
        for index, step in enumerate(one_shot.steps)
    )


def test_direct_control_rejects_invalid_control_contracts() -> None:
    model = _model()
    config = StatefulCorotationalFrame3DDisplacementControlConfig()

    with pytest.raises(ValueError, match="free global DOF"):
        solve_stateful_corotational_frame3d_displacement_control_path(
            model,
            (1.0e-3,),
            control_global_dof=0,
            config=config,
        )
    with pytest.raises(ValueError, match="translational"):
        solve_stateful_corotational_frame3d_displacement_control_path(
            model,
            (1.0e-3,),
            control_global_dof=9,
            config=config,
        )
    with pytest.raises(ValueError, match="distinct"):
        solve_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.0,),
            control_global_dof=6,
            config=config,
        )
    with pytest.raises(ValueError, match="finite"):
        solve_stateful_corotational_frame3d_displacement_control_path(
            model,
            (float("nan"),),
            control_global_dof=6,
            config=config,
        )
    with pytest.raises(ValueError, match="must be positive"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            control_absolute_tolerance_m=0.0
        )


def test_singular_augmented_system_fails_with_exact_parent_rollback() -> None:
    model = _model(
        restrained_dofs=(0, 1, 2),
        model_id="direct-control-underconstrained",
    )
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.solver_config,
    )
    parent_payload = parent.to_dict()

    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="augmented factorization failed",
    ) as failure:
        solve_stateful_corotational_frame3d_displacement_control_path(
            model,
            (1.0e-3,),
            control_global_dof=6,
            config=config,
            resume_from=parent,
        )

    assert failure.value.code == "direct_control_augmented_factorization_failed"
    assert len(failure.value.attempts) == 1
    assert failure.value.attempts[0]["rollback_exact"] is True
    assert parent.to_dict() == parent_payload


def test_confined_concrete_unloading_is_not_hidden_by_direct_control() -> None:
    material = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)
    section = _section(
        elastic_modulus_kn_per_m2=material.elastic_modulus_mpa * 1000.0
    )
    load = [0.0] * 12
    load[6] = -300.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, section),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="direct-control-confined-concrete",
    )
    model = StatefulCorotationalFrame3DSparseModel(elastic, (material,))
    solver = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40)
    loaded = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=solver,
    )
    parent = loaded.final_checkpoint
    parent_payload = parent.to_dict()
    target = 0.5 * parent.displacement[6]

    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="unsupported_constitutive_path",
    ) as failure:
        solve_stateful_corotational_frame3d_displacement_control_path(
            model,
            (target,),
            control_global_dof=6,
            config=StatefulCorotationalFrame3DDisplacementControlConfig(
                solver_config=solver
            ),
            resume_from=parent,
        )

    assert failure.value.code == "unsupported_constitutive_path"
    assert failure.value.attempts[0]["rollback_exact"] is True
    assert parent.to_dict() == parent_payload
