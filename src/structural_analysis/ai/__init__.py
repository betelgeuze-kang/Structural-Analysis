"""AI-control-plane namespace.

Only shadow observation/proposal wiring is exported here. No AI proposal is
executed and no numerical or engineering authority is created by this package.
"""

from structural_analysis.ai.shadow_solver_controller import (
    DeterministicResidualStepPolicy,
    ShadowControllerError,
    ShadowStepDecision,
    ShadowStepPolicy,
    build_shadow_solver_episode,
)

__all__ = [
    "DeterministicResidualStepPolicy",
    "ShadowControllerError",
    "ShadowStepDecision",
    "ShadowStepPolicy",
    "build_shadow_solver_episode",
]
