from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

import structural_analysis.ai as ai
from structural_analysis.ai.fiber_frame_solver_episode_adapter import (
    FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE,
    FIBER_FRAME_SOLVER_EPISODE_CLAIM_BOUNDARY,
    FiberFrameSolverEpisodeAdapterError,
    _adapter_payload,
    _observation_binding_payload,
    _transition_binding_payload,
    create_fiber_frame_solver_episode_adapter,
    validate_fiber_frame_solver_episode_adapter,
    validate_fiber_frame_solver_episode_adapter_manifest,
)
from structural_analysis.assembly import (
    make_stateful_fiber_frame2d_checkpoint_chain,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    create_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    create_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    create_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    create_fiber_frame_nonlinear_terminal_receipt,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.benchmark import make_two_member_stateful_fiber_l_frame
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


MODEL_HASH = "sha256:" + "1" * 64
LICENSE_HASH = "sha256:" + "7" * 64
PRIVACY_HASH = "sha256:" + "8" * 64
LOAD_FACTORS = (0.25, 0.5, 0.75, 1.0)
NODE_IDS = ("N1", "N2", "N3")
HASH_ZERO = "sha256:" + "0" * 64


def _state_sources(*, load_factors, config):
    problem = make_two_member_stateful_fiber_l_frame()
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        load_factors,
        config=config,
    )
    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps if step.committed),
    )
    checkpoint_chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        checkpoints,
    )
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=MODEL_HASH,
        node_ids=NODE_IDS,
    )
    scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
    )
    material = create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hashes=kinematic.solver_state_hashes,
    )
    binding = create_fiber_frame_nonlinear_execution_state_binding(
        problem,
        plan,
        scaling,
        checkpoint_chain,
        kinematic,
        material,
    )
    return (
        problem,
        path,
        checkpoint_chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
    )


@pytest.fixture(scope="module")
def ready_artifacts():
    sources = _state_sources(
        load_factors=LOAD_FACTORS,
        config=NewtonRaphsonConfig(max_iterations=40),
    )
    problem, path, chain, plan, scaling, kinematic, material, binding = sources
    receipt = create_fiber_frame_nonlinear_terminal_receipt(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
    )
    baseline = create_fiber_frame_solver_episode_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
        terminal_receipt=receipt,
        episode_mode="baseline",
    )
    shadow = create_fiber_frame_solver_episode_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
        terminal_receipt=receipt,
        episode_mode="shadow",
    )
    return (*sources, receipt, baseline, shadow)


@pytest.fixture(scope="module")
def blocked_artifacts():
    sources = _state_sources(
        load_factors=(1.0,),
        config=NewtonRaphsonConfig(max_iterations=1),
    )
    problem, path, chain, plan, scaling, kinematic, material, binding = sources
    baseline = create_fiber_frame_solver_episode_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
    )
    return (*sources, baseline)


def _rehash_adapter(adapter, *, observations=None, transitions=None):
    provisional = replace(
        adapter,
        adapter_hash=HASH_ZERO,
        observation_bindings=(
            adapter.observation_bindings if observations is None else observations
        ),
        transition_bindings=(
            adapter.transition_bindings if transitions is None else transitions
        ),
    )
    return replace(
        provisional,
        adapter_hash=canonical_hash(_adapter_payload(provisional, include_hash=False)),
    )


def test_ready_baseline_binds_each_j4_epoch_and_j5_receipt(ready_artifacts) -> None:
    *_, binding, receipt, baseline, _ = ready_artifacts

    assert baseline.authority_profile == FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE
    assert baseline.terminal_receipt_hash == receipt.terminal_receipt_hash
    assert baseline.execution_state_binding_hash == binding.binding_hash
    assert len(baseline.episode.observations) == 5
    assert len(baseline.episode.executed_actions) == 4
    assert baseline.episode.proposals == ()
    assert all(row.accepted for row in baseline.episode.observations)
    assert tuple(row.state_hash for row in baseline.episode.observations) == tuple(
        row.epoch_binding_hash for row in binding.epoch_bindings
    )
    assert baseline.episode.terminal.converged is True
    assert baseline.episode.terminal.final_authority_status == "none"
    assert baseline.episode.terminal.final_result_hash is None
    assert baseline.episode.terminal.final_state_hash == (
        binding.epoch_bindings[-1].epoch_binding_hash
    )


def test_shadow_proposals_replay_but_only_baseline_actions_execute(
    ready_artifacts,
) -> None:
    *_, shadow = ready_artifacts

    assert shadow.episode.episode_mode == "shadow"
    assert len(shadow.episode.proposals) == len(shadow.transition_bindings) == 4
    assert all(row.source == "baseline" for row in shadow.episode.executed_actions)
    assert all(
        row.disposition in {"shadow_only", "rejected"}
        for row in shadow.episode.proposals
    )
    for transition, proposal in zip(
        shadow.transition_bindings,
        shadow.episode.proposals,
        strict=True,
    ):
        assert transition.shadow_policy_artifact_hash == proposal.policy_artifact_hash
        assert transition.shadow_action_payload_hash == proposal.action_payload_hash
        assert transition.baseline_action_payload_hash != proposal.action_payload_hash


def test_repeated_creation_and_full_source_validation_are_identical(
    ready_artifacts,
) -> None:
    (
        problem,
        path,
        chain,
        plan,
        scaling,
        kinematic,
        material,
        binding,
        receipt,
        baseline,
        _,
    ) = ready_artifacts
    repeated = create_fiber_frame_solver_episode_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
        terminal_receipt=receipt,
    )

    assert repeated == baseline
    assert repeated.to_manifest() == baseline.to_manifest()
    assert (
        validate_fiber_frame_solver_episode_adapter(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
            baseline,
            terminal_receipt=receipt,
        )
        is baseline
    )


def test_manifest_is_strict_hash_only_and_rejects_authority_promotion(
    ready_artifacts,
) -> None:
    *_, baseline, _ = ready_artifacts
    manifest = baseline.to_manifest()

    assert validate_fiber_frame_solver_episode_adapter_manifest(manifest) == manifest
    assert manifest["claim_boundary"] == dict(FIBER_FRAME_SOLVER_EPISODE_CLAIM_BOUNDARY)
    assert all(
        value is False
        for key, value in manifest["data_boundary"].items()
        if key.endswith("_included")
    )
    rendered = repr(manifest)
    assert "global_displacements" not in rendered
    assert "constituent_states" not in rendered
    assert "raw_residual_source_3dof" not in rendered

    unknown = deepcopy(manifest)
    unknown["unexpected"] = True
    with pytest.raises(
        FiberFrameSolverEpisodeAdapterError,
        match="fiber_frame_episode_manifest_keys_invalid",
    ):
        validate_fiber_frame_solver_episode_adapter_manifest(unknown)

    promoted = deepcopy(manifest)
    promoted["episode"]["terminal"]["final_authority_status"] = "numerical"
    promoted["episode"]["terminal"]["final_result_hash"] = "sha256:" + "9" * 64
    promoted["episode"]["episode_hash"] = canonical_hash(
        {
            key: value
            for key, value in promoted["episode"].items()
            if key != "episode_hash"
        }
    )
    promoted["adapter_hash"] = canonical_hash(
        {key: value for key, value in promoted.items() if key != "adapter_hash"}
    )
    with pytest.raises(
        FiberFrameSolverEpisodeAdapterError,
        match="fiber_frame_episode_authority_promotion_forbidden",
    ):
        validate_fiber_frame_solver_episode_adapter_manifest(promoted)


def test_ready_path_cannot_omit_j5_receipt(ready_artifacts) -> None:
    problem, path, chain, plan, scaling, kinematic, material, binding, *_ = (
        ready_artifacts
    )
    with pytest.raises(
        FiberFrameSolverEpisodeAdapterError,
        match="fiber_frame_episode_terminal_receipt_required",
    ):
        create_fiber_frame_solver_episode_adapter(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
        )


def test_blocked_path_records_one_exact_rollback_without_state_mutation(
    blocked_artifacts,
) -> None:
    problem, path, chain, plan, scaling, kinematic, material, binding, adapter = (
        blocked_artifacts
    )
    parent = path.steps[-1].parent_checkpoint

    assert path.status == "blocked"
    assert path.steps[-1].accepted_checkpoint is parent
    assert path.steps[-1].accepted_checkpoint.canonical_bytes() == (
        parent.canonical_bytes()
    )
    assert adapter.rollback_count == 1
    assert [row.accepted for row in adapter.episode.observations] == [True, False]
    assert [row.rollback for row in adapter.episode.observations] == [False, True]
    assert adapter.episode.terminal.reason == "rolled_back"
    assert adapter.episode.terminal.final_state_hash == (
        adapter.episode.observations[0].state_hash
    )
    assert adapter.transition_bindings[0].parent_checkpoint_state_hash == (
        adapter.transition_bindings[0].outcome_checkpoint_state_hash
    )
    assert (
        validate_fiber_frame_solver_episode_adapter(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
            adapter,
        )
        is adapter
    )


def test_coherently_rehashed_source_step_tamper_fails_full_replay(
    blocked_artifacts,
) -> None:
    problem, path, chain, plan, scaling, kinematic, material, binding, adapter = (
        blocked_artifacts
    )
    fake_hash = "sha256:" + "9" * 64
    target = replace(
        adapter.observation_bindings[1],
        observation_binding_hash=HASH_ZERO,
        source_step_replay_hash=fake_hash,
    )
    target = replace(
        target,
        observation_binding_hash=canonical_hash(
            _observation_binding_payload(target, include_hash=False)
        ),
    )
    transition = replace(
        adapter.transition_bindings[0],
        transition_binding_hash=HASH_ZERO,
        source_step_replay_hash=fake_hash,
    )
    transition = replace(
        transition,
        transition_binding_hash=canonical_hash(
            _transition_binding_payload(transition, include_hash=False)
        ),
    )
    tampered = _rehash_adapter(
        adapter,
        observations=(adapter.observation_bindings[0], target),
        transitions=(transition,),
    )

    assert tampered.to_manifest()
    with pytest.raises(
        FiberFrameSolverEpisodeAdapterError,
        match="fiber_frame_episode_source_replay_mismatch",
    ):
        validate_fiber_frame_solver_episode_adapter(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
            tampered,
        )


def test_training_eligibility_requires_explicit_receipts(ready_artifacts) -> None:
    problem, path, chain, plan, scaling, kinematic, material, binding, receipt, *_ = (
        ready_artifacts
    )
    with pytest.raises(
        FiberFrameSolverEpisodeAdapterError,
        match="fiber_frame_episode_training_receipts_missing",
    ):
        create_fiber_frame_solver_episode_adapter(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
            terminal_receipt=receipt,
            training_eligible=True,
        )

    eligible = create_fiber_frame_solver_episode_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
        terminal_receipt=receipt,
        training_eligible=True,
        source_license_receipt_hash=LICENSE_HASH,
        privacy_receipt_hash=PRIVACY_HASH,
    )
    assert eligible.episode.data_use.training_eligible is True
    assert eligible.episode.data_use.evaluation_only is False
    assert eligible.episode.data_use.raw_customer_payload_included is False


def test_ai_namespace_exports_real_controller_and_adapter_symbols() -> None:
    assert ai.ShadowSolverControllerError.__name__ == "ShadowSolverControllerError"
    assert ai.build_shadow_step_solver_episode is not None
    assert ai.create_fiber_frame_solver_episode_adapter is (
        create_fiber_frame_solver_episode_adapter
    )
