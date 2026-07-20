from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.solver_episode import (
    SOLVER_EPISODE_AUTHORITY_PROFILE,
    SolverActionProposal,
    SolverEpisodeDataUse,
    SolverEpisodeError,
    SolverEpisodeObservation,
    SolverEpisodeTerminal,
    SolverExecutedAction,
    create_solver_episode_ir,
    validate_solver_episode_ir,
    validate_solver_episode_manifest,
)


def _hash(digit: str) -> str:
    return "sha256:" + digit * 64


def _observation(
    index: int = 0,
    *,
    accepted: bool = False,
    rollback: bool = False,
    state_hash: str | None = None,
) -> SolverEpisodeObservation:
    return SolverEpisodeObservation(
        observation_index=index,
        state_hash=state_hash or _hash(str((index + 1) % 10)),
        iteration=index,
        restart_index=0,
        load_factor=0.25 * index,
        residual_linf=1.0 / (index + 1),
        scaled_residual_l2=0.5 / (index + 1),
        increment_linf=0.1 / (index + 1),
        runtime_ms=2.5 * (index + 1),
        accepted=accepted,
        rollback=rollback,
    )


def _default_observations() -> tuple[SolverEpisodeObservation, ...]:
    return (_observation(0), _observation(1, accepted=True))


def _terminal(
    *,
    reason="converged",
    converged=True,
    authority="numerical",
    final_state_hash=_hash("2"),
    final_result_hash=_hash("8"),
) -> SolverEpisodeTerminal:
    return SolverEpisodeTerminal(
        reason=reason,
        converged=converged,
        final_authority_status=authority,
        final_state_hash=final_state_hash,
        final_result_hash=final_result_hash,
        fallback_count=0,
        regularization_count=0,
        total_iterations=3,
        total_runtime_ms=12.5,
    )


def _evaluation_only() -> SolverEpisodeDataUse:
    return SolverEpisodeDataUse(
        training_eligible=False,
        evaluation_only=True,
        source_license_receipt_hash=None,
        privacy_receipt_hash=None,
    )


def _create(
    *,
    mode="baseline",
    observations=None,
    proposals=(),
    actions=(),
    terminal=None,
    data_use=None,
):
    return create_solver_episode_ir(
        episode_id="episode.test",
        model_ir_content_hash=_hash("1"),
        execution_plan_hash=_hash("2"),
        initial_state_hash=_hash("3"),
        analysis_profile="nonlinear-static.truss2d",
        backend_profile="cpu-fgmres.reference",
        backend_receipt_hash=_hash("4"),
        episode_mode=mode,
        observations=_default_observations() if observations is None else observations,
        proposals=proposals,
        executed_actions=actions,
        terminal=_terminal() if terminal is None else terminal,
        data_use=_evaluation_only() if data_use is None else data_use,
    )


def _proposal(*, disposition="shadow_only", ood=False) -> SolverActionProposal:
    return SolverActionProposal(
        proposal_index=0,
        observation_index=0,
        policy_id="step-policy",
        policy_version="v1",
        policy_artifact_hash=_hash("5"),
        action_kind="step_size",
        action_payload_hash=_hash("6"),
        uncertainty=0.1,
        ood=ood,
        disposition=disposition,
    )


def test_baseline_episode_is_canonical_trace_bound_and_non_authoritative() -> None:
    action = SolverExecutedAction(
        action_index=0,
        observation_index=0,
        proposal_index=None,
        action_kind="step_size",
        action_payload_hash=_hash("5"),
        source="baseline",
        guard_receipt_hash=None,
    )
    episode = _create(actions=(action,))
    assert episode.authority_profile == SOLVER_EPISODE_AUTHORITY_PROFILE
    assert episode.episode_mode == "baseline"
    assert episode.terminal.final_state_hash == episode.observations[-1].state_hash
    manifest = episode.to_manifest()
    assert validate_solver_episode_manifest(manifest) == manifest
    assert "claims" not in manifest
    assert "result_authority" not in manifest


def test_shadow_episode_records_proposal_without_executing_it() -> None:
    baseline = SolverExecutedAction(
        action_index=0,
        observation_index=0,
        proposal_index=None,
        action_kind="step_size",
        action_payload_hash=_hash("7"),
        source="baseline",
        guard_receipt_hash=None,
    )
    episode = _create(
        mode="shadow",
        proposals=(_proposal(),),
        actions=(baseline,),
    )
    assert episode.proposals[0].disposition == "shadow_only"
    assert all(row.source != "ai_proposal" for row in episode.executed_actions)


def test_guarded_episode_can_execute_one_eligible_non_ood_proposal() -> None:
    proposal = replace(
        _proposal(disposition="eligible"),
        policy_id="restart-policy",
        policy_version="v2",
        action_kind="restart_length",
    )
    action = SolverExecutedAction(
        action_index=0,
        observation_index=0,
        proposal_index=0,
        action_kind="restart_length",
        action_payload_hash=proposal.action_payload_hash,
        source="ai_proposal",
        guard_receipt_hash=_hash("9"),
    )
    episode = _create(
        mode="guarded",
        proposals=(proposal,),
        actions=(action,),
    )
    assert episode.executed_actions[0].source == "ai_proposal"
    validate_solver_episode_ir(episode)


def test_baseline_shadow_and_ood_boundaries_fail_closed() -> None:
    eligible = _proposal(disposition="eligible")
    with pytest.raises(
        SolverEpisodeError,
        match="baseline_episode_proposals_forbidden",
    ):
        _create(mode="baseline", proposals=(eligible,))
    with pytest.raises(
        SolverEpisodeError,
        match="shadow_proposal_eligible_for_execution",
    ):
        _create(mode="shadow", proposals=(eligible,))
    with pytest.raises(
        SolverEpisodeError,
        match="ood_proposal_eligible_for_execution",
    ):
        _create(mode="guarded", proposals=(_proposal(disposition="eligible", ood=True),))


def test_guarded_ai_action_requires_matching_proposal_and_guard_receipt() -> None:
    proposal = _proposal(disposition="eligible")
    missing_guard = SolverExecutedAction(
        action_index=0,
        observation_index=0,
        proposal_index=0,
        action_kind="step_size",
        action_payload_hash=proposal.action_payload_hash,
        source="ai_proposal",
        guard_receipt_hash=None,
    )
    with pytest.raises(
        SolverEpisodeError,
        match="executed_ai_action_guard_missing",
    ):
        _create(
            mode="guarded",
            proposals=(proposal,),
            actions=(missing_guard,),
        )

    mismatched = replace(
        missing_guard,
        action_payload_hash=_hash("7"),
        guard_receipt_hash=_hash("9"),
    )
    with pytest.raises(
        SolverEpisodeError,
        match="executed_ai_action_proposal_mismatch",
    ):
        _create(
            mode="guarded",
            proposals=(proposal,),
            actions=(mismatched,),
        )


def test_indices_and_references_are_contiguous_and_in_range() -> None:
    bad_observation = replace(_observation(), observation_index=1)
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_observation_index_invalid",
    ):
        _create(
            observations=(bad_observation,),
            terminal=_terminal(authority="none", final_state_hash=None, final_result_hash=None),
        )

    bad_proposal = replace(_proposal(), observation_index=5)
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_reference_out_of_range",
    ):
        _create(mode="shadow", proposals=(bad_proposal,))


def test_terminal_authority_and_trace_references_fail_closed() -> None:
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_terminal_convergence_mismatch",
    ):
        _create(terminal=_terminal(reason="max_iterations", converged=True))
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_terminal_authority_binding_missing",
    ):
        _create(
            terminal=_terminal(
                authority="engineering",
                final_result_hash=None,
            )
        )
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_terminal_result_without_authority_reference",
    ):
        _create(
            terminal=_terminal(
                authority="none",
                final_result_hash=_hash("8"),
            )
        )
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_terminal_state_trace_mismatch",
    ):
        _create(terminal=_terminal(final_state_hash=_hash("7")))
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_terminal_state_without_accepted_observation",
    ):
        _create(
            observations=(_observation(0),),
            terminal=_terminal(final_state_hash=_hash("1")),
        )


def test_training_eligibility_requires_license_and_privacy_receipts() -> None:
    invalid = SolverEpisodeDataUse(
        training_eligible=True,
        evaluation_only=False,
        source_license_receipt_hash=None,
        privacy_receipt_hash=None,
    )
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_training_eligibility_invalid",
    ):
        _create(data_use=invalid)

    valid = SolverEpisodeDataUse(
        training_eligible=True,
        evaluation_only=False,
        source_license_receipt_hash=_hash("5"),
        privacy_receipt_hash=_hash("6"),
    )
    assert _create(data_use=valid).data_use.training_eligible is True

    raw_customer = replace(valid, raw_customer_payload_included=True)
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_raw_customer_payload_forbidden",
    ):
        _create(data_use=raw_customer)


def test_manifest_rejects_exact_type_semantic_trace_and_hash_tamper() -> None:
    manifest = _create(mode="shadow", proposals=(_proposal(),)).to_manifest()

    unknown = dict(manifest)
    unknown["autonomous_solver_authority"] = True
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_manifest_schema_invalid",
    ):
        validate_solver_episode_manifest(unknown)

    integral_float = deepcopy(manifest)
    integral_float["observations"][0]["observation_index"] = 0.0
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_manifest_schema_invalid",
    ):
        validate_solver_episode_manifest(integral_float)

    semantic = deepcopy(manifest)
    semantic["proposals"][0]["disposition"] = "eligible"
    with pytest.raises(
        SolverEpisodeError,
        match="shadow_proposal_eligible_for_execution",
    ):
        validate_solver_episode_manifest(semantic)

    unrelated = deepcopy(manifest)
    unrelated["terminal"]["final_state_hash"] = _hash("7")
    unsigned = dict(unrelated)
    unsigned.pop("episode_hash")
    unrelated["episode_hash"] = canonical_hash(unsigned)
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_terminal_state_trace_mismatch",
    ):
        validate_solver_episode_manifest(unrelated)

    hash_tamper = dict(manifest)
    hash_tamper["episode_hash"] = _hash("9")
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_hash_mismatch",
    ):
        validate_solver_episode_manifest(hash_tamper)


def test_episode_authority_profile_cannot_be_promoted() -> None:
    episode = _create()
    promoted = replace(
        episode,
        authority_profile="authoritative_autonomous_solver_episode",
    )
    with pytest.raises(
        SolverEpisodeError,
        match="solver_episode_authority_profile_invalid",
    ):
        validate_solver_episode_ir(promoted)
