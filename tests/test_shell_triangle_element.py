from __future__ import annotations

import numpy as np

from structural_analysis.elements.shell_triangle import (
    recover_shell_triangle,
    shell_triangle_matrices,
)


POINTS = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


def test_shell_triangle_membrane_patch_matches_closed_form_energy() -> None:
    elastic, poisson, thickness = 30.0e9, 0.2, 0.2
    matrices = shell_triangle_matrices(
        POINTS, elastic_modulus_pa=elastic, poisson_ratio=poisson, thickness_m=thickness
    )
    eps_x, eps_y, gamma_xy = 1.0e-4, 2.0e-5, 3.0e-5
    displacement = np.zeros(18)
    for index, (x, y, _z) in enumerate(POINTS):
        displacement[6 * index] = eps_x * x + 0.5 * gamma_xy * y
        displacement[6 * index + 1] = eps_y * y + 0.5 * gamma_xy * x
    recovery = recover_shell_triangle(matrices, displacement)
    strain = np.asarray([eps_x, eps_y, gamma_xy])
    expected = 0.5 * matrices.area_m2 * float(strain @ matrices.membrane_d_n_per_m @ strain)

    np.testing.assert_allclose(recovery.membrane_strain, strain, rtol=0.0, atol=1.0e-15)
    assert abs(recovery.strain_energy_j - expected) / expected <= 1.0e-12


def test_shell_triangle_rigid_translation_and_matching_slope_are_zero_energy() -> None:
    matrices = shell_triangle_matrices(
        POINTS, elastic_modulus_pa=30.0e9, poisson_ratio=0.2, thickness_m=0.2
    )
    rigid = np.zeros(18)
    for index in range(3):
        rigid[6 * index : 6 * index + 3] = (0.2, -0.1, 0.3)
    assert abs(float(rigid @ matrices.stiffness_n_per_m @ rigid)) <= 1.0e-5

    slope = np.zeros(18)
    for index, (x, _y, _z) in enumerate(POINTS):
        slope[6 * index + 2] = 1.0e-4 * x
        slope[6 * index + 4] = 1.0e-4
    recovery = recover_shell_triangle(matrices, slope)
    assert max(abs(value) for value in recovery.transverse_shear_strain) <= 1.0e-18
    assert recovery.strain_energy_j <= 1.0e-16


def test_shell_triangle_stiffness_is_symmetric_and_positive_semidefinite() -> None:
    matrices = shell_triangle_matrices(
        POINTS, elastic_modulus_pa=30.0e9, poisson_ratio=0.2, thickness_m=0.2
    )
    np.testing.assert_array_equal(matrices.stiffness_n_per_m, matrices.stiffness_n_per_m.T)
    assert np.min(np.linalg.eigvalsh(matrices.stiffness_n_per_m)) >= -1.0e-5
