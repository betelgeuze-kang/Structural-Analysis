"""Retained HIP FGMRES completion to sparse ``ResultIRV2`` recovery.

This bridge is intentionally a one-way authority boundary.  It consumes the
private, process-local authority minted by model-case parity while the HIP
completion-export context is still live, copies only the two already-exported
host payloads, and performs result recovery through ``ExecutionPlanV2`` on the
CPU.  It never launches, allocates, synchronizes, exports, or solves on a
device.

The returned object retains a detached value seal, the exact sparse plan, and
the three ``StateIR`` snapshots.  Consequently its public validator remains
usable after all HIP contexts have been closed; it does not replay model-case
parity or a CPU FGMRES solve.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import threading
from typing import Any, NoReturn
import weakref

import numpy as np

from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    HipDeviceIdentityResultV1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    ExecutionPlanV2Error,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.result_ir_v2 import (
    ResultIRV2,
    ResultIRV2Error,
    SourceProvenance,
    _issue_bridge_result_ir_v2_ready,
    build_result_ir_v2,
    validate_result_ir_v2_physics,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    StateIRError,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
    validate_state_ir,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceResultV1,
)

from .fgmres_completion_export_v1 import (
    HipFgmresCompletionExportResultV1,
    _CompletionExportModelCaseParityAuthorityV1,
    _CompletionExportPublishedResultAuthorityV1,
)
from .fgmres_model_case_parity_v1 import (
    HipFgmresModelCaseParityReceiptV1,
    HipFgmresModelCaseParityResultV1,
    HipFgmresModelCaseParityV1Error,
    _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1,
)
from .fgmres_model_case_parity_v2 import (
    HipFgmresModelCaseParityReceiptV2,
    HipFgmresModelCaseParityResultV2,
    HipFgmresModelCaseParityV2Error,
    _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2,
)
from .fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeObservationResultV1,
)


__all__ = (
    "HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE",
    "HipFgmresResultIRBridgeResultV2",
    "HipFgmresResultIRV2Error",
    "build_hip_fgmres_result_ir_v2",
    "validate_hip_fgmres_result_ir_v2",
)


HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE = (
    "hip_fgmres_retained_completion_sparse_result_ir_v2"
)


class HipFgmresResultIRV2Error(ValueError):
    """Stable fail-closed HIP FGMRES to ResultIR v2 bridge error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _LiveAuthorityCaptureV2:
    """Transient identity-bearing view; never retained in the result."""

    authority: (
        _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1
        | _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2
    )
    source_case_identity_token: object
    receipt: HipFgmresModelCaseParityReceiptV1 | HipFgmresModelCaseParityReceiptV2
    plan: ExecutionPlanV2
    cpu_result: CpuFgmresReferenceResultV1
    observation_result: HipFgmresTerminalOutcomeObservationResultV1
    device_identity_result: HipDeviceIdentityResultV1
    export_result: HipFgmresCompletionExportResultV1
    publication_authority: _CompletionExportModelCaseParityAuthorityV1
    published_result: _CompletionExportPublishedResultAuthorityV1
    solution_x: bytes
    true_residual: bytes
    authority_snapshot_hash: str


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresResultIRDetachedSourceSealV2:
    """Value-only commitment retained after live HIP authority disappears."""

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
    case_parity_receipt_hash: str
    terminal_observation_receipt_hash: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    solution_payload_sha256: str
    true_residual_payload_sha256: str
    solution_x: bytes
    true_residual: bytes
    source_provenance: SourceProvenance
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str
    result_ir_hash: str
    capture_hash: str


@dataclass(frozen=True, repr=False, eq=False)
class HipFgmresResultIRBridgeResultV2:
    """Detached, post-close-validatable HIP FGMRES ResultIR v2 bridge."""

    receipt: ResultIRV2
    accepted_state: StateIR
    evaluated_trial_state: StateIR
    committed_state: StateIR
    _source_execution_plan: ExecutionPlanV2
    _source_seal: _HipFgmresResultIRDetachedSourceSealV2

    @property
    def result_ir(self) -> ResultIRV2:
        """Explicit alias for consumers that use the contract type name."""

        return self.receipt

    @property
    def source_execution_plan(self) -> ExecutionPlanV2:
        """Return the exact retained sparse plan used for recovery."""

        return self._source_execution_plan

    def to_manifest(self) -> dict[str, Any]:
        """Return the descriptor-only ResultIR manifest after detached replay."""

        validate_hip_fgmres_result_ir_v2(self)
        return self.receipt.to_manifest()


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresResultIRBridgeIssuanceV2:
    """Exact-object process-local issuance retained without owning the result."""

    mint: object
    seal: _HipFgmresResultIRDetachedSourceSealV2
    receipt: ResultIRV2
    accepted_state: StateIR
    evaluated_trial_state: StateIR
    committed_state: StateIR
    source_execution_plan: ExecutionPlanV2
    source_provenance: SourceProvenance
    result_ir_hash: str
    capture_hash: str
    provenance_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str
    source_case_identity_token: object


_BRIDGE_RESULT_ISSUANCE_LOCK = threading.RLock()
_BRIDGE_RESULT_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresResultIRBridgeResultV2,
    _HipFgmresResultIRBridgeIssuanceV2,
] = weakref.WeakKeyDictionary()
_ZERO_HASH = "sha256:" + "0" * 64


def build_hip_fgmres_result_ir_v2(
    case_result: HipFgmresModelCaseParityResultV1,
    *,
    accepted_state: StateIR | None = None,
    result_id: str = "Result.hip-fgmres-linear-static.v2",
) -> HipFgmresResultIRBridgeResultV2:
    """Recover one converged retained HIP completion into ``ResultIRV2``.

    The optional accepted state is intentionally narrow: it must be exactly
    the canonical zero-valued initial ``StateIR`` for the retained plan.  The
    model-case attestation itself is fixed to a zero initial solve, so accepting
    an arbitrary warm start here would break lineage.
    """

    if type(case_result) is not HipFgmresModelCaseParityResultV1:
        _fail(
            "hip_fgmres_result_ir_v2_case_result_type_invalid",
            "/source/case_result",
            "Expected an exact HipFgmresModelCaseParityResultV1.",
        )

    first = _capture_live_authority(case_result)
    plan = first.plan
    _require_converged_native_source(first)

    initial = _canonical_initial_state(plan, accepted_state)
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    solution = _f64_payload(
        first.solution_x,
        int(free.size),
        "/source/completion_export/solution_x",
    )
    exported_residual = _f64_payload(
        first.true_residual,
        int(free.size),
        "/source/completion_export/true_residual",
    )
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[free] = solution
    # Preserve prescribed zero with canonical positive-zero bits even if a
    # future NumPy scatter implementation changes untouched storage behavior.
    displacement[constrained] = 0.0

    try:
        trial = open_trial_state(
            initial,
            displacement,
            load_step=1,
            iteration=first.cpu_result.iteration_count,
            load_factor=1.0,
            expected_plan=plan,
        )
        committed = commit_trial_state(
            initial,
            trial,
            expected_plan=plan,
        )
    except StateIRError as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_state_transition_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    provenance = _source_provenance(first)
    try:
        result_ir = build_result_ir_v2(
            plan,
            trial,
            committed,
            displacement,
            exported_residual,
            provenance,
            result_id=result_id,
        )
    except ResultIRV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_recovery_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    # A second live capture is deliberately after all CPU recovery work.  If
    # cleanup, replacement, or mutation raced the bridge, no detached result is
    # published.
    second = _capture_live_authority(case_result)
    _require_same_live_authority(first, second)
    result_ir = _issue_bridge_result_ir_v2_ready(result_ir)

    seal = _make_detached_seal(
        first,
        provenance=provenance,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        result_ir=result_ir,
    )
    result = HipFgmresResultIRBridgeResultV2(
        receipt=result_ir,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        _source_execution_plan=plan,
        _source_seal=seal,
    )
    issuance = _HipFgmresResultIRBridgeIssuanceV2(
        mint=seal._mint,
        seal=seal,
        receipt=result_ir,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        source_execution_plan=plan,
        source_provenance=provenance,
        result_ir_hash=result_ir.result_ir_hash,
        capture_hash=seal.capture_hash,
        provenance_hash=canonical_hash(provenance.to_dict()),
        accepted_state_hash=initial.state_hash,
        evaluated_trial_state_hash=trial.state_hash,
        committed_state_hash=committed.state_hash,
        source_case_identity_token=seal._source_case_identity_token,
    )
    with _BRIDGE_RESULT_ISSUANCE_LOCK:
        if result in _BRIDGE_RESULT_ISSUANCES:  # pragma: no cover - fresh object
            _fail(
                "hip_fgmres_result_ir_v2_issuance_duplicate",
                "/source/issuance",
            )
        _BRIDGE_RESULT_ISSUANCES[result] = issuance
    try:
        return validate_hip_fgmres_result_ir_v2(result)
    except BaseException:
        with _BRIDGE_RESULT_ISSUANCE_LOCK:
            if _BRIDGE_RESULT_ISSUANCES.get(result) is issuance:
                del _BRIDGE_RESULT_ISSUANCES[result]
        raise


def _probe_hip_fgmres_result_ir_v2_from_model_case_parity_v2(
    case_result: HipFgmresModelCaseParityResultV2,
    *,
    accepted_state: StateIR | None = None,
    result_id: str = "Result.hip-fgmres-linear-static.model-case-v2",
) -> HipFgmresResultIRBridgeResultV2:
    """Exercise the frozen v2 gate as a non-public compatibility probe.

    Original-scale high-load cases are expected to fail the v2 fixed residual
    sign tolerance.  The public additive path is ResultIR v3; keeping this
    helper private prevents a false claim that the v2 wire was relaxed.
    """

    if type(case_result) is not HipFgmresModelCaseParityResultV2:
        _fail(
            "hip_fgmres_result_ir_v2_case_result_v2_type_invalid",
            "/source/case_result",
            "Expected an exact HipFgmresModelCaseParityResultV2.",
        )

    first = _capture_live_authority_v2(case_result)
    plan = first.plan
    _require_converged_native_source(first)

    initial = _canonical_initial_state(plan, accepted_state)
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    solution = _f64_payload(
        first.solution_x,
        int(free.size),
        "/source/completion_export/solution_x",
    )
    exported_residual = _f64_payload(
        first.true_residual,
        int(free.size),
        "/source/completion_export/true_residual",
    )
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[free] = solution
    displacement[constrained] = 0.0

    try:
        trial = open_trial_state(
            initial,
            displacement,
            load_step=1,
            iteration=first.cpu_result.iteration_count,
            load_factor=1.0,
            expected_plan=plan,
        )
        committed = commit_trial_state(initial, trial, expected_plan=plan)
    except StateIRError as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_state_transition_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    provenance = _source_provenance(first)
    try:
        result_ir = build_result_ir_v2(
            plan,
            trial,
            committed,
            displacement,
            exported_residual,
            provenance,
            result_id=result_id,
        )
    except ResultIRV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_recovery_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    second = _capture_live_authority_v2(case_result)
    _require_same_live_authority(first, second)
    result_ir = _issue_bridge_result_ir_v2_ready(result_ir)

    seal = _make_detached_seal(
        first,
        provenance=provenance,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        result_ir=result_ir,
    )
    result = HipFgmresResultIRBridgeResultV2(
        receipt=result_ir,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        _source_execution_plan=plan,
        _source_seal=seal,
    )
    issuance = _HipFgmresResultIRBridgeIssuanceV2(
        mint=seal._mint,
        seal=seal,
        receipt=result_ir,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        source_execution_plan=plan,
        source_provenance=provenance,
        result_ir_hash=result_ir.result_ir_hash,
        capture_hash=seal.capture_hash,
        provenance_hash=canonical_hash(provenance.to_dict()),
        accepted_state_hash=initial.state_hash,
        evaluated_trial_state_hash=trial.state_hash,
        committed_state_hash=committed.state_hash,
        source_case_identity_token=seal._source_case_identity_token,
    )
    with _BRIDGE_RESULT_ISSUANCE_LOCK:
        if result in _BRIDGE_RESULT_ISSUANCES:  # pragma: no cover - fresh object
            _fail("hip_fgmres_result_ir_v2_issuance_duplicate", "/source/issuance")
        _BRIDGE_RESULT_ISSUANCES[result] = issuance
    try:
        return validate_hip_fgmres_result_ir_v2(result)
    except BaseException:
        with _BRIDGE_RESULT_ISSUANCE_LOCK:
            if _BRIDGE_RESULT_ISSUANCES.get(result) is issuance:
                del _BRIDGE_RESULT_ISSUANCES[result]
        raise


def validate_hip_fgmres_result_ir_v2(
    result: HipFgmresResultIRBridgeResultV2,
) -> HipFgmresResultIRBridgeResultV2:
    """Validate a bridge result without touching live HIP/model-case state."""

    if type(result) is not HipFgmresResultIRBridgeResultV2:
        _fail(
            "hip_fgmres_result_ir_v2_result_type_invalid",
            "/",
            "Expected an exact HipFgmresResultIRBridgeResultV2.",
        )
    if type(result.receipt) is not ResultIRV2:
        _fail(
            "hip_fgmres_result_ir_v2_receipt_type_invalid",
            "/receipt",
        )
    if type(result._source_execution_plan) is not ExecutionPlanV2:
        _fail(
            "hip_fgmres_result_ir_v2_plan_type_invalid",
            "/source/execution_plan",
        )
    if type(result._source_seal) is not _HipFgmresResultIRDetachedSourceSealV2:
        _fail(
            "hip_fgmres_result_ir_v2_source_seal_type_invalid",
            "/source/seal",
        )
    for state, path in (
        (result.accepted_state, "/states/accepted"),
        (result.evaluated_trial_state, "/states/evaluated_trial"),
        (result.committed_state, "/states/committed"),
    ):
        if type(state) is not StateIR:
            _fail("hip_fgmres_result_ir_v2_state_type_invalid", path)

    plan = result._source_execution_plan
    seal = result._source_seal
    seal_hashes = (
        seal.authority_snapshot_hash,
        seal.source_execution_plan_hash,
        seal.cpu_result_hash,
        seal.case_parity_receipt_hash,
        seal.terminal_observation_receipt_hash,
        seal.completion_export_receipt_hash,
        seal.completion_export_payload_hash,
        seal.device_identity_receipt_hash,
        seal.solution_payload_sha256,
        seal.true_residual_payload_sha256,
        seal.accepted_state_hash,
        seal.evaluated_trial_state_hash,
        seal.committed_state_hash,
        seal.result_ir_hash,
        seal.capture_hash,
    )
    if (
        type(seal._source_case_identity_token) is not object
        or type(seal.cpu_iteration_count) is not int
        or seal.cpu_iteration_count < 0
        or not _valid_stable_id(seal.case_id)
        or any(not _valid_hash(value) for value in seal_hashes)
    ):
        _fail(
            "hip_fgmres_result_ir_v2_source_seal_scalar_invalid",
            "/source/seal",
        )
    if (
        seal.capability_profile != HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE
        or type(seal.source_execution_plan_identity) is not int
        or seal.source_execution_plan_identity != id(plan)
        or seal.source_execution_plan_id != plan.plan_id
        or seal.source_execution_plan_hash != plan.plan_hash
    ):
        _fail(
            "hip_fgmres_result_ir_v2_plan_binding_mismatch",
            "/source/execution_plan",
        )
    try:
        validate_execution_plan_v2(plan)
    except ExecutionPlanV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    _validate_detached_state_lineage(result, seal, plan)
    if (
        type(seal.solution_x) is not bytes
        or type(seal.true_residual) is not bytes
        or _sha256(seal.solution_x) != seal.solution_payload_sha256
        or _sha256(seal.true_residual) != seal.true_residual_payload_sha256
        or seal.source_provenance.solution_payload_sha256
        != seal.solution_payload_sha256
        or seal.source_provenance.exported_free_residual_payload_sha256
        != seal.true_residual_payload_sha256
    ):
        _fail(
            "hip_fgmres_result_ir_v2_detached_payload_invalid",
            "/source/seal/payloads",
        )
    if (
        result.receipt.source_provenance != seal.source_provenance
        or result.receipt.result_ir_hash != seal.result_ir_hash
        or result.receipt.source_provenance.case_id != seal.case_id
        or result.receipt.source_provenance.case_parity_receipt_hash
        != seal.case_parity_receipt_hash
        or result.receipt.source_provenance.terminal_observation_receipt_hash
        != seal.terminal_observation_receipt_hash
        or result.receipt.source_provenance.completion_export_receipt_hash
        != seal.completion_export_receipt_hash
        or result.receipt.source_provenance.completion_export_payload_hash
        != seal.completion_export_payload_hash
        or result.receipt.source_provenance.device_identity_receipt_hash
        != seal.device_identity_receipt_hash
    ):
        _fail(
            "hip_fgmres_result_ir_v2_detached_provenance_mismatch",
            "/source/seal/provenance",
        )

    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    displacement = result.receipt.arrays.displacements_si.values.reshape(-1)
    exported = result.receipt.arrays.exported_free_residual_si.values.reshape(-1)
    raw_solution = _f64_payload(
        seal.solution_x,
        int(free.size),
        "/source/seal/solution_x",
    )
    raw_exported = _f64_payload(
        seal.true_residual,
        int(free.size),
        "/source/seal/true_residual",
    )
    normalized_solution = np.ascontiguousarray(raw_solution, dtype="<f8").copy()
    normalized_solution[normalized_solution == 0.0] = 0.0
    normalized_exported = np.ascontiguousarray(raw_exported, dtype="<f8").copy()
    normalized_exported[normalized_exported == 0.0] = 0.0
    if not np.array_equal(displacement[free], normalized_solution):
        _fail(
            "hip_fgmres_result_ir_v2_solution_payload_mismatch",
            "/receipt/arrays/displacements_si",
        )
    if not np.array_equal(exported, normalized_exported):
        _fail(
            "hip_fgmres_result_ir_v2_residual_payload_mismatch",
            "/receipt/arrays/exported_free_residual_si",
        )
    if np.any(displacement[constrained] != 0.0) or np.any(
        np.signbit(displacement[constrained])
    ):
        _fail(
            "hip_fgmres_result_ir_v2_constrained_zero_invalid",
            "/receipt/arrays/displacements_si",
            "Constrained displacement must retain exact positive zero.",
        )

    if seal.capture_hash != canonical_hash(_detached_seal_payload(seal)):
        _fail(
            "hip_fgmres_result_ir_v2_source_seal_hash_mismatch",
            "/source/seal/capture_hash",
        )
    try:
        validate_result_ir_v2_physics(
            result.receipt,
            expected_plan=plan,
            expected_evaluated_trial_state=result.evaluated_trial_state,
            expected_committed_state=result.committed_state,
        )
    except ResultIRV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_detached_replay_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc

    # Keep exact factory issuance as the final authority gate.  Detached value
    # validation runs first so fail-closed diagnostics identify payload, seal,
    # or provenance corruption without allowing any unissued object to pass.
    with _BRIDGE_RESULT_ISSUANCE_LOCK:
        issuance = _BRIDGE_RESULT_ISSUANCES.get(result)
    if type(issuance) is not _HipFgmresResultIRBridgeIssuanceV2:
        _fail(
            "hip_fgmres_result_ir_v2_issuance_unavailable",
            "/source/issuance",
            "Bridge result was not issued by the live-authority factory.",
        )
    if (
        issuance.mint is not seal._mint
        or issuance.source_case_identity_token is not seal._source_case_identity_token
        or issuance.seal is not seal
        or issuance.receipt is not result.receipt
        or issuance.accepted_state is not result.accepted_state
        or issuance.evaluated_trial_state is not result.evaluated_trial_state
        or issuance.committed_state is not result.committed_state
        or issuance.source_execution_plan is not plan
        or issuance.source_provenance is not seal.source_provenance
        or issuance.source_provenance is not result.receipt.source_provenance
        or issuance.result_ir_hash != result.receipt.result_ir_hash
        or issuance.capture_hash != seal.capture_hash
        or issuance.provenance_hash
        != canonical_hash(result.receipt.source_provenance.to_dict())
        or issuance.accepted_state_hash != result.accepted_state.state_hash
        or issuance.evaluated_trial_state_hash
        != result.evaluated_trial_state.state_hash
        or issuance.committed_state_hash != result.committed_state.state_hash
    ):
        _fail(
            "hip_fgmres_result_ir_v2_issuance_binding_mismatch",
            "/source/issuance",
            "Bridge result no longer matches its exact factory issuance.",
        )
    return result


def _validate_hip_fgmres_result_ir_v2_against_live_case(
    result: HipFgmresResultIRBridgeResultV2,
    case_result: HipFgmresModelCaseParityResultV1,
) -> HipFgmresResultIRBridgeResultV2:
    """Bind one issued bridge to the exact still-live source case object.

    Process-local identities remain private issuance metadata; they are never
    serialized into ResultIR or its detached manifest.  This gate exists for
    higher-level live composition factories and deliberately cannot run after
    the source case/export context has closed.
    """

    validate_hip_fgmres_result_ir_v2(result)
    if type(case_result) is not HipFgmresModelCaseParityResultV1:
        _fail(
            "hip_fgmres_result_ir_v2_live_case_type_invalid",
            "/source/live_case",
        )
    capture = _capture_live_authority(case_result)
    _require_converged_native_source(capture)
    with _BRIDGE_RESULT_ISSUANCE_LOCK:
        issuance = _BRIDGE_RESULT_ISSUANCES.get(result)
    if type(issuance) is not _HipFgmresResultIRBridgeIssuanceV2:
        _fail(
            "hip_fgmres_result_ir_v2_issuance_unavailable",
            "/source/issuance",
        )
    provenance = result.receipt.source_provenance
    if (
        issuance.source_case_identity_token is not capture.source_case_identity_token
        or issuance.source_case_identity_token
        is not result._source_seal._source_case_identity_token
        or capture.plan is not result.source_execution_plan
        or capture.receipt.receipt_hash != provenance.case_parity_receipt_hash
        or capture.receipt.case_id != provenance.case_id
        or capture.receipt.bindings.terminal_observation_receipt_hash
        != provenance.terminal_observation_receipt_hash
        or capture.receipt.bindings.completion_export_receipt_hash
        != provenance.completion_export_receipt_hash
        or capture.receipt.bindings.completion_export_payload_hash
        != provenance.completion_export_payload_hash
        or capture.receipt.bindings.device_identity_receipt_hash
        != provenance.device_identity_receipt_hash
        or _sha256(capture.solution_x) != provenance.solution_payload_sha256
        or _sha256(capture.true_residual)
        != provenance.exported_free_residual_payload_sha256
    ):
        _fail(
            "hip_fgmres_result_ir_v2_live_case_identity_mismatch",
            "/source/live_case",
            "Bridge was not issued from this exact retained model-case authority.",
        )
    return result


def _capture_live_authority(
    case_result: HipFgmresModelCaseParityResultV1,
) -> _LiveAuthorityCaptureV2:
    try:
        authority, source_case_identity_token = (
            case_result._result_ir_downstream_authority_binding()
        )
    except HipFgmresModelCaseParityV1Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_live_authority_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if type(authority) is not _HipFgmresModelCaseParityResultIrDownstreamAuthorityV1:
        _fail(
            "hip_fgmres_result_ir_v2_live_authority_type_invalid",
            "/source/authority",
        )
    if type(source_case_identity_token) is not object:
        _fail(
            "hip_fgmres_result_ir_v2_live_case_identity_token_invalid",
            "/source/authority/identity_token",
        )
    publication_authority = authority.publication
    if type(publication_authority) is not _CompletionExportModelCaseParityAuthorityV1:
        _fail(
            "hip_fgmres_result_ir_v2_publication_authority_type_invalid",
            "/source/authority/publication",
        )
    published = publication_authority.publication
    exact_sources = (
        (authority.receipt, HipFgmresModelCaseParityReceiptV1),
        (authority.source_execution_plan, ExecutionPlanV2),
        (authority.cpu_result, CpuFgmresReferenceResultV1),
        (authority.observation_result, HipFgmresTerminalOutcomeObservationResultV1),
        (authority.device_identity_result, HipDeviceIdentityResultV1),
        (authority.export_result, HipFgmresCompletionExportResultV1),
        (published, _CompletionExportPublishedResultAuthorityV1),
    )
    if any(type(value) is not expected for value, expected in exact_sources):
        _fail(
            "hip_fgmres_result_ir_v2_live_source_type_invalid",
            "/source/authority",
        )
    if (
        authority.receipt is not case_result.receipt
        or publication_authority.source.source_execution_plan
        is not authority.source_execution_plan
        or published.result is not authority.export_result
        or published.receipt is not authority.export_result.receipt
        or published.solution_x is not authority.export_result.solution_x
        or published.true_residual is not authority.export_result.true_residual
        or type(published.solution_x) is not bytes
        or type(published.true_residual) is not bytes
        or type(authority.snapshot) is not tuple
    ):
        _fail(
            "hip_fgmres_result_ir_v2_live_source_identity_invalid",
            "/source/authority",
        )
    try:
        validate_execution_plan_v2(authority.source_execution_plan)
        snapshot_hash = canonical_hash(_snapshot_token(authority.snapshot))
    except ExecutionPlanV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    except CanonicalContractError as exc:
        _fail(
            "hip_fgmres_result_ir_v2_authority_snapshot_invalid",
            "/source/authority/snapshot",
            str(exc),
        )
    return _LiveAuthorityCaptureV2(
        authority=authority,
        source_case_identity_token=source_case_identity_token,
        receipt=authority.receipt,
        plan=authority.source_execution_plan,
        cpu_result=authority.cpu_result,
        observation_result=authority.observation_result,
        device_identity_result=authority.device_identity_result,
        export_result=authority.export_result,
        publication_authority=publication_authority,
        published_result=published,
        solution_x=memoryview(published.solution_x).tobytes(),
        true_residual=memoryview(published.true_residual).tobytes(),
        authority_snapshot_hash=snapshot_hash,
    )


def _capture_live_authority_v2(
    case_result: HipFgmresModelCaseParityResultV2,
) -> _LiveAuthorityCaptureV2:
    """Capture the additive v2 case authority without accepting a v1 proxy."""

    try:
        authority, source_case_identity_token = (
            case_result._result_ir_downstream_authority_binding()
        )
    except HipFgmresModelCaseParityV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_live_authority_v2_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if type(authority) is not _HipFgmresModelCaseParityResultIrDownstreamAuthorityV2:
        _fail(
            "hip_fgmres_result_ir_v2_live_authority_v2_type_invalid",
            "/source/authority",
        )
    if type(source_case_identity_token) is not object:
        _fail(
            "hip_fgmres_result_ir_v2_live_case_v2_identity_token_invalid",
            "/source/authority/identity_token",
        )
    publication_authority = authority.publication
    if type(publication_authority) is not _CompletionExportModelCaseParityAuthorityV1:
        _fail(
            "hip_fgmres_result_ir_v2_publication_authority_v2_type_invalid",
            "/source/authority/publication",
        )
    published = publication_authority.publication
    exact_sources = (
        (authority.receipt, HipFgmresModelCaseParityReceiptV2),
        (authority.source_execution_plan, ExecutionPlanV2),
        (authority.cpu_result, CpuFgmresReferenceResultV1),
        (authority.observation_result, HipFgmresTerminalOutcomeObservationResultV1),
        (authority.device_identity_result, HipDeviceIdentityResultV1),
        (authority.export_result, HipFgmresCompletionExportResultV1),
        (published, _CompletionExportPublishedResultAuthorityV1),
    )
    if any(type(value) is not expected for value, expected in exact_sources):
        _fail(
            "hip_fgmres_result_ir_v2_live_source_v2_type_invalid",
            "/source/authority",
        )
    if (
        authority.receipt is not case_result.receipt
        or authority.terminal_metric_parity is not case_result.terminal_metric_parity
        or publication_authority.source.source_execution_plan
        is not authority.source_execution_plan
        or published.result is not authority.export_result
        or published.receipt is not authority.export_result.receipt
        or published.solution_x is not authority.export_result.solution_x
        or published.true_residual is not authority.export_result.true_residual
        or type(published.solution_x) is not bytes
        or type(published.true_residual) is not bytes
        or type(authority.snapshot) is not tuple
    ):
        _fail(
            "hip_fgmres_result_ir_v2_live_source_v2_identity_invalid",
            "/source/authority",
        )
    try:
        validate_execution_plan_v2(authority.source_execution_plan)
        snapshot_hash = canonical_hash(_snapshot_token(authority.snapshot))
    except ExecutionPlanV2Error as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    except CanonicalContractError as exc:
        _fail(
            "hip_fgmres_result_ir_v2_authority_v2_snapshot_invalid",
            "/source/authority/snapshot",
            str(exc),
        )
    return _LiveAuthorityCaptureV2(
        authority=authority,
        source_case_identity_token=source_case_identity_token,
        receipt=authority.receipt,
        plan=authority.source_execution_plan,
        cpu_result=authority.cpu_result,
        observation_result=authority.observation_result,
        device_identity_result=authority.device_identity_result,
        export_result=authority.export_result,
        publication_authority=publication_authority,
        published_result=published,
        solution_x=memoryview(published.solution_x).tobytes(),
        true_residual=memoryview(published.true_residual).tobytes(),
        authority_snapshot_hash=snapshot_hash,
    )


def _require_converged_native_source(capture: _LiveAuthorityCaptureV2) -> None:
    receipt = capture.receipt
    cpu = capture.cpu_result
    observation = capture.observation_result.receipt
    device = capture.device_identity_result.receipt
    export = capture.export_result.receipt
    published = capture.published_result
    plan = capture.plan
    if (
        receipt.actual_backend != "hip"
        or observation.actual_backend != "hip"
        or device.actual_backend != "hip"
        or export.actual_backend != "hip"
    ):
        _fail(
            "hip_fgmres_result_ir_v2_backend_invalid",
            "/source/actual_backend",
            "Every retained source must be an attested HIP backend.",
        )
    if (
        cpu.status != "converged"
        or cpu.solver_tolerance_passed is not True
        or cpu.authoritative_plan_tolerance_passed is not True
    ):
        _fail(
            "hip_fgmres_result_ir_v2_cpu_not_converged",
            "/source/cpu_result/status",
            "CPU parity source must pass both solver and plan tolerances.",
        )
    if (
        observation.status != "terminal_converged"
        or observation.outcome.terminal_status != "converged"
    ):
        _fail(
            "hip_fgmres_result_ir_v2_hip_not_converged",
            "/source/terminal_observation/outcome",
        )

    bindings = receipt.bindings
    solution_hash = _sha256(capture.solution_x)
    residual_hash = _sha256(capture.true_residual)
    export_buffers = {row.role: row for row in export.buffers}
    if set(export_buffers) != {"solution_x", "true_residual", "solve_record"}:
        _fail(
            "hip_fgmres_result_ir_v2_export_buffers_invalid",
            "/source/completion_export/buffers",
        )
    if (
        bindings.execution_plan_id != plan.plan_id
        or bindings.execution_plan_hash != plan.plan_hash
        or bindings.cpu_result_hash != cpu.result_hash
        or bindings.terminal_observation_receipt_hash != observation.receipt_hash
        or bindings.completion_export_receipt_hash != export.receipt_hash
        or bindings.completion_export_payload_hash != export.payload_hash
        or bindings.device_identity_receipt_hash != device.receipt_hash
    ):
        _fail(
            "hip_fgmres_result_ir_v2_lineage_binding_mismatch",
            "/source/bindings",
        )
    if (
        receipt.dimensions.global_dof_count != plan.dof_count
        or receipt.dimensions.free_dof_count != len(plan.free_dofs)
        or export.dimensions.free_dof_count != len(plan.free_dofs)
        or export.dimensions.solution_byte_count != len(capture.solution_x)
        or export.dimensions.true_residual_byte_count != len(capture.true_residual)
        or len(capture.solution_x) != len(plan.free_dofs) * 8
        or len(capture.true_residual) != len(plan.free_dofs) * 8
    ):
        _fail(
            "hip_fgmres_result_ir_v2_source_dimension_mismatch",
            "/source/dimensions",
        )
    if (
        capture.export_result.payload_hash != export.payload_hash
        or published.receipt_hash != export.receipt_hash
        or published.payload_hash != export.payload_hash
        or published.buffer_payload_hashes[0] != solution_hash
        or published.buffer_payload_hashes[1] != residual_hash
        or export_buffers["solution_x"].payload_sha256 != solution_hash
        or export_buffers["true_residual"].payload_sha256 != residual_hash
        or observation.bindings.solution_payload_sha256 != solution_hash
        or observation.bindings.true_residual_payload_sha256 != residual_hash
    ):
        _fail(
            "hip_fgmres_result_ir_v2_payload_binding_mismatch",
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
            "hip_fgmres_result_ir_v2_device_binding_mismatch",
            "/source/device_identity",
        )


def _require_same_live_authority(
    first: _LiveAuthorityCaptureV2,
    second: _LiveAuthorityCaptureV2,
) -> None:
    if (
        second.authority is not first.authority
        or second.source_case_identity_token is not first.source_case_identity_token
        or second.receipt is not first.receipt
        or second.plan is not first.plan
        or second.cpu_result is not first.cpu_result
        or second.observation_result is not first.observation_result
        or second.device_identity_result is not first.device_identity_result
        or second.export_result is not first.export_result
        or second.publication_authority is not first.publication_authority
        or second.published_result is not first.published_result
        or second.published_result.solution_x is not first.published_result.solution_x
        or second.published_result.true_residual
        is not first.published_result.true_residual
        or second.authority.snapshot != first.authority.snapshot
        or second.authority_snapshot_hash != first.authority_snapshot_hash
        or second.solution_x != first.solution_x
        or second.true_residual != first.true_residual
    ):
        _fail(
            "hip_fgmres_result_ir_v2_live_authority_changed",
            "/source/authority",
            "Live parity/export authority changed during CPU recovery.",
        )
    _require_converged_native_source(second)


def _canonical_initial_state(
    plan: ExecutionPlanV2,
    candidate: StateIR | None,
) -> StateIR:
    expected = create_initial_state(plan)
    if candidate is None:
        return expected
    if type(candidate) is not StateIR:
        _fail(
            "hip_fgmres_result_ir_v2_accepted_state_type_invalid",
            "/states/accepted",
        )
    try:
        validate_state_ir(candidate, expected_plan=plan)
    except StateIRError as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_accepted_state_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    if candidate.state_hash != expected.state_hash:
        _fail(
            "hip_fgmres_result_ir_v2_warm_start_unsupported",
            "/states/accepted",
            "Only the exact canonical zero initial StateIR is supported.",
        )
    return candidate


def _source_provenance(capture: _LiveAuthorityCaptureV2) -> SourceProvenance:
    bindings = capture.receipt.bindings
    return SourceProvenance(
        case_id=capture.receipt.case_id,
        case_parity_receipt_hash=capture.receipt.receipt_hash,
        terminal_observation_receipt_hash=(bindings.terminal_observation_receipt_hash),
        completion_export_receipt_hash=bindings.completion_export_receipt_hash,
        completion_export_payload_hash=bindings.completion_export_payload_hash,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        solution_payload_sha256=_sha256(capture.solution_x),
        exported_free_residual_payload_sha256=_sha256(capture.true_residual),
        compiled_architecture=bindings.compiled_architecture,
        runtime_architecture_base=bindings.runtime_architecture_base,
        device_ordinal=bindings.device_ordinal,
        device_uuid_bytes_hex=bindings.device_uuid_bytes_hex,
        device_pci_bdf=bindings.device_pci_bdf,
    )


def _make_detached_seal(
    capture: _LiveAuthorityCaptureV2,
    *,
    provenance: SourceProvenance,
    accepted_state: StateIR,
    evaluated_trial_state: StateIR,
    committed_state: StateIR,
    result_ir: ResultIRV2,
) -> _HipFgmresResultIRDetachedSourceSealV2:
    bindings = capture.receipt.bindings
    draft = _HipFgmresResultIRDetachedSourceSealV2(
        _mint=object(),
        _source_case_identity_token=capture.source_case_identity_token,
        capability_profile=HIP_FGMRES_RESULT_IR_V2_CAPABILITY_PROFILE,
        authority_snapshot_hash=capture.authority_snapshot_hash,
        source_execution_plan_identity=id(capture.plan),
        source_execution_plan_id=capture.plan.plan_id,
        source_execution_plan_hash=capture.plan.plan_hash,
        cpu_result_hash=capture.cpu_result.result_hash,
        cpu_iteration_count=capture.cpu_result.iteration_count,
        case_id=capture.receipt.case_id,
        case_parity_receipt_hash=capture.receipt.receipt_hash,
        terminal_observation_receipt_hash=(bindings.terminal_observation_receipt_hash),
        completion_export_receipt_hash=bindings.completion_export_receipt_hash,
        completion_export_payload_hash=bindings.completion_export_payload_hash,
        device_identity_receipt_hash=bindings.device_identity_receipt_hash,
        solution_payload_sha256=_sha256(capture.solution_x),
        true_residual_payload_sha256=_sha256(capture.true_residual),
        solution_x=bytes(bytearray(capture.solution_x)),
        true_residual=bytes(bytearray(capture.true_residual)),
        source_provenance=provenance,
        accepted_state_hash=accepted_state.state_hash,
        evaluated_trial_state_hash=evaluated_trial_state.state_hash,
        committed_state_hash=committed_state.state_hash,
        result_ir_hash=result_ir.result_ir_hash,
        capture_hash=_ZERO_HASH,
    )
    return replace(draft, capture_hash=canonical_hash(_detached_seal_payload(draft)))


def _validate_detached_state_lineage(
    result: HipFgmresResultIRBridgeResultV2,
    seal: _HipFgmresResultIRDetachedSourceSealV2,
    plan: ExecutionPlanV2,
) -> None:
    try:
        for state in (
            result.accepted_state,
            result.evaluated_trial_state,
            result.committed_state,
        ):
            validate_state_ir(state, expected_plan=plan)
    except StateIRError as exc:
        raise HipFgmresResultIRV2Error(
            "hip_fgmres_result_ir_v2_state_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    expected_initial = create_initial_state(plan)
    if (
        result.accepted_state.state_hash != expected_initial.state_hash
        or result.accepted_state.state_hash != seal.accepted_state_hash
        or result.evaluated_trial_state.state_hash != seal.evaluated_trial_state_hash
        or result.committed_state.state_hash != seal.committed_state_hash
        or result.evaluated_trial_state.parent_state_hash
        != result.accepted_state.state_hash
        or result.evaluated_trial_state.role != "trial"
        or result.evaluated_trial_state.epoch != 1
        or result.evaluated_trial_state.load_step != 1
        or result.evaluated_trial_state.iteration != seal.cpu_iteration_count
        or result.evaluated_trial_state.load_factor != 1.0
        or result.committed_state.role != "committed"
        or result.committed_state.parent_state_hash
        != result.evaluated_trial_state.state_hash
    ):
        _fail(
            "hip_fgmres_result_ir_v2_state_lineage_mismatch",
            "/states",
        )


def _detached_seal_payload(
    seal: _HipFgmresResultIRDetachedSourceSealV2,
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
        "case_parity_receipt_hash": seal.case_parity_receipt_hash,
        "terminal_observation_receipt_hash": (seal.terminal_observation_receipt_hash),
        "completion_export_receipt_hash": seal.completion_export_receipt_hash,
        "completion_export_payload_hash": seal.completion_export_payload_hash,
        "device_identity_receipt_hash": seal.device_identity_receipt_hash,
        "solution_payload_sha256": seal.solution_payload_sha256,
        "true_residual_payload_sha256": seal.true_residual_payload_sha256,
        "solution_byte_count": len(seal.solution_x),
        "true_residual_byte_count": len(seal.true_residual),
        "source_provenance": seal.source_provenance.to_dict(),
        "accepted_state_hash": seal.accepted_state_hash,
        "evaluated_trial_state_hash": seal.evaluated_trial_state_hash,
        "committed_state_hash": seal.committed_state_hash,
        "result_ir_hash": seal.result_ir_hash,
    }


def _snapshot_token(value: Any) -> Any:
    """Convert the private value snapshot into canonical, value-only JSON."""

    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        return {"float_hex": value.hex()}
    if type(value) is bytes:
        return {"byte_count": len(value), "sha256": _sha256(value)}
    if type(value) is type:
        return {"python_type": f"{value.__module__}.{value.__qualname__}"}
    if type(value) is tuple:
        return tuple(_snapshot_token(item) for item in value)
    raise CanonicalContractError(
        f"Unsupported authority snapshot value {type(value).__name__}."
    )


def _f64_payload(payload: bytes, count: int, path: str) -> np.ndarray:
    if type(payload) is not bytes or len(payload) != count * 8:
        _fail(
            "hip_fgmres_result_ir_v2_payload_shape_invalid",
            path,
            f"Expected {count} little-endian FP64 entries.",
        )
    vector = np.frombuffer(payload, dtype="<f8")
    if vector.shape != (count,) or not np.all(np.isfinite(vector)):
        _fail(
            "hip_fgmres_result_ir_v2_payload_nonfinite",
            path,
        )
    return vector


def _sha256(payload: bytes) -> str:
    if type(payload) is not bytes:
        _fail(
            "hip_fgmres_result_ir_v2_payload_type_invalid",
            "/source/payload",
        )
    return sha256_prefixed(payload)


def _valid_hash(value: Any) -> bool:
    if type(value) is not str or len(value) != 71 or not value.startswith("sha256:"):
        return False
    return all(character in "0123456789abcdef" for character in value[7:])


def _valid_stable_id(value: Any) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 128 or not value[0].isalpha():
        return False
    return all(character.isalnum() or character in "_.:-" for character in value)


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresResultIRV2Error(code, path, message)
