"""Pure binding of owner-recorded suffix artifacts and nonrefundable grants.

Self-hashes detect corruption; only the service's original invocation journal
and external authority establish custody. This module never solves a prefix.
"""

from __future__ import annotations

import base64

from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver import (
    load_ordinal_continuation,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
    hash_field,
)
from structural_analysis.execution.rc_corotational_job_request import (
    _integer,
    _object,
    _sha,
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    RC_ORDINAL_JOB_PROFILE,
    RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION,
    RCCorotationalOrdinalJobRequest,
    validate_rc_corotational_ordinal_job_request,
)

ORDINAL_JOB_VALIDATOR_ID = "managed-ordinal-owner-suffix-contract.v1"
ORDINAL_JOB_MAX_BYTES = 64 * 1024 * 1024
ORDINAL_JOB_CHECKPOINT_SCHEMA_VERSION = "rc-corotational-ordinal-job-checkpoint.v1"
ORDINAL_INVOCATION_SCHEMA_VERSION = "rc-corotational-ordinal-invocation.v1"
AUTHORITY = {
    "accepted_state": "reference_solver_commit_rollback",
    "execution_budget": "external_shared_execution_authority",
    "verification": "separately_reserved_fresh_suffix",
    "experimental_physical_validation": False,
    "design_approval": False,
    "release_qualification": False,
}
_GRANT_KEYS = {
    "schema_version",
    "job_request_hash",
    "context_hash",
    "credit_ordinal",
    "api_ordinal",
    "phase",
    "ceiling",
    "completed_before",
    "prior_checkpoint_hash",
    "native_input_sha256",
    "record_limit",
    "authority_id",
    "authority_generation",
    "authority_root",
    "worker_id",
    "lease_token_hash",
    "grant_hash",
}
_OUTCOME_KEYS = {
    "schema_version",
    "phase",
    "status",
    "job_request_hash",
    "context_hash",
    "chunk_request_hash",
    "completed_before",
    "completed_after",
    "restart_input_sha256",
    "timing",
    "api_result",
    "checkpoint_artifact_base64",
    "verification_report",
    "error",
    "unavailable_execution_work",
    "grant",
    "credits_used",
    "phase_supervision",
}
_RECEIPT_KEYS = {
    "job_request_hash",
    "context_hash",
    "chunk_request_hash",
    "completed_before",
    "actual_after",
    "restart_input_sha256",
    "prior_checkpoint_hash",
    "checkpoint_sha256",
    "checkpoint_byte_length",
    "checkpoint_state_hash",
    "api_status",
    "result_artifact_sha256",
    "production_ordinal",
    "verification_ordinal",
    "production_grant_hash",
    "verification_grant_hash",
    "production_outcome_hash",
    "verification_outcome_hash",
    "production_credits_used",
    "verification_credits_used",
    "production_work",
    "verification_work",
    "validation_report",
    "receipt_hash",
}


def _mapping(value):
    raw = value if type(value) is bytes else rc_corotational_job_canonical_bytes(value)
    return strict_json_object_bytes(raw, maximum_bytes=ORDINAL_JOB_MAX_BYTES)


def _typed(request):
    return (
        request
        if type(request) is RCCorotationalOrdinalJobRequest
        else validate_rc_corotational_ordinal_job_request(request)
    )


def _hash(value):
    return _sha(rc_corotational_job_canonical_bytes(value))


def _self_hash(value, key):
    actual = value.get(key)
    hash_field(actual, key)
    if actual != _hash({k: v for k, v in value.items() if k != key}):
        raise ValueError(f"ordinal {key} mismatch")


def _nullable_hash(value, name):
    if value is not None:
        hash_field(value, name)
    return value


def _base64(value):
    if type(value) is not str or len(value) > 24 * 1024 * 1024:
        raise ValueError("bounded native checkpoint base64 required")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid ordinal checkpoint base64") from exc
    if not raw or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("canonical nonempty ordinal checkpoint base64 required")
    return raw


def _native(request, raw):
    problem, plan, config = request.prepare()
    return load_ordinal_continuation(
        raw,
        problem,
        plan,
        maximum_solver_attempts=request.config.maximum_solver_attempts,
        maximum_subdivision_depth=request.config.maximum_subdivision_depth,
        config=config,
        recorded_source_identity=request.execution_source_identity,
    )


def ordinal_resume_binding(request, checkpoint, *, record_limit=None):
    """Decode only the owner-attached prefix; never certify a caller's self-hash."""
    typed = _typed(request)
    limit = (
        typed.execution_config.record_limit_per_call
        if record_limit is None
        else _integer(
            record_limit,
            "record_limit",
            1,
            typed.execution_config.record_limit_per_call,
        )
    )
    if checkpoint is None:
        return dict(
            context_hash=typed.context_hash,
            completed_before=0,
            native_input_sha256=None,
            native_continuation_bytes=None,
            requires_solver=True,
        )
    value = _mapping(checkpoint)
    _self_hash(value, "checkpoint_hash")
    if (
        value.get("schema_version") != ORDINAL_JOB_CHECKPOINT_SCHEMA_VERSION
        or value.get("request_hash") != typed.request_hash
        or value.get("context_hash") != typed.context_hash
        or value.get("resume_contract_hash") != typed.resume_contract_hash
    ):
        raise ValueError("ordinal attached checkpoint identity differs")
    raw = _base64(value["terminal_checkpoint_artifact_base64"])
    native = _native(typed, raw)
    if native.next_ordinal != value.get("progress_completed"):
        raise ValueError("ordinal attached progress differs from native source cursor")
    end = min(len(typed.plan.rows), native.next_ordinal + limit)
    requires = (
        not native.mechanical.certified
        or bool(native.pending_positions)
        or bool(native.terminal_failure)
    )
    if not requires:
        prior = native.mechanical
        requires = any(
            (r.target_m, r.axial_load_kn)
            != (prior.prescribed_target_m, prior.axial_load_kn)
            for r in typed.plan.rows[native.next_ordinal : end]
        )
    return dict(
        context_hash=typed.context_hash,
        completed_before=native.next_ordinal,
        native_input_sha256=_sha(raw),
        native_continuation_bytes=raw,
        requires_solver=requires,
    )


def ordinal_chunk_hash(request, grant):
    typed = _typed(request)
    return _hash(
        {
            "schema_version": "ordinal-owned-suffix-binding.v1",
            "request_hash": typed.request_hash,
            "context_hash": typed.context_hash,
            **{
                k: grant[k]
                for k in (
                    "completed_before",
                    "prior_checkpoint_hash",
                    "native_input_sha256",
                    "ceiling",
                    "record_limit",
                )
            },
        }
    )


def _grant(value, typed):
    _object(value, _GRANT_KEYS, "ordinal solver grant")
    _self_hash(value, "grant_hash")
    if (
        value["schema_version"] != "rc-ordinal-solver-credit-reservation.v1"
        or value["job_request_hash"] != typed.request_hash
        or value["context_hash"] != typed.context_hash
        or value["phase"] not in ("production", "verification")
    ):
        raise ValueError("ordinal grant identity/phase differs")
    for key in ("credit_ordinal", "api_ordinal"):
        _integer(value[key], key, 1, typed.execution_config.maximum_api_invocations)
    _integer(
        value["ceiling"], "ceiling", 0, typed.execution_config.attempt_limit_per_call
    )
    _integer(value["completed_before"], "completed_before", 0, typed.progress_total)
    _integer(
        value["record_limit"],
        "record_limit",
        1,
        typed.execution_config.record_limit_per_call,
    )
    _integer(value["authority_generation"], "authority_generation", 1, 2**53 - 1)
    for key in ("prior_checkpoint_hash", "native_input_sha256"):
        _nullable_hash(value[key], key)
    hash_field(value["lease_token_hash"], "lease_token_hash")
    for key in ("authority_id", "authority_root", "worker_id"):
        if type(value[key]) is not str or not value[key] or len(value[key]) > 4096:
            raise ValueError("ordinal grant authority binding is invalid")
    return value


def _budget(execution, solver, typed):
    _object(
        execution,
        {"maximum_attempts", "reserved_attempts", "remaining_attempts"},
        "API execution budget",
    )
    maximum = typed.execution_config.maximum_api_invocations
    _integer(execution["maximum_attempts"], "maximum_attempts", 1, maximum)
    _integer(execution["remaining_attempts"], "remaining_attempts", 0, maximum)
    spent = _integer(execution["reserved_attempts"], "reserved_attempts", 0, maximum)
    if (
        execution["maximum_attempts"] != maximum
        or execution["remaining_attempts"] != maximum - spent
    ):
        raise ValueError("ordinal immutable API budget differs")
    _object(
        solver,
        {"context_hash", "production", "verification", "reservations"},
        "solver credit budget",
    )
    if (
        solver["context_hash"] != typed.context_hash
        or type(solver["reservations"]) is not list
    ):
        raise ValueError("ordinal solver budget context/journal differs")
    if len(solver["reservations"]) > spent:
        raise ValueError("solver grants exceed reserved API entries")
    totals = {"production": 0, "verification": 0}
    seen = set()
    for index, grant in enumerate(solver["reservations"], 1):
        _grant(grant, typed)
        if (
            grant["credit_ordinal"] != index
            or grant["api_ordinal"] in seen
            or grant["api_ordinal"] > spent
        ):
            raise ValueError("ordinal grant journal is not ordered and unique")
        seen.add(grant["api_ordinal"])
        totals[grant["phase"]] += grant["ceiling"]
    for phase in totals:
        value = _object(
            solver[phase], {"maximum", "reserved", "remaining"}, "phase credit budget"
        )
        phase_max = getattr(typed.execution_config, phase + "_solver_budget")
        _integer(value["maximum"], "phase maximum", 1, phase_max)
        _integer(value["remaining"], "phase remaining", 0, phase_max)
        reserved = _integer(value["reserved"], "phase reserved", 0, phase_max)
        if (
            value["maximum"] != phase_max
            or reserved != totals[phase]
            or value["remaining"] != phase_max - reserved
        ):
            raise ValueError(
                "ordinal whole-path credits disagree with immutable grants"
            )


def _api(value, typed, grant, raw):
    from structural_analysis.api.rc_corotational_ordinal_control import (
        ORDINAL_API_SCHEMA_VERSION,
        WORK_FIELDS,
    )

    _object(
        value,
        {
            "schema_version",
            "request_hash",
            "context_hash",
            "plan_hash",
            "native_input_sha256",
            "continuation_sha256",
            "attempt_limit",
            "record_limit",
            "completed_before",
            "completed_after",
            "progress_total",
            "status",
            "detail",
            "events",
            "work",
            "credits_used",
            "source_checks",
            "preload_solver_invocations",
            "prefix_replay_solver_invocations",
            "mechanical_state_hash",
            "source_revision_is_execution_attestation",
            "experimental_physical_validation",
            "result_hash",
        },
        "ordinal API result",
    )
    _self_hash(value, "result_hash")
    if (
        value.get("schema_version") != ORDINAL_API_SCHEMA_VERSION
        or value.get("request_hash") != typed.request_hash
        or value.get("context_hash") != typed.context_hash
        or value.get("plan_hash") != typed.plan.hash
        or value.get("native_input_sha256") != grant["native_input_sha256"]
        or value.get("attempt_limit") != grant["ceiling"]
        or value.get("record_limit") != grant["record_limit"]
        or value.get("completed_before") != grant["completed_before"]
        or value.get("progress_total") != typed.progress_total
        or value.get("status")
        not in ("paused", "complete", "blocked", "budget_exhausted")
        or value.get("continuation_sha256") != _sha(raw)
    ):
        raise ValueError("ordinal production artifact differs from reserved suffix")
    after = _integer(
        value["completed_after"],
        "completed_after",
        grant["completed_before"],
        min(typed.progress_total, grant["completed_before"] + grant["record_limit"]),
    )
    used = _integer(value["credits_used"], "credits_used", 0, grant["ceiling"])
    _object(value["work"], set(WORK_FIELDS), "ordinal window work")
    for count in value["work"].values():
        _integer(count, "work counter", 0, 2**53 - 1)
    if (
        used != value["work"]["solver_invocations"]
        or after - grant["completed_before"]
        != value["work"]["completed_solve_records"] + value["work"]["hold_records"]
        or value.get("preload_solver_invocations") != 0
        or value.get("prefix_replay_solver_invocations") != 0
        or value.get("experimental_physical_validation") is not False
        or value.get("source_revision_is_execution_attestation") is not False
    ):
        raise ValueError("ordinal artifact work/progress/authority differs")
    native = _native(typed, raw)
    if (
        native.next_ordinal != after
        or value.get("mechanical_state_hash") != native.mechanical.state_hash
    ):
        raise ValueError("ordinal production continuation state differs")
    if value["status"] == "complete" and (
        after != typed.progress_total
        or native.terminal_failure
        or native.pending_positions
    ):
        raise ValueError("ordinal completion omits future source rows or a failure")
    events = value.get("events")
    if type(events) is not list or len(events) > 255:
        raise ValueError("ordinal native event window exceeds bound")
    for event in events:
        if type(event) is not dict:
            raise ValueError("ordinal native event must be an object")
        ordinal = _integer(
            event.get("ordinal"),
            "event ordinal",
            grant["completed_before"],
            typed.progress_total - 1,
        )
        row = typed.plan.rows[ordinal]
        if (
            event.get("source_row") != row.source_row
            or event.get("source_row_sha256") != row.source_row_sha256
        ):
            raise ValueError(
                "ordinal native event lost its published source-row binding"
            )
    return native


def validate_ordinal_invocation_outcome(outcome, request, request_hash):
    typed, value = _typed(request), _mapping(outcome)
    _object(value, _OUTCOME_KEYS, "ordinal invocation")
    grant = _grant(value["grant"], typed)
    if (
        request_hash != typed.request_hash
        or value["schema_version"] != ORDINAL_INVOCATION_SCHEMA_VERSION
        or value["job_request_hash"] != typed.request_hash
        or value["context_hash"] != typed.context_hash
        or value["phase"] != grant["phase"]
        or value["status"] not in ("returned", "raised")
        or value["chunk_request_hash"] != ordinal_chunk_hash(typed, grant)
        or value["completed_before"] != grant["completed_before"]
        or value["restart_input_sha256"] != grant["native_input_sha256"]
    ):
        raise ValueError("ordinal invocation does not bind its owned grant")
    _integer(
        value["completed_after"],
        "completed_after",
        grant["completed_before"],
        min(typed.progress_total, grant["completed_before"] + grant["record_limit"]),
    )
    timing = _object(value["timing"], {"wall_ns", "process_cpu_ns"}, "ordinal timing")
    for count in timing.values():
        _integer(count, "timing counter", 0, 2**63 - 1)
    supervision = _object(
        value["phase_supervision"],
        {
            "phase",
            "policy",
            "status",
            "supervisor",
            "parent_wall_ns",
            "parent_process_cpu_ns",
            "cleanup",
        },
        "ordinal phase supervision",
    )
    if (
        supervision["phase"] != value["phase"]
        or supervision["policy"]
        != typed.execution_config.phase_execution_policy.to_dict()
    ):
        raise ValueError("ordinal supervision does not bind authored policy")
    for key in ("parent_wall_ns", "parent_process_cpu_ns"):
        _integer(supervision[key], key, 0, 2**63 - 1)
    if type(value["unavailable_execution_work"]) is not bool:
        raise ValueError("ordinal unknown-work flag must be explicit")
    if value["status"] == "raised":
        if (
            not value["unavailable_execution_work"]
            or value["credits_used"] is not None
            or type(value["error"]) is not dict
            or not value["error"]
            or any(
                value[key] is not None
                for key in (
                    "api_result",
                    "checkpoint_artifact_base64",
                    "verification_report",
                )
            )
        ):
            raise ValueError(
                "raised ordinal phase must retain full nonrefundable unknown credit"
            )
        return value
    if value["error"] is not None or value["unavailable_execution_work"]:
        raise ValueError("returned ordinal phase cannot hide unknown work")
    used = _integer(value["credits_used"], "credits_used", 0, grant["ceiling"])
    supervisor = supervision["supervisor"]
    if (
        type(supervisor) is not dict
        or supervisor.get("direct_child_reaped") is not True
        or supervisor.get("child_returncode") != 0
    ):
        raise ValueError("returned ordinal phase requires a successfully reaped child")
    if value["phase"] == "production":
        if value["verification_report"] is not None:
            raise ValueError("production cannot attest its own verification")
        raw = _base64(value["checkpoint_artifact_base64"])
        _api(value["api_result"], typed, grant, raw)
        if (
            value["completed_after"] != value["api_result"]["completed_after"]
            or used != value["api_result"]["credits_used"]
        ):
            raise ValueError(
                "ordinal production metadata differs from actual artifacts"
            )
    else:
        if (
            value["api_result"] is not None
            or value["checkpoint_artifact_base64"] is not None
        ):
            raise ValueError("verification cannot duplicate production artifacts")
        report = _mapping(value["verification_report"])
        _self_hash(report, "report_hash")
        from structural_analysis.api.rc_corotational_ordinal_control import (
            ORDINAL_VERIFICATION_SCHEMA_VERSION,
        )

        if (
            report.get("schema_version") != ORDINAL_VERIFICATION_SCHEMA_VERSION
            or report.get("request_hash") != typed.request_hash
            or report.get("context_hash") != typed.context_hash
            or report.get("native_input_sha256") != grant["native_input_sha256"]
            or report.get("completed_before") != grant["completed_before"]
            or report.get("completed_after") != value["completed_after"]
            or report.get("attempt_limit") != grant["ceiling"]
            or report.get("record_limit") != grant["record_limit"]
            or report.get("credits_used") != used
            or report.get("artifact_contract_pass") is not True
            or report.get("prefix_replay_solver_invocations") != 0
            or report.get("experimental_physical_validation") is not False
        ):
            raise ValueError(
                "ordinal verification report differs from reserved fresh suffix"
            )
    return value


def build_ordinal_job_receipt(
    request,
    *,
    production_ordinal,
    verification_ordinal,
    production_outcome,
    verification_outcome,
):
    typed = _typed(request)
    production = validate_ordinal_invocation_outcome(
        production_outcome, typed, typed.request_hash
    )
    verification = validate_ordinal_invocation_outcome(
        verification_outcome, typed, typed.request_hash
    )
    if (
        production["phase"] != "production"
        or verification["phase"] != "verification"
        or production["status"] != "returned"
        or verification["status"] != "returned"
        or production["grant"]["api_ordinal"] != production_ordinal
        or verification["grant"]["api_ordinal"] != verification_ordinal
        or verification_ordinal <= production_ordinal
    ):
        raise ValueError("ordinal accepted receipt requires its recorded phase pair")
    for key in (
        "chunk_request_hash",
        "completed_before",
        "completed_after",
        "restart_input_sha256",
        "credits_used",
    ):
        if production[key] != verification[key]:
            raise ValueError(
                "ordinal production and verification reserve different suffixes"
            )
    api, report = production["api_result"], verification["verification_report"]
    raw = _base64(production["checkpoint_artifact_base64"])
    if (
        api["status"] not in ("paused", "complete")
        or report.get("contract_pass") is not True
        or report["result_artifact_sha256"] != _hash(api)
        or report["continuation_sha256"] != _sha(raw)
        or report["replay_work"] != api["work"]
    ):
        raise ValueError(
            "ordinal accepted receipt lacks matching fresh-suffix verification"
        )
    native = _native(typed, raw)
    receipt = dict(
        job_request_hash=typed.request_hash,
        context_hash=typed.context_hash,
        chunk_request_hash=production["chunk_request_hash"],
        completed_before=production["completed_before"],
        actual_after=production["completed_after"],
        restart_input_sha256=production["restart_input_sha256"],
        prior_checkpoint_hash=production["grant"]["prior_checkpoint_hash"],
        checkpoint_sha256=_sha(raw),
        checkpoint_byte_length=len(raw),
        checkpoint_state_hash=native.mechanical.state_hash,
        api_status=api["status"],
        result_artifact_sha256=_hash(api),
        production_ordinal=production_ordinal,
        verification_ordinal=verification_ordinal,
        production_grant_hash=production["grant"]["grant_hash"],
        verification_grant_hash=verification["grant"]["grant_hash"],
        production_outcome_hash=_hash(production),
        verification_outcome_hash=_hash(verification),
        production_credits_used=production["credits_used"],
        verification_credits_used=verification["credits_used"],
        production_work=api["work"],
        verification_work=report["replay_work"],
        validation_report=report,
    )
    receipt["receipt_hash"] = _hash(receipt)
    return receipt


def bind_ordinal_receipts(receipts, outcomes, request, solver_credit_budget):
    typed = _typed(request)
    records = {}
    for row in outcomes:
        if (
            type(row) is not dict
            or type(row.get("ordinal")) is not int
            or row["ordinal"] in records
        ):
            raise ValueError("ordinal invocation journal must have unique API ordinals")
        records[row["ordinal"]] = row["outcome"]
    grants = {g["api_ordinal"]: g for g in solver_credit_budget["reservations"]}
    for receipt in receipts:
        p, v = receipt["production_ordinal"], receipt["verification_ordinal"]
        if p not in records or v not in records or p not in grants or v not in grants:
            raise ValueError(
                "ordinal receipt lacks owner-recorded invocation/grant originals"
            )
        for ordinal in (p, v):
            if records[ordinal]["grant"] != grants[ordinal]:
                raise ValueError(
                    "ordinal recorded outcome differs from external authority grant"
                )
        expected = build_ordinal_job_receipt(
            typed,
            production_ordinal=p,
            verification_ordinal=v,
            production_outcome=records[p],
            verification_outcome=records[v],
        )
        if rc_corotational_job_canonical_bytes(
            expected
        ) != rc_corotational_job_canonical_bytes(receipt):
            raise ValueError(
                "ordinal receipt differs from immutable recorded phase artifacts"
            )


def build_ordinal_job_payload(
    request,
    *,
    receipts,
    execution_budget,
    solver_credit_budget,
    terminal_checkpoint,
    api_result,
    complete,
):
    typed = _typed(request)
    if (
        type(complete) is not bool
        or type(terminal_checkpoint) is not bytes
        or not receipts
    ):
        raise ValueError(
            "ordinal wrapper requires native bytes, recorded receipts and explicit completion"
        )
    rows = [_mapping(row) for row in receipts]
    value = {
        "schema_version": RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION
        if complete
        else ORDINAL_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": RC_ORDINAL_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": typed.request_hash,
        "resume_contract_hash": typed.resume_contract_hash,
        "context_hash": typed.context_hash,
        "case_id": typed.case_id,
        "source_revision": typed.source_revision,
        "source_revision_is_attestation": False,
        "progress_completed": rows[-1]["actual_after"],
        "progress_total": typed.progress_total,
        "progress_unit": typed.progress_unit,
        "plan_hash": typed.plan.hash,
        "receipts": rows,
        "execution_budget": _mapping(execution_budget),
        "solver_credit_budget": _mapping(solver_credit_budget),
        "terminal_checkpoint_artifact_base64": base64.b64encode(
            terminal_checkpoint
        ).decode("ascii"),
        "api_result": _mapping(api_result),
        "authority": dict(AUTHORITY),
    }
    value["result_hash" if complete else "checkpoint_hash"] = _hash(value)
    return _validate_payload(
        value, typed, execution_budget, solver_credit_budget, complete
    )


def _validate_payload(payload, typed, execution_budget, solver_credit_budget, complete):
    value = _mapping(payload)
    self_key = "result_hash" if complete else "checkpoint_hash"
    _object(
        value,
        {
            "schema_version",
            "profile",
            "status",
            "contract_pass",
            "request_hash",
            "resume_contract_hash",
            "context_hash",
            "case_id",
            "source_revision",
            "source_revision_is_attestation",
            "progress_completed",
            "progress_total",
            "progress_unit",
            "plan_hash",
            "receipts",
            "execution_budget",
            "solver_credit_budget",
            "terminal_checkpoint_artifact_base64",
            "api_result",
            "authority",
            self_key,
        },
        "ordinal durable wrapper",
    )
    _self_hash(value, self_key)
    expected = dict(
        schema_version=RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION
        if complete
        else ORDINAL_JOB_CHECKPOINT_SCHEMA_VERSION,
        profile=RC_ORDINAL_JOB_PROFILE,
        status="ready" if complete else "checkpointed",
        contract_pass=True,
        request_hash=typed.request_hash,
        resume_contract_hash=typed.resume_contract_hash,
        context_hash=typed.context_hash,
        case_id=typed.case_id,
        source_revision=typed.source_revision,
        source_revision_is_attestation=False,
        progress_total=typed.progress_total,
        progress_unit=typed.progress_unit,
        plan_hash=typed.plan.hash,
        authority=AUTHORITY,
    )
    if any(
        rc_corotational_job_canonical_bytes(value[k])
        != rc_corotational_job_canonical_bytes(v)
        for k, v in expected.items()
    ):
        raise ValueError("ordinal durable wrapper identity/authority differs")
    _budget(value["execution_budget"], value["solver_credit_budget"], typed)
    _budget(execution_budget, solver_credit_budget, typed)
    # A crash after checkpointing may spend later unknown reservations. Reading
    # the old immutable checkpoint must not erase or refund those owner credits.
    if (
        value["execution_budget"]["reserved_attempts"]
        > execution_budget["reserved_attempts"]
        or any(
            value["solver_credit_budget"][p]["reserved"]
            > solver_credit_budget[p]["reserved"]
            for p in ("production", "verification")
        )
        or value["solver_credit_budget"]["reservations"]
        != solver_credit_budget["reservations"][
            : len(value["solver_credit_budget"]["reservations"])
        ]
    ):
        raise ValueError(
            "ordinal saved budget is not an immutable prefix of current owner spend"
        )
    rows = value["receipts"]
    if type(rows) is not list or not rows:
        raise ValueError("ordinal durable wrapper requires immutable phase receipts")
    before, prior_native, prior_api = 0, None, 0
    grants = {g["api_ordinal"]: g for g in solver_credit_budget["reservations"]}
    for row in rows:
        _object(row, _RECEIPT_KEYS, "ordinal receipt")
        _self_hash(row, "receipt_hash")
        p, v = row["production_ordinal"], row["verification_ordinal"]
        if (
            type(p) is not int
            or type(v) is not int
            or not prior_api < p < v
            or p not in grants
            or v not in grants
            or row["job_request_hash"] != typed.request_hash
            or row["context_hash"] != typed.context_hash
            or row["completed_before"] != before
            or row["restart_input_sha256"] != prior_native
            or row["production_grant_hash"] != grants[p]["grant_hash"]
            or row["verification_grant_hash"] != grants[v]["grant_hash"]
            or grants[p]["phase"] != "production"
            or grants[v]["phase"] != "verification"
            or row["chunk_request_hash"] != ordinal_chunk_hash(typed, grants[p])
            or row["chunk_request_hash"] != ordinal_chunk_hash(typed, grants[v])
            or row["prior_checkpoint_hash"] != grants[p]["prior_checkpoint_hash"]
        ):
            raise ValueError(
                "ordinal receipt chain differs from immutable owner grants/prefix"
            )
        before = _integer(
            row["actual_after"],
            "actual_after",
            before,
            min(typed.progress_total, before + grants[p]["record_limit"]),
        )
        if row["api_status"] not in ("paused", "complete"):
            raise ValueError(
                "failed native suffix cannot advance accepted durable history"
            )
        for phase, ordinal in (("production", p), ("verification", v)):
            _integer(
                row[phase + "_credits_used"],
                phase + " credits",
                0,
                grants[ordinal]["ceiling"],
            )
        hash_field(row["checkpoint_sha256"], "checkpoint_sha256")
        prior_native, prior_api = row["checkpoint_sha256"], v
    last = rows[-1]
    raw = _base64(value["terminal_checkpoint_artifact_base64"])
    native = _api(value["api_result"], typed, grants[last["production_ordinal"]], raw)
    if (
        native.next_ordinal != before
        or value["progress_completed"] != before
        or last["checkpoint_sha256"] != _sha(raw)
        or last["checkpoint_byte_length"] != len(raw)
        or last["checkpoint_state_hash"] != native.mechanical.state_hash
        or last["result_artifact_sha256"] != _hash(value["api_result"])
    ):
        raise ValueError("ordinal terminal wrapper differs from final recorded suffix")
    if complete and (
        before != typed.progress_total or value["api_result"]["status"] != "complete"
    ):
        raise ValueError("ordinal completion requires the entire fixed source history")
    return value


def _preserve_prefix(value, checkpoint):
    if checkpoint is None:
        if value["receipts"][0]["prior_checkpoint_hash"] is not None:
            raise ValueError("first ordinal wrapper cannot invent an owner prefix")
        return
    old = _mapping(checkpoint)
    _self_hash(old, "checkpoint_hash")
    if (
        len(value["receipts"]) != len(old["receipts"]) + 1
        or value["receipts"][:-1] != old["receipts"]
        or value["receipts"][-1]["prior_checkpoint_hash"]
        != _sha(
            checkpoint
            if type(checkpoint) is bytes
            else rc_corotational_job_canonical_bytes(old)
        )
        or value["receipts"][-1]["restart_input_sha256"]
        != _sha(_base64(old["terminal_checkpoint_artifact_base64"]))
    ):
        raise ValueError(
            "ordinal wrapper replaced or skipped its owner-attached prefix"
        )


def _validation_report(value, complete):
    return {
        "schema_version": "rc-corotational-ordinal-job-validation-report.v1",
        "validator_id": ORDINAL_JOB_VALIDATOR_ID,
        "contract_pass": True,
        "request_hash": value["request_hash"],
        "context_hash": value["context_hash"],
        "artifact_hash": value["result_hash" if complete else "checkpoint_hash"],
        "progress_completed": value["progress_completed"],
        "progress_total": value["progress_total"],
        "progress_unit": value["progress_unit"],
        "complete": complete,
        "prefix_replay_solver_invocations": 0,
        "experimental_physical_validation": False,
    }


def validate_ordinal_job_checkpoint(
    data,
    *,
    request,
    progress_completed,
    resume_contract_hash,
    execution_budget,
    solver_credit_budget,
    checkpoint=None,
):
    typed = _typed(request)
    value = _validate_payload(
        data, typed, execution_budget, solver_credit_budget, False
    )
    if (
        type(progress_completed) is not int
        or progress_completed != value["progress_completed"]
        or resume_contract_hash != typed.resume_contract_hash
    ):
        raise ValueError("ordinal checkpoint progress/resume contract differs")
    _preserve_prefix(value, checkpoint)
    return dict(_validation_report(value, False), payload=value)


def validate_ordinal_job_result(
    result, *, request, execution_budget, solver_credit_budget, checkpoint=None
):
    value = _validate_payload(
        result, _typed(request), execution_budget, solver_credit_budget, True
    )
    _preserve_prefix(value, checkpoint)
    return _validation_report(value, True)
