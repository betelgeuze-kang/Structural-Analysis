"""Exact durable-job dispatcher for allowlisted solver worker pairs."""

from __future__ import annotations

import hashlib
import json
from typing import Any, NoReturn

from structural_analysis.execution.frame3d_load_control_worker import (
    FRAME3D_LOAD_CONTROL_OPERATION,
    execute_frame3d_load_control_claim,
)
from structural_analysis.execution.job_service import (
    JOB_REQUEST_SCHEMA_VERSION,
    JOB_REQUEST_V2_SCHEMA_VERSION,
    DurableJobService,
    JobClaim,
    JobView,
)
from structural_analysis.execution.nonlinear_frame_worker import (
    execute_nonlinear_frame_claim,
)


class JobWorkerDispatchError(ValueError):
    """Stable failure for a claim outside the exact worker dispatch table."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def execute_job_claim(
    service: DurableJobService,
    claim: JobClaim,
    *,
    worker_id: str,
    authorization_token: str,
    checkpoint_step_budget: int | None = None,
) -> JobView:
    """Dispatch only the two exact schema-version and operation pairs."""

    if type(service) is not DurableJobService or type(claim) is not JobClaim:
        _fail(
            "worker_dispatch_argument_invalid",
            "Exact DurableJobService and JobClaim types are required.",
        )
    if claim.job.status != "running":
        _fail(
            "worker_dispatch_claim_not_running",
            "Only an active running claim may be dispatched.",
        )
    if _sha256(claim.request_bytes) != claim.job.request.content_hash:
        _fail(
            "worker_dispatch_request_integrity_failed",
            "Claim request bytes differ from the persisted artifact digest.",
        )
    identity = _request_identity(claim.request_bytes)
    arguments = {
        "worker_id": worker_id,
        "authorization_token": authorization_token,
        "checkpoint_step_budget": checkpoint_step_budget,
    }
    if identity == (JOB_REQUEST_SCHEMA_VERSION, "nonlinear_frame"):
        return execute_nonlinear_frame_claim(service, claim, **arguments)
    if identity == (
        JOB_REQUEST_V2_SCHEMA_VERSION,
        FRAME3D_LOAD_CONTROL_OPERATION,
    ):
        return execute_frame3d_load_control_claim(service, claim, **arguments)
    _fail(
        "worker_dispatch_identity_unsupported",
        "Claim schema_version and operation pair is not allowlisted.",
    )


def claim_and_execute_next(
    service: DurableJobService,
    *,
    worker_id: str,
    authorization_token: str,
    tenant_id: str | None = None,
    lease_seconds: int = 60,
    checkpoint_step_budget: int | None = None,
) -> JobView | None:
    """Claim the next durable job and run it through the exact dispatcher."""

    if type(service) is not DurableJobService:
        _fail("worker_service_invalid", "Exact DurableJobService is required.")
    claim = service.claim_next(
        worker_id=worker_id,
        authorization_token=authorization_token,
        tenant_id=tenant_id,
        lease_seconds=lease_seconds,
    )
    if claim is None:
        return None
    return execute_job_claim(
        service,
        claim,
        worker_id=worker_id,
        authorization_token=authorization_token,
        checkpoint_step_budget=checkpoint_step_budget,
    )


def _request_identity(payload: bytes) -> tuple[str, str]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise JobWorkerDispatchError(
            "worker_dispatch_request_invalid",
            "Claim request is not valid UTF-8 JSON.",
        ) from error
    schema_version = value.get("schema_version") if type(value) is dict else None
    operation = value.get("operation") if type(value) is dict else None
    if type(schema_version) is not str or type(operation) is not str:
        _fail(
            "worker_dispatch_request_invalid",
            "Claim request identity must contain exact strings.",
        )
    if _canonical_json_bytes(value) != payload:
        _fail(
            "worker_dispatch_request_invalid",
            "Claim request must use exact canonical JSON bytes.",
        )
    return schema_version, operation


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise JobWorkerDispatchError(
            "worker_dispatch_request_invalid",
            "Claim request cannot be canonicalized.",
        ) from error


def _object_without_duplicate_keys(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant: {value}")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fail(code: str, detail: str) -> NoReturn:
    raise JobWorkerDispatchError(code, detail)


__all__ = [
    "JobWorkerDispatchError",
    "claim_and_execute_next",
    "execute_job_claim",
]
