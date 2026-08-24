from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from structural_analysis.elements.frame3d import (
    FrameProps,
    frame_rotation_matrix,
    frame_transform,
    rigid_end_offset_transform,
)
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
    local_timoshenko_frame_stiffness,
)


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
MODEL_ABI_MAJOR = 1
MODEL_ABI_MINOR = 5
ABI_VERSION = 0x0001_0005
STATUS_OK = 0
STATUS_INVALID_ARGUMENT = 1000
STATUS_BUFFER_TOO_SMALL = 1003
STATUS_SINGULAR_SYSTEM = 1102
CAPABILITY_LINEAR_FRAME3D = 1 << 3
CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD = 1 << 4
CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE = 1 << 5
CAPABILITY_LINEAR_FRAME3D_RIGID_END_OFFSET = 1 << 6
DOF_MASK_RZ = 1 << 5
DOF_MASK_RY = 1 << 4


class ApiRequest(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("flags", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64 * 3),
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
        ("released_dof_mask_i", ctypes.c_uint32),
        ("released_dof_mask_j", ctypes.c_uint32),
        ("local_axis_roll_deg", ctypes.c_double),
    ]


class MemberOffset(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("member_index", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32 * 2),
        ("offset_i_global_m", ctypes.c_double * 3),
        ("offset_j_global_m", ctypes.c_double * 3),
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
        ("member_offsets", ctypes.POINTER(MemberOffset)),
        ("member_offset_count", ctypes.c_size_t),
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


class UniformMemberLoad(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("member_index", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32 * 2),
        ("components_kn_per_m", ctypes.c_double * 3),
    ]


class LoadCase(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved_u32", ctypes.c_uint32),
        ("nodal_load_vector_kn", ctypes.POINTER(ctypes.c_double)),
        ("nodal_load_count", ctypes.c_uint64),
        ("uniform_member_loads", ctypes.POINTER(UniformMemberLoad)),
        ("uniform_member_load_count", ctypes.c_uint64),
    ]


CompileFn = ctypes.CFUNCTYPE(
    ctypes.c_uint32,
    ctypes.POINTER(ModelInput),
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
)
DestroyFn = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)
SizesFn = ctypes.CFUNCTYPE(
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64),
    ctypes.c_void_p,
)
SolveFn = ctypes.CFUNCTYPE(
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_double),
    ctypes.c_uint64,
    ctypes.POINTER(ResultBuffers),
    ctypes.c_void_p,
)
SolveLoadCaseFn = ctypes.CFUNCTYPE(
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.POINTER(LoadCase),
    ctypes.POINTER(ResultBuffers),
    ctypes.c_void_p,
)


class Api(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint64),
        ("validate_buffer_view", ctypes.c_void_p),
        ("model_ir_create", ctypes.c_void_p),
        ("model_ir_destroy", ctypes.c_void_p),
        ("model_ir_validation_report_size", ctypes.c_void_p),
        ("model_ir_validation_report_write", ctypes.c_void_p),
        ("model_ir_snapshot_size", ctypes.c_void_p),
        ("model_ir_snapshot_write", ctypes.c_void_p),
        ("linear_frame3d_model_compile", CompileFn),
        ("linear_frame3d_model_destroy", DestroyFn),
        ("linear_frame3d_model_sizes", SizesFn),
        ("linear_frame3d_solve", SolveFn),
        ("linear_frame3d_solve_load_case", SolveLoadCaseFn),
        ("reserved", ctypes.c_void_p * 2),
    ]


@pytest.fixture(scope="module")
def native_library(tmp_path_factory: pytest.TempPathFactory) -> ctypes.CDLL:
    if os.name == "nt":
        pytest.skip("ctypes shared-library parity is exercised on the POSIX CI lane")
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is unavailable")
    build_dir = tmp_path_factory.mktemp("native-linear-frame3d")
    subprocess.run(
        [
            cmake,
            "-S",
            str(NATIVE / "cpp"),
            "-B",
            str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_SHARED_LIBS=ON",
            "-DSTRUCTURAL_BUILD_TESTS=OFF",
            "-DSTRUCTURAL_ENABLE_HIP=OFF",
            "-DSTRUCTURAL_WARNINGS_AS_ERRORS=ON",
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
    )
    subprocess.run(
        [cmake, "--build", str(build_dir), "--parallel", "2"],
        cwd=ROOT,
        check=True,
        timeout=120,
    )
    library_path = build_dir / "lib" / "libstructural_c_abi_v1.so"
    library = ctypes.CDLL(str(library_path))
    library.sa_get_api_v1.argtypes = [
        ctypes.POINTER(ApiRequest),
        ctypes.POINTER(Api),
        ctypes.c_void_p,
    ]
    library.sa_get_api_v1.restype = ctypes.c_uint32
    return library


def _api(library: ctypes.CDLL) -> Api:
    request = ApiRequest()
    request.abi_version = ABI_VERSION
    request.struct_size = ctypes.sizeof(ApiRequest)
    api = Api()
    api.abi_version = ABI_VERSION
    api.struct_size = ctypes.sizeof(Api)
    assert (
        library.sa_get_api_v1(ctypes.byref(request), ctypes.byref(api), None)
        == STATUS_OK
    )
    assert api.abi_version == ABI_VERSION
    assert api.struct_size == ctypes.sizeof(Api)
    assert api.capabilities & CAPABILITY_LINEAR_FRAME3D
    assert api.capabilities & CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD
    assert api.capabilities & CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE
    assert api.capabilities & CAPABILITY_LINEAR_FRAME3D_RIGID_END_OFFSET
    return api


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
    model_input.abi_version_major = MODEL_ABI_MAJOR
    model_input.abi_version_minor = MODEL_ABI_MINOR
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
    api: Api,
    *,
    restrained_values: tuple[int, ...] = (0, 1, 2, 3, 4, 5),
) -> tuple[ctypes.c_void_p, tuple[object, ...]]:
    model_input, *owners = _model_input(restrained_values=restrained_values)
    model = ctypes.c_void_p()
    status = api.linear_frame3d_model_compile(
        ctypes.byref(model_input),
        ctypes.byref(model),
        None,
    )
    assert status == STATUS_OK
    assert model.value is not None
    return model, tuple(owners) + (model_input,)


def _result_buffers(
    dof_count: int = 12,
    member_force_count: int = 12,
) -> tuple[ResultBuffers, object, object, object]:
    displacements = (ctypes.c_double * dof_count)()
    reactions = (ctypes.c_double * dof_count)()
    member_forces = (ctypes.c_double * member_force_count)()
    result = ResultBuffers()
    result.struct_size = ctypes.sizeof(result)
    result.displacements = displacements
    result.displacement_count = dof_count
    result.reactions = reactions
    result.reaction_count = dof_count
    result.member_end_forces = member_forces
    result.member_end_force_count = member_force_count
    return result, displacements, reactions, member_forces


@pytest.mark.parametrize(
    ("loaded_dof", "load_value"),
    [
        (6, 12.5),
        (7, -10.0),
        (8, 7.5),
        (9, -3.0),
        (10, 4.0),
        (11, -5.0),
    ],
    ids=("axial", "shear-y", "shear-z", "torsion", "moment-y", "moment-z"),
)
def test_native_cantilever_all_six_modes_match_python_timoshenko_reference(
    native_library: ctypes.CDLL,
    loaded_dof: int,
    load_value: float,
) -> None:
    api = _api(native_library)
    model, owners = _compile_model(api)
    assert owners
    try:
        dof_count = ctypes.c_uint64()
        force_count = ctypes.c_uint64()
        assert (
            api.linear_frame3d_model_sizes(
                model,
                ctypes.byref(dof_count),
                ctypes.byref(force_count),
                None,
            )
            == STATUS_OK
        )
        assert (dof_count.value, force_count.value) == (12, 12)

        loads = (ctypes.c_double * 12)()
        loads[loaded_dof] = load_value
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()
        assert (
            api.linear_frame3d_solve(
                model,
                loads,
                len(loads),
                ctypes.byref(result),
                None,
            )
            == STATUS_OK
        )

        _, reference_section = _section()
        stiffness = local_timoshenko_frame_stiffness(reference_section, 2.0)
        load_vector = np.zeros(12, dtype=np.float64)
        load_vector[loaded_dof] = load_value
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
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_native_rigid_end_offsets_match_independent_python_transform(
    native_library: ctypes.CDLL,
) -> None:
    api = _api(native_library)
    start = np.asarray([0.0, 0.0, 0.0], dtype=np.float64)
    end = np.asarray([1.8, -0.4, 1.1], dtype=np.float64)
    offset_i = np.asarray([0.12, -0.08, 0.05], dtype=np.float64)
    offset_j = np.asarray([-0.09, 0.06, -0.03], dtype=np.float64)
    roll_deg = 17.0
    nodes = (Node * 2)()
    for node, coordinate in zip(nodes, (start, end), strict=True):
        node.struct_size = ctypes.sizeof(Node)
        node.x_m, node.y_m, node.z_m = coordinate
    native_section, reference_section = _section()
    sections = (Section * 1)(native_section)
    members = (Member * 1)()
    members[0].struct_size = ctypes.sizeof(Member)
    members[0].node_j = 1
    members[0].local_axis_roll_deg = roll_deg
    offsets = (MemberOffset * 1)()
    offsets[0].struct_size = ctypes.sizeof(MemberOffset)
    offsets[0].member_index = 0
    offsets[0].offset_i_global_m[:] = offset_i
    offsets[0].offset_j_global_m[:] = offset_j
    restrained = (ctypes.c_uint32 * 6)(0, 1, 2, 3, 4, 5)
    model_input = ModelInput(
        struct_size=ctypes.sizeof(ModelInput),
        abi_version_major=MODEL_ABI_MAJOR,
        abi_version_minor=MODEL_ABI_MINOR,
        nodes=nodes,
        node_count=len(nodes),
        sections=sections,
        section_count=len(sections),
        members=members,
        member_count=len(members),
        restrained_dofs=restrained,
        restrained_dof_count=len(restrained),
        member_offsets=offsets,
        member_offset_count=len(offsets),
    )
    model = ctypes.c_void_p()
    assert (
        api.linear_frame3d_model_compile(
            ctypes.byref(model_input), ctypes.byref(model), None
        )
        == STATUS_OK
    )
    try:
        loads = np.asarray(
            [0.0] * 6 + [8.0, -11.0, 5.0, 1.5, -2.0, 3.0],
            dtype=np.float64,
        )
        native_loads = (ctypes.c_double * 12)(*loads)
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()
        assert (
            api.linear_frame3d_solve(
                model, native_loads, len(native_loads), ctypes.byref(result), None
            )
            == STATUS_OK
        )

        effective_start = start + offset_i
        effective_end = end + offset_j
        length_m = float(np.linalg.norm(effective_end - effective_start))
        rotation = frame_rotation_matrix(effective_start, effective_end, roll_deg=roll_deg)
        local = local_timoshenko_frame_stiffness(reference_section, length_m)
        combined = frame_transform(rotation) @ rigid_end_offset_transform(offset_i, offset_j)
        global_stiffness = combined.T @ local @ combined
        expected_displacement = np.zeros(12, dtype=np.float64)
        expected_displacement[6:] = np.linalg.solve(global_stiffness[6:, 6:], loads[6:])
        expected_reaction = global_stiffness @ expected_displacement - loads
        expected_member_force = local @ combined @ expected_displacement

        np.testing.assert_allclose(
            np.ctypeslib.as_array(displacement_buffer),
            expected_displacement,
            rtol=2.0e-10,
            atol=2.0e-12,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(reaction_buffer),
            expected_reaction,
            rtol=2.0e-10,
            atol=2.0e-10,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(force_buffer),
            expected_member_force,
            rtol=2.0e-10,
            atol=2.0e-10,
        )
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


@pytest.mark.parametrize(
    (
        "load_component",
        "translation_dof",
        "rotation_dof",
        "inertia_name",
        "shear_area_name",
        "rotation_sign",
        "moment_sign",
    ),
    [
        (1, 7, 11, "iz_m4", "effective_shear_area_y_m2", 1.0, -1.0),
        (2, 8, 10, "iy_m4", "effective_shear_area_z_m2", -1.0, 1.0),
    ],
    ids=("local-y", "local-z"),
)
def test_native_uniform_transverse_member_loads_match_closed_form_cantilever_reference(
    native_library: ctypes.CDLL,
    load_component: int,
    translation_dof: int,
    rotation_dof: int,
    inertia_name: str,
    shear_area_name: str,
    rotation_sign: float,
    moment_sign: float,
) -> None:
    api = _api(native_library)
    model, owners = _compile_model(api)
    assert owners
    try:
        member_loads = (UniformMemberLoad * 1)()
        member_loads[0].struct_size = ctypes.sizeof(UniformMemberLoad)
        member_loads[0].member_index = 0
        member_loads[0].components_kn_per_m[load_component] = -10.0
        nodal_loads = (ctypes.c_double * 12)()
        load_case = LoadCase()
        load_case.struct_size = ctypes.sizeof(LoadCase)
        load_case.nodal_load_vector_kn = nodal_loads
        load_case.nodal_load_count = len(nodal_loads)
        load_case.uniform_member_loads = member_loads
        load_case.uniform_member_load_count = len(member_loads)

        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()
        assert (
            api.linear_frame3d_solve_load_case(
                model,
                ctypes.byref(load_case),
                ctypes.byref(result),
                None,
            )
            == STATUS_OK
        )

        length_m = 2.0
        load_kn_per_m = -10.0
        _, reference_section = _section()
        elastic_modulus = reference_section.frame.e_n_per_m2
        shear_modulus = reference_section.frame.g_n_per_m2
        inertia = getattr(reference_section.frame, inertia_name)
        shear_area = getattr(reference_section, shear_area_name)
        expected_tip_translation = load_kn_per_m * (
            length_m**4 / (8.0 * elastic_modulus * inertia)
            + length_m**2 / (2.0 * shear_modulus * shear_area)
        )
        expected_tip_rotation = (
            rotation_sign
            * load_kn_per_m
            * length_m**3
            / (6.0 * elastic_modulus * inertia)
        )
        moment_dof = rotation_dof - 6
        expected_reaction_moment = moment_sign * load_kn_per_m * length_m**2 / 2.0

        displacement = np.ctypeslib.as_array(displacement_buffer)
        reaction = np.ctypeslib.as_array(reaction_buffer)
        member_force = np.ctypeslib.as_array(force_buffer)
        np.testing.assert_allclose(
            displacement[[translation_dof, rotation_dof]],
            [expected_tip_translation, expected_tip_rotation],
            rtol=1.0e-11,
            atol=1.0e-13,
        )
        np.testing.assert_allclose(
            reaction[[load_component, moment_dof]],
            [-load_kn_per_m * length_m, expected_reaction_moment],
            rtol=1.0e-11,
            atol=1.0e-11,
        )
        np.testing.assert_allclose(
            member_force[
                [load_component, moment_dof, translation_dof, rotation_dof]
            ],
            [
                -load_kn_per_m * length_m,
                expected_reaction_moment,
                0.0,
                0.0,
            ],
            rtol=1.0e-11,
            atol=1.0e-11,
        )
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_native_uniform_axial_member_load_matches_closed_form_cantilever_reference(
    native_library: ctypes.CDLL,
) -> None:
    api = _api(native_library)
    model, owners = _compile_model(api)
    assert owners
    try:
        load_kn_per_m = 10.0
        length_m = 2.0
        member_loads = (UniformMemberLoad * 1)()
        member_loads[0].struct_size = ctypes.sizeof(UniformMemberLoad)
        member_loads[0].components_kn_per_m[0] = load_kn_per_m
        nodal_loads = (ctypes.c_double * 12)()
        load_case = LoadCase()
        load_case.struct_size = ctypes.sizeof(LoadCase)
        load_case.nodal_load_vector_kn = nodal_loads
        load_case.nodal_load_count = len(nodal_loads)
        load_case.uniform_member_loads = member_loads
        load_case.uniform_member_load_count = len(member_loads)
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()

        assert (
            api.linear_frame3d_solve_load_case(
                model,
                ctypes.byref(load_case),
                ctypes.byref(result),
                None,
            )
            == STATUS_OK
        )

        _, reference_section = _section()
        expected_tip_x = (
            load_kn_per_m
            * length_m**2
            / (2.0 * reference_section.frame.e_n_per_m2 * reference_section.frame.area_m2)
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(displacement_buffer)[6],
            expected_tip_x,
            rtol=1.0e-11,
            atol=1.0e-13,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(reaction_buffer)[0],
            -load_kn_per_m * length_m,
            rtol=1.0e-11,
            atol=1.0e-11,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(force_buffer)[[0, 6]],
            [-load_kn_per_m * length_m, 0.0],
            rtol=1.0e-11,
            atol=1.0e-11,
        )
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_native_rotational_release_matches_independent_static_condensation(
    native_library: ctypes.CDLL,
) -> None:
    api = _api(native_library)
    model_input, nodes, sections, members, _ = _model_input(
        restrained_values=(0, 1, 2, 3, 4, 5, 7, 8, 10, 11)
    )
    members[0].released_dof_mask_i = DOF_MASK_RY
    members[0].released_dof_mask_j = DOF_MASK_RZ
    model = ctypes.c_void_p()
    assert (
        api.linear_frame3d_model_compile(
            ctypes.byref(model_input), ctypes.byref(model), None
        )
        == STATUS_OK
    )
    assert nodes and sections
    try:
        member_loads = (UniformMemberLoad * 1)()
        member_loads[0].struct_size = ctypes.sizeof(UniformMemberLoad)
        member_loads[0].components_kn_per_m[1] = -10.0
        member_loads[0].components_kn_per_m[2] = 7.0
        nodal_loads = (ctypes.c_double * 12)()
        load_case = LoadCase(
            struct_size=ctypes.sizeof(LoadCase),
            nodal_load_vector_kn=nodal_loads,
            nodal_load_count=len(nodal_loads),
            uniform_member_loads=member_loads,
            uniform_member_load_count=len(member_loads),
        )
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()
        assert (
            api.linear_frame3d_solve_load_case(
                model, ctypes.byref(load_case), ctypes.byref(result), None
            )
            == STATUS_OK
        )

        _, reference_section = _section()
        original = local_timoshenko_frame_stiffness(reference_section, 2.0)
        released = np.asarray([4, 11])
        retained = np.asarray([index for index in range(12) if index not in released])
        inverse = np.linalg.inv(original[np.ix_(released, released)])
        condensed = np.zeros((12, 12), dtype=np.float64)
        condensed[np.ix_(retained, retained)] = (
            original[np.ix_(retained, retained)]
            - original[np.ix_(retained, released)]
            @ inverse
            @ original[np.ix_(released, retained)]
        )
        raw_equivalent = np.asarray(
            [0.0, -10.0, 7.0, 0.0, -7.0 / 3.0, -10.0 / 3.0,
             0.0, -10.0, 7.0, 0.0, 7.0 / 3.0, 10.0 / 3.0],
            dtype=np.float64,
        )
        condensed_equivalent = np.zeros(12, dtype=np.float64)
        condensed_equivalent[retained] = (
            raw_equivalent[retained]
            - original[np.ix_(retained, released)]
            @ inverse
            @ raw_equivalent[released]
        )
        free = np.asarray([6, 9])
        expected_displacement = np.zeros(12, dtype=np.float64)
        expected_displacement[free] = np.linalg.solve(
            condensed[np.ix_(free, free)], condensed_equivalent[free]
        )
        expected_reaction = condensed @ expected_displacement - condensed_equivalent
        expected_member_force = expected_reaction.copy()

        np.testing.assert_allclose(
            np.ctypeslib.as_array(displacement_buffer),
            expected_displacement,
            rtol=2.0e-10,
            atol=2.0e-12,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(reaction_buffer),
            expected_reaction,
            rtol=2.0e-10,
            atol=2.0e-10,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(force_buffer),
            expected_member_force,
            rtol=2.0e-10,
            atol=2.0e-10,
        )
        assert abs(force_buffer[11]) < 1.0e-10
        assert abs(force_buffer[4]) < 1.0e-10
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_native_rotated_rolled_uniform_member_load_matches_transformed_closed_form(
    native_library: ctypes.CDLL,
) -> None:
    api = _api(native_library)
    start = np.asarray([0.0, 0.0, 0.0], dtype=np.float64)
    end = np.asarray([1.2, -0.8, 1.4], dtype=np.float64)
    roll_deg = 23.0
    length_m = float(np.linalg.norm(end - start))
    nodes = (Node * 2)()
    for node, coordinate in zip(nodes, (start, end), strict=True):
        node.struct_size = ctypes.sizeof(Node)
        node.x_m, node.y_m, node.z_m = coordinate
    native_section, reference_section = _section()
    sections = (Section * 1)(native_section)
    members = (Member * 1)()
    members[0].struct_size = ctypes.sizeof(Member)
    members[0].node_j = 1
    members[0].local_axis_roll_deg = roll_deg
    restrained = (ctypes.c_uint32 * 6)(0, 1, 2, 3, 4, 5)
    model_input = ModelInput(
        struct_size=ctypes.sizeof(ModelInput),
        abi_version_major=MODEL_ABI_MAJOR,
        abi_version_minor=MODEL_ABI_MINOR,
        nodes=nodes,
        node_count=len(nodes),
        sections=sections,
        section_count=len(sections),
        members=members,
        member_count=len(members),
        restrained_dofs=restrained,
        restrained_dof_count=len(restrained),
    )
    model = ctypes.c_void_p()
    assert (
        api.linear_frame3d_model_compile(
            ctypes.byref(model_input), ctypes.byref(model), None
        )
        == STATUS_OK
    )
    try:
        load_kn_per_m = -10.0
        member_loads = (UniformMemberLoad * 1)()
        member_loads[0].struct_size = ctypes.sizeof(UniformMemberLoad)
        member_loads[0].components_kn_per_m[1] = load_kn_per_m
        nodal_loads = (ctypes.c_double * 12)()
        load_case = LoadCase(
            struct_size=ctypes.sizeof(LoadCase),
            nodal_load_vector_kn=nodal_loads,
            nodal_load_count=len(nodal_loads),
            uniform_member_loads=member_loads,
            uniform_member_load_count=len(member_loads),
        )
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers()
        assert (
            api.linear_frame3d_solve_load_case(
                model,
                ctypes.byref(load_case),
                ctypes.byref(result),
                None,
            )
            == STATUS_OK
        )

        local_displacement = np.zeros(12, dtype=np.float64)
        local_displacement[7] = load_kn_per_m * (
            length_m**4
            / (8.0 * reference_section.frame.e_n_per_m2 * reference_section.frame.iz_m4)
            + length_m**2
            / (
                2.0
                * reference_section.frame.g_n_per_m2
                * reference_section.effective_shear_area_y_m2
            )
        )
        local_displacement[11] = (
            load_kn_per_m
            * length_m**3
            / (6.0 * reference_section.frame.e_n_per_m2 * reference_section.frame.iz_m4)
        )
        local_reaction = np.zeros(12, dtype=np.float64)
        local_reaction[1] = -load_kn_per_m * length_m
        local_reaction[5] = -load_kn_per_m * length_m**2 / 2.0
        transform = frame_transform(frame_rotation_matrix(start, end, roll_deg=roll_deg))

        np.testing.assert_allclose(
            np.ctypeslib.as_array(displacement_buffer),
            transform.T @ local_displacement,
            rtol=2.0e-10,
            atol=2.0e-12,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(reaction_buffer),
            transform.T @ local_reaction,
            rtol=2.0e-9,
            atol=2.0e-9,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(force_buffer),
            local_reaction,
            rtol=2.0e-9,
            atol=2.0e-9,
        )
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_native_rotated_two_member_assembly_matches_python_reference(
    native_library: ctypes.CDLL,
) -> None:
    api = _api(native_library)
    coordinates = np.asarray(
        [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.5, 1.0)],
        dtype=np.float64,
    )
    nodes = (Node * 3)()
    for node, coordinate in zip(nodes, coordinates, strict=True):
        node.struct_size = ctypes.sizeof(Node)
        node.x_m, node.y_m, node.z_m = coordinate
    native_section, reference_section = _section()
    sections = (Section * 1)(native_section)
    member_rows = ((0, 1, 17.0), (1, 2, -23.0))
    members = (Member * len(member_rows))()
    for member, (node_i, node_j, roll_deg) in zip(members, member_rows, strict=True):
        member.struct_size = ctypes.sizeof(Member)
        member.node_i = node_i
        member.node_j = node_j
        member.section_index = 0
        member.local_axis_roll_deg = roll_deg
    restrained = (ctypes.c_uint32 * 6)(0, 1, 2, 3, 4, 5)
    model_input = ModelInput(
        struct_size=ctypes.sizeof(ModelInput),
        abi_version_major=MODEL_ABI_MAJOR,
        abi_version_minor=MODEL_ABI_MINOR,
        nodes=nodes,
        node_count=len(nodes),
        sections=sections,
        section_count=len(sections),
        members=members,
        member_count=len(members),
        restrained_dofs=restrained,
        restrained_dof_count=len(restrained),
    )
    model = ctypes.c_void_p()
    assert (
        api.linear_frame3d_model_compile(
            ctypes.byref(model_input), ctypes.byref(model), None
        )
        == STATUS_OK
    )
    assert model.value is not None
    try:
        dof_count = 18
        member_force_count = 24
        loads = np.zeros(dof_count, dtype=np.float64)
        loads[12:18] = (3.5, -7.0, 4.25, 1.5, -2.0, 2.75)
        native_loads = (ctypes.c_double * dof_count)(*loads)
        result, displacement_buffer, reaction_buffer, force_buffer = _result_buffers(
            dof_count, member_force_count
        )
        assert (
            api.linear_frame3d_solve(
                model,
                native_loads,
                len(native_loads),
                ctypes.byref(result),
                None,
            )
            == STATUS_OK
        )

        stiffness = np.zeros((dof_count, dof_count), dtype=np.float64)
        expected_member_forces: list[np.ndarray] = []
        member_reference: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        for node_i, node_j, roll_deg in member_rows:
            start = coordinates[node_i]
            end = coordinates[node_j]
            length = float(np.linalg.norm(end - start))
            local = local_timoshenko_frame_stiffness(reference_section, length)
            transform = frame_transform(
                frame_rotation_matrix(start, end, roll_deg=roll_deg)
            )
            dofs = np.asarray(
                [
                    *(range(node_i * 6, node_i * 6 + 6)),
                    *(range(node_j * 6, node_j * 6 + 6)),
                ]
            )
            stiffness[np.ix_(dofs, dofs)] += transform.T @ local @ transform
            member_reference.append((dofs, transform, local))

        expected_displacement = np.zeros(dof_count, dtype=np.float64)
        expected_displacement[6:] = np.linalg.solve(stiffness[6:, 6:], loads[6:])
        expected_reaction = stiffness @ expected_displacement - loads
        for dofs, transform, local in member_reference:
            expected_member_forces.append(
                local @ (transform @ expected_displacement[dofs])
            )

        np.testing.assert_allclose(
            np.ctypeslib.as_array(displacement_buffer),
            expected_displacement,
            rtol=2.0e-10,
            atol=2.0e-12,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(reaction_buffer),
            expected_reaction,
            rtol=2.0e-9,
            atol=2.0e-9,
        )
        np.testing.assert_allclose(
            np.ctypeslib.as_array(force_buffer),
            np.concatenate(expected_member_forces),
            rtol=2.0e-9,
            atol=2.0e-9,
        )
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_singular_model_fails_with_zeroed_outputs(native_library: ctypes.CDLL) -> None:
    api = _api(native_library)
    model, owners = _compile_model(
        api,
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
        assert (
            api.linear_frame3d_solve(
                model,
                loads,
                len(loads),
                ctypes.byref(result),
                None,
            )
            == STATUS_SINGULAR_SYSTEM
        )
        assert np.all(np.ctypeslib.as_array(displacements) == 0.0)
        assert np.all(np.ctypeslib.as_array(reactions) == 0.0)
        assert np.all(np.ctypeslib.as_array(forces) == 0.0)
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_reserved_section_fields_fail_closed(native_library: ctypes.CDLL) -> None:
    api = _api(native_library)
    model_input, _nodes, sections, _members, _restrained = _model_input()
    sections[0].reserved_u32 = 1
    model = ctypes.c_void_p(1)
    assert (
        api.linear_frame3d_model_compile(
            ctypes.byref(model_input),
            ctypes.byref(model),
            None,
        )
        == STATUS_INVALID_ARGUMENT
    )
    assert model.value is None
    sections[0].reserved_u32 = 0
    sections[0].area_m2 = 1.0e308
    model = ctypes.c_void_p(1)
    assert (
        api.linear_frame3d_model_compile(
            ctypes.byref(model_input),
            ctypes.byref(model),
            None,
        )
        == STATUS_INVALID_ARGUMENT
    )
    assert model.value is None


def test_nonfinite_load_fails_with_zeroed_outputs(native_library: ctypes.CDLL) -> None:
    api = _api(native_library)
    model, owners = _compile_model(api)
    assert owners
    try:
        loads = (ctypes.c_double * 12)()
        loads[7] = float("nan")
        result, displacements, reactions, forces = _result_buffers()
        for buffer in (displacements, reactions, forces):
            for index in range(12):
                buffer[index] = 9.0
        assert (
            api.linear_frame3d_solve(
                model,
                loads,
                len(loads),
                ctypes.byref(result),
                None,
            )
            == STATUS_INVALID_ARGUMENT
        )
        assert np.all(np.ctypeslib.as_array(displacements) == 0.0)
        assert np.all(np.ctypeslib.as_array(reactions) == 0.0)
        assert np.all(np.ctypeslib.as_array(forces) == 0.0)
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK


def test_invalid_and_small_output_descriptors_keep_distinct_statuses(
    native_library: ctypes.CDLL,
) -> None:
    api = _api(native_library)
    model, owners = _compile_model(api)
    assert owners
    try:
        loads = (ctypes.c_double * 12)()
        result, _displacements, _reactions, _forces = _result_buffers()
        result.member_end_force_count = 11
        assert (
            api.linear_frame3d_solve(
                model,
                loads,
                len(loads),
                ctypes.byref(result),
                None,
            )
            == STATUS_BUFFER_TOO_SMALL
        )
        result.member_end_force_count = 12
        result.reserved_u32 = 1
        assert (
            api.linear_frame3d_solve(
                model,
                loads,
                len(loads),
                ctypes.byref(result),
                None,
            )
            == STATUS_INVALID_ARGUMENT
        )
    finally:
        assert api.linear_frame3d_model_destroy(model, None) == STATUS_OK
