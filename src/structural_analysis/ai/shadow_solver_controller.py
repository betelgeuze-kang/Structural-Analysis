"""Shadow-only solver-policy plumbing.

The controller records policy proposals beside deterministic baseline actions
and emits a ``SolverEpisodeIR`` in ``shadow`` mode. It never executes an AI
proposal and never changes solver/result authority.

The bundled deterministic residual-step policy is a wiring/reference policy,
not a trained AI model. Future learned policies may implement the same
``ShadowStepPolicy`` protocol while remaining subject to OOD, license/privacy,
replay, and physics guards.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Protocol, Sequence

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.solver_episode import (
    SolverActionProposal,
    SolverEpisodeDataUse,
    SolverEpisodeIR,
    SolverEpisodeObservation,
    SolverEpisodeTerminal,
    SolverExecutedAction,
    create_solver_episode_ir,
)


SHADOW_STEP_ACTION_UNIT = "load_factor_increment"
SHADOW_CONTROLLER_PROFILE = "shadow-step-controller.v1"
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHADOW_DISPOSITIONS = {"shadow_only", "rejected"}


class ShadowSolverControllerError(ValueError):
    """Fail-closed shadow-controller input or policy error."""


class ShadowStepPolicy(Protocol):
    policy_id: str
    policy_version: str
    minimum_step_size: float
    maximum_step_size: float

    @property
    def artifact_hash(self) -> str: ...

    def propose(self, value: "ShadowStepInput") -> "ShadowStepDecision": ...


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise ShadowSolverControllerError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ShadowSolverControllerError(f"{name} must be a finite number")
    return normalized


def _positive(value: Any, *, name: str) -> float:
    normalized = _finite(value, name=name)
    if normalized <= 0.0:
        raise ShadowSolverControllerError(f"{name} must be positive")
    return normalized


def _sha256(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        raise ShadowSolverControllerError(
            f"{name} must be a lowercase sha256:<hex> hash"
        )
    return normalized


def _ratio(current: float, previous: float) -> float:
    if previous == 0.0:
        return 0.0 if current == 0.0 else math.inf
    return current / previous


def _step_payload_hash(*, step_size: float, source_profile: str) -> str:
    return canonical_hash(
        {
            "action_kind": "step_size",
            "step_size": float(step_size),
            "unit": SHADOW_STEP_ACTION_UNIT,
            "source_profile": source_profile,
        }
    )


@dataclass(frozen=True)
class ShadowStepInput:
    """One observation and its deterministic baseline next-step action."""

    observation: SolverEpisodeObservation
    current_step_size: float
    baseline_next_step_size: float
    previous_residual_linf: float | None
    supported_model_family: bool = True

    def __post_init__(self) -> None:
        if type(self.observation) is not SolverEpisodeObservation:
            raise ShadowSolverControllerError(
                "observation must be a SolverEpisodeObservation"
            )
        object.__setattr__(
            self,
            "current_step_size",
            _positive(self.current_step_size, name="current_step_size"),
        )
        object.__setattr__(
            self,
            "baseline_next_step_size",
            _positive(
                self.baseline_next_step_size,
                name="baseline_next_step_size",
            ),
        )
        if self.previous_residual_linf is not None:
            previous = _finite(
                self.previous_residual_linf,
                name="previous_residual_linf",
            )
            if previous < 0.0:
                raise ShadowSolverControllerError(
                    "previous_residual_linf must be non-negative"
                )
            object.__setattr__(self, "previous_residual_linf", previous)
        if type(self.supported_model_family) is not bool:
            raise ShadowSolverControllerError(
                "supported_model_family must be an exact boolean"
            )


@dataclass(frozen=True)
class ShadowStepDecision:
    observation_index: int
    current_step_size: float
    baseline_next_step_size: float
    proposed_step_size: float
    residual_ratio: float | None
    reason_code: str
    uncertainty: float
    ood: bool
    disposition: str
    action_payload_hash: str
    policy_artifact_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_index": self.observation_index,
            "current_step_size": self.current_step_size,
            "baseline_next_step_size": self.baseline_next_step_size,
            "proposed_step_size": self.proposed_step_size,
            "residual_ratio": self.residual_ratio,
            "reason_code": self.reason_code,
            "uncertainty": self.uncertainty,
            "ood": self.ood,
            "disposition": self.disposition,
            "action_payload_hash": self.action_payload_hash,
            "policy_artifact_hash": self.policy_artifact_hash,
        }


@dataclass(frozen=True)
class DeterministicResidualStepPolicy:
    """Deterministic reference policy used to validate shadow plumbing."""

    minimum_step_size: float = 1.0e-4
    maximum_step_size: float = 0.25
    grow_factor: float = 1.25
    shrink_factor: float = 0.5
    strong_reduction_ratio: float = 0.25
    weak_reduction_ratio: float = 0.9
    policy_id: str = "deterministic-residual-step-policy"
    policy_version: str = "v1"

    def __post_init__(self) -> None:
        minimum = _positive(self.minimum_step_size, name="minimum_step_size")
        maximum = _positive(self.maximum_step_size, name="maximum_step_size")
        if minimum > maximum:
            raise ShadowSolverControllerError(
                "minimum_step_size cannot exceed maximum_step_size"
            )
        grow = _positive(self.grow_factor, name="grow_factor")
        shrink = _positive(self.shrink_factor, name="shrink_factor")
        if grow <= 1.0:
            raise ShadowSolverControllerError("grow_factor must exceed one")
        if shrink >= 1.0:
            raise ShadowSolverControllerError("shrink_factor must be below one")
        strong = _finite(
            self.strong_reduction_ratio,
            name="strong_reduction_ratio",
        )
        weak = _finite(
            self.weak_reduction_ratio,
            name="weak_reduction_ratio",
        )
        if strong < 0.0 or weak <= strong or weak > 1.0:
            raise ShadowSolverControllerError(
                "residual ratio thresholds must satisfy 0 <= strong < weak <= 1"
            )
        if not str(self.policy_id).strip() or not str(self.policy_version).strip():
            raise ShadowSolverControllerError(
                "policy_id and policy_version must be non-empty"
            )
        object.__setattr__(self, "minimum_step_size", minimum)
        object.__setattr__(self, "maximum_step_size", maximum)
        object.__setattr__(self, "grow_factor", grow)
        object.__setattr__(self, "shrink_factor", shrink)
        object.__setattr__(self, "strong_reduction_ratio", strong)
        object.__setattr__(self, "weak_reduction_ratio", weak)

    @property
    def artifact_hash(self) -> str:
        return canonical_hash(
            {
                "profile": SHADOW_CONTROLLER_PROFILE,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "minimum_step_size": self.minimum_step_size,
                "maximum_step_size": self.maximum_step_size,
                "grow_factor": self.grow_factor,
                "shrink_factor": self.shrink_factor,
                "strong_reduction_ratio": self.strong_reduction_ratio,
                "weak_reduction_ratio": self.weak_reduction_ratio,
            }
        )

    def propose(self, value: ShadowStepInput) -> ShadowStepDecision:
        if type(value) is not ShadowStepInput:
            raise ShadowSolverControllerError("policy input must be a ShadowStepInput")
        current = value.current_step_size
        if current < self.minimum_step_size or current > self.maximum_step_size:
            raise ShadowSolverControllerError(
                "current_step_size is outside the declared policy range"
            )
        baseline = value.baseline_next_step_size
        if baseline < self.minimum_step_size or baseline > self.maximum_step_size:
            raise ShadowSolverControllerError(
                "baseline_next_step_size is outside the declared policy range"
            )

        if not value.supported_model_family:
            proposed = current
            ratio = None
            reason = "ood_model_family"
            uncertainty = 1.0
            ood = True
            disposition = "rejected"
        elif value.observation.rollback:
            proposed = current * self.shrink_factor
            ratio = None
            reason = "rollback_shrink"
            uncertainty = 0.05
            ood = False
            disposition = "shadow_only"
        elif value.previous_residual_linf is None:
            proposed = current
            ratio = None
            reason = "insufficient_history_hold"
            uncertainty = 0.5
            ood = False
            disposition = "shadow_only"
        else:
            ratio = _ratio(
                value.observation.residual_linf,
                value.previous_residual_linf,
            )
            if ratio <= self.strong_reduction_ratio:
                proposed = current * self.grow_factor
                reason = "strong_residual_reduction_grow"
                uncertainty = 0.05
            elif ratio >= self.weak_reduction_ratio:
                proposed = current * self.shrink_factor
                reason = "weak_residual_reduction_shrink"
                uncertainty = 0.1
            else:
                proposed = current
                reason = "moderate_residual_reduction_hold"
                uncertainty = 0.2
            ood = False
            disposition = "shadow_only"

        proposed = min(
            self.maximum_step_size,
            max(self.minimum_step_size, proposed),
        )
        payload_hash = _step_payload_hash(
            step_size=proposed,
            source_profile=self.artifact_hash,
        )
        return ShadowStepDecision(
            observation_index=value.observation.observation_index,
            current_step_size=current,
            baseline_next_step_size=baseline,
            proposed_step_size=float(proposed),
            residual_ratio=(
                None if ratio is None or not math.isfinite(ratio) else float(ratio)
            ),
            reason_code=reason,
            uncertainty=uncertainty,
            ood=ood,
            disposition=disposition,
            action_payload_hash=payload_hash,
            policy_artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True)
class ShadowSolverControllerRun:
    episode: SolverEpisodeIR
    decisions: tuple[ShadowStepDecision, ...]
    baseline_action_payload_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": SHADOW_CONTROLLER_PROFILE,
            "episode": self.episode.to_manifest(),
            "decisions": [row.to_dict() for row in self.decisions],
            "baseline_action_payload_hashes": list(self.baseline_action_payload_hashes),
            "ai_action_executed": False,
            "result_authority": False,
        }


def _validate_policy(policy: ShadowStepPolicy) -> tuple[str, float, float]:
    policy_id = str(getattr(policy, "policy_id", "")).strip()
    policy_version = str(getattr(policy, "policy_version", "")).strip()
    if not policy_id or not policy_version:
        raise ShadowSolverControllerError(
            "policy_id and policy_version must be non-empty"
        )
    artifact_hash = _sha256(
        getattr(policy, "artifact_hash", ""),
        name="policy artifact_hash",
    )
    minimum = _positive(
        getattr(policy, "minimum_step_size", None),
        name="policy minimum_step_size",
    )
    maximum = _positive(
        getattr(policy, "maximum_step_size", None),
        name="policy maximum_step_size",
    )
    if minimum > maximum:
        raise ShadowSolverControllerError(
            "policy minimum_step_size cannot exceed maximum_step_size"
        )
    return artifact_hash, minimum, maximum


def _validate_decision(
    policy: ShadowStepPolicy,
    row: ShadowStepInput,
    decision: ShadowStepDecision,
    *,
    policy_hash: str,
    minimum_step_size: float,
    maximum_step_size: float,
) -> ShadowStepDecision:
    if type(decision) is not ShadowStepDecision:
        raise ShadowSolverControllerError(
            "policy must return an exact ShadowStepDecision"
        )
    if decision.observation_index != row.observation.observation_index:
        raise ShadowSolverControllerError(
            "decision observation_index does not match policy input"
        )
    current = _positive(decision.current_step_size, name="decision current_step_size")
    baseline = _positive(
        decision.baseline_next_step_size,
        name="decision baseline_next_step_size",
    )
    proposed = _positive(
        decision.proposed_step_size,
        name="decision proposed_step_size",
    )
    if current != row.current_step_size or baseline != row.baseline_next_step_size:
        raise ShadowSolverControllerError(
            "decision current/baseline step does not match policy input"
        )
    if proposed < minimum_step_size or proposed > maximum_step_size:
        raise ShadowSolverControllerError(
            "decision proposed_step_size is outside the declared policy range"
        )
    if decision.residual_ratio is not None:
        ratio = _finite(decision.residual_ratio, name="decision residual_ratio")
        if ratio < 0.0:
            raise ShadowSolverControllerError(
                "decision residual_ratio must be non-negative"
            )
    uncertainty = _finite(decision.uncertainty, name="decision uncertainty")
    if uncertainty < 0.0:
        raise ShadowSolverControllerError("decision uncertainty must be non-negative")
    if type(decision.ood) is not bool:
        raise ShadowSolverControllerError("decision ood must be an exact boolean")
    if decision.disposition not in _SHADOW_DISPOSITIONS:
        raise ShadowSolverControllerError(
            "shadow decision disposition must be shadow_only or rejected"
        )
    if decision.ood and decision.disposition != "rejected":
        raise ShadowSolverControllerError("OOD shadow decisions must be rejected")
    if not str(decision.reason_code).strip():
        raise ShadowSolverControllerError("decision reason_code must be non-empty")
    if decision.policy_artifact_hash != policy_hash:
        raise ShadowSolverControllerError(
            "decision policy_artifact_hash does not match selected policy"
        )
    expected_action_hash = _step_payload_hash(
        step_size=proposed,
        source_profile=policy_hash,
    )
    if decision.action_payload_hash != expected_action_hash:
        raise ShadowSolverControllerError(
            "decision action_payload_hash does not match proposed_step_size"
        )
    return decision


def build_shadow_step_solver_episode(
    *,
    episode_id: str,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    initial_state_hash: str,
    analysis_profile: str,
    backend_profile: str,
    backend_receipt_hash: str,
    rows: Sequence[ShadowStepInput],
    terminal: SolverEpisodeTerminal,
    data_use: SolverEpisodeDataUse,
    policy: ShadowStepPolicy | None = None,
) -> ShadowSolverControllerRun:
    """Build a shadow episode with baseline actions and non-executed proposals."""

    if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
        raise ShadowSolverControllerError("rows must be a non-string sequence")
    normalized_rows = tuple(rows)
    if not normalized_rows:
        raise ShadowSolverControllerError("rows must be non-empty")
    if any(type(row) is not ShadowStepInput for row in normalized_rows):
        raise ShadowSolverControllerError("rows must contain ShadowStepInput values")

    selected_policy = policy or DeterministicResidualStepPolicy()
    policy_hash, minimum_step, maximum_step = _validate_policy(selected_policy)
    decisions = tuple(
        _validate_decision(
            selected_policy,
            row,
            selected_policy.propose(row),
            policy_hash=policy_hash,
            minimum_step_size=minimum_step,
            maximum_step_size=maximum_step,
        )
        for row in normalized_rows
    )
    observations = tuple(row.observation for row in normalized_rows)
    proposals = tuple(
        SolverActionProposal(
            proposal_index=index,
            observation_index=decision.observation_index,
            policy_id=selected_policy.policy_id,
            policy_version=selected_policy.policy_version,
            policy_artifact_hash=policy_hash,
            action_kind="step_size",
            action_payload_hash=decision.action_payload_hash,
            uncertainty=decision.uncertainty,
            ood=decision.ood,
            disposition=decision.disposition,
        )
        for index, decision in enumerate(decisions)
    )
    baseline_hashes = tuple(
        _step_payload_hash(
            step_size=row.baseline_next_step_size,
            source_profile="deterministic-baseline-step-policy.v1",
        )
        for row in normalized_rows
    )
    baseline_actions = tuple(
        SolverExecutedAction(
            action_index=index,
            observation_index=row.observation.observation_index,
            proposal_index=None,
            action_kind="step_size",
            action_payload_hash=baseline_hashes[index],
            source="baseline",
            guard_receipt_hash=None,
        )
        for index, row in enumerate(normalized_rows)
    )
    episode = create_solver_episode_ir(
        episode_id=episode_id,
        model_ir_content_hash=model_ir_content_hash,
        execution_plan_hash=execution_plan_hash,
        initial_state_hash=initial_state_hash,
        analysis_profile=analysis_profile,
        backend_profile=backend_profile,
        backend_receipt_hash=backend_receipt_hash,
        episode_mode="shadow",
        observations=observations,
        proposals=proposals,
        executed_actions=baseline_actions,
        terminal=terminal,
        data_use=data_use,
    )
    if any(action.source == "ai_proposal" for action in episode.executed_actions):
        raise ShadowSolverControllerError(
            "shadow controller emitted an executed AI action"
        )
    return ShadowSolverControllerRun(
        episode=episode,
        decisions=decisions,
        baseline_action_payload_hashes=baseline_hashes,
    )


__all__ = [
    "SHADOW_CONTROLLER_PROFILE",
    "SHADOW_STEP_ACTION_UNIT",
    "DeterministicResidualStepPolicy",
    "ShadowSolverControllerError",
    "ShadowSolverControllerRun",
    "ShadowStepDecision",
    "ShadowStepInput",
    "ShadowStepPolicy",
    "build_shadow_step_solver_episode",
]
