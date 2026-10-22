"""Direct free-CSR trials for the existing fixed-chord fiber frame.

Newton trials discard element responses; terminal/recovery trials retain them.
Legacy serialization retains ordinary dense lists. An unchanged exact CSR
boundary builds one temporary dense row; modified hooks use the original dense
conversion. Assembly never allocates the full global square tangent.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from types import BuiltinFunctionType, FunctionType
from typing import Any, NamedTuple, cast

import numpy as np
from scipy.sparse import csr_matrix

from .stateful_fiber_frame2d import (
    StatefulFiberFrame2DAssembly,
    StatefulFiberFrame2DMemberAssembly,
    StatefulFiberFrame2DProblem,
    _finite,
    _readonly,
    validate_stateful_fiber_frame2d_checkpoint,
)
from .stateful_fiber_frame2d_state import StatefulFiberFrame2DCheckpoint
from structural_analysis.elements.stateful_fiber_beam2d_state import (
    StatefulFiberBeam2DState,
)


# A small exact tuple can keep the original conversion without inspecting the
# mutable matrix or invoking caller-provided length/type hooks.
_BUILTIN_TYPE = type
_BUILTIN_TUPLE = tuple
_TUPLE_LENGTH = tuple.__len__
_BUILTIN_VARS = vars
_BUILTIN_ALL = all
_BUILTIN_ANY = any
_BUILTIN_ID = id
_BUILTIN_FROZENSET = frozenset
_BUILTIN_LEN = len
_BUILTIN_STR = str
_BUILTIN_BOOL = bool
_BUILTIN_INT = int
_BUILTIN_BYTES = bytes
_BUILTIN_FLOAT = float
_BUILTIN_LIST = list
_BUILTIN_DICT = dict
_BUILTIN_SET = set
_BUILTIN_OBJECT = object
_BUILTIN_PROPERTY = property
_BUILTIN_STATICMETHOD = staticmethod
_BUILTIN_CLASSMETHOD = classmethod
_BUILTIN_EXCEPTION = Exception
_BOUNDARY_ABSENT = object()
_LEGACY_ROW_MIN_FREE_DOFS = 64


# These small boundary descriptions do not walk the numerical implementation.
# Unknown defaults/closures are rejected without reading foreign metadata.
class _BoundaryUnsupported(TypeError):
    pass


def _known_numpy_boundary_defaults() -> tuple:
    initializer = np.errstate.__init__
    if _BUILTIN_TYPE(initializer) is FunctionType:
        defaults = initializer.__kwdefaults__
        if _BUILTIN_TYPE(defaults) is _BUILTIN_DICT and "call" in defaults:
            return (defaults["call"],)
    return ()


_BOUNDARY_EXPECTED_IDENTITIES = _known_numpy_boundary_defaults()


def _boundary_value(value: Any, depth: int = 0) -> tuple:
    if depth > 12:
        raise _BoundaryUnsupported
    kind = _BUILTIN_TYPE(value)
    if value is None or (
        kind is _BUILTIN_STR
        or kind is _BUILTIN_BOOL
        or kind is _BUILTIN_INT
        or kind is _BUILTIN_BYTES
    ):
        return (kind, value)
    if _BUILTIN_ANY(value is expected for expected in _BOUNDARY_EXPECTED_IDENTITIES):
        return ("expected identity", _BUILTIN_ID(value))
    if kind is _BUILTIN_FLOAT:
        return (_BUILTIN_FLOAT, value.hex())
    if kind is _BUILTIN_TUPLE or kind is _BUILTIN_LIST:
        return (
            kind,
            _BUILTIN_TUPLE(_boundary_value(item, depth + 1) for item in value),
        )
    if kind is _BUILTIN_DICT:
        return (
            _BUILTIN_DICT,
            _BUILTIN_TUPLE(
                (_boundary_value(key, depth + 1), _boundary_value(item, depth + 1))
                for key, item in value.items()
            ),
        )
    if kind is _BUILTIN_SET or kind is _BUILTIN_FROZENSET:
        return (
            kind,
            _BUILTIN_FROZENSET(_boundary_value(item, depth + 1) for item in value),
        )
    if kind is FunctionType:
        return ("function", _BUILTIN_ID(value), _BUILTIN_ID(value.__code__))
    if kind is _BUILTIN_TYPE or kind is _BUILTIN_OBJECT:
        return ("identity", _BUILTIN_ID(value))
    if kind is BuiltinFunctionType and (
        value is _BUILTIN_LEN or value is _BUILTIN_TUPLE.__new__
    ):
        return ("builtin", _BUILTIN_ID(value))
    raise _BoundaryUnsupported


def _boundary_function_token(function: Any) -> tuple:
    # Function slots and an exact function's dictionary cannot invoke caller
    # descriptors. In particular, do not inspect an unknown default's class.
    namespace = _BUILTIN_VARS(function)
    if _BUILTIN_TYPE(namespace) is not _BUILTIN_DICT:
        raise _BoundaryUnsupported
    wrapped = namespace.get("__wrapped__", function)
    if _BUILTIN_TYPE(wrapped) is not FunctionType:
        raise _BoundaryUnsupported
    return _BUILTIN_TUPLE(
        (
            _BUILTIN_ID(fn),
            _BUILTIN_ID(fn.__code__),
            _boundary_value(fn.__defaults__),
            _boundary_value(fn.__kwdefaults__),
            _BUILTIN_TUPLE(
                _boundary_value(cell.cell_contents) for cell in fn.__closure__ or ()
            ),
        )
        for fn in (function, wrapped)
    )


def _boundary_binding(owner: Any, name: str) -> Any:
    if _BUILTIN_TYPE(owner) is _BUILTIN_DICT:
        return owner.get(name, _BOUNDARY_ABSENT)
    if _BUILTIN_TYPE(owner) is _BUILTIN_TYPE:
        for cls in owner.__mro__:
            namespace = _BUILTIN_VARS(cls)
            if name in namespace:
                return namespace[name]
        return _BOUNDARY_ABSENT
    raise _BoundaryUnsupported("unsupported conversion boundary owner")


def _boundary_token(value: Any) -> tuple:
    kind = _BUILTIN_TYPE(value)
    if kind is _BUILTIN_PROPERTY:
        return _BUILTIN_TUPLE(
            _boundary_token(fn) if fn is not None else None
            for fn in (value.fget, value.fset, value.fdel)
        )
    if kind is _BUILTIN_STATICMETHOD or kind is _BUILTIN_CLASSMETHOD:
        return _boundary_token(value.__func__)
    if kind is FunctionType:
        return _boundary_function_token(value)
    # Non-Python implementations are bound by identity. Mutable Python methods
    # used through classes/properties are described separately above.
    return ("identity", _BUILTIN_ID(value))


def _capture_boundary_bindings(bindings: tuple[tuple[Any, str], ...]) -> tuple | None:
    try:
        return _BUILTIN_TUPLE(
            (owner, name, value, _boundary_token(value))
            for owner, name in bindings
            for value in (_boundary_binding(owner, name),)
        )
    except _BUILTIN_EXCEPTION:
        # Another supported dependency layout retains its existing path.
        return None


def _boundary_bindings_unchanged(bindings: tuple | None) -> bool:
    if bindings is None:
        return False
    try:
        return _BUILTIN_ALL(
            _boundary_binding(owner, name) is value and _boundary_token(value) == token
            for owner, name, value, token in bindings
        )
    except _BUILTIN_EXCEPTION:
        return False


def _function_builtin_bindings(functions: tuple, names: tuple[str, ...]) -> tuple:
    """Bind each actual function builtin dictionary once, without caller hooks."""
    try:
        owners = {}
        for function in functions:
            if _BUILTIN_TYPE(function) is not FunctionType:
                raise _BoundaryUnsupported
            namespace = function.__builtins__
            if _BUILTIN_TYPE(namespace) is not _BUILTIN_DICT:
                raise _BoundaryUnsupported
            owners[_BUILTIN_ID(namespace)] = namespace
        return _BUILTIN_TUPLE(
            (owner, name) for owner in owners.values() for name in names
        )
    except _BUILTIN_EXCEPTION:
        # The common capture routine makes this unsupported owner ineligible.
        return ((None, "unsupported function builtins"),)


class _SparseLegacyRows:
    """Private transient tolist adapter; only ordinary rows escape."""

    def __init__(self, matrix: csr_matrix) -> None:
        self.matrix = matrix

    def tolist(self) -> list[list[float]]:
        matrix = self.matrix
        rows = []
        for row in range(matrix.shape[0]):
            buffer = np.zeros(matrix.shape[1], dtype=np.float64)
            for position in range(matrix.indptr[row], matrix.indptr[row + 1]):
                column = matrix.indices[position]
                # Match csr_todense's +0 initialization and stored-order addition.
                buffer[column] += matrix.data[position]
            rows.append(buffer.tolist())
        return rows


def _sparse_legacy_rows_eligible(matrix: Any) -> bool:
    if _BUILTIN_TYPE(matrix) is not csr_matrix or not _boundary_bindings_unchanged(
        _SPARSE_LEGACY_BOUNDARIES
    ):
        return False
    try:
        namespace = vars(matrix)
        if any(
            name in namespace
            for name in ("toarray", "_swap", "_process_toarray_args", "tocsr")
        ):
            return False
        shape = matrix.shape
        if (
            type(shape) is not tuple
            or len(shape) != 2
            or any(type(size) is not int or size < 0 for size in shape)
            or shape[0] != shape[1]
        ):
            return False
        data, indices, indptr = matrix.data, matrix.indices, matrix.indptr
        if any(type(array) is not np.ndarray for array in (data, indices, indptr)):
            return False
        if (
            data.dtype.str != "<f8"
            or indices.dtype.str not in ("<i4", "<i8")
            or indptr.dtype.str != indices.dtype.str
            or any(
                array.ndim != 1
                or not array.flags.c_contiguous
                or not array.flags.aligned
                for array in (data, indices, indptr)
            )
            or indptr.size != shape[0] + 1
            or indices.size != data.size
            or int(indptr[0]) != 0
            or int(indptr[-1]) != data.size
            or not np.all(np.isfinite(data))
        ):
            return False
        previous = 0
        for row in range(shape[0]):
            end = int(indptr[row + 1])
            if not previous <= end <= data.size:
                return False
            last = -1
            for column in indices[previous:end]:
                current = int(column)
                if not last < current < shape[1]:
                    return False
                last = current
            previous = end
        return True
    except Exception:
        return False


class _TopologyPlan(NamedTuple):
    indptr: tuple[int, ...]
    indices: tuple[int, ...]
    data_rows: tuple[int, ...]
    # Per member: unique CSR positions and their corresponding 6x6 local slots.
    members: tuple[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]], ...]


@lru_cache(maxsize=64)
def _topology_plan(
    global_count: int,
    free_dofs: tuple[int, ...],
    member_dofs: tuple[tuple[int, ...], ...],
) -> _TopologyPlan:
    """Cache only immutable integer topology, never a problem or physical value."""
    if len(set(free_dofs)) != len(free_dofs) or any(
        type(dof) is not int or not 0 <= dof < global_count for dof in free_dofs
    ):
        raise ValueError("direct sparse free DOF topology is invalid")
    free_index = {dof: index for index, dof in enumerate(free_dofs)}
    columns = [set() for _ in free_dofs]
    local_pairs = []
    for dofs in member_dofs:
        if (
            len(dofs) != 6
            or len(set(dofs)) != 6
            or any(type(dof) is not int or not 0 <= dof < global_count for dof in dofs)
        ):
            raise ValueError("direct sparse member DOF topology is invalid")
        active = [
            (local, free_index[dof])
            for local, dof in enumerate(dofs)
            if dof in free_index
        ]
        pairs = []
        for local_row, row in active:
            for local_column, column in active:
                columns[row].add(column)
                pairs.append((row, column, local_row, local_column))
        local_pairs.append(pairs)
    indptr, indices, data_rows = [0], [], []
    positions = {}
    for row, row_columns in enumerate(columns):
        for column in sorted(row_columns):
            positions[row, column] = len(indices)
            indices.append(column)
            data_rows.append(row)
        indptr.append(len(indices))
    groups = []
    for pairs in local_pairs:
        groups.append(
            (
                tuple(positions[row, column] for row, column, _, _ in pairs),
                tuple(local_row for _, _, local_row, _ in pairs),
                tuple(local_column for _, _, _, local_column in pairs),
            )
        )
    return _TopologyPlan(tuple(indptr), tuple(indices), tuple(data_rows), tuple(groups))


def _immutable_array(value: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(value)
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


@dataclass(frozen=True)
class DirectSparseFiberFrameTrial:
    parent_checkpoint_hash: str
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: csr_matrix
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    pattern_nnz: int
    # Bytes in the returned numeric buffers only, not peak RSS, temporaries,
    # Python objects/cache entries or cumulative allocation traffic.
    allocated_bytes: int


@dataclass(frozen=True)
class DirectSparseFiberFrameAssembly:
    parent_checkpoint_hash: str
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: csr_matrix
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    member_assemblies: tuple[StatefulFiberFrame2DMemberAssembly, ...]
    trial_element_states: tuple[StatefulFiberBeam2DState, ...]

    def to_dict(self) -> dict[str, Any]:
        # Preserve constructor argument and serializer evaluation order.
        return StatefulFiberFrame2DAssembly(
            parent_checkpoint_hash=self.parent_checkpoint_hash,
            target_load_factor=self.target_load_factor,
            free_global_dofs=(free_dofs := self.free_global_dofs),
            generalized_coordinates_m=self.generalized_coordinates_m,
            global_displacements=self.global_displacements,
            residual_kn=self.residual_kn,
            jacobian_kn_per_m=_legacy_jacobian_payload(
                self, self.jacobian_kn_per_m, free_dofs
            ),
            internal_loads_global=self.internal_loads_global,
            external_loads_global=self.external_loads_global,
            reactions_global=self.reactions_global,
            member_assemblies=self.member_assemblies,
            trial_element_states=self.trial_element_states,
        ).to_dict()


def _legacy_jacobian_payload(
    assembly: DirectSparseFiberFrameAssembly,
    matrix: csr_matrix,
    free_dofs: tuple[int, ...],
) -> np.ndarray:
    if (
        _BUILTIN_TYPE(free_dofs) is _BUILTIN_TUPLE
        and _TUPLE_LENGTH(free_dofs) < _LEGACY_ROW_MIN_FREE_DOFS
    ):
        return matrix.toarray()
    if (
        _BUILTIN_TYPE(assembly) is DirectSparseFiberFrameAssembly
        and _sparse_legacy_rows_eligible(matrix)
        and type(free_dofs) is tuple
        and all(type(dof) is int for dof in free_dofs)
        and all(
            type(array) is np.ndarray and array.dtype.str == "<f8"
            for array in (
                assembly.generalized_coordinates_m,
                assembly.global_displacements,
                assembly.residual_kn,
            )
        )
    ):
        return cast(np.ndarray, _SparseLegacyRows(matrix))
    return matrix.toarray()


def assemble_stateful_fiber_frame2d_direct_sparse(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> DirectSparseFiberFrameTrial:
    """Assemble one unchanged material trial without a global dense tangent."""
    trial, _members, _states = _assemble_direct_sparse(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
        retain_members=False,
    )
    return trial


def assemble_stateful_fiber_frame2d_direct_sparse_terminal(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> DirectSparseFiberFrameAssembly:
    """Retain the same-parent element trials required for commit and recovery."""
    trial, members, states = _assemble_direct_sparse(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
        retain_members=True,
    )
    return DirectSparseFiberFrameAssembly(
        parent_checkpoint_hash=trial.parent_checkpoint_hash,
        target_load_factor=trial.target_load_factor,
        free_global_dofs=trial.free_global_dofs,
        generalized_coordinates_m=trial.generalized_coordinates_m,
        global_displacements=trial.global_displacements,
        residual_kn=trial.residual_kn,
        jacobian_kn_per_m=trial.jacobian_kn_per_m,
        internal_loads_global=trial.internal_loads_global,
        external_loads_global=trial.external_loads_global,
        reactions_global=trial.reactions_global,
        member_assemblies=members,
        trial_element_states=states,
    )


def _assemble_direct_sparse(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
    retain_members: bool,
) -> tuple[
    DirectSparseFiberFrameTrial,
    tuple[StatefulFiberFrame2DMemberAssembly, ...],
    tuple[StatefulFiberBeam2DState, ...],
]:
    validate_stateful_fiber_frame2d_checkpoint(problem, accepted_checkpoint)
    load_factor = _finite(target_load_factor, name="target_load_factor")
    free_dofs = problem.free_global_dofs
    try:
        free = np.asarray(trial_free_coordinates_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("trial_free_coordinates_m has invalid values") from exc
    if free.shape != (len(free_dofs),) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")
    scale = problem.physical_coordinate_scale
    generalized = np.zeros(problem.global_dof_count, dtype=np.float64)
    generalized[list(free_dofs)] = free
    global_displacements = scale * generalized
    internal = np.zeros(problem.global_dof_count, dtype=np.float64)
    member_dofs = tuple(
        problem.member_global_dofs(member) for member in problem.members
    )
    plan = _topology_plan(problem.global_dof_count, free_dofs, member_dofs)
    data = np.zeros(len(plan.indices), dtype=np.float64)
    member_rows = []
    trial_states = []
    for member, parent, dofs, group in zip(
        problem.members,
        accepted_checkpoint.element_states,
        member_dofs,
        plan.members,
        strict=True,
    ):
        transformation = problem.member_transformation(member)
        local_displacements = transformation @ global_displacements[list(dofs)]
        response = member.element.integrate(local_displacements, parent)
        if response.parent_state_hash != parent.state_hash:
            raise ValueError(
                "element response parent_state_hash does not match checkpoint parent"
            )
        internal_global = transformation.T @ response.internal_force_local
        tangent_global = (
            transformation.T @ response.consistent_tangent_local @ transformation
        )
        internal[list(dofs)] += internal_global
        positions, local_rows, local_columns = group
        if positions:
            # Positions are unique within this member; member order matches dense +=.
            data[list(positions)] += tangent_global[
                list(local_rows), list(local_columns)
            ]
        if retain_members:
            member_rows.append(
                StatefulFiberFrame2DMemberAssembly(
                    member_id=member.member_id,
                    global_dofs=dofs,
                    transformation_global_to_local=_readonly(transformation),
                    internal_load_global=_readonly(internal_global),
                    consistent_tangent_global=_readonly(tangent_global),
                    response=response,
                )
            )
            trial_states.append(response.state)
    external = load_factor * problem.reference_external_load_vector()
    physical_residual = internal - external
    free_scale = scale[list(free_dofs)]
    residual = free_scale * physical_residual[list(free_dofs)]
    # Preserve dense's (row_scale * accumulated_tangent) * column_scale order.
    data = (free_scale[list(plan.data_rows)] * data) * free_scale[list(plan.indices)]
    jacobian = csr_matrix(
        (
            data,
            np.asarray(plan.indices, dtype=np.int64),
            np.asarray(plan.indptr, dtype=np.int64),
        ),
        shape=(len(free_dofs), len(free_dofs)),
        copy=False,
    )
    # Structural zeros and every tiny nonzero are retained; no dropping/elimination.
    jacobian.data = _immutable_array(jacobian.data)
    jacobian.indices = _immutable_array(jacobian.indices)
    jacobian.indptr = _immutable_array(jacobian.indptr)
    reactions = np.zeros(problem.global_dof_count, dtype=np.float64)
    reactions[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    vectors = tuple(
        _immutable_array(array)
        for array in (
            generalized,
            global_displacements,
            residual,
            internal,
            external,
            reactions,
        )
    )
    allocated_bytes = sum(array.nbytes for array in vectors) + sum(
        array.nbytes for array in (jacobian.data, jacobian.indices, jacobian.indptr)
    )
    trial = DirectSparseFiberFrameTrial(
        accepted_checkpoint.state_hash,
        load_factor,
        free_dofs,
        *vectors[:3],
        jacobian,
        *vectors[3:],
        len(plan.indices),
        allocated_bytes,
    )
    return trial, tuple(member_rows), tuple(trial_states)


__all__ = [
    "DirectSparseFiberFrameTrial",
    "assemble_stateful_fiber_frame2d_direct_sparse",
]


# Only the actual default C-order CSR.toarray path is omitted by the adapter.
# No constructor, slicing, matmul or solver implementation scan is added here.
_SPARSE_LEGACY_BOUNDARIES = _capture_boundary_bindings(
    tuple(
        (owner, name)
        for owner, names in (
            (
                globals(),
                (
                    "StatefulFiberFrame2DAssembly",
                    "csr_matrix",
                    "np",
                    "__builtins__",
                    "cast",
                    "range",
                    "int",
                    "type",
                    "vars",
                    "all",
                    "any",
                    "len",
                    "Exception",
                ),
            ),
            (StatefulFiberFrame2DAssembly.to_dict.__globals__, ("list",)),
            (StatefulFiberFrame2DAssembly.to_dict.__builtins__, ("list",)),
            (
                StatefulFiberFrame2DAssembly,
                (
                    "__new__",
                    "__init__",
                    "__getattribute__",
                    "__getattr__",
                    "__setattr__",
                    "__post_init__",
                    "to_dict",
                    *StatefulFiberFrame2DAssembly.__dataclass_fields__,
                ),
            ),
            (
                DirectSparseFiberFrameAssembly,
                (
                    "__getattribute__",
                    "__getattr__",
                    *DirectSparseFiberFrameAssembly.__dataclass_fields__,
                ),
            ),
            (
                csr_matrix,
                (
                    "__getattribute__",
                    "__getattr__",
                    "toarray",
                    "_swap",
                    "_process_toarray_args",
                    "tocsr",
                    "shape",
                    "dtype",
                    "data",
                    "indices",
                    "indptr",
                    "_shape",
                ),
            ),
            (csr_matrix.toarray.__globals__, ("csr_todense",)),
            (csr_matrix._process_toarray_args.__globals__, ("np",)),
            (vars(np), ("zeros", "float64", "ndarray", "all", "isfinite")),
        )
        for name in names
    )
    + _function_builtin_bindings(
        (
            _SparseLegacyRows.tolist,
            _sparse_legacy_rows_eligible,
            _legacy_jacobian_payload,
        ),
        ("range", "int", "type", "vars", "all", "any", "len", "Exception"),
    )
)
