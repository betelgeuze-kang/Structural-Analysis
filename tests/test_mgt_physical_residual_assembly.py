from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_frame_force_based_assembly import assemble_frame_force_based_f_int  # noqa: E402
from mgt_physical_residual_assembly import (  # noqa: E402
    assemble_physical_internal_force_components,
    assemble_physical_internal_forces,
    assemble_physical_internal_forces_batch,
    assemble_physical_residual,
)
from mgt_shell_force_based_assembly import (  # noqa: E402
    assemble_shell_internal_force_components,
    assemble_shell_internal_forces,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    FrameElement,
    _assemble_sparse_frame,
)


def test_assemble_physical_residual_matches_linear_equilibrium() -> None:
    stiffness = coo_matrix(([2.0, 2.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsr()
    u = np.asarray([1.0, 2.0], dtype=np.float64)
    f_ext = np.asarray([2.0, 4.0], dtype=np.float64)
    f_int = np.asarray(stiffness @ u, dtype=np.float64)
    free = np.asarray([0, 1], dtype=np.int64)

    residual, rhs = assemble_physical_residual(u=u, f_ext=f_ext, free=free, f_int=f_int)

    np.testing.assert_allclose(residual, np.zeros(2), rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(rhs, f_ext)


def test_force_based_frame_matches_reference_stiffness_at_small_strain() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 4.0]], dtype=np.float64)
    elements = [
        FrameElement(
            elem_id=1,
            node_i=0,
            node_j=1,
            section_id=1,
            material_id=1,
            length_m=4.0,
        )
    ]
    section_props = {
        1: {"A_m2": 0.02, "Iy_m4": 8.0e-5, "Iz_m4": 4.0e-5},
    }
    material_props = {1: {"E_kN_per_m2": 210000.0, "poisson": 0.3}}
    u = np.zeros(12, dtype=np.float64)
    u[2] = -0.001
    u[8] = -0.001

    stiffness, _f_ext, _meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        include_geometric=False,
    )
    f_quasi = np.asarray(stiffness @ u, dtype=np.float64)
    f_force, meta = assemble_frame_force_based_f_int(
        u=u,
        node_xyz=node_xyz,
        frame_elements=elements,
        section_props=section_props,
        material_props=material_props,
        include_geometric=False,
    )

    assert meta["frame_internal_force_model"] == "corotational_force_based_6dof"
    np.testing.assert_allclose(f_force, f_quasi, rtol=1.0e-9, atol=1.0e-6)


def test_assemble_physical_internal_forces_defaults_to_force_based_frame() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]], dtype=np.float64)
    elements = [
        FrameElement(
            elem_id=1,
            node_i=0,
            node_j=1,
            section_id=1,
            material_id=1,
            length_m=3.0,
        )
    ]
    section_props = {
        1: {"A_m2": 0.01, "Iy_m4": 1.0e-4, "Iz_m4": 5.0e-5},
    }
    material_props = {1: {"E_kN_per_m2": 210000.0, "poisson": 0.3}}
    u = np.zeros(12, dtype=np.float64)
    elem_type_code = np.asarray([], dtype=np.int32)
    elem_section_id = np.asarray([], dtype=np.int32)
    elem_material_id = np.asarray([], dtype=np.int32)
    conn_ptr = np.asarray([0], dtype=np.int64)
    conn_idx = np.asarray([], dtype=np.int64)
    from scipy.sparse import coo_matrix

    spring_stiffness = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(12, 12),
    ).tocsr()

    f_int, meta = assemble_physical_internal_forces(
        u=u,
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring_stiffness,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=1.0,
    )

    assert meta["use_force_based_frame"] is True
    assert "corotational_force_based_6dof" in meta["physical_internal_force_model"]
    assert "component_internal_force_inf_n" in meta


def test_physical_internal_force_components_sum_to_total() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]], dtype=np.float64)
    elements = [
        FrameElement(
            elem_id=1,
            node_i=0,
            node_j=1,
            section_id=1,
            material_id=1,
            length_m=3.0,
        )
    ]
    section_props = {1: {"A_m2": 0.01, "Iy_m4": 1.0e-4, "Iz_m4": 5.0e-5}}
    material_props = {1: {"E_kN_per_m2": 210000.0, "poisson": 0.3}}
    u = np.zeros(12, dtype=np.float64)
    u[2] = -0.001
    elem_type_code = np.asarray([], dtype=np.int32)
    elem_section_id = np.asarray([], dtype=np.int32)
    elem_material_id = np.asarray([], dtype=np.int32)
    conn_ptr = np.asarray([0], dtype=np.int64)
    conn_idx = np.asarray([], dtype=np.int64)
    spring_stiffness = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(12, 12),
    ).tocsr()

    components, _component_meta = assemble_physical_internal_force_components(
        u=u,
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring_stiffness,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=1.0,
        split_shell_components=True,
    )
    total, meta = assemble_physical_internal_forces(
        u=u,
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring_stiffness,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=1.0,
        include_component_forces=True,
    )

    summed = sum(np.asarray(values, dtype=np.float64) for values in components.values())
    np.testing.assert_allclose(total, summed, rtol=1.0e-12, atol=1.0e-12)
    assert set(meta["component_forces"]) == set(components)
    assert meta["split_shell_components"] is True


def test_shell_internal_force_component_split_sums_to_shell_force() -> None:
    node_xyz = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 1.5, 0.0],
        ],
        dtype=np.float64,
    )
    elem_type_code = np.asarray([2], dtype=np.int32)
    elem_section_id = np.asarray([1], dtype=np.int32)
    elem_material_id = np.asarray([1], dtype=np.int32)
    conn_ptr = np.asarray([0, 3], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 2], dtype=np.int64)
    material_props = {1: {"E_kN_per_m2": 210000000.0, "poisson": 0.25}}
    plate_thickness_props = {1: {"effective_thickness_m": 0.18}}
    u = np.zeros(18, dtype=np.float64)
    u[0] = 0.002
    u[2] = -0.001
    u[8] = 0.003

    f_shell, aggregate_meta = assemble_shell_internal_forces(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )
    components, split_meta = assemble_shell_internal_force_components(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
    )

    f_split = components["shell_bending_drilling"] + components["shell_membrane"]
    np.testing.assert_allclose(f_split, f_shell, rtol=1.0e-10, atol=1.0e-6)
    assert split_meta["shell_stiffness_nnz"] == aggregate_meta["shell_stiffness_nnz"]
    assert split_meta["shell_bending_drilling_stiffness_nnz"] > 0
    assert split_meta["shell_membrane_stiffness_nnz"] > 0


def test_shell_internal_forces_reuse_operator_cache() -> None:
    node_xyz = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 1.5, 0.0],
        ],
        dtype=np.float64,
    )
    elem_type_code = np.asarray([2], dtype=np.int32)
    elem_section_id = np.asarray([1], dtype=np.int32)
    elem_material_id = np.asarray([1], dtype=np.int32)
    conn_ptr = np.asarray([0, 3], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 2], dtype=np.int64)
    material_props = {1: {"E_kN_per_m2": 210000000.0, "poisson": 0.25}}
    plate_thickness_props = {1: {"effective_thickness_m": 0.18}}
    u = np.zeros(18, dtype=np.float64)
    u[0] = 0.002
    u[2] = -0.001
    u[8] = 0.003
    cache: dict[str, object] = {}

    f_first, first_meta = assemble_shell_internal_forces(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        shell_operator_cache=cache,
    )
    f_second, second_meta = assemble_shell_internal_forces(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        shell_operator_cache=cache,
    )

    assert first_meta["shell_internal_force_cache_enabled"] is True
    assert first_meta["shell_internal_force_cache_hit"] is False
    assert second_meta["shell_internal_force_cache_hit"] is True
    assert sorted(cache) == ["shell_full_membrane_bending"]
    np.testing.assert_allclose(f_second, f_first, rtol=1.0e-12, atol=1.0e-12)


def test_physical_internal_forces_apply_shell_material_tangent_and_disable_cache() -> None:
    node_xyz = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 1.5, 0.0],
        ],
        dtype=np.float64,
    )
    elem_type_code = np.asarray([2], dtype=np.int32)
    elem_section_id = np.asarray([1], dtype=np.int32)
    elem_material_id = np.asarray([1], dtype=np.int32)
    conn_ptr = np.asarray([0, 3], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 2], dtype=np.int64)
    material_props = {1: {"type": "CONC", "name": "C40", "E_kN_per_m2": 30000000.0, "poisson": 0.2}}
    plate_thickness_props = {1: {"effective_thickness_m": 0.18}}
    spring_stiffness = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(18, 18),
    ).tocsr()
    u = np.zeros(18, dtype=np.float64)
    u[6] = -0.008
    cache: dict[str, object] = {}

    elastic, elastic_meta = assemble_physical_internal_forces(
        u=u,
        node_xyz=node_xyz,
        frame_elements=[],
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props={},
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        spring_stiffness=spring_stiffness,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=1.0,
        shell_operator_cache=cache,
    )
    material, material_meta = assemble_physical_internal_forces(
        u=u,
        node_xyz=node_xyz,
        frame_elements=[],
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props={},
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        spring_stiffness=spring_stiffness,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=1.0,
        apply_shell_material_tangent=True,
        shell_operator_cache=cache,
    )

    assert sorted(cache) == ["shell_full_membrane_bending"]
    assert elastic_meta["shell_meta"]["shell_material_tangent_override_enabled"] is False
    assert material_meta["shell_meta"]["shell_material_tangent_override_enabled"] is True
    assert material_meta["shell_meta"]["shell_material_tangent_operator_cache_disabled"] is True
    assert material_meta["shell_material_tangent_meta"]["shell_material_tangent_applied"] is True
    assert (
        material_meta["shell_material_tangent_meta"]["nonlinear_tangent_surface_element_count"]
        == 1
    )
    assert not np.allclose(material, elastic)


def test_physical_internal_forces_batch_recomputes_shell_material_tangent() -> None:
    node_xyz = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 1.5, 0.0],
        ],
        dtype=np.float64,
    )
    elem_type_code = np.asarray([2], dtype=np.int32)
    elem_section_id = np.asarray([1], dtype=np.int32)
    elem_material_id = np.asarray([1], dtype=np.int32)
    conn_ptr = np.asarray([0, 3], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 2], dtype=np.int64)
    material_props = {1: {"type": "CONC", "name": "C40", "E_kN_per_m2": 30000000.0, "poisson": 0.2}}
    plate_thickness_props = {1: {"effective_thickness_m": 0.18}}
    spring_stiffness = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(18, 18),
    ).tocsr()
    states = np.zeros((2, 18), dtype=np.float64)
    states[0, 6] = -0.008
    states[1, 6] = -0.004

    batch, meta = assemble_physical_internal_forces_batch(
        u_batch=states,
        node_xyz=node_xyz,
        frame_elements=[],
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        section_props={},
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        spring_stiffness=spring_stiffness,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=1.0,
        apply_shell_material_tangent=True,
    )

    assert batch.shape == states.shape
    assert meta["shell_material_tangent_meta"]["shell_material_tangent_applied"] is True
    assert meta["shell_meta"]["shell_material_tangent_batch_recomputed"] is True
    assert meta["shell_material_tangent_meta"]["shell_material_tangent_min_nonlinear_surface_element_count"] == 1


def test_assemble_physical_residual_reports_nonzero_imbalance() -> None:
    u = np.asarray([0.1], dtype=np.float64)
    f_ext = np.asarray([1.0], dtype=np.float64)
    f_int = np.asarray([0.25], dtype=np.float64)
    free = np.asarray([0], dtype=np.int64)

    residual, _rhs = assemble_physical_residual(u=u, f_ext=f_ext, free=free, f_int=f_int)

    assert float(residual[0]) == -0.75
