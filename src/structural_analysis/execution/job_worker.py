"""Operation dispatcher for planar and experimental RC/3D durable workers."""

from __future__ import annotations

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.execution.frame3d_direct_control_worker import (
    execute_frame3d_direct_control_claim,
)
from structural_analysis.execution.frame3d_job_contract import FRAME3D_JOB_OPERATION
from structural_analysis.execution.job_service import (
    DurableJobService,
    JobClaim,
    JobView,
)
from structural_analysis.execution.nonlinear_frame_worker import (
    execute_nonlinear_frame_claim,
)
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)
from structural_analysis.execution.rc_fiber_job_contract import RC_FIBER_JOB_OPERATION


def execute_job_claim(
    service: DurableJobService,
    claim: JobClaim,
    *,
    worker_id: str,
    authorization_token: str,
    checkpoint_step_budget: int | None = None,
    checkpoint_target_budget: int | None = None,
    lease_seconds: int = 300,
) -> JobView:
    if type(claim) is not JobClaim:
        raise ValueError("dispatcher requires an exact JobClaim")
    request = strict_json_object_bytes(
        claim.request_bytes, maximum_bytes=16 * 1024 * 1024
    )
    if request.get("operation") == "nonlinear_frame":
        if checkpoint_target_budget is not None:
            raise ValueError(
                "authored-target budget is only valid for bounded direct-control jobs"
            )
        return execute_nonlinear_frame_claim(
            service,
            claim,
            worker_id=worker_id,
            authorization_token=authorization_token,
            checkpoint_step_budget=checkpoint_step_budget,
        )
    if request.get("operation") == FRAME3D_JOB_OPERATION:
        if checkpoint_step_budget is not None:
            raise ValueError("load-step budget is not valid for bounded Frame3D jobs")
        return execute_frame3d_direct_control_claim(
            service,
            claim,
            worker_id=worker_id,
            authorization_token=authorization_token,
            checkpoint_target_budget=checkpoint_target_budget,
            lease_seconds=lease_seconds,
        )
    if request.get("operation") == RC_FIBER_JOB_OPERATION:
        if checkpoint_step_budget is not None:
            raise ValueError(
                "load-step budget is not valid for bounded RC control jobs"
            )
        return execute_rc_fiber_direct_control_claim(
            service,
            claim,
            worker_id=worker_id,
            authorization_token=authorization_token,
            checkpoint_target_budget=checkpoint_target_budget,
            lease_seconds=lease_seconds,
        )
    raise ValueError("unsupported durable worker operation")


__all__ = ["execute_job_claim"]
