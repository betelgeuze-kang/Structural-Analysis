"""Retained nonconverged HIP FGMRES completion to ``DiagnosticIRV1``.

The bridge consumes the exact process-local model-case authority while the
completion-export context is live, but it never performs another solve,
export, device allocation, copy, launch, or synchronization.  Only an exact
``max_iterations`` / ``max_iterations_exhausted`` source is accepted.  Its
last completed true-residual checkpoint is represented as an evaluated trial
and is rolled back to the canonical accepted state; no new committed analysis
state is created.

The returned bridge retains value-only copies of ``solution_x``,
``true_residual``, and ``solve_record`` plus the sparse plan and StateIR
snapshots.  Detached validation therefore remains possible after the live HIP
context closes.  Serialized DiagnosticIR provenance remains an unsigned hash
commitment, not standalone hardware authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import threading
from typing import Any, NoReturn
import weakref

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.diagnostic_ir_v1 import (
    DiagnosticIRV1,
    DiagnosticIRV1Counters,
    DiagnosticIRV1Error,
    DiagnosticIRV1Metrics,
    DiagnosticIRV1Policy,
    DiagnosticIRV1RestartRecord,
    DiagnosticIRV1Termination,
    DiagnosticSourceProvenanceV1,
    _issue_bridge_diagnostic_ir_v1_ready,
    build_diagnostic_ir_v1,
    validate_diagnostic_ir_v1,
    validate_diagnostic_ir_v1_physics,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    ExecutionPlanV2Error,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    StateIRError,
    create_initial_state,
    open_trial_state,
    rollback_trial_state,
    validate_state_ir,
)

from .fgmres_model_case_parity_v1 import HipFgmresModelCaseParityResultV1
from .fgmres_result_ir_v2 import (
    HipFgmresResultIRV2Error,
    _LiveAuthorityCaptureV2,
    _capture_live_authority,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeCountersV1,
    HipFgmresTerminalOutcomeMetricsV1,
    HipFgmresTerminalOutcomeObservationV1Error,
    HipFgmresTerminalOutcomePolicySnapshotV1,
    HipFgmresTerminalOutcomeRestartRowV1,
    HipFgmresTerminalOutcomeV1,
    decode_hip_fgmres_detached_completion_payload_v1,
)


HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE = (
    "hip_fgmres_retained_max_iterations_diagnostic_ir_v1"
)


class HipFgmresDiagnosticIRV1Error(ValueError):
    """Stable fail-closed HIP FGMRES DiagnosticIR bridge error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _DiagnosticLiveCaptureV1:
    """Transient live authority plus the third completion-export payload."""

    base: _LiveAuthorityCaptureV2
    solve_record: bytes
    policy: HipFgmresTerminalOutcomePolicySnapshotV1
    outcome: Any
    outcome_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresDiagnosticIRDetachedSourceSealV1:
    """Value-only source seal; it owns no live model-case or HIP context."""

    _mint: object
    _source_case_identity_token: object
    capability_profile: str
    authority_snapshot_hash: str
    source_execution_plan_identity: int
    source_execution_plan_id: str
    source_execution_plan_hash: str
    cpu_result_hash: str
    cpu_iteration_count: int
    case_id: str
    source_schema_version: str
    case_parity_receipt_hash: str
    terminal_observation_id: str
    terminal_observation_receipt_hash: str
    terminal_outcome_hash: str
    completion_export_context_id: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    source_binding_hash: str
    device_identity_receipt_hash: str
    solution_payload_sha256: str
    true_residual_payload_sha256: str
    solve_record_payload_sha256: str
    solution_x: bytes
    true_residual: bytes
    solve_record: bytes
    terminal_policy: HipFgmresTerminalOutcomePolicySnapshotV1
    source_provenance: DiagnosticSourceProvenanceV1
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    rollback_state_hash: str
    diagnostic_ir_hash: str
    termination_hash: str
    capture_hash: str


@dataclass(frozen=True, repr=False, eq=False)
class HipFgmresDiagnosticIRBridgeResultV1:
    """Detached, post-close-validatable nonconverged DiagnosticIR bridge."""

    receipt: DiagnosticIRV1
    accepted_state: StateIR
    evaluated_trial_state: StateIR
    rollback_state: StateIR
    _source_execution_plan: ExecutionPlanV2
    _source_seal: _HipFgmresDiagnosticIRDetachedSourceSealV1

    @property
    def diagnostic_ir(self) -> DiagnosticIRV1:
        return self.receipt

    @property
    def source_execution_plan(self) -> ExecutionPlanV2:
        return self._source_execution_plan

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_diagnostic_ir_v1(self)
        return self.receipt.to_manifest()


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresDiagnosticIRBridgeIssuanceV1:
    """Exact-object issuance retained without owning the source case."""

    mint: object
    seal: _HipFgmresDiagnosticIRDetachedSourceSealV1
    receipt: DiagnosticIRV1
    accepted_state: StateIR
    evaluated_trial_state: StateIR
    rollback_state: StateIR
    source_execution_plan: ExecutionPlanV2
    source_provenance: DiagnosticSourceProvenanceV1
    diagnostic_ir_hash: str
    capture_hash: str
    provenance_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    rollback_state_hash: str
    source_case_identity_token: object


_DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK = threading.RLock()
_DIAGNOSTIC_BRIDGE_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresDiagnosticIRBridgeResultV1,
    _HipFgmresDiagnosticIRBridgeIssuanceV1,
] = weakref.WeakKeyDictionary()
_ZERO_HASH = "sha256:" + "0" * 64
_SOURCE_L2_RELATIVE_TOLERANCE = 64.0 * float(np.finfo(np.float64).eps)


def build_hip_fgmres_diagnostic_ir_v1(
    case_result: HipFgmresModelCaseParityResultV1,
    *,
    accepted_state: StateIR | None = None,
    diagnostic_id: str = "Diagnostic.hip-fgmres-max-iterations.v1",
) -> HipFgmresDiagnosticIRBridgeResultV1:
    """Materialize one exact retained ``max_iterations`` diagnostic."""

    if type(case_result) is not HipFgmresModelCaseParityResultV1:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_case_result_type_invalid",
            "/source/case_result",
        )
    first = _capture_diagnostic_live_authority(case_result)
    _require_exact_max_iterations_source(first)
    plan = first.base.plan
    initial = _canonical_initial_state(plan, accepted_state)
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    partial_free = _f64_payload(
        first.base.solution_x,
        int(free.size),
        "/source/completion_export/solution_x",
    )
    exported_residual = _f64_payload(
        first.base.true_residual,
        int(free.size),
        "/source/completion_export/true_residual",
    )
    full_partial = np.zeros(plan.dof_count, dtype="<f8")
    full_partial[free] = partial_free
    full_partial[constrained] = 0.0

    try:
        trial = open_trial_state(
            initial,
            full_partial,
            load_step=1,
            iteration=first.base.cpu_result.iteration_count,
            load_factor=1.0,
            expected_plan=plan,
        )
        rolled_back = rollback_trial_state(initial, trial, expected_plan=plan)
    except StateIRError as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_state_transition_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if rolled_back is not initial:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_rollback_identity_invalid",
            "/states/rollback",
        )

    termination = _diagnostic_termination(first, full_partial, exported_residual)
    provenance = _source_provenance(first)
    try:
        diagnostic = build_diagnostic_ir_v1(
            plan,
            initial,
            trial,
            full_partial,
            exported_residual,
            termination,
            provenance,
            diagnostic_id=diagnostic_id,
        )
    except DiagnosticIRV1Error as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_materialization_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    second = _capture_diagnostic_live_authority(case_result)
    _require_same_live_authority(first, second)
    diagnostic = _issue_bridge_diagnostic_ir_v1_ready(diagnostic)
    seal = _make_detached_seal(
        first,
        provenance=provenance,
        accepted_state=initial,
        evaluated_trial_state=trial,
        rollback_state=rolled_back,
        diagnostic=diagnostic,
    )
    result = HipFgmresDiagnosticIRBridgeResultV1(
        receipt=diagnostic,
        accepted_state=initial,
        evaluated_trial_state=trial,
        rollback_state=rolled_back,
        _source_execution_plan=plan,
        _source_seal=seal,
    )
    issuance = _HipFgmresDiagnosticIRBridgeIssuanceV1(
        mint=seal._mint,
        seal=seal,
        receipt=diagnostic,
        accepted_state=initial,
        evaluated_trial_state=trial,
        rollback_state=rolled_back,
        source_execution_plan=plan,
        source_provenance=provenance,
        diagnostic_ir_hash=diagnostic.diagnostic_ir_hash,
        capture_hash=seal.capture_hash,
        provenance_hash=canonical_hash(provenance.to_dict()),
        accepted_state_hash=initial.state_hash,
        evaluated_trial_state_hash=trial.state_hash,
        rollback_state_hash=rolled_back.state_hash,
        source_case_identity_token=seal._source_case_identity_token,
    )
    with _DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK:
        if result in _DIAGNOSTIC_BRIDGE_ISSUANCES:  # pragma: no cover
            _fail(
                "hip_fgmres_diagnostic_ir_v1_issuance_duplicate",
                "/source/issuance",
            )
        _DIAGNOSTIC_BRIDGE_ISSUANCES[result] = issuance
    try:
        return validate_hip_fgmres_diagnostic_ir_v1(result)
    except BaseException:
        with _DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK:
            if _DIAGNOSTIC_BRIDGE_ISSUANCES.get(result) is issuance:
                del _DIAGNOSTIC_BRIDGE_ISSUANCES[result]
        raise


def validate_hip_fgmres_diagnostic_ir_v1(
    result: HipFgmresDiagnosticIRBridgeResultV1,
) -> HipFgmresDiagnosticIRBridgeResultV1:
    """Replay detached bytes, sparse physics, state rollback, and issuance."""

    if type(result) is not HipFgmresDiagnosticIRBridgeResultV1:
        _fail("hip_fgmres_diagnostic_ir_v1_result_type_invalid", "/")
    if (
        type(result.receipt) is not DiagnosticIRV1
        or type(result.accepted_state) is not StateIR
        or type(result.evaluated_trial_state) is not StateIR
        or type(result.rollback_state) is not StateIR
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_result_container_invalid",
            "/",
        )
    seal = result._source_seal
    plan = result._source_execution_plan
    if (
        type(seal) is not _HipFgmresDiagnosticIRDetachedSourceSealV1
        or type(plan) is not ExecutionPlanV2
        or type(seal._mint) is not object
        or type(seal._source_case_identity_token) is not object
    ):
        _fail("hip_fgmres_diagnostic_ir_v1_source_seal_invalid", "/source/seal")
    try:
        validate_execution_plan_v2(plan)
    except ExecutionPlanV2Error as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    try:
        validate_diagnostic_ir_v1(result.receipt)
    except DiagnosticIRV1Error as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_receipt_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if (
        seal.capability_profile != HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE
        or seal.source_execution_plan_identity != id(plan)
        or seal.source_execution_plan_id != plan.plan_id
        or seal.source_execution_plan_hash != plan.plan_hash
        or seal.capture_hash != canonical_hash(_detached_seal_payload(seal))
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_source_seal_hash_mismatch",
            "/source/seal",
        )
    if (
        type(seal.solution_x) is not bytes
        or type(seal.true_residual) is not bytes
        or type(seal.solve_record) is not bytes
        or len(seal.solution_x) != 8 * len(plan.free_dofs)
        or len(seal.true_residual) != 8 * len(plan.free_dofs)
        or sha256_prefixed(seal.solution_x) != seal.solution_payload_sha256
        or sha256_prefixed(seal.true_residual) != seal.true_residual_payload_sha256
        or sha256_prefixed(seal.solve_record) != seal.solve_record_payload_sha256
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_detached_payload_invalid",
            "/source/seal/payloads",
        )
    decoded = _decode_detached_outcome(
        solution_x=seal.solution_x,
        true_residual=seal.true_residual,
        solve_record=seal.solve_record,
        free_dof_count=len(plan.free_dofs),
        maximum_restart_count=seal.terminal_policy.maximum_restart_count,
        policy=seal.terminal_policy,
    )
    if canonical_hash(_outcome_payload(decoded)) != seal.terminal_outcome_hash:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_detached_outcome_mismatch",
            "/source/seal/solve_record",
        )
    _validate_terminal_policy_against_termination(
        seal.terminal_policy,
        result.receipt.termination,
    )
    _validate_decoded_against_termination(decoded, result.receipt.termination)
    _validate_detached_state_lineage(result, seal, plan)
    provenance = result.receipt.source_provenance
    if (
        provenance is not seal.source_provenance
        or provenance.case_id != seal.case_id
        or provenance.case_parity_receipt_hash != seal.case_parity_receipt_hash
        or provenance.terminal_observation_receipt_hash
        != seal.terminal_observation_receipt_hash
        or provenance.completion_export_receipt_hash
        != seal.completion_export_receipt_hash
        or provenance.completion_export_payload_hash
        != seal.completion_export_payload_hash
        or provenance.device_identity_receipt_hash != seal.device_identity_receipt_hash
        or provenance.source_schema_version != seal.source_schema_version
        or provenance.cpu_result_hash != seal.cpu_result_hash
        or provenance.terminal_outcome_hash != seal.terminal_outcome_hash
        or provenance.terminal_observation_id != seal.terminal_observation_id
        or provenance.completion_export_context_id != seal.completion_export_context_id
        or provenance.source_binding_hash != seal.source_binding_hash
        or provenance.solution_payload_sha256 != seal.solution_payload_sha256
        or provenance.exported_free_residual_payload_sha256
        != seal.true_residual_payload_sha256
        or provenance.solve_record_payload_sha256 != seal.solve_record_payload_sha256
        or result.receipt.diagnostic_ir_hash != seal.diagnostic_ir_hash
        or canonical_hash(result.receipt.termination.to_dict()) != seal.termination_hash
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_detached_provenance_mismatch",
            "/source/provenance",
        )
    try:
        validate_diagnostic_ir_v1_physics(
            result.receipt,
            expected_plan=plan,
            expected_accepted_state=result.accepted_state,
            expected_evaluated_trial_state=result.evaluated_trial_state,
        )
    except DiagnosticIRV1Error as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_detached_replay_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    with _DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK:
        issuance = _DIAGNOSTIC_BRIDGE_ISSUANCES.get(result)
    if type(issuance) is not _HipFgmresDiagnosticIRBridgeIssuanceV1:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_issuance_unavailable",
            "/source/issuance",
        )
    if (
        issuance.mint is not seal._mint
        or issuance.source_case_identity_token is not seal._source_case_identity_token
        or issuance.seal is not seal
        or issuance.receipt is not result.receipt
        or issuance.accepted_state is not result.accepted_state
        or issuance.evaluated_trial_state is not result.evaluated_trial_state
        or issuance.rollback_state is not result.rollback_state
        or issuance.source_execution_plan is not plan
        or issuance.source_provenance is not provenance
        or issuance.diagnostic_ir_hash != result.receipt.diagnostic_ir_hash
        or issuance.capture_hash != seal.capture_hash
        or issuance.provenance_hash != canonical_hash(provenance.to_dict())
        or issuance.accepted_state_hash != result.accepted_state.state_hash
        or issuance.evaluated_trial_state_hash
        != result.evaluated_trial_state.state_hash
        or issuance.rollback_state_hash != result.rollback_state.state_hash
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_issuance_binding_mismatch",
            "/source/issuance",
        )
    return result


def _validate_hip_fgmres_diagnostic_ir_v1_against_live_case(
    result: HipFgmresDiagnosticIRBridgeResultV1,
    case_result: HipFgmresModelCaseParityResultV1,
) -> HipFgmresDiagnosticIRBridgeResultV1:
    """Bind an issued diagnostic to its exact still-live source case."""

    validate_hip_fgmres_diagnostic_ir_v1(result)
    if type(case_result) is not HipFgmresModelCaseParityResultV1:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_live_case_type_invalid",
            "/source/live_case",
        )
    capture = _capture_diagnostic_live_authority(case_result)
    _require_exact_max_iterations_source(capture)
    with _DIAGNOSTIC_BRIDGE_ISSUANCE_LOCK:
        issuance = _DIAGNOSTIC_BRIDGE_ISSUANCES.get(result)
    if type(issuance) is not _HipFgmresDiagnosticIRBridgeIssuanceV1:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_issuance_unavailable",
            "/source/issuance",
        )
    seal = result._source_seal
    if (
        issuance.source_case_identity_token
        is not capture.base.source_case_identity_token
        or issuance.source_case_identity_token is not seal._source_case_identity_token
        or capture.base.plan is not result.source_execution_plan
        or capture.base.receipt.receipt_hash != seal.case_parity_receipt_hash
        or capture.base.receipt.case_id != seal.case_id
        or capture.base.receipt.schema_version != seal.source_schema_version
        or capture.base.observation_result.receipt.observation_id
        != seal.terminal_observation_id
        or capture.base.receipt.bindings.completion_export_context_id
        != seal.completion_export_context_id
        or capture.base.export_result.receipt.bindings.source_binding_hash
        != seal.source_binding_hash
        or sha256_prefixed(capture.base.solution_x) != seal.solution_payload_sha256
        or sha256_prefixed(capture.base.true_residual)
        != seal.true_residual_payload_sha256
        or sha256_prefixed(capture.solve_record) != seal.solve_record_payload_sha256
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_live_case_identity_mismatch",
            "/source/live_case",
        )
    return result


def _capture_diagnostic_live_authority(
    case_result: HipFgmresModelCaseParityResultV1,
) -> _DiagnosticLiveCaptureV1:
    try:
        base = _capture_live_authority(case_result)
    except HipFgmresResultIRV2Error as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_live_authority_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    export_result = base.export_result
    published = base.published_result
    observation = base.observation_result.receipt
    try:
        solve_record = published.solve_record
        policy = observation.policy
        source_outcome = observation.outcome
        outcome_hash = observation.outcome_hash
    except AttributeError as exc:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_live_source_incomplete",
            "/source/authority",
            type(exc).__name__,
        )
    if (
        type(solve_record) is not bytes
        or solve_record is not export_result.solve_record
        or published.solve_record is not export_result.solve_record
        or type(policy) is not HipFgmresTerminalOutcomePolicySnapshotV1
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_solve_record_identity_invalid",
            "/source/completion_export/solve_record",
        )
    copied = memoryview(solve_record).tobytes()
    decoded = _decode_detached_outcome(
        solution_x=base.solution_x,
        true_residual=base.true_residual,
        solve_record=copied,
        free_dof_count=len(base.plan.free_dofs),
        maximum_restart_count=policy.maximum_restart_count,
        policy=policy,
    )
    decoded_hash = canonical_hash(_outcome_payload(decoded))
    if (
        decoded_hash != canonical_hash(_outcome_payload(source_outcome))
        or outcome_hash != decoded_hash
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_solve_record_outcome_mismatch",
            "/source/terminal_observation/outcome",
        )
    return _DiagnosticLiveCaptureV1(
        base=base,
        solve_record=copied,
        policy=replace(policy),
        outcome=decoded,
        outcome_hash=decoded_hash,
    )


def _require_exact_max_iterations_source(capture: _DiagnosticLiveCaptureV1) -> None:
    base = capture.base
    receipt = base.receipt
    cpu = base.cpu_result
    observation = base.observation_result.receipt
    outcome = capture.outcome
    export = base.export_result.receipt
    device = base.device_identity_result.receipt
    published = base.published_result
    plan = base.plan
    if any(
        value != "hip"
        for value in (
            receipt.actual_backend,
            observation.actual_backend,
            export.actual_backend,
            device.actual_backend,
        )
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_backend_invalid",
            "/source/actual_backend",
        )
    if (
        cpu.status != "max_iterations"
        or cpu.termination_code != "max_iterations_exhausted"
        or cpu.solver_tolerance_passed is not False
        or cpu.authoritative_plan_tolerance_passed is not False
        or cpu.iteration_count != cpu.policy.max_iterations
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_cpu_status_invalid",
            "/source/cpu_result/status",
        )
    policy = capture.policy
    cpu_policy = cpu.policy
    if (
        policy.restart_dimension != cpu_policy.restart_dimension
        or policy.max_iterations != cpu_policy.max_iterations
        or policy.maximum_restart_count != receipt.dimensions.maximum_restart_count
        or policy.stagnation_checkpoint_limit != cpu_policy.stagnation_checkpoint_limit
        or policy.absolute_tolerance != cpu_policy.absolute_tolerance
        or policy.relative_tolerance != cpu_policy.relative_tolerance
        or policy.authoritative_tolerance != plan.residual_tolerance
        or policy.stagnation_relative_tolerance
        != cpu_policy.stagnation_relative_tolerance
        or policy.divergence_factor != cpu_policy.divergence_factor
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_terminal_policy_invalid",
            "/source/terminal_observation/policy",
        )
    if (
        observation.status != "terminal_not_converged"
        or outcome.outcome_class != "not_converged"
        or outcome.active != 0
        or outcome.terminal_status != "max_iterations"
        or outcome.termination_code != "max_iterations_exhausted"
        or outcome.device_error_bits != 0
        or outcome.device_error_names != ()
        or outcome.record_metrics_authoritative is not True
        or outcome.metrics is None
        or outcome.solution_x_all_finite is not True
        or outcome.true_residual_all_finite is not True
        or outcome.true_residual_record_metrics_match is not True
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_terminal_outcome_invalid",
            "/source/terminal_observation/outcome",
        )
    counters = outcome.counters
    populated = tuple(row for row in outcome.restart_rows if row.populated)
    if (
        counters.scheduled_iterations != cpu_policy.max_iterations
        or counters.scheduled_restarts != policy.maximum_restart_count
        or counters.effective_iterations != cpu.iteration_count
        or counters.effective_restarts != cpu.restart_count
        or counters.operator_apply_count != cpu.operator_apply_count
        or counters.preconditioner_apply_count != cpu.preconditioner_apply_count
        or len(populated) != len(cpu.history)
        or not populated
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_terminal_counter_invalid",
            "/source/terminal_observation/outcome/counters",
        )
    bindings = receipt.bindings
    solution_hash = sha256_prefixed(base.solution_x)
    residual_hash = sha256_prefixed(base.true_residual)
    record_hash = sha256_prefixed(capture.solve_record)
    export_buffers = {row.role: row for row in export.buffers}
    if set(export_buffers) != {"solution_x", "true_residual", "solve_record"}:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_export_buffers_invalid",
            "/source/completion_export/buffers",
        )
    if (
        bindings.execution_plan_id != plan.plan_id
        or bindings.execution_plan_hash != plan.plan_hash
        or bindings.cpu_result_hash != cpu.result_hash
        or bindings.terminal_observation_id != observation.observation_id
        or bindings.terminal_observation_receipt_hash != observation.receipt_hash
        or bindings.completion_export_context_id
        != observation.bindings.completion_export_context_id
        or bindings.completion_export_receipt_hash != export.receipt_hash
        or bindings.completion_export_payload_hash != export.payload_hash
        or bindings.device_identity_receipt_hash != device.receipt_hash
        or receipt.dimensions.global_dof_count != plan.dof_count
        or receipt.dimensions.free_dof_count != len(plan.free_dofs)
        or export.dimensions.free_dof_count != len(plan.free_dofs)
        or export.dimensions.solution_byte_count != len(base.solution_x)
        or export.dimensions.true_residual_byte_count != len(base.true_residual)
        or export.dimensions.solve_record_byte_count != len(capture.solve_record)
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_lineage_binding_mismatch",
            "/source/bindings",
        )
    if (
        base.export_result.payload_hash != export.payload_hash
        or published.receipt_hash != export.receipt_hash
        or published.payload_hash != export.payload_hash
        or published.buffer_payload_hashes
        != (solution_hash, residual_hash, record_hash)
        or export_buffers["solution_x"].payload_sha256 != solution_hash
        or export_buffers["true_residual"].payload_sha256 != residual_hash
        or export_buffers["solve_record"].payload_sha256 != record_hash
        or observation.bindings.solution_payload_sha256 != solution_hash
        or observation.bindings.true_residual_payload_sha256 != residual_hash
        or observation.bindings.solve_record_payload_sha256 != record_hash
        or observation.bindings.completion_export_source_binding_hash
        != export.bindings.source_binding_hash
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_payload_binding_mismatch",
            "/source/completion_export/payloads",
        )
    if (
        bindings.compiled_architecture
        != device.architecture.expected_compiled.normalized
        or bindings.runtime_architecture_base != device.architecture.runtime.base
        or bindings.device_ordinal != device.device.selected_ordinal
        or bindings.device_uuid_bytes_hex != device.device.uuid_bytes_hex
        or bindings.device_pci_bdf != device.device.pci_bdf
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_device_binding_mismatch",
            "/source/device_identity",
        )
    for claims, path in (
        (receipt.claims, "/source/model_case/claims"),
        (observation.claims, "/source/terminal_observation/claims"),
        (export.claims, "/source/completion_export/claims"),
    ):
        if claims.solution_ready is not False or claims.result_ir_ready is not False:
            _fail(
                "hip_fgmres_diagnostic_ir_v1_upstream_claim_invalid",
                path,
            )


def _require_same_live_authority(
    first: _DiagnosticLiveCaptureV1,
    second: _DiagnosticLiveCaptureV1,
) -> None:
    left = first.base
    right = second.base
    if (
        right.authority is not left.authority
        or right.source_case_identity_token is not left.source_case_identity_token
        or right.receipt is not left.receipt
        or right.plan is not left.plan
        or right.cpu_result is not left.cpu_result
        or right.observation_result is not left.observation_result
        or right.device_identity_result is not left.device_identity_result
        or right.export_result is not left.export_result
        or right.publication_authority is not left.publication_authority
        or right.published_result is not left.published_result
        or right.published_result.solution_x is not left.published_result.solution_x
        or right.published_result.true_residual
        is not left.published_result.true_residual
        or right.published_result.solve_record is not left.published_result.solve_record
        or right.authority.snapshot != left.authority.snapshot
        or right.authority_snapshot_hash != left.authority_snapshot_hash
        or right.solution_x != left.solution_x
        or right.true_residual != left.true_residual
        or second.solve_record != first.solve_record
        or second.policy != first.policy
        or second.outcome_hash != first.outcome_hash
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_live_authority_changed",
            "/source/authority",
        )
    _require_exact_max_iterations_source(second)


def _canonical_initial_state(
    plan: ExecutionPlanV2,
    candidate: StateIR | None,
) -> StateIR:
    expected = create_initial_state(plan)
    if candidate is None:
        return expected
    if type(candidate) is not StateIR:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_accepted_state_type_invalid",
            "/states/accepted",
        )
    try:
        validate_state_ir(candidate, expected_plan=plan)
    except StateIRError as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_accepted_state_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if candidate.state_hash != expected.state_hash:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_warm_start_unsupported",
            "/states/accepted",
        )
    return candidate


def _diagnostic_termination(
    capture: _DiagnosticLiveCaptureV1,
    full_partial: np.ndarray,
    exported_residual: np.ndarray,
) -> DiagnosticIRV1Termination:
    base = capture.base
    outcome = capture.outcome
    source_policy = base.cpu_result.policy
    plan = base.plan
    full_residual = np.asarray(plan.residual(full_partial), dtype="<f8")
    free_residual = full_residual[plan.array("free_dofs")]
    rhs = plan.array("global_load")[plan.array("free_dofs")]
    load_scale = max(1.0, _linf(rhs))
    initial_l2 = _stable_l2(rhs)
    solver_tolerance = max(
        source_policy.absolute_tolerance,
        source_policy.relative_tolerance * initial_l2,
    )
    exported_l2 = _stable_l2(exported_residual)
    exported_linf = _linf(exported_residual)
    policy = DiagnosticIRV1Policy(
        restart_dimension=source_policy.restart_dimension,
        max_iterations=source_policy.max_iterations,
        absolute_tolerance=source_policy.absolute_tolerance,
        relative_tolerance=source_policy.relative_tolerance,
        stagnation_checkpoint_limit=source_policy.stagnation_checkpoint_limit,
        stagnation_relative_tolerance=source_policy.stagnation_relative_tolerance,
        divergence_factor=source_policy.divergence_factor,
        policy_hash=source_policy.policy_hash,
    )
    counters = DiagnosticIRV1Counters(
        iteration_count=outcome.counters.effective_iterations,
        restart_count=outcome.counters.effective_restarts,
        operator_apply_count=outcome.counters.operator_apply_count,
        preconditioner_apply_count=outcome.counters.preconditioner_apply_count,
    )
    metrics = DiagnosticIRV1Metrics(
        initial_residual_l2=initial_l2,
        solver_tolerance_l2=solver_tolerance,
        final_residual_l2=exported_l2,
        final_residual_linf=exported_linf,
        scaled_true_residual=exported_linf / load_scale,
        load_scale=load_scale,
        free_residual_l2=_stable_l2(free_residual),
        free_residual_linf=_linf(free_residual),
        scaled_free_residual=_linf(free_residual) / load_scale,
        exported_free_residual_l2=exported_l2,
        exported_free_residual_linf=exported_linf,
        scaled_exported_free_residual=exported_linf / load_scale,
        solver_tolerance_passed=False,
        authoritative_plan_tolerance_passed=False,
    )
    history = tuple(
        DiagnosticIRV1RestartRecord(
            restart_index=row.restart_index,
            start_iteration=row.start_iteration,
            end_iteration=row.end_iteration,
            arnoldi_step_count=row.arnoldi_step_count,
            preconditioner_apply_count=row.arnoldi_step_count,
            reorthogonalization_count=row.reorthogonalization_count,
            estimated_residual_l2=row.estimated_residual_l2,
            true_residual_l2=row.true_residual_l2,
            true_residual_linf=row.true_residual_linf,
            scaled_true_residual=row.scaled_true_residual,
            solution_update_l2=row.solution_update_l2,
            termination_hint=row.termination_hint,
        )
        for row in outcome.restart_rows
        if row.populated
    )
    return DiagnosticIRV1Termination(
        status="max_iterations",
        termination_code="max_iterations_exhausted",
        policy=policy,
        counters=counters,
        metrics=metrics,
        history=history,
    )


def _source_provenance(
    capture: _DiagnosticLiveCaptureV1,
) -> DiagnosticSourceProvenanceV1:
    base = capture.base
    bindings = base.receipt.bindings
    observation = base.observation_result.receipt
    export = base.export_result.receipt
    return DiagnosticSourceProvenanceV1(
        case_id=base.receipt.case_id,
        case_parity_receipt_hash=base.receipt.receipt_hash,
        terminal_observation_receipt_hash=(bindings.terminal_observation_receipt_hash),
        completion_export_receipt_hash=bindings.completion_export_receipt_hash,
        completion_export_payload_hash=bindings.completion_export_payload_hash,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        source_schema_version=base.receipt.schema_version,
        cpu_result_hash=base.cpu_result.result_hash,
        terminal_outcome_hash=capture.outcome_hash,
        terminal_observation_id=observation.observation_id,
        completion_export_context_id=bindings.completion_export_context_id,
        source_binding_hash=export.bindings.source_binding_hash,
        actual_backend="hip",
        solution_payload_sha256=sha256_prefixed(base.solution_x),
        exported_free_residual_payload_sha256=sha256_prefixed(base.true_residual),
        solve_record_payload_sha256=sha256_prefixed(capture.solve_record),
        compiled_architecture=bindings.compiled_architecture,
        runtime_architecture_base=bindings.runtime_architecture_base,
        device_ordinal=bindings.device_ordinal,
        device_uuid_bytes_hex=bindings.device_uuid_bytes_hex,
        device_pci_bdf=bindings.device_pci_bdf,
        source_kind="fgmres_partial_iterate",
        additional_device_operation_count=0,
        additional_d2h_operation_count=0,
        additional_solve_count=0,
        additional_export_count=0,
        fallback_count=0,
        live_authority_serialized=False,
        signed_evidence=False,
        standalone_provenance=False,
    )


def _make_detached_seal(
    capture: _DiagnosticLiveCaptureV1,
    *,
    provenance: DiagnosticSourceProvenanceV1,
    accepted_state: StateIR,
    evaluated_trial_state: StateIR,
    rollback_state: StateIR,
    diagnostic: DiagnosticIRV1,
) -> _HipFgmresDiagnosticIRDetachedSourceSealV1:
    base = capture.base
    bindings = base.receipt.bindings
    draft = _HipFgmresDiagnosticIRDetachedSourceSealV1(
        _mint=object(),
        _source_case_identity_token=base.source_case_identity_token,
        capability_profile=HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE,
        authority_snapshot_hash=base.authority_snapshot_hash,
        source_execution_plan_identity=id(base.plan),
        source_execution_plan_id=base.plan.plan_id,
        source_execution_plan_hash=base.plan.plan_hash,
        cpu_result_hash=base.cpu_result.result_hash,
        cpu_iteration_count=base.cpu_result.iteration_count,
        case_id=base.receipt.case_id,
        source_schema_version=base.receipt.schema_version,
        case_parity_receipt_hash=base.receipt.receipt_hash,
        terminal_observation_id=base.observation_result.receipt.observation_id,
        terminal_observation_receipt_hash=(bindings.terminal_observation_receipt_hash),
        terminal_outcome_hash=capture.outcome_hash,
        completion_export_context_id=bindings.completion_export_context_id,
        completion_export_receipt_hash=bindings.completion_export_receipt_hash,
        completion_export_payload_hash=bindings.completion_export_payload_hash,
        source_binding_hash=base.export_result.receipt.bindings.source_binding_hash,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        solution_payload_sha256=sha256_prefixed(base.solution_x),
        true_residual_payload_sha256=sha256_prefixed(base.true_residual),
        solve_record_payload_sha256=sha256_prefixed(capture.solve_record),
        solution_x=bytes(bytearray(base.solution_x)),
        true_residual=bytes(bytearray(base.true_residual)),
        solve_record=bytes(bytearray(capture.solve_record)),
        terminal_policy=replace(capture.policy),
        source_provenance=provenance,
        accepted_state_hash=accepted_state.state_hash,
        evaluated_trial_state_hash=evaluated_trial_state.state_hash,
        rollback_state_hash=rollback_state.state_hash,
        diagnostic_ir_hash=diagnostic.diagnostic_ir_hash,
        termination_hash=canonical_hash(diagnostic.termination.to_dict()),
        capture_hash=_ZERO_HASH,
    )
    return replace(draft, capture_hash=canonical_hash(_detached_seal_payload(draft)))


def _validate_detached_state_lineage(
    result: HipFgmresDiagnosticIRBridgeResultV1,
    seal: _HipFgmresDiagnosticIRDetachedSourceSealV1,
    plan: ExecutionPlanV2,
) -> None:
    try:
        validate_state_ir(result.accepted_state, expected_plan=plan)
        validate_state_ir(result.evaluated_trial_state, expected_plan=plan)
        validate_state_ir(result.rollback_state, expected_plan=plan)
    except StateIRError as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_state_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    initial = create_initial_state(plan)
    free_solution = _f64_payload(
        seal.solution_x,
        len(plan.free_dofs),
        "/source/seal/solution_x",
    )
    expected_displacement = np.zeros(plan.dof_count, dtype="<f8")
    expected_displacement[plan.array("free_dofs")] = free_solution
    expected_displacement[plan.array("constrained_dofs")] = 0.0
    if (
        result.accepted_state.state_hash != initial.state_hash
        or result.accepted_state.state_hash != seal.accepted_state_hash
        or result.evaluated_trial_state.state_hash != seal.evaluated_trial_state_hash
        or result.rollback_state is not result.accepted_state
        or result.rollback_state.state_hash != seal.rollback_state_hash
        or result.evaluated_trial_state.role != "trial"
        or result.evaluated_trial_state.parent_state_hash
        != result.accepted_state.state_hash
        or result.evaluated_trial_state.epoch != 1
        or result.evaluated_trial_state.load_step != 1
        or result.evaluated_trial_state.iteration != seal.cpu_iteration_count
        or result.evaluated_trial_state.load_factor != 1.0
        or not np.array_equal(
            result.evaluated_trial_state.displacement_si,
            expected_displacement,
        )
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_state_lineage_mismatch",
            "/states",
        )


def _detached_seal_payload(
    seal: _HipFgmresDiagnosticIRDetachedSourceSealV1,
) -> dict[str, Any]:
    return {
        "capability_profile": seal.capability_profile,
        "authority_snapshot_hash": seal.authority_snapshot_hash,
        "source_execution_plan_identity": seal.source_execution_plan_identity,
        "source_execution_plan_id": seal.source_execution_plan_id,
        "source_execution_plan_hash": seal.source_execution_plan_hash,
        "cpu_result_hash": seal.cpu_result_hash,
        "cpu_iteration_count": seal.cpu_iteration_count,
        "case_id": seal.case_id,
        "source_schema_version": seal.source_schema_version,
        "case_parity_receipt_hash": seal.case_parity_receipt_hash,
        "terminal_observation_id": seal.terminal_observation_id,
        "terminal_observation_receipt_hash": (seal.terminal_observation_receipt_hash),
        "terminal_outcome_hash": seal.terminal_outcome_hash,
        "completion_export_context_id": seal.completion_export_context_id,
        "completion_export_receipt_hash": seal.completion_export_receipt_hash,
        "completion_export_payload_hash": seal.completion_export_payload_hash,
        "source_binding_hash": seal.source_binding_hash,
        "device_identity_receipt_hash": seal.device_identity_receipt_hash,
        "solution_payload_sha256": seal.solution_payload_sha256,
        "true_residual_payload_sha256": seal.true_residual_payload_sha256,
        "solve_record_payload_sha256": seal.solve_record_payload_sha256,
        "solution_x": seal.solution_x.hex(),
        "true_residual": seal.true_residual.hex(),
        "solve_record": seal.solve_record.hex(),
        "terminal_policy": seal.terminal_policy.to_dict(),
        "source_provenance": seal.source_provenance.to_dict(),
        "accepted_state_hash": seal.accepted_state_hash,
        "evaluated_trial_state_hash": seal.evaluated_trial_state_hash,
        "rollback_state_hash": seal.rollback_state_hash,
        "diagnostic_ir_hash": seal.diagnostic_ir_hash,
        "termination_hash": seal.termination_hash,
    }


def _validate_terminal_policy_against_termination(
    policy: HipFgmresTerminalOutcomePolicySnapshotV1,
    termination: DiagnosticIRV1Termination,
) -> None:
    diagnostic = termination.policy
    if (
        type(policy) is not HipFgmresTerminalOutcomePolicySnapshotV1
        or policy.restart_dimension != diagnostic.restart_dimension
        or policy.max_iterations != diagnostic.max_iterations
        or policy.stagnation_checkpoint_limit != diagnostic.stagnation_checkpoint_limit
        or policy.absolute_tolerance != diagnostic.absolute_tolerance
        or policy.relative_tolerance != diagnostic.relative_tolerance
        or policy.stagnation_relative_tolerance
        != diagnostic.stagnation_relative_tolerance
        or policy.divergence_factor != diagnostic.divergence_factor
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_terminal_policy_mismatch",
            "/source/seal/terminal_policy",
        )


def _validate_decoded_against_termination(
    outcome: Any,
    termination: DiagnosticIRV1Termination,
) -> None:
    """Keep the retained record semantically bound to the DiagnosticIR."""

    if (
        type(outcome) is not HipFgmresTerminalOutcomeV1
        or type(outcome.counters) is not HipFgmresTerminalOutcomeCountersV1
        or type(outcome.metrics) is not HipFgmresTerminalOutcomeMetricsV1
        or any(
            type(row) is not HipFgmresTerminalOutcomeRestartRowV1
            for row in outcome.restart_rows
        )
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_decoded_outcome_type_invalid",
            "/source/seal/solve_record",
        )
    if (
        outcome.outcome_class != "not_converged"
        or outcome.active != 0
        or outcome.terminal_status != termination.status
        or outcome.termination_code != termination.termination_code
        or outcome.device_error_bits != 0
        or outcome.device_error_names != ()
        or outcome.record_metrics_authoritative is not True
        or outcome.solution_x_all_finite is not True
        or outcome.true_residual_all_finite is not True
        or outcome.true_residual_record_metrics_match is not True
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_decoded_outcome_mismatch",
            "/source/seal/solve_record/outcome",
        )
    counters = outcome.counters
    diagnostic_counters = termination.counters
    populated = tuple(row for row in outcome.restart_rows if row.populated)
    if (
        counters.effective_iterations != diagnostic_counters.iteration_count
        or counters.effective_restarts != diagnostic_counters.restart_count
        or counters.operator_apply_count != diagnostic_counters.operator_apply_count
        or counters.preconditioner_apply_count
        != diagnostic_counters.preconditioner_apply_count
        or len(populated) != len(termination.history)
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_decoded_counter_mismatch",
            "/source/seal/solve_record/counters",
        )
    for index, (source, diagnostic) in enumerate(
        zip(populated, termination.history, strict=True)
    ):
        if (
            source.restart_index != diagnostic.restart_index
            or source.start_iteration != diagnostic.start_iteration
            or source.end_iteration != diagnostic.end_iteration
            or source.arnoldi_step_count != diagnostic.arnoldi_step_count
            or source.arnoldi_step_count != diagnostic.preconditioner_apply_count
            or source.reorthogonalization_count != diagnostic.reorthogonalization_count
            or source.estimated_residual_l2 != diagnostic.estimated_residual_l2
            or source.true_residual_l2 != diagnostic.true_residual_l2
            or source.true_residual_linf != diagnostic.true_residual_linf
            or source.scaled_true_residual != diagnostic.scaled_true_residual
            or source.solution_update_l2 != diagnostic.solution_update_l2
            or source.termination_hint != diagnostic.termination_hint
        ):
            _fail(
                "hip_fgmres_diagnostic_ir_v1_decoded_history_mismatch",
                f"/source/seal/solve_record/restart_rows/{index}",
            )
    source_metrics = outcome.metrics
    diagnostic_metrics = termination.metrics
    l2_metric_pairs = (
        (source_metrics.initial_residual_l2, diagnostic_metrics.initial_residual_l2),
        (source_metrics.solver_tolerance_l2, diagnostic_metrics.solver_tolerance_l2),
        (source_metrics.final_residual_l2, diagnostic_metrics.final_residual_l2),
        (outcome.observed_true_residual_l2, diagnostic_metrics.final_residual_l2),
    )
    exact_metric_pairs = (
        (source_metrics.final_residual_linf, diagnostic_metrics.final_residual_linf),
        (source_metrics.final_scaled_residual, diagnostic_metrics.scaled_true_residual),
        (outcome.observed_true_residual_linf, diagnostic_metrics.final_residual_linf),
        (
            outcome.observed_true_residual_scaled_linf,
            diagnostic_metrics.scaled_true_residual,
        ),
    )
    if any(
        observed is None
        or not math.isclose(
            float(observed),
            expected,
            rel_tol=_SOURCE_L2_RELATIVE_TOLERANCE,
            abs_tol=0.0,
        )
        for observed, expected in l2_metric_pairs
    ) or any(
        observed is None or float(observed) != expected
        for observed, expected in exact_metric_pairs
    ):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_decoded_metric_mismatch",
            "/source/seal/solve_record/metrics",
        )


def _decode_detached_outcome(**kwargs: Any) -> Any:
    try:
        return decode_hip_fgmres_detached_completion_payload_v1(**kwargs)
    except HipFgmresTerminalOutcomeObservationV1Error as exc:
        raise HipFgmresDiagnosticIRV1Error(
            "hip_fgmres_diagnostic_ir_v1_solve_record_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc


def _outcome_payload(outcome: Any) -> dict[str, Any]:
    try:
        payload = outcome.to_dict()
    except (AttributeError, TypeError) as exc:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_outcome_type_invalid",
            "/source/terminal_observation/outcome",
            type(exc).__name__,
        )
    if type(payload) is not dict:
        _fail(
            "hip_fgmres_diagnostic_ir_v1_outcome_type_invalid",
            "/source/terminal_observation/outcome",
        )
    return payload


def _f64_payload(payload: bytes, count: int, path: str) -> np.ndarray:
    if type(payload) is not bytes or len(payload) != 8 * count:
        _fail("hip_fgmres_diagnostic_ir_v1_payload_extent_invalid", path)
    array = np.frombuffer(payload, dtype="<f8").copy()
    if array.shape != (count,) or not np.isfinite(array).all():
        _fail("hip_fgmres_diagnostic_ir_v1_payload_numeric_invalid", path)
    array[array == 0.0] = 0.0
    return array


def _stable_l2(values: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for raw in np.asarray(values, dtype=np.float64).reshape(-1):
        value = abs(float(raw))
        if not math.isfinite(value):
            _fail(
                "hip_fgmres_diagnostic_ir_v1_metric_nonfinite",
                "/termination/metrics",
            )
        if value == 0.0:
            continue
        if scale < value:
            ratio = 0.0 if scale == 0.0 else scale / value
            sumsq = 1.0 + sumsq * ratio * ratio
            scale = value
        else:
            ratio = value / scale
            sumsq += ratio * ratio
    result = 0.0 if scale == 0.0 else scale * math.sqrt(sumsq)
    if not math.isfinite(result):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_metric_nonfinite",
            "/termination/metrics",
        )
    return result


def _linf(values: np.ndarray) -> float:
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    if array.size == 0:
        return 0.0
    value = float(np.max(np.abs(array)))
    if not math.isfinite(value):
        _fail(
            "hip_fgmres_diagnostic_ir_v1_metric_nonfinite",
            "/termination/metrics",
        )
    return value


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresDiagnosticIRV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE",
    "HipFgmresDiagnosticIRBridgeResultV1",
    "HipFgmresDiagnosticIRV1Error",
    "build_hip_fgmres_diagnostic_ir_v1",
    "validate_hip_fgmres_diagnostic_ir_v1",
]
