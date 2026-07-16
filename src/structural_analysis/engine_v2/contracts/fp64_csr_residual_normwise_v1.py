"""Normwise projection of the FP64 CSR componentwise residual contract.

The v1 roundoff receipt proves ``|delta_r_i| <= B_i``.  This additive
contract projects that proof through the reverse triangle inequality to
``L2``, ``Linf`` and solver ``scaled-Linf`` metrics.  It accepts no caller
tolerance and does not alter the componentwise v1 wire contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.fp64_csr_residual_roundoff_v1 import (
    Fp64CsrResidualRoundoffResultV1,
    validate_fp64_csr_residual_roundoff_result_v1,
)


FP64_CSR_RESIDUAL_NORMWISE_SCHEMA_VERSION_V1 = (
    "structural-analysis-fp64-csr-residual-normwise.v1"
)
FP64_CSR_RESIDUAL_NORMWISE_CAPABILITY_PROFILE_V1 = (
    "phase0_fp64_csr_residual_normwise_projection"
)
FP64_CSR_RESIDUAL_NORMWISE_EVIDENCE_SCOPE_V1 = (
    "backend_neutral_normwise_value_contract_non_promoting"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_RESOURCE = "fp64_csr_residual_normwise_v1.schema.json"
_METRIC_NAMES = ("l2", "linf", "scaled_linf")


class Fp64CsrResidualNormwiseV1Error(ValueError):
    """Stable fail-closed error for normwise residual projection."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseBindingsV1:
    componentwise_comparison_id: str
    componentwise_receipt_hash: str
    execution_plan_hash: str
    operator_hash: str
    reference_residual_sha256: str
    candidate_residual_sha256: str
    componentwise_bound_sha256: str
    metric_projection_hash: str

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseIntervalV1:
    lower: float
    upper: float

    def to_dict(self) -> dict[str, float]:
        return {"lower": self.lower, "upper": self.upper}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseMetricV1:
    name: Literal["l2", "linf", "scaled_linf"]
    reference_interval: Fp64CsrResidualNormwiseIntervalV1
    candidate_interval: Fp64CsrResidualNormwiseIntervalV1
    vector_difference_upper_bound: float
    interval_gap_lower_bound: float
    interval_envelope_gap_upper_bound: float
    reverse_triangle_bound_verified: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reference_interval": self.reference_interval.to_dict(),
            "candidate_interval": self.candidate_interval.to_dict(),
            "vector_difference_upper_bound": self.vector_difference_upper_bound,
            "interval_gap_lower_bound": self.interval_gap_lower_bound,
            "interval_envelope_gap_upper_bound": (
                self.interval_envelope_gap_upper_bound
            ),
            "reverse_triangle_bound_verified": (self.reverse_triangle_bound_verified),
        }


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseSummaryV1:
    row_count: int
    rhs_linf: float
    load_scale: float
    metric_count: Literal[3]
    all_reverse_triangle_bounds_verified: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseCompatibilityV1:
    source_componentwise_schema_version: Literal[
        "structural-analysis-fp64-csr-residual-roundoff.v1"
    ] = "structural-analysis-fp64-csr-residual-roundoff.v1"
    source_wire_receipt_mutated: Literal[False] = False
    migration_action: Literal["preserve_v1_and_issue_additive_normwise_v1"] = (
        "preserve_v1_and_issue_additive_normwise_v1"
    )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseClaimsV1:
    componentwise_receipt_fully_replayed: Literal[True] = True
    reverse_triangle_l2_verified: Literal[True] = True
    reverse_triangle_linf_verified: Literal[True] = True
    reverse_triangle_scaled_linf_verified: Literal[True] = True
    outward_interval_arithmetic_verified: Literal[True] = True
    caller_tolerance_allowed: Literal[False] = False
    legacy_wire_contract_changed: Literal[False] = False
    actual_backend_verified: Literal[False] = False
    terminal_record_metric_verified: Literal[False] = False
    history_metric_verified: Literal[False] = False
    performance_speedup_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualNormwiseReceiptV1:
    schema_version: str
    capability_profile: str
    status: Literal["normwise_projection_verified"]
    evidence_scope: str
    promotion_eligible: Literal[False]
    projection_id: str
    bindings: Fp64CsrResidualNormwiseBindingsV1
    metrics: tuple[Fp64CsrResidualNormwiseMetricV1, ...]
    summary: Fp64CsrResidualNormwiseSummaryV1
    compatibility: Fp64CsrResidualNormwiseCompatibilityV1
    claims: Fp64CsrResidualNormwiseClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_fp64_csr_residual_normwise_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class Fp64CsrResidualNormwiseResultV1:
    receipt: Fp64CsrResidualNormwiseReceiptV1
    _componentwise_result: Fp64CsrResidualRoundoffResultV1 = dataclass_field(
        repr=False,
        compare=False,
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_fp64_csr_residual_normwise_result_v1(self)
        return self.receipt.to_dict()


def attest_fp64_csr_residual_normwise_v1(
    componentwise_result: Fp64CsrResidualRoundoffResultV1,
) -> Fp64CsrResidualNormwiseResultV1:
    """Project a fully replayed componentwise receipt to three norm budgets."""

    validate_fp64_csr_residual_roundoff_result_v1(componentwise_result)
    receipt = _evaluate(componentwise_result)
    result = Fp64CsrResidualNormwiseResultV1(
        receipt=receipt,
        _componentwise_result=componentwise_result,
    )
    return validate_fp64_csr_residual_normwise_result_v1(
        result,
        expected_componentwise_result=componentwise_result,
    )


def validate_fp64_csr_residual_normwise_receipt_v1(
    receipt: Fp64CsrResidualNormwiseReceiptV1,
) -> Fp64CsrResidualNormwiseReceiptV1:
    """Validate the strict serialized projection without provenance claims."""

    if type(receipt) is not Fp64CsrResidualNormwiseReceiptV1:
        _fail("fp64_csr_residual_normwise_receipt_type_invalid", "/")
    if (
        type(receipt.bindings) is not Fp64CsrResidualNormwiseBindingsV1
        or type(receipt.summary) is not Fp64CsrResidualNormwiseSummaryV1
        or type(receipt.compatibility) is not Fp64CsrResidualNormwiseCompatibilityV1
        or type(receipt.claims) is not Fp64CsrResidualNormwiseClaimsV1
        or type(receipt.metrics) is not tuple
        or any(
            type(row) is not Fp64CsrResidualNormwiseMetricV1 for row in receipt.metrics
        )
    ):
        _fail("fp64_csr_residual_normwise_nested_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("fp64_csr_residual_normwise_schema_invalid", path, error.message)
    if (
        receipt.schema_version != FP64_CSR_RESIDUAL_NORMWISE_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != FP64_CSR_RESIDUAL_NORMWISE_CAPABILITY_PROFILE_V1
        or receipt.status != "normwise_projection_verified"
        or receipt.evidence_scope != FP64_CSR_RESIDUAL_NORMWISE_EVIDENCE_SCOPE_V1
        or receipt.promotion_eligible is not False
        or receipt.compatibility != Fp64CsrResidualNormwiseCompatibilityV1()
        or receipt.claims != Fp64CsrResidualNormwiseClaimsV1()
    ):
        _fail("fp64_csr_residual_normwise_semantics_invalid", "/")
    _validate_bindings(receipt.bindings)
    _validate_summary(receipt.summary)
    if tuple(row.name for row in receipt.metrics) != _METRIC_NAMES:
        _fail("fp64_csr_residual_normwise_metric_order_invalid", "/metrics")
    for index, row in enumerate(receipt.metrics):
        _validate_metric(row, f"/metrics/{index}")
    expected_projection_hash = canonical_hash(
        [row.to_dict() for row in receipt.metrics]
    )
    if receipt.bindings.metric_projection_hash != expected_projection_hash:
        _fail(
            "fp64_csr_residual_normwise_projection_hash_invalid",
            "/bindings/metric_projection_hash",
        )
    expected_id = canonical_hash(
        {
            "profile": FP64_CSR_RESIDUAL_NORMWISE_CAPABILITY_PROFILE_V1,
            "componentwise_receipt_hash": receipt.bindings.componentwise_receipt_hash,
            "metric_projection_hash": receipt.bindings.metric_projection_hash,
        }
    )
    if receipt.projection_id != expected_id:
        _fail("fp64_csr_residual_normwise_projection_id_invalid", "/projection_id")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if (
        _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != expected_hash
    ):
        _fail("fp64_csr_residual_normwise_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_fp64_csr_residual_normwise_result_v1(
    result: Fp64CsrResidualNormwiseResultV1,
    *,
    expected_componentwise_result: Fp64CsrResidualRoundoffResultV1 | None = None,
) -> Fp64CsrResidualNormwiseResultV1:
    """Replay the componentwise source and the complete normwise projection."""

    if type(result) is not Fp64CsrResidualNormwiseResultV1:
        _fail("fp64_csr_residual_normwise_result_type_invalid", "/")
    validate_fp64_csr_residual_normwise_receipt_v1(result.receipt)
    if type(result._componentwise_result) is not Fp64CsrResidualRoundoffResultV1:
        _fail("fp64_csr_residual_normwise_source_type_invalid", "/source")
    if (
        expected_componentwise_result is not None
        and result._componentwise_result is not expected_componentwise_result
    ):
        _fail("fp64_csr_residual_normwise_source_identity_mismatch", "/source")
    validate_fp64_csr_residual_roundoff_result_v1(result._componentwise_result)
    if _evaluate(result._componentwise_result) != result.receipt:
        _fail("fp64_csr_residual_normwise_replay_mismatch", "/")
    return result


def _evaluate(
    componentwise: Fp64CsrResidualRoundoffResultV1,
) -> Fp64CsrResidualNormwiseReceiptV1:
    source = componentwise.receipt
    plan = componentwise._execution_plan
    reference = componentwise._reference_residual
    candidate = componentwise._candidate_residual
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    rhs_linf = _linf_exact(rhs)
    load_scale = max(1.0, rhs_linf)
    reference_intervals = _metric_intervals(reference, load_scale, "/reference")
    candidate_intervals = _metric_intervals(candidate, load_scale, "/candidate")
    vector_bounds = (
        source.summary.componentwise_bound_l2,
        source.summary.componentwise_bound_linf,
        _div_up(
            source.summary.componentwise_bound_linf,
            load_scale,
            "/metrics/scaled_linf/vector_difference_upper_bound",
        ),
    )
    metrics = tuple(
        _metric(
            name,
            reference_interval,
            candidate_interval,
            vector_bound,
            f"/metrics/{index}",
        )
        for index, (
            name,
            reference_interval,
            candidate_interval,
            vector_bound,
        ) in enumerate(
            zip(
                _METRIC_NAMES,
                reference_intervals,
                candidate_intervals,
                vector_bounds,
                strict=True,
            )
        )
    )
    metric_hash = canonical_hash([row.to_dict() for row in metrics])
    bindings = Fp64CsrResidualNormwiseBindingsV1(
        componentwise_comparison_id=source.comparison_id,
        componentwise_receipt_hash=source.receipt_hash,
        execution_plan_hash=source.bindings.execution_plan_hash,
        operator_hash=source.bindings.operator_hash,
        reference_residual_sha256=source.bindings.reference_residual_sha256,
        candidate_residual_sha256=source.bindings.candidate_residual_sha256,
        componentwise_bound_sha256=source.bindings.componentwise_bound_sha256,
        metric_projection_hash=metric_hash,
    )
    projection_id = canonical_hash(
        {
            "profile": FP64_CSR_RESIDUAL_NORMWISE_CAPABILITY_PROFILE_V1,
            "componentwise_receipt_hash": bindings.componentwise_receipt_hash,
            "metric_projection_hash": bindings.metric_projection_hash,
        }
    )
    draft = Fp64CsrResidualNormwiseReceiptV1(
        schema_version=FP64_CSR_RESIDUAL_NORMWISE_SCHEMA_VERSION_V1,
        capability_profile=FP64_CSR_RESIDUAL_NORMWISE_CAPABILITY_PROFILE_V1,
        status="normwise_projection_verified",
        evidence_scope=FP64_CSR_RESIDUAL_NORMWISE_EVIDENCE_SCOPE_V1,
        promotion_eligible=False,
        projection_id=projection_id,
        bindings=bindings,
        metrics=metrics,
        summary=Fp64CsrResidualNormwiseSummaryV1(
            row_count=int(reference.size),
            rhs_linf=rhs_linf,
            load_scale=load_scale,
            metric_count=3,
            all_reverse_triangle_bounds_verified=True,
        ),
        compatibility=Fp64CsrResidualNormwiseCompatibilityV1(),
        claims=Fp64CsrResidualNormwiseClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_fp64_csr_residual_normwise_receipt_v1(receipt)


def _metric(
    name: str,
    reference: Fp64CsrResidualNormwiseIntervalV1,
    candidate: Fp64CsrResidualNormwiseIntervalV1,
    vector_bound: float,
    path: str,
) -> Fp64CsrResidualNormwiseMetricV1:
    gap_lower = _interval_gap_lower(reference, candidate, f"{path}/gap")
    envelope_upper = _interval_envelope_gap_upper(
        reference,
        candidate,
        f"{path}/envelope",
    )
    if gap_lower > vector_bound:
        _fail(
            "fp64_csr_residual_normwise_reverse_triangle_mismatch",
            path,
            f"interval_gap_lower={gap_lower!r} bound={vector_bound!r}",
        )
    return Fp64CsrResidualNormwiseMetricV1(
        name=name,  # type: ignore[arg-type]
        reference_interval=reference,
        candidate_interval=candidate,
        vector_difference_upper_bound=vector_bound,
        interval_gap_lower_bound=gap_lower,
        interval_envelope_gap_upper_bound=envelope_upper,
        reverse_triangle_bound_verified=True,
    )


def _metric_intervals(
    vector: np.ndarray,
    load_scale: float,
    path: str,
) -> tuple[Fp64CsrResidualNormwiseIntervalV1, ...]:
    l2 = _l2_interval(vector, f"{path}/l2")
    linf = _linf_exact(vector)
    linf_interval = Fp64CsrResidualNormwiseIntervalV1(linf, linf)
    scaled = Fp64CsrResidualNormwiseIntervalV1(
        _div_down(linf, load_scale, f"{path}/scaled_linf/lower"),
        _div_up(linf, load_scale, f"{path}/scaled_linf/upper"),
    )
    return l2, linf_interval, scaled


def _l2_interval(
    vector: np.ndarray,
    path: str,
) -> Fp64CsrResidualNormwiseIntervalV1:
    lower = 0.0
    upper = 0.0
    for index, raw in enumerate(vector):
        value = abs(float(raw))
        if not math.isfinite(value):
            _fail("fp64_csr_residual_normwise_nonfinite_operand", f"{path}/{index}")
        lower_square = _mul_down(value, value, f"{path}/{index}/square_lower")
        upper_square = _mul_up(value, value, f"{path}/{index}/square_upper")
        lower = _add_down(lower, lower_square, f"{path}/{index}/sum_lower")
        upper = _add_up(upper, upper_square, f"{path}/{index}/sum_upper")
    lower_root = math.sqrt(lower)
    upper_root = math.sqrt(upper)
    if not math.isfinite(lower_root) or not math.isfinite(upper_root):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    return Fp64CsrResidualNormwiseIntervalV1(
        _next_down_nonnegative(lower_root, f"{path}/lower"),
        _next_up_nonnegative(upper_root, f"{path}/upper"),
    )


def _linf_exact(vector: np.ndarray) -> float:
    maximum = max((abs(float(value)) for value in vector), default=0.0)
    if not math.isfinite(maximum):
        _fail("fp64_csr_residual_normwise_nonfinite_operand", "/linf")
    return maximum


def _interval_gap_lower(
    left: Fp64CsrResidualNormwiseIntervalV1,
    right: Fp64CsrResidualNormwiseIntervalV1,
    path: str,
) -> float:
    if left.upper < right.lower:
        return _sub_down(right.lower, left.upper, path)
    if right.upper < left.lower:
        return _sub_down(left.lower, right.upper, path)
    return 0.0


def _interval_envelope_gap_upper(
    left: Fp64CsrResidualNormwiseIntervalV1,
    right: Fp64CsrResidualNormwiseIntervalV1,
    path: str,
) -> float:
    value = max(
        abs(left.lower - right.upper),
        abs(left.upper - right.lower),
    )
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _add_down(left: float, right: float, path: str) -> float:
    value = left + right
    if not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    return _next_down_nonnegative(value, path)


def _add_up(left: float, right: float, path: str) -> float:
    value = left + right
    if not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    return _next_up_nonnegative(value, path)


def _mul_down(left: float, right: float, path: str) -> float:
    value = left * right
    if not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    return _next_down_nonnegative(value, path)


def _mul_up(left: float, right: float, path: str) -> float:
    if left < 0.0 or right < 0.0:
        _fail("fp64_csr_residual_normwise_bound_invalid", path)
    value = left * right
    if not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    if value == 0.0 and left != 0.0 and right != 0.0:
        return float.fromhex("0x0.0000000000001p-1022")
    return _next_up_nonnegative(value, path)


def _div_down(numerator: float, denominator: float, path: str) -> float:
    if denominator <= 0.0:
        _fail("fp64_csr_residual_normwise_zero_denominator", path)
    value = numerator / denominator
    if not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    return _next_down_nonnegative(value, path)


def _div_up(numerator: float, denominator: float, path: str) -> float:
    if numerator < 0.0 or denominator <= 0.0:
        _fail("fp64_csr_residual_normwise_zero_denominator", path)
    value = numerator / denominator
    if not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    if value == 0.0 and numerator != 0.0:
        return float.fromhex("0x0.0000000000001p-1022")
    return _next_up_nonnegative(value, path)


def _sub_down(high: float, low: float, path: str) -> float:
    value = high - low
    if not math.isfinite(value) or value < 0.0:
        _fail("fp64_csr_residual_normwise_bound_invalid", path)
    return _next_down_nonnegative(value, path)


def _next_down_nonnegative(value: float, path: str) -> float:
    if value < 0.0 or not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_invalid", path)
    if value == 0.0:
        return 0.0
    return max(0.0, math.nextafter(value, -math.inf))


def _next_up_nonnegative(value: float, path: str) -> float:
    if value < 0.0 or not math.isfinite(value):
        _fail("fp64_csr_residual_normwise_bound_invalid", path)
    if value == 0.0:
        return 0.0
    outward = math.nextafter(value, math.inf)
    if not math.isfinite(outward):
        _fail("fp64_csr_residual_normwise_bound_overflow", path)
    return outward


def _validate_bindings(bindings: Fp64CsrResidualNormwiseBindingsV1) -> None:
    for name in bindings.__dataclass_fields__:
        value = getattr(bindings, name)
        if type(value) is not str or _HASH_RE.fullmatch(value) is None:
            _fail(
                "fp64_csr_residual_normwise_binding_hash_invalid", f"/bindings/{name}"
            )


def _validate_interval(
    interval: Fp64CsrResidualNormwiseIntervalV1,
    path: str,
) -> None:
    if type(interval) is not Fp64CsrResidualNormwiseIntervalV1:
        _fail("fp64_csr_residual_normwise_interval_type_invalid", path)
    if (
        any(
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
            for value in (interval.lower, interval.upper)
        )
        or interval.lower > interval.upper
    ):
        _fail("fp64_csr_residual_normwise_interval_invalid", path)


def _validate_metric(row: Fp64CsrResidualNormwiseMetricV1, path: str) -> None:
    _validate_interval(row.reference_interval, f"{path}/reference_interval")
    _validate_interval(row.candidate_interval, f"{path}/candidate_interval")
    values = (
        row.vector_difference_upper_bound,
        row.interval_gap_lower_bound,
        row.interval_envelope_gap_upper_bound,
    )
    if (
        any(
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
            for value in values
        )
        or row.reverse_triangle_bound_verified is not True
    ):
        _fail("fp64_csr_residual_normwise_metric_invalid", path)
    if row.interval_gap_lower_bound > row.vector_difference_upper_bound:
        _fail("fp64_csr_residual_normwise_metric_bound_invalid", path)


def _validate_summary(summary: Fp64CsrResidualNormwiseSummaryV1) -> None:
    if (
        type(summary.row_count) is not int
        or summary.row_count <= 0
        or type(summary.metric_count) is not int
        or summary.metric_count != 3
        or summary.all_reverse_triangle_bounds_verified is not True
    ):
        _fail("fp64_csr_residual_normwise_summary_invalid", "/summary")
    for name in ("rhs_linf", "load_scale"):
        value = getattr(summary, name)
        if (
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        ):
            _fail("fp64_csr_residual_normwise_summary_invalid", f"/summary/{name}")
    if summary.load_scale != max(1.0, summary.rhs_linf):
        _fail("fp64_csr_residual_normwise_load_scale_invalid", "/summary/load_scale")


def _receipt_payload(
    receipt: Fp64CsrResidualNormwiseReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "projection_id": receipt.projection_id,
        "bindings": receipt.bindings.to_dict(),
        "metrics": [row.to_dict() for row in receipt.metrics],
        "summary": receipt.summary.to_dict(),
        "compatibility": receipt.compatibility.to_dict(),
        "claims": receipt.claims.to_dict(),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise Fp64CsrResidualNormwiseV1Error(code, path, message)


__all__ = [
    "FP64_CSR_RESIDUAL_NORMWISE_CAPABILITY_PROFILE_V1",
    "FP64_CSR_RESIDUAL_NORMWISE_EVIDENCE_SCOPE_V1",
    "FP64_CSR_RESIDUAL_NORMWISE_SCHEMA_VERSION_V1",
    "Fp64CsrResidualNormwiseBindingsV1",
    "Fp64CsrResidualNormwiseClaimsV1",
    "Fp64CsrResidualNormwiseCompatibilityV1",
    "Fp64CsrResidualNormwiseIntervalV1",
    "Fp64CsrResidualNormwiseMetricV1",
    "Fp64CsrResidualNormwiseReceiptV1",
    "Fp64CsrResidualNormwiseResultV1",
    "Fp64CsrResidualNormwiseSummaryV1",
    "Fp64CsrResidualNormwiseV1Error",
    "attest_fp64_csr_residual_normwise_v1",
    "validate_fp64_csr_residual_normwise_receipt_v1",
    "validate_fp64_csr_residual_normwise_result_v1",
]
