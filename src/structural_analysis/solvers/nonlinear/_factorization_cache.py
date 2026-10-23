"""Invocation-local private ownership of exact-matrix SuperLU reuse."""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import threading
from typing import Any, Iterator


@dataclass(frozen=True)
class _Entry:
    factor: Any
    inverse_one_norm: float


class _Scope:
    def __init__(self, maximum: int) -> None:
        self.owner = threading.current_thread()
        self.maximum = maximum
        self.entries: OrderedDict[tuple, _Entry] = OrderedDict()
        self.active = True
        self.busy = False
        self.counters = dict(hits=0, misses=0, publications=0, evictions=0)

    def check_owner(self) -> None:
        if not self.active:
            raise RuntimeError("sparse factorization reuse scope is closed")
        if threading.current_thread() is not self.owner:
            raise RuntimeError(
                "sparse factorization reuse scope belongs to another thread"
            )


_ACTIVE: ContextVar[_Scope | None] = ContextVar(
    "sparse_factorization_reuse", default=None
)


@contextmanager
def reuse_sparse_factorizations(*, max_entries: int = 4) -> Iterator[None]:
    """Own up to eight exact-matrix factors for this invocation/thread only.

    Yields no handle. Nested scopes are independent; exit releases all factors.
    This changes no numerical admission, condition/pivot gate or RHS verification.
    """
    if type(max_entries) is not int or not 1 <= max_entries <= 8:
        raise ValueError("max_entries must be a Python integer in [1,8]")
    scope = _Scope(max_entries)
    token = _ACTIVE.set(scope)
    try:
        yield None
    finally:
        scope.check_owner()
        if scope.busy:
            raise RuntimeError("sparse factorization reuse scope is still in use")
        scope.active = False
        scope.entries.clear()
        _ACTIVE.reset(token)


def sparse_factorization_reuse_statistics() -> dict[str, int | bool]:
    """Detached execution counters only; no factor or cache entries escape."""
    scope = _ACTIVE.get()
    if scope is None:
        return {"active": False}
    scope.check_owner()
    return {
        "active": True,
        **scope.counters,
        "entries": len(scope.entries),
        "maximum": scope.maximum,
    }


class _Lease:
    def __init__(self, scope: _Scope | None, key: tuple | None) -> None:
        self.scope, self.key = scope, key
        self.entry = None
        if scope is not None and key is not None:
            self.entry = scope.entries.get(key)
            if self.entry is None:
                scope.counters["misses"] += 1
            else:
                scope.entries.move_to_end(key)
                scope.counters["hits"] += 1

    def publish(self, factor: Any, inverse_one_norm: float) -> None:
        if self.scope is None or self.key is None or self.entry is not None:
            return
        self.scope.check_owner()
        self.scope.entries[self.key] = _Entry(factor, inverse_one_norm)
        self.scope.counters["publications"] += 1
        while len(self.scope.entries) > self.scope.maximum:
            self.scope.entries.popitem(last=False)
            self.scope.counters["evictions"] += 1


@contextmanager
def _factorization_lease(key: tuple | None) -> Iterator[_Lease]:
    scope = _ACTIVE.get()
    if scope is None:
        yield _Lease(None, None)
        return
    scope.check_owner()
    if scope.busy:
        raise RuntimeError("sparse factorization reuse scope is already in use")
    scope.busy = True
    try:
        lease = _Lease(scope, key)
        yield lease
    except BaseException:
        if key is not None:
            scope.entries.pop(key, None)
        raise
    finally:
        scope.busy = False


def _reuse_scope_active() -> bool:
    scope = _ACTIVE.get()
    if scope is None:
        return False
    scope.check_owner()
    return True
