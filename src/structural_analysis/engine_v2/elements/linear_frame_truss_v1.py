"""Shared FP64 linear 3D frame/truss element semantics v1.

This module is the versioned constitutive and local-frame source consumed by
the CPU reference, sparse ExecutionPlan v2, and HIP symbolic assembly paths.
It only materializes fixed-size 12 by 12 element arrays; global assembly and
solver policy remain backend responsibilities.

The compatibility operator version deliberately retains the historical CPU
reference string.  Moving unchanged formulas behind this public boundary must
not invalidate already sealed plan, operator, registry, or ResultIR hashes.
Any future numerical-semantic change requires a new semantics version and a
new compatibility operator version instead of mutating these v1 constants.
"""

from __future__ import annotations

import math
from typing import Any, Literal, NoReturn

import numpy as np

from structural_analysis.engine_v2.buffers import (
    ELEMENT_FORMULATION_CODES,
    ELEMENT_TYPE_CODES,
    MATERIAL_LAW_CODES,
    SECTION_FAMILY_CODES,
)


LINEAR_FRAME_TRUSS_ELEMENT_SEMANTICS_VERSION_V1 = (
    "engine-v2-linear-frame-truss-element-semantics.v1"
)
LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1 = (
    "engine-v2-cpu-reference-linear-static.v1"
)
LINEAR_FRAME_TRUSS_REFERENCE_AXIS_POLICY_V1 = (
    "cpu_reference_global_z_unless_abs_local_x_z_gt_0_9_v1"
)
REFERENCE_AXIS_SWITCH_THRESHOLD_V1 = 0.9
MINIMUM_ELEMENT_LENGTH_M_V1 = 1.0e-12
ELEMENT_DOF_COUNT_V1 = 12

ReferenceAxisV1 = Literal["global_y", "global_z"]


class LinearFrameTrussV1Error(ValueError):
    """Stable fail-closed error for the shared v1 element semantics."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def frame_reference_axis_v1(start_m: Any, end_m: Any) -> ReferenceAxisV1:
    """Return the v1 reference-axis choice for an element chord."""

    local_x, _ = _local_x_and_length(start_m, end_m)
    return (
        "global_y"
        if abs(float(local_x[2])) > REFERENCE_AXIS_SWITCH_THRESHOLD_V1
        else "global_z"
    )


def frame_transform_v1(
    start_m: Any,
    end_m: Any,
    roll_rad: Any,
) -> tuple[np.ndarray, float]:
    """Build the 12-DOF global-to-local transform and chord length."""

    local_x, length = _local_x_and_length(start_m, end_m)
    roll = _finite_scalar(roll_rad, path="/roll_rad")
    reference_axis = (
        "global_y"
        if abs(float(local_x[2])) > REFERENCE_AXIS_SWITCH_THRESHOLD_V1
        else "global_z"
    )
    reference = (
        np.array([0.0, 1.0, 0.0], dtype="<f8")
        if reference_axis == "global_y"
        else np.array([0.0, 0.0, 1.0], dtype="<f8")
    )
    local_y_zero = np.cross(reference, local_x)
    local_y_norm = float(np.linalg.norm(local_y_zero))
    if not math.isfinite(local_y_norm) or local_y_norm <= 0.0:  # pragma: no cover
        _raise(
            "linear_frame_truss_local_frame_invalid",
            "/geometry",
            "Element reference axis cannot define a local frame.",
        )
    local_y_zero /= local_y_norm
    local_z_zero = np.cross(local_x, local_y_zero)
    cosine = math.cos(roll)
    sine = math.sin(roll)
    local_y = cosine * local_y_zero + sine * local_z_zero
    local_z = -sine * local_y_zero + cosine * local_z_zero
    rotation = np.vstack((local_x, local_y, local_z))
    if not np.allclose(rotation @ rotation.T, np.eye(3), rtol=0.0, atol=1.0e-12):
        _raise(
            "linear_frame_truss_local_frame_invalid",
            "/geometry",
            "Element local frame is not orthonormal.",
        )
    if float(np.linalg.det(rotation)) <= 0.0:
        _raise(
            "linear_frame_truss_local_frame_left_handed",
            "/geometry",
            "Element local frame must be right-handed.",
        )
    transform = np.zeros((ELEMENT_DOF_COUNT_V1, ELEMENT_DOF_COUNT_V1), dtype="<f8")
    for block in range(4):
        offset = block * 3
        transform[offset : offset + 3, offset : offset + 3] = rotation
    return transform, length


def frame_local_stiffness_v1(
    material_properties_si: Any,
    section_properties_si: Any,
    length_m: Any,
) -> np.ndarray:
    """Return the Euler-Bernoulli 3D frame local stiffness matrix."""

    material = _material_properties(material_properties_si)
    section = _section_properties(section_properties_si)
    length = _positive_length(length_m)
    _validate_material_values(material, path="/material_properties_si")
    if np.any(section <= 0.0):
        _raise(
            "linear_frame_truss_section_properties_invalid",
            "/section_properties_si",
            "Frame section properties must all be positive.",
        )

    elastic_modulus = float(material[0])
    poisson_ratio = float(material[1])
    area, iy, iz, torsion, _, _ = (float(value) for value in section)
    shear_modulus = elastic_modulus / (2.0 * (1.0 + poisson_ratio))
    stiffness = np.zeros((ELEMENT_DOF_COUNT_V1, ELEMENT_DOF_COUNT_V1), dtype="<f8")

    _add_pair(stiffness, 0, 6, elastic_modulus * area / length)
    _add_pair(stiffness, 3, 9, shear_modulus * torsion / length)
    _add_bending_block(stiffness, (1, 5, 7, 11), elastic_modulus * iz, length, 1.0)
    _add_bending_block(stiffness, (2, 4, 8, 10), elastic_modulus * iy, length, -1.0)
    return stiffness


def truss_local_stiffness_v1(
    material_properties_si: Any,
    section_properties_si: Any,
    length_m: Any,
) -> np.ndarray:
    """Return the axial-only 3D truss local stiffness matrix."""

    material = _material_properties(material_properties_si)
    section = _section_properties(section_properties_si)
    length = _positive_length(length_m)
    _validate_material_values(material, path="/material_properties_si")
    if float(section[0]) <= 0.0 or np.any(section[1:] != 0.0):
        _raise(
            "linear_frame_truss_section_properties_invalid",
            "/section_properties_si",
            "Truss section requires positive area and zero unused columns.",
        )
    stiffness = np.zeros((ELEMENT_DOF_COUNT_V1, ELEMENT_DOF_COUNT_V1), dtype="<f8")
    _add_pair(
        stiffness,
        0,
        6,
        float(material[0]) * float(section[0]) / length,
    )
    return stiffness


def validate_linear_frame_truss_references_v1(
    *,
    coordinates: Any,
    connectivity: Any,
    element_types: Any,
    formulations: Any,
    material_indices: Any,
    section_indices: Any,
    material_laws: Any,
    materials: Any,
    section_families: Any,
    sections: Any,
) -> None:
    """Validate v1 element/material/section references.

    Chord length is intentionally validated by :func:`frame_transform_v1`.
    Keeping that stage boundary preserves the historical CPU/v2 error order
    when unsupported offsets, releases, or prescribed values coexist with a
    degenerate chord.
    """

    coordinates_array = _float_table(coordinates, columns=3, path="/node_coordinates_m")
    connectivity_array = _integer_table(
        connectivity, columns=2, path="/element_connectivity"
    )
    materials_array = _float_table(materials, columns=3, path="/material_properties_si")
    sections_array = _float_table(sections, columns=6, path="/section_properties_si")
    element_count = connectivity_array.shape[0]
    material_count = materials_array.shape[0]
    section_count = sections_array.shape[0]
    if (
        min(coordinates_array.shape[0], element_count, material_count, section_count)
        <= 0
    ):
        _raise(
            "linear_frame_truss_input_shape_invalid",
            "/",
            "Node, element, material, and section tables must be non-empty.",
        )

    element_types_array = _integer_vector(
        element_types, element_count, path="/element_type"
    )
    formulations_array = _integer_vector(
        formulations, element_count, path="/element_formulation_code"
    )
    material_indices_array = _integer_vector(
        material_indices, element_count, path="/element_material_index"
    )
    section_indices_array = _integer_vector(
        section_indices, element_count, path="/element_section_index"
    )
    material_laws_array = _integer_vector(
        material_laws, material_count, path="/material_law_code"
    )
    section_families_array = _integer_vector(
        section_families, section_count, path="/section_family_code"
    )

    supported_material_law = MATERIAL_LAW_CODES["linear_elastic_isotropic"]
    frame_type = ELEMENT_TYPE_CODES["frame_3d"]
    truss_type = ELEMENT_TYPE_CODES["truss_3d"]
    frame_family = SECTION_FAMILY_CODES["frame_3d"]
    truss_family = SECTION_FAMILY_CODES["truss_3d"]
    node_count = coordinates_array.shape[0]

    for element_index in range(element_count):
        element_path = f"/elements/{element_index}"
        node_i = int(connectivity_array[element_index, 0])
        node_j = int(connectivity_array[element_index, 1])
        if not (0 <= node_i < node_count and 0 <= node_j < node_count):
            _raise(
                "linear_frame_truss_connectivity_out_of_range",
                f"/element_connectivity/{element_index}",
                f"Element {element_index} references a node outside [0, {node_count}).",
            )
        if node_i == node_j:
            _raise(
                "linear_frame_truss_connectivity_invalid",
                f"/element_connectivity/{element_index}",
                f"Element {element_index} must connect two distinct nodes.",
            )
        material_index = int(material_indices_array[element_index])
        section_index = int(section_indices_array[element_index])
        if not 0 <= material_index < material_count:
            _raise(
                "linear_frame_truss_material_index_out_of_range",
                f"/element_material_index/{element_index}",
                f"Element {element_index} material index {material_index} is out of range.",
            )
        if not 0 <= section_index < section_count:
            _raise(
                "linear_frame_truss_section_index_out_of_range",
                f"/element_section_index/{element_index}",
                f"Element {element_index} section index {section_index} is out of range.",
            )
        material_law = int(material_laws_array[material_index])
        if material_law != supported_material_law:
            _raise(
                "linear_frame_truss_material_law_not_supported",
                f"/material_law_code/{material_index}",
                f"Element {element_index} references unsupported material law code {material_law}.",
            )
        _validate_material_values(
            materials_array[material_index],
            path=f"/material_properties_si/{material_index}",
            message=(
                f"Element {element_index} references invalid isotropic material properties."
            ),
        )

        element_type = int(element_types_array[element_index])
        formulation = int(formulations_array[element_index])
        section_family = int(section_families_array[section_index])
        section = sections_array[section_index]
        if element_type == frame_type:
            if formulation != ELEMENT_FORMULATION_CODES["euler_bernoulli_3d"]:
                _raise(
                    "linear_frame_truss_formulation_not_supported",
                    f"{element_path}/formulation",
                    f"Unsupported frame formulation code {formulation}.",
                )
            if section_family != frame_family:
                _raise(
                    "linear_frame_truss_section_family_mismatch",
                    f"/section_family_code/{section_index}",
                    f"Frame element {element_index} requires section family code {frame_family}, "
                    f"got {section_family}.",
                )
            if np.any(section <= 0.0):
                _raise(
                    "linear_frame_truss_section_properties_invalid",
                    f"/section_properties_si/{section_index}",
                    f"Frame element {element_index} requires positive section properties.",
                )
        elif element_type == truss_type:
            if formulation != ELEMENT_FORMULATION_CODES["linear_truss_3d"]:
                _raise(
                    "linear_frame_truss_formulation_not_supported",
                    f"{element_path}/formulation",
                    f"Unsupported truss formulation code {formulation}.",
                )
            if section_family != truss_family:
                _raise(
                    "linear_frame_truss_section_family_mismatch",
                    f"/section_family_code/{section_index}",
                    f"Truss element {element_index} requires section family code {truss_family}, "
                    f"got {section_family}.",
                )
            if float(section[0]) <= 0.0 or np.any(section[1:] != 0.0):
                _raise(
                    "linear_frame_truss_section_properties_invalid",
                    f"/section_properties_si/{section_index}",
                    f"Truss element {element_index} requires positive area and zero unused columns.",
                )
        else:
            _raise(
                "linear_frame_truss_element_type_not_supported",
                f"{element_path}/type",
                f"Unsupported element type code {element_type}.",
            )


def _local_x_and_length(start_m: Any, end_m: Any) -> tuple[np.ndarray, float]:
    start = _float_vector(start_m, size=3, path="/start_m")
    end = _float_vector(end_m, size=3, path="/end_m")
    delta = end - start
    length = float(np.linalg.norm(delta))
    if not math.isfinite(length) or length <= MINIMUM_ELEMENT_LENGTH_M_V1:
        _raise(
            "linear_frame_truss_zero_length_element",
            "/geometry",
            "Element length must exceed 1e-12 m.",
        )
    return delta / length, length


def _material_properties(value: Any) -> np.ndarray:
    return _float_vector(value, size=3, path="/material_properties_si")


def _section_properties(value: Any) -> np.ndarray:
    return _float_vector(value, size=6, path="/section_properties_si")


def _validate_material_values(
    material: np.ndarray,
    *,
    path: str,
    message: str = "Isotropic material requires E>0, -1<nu<0.5, and density>=0.",
) -> None:
    elastic_modulus, poisson_ratio, density = (float(value) for value in material)
    if elastic_modulus <= 0.0 or not -1.0 < poisson_ratio < 0.5 or density < 0.0:
        _raise(
            "linear_frame_truss_material_properties_invalid",
            path,
            message,
        )


def _float_vector(value: Any, *, size: int, path: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise LinearFrameTrussV1Error(
            "linear_frame_truss_input_dtype_invalid",
            path,
            "Expected FP64-compatible numerical values.",
        ) from exc
    if array.shape != (size,):
        _raise(
            "linear_frame_truss_input_shape_invalid",
            path,
            f"Expected shape ({size},), got {array.shape}.",
        )
    if not np.all(np.isfinite(array)):
        _raise(
            "linear_frame_truss_input_non_finite",
            path,
            "Input contains NaN or Infinity.",
        )
    return array


def _float_table(value: Any, *, columns: int, path: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise LinearFrameTrussV1Error(
            "linear_frame_truss_input_dtype_invalid",
            path,
            "Expected an FP64-compatible numerical table.",
        ) from exc
    if array.ndim != 2 or array.shape[1:] != (columns,):
        _raise(
            "linear_frame_truss_input_shape_invalid",
            path,
            f"Expected shape (N,{columns}), got {array.shape}.",
        )
    if not np.all(np.isfinite(array)):
        _raise(
            "linear_frame_truss_input_non_finite",
            path,
            "Input contains NaN or Infinity.",
        )
    return array


def _integer_vector(value: Any, size: int, *, path: str) -> np.ndarray:
    array = np.asarray(value)
    if array.shape != (size,):
        _raise(
            "linear_frame_truss_input_shape_invalid",
            path,
            f"Expected shape ({size},), got {array.shape}.",
        )
    if array.dtype.kind not in "iu":
        _raise(
            "linear_frame_truss_input_dtype_invalid",
            path,
            "Expected an integer code/index vector.",
        )
    return array


def _integer_table(value: Any, *, columns: int, path: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 2 or array.shape[1:] != (columns,):
        _raise(
            "linear_frame_truss_input_shape_invalid",
            path,
            f"Expected shape (N,{columns}), got {array.shape}.",
        )
    if array.dtype.kind not in "iu":
        _raise(
            "linear_frame_truss_input_dtype_invalid",
            path,
            "Expected an integer code/index table.",
        )
    return array


def _finite_scalar(value: Any, *, path: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        _raise(
            "linear_frame_truss_input_dtype_invalid",
            path,
            "Expected a finite real scalar.",
        )
    try:
        scalar = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LinearFrameTrussV1Error(
            "linear_frame_truss_input_dtype_invalid",
            path,
            "Expected a finite real scalar.",
        ) from exc
    if not math.isfinite(scalar):
        _raise(
            "linear_frame_truss_input_non_finite",
            path,
            "Expected a finite real scalar.",
        )
    return scalar


def _positive_length(value: Any) -> float:
    length = _finite_scalar(value, path="/length_m")
    if length <= MINIMUM_ELEMENT_LENGTH_M_V1:
        _raise(
            "linear_frame_truss_zero_length_element",
            "/length_m",
            "Element length must exceed 1e-12 m.",
        )
    return length


def _add_pair(matrix: np.ndarray, start: int, end: int, value: float) -> None:
    matrix[start, start] += value
    matrix[start, end] -= value
    matrix[end, start] -= value
    matrix[end, end] += value


def _add_bending_block(
    matrix: np.ndarray,
    dofs: tuple[int, int, int, int],
    flexural_rigidity: float,
    length: float,
    rotation_sign: float,
) -> None:
    l2 = length * length
    base = (flexural_rigidity / (length**3)) * np.array(
        [
            [12.0, 6.0 * length, -12.0, 6.0 * length],
            [6.0 * length, 4.0 * l2, -6.0 * length, 2.0 * l2],
            [-12.0, -6.0 * length, 12.0, -6.0 * length],
            [6.0 * length, 2.0 * l2, -6.0 * length, 4.0 * l2],
        ],
        dtype="<f8",
    )
    if rotation_sign < 0.0:
        sign = np.diag([1.0, -1.0, 1.0, -1.0])
        base = sign @ base @ sign
    matrix[np.ix_(dofs, dofs)] += base


def _raise(code: str, path: str, message: str) -> NoReturn:
    raise LinearFrameTrussV1Error(code, path, message)
