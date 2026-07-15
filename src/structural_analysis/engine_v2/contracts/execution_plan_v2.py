"""Sparse-only Engine v2 ExecutionPlan v2 for the Phase 0 frame/truss scope.

This compiler deliberately never materializes a global ``(G, G)`` stiffness
array.  It builds a sorted CSR symbolic plan first and accumulates each 12 by
12 element contribution directly into the retained CSR slots in element order
and local-row-major order.

Frame/truss formulas and local-frame policy come from the versioned,
backend-neutral element semantics module.  The historical source operator
version remains in serialized hashes for byte-for-byte artifact compatibility;
the separate source semantics version identifies the refactored code boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import (
    BufferDescriptor,
    DOF_ORDER,
    ELEMENT_FORMULATION_CODES,
    ELEMENT_TYPE_CODES,
    SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
    SolverModelBuffers,
    SolverModelBufferError,
    validate_solver_model_buffers,
)
from structural_analysis.engine_v2.elements.linear_frame_truss_v1 import (
    LINEAR_FRAME_TRUSS_ELEMENT_SEMANTICS_VERSION_V1,
    LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1,
    LinearFrameTrussV1Error,
    frame_local_stiffness_v1,
    frame_transform_v1,
    truss_local_stiffness_v1,
    validate_linear_frame_truss_references_v1,
)

from ._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)

EXECUTION_PLAN_V2_SCHEMA_VERSION = "structural-analysis-execution-plan.v2"
EXECUTION_PLAN_V2_CAPABILITY_PROFILE = "phase0_sparse_cpu_direct_linear_static"
SPARSE_CPU_OPERATOR_VERSION = "engine-v2-cpu-direct-csr-linear-static.v2"
SOURCE_ELEMENT_OPERATOR_VERSION = LINEAR_FRAME_TRUSS_OPERATOR_COMPATIBILITY_VERSION_V1
SOURCE_ELEMENT_SEMANTICS_VERSION = LINEAR_FRAME_TRUSS_ELEMENT_SEMANTICS_VERSION_V1

_DOFS_PER_NODE = len(DOF_ORDER)
_ELEMENT_DOF_COUNT = 2 * _DOFS_PER_NODE
_INT32_MAX = int(np.iinfo(np.int32).max)
_ASSEMBLY_ORDER = "element_index_then_local_row_then_local_column_v1"
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))

_INDEX_ARRAY_NAMES = (
    "node_dof_indices",
    "global_to_free",
    "element_global_dofs",
    "constrained_dofs",
    "free_dofs",
    "csr_row_ptr",
    "csr_column_indices",
    "csr_diagonal_positions",
    "csr_element_scatter_indices",
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_global_value_indices",
)
_FLOAT_ARRAY_NAMES = (
    "global_stiffness_csr_values",
    "reduced_stiffness_csr_values",
    "global_load",
    "recovery_transform_global_to_local",
    "recovery_stiffness_local",
)
_ARRAY_NAMES = _INDEX_ARRAY_NAMES + _FLOAT_ARRAY_NAMES
_SYMBOLIC_HASH_ARRAY_NAMES = (
    "element_global_dofs",
    "global_to_free",
    "constrained_dofs",
    "free_dofs",
    "csr_row_ptr",
    "csr_column_indices",
    "csr_diagonal_positions",
    "csr_element_scatter_indices",
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_global_value_indices",
)
_NUMERIC_HASH_ARRAY_NAMES = (
    "global_stiffness_csr_values",
    "reduced_stiffness_csr_values",
    "global_load",
    "recovery_transform_global_to_local",
    "recovery_stiffness_local",
)


class ExecutionPlanV2Error(ValueError):
    """Fail-closed v2 plan error with stable code and JSON pointer."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class PlanArrayDescriptorV2:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class ExecutionPlanV2:
    """Immutable sparse-only compiled artifact.

    ``_source_buffers`` is retained solely so validation can independently
    reconstruct the supported element numerics and reject coherently rehashed
    local-operator tampering.  It does not contain a compiled global matrix,
    but its referenced bytes are outside ``described_array_byte_length``.
    """

    schema_version: str
    capability_profile: str
    plan_id: str
    plan_hash: str
    model_ir_content_hash: str
    solver_buffer_schema_version: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    load_pattern_id: str
    operator_version: str
    source_element_operator_version: str
    operator_hash: str
    recovery_operator_hash: str
    symbolic_reuse_hash: str
    numeric_snapshot_hash: str
    partition_hash: str
    ordering_hash: str
    node_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    node_count: int
    element_count: int
    dof_count: int
    residual_tolerance: float
    descriptors: tuple[PlanArrayDescriptorV2, ...]
    _arrays: tuple[np.ndarray, ...]
    _source_buffers: SolverModelBuffers

    def array(self, name: str) -> np.ndarray:
        try:
            index = _ARRAY_NAMES.index(name)
        except ValueError as exc:
            raise KeyError(f"Unknown ExecutionPlan v2 array: {name}") from exc
        return self._arrays[index]

    @property
    def constrained_dofs(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.array("constrained_dofs"))

    @property
    def free_dofs(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.array("free_dofs"))

    @property
    def described_array_byte_length(self) -> int:
        """Bytes of descriptor-listed retained plan arrays only.

        This excludes the strong ``_source_buffers`` reference, Python object
        overhead, transient symbolic compiler state, SciPy state, and manifest
        lists created by :meth:`to_dict`.
        """

        return sum(row.byte_length for row in self.descriptors)

    @property
    def nnz(self) -> int:
        return int(self.array("csr_column_indices").size)

    @property
    def reduced_nnz(self) -> int:
        return int(self.array("reduced_csr_column_indices").size)

    def residual(self, displacement: np.ndarray) -> np.ndarray:
        vector = _finite_vector(displacement, self.dof_count, "displacement")
        result = _csr_matvec(
            self.array("csr_row_ptr"),
            self.array("csr_column_indices"),
            self.array("global_stiffness_csr_values"),
            vector,
        )
        result -= self.array("global_load")
        return result

    def jvp(self, direction: np.ndarray) -> np.ndarray:
        vector = _finite_vector(direction, self.dof_count, "direction")
        return _csr_matvec(
            self.array("csr_row_ptr"),
            self.array("csr_column_indices"),
            self.array("global_stiffness_csr_values"),
            vector,
        )

    def to_dict(self) -> dict[str, Any]:
        descriptors = {row.name: row.to_dict() for row in self.descriptors}
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "plan_id": self.plan_id,
            "input_binding": {
                "model_ir_content_hash": self.model_ir_content_hash,
                "solver_buffer_schema_version": self.solver_buffer_schema_version,
                "solver_numeric_buffer_hash": self.solver_numeric_buffer_hash,
                "solver_entity_mapping_hash": self.solver_entity_mapping_hash,
                "solver_artifact_hash": self.solver_artifact_hash,
                "load_pattern_id": self.load_pattern_id,
            },
            "analysis": {
                "type": "linear_static",
                "residual_sign": "internal_minus_external",
                "operator_version": self.operator_version,
                "source_element_operator_version": (
                    self.source_element_operator_version
                ),
                "operator_hash": self.operator_hash,
                "recovery_operator_hash": self.recovery_operator_hash,
                "numeric_snapshot_hash": self.numeric_snapshot_hash,
            },
            "entity_order": {
                "node_ids": list(self.node_ids),
                "element_ids": list(self.element_ids),
                "ordering_hash": self.ordering_hash,
            },
            "dof_layout": {
                "components": list(DOF_ORDER),
                "node_count": self.node_count,
                "element_count": self.element_count,
                "dofs_per_node": _DOFS_PER_NODE,
                "dof_count": self.dof_count,
                "index_base": 0,
                "index_dtype": "<i4",
                "node_dof_indices": self.array("node_dof_indices").tolist(),
                "element_global_dofs": self.array("element_global_dofs").tolist(),
                "global_to_free": self.array("global_to_free").tolist(),
            },
            "constraint_partition": {
                "constrained_dofs": self.array("constrained_dofs").tolist(),
                "free_dofs": self.array("free_dofs").tolist(),
                "prescribed_displacement_mode": "zero_only",
                "partition_hash": self.partition_hash,
            },
            "symbolic_plan": {
                "format": "csr",
                "shape": [self.dof_count, self.dof_count],
                "row_ptr": self.array("csr_row_ptr").tolist(),
                "column_indices": self.array("csr_column_indices").tolist(),
                "diagonal_positions": self.array("csr_diagonal_positions").tolist(),
                "element_scatter_indices": self.array(
                    "csr_element_scatter_indices"
                ).tolist(),
                "reduced_shape": [len(self.free_dofs), len(self.free_dofs)],
                "reduced_row_ptr": self.array("reduced_csr_row_ptr").tolist(),
                "reduced_column_indices": self.array(
                    "reduced_csr_column_indices"
                ).tolist(),
                "reduced_global_value_indices": self.array(
                    "reduced_csr_global_value_indices"
                ).tolist(),
                "nnz": self.nnz,
                "reduced_nnz": self.reduced_nnz,
                "sorted_columns": True,
                "symmetric_pattern": True,
                "structural_zero_slots_retained": True,
                "assembly_order": _ASSEMBLY_ORDER,
                "symbolic_reuse_hash": self.symbolic_reuse_hash,
            },
            "numeric_snapshot": {
                "scalar_type": "<f8",
                "signed_zero_normalized": True,
                "structural_zero_count": int(
                    np.count_nonzero(self.array("global_stiffness_csr_values") == 0.0)
                ),
                "described_array_byte_length": self.described_array_byte_length,
                "arrays": [descriptors[name] for name in _ARRAY_NAMES],
                "numeric_snapshot_hash": self.numeric_snapshot_hash,
            },
            "solver_policy": {
                "linear_solver": "scipy_sparse_direct",
                "solver_permutation": "NATURAL",
                "residual_tolerance": self.residual_tolerance,
                "fallback_policy": "forbidden",
            },
            "claim_boundary": {
                "global_dense_matrix_materialized": False,
                "symbolic_and_numeric_compile_complexity": (
                    "O(E*12^3+sum_r(z_r*log(z_r))+nnz)"
                ),
                "direct_scatter_complexity": "O(E*12^2+nnz)",
                "bounded_row_degree_compile_note": (
                    "O(E+nnz)_only_when_element_rank_and_row_degree_are_bounded"
                ),
                "residual_jvp_complexity": "O(nnz)",
                "direct_solve_complexity_claim": "not_O_N",
                "end_to_end_O_N_claim": False,
                "supported_scope": (
                    "zero_offset_zero_release_zero_prescribed_linear_3d_frame_truss"
                ),
            },
            "plan_hash": self.plan_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def compile_execution_plan_v2(
    buffers: SolverModelBuffers,
    *,
    residual_tolerance: float = 1.0e-10,
) -> ExecutionPlanV2:
    """Compile a deterministic sparse-only plan and validate it immediately."""

    _validate_tolerance(residual_tolerance)
    _validate_supported_buffers(buffers)

    node_ids = tuple(buffers.entity_ids["nodes"])
    element_ids = tuple(buffers.entity_ids["elements"])
    node_count = len(node_ids)
    element_count = len(element_ids)
    dof_count = node_count * _DOFS_PER_NODE
    if dof_count > _INT32_MAX:
        _raise(
            "execution_plan_v2_int32_capacity_exceeded",
            "/dof_layout/dof_count",
            "Global DOF count exceeds the int32 sparse ABI.",
        )

    constrained, free, global_to_free = _compile_partition(buffers, dof_count)
    element_dofs, transforms, local_stiffness = _compile_element_numeric(buffers)
    symbolic = _compile_symbolic_pattern(
        dof_count=dof_count,
        element_global_dofs=element_dofs,
        free_dofs=free,
        global_to_free=global_to_free,
    )
    values = _assemble_csr_values(
        transforms,
        local_stiffness,
        symbolic["csr_element_scatter_indices"],
        int(symbolic["csr_column_indices"].size),
    )
    reduced_values = _normalize_float_array(
        values[symbolic["reduced_csr_global_value_indices"]]
    )
    load = _normalize_float_array(buffers.array("load_vector_si").reshape(-1))
    node_dofs = np.arange(dof_count, dtype="<i4").reshape(node_count, _DOFS_PER_NODE)

    raw_arrays: dict[str, np.ndarray] = {
        "node_dof_indices": node_dofs,
        "global_to_free": global_to_free,
        "element_global_dofs": element_dofs,
        "constrained_dofs": constrained,
        "free_dofs": free,
        **symbolic,
        "global_stiffness_csr_values": values,
        "reduced_stiffness_csr_values": reduced_values,
        "global_load": load,
        "recovery_transform_global_to_local": transforms,
        "recovery_stiffness_local": local_stiffness,
    }
    arrays = {
        name: immutable_array(
            raw_arrays[name],
            dtype="<f8" if name in _FLOAT_ARRAY_NAMES else "<i4",
        )
        for name in _ARRAY_NAMES
    }
    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES)
    descriptor_map = {row.name: row for row in descriptors}

    ordering_hash = canonical_hash(
        {
            "node_ids": list(node_ids),
            "element_ids": list(element_ids),
            "entity_mapping_hash": buffers.entity_mapping_hash,
            "dof_order": list(DOF_ORDER),
            "element_end_order": ["i", "j"],
        }
    )
    partition_hash = _partition_hash(descriptor_map)
    symbolic_reuse_hash = _symbolic_reuse_hash(
        descriptor_map, dof_count=dof_count, free_count=free.size
    )
    recovery_hash = _recovery_hash(
        element_ids,
        descriptor_map,
    )
    numeric_hash = _numeric_snapshot_hash(
        descriptor_map,
        recovery_operator_hash=recovery_hash,
        solver_numeric_buffer_hash=buffers.numeric_buffer_hash,
    )
    operator_hash = _operator_hash(
        numeric_snapshot_hash=numeric_hash,
        partition_hash=partition_hash,
        symbolic_reuse_hash=symbolic_reuse_hash,
    )
    seed = canonical_hash(
        {
            "solver_artifact_hash": buffers.artifact_hash,
            "symbolic_reuse_hash": symbolic_reuse_hash,
            "numeric_snapshot_hash": numeric_hash,
            "residual_tolerance": float(residual_tolerance),
        }
    )
    zero_hash = "sha256:" + "0" * 64
    plan = ExecutionPlanV2(
        schema_version=EXECUTION_PLAN_V2_SCHEMA_VERSION,
        capability_profile=EXECUTION_PLAN_V2_CAPABILITY_PROFILE,
        plan_id=f"SparsePlan:{seed.removeprefix('sha256:')[:24]}",
        plan_hash=zero_hash,
        model_ir_content_hash=buffers.model_ir_content_hash,
        solver_buffer_schema_version=buffers.schema_version,
        solver_numeric_buffer_hash=buffers.numeric_buffer_hash,
        solver_entity_mapping_hash=buffers.entity_mapping_hash,
        solver_artifact_hash=buffers.artifact_hash,
        load_pattern_id=buffers.load_pattern_id,
        operator_version=SPARSE_CPU_OPERATOR_VERSION,
        source_element_operator_version=SOURCE_ELEMENT_OPERATOR_VERSION,
        operator_hash=operator_hash,
        recovery_operator_hash=recovery_hash,
        symbolic_reuse_hash=symbolic_reuse_hash,
        numeric_snapshot_hash=numeric_hash,
        partition_hash=partition_hash,
        ordering_hash=ordering_hash,
        node_ids=node_ids,
        element_ids=element_ids,
        node_count=node_count,
        element_count=element_count,
        dof_count=dof_count,
        residual_tolerance=float(residual_tolerance),
        descriptors=descriptors,
        _arrays=tuple(arrays[name] for name in _ARRAY_NAMES),
        _source_buffers=_detached_source_snapshot(buffers),
    )
    plan = replace(plan, plan_hash=_plan_hash(plan))
    validate_execution_plan_v2(plan, expected_buffers=buffers)
    return plan


def validate_execution_plan_v2(
    plan: ExecutionPlanV2,
    *,
    expected_buffers: SolverModelBuffers | None = None,
) -> None:
    """Validate storage, source numerics, independent assembly, and all hashes."""

    if type(plan) is not ExecutionPlanV2:
        _raise(
            "execution_plan_v2_type_invalid",
            "/",
            "Expected an ExecutionPlanV2 instance.",
        )
    if (
        type(plan.descriptors) is not tuple
        or any(type(row) is not PlanArrayDescriptorV2 for row in plan.descriptors)
        or type(plan._arrays) is not tuple
        or len(plan._arrays) != len(_ARRAY_NAMES)
        or any(type(array) is not np.ndarray for array in plan._arrays)
        or type(plan.node_ids) is not tuple
        or type(plan.element_ids) is not tuple
    ):
        _fail("execution_plan_v2_container_invalid", "/numeric_snapshot")
    if type(plan._source_buffers) is not SolverModelBuffers:
        _fail("execution_plan_v2_source_buffer_invalid", "/input_binding")
    try:
        manifest = plan.to_dict()
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionPlanV2Error(
            "execution_plan_v2_manifest_invalid", "/", f"Cannot build manifest: {exc}"
        ) from exc
    errors = sorted(
        _plan_validator().iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ExecutionPlanV2Error(
            "execution_plan_v2_schema_invalid", path, error.message
        )

    if plan.schema_version != EXECUTION_PLAN_V2_SCHEMA_VERSION:
        _fail("execution_plan_v2_schema_mismatch", "/schema_version")
    if plan.capability_profile != EXECUTION_PLAN_V2_CAPABILITY_PROFILE:
        _fail("execution_plan_v2_profile_mismatch", "/capability_profile")
    if plan.operator_version != SPARSE_CPU_OPERATOR_VERSION:
        _fail(
            "execution_plan_v2_operator_version_mismatch", "/analysis/operator_version"
        )
    if plan.source_element_operator_version != SOURCE_ELEMENT_OPERATOR_VERSION:
        _fail(
            "execution_plan_v2_source_version_mismatch",
            "/analysis/source_element_operator_version",
        )
    _validate_tolerance(plan.residual_tolerance)
    if plan.solver_buffer_schema_version != SOLVER_MODEL_BUFFERS_SCHEMA_VERSION:
        _fail(
            "execution_plan_v2_buffer_schema_mismatch",
            "/input_binding/solver_buffer_schema_version",
        )
    if (
        plan.node_count != len(plan.node_ids)
        or plan.element_count != len(plan.element_ids)
        or plan.dof_count != plan.node_count * _DOFS_PER_NODE
    ):
        _fail("execution_plan_v2_entity_count_mismatch", "/entity_order")
    if (
        len(set(plan.node_ids)) != plan.node_count
        or len(set(plan.element_ids)) != plan.element_count
    ):
        _fail("execution_plan_v2_entity_ids_invalid", "/entity_order")

    descriptor_names = tuple(row.name for row in plan.descriptors)
    if descriptor_names != _ARRAY_NAMES or len(set(descriptor_names)) != len(
        _ARRAY_NAMES
    ):
        _fail("execution_plan_v2_descriptor_set_invalid", "/numeric_snapshot/arrays")
    for descriptor in plan.descriptors:
        array = plan.array(descriptor.name)
        expected_dtype = "<f8" if descriptor.name in _FLOAT_ARRAY_NAMES else "<i4"
        if type(array) is not np.ndarray or array.dtype.str != expected_dtype:
            _fail(
                "execution_plan_v2_array_dtype_mismatch",
                f"/numeric_snapshot/arrays/{descriptor.name}",
            )
        if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
            _fail(
                "execution_plan_v2_array_storage_invalid",
                f"/numeric_snapshot/arrays/{descriptor.name}",
            )
        if _array_descriptor(descriptor.name, array) != descriptor:
            _fail(
                "execution_plan_v2_array_descriptor_mismatch",
                f"/numeric_snapshot/arrays/{descriptor.name}",
            )
        if descriptor.name in _FLOAT_ARRAY_NAMES:
            if not np.all(np.isfinite(array)):
                _fail(
                    "execution_plan_v2_non_finite_numeric",
                    f"/numeric_snapshot/arrays/{descriptor.name}",
                )
            if np.any(np.signbit(array[array == 0.0])):
                _fail(
                    "execution_plan_v2_signed_zero_not_normalized",
                    f"/numeric_snapshot/arrays/{descriptor.name}",
                )

    source_buffers = plan._source_buffers
    _validate_buffer_binding(plan, source_buffers)
    _validate_partition_binding(plan, source_buffers)
    if expected_buffers is not None:
        _validate_buffer_binding(plan, expected_buffers)
        _validate_partition_binding(plan, expected_buffers)
        if expected_buffers.artifact_hash != source_buffers.artifact_hash:
            _fail(
                "execution_plan_v2_buffer_binding_mismatch",
                "/input_binding/solver_artifact_hash",
            )

    _validate_layout_and_partition(plan)
    expected_symbolic = _compile_symbolic_pattern(
        dof_count=plan.dof_count,
        element_global_dofs=plan.array("element_global_dofs"),
        free_dofs=plan.array("free_dofs"),
        global_to_free=plan.array("global_to_free"),
    )
    for name, expected in expected_symbolic.items():
        if not np.array_equal(plan.array(name), expected):
            _fail(
                "execution_plan_v2_symbolic_pattern_invalid",
                f"/symbolic_plan/{name}",
            )

    source_dofs, source_transforms, source_local_stiffness = _compile_element_numeric(
        source_buffers
    )
    if not np.array_equal(plan.array("element_global_dofs"), source_dofs):
        _fail(
            "execution_plan_v2_source_numeric_mismatch",
            "/dof_layout/element_global_dofs",
        )
    if not np.array_equal(
        plan.array("recovery_transform_global_to_local"), source_transforms
    ):
        _fail(
            "execution_plan_v2_source_numeric_mismatch",
            "/numeric_snapshot/recovery_transform_global_to_local",
        )
    if not np.array_equal(
        plan.array("recovery_stiffness_local"), source_local_stiffness
    ):
        _fail(
            "execution_plan_v2_source_numeric_mismatch",
            "/numeric_snapshot/recovery_stiffness_local",
        )
    expected_load = _normalize_float_array(
        source_buffers.array("load_vector_si").reshape(-1)
    )
    if not np.array_equal(plan.array("global_load"), expected_load):
        _fail(
            "execution_plan_v2_source_numeric_mismatch", "/numeric_snapshot/global_load"
        )

    reaccumulated = _assemble_csr_values(
        plan.array("recovery_transform_global_to_local"),
        plan.array("recovery_stiffness_local"),
        plan.array("csr_element_scatter_indices"),
        plan.nnz,
    )
    if not np.array_equal(plan.array("global_stiffness_csr_values"), reaccumulated):
        _fail(
            "execution_plan_v2_reassembly_mismatch",
            "/numeric_snapshot/global_stiffness_csr_values",
        )
    reduced_expected = _normalize_float_array(
        reaccumulated[plan.array("reduced_csr_global_value_indices")]
    )
    if not np.array_equal(plan.array("reduced_stiffness_csr_values"), reduced_expected):
        _fail(
            "execution_plan_v2_reduced_values_mismatch",
            "/numeric_snapshot/reduced_stiffness_csr_values",
        )
    _validate_sparse_symmetry(plan)

    descriptor_map = {row.name: row for row in plan.descriptors}
    expected_ordering_hash = canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "element_ids": list(plan.element_ids),
            "entity_mapping_hash": plan.solver_entity_mapping_hash,
            "dof_order": list(DOF_ORDER),
            "element_end_order": ["i", "j"],
        }
    )
    if plan.ordering_hash != expected_ordering_hash:
        _fail("execution_plan_v2_ordering_hash_mismatch", "/entity_order/ordering_hash")
    if plan.partition_hash != _partition_hash(descriptor_map):
        _fail(
            "execution_plan_v2_partition_hash_mismatch",
            "/constraint_partition/partition_hash",
        )
    expected_symbolic_hash = _symbolic_reuse_hash(
        descriptor_map,
        dof_count=plan.dof_count,
        free_count=len(plan.free_dofs),
    )
    if plan.symbolic_reuse_hash != expected_symbolic_hash:
        _fail(
            "execution_plan_v2_symbolic_hash_mismatch",
            "/symbolic_plan/symbolic_reuse_hash",
        )
    expected_recovery_hash = _recovery_hash(plan.element_ids, descriptor_map)
    if plan.recovery_operator_hash != expected_recovery_hash:
        _fail(
            "execution_plan_v2_recovery_hash_mismatch",
            "/analysis/recovery_operator_hash",
        )
    expected_numeric_hash = _numeric_snapshot_hash(
        descriptor_map,
        recovery_operator_hash=expected_recovery_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
    )
    if plan.numeric_snapshot_hash != expected_numeric_hash:
        _fail(
            "execution_plan_v2_numeric_hash_mismatch",
            "/analysis/numeric_snapshot_hash",
        )
    if plan.operator_hash != _operator_hash(
        numeric_snapshot_hash=expected_numeric_hash,
        partition_hash=plan.partition_hash,
        symbolic_reuse_hash=expected_symbolic_hash,
    ):
        _fail("execution_plan_v2_operator_hash_mismatch", "/analysis/operator_hash")
    if plan.plan_hash != _plan_hash(plan):
        _fail("execution_plan_v2_plan_hash_mismatch", "/plan_hash")


def _validate_supported_buffers(buffers: SolverModelBuffers) -> None:
    if type(buffers) is not SolverModelBuffers:
        _fail("execution_plan_v2_source_buffer_invalid", "/input_binding")
    if type(buffers.descriptors) is not tuple or any(
        type(row) is not BufferDescriptor for row in buffers.descriptors
    ):
        _fail("execution_plan_v2_source_buffer_invalid", "/input_binding")
    try:
        validate_solver_model_buffers(buffers)
    except SolverModelBufferError as exc:
        raise ExecutionPlanV2Error(
            "execution_plan_v2_source_buffer_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if (
        type(buffers.descriptors) is not tuple
        or type(buffers._arrays) is not _MAPPING_PROXY_TYPE
        or type(buffers.entity_ids) is not _MAPPING_PROXY_TYPE
        or type(buffers.code_tables) is not _MAPPING_PROXY_TYPE
        or any(
            type(value) is not _MAPPING_PROXY_TYPE
            for value in buffers.code_tables.values()
        )
        or any(
            type(name) is not str
            or type(ids) is not tuple
            or any(type(value) is not str for value in ids)
            for name, ids in buffers.entity_ids.items()
        )
        or any(
            type(key) is not str
            or any(
                type(code_name) is not str
                or type(code_value) is not int
                or isinstance(code_value, bool)
                for code_name, code_value in table.items()
            )
            for key, table in buffers.code_tables.items()
        )
    ):
        _fail("execution_plan_v2_source_buffer_invalid", "/input_binding")
    if any(
        type(buffers.array(descriptor.name)) is not np.ndarray
        for descriptor in buffers.descriptors
    ):
        _fail("execution_plan_v2_source_buffer_invalid", "/input_binding")
    offsets = buffers.array("element_offsets_m")
    releases = buffers.array("element_release_mask")
    prescribed = buffers.array("prescribed_values_si")
    if np.any(offsets != 0.0):
        _raise(
            "execution_plan_v2_offsets_unsupported",
            "/input_binding/element_offsets_m",
            "ExecutionPlan v2 currently requires zero element offsets.",
        )
    if np.any(releases != 0):
        _raise(
            "execution_plan_v2_releases_unsupported",
            "/input_binding/element_release_mask",
            "ExecutionPlan v2 currently requires empty element releases.",
        )
    if np.any(prescribed != 0.0):
        _raise(
            "execution_plan_v2_nonzero_prescribed_unsupported",
            "/constraint_partition/prescribed_displacement_mode",
            "ExecutionPlan v2 supports zero prescribed displacements only.",
        )

    try:
        validate_linear_frame_truss_references_v1(
            coordinates=buffers.array("node_coordinates_m"),
            connectivity=buffers.array("element_connectivity"),
            element_types=buffers.array("element_type"),
            formulations=buffers.array("element_formulation_code"),
            material_indices=buffers.array("element_material_index"),
            section_indices=buffers.array("element_section_index"),
            material_laws=buffers.array("material_law_code"),
            materials=buffers.array("material_properties_si"),
            section_families=buffers.array("section_family_code"),
            sections=buffers.array("section_properties_si"),
        )
    except LinearFrameTrussV1Error as exc:
        _raise_element_semantics_error(exc)


def _detached_source_snapshot(buffers: SolverModelBuffers) -> SolverModelBuffers:
    """Detach all mutable mapping containers after immutable-byte preflight."""

    arrays = MappingProxyType(
        {
            descriptor.name: buffers.array(descriptor.name)
            for descriptor in buffers.descriptors
        }
    )
    entity_ids = MappingProxyType(
        {name: tuple(values) for name, values in buffers.entity_ids.items()}
    )
    code_tables = MappingProxyType(
        {
            name: MappingProxyType(dict(values))
            for name, values in buffers.code_tables.items()
        }
    )
    snapshot = replace(
        buffers,
        entity_ids=entity_ids,
        code_tables=code_tables,
        _arrays=arrays,
    )
    _validate_supported_buffers(snapshot)
    return snapshot


def _compile_partition(
    buffers: SolverModelBuffers, dof_count: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    constrained = np.asarray(
        np.flatnonzero(buffers.array("support_mask").reshape(-1)), dtype="<i4"
    )
    if constrained.size == 0:
        _raise(
            "execution_plan_v2_constraints_missing",
            "/constraint_partition/constrained_dofs",
            "At least one constrained DOF is required.",
        )
    free_mask = np.ones(dof_count, dtype=bool)
    free_mask[constrained] = False
    free = np.asarray(np.flatnonzero(free_mask), dtype="<i4")
    if free.size == 0:
        _raise(
            "execution_plan_v2_free_dofs_missing",
            "/constraint_partition/free_dofs",
            "At least one free DOF is required.",
        )
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    return constrained, free, global_to_free


def _compile_element_numeric(
    buffers: SolverModelBuffers,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    _validate_supported_buffers(buffers)
    coordinates = buffers.array("node_coordinates_m")
    connectivity = buffers.array("element_connectivity")
    element_types = buffers.array("element_type")
    formulations = buffers.array("element_formulation_code")
    material_indices = buffers.array("element_material_index")
    section_indices = buffers.array("element_section_index")
    materials = buffers.array("material_properties_si")
    sections = buffers.array("section_properties_si")
    rolls = buffers.array("element_local_axis_rotation_rad")
    element_count = connectivity.shape[0]

    element_dofs = np.empty((element_count, _ELEMENT_DOF_COUNT), dtype="<i4")
    transforms = np.empty(
        (element_count, _ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT), dtype="<f8"
    )
    local_stiffness = np.empty_like(transforms)
    for element_index in range(element_count):
        node_i = int(connectivity[element_index, 0])
        node_j = int(connectivity[element_index, 1])
        try:
            transform, length = frame_transform_v1(
                coordinates[node_i],
                coordinates[node_j],
                float(rolls[element_index]),
            )
        except LinearFrameTrussV1Error as exc:
            _raise_element_semantics_error(exc, element_index=element_index)
        material = materials[int(material_indices[element_index])]
        section = sections[int(section_indices[element_index])]
        element_type = int(element_types[element_index])
        formulation = int(formulations[element_index])
        if element_type == ELEMENT_TYPE_CODES["frame_3d"]:
            if formulation != ELEMENT_FORMULATION_CODES["euler_bernoulli_3d"]:
                _raise(
                    "execution_plan_v2_formulation_unsupported",
                    f"/elements/{element_index}/formulation",
                    "Frame element requires euler_bernoulli_3d.",
                )
            try:
                stiffness = frame_local_stiffness_v1(material, section, length)
            except LinearFrameTrussV1Error as exc:  # pragma: no cover - preflight
                _raise_element_semantics_error(exc, element_index=element_index)
        elif element_type == ELEMENT_TYPE_CODES["truss_3d"]:
            if formulation != ELEMENT_FORMULATION_CODES["linear_truss_3d"]:
                _raise(
                    "execution_plan_v2_formulation_unsupported",
                    f"/elements/{element_index}/formulation",
                    "Truss element requires linear_truss_3d.",
                )
            try:
                stiffness = truss_local_stiffness_v1(material, section, length)
            except LinearFrameTrussV1Error as exc:  # pragma: no cover - preflight
                _raise_element_semantics_error(exc, element_index=element_index)
        else:  # pragma: no cover - validated code-table invariant
            _raise(
                "execution_plan_v2_element_type_unsupported",
                f"/elements/{element_index}/type",
                f"Unsupported element type code {element_type}.",
            )
        element_dofs[element_index] = [
            node * _DOFS_PER_NODE + component
            for node in (node_i, node_j)
            for component in range(_DOFS_PER_NODE)
        ]
        transforms[element_index] = _normalize_float_array(transform)
        local_stiffness[element_index] = _normalize_float_array(stiffness)
    return (
        immutable_array(element_dofs, dtype="<i4"),
        immutable_array(_normalize_float_array(transforms), dtype="<f8"),
        immutable_array(_normalize_float_array(local_stiffness), dtype="<f8"),
    )


def _raise_element_semantics_error(
    exc: LinearFrameTrussV1Error,
    *,
    element_index: int | None = None,
) -> NoReturn:
    code = {
        "linear_frame_truss_formulation_not_supported": (
            "execution_plan_v2_formulation_unsupported"
        ),
        "linear_frame_truss_element_type_not_supported": (
            "execution_plan_v2_element_type_unsupported"
        ),
    }.get(exc.code, "execution_plan_v2_element_semantics_invalid")
    path = exc.path
    if element_index is not None and path in {
        "/geometry",
        "/start_m",
        "/end_m",
        "/roll_rad",
        "/length_m",
    }:
        path = f"/elements/{element_index}{path}"
    raise ExecutionPlanV2Error(
        code,
        path,
        f"{exc.code}: {exc.message}",
    ) from exc


def _compile_symbolic_pattern(
    *,
    dof_count: int,
    element_global_dofs: np.ndarray,
    free_dofs: np.ndarray,
    global_to_free: np.ndarray,
) -> dict[str, np.ndarray]:
    row_columns = [{row} for row in range(dof_count)]
    for element in element_global_dofs:
        dofs = [int(value) for value in element]
        for global_row in dofs:
            row_columns[global_row].update(dofs)
    nnz = sum(len(columns) for columns in row_columns)
    if nnz > _INT32_MAX:
        _raise(
            "execution_plan_v2_int32_capacity_exceeded",
            "/symbolic_plan/nnz",
            "Full CSR nonzero count exceeds the int32 sparse ABI.",
        )

    row_ptr_values = [0]
    column_values: list[int] = []
    position: dict[tuple[int, int], int] = {}
    for row, columns in enumerate(row_columns):
        for column in sorted(columns):
            position[(row, column)] = len(column_values)
            column_values.append(column)
        row_ptr_values.append(len(column_values))
    diagonal_positions = [position[(row, row)] for row in range(dof_count)]
    scatter = np.empty(
        (element_global_dofs.shape[0], _ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT),
        dtype="<i4",
    )
    for element_index, element in enumerate(element_global_dofs):
        for local_row, global_row in enumerate(element):
            for local_column, global_column in enumerate(element):
                scatter[element_index, local_row, local_column] = position[
                    (int(global_row), int(global_column))
                ]

    full_row_ptr = np.asarray(row_ptr_values, dtype="<i4")
    full_columns = np.asarray(column_values, dtype="<i4")
    reduced_row_ptr_values = [0]
    reduced_columns: list[int] = []
    reduced_global_positions: list[int] = []
    for global_row_value in free_dofs:
        global_row = int(global_row_value)
        start = int(full_row_ptr[global_row])
        stop = int(full_row_ptr[global_row + 1])
        for full_position in range(start, stop):
            reduced_column = int(global_to_free[int(full_columns[full_position])])
            if reduced_column >= 0:
                reduced_columns.append(reduced_column)
                reduced_global_positions.append(full_position)
        reduced_row_ptr_values.append(len(reduced_columns))
    if len(reduced_columns) > _INT32_MAX:
        _raise(
            "execution_plan_v2_int32_capacity_exceeded",
            "/symbolic_plan/reduced_nnz",
            "Reduced CSR nonzero count exceeds the int32 sparse ABI.",
        )
    return {
        "csr_row_ptr": immutable_array(full_row_ptr, dtype="<i4"),
        "csr_column_indices": immutable_array(full_columns, dtype="<i4"),
        "csr_diagonal_positions": immutable_array(diagonal_positions, dtype="<i4"),
        "csr_element_scatter_indices": immutable_array(scatter, dtype="<i4"),
        "reduced_csr_row_ptr": immutable_array(reduced_row_ptr_values, dtype="<i4"),
        "reduced_csr_column_indices": immutable_array(reduced_columns, dtype="<i4"),
        "reduced_csr_global_value_indices": immutable_array(
            reduced_global_positions, dtype="<i4"
        ),
    }


def _assemble_csr_values(
    transforms: np.ndarray,
    local_stiffness: np.ndarray,
    scatter: np.ndarray,
    nnz: int,
) -> np.ndarray:
    """Reaccumulate in the declared deterministic order using O(nnz) output."""

    values = np.zeros(nnz, dtype="<f8")
    for element_index in range(transforms.shape[0]):
        element_stiffness = (
            transforms[element_index].T
            @ local_stiffness[element_index]
            @ transforms[element_index]
        )
        for local_row in range(_ELEMENT_DOF_COUNT):
            for local_column in range(_ELEMENT_DOF_COUNT):
                position = int(scatter[element_index, local_row, local_column])
                values[position] += element_stiffness[local_row, local_column]
    return _normalize_float_array(values)


def _csr_matvec(
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    row_count = row_ptr.size - 1
    result = np.zeros(row_count, dtype="<f8")
    for row in range(row_count):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        accumulator = 0.0
        for position in range(start, stop):
            accumulator += float(values[position]) * float(
                vector[int(columns[position])]
            )
        result[row] = accumulator
    return result


def _validate_layout_and_partition(plan: ExecutionPlanV2) -> None:
    expected_node_dofs = np.arange(plan.dof_count, dtype="<i4").reshape(
        plan.node_count, _DOFS_PER_NODE
    )
    if not np.array_equal(plan.array("node_dof_indices"), expected_node_dofs):
        _fail("execution_plan_v2_node_dof_map_invalid", "/dof_layout/node_dof_indices")
    element_dofs = plan.array("element_global_dofs")
    if element_dofs.shape != (plan.element_count, _ELEMENT_DOF_COUNT):
        _fail(
            "execution_plan_v2_element_dof_shape_invalid",
            "/dof_layout/element_global_dofs",
        )
    if np.any(element_dofs < 0) or np.any(element_dofs >= plan.dof_count):
        _fail(
            "execution_plan_v2_element_dof_range_invalid",
            "/dof_layout/element_global_dofs",
        )

    constrained = plan.array("constrained_dofs")
    free = plan.array("free_dofs")
    if constrained.ndim != 1 or free.ndim != 1 or not constrained.size or not free.size:
        _fail("execution_plan_v2_partition_empty", "/constraint_partition")
    if np.any(np.diff(constrained) <= 0) or np.any(np.diff(free) <= 0):
        _fail("execution_plan_v2_partition_not_sorted", "/constraint_partition")
    if not np.array_equal(
        np.sort(np.concatenate((constrained, free))),
        np.arange(plan.dof_count, dtype="<i4"),
    ):
        _fail("execution_plan_v2_partition_not_complete", "/constraint_partition")
    expected_mapping = np.full(plan.dof_count, -1, dtype="<i4")
    expected_mapping[free] = np.arange(free.size, dtype="<i4")
    if not np.array_equal(plan.array("global_to_free"), expected_mapping):
        _fail("execution_plan_v2_global_to_free_invalid", "/dof_layout/global_to_free")


def _validate_sparse_symmetry(plan: ExecutionPlanV2) -> None:
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    values = plan.array("global_stiffness_csr_values")
    positions: dict[tuple[int, int], int] = {}
    for row in range(plan.dof_count):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        row_columns = columns[start:stop]
        if row_columns.size == 0 or np.any(np.diff(row_columns) <= 0):
            _fail(
                "execution_plan_v2_csr_columns_not_sorted",
                "/symbolic_plan/column_indices",
            )
        for position in range(start, stop):
            positions[(row, int(columns[position]))] = position
    scale = max(1.0, float(np.max(np.abs(values))))
    tolerance = scale * 1.0e-12
    for (row, column), position in positions.items():
        reverse = positions.get((column, row))
        if reverse is None:
            _fail("execution_plan_v2_csr_pattern_not_symmetric", "/symbolic_plan")
        if abs(float(values[position]) - float(values[reverse])) > tolerance:
            _fail("execution_plan_v2_csr_values_not_symmetric", "/numeric_snapshot")


def _validate_buffer_binding(
    plan: ExecutionPlanV2, buffers: SolverModelBuffers
) -> None:
    _validate_supported_buffers(buffers)
    bindings = (
        (
            plan.model_ir_content_hash,
            buffers.model_ir_content_hash,
            "model_ir_content_hash",
        ),
        (
            plan.solver_buffer_schema_version,
            buffers.schema_version,
            "solver_buffer_schema_version",
        ),
        (
            plan.solver_numeric_buffer_hash,
            buffers.numeric_buffer_hash,
            "solver_numeric_buffer_hash",
        ),
        (
            plan.solver_entity_mapping_hash,
            buffers.entity_mapping_hash,
            "solver_entity_mapping_hash",
        ),
        (plan.solver_artifact_hash, buffers.artifact_hash, "solver_artifact_hash"),
        (plan.load_pattern_id, buffers.load_pattern_id, "load_pattern_id"),
        (plan.node_ids, tuple(buffers.entity_ids["nodes"]), "node_ids"),
        (plan.element_ids, tuple(buffers.entity_ids["elements"]), "element_ids"),
    )
    for actual, expected, field in bindings:
        if actual != expected:
            _fail(
                "execution_plan_v2_buffer_binding_mismatch",
                f"/input_binding/{field}",
            )


def _validate_partition_binding(
    plan: ExecutionPlanV2, buffers: SolverModelBuffers
) -> None:
    expected_constrained, expected_free, expected_global_to_free = _compile_partition(
        buffers, plan.dof_count
    )
    for name, expected in (
        ("constrained_dofs", expected_constrained),
        ("free_dofs", expected_free),
        ("global_to_free", expected_global_to_free),
    ):
        if not np.array_equal(plan.array(name), expected):
            _fail(
                "execution_plan_v2_source_partition_mismatch",
                f"/constraint_partition/{name}",
            )


def _array_descriptor(name: str, array: np.ndarray) -> PlanArrayDescriptorV2:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return PlanArrayDescriptorV2(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _partition_hash(descriptors: Mapping[str, PlanArrayDescriptorV2]) -> str:
    return canonical_hash(
        {
            "index_dtype": "<i4",
            "prescribed_displacement_mode": "zero_only",
            "arrays": [
                descriptors[name].to_dict()
                for name in ("constrained_dofs", "free_dofs", "global_to_free")
            ],
        }
    )


def _symbolic_reuse_hash(
    descriptors: Mapping[str, PlanArrayDescriptorV2],
    *,
    dof_count: int,
    free_count: int,
) -> str:
    return canonical_hash(
        {
            "format": "csr",
            "full_shape": [dof_count, dof_count],
            "reduced_shape": [free_count, free_count],
            "column_order": "ascending",
            "structural_zero_slots_retained": True,
            "assembly_order": _ASSEMBLY_ORDER,
            "arrays": [
                descriptors[name].to_dict() for name in _SYMBOLIC_HASH_ARRAY_NAMES
            ],
        }
    )


def _recovery_hash(
    element_ids: tuple[str, ...],
    descriptors: Mapping[str, PlanArrayDescriptorV2],
) -> str:
    return canonical_hash(
        {
            "source_element_operator_version": SOURCE_ELEMENT_OPERATOR_VERSION,
            "local_frame_convention": (
                "engine_v2_frame_local_x_i_to_j_right_handed_v1"
            ),
            "element_ids": list(element_ids),
            "arrays": [
                descriptors[name].to_dict()
                for name in (
                    "element_global_dofs",
                    "recovery_transform_global_to_local",
                    "recovery_stiffness_local",
                )
            ],
        }
    )


def _numeric_snapshot_hash(
    descriptors: Mapping[str, PlanArrayDescriptorV2],
    *,
    recovery_operator_hash: str,
    solver_numeric_buffer_hash: str,
) -> str:
    return canonical_hash(
        {
            "operator_version": SPARSE_CPU_OPERATOR_VERSION,
            "source_element_operator_version": SOURCE_ELEMENT_OPERATOR_VERSION,
            "solver_numeric_buffer_hash": solver_numeric_buffer_hash,
            "recovery_operator_hash": recovery_operator_hash,
            "assembly_order": _ASSEMBLY_ORDER,
            "signed_zero_normalized": True,
            "arrays": [
                descriptors[name].to_dict() for name in _NUMERIC_HASH_ARRAY_NAMES
            ],
        }
    )


def _operator_hash(
    *,
    numeric_snapshot_hash: str,
    partition_hash: str,
    symbolic_reuse_hash: str,
) -> str:
    return canonical_hash(
        {
            "operator_version": SPARSE_CPU_OPERATOR_VERSION,
            "numeric_snapshot_hash": numeric_snapshot_hash,
            "partition_hash": partition_hash,
            "symbolic_reuse_hash": symbolic_reuse_hash,
            "residual_sign": "internal_minus_external",
        }
    )


def _plan_hash(plan: ExecutionPlanV2) -> str:
    payload = plan.to_dict()
    payload.pop("plan_hash")
    return canonical_hash(payload)


def _normalize_float_array(value: Any) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype="<f8").copy()
    if not np.all(np.isfinite(array)):
        _raise(
            "execution_plan_v2_non_finite_numeric",
            "/numeric_snapshot",
            "Compiled numerical payload contains NaN or Infinity.",
        )
    array[array == 0.0] = 0.0
    return array


def _finite_vector(value: np.ndarray, size: int, label: str) -> np.ndarray:
    vector = np.asarray(value, dtype="<f8").reshape(-1)
    if vector.size != size:
        raise ValueError(f"{label} must contain {size} values, got {vector.size}.")
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{label} contains NaN or Infinity.")
    return vector


def _validate_tolerance(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
        _raise(
            "execution_plan_v2_tolerance_invalid",
            "/solver_policy/residual_tolerance",
            "Residual tolerance must be a finite positive number.",
        )
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        _raise(
            "execution_plan_v2_tolerance_invalid",
            "/solver_policy/residual_tolerance",
            "Residual tolerance must be a finite positive number.",
        )


@lru_cache(maxsize=1)
def _plan_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "execution_plan_v2.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str) -> None:
    messages = {
        "execution_plan_v2_schema_mismatch": "ExecutionPlan v2 schema version is invalid.",
        "execution_plan_v2_profile_mismatch": "ExecutionPlan v2 capability profile is invalid.",
        "execution_plan_v2_operator_version_mismatch": "Sparse operator version is invalid.",
        "execution_plan_v2_source_version_mismatch": "Element formula source version is invalid.",
        "execution_plan_v2_tolerance_invalid": "Residual tolerance is invalid.",
        "execution_plan_v2_buffer_schema_mismatch": "Solver buffer schema binding is invalid.",
        "execution_plan_v2_entity_count_mismatch": "Entity counts or DOF count are inconsistent.",
        "execution_plan_v2_entity_ids_invalid": "Entity IDs must be unique.",
        "execution_plan_v2_descriptor_set_invalid": "Array descriptor set or order is invalid.",
        "execution_plan_v2_container_invalid": "Plan containers must use exact immutable contract types.",
        "execution_plan_v2_array_set_invalid": "Backing array set is invalid.",
        "execution_plan_v2_array_dtype_mismatch": "Backing array dtype is invalid.",
        "execution_plan_v2_array_storage_invalid": "Backing array is not immutable C-order bytes.",
        "execution_plan_v2_array_descriptor_mismatch": "Array descriptor/hash is stale.",
        "execution_plan_v2_non_finite_numeric": "Numerical payload contains NaN or Infinity.",
        "execution_plan_v2_signed_zero_not_normalized": "Numerical payload contains negative zero.",
        "execution_plan_v2_node_dof_map_invalid": "Node-major DOF map is invalid.",
        "execution_plan_v2_element_dof_shape_invalid": "Element DOF map shape is invalid.",
        "execution_plan_v2_element_dof_range_invalid": "Element DOF map is out of range.",
        "execution_plan_v2_partition_empty": "DOF partition must contain constrained and free entries.",
        "execution_plan_v2_partition_not_sorted": "DOF partition is not strictly sorted.",
        "execution_plan_v2_partition_not_complete": "DOF partition is not a complete disjoint cover.",
        "execution_plan_v2_global_to_free_invalid": "Global-to-free map is invalid.",
        "execution_plan_v2_symbolic_pattern_invalid": "CSR symbolic pattern is inconsistent.",
        "execution_plan_v2_source_numeric_mismatch": "Compiled numeric source differs from bound buffers.",
        "execution_plan_v2_reassembly_mismatch": "CSR values differ from independent element reaccumulation.",
        "execution_plan_v2_reduced_values_mismatch": "Reduced CSR values do not map exactly to full CSR.",
        "execution_plan_v2_csr_columns_not_sorted": "CSR columns are not strictly ascending per row.",
        "execution_plan_v2_csr_pattern_not_symmetric": "CSR symbolic pattern is not symmetric.",
        "execution_plan_v2_csr_values_not_symmetric": "CSR stiffness values are not symmetric within tolerance.",
        "execution_plan_v2_buffer_binding_mismatch": "Plan is bound to different SolverModelBuffers.",
        "execution_plan_v2_source_buffer_invalid": "Source SolverModelBuffers storage is not immutable and contract-valid.",
        "execution_plan_v2_source_partition_mismatch": "Plan DOF partition differs from bound support_mask bytes.",
        "execution_plan_v2_ordering_hash_mismatch": "Entity ordering hash is stale.",
        "execution_plan_v2_partition_hash_mismatch": "Constraint partition hash is stale.",
        "execution_plan_v2_symbolic_hash_mismatch": "Symbolic reuse hash is stale.",
        "execution_plan_v2_recovery_hash_mismatch": "Recovery operator hash is stale.",
        "execution_plan_v2_numeric_hash_mismatch": "Numeric snapshot hash is stale.",
        "execution_plan_v2_operator_hash_mismatch": "Sparse operator hash is stale.",
        "execution_plan_v2_plan_hash_mismatch": "ExecutionPlan v2 aggregate hash is stale.",
    }
    _raise(code, path, messages.get(code, code))


def _raise(code: str, path: str, message: str) -> None:
    raise ExecutionPlanV2Error(code, path, message)


__all__ = [
    "EXECUTION_PLAN_V2_CAPABILITY_PROFILE",
    "EXECUTION_PLAN_V2_SCHEMA_VERSION",
    "SOURCE_ELEMENT_OPERATOR_VERSION",
    "SPARSE_CPU_OPERATOR_VERSION",
    "ExecutionPlanV2",
    "ExecutionPlanV2Error",
    "PlanArrayDescriptorV2",
    "compile_execution_plan_v2",
    "validate_execution_plan_v2",
]
