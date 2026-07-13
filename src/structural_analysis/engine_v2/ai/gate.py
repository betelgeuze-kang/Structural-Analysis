"""Authoritative full-physics gate for Phase 0 AI correction proposals.

The gate never commits a state and never produces a solver result.  It applies
one plan-bound free-DOF correction in an ephemeral ``StateIR`` trial, replays
the complete CPU reference residual and total potential energy, and then rolls
the trial back to the exact accepted object.  Receipt v1 carries no calibrated
OOD evidence and is therefore always rejected.  Eligibility requires a future
evidence-bound schema; it cannot be created by rehashing this artifact.

Residual improvement is measured in the projection coordinate contract:
``D = 1/sqrt(diag(K_ff))`` and ``scaled_residual = ||D r_free||_2``.  The L2
norm uses a scale-first implementation to avoid overflow.  ``load_scale`` is
retained only as telemetry and is not part of the gate metric.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    open_trial_state,
    rollback_trial_state,
    validate_state_ir,
)

AI_PROPOSAL_GATE_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-ai-proposal-gate-receipt.v1"
)
AI_PROPOSAL_GATE_CAPABILITY_PROFILE = (
    "phase0_cpu_full_physics_initial_guess_gate"
)
MAX_BASIS_GRAM_CONDITION = 1.00000001
MAX_PHASE0_RANK = 16
_ZERO_HASH = "sha256:" + ("0" * 64)


class AIProposalGateError(ValueError):
    """Fail-closed gate or receipt error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class GateInputBindings:
    model_ir_content_hash: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    operator_hash: str
    pattern_hash: str
    partition_hash: str
    accepted_state_hash: str
    accepted_displacement_hash: str
    accepted_state_epoch: int
    proposal_hash: str
    projection_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProposalPolicyReceipt:
    hook: str
    target_vector_space: str
    free_dof_count: int
    retained_rank: int
    rank_cap: int
    basis_gram_condition: float
    max_basis_gram_condition: float
    trust_radius: float
    trust_coordinate_units: str
    coefficient_l2_norm: float
    correction_scaled_l2_norm: float
    ood_status: str
    statistical_calibration: bool
    ood_policy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhysicsReplayReceipt:
    residual_sign: str
    scaled_residual_definition: str
    constitutive_mode: str
    load_scale: float
    base_residual_hash: str
    trial_residual_hash: str
    base_constitutive_internal_force_hash: str
    trial_constitutive_internal_force_hash: str
    trial_displacement_hash: str
    ephemeral_trial_state_hash: str
    base_full_residual_linf: float
    trial_full_residual_linf: float
    base_free_residual_linf: float
    trial_free_residual_linf: float
    base_scaled_free_residual: float
    trial_scaled_free_residual: float
    scaled_free_residual_reduction: float
    scaled_free_residual_reduction_ratio: float
    base_total_potential_energy_j: float
    trial_total_potential_energy_j: float
    potential_energy_change_j: float
    constrained_increment_linf: float
    constitutive_operator_consistency_linf: float
    constitutive_energy_consistency_abs_j: float
    constitutive_force_tolerance: float
    constitutive_energy_tolerance_j: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateChecks:
    proposal_contract_valid: bool
    plan_state_proposal_binding_pass: bool
    initial_guess_hook_pass: bool
    free_vector_space_pass: bool
    trust_budget_pass: bool
    rank_budget_pass: bool
    condition_pass: bool
    ood_policy_pass: bool
    full_residual_replayed: bool
    stateless_linear_elastic_constitutive_replayed: bool
    constitutive_admissibility_pass: bool
    free_scaled_residual_reduced: bool
    total_potential_energy_nonincrease: bool
    constrained_increment_exact_zero: bool
    rollback_exact: bool
    accepted_state_preserved: bool
    eligible_initial_guess: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RollbackProof:
    accepted_state_hash_before: str
    accepted_state_hash_after: str
    accepted_state_object_identity_preserved: bool
    accepted_displacement_hash_before: str
    accepted_displacement_hash_after: str
    rollback_returned_exact_accepted_object: bool
    trial_committed: bool
    state_commit_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateAuthority:
    eligible_use: str = "initial_guess_only"
    proposal_consumed_by_authoritative_solver: bool = False
    commit_performed: bool = False
    final_result: bool = False
    authoritative_result: bool = False
    speed_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AIProposalGateReceipt:
    schema_version: str
    capability_profile: str
    gate_id: str
    status: Literal["rejected"]
    reason_codes: tuple[str, ...]
    input_bindings: GateInputBindings
    proposal_policy: ProposalPolicyReceipt
    physics_replay: PhysicsReplayReceipt
    checks: GateChecks
    rollback_proof: RollbackProof
    authority: GateAuthority
    gate_receipt_hash: str
    extensions: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        validate_ai_proposal_gate_receipt(self)
        return _receipt_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def evaluate_ai_proposal_gate(
    plan: ExecutionPlan,
    accepted_state: StateIR,
    proposal: Any,
) -> AIProposalGateReceipt:
    """Replay one proposal and return a non-promoting Phase 0 v1 receipt."""

    return _evaluate_ai_proposal_gate(
        plan,
        accepted_state,
        proposal,
        validate_output=True,
    )


def validate_ai_proposal_gate_receipt(
    receipt: AIProposalGateReceipt,
    *,
    expected_plan: ExecutionPlan | None = None,
    expected_accepted_state: StateIR | None = None,
    expected_proposal: Any | None = None,
) -> None:
    """Validate schema, hash, logical invariants, and optional full replay."""

    if not isinstance(receipt, AIProposalGateReceipt):
        _fail("gate_receipt_type_invalid", "/", "Expected an AIProposalGateReceipt.")
    payload = _receipt_payload(receipt, include_hash=True)
    errors = sorted(_schema_validator().iter_errors(payload), key=lambda row: list(row.path))
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(value) for value in first.path)
        _fail("gate_receipt_schema_invalid", path or "/", first.message)
    if receipt.schema_version != AI_PROPOSAL_GATE_RECEIPT_SCHEMA_VERSION:
        _fail("gate_receipt_schema_version_mismatch", "/schema_version", "Unsupported schema.")
    if receipt.capability_profile != AI_PROPOSAL_GATE_CAPABILITY_PROFILE:
        _fail("gate_receipt_profile_mismatch", "/capability_profile", "Unsupported profile.")
    if receipt.gate_receipt_hash != _gate_receipt_hash(receipt):
        _fail("gate_receipt_hash_mismatch", "/gate_receipt_hash", "Receipt hash is stale.")

    expected_gate_id = _gate_id(
        receipt.input_bindings.proposal_hash,
        receipt.input_bindings.accepted_state_hash,
    )
    if receipt.gate_id != expected_gate_id:
        _fail(
            "gate_receipt_id_mismatch",
            "/gate_id",
            "Gate ID is not derived from the bound proposal and accepted state.",
        )
    if receipt.authority != GateAuthority():
        _fail(
            "gate_receipt_authority_mismatch",
            "/authority",
            "Receipt authority differs from the Phase 0 initial-guess-only boundary.",
        )

    policy = receipt.proposal_policy
    if (
        policy.max_basis_gram_condition != MAX_BASIS_GRAM_CONDITION
        or policy.trust_coordinate_units != "sqrt_joule_energy_coordinate"
        or policy.ood_policy
        != "require_in_distribution_and_statistically_calibrated"
        or policy.ood_status != "not_evaluated"
        or policy.statistical_calibration is not False
    ):
        _fail(
            "gate_receipt_policy_contract_mismatch",
            "/proposal_policy",
            "Proposal policy constants, units, or Phase 0 OOD authority are unsupported.",
        )

    checks = receipt.checks
    expected_policy_checks = _policy_check_values(policy)
    stored_policy_checks = {
        name: bool(getattr(checks, name)) for name in expected_policy_checks
    }
    if stored_policy_checks != expected_policy_checks:
        _fail(
            "gate_receipt_policy_check_mismatch",
            "/checks",
            "Stored policy checks are inconsistent with proposal-policy telemetry.",
        )
    if (
        checks.ood_policy_pass
        or checks.eligible_initial_guess
        or receipt.status != "rejected"
    ):
        _fail(
            "gate_receipt_phase0_authority_invalid",
            "/status",
            "Gate receipt v1 cannot carry calibrated or eligible authority.",
        )
    required = (
        checks.proposal_contract_valid,
        checks.plan_state_proposal_binding_pass,
        checks.initial_guess_hook_pass,
        checks.free_vector_space_pass,
        checks.trust_budget_pass,
        checks.rank_budget_pass,
        checks.condition_pass,
        checks.ood_policy_pass,
        checks.full_residual_replayed,
        checks.stateless_linear_elastic_constitutive_replayed,
        checks.constitutive_admissibility_pass,
        checks.free_scaled_residual_reduced,
        checks.total_potential_energy_nonincrease,
        checks.constrained_increment_exact_zero,
        checks.rollback_exact,
        checks.accepted_state_preserved,
    )
    eligible = all(required)
    if checks.eligible_initial_guess != eligible:
        _fail("gate_receipt_eligibility_mismatch", "/checks/eligible_initial_guess", "Eligibility is inconsistent.")
    expected_status = "eligible_initial_guess" if eligible else "rejected"
    if receipt.status != expected_status:
        _fail("gate_receipt_status_mismatch", "/status", "Status is inconsistent with checks.")
    expected_reasons = _reason_codes(receipt.proposal_policy, checks)
    if receipt.reason_codes != expected_reasons:
        _fail("gate_receipt_reason_codes_mismatch", "/reason_codes", "Reason codes are inconsistent.")

    replay = receipt.physics_replay
    if (
        replay.base_full_residual_linf < replay.base_free_residual_linf
        or replay.trial_full_residual_linf < replay.trial_free_residual_linf
    ):
        _fail(
            "gate_receipt_residual_subset_invalid",
            "/physics_replay",
            "A full residual norm cannot be smaller than its free-DOF subset norm.",
        )
    if checks.free_scaled_residual_reduced != (
        replay.trial_scaled_free_residual < replay.base_scaled_free_residual
    ):
        _fail("gate_receipt_residual_check_mismatch", "/checks/free_scaled_residual_reduced", "Residual check is inconsistent.")
    if checks.total_potential_energy_nonincrease != (
        replay.trial_total_potential_energy_j <= replay.base_total_potential_energy_j
    ):
        _fail("gate_receipt_energy_check_mismatch", "/checks/total_potential_energy_nonincrease", "Energy check is inconsistent.")
    if checks.constrained_increment_exact_zero != (replay.constrained_increment_linf == 0.0):
        _fail("gate_receipt_constraint_check_mismatch", "/checks/constrained_increment_exact_zero", "Constraint check is inconsistent.")
    constitutive_expected = (
        replay.constitutive_operator_consistency_linf
        <= replay.constitutive_force_tolerance
        and replay.constitutive_energy_consistency_abs_j
        <= replay.constitutive_energy_tolerance_j
    )
    if (
        checks.stateless_linear_elastic_constitutive_replayed
        != constitutive_expected
        or checks.constitutive_admissibility_pass != constitutive_expected
    ):
        _fail(
            "gate_receipt_constitutive_check_mismatch",
            "/checks/stateless_linear_elastic_constitutive_replayed",
            "Constitutive checks are inconsistent with replay metrics.",
        )
    expected_reduction = (
        replay.base_scaled_free_residual - replay.trial_scaled_free_residual
    )
    expected_ratio = (
        expected_reduction / replay.base_scaled_free_residual
        if replay.base_scaled_free_residual > 0.0
        else (0.0 if replay.trial_scaled_free_residual == 0.0 else -1.0)
    )
    if (
        replay.scaled_free_residual_reduction != expected_reduction
        or replay.scaled_free_residual_reduction_ratio != expected_ratio
        or replay.potential_energy_change_j
        != replay.trial_total_potential_energy_j
        - replay.base_total_potential_energy_j
    ):
        _fail(
            "gate_receipt_derived_metric_mismatch",
            "/physics_replay",
            "Reduction, ratio, or energy-change telemetry is inconsistent.",
        )
    rollback = receipt.rollback_proof
    if (
        rollback.accepted_state_hash_before != rollback.accepted_state_hash_after
        or rollback.accepted_displacement_hash_before
        != rollback.accepted_displacement_hash_after
        or not rollback.accepted_state_object_identity_preserved
        or not rollback.rollback_returned_exact_accepted_object
        or rollback.trial_committed
        or rollback.state_commit_count != 0
    ):
        _fail("gate_receipt_rollback_proof_invalid", "/rollback_proof", "Rollback proof is inconsistent.")
    bindings = receipt.input_bindings
    if not (
        bindings.accepted_state_hash
        == rollback.accepted_state_hash_before
        == rollback.accepted_state_hash_after
        and bindings.accepted_displacement_hash
        == rollback.accepted_displacement_hash_before
        == rollback.accepted_displacement_hash_after
    ):
        _fail(
            "gate_receipt_rollback_binding_mismatch",
            "/rollback_proof",
            "Rollback hashes are not bound to the accepted input state and displacement.",
        )

    expected_values = (expected_plan, expected_accepted_state, expected_proposal)
    if any(value is not None for value in expected_values):
        if not all(value is not None for value in expected_values):
            _fail("gate_receipt_replay_inputs_incomplete", "/", "Plan, state, and proposal are all required for replay.")
        expected = _evaluate_ai_proposal_gate(
            expected_plan,
            expected_accepted_state,
            expected_proposal,
            validate_output=False,
        )
        if _receipt_payload(receipt, include_hash=True) != _receipt_payload(expected, include_hash=True):
            _fail("gate_receipt_replay_mismatch", "/", "Receipt differs from authoritative gate replay.")


def _evaluate_ai_proposal_gate(
    plan: ExecutionPlan,
    accepted_state: StateIR,
    proposal: Any,
    *,
    validate_output: bool,
) -> AIProposalGateReceipt:
    try:
        validate_execution_plan(plan)
        validate_state_ir(accepted_state, expected_plan=plan)
    except Exception as exc:
        raise AIProposalGateError(
            "gate_input_contract_invalid",
            "/",
            f"ExecutionPlan or accepted StateIR validation failed: {exc}",
        ) from exc
    if accepted_state.role != "committed":
        _fail("gate_accepted_state_role_invalid", "/accepted_state/role", "Gate requires a committed state.")

    try:
        from structural_analysis.engine_v2.ai.proposal import (
            validate_phase0_ai_proposal,
        )

        validate_phase0_ai_proposal(
            proposal,
            expected_plan=plan,
            expected_accepted_state=accepted_state,
        )
    except Exception as exc:
        raise AIProposalGateError(
            "gate_proposal_contract_invalid",
            "/proposal",
            f"AICorrectionProposal validation failed: {exc}",
        ) from exc

    accepted_object = accepted_state
    state_hash_before = accepted_state.state_hash
    displacement_hash_before = array_data_hash(accepted_state.displacement_si)
    correction = _proposal_correction(proposal, len(plan.free_dofs))
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    trial_displacement = np.asarray(accepted_state.displacement_si, dtype="<f8").copy()
    trial_displacement[free] += correction
    increment = trial_displacement - accepted_state.displacement_si

    trial_state: StateIR | None = None
    rolled_back: StateIR | None = None
    try:
        trial_state = open_trial_state(
            accepted_state,
            trial_displacement,
            load_step=accepted_state.load_step + 1,
            iteration=0,
            load_factor=1.0,
            time_s=accepted_state.time_s,
            state_id=(
                f"state.trial.ai.e{accepted_state.epoch + 1}."
                f"s{accepted_state.load_step + 1}.i0"
            ),
            expected_plan=plan,
        )
        replay = _authoritative_physics_replay(
            plan,
            accepted_state.displacement_si,
            trial_state.displacement_si,
            increment,
            trial_state.state_hash,
        )
    except Exception as exc:
        raise AIProposalGateError(
            "gate_authoritative_replay_failed",
            "/physics_replay",
            f"Authoritative CPU replay failed: {exc}",
        ) from exc
    finally:
        if trial_state is not None:
            rolled_back = rollback_trial_state(
                accepted_state,
                trial_state,
                expected_plan=plan,
            )

    rollback_exact = rolled_back is accepted_object
    state_hash_after = accepted_state.state_hash
    displacement_hash_after = array_data_hash(accepted_state.displacement_si)
    accepted_preserved = (
        accepted_state is accepted_object
        and state_hash_after == state_hash_before
        and displacement_hash_after == displacement_hash_before
    )
    if not rollback_exact or not accepted_preserved:
        _fail("gate_rollback_invariant_failed", "/rollback_proof", "Accepted state changed during gate evaluation.")

    policy = _proposal_policy(proposal)
    policy_checks = _policy_check_values(policy)
    initial_guess_hook_pass = policy_checks["initial_guess_hook_pass"]
    free_vector_space_pass = policy_checks["free_vector_space_pass"]
    trust_budget_pass = policy_checks["trust_budget_pass"]
    rank_budget_pass = policy_checks["rank_budget_pass"]
    condition_pass = policy_checks["condition_pass"]
    ood_policy_pass = policy_checks["ood_policy_pass"]
    residual_pass = bool(
        replay.trial_scaled_free_residual < replay.base_scaled_free_residual
    )
    constitutive_replay_pass = bool(
        replay.constitutive_operator_consistency_linf
        <= replay.constitutive_force_tolerance
        and replay.constitutive_energy_consistency_abs_j
        <= replay.constitutive_energy_tolerance_j
    )
    constitutive_admissibility_pass = constitutive_replay_pass
    energy_pass = bool(
        replay.trial_total_potential_energy_j
        <= replay.base_total_potential_energy_j
    )
    constrained_pass = bool(replay.constrained_increment_linf == 0.0)
    checks_without_eligibility = (
        initial_guess_hook_pass,
        free_vector_space_pass,
        trust_budget_pass,
        rank_budget_pass,
        condition_pass,
        ood_policy_pass,
        constitutive_replay_pass,
        constitutive_admissibility_pass,
        residual_pass,
        energy_pass,
        constrained_pass,
        rollback_exact,
        accepted_preserved,
    )
    eligible = all(checks_without_eligibility)
    checks = GateChecks(
        proposal_contract_valid=True,
        plan_state_proposal_binding_pass=True,
        initial_guess_hook_pass=initial_guess_hook_pass,
        free_vector_space_pass=free_vector_space_pass,
        trust_budget_pass=trust_budget_pass,
        rank_budget_pass=rank_budget_pass,
        condition_pass=condition_pass,
        ood_policy_pass=ood_policy_pass,
        full_residual_replayed=True,
        stateless_linear_elastic_constitutive_replayed=constitutive_replay_pass,
        constitutive_admissibility_pass=constitutive_admissibility_pass,
        free_scaled_residual_reduced=residual_pass,
        total_potential_energy_nonincrease=energy_pass,
        constrained_increment_exact_zero=constrained_pass,
        rollback_exact=rollback_exact,
        accepted_state_preserved=accepted_preserved,
        eligible_initial_guess=eligible,
    )
    rollback_proof = RollbackProof(
        accepted_state_hash_before=state_hash_before,
        accepted_state_hash_after=state_hash_after,
        accepted_state_object_identity_preserved=accepted_state is accepted_object,
        accepted_displacement_hash_before=displacement_hash_before,
        accepted_displacement_hash_after=displacement_hash_after,
        rollback_returned_exact_accepted_object=rollback_exact,
        trial_committed=False,
        state_commit_count=0,
    )
    bindings = GateInputBindings(
        model_ir_content_hash=plan.model_ir_content_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
        solver_artifact_hash=plan.solver_artifact_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        pattern_hash=plan.pattern_hash,
        partition_hash=plan.partition_hash,
        accepted_state_hash=state_hash_before,
        accepted_displacement_hash=displacement_hash_before,
        accepted_state_epoch=accepted_state.epoch,
        proposal_hash=str(proposal.proposal_hash),
        projection_hash=str(proposal.projection_hash),
    )
    gate_id = _gate_id(str(proposal.proposal_hash), state_hash_before)
    provisional = AIProposalGateReceipt(
        schema_version=AI_PROPOSAL_GATE_RECEIPT_SCHEMA_VERSION,
        capability_profile=AI_PROPOSAL_GATE_CAPABILITY_PROFILE,
        gate_id=gate_id,
        status="rejected",
        reason_codes=_reason_codes(policy, checks),
        input_bindings=bindings,
        proposal_policy=policy,
        physics_replay=replay,
        checks=checks,
        rollback_proof=rollback_proof,
        authority=GateAuthority(),
        gate_receipt_hash=_ZERO_HASH,
        extensions=MappingProxyType({}),
    )
    receipt = replace(provisional, gate_receipt_hash=_gate_receipt_hash(provisional))
    if validate_output:
        validate_ai_proposal_gate_receipt(receipt)
    return receipt


def _proposal_correction(proposal: Any, free_dof_count: int) -> np.ndarray:
    try:
        correction = np.asarray(proposal.array("correction_free"), dtype="<f8")
    except Exception as exc:
        raise AIProposalGateError(
            "gate_correction_unavailable",
            "/proposal/correction_free",
            f"Proposal correction cannot be read: {exc}",
        ) from exc
    if correction.shape != (free_dof_count,) or not np.all(np.isfinite(correction)):
        _fail("gate_correction_invalid", "/proposal/correction_free", "Correction must be a finite free-DOF vector.")
    return immutable_array(correction, dtype="<f8")


def _proposal_policy(proposal: Any) -> ProposalPolicyReceipt:
    values = {
        "hook": str(proposal.hook),
        "target_vector_space": str(proposal.target_vector_space),
        "free_dof_count": int(proposal.free_dof_count),
        "retained_rank": int(proposal.retained_rank),
        "rank_cap": int(proposal.rank_cap),
        "basis_gram_condition": float(proposal.basis_gram_condition),
        "max_basis_gram_condition": MAX_BASIS_GRAM_CONDITION,
        "trust_radius": float(proposal.trust_radius),
        "trust_coordinate_units": "sqrt_joule_energy_coordinate",
        "coefficient_l2_norm": float(proposal.coefficient_l2_norm),
        "correction_scaled_l2_norm": float(proposal.correction_scaled_l2_norm),
        "ood_status": str(proposal.ood_status),
        "statistical_calibration": bool(proposal.statistical_calibration),
        "ood_policy": "require_in_distribution_and_statistically_calibrated",
    }
    if any(
        not math.isfinite(value)
        for key, value in values.items()
        if key
        in {
            "basis_gram_condition",
            "trust_radius",
            "coefficient_l2_norm",
            "correction_scaled_l2_norm",
        }
    ):
        _fail("gate_proposal_policy_non_finite", "/proposal", "Proposal policy contains a non-finite number.")
    return ProposalPolicyReceipt(**values)


def _policy_check_values(policy: ProposalPolicyReceipt) -> dict[str, bool]:
    """Derive every policy check solely from hash-bound policy telemetry."""

    numeric_values = (
        policy.basis_gram_condition,
        policy.trust_radius,
        policy.coefficient_l2_norm,
        policy.correction_scaled_l2_norm,
    )
    finite = all(math.isfinite(value) for value in numeric_values)
    trust_tolerance = (
        64.0
        * np.finfo(np.float64).eps
        * max(
            1.0,
            policy.trust_radius,
            policy.coefficient_l2_norm,
            policy.correction_scaled_l2_norm,
        )
        if finite
        else 0.0
    )
    return {
        "initial_guess_hook_pass": policy.hook == "initial_guess",
        "free_vector_space_pass": (
            policy.target_vector_space == "scaled_reduced_free_dof"
        ),
        "trust_budget_pass": bool(
            finite
            and policy.trust_radius > 0.0
            and policy.coefficient_l2_norm >= 0.0
            and policy.correction_scaled_l2_norm >= 0.0
            and policy.coefficient_l2_norm
            <= policy.trust_radius + trust_tolerance
            and policy.correction_scaled_l2_norm
            <= policy.trust_radius + trust_tolerance
        ),
        "rank_budget_pass": bool(
            policy.free_dof_count >= 1
            and 1 <= policy.rank_cap <= MAX_PHASE0_RANK
            and 1
            <= policy.retained_rank
            <= min(policy.rank_cap, policy.free_dof_count)
        ),
        "condition_pass": bool(
            finite
            and 0.0
            < policy.basis_gram_condition
            <= MAX_BASIS_GRAM_CONDITION
        ),
        "ood_policy_pass": bool(
            policy.ood_status == "in_distribution"
            and policy.statistical_calibration is True
        ),
    }


def _gate_id(proposal_hash: str, accepted_state_hash: str) -> str:
    return (
        "Gate:"
        + proposal_hash.removeprefix("sha256:")[:20]
        + ":"
        + accepted_state_hash.removeprefix("sha256:")[:12]
    )


def _authoritative_physics_replay(
    plan: ExecutionPlan,
    base_displacement: np.ndarray,
    trial_displacement: np.ndarray,
    increment: np.ndarray,
    trial_state_hash: str,
) -> PhysicsReplayReceipt:
    stiffness = plan.operator.stiffness_matrix
    load = plan.operator.load_vector
    base = np.asarray(base_displacement, dtype="<f8")
    trial = np.asarray(trial_displacement, dtype="<f8")
    base_operator_internal = stiffness @ base
    trial_operator_internal = stiffness @ trial
    base_residual = base_operator_internal - load
    trial_residual = trial_operator_internal - load
    if not np.all(np.isfinite(base_residual)) or not np.all(np.isfinite(trial_residual)):
        _fail("gate_residual_non_finite", "/physics_replay", "Residual replay produced NaN or Infinity.")
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    constrained = np.asarray(plan.constrained_dofs, dtype=np.int64)
    base_free_linf = _linf(base_residual[free])
    trial_free_linf = _linf(trial_residual[free])
    load_scale = max(1.0, _linf(load[free]))
    reduced_diagonal = np.asarray(stiffness[free, free], dtype="<f8")
    if (
        reduced_diagonal.shape != (free.size,)
        or not np.all(np.isfinite(reduced_diagonal))
        or np.any(reduced_diagonal <= 0.0)
    ):
        _fail(
            "gate_jacobi_scaling_invalid",
            "/physics_replay/scaled_residual_definition",
            "diag(K_ff) must be finite and strictly positive.",
        )
    jacobi_scale = 1.0 / np.sqrt(reduced_diagonal)
    base_scaled = _stable_l2(jacobi_scale * base_residual[free])
    trial_scaled = _stable_l2(jacobi_scale * trial_residual[free])
    reduction = base_scaled - trial_scaled
    if base_scaled > 0.0:
        reduction_ratio = reduction / base_scaled
    else:
        reduction_ratio = 0.0 if trial_scaled == 0.0 else -1.0
    base_energy = 0.5 * float(base @ base_operator_internal) - float(base @ load)
    trial_energy = 0.5 * float(trial @ trial_operator_internal) - float(trial @ load)
    (
        base_constitutive_internal,
        base_constitutive_energy,
    ) = _replay_stateless_linear_elastic_constitutive(plan, base)
    (
        trial_constitutive_internal,
        trial_constitutive_energy,
    ) = _replay_stateless_linear_elastic_constitutive(plan, trial)
    constitutive_operator_consistency = max(
        _linf(base_constitutive_internal - base_operator_internal),
        _linf(trial_constitutive_internal - trial_operator_internal),
    )
    constitutive_energy_consistency = max(
        abs(base_constitutive_energy - 0.5 * float(base @ base_operator_internal)),
        abs(trial_constitutive_energy - 0.5 * float(trial @ trial_operator_internal)),
    )
    force_scale = max(
        1.0,
        _linf(base_operator_internal),
        _linf(trial_operator_internal),
        _linf(base_constitutive_internal),
        _linf(trial_constitutive_internal),
    )
    constitutive_force_tolerance = (
        256.0 * np.finfo(np.float64).eps * max(1, plan.dof_count) * force_scale
    )
    energy_scale = max(
        1.0,
        abs(base_constitutive_energy),
        abs(trial_constitutive_energy),
        abs(0.5 * float(base @ base_operator_internal)),
        abs(0.5 * float(trial @ trial_operator_internal)),
    )
    constitutive_energy_tolerance = (
        256.0 * np.finfo(np.float64).eps * max(1, plan.element_count) * energy_scale
    )
    values = (
        load_scale,
        base_free_linf,
        trial_free_linf,
        base_scaled,
        trial_scaled,
        reduction,
        reduction_ratio,
        base_energy,
        trial_energy,
        base_constitutive_energy,
        trial_constitutive_energy,
        constitutive_operator_consistency,
        constitutive_energy_consistency,
    )
    if not all(math.isfinite(value) for value in values):
        _fail("gate_physics_metric_non_finite", "/physics_replay", "A physics metric is non-finite.")
    return PhysicsReplayReceipt(
        residual_sign="internal_minus_external",
        scaled_residual_definition=(
            "l2_of_D_times_free_residual_D_equals_inv_sqrt_diag_Kff"
        ),
        constitutive_mode="stateless_linear_elastic",
        load_scale=load_scale,
        base_residual_hash=array_data_hash(np.ascontiguousarray(base_residual, dtype="<f8")),
        trial_residual_hash=array_data_hash(np.ascontiguousarray(trial_residual, dtype="<f8")),
        base_constitutive_internal_force_hash=array_data_hash(
            np.ascontiguousarray(base_constitutive_internal, dtype="<f8")
        ),
        trial_constitutive_internal_force_hash=array_data_hash(
            np.ascontiguousarray(trial_constitutive_internal, dtype="<f8")
        ),
        trial_displacement_hash=array_data_hash(np.ascontiguousarray(trial, dtype="<f8")),
        ephemeral_trial_state_hash=trial_state_hash,
        base_full_residual_linf=_linf(base_residual),
        trial_full_residual_linf=_linf(trial_residual),
        base_free_residual_linf=base_free_linf,
        trial_free_residual_linf=trial_free_linf,
        base_scaled_free_residual=base_scaled,
        trial_scaled_free_residual=trial_scaled,
        scaled_free_residual_reduction=reduction,
        scaled_free_residual_reduction_ratio=reduction_ratio,
        base_total_potential_energy_j=base_energy,
        trial_total_potential_energy_j=trial_energy,
        potential_energy_change_j=trial_energy - base_energy,
        constrained_increment_linf=_linf(np.asarray(increment)[constrained]),
        constitutive_operator_consistency_linf=constitutive_operator_consistency,
        constitutive_energy_consistency_abs_j=constitutive_energy_consistency,
        constitutive_force_tolerance=constitutive_force_tolerance,
        constitutive_energy_tolerance_j=constitutive_energy_tolerance,
    )


def _linf(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0


def _stable_l2(values: np.ndarray) -> float:
    """Compute an overflow-resistant Euclidean norm without changing meaning."""

    array = np.asarray(values, dtype="<f8")
    if not np.all(np.isfinite(array)):
        _fail("gate_scaled_residual_non_finite", "/physics_replay", "Scaled residual is non-finite.")
    scale = _linf(array)
    if scale == 0.0:
        return 0.0
    return scale * math.sqrt(float(np.sum((array / scale) ** 2)))


def _replay_stateless_linear_elastic_constitutive(
    plan: ExecutionPlan,
    displacement: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Reassemble element forces/energy from the compiled linear laws."""

    internal = np.zeros(plan.dof_count, dtype="<f8")
    total_energy = 0.0
    for element in plan.operator.element_operators:
        dofs = np.asarray(element.global_dofs, dtype=np.int64)
        global_u = displacement[dofs]
        local_u = element.transform_global_to_local @ global_u
        local_force = element.stiffness_local @ local_u
        global_force = element.transform_global_to_local.T @ local_force
        internal[dofs] += global_force
        total_energy += 0.5 * float(local_u @ local_force)
    if not np.all(np.isfinite(internal)) or not math.isfinite(total_energy):
        _fail(
            "gate_constitutive_replay_non_finite",
            "/physics_replay/constitutive_mode",
            "Stateless linear-elastic replay produced a non-finite value.",
        )
    return internal, total_energy


def _reason_codes(
    policy: ProposalPolicyReceipt,
    checks: GateChecks,
) -> tuple[str, ...]:
    if checks.eligible_initial_guess:
        return ("eligible_initial_guess",)
    reasons: list[str] = []
    pairs = (
        (checks.initial_guess_hook_pass, "initial_guess_hook_failed"),
        (checks.free_vector_space_pass, "target_vector_space_failed"),
        (checks.trust_budget_pass, "trust_budget_failed"),
        (checks.rank_budget_pass, "rank_budget_failed"),
        (checks.condition_pass, "condition_limit_failed"),
    )
    reasons.extend(code for passed, code in pairs if not passed)
    if not checks.ood_policy_pass:
        if policy.ood_status == "not_evaluated":
            reasons.append("ood_not_evaluated")
        elif policy.ood_status == "out_of_distribution":
            reasons.append("ood_out_of_distribution")
        else:
            reasons.append("ood_policy_failed")
        if not policy.statistical_calibration:
            reasons.append("statistical_calibration_missing")
    physics_pairs = (
        (
            checks.stateless_linear_elastic_constitutive_replayed,
            "constitutive_replay_failed",
        ),
        (
            checks.constitutive_admissibility_pass,
            "constitutive_admissibility_failed",
        ),
        (checks.free_scaled_residual_reduced, "free_scaled_residual_not_reduced"),
        (checks.total_potential_energy_nonincrease, "potential_energy_increased"),
        (checks.constrained_increment_exact_zero, "constrained_increment_nonzero"),
        (checks.rollback_exact, "rollback_failed"),
        (checks.accepted_state_preserved, "accepted_state_changed"),
    )
    reasons.extend(code for passed, code in physics_pairs if not passed)
    return tuple(reasons or ["proposal_rejected"])


def _receipt_payload(
    receipt: AIProposalGateReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "capability_profile": receipt.capability_profile,
        "gate_id": receipt.gate_id,
        "status": receipt.status,
        "reason_codes": list(receipt.reason_codes),
        "input_bindings": receipt.input_bindings.to_dict(),
        "proposal_policy": receipt.proposal_policy.to_dict(),
        "physics_replay": receipt.physics_replay.to_dict(),
        "checks": receipt.checks.to_dict(),
        "rollback_proof": receipt.rollback_proof.to_dict(),
        "authority": receipt.authority.to_dict(),
        "extensions": dict(receipt.extensions),
    }
    if include_hash:
        payload["gate_receipt_hash"] = receipt.gate_receipt_hash
    return payload


def _gate_receipt_hash(receipt: AIProposalGateReceipt) -> str:
    return canonical_hash(_receipt_payload(receipt, include_hash=False))


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "ai_proposal_gate_receipt_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise AIProposalGateError(code, path, message)


__all__ = [
    "AI_PROPOSAL_GATE_CAPABILITY_PROFILE",
    "AI_PROPOSAL_GATE_RECEIPT_SCHEMA_VERSION",
    "MAX_BASIS_GRAM_CONDITION",
    "AIProposalGateError",
    "AIProposalGateReceipt",
    "GateAuthority",
    "GateChecks",
    "GateInputBindings",
    "PhysicsReplayReceipt",
    "ProposalPolicyReceipt",
    "RollbackProof",
    "evaluate_ai_proposal_gate",
    "validate_ai_proposal_gate_receipt",
]
