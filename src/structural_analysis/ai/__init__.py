"""Guarded AI-assistance namespace for structural solver orchestration."""

from structural_analysis.ai.shadow_solver_controller import (
    DeterministicResidualStepPolicy,
    ShadowSolverControllerRun,
    ShadowStepDecision,
    ShadowStepInput,
    ShadowStepPolicy,
    build_shadow_step_solver_episode,
)

__all__ = [
    "DeterministicResidualStepPolicy",
    "ShadowSolverControllerRun",
    "ShadowStepDecision",
    "ShadowStepInput",
    "ShadowStepPolicy",
    "build_shadow_step_solver_episode",
]
