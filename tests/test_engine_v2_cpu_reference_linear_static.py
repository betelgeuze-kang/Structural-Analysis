from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import MappingProxyType

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    CPUReferenceError,
    SolverModelBuffers,
    assemble_linear_static_operator,
    pack_solver_model_buffers,
    solve_linear_static,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    _artifact_hash,
    _descriptor,
    _numeric_buffer_hash,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
EXPECTED = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.expected.json"
DOF_INDEX = {name: index for index, name in enumerate(("UX", "UY", "UZ", "RX", "RY", "RZ"))}
REACTION_INDEX = {name: index for index, name in enumerate(("FX", "FY", "FZ", "MX", "MY", "MZ"))}


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _truss_payload() -> dict:
    payload = _payload()
    payload["sections"][0]["family_id"] = "truss_3d"
    payload["sections"][0]["parameters"] = {"area_m2": 0.02}
    element = payload["elements"][0]
    element["type"] = "truss_3d"
    element["formulation"] = "linear_truss_3d"
    element.pop("local_axis_rotation_rad")
    element.pop("releases")
    payload["constraints"].append(
        {
            "id": "BC2",
            "index": 1,
            "type": "fixed_dofs",
            "node_id": "N2",
            "dofs": ["UY", "UZ", "RX", "RY", "RZ"],
            "prescribed_values_si": {},
            "source_id": "generated:BC2",
            "extensions": {},
        }
    )
    return payload


def _immutable_array(value: np.ndarray) -> np.ndarray:
    contiguous = np.ascontiguousarray(value)
    return np.frombuffer(contiguous.tobytes(order="C"), dtype=contiguous.dtype).reshape(
        contiguous.shape
    )


def _forge_buffer_array(
    buffers: SolverModelBuffers,
    name: str,
    value: np.ndarray,
    *,
    refresh_descriptor: bool,
    refresh_numeric_hash: bool,
) -> SolverModelBuffers:
    forged_array = _immutable_array(value)
    arrays = dict(buffers._arrays)
    arrays[name] = forged_array
    descriptors = list(buffers.descriptors)
    if refresh_descriptor:
        descriptor_index = next(
            index for index, descriptor in enumerate(descriptors) if descriptor.name == name
        )
        descriptors[descriptor_index] = _descriptor(name, forged_array)
    descriptor_tuple = tuple(descriptors)
    numeric_hash = buffers.numeric_buffer_hash
    artifact_hash = buffers.artifact_hash
    if refresh_numeric_hash:
        numeric_hash = _numeric_buffer_hash(descriptor_tuple, buffers.code_tables)
        artifact_hash = _artifact_hash(
            model_ir_content_hash=buffers.model_ir_content_hash,
            load_pattern_id=buffers.load_pattern_id,
            numeric_buffer_hash=numeric_hash,
            entity_mapping_hash=buffers.entity_mapping_hash,
        )
    return replace(
        buffers,
        descriptors=descriptor_tuple,
        numeric_buffer_hash=numeric_hash,
        artifact_hash=artifact_hash,
        _arrays=MappingProxyType(arrays),
    )


@pytest.mark.parametrize("case_id", ["LC_AXIAL", "LC_WEAK", "LC_STRONG", "LC_TORSION"])
def test_dense_and_sparse_cpu_reference_match_analytic_cantilever_modes(case_id: str) -> None:
    expected_file = json.loads(EXPECTED.read_text(encoding="utf-8"))
    expected = expected_file["cases"][case_id]
    buffers = pack_solver_model_buffers(load_model_ir_v2(FIXTURE), load_pattern_id=case_id)
    dense = solve_linear_static(buffers, matrix_backend="dense")
    sparse = solve_linear_static(buffers, matrix_backend="scipy_sparse")
    atol = float(expected_file["absolute_tolerance"])
    rtol = float(expected_file["relative_tolerance"])

    assert dense.status == "ready"
    assert sparse.status == "ready"
    assert dense.operator_version == expected_file["operator_version"]
    assert dense.solver_buffer_hash == buffers.numeric_buffer_hash
    assert sparse.solver_buffer_hash == buffers.numeric_buffer_hash
    assert dense.operator_hash == sparse.operator_hash
    np.testing.assert_allclose(dense.displacements_si, sparse.displacements_si, rtol=rtol, atol=atol)
    np.testing.assert_allclose(dense.reactions_si, sparse.reactions_si, rtol=rtol, atol=atol)
    np.testing.assert_allclose(
        dense.element_end_forces_local_si,
        sparse.element_end_forces_local_si,
        rtol=rtol,
        atol=atol,
    )
    for component, value in expected["tip"].items():
        assert dense.displacements_si[1, DOF_INDEX[component]] == pytest.approx(
            value, rel=rtol, abs=atol
        )
    for component, value in expected["base_reaction"].items():
        assert dense.reactions_si[0, REACTION_INDEX[component]] == pytest.approx(
            value, rel=rtol, abs=atol
        )
    assert dense.total_strain_energy_j == pytest.approx(
        expected["total_strain_energy_j"], rel=rtol, abs=atol
    )
    assert dense.free_residual_linf <= 1.0e-8
    assert dense.scaled_free_residual <= 1.0e-12
    assert dense.to_manifest()["claim_boundary"] == (
        "engine_v2_phase0_cpu_reference_not_hip_parity"
    )


def test_dense_and_sparse_cpu_reference_match_analytic_axial_truss() -> None:
    buffers = pack_solver_model_buffers(_truss_payload(), load_pattern_id="LC_AXIAL")
    dense = solve_linear_static(buffers, matrix_backend="dense")
    sparse = solve_linear_static(buffers, matrix_backend="scipy_sparse")

    assert dense.status == "ready"
    assert sparse.status == "ready"
    np.testing.assert_allclose(dense.displacements_si, sparse.displacements_si)
    np.testing.assert_allclose(dense.reactions_si, sparse.reactions_si)
    np.testing.assert_allclose(
        dense.element_end_forces_local_si, sparse.element_end_forces_local_si
    )
    assert dense.displacements_si[1, DOF_INDEX["UX"]] == pytest.approx(5.0e-5)
    assert dense.reactions_si[0, REACTION_INDEX["FX"]] == pytest.approx(-100000.0)
    assert dense.element_end_forces_local_si[0, 0, DOF_INDEX["UX"]] == pytest.approx(
        -100000.0
    )
    assert dense.element_end_forces_local_si[0, 1, DOF_INDEX["UX"]] == pytest.approx(
        100000.0
    )
    assert dense.total_strain_energy_j == pytest.approx(2.5)


def test_cpu_reference_rejects_stale_descriptor_after_buffer_byte_mutation() -> None:
    buffers = pack_solver_model_buffers(_payload(), load_pattern_id="LC_AXIAL")
    forged = _forge_buffer_array(
        buffers,
        "material_law_code",
        np.array([255], dtype="u1"),
        refresh_descriptor=False,
        refresh_numeric_hash=False,
    )

    with pytest.raises(CPUReferenceError) as error:
        solve_linear_static(forged)
    assert error.value.code == "cpu_reference_buffer_descriptor_mismatch"


def test_cpu_reference_rejects_stale_numeric_hash_after_descriptor_refresh() -> None:
    buffers = pack_solver_model_buffers(_payload(), load_pattern_id="LC_AXIAL")
    forged = _forge_buffer_array(
        buffers,
        "material_law_code",
        np.array([255], dtype="u1"),
        refresh_descriptor=True,
        refresh_numeric_hash=False,
    )

    with pytest.raises(CPUReferenceError) as error:
        solve_linear_static(forged)
    assert error.value.code == "cpu_reference_numeric_buffer_hash_mismatch"


@pytest.mark.parametrize(
    ("buffer_name", "forged_value", "expected_error"),
    [
        (
            "material_law_code",
            np.array([255], dtype="u1"),
            "cpu_reference_material_law_not_supported",
        ),
        (
            "section_family_code",
            np.array([1], dtype="u1"),
            "cpu_reference_section_family_mismatch",
        ),
    ],
)
def test_cpu_reference_rejects_semantically_forged_codes_even_when_rehashed(
    buffer_name: str,
    forged_value: np.ndarray,
    expected_error: str,
) -> None:
    buffers = pack_solver_model_buffers(_payload(), load_pattern_id="LC_AXIAL")
    forged = _forge_buffer_array(
        buffers,
        buffer_name,
        forged_value,
        refresh_descriptor=True,
        refresh_numeric_hash=True,
    )

    with pytest.raises(CPUReferenceError) as error:
        solve_linear_static(forged)
    assert error.value.code == expected_error


def test_cpu_reference_operator_is_symmetric_positive_definite_on_free_dofs() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_WEAK"
    )
    operator = assemble_linear_static_operator(buffers)
    free = np.asarray(operator.free_dofs, dtype=np.int64)
    reduced = operator.stiffness_matrix[np.ix_(free, free)]

    np.testing.assert_allclose(operator.stiffness_matrix, operator.stiffness_matrix.T, atol=1e-10)
    assert np.min(np.linalg.eigvalsh(reduced)) > 0.0
    assert operator.stiffness_matrix.flags.writeable is False
    with pytest.raises(ValueError):
        operator.stiffness_matrix.setflags(write=True)


def test_cpu_reference_residual_jvp_matches_centered_finite_difference() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_STRONG"
    )
    operator = assemble_linear_static_operator(buffers)
    size = operator.stiffness_matrix.shape[0]
    displacement = np.linspace(-2.0e-5, 3.0e-5, size)
    direction = np.linspace(1.0, 2.0, size)
    epsilon = 1.0e-7
    finite_difference = (
        operator.residual(displacement + epsilon * direction)
        - operator.residual(displacement - epsilon * direction)
    ) / (2.0 * epsilon)

    np.testing.assert_allclose(operator.jvp(direction), finite_difference, rtol=1e-9, atol=1e-4)


def test_rotated_nonzero_roll_frame_builds_right_handed_operator() -> None:
    payload = _payload()
    payload["nodes"][1]["coordinates_m"] = [1.0, 2.0, 3.0]
    payload["elements"][0]["local_axis_rotation_rad"] = 0.37
    buffers = pack_solver_model_buffers(payload, load_pattern_id="LC_WEAK")
    operator = assemble_linear_static_operator(buffers)
    transform = operator.element_operators[0].transform_global_to_local
    rotation = transform[:3, :3]

    np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), rtol=0.0, atol=1e-12)
    assert np.linalg.det(rotation) == pytest.approx(1.0, abs=1e-12)
    np.testing.assert_allclose(operator.stiffness_matrix, operator.stiffness_matrix.T, atol=1e-9)


def test_two_element_frame_assembles_and_solves_without_proxy_reduction() -> None:
    payload = _payload()
    payload["nodes"].append(
        {
            "id": "N3",
            "index": 2,
            "coordinates_m": [4.0, 0.0, 0.0],
            "source_id": "generated:N3",
            "extensions": {},
        }
    )
    second = deepcopy(payload["elements"][0])
    second.update({"id": "E2", "index": 1, "node_ids": ["N2", "N3"], "source_id": "generated:E2"})
    payload["elements"].append(second)
    for pattern in payload["load_patterns"]:
        pattern["nodal_loads"][0]["node_id"] = "N3"

    buffers = pack_solver_model_buffers(payload, load_pattern_id="LC_AXIAL")
    operator = assemble_linear_static_operator(buffers)
    result = solve_linear_static(buffers)

    assert operator.stiffness_matrix.shape == (18, 18)
    assert result.status == "ready"
    assert result.displacements_si[2, DOF_INDEX["UX"]] == pytest.approx(0.0001)
    assert result.reactions_si[0, REACTION_INDEX["FX"]] == pytest.approx(-100000.0)
    assert result.element_end_forces_local_si.shape == (2, 2, 6)


def test_result_arrays_are_immutable_bytes_backed() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_TORSION"
    )
    result = solve_linear_static(buffers)

    for array in (
        result.displacements_si,
        result.reactions_si,
        result.residual_si,
        result.element_end_forces_local_si,
        result.element_strain_energy_j,
    ):
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array.setflags(write=True)
