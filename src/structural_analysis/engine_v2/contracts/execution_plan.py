"""Immutable Phase 0 ExecutionPlan v1 compiler and semantic validator.

The execution plan is the compiled boundary between semantic ``ModelIR`` data
and a concrete backend execution.  It binds entity ordering, the node-major
six-DOF map, a canonical CSR symbolic pattern, compiled K/F bytes, the result
recovery operator, solver policy, and the exact seven-stage operator graph.

Runtime arrays remain bytes-backed NumPy views.  ``to_dict()`` is the strict
JSON manifest; large numerical payloads are represented by descriptors and
content hashes in that manifest and are retained by the in-memory artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (
    CPU_REFERENCE_OPERATOR_VERSION,
    LinearStaticOperator,
    _operator_hash,
    _validate_buffer_contract,
    assemble_linear_static_operator,
)
from structural_analysis.engine_v2.buffers import (
    DOF_ORDER,
    SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
    SolverModelBuffers,
)

from ._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)

EXECUTION_PLAN_SCHEMA_VERSION = "structural-analysis-execution-plan.v1"
EXECUTION_PLAN_CAPABILITY_PROFILE = "phase0_cpu_reference_linear_static"
_INT32_MAX = int(np.iinfo(np.int32).max)
_DOF_COUNT_PER_NODE = len(DOF_ORDER)
_ELEMENT_DOF_COUNT = 2 * _DOF_COUNT_PER_NODE

_ARRAY_NAMES = (
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
    "global_stiffness_csr_values",
    "global_stiffness_dense",
    "global_load",
    "recovery_transform_global_to_local",
    "recovery_stiffness_local",
)

_OPERATOR_GRAPH: tuple[dict[str, Any], ...] = (
    {
        "id": "assembly",
        "kind": "assembly",
        "depends_on": [],
        "input_space": "solver_model_buffers",
        "output_space": "global_dof",
        "state_epoch_source": "state_ir",
        "representation": "assembled_csr",
    },
    {
        "id": "partition",
        "kind": "constraint_partition",
        "depends_on": ["assembly"],
        "input_space": "global_dof",
        "output_space": "reduced_dof",
        "state_epoch_source": "state_ir",
        "representation": "index_partition",
    },
    {
        "id": "solve",
        "kind": "linear_solve",
        "depends_on": ["partition"],
        "input_space": "reduced_dof",
        "output_space": "global_dof",
        "state_epoch_source": "state_ir",
        "representation": "direct_solve",
    },
    {
        "id": "residual",
        "kind": "residual",
        "depends_on": ["assembly", "solve"],
        "input_space": "global_dof",
        "output_space": "global_dof",
        "state_epoch_source": "state_ir",
        "representation": "matrix_vector",
    },
    {
        "id": "reaction",
        "kind": "reaction",
        "depends_on": ["residual"],
        "input_space": "global_dof",
        "output_space": "global_dof",
        "state_epoch_source": "state_ir",
        "representation": "index_partition",
    },
    {
        "id": "recovery",
        "kind": "result_recovery",
        "depends_on": ["solve"],
        "input_space": "global_dof",
        "output_space": "element_result",
        "state_epoch_source": "state_ir",
        "representation": "element_local",
    },
    {
        "id": "energy",
        "kind": "energy",
        "depends_on": ["solve", "recovery"],
        "input_space": "element_result",
        "output_space": "scalar_result",
        "state_epoch_source": "state_ir",
        "representation": "scalar_reduction",
    },
)


class ExecutionPlanError(ValueError):
    """Fail-closed ExecutionPlan contract error with a stable code."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class PlanArrayDescriptor:
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
class ExecutionPlan:
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
    operator_hash: str
    recovery_operator_hash: str
    node_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    ordering_hash: str
    node_count: int
    element_count: int
    dof_count: int
    matrix_backend: Literal["dense", "scipy_sparse"]
    residual_tolerance: float
    pattern_hash: str
    partition_hash: str
    descriptors: tuple[PlanArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray]
    _operator: LinearStaticOperator

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown ExecutionPlan array: {name}") from exc

    @property
    def operator(self) -> LinearStaticOperator:
        return self._operator

    @property
    def constrained_dofs(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.array("constrained_dofs"))

    @property
    def free_dofs(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.array("free_dofs"))

    def to_dict(self) -> dict[str, Any]:
        descriptors = {descriptor.name: descriptor for descriptor in self.descriptors}
        stiffness_descriptor = descriptors["global_stiffness_csr_values"].to_dict()
        stiffness_descriptor["name"] = "global_stiffness"
        load_descriptor = descriptors["global_load"].to_dict()
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "capability_profile": self.capability_profile,
            "model_ir_content_hash": self.model_ir_content_hash,
            "solver_model_buffers": {
                "schema_version": self.solver_buffer_schema_version,
                "load_pattern_id": self.load_pattern_id,
                "numeric_buffer_hash": self.solver_numeric_buffer_hash,
                "entity_mapping_hash": self.solver_entity_mapping_hash,
                "artifact_hash": self.solver_artifact_hash,
            },
            "analysis": {
                "type": "linear_static",
                "residual_sign": "internal_minus_external",
                "operator_version": self.operator_version,
                "operator_hash": self.operator_hash,
                "recovery_operator_hash": self.recovery_operator_hash,
            },
            "entity_order": {
                "node_ids": list(self.node_ids),
                "element_ids": list(self.element_ids),
                "ordering_hash": self.ordering_hash,
            },
            "vector_spaces": _vector_spaces(self.node_count, self.element_count),
            "dof_layout": {
                "components": list(DOF_ORDER),
                "node_count": self.node_count,
                "dofs_per_node": _DOF_COUNT_PER_NODE,
                "dof_count": self.dof_count,
                "index_base": 0,
                "index_dtype": "<i4",
                "global_index_formula": "node_index*6+component_index",
                "node_dof_indices": self.array("node_dof_indices").tolist(),
                "global_to_free": self.array("global_to_free").tolist(),
                "element_global_dofs": self.array("element_global_dofs").tolist(),
            },
            "constraint_partition": {
                "constrained_dofs": self.array("constrained_dofs").tolist(),
                "free_dofs": self.array("free_dofs").tolist(),
                "partition_hash": self.partition_hash,
            },
            "sparse_pattern": {
                "format": "csr",
                "shape": [self.dof_count, self.dof_count],
                "index_dtype": "<i4",
                "row_ptr": self.array("csr_row_ptr").tolist(),
                "column_indices": self.array("csr_column_indices").tolist(),
                "diagonal_positions": self.array("csr_diagonal_positions").tolist(),
                "element_scatter_indices": self.array(
                    "csr_element_scatter_indices"
                ).tolist(),
                "reduced_row_ptr": self.array("reduced_csr_row_ptr").tolist(),
                "reduced_column_indices": self.array(
                    "reduced_csr_column_indices"
                ).tolist(),
                "reduced_global_value_indices": self.array(
                    "reduced_csr_global_value_indices"
                ).tolist(),
                "nnz": int(self.array("csr_column_indices").size),
                "reduced_nnz": int(
                    self.array("reduced_csr_column_indices").size
                ),
                "sorted_columns": True,
                "symmetric_pattern": True,
                "pattern_hash": self.pattern_hash,
            },
            "operator_graph": [dict(row) for row in _OPERATOR_GRAPH],
            "compiled_operator": {
                "stiffness": stiffness_descriptor,
                "load": load_descriptor,
                "recovery_operator_hash": self.recovery_operator_hash,
            },
            "backend_policy": {
                "backend": "cpu_reference",
                "execution_mode": "verification",
                "scalar_type": "<f8",
                "fallback_policy": "forbidden",
                "deterministic": True,
                "device_residency_required": False,
                "required_capabilities": [
                    "fp64",
                    "assembled_operator",
                    "result_recovery",
                    "immutable_state",
                ],
            },
            "solver_policy": {
                "linear_solver": (
                    "dense_direct"
                    if self.matrix_backend == "dense"
                    else "scipy_sparse_direct"
                ),
                "residual_tolerance": self.residual_tolerance,
                "max_iterations": 1,
            },
            "state_contract": {
                "schema_version": "structural-analysis-state-ir.v1",
                "initial_epoch": 0,
                "material_state_mode": "stateless_linear_elastic",
                "trial_commit_rollback_required": True,
            },
            "plan_hash": self.plan_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def compile_execution_plan(
    buffers: SolverModelBuffers,
    *,
    matrix_backend: Literal["dense", "scipy_sparse"] = "dense",
    residual_tolerance: float = 1.0e-10,
) -> ExecutionPlan:
    """Compile and immediately validate a deterministic Phase 0 plan."""

    if matrix_backend not in ("dense", "scipy_sparse"):
        raise ExecutionPlanError(
            "execution_plan_backend_unsupported",
            "/solver_policy/linear_solver",
            f"Unsupported matrix backend: {matrix_backend}",
        )
    if (
        isinstance(residual_tolerance, bool)
        or not np.isfinite(residual_tolerance)
        or residual_tolerance <= 0.0
    ):
        raise ExecutionPlanError(
            "execution_plan_tolerance_invalid",
            "/solver_policy/residual_tolerance",
            "Residual tolerance must be finite and positive.",
        )

    # The CPU assembler performs the authoritative buffer integrity preflight.
    operator = assemble_linear_static_operator(buffers)
    node_ids = tuple(buffers.entity_ids["nodes"])
    element_ids = tuple(buffers.entity_ids["elements"])
    node_count = len(node_ids)
    element_count = len(element_ids)
    dof_count = node_count * _DOF_COUNT_PER_NODE
    if dof_count > _INT32_MAX:
        raise ExecutionPlanError(
            "execution_plan_int32_capacity_exceeded",
            "/dof_layout/dof_count",
            "Global DOF count exceeds the Phase 0 int32 ABI.",
        )

    node_dofs = np.arange(dof_count, dtype="<i4").reshape(
        node_count, _DOF_COUNT_PER_NODE
    )
    constrained = np.asarray(operator.constrained_dofs, dtype="<i4")
    free = np.asarray(operator.free_dofs, dtype="<i4")
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    element_global_dofs = np.asarray(
        [row.global_dofs for row in operator.element_operators], dtype="<i4"
    ).reshape(element_count, _ELEMENT_DOF_COUNT)

    symbolic = _compile_symbolic_pattern(
        dof_count=dof_count,
        element_global_dofs=element_global_dofs,
        free_dofs=free,
        global_to_free=global_to_free,
    )
    row_ptr = symbolic["csr_row_ptr"]
    columns = symbolic["csr_column_indices"]
    stiffness_values = _gather_csr_values(
        operator.stiffness_matrix, row_ptr, columns
    )
    recovery_transforms = np.stack(
        [row.transform_global_to_local for row in operator.element_operators], axis=0
    )
    recovery_stiffness = np.stack(
        [row.stiffness_local for row in operator.element_operators], axis=0
    )

    raw_arrays: dict[str, np.ndarray] = {
        "node_dof_indices": node_dofs,
        "global_to_free": global_to_free,
        "element_global_dofs": element_global_dofs,
        "constrained_dofs": constrained,
        "free_dofs": free,
        **symbolic,
        "global_stiffness_csr_values": stiffness_values,
        "global_stiffness_dense": operator.stiffness_matrix,
        "global_load": operator.load_vector,
        "recovery_transform_global_to_local": recovery_transforms,
        "recovery_stiffness_local": recovery_stiffness,
    }
    arrays = {
        name: immutable_array(
            raw_arrays[name], dtype="<f8" if name in _float_array_names() else "<i4"
        )
        for name in _ARRAY_NAMES
    }
    descriptors = tuple(
        _array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES
    )
    ordering_hash = canonical_hash(
        {
            "node_ids": list(node_ids),
            "element_ids": list(element_ids),
            "entity_mapping_hash": buffers.entity_mapping_hash,
            "dof_order": list(DOF_ORDER),
            "element_end_order": ["i", "j"],
        }
    )
    partition_hash = _partition_hash(arrays)
    pattern_hash = _pattern_hash(arrays, dof_count)
    recovery_hash = _recovery_hash_from_arrays(
        element_ids,
        arrays["element_global_dofs"],
        arrays["recovery_transform_global_to_local"],
        arrays["recovery_stiffness_local"],
    )
    seed_hash = canonical_hash(
        {
            "model_ir_content_hash": buffers.model_ir_content_hash,
            "solver_artifact_hash": buffers.artifact_hash,
            "matrix_backend": matrix_backend,
            "residual_tolerance": float(residual_tolerance),
        }
    )
    plan_id = f"Plan:{seed_hash.removeprefix('sha256:')[:24]}"
    zero_hash = "sha256:" + ("0" * 64)
    plan = ExecutionPlan(
        schema_version=EXECUTION_PLAN_SCHEMA_VERSION,
        capability_profile=EXECUTION_PLAN_CAPABILITY_PROFILE,
        plan_id=plan_id,
        plan_hash=zero_hash,
        model_ir_content_hash=buffers.model_ir_content_hash,
        solver_buffer_schema_version=buffers.schema_version,
        solver_numeric_buffer_hash=buffers.numeric_buffer_hash,
        solver_entity_mapping_hash=buffers.entity_mapping_hash,
        solver_artifact_hash=buffers.artifact_hash,
        load_pattern_id=buffers.load_pattern_id,
        operator_version=operator.version,
        operator_hash=operator.operator_hash,
        recovery_operator_hash=recovery_hash,
        node_ids=node_ids,
        element_ids=element_ids,
        ordering_hash=ordering_hash,
        node_count=node_count,
        element_count=element_count,
        dof_count=dof_count,
        matrix_backend=matrix_backend,
        residual_tolerance=float(residual_tolerance),
        pattern_hash=pattern_hash,
        partition_hash=partition_hash,
        descriptors=descriptors,
        _arrays=MappingProxyType(arrays),
        _operator=operator,
    )
    plan = replace(plan, plan_hash=_plan_hash(plan))
    # Assembly above already performed the authoritative semantic preflight.
    # Internal validation must not assemble a second, hidden operator.
    validate_execution_plan(plan)
    return plan


def validate_execution_plan(
    plan: ExecutionPlan,
    *,
    expected_buffers: SolverModelBuffers | None = None,
) -> None:
    """Validate schema, typed payloads, numerical bindings, and all hashes."""

    if not isinstance(plan, ExecutionPlan):
        raise ExecutionPlanError(
            "execution_plan_type_invalid", "/", "Expected an ExecutionPlan instance."
        )
    try:
        manifest = plan.to_dict()
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionPlanError(
            "execution_plan_manifest_invalid", "/", f"Cannot build manifest: {exc}"
        ) from exc
    errors = sorted(
        _execution_plan_validator().iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ExecutionPlanError(
            "execution_plan_schema_invalid", path, error.message
        )

    if plan.schema_version != EXECUTION_PLAN_SCHEMA_VERSION:
        _fail("execution_plan_schema_mismatch", "/schema_version")
    if plan.capability_profile != EXECUTION_PLAN_CAPABILITY_PROFILE:
        _fail("execution_plan_profile_mismatch", "/capability_profile")
    if plan.operator_version != CPU_REFERENCE_OPERATOR_VERSION:
        _fail("execution_plan_operator_version_mismatch", "/analysis/operator_version")
    if plan.solver_buffer_schema_version != SOLVER_MODEL_BUFFERS_SCHEMA_VERSION:
        _fail(
            "execution_plan_buffer_schema_mismatch",
            "/solver_model_buffers/schema_version",
        )
    if plan.matrix_backend not in ("dense", "scipy_sparse"):
        _fail("execution_plan_backend_unsupported", "/solver_policy/linear_solver")
    if not np.isfinite(plan.residual_tolerance) or plan.residual_tolerance <= 0.0:
        _fail("execution_plan_tolerance_invalid", "/solver_policy/residual_tolerance")
    if plan.node_count != len(plan.node_ids) or plan.element_count != len(plan.element_ids):
        _fail("execution_plan_entity_count_mismatch", "/entity_order")
    if len(set(plan.node_ids)) != plan.node_count or len(set(plan.element_ids)) != plan.element_count:
        _fail("execution_plan_entity_ids_invalid", "/entity_order")
    if plan.dof_count != plan.node_count * _DOF_COUNT_PER_NODE:
        _fail("execution_plan_dof_count_mismatch", "/dof_layout/dof_count")

    descriptor_names = tuple(row.name for row in plan.descriptors)
    if descriptor_names != _ARRAY_NAMES or len(set(descriptor_names)) != len(_ARRAY_NAMES):
        _fail("execution_plan_descriptor_set_invalid", "/compiled_operator")
    if set(plan._arrays) != set(_ARRAY_NAMES):
        _fail("execution_plan_array_set_invalid", "/compiled_operator")
    for descriptor in plan.descriptors:
        array = plan.array(descriptor.name)
        expected_dtype = "<f8" if descriptor.name in _float_array_names() else "<i4"
        if array.dtype.str != expected_dtype:
            _fail(
                "execution_plan_array_dtype_mismatch",
                f"/payloads/{descriptor.name}/dtype",
            )
        if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
            _fail(
                "execution_plan_array_storage_invalid",
                f"/payloads/{descriptor.name}",
            )
        if _array_descriptor(descriptor.name, array) != descriptor:
            _fail(
                "execution_plan_array_descriptor_mismatch",
                f"/payloads/{descriptor.name}",
            )

    _validate_dof_partition(plan)
    _validate_symbolic_pattern(plan)
    _validate_compiled_operator(plan)
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
        _fail("execution_plan_ordering_hash_mismatch", "/entity_order/ordering_hash")
    if plan.partition_hash != _partition_hash(plan._arrays):
        _fail(
            "execution_plan_partition_hash_mismatch",
            "/constraint_partition/partition_hash",
        )
    if plan.pattern_hash != _pattern_hash(plan._arrays, plan.dof_count):
        _fail("execution_plan_pattern_hash_mismatch", "/sparse_pattern/pattern_hash")
    expected_recovery_hash = _recovery_hash_from_arrays(
        plan.element_ids,
        plan.array("element_global_dofs"),
        plan.array("recovery_transform_global_to_local"),
        plan.array("recovery_stiffness_local"),
    )
    if plan.recovery_operator_hash != expected_recovery_hash:
        _fail(
            "execution_plan_recovery_hash_mismatch",
            "/analysis/recovery_operator_hash",
        )
    if plan.plan_hash != _plan_hash(plan):
        _fail("execution_plan_hash_mismatch", "/plan_hash")

    if expected_buffers is not None:
        _validate_buffer_bindings(plan, expected_buffers)


def compute_recovery_operator_hash(
    operator: LinearStaticOperator, element_ids: tuple[str, ...] | list[str]
) -> str:
    """Hash the complete local result-recovery operator for public receipts."""

    ids = tuple(element_ids)
    if len(ids) != len(operator.element_operators) or not ids:
        raise ExecutionPlanError(
            "execution_plan_recovery_entity_mismatch",
            "/entity_order/element_ids",
            "Element IDs do not match the recovery operator count.",
        )
    global_dofs = immutable_array(
        [row.global_dofs for row in operator.element_operators], dtype="<i4"
    )
    transforms = immutable_array(
        np.stack(
            [row.transform_global_to_local for row in operator.element_operators]
        ),
        dtype="<f8",
    )
    stiffness = immutable_array(
        np.stack([row.stiffness_local for row in operator.element_operators]),
        dtype="<f8",
    )
    return _recovery_hash_from_arrays(ids, global_dofs, transforms, stiffness)


def _validate_buffer_bindings(
    plan: ExecutionPlan, buffers: SolverModelBuffers
) -> None:
    # Revalidate descriptors and all three buffer hashes without rebuilding K.
    # The immutable artifact hash binds the exact bytes used at compilation.
    _validate_buffer_contract(buffers)
    bindings = (
        (plan.model_ir_content_hash, buffers.model_ir_content_hash, "model_ir_content_hash"),
        (
            plan.solver_buffer_schema_version,
            buffers.schema_version,
            "schema_version",
        ),
        (plan.load_pattern_id, buffers.load_pattern_id, "load_pattern_id"),
        (
            plan.solver_numeric_buffer_hash,
            buffers.numeric_buffer_hash,
            "numeric_buffer_hash",
        ),
        (
            plan.solver_entity_mapping_hash,
            buffers.entity_mapping_hash,
            "entity_mapping_hash",
        ),
        (plan.solver_artifact_hash, buffers.artifact_hash, "artifact_hash"),
        (plan.node_ids, tuple(buffers.entity_ids["nodes"]), "node_ids"),
        (plan.element_ids, tuple(buffers.entity_ids["elements"]), "element_ids"),
    )
    for actual, expected, field in bindings:
        if actual != expected:
            _fail(
                "execution_plan_buffer_binding_mismatch",
                f"/solver_model_buffers/{field}",
            )
    if plan.operator.solver_buffer_hash != buffers.numeric_buffer_hash:
        _fail("execution_plan_operator_hash_mismatch", "/analysis/operator_hash")
    expected_load = buffers.array("load_vector_si").reshape(-1)
    if not np.array_equal(plan.array("global_load"), expected_load):
        _fail("execution_plan_compiled_load_mismatch", "/compiled_operator/load")


def _validate_dof_partition(plan: ExecutionPlan) -> None:
    expected_node_dofs = np.arange(plan.dof_count, dtype="<i4").reshape(
        plan.node_count, _DOF_COUNT_PER_NODE
    )
    if not np.array_equal(plan.array("node_dof_indices"), expected_node_dofs):
        _fail("execution_plan_node_dof_map_invalid", "/dof_layout/node_dof_indices")
    element_dofs = plan.array("element_global_dofs")
    if element_dofs.shape != (plan.element_count, _ELEMENT_DOF_COUNT):
        _fail("execution_plan_element_dof_shape_invalid", "/dof_layout/element_global_dofs")
    if np.any(element_dofs < 0) or np.any(element_dofs >= plan.dof_count):
        _fail("execution_plan_element_dof_out_of_range", "/dof_layout/element_global_dofs")

    constrained = plan.array("constrained_dofs")
    free = plan.array("free_dofs")
    if constrained.ndim != 1 or free.ndim != 1 or not constrained.size or not free.size:
        _fail("execution_plan_partition_empty", "/constraint_partition")
    if np.any(np.diff(constrained) <= 0) or np.any(np.diff(free) <= 0):
        _fail("execution_plan_partition_not_sorted", "/constraint_partition")
    combined = np.sort(np.concatenate((constrained, free)))
    if not np.array_equal(combined, np.arange(plan.dof_count, dtype="<i4")):
        _fail("execution_plan_partition_not_complete", "/constraint_partition")
    global_to_free = plan.array("global_to_free")
    if global_to_free.shape != (plan.dof_count,):
        _fail("execution_plan_global_to_free_shape_invalid", "/dof_layout/global_to_free")
    expected = np.full(plan.dof_count, -1, dtype="<i4")
    expected[free] = np.arange(free.size, dtype="<i4")
    if not np.array_equal(global_to_free, expected):
        _fail("execution_plan_global_to_free_invalid", "/dof_layout/global_to_free")


def _validate_symbolic_pattern(plan: ExecutionPlan) -> None:
    expected = _compile_symbolic_pattern(
        dof_count=plan.dof_count,
        element_global_dofs=plan.array("element_global_dofs"),
        free_dofs=plan.array("free_dofs"),
        global_to_free=plan.array("global_to_free"),
    )
    for name, expected_array in expected.items():
        if not np.array_equal(plan.array(name), expected_array):
            _fail(
                "execution_plan_symbolic_pattern_invalid",
                f"/sparse_pattern/{name}",
            )


def _validate_compiled_operator(plan: ExecutionPlan) -> None:
    stiffness = plan.array("global_stiffness_dense")
    load = plan.array("global_load")
    if stiffness.shape != (plan.dof_count, plan.dof_count):
        _fail("execution_plan_stiffness_shape_invalid", "/compiled_operator/stiffness")
    if load.shape != (plan.dof_count,):
        _fail("execution_plan_load_shape_invalid", "/compiled_operator/load")
    if not np.all(np.isfinite(stiffness)) or not np.all(np.isfinite(load)):
        _fail("execution_plan_compiled_operator_non_finite", "/compiled_operator")
    scale = max(1.0, float(np.max(np.abs(stiffness))))
    if float(np.max(np.abs(stiffness - stiffness.T))) > scale * 1.0e-12:
        _fail("execution_plan_stiffness_not_symmetric", "/compiled_operator/stiffness")
    expected_values = _gather_csr_values(
        stiffness,
        plan.array("csr_row_ptr"),
        plan.array("csr_column_indices"),
    )
    if not np.array_equal(plan.array("global_stiffness_csr_values"), expected_values):
        _fail("execution_plan_csr_values_mismatch", "/compiled_operator/stiffness")
    transforms = plan.array("recovery_transform_global_to_local")
    local_stiffness = plan.array("recovery_stiffness_local")
    expected_shape = (plan.element_count, _ELEMENT_DOF_COUNT, _ELEMENT_DOF_COUNT)
    if transforms.shape != expected_shape or local_stiffness.shape != expected_shape:
        _fail("execution_plan_recovery_shape_invalid", "/compiled_operator/recovery")
    if not np.all(np.isfinite(transforms)) or not np.all(np.isfinite(local_stiffness)):
        _fail("execution_plan_recovery_non_finite", "/compiled_operator/recovery")
    for transform in transforms:
        if not np.allclose(transform @ transform.T, np.eye(_ELEMENT_DOF_COUNT), rtol=0.0, atol=1.0e-12):
            _fail("execution_plan_recovery_transform_invalid", "/compiled_operator/recovery")
    reconstructed = np.zeros_like(stiffness)
    element_global_dofs = plan.array("element_global_dofs")
    for index in range(plan.element_count):
        dofs = element_global_dofs[index]
        element_stiffness = (
            transforms[index].T @ local_stiffness[index] @ transforms[index]
        )
        reconstructed[np.ix_(dofs, dofs)] += element_stiffness
    if not np.allclose(
        reconstructed,
        stiffness,
        rtol=5.0e-13,
        atol=5.0e-13 * scale,
    ):
        _fail(
            "execution_plan_recovery_assembly_mismatch",
            "/compiled_operator/recovery",
        )
    backend_native_hash = _operator_hash(
        plan.solver_numeric_buffer_hash,
        stiffness,
        load,
        plan.constrained_dofs,
    )
    if plan.operator_hash != backend_native_hash:
        _fail("execution_plan_operator_hash_mismatch", "/analysis/operator_hash")


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
        for row in dofs:
            row_columns[row].update(dofs)
    nnz = sum(len(columns) for columns in row_columns)
    if nnz > _INT32_MAX:
        raise ExecutionPlanError(
            "execution_plan_int32_capacity_exceeded",
            "/sparse_pattern/nnz",
            "Canonical CSR nonzero count exceeds the Phase 0 int32 ABI.",
        )
    row_ptr_values = [0]
    column_values: list[int] = []
    position: dict[tuple[int, int], int] = {}
    for row, columns in enumerate(row_columns):
        for column in sorted(columns):
            position[(row, column)] = len(column_values)
            column_values.append(column)
        row_ptr_values.append(len(column_values))
    diagonal = [position[(row, row)] for row in range(dof_count)]
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

    reduced_row_ptr = [0]
    reduced_columns: list[int] = []
    reduced_global_positions: list[int] = []
    row_ptr_array = np.asarray(row_ptr_values, dtype="<i4")
    columns_array = np.asarray(column_values, dtype="<i4")
    for global_row in free_dofs:
        row = int(global_row)
        start = int(row_ptr_array[row])
        stop = int(row_ptr_array[row + 1])
        for global_position in range(start, stop):
            global_column = int(columns_array[global_position])
            reduced_column = int(global_to_free[global_column])
            if reduced_column >= 0:
                reduced_columns.append(reduced_column)
                reduced_global_positions.append(global_position)
        reduced_row_ptr.append(len(reduced_columns))
    if len(reduced_columns) > _INT32_MAX:
        raise ExecutionPlanError(
            "execution_plan_int32_capacity_exceeded",
            "/sparse_pattern/reduced_nnz",
            "Reduced CSR nonzero count exceeds the Phase 0 int32 ABI.",
        )
    return {
        "csr_row_ptr": immutable_array(row_ptr_values, dtype="<i4"),
        "csr_column_indices": immutable_array(column_values, dtype="<i4"),
        "csr_diagonal_positions": immutable_array(diagonal, dtype="<i4"),
        "csr_element_scatter_indices": immutable_array(scatter, dtype="<i4"),
        "reduced_csr_row_ptr": immutable_array(reduced_row_ptr, dtype="<i4"),
        "reduced_csr_column_indices": immutable_array(reduced_columns, dtype="<i4"),
        "reduced_csr_global_value_indices": immutable_array(
            reduced_global_positions, dtype="<i4"
        ),
    }


def _gather_csr_values(
    stiffness: np.ndarray, row_ptr: np.ndarray, columns: np.ndarray
) -> np.ndarray:
    values = np.empty(columns.size, dtype="<f8")
    for row in range(stiffness.shape[0]):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        values[start:stop] = stiffness[row, columns[start:stop]]
    return immutable_array(values, dtype="<f8")


def _array_descriptor(name: str, array: np.ndarray) -> PlanArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return PlanArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _partition_hash(arrays: Mapping[str, np.ndarray]) -> str:
    names = ("constrained_dofs", "free_dofs", "global_to_free")
    return canonical_hash(
        {
            "index_base": 0,
            "index_dtype": "<i4",
            "arrays": [_array_descriptor(name, arrays[name]).to_dict() for name in names],
        }
    )


def _pattern_hash(arrays: Mapping[str, np.ndarray], dof_count: int) -> str:
    names = (
        "csr_row_ptr",
        "csr_column_indices",
        "csr_diagonal_positions",
        "csr_element_scatter_indices",
        "reduced_csr_row_ptr",
        "reduced_csr_column_indices",
        "reduced_csr_global_value_indices",
    )
    return canonical_hash(
        {
            "format": "csr_full",
            "shape": [dof_count, dof_count],
            "column_order": "ascending",
            "symmetric_pattern": True,
            "solver_permutation": "NATURAL",
            "arrays": [_array_descriptor(name, arrays[name]).to_dict() for name in names],
        }
    )


def _recovery_hash_from_arrays(
    element_ids: tuple[str, ...] | list[str],
    global_dofs: np.ndarray,
    transforms: np.ndarray,
    local_stiffness: np.ndarray,
) -> str:
    artifacts = (
        ("element_global_dofs", global_dofs),
        ("recovery_transform_global_to_local", transforms),
        ("recovery_stiffness_local", local_stiffness),
    )
    return canonical_hash(
        {
            "operator_version": CPU_REFERENCE_OPERATOR_VERSION,
            "constitutive_source": "solver_model_buffers_linear_elastic_isotropic",
            "local_frame_convention": "engine_v2_frame_local_x_i_to_j_right_handed_v1",
            "element_ids": list(element_ids),
            "artifacts": [
                _array_descriptor(name, array).to_dict()
                for name, array in artifacts
            ],
        }
    )


def _plan_hash(plan: ExecutionPlan) -> str:
    payload = plan.to_dict()
    payload.pop("plan_hash")
    return canonical_hash(payload)


def _float_array_names() -> frozenset[str]:
    return frozenset(
        {
            "global_stiffness_csr_values",
            "global_stiffness_dense",
            "global_load",
            "recovery_transform_global_to_local",
            "recovery_stiffness_local",
        }
    )


def _vector_spaces(node_count: int, element_count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": "nodal_state",
            "shape": [node_count, _DOF_COUNT_PER_NODE],
            "dtype": "<f8",
            "axis_labels": ["node", "dof"],
            "component_labels": list(DOF_ORDER),
            "component_units": ["m", "m", "m", "rad", "rad", "rad"],
        },
        {
            "id": "global_equation",
            "shape": [node_count * _DOF_COUNT_PER_NODE],
            "dtype": "<f8",
            "axis_labels": ["global_dof"],
            "component_labels": ["FX", "FY", "FZ", "MX", "MY", "MZ"],
            "component_units": ["N", "N", "N", "N*m", "N*m", "N*m"],
        },
        {
            "id": "element_end_result",
            "shape": [element_count, 2, _DOF_COUNT_PER_NODE],
            "dtype": "<f8",
            "axis_labels": ["element", "end", "dof"],
            "component_labels": ["FX", "FY", "FZ", "MX", "MY", "MZ"],
            "component_units": ["N", "N", "N", "N*m", "N*m", "N*m"],
        },
        {
            "id": "scalar_result",
            "shape": [element_count],
            "dtype": "<f8",
            "axis_labels": ["element"],
            "component_labels": ["strain_energy"],
            "component_units": ["J"],
        },
    ]


@lru_cache(maxsize=1)
def _execution_plan_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / "execution_plan_v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str) -> None:
    messages = {
        "execution_plan_schema_mismatch": "ExecutionPlan schema version is invalid.",
        "execution_plan_profile_mismatch": "ExecutionPlan capability profile is invalid.",
        "execution_plan_operator_version_mismatch": "CPU operator version is invalid.",
        "execution_plan_buffer_schema_mismatch": "Solver buffer schema binding is invalid.",
        "execution_plan_backend_unsupported": "Matrix backend is unsupported.",
        "execution_plan_tolerance_invalid": "Residual tolerance must be finite and positive.",
        "execution_plan_entity_count_mismatch": "Entity counts do not match ordered IDs.",
        "execution_plan_entity_ids_invalid": "Ordered entity IDs must be unique.",
        "execution_plan_dof_count_mismatch": "Global DOF count is not node_count*6.",
        "execution_plan_descriptor_set_invalid": "Plan descriptor set/order is invalid.",
        "execution_plan_array_set_invalid": "Plan numerical payload set is invalid.",
        "execution_plan_array_dtype_mismatch": "Plan numerical payload dtype is invalid.",
        "execution_plan_array_storage_invalid": "Plan payload must be immutable C-order bytes.",
        "execution_plan_array_descriptor_mismatch": "Plan payload descriptor/hash is stale.",
        "execution_plan_node_dof_map_invalid": "Node-major global DOF map is invalid.",
        "execution_plan_element_dof_shape_invalid": "Element global DOF map shape is invalid.",
        "execution_plan_element_dof_out_of_range": "Element global DOF map is out of range.",
        "execution_plan_partition_empty": "Free and constrained partitions must be non-empty.",
        "execution_plan_partition_not_sorted": "DOF partitions must be strictly ascending.",
        "execution_plan_partition_not_complete": "DOF partitions are not a disjoint cover.",
        "execution_plan_global_to_free_shape_invalid": "global_to_free shape is invalid.",
        "execution_plan_global_to_free_invalid": "global_to_free mapping is invalid.",
        "execution_plan_symbolic_pattern_invalid": "CSR symbolic plan is inconsistent.",
        "execution_plan_stiffness_shape_invalid": "Compiled stiffness shape is invalid.",
        "execution_plan_load_shape_invalid": "Compiled load shape is invalid.",
        "execution_plan_compiled_operator_non_finite": "Compiled K/F contains non-finite values.",
        "execution_plan_stiffness_not_symmetric": "Compiled stiffness is not symmetric.",
        "execution_plan_csr_values_mismatch": "CSR values do not match the compiled stiffness.",
        "execution_plan_recovery_shape_invalid": "Recovery operator shapes are invalid.",
        "execution_plan_recovery_non_finite": "Recovery operator contains non-finite values.",
        "execution_plan_recovery_transform_invalid": "Recovery transform is not orthonormal.",
        "execution_plan_recovery_assembly_mismatch": "Global stiffness differs from recovery element assembly.",
        "execution_plan_operator_hash_mismatch": "Backend-native operator hash is stale.",
        "execution_plan_ordering_hash_mismatch": "Entity ordering hash is stale.",
        "execution_plan_partition_hash_mismatch": "Constraint partition hash is stale.",
        "execution_plan_pattern_hash_mismatch": "CSR symbolic pattern hash is stale.",
        "execution_plan_recovery_hash_mismatch": "Recovery operator hash is stale.",
        "execution_plan_hash_mismatch": "ExecutionPlan aggregate hash is stale.",
        "execution_plan_buffer_binding_mismatch": "ExecutionPlan is bound to different buffers.",
        "execution_plan_compiled_stiffness_mismatch": "Compiled K differs from bound buffers.",
        "execution_plan_compiled_load_mismatch": "Compiled F differs from bound buffers.",
    }
    raise ExecutionPlanError(code, path, messages.get(code, code))


__all__ = [
    "EXECUTION_PLAN_CAPABILITY_PROFILE",
    "EXECUTION_PLAN_SCHEMA_VERSION",
    "ExecutionPlan",
    "ExecutionPlanError",
    "PlanArrayDescriptor",
    "compile_execution_plan",
    "compute_recovery_operator_hash",
    "validate_execution_plan",
]
