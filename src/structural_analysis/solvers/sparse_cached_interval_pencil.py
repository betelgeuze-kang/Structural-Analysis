"""Standalone source-bound interval counts with one live cumulative ledger.

Private exact originals and their mass proof are retained for one immutable
CSR pair. No certificate/public solver is connected here. Query statistics
are additive deltas (the first includes construction); cumulative statistics
and custody are separate. Uncertain work stays spent. A budget refusal seals
the session. Retained coefficient storage includes originals, interval rows
and workspace; CSR snapshots, Python containers, arithmetic temporaries and
exception/runtime overhead require independent OS limits, not this proxy.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from fractions import Fraction
import math
from typing import Any, NoReturn

from scipy.sparse import issparse

from structural_analysis.solvers import sparse_inertia as _exact
from structural_analysis.solvers import sparse_interval_inertia as _interval


CACHED_INTERVAL_PENCIL_PROFILE = "cached_source_bound_interval_pencil.v1"
_ZERO = Fraction(0)
_ADDITIVE = (
    "input_entries",
    "work_units",
    "fraction_operation_attempts",
    "bit_operation_cost",
    "pivot_attempts",
    "one_by_one_pivots",
    "two_by_two_pivots",
    "zero_dimensions",
    "inertia_call_attempts",
    "completed_inertia_calls",
)
_AGGREGATE = {
    "maximum_input_entries": "maximum_aggregate_input_entries",
    "maximum_work_units": "maximum_aggregate_work_units",
    "maximum_bit_operation_cost": "maximum_aggregate_bit_operation_cost",
    "maximum_pivots": "maximum_aggregate_pivots",
    "maximum_inertia_calls": "maximum_aggregate_inertia_calls",
}
_COUNTER = {
    "maximum_input_entries": "input_entries",
    "maximum_work_units": "work_units",
    "maximum_bit_operation_cost": "bit_operation_cost",
    "maximum_pivots": "pivot_attempts",
    "maximum_inertia_calls": "inertia_call_attempts",
}


@dataclass(frozen=True)
class SparseCachedIntervalPencilBudget:
    provider_budget: _exact.SparseInertiaBudget = field(
        default_factory=_exact.SparseInertiaBudget
    )
    maximum_provider_calls: int = 256
    maximum_aggregate_input_entries: int = 10_000_000
    maximum_aggregate_work_units: int = 100_000_000
    maximum_aggregate_bit_operation_cost: int = 64_000_000_000
    maximum_aggregate_pivots: int = 1_000_000
    maximum_aggregate_inertia_calls: int = 512

    def __post_init__(self) -> None:
        if not isinstance(self.provider_budget, _exact.SparseInertiaBudget):
            raise ValueError("provider_budget must be SparseInertiaBudget")
        defaults = _exact.SparseInertiaBudget()
        for item in fields(defaults):
            if getattr(self.provider_budget, item.name) > getattr(defaults, item.name):
                raise ValueError("cached prototype cannot raise default provider caps")
        maxima = (256, 10_000_000, 100_000_000, 64_000_000_000, 1_000_000, 512)
        names = [item.name for item in fields(self) if item.name != "provider_budget"]
        for name, maximum in zip(names, maxima, strict=True):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError(f"{name} must be positive and at most {maximum}")


@dataclass(frozen=True)
class SparseCachedIntervalPencilStatistics:
    inertia: _exact.SparseInertiaStatistics
    provider_call_attempts: int
    provider_calls_completed: int
    uncertain_provider_calls: int
    mass_proof_reuse_count: int
    sealed: bool
    closed: bool


@dataclass(frozen=True)
class SparseCachedIntervalPencilCustody:
    dimension: int
    stiffness_input_hash: str
    mass_input_hash: str
    mass_proof_profile: str
    source_snapshot_isolated: bool = True
    external_or_durable_authority_verified: bool = False
    caller_numerical_admission_verified: bool = False


@dataclass(frozen=True)
class SparseCachedIntervalPencilCount:
    dimension: int
    shift_numerator: int
    shift_denominator: int
    negative: int
    zero: int
    positive: int
    stiffness_input_hash: str
    mass_input_hash: str
    mass_inertia: _exact.SparseInertiaResult
    statistics: _exact.SparseInertiaStatistics
    cumulative_statistics: SparseCachedIntervalPencilStatistics
    custody: SparseCachedIntervalPencilCustody
    algorithm_profile: str = CACHED_INTERVAL_PENCIL_PROFILE

    @property
    def less_than_shift(self) -> int:
        return self.negative

    @property
    def equal_to_shift(self) -> int:
        return self.zero

    @property
    def less_than_or_equal_to_shift(self) -> int:
        return self.negative + self.zero


class SparseCachedIntervalPencilError(_exact.SparseInertiaError):
    def __init__(
        self,
        message: str,
        statistics: _exact.SparseInertiaStatistics,
        cumulative_statistics: SparseCachedIntervalPencilStatistics,
    ) -> None:
        super().__init__(message, statistics)
        self.cumulative_statistics = cumulative_statistics


class SparseCachedIntervalPencilUncertain(
    SparseCachedIntervalPencilError, _interval.SparseIntervalInertiaUncertain
):
    """No count; charged work remains, and only query rows are released."""


class SparseCachedIntervalPencilBudgetExceeded(
    SparseCachedIntervalPencilError, _exact.SparseInertiaBudgetExceeded
):
    """No refund, no further queries; all retained coefficients released."""


class _RetentionLedger(_exact._Ledger):
    def reserve(self, old: Fraction, new: Fraction) -> None:
        if not new:
            # Releasing owned coefficients must remain possible after a tighter
            # window/storage refusal. This changes retention only, not spend.
            self.values["current_stored_entries"] -= bool(old)
            self.values["current_stored_bits"] -= _exact._bits(old) if old else 0
            return
        super().reserve(old, new)


class _DistinctEndpointOps(_interval._IntervalOps):
    """Evaluate each distinct endpoint pair once on the shared live ledger.

    Point intervals have the same lower and upper endpoint. Repeating their
    exact Fraction arithmetic does not strengthen the enclosure. Keep the
    inherited outward rounding and charge every operation actually attempted.
    """

    @staticmethod
    def _endpoints(value: _interval.Binary64Interval) -> tuple[float, ...]:
        if value.lower == value.upper:
            return (value.lower,)
        return value.lower, value.upper

    def _point_binary(self, a, b, name):
        if a.lower == a.upper and b.lower == b.upper:
            exact = self.ledger.operation(
                Fraction.from_float(a.lower), Fraction.from_float(b.lower), name
            )
            return self.enclose(exact)
        return getattr(super(), name)(a, b)

    def add(self, a, b):
        return self._point_binary(a, b, "add")

    def subtract(self, a, b):
        return self._point_binary(a, b, "subtract")

    def _extrema(self, a, b, name):
        values = [
            self.ledger.operation(
                Fraction.from_float(x), Fraction.from_float(y), name
            )
            for x in self._endpoints(a)
            for y in self._endpoints(b)
        ]
        return self.enclose(min(values), max(values))

    def multiply(self, a, b):
        return self._extrema(a, b, "multiply")

    def divide(self, a, b):
        if b.lower <= 0 <= b.upper:
            raise _interval.SparseIntervalInertiaUncertain(
                "interval division includes zero"
            )
        return self._extrema(a, b, "divide")

    def square(self, a):
        if a.lower == a.upper:
            return self.multiply(a, a)
        return super().square(a)


class _AtomicIntervalRows(_interval._IntervalRows):
    def set(self, i: int, j: int, value: _interval.Binary64Interval) -> None:
        ledger = self.ops.ledger
        before = (
            ledger.values["current_stored_entries"],
            ledger.values["current_stored_bits"],
        )
        try:
            super().set(i, j, value)
        except _exact.SparseInertiaError:
            # Two endpoint reservations precede map assignment. A refusal can
            # leave only the first reservation charged, without retained data.
            # Roll back those unallocated CURRENT reservations, never work/peaks.
            (
                ledger.values["current_stored_entries"],
                ledger.values["current_stored_bits"],
            ) = before
            raise


def _release_rows(rows: _exact._Rows | _interval._IntervalRows | None) -> None:
    if rows is None:
        return
    ledger = rows.ledger if isinstance(rows, _exact._Rows) else rows.ops.ledger
    for row in rows.rows.values():
        for value in row.values():
            coefficients = (
                (value,)
                if isinstance(value, Fraction)
                else (
                    Fraction.from_float(value.lower),
                    Fraction.from_float(value.upper),
                )
            )
            for coefficient in coefficients:
                ledger.reserve(coefficient, _ZERO)
    rows.rows.clear()


def _interval_copy(
    source: _exact._Rows, ops: _interval._IntervalOps
) -> _AtomicIntervalRows:
    rows = _AtomicIntervalRows(source.dimension, ops)
    try:
        for i, row in source.rows.items():
            for j, value in row.items():
                rows.set(i, j, ops.enclose(value))
        return rows
    except _exact.SparseInertiaError:
        _release_rows(rows)
        raise


class SparseCachedIntervalPencil:
    """Live immutable-pair prototype, not serialized count/cost authority.

    Inputs must not be mutated concurrently with construction. Their private
    CSR snapshots are read once into exact immutable-by-API coefficients;
    later caller mutations cannot alter this pair. Construction and the first
    query share ONE provider window. Later queries use fixed global ceilings
    and a fresh *local* work window, while retaining all prior cumulative spend.
    A stricter caller budget can only tighten that window, never enlarge it.
    No successful query/result cache or exact fallback is used.
    """

    def __init__(
        self,
        stiffness: Any,
        mass: Any,
        *,
        budget: SparseCachedIntervalPencilBudget | None = None,
    ) -> None:
        self._budget = (
            budget if budget is not None else SparseCachedIntervalPencilBudget()
        )
        if not isinstance(self._budget, SparseCachedIntervalPencilBudget):
            raise ValueError("budget must be SparseCachedIntervalPencilBudget")
        self._ledger = _RetentionLedger(self._budget.provider_budget)
        self._zero_statistics = self._ledger.snapshot()
        self._reported = self._zero_statistics
        self._attempts = self._completed = self._uncertain = self._reuses = 0
        self._sealed = self._closed = False
        self._k: _exact._Rows | None = None
        self._m: _exact._Rows | None = None
        self._hint_workspace = _exact._Workspace(self._ledger)
        self._hint: Fraction | None = None
        self._set_window(self._zero_statistics, self._budget.provider_budget)
        massrows = None
        failure: tuple[str, str] | None = None
        try:
            self._k, khash = self._snapshot_load(stiffness, "stiffness")
            self._m, mhash = self._snapshot_load(mass, "mass")
            if self._k.dimension != self._m.dimension:
                raise _interval.SparseIntervalInertiaError(
                    "stiffness and mass shapes must agree"
                )
            self._hint = self._gershgorin_hint()
            massrows = _interval_copy(self._m, _DistinctEndpointOps(self._ledger))
            counts = _interval._eliminate(massrows, minimum_degree_pivots=True)
            if counts != (0, 0, self._m.dimension):
                raise _interval.SparseIntervalInertiaError(
                    "mass must be certified positive definite"
                )
            self._custody = SparseCachedIntervalPencilCustody(
                self._k.dimension,
                khash,
                mhash,
                _interval.INTERVAL_SPARSE_INERTIA_PROFILE,
            )
        except _exact.SparseInertiaError as error:
            failure = self._failure_kind(error), str(error)
        finally:
            _release_rows(massrows)
        if failure is not None:
            self._dispose()
            # _load can fail before returning its private partial row map.
            # It is no longer owned here: release current reservation accounting.
            # Spent and peak fields remain; Python traceback overhead is outside proxy.
            self._ledger.values["current_stored_entries"] = 0
            self._ledger.values["current_stored_bits"] = 0
            self._sealed = True
            self._raise_failure(*failure)
        self._constructor_statistics = self._ledger.snapshot()
        self._mass_proof = _exact.SparseInertiaResult(
            self._custody.dimension,
            *counts,
            mhash,
            self._constructor_statistics,
            _interval.INTERVAL_SPARSE_INERTIA_PROFILE,
        )

    def _snapshot_load(self, matrix: Any, name: str) -> tuple[_exact._Rows, str]:
        if not issparse(matrix) or matrix.format != "csr":
            raise _interval.SparseIntervalInertiaError(f"{name} must be binary64 CSR")
        if (
            len(matrix.shape) != 2
            or matrix.shape[0] != matrix.shape[1]
            or matrix.shape[0] <= 0
        ):
            raise _interval.SparseIntervalInertiaError(
                f"{name} must be nonempty square CSR"
            )
        if matrix.shape[0] > self._budget.provider_budget.maximum_dimension:
            self._ledger.refuse("dimension_before_snapshot")
        if (
            matrix.data.dtype != _exact.np.dtype(_exact.np.float64)
            or matrix.data.ndim != 1
            or matrix.indices.ndim != 1
            or matrix.indptr.ndim != 1
            or matrix.indices.dtype.kind not in "iu"
            or matrix.indptr.dtype.kind not in "iu"
            or len(matrix.indices) != len(matrix.data)
            or len(matrix.indptr) != matrix.shape[0] + 1
        ):
            raise _interval.SparseIntervalInertiaError(
                f"{name} CSR storage is invalid before snapshot"
            )
        pointers = [int(value) for value in matrix.indptr]
        self._ledger.work(len(pointers))
        if (
            pointers[0] != 0
            or pointers[-1] != len(matrix.data)
            or any(
                a > b or a < 0 or b > len(matrix.data)
                for a, b in zip(pointers, pointers[1:])
            )
        ):
            raise _interval.SparseIntervalInertiaError(
                f"{name} CSR pointers are invalid before snapshot"
            )
        if (
            len(matrix.data)
            > self._ledger.budget.maximum_input_entries
            - self._ledger.values["input_entries"]
        ):
            self._ledger.refuse("input_entries_before_snapshot")
        snapshot = matrix.copy()
        for array in (snapshot.data, snapshot.indices, snapshot.indptr):
            array.flags.writeable = False
        return _exact._load(snapshot, self._ledger, name)

    def _gershgorin_hint(self) -> Fraction | None:
        assert self._m is not None
        lower = None
        for i in range(self._m.dimension):
            row_bound = self._m.get(i, i)
            for j, value in self._m.rows.get(i, {}).items():
                self._ledger.work()
                if j != i:
                    row_bound = self._ledger.operation(
                        row_bound, abs(value), "subtract"
                    )
            lower = row_bound if lower is None else min(lower, row_bound)
        if lower is not None and lower > 0:
            hint = self._ledger.operation(lower, Fraction(2), "divide")
            self._hint_workspace.keep(hint)
            return hint
        return None

    def _set_window(
        self,
        baseline: _exact.SparseInertiaStatistics,
        requested: _exact.SparseInertiaBudget,
    ) -> None:
        limits = {
            item.name: min(
                getattr(self._budget.provider_budget, item.name),
                getattr(requested, item.name),
            )
            for item in fields(requested)
        }
        for name, global_name in _AGGREGATE.items():
            limits[name] = min(
                getattr(self._budget, global_name),
                getattr(baseline, _COUNTER[name]) + limits[name],
            )
        self._ledger.budget = _exact.SparseInertiaBudget(**limits)
        for field_name, maximum_name in (
            ("current_stored_entries", "maximum_stored_entries"),
            ("current_stored_bits", "maximum_total_stored_bits"),
            ("peak_coefficient_bits", "maximum_coefficient_bits"),
        ):
            if self._ledger.values[field_name] > limits[maximum_name]:
                self._ledger.refuse(field_name)
        for name, counter in _COUNTER.items():
            if self._ledger.values[counter] > limits[name]:
                self._ledger.refuse(counter)

    @staticmethod
    def _failure_kind(error: _exact.SparseInertiaError) -> str:
        if isinstance(error, _exact.SparseInertiaBudgetExceeded):
            return "budget"
        if isinstance(error, _interval.SparseIntervalInertiaUncertain):
            return "uncertain"
        return "input"

    def _take_delta(self) -> _exact.SparseInertiaStatistics:
        current = self._ledger.snapshot()
        values = {item.name: getattr(current, item.name) for item in fields(current)}
        for name in _ADDITIVE:
            values[name] -= getattr(self._reported, name)
        self._reported = current
        return _exact.SparseInertiaStatistics(**values)

    def _raise_failure(self, kind: str, message: str) -> NoReturn:
        delta = self._take_delta()
        error_class = {
            "budget": SparseCachedIntervalPencilBudgetExceeded,
            "uncertain": SparseCachedIntervalPencilUncertain,
            "input": SparseCachedIntervalPencilError,
        }[kind]
        raise error_class(message, delta, self.statistics)

    def _dispose(self) -> None:
        self._hint_workspace.release()
        self._hint = None
        _release_rows(self._k)
        _release_rows(self._m)
        self._k = self._m = None
        self._closed = True

    @property
    def statistics(self) -> SparseCachedIntervalPencilStatistics:
        return SparseCachedIntervalPencilStatistics(
            self._ledger.snapshot(),
            self._attempts,
            self._completed,
            self._uncertain,
            self._reuses,
            self._sealed,
            self._closed,
        )

    @property
    def custody(self) -> SparseCachedIntervalPencilCustody:
        return self._custody

    @property
    def constructor_statistics(self) -> _exact.SparseInertiaStatistics:
        return self._constructor_statistics

    @property
    def exact_mass_lower_bound_hint(self) -> Fraction | None:
        """Strict original Gershgorin hint only; no fresh M-mu*I count claim.

        General SPD matrices need not be diagonally dominant. None does not
        reject such mass: its one-time interval SPD proof still applies.
        Future lower-bound halving must charge each M/I proof into one live
        aggregate coordinator and maintain that separate source-pair identity.
        """
        return self._hint

    def count(
        self,
        shift: float | int | Fraction,
        *,
        budget: _exact.SparseInertiaBudget | None = None,
    ) -> SparseCachedIntervalPencilCount:
        if self._closed or self._sealed:
            self._raise_failure(
                "input", "cached pencil is closed/sealed; no new count admitted"
            )
        self._attempts += 1
        shifted = None
        failure = None
        try:
            if self._attempts > self._budget.maximum_provider_calls:
                self._ledger.refuse("provider_call_attempts")
            requested = _exact._budget(budget)
            baseline = (
                self._zero_statistics
                if self._attempts == 1
                else self._ledger.snapshot()
            )
            self._set_window(baseline, requested)
            if isinstance(shift, Fraction):
                t = shift
            elif type(shift) is int:
                t = Fraction(shift)
            elif type(shift) is float and math.isfinite(shift):
                t = Fraction.from_float(shift)
            else:
                raise _interval.SparseIntervalInertiaError(
                    "shift must be finite float/int/Fraction"
                )
            self._ledger.coefficient(t)
            assert self._k is not None and self._m is not None
            ops = _DistinctEndpointOps(self._ledger)
            shifted = _AtomicIntervalRows(self._custody.dimension, ops)
            for i in range(self._custody.dimension):
                keys = set(self._k.rows.get(i, {})) | set(self._m.rows.get(i, {}))
                self._ledger.work(len(keys))
                for j in sorted(keys):
                    if j < i:
                        continue
                    coefficient = self._ledger.operation(
                        self._k.get(i, j),
                        self._ledger.operation(t, self._m.get(i, j), "multiply"),
                        "subtract",
                    )
                    shifted.symmetric_set(i, j, ops.enclose(coefficient))
            self._reuses += 1
            counts = _interval._eliminate(shifted, minimum_degree_pivots=True)
            self._completed += 1
        except _exact.SparseInertiaError as error:
            failure = self._failure_kind(error), str(error)
            if failure[0] == "uncertain":
                self._uncertain += 1
            elif failure[0] == "budget":
                self._sealed = True
        finally:
            _release_rows(shifted)
            if self._sealed:
                self._dispose()
        if failure is not None:
            self._raise_failure(*failure)
        return SparseCachedIntervalPencilCount(
            self._custody.dimension,
            t.numerator,
            t.denominator,
            *counts,
            self._custody.stiffness_input_hash,
            self._custody.mass_input_hash,
            self._mass_proof,
            self._take_delta(),
            self.statistics,
            self._custody,
        )

    def close(self) -> _exact.SparseInertiaStatistics:
        """Release cache; return unreported startup/query costs exactly once."""
        self._dispose()
        return self._take_delta()
