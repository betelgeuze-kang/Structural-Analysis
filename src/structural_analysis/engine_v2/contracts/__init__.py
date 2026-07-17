"""Versioned backend-neutral Engine v2 core contracts."""

from structural_analysis.engine_v2.contracts.execution_plan import (
    EXECUTION_PLAN_CAPABILITY_PROFILE,
    EXECUTION_PLAN_DOF_COMPONENTS,
    EXECUTION_PLAN_RESIDUAL_SIGN,
    EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionPlan,
    ExecutionPlanError,
    PlanArrayDescriptor,
    create_execution_plan,
    validate_execution_plan,
    validate_execution_plan_manifest,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    STATE_IR_SCHEMA_VERSION,
    StateIR,
    StateIRError,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
    rollback_trial_state,
    validate_state_ir,
    validate_state_ir_manifest,
)

__all__ = [
    "EXECUTION_PLAN_CAPABILITY_PROFILE",
    "EXECUTION_PLAN_DOF_COMPONENTS",
    "EXECUTION_PLAN_RESIDUAL_SIGN",
    "EXECUTION_PLAN_SCHEMA_VERSION",
    "STATE_IR_SCHEMA_VERSION",
    "ExecutionPlan",
    "ExecutionPlanError",
    "PlanArrayDescriptor",
    "StateIR",
    "StateIRError",
    "commit_trial_state",
    "create_execution_plan",
    "create_initial_state",
    "open_trial_state",
    "rollback_trial_state",
    "validate_execution_plan",
    "validate_execution_plan_manifest",
    "validate_state_ir",
    "validate_state_ir_manifest",
]
