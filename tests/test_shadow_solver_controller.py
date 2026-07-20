from __future__ import annotations

from dataclasses import dataclass

import pytest

from structural_analysis.ai.shadow_solver_controller import (
    SHADOW_STEP_ACTION_UNIT,
    DeterministicResidualStepPolicy,
    ShadowSolverControllerError,
    ShadowStepDecision,
    ShadowStepInput,
    build_shadow_step_solver_episode,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.solver_episode import (
    SolverEpisodeDataUse,
    SolverEpisodeError,
    SolverEpisodeObservation,
    SolverEpisodeTerminal,
)


def _hash(digit: str) -> str:
    return "sha256:" + digit * 64


def _action_hash(step_size: float, policy_hash: str) -> str:
    return canonical_hash(
        {
            "action_kind": "step_size",
            "step_size": float(step_size),
            "unit": SHADOW_STEP_ACTION_UNIT,
            "source_profile": policy_hash,
        }
    )


def _observation(
    index: int,
    *,
    residual: float,
    accepted: bool = False,
    rollback: bool = False,
) -> SolverEpisodeObservation:
    return SolverEpisodeObservation(
        observation_index=index,
        state_hash=_hash(str((index + 1) % 10)),
        iteration=index,
        restart_index=0,
        load_factor=0.1 * index,
        residual_linf=residual,
        scaled_residual_l2=0.5 * residual,
        increment_linf=0.01,
        runtime_ms=5.0,
        accepted=accepted,
        rollback=rollback,
    )


def _terminal_for(rows) -> SolverEpisodeTerminal:
    accepted = [row.observation for row in rows if row.observation.accepted]
    if accepted:
        return SolverEpisodeTerminal(
            reason="converged",
            converged=True,
            final_authority_status="numerical",
            final_state_hash=accepted[-1].state_hash,
            final_result_hash=_hash("8"),
            fallback_count=0,
            regularization_count=0,
            total_iterations=len(rows),
            total_runtime_ms=5.0 * len(rows),
        )
    return SolverEpisodeTerminal(
        reason="blocked",
        converged=False,
        final_authority_status="none",
        final_state_hash=None,
        final_result_hash=None,
        fallback_count=0,
        regularization_count=0,
        total_iterations=len(rows),
        total_runtime_ms=5.0 * len(rows),
    )


def _data_use() -> SolverEpisodeDataUse:
    return SolverEpisodeDataUse(
        training_eligible=False,
        evaluation_only=True,
        source_license_receipt_hash=None,
        privacy_receipt_hash=None,
    )


def _build(rows, *, policy=None):
    normalized = tuple(rows)
    return build_shadow_step_solver_episode(
        episode_id="episode.shadow-step",
        model_ir_content_hash=_hash("1"),
        execution_plan_hash=_hash("2"),
        initial_state_hash=_hash("3"),
        analysis_profile="nonlinear-static.truss2d",
        backend_profile="cpu-fgmres.reference",
        backend_receipt_hash=_hash("4"),
        rows=normalized,
        terminal=_terminal_for(normalized),
        data_use=_data_use(),
        policy=policy,
    )


def test_shadow_controller_records_proposals_but_executes_baseline_only() -> None:
    run = _build(
        (
            ShadowStepInput(
                observation=_observation(0, residual=10.0),
                current_step_size=0.04,
                baseline_next_step_size=0.04,
                previous_residual_linf=None,
            ),
            ShadowStepInput(
                observation=_observation(1, residual=1.0, accepted=True),
                current_step_size=0.04,
                baseline_next_step_size=0.05,
                previous_residual_linf=10.0,
            ),
        )
    )
    assert run.episode.episode_mode == "shadow"
    assert run.episode.terminal.final_state_hash == run.episode.observations[-1].state_hash
    assert [row.source for row in run.episode.executed_actions] == [
        "baseline",
        "baseline",
    ]
    assert [row.disposition for row in run.episode.proposals] == [
        "shadow_only",
        "shadow_only",
    ]
    assert run.decisions[0].reason_code == "insufficient_history_hold"
    assert run.decisions[1].reason_code == "strong_residual_reduction_grow"
    assert run.decisions[1].proposed_step_size == pytest.approx(0.05)
    assert run.to_dict()["ai_action_executed"] is False
    assert run.to_dict()["result_authority"] is False


def test_weak_reduction_shrinks_and_moderate_reduction_holds() -> None:
    policy = DeterministicResidualStepPolicy()
    weak = policy.propose(
        ShadowStepInput(
            observation=_observation(0, residual=9.5),
            current_step_size=0.08,
            baseline_next_step_size=0.08,
            previous_residual_linf=10.0,
        )
    )
    moderate = policy.propose(
        ShadowStepInput(
            observation=_observation(0, residual=5.0),
            current_step_size=0.08,
            baseline_next_step_size=0.08,
            previous_residual_linf=10.0,
        )
    )
    assert weak.reason_code == "weak_residual_reduction_shrink"
    assert weak.proposed_step_size == pytest.approx(0.04)
    assert moderate.reason_code == "moderate_residual_reduction_hold"
    assert moderate.proposed_step_size == pytest.approx(0.08)


def test_rollback_always_proposes_bounded_shrink() -> None:
    policy = DeterministicResidualStepPolicy(minimum_step_size=0.01)
    decision = policy.propose(
        ShadowStepInput(
            observation=_observation(0, residual=20.0, rollback=True),
            current_step_size=0.012,
            baseline_next_step_size=0.01,
            previous_residual_linf=10.0,
        )
    )
    assert decision.reason_code == "rollback_shrink"
    assert decision.proposed_step_size == pytest.approx(0.01)
    assert decision.ood is False
    assert decision.disposition == "shadow_only"


def test_unsupported_model_family_is_ood_rejected_and_baseline_only() -> None:
    run = _build(
        (
            ShadowStepInput(
                observation=_observation(0, residual=10.0),
                current_step_size=0.04,
                baseline_next_step_size=0.04,
                previous_residual_linf=20.0,
                supported_model_family=False,
            ),
        )
    )
    decision = run.decisions[0]
    proposal = run.episode.proposals[0]
    assert decision.reason_code == "ood_model_family"
    assert decision.ood is True
    assert decision.disposition == "rejected"
    assert proposal.ood is True
    assert proposal.disposition == "rejected"
    assert run.episode.executed_actions[0].source == "baseline"
    assert run.episode.terminal.final_state_hash is None


def test_episode_and_decision_hashes_are_deterministic() -> None:
    rows = (
        ShadowStepInput(
            observation=_observation(0, residual=10.0),
            current_step_size=0.04,
            baseline_next_step_size=0.04,
            previous_residual_linf=None,
        ),
        ShadowStepInput(
            observation=_observation(1, residual=2.0, accepted=True),
            current_step_size=0.04,
            baseline_next_step_size=0.05,
            previous_residual_linf=10.0,
        ),
    )
    first = _build(rows)
    second = _build(rows)
    assert first.episode.episode_hash == second.episode.episode_hash
    assert first.decisions == second.decisions
    assert first.baseline_action_payload_hashes == second.baseline_action_payload_hashes


@dataclass(frozen=True)
class _MaliciousEligibleShadowPolicy:
    minimum_step_size: float = 0.001
    maximum_step_size: float = 0.25
    policy_id: str = "malicious-policy"
    policy_version: str = "v1"

    @property
    def artifact_hash(self) -> str:
        return _hash("9")

    def propose(self, value: ShadowStepInput) -> ShadowStepDecision:
        proposed = value.current_step_size
        return ShadowStepDecision(
            observation_index=value.observation.observation_index,
            current_step_size=value.current_step_size,
            baseline_next_step_size=value.baseline_next_step_size,
            proposed_step_size=proposed,
            residual_ratio=None,
            reason_code="attempt_shadow_promotion",
            uncertainty=0.0,
            ood=False,
            disposition="eligible",
            action_payload_hash=_action_hash(proposed, self.artifact_hash),
            policy_artifact_hash=self.artifact_hash,
        )


def test_policy_cannot_mark_shadow_proposal_eligible() -> None:
    with pytest.raises(
        ShadowSolverControllerError,
        match="shadow decision disposition",
    ):
        _build(
            (
                ShadowStepInput(
                    observation=_observation(0, residual=10.0),
                    current_step_size=0.04,
                    baseline_next_step_size=0.04,
                    previous_residual_linf=None,
                ),
            ),
            policy=_MaliciousEligibleShadowPolicy(),
        )


@dataclass(frozen=True)
class _InconsistentDecisionPolicy:
    mode: str
    minimum_step_size: float = 0.001
    maximum_step_size: float = 0.25
    policy_id: str = "inconsistent-policy"
    policy_version: str = "v1"

    @property
    def artifact_hash(self) -> str:
        return _hash("5")

    def propose(self, value: ShadowStepInput) -> ShadowStepDecision:
        proposed = 0.04
        policy_hash = self.artifact_hash
        action_hash = _action_hash(proposed, policy_hash)
        if self.mode == "wrong_policy_hash":
            policy_hash = _hash("6")
        elif self.mode == "wrong_action_hash":
            action_hash = _hash("7")
        elif self.mode == "out_of_range":
            proposed = 0.5
            action_hash = _action_hash(proposed, policy_hash)
        return ShadowStepDecision(
            observation_index=value.observation.observation_index,
            current_step_size=value.current_step_size,
            baseline_next_step_size=value.baseline_next_step_size,
            proposed_step_size=proposed,
            residual_ratio=None,
            reason_code="malicious-identity-mismatch",
            uncertainty=0.0,
            ood=False,
            disposition="shadow_only",
            action_payload_hash=action_hash,
            policy_artifact_hash=policy_hash,
        )


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("wrong_policy_hash", "policy_artifact_hash"),
        ("wrong_action_hash", "action_payload_hash"),
        ("out_of_range", "outside the declared policy range"),
    ],
)
def test_third_party_policy_decision_identity_mismatch_fails_closed(
    mode: str,
    message: str,
) -> None:
    with pytest.raises(ShadowSolverControllerError, match=message):
        _build(
            (
                ShadowStepInput(
                    observation=_observation(0, residual=10.0),
                    current_step_size=0.04,
                    baseline_next_step_size=0.04,
                    previous_residual_linf=None,
                ),
            ),
            policy=_InconsistentDecisionPolicy(mode=mode),
        )


def test_invalid_policy_and_input_ranges_fail_closed() -> None:
    with pytest.raises(ShadowSolverControllerError, match="minimum_step_size"):
        DeterministicResidualStepPolicy(
            minimum_step_size=0.2,
            maximum_step_size=0.1,
        )
    with pytest.raises(ShadowSolverControllerError, match="grow_factor"):
        DeterministicResidualStepPolicy(grow_factor=1.0)
    with pytest.raises(ShadowSolverControllerError, match="shrink_factor"):
        DeterministicResidualStepPolicy(shrink_factor=1.0)
    with pytest.raises(ShadowSolverControllerError, match="current_step_size"):
        DeterministicResidualStepPolicy().propose(
            ShadowStepInput(
                observation=_observation(0, residual=1.0),
                current_step_size=0.5,
                baseline_next_step_size=0.04,
                previous_residual_linf=2.0,
            )
        )
    with pytest.raises(ShadowSolverControllerError, match="rows must be non-empty"):
        _build(())


def test_non_contiguous_observations_are_rejected_by_episode_contract() -> None:
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_observation_index_invalid",
    ):
        _build(
            (
                ShadowStepInput(
                    observation=_observation(1, residual=1.0),
                    current_step_size=0.04,
                    baseline_next_step_size=0.04,
                    previous_residual_linf=None,
                ),
            )
        )
