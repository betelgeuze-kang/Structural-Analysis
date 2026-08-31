"""Public, non-promoting surface for the dedicated gfx1100 worker contract."""

from structural_analysis.engine_v2_backends._hip_residual_jvp_worker_contract import (
    BLOCKERS,
    CLAIM_BOUNDARY,
    EXPECTED_ARCHITECTURE,
    EXPECTED_REPOSITORY,
    EXPECTED_REPOSITORY_ID,
    EXPECTED_SOURCE_REF,
    EXPECTED_WORKFLOW_PATH,
    EXPECTED_WORKFLOW_REF,
    HIPResidualJVPWorkerContractError,
    MAX_RETAINED_WHEEL_BYTES,
    PROFILE,
    REQUIRED_RUNNER_LABELS,
    SCHEMA_VERSION,
    build_preexecution_receipt,
    validate_preexecution_receipt,
)

__all__ = [
    "BLOCKERS",
    "CLAIM_BOUNDARY",
    "EXPECTED_ARCHITECTURE",
    "EXPECTED_REPOSITORY",
    "EXPECTED_REPOSITORY_ID",
    "EXPECTED_SOURCE_REF",
    "EXPECTED_WORKFLOW_PATH",
    "EXPECTED_WORKFLOW_REF",
    "HIPResidualJVPWorkerContractError",
    "MAX_RETAINED_WHEEL_BYTES",
    "PROFILE",
    "REQUIRED_RUNNER_LABELS",
    "SCHEMA_VERSION",
    "build_preexecution_receipt",
    "validate_preexecution_receipt",
]
