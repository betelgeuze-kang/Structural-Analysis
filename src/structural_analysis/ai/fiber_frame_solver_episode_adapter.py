"""Replay-bound SolverEpisode adapter for the bounded stateful fiber frame.

The adapter projects an exact J4 execution-state chain and its source Newton
load path into baseline or shadow ``SolverEpisodeIR`` observations.  It keeps
only canonical identities and scalar diagnostics in the manifest.  Raw model,
displacement, residual-vector, and constituent-state bytes remain in the
caller-owned source artifacts.

This is an observation/control-plane contract.  Even when a separately
validated J5 receipt proves bounded convergence, the emitted episode retains
``final_authority_status=none`` and cannot mint a numerical result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from structural_analysis.ai.shadow_solver_controller import (
    SHADOW_STEP_ACTION_UNIT,
    DeterministicResidualStepPolicy,
    ShadowSolverControllerRun,
    ShadowStepDecision,
    ShadowStepInput,
    ShadowStepPolicy,
    build_shadow_step_solver_episode,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    assemble_stateful_fiber_frame2d,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION,
    StatefulFiberFrame2DCheckpointChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
    FiberFrameNonlinearExecutionTopologyPlan,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION,
    FiberFrameNonlinearKinematicStateChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION,
    FiberFrameMaterialStateProjectionChain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION,
    FiberFrameNonlinearExecutionStateBinding,
    validate_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION,
    FiberFrameNonlinearTerminalReceipt,
    validate_fiber_frame_nonlinear_terminal_receipt,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION,
    FiberFramePhysicalEquationScalingBinding,
    FiberFramePhysicalResidualTrace,
    trace_stateful_fiber_frame2d_physical_residual,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
    StatefulFiberFrame2DLoadStepResult,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.solver_episode import (
    SOLVER_EPISODE_SCHEMA_VERSION,
    SolverActionProposal,
    SolverEpisodeDataUse,
    SolverEpisodeIR,
    SolverEpisodeObservation,
    SolverEpisodeTerminal,
    SolverExecutedAction,
    create_solver_episode_ir,
    validate_solver_episode_ir,
    validate_solver_episode_manifest,
)
from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
)


FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-solver-episode-adapter.v1"
)
FIBER_FRAME_SOLVER_EPISODE_OBSERVATION_BINDING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-solver-episode-observation-binding.v1"
)
FIBER_FRAME_SOLVER_EPISODE_TRANSITION_BINDING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-solver-episode-transition-binding.v1"
)
FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE = (
    "non_authoritative_fiber_frame_solver_episode_adapter.v1"
)
FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE = (
    "stateful-fiber-frame2d.nonlinear-static.v1"
)
FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE = "stateful-fiber-frame2d.cpu-newton.v1"
FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE = (
    "source-runtime-not-captured.report-zero.v1"
)
FIBER_FRAME_BASELINE_STEP_POLICY_PROFILE = "deterministic-baseline-step-policy.v1"

FIBER_FRAME_SOLVER_EPISODE_CLAIM_BOUNDARY = MappingProxyType(
    {
        "exact_j4_execution_state_binding_replayed": True,
        "exact_checkpoint_topology_and_scaling_hashes_bound": True,
        "physical_residual_observations_replayed": True,
        "deterministic_source_load_path_replayed": True,
        "successful_path_requires_exact_j5_receipt": True,
        "exact_rollback_parent_immutability_bound": True,
        "deterministic_baseline_actions_bound": True,
        "shadow_policy_proposals_bound": True,
        "shadow_policy_action_executed": False,
        "raw_customer_payload_included": False,
        "raw_displacement_or_constituent_state_bytes_included": False,
        "solver_convergence_authority": False,
        "numerical_result_authority": False,
        "engineering_result_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)
FIBER_FRAME_SOLVER_EPISODE_DATA_BOUNDARY = MappingProxyType(
    {
        "raw_customer_payload_included": False,
        "raw_model_bytes_included": False,
        "raw_displacement_bytes_included": False,
        "raw_residual_vector_bytes_included": False,
        "raw_constituent_state_bytes_included": False,
        "manifest_storage_profile": "canonical_hashes_and_scalars_only.v1",
    }
)

_SOURCE_SCHEMA_VERSIONS = MappingProxyType(
    {
        "solver_episode": SOLVER_EPISODE_SCHEMA_VERSION,
        "checkpoint_chain": STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION,
        "execution_topology": FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
        "physical_equation_scaling": (
            FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION
        ),
        "kinematic_state_chain": (
            FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION
        ),
        "material_state_projection_chain": (
            FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION
        ),
        "execution_state_binding": (
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION
        ),
        "nonlinear_terminal_receipt": (
            FIBER_FRAME_NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION
        ),
    }
)

FiberFrameSolverEpisodeMode = Literal["baseline", "shadow"]
_MODES = {"baseline", "shadow"}
_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class FiberFrameSolverEpisodeAdapterError(ValueError):
    """Stable fail-closed error for the source-bound episode adapter."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameSolverEpisodeObservationBinding:
    schema_version: str
    observation_binding_hash: str
    observation_index: int
    source_step_index: int | None
    execution_state_epoch: int
    execution_state_epoch_binding_hash: str
    checkpoint_state_hash: str
    execution_topology_plan_hash: str
    execution_topology_hash: str
    solver_coordinate_scaling_hash: str
    physical_equation_scaling_binding_hash: str
    physical_residual_trace_hash: str
    source_step_replay_hash: str | None
    load_factor: float
    raw_translation_linf_n: float
    raw_rotation_linf_nm: float
    scaled_residual_l2: float
    scaled_residual_linf: float
    dimensionless_increment_linf: float
    cumulative_iteration_count: int
    accepted: bool
    rollback: bool
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        _validate_observation_binding(self)
        return _observation_binding_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameSolverEpisodeTransitionBinding:
    schema_version: str
    transition_binding_hash: str
    transition_index: int
    from_observation_index: int
    to_observation_index: int
    source_step_index: int
    source_step_replay_hash: str
    parent_checkpoint_state_hash: str
    outcome_checkpoint_state_hash: str
    target_load_factor: float
    baseline_step_size: float
    baseline_action_payload_hash: str
    committed: bool
    rollback_exact: bool
    shadow_proposal_index: int | None
    shadow_policy_id: str | None
    shadow_policy_version: str | None
    shadow_policy_artifact_hash: str | None
    shadow_action_payload_hash: str | None
    shadow_current_step_size: float | None
    shadow_baseline_next_step_size: float | None
    shadow_proposed_step_size: float | None
    shadow_residual_ratio: float | None
    shadow_reason_code: str | None
    shadow_uncertainty: float | None
    shadow_ood: bool | None
    shadow_disposition: str | None
    shadow_decision_hash: str | None
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        _validate_transition_binding(self)
        return _transition_binding_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameSolverEpisodeAdapter:
    schema_version: str
    adapter_hash: str
    authority_profile: str
    episode: SolverEpisodeIR
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_hash: str
    execution_state_binding_hash: str
    checkpoint_chain_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    solver_config_hash: str
    backend_receipt_hash: str
    source_load_path_replay_hash: str
    terminal_receipt_hash: str | None
    load_path_status: str
    accepted_step_count: int
    rollback_count: int
    runtime_profile: str
    observation_bindings: tuple[FiberFrameSolverEpisodeObservationBinding, ...]
    transition_bindings: tuple[FiberFrameSolverEpisodeTransitionBinding, ...]
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_solver_episode_adapter_shape(self)
        return _adapter_payload(self, include_hash=True)


@dataclass(frozen=True)
class _SourceReplay:
    config: NewtonRaphsonConfig
    solver_config_hash: str
    source_load_path_replay_hash: str
    accepted_step_count: int
    rollback_count: int


def create_fiber_frame_solver_episode_adapter(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    *,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt | None = None,
    episode_mode: FiberFrameSolverEpisodeMode = "baseline",
    policy: ShadowStepPolicy | None = None,
    training_eligible: bool = False,
    source_license_receipt_hash: str | None = None,
    privacy_receipt_hash: str | None = None,
) -> FiberFrameSolverEpisodeAdapter:
    """Create one replay-bound baseline or shadow fiber-frame episode."""

    mode = _mode(episode_mode, "/episode_mode")
    if mode == "baseline" and policy is not None:
        _fail(
            "fiber_frame_episode_baseline_policy_invalid",
            "/policy",
            "A baseline episode cannot accept a shadow policy.",
        )
    data_use = _data_use(
        training_eligible=training_eligible,
        source_license_receipt_hash=source_license_receipt_hash,
        privacy_receipt_hash=privacy_receipt_hash,
    )
    replay = _validate_and_replay_sources(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
        load_path,
        terminal_receipt,
    )
    adapter = _build_adapter(
        problem,
        topology_plan,
        physical_scaling,
        execution_state_binding,
        load_path,
        terminal_receipt,
        mode=mode,
        policy=policy,
        data_use=data_use,
        replay=replay,
    )
    return validate_fiber_frame_solver_episode_adapter_shape(adapter)


def validate_fiber_frame_solver_episode_adapter_shape(
    adapter: FiberFrameSolverEpisodeAdapter,
) -> FiberFrameSolverEpisodeAdapter:
    """Validate immutable adapter/episode linkage without replaying sources."""

    if type(adapter) is not FiberFrameSolverEpisodeAdapter:
        _fail(
            "fiber_frame_episode_adapter_type_invalid",
            "/",
            "Expected FiberFrameSolverEpisodeAdapter.",
        )
    if adapter.schema_version != FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION:
        _fail(
            "fiber_frame_episode_adapter_schema_invalid",
            "/schema_version",
            "Unsupported fiber-frame SolverEpisode adapter schema.",
        )
    if adapter.authority_profile != FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_episode_adapter_authority_invalid",
            "/authority_profile",
            "The adapter cannot acquire result authority.",
        )
    for path, value in (
        ("/adapter_hash", adapter.adapter_hash),
        ("/bindings/problem_contract_hash", adapter.problem_contract_hash),
        ("/bindings/model_ir_content_hash", adapter.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            adapter.execution_topology_plan_hash,
        ),
        (
            "/bindings/execution_state_binding_hash",
            adapter.execution_state_binding_hash,
        ),
        ("/bindings/checkpoint_chain_hash", adapter.checkpoint_chain_hash),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            adapter.physical_equation_scaling_binding_hash,
        ),
        (
            "/bindings/engine_equation_scaling_hash",
            adapter.engine_equation_scaling_hash,
        ),
        ("/bindings/solver_config_hash", adapter.solver_config_hash),
        ("/bindings/backend_receipt_hash", adapter.backend_receipt_hash),
        (
            "/bindings/source_load_path_replay_hash",
            adapter.source_load_path_replay_hash,
        ),
    ):
        _hash(value, path)
    if adapter.terminal_receipt_hash is not None:
        _hash(
            adapter.terminal_receipt_hash,
            "/bindings/terminal_receipt_hash",
        )
    if adapter.load_path_status not in {"ready", "blocked"}:
        _fail(
            "fiber_frame_episode_source_status_invalid",
            "/source/load_path_status",
            "Only ready and exact-rollback blocked paths are supported.",
        )
    accepted_count = _index(
        adapter.accepted_step_count,
        "/source/accepted_step_count",
    )
    rollback_count = _index(adapter.rollback_count, "/source/rollback_count")
    expected_rollback_count = 0 if adapter.load_path_status == "ready" else 1
    if rollback_count != expected_rollback_count:
        _fail(
            "fiber_frame_episode_rollback_count_invalid",
            "/source/rollback_count",
            "Ready paths have no rollback; blocked paths have exactly one.",
        )
    if (adapter.load_path_status == "ready") != (
        adapter.terminal_receipt_hash is not None
    ):
        _fail(
            "fiber_frame_episode_terminal_receipt_binding_invalid",
            "/bindings/terminal_receipt_hash",
            "Only a ready path must bind an exact J5 terminal receipt.",
        )
    if adapter.runtime_profile != FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE:
        _fail(
            "fiber_frame_episode_runtime_profile_invalid",
            "/profiles/runtime",
            "v1 records zero runtime because source timing is unavailable.",
        )
    if not isinstance(adapter.extensions, MappingProxyType) or adapter.extensions:
        _fail(
            "fiber_frame_episode_adapter_extensions_invalid",
            "/extensions",
            "Adapter v1 requires an immutable empty extensions object.",
        )

    episode = validate_solver_episode_ir(adapter.episode)
    if episode.episode_mode not in _MODES:
        _fail(
            "fiber_frame_episode_mode_invalid",
            "/episode/episode_mode",
            "Only baseline and shadow modes are supported.",
        )
    if (
        episode.model_ir_content_hash != adapter.model_ir_content_hash
        or episode.execution_plan_hash != adapter.execution_topology_plan_hash
        or episode.backend_receipt_hash != adapter.backend_receipt_hash
    ):
        _fail(
            "fiber_frame_episode_outer_binding_mismatch",
            "/episode/bindings",
            "Episode bindings differ from the adapter envelope.",
        )
    if (
        episode.analysis_profile != FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE
        or episode.backend_profile != FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE
    ):
        _fail(
            "fiber_frame_episode_profile_mismatch",
            "/episode",
            "Episode analysis/backend profile is stale.",
        )
    if (
        episode.terminal.final_authority_status != "none"
        or episode.terminal.final_result_hash is not None
        or any(row.source != "baseline" for row in episode.executed_actions)
    ):
        _fail(
            "fiber_frame_episode_authority_promotion_forbidden",
            "/episode",
            "The adapter permits baseline execution and no result authority only.",
        )
    if any(row.runtime_ms != 0.0 for row in episode.observations):
        _fail(
            "fiber_frame_episode_runtime_claim_invalid",
            "/episode/observations",
            "Source runtime was not captured; every runtime must be exact zero.",
        )

    if (
        type(adapter.observation_bindings) is not tuple
        or len(adapter.observation_bindings) != len(episode.observations)
        or len(adapter.observation_bindings) != accepted_count + rollback_count + 1
    ):
        _fail(
            "fiber_frame_episode_observation_set_invalid",
            "/observation_bindings",
            "Observation bindings must cover genesis, accepted steps, and rollback.",
        )
    for index, (binding, observation) in enumerate(
        zip(adapter.observation_bindings, episode.observations, strict=True)
    ):
        _validate_observation_binding(binding)
        _validate_observation_episode_link(binding, observation, index=index)
        if (
            binding.execution_topology_plan_hash != adapter.execution_topology_plan_hash
            or binding.physical_equation_scaling_binding_hash
            != adapter.physical_equation_scaling_binding_hash
        ):
            _fail(
                "fiber_frame_episode_observation_outer_binding_mismatch",
                f"/observation_bindings/{index}/bindings",
                "Observation topology/scaling differs from the outer envelope.",
            )

    actual_accepted_count = (
        sum(int(row.accepted) for row in adapter.observation_bindings) - 1
    )
    actual_rollback_count = sum(
        int(row.rollback) for row in adapter.observation_bindings
    )
    if (
        actual_accepted_count != accepted_count
        or actual_rollback_count != rollback_count
        or (rollback_count == 1 and not adapter.observation_bindings[-1].rollback)
    ):
        _fail(
            "fiber_frame_episode_observation_source_count_mismatch",
            "/observation_bindings",
            "Observation dispositions differ from source counts/status.",
        )

    if (
        type(adapter.transition_bindings) is not tuple
        or len(adapter.transition_bindings) != len(episode.executed_actions)
        or len(adapter.transition_bindings) != len(episode.observations) - 1
    ):
        _fail(
            "fiber_frame_episode_transition_set_invalid",
            "/transition_bindings",
            "Every source load step must bind one observation transition/action.",
        )
    for index, (binding, action) in enumerate(
        zip(adapter.transition_bindings, episode.executed_actions, strict=True)
    ):
        _validate_transition_binding(binding)
        _validate_transition_episode_link(
            binding,
            action,
            episode=episode,
            index=index,
        )
        target = adapter.observation_bindings[binding.to_observation_index]
        source = adapter.observation_bindings[binding.from_observation_index]
        if (
            binding.parent_checkpoint_state_hash != source.checkpoint_state_hash
            or binding.outcome_checkpoint_state_hash != target.checkpoint_state_hash
            or binding.source_step_replay_hash != target.source_step_replay_hash
            or binding.committed != target.accepted
            or binding.rollback_exact != target.rollback
            or binding.baseline_step_size != target.load_factor - source.load_factor
        ):
            _fail(
                "fiber_frame_episode_transition_outcome_mismatch",
                f"/transition_bindings/{index}",
                "Transition outcome differs from its target observation.",
            )
    expected_proposal_count = (
        len(adapter.transition_bindings) if episode.episode_mode == "shadow" else 0
    )
    if len(episode.proposals) != expected_proposal_count:
        _fail(
            "fiber_frame_episode_proposal_count_mismatch",
            "/episode/proposals",
            "Proposal count must equal shadow transitions or be zero in baseline.",
        )

    first = adapter.observation_bindings[0]
    last_accepted = tuple(row for row in adapter.observation_bindings if row.accepted)[
        -1
    ]
    if (
        episode.initial_state_hash != first.execution_state_epoch_binding_hash
        or episode.terminal.final_state_hash
        != last_accepted.execution_state_epoch_binding_hash
    ):
        _fail(
            "fiber_frame_episode_terminal_state_binding_mismatch",
            "/episode/terminal/final_state_hash",
            "Initial/final states must use the exact J4 execution-state hashes.",
        )
    expected_reason = (
        "converged" if adapter.load_path_status == "ready" else "rolled_back"
    )
    if (
        episode.terminal.converged != (adapter.load_path_status == "ready")
        or episode.terminal.reason != expected_reason
        or episode.terminal.total_iterations
        != adapter.observation_bindings[-1].cumulative_iteration_count
    ):
        _fail(
            "fiber_frame_episode_terminal_status_mismatch",
            "/episode/terminal",
            "Episode convergence flag differs from the replayed path status.",
        )
    expected_hash = canonical_hash(_adapter_payload(adapter, include_hash=False))
    if adapter.adapter_hash != expected_hash:
        _fail(
            "fiber_frame_episode_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash does not match canonical content.",
        )
    return adapter


def validate_fiber_frame_solver_episode_adapter(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    adapter: FiberFrameSolverEpisodeAdapter,
    *,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt | None = None,
    policy: ShadowStepPolicy | None = None,
) -> FiberFrameSolverEpisodeAdapter:
    """Replay all source artifacts and require an identical adapter manifest."""

    validate_fiber_frame_solver_episode_adapter_shape(adapter)
    replay = _validate_and_replay_sources(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
        load_path,
        terminal_receipt,
    )
    expected = _build_adapter(
        problem,
        topology_plan,
        physical_scaling,
        execution_state_binding,
        load_path,
        terminal_receipt,
        mode=_mode(adapter.episode.episode_mode, "/episode/episode_mode"),
        policy=policy,
        data_use=adapter.episode.data_use,
        replay=replay,
    )
    if adapter.to_manifest() != expected.to_manifest():
        _fail(
            "fiber_frame_episode_source_replay_mismatch",
            "/",
            "Adapter differs from the replayed J4/J5/Newton sources.",
        )
    return adapter


def _validate_and_replay_sources(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt | None,
) -> _SourceReplay:
    validate_fiber_frame_nonlinear_execution_state_binding(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        execution_state_binding,
    )
    if type(load_path) is not StatefulFiberFrame2DLoadPathResult:
        _fail(
            "fiber_frame_episode_source_path_type_invalid",
            "/load_path",
            "Expected exact StatefulFiberFrame2DLoadPathResult.",
        )
    if not load_path.steps:
        _fail(
            "fiber_frame_episode_source_path_empty",
            "/load_path/steps",
            "At least one source load step is required.",
        )
    if (
        load_path.initial_checkpoint.state_hash
        != execution_state_binding.root_checkpoint_state_hash
        or load_path.initial_checkpoint.state_hash
        != checkpoint_chain.root_checkpoint.state_hash
    ):
        _fail(
            "fiber_frame_episode_source_root_mismatch",
            "/load_path/initial_checkpoint",
            "Source genesis differs from the exact J4/checkpoint-chain root.",
        )

    first_solution = load_path.steps[0].trial_solution
    if (
        type(first_solution) is not NewtonRaphsonVectorSolution
        or type(first_solution.config) is not NewtonRaphsonConfig
    ):
        _fail(
            "fiber_frame_episode_source_solution_type_invalid",
            "/load_path/steps/0/trial_solution",
            "Expected an exact vector Newton solution and config.",
        )
    config = first_solution.config
    accepted_checkpoint = load_path.initial_checkpoint
    accepted_hashes = [accepted_checkpoint.state_hash]
    accepted_count = 0
    rollback_count = 0
    factors: list[float] = []

    for index, step in enumerate(load_path.steps):
        path = f"/load_path/steps/{index}"
        if (
            type(step) is not StatefulFiberFrame2DLoadStepResult
            or type(step.trial_solution) is not NewtonRaphsonVectorSolution
        ):
            _fail(
                "fiber_frame_episode_source_step_type_invalid",
                path,
                "Expected exact fiber-frame load-step result.",
            )
        if step.trial_solution.config != config:
            _fail(
                "fiber_frame_episode_source_config_changed",
                f"{path}/trial_solution/config",
                "Every source step must share one Newton config.",
            )
        target = step.metrics.get("target_load_factor")
        if type(target) is not float or not math.isfinite(target):
            _fail(
                "fiber_frame_episode_source_load_invalid",
                f"{path}/metrics/target_load_factor",
                "Target load factor must be a finite float.",
            )
        if target <= accepted_checkpoint.load_factor:
            _fail(
                "fiber_frame_episode_source_load_not_increasing",
                f"{path}/metrics/target_load_factor",
                "Each attempted target must exceed the accepted load factor.",
            )
        if step.parent_checkpoint.state_hash != accepted_checkpoint.state_hash:
            _fail(
                "fiber_frame_episode_source_parent_mismatch",
                f"{path}/parent_checkpoint",
                "Each step must descend from the preceding accepted checkpoint.",
            )
        factors.append(target)
        if step.committed:
            if rollback_count or step.status != "ready":
                _fail(
                    "fiber_frame_episode_source_commit_sequence_invalid",
                    path,
                    "Committed steps must precede the only optional rollback.",
                )
            accepted_count += 1
            accepted_checkpoint = step.accepted_checkpoint
            accepted_hashes.append(accepted_checkpoint.state_hash)
        else:
            rollback_count += 1
            parent_bytes = step.parent_checkpoint.canonical_bytes()
            rollback_exact = bool(
                index == len(load_path.steps) - 1
                and step.status == "blocked"
                and step.accepted_checkpoint is step.parent_checkpoint
                and step.accepted_checkpoint.state_hash
                == step.parent_checkpoint.state_hash
                and step.accepted_checkpoint.canonical_bytes() == parent_bytes
                and step.metrics.get("rollback_exact") is True
            )
            if rollback_count != 1 or not rollback_exact:
                _fail(
                    "fiber_frame_episode_source_rollback_not_exact",
                    path,
                    "Blocked paths require one terminal immutable exact rollback.",
                )

    if tuple(accepted_hashes) != tuple(
        checkpoint.state_hash for checkpoint in checkpoint_chain.checkpoints
    ):
        _fail(
            "fiber_frame_episode_source_checkpoint_chain_mismatch",
            "/load_path/steps",
            "Committed source outcomes differ from the exact J4 checkpoint chain.",
        )
    if execution_state_binding.epoch_count != accepted_count + 1:
        _fail(
            "fiber_frame_episode_source_epoch_count_mismatch",
            "/load_path/steps",
            "J4 epochs must equal genesis plus committed source steps.",
        )
    if load_path.final_checkpoint.state_hash != accepted_checkpoint.state_hash:
        _fail(
            "fiber_frame_episode_source_terminal_checkpoint_mismatch",
            "/load_path/final_checkpoint",
            "Load-path terminal checkpoint differs from the accepted ancestry.",
        )

    if load_path.status == "ready":
        if rollback_count or accepted_count != len(load_path.steps):
            _fail(
                "fiber_frame_episode_ready_path_invalid",
                "/load_path",
                "A ready path must commit every source step.",
            )
        if terminal_receipt is None:
            _fail(
                "fiber_frame_episode_terminal_receipt_required",
                "/terminal_receipt",
                "A ready episode requires an exact replay-validated J5 receipt.",
            )
        validate_fiber_frame_nonlinear_terminal_receipt(
            problem,
            topology_plan,
            physical_scaling,
            checkpoint_chain,
            kinematic_chain,
            material_chain,
            execution_state_binding,
            load_path,
            terminal_receipt,
        )
    elif load_path.status == "blocked":
        if rollback_count != 1 or accepted_count != len(load_path.steps) - 1:
            _fail(
                "fiber_frame_episode_blocked_path_invalid",
                "/load_path",
                "A blocked path must end in exactly one non-committed step.",
            )
        if terminal_receipt is not None:
            _fail(
                "fiber_frame_episode_blocked_receipt_forbidden",
                "/terminal_receipt",
                "A rolled-back path cannot bind a convergence receipt.",
            )
    else:
        _fail(
            "fiber_frame_episode_source_status_invalid",
            "/load_path/status",
            "Only ready and blocked source paths are supported.",
        )

    source_hash = canonical_hash(load_path.to_dict())
    replayed = run_stateful_fiber_frame2d_load_path(
        problem,
        tuple(factors),
        initial_checkpoint=load_path.initial_checkpoint,
        config=config,
    )
    if canonical_hash(replayed.to_dict()) != source_hash:
        _fail(
            "fiber_frame_episode_source_path_replay_mismatch",
            "/load_path",
            "Deterministic Newton replay differs from the supplied path.",
        )
    return _SourceReplay(
        config=config,
        solver_config_hash=canonical_hash(_config_payload(config)),
        source_load_path_replay_hash=source_hash,
        accepted_step_count=accepted_count,
        rollback_count=rollback_count,
    )


def _build_adapter(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
    terminal_receipt: FiberFrameNonlinearTerminalReceipt | None,
    *,
    mode: FiberFrameSolverEpisodeMode,
    policy: ShadowStepPolicy | None,
    data_use: SolverEpisodeDataUse,
    replay: _SourceReplay,
) -> FiberFrameSolverEpisodeAdapter:
    observations, observation_bindings = _build_observations(
        problem,
        topology_plan,
        physical_scaling,
        execution_state_binding,
        load_path,
    )
    step_sizes = tuple(
        float(step.metrics["target_load_factor"] - step.parent_checkpoint.load_factor)
        for step in load_path.steps
    )
    baseline_hashes = tuple(_baseline_action_hash(value) for value in step_sizes)
    decisions: tuple[ShadowStepDecision, ...] = ()
    proposals: tuple[SolverActionProposal, ...] = ()
    if mode == "shadow":
        shadow_run = _build_shadow_transitions(
            observations,
            step_sizes,
            model_ir_content_hash=topology_plan.model_ir_content_hash,
            execution_plan_hash=topology_plan.plan_hash,
            backend_receipt_hash=_backend_receipt_hash(
                topology_plan,
                physical_scaling,
                replay.solver_config_hash,
            ),
            data_use=data_use,
            policy=policy,
        )
        decisions = shadow_run.decisions
        proposals = shadow_run.episode.proposals
        if shadow_run.baseline_action_payload_hashes != baseline_hashes:
            _fail(
                "fiber_frame_episode_baseline_action_replay_mismatch",
                "/episode/executed_actions",
                "Shadow controller baseline hashes differ from source transitions.",
            )

    actions = tuple(
        SolverExecutedAction(
            action_index=index,
            observation_index=index,
            proposal_index=None,
            action_kind="step_size",
            action_payload_hash=baseline_hashes[index],
            source="baseline",
            guard_receipt_hash=None,
        )
        for index in range(len(step_sizes))
    )
    terminal = _episode_terminal(load_path, observation_bindings)
    backend_receipt_hash = _backend_receipt_hash(
        topology_plan,
        physical_scaling,
        replay.solver_config_hash,
    )
    policy_artifact_hash = proposals[0].policy_artifact_hash if proposals else None
    episode_id_suffix = canonical_hash(
        {
            "source_load_path_replay_hash": replay.source_load_path_replay_hash,
            "episode_mode": mode,
            "policy_artifact_hash": policy_artifact_hash,
        }
    ).removeprefix("sha256:")[:16]
    episode = create_solver_episode_ir(
        episode_id=f"fiber-frame.episode.{mode}.{episode_id_suffix}",
        model_ir_content_hash=topology_plan.model_ir_content_hash,
        execution_plan_hash=topology_plan.plan_hash,
        initial_state_hash=observation_bindings[0].execution_state_epoch_binding_hash,
        analysis_profile=FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE,
        backend_profile=FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE,
        backend_receipt_hash=backend_receipt_hash,
        episode_mode=mode,
        observations=observations,
        proposals=proposals,
        executed_actions=actions,
        terminal=terminal,
        data_use=data_use,
    )
    transitions = _build_transition_bindings(
        load_path,
        baseline_hashes,
        decisions,
        proposals,
    )
    provisional = FiberFrameSolverEpisodeAdapter(
        schema_version=FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION,
        adapter_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE,
        episode=episode,
        problem_contract_hash=problem.contract_hash,
        model_ir_content_hash=topology_plan.model_ir_content_hash,
        execution_topology_plan_hash=topology_plan.plan_hash,
        execution_state_binding_hash=execution_state_binding.binding_hash,
        checkpoint_chain_hash=execution_state_binding.checkpoint_chain_hash,
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        engine_equation_scaling_hash=physical_scaling.engine_equation_scaling_hash,
        solver_config_hash=replay.solver_config_hash,
        backend_receipt_hash=backend_receipt_hash,
        source_load_path_replay_hash=replay.source_load_path_replay_hash,
        terminal_receipt_hash=(
            terminal_receipt.terminal_receipt_hash
            if terminal_receipt is not None
            else None
        ),
        load_path_status=load_path.status,
        accepted_step_count=replay.accepted_step_count,
        rollback_count=replay.rollback_count,
        runtime_profile=FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE,
        observation_bindings=observation_bindings,
        transition_bindings=transitions,
        extensions=MappingProxyType({}),
    )
    adapter = replace(
        provisional,
        adapter_hash=canonical_hash(_adapter_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_solver_episode_adapter_shape(adapter)


def _build_observations(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    execution_state_binding: FiberFrameNonlinearExecutionStateBinding,
    load_path: StatefulFiberFrame2DLoadPathResult,
) -> tuple[
    tuple[SolverEpisodeObservation, ...],
    tuple[FiberFrameSolverEpisodeObservationBinding, ...],
]:
    root = load_path.initial_checkpoint
    scale = np.asarray(problem.physical_coordinate_scale, dtype=np.float64)
    generalized = np.asarray(root.global_displacements, dtype=np.float64) / scale
    initial_assembly = assemble_stateful_fiber_frame2d(
        problem,
        root,
        target_load_factor=root.load_factor,
        trial_free_coordinates_m=generalized[list(problem.free_global_dofs)],
    )
    trace = _trace_assembly_residual(
        topology_plan,
        physical_scaling,
        initial_assembly.internal_loads_global,
        initial_assembly.external_loads_global,
    )
    first_epoch = execution_state_binding.epoch_bindings[0]
    observations: list[SolverEpisodeObservation] = []
    bindings: list[FiberFrameSolverEpisodeObservationBinding] = []
    first_observation, first_binding = _make_observation(
        index=0,
        source_step_index=None,
        epoch_binding=first_epoch,
        checkpoint_state_hash=root.state_hash,
        topology_plan=topology_plan,
        physical_scaling=physical_scaling,
        trace=trace,
        source_step_replay_hash=None,
        load_factor=root.load_factor,
        increment_linf_m=0.0,
        cumulative_iteration_count=0,
        accepted=True,
        rollback=False,
    )
    observations.append(first_observation)
    bindings.append(first_binding)

    epoch_index = 0
    cumulative_iterations = 0
    for source_index, step in enumerate(load_path.steps, start=1):
        cumulative_iterations += len(step.trial_solution.convergence_history)
        if step.committed:
            epoch_index += 1
        epoch_binding = execution_state_binding.epoch_bindings[epoch_index]
        step_trace = _trace_assembly_residual(
            topology_plan,
            physical_scaling,
            step.trial_assembly.internal_loads_global,
            step.trial_assembly.external_loads_global,
        )
        observation, binding = _make_observation(
            index=source_index,
            source_step_index=source_index,
            epoch_binding=epoch_binding,
            checkpoint_state_hash=step.accepted_checkpoint.state_hash,
            topology_plan=topology_plan,
            physical_scaling=physical_scaling,
            trace=step_trace,
            source_step_replay_hash=canonical_hash(step.to_dict()),
            load_factor=float(step.metrics["target_load_factor"]),
            increment_linf_m=_final_increment_linf_m(step.trial_solution),
            cumulative_iteration_count=cumulative_iterations,
            accepted=step.committed,
            rollback=not step.committed,
        )
        observations.append(observation)
        bindings.append(binding)
    return tuple(observations), tuple(bindings)


def _make_observation(
    *,
    index: int,
    source_step_index: int | None,
    epoch_binding: Any,
    checkpoint_state_hash: str,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    trace: FiberFramePhysicalResidualTrace,
    source_step_replay_hash: str | None,
    load_factor: float,
    increment_linf_m: float,
    cumulative_iteration_count: int,
    accepted: bool,
    rollback: bool,
) -> tuple[SolverEpisodeObservation, FiberFrameSolverEpisodeObservationBinding]:
    dimensionless_increment = (
        increment_linf_m / physical_scaling.characteristic_length_m
    )
    observation = SolverEpisodeObservation(
        observation_index=index,
        state_hash=epoch_binding.epoch_binding_hash,
        iteration=cumulative_iteration_count,
        restart_index=0,
        load_factor=load_factor,
        residual_linf=trace.scaled_linf,
        scaled_residual_l2=trace.scaled_l2,
        increment_linf=dimensionless_increment,
        runtime_ms=0.0,
        accepted=accepted,
        rollback=rollback,
    )
    provisional = FiberFrameSolverEpisodeObservationBinding(
        schema_version=(FIBER_FRAME_SOLVER_EPISODE_OBSERVATION_BINDING_SCHEMA_VERSION),
        observation_binding_hash=_HASH_ZERO,
        observation_index=index,
        source_step_index=source_step_index,
        execution_state_epoch=epoch_binding.epoch,
        execution_state_epoch_binding_hash=epoch_binding.epoch_binding_hash,
        checkpoint_state_hash=checkpoint_state_hash,
        execution_topology_plan_hash=topology_plan.plan_hash,
        execution_topology_hash=topology_plan.topology_hash,
        solver_coordinate_scaling_hash=topology_plan.solver_coordinate_scaling_hash,
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        physical_residual_trace_hash=trace.trace_hash,
        source_step_replay_hash=source_step_replay_hash,
        load_factor=load_factor,
        raw_translation_linf_n=trace.raw_translation_linf_n,
        raw_rotation_linf_nm=trace.raw_rotation_linf_nm,
        scaled_residual_l2=trace.scaled_l2,
        scaled_residual_linf=trace.scaled_linf,
        dimensionless_increment_linf=dimensionless_increment,
        cumulative_iteration_count=cumulative_iteration_count,
        accepted=accepted,
        rollback=rollback,
        extensions=MappingProxyType({}),
    )
    binding = replace(
        provisional,
        observation_binding_hash=canonical_hash(
            _observation_binding_payload(provisional, include_hash=False)
        ),
    )
    return observation, _validate_observation_binding(binding)


def _trace_assembly_residual(
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    internal_loads_global: np.ndarray,
    external_loads_global: np.ndarray,
) -> FiberFramePhysicalResidualTrace:
    return trace_stateful_fiber_frame2d_physical_residual(
        topology_plan=topology_plan,
        scaling_binding=physical_scaling,
        raw_residual_source_3dof=np.asarray(internal_loads_global)
        - np.asarray(external_loads_global),
    )


def _build_shadow_transitions(
    observations: tuple[SolverEpisodeObservation, ...],
    step_sizes: tuple[float, ...],
    *,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    backend_receipt_hash: str,
    data_use: SolverEpisodeDataUse,
    policy: ShadowStepPolicy | None,
) -> ShadowSolverControllerRun:
    selected_policy = policy or DeterministicResidualStepPolicy(
        minimum_step_size=min(1.0e-12, min(step_sizes)),
        maximum_step_size=max(1.0, max(step_sizes)),
    )
    action_observations = observations[:-1]
    rows = tuple(
        ShadowStepInput(
            observation=observation,
            current_step_size=(step_sizes[index - 1] if index else step_sizes[0]),
            baseline_next_step_size=step_sizes[index],
            previous_residual_linf=(
                observations[index - 1].residual_linf if index else None
            ),
        )
        for index, observation in enumerate(action_observations)
    )
    temporary_terminal = SolverEpisodeTerminal(
        reason="blocked",
        converged=False,
        final_authority_status="none",
        final_state_hash=action_observations[-1].state_hash,
        final_result_hash=None,
        fallback_count=0,
        regularization_count=0,
        total_iterations=action_observations[-1].iteration,
        total_runtime_ms=0.0,
    )
    return build_shadow_step_solver_episode(
        episode_id="fiber-frame.episode.shadow-transition-validation",
        model_ir_content_hash=model_ir_content_hash,
        execution_plan_hash=execution_plan_hash,
        initial_state_hash=observations[0].state_hash,
        analysis_profile=FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE,
        backend_profile=FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE,
        backend_receipt_hash=backend_receipt_hash,
        rows=rows,
        terminal=temporary_terminal,
        data_use=data_use,
        policy=selected_policy,
    )


def _build_transition_bindings(
    load_path: StatefulFiberFrame2DLoadPathResult,
    baseline_hashes: tuple[str, ...],
    decisions: tuple[ShadowStepDecision, ...],
    proposals: tuple[SolverActionProposal, ...],
) -> tuple[FiberFrameSolverEpisodeTransitionBinding, ...]:
    rows: list[FiberFrameSolverEpisodeTransitionBinding] = []
    for index, step in enumerate(load_path.steps):
        decision = decisions[index] if decisions else None
        proposal = proposals[index] if proposals else None
        provisional = FiberFrameSolverEpisodeTransitionBinding(
            schema_version=(
                FIBER_FRAME_SOLVER_EPISODE_TRANSITION_BINDING_SCHEMA_VERSION
            ),
            transition_binding_hash=_HASH_ZERO,
            transition_index=index,
            from_observation_index=index,
            to_observation_index=index + 1,
            source_step_index=index + 1,
            source_step_replay_hash=canonical_hash(step.to_dict()),
            parent_checkpoint_state_hash=step.parent_checkpoint.state_hash,
            outcome_checkpoint_state_hash=step.accepted_checkpoint.state_hash,
            target_load_factor=float(step.metrics["target_load_factor"]),
            baseline_step_size=float(
                step.metrics["target_load_factor"] - step.parent_checkpoint.load_factor
            ),
            baseline_action_payload_hash=baseline_hashes[index],
            committed=step.committed,
            rollback_exact=not step.committed,
            shadow_proposal_index=index if decision is not None else None,
            shadow_policy_id=proposal.policy_id if proposal is not None else None,
            shadow_policy_version=(
                proposal.policy_version if proposal is not None else None
            ),
            shadow_policy_artifact_hash=(
                decision.policy_artifact_hash if decision is not None else None
            ),
            shadow_action_payload_hash=(
                decision.action_payload_hash if decision is not None else None
            ),
            shadow_current_step_size=(
                decision.current_step_size if decision is not None else None
            ),
            shadow_baseline_next_step_size=(
                decision.baseline_next_step_size if decision is not None else None
            ),
            shadow_proposed_step_size=(
                decision.proposed_step_size if decision is not None else None
            ),
            shadow_residual_ratio=(
                decision.residual_ratio if decision is not None else None
            ),
            shadow_reason_code=(decision.reason_code if decision is not None else None),
            shadow_uncertainty=(decision.uncertainty if decision is not None else None),
            shadow_ood=decision.ood if decision is not None else None,
            shadow_disposition=(decision.disposition if decision is not None else None),
            shadow_decision_hash=(
                canonical_hash(decision.to_dict()) if decision is not None else None
            ),
            extensions=MappingProxyType({}),
        )
        rows.append(
            replace(
                provisional,
                transition_binding_hash=canonical_hash(
                    _transition_binding_payload(provisional, include_hash=False)
                ),
            )
        )
    return tuple(rows)


def _episode_terminal(
    load_path: StatefulFiberFrame2DLoadPathResult,
    bindings: tuple[FiberFrameSolverEpisodeObservationBinding, ...],
) -> SolverEpisodeTerminal:
    return SolverEpisodeTerminal(
        reason="converged" if load_path.status == "ready" else "rolled_back",
        converged=load_path.status == "ready",
        final_authority_status="none",
        final_state_hash=tuple(row for row in bindings if row.accepted)[
            -1
        ].execution_state_epoch_binding_hash,
        final_result_hash=None,
        fallback_count=sum(
            int(bool(step.trial_solution.metrics.get("fallback_used")))
            for step in load_path.steps
        ),
        regularization_count=sum(
            int(bool(step.trial_solution.metrics.get("regularization_used")))
            for step in load_path.steps
        ),
        total_iterations=sum(
            len(step.trial_solution.convergence_history) for step in load_path.steps
        ),
        total_runtime_ms=0.0,
    )


def _validate_observation_binding(
    binding: FiberFrameSolverEpisodeObservationBinding,
) -> FiberFrameSolverEpisodeObservationBinding:
    if type(binding) is not FiberFrameSolverEpisodeObservationBinding:
        _fail(
            "fiber_frame_episode_observation_binding_type_invalid",
            "/",
            "Expected FiberFrameSolverEpisodeObservationBinding.",
        )
    if (
        binding.schema_version
        != FIBER_FRAME_SOLVER_EPISODE_OBSERVATION_BINDING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_episode_observation_binding_schema_invalid",
            "/schema_version",
            "Unsupported observation-binding schema.",
        )
    for path, value in (
        ("/observation_binding_hash", binding.observation_binding_hash),
        (
            "/bindings/execution_state_epoch_binding_hash",
            binding.execution_state_epoch_binding_hash,
        ),
        ("/bindings/checkpoint_state_hash", binding.checkpoint_state_hash),
        (
            "/bindings/execution_topology_plan_hash",
            binding.execution_topology_plan_hash,
        ),
        (
            "/bindings/execution_topology_hash",
            binding.execution_topology_hash,
        ),
        (
            "/bindings/solver_coordinate_scaling_hash",
            binding.solver_coordinate_scaling_hash,
        ),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            binding.physical_equation_scaling_binding_hash,
        ),
        (
            "/bindings/physical_residual_trace_hash",
            binding.physical_residual_trace_hash,
        ),
    ):
        _hash(value, path)
    observation_index = _index(binding.observation_index, "/observation_index")
    source_index = binding.source_step_index
    if source_index is None:
        if observation_index != 0:
            _fail(
                "fiber_frame_episode_observation_source_index_invalid",
                "/source_step_index",
                "Only the genesis observation has no source step.",
            )
    elif _index(source_index, "/source_step_index") != observation_index:
        _fail(
            "fiber_frame_episode_observation_source_index_invalid",
            "/source_step_index",
            "Source step and non-genesis observation indices must match.",
        )
    accepted = _boolean(binding.accepted, "/disposition/accepted")
    rollback = _boolean(binding.rollback, "/disposition/rollback")
    epoch = _index(binding.execution_state_epoch, "/execution_state_epoch")
    if epoch != observation_index - int(rollback):
        _fail(
            "fiber_frame_episode_observation_epoch_invalid",
            "/execution_state_epoch",
            "Committed observations advance J4; rollback retains the parent epoch.",
        )
    if source_index is None:
        if binding.source_step_replay_hash is not None:
            _fail(
                "fiber_frame_episode_genesis_source_hash_invalid",
                "/bindings/source_step_replay_hash",
                "Genesis cannot claim a source-step replay hash.",
            )
    else:
        _hash(
            binding.source_step_replay_hash,
            "/bindings/source_step_replay_hash",
        )
    _finite(binding.load_factor, "/observation/load_factor")
    for name in (
        "raw_translation_linf_n",
        "raw_rotation_linf_nm",
        "scaled_residual_l2",
        "scaled_residual_linf",
        "dimensionless_increment_linf",
    ):
        _nonnegative(getattr(binding, name), f"/observation/{name}")
    _index(
        binding.cumulative_iteration_count,
        "/observation/cumulative_iteration_count",
    )
    if accepted == rollback:
        _fail(
            "fiber_frame_episode_observation_disposition_invalid",
            "/disposition",
            "Every adapter observation is either accepted or an exact rollback.",
        )
    if not isinstance(binding.extensions, MappingProxyType) or binding.extensions:
        _fail(
            "fiber_frame_episode_observation_extensions_invalid",
            "/extensions",
            "Observation binding v1 requires empty immutable extensions.",
        )
    expected_hash = canonical_hash(
        _observation_binding_payload(binding, include_hash=False)
    )
    if binding.observation_binding_hash != expected_hash:
        _fail(
            "fiber_frame_episode_observation_hash_mismatch",
            "/observation_binding_hash",
            "Observation-binding hash does not match canonical content.",
        )
    return binding


def _validate_observation_episode_link(
    binding: FiberFrameSolverEpisodeObservationBinding,
    observation: SolverEpisodeObservation,
    *,
    index: int,
) -> None:
    expected = (
        index,
        binding.execution_state_epoch_binding_hash,
        binding.cumulative_iteration_count,
        binding.load_factor,
        binding.scaled_residual_linf,
        binding.scaled_residual_l2,
        binding.dimensionless_increment_linf,
        binding.accepted,
        binding.rollback,
    )
    actual = (
        observation.observation_index,
        observation.state_hash,
        observation.iteration,
        observation.load_factor,
        observation.residual_linf,
        observation.scaled_residual_l2,
        observation.increment_linf,
        observation.accepted,
        observation.rollback,
    )
    if actual != expected or observation.restart_index != 0:
        _fail(
            "fiber_frame_episode_observation_link_mismatch",
            f"/observation_bindings/{index}",
            "Episode observation differs from its source-binding scalars/hash.",
        )


def _validate_transition_binding(
    binding: FiberFrameSolverEpisodeTransitionBinding,
) -> FiberFrameSolverEpisodeTransitionBinding:
    if type(binding) is not FiberFrameSolverEpisodeTransitionBinding:
        _fail(
            "fiber_frame_episode_transition_binding_type_invalid",
            "/",
            "Expected FiberFrameSolverEpisodeTransitionBinding.",
        )
    if (
        binding.schema_version
        != FIBER_FRAME_SOLVER_EPISODE_TRANSITION_BINDING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_episode_transition_binding_schema_invalid",
            "/schema_version",
            "Unsupported transition-binding schema.",
        )
    transition_index = _index(binding.transition_index, "/transition_index")
    from_index = _index(
        binding.from_observation_index,
        "/from_observation_index",
    )
    to_index = _index(binding.to_observation_index, "/to_observation_index")
    source_index = _index(binding.source_step_index, "/source_step_index")
    if (
        from_index != transition_index
        or to_index != transition_index + 1
        or source_index != transition_index + 1
    ):
        _fail(
            "fiber_frame_episode_transition_index_invalid",
            "/",
            "Transition, observation, and source-step indices must be contiguous.",
        )
    for path, value in (
        ("/transition_binding_hash", binding.transition_binding_hash),
        ("/bindings/source_step_replay_hash", binding.source_step_replay_hash),
        (
            "/bindings/parent_checkpoint_state_hash",
            binding.parent_checkpoint_state_hash,
        ),
        (
            "/bindings/outcome_checkpoint_state_hash",
            binding.outcome_checkpoint_state_hash,
        ),
        (
            "/baseline/action_payload_hash",
            binding.baseline_action_payload_hash,
        ),
    ):
        _hash(value, path)
    _finite(binding.target_load_factor, "/target_load_factor")
    step_size = _positive(binding.baseline_step_size, "/baseline/step_size")
    if binding.baseline_action_payload_hash != _baseline_action_hash(step_size):
        _fail(
            "fiber_frame_episode_baseline_action_hash_mismatch",
            "/baseline/action_payload_hash",
            "Baseline action hash does not match the exact source step size.",
        )
    committed = _boolean(binding.committed, "/outcome/committed")
    rollback = _boolean(binding.rollback_exact, "/outcome/rollback_exact")
    if committed == rollback:
        _fail(
            "fiber_frame_episode_transition_disposition_invalid",
            "/outcome",
            "Transition must commit or roll back exactly, but not both.",
        )
    if rollback and (
        binding.parent_checkpoint_state_hash != binding.outcome_checkpoint_state_hash
    ):
        _fail(
            "fiber_frame_episode_transition_rollback_state_mismatch",
            "/bindings/outcome_checkpoint_state_hash",
            "Exact rollback must preserve the parent checkpoint hash.",
        )

    shadow_values = (
        binding.shadow_policy_id,
        binding.shadow_policy_version,
        binding.shadow_policy_artifact_hash,
        binding.shadow_action_payload_hash,
        binding.shadow_current_step_size,
        binding.shadow_baseline_next_step_size,
        binding.shadow_proposed_step_size,
        binding.shadow_reason_code,
        binding.shadow_uncertainty,
        binding.shadow_ood,
        binding.shadow_disposition,
        binding.shadow_decision_hash,
    )
    if binding.shadow_proposal_index is None:
        if any(value is not None for value in shadow_values) or (
            binding.shadow_residual_ratio is not None
        ):
            _fail(
                "fiber_frame_episode_baseline_shadow_fields_invalid",
                "/shadow",
                "Baseline transitions cannot contain shadow fields.",
            )
    else:
        if binding.shadow_proposal_index != transition_index or any(
            value is None for value in shadow_values
        ):
            _fail(
                "fiber_frame_episode_shadow_fields_incomplete",
                "/shadow",
                "Shadow transition fields must be complete and contiguous.",
            )
        _nonempty(binding.shadow_policy_id, "/shadow/policy_id")
        _nonempty(binding.shadow_policy_version, "/shadow/policy_version")
        _hash(binding.shadow_policy_artifact_hash, "/shadow/policy_artifact_hash")
        _hash(binding.shadow_action_payload_hash, "/shadow/action_payload_hash")
        _positive(binding.shadow_current_step_size, "/shadow/current_step_size")
        baseline_next = _positive(
            binding.shadow_baseline_next_step_size,
            "/shadow/baseline_next_step_size",
        )
        _positive(binding.shadow_proposed_step_size, "/shadow/proposed_step_size")
        expected_action_hash = _shadow_action_hash(
            binding.shadow_proposed_step_size,
            binding.shadow_policy_artifact_hash,
        )
        if binding.shadow_action_payload_hash != expected_action_hash:
            _fail(
                "fiber_frame_episode_shadow_action_hash_mismatch",
                "/shadow/action_payload_hash",
                "Shadow action hash does not match its policy/scalar payload.",
            )
        if baseline_next != step_size:
            _fail(
                "fiber_frame_episode_shadow_baseline_mismatch",
                "/shadow/baseline_next_step_size",
                "Shadow input must retain the executed baseline step.",
            )
        if binding.shadow_residual_ratio is not None:
            _nonnegative(
                binding.shadow_residual_ratio,
                "/shadow/residual_ratio",
            )
        _nonempty(binding.shadow_reason_code, "/shadow/reason_code")
        _nonnegative(binding.shadow_uncertainty, "/shadow/uncertainty")
        _boolean(binding.shadow_ood, "/shadow/ood")
        if binding.shadow_disposition not in {"shadow_only", "rejected"}:
            _fail(
                "fiber_frame_episode_shadow_disposition_invalid",
                "/shadow/disposition",
                "Shadow proposals must remain shadow-only or rejected.",
            )
        _hash(binding.shadow_decision_hash, "/shadow/decision_hash")
        expected_decision_hash = canonical_hash(
            {
                "observation_index": binding.from_observation_index,
                "current_step_size": binding.shadow_current_step_size,
                "baseline_next_step_size": (binding.shadow_baseline_next_step_size),
                "proposed_step_size": binding.shadow_proposed_step_size,
                "residual_ratio": binding.shadow_residual_ratio,
                "reason_code": binding.shadow_reason_code,
                "uncertainty": binding.shadow_uncertainty,
                "ood": binding.shadow_ood,
                "disposition": binding.shadow_disposition,
                "action_payload_hash": binding.shadow_action_payload_hash,
                "policy_artifact_hash": binding.shadow_policy_artifact_hash,
            }
        )
        if binding.shadow_decision_hash != expected_decision_hash:
            _fail(
                "fiber_frame_episode_shadow_decision_hash_mismatch",
                "/shadow/decision_hash",
                "Shadow decision hash does not replay from retained scalars.",
            )
    if not isinstance(binding.extensions, MappingProxyType) or binding.extensions:
        _fail(
            "fiber_frame_episode_transition_extensions_invalid",
            "/extensions",
            "Transition binding v1 requires empty immutable extensions.",
        )
    expected_hash = canonical_hash(
        _transition_binding_payload(binding, include_hash=False)
    )
    if binding.transition_binding_hash != expected_hash:
        _fail(
            "fiber_frame_episode_transition_hash_mismatch",
            "/transition_binding_hash",
            "Transition-binding hash does not match canonical content.",
        )
    return binding


def _validate_transition_episode_link(
    binding: FiberFrameSolverEpisodeTransitionBinding,
    action: SolverExecutedAction,
    *,
    episode: SolverEpisodeIR,
    index: int,
) -> None:
    source = episode.observations[binding.from_observation_index]
    target = episode.observations[binding.to_observation_index]
    if (
        action.action_index != index
        or action.observation_index != binding.from_observation_index
        or action.action_payload_hash != binding.baseline_action_payload_hash
        or action.action_kind != "step_size"
        or binding.target_load_factor != target.load_factor
    ):
        _fail(
            "fiber_frame_episode_transition_action_link_mismatch",
            f"/transition_bindings/{index}",
            "Transition does not match its episode action/observations.",
        )
    if binding.source_step_replay_hash is None or target.observation_index != index + 1:
        _fail(
            "fiber_frame_episode_transition_source_link_invalid",
            f"/transition_bindings/{index}",
            "Transition source/target link is invalid.",
        )
    if episode.episode_mode == "baseline":
        if binding.shadow_proposal_index is not None or episode.proposals:
            _fail(
                "fiber_frame_episode_baseline_proposal_forbidden",
                f"/transition_bindings/{index}/shadow",
                "Baseline episodes cannot bind proposals.",
            )
        return
    proposal_index = binding.shadow_proposal_index
    if proposal_index is None or proposal_index >= len(episode.proposals):
        _fail(
            "fiber_frame_episode_shadow_proposal_missing",
            f"/transition_bindings/{index}/shadow/proposal_index",
            "Every shadow transition must bind one proposal.",
        )
    proposal = episode.proposals[proposal_index]
    if (
        proposal.proposal_index != index
        or proposal.observation_index != source.observation_index
        or proposal.policy_id != binding.shadow_policy_id
        or proposal.policy_version != binding.shadow_policy_version
        or proposal.policy_artifact_hash != binding.shadow_policy_artifact_hash
        or proposal.action_payload_hash != binding.shadow_action_payload_hash
        or proposal.uncertainty != binding.shadow_uncertainty
        or proposal.ood != binding.shadow_ood
        or proposal.disposition != binding.shadow_disposition
    ):
        _fail(
            "fiber_frame_episode_shadow_proposal_link_mismatch",
            f"/transition_bindings/{index}/shadow",
            "Episode proposal differs from the retained shadow decision.",
        )


def _observation_binding_payload(
    binding: FiberFrameSolverEpisodeObservationBinding,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": binding.schema_version,
        "observation_index": binding.observation_index,
        "source_step_index": binding.source_step_index,
        "execution_state": {
            "epoch": binding.execution_state_epoch,
            "epoch_binding_hash": binding.execution_state_epoch_binding_hash,
            "checkpoint_state_hash": binding.checkpoint_state_hash,
        },
        "bindings": {
            "execution_topology_plan_hash": (binding.execution_topology_plan_hash),
            "execution_topology_hash": binding.execution_topology_hash,
            "solver_coordinate_scaling_hash": (binding.solver_coordinate_scaling_hash),
            "physical_equation_scaling_binding_hash": (
                binding.physical_equation_scaling_binding_hash
            ),
            "physical_residual_trace_hash": binding.physical_residual_trace_hash,
            "source_step_replay_hash": binding.source_step_replay_hash,
        },
        "observation": {
            "load_factor": binding.load_factor,
            "raw_translation_linf_n": binding.raw_translation_linf_n,
            "raw_rotation_linf_nm": binding.raw_rotation_linf_nm,
            "scaled_residual_l2": binding.scaled_residual_l2,
            "scaled_residual_linf": binding.scaled_residual_linf,
            "dimensionless_increment_linf": (binding.dimensionless_increment_linf),
            "cumulative_iteration_count": binding.cumulative_iteration_count,
        },
        "disposition": {
            "accepted": binding.accepted,
            "rollback": binding.rollback,
        },
        "extensions": dict(binding.extensions),
    }
    if include_hash:
        payload["observation_binding_hash"] = binding.observation_binding_hash
    return payload


def _transition_binding_payload(
    binding: FiberFrameSolverEpisodeTransitionBinding,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    shadow: dict[str, Any] | None
    if binding.shadow_proposal_index is None:
        shadow = None
    else:
        shadow = {
            "proposal_index": binding.shadow_proposal_index,
            "policy_id": binding.shadow_policy_id,
            "policy_version": binding.shadow_policy_version,
            "policy_artifact_hash": binding.shadow_policy_artifact_hash,
            "action_payload_hash": binding.shadow_action_payload_hash,
            "current_step_size": binding.shadow_current_step_size,
            "baseline_next_step_size": (binding.shadow_baseline_next_step_size),
            "proposed_step_size": binding.shadow_proposed_step_size,
            "residual_ratio": binding.shadow_residual_ratio,
            "reason_code": binding.shadow_reason_code,
            "uncertainty": binding.shadow_uncertainty,
            "ood": binding.shadow_ood,
            "disposition": binding.shadow_disposition,
            "decision_hash": binding.shadow_decision_hash,
        }
    payload: dict[str, Any] = {
        "schema_version": binding.schema_version,
        "transition_index": binding.transition_index,
        "from_observation_index": binding.from_observation_index,
        "to_observation_index": binding.to_observation_index,
        "source_step_index": binding.source_step_index,
        "bindings": {
            "source_step_replay_hash": binding.source_step_replay_hash,
            "parent_checkpoint_state_hash": (binding.parent_checkpoint_state_hash),
            "outcome_checkpoint_state_hash": (binding.outcome_checkpoint_state_hash),
        },
        "target_load_factor": binding.target_load_factor,
        "baseline": {
            "action_kind": "step_size",
            "step_size": binding.baseline_step_size,
            "unit": SHADOW_STEP_ACTION_UNIT,
            "source_profile": FIBER_FRAME_BASELINE_STEP_POLICY_PROFILE,
            "action_payload_hash": binding.baseline_action_payload_hash,
        },
        "outcome": {
            "committed": binding.committed,
            "rollback_exact": binding.rollback_exact,
        },
        "shadow": shadow,
        "extensions": dict(binding.extensions),
    }
    if include_hash:
        payload["transition_binding_hash"] = binding.transition_binding_hash
    return payload


def _adapter_payload(
    adapter: FiberFrameSolverEpisodeAdapter,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": adapter.schema_version,
        "authority_profile": adapter.authority_profile,
        "source_schema_versions": dict(_SOURCE_SCHEMA_VERSIONS),
        "bindings": {
            "problem_contract_hash": adapter.problem_contract_hash,
            "model_ir_content_hash": adapter.model_ir_content_hash,
            "execution_topology_plan_hash": (adapter.execution_topology_plan_hash),
            "execution_state_binding_hash": (adapter.execution_state_binding_hash),
            "checkpoint_chain_hash": adapter.checkpoint_chain_hash,
            "physical_equation_scaling_binding_hash": (
                adapter.physical_equation_scaling_binding_hash
            ),
            "engine_equation_scaling_hash": (adapter.engine_equation_scaling_hash),
            "solver_config_hash": adapter.solver_config_hash,
            "backend_receipt_hash": adapter.backend_receipt_hash,
            "source_load_path_replay_hash": (adapter.source_load_path_replay_hash),
            "terminal_receipt_hash": adapter.terminal_receipt_hash,
        },
        "profiles": {
            "analysis": FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE,
            "backend": FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE,
            "runtime": adapter.runtime_profile,
            "baseline_action": FIBER_FRAME_BASELINE_STEP_POLICY_PROFILE,
        },
        "source": {
            "load_path_status": adapter.load_path_status,
            "accepted_step_count": adapter.accepted_step_count,
            "rollback_count": adapter.rollback_count,
        },
        "episode": adapter.episode.to_manifest(),
        "observation_bindings": [
            row.to_manifest() for row in adapter.observation_bindings
        ],
        "transition_bindings": [
            row.to_manifest() for row in adapter.transition_bindings
        ],
        "data_boundary": dict(FIBER_FRAME_SOLVER_EPISODE_DATA_BOUNDARY),
        "claim_boundary": dict(FIBER_FRAME_SOLVER_EPISODE_CLAIM_BOUNDARY),
        "extensions": dict(adapter.extensions),
    }
    if include_hash:
        payload["adapter_hash"] = adapter.adapter_hash
    return payload


def validate_fiber_frame_solver_episode_adapter_manifest(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a strict hash-only manifest without granting replay authority."""

    if not isinstance(value, Mapping):
        _fail(
            "fiber_frame_episode_manifest_type_invalid",
            "/",
            "Adapter manifest must be an object.",
        )
    try:
        manifest = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFrameSolverEpisodeAdapterError(
            "fiber_frame_episode_manifest_json_invalid",
            "/",
            "Adapter manifest must be finite strict JSON.",
        ) from exc
    _exact_keys(
        manifest,
        {
            "schema_version",
            "adapter_hash",
            "authority_profile",
            "source_schema_versions",
            "bindings",
            "profiles",
            "source",
            "episode",
            "observation_bindings",
            "transition_bindings",
            "data_boundary",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if manifest["schema_version"] != FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION:
        _fail(
            "fiber_frame_episode_adapter_schema_invalid",
            "/schema_version",
            "Unsupported fiber-frame SolverEpisode adapter schema.",
        )
    if manifest["authority_profile"] != FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_episode_adapter_authority_invalid",
            "/authority_profile",
            "The adapter cannot acquire result authority.",
        )
    _hash(manifest["adapter_hash"], "/adapter_hash")
    if manifest["source_schema_versions"] != dict(_SOURCE_SCHEMA_VERSIONS):
        _fail(
            "fiber_frame_episode_source_schemas_invalid",
            "/source_schema_versions",
            "Source schema commitments are stale or incomplete.",
        )
    bindings = _mapping(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_hash",
            "execution_state_binding_hash",
            "checkpoint_chain_hash",
            "physical_equation_scaling_binding_hash",
            "engine_equation_scaling_hash",
            "solver_config_hash",
            "backend_receipt_hash",
            "source_load_path_replay_hash",
            "terminal_receipt_hash",
        },
        "/bindings",
    )
    for name, bound in bindings.items():
        if name == "terminal_receipt_hash" and bound is None:
            continue
        _hash(bound, f"/bindings/{name}")
    profiles = _mapping(manifest["profiles"], "/profiles")
    expected_profiles = {
        "analysis": FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE,
        "backend": FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE,
        "runtime": FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE,
        "baseline_action": FIBER_FRAME_BASELINE_STEP_POLICY_PROFILE,
    }
    if profiles != expected_profiles:
        _fail(
            "fiber_frame_episode_profile_mismatch",
            "/profiles",
            "Adapter profiles are stale or unsupported.",
        )
    source = _mapping(manifest["source"], "/source")
    _exact_keys(
        source,
        {"load_path_status", "accepted_step_count", "rollback_count"},
        "/source",
    )
    status = source["load_path_status"]
    if status not in {"ready", "blocked"}:
        _fail(
            "fiber_frame_episode_source_status_invalid",
            "/source/load_path_status",
            "Only ready and blocked source paths are supported.",
        )
    accepted_count = _index(
        source["accepted_step_count"],
        "/source/accepted_step_count",
    )
    rollback_count = _index(source["rollback_count"], "/source/rollback_count")
    if rollback_count != (0 if status == "ready" else 1):
        _fail(
            "fiber_frame_episode_rollback_count_invalid",
            "/source/rollback_count",
            "Ready paths have no rollback; blocked paths have exactly one.",
        )
    if (status == "ready") != (bindings["terminal_receipt_hash"] is not None):
        _fail(
            "fiber_frame_episode_terminal_receipt_binding_invalid",
            "/bindings/terminal_receipt_hash",
            "Only a ready path must bind a J5 receipt hash.",
        )

    episode = validate_solver_episode_manifest(
        _mapping(manifest["episode"], "/episode")
    )
    if (
        episode["bindings"]["model_ir_content_hash"]
        != bindings["model_ir_content_hash"]
        or episode["bindings"]["execution_plan_hash"]
        != bindings["execution_topology_plan_hash"]
        or episode["backend"]["receipt_hash"] != bindings["backend_receipt_hash"]
        or episode["analysis_profile"] != FIBER_FRAME_SOLVER_EPISODE_ANALYSIS_PROFILE
        or episode["backend"]["profile"] != FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE
    ):
        _fail(
            "fiber_frame_episode_outer_binding_mismatch",
            "/episode",
            "Episode identity/profile differs from the adapter envelope.",
        )
    mode = _mode(episode["episode_mode"], "/episode/episode_mode")
    if (
        episode["terminal"]["final_authority_status"] != "none"
        or episode["terminal"]["final_result_hash"] is not None
        or any(row["source"] != "baseline" for row in episode["executed_actions"])
        or any(row["runtime_ms"] != 0.0 for row in episode["observations"])
    ):
        _fail(
            "fiber_frame_episode_authority_promotion_forbidden",
            "/episode",
            "Manifest may record baseline execution and no result authority only.",
        )

    observation_rows = manifest["observation_bindings"]
    if not isinstance(observation_rows, list) or len(observation_rows) != (
        accepted_count + rollback_count + 1
    ):
        _fail(
            "fiber_frame_episode_observation_set_invalid",
            "/observation_bindings",
            "Observation bindings do not match source counts.",
        )
    episode_observations = episode["observations"]
    if len(episode_observations) != len(observation_rows):
        _fail(
            "fiber_frame_episode_observation_set_invalid",
            "/episode/observations",
            "Episode and adapter observation counts differ.",
        )
    normalized_observations = tuple(
        _validate_observation_binding_manifest(row, index=index)
        for index, row in enumerate(observation_rows)
    )
    for index, row in enumerate(normalized_observations):
        if (
            row["bindings"]["execution_topology_plan_hash"]
            != bindings["execution_topology_plan_hash"]
            or row["bindings"]["physical_equation_scaling_binding_hash"]
            != bindings["physical_equation_scaling_binding_hash"]
        ):
            _fail(
                "fiber_frame_episode_observation_outer_binding_mismatch",
                f"/observation_bindings/{index}/bindings",
                "Observation topology/scaling differs from the outer envelope.",
            )
    actual_accepted_count = (
        sum(int(row["disposition"]["accepted"]) for row in normalized_observations) - 1
    )
    actual_rollback_count = sum(
        int(row["disposition"]["rollback"]) for row in normalized_observations
    )
    if (
        actual_accepted_count != accepted_count
        or actual_rollback_count != rollback_count
        or (
            rollback_count == 1
            and not normalized_observations[-1]["disposition"]["rollback"]
        )
    ):
        _fail(
            "fiber_frame_episode_observation_source_count_mismatch",
            "/observation_bindings",
            "Observation dispositions differ from source counts/status.",
        )
    for index, (row, observation) in enumerate(
        zip(normalized_observations, episode_observations, strict=True)
    ):
        state = row["execution_state"]
        metrics = row["observation"]
        disposition = row["disposition"]
        if (
            observation["observation_index"] != index
            or observation["state_hash"] != state["epoch_binding_hash"]
            or observation["iteration"] != metrics["cumulative_iteration_count"]
            or observation["restart_index"] != 0
            or observation["load_factor"] != metrics["load_factor"]
            or observation["residual_linf"] != metrics["scaled_residual_linf"]
            or observation["scaled_residual_l2"] != metrics["scaled_residual_l2"]
            or observation["increment_linf"] != metrics["dimensionless_increment_linf"]
            or observation["accepted"] != disposition["accepted"]
            or observation["rollback"] != disposition["rollback"]
        ):
            _fail(
                "fiber_frame_episode_observation_link_mismatch",
                f"/observation_bindings/{index}",
                "Episode observation differs from its source binding.",
            )

    transition_rows = manifest["transition_bindings"]
    if not isinstance(transition_rows, list) or len(transition_rows) != (
        len(normalized_observations) - 1
    ):
        _fail(
            "fiber_frame_episode_transition_set_invalid",
            "/transition_bindings",
            "Every source step must bind one transition.",
        )
    if len(episode["executed_actions"]) != len(transition_rows):
        _fail(
            "fiber_frame_episode_transition_set_invalid",
            "/episode/executed_actions",
            "Episode action count differs from transition count.",
        )
    normalized_transitions = tuple(
        _validate_transition_binding_manifest(row, index=index)
        for index, row in enumerate(transition_rows)
    )
    for index, (row, action) in enumerate(
        zip(normalized_transitions, episode["executed_actions"], strict=True)
    ):
        source_row = normalized_observations[index]
        target_row = normalized_observations[index + 1]
        shadow = row["shadow"]
        if (
            row["bindings"]["parent_checkpoint_state_hash"]
            != source_row["execution_state"]["checkpoint_state_hash"]
            or row["bindings"]["outcome_checkpoint_state_hash"]
            != target_row["execution_state"]["checkpoint_state_hash"]
            or row["bindings"]["source_step_replay_hash"]
            != target_row["bindings"]["source_step_replay_hash"]
            or row["target_load_factor"] != target_row["observation"]["load_factor"]
            or row["outcome"]["committed"] != target_row["disposition"]["accepted"]
            or row["outcome"]["rollback_exact"] != target_row["disposition"]["rollback"]
            or row["baseline"]["step_size"]
            != target_row["observation"]["load_factor"]
            - source_row["observation"]["load_factor"]
            or action["action_index"] != index
            or action["observation_index"] != index
            or action["action_kind"] != "step_size"
            or action["action_payload_hash"] != row["baseline"]["action_payload_hash"]
        ):
            _fail(
                "fiber_frame_episode_transition_action_link_mismatch",
                f"/transition_bindings/{index}",
                "Transition differs from its source, target, or baseline action.",
            )
        if mode == "baseline":
            if shadow is not None or episode["proposals"]:
                _fail(
                    "fiber_frame_episode_baseline_proposal_forbidden",
                    f"/transition_bindings/{index}/shadow",
                    "Baseline episodes cannot bind proposals.",
                )
        else:
            if shadow is None or len(episode["proposals"]) != len(transition_rows):
                _fail(
                    "fiber_frame_episode_shadow_proposal_missing",
                    f"/transition_bindings/{index}/shadow",
                    "Every shadow transition must bind one proposal.",
                )
            proposal = episode["proposals"][index]
            if (
                proposal["proposal_index"] != shadow["proposal_index"]
                or proposal["observation_index"] != index
                or proposal["policy_id"] != shadow["policy_id"]
                or proposal["policy_version"] != shadow["policy_version"]
                or proposal["policy_artifact_hash"] != shadow["policy_artifact_hash"]
                or proposal["action_payload_hash"] != shadow["action_payload_hash"]
                or proposal["uncertainty"] != shadow["uncertainty"]
                or proposal["ood"] != shadow["ood"]
                or proposal["disposition"] != shadow["disposition"]
            ):
                _fail(
                    "fiber_frame_episode_shadow_proposal_link_mismatch",
                    f"/transition_bindings/{index}/shadow",
                    "Episode proposal differs from its decision binding.",
                )

    expected_proposal_count = len(transition_rows) if mode == "shadow" else 0
    if len(episode["proposals"]) != expected_proposal_count:
        _fail(
            "fiber_frame_episode_proposal_count_mismatch",
            "/episode/proposals",
            "Proposal count must equal shadow transitions or be zero in baseline.",
        )
    accepted_rows = [
        row for row in normalized_observations if row["disposition"]["accepted"]
    ]
    if (
        episode["bindings"]["initial_state_hash"]
        != normalized_observations[0]["execution_state"]["epoch_binding_hash"]
        or episode["terminal"]["final_state_hash"]
        != accepted_rows[-1]["execution_state"]["epoch_binding_hash"]
        or episode["terminal"]["converged"] != (status == "ready")
        or episode["terminal"]["reason"]
        != ("converged" if status == "ready" else "rolled_back")
        or episode["terminal"]["total_iterations"]
        != normalized_observations[-1]["observation"]["cumulative_iteration_count"]
    ):
        _fail(
            "fiber_frame_episode_terminal_state_binding_mismatch",
            "/episode/terminal",
            "Terminal state/status differs from retained execution-state ancestry.",
        )
    if manifest["data_boundary"] != dict(FIBER_FRAME_SOLVER_EPISODE_DATA_BOUNDARY):
        _fail(
            "fiber_frame_episode_data_boundary_invalid",
            "/data_boundary",
            "Raw customer/source bytes are forbidden in adapter manifests.",
        )
    if manifest["claim_boundary"] != dict(FIBER_FRAME_SOLVER_EPISODE_CLAIM_BOUNDARY):
        _fail(
            "fiber_frame_episode_claim_boundary_invalid",
            "/claim_boundary",
            "Claim boundary is stale or promoted.",
        )
    if manifest["extensions"] != {}:
        _fail(
            "fiber_frame_episode_adapter_extensions_invalid",
            "/extensions",
            "Adapter v1 requires empty extensions.",
        )
    expected_hash = canonical_hash(
        {key: item for key, item in manifest.items() if key != "adapter_hash"}
    )
    if manifest["adapter_hash"] != expected_hash:
        _fail(
            "fiber_frame_episode_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash does not match canonical content.",
        )
    return manifest


def _validate_observation_binding_manifest(
    value: Any,
    *,
    index: int,
) -> dict[str, Any]:
    row = _mapping(value, f"/observation_bindings/{index}")
    _exact_keys(
        row,
        {
            "schema_version",
            "observation_binding_hash",
            "observation_index",
            "source_step_index",
            "execution_state",
            "bindings",
            "observation",
            "disposition",
            "extensions",
        },
        f"/observation_bindings/{index}",
    )
    if row["schema_version"] != (
        FIBER_FRAME_SOLVER_EPISODE_OBSERVATION_BINDING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_episode_observation_binding_schema_invalid",
            f"/observation_bindings/{index}/schema_version",
            "Unsupported observation-binding schema.",
        )
    observation_index = _index(
        row["observation_index"],
        f"/observation_bindings/{index}/observation_index",
    )
    if observation_index != index:
        _fail(
            "fiber_frame_episode_observation_index_invalid",
            f"/observation_bindings/{index}/observation_index",
            "Observation indices must be contiguous.",
        )
    source_index = row["source_step_index"]
    if index == 0:
        source_index_valid = source_index is None
    else:
        source_index_valid = (
            _index(
                source_index,
                f"/observation_bindings/{index}/source_step_index",
            )
            == index
        )
    if not source_index_valid:
        _fail(
            "fiber_frame_episode_observation_source_index_invalid",
            f"/observation_bindings/{index}/source_step_index",
            "Only genesis omits the matching source-step index.",
        )
    state = _mapping(
        row["execution_state"],
        f"/observation_bindings/{index}/execution_state",
    )
    _exact_keys(
        state,
        {"epoch", "epoch_binding_hash", "checkpoint_state_hash"},
        f"/observation_bindings/{index}/execution_state",
    )
    disposition = _mapping(
        row["disposition"],
        f"/observation_bindings/{index}/disposition",
    )
    _exact_keys(
        disposition,
        {"accepted", "rollback"},
        f"/observation_bindings/{index}/disposition",
    )
    accepted = _boolean(
        disposition["accepted"],
        f"/observation_bindings/{index}/disposition/accepted",
    )
    rollback = _boolean(
        disposition["rollback"],
        f"/observation_bindings/{index}/disposition/rollback",
    )
    epoch = _index(
        state["epoch"],
        f"/observation_bindings/{index}/execution_state/epoch",
    )
    if accepted == rollback or epoch != index - int(rollback):
        _fail(
            "fiber_frame_episode_observation_disposition_invalid",
            f"/observation_bindings/{index}",
            "Observation must commit its epoch or retain it by exact rollback.",
        )
    _hash(
        state["epoch_binding_hash"],
        f"/observation_bindings/{index}/execution_state/epoch_binding_hash",
    )
    _hash(
        state["checkpoint_state_hash"],
        f"/observation_bindings/{index}/execution_state/checkpoint_state_hash",
    )
    bound = _mapping(
        row["bindings"],
        f"/observation_bindings/{index}/bindings",
    )
    _exact_keys(
        bound,
        {
            "execution_topology_plan_hash",
            "execution_topology_hash",
            "solver_coordinate_scaling_hash",
            "physical_equation_scaling_binding_hash",
            "physical_residual_trace_hash",
            "source_step_replay_hash",
        },
        f"/observation_bindings/{index}/bindings",
    )
    for name, item in bound.items():
        if name == "source_step_replay_hash":
            if index == 0 and item is None:
                continue
            if index == 0 or item is None:
                _fail(
                    "fiber_frame_episode_observation_source_hash_invalid",
                    f"/observation_bindings/{index}/bindings/{name}",
                    "Only genesis must omit the source-step replay hash.",
                )
        _hash(item, f"/observation_bindings/{index}/bindings/{name}")
    metrics = _mapping(
        row["observation"],
        f"/observation_bindings/{index}/observation",
    )
    _exact_keys(
        metrics,
        {
            "load_factor",
            "raw_translation_linf_n",
            "raw_rotation_linf_nm",
            "scaled_residual_l2",
            "scaled_residual_linf",
            "dimensionless_increment_linf",
            "cumulative_iteration_count",
        },
        f"/observation_bindings/{index}/observation",
    )
    _finite(metrics["load_factor"], f"/observation_bindings/{index}/load_factor")
    for name in (
        "raw_translation_linf_n",
        "raw_rotation_linf_nm",
        "scaled_residual_l2",
        "scaled_residual_linf",
        "dimensionless_increment_linf",
    ):
        _nonnegative(
            metrics[name],
            f"/observation_bindings/{index}/observation/{name}",
        )
    _index(
        metrics["cumulative_iteration_count"],
        f"/observation_bindings/{index}/observation/cumulative_iteration_count",
    )
    if row["extensions"] != {}:
        _fail(
            "fiber_frame_episode_observation_extensions_invalid",
            f"/observation_bindings/{index}/extensions",
            "Observation binding v1 requires empty extensions.",
        )
    _hash(
        row["observation_binding_hash"],
        f"/observation_bindings/{index}/observation_binding_hash",
    )
    expected_hash = canonical_hash(
        {key: item for key, item in row.items() if key != "observation_binding_hash"}
    )
    if row["observation_binding_hash"] != expected_hash:
        _fail(
            "fiber_frame_episode_observation_hash_mismatch",
            f"/observation_bindings/{index}/observation_binding_hash",
            "Observation-binding hash does not match canonical content.",
        )
    return row


def _validate_transition_binding_manifest(
    value: Any,
    *,
    index: int,
) -> dict[str, Any]:
    path = f"/transition_bindings/{index}"
    row = _mapping(value, path)
    _exact_keys(
        row,
        {
            "schema_version",
            "transition_binding_hash",
            "transition_index",
            "from_observation_index",
            "to_observation_index",
            "source_step_index",
            "bindings",
            "target_load_factor",
            "baseline",
            "outcome",
            "shadow",
            "extensions",
        },
        path,
    )
    if row["schema_version"] != (
        FIBER_FRAME_SOLVER_EPISODE_TRANSITION_BINDING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_episode_transition_binding_schema_invalid",
            f"{path}/schema_version",
            "Unsupported transition-binding schema.",
        )
    transition_index = _index(row["transition_index"], f"{path}/transition_index")
    from_index = _index(
        row["from_observation_index"],
        f"{path}/from_observation_index",
    )
    to_index = _index(
        row["to_observation_index"],
        f"{path}/to_observation_index",
    )
    source_index = _index(row["source_step_index"], f"{path}/source_step_index")
    if (
        transition_index != index
        or from_index != index
        or to_index != index + 1
        or source_index != index + 1
    ):
        _fail(
            "fiber_frame_episode_transition_index_invalid",
            path,
            "Transition, observation, and source-step indices must be contiguous.",
        )
    bound = _mapping(row["bindings"], f"{path}/bindings")
    _exact_keys(
        bound,
        {
            "source_step_replay_hash",
            "parent_checkpoint_state_hash",
            "outcome_checkpoint_state_hash",
        },
        f"{path}/bindings",
    )
    for name, item in bound.items():
        _hash(item, f"{path}/bindings/{name}")
    _finite(row["target_load_factor"], f"{path}/target_load_factor")
    baseline = _mapping(row["baseline"], f"{path}/baseline")
    _exact_keys(
        baseline,
        {
            "action_kind",
            "step_size",
            "unit",
            "source_profile",
            "action_payload_hash",
        },
        f"{path}/baseline",
    )
    if (
        baseline["action_kind"] != "step_size"
        or baseline["unit"] != SHADOW_STEP_ACTION_UNIT
        or baseline["source_profile"] != FIBER_FRAME_BASELINE_STEP_POLICY_PROFILE
    ):
        _fail(
            "fiber_frame_episode_baseline_profile_invalid",
            f"{path}/baseline",
            "Unsupported baseline action profile.",
        )
    step_size = _positive(baseline["step_size"], f"{path}/baseline/step_size")
    _hash(
        baseline["action_payload_hash"],
        f"{path}/baseline/action_payload_hash",
    )
    if baseline["action_payload_hash"] != _baseline_action_hash(step_size):
        _fail(
            "fiber_frame_episode_baseline_action_hash_mismatch",
            f"{path}/baseline/action_payload_hash",
            "Baseline action hash does not match its scalar payload.",
        )
    outcome = _mapping(row["outcome"], f"{path}/outcome")
    _exact_keys(outcome, {"committed", "rollback_exact"}, f"{path}/outcome")
    committed = _boolean(outcome["committed"], f"{path}/outcome/committed")
    rollback = _boolean(
        outcome["rollback_exact"],
        f"{path}/outcome/rollback_exact",
    )
    if committed == rollback:
        _fail(
            "fiber_frame_episode_transition_disposition_invalid",
            f"{path}/outcome",
            "Transition must commit or roll back exactly, but not both.",
        )
    if rollback and (
        bound["parent_checkpoint_state_hash"] != bound["outcome_checkpoint_state_hash"]
    ):
        _fail(
            "fiber_frame_episode_transition_rollback_state_mismatch",
            f"{path}/bindings/outcome_checkpoint_state_hash",
            "Exact rollback must preserve the parent checkpoint hash.",
        )
    shadow = row["shadow"]
    if shadow is not None:
        shadow = _mapping(shadow, f"{path}/shadow")
        _exact_keys(
            shadow,
            {
                "proposal_index",
                "policy_id",
                "policy_version",
                "policy_artifact_hash",
                "action_payload_hash",
                "current_step_size",
                "baseline_next_step_size",
                "proposed_step_size",
                "residual_ratio",
                "reason_code",
                "uncertainty",
                "ood",
                "disposition",
                "decision_hash",
            },
            f"{path}/shadow",
        )
        if shadow["proposal_index"] != index:
            _fail(
                "fiber_frame_episode_shadow_proposal_index_invalid",
                f"{path}/shadow/proposal_index",
                "Proposal indices must be contiguous.",
            )
        _nonempty(shadow["policy_id"], f"{path}/shadow/policy_id")
        _nonempty(shadow["policy_version"], f"{path}/shadow/policy_version")
        _hash(
            shadow["policy_artifact_hash"],
            f"{path}/shadow/policy_artifact_hash",
        )
        _hash(shadow["action_payload_hash"], f"{path}/shadow/action_payload_hash")
        _positive(shadow["current_step_size"], f"{path}/shadow/current_step_size")
        if (
            _positive(
                shadow["baseline_next_step_size"],
                f"{path}/shadow/baseline_next_step_size",
            )
            != step_size
        ):
            _fail(
                "fiber_frame_episode_shadow_baseline_mismatch",
                f"{path}/shadow/baseline_next_step_size",
                "Shadow input must retain the executed baseline step.",
            )
        _positive(
            shadow["proposed_step_size"],
            f"{path}/shadow/proposed_step_size",
        )
        if shadow["action_payload_hash"] != _shadow_action_hash(
            shadow["proposed_step_size"],
            shadow["policy_artifact_hash"],
        ):
            _fail(
                "fiber_frame_episode_shadow_action_hash_mismatch",
                f"{path}/shadow/action_payload_hash",
                "Shadow action hash does not match its policy/scalar payload.",
            )
        if shadow["residual_ratio"] is not None:
            _nonnegative(
                shadow["residual_ratio"],
                f"{path}/shadow/residual_ratio",
            )
        _nonempty(shadow["reason_code"], f"{path}/shadow/reason_code")
        _nonnegative(shadow["uncertainty"], f"{path}/shadow/uncertainty")
        _boolean(shadow["ood"], f"{path}/shadow/ood")
        if shadow["disposition"] not in {"shadow_only", "rejected"}:
            _fail(
                "fiber_frame_episode_shadow_disposition_invalid",
                f"{path}/shadow/disposition",
                "Shadow proposals must remain shadow-only or rejected.",
            )
        _hash(shadow["decision_hash"], f"{path}/shadow/decision_hash")
        decision_payload = {
            "observation_index": index,
            "current_step_size": shadow["current_step_size"],
            "baseline_next_step_size": shadow["baseline_next_step_size"],
            "proposed_step_size": shadow["proposed_step_size"],
            "residual_ratio": shadow["residual_ratio"],
            "reason_code": shadow["reason_code"],
            "uncertainty": shadow["uncertainty"],
            "ood": shadow["ood"],
            "disposition": shadow["disposition"],
            "action_payload_hash": shadow["action_payload_hash"],
            "policy_artifact_hash": shadow["policy_artifact_hash"],
        }
        if shadow["decision_hash"] != canonical_hash(decision_payload):
            _fail(
                "fiber_frame_episode_shadow_decision_hash_mismatch",
                f"{path}/shadow/decision_hash",
                "Shadow decision hash does not replay from retained scalars.",
            )
    if row["extensions"] != {}:
        _fail(
            "fiber_frame_episode_transition_extensions_invalid",
            f"{path}/extensions",
            "Transition binding v1 requires empty extensions.",
        )
    _hash(row["transition_binding_hash"], f"{path}/transition_binding_hash")
    expected_hash = canonical_hash(
        {key: item for key, item in row.items() if key != "transition_binding_hash"}
    )
    if row["transition_binding_hash"] != expected_hash:
        _fail(
            "fiber_frame_episode_transition_hash_mismatch",
            f"{path}/transition_binding_hash",
            "Transition-binding hash does not match canonical content.",
        )
    return row


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(
            "fiber_frame_episode_manifest_object_invalid",
            path,
            "Expected a JSON object.",
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        _fail(
            "fiber_frame_episode_manifest_keys_invalid",
            path,
            "Manifest object contains missing or unknown fields.",
        )


def _config_payload(config: NewtonRaphsonConfig) -> dict[str, Any]:
    return {
        "residual_tolerance": config.residual_tolerance,
        "increment_tolerance": config.increment_tolerance,
        "max_iterations": config.max_iterations,
        "line_search_alphas": list(config.line_search_alphas),
        "matrix_backend": config.matrix_backend,
    }


def _backend_receipt_hash(
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    solver_config_hash: str,
) -> str:
    return canonical_hash(
        {
            "backend_profile": FIBER_FRAME_SOLVER_EPISODE_BACKEND_PROFILE,
            "runtime_profile": FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE,
            "solver_config_hash": solver_config_hash,
            "execution_operator_hash": topology_plan.operator_hash,
            "execution_numeric_buffer_hash": topology_plan.numeric_buffer_hash,
            "solver_coordinate_scaling_hash": (
                topology_plan.solver_coordinate_scaling_hash
            ),
            "engine_equation_scaling_hash": (
                physical_scaling.engine_equation_scaling_hash
            ),
        }
    )


def _baseline_action_hash(step_size: float) -> str:
    return canonical_hash(
        {
            "action_kind": "step_size",
            "step_size": float(step_size),
            "unit": SHADOW_STEP_ACTION_UNIT,
            "source_profile": FIBER_FRAME_BASELINE_STEP_POLICY_PROFILE,
        }
    )


def _shadow_action_hash(step_size: float, policy_artifact_hash: str) -> str:
    return canonical_hash(
        {
            "action_kind": "step_size",
            "step_size": float(step_size),
            "unit": SHADOW_STEP_ACTION_UNIT,
            "source_profile": policy_artifact_hash,
        }
    )


def _final_increment_linf_m(solution: NewtonRaphsonVectorSolution) -> float:
    claimed = solution.metrics.get("final_increment_abs_m")
    if type(claimed) in (int, float) and not isinstance(claimed, bool):
        value = float(claimed)
    elif solution.convergence_history:
        value = float(solution.convergence_history[-1].get("increment_abs_m", 0.0))
    else:
        value = 0.0
    if not math.isfinite(value) or value < 0.0:
        _fail(
            "fiber_frame_episode_source_increment_invalid",
            "/load_path/trial_solution",
            "Final solver-coordinate increment must be finite and non-negative.",
        )
    return value


def _data_use(
    *,
    training_eligible: bool,
    source_license_receipt_hash: str | None,
    privacy_receipt_hash: str | None,
) -> SolverEpisodeDataUse:
    training = _boolean(training_eligible, "/data_use/training_eligible")
    if source_license_receipt_hash is not None:
        _hash(
            source_license_receipt_hash,
            "/data_use/source_license_receipt_hash",
        )
    if privacy_receipt_hash is not None:
        _hash(privacy_receipt_hash, "/data_use/privacy_receipt_hash")
    if training and (
        source_license_receipt_hash is None or privacy_receipt_hash is None
    ):
        _fail(
            "fiber_frame_episode_training_receipts_missing",
            "/data_use",
            "Training eligibility requires explicit license and privacy receipts.",
        )
    return SolverEpisodeDataUse(
        training_eligible=training,
        evaluation_only=not training,
        source_license_receipt_hash=source_license_receipt_hash,
        privacy_receipt_hash=privacy_receipt_hash,
        raw_customer_payload_included=False,
    )


def _mode(value: Any, path: str) -> FiberFrameSolverEpisodeMode:
    if value not in _MODES:
        _fail(
            "fiber_frame_episode_mode_invalid",
            path,
            "Mode must be baseline or shadow.",
        )
    return value


def _hash(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        _fail(
            "fiber_frame_episode_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return value


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > 2**31 - 1:
        _fail(
            "fiber_frame_episode_index_invalid",
            path,
            "Expected a bounded non-negative integer.",
        )
    return value


def _finite(value: Any, path: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        _fail(
            "fiber_frame_episode_number_invalid",
            path,
            "Expected a finite number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "fiber_frame_episode_number_invalid",
            path,
            "Expected a finite number.",
        )
    return normalized


def _nonnegative(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized < 0.0:
        _fail(
            "fiber_frame_episode_nonnegative_invalid",
            path,
            "Expected a non-negative number.",
        )
    return normalized


def _positive(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized <= 0.0:
        _fail(
            "fiber_frame_episode_positive_invalid",
            path,
            "Expected a positive number.",
        )
    return normalized


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        _fail(
            "fiber_frame_episode_boolean_invalid",
            path,
            "Expected an exact boolean.",
        )
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(
            "fiber_frame_episode_string_invalid",
            path,
            "Expected a non-empty string.",
        )
    return value


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameSolverEpisodeAdapterError(code, path, message)


__all__ = [
    "FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION",
    "FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE",
    "FIBER_FRAME_SOLVER_EPISODE_CLAIM_BOUNDARY",
    "FIBER_FRAME_SOLVER_EPISODE_DATA_BOUNDARY",
    "FIBER_FRAME_SOLVER_EPISODE_OBSERVATION_BINDING_SCHEMA_VERSION",
    "FIBER_FRAME_SOLVER_EPISODE_TRANSITION_BINDING_SCHEMA_VERSION",
    "FiberFrameSolverEpisodeAdapter",
    "FiberFrameSolverEpisodeAdapterError",
    "FiberFrameSolverEpisodeObservationBinding",
    "FiberFrameSolverEpisodeTransitionBinding",
    "create_fiber_frame_solver_episode_adapter",
    "validate_fiber_frame_solver_episode_adapter",
    "validate_fiber_frame_solver_episode_adapter_manifest",
    "validate_fiber_frame_solver_episode_adapter_shape",
]
