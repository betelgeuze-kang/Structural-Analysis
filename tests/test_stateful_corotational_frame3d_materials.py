"""Material adapters for the native-sparse corotational 3D frame candidate."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    AxialMaterial,
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    assemble_stateful_corotational_frame3d_dense_reference,
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
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.composite_section import (
    ParallelCompositeSectionResponse,
    ParallelCompositeSectionState,
    ParallelSteelConcreteSectionMaterial,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
    FractureEnergyConcreteDamageMaterial,
)
from structural_analysis.materials.confined_concrete import (
    ConfinedConcreteMaterial,
    ConfinedConcreteState,
    StatefulConfinedConcreteResponse,
)
from structural_analysis.materials.partial_composite import (
    CondensedPartialCompositeAxialMaterial,
    CondensedPartialCompositeAxialResponse,
    CondensedPartialCompositeAxialState,
)


ROOT = Path(__file__).resolve().parents[1]


def _section(
    elastic_modulus_kn_per_m2: float,
    *,
    area_m2: float = 0.02,
) -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=area_m2,
            e_n_per_m2=elastic_modulus_kn_per_m2,
            g_n_per_m2=1.2e7,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )


def _single_member_model(
    material: AxialMaterial,
    *,
    elastic_modulus_mpa: float,
    reference_load_kn: float,
    model_id: str,
    area_m2: float = 0.02,
) -> StatefulCorotationalFrame3DSparseModel:
    load = [0.0] * 12
    load[6] = reference_load_kn
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember(
                "member-1",
                0,
                1,
                _section(elastic_modulus_mpa * 1000.0, area_m2=area_m2),
            ),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(load),
        model_id=model_id,
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, (material,))


def test_concrete_damage_member_uses_same_parent_consistent_tangent() -> None:
    material = AsymmetricConcreteDamageMaterial()
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.elastic_modulus_mpa,
        reference_load_kn=40.0,
        model_id="concrete-damage-member",
    )
    member = model.elastic_model.members[0]
    coordinates = np.asarray(model.elastic_model.node_coordinates_m)
    parent = material.initial_state()
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6] = 3.0e-4

    center = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        axial_material=material,
        committed_state=parent,
    )
    epsilon = 1.0e-7
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
        forward.internal_force_global[6] - backward.internal_force_global[6]
    ) / (2.0 * epsilon)
    relative_error = abs(
        finite_difference - center.consistent_tangent_global[6, 6]
    ) / max(abs(finite_difference), 1.0)

    assert type(center.axial_material_response) is ConcreteDamageResponse
    assert type(center.trial_state) is ConcreteDamageState
    assert center.axial_material_response.damage_evolved is True
    assert center.axial_material_response.committed_state_hash == parent.state_hash
    assert forward.axial_material_response.committed_state_hash == parent.state_hash
    assert backward.axial_material_response.committed_state_hash == parent.state_hash
    assert relative_error <= 2.0e-8

    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    receipt = stateful_corotational_frame3d_dense_sparse_parity_receipt(
        model,
        checkpoint,
        target_load_factor=0.5,
        trial_displacement=displacement,
    )
    assert all(receipt.checks.values())


def test_fracture_energy_concrete_is_bound_to_its_reference_modulus() -> None:
    material = FractureEnergyConcreteDamageMaterial(
        characteristic_length_m=0.1,
        tensile_fracture_energy_n_per_m=1000.0,
        compressive_fracture_energy_n_per_m=100_000.0,
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.elastic_modulus_mpa,
        reference_load_kn=10.0,
        model_id="fracture-energy-concrete-member",
    )
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=StatefulCorotationalFrame3DSparseConfig(),
    )

    assert type(checkpoint.material_states[0]) is ConcreteDamageState
    assert model.to_manifest()["axial_materials"][0]["material_type"] == (
        "fracture_energy_concrete_damage"
    )


def test_parallel_composite_commits_nested_state_and_resumes_exactly() -> None:
    material = ParallelSteelConcreteSectionMaterial(steel_area_fraction=0.5)
    effective_modulus_mpa = (
        material.steel_area_fraction * material.steel.elastic_modulus_mpa
        + material.concrete_area_fraction * material.concrete.elastic_modulus_mpa
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=effective_modulus_mpa,
        reference_load_kn=3000.0,
        model_id="parallel-composite-member",
    )
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40)
    path = (0.25, 0.5, 1.0, -0.5)
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
    state = one_shot.final_checkpoint.material_states[0]
    assert type(state) is ParallelCompositeSectionState
    assert state.steel_state.accumulated_plastic_strain > 0.0
    assert state.concrete_state.tensile_damage > 0.0
    assert one_shot.contract_pass is True
    assert all(
        diagnostic.contract_pass
        for step in one_shot.steps
        for diagnostic in step.factorization_diagnostics
    )

    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(one_shot.final_checkpoint.to_dict())


def test_parallel_composite_checkpoint_rejects_unreachable_nested_concrete() -> None:
    material = ParallelSteelConcreteSectionMaterial(steel_area_fraction=0.5)
    effective_modulus_mpa = (
        material.steel_area_fraction * material.steel.elastic_modulus_mpa
        + material.concrete_area_fraction * material.concrete.elastic_modulus_mpa
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=effective_modulus_mpa,
        reference_load_kn=100.0,
        model_id="parallel-composite-admissibility",
    )
    config = StatefulCorotationalFrame3DSparseConfig()
    checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    state = checkpoint.material_states[0]
    assert type(state) is ParallelCompositeSectionState
    forged_state = ParallelCompositeSectionState(
        steel_state=state.steel_state,
        concrete_state=ConcreteDamageState(
            dissipated_energy_density_mj_per_m3=1.0
        ),
    )
    forged = replace(checkpoint, material_states=(forged_state,))
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


def test_parallel_composite_member_reports_constituent_response() -> None:
    material = ParallelSteelConcreteSectionMaterial()
    effective_modulus_mpa = (
        material.steel_area_fraction * material.steel.elastic_modulus_mpa
        + material.concrete_area_fraction * material.concrete.elastic_modulus_mpa
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=effective_modulus_mpa,
        reference_load_kn=100.0,
        model_id="parallel-composite-recovery",
    )
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6] = 0.004
    response = stateful_corotational_frame3d_member_response(
        member=model.elastic_model.members[0],
        node_coordinates_m=np.asarray(model.elastic_model.node_coordinates_m),
        element_displacements=displacement,
        axial_material=material,
        committed_state=material.initial_state(),
    )

    assert type(response.axial_material_response) is ParallelCompositeSectionResponse
    assert response.axial_material_response.yielded is True
    assert response.axial_material_response.damage_evolved is True
    recovery = response.recovery_manifest()["axial_material_response"]
    assert recovery["steel_response"]["yielded"] is True
    assert recovery["concrete_response"]["damage_evolved"] is True


def test_material_and_reference_modulus_mismatch_fails_closed() -> None:
    material = AsymmetricConcreteDamageMaterial()
    with pytest.raises(ValueError, match="elastic modulus mismatch"):
        _single_member_model(
            material,
            elastic_modulus_mpa=200_000.0,
            reference_load_kn=1.0,
            model_id="invalid-concrete-reference",
        )


def test_confined_concrete_envelope_is_bound_to_member_state_and_tangent() -> None:
    material = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.elastic_modulus_mpa,
        reference_load_kn=-300.0,
        model_id="confined-concrete-member",
    )
    member = model.elastic_model.members[0]
    coordinates = np.asarray(model.elastic_model.node_coordinates_m)
    parent = material.initial_state()
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6] = -1.0e-3

    center = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        axial_material=material,
        committed_state=parent,
    )
    epsilon = 1.0e-7
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
        forward.internal_force_global[6] - backward.internal_force_global[6]
    ) / (2.0 * epsilon)
    relative_error = abs(
        finite_difference - center.consistent_tangent_global[6, 6]
    ) / max(abs(finite_difference), 1.0)

    assert type(center.axial_material_response) is StatefulConfinedConcreteResponse
    assert type(center.trial_state) is ConfinedConcreteState
    assert center.axial_material_response.branch == "ascending"
    assert center.axial_material_response.committed_state_hash == parent.state_hash
    assert center.trial_state.maximum_compressive_strain == pytest.approx(5.0e-4)
    assert relative_error <= 2.0e-7

    result = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.5, 1.0),
        config=StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40),
    )
    assert type(result.final_checkpoint.material_states[0]) is ConfinedConcreteState
    assert result.final_checkpoint.material_states[0].maximum_compressive_strain > 0.0
    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(result.final_checkpoint.to_dict())


def test_confined_concrete_frame3d_reversal_is_a_stable_solver_error() -> None:
    material = ConfinedConcreteMaterial(effective_lateral_pressure_mpa=2.0)
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.elastic_modulus_mpa,
        reference_load_kn=-300.0,
        model_id="confined-concrete-reversal-blocked",
    )
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40)
    prefix = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        (0.5, 1.0),
        config=config,
    )
    parent_bytes = prefix.final_checkpoint.material_states[0].canonical_bytes()
    manifest = model.to_manifest()["axial_materials"][0]
    assert manifest["path_capabilities"]["supports_monotonic"] is True
    assert manifest["path_capabilities"]["supports_unloading"] is False
    unloading_trial = np.asarray(prefix.final_checkpoint.displacement).copy()
    unloading_trial[6] *= 0.5

    for assemble in (
        assemble_stateful_corotational_frame3d_sparse,
        assemble_stateful_corotational_frame3d_dense_reference,
    ):
        with pytest.raises(
            StatefulCorotationalFrame3DSparseError,
            match="^unsupported_constitutive_path: member member-1:",
        ):
            assemble(
                model,
                prefix.final_checkpoint,
                target_load_factor=-0.5,
                trial_displacement=unloading_trial,
            )

    with pytest.raises(
        StatefulCorotationalFrame3DSparseError,
        match=(
            "^unsupported_constitutive_path: member member-1: "
            "mander_uniaxial_monotonic_compression"
        ),
    ):
        solve_stateful_corotational_frame3d_sparse_load_path(
            model,
            (-0.5,),
            config=config,
            resume_from=prefix.final_checkpoint,
        )
    assert (
        prefix.final_checkpoint.material_states[0].canonical_bytes()
        == parent_bytes
    )


def test_condensed_partial_interaction_has_exact_same_parent_schur_tangent() -> None:
    material = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.0,
        reference_area_m2=0.005,
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.initial_effective_modulus_mpa,
        reference_load_kn=500.0,
        model_id="condensed-partial-composite-member",
        area_m2=material.reference_area_m2,
    )
    member = model.elastic_model.members[0]
    coordinates = np.asarray(model.elastic_model.node_coordinates_m)
    parent = material.initial_state()
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6] = 4.0e-4

    center = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        axial_material=material,
        committed_state=parent,
    )
    epsilon = 1.0e-7
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
        forward.internal_force_global[6] - backward.internal_force_global[6]
    ) / (2.0 * epsilon)
    relative_error = abs(
        finite_difference - center.consistent_tangent_global[6, 6]
    ) / max(abs(finite_difference), 1.0)

    response = center.axial_material_response
    assert type(response) is CondensedPartialCompositeAxialResponse
    assert type(center.trial_state) is CondensedPartialCompositeAxialState
    assert response.committed_state_hash == parent.state_hash
    assert response.interface_slip_m > 0.0
    assert response.partial_composite_response.steel_strain != (
        response.partial_composite_response.concrete_strain
    )
    assert abs(response.internal_equilibrium_residual_n) <= (
        material.local_equilibrium_absolute_tolerance_n
    )
    assert relative_error <= 2.0e-7
    assert parent == material.initial_state()


def test_partial_interaction_cyclic_state_and_checkpoint_resume_are_exact() -> None:
    material = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.0,
        reference_area_m2=0.005,
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.initial_effective_modulus_mpa,
        reference_load_kn=500.0,
        model_id="condensed-partial-composite-cyclic-member",
        area_m2=material.reference_area_m2,
    )
    config = StatefulCorotationalFrame3DSparseConfig(maximum_iterations=40)
    path = (0.4, 1.0, -0.5, 0.25)
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
    state = one_shot.final_checkpoint.material_states[0]
    assert type(state) is CondensedPartialCompositeAxialState
    connector = state.component_state.connector_state
    assert connector.reversal_count == 2
    assert connector.stiffness_degradation > 0.0
    assert connector.strength_degradation > 0.0
    assert connector.dissipated_energy_j > 0.0

    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(one_shot.final_checkpoint.to_dict())


def test_partial_interaction_member_length_and_area_bindings_fail_closed() -> None:
    material = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.1,
        reference_area_m2=0.005,
    )
    with pytest.raises(ValueError, match="length binding mismatch"):
        _single_member_model(
            material,
            elastic_modulus_mpa=material.initial_effective_modulus_mpa,
            reference_load_kn=1.0,
            model_id="invalid-partial-length-binding",
            area_m2=material.reference_area_m2,
        )

    area_mismatch = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.0,
        reference_area_m2=0.006,
    )
    with pytest.raises(ValueError, match="area binding mismatch"):
        _single_member_model(
            area_mismatch,
            elastic_modulus_mpa=area_mismatch.initial_effective_modulus_mpa,
            reference_load_kn=1.0,
            model_id="invalid-partial-area-binding",
            area_m2=0.005,
        )


def test_partial_interaction_local_failure_has_stable_frame3d_reason_code() -> None:
    material = CondensedPartialCompositeAxialMaterial(
        member_length_m=2.0,
        reference_area_m2=0.005,
        maximum_local_iterations=1,
    )
    model = _single_member_model(
        material,
        elastic_modulus_mpa=material.initial_effective_modulus_mpa,
        reference_load_kn=500.0,
        model_id="partial-composite-local-failure",
        area_m2=material.reference_area_m2,
    )
    config = StatefulCorotationalFrame3DSparseConfig()
    parent = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    trial = np.asarray(parent.displacement, dtype=np.float64).copy()
    trial[6] = 1.0e-2

    for assemble in (
        assemble_stateful_corotational_frame3d_sparse,
        assemble_stateful_corotational_frame3d_dense_reference,
    ):
        with pytest.raises(StatefulCorotationalFrame3DSparseError) as error:
            assemble(
                model,
                parent,
                target_load_factor=1.0,
                trial_displacement=trial,
            )
        assert error.value.reason_code == "material_integration_failed"
    assert parent.material_states[0] == material.initial_state()
