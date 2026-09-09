"""Real constant-load durable continuation; pure receipt tampering tests reuse it."""

from copy import deepcopy
from datetime import datetime, timezone
import base64
import json
from pathlib import Path

import jsonschema
import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.execution import rc_fiber_job_contract as contract
from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.execution.job_worker import execute_job_claim

ROOT = Path(__file__).resolve().parents[1]
TENANT = dict(
    tenant_id="tenant", authorization_token="constant-test-tenant-token-0123456789"
)
WORKER = dict(
    worker_id="worker", authorization_token="constant-test-worker-token-0123456789"
)
TARGETS = (-1e-5, -2e-5, 1e-5)


def _service(directory):
    return DurableJobService(
        directory,
        tenant_tokens={"tenant": TENANT["authorization_token"]},
        worker_tokens={"worker": WORKER["authorization_token"]},
        worker_tenants={"worker": {"tenant"}},
        clock=lambda: datetime(2026, 9, 10, tzinfo=timezone.utc),
    )


def request(chunk=1):
    return dict(
        schema_version=contract.RC_FIBER_JOB_REQUEST_SCHEMA_VERSION,
        operation=contract.RC_FIBER_JOB_OPERATION,
        case_id="constant-durable-fixture",
        model=json.loads(
            (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_bytes()
        ),
        config=BoundedRCFiberDirectControlRequest(
            control_global_dof=4,
            targets_m=TARGETS,
            allow_reversals=True,
            maximum_reversals=2,
            constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
        ).to_dict(),
        source_revision="a"
        * 40,  # Authored fixture declaration, not independent execution proof.
        result_contract=contract.CONSTANT_RC_FIBER_JOB_RESULT_SCHEMA_VERSION,
        execution_config=dict(chunk_target_count=chunk, maximum_api_invocations=12),
    )


def forbidden(*args, **kwargs):
    pytest.fail("pure service validation must not execute preload or lateral solves")


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    directory = tmp_path_factory.mktemp("constant-durable")
    results = {}
    for label, chunk in (("split", 1), ("full", 3)):
        req = request(chunk)
        store = directory / label
        service = _service(store)
        job = service.submit_job(**TENANT, idempotency_key=label, request=req)
        observed = {"preload": 0, "lateral": 0}
        preload = paths.solve_stateful_fiber_frame2d_constant_load_preload
        lateral = paths.solve_stateful_fiber_frame2d_displacement_control_step

        def observe_preload(*args, **kwargs):
            observed["preload"] += 1
            return preload(*args, **kwargs)

        def observe_lateral(*args, **kwargs):
            observed["lateral"] += 1
            return lateral(*args, **kwargs)

        checkpoints = []
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                paths,
                "solve_stateful_fiber_frame2d_constant_load_preload",
                observe_preload,
            )
            patch.setattr(
                paths,
                "solve_stateful_fiber_frame2d_displacement_control_step",
                observe_lateral,
            )
            for completed in range(chunk, 4, chunk):
                service = _service(
                    store
                )  # Reopen durable state before every worker claim.
                claim = service.claim_next(**WORKER, lease_seconds=300)
                assert claim is not None
                if claim.checkpoint_bytes is not None:
                    checkpoints.append(json.loads(claim.checkpoint_bytes))
                job = execute_job_claim(service, claim, **WORKER)
                assert job.progress_completed == completed
                assert job.status == ("succeeded" if completed == 3 else "checkpointed")
                assert service.validate_integrity(job.job_id, **TENANT)["contract_pass"]
        raw = service.read_result(job.job_id, **TENANT)
        value = json.loads(raw)
        evidence = service.read_rc_invocation_evidence(job.job_id, **TENANT)
        invocations = [
            json.loads(
                service.read_rc_invocation_artifact(
                    job.job_id, **TENANT, ordinal=row["ordinal"]
                )
            )
            for row in evidence["invocations"]
        ]
        results[label] = dict(
            request=req,
            result=value,
            raw=raw,
            checkpoints=checkpoints,
            observed=observed,
            invocations=invocations,
        )
    return results


def test_pure_constant_request_schema_and_binding(monkeypatch):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_constant_load_preload", forbidden
    )
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    req = request()
    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/job_request_v3.schema.json"
        ).read_bytes()
    )
    jsonschema.validate(req, schema)
    _, typed = contract.validate_rc_fiber_job_request(req)
    _, compiled, scope, _, _ = contract._context(req)
    assert compiled.problem.constant_external_loads == ((3, -600.0),)
    assert typed.to_dict() == req["config"]
    assert scope["problem_contract_hash"] == compiled.problem.contract_hash
    changed = deepcopy(req)
    changed["config"]["constant_nodal_loads"][0]["FX_kN"] = -601.0
    assert contract.rc_fiber_job_resume_contract_hash(
        changed
    ) != contract.rc_fiber_job_resume_contract_hash(req)
    changed["result_contract"] = contract.RC_FIBER_JOB_RESULT_SCHEMA_VERSION
    with pytest.raises(ValueError, match="loading profile"):
        contract.validate_rc_fiber_job_request(changed)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(changed, schema)


def test_actual_reopened_chunks_match_full_physical_history_and_native_state(actual):
    split, full = actual["split"], actual["full"]
    for arm in (split, full):
        result = arm["result"]
        assert (
            result["schema_version"]
            == contract.CONSTANT_RC_FIBER_JOB_RESULT_SCHEMA_VERSION
        )
        assert result["profile"] == contract.CONSTANT_RC_FIBER_JOB_PROFILE
        assert result["completed_target_count"] == 3
        assert not result["authority"]["independent_physical_validation"]
    assert split["observed"] == {"preload": 6, "lateral": 12}
    assert full["observed"] == {"preload": 2, "lateral": 6}
    a, b = split["result"]["api_result"], full["result"]["api_result"]
    for key in (
        "preload_response",
        "response_history",
        "terminal_response",
        "checkpoint",
        "model",
    ):
        assert a[key] == b[key]
    assert (
        split["result"]["terminal_checkpoint_artifact_base64"]
        == full["result"]["terminal_checkpoint_artifact_base64"]
    )
    assert [r["epoch"] for r in a["response_history"]] == [2, 3, 4]
    assert a["preload_response"]["support_reactions"][0]["value_si"] == pytest.approx(
        600000.0
    )


def test_each_analysis_and_verification_charges_preload_and_prefix(actual):
    arm = actual["split"]
    receipts = arm["result"]["receipts"]
    assert arm["result"]["execution_budget"]["reserved_attempts"] == 6
    assert [
        r["analysis_metrics"]["control_work"]["attempted_step_count"] for r in receipts
    ] == [2, 3, 4]
    assert [
        r["verification_metrics"]["replay_control_work"]["attempted_step_count"]
        for r in receipts
    ] == [2, 3, 4]
    assert len({r["preload_step_hash"] for r in receipts}) == 1
    assert len({r["preload_checkpoint_state_hash"] for r in receipts}) == 1
    total = 0
    for row in arm["invocations"]:
        assert row["status"] == "returned" and not row["unavailable_execution_work"]
        work = (
            row["api_result"]["metrics"]["control_work"]
            if row["phase"] == "analysis"
            else row["verification_report"]["replay_control_work"]
        )
        total += work["attempted_step_count"]
    assert total == sum(arm["observed"].values()) == 18


def _rehash(value, key):
    value[key] = contract._hash({k: v for k, v in value.items() if k != key})


def _rebind_result(value):
    api_value = value["api_result"]
    _rehash(api_value["path"], "path_hash")
    _rehash(api_value, "result_hash")
    tail = value["receipts"][-1]
    tail["path_hash"] = api_value["path"]["path_hash"]
    tail["result_hash"] = api_value["result_hash"]
    tail["result_artifact_sha256"] = contract._hash(api_value)
    tail["validation_report"]["verified_result_hash"] = api_value["result_hash"]
    _rehash(tail, "receipt_hash")
    _rehash(value, "result_hash")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_response",
        "preload_epoch",
        "preload_parent",
        "lateral_epoch",
        "preload_work",
        "preload_attempt",
        "preload_metrics",
        "initial_epoch",
        "earlier_preload",
        "legacy_schema",
    ],
)
def test_rehashed_preload_and_history_corruption_rejected_without_solving(
    actual, monkeypatch, mutation
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_constant_load_preload", forbidden
    )
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    arm = actual["split"]
    value = deepcopy(arm["result"])
    a = value["api_result"]
    if mutation == "missing_response":
        a.pop("preload_response")
    elif mutation == "preload_epoch":
        a["preload_response"]["epoch"] = 0
    elif mutation == "preload_parent":
        a["preload_response"]["parent_checkpoint_hash"] = "sha256:" + "0" * 64
    elif mutation == "lateral_epoch":
        a["response_history"][0]["epoch"] = 1
    elif mutation == "preload_work":
        a["path"]["metrics"]["preload_work"]["known_linear_solve_count"] += 1
    elif mutation == "preload_attempt":
        a["path"]["preload_attempts"][0]["step"]["committed"] = False
    elif mutation == "preload_metrics":
        a["path"]["preload_attempts"][0]["solver_work"]["linear_solve_count"] += 1
    elif mutation == "initial_epoch":
        a["path"]["initial_checkpoint"]["epoch"] -= 1
    elif mutation == "earlier_preload":
        value["receipts"][0]["preload_step_hash"] = "sha256:" + "0" * 64
        _rehash(value["receipts"][0], "receipt_hash")
    elif mutation == "legacy_schema":
        a["schema_version"] = api.BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION
    _rebind_result(value)
    with pytest.raises(ValueError):
        contract.validate_rc_fiber_job_result(
            value, request=arm["request"], execution_budget=value["execution_budget"]
        )


def test_constant_checkpoint_retains_prefix_receipts_and_changed_load_rejects(
    actual, monkeypatch
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_constant_load_preload", forbidden
    )
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    arm = actual["split"]
    for i, checkpoint in enumerate(arm["checkpoints"], 1):
        assert (
            checkpoint["schema_version"]
            == contract.CONSTANT_RC_FIBER_JOB_CHECKPOINT_SCHEMA_VERSION
        )
        assert checkpoint["completed_target_count"] == i
        assert checkpoint["receipts"] == arm["result"]["receipts"][:i]
        native = json.loads(
            base64.b64decode(checkpoint["terminal_checkpoint_artifact_base64"])
        )
        assert native["preload_checkpoint"]["epoch"] == 1
        assert native["terminal_checkpoint"]["epoch"] == i + 1
    changed = deepcopy(arm["request"])
    changed["config"]["constant_nodal_loads"][0]["FX_kN"] = -601.0
    with pytest.raises(ValueError):
        contract.validate_rc_fiber_job_result(
            arm["result"],
            request=changed,
            execution_budget=arm["result"]["execution_budget"],
        )


def test_actual_failed_preload_retains_both_worker_invocations_and_no_checkpoint(
    tmp_path, monkeypatch
):
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        RCFiberDirectControlWorkerError,
    )

    req = request()
    req["config"]["constant_nodal_loads"][0]["FX_kN"] = -30000.0
    req["config"]["solver_config"]["newton"]["max_iterations"] = 1
    service = _service(tmp_path / "failed")
    job = service.submit_job(**TENANT, idempotency_key="failed", request=req)
    claim = service.claim_next(**WORKER, lease_seconds=300)
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    with pytest.raises(RCFiberDirectControlWorkerError, match="authored chunk"):
        execute_job_claim(service, claim, **WORKER)
    evidence = service.read_rc_invocation_evidence(job.job_id, **TENANT)
    assert len(evidence["invocations"]) == 2
    records = [
        json.loads(
            service.read_rc_invocation_artifact(
                job.job_id, **TENANT, ordinal=row["ordinal"]
            )
        )
        for row in evidence["invocations"]
    ]
    assert [r["phase"] for r in records] == ["analysis", "verification"]
    for row in records:
        assert row["unavailable_execution_work"]
        work = (
            row["api_result"]["metrics"]["control_work"]
            if row["phase"] == "analysis"
            else row["verification_report"]["replay_control_work"]
        )
        assert (
            work["attempted_step_count"] == 1
            and work["unknown_solver_work_attempt_count"] == 1
        )
    failed = service.get_job(job.job_id, **TENANT)
    assert failed.status == "failed" and failed.checkpoint is None
    assert failed.progress_completed == 0
    assert records[0]["checkpoint_artifact_base64"] is None
    step = records[0]["api_result"]["failure"]["attempts"][0]["step"]
    assert step["parent_checkpoint"] == step["accepted_checkpoint"]


def test_actual_preloaded_zero_first_target_is_valid_durable_input(tmp_path):
    req = request(3)
    req["config"]["targets_m"] = [0.0]
    req["config"]["constant_nodal_loads"][0]["FY_kN"] = -0.1
    service = _service(tmp_path / "origin")
    job = service.submit_job(**TENANT, idempotency_key="origin", request=req)
    claim = service.claim_next(**WORKER, lease_seconds=300)
    job = execute_job_claim(service, claim, **WORKER)
    assert job.status == "succeeded"
    result = json.loads(service.read_result(job.job_id, **TENANT))
    a = result["api_result"]
    assert a["preload_response"]["node_displacements"][1]["UY_m"] < 0
    assert a["path"]["requested_directions"] == [1]
    assert a["path"]["requested_reversal_count"] == 0
    assert a["terminal_response"]["node_displacements"][1]["UY_m"] == pytest.approx(
        0.0, abs=1e-12
    )


def test_exhausted_budget_keeps_v2_checkpoint_without_extra_solves(
    tmp_path, monkeypatch
):
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        RCFiberDirectControlWorkerError,
    )

    req = request()
    req["execution_config"]["maximum_api_invocations"] = 2
    store = tmp_path / "budget"
    service = _service(store)
    job = service.submit_job(**TENANT, idempotency_key="budget", request=req)
    claim = service.claim_next(**WORKER, lease_seconds=300)
    job = execute_job_claim(service, claim, **WORKER)
    assert job.status == "checkpointed" and job.progress_completed == 1
    old_ref = job.checkpoint
    service = _service(store)
    claim = service.claim_next(**WORKER, lease_seconds=300)
    assert claim.job.checkpoint == old_ref
    prior_bytes = claim.checkpoint_bytes
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_constant_load_preload", forbidden
    )
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )
    with pytest.raises(RCFiberDirectControlWorkerError, match="reservations"):
        execute_job_claim(service, claim, **WORKER)
    failed = service.get_job(job.job_id, **TENANT)
    assert failed.status == "failed" and failed.checkpoint == old_ref
    assert failed.progress_completed == 1
    assert service.read_checkpoint(job.job_id, **TENANT) == prior_bytes
    evidence = service.read_rc_invocation_evidence(job.job_id, **TENANT)
    assert len(evidence["invocations"]) == 2
