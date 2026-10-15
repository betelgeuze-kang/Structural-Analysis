"""Global count/interval certificates, without modal-vector acceptance.

All inertia calls share cumulative work budgets. Exact SPD from the count
provider does not replace a caller's numerical SPD/PSD/symmetry policies.
No eigenvectors, dense extraction, external state or solver retries occur.
Input snapshots and cached certificates are bounded by declared dimensions,
input entries and provider calls; rational work/bit counters are proxies, not
hard bounds on every Python/CSR allocation or OS CPU/RSS. An external resource
limit is required for a hard execution bound. Failed attempts retain charged
partial counters, which can exceed a cap at the refusing operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from fractions import Fraction
import math
from typing import Any, NoReturn

from scipy.sparse import eye, issparse

from structural_analysis.solvers.sparse_interval_inertia import SparseIntervalInertiaUncertain

from structural_analysis.solvers.sparse_inertia import (
    SparseInertiaBudget,
    SparseInertiaBudgetExceeded,
    SparseInertiaError,
    SparseInertiaStatistics,
    SparsePencilEigenvalueCounts,
    count_sparse_generalized_eigenvalues,
)


@dataclass(frozen=True)
class SparseModalCertificateBudget:
    provider_budget: SparseInertiaBudget = field(default_factory=SparseInertiaBudget)
    maximum_provider_calls: int = 256
    maximum_aggregate_input_entries: int = 10_000_000
    maximum_aggregate_work_units: int = 100_000_000
    maximum_aggregate_bit_operation_cost: int = 64_000_000_000
    maximum_aggregate_pivots: int = 1_000_000
    maximum_aggregate_inertia_calls: int = 512
    maximum_growth_steps: int = 128
    maximum_total_refinements: int = 1024
    maximum_refinements_per_interval: int = 96
    maximum_intervals: int = 256
    maximum_shift_bits: int = 4096

    def __post_init__(self) -> None:
        if not isinstance(self.provider_budget, SparseInertiaBudget):
            raise ValueError("provider_budget must be SparseInertiaBudget")
        for item in fields(self):
            if item.name == "provider_budget":
                continue
            value = getattr(self, item.name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{item.name} must be a positive integer")


@dataclass(frozen=True)
class SparseModalCertificateStatistics:
    provider_call_attempts: int = 0
    provider_calls_completed: int = 0
    aggregate_input_entries: int = 0
    aggregate_work_units: int = 0
    aggregate_bit_operation_cost: int = 0
    aggregate_pivots: int = 0
    aggregate_inertia_calls: int = 0
    aggregate_fraction_operation_attempts: int = 0
    peak_stored_entries_per_provider: int = 0
    peak_stored_bits_per_provider: int = 0
    peak_coefficient_bits: int = 0
    count_cache_hits: int = 0
    growth_steps: int = 0
    refinement_attempts: int = 0
    peak_shift_bits: int = 0


class SparseModalCertificateError(ValueError):
    def __init__(
        self, message: str, statistics: SparseModalCertificateStatistics | None = None
    ) -> None:
        super().__init__(message)
        self.statistics = statistics


class SparseModalCertificateBudgetExceeded(SparseModalCertificateError):
    pass


@dataclass(frozen=True)
class CountEndpoint:
    shift: Fraction
    less: int
    equal: int
    less_or_equal: int


@dataclass(frozen=True)
class CertifiedEigenvalueInterval:
    """Enclose one global ordinal in (lower,upper], or an exact point.

    At an exact point, count_below_lower is strict. Otherwise it is inclusive
    at the excluded lower endpoint. Counts enclose all multiplicity, rather
    than only an extracted subset of eigenvalues.
    """

    lower: Fraction
    upper: Fraction
    count_below_lower: int
    count_through_upper: int
    target_global_ordinal: int

    @property
    def enclosed_multiplicity(self) -> int:
        return self.count_through_upper - self.count_below_lower


@dataclass(frozen=True)
class CertifiedModalCluster:
    lower: Fraction
    upper: Fraction
    positive_ordinal_start: int
    positive_ordinal_stop: int
    multiplicity: int
    lower_guard: CountEndpoint
    upper_guard: CountEndpoint
    preceding_guard: CountEndpoint | None
    following_guard: CountEndpoint | None
    outside_gap_lower_bound: Fraction


@dataclass(frozen=True)
class SparseModalSpectrumCertificate:
    dimension: int
    requested_mode_count: int
    stiffness_input_hash: str
    mass_input_hash: str
    largest: CertifiedEigenvalueInterval
    threshold_lower: Fraction
    threshold_upper: Fraction
    rigid_mode_count: int
    threshold_lower_guard: CountEndpoint
    threshold_upper_guard: CountEndpoint
    positive_intervals: tuple[CertifiedEigenvalueInterval, ...]
    selected_clusters: tuple[CertifiedModalCluster, ...]
    mass_lower_bound: Fraction
    mass_lower_bound_guard: CountEndpoint
    mass_bound_stiffness_input_hash: str
    mass_bound_identity_input_hash: str
    statistics: SparseModalCertificateStatistics
    vectors_verified: bool = False
    caller_numerical_admission_verified: bool = False
    algorithm_profile: str = "exact_inertia_global_modal_count_intervals.v1"


class _Ledger:
    def __init__(
        self, budget: SparseModalCertificateBudget, *, live_session: Any | None = None
    ) -> None:
        self.live_session = live_session
        if live_session is not None:
            from structural_analysis.solvers.sparse_live_modal_pipeline import (
                _LiveCountSession,
            )

            if type(live_session) is not _LiveCountSession:
                raise SparseModalCertificateError("invalid private live proof session")
            live_session.check_owner()
        self.budget = budget
        self.values = {
            item.name: 0 for item in fields(SparseModalCertificateStatistics)
        }

    def snapshot(self) -> SparseModalCertificateStatistics:
        return SparseModalCertificateStatistics(**self.values)

    def refuse(self, name: str) -> NoReturn:
        raise SparseModalCertificateBudgetExceeded(
            f"sparse modal certificate budget exceeded: {name}", self.snapshot()
        )

    def increment(self, name: str, maximum: int) -> None:
        self.values[name] += 1
        if self.values[name] > maximum:
            self.refuse(name)

    def endpoint(self, shift: Fraction) -> None:
        bits = abs(shift.numerator).bit_length() + shift.denominator.bit_length()
        self.values["peak_shift_bits"] = max(self.values["peak_shift_bits"], bits)
        if bits > self.budget.maximum_shift_bits:
            self.refuse("shift_bits")

    def remaining_provider_budget(self) -> SparseInertiaBudget:
        reductions = {
            "maximum_input_entries": (
                "aggregate_input_entries",
                "maximum_aggregate_input_entries",
            ),
            "maximum_work_units": (
                "aggregate_work_units",
                "maximum_aggregate_work_units",
            ),
            "maximum_bit_operation_cost": (
                "aggregate_bit_operation_cost",
                "maximum_aggregate_bit_operation_cost",
            ),
            "maximum_pivots": ("aggregate_pivots", "maximum_aggregate_pivots"),
            "maximum_inertia_calls": (
                "aggregate_inertia_calls",
                "maximum_aggregate_inertia_calls",
            ),
        }
        overrides = {}
        for provider_name, (counter, maximum_name) in reductions.items():
            remaining = getattr(self.budget, maximum_name) - self.values[counter]
            if remaining <= 0:
                self.refuse(counter)
            overrides[provider_name] = min(
                getattr(self.budget.provider_budget, provider_name), remaining
            )
        return replace(self.budget.provider_budget, **overrides)

    def absorb(self, stats: SparseInertiaStatistics) -> None:
        sums = {
            "aggregate_input_entries": stats.input_entries,
            "aggregate_work_units": stats.work_units,
            "aggregate_bit_operation_cost": stats.bit_operation_cost,
            "aggregate_pivots": stats.pivot_attempts,
            "aggregate_inertia_calls": stats.inertia_call_attempts,
            "aggregate_fraction_operation_attempts": stats.fraction_operation_attempts,
        }
        for key, value in sums.items():
            self.values[key] += value
        for key, value in [
            ("peak_stored_entries_per_provider", stats.peak_stored_entries),
            ("peak_stored_bits_per_provider", stats.peak_stored_bits),
            ("peak_coefficient_bits", stats.peak_coefficient_bits),
        ]:
            self.values[key] = max(self.values[key], value)


class _Oracle:
    def __init__(self, stiffness: Any, mass: Any, ledger: _Ledger) -> None:
        if not issparse(stiffness) or not issparse(mass):
            raise SparseModalCertificateError("stiffness and mass must be CSR")
        if stiffness.format != "csr" or mass.format != "csr":
            raise SparseModalCertificateError("stiffness and mass must be CSR")
        if stiffness.shape != mass.shape or stiffness.shape[0] != stiffness.shape[1]:
            raise SparseModalCertificateError(
                "stiffness and mass must be equal square matrices"
            )
        if stiffness.shape[0] > ledger.budget.provider_budget.maximum_dimension:
            ledger.refuse("dimension")
        if (
            len(stiffness.data) + len(mass.data)
            > ledger.budget.provider_budget.maximum_input_entries
        ):
            ledger.refuse("input_entries_before_snapshot")
        if ledger.live_session is not None:
            from structural_analysis.solvers.sparse_live_modal_pipeline import (
                _LiveCountSession,
            )

            if type(ledger.live_session) is not _LiveCountSession:
                raise SparseModalCertificateError("invalid private proof context")
            ledger.live_session._fee(
                len(stiffness.data) + len(mass.data) + 2 * stiffness.shape[0]
            )
        self.stiffness = stiffness.copy()
        self.mass = mass.copy()
        self.dimension = stiffness.shape[0]
        self.ledger = ledger
        self.cache: dict[Fraction, SparsePencilEigenvalueCounts] = {}
        self.identity: tuple[str, str] | None = None

    def count(self, shift: Fraction) -> SparsePencilEigenvalueCounts:
        self.ledger.endpoint(shift)
        if self.ledger.live_session is not None:
            context = self.ledger.live_session
            try:
                result = context.acquire(
                    self.stiffness,
                    self.mass,
                    shift=shift,
                    budget=self.ledger.budget.provider_budget,
                )
            except SparseInertiaError as error:
                self.ledger.values.update(context.certificate_totals())
                error_type = (
                    SparseModalCertificateBudgetExceeded
                    if isinstance(error, SparseInertiaBudgetExceeded)
                    else SparseModalCertificateError
                )
                raise error_type(
                    f"private live provider refused: {error}", self.ledger.snapshot()
                ) from error
            self.ledger.values.update(context.certificate_totals())
            identity = result.stiffness_input_hash, result.mass_input_hash
            if self.identity is not None and identity != self.identity:
                raise SparseModalCertificateError(
                    "count input snapshot changed", self.ledger.snapshot()
                )
            self.identity = identity
            self.cache[shift] = result
            return result
        if shift in self.cache:
            self.ledger.values["count_cache_hits"] += 1
            return self.cache[shift]
        self.ledger.increment(
            "provider_call_attempts", self.ledger.budget.maximum_provider_calls
        )
        budget = self.ledger.remaining_provider_budget()
        try:
            result = count_sparse_generalized_eigenvalues(
                self.stiffness, self.mass, shift=shift, budget=budget
            )
        except SparseInertiaError as exc:
            if exc.statistics is not None:
                self.ledger.absorb(exc.statistics)
            error_type = (
                SparseModalCertificateBudgetExceeded
                if isinstance(exc, SparseInertiaBudgetExceeded)
                else SparseModalCertificateError
            )
            raise error_type(
                f"exact inertia provider refused: {exc}", self.ledger.snapshot()
            ) from exc
        self.ledger.absorb(result.statistics)
        self.ledger.values["provider_calls_completed"] += 1
        identity = result.stiffness_input_hash, result.mass_input_hash
        if self.identity is not None and identity != self.identity:
            raise SparseModalCertificateError(
                "count input snapshot changed", self.ledger.snapshot()
            )
        self.identity = identity
        self.cache[shift] = result
        return result

    def endpoint(self, shift: Fraction) -> CountEndpoint:
        result = self.count(shift)
        return CountEndpoint(
            shift, result.negative, result.zero, result.negative + result.zero
        )


def _fraction(value: Any, name: str, *, positive: bool = False) -> Fraction:
    if isinstance(value, Fraction):
        result = value
    elif type(value) is int:
        result = Fraction(value)
    elif type(value) is float and math.isfinite(value):
        result = Fraction.from_float(value)
    else:
        raise SparseModalCertificateError(f"{name} must be finite int/float/Fraction")
    if result < 0 or (positive and not result):
        raise SparseModalCertificateError(
            f"{name} must be {'positive' if positive else 'nonnegative'}"
        )
    return result


def _refinement(oracle: _Oracle) -> None:
    oracle.ledger.increment(
        "refinement_attempts", oracle.ledger.budget.maximum_total_refinements
    )


def _largest(oracle: _Oracle) -> CertifiedEigenvalueInterval:
    n = oracle.dimension
    lower, upper = Fraction(0), Fraction(1)
    while oracle.count(lower).less_than_or_equal_to_shift == n:
        oracle.ledger.increment(
            "growth_steps", oracle.ledger.budget.maximum_growth_steps
        )
        lower = Fraction(-1) if not lower else 2 * lower
    while True:
        try:
            upper_count = oracle.count(upper)
        except SparseModalCertificateError as exc:
            if not isinstance(exc.__cause__, SparseIntervalInertiaUncertain):
                raise
            # An optional search point may be too close to an eigenvalue for
            # binary64 interval signs. It supplies NO count. Grow to a different
            # upper bound on the same paid ledger; budget refusals stay terminal.
            # Actual policy/rigid thresholds never use this bracket-search rule.
        else:
            if upper_count.less_than_or_equal_to_shift == n:
                break
        oracle.ledger.increment(
            "growth_steps", oracle.ledger.budget.maximum_growth_steps
        )
        upper *= 2
    endpoint = oracle.count(upper)
    if endpoint.zero:
        return CertifiedEigenvalueInterval(upper, upper, endpoint.negative, n, n)
    return CertifiedEigenvalueInterval(
        lower, upper, oracle.count(lower).less_than_or_equal_to_shift, n, n
    )


def _refine_interval(
    oracle: _Oracle, interval: CertifiedEigenvalueInterval
) -> CertifiedEigenvalueInterval:
    if interval.lower == interval.upper:
        return interval
    _refinement(oracle)
    middle = (interval.lower + interval.upper) / 2
    count = oracle.count(middle)
    target = interval.target_global_ordinal
    if count.negative < target <= count.less_than_or_equal_to_shift:
        return CertifiedEigenvalueInterval(
            middle, middle, count.negative, count.less_than_or_equal_to_shift, target
        )
    if count.less_than_or_equal_to_shift >= target:
        return CertifiedEigenvalueInterval(
            interval.lower,
            middle,
            interval.count_below_lower,
            count.less_than_or_equal_to_shift,
            target,
        )
    return CertifiedEigenvalueInterval(
        middle,
        interval.upper,
        count.less_than_or_equal_to_shift,
        interval.count_through_upper,
        target,
    )


def _threshold_bounds(
    largest: CertifiedEigenvalueInterval, tolerance: Fraction
) -> tuple[Fraction, Fraction]:
    low, high = largest.lower, largest.upper
    minimum_abs = Fraction(0) if low <= 0 <= high else min(abs(low), abs(high))
    return tolerance * max(minimum_abs, Fraction(1)), tolerance * max(
        abs(low), abs(high), Fraction(1)
    )


def _ordinal(
    oracle: _Oracle,
    target: int,
    lower: Fraction,
    lower_count: int,
    upper: Fraction,
    relative_width: Fraction,
) -> CertifiedEigenvalueInterval:
    top = oracle.count(upper)
    if top.negative < target <= top.less_than_or_equal_to_shift:
        return CertifiedEigenvalueInterval(
            upper, upper, top.negative, top.less_than_or_equal_to_shift, target
        )
    interval = CertifiedEigenvalueInterval(
        lower, upper, lower_count, top.less_than_or_equal_to_shift, target
    )
    for _ in range(oracle.ledger.budget.maximum_refinements_per_interval):
        if (
            interval.lower == interval.upper
            or interval.upper - interval.lower
            <= relative_width
            * max(abs(interval.lower), abs(interval.upper), Fraction(1))
        ):
            return interval
        interval = _refine_interval(oracle, interval)
    oracle.ledger.refuse("ordinal_refinements")


def _relation(
    left: CertifiedEigenvalueInterval,
    right: CertifiedEigenvalueInterval,
    tolerance: Fraction,
) -> bool | None:
    # Positive eigenvalues; preserve the original adjacent floor-one cluster rule.
    minimum_scale = max(left.lower, right.lower, Fraction(1))
    maximum_scale = max(left.upper, right.upper, Fraction(1))
    if right.upper - left.lower <= tolerance * minimum_scale:
        return True
    if right.lower - left.upper > tolerance * maximum_scale:
        return False
    return None


def certify_sparse_modal_spectrum(
    stiffness: Any,
    mass: Any,
    *,
    mode_count: int,
    rigid_mode_relative_tolerance: float | Fraction = 1e-10,
    cluster_relative_tolerance: float | Fraction = 1e-9,
    interval_relative_width: Fraction = Fraction(1, 1 << 40),
    mass_lower_bound_hint: Fraction = Fraction(1),
    budget: SparseModalCertificateBudget | None = None,
    _live_session: Any | None = None,
) -> SparseModalSpectrumCertificate:
    """Certify global counts and selected whole-cluster intervals, not vectors.

    Thresholds use exact rational ``tol*max(abs(lambda_largest),1)`` bounds.
    A future binary64 consumer must enclose its rounded threshold or explicitly
    use these guards; this utility does not relabel the old ARPACK threshold.
    Numerical admission and actual complete-space extraction remain separate.
    The rigid count is the inclusive count below the positive threshold; it
    represents rigid/nullity only after the caller's numerical K-PSD policy.
    """
    if budget is None:
        budget = SparseModalCertificateBudget()
    if not isinstance(budget, SparseModalCertificateBudget):
        raise SparseModalCertificateError("budget must be SparseModalCertificateBudget")
    ledger = _Ledger(budget, live_session=_live_session)
    try:
        rigid = _fraction(rigid_mode_relative_tolerance, "rigid tolerance")
        cluster = _fraction(cluster_relative_tolerance, "cluster tolerance")
        width = _fraction(interval_relative_width, "interval width", positive=True)
        mass_bound = _fraction(mass_lower_bound_hint, "mass bound hint", positive=True)
        oracle = _Oracle(stiffness, mass, ledger)
        n = oracle.dimension
        if type(mode_count) is not int or mode_count <= 0 or mode_count > n - 2:
            raise SparseModalCertificateError("mode_count must be in [1, dimension-2]")
        if mode_count + 1 > budget.maximum_intervals:
            ledger.refuse("interval_count")
        largest = _largest(oracle)
        for _ in range(budget.maximum_refinements_per_interval):
            threshold_lo, threshold_hi = _threshold_bounds(largest, rigid)
            lower_guard, upper_guard = (
                oracle.endpoint(threshold_lo),
                oracle.endpoint(threshold_hi),
            )
            if lower_guard.less_or_equal == upper_guard.less_or_equal:
                break
            largest = _refine_interval(oracle, largest)
        else:
            ledger.refuse("threshold_refinements")
        rigid_count = lower_guard.less_or_equal
        if n - rigid_count < mode_count:
            raise SparseModalCertificateError(
                "not enough positive eigenvalues above certified threshold"
            )
        wanted = min(mode_count + 1, n - rigid_count)
        intervals = [
            _ordinal(
                oracle, rigid_count + j, threshold_hi, rigid_count, largest.upper, width
            )
            for j in range(1, wanted + 1)
        ]
        joined = []
        for index in range(len(intervals) - 1):
            for _ in range(budget.maximum_refinements_per_interval):
                relation = _relation(intervals[index], intervals[index + 1], cluster)
                if relation is not None:
                    joined.append(relation)
                    break
                intervals[index] = _refine_interval(oracle, intervals[index])
                intervals[index + 1] = _refine_interval(oracle, intervals[index + 1])
            else:
                ledger.refuse("cluster_relation_refinements")
        if len(intervals) > mode_count and joined[mode_count - 1]:
            raise SparseModalCertificateError(
                "requested mode_count cuts a repeated or clustered eigenvalue group"
            )
        clusters = []
        start = 0
        while start < mode_count:
            stop = start + 1
            while stop < mode_count and joined[stop - 1]:
                stop += 1
            first, last = intervals[start], intervals[stop - 1]
            left_guard = oracle.endpoint(first.lower)
            right_guard = oracle.endpoint(last.upper)
            below = (
                left_guard.less
                if first.lower == first.upper
                else left_guard.less_or_equal
            )
            if (
                below != rigid_count + start
                or right_guard.less_or_equal != rigid_count + stop
            ):
                raise SparseModalCertificateError(
                    "selected interval does not certify full global cluster rank"
                )
            preceding = (
                oracle.endpoint(intervals[start - 1].upper)
                if start
                else (lower_guard if rigid_count else None)
            )
            following = (
                oracle.endpoint(intervals[stop].lower)
                if stop < len(intervals)
                else None
            )
            if preceding is not None and preceding.less_or_equal != rigid_count + start:
                raise SparseModalCertificateError(
                    "preceding guard does not certify adjacent global rank"
                )
            if following is not None:
                next_interval = intervals[stop]
                next_below = (
                    following.less
                    if next_interval.lower == next_interval.upper
                    else following.less_or_equal
                )
                if next_below != rigid_count + stop:
                    raise SparseModalCertificateError(
                        "following guard does not certify adjacent global rank"
                    )
            gaps = []
            if preceding is not None:
                gaps.append(first.lower - preceding.shift)
            if following is not None:
                gaps.append(following.shift - last.upper)
            if not gaps or min(gaps) <= 0:
                raise SparseModalCertificateError(
                    "selected cluster lacks a positive count-verified outside gap"
                )
            clusters.append(
                CertifiedModalCluster(
                    first.lower,
                    last.upper,
                    start + 1,
                    stop,
                    stop - start,
                    left_guard,
                    right_guard,
                    preceding,
                    following,
                    min(gaps),
                )
            )
            start = stop
        # Counts of M-mu*I under the SAME cumulative ledger prove a useful
        # positive lower bound for the generalized residual error estimate.
        mass_oracle = _Oracle(oracle.mass, eye(n, format="csr", dtype=float), ledger)
        while mass_oracle.count(mass_bound).less_than_or_equal_to_shift:
            ledger.increment("growth_steps", budget.maximum_growth_steps)
            mass_bound /= 2
        mass_guard = mass_oracle.endpoint(mass_bound)
        assert oracle.identity is not None
        assert mass_oracle.identity is not None
        if mass_oracle.identity[0] != oracle.identity[1]:
            raise SparseModalCertificateError(
                "mass lower-bound certificate input does not match original mass"
            )
        return SparseModalSpectrumCertificate(
            n,
            mode_count,
            *oracle.identity,
            largest,
            threshold_lo,
            threshold_hi,
            rigid_count,
            lower_guard,
            upper_guard,
            tuple(intervals),
            tuple(clusters),
            mass_bound,
            mass_guard,
            *mass_oracle.identity,
            ledger.snapshot(),
        )
    except SparseModalCertificateError as exc:
        if exc.statistics is None:
            exc.statistics = ledger.snapshot()
        raise
