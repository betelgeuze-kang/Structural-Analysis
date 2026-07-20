"""Non-authoritative AI observation and solver-control-plane namespace."""

from structural_analysis.ai.shadow_solver_controller import (
    DeterministicResidualStepPolicy,
    ShadowSolverControllerError,
    ShadowSolverControllerRun,
    ShadowStepDecision,
    ShadowStepInput,
    ShadowStepPolicy,
    build_shadow_step_solver_episode,
)
from structural_analysis.ai.fiber_frame_solver_episode_adapter import (
    FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION,
    FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE,
    FiberFrameSolverEpisodeAdapter,
    FiberFrameSolverEpisodeAdapterError,
    FiberFrameSolverEpisodeObservationBinding,
    FiberFrameSolverEpisodeTransitionBinding,
    create_fiber_frame_solver_episode_adapter,
    validate_fiber_frame_solver_episode_adapter,
    validate_fiber_frame_solver_episode_adapter_manifest,
    validate_fiber_frame_solver_episode_adapter_shape,
)

# Preserve the originally documented short names while exporting the concrete
# controller names used by the implementation module.
ShadowControllerError = ShadowSolverControllerError
build_shadow_solver_episode = build_shadow_step_solver_episode

__all__ = [
    "FIBER_FRAME_SOLVER_EPISODE_ADAPTER_SCHEMA_VERSION",
    "FIBER_FRAME_SOLVER_EPISODE_AUTHORITY_PROFILE",
    "DeterministicResidualStepPolicy",
    "FiberFrameSolverEpisodeAdapter",
    "FiberFrameSolverEpisodeAdapterError",
    "FiberFrameSolverEpisodeObservationBinding",
    "FiberFrameSolverEpisodeTransitionBinding",
    "ShadowSolverControllerError",
    "ShadowSolverControllerRun",
    "ShadowControllerError",
    "ShadowStepDecision",
    "ShadowStepInput",
    "ShadowStepPolicy",
    "build_shadow_step_solver_episode",
    "build_shadow_solver_episode",
    "create_fiber_frame_solver_episode_adapter",
    "validate_fiber_frame_solver_episode_adapter",
    "validate_fiber_frame_solver_episode_adapter_manifest",
    "validate_fiber_frame_solver_episode_adapter_shape",
]
