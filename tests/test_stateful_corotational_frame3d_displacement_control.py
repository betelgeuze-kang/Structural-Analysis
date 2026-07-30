"""Focused contracts for bounded sparse Frame3D direct displacement control."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

import structural_analysis.assembly as assembly_namespace
import structural_analysis.assembly.stateful_corotational_frame3d_displacement_control as direct_control_module
from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE,
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION,
    StatefulCorotationalFrame3DDisplacementControlConfig,
    StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
    StatefulCorotationalFrame3DDisplacementControlError,
    StatefulCorotationalFrame3DDisplacementControlStepProblem,
    finite_difference_stateful_corotational_frame3d_displacement_control_check,
    run_stateful_corotational_frame3d_displacement_control_path,
    solve_stateful_corotational_frame3d_displacement_control_step,
    validate_stateful_corotational_frame3d_displacement_control_resume_binding,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseModel,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityState,
)


ROOT = Path(__file__).resolve().parents[1]


def _section() -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.02,
            e_n_per_m2=2.0e8,
            g_n_per_m2=8.0e7,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )


def _material() -> BilinearCombinedHardeningSteel:
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id="direct-control-steel",
    )


def _cantilever_model(
    *,
    reference_dof: int = 6,
    reference_value: float = 6_000.0,
    restrained_dofs: tuple[int, ...] = tuple(range(6)),
    model_id: str = "frame3d-direct-control-cantilever",
) -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 12
    load[reference_dof] = reference_value
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember("member-1", 0, 1, _section()),
        ),
        restrained_dofs=restrained_dofs,
        reference_load_kn=tuple(load),
        model_id=model_id,
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, (_material(),))


def test_axial_yield_path_commits_and_exact_checkpoint_resume_matches() -> None:
    model = _cantilever_model()
    targets = (0.001, 0.002, 0.003, 0.004)

    one_shot = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets,
        control_global_dof=6,
    )
    prefix = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets[:2],
        control_global_dof=6,
    )
    resumed = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets[2:],
        control_global_dof=6,
        resume_from=prefix.final_checkpoint,
        resume_binding=prefix.resume_binding,
    )

    assert one_shot.status == "ready"
    assert one_shot.contract_pass is True
    assert len(one_shot.checkpoints) == len(targets) + 1
    assert all(step.committed for step in one_shot.steps)
    assert one_shot.final_checkpoint.displacement[6] == pytest.approx(targets[-1])
    assert one_shot.steps[1].solution.load_factor == pytest.approx(2.0 / 3.0)
    assert one_shot.steps[-1].solution.load_factor == pytest.approx(13.0 / 12.0)
    final_state = one_shot.final_checkpoint.material_states[0]
    assert isinstance(final_state, UniaxialPlasticityState)
    assert final_state.accumulated_plastic_strain > 0
    assert one_shot.final_checkpoint == resumed.final_checkpoint
    assert one_shot.resume_binding == resumed.resume_binding
    assert one_shot.checkpoints[3:] == resumed.checkpoints[1:]
    assert [step.result_hash for step in one_shot.steps[2:]] == [
        step.result_hash for step in resumed.steps
    ]
    assert one_shot.exact_checkpoint_resume_supported is True
    assert one_shot.resume_mode == "fresh_start"
    assert one_shot.resume_contract_verified is False
    assert resumed.resume_mode == "exact_bound_resume"
    assert resumed.resume_contract_verified is True
    assert one_shot.regularization_used is False
    assert one_shot.fallback_used is False
    assert one_shot.result_hash.startswith("sha256:")
    assert one_shot.to_dict()["result_hash"] == one_shot.result_hash

    for step in one_shot.steps:
        metrics = step.solution.metrics
        assert metrics["contract_pass"] is True
        assert step.accepted_checkpoint is not None
        assert step.accepted_checkpoint.converged_iterations == metrics[
            "converged_iterations"
        ]
        assert metrics["converged_iterations"] == metrics[
            "line_search_step_count"
        ]
        assert metrics["iteration_count"] == metrics["converged_iterations"] + 1
        assert metrics["raw_translational_residual_inf_norm_kn"] >= 0.0
        assert metrics["raw_rotational_residual_inf_norm_kn_m"] >= 0.0
        assert metrics["raw_translation_increment_inf_norm_m"] is not None
        assert metrics["raw_rotation_increment_inf_norm_rad"] is not None
        assert metrics["scaled_increment"] is not None
        assert metrics["scaled_condition_number_1"] > 0.0
        assert all(
            row["selected_alpha"] is not None
            for row in step.solution.line_search_history
        )
        assert all(
            diagnostic.contract_pass
            for diagnostic in step.solution.factorization_diagnostics
        )

    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_displacement_control_resume_binding_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(one_shot.resume_binding.to_dict())
    assert (
        one_shot.resume_binding.schema_version
        == STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION
    )


def test_cyclic_reversal_v2_chain_and_exact_resume_match() -> None:
    model = _cantilever_model(model_id="frame3d-direct-control-cyclic")
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        allow_direction_reversal=True,
        maximum_direction_reversals=4,
    )
    targets = (0.003, 0.006, 0.001, -0.004, 0.002)

    one_shot = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets,
        control_global_dof=6,
        config=config,
    )
    prefix = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets[:2],
        control_global_dof=6,
        config=config,
    )
    resumed = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        targets[2:],
        control_global_dof=6,
        config=config,
        resume_from=prefix.final_checkpoint,
        resume_binding=prefix.resume_binding,
    )

    assert one_shot.status == "ready"
    assert one_shot.path_mode == (
        STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE
    )
    assert one_shot.requested_target_direction_signs == (1, 1, -1, -1, 1)
    assert one_shot.requested_direction_reversal_count == 2
    assert one_shot.completed_direction_reversal_count == 2
    assert one_shot.cumulative_completed_target_count == 5
    assert one_shot.cumulative_direction_reversal_count == 2
    assert resumed.resumed_with_direction_reversal is True
    assert one_shot.final_checkpoint == resumed.final_checkpoint
    assert one_shot.final_checkpoint.material_states == (
        resumed.final_checkpoint.material_states
    )
    assert one_shot.accepted_target_chain_hash == (
        resumed.accepted_target_chain_hash
    )
    assert one_shot.resume_binding == resumed.resume_binding
    assert isinstance(
        one_shot.resume_binding,
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
    )
    assert one_shot.resume_binding.schema_version == (
        STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION
    )

    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_displacement_control_resume_binding_v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(one_shot.resume_binding.to_dict())

    tampered = replace(
        prefix.resume_binding,
        cumulative_completed_target_count=3,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_cyclic_resume_binding_hash_mismatch",
    ):
        validate_stateful_corotational_frame3d_displacement_control_resume_binding(
            tampered,
            checkpoint=prefix.final_checkpoint,
            model=model,
            config=config,
            control_global_dof=6,
        )

    monotonic = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.001, 0.002),
        control_global_dof=6,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_v1_binding_cyclic_policy_mismatch",
    ):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.003,),
            control_global_dof=6,
            config=config,
            resume_from=monotonic.final_checkpoint,
            resume_binding=monotonic.resume_binding,
        )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_v2_binding_monotonic_policy_mismatch",
    ):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.003,),
            control_global_dof=6,
            resume_from=prefix.final_checkpoint,
            resume_binding=prefix.resume_binding,
        )


def test_cyclic_reversal_limits_and_equal_targets_fail_closed() -> None:
    model = _cantilever_model(model_id="frame3d-direct-control-cyclic-limits")
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        allow_direction_reversal=True,
        maximum_direction_reversals=1,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_direction_reversal_limit_exceeded",
    ):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.002, -0.002, 0.001),
            control_global_dof=6,
            config=config,
        )
    with pytest.raises(ValueError, match="distinct coordinate"):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.002, 0.002),
            control_global_dof=6,
            config=config,
        )
    cumulative_config = StatefulCorotationalFrame3DDisplacementControlConfig(
        maximum_path_targets=2,
        allow_direction_reversal=True,
        maximum_direction_reversals=1,
    )
    prefix = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.001, 0.002),
        control_global_dof=6,
        config=cumulative_config,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_cumulative_target_limit_exceeded",
    ):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.003,),
            control_global_dof=6,
            config=cumulative_config,
            resume_from=prefix.final_checkpoint,
            resume_binding=prefix.resume_binding,
        )


def test_adaptive_target_cutback_is_deterministic_and_bound_resume_is_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _cantilever_model(model_id="frame3d-direct-target-cutback")
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        maximum_iterations=2,
        target_cutback_ratio=0.5,
        maximum_target_cutback_depth=4,
        maximum_target_cutback_substeps=8,
        maximum_path_solve_attempts=16,
    )
    initial = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.frame_config,
    )
    blocked_large = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        initial,
        control_global_dof=6,
        target_control_coordinate=0.004,
        config=replace(
            config,
            maximum_iterations=1,
            adaptive_target_cutback_enabled=False,
        ),
    )
    accepted_half = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        initial,
        control_global_dof=6,
        target_control_coordinate=0.002,
        config=config,
    )
    assert blocked_large.committed is False
    assert (
        blocked_large.solution.reason_code
        == "direct_control_maximum_iterations_exceeded"
    )
    assert accepted_half.accepted_checkpoint is not None
    accepted_target = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        accepted_half.accepted_checkpoint,
        control_global_dof=6,
        target_control_coordinate=0.004,
        config=config,
    )
    assert accepted_target.accepted_checkpoint is not None
    accepted_followup = (
        solve_stateful_corotational_frame3d_displacement_control_step(
            model,
            accepted_target.accepted_checkpoint,
            control_global_dof=6,
            target_control_coordinate=0.005,
            config=config,
        )
    )
    assert accepted_followup.accepted_checkpoint is not None

    lookup = {
        (initial.checkpoint_hash, 0.004): blocked_large,
        (initial.checkpoint_hash, 0.002): accepted_half,
        (accepted_half.accepted_checkpoint.checkpoint_hash, 0.004): (
            accepted_target
        ),
        (accepted_target.accepted_checkpoint.checkpoint_hash, 0.005): (
            accepted_followup
        ),
    }
    expected_contract_hash = config.contract_hash

    def deterministic_step(
        _model: StatefulCorotationalFrame3DSparseModel,
        parent: object,
        *,
        control_global_dof: int,
        target_control_coordinate: float,
        config: StatefulCorotationalFrame3DDisplacementControlConfig,
    ) -> object:
        assert _model is model
        assert control_global_dof == 6
        assert config.contract_hash == expected_contract_hash
        return lookup[(parent.checkpoint_hash, target_control_coordinate)]

    monkeypatch.setattr(
        direct_control_module,
        "solve_stateful_corotational_frame3d_displacement_control_step",
        deterministic_step,
    )
    one_shot = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.004, 0.005),
        control_global_dof=6,
        config=config,
    )
    repeated = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.004, 0.005),
        control_global_dof=6,
        config=config,
    )
    prefix = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.004,),
        control_global_dof=6,
        config=config,
    )
    resumed = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.005,),
        control_global_dof=6,
        config=config,
        resume_from=prefix.final_checkpoint,
        resume_binding=prefix.resume_binding,
    )

    assert one_shot.status == "ready"
    assert one_shot.contract_pass is True
    assert one_shot.adaptive_target_cutback_supported is True
    assert one_shot.adaptive_target_cutback_used is True
    assert one_shot.completed_requested_target_count == 2
    assert one_shot.solve_attempt_count == 4
    assert one_shot.final_checkpoint_at_requested_target_boundary is True
    assert one_shot.exact_checkpoint_resume_supported is True
    assert [step.target_control_coordinate for step in one_shot.steps] == [
        0.002,
        0.004,
        0.005,
    ]
    assert len(one_shot.checkpoints) == 4
    assert one_shot.completed_requested_target_checkpoint_hashes == (
        accepted_target.accepted_checkpoint.checkpoint_hash,
        accepted_followup.accepted_checkpoint.checkpoint_hash,
    )
    cutback = one_shot.target_cutback_history[0]
    assert cutback.requested_target_control_coordinate == 0.004
    assert cutback.rejected_target_control_coordinate == 0.004
    assert cutback.cutback_target_control_coordinate == 0.002
    assert cutback.accepted_parent_checkpoint_hash == initial.checkpoint_hash
    assert cutback.reason_code == "direct_control_maximum_iterations_exceeded"
    assert cutback.outcome == "cutback_scheduled"
    assert cutback.rejected_result_hash == blocked_large.result_hash
    assert cutback.parent_state_immutable is True
    assert one_shot.to_dict()["target_cutback_history"][0] == cutback.to_dict()
    assert one_shot.result_hash == repeated.result_hash
    assert one_shot.target_cutback_history == repeated.target_cutback_history
    assert one_shot.final_checkpoint == resumed.final_checkpoint
    assert one_shot.resume_binding == resumed.resume_binding
    assert one_shot.steps[-1].result_hash == resumed.steps[-1].result_hash
    assert prefix.adaptive_target_cutback_used is True
    assert resumed.resume_mode == "exact_bound_resume"
    assert resumed.resume_contract_verified is True

    terminal_solution = replace(
        blocked_large.solution,
        reason_code="direct_control_terminal_contract_failed",
    )
    terminal_after_half = replace(
        blocked_large,
        parent_checkpoint=accepted_half.accepted_checkpoint,
        solution=terminal_solution,
        result_hash="sha256:" + "1" * 64,
    )

    def incomplete_step(
        _model: StatefulCorotationalFrame3DSparseModel,
        parent: object,
        *,
        control_global_dof: int,
        target_control_coordinate: float,
        config: StatefulCorotationalFrame3DDisplacementControlConfig,
    ) -> object:
        assert _model is model
        assert control_global_dof == 6
        assert config.contract_hash == expected_contract_hash
        incomplete_lookup = {
            (initial.checkpoint_hash, 0.004): blocked_large,
            (initial.checkpoint_hash, 0.002): accepted_half,
            (accepted_half.accepted_checkpoint.checkpoint_hash, 0.004): (
                terminal_after_half
            ),
        }
        return incomplete_lookup[
            (parent.checkpoint_hash, target_control_coordinate)
        ]

    monkeypatch.setattr(
        direct_control_module,
        "solve_stateful_corotational_frame3d_displacement_control_step",
        incomplete_step,
    )
    incomplete = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.004,),
        control_global_dof=6,
        config=config,
    )
    assert incomplete.status == "blocked"
    assert incomplete.contract_pass is False
    assert incomplete.completed_requested_target_count == 0
    assert incomplete.final_checkpoint == accepted_half.accepted_checkpoint
    assert incomplete.final_checkpoint_at_requested_target_boundary is False
    assert incomplete.exact_checkpoint_resume_supported is False
    assert incomplete.terminal_reason_code == (
        "direct_control_terminal_contract_failed"
    )
    assert incomplete.resume_binding is None
    unbound_restart = (
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.004,),
            control_global_dof=6,
            config=config,
            resume_from=incomplete.final_checkpoint,
            resume_binding=incomplete.resume_binding,
        )
    )
    assert unbound_restart.resume_mode == "unbound_equilibrium_checkpoint_restart"
    assert unbound_restart.resume_contract_verified is False

    limited_config = replace(config, maximum_path_solve_attempts=1)

    def first_attempt_only(
        _model: StatefulCorotationalFrame3DSparseModel,
        parent: object,
        *,
        control_global_dof: int,
        target_control_coordinate: float,
        config: StatefulCorotationalFrame3DDisplacementControlConfig,
    ) -> object:
        assert _model is model
        assert parent.checkpoint_hash == initial.checkpoint_hash
        assert control_global_dof == 6
        assert target_control_coordinate == 0.004
        assert config.contract_hash == limited_config.contract_hash
        return blocked_large

    monkeypatch.setattr(
        direct_control_module,
        "solve_stateful_corotational_frame3d_displacement_control_step",
        first_attempt_only,
    )
    attempt_limited = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.004,),
        control_global_dof=6,
        config=limited_config,
    )
    assert attempt_limited.status == "blocked"
    assert attempt_limited.terminal_reason_code == (
        "direct_control_path_solve_attempt_limit_exceeded"
    )
    assert attempt_limited.solve_attempt_count == 1
    assert len(attempt_limited.target_cutback_history) == 1
    assert attempt_limited.target_cutback_history[0].outcome == (
        "cutback_scheduled"
    )


def test_target_cutback_exhaustion_preserves_resume_parent() -> None:
    model = _cantilever_model(model_id="frame3d-direct-cutback-exhaustion")
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        maximum_iterations=1,
        maximum_target_cutback_depth=0,
    )
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.frame_config,
    )
    parent_payload = parent.to_dict()
    result = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.004,),
        control_global_dof=6,
        config=config,
        resume_from=parent,
    )
    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.terminal_reason_code == "direct_control_target_cutback_exhausted"
    assert result.final_checkpoint == parent
    assert result.final_checkpoint_at_requested_target_boundary is True
    assert result.resume_binding is not None
    assert result.solve_attempt_count == 1
    assert len(result.target_cutback_history) == 1
    exhausted = result.target_cutback_history[0]
    assert exhausted.outcome == "bounds_exhausted"
    assert exhausted.outcome_reason_code == (
        "direct_control_target_cutback_exhausted"
    )
    assert exhausted.cutback_target_control_coordinate is None
    assert exhausted.rejected_result_hash == result.steps[-1].result_hash
    assert exhausted.parent_state_immutable is True
    assert parent.to_dict() == parent_payload


def test_target_cutback_unit_minima_and_contract_hash_are_bound() -> None:
    base = StatefulCorotationalFrame3DDisplacementControlConfig()
    assert direct_control_module._minimum_control_increment(base, 6) == (
        base.minimum_control_increment_m
    )
    assert direct_control_module._minimum_control_increment(base, 11) == (
        base.minimum_control_increment_rad
    )
    variants = (
        replace(base, adaptive_target_cutback_enabled=False),
        replace(base, target_cutback_ratio=0.4),
        replace(base, maximum_target_cutback_depth=7),
        replace(base, maximum_target_cutback_substeps=128),
        replace(base, maximum_path_solve_attempts=2048),
        replace(base, minimum_control_increment_m=2.0e-9),
        replace(base, minimum_control_increment_rad=2.0e-9),
    )
    assert all(row.contract_hash != base.contract_hash for row in variants)
    manifest = base.to_manifest()["target_cutback"]
    assert manifest["supported"] is True
    assert manifest["retry_reason_codes"] == [
        "direct_control_maximum_iterations_exceeded",
        "direct_control_line_search_failed",
    ]


def test_mixed_inadmissible_line_search_is_not_cutback_retryable() -> None:
    model = _cantilever_model(model_id="frame3d-direct-mixed-inadmissible")
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        maximum_iterations=1,
    )
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.frame_config,
    )
    blocked = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        parent,
        control_global_dof=6,
        target_control_coordinate=0.004,
        config=config,
    )
    assert direct_control_module._target_failure_is_retryable(blocked) is True
    mixed_metrics = {
        **dict(blocked.solution.metrics),
        "inadmissible_trial_count": 1,
        "first_inadmissibility_reason_code": "member_trial_inadmissible",
    }
    mixed = replace(
        blocked,
        solution=replace(
            blocked.solution,
            reason_code="direct_control_line_search_failed",
            metrics=mixed_metrics,
        ),
    )
    assert direct_control_module._target_failure_is_retryable(mixed) is False


def test_exact_resume_binding_rejects_tamper_contract_change_and_reversal() -> None:
    model = _cantilever_model(model_id="frame3d-direct-bound-resume")
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    prefix = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.001, 0.002),
        control_global_dof=6,
        config=config,
    )

    unbound = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.003,),
        control_global_dof=6,
        config=config,
        resume_from=prefix.final_checkpoint,
    )
    assert unbound.status == "ready"
    assert unbound.resume_mode == "unbound_equilibrium_checkpoint_restart"
    assert unbound.resume_contract_verified is False

    tampered = replace(
        prefix.resume_binding,
        accepted_control_target=0.0015,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_resume_binding_hash_mismatch",
    ):
        validate_stateful_corotational_frame3d_displacement_control_resume_binding(
            tampered,
            checkpoint=prefix.final_checkpoint,
            model=model,
            config=config,
            control_global_dof=6,
        )

    changed_config = StatefulCorotationalFrame3DDisplacementControlConfig(
        control_relative_tolerance=1.0e-9,
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_resume_binding_contract_mismatch",
    ):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.003,),
            control_global_dof=6,
            config=changed_config,
            resume_from=prefix.final_checkpoint,
            resume_binding=prefix.resume_binding,
        )

    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_resume_direction_mismatch",
    ):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.001,),
            control_global_dof=6,
            config=config,
            resume_from=prefix.final_checkpoint,
            resume_binding=prefix.resume_binding,
        )


def test_resume_binding_objects_reject_numeric_type_aliases() -> None:
    model = _cantilever_model(model_id="frame3d-direct-binding-number-domain")
    monotonic = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.001,),
        control_global_dof=6,
    )
    invalid_target = replace(
        monotonic.resume_binding,
        accepted_control_target=False,
    )
    invalid_target_payload = direct_control_module._resume_binding_payload(
        invalid_target,
        include_hash=False,
    )
    invalid_target = replace(
        invalid_target,
        binding_hash=direct_control_module.canonical_hash(invalid_target_payload),
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_resume_binding_invalid",
    ):
        invalid_target.to_dict()

    cyclic_config = StatefulCorotationalFrame3DDisplacementControlConfig(
        allow_direction_reversal=True,
        maximum_direction_reversals=1,
    )
    cyclic = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (0.001,),
        control_global_dof=6,
        config=cyclic_config,
    )
    assert isinstance(
        cyclic.resume_binding,
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
    )
    invalid_direction = replace(
        cyclic.resume_binding,
        last_completed_leg_direction_sign=True,
    )
    invalid_direction_payload = direct_control_module._cyclic_resume_binding_payload(
        invalid_direction,
        include_hash=False,
    )
    invalid_direction = replace(
        invalid_direction,
        binding_hash=direct_control_module.canonical_hash(
            invalid_direction_payload
        ),
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_cyclic_resume_binding_invalid",
    ):
        invalid_direction.to_dict()

    invalid_step_type = replace(
        cyclic.resume_binding,
        accepted_step_index="1",
    )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_cyclic_resume_binding_invalid",
    ):
        invalid_step_type.to_dict()


def test_rotation_control_uses_equivalent_6dof_scaling_and_tangent() -> None:
    model = _cantilever_model(
        reference_dof=11,
        reference_value=20.0,
        model_id="frame3d-direct-rotation-control",
    )
    frame_config = StatefulCorotationalFrame3DSparseConfig()
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        frame_config=frame_config
    )
    initial = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=frame_config,
    )
    problem = StatefulCorotationalFrame3DDisplacementControlStepProblem(
        model=model,
        accepted_checkpoint=initial,
        control_global_dof=11,
        target_control_coordinate=5.0e-4,
        config=config,
    )
    check = finite_difference_stateful_corotational_frame3d_displacement_control_check(
        problem,
        coordinate_step_m=1.0e-8,
    )
    analytic_scale = max(abs(value) for value in check["analytic"])

    assert problem.control_unit == "rad"
    assert problem.load_factor_coordinate_scale_m == pytest.approx(2.0)
    assert check["parent_state_immutable"] is True
    assert check["maximum_absolute_error_kn_per_m"] / analytic_scale <= 1.0e-6

    result = run_stateful_corotational_frame3d_displacement_control_path(
        model,
        (5.0e-4, 1.0e-3),
        control_global_dof=11,
        config=config,
    )
    assert result.status == "ready"
    assert result.control_unit == "rad"
    assert result.final_checkpoint.displacement[11] == pytest.approx(1.0e-3)
    assert result.steps[-1].solution.load_factor == pytest.approx(0.4)
    assert (
        result.steps[-1].solution.metrics["equation_scaling_hash"]
        == check["scaling_hash"]
    )


def test_failed_step_keeps_parent_and_missing_metrics_unavailable() -> None:
    model = _cantilever_model(
        restrained_dofs=(0, 1, 2),
        model_id="frame3d-direct-control-underconstrained",
    )
    frame_config = StatefulCorotationalFrame3DSparseConfig()
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        frame_config=frame_config
    )
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=frame_config,
    )
    parent_hash = parent.checkpoint_hash
    state_hash = parent.material_states[0].state_hash

    result = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        parent,
        control_global_dof=6,
        target_control_coordinate=0.004,
        config=config,
    )

    assert result.status == "blocked"
    assert result.committed is False
    assert result.accepted_checkpoint is None
    assert result.solution.reason_code == "direct_control_sparse_factorization_failed"
    assert result.solution.metrics["contract_pass"] is False
    assert result.solution.metrics["raw_translation_increment_inf_norm_m"] is None
    assert result.solution.metrics["raw_rotation_increment_inf_norm_rad"] is None
    assert result.solution.metrics["scaled_increment"] is None
    assert result.solution.metrics["scaled_condition_number_1"] is None
    assert parent.checkpoint_hash == parent_hash
    assert parent.material_states[0].state_hash == state_hash
    validate_stateful_corotational_frame3d_sparse_checkpoint(
        parent,
        model=model,
        config=frame_config,
    )


def test_later_factorization_failure_does_not_leak_prior_terminal_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _cantilever_model(model_id="frame3d-direct-control-late-factor-fail")
    config = StatefulCorotationalFrame3DDisplacementControlConfig()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config.frame_config,
    )
    original = direct_control_module._solve_sparse_tangent
    call_count = 0

    def fail_second_factorization(*args: object, **kwargs: object):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise np.linalg.LinAlgError("forced second-iteration failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        direct_control_module,
        "_solve_sparse_tangent",
        fail_second_factorization,
    )
    result = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        parent,
        control_global_dof=6,
        target_control_coordinate=0.004,
        config=config,
    )

    assert call_count == 2
    assert result.status == "blocked"
    assert result.solution.reason_code == "direct_control_sparse_factorization_failed"
    assert len(result.solution.factorization_diagnostics) == 1
    assert result.solution.metrics["raw_translation_increment_inf_norm_m"] is None
    assert result.solution.metrics["raw_rotation_increment_inf_norm_rad"] is None
    assert result.solution.metrics["scaled_increment"] is None
    assert result.solution.metrics["load_factor_increment"] is None
    assert result.solution.metrics["scaled_condition_number_1"] is None


def test_maximum_iteration_block_rolls_back_nonlinear_trial() -> None:
    model = _cantilever_model(model_id="frame3d-direct-control-rollback")
    frame_config = StatefulCorotationalFrame3DSparseConfig()
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        frame_config=frame_config,
        maximum_iterations=1,
    )
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=frame_config,
    )
    parent_dict = parent.to_dict()

    result = solve_stateful_corotational_frame3d_displacement_control_step(
        model,
        parent,
        control_global_dof=6,
        target_control_coordinate=0.004,
        config=config,
    )

    assert result.status == "blocked"
    assert result.committed is False
    assert result.accepted_checkpoint is None
    assert result.solution.reason_code == "direct_control_maximum_iterations_exceeded"
    assert parent.to_dict() == parent_dict
    parent_state = parent.material_states[0]
    assert isinstance(parent_state, UniaxialPlasticityState)
    assert parent_state.accumulated_plastic_strain == 0.0


def test_invalid_control_contracts_and_zero_reference_load_fail_closed() -> None:
    model = _cantilever_model()
    frame_config = StatefulCorotationalFrame3DSparseConfig()
    config = StatefulCorotationalFrame3DDisplacementControlConfig(
        frame_config=frame_config
    )
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=frame_config,
    )
    with pytest.raises(ValueError, match="free Frame3D DOF"):
        solve_stateful_corotational_frame3d_displacement_control_step(
            model,
            parent,
            control_global_dof=0,
            target_control_coordinate=0.001,
            config=config,
        )
    with pytest.raises(ValueError, match="strictly in one direction"):
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (0.001, 0.0005),
            control_global_dof=6,
            config=config,
        )
    with pytest.raises(ValueError, match="differ from the parent"):
        solve_stateful_corotational_frame3d_displacement_control_step(
            model,
            parent,
            control_global_dof=6,
            target_control_coordinate=0.0,
            config=config,
        )
    with pytest.raises(
        StatefulCorotationalFrame3DDisplacementControlError,
        match="direct_control_target_within_tolerance",
    ) as tiny_target_error:
        run_stateful_corotational_frame3d_displacement_control_path(
            model,
            (1.0e-13,),
            control_global_dof=6,
            config=config,
        )
    assert (
        tiny_target_error.value.reason_code
        == "direct_control_target_within_tolerance"
    )

    zero_load = _cantilever_model(
        reference_dof=0,
        reference_value=1.0,
        model_id="frame3d-direct-control-zero-reference",
    )
    zero_parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        zero_load,
        config=frame_config,
    )
    with pytest.raises(StatefulCorotationalFrame3DDisplacementControlError) as error:
        solve_stateful_corotational_frame3d_displacement_control_step(
            zero_load,
            zero_parent,
            control_global_dof=6,
            target_control_coordinate=0.001,
            config=config,
        )
    assert error.value.reason_code == "direct_control_reference_load_missing"


def test_config_is_bounded_and_public_assembly_namespace_exports_candidate() -> None:
    assert (
        assembly_namespace.STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE
        == STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE
    )
    assert callable(
        assembly_namespace.run_stateful_corotational_frame3d_displacement_control_path
    )
    default = StatefulCorotationalFrame3DDisplacementControlConfig()
    assert default.maximum_iterations == default.frame_config.maximum_iterations
    with pytest.raises(ValueError, match="cannot exceed frame_config"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            frame_config=StatefulCorotationalFrame3DSparseConfig(
                maximum_iterations=2
            ),
            maximum_iterations=3,
        )
    with pytest.raises(ValueError, match="must start with 1"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            line_search_alphas=(0.5,)
        )
    with pytest.raises(ValueError, match="strictly decreasing"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            line_search_alphas=(1.0, 0.5, 0.5)
        )
    with pytest.raises(ValueError, match="maximum_path_targets"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            maximum_path_targets=0
        )
    with pytest.raises(ValueError, match="load_factor_increment_tolerance"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            load_factor_increment_tolerance=0.0
        )
    with pytest.raises(ValueError, match="adaptive_target_cutback_enabled"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            adaptive_target_cutback_enabled=1,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="target_cutback_ratio"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            target_cutback_ratio=1.0
        )
    with pytest.raises(ValueError, match="maximum_target_cutback_depth"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            maximum_target_cutback_depth=-1
        )
    with pytest.raises(ValueError, match="maximum_target_cutback_substeps"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            maximum_target_cutback_substeps=0
        )
    with pytest.raises(ValueError, match="maximum_path_solve_attempts"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            maximum_path_solve_attempts=0
        )
    with pytest.raises(ValueError, match="minimum_control_increment_m"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            minimum_control_increment_m=0.0
        )
    with pytest.raises(ValueError, match="minimum_control_increment_rad"):
        StatefulCorotationalFrame3DDisplacementControlConfig(
            minimum_control_increment_rad=0.0
        )
