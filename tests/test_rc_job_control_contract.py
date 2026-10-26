"""Synthetic control histories only: no service, database or numerical API."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.execution.rc_job_control import (
    RC_CONTROL_MAX_INTEGER,
    build_rc_control_command_result,
    build_rc_control_view,
    find_rc_control_command,
    rc_control_command_hash,
    validate_rc_control_command,
    validate_rc_control_command_result,
    validate_rc_control_view,
)


REQUEST = "sha256:" + "1" * 64
CHECKPOINT = "sha256:" + "2" * 64
CHUNK = "sha256:" + "3" * 64
LEASE = "sha256:" + "4" * 64
JOB = "job_" + "1" * 32


def control_id(number=1):
    return f"rc-control-00000000-0000-4000-8000-{number:012x}"


def command(action="pause", **changes):
    return {
        "schema_version": "rc-job-control-request.v1",
        "control_id": control_id(),
        "action": action,
        "expected_request_hash": REQUEST,
        "expected_checkpoint_hash": None,
        "expected_control_revision": 0,
        "expected_attempt": 0,
        **changes,
    }


class History:
    def __init__(self):
        self.events = []
        self.job = {
            "job_id": JOB,
            "tenant_id": "tenant-a",
            "request_hash": REQUEST,
            "checkpoint_hash": None,
            "attempt": 0,
            "revision": 0,
            "status": "queued",
            "terminal_event_hash": REQUEST,
            "progress_completed": 0,
            "progress_total": 5,
        }
        self.append(
            "submitted", "queued", {"request_hash": REQUEST, "progress_total": 5}
        )

    def append(self, kind, status=None, payload=None):
        row = {
            "revision": len(self.events),
            "event_type": kind,
            "status": status or self.job["status"],
            "occurred_at": "2026-10-23T00:00:00.000000Z",
            "payload_json": json.dumps(payload or {}),
        }
        self.events.append(row)
        self.job.update(revision=row["revision"], status=row["status"])
        if kind == "claimed":
            self.job["attempt"] = payload["attempt"]
        if kind == "checkpoint_committed":
            self.job["checkpoint_hash"] = payload["checkpoint_hash"]
        if kind in {"checkpoint_committed", "completed"}:
            self.job["progress_completed"] = payload["progress_completed"]
        self.rehash()
        return row

    def rehash(self):
        previous = None
        for event in self.events:
            event["previous_event_hash"] = previous
            body = {
                "schema_version": "structural-analysis-job-event.v1",
                "job_id": JOB,
                **{
                    key: event[key]
                    for key in ("revision", "event_type", "status", "occurred_at")
                },
                "payload": json.loads(event["payload_json"]),
                "previous_event_hash": previous,
            }
            previous = (
                "sha256:"
                + hashlib.sha256(
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            )
            event["event_hash"] = previous
        self.job["terminal_event_hash"] = previous

    def mutate(self, index, change):
        payload = json.loads(self.events[index]["payload_json"])
        change(payload)
        self.events[index]["payload_json"] = json.dumps(payload)
        self.rehash()

    def claim(self):
        self.append(
            "claimed",
            "running",
            {
                "attempt": self.job["attempt"] + 1,
                "checkpoint_hash": self.job["checkpoint_hash"],
            },
        )

    def request(self, action="pause", **changes):
        revision = sum(
            event["event_type"] == "rc_control_requested" for event in self.events
        )
        value = command(
            action,
            control_id=control_id(revision + 1),
            expected_control_revision=revision,
            expected_checkpoint_hash=self.job["checkpoint_hash"],
            expected_attempt=self.job["attempt"],
        )
        value.update(changes)
        self.append(
            "rc_control_requested",
            payload={
                "schema_version": "rc-job-control-event.v1",
                "control_revision": revision + 1,
                "command": value,
                "command_hash": rc_control_command_hash(value),
            },
        )
        return value

    def resolve(self, disposition, boundary, **changes):
        requested = next(
            json.loads(row["payload_json"])
            for row in reversed(self.events)
            if row["event_type"] == "rc_control_requested"
        )
        payload = {
            "schema_version": "rc-job-control-event.v1",
            "control_revision": requested["control_revision"],
            "control_id": requested["command"]["control_id"],
            "disposition": disposition,
            "boundary": boundary,
            "checkpoint_hash": self.job["checkpoint_hash"],
            "progress_completed": self.job["progress_completed"],
            "progress_total": self.job["progress_total"],
            "attempt": self.job["attempt"],
            **changes,
        }
        status = (
            ("checkpointed" if self.job["checkpoint_hash"] else "queued")
            if disposition == "paused"
            else self.job["status"]
        )
        self.append("rc_control_resolved", status, payload)

    def reserve(
        self, ordinal, phase="analysis", analysis_ordinal=None, chunk=CHUNK, **changes
    ):
        payload = {
            "reserved_attempts": ordinal,
            "attempt": self.job["attempt"],
            "lease_token_hash": LEASE,
            "rc_phase": {
                "phase": phase,
                "chunk_request_hash": chunk,
                "analysis_ordinal": analysis_ordinal,
            },
            **changes,
        }
        self.append("execution_attempt_reserved", payload=payload)

    def outcome(self, ordinal, phase="analysis", status="returned", chunk=CHUNK):
        self.append(
            "rc_invocation_recorded",
            payload={
                "ordinal": ordinal,
                "metadata": {
                    "job_request_hash": REQUEST,
                    "phase": phase,
                    "status": status,
                    "chunk_request_hash": chunk,
                    "completed_before": self.job["progress_completed"],
                },
            },
        )

    def checkpoint(self, completed=1):
        self.append(
            "checkpoint_committed",
            "checkpointed",
            {
                "checkpoint_hash": CHECKPOINT,
                "progress_completed": completed,
                "progress_total": self.job["progress_total"],
            },
        )

    def view(self):
        return build_rc_control_view(self.job, self.events)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_control_revision", True),
        ("expected_attempt", False),
        ("expected_attempt", -1),
        ("expected_control_revision", RC_CONTROL_MAX_INTEGER + 1),
        ("expected_attempt", 1.0),
        ("control_id", "rc-control-00000000-0000-0000-8000-000000000001"),
        ("control_id", "RC-CONTROL-00000000-0000-4000-8000-000000000001"),
        ("action", "stop"),
        ("action", []),
        ("expected_request_hash", "SHA256:" + "1" * 64),
        ("expected_checkpoint_hash", False),
        ("unknown", 0),
    ],
)
def test_command_is_exact_and_rejects_ambiguous_values(field, value):
    with pytest.raises(ValueError, match="rc_control_request_invalid"):
        validate_rc_control_command(command(**{field: value}))


def test_command_canonical_hash_is_order_independent_but_binds_every_field():
    value = command()
    assert validate_rc_control_command(value) == value
    assert validate_rc_control_command(value) is not value
    assert rc_control_command_hash(
        dict(reversed(list(value.items())))
    ) == rc_control_command_hash(value)
    assert rc_control_command_hash(command(action="cancel")) != rc_control_command_hash(
        value
    )
    assert rc_control_command_hash(
        command(expected_checkpoint_hash=CHECKPOINT)
    ) != rc_control_command_hash(value)
    assert (
        rc_control_command_hash(value)
        == "sha256:"
        + hashlib.sha256(
            b'{"action":"pause","control_id":"rc-control-00000000-0000-4000-8000-000000000001","expected_attempt":0,"expected_checkpoint_hash":null,"expected_control_revision":0,"expected_request_hash":"sha256:1111111111111111111111111111111111111111111111111111111111111111","schema_version":"rc-job-control-request.v1"}'
        ).hexdigest()
    )


def test_existing_history_has_no_hold_and_original_metadata_is_not_mutated():
    h = History()
    before = deepcopy((h.job, h.events))
    assert h.view()["state"] == "available"
    assert h.view()["last_command"] is None
    assert h.view()["control_revision"] == 0
    assert (h.job, h.events) == before
    h.claim()
    h.append("lease_renewed")
    assert h.view()["state"] == "available"
    h.checkpoint()
    h.claim()
    h.append("failed", "failed")
    assert h.view()["state"] == "terminal"
    h.append(
        "resume_requested",
        "checkpointed",
        {"request_hash": REQUEST, "checkpoint_hash": CHECKPOINT},
    )
    assert h.view()["can_pause"] is True


def test_unleased_pause_resume_cancel_and_old_receipt_are_distinct_from_latest_view():
    h = History()
    first = h.request()
    h.resolve("paused", "unleased")
    paused = h.view()
    assert (
        paused["state"],
        paused["can_pause"],
        paused["can_cancel"],
        paused["can_resume_control"],
    ) == ("paused", False, True, True)
    h.request("resume")
    h.resolve("resumed", "unleased")
    assert h.view()["state"] == "available"
    h.request("cancel")
    h.resolve("cancelled", "unleased")
    h.append("cancelled", "cancelled")
    view = h.view()
    receipt = find_rc_control_command(h.events, first["control_id"])
    result = build_rc_control_command_result(receipt, view)
    assert result["control_id"] == first["control_id"]
    assert result["accepted_control_revision"] == 1
    assert result["view"]["last_command"]["control_id"] == control_id(3)
    assert result["view"]["state"] == "terminal"
    assert find_rc_control_command(h.events, control_id(99)) is None


def test_pause_can_be_strengthened_to_cancel_but_superseded_pause_cannot_resolve():
    h = History()
    h.claim()
    h.request()
    assert h.view()["state"] == "pause_pending" and h.view()["can_cancel"]
    h.request("cancel")
    assert h.view()["state"] == "cancel_pending"
    h.resolve("cancelled", "before_analysis")
    h.append("cancelled", "cancelled")
    assert h.view()["control_revision"] == 2
    h.mutate(
        4,
        lambda p: p.update(
            control_revision=1, control_id=control_id(1), disposition="paused"
        ),
    )
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


def test_pending_allows_only_matching_returned_analysis_verification_then_checkpoint_hold():
    h = History()
    h.claim()
    h.reserve(1)
    h.outcome(1)
    h.request()
    h.reserve(2, "verification", 1)
    h.outcome(2, "verification")
    h.checkpoint()
    h.resolve("paused", "verified_checkpoint")
    view = h.view()
    assert view["state"] == "paused"
    assert view["last_command"]["applied_progress"] == {"completed": 1, "total": 5}
    assert view["last_command"]["applied_checkpoint_hash"] == CHECKPOINT


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["rc_phase"].update(phase="analysis", analysis_ordinal=None),
        lambda p: p["rc_phase"].update(analysis_ordinal=2),
        lambda p: p["rc_phase"].update(chunk_request_hash=CHECKPOINT),
        lambda p: p.update(lease_token_hash=REQUEST),
        lambda p: p.update(attempt=2),
    ],
)
def test_rehashed_verification_reservation_cannot_bypass_pending_control(mutation):
    h = History()
    h.claim()
    h.reserve(1)
    h.outcome(1)
    h.request()
    h.reserve(2, "verification", 1)
    h.mutate(5, mutation)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


def test_analysis_must_have_returned_and_cannot_fund_two_verifications():
    h = History()
    h.claim()
    h.reserve(1)
    h.request()
    h.reserve(2, "verification", 1)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()
    h = History()
    h.claim()
    h.reserve(1)
    h.outcome(1)
    h.request()
    h.reserve(2, "verification", 1)
    h.outcome(2, "verification")
    h.reserve(3, "verification", 1)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


def test_unphased_legacy_reservation_cannot_start_analysis_after_pending():
    h = History()
    h.claim()
    h.request()
    h.append(
        "execution_attempt_reserved",
        payload={"reserved_attempts": 1, "attempt": 1, "lease_token_hash": LEASE},
    )
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()
    h = History()
    h.claim()
    h.reserve(1)
    h.outcome(1)
    h.request()
    h.append(
        "execution_attempt_reserved",
        payload={"reserved_attempts": 2, "attempt": 1, "lease_token_hash": LEASE},
    )
    h.outcome(2, "verification")
    assert h.view()["state"] == "pause_pending"
    h.mutate(6, lambda p: p["metadata"].update(phase="analysis"))
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


@pytest.mark.parametrize("boundary", ["before_analysis", "lease_expired"])
def test_verified_prefix_is_preserved_at_non_numerical_stop_boundaries(boundary):
    h = History()
    h.claim()
    h.checkpoint()
    h.claim()
    h.request()
    if boundary == "lease_expired":
        h.append(
            "lease_expired_requeued", "checkpointed", {"checkpoint_preserved": True}
        )
    h.resolve("paused", boundary)
    view = h.view()
    assert view["job"]["checkpoint_hash"] == CHECKPOINT
    assert view["job"]["attempt"] == 2
    assert view["last_command"]["applied_progress"]["completed"] == 1
    h.claim()
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


@pytest.mark.parametrize(
    "action,disposition,terminal,progress",
    [("pause", "completed", "succeeded", 4), ("cancel", "cancelled", "cancelled", 1)],
)
def test_final_boundary_preserves_terminal_order_and_cancel_keeps_prior_prefix(
    action, disposition, terminal, progress
):
    h = History()
    h.claim()
    h.checkpoint()
    h.claim()
    h.request(action)
    h.resolve(disposition, "verified_final", progress_completed=progress)
    h.append(
        "completed" if action == "pause" else "cancelled",
        terminal,
        {"progress_completed": progress},
    )
    view = h.view()
    assert view["state"] == "terminal" and view["job"]["checkpoint_hash"] == CHECKPOINT
    assert view["last_command"]["applied_progress"]["completed"] == progress
    assert (
        not view["can_pause"]
        and not view["can_cancel"]
        and not view["can_resume_control"]
    )
    h.request("pause")
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


def test_worker_failure_is_not_a_pause_success_and_explicit_failure_retry_releases_terminal_state():
    h = History()
    h.claim()
    h.request()
    h.resolve("failed", "worker_failure")
    h.append("failed", "failed")
    assert h.view()["last_command"]["disposition"] == "failed"
    h.append(
        "resume_requested", "queued", {"request_hash": REQUEST, "checkpoint_hash": None}
    )
    view = h.view()
    assert (
        view["state"] == "available" and view["last_command"]["disposition"] == "failed"
    )
    h.claim()
    h.reserve(1)
    assert h.view()["state"] == "available"


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_request_hash", CHECKPOINT),
        ("expected_checkpoint_hash", CHECKPOINT),
        ("expected_attempt", 1),
        ("expected_control_revision", 1),
    ],
)
def test_rehashed_command_cas_cannot_change_accepted_source(field, value):
    h = History()
    h.request()

    def alter(payload):
        payload["command"][field] = value
        payload["command_hash"] = rc_control_command_hash(payload["command"])

    h.mutate(1, alter)
    h.resolve("paused", "unleased")
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


@pytest.mark.parametrize("bad_action", ["pause", "resume"])
def test_pending_control_cannot_be_retracted_or_weakened(bad_action):
    h = History()
    h.claim()
    h.request("cancel")
    h.request(bad_action)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


def test_duplicate_id_resolution_and_incomplete_atomic_prefix_are_rejected():
    h = History()
    h.request()
    h.resolve("paused", "unleased")
    h.resolve("paused", "unleased")
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()
    h = History()
    h.request()
    h.resolve("paused", "unleased")
    h.request("resume", control_id=control_id())
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        find_rc_control_command(h.events, control_id())
    h = History()
    h.request("cancel")
    h.resolve("cancelled", "unleased")
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


def test_view_and_receipt_are_exact_and_capabilities_are_derived():
    h = History()
    h.request()
    h.resolve("paused", "unleased")
    view = h.view()
    for change in [
        lambda v: v.update(can_pause=True),
        lambda v: v.update(can_resume_control=1),
        lambda v: v.update(state="available"),
        lambda v: v["job"].update(tenant_id=None),
        lambda v: v["last_command"].update(applied_checkpoint_hash=CHECKPOINT),
        lambda v: v["last_command"].update(resolved_event_revision=1),
        lambda v: v.update(extra=True),
    ]:
        invalid = deepcopy(view)
        change(invalid)
        with pytest.raises(ValueError, match="rc_control_integrity_failed"):
            validate_rc_control_view(invalid)
    result = build_rc_control_command_result(
        find_rc_control_command(h.events, control_id()), view
    )
    invalid = deepcopy(result)
    invalid["control_id"] = control_id(2)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        validate_rc_control_command_result(invalid)
    receipt = find_rc_control_command(h.events, control_id())
    receipt["command_hash"] = CHECKPOINT
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        build_rc_control_command_result(receipt, view)


def test_generic_unknown_spend_import_is_preserved_after_pause_or_terminal():
    for terminal in (False, True):
        h = History()
        h.request("cancel" if terminal else "pause")
        h.resolve("cancelled" if terminal else "paused", "unleased")
        if terminal:
            h.append("cancelled", "cancelled")
        h.append(
            "execution_authority_reservation_imported",
            payload={"reserved_attempts": 1, "execution_work": "unknown"},
        )
        assert h.view()["state"] == ("terminal" if terminal else "paused")


def test_unknown_spent_reservation_does_not_prevent_stopping_before_new_analysis():
    h = History()
    h.claim()
    h.reserve(1)
    h.request()
    h.resolve("paused", "before_analysis")
    assert h.view()["state"] == "paused"
    assert h.view()["last_command"]["applied_progress"]["completed"] == 0


def test_optional_phase_cannot_be_explicit_null_or_disagree_with_returned_outcome():
    h = History()
    h.claim()
    h.reserve(1, rc_phase=None)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()
    h = History()
    h.claim()
    h.reserve(1)
    h.outcome(1, chunk=CHECKPOINT)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


@pytest.mark.parametrize("wrong_prefix", [1, True])
def test_rehashed_returned_analysis_cannot_be_reused_from_another_durable_prefix(
    wrong_prefix,
):
    h = History()
    h.claim()
    h.reserve(1)
    h.outcome(1)
    h.request()
    h.reserve(2, "verification", 1)
    h.mutate(3, lambda p: p["metadata"].update(completed_before=wrong_prefix))
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        h.view()


@pytest.mark.parametrize(
    "status,checkpoint", [("queued", CHECKPOINT), ("checkpointed", None)]
)
def test_view_rejects_checkpoint_presence_inconsistent_with_unleased_status(
    status, checkpoint
):
    view = History().view()
    view["job"].update(status=status, checkpoint_hash=checkpoint)
    with pytest.raises(ValueError, match="rc_control_integrity_failed"):
        validate_rc_control_view(view)


def test_packaged_json_schema_covers_view_command_and_command_result_shapes():
    path = (
        Path(__file__).parents[1]
        / "src/structural_analysis/schemas/rc_job_control_v1.schema.json"
    )
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    h = History()
    h.request()
    h.resolve("paused", "unleased")
    view = h.view()
    Draft202012Validator(schema).validate(view)
    for name, value in [
        ("command", command()),
        (
            "commandResult",
            build_rc_control_command_result(
                find_rc_control_command(h.events, control_id()), view
            ),
        ),
    ]:
        validator = Draft202012Validator({**schema, "$ref": f"#/$defs/{name}"})
        validator.validate(value)
        invalid = deepcopy(value)
        invalid["unknown"] = None
        assert list(validator.iter_errors(invalid))
