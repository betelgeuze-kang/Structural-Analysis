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
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseModel,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    solve_stateful_corotational_frame3d_sparse_load_path,
    stateful_corotational_frame3d_dense_sparse_parity_receipt,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.stateful_corotational_partial_composite_frame3d import (
    StatefulCorotationalPartialCompositeFrame3D,
    StatefulCorotationalPartialCompositeFrame3DState,
)
from structural_analysis.elements.timoshenko_frame3d import TimoshenkoFrame3DSection
from structural_analysis.materials.bond_slip import BondSlipMaterial
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_biaxial_fiber_section import (
    StatefulBiaxialFiberSection,
    StatefulBiaxialSectionFiber,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


ROOT = Path(__file__).resolve().parents[1]


def _sections() -> tuple[
    StatefulBiaxialFiberSection,
    StatefulBiaxialFiberSection,
]:
    steel = BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=200_000.0,
        yield_stress_mpa=250.0,
        isotropic_hardening_modulus_mpa=100_000.0,
        kinematic_hardening_modulus_mpa=100_000.0,
        material_id="distributed-partial-steel",
    )
    concrete = AsymmetricConcreteDamageMaterial(
        elastic_modulus_mpa=30_000.0,
        tensile_strength_mpa=3.0,
        compressive_strength_mpa=30.0,
        tensile_softening_rate=3_000.0,
        compressive_softening_rate=400.0,
        material_id="distributed-partial-concrete",
    )
    steel_section = StatefulBiaxialFiberSection(
        fibers=tuple(
            StatefulBiaxialSectionFiber(
                fiber_id=f"steel-{index}",
                y_m=y,
                z_m=0.16,
                area_m2=0.0006,
                material=steel,
            )
            for index, y in enumerate((-0.08, 0.08))
        ),
        section_id="distributed-partial-steel-layer",
    )
    concrete_section = StatefulBiaxialFiberSection(
        fibers=tuple(
            StatefulBiaxialSectionFiber(
                fiber_id=f"concrete-{index}",
                y_m=y,
                z_m=-0.16,
                area_m2=0.004,
                material=concrete,
            )
            for index, y in enumerate((-0.08, 0.08))
        ),
        section_id="distributed-partial-concrete-layer",
    )
    return steel_section, concrete_section


def _reference_section() -> TimoshenkoFrame3DSection:
    steel, concrete = _sections()
    tangent = steel.initial_consistent_tangent() + concrete.initial_consistent_tangent()
    area_m2 = sum(fiber.area_m2 for fiber in (*steel.fibers, *concrete.fibers))
    elastic_modulus_kn_per_m2 = float(tangent[0, 0]) / area_m2
    assert (
        np.linalg.norm(
            tangent - np.diag(np.diag(tangent)),
            ord=np.inf,
        )
        <= 1.0e-10
    )
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=area_m2,
            e_n_per_m2=elastic_modulus_kn_per_m2,
            g_n_per_m2=12.0e6,
            iy_m4=float(tangent[1, 1]) / elastic_modulus_kn_per_m2,
            iz_m4=float(tangent[2, 2]) / elastic_modulus_kn_per_m2,
            j_m4=2.0e-5,
        ),
        effective_shear_area_y_m2=0.007,
        effective_shear_area_z_m2=0.007,
    )


def _element(
    *,
    connector_stiffness_n_per_m: float = 90.0e6,
    coordinates: tuple[tuple[float, float, float], ...] = (
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
    ),
    roll_deg: float = 0.0,
    maximum_local_condition_number: float = 1.0e14,
) -> StatefulCorotationalPartialCompositeFrame3D:
    steel, concrete = _sections()
    return StatefulCorotationalPartialCompositeFrame3D(
        node_coordinates_m=coordinates,
        steel_section=steel,
        concrete_section=concrete,
        connector=BondSlipMaterial(
            initial_stiffness_n_per_m=connector_stiffness_n_per_m,
            yield_slip_m=5.0e-5,
            ultimate_slip_m=2.0e-3,
            residual_strength_ratio=0.25,
            reversal_stiffness_degradation=0.08,
            reversal_strength_degradation=0.05,
            minimum_stiffness_ratio=0.15,
            material_id="distributed-partial-connector",
        ),
        connector_spacing_m=0.20,
        integration_order=2,
        local_axis_roll_deg=roll_deg,
        maximum_local_condition_number=maximum_local_condition_number,
        element_id="distributed-partial-member",
    )


def _model() -> StatefulCorotationalFrame3DSparseModel:
    reference_load = [0.0] * 12
    reference_load[7] = -0.25
    reference_load[10] = 0.35
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
        model_id="distributed-partial-frame3d",
    )
    return StatefulCorotationalFrame3DSparseModel(elastic, (_element(),))


def test_distributed_partial_composite_condenses_connector_field() -> None:
    reference = _reference_section()
    weak = _element(connector_stiffness_n_per_m=1.0e5)
    strong = _element(connector_stiffness_n_per_m=1.0e12)
    weak.validate_reference_section(reference)
    strong.validate_reference_section(reference)
    weak_tangent = weak.initial_condensed_basic_tangent()
    strong_tangent = strong.initial_condensed_basic_tangent()

    assert weak_tangent.shape == (5, 5)
    assert np.array_equal(weak_tangent, weak_tangent.T)
    assert np.array_equal(strong_tangent, strong_tangent.T)
    assert weak_tangent[1, 1] < strong_tangent[1, 1]
    assert weak_tangent[3, 3] < strong_tangent[3, 3]
    assert strong_tangent[1, 1] <= strong._elastic_reference_basic_tangent()[1, 1]


def test_distributed_partial_composite_same_parent_global_tangent() -> None:
    element = _element()
    reference = _reference_section()
    parent = element.initial_state()
    parent_bytes = parent.canonical_bytes()
    displacement = np.zeros(12)
    displacement[6] = 2.0e-4
    displacement[7] = -4.0e-4
    displacement[10] = 6.0e-4
    displacement[11] = -2.0e-4
    center = element.integrate(
        displacement,
        parent,
        reference_section=reference,
    )

    assert np.linalg.norm(center.interface_slip_nodes_m, ord=np.inf) > 0.0
    assert (
        np.linalg.norm(
            center.local_equilibrium_residual_kn,
            ord=np.inf,
        )
        <= element.local_equilibrium_absolute_tolerance_kn
    )
    for column, tolerance in ((6, 4.0e-6), (10, 4.0e-6), (11, 4.0e-6)):
        step = 1.0e-8
        plus = displacement.copy()
        minus = displacement.copy()
        plus[column] += step
        minus[column] -= step
        forward = element.integrate(plus, parent, reference_section=reference)
        backward = element.integrate(minus, parent, reference_section=reference)
        finite_difference = (
            forward.internal_force_global - backward.internal_force_global
        ) / (2.0 * step)
        analytic = center.consistent_tangent_global[:, column]
        relative_error = np.linalg.norm(
            finite_difference - analytic,
            ord=np.inf,
        ) / max(
            np.linalg.norm(finite_difference, ord=np.inf),
            np.linalg.norm(analytic, ord=np.inf),
            1.0,
        )
        assert relative_error <= tolerance
    assert center.parent_state_hash == parent.state_hash
    assert parent.canonical_bytes() == parent_bytes


def test_distributed_partial_composite_cyclic_state_and_replay_are_exact() -> None:
    element = _element()
    reference = _reference_section()
    parent = element.initial_state()

    def displacement(rotation: float) -> np.ndarray:
        values = np.zeros(12)
        values[4] = rotation
        values[10] = -rotation
        return values

    positive = element.integrate(
        displacement(1.2e-3),
        parent,
        reference_section=reference,
    )
    negative = element.integrate(
        displacement(-1.2e-3),
        positive.state,
        reference_section=reference,
    )
    recovery = element.integrate(
        displacement(6.0e-4),
        negative.state,
        reference_section=reference,
    )
    replay = element.integrate(
        displacement(6.0e-4),
        negative.state,
        reference_section=reference,
    )

    assert replay.state == recovery.state
    assert replay.state.state_hash == recovery.state.state_hash
    assert np.array_equal(replay.internal_force_global, recovery.internal_force_global)
    assert max(state.reversal_count for state in negative.state.connector_states) >= 1
    assert (
        max(state.stiffness_degradation for state in negative.state.connector_states)
        > 0.0
    )
    assert recovery.dissipated_energy_mj > 0.0


def test_distributed_partial_composite_native_sparse_resume_and_schema() -> None:
    model = _model()
    config = StatefulCorotationalFrame3DSparseConfig(
        maximum_iterations=35,
        residual_relative_tolerance=1.0e-8,
        residual_absolute_tolerance_kn=1.0e-8,
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
    assert type(state) is StatefulCorotationalPartialCompositeFrame3DState
    assert any(connector.reversal_count > 0 for connector in state.connector_states)
    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(one_shot.final_checkpoint.to_dict())


def test_distributed_partial_composite_bindings_and_local_failure_fail_closed() -> None:
    reference_load = [0.0] * 12
    reference_load[10] = 1.0
    elastic = CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(
            CorotationalFrame3DMember(
                "member-1",
                0,
                1,
                _reference_section(),
                local_axis_roll_deg=5.0,
            ),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(reference_load),
        model_id="invalid-distributed-partial-binding",
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
        StatefulCorotationalFrame3DSparseModel(elastic, (_element(),))

    ill_conditioned = _element(maximum_local_condition_number=1.0)
    parent = ill_conditioned.initial_state()
    parent_bytes = parent.canonical_bytes()
    displacement = np.zeros(12)
    displacement[10] = 8.0e-4
    with pytest.raises(RuntimeError, match="ill-conditioned"):
        ill_conditioned.integrate(
            displacement,
            parent,
            reference_section=_reference_section(),
        )
    assert parent.canonical_bytes() == parent_bytes


def test_distributed_partial_composite_state_tampering_is_rejected() -> None:
    element = _element()
    parent = element.initial_state()
    tampered = replace(parent, interface_slip_nodes_m=(1.0e-4, 0.0))
    with pytest.raises(ValueError, match="section strain"):
        element.validate_state(tampered)
