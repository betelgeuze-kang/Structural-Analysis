"""Deterministic free-equation CSR identity bound to ExecutionPlan v1.

The artifact derives the reduced pattern once from the exact global CSR and
partition.  CPU and HIP consumers select numeric values through the retained
global-value positions instead of independently rebuilding a reduced matrix.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import re
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from ._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from .execution_plan import ExecutionPlan, validate_execution_plan

EXECUTION_PLAN_REDUCED_CSR_SCHEMA_VERSION = (
    "structural-analysis-execution-plan-reduced-csr.v1"
)
REDUCED_CSR_EQUATION_SCOPE = "free_equations"
REDUCED_CSR_NUMERIC_VALUES_SCOPE = "global_csr_values_in_global_pattern_order"
REDUCED_CSR_SELECTION_ORDER = "ascending_free_row_then_ascending_global_csr_position.v1"

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)
_ARRAY_SPECS = (
    ("free_csr_row_ptr", "<i8"),
    ("free_csr_column_indices", "<i4"),
    ("free_csr_global_value_indices", "<i8"),
)
_ARRAY_NAMES = tuple(name for name, _dtype in _ARRAY_SPECS)


class ExecutionPlanReducedCSRError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class ReducedCSRArrayDescriptor:
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
class ExecutionPlanReducedCSR:
    schema_version: str
    identity_hash: str
    execution_plan_hash: str
    model_ir_content_hash: str
    load_pattern_id: str
    operator_hash: str
    global_pattern_hash: str
    global_to_free_content_hash: str
    free_dofs_content_hash: str
    operator_numeric_values_hash: str
    free_pattern_hash: str
    free_count: int
    free_nnz: int
    terminal_disposition: Literal["solve_free_equations", "no_solve_reaction_only"]
    descriptors: tuple[ReducedCSRArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray]
    _source_plan: ExecutionPlan

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown reduced-CSR array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_execution_plan_reduced_csr(self)
        return _identity_payload(self, include_identity_hash=True)


def create_execution_plan_reduced_csr(
    execution_plan: ExecutionPlan,
    *,
    operator_numeric_values_hash: str,
) -> ExecutionPlanReducedCSR:
    plan = validate_execution_plan(execution_plan)
    numeric_hash = _require_hash(
        operator_numeric_values_hash, "/global_csr/operator_numeric_values_hash"
    )
    derived = _derive_reduced_arrays(plan)
    arrays = MappingProxyType(
        {
            name: immutable_array(derived[name], dtype=dtype)
            for name, dtype in _ARRAY_SPECS
        }
    )
    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES)
    descriptor_by_name = {row.name: row for row in descriptors}
    plan_descriptor_by_name = {row.name: row for row in plan.descriptors}
    global_to_free_hash = plan_descriptor_by_name["global_to_free"].content_hash
    free_dofs_hash = plan_descriptor_by_name["free_dofs"].content_hash
    free_pattern_hash = _free_pattern_hash(
        global_pattern_hash=plan.pattern_hash,
        global_to_free_content_hash=global_to_free_hash,
        free_dofs_content_hash=free_dofs_hash,
        descriptor_by_name=descriptor_by_name,
    )
    free_count = int(plan.array("free_dofs").size)
    provisional = ExecutionPlanReducedCSR(
        schema_version=EXECUTION_PLAN_REDUCED_CSR_SCHEMA_VERSION,
        identity_hash="sha256:" + "0" * 64,
        execution_plan_hash=plan.plan_hash,
        model_ir_content_hash=plan.model_ir_content_hash,
        load_pattern_id=plan.load_pattern_id,
        operator_hash=plan.operator_hash,
        global_pattern_hash=plan.pattern_hash,
        global_to_free_content_hash=global_to_free_hash,
        free_dofs_content_hash=free_dofs_hash,
        operator_numeric_values_hash=numeric_hash,
        free_pattern_hash=free_pattern_hash,
        free_count=free_count,
        free_nnz=int(arrays["free_csr_column_indices"].size),
        terminal_disposition=(
            "no_solve_reaction_only" if free_count == 0 else "solve_free_equations"
        ),
        descriptors=descriptors,
        _arrays=arrays,
        _source_plan=plan,
    )
    identity = replace(provisional, identity_hash=_identity_hash(provisional))
    return validate_execution_plan_reduced_csr(identity)


def validate_execution_plan_reduced_csr(
    identity: ExecutionPlanReducedCSR,
    *,
    execution_plan: ExecutionPlan | None = None,
) -> ExecutionPlanReducedCSR:
    if type(identity) is not ExecutionPlanReducedCSR:
        _fail("reduced_csr_type_invalid", "/", "Expected ExecutionPlanReducedCSR.")
    plan = validate_execution_plan(
        identity._source_plan if execution_plan is None else execution_plan
    )
    if identity.schema_version != EXECUTION_PLAN_REDUCED_CSR_SCHEMA_VERSION:
        _fail("schema_version_invalid", "/schema_version", "Unsupported schema.")
    for path, value in (
        ("/identity_hash", identity.identity_hash),
        ("/source_plan/execution_plan_hash", identity.execution_plan_hash),
        ("/source_plan/model_ir_content_hash", identity.model_ir_content_hash),
        ("/source_plan/operator_hash", identity.operator_hash),
        ("/global_csr/pattern_hash", identity.global_pattern_hash),
        (
            "/partition/global_to_free_content_hash",
            identity.global_to_free_content_hash,
        ),
        ("/partition/free_dofs_content_hash", identity.free_dofs_content_hash),
        (
            "/global_csr/operator_numeric_values_hash",
            identity.operator_numeric_values_hash,
        ),
        ("/free_csr/pattern_hash", identity.free_pattern_hash),
    ):
        _require_hash(value, path)
    if not isinstance(identity._arrays, MappingProxyType):
        _fail(
            "reduced_csr_arrays_mutable", "/array_descriptors", "Array map is mutable."
        )
    if tuple(identity._arrays) != _ARRAY_NAMES:
        _fail(
            "reduced_csr_array_set_invalid",
            "/array_descriptors",
            "Array set is invalid.",
        )
    if (
        type(identity.descriptors) is not tuple
        or tuple(row.name for row in identity.descriptors) != _ARRAY_NAMES
        or any(
            type(row) is not ReducedCSRArrayDescriptor for row in identity.descriptors
        )
    ):
        _fail(
            "reduced_csr_descriptor_set_invalid",
            "/array_descriptors",
            "Descriptor set is invalid.",
        )
    descriptor_by_name = {row.name: row for row in identity.descriptors}
    for name, dtype in _ARRAY_SPECS:
        array = identity._arrays[name]
        _validate_array(array, dtype=dtype, path=f"/arrays/{name}")
        if descriptor_by_name[name] != _array_descriptor(name, array):
            _fail(
                "reduced_csr_descriptor_mismatch",
                f"/array_descriptors/{name}",
                "Descriptor does not match immutable bytes.",
            )

    expected_source = {
        "execution_plan_hash": plan.plan_hash,
        "model_ir_content_hash": plan.model_ir_content_hash,
        "load_pattern_id": plan.load_pattern_id,
        "operator_hash": plan.operator_hash,
        "global_pattern_hash": plan.pattern_hash,
    }
    actual_source = {
        "execution_plan_hash": identity.execution_plan_hash,
        "model_ir_content_hash": identity.model_ir_content_hash,
        "load_pattern_id": identity.load_pattern_id,
        "operator_hash": identity.operator_hash,
        "global_pattern_hash": identity.global_pattern_hash,
    }
    if actual_source != expected_source:
        _fail(
            "reduced_csr_source_plan_mismatch",
            "/source_plan",
            "Reduced CSR identifies another ExecutionPlan.",
        )
    plan_descriptors = {row.name: row for row in plan.descriptors}
    if (
        identity.global_to_free_content_hash
        != plan_descriptors["global_to_free"].content_hash
        or identity.free_dofs_content_hash != plan_descriptors["free_dofs"].content_hash
    ):
        _fail(
            "reduced_csr_partition_mismatch",
            "/partition",
            "Partition descriptor hashes are stale.",
        )

    expected_arrays = _derive_reduced_arrays(plan)
    if any(
        not np.array_equal(identity.array(name), expected_arrays[name])
        for name in _ARRAY_NAMES
    ):
        _fail(
            "reduced_csr_derivation_mismatch",
            "/arrays",
            "Reduced CSR is not the exact projection of global CSR and free DOFs.",
        )
    free_count = int(plan.array("free_dofs").size)
    free_nnz = int(identity.array("free_csr_column_indices").size)
    expected_terminal = (
        "no_solve_reaction_only" if free_count == 0 else "solve_free_equations"
    )
    if (
        identity.free_count != free_count
        or identity.free_nnz != free_nnz
        or identity.terminal_disposition != expected_terminal
    ):
        _fail(
            "reduced_csr_dimensions_mismatch",
            "/free_csr",
            "Free dimensions or terminal disposition are stale.",
        )
    expected_pattern_hash = _free_pattern_hash(
        global_pattern_hash=identity.global_pattern_hash,
        global_to_free_content_hash=identity.global_to_free_content_hash,
        free_dofs_content_hash=identity.free_dofs_content_hash,
        descriptor_by_name=descriptor_by_name,
    )
    if identity.free_pattern_hash != expected_pattern_hash:
        _fail(
            "reduced_csr_pattern_hash_mismatch",
            "/free_csr/pattern_hash",
            "Free CSR pattern hash is stale.",
        )
    validate_execution_plan_reduced_csr_manifest(
        _identity_payload(identity, include_identity_hash=True)
    )
    if identity.identity_hash != _identity_hash(identity):
        _fail(
            "reduced_csr_identity_hash_mismatch",
            "/identity_hash",
            "Reduced CSR identity hash is stale.",
        )
    return identity


def validate_execution_plan_reduced_csr_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("reduced_csr_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail("reduced_csr_manifest_type_invalid", "/", "Expected an object.")
    free_count = payload["partition"]["free_count"]
    free_nnz = payload["free_csr"]["nnz"]
    descriptors = payload["array_descriptors"]
    expected_shapes = {
        "free_csr_row_ptr": [free_count + 1],
        "free_csr_column_indices": [free_nnz],
        "free_csr_global_value_indices": [free_nnz],
    }
    expected_byte_lengths = {
        "free_csr_row_ptr": 8 * (free_count + 1),
        "free_csr_column_indices": 4 * free_nnz,
        "free_csr_global_value_indices": 8 * free_nnz,
    }
    expected_dtypes = dict(_ARRAY_SPECS)
    for name in _ARRAY_NAMES:
        if (
            descriptors[name]["name"] != name
            or descriptors[name]["dtype"] != expected_dtypes[name]
            or descriptors[name]["shape"] != expected_shapes[name]
            or descriptors[name]["byte_length"] != expected_byte_lengths[name]
        ):
            _fail(
                "reduced_csr_descriptor_semantics_invalid",
                f"/array_descriptors/{name}",
                "Descriptor shape or byte length is stale.",
            )
    expected_terminal = (
        "no_solve_reaction_only" if free_count == 0 else "solve_free_equations"
    )
    if payload["terminal_disposition"] != expected_terminal:
        _fail(
            "reduced_csr_terminal_disposition_invalid",
            "/terminal_disposition",
            "Terminal disposition does not match the free-equation count.",
        )
    expected_pattern_hash = _free_pattern_hash_from_manifest(payload)
    if payload["free_csr"]["pattern_hash"] != expected_pattern_hash:
        _fail(
            "reduced_csr_pattern_hash_mismatch",
            "/free_csr/pattern_hash",
            "Free CSR pattern hash is stale.",
        )
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("identity_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "reduced_csr_identity_hash_mismatch",
            "/identity_hash",
            "Reduced CSR identity hash is stale.",
        )
    return payload


def _derive_reduced_arrays(plan: ExecutionPlan) -> dict[str, np.ndarray]:
    free_dofs = plan.array("free_dofs")
    global_to_free = plan.array("global_to_free")
    global_row_ptr = plan.array("csr_row_ptr")
    global_columns = plan.array("csr_column_indices")
    row_ptr = [0]
    columns: list[int] = []
    global_positions: list[int] = []
    for global_row_value in free_dofs:
        global_row = int(global_row_value)
        start = int(global_row_ptr[global_row])
        stop = int(global_row_ptr[global_row + 1])
        for global_position in range(start, stop):
            free_column = int(global_to_free[int(global_columns[global_position])])
            if free_column >= 0:
                columns.append(free_column)
                global_positions.append(global_position)
        row_ptr.append(len(columns))
    return {
        "free_csr_row_ptr": np.asarray(row_ptr, dtype="<i8"),
        "free_csr_column_indices": np.asarray(columns, dtype="<i4"),
        "free_csr_global_value_indices": np.asarray(global_positions, dtype="<i8"),
    }


def _identity_payload(
    identity: ExecutionPlanReducedCSR, *, include_identity_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "source_plan": {
            "execution_plan_hash": identity.execution_plan_hash,
            "model_ir_content_hash": identity.model_ir_content_hash,
            "load_pattern_id": identity.load_pattern_id,
            "operator_hash": identity.operator_hash,
        },
        "partition": {
            "equation_scope": REDUCED_CSR_EQUATION_SCOPE,
            "free_count": identity.free_count,
            "global_to_free_content_hash": identity.global_to_free_content_hash,
            "free_dofs_content_hash": identity.free_dofs_content_hash,
        },
        "global_csr": {
            "pattern_hash": identity.global_pattern_hash,
            "operator_numeric_values_hash": identity.operator_numeric_values_hash,
            "numeric_values_scope": REDUCED_CSR_NUMERIC_VALUES_SCOPE,
        },
        "free_csr": {
            "format": "csr",
            "row_ptr": "free_csr_row_ptr",
            "column_indices": "free_csr_column_indices",
            "global_value_indices": "free_csr_global_value_indices",
            "selection_order": REDUCED_CSR_SELECTION_ORDER,
            "nnz": identity.free_nnz,
            "pattern_hash": identity.free_pattern_hash,
        },
        "array_descriptors": {row.name: row.to_dict() for row in identity.descriptors},
        "terminal_disposition": identity.terminal_disposition,
        "claim_boundary": {
            "solver_executed": False,
            "result_authority": False,
            "numeric_values_embedded": False,
            "cpu_hip_must_consume_same_identity": True,
            "fully_constrained_recurrence_allowed": False,
        },
    }
    if include_identity_hash:
        payload["identity_hash"] = identity.identity_hash
    return payload


def _identity_hash(identity: ExecutionPlanReducedCSR) -> str:
    return canonical_hash(_identity_payload(identity, include_identity_hash=False))


def _free_pattern_hash(
    *,
    global_pattern_hash: str,
    global_to_free_content_hash: str,
    free_dofs_content_hash: str,
    descriptor_by_name: Mapping[str, ReducedCSRArrayDescriptor],
) -> str:
    return canonical_hash(
        {
            "format": "csr",
            "equation_scope": REDUCED_CSR_EQUATION_SCOPE,
            "selection_order": REDUCED_CSR_SELECTION_ORDER,
            "global_pattern_hash": global_pattern_hash,
            "global_to_free_content_hash": global_to_free_content_hash,
            "free_dofs_content_hash": free_dofs_content_hash,
            "free_csr_row_ptr_content_hash": descriptor_by_name[
                "free_csr_row_ptr"
            ].content_hash,
            "free_csr_column_indices_content_hash": descriptor_by_name[
                "free_csr_column_indices"
            ].content_hash,
            "free_csr_global_value_indices_content_hash": descriptor_by_name[
                "free_csr_global_value_indices"
            ].content_hash,
        }
    )


def _free_pattern_hash_from_manifest(payload: Mapping[str, Any]) -> str:
    descriptors = payload["array_descriptors"]
    return canonical_hash(
        {
            "format": "csr",
            "equation_scope": payload["partition"]["equation_scope"],
            "selection_order": payload["free_csr"]["selection_order"],
            "global_pattern_hash": payload["global_csr"]["pattern_hash"],
            "global_to_free_content_hash": payload["partition"][
                "global_to_free_content_hash"
            ],
            "free_dofs_content_hash": payload["partition"]["free_dofs_content_hash"],
            "free_csr_row_ptr_content_hash": descriptors["free_csr_row_ptr"][
                "content_hash"
            ],
            "free_csr_column_indices_content_hash": descriptors[
                "free_csr_column_indices"
            ]["content_hash"],
            "free_csr_global_value_indices_content_hash": descriptors[
                "free_csr_global_value_indices"
            ]["content_hash"],
        }
    )


def _array_descriptor(name: str, array: np.ndarray) -> ReducedCSRArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return ReducedCSRArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _validate_array(array: Any, *, dtype: str, path: str) -> None:
    if type(array) is not np.ndarray or array.dtype.str != dtype or array.ndim != 1:
        _fail(
            "reduced_csr_array_contract_invalid",
            path,
            f"Expected rank-one {dtype} array.",
        )
    if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
        _fail(
            "reduced_csr_array_mutable", path, "Array requires immutable C-order bytes."
        )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hash_invalid", path, "Expected sha256:<64 lowercase hex>.")
    return value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "execution_plan_reduced_csr_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise ExecutionPlanReducedCSRError(code, path, message)
