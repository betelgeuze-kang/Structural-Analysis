"""Focused tests for native sparse, stateful corotational 3D frames."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

import structural_analysis.assembly.stateful_corotational_frame3d_sparse as sparse_module
from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CHECKPOINT_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    assemble_stateful_corotational_frame3d_sparse,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    solve_stateful_corotational_frame3d_sparse_load_path,
    stateful_corotational_frame3d_equation_scaling_6dof,
    stateful_corotational_frame3d_dense_sparse_parity_receipt,
    stateful_corotational_frame3d_member_response,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityState,
)
from structural_analysis.materials.composite_section import (
    ParallelCompositeSectionState,
    ParallelSteelConcreteSectionMaterial,
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


def _material(*, material_id: str = "steel") -> BilinearCombinedHardeningSteel:
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id=material_id,
    )


def _axial_model(
    *,
    restrained_dofs: tuple[int, ...] = tuple(range(6)),
    model_id: str = "stateful-axial-cantilever",
) -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 12
    load[6] = 6_000.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, _section()),),
        restrained_dofs=restrained_dofs,
        reference_load_kn=tuple(load),
        model_id=model_id,
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, (_material(),))


def _rehash_checkpoint(candidate):
    payload = candidate.to_dict()
    payload.pop("checkpoint_hash")
    return replace(candidate, checkpoint_hash=canonical_hash(payload))


@pytest.mark.parametrize("value", (False, "0", 0, 2**53 + 1))
def test_checkpoint_displacement_rejects_coercive_binary64_sources(
    value: object,
) -> None:
    model = _axial_model(model_id="checkpoint-displacement-source-domain")
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    displacement = list(checkpoint.displacement)
    displacement[6] = value
    forged = _rehash_checkpoint(
        replace(checkpoint, displacement=tuple(displacement))
    )

    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            forged,
            model=model,
            config=config,
            require_equilibrium=False,
        )
    assert error.value.reason_code in {
        "checkpoint_displacement_invalid",
        "checkpoint_displacement_numeric_domain_mismatch",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (("load_factor", 1), ("residual_inf_norm_kn", 0)),
)
def test_checkpoint_scalar_identity_requires_typed_binary64_float(
    field: str,
    value: int,
) -> None:
    model = _axial_model(model_id="checkpoint-scalar-number-domain")
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    forged = _rehash_checkpoint(replace(checkpoint, **{field: value}))

    with pytest.raises(StatefulCorotationalFrame3DSparseError, match="scalar metadata"):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            forged,
            model=model,
            config=config,
            require_equilibrium=False,
        )


def test_checkpoint_material_state_must_replay_at_stored_displacement() -> None:
    model = _axial_model(model_id="checkpoint-material-state-replay")
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    displacement = list(checkpoint.displacement)
    displacement[6] = 0.01
    forged = _rehash_checkpoint(
        replace(
            checkpoint,
            step_index=1,
            displacement=tuple(displacement),
            converged_iterations=1,
            parent_checkpoint_hash=checkpoint.checkpoint_hash,
        )
    )

    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            forged,
            model=model,
            config=config,
            require_equilibrium=False,
        )
    assert error.value.reason_code == "checkpoint_material_state_replay_invalid"


def test_non_genesis_checkpoint_rejects_zero_parent_hash() -> None:
    model = _axial_model(model_id="checkpoint-child-lineage")
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    forged = _rehash_checkpoint(
        replace(
            checkpoint,
            step_index=1,
            converged_iterations=1,
            parent_checkpoint_hash="sha256:" + "0" * 64,
        )
    )

    with pytest.raises(StatefulCorotationalFrame3DSparseError, match="scalar metadata"):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            forged,
            model=model,
            config=config,
            require_equilibrium=False,
        )


def test_reaction_only_load_step_accepts_zero_newton_update_checkpoint() -> None:
    load = [0.0] * 12
    load[0] = 100.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, _section()),),
        restrained_dofs=tuple(range(6)) + tuple(range(7, 12)),
        reference_load_kn=tuple(load),
        model_id="reaction-only-zero-newton-checkpoint",
    )
    model = StatefulCorotationalFrame3DSparseModel(elastic, (_material(),))
    config = StatefulCorotationalFrame3DSparseConfig()
    genesis = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )

    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
    )

    assert result.final_checkpoint.step_index == 1
    assert result.final_checkpoint.converged_iterations == 0
    assert result.final_checkpoint.parent_checkpoint_hash == genesis.checkpoint_hash


def _two_member_spatial_model() -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 18
    load[12] = 50.0
    load[13] = -25.0
    section = _section()
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=(
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (3.0, 1.0, 1.0),
        ),
        members=(
            CorotationalFrame3DMember("member-1", 0, 1, section),
            CorotationalFrame3DMember(
                "member-2",
                1,
                2,
                section,
                local_axis_roll_deg=17.0,
            ),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="stateful-spatial-two-member",
    )
    return StatefulCorotationalFrame3DSparseModel(
        elastic,
        (_material(material_id="steel-1"), _material(material_id="steel-2")),
    )


def test_native_coo_csr_matches_independent_dense_scatter() -> None:
    model = _two_member_spatial_model()
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    displacement = np.zeros(model.total_dofs, dtype=np.float64)
    displacement[6:18] = np.asarray(
        [
            2.0e-4,
            -1.0e-4,
            1.5e-4,
            2.0e-5,
            -3.0e-5,
            1.0e-5,
            5.0e-4,
            -3.0e-4,
            2.0e-4,
            -1.0e-5,
            4.0e-5,
            -2.0e-5,
        ]
    )
    assembly = assemble_stateful_corotational_frame3d_sparse(
        model,
        checkpoint,
        target_load_factor=0.4,
        trial_displacement=displacement,
    )
    receipt = stateful_corotational_frame3d_dense_sparse_parity_receipt(
        model,
        checkpoint,
        target_load_factor=0.4,
        trial_displacement=displacement,
    )

    assert receipt.to_dict()["contract_pass"] is True
    assert all(receipt.checks.values())
    assert max(receipt.metrics.values()) <= 1.0e-10
    assert assembly.raw_coo_entry_count == 180
    assert 0 < assembly.csr_nnz < assembly.raw_coo_entry_count
    assert assembly.tangent_free_csr.has_canonical_format
    assert assembly.tangent_free_csr.has_sorted_indices
    assert assembly.csr_pattern_hash.startswith("sha256:")
    assert assembly.csr_numeric_hash.startswith("sha256:")
    assert assembly.displacement.flags.writeable is False
    assert assembly.csr_values_kn_per_m.flags.writeable is False
    repeated = assemble_stateful_corotational_frame3d_sparse(
        model,
        checkpoint,
        target_load_factor=0.4,
        trial_displacement=displacement,
    )
    assert repeated.assembly_hash == assembly.assembly_hash


def test_axial_return_mapping_correction_has_same_parent_consistent_tangent() -> None:
    model = _axial_model()
    member = model.elastic_model.members[0]
    material = model.axial_materials[0]
    coordinates = np.asarray(model.elastic_model.node_coordinates_m)
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6] = 0.0035
    parent = material.initial_state()
    center = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        axial_material=material,
        committed_state=parent,
    )
    epsilon = 1.0e-5
    plus = displacement.copy()
    minus = displacement.copy()
    plus[6] += epsilon
    minus[6] -= epsilon
    forward = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=plus,
        axial_material=material,
        committed_state=parent,
    )
    backward = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=minus,
        axial_material=material,
        committed_state=parent,
    )
    finite_difference = (
        forward.internal_force_global - backward.internal_force_global
    ) / (2.0 * epsilon)
    relative_error = abs(
        finite_difference[6] - center.consistent_tangent_global[6, 6]
    ) / max(abs(finite_difference[6]), 1.0)

    assert center.axial_material_response.yielded is True
    assert center.axial_material_response.committed_state_hash == parent.state_hash
    assert forward.axial_material_response.committed_state_hash == parent.state_hash
    assert backward.axial_material_response.committed_state_hash == parent.state_hash
    assert center.axial_force_kn == pytest.approx(6_000.0, rel=1.0e-12)
    assert center.axial_tangent_kn_per_m == pytest.approx(1_000_000.0)
    assert relative_error <= 5.0e-7
    np.testing.assert_allclose(
        center.consistent_tangent_global,
        center.consistent_tangent_global.T,
        atol=1.0e-12,
        rtol=0.0,
    )


def test_cyclic_material_commit_and_exact_checkpoint_resume() -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig()
    path = (0.5, 1.0, -1.0, 0.25)
    one_shot = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        path,
        config=config,
    )
    prefix = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        path[:2],
        config=config,
    )
    resumed = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        path[2:],
        config=config,
        resume_from=prefix.final_checkpoint,
    )

    assert one_shot.final_checkpoint == resumed.final_checkpoint
    assert one_shot.final_checkpoint.checkpoint_hash == (
        resumed.final_checkpoint.checkpoint_hash
    )
    assert one_shot.final_checkpoint.material_states == (
        resumed.final_checkpoint.material_states
    )
    state = one_shot.final_checkpoint.material_states[0]
    assert state.accumulated_plastic_strain > 0.0
    assert state.dissipated_energy_density_mj_per_m3 > 0.0
    assert one_shot.final_checkpoint.displacement[6] == pytest.approx(0.00075)
    assert dict(one_shot.steps[-1].reactions)[0] == pytest.approx(
        -1_500.0,
        abs=2.0e-4,
    )
    assert all(
        diagnostic.contract_pass
        for step in one_shot.steps
        for diagnostic in step.factorization_diagnostics
    )
    assert one_shot.exact_checkpoint_resume_supported is True
    assert one_shot.material_commit_rollback_supported is True
    assert one_shot.regularization_used is False
    assert one_shot.fallback_used is False
    assert one_shot.contract_pass is True
    assert one_shot.maximum_scaled_residual_inf_norm <= (
        config.residual_relative_tolerance
        + config.residual_absolute_tolerance_kn
        / one_shot.equation_scaling.reference_force_kn
    )
    assert one_shot.maximum_scaled_increment_inf_norm <= (
        config.increment_relative_tolerance
        + config.increment_absolute_tolerance_m
        / one_shot.equation_scaling.characteristic_length_m
    )
    assert all(step.residual_gate_passed for step in one_shot.steps)
    assert all(step.increment_gate_passed for step in one_shot.steps)
    assert all(step.line_search_valid for step in one_shot.steps)
    assert all(step.final_reassembled_equilibrium_passed for step in one_shot.steps)
    assert all(step.parent_state_immutable for step in one_shot.steps)
    assert all(step.sparse_diagnostic_passed for step in one_shot.steps)


def test_residual_only_cannot_commit_and_6dof_scaling_is_source_bound() -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig(
        residual_relative_tolerance=1.0e3,
        residual_absolute_tolerance_kn=1.0e3,
        increment_relative_tolerance=1.0e-12,
        increment_absolute_tolerance_m=1.0e-15,
    )
    scaling = stateful_corotational_frame3d_equation_scaling_6dof(
        model,
        config=config,
    )
    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.5,),
        config=config,
    )
    step = result.steps[0]
    first = step.convergence_history[0]

    assert scaling.characteristic_length_m == pytest.approx(2.0)
    assert scaling.reference_force_kn == pytest.approx(6_000.0)
    assert scaling.residual_rotation_scale_kn_m == pytest.approx(12_000.0)
    assert scaling.scaling_hash.startswith("sha256:")
    assert result.equation_scaling == scaling
    assert first["residual_gate_passed"] is True
    assert first["increment_gate_passed"] is False
    assert step.checkpoint.converged_iterations >= 1
    assert step.line_search_required is True
    assert step.selected_line_search_alpha is not None
    assert step.line_search_valid is True
    assert step.scaled_residual_inf_norm <= step.scaled_residual_tolerance
    assert step.scaled_increment_inf_norm <= step.scaled_increment_tolerance
    assert step.scaled_condition_number_1 > 0.0
    assert step.equation_scaling_hash == scaling.scaling_hash
    attempts = step.line_search_history[0]["attempts"]
    with pytest.raises(TypeError):
        attempts[0]["accepted"] = False
    assert result.to_dict()["steps"][0]["line_search_history"][0]["attempts"]

    tampered = replace(scaling, characteristic_length_m=4.0)
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="derived scales are inconsistent",
    ):
        tampered.to_dict()


def test_3d_convergence_config_rejects_invalid_increment_and_line_search() -> None:
    with pytest.raises(ValueError, match="increment_relative_tolerance"):
        StatefulCorotationalFrame3DSparseConfig(
            increment_relative_tolerance=0.0
        )
    with pytest.raises(ValueError, match="must start with 1"):
        StatefulCorotationalFrame3DSparseConfig(line_search_alphas=(0.5,))
    with pytest.raises(ValueError, match="strictly decreasing"):
        StatefulCorotationalFrame3DSparseConfig(
            line_search_alphas=(1.0, 0.5, 0.5)
        )
    with pytest.raises(ValueError, match="adaptive_load_cutback_enabled"):
        StatefulCorotationalFrame3DSparseConfig(
            adaptive_load_cutback_enabled=1,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="load_cutback_ratio"):
        StatefulCorotationalFrame3DSparseConfig(load_cutback_ratio=1.0)
    with pytest.raises(ValueError, match="maximum_load_cutback_depth"):
        StatefulCorotationalFrame3DSparseConfig(maximum_load_cutback_depth=-1)
    with pytest.raises(ValueError, match="maximum_load_cutback_substeps"):
        StatefulCorotationalFrame3DSparseConfig(maximum_load_cutback_substeps=0)
    with pytest.raises(ValueError, match="minimum_load_increment_factor"):
        StatefulCorotationalFrame3DSparseConfig(
            minimum_load_increment_factor=0.0
        )


def test_adaptive_cutback_reaches_requested_target_with_exact_resume() -> None:
    model = _two_member_spatial_model()
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_iterations=30,
        maximum_load_cutback_depth=8,
    )

    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
    )

    assert result.schema_version == "stateful-corotational-frame3d-sparse-result.v2"
    assert result.requested_load_factors == (1.0,)
    assert result.adaptive_load_cutback_supported is True
    assert result.adaptive_load_cutback_used is True
    assert result.load_cutback_history
    assert len(result.steps) > len(result.requested_load_factors)
    assert result.final_checkpoint.load_factor == 1.0
    assert all(row.parent_state_immutable for row in result.load_cutback_history)
    assert {
        row.reason_code for row in result.load_cutback_history
    } <= {"maximum_iterations_exceeded", "line_search_failed"}
    assert [row.attempt_index for row in result.load_cutback_history] == list(
        range(len(result.load_cutback_history))
    )
    assert all(
        step.checkpoint.parent_checkpoint_hash
        == result.checkpoints[index].checkpoint_hash
        for index, step in enumerate(result.steps)
    )
    restart = result.checkpoints[1]
    resumed = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
        resume_from=restart,
    )
    assert resumed.checkpoints == result.checkpoints[1:]
    assert resumed.steps == result.steps[1:]
    assert resumed.final_checkpoint == result.final_checkpoint
    serialized = result.to_dict()
    assert serialized["adaptive_load_cutback_used"] is True
    assert serialized["load_cutback_history"]


def test_failed_trial_does_not_mutate_accepted_material_parent() -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=1)
    prefix = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.5,),
        config=config,
    )
    accepted = prefix.final_checkpoint
    accepted_hash = accepted.checkpoint_hash
    accepted_state_hash = accepted.material_states[0].state_hash

    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (1.0,),
            config=config,
            resume_from=accepted,
        )
    assert error.value.reason_code == "adaptive_load_cutback_exhausted"

    assert accepted.checkpoint_hash == accepted_hash
    assert accepted.material_states[0].state_hash == accepted_state_hash
    validate_stateful_corotational_frame3d_sparse_checkpoint(
        accepted,
        model=model,
        config=config,
    )


def test_material_inadmissibility_is_not_reclassified_as_retryable_cutback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model(model_id="stateful-material-inadmissibility")
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_iterations=3,
        maximum_load_cutback_depth=8,
    )
    original_integrate = BilinearCombinedHardeningSteel.integrate

    def bounded_integrate(
        self: BilinearCombinedHardeningSteel,
        total_strain: float,
        committed_state: UniaxialPlasticityState,
    ):
        if total_strain > 1.4e-3:
            raise ValueError("fault-injected bounded material path")
        return original_integrate(self, total_strain, committed_state)

    monkeypatch.setattr(BilinearCombinedHardeningSteel, "integrate", bounded_integrate)
    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (1.0,),
            config=config,
        )

    assert error.value.reason_code == "member_trial_inadmissible"
    assert error.value.retryable_convergence_failure is False
    disguised = StatefulCorotationalFrame3DSparseError(
        "mixed material/convergence failure",
        reason_code="line_search_failed",
    )
    classified = StatefulCorotationalFrame3DSparseError(
        "pure convergence failure",
        reason_code="line_search_failed",
        retryable_convergence_failure=True,
    )
    assert sparse_module._load_cutback_failure_is_retryable(disguised) is False
    assert sparse_module._load_cutback_failure_is_retryable(classified) is True


def test_material_response_must_bind_the_actual_accepted_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model(model_id="stateful-material-parent-binding")
    member = model.elastic_model.members[0]
    material = model.axial_materials[0]
    accepted_parent = material.initial_state()
    wrong_parent = UniaxialPlasticityState(
        plastic_strain=1.0e-5,
        backstress_mpa=material.kinematic_hardening_modulus_mpa * 1.0e-5,
        accumulated_plastic_strain=1.0e-5,
        dissipated_energy_density_mj_per_m3=(
            material.yield_stress_mpa * 1.0e-5
        ),
    )
    original_integrate = BilinearCombinedHardeningSteel.integrate

    def wrong_parent_integrate(
        self: BilinearCombinedHardeningSteel,
        total_strain: float,
        committed_state: UniaxialPlasticityState,
    ):
        del committed_state
        return original_integrate(self, total_strain, wrong_parent)

    monkeypatch.setattr(
        BilinearCombinedHardeningSteel,
        "integrate",
        wrong_parent_integrate,
    )
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6] = 1.0e-4
    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        stateful_corotational_frame3d_member_response(
            member=member,
            node_coordinates_m=model.elastic_model.node_coordinates_m,
            element_displacements=displacement,
            axial_material=material,
            committed_state=accepted_parent,
        )

    assert error.value.reason_code == "material_response_parent_state_mismatch"


def test_sparse_factorization_failure_and_invalid_history_fail_closed() -> None:
    model = _axial_model(restrained_dofs=(0, 1, 2), model_id="underconstrained")
    config = StatefulCorotationalFrame3DSparseConfig()
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="factorization failed without fallback",
    ):
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (1.0,),
            config=config,
        )

    stable = _axial_model()
    with pytest.raises(ValueError, match="adjacent load factors"):
        solve_stateful_corotational_frame3d_sparse_load_path(
            stable,
            (0.5, 0.5),
            config=config,
        )
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        stable,
        config=config,
    )
    invalid = list(checkpoint.displacement)
    invalid[0] = 1.0e-4
    with pytest.raises(ValueError, match="restrained displacement"):
        assemble_stateful_corotational_frame3d_sparse(
            stable,
            checkpoint,
            target_load_factor=0.5,
            trial_displacement=invalid,
        )


def test_checkpoint_schema_tamper_and_cross_model_binding() -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig()
    solution = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.5, 1.0),
        config=config,
    )
    checkpoint = solution.final_checkpoint
    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(checkpoint.to_dict())
    assert (
        checkpoint.schema_version
        == STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CHECKPOINT_SCHEMA_VERSION
    )
    assert checkpoint.profile == STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE

    values = list(checkpoint.displacement)
    values[6] += 1.0e-4
    tampered = replace(checkpoint, displacement=tuple(values))
    with pytest.raises(StatefulCorotationalFrame3DSparseError, match="hash mismatch"):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            tampered,
            model=model,
            config=config,
        )
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="contract binding",
    ):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            checkpoint,
            model=_axial_model(model_id="different-model"),
            config=config,
        )


def test_checkpoint_runtime_rejects_rehashed_invalid_contract_and_lineage() -> None:
    model = _axial_model(model_id="checkpoint-runtime-contract")
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=1)
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )

    def rehash(
        candidate: sparse_module.StatefulCorotationalFrame3DSparseCheckpoint,
    ) -> sparse_module.StatefulCorotationalFrame3DSparseCheckpoint:
        payload = candidate.to_dict()
        payload.pop("checkpoint_hash")
        return replace(candidate, checkpoint_hash=canonical_hash(payload))

    invalid_contract = rehash(
        replace(checkpoint, solver_contract_hash="not-a-canonical-hash")
    )
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="contract binding",
    ):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            invalid_contract,
            model=model,
            config=None,
            require_equilibrium=False,
        )

    detached_child = rehash(replace(checkpoint, step_index=1))
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="scalar metadata",
    ):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            detached_child,
            model=model,
            config=config,
            require_equilibrium=False,
        )

    forged_genesis = rehash(
        replace(
            checkpoint,
            material_states=(
                UniaxialPlasticityState(
                    plastic_strain=1.0e-5,
                    backstress_mpa=(
                        model.axial_materials[0].kinematic_hardening_modulus_mpa
                        * 1.0e-5
                    ),
                    accumulated_plastic_strain=1.0e-5,
                    dissipated_energy_density_mj_per_m3=(
                        model.axial_materials[0].yield_stress_mpa * 1.0e-5
                    ),
                ),
            ),
        )
    )
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="genesis state",
    ):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            forged_genesis,
            model=model,
            config=config,
            require_equilibrium=False,
        )

    unreachable_state = UniaxialPlasticityState(
        plastic_strain=0.0,
        backstress_mpa=249.0,
        accumulated_plastic_strain=0.0,
        dissipated_energy_density_mj_per_m3=0.0,
    )
    rehashed_unreachable_child = rehash(
        replace(
            checkpoint,
            step_index=1,
            material_states=(unreachable_state,),
            parent_checkpoint_hash=checkpoint.checkpoint_hash,
        )
    )
    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            rehashed_unreachable_child,
            model=model,
            config=config,
            require_equilibrium=False,
        )
    assert error.value.reason_code == "material_state_admissibility_failed"

    impossible_iterations = rehash(
        replace(
            checkpoint,
            step_index=1,
            converged_iterations=2,
            parent_checkpoint_hash=checkpoint.checkpoint_hash,
        )
    )
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="scalar metadata",
    ):
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            impossible_iterations,
            model=model,
            config=config,
            require_equilibrium=False,
        )


def test_checkpoint_rejects_rehashed_unreachable_nested_steel_state() -> None:
    composite = ParallelSteelConcreteSectionMaterial(steel=_material())
    effective_modulus_mpa = (
        composite.steel_area_fraction * composite.steel.elastic_modulus_mpa
        + composite.concrete_area_fraction
        * composite.concrete.elastic_modulus_mpa
    )
    section = TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.02,
            e_n_per_m2=effective_modulus_mpa * 1000.0,
            g_n_per_m2=8.0e7,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, section),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=(0.0,) * 6 + (1.0,) + (0.0,) * 5,
        model_id="nested-steel-checkpoint",
    )
    model = StatefulCorotationalFrame3DSparseModel(elastic, (composite,))
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    parent_state = checkpoint.material_states[0]
    assert type(parent_state) is ParallelCompositeSectionState
    unreachable = replace(
        parent_state,
        steel_state=UniaxialPlasticityState(backstress_mpa=249.0),
    )
    forged = replace(
        checkpoint,
        step_index=1,
        parent_checkpoint_hash=checkpoint.checkpoint_hash,
        material_states=(unreachable,),
    )
    payload = forged.to_dict()
    payload.pop("checkpoint_hash")
    forged = replace(forged, checkpoint_hash=canonical_hash(payload))

    with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            forged,
            model=model,
            config=config,
            require_equilibrium=False,
        )
    assert error.value.reason_code == "material_state_admissibility_failed"


def test_material_modulus_must_match_elastic_geometric_reference() -> None:
    base = _axial_model().elastic_model
    inconsistent = BilinearCombinedHardeningSteel(elastic_modulus_mpa=190_000.0)
    with pytest.raises(ValueError, match="elastic modulus mismatch"):
        StatefulCorotationalFrame3DSparseModel(base, (inconsistent,))
