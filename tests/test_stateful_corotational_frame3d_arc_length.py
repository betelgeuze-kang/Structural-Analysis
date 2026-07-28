"""Focused contracts for scaled sparse Frame3D arc-length continuation."""

from __future__ import annotations

from dataclasses import replace
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

import structural_analysis.assembly as assembly_namespace
import structural_analysis.assembly.stateful_corotational_frame3d_arc_length as arc_module
from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_arc_length import (
    STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION,
    StatefulCorotationalFrame3DArcLengthConfig,
    StatefulCorotationalFrame3DArcLengthError,
    stateful_corotational_frame3d_arc_length_continuation,
    validate_stateful_corotational_frame3d_arc_length_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseError,
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
    area_m2: float = 0.02,
    elastic_modulus_kn_per_m2: float = 2.0e8,
    inertia_m4: float = 5.0e-5,
) -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=area_m2,
            e_n_per_m2=elastic_modulus_kn_per_m2,
            g_n_per_m2=8.0e7,
            iy_m4=inertia_m4,
            iz_m4=inertia_m4,
            j_m4=max(inertia_m4, 1.0e-10),
        ),
        effective_shear_area_y_m2=0.75 * area_m2,
        effective_shear_area_z_m2=0.75 * area_m2,
    )


def _steel(
    material_id: str,
    *,
    yield_stress_mpa: float = 250.0,
) -> BilinearCombinedHardeningSteel:
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=yield_stress_mpa,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id=material_id,
    )


def _axial_model(
    *,
    restrained_dofs: tuple[int, ...] = tuple(range(6)),
    model_id: str = "arc-length-axial",
) -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 12
    load[6] = 6_000.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember(
                "member-1",
                0,
                1,
                _section(),
            ),
        ),
        restrained_dofs=restrained_dofs,
        reference_load_kn=tuple(load),
        model_id=model_id,
    )
    return StatefulCorotationalFrame3DSparseModel(
        elastic,
        (_steel(f"{model_id}-steel"),),
    )


def _axial_config(
    **overrides: object,
) -> StatefulCorotationalFrame3DArcLengthConfig:
    values: dict[str, object] = {
        "monitor_global_dof": 6,
        "target_monitor_displacement_m": 1.0e-3,
        "target_direction": 1,
        "solver_config": StatefulCorotationalFrame3DSparseConfig(),
        "initial_arc_length": 5.0e-4,
        "minimum_arc_length": 5.0e-5,
        "maximum_arc_length": 5.0e-4,
        "load_factor_metric_scale": 1.0e-3,
        "maximum_attempt_count": 40,
    }
    values.update(overrides)
    return StatefulCorotationalFrame3DArcLengthConfig(**values)  # type: ignore[arg-type]


def _bending_model() -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 12
    load[7] = -100.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember(
                "bending-member",
                0,
                1,
                _section(),
            ),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="arc-length-bending-checkpoint",
    )
    return StatefulCorotationalFrame3DSparseModel(
        elastic,
        (_steel("arc-bending-steel", yield_stress_mpa=1.0e9),),
    )


def _shallow_arch_model() -> StatefulCorotationalFrame3DSparseModel:
    section = _section(
        area_m2=1.0e-3,
        inertia_m4=1.0e-10,
    )
    load = [0.0] * 18
    load[7] = -1_000.0
    restrained = tuple(sorted(set(range(6)) | set(range(12, 18)) | {6, 8, 9, 10, 11}))
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=(
            (-1.0, 0.0, 0.0),
            (0.0, 0.1, 0.0),
            (1.0, 0.0, 0.0),
        ),
        members=(
            CorotationalFrame3DMember("left", 0, 1, section),
            CorotationalFrame3DMember("right", 1, 2, section),
        ),
        restrained_dofs=restrained,
        reference_load_kn=tuple(load),
        model_id="arc-length-shallow-arch",
    )
    return StatefulCorotationalFrame3DSparseModel(
        elastic,
        (
            _steel("arc-left", yield_stress_mpa=1.0e9),
            _steel("arc-right", yield_stress_mpa=1.0e9),
        ),
    )


def test_scaled_axial_arc_path_publishes_all_commit_gates() -> None:
    model = _axial_model()
    config = _axial_config()
    result = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
    )
    repeated = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
    )

    assert result.schema_version == (
        STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION
    )
    assert result.status == "ready"
    assert result.terminal_reason == "target_monitor_displacement_reached"
    assert result.metrics["contract_pass"] is True
    assert result.metrics["regularization_count"] == 0
    assert result.metrics["fallback_count"] == 0
    assert result.result_hash.startswith("sha256:")
    assert result.path_contract_hash.startswith("sha256:")
    assert repeated.to_dict() == result.to_dict()
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)
    assert result.final_state_checkpoint == result.final_checkpoint.accepted_checkpoint

    for step in result.steps:
        assert step.solved_load_factor == pytest.approx(
            step.monitor_displacement_m / 3.0e-3,
            rel=5.0e-9,
        )
        tangent_norm = math.sqrt(
            sum(value**2 for value in step.tangent_scaled_displacements)
            + (config.load_factor_metric_scale * step.tangent_load_factor) ** 2
        )
        assert tangent_norm == pytest.approx(1.0, abs=1.0e-12)
        assert abs(step.constraint_residual) <= config.constraint_tolerance
        assert all(step.convergence_checks.values())
        assert step.equation_scaling.characteristic_length == pytest.approx(2.0)
        assert step.equation_scaling.scaled_tangent_condition > 0.0
        assert step.augmented_scaled_condition_number == (
            step.equation_scaling.scaled_tangent_condition
        )
        assert step.to_dict()["condition_scope"] == (
            "dimensionless_augmented_equilibrium_arc_constraint_jacobian"
        )
        assert all(row.contract_pass for row in step.factorization_diagnostics)
        assert step.convergence_trace[-1]["accepted"] is True
        assert step.convergence_trace[-1]["condition_scope"] == (
            "dimensionless_augmented_equilibrium_arc_constraint_jacobian"
        )
    assert result.metrics["scaling_hash"] == (
        result.steps[-1].equation_scaling.scaling_hash
    )
    assert result.metrics["maximum_scaled_residual_norm"] is not None
    assert result.metrics["maximum_arc_constraint_residual"] is not None
    assert result.metrics["failed_attempt_rollback_exact"] is None


def test_assembly_namespace_exports_arc_length_contract() -> None:
    exported = (
        "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_PROFILE",
        "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_CHECKPOINT_SCHEMA_VERSION",
        "STATEFUL_COROTATIONAL_FRAME3D_ARC_LENGTH_RESULT_SCHEMA_VERSION",
        "StatefulCorotationalFrame3DArcLengthConfig",
        "StatefulCorotationalFrame3DArcLengthCheckpoint",
        "StatefulCorotationalFrame3DArcLengthResult",
        "stateful_corotational_frame3d_arc_length_continuation",
        "validate_stateful_corotational_frame3d_arc_length_checkpoint",
    )
    for name in exported:
        assert name in assembly_namespace.__all__
        assert getattr(assembly_namespace, name) is getattr(arc_module, name)


def test_bending_checkpoint_binds_full_free_residual_norm() -> None:
    model = _bending_model()
    solver = StatefulCorotationalFrame3DSparseConfig()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=solver,
    )
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    displacement[9] = 1.0e-9
    assembly = arc_module.assemble_stateful_corotational_frame3d_sparse(
        model,
        parent,
        target_load_factor=0.0,
        trial_displacement=displacement,
    )
    residual = np.asarray(assembly.residual_free, dtype=np.float64)
    translation = max(
        abs(float(value))
        for value, dof in zip(residual, model.free_dofs)
        if dof % 6 < 3
    )
    rotation = max(
        abs(float(value))
        for value, dof in zip(residual, model.free_dofs)
        if dof % 6 >= 3
    )
    full_residual = float(np.linalg.norm(residual, ord=np.inf))

    assert rotation > translation
    assert full_residual == rotation
    assert arc_module._checkpoint_residual_inf_norm(residual) == full_residual

    translation_only = arc_module._make_checkpoint(
        model=model,
        config=solver,
        step_index=1,
        load_factor=0.0,
        displacement=assembly.displacement,
        material_states=assembly.trial_material_states,
        converged_iterations=1,
        residual_inf_norm_kn=translation,
        parent_checkpoint_hash=parent.checkpoint_hash,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="residual observation is inconsistent",
    ):
        arc_module.validate_stateful_corotational_frame3d_sparse_checkpoint(
            translation_only,
            model=model,
            config=solver,
            require_equilibrium=True,
        )

    full_vector = arc_module._make_checkpoint(
        model=model,
        config=solver,
        step_index=1,
        load_factor=0.0,
        displacement=assembly.displacement,
        material_states=assembly.trial_material_states,
        converged_iterations=1,
        residual_inf_norm_kn=full_residual,
        parent_checkpoint_hash=parent.checkpoint_hash,
    )
    assert (
        arc_module.validate_stateful_corotational_frame3d_sparse_checkpoint(
            full_vector,
            model=model,
            config=solver,
            require_equilibrium=True,
        )
        == full_vector
    )


def test_dimensionless_augmented_tangent_matches_finite_differences() -> None:
    model = _axial_model(model_id="arc-linearization")
    config = _axial_config()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.solver_config,
    )
    scaling = arc_module._arc_length_scaling(
        model,
        config.solver_config,
    )
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    displacement[7] = 1.0e-4
    displacement[11] = 2.0e-4
    scaled_coordinates = scaling.scale_increment(displacement[list(model.free_dofs)])
    parent_scaled = scaling.scale_increment(
        np.asarray(parent.displacement, dtype=np.float64)[list(model.free_dofs)]
    )
    load_factor = 0.1
    center = arc_module._arc_trial(
        model=model,
        parent=parent,
        scaled_coordinates=scaled_coordinates,
        load_factor=load_factor,
        scaling=scaling,
    )
    reference_load = np.asarray(
        model.elastic_model.reference_load_kn,
        dtype=np.float64,
    )[list(model.free_dofs)]
    scaled_reference_load = scaling.scale_residual(reference_load)
    delta_coordinates = scaled_coordinates - parent_scaled
    delta_load = load_factor - parent.load_factor
    arc_length = 8.0e-4
    augmented = arc_module._augmented_tangent(
        center,
        scaling=scaling,
        scaled_reference_load=scaled_reference_load,
        delta_coordinates=delta_coordinates,
        delta_load_factor=delta_load,
        load_factor_metric_scale=config.load_factor_metric_scale,
    ).toarray()

    def augmented_residual(
        coordinates: np.ndarray,
        load: float,
    ) -> np.ndarray:
        trial = arc_module._arc_trial(
            model=model,
            parent=parent,
            scaled_coordinates=coordinates,
            load_factor=load,
            scaling=scaling,
        )
        constraint = arc_module._constraint_residual(
            coordinates - parent_scaled,
            load - parent.load_factor,
            arc_length=arc_length,
            load_factor_metric_scale=config.load_factor_metric_scale,
        )
        return np.concatenate((trial.scaled_residual, np.asarray([constraint])))

    finite_step = 1.0e-7
    for column in (0, 1, 5):
        direction = np.zeros_like(scaled_coordinates)
        direction[column] = finite_step
        finite_difference = (
            augmented_residual(
                scaled_coordinates + direction,
                load_factor,
            )
            - augmented_residual(
                scaled_coordinates - direction,
                load_factor,
            )
        ) / (2.0 * finite_step)
        np.testing.assert_allclose(
            augmented[:, column],
            finite_difference,
            rtol=3.0e-5,
            atol=3.0e-6,
        )

    finite_load_column = (
        augmented_residual(
            scaled_coordinates,
            load_factor + finite_step,
        )
        - augmented_residual(
            scaled_coordinates,
            load_factor - finite_step,
        )
    ) / (2.0 * finite_step)
    np.testing.assert_allclose(
        augmented[:, -1],
        finite_load_column,
        rtol=1.0e-9,
        atol=1.0e-9,
    )


def test_corrector_line_search_cannot_bypass_strict_merit_decrease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model(model_id="arc-line-search-merit")
    config = _axial_config()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.solver_config,
    )
    scaling = arc_module._arc_length_scaling(model, config.solver_config)
    parent_scaled = scaling.scale_increment(
        np.asarray(parent.displacement, dtype=np.float64)[list(model.free_dofs)]
    )
    coordinate_correction = np.zeros(len(model.free_dofs), dtype=np.float64)
    coordinate_correction[0] = config.initial_arc_length

    monkeypatch.setattr(
        arc_module,
        "_arc_trial",
        lambda **_kwargs: SimpleNamespace(scaled_residual_norm=0.0),
    )
    monkeypatch.setattr(arc_module, "_arc_merit", lambda *_args, **_kwargs: 1.0)

    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="failed to reduce normalized merit",
    ) as failure:
        arc_module._arc_corrector_line_search(
            model=model,
            config=config,
            parent=parent,
            parent_signature=arc_module._checkpoint_parent_signature(parent),
            parent_scaled=parent_scaled,
            scaled_coordinates=parent_scaled,
            load_factor=parent.load_factor,
            coordinate_correction=coordinate_correction,
            load_correction=0.0,
            scaling=scaling,
            arc_length=config.initial_arc_length,
            base_merit=1.0,
            residual_tolerance=1.0,
        )

    first_attempt = failure.value.attempts[0]
    assert first_attempt["scaled_residual_norm"] == 0.0
    assert first_attempt["constraint_residual"] == pytest.approx(0.0)
    assert first_attempt["normalized_merit"] == 1.0
    assert first_attempt["required_normalized_merit"] == 1.0
    assert first_attempt["accepted"] is False


def test_shallow_arch_crosses_limit_point_and_descending_branch() -> None:
    model = _shallow_arch_model()
    config = StatefulCorotationalFrame3DArcLengthConfig(
        monitor_global_dof=7,
        target_monitor_displacement_m=-0.12,
        target_direction=-1,
        solver_config=StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40),
        initial_arc_length=0.015,
        minimum_arc_length=1.0e-5,
        maximum_arc_length=0.015,
        load_factor_metric_scale=1.0e-3,
        maximum_attempt_count=20,
    )
    result = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
    )
    load_factors = [step.solved_load_factor for step in result.steps]
    monitor_values = [step.monitor_displacement_m for step in result.steps]

    assert result.status == "ready"
    assert result.metrics["descending_load_branch_observed"] is True
    assert result.metrics["maximum_load_factor"] == pytest.approx(max(load_factors))
    assert max(load_factors) > load_factors[-1]
    assert load_factors[-1] < 0.0
    assert monitor_values[-1] <= config.target_monitor_displacement_m
    assert all(right < left for left, right in zip(monitor_values, monitor_values[1:]))
    assert all(all(step.convergence_checks.values()) for step in result.steps)
    assert all(attempt.rollback_exact for attempt in result.attempts)


def test_failed_attempt_reduces_radius_and_restarts_bit_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model(model_id="arc-restart")
    config = _axial_config(
        target_monitor_displacement_m=2.0e-3,
        initial_arc_length=7.5e-4,
        maximum_arc_length=7.5e-4,
    )
    original = arc_module._solve_arc_attempt
    call_count = 0

    def fail_once(**kwargs: object):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise StatefulCorotationalFrame3DArcLengthError(
                "forced retryable arc attempt",
                code="arc_length_corrector_line_search_failed",
                attempts=({"iteration": 0, "forced": True},),
            )
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(arc_module, "_solve_arc_attempt", fail_once)
    one_shot = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
    )
    rejected_boundary = one_shot.checkpoints[1]
    restarted = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
        checkpoint=rejected_boundary,
    )
    rejected_attempt = one_shot.attempts[0]

    assert one_shot.status == "ready"
    assert rejected_attempt.outcome == "rolled_back"
    assert rejected_attempt.failure_code == "arc_length_corrector_line_search_failed"
    assert rejected_attempt.rollback_exact is True
    assert rejected_attempt.parent_checkpoint_hash == (
        rejected_attempt.accepted_checkpoint_hash
    )
    assert rejected_attempt.next_arc_length == pytest.approx(
        rejected_attempt.arc_length * config.failed_step_reduction_factor
    )
    assert rejected_boundary.last_attempt_outcome == "rolled_back"
    assert (
        rejected_boundary.last_attempt_code == "arc_length_corrector_line_search_failed"
    )
    assert restarted.initial_checkpoint == rejected_boundary
    assert restarted.final_checkpoint == one_shot.final_checkpoint
    assert restarted.final_state_checkpoint == one_shot.final_state_checkpoint


def test_committed_boundary_restart_matches_uninterrupted_terminal_state() -> None:
    model = _axial_model(model_id="arc-committed-restart")
    config = _axial_config(target_monitor_displacement_m=2.0e-3)
    uninterrupted = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
    )
    committed_boundary = uninterrupted.checkpoints[1]

    assert committed_boundary.last_attempt_outcome == "committed"
    assert committed_boundary.accepted_step_count == 1
    assert committed_boundary.accepted_checkpoint != (
        uninterrupted.final_state_checkpoint
    )

    restarted = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
        checkpoint=committed_boundary,
    )

    assert restarted.initial_checkpoint == committed_boundary
    assert restarted.final_checkpoint == uninterrupted.final_checkpoint
    assert restarted.final_state_checkpoint == uninterrupted.final_state_checkpoint


def test_underconstrained_path_exhausts_radius_without_parent_mutation() -> None:
    model = _axial_model(
        restrained_dofs=(0, 1, 2),
        model_id="arc-underconstrained",
    )
    config = _axial_config(
        initial_arc_length=1.0e-3,
        minimum_arc_length=3.0e-4,
        maximum_arc_length=1.0e-3,
    )
    initial = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.solver_config,
    )
    initial_payload = initial.to_dict()
    result = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
        initial_state=initial,
    )

    assert result.status == "blocked"
    assert result.terminal_reason == "minimum_arc_length_exhausted"
    assert len(result.attempts) == 2
    assert all(
        attempt.outcome == "rolled_back"
        and attempt.rollback_exact
        and attempt.parent_checkpoint_hash == attempt.accepted_checkpoint_hash
        for attempt in result.attempts
    )
    assert result.final_state_checkpoint == initial
    assert initial.to_dict() == initial_payload


def test_checkpoint_tamper_and_path_drift_fail_closed() -> None:
    model = _axial_model(model_id="arc-checkpoint")
    config = _axial_config()
    result = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
    )
    checkpoint = result.checkpoints[1]
    tampered = replace(
        checkpoint,
        current_arc_length=0.9 * checkpoint.current_arc_length,
    )

    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="hash mismatch",
    ):
        validate_stateful_corotational_frame3d_arc_length_checkpoint(
            tampered,
            model=model,
            config=config,
        )
    invalid_radius = replace(
        checkpoint,
        current_arc_length=float("nan"),
    )
    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="radius is invalid",
    ) as radius_failure:
        validate_stateful_corotational_frame3d_arc_length_checkpoint(
            invalid_radius,
            model=model,
            config=config,
        )
    assert radius_failure.value.code == "arc_length_checkpoint_invalid"
    invalid_tangent = replace(
        checkpoint,
        previous_tangent_load_factor=float("nan"),
    )
    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="tangent is invalid",
    ):
        validate_stateful_corotational_frame3d_arc_length_checkpoint(
            invalid_tangent,
            model=model,
            config=config,
        )
    invalid_accepted = replace(
        checkpoint,
        accepted_checkpoint=replace(
            checkpoint.accepted_checkpoint,
            load_factor=checkpoint.accepted_checkpoint.load_factor + 0.1,
        ),
    )
    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="accepted checkpoint is invalid",
    ) as accepted_failure:
        validate_stateful_corotational_frame3d_arc_length_checkpoint(
            invalid_accepted,
            model=model,
            config=config,
        )
    assert accepted_failure.value.code == (
        "arc_length_checkpoint_accepted_state_invalid"
    )
    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="binding",
    ):
        stateful_corotational_frame3d_arc_length_continuation(
            model,
            config=replace(
                config,
                target_monitor_displacement_m=2.0e-3,
            ),
            checkpoint=checkpoint,
        )


def test_invalid_monitor_and_radius_contracts_fail_closed() -> None:
    model = _axial_model(model_id="arc-invalid")

    with pytest.raises(ValueError, match="free global DOF"):
        stateful_corotational_frame3d_arc_length_continuation(
            model,
            config=_axial_config(monitor_global_dof=0),
        )
    with pytest.raises(ValueError, match="translational"):
        stateful_corotational_frame3d_arc_length_continuation(
            model,
            config=_axial_config(monitor_global_dof=9),
        )
    with pytest.raises(
        StatefulCorotationalFrame3DArcLengthError,
        match="already reached",
    ):
        stateful_corotational_frame3d_arc_length_continuation(
            model,
            config=_axial_config(
                target_monitor_displacement_m=-1.0e-3,
                target_direction=1,
            ),
        )
    with pytest.raises(ValueError, match="cannot exceed"):
        _axial_config(
            initial_arc_length=2.0e-3,
            maximum_arc_length=1.0e-3,
        )
    with pytest.raises(ValueError, match="finite"):
        _axial_config(load_factor_metric_scale=float("nan"))
    with pytest.raises(
        ValueError,
        match=(
            "maximum_corrector_iterations cannot exceed "
            "solver_config.maximum_iterations"
        ),
    ):
        _axial_config(
            solver_config=StatefulCorotationalFrame3DSparseConfig(maximum_iterations=4),
            maximum_corrector_iterations=5,
        )


def test_confined_concrete_unloading_is_nonretryable_and_rolled_back() -> None:
    material = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)
    section = _section(elastic_modulus_kn_per_m2=material.elastic_modulus_mpa * 1000.0)
    load = [0.0] * 12
    load[6] = -300.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, section),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="arc-confined-concrete",
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
    config = StatefulCorotationalFrame3DArcLengthConfig(
        monitor_global_dof=6,
        target_monitor_displacement_m=0.5 * parent.displacement[6],
        target_direction=1,
        solver_config=solver,
        initial_arc_length=1.0e-3,
        minimum_arc_length=1.0e-5,
        maximum_arc_length=1.0e-3,
        load_factor_metric_scale=1.0e-3,
        maximum_attempt_count=20,
    )
    result = stateful_corotational_frame3d_arc_length_continuation(
        model,
        config=config,
        initial_state=parent,
    )

    assert result.status == "blocked"
    assert result.terminal_reason == "unsupported_constitutive_path"
    assert len(result.attempts) == 1
    assert result.attempts[0].outcome == "rolled_back"
    assert result.attempts[0].failure_code == "unsupported_constitutive_path"
    assert result.attempts[0].rollback_exact is True
    assert result.attempts[0].convergence_checks["retryable_failure"] is False
    assert result.final_state_checkpoint == parent
    assert parent.to_dict() == parent_payload
