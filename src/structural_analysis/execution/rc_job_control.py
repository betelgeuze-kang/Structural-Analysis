"""Pure RC control contracts over an already hash-verified durable event chain.

This module neither imports a service nor executes/reconstructs numerical work.
The service owns authentication, event hashes, leases, artifacts and transaction
atomicity. This reducer checks the additional control ordering and source/phase
bindings, including histories whose hashes were coherently recomputed.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from structural_analysis.api.strict_json import strict_json_object_bytes


RC_CONTROL_REQUEST_SCHEMA = "rc-job-control-request.v1"
RC_CONTROL_VIEW_SCHEMA = "rc-job-control.v1"
RC_CONTROL_EVENT_SCHEMA = "rc-job-control-event.v1"
RC_CONTROL_COMMAND_RESULT_SCHEMA = "rc-job-control-command-result.v1"
RC_CONTROL_MAX_INTEGER = 2**53 - 1
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_JOB = re.compile(r"job_[0-9a-f]{32}")
_TENANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_ID = re.compile(
    r"rc-control-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_STATUSES = {"queued", "running", "checkpointed", "succeeded", "failed", "cancelled"}
_TERMINAL = {"succeeded", "failed", "cancelled"}
_DISPOSITIONS = {"pending", "paused", "cancelled", "resumed", "completed", "failed"}
_BOUNDARIES = {
    "unleased",
    "before_analysis",
    "verified_checkpoint",
    "verified_final",
    "lease_expired",
    "worker_failure",
}
_COMMAND_KEYS = {
    "schema_version",
    "control_id",
    "action",
    "expected_request_hash",
    "expected_checkpoint_hash",
    "expected_control_revision",
    "expected_attempt",
}
_JOB_KEYS = {
    "job_id",
    "tenant_id",
    "request_hash",
    "checkpoint_hash",
    "attempt",
    "revision",
    "status",
    "terminal_event_hash",
}
_LAST_KEYS = {
    "control_id",
    "command_hash",
    "action",
    "control_revision",
    "requested_event_revision",
    "resolved_event_revision",
    "disposition",
    "boundary",
    "applied_checkpoint_hash",
    "applied_progress",
}
_VIEW_KEYS = {
    "schema_version",
    "job",
    "control_revision",
    "state",
    "last_command",
    "can_pause",
    "can_cancel",
    "can_resume_control",
}


def _check(condition: Any, code: str = "rc_control_integrity_failed") -> None:
    if not condition:
        raise ValueError(code)


def _exact(value: Any, keys: set[str]) -> dict[str, Any]:
    _check(type(value) is dict and set(value) == keys)
    return value


def _integer(value: Any, minimum: int = 0) -> int:
    _check(type(value) is int and minimum <= value <= RC_CONTROL_MAX_INTEGER)
    return value


def _text(value: Any, pattern: re.Pattern[str]) -> str:
    _check(type(value) is str and pattern.fullmatch(value) is not None)
    return value


def _hash(value: Any, *, nullable: bool = False) -> str | None:
    return None if nullable and value is None else _text(value, _HASH)


def validate_rc_control_command(value: Any) -> dict[str, Any]:
    """Return a detached, exact command, rejecting bool-as-int and unknown keys."""
    try:
        raw = _exact(value, _COMMAND_KEYS)
        _check(raw["schema_version"] == RC_CONTROL_REQUEST_SCHEMA)
        _text(raw["control_id"], _ID)
        _check(raw["action"] in ("pause", "cancel", "resume"))
        _hash(raw["expected_request_hash"])
        _hash(raw["expected_checkpoint_hash"], nullable=True)
        _integer(raw["expected_control_revision"])
        _integer(raw["expected_attempt"])
        return dict(raw)
    except (ValueError, TypeError):
        raise ValueError("rc_control_request_invalid") from None


def rc_control_command_hash(command: Any) -> str:
    value = validate_rc_control_command(command)
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _payload(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("payload_json")
    _check(type(raw) is str)
    return strict_json_object_bytes(raw.encode("utf-8"), maximum_bytes=1024 * 1024)


def _requested(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = _exact(
        _payload(event),
        {"schema_version", "control_revision", "command", "command_hash"},
    )
    _check(payload["schema_version"] == RC_CONTROL_EVENT_SCHEMA)
    command = validate_rc_control_command(payload["command"])
    _check(payload["command_hash"] == rc_control_command_hash(command))
    return {
        "command": command,
        "command_hash": payload["command_hash"],
        "control_revision": _integer(payload["control_revision"], 1),
        "requested_event_revision": _integer(event.get("revision")),
    }


def find_rc_control_command(
    events: Sequence[Mapping[str, Any]], control_id: str
) -> dict[str, Any] | None:
    """Find the immutable acceptance receipt, independently of the latest view.

    The service validates chain/reducer integrity before this lookup. A replay
    must compare this command/hash before checking the caller's now-stale CAS.
    """
    try:
        _text(control_id, _ID)
        found = None
        for event in events:
            if event["event_type"] == "rc_control_requested":
                receipt = _requested(event)
                if receipt["command"]["control_id"] == control_id:
                    _check(found is None)
                    found = receipt
        return found
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ValueError("rc_control_integrity_failed") from None


def _state(status: str, last: dict[str, Any] | None) -> str:
    if status in _TERMINAL:
        return "terminal"
    if last is None:
        return "available"
    if last["disposition"] == "pending":
        return f"{last['action']}_pending"
    return "paused" if last["disposition"] == "paused" else "available"


def _capabilities(state: str) -> tuple[bool, bool, bool]:
    return (
        state == "available",
        state in {"available", "paused", "pause_pending"},
        state == "paused",
    )


def validate_rc_control_view(value: Any) -> dict[str, Any]:
    """Strict transport and cross-field semantics, without event authority."""
    try:
        raw = _exact(value, _VIEW_KEYS)
        _check(raw["schema_version"] == RC_CONTROL_VIEW_SCHEMA)
        job = _exact(raw["job"], _JOB_KEYS)
        _text(job["job_id"], _JOB)
        _text(job["tenant_id"], _TENANT)
        _hash(job["request_hash"])
        _hash(job["checkpoint_hash"], nullable=True)
        _hash(job["terminal_event_hash"])
        _integer(job["attempt"])
        _integer(job["revision"])
        _check(job["status"] in _STATUSES)
        if job["status"] == "checkpointed":
            _check(job["checkpoint_hash"] is not None)
        elif job["status"] == "queued":
            _check(job["checkpoint_hash"] is None)
        revision = _integer(raw["control_revision"])
        _check(revision <= job["revision"])
        last = raw["last_command"]
        if last is None:
            _check(revision == 0)
        else:
            _exact(last, _LAST_KEYS)
            _text(last["control_id"], _ID)
            _hash(last["command_hash"])
            _check(last["action"] in ("pause", "cancel", "resume"))
            _check(_integer(last["control_revision"], 1) == revision)
            requested = _integer(last["requested_event_revision"], 1)
            _check(requested <= job["revision"] and revision <= requested)
            _check(last["disposition"] in _DISPOSITIONS)
            _hash(last["applied_checkpoint_hash"], nullable=True)
            if last["disposition"] == "pending":
                _check(last["action"] != "resume" and job["status"] == "running")
                _check(
                    last["resolved_event_revision"] is None
                    and last["boundary"] is None
                    and last["applied_checkpoint_hash"] is None
                    and last["applied_progress"] is None
                )
            else:
                resolved = _integer(last["resolved_event_revision"], 1)
                _check(
                    requested < resolved <= job["revision"]
                    and last["boundary"] in _BOUNDARIES
                )
                progress = _exact(last["applied_progress"], {"completed", "total"})
                _check(
                    _integer(progress["completed"]) <= _integer(progress["total"], 1)
                )
                allowed = {
                    "pause": {"paused", "completed", "failed"},
                    "cancel": {"cancelled", "failed"},
                    "resume": {"resumed"},
                }
                _check(last["disposition"] in allowed[last["action"]])
                if last["disposition"] == "paused":
                    _check(
                        job["status"] in {"queued", "checkpointed"}
                        and last["boundary"]
                        in {
                            "unleased",
                            "before_analysis",
                            "verified_checkpoint",
                            "lease_expired",
                        }
                    )
                    _check(last["applied_checkpoint_hash"] == job["checkpoint_hash"])
                elif last["disposition"] == "cancelled":
                    _check(
                        job["status"] == "cancelled"
                        and last["boundary"] != "worker_failure"
                    )
                elif last["disposition"] == "completed":
                    _check(
                        job["status"] == "succeeded"
                        and last["boundary"] == "verified_final"
                    )
                elif last["disposition"] == "resumed":
                    _check(last["boundary"] == "unleased")
                else:
                    _check(last["boundary"] == "worker_failure")
        expected_state = _state(job["status"], last)
        _check(raw["state"] == expected_state and expected_state != "resume_pending")
        for key, expected in zip(
            ("can_pause", "can_cancel", "can_resume_control"),
            _capabilities(expected_state),
        ):
            _check(type(raw[key]) is bool and raw[key] is expected)
        return json.loads(json.dumps(raw, allow_nan=False))
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ValueError("rc_control_integrity_failed") from None


def build_rc_control_command_result(
    receipt: Mapping[str, Any], view: Any
) -> dict[str, Any]:
    command = validate_rc_control_command(receipt["command"])
    _check(receipt["command_hash"] == rc_control_command_hash(command))
    return validate_rc_control_command_result(
        {
            "schema_version": RC_CONTROL_COMMAND_RESULT_SCHEMA,
            "control_id": command["control_id"],
            "command_hash": receipt["command_hash"],
            "accepted_control_revision": receipt["control_revision"],
            "view": view,
        }
    )


def validate_rc_control_command_result(value: Any) -> dict[str, Any]:
    try:
        raw = _exact(
            value,
            {
                "schema_version",
                "control_id",
                "command_hash",
                "accepted_control_revision",
                "view",
            },
        )
        _check(raw["schema_version"] == RC_CONTROL_COMMAND_RESULT_SCHEMA)
        _text(raw["control_id"], _ID)
        _hash(raw["command_hash"])
        revision = _integer(raw["accepted_control_revision"], 1)
        view = validate_rc_control_view(raw["view"])
        _check(revision <= view["control_revision"])
        if revision == view["control_revision"]:
            _check(
                view["last_command"]["control_id"] == raw["control_id"]
                and view["last_command"]["command_hash"] == raw["command_hash"]
            )
        return {**raw, "view": view}
    except (KeyError, TypeError, ValueError):
        raise ValueError("rc_control_integrity_failed") from None


def build_rc_control_view(
    job_metadata: Mapping[str, Any], events: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Reduce a complete stable snapshot, after the service checks its hashes.

    Publication must retain the pre-publication view until its atomic sequence
    (checkpoint/resolution/terminal event) is complete; intermediate prefixes
    intentionally do not satisfy this public-view contract.
    """
    try:
        return _reduce(job_metadata, events)
    except (KeyError, TypeError, ValueError, UnicodeError, IndexError):
        raise ValueError("rc_control_integrity_failed") from None


def _reduce(
    job: Mapping[str, Any], events: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    _check(bool(events))
    current_request = None
    checkpoint = None
    attempt = completed = total = revision = 0
    status = "queued"
    last: dict[str, Any] | None = None
    seen: set[str] = set()
    reservations: dict[int, dict[str, Any]] = {}
    returned: dict[int, dict[str, Any]] = {}
    verification_for: set[int] = set()
    required_next: tuple[str, int | None] | None = None
    previous_kind = ""
    has_control = any(event["event_type"].startswith("rc_control_") for event in events)
    for index, event in enumerate(events):
        _check(_integer(event["revision"]) == index)
        kind, next_status = event["event_type"], event["status"]
        _check(type(kind) is str and next_status in _STATUSES)
        payload = _payload(event)
        _hash(event["event_hash"])
        prior_state = _state(status, last)
        pending = last is not None and last["disposition"] == "pending"
        if required_next is not None:
            expected_kind, expected_progress = required_next
            _check(kind == expected_kind)
            if expected_progress is not None:
                _check(payload.get("progress_completed") == expected_progress)
            required_next = None
        if prior_state == "paused":
            _check(
                kind
                not in {
                    "claimed",
                    "execution_attempt_reserved",
                    "rc_invocation_recorded",
                    "checkpoint_committed",
                    "completed",
                    "lease_renewed",
                    "resume_requested",
                    "cancelled",
                }
            )
        if kind == "submitted":
            _check(index == 0 and next_status == "queued")
            current_request = _hash(payload["request_hash"])
            total = _integer(payload["progress_total"], 1)
        elif kind == "rc_control_requested":
            receipt = _requested(event)
            command = receipt["command"]
            _check(next_status == status and status not in _TERMINAL)
            _check(
                receipt["control_revision"] == revision + 1
                and command["expected_control_revision"] == revision
                and command["expected_request_hash"] == current_request
                and command["expected_checkpoint_hash"] == checkpoint
                and command["expected_attempt"] == attempt
            )
            _check(command["control_id"] not in seen)
            action = command["action"]
            _check(
                (action == "pause" and prior_state == "available")
                or (
                    action == "cancel"
                    and prior_state in {"available", "paused", "pause_pending"}
                )
                or (action == "resume" and prior_state == "paused")
            )
            seen.add(command["control_id"])
            revision += 1
            last = {
                "control_id": command["control_id"],
                "command_hash": receipt["command_hash"],
                "action": action,
                "control_revision": revision,
                "requested_event_revision": index,
                "resolved_event_revision": None,
                "disposition": "pending",
                "boundary": None,
                "applied_checkpoint_hash": None,
                "applied_progress": None,
            }
        elif kind == "rc_control_resolved":
            _exact(
                payload,
                {
                    "schema_version",
                    "control_revision",
                    "control_id",
                    "disposition",
                    "boundary",
                    "checkpoint_hash",
                    "progress_completed",
                    "progress_total",
                    "attempt",
                },
            )
            _check(
                payload["schema_version"] == RC_CONTROL_EVENT_SCHEMA
                and pending
                and last is not None
            )
            _check(
                _integer(payload["control_revision"], 1) == revision
                and payload["control_id"] == last["control_id"]
            )
            _check(
                _integer(payload["attempt"]) == attempt
                and payload["checkpoint_hash"] == checkpoint
            )
            disposition, boundary = payload["disposition"], payload["boundary"]
            allowed = {
                "pause": {"paused", "completed", "failed"},
                "cancel": {"cancelled", "failed"},
                "resume": {"resumed"},
            }
            _check(disposition in allowed[last["action"]] and boundary in _BOUNDARIES)
            applied = _integer(payload["progress_completed"])
            _check(_integer(payload["progress_total"], 1) == total and applied <= total)
            _check(
                applied == completed
                if disposition != "completed"
                else completed <= applied
            )
            if boundary == "unleased":
                _check(
                    status in {"queued", "checkpointed"}
                    and disposition in {"paused", "cancelled", "resumed"}
                )
            elif boundary == "before_analysis":
                _check(status == "running" and disposition in {"paused", "cancelled"})
                # Earlier/unknown reservations remain spent. The service stops
                # the new reservation, not the history of this lease attempt.
            elif boundary == "verified_checkpoint":
                _check(
                    previous_kind == "checkpoint_committed"
                    and status == "checkpointed"
                    and disposition in {"paused", "cancelled"}
                )
            elif boundary == "verified_final":
                _check(
                    status == "running" and disposition in {"completed", "cancelled"}
                )
            elif boundary == "lease_expired":
                _check(
                    previous_kind == "lease_expired_requeued"
                    and disposition in {"paused", "cancelled"}
                )
            else:
                _check(status == "running" and disposition == "failed")
            if disposition == "paused":
                _check(
                    next_status
                    == ("checkpointed" if checkpoint is not None else "queued")
                )
            else:
                _check(next_status == status)
            if disposition in {"completed", "cancelled", "failed"}:
                required_next = (
                    {
                        "completed": "completed",
                        "cancelled": "cancelled",
                        "failed": "failed",
                    }[disposition],
                    applied if disposition == "completed" else None,
                )
            last.update(
                resolved_event_revision=index,
                disposition=disposition,
                boundary=boundary,
                applied_checkpoint_hash=checkpoint,
                applied_progress={"completed": applied, "total": total},
            )
        elif kind.startswith("rc_control_"):
            _check(False)
        elif kind == "claimed":
            _check(
                status in {"queued", "checkpointed"}
                and next_status == "running"
                and not pending
            )
            _check(
                _integer(payload["attempt"], 1) == attempt + 1
                and payload["checkpoint_hash"] == checkpoint
            )
            attempt += 1
        elif kind == "checkpoint_committed":
            _check(status == "running" and next_status == "checkpointed")
            checkpoint = _hash(payload["checkpoint_hash"])
            value = _integer(payload["progress_completed"])
            _check(completed < value < total and payload["progress_total"] == total)
            completed = value
        elif kind == "completed":
            _check(status == "running" and next_status == "succeeded" and not pending)
            value = _integer(payload["progress_completed"])
            _check(completed <= value <= total)
            completed = value
        elif kind == "failed":
            _check(status == "running" and next_status == "failed" and not pending)
        elif kind in {"attempt_failed_requeued", "lease_expired_requeued"}:
            _check(
                status == "running"
                and next_status
                == ("checkpointed" if checkpoint is not None else "queued")
            )
            _check(not pending or kind == "lease_expired_requeued")
        elif kind == "resume_requested":
            _check(
                status == "failed"
                and not pending
                and next_status
                == ("checkpointed" if checkpoint is not None else "queued")
            )
            _check(
                payload["request_hash"] == current_request
                and payload["checkpoint_hash"] == checkpoint
            )
        elif kind == "cancelled":
            _check(
                next_status == "cancelled" and not pending and status not in _TERMINAL
            )
            _check(
                status != "running"
                or (
                    last is not None
                    and last["disposition"] == "cancelled"
                    and last["resolved_event_revision"] == index - 1
                )
            )
        elif kind == "execution_attempt_reserved":
            _check(status == next_status == "running")
            ordinal = _integer(payload["reserved_attempts"], 1)
            _check(ordinal not in reservations)
            phase = payload.get("rc_phase")
            if "rc_phase" in payload:
                _check(type(phase) is dict)
            if has_control or phase is not None:
                _check(_integer(payload["attempt"], 1) == attempt)
                _hash(payload["lease_token_hash"])
                if phase is not None:
                    _exact(phase, {"phase", "chunk_request_hash", "analysis_ordinal"})
                    _check(phase["phase"] in {"analysis", "verification"})
                    _hash(phase["chunk_request_hash"])
                    if phase["phase"] == "analysis":
                        _check(phase["analysis_ordinal"] is None and not pending)
                    else:
                        analysis = _integer(phase["analysis_ordinal"], 1)
                        _matching_analysis(
                            analysis,
                            reservations,
                            returned,
                            verification_for,
                            payload,
                            phase["chunk_request_hash"],
                            completed,
                        )
                        verification_for.add(analysis)
                elif pending:
                    candidates = [
                        n
                        for n, row in returned.items()
                        if row["phase"] == "analysis"
                        and row["status"] == "returned"
                        and row["completed_before"] == completed
                        and reservations[n]["attempt"] == attempt
                        and reservations[n]["lease_token_hash"]
                        == payload["lease_token_hash"]
                        and n not in verification_for
                    ]
                    _check(len(candidates) == 1)
                    analysis = candidates[0]
                    phase = {
                        "phase": "verification",
                        "chunk_request_hash": returned[analysis]["chunk_request_hash"],
                        "analysis_ordinal": analysis,
                    }
                    verification_for.add(analysis)
            reservations[ordinal] = {
                "attempt": payload.get("attempt", attempt),
                "lease_token_hash": payload.get("lease_token_hash"),
                "phase": phase,
            }
        elif kind == "rc_invocation_recorded":
            _check(status == next_status == "running")
            ordinal = _integer(payload["ordinal"], 1)
            _check(ordinal in reservations and ordinal not in returned)
            metadata = payload["metadata"]
            _check(
                type(metadata) is dict
                and metadata["job_request_hash"] == current_request
            )
            _check(_integer(metadata["completed_before"]) == completed)
            _check(reservations[ordinal]["attempt"] == attempt)
            phase = reservations[ordinal]["phase"]
            if phase is not None:
                _check(
                    metadata["phase"] == phase["phase"]
                    and metadata["chunk_request_hash"] == phase["chunk_request_hash"]
                )
            returned[ordinal] = metadata
        else:
            _check(next_status == status)
        status, previous_kind = next_status, kind
    _check(required_next is None)
    _check(
        current_request == job["request_hash"]
        and checkpoint == job["checkpoint_hash"]
        and attempt == job["attempt"]
        and completed == job["progress_completed"]
        and total == job["progress_total"]
        and status == job["status"]
        and events[-1]["revision"] == job["revision"]
        and events[-1]["event_hash"] == job["terminal_event_hash"]
    )
    # Generic external-spend reconciliation can append after a terminal event.
    # The numerical profile owns any stricter completed-last projection rule.
    state = _state(status, last)
    pause, cancel, resume = _capabilities(state)
    return validate_rc_control_view(
        {
            "schema_version": RC_CONTROL_VIEW_SCHEMA,
            "job": {key: job[key] for key in _JOB_KEYS},
            "control_revision": revision,
            "state": state,
            "last_command": last,
            "can_pause": pause,
            "can_cancel": cancel,
            "can_resume_control": resume,
        }
    )


def _matching_analysis(
    ordinal: int,
    reservations: dict[int, dict[str, Any]],
    returned: dict[int, dict[str, Any]],
    used: set[int],
    reservation: dict[str, Any],
    chunk: str,
    completed: int,
) -> None:
    prior, outcome = reservations.get(ordinal), returned.get(ordinal)
    _check(prior is not None and outcome is not None and ordinal not in used)
    _check(
        prior["attempt"] == reservation["attempt"]
        and prior["lease_token_hash"] == reservation["lease_token_hash"]
    )
    _check(
        outcome["phase"] == "analysis"
        and outcome["status"] == "returned"
        and outcome["chunk_request_hash"] == chunk
    )
    _check(_integer(outcome["completed_before"]) == completed)
