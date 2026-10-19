"""Exact, budgeted inertia of binary64 CSR matrices and symmetric pencils.

This independent utility does not extract modal vectors or repair the modal
solver.  Congruence elimination uses sparse row maps and exact ``Fraction``
arithmetic; it never forms a dense matrix or infers inertia from numeric LU.
Budgets count sparse-map and retained-workspace coefficients, rational bits,
arithmetic work and pivot attempts. Expression temporaries, Python container
overhead and runtime imports are not a hard memory bound. Fraction arithmetic
allocates its result before the result-bit check; work weights are proxies,
not operating-system CPU/RSS limits or an external quota.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from fractions import Fraction
import hashlib
import math
import struct
from typing import Any

import numpy as np
from scipy.sparse import issparse


EXACT_SPARSE_INERTIA_PROFILE = "exact_binary64_fraction_sparse_congruence.v1"
_ZERO = Fraction(0)


@dataclass(frozen=True)
class SparseInertiaBudget:
    maximum_dimension: int = 4096
    maximum_input_entries: int = 1_000_000
    maximum_stored_entries: int = 200_000
    maximum_coefficient_bits: int = 65_536
    maximum_total_stored_bits: int = 64_000_000
    maximum_work_units: int = 10_000_000
    maximum_bit_operation_cost: int = 1_000_000_000
    maximum_pivots: int = 8192
    maximum_inertia_calls: int = 2

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{item.name} must be a positive integer")


@dataclass(frozen=True)
class SparseInertiaStatistics:
    input_entries: int
    current_stored_entries: int
    peak_stored_entries: int
    current_stored_bits: int
    peak_stored_bits: int
    peak_coefficient_bits: int
    current_workspace_entries: int
    peak_workspace_entries: int
    current_workspace_bits: int
    peak_workspace_bits: int
    work_units: int
    fraction_operation_attempts: int
    bit_operation_cost: int
    pivot_attempts: int
    one_by_one_pivots: int
    two_by_two_pivots: int
    zero_dimensions: int
    inertia_call_attempts: int
    completed_inertia_calls: int


class SparseInertiaError(ValueError):
    def __init__(
        self, message: str, statistics: SparseInertiaStatistics | None = None
    ) -> None:
        super().__init__(message)
        self.statistics = statistics


class SparseInertiaBudgetExceeded(SparseInertiaError):
    """Resource refusal with the charged, non-reset partial work counters."""


@dataclass(frozen=True)
class SparseInertiaResult:
    dimension: int
    negative: int
    zero: int
    positive: int
    input_hash: str
    statistics: SparseInertiaStatistics
    algorithm_profile: str = EXACT_SPARSE_INERTIA_PROFILE


@dataclass(frozen=True)
class SparsePencilEigenvalueCounts:
    dimension: int
    shift_numerator: int
    shift_denominator: int
    negative: int
    zero: int
    positive: int
    stiffness_input_hash: str
    mass_input_hash: str
    mass_inertia: SparseInertiaResult
    statistics: SparseInertiaStatistics
    algorithm_profile: str = EXACT_SPARSE_INERTIA_PROFILE

    @property
    def less_than_shift(self) -> int:
        return self.negative

    @property
    def equal_to_shift(self) -> int:
        return self.zero

    @property
    def less_than_or_equal_to_shift(self) -> int:
        return self.negative + self.zero


def _bits(value: Fraction) -> int:
    return abs(value.numerator).bit_length() + value.denominator.bit_length()


class _Ledger:
    def __init__(self, budget: SparseInertiaBudget) -> None:
        self.budget = budget
        self.values = {item.name: 0 for item in fields(SparseInertiaStatistics)}

    def snapshot(self) -> SparseInertiaStatistics:
        return SparseInertiaStatistics(**self.values)

    def refuse(self, name: str) -> None:
        raise SparseInertiaBudgetExceeded(
            f"exact sparse inertia budget exceeded: {name}", self.snapshot()
        )

    def charge(self, name: str, amount: int, maximum: int) -> None:
        self.values[name] += amount
        if self.values[name] > maximum:
            self.refuse(name)

    def work(self, amount: int = 1) -> None:
        self.charge("work_units", amount, self.budget.maximum_work_units)

    def coefficient(self, value: Fraction) -> Fraction:
        bits = _bits(value)
        self.values["peak_coefficient_bits"] = max(
            self.values["peak_coefficient_bits"], bits
        )
        if bits > self.budget.maximum_coefficient_bits:
            self.refuse("coefficient_bits")
        return value

    def operation(self, left: Fraction, right: Fraction, name: str) -> Fraction:
        self.work()
        self.values["fraction_operation_attempts"] += 1
        # A deterministic conservative work weight, not measured CPU instructions.
        weight = max(1, (_bits(left) + _bits(right)) ** 2)
        self.charge(
            "bit_operation_cost", weight, self.budget.maximum_bit_operation_cost
        )
        if name == "add":
            result = left + right
        elif name == "subtract":
            result = left - right
        elif name == "multiply":
            result = left * right
        else:
            if not right:
                raise SparseInertiaError("exact pivot division by zero")
            result = left / right
        return self.coefficient(result)

    def reserve(self, old: Fraction, new: Fraction) -> None:
        entries = self.values["current_stored_entries"] + bool(new) - bool(old)
        bits = (
            self.values["current_stored_bits"]
            + (_bits(new) if new else 0)
            - (_bits(old) if old else 0)
        )
        if entries > self.budget.maximum_stored_entries:
            self.refuse("stored_entries")
        if bits > self.budget.maximum_total_stored_bits:
            self.refuse("total_stored_bits")
        self.values["current_stored_entries"] = entries
        self.values["current_stored_bits"] = bits
        self.values["peak_stored_entries"] = max(
            self.values["peak_stored_entries"], entries
        )
        self.values["peak_stored_bits"] = max(self.values["peak_stored_bits"], bits)


class _Workspace:
    """Charge retained arithmetic results before caching them across updates."""

    def __init__(self, ledger: _Ledger) -> None:
        self.ledger = ledger
        self.values: list[Fraction] = []

    def keep(self, value: Fraction) -> int:
        self.ledger.work()
        self.ledger.reserve(_ZERO, value)
        self.ledger.values["current_workspace_entries"] += bool(value)
        self.ledger.values["current_workspace_bits"] += _bits(value) if value else 0
        for label in ("entries", "bits"):
            self.ledger.values["peak_workspace_" + label] = max(
                self.ledger.values["peak_workspace_" + label],
                self.ledger.values["current_workspace_" + label],
            )
        self.values.append(value if value else _ZERO)
        return len(self.values) - 1

    def __getitem__(self, index: int) -> Fraction:
        return self.values[index]

    def release(self) -> None:
        # No additional charged work can obscure the original failure while
        # releasing retained values after a budget exception.
        for value in self.values:
            self.ledger.reserve(value, _ZERO)
            self.ledger.values["current_workspace_entries"] -= bool(value)
            self.ledger.values["current_workspace_bits"] -= _bits(value) if value else 0
        self.values.clear()


class _Rows:
    def __init__(self, dimension: int, ledger: _Ledger) -> None:
        self.dimension = dimension
        self.ledger = ledger
        self.rows: dict[int, dict[int, Fraction]] = {}

    def get(self, i: int, j: int) -> Fraction:
        return self.rows.get(i, {}).get(j, _ZERO)

    def set(self, i: int, j: int, value: Fraction) -> None:
        self.ledger.work()
        self.ledger.coefficient(value)
        old = self.get(i, j)
        self.ledger.reserve(old, value)
        if value:
            self.rows.setdefault(i, {})[j] = value
        elif i in self.rows:
            self.rows[i].pop(j, None)
            if not self.rows[i]:
                del self.rows[i]

    def symmetric_set(self, i: int, j: int, value: Fraction) -> None:
        self.set(i, j, value)
        if i != j:
            self.set(j, i, value)

    def remove(self, index: int) -> None:
        for other in tuple(self.rows.get(index, {})):
            self.set(index, other, _ZERO)
            if other != index:
                self.set(other, index, _ZERO)

    def clear(self) -> None:
        for i in tuple(self.rows):
            for j in tuple(self.rows.get(i, {})):
                self.set(i, j, _ZERO)


def _budget(value: SparseInertiaBudget | None) -> SparseInertiaBudget:
    if value is None:
        return SparseInertiaBudget()
    if not isinstance(value, SparseInertiaBudget):
        raise SparseInertiaError("budget must be SparseInertiaBudget")
    return value


def _load(matrix: Any, ledger: _Ledger, name: str) -> tuple[_Rows, str]:
    if not issparse(matrix) or matrix.format != "csr":
        raise SparseInertiaError(f"{name} must be real binary64 CSR")
    if len(matrix.shape) != 2 or matrix.shape[0] != matrix.shape[1]:
        raise SparseInertiaError(f"{name} must be square")
    n = matrix.shape[0]
    if n <= 0:
        raise SparseInertiaError(f"{name} must be nonempty")
    if n > ledger.budget.maximum_dimension:
        ledger.refuse("dimension")
    if matrix.data.dtype != np.dtype(np.float64):
        raise SparseInertiaError(f"{name} must have binary64 real data")
    if (
        matrix.data.ndim != 1
        or matrix.indices.ndim != 1
        or matrix.indptr.ndim != 1
        or matrix.indices.dtype.kind not in "iu"
        or matrix.indptr.dtype.kind not in "iu"
        or len(matrix.indices) != len(matrix.data)
        or len(matrix.indptr) != n + 1
    ):
        raise SparseInertiaError(f"{name} CSR storage is invalid")
    count = len(matrix.data)
    ledger.charge("input_entries", count, ledger.budget.maximum_input_entries)
    pointers = [int(value) for value in matrix.indptr]
    ledger.work(n + 1)
    if (
        pointers[0] != 0
        or pointers[-1] != count
        or any(a > b or a < 0 or b > count for a, b in zip(pointers, pointers[1:]))
    ):
        raise SparseInertiaError(f"{name} CSR row pointers are invalid")
    digest = hashlib.sha256(b"exact-binary64-CSR-storage.v1\0")
    digest.update(struct.pack("<QQ", n, count))
    for pointer in pointers:
        digest.update(struct.pack("<Q", pointer))
    result = _Rows(n, ledger)
    for i in range(n):
        for position in range(pointers[i], pointers[i + 1]):
            ledger.work()
            j = int(matrix.indices[position])
            stored_value = float(matrix.data[position])
            if not 0 <= j < n or not math.isfinite(stored_value):
                raise SparseInertiaError(f"{name} CSR index or finite value is invalid")
            digest.update(struct.pack("<Qd", j, stored_value))
            exact = ledger.coefficient(Fraction.from_float(stored_value))
            result.set(i, j, ledger.operation(result.get(i, j), exact, "add"))
    for i, row in result.rows.items():
        for j, coefficient in row.items():
            ledger.work()
            if coefficient != result.get(j, i):
                raise SparseInertiaError(f"{name} must be exactly symmetric")
    return result, "sha256:" + digest.hexdigest()


def _eliminate(matrix: _Rows) -> tuple[int, int, int]:
    ledger = matrix.ledger
    ledger.charge("inertia_call_attempts", 1, ledger.budget.maximum_inertia_calls)
    negative = zero = positive = 0
    remaining = set(range(matrix.dimension))
    while remaining:
        ledger.work(len(remaining))
        p = min(remaining)
        neighbors = sorted(j for j in matrix.rows.get(p, {}) if j != p)
        diagonal = matrix.get(p, p)
        if not diagonal and not neighbors:
            zero += 1
            ledger.values["zero_dimensions"] += 1
            remaining.remove(p)
            continue
        ledger.charge("pivot_attempts", 1, ledger.budget.maximum_pivots)
        if diagonal:
            ledger.values["one_by_one_pivots"] += 1
            if diagonal > 0:
                positive += 1
            else:
                negative += 1
            pivot_values = {i: matrix.get(p, i) for i in neighbors}
            for offset, i in enumerate(neighbors):
                for j in neighbors[offset:]:
                    correction = ledger.operation(
                        ledger.operation(pivot_values[i], pivot_values[j], "multiply"),
                        diagonal,
                        "divide",
                    )
                    matrix.symmetric_set(
                        i,
                        j,
                        ledger.operation(matrix.get(i, j), correction, "subtract"),
                    )
            pivot_values.clear()
            matrix.remove(p)
            remaining.remove(p)
        else:
            # D=[[0,b],[b,c]] has det=-b**2<0: exactly one of each sign.
            q = neighbors[0]
            b, c = matrix.get(p, q), matrix.get(q, q)
            ledger.values["two_by_two_pivots"] += 1
            negative += 1
            positive += 1
            union = sorted((set(matrix.rows[p]) | set(matrix.rows.get(q, {}))) - {p, q})
            workspace = _Workspace(ledger)
            pair_values = {i: (matrix.get(p, i), matrix.get(q, i)) for i in union}
            applied: dict[int, tuple[int, int]] = {}
            try:
                b_squared = workspace.keep(ledger.operation(b, b, "multiply"))
                inv00 = workspace.keep(
                    ledger.operation(-c, workspace[b_squared], "divide")
                )
                inv01 = workspace.keep(ledger.operation(Fraction(1), b, "divide"))
                for i in union:
                    applied[i] = (
                        workspace.keep(
                            ledger.operation(
                                ledger.operation(
                                    workspace[inv00], pair_values[i][0], "multiply"
                                ),
                                ledger.operation(
                                    workspace[inv01], pair_values[i][1], "multiply"
                                ),
                                "add",
                            )
                        ),
                        workspace.keep(
                            ledger.operation(
                                workspace[inv01], pair_values[i][0], "multiply"
                            )
                        ),
                    )
                for offset, i in enumerate(union):
                    for j in union[offset:]:
                        correction = ledger.operation(
                            ledger.operation(
                                pair_values[i][0], workspace[applied[j][0]], "multiply"
                            ),
                            ledger.operation(
                                pair_values[i][1], workspace[applied[j][1]], "multiply"
                            ),
                            "add",
                        )
                        matrix.symmetric_set(
                            i,
                            j,
                            ledger.operation(matrix.get(i, j), correction, "subtract"),
                        )
            finally:
                applied.clear()
                pair_values.clear()
                workspace.release()
            del b, c
            matrix.remove(p)
            matrix.remove(q)
            remaining.remove(p)
            remaining.remove(q)
    if negative + zero + positive != matrix.dimension:
        raise SparseInertiaError("exact inertia lost dimension")
    ledger.values["completed_inertia_calls"] += 1
    return negative, zero, positive


def compute_sparse_inertia(
    matrix: Any, *, budget: SparseInertiaBudget | None = None
) -> SparseInertiaResult:
    """Inertia of an exactly symmetric finite binary64 CSR, without mutation."""
    ledger = _Ledger(_budget(budget))
    try:
        rows, digest = _load(matrix, ledger, "matrix")
        negative, zero, positive = _eliminate(rows)
        return SparseInertiaResult(
            rows.dimension, negative, zero, positive, digest, ledger.snapshot()
        )
    except SparseInertiaError as exc:
        if exc.statistics is None:
            exc.statistics = ledger.snapshot()
        raise


def count_sparse_generalized_eigenvalues(
    stiffness: Any,
    mass: Any,
    *,
    shift: float | int | Fraction,
    budget: SparseInertiaBudget | None = None,
) -> SparsePencilEigenvalueCounts:
    """Count lambda<shift, lambda=shift and lambda>shift for exactly SPD M.

    ``K - shift*M`` is formed as a rational expression from stored values,
    never by floating subtraction. Exact SPD here is not a replacement for a
    modal caller's existing numerical SPD/PSD/symmetry admission policies.
    Both inertia calls and all simultaneous owned rational maps share one
    budget; no external state, grants, clock or quota is consulted.
    """
    ledger = _Ledger(_budget(budget))
    try:
        if isinstance(shift, Fraction):
            exact_shift = shift
        elif type(shift) is int:
            exact_shift = Fraction(shift)
        elif isinstance(shift, (float, np.float64)) and math.isfinite(shift):
            exact_shift = Fraction.from_float(float(shift))
        else:
            raise SparseInertiaError("shift must be finite float, int or Fraction")
        ledger.coefficient(exact_shift)
        k_rows, k_hash = _load(stiffness, ledger, "stiffness")
        m_rows, m_hash = _load(mass, ledger, "mass")
        if k_rows.dimension != m_rows.dimension:
            raise SparseInertiaError("stiffness and mass must have the same shape")
        shifted = _Rows(k_rows.dimension, ledger)
        for i in range(k_rows.dimension):
            keys = set(k_rows.rows.get(i, {})) | set(m_rows.rows.get(i, {}))
            ledger.work(len(keys))
            for j in sorted(keys):
                shifted.set(
                    i,
                    j,
                    ledger.operation(
                        k_rows.get(i, j),
                        ledger.operation(exact_shift, m_rows.get(i, j), "multiply"),
                        "subtract",
                    ),
                )
        k_rows.clear()
        mass_counts = _eliminate(m_rows)
        mass_result = SparseInertiaResult(
            m_rows.dimension, *mass_counts, m_hash, ledger.snapshot()
        )
        if mass_counts != (0, 0, m_rows.dimension):
            raise SparseInertiaError("mass must be exactly positive definite")
        negative, zero, positive = _eliminate(shifted)
        return SparsePencilEigenvalueCounts(
            shifted.dimension,
            exact_shift.numerator,
            exact_shift.denominator,
            negative,
            zero,
            positive,
            k_hash,
            m_hash,
            mass_result,
            ledger.snapshot(),
        )
    except SparseInertiaError as exc:
        if exc.statistics is None:
            exc.statistics = ledger.snapshot()
        raise
