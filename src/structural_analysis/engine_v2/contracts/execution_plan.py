"""Backend-neutral immutable ExecutionPlan v1 contract.

The contract freezes compiler-produced topology and sparse-pattern arrays.  It
does not assemble an operator, select a CPU/HIP backend, run a solver, or create
authoritative results.  Equation scaling can be bound through a typed extension.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import resources
import json
import re
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from ._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    has_immutable_bytes_backing,
    immutable_array,
)

EXECUTION_PLAN_SCHEMA_VERSION = "structural-analysis-execution-plan.v1"
EXECUTION_PLAN_CAPABILITY_PROFILE = "engine_v2_core_linear_static"
EXECUTION_PLAN_RESIDUAL_SIGN = "internal_minus_external"
EXECUTION_PLAN_DOF_COMPONENTS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_EXTENSION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*:[A-Za-z0-9_.-]+$")
_INT32_MAX = int(np.iinfo(np.int32).max)
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)
_ARRAY_SPECS = (
    ("node_dof_indices", "<i4"),
    ("global_to_free", "<i4"),
    ("element_global_dofs", "<i4"),
    ("constrained_dofs", "<i4"),
    ("free_dofs", "<i4"),
    ("csr_row_ptr", "<i8"),
    ("csr_column_indices", "<i4"),
)
_ARRAY_NAMES = tuple(name for name, _dtype in _ARRAY_SPECS)
_OPERATOR_GRAPH: tuple[dict[str, Any], ...] = (
    {
        "id": "assembly",
        "kind": "assembly",
        "depends_on": [],
        "input_space": "model_ir",
        "output_space": "global_equation",
    },
    {
        "id": "partition",
        "kind": "constraint_partition",
        "depends_on": ["assembly"],
        "input_space": "global_equation",
        "output_space": "free_equation",
    },
    {
        "id": "solve",
        "kind": "linear_solve",
        "depends_on": ["partition"],
        "input_space": "free_equation",
        "output_space": "global_state",
    },
    {
        "id": "residual",
        "kind": "residual",
        "depends_on": ["assembly", "solve"],
        "input_space": "global_state",
        "output_space": "global_equation",
    },
    {
        "id": "reaction",
        "kind": "reaction",
        "depends_on": ["residual"],
        "input_space": "global_equation",
        "output_space": "constrained_equation",
    },
    {
        "id": "recovery",
        "kind": "result_recovery",
        "depends_on": ["solve"],
        "input_space": "global_state",
        "output_space": "element_response",
    },
    {
        "id": "energy",
        "kind": "energy",
        "depends_on": ["solve", "recovery"],
        "input_space": "element_response",
        "output_space": "scalar",
    },
)


class ExecutionPlanError(ValueError):
    """Fail-closed contract error with a stable code and JSON pointer."""

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
    layout: Literal["C"]
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class ExecutionPlan:
    """Immutable topology, sparse pattern, and opaque operator binding."""

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
    operator_id: str
    operator_version: str
    operator_hash: str
    node_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    ordering_hash: str
    pattern_hash: str
    node_count: int
    element_count: int
    dof_count: int
    descriptors: tuple[PlanArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray]
    extensions: Mapping[str, Any]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown ExecutionPlan array: {name}") from exc

    @property
    def constrained_dofs(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.array("constrained_dofs"))

    @property
    def free_dofs(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.array("free_dofs"))

    def to_dict(self) -> dict[str, Any]:
        validate_execution_plan(self)
        return _plan_payload(self, include_plan_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def create_execution_plan(
    *,
    model_ir_content_hash: str,
    solver_buffer_schema_version: str,
    solver_numeric_buffer_hash: str,
    solver_entity_mapping_hash: str,
    solver_artifact_hash: str,
    load_pattern_id: str,
    operator_id: str,
    operator_version: str,
    operator_hash: str,
    node_ids: Sequence[str],
    element_ids: Sequence[str],
    node_dof_indices: Any,
    global_to_free: Any,
    element_global_dofs: Any,
    constrained_dofs: Any,
    free_dofs: Any,
    csr_row_ptr: Any,
    csr_column_indices: Any,
    plan_id: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> ExecutionPlan:
    """Freeze compiler outputs without importing or invoking an executor."""

    nodes = _stable_id_tuple(node_ids, "/entity_order/node_ids")
    elements = _stable_id_tuple(element_ids, "/entity_order/element_ids")
    if not nodes or not elements:
        _fail(
            "entity_order_invalid",
            "/entity_order",
            "At least one node and one element are required.",
        )
    node_count = len(nodes)
    element_count = len(elements)
    dof_count = node_count * len(EXECUTION_PLAN_DOF_COMPONENTS)
    values = {
        "node_dof_indices": node_dof_indices,
        "global_to_free": global_to_free,
        "element_global_dofs": element_global_dofs,
        "constrained_dofs": constrained_dofs,
        "free_dofs": free_dofs,
        "csr_row_ptr": csr_row_ptr,
        "csr_column_indices": csr_column_indices,
    }
    arrays = MappingProxyType(
        {
            name: _immutable_index_array(
                values[name], dtype=dtype, path=f"/arrays/{name}"
            )
            for name, dtype in _ARRAY_SPECS
        }
    )
    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES)
    ordering_hash = _ordering_hash(nodes, elements)
    pattern_hash = _pattern_hash(arrays)
    normalized_id = plan_id or (
        f"plan.{model_ir_content_hash.removeprefix('sha256:')[:12]}.{load_pattern_id}"
    )
    frozen_extensions = _freeze_extensions({} if extensions is None else extensions)
    provisional = ExecutionPlan(
        schema_version=EXECUTION_PLAN_SCHEMA_VERSION,
        capability_profile=EXECUTION_PLAN_CAPABILITY_PROFILE,
        plan_id=normalized_id,
        plan_hash="sha256:" + "0" * 64,
        model_ir_content_hash=model_ir_content_hash,
        solver_buffer_schema_version=solver_buffer_schema_version,
        solver_numeric_buffer_hash=solver_numeric_buffer_hash,
        solver_entity_mapping_hash=solver_entity_mapping_hash,
        solver_artifact_hash=solver_artifact_hash,
        load_pattern_id=load_pattern_id,
        operator_id=operator_id,
        operator_version=operator_version,
        operator_hash=operator_hash,
        node_ids=nodes,
        element_ids=elements,
        ordering_hash=ordering_hash,
        pattern_hash=pattern_hash,
        node_count=node_count,
        element_count=element_count,
        dof_count=dof_count,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=frozen_extensions,
    )
    plan = ExecutionPlan(
        **{
            **provisional.__dict__,
            "plan_hash": canonical_hash(
                _plan_payload(provisional, include_plan_hash=False)
            ),
        }
    )
    return validate_execution_plan(plan)


def validate_execution_plan(plan: ExecutionPlan) -> ExecutionPlan:
    """Recompute array, topology, schema, and aggregate-hash invariants."""

    if not isinstance(plan, ExecutionPlan):
        _fail("execution_plan_type_invalid", "/", "Expected an ExecutionPlan.")
    if plan.schema_version != EXECUTION_PLAN_SCHEMA_VERSION:
        _fail("schema_version_invalid", "/schema_version", "Unsupported schema.")
    if plan.capability_profile != EXECUTION_PLAN_CAPABILITY_PROFILE:
        _fail(
            "capability_profile_invalid",
            "/capability_profile",
            "Unsupported capability profile.",
        )
    for path, value in (
        ("/plan_id", plan.plan_id),
        (
            "/solver_artifact_bindings/schema_version",
            plan.solver_buffer_schema_version,
        ),
        ("/analysis/load_pattern_id", plan.load_pattern_id),
        ("/analysis/operator_id", plan.operator_id),
        ("/analysis/operator_version", plan.operator_version),
    ):
        _require_stable_id(value, path)
    for path, value in (
        ("/plan_hash", plan.plan_hash),
        ("/model_ir_content_hash", plan.model_ir_content_hash),
        (
            "/solver_artifact_bindings/numeric_buffer_hash",
            plan.solver_numeric_buffer_hash,
        ),
        (
            "/solver_artifact_bindings/entity_mapping_hash",
            plan.solver_entity_mapping_hash,
        ),
        ("/solver_artifact_bindings/artifact_hash", plan.solver_artifact_hash),
        ("/analysis/operator_hash", plan.operator_hash),
        ("/entity_order/ordering_hash", plan.ordering_hash),
        ("/sparse_pattern/pattern_hash", plan.pattern_hash),
    ):
        _require_hash(value, path)
    if not isinstance(plan.node_ids, tuple) or not isinstance(plan.element_ids, tuple):
        _fail(
            "entity_order_type_invalid",
            "/entity_order",
            "Entity orders must be tuples.",
        )
    nodes = _stable_id_tuple(plan.node_ids, "/entity_order/node_ids")
    elements = _stable_id_tuple(plan.element_ids, "/entity_order/element_ids")
    if not nodes or not elements:
        _fail("entity_order_invalid", "/entity_order", "Entity orders cannot be empty.")
    if len(nodes) != len(set(nodes)) or len(elements) != len(set(elements)):
        _fail("entity_order_duplicate", "/entity_order", "Entity IDs must be unique.")
    for path, value in (
        ("/dof_layout/node_count", plan.node_count),
        ("/dof_layout/element_count", plan.element_count),
        ("/dof_layout/dof_count", plan.dof_count),
    ):
        _require_exact_int(value, path, minimum=1)
    if plan.node_count != len(nodes) or plan.element_count != len(elements):
        _fail("entity_count_mismatch", "/entity_order", "Entity counts are stale.")
    if plan.dof_count != plan.node_count * len(EXECUTION_PLAN_DOF_COMPONENTS):
        _fail(
            "dof_count_invalid",
            "/dof_layout/dof_count",
            "DOF count must equal node_count*6.",
        )
    if plan.ordering_hash != _ordering_hash(nodes, elements):
        _fail(
            "ordering_hash_mismatch",
            "/entity_order/ordering_hash",
            "Ordering hash is stale.",
        )
    if not isinstance(plan._arrays, MappingProxyType):
        _fail("plan_arrays_mutable", "/array_descriptors", "Array map is mutable.")
    if tuple(plan._arrays) != _ARRAY_NAMES:
        _fail(
            "plan_array_set_invalid",
            "/array_descriptors",
            "Array set or order is invalid.",
        )
    if (
        not isinstance(plan.descriptors, tuple)
        or tuple(descriptor.name for descriptor in plan.descriptors) != _ARRAY_NAMES
    ):
        _fail(
            "array_descriptor_set_invalid",
            "/array_descriptors",
            "Descriptor set or order is invalid.",
        )
    descriptor_by_name = {row.name: row for row in plan.descriptors}
    for name, dtype in _ARRAY_SPECS:
        array = plan._arrays[name]
        _validate_contract_array(array, dtype=dtype, path=f"/arrays/{name}")
        if descriptor_by_name[name] != _array_descriptor(name, array):
            _fail(
                "array_descriptor_mismatch",
                f"/array_descriptors/{name}",
                "Descriptor does not match immutable array bytes.",
            )
    _validate_array_semantics(plan)
    if plan.pattern_hash != _pattern_hash(plan._arrays):
        _fail(
            "pattern_hash_mismatch",
            "/sparse_pattern/pattern_hash",
            "CSR pattern hash is stale.",
        )
    _validate_extensions(plan.extensions)
    manifest = _plan_payload(plan, include_plan_hash=True)
    validate_execution_plan_manifest(manifest)
    if plan.plan_hash != canonical_hash(_plan_payload(plan, include_plan_hash=False)):
        _fail(
            "plan_hash_mismatch",
            "/plan_hash",
            "Plan hash does not match the canonical manifest.",
        )
    if "engine-v2:equation-scaling" in plan.extensions:
        # Local import preserves the one-way contract dependency while allowing
        # ExecutionPlan validation to fail closed on the typed PR-B extension.
        from .equation_scaling import _validate_equation_scaling_binding_semantics

        _validate_equation_scaling_binding_semantics(plan)
    return plan


def validate_execution_plan_manifest(payload: Any) -> Mapping[str, Any]:
    """Reject unknown fields, wrong JSON types, and stale manifest hashes."""

    errors = sorted(
        _execution_plan_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("execution_plan_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail("execution_plan_manifest_type_invalid", "/", "Expected an object.")
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("plan_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail("plan_hash_mismatch", "/plan_hash", "Manifest plan hash is stale.")
    return payload


def _validate_array_semantics(plan: ExecutionPlan) -> None:
    node_dofs = plan.array("node_dof_indices")
    global_to_free = plan.array("global_to_free")
    element_dofs = plan.array("element_global_dofs")
    constrained = plan.array("constrained_dofs")
    free = plan.array("free_dofs")
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    expected_shapes = {
        "node_dof_indices": (plan.node_count, 6),
        "global_to_free": (plan.dof_count,),
        "element_global_dofs": (plan.element_count, 12),
        "constrained_dofs": (constrained.size,),
        "free_dofs": (free.size,),
        "csr_row_ptr": (plan.dof_count + 1,),
        "csr_column_indices": (columns.size,),
    }
    for name, shape in expected_shapes.items():
        if plan.array(name).shape != shape:
            _fail(
                "array_shape_invalid",
                f"/arrays/{name}",
                f"Expected shape {shape}.",
            )
    expected_node_dofs = np.arange(plan.dof_count, dtype="<i4").reshape(
        plan.node_count, 6
    )
    if not np.array_equal(node_dofs, expected_node_dofs):
        _fail(
            "node_dof_order_invalid",
            "/arrays/node_dof_indices",
            "Node-major six-DOF order is required.",
        )
    if constrained.size + free.size != plan.dof_count:
        _fail(
            "dof_partition_invalid",
            "/constraint_partition",
            "Partition must cover every DOF once.",
        )
    for name, values in (("constrained_dofs", constrained), ("free_dofs", free)):
        if values.size and (
            int(values[0]) < 0
            or int(values[-1]) >= plan.dof_count
            or np.any(values[1:] <= values[:-1])
        ):
            _fail(
                "dof_partition_invalid",
                f"/arrays/{name}",
                "DOFs must be sorted, unique, and in range.",
            )
    if np.intersect1d(constrained, free).size or not np.array_equal(
        np.sort(np.concatenate((constrained, free))), np.arange(plan.dof_count)
    ):
        _fail(
            "dof_partition_invalid",
            "/constraint_partition",
            "Partition overlaps or omits a global DOF.",
        )
    expected_global_to_free = np.full(plan.dof_count, -1, dtype="<i4")
    expected_global_to_free[free] = np.arange(free.size, dtype="<i4")
    if not np.array_equal(global_to_free, expected_global_to_free):
        _fail(
            "global_to_free_invalid",
            "/arrays/global_to_free",
            "Reduced-DOF map is inconsistent.",
        )
    if element_dofs.size and (
        int(element_dofs.min()) < 0
        or int(element_dofs.max()) >= plan.dof_count
        or any(np.unique(row).size != 12 for row in element_dofs)
    ):
        _fail(
            "element_dof_map_invalid",
            "/arrays/element_global_dofs",
            "Element DOFs must be unique and in range.",
        )
    if row_ptr[0] != 0 or np.any(row_ptr[1:] < row_ptr[:-1]):
        _fail(
            "csr_row_ptr_invalid",
            "/arrays/csr_row_ptr",
            "CSR row pointers must start at zero and be monotone.",
        )
    if int(row_ptr[-1]) != columns.size:
        _fail(
            "csr_row_ptr_invalid",
            "/arrays/csr_row_ptr",
            "Final CSR pointer must equal column count.",
        )
    if columns.size and (
        int(columns.min()) < 0 or int(columns.max()) >= plan.dof_count
    ):
        _fail(
            "csr_column_invalid",
            "/arrays/csr_column_indices",
            "CSR column is out of range.",
        )
    for row in range(plan.dof_count):
        start, stop = int(row_ptr[row]), int(row_ptr[row + 1])
        row_columns = columns[start:stop]
        if row_columns.size == 0 or np.any(row_columns[1:] <= row_columns[:-1]):
            _fail(
                "csr_row_invalid",
                f"/sparse_pattern/row/{row}",
                "CSR rows must be nonempty, sorted, and unique.",
            )
        if not np.any(row_columns == row):
            _fail(
                "csr_diagonal_missing",
                f"/sparse_pattern/row/{row}",
                "Every equation row requires a diagonal entry.",
            )


def _plan_payload(plan: ExecutionPlan, *, include_plan_hash: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "capability_profile": plan.capability_profile,
        "model_ir_content_hash": plan.model_ir_content_hash,
        "solver_artifact_bindings": {
            "schema_version": plan.solver_buffer_schema_version,
            "numeric_buffer_hash": plan.solver_numeric_buffer_hash,
            "entity_mapping_hash": plan.solver_entity_mapping_hash,
            "artifact_hash": plan.solver_artifact_hash,
        },
        "analysis": {
            "type": "linear_static",
            "load_pattern_id": plan.load_pattern_id,
            "residual_sign": EXECUTION_PLAN_RESIDUAL_SIGN,
            "operator_id": plan.operator_id,
            "operator_version": plan.operator_version,
            "operator_hash": plan.operator_hash,
        },
        "entity_order": {
            "node_ids": list(plan.node_ids),
            "element_ids": list(plan.element_ids),
            "ordering_hash": plan.ordering_hash,
        },
        "dof_layout": {
            "components": list(EXECUTION_PLAN_DOF_COMPONENTS),
            "node_count": plan.node_count,
            "element_count": plan.element_count,
            "dofs_per_node": 6,
            "dof_count": plan.dof_count,
            "index_base": 0,
            "node_dof_indices": "node_dof_indices",
            "global_to_free": "global_to_free",
            "element_global_dofs": "element_global_dofs",
        },
        "constraint_partition": {
            "constrained_dofs": "constrained_dofs",
            "free_dofs": "free_dofs",
        },
        "sparse_pattern": {
            "format": "csr",
            "index_base": 0,
            "row_ptr": "csr_row_ptr",
            "column_indices": "csr_column_indices",
            "pattern_hash": plan.pattern_hash,
        },
        "array_descriptors": {row.name: row.to_dict() for row in plan.descriptors},
        "operator_graph": [
            {**row, "depends_on": list(row["depends_on"])} for row in _OPERATOR_GRAPH
        ],
        "execution_policy": {
            "precision": "fp64",
            "fallback": "forbidden",
            "placement": "runtime_selected",
            "backend_binding": "external",
        },
        "state_contract": {
            "schema_version": "structural-analysis-state-ir.v1",
            "accepted_state_immutable": True,
            "trial_commit_rollback": True,
        },
        "extensions": _thaw(plan.extensions),
    }
    if include_plan_hash:
        payload["plan_hash"] = plan.plan_hash
    return payload


def _immutable_index_array(value: Any, *, dtype: str, path: str) -> np.ndarray:
    source = np.asarray(value)
    if (
        source.size == 0
        and isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
    ):
        source = np.asarray(value, dtype=dtype)
    if source.dtype.kind not in "iu" or source.dtype.kind == "b":
        _fail(
            "array_type_invalid",
            path,
            "Index arrays require exact integer values.",
        )
    if source.ndim not in (1, 2):
        _fail("array_rank_invalid", path, "Index arrays must be rank one or two.")
    if source.size:
        info = np.iinfo(np.dtype(dtype))
        if int(source.min()) < int(info.min) or int(source.max()) > int(info.max):
            _fail("array_range_invalid", path, f"Values do not fit {dtype}.")
    try:
        return immutable_array(source, dtype=dtype)
    except CanonicalContractError as exc:  # pragma: no cover
        _fail("array_invalid", path, str(exc))


def _validate_contract_array(array: Any, *, dtype: str, path: str) -> None:
    if not isinstance(array, np.ndarray):
        _fail("array_type_invalid", path, "Expected a NumPy array.")
    if array.dtype.str != dtype:
        _fail("array_dtype_invalid", path, f"Expected canonical dtype {dtype}.")
    if not array.flags.c_contiguous:
        _fail("array_layout_invalid", path, "Expected C-contiguous layout.")
    if not has_immutable_bytes_backing(array):
        _fail("array_mutable", path, "Array must be backed by immutable bytes.")


def _array_descriptor(name: str, array: np.ndarray) -> PlanArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
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


def _ordering_hash(node_ids: tuple[str, ...], element_ids: tuple[str, ...]) -> str:
    return canonical_hash(
        {
            "node_ids": list(node_ids),
            "element_ids": list(element_ids),
            "dof_components": list(EXECUTION_PLAN_DOF_COMPONENTS),
        }
    )


def _pattern_hash(arrays: Mapping[str, np.ndarray]) -> str:
    return canonical_hash(
        {
            "format": "csr",
            "row_ptr_data_hash": array_data_hash(arrays["csr_row_ptr"]),
            "column_indices_data_hash": array_data_hash(arrays["csr_column_indices"]),
        }
    )


def _stable_id_tuple(value: Any, path: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(
            "entity_order_type_invalid",
            path,
            "Expected a sequence of stable IDs.",
        )
    result = tuple(value)
    for index, item in enumerate(result):
        _require_stable_id(item, f"{path}/{index}")
    return result


def _freeze_extensions(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("extensions_invalid", "/extensions", "Expected an object.")
    try:
        normalized = json.loads(canonical_json_bytes(value))
    except (CanonicalContractError, json.JSONDecodeError) as exc:
        _fail("extensions_invalid", "/extensions", str(exc))
    return _freeze(normalized)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _is_frozen(value: Any) -> bool:
    if isinstance(value, MappingProxyType):
        return all(_is_frozen(item) for item in value.values())
    if isinstance(value, tuple):
        return all(_is_frozen(item) for item in value)
    return value is None or type(value) in (str, bool, int, float)


def _validate_extensions(value: Any) -> None:
    if not isinstance(value, MappingProxyType) or not _is_frozen(value):
        _fail(
            "extensions_mutable",
            "/extensions",
            "Extensions must be deeply immutable.",
        )
    for key in value:
        if not isinstance(key, str) or _EXTENSION_KEY_PATTERN.fullmatch(key) is None:
            _fail(
                "extension_key_invalid",
                f"/extensions/{key}",
                "Invalid extension key.",
            )
    try:
        canonical_json_bytes(_thaw(value))
    except CanonicalContractError as exc:
        _fail("extensions_invalid", "/extensions", str(exc))


def _require_hash(value: Any, path: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hash_invalid", path, "Expected sha256:<64 lowercase hex>.")
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail("stable_id_invalid", path, "Invalid stable identifier.")
    return value


def _require_exact_int(value: Any, path: str, *, minimum: int) -> int:
    if type(value) is not int:
        _fail(
            "integer_type_invalid",
            path,
            "Expected an integer, not bool or float.",
        )
    if value < minimum or value > _INT32_MAX:
        _fail(
            "integer_range_invalid",
            path,
            f"Expected {minimum}..{_INT32_MAX}.",
        )
    return value


@lru_cache(maxsize=1)
def _execution_plan_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "execution_plan_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):  # pragma: no cover
        raise TypeError("Packaged ExecutionPlan schema must be an object.")
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise ExecutionPlanError(code, path, message)


__all__ = [
    "EXECUTION_PLAN_CAPABILITY_PROFILE",
    "EXECUTION_PLAN_DOF_COMPONENTS",
    "EXECUTION_PLAN_RESIDUAL_SIGN",
    "EXECUTION_PLAN_SCHEMA_VERSION",
    "ExecutionPlan",
    "ExecutionPlanError",
    "PlanArrayDescriptor",
    "create_execution_plan",
    "validate_execution_plan",
    "validate_execution_plan_manifest",
]
