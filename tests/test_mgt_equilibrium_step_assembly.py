from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_equilibrium_step_assembly import (  # noqa: E402
    _surface_pressure_load_path_filter,
    build_equilibrium_step_assembler,
    surface_pressure_load_path_components,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import FrameElement  # noqa: E402
import mgt_hip_full_residual_backend  # noqa: E402


def test_build_equilibrium_step_assembler_freezes_external_load() -> None:
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
    spring = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(12, 12),
    ).tocsr()
    assembler, meta = build_equilibrium_step_assembler(
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=np.asarray([], dtype=np.int32),
        elem_section_id=np.asarray([], dtype=np.int32),
        elem_material_id=np.asarray([], dtype=np.int32),
        conn_ptr=np.asarray([0], dtype=np.int64),
        conn_idx=np.asarray([], dtype=np.int64),
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=0.5,
        restrained={0, 1, 2, 3, 4, 5},
    )
    u = np.zeros(12, dtype=np.float64)
    _k0, f0, _free0, _r0, _rhs0, m0 = assembler(u)
    u[8] = 0.01
    _k1, f1, _free1, _r1, _rhs1, m1 = assembler(u)

    assert meta["frozen_load_scale"] == 0.5
    np.testing.assert_allclose(f0, f1)
    assert m1["frozen_external_load"] is True


def test_surface_pressure_load_path_filter_keeps_attached_components_only() -> None:
    elements = [
        FrameElement(
            elem_id=1,
            node_i=0,
            node_j=6,
            section_id=1,
            material_id=1,
            length_m=3.0,
        )
    ]
    allowed, meta = _surface_pressure_load_path_filter(
        frame_elements=elements,
        elem_type_code=np.asarray([2, 2], dtype=np.int32),
        conn_ptr=np.asarray([0, 3, 6], dtype=np.int64),
        conn_idx=np.asarray([0, 1, 2, 3, 4, 5], dtype=np.int64),
        restrained=set(),
        policy="attached_components_only",
    )

    assert allowed == {0}
    assert meta["pressure_load_filter_enabled"] is True
    assert meta["surface_component_count"] == 2
    assert meta["attached_surface_component_count"] == 1
    assert meta["free_pressure_surface_component_count"] == 1
    assert meta["pressure_load_suppressed_surface_element_count"] == 1


def test_surface_pressure_load_path_components_reports_free_component_nodes() -> None:
    components = surface_pressure_load_path_components(
        frame_elements=[
            FrameElement(
                elem_id=1,
                node_i=0,
                node_j=6,
                section_id=1,
                material_id=1,
                length_m=3.0,
            )
        ],
        elem_type_code=np.asarray([2, 2], dtype=np.int32),
        conn_ptr=np.asarray([0, 3, 6], dtype=np.int64),
        conn_idx=np.asarray([0, 1, 2, 3, 4, 5], dtype=np.int64),
        restrained=set(),
    )

    assert [component["attached"] for component in components] == [True, False]
    assert components[0]["surface_node_indices"] == [0, 1, 2]
    assert components[1]["surface_node_indices"] == [3, 4, 5]
    assert components[1]["surface_element_indices"] == [1]


def test_surface_pressure_load_path_filter_keeps_restrained_shell_component() -> None:
    allowed, meta = _surface_pressure_load_path_filter(
        frame_elements=[],
        elem_type_code=np.asarray([2], dtype=np.int32),
        conn_ptr=np.asarray([0, 3], dtype=np.int64),
        conn_idx=np.asarray([0, 1, 2], dtype=np.int64),
        restrained={1},
        policy="attached_components_only",
    )

    assert allowed == {0}
    assert meta["attached_surface_component_count"] == 1
    assert meta["free_pressure_surface_component_count"] == 0


def test_surface_pressure_load_path_filter_supports_structural_policy_name() -> None:
    elements = [
        FrameElement(
            elem_id=1,
            node_i=0,
            node_j=6,
            section_id=1,
            material_id=1,
            length_m=3.0,
        )
    ]
    allowed, meta = _surface_pressure_load_path_filter(
        frame_elements=elements,
        elem_type_code=np.asarray([2, 2], dtype=np.int32),
        conn_ptr=np.asarray([0, 3, 6], dtype=np.int64),
        conn_idx=np.asarray([0, 1, 2, 3, 4, 5], dtype=np.int64),
        restrained=set(),
        policy="structural_components_only",
    )

    assert allowed == {0}
    assert meta["shell_pressure_load_path_policy"] == "structural_components_only"
    assert meta["pressure_load_filter_enabled"] is True
    assert meta["attached_surface_component_count"] == 1
    assert meta["free_pressure_surface_component_count"] == 1


def test_residual_batch_evaluator_accepts_resident_hip_backend(monkeypatch) -> None:
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
    spring = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(12, 12),
    ).tocsr()
    assembler, _meta = build_equilibrium_step_assembler(
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=np.asarray([], dtype=np.int32),
        elem_section_id=np.asarray([], dtype=np.int32),
        elem_material_id=np.asarray([], dtype=np.int32),
        conn_ptr=np.asarray([0], dtype=np.int64),
        conn_idx=np.asarray([], dtype=np.int64),
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=0.5,
        restrained={0, 1, 2, 3, 4, 5},
    )
    u = np.zeros(12, dtype=np.float64)
    _k, _f, free, _r, _rhs, _m = assembler(u)
    calls: dict[str, int] = {"prepare": 0, "evaluate": 0}

    class FakeResidentBackend:
        def evaluate(self, states: np.ndarray, *, reps: int = 1):
            calls["evaluate"] += 1
            state_batch = np.asarray(states, dtype=np.float64)
            return np.zeros((state_batch.shape[0], free.size), dtype=np.float64), {
                "backend": "native_hip_full_residual_resident_worker",
                "persistent_process_worker": True,
                "operator_buffers_device_resident": True,
            }

    def fake_prepare(**_kwargs):
        calls["prepare"] += 1
        return FakeResidentBackend()

    monkeypatch.setattr(
        mgt_hip_full_residual_backend.HipFullResidualResidentWorkerBackend,
        "prepare",
        staticmethod(fake_prepare),
    )
    residual_batch, trial_free, _trial_rhs, batch_meta = assembler.evaluate_residual_batch(
        np.vstack([u, u]),
        backend="hip_full_residual_resident",
    )

    assert calls == {"prepare": 1, "evaluate": 1}
    assert residual_batch.shape == (2, free.size)
    np.testing.assert_array_equal(trial_free, free)
    assert batch_meta["residual_batch_backend"] == "hip_full_residual_resident"
    assert batch_meta["hip_full_residual_batch_replay"] is True
    assert batch_meta["hip_full_residual_resident_worker"] is True
    assert batch_meta["persistent_process_worker"] is True


def test_residual_batch_evaluator_accepts_rust_hip_ffi_backend(monkeypatch) -> None:
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
    spring = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(12, 12),
    ).tocsr()
    assembler, _meta = build_equilibrium_step_assembler(
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=np.asarray([], dtype=np.int32),
        elem_section_id=np.asarray([], dtype=np.int32),
        elem_material_id=np.asarray([], dtype=np.int32),
        conn_ptr=np.asarray([0], dtype=np.int64),
        conn_idx=np.asarray([], dtype=np.int64),
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=0.5,
        restrained={0, 1, 2, 3, 4, 5},
    )
    u = np.zeros(12, dtype=np.float64)
    _k, _f, free, _r, _rhs, _m = assembler(u)
    calls: dict[str, int] = {"prepare": 0, "evaluate": 0}

    class FakeRustFfiBackend:
        def evaluate(self, states: np.ndarray, *, reps: int = 1):
            calls["evaluate"] += 1
            state_batch = np.asarray(states, dtype=np.float64)
            return np.zeros((state_batch.shape[0], free.size), dtype=np.float64), {
                "backend": "rust_hip_full_residual_ffi",
                "persistent_in_process_worker": True,
                "rust_ffi_worker": True,
                "operator_buffers_device_resident": True,
            }

    def fake_prepare(**_kwargs):
        calls["prepare"] += 1
        return FakeRustFfiBackend()

    monkeypatch.setattr(
        mgt_hip_full_residual_backend.HipFullResidualRustFfiBackend,
        "prepare",
        staticmethod(fake_prepare),
    )
    residual_batch, trial_free, _trial_rhs, batch_meta = assembler.evaluate_residual_batch(
        np.vstack([u, u]),
        backend="rust_hip_full_residual_ffi",
    )

    assert calls == {"prepare": 1, "evaluate": 1}
    assert residual_batch.shape == (2, free.size)
    np.testing.assert_array_equal(trial_free, free)
    assert batch_meta["residual_batch_backend"] == "rust_hip_full_residual_ffi"
    assert batch_meta["hip_full_residual_batch_replay"] is True
    assert batch_meta["rust_hip_full_residual_ffi_worker"] is True
    assert batch_meta["persistent_in_process_worker"] is True
