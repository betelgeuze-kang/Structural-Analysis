"""Non-authoritative solver-episode contract for AI observation and replay.

The episode records solver observations, policy proposals, executed actions,
rollback outcomes, terminal disposition, and data-use eligibility while binding
all records to exact model/plan/state/backend identities. It is intentionally
non-authoritative: an episode can reference a separately authoritative result,
but it cannot create or promote numerical, engineering, design, release, or
commercial authority.

A terminal state reference is valid only when it equals the state hash of the
last accepted observation in the retained episode trace.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


SOLVER_EPISODE_SCHEMA_VERSION = "structural-analysis-solver-episode.v1"
SOLVER_EPISODE_AUTHORITY_PROFILE = "non_authoritative_solver_episode.v1"
SOLVER_EPISODE_CLAIM_BOUNDARY = MappingProxyType(
    {
        "solver_observation": True,
        "ai_policy_proposal": True,
        "executed_action_trace": True,
        "rollback_trace": True,
        "terminal_state_trace_bound": True,
        "training_eligibility_recorded": True,
        "solver_convergence_authority": False,
        "numerical_result_authority": False,
        "engineering_result_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

SolverEpisodeMode = Literal["baseline", "shadow", "guarded"]
ProposalDisposition = Literal["shadow_only", "eligible", "rejected"]
ActionSource = Literal["baseline", "ai_proposal", "human_override"]
ActionKind = Literal[
    "step_size",
    "solver_route",
    "restart_length",
    "preconditioner",
    "warm_start",
    "checkpoint_recovery",
]
TerminalReason = Literal[
    "converged",
    "max_iterations",
    "breakdown",
    "diverged",
    "blocked",
    "rolled_back",
]
FinalAuthorityStatus = Literal["none", "diagnostic", "numerical", "engineering"]

_ACTION_KINDS = {
    "step_size",
    "solver_route",
    "restart_length",
    "preconditioner",
    "warm_start",
    "checkpoint_recovery",
}
_MODES = {"baseline", "shadow", "guarded"}
_PROPOSAL_DISPOSITIONS = {"shadow_only", "eligible", "rejected"}
_ACTION_SOURCES = {"baseline", "ai_proposal", "human_override"}
_TERMINAL_REASONS = {
    "converged",
    "max_iterations",
    "breakdown",
    "diverged",
    "blocked",
    "rolled_back",
}
_AUTHORITY_STATUSES = {"none", "diagnostic", "numerical", "engineering"}
_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class SolverEpisodeError(ValueError):
    """Stable fail-closed solver-episode contract error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class SolverEpisodeObservation:
    observation_index: int
    state_hash: str
    iteration: int
    restart_index: int
    load_factor: float
    residual_linf: float
    scaled_residual_l2: float
    increment_linf: float
    runtime_ms: float
    accepted: bool
    rollback: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_index": self.observation_index,
            "state_hash": self.state_hash,
            "iteration": self.iteration,
            "restart_index": self.restart_index,
            "load_factor": self.load_factor,
            "residual_linf": self.residual_linf,
            "scaled_residual_l2": self.scaled_residual_l2,
            "increment_linf": self.increment_linf,
            "runtime_ms": self.runtime_ms,
            "accepted": self.accepted,
            "rollback": self.rollback,
        }


@dataclass(frozen=True)
class SolverActionProposal:
    proposal_index: int
    observation_index: int
    policy_id: str
    policy_version: str
    policy_artifact_hash: str
    action_kind: ActionKind
    action_payload_hash: str
    uncertainty: float
    ood: bool
    disposition: ProposalDisposition

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_index": self.proposal_index,
            "observation_index": self.observation_index,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_artifact_hash": self.policy_artifact_hash,
            "action_kind": self.action_kind,
            "action_payload_hash": self.action_payload_hash,
            "uncertainty": self.uncertainty,
            "ood": self.ood,
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class SolverExecutedAction:
    action_index: int
    observation_index: int
    proposal_index: int | None
    action_kind: ActionKind
    action_payload_hash: str
    source: ActionSource
    guard_receipt_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_index": self.action_index,
            "observation_index": self.observation_index,
            "proposal_index": self.proposal_index,
            "action_kind": self.action_kind,
            "action_payload_hash": self.action_payload_hash,
            "source": self.source,
            "guard_receipt_hash": self.guard_receipt_hash,
        }


@dataclass(frozen=True)
class SolverEpisodeTerminal:
    reason: TerminalReason
    converged: bool
    final_authority_status: FinalAuthorityStatus
    final_state_hash: str | None
    final_result_hash: str | None
    fallback_count: int
    regularization_count: int
    total_iterations: int
    total_runtime_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "converged": self.converged,
            "final_authority_status": self.final_authority_status,
            "final_state_hash": self.final_state_hash,
            "final_result_hash": self.final_result_hash,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "total_iterations": self.total_iterations,
            "total_runtime_ms": self.total_runtime_ms,
        }


@dataclass(frozen=True)
class SolverEpisodeDataUse:
    training_eligible: bool
    evaluation_only: bool
    source_license_receipt_hash: str | None
    privacy_receipt_hash: str | None
    raw_customer_payload_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_eligible": self.training_eligible,
            "evaluation_only": self.evaluation_only,
            "source_license_receipt_hash": self.source_license_receipt_hash,
            "privacy_receipt_hash": self.privacy_receipt_hash,
            "raw_customer_payload_included": self.raw_customer_payload_included,
        }


@dataclass(frozen=True)
class SolverEpisodeIR:
    schema_version: str
    episode_id: str
    episode_hash: str
    authority_profile: str
    model_ir_content_hash: str
    execution_plan_hash: str
    initial_state_hash: str
    analysis_profile: str
    backend_profile: str
    backend_receipt_hash: str
    episode_mode: SolverEpisodeMode
    observations: tuple[SolverEpisodeObservation, ...]
    proposals: tuple[SolverActionProposal, ...]
    executed_actions: tuple[SolverExecutedAction, ...]
    terminal: SolverEpisodeTerminal
    data_use: SolverEpisodeDataUse
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_solver_episode_ir(self)
        return _episode_payload(self, include_episode_hash=True)


def create_solver_episode_ir(
    *,
    episode_id: str,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    initial_state_hash: str,
    analysis_profile: str,
    backend_profile: str,
    backend_receipt_hash: str,
    episode_mode: SolverEpisodeMode,
    observations: Sequence[SolverEpisodeObservation],
    proposals: Sequence[SolverActionProposal],
    executed_actions: Sequence[SolverExecutedAction],
    terminal: SolverEpisodeTerminal,
    data_use: SolverEpisodeDataUse,
) -> SolverEpisodeIR:
    """Create one canonical non-authoritative solver episode."""

    provisional = SolverEpisodeIR(
        schema_version=SOLVER_EPISODE_SCHEMA_VERSION,
        episode_id=_require_stable_id(episode_id, "/episode_id"),
        episode_hash=_HASH_ZERO,
        authority_profile=SOLVER_EPISODE_AUTHORITY_PROFILE,
        model_ir_content_hash=_require_hash(
            model_ir_content_hash,
            "/bindings/model_ir_content_hash",
        ),
        execution_plan_hash=_require_hash(
            execution_plan_hash,
            "/bindings/execution_plan_hash",
        ),
        initial_state_hash=_require_hash(
            initial_state_hash,
            "/bindings/initial_state_hash",
        ),
        analysis_profile=_require_stable_id(
            analysis_profile,
            "/analysis_profile",
        ),
        backend_profile=_require_stable_id(
            backend_profile,
            "/backend/profile",
        ),
        backend_receipt_hash=_require_hash(
            backend_receipt_hash,
            "/backend/receipt_hash",
        ),
        episode_mode=_require_choice(
            episode_mode,
            _MODES,
            "/episode_mode",
        ),
        observations=tuple(observations),
        proposals=tuple(proposals),
        executed_actions=tuple(executed_actions),
        terminal=terminal,
        data_use=data_use,
        extensions=MappingProxyType({}),
    )
    episode = replace(
        provisional,
        episode_hash=canonical_hash(
            _episode_payload(provisional, include_episode_hash=False)
        ),
    )
    return validate_solver_episode_ir(episode)


def validate_solver_episode_ir(episode: SolverEpisodeIR) -> SolverEpisodeIR:
    """Recompute sequence, reference, policy, terminal, and hash invariants."""

    if type(episode) is not SolverEpisodeIR:
        _fail("solver_episode_type_invalid", "/", "Expected SolverEpisodeIR.")
    if episode.schema_version != SOLVER_EPISODE_SCHEMA_VERSION:
        _fail(
            "solver_episode_schema_invalid",
            "/schema_version",
            "Unsupported SolverEpisodeIR schema.",
        )
    if episode.authority_profile != SOLVER_EPISODE_AUTHORITY_PROFILE:
        _fail(
            "solver_episode_authority_profile_invalid",
            "/authority_profile",
            "Solver episodes cannot acquire result authority.",
        )
    _require_stable_id(episode.episode_id, "/episode_id")
    for path, value in (
        ("/episode_hash", episode.episode_hash),
        ("/bindings/model_ir_content_hash", episode.model_ir_content_hash),
        ("/bindings/execution_plan_hash", episode.execution_plan_hash),
        ("/bindings/initial_state_hash", episode.initial_state_hash),
        ("/backend/receipt_hash", episode.backend_receipt_hash),
    ):
        _require_hash(value, path)
    _require_stable_id(episode.analysis_profile, "/analysis_profile")
    _require_stable_id(episode.backend_profile, "/backend/profile")
    mode = _require_choice(episode.episode_mode, _MODES, "/episode_mode")

    observations = _validate_observations(episode.observations)
    proposals = _validate_proposals(
        episode.proposals,
        observation_count=len(observations),
        mode=mode,
    )
    _validate_executed_actions(
        episode.executed_actions,
        observation_count=len(observations),
        proposals=proposals,
        mode=mode,
    )
    _validate_terminal(episode.terminal, observations)
    _validate_data_use(episode.data_use)

    if not isinstance(episode.extensions, MappingProxyType) or episode.extensions:
        _fail(
            "solver_episode_extensions_invalid",
            "/extensions",
            "SolverEpisodeIR v1 requires an immutable empty extensions object.",
        )
    expected_hash = canonical_hash(
        _episode_payload(episode, include_episode_hash=False)
    )
    if episode.episode_hash != expected_hash:
        _fail(
            "solver_episode_hash_mismatch",
            "/episode_hash",
            "Episode hash does not match canonical content.",
        )
    return episode


def validate_solver_episode_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a strict imported episode manifest and semantic references."""

    if not isinstance(payload, Mapping):
        _fail(
            "solver_episode_manifest_type_invalid",
            "/",
            "Solver episode manifest must be an object.",
        )
    try:
        normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        _fail(
            "solver_episode_manifest_json_invalid",
            "/",
            "Solver episode manifest must be finite strict JSON.",
            cause=exc,
        )
    errors = sorted(
        _manifest_validator().iter_errors(normalized),
        key=lambda row: tuple(str(value) for value in row.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(value) for value in first.absolute_path)
        _fail(
            "solver_episode_manifest_schema_invalid",
            path or "/",
            first.message,
        )
    _validate_manifest_semantics(normalized)
    expected_hash = canonical_hash(
        {key: value for key, value in normalized.items() if key != "episode_hash"}
    )
    if normalized["episode_hash"] != expected_hash:
        _fail(
            "solver_episode_hash_mismatch",
            "/episode_hash",
            "Episode hash does not match canonical content.",
        )
    return normalized


def _validate_observations(
    values: tuple[SolverEpisodeObservation, ...],
) -> tuple[SolverEpisodeObservation, ...]:
    if type(values) is not tuple or not values:
        _fail(
            "solver_episode_observations_invalid",
            "/observations",
            "Observations must be a non-empty tuple.",
        )
    for index, value in enumerate(values):
        path = f"/observations/{index}"
        if type(value) is not SolverEpisodeObservation:
            _fail(
                "solver_episode_observation_type_invalid",
                path,
                "Expected SolverEpisodeObservation.",
            )
        if value.observation_index != index:
            _fail(
                "solver_episode_observation_index_invalid",
                f"{path}/observation_index",
                "Observation indices must be contiguous and ordered.",
            )
        _require_hash(value.state_hash, f"{path}/state_hash")
        _require_index(value.iteration, f"{path}/iteration")
        _require_index(value.restart_index, f"{path}/restart_index")
        _require_finite(value.load_factor, f"{path}/load_factor")
        for name in (
            "residual_linf",
            "scaled_residual_l2",
            "increment_linf",
            "runtime_ms",
        ):
            _require_nonnegative(getattr(value, name), f"{path}/{name}")
        _require_bool(value.accepted, f"{path}/accepted")
        _require_bool(value.rollback, f"{path}/rollback")
        if value.accepted and value.rollback:
            _fail(
                "solver_episode_observation_disposition_invalid",
                path,
                "An observation cannot be accepted and rolled back.",
            )
    return values


def _validate_proposals(
    values: tuple[SolverActionProposal, ...],
    *,
    observation_count: int,
    mode: str,
) -> tuple[SolverActionProposal, ...]:
    if type(values) is not tuple:
        _fail(
            "solver_episode_proposals_invalid",
            "/proposals",
            "Proposals must use an immutable tuple.",
        )
    if mode == "baseline" and values:
        _fail(
            "baseline_episode_proposals_forbidden",
            "/proposals",
            "Baseline episodes cannot contain AI proposals.",
        )
    for index, value in enumerate(values):
        path = f"/proposals/{index}"
        if type(value) is not SolverActionProposal:
            _fail(
                "solver_episode_proposal_type_invalid",
                path,
                "Expected SolverActionProposal.",
            )
        if value.proposal_index != index:
            _fail(
                "solver_episode_proposal_index_invalid",
                f"{path}/proposal_index",
                "Proposal indices must be contiguous and ordered.",
            )
        _require_reference(
            value.observation_index,
            observation_count,
            f"{path}/observation_index",
        )
        _require_stable_id(value.policy_id, f"{path}/policy_id")
        _require_stable_id(value.policy_version, f"{path}/policy_version")
        _require_hash(value.policy_artifact_hash, f"{path}/policy_artifact_hash")
        _require_choice(value.action_kind, _ACTION_KINDS, f"{path}/action_kind")
        _require_hash(value.action_payload_hash, f"{path}/action_payload_hash")
        _require_nonnegative(value.uncertainty, f"{path}/uncertainty")
        _require_bool(value.ood, f"{path}/ood")
        disposition = _require_choice(
            value.disposition,
            _PROPOSAL_DISPOSITIONS,
            f"{path}/disposition",
        )
        if value.ood and disposition == "eligible":
            _fail(
                "ood_proposal_eligible_for_execution",
                f"{path}/disposition",
                "OOD proposals cannot be eligible for execution.",
            )
        if mode == "shadow" and disposition == "eligible":
            _fail(
                "shadow_proposal_eligible_for_execution",
                f"{path}/disposition",
                "Shadow proposals must remain shadow-only or rejected.",
            )
    return values


def _validate_executed_actions(
    values: tuple[SolverExecutedAction, ...],
    *,
    observation_count: int,
    proposals: tuple[SolverActionProposal, ...],
    mode: str,
) -> None:
    if type(values) is not tuple:
        _fail(
            "solver_episode_actions_invalid",
            "/executed_actions",
            "Executed actions must use an immutable tuple.",
        )
    for index, value in enumerate(values):
        path = f"/executed_actions/{index}"
        if type(value) is not SolverExecutedAction:
            _fail(
                "solver_episode_action_type_invalid",
                path,
                "Expected SolverExecutedAction.",
            )
        if value.action_index != index:
            _fail(
                "solver_episode_action_index_invalid",
                f"{path}/action_index",
                "Action indices must be contiguous and ordered.",
            )
        _require_reference(
            value.observation_index,
            observation_count,
            f"{path}/observation_index",
        )
        action_kind = _require_choice(
            value.action_kind,
            _ACTION_KINDS,
            f"{path}/action_kind",
        )
        action_hash = _require_hash(
            value.action_payload_hash,
            f"{path}/action_payload_hash",
        )
        source = _require_choice(value.source, _ACTION_SOURCES, f"{path}/source")
        if source == "ai_proposal":
            if mode != "guarded":
                _fail(
                    "ai_action_execution_mode_invalid",
                    f"{path}/source",
                    "AI proposals may execute only in guarded episodes.",
                )
            if value.proposal_index is None:
                _fail(
                    "executed_ai_action_proposal_missing",
                    f"{path}/proposal_index",
                    "AI action requires a proposal reference.",
                )
            proposal_index = _require_reference(
                value.proposal_index,
                len(proposals),
                f"{path}/proposal_index",
            )
            proposal = proposals[proposal_index]
            if (
                proposal.observation_index != value.observation_index
                or proposal.action_kind != action_kind
                or proposal.action_payload_hash != action_hash
            ):
                _fail(
                    "executed_ai_action_proposal_mismatch",
                    path,
                    "Executed AI action does not match its proposal.",
                )
            if proposal.disposition != "eligible" or proposal.ood:
                _fail(
                    "executed_ai_action_not_eligible",
                    f"{path}/proposal_index",
                    "Executed AI action was rejected, shadow-only, or OOD.",
                )
            if value.guard_receipt_hash is None:
                _fail(
                    "executed_ai_action_guard_missing",
                    f"{path}/guard_receipt_hash",
                    "Guarded AI execution requires a guard receipt.",
                )
            _require_hash(value.guard_receipt_hash, f"{path}/guard_receipt_hash")
        else:
            if value.proposal_index is not None:
                _fail(
                    "non_ai_action_proposal_reference_invalid",
                    f"{path}/proposal_index",
                    "Baseline and human actions cannot claim an AI proposal.",
                )
            if value.guard_receipt_hash is not None:
                _fail(
                    "non_ai_action_guard_receipt_invalid",
                    f"{path}/guard_receipt_hash",
                    "Baseline and human actions do not use AI guard receipts.",
                )


def _last_accepted_state_hash(
    observations: Sequence[SolverEpisodeObservation] | Sequence[Mapping[str, Any]],
) -> str | None:
    accepted = [row for row in observations if bool(_field(row, "accepted"))]
    if not accepted:
        return None
    return str(_field(accepted[-1], "state_hash"))


def _validate_terminal(
    value: SolverEpisodeTerminal,
    observations: tuple[SolverEpisodeObservation, ...],
) -> None:
    path = "/terminal"
    if type(value) is not SolverEpisodeTerminal:
        _fail(
            "solver_episode_terminal_type_invalid",
            path,
            "Expected SolverEpisodeTerminal.",
        )
    reason = _require_choice(value.reason, _TERMINAL_REASONS, f"{path}/reason")
    converged = _require_bool(value.converged, f"{path}/converged")
    authority = _require_choice(
        value.final_authority_status,
        _AUTHORITY_STATUSES,
        f"{path}/final_authority_status",
    )
    if converged != (reason == "converged"):
        _fail(
            "solver_episode_terminal_convergence_mismatch",
            path,
            "Only reason=converged may set converged=true.",
        )
    for name in ("fallback_count", "regularization_count", "total_iterations"):
        _require_index(getattr(value, name), f"{path}/{name}")
    _require_nonnegative(value.total_runtime_ms, f"{path}/total_runtime_ms")
    if value.final_state_hash is not None:
        _require_hash(value.final_state_hash, f"{path}/final_state_hash")
    if value.final_result_hash is not None:
        _require_hash(value.final_result_hash, f"{path}/final_result_hash")
    if authority in {"numerical", "engineering"}:
        if not converged or value.final_state_hash is None or value.final_result_hash is None:
            _fail(
                "solver_episode_terminal_authority_binding_missing",
                path,
                "Numerical/engineering references require a converged state and result hash.",
            )
    if authority == "none" and value.final_result_hash is not None:
        _fail(
            "solver_episode_terminal_result_without_authority_reference",
            f"{path}/final_result_hash",
            "Authority status none cannot reference a final result.",
        )
    last_accepted = _last_accepted_state_hash(observations)
    if value.final_state_hash is not None and last_accepted is None:
        _fail(
            "solver_episode_terminal_state_without_accepted_observation",
            f"{path}/final_state_hash",
            "A terminal state reference requires an accepted observation.",
        )
    if value.final_state_hash is not None and value.final_state_hash != last_accepted:
        _fail(
            "solver_episode_terminal_state_trace_mismatch",
            f"{path}/final_state_hash",
            "Terminal state must equal the last accepted observation state.",
        )


def _validate_data_use(value: SolverEpisodeDataUse) -> None:
    path = "/data_use"
    if type(value) is not SolverEpisodeDataUse:
        _fail(
            "solver_episode_data_use_type_invalid",
            path,
            "Expected SolverEpisodeDataUse.",
        )
    training = _require_bool(value.training_eligible, f"{path}/training_eligible")
    evaluation = _require_bool(value.evaluation_only, f"{path}/evaluation_only")
    raw_customer = _require_bool(
        value.raw_customer_payload_included,
        f"{path}/raw_customer_payload_included",
    )
    if raw_customer:
        _fail(
            "solver_episode_raw_customer_payload_forbidden",
            f"{path}/raw_customer_payload_included",
            "SolverEpisodeIR cannot embed raw customer payloads.",
        )
    license_hash = value.source_license_receipt_hash
    privacy_hash = value.privacy_receipt_hash
    if license_hash is not None:
        _require_hash(license_hash, f"{path}/source_license_receipt_hash")
    if privacy_hash is not None:
        _require_hash(privacy_hash, f"{path}/privacy_receipt_hash")
    if training and (evaluation or license_hash is None or privacy_hash is None):
        _fail(
            "solver_episode_training_eligibility_invalid",
            path,
            "Training eligibility requires license/privacy receipts and evaluation_only=false.",
        )


def _validate_manifest_semantics(payload: Mapping[str, Any]) -> None:
    mode = payload["episode_mode"]
    observations = payload["observations"]
    proposals = payload["proposals"]
    actions = payload["executed_actions"]
    if not observations:
        _fail(
            "solver_episode_observations_invalid",
            "/observations",
            "At least one observation is required.",
        )
    for index, row in enumerate(observations):
        if row["observation_index"] != index:
            _fail(
                "solver_episode_observation_index_invalid",
                f"/observations/{index}/observation_index",
                "Observation indices must be contiguous and ordered.",
            )
        if row["accepted"] and row["rollback"]:
            _fail(
                "solver_episode_observation_disposition_invalid",
                f"/observations/{index}",
                "An observation cannot be accepted and rolled back.",
            )
    if mode == "baseline" and proposals:
        _fail(
            "baseline_episode_proposals_forbidden",
            "/proposals",
            "Baseline episodes cannot contain AI proposals.",
        )
    for index, row in enumerate(proposals):
        if row["proposal_index"] != index:
            _fail(
                "solver_episode_proposal_index_invalid",
                f"/proposals/{index}/proposal_index",
                "Proposal indices must be contiguous and ordered.",
            )
        if row["observation_index"] >= len(observations):
            _fail(
                "solver_episode_reference_out_of_range",
                f"/proposals/{index}/observation_index",
                "Proposal references an unknown observation.",
            )
        if row["ood"] and row["disposition"] == "eligible":
            _fail(
                "ood_proposal_eligible_for_execution",
                f"/proposals/{index}/disposition",
                "OOD proposals cannot be eligible.",
            )
        if mode == "shadow" and row["disposition"] == "eligible":
            _fail(
                "shadow_proposal_eligible_for_execution",
                f"/proposals/{index}/disposition",
                "Shadow proposals cannot be eligible.",
            )
    for index, row in enumerate(actions):
        if row["action_index"] != index:
            _fail(
                "solver_episode_action_index_invalid",
                f"/executed_actions/{index}/action_index",
                "Action indices must be contiguous and ordered.",
            )
        if row["observation_index"] >= len(observations):
            _fail(
                "solver_episode_reference_out_of_range",
                f"/executed_actions/{index}/observation_index",
                "Action references an unknown observation.",
            )
        if row["source"] == "ai_proposal":
            if mode != "guarded" or row["proposal_index"] is None:
                _fail(
                    "ai_action_execution_mode_invalid",
                    f"/executed_actions/{index}",
                    "AI action execution requires guarded mode and a proposal.",
                )
            proposal_index = row["proposal_index"]
            if proposal_index >= len(proposals):
                _fail(
                    "solver_episode_reference_out_of_range",
                    f"/executed_actions/{index}/proposal_index",
                    "Action references an unknown proposal.",
                )
            proposal = proposals[proposal_index]
            if (
                proposal["observation_index"] != row["observation_index"]
                or proposal["action_kind"] != row["action_kind"]
                or proposal["action_payload_hash"] != row["action_payload_hash"]
                or proposal["disposition"] != "eligible"
                or proposal["ood"]
                or row["guard_receipt_hash"] is None
            ):
                _fail(
                    "executed_ai_action_not_eligible",
                    f"/executed_actions/{index}",
                    "Executed AI action is not a matching eligible guarded proposal.",
                )
        elif row["proposal_index"] is not None or row["guard_receipt_hash"] is not None:
            _fail(
                "non_ai_action_reference_invalid",
                f"/executed_actions/{index}",
                "Non-AI actions cannot reference proposals or AI guard receipts.",
            )

    terminal = payload["terminal"]
    if terminal["converged"] != (terminal["reason"] == "converged"):
        _fail(
            "solver_episode_terminal_convergence_mismatch",
            "/terminal",
            "Only reason=converged may set converged=true.",
        )
    if terminal["final_authority_status"] in ("numerical", "engineering") and (
        not terminal["converged"]
        or terminal["final_state_hash"] is None
        or terminal["final_result_hash"] is None
    ):
        _fail(
            "solver_episode_terminal_authority_binding_missing",
            "/terminal",
            "Numerical/engineering references require converged state/result hashes.",
        )
    if (
        terminal["final_authority_status"] == "none"
        and terminal["final_result_hash"] is not None
    ):
        _fail(
            "solver_episode_terminal_result_without_authority_reference",
            "/terminal/final_result_hash",
            "Authority status none cannot reference a final result.",
        )
    last_accepted = _last_accepted_state_hash(observations)
    if terminal["final_state_hash"] is not None and last_accepted is None:
        _fail(
            "solver_episode_terminal_state_without_accepted_observation",
            "/terminal/final_state_hash",
            "A terminal state reference requires an accepted observation.",
        )
    if (
        terminal["final_state_hash"] is not None
        and terminal["final_state_hash"] != last_accepted
    ):
        _fail(
            "solver_episode_terminal_state_trace_mismatch",
            "/terminal/final_state_hash",
            "Terminal state must equal the last accepted observation state.",
        )

    data_use = payload["data_use"]
    if data_use["raw_customer_payload_included"]:
        _fail(
            "solver_episode_raw_customer_payload_forbidden",
            "/data_use/raw_customer_payload_included",
            "SolverEpisodeIR cannot embed raw customer payloads.",
        )
    if data_use["training_eligible"] and (
        data_use["evaluation_only"]
        or data_use["source_license_receipt_hash"] is None
        or data_use["privacy_receipt_hash"] is None
    ):
        _fail(
            "solver_episode_training_eligibility_invalid",
            "/data_use",
            "Training eligibility requires license/privacy receipts and evaluation_only=false.",
        )


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def _episode_payload(
    episode: SolverEpisodeIR,
    *,
    include_episode_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": episode.schema_version,
        "episode_id": episode.episode_id,
        "episode_hash": episode.episode_hash,
        "authority_profile": episode.authority_profile,
        "bindings": {
            "model_ir_content_hash": episode.model_ir_content_hash,
            "execution_plan_hash": episode.execution_plan_hash,
            "initial_state_hash": episode.initial_state_hash,
        },
        "analysis_profile": episode.analysis_profile,
        "backend": {
            "profile": episode.backend_profile,
            "receipt_hash": episode.backend_receipt_hash,
        },
        "episode_mode": episode.episode_mode,
        "observations": [row.to_dict() for row in episode.observations],
        "proposals": [row.to_dict() for row in episode.proposals],
        "executed_actions": [row.to_dict() for row in episode.executed_actions],
        "terminal": episode.terminal.to_dict(),
        "data_use": episode.data_use.to_dict(),
        "extensions": dict(episode.extensions),
    }
    if not include_episode_hash:
        payload.pop("episode_hash")
    return payload


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail(
            "solver_episode_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _require_stable_id(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _STABLE_ID_PATTERN.fullmatch(normalized):
        _fail(
            "solver_episode_id_invalid",
            path,
            "Expected a stable non-empty identifier.",
        )
    return normalized


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "solver_episode_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _require_reference(value: Any, count: int, path: str) -> int:
    normalized = _require_index(value, path)
    if normalized >= count:
        _fail(
            "solver_episode_reference_out_of_range",
            path,
            "Reference points outside the retained episode sequence.",
        )
    return normalized


def _require_finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "solver_episode_number_invalid",
            path,
            "Expected a finite JSON number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "solver_episode_number_invalid",
            path,
            "Expected a finite JSON number.",
        )
    return normalized


def _require_nonnegative(value: Any, path: str) -> float:
    normalized = _require_finite(value, path)
    if normalized < 0.0:
        _fail(
            "solver_episode_number_negative",
            path,
            "Expected a non-negative number.",
        )
    return normalized


def _require_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        _fail(
            "solver_episode_boolean_invalid",
            path,
            "Expected an exact JSON boolean.",
        )
    return value


def _require_choice(value: Any, allowed: set[str], path: str) -> str:
    normalized = str(value)
    if normalized not in allowed:
        _fail(
            "solver_episode_enum_invalid",
            path,
            f"Unsupported value: {normalized}",
        )
    return normalized


@lru_cache(maxsize=1)
def _manifest_validator() -> Draft202012Validator:
    schema_path = resources.files("structural_analysis.schemas").joinpath(
        "solver_episode_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return _StrictDraft202012Validator(schema)


def _fail(
    code: str,
    path: str,
    message: str,
    *,
    cause: Exception | None = None,
) -> None:
    error = SolverEpisodeError(code, path, message)
    if cause is not None:
        raise error from cause
    raise error


__all__ = [
    "SOLVER_EPISODE_AUTHORITY_PROFILE",
    "SOLVER_EPISODE_CLAIM_BOUNDARY",
    "SOLVER_EPISODE_SCHEMA_VERSION",
    "SolverActionProposal",
    "SolverEpisodeDataUse",
    "SolverEpisodeError",
    "SolverEpisodeIR",
    "SolverEpisodeObservation",
    "SolverEpisodeTerminal",
    "SolverExecutedAction",
    "create_solver_episode_ir",
    "validate_solver_episode_ir",
    "validate_solver_episode_manifest",
]
