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
    STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION,
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    assemble_stateful_corotational_frame3d_sparse,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    solve_stateful_corotational_frame3d_sparse_load_path,
    stateful_corotational_frame3d_dense_sparse_parity_receipt,
    stateful_corotational_frame3d_member_response,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.materials.confined_concrete import (
    ConfinedConcreteMaterial,
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
    assert one_shot.adaptive_load_cutback_used is False
    assert one_shot.failed_attempt_rollback_exact is None
    assert all(row.outcome == "accepted" for row in one_shot.attempts)
    assert one_shot.regularization_used is False
    assert one_shot.fallback_used is False
    assert one_shot.contract_pass is True


def test_failed_trial_does_not_mutate_accepted_material_parent() -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_iterations=1,
        maximum_cutback_attempts_per_target=0,
    )
    prefix = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.5,),
        config=config,
    )
    accepted = prefix.final_checkpoint
    accepted_hash = accepted.checkpoint_hash
    accepted_state_hash = accepted.material_states[0].state_hash

    with pytest.raises(
        StatefulCorotationalFrame3DSparseError, match="did not converge"
    ) as failure:
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (1.0,),
            config=config,
            resume_from=accepted,
        )

    assert failure.value.code == "adaptive_load_cutback_exhausted"
    assert len(failure.value.attempts) == 1
    assert failure.value.attempts[0]["failure_code"] == (
        "maximum_iterations_exhausted"
    )
    assert failure.value.attempts[0]["rollback_exact"] is True
    assert accepted.checkpoint_hash == accepted_hash
    assert accepted.material_states[0].state_hash == accepted_state_hash
    validate_stateful_corotational_frame3d_sparse_checkpoint(
        accepted,
        model=model,
        config=config,
    )


def test_adaptive_load_cutback_retries_from_exact_accepted_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_cutback_attempts_per_target=4,
        load_cutback_factor=0.5,
        minimum_load_factor_increment=1.0e-8,
    )
    original = sparse_module._solve_step
    injected = False

    def _reject_first_requested_target(
        model_arg: object,
        config_arg: object,
        factor: float,
        parent: object,
    ):
        nonlocal injected
        if not injected and factor == 1.0:
            injected = True
            raise StatefulCorotationalFrame3DSparseError(
                "injected bounded nonconvergence",
                code="maximum_iterations_exhausted",
            )
        return original(model_arg, config_arg, factor, parent)

    monkeypatch.setattr(
        sparse_module,
        "_solve_step",
        _reject_first_requested_target,
    )
    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
    )

    assert result.schema_version == (
        STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION
    )
    assert result.requested_load_factors == (1.0,)
    assert [row.load_factor for row in result.steps] == [0.5, 1.0]
    assert [row.outcome for row in result.attempts] == [
        "rolled_back",
        "accepted",
        "accepted",
    ]
    rejected = result.attempts[0]
    assert rejected.parent_checkpoint_hash == result.start_checkpoint_hash
    assert rejected.failure_code == "maximum_iterations_exhausted"
    assert rejected.rollback_exact is True
    assert rejected.cutback_applied is True
    assert rejected.next_attempt_load_factor == pytest.approx(0.5)
    assert result.adaptive_load_cutback_used is True
    assert result.failed_attempt_rollback_exact is True
    assert result.final_checkpoint.load_factor == pytest.approx(1.0)
    assert result.contract_pass is True


def test_adaptive_load_cutback_exhaustion_preserves_parent_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model()
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_cutback_attempts_per_target=2,
        load_cutback_factor=0.5,
        minimum_load_factor_increment=1.0e-8,
    )
    accepted = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    accepted_payload = accepted.to_dict()

    def _always_fail(*_args: object, **_kwargs: object):
        raise StatefulCorotationalFrame3DSparseError(
            "injected line-search exhaustion",
            code="line_search_failed",
        )

    monkeypatch.setattr(sparse_module, "_solve_step", _always_fail)
    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="exhausted adaptive load cutback",
    ) as failure:
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (1.0,),
            config=config,
            resume_from=accepted,
        )

    assert failure.value.code == "adaptive_load_cutback_exhausted"
    assert [row["attempted_load_factor"] for row in failure.value.attempts] == [
        1.0,
        0.5,
        0.25,
    ]
    assert [row["cutback_applied"] for row in failure.value.attempts] == [
        True,
        True,
        False,
    ]
    assert all(
        row["failure_code"] == "line_search_failed"
        and row["rollback_exact"] is True
        for row in failure.value.attempts
    )
    assert accepted.to_dict() == accepted_payload


def test_adaptive_load_cutback_configuration_is_strict_and_hashed() -> None:
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_cutback_attempts_per_target=3,
        load_cutback_factor=0.25,
        minimum_load_factor_increment=1.0e-5,
    )
    manifest = config.to_manifest()["adaptive_load_cutback"]

    assert manifest["maximum_attempts_per_requested_target"] == 3
    assert manifest["reduction_factor"] == pytest.approx(0.25)
    assert manifest["minimum_load_factor_increment"] == pytest.approx(1.0e-5)
    assert manifest["unsupported_constitutive_path"] == (
        "fail_closed_without_cutback"
    )
    assert "maximum_iterations_exhausted" in manifest[
        "retryable_failure_codes"
    ]
    assert config.contract_hash.startswith("sha256:")

    with pytest.raises(ValueError, match="nonnegative integer"):
        StatefulCorotationalFrame3DSparseConfig(
            maximum_cutback_attempts_per_target=-1
        )
    with pytest.raises(ValueError, match=r"must be in \(0, 1\)"):
        StatefulCorotationalFrame3DSparseConfig(load_cutback_factor=1.0)
    with pytest.raises(ValueError, match="must be positive"):
        StatefulCorotationalFrame3DSparseConfig(
            minimum_load_factor_increment=0.0
        )


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


def test_material_modulus_must_match_elastic_geometric_reference() -> None:
    base = _axial_model().elastic_model
    inconsistent = BilinearCombinedHardeningSteel(elastic_modulus_mpa=190_000.0)
    with pytest.raises(ValueError, match="elastic modulus mismatch"):
        StatefulCorotationalFrame3DSparseModel(base, (inconsistent,))


def test_scaled_residual_and_increment_are_both_required_for_commit() -> None:
    model = _axial_model()
    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.01,),
        config=StatefulCorotationalFrame3DSparseConfig(
            residual_relative_tolerance=2.0e-2,
            increment_relative_tolerance=1.0e-12,
            increment_absolute_tolerance_m=1.0e-14,
        ),
    )

    first = result.steps[0].convergence_trace[0]
    assert first["residual_gate_pass"] is True
    assert first["increment_gate_pass"] is False
    assert result.steps[0].checkpoint.converged_iterations > 0
    assert all(result.steps[0].convergence_checks.values())
    assert result.maximum_scaled_residual_inf_norm >= 0.0
    assert result.maximum_scaled_increment_inf_norm >= 0.0
    assert result.equation_scaling_hashes == (
        result.steps[0].equation_scaling.scaling_hash,
    )


def test_invalid_full_trial_is_rejected_and_positive_backtrack_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _axial_model()
    original = sparse_module.assemble_stateful_corotational_frame3d_sparse
    injected = False

    def _reject_first_nonzero_trial(*args: object, **kwargs: object):
        nonlocal injected
        displacement = np.asarray(kwargs["trial_displacement"], dtype=np.float64)
        if not injected and np.linalg.norm(displacement, ord=np.inf) > 0.0:
            injected = True
            raise ValueError("invalid_geometry_trial")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        sparse_module,
        "assemble_stateful_corotational_frame3d_sparse",
        _reject_first_nonzero_trial,
    )
    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=StatefulCorotationalFrame3DSparseConfig(),
    )

    first_search = result.steps[0].convergence_trace[0]
    assert first_search["line_search_attempts"][0]["invalid_trial"] is True
    assert (
        first_search["line_search_attempts"][0]["invalid_trial_code"]
        == "invalid_geometry_or_material_trial"
    )
    assert first_search["accepted_line_search_alpha"] == pytest.approx(0.5)
    assert result.steps[0].accepted_line_search_alphas[0] == pytest.approx(0.5)
    assert all(result.steps[0].convergence_checks.values())


def test_rotation_equations_publish_separate_moment_scaling_evidence() -> None:
    load = [0.0] * 12
    load[11] = 10.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, _section()),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="stateful-moment-cantilever",
    )
    model = StatefulCorotationalFrame3DSparseModel(elastic, (_material(),))

    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=StatefulCorotationalFrame3DSparseConfig(),
    )
    first = result.steps[0].convergence_trace[0]["equation_scaling"]
    final = result.steps[0].equation_scaling

    assert first["translation_residual_norm"] == pytest.approx(0.0, abs=1.0e-8)
    assert first["rotation_residual_norm"] == pytest.approx(10.0)
    assert final.characteristic_length == pytest.approx(2.0)
    assert final.rotation_increment_norm >= 0.0
    assert final.scaled_tangent_condition > 0.0
    assert all(
        diagnostic.contract_pass
        for diagnostic in result.steps[0].factorization_diagnostics
    )


def test_confined_concrete_unloading_is_rejected_at_solver_level() -> None:
    material = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)
    props = FrameProps(
        area_m2=0.02,
        e_n_per_m2=material.elastic_modulus_mpa * 1000.0,
        g_n_per_m2=1.2e7,
        iy_m4=5.0e-5,
        iz_m4=8.0e-5,
        j_m4=1.0e-5,
    )
    section = TimoshenkoFrame3DSection(
        props,
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )
    load = [0.0] * 12
    load[6] = -300.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, section),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id="confined-concrete-unloading-guard",
    )
    model = StatefulCorotationalFrame3DSparseModel(elastic, (material,))
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40)
    loaded = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (1.0,),
        config=config,
    )
    accepted = loaded.final_checkpoint

    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match="unsupported_constitutive_path",
    ) as failure:
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (0.5,),
            config=config,
            resume_from=accepted,
        )

    assert failure.value.code == "unsupported_constitutive_path"
    assert len(failure.value.attempts) == 1
    assert failure.value.attempts[0]["cutback_applied"] is False
    assert failure.value.attempts[0]["rollback_exact"] is True
    assert loaded.final_checkpoint == accepted
    assert (
        loaded.final_checkpoint.material_states[0].state_hash
        == accepted.material_states[0].state_hash
    )
