from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseModel,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    solve_stateful_corotational_frame3d_sparse_load_path,
    stateful_corotational_frame3d_dense_sparse_parity_receipt,
    stateful_corotational_frame3d_member_response,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.stateful_corotational_fiber_frame3d import (
    StatefulCorotationalFiberFrame3D,
    StatefulCorotationalFiberFrame3DResponse,
    StatefulCorotationalFiberFrame3DState,
)
from structural_analysis.elements.timoshenko_frame3d import TimoshenkoFrame3DSection
from structural_analysis.materials.stateful_biaxial_fiber_section import (
    StatefulBiaxialFiberSection,
    StatefulBiaxialSectionFiber,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


ROOT = Path(__file__).resolve().parents[1]


def _steel() -> BilinearCombinedHardeningSteel:
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id="distributed-frame3d-steel",
    )


def _fiber_section() -> StatefulBiaxialFiberSection:
    steel = _steel()
    return StatefulBiaxialFiberSection(
        fibers=tuple(
            StatefulBiaxialSectionFiber(
                fiber_id=f"fiber-{index}",
                y_m=y,
                z_m=z,
                area_m2=0.0025,
                material=steel,
            )
            for index, (y, z) in enumerate(
                ((-0.15, -0.10), (-0.15, 0.10), (0.15, -0.10), (0.15, 0.10))
            )
        ),
        section_id="distributed-frame3d-section",
    )


def _reference_section() -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.01,
            e_n_per_m2=2.0e8,
            g_n_per_m2=8.0e7,
            iy_m4=1.0e-4,
            iz_m4=2.25e-4,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.008,
        effective_shear_area_z_m2=0.008,
    )


def _element(
    *,
    coordinates: tuple[tuple[float, float, float], ...] = (
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
    ),
    roll_deg: float = 0.0,
) -> StatefulCorotationalFiberFrame3D:
    return StatefulCorotationalFiberFrame3D(
        node_coordinates_m=coordinates,
        section=_fiber_section(),
        integration_order=2,
        local_axis_roll_deg=roll_deg,
        element_id="distributed-fiber-member",
    )


def _model() -> StatefulCorotationalFrame3DSparseModel:
    reference_load = [0.0] * 12
    reference_load[6] = 1800.0
    reference_load[10] = 100.0
    reference_load[11] = -150.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember(
                "member-1",
                0,
                1,
                _reference_section(),
            ),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(reference_load),
        model_id="distributed-fiber-frame3d",
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, (_element(),))


def test_distributed_fiber_member_zero_and_rigid_motion_are_objective() -> None:
    element = _element()
    reference = _reference_section()
    parent = element.initial_state()
    zero = element.integrate(
        np.zeros(12),
        parent,
        reference_section=reference,
    )

    assert zero.state == parent
    assert zero.parent_state_hash == parent.state_hash
    assert np.linalg.norm(zero.correction_basic_forces, ord=np.inf) <= 1.0e-12
    assert np.linalg.norm(zero.internal_force_global, ord=np.inf) <= 3.0e-10

    rotation_vector = np.asarray((0.08, -0.05, 0.12))
    rotation = Rotation.from_rotvec(rotation_vector).as_matrix()
    translation = np.asarray((0.4, -0.3, 0.2))
    coordinates = np.asarray(element.node_coordinates_m)
    displacement = np.zeros(12)
    displacement[0:3] = translation + rotation @ coordinates[0] - coordinates[0]
    displacement[3:6] = rotation_vector
    displacement[6:9] = translation + rotation @ coordinates[1] - coordinates[1]
    displacement[9:12] = rotation_vector
    rigid = element.integrate(
        displacement,
        parent,
        reference_section=reference,
    )

    assert np.linalg.norm(rigid.selected_basic_deformations, ord=np.inf) <= 5.0e-16
    assert np.linalg.norm(rigid.correction_basic_forces, ord=np.inf) <= 1.0e-9
    assert np.linalg.norm(rigid.internal_force_global, ord=np.inf) <= 2.0e-6


def test_distributed_fiber_member_same_parent_global_tangent() -> None:
    model = _model()
    element = model.axial_materials[0]
    assert type(element) is StatefulCorotationalFiberFrame3D
    member = model.elastic_model.members[0]
    coordinates = np.asarray(model.elastic_model.node_coordinates_m)
    parent = element.initial_state()
    displacement = np.zeros(12)
    displacement[6] = 3.0e-3
    displacement[7] = -2.0e-3
    displacement[8] = 1.5e-3
    displacement[10] = 8.0e-3
    displacement[11] = -6.0e-3
    center = stateful_corotational_frame3d_member_response(
        member=member,
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        axial_material=element,
        committed_state=parent,
    )

    assert (
        type(center.axial_material_response) is StatefulCorotationalFiberFrame3DResponse
    )
    for column in (6, 10, 11):
        step = 1.0e-7
        plus = displacement.copy()
        minus = displacement.copy()
        plus[column] += step
        minus[column] -= step
        forward = stateful_corotational_frame3d_member_response(
            member=member,
            node_coordinates_m=coordinates,
            element_displacements=plus,
            axial_material=element,
            committed_state=parent,
        )
        backward = stateful_corotational_frame3d_member_response(
            member=member,
            node_coordinates_m=coordinates,
            element_displacements=minus,
            axial_material=element,
            committed_state=parent,
        )
        finite_difference = (
            forward.internal_force_global - backward.internal_force_global
        ) / (2.0 * step)
        tangent_column = center.consistent_tangent_global[:, column]
        relative_error = np.linalg.norm(
            finite_difference - tangent_column,
            ord=np.inf,
        ) / max(
            np.linalg.norm(finite_difference, ord=np.inf),
            np.linalg.norm(tangent_column, ord=np.inf),
            1.0,
        )
        assert relative_error <= 2.0e-6
    assert center.axial_material_response.parent_state_hash == parent.state_hash
    assert (
        sum(
            row.yielded_steel_fiber_count
            for row in center.axial_material_response.section_responses
        )
        > 0
    )
    assert parent == element.initial_state()


def test_distributed_fiber_native_sparse_reversal_and_resume_are_exact() -> None:
    model = _model()
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_iterations=40,
        residual_relative_tolerance=1.0e-7,
        residual_absolute_tolerance_kn=1.0e-6,
    )
    initial = initial_stateful_corotational_frame3d_sparse_checkpoint(
        model,
        config=config,
    )
    parity = stateful_corotational_frame3d_dense_sparse_parity_receipt(
        model,
        initial,
        target_load_factor=0.25,
        trial_displacement=np.zeros(model.total_dofs),
    )
    assert all(parity.checks.values())

    path = (0.25, 0.5, 1.0, -0.5, 0.25)
    one_shot = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        path,
        config=config,
    )
    prefix = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        path[:3],
        config=config,
    )
    resumed = solve_stateful_corotational_frame3d_sparse_load_path(
        model,
        path[3:],
        config=config,
        resume_from=prefix.final_checkpoint,
    )

    assert one_shot.final_checkpoint == resumed.final_checkpoint
    state = one_shot.final_checkpoint.material_states[0]
    assert type(state) is StatefulCorotationalFiberFrame3DState
    assert any(
        fiber_state.accumulated_plastic_strain > 0.0
        for point in state.integration_point_states
        for fiber_state in point.fiber_states
    )
    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(one_shot.final_checkpoint.to_dict())


def test_distributed_fiber_member_bindings_fail_closed() -> None:
    reference_load = [0.0] * 12
    reference_load[6] = 1.0
    member = CorotationalFrame3DMember(
        "member-1",
        0,
        1,
        _reference_section(),
        local_axis_roll_deg=5.0,
    )
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(member,),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(reference_load),
        model_id="invalid-distributed-fiber-binding",
    )
    with pytest.raises(ValueError, match="coordinate binding mismatch"):
        StatefulCorotationalFrame3DSparseModel(
            elastic,
            (
                _element(
                    coordinates=((0.0, 0.0, 0.0), (2.1, 0.0, 0.0)),
                    roll_deg=5.0,
                ),
            ),
        )
    with pytest.raises(ValueError, match="roll binding mismatch"):
        StatefulCorotationalFrame3DSparseModel(elastic, (_element(roll_deg=0.0),))

    mismatched = TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.01,
            e_n_per_m2=1.9e8,
            g_n_per_m2=8.0e7,
            iy_m4=1.0e-4,
            iz_m4=2.25e-4,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.008,
        effective_shear_area_z_m2=0.008,
    )
    bad_elastic = CorotationalFrame3DModel(
        node_coordinates_m=elastic.node_coordinates_m,
        members=(CorotationalFrame3DMember("member-1", 0, 1, mismatched),),
        restrained_dofs=elastic.restrained_dofs,
        reference_load_kn=elastic.reference_load_kn,
        model_id="invalid-distributed-fiber-reference",
    )
    with pytest.raises(ValueError, match="initial tangent"):
        StatefulCorotationalFrame3DSparseModel(bad_elastic, (_element(),))


def test_distributed_mixed_steel_concrete_fibers_couple_axial_and_bending() -> None:
    steel = _steel()
    concrete = AsymmetricConcreteDamageMaterial(
        material_id="distributed-frame3d-concrete"
    )
    coordinates = ((-0.15, -0.10), (-0.15, 0.10), (0.15, -0.10), (0.15, 0.10))
    fibers: list[StatefulBiaxialSectionFiber] = []
    for index, (y, z) in enumerate(coordinates):
        fibers.extend(
            (
                StatefulBiaxialSectionFiber(
                    f"concrete-{index}",
                    y,
                    z,
                    0.002,
                    concrete,
                ),
                StatefulBiaxialSectionFiber(
                    f"steel-{index}",
                    y,
                    z,
                    0.0005,
                    steel,
                ),
            )
        )
    fiber_section = StatefulBiaxialFiberSection(
        tuple(fibers),
        section_id="distributed-mixed-rc-section",
    )
    element = StatefulCorotationalFiberFrame3D(
        ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        fiber_section,
        integration_order=2,
        element_id="distributed-mixed-rc-member",
    )
    effective_modulus_kn_per_m2 = 64.0e6
    reference = TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.01,
            e_n_per_m2=effective_modulus_kn_per_m2,
            g_n_per_m2=2.5e7,
            iy_m4=1.0e-4,
            iz_m4=2.25e-4,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.008,
        effective_shear_area_z_m2=0.008,
    )
    parent = element.initial_state()
    displacement = np.zeros(12)
    displacement[6] = 4.0e-3
    displacement[10] = 3.0e-3
    displacement[11] = -2.0e-3
    response = element.integrate(
        displacement,
        parent,
        reference_section=reference,
    )

    assert all(row.yielded_steel_fiber_count > 0 for row in response.section_responses)
    assert all(
        row.damaged_concrete_fiber_count > 0 for row in response.section_responses
    )
    assert response.dissipated_energy_mj > 0.0
    assert (
        len(
            {
                type(state)
                for point in response.state.integration_point_states
                for state in point.fiber_states
            }
        )
        == 2
    )
    step = 1.0e-7
    plus = displacement.copy()
    minus = displacement.copy()
    plus[6] += step
    minus[6] -= step
    finite_difference = (
        element.integrate(
            plus, parent, reference_section=reference
        ).internal_force_global
        - element.integrate(
            minus,
            parent,
            reference_section=reference,
        ).internal_force_global
    ) / (2.0 * step)
    tangent = response.consistent_tangent_global[:, 6]
    relative_error = np.linalg.norm(finite_difference - tangent, ord=np.inf) / max(
        np.linalg.norm(finite_difference, ord=np.inf),
        np.linalg.norm(tangent, ord=np.inf),
        1.0,
    )
    assert relative_error <= 3.0e-6
