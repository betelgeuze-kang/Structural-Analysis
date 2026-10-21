"""Bounded reuse of pure computations on fresh, type-preserving value copies.

Schema success is scoped to one public invocation. Numerical replay, source
bindings, array commitments and semantic validators still run on every call.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import math
import sys
import threading
from types import FunctionType
from typing import Any, Iterator
import weakref

from jsonschema import Draft202012Validator
from referencing.jsonschema import DRAFT202012

from ._canonical import canonical_hash


class _Uncacheable(TypeError):
    pass


def _snapshot(value: Any, remaining: list[int]) -> tuple[Any, ...]:
    remaining[0] -= 1
    if remaining[0] < 0:
        raise _Uncacheable
    kind = type(value)
    if kind is str:
        remaining[1] -= len(value)
        if remaining[1] < 0:
            raise _Uncacheable
    if value is None or kind in (str, bool, int):
        return (kind, value)
    if kind is float and math.isfinite(value):
        return (float, value.hex())
    if kind is dict and all(type(key) is str for key in value):
        return (
            dict,
            tuple(
                (_snapshot(key, remaining)[1], _snapshot(item, remaining))
                for key, item in value.items()
            ),
        )
    if kind in (tuple, list):
        return (kind, tuple(_snapshot(item, remaining) for item in value))
    raise _Uncacheable


def _restore(snapshot: tuple[Any, ...]) -> Any:
    kind, value = snapshot
    if kind is dict:
        return {key: _restore(item) for key, item in value}
    if kind in (list, tuple):
        return [_restore(item) for item in value]
    if kind is float:
        return float.fromhex(value)
    return value


@lru_cache(maxsize=256)
def _digest(snapshot: tuple[Any, ...]) -> str:
    return canonical_hash(_restore(snapshot))


def canonical_hash_cached(payload: Any) -> str:
    """Hash current plain values; custom or large inputs retain the original path."""
    try:
        key = _snapshot(payload, [2048, 65536])
    except _Uncacheable:
        return canonical_hash(payload)
    return _digest(key)


_STANDARD_KEYWORDS: tuple[Any, ...] = ()
_STANDARD_METHODS: dict[str, Any] = {}
_DEFAULT_REGISTRY: Any = None
_PURE_SCHEMA_ELIGIBILITY_AVAILABLE = False
try:
    # jsonschema's private layout is an optional optimization prerequisite.
    # A supported dependency version with another layout must still import and
    # perform its original validation instead of failing during module loading.
    _keywords = tuple(
        (name, function, function.__code__)
        for name, function in Draft202012Validator.VALIDATORS.items()
    )
    _methods = {}
    for _name in ("iter_errors", "descend", "is_type", "evolve"):
        _function = getattr(Draft202012Validator, _name)
        _methods[_name] = (
            _function.__code__,
            tuple(
                (
                    name,
                    _snapshot(cell.cell_contents, [64, 1024])
                    if name == "evolve_fields"
                    else cell.cell_contents,
                )
                for name, cell in zip(
                    _function.__code__.co_freevars,
                    _function.__closure__ or (),
                    strict=True,
                )
            ),
        )
    _default_registry = next(
        attribute.default
        for attribute in Draft202012Validator.__attrs_attrs__
        if attribute.name == "_registry"
    )
except (
    _Uncacheable,
    AttributeError,
    StopIteration,
    TypeError,
    ValueError,
    RecursionError,
):
    pass
else:
    _STANDARD_KEYWORDS = _keywords
    _STANDARD_METHODS = _methods
    _DEFAULT_REGISTRY = _default_registry
    _PURE_SCHEMA_ELIGIBILITY_AVAILABLE = True
_PURE_SCHEMA_VALIDATORS: dict[int, dict[str, Any]] = {}
_PURE_SCHEMA_LOCK = threading.Lock()


def _external_reference(value: Any) -> bool:
    if type(value) is dict:
        return any(
            (
                name in ("$ref", "$dynamicRef")
                and (type(item) is not str or not item.startswith("#"))
            )
            or _external_reference(item)
            for name, item in value.items()
        )
    return type(value) in (list, tuple) and any(
        _external_reference(item) for item in value
    )


def _known_validator_class(validator: Any) -> bool:
    # Only these private, source-owned factories may opt into schema reuse.
    # Looking up already loaded modules avoids imports during a circular load.
    if not _PURE_SCHEMA_ELIGIBILITY_AVAILABLE:
        return False
    for name in ("equation_scaling", "execution_plan"):
        module = sys.modules.get(f"structural_analysis.engine_v2.contracts.{name}")
        if (
            module is not None
            and type(validator) is getattr(module, "_StrictDraft202012Validator", None)
            and validator.TYPE_CHECKER
            is getattr(module, "_STRICT_JSON_TYPE_CHECKER", None)
        ):
            return True
    return False


def _keyword_configuration(validator: Any) -> tuple[Any, ...]:
    if len(validator.VALIDATORS) != len(_STANDARD_KEYWORDS):
        raise _Uncacheable
    for name, function, code in _STANDARD_KEYWORDS:
        if (
            validator.VALIDATORS.get(name) is not function
            or function.__code__ is not code
        ):
            raise _Uncacheable
    return tuple(validator.VALIDATORS.items())


def _method_configuration(validator: Any) -> tuple[Any, ...]:
    result = []
    for name, (code, expected_closure) in _STANDARD_METHODS.items():
        method = getattr(validator, name)
        function = getattr(method, "__func__", method)
        if type(function) is not FunctionType or function.__code__ is not code:
            raise _Uncacheable
        closure = tuple(cell.cell_contents for cell in function.__closure__ or ())
        if len(closure) != len(expected_closure):
            raise _Uncacheable
        copied = []
        for current, (closure_name, expected) in zip(
            closure, expected_closure, strict=True
        ):
            if closure_name == "evolve_fields":
                current = _snapshot(current, [64, 1024])
                if current != expected:
                    raise _Uncacheable
                copied.append(current)
            elif current is not expected:
                raise _Uncacheable
        result.append((function, code, tuple(copied)))
    return tuple(result)


def _actual_validator_configuration(validator: Any) -> tuple[Any, ...]:
    if type(validator._validators) is not list:
        raise _Uncacheable
    remaining = [4096, 65536]
    result = []
    for row in validator._validators:
        if type(row) is not tuple or len(row) != 3:
            raise _Uncacheable
        function, name, value = row
        if type(name) is not str or validator.VALIDATORS.get(name) is not function:
            raise _Uncacheable
        result.append((function, name, _snapshot(value, remaining)))
    return tuple(result)


def _registry_configuration(registry: Any) -> tuple[Any, ...]:
    return tuple(
        getattr(registry, name)
        for name in ("_resources", "_anchors", "_uncrawled", "_retrieve")
    )


def _checker_configuration(checker: Any) -> tuple[Any, ...]:
    method = getattr(checker.is_type, "__func__", checker.is_type)
    return (
        method,
        getattr(method, "__code__", None),
        tuple(
            (name, function, getattr(function, "__code__", None))
            for name, function in checker._type_checkers.items()
        ),
    )


def _register_pure_schema_validator(validator: Any) -> bool:
    """Admit only an unchanged source-owned factory's default pure validator.

    Arbitrary validators, keyword closures, registries, resolvers and format
    checkers never gain eligibility merely by supplying matching JSON values.
    Registration holds a weak reference, so IDs cannot be borrowed after GC.
    """
    if not _known_validator_class(validator):
        return False
    try:
        if (
            validator.format_checker is not None
            or validator._ref_resolver is not None
            or validator._registry is not _DEFAULT_REGISTRY
            or _external_reference(validator.schema)
        ):
            return False
        schema = _snapshot(validator.schema, [4096, 65536])
        keywords = _keyword_configuration(validator)
        methods = _method_configuration(validator)
        actual = _actual_validator_configuration(validator)
        expected_actual = (
            ()
            if type(validator.schema) is bool
            else tuple(
                (validator.VALIDATORS[name], name, _snapshot(value, [4096, 65536]))
                for name, value in validator.schema.items()
                if name in validator.VALIDATORS
            )
        )
        if actual != expected_actual:
            return False
        expected_resolver = _DEFAULT_REGISTRY.resolver_with_root(
            DRAFT202012.create_resource(validator.schema)
        )
        resolver = validator._resolver
        if (
            type(resolver) is not type(expected_resolver)
            or resolver != expected_resolver
        ):
            return False
        identity = id(validator)

        def forget(reference: Any) -> None:
            with _PURE_SCHEMA_LOCK:
                saved = _PURE_SCHEMA_VALIDATORS.get(identity)
                if saved is not None and saved["reference"] is reference:
                    _PURE_SCHEMA_VALIDATORS.pop(identity, None)

        reference = weakref.ref(validator, forget)
        registration = {
            "reference": reference,
            "token": object(),
            "type": type(validator),
            "schema": schema,
            "keywords": keywords,
            "methods": methods,
            "actual": actual,
            "checker": validator.TYPE_CHECKER,
            "checker_map": validator.TYPE_CHECKER._type_checkers,
            "checker_configuration": _checker_configuration(validator.TYPE_CHECKER),
            "default_registry_configuration": _registry_configuration(
                _DEFAULT_REGISTRY
            ),
            "resolver": resolver,
            "resolver_registry": resolver._registry,
            "resolver_registry_configuration": _registry_configuration(
                resolver._registry
            ),
            "resolver_base_uri": resolver._base_uri,
            "resolver_previous": resolver._previous,
        }
    except (_Uncacheable, AttributeError, TypeError, ValueError, RecursionError):
        return False
    with _PURE_SCHEMA_LOCK:
        _PURE_SCHEMA_VALIDATORS[identity] = registration
    return True


def _registered_schema_key(validator: Any) -> tuple[Any, ...] | None:
    with _PURE_SCHEMA_LOCK:
        registration = _PURE_SCHEMA_VALIDATORS.get(id(validator))
    if registration is None or registration["reference"]() is not validator:
        return None
    if (
        type(validator) is not registration["type"]
        or validator.format_checker is not None
        or validator._ref_resolver is not None
        or validator._registry is not _DEFAULT_REGISTRY
        or validator.TYPE_CHECKER is not registration["checker"]
        or validator.TYPE_CHECKER._type_checkers is not registration["checker_map"]
        or _checker_configuration(validator.TYPE_CHECKER)
        != registration["checker_configuration"]
        or validator._resolver is not registration["resolver"]
        or validator._resolver._registry is not registration["resolver_registry"]
        or validator._resolver._base_uri != registration["resolver_base_uri"]
        or validator._resolver._previous is not registration["resolver_previous"]
        or any(
            current is not original
            for current, original in zip(
                _registry_configuration(validator._resolver._registry),
                registration["resolver_registry_configuration"],
                strict=True,
            )
        )
        or any(
            current is not original
            for current, original in zip(
                _registry_configuration(_DEFAULT_REGISTRY),
                registration["default_registry_configuration"],
                strict=True,
            )
        )
    ):
        return None
    schema = _snapshot(validator.schema, [4096, 65536])
    if (
        schema != registration["schema"]
        or _keyword_configuration(validator) != registration["keywords"]
        or _method_configuration(validator) != registration["methods"]
        or _actual_validator_configuration(validator) != registration["actual"]
    ):
        return None
    return (id(validator), registration["token"], schema)


class _SchemaMemo:
    def __init__(self) -> None:
        self.owner = threading.get_ident()
        self.successes: OrderedDict[tuple[Any, ...], None] = OrderedDict()


_SCHEMA_MEMO: ContextVar[_SchemaMemo | None] = ContextVar(
    "schema_value_memo", default=None
)


@contextmanager
def reuse_contract_computations() -> Iterator[None]:
    """Create a fresh admission scope, never carrying schema success between runs."""
    token = _SCHEMA_MEMO.set(_SchemaMemo())
    try:
        yield
    finally:
        _SCHEMA_MEMO.reset(token)


def schema_errors(validator: Any, payload: Any) -> list[Any]:
    """Reuse only successful structural checks of exactly the same plain values.

    The schema and its validator/type-checker implementations are part of the key.
    Format checking and external references stay on the uncached path. Invalid
    values are never memoized; callers retain original error ordering and paths.
    """
    memo = _SCHEMA_MEMO.get()
    key = None
    if memo is not None and memo.owner == threading.get_ident():
        try:
            schema_key = _registered_schema_key(validator)
            if schema_key is not None:
                key = (schema_key, _snapshot(payload, [4096, 65536]))
                hash(key)
                if key in memo.successes:
                    memo.successes.move_to_end(key)
                    return []
        except (_Uncacheable, AttributeError, TypeError, ValueError, RecursionError):
            key = None
    errors = list(validator.iter_errors(payload))
    if not errors and key is not None and memo is not None:
        memo.successes[key] = None
        if len(memo.successes) > 64:
            memo.successes.popitem(last=False)
    return errors
