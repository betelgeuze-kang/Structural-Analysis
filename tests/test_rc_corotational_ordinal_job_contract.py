"""Pure contract fixtures bind actual suffix artifacts, never owner authority."""

import base64
from copy import deepcopy
import json

import pytest

from tests.test_rc_corotational_ordinal_job_request import ordinal_request
from structural_analysis.api.rc_corotational_ordinal_control import (
    analyze_ordinal_job,
    verify_ordinal_job,
)
from structural_analysis.execution.rc_corotational_job_request import (
    _sha,
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
    bind_ordinal_receipts,
    build_ordinal_job_payload,
    build_ordinal_job_receipt,
    ordinal_chunk_hash,
    ordinal_resume_binding,
    validate_ordinal_invocation_outcome,
    validate_ordinal_job_checkpoint,
    validate_ordinal_job_result,
)
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    validate_rc_corotational_ordinal_job_request,
)
from structural_analysis.execution.rc_corotational_ordinal_report import (
    build_ordinal_report,
)


def rehash(value, field):
    value[field] = _sha(
        rc_corotational_job_canonical_bytes(
            {k: v for k, v in value.items() if k != field}
        )
    )
    return value


def grant(request, ordinal, phase, checkpoint=None, *, ceiling=2, record_limit=3):
    binding = ordinal_resume_binding(request, checkpoint, record_limit=record_limit)
    return rehash(
        {
            "schema_version": "rc-ordinal-solver-credit-reservation.v1",
            "job_request_hash": request.request_hash,
            "context_hash": request.context_hash,
            "credit_ordinal": ordinal,
            "api_ordinal": ordinal,
            "phase": phase,
            "ceiling": ceiling,
            "completed_before": binding["completed_before"],
            "prior_checkpoint_hash": None
            if checkpoint is None
            else _sha(rc_corotational_job_canonical_bytes(checkpoint)),
            "native_input_sha256": binding["native_input_sha256"],
            "record_limit": record_limit,
            "authority_id": "authored-contract-fixture",
            "authority_generation": 1,
            "authority_root": "/authored/contract-fixture",
            "worker_id": "authored-worker",
            "lease_token_hash": "sha256:" + "a" * 64,
        },
        "grant_hash",
    )


def budgets(request, grants):
    api = dict(
        maximum_attempts=request.execution_config.maximum_api_invocations,
        reserved_attempts=len(grants),
        remaining_attempts=request.execution_config.maximum_api_invocations
        - len(grants),
    )
    solver = {"context_hash": request.context_hash, "reservations": deepcopy(grants)}
    for phase in ("production", "verification"):
        maximum = getattr(request.execution_config, phase + "_solver_budget")
        spent = sum(g["ceiling"] for g in grants if g["phase"] == phase)
        solver[phase] = dict(maximum=maximum, reserved=spent, remaining=maximum - spent)
    return api, solver


def pair(request, grants, checkpoint=None, *, ceiling=2, record_limit=3):
    binding = ordinal_resume_binding(request, checkpoint, record_limit=record_limit)
    artifacts = analyze_ordinal_job(
        request.request_bytes,
        binding["native_continuation_bytes"],
        ceiling,
        record_limit,
    )
    api = json.loads(artifacts.result_bytes)
    report = json.loads(
        verify_ordinal_job(
            request.request_bytes,
            binding["native_continuation_bytes"],
            artifacts.result_bytes,
            artifacts.continuation_bytes,
            ceiling,
            record_limit,
        )
    )
    outcomes = []
    for phase in ("production", "verification"):
        g = grant(
            request,
            len(grants) + 1,
            phase,
            checkpoint,
            ceiling=ceiling,
            record_limit=record_limit,
        )
        grants.append(g)
        outcome = dict(
            schema_version="rc-corotational-ordinal-invocation.v1",
            phase=phase,
            status="returned",
            job_request_hash=request.request_hash,
            context_hash=request.context_hash,
            chunk_request_hash=ordinal_chunk_hash(request, g),
            completed_before=binding["completed_before"],
            completed_after=api["completed_after"],
            restart_input_sha256=binding["native_input_sha256"],
            timing=dict(wall_ns=1, process_cpu_ns=1),
            api_result=api if phase == "production" else None,
            checkpoint_artifact_base64=base64.b64encode(
                artifacts.continuation_bytes
            ).decode()
            if phase == "production"
            else None,
            verification_report=report if phase == "verification" else None,
            error=None,
            unavailable_execution_work=False,
            grant=g,
            credits_used=api["credits_used"],
            # Authored pure-validator fixture; no child process custody is claimed.
            phase_supervision=dict(
                phase=phase,
                policy=request.execution_config.phase_execution_policy.to_dict(),
                status="returned",
                supervisor=dict(direct_child_reaped=True, child_returncode=0),
                parent_wall_ns=1,
                parent_process_cpu_ns=1,
                cleanup={},
            ),
        )
        outcomes.append({"ordinal": g["api_ordinal"], "outcome": outcome})
    receipt = build_ordinal_job_receipt(
        request,
        production_ordinal=outcomes[0]["ordinal"],
        verification_ordinal=outcomes[1]["ordinal"],
        production_outcome=outcomes[0]["outcome"],
        verification_outcome=outcomes[1]["outcome"],
    )
    return artifacts, api, outcomes, receipt


def complete_fixture():
    request = validate_rc_corotational_ordinal_job_request(ordinal_request())
    grants = []
    artifact, api, outcomes, first_receipt = pair(request, grants)
    execution, solver = budgets(request, grants)
    checkpoint = build_ordinal_job_payload(
        request,
        receipts=[first_receipt],
        execution_budget=execution,
        solver_credit_budget=solver,
        terminal_checkpoint=artifact.continuation_bytes,
        api_result=api,
        complete=False,
    )
    artifact, api, second_outcomes, receipt = pair(request, grants, checkpoint)
    execution, solver = budgets(request, grants)
    result = build_ordinal_job_payload(
        request,
        receipts=[first_receipt, receipt],
        execution_budget=execution,
        solver_credit_budget=solver,
        terminal_checkpoint=artifact.continuation_bytes,
        api_result=api,
        complete=True,
    )
    outcomes += second_outcomes
    return request, checkpoint, result, outcomes, execution, solver


def test_actual_suffix_receipts_preserve_prefix_and_complete_full_source():
    request, checkpoint, result, outcomes, execution, solver = complete_fixture()
    validation = validate_ordinal_job_result(
        result,
        request=request,
        execution_budget=execution,
        solver_credit_budget=solver,
        checkpoint=checkpoint,
    )
    assert validation["contract_pass"] and validation["complete"]
    assert validation["progress_completed"] == 4
    bind_ordinal_receipts(result["receipts"], outcomes, request, solver)
    substituted = deepcopy(checkpoint)
    substituted["receipts"][0]["production_work"]["solver_invocations"] = 0
    rehash(substituted["receipts"][0], "receipt_hash")
    rehash(substituted, "checkpoint_hash")
    with pytest.raises(ValueError, match="replaced or skipped"):
        validate_ordinal_job_result(
            result,
            request=request,
            execution_budget=execution,
            solver_credit_budget=solver,
            checkpoint=substituted,
        )


def test_rehashed_receipt_cannot_substitute_owner_recorded_originals():
    request, _, result, outcomes, _, solver = complete_fixture()
    receipt = deepcopy(result["receipts"][0])
    receipt["production_work"]["solver_invocations"] = 0
    rehash(receipt, "receipt_hash")
    with pytest.raises(ValueError, match="differs from immutable"):
        bind_ordinal_receipts([receipt], outcomes, request, solver)
    forged_grants = deepcopy(solver)
    forged_grants["reservations"][0]["ceiling"] = 1
    rehash(forged_grants["reservations"][0], "grant_hash")
    with pytest.raises(ValueError, match="differs from external"):
        bind_ordinal_receipts(result["receipts"], outcomes, request, forged_grants)


def test_old_saved_checkpoint_read_cannot_refund_later_unknown_credit():
    request, checkpoint, _, _, _, _ = complete_fixture()
    grants = deepcopy(checkpoint["solver_credit_budget"]["reservations"])
    grants.append(grant(request, 3, "production", checkpoint))
    execution, solver = budgets(request, grants)
    restored = validate_ordinal_job_checkpoint(
        checkpoint,
        request=request,
        progress_completed=3,
        resume_contract_hash=request.resume_contract_hash,
        execution_budget=execution,
        solver_credit_budget=solver,
    )
    assert restored["payload"]["solver_credit_budget"]["production"]["reserved"] == 2
    assert solver["production"]["reserved"] == 4
    corrupted = deepcopy(solver)
    corrupted["production"]["reserved"] = 2
    corrupted["production"]["remaining"] += 2
    with pytest.raises(ValueError, match="credits disagree"):
        validate_ordinal_job_checkpoint(
            checkpoint,
            request=request,
            progress_completed=3,
            resume_contract_hash=request.resume_contract_hash,
            execution_budget=execution,
            solver_credit_budget=corrupted,
        )


def test_unknown_raised_outcome_cannot_claim_zero_or_returned_work():
    request, _, _, outcomes, _, _ = complete_fixture()
    outcome = deepcopy(outcomes[0]["outcome"])
    outcome.update(
        status="raised",
        api_result=None,
        checkpoint_artifact_base64=None,
        verification_report=None,
        error={"type": "AuthoredTimeout"},
        unavailable_execution_work=True,
        credits_used=None,
    )
    assert (
        validate_ordinal_invocation_outcome(outcome, request, request.request_hash)[
            "credits_used"
        ]
        is None
    )
    outcome["credits_used"] = 0
    with pytest.raises(ValueError, match="nonrefundable unknown"):
        validate_ordinal_invocation_outcome(outcome, request, request.request_hash)


def test_full_report_preserves_all_rows_and_per_window_originals_without_solver_or_source_fingerprint(
    monkeypatch,
):
    request, checkpoint, result, outcomes, execution, solver = complete_fixture()
    validation = validate_ordinal_job_result(
        result,
        request=request,
        execution_budget=execution,
        solver_credit_budget=solver,
        checkpoint=checkpoint,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("saved report executed a solver or fingerprinted current source")

    monkeypatch.setattr(
        "structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver._source_identity",
        forbidden,
    )
    monkeypatch.setattr(
        "structural_analysis.execution.rc_corotational_ordinal_job_request._source_identity",
        forbidden,
    )
    monkeypatch.setattr(
        "structural_analysis.api.rc_corotational_ordinal_control.analyze_ordinal_job",
        forbidden,
    )
    report = json.loads(
        build_ordinal_report(
            request,
            result,
            {"invocations": outcomes, "validation_report": validation},
            job_id="authored-contract-fixture",
        )
    )
    assert [s["ordinal"] for s in report["samples"]] == [0, 1, 2, 3]
    assert [s["observed_force_kn"] for s in report["samples"]] == [0.0, 1.0, 2.0, 3.0]
    assert report["samples"][1]["kind"] == "verified_hold"
    assert report["known_solver_invocations"] == {"production": 3, "verification": 3}
    assert len(report["native_window_originals"]) == 2
    assert report["force_comparison_status"] == "explicit_force_observer_not_admitted"
    assert report["authority"]["experimental_physical_validation"] is False


def test_zero_solver_resume_requires_an_entire_hold_window():
    payload = ordinal_request(
        [(-1e-6, 0.01), (-1e-6, 0.01), (-1e-6, 0.01), (-1e-6, 0.02)]
    )
    request = validate_rc_corotational_ordinal_job_request(payload)
    grants = []
    artifact, api, _, receipt = pair(request, grants, ceiling=1, record_limit=1)
    execution, solver = budgets(request, grants)
    checkpoint = build_ordinal_job_payload(
        request,
        receipts=[receipt],
        execution_budget=execution,
        solver_credit_budget=solver,
        terminal_checkpoint=artifact.continuation_bytes,
        api_result=api,
        complete=False,
    )
    assert (
        ordinal_resume_binding(request, checkpoint, record_limit=2)["requires_solver"]
        is False
    )
    assert (
        ordinal_resume_binding(request, checkpoint, record_limit=3)["requires_solver"]
        is True
    )
    assert (
        ordinal_resume_binding(request, None, record_limit=2)["requires_solver"] is True
    )
