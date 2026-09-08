"""Complete trial-state recovery in CSR storage, without global dense matrices.

This is a storage contract, not a convergence or independent constitutive proof.
Member responses come from one native material trial pass. Public source replay
still establishes the physical authority of accepted engineering results.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from structural_analysis.assembly.corotational_frame2d_member_features import (
    expected_element_displacements,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMemberAssembly,
    StatefulCorotationalFiberFrame2DProblem,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse import (
    _assemble_native_trial,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2DState,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA

COROTATIONAL_FIBER_FRAME_SPARSE_STATE_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-sparse-state.v1"
)
COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE = (
    "member-scatter-canonical-csr-fp64.v1"
)
_VECTOR_NAMES = (
    "generalized_coordinates_m",
    "global_displacements",
    "residual_kn",
    "residual_load_factor_derivative_kn",
    "partial_residual_load_factor_derivative_global",
    "internal_loads_global",
    "external_loads_global",
    "reactions_global",
)
_MATRIX_NAMES = (
    "jacobian",
    "material_tangent",
    "geometric_tangent",
    "consistent_tangent",
)


def _array(value: Any, dtype: str, shape: tuple[int, ...], name: str) -> None:
    if (
        type(value) is not np.ndarray
        or value.dtype.str != dtype
        or value.shape != shape
        or not value.flags.c_contiguous
        or not has_immutable_bytes_backing(value)
        or not np.all(np.isfinite(value))
    ):
        raise ValueError(
            f"{name} requires finite immutable {dtype} bytes with shape {shape}"
        )


@dataclass(frozen=True)
class CorotationalFiberFrameCSR:
    """Canonical immutable CSR bytes; every exported SciPy matrix is detached."""

    shape: tuple[int, int]
    row_ptr: np.ndarray
    column_indices: np.ndarray
    values: np.ndarray
    nnz: int = field(init=False)
    pattern_hash: str = field(init=False)
    numeric_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_csr(self, hashes=False)
        object.__setattr__(self, "nnz", self.values.size)
        object.__setattr__(self, "pattern_hash", _pattern_hash(self))
        object.__setattr__(self, "numeric_hash", array_data_hash(self.values))

    def to_csr(self) -> csr_matrix:
        _validate_csr(self)
        return csr_matrix(
            (self.values.copy(), self.column_indices.copy(), self.row_ptr.copy()),
            shape=self.shape,
            dtype=np.float64,
        )

    def to_dict(self) -> dict[str, Any]:
        _validate_csr(self)
        return {
            "shape": list(self.shape),
            "index_dtype": "<i8",
            "value_dtype": "<f8",
            "row_ptr": self.row_ptr.tolist(),
            "column_indices": self.column_indices.tolist(),
            "values": self.values.tolist(),
            "nnz": self.nnz,
            "pattern_hash": self.pattern_hash,
            "numeric_hash": self.numeric_hash,
        }


def _pattern_hash(matrix: CorotationalFiberFrameCSR) -> str:
    return canonical_hash(
        {
            "shape": list(matrix.shape),
            "row_ptr": matrix.row_ptr.tolist(),
            "column_indices": matrix.column_indices.tolist(),
        }
    )


def _validate_csr(matrix: CorotationalFiberFrameCSR, *, hashes: bool = True) -> None:
    if type(matrix) is not CorotationalFiberFrameCSR:
        raise ValueError("CSR matrix type is invalid")
    if (
        type(matrix.shape) is not tuple
        or len(matrix.shape) != 2
        or any(type(size) is not int or size < 0 for size in matrix.shape)
    ):
        raise ValueError("CSR shape must contain two non-negative integers")
    if type(matrix.values) is not np.ndarray or matrix.values.ndim != 1:
        raise ValueError("CSR values must be a vector")
    count = matrix.values.size
    _array(matrix.row_ptr, "<i8", (matrix.shape[0] + 1,), "CSR row_ptr")
    _array(matrix.column_indices, "<i8", (count,), "CSR column_indices")
    _array(matrix.values, "<f8", (count,), "CSR values")
    if (
        matrix.row_ptr[0] != 0
        or matrix.row_ptr[-1] != count
        or np.any(np.diff(matrix.row_ptr) < 0)
        or np.any(matrix.column_indices < 0)
        or np.any(matrix.column_indices >= matrix.shape[1])
        or np.any(matrix.values == 0.0)
    ):
        raise ValueError("CSR structure is not canonical")
    for start, stop in zip(matrix.row_ptr[:-1], matrix.row_ptr[1:], strict=True):
        if np.any(np.diff(matrix.column_indices[start:stop]) <= 0):
            raise ValueError("CSR columns must be sorted and unique within each row")
    if hashes and (
        type(matrix.nnz) is not int
        or matrix.nnz != count
        or matrix.pattern_hash != _pattern_hash(matrix)
        or matrix.numeric_hash != array_data_hash(matrix.values)
    ):
        raise ValueError("CSR counts or hashes are stale")


def _canonical_csr(matrix: csr_matrix) -> csr_matrix:
    result = matrix.tocsr(copy=True)
    result.sum_duplicates()
    result.eliminate_zeros()
    result.sort_indices()
    return result


def _freeze_csr(matrix: csr_matrix) -> CorotationalFiberFrameCSR:
    result = _canonical_csr(matrix)
    return CorotationalFiberFrameCSR(
        shape=result.shape,
        row_ptr=immutable_array(result.indptr, dtype="<i8"),
        column_indices=immutable_array(result.indices, dtype="<i8"),
        values=immutable_array(result.data, dtype="<f8"),
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DSparseAssembly:
    schema_version: str
    storage_profile: str
    problem_contract_hash: str
    parent_checkpoint_hash: str
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    residual_load_factor_derivative_kn: np.ndarray
    partial_residual_load_factor_derivative_global: np.ndarray
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    jacobian: CorotationalFiberFrameCSR
    material_tangent: CorotationalFiberFrameCSR
    geometric_tangent: CorotationalFiberFrameCSR
    consistent_tangent: CorotationalFiberFrameCSR
    member_assemblies: tuple[StatefulCorotationalFiberFrame2DMemberAssembly, ...]
    trial_element_states: tuple[StatefulCorotationalFiberBeam2DState, ...]
    _source_problem: StatefulCorotationalFiberFrame2DProblem = field(
        repr=False, compare=False
    )
    _source_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint = field(
        repr=False, compare=False
    )
    assembly_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_assembly(self, check_hash=False)
        object.__setattr__(
            self, "assembly_hash", canonical_hash(_assembly_payload(self))
        )

    @property
    def jacobian_csr(self) -> csr_matrix:
        return self.jacobian.to_csr()

    @property
    def material_tangent_global_csr(self) -> csr_matrix:
        return self.material_tangent.to_csr()

    @property
    def geometric_tangent_global_csr(self) -> csr_matrix:
        return self.geometric_tangent.to_csr()

    @property
    def consistent_tangent_global_csr(self) -> csr_matrix:
        return self.consistent_tangent.to_csr()

    def to_dict(self) -> dict[str, Any]:
        validate_stateful_corotational_fiber_frame2d_sparse_assembly(self)
        return {**_assembly_payload(self), "assembly_hash": self.assembly_hash}


def _assembly_payload(
    assembly: StatefulCorotationalFiberFrame2DSparseAssembly,
) -> dict[str, Any]:
    return {
        "schema_version": assembly.schema_version,
        "storage_profile": assembly.storage_profile,
        "residual_formula": RESIDUAL_FORMULA,
        "problem_contract_hash": assembly.problem_contract_hash,
        "parent_checkpoint_hash": assembly.parent_checkpoint_hash,
        "target_load_factor": assembly.target_load_factor,
        "free_global_dofs": list(assembly.free_global_dofs),
        **{name: getattr(assembly, name).tolist() for name in _VECTOR_NAMES},
        **{name + "_csr": getattr(assembly, name).to_dict() for name in _MATRIX_NAMES},
        "member_assemblies": [row.to_dict() for row in assembly.member_assemblies],
        "trial_element_state_hashes": [
            state.state_hash for state in assembly.trial_element_states
        ],
    }


def _scatter_tangents(
    rows: tuple[StatefulCorotationalFiberFrame2DMemberAssembly, ...],
    global_count: int,
) -> tuple[csr_matrix, csr_matrix, csr_matrix]:
    indices_i: list[int] = []
    indices_j: list[int] = []
    material: list[float] = []
    geometric: list[float] = []
    for row in rows:
        for local_i, global_i in enumerate(row.global_dofs):
            for local_j, global_j in enumerate(row.global_dofs):
                indices_i.append(global_i)
                indices_j.append(global_j)
                material.append(float(row.material_tangent_global[local_i, local_j]))
                geometric.append(float(row.geometric_tangent_global[local_i, local_j]))
    shape = (global_count, global_count)
    first = _canonical_csr(coo_matrix((material, (indices_i, indices_j)), shape=shape))
    second = _canonical_csr(
        coo_matrix((geometric, (indices_i, indices_j)), shape=shape)
    )
    return first, second, _canonical_csr(first + second)


def _scatter_jacobian(
    rows: tuple[StatefulCorotationalFiberFrame2DMemberAssembly, ...],
    free_dofs: tuple[int, ...],
    scale: np.ndarray,
) -> csr_matrix:
    positions = {dof: index for index, dof in enumerate(free_dofs)}
    indices_i: list[int] = []
    indices_j: list[int] = []
    values: list[float] = []
    for row in rows:
        for i, global_i in enumerate(row.global_dofs):
            if global_i not in positions:
                continue
            for j, global_j in enumerate(row.global_dofs):
                if global_j in positions:
                    indices_i.append(positions[global_i])
                    indices_j.append(positions[global_j])
                    values.append(
                        float(
                            scale[global_i]
                            * row.consistent_tangent_global[i, j]
                            * scale[global_j]
                        )
                    )
    return _canonical_csr(
        coo_matrix(
            (values, (indices_i, indices_j)), shape=(len(free_dofs), len(free_dofs))
        )
    )


def _same_csr(
    actual: CorotationalFiberFrameCSR, expected: csr_matrix, name: str
) -> None:
    canonical = _freeze_csr(expected)
    if actual.to_dict() != canonical.to_dict():
        raise ValueError(f"{name} does not bind the member tangent scatter")


def _require_equal(actual: np.ndarray, expected: Any, name: str) -> None:
    if not np.array_equal(actual, expected):
        raise ValueError(f"{name} does not bind the member/source state")


def _validate_assembly(
    assembly: StatefulCorotationalFiberFrame2DSparseAssembly, *, check_hash: bool = True
) -> None:
    if type(assembly) is not StatefulCorotationalFiberFrame2DSparseAssembly:
        raise ValueError("sparse assembly type is invalid")
    if (
        assembly.schema_version != COROTATIONAL_FIBER_FRAME_SPARSE_STATE_SCHEMA_VERSION
        or assembly.storage_profile
        != COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE
    ):
        raise ValueError("sparse assembly schema or storage profile is invalid")
    problem, parent = assembly._source_problem, assembly._source_checkpoint
    if type(problem) is not StatefulCorotationalFiberFrame2DProblem:
        raise ValueError("sparse assembly source problem type is invalid")
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, parent)
    if (
        assembly.problem_contract_hash != problem.contract_hash
        or assembly.parent_checkpoint_hash != parent.state_hash
    ):
        raise ValueError("sparse assembly source binding is stale")
    if type(assembly.target_load_factor) is not float or not np.isfinite(
        assembly.target_load_factor
    ):
        raise ValueError("sparse target load factor must be a finite float")
    if (
        type(assembly.free_global_dofs) is not tuple
        or any(type(dof) is not int for dof in assembly.free_global_dofs)
        or assembly.free_global_dofs != problem.free_global_dofs
    ):
        raise ValueError("sparse free DOF binding is invalid")
    global_count, free_count = problem.global_dof_count, len(problem.free_global_dofs)
    for name in _VECTOR_NAMES:
        count = (
            free_count
            if name in ("residual_kn", "residual_load_factor_derivative_kn")
            else global_count
        )
        _array(getattr(assembly, name), "<f8", (count,), name)
    for name in _MATRIX_NAMES:
        matrix = getattr(assembly, name)
        _validate_csr(matrix)
        count = free_count if name == "jacobian" else global_count
        if matrix.shape != (count, count):
            raise ValueError(f"{name} shape does not bind the problem")
    scale = np.asarray(problem.physical_coordinate_scale, dtype=np.float64)
    physical = scale * assembly.generalized_coordinates_m
    prescribed = problem.prescribed_displacement_vector(assembly.target_load_factor)
    fixed = list(problem.fixed_global_dofs)
    prescribed_dofs = [dof for dof, _value in problem.prescribed_displacements]
    physical[prescribed_dofs] = prescribed[prescribed_dofs]
    _require_equal(assembly.global_displacements, physical, "physical coordinates")
    _require_equal(
        assembly.global_displacements[fixed],
        prescribed[fixed],
        "prescribed coordinates",
    )
    _require_equal(
        assembly.generalized_coordinates_m[fixed],
        prescribed[fixed] / scale[fixed],
        "prescribed generalized coordinates",
    )
    if (
        type(assembly.member_assemblies) is not tuple
        or type(assembly.trial_element_states) is not tuple
        or len(assembly.member_assemblies) != len(problem.members)
        or len(assembly.trial_element_states) != len(problem.members)
    ):
        raise ValueError("sparse member/state coverage is invalid")
    internal = np.zeros(global_count, dtype=np.float64)
    external = assembly.target_load_factor * problem.reference_external_load_vector()
    partial = -problem.reference_external_load_vector().copy()
    for member, row, state, parent_state in zip(
        problem.members,
        assembly.member_assemblies,
        assembly.trial_element_states,
        parent.element_states,
        strict=True,
    ):
        if (
            type(row) is not StatefulCorotationalFiberFrame2DMemberAssembly
            or type(state) is not StatefulCorotationalFiberBeam2DState
        ):
            raise ValueError("sparse member/state type is invalid")
        replace(row)
        replace(row.response)
        replace(row.feature_response)
        feature_payload = row.feature_response.to_dict()
        stored_hash = feature_payload.pop("response_hash")
        if stored_hash != canonical_hash(feature_payload):
            raise ValueError("sparse member feature response hash is stale")
        if (
            row.member_id != member.member_id
            or row.global_dofs != problem.member_global_dofs(member)
            or row.response.parent_state_hash != parent_state.state_hash
            or row.feature_response.feature_contract_hash
            != member.features.contract_hash
            or row.feature_response.target_load_factor != assembly.target_load_factor
            or row.response.state.canonical_bytes() != state.canonical_bytes()
            or state.step_index != parent_state.step_index + 1
        ):
            raise ValueError("sparse member/state source binding is invalid")
        member.element.validate_state(state)
        released = tuple(
            state.element_displacements[dof]
            for dof in member.features.released_element_dofs
        )
        expected = expected_element_displacements(
            assembly.global_displacements[list(row.global_dofs)],
            member.features,
            released_rotations_rad=released,
        )
        _require_equal(
            np.asarray(state.element_displacements), expected, "member displacement"
        )
        internal[list(row.global_dofs)] += row.internal_load_global
        external[list(row.global_dofs)] += row.equivalent_external_load_global
        partial[list(row.global_dofs)] += (
            row.feature_response.load_factor_residual_derivative_global
        )
    for name, expected in (
        ("internal_loads_global", internal),
        ("external_loads_global", external),
        ("partial_residual_load_factor_derivative_global", partial),
    ):
        _require_equal(getattr(assembly, name), expected, name)
    free = list(problem.free_global_dofs)
    residual = internal - external
    _require_equal(assembly.residual_kn, scale[free] * residual[free], "residual")
    reactions = np.zeros(global_count, dtype=np.float64)
    reactions[fixed] = residual[fixed]
    _require_equal(assembly.reactions_global, reactions, "reactions")
    material, geometric, consistent = _scatter_tangents(
        assembly.member_assemblies, global_count
    )
    for name, expected in (
        ("material_tangent", material),
        ("geometric_tangent", geometric),
        ("consistent_tangent", consistent),
    ):
        _same_csr(getattr(assembly, name), expected, name)
    _same_csr(
        assembly.jacobian,
        _scatter_jacobian(assembly.member_assemblies, problem.free_global_dofs, scale),
        "jacobian",
    )
    derivative = partial + consistent @ problem.prescribed_displacement_vector(1.0)
    _require_equal(
        assembly.residual_load_factor_derivative_kn,
        scale[free] * derivative[free],
        "load-factor derivative",
    )
    if check_hash and assembly.assembly_hash != canonical_hash(
        _assembly_payload(assembly)
    ):
        raise ValueError("sparse assembly hash is stale")


def validate_stateful_corotational_fiber_frame2d_sparse_assembly(
    assembly: StatefulCorotationalFiberFrame2DSparseAssembly,
    *,
    problem: StatefulCorotationalFiberFrame2DProblem | None = None,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
) -> StatefulCorotationalFiberFrame2DSparseAssembly:
    _validate_assembly(assembly)
    if problem is not None and (
        type(problem) is not StatefulCorotationalFiberFrame2DProblem
        or problem.contract_hash != assembly.problem_contract_hash
    ):
        raise ValueError("sparse assembly does not bind the supplied problem")
    if checkpoint is not None and (
        type(checkpoint) is not StatefulCorotationalFiberFrame2DCheckpoint
        or checkpoint.canonical_bytes() != assembly._source_checkpoint.canonical_bytes()
    ):
        raise ValueError("sparse assembly does not bind the supplied parent checkpoint")
    return assembly


def assemble_stateful_corotational_fiber_frame2d_sparse_state(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> StatefulCorotationalFiberFrame2DSparseAssembly:
    native, rows = _assemble_native_trial(
        problem,
        checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
        collect_member_states=True,
    )
    material, geometric, consistent = _scatter_tangents(rows, problem.global_dof_count)
    partial = -problem.reference_external_load_vector().copy()
    for row in rows:
        partial[list(row.global_dofs)] += (
            row.feature_response.load_factor_residual_derivative_global
        )
    derivative = partial + consistent @ problem.prescribed_displacement_vector(1.0)
    scale = np.asarray(problem.physical_coordinate_scale, dtype=np.float64)
    free = list(problem.free_global_dofs)
    return StatefulCorotationalFiberFrame2DSparseAssembly(
        schema_version=COROTATIONAL_FIBER_FRAME_SPARSE_STATE_SCHEMA_VERSION,
        storage_profile=COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE,
        problem_contract_hash=problem.contract_hash,
        parent_checkpoint_hash=checkpoint.state_hash,
        target_load_factor=native.target_load_factor,
        free_global_dofs=problem.free_global_dofs,
        generalized_coordinates_m=native.generalized_coordinates_m,
        global_displacements=native.global_displacements,
        residual_kn=native.residual_kn,
        residual_load_factor_derivative_kn=immutable_array(
            scale[free] * derivative[free], dtype="<f8"
        ),
        partial_residual_load_factor_derivative_global=immutable_array(
            partial, dtype="<f8"
        ),
        internal_loads_global=native.internal_loads_global,
        external_loads_global=native.external_loads_global,
        reactions_global=native.reactions_global,
        jacobian=CorotationalFiberFrameCSR(
            shape=(len(free), len(free)),
            row_ptr=native.csr_row_ptr,
            column_indices=native.csr_column_indices,
            values=native.csr_values_kn_per_m,
        ),
        material_tangent=_freeze_csr(material),
        geometric_tangent=_freeze_csr(geometric),
        consistent_tangent=_freeze_csr(consistent),
        member_assemblies=rows,
        trial_element_states=tuple(row.response.state for row in rows),
        _source_problem=problem,
        _source_checkpoint=checkpoint,
    )


__all__ = [
    "COROTATIONAL_FIBER_FRAME_SPARSE_STATE_SCHEMA_VERSION",
    "COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE",
    "CorotationalFiberFrameCSR",
    "StatefulCorotationalFiberFrame2DSparseAssembly",
    "assemble_stateful_corotational_fiber_frame2d_sparse_state",
    "validate_stateful_corotational_fiber_frame2d_sparse_assembly",
]
