from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "native" / "cpp"


def _compile_and_run(tmp_path: Path) -> dict[str, np.ndarray]:
    compiler = shutil.which("c++")
    assert compiler is not None, "a C++20 compiler is required for the CPU oracle lane"
    executable = tmp_path / "model-ir-assembly-parity"
    sources = [
        CPP / "tests" / "assembly" / "model_ir_assembly_parity_dump.cpp",
        CPP / "src" / "model_ir" / "model_ir.cpp",
        CPP / "src" / "model_ir" / "sha256.cpp",
        CPP / "src" / "materials" / "materials.cpp",
        CPP / "src" / "elements" / "reference_elements.cpp",
        CPP / "src" / "assembly" / "dense_assembly.cpp",
        CPP / "src" / "assembly" / "model_ir_assembly.cpp",
    ]
    command = [
        compiler,
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(CPP / "include"),
        "-I",
        str(CPP / "src" / "model_ir"),
        "-I",
        str(CPP / "src" / "materials"),
        "-I",
        str(CPP / "src" / "elements"),
        "-I",
        str(CPP / "src" / "assembly"),
        "-I",
        str(CPP / "tests" / "assembly"),
        *(str(source) for source in sources),
        "-o",
        str(executable),
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    completed = subprocess.run(
        [str(executable)], cwd=ROOT, check=True, capture_output=True, text=True
    )
    parsed: dict[str, np.ndarray] = {}
    for line in completed.stdout.splitlines():
        name, *values = line.split("|")
        assert name and values and name not in parsed
        parsed[name] = np.asarray([float(value) for value in values], dtype=np.float64)
    return parsed


def _scatter(matrix: np.ndarray, indices: tuple[int, ...], values: np.ndarray) -> None:
    matrix[np.ix_(indices, indices)] += values


def _frame_response(
    displacement: np.ndarray, direction: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    youngs_modulus = 200.0
    poisson_ratio = 0.25
    shear_modulus = youngs_modulus / (2.0 * (1.0 + poisson_ratio))
    density = 1000.0
    area = 0.01
    iy = 2.0e-5
    iz = 3.0e-5
    torsional_constant = 4.0e-5
    length = 2.0
    roll = 0.2
    rotation = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(roll), np.sin(roll)],
            [0.0, -np.sin(roll), np.cos(roll)],
        ],
        dtype=np.float64,
    )
    transform = np.zeros((12, 12), dtype=np.float64)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = rotation

    local_stiffness = np.zeros((12, 12), dtype=np.float64)
    for left, right, value in (
        (0, 6, youngs_modulus * area / length),
        (3, 9, shear_modulus * torsional_constant / length),
    ):
        local_stiffness[left, left] += value
        local_stiffness[right, right] += value
        local_stiffness[left, right] -= value
        local_stiffness[right, left] -= value
    length2 = length * length
    length3 = length2 * length
    eiz = youngs_modulus * iz
    eiy = youngs_modulus * iy
    _scatter(
        local_stiffness,
        (1, 5, 7, 11),
        np.asarray(
            [
                [12 * eiz / length3, 6 * eiz / length2, -12 * eiz / length3, 6 * eiz / length2],
                [6 * eiz / length2, 4 * eiz / length, -6 * eiz / length2, 2 * eiz / length],
                [-12 * eiz / length3, -6 * eiz / length2, 12 * eiz / length3, -6 * eiz / length2],
                [6 * eiz / length2, 2 * eiz / length, -6 * eiz / length2, 4 * eiz / length],
            ]
        ),
    )
    _scatter(
        local_stiffness,
        (2, 4, 8, 10),
        np.asarray(
            [
                [12 * eiy / length3, -6 * eiy / length2, -12 * eiy / length3, -6 * eiy / length2],
                [-6 * eiy / length2, 4 * eiy / length, 6 * eiy / length2, 2 * eiy / length],
                [-12 * eiy / length3, 6 * eiy / length2, 12 * eiy / length3, 6 * eiy / length2],
                [-6 * eiy / length2, 2 * eiy / length, 6 * eiy / length2, 4 * eiy / length],
            ]
        ),
    )

    local_mass = np.zeros((12, 12), dtype=np.float64)
    total_mass = density * area * length
    _scatter(
        local_mass,
        (0, 6),
        total_mass / 6.0 * np.asarray([[2.0, 1.0], [1.0, 2.0]]),
    )
    mass_scale = total_mass / 420.0
    _scatter(
        local_mass,
        (1, 5, 7, 11),
        mass_scale
        * np.asarray(
            [
                [156.0, 22 * length, 54.0, -13 * length],
                [22 * length, 4 * length2, 13 * length, -3 * length2],
                [54.0, 13 * length, 156.0, -22 * length],
                [-13 * length, -3 * length2, -22 * length, 4 * length2],
            ]
        ),
    )
    _scatter(
        local_mass,
        (2, 4, 8, 10),
        mass_scale
        * np.asarray(
            [
                [156.0, -22 * length, 54.0, 13 * length],
                [-22 * length, 4 * length2, -13 * length, -3 * length2],
                [54.0, -13 * length, 156.0, 22 * length],
                [13 * length, -3 * length2, 22 * length, 4 * length2],
            ]
        ),
    )
    polar_mass = density * (iy + iz) * length
    _scatter(
        local_mass,
        (3, 9),
        polar_mass / 6.0 * np.asarray([[2.0, 1.0], [1.0, 2.0]]),
    )
    tangent = transform.T @ local_stiffness @ transform
    mass = transform.T @ local_mass @ transform
    return (
        tangent,
        mass,
        tangent @ displacement,
        tangent @ direction,
        local_stiffness @ (transform @ displacement),
    )


def _truss_response(
    displacement: np.ndarray, direction: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    axis = np.asarray([0.0, 1.0, 0.0])
    youngs_modulus = 200.0
    area = 0.02
    density = 1000.0
    length = 1.0
    block = youngs_modulus * area / length * np.outer(axis, axis)
    tangent = np.block([[block, -block], [-block, block]])
    mass_scale = density * area * length / 6.0
    mass = mass_scale * np.block(
        [[2.0 * np.eye(3), np.eye(3)], [np.eye(3), 2.0 * np.eye(3)]]
    )
    relative = displacement[3:] - displacement[:3]
    strain = float(relative @ axis / length)
    stress = youngs_modulus * strain
    return (
        tangent,
        mass,
        tangent @ displacement,
        tangent @ direction,
        np.asarray([strain, stress, stress * area]),
    )


def _offset_release_member_load() -> tuple[np.ndarray, np.ndarray]:
    node_i = np.asarray([0.0, 0.0, 0.0])
    node_j = np.asarray([2.0, 0.0, 0.0])
    offset_i = np.asarray([0.0, 0.2, 0.0])
    offset_j = np.asarray([0.0, -0.1, 0.1])
    chord = node_j + offset_j - node_i - offset_i
    length = float(np.linalg.norm(chord))
    x_axis = chord / length
    reference = np.asarray([0.0, 0.0, 1.0])
    y_base = np.cross(reference, x_axis)
    y_base /= np.linalg.norm(y_base)
    z_base = np.cross(x_axis, y_base)
    roll = 0.2
    y_axis = np.cos(roll) * y_base + np.sin(roll) * z_base
    z_axis = -np.sin(roll) * y_base + np.cos(roll) * z_base
    rotation = np.asarray([x_axis, y_axis, z_axis])
    block = np.zeros((12, 12), dtype=np.float64)
    for offset in (0, 3, 6, 9):
        block[offset : offset + 3, offset : offset + 3] = rotation
    rigid = np.eye(12, dtype=np.float64)
    for translation, rotational, arm in ((0, 3, offset_i), (6, 9, offset_j)):
        rigid[translation : translation + 3, rotational : rotational + 3] = np.asarray(
            [
                [0.0, arm[2], -arm[1]],
                [-arm[2], 0.0, arm[0]],
                [arm[1], -arm[0], 0.0],
            ]
        )
    base_transform = block @ rigid

    youngs_modulus = 200.0
    shear_modulus = youngs_modulus / (2.0 * (1.0 + 0.25))
    local_stiffness = np.zeros((12, 12), dtype=np.float64)
    for left, right, value in (
        (0, 6, youngs_modulus * 0.01 / length),
        (3, 9, shear_modulus * 4.0e-5 / length),
    ):
        local_stiffness[left, left] += value
        local_stiffness[right, right] += value
        local_stiffness[left, right] -= value
        local_stiffness[right, left] -= value
    length2 = length * length
    length3 = length2 * length
    eiz = youngs_modulus * 3.0e-5
    eiy = youngs_modulus * 2.0e-5
    _scatter(
        local_stiffness,
        (1, 5, 7, 11),
        np.asarray(
            [
                [12 * eiz / length3, 6 * eiz / length2, -12 * eiz / length3, 6 * eiz / length2],
                [6 * eiz / length2, 4 * eiz / length, -6 * eiz / length2, 2 * eiz / length],
                [-12 * eiz / length3, -6 * eiz / length2, 12 * eiz / length3, -6 * eiz / length2],
                [6 * eiz / length2, 2 * eiz / length, -6 * eiz / length2, 4 * eiz / length],
            ]
        ),
    )
    _scatter(
        local_stiffness,
        (2, 4, 8, 10),
        np.asarray(
            [
                [12 * eiy / length3, -6 * eiy / length2, -12 * eiy / length3, -6 * eiy / length2],
                [-6 * eiy / length2, 4 * eiy / length, 6 * eiy / length2, 2 * eiy / length],
                [-12 * eiy / length3, 6 * eiy / length2, 12 * eiy / length3, 6 * eiy / length2],
                [-6 * eiy / length2, 2 * eiy / length, 6 * eiy / length2, 4 * eiy / length],
            ]
        ),
    )
    released = np.asarray([4, 11])
    retained = np.asarray([index for index in range(12) if index not in released])
    release_transform = np.zeros((12, 12), dtype=np.float64)
    release_transform[retained, retained] = 1.0
    release_transform[np.ix_(released, retained)] = np.linalg.solve(
        local_stiffness[np.ix_(released, released)],
        -local_stiffness[np.ix_(released, retained)],
    )
    qx, qy, qz = 2.0, -3.0, 5.0
    local_equivalent = np.asarray(
        [
            qx * length / 2.0,
            qy * length / 2.0,
            qz * length / 2.0,
            0.0,
            -qz * length2 / 12.0,
            qy * length2 / 12.0,
            qx * length / 2.0,
            qy * length / 2.0,
            qz * length / 2.0,
            0.0,
            qz * length2 / 12.0,
            -qy * length2 / 12.0,
        ]
    )
    transform = release_transform @ base_transform
    return transform.T @ local_equivalent, release_transform.T @ local_equivalent


def _oracle() -> dict[str, np.ndarray]:
    displacement = np.zeros(18, dtype=np.float64)
    displacement[6:12] = np.asarray([0.001, -0.002, 0.003, 0.0004, -0.0005, 0.0006])
    displacement[13] = 0.004
    direction = np.zeros(18, dtype=np.float64)
    direction[6:12] = np.asarray([-0.003, 0.002, 0.001, -0.0002, 0.0007, -0.0004])
    direction[13] = -0.005
    frame_dofs = np.asarray([*range(0, 6), *range(6, 12)])
    truss_dofs = np.asarray([6, 7, 8, 12, 13, 14])
    frame = _frame_response(displacement[frame_dofs], direction[frame_dofs])
    truss = _truss_response(displacement[truss_dofs], direction[truss_dofs])

    tangent = np.zeros((18, 18), dtype=np.float64)
    mass = np.zeros((18, 18), dtype=np.float64)
    internal = np.zeros(18, dtype=np.float64)
    jvp = np.zeros(18, dtype=np.float64)
    pattern = np.zeros((18, 18), dtype=np.bool_)
    for dofs, response in ((frame_dofs, frame), (truss_dofs, truss)):
        tangent[np.ix_(dofs, dofs)] += response[0]
        mass[np.ix_(dofs, dofs)] += response[1]
        internal[dofs] += response[2]
        jvp[dofs] += response[3]
        pattern[np.ix_(dofs, dofs)] = True

    active = np.asarray([6, 7, 8, 9, 10, 11, 13])
    constrained = np.asarray([0, 1, 2, 3, 4, 5, 12, 14, 15, 16, 17])
    reduced_pattern = pattern[np.ix_(active, active)]
    reduced_tangent = tangent[np.ix_(active, active)]
    reduced_mass = mass[np.ix_(active, active)]
    row_offsets = [0]
    columns: list[int] = []
    tangent_values: list[float] = []
    mass_values: list[float] = []
    for row in range(active.size):
        row_columns = np.flatnonzero(reduced_pattern[row])
        columns.extend(int(column) for column in row_columns)
        tangent_values.extend(float(reduced_tangent[row, column]) for column in row_columns)
        mass_values.extend(float(reduced_mass[row, column]) for column in row_columns)
        row_offsets.append(len(columns))
    external = np.asarray([10.0, -20.0, 0.0, 0.0, 0.0, 0.0, 30.0])
    secondary = np.asarray([0.0, 0.0, 8.0, 0.0, 0.0, 0.0, 0.0])
    tertiary = np.asarray([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 16.0])
    combination_external = 1.2 * external - 0.5 * secondary
    direct_terms_external = combination_external + 0.25 * tertiary
    nested_combination_external = (
        0.5 * combination_external + 0.4 * external + 0.25 * tertiary
    )
    full_external = np.zeros(18, dtype=np.float64)
    full_external[active] = external
    full_secondary = np.zeros(18, dtype=np.float64)
    full_secondary[active] = secondary
    full_combination_external = np.zeros(18, dtype=np.float64)
    full_combination_external[active] = combination_external
    roll = 0.2
    member_rotation = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(roll), np.sin(roll)],
            [0.0, -np.sin(roll), np.cos(roll)],
        ],
        dtype=np.float64,
    )
    member_transform = np.zeros((12, 12), dtype=np.float64)
    for offset in (0, 3, 6, 9):
        member_transform[offset : offset + 3, offset : offset + 3] = member_rotation
    member_local = np.asarray(
        [
            2.0,
            -3.0,
            5.0,
            0.0,
            -5.0 / 3.0,
            -1.0,
            2.0,
            -3.0,
            5.0,
            0.0,
            5.0 / 3.0,
            1.0,
        ],
        dtype=np.float64,
    )
    member_full = np.zeros(18, dtype=np.float64)
    member_full[:12] = member_transform.T @ member_local
    member_load_full_external = full_external + member_full
    member_load_combination_full_external = (
        full_combination_external + 1.2 * member_full
    )
    full_direct_terms_external = np.zeros(18, dtype=np.float64)
    full_direct_terms_external[active] = direct_terms_external
    full_nested_combination_external = np.zeros(18, dtype=np.float64)
    full_nested_combination_external[active] = nested_combination_external
    gravity_acceleration = np.zeros(18, dtype=np.float64)
    gravity_acceleration[2::6] = -9.80665
    self_weight_full_external = full_external + mass @ gravity_acceleration
    self_weight_external = self_weight_full_external[active]
    self_weight_combination_full_external = (
        1.2 * self_weight_full_external - 0.5 * full_secondary
    )
    self_weight_combination_external = self_weight_combination_full_external[active]
    offset_release_global, offset_release_local = _offset_release_member_load()
    offset_release_full = np.zeros(18, dtype=np.float64)
    offset_release_full[:12] = offset_release_global
    return {
        "model_assembly.active_dofs": active,
        "model_assembly.row_offsets": np.asarray(row_offsets),
        "model_assembly.column_indices": np.asarray(columns),
        "model_assembly.tangent": np.asarray(tangent_values),
        "model_assembly.consistent_mass": np.asarray(mass_values),
        "model_assembly.internal_force": internal[active],
        "model_assembly.external_load": external,
        "model_assembly.equilibrium_residual": internal[active] - external,
        "model_assembly.jvp": jvp[active],
        "model_assembly.constrained_dofs": constrained,
        "model_assembly.constrained_internal_force": internal[constrained],
        "model_assembly.constrained_external_load": full_external[constrained],
        "model_assembly.reactions": internal[constrained] - full_external[constrained],
        "model_assembly.frame_recovery": frame[4],
        "model_assembly.truss_recovery": truss[4],
        "model_assembly.combination_external_load": combination_external,
        "model_assembly.combination_equilibrium_residual": internal[active]
        - combination_external,
        "model_assembly.combination_reactions": internal[constrained]
        - full_combination_external[constrained],
        "model_assembly.member_load_external_load": member_load_full_external[active],
        "model_assembly.member_load_constrained_external_load": member_load_full_external[
            constrained
        ],
        "model_assembly.member_load_reactions": internal[constrained]
        - member_load_full_external[constrained],
        "model_assembly.member_load_frame_recovery": frame[4] - member_local,
        "model_assembly.member_load_combination_external_load": member_load_combination_full_external[
            active
        ],
        "model_assembly.member_load_combination_reactions": internal[constrained]
        - member_load_combination_full_external[constrained],
        "model_assembly.member_load_combination_frame_recovery": frame[4]
        - 1.2 * member_local,
        "model_assembly.member_load_offset_release_external_delta": offset_release_full[
            active
        ],
        "model_assembly.member_load_offset_release_constrained_external_delta": offset_release_full[
            constrained
        ],
        "model_assembly.member_load_offset_release_reaction_delta": -offset_release_full[
            constrained
        ],
        "model_assembly.member_load_offset_release_recovery_delta": -offset_release_local,
        "model_assembly.self_weight_external_load": self_weight_external,
        "model_assembly.self_weight_equilibrium_residual": internal[active]
        - self_weight_external,
        "model_assembly.self_weight_reactions": internal[constrained]
        - self_weight_full_external[constrained],
        "model_assembly.self_weight_combination_external_load": self_weight_combination_external,
        "model_assembly.self_weight_combination_equilibrium_residual": internal[active]
        - self_weight_combination_external,
        "model_assembly.self_weight_combination_reactions": internal[constrained]
        - self_weight_combination_full_external[constrained],
        "model_assembly.direct_terms_external_load": direct_terms_external,
        "model_assembly.direct_terms_equilibrium_residual": internal[active]
        - direct_terms_external,
        "model_assembly.direct_terms_reactions": internal[constrained]
        - full_direct_terms_external[constrained],
        "model_assembly.nested_combination_external_load": nested_combination_external,
        "model_assembly.nested_combination_equilibrium_residual": internal[active]
        - nested_combination_external,
        "model_assembly.nested_combination_reactions": internal[constrained]
        - full_nested_combination_external[constrained],
    }


def test_typed_model_ir_mixed_graph_assembly_matches_independent_numpy_oracle(
    tmp_path: Path,
) -> None:
    actual = _compile_and_run(tmp_path)
    expected = _oracle()
    assert set(actual) == set(expected)
    for key, values in expected.items():
        np.testing.assert_allclose(
            actual[key], values, rtol=1.0e-13, atol=1.0e-14, err_msg=key
        )
