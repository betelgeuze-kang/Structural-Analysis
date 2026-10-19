"""Certified sparse inertia filter with outward binary64 interval arithmetic.

Every successful count is for the original exactly symmetric binary64 CSR.
An ambiguous pivot returns Uncertain, never an invented zero. This standalone
filter has no exact fallback, modal extraction or external authority access.
The frozen exact loader/ledger gives compatible source hashes and one shared
budget across stages. Stored interval endpoints and cached 2x2 workspace are
charged; expression temporaries, Python/CSR overhead and operating-system
CPU/RSS require independent external limits. Work weights remain proxies.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any, NoReturn

from structural_analysis.solvers import sparse_inertia as _exact


INTERVAL_SPARSE_INERTIA_PROFILE = "certified_binary64_interval_sparse_congruence.v1"
_ZERO = Fraction(0)


class SparseIntervalInertiaError(_exact.SparseInertiaError):
    """Input or certified-domain refusal with charged partial statistics."""


class SparseIntervalInertiaUncertain(SparseIntervalInertiaError):
    """Finite enclosures cannot certify a pivot; no count is returned."""


class SparseIntervalInertiaBudgetExceeded(
    SparseIntervalInertiaError, _exact.SparseInertiaBudgetExceeded
):
    """Resource refusal; attempted costs are never reset or refunded."""


@dataclass(frozen=True)
class Binary64Interval:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if (
            type(self.lower) is not float
            or type(self.upper) is not float
            or not math.isfinite(self.lower)
            or not math.isfinite(self.upper)
            or self.lower > self.upper
        ):
            raise SparseIntervalInertiaError(
                "interval must have finite ordered binary64 endpoints"
            )

    @property
    def exact_zero(self) -> bool:
        return self.lower == self.upper == 0.0

    @property
    def definite_sign(self) -> int:
        return 1 if self.lower > 0 else (-1 if self.upper < 0 else 0)


_IZERO = Binary64Interval(0.0, 0.0)


class _IntervalOps:
    def __init__(self, ledger: _exact._Ledger) -> None:
        self.ledger = ledger

    def _bound(self, exact: Fraction, *, upper: bool) -> float:
        self.ledger.work()
        self.ledger.coefficient(exact)
        try:
            rounded = float(exact)
        except OverflowError as exc:
            raise SparseIntervalInertiaUncertain(
                "finite binary64 enclosure overflow"
            ) from exc
        if not math.isfinite(rounded):
            raise SparseIntervalInertiaUncertain("finite binary64 enclosure overflow")
        represented = Fraction.from_float(rounded)
        if (upper and represented < exact) or (not upper and represented > exact):
            rounded = math.nextafter(rounded, math.inf if upper else -math.inf)
        if not math.isfinite(rounded):
            raise SparseIntervalInertiaUncertain("outward binary64 endpoint overflow")
        self.ledger.coefficient(Fraction.from_float(rounded))
        return rounded

    def enclose(
        self, lower: Fraction, upper: Fraction | None = None
    ) -> Binary64Interval:
        if upper is None:
            upper = lower
        if lower > upper:
            raise SparseIntervalInertiaError("exact interval endpoints are reversed")
        return Binary64Interval(
            self._bound(lower, upper=False), self._bound(upper, upper=True)
        )

    def add(self, a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
        return self.enclose(
            self.ledger.operation(
                Fraction.from_float(a.lower), Fraction.from_float(b.lower), "add"
            ),
            self.ledger.operation(
                Fraction.from_float(a.upper), Fraction.from_float(b.upper), "add"
            ),
        )

    def subtract(self, a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
        return self.enclose(
            self.ledger.operation(
                Fraction.from_float(a.lower), Fraction.from_float(b.upper), "subtract"
            ),
            self.ledger.operation(
                Fraction.from_float(a.upper), Fraction.from_float(b.lower), "subtract"
            ),
        )

    def multiply(self, a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
        products = [
            self.ledger.operation(
                Fraction.from_float(x), Fraction.from_float(y), "multiply"
            )
            for x in (a.lower, a.upper)
            for y in (b.lower, b.upper)
        ]
        return self.enclose(min(products), max(products))

    def divide(self, a: Binary64Interval, b: Binary64Interval) -> Binary64Interval:
        if b.lower <= 0 <= b.upper:
            raise SparseIntervalInertiaUncertain("interval division includes zero")
        quotients = [
            self.ledger.operation(
                Fraction.from_float(x), Fraction.from_float(y), "divide"
            )
            for x in (a.lower, a.upper)
            for y in (b.lower, b.upper)
        ]
        return self.enclose(min(quotients), max(quotients))

    def square(self, a: Binary64Interval) -> Binary64Interval:
        values = [
            self.ledger.operation(
                Fraction.from_float(x), Fraction.from_float(x), "multiply"
            )
            for x in (a.lower, a.upper)
        ]
        return self.enclose(
            _ZERO if a.lower <= 0 <= a.upper else min(values), max(values)
        )

    def negate(self, a: Binary64Interval) -> Binary64Interval:
        self.ledger.work()
        return Binary64Interval(-a.upper, -a.lower)


class _IntervalRows:
    def __init__(self, n: int, ops: _IntervalOps) -> None:
        self.dimension = n
        self.ops = ops
        self.rows: dict[int, dict[int, Binary64Interval]] = {}

    def get(self, i: int, j: int) -> Binary64Interval:
        return self.rows.get(i, {}).get(j, _IZERO)

    def set(self, i: int, j: int, value: Binary64Interval) -> None:
        ledger = self.ops.ledger
        ledger.work()
        old = self.get(i, j)
        # Endpoint coefficient/storage charges include both ends; exact zero
        # uses the shared zero constant. Constant expression temporaries are
        # outside this retained-storage proxy, as in the exact utility.
        for before, after in zip(
            (old.lower, old.upper), (value.lower, value.upper), strict=True
        ):
            new = Fraction.from_float(after)
            ledger.coefficient(new)
            ledger.reserve(Fraction.from_float(before), new)
        if not value.exact_zero:
            self.rows.setdefault(i, {})[j] = value
        elif i in self.rows:
            self.rows[i].pop(j, None)
            if not self.rows[i]:
                del self.rows[i]

    def symmetric_set(self, i: int, j: int, value: Binary64Interval) -> None:
        self.set(i, j, value)
        if i != j:
            self.set(j, i, value)

    def remove(self, index: int) -> None:
        for other in tuple(self.rows.get(index, {})):
            self.set(index, other, _IZERO)
            if other != index:
                self.set(other, index, _IZERO)


class _IntervalWorkspace:
    def __init__(self, ops: _IntervalOps) -> None:
        self.charges = _exact._Workspace(ops.ledger)

    def keep(self, value: Binary64Interval) -> Binary64Interval:
        self.charges.keep(Fraction.from_float(value.lower))
        self.charges.keep(Fraction.from_float(value.upper))
        return value

    def release(self) -> None:
        self.charges.release()


def _from_exact_rows(source: _exact._Rows, ops: _IntervalOps) -> _IntervalRows:
    result = _IntervalRows(source.dimension, ops)
    for i, row in source.rows.items():
        for j, coefficient in row.items():
            result.set(i, j, ops.enclose(coefficient))
    return result


def _eliminate(
    matrix: _IntervalRows, *, minimum_degree_pivots: bool = False
) -> tuple[int, int, int]:
    ops = matrix.ops
    ledger = ops.ledger
    ledger.charge("inertia_call_attempts", 1, ledger.budget.maximum_inertia_calls)
    remaining = set(range(matrix.dimension))
    negative = zero = positive = 0
    while remaining:
        ledger.work(len(remaining))
        empty = next((p for p in sorted(remaining) if not matrix.rows.get(p)), None)
        if empty is not None:
            zero += 1
            ledger.values["zero_dimensions"] += 1
            remaining.remove(empty)
            continue
        if minimum_degree_pivots:
            ledger.work(len(remaining))
            # Prefer sparse, well-separated pivots before tiny ones. Every
            # selected diagonal still has a certified sign; this changes only
            # the congruence order, never a count, enclosure or budget gate.
            pivot = min(
                (p for p in remaining if matrix.get(p, p).definite_sign),
                key=lambda p: (
                    len(matrix.rows[p]),
                    -min(abs(matrix.get(p, p).lower), abs(matrix.get(p, p).upper)),
                    p,
                ),
                default=None,
            )
        else:
            pivot = next(
                (p for p in sorted(remaining) if matrix.get(p, p).definite_sign), None
            )
        if pivot is not None:
            ledger.charge("pivot_attempts", 1, ledger.budget.maximum_pivots)
            ledger.values["one_by_one_pivots"] += 1
            diagonal = matrix.get(pivot, pivot)
            negative += diagonal.definite_sign < 0
            positive += diagonal.definite_sign > 0
            neighbors = sorted(j for j in matrix.rows[pivot] if j != pivot)
            values = {j: matrix.get(pivot, j) for j in neighbors}
            for offset, i in enumerate(neighbors):
                for j in neighbors[offset:]:
                    correction = ops.divide(
                        ops.multiply(values[i], values[j]), diagonal
                    )
                    matrix.symmetric_set(
                        i, j, ops.subtract(matrix.get(i, j), correction)
                    )
            values.clear()
            matrix.remove(pivot)
            remaining.remove(pivot)
            continue
        pair = None
        for p in sorted(remaining):
            for q in sorted(j for j in matrix.rows.get(p, {}) if j > p):
                ledger.charge("pivot_attempts", 1, ledger.budget.maximum_pivots)
                a, b, c = matrix.get(p, p), matrix.get(p, q), matrix.get(q, q)
                determinant = ops.subtract(ops.multiply(a, c), ops.square(b))
                if determinant.upper < 0:
                    pair = p, q, determinant
                    break
            if pair is not None:
                break
        if pair is None:
            raise SparseIntervalInertiaUncertain(
                "no certified-sign 1x1 or negative-determinant 2x2 pivot; zero is unproved"
            )
        p, q, determinant = pair
        ledger.values["two_by_two_pivots"] += 1
        negative += 1
        positive += 1
        a, b, c = matrix.get(p, p), matrix.get(p, q), matrix.get(q, q)
        union = sorted(
            (set(matrix.rows.get(p, {})) | set(matrix.rows.get(q, {}))) - {p, q}
        )
        pairs = {i: (matrix.get(p, i), matrix.get(q, i)) for i in union}
        workspace = _IntervalWorkspace(ops)
        applied: dict[int, tuple[Binary64Interval, Binary64Interval]] = {}
        try:
            inv00 = workspace.keep(ops.divide(c, determinant))
            inv01 = workspace.keep(ops.divide(ops.negate(b), determinant))
            inv11 = workspace.keep(ops.divide(a, determinant))
            for i in union:
                applied[i] = (
                    workspace.keep(
                        ops.add(
                            ops.multiply(inv00, pairs[i][0]),
                            ops.multiply(inv01, pairs[i][1]),
                        )
                    ),
                    workspace.keep(
                        ops.add(
                            ops.multiply(inv01, pairs[i][0]),
                            ops.multiply(inv11, pairs[i][1]),
                        )
                    ),
                )
            for offset, i in enumerate(union):
                for j in union[offset:]:
                    correction = ops.add(
                        ops.multiply(pairs[i][0], applied[j][0]),
                        ops.multiply(pairs[i][1], applied[j][1]),
                    )
                    matrix.symmetric_set(
                        i, j, ops.subtract(matrix.get(i, j), correction)
                    )
        finally:
            applied.clear()
            pairs.clear()
            workspace.release()
        matrix.remove(p)
        matrix.remove(q)
        remaining.remove(p)
        remaining.remove(q)
    ledger.values["completed_inertia_calls"] += 1
    return negative, zero, positive


def _raise(error: _exact.SparseInertiaError, ledger: _exact._Ledger) -> NoReturn:
    stats = ledger.snapshot()
    if isinstance(error, SparseIntervalInertiaError):
        error.statistics = stats
        raise error
    cls = (
        SparseIntervalInertiaBudgetExceeded
        if isinstance(error, _exact.SparseInertiaBudgetExceeded)
        else SparseIntervalInertiaError
    )
    raise cls(str(error), stats) from error


def compute_sparse_interval_inertia(
    matrix: Any, *, budget: _exact.SparseInertiaBudget | None = None
) -> _exact.SparseInertiaResult:
    """Certified count or explicit uncertainty; unchanged default resource cap."""
    ledger = _exact._Ledger(_exact._budget(budget))
    try:
        exact, digest = _exact._load(matrix, ledger, "matrix")
        rows = _from_exact_rows(exact, _IntervalOps(ledger))
        exact.clear()
        counts = _eliminate(rows)
        return _exact.SparseInertiaResult(
            rows.dimension,
            *counts,
            digest,
            ledger.snapshot(),
            INTERVAL_SPARSE_INERTIA_PROFILE,
        )
    except _exact.SparseInertiaError as exc:
        _raise(exc, ledger)


def count_sparse_interval_generalized_eigenvalues(
    stiffness: Any,
    mass: Any,
    *,
    shift: float | int | Fraction,
    budget: _exact.SparseInertiaBudget | None = None,
) -> _exact.SparsePencilEigenvalueCounts:
    """Certify strict/inclusive counts for original exact K-shift*M and SPD M.

    This uses one ledger for load, mass and pencil elimination. It neither
    substitutes floating subtraction nor continues an uncertain count with a
    fresh exact budget. A future hybrid must preserve this ledger's spent
    costs and source identity with an explicit bounded continuation policy.
    Exact/certified SPD remains separate from numerical modal admission.
    """
    ledger = _exact._Ledger(_exact._budget(budget))
    try:
        if isinstance(shift, Fraction):
            t = shift
        elif type(shift) is int:
            t = Fraction(shift)
        elif type(shift) is float and math.isfinite(shift):
            t = Fraction.from_float(shift)
        else:
            raise SparseIntervalInertiaError("shift must be finite float/int/Fraction")
        ledger.coefficient(t)
        k, khash = _exact._load(stiffness, ledger, "stiffness")
        m, mhash = _exact._load(mass, ledger, "mass")
        if k.dimension != m.dimension:
            raise SparseIntervalInertiaError("stiffness and mass shapes must agree")
        ops = _IntervalOps(ledger)
        shifted = _IntervalRows(k.dimension, ops)
        for i in range(k.dimension):
            keys = set(k.rows.get(i, {})) | set(m.rows.get(i, {}))
            ledger.work(len(keys))
            for j in sorted(keys):
                if j < i:
                    continue
                exact = ledger.operation(
                    k.get(i, j),
                    ledger.operation(t, m.get(i, j), "multiply"),
                    "subtract",
                )
                shifted.symmetric_set(i, j, ops.enclose(exact))
        massrows = _from_exact_rows(m, ops)
        k.clear()
        m.clear()
        masscounts = _eliminate(massrows)
        massresult = _exact.SparseInertiaResult(
            k.dimension,
            *masscounts,
            mhash,
            ledger.snapshot(),
            INTERVAL_SPARSE_INERTIA_PROFILE,
        )
        if masscounts != (0, 0, k.dimension):
            raise SparseIntervalInertiaError("mass must be certified positive definite")
        counts = _eliminate(shifted)
        return _exact.SparsePencilEigenvalueCounts(
            k.dimension,
            t.numerator,
            t.denominator,
            *counts,
            khash,
            mhash,
            massresult,
            ledger.snapshot(),
            INTERVAL_SPARSE_INERTIA_PROFILE,
        )
    except _exact.SparseInertiaError as exc:
        _raise(exc, ledger)
