from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (  # noqa: E402
    CPU_REFERENCE_OPERATOR_VERSION,
    assemble_linear_static_operator,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    ELEMENT_FORMULATION_CODES,
    ELEMENT_TYPE_CODES,
    MATERIAL_LAW_CODES,
    SECTION_FAMILY_CODES,
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.elements.linear_frame_truss_v1 import (  # noqa: E402
    LINEAR_FRAME_TRUSS_ELEMENT_SEMANTICS_VERSION_V1,
    LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1,
    LINEAR_FRAME_TRUSS_REFERENCE_AXIS_POLICY_V1,
    REFERENCE_AXIS_SWITCH_THRESHOLD_V1,
    LinearFrameTrussV1Error,
    frame_local_stiffness_v1,
    frame_reference_axis_v1,
    frame_transform_v1,
    truss_local_stiffness_v1,
    validate_linear_frame_truss_references_v1,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402


FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
MATERIAL = np.array([210.0e9, 0.3, 7_850.0], dtype="<f8")
FRAME_SECTION = np.array([0.02, 8.0e-5, 5.0e-5, 2.0e-5, 0.015, 0.016], dtype="<f8")
TRUSS_SECTION = np.array([0.02, 0.0, 0.0, 0.0, 0.0, 0.0], dtype="<f8")
LENGTH_M = 2.5


def _valid_reference_arrays() -> dict[str, np.ndarray]:
    return {
        "coordinates": np.array([[0.0, 0.0, 0.0], [LENGTH_M, 0.0, 0.0]], dtype="<f8"),
        "connectivity": np.array([[0, 1]], dtype="<i4"),
        "element_types": np.array([ELEMENT_TYPE_CODES["frame_3d"]], dtype="u1"),
        "formulations": np.array(
            [ELEMENT_FORMULATION_CODES["euler_bernoulli_3d"]], dtype="u1"
        ),
        "material_indices": np.array([0], dtype="<i4"),
        "section_indices": np.array([0], dtype="<i4"),
        "material_laws": np.array(
            [MATERIAL_LAW_CODES["linear_elastic_isotropic"]], dtype="u1"
        ),
        "materials": MATERIAL.reshape(1, 3),
        "section_families": np.array([SECTION_FAMILY_CODES["frame_3d"]], dtype="u1"),
        "sections": FRAME_SECTION.reshape(1, 6),
    }


def _expected_frame_stiffness() -> np.ndarray:
    elastic_modulus, poisson_ratio, _ = MATERIAL
    area, iy, iz, torsion, _, _ = FRAME_SECTION
    shear_modulus = elastic_modulus / (2.0 * (1.0 + poisson_ratio))
    expected = np.zeros((12, 12), dtype="<f8")

    def add_pair(start: int, end: int, value: float) -> None:
        expected[start, start] += value
        expected[start, end] -= value
        expected[end, start] -= value
        expected[end, end] += value

    def add_bending(
        dofs: tuple[int, int, int, int], rigidity: float, rotation_sign: float
    ) -> None:
        length_squared = LENGTH_M * LENGTH_M
        block = (rigidity / LENGTH_M**3) * np.array(
            [
                [12.0, 6.0 * LENGTH_M, -12.0, 6.0 * LENGTH_M],
                [
                    6.0 * LENGTH_M,
                    4.0 * length_squared,
                    -6.0 * LENGTH_M,
                    2.0 * length_squared,
                ],
                [-12.0, -6.0 * LENGTH_M, 12.0, -6.0 * LENGTH_M],
                [
                    6.0 * LENGTH_M,
                    2.0 * length_squared,
                    -6.0 * LENGTH_M,
                    4.0 * length_squared,
                ],
            ],
            dtype="<f8",
        )
        if rotation_sign < 0.0:
            signs = np.diag([1.0, -1.0, 1.0, -1.0])
            block = signs @ block @ signs
        expected[np.ix_(dofs, dofs)] += block

    add_pair(0, 6, elastic_modulus * area / LENGTH_M)
    add_pair(3, 9, shear_modulus * torsion / LENGTH_M)
    add_bending((1, 5, 7, 11), elastic_modulus * iz, 1.0)
    add_bending((2, 4, 8, 10), elastic_modulus * iy, -1.0)
    return expected


def _assert_error(
    call,
    *,
    code: str,
    path: str,
) -> None:
    with pytest.raises(LinearFrameTrussV1Error) as captured:
        call()
    assert captured.value.code == code
    assert captured.value.path == path
    assert captured.value.message
    assert code in str(captured.value)
    assert path in str(captured.value)


def test_public_contract_versions_preserve_the_frozen_operator_identity() -> None:
    assert LINEAR_FRAME_TRUSS_ELEMENT_SEMANTICS_VERSION_V1.endswith(".v1")
    assert isinstance(LINEAR_FRAME_TRUSS_REFERENCE_AXIS_POLICY_V1, str)
    assert LINEAR_FRAME_TRUSS_REFERENCE_AXIS_POLICY_V1
    assert LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1 == (
        CPU_REFERENCE_OPERATOR_VERSION
    )
    assert REFERENCE_AXIS_SWITCH_THRESHOLD_V1 == 0.9


def test_frame_and_truss_local_stiffness_match_independent_analytic_formulas() -> None:
    frame = frame_local_stiffness_v1(MATERIAL, FRAME_SECTION, LENGTH_M)
    truss = truss_local_stiffness_v1(MATERIAL, TRUSS_SECTION, LENGTH_M)

    assert frame.shape == (12, 12)
    assert truss.shape == (12, 12)
    assert frame.dtype.str == "<f8"
    assert truss.dtype.str == "<f8"
    np.testing.assert_allclose(
        frame, _expected_frame_stiffness(), rtol=2.0e-15, atol=0.0
    )

    expected_truss = np.zeros((12, 12), dtype="<f8")
    axial = MATERIAL[0] * TRUSS_SECTION[0] / LENGTH_M
    expected_truss[np.ix_((0, 6), (0, 6))] = ((axial, -axial), (-axial, axial))
    np.testing.assert_array_equal(truss, expected_truss)


def test_frame_stiffness_is_symmetric_psd_and_has_six_rigid_body_modes() -> None:
    stiffness = frame_local_stiffness_v1(MATERIAL, FRAME_SECTION, LENGTH_M)
    np.testing.assert_array_equal(stiffness, stiffness.T)
    eigenvalues = np.linalg.eigvalsh(stiffness)
    scale = float(np.max(np.abs(eigenvalues)))
    assert float(np.min(eigenvalues)) >= -1.0e-14 * scale
    assert np.count_nonzero(eigenvalues > 1.0e-10 * scale) == 6

    rigid_modes = []
    for component in range(4):
        mode = np.zeros(12, dtype="<f8")
        mode[component] = mode[6 + component] = 1.0
        rigid_modes.append(mode)
    rz_mode = np.zeros(12, dtype="<f8")
    rz_mode[[5, 7, 11]] = (1.0, LENGTH_M, 1.0)
    rigid_modes.append(rz_mode)
    ry_mode = np.zeros(12, dtype="<f8")
    ry_mode[[4, 8, 10]] = (-1.0, LENGTH_M, -1.0)
    rigid_modes.append(ry_mode)
    for mode in rigid_modes:
        np.testing.assert_allclose(stiffness @ mode, 0.0, rtol=0.0, atol=1.0e-8)

    generator = np.random.default_rng(20260715)
    for vector in generator.standard_normal((16, 12)):
        energy = float(vector @ stiffness @ vector)
        assert energy >= -1.0e-14 * scale * float(vector @ vector)


def test_reference_axis_switch_is_strictly_greater_than_point_nine() -> None:
    start = np.zeros(3, dtype="<f8")
    at_threshold = np.array(
        [math.sqrt(1.0 - REFERENCE_AXIS_SWITCH_THRESHOLD_V1**2), 0.0, 0.9],
        dtype="<f8",
    )
    above_z = np.nextafter(0.9, 1.0)
    above_threshold = np.array([math.sqrt(1.0 - above_z**2), 0.0, above_z], dtype="<f8")
    below_z = np.nextafter(-0.9, -1.0)
    below_negative_threshold = np.array(
        [math.sqrt(1.0 - below_z**2), 0.0, below_z], dtype="<f8"
    )

    assert frame_reference_axis_v1(start, at_threshold) == "global_z"
    assert frame_reference_axis_v1(start, above_threshold) == "global_y"
    assert frame_reference_axis_v1(start, -at_threshold) == "global_z"
    assert frame_reference_axis_v1(start, below_negative_threshold) == "global_y"


def test_rolled_transform_is_block_orthonormal_and_right_handed() -> None:
    transform, length = frame_transform_v1(
        np.zeros(3, dtype="<f8"),
        np.array([LENGTH_M, 0.0, 0.0], dtype="<f8"),
        math.pi / 2.0,
    )
    assert length == pytest.approx(LENGTH_M, rel=0.0, abs=0.0)
    assert transform.shape == (12, 12)
    assert transform.dtype.str == "<f8"
    np.testing.assert_allclose(
        transform @ transform.T, np.eye(12), rtol=0.0, atol=1.0e-15
    )
    expected_rotation = np.array(
        [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]], dtype="<f8"
    )
    for offset in (0, 3, 6, 9):
        np.testing.assert_allclose(
            transform[offset : offset + 3, offset : offset + 3],
            expected_rotation,
            rtol=0.0,
            atol=1.0e-15,
        )
    assert float(np.linalg.det(transform[:3, :3])) > 0.0


def test_oblique_nonzero_roll_transform_preserves_the_pre_refactor_golden_bytes() -> (
    None
):
    transform, length = frame_transform_v1(
        np.zeros(3, dtype="<f8"),
        np.array([1.0, 2.0, 3.0], dtype="<f8"),
        0.37,
    )

    assert length == 3.7416573867739413
    assert hashlib.sha256(transform.tobytes(order="C")).hexdigest() == (
        "59c577beacb65f5bb3526f07d149d008119c33905a01b0609399d9e43137bc41"
    )


@pytest.mark.parametrize(
    ("call", "code", "path"),
    [
        (
            lambda: frame_transform_v1(
                np.zeros(2, dtype="<f8"), np.ones(3, dtype="<f8"), 0.0
            ),
            "linear_frame_truss_input_shape_invalid",
            "/start_m",
        ),
        (
            lambda: frame_transform_v1(
                np.zeros(3, dtype="<f8"),
                np.array([1.0, np.nan, 0.0], dtype="<f8"),
                0.0,
            ),
            "linear_frame_truss_input_non_finite",
            "/end_m",
        ),
        (
            lambda: frame_transform_v1(
                np.zeros(3, dtype="<f8"), np.zeros(3, dtype="<f8"), 0.0
            ),
            "linear_frame_truss_zero_length_element",
            "/geometry",
        ),
        (
            lambda: frame_transform_v1(
                np.zeros(3, dtype="<f8"), np.ones(3, dtype="<f8"), math.inf
            ),
            "linear_frame_truss_input_non_finite",
            "/roll_rad",
        ),
        (
            lambda: frame_local_stiffness_v1(MATERIAL[:2], FRAME_SECTION, LENGTH_M),
            "linear_frame_truss_input_shape_invalid",
            "/material_properties_si",
        ),
        (
            lambda: frame_local_stiffness_v1(MATERIAL, FRAME_SECTION, float("nan")),
            "linear_frame_truss_input_non_finite",
            "/length_m",
        ),
        (
            lambda: frame_local_stiffness_v1(MATERIAL, FRAME_SECTION, 1.0e-13),
            "linear_frame_truss_zero_length_element",
            "/length_m",
        ),
        (
            lambda: frame_local_stiffness_v1(
                np.array([-1.0, 0.3, 1.0], dtype="<f8"), FRAME_SECTION, LENGTH_M
            ),
            "linear_frame_truss_material_properties_invalid",
            "/material_properties_si",
        ),
        (
            lambda: frame_local_stiffness_v1(
                MATERIAL, np.array([0.02, 1.0, 1.0, 1.0, 1.0, -1.0]), LENGTH_M
            ),
            "linear_frame_truss_section_properties_invalid",
            "/section_properties_si",
        ),
        (
            lambda: truss_local_stiffness_v1(MATERIAL, FRAME_SECTION, LENGTH_M),
            "linear_frame_truss_section_properties_invalid",
            "/section_properties_si",
        ),
    ],
)
def test_direct_formula_inputs_fail_closed(call, code: str, path: str) -> None:
    _assert_error(call, code=code, path=path)


def test_reference_validator_accepts_the_canonical_frame_and_truss_contracts() -> None:
    frame = _valid_reference_arrays()
    validate_linear_frame_truss_references_v1(**frame)

    truss = _valid_reference_arrays()
    truss["element_types"] = np.array([ELEMENT_TYPE_CODES["truss_3d"]], dtype="u1")
    truss["formulations"] = np.array(
        [ELEMENT_FORMULATION_CODES["linear_truss_3d"]], dtype="u1"
    )
    truss["section_families"] = np.array([SECTION_FAMILY_CODES["truss_3d"]], dtype="u1")
    truss["sections"] = TRUSS_SECTION.reshape(1, 6)
    validate_linear_frame_truss_references_v1(**truss)


@pytest.mark.parametrize(
    ("update", "code", "path"),
    [
        (
            {"connectivity": np.array([[0, 2]], dtype="<i4")},
            "linear_frame_truss_connectivity_out_of_range",
            "/element_connectivity/0",
        ),
        (
            {"connectivity": np.array([[1, 1]], dtype="<i4")},
            "linear_frame_truss_connectivity_invalid",
            "/element_connectivity/0",
        ),
        (
            {"material_indices": np.array([1], dtype="<i4")},
            "linear_frame_truss_material_index_out_of_range",
            "/element_material_index/0",
        ),
        (
            {"section_indices": np.array([1], dtype="<i4")},
            "linear_frame_truss_section_index_out_of_range",
            "/element_section_index/0",
        ),
        (
            {"material_laws": np.array([255], dtype="u1")},
            "linear_frame_truss_material_law_not_supported",
            "/material_law_code/0",
        ),
        (
            {"formulations": np.array([255], dtype="u1")},
            "linear_frame_truss_formulation_not_supported",
            "/elements/0/formulation",
        ),
        (
            {
                "section_families": np.array(
                    [SECTION_FAMILY_CODES["truss_3d"]], dtype="u1"
                )
            },
            "linear_frame_truss_section_family_mismatch",
            "/section_family_code/0",
        ),
        (
            {"element_types": np.array([255], dtype="u1")},
            "linear_frame_truss_element_type_not_supported",
            "/elements/0/type",
        ),
    ],
)
def test_reference_validator_rejects_invalid_references_and_code_mismatches(
    update: dict[str, np.ndarray], code: str, path: str
) -> None:
    arrays = _valid_reference_arrays()
    arrays.update(update)
    _assert_error(
        lambda: validate_linear_frame_truss_references_v1(**arrays),
        code=code,
        path=path,
    )


@pytest.mark.parametrize(
    ("update", "code", "path"),
    [
        (
            {"coordinates": np.zeros((2, 2), dtype="<f8")},
            "linear_frame_truss_input_shape_invalid",
            "/node_coordinates_m",
        ),
        (
            {"connectivity": np.array([[0.0, 1.0]], dtype="<f8")},
            "linear_frame_truss_input_dtype_invalid",
            "/element_connectivity",
        ),
        (
            {"materials": np.array([[210.0e9, np.inf, 7_850.0]], dtype="<f8")},
            "linear_frame_truss_input_non_finite",
            "/material_properties_si",
        ),
        (
            {"sections": np.zeros((1, 5), dtype="<f8")},
            "linear_frame_truss_input_shape_invalid",
            "/section_properties_si",
        ),
    ],
)
def test_reference_validator_rejects_shape_dtype_and_non_finite_inputs(
    update: dict[str, np.ndarray], code: str, path: str
) -> None:
    arrays = _valid_reference_arrays()
    arrays.update(update)
    _assert_error(
        lambda: validate_linear_frame_truss_references_v1(**arrays),
        code=code,
        path=path,
    )


def test_shared_source_preserves_cpu_and_sparse_plan_element_bytes_and_hashes() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )
    cpu = assemble_linear_static_operator(buffers)
    plan = compile_execution_plan_v2(buffers)
    expected_transforms = np.stack(
        [operator.transform_global_to_local for operator in cpu.element_operators]
    )
    expected_stiffness = np.stack(
        [operator.stiffness_local for operator in cpu.element_operators]
    )

    assert plan.source_element_operator_version == (
        LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1
    )
    assert cpu.version == LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1
    assert plan.array("recovery_transform_global_to_local").tobytes(order="C") == (
        expected_transforms.tobytes(order="C")
    )
    assert plan.array("recovery_stiffness_local").tobytes(order="C") == (
        expected_stiffness.tobytes(order="C")
    )
    assert cpu.operator_hash == (
        "sha256:168d0efd580683580afe44d66849c501e7e5ae6c0cc19dadce899890f5a27ca8"
    )
    assert plan.numeric_snapshot_hash == (
        "sha256:73aedc35e01fe2a2e5982b2646f13a2ca986a10566a889e023b7e2f1ee707658"
    )
    assert plan.recovery_operator_hash == (
        "sha256:48af8d0e448dd5e0f814bd056491251132ae08d1a8d13a92ea330a0fb5908b00"
    )
    assert plan.plan_hash == (
        "sha256:ba0def8d9b29b65d387dbda87c5048df0e818939292ede8cc26ede08f566020d"
    )
