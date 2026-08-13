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
    executable = tmp_path / "reference-elements-parity"
    sources = [
        CPP / "tests" / "elements" / "reference_elements_parity_dump.cpp",
        CPP / "src" / "materials" / "materials.cpp",
        CPP / "src" / "elements" / "reference_elements.cpp",
        CPP / "src" / "assembly" / "dense_assembly.cpp",
    ]
    command = [
        compiler,
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(CPP / "src" / "materials"),
        "-I",
        str(CPP / "src" / "elements"),
        "-I",
        str(CPP / "src" / "assembly"),
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


def _normalize(vector: np.ndarray) -> np.ndarray:
    magnitude = np.linalg.norm(vector)
    assert np.isfinite(magnitude) and magnitude > 1.0e-12
    return vector / magnitude


def _reduced_csr_assembly_oracle() -> dict[str, np.ndarray]:
    contributions = [
        (
            20,
            np.asarray([1, 2]),
            np.asarray([[4.0, -4.0], [-4.0, 4.0]]),
            np.asarray([[2.0, 1.0], [1.0, 2.0]]),
            np.asarray([8.0, -8.0]),
            np.asarray([12.0, -12.0]),
        ),
        (
            10,
            np.asarray([0, 1]),
            np.asarray([[3.0, -3.0], [-3.0, 3.0]]),
            np.asarray([[6.0, 3.0], [3.0, 6.0]]),
            np.asarray([6.0, -6.0]),
            np.asarray([9.0, -9.0]),
        ),
        (
            30,
            np.asarray([2, 3]),
            np.asarray([[5.0, -5.0], [-5.0, 5.0]]),
            np.asarray([[10.0, 4.0], [4.0, 10.0]]),
            np.asarray([7.0, -7.0]),
            np.asarray([11.0, -11.0]),
        ),
    ]
    tangent = np.zeros((4, 4), dtype=np.float64)
    mass = np.zeros((4, 4), dtype=np.float64)
    residual = np.zeros(4, dtype=np.float64)
    jvp = np.zeros(4, dtype=np.float64)
    pattern = np.zeros((4, 4), dtype=np.bool_)
    for _, dofs, local_tangent, local_mass, local_residual, local_jvp in sorted(
        contributions, key=lambda contribution: contribution[0]
    ):
        tangent[np.ix_(dofs, dofs)] += local_tangent
        mass[np.ix_(dofs, dofs)] += local_mass
        residual[dofs] += local_residual
        jvp[dofs] += local_jvp
        pattern[np.ix_(dofs, dofs)] = True

    active = np.asarray([1, 2, 3])
    reduced_pattern = pattern[np.ix_(active, active)]
    reduced_tangent = tangent[np.ix_(active, active)]
    reduced_mass = mass[np.ix_(active, active)]
    row_offsets = [0]
    column_indices: list[int] = []
    tangent_values: list[float] = []
    mass_values: list[float] = []
    for row in range(active.size):
        columns = np.flatnonzero(reduced_pattern[row])
        column_indices.extend(int(column) for column in columns)
        tangent_values.extend(float(reduced_tangent[row, column]) for column in columns)
        mass_values.extend(float(reduced_mass[row, column]) for column in columns)
        row_offsets.append(len(column_indices))
    return {
        "assembly_csr.active_dofs": active,
        "assembly_csr.row_offsets": np.asarray(row_offsets),
        "assembly_csr.column_indices": np.asarray(column_indices),
        "assembly_csr.tangent": np.asarray(tangent_values),
        "assembly_csr.consistent_mass": np.asarray(mass_values),
        "assembly_csr.residual": residual[active],
        "assembly_csr.jvp": jvp[active],
    }


def _frame_oracle_for(
    node_i: np.ndarray,
    node_j: np.ndarray,
    roll_rad: float,
    displacement: np.ndarray,
    direction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    e = 200.0
    nu = 0.25
    g = e / (2.0 * (1.0 + nu))
    density = 1000.0
    area = 0.01
    iy = 2.0e-5
    iz = 3.0e-5
    torsion_constant = 4.0e-5
    x_axis = _normalize(node_j - node_i)
    reference = np.asarray([0.0, 0.0, 1.0])
    if abs(np.dot(x_axis, reference)) > 0.95:
        reference = np.asarray([0.0, 1.0, 0.0])
    y_base = _normalize(np.cross(reference, x_axis))
    z_base = _normalize(np.cross(x_axis, y_base))
    y_axis = np.cos(roll_rad) * y_base + np.sin(roll_rad) * z_base
    z_axis = -np.sin(roll_rad) * y_base + np.cos(roll_rad) * z_base
    rotation = np.vstack((x_axis, y_axis, z_axis))
    transform = np.zeros((12, 12), dtype=np.float64)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = rotation
    length = np.linalg.norm(node_j - node_i)
    stiffness = np.zeros((12, 12), dtype=np.float64)
    for left, right, value in (
        (0, 6, e * area / length),
        (3, 9, g * torsion_constant / length),
    ):
        stiffness[left, left] += value
        stiffness[right, right] += value
        stiffness[left, right] -= value
        stiffness[right, left] -= value
    eiz = e * iz
    eiy = e * iy
    l2 = length * length
    l3 = l2 * length
    bending_z = np.asarray(
        [
            [12 * eiz / l3, 6 * eiz / l2, -12 * eiz / l3, 6 * eiz / l2],
            [6 * eiz / l2, 4 * eiz / length, -6 * eiz / l2, 2 * eiz / length],
            [-12 * eiz / l3, -6 * eiz / l2, 12 * eiz / l3, -6 * eiz / l2],
            [6 * eiz / l2, 2 * eiz / length, -6 * eiz / l2, 4 * eiz / length],
        ]
    )
    bending_y = np.asarray(
        [
            [12 * eiy / l3, -6 * eiy / l2, -12 * eiy / l3, -6 * eiy / l2],
            [-6 * eiy / l2, 4 * eiy / length, 6 * eiy / l2, 2 * eiy / length],
            [-12 * eiy / l3, 6 * eiy / l2, 12 * eiy / l3, 6 * eiy / l2],
            [-6 * eiy / l2, 2 * eiy / length, 6 * eiy / l2, 4 * eiy / length],
        ]
    )
    _scatter(stiffness, (1, 5, 7, 11), bending_z)
    _scatter(stiffness, (2, 4, 8, 10), bending_y)

    mass = np.zeros((12, 12), dtype=np.float64)
    total_mass = density * area * length
    _scatter(mass, (0, 6), total_mass / 6.0 * np.asarray([[2.0, 1.0], [1.0, 2.0]]))
    scale = total_mass / 420.0
    _scatter(
        mass,
        (1, 5, 7, 11),
        scale
        * np.asarray(
            [
                [156.0, 22 * length, 54.0, -13 * length],
                [22 * length, 4 * l2, 13 * length, -3 * l2],
                [54.0, 13 * length, 156.0, -22 * length],
                [-13 * length, -3 * l2, -22 * length, 4 * l2],
            ]
        ),
    )
    _scatter(
        mass,
        (2, 4, 8, 10),
        scale
        * np.asarray(
            [
                [156.0, -22 * length, 54.0, 13 * length],
                [-22 * length, 4 * l2, -13 * length, -3 * l2],
                [54.0, -13 * length, 156.0, 22 * length],
                [13 * length, -3 * l2, 22 * length, 4 * l2],
            ]
        ),
    )
    polar_mass = density * (iy + iz) * length
    _scatter(mass, (3, 9), polar_mass / 6.0 * np.asarray([[2.0, 1.0], [1.0, 2.0]]))
    global_stiffness = transform.T @ stiffness @ transform
    global_mass = transform.T @ mass @ transform
    local_displacement = transform @ displacement
    return (
        global_stiffness,
        global_mass,
        global_stiffness @ displacement,
        global_stiffness @ direction,
        stiffness @ local_displacement,
    )


def _frame_oracle() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return _frame_oracle_for(
        np.asarray([0.0, 0.0, 0.0]),
        np.asarray([2.0, 0.0, 0.0]),
        0.0,
        np.asarray(
            [0, 0, 0, 0, 0, 0, 0.001, 0.002, -0.003, 0.004, -0.005, 0.006],
            dtype=np.float64,
        ),
        np.arange(1.0, 13.0, dtype=np.float64),
    )


def _shell_oracle_for(
    nodes: np.ndarray,
    displacement: np.ndarray,
    direction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    e = 200.0
    nu = 0.25
    density = 1000.0
    thickness = 0.1
    edge_12 = nodes[1] - nodes[0]
    edge_13 = nodes[2] - nodes[0]
    local_x = _normalize(edge_12)
    local_z = _normalize(np.cross(edge_12, edge_13))
    local_y = _normalize(np.cross(local_z, local_x))
    x2 = np.linalg.norm(edge_12)
    x3 = np.dot(edge_13, local_x)
    y3 = np.dot(edge_13, local_y)
    double_area = x2 * y3
    assert double_area > 1.0e-12
    area = 0.5 * double_area
    b = np.asarray(
        [
            [-y3 / double_area, 0.0, y3 / double_area, 0.0, 0.0, 0.0],
            [0.0, (x3 - x2) / double_area, 0.0, -x3 / double_area, 0.0, x2 / double_area],
            [
                (x3 - x2) / double_area,
                -y3 / double_area,
                -x3 / double_area,
                y3 / double_area,
                x2 / double_area,
                0.0,
            ],
        ]
    )
    d = e / (1.0 - nu * nu) * np.asarray(
        [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]]
    )
    transform = np.zeros((6, 9), dtype=np.float64)
    for node in range(3):
        transform[2 * node, 3 * node : 3 * node + 3] = local_x
        transform[2 * node + 1, 3 * node : 3 * node + 3] = local_y
    local_stiffness = thickness * area * b.T @ d @ b
    stiffness = transform.T @ local_stiffness @ transform
    local_mass = np.zeros((6, 6), dtype=np.float64)
    mass_scale = density * thickness * area / 12.0
    for row_node in range(3):
        for column_node in range(3):
            factor = 2.0 if row_node == column_node else 1.0
            for component in range(2):
                local_mass[2 * row_node + component, 2 * column_node + component] = (
                    factor * mass_scale
                )
    mass = transform.T @ local_mass @ transform
    strain = b @ transform @ displacement
    stress = d @ strain
    return stiffness, mass, stiffness @ displacement, stiffness @ direction, np.r_[strain, stress]


def _shell_oracle() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return _shell_oracle_for(
        np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        np.asarray([0, 0, 0, 0.002, 0, 0, 0, 0.001, 0], dtype=np.float64),
        np.asarray([0, 0, 1, 0, 0, 2, 0, 0, 3], dtype=np.float64),
    )


def test_reference_material_element_and_assembly_cpp_match_independent_numpy_oracle(
    tmp_path: Path,
) -> None:
    actual = _compile_and_run(tmp_path)
    expected_keys = {
        "material.shear_modulus",
        "material.plastic_trial",
        "material.committed",
        *(f"{kind}.{field}" for kind in (
            "truss", "frame", "frame_rotated", "shell", "shell_rotated"
        ) for field in (
            "tangent", "consistent_mass", "residual", "jvp", "recovery"
        )),
        "assembly.tangent",
        "assembly.consistent_mass",
        "assembly.residual",
        "assembly.jvp",
        "assembly_csr.active_dofs",
        "assembly_csr.row_offsets",
        "assembly_csr.column_indices",
        "assembly_csr.tangent",
        "assembly_csr.consistent_mass",
        "assembly_csr.residual",
        "assembly_csr.jvp",
    }
    assert set(actual) == expected_keys
    expected: dict[str, np.ndarray] = {
        "material.shear_modulus": np.asarray([80.0]),
        "material.plastic_trial": np.asarray([0.02, 2.2, 20.0, 0.009, 0.009, 1.0, 1.0]),
        "material.committed": np.asarray([1.0, 0.009, 0.009]),
    }
    truss_axis = np.asarray([1.0, 0.0, 0.0])
    truss_block = np.outer(truss_axis, truss_axis)
    truss_stiffness = np.block([[truss_block, -truss_block], [-truss_block, truss_block]])
    truss_mass = 20.0 / 6.0 * np.block(
        [[2.0 * np.eye(3), np.eye(3)], [np.eye(3), 2.0 * np.eye(3)]]
    )
    truss_displacement = np.asarray([0, 0, 0, 0.002, 0, 0], dtype=np.float64)
    truss_direction = np.asarray([0, 0, 0, 1, 0, 0], dtype=np.float64)
    expected.update(
        {
            "truss.tangent": truss_stiffness.ravel(),
            "truss.consistent_mass": truss_mass.ravel(),
            "truss.residual": truss_stiffness @ truss_displacement,
            "truss.jvp": truss_stiffness @ truss_direction,
            "truss.recovery": np.asarray([0.001, 0.2, 0.002]),
        }
    )
    for prefix, oracle in (("frame", _frame_oracle()), ("shell", _shell_oracle())):
        for field, values in zip(
            ("tangent", "consistent_mass", "residual", "jvp", "recovery"), oracle
        ):
            expected[f"{prefix}.{field}"] = values.ravel()
    rotated_frame = _frame_oracle_for(
        np.asarray([1.0, -2.0, 0.5]),
        np.asarray([3.0, 1.0, 4.5]),
        0.37,
        np.asarray(
            [0.001, -0.002, 0.003, -0.004, 0.005, -0.006,
             0.007, -0.008, 0.009, -0.010, 0.011, -0.012],
            dtype=np.float64,
        ),
        np.asarray(
            [-6.0, 5.0, -4.0, 3.0, -2.0, 1.0,
             0.5, -1.5, 2.5, -3.5, 4.5, -5.5],
            dtype=np.float64,
        ),
    )
    rotated_shell = _shell_oracle_for(
        np.asarray([[1.0, -1.0, 0.5], [3.0, 0.0, 2.5], [0.0, 1.0, 3.5]]),
        np.asarray(
            [0.001, -0.002, 0.003, -0.004, 0.005, -0.006, 0.007, -0.008, 0.009],
            dtype=np.float64,
        ),
        np.asarray([-1.0, 2.0, -3.0, 4.0, -5.0, 6.0, -7.0, 8.0, -9.0]),
    )
    for prefix, oracle in (
        ("frame_rotated", rotated_frame),
        ("shell_rotated", rotated_shell),
    ):
        for field, values in zip(
            ("tangent", "consistent_mass", "residual", "jvp", "recovery"), oracle
        ):
            expected[f"{prefix}.{field}"] = values.ravel()
    expected.update(
        {
            "assembly.tangent": np.asarray([[3, -3, 0], [-3, 7, -4], [0, -4, 4]]).ravel(),
            "assembly.consistent_mass": np.asarray([[6, 3, 0], [3, 8, 1], [0, 1, 2]]).ravel(),
            "assembly.residual": np.asarray([6, 2, -8]),
            "assembly.jvp": np.asarray([9, 3, -12]),
        }
    )
    expected.update(_reduced_csr_assembly_oracle())
    for key, values in expected.items():
        np.testing.assert_allclose(actual[key], values, rtol=1.0e-13, atol=1.0e-14, err_msg=key)
