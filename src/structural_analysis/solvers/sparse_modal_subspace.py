"""Deterministic thin-block extraction for globally certified modal clusters.

This is an independent, unintegrated building block.  Exact count certificates
bind the requested rank and outside gaps; sparse LU only applies numeric solves.
Coordinate augmentation is part of one bounded algorithm, not random restarts.
Small Ritz matrices are dense, but the n-by-n sparse model is never densified.
Caller numerical admission, canonical output and the public modal solver remain
separate.  Arithmetic counters are proxies; OS memory/CPU limits are external.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from fractions import Fraction
import math
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import eigh
from scipy.sparse import eye, issparse
from scipy.sparse.linalg import splu

from structural_analysis.solvers.sparse_inertia import (
    SparseInertiaBudget,
    SparseInertiaError,
    count_sparse_generalized_eigenvalues,
)
from structural_analysis.solvers.sparse_modal_certificate import (
    SparseModalSpectrumCertificate,
)


@dataclass(frozen=True)
class SparseModalSubspaceBudget:
    maximum_block_columns: int = 64
    maximum_thin_entries: int = 2_000_000
    maximum_coordinate_attempts: int = 4096
    maximum_iterations_per_block: int = 32
    maximum_total_iterations: int = 4096
    maximum_total_provider_calls: int = 512
    maximum_total_work_units: int = 100_000_000
    maximum_total_bit_operation_cost: int = 128_000_000_000
    maximum_total_inertia_calls: int = 1024
    provider_budget: SparseInertiaBudget = SparseInertiaBudget(
        maximum_bit_operation_cost=20_000_000_000
    )

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "provider_budget":
                if not isinstance(value, SparseInertiaBudget):
                    raise ValueError("provider_budget must be SparseInertiaBudget")
            elif type(value) is not int or value <= 0:
                raise ValueError(f"{item.name} must be a positive integer")


@dataclass(frozen=True)
class SparseModalSubspaceStatistics:
    total_provider_calls: int
    total_work_units: int
    total_bit_operation_cost: int
    total_inertia_calls: int
    certificate_provider_calls: int
    coordinate_attempts: int
    iterations: int
    factorizations: int
    solve_columns: int
    peak_thin_entries: int


class SparseModalSubspaceError(ValueError):
    def __init__(
        self, message: str, statistics: SparseModalSubspaceStatistics | None = None
    ) -> None:
        super().__init__(message)
        self.statistics = statistics


class SparseModalSubspaceBudgetExceeded(SparseModalSubspaceError):
    """Spent certificate and extraction counters are retained on refusal."""


@dataclass(frozen=True)
class ExtractedModalCluster:
    eigenvalues: tuple[float, ...]
    mass_normalized_vectors: tuple[tuple[float, ...], ...]
    positive_ordinal_start: int
    positive_ordinal_stop: int
    residual_relative_inf_maximum: float
    mass_orthogonality_error_inf: float
    subspace_error_bound: float
    numeric_shift: float


@dataclass(frozen=True)
class SparseModalSubspaceResult:
    dimension: int
    requested_mode_count: int
    clusters: tuple[ExtractedModalCluster, ...]
    stiffness_input_hash: str
    mass_input_hash: str
    statistics: SparseModalSubspaceStatistics
    vectors_verified: bool = True
    public_modal_integration_verified: bool = False
    caller_numerical_admission_verified: bool = False
    rounded_residual_error_enclosure_verified: bool = False
    certificate_cost_provenance_verified: bool = False
    algorithm_profile: str = "certified_coordinate_augmented_thin_shift_invert.v1"


class _Ledger:
    def __init__(
        self,
        budget: SparseModalSubspaceBudget,
        certificate: SparseModalSpectrumCertificate,
        *,
        live_session: Any | None = None,
    ) -> None:
        self.budget = budget
        self.live = live_session
        if self.live is not None:
            from structural_analysis.solvers.sparse_live_modal_pipeline import (
                _LiveCountSession,
            )

            if type(self.live) is not _LiveCountSession:
                raise SparseModalSubspaceError("invalid private proof context")
            self.live.authentic(certificate)
        spent = certificate.statistics
        if any(
            type(getattr(spent, f.name)) is not int or getattr(spent, f.name) < 0
            for f in fields(spent)
        ):
            raise SparseModalSubspaceError(
                "certificate spent counters must be nonnegative integers"
            )
        self.values = {f.name: 0 for f in fields(SparseModalSubspaceStatistics)}
        self.values.update(
            total_provider_calls=spent.provider_call_attempts,
            total_work_units=spent.aggregate_work_units,
            total_bit_operation_cost=spent.aggregate_bit_operation_cost,
            total_inertia_calls=spent.aggregate_inertia_calls,
            certificate_provider_calls=spent.provider_call_attempts,
        )
        for name in (
            "total_provider_calls",
            "total_work_units",
            "total_bit_operation_cost",
            "total_inertia_calls",
        ):
            if self.values[name] > getattr(budget, "maximum_" + name):
                self.refuse(name)

    def snapshot(self) -> SparseModalSubspaceStatistics:
        return SparseModalSubspaceStatistics(**self.values)

    def refuse(self, name: str) -> None:
        raise SparseModalSubspaceBudgetExceeded(
            f"sparse modal subspace budget exceeded: {name}", self.snapshot()
        )

    def charge(self, name: str, amount: int, maximum: int) -> None:
        self.values[name] += amount
        if self.values[name] > maximum:
            self.refuse(name)

    def count(self, stiffness: Any, mass: Any, shift: Fraction):
        if self.live is not None:
            try:
                result = self.live.acquire(
                    stiffness, mass, shift=shift, budget=self.budget.provider_budget
                )
            except SparseInertiaError as exc:
                self.values.update(self.live.subspace_totals())
                raise SparseModalSubspaceError(
                    f"private live count refused: {exc}", self.snapshot()
                ) from exc
            self.values.update(self.live.subspace_totals())
            for name in (
                "total_provider_calls",
                "total_work_units",
                "total_bit_operation_cost",
                "total_inertia_calls",
            ):
                if self.values[name] > getattr(self.budget, "maximum_" + name):
                    self.refuse(name)
            return result
        self.charge("total_provider_calls", 1, self.budget.maximum_total_provider_calls)
        reductions = {
            "maximum_work_units": "total_work_units",
            "maximum_bit_operation_cost": "total_bit_operation_cost",
            "maximum_inertia_calls": "total_inertia_calls",
        }
        limits = {}
        for provider_name, counter in reductions.items():
            remaining = (
                getattr(self.budget, "maximum_" + counter) - self.values[counter]
            )
            if remaining <= 0:
                self.refuse(counter)
            limits[provider_name] = min(
                remaining, getattr(self.budget.provider_budget, provider_name)
            )
        budget = replace(self.budget.provider_budget, **limits)
        try:
            result = count_sparse_generalized_eigenvalues(
                stiffness, mass, shift=shift, budget=budget
            )
        except SparseInertiaError as exc:
            if exc.statistics is not None:
                self.absorb(exc.statistics)
            raise SparseModalSubspaceError(
                f"exact count provider refused: {exc}", self.snapshot()
            ) from exc
        self.absorb(result.statistics)
        return result

    def absorb(self, stats: Any) -> None:
        self.values["total_work_units"] += stats.work_units
        self.values["total_bit_operation_cost"] += stats.bit_operation_cost
        self.values["total_inertia_calls"] += stats.inertia_call_attempts


def _orthonormalize(columns, mass, locked, needed: int, rank_tolerance: float):
    accepted: list[NDArray[np.float64]] = []
    for column in columns:
        vector = np.array(column, dtype=float, copy=True)
        original_squared = float(vector @ (mass @ vector))
        if not math.isfinite(original_squared) or original_squared <= 0:
            continue
        for _ in range(2):
            for basis in list(locked.T) + accepted:
                vector -= basis * float(basis @ (mass @ vector))
        squared = float(vector @ (mass @ vector))
        if (
            not math.isfinite(squared)
            or squared <= rank_tolerance**2 * original_squared
        ):
            continue
        vector /= math.sqrt(squared)
        if not np.all(np.isfinite(vector)):
            raise SparseModalSubspaceError("nonfinite mass-normalized basis")
        accepted.append(vector)
        if len(accepted) == needed:
            break
    return np.column_stack(accepted) if accepted else np.zeros((mass.shape[0], 0))


def _ritz(stiffness, mass, basis):
    projected = basis.T @ (stiffness @ basis)
    metric = basis.T @ (mass @ basis)
    values, rotation = eigh(
        (projected + projected.T) / 2,
        (metric + metric.T) / 2,
        check_finite=True,
    )
    return values, basis @ rotation


def _measures(stiffness, mass, vectors, values, mass_lower, gap):
    mv = mass @ vectors
    kv = stiffness @ vectors
    residual = kv - mv * values[None, :]
    denominator = np.maximum(
        np.max(np.abs(kv), axis=0) + np.abs(values) * np.max(np.abs(mv), axis=0),
        np.finfo(float).tiny,
    )
    relative = np.max(np.abs(residual), axis=0) / denominator
    # Keep a conservative normalization margin for the numerical M-Gram gate.
    spectral_distance = 2 * np.linalg.norm(residual, axis=0) / math.sqrt(mass_lower)
    metric_error = float(np.max(np.abs(vectors.T @ mv - np.eye(vectors.shape[1]))))
    block = kv - mv @ (vectors.T @ kv)
    # Ritz intervals must lie within gap/4 of the target.  Thus gap/2 is a
    # conservative outside separation, with a further normalization margin.
    subspace_bound = 4 * float(np.linalg.norm(block)) / math.sqrt(mass_lower) / gap
    return relative, spectral_distance, metric_error, subspace_bound


def _validate_cluster(stiffness, mass, certificate, cluster, ledger):
    below = certificate.rigid_mode_count + cluster.positive_ordinal_start - 1
    through = certificate.rigid_mode_count + cluster.positive_ordinal_stop
    low = ledger.count(stiffness, mass, cluster.lower)
    high = (
        low
        if cluster.lower == cluster.upper
        else ledger.count(stiffness, mass, cluster.upper)
    )
    for result in (low, high):
        if (result.stiffness_input_hash, result.mass_input_hash) != (
            certificate.stiffness_input_hash,
            certificate.mass_input_hash,
        ):
            raise SparseModalSubspaceError("certificate input identity mismatch")
    actual_below = (
        low.negative
        if cluster.lower == cluster.upper
        else low.less_than_or_equal_to_shift
    )
    if actual_below != below or high.less_than_or_equal_to_shift != through:
        raise SparseModalSubspaceError("cluster does not have its certified full rank")
    if cluster.multiplicity != through - below or cluster.outside_gap_lower_bound <= 0:
        raise SparseModalSubspaceError("invalid cluster multiplicity or outside gap")
    gaps = []
    for endpoint, preceding in (
        (cluster.preceding_guard, True),
        (cluster.following_guard, False),
    ):
        if endpoint is None:
            continue
        result = ledger.count(stiffness, mass, endpoint.shift)
        if preceding:
            if result.less_than_or_equal_to_shift != below:
                raise SparseModalSubspaceError("preceding guard has wrong global rank")
            gaps.append(cluster.lower - endpoint.shift)
        else:
            if result.negative != through:
                raise SparseModalSubspaceError("following guard has wrong global rank")
            gaps.append(endpoint.shift - cluster.upper)
    if not gaps or min(gaps) < cluster.outside_gap_lower_bound:
        raise SparseModalSubspaceError("outside gap is not independently count bounded")


def _validate_global_prefix(stiffness, mass, certificate, ledger, tolerance):
    if isinstance(tolerance, Fraction):
        relative = tolerance
    elif type(tolerance) is float and math.isfinite(tolerance):
        relative = Fraction.from_float(tolerance)
    else:
        raise SparseModalSubspaceError("rigid tolerance must be finite float/Fraction")
    if relative < 0:
        raise SparseModalSubspaceError("rigid tolerance must be nonnegative")
    largest = certificate.largest
    n = certificate.dimension
    if largest.lower > largest.upper or largest.target_global_ordinal != n:
        raise SparseModalSubspaceError("largest interval has wrong global ordinal")

    def fresh(shift):
        result = ledger.count(stiffness, mass, shift)
        if (result.stiffness_input_hash, result.mass_input_hash) != (
            certificate.stiffness_input_hash,
            certificate.mass_input_hash,
        ):
            raise SparseModalSubspaceError("certificate input identity mismatch")
        return result

    low = fresh(largest.lower)
    high = low if largest.lower == largest.upper else fresh(largest.upper)
    below = (
        low.negative
        if largest.lower == largest.upper
        else low.less_than_or_equal_to_shift
    )
    if (
        below >= n
        or high.less_than_or_equal_to_shift != n
        or below != largest.count_below_lower
        or high.less_than_or_equal_to_shift != largest.count_through_upper
    ):
        raise SparseModalSubspaceError(
            "largest interval lacks fresh global count proof"
        )
    minimum_abs = (
        Fraction(0)
        if largest.lower <= 0 <= largest.upper
        else min(abs(largest.lower), abs(largest.upper))
    )
    bounds = (
        relative * max(minimum_abs, Fraction(1)),
        relative * max(abs(largest.lower), abs(largest.upper), Fraction(1)),
    )
    if bounds != (certificate.threshold_lower, certificate.threshold_upper):
        raise SparseModalSubspaceError("rigid threshold does not match caller policy")
    for shift, guard in zip(
        bounds,
        (certificate.threshold_lower_guard, certificate.threshold_upper_guard),
        strict=True,
    ):
        count = fresh(shift)
        if (
            count.less_than_or_equal_to_shift != certificate.rigid_mode_count
            or guard.shift != shift
            or guard.less != count.negative
            or guard.equal != count.zero
            or guard.less_or_equal != count.less_than_or_equal_to_shift
        ):
            raise SparseModalSubspaceError("rigid count lacks fresh threshold proof")


def _numeric_shift(stiffness, mass, cluster, ledger):
    center = (cluster.lower + cluster.upper) / 2
    gap = cluster.outside_gap_lower_bound
    seen = set()
    for index in range(cluster.multiplicity + 1):
        exact = center + gap * (
            Fraction(1, 4) + Fraction(index, 16 * (cluster.multiplicity + 1))
        )
        value = float(exact)
        if not math.isfinite(value) or value in seen:
            continue
        seen.add(value)
        rounded = Fraction.from_float(value)
        # All target eigenvalues remain strictly nearer than any outside one.
        if not center + gap / 8 < rounded < center + 3 * gap / 8:
            continue
        if ledger.count(stiffness, mass, rounded).equal_to_shift == 0:
            return value
    raise SparseModalSubspaceError("no representable nonsingular target shift")


def _bounded_provisional(provisional, n, certificate, budget, ledger):
    if provisional is None:
        columns = 0
    elif type(provisional) is np.ndarray:
        if (
            provisional.ndim != 2
            or provisional.shape[0] != n
            or provisional.dtype.kind not in "iuf"
        ):
            raise SparseModalSubspaceError("invalid provisional thin vectors")
        columns = provisional.shape[1]
    elif type(provisional) in (list, tuple):
        if len(provisional) != n or any(
            type(row) not in (list, tuple) for row in provisional
        ):
            raise SparseModalSubspaceError("invalid provisional thin vectors")
        columns = len(provisional[0])
        if any(len(row) != columns for row in provisional):
            raise SparseModalSubspaceError("invalid provisional thin vectors")
        if any(
            not isinstance(value, (int, float, np.integer, np.floating))
            or isinstance(value, (bool, np.bool_))
            for row in provisional
            for value in row
        ):
            raise SparseModalSubspaceError("invalid provisional thin vectors")
    else:
        raise SparseModalSubspaceError("invalid provisional thin vectors")
    if columns > budget.maximum_block_columns:
        ledger.refuse("provisional_block_columns")
    width = max(c.multiplicity for c in certificate.selected_clusters)
    # Conservative coefficient envelope for retained provisional/output data,
    # Gram-Schmidt copies, shifted/Ritz bases and residual work arrays. Sparse
    # LU, libraries and Python container overhead are outside this proxy.
    envelope = (
        n * (certificate.requested_mode_count + columns + 12 * width) + 6 * width**2
    )
    ledger.values["peak_thin_entries"] = max(
        ledger.values["peak_thin_entries"], envelope
    )
    if envelope > budget.maximum_thin_entries:
        ledger.refuse("thin_entries")
    result = (
        np.zeros((n, 0))
        if provisional is None
        else np.array(provisional, dtype=float, copy=True)
    )
    if not np.all(np.isfinite(result)):
        raise SparseModalSubspaceError("invalid provisional thin vectors")
    return result


def extract_certified_sparse_modal_subspace(
    stiffness: Any,
    mass: Any,
    certificate: SparseModalSpectrumCertificate,
    *,
    provisional_vectors: Any | None = None,
    rigid_mode_relative_tolerance: float | Fraction = 1e-10,
    residual_relative_tolerance: float = 1e-9,
    orthogonality_tolerance: float = 1e-8,
    subspace_error_tolerance: float = 1e-8,
    rank_relative_tolerance: float = 1e-12,
    budget: SparseModalSubspaceBudget | None = None,
    _live_session: Any | None = None,
) -> SparseModalSubspaceResult:
    """Extract every certified selected cluster, including missing directions.

    Declared certificate costs are included in cumulative counters; their
    authentic custody must be established by a caller's live coordinator.
    This helper does not authenticate external grants or certificate costs.
    Fresh count calls
    recheck input identity, largest ordinal, caller rigid threshold/full prefix,
    full cluster rank, outside gaps and the mass bound. Numerical residual
    estimates use binary64 arithmetic and are not directed rounding enclosures.
    Any numerical failure or exhausted coordinate/iteration/work budget remains
    an explicit failure.  No dense model fallback or alternate random seed is
    used.  The returned Ritz basis still needs caller canonical/original gates.
    """
    if not isinstance(certificate, SparseModalSpectrumCertificate):
        raise SparseModalSubspaceError(
            "certificate must be SparseModalSpectrumCertificate"
        )
    if budget is None:
        budget = SparseModalSubspaceBudget()
    if not isinstance(budget, SparseModalSubspaceBudget):
        raise SparseModalSubspaceError("budget must be SparseModalSubspaceBudget")
    ledger = _Ledger(budget, certificate, live_session=_live_session)
    try:
        for value in (residual_relative_tolerance, orthogonality_tolerance):
            if not math.isfinite(value) or value < 0:
                raise SparseModalSubspaceError(
                    "residual and orthogonality tolerances must be finite and nonnegative"
                )
        for value in (subspace_error_tolerance, rank_relative_tolerance):
            if not math.isfinite(value) or value <= 0:
                raise SparseModalSubspaceError(
                    "subspace and rank tolerances must be finite and positive"
                )
        n = certificate.dimension
        if not issparse(stiffness) or not issparse(mass):
            raise SparseModalSubspaceError("stiffness and mass must be CSR")
        if stiffness.format != "csr" or mass.format != "csr":
            raise SparseModalSubspaceError("stiffness and mass must be CSR")
        if stiffness.shape != (n, n) or mass.shape != (n, n):
            raise SparseModalSubspaceError("certificate shape mismatch")
        if n > budget.provider_budget.maximum_dimension:
            ledger.refuse("dimension_before_snapshot")
        if (
            len(stiffness.data) + len(mass.data)
            > budget.provider_budget.maximum_input_entries
        ):
            ledger.refuse("input_entries_before_snapshot")
        # Every proof and numeric factor uses this one owned input snapshot.
        # Coefficient-work counters do not purport to measure CSR/container RSS.
        stiffness, mass = stiffness.copy(), mass.copy()
        if (
            not certificate.selected_clusters
            or sum(c.multiplicity for c in certificate.selected_clusters)
            != certificate.requested_mode_count
        ):
            raise SparseModalSubspaceError("certificate selected rank mismatch")
        next_ordinal = 1
        previous_upper = None
        for cluster in certificate.selected_clusters:
            if (
                cluster.multiplicity <= 0
                or cluster.positive_ordinal_start != next_ordinal
                or cluster.positive_ordinal_stop
                != next_ordinal + cluster.multiplicity - 1
                or cluster.lower > cluster.upper
                or (previous_upper is not None and cluster.lower <= previous_upper)
            ):
                raise SparseModalSubspaceError(
                    "selected clusters must cover one ordered positive prefix"
                )
            next_ordinal = cluster.positive_ordinal_stop + 1
            previous_upper = cluster.upper
        # Returned vectors from earlier clusters remain retained while another
        # thin block is solved. This coefficient proxy includes those outputs;
        # temporary array/container overhead still needs the external OS cap.
        retained_entries = n * certificate.requested_mode_count
        if retained_entries > budget.maximum_thin_entries:
            ledger.refuse("retained_thin_entries")
        provisional = _bounded_provisional(
            provisional_vectors, n, certificate, budget, ledger
        )
        _validate_global_prefix(
            stiffness, mass, certificate, ledger, rigid_mode_relative_tolerance
        )
        mass_check = ledger.count(
            mass, eye(n, format="csr", dtype=float), certificate.mass_lower_bound
        )
        if (
            mass_check.stiffness_input_hash != certificate.mass_input_hash
            or mass_check.less_than_or_equal_to_shift
        ):
            raise SparseModalSubspaceError("mass lower bound is not count certified")
        mass_lower = float(certificate.mass_lower_bound)
        if not math.isfinite(mass_lower) or mass_lower <= 0:
            raise SparseModalSubspaceError("mass lower bound is not representable")
        groups = []
        for cluster in certificate.selected_clusters:
            width = cluster.multiplicity
            if width > budget.maximum_block_columns or width > n - 2:
                ledger.refuse("block_columns")
            entries = retained_entries + n * max(width, provisional.shape[1])
            ledger.values["peak_thin_entries"] = max(
                ledger.values["peak_thin_entries"], entries
            )
            if entries > budget.maximum_thin_entries:
                ledger.refuse("thin_entries")
            _validate_cluster(stiffness, mass, certificate, cluster, ledger)
            shift = _numeric_shift(stiffness, mass, cluster, ledger)
            ledger.values["factorizations"] += 1
            factor = splu((stiffness - shift * mass).tocsc())
            locked = np.zeros((n, 0))
            cursor = 0
            initial = [x for x in provisional.T]
            solved = False
            while not solved:
                needed = width - locked.shape[1]
                seeds = initial
                initial = []
                trial = _orthonormalize(
                    seeds, mass, locked, needed, rank_relative_tolerance
                )
                while trial.shape[1] < needed and cursor < n:
                    ledger.charge(
                        "coordinate_attempts", 1, budget.maximum_coordinate_attempts
                    )
                    coordinate = np.zeros(n)
                    coordinate[cursor] = 1
                    cursor += 1
                    trial = _orthonormalize(
                        list(trial.T) + [coordinate],
                        mass,
                        locked,
                        needed,
                        rank_relative_tolerance,
                    )
                if not trial.shape[1]:
                    raise SparseModalSubspaceError(
                        "coordinate augmentation did not complete certified rank"
                    )
                for _ in range(budget.maximum_iterations_per_block):
                    ledger.charge("iterations", 1, budget.maximum_total_iterations)
                    ledger.values["solve_columns"] += trial.shape[1]
                    applied = factor.solve(mass @ trial)
                    if not np.all(np.isfinite(applied)):
                        raise SparseModalSubspaceError("nonfinite shifted solve")
                    trial = _orthonormalize(
                        applied.T, mass, locked, needed, rank_relative_tolerance
                    )
                    if not trial.shape[1]:
                        break
                    values, trial = _ritz(stiffness, mass, trial)
                    relative, errors, _, _ = _measures(
                        stiffness,
                        mass,
                        trial,
                        values,
                        mass_lower,
                        float(cluster.outside_gap_lower_bound),
                    )
                    admitted = (
                        (values + errors >= float(cluster.lower))
                        & (values - errors <= float(cluster.upper))
                        & (relative <= residual_relative_tolerance)
                        & (errors < float(cluster.outside_gap_lower_bound) / 4)
                    )
                    if np.any(admitted):
                        new = _orthonormalize(
                            trial[:, admitted].T,
                            mass,
                            locked,
                            needed,
                            rank_relative_tolerance,
                        )
                        locked = np.column_stack((locked, new))
                        needed = width - locked.shape[1]
                        if not needed:
                            values, locked = _ritz(stiffness, mass, locked)
                            relative, errors, metric_error, bound = _measures(
                                stiffness,
                                mass,
                                locked,
                                values,
                                mass_lower,
                                float(cluster.outside_gap_lower_bound),
                            )
                            prefix_accuracy_satisfied = True
                            if len(certificate.selected_clusters) > 1:
                                # Bound cross-cluster errors while refining this
                                # same block within its existing iteration budget.
                                tau = min(orthogonality_tolerance, 1.0)
                                prefix_accuracy_satisfied = (
                                    metric_error <= tau
                                    and bound <= min(
                                        subspace_error_tolerance, tau / 8.0
                                    )
                                    and float(np.linalg.norm(errors, ord=2))
                                    <= (tau / 2.0)
                                    * max(float(np.max(np.abs(values))), 1.0)
                                )
                            if (
                                np.max(relative) <= residual_relative_tolerance
                                and metric_error <= orthogonality_tolerance
                                and bound <= subspace_error_tolerance
                                and prefix_accuracy_satisfied
                            ):
                                groups.append(
                                    ExtractedModalCluster(
                                        tuple(float(x) for x in values),
                                        tuple(
                                            tuple(float(x) for x in v) for v in locked.T
                                        ),
                                        cluster.positive_ordinal_start,
                                        cluster.positive_ordinal_stop,
                                        float(np.max(relative)),
                                        metric_error,
                                        bound,
                                        shift,
                                    )
                                )
                                solved = True
                                break
                            # Refine the same complete block; never relabel its rank.
                            trial, locked, needed = locked, np.zeros((n, 0)), width
                        else:
                            trial = _orthonormalize(
                                trial[:, ~admitted].T,
                                mass,
                                locked,
                                needed,
                                rank_relative_tolerance,
                            )
                            if not trial.shape[1]:
                                break
                    elif np.max(relative) <= residual_relative_tolerance:
                        # A seed with no remaining target projection converged to
                        # outside directions. Continue the fixed coordinate scan.
                        break
                if not solved and cursor >= n:
                    raise SparseModalSubspaceError(
                        "certified space did not converge within coordinate budget"
                    )
        return SparseModalSubspaceResult(
            n,
            certificate.requested_mode_count,
            tuple(groups),
            certificate.stiffness_input_hash,
            certificate.mass_input_hash,
            ledger.snapshot(),
        )
    except (
        SparseModalSubspaceError,
        RuntimeError,
        ValueError,
        np.linalg.LinAlgError,
    ) as exc:
        if isinstance(exc, SparseModalSubspaceError):
            if exc.statistics is None:
                exc.statistics = ledger.snapshot()
            raise
        raise SparseModalSubspaceError(str(exc), ledger.snapshot()) from exc
