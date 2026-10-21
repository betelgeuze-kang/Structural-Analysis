"""Private, bounded invocation ownership for successful Jacobian scalar receipts.

No problem, checkpoint, array, diagnostic matrix, or returned receipt is retained.
The caller supplies fresh typed value/byte snapshots and rechecks them before
publication. Source-owned implementations must still match their import baseline.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
import math
import struct
import sys
import threading
from types import BuiltinFunctionType, FunctionType, MappingProxyType, ModuleType
from typing import Any, Iterator

import numpy as np
from scipy import sparse as _scipy_sparse
from scipy.sparse import csr_matrix as _CSR_MATRIX


class _Ineligible(TypeError):
    pass


def value_snapshot(value: Any, classes: frozenset[type], remaining: list[int]) -> tuple:
    """Copy exact current values; preserve types, order, and signed float bits."""
    remaining[0] -= 1
    if remaining[0] < 0:
        raise _Ineligible
    kind = type(value)
    result: tuple[Any, ...]
    if value is None or kind in (bool, int, str, bytes):
        if kind in (str, bytes):
            remaining[1] -= len(value)
        result = (kind.__name__, value)
    elif kind is float:
        if not math.isfinite(value):
            raise _Ineligible
        result = ("float64", struct.pack("<d", value))
    elif kind in (tuple, list):
        result = (
            kind.__name__,
            tuple(value_snapshot(item, classes, remaining) for item in value),
        )
    elif kind in (dict, MappingProxyType):
        if any(type(key) is not str for key in value):
            raise _Ineligible
        result = (
            kind.__name__,
            tuple(
                (key, value_snapshot(item, classes, remaining))
                for key, item in value.items()
            ),
        )
    elif kind is np.ndarray:
        if (
            value.dtype.hasobject
            or value.dtype.kind not in "biuf"
            or not value.flags.c_contiguous
        ):
            raise _Ineligible
        if value.dtype.kind == "f" and not np.all(np.isfinite(value)):
            raise _Ineligible
        data = value.tobytes(order="C")
        remaining[1] -= len(data)
        result = ("ndarray", value.dtype.str, value.shape, value.strides, data)
    elif kind in classes and is_dataclass(value):
        names = tuple(item.name for item in fields(value))
        if set(vars(value)) != set(names):
            # Instance-level method shadowing and undeclared state stay uncached.
            raise _Ineligible
        result = (
            kind.__module__,
            kind.__qualname__,
            tuple(
                (name, value_snapshot(getattr(value, name), classes, remaining))
                for name in names
            ),
        )
    else:
        raise _Ineligible
    if remaining[1] < 0:
        raise _Ineligible
    return result


def _guard_value(value: Any, depth: int = 0) -> tuple:
    if depth > 12:
        raise _Ineligible
    kind = type(value)
    if value is None or kind in (str, bool, int, bytes):
        return (kind.__name__, value)
    if kind is float:
        return ("float", struct.pack("<d", value))
    if kind in (tuple, list):
        return (kind.__name__, tuple(_guard_value(item, depth + 1) for item in value))
    if kind in (set, frozenset):
        return (
            kind.__name__,
            frozenset(_guard_value(item, depth + 1) for item in value),
        )
    if kind in (dict, MappingProxyType):
        return (
            kind.__name__,
            tuple(
                (_guard_value(key, depth + 1), _guard_value(item, depth + 1))
                for key, item in value.items()
            ),
        )
    if isinstance(value, type) or kind is FunctionType or kind is object:
        return ("implementation", id(value), id(getattr(value, "__code__", None)))
    if kind is BuiltinFunctionType:
        target = getattr(value, "__self__", None)
        if value is len or value is tuple.__new__:
            # NamedTuple-generated methods close over len and tuple.__new__.
            # A bound mutable-instance builtin (for example list.append) is not
            # an immutable implementation and deliberately remains ineligible.
            return ("builtin_implementation", id(value), id(target))
    if kind.__module__ in ("dataclasses", "numpy._globals"):
        namespace = getattr(value, "__dict__", None)
        if type(namespace) is dict and not namespace:
            return ("default_sentinel", id(value))
    raise _Ineligible(
        f"unsupported implementation closure/default: {kind.__module__}.{kind.__qualname__}"
    )


def _function_token(function: Any) -> tuple:
    wrapped = getattr(function, "__wrapped__", function)
    if type(wrapped) is not FunctionType:
        return (id(function),)
    return (
        id(function),
        id(getattr(function, "__code__", None)),
        id(wrapped),
        id(wrapped.__code__),
        _guard_value(wrapped.__defaults__),
        _guard_value(wrapped.__kwdefaults__),
        _guard_value(getattr(function, "__defaults__", None)),
        _guard_value(getattr(function, "__kwdefaults__", None)),
        tuple(_guard_value(cell.cell_contents) for cell in wrapped.__closure__ or ()),
        tuple(
            _guard_value(cell.cell_contents)
            for cell in getattr(function, "__closure__", ()) or ()
        ),
    )


_CSR_NUMPY_ATTRIBUTES = (
    "array",
    "asarray",
    "bincount",
    "can_cast",
    "diff",
    "iinfo",
    "int32",
    "int64",
    "intc",
    "integer",
    "issubdtype",
    "ndarray",
    "zeros",
)


def _csr_numpy_binding_tokens(functions: tuple[Any, ...]) -> tuple:
    bindings = []
    namespaces = {}
    for function in functions:
        namespace = getattr(function, "__globals__", {})
        if "np" not in namespace:
            continue
        numpy = namespace["np"]
        identity = id(numpy)
        bindings.append((id(function), identity))
        if identity not in namespaces:
            namespaces[identity] = tuple(
                (name, _function_token(getattr(numpy, name)))
                for name in _CSR_NUMPY_ATTRIBUTES
            )
    return tuple(bindings), tuple(namespaces.items())


def _csr_implementation_tokens() -> tuple | None:
    """Bound the CSR construction/toarray path without scanning all of SciPy.

    Private-layout differences make reuse ineligible, never break the original
    numerical API. Resolved methods include inherited implementations, and the
    actual constructor/toarray globals bind their directly used helper/backend
    aliases. Generic sparse slicing/multiplication are not new solver paths.
    """
    try:
        constructor = _CSR_MATRIX.__init__
        namespace = constructor.__globals__
        data_class = namespace["_data_matrix"]
        base_class = data_class.__init__.__globals__["_spbase"]
        sputils = sys.modules["scipy.sparse._sputils"]
        index_type = _CSR_MATRIX._get_index_dtype
        shape_check = namespace["check_shape"]
        numerical_functions = (
            *(
                getattr(_CSR_MATRIX, name)
                for name in (
                    "__new__",
                    "__init__",
                    "check_format",
                    "prune",
                    "_get_index_dtype",
                    "_getnnz",
                    "_swap",
                    "toarray",
                    "_process_toarray_args",
                    "tocsr",
                )
            ),
            *(getattr(_CSR_MATRIX, name).fget for name in ("shape", "dtype", "nnz")),
            data_class.__init__,
            base_class.__init__,
            *(
                namespace[name]
                for name in ("issparse", "isshape", "check_shape", "_prune_array")
            ),
            sputils.get_index_dtype,
            sputils.check_shape,
        )
        return (
            id(_scipy_sparse.csr_matrix),
            id(_CSR_MATRIX),
            _CSR_MATRIX.__name__,
            tuple(id(cls) for cls in _CSR_MATRIX.__mro__),
            tuple(
                (name, _function_token(getattr(_CSR_MATRIX, name, None)))
                for name in (
                    "__new__",
                    "__init__",
                    "check_format",
                    "prune",
                    "_get_index_dtype",
                    "_getnnz",
                    "_swap",
                    "toarray",
                    "_process_toarray_args",
                    "tocsr",
                    "__getitem__",
                    "__matmul__",
                    "_mul_dispatch",
                    "_mul_vector",
                    "_matmul_dispatch",
                    "_matmul_vector",
                )
            ),
            tuple(
                (name, _function_token(getattr(_CSR_MATRIX, name).fget))
                for name in ("shape", "dtype", "nnz")
            ),
            (id(data_class), _function_token(data_class.__init__)),
            (id(base_class), _function_token(base_class.__init__)),
            tuple(
                (name, _function_token(namespace[name]))
                for name in (
                    "issparse",
                    "isshape",
                    "check_shape",
                    "_prune_array",
                    "csr_todense",
                )
            ),
            id(namespace["np"]),
            id(namespace["issparse"].__globals__["_spbase"]),
            id(index_type.__globals__["sparray"]),
            id(sputils),
            id(getattr(_scipy_sparse, "_sputils", None)),
            id(sputils.np),
            _function_token(sputils.get_index_dtype),
            _function_token(sputils.check_shape),
            id(shape_check.__globals__["operator"]),
            _function_token(shape_check.__globals__["operator"].index),
            _csr_numpy_binding_tokens(numerical_functions),
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        return None


class ImplementationGuard:
    """Conservative admission for exact source-owned functions/classes only."""

    def __init__(self, modules: tuple[ModuleType, ...]) -> None:
        self.modules = modules
        self.classes = frozenset(
            value
            for module in modules
            for value in vars(module).values()
            if isinstance(value, type)
            and value.__module__.startswith("structural_analysis.")
        )
        self.baseline = self._current()

    def _current(self) -> tuple:
        result = []
        function_tokens: dict[int, tuple] = {}
        class_tokens: dict[int, tuple] = {}

        def function_token(value: Any) -> tuple:
            identity = id(value)
            if identity not in function_tokens:
                function_tokens[identity] = _function_token(value)
            return function_tokens[identity]

        for module in self.modules:
            entries: list[tuple[Any, ...]] = []
            for name, value in vars(module).copy().items():
                if name in ("_AUDIT_IMPLEMENTATION", "_PURE_SCHEMA_VALIDATORS"):
                    # Self-registration and successful structural-schema memo
                    # bookkeeping are not numerical-audit implementations.
                    continue
                owner = getattr(value, "__module__", "")
                if (
                    callable(value)
                    and isinstance(owner, str)
                    and owner.startswith("structural_analysis.")
                ):
                    if isinstance(value, type):
                        if id(value) not in class_tokens:
                            members = []
                            for member_name, member in vars(value).copy().items():
                                if isinstance(member, (staticmethod, classmethod)):
                                    member = member.__func__
                                if isinstance(member, property):
                                    members.append(
                                        (
                                            member_name,
                                            tuple(
                                                function_token(fn)
                                                if fn is not None
                                                else None
                                                for fn in (
                                                    member.fget,
                                                    member.fset,
                                                    member.fdel,
                                                )
                                            ),
                                        )
                                    )
                                elif callable(member):
                                    members.append(
                                        (member_name, function_token(member))
                                    )
                            class_tokens[id(value)] = tuple(members)
                        entries.append((name, id(value), class_tokens[id(value)]))
                    else:
                        entries.append((name, function_token(value)))
                elif callable(value):
                    entries.append((name, "external_alias", function_token(value)))
                elif isinstance(value, ModuleType):
                    entries.append((name, "module_binding", id(value)))
                elif name.isupper():
                    try:
                        token = _guard_value(value)
                    except _Ineligible:
                        # Immutable regex/type-policy objects: identity changes disable reuse.
                        token = ("constant_object", id(value))
                    entries.append((name, token))
            result.append((id(module), tuple(entries)))
        external = (
            tuple(
                _function_token(getattr(np, name))
                for name in (
                    "asarray",
                    "array",
                    "ascontiguousarray",
                    "frombuffer",
                    "isfinite",
                    "all",
                    "any",
                    "arange",
                    "concatenate",
                    "can_cast",
                    "bincount",
                    "diff",
                    "dtype",
                    "zeros",
                    "ones",
                    "full",
                    "zeros_like",
                    "empty",
                    "empty_like",
                    "errstate",
                    "array_equal",
                    "allclose",
                    "isin",
                    "issubdtype",
                    "ix_",
                    "finfo",
                    "iinfo",
                    "require",
                    "shares_memory",
                    "tile",
                    "vstack",
                )
            )
            + tuple(
                _function_token(getattr(math, name))
                for name in (
                    "isfinite",
                    "fsum",
                    "isclose",
                    "sqrt",
                    "hypot",
                    "exp",
                    "expm1",
                    "log",
                    "nextafter",
                    "prod",
                    "copysign",
                )
            )
            + (
                _function_token(np.linalg.norm),
                _function_token(np.linalg.solve),
                _function_token(struct.pack),
                (
                    id(np.float64),
                    id(np.bool_),
                    id(np.int32),
                    id(np.int64),
                    id(np.intc),
                    id(np.integer),
                    id(np.floating),
                    id(np.ndarray),
                    id(np.linalg),
                    id(np.linalg.LinAlgError),
                    _guard_value(np.inf),
                    _guard_value(math.inf),
                ),
            )
        )
        return tuple(result), external, _csr_implementation_tokens()

    def unchanged(self) -> bool:
        try:
            current = self._current()
            return current[-1] is not None and current == self.baseline
        except (AttributeError, TypeError, ValueError, RecursionError):
            return False


class _Scope:
    def __init__(self, maximum: int) -> None:
        self.owner = threading.current_thread()
        self.maximum = maximum
        self.active = True
        self.busy = False
        self.entries: OrderedDict[tuple, tuple] = OrderedDict()
        self.counters = dict(hits=0, misses=0, bypasses=0, publications=0, evictions=0)

    def check(self) -> None:
        if not self.active or threading.current_thread() is not self.owner:
            raise RuntimeError(
                "Jacobian audit reuse scope is closed or belongs to another thread"
            )


_ACTIVE: ContextVar[_Scope | None] = ContextVar(
    "fiber_frame_jacobian_audit_reuse", default=None
)


@contextmanager
def reuse_fiber_frame_jacobian_audits(*, maximum: int = 16) -> Iterator[None]:
    """A fresh scope per invocation; nesting never shares successful receipts."""
    if type(maximum) is not int or not 1 <= maximum <= 64:
        raise ValueError("maximum must be an integer in [1,64]")
    scope = _Scope(maximum)
    token = _ACTIVE.set(scope)
    try:
        yield None
    finally:
        scope.active = False
        scope.entries.clear()
        _ACTIVE.reset(token)


def jacobian_audit_reuse_statistics() -> dict[str, int | bool]:
    scope = _ACTIVE.get()
    if scope is None:
        return {"active": False}
    scope.check()
    return {
        "active": True,
        **scope.counters,
        "entries": len(scope.entries),
        "maximum": scope.maximum,
    }


def scope_active() -> bool:
    scope = _ACTIVE.get()
    if scope is None:
        return False
    scope.check()
    return True


class _Lease:
    def __init__(self, scope: _Scope | None, key: tuple | None) -> None:
        self.scope, self.key = scope, key
        self.entry = None
        if scope is not None:
            if key is None:
                scope.counters["bypasses"] += 1
            elif key in scope.entries:
                scope.counters["hits"] += 1
                scope.entries.move_to_end(key)
                self.entry = scope.entries[key]
            else:
                scope.counters["misses"] += 1

    def publish(self, value: tuple) -> None:
        if self.scope is None or self.key is None:
            return
        self.scope.check()
        if type(value) is not tuple or any(
            type(item) not in (str, bool, int, float) for item in value
        ):
            raise TypeError("only immutable scalar/hash receipt fields may be retained")
        self.scope.entries[self.key] = value
        self.scope.counters["publications"] += 1
        while len(self.scope.entries) > self.scope.maximum:
            self.scope.entries.popitem(last=False)
            self.scope.counters["evictions"] += 1


@contextmanager
def audit_lease(key: tuple | None) -> Iterator[_Lease]:
    scope = _ACTIVE.get()
    if scope is None:
        yield _Lease(None, None)
        return
    scope.check()
    if scope.busy:
        raise RuntimeError("Jacobian audit reuse scope is already in use")
    scope.busy = True
    try:
        yield _Lease(scope, key)
    except BaseException:
        if key is not None:
            scope.entries.pop(key, None)
        raise
    finally:
        scope.busy = False
