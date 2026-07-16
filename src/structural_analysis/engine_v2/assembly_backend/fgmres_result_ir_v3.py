"""Roundoff-aware ResultIR authority for scoped FGMRES model-case parity v2.

ResultIRV2 intentionally keeps its historical ``numpy.allclose`` residual-sign
gate.  Original-scale high-load cases can satisfy the stronger componentwise
FP64 CSR roundoff contract while failing that fixed gate.  This additive v3
bridge does not relax or mutate ResultIRV2.  It retains a structurally valid,
not-ready ResultIRV2 payload, validates all non-export physics through an
internal exact-residual witness, and replaces only the exported-residual sign
link with a two-stage componentwise proof:

``exported HIP -> independent math.fsum replay -> ResultIR plan residual``.

The public v3 receipt is non-promoting and records that the base v2 receipt is
not ready under its frozen policy.  Exact process-local factory issuance is
required; detached serialization alone is not provenance authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Literal, NoReturn
import weakref

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.fp64_csr_residual_roundoff_v1 import (
    Fp64CsrResidualRoundoffResultV1,
    attest_fp64_csr_residual_roundoff_v1,
    validate_fp64_csr_residual_roundoff_result_v1,
)
from structural_analysis.engine_v2.contracts.result_ir_v2 import (
    ResultIRV2,
    ResultIRV2Claims,
    _array_artifact,
    _build_result_ir_v2_unvalidated_physics,
    _numerical_hash,
    _receipt_hash as _result_ir_v2_receipt_hash,
    validate_result_ir_v2,
    validate_result_ir_v2_physics,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
    validate_state_ir,
)

from .fgmres_model_case_parity_v2 import HipFgmresModelCaseParityResultV2
from .fgmres_model_case_terminal_metric_parity_v2 import (
    HipFgmresTerminalMetricParityResultV2,
    validate_hip_fgmres_terminal_metric_parity_result_v2,
)
from .fgmres_result_ir_v2 import (
    _canonical_initial_state,
    _capture_live_authority_v2,
    _f64_payload,
    _require_converged_native_source,
    _require_same_live_authority,
    _source_provenance,
)


HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3 = "structural-analysis-hip-fgmres-result-ir.v3"
HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3 = (
    "hip_fgmres_scoped_roundoff_aware_sparse_result_ir_v3"
)
HIP_FGMRES_RESULT_IR_EVIDENCE_SCOPE_V3 = (
    "process_local_high_load_single_terminal_restart_result_ir_non_promoting"
)

_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_RESOURCE = "hip_fgmres_result_ir_v3.schema.json"


class HipFgmresResultIRV3Error(ValueError):
    """Stable fail-closed roundoff-aware ResultIR v3 error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRBindingsV3:
    case_id: str
    case_parity_receipt_hash: str
    terminal_metric_parity_receipt_hash: str
    execution_plan_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str
    terminal_observation_receipt_hash: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    source_provenance_hash: str
    solution_payload_sha256: str
    exported_residual_payload_sha256: str
    independent_fsum_residual_sha256: str
    result_ir_plan_residual_f_minus_ku_sha256: str
    exported_to_fsum_componentwise_receipt_hash: str
    fsum_to_result_ir_plan_componentwise_receipt_hash: str
    base_result_ir_v2_hash: str
    base_numerical_result_hash: str
    fixed_physics_witness_result_ir_hash: str

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRDimensionsV3:
    global_dof_count: int
    free_dof_count: int
    reduced_csr_nnz: int
    result_array_count: Literal[6]
    residual_comparison_stage_count: Literal[2]

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRResidualValidationV3:
    chain: Literal["exported_hip_to_independent_fsum_to_result_ir_plan_f_minus_ku"]
    exported_to_fsum_maximum_componentwise_bound_ratio: float
    fsum_to_result_ir_plan_maximum_componentwise_bound_ratio: float
    terminal_maximum_record_bound_ratio: float
    exported_to_fsum_componentwise_bound_verified: Literal[True]
    fsum_to_result_ir_plan_componentwise_bound_verified: Literal[True]
    terminal_l2_linf_scaled_linf_bound_verified: Literal[True]
    fixed_physics_witness_verified: Literal[True]
    caller_tolerance_allowed: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRCompatibilityV3:
    source_model_case_schema_version: Literal[
        "structural-analysis-hip-fgmres-model-case-parity.v2"
    ] = "structural-analysis-hip-fgmres-model-case-parity.v2"
    retained_base_result_ir_schema_version: Literal[
        "structural-analysis-result-ir.v2"
    ] = "structural-analysis-result-ir.v2"
    retained_base_result_ir_ready: Literal[False] = False
    retained_base_wire_mutated: Literal[False] = False
    result_ir_v2_fixed_residual_policy_relaxed: Literal[False] = False
    migration_action: Literal[
        "retain_not_ready_v2_and_issue_roundoff_aware_v3_authority"
    ] = "retain_not_ready_v2_and_issue_roundoff_aware_v3_authority"

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRTelemetryV3:
    retained_completion_payload_count: Literal[2] = 2
    additional_cpu_componentwise_comparison_count: Literal[1] = 1
    fixed_physics_witness_count: Literal[1] = 1
    additional_device_operation_count: Literal[0] = 0
    additional_d2h_operation_count: Literal[0] = 0
    additional_solve_count: Literal[0] = 0
    additional_export_count: Literal[0] = 0
    fallback_count: Literal[0] = 0

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRClaimsV3:
    result_ir_v3_verified: Literal[True] = True
    result_ir_v3_ready: Literal[True] = True
    state_ir_lineage_verified: Literal[True] = True
    reaction_recovery_verified: Literal[True] = True
    member_force_recovery_verified: Literal[True] = True
    energy_identities_verified: Literal[True] = True
    exported_residual_roundoff_chain_verified: Literal[True] = True
    actual_hip_source_provenance_verified_at_factory: Literal[True] = True
    general_restart_history_v2_verified: Literal[False] = False
    device_recovery_verified: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    standalone_provenance: Literal[False] = False
    signed_evidence: Literal[False] = False
    end_to_end_o_n_proven: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresResultIRReceiptV3:
    schema_version: str
    capability_profile: str
    status: Literal["result_ir_v3_ready"]
    evidence_scope: str
    promotion_eligible: Literal[False]
    result_id: str
    bindings: HipFgmresResultIRBindingsV3
    dimensions: HipFgmresResultIRDimensionsV3
    residual_validation: HipFgmresResultIRResidualValidationV3
    compatibility: HipFgmresResultIRCompatibilityV3
    telemetry: HipFgmresResultIRTelemetryV3
    claims: HipFgmresResultIRClaimsV3
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_result_ir_receipt_v3(self)
        return _receipt_payload(self, include_hash=True)


class _WeakReferenceableResultIRV3:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HipFgmresResultIRResultV3(_WeakReferenceableResultIRV3):
    receipt: HipFgmresResultIRReceiptV3
    base_result_ir_v2: ResultIRV2
    accepted_state: StateIR
    evaluated_trial_state: StateIR
    committed_state: StateIR
    terminal_metric_parity: HipFgmresTerminalMetricParityResultV2
    fsum_to_result_ir_plan_roundoff: Fp64CsrResidualRoundoffResultV1
    _source_execution_plan: ExecutionPlanV2
    _source_solution_x: bytes
    _source_true_residual: bytes
    _source_case_identity_token: object

    @property
    def result_ir(self) -> ResultIRV2:
        """Return the retained six-array payload governed by the v3 receipt."""

        return self.base_result_ir_v2

    @property
    def source_execution_plan(self) -> ExecutionPlanV2:
        return self._source_execution_plan

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_fgmres_result_ir_v3(self)
        return {
            "result_ir_v3": self.receipt.to_dict(),
            "retained_result_ir_v2": self.base_result_ir_v2.to_manifest(),
        }


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _HipFgmresResultIRIssuanceV3:
    receipt: HipFgmresResultIRReceiptV3
    result_ir_v2: ResultIRV2
    accepted_state: StateIR
    evaluated_trial_state: StateIR
    committed_state: StateIR
    terminal_metric_parity: HipFgmresTerminalMetricParityResultV2
    fsum_to_plan_roundoff: Fp64CsrResidualRoundoffResultV1
    source_execution_plan: ExecutionPlanV2
    source_solution_x: bytes
    source_true_residual: bytes
    source_case_identity_token: object


_ISSUANCE_LOCK = threading.RLock()
_ISSUANCES: weakref.WeakKeyDictionary[
    HipFgmresResultIRResultV3, _HipFgmresResultIRIssuanceV3
] = weakref.WeakKeyDictionary()


def build_hip_fgmres_result_ir_v3(
    case_result: HipFgmresModelCaseParityResultV2,
    *,
    accepted_state: StateIR | None = None,
    result_id: str = "Result.hip-fgmres-linear-static.v3",
) -> HipFgmresResultIRResultV3:
    """Build one roundoff-aware ResultIR v3 from exact live v2 authority."""

    if type(case_result) is not HipFgmresModelCaseParityResultV2:
        _fail(
            "hip_fgmres_result_ir_v3_case_result_type_invalid",
            "/source/case_result",
        )
    first = _capture_live_authority_v2(case_result)
    _require_converged_native_source(first)
    plan = first.plan
    initial = _canonical_initial_state(plan, accepted_state)
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    solution = _f64_payload(
        first.solution_x,
        int(free.size),
        "/source/completion_export/solution_x",
    )
    exported = _f64_payload(
        first.true_residual,
        int(free.size),
        "/source/completion_export/true_residual",
    )
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[free] = solution
    displacement[constrained] = 0.0
    trial = open_trial_state(
        initial,
        displacement,
        load_step=1,
        iteration=first.cpu_result.iteration_count,
        load_factor=1.0,
        expected_plan=plan,
    )
    committed = commit_trial_state(initial, trial, expected_plan=plan)
    provenance = _source_provenance(first)
    base = _build_result_ir_v2_unvalidated_physics(
        plan,
        trial,
        committed,
        displacement,
        exported,
        provenance,
        result_id=result_id,
    )
    terminal = case_result.terminal_metric_parity
    fsum_to_plan, witness = _residual_chain_and_physics_witness(
        plan=plan,
        base=base,
        terminal=terminal,
        solution_x=first.solution_x,
        true_residual=first.true_residual,
        evaluated_trial_state=trial,
        committed_state=committed,
    )
    second = _capture_live_authority_v2(case_result)
    _require_same_live_authority(first, second)
    receipt = _build_receipt(
        plan=plan,
        base=base,
        witness=witness,
        terminal=terminal,
        fsum_to_plan=fsum_to_plan,
        solution_x=first.solution_x,
        true_residual=first.true_residual,
    )
    result = HipFgmresResultIRResultV3(
        receipt=receipt,
        base_result_ir_v2=base,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        terminal_metric_parity=terminal,
        fsum_to_result_ir_plan_roundoff=fsum_to_plan,
        _source_execution_plan=plan,
        _source_solution_x=bytes(bytearray(first.solution_x)),
        _source_true_residual=bytes(bytearray(first.true_residual)),
        _source_case_identity_token=first.source_case_identity_token,
    )
    issuance = _HipFgmresResultIRIssuanceV3(
        receipt=receipt,
        result_ir_v2=base,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        terminal_metric_parity=terminal,
        fsum_to_plan_roundoff=fsum_to_plan,
        source_execution_plan=plan,
        source_solution_x=result._source_solution_x,
        source_true_residual=result._source_true_residual,
        source_case_identity_token=first.source_case_identity_token,
    )
    with _ISSUANCE_LOCK:
        if result in _ISSUANCES:  # pragma: no cover
            _fail("hip_fgmres_result_ir_v3_issuance_duplicate", "/source/issuance")
        _ISSUANCES[result] = issuance
    try:
        return validate_hip_fgmres_result_ir_v3(result)
    except BaseException:
        with _ISSUANCE_LOCK:
            if _ISSUANCES.get(result) is issuance:
                del _ISSUANCES[result]
        raise


def validate_hip_fgmres_result_ir_receipt_v3(
    receipt: HipFgmresResultIRReceiptV3,
) -> HipFgmresResultIRReceiptV3:
    """Validate the strict v3 wire without asserting process-local issuance."""

    if type(receipt) is not HipFgmresResultIRReceiptV3:
        _fail("hip_fgmres_result_ir_v3_receipt_type_invalid", "/")
    nested = (
        (receipt.bindings, HipFgmresResultIRBindingsV3, "/bindings"),
        (receipt.dimensions, HipFgmresResultIRDimensionsV3, "/dimensions"),
        (
            receipt.residual_validation,
            HipFgmresResultIRResidualValidationV3,
            "/residual_validation",
        ),
        (receipt.compatibility, HipFgmresResultIRCompatibilityV3, "/compatibility"),
        (receipt.telemetry, HipFgmresResultIRTelemetryV3, "/telemetry"),
        (receipt.claims, HipFgmresResultIRClaimsV3, "/claims"),
    )
    for value, expected, path in nested:
        if type(value) is not expected:
            _fail("hip_fgmres_result_ir_v3_nested_type_invalid", path)
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_result_ir_v3_schema_invalid", path, error.message)
    if (
        receipt.schema_version != HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3
        or receipt.capability_profile != HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3
        or receipt.status != "result_ir_v3_ready"
        or receipt.evidence_scope != HIP_FGMRES_RESULT_IR_EVIDENCE_SCOPE_V3
        or receipt.promotion_eligible is not False
        or receipt.compatibility != HipFgmresResultIRCompatibilityV3()
        or receipt.telemetry != HipFgmresResultIRTelemetryV3()
        or receipt.claims != HipFgmresResultIRClaimsV3()
    ):
        _fail("hip_fgmres_result_ir_v3_semantics_invalid", "/")
    if (
        any(
            _HASH_RE.fullmatch(getattr(receipt.bindings, name)) is None
            for name in receipt.bindings.__dataclass_fields__
            if name != "case_id"
        )
        or _HASH_RE.fullmatch(receipt.bindings.case_id) is None
    ):
        _fail("hip_fgmres_result_ir_v3_binding_hash_invalid", "/bindings")
    dimensions = receipt.dimensions
    if (
        any(
            type(getattr(dimensions, name)) is not int
            for name in dimensions.__dataclass_fields__
        )
        or dimensions.global_dof_count <= 0
        or dimensions.free_dof_count <= 0
        or dimensions.free_dof_count > dimensions.global_dof_count
        or dimensions.reduced_csr_nnz <= 0
        or dimensions.result_array_count != 6
        or dimensions.residual_comparison_stage_count != 2
    ):
        _fail("hip_fgmres_result_ir_v3_dimension_invalid", "/dimensions")
    validation = receipt.residual_validation
    ratios = (
        validation.exported_to_fsum_maximum_componentwise_bound_ratio,
        validation.fsum_to_result_ir_plan_maximum_componentwise_bound_ratio,
        validation.terminal_maximum_record_bound_ratio,
    )
    if any(
        type(value) is not float
        or not math.isfinite(value)
        or value < 0.0
        or value > 1.0
        for value in ratios
    ):
        _fail(
            "hip_fgmres_result_ir_v3_residual_ratio_invalid",
            "/residual_validation",
        )
    expected_id = canonical_hash(
        {
            "profile": HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3,
            "case_parity_receipt_hash": receipt.bindings.case_parity_receipt_hash,
            "base_result_ir_v2_hash": receipt.bindings.base_result_ir_v2_hash,
            "fsum_to_result_ir_plan_componentwise_receipt_hash": (
                receipt.bindings.fsum_to_result_ir_plan_componentwise_receipt_hash
            ),
        }
    )
    if receipt.result_id != expected_id:
        _fail("hip_fgmres_result_ir_v3_result_id_invalid", "/result_id")
    expected_hash = canonical_hash(_receipt_payload(receipt, include_hash=False))
    if receipt.receipt_hash != expected_hash:
        _fail("hip_fgmres_result_ir_v3_receipt_hash_invalid", "/receipt_hash")
    return receipt


def validate_hip_fgmres_result_ir_v3(
    result: HipFgmresResultIRResultV3,
) -> HipFgmresResultIRResultV3:
    """Replay the detached sparse physics, residual chain, and issuance."""

    if type(result) is not HipFgmresResultIRResultV3:
        _fail("hip_fgmres_result_ir_v3_result_type_invalid", "/")
    validate_hip_fgmres_result_ir_receipt_v3(result.receipt)
    if (
        type(result.base_result_ir_v2) is not ResultIRV2
        or type(result.accepted_state) is not StateIR
        or type(result.evaluated_trial_state) is not StateIR
        or type(result.committed_state) is not StateIR
        or type(result.terminal_metric_parity)
        is not HipFgmresTerminalMetricParityResultV2
        or type(result.fsum_to_result_ir_plan_roundoff)
        is not Fp64CsrResidualRoundoffResultV1
        or type(result._source_execution_plan) is not ExecutionPlanV2
        or type(result._source_solution_x) is not bytes
        or type(result._source_true_residual) is not bytes
        or type(result._source_case_identity_token) is not object
    ):
        _fail("hip_fgmres_result_ir_v3_source_type_invalid", "/source")
    plan = result._source_execution_plan
    validate_execution_plan_v2(plan)
    _validate_state_lineage(result, plan)
    validate_result_ir_v2(result.base_result_ir_v2)
    if result.base_result_ir_v2.claims != ResultIRV2Claims():
        _fail(
            "hip_fgmres_result_ir_v3_base_v2_ready_invalid",
            "/base_result_ir_v2/claims",
        )
    validate_hip_fgmres_terminal_metric_parity_result_v2(result.terminal_metric_parity)
    validate_fp64_csr_residual_roundoff_result_v1(
        result.fsum_to_result_ir_plan_roundoff,
        expected_execution_plan=plan,
    )
    fresh_roundoff, witness = _residual_chain_and_physics_witness(
        plan=plan,
        base=result.base_result_ir_v2,
        terminal=result.terminal_metric_parity,
        solution_x=result._source_solution_x,
        true_residual=result._source_true_residual,
        evaluated_trial_state=result.evaluated_trial_state,
        committed_state=result.committed_state,
    )
    if fresh_roundoff.receipt != result.fsum_to_result_ir_plan_roundoff.receipt:
        _fail(
            "hip_fgmres_result_ir_v3_roundoff_replay_mismatch",
            "/residual_validation",
        )
    expected = _build_receipt(
        plan=plan,
        base=result.base_result_ir_v2,
        witness=witness,
        terminal=result.terminal_metric_parity,
        fsum_to_plan=fresh_roundoff,
        solution_x=result._source_solution_x,
        true_residual=result._source_true_residual,
    )
    if expected != result.receipt:
        _fail("hip_fgmres_result_ir_v3_replay_mismatch", "/")
    with _ISSUANCE_LOCK:
        issuance = _ISSUANCES.get(result)
    if type(issuance) is not _HipFgmresResultIRIssuanceV3:
        _fail("hip_fgmres_result_ir_v3_issuance_unavailable", "/source/issuance")
    if (
        issuance.receipt is not result.receipt
        or issuance.result_ir_v2 is not result.base_result_ir_v2
        or issuance.accepted_state is not result.accepted_state
        or issuance.evaluated_trial_state is not result.evaluated_trial_state
        or issuance.committed_state is not result.committed_state
        or issuance.terminal_metric_parity is not result.terminal_metric_parity
        or issuance.fsum_to_plan_roundoff is not result.fsum_to_result_ir_plan_roundoff
        or issuance.source_execution_plan is not plan
        or issuance.source_solution_x is not result._source_solution_x
        or issuance.source_true_residual is not result._source_true_residual
        or issuance.source_case_identity_token is not result._source_case_identity_token
    ):
        _fail(
            "hip_fgmres_result_ir_v3_issuance_binding_mismatch",
            "/source/issuance",
        )
    return result


def _residual_chain_and_physics_witness(
    *,
    plan: ExecutionPlanV2,
    base: ResultIRV2,
    terminal: HipFgmresTerminalMetricParityResultV2,
    solution_x: bytes,
    true_residual: bytes,
    evaluated_trial_state: StateIR,
    committed_state: StateIR,
) -> tuple[Fp64CsrResidualRoundoffResultV1, ResultIRV2]:
    validate_result_ir_v2(base)
    validate_hip_fgmres_terminal_metric_parity_result_v2(terminal)
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    solution = _payload_vector(solution_x, int(free.size), "/source/solution_x")
    exported = _payload_vector(true_residual, int(free.size), "/source/true_residual")
    displacement = base.arrays.displacements_si.values.reshape(-1)
    base_exported = base.arrays.exported_free_residual_si.values.reshape(-1)
    base_residual = base.arrays.residual_si.values.reshape(-1)
    if not _same_f64(displacement[free], solution) or not _same_f64(
        base_exported, exported
    ):
        _fail(
            "hip_fgmres_result_ir_v3_base_payload_mismatch",
            "/base_result_ir_v2/arrays",
        )
    stage_one = terminal.roundoff_replay.candidate_vs_independent_replay
    validate_fp64_csr_residual_roundoff_result_v1(stage_one)
    if (
        stage_one._execution_plan.plan_hash != plan.plan_hash
        or not _same_f64(stage_one._reference_solution, solution)
        or not _same_f64(stage_one._candidate_solution, solution)
        or not _same_f64(stage_one._reference_residual, exported)
    ):
        _fail(
            "hip_fgmres_result_ir_v3_terminal_roundoff_binding_mismatch",
            "/residual_validation/exported_to_fsum",
        )
    fsum_residual = np.ascontiguousarray(stage_one._candidate_residual, dtype="<f8")
    plan_f_minus_ku = np.ascontiguousarray(-base_residual[free], dtype="<f8")
    plan_f_minus_ku[plan_f_minus_ku == 0.0] = 0.0
    fsum_to_plan = attest_fp64_csr_residual_roundoff_v1(
        plan,
        solution,
        solution,
        fsum_residual,
        plan_f_minus_ku,
    )
    witness = _fixed_physics_witness(
        base,
        plan_f_minus_ku,
        plan=plan,
        evaluated_trial_state=evaluated_trial_state,
        committed_state=committed_state,
    )
    return fsum_to_plan, witness


def _fixed_physics_witness(
    base: ResultIRV2,
    exact_exported: np.ndarray,
    *,
    plan: ExecutionPlanV2,
    evaluated_trial_state: StateIR,
    committed_state: StateIR,
) -> ResultIRV2:
    source = base.arrays.exported_free_residual_si
    artifact = _array_artifact(
        source.name,
        exact_exported,
        axis_labels=source.axis_labels,
        component_labels=source.component_labels,
        component_units=source.component_units,
    )
    arrays = replace(base.arrays, exported_free_residual_si=artifact)
    linf = float(np.max(np.abs(exact_exported), initial=0.0))
    convergence = replace(
        base.convergence,
        exported_free_residual_linf=linf,
        scaled_exported_free_residual=linf / base.convergence.load_scale,
    )
    draft = replace(
        base,
        arrays=arrays,
        convergence=convergence,
        numerical_result_hash=_numerical_hash(arrays, convergence, base.energy),
        result_ir_hash=_ZERO_HASH,
    )
    witness = replace(
        draft,
        result_ir_hash=_result_ir_v2_receipt_hash(draft.to_dict()),
    )
    return validate_result_ir_v2_physics(
        witness,
        expected_plan=plan,
        expected_evaluated_trial_state=evaluated_trial_state,
        expected_committed_state=committed_state,
    )


def _build_receipt(
    *,
    plan: ExecutionPlanV2,
    base: ResultIRV2,
    witness: ResultIRV2,
    terminal: HipFgmresTerminalMetricParityResultV2,
    fsum_to_plan: Fp64CsrResidualRoundoffResultV1,
    solution_x: bytes,
    true_residual: bytes,
) -> HipFgmresResultIRReceiptV3:
    stage_one = terminal.roundoff_replay.candidate_vs_independent_replay
    stage_two = fsum_to_plan
    provenance = base.source_provenance
    fsum = stage_one._candidate_residual
    plan_residual = stage_two._candidate_residual
    bindings = HipFgmresResultIRBindingsV3(
        case_id=provenance.case_id,
        case_parity_receipt_hash=provenance.case_parity_receipt_hash,
        terminal_metric_parity_receipt_hash=terminal.receipt.receipt_hash,
        execution_plan_hash=plan.plan_hash,
        evaluated_trial_state_hash=base.input_bindings.evaluated_trial_state_hash,
        committed_state_hash=base.input_bindings.committed_state_hash,
        terminal_observation_receipt_hash=(
            provenance.terminal_observation_receipt_hash
        ),
        completion_export_receipt_hash=provenance.completion_export_receipt_hash,
        completion_export_payload_hash=provenance.completion_export_payload_hash,
        device_identity_receipt_hash=provenance.device_identity_receipt_hash,
        source_provenance_hash=canonical_hash(provenance.to_dict()),
        solution_payload_sha256=sha256_prefixed(solution_x),
        exported_residual_payload_sha256=sha256_prefixed(true_residual),
        independent_fsum_residual_sha256=_array_hash(fsum),
        result_ir_plan_residual_f_minus_ku_sha256=_array_hash(plan_residual),
        exported_to_fsum_componentwise_receipt_hash=stage_one.receipt.receipt_hash,
        fsum_to_result_ir_plan_componentwise_receipt_hash=(
            stage_two.receipt.receipt_hash
        ),
        base_result_ir_v2_hash=base.result_ir_hash,
        base_numerical_result_hash=base.numerical_result_hash,
        fixed_physics_witness_result_ir_hash=witness.result_ir_hash,
    )
    validation = HipFgmresResultIRResidualValidationV3(
        chain="exported_hip_to_independent_fsum_to_result_ir_plan_f_minus_ku",
        exported_to_fsum_maximum_componentwise_bound_ratio=(
            stage_one.receipt.summary.maximum_componentwise_bound_ratio
        ),
        fsum_to_result_ir_plan_maximum_componentwise_bound_ratio=(
            stage_two.receipt.summary.maximum_componentwise_bound_ratio
        ),
        terminal_maximum_record_bound_ratio=(
            terminal.receipt.summary.maximum_record_bound_ratio
        ),
        exported_to_fsum_componentwise_bound_verified=True,
        fsum_to_result_ir_plan_componentwise_bound_verified=True,
        terminal_l2_linf_scaled_linf_bound_verified=True,
        fixed_physics_witness_verified=True,
        caller_tolerance_allowed=False,
    )
    result_id = canonical_hash(
        {
            "profile": HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3,
            "case_parity_receipt_hash": bindings.case_parity_receipt_hash,
            "base_result_ir_v2_hash": bindings.base_result_ir_v2_hash,
            "fsum_to_result_ir_plan_componentwise_receipt_hash": (
                bindings.fsum_to_result_ir_plan_componentwise_receipt_hash
            ),
        }
    )
    draft = HipFgmresResultIRReceiptV3(
        schema_version=HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3,
        capability_profile=HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3,
        status="result_ir_v3_ready",
        evidence_scope=HIP_FGMRES_RESULT_IR_EVIDENCE_SCOPE_V3,
        promotion_eligible=False,
        result_id=result_id,
        bindings=bindings,
        dimensions=HipFgmresResultIRDimensionsV3(
            global_dof_count=plan.dof_count,
            free_dof_count=int(plan.array("free_dofs").size),
            reduced_csr_nnz=int(plan.array("reduced_csr_column_indices").size),
            result_array_count=6,
            residual_comparison_stage_count=2,
        ),
        residual_validation=validation,
        compatibility=HipFgmresResultIRCompatibilityV3(),
        telemetry=HipFgmresResultIRTelemetryV3(),
        claims=HipFgmresResultIRClaimsV3(),
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_result_ir_receipt_v3(receipt)


def _validate_state_lineage(
    result: HipFgmresResultIRResultV3,
    plan: ExecutionPlanV2,
) -> None:
    for state in (
        result.accepted_state,
        result.evaluated_trial_state,
        result.committed_state,
    ):
        validate_state_ir(state, expected_plan=plan)
    initial = create_initial_state(plan)
    if (
        result.accepted_state.state_hash != initial.state_hash
        or result.evaluated_trial_state.parent_state_hash
        != result.accepted_state.state_hash
        or result.evaluated_trial_state.role != "trial"
        or result.committed_state.parent_state_hash
        != result.evaluated_trial_state.state_hash
        or result.committed_state.role != "committed"
        or result.base_result_ir_v2.input_bindings.evaluated_trial_state_hash
        != result.evaluated_trial_state.state_hash
        or result.base_result_ir_v2.input_bindings.committed_state_hash
        != result.committed_state.state_hash
    ):
        _fail("hip_fgmres_result_ir_v3_state_lineage_mismatch", "/states")


def _payload_vector(payload: bytes, count: int, path: str) -> np.ndarray:
    if type(payload) is not bytes or len(payload) != count * 8:
        _fail("hip_fgmres_result_ir_v3_payload_extent_invalid", path)
    value = np.frombuffer(payload, dtype="<f8")
    if (
        value.shape != (count,)
        or not np.isfinite(value).all()
        or np.any(np.signbit(value[value == 0.0]))
    ):
        _fail("hip_fgmres_result_ir_v3_payload_invalid", path)
    return value


def _same_f64(left: np.ndarray, right: np.ndarray) -> bool:
    return left.shape == right.shape and np.asarray(left, dtype="<f8").tobytes(
        order="C"
    ) == np.asarray(right, dtype="<f8").tobytes(order="C")


def _array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value, dtype="<f8")
    return sha256_prefixed(array.tobytes(order="C"))


def _receipt_payload(
    receipt: HipFgmresResultIRReceiptV3,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "status": receipt.status,
        "evidence_scope": receipt.evidence_scope,
        "promotion_eligible": receipt.promotion_eligible,
        "result_id": receipt.result_id,
        "bindings": receipt.bindings.to_dict(),
        "dimensions": receipt.dimensions.to_dict(),
        "residual_validation": receipt.residual_validation.to_dict(),
        "compatibility": receipt.compatibility.to_dict(),
        "telemetry": receipt.telemetry.to_dict(),
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
    raise HipFgmresResultIRV3Error(code, path, message)


__all__ = [
    "HIP_FGMRES_RESULT_IR_CAPABILITY_PROFILE_V3",
    "HIP_FGMRES_RESULT_IR_EVIDENCE_SCOPE_V3",
    "HIP_FGMRES_RESULT_IR_SCHEMA_VERSION_V3",
    "HipFgmresResultIRBindingsV3",
    "HipFgmresResultIRClaimsV3",
    "HipFgmresResultIRCompatibilityV3",
    "HipFgmresResultIRDimensionsV3",
    "HipFgmresResultIRReceiptV3",
    "HipFgmresResultIRResidualValidationV3",
    "HipFgmresResultIRResultV3",
    "HipFgmresResultIRTelemetryV3",
    "HipFgmresResultIRV3Error",
    "build_hip_fgmres_result_ir_v3",
    "validate_hip_fgmres_result_ir_receipt_v3",
    "validate_hip_fgmres_result_ir_v3",
]
