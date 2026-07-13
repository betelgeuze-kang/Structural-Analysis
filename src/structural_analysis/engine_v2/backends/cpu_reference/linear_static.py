"""FP64 3D frame/truss linear-static reference operator over SolverModelBuffers v1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Literal

import numpy as np

from structural_analysis.engine_v2.buffers import (
    DOF_ORDER,
    ELEMENT_FORMULATION_CODES,
    ELEMENT_TYPE_CODES,
    MATERIAL_LAW_CODES,
    SECTION_FAMILY_CODES,
    SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
    SolverModelBuffers,
    _artifact_hash,
    _descriptor,
    _mapping_hash,
    _numeric_buffer_hash,
)

CPU_REFERENCE_OPERATOR_VERSION = "engine-v2-cpu-reference-linear-static.v1"
_DOF_PER_NODE = len(DOF_ORDER)
_ELEMENT_DOF_COUNT = 12
_REQUIRED_BUFFER_NAMES = frozenset(
    {
        "node_coordinates_m",
        "element_connectivity",
        "element_type",
        "element_formulation_code",
        "element_material_index",
        "element_section_index",
        "material_law_code",
        "material_properties_si",
        "section_family_code",
        "section_properties_si",
        "element_local_axis_rotation_rad",
        "element_offsets_m",
        "element_release_mask",
        "support_mask",
        "prescribed_values_si",
        "load_vector_si",
    }
)
_EXPECTED_CODE_TABLES = {
    "element_type": ELEMENT_TYPE_CODES,
    "element_formulation": ELEMENT_FORMULATION_CODES,
    "material_law": MATERIAL_LAW_CODES,
    "section_family": SECTION_FAMILY_CODES,
}
_EXPECTED_BUFFER_DTYPES = {
    "node_coordinates_m": "<f8",
    "element_connectivity": "<i4",
    "element_type": "|u1",
    "element_formulation_code": "|u1",
    "element_material_index": "<i4",
    "element_section_index": "<i4",
    "material_law_code": "|u1",
    "material_properties_si": "<f8",
    "section_family_code": "|u1",
    "section_properties_si": "<f8",
    "element_local_axis_rotation_rad": "<f8",
    "element_offsets_m": "<f8",
    "element_release_mask": "|u1",
    "support_mask": "|u1",
    "prescribed_values_si": "<f8",
    "load_vector_si": "<f8",
}


class CPUReferenceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class _ElementOperator:
    global_dofs: tuple[int, ...]
    transform_global_to_local: np.ndarray
    stiffness_local: np.ndarray


@dataclass(frozen=True)
class LinearStaticOperator:
    version: str
    solver_buffer_hash: str
    stiffness_matrix: np.ndarray
    load_vector: np.ndarray
    constrained_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]
    element_operators: tuple[_ElementOperator, ...]
    operator_hash: str

    def residual(self, displacement: np.ndarray) -> np.ndarray:
        vector = _vector(displacement, self.stiffness_matrix.shape[0], "displacement")
        return self.stiffness_matrix @ vector - self.load_vector

    def jvp(self, direction: np.ndarray) -> np.ndarray:
        vector = _vector(direction, self.stiffness_matrix.shape[0], "direction")
        return self.stiffness_matrix @ vector


@dataclass(frozen=True)
class LinearStaticResult:
    status: str
    backend: str
    operator_version: str
    solver_buffer_hash: str
    operator_hash: str
    result_hash: str
    displacements_si: np.ndarray
    reactions_si: np.ndarray
    residual_si: np.ndarray
    element_end_forces_local_si: np.ndarray
    element_strain_energy_j: np.ndarray
    total_strain_energy_j: float
    free_residual_linf: float
    scaled_free_residual: float
    constrained_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]

    def to_manifest(self) -> dict[str, object]:
        return {
            "status": self.status,
            "backend": self.backend,
            "operator_version": self.operator_version,
            "solver_buffer_hash": self.solver_buffer_hash,
            "operator_hash": self.operator_hash,
            "result_hash": self.result_hash,
            "total_strain_energy_j": self.total_strain_energy_j,
            "free_residual_linf": self.free_residual_linf,
            "scaled_free_residual": self.scaled_free_residual,
            "constrained_dofs": list(self.constrained_dofs),
            "free_dofs": list(self.free_dofs),
            "claim_boundary": "engine_v2_phase0_cpu_reference_not_hip_parity",
        }


def assemble_linear_static_operator(buffers: SolverModelBuffers) -> LinearStaticOperator:
    _validate_buffer_contract(buffers)
    coordinates = buffers.array("node_coordinates_m")
    connectivity = buffers.array("element_connectivity")
    element_types = buffers.array("element_type")
    formulations = buffers.array("element_formulation_code")
    material_indices = buffers.array("element_material_index")
    section_indices = buffers.array("element_section_index")
    material_laws = buffers.array("material_law_code")
    materials = buffers.array("material_properties_si")
    section_families = buffers.array("section_family_code")
    sections = buffers.array("section_properties_si")
    rolls = buffers.array("element_local_axis_rotation_rad")
    offsets = buffers.array("element_offsets_m")
    releases = buffers.array("element_release_mask")
    support_mask = buffers.array("support_mask")
    prescribed = buffers.array("prescribed_values_si")
    loads = buffers.array("load_vector_si")

    _validate_element_references(
        coordinates=coordinates,
        connectivity=connectivity,
        element_types=element_types,
        formulations=formulations,
        material_indices=material_indices,
        section_indices=section_indices,
        material_laws=material_laws,
        materials=materials,
        section_families=section_families,
        sections=sections,
    )

    if np.any(offsets != 0.0):
        raise CPUReferenceError(
            "cpu_reference_offsets_not_implemented",
            "Phase 0 CPU reference requires zero element offsets.",
        )
    if np.any(releases != 0):
        raise CPUReferenceError(
            "cpu_reference_releases_not_implemented",
            "Phase 0 CPU reference requires empty element releases.",
        )
    if np.any(prescribed != 0.0):
        raise CPUReferenceError(
            "cpu_reference_prescribed_values_not_implemented",
            "Phase 0 CPU reference requires zero prescribed values.",
        )

    dof_count = coordinates.shape[0] * _DOF_PER_NODE
    stiffness = np.zeros((dof_count, dof_count), dtype="<f8")
    element_operators: list[_ElementOperator] = []

    for element_index in range(connectivity.shape[0]):
        node_i = int(connectivity[element_index, 0])
        node_j = int(connectivity[element_index, 1])
        start = coordinates[node_i]
        end = coordinates[node_j]
        material = materials[int(material_indices[element_index])]
        section = sections[int(section_indices[element_index])]
        transform, length = _frame_transform(
            start,
            end,
            float(rolls[element_index]),
        )
        element_type = int(element_types[element_index])
        formulation = int(formulations[element_index])
        if element_type == ELEMENT_TYPE_CODES["frame_3d"]:
            if formulation != ELEMENT_FORMULATION_CODES["euler_bernoulli_3d"]:
                raise CPUReferenceError(
                    "cpu_reference_formulation_not_supported",
                    f"Unsupported frame formulation code {formulation}.",
                )
            local_stiffness = _frame_local_stiffness(material, section, length)
        elif element_type == ELEMENT_TYPE_CODES["truss_3d"]:
            if formulation != ELEMENT_FORMULATION_CODES["linear_truss_3d"]:
                raise CPUReferenceError(
                    "cpu_reference_formulation_not_supported",
                    f"Unsupported truss formulation code {formulation}.",
                )
            local_stiffness = _truss_local_stiffness(material, section, length)
        else:  # pragma: no cover - code table/packer invariant
            raise CPUReferenceError(
                "cpu_reference_element_type_not_supported",
                f"Unsupported element type code {element_type}.",
            )

        global_stiffness = transform.T @ local_stiffness @ transform
        global_dofs = tuple(
            node * _DOF_PER_NODE + component
            for node in (node_i, node_j)
            for component in range(_DOF_PER_NODE)
        )
        indices = np.ix_(global_dofs, global_dofs)
        stiffness[indices] += global_stiffness
        element_operators.append(
            _ElementOperator(
                global_dofs=global_dofs,
                transform_global_to_local=_immutable_array(transform),
                stiffness_local=_immutable_array(local_stiffness),
            )
        )

    load_vector = np.asarray(loads, dtype="<f8").reshape(-1)
    constrained_dofs = tuple(int(value) for value in np.flatnonzero(support_mask.reshape(-1)))
    constrained_set = set(constrained_dofs)
    free_dofs = tuple(index for index in range(dof_count) if index not in constrained_set)
    if not constrained_dofs:
        raise CPUReferenceError(
            "cpu_reference_constraints_missing", "At least one constrained DOF is required."
        )
    if not free_dofs:
        raise CPUReferenceError(
            "cpu_reference_free_dofs_missing", "At least one free DOF is required."
        )
    stiffness_scale = max(1.0, float(np.max(np.abs(stiffness))))
    antisymmetric_linf = float(np.max(np.abs(stiffness - stiffness.T)))
    if antisymmetric_linf > stiffness_scale * 1.0e-12:
        raise CPUReferenceError(
            "cpu_reference_stiffness_not_symmetric", "Assembled stiffness is not symmetric."
        )
    stiffness = 0.5 * (stiffness + stiffness.T)

    immutable_stiffness = _immutable_array(stiffness)
    immutable_load = _immutable_array(load_vector)
    operator_hash = _operator_hash(
        buffers.numeric_buffer_hash,
        immutable_stiffness,
        immutable_load,
        constrained_dofs,
    )
    return LinearStaticOperator(
        version=CPU_REFERENCE_OPERATOR_VERSION,
        solver_buffer_hash=buffers.numeric_buffer_hash,
        stiffness_matrix=immutable_stiffness,
        load_vector=immutable_load,
        constrained_dofs=constrained_dofs,
        free_dofs=free_dofs,
        element_operators=tuple(element_operators),
        operator_hash=operator_hash,
    )


def solve_linear_static(
    buffers: SolverModelBuffers,
    *,
    matrix_backend: Literal["dense", "scipy_sparse"] = "dense",
    residual_tolerance: float = 1.0e-10,
) -> LinearStaticResult:
    if not math.isfinite(residual_tolerance) or residual_tolerance <= 0.0:
        raise ValueError("residual_tolerance must be finite and positive.")
    operator = assemble_linear_static_operator(buffers)
    node_count = buffers.array("node_coordinates_m").shape[0]
    return solve_linear_static_operator(
        operator,
        node_count=node_count,
        matrix_backend=matrix_backend,
        residual_tolerance=residual_tolerance,
    )


def solve_linear_static_operator(
    operator: LinearStaticOperator,
    *,
    node_count: int,
    matrix_backend: Literal["dense", "scipy_sparse"] = "dense",
    residual_tolerance: float = 1.0e-10,
) -> LinearStaticResult:
    """Solve one precompiled, validated CPU reference operator.

    This is the execution entrypoint used by Engine v2 ``ExecutionPlan``.  It
    keeps the legacy buffer convenience function above while avoiding a second
    assembly when a compiled plan already exists.
    """

    if not math.isfinite(residual_tolerance) or residual_tolerance <= 0.0:
        raise ValueError("residual_tolerance must be finite and positive.")
    _validate_linear_static_operator(operator, node_count=node_count)
    stiffness = operator.stiffness_matrix
    load = operator.load_vector
    free = np.asarray(operator.free_dofs, dtype=np.int64)
    displacement = np.zeros(stiffness.shape[0], dtype="<f8")
    reduced_stiffness = stiffness[np.ix_(free, free)]
    reduced_load = load[free]

    try:
        if matrix_backend == "dense":
            displacement[free] = np.linalg.solve(reduced_stiffness, reduced_load)
        elif matrix_backend == "scipy_sparse":
            from scipy.sparse import csr_matrix
            from scipy.sparse.linalg import MatrixRankWarning, spsolve
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                displacement[free] = np.asarray(
                    spsolve(csr_matrix(reduced_stiffness), reduced_load), dtype="<f8"
                )
        else:
            raise ValueError(f"Unsupported matrix_backend: {matrix_backend}")
    except (np.linalg.LinAlgError, RuntimeError, Warning) as exc:
        raise CPUReferenceError(
            "cpu_reference_singular_or_failed_solve",
            f"Reduced system solve failed: {exc}",
        ) from exc

    if not np.all(np.isfinite(displacement)):
        raise CPUReferenceError(
            "cpu_reference_non_finite_solution", "Linear solve returned NaN or Infinity."
        )

    residual = operator.residual(displacement)
    free_residual_linf = float(np.max(np.abs(residual[free]))) if free.size else 0.0
    load_scale = max(1.0, float(np.max(np.abs(load[free]))) if free.size else 0.0)
    scaled_residual = free_residual_linf / load_scale
    status = "ready" if scaled_residual <= residual_tolerance else "failed"

    reactions = np.zeros_like(residual)
    constrained = np.asarray(operator.constrained_dofs, dtype=np.int64)
    reactions[constrained] = residual[constrained]
    element_forces = np.zeros(
        (len(operator.element_operators), 2, _DOF_PER_NODE), dtype="<f8"
    )
    element_energy = np.zeros(len(operator.element_operators), dtype="<f8")
    for index, element in enumerate(operator.element_operators):
        global_displacement = displacement[np.asarray(element.global_dofs, dtype=np.int64)]
        local_displacement = element.transform_global_to_local @ global_displacement
        local_force = element.stiffness_local @ local_displacement
        element_forces[index] = local_force.reshape(2, _DOF_PER_NODE)
        element_energy[index] = 0.5 * float(local_displacement @ local_force)

    total_energy = float(np.sum(element_energy))
    immutable_displacement = _immutable_array(displacement.reshape(node_count, _DOF_PER_NODE))
    immutable_reactions = _immutable_array(reactions.reshape(node_count, _DOF_PER_NODE))
    immutable_residual = _immutable_array(residual.reshape(node_count, _DOF_PER_NODE))
    immutable_element_forces = _immutable_array(element_forces)
    immutable_element_energy = _immutable_array(element_energy)
    result_hash = _result_hash(
        operator.operator_hash,
        matrix_backend,
        immutable_displacement,
        immutable_reactions,
        immutable_element_forces,
    )
    return LinearStaticResult(
        status=status,
        backend=f"cpu_reference_{matrix_backend}_fp64",
        operator_version=operator.version,
        solver_buffer_hash=operator.solver_buffer_hash,
        operator_hash=operator.operator_hash,
        result_hash=result_hash,
        displacements_si=immutable_displacement,
        reactions_si=immutable_reactions,
        residual_si=immutable_residual,
        element_end_forces_local_si=immutable_element_forces,
        element_strain_energy_j=immutable_element_energy,
        total_strain_energy_j=total_energy,
        free_residual_linf=free_residual_linf,
        scaled_free_residual=scaled_residual,
        constrained_dofs=operator.constrained_dofs,
        free_dofs=operator.free_dofs,
    )


def _validate_linear_static_operator(
    operator: LinearStaticOperator, *, node_count: int
) -> None:
    if not isinstance(operator, LinearStaticOperator):
        raise CPUReferenceError(
            "cpu_reference_operator_type_invalid",
            "Expected a LinearStaticOperator artifact.",
        )
    if operator.version != CPU_REFERENCE_OPERATOR_VERSION:
        raise CPUReferenceError(
            "cpu_reference_operator_version_mismatch",
            "Compiled operator version is not supported.",
        )
    if isinstance(node_count, bool) or not isinstance(node_count, (int, np.integer)):
        raise CPUReferenceError(
            "cpu_reference_node_count_invalid", "node_count must be an integer."
        )
    normalized_node_count = int(node_count)
    if normalized_node_count <= 0:
        raise CPUReferenceError(
            "cpu_reference_node_count_invalid", "node_count must be positive."
        )
    dof_count = normalized_node_count * _DOF_PER_NODE
    stiffness = operator.stiffness_matrix
    load = operator.load_vector
    for name, array, shape in (
        ("stiffness", stiffness, (dof_count, dof_count)),
        ("load", load, (dof_count,)),
    ):
        if (
            not isinstance(array, np.ndarray)
            or array.dtype.str != "<f8"
            or array.shape != shape
            or not array.flags.c_contiguous
            or array.flags.writeable
        ):
            raise CPUReferenceError(
                "cpu_reference_operator_storage_invalid",
                f"Compiled {name} must be immutable C-order <f8 with shape {shape}.",
            )
        try:
            array.setflags(write=True)
        except ValueError:
            pass
        else:  # pragma: no cover - defensive; never mutate caller storage
            array.setflags(write=False)
            raise CPUReferenceError(
                "cpu_reference_operator_storage_invalid",
                f"Compiled {name} is not backed by immutable storage.",
            )
        if not np.all(np.isfinite(array)):
            raise CPUReferenceError(
                "cpu_reference_operator_non_finite",
                f"Compiled {name} contains NaN or Infinity.",
            )

    constrained = operator.constrained_dofs
    free = operator.free_dofs
    if (
        not isinstance(constrained, tuple)
        or not isinstance(free, tuple)
        or not constrained
        or not free
        or any(isinstance(value, bool) or not isinstance(value, int) for value in constrained + free)
        or any(left >= right for left, right in zip(constrained, constrained[1:]))
        or any(left >= right for left, right in zip(free, free[1:]))
        or sorted(constrained + free) != list(range(dof_count))
    ):
        raise CPUReferenceError(
            "cpu_reference_operator_partition_invalid",
            "Compiled constrained/free DOFs are not a strict partition.",
        )
    if not operator.element_operators:
        raise CPUReferenceError(
            "cpu_reference_operator_elements_missing",
            "Compiled operator must contain at least one element recovery operator.",
        )
    reconstructed = np.zeros_like(stiffness)
    for element_index, element in enumerate(operator.element_operators):
        if (
            not isinstance(element.global_dofs, tuple)
            or len(element.global_dofs) != _ELEMENT_DOF_COUNT
            or len(set(element.global_dofs)) != _ELEMENT_DOF_COUNT
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value < dof_count
                for value in element.global_dofs
            )
        ):
            raise CPUReferenceError(
                "cpu_reference_operator_element_dofs_invalid",
                f"Element operator {element_index} has invalid global DOFs.",
            )
        transform = element.transform_global_to_local
        local_stiffness = element.stiffness_local
        for name, array in (
            ("transform", transform),
            ("local stiffness", local_stiffness),
        ):
            if (
                not isinstance(array, np.ndarray)
                or array.dtype.str != "<f8"
                or array.shape != (_ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT)
                or not array.flags.c_contiguous
                or array.flags.writeable
                or not np.all(np.isfinite(array))
            ):
                raise CPUReferenceError(
                    "cpu_reference_operator_element_storage_invalid",
                    f"Element {element_index} {name} storage is invalid.",
                )
        if not np.allclose(
            transform @ transform.T,
            np.eye(_ELEMENT_DOF_COUNT),
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise CPUReferenceError(
                "cpu_reference_operator_transform_invalid",
                f"Element operator {element_index} transform is not orthonormal.",
            )
        global_stiffness = transform.T @ local_stiffness @ transform
        reconstructed[np.ix_(element.global_dofs, element.global_dofs)] += global_stiffness
    scale = max(1.0, float(np.max(np.abs(stiffness))))
    if not np.allclose(reconstructed, stiffness, rtol=5.0e-13, atol=5.0e-13 * scale):
        raise CPUReferenceError(
            "cpu_reference_operator_assembly_mismatch",
            "Compiled global stiffness differs from element operators.",
        )
    expected_hash = _operator_hash(
        operator.solver_buffer_hash,
        stiffness,
        load,
        constrained,
    )
    if operator.operator_hash != expected_hash:
        raise CPUReferenceError(
            "cpu_reference_operator_hash_mismatch",
            "Compiled operator hash is stale.",
        )


def _frame_local_stiffness(
    material: np.ndarray, section: np.ndarray, length: float
) -> np.ndarray:
    elastic_modulus = float(material[0])
    poisson_ratio = float(material[1])
    area, iy, iz, torsion, _, _ = (float(value) for value in section)
    shear_modulus = elastic_modulus / (2.0 * (1.0 + poisson_ratio))
    stiffness = np.zeros((_ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT), dtype="<f8")

    _add_pair(stiffness, 0, 6, elastic_modulus * area / length)
    _add_pair(stiffness, 3, 9, shear_modulus * torsion / length)
    _add_bending_block(stiffness, (1, 5, 7, 11), elastic_modulus * iz, length, 1.0)
    _add_bending_block(stiffness, (2, 4, 8, 10), elastic_modulus * iy, length, -1.0)
    return stiffness


def _truss_local_stiffness(
    material: np.ndarray, section: np.ndarray, length: float
) -> np.ndarray:
    stiffness = np.zeros((_ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT), dtype="<f8")
    _add_pair(stiffness, 0, 6, float(material[0]) * float(section[0]) / length)
    return stiffness


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


def _frame_transform(
    start: np.ndarray, end: np.ndarray, roll_rad: float
) -> tuple[np.ndarray, float]:
    delta = np.asarray(end, dtype=float) - np.asarray(start, dtype=float)
    length = float(np.linalg.norm(delta))
    if not math.isfinite(length) or length <= 1.0e-12:
        raise CPUReferenceError(
            "cpu_reference_zero_length_element",
            "Element length must exceed 1e-12 m.",
        )
    local_x = delta / length
    reference = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(local_x, reference))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0], dtype=float)
    local_y_zero = np.cross(reference, local_x)
    local_y_zero /= np.linalg.norm(local_y_zero)
    local_z_zero = np.cross(local_x, local_y_zero)
    cosine = math.cos(roll_rad)
    sine = math.sin(roll_rad)
    local_y = cosine * local_y_zero + sine * local_z_zero
    local_z = -sine * local_y_zero + cosine * local_z_zero
    rotation = np.vstack((local_x, local_y, local_z))
    if not np.allclose(rotation @ rotation.T, np.eye(3), rtol=0.0, atol=1.0e-12):
        raise CPUReferenceError(
            "cpu_reference_local_frame_invalid", "Element local frame is not orthonormal."
        )
    if float(np.linalg.det(rotation)) <= 0.0:
        raise CPUReferenceError(
            "cpu_reference_local_frame_left_handed", "Element local frame must be right-handed."
        )
    transform = np.zeros((_ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT), dtype="<f8")
    for block in range(4):
        offset = block * 3
        transform[offset : offset + 3, offset : offset + 3] = rotation
    return transform, length


def _validate_buffer_contract(buffers: SolverModelBuffers) -> None:
    if buffers.schema_version != SOLVER_MODEL_BUFFERS_SCHEMA_VERSION:
        raise CPUReferenceError(
            "cpu_reference_buffer_schema_mismatch",
            f"Expected {SOLVER_MODEL_BUFFERS_SCHEMA_VERSION}, got {buffers.schema_version}.",
        )
    if buffers.dof_order != DOF_ORDER:
        raise CPUReferenceError(
            "cpu_reference_dof_order_mismatch", f"Expected DOF order {DOF_ORDER}."
        )
    descriptor_names = tuple(descriptor.name for descriptor in buffers.descriptors)
    actual = set(descriptor_names)
    missing = sorted(_REQUIRED_BUFFER_NAMES - actual)
    if missing:
        raise CPUReferenceError(
            "cpu_reference_buffer_missing", f"Missing required buffers: {missing}"
        )
    unexpected = sorted(actual - _REQUIRED_BUFFER_NAMES)
    if unexpected or len(descriptor_names) != len(actual):
        raise CPUReferenceError(
            "cpu_reference_buffer_descriptor_set_invalid",
            f"Unexpected or duplicate buffer descriptors: {unexpected or list(descriptor_names)}",
        )
    expected_order = tuple(sorted(_REQUIRED_BUFFER_NAMES))
    if descriptor_names != expected_order:
        raise CPUReferenceError(
            "cpu_reference_buffer_descriptor_order_invalid",
            "SolverModelBuffers descriptors are not in canonical name order.",
        )

    arrays: dict[str, np.ndarray] = {}
    for descriptor in buffers.descriptors:
        try:
            array = buffers.array(descriptor.name)
        except KeyError as exc:
            raise CPUReferenceError(
                "cpu_reference_buffer_missing",
                f"Descriptor {descriptor.name} has no backing array.",
            ) from exc
        expected_dtype = _EXPECTED_BUFFER_DTYPES[descriptor.name]
        if array.dtype.str != expected_dtype:
            raise CPUReferenceError(
                "cpu_reference_buffer_dtype_mismatch",
                f"{descriptor.name} must use {expected_dtype}, got {array.dtype.str}.",
            )
        if not array.flags.c_contiguous or array.flags.writeable:
            raise CPUReferenceError(
                "cpu_reference_buffer_storage_invalid",
                f"{descriptor.name} must be immutable and C-contiguous.",
            )
        if _descriptor(descriptor.name, array) != descriptor:
            raise CPUReferenceError(
                "cpu_reference_buffer_descriptor_mismatch",
                f"{descriptor.name} descriptor does not match its backing bytes.",
            )
        arrays[descriptor.name] = array

    base_dimensions = {
        "node_coordinates_m": 2,
        "element_connectivity": 2,
        "material_properties_si": 2,
        "section_properties_si": 2,
    }
    for name, expected_ndim in base_dimensions.items():
        if arrays[name].ndim != expected_ndim:
            raise CPUReferenceError(
                "cpu_reference_buffer_shape_mismatch",
                f"{name} must have {expected_ndim} dimensions.",
            )
    node_count = arrays["node_coordinates_m"].shape[0]
    element_count = arrays["element_connectivity"].shape[0]
    material_count = arrays["material_properties_si"].shape[0]
    section_count = arrays["section_properties_si"].shape[0]
    if min(node_count, element_count, material_count, section_count) <= 0:
        raise CPUReferenceError(
            "cpu_reference_buffer_shape_mismatch",
            "Node, element, material, and section buffers must be non-empty.",
        )
    expected_shapes = {
        "node_coordinates_m": (node_count, 3),
        "element_connectivity": (element_count, 2),
        "element_type": (element_count,),
        "element_formulation_code": (element_count,),
        "element_material_index": (element_count,),
        "element_section_index": (element_count,),
        "material_law_code": (material_count,),
        "material_properties_si": (material_count, 3),
        "section_family_code": (section_count,),
        "section_properties_si": (section_count, 6),
        "element_local_axis_rotation_rad": (element_count,),
        "element_offsets_m": (element_count, 2, 3),
        "element_release_mask": (element_count, 2, _DOF_PER_NODE),
        "support_mask": (node_count, _DOF_PER_NODE),
        "prescribed_values_si": (node_count, _DOF_PER_NODE),
        "load_vector_si": (node_count, _DOF_PER_NODE),
    }
    for name, expected_shape in expected_shapes.items():
        if arrays[name].shape != expected_shape:
            raise CPUReferenceError(
                "cpu_reference_buffer_shape_mismatch",
                f"{name} must have shape {expected_shape}, got {arrays[name].shape}.",
            )

    for name in (
        "node_coordinates_m",
        "material_properties_si",
        "section_properties_si",
        "element_local_axis_rotation_rad",
        "element_offsets_m",
        "prescribed_values_si",
        "load_vector_si",
    ):
        if not np.all(np.isfinite(arrays[name])):
            raise CPUReferenceError(
                "cpu_reference_buffer_non_finite",
                f"{name} contains NaN or Infinity.",
            )
    for name in ("element_release_mask", "support_mask"):
        if np.any((arrays[name] != 0) & (arrays[name] != 1)):
            raise CPUReferenceError(
                "cpu_reference_buffer_mask_invalid", f"{name} must contain only 0 or 1."
            )

    try:
        actual_code_tables = {
            key: dict(value) for key, value in buffers.code_tables.items()
        }
    except (AttributeError, TypeError, ValueError) as exc:
        raise CPUReferenceError(
            "cpu_reference_code_tables_invalid", "Code tables are not valid mappings."
        ) from exc
    if actual_code_tables != _EXPECTED_CODE_TABLES:
        raise CPUReferenceError(
            "cpu_reference_code_tables_invalid",
            "SolverModelBuffers code tables do not match the CPU reference ABI.",
        )
    expected_numeric_hash = _numeric_buffer_hash(buffers.descriptors, buffers.code_tables)
    if buffers.numeric_buffer_hash != expected_numeric_hash:
        raise CPUReferenceError(
            "cpu_reference_numeric_buffer_hash_mismatch",
            "SolverModelBuffers numeric hash does not match its descriptors.",
        )

    required_entity_families = {
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
    }
    if set(buffers.entity_ids) != required_entity_families:
        raise CPUReferenceError(
            "cpu_reference_entity_mapping_invalid",
            "SolverModelBuffers entity mapping has missing or unexpected families.",
        )
    for family, ids in buffers.entity_ids.items():
        if not isinstance(ids, tuple) or any(not isinstance(value, str) for value in ids):
            raise CPUReferenceError(
                "cpu_reference_entity_mapping_invalid",
                f"Entity family {family} must contain a tuple of string IDs.",
            )
        if len(ids) != len(set(ids)):
            raise CPUReferenceError(
                "cpu_reference_entity_mapping_invalid",
                f"Entity family {family} contains duplicate IDs.",
            )
    expected_entity_counts = {
        "nodes": node_count,
        "materials": material_count,
        "sections": section_count,
        "elements": element_count,
    }
    for family, expected_count in expected_entity_counts.items():
        if len(buffers.entity_ids[family]) != expected_count:
            raise CPUReferenceError(
                "cpu_reference_entity_mapping_invalid",
                f"Entity family {family} must contain {expected_count} IDs.",
            )
    if buffers.load_pattern_id not in buffers.entity_ids["load_patterns"]:
        raise CPUReferenceError(
            "cpu_reference_entity_mapping_invalid",
            "Selected load pattern is absent from the entity mapping.",
        )
    expected_mapping_hash = _mapping_hash(buffers.entity_ids)
    if buffers.entity_mapping_hash != expected_mapping_hash:
        raise CPUReferenceError(
            "cpu_reference_entity_mapping_hash_mismatch",
            "SolverModelBuffers entity mapping hash is stale.",
        )
    expected_artifact_hash = _artifact_hash(
        model_ir_content_hash=buffers.model_ir_content_hash,
        load_pattern_id=buffers.load_pattern_id,
        numeric_buffer_hash=buffers.numeric_buffer_hash,
        entity_mapping_hash=buffers.entity_mapping_hash,
    )
    if buffers.artifact_hash != expected_artifact_hash:
        raise CPUReferenceError(
            "cpu_reference_artifact_hash_mismatch",
            "SolverModelBuffers artifact hash is stale.",
        )


def _validate_element_references(
    *,
    coordinates: np.ndarray,
    connectivity: np.ndarray,
    element_types: np.ndarray,
    formulations: np.ndarray,
    material_indices: np.ndarray,
    section_indices: np.ndarray,
    material_laws: np.ndarray,
    materials: np.ndarray,
    section_families: np.ndarray,
    sections: np.ndarray,
) -> None:
    node_count = coordinates.shape[0]
    material_count = materials.shape[0]
    section_count = sections.shape[0]
    supported_material_law = MATERIAL_LAW_CODES["linear_elastic_isotropic"]
    frame_type = ELEMENT_TYPE_CODES["frame_3d"]
    truss_type = ELEMENT_TYPE_CODES["truss_3d"]
    frame_family = SECTION_FAMILY_CODES["frame_3d"]
    truss_family = SECTION_FAMILY_CODES["truss_3d"]

    for element_index in range(connectivity.shape[0]):
        node_i = int(connectivity[element_index, 0])
        node_j = int(connectivity[element_index, 1])
        if not (0 <= node_i < node_count and 0 <= node_j < node_count):
            raise CPUReferenceError(
                "cpu_reference_connectivity_out_of_range",
                f"Element {element_index} references a node outside [0, {node_count}).",
            )
        if node_i == node_j:
            raise CPUReferenceError(
                "cpu_reference_connectivity_invalid",
                f"Element {element_index} must connect two distinct nodes.",
            )
        material_index = int(material_indices[element_index])
        section_index = int(section_indices[element_index])
        if not 0 <= material_index < material_count:
            raise CPUReferenceError(
                "cpu_reference_material_index_out_of_range",
                f"Element {element_index} material index {material_index} is out of range.",
            )
        if not 0 <= section_index < section_count:
            raise CPUReferenceError(
                "cpu_reference_section_index_out_of_range",
                f"Element {element_index} section index {section_index} is out of range.",
            )
        material_law = int(material_laws[material_index])
        if material_law != supported_material_law:
            raise CPUReferenceError(
                "cpu_reference_material_law_not_supported",
                f"Element {element_index} references unsupported material law code {material_law}.",
            )
        elastic_modulus, poisson_ratio, density = (
            float(value) for value in materials[material_index]
        )
        if elastic_modulus <= 0.0 or not -1.0 < poisson_ratio < 0.5 or density < 0.0:
            raise CPUReferenceError(
                "cpu_reference_material_properties_invalid",
                f"Element {element_index} references invalid isotropic material properties.",
            )

        element_type = int(element_types[element_index])
        formulation = int(formulations[element_index])
        section_family = int(section_families[section_index])
        section = sections[section_index]
        if element_type == frame_type:
            if formulation != ELEMENT_FORMULATION_CODES["euler_bernoulli_3d"]:
                raise CPUReferenceError(
                    "cpu_reference_formulation_not_supported",
                    f"Unsupported frame formulation code {formulation}.",
                )
            if section_family != frame_family:
                raise CPUReferenceError(
                    "cpu_reference_section_family_mismatch",
                    f"Frame element {element_index} requires section family code {frame_family}, "
                    f"got {section_family}.",
                )
            if np.any(section <= 0.0):
                raise CPUReferenceError(
                    "cpu_reference_section_properties_invalid",
                    f"Frame element {element_index} requires positive section properties.",
                )
        elif element_type == truss_type:
            if formulation != ELEMENT_FORMULATION_CODES["linear_truss_3d"]:
                raise CPUReferenceError(
                    "cpu_reference_formulation_not_supported",
                    f"Unsupported truss formulation code {formulation}.",
                )
            if section_family != truss_family:
                raise CPUReferenceError(
                    "cpu_reference_section_family_mismatch",
                    f"Truss element {element_index} requires section family code {truss_family}, "
                    f"got {section_family}.",
                )
            if float(section[0]) <= 0.0 or np.any(section[1:] != 0.0):
                raise CPUReferenceError(
                    "cpu_reference_section_properties_invalid",
                    f"Truss element {element_index} requires positive area and zero unused columns.",
                )
        else:
            raise CPUReferenceError(
                "cpu_reference_element_type_not_supported",
                f"Unsupported element type code {element_type}.",
            )


def _vector(value: np.ndarray, size: int, label: str) -> np.ndarray:
    vector = np.asarray(value, dtype="<f8").reshape(-1)
    if vector.size != size:
        raise ValueError(f"{label} must contain {size} values, got {vector.size}.")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{label} contains NaN or Infinity.")
    return vector


def _immutable_array(value: np.ndarray) -> np.ndarray:
    contiguous = np.ascontiguousarray(value)
    return np.frombuffer(contiguous.tobytes(order="C"), dtype=contiguous.dtype).reshape(
        contiguous.shape
    )


def _operator_hash(
    solver_buffer_hash: str,
    stiffness: np.ndarray,
    load: np.ndarray,
    constrained_dofs: tuple[int, ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(CPU_REFERENCE_OPERATOR_VERSION.encode("utf-8"))
    digest.update(b"\0")
    digest.update(solver_buffer_hash.encode("ascii"))
    for array in (stiffness, load):
        digest.update(b"\0")
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(memoryview(array).cast("B"))
    digest.update(b"\0")
    digest.update(json.dumps(list(constrained_dofs), separators=(",", ":")).encode("ascii"))
    return f"sha256:{digest.hexdigest()}"


def _result_hash(
    operator_hash: str,
    matrix_backend: str,
    displacement: np.ndarray,
    reactions: np.ndarray,
    element_forces: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    digest.update(operator_hash.encode("ascii"))
    digest.update(b"\0")
    digest.update(matrix_backend.encode("ascii"))
    for array in (displacement, reactions, element_forces):
        digest.update(b"\0")
        digest.update(memoryview(array).cast("B"))
    return f"sha256:{digest.hexdigest()}"
