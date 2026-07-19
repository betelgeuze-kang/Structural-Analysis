from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation" / "phase1"))

from mgt_state_updated_frame_axial_geometry import (  # noqa: E402
    audit_state_updated_frame_axial_property_coverage,
    prepack_state_updated_frame_axial_geometry,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    FrameElement,
    _assemble_sparse_frame,
)


def _single_element(*, offset: bool = False):
    node_xyz = np.asarray(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    element = FrameElement(
        elem_id=1,
        node_i=0,
        node_j=1,
        section_id=1,
        material_id=1,
        length_m=2.0,
        offset_i_global_m=(0.0, 0.2, 0.0) if offset else (0.0, 0.0, 0.0),
        offset_j_global_m=(0.0, 0.2, 0.0) if offset else (0.0, 0.0, 0.0),
    )
    section_props = {
        1: {"A_m2": 0.01, "Iy_m4": 1.0e-4, "Iz_m4": 5.0e-5}
    }
    material_props = {1: {"E_kN_per_m2": 210_000.0, "poisson": 0.3}}
    packed = prepack_state_updated_frame_axial_geometry(
        node_xyz=node_xyz,
        frame_elements=[element],
        section_props=section_props,
        material_props=material_props,
    )
    return node_xyz, [element], section_props, material_props, packed


def _reference_linear_force(
    node_xyz: np.ndarray,
    elements: list[FrameElement],
    section_props: dict,
    material_props: dict,
    displacement: np.ndarray,
) -> np.ndarray:
    stiffness, _external, _meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        include_geometric=False,
    )
    return np.asarray(stiffness @ displacement, dtype=np.float64)


def test_zero_state_correction_and_tangent_are_exact_zero() -> None:
    _node_xyz, _elements, _sections, _materials, packed = _single_element()
    zero = np.zeros(12, dtype=np.float64)
    direction = np.linspace(-0.3, 0.7, 12)

    correction, meta = packed.assemble_correction(zero)

    np.testing.assert_array_equal(correction, np.zeros(12))
    np.testing.assert_array_equal(packed.tangent_action(zero, direction), np.zeros(12))
    assert meta["state_updated_frame_axial_geometry_applied"] is True
    assert meta["maximum_axial_force_abs_n"] == 0.0
    assert meta["full_corotational_frame_claim"] is False


def test_finite_chord_replacement_removes_spurious_axial_rigid_rotation() -> None:
    node_xyz, elements, sections, materials, packed = _single_element()
    angle = np.deg2rad(30.0)
    displacement = np.zeros(12, dtype=np.float64)
    displacement[6:9] = [
        2.0 * np.cos(angle) - 2.0,
        2.0 * np.sin(angle),
        0.0,
    ]
    linear = _reference_linear_force(
        node_xyz,
        elements,
        sections,
        materials,
        displacement,
    )
    correction, _meta = packed.assemble_correction(displacement)
    total_axial = packed.assemble_total_axial_internal_force(displacement)
    linear_axial = packed.assemble_reference_linear_axial_internal_force(
        displacement
    )

    assert np.linalg.norm(linear_axial, ord=np.inf) > 1.0
    np.testing.assert_allclose(total_axial, np.zeros(12), atol=1.0e-9, rtol=0.0)
    np.testing.assert_allclose(
        linear_axial + correction,
        total_axial,
        atol=1.0e-9,
        rtol=0.0,
    )
    assert np.linalg.norm(linear + correction, ord=np.inf) < np.linalg.norm(
        linear,
        ord=np.inf,
    )


def test_tiny_transverse_motion_preserves_second_order_extension() -> None:
    _node_xyz, _elements, _sections, _materials, packed = _single_element()
    displacement = np.zeros(12, dtype=np.float64)
    transverse_motion_m = 1.0e-8
    displacement[7] = transverse_motion_m

    correction, meta = packed.assemble_correction(displacement)

    expected_extension_m = transverse_motion_m**2 / (
        np.hypot(2.0, transverse_motion_m) + 2.0
    )
    expected_axial_force_n = (
        packed.axial_stiffness_n_per_m[0] * expected_extension_m
    )
    assert expected_axial_force_n > 0.0
    assert correction[6] == pytest.approx(
        expected_axial_force_n,
        rel=1.0e-12,
        abs=1.0e-24,
    )
    assert correction[0] == pytest.approx(
        -expected_axial_force_n,
        rel=1.0e-12,
        abs=1.0e-24,
    )
    assert meta["maximum_extension_abs_m"] == pytest.approx(
        expected_extension_m,
        rel=1.0e-12,
        abs=1.0e-30,
    )
    assert meta["finite_chord_extension_evaluation"] == (
        "difference_of_squares_cancellation_stable"
    )
    assert meta["finite_chord_correction_evaluation"] == (
        "second_order_decomposition_cancellation_stable"
    )


@pytest.mark.parametrize("offset", [False, True])
def test_correction_is_energy_gradient_and_tangent_action(offset: bool) -> None:
    _node_xyz, _elements, _sections, _materials, packed = _single_element(
        offset=offset
    )
    displacement = np.asarray(
        [
            0.001,
            -0.002,
            0.0005,
            0.0002,
            -0.0001,
            0.0003,
            0.004,
            0.015,
            -0.006,
            -0.0002,
            0.0004,
            -0.0001,
        ],
        dtype=np.float64,
    )
    direction = np.asarray(
        [
            0.7,
            -0.2,
            0.4,
            0.1,
            -0.3,
            0.6,
            -0.5,
            0.8,
            -0.7,
            0.2,
            0.9,
            -0.4,
        ],
        dtype=np.float64,
    )
    direction /= np.linalg.norm(direction)
    force_step = 1.0e-7
    energy_step = 1.0e-7

    analytic_action = packed.tangent_action(displacement, direction)
    forward_force, _ = packed.assemble_correction(
        displacement + force_step * direction
    )
    backward_force, _ = packed.assemble_correction(
        displacement - force_step * direction
    )
    finite_difference_action = (
        forward_force - backward_force
    ) / (2.0 * force_step)
    correction, _meta = packed.assemble_correction(displacement)
    forward_energy = packed.correction_strain_energy_n_m(
        displacement + energy_step * direction
    )
    backward_energy = packed.correction_strain_energy_n_m(
        displacement - energy_step * direction
    )
    energy_derivative = (forward_energy - backward_energy) / (
        2.0 * energy_step
    )

    np.testing.assert_allclose(
        analytic_action,
        finite_difference_action,
        rtol=2.0e-7,
        atol=2.0e-3,
    )
    assert energy_derivative == pytest.approx(
        float(np.dot(correction, direction)),
        rel=2.0e-7,
        abs=2.0e-5,
    )


def test_batch_correction_matches_scalar_rows() -> None:
    _node_xyz, _elements, _sections, _materials, packed = _single_element()
    first = np.zeros(12, dtype=np.float64)
    second = np.zeros(12, dtype=np.float64)
    second[7] = 0.02

    batch, meta = packed.assemble_correction_batch(np.vstack([first, second]))
    scalar_first, _ = packed.assemble_correction(first)
    scalar_second, _ = packed.assemble_correction(second)

    np.testing.assert_array_equal(batch[0], scalar_first)
    np.testing.assert_array_equal(batch[1], scalar_second)
    assert meta["batch_size"] == 2
    assert meta["maximum_batch_correction_inf_n"] > 0.0


def test_prepack_rejects_missing_source_properties() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    element = FrameElement(
        elem_id=9,
        node_i=0,
        node_j=1,
        section_id=4,
        material_id=7,
        length_m=1.0,
    )

    with pytest.raises(
        ValueError,
        match=(
            "requires complete source property coverage: "
            "unresolved_element_count=1.*first_unresolved_element=9"
        ),
    ):
        prepack_state_updated_frame_axial_geometry(
            node_xyz=node_xyz,
            frame_elements=[element],
            section_props={},
            material_props={},
        )


def test_property_coverage_audit_counts_missing_bindings_exactly() -> None:
    elements = [
        FrameElement(
            elem_id=element_id,
            node_i=0,
            node_j=1,
            section_id=section_id,
            material_id=material_id,
            length_m=1.0,
        )
        for element_id, section_id, material_id in (
            (1, 10, 20),
            (2, 10, 21),
            (3, 11, 20),
            (4, 12, 22),
        )
    ]

    audit = audit_state_updated_frame_axial_property_coverage(
        frame_elements=elements,
        section_props={10: {"A_m2": 0.1}, 11: {"A_m2": 0.2}},
        material_props={20: {"E_kN_per_m2": 1.0}},
        unresolved_element_head_limit=2,
    )

    assert audit["frame_element_count"] == 4
    assert audit["resolved_source_property_element_count"] == 2
    assert audit["unresolved_source_property_element_count"] == 2
    assert audit["source_property_coverage_ratio"] == pytest.approx(0.5)
    assert audit["exact_source_property_coverage"] is False
    assert audit["missing_section_element_count"] == 1
    assert audit["missing_material_element_count"] == 2
    assert audit["missing_section_id_counts"] == [
        {"section_id": 12, "element_count": 1}
    ]
    assert audit["missing_material_id_counts"] == [
        {"material_id": 21, "element_count": 1},
        {"material_id": 22, "element_count": 1},
    ]
    assert audit["unresolved_element_head"] == [
        {
            "element_id": 2,
            "section_id": 10,
            "material_id": 21,
            "missing_section_property": False,
            "missing_material_property": True,
        },
        {
            "element_id": 4,
            "section_id": 12,
            "material_id": 22,
            "missing_section_property": True,
            "missing_material_property": True,
        },
    ]
    assert audit["fallback_allowed_for_state_updated_geometry"] is False
