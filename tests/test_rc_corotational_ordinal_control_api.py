"""Actual suffix solves preserve source holds, independent P, and rollback."""

import json

import pytest

from tests.test_rc_corotational_ordinal_job_request import ordinal_request
from structural_analysis.api.rc_corotational_ordinal_control import (
    analyze_ordinal_job,
    verify_ordinal_job,
)
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    validate_rc_corotational_ordinal_job_request,
)


def test_separately_replayed_suffix_preserves_hold_and_changed_p():
    request = validate_rc_corotational_ordinal_job_request(ordinal_request())
    first = analyze_ordinal_job(request.request_bytes, None, 2, 3)
    value = json.loads(first.result_bytes)
    assert value["completed_after"] == 3 and value["status"] == "paused"
    assert value["credits_used"] == 2
    assert value["work"]["hold_records"] == 1
    assert [e["kind"] for e in value["events"]] == [
        "mechanical_commit",
        "verified_hold",
        "mechanical_commit",
    ]
    assert [e["ordinal"] for e in value["events"]] == [0, 1, 2]
    assert (
        value["events"][0]["mechanical_state_hash"]
        == value["events"][1]["mechanical_state_hash"]
    )
    assert (
        value["events"][2]["mechanical_state_hash"]
        != value["events"][1]["mechanical_state_hash"]
    )
    report = json.loads(
        verify_ordinal_job(
            request.request_bytes,
            None,
            first.result_bytes,
            first.continuation_bytes,
            2,
            3,
        )
    )
    assert report["artifact_contract_pass"] and report["credits_used"] == 2
    assert report["prefix_replay_solver_invocations"] == 0
    second = analyze_ordinal_job(request.request_bytes, first.continuation_bytes, 2, 3)
    final = json.loads(second.result_bytes)
    assert final["completed_before"] == 3 and final["completed_after"] == 4
    assert final["credits_used"] == 1 and final["status"] == "complete"
    assert final["work"]["resume_verification_assembly_attempts"] == 1
    assert len(final["events"]) == 1
    verify_ordinal_job(
        request.request_bytes,
        first.continuation_bytes,
        second.result_bytes,
        second.continuation_bytes,
        2,
        3,
    )


def test_zero_credit_cannot_solve_an_uncertified_first_row():
    request = validate_rc_corotational_ordinal_job_request(
        ordinal_request([(0.0, 0.0)])
    )
    artifact = analyze_ordinal_job(request.request_bytes, None, 0, 1)
    value = json.loads(artifact.result_bytes)
    assert value["credits_used"] == 0 and value["completed_after"] == 0
    assert value["status"] == "paused" and not value["events"]


def test_verification_rejects_a_different_grant_or_altered_artifact():
    request = validate_rc_corotational_ordinal_job_request(ordinal_request())
    artifact = analyze_ordinal_job(request.request_bytes, None, 2, 3)
    with pytest.raises(ValueError, match="differs"):
        verify_ordinal_job(
            request.request_bytes,
            None,
            artifact.result_bytes,
            artifact.continuation_bytes,
            1,
            3,
        )
    altered = bytearray(artifact.continuation_bytes)
    altered[-2] ^= 1
    with pytest.raises(ValueError, match="differs"):
        verify_ordinal_job(
            request.request_bytes, None, artifact.result_bytes, bytes(altered), 2, 3
        )
