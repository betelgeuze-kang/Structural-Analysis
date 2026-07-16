"""Additive FGMRES terminal norm-metric parity contract v2.

This detached contract keeps model-case parity v1 byte-for-byte unchanged.
It binds the validated CPU stable-L2 records and HIP GPU-tree records to the
v0.2.48 componentwise residual envelope and its normwise projection.  Record
evaluation error is measured against outward intervals enclosing the exact
norm of each represented residual vector, so no caller tolerance is needed.
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
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.fp64_csr_residual_normwise_v1 import (
    Fp64CsrResidualNormwiseIntervalV1,
    Fp64CsrResidualNormwiseResultV1,
    attest_fp64_csr_residual_normwise_v1,
    validate_fp64_csr_residual_normwise_result_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceResultV1,
    validate_cpu_fgmres_reference_result_v1,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
)

from .fgmres_model_case_parity_v1 import (
    HipFgmresDetachedResidualRoundoffReplayV1,
    replay_hip_fgmres_detached_residual_roundoff_v1,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeMetricsV1,
    HipFgmresTerminalOutcomeV1,
)


HIP_FGMRES_TERMINAL_METRIC_PARITY_SCHEMA_VERSION_V2 = (
    "structural-analysis-hip-fgmres-terminal-metric-parity.v2"
)
HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2 = (
    "phase0_detached_fgmres_terminal_norm_metric_parity_v2"
)
HIP_FGMRES_TERMINAL_METRIC_PARITY_EVIDENCE_SCOPE_V2 = (
    "detached_value_replay_non_provenance_non_promoting"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_RESOURCE = "hip_fgmres_terminal_metric_parity_v2.schema.json"
_METRIC_NAMES = ("l2", "linf", "scaled_linf")


class HipFgmresTerminalMetricParityV2Error(ValueError):
    """Stable fail-closed error for detached terminal metric parity."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalMetricParityBindingsV2:
    execution_plan_hash: str
    operator_hash: str
    cpu_result_hash: str
    terminal_outcome_hash: str
    candidate_solution_sha256: str
    candidate_residual_sha256: str
    cpu_candidate_componentwise_receipt_hash: str
    cpu_candidate_normwise_receipt_hash: str
    candidate_replay_componentwise_receipt_hash: str
    candidate_replay_normwise_receipt_hash: str
    terminal_metric_projection_hash: str

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalMetricParityRecordV2:
    name: Literal["l2", "linf", "scaled_linf"]
    reference_record: float
    candidate_record: float
    reference_record_evaluation_error_upper_bound: float
    candidate_record_evaluation_error_upper_bound: float
    vector_difference_upper_bound: float
    total_record_difference_upper_bound: float
    absolute_record_difference_upper_bound: float
    maximum_bound_ratio: float
    record_difference_bound_passed: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalMetricParitySummaryV2:
    free_dof_count: int
    rhs_linf: float
    load_scale: float
    metric_count: Literal[3]
    maximum_record_bound_ratio: float
    all_terminal_record_bounds_passed: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalMetricParityCompatibilityV2:
    legacy_model_case_parity_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-case-parity.v1"
    ] = "structural-analysis-hip-fgmres-model-case-parity.v1"
    legacy_wire_receipt_mutated: Literal[False] = False
    legacy_solution_gate_relaxed: Literal[False] = False
    legacy_residual_gate_relaxed: Literal[False] = False
    legacy_terminal_or_history_gate_relaxed: Literal[False] = False
    migration_action: Literal["preserve_v1_and_issue_additive_terminal_metric_v2"] = (
        "preserve_v1_and_issue_additive_terminal_metric_v2"
    )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalMetricParityClaimsV2:
    legacy_fixed_solution_gate_verified: Literal[True] = True
    cpu_candidate_componentwise_roundoff_replayed: Literal[True] = True
    candidate_independent_replay_roundoff_replayed: Literal[True] = True
    cpu_stable_l2_record_replayed: Literal[True] = True
    candidate_gpu_tree_record_replayed: Literal[True] = True
    terminal_l2_record_bound_verified: Literal[True] = True
    terminal_linf_record_bound_verified: Literal[True] = True
    terminal_scaled_linf_record_bound_verified: Literal[True] = True
    caller_tolerance_allowed: Literal[False] = False
    history_metric_v2_verified: Literal[False] = False
    actual_backend_verified: Literal[False] = False
    hardware_provenance_verified: Literal[False] = False
    result_ir_ready: Literal[False] = False
    performance_speedup_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresTerminalMetricParityReceiptV2:
    schema_version: str
    capability_profile: str
    status: Literal["terminal_metric_parity_verified"]
    evidence_scope: str
    promotion_eligible: Literal[False]
    parity_id: str
    bindings: HipFgmresTerminalMetricParityBindingsV2
    records: tuple[HipFgmresTerminalMetricParityRecordV2, ...]
    summary: HipFgmresTerminalMetricParitySummaryV2
    compatibility: HipFgmresTerminalMetricParityCompatibilityV2
    claims: HipFgmresTerminalMetricParityClaimsV2
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_terminal_metric_parity_receipt_v2(self)
        return _receipt_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresTerminalMetricParityResultV2:
    receipt: HipFgmresTerminalMetricParityReceiptV2
    roundoff_replay: HipFgmresDetachedResidualRoundoffReplayV1
    cpu_candidate_normwise: Fp64CsrResidualNormwiseResultV1
    candidate_replay_normwise: Fp64CsrResidualNormwiseResultV1
    _execution_plan: ExecutionPlanV2 = dataclass_field(repr=False, compare=False)
    _cpu_result: CpuFgmresReferenceResultV1 = dataclass_field(
        repr=False,
        compare=False,
    )
    _solution_x: bytes = dataclass_field(repr=False, compare=False)
    _true_residual: bytes = dataclass_field(repr=False, compare=False)
    _outcome: HipFgmresTerminalOutcomeV1 = dataclass_field(
        repr=False,
        compare=False,
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_terminal_metric_parity_result_v2(self)
        return self.receipt.to_dict()


def replay_hip_fgmres_detached_terminal_metric_parity_v2(
    *,
    execution_plan: ExecutionPlanV2,
    cpu_result: CpuFgmresReferenceResultV1,
    solution_x: bytes,
    true_residual: bytes,
    outcome: HipFgmresTerminalOutcomeV1,
) -> HipFgmresTerminalMetricParityResultV2:
    """Issue an additive normwise terminal-record parity receipt.

    No device identity or live execution context is accepted.  A higher layer
    may bind this value receipt to actual HIP provenance, but this function
    never makes that claim itself.
    """

    if type(solution_x) is not bytes or type(true_residual) is not bytes:
        _fail("hip_fgmres_terminal_metric_payload_type_invalid", "/payload")
    validate_execution_plan_v2(execution_plan)
    validate_cpu_fgmres_reference_result_v1(
        cpu_result,
        expected_plan=execution_plan,
        expected_policy=cpu_result.policy,
        expected_initial_full_state=None,
    )
    solution_snapshot = bytes(solution_x)
    residual_snapshot = bytes(true_residual)
    receipt, roundoff, cpu_normwise, replay_normwise = _evaluate(
        execution_plan,
        cpu_result,
        solution_snapshot,
        residual_snapshot,
        outcome,
    )
    result = HipFgmresTerminalMetricParityResultV2(
        receipt=receipt,
        roundoff_replay=roundoff,
        cpu_candidate_normwise=cpu_normwise,
        candidate_replay_normwise=replay_normwise,
        _execution_plan=execution_plan,
        _cpu_result=cpu_result,
        _solution_x=solution_snapshot,
        _true_residual=residual_snapshot,
        _outcome=outcome,
    )
    return validate_hip_fgmres_terminal_metric_parity_result_v2(
        result,
        expected_execution_plan=execution_plan,
        expected_cpu_result=cpu_result,
        expected_outcome=outcome,
    )


def validate_hip_fgmres_terminal_metric_parity_receipt_v2(
    receipt: HipFgmresTerminalMetricParityReceiptV2,
) -> HipFgmresTerminalMetricParityReceiptV2:
    """Validate strict detached wire semantics without backend provenance."""

    if type(receipt) is not HipFgmresTerminalMetricParityReceiptV2:
        _fail("hip_fgmres_terminal_metric_receipt_type_invalid", "/")
    if (
        type(receipt.bindings) is not HipFgmresTerminalMetricParityBindingsV2
        or type(receipt.summary) is not HipFgmresTerminalMetricParitySummaryV2
        or type(receipt.compatibility)
        is not HipFgmresTerminalMetricParityCompatibilityV2
        or type(receipt.claims) is not HipFgmresTerminalMetricParityClaimsV2
        or type(receipt.records) is not tuple
        or any(
            type(row) is not HipFgmresTerminalMetricParityRecordV2
            for row in receipt.records
        )
    ):
        _fail("hip_fgmres_terminal_metric_nested_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_terminal_metric_schema_invalid", path, error.message)
    if (
        receipt.schema_version != HIP_FGMRES_TERMINAL_METRIC_PARITY_SCHEMA_VERSION_V2
        or receipt.capability_profile
        != HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2
        or receipt.status != "terminal_metric_parity_verified"
        or receipt.evidence_scope != HIP_FGMRES_TERMINAL_METRIC_PARITY_EVIDENCE_SCOPE_V2
        or receipt.promotion_eligible is not False
        or receipt.compatibility != HipFgmresTerminalMetricParityCompatibilityV2()
        or receipt.claims != HipFgmresTerminalMetricParityClaimsV2()
    ):
        _fail("hip_fgmres_terminal_metric_semantics_invalid", "/")
    _validate_bindings(receipt.bindings)
    _validate_summary(receipt.summary)
    if tuple(row.name for row in receipt.records) != _METRIC_NAMES:
        _fail("hip_fgmres_terminal_metric_record_order_invalid", "/records")
    for index, row in enumerate(receipt.records):
        _validate_record(row, f"/records/{index}")
    projection_hash = canonical_hash([row.to_dict() for row in receipt.records])
    if receipt.bindings.terminal_metric_projection_hash != projection_hash:
        _fail(
            "hip_fgmres_terminal_metric_projection_hash_invalid",
            "/bindings/terminal_metric_projection_hash",
        )
    expected_id = canonical_hash(
        {
            "profile": HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2,
            "cpu_candidate_normwise_receipt_hash": (
                receipt.bindings.cpu_candidate_normwise_receipt_hash
            ),
            "terminal_outcome_hash": receipt.bindings.terminal_outcome_hash,
            "terminal_metric_projection_hash": projection_hash,
        }
    )
    if receipt.parity_id != expected_id:
        _fail("hip_fgmres_terminal_metric_parity_id_invalid", "/parity_id")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if (
        _HASH_RE.fullmatch(receipt.receipt_hash) is None
        or receipt.receipt_hash != expected_hash
    ):
        _fail("hip_fgmres_terminal_metric_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_fgmres_terminal_metric_parity_result_v2(
    result: HipFgmresTerminalMetricParityResultV2,
    *,
    expected_execution_plan: ExecutionPlanV2 | None = None,
    expected_cpu_result: CpuFgmresReferenceResultV1 | None = None,
    expected_outcome: HipFgmresTerminalOutcomeV1 | None = None,
) -> HipFgmresTerminalMetricParityResultV2:
    """Replay all retained vector, reduction-path and normwise sources."""

    if type(result) is not HipFgmresTerminalMetricParityResultV2:
        _fail("hip_fgmres_terminal_metric_result_type_invalid", "/")
    validate_hip_fgmres_terminal_metric_parity_receipt_v2(result.receipt)
    if (
        type(result._execution_plan) is not ExecutionPlanV2
        or type(result._cpu_result) is not CpuFgmresReferenceResultV1
        or type(result._solution_x) is not bytes
        or type(result._true_residual) is not bytes
        or type(result._outcome) is not HipFgmresTerminalOutcomeV1
    ):
        _fail("hip_fgmres_terminal_metric_source_type_invalid", "/source")
    if (
        expected_execution_plan is not None
        and result._execution_plan is not expected_execution_plan
    ):
        _fail("hip_fgmres_terminal_metric_plan_identity_mismatch", "/source/plan")
    if (
        expected_cpu_result is not None
        and result._cpu_result is not expected_cpu_result
    ):
        _fail("hip_fgmres_terminal_metric_cpu_identity_mismatch", "/source/cpu")
    if expected_outcome is not None and result._outcome is not expected_outcome:
        _fail("hip_fgmres_terminal_metric_outcome_identity_mismatch", "/source/outcome")
    replayed, roundoff, cpu_normwise, replay_normwise = _evaluate(
        result._execution_plan,
        result._cpu_result,
        result._solution_x,
        result._true_residual,
        result._outcome,
    )
    if replayed != result.receipt:
        _fail("hip_fgmres_terminal_metric_replay_mismatch", "/")
    if (
        roundoff.solution_comparison != result.roundoff_replay.solution_comparison
        or roundoff.cpu_reference_vs_candidate.receipt
        != result.roundoff_replay.cpu_reference_vs_candidate.receipt
        or roundoff.candidate_vs_independent_replay.receipt
        != result.roundoff_replay.candidate_vs_independent_replay.receipt
        or cpu_normwise.receipt != result.cpu_candidate_normwise.receipt
        or replay_normwise.receipt != result.candidate_replay_normwise.receipt
    ):
        _fail("hip_fgmres_terminal_metric_child_replay_mismatch", "/children")
    validate_fp64_csr_residual_normwise_result_v1(result.cpu_candidate_normwise)
    validate_fp64_csr_residual_normwise_result_v1(result.candidate_replay_normwise)
    return result


def _evaluate(
    plan: ExecutionPlanV2,
    cpu: CpuFgmresReferenceResultV1,
    solution_x: bytes,
    true_residual: bytes,
    outcome: HipFgmresTerminalOutcomeV1,
) -> tuple[
    HipFgmresTerminalMetricParityReceiptV2,
    HipFgmresDetachedResidualRoundoffReplayV1,
    Fp64CsrResidualNormwiseResultV1,
    Fp64CsrResidualNormwiseResultV1,
]:
    validate_execution_plan_v2(plan)
    validate_cpu_fgmres_reference_result_v1(
        cpu,
        expected_plan=plan,
        expected_policy=cpu.policy,
        expected_initial_full_state=None,
    )
    metrics = _validate_outcome_and_replay_candidate_metrics(
        plan, cpu, true_residual, outcome
    )
    roundoff = replay_hip_fgmres_detached_residual_roundoff_v1(
        execution_plan=plan,
        cpu_result=cpu,
        solution_x=solution_x,
        true_residual=true_residual,
    )
    cpu_normwise = attest_fp64_csr_residual_normwise_v1(
        roundoff.cpu_reference_vs_candidate
    )
    replay_normwise = attest_fp64_csr_residual_normwise_v1(
        roundoff.candidate_vs_independent_replay
    )
    reference_records = (
        cpu.final_residual_l2,
        cpu.final_residual_linf,
        cpu.scaled_true_residual,
    )
    candidate_records = (
        metrics.final_residual_l2,
        metrics.final_residual_linf,
        metrics.final_scaled_residual,
    )
    records = tuple(
        _record(
            name,
            reference_record,
            candidate_record,
            projection.reference_interval,
            projection.candidate_interval,
            projection.vector_difference_upper_bound,
            f"/records/{index}",
        )
        for index, (name, reference_record, candidate_record, projection) in enumerate(
            zip(
                _METRIC_NAMES,
                reference_records,
                candidate_records,
                cpu_normwise.receipt.metrics,
                strict=True,
            )
        )
    )
    projection_hash = canonical_hash([row.to_dict() for row in records])
    source = roundoff.cpu_reference_vs_candidate.receipt
    bindings = HipFgmresTerminalMetricParityBindingsV2(
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        cpu_result_hash=cpu.result_hash,
        terminal_outcome_hash=canonical_hash(outcome.to_dict()),
        candidate_solution_sha256=roundoff.solution_comparison.hip_or_candidate_sha256,
        candidate_residual_sha256=source.bindings.candidate_residual_sha256,
        cpu_candidate_componentwise_receipt_hash=source.receipt_hash,
        cpu_candidate_normwise_receipt_hash=cpu_normwise.receipt.receipt_hash,
        candidate_replay_componentwise_receipt_hash=(
            roundoff.candidate_vs_independent_replay.receipt.receipt_hash
        ),
        candidate_replay_normwise_receipt_hash=replay_normwise.receipt.receipt_hash,
        terminal_metric_projection_hash=projection_hash,
    )
    parity_id = canonical_hash(
        {
            "profile": HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2,
            "cpu_candidate_normwise_receipt_hash": (
                bindings.cpu_candidate_normwise_receipt_hash
            ),
            "terminal_outcome_hash": bindings.terminal_outcome_hash,
            "terminal_metric_projection_hash": projection_hash,
        }
    )
    summary = cpu_normwise.receipt.summary
    draft = HipFgmresTerminalMetricParityReceiptV2(
        schema_version=HIP_FGMRES_TERMINAL_METRIC_PARITY_SCHEMA_VERSION_V2,
        capability_profile=HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2,
        status="terminal_metric_parity_verified",
        evidence_scope=HIP_FGMRES_TERMINAL_METRIC_PARITY_EVIDENCE_SCOPE_V2,
        promotion_eligible=False,
        parity_id=parity_id,
        bindings=bindings,
        records=records,
        summary=HipFgmresTerminalMetricParitySummaryV2(
            free_dof_count=summary.row_count,
            rhs_linf=summary.rhs_linf,
            load_scale=summary.load_scale,
            metric_count=3,
            maximum_record_bound_ratio=max(row.maximum_bound_ratio for row in records),
            all_terminal_record_bounds_passed=True,
        ),
        compatibility=HipFgmresTerminalMetricParityCompatibilityV2(),
        claims=HipFgmresTerminalMetricParityClaimsV2(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return (
        validate_hip_fgmres_terminal_metric_parity_receipt_v2(receipt),
        roundoff,
        cpu_normwise,
        replay_normwise,
    )


def _validate_outcome_and_replay_candidate_metrics(
    plan: ExecutionPlanV2,
    cpu: CpuFgmresReferenceResultV1,
    true_residual: bytes,
    outcome: HipFgmresTerminalOutcomeV1,
) -> HipFgmresTerminalOutcomeMetricsV1:
    if type(outcome) is not HipFgmresTerminalOutcomeV1:
        _fail("hip_fgmres_terminal_metric_outcome_type_invalid", "/outcome")
    metrics = outcome.metrics
    if (
        outcome.outcome_class == "numerical_failure"
        or outcome.terminal_status != cpu.status
        or outcome.termination_code != cpu.termination_code
        or outcome.record_metrics_authoritative is not True
        or outcome.true_residual_record_metrics_match is not True
        or outcome.true_residual_all_finite is not True
        or type(metrics) is not HipFgmresTerminalOutcomeMetricsV1
    ):
        _fail("hip_fgmres_terminal_metric_outcome_invalid", "/outcome")
    free_count = int(plan.array("free_dofs").size)
    if len(true_residual) != free_count * 8:
        _fail(
            "hip_fgmres_terminal_metric_payload_extent_invalid",
            "/payload/true_residual",
        )
    candidate = np.frombuffer(true_residual, dtype="<f8")
    if (
        candidate.shape != (free_count,)
        or not np.isfinite(candidate).all()
        or np.any(np.signbit(candidate[candidate == 0.0]))
    ):
        _fail("hip_fgmres_terminal_metric_payload_invalid", "/payload/true_residual")
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    candidate_l2 = fgmres_gpu_tree_l2_v2(candidate).value
    candidate_linf = fgmres_gpu_tree_linf_v2(candidate).value
    rhs_l2 = fgmres_gpu_tree_l2_v2(rhs).value
    rhs_linf = fgmres_gpu_tree_linf_v2(rhs).value
    candidate_scaled = candidate_linf / max(1.0, rhs_linf)
    expected = (
        (metrics.rhs_l2, rhs_l2),
        (metrics.rhs_linf, rhs_linf),
        (metrics.final_residual_l2, candidate_l2),
        (metrics.final_residual_linf, candidate_linf),
        (metrics.final_scaled_residual, candidate_scaled),
        (outcome.observed_true_residual_l2, candidate_l2),
        (outcome.observed_true_residual_linf, candidate_linf),
        (outcome.observed_true_residual_scaled_linf, candidate_scaled),
    )
    if any(
        type(actual) is not float
        or not math.isfinite(actual)
        or actual != expected_value
        for actual, expected_value in expected
    ):
        _fail(
            "hip_fgmres_terminal_metric_candidate_record_mismatch", "/outcome/metrics"
        )
    return metrics


def _record(
    name: str,
    reference_record: float,
    candidate_record: float,
    reference_interval: Fp64CsrResidualNormwiseIntervalV1,
    candidate_interval: Fp64CsrResidualNormwiseIntervalV1,
    vector_bound: float,
    path: str,
) -> HipFgmresTerminalMetricParityRecordV2:
    for label, value in (
        ("reference", reference_record),
        ("candidate", candidate_record),
    ):
        if (
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        ):
            _fail("hip_fgmres_terminal_metric_record_invalid", f"{path}/{label}")
    reference_error = _record_interval_error_up(
        reference_record,
        reference_interval,
        f"{path}/reference_evaluation_error",
    )
    candidate_error = _record_interval_error_up(
        candidate_record,
        candidate_interval,
        f"{path}/candidate_evaluation_error",
    )
    total = _add_up(
        _add_up(reference_error, vector_bound, f"{path}/total"),
        candidate_error,
        f"{path}/total",
    )
    difference = _distance_up(reference_record, candidate_record, f"{path}/difference")
    if difference > total:
        _fail(
            "hip_fgmres_terminal_metric_record_bound_mismatch",
            path,
            f"difference={difference!r} bound={total!r}",
        )
    if total == 0.0:
        ratio = 0.0
    else:
        ratio = min(1.0, _div_up(difference, total, f"{path}/ratio"))
    return HipFgmresTerminalMetricParityRecordV2(
        name=name,  # type: ignore[arg-type]
        reference_record=reference_record,
        candidate_record=candidate_record,
        reference_record_evaluation_error_upper_bound=reference_error,
        candidate_record_evaluation_error_upper_bound=candidate_error,
        vector_difference_upper_bound=vector_bound,
        total_record_difference_upper_bound=total,
        absolute_record_difference_upper_bound=difference,
        maximum_bound_ratio=ratio,
        record_difference_bound_passed=True,
    )


def _record_interval_error_up(
    record: float,
    interval: Fp64CsrResidualNormwiseIntervalV1,
    path: str,
) -> float:
    value = max(abs(record - interval.lower), abs(record - interval.upper))
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _distance_up(left: float, right: float, path: str) -> float:
    value = abs(left - right)
    if not math.isfinite(value):
        _fail("hip_fgmres_terminal_metric_bound_overflow", path)
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _add_up(left: float, right: float, path: str) -> float:
    value = left + right
    if not math.isfinite(value):
        _fail("hip_fgmres_terminal_metric_bound_overflow", path)
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _div_up(numerator: float, denominator: float, path: str) -> float:
    if numerator < 0.0 or denominator <= 0.0:
        _fail("hip_fgmres_terminal_metric_zero_denominator", path)
    value = numerator / denominator
    if not math.isfinite(value):
        _fail("hip_fgmres_terminal_metric_bound_overflow", path)
    if value == 0.0 and numerator != 0.0:
        return float.fromhex("0x0.0000000000001p-1022")
    return _next_up_nonnegative(value, path) if value != 0.0 else 0.0


def _next_up_nonnegative(value: float, path: str) -> float:
    if value < 0.0 or not math.isfinite(value):
        _fail("hip_fgmres_terminal_metric_bound_invalid", path)
    outward = math.nextafter(value, math.inf)
    if not math.isfinite(outward):
        _fail("hip_fgmres_terminal_metric_bound_overflow", path)
    return outward


def _validate_bindings(bindings: HipFgmresTerminalMetricParityBindingsV2) -> None:
    for name in bindings.__dataclass_fields__:
        value = getattr(bindings, name)
        if type(value) is not str or _HASH_RE.fullmatch(value) is None:
            _fail(
                "hip_fgmres_terminal_metric_binding_hash_invalid", f"/bindings/{name}"
            )


def _validate_record(row: HipFgmresTerminalMetricParityRecordV2, path: str) -> None:
    values = tuple(
        getattr(row, name)
        for name in row.__dataclass_fields__
        if name not in {"name", "record_difference_bound_passed"}
    )
    if any(
        type(value) is not float
        or not math.isfinite(value)
        or value < 0.0
        or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        for value in values
    ):
        _fail("hip_fgmres_terminal_metric_record_invalid", path)
    if (
        row.record_difference_bound_passed is not True
        or row.maximum_bound_ratio > 1.0
        or row.absolute_record_difference_upper_bound
        > row.total_record_difference_upper_bound
    ):
        _fail("hip_fgmres_terminal_metric_record_bound_invalid", path)


def _validate_summary(summary: HipFgmresTerminalMetricParitySummaryV2) -> None:
    if (
        type(summary.free_dof_count) is not int
        or summary.free_dof_count <= 0
        or type(summary.metric_count) is not int
        or summary.metric_count != 3
        or summary.all_terminal_record_bounds_passed is not True
    ):
        _fail("hip_fgmres_terminal_metric_summary_invalid", "/summary")
    for name in ("rhs_linf", "load_scale", "maximum_record_bound_ratio"):
        value = getattr(summary, name)
        if (
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        ):
            _fail("hip_fgmres_terminal_metric_summary_invalid", f"/summary/{name}")
    if (
        summary.load_scale != max(1.0, summary.rhs_linf)
        or summary.maximum_record_bound_ratio > 1.0
    ):
        _fail("hip_fgmres_terminal_metric_summary_bound_invalid", "/summary")


def _receipt_payload(
    receipt: HipFgmresTerminalMetricParityReceiptV2,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "parity_id": receipt.parity_id,
        "bindings": receipt.bindings.to_dict(),
        "records": [row.to_dict() for row in receipt.records],
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
    raise HipFgmresTerminalMetricParityV2Error(code, path, message)


__all__ = [
    "HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2",
    "HIP_FGMRES_TERMINAL_METRIC_PARITY_EVIDENCE_SCOPE_V2",
    "HIP_FGMRES_TERMINAL_METRIC_PARITY_SCHEMA_VERSION_V2",
    "HipFgmresTerminalMetricParityBindingsV2",
    "HipFgmresTerminalMetricParityClaimsV2",
    "HipFgmresTerminalMetricParityCompatibilityV2",
    "HipFgmresTerminalMetricParityReceiptV2",
    "HipFgmresTerminalMetricParityRecordV2",
    "HipFgmresTerminalMetricParityResultV2",
    "HipFgmresTerminalMetricParitySummaryV2",
    "HipFgmresTerminalMetricParityV2Error",
    "replay_hip_fgmres_detached_terminal_metric_parity_v2",
    "validate_hip_fgmres_terminal_metric_parity_receipt_v2",
    "validate_hip_fgmres_terminal_metric_parity_result_v2",
]
