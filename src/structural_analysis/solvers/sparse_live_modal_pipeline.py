"""Same-live source-bound modal count proofs with a single cumulative ledger.

Only this coordinator mints reusable proof sessions. External/plaintext
certificate paths remain freshly counted. Independent callers have independent
explicit sessions; one instance rejects overlapping runs. No globals are swapped.
Coefficient retention/work are proxies, not all Python/CSR/CPU memory bounds.
Caller numerical policies and original-coordinate export gates remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from fractions import Fraction
import hashlib
import math
import struct
import threading
import os
from typing import Any

from scipy.sparse import eye, issparse

from structural_analysis.solvers.sparse_cached_interval_pencil import (
    CACHED_INTERVAL_PENCIL_PROFILE,
    SparseCachedIntervalPencil,
    SparseCachedIntervalPencilBudget,
)
from structural_analysis.solvers.sparse_inertia import (
    SparseInertiaBudget,
    SparseInertiaBudgetExceeded,
    SparseInertiaError,
    SparseInertiaStatistics,
)
from structural_analysis.solvers import sparse_modal_certificate as certificate
from structural_analysis.solvers import sparse_modal_subspace as subspace

LIVE_MODAL_COUNT_PROFILE = "source_bound_live_count_certified_modal.v1"
PROFILE = LIVE_MODAL_COUNT_PROFILE
_TOKEN = object()
_COUNT_METHOD = SparseCachedIntervalPencil.count
_ZERO = SparseInertiaStatistics(**{f.name: 0 for f in fields(SparseInertiaStatistics)})
_SUM = (
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
_CAPS = {
    "provider_attempts": ("maximum_provider_calls", 256),
    "input_entries": ("maximum_aggregate_input_entries", 10_000_000),
    "work_units": ("maximum_aggregate_work_units", 100_000_000),
    "bit_operation_cost": ("maximum_aggregate_bit_operation_cost", 64_000_000_000),
    "pivot_attempts": ("maximum_aggregate_pivots", 1_000_000),
    "inertia_call_attempts": ("maximum_aggregate_inertia_calls", 512),
}
_PROVIDER_COUNTER = {
    "maximum_input_entries": "input_entries",
    "maximum_work_units": "work_units",
    "maximum_bit_operation_cost": "bit_operation_cost",
    "maximum_pivots": "pivot_attempts",
    "maximum_inertia_calls": "inertia_call_attempts",
}


class LiveModalPipelineError(SparseInertiaError):
    def __init__(
        self,
        message: str,
        statistics: Any = None,
        *,
        cumulative_cost: dict[str, Any] | None = None,
        stage: str | None = None,
        certificate: Any = None,
        public_threshold_guard: Any = None,
        stiffness_psd_guard: Any = None,
        mass_spd_guard: Any = None,
    ) -> None:
        super().__init__(message, statistics)
        self.cumulative_cost = cumulative_cost
        self.stage = stage
        self.certificate = certificate
        self.public_threshold_guard = public_threshold_guard
        self.stiffness_psd_guard = stiffness_psd_guard
        self.mass_spd_guard = mass_spd_guard


class LiveModalPipelineBudgetExceeded(
    LiveModalPipelineError, SparseInertiaBudgetExceeded
):
    pass


@dataclass(frozen=True)
class LiveModalPipelineBudget:
    provider_budget: SparseInertiaBudget = SparseInertiaBudget()
    maximum_provider_calls: int = 256
    maximum_aggregate_input_entries: int = 10_000_000
    maximum_aggregate_work_units: int = 100_000_000
    maximum_aggregate_bit_operation_cost: int = 64_000_000_000
    maximum_aggregate_pivots: int = 1_000_000
    maximum_aggregate_inertia_calls: int = 512
    maximum_count_requests: int = 1024

    def __post_init__(self):
        defaults = SparseInertiaBudget()
        if type(self.provider_budget) is not SparseInertiaBudget:
            raise ValueError("exact provider budget type required")
        for f in fields(defaults):
            if getattr(self.provider_budget, f.name) > getattr(defaults, f.name):
                raise ValueError("provider caps cannot increase")
        for name, maximum in [
            *[(n, m) for n, m in _CAPS.values()],
            ("maximum_count_requests", 1024),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError(f"invalid tightened cap: {name}")


@dataclass(frozen=True)
class PublicRigidThresholdGuard:
    threshold: float
    exact_shift: Fraction
    dimension: int
    less: int
    equal: int
    less_or_equal: int
    stiffness_input_hash: str
    mass_input_hash: str
    count_provider_profile: str
    largest_estimate_error_enclosure_verified: bool = False


@dataclass(frozen=True)
class PublicMatrixPolicyGuard:
    """All-direction count at a caller's actual binary64 admission point.

    This verifies a policy point, not an enclosure of an ARPACK estimate.
    The source pair is the admitted matrix and an identity mass matrix.
    """

    threshold: float
    exact_shift: Fraction
    dimension: int
    less: int
    equal: int
    less_or_equal: int
    stiffness_input_hash: str
    mass_input_hash: str
    count_provider_profile: str
    policy_role: str
    numerical_estimate_error_enclosure_verified: bool = False


@dataclass(frozen=True)
class LiveModalPipelineResult:
    certificate: certificate.SparseModalSpectrumCertificate
    subspace: subspace.SparseModalSubspaceResult
    cumulative_cost: dict[str, Any]
    public_threshold_guard: PublicRigidThresholdGuard | None = None
    stiffness_psd_guard: PublicMatrixPolicyGuard | None = None
    mass_spd_guard: PublicMatrixPolicyGuard | None = None
    algorithm_profile: str = PROFILE
    public_integration_verified: bool = False
    serialized_proof_authority_verified: bool = False
    caller_numerical_admission_verified: bool = False
    rounded_vector_error_enclosure_verified: bool = False
    whole_cost_or_physical_acceptance_verified: bool = False


class _TrialLedger:
    def __init__(self, budget):
        self.budget = budget
        self.values = {name: 0 for name in _SUM}
        self.values.update(
            provider_attempts=0,
            provider_completed=0,
            count_requests=0,
            proof_cache_hits=0,
            constructors=0,
            constructor_attempts=0,
            closes=0,
            prospective_provider_refusals=0,
            maximum_observed_retained_coefficient_entries=0,
            maximum_observed_retained_coefficient_bits=0,
            peak_stored_entries_per_provider=0,
            peak_stored_bits_per_provider=0,
            peak_coefficient_bits=0,
        )
        self.sealed = False
        self.events = []

    def charge(self, name, amount):
        if type(amount) is not int or amount < 0:
            raise LiveModalPipelineError("invalid additive charge")
        if amount == 0:
            return  # cleanup/no new work must not re-refuse an already-spent cap
        self.values[name] += amount
        maximum = (
            getattr(self.budget, _CAPS[name][0])
            if name in _CAPS
            else self.budget.maximum_count_requests
            if name == "count_requests"
            else None
        )
        if maximum is not None and self.values[name] > maximum:
            self.sealed = True
            raise LiveModalPipelineBudgetExceeded(
                f"global spent cap: {name}", self.stats()
            )

    def absorb_native(self, stats, prior=_ZERO):
        exceeded = None
        for name in _SUM:
            try:
                self.charge(name, getattr(stats, name) - getattr(prior, name))
            except LiveModalPipelineBudgetExceeded as error:
                exceeded = error
        if exceeded:
            raise exceeded

    def stats(self):
        return replace(_ZERO, **{k: self.values[k] for k in _SUM})

    def snapshot(self):
        return {
            **self.values,
            "sealed": self.sealed,
            "event_count": len(self.events),
            "profile": PROFILE,
        }


class _LiveCountSession:
    def __init__(self, token, trial):
        if token is not _TOKEN:
            raise LiveModalPipelineError(
                "private session cannot be imported as authority"
            )
        self.trial = trial
        self.owner = (os.getpid(), threading.get_ident())
        self.baseline = trial.values.copy()
        self.pairs = {}
        self.proofs = {}
        self.pending_work = 0
        self.closed = False
        self.minted = None
        self.authentic_statistics = None

    def check_owner(self):
        if (os.getpid(), threading.get_ident()) != self.owner:
            raise LiveModalPipelineError(
                "live proof session belongs to another process/thread"
            )
        if self.closed or self.trial.sealed:
            raise LiveModalPipelineError("closed/sealed live proof session")

    def _fee(self, amount):
        self.pending_work += amount
        self.trial.charge("work_units", amount)

    def _hash(self, matrix):
        if not issparse(matrix) or matrix.format != "csr":
            raise LiveModalPipelineError("binary64 CSR required")
        n = matrix.shape[0]
        cap = self.trial.budget.provider_budget
        if (
            matrix.shape != (n, n)
            or not 0 < n <= cap.maximum_dimension
            or len(matrix.data) > cap.maximum_input_entries
            or matrix.data.dtype.name != "float64"
            or matrix.indices.dtype.kind not in "iu"
            or matrix.indptr.dtype.kind not in "iu"
            or len(matrix.indices) != len(matrix.data)
            or len(matrix.indptr) != n + 1
        ):
            raise LiveModalPipelineError("invalid or unbounded CSR storage")
        self._fee(1 + n + 2 * len(matrix.data))
        pointers = [int(x) for x in matrix.indptr]
        if (
            pointers[0] != 0
            or pointers[-1] != len(matrix.data)
            or any(
                a > b or a < 0 or b > len(matrix.data)
                for a, b in zip(pointers, pointers[1:])
            )
        ):
            raise LiveModalPipelineError("invalid CSR pointers")
        digest = hashlib.sha256(b"exact-binary64-CSR-storage.v1\0")
        digest.update(struct.pack("<QQ", n, len(matrix.data)))
        for p in pointers:
            digest.update(struct.pack("<Q", p))
        for i in range(n):
            for pos in range(pointers[i], pointers[i + 1]):
                j, value = int(matrix.indices[pos]), float(matrix.data[pos])
                if not 0 <= j < n or not math.isfinite(value):
                    raise LiveModalPipelineError("invalid CSR index/value")
                digest.update(struct.pack("<Qd", j, value))
        return "sha256:" + digest.hexdigest()

    def isolated(self, matrix):
        self._hash(matrix)
        result = matrix.copy()
        for a in (result.data, result.indices, result.indptr):
            a.flags.writeable = False
        return result

    def _sync(self, entry):
        now = entry["pencil"].statistics.inertia
        prior = entry["observed"]
        try:
            self.trial.absorb_native(now, prior)
        finally:
            entry["observed"] = now
        for name in (
            "peak_stored_entries_per_provider",
            "peak_stored_bits_per_provider",
            "peak_coefficient_bits",
        ):
            native_name = name.removesuffix("_per_provider")
            self.trial.values[name] = max(
                self.trial.values[name], getattr(now, native_name)
            )
        entries, bits = self._retained()
        self.trial.values["maximum_observed_retained_coefficient_entries"] = max(
            self.trial.values["maximum_observed_retained_coefficient_entries"], entries
        )
        self.trial.values["maximum_observed_retained_coefficient_bits"] = max(
            self.trial.values["maximum_observed_retained_coefficient_bits"], bits
        )

    def _retained(self):
        entries = bits = 0
        for entry in self.pairs.values():
            native = entry["pencil"].statistics.inertia
            entries += native.current_stored_entries
            bits += native.current_stored_bits
        for _, _, shift, _ in self.proofs:
            entries += bool(shift)
            bits += (
                abs(shift.numerator).bit_length() + shift.denominator.bit_length()
                if shift
                else 0
            )
        return entries, bits

    def _remaining(self, counter):
        return (
            getattr(self.trial.budget, _CAPS[counter][0]) - self.trial.values[counter]
        )

    def _provider_budget(self, requested, entry=None):
        defaults = self.trial.budget.provider_budget
        limits = {}
        for f in fields(defaults):
            limits[f.name] = min(getattr(defaults, f.name), getattr(requested, f.name))
        for name, counter in _PROVIDER_COUNTER.items():
            pending_constructor = (
                getattr(entry["observed"], counter)
                if entry and entry["returned"] is _ZERO
                else 0
            )
            limits[name] = min(
                limits[name], self._remaining(counter) + pending_constructor
            )
        used_entries, used_bits = self._retained()
        if entry:
            native = entry["pencil"].statistics.inertia
            used_entries -= native.current_stored_entries
            used_bits -= native.current_stored_bits
        limits["maximum_stored_entries"] = min(
            limits["maximum_stored_entries"],
            defaults.maximum_stored_entries - used_entries,
        )
        limits["maximum_total_stored_bits"] = min(
            limits["maximum_total_stored_bits"],
            defaults.maximum_total_stored_bits - used_bits,
        )
        if any(v <= 0 for v in limits.values()):
            self.trial.sealed = True
            raise LiveModalPipelineBudgetExceeded(
                "no remaining provider/storage budget", self.trial.stats()
            )
        return replace(defaults, **limits)

    def _entry(self, k, m, pair, requested):
        if pair in self.pairs:
            return self.pairs[pair]
        if len(self.pairs) >= 2:
            raise LiveModalPipelineError("maximum two live immutable pencils")
        kwargs = {
            name: max(1, self._remaining(counter))
            for counter, (name, _) in _CAPS.items()
        }
        self.trial.charge("constructor_attempts", 1)
        ctor_budget = self._provider_budget(requested)
        self.trial.charge("constructors", 1)
        try:
            pencil = SparseCachedIntervalPencil(
                k,
                m,
                budget=SparseCachedIntervalPencilBudget(
                    provider_budget=ctor_budget, **kwargs
                ),
            )
        except SparseInertiaError as error:
            if error.statistics:
                self.trial.absorb_native(error.statistics)
            if isinstance(error, SparseInertiaBudgetExceeded):
                self.trial.sealed = True
            raise
        entry = {"pencil": pencil, "observed": _ZERO, "returned": _ZERO}
        self.pairs[pair] = entry
        self._sync(entry)
        if (
            pencil.custody.stiffness_input_hash,
            pencil.custody.mass_input_hash,
        ) != pair:
            raise LiveModalPipelineError("constructor storage identity mismatch")
        return entry

    def _delta(self, entry=None):
        values = {k: 0 for k in _SUM}
        if entry:
            now = entry["pencil"].statistics.inertia
            for name in _SUM:
                values[name] = getattr(now, name) - getattr(entry["returned"], name)
            entry["returned"] = now
        values["work_units"] += self.pending_work
        self.pending_work = 0
        return replace(_ZERO, **values)

    def acquire(self, k, m, *, shift=Fraction(0), budget=None):
        self.check_owner()
        if self.closed or self.trial.sealed:
            raise LiveModalPipelineError("closed/sealed live proof session")
        small = type(shift) is Fraction and (
            abs(shift.numerator).bit_length() + shift.denominator.bit_length() <= 4096
        )
        event = {
            "request": self.trial.values["count_requests"] + 1,
            "status": "started",
            "shift": str(shift) if small else "<invalid shift>",
            "profile": PROFILE,
        }
        self.trial.events.append(event)
        hits = self.trial.values["proof_cache_hits"]
        try:
            self.trial.charge("count_requests", 1)
            self._fee(1)  # bounded metadata/lookup proxy, no new inertia credit
            result = self._acquire(k, m, shift=shift, budget=budget)
        except BaseException as error:
            event.update(
                status="refused",
                error_type=type(error).__name__,
                actual_provider_attempts=self.trial.values["provider_attempts"],
            )
            raise
        event.update(
            status="hit"
            if self.trial.values["proof_cache_hits"] > hits
            else "computed",
            pair=(result.stiffness_input_hash, result.mass_input_hash),
            actual_provider_attempts=self.trial.values["provider_attempts"],
        )
        return result

    def _acquire(self, k, m, *, shift=Fraction(0), budget=None):
        if self.closed or self.trial.sealed:
            raise LiveModalPipelineError("closed/sealed live proof session")
        if type(shift) is not Fraction or (
            abs(shift.numerator).bit_length() + shift.denominator.bit_length() > 4096
        ):
            raise LiveModalPipelineError("bounded exact Fraction shift required")
        if (
            SparseCachedIntervalPencil.count is not _COUNT_METHOD
            or CACHED_INTERVAL_PENCIL_PROFILE
            != "cached_source_bound_interval_pencil.v1"
        ):
            raise LiveModalPipelineError("native live provider/profile changed")
        pair = self._hash(k), self._hash(m)
        key = (*pair, shift, CACHED_INTERVAL_PENCIL_PROFILE)
        entry = self._entry(k, m, pair, budget or self.trial.budget.provider_budget)
        hit = key in self.proofs
        if hit:
            self.trial.charge("proof_cache_hits", 1)
            result = replace(
                self.proofs[key],
                statistics=self._delta(),
                cumulative_statistics=entry["pencil"].statistics,
            )
        else:
            if self._remaining("provider_attempts") <= 0:
                self.trial.values["prospective_provider_refusals"] += 1
                self.trial.sealed = True
                raise LiveModalPipelineBudgetExceeded(
                    "prospective provider refused before dispatch", self.trial.stats()
                )
            try:
                query_budget = self._provider_budget(
                    budget or self.trial.budget.provider_budget, entry
                )
            except LiveModalPipelineBudgetExceeded:
                self.trial.values["prospective_provider_refusals"] += 1
                raise
            self.trial.charge("provider_attempts", 1)
            try:
                result = entry["pencil"].count(shift, budget=query_budget)
            except SparseInertiaError as error:
                self._sync(entry)
                error.statistics = self._delta(entry)
                if isinstance(error, SparseInertiaBudgetExceeded):
                    self.trial.sealed = True
                raise
            self._sync(entry)
            self.trial.charge("provider_completed", 1)
            if (
                result.algorithm_profile != CACHED_INTERVAL_PENCIL_PROFILE
                or (result.stiffness_input_hash, result.mass_input_hash) != pair
                or result.negative + result.zero + result.positive != result.dimension
            ):
                raise LiveModalPipelineError("invalid completed count custody")
            # Cache key coefficients share retention caps with native originals/workspace.
            self._fee(1)
            entries, bits = self._retained()
            entries += bool(shift)
            bits += (
                (abs(shift.numerator).bit_length() + shift.denominator.bit_length())
                if shift
                else 0
            )
            cap = self.trial.budget.provider_budget
            if (
                entries > cap.maximum_stored_entries
                or bits > cap.maximum_total_stored_bits
            ):
                self.trial.sealed = True
                raise LiveModalPipelineBudgetExceeded(
                    "live proof key storage cap", self.trial.stats()
                )
            self.proofs[key] = result
            self.trial.values["maximum_observed_retained_coefficient_entries"] = max(
                self.trial.values["maximum_observed_retained_coefficient_entries"],
                entries,
            )
            self.trial.values["maximum_observed_retained_coefficient_bits"] = max(
                self.trial.values["maximum_observed_retained_coefficient_bits"], bits
            )
            result = replace(result, statistics=self._delta(entry))
        return result

    def certificate_totals(self):
        v, b = self.trial.values, self.baseline
        return dict(
            provider_call_attempts=v["provider_attempts"] - b["provider_attempts"],
            provider_calls_completed=v["provider_completed"] - b["provider_completed"],
            aggregate_input_entries=v["input_entries"] - b["input_entries"],
            aggregate_work_units=v["work_units"] - b["work_units"],
            aggregate_bit_operation_cost=v["bit_operation_cost"]
            - b["bit_operation_cost"],
            aggregate_pivots=v["pivot_attempts"] - b["pivot_attempts"],
            aggregate_inertia_calls=v["inertia_call_attempts"]
            - b["inertia_call_attempts"],
            aggregate_fraction_operation_attempts=v["fraction_operation_attempts"]
            - b["fraction_operation_attempts"],
            count_cache_hits=v["proof_cache_hits"] - b["proof_cache_hits"],
            # Maxima are cumulative high-water observations, not additive
            # delta costs. Retiring an admission pencil must not erase them.
            peak_stored_entries_per_provider=v["peak_stored_entries_per_provider"],
            peak_stored_bits_per_provider=v["peak_stored_bits_per_provider"],
            peak_coefficient_bits=v["peak_coefficient_bits"],
        )

    def mint(self, cert):
        comparisons = {
            "provider_call_attempts": "provider_attempts",
            "aggregate_input_entries": "input_entries",
            "aggregate_work_units": "work_units",
            "aggregate_bit_operation_cost": "bit_operation_cost",
            "aggregate_pivots": "pivot_attempts",
            "aggregate_inertia_calls": "inertia_call_attempts",
        }
        if any(
            getattr(cert.statistics, a) != self.trial.values[b] - self.baseline[b]
            for a, b in comparisons.items()
        ):
            raise LiveModalPipelineError(
                "certificate counters differ from live paid prefix"
            )
        self.minted = cert
        self.authentic_statistics = tuple(
            getattr(cert.statistics, f.name) for f in fields(cert.statistics)
        )

    def authentic(self, cert):
        self.check_owner()
        if cert is None or cert is not self.minted:
            raise LiveModalPipelineError(
                "certificate not minted by this live session or cost changed"
            )
        statistics = cert.statistics
        if self.authentic_statistics != tuple(
            getattr(statistics, f.name) for f in fields(statistics)
        ):
            raise LiveModalPipelineError(
                "certificate not minted by this live session or cost changed"
            )

    def subspace_totals(self):
        v, b = self.trial.values, self.baseline
        return dict(
            total_provider_calls=v["provider_attempts"] - b["provider_attempts"],
            total_work_units=v["work_units"] - b["work_units"],
            total_bit_operation_cost=v["bit_operation_cost"] - b["bit_operation_cost"],
            total_inertia_calls=v["inertia_call_attempts"] - b["inertia_call_attempts"],
        )

    def retire_pair(self, pair):
        """Close one paid pencil and release its keys without refunding work."""
        self.check_owner()
        entry = self.pairs[pair]
        for key in tuple(self.proofs):
            if key[:2] == pair:
                del self.proofs[key]
        try:
            entry["pencil"].close()
            self._sync(entry)
        finally:
            del self.pairs[pair]
            self.trial.charge("closes", 1)

    def close(self):
        if self.closed:
            return
        self.proofs.clear()
        errors = []
        try:
            for entry in self.pairs.values():
                try:
                    entry["pencil"].close()
                    self._sync(entry)
                except BaseException as error:
                    errors.append(error)
                finally:
                    self.trial.charge("closes", 1)
        finally:
            self.closed = True
        if errors:
            raise errors[0]  # all contexts already cleaned; no cost refund


class LiveModalProofPipeline:
    def __init__(self, *, budget=None):
        self._run_lock = threading.Lock()
        self._trial = _TrialLedger(
            budget if budget is not None else LiveModalPipelineBudget()
        )
        if type(self._trial.budget) is not LiveModalPipelineBudget:
            raise ValueError("LiveModalPipelineBudget required")

    @property
    def statistics(self):
        return self._trial.snapshot()

    @property
    def proof_events(self):
        return tuple(dict(event) for event in self._trial.events)

    def run(
        self,
        stiffness: Any,
        mass: Any,
        mode_count: int,
        *,
        rigid_mode_relative_tolerance: float | Fraction = 1e-10,
        cluster_relative_tolerance: float | Fraction = 1e-9,
        residual_relative_tolerance: float = 1e-9,
        orthogonality_tolerance: float = 1e-8,
        maximum_iterations: int | None = None,
        public_rigid_threshold: float | None = None,
        stiffness_psd_threshold: float | None = None,
        mass_spd_threshold: float | None = None,
        interval_relative_width: Fraction = Fraction(1, 1 << 40),
    ) -> LiveModalPipelineResult:
        """Produce selected complete space; caller numerical/export gates separate.

        The optional public threshold is an ACTUAL binary64 policy point,
        not an error enclosure for a largest-eigenvalue estimate. Iteration
        limits only tighten original thin budgets; there is no hidden restart.
        """
        if self._trial.sealed:
            raise LiveModalPipelineError(
                "trial sealed; no reset/refund",
                cumulative_cost=self.statistics,
                stage="admission",
            )
        if not self._run_lock.acquire(blocking=False):
            raise LiveModalPipelineError(
                "same pipeline instance run already active",
                cumulative_cost=self.statistics,
                stage="admission",
            )
        session = _LiveCountSession(_TOKEN, self._trial)
        stage = "options"
        guard = None
        stiffness_guard = mass_guard = None
        failure = None
        result = None
        cert = None
        try:
            if maximum_iterations is not None and (
                type(maximum_iterations) is not int or maximum_iterations <= 0
            ):
                raise LiveModalPipelineError(
                    "maximum_iterations must be a positive integer or None"
                )
            for value in (residual_relative_tolerance, orthogonality_tolerance):
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise LiveModalPipelineError(
                        "residual/orthogonality tolerances must be finite nonnegative numbers"
                    )
            if public_rigid_threshold is not None and (
                type(public_rigid_threshold) is not float
                or not math.isfinite(public_rigid_threshold)
                or public_rigid_threshold < 0
            ):
                raise LiveModalPipelineError(
                    "public_rigid_threshold must be finite nonnegative binary64 float"
                )
            for name, point_value, valid_sign in (
                ("stiffness_psd_threshold", stiffness_psd_threshold, "nonpositive"),
                ("mass_spd_threshold", mass_spd_threshold, "nonnegative"),
            ):
                if point_value is not None and (
                    type(point_value) is not float
                    or not math.isfinite(point_value)
                    or (
                        point_value > 0
                        if valid_sign == "nonpositive"
                        else point_value < 0
                    )
                ):
                    raise LiveModalPipelineError(
                        f"{name} must be finite {valid_sign} binary64 float"
                    )
            stage = "source_setup"
            k, m = session.isolated(stiffness), session.isolated(mass)
            pair = session._hash(k), session._hash(m)
            identity = None
            if stiffness_psd_threshold is not None or mass_spd_threshold is not None:
                identity = session.isolated(eye(k.shape[0], format="csr", dtype=float))
            for role, threshold, matrix in (
                ("stiffness_psd", stiffness_psd_threshold, k),
                ("mass_spd", mass_spd_threshold, m),
            ):
                if threshold is None:
                    continue
                assert identity is not None
                stage = role + "_guard"
                policy_pair = session._hash(matrix), session._hash(identity)
                point = Fraction.from_float(threshold)
                count = session.acquire(
                    matrix,
                    identity,
                    shift=point,
                    budget=self._trial.budget.provider_budget,
                )
                if (
                    count.stiffness_input_hash,
                    count.mass_input_hash,
                ) != policy_pair or count.dimension != k.shape[0]:
                    raise LiveModalPipelineError(
                        "matrix policy count source/dimension mismatch"
                    )
                if count.negative or (role == "mass_spd" and count.zero):
                    raise LiveModalPipelineError(
                        role + " all-direction policy rejected"
                    )
                policy_guard = PublicMatrixPolicyGuard(
                    threshold,
                    point,
                    count.dimension,
                    count.negative,
                    count.zero,
                    count.less_than_or_equal_to_shift,
                    count.stiffness_input_hash,
                    count.mass_input_hash,
                    count.algorithm_profile,
                    role,
                )
                if role == "stiffness_psd":
                    stiffness_guard = policy_guard
                    session.retire_pair(policy_pair)
                else:
                    mass_guard = policy_guard
            main = session._entry(k, m, pair, self._trial.budget.provider_budget)
            hint = main["pencil"].exact_mass_lower_bound_hint or Fraction(1)
            remaining = {
                name: max(
                    1, getattr(self._trial.budget, name) - session.baseline[counter]
                )
                for counter, (name, _) in _CAPS.items()
            }
            stage = "certificate"
            cert = certificate.certify_sparse_modal_spectrum(
                k,
                m,
                mode_count=mode_count,
                rigid_mode_relative_tolerance=rigid_mode_relative_tolerance,
                cluster_relative_tolerance=cluster_relative_tolerance,
                interval_relative_width=interval_relative_width,
                mass_lower_bound_hint=hint,
                budget=certificate.SparseModalCertificateBudget(
                    provider_budget=self._trial.budget.provider_budget, **remaining
                ),
                _live_session=session,
            )
            if public_rigid_threshold is not None:
                stage = "public_threshold_guard"
                point = Fraction.from_float(public_rigid_threshold)
                count = session.acquire(
                    k, m, shift=point, budget=self._trial.budget.provider_budget
                )
                if (
                    count.stiffness_input_hash,
                    count.mass_input_hash,
                ) != pair or count.dimension != cert.dimension:
                    raise LiveModalPipelineError(
                        "public threshold count source/dimension mismatch"
                    )
                if count.less_than_or_equal_to_shift != cert.rigid_mode_count:
                    raise LiveModalPipelineError(
                        "public rounded threshold prefix differs from certified rigid prefix"
                    )
                guard = PublicRigidThresholdGuard(
                    public_rigid_threshold,
                    point,
                    count.dimension,
                    count.negative,
                    count.zero,
                    count.less_than_or_equal_to_shift,
                    count.stiffness_input_hash,
                    count.mass_input_hash,
                    count.algorithm_profile,
                )
            # Mint exactly the already-paid whole prefix, including admission
            # and rounded-policy points. This is not an extra trial charge.
            cert = replace(
                cert,
                statistics=replace(cert.statistics, **session.certificate_totals()),
            )
            session.mint(cert)
            totals = session.subspace_totals()
            caps = self._trial.budget
            default = subspace.SparseModalSubspaceBudget()
            iterations = (
                default.maximum_total_iterations
                if maximum_iterations is None
                else min(maximum_iterations, default.maximum_total_iterations)
            )
            per_block = (
                default.maximum_iterations_per_block
                if maximum_iterations is None
                else min(maximum_iterations, default.maximum_iterations_per_block)
            )
            stage = "extraction"
            result = subspace.extract_certified_sparse_modal_subspace(
                k,
                m,
                cert,
                rigid_mode_relative_tolerance=rigid_mode_relative_tolerance,
                residual_relative_tolerance=residual_relative_tolerance,
                orthogonality_tolerance=orthogonality_tolerance,
                budget=subspace.SparseModalSubspaceBudget(
                    provider_budget=caps.provider_budget,
                    maximum_total_iterations=iterations,
                    maximum_iterations_per_block=per_block,
                    maximum_total_provider_calls=session._remaining("provider_attempts")
                    + totals["total_provider_calls"],
                    maximum_total_work_units=session._remaining("work_units")
                    + totals["total_work_units"],
                    maximum_total_bit_operation_cost=session._remaining(
                        "bit_operation_cost"
                    )
                    + totals["total_bit_operation_cost"],
                    maximum_total_inertia_calls=session._remaining(
                        "inertia_call_attempts"
                    )
                    + totals["total_inertia_calls"],
                ),
                _live_session=session,
            )
        except BaseException as error:
            failure = error
            if isinstance(
                error,
                (
                    SparseInertiaBudgetExceeded,
                    certificate.SparseModalCertificateBudgetExceeded,
                    subspace.SparseModalSubspaceBudgetExceeded,
                ),
            ):
                self._trial.sealed = True
        finally:
            try:
                session.close()
            except BaseException as close_error:
                if failure is None:
                    failure = close_error
                    stage = "cleanup"
            finally:
                self._run_lock.release()
        if failure is not None:
            if not isinstance(failure, Exception):
                raise failure
            error_type = (
                LiveModalPipelineBudgetExceeded
                if isinstance(
                    failure,
                    (
                        SparseInertiaBudgetExceeded,
                        certificate.SparseModalCertificateBudgetExceeded,
                        subspace.SparseModalSubspaceBudgetExceeded,
                    ),
                )
                else LiveModalPipelineError
            )
            raise error_type(
                f"live modal pipeline {stage} refused: {failure}",
                getattr(failure, "statistics", None),
                cumulative_cost=self.statistics,
                stage=stage,
                certificate=cert,
                public_threshold_guard=guard,
                stiffness_psd_guard=stiffness_guard,
                mass_spd_guard=mass_guard,
            ) from failure
        assert cert is not None and result is not None
        return LiveModalPipelineResult(
            cert, result, self.statistics, guard, stiffness_guard, mass_guard
        )
