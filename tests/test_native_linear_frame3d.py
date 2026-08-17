from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
    local_timoshenko_frame_stiffness,
)


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
ABI_MAJOR = 1
ABI_MINOR = 1
STATUS_OK = 0
STATUS_INVALID_ARGUMENT = 1
STATUS_BUFFER_TOO_SMALL = 5
STATUS_SINGULAR_SYSTEM = 7
CAPABILITY_LINEAR_FRAME3D = 1 << 4


class EngineConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version_major", ctypes.c_uint32),
        ("abi_version_minor", ctypes.c_uint32),
        ("execution_mode", ctypes.c_uint32),
        ("requested_device_index", ctypes.c_int32),
        ("reserved_u32", ctypes.c_uint32 * 3),
    ]


class Node(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32),
        ("x_m", ctypes.c_double),
        ("y_m", ctypes.c_double),
        ("z_m", ctypes.c_double),
    ]


class Section(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32),
        ("area_m2", ctypes.c_double),
        ("elastic_modulus_kn_per_m2", ctypes.c_double),
        ("shear_modulus_kn_per_m2", ctypes.c_double),
        ("iy_m4", ctypes.c_double),
        ("iz_m4", ctypes.c_double),
        ("j_m4", ctypes.c_double),
        ("effective_shear_area_y_m2", ctypes.c_double),
        ("effective_shear_area_z_m2", ctypes.c_double),
    ]


class Member(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("node_i", ctypes.c_uint32),
        ("node_j", ctypes.c_uint32),
        ("section_index", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32 * 2),
        ("local_axis_roll_deg", ctypes.c_double),
    ]


class ModelInput(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version_major", ctypes.c_uint32),
        ("abi_version_minor", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32),
        ("nodes", ctypes.POINTER(Node)),
        ("node_count", ctypes.c_size_t),
        ("sections", ctypes.POINTER(Section)),
        ("section_count", ctypes.c_size_t),
        ("members", ctypes.POINTER(Member)),
        ("member_count", ctypes.c_size_t),
        ("restrained_dofs", ctypes.POINTER(ctypes.c_uint32)),
        ("restrained_dof_count", ctypes.c_size_t),
    ]


class ResultBuffers(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32),
        ("displacements", ctypes.POINTER(ctypes.c_double)),
        ("displacement_count", ctypes.c_size_t),
        ("reactions", ctypes.POINTER(ctypes.c_double)),
        ("reaction_count", ctypes.c_size_t),
        ("member_end_forces", ctypes.POINTER(ctypes.c_double)),
        ("member_end_force_count", ctypes.c_size_t),
    ]


@pytest.fixture(scope="module")
def native_library(tmp_path_factory: pytest.TempPathFactory) -> ctypes.CDLL:
    if os.name == "nt":
        pytest.skip("ctypes shared-library parity is exercised on the POSIX CI lane")
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.skip("C++ compiler is unavailable")
    build_dir = tmp_path_factory.mktemp("native-linear-frame3d")
    library_path = build_dir / "libstructural_engine_test.so"
    subprocess.run(
        [
            compiler,
            "-std=c++20",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-Werror",
            "-I",
            str(NATIVE / "include"),
            "-I",
            str(NATIVE / "cpp"),
            str(NATIVE / "cpp/structural_engine_c_api.cpp"),
            str(NATIVE / "cpp/linear_frame3d_c_api.cpp"),
            "-o",
            str(library_path),
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
    )
    library = ctypes.CDLL(str(library_path))
    library.sa_engine_create.argtypes = [
        ctypes.POINTER(EngineConfig),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.sa_engine_create.restype = ctypes.c_int32
    library.sa_engine_destroy.argtypes = [ctypes.c_void_p]
    library.sa_engine_destroy.restype = None
    library.sa_engine_capabilities.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint64),
    ]
    library.sa_engine_capabilities.restype = ctypes.c_int32
    library.sa_linear_frame3d_model_compile.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ModelInput),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.sa_linear_frame3d_model_compile.restype = ctypes.c_int32
    library.sa_linear_frame3d_model_destroy.argtypes = [ctypes.c_void_p]
    library.sa_linear_frame3d_model_destroy.restype = None
    library.sa_linear_frame3d_model_sizes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    library.sa_linear_frame3d_model_sizes.restype = ctypes.c_int32
    library.sa_linear_frame3d_solve.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.POINTER(ResultBuffers),
    ]
    library.sa_linear_frame3d_solve.restype = ctypes.c_int32
    return library


def _engine(library: ctypes.CDLL) -> ctypes.c_void_p:
    config = EngineConfig()
    config.struct_size = ctypes.sizeof(config)
    config.abi_version_major = ABI_MAJOR
    config.abi_version_minor = ABI_MINOR
    config.execution_mode = 0
    config.requested_device_index = -1
    handle = ctypes.c_void_p()
    assert library.sa_engine_create(ctypes.byref(config), ctypes.byref(handle)) == STATUS_OK
    assert handle.value is not None
    return handle


def _section() -> tuple[Section, TimoshenkoFrame3DSection]:
    values = {
        "area_m2": 0.02,
        "elastic_modulus_kn_per_m2": 200_000_000.0,
        "shear_modulus_kn_per_m2": 76_923_076.92307693,
        "iy_m4": 8.0e-5,
        "iz_m4": 5.0e-5,
        "j_m4": 1.0e-5,
        "effective_shear_area_y_m2": 0.015,
        "effective_shear_area_z_m2": 0.014,
    }
    native = Section()
    native.struct_size = ctypes.sizeof(native)
    for name, value in values.items():
        setattr(native, name, value)
    reference = TimoshenkoFrame3DSection(
        frame=FrameProps(
            area_m2=values["area_m2"],
            e_n_per_m2=values["elastic_modulus_kn_per_m2"],
            g_n_per_m2=values["shear_modulus_kn_per_m2"],
            iy_m4=values["iy_m4"],
            iz_m4=values["iz_m4"],
            j_m4=values["j_m4"],
        ),
        effective_shear_area_y_m2=values["effective_shear_area_y_m2"],
        effective_shear_area_z_m2=values["effective_shear_area_z_m2"],
    )
    return native, reference


def _model_input(
    *,
    restrained_values: tuple[int, ...] = (0, 1, 2, 3, 4, 5),
) -> tuple[ModelInput, object, object, object, object]:
    nodes = (Node * 2)()
    for node in nodes:
        node.struct_size = ctypes.sizeof(Node)
    nodes[1].x_m = 2.0
    native_section, _ = _section()
    sections = (Section * 1)(native_section)
    members = (Member * 1)()
    members[0].struct_size = ctypes.sizeof(Member)
    members[0].node_i = 0
    members[0].node_j = 1
    members[0].section_index = 0
    restrained = (ctypes.c_uint32 * len(restrained_values))(*restrained_values)
    model_input = ModelInput()
    model_input.struct_size = ctypes.sizeof(model_input)
    model_input.abi_version_major = ABI_MAJOR
    model_input.abi_version_minor = ABI_MINOR
    model_input.nodes = nodes
    model_input.node_count = len(nodes)
    model_input.sections = sections
    model_input.section_count = len(sections)
    model_input.members = members
    model_input.member_count = len(members)
    model_input.restrained_dofs = restrained
    model_input.restrained_dof_count = len(restrained)
    return model_input, nodes, sections, members, restrained


def _compile_model(
    library: ctypes.CDLL,
    engine: ctypes.c_void_p,
    *,
    restrained_values: tuple[int, ...] = (0, 1, 2, 3, 4, 5),
) -> tuple[ctypes.c_void_p, tuple[object, ...]]:
    model_input, *owners = _model_input(restrained_values=restrained_values)
    model = ctypes.c_void_p()
    status = library.sa_linear_frame3d_model_compile(
        engine,
        ctypes.byref(model_input),
        ctypes.byref(model),
    )
    assert status == STATUS_OK
    assert model.value is not None
    return model, tuple(owners) + (model_input,)


def _result_buffers() -> tuple[ResultBuffers, object, object, object]:
    displacements = (ctypes.c_double * 12)()
    reactions = (ctypes.c_double * 12)()
    member_forces = (ctypes.c_double * 12)()
    result = ResultBuffers()
    result.struct_size = ctypes.sizeof(result)
    result.displacements = displacements
    result.displacement_count = 12
    result.reactions = reactions
    result.reaction_count = 12
    result.member_end_forces = member_forces
    result.member_end_force_count = 12
    return result, displacements, reactions, member_forces


def test_native_cantilever_matches_python_timoshenko_reference(
    native_library: ctypes.CDLL,
) -> None:
    engine = _engine(native_library)
    model, owners = _compile_model(native_library, engine)
    assert owners
    try:
        capabilities = ctypes.c_uint64()
        assert native_library.sa_engine_capabilities(engine, ctypes.byref(capabilities)) == STATUS_OK
        assert capabilities.value & CAPABILITY_LINEAR_FRAME3D

        dof_count = ctypes.c_size_t()
        force_count = ctypes.c_size_t()
        assert native_library.sa_linear_frame3d_model_sizes(
            model,
            ctypes.byref(dof_count),
            ctypes.byref(force_count),
        ) == STATUS_OK
        assert (dof_count.value, force_count.value) == (12, 12)

        loads = (ctypes.c_double * 12)()
        loads[7] = -10.0
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()
        assert native_library.sa_linear_frame3d_solve(
            model,
            loads,
            len(loads),
            ctypes.byref(result),
        ) == STATUS_OK

        _, reference_section = _section()
        stiffness = local_timoshenko_frame_stiffness(reference_section, 2.0)
        load_vector = np.zeros(12, dtype=np.float64)
        load_vector[7] = -10.0
        expected_displacement = np.zeros(12, dtype=np.float64)
        expected_displacement[6:] = np.linalg.solve(stiffness[6:, 6:], load_vector[6:])
        expected_reaction = stiffness @ expected_displacement - load_vector
        expected_force = stiffness @ expected_displacement

        np.testing.assert_allclose(
            np.ctypeslib.as_array(displacement_buffer),
            expected_displacement,
            rtol=1.0e-11,
            atol=1.0e-13,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(reaction_buffer),
            expected_reaction,
            rtol=1.0e-10,
            atol=1.0e-10,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(force_buffer),
            expected_force,
            rtol=1.0e-10,
            atol=1.0e-10,
        )
    finally:
        native_library.sa_linear_frame3d_model_destroy(model)
        native_library.sa_engine_destroy(engine)


def test_singular_model_fails_with_zeroed_outputs(native_library: ctypes.CDLL) -> None:
    engine = _engine(native_library)
    model, owners = _compile_model(
        native_library,
        engine,
        restrained_values=(0, 1, 2),
    )
    assert owners
    try:
        loads = (ctypes.c_double * 12)()
        loads[7] = -10.0
        result, displacements, reactions, forces = _result_buffers()
        for buffer in (displacements, reactions, forces):
            for index in range(12):
                buffer[index] = 9.0
        assert native_library.sa_linear_frame3d_solve(
            model,
            loads,
            len(loads),
            ctypes.byref(result),
        ) == STATUS_SINGULAR_SYSTEM
        assert np.all(np.ctypeslib.as_array(displacements) == 0.0)
        assert np.all(np.ctypeslib.as_array(reactions) == 0.0)
        assert np.all(np.ctypeslib.as_array(forces) == 0.0)
    finally:
        native_library.sa_linear_frame3d_model_destroy(model)
        native_library.sa_engine_destroy(engine)


def test_reserved_section_fields_fail_closed(native_library: ctypes.CDLL) -> None:
    engine = _engine(native_library)
    model_input, _nodes, sections, _members, _restrained = _model_input()
    sections[0].reserved_u32 = 1
    model = ctypes.c_void_p(1)
    try:
        assert native_library.sa_linear_frame3d_model_compile(
            engine,
            ctypes.byref(model_input),
            ctypes.byref(model),
        ) == STATUS_INVALID_ARGUMENT
        assert model.value is None
    finally:
        native_library.sa_engine_destroy(engine)


def test_small_output_descriptor_is_rejected(native_library: ctypes.CDLL) -> None:
    engine = _engine(native_library)
    model, owners = _compile_model(native_library, engine)
    assert owners
    try:
        loads = (ctypes.c_double * 12)()
        result, _displacements, _reactions, _forces = _result_buffers()
        result.member_end_force_count = 11
        assert native_library.sa_linear_frame3d_solve(
            model,
            loads,
            len(loads),
            ctypes.byref(result),
        ) == STATUS_BUFFER_TOO_SMALL
    finally:
        native_library.sa_linear_frame3d_model_destroy(model)
        native_library.sa_engine_destroy(engine)
