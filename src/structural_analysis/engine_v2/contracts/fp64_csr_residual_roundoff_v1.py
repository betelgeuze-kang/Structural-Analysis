"""Scale-aware FP64 CSR residual roundoff and backward-error contract.

This module compares two represented residual vectors without a user-selected
absolute tolerance.  For each reduced CSR row it bounds

``|r_candidate - r_reference|``

by the exact-solution transport envelope ``|A| |x_candidate-x_reference|``
plus a conservative binary64 error budget for each residual evaluation path.
Every non-negative bound operation is rounded outward with ``nextafter``.

The contract is backend-neutral and deliberately non-promoting.  A higher
level receipt must bind the supplied arrays to an actual CPU or HIP execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, replace
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)


FP64_CSR_RESIDUAL_ROUNDOFF_SCHEMA_VERSION_V1 = (
    "structural-analysis-fp64-csr-residual-roundoff.v1"
)
FP64_CSR_RESIDUAL_ROUNDOFF_CAPABILITY_PROFILE_V1 = (
    "phase0_sparse_fp64_residual_roundoff_backward_error"
)
FP64_CSR_RESIDUAL_ROUNDOFF_EVIDENCE_SCOPE_V1 = (
    "backend_neutral_value_contract_non_promoting"
)
FP64_BINARY64_UNIT_ROUNDOFF_V1 = 2.0**-53
FP64_BINARY64_SMALLEST_SUBNORMAL_V1 = float.fromhex("0x0.0000000000001p-1022")

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLAN_ID_RE = re.compile(r"^SparsePlan:[0-9a-f]{24}$")
_SCHEMA_RESOURCE = "fp64_csr_residual_roundoff_v1.schema.json"
_POSITIVE_INFINITY = math.inf


class Fp64CsrResidualRoundoffV1Error(ValueError):
    """Stable fail-closed error for the residual roundoff contract."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualRoundoffBindingsV1:
    execution_plan_id: str
    execution_plan_hash: str
    operator_hash: str
    numeric_snapshot_hash: str
    partition_hash: str
    load_pattern_id: str
    reference_solution_sha256: str
    candidate_solution_sha256: str
    reference_residual_sha256: str
    candidate_residual_sha256: str
    componentwise_bound_sha256: str
    solution_transport_bound_sha256: str
    reference_roundoff_bound_sha256: str
    candidate_roundoff_bound_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualRoundoffArithmeticModelV1:
    binary64_unit_roundoff: float = FP64_BINARY64_UNIT_ROUNDOFF_V1
    binary64_smallest_subnormal: float = FP64_BINARY64_SMALLEST_SUBNORMAL_V1
    operation_count_rule: Literal["k_i=2*row_nnz_i+1"] = "k_i=2*row_nnz_i+1"
    roundoff_rule: Literal["gamma(k_i)*(abs(b_i)+sum_abs_aij_xj)+k_i*eta"] = (
        "gamma(k_i)*(abs(b_i)+sum_abs_aij_xj)+k_i*eta"
    )
    comparison_rule: Literal[
        "abs(delta_r_i)<=sum_abs_aij_delta_xj+roundoff_ref_i+roundoff_candidate_i"
    ] = "abs(delta_r_i)<=sum_abs_aij_delta_xj+roundoff_ref_i+roundoff_candidate_i"
    outward_rounding_rule: Literal[
        "nextafter_positive_infinity_after_each_nonnegative_bound_operation"
    ] = "nextafter_positive_infinity_after_each_nonnegative_bound_operation"
    caller_tolerance_allowed: Literal[False] = False
    dense_matrix_materialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualRoundoffSummaryV1:
    row_count: int
    reduced_csr_nnz: int
    maximum_row_nnz: int
    same_solution_bytes: bool
    maximum_absolute_difference_upper_bound: float
    difference_l2_upper_bound: float
    componentwise_bound_linf: float
    componentwise_bound_l2: float
    maximum_solution_transport_bound: float
    maximum_reference_roundoff_bound: float
    maximum_candidate_roundoff_bound: float
    maximum_componentwise_bound_ratio: float
    reference_componentwise_backward_error: float
    candidate_componentwise_backward_error: float
    positive_bound_row_count: int
    zero_bound_exact_match_row_count: int
    componentwise_bound_passed: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualRoundoffClaimsV1:
    componentwise_roundoff_bound_verified: Literal[True] = True
    solution_transport_bound_included: Literal[True] = True
    no_user_absolute_tolerance_floor: Literal[True] = True
    bound_formula_positive_homogeneous_above_subnormal_range: Literal[True] = True
    subnormal_absolute_guard_included: Literal[True] = True
    sparse_o_nnz_plus_n_work_bound: Literal[True] = True
    dense_matrix_materialized: Literal[False] = False
    actual_backend_verified: Literal[False] = False
    hardware_provenance_verified: Literal[False] = False
    end_to_end_o_n_verified: Literal[False] = False
    performance_speedup_verified: Literal[False] = False
    signed_evidence: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class Fp64CsrResidualRoundoffReceiptV1:
    schema_version: str
    capability_profile: str
    status: Literal["roundoff_bound_verified"]
    evidence_scope: str
    promotion_eligible: Literal[False]
    comparison_id: str
    bindings: Fp64CsrResidualRoundoffBindingsV1
    arithmetic_model: Fp64CsrResidualRoundoffArithmeticModelV1
    summary: Fp64CsrResidualRoundoffSummaryV1
    claims: Fp64CsrResidualRoundoffClaimsV1
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_fp64_csr_residual_roundoff_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class Fp64CsrResidualRoundoffResultV1:
    receipt: Fp64CsrResidualRoundoffReceiptV1
    _execution_plan: ExecutionPlanV2 = dataclass_field(repr=False, compare=False)
    _reference_solution: np.ndarray = dataclass_field(repr=False, compare=False)
    _candidate_solution: np.ndarray = dataclass_field(repr=False, compare=False)
    _reference_residual: np.ndarray = dataclass_field(repr=False, compare=False)
    _candidate_residual: np.ndarray = dataclass_field(repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        validate_fp64_csr_residual_roundoff_result_v1(self)
        return self.receipt.to_dict()


@dataclass(frozen=True, slots=True)
class _ComputedBoundsV1:
    componentwise: np.ndarray
    transport: np.ndarray
    reference_roundoff: np.ndarray
    candidate_roundoff: np.ndarray
    reference_scale: np.ndarray
    candidate_scale: np.ndarray
    difference_upper: np.ndarray
    maximum_row_nnz: int


def attest_fp64_csr_residual_roundoff_v1(
    execution_plan: ExecutionPlanV2,
    reference_solution: np.ndarray,
    candidate_solution: np.ndarray,
    reference_residual: np.ndarray,
    candidate_residual: np.ndarray,
) -> Fp64CsrResidualRoundoffResultV1:
    """Attest a scale-aware componentwise residual comparison.

    The function accepts no tolerance.  It snapshots all four vectors before
    evaluating the immutable ``ExecutionPlanV2`` reduced CSR operator.
    """

    validate_execution_plan_v2(execution_plan)
    row_count = int(execution_plan.array("free_dofs").size)
    snapshots = tuple(
        _snapshot_f64_vector(value, row_count, path)
        for value, path in (
            (reference_solution, "/source/reference_solution"),
            (candidate_solution, "/source/candidate_solution"),
            (reference_residual, "/source/reference_residual"),
            (candidate_residual, "/source/candidate_residual"),
        )
    )
    receipt = _evaluate(execution_plan, *snapshots)
    result = Fp64CsrResidualRoundoffResultV1(
        receipt=receipt,
        _execution_plan=execution_plan,
        _reference_solution=snapshots[0],
        _candidate_solution=snapshots[1],
        _reference_residual=snapshots[2],
        _candidate_residual=snapshots[3],
    )
    return validate_fp64_csr_residual_roundoff_result_v1(
        result,
        expected_execution_plan=execution_plan,
    )


def validate_fp64_csr_residual_roundoff_receipt_v1(
    receipt: Fp64CsrResidualRoundoffReceiptV1,
) -> Fp64CsrResidualRoundoffReceiptV1:
    """Validate serialized structure without asserting backend provenance."""

    if type(receipt) is not Fp64CsrResidualRoundoffReceiptV1:
        _fail("fp64_csr_residual_roundoff_receipt_type_invalid", "/")
    if (
        type(receipt.bindings) is not Fp64CsrResidualRoundoffBindingsV1
        or type(receipt.arithmetic_model)
        is not Fp64CsrResidualRoundoffArithmeticModelV1
        or type(receipt.summary) is not Fp64CsrResidualRoundoffSummaryV1
        or type(receipt.claims) is not Fp64CsrResidualRoundoffClaimsV1
    ):
        _fail("fp64_csr_residual_roundoff_nested_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("fp64_csr_residual_roundoff_schema_invalid", path, error.message)
    if (
        receipt.schema_version != FP64_CSR_RESIDUAL_ROUNDOFF_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != FP64_CSR_RESIDUAL_ROUNDOFF_CAPABILITY_PROFILE_V1
        or receipt.status != "roundoff_bound_verified"
        or receipt.evidence_scope != FP64_CSR_RESIDUAL_ROUNDOFF_EVIDENCE_SCOPE_V1
        or receipt.promotion_eligible is not False
        or receipt.arithmetic_model != Fp64CsrResidualRoundoffArithmeticModelV1()
        or receipt.claims != Fp64CsrResidualRoundoffClaimsV1()
    ):
        _fail("fp64_csr_residual_roundoff_semantics_invalid", "/")
    _validate_bindings(receipt.bindings)
    _validate_summary(receipt.summary)
    expected_id = canonical_hash(
        {
            "profile": FP64_CSR_RESIDUAL_ROUNDOFF_CAPABILITY_PROFILE_V1,
            "execution_plan_hash": receipt.bindings.execution_plan_hash,
            "reference_solution_sha256": receipt.bindings.reference_solution_sha256,
            "candidate_solution_sha256": receipt.bindings.candidate_solution_sha256,
            "reference_residual_sha256": receipt.bindings.reference_residual_sha256,
            "candidate_residual_sha256": receipt.bindings.candidate_residual_sha256,
            "componentwise_bound_sha256": (receipt.bindings.componentwise_bound_sha256),
        }
    )
    if receipt.comparison_id != expected_id:
        _fail("fp64_csr_residual_roundoff_comparison_id_invalid", "/comparison_id")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if (
        _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != expected_hash
    ):
        _fail("fp64_csr_residual_roundoff_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_fp64_csr_residual_roundoff_result_v1(
    result: Fp64CsrResidualRoundoffResultV1,
    *,
    expected_execution_plan: ExecutionPlanV2 | None = None,
) -> Fp64CsrResidualRoundoffResultV1:
    """Recompute the receipt from the retained immutable plan and vectors."""

    if type(result) is not Fp64CsrResidualRoundoffResultV1:
        _fail("fp64_csr_residual_roundoff_result_type_invalid", "/")
    validate_fp64_csr_residual_roundoff_receipt_v1(result.receipt)
    if type(result._execution_plan) is not ExecutionPlanV2:
        _fail("fp64_csr_residual_roundoff_plan_type_invalid", "/source/plan")
    if (
        expected_execution_plan is not None
        and result._execution_plan is not expected_execution_plan
    ):
        _fail("fp64_csr_residual_roundoff_plan_identity_mismatch", "/source/plan")
    validate_execution_plan_v2(result._execution_plan)
    row_count = int(result._execution_plan.array("free_dofs").size)
    vectors = (
        _validate_snapshot_vector(result._reference_solution, row_count, 0),
        _validate_snapshot_vector(result._candidate_solution, row_count, 1),
        _validate_snapshot_vector(result._reference_residual, row_count, 2),
        _validate_snapshot_vector(result._candidate_residual, row_count, 3),
    )
    replayed = _evaluate(result._execution_plan, *vectors)
    if replayed != result.receipt:
        _fail("fp64_csr_residual_roundoff_replay_mismatch", "/")
    return result


def _evaluate(
    plan: ExecutionPlanV2,
    reference_solution: np.ndarray,
    candidate_solution: np.ndarray,
    reference_residual: np.ndarray,
    candidate_residual: np.ndarray,
) -> Fp64CsrResidualRoundoffReceiptV1:
    bounds = _compute_bounds(
        plan,
        reference_solution,
        candidate_solution,
        reference_residual,
        candidate_residual,
    )
    ratios = np.empty(bounds.componentwise.size, dtype="<f8")
    positive_count = 0
    zero_exact_count = 0
    for row in range(bounds.componentwise.size):
        bound = float(bounds.componentwise[row])
        difference = float(bounds.difference_upper[row])
        if bound == 0.0:
            if difference != 0.0:
                _fail(
                    "fp64_csr_residual_roundoff_componentwise_mismatch",
                    f"/rows/{row}",
                )
            ratios[row] = 0.0
            zero_exact_count += 1
            continue
        positive_count += 1
        ratio = _div_up(difference, bound, f"/rows/{row}/ratio")
        if ratio > 1.0:
            _fail(
                "fp64_csr_residual_roundoff_componentwise_mismatch",
                f"/rows/{row}",
                f"difference={difference!r} bound={bound!r} ratio={ratio!r}",
            )
        ratios[row] = ratio
    ratios.setflags(write=False)

    bindings = Fp64CsrResidualRoundoffBindingsV1(
        execution_plan_id=plan.plan_id,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        partition_hash=plan.partition_hash,
        load_pattern_id=plan.load_pattern_id,
        reference_solution_sha256=_array_sha256(reference_solution),
        candidate_solution_sha256=_array_sha256(candidate_solution),
        reference_residual_sha256=_array_sha256(reference_residual),
        candidate_residual_sha256=_array_sha256(candidate_residual),
        componentwise_bound_sha256=_array_sha256(bounds.componentwise),
        solution_transport_bound_sha256=_array_sha256(bounds.transport),
        reference_roundoff_bound_sha256=_array_sha256(bounds.reference_roundoff),
        candidate_roundoff_bound_sha256=_array_sha256(bounds.candidate_roundoff),
    )
    summary = Fp64CsrResidualRoundoffSummaryV1(
        row_count=bounds.componentwise.size,
        reduced_csr_nnz=int(plan.array("reduced_csr_column_indices").size),
        maximum_row_nnz=bounds.maximum_row_nnz,
        same_solution_bytes=(
            bindings.reference_solution_sha256 == bindings.candidate_solution_sha256
        ),
        maximum_absolute_difference_upper_bound=_maximum(bounds.difference_upper),
        difference_l2_upper_bound=_l2_up(
            bounds.difference_upper, "/summary/difference_l2_upper_bound"
        ),
        componentwise_bound_linf=_maximum(bounds.componentwise),
        componentwise_bound_l2=_l2_up(
            bounds.componentwise, "/summary/componentwise_bound_l2"
        ),
        maximum_solution_transport_bound=_maximum(bounds.transport),
        maximum_reference_roundoff_bound=_maximum(bounds.reference_roundoff),
        maximum_candidate_roundoff_bound=_maximum(bounds.candidate_roundoff),
        maximum_componentwise_bound_ratio=_maximum(ratios),
        reference_componentwise_backward_error=_componentwise_backward_error(
            reference_residual,
            bounds.reference_scale,
            "/summary/reference_componentwise_backward_error",
        ),
        candidate_componentwise_backward_error=_componentwise_backward_error(
            candidate_residual,
            bounds.candidate_scale,
            "/summary/candidate_componentwise_backward_error",
        ),
        positive_bound_row_count=positive_count,
        zero_bound_exact_match_row_count=zero_exact_count,
        componentwise_bound_passed=True,
    )
    comparison_id = canonical_hash(
        {
            "profile": FP64_CSR_RESIDUAL_ROUNDOFF_CAPABILITY_PROFILE_V1,
            "execution_plan_hash": bindings.execution_plan_hash,
            "reference_solution_sha256": bindings.reference_solution_sha256,
            "candidate_solution_sha256": bindings.candidate_solution_sha256,
            "reference_residual_sha256": bindings.reference_residual_sha256,
            "candidate_residual_sha256": bindings.candidate_residual_sha256,
            "componentwise_bound_sha256": bindings.componentwise_bound_sha256,
        }
    )
    draft = Fp64CsrResidualRoundoffReceiptV1(
        schema_version=FP64_CSR_RESIDUAL_ROUNDOFF_SCHEMA_VERSION_V1,
        capability_profile=FP64_CSR_RESIDUAL_ROUNDOFF_CAPABILITY_PROFILE_V1,
        status="roundoff_bound_verified",
        evidence_scope=FP64_CSR_RESIDUAL_ROUNDOFF_EVIDENCE_SCOPE_V1,
        promotion_eligible=False,
        comparison_id=comparison_id,
        bindings=bindings,
        arithmetic_model=Fp64CsrResidualRoundoffArithmeticModelV1(),
        summary=summary,
        claims=Fp64CsrResidualRoundoffClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_fp64_csr_residual_roundoff_receipt_v1(receipt)


def _compute_bounds(
    plan: ExecutionPlanV2,
    reference_solution: np.ndarray,
    candidate_solution: np.ndarray,
    reference_residual: np.ndarray,
    candidate_residual: np.ndarray,
) -> _ComputedBoundsV1:
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    row_count = free.size
    componentwise = np.empty(row_count, dtype="<f8")
    transport = np.empty(row_count, dtype="<f8")
    reference_roundoff = np.empty(row_count, dtype="<f8")
    candidate_roundoff = np.empty(row_count, dtype="<f8")
    reference_scale = np.empty(row_count, dtype="<f8")
    candidate_scale = np.empty(row_count, dtype="<f8")
    difference_upper = np.empty(row_count, dtype="<f8")
    maximum_row_nnz = 0

    for row in range(row_count):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        row_nnz = stop - start
        maximum_row_nnz = max(maximum_row_nnz, row_nnz)
        operation_count = 2 * row_nnz + 1
        gamma = _gamma(operation_count, f"/rows/{row}/gamma")
        ref_scale = _abs_up(float(rhs[row]), f"/rows/{row}/reference_scale")
        cand_scale = _abs_up(float(rhs[row]), f"/rows/{row}/candidate_scale")
        row_transport = 0.0
        for index in range(start, stop):
            column = int(columns[index])
            coefficient = _abs_up(float(values[index]), f"/rows/{row}/values/{index}")
            ref_product = _mul_up(
                coefficient,
                _abs_up(
                    float(reference_solution[column]),
                    f"/rows/{row}/reference_solution/{column}",
                ),
                f"/rows/{row}/reference_scale",
            )
            cand_product = _mul_up(
                coefficient,
                _abs_up(
                    float(candidate_solution[column]),
                    f"/rows/{row}/candidate_solution/{column}",
                ),
                f"/rows/{row}/candidate_scale",
            )
            delta = _distance_up(
                float(candidate_solution[column]),
                float(reference_solution[column]),
                f"/rows/{row}/solution_delta/{column}",
            )
            transport_product = _mul_up(
                coefficient,
                delta,
                f"/rows/{row}/transport",
            )
            ref_scale = _add_up(ref_scale, ref_product, f"/rows/{row}/reference_scale")
            cand_scale = _add_up(
                cand_scale, cand_product, f"/rows/{row}/candidate_scale"
            )
            row_transport = _add_up(
                row_transport, transport_product, f"/rows/{row}/transport"
            )
        subnormal_guard = _mul_up(
            float(operation_count),
            FP64_BINARY64_SMALLEST_SUBNORMAL_V1,
            f"/rows/{row}/subnormal_guard",
        )
        ref_roundoff = _add_up(
            _mul_up(gamma, ref_scale, f"/rows/{row}/reference_roundoff"),
            subnormal_guard,
            f"/rows/{row}/reference_roundoff",
        )
        cand_roundoff = _add_up(
            _mul_up(gamma, cand_scale, f"/rows/{row}/candidate_roundoff"),
            subnormal_guard,
            f"/rows/{row}/candidate_roundoff",
        )
        total = _add_up(
            _add_up(
                row_transport,
                ref_roundoff,
                f"/rows/{row}/componentwise_bound",
            ),
            cand_roundoff,
            f"/rows/{row}/componentwise_bound",
        )
        componentwise[row] = total
        transport[row] = row_transport
        reference_roundoff[row] = ref_roundoff
        candidate_roundoff[row] = cand_roundoff
        reference_scale[row] = ref_scale
        candidate_scale[row] = cand_scale
        difference_upper[row] = _distance_up(
            float(candidate_residual[row]),
            float(reference_residual[row]),
            f"/rows/{row}/residual_difference",
        )

    arrays = (
        componentwise,
        transport,
        reference_roundoff,
        candidate_roundoff,
        reference_scale,
        candidate_scale,
        difference_upper,
    )
    for array in arrays:
        if not np.isfinite(array).all() or np.any(array < 0.0):
            _fail("fp64_csr_residual_roundoff_bound_nonfinite", "/rows")
        array[array == 0.0] = 0.0
        array.setflags(write=False)
    return _ComputedBoundsV1(
        componentwise=componentwise,
        transport=transport,
        reference_roundoff=reference_roundoff,
        candidate_roundoff=candidate_roundoff,
        reference_scale=reference_scale,
        candidate_scale=candidate_scale,
        difference_upper=difference_upper,
        maximum_row_nnz=maximum_row_nnz,
    )


def _snapshot_f64_vector(value: np.ndarray, size: int, path: str) -> np.ndarray:
    if (
        type(value) is not np.ndarray
        or value.dtype.str != "<f8"
        or value.shape != (size,)
        or not value.flags.c_contiguous
        or not np.isfinite(value).all()
        or np.any(np.signbit(value[value == 0.0]))
    ):
        _fail("fp64_csr_residual_roundoff_vector_invalid", path)
    snapshot = np.frombuffer(value.tobytes(order="C"), dtype="<f8")
    snapshot.setflags(write=False)
    return snapshot


def _validate_snapshot_vector(value: np.ndarray, size: int, index: int) -> np.ndarray:
    if (
        type(value) is not np.ndarray
        or value.dtype.str != "<f8"
        or value.shape != (size,)
        or not value.flags.c_contiguous
        or value.flags.writeable
        or not np.isfinite(value).all()
        or np.any(np.signbit(value[value == 0.0]))
    ):
        _fail(
            "fp64_csr_residual_roundoff_retained_vector_invalid",
            f"/source/vectors/{index}",
        )
    return value


def _abs_up(value: float, path: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        _fail("fp64_csr_residual_roundoff_nonfinite_operand", path)
    absolute = abs(value)
    return _next_up_nonnegative(absolute, path) if absolute != 0.0 else 0.0


def _distance_up(left: float, right: float, path: str) -> float:
    if not math.isfinite(left) or not math.isfinite(right):
        _fail("fp64_csr_residual_roundoff_nonfinite_operand", path)
    if left == right:
        return 0.0
    difference = abs(left - right)
    if not math.isfinite(difference):
        _fail("fp64_csr_residual_roundoff_bound_overflow", path)
    return _next_up_nonnegative(difference, path)


def _add_up(left: float, right: float, path: str) -> float:
    value = left + right
    if not math.isfinite(value):
        _fail("fp64_csr_residual_roundoff_bound_overflow", path)
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _mul_up(left: float, right: float, path: str) -> float:
    value = left * right
    if not math.isfinite(value):
        _fail("fp64_csr_residual_roundoff_bound_overflow", path)
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _div_up(numerator: float, denominator: float, path: str) -> float:
    if denominator <= 0.0:
        _fail("fp64_csr_residual_roundoff_zero_denominator", path)
    value = numerator / denominator
    if not math.isfinite(value):
        _fail("fp64_csr_residual_roundoff_bound_overflow", path)
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _next_up_nonnegative(value: float, path: str) -> float:
    if value < 0.0 or not math.isfinite(value):
        _fail("fp64_csr_residual_roundoff_bound_invalid", path)
    outward = math.nextafter(value, _POSITIVE_INFINITY)
    if not math.isfinite(outward):
        _fail("fp64_csr_residual_roundoff_bound_overflow", path)
    return outward


def _gamma(operation_count: int, path: str) -> float:
    product = operation_count * FP64_BINARY64_UNIT_ROUNDOFF_V1
    if operation_count <= 0 or not product < 1.0:
        _fail("fp64_csr_residual_roundoff_gamma_invalid", path)
    return _div_up(product, 1.0 - product, path)


def _l2_up(vector: np.ndarray, path: str) -> float:
    total = 0.0
    for value in vector:
        square = _mul_up(float(value), float(value), path)
        total = _add_up(total, square, path)
    root = math.sqrt(total)
    if not math.isfinite(root):
        _fail("fp64_csr_residual_roundoff_bound_overflow", path)
    return _next_up_nonnegative(root, path) if root != 0.0 else 0.0


def _componentwise_backward_error(
    residual: np.ndarray,
    scale: np.ndarray,
    path: str,
) -> float:
    maximum = 0.0
    for row, (raw_residual, raw_scale) in enumerate(zip(residual, scale, strict=True)):
        numerator = _abs_up(float(raw_residual), f"{path}/{row}/residual")
        denominator = float(raw_scale)
        if denominator == 0.0:
            if numerator != 0.0:
                _fail(
                    "fp64_csr_residual_roundoff_zero_scale_nonzero_residual",
                    f"{path}/{row}",
                )
            ratio = 0.0
        else:
            ratio = _div_up(numerator, denominator, f"{path}/{row}")
        maximum = max(maximum, ratio)
    return maximum


def _maximum(vector: np.ndarray) -> float:
    return max((float(value) for value in vector), default=0.0)


def _array_sha256(array: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _validate_bindings(bindings: Fp64CsrResidualRoundoffBindingsV1) -> None:
    if (
        _PLAN_ID_RE.fullmatch(bindings.execution_plan_id) is None
        or type(bindings.load_pattern_id) is not str
        or not bindings.load_pattern_id
    ):
        _fail("fp64_csr_residual_roundoff_binding_invalid", "/bindings")
    hash_fields = tuple(
        name
        for name in bindings.__dataclass_fields__
        if name.endswith("_hash") or name.endswith("_sha256")
    )
    if any(
        type(getattr(bindings, name)) is not str
        or _HASH_RE.fullmatch(getattr(bindings, name)) is None
        for name in hash_fields
    ):
        _fail("fp64_csr_residual_roundoff_binding_hash_invalid", "/bindings")


def _validate_summary(summary: Fp64CsrResidualRoundoffSummaryV1) -> None:
    integer_fields = (
        "row_count",
        "reduced_csr_nnz",
        "maximum_row_nnz",
        "positive_bound_row_count",
        "zero_bound_exact_match_row_count",
    )
    if any(type(getattr(summary, name)) is not int for name in integer_fields):
        _fail("fp64_csr_residual_roundoff_summary_type_invalid", "/summary")
    if (
        summary.row_count <= 0
        or summary.reduced_csr_nnz <= 0
        or summary.maximum_row_nnz <= 0
        or summary.positive_bound_row_count < 0
        or summary.zero_bound_exact_match_row_count < 0
        or summary.positive_bound_row_count + summary.zero_bound_exact_match_row_count
        != summary.row_count
        or type(summary.same_solution_bytes) is not bool
        or summary.componentwise_bound_passed is not True
    ):
        _fail("fp64_csr_residual_roundoff_summary_invalid", "/summary")
    float_fields = tuple(
        name
        for name in summary.__dataclass_fields__
        if name not in integer_fields
        and name not in {"same_solution_bytes", "componentwise_bound_passed"}
    )
    if any(
        type(getattr(summary, name)) is not float
        or not math.isfinite(getattr(summary, name))
        or getattr(summary, name) < 0.0
        or (
            getattr(summary, name) == 0.0
            and math.copysign(1.0, getattr(summary, name)) < 0.0
        )
        for name in float_fields
    ):
        _fail("fp64_csr_residual_roundoff_summary_metric_invalid", "/summary")
    if summary.maximum_componentwise_bound_ratio > 1.0:
        _fail("fp64_csr_residual_roundoff_summary_ratio_invalid", "/summary")


def _receipt_payload(
    receipt: Fp64CsrResidualRoundoffReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "comparison_id": receipt.comparison_id,
        "bindings": receipt.bindings.to_dict(),
        "arithmetic_model": receipt.arithmetic_model.to_dict(),
        "summary": receipt.summary.to_dict(),
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
    raise Fp64CsrResidualRoundoffV1Error(code, path, message)


__all__ = [
    "FP64_BINARY64_SMALLEST_SUBNORMAL_V1",
    "FP64_BINARY64_UNIT_ROUNDOFF_V1",
    "FP64_CSR_RESIDUAL_ROUNDOFF_CAPABILITY_PROFILE_V1",
    "FP64_CSR_RESIDUAL_ROUNDOFF_EVIDENCE_SCOPE_V1",
    "FP64_CSR_RESIDUAL_ROUNDOFF_SCHEMA_VERSION_V1",
    "Fp64CsrResidualRoundoffArithmeticModelV1",
    "Fp64CsrResidualRoundoffBindingsV1",
    "Fp64CsrResidualRoundoffClaimsV1",
    "Fp64CsrResidualRoundoffReceiptV1",
    "Fp64CsrResidualRoundoffResultV1",
    "Fp64CsrResidualRoundoffSummaryV1",
    "Fp64CsrResidualRoundoffV1Error",
    "attest_fp64_csr_residual_roundoff_v1",
    "validate_fp64_csr_residual_roundoff_receipt_v1",
    "validate_fp64_csr_residual_roundoff_result_v1",
]
