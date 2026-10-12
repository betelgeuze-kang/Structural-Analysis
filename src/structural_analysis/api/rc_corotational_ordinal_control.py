"""Bounded production and separately charged fresh-suffix verification.

These numerical functions confer no owner, lease, or budget custody. Managed
workers reserve nonrefundable credits before entering either function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver import (
    dump_ordinal_continuation,
    load_ordinal_continuation,
    run_ordinal_history,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
    integer,
)
from structural_analysis.execution.rc_corotational_job_request import (
    _sha,
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    validate_rc_corotational_ordinal_job_request,
)

ORDINAL_API_SCHEMA_VERSION = "rc-corotational-ordinal-window.v1"
ORDINAL_VERIFICATION_SCHEMA_VERSION = "rc-corotational-ordinal-suffix-verification.v1"
ORDINAL_API_MAX_BYTES = 32 * 1024 * 1024
WORK_FIELDS = (
    "solver_invocations",
    "mechanical_commits",
    "failed_attempts",
    "completed_solve_records",
    "hold_records",
    "linear_solve_attempts",
    "failed_assembly_attempts",
    "assembly_attempts",
    "hold_assembly_attempts",
    "resume_verification_assembly_attempts",
)


@dataclass(frozen=True)
class OrdinalJobArtifacts:
    result_bytes: bytes
    continuation_bytes: bytes


def analyze_ordinal_job(
    request_bytes: bytes,
    restart: bytes | None,
    attempt_limit: int,
    record_limit: int,
) -> OrdinalJobArtifacts:
    """Execute at most one granted window; retain every native event and hold."""
    request = validate_rc_corotational_ordinal_job_request(request_bytes)
    integer(
        attempt_limit,
        "attempt_limit",
        0,
        request.execution_config.attempt_limit_per_call,
    )
    integer(
        record_limit, "record_limit", 1, request.execution_config.record_limit_per_call
    )
    if restart is not None and type(restart) is not bytes:
        raise ValueError("restart must be exact continuation bytes or None")
    problem, plan, config = request.prepare()
    options = dict(
        maximum_solver_attempts=request.config.maximum_solver_attempts,
        maximum_subdivision_depth=request.config.maximum_subdivision_depth,
        config=config,
    )
    prior = (
        None
        if restart is None
        else load_ordinal_continuation(restart, problem, plan, **options)
    )
    before = 0 if prior is None else prior.next_ordinal
    prior_work = {
        key: 0 if prior is None else getattr(prior, key) for key in WORK_FIELDS
    }
    consumed = 0

    def require_credit(binding: Any):
        nonlocal consumed
        if binding["context_hash"] != request.context_hash or consumed >= attempt_limit:
            raise ValueError("solver invocation lacks a matching bounded grant")
        consumed += 1

    result = run_ordinal_history(
        problem,
        plan,
        **options,
        continuation=prior,
        per_call_attempt_limit=attempt_limit,
        per_call_record_limit=record_limit,
        before_solver=require_credit,
    )
    if result.continuation.context_hash != request.context_hash:
        raise ValueError("ordinal source identity changed after request admission")
    continuation = dump_ordinal_continuation(
        problem, plan, result.continuation, **options
    )
    work = {
        key: getattr(result.continuation, key) - prior_work[key] for key in WORK_FIELDS
    }
    if consumed != work["solver_invocations"] or consumed > attempt_limit:
        raise ValueError("ordinal per-entry solver credit accounting differs")
    payload = {
        "schema_version": ORDINAL_API_SCHEMA_VERSION,
        "request_hash": request.request_hash,
        "context_hash": request.context_hash,
        "plan_hash": plan.hash,
        "native_input_sha256": None if restart is None else _sha(restart),
        "continuation_sha256": _sha(continuation),
        "attempt_limit": attempt_limit,
        "record_limit": record_limit,
        "completed_before": before,
        "completed_after": result.continuation.next_ordinal,
        "progress_total": len(plan.rows),
        "status": result.status,
        "detail": result.detail,
        "events": list(result.events),
        "work": work,
        "credits_used": consumed,
        "source_checks": result.source_checks,
        "preload_solver_invocations": result.preload_solver_invocations,
        "prefix_replay_solver_invocations": result.replay_solver_invocations,
        "mechanical_state_hash": result.continuation.mechanical.state_hash,
        "source_revision_is_execution_attestation": False,
        "experimental_physical_validation": False,
    }
    payload["result_hash"] = _sha(rc_corotational_job_canonical_bytes(payload))
    raw = rc_corotational_job_canonical_bytes(payload)
    if len(raw) > ORDINAL_API_MAX_BYTES:
        raise ValueError("ordinal window result byte budget exceeded")
    return OrdinalJobArtifacts(raw, continuation)


def verify_ordinal_job(
    request_bytes: bytes,
    input_restart: bytes | None,
    result: bytes,
    output_continuation: bytes,
    attempt_limit: int,
    record_limit: int,
) -> bytes:
    """Replay only the exact suffix from the same owner-attached prefix.

    No reconstruction of earlier source rows occurs. Numerical work here is
    charged to a separate verification reservation before the phase is launched.
    """
    supplied = strict_json_object_bytes(result, maximum_bytes=ORDINAL_API_MAX_BYTES)
    if rc_corotational_job_canonical_bytes(supplied) != result:
        raise ValueError("ordinal result requires canonical exact bytes")
    replay = analyze_ordinal_job(
        request_bytes, input_restart, attempt_limit, record_limit
    )
    if (
        replay.result_bytes != result
        or replay.continuation_bytes != output_continuation
    ):
        raise ValueError("fresh ordinal suffix differs from production artifacts")
    request = validate_rc_corotational_ordinal_job_request(request_bytes)
    report = {
        "schema_version": ORDINAL_VERIFICATION_SCHEMA_VERSION,
        "request_hash": request.request_hash,
        "context_hash": request.context_hash,
        "result_artifact_sha256": _sha(result),
        "continuation_sha256": _sha(output_continuation),
        "native_input_sha256": None if input_restart is None else _sha(input_restart),
        "completed_before": supplied["completed_before"],
        "completed_after": supplied["completed_after"],
        "attempt_limit": attempt_limit,
        "record_limit": record_limit,
        "credits_used": supplied["credits_used"],
        "artifact_contract_pass": True,
        "contract_pass": supplied["status"] in ("paused", "complete"),
        "replay_work": supplied["work"],
        "prefix_replay_solver_invocations": 0,
        "experimental_physical_validation": False,
    }
    report["report_hash"] = _sha(rc_corotational_job_canonical_bytes(report))
    return rc_corotational_job_canonical_bytes(report)
